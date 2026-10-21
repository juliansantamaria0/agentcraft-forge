import json

import pytest

from agentcraft_forge.domains.audit import handle
from agentcraft_forge.domains.common import DomainError


def fixture_workspace(root):
    (root / "journal").mkdir()
    (root / "whatsapp").mkdir()
    (root / "open-loops.md").write_text(
        "# Compromisos\n- [ ] [2026-09-01] Preparar informe técnico del cliente Andino\n",
        encoding="utf-8",
    )
    return {"action": "scan", "owner": "Lucía", "reference_date": "2026-10-21"}


def test_audit_tracks_evidence_dates_owner_and_recent_progress(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Avancé informe técnico del cliente Andino\nMe comprometí a entregar contrato mañana\n",
        encoding="utf-8",
    )
    (tmp_path / "whatsapp/chat.txt").write_text(
        "[21/10/2026, 10:00] Otra persona: Me comprometí a entregar mockups mañana\n",
        encoding="utf-8",
    )
    report = handle(tmp_path, request)
    assert report["status"] == "review_required"
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["due_date"] == "2026-10-21"
    assert report["candidates"][0]["source"]["line"] == 2
    assert report["loops"][0]["status"] == "needs_review_progress"
    assert report["loops"][0]["progress_evidence"]


def test_assignments_are_requests_not_confirmed_promises(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.txt").write_text(
        "[20/10/2026, 16:43] Persona B: Compromisos para Lucía:\n1. Excel detallado de gastos\n2. Cronograma con fechas de entrega\nFecha de entrega: 21 de octubre\n",
        encoding="utf-8",
    )
    report = handle(tmp_path, request)
    assert len(report["candidates"]) == 2
    assert all(
        item["kind"] == "request_to_owner" and not item["acceptance_confirmed"]
        for item in report["candidates"]
    )
    assert all(item["due_date"] == "2026-10-21" for item in report["candidates"])


def test_missing_or_undated_sources_never_report_synced(tmp_path):
    report = handle(
        tmp_path, {"action": "scan", "owner": "Lucía", "reference_date": "2026-10-21"}
    )
    assert report["status"] == "incomplete"
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/note.md").write_text(
        "Me comprometí a entregar un informe", encoding="utf-8"
    )
    assert handle(tmp_path, request)["status"] == "incomplete"


def test_old_sources_and_completed_matches_do_not_hide_candidates(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-01-01.md").write_text(
        "Me comprometí a enviar el contrato antiguo", encoding="utf-8"
    )
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Me comprometí a enviar contrato cliente Andino", encoding="utf-8"
    )
    (tmp_path / "open-loops.md").write_text(
        "- [x] [2026-09-01] enviar contrato cliente Andino\n", encoding="utf-8"
    )
    report = handle(tmp_path, request)
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["possible_matches"][0]["completed"] is True
    assert report["skipped_lines_outside_window"] == 1


def test_apply_requires_reviewed_selection_is_atomic_and_replayable(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Me comprometí a llamar al proveedor mañana", encoding="utf-8"
    )
    before = (tmp_path / "open-loops.md").read_text(encoding="utf-8")
    report = handle(tmp_path, request)
    assert (tmp_path / "open-loops.md").read_text(encoding="utf-8") == before
    apply = {
        "action": "apply",
        "scan_id": report["scan_id"],
        "candidate_ids": [report["candidates"][0]["id"]],
        "operation_id": "apply-review-001",
    }
    receipt = handle(tmp_path, apply)
    assert receipt["persisted"] is True
    assert (tmp_path / receipt["backup"]).read_text(encoding="utf-8") == before
    after = (tmp_path / "open-loops.md").read_text(encoding="utf-8")
    assert handle(tmp_path, apply)["replayed"] is True
    assert (tmp_path / "open-loops.md").read_text(encoding="utf-8") == after


