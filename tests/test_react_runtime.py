import pytest


@pytest.fixture
def runtime(runtime_project):
    pytest.importorskip(
        "langchain_core",
        reason="Estas pruebas requieren el extra ai; CI instala todos los extras.",
    )
    _, load = runtime_project("tools")
    return load("react")


class Model:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.messages.append(list(messages))
        return next(self.responses)


class Tool:
    name = "lookup"

    def __init__(self):
        self.calls = []

    def invoke(self, args):
        self.calls.append(args)
        return "Resultado de prueba"


def call(identifier="call-1", name="lookup"):
    return {"id": identifier, "name": name, "args": {}}


def test_mixed_valid_and_invalid_calls_are_rejected_before_tools(runtime):
    response = runtime.AIMessage(
        content="",
        tool_calls=[call()],
        invalid_tool_calls=[
            {
                "id": "call-bad",
                "name": "lookup",
                "args": "{",
                "error": "invalid JSON",
            }
        ],
    )
    tool = Tool()
    with pytest.raises(ValueError, match="inválida"):
        runtime.run_react(Model([response]), [tool], "Consulta de prueba")
    assert tool.calls == []


@pytest.mark.parametrize("ids", [[None], [""], [" "], ["call-1", "call-1"]])
def test_bad_or_duplicate_ids_never_execute_current_batch(runtime, ids):
    response = runtime.AIMessage(content="", tool_calls=[call(value) for value in ids])
    tool = Tool()
    with pytest.raises(ValueError, match="identificador"):
        runtime.run_react(Model([response]), [tool], "Consulta de prueba")
    assert tool.calls == []


def test_reused_id_in_later_turn_does_not_repeat_tool(runtime):
    response = runtime.AIMessage(content="", tool_calls=[call()])
    tool = Tool()
    with pytest.raises(ValueError, match="identificador"):
        runtime.run_react(Model([response, response]), [tool], "Consulta de prueba")
    assert len(tool.calls) == 1


@pytest.mark.parametrize(
    "limits",
    [
        {"max_steps": True},
        {"max_steps": 1.5},
        {"max_tool_calls": True},
        {"deadline_seconds": float("nan")},
        {"deadline_seconds": float("inf")},
        {"deadline_seconds": True},
    ],
)
def test_invalid_budgets_fail_before_model_call(runtime, limits):
    model = Model([])
    with pytest.raises(ValueError):
        runtime.run_react(model, [Tool()], "Consulta de prueba", **limits)
    assert model.messages == []


def test_valid_calls_keep_observations_and_matching_ids(runtime):
    tool = Tool()
    model = Model(
        [
            runtime.AIMessage(content="", tool_calls=[call()]),
            runtime.AIMessage(content="Respuesta"),
        ]
    )
    result = runtime.run_react(model, [tool], "Consulta de prueba")
    assert result.tool_calls == 1
    assert result.observations == [{"tool": "lookup", "result": "Resultado de prueba"}]
    assert model.messages[1][-1].tool_call_id == "call-1"


def test_oversized_batch_cannot_partially_spend_tool_budget(runtime):
    tool = Tool()
    response = runtime.AIMessage(content="", tool_calls=[call("one"), call("two")])
    with pytest.raises(runtime.BudgetExceeded):
        runtime.run_react(
            Model([response]), [tool], "Consulta de prueba", max_tool_calls=1
        )
    assert tool.calls == []


def test_unapproved_tool_is_denied_and_counts_against_budget(runtime):
    tool = Tool()
    model = Model(
        [
            runtime.AIMessage(content="", tool_calls=[call(name="shell")]),
            runtime.AIMessage(content="Herramienta no disponible"),
        ]
    )
    result = runtime.run_react(model, [tool], "Consulta de prueba")
    assert tool.calls == []
    assert result.tool_calls == 1
    assert result.observations == [{"tool": "shell", "error": "tool_not_allowed"}]


def test_expired_deadline_after_model_prevents_tools(runtime):
    tool = Tool()
    ticks = iter([0.0, 0.0, 2.0])
    model = Model([runtime.AIMessage(content="", tool_calls=[call()])])
    with pytest.raises(runtime.BudgetExceeded):
        runtime.run_react(
            model,
            [tool],
            "Consulta de prueba",
            deadline_seconds=1,
            clock=lambda: next(ticks),
        )
    assert tool.calls == []
