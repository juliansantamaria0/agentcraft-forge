import json
import subprocess
from importlib.resources import files

import pytest
from typer.testing import CliRunner

from agentcraft_forge.catalog import (
    Kind,
    ToolDefinition,
    capabilities,
    register_tool,
    scope,
)
from agentcraft_forge.cli import app
from agentcraft_forge.evaluation import (
    Case,
    Check,
    Price,
    Suite,
    Trial,
    evaluate,
    grade,
    load_suite,
)
from agentcraft_forge.generator import generate, render
from agentcraft_forge.planner import design
from agentcraft_forge.project import build, validate


def make_project(tmp_path, kind=Kind.tools):
    root = generate(
        design("evaluation-project", "Pruebas con datos sintéticos", kind), tmp_path
    )
    build(root)
    return root, load_suite(root / "evals/smoke.json")


def minimal_suite(kind=Kind.tools, repetitions=1):
    return Suite(
        name="minimal",
        kind=kind,
        repetitions=repetitions,
        cases=[
            Case(
                id="one",
                category="abstention",
                message="Pregunta sintética",
                checks=[Check(path="answer", op="equals", value="ok")],
            )
        ],
    )


def success(*args):
    return Trial(
        status="ok",
        response={"answer": "ok"},
        usage_known=True,
        usage=[{"model": "test-model", "input_tokens": 100, "output_tokens": 50}],
    )


PRICES = {"test-model": Price(input_per_million=1, output_per_million=2)}


@pytest.mark.parametrize("kind", list(Kind))
def test_all_templates_include_valid_suite_and_scope(tmp_path, kind):
    root, suite = make_project(tmp_path, kind)
    assert suite.kind == kind
    assert {case.category for case in suite.cases} >= {
        "capability",
        "abstention",
        "boundary",
    }
    assert json.loads((root / "scope.json").read_text(encoding="utf-8")) == scope(
        design("scope-project", "Datos de prueba", kind)
    )
    assert validate(root)["kind"] == kind.value


def test_plan_is_read_only_and_never_invokes_executor(tmp_path):
    root, _ = make_project(tmp_path)
    before = sorted(p.relative_to(root) for p in root.rglob("*"))
    result = evaluate(
        root, minimal_suite(), executor=lambda *_: pytest.fail("No execution")
    )
    assert result["mode"] == "plan"
    assert result["model_execution_requested"] is False
    assert "metrics" not in result
    assert before == sorted(p.relative_to(root) for p in root.rglob("*"))


@pytest.mark.parametrize(
    "options",
    [
        {"run": True},
        {"live": True},
        {"live": True, "rates": PRICES},
        {"live": True, "rates": PRICES, "max_cost_usd": float("nan")},
    ],
)
def test_live_requires_explicit_activation_rates_and_budget(tmp_path, options):
    root, _ = make_project(tmp_path)
    with pytest.raises(ValueError):
        evaluate(
            root,
            minimal_suite(),
            executor=lambda *_: pytest.fail("No execution"),
            **options,
        )


def test_reliability_metrics_keep_missing_attempts_in_denominator(tmp_path):
    root, _ = make_project(tmp_path)
    suite = minimal_suite(repetitions=3)
    result = evaluate(
        root, suite, live=True, rates=PRICES, max_cost_usd=0.0001, executor=success
    )
    metrics = result["metrics"]
    assert result["status"] == "incomplete"
    assert result["stop_reason"] == "budget_reached"
    assert metrics["completed_trials"] == 1
    assert metrics["rule_pass_at_k"] == 1
    assert metrics["rule_pass_power_k"] == 0
    assert metrics["abstention_rule_pass_rate"] == pytest.approx(1 / 3)
    assert metrics["estimated_cost_usd"] == pytest.approx(0.0002)
    assert metrics["cost_complete"] is False


def test_unknown_usage_never_becomes_zero_and_stops(tmp_path):
    root, _ = make_project(tmp_path)

    def unknown(*args):
        return Trial(status="ok", response={"answer": "ok"}, usage_known=False)

    result = evaluate(
        root,
        minimal_suite(repetitions=2),
        live=True,
        rates=PRICES,
        max_cost_usd=1,
        executor=unknown,
    )
    assert result["stop_reason"] == "unknown_usage_or_rate"
    assert result["metrics"]["estimated_cost_usd"] is None
    assert len(result["trials"]) == 1


def test_unknown_model_rate_is_not_free(tmp_path):
    root, _ = make_project(tmp_path)
    result = evaluate(
        root,
        minimal_suite(),
        live=True,
        rates={"other": next(iter(PRICES.values()))},
        max_cost_usd=1,
        executor=success,
    )
    assert result["trials"][0]["estimated_cost_usd"] is None


def test_timeout_is_error_with_unknown_cost(tmp_path):
    root, _ = make_project(tmp_path)

    def timeout(*args):
        raise subprocess.TimeoutExpired("worker", 1)

    result = evaluate(
        root, minimal_suite(), live=True, rates=PRICES, max_cost_usd=1, executor=timeout
    )
    assert result["trials"][0]["error"] == "timeout"
    assert result["trials"][0]["passed"] is False
    assert result["metrics"]["rule_pass_at_1"] == 0


