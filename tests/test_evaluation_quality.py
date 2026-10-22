import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

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
from agentcraft_forge.evaluation_review import (
    ReviewDocument,
    apply_review,
    prepare_review,
)
from agentcraft_forge.generator import generate
from agentcraft_forge.planner import design
from agentcraft_forge.project import build, validate
from agentcraft_forge.schema import Kind


@pytest.mark.parametrize(
    "op,value",
    [
        ("min_length", True),
        ("min_length", -1),
        ("min_length", "3"),
        ("max_value", True),
        ("max_value", float("inf")),
        ("exists", 1),
        ("contains_any", []),
        ("contains_any", [""]),
        ("contains_any", "yes"),
    ],
)
def test_bad_grader_operands_rejected_before_execution(op, value):
    with pytest.raises(ValueError):
        Check(path="answer", op=op, value=value)


@pytest.mark.parametrize(
    "actual,expected",
    [
        ([True], [1]),
        ({"value": True}, {"value": 1}),
        ({"nested": [1]}, {"nested": [1.0]}),
    ],
)
def test_nested_json_types_do_not_create_false_passes(actual, expected):
    case = Case(
        id="strict",
        category="boundary",
        message="Synthetic case",
        checks=[Check(path="data", op="equals", value=expected)],
    )
    assert not grade(case, {"data": actual})[0]["passed"]


def test_contains_any_accepts_variants_without_accepting_wrong_answer():
    case = Case(
        id="variants",
        category="capability",
        message="Plazo",
        checks=[
            Check(path="answer", op="contains_any", value=["cuatro horas", "4 horas"])
        ],
    )
    assert grade(case, {"answer": "Se atiende en 4 horas."})[0]["passed"]
    assert grade(case, {"answer": "Se atiende en CUATRO HORAS."})[0]["passed"]
    assert not grade(case, {"answer": "cuatro días"})[0]["passed"]


def test_exists_distinguishes_missing_from_null_and_rejects_negative_index():
    case = Case(
        id="presence",
        category="boundary",
        message="Synthetic",
        checks=[
            Check(path="missing", op="exists", value=False),
            Check(path="null", op="exists", value=True),
            Check(path="items.-1", op="equals", value="last"),
        ],
    )
    assert [c["passed"] for c in grade(case, {"null": None, "items": ["last"]})] == [
        True,
        True,
        False,
    ]


def test_tool_failure_with_right_number_does_not_pass(runtime_project):
    target, _ = runtime_project("tools")
    case = next(
        c for c in load_suite(target / "evals/smoke.json").cases if c.id == "weather"
    )
    fabricated = {
        "answer": "21 grados en Madrid",
        "tool_calls": 1,
        "observations": [
            {
                "tool": "current_weather",
                "arguments": {"city": "Madrid"},
                "error": "tool_unavailable",
            }
        ],
    }
    assert not all(c["passed"] for c in grade(case, fabricated))
    fabricated["observations"][0].pop("error")
    fabricated["observations"][0]["result"] = "Temperatura sintética de evaluación"
    assert all(c["passed"] for c in grade(case, fabricated))
    assert case.human_review  # Passing these rules still requires semantic review.


def human_report(tmp_path, **acceptance):
    target = generate(
        design("review-agent", "Evaluación con revisión declarada", Kind.tools),
        tmp_path,
    )
    build(target)
    suite = Suite(
        name="review-case",
        kind=Kind.tools,
        acceptance=acceptance,
        cases=[
            Case(
                id="response",
                category="capability",
                message="Sintético",
                human_review=True,
                checks=[Check(path="answer", op="equals", value="ok")],
            )
        ],
    )

    def execute(*args):
        return Trial(
            status="ok",
            response={"answer": "ok"},
            usage_known=True,
            usage=[{"model": "test", "input_tokens": 1, "output_tokens": 1}],
        )

    result = evaluate(
        target,
        suite,
        live=True,
        rates={"test": Price(input_per_million=1, output_per_million=1)},
        max_cost_usd=1,
        executor=execute,
        clock=iter([0.0, 2.0]).__next__,
    )
    path = tmp_path / "report.json"
    path.write_text(json.dumps(result), encoding="utf-8")
    return path, result


def test_automatic_pass_keeps_human_review_pending(tmp_path):
    path, result = human_report(tmp_path)
    assert result["metrics"]["rule_pass_rate"] == 1
    assert result["quality_gate"]["decision"] == "review_required"
    _, form = prepare_review(path)
    assert form.reviewer is None
    assert all(answer is None for item in form.reviews for answer in item.answers)


def test_latency_policy_can_fail_even_if_all_rules_pass(tmp_path):
    _, result = human_report(tmp_path, max_latency_p95_seconds=1)
    assert result["quality_gate"]["decision"] == "failed"


@pytest.mark.parametrize(
    "decision,expected",
    [(True, "accepted"), (False, "failed"), (None, "review_required")],
)
def test_review_applies_only_declared_answers(tmp_path, decision, expected):
    report, _ = human_report(tmp_path)
    _, form = prepare_review(report)
    form.reviewer = "Revisor de prueba"
    for item in form.reviews:
        item.answers = [decision] * len(item.criteria)
        item.notes = "Anotación sintética para probar el flujo; no es una evaluación de un modelo real."
    path = tmp_path / "review.json"
    path.write_text(form.model_dump_json(), encoding="utf-8")
    assert apply_review(report, path)["quality_gate"]["decision"] == expected


