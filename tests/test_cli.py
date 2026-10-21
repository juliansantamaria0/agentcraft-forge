import json

from typer.testing import CliRunner

from agentcraft_forge import __version__
from agentcraft_forge.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_full_offline_cli(tmp_path):
    result = runner.invoke(
        app,
        [
            "init",
            "--name",
            "cli-agent",
            "--purpose",
            "Asistente documental para soporte técnico",
            "--kind",
            "rag",
            "--directory",
            str(tmp_path),
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    target = tmp_path / "cli-agent"
    result = runner.invoke(app, ["build", "--project", str(target)])
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        app,
        [
            "run",
            "--project",
            str(target),
            "--dry-run",
            "--message",
            "Consulta de prueba",
        ],
    )
    assert result.exit_code == 0, result.output
    assert '"model_invoked": false' in result.output


def test_interactive_wizard(tmp_path):
    result = runner.invoke(
        app,
        ["init", "--directory", str(tmp_path)],
        input="interactive-agent\nAsistente para el clima de Bogota\ntools\ny\n",
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "interactive-agent/agentcraft.json").is_file()


def test_wizard_cancel_preserves_filesystem(tmp_path):
    result = runner.invoke(
        app,
        ["init", "--directory", str(tmp_path)],
        input="cancel-agent\nAsistente para el clima de Bogota\ntools\nn\n",
    )
    assert result.exit_code != 0
    assert not (tmp_path / "cancel-agent").exists()


def test_automation_requires_name_and_purpose():
    assert runner.invoke(app, ["init", "--yes"]).exit_code != 0


def test_run_without_venv_fails_cleanly(tmp_path):
    runner.invoke(
        app,
        [
            "init",
            "--name",
            "no-env-agent",
            "--purpose",
            "Asistente para soporte técnico",
            "--directory",
            str(tmp_path),
            "--yes",
        ],
    )
    target = tmp_path / "no-env-agent"
    runner.invoke(app, ["build", "--project", str(target)])
    result = runner.invoke(
        app, ["run", "--project", str(target), "--message", "Consulta"]
    )
    assert result.exit_code == 1
    assert "Run falló" in result.output


def test_dry_run_json_does_not_wrap_long_strings(tmp_path):
    runner.invoke(
        app,
        [
            "init",
            "--name",
            "json-agent",
            "--purpose",
            "Asistente para soporte técnico",
            "--directory",
            str(tmp_path),
            "--yes",
        ],
    )
    target = tmp_path / "json-agent"
    runner.invoke(app, ["build", "--project", str(target)])
    message = "x" * 2000
    result = runner.invoke(
        app, ["run", "--project", str(target), "--dry-run", "--message", message]
    )
    assert json.loads(result.output)["message"] == message
