import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from agentcraft_forge.domains.audit import due_date, handle
from agentcraft_forge.domains.common import DomainError


def fixture_workspace(root):
    (root / "journal").mkdir()
    (root / "whatsapp").mkdir()
    (root / "open-loops.md").write_text(
        "# Compromisos\n- [ ] [2026-09-01] Preparar informe técnico del cliente Andino\n",
        encoding="utf-8",
    )
    return {"action": "scan", "owner": "Lucía", "reference_date": "2026-10-21"}


def test_relative_workspace_is_normalized_before_audit(tmp_path, monkeypatch):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Me comprometí a llamar al proveedor mañana", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path.parent)
    report = handle(Path(tmp_path.name), request)
    assert report["status"] == "review_required"
    assert report["candidates"][0]["source"]["file"] == "journal/2026-10-20.md"


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


def test_apply_requires_reviewed_selection_is_atomic_and_replayable(
    tmp_path, monkeypatch
):
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
    from agentcraft_forge.domains import audit

    monkeypatch.setattr(audit, "SCAN_VERSION", audit.SCAN_VERSION + 1)
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


def test_json_source_cannot_silently_replace_message_sender(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.json").write_text(
        '[{"id":"wa-01","sender":"Otra persona","sender":"Lucía","date":"2026-10-20","text":"Tengo que enviar contrato"}]',
        encoding="utf-8",
    )
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "invalid_json"
    assert not (tmp_path / ".agentcraft/audit/scans").exists()


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


@pytest.mark.parametrize(
    "message",
    [
        "No he avanzado informe técnico del cliente Andino",
        "Sin avance en informe técnico del cliente Andino",
        "¿Has enviado informe técnico del cliente Andino?",
        "Voy a dejar terminado informe técnico del cliente Andino",
    ],
)
def test_denied_questioned_or_future_progress_does_not_clear_stagnation(
    tmp_path, message
):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(message, encoding="utf-8")
    report = handle(tmp_path, request)
    assert report["loops"][0]["status"] == "stalled_candidate"
    assert report["loops"][0]["progress_evidence"] == []


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