def test_review_rejects_wrong_report_duplicate_trials_and_changed_criteria(tmp_path):
    report, _ = human_report(tmp_path)
    _, template = prepare_review(report)
    data = template.model_dump()
    path = tmp_path / "reviews.json"
    for mutate in [
        lambda d: d.update(report_sha256="0" * 64),
        lambda d: d["reviews"].append(d["reviews"][0]),
        lambda d: d["reviews"][0]["criteria"].append("Fake criterion"),
    ]:
        altered = json.loads(json.dumps(data))
        mutate(altered)
        path.write_text(json.dumps(altered), encoding="utf-8")
        with pytest.raises(ValueError):
            apply_review(report, path)


def test_review_requires_strict_booleans_identity_and_evidence_note(tmp_path):
    report, _ = human_report(tmp_path)
    _, form = prepare_review(report)
    data = form.model_dump()
    data["reviews"][0]["answers"] = [1] * len(data["reviews"][0]["criteria"])
    with pytest.raises(ValueError):
        ReviewDocument.model_validate(data)
    form.reviews[0].answers = [True] * len(form.reviews[0].criteria)
    path = tmp_path / "reviews.json"
    path.write_text(form.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError, match="Identifique"):
        apply_review(report, path)


def test_review_cli_never_overwrites_and_template_contains_no_approval(tmp_path):
    report, _ = human_report(tmp_path)
    output = tmp_path / "form.json"
    runner = CliRunner()
    result = runner.invoke(
        app, ["review-evaluation", "--report", str(report), "--output", str(output)]
    )
    assert result.exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["reviewer"] is None
    previous = output.read_bytes()
    assert (
        runner.invoke(
            app, ["review-evaluation", "--report", str(report), "--output", str(output)]
        ).exit_code
        == 1
    )
    assert output.read_bytes() == previous


def test_complete_expenses_suite_runs_three_times_on_fresh_state(
    runtime_project, tmp_path
):
    from tempfile import TemporaryDirectory

    target, module = runtime_project("expenses")
    worker = module("evaluate")
    suite = load_suite(target / "evals/complete.json")
    spec = json.loads((target / "agentcraft.json").read_text(encoding="utf-8"))
    for _ in range(suite.repetitions):
        with TemporaryDirectory(dir=tmp_path) as directory:
            response = worker.execute(
                spec,
                {
                    "case": suite.cases[0].model_dump(),
                    "reference_date": suite.reference_date,
                },
                Path(directory),
                [],
                {},
            )
            assert all(c["passed"] for c in grade(suite.cases[0], response))
    assert not (target / ".data").exists()


def test_unexpected_domain_error_and_missing_expected_error_fail(
    runtime_project, tmp_path
):
    target, module = runtime_project("expenses")
    worker = module("evaluate")
    suite = load_suite(target / "evals/smoke.json")
    spec = json.loads((target / "agentcraft.json").read_text(encoding="utf-8"))
    case = next(
        c for c in suite.cases if c.id == "invalid-batch-keeps-state"
    ).model_dump()
    case["expected_errors"] = {"1": "wrong_code"}
    with pytest.raises(ValueError):
        worker.execute(spec, {"case": case}, tmp_path, [], {})
    case["requests"] = [{"action": "summary"}]
    case["expected_errors"] = {"0": "invalid_integer"}
    with pytest.raises(ValueError, match="No ocurrió"):
        worker.execute(spec, {"case": case}, tmp_path, [], {})


def test_new_evaluation_resource_does_not_break_existing_v030_inventory(tmp_path):
    spec = design(
        "old-project", "Compatibilidad con la versión previa", Kind.expenses
    ).model_copy(update={"generator_version": "0.3.0"})
    root = generate(spec, tmp_path)
    assert not (root / "evals/complete.json").exists()
    assert validate(root)["kind"] == "expenses"


def test_budget_overrun_does_not_accept_an_otherwise_successful_trial(tmp_path):
    from agentcraft_forge.evaluation import assess

    _, result = human_report(tmp_path, require_human_review=False)
    result["max_cost_usd"] = 0.0000001
    assert assess(result)["decision"] == "failed"
    assert (
        next(
            item
            for item in assess(result)["checks"]
            if item["name"] == "estimated_budget_usd"
        )["passed"]
        is False
    )


def test_review_hash_uses_the_same_bytes_that_were_parsed(tmp_path, monkeypatch):
    import hashlib

    from agentcraft_forge import evaluation_review

    report, result = human_report(tmp_path)
    original = report.read_bytes()

    def captured(_):
        report.write_text("changed-after-read", encoding="utf-8")
        return result, original

    monkeypatch.setattr(evaluation_review, "read_json_document", captured)
    _, form = prepare_review(report)
    assert form.report_sha256 == hashlib.sha256(original).hexdigest()


def test_review_criteria_cannot_be_blank_and_large_integers_are_finite():
    with pytest.raises(ValueError):
        Case(
            id="blank",
            category="capability",
            message="Caso",
            human_review=True,
            review_criteria=["     "],
            checks=[Check(path="answer", op="equals", value="ok")],
        )
    case = Case(
        id="large",
        category="boundary",
        message="Entero grande",
        checks=[Check(path="value", op="max_value", value=10**1000)],
    )
    assert grade(case, {"value": 10**999})[0]["passed"]
