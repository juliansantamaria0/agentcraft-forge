import json

import pytest

pytest.importorskip("langchain_openai")

from langchain_core.messages import AIMessage


def test_runtime_logs_model_and_tool_without_exposing_inputs(
    runtime_project, monkeypatch, capsys
):
    target, load = runtime_project("tools")
    runner = load("runner")
    responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "repository_info", "args": {}}],
            ),
            AIMessage(content="Respuesta sintética"),
        ]
    )

    class Model:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return next(responses)

    class Tool:
        name = "repository_info"

        def invoke(self, args):
            return "contenido-privado-de-la-herramienta"

    monkeypatch.setattr(load("providers"), "chat_model", lambda settings: Model())
    monkeypatch.setattr(load("tools"), "build_tools", lambda client: [Tool()])
    assert (
        runner.main(
            ["--root", str(target), "--message", "pregunta-privada-del-usuario"]
        )
        == 0
    )
    output = capsys.readouterr()
    assert json.loads(output.out)["answer"] == "Respuesta sintética"
    events = [json.loads(line) for line in output.err.splitlines()]
    assert {"agent.run", "agent.query", "model.invoke", "tool.invoke"} <= {
        e["operation"] for e in events
    }
    assert all(
        e["status"] == "ok" and e["run_id"] and e["elapsed_seconds"] >= 0
        for e in events
    )
    assert "privad" not in output.err
    assert len({e["run_id"] for e in events}) == 1


def test_failed_model_has_error_event_and_json_error(
    runtime_project, monkeypatch, capsys
):
    target, load = runtime_project("tools")
    runner = load("runner")

    class Model:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            raise ValueError("dato-confidencial")

    monkeypatch.setattr(load("providers"), "chat_model", lambda settings: Model())
    assert runner.main(["--root", str(target), "--message", "dato-del-usuario"]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["error"] == "ValueError"
    events = [json.loads(line) for line in output.err.splitlines()]
    assert any(
        e["operation"] == "model.invoke" and e["status"] == "error" for e in events
    )
    assert any(e["operation"] == "agent.run" and e["status"] == "error" for e in events)
    assert "confidencial" not in output.err + output.out


def test_container_spec_can_live_outside_writable_data(
    runtime_project, monkeypatch, capsys, tmp_path
):
    target, load = runtime_project("tools")
    monkeypatch.setenv("AGENTCRAFT_SPEC_PATH", str(target / "agentcraft.json"))
    workspace = tmp_path / "data-only"
    workspace.mkdir()

    class Model:
        def bind_tools(self, tools):
            return self

        def invoke(self, messages):
            return AIMessage(content="ok")

    monkeypatch.setattr(load("providers"), "chat_model", lambda settings: Model())
    assert load("runner").main(["--root", str(workspace), "--message", "consulta"]) == 0
    assert json.loads(capsys.readouterr().out)["answer"] == "ok"
    assert not (workspace / "agentcraft.json").exists()