@pytest.mark.parametrize("suffix", ["json", "JSON"])
def test_json_multiline_with_bom_preserves_assignment_and_message_lines(
    tmp_path, suffix
):
    request = fixture_workspace(tmp_path)
    (tmp_path / f"whatsapp/messages.{suffix}").write_text(
        json.dumps(
            [
                {
                    "id": "wa-multiline-001",
                    "sender": "Persona B",
                    "date": "2026-10-20",
                    "text": "Compromisos para Lucía:\n1. Preparar plan de trabajo\n2. Revisar inventario de equipos\nFecha de entrega: 21 de octubre",
                },
                {
                    "id": "wa-multiline-002",
                    "sender": "Otra persona",
                    "date": "2026-10-20",
                    "text": "Mis pendientes:\n1. Preparar otra presentación",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8-sig",
    )
    report = handle(tmp_path, request)
    assert len(report["candidates"]) == 2
    assert [item["source"]["message_line"] for item in report["candidates"]] == [2, 3]
    assert all(
        item["source"]["message_id"] == "wa-multiline-001"
        for item in report["candidates"]
    )
    assert all(item["due_date"] == "2026-10-21" for item in report["candidates"])
    assert all(
        item["deadline_source"]["message_line"] == 4 for item in report["candidates"]
    )


def test_repeated_json_message_ids_are_rejected(tmp_path):
    request = fixture_workspace(tmp_path)
    item = {
        "id": "repeated-001",
        "sender": "Lucía",
        "date": "2026-10-20",
        "text": "Tengo que revisar el contrato",
    }
    (tmp_path / "whatsapp/chat.json").write_text(
        json.dumps([item, item]), encoding="utf-8"
    )
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "invalid_source"


@pytest.mark.parametrize(
    "message",
    [
        "No me comprometí a enviar contrato",
        "No tengo que enviar contrato",
        "Nunca acordé con el proveedor una entrega",
        "¿Tengo que enviar contrato?",
    ],
)
def test_negated_promises_and_questions_are_not_commitments(tmp_path, message):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(message, encoding="utf-8")
    assert handle(tmp_path, request)["candidates"] == []


def test_no_olvidar_remains_a_positive_reminder(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "No olvidar enviar el contrato", encoding="utf-8"
    )
    assert len(handle(tmp_path, request)["candidates"]) == 1


@pytest.mark.parametrize(
    "message,reference,expected",
    [
        ("Entregar pasado mañana", "2026-10-20", "2026-10-22"),
        ("Entregar el próximo viernes", "2026-10-23", "2026-10-30"),
        ("Entregar el 23/10/2026", "2026-10-20", "2026-10-23"),
        ("Entregar mañana, 2026-10-21", "2026-10-20", "2026-10-21"),
        ("Revisar rutina mañanera", "2026-10-20", None),
        ("Entregar el 23 de octubre 2027", "2026-10-20", "2027-10-23"),
        ("Entregar hoy por la mañana", "2026-10-20", "2026-10-20"),
        ("Entregar esta mañana", "2026-10-20", "2026-10-20"),
        ("Entregar mañana por la mañana", "2026-10-20", "2026-10-21"),
    ],
)
def test_deadline_resolution_preserves_explicit_and_relative_meaning(
    message, reference, expected
):
    assert due_date(message, date.fromisoformat(reference)) == expected


@pytest.mark.parametrize(
    "deadline",
    [
        "mañana o el viernes",
        "2026-10-21 o 2026-10-22",
        "31 de febrero de 2027",
        "21 de enero",
    ],
)
def test_uncertain_deadlines_keep_task_with_warning_without_inventing_date(
    tmp_path, deadline
):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        f"Tengo que enviar contrato el {deadline}", encoding="utf-8"
    )
    item = handle(tmp_path, request)["candidates"][0]
    assert item["due_date"] is None
    assert item["date_warnings"]


def test_assignment_deadline_does_not_silently_override_item_date(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.txt").write_text(
        "[20/10/2026, 10:00] Persona B: Compromisos para Lucía:\n1. Enviar contrato el 2026-10-21\nFecha de entrega: 2026-10-23\n",
        encoding="utf-8",
    )
    item = handle(tmp_path, request)["candidates"][0]
    assert item["due_date"] is None
    assert item["date_warnings"]


def test_undated_source_produces_one_diagnostic_per_file(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/note.md").write_text(
        "Pendiente\nOtra nota\nTengo que enviar contrato\n", encoding="utf-8"
    )
    report = handle(tmp_path, request)
    assert report["status"] == "incomplete"
    assert len(report["errors"]) == 1
    assert "3" in report["errors"][0]


def test_sources_changed_during_scan_cannot_publish_report(tmp_path, monkeypatch):
    from agentcraft_forge.domains import audit

    request = fixture_workspace(tmp_path)
    source = tmp_path / "journal/2026-10-20.md"
    source.write_text("Tengo que llamar al proveedor", encoding="utf-8")
    original = audit.source_lines

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        source.write_text("Otro contenido", encoding="utf-8")
        return result

    monkeypatch.setattr(audit, "source_lines", change)
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "sources_changed"
    assert not (tmp_path / ".agentcraft/audit/scans").exists()


def test_report_size_limit_is_shared_with_apply(tmp_path, monkeypatch):
    from agentcraft_forge.domains import audit

    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Tengo que llamar al proveedor", encoding="utf-8"
    )
    monkeypatch.setattr(audit, "MAX_REPORT_BYTES", 100)
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "report_too_large"
    assert not (tmp_path / ".agentcraft/audit/scans").exists()


def test_duplicate_lines_in_one_json_message_have_distinct_candidate_ids(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.json").write_text(
        json.dumps(
            [
                {
                    "id": "wa-duplicate-lines",
                    "sender": "Lucía",
                    "date": "2026-10-20",
                    "text": "\nTengo que llamar al proveedor\nTengo que llamar al proveedor",
                }
            ]
        ),
        encoding="utf-8",
    )
    items = handle(tmp_path, request)["candidates"]
    assert len({item["id"] for item in items}) == 2
    assert [item["source"]["message_line"] for item in items] == [2, 3]


def test_plaintext_bom_does_not_hide_first_sender_or_date(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.txt").write_text(
        "[20/10/2026, 10:00] Lucía: Tengo que llamar al proveedor", encoding="utf-8-sig"
    )
    assert len(handle(tmp_path, request)["candidates"]) == 1


def test_invalid_message_header_date_has_controlled_source_error(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.txt").write_text(
        "[31/02/2026, 10:00] Lucía: Tengo que llamar al proveedor", encoding="utf-8"
    )
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "invalid_source"


def test_invalid_utf8_source_does_not_publish_partial_audit(tmp_path):
    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_bytes(b"\xff\xfeinvalid")
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "invalid_source"
    assert not (tmp_path / ".agentcraft/audit/scans").exists()


def test_content_changed_after_inventory_is_rejected_at_read(tmp_path, monkeypatch):
    from agentcraft_forge.domains import audit

    request = fixture_workspace(tmp_path)
    source = tmp_path / "journal/2026-10-20.md"
    source.write_text("Tengo que llamar al proveedor", encoding="utf-8")
    original = audit.inventory

    def change(root):
        snapshot = original(root)
        source.write_text("Tengo que enviar otro documento", encoding="utf-8")
        return snapshot

    monkeypatch.setattr(audit, "inventory", change)
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "sources_changed"


def test_new_scan_format_cannot_overwrite_previous_version_report(
    tmp_path, monkeypatch
):
    from agentcraft_forge.domains import audit

    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Tengo que llamar al proveedor", encoding="utf-8"
    )
    first = handle(tmp_path, request)
    path = tmp_path / f".agentcraft/audit/scans/{first['scan_id']}.json"
    before = path.read_bytes()
    monkeypatch.setattr(audit, "SCAN_VERSION", audit.SCAN_VERSION + 1)
    second = handle(tmp_path, request)
    assert second["scan_id"] != first["scan_id"]
    assert path.read_bytes() == before
    with pytest.raises(DomainError) as error:
        handle(
            tmp_path,
            {
                "action": "apply",
                "scan_id": first["scan_id"],
                "candidate_ids": [first["candidates"][0]["id"]],
                "operation_id": "apply-old-format-001",
            },
        )
    assert error.value.code == "unsupported_scan"