def test_source_change_requires_new_audit(tmp_path):
    request = fixture_workspace(tmp_path)
    source = tmp_path / "journal/2026-10-20.md"
    source.write_text("Me comprometí a llamar al proveedor mañana", encoding="utf-8")
    report = handle(tmp_path, request)
    source.write_text("Contenido cambiado", encoding="utf-8")
    with pytest.raises(DomainError, match="cambiaron"):
        handle(
            tmp_path,
            {
                "action": "apply",
                "scan_id": report["scan_id"],
                "candidate_ids": [report["candidates"][0]["id"]],
                "operation_id": "apply-review-002",
            },
        )


def test_json_messages_preserve_source_id(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.json").write_text(
        json.dumps(
            [
                {
                    "id": "wa-message-01",
                    "sender": "Lucía",
                    "date": "2026-10-21",
                    "text": "Tengo que enviar contrato al proveedor mañana",
                }
            ]
        ),
        encoding="utf-8",
    )
    report = handle(tmp_path, request)
    assert report["candidates"][0]["source"]["message_id"] == "wa-message-01"


def test_time_first_whatsapp_and_assignment_does_not_leak_to_next_message(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.txt").write_text(
        "[16:43, 20/10/2026] Persona B: Compromisos para Lucía:\n1. Excel detallado de gastos\nFecha de entrega: 21 de octubre\n[17:00, 20/10/2026] Otra persona: Mis pendientes:\n1. Preparar una presentación\n",
        encoding="utf-8",
    )
    report = handle(tmp_path, request)
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["due_date"] == "2026-10-21"


def test_old_progress_does_not_clear_stagnation(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-01.md").write_text(
        "Avancé informe técnico del cliente Andino", encoding="utf-8"
    )
    report = handle(tmp_path, request)
    assert report["loops"][0]["status"] == "stalled_candidate"


def test_receipt_is_recovered_after_write_but_before_confirmation(
    tmp_path, monkeypatch
):
    from agentcraft_forge.domains import audit

    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Me comprometí a llamar al proveedor mañana", encoding="utf-8"
    )
    report = handle(tmp_path, request)
    apply = {
        "action": "apply",
        "scan_id": report["scan_id"],
        "candidate_ids": [report["candidates"][0]["id"]],
        "operation_id": "apply-interrupted-001",
    }
    original_atomic_text = audit.atomic_text

    def fail_receipt(path, content):
        if path.parent.name == "receipts":
            raise OSError("Simulated failure after canonical write")
        original_atomic_text(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(audit, "atomic_text", fail_receipt)
        with pytest.raises(OSError):
            handle(tmp_path, apply)
    after = (tmp_path / "open-loops.md").read_text(encoding="utf-8")
    receipt = handle(tmp_path, apply)
    assert receipt["persisted"] is True
    assert receipt["replayed"] is True
    assert (tmp_path / "open-loops.md").read_text(encoding="utf-8") == after


def test_interrupted_apply_with_later_manual_edit_stays_uncertain(
    tmp_path, monkeypatch
):
    from agentcraft_forge.domains import audit

    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Me comprometí a llamar al proveedor mañana", encoding="utf-8"
    )
    report = handle(tmp_path, request)
    apply = {
        "action": "apply",
        "scan_id": report["scan_id"],
        "candidate_ids": [report["candidates"][0]["id"]],
        "operation_id": "apply-manual-edit-001",
    }
    original = audit.atomic_text

    def fail_receipt(path, content):
        if path.parent.name == "receipts":
            raise OSError("Simulated interrupted confirmation")
        original(path, content)

    with monkeypatch.context() as patch:
        patch.setattr(audit, "atomic_text", fail_receipt)
        with pytest.raises(OSError):
            handle(tmp_path, apply)
    canonical_path = tmp_path / "open-loops.md"
    after = canonical_path.read_text(encoding="utf-8") + "\nNota manual\n"
    canonical_path.write_text(after, encoding="utf-8")
    with pytest.raises(DomainError) as error:
        handle(tmp_path, apply)
    assert error.value.code == "operation_unconfirmed"
    assert canonical_path.read_text(encoding="utf-8") == after
