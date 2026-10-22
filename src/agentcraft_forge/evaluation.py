"""Suites versionadas, reglas explícitas y ejecución optativa del proyecto fiable."""

import hashlib
import json
import math
import subprocess
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentcraft_forge import __version__
from agentcraft_forge.catalog import TEMPLATES, Kind
from agentcraft_forge.domains.common import parse_json
from agentcraft_forge.project import ensure_built, fingerprint, interpreter, read_spec


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Check(Strict):
    path: str = Field(min_length=1, max_length=200)
    op: Literal["equals", "contains", "not_contains", "min_length", "max_value"]
    value: Any


class Case(Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    category: Literal["capability", "abstention", "boundary"]
    message: str = Field(min_length=1, max_length=4000)
    checks: list[Check] = Field(min_length=1, max_length=30)
    human_review: bool = False
    documents: list[Annotated[str, Field(min_length=1, max_length=8000)]] = Field(
        default_factory=list, max_length=10
    )
    files: dict[str, str] = Field(default_factory=dict, max_length=10)
    requests: list[dict] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def bounded_fixtures(self):
        for path, value in self.files.items():
            if (
                not path
                or "\\" in path
                or ":" in path
                or path.startswith("/")
                or ".." in path.split("/")
                or len(value) > 8000
            ):
                raise ValueError("Fixture local no válida.")
        if len(json.dumps(self.requests)) > 32000:
            raise ValueError("Solicitudes sintéticas demasiado grandes.")
        return self


class Suite(Strict):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=100)
    kind: Kind
    reference_date: str = Field(default="2026-10-22", pattern=r"^\d{4}-\d{2}-\d{2}$")
    repetitions: int = Field(default=1, ge=1, le=10, strict=True)
    timeout_seconds: int = Field(default=180, ge=1, le=600, strict=True)
    cases: list[Case] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        from datetime import date

        date.fromisoformat(self.reference_date)
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("IDs de caso duplicados.")
        if not TEMPLATES[self.kind].domain and any(
            c.requests or c.files for c in self.cases
        ):
            raise ValueError(
                "Las fixtures de archivos y solicitudes son solo para dominios."
            )
        if self.kind == Kind.rag and any(not case.documents for case in self.cases):
            raise ValueError("Cada caso RAG requiere un corpus sintético explícito.")
        if self.kind != Kind.rag and any(case.documents for case in self.cases):
            raise ValueError("Los documentos de evaluación son solo para RAG.")
        return self


class Price(Strict):
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)


class Usage(Strict):
    model: str = Field(min_length=1, max_length=200)
    input_tokens: int = Field(ge=0, strict=True)
    output_tokens: int = Field(ge=0, strict=True)


class Trial(Strict):
    status: Literal["ok", "error"]
    response: dict | None = None
    error: str | None = None
    usage_known: bool
    usage: list[Usage] = Field(default_factory=list)