def test_rule_grader_missing_values_and_false_positive_boundaries():
    case = Case(
        id="rules",
        category="capability",
        message="Synthetic",
        checks=[
            Check(path="nested.0.value", op="equals", value=1),
            Check(path="answer", op="contains", value="HOLA"),
            Check(path="answer", op="not_contains", value="secret"),
            Check(path="nested", op="min_length", value=1),
            Check(path="tool_calls", op="max_value", value=0),
            Check(path="absent", op="equals", value=None),
        ],
    )
    checks = grade(
        case, {"nested": [{"value": True}], "answer": "hola", "tool_calls": 0}
    )
    assert [c["passed"] for c in checks] == [False, True, True, True, True, False]


def test_suite_rejects_duplicate_ids_invalid_dates_and_escaped_fixtures():
    data = minimal_suite().model_dump()
    data["cases"] *= 2
    with pytest.raises(ValueError):
        Suite.model_validate(data)
    data = minimal_suite().model_dump()
    data["reference_date"] = "2026-02-30"
    with pytest.raises(ValueError):
        Suite.model_validate(data)
    data = minimal_suite(Kind.expenses).model_dump()
    data["cases"][0]["files"] = {"../personal.txt": "bad"}
    with pytest.raises(ValueError):
        Suite.model_validate(data)


def test_cli_preview_and_report_no_overwrite(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "plan",
            "--name",
            "preview-agent",
            "--purpose",
            "Consultar clima mundial",
            "--kind",
            "tools",
        ],
    )
    assert result.exit_code == 0
    assert "Madrid" in result.output and "crewAIInc/crewAI" in result.output
    assert not list(tmp_path.iterdir())
    root, _ = make_project(tmp_path)
    report = tmp_path / "report.json"
    report.write_text("existing", encoding="utf-8")
    result = runner.invoke(
        app, ["evaluate", "--project", str(root), "--live", "--report", str(report)]
    )
    assert result.exit_code == 1
    assert report.read_text(encoding="utf-8") == "existing"


@pytest.mark.parametrize("version", ["1", "2"])
def test_legacy_templates_keep_original_file_contract(tmp_path, version):
    spec = design("legacy-agent", "Prueba de compatibilidad", Kind.tools).model_copy(
        update={"template_version": version}
    )
    contents = render(spec)
    assert "evals/smoke.json" not in contents
    assert "src/agent_app/tool_registry.py" not in contents
    assert "RepositoryName" in contents["src/agent_app/tools.py"]
    root = generate(spec, tmp_path)
    assert validate(root)["kind"] == "tools"


def test_registry_extension_updates_planner_and_validation(monkeypatch):
    from agentcraft_forge import catalog

    monkeypatch.setattr(catalog, "TOOLS", dict(catalog.TOOLS))
    # Runtime resources must be supplied in the package before generating this tool.
    register_tool(
        ToolDefinition(
            "example",
            "tool_plugins/example.py",
            "agent_app.tool_plugins.example:build",
            "Example scope",
        )
    )
    assert "example" in capabilities(Kind.tools)
    spec = design("extensible-agent", "Prueba del catálogo", Kind.tools)
    assert "example" in spec.plan.tools
    assert (
        next(item for item in scope(spec)["capabilities"] if item["name"] == "example")[
            "scope"
        ]
        == "Example scope"
    )
    with pytest.raises(ValueError):
        register_tool(catalog.TOOLS["example"])


@pytest.mark.parametrize("kind", ["expenses", "audit"])
def test_generated_domain_evaluation_uses_scratch_data(runtime_project, kind):
    target, module = runtime_project(kind)
    worker = module("evaluate")
    suite = load_suite(target / "evals/smoke.json")
    from pathlib import Path
    from tempfile import TemporaryDirectory

    spec = json.loads((target / "agentcraft.json").read_text(encoding="utf-8"))
    for case in suite.cases:
        with TemporaryDirectory() as temporary:
            response = worker.execute(
                spec,
                {"case": case.model_dump(), "reference_date": suite.reference_date},
                Path(temporary),
                [],
                {},
            )
        assert all(c["passed"] for c in grade(case, response)), (case.id, response)
    assert not (target / ".data").exists()


def test_registered_tools_use_fixed_destinations_and_validate_arguments(
    runtime_project,
):
    import httpx
    from pydantic import ValidationError

    _, module = runtime_project("tools")
    worker = module("evaluate")
    tools_module = module("tools")
    with httpx.Client(transport=httpx.MockTransport(worker.fixture_response)) as client:
        tools = {t.name: t for t in tools_module.build_tools(client)}
        assert (
            json.loads(tools["current_weather"].invoke({"city": "Madrid"}))["current"][
                "temperature_2m"
            ]
            == 21
        )
        assert (
            json.loads(
                tools["repository_info"].invoke({"repository": "qdrant/qdrant"})
            )["stars"]
            == 123
        )
        with pytest.raises(ValidationError):
            tools["current_weather"].invoke({"city": "Tokyo"})
        with pytest.raises(ValidationError):
            tools["repository_info"].invoke({"repository": "unapproved/private"})