def test_apply_cannot_grow_canonical_file_beyond_source_limit(tmp_path, monkeypatch):
    from agentcraft_forge.domains import audit

    request = fixture_workspace(tmp_path)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Tengo que llamar al proveedor", encoding="utf-8"
    )
    report = handle(tmp_path, request)
    canonical_path = tmp_path / "open-loops.md"
    original = canonical_path.read_bytes()
    monkeypatch.setattr(audit, "MAX_SOURCE_BYTES", len(original) + 1)
    with pytest.raises(DomainError) as error:
        handle(
            tmp_path,
            {
                "action": "apply",
                "scan_id": report["scan_id"],
                "candidate_ids": [report["candidates"][0]["id"]],
                "operation_id": "apply-size-limit-001",
            },
        )
    assert error.value.code == "oversized_source"
    assert canonical_path.read_bytes() == original
    assert not (tmp_path / ".agentcraft/audit/receipts").exists()


@pytest.mark.parametrize(
    "header", ["[20/10/26, 11:00] Otra persona:", "20/10/2026, 11:00 - Otra persona:"]
)
def test_unsupported_header_cannot_inherit_previous_sender(tmp_path, header):
    request = fixture_workspace(tmp_path)
    (tmp_path / "whatsapp/chat.txt").write_text(
        f"[20/10/2026, 10:00] Lucía: Hola\n{header} Tengo que revisar contrato\n",
        encoding="utf-8",
    )
    with pytest.raises(DomainError) as error:
        handle(tmp_path, request)
    assert error.value.code == "invalid_source"
    assert not (tmp_path / ".agentcraft/audit/scans").exists()


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_backup_preserves_windows_line_endings_and_bom_byte_for_byte(
    tmp_path, encoding
):
    request = fixture_workspace(tmp_path)
    canonical_path = tmp_path / "open-loops.md"
    original = "# Compromisos\r\n- [ ] [2026-09-01] Preparar informe técnico del cliente Andino\r\n".encode(
        encoding
    )
    canonical_path.write_bytes(original)
    (tmp_path / "journal/2026-10-20.md").write_text(
        "Tengo que llamar al proveedor", encoding="utf-8"
    )
    report = handle(tmp_path, request)
    receipt = handle(
        tmp_path,
        {
            "action": "apply",
            "scan_id": report["scan_id"],
            "candidate_ids": [report["candidates"][0]["id"]],
            "operation_id": "apply-windows-backup-001",
        },
    )
    backup = (tmp_path / receipt["backup"]).read_bytes()
    assert backup == original
    assert hashlib.sha256(backup).hexdigest() == receipt["before_sha256"]