def read_json_file(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("Se requiere un JSON local de hasta 1 MB.")
    value = parse_json(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Se requiere un objeto JSON.")
    return value


def load_suite(path: Path) -> Suite:
    return Suite.model_validate(read_json_file(path))


def grade(case: Case, response: dict) -> list[dict]:
    results = []
    for check in case.checks:
        try:
            value: Any = response
            for part in check.path.split("."):
                value = value[int(part)] if isinstance(value, list) else value[part]
            expected = check.value
            if check.op == "equals":
                passed = type(value) is type(expected) and value == expected
            elif check.op == "contains":
                passed = (
                    expected.casefold() in value.casefold()
                    if isinstance(value, str) and isinstance(expected, str)
                    else expected in value
                )
            elif check.op == "not_contains":
                passed = (
                    expected.casefold() not in value.casefold()
                    if isinstance(value, str) and isinstance(expected, str)
                    else expected not in value
                )
            elif check.op == "min_length":
                passed = len(value) >= expected
            else:
                passed = value <= expected
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            passed = False
        results.append({**check.model_dump(), "passed": bool(passed)})
    return results


def estimate(usage: list[Usage], rates: dict[str, Price]) -> float | None:
    if any(item.model not in rates for item in usage):
        return None
    return sum(
        (
            item.input_tokens * rates[item.model].input_per_million
            + item.output_tokens * rates[item.model].output_per_million
        )
        / 1_000_000
        for item in usage
    )


def _execute(root: Path, payload: dict, timeout: int) -> Trial:
    python = interpreter(root)
    if not python.is_file():
        raise ValueError("Prepare el proyecto con build --install.")
    result = subprocess.run(
        [str(python), "-X", "utf8", "-m", "agent_app.evaluate"],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        cwd=root,
        shell=False,
        timeout=timeout,
        check=False,
    )
    # Se omite stderr: puede contener mensajes de dependencias o datos del proveedor.
    if result.returncode or len(result.stdout) > 1_000_000:
        return Trial(status="error", error="worker_failed", usage_known=False)
    try:
        return Trial.model_validate(parse_json(result.stdout))
    except ValueError:
        return Trial(status="error", error="invalid_worker_result", usage_known=False)


def summarize(suite: Suite, trials: list[dict]) -> dict:
    groups = defaultdict(list)
    for trial in trials:
        groups[trial["case_id"]].append(trial)
    k = suite.repetitions
    first = sum(bool(groups[c.id]) and groups[c.id][0]["passed"] for c in suite.cases)
    any_pass = sum(any(t["passed"] for t in groups[c.id]) for c in suite.cases)
    all_pass = sum(
        len(groups[c.id]) == k and all(t["passed"] for t in groups[c.id])
        for c in suite.cases
    )
    durations = sorted(t["elapsed_seconds"] for t in trials)

    def percentile(fraction):
        return (
            durations[max(0, math.ceil(len(durations) * fraction) - 1)]
            if durations
            else None
        )

    abstentions = [c for c in suite.cases if c.category == "abstention"]
    tokens = {}
    for trial in trials:
        for usage in trial["usage"]:
            values = tokens.setdefault(
                usage["model"], {"input_tokens": 0, "output_tokens": 0}
            )
            values["input_tokens"] += usage["input_tokens"]
            values["output_tokens"] += usage["output_tokens"]
    known = all(
        t["usage_known"] and t["estimated_cost_usd"] is not None for t in trials
    )
    return {
        "planned_trials": len(suite.cases) * k,
        "completed_trials": len(trials),
        "rule_pass_at_1": first / len(suite.cases),
        "rule_pass_at_k": any_pass / len(suite.cases),
        "rule_pass_power_k": all_pass / len(suite.cases),
        "k": k,
        "abstention_rule_pass_rate": (
            sum(t["passed"] for c in abstentions for t in groups[c.id])
            / (len(abstentions) * k)
            if abstentions
            else None
        ),
        "errors": sum(t["status"] != "ok" for t in trials),
        "human_reviews_pending": sum(t["human_review"] for t in trials),
        "latency_seconds_p50": percentile(0.5),
        "latency_seconds_p95": percentile(0.95),
        "estimated_cost_usd": (
            sum(t["estimated_cost_usd"] for t in trials) if known and trials else None
        ),
        "known_cost_subtotal_usd": sum(t["estimated_cost_usd"] or 0 for t in trials),
        "cost_complete": known and len(trials) == len(suite.cases) * k,
        "known_token_subtotals_by_model": tokens,
        "token_usage_complete": bool(trials)
        and all(t["usage_known"] for t in trials)
        and len(trials) == len(suite.cases) * k,
    }


def evaluate(
    root: Path,
    suite: Suite,
    *,
    run: bool = False,
    live: bool = False,
    rates: dict[str, Price] | None = None,
    max_cost_usd: float | None = None,
    executor=None,
    clock=time.monotonic,
) -> dict:
    root = root.resolve(strict=True)
    spec = read_spec(root)
    if spec.plan.kind != suite.kind:
        raise ValueError("La suite no corresponde al tipo de proyecto.")
    if spec.template_version != "3":
        raise ValueError("Las evaluaciones requieren una nueva plantilla v3.")
    model_required = not TEMPLATES[suite.kind].domain
    planned = len(suite.cases) * suite.repetitions
    report = {
        "schema_version": 1,
        "generator_version": __version__,
        "created_at": datetime.now(UTC).isoformat(),
        "project_name": spec.name,
        "template_version": spec.template_version,
        "suite": suite.model_dump(mode="json"),
        "suite_sha256": hashlib.sha256(suite.model_dump_json().encode()).hexdigest(),
        "project_fingerprint": fingerprint(root),
        "mode": "plan",
        "model_execution_requested": False,
        "external_tools": "fixed_http_fixtures" if suite.kind == Kind.tools else "none",
        "planned_trials": planned,
        "trials": [],
        "limitations": [
            "Reglas de regresión; no certifican exactitud semántica.",
            "La ejecución de código local fiable no está aislada por una sandbox.",
            "El presupuesto se comprueba entre intentos; una petición puede excederlo.",
            "Costes estimados con tarifas declaradas, sin descuentos de caché ni facturación oficial.",
        ],
    }
    if not (run or live):
        return report
    if model_required and not live:
        raise ValueError("Este tipo requiere --live para llamar modelos.")
    if not model_required and live:
        raise ValueError("Este tipo es determinista; use --run.")
    rates = rates or {}
    if model_required and (
        not rates
        or max_cost_usd is None
        or not math.isfinite(max_cost_usd)
        or max_cost_usd <= 0
    ):
        raise ValueError("--live requiere tarifas y presupuesto positivo explícitos.")
    ensure_built(root)
    report.update(
        mode="live" if live else "offline",
        model_execution_requested=live,
        rates={name: price.model_dump() for name, price in rates.items()},
        max_cost_usd=max_cost_usd,
        stop_reason=None,
    )
    total = 0.0
    execute = executor or _execute
    for case in suite.cases:
        for repetition in range(1, suite.repetitions + 1):
            if live and total >= max_cost_usd:
                report["stop_reason"] = "budget_reached"
                break
            started = clock()
            try:
                trial = execute(
                    root,
                    {
                        "case": case.model_dump(),
                        "reference_date": suite.reference_date,
                        "priced_models": list(rates),
                    },
                    suite.timeout_seconds,
                )
                trial = Trial.model_validate(trial)
            except subprocess.TimeoutExpired:
                trial = Trial(status="error", error="timeout", usage_known=False)
            except Exception:
                trial = Trial(
                    status="error", error="execution_failed", usage_known=False
                )
            checks = (
                grade(case, trial.response)
                if trial.status == "ok" and trial.response is not None
                else []
            )
            cost = estimate(trial.usage, rates) if trial.usage_known else None
            if not live and trial.usage_known and not trial.usage:
                cost = 0.0
            total += cost or 0
            report["trials"].append(
                {
                    **trial.model_dump(),
                    "case_id": case.id,
                    "repetition": repetition,
                    "elapsed_seconds": round(clock() - started, 6),
                    "checks": checks,
                    "passed": bool(checks) and all(c["passed"] for c in checks),
                    "human_review": case.human_review,
                    "estimated_cost_usd": cost,
                }
            )
            if fingerprint(root) != report["project_fingerprint"]:
                report["stop_reason"] = "project_changed"
                break
            if live and cost is None:
                report["stop_reason"] = "unknown_usage_or_rate"
                break
        if report["stop_reason"]:
            break
    report["metrics"] = summarize(suite, report["trials"])
    report["status"] = (
        "complete"
        if len(report["trials"]) == planned and not report["stop_reason"]
        else "incomplete"
    )
    report["budget_overshoot_usd"] = max(0, total - max_cost_usd) if live else 0
    return report