def test_packaged_suites_are_available():
    root = files("agentcraft_forge").joinpath("templates", "evals")
    assert len([path for path in root.iterdir() if path.name.endswith(".json")]) == 5


@pytest.mark.parametrize(
    "metadata,known",
    [
        ({"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}, True),
        (None, False),
    ],
)
def test_generated_chat_meter_uses_provider_metadata(
    runtime_project, monkeypatch, metadata, known
):
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    _, module = runtime_project("tools")
    worker = module("evaluate")

    class Model(BaseChatModel):
        @property
        def _llm_type(self):
            return "test"

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(content="ok", usage_metadata=metadata)
                    )
                ]
            )

    monkeypatch.setattr(module("providers"), "chat_model", lambda _: Model())
    settings = module("settings").Settings()
    usage = []
    state = {"known": True, "started": 0, "finished": 0}
    model = worker.model_with_usage(settings, usage, state)
    model.invoke("Mensaje sintético")
    assert state == {"known": known, "started": 1, "finished": 1}
    assert usage == (
        [{"model": settings.chat_model, "input_tokens": 10, "output_tokens": 4}]
        if known
        else []
    )


@pytest.mark.parametrize("tokens,known", [(25, True), (None, False)])
def test_generated_embedding_meter_uses_real_response_shape(
    runtime_project, monkeypatch, tokens, known
):
    from types import SimpleNamespace

    _, module = runtime_project("rag")
    data = {"data": [], "usage": {"total_tokens": tokens}}
    embeddings = SimpleNamespace(client=SimpleNamespace(create=lambda **kwargs: data))
    monkeypatch.setattr(module("providers"), "embeddings_model", lambda _: embeddings)
    state = {"known": True}
    usage = []
    settings = module("settings").Settings()
    metered = module("evaluate").embeddings_with_usage(settings, usage, state)
    assert metered.client.create(input="synthetic", model="test") is data
    assert state["known"] is known
    assert usage == (
        [{"model": settings.embedding_model, "input_tokens": 25, "output_tokens": 0}]
        if known
        else []
    )


def test_worker_rejects_unpriced_models_before_api(
    runtime_project, monkeypatch, tmp_path
):
    target, module = runtime_project("tools")
    monkeypatch.chdir(target)
    monkeypatch.setattr(
        module("providers"), "chat_model", lambda _: pytest.fail("No model call")
    )
    spec = json.loads((target / "agentcraft.json").read_text(encoding="utf-8"))
    case = minimal_suite().cases[0].model_dump()
    with pytest.raises(ValueError, match="tarifas"):
        module("evaluate").execute(
            spec, {"case": case, "priced_models": []}, tmp_path, [], {}
        )


@pytest.mark.parametrize("kind", [Kind.expenses, Kind.audit])
def test_domain_cli_executes_worker_protocol_and_saves_report(
    tmp_path, monkeypatch, kind
):
    import sys
    from pathlib import Path

    from agentcraft_forge import evaluation

    root, _ = make_project(tmp_path, kind)
    monkeypatch.setattr(evaluation, "interpreter", lambda _: Path(sys.executable))
    monkeypatch.setenv("PYTHONPATH", str(root / "src"))
    report = root / ".agentcraft/evaluation-test.json"
    result = CliRunner().invoke(
        app, ["evaluate", "--project", str(root), "--run", "--report", str(report)]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "complete"
    assert data["metrics"]["rule_pass_power_k"] == 1
    assert data["metrics"]["estimated_cost_usd"] == 0
    assert not (root / ".data").exists()


def test_multi_usage_survives_proposal_extraction(runtime_project, monkeypatch):
    import sys
    from types import SimpleNamespace

    from pydantic import BaseModel

    _, module = runtime_project("multi")
    runtime = module("multi")

    class Metrics(BaseModel):
        prompt_tokens: int = 120
        completion_tokens: int = 30
        total_tokens: int = 150
        successful_requests: int = 3

    proposal = runtime.Proposal(
        summary="Diseño sintético",
        implementation_steps=["Paso"],
        risks=[],
        acceptance_checks=["Comprobar"],
    )
    output = SimpleNamespace(pydantic=proposal, token_usage=Metrics())
    monkeypatch.setitem(
        sys.modules, "crewai", SimpleNamespace(LLM=lambda **kwargs: object())
    )
    monkeypatch.setattr(
        runtime,
        "build_crew",
        lambda _: SimpleNamespace(kickoff=lambda **kwargs: output),
    )
    metrics = {}
    settings = module("settings").Settings(api_key="synthetic-test-key")
    assert (
        runtime.run_multi(settings, "Requisitos sintéticos", usage=metrics) is proposal
    )
    assert metrics == Metrics().model_dump()
