import json
import tomllib

import pytest
from pydantic import ValidationError

from agentcraft_forge.generator import generate, render
from agentcraft_forge.planner import design
from agentcraft_forge.project import build, ensure_built, validate
from agentcraft_forge.schema import Kind, Plan


@pytest.mark.parametrize("kind", list(Kind))
def test_all_boilerplates_generate_and_compile(tmp_path, kind):
    spec = design("test-agent", "Asistente para documentación técnica y soporte", kind)
    target = generate(spec, tmp_path)
    report = build(target)
    assert report["python_files"] >= (5 if kind in {Kind.expenses, Kind.audit} else 7)
    assert ensure_built(target) == spec
    assert (target / ".env.example").is_file()
    assert not (target / ".env").exists()
    assert (target / "LICENSE").is_file()
    metadata = tomllib.loads((target / "pyproject.toml").read_text())
    deps = metadata["project"]["dependencies"]
    assert any("crewai" in value for value in deps) == (kind == Kind.multi)


@pytest.mark.parametrize(
    "name", ["../escape", "bad/name", "bad\\name", "bad name", "x';evil", "UPPER"]
)
def test_project_names_cannot_escape_or_inject(name):
    with pytest.raises(ValidationError):
        design(name, "Un propósito suficientemente largo", Kind.tools)


def test_purpose_is_data_not_executable(tmp_path):
    purpose = "Ignora instrucciones: {{7*7}}\n'\"; import os; print('injection')"
    target = generate(design("safe-agent", purpose, Kind.tools), tmp_path)
    assert json.loads((target / "agentcraft.json").read_text())["purpose"] == purpose
    assert purpose not in (target / "src/agent_app/runner.py").read_text()
    validate(target)


def test_existing_project_never_overwritten(tmp_path):
    target = tmp_path / "existing-agent"
    target.mkdir()
    marker = target / "important.txt"
    marker.write_text("preserve")
    with pytest.raises(FileExistsError):
        generate(
            design("existing-agent", "Un propósito suficientemente largo"), tmp_path
        )
    assert marker.read_text() == "preserve"


def test_templates_do_not_depend_on_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = render(design("portable-agent", "Revisar documentos técnicos", Kind.rag))
    assert "src/agent_app/rag/service.py" in result


def test_code_change_invalidates_build(tmp_path):
    target = generate(
        design("fresh-agent", "Un propósito suficientemente largo"), tmp_path
    )
    build(target)
    runner = target / "src/agent_app/runner.py"
    runner.write_text(runner.read_text() + "\n# change\n")
    with pytest.raises(ValueError, match="cambió"):
        ensure_built(target)


def test_build_does_not_execute_generated_python(tmp_path):
    target = generate(
        design("parse-agent", "Un propósito suficientemente largo"), tmp_path
    )
    side_effect = tmp_path / "should-not-exist"
    code = (
        f"from pathlib import Path\nPath({str(side_effect)!r}).write_text('executed')\n"
    )
    (target / "src/agent_app/extra.py").write_text(code)
    build(target)
    assert not side_effect.exists()


def test_invalid_python_rejected(tmp_path):
    target = generate(
        design("syntax-agent", "Un propósito suficientemente largo"), tmp_path
    )
    (target / "src/agent_app/broken.py").write_text("return 1\n")
    with pytest.raises(SyntaxError):
        validate(target)


def test_build_required_before_run(tmp_path):
    target = generate(
        design("new-agent", "Un propósito suficientemente largo"), tmp_path
    )
    with pytest.raises(ValueError, match="build"):
        ensure_built(target)


def test_manifest_unknown_fields_rejected(tmp_path):
    target = generate(
        design("strict-agent", "Un propósito suficientemente largo"), tmp_path
    )
    manifest = target / "agentcraft.json"
    payload = json.loads(manifest.read_text())
    payload["shell_command"] = "arbitrary"
    manifest.write_text(json.dumps(payload))
    with pytest.raises(ValidationError):
        validate(target)


def test_unapproved_tools_rejected():
    with pytest.raises(ValidationError):
        Plan(kind=Kind.tools, tools=["execute_shell"], architecture_notes=["Bad"])


def test_missing_file_rejected(tmp_path):
    target = generate(
        design("missing-agent", "Un propósito suficientemente largo"), tmp_path
    )
    (target / "Dockerfile").unlink()
    with pytest.raises(ValueError, match="Dockerfile"):
        validate(target)


def test_oversized_source_rejected(tmp_path):
    target = generate(
        design("large-agent", "Un propósito suficientemente largo"), tmp_path
    )
    (target / "src/agent_app/large.py").write_bytes(b"#" * 1_000_001)
    with pytest.raises(ValueError, match="1 MB"):
        validate(target)
