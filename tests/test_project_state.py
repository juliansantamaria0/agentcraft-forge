import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agentcraft_forge.cli import app
from agentcraft_forge.generator import generate
from agentcraft_forge.integration import inspect_project
from agentcraft_forge.planner import design
from agentcraft_forge.project import build, ensure_built
from agentcraft_forge.schema import Kind


@pytest.fixture
def project(tmp_path):
    target = generate(
        design("state-agent", "Registrar gastos personales", Kind.expenses), tmp_path
    )
    build(target)
    return target


def test_failed_install_invalidates_previous_build(project, monkeypatch):
    from agentcraft_forge import project as operations

    monkeypatch.setattr(operations.venv.EnvBuilder, "create", lambda *args: None)

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["pip", "install"])

    monkeypatch.setattr(operations.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        build(project, install=True)
    with pytest.raises(ValueError, match="build"):
        ensure_built(project)
    assert inspect_project(project)["build_fresh"] is False


def test_failed_validation_also_invalidates_previous_build(project):
    (project / "Dockerfile").unlink()
    with pytest.raises(ValueError):
        build(project)
    with pytest.raises(ValueError):
        ensure_built(project)


def test_build_report_cannot_survive_source_changes_during_install(
    project, monkeypatch
):
    from agentcraft_forge import project as operations

    monkeypatch.setattr(operations.venv.EnvBuilder, "create", lambda *args: None)

    def change_source(*args, **kwargs):
        (project / "src/agent_app/extra.py").write_text(
            "# changed during install\n", encoding="utf-8"
        )

    monkeypatch.setattr(operations.subprocess, "run", change_source)
    with pytest.raises(ValueError, match="cambió"):
        build(project, install=True)
    with pytest.raises(ValueError):
        ensure_built(project)


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "null",
        '{"fingerprint":"bad"}',
        '{"schema_version":1,"schema_version":2}',
        "{",
    ],
)
def test_corrupt_build_state_is_reported_without_traceback(project, content):
    (project / ".agentcraft/build.json").write_text(content, encoding="utf-8")
    result = CliRunner().invoke(app, ["inspect", "--project", str(project)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["build_fresh"] is False
    assert payload["build_status"] == "invalid"
    with pytest.raises(ValueError, match="build"):
        ensure_built(project)
    build(project)
    assert inspect_project(project)["build_status"] == "fresh"


@pytest.mark.parametrize(
    "content", ["[]", "null", '{"original_files":{}}', '{"original_files":42}']
)
def test_corrupt_provenance_is_a_controlled_json_error(project, content):
    (project / "agentcraft.provenance.json").write_text(content, encoding="utf-8")
    result = CliRunner().invoke(app, ["inspect", "--project", str(project)])
    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "error"
    assert result.exception is not None
    assert "Traceback" not in result.output


def test_added_python_source_changes_origin_status(project):
    (project / "src/agent_app/custom_tool.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    origin = inspect_project(project)["origin"]
    assert origin["status"] == "modified"
    assert origin["added_source_files"] == ["src/agent_app/custom_tool.py"]


def test_ensure_built_rechecks_required_files(project):
    (project / "Dockerfile").unlink()
    with pytest.raises(ValueError, match="Dockerfile"):
        ensure_built(project)


def test_interrupted_build_report_write_has_no_valid_old_report(project, monkeypatch):
    from agentcraft_forge import project as operations

    def fail(*args):
        raise OSError("Simulated full disk")

    monkeypatch.setattr(operations, "atomic_text", fail)
    with pytest.raises(OSError):
        build(project)
    with pytest.raises(ValueError, match="build"):
        ensure_built(project)


def test_build_rejects_linked_report_before_touching_it(project, monkeypatch):
    state = project / ".agentcraft/build.json"
    previous = state.read_bytes()
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == state or original(path)
    )
    with pytest.raises(ValueError, match="enlaces"):
        build(project)
    assert state.read_bytes() == previous


@pytest.mark.parametrize(
    "field,value",
    [("installed", "yes"), ("python_files", True), ("schema_version", True)],
)
def test_build_state_requires_exact_field_types(project, field, value):
    state = project / ".agentcraft/build.json"
    report = json.loads(state.read_text(encoding="utf-8"))
    report[field] = value
    state.write_text(json.dumps(report), encoding="utf-8")
    assert inspect_project(project)["build_status"] == "invalid"
    with pytest.raises(ValueError, match="build"):
        ensure_built(project)


@pytest.mark.parametrize(
    "mutation", ["empty_inventory", "invalid_hash", "unsafe_path", "boolean_schema"]
)
def test_provenance_checks_structure_hashes_and_paths(project, mutation):
    path = project / "agentcraft.provenance.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "empty_inventory":
        record["original_files"] = {}
    elif mutation == "invalid_hash":
        record["original_files"]["README.md"] = 123
    elif mutation == "unsafe_path":
        record["original_files"]["../outside"] = "0" * 64
    else:
        record["schema_version"] = True
    path.write_text(json.dumps(record), encoding="utf-8")
    result = CliRunner().invoke(app, ["inspect", "--project", str(project)])
    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "error"


def test_duplicate_manifest_fields_do_not_silently_override_requirements(project):
    path = project / "agentcraft.json"
    content = path.read_text(encoding="utf-8")
    path.write_text(
        '{"purpose":"Otra intención",' + content.lstrip()[1:], encoding="utf-8"
    )
    with pytest.raises(ValueError, match="repetidas"):
        build(project)


def test_build_record_inconsistent_with_sources_is_stale(project):
    state = project / ".agentcraft/build.json"
    report = json.loads(state.read_text(encoding="utf-8"))
    report["python_files"] += 1
    state.write_text(json.dumps(report), encoding="utf-8")
    assert inspect_project(project)["build_status"] == "stale"
    with pytest.raises(ValueError, match="cambió"):
        ensure_built(project)


def test_inspect_reports_invalid_python_as_json(project):
    (project / "src/agent_app/broken.py").write_text("return 1\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["inspect", "--project", str(project)])
    assert result.exit_code == 1
    assert json.loads(result.output)["code"] == "SyntaxError"


def test_inspect_reports_invalid_project_table_as_json(project):
    (project / "pyproject.toml").write_text("project = 42\n", encoding="utf-8")
    result = CliRunner().invoke(app, ["inspect", "--project", str(project)])
    assert result.exit_code == 1
    assert json.loads(result.output)["code"] == "ValueError"
