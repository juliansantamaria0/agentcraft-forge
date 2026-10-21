import json
import subprocess
import sys

import pytest
from typer.testing import CliRunner

from agentcraft_forge.cli import app
from agentcraft_forge.generator import generate
from agentcraft_forge.integration import doctor, inspect_project, install_skill
from agentcraft_forge.planner import design
from agentcraft_forge.project import build
from agentcraft_forge.schema import Kind


def test_evidence_changes_and_build_freshness_are_distinct(tmp_path):
    target = generate(
        design("my-expenses", "Registrar gastos personales", Kind.expenses), tmp_path
    )
    result = inspect_project(target)
    assert result["origin"]["status"] == "matches_recorded_origin"
    assert not result["build_fresh"]
    build(target)
    assert inspect_project(target)["build_fresh"]
    source = target / "src/agent_app/domain.py"
    source.write_text(
        source.read_text(encoding="utf-8") + "\n# customization\n", encoding="utf-8"
    )
    result = inspect_project(target)
    assert result["origin"]["status"] == "modified"
    assert not result["build_fresh"]
    assert result["behavioral_tests"] == "not_run_by_inspect"


def test_installer_is_explicit_repeatable_and_preserves_custom_skills(tmp_path):
    path = install_skill(tmp_path / "skills")
    assert path == install_skill(tmp_path / "skills")
    path.write_text("Custom instructions", encoding="utf-8")
    with pytest.raises(FileExistsError):
        install_skill(tmp_path / "skills")
    assert path.read_text() == "Custom instructions"
    assert len(doctor()["templates"]) == 5


def test_cli_creation_is_machine_readable_and_infers_domain(tmp_path):
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--name",
            "personal-expenses",
            "--purpose",
            "Registrar gastos personales y resúmenes",
            "--directory",
            str(tmp_path),
            "--yes",
            "--json",
        ],
    )
    payload = json.loads(result.output)
    assert result.exit_code == 0
    assert payload["kind"] == "expenses"
    assert (tmp_path / "personal-expenses" / payload["provenance"]).is_file()


def test_legacy_templates_can_be_inspected_without_fabricating_origin(tmp_path):
    spec = design("old-project", "Revisar documentos de soporte", Kind.rag).model_copy(
        update={"template_version": "1", "generator_version": None}
    )
    target = generate(spec, tmp_path)
    build(target)
    assert inspect_project(target)["origin"]["status"] == "legacy_without_provenance"


def test_cli_timeout_never_claims_no_write(tmp_path, monkeypatch):
    from agentcraft_forge import cli

    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")

    def timeout(*args):
        raise subprocess.TimeoutExpired("runtime", 120)

    monkeypatch.setattr(cli, "run_request", timeout)
    result = CliRunner().invoke(
        app, ["invoke", "--project", str(tmp_path), "--request", str(request)]
    )
    assert result.exit_code == 2
    assert json.loads(result.output)["persisted"] is None


def test_generated_runtime_persists_across_processes(tmp_path):
    target = generate(
        design("portable-expenses", "Registrar gastos personales", Kind.expenses),
        tmp_path,
    )
    request_file = tmp_path / "request.json"

    def invoke(request):
        request_file.write_text(
            json.dumps(request, ensure_ascii=False), encoding="utf-8"
        )
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                "-I",
                "-c",
                "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('agent_app.runner',run_name='__main__')",
                str(target / "src"),
                "--root",
                str(target),
                "--request",
                str(request_file),
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        return json.loads(result.stdout)

    request = {
        "action": "record",
        "operation_id": "message-unicode-001",
        "currency": "COP",
        "expenses": [
            {
                "amount": 24500,
                "description": "Café y galleta",
                "expense_date": "2026-10-21",
            }
        ],
    }
    assert invoke(request)["persisted"]
    assert invoke(request)["replayed"]
    assert invoke({"action": "summary"})["total"] == 24500
