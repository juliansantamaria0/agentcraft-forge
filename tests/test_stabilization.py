import json
import subprocess
import sys
from datetime import date

import pytest

from agentcraft_forge.domains.audit import handle
from agentcraft_forge.domains.common import DomainError
from agentcraft_forge.domains.expenses import propose
from agentcraft_forge.generator import generate, render
from agentcraft_forge.planner import design
from agentcraft_forge.schema import Kind


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Gasté 15k en transporte hace tres días", "2026-10-19"),
        ("Gasté 15k en transporte hace 3 días", "2026-10-19"),
        ("Gasté 15k en transporte el 20 de octubre de 2026", "2026-10-20"),
        ("El 20 de OCTUBRE del 2026 gasté 15k en café", "2026-10-20"),
    ],
)
def test_expense_dates_are_preserved(message, expected):
    result = propose(message, date(2026, 10, 22))
    assert result["status"] == "proposal"
    item = result["request"]["expenses"][0]
    assert item["expense_date"] == expected
    assert item["amount"] == 15000


@pytest.mark.parametrize(
    "period",
    [
        "el lunes",
        "anoche",
        "hace varios días",
        "la semana pasada",
        "en septiembre de 2026",
        "el 20 de octubre",
        "hace 5000 días",
        "hace tres días y ayer",
        "el 31 de febrero de 2026",
        "el día 20",
        "hace " + "9" * 4500 + " días",
    ],
)
def test_unresolved_expense_dates_never_default_to_today(period):
    result = propose(f"Gasté 15k en transporte {period}", date(2026, 10, 22))
    assert result["status"] == "needs_clarification"
    assert result["persisted"] is False
    assert "request" not in result


def test_audit_duplicates_are_visible_and_cannot_be_applied_together(tmp_path):
    (tmp_path / "open-loops.md").write_text("# Compromisos\n", encoding="utf-8")
    (tmp_path / "journal").mkdir()
    for suffix in ("a", "b"):
        (tmp_path / "journal" / f"2026-10-22-{suffix}.md").write_text(
            "Tengo que enviar el informe comercial mañana.", encoding="utf-8"
        )
    report = handle(
        tmp_path, {"action": "scan", "owner": "Persona", "reference_date": "2026-10-22"}
    )
    items = report["candidates"]
    assert len(items) == 2
    assert items[0]["possible_candidate_matches"][0]["candidate_id"] == items[1]["id"]
    assert items[1]["possible_candidate_matches"][0]["candidate_id"] == items[0]["id"]
    before = (tmp_path / "open-loops.md").read_bytes()
    request = {
        "action": "apply",
        "scan_id": report["scan_id"],
        "candidate_ids": [c["id"] for c in items],
        "operation_id": "duplicate-review-001",
    }
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "possible_duplicate"
    assert (tmp_path / "open-loops.md").read_bytes() == before
    request["candidate_ids"] = [items[0]["id"]]
    assert handle(tmp_path, request)["count"] == 1
    assert handle(tmp_path, request)["replayed"] is True


def test_recurring_tasks_with_distinct_deadlines_remain_separate(tmp_path):
    (tmp_path / "open-loops.md").write_text("# Compromisos\n", encoding="utf-8")
    (tmp_path / "journal").mkdir()
    (tmp_path / "journal/2026-10-22.md").write_text(
        "Tengo que enviar el informe comercial hoy.\nTengo que enviar el informe comercial mañana.",
        encoding="utf-8",
    )
    report = handle(
        tmp_path, {"action": "scan", "owner": "Persona", "reference_date": "2026-10-22"}
    )
    assert all(not c["possible_candidate_matches"] for c in report["candidates"])
    result = handle(
        tmp_path,
        {
            "action": "apply",
            "scan_id": report["scan_id"],
            "candidate_ids": [c["id"] for c in report["candidates"]],
            "operation_id": "recurring-review-001",
        },
    )
    assert result["count"] == 2


@pytest.mark.parametrize("kind", list(Kind))
def test_docker_only_copies_code_and_uses_writable_workspace(kind):
    resources = render(
        design("docker-review", "Revisar contratos con datos sintéticos", kind)
    )
    dockerfile = resources["Dockerfile"]
    assert "COPY --chown=app:app . ." not in dockerfile
    assert "COPY agentcraft.json /app/agentcraft.json" in dockerfile
    assert 'ENTRYPOINT ["agent", "--root", "/workspace"]' in dockerfile
    assert "chown app:app /workspace" in dockerfile
    patterns = resources[".dockerignore"].splitlines()
    assert patterns[0] == "*"
    assert "!src/**" in patterns
    assert not any(
        p.startswith("!")
        and any(
            name in p
            for name in ("journal", "whatsapp", "open-loops", ".data", ".agentcraft")
        )
        for p in patterns
    )
    assert json.loads(resources["agentcraft.json"])["name"] == "docker-review"


@pytest.mark.parametrize("kind", list(Kind))
def test_generated_project_passes_its_ci_lint(tmp_path, kind):
    target = generate(
        design("generated-quality", "Comprobar calidad del agente generado", kind),
        tmp_path,
    )
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", str(target)],
        cwd=target,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
