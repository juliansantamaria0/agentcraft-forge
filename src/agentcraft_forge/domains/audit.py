"""Auditor local: evidencia, identidad declarada, revisión y aplicación verificable."""

import hashlib
import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

from agentcraft_forge.domains.common import (
    DomainError,
    atomic_text,
    canonical,
    digest,
    fields,
    integer,
    iso_date,
    normalize,
    now,
    operation_id,
    safe_path,
    text,
)

PROMISE = re.compile(
    r"\b(?:qued[eé] de|me compromet[ií] a|tengo que|acord[eé] con|debo|pendiente de|no olvidar)\b",
    re.IGNORECASE,
)
PROGRESS = re.compile(
    r"\b(?:avance|avancé|avanzado|actualicé|actualizado|envié|enviado|entregué|entregado|terminé|terminado|completado|trabajé)\b",
    re.IGNORECASE,
)
WHATSAPP = re.compile(r"^\[(\d{1,2})/(\d{1,2})/(\d{4}),?\s+[^\]]+\]\s*([^:]+):\s*(.*)$")
WHATSAPP_TIME_FIRST = re.compile(
    r"^\[\d{1,2}:\d{2}(?::\d{2})?,\s*(\d{1,2})/(\d{1,2})/(\d{4})\]\s*([^:]+):\s*(.*)$"
)
STOP = {
    "para",
    "con",
    "del",
    "las",
    "los",
    "que",
    "una",
    "por",
    "debo",
    "enviar",
    "revisar",
    "tengo",
    "pendiente",
    "comprometi",
    "quede",
    "actualizado",
    "avance",
    "avanzado",
    "envie",
    "entregado",
    "completado",
    "trabaje",
}
WEEKDAYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
MONTHS = (
    "",
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b[a-z0-9]{3,}\b", normalize(value))
        if token not in STOP
    }


def similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    common = a & b
    if len(common) < 3:
        return 1.0 if a == b and len(a) >= 2 else 0.0
    return len(common) / len(a | b)


def due_date(value: str, reference: date) -> str | None:
    lower = normalize(value)
    explicit = re.search(r"\b\d{4}-\d{2}-\d{2}\b", lower)
    if explicit:
        return iso_date(explicit.group())
    if "manana" in lower:
        return (reference + timedelta(days=1)).isoformat()
    if "hoy" in lower:
        return reference.isoformat()
    for index, day in enumerate(WEEKDAYS):
        if re.search(rf"\b{day}\b", lower):
            return (
                reference + timedelta(days=(index - reference.weekday()) % 7)
            ).isoformat()
    spanish = re.search(
        r"\b(\d{1,2}) de (" + "|".join(MONTHS[1:]) + r")(?: de (\d{4}))?\b", lower
    )
    if spanish:
        try:
            return date(
                int(spanish[3] or reference.year),
                MONTHS.index(spanish[2]),
                int(spanish[1]),
            ).isoformat()
        except ValueError as exc:
            raise DomainError(
                "invalid_date", "Una fuente contiene un vencimiento inválido."
            ) from exc
    return None


def inventory(root: Path) -> dict[str, str]:
    result = {}
    canonical_file = safe_path(root, "open-loops.md")
    if canonical_file.is_file():
        if canonical_file.stat().st_size > 1_000_000:
            raise DomainError(
                "oversized_source", "El registro de compromisos supera 1 MB."
            )
        result["open-loops.md"] = file_hash(canonical_file)
    for name in ("journal", "whatsapp"):
        directory = safe_path(root, name)
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            relative = path.relative_to(root).as_posix()
            safe_path(root, relative)
            if path.is_file() and path.suffix.lower() in {".md", ".txt", ".json"}:
                if path.stat().st_size > 1_000_000:
                    raise DomainError("oversized_source", "Una fuente supera 1 MB.")
                result[relative] = file_hash(path)
                if len(result) > 200:
                    raise DomainError(
                        "too_many_sources", "Máximo 200 fuentes por auditoría."
                    )
    return result


def source_lines(root: Path, relative: str, owner: str) -> list[dict]:
    content = safe_path(root, relative).read_text(encoding="utf-8")
    if relative.endswith(".json"):
        messages = json.loads(content)
        if not isinstance(messages, list) or len(messages) > 5000:
            raise DomainError(
                "invalid_source", "El JSON de WhatsApp debe ser una lista de mensajes."
            )
        result = []
        for index, item in enumerate(messages, 1):
            fields(item, {"id", "sender", "date", "text"})
            result.append(
                {
                    "line": index,
                    "text": text(item["text"], 6000),
                    "sender": text(item["sender"], 100),
                    "date": iso_date(item["date"]),
                    "message_id": text(item["id"], 128),
                    "message_start": True,
                }
            )
        return result
    filename_date = re.search(r"\d{4}-\d{2}-\d{2}", Path(relative).name)
    current = {
        "sender": owner if relative.startswith("journal/") else None,
        "date": iso_date(filename_date.group()) if filename_date else None,
        "message_id": None,
    }
    result = []
    for index, line in enumerate(content.splitlines(), 1):
        match = WHATSAPP.match(line) or WHATSAPP_TIME_FIRST.match(line)
        if match:
            current = {
                "sender": match[4].strip(),
                "date": date(int(match[3]), int(match[2]), int(match[1])).isoformat(),
                "message_id": str(index),
            }
            line = match[5]
        result.append(
            {
                **current,
                "line": index,
                "text": line.strip(),
                "message_start": bool(match),
            }
        )
    return result


def parse_loops(root: Path, reference: date, stale_days: int) -> list[dict]:
    path = safe_path(root, "open-loops.md")
    if not path.is_file():
        return []
    loops = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        match = re.match(r"^\s*[-*]\s+\[([ xX])\]\s*(.+)$", line)
        if not match:
            continue
        dates = re.findall(r"\[(\d{4}-\d{2}-\d{2})\]", match[2])
        updated = re.search(
            r"\[(?:updated|actualizado):\s*(\d{4}-\d{2}-\d{2})\]",
            match[2],
            re.IGNORECASE,
        )
        effective = (
            iso_date(updated[1]) if updated else iso_date(dates[0]) if dates else None
        )
        description = re.sub(r"\[[^\]]+\]|#\S+", " ", match[2])
        description = " ".join(description.split())
        age = (reference - date.fromisoformat(effective)).days if effective else None
        loops.append(
            {
                "id": digest({"line": line_number, "text": line})[:20],
                "line": line_number,
                "text": description,
                "completed": match[1].lower() == "x",
                "last_updated": effective,
                "days_without_update": age,
                "stalled_candidate": match[1] == " "
                and age is not None
                and age >= stale_days,
                "progress_evidence": [],
            }
        )
    return loops


def scan(root: Path, request: dict) -> dict:
    fields(
        request, {"action", "owner", "reference_date"}, {"stale_days", "recent_days"}
    )
    owner = text(request["owner"], 100)
    reference = date.fromisoformat(iso_date(request["reference_date"]))
    stale_days = integer(request.get("stale_days", 14), 1, 3650)
    recent_days = integer(request.get("recent_days", 30), 1, 3650)
    sources = inventory(root)
    errors = []
    if "open-loops.md" not in sources:
        errors.append("Falta open-loops.md; no puede comprobarse el registro canónico.")
    inputs = [name for name in sources if name != "open-loops.md"]
    if not inputs:
        errors.append("No hay fuentes de journal o WhatsApp para revisar.")
    loops = parse_loops(root, reference, stale_days)
    candidates = []
    skipped_old = 0
    ignored_other_senders = 0
    for relative in inputs:
        assignment_owner = None
        assignment_candidates = []
        for entry in source_lines(root, relative, owner):
            body = entry["text"]
            if entry["message_start"]:
                assignment_owner = None
                assignment_candidates = []
            if not entry["date"]:
                if body:
                    errors.append(
                        f"Fuente sin fecha comprobable: {relative}:{entry['line']}."
                    )
                continue
            source_date = date.fromisoformat(entry["date"])
            if source_date > reference or source_date < reference - timedelta(
                days=max(recent_days, stale_days)
            ):
                skipped_old += 1
                continue
            assignment = re.search(r"compromisos para\s+([^:]+)", body, re.IGNORECASE)
            if assignment:
                assignment_owner = assignment[1].strip()
                assignment_candidates = []
                continue
            deadline = re.search(r"fecha de entrega\s*:\s*(.+)", body, re.IGNORECASE)
            if deadline and assignment_owner:
                due = due_date(deadline[1], source_date)
                for candidate in assignment_candidates:
                    candidate["due_date"] = due
                continue
            is_assignment = assignment_owner is not None and bool(
                re.match(r"^(?:\d+[.)]|[-*])\s+", body)
            )
            responsible = assignment_owner if is_assignment else entry["sender"]
            if responsible is None or normalize(responsible) != normalize(owner):
                ignored_other_senders += 1
                continue
            evidence = {
                "file": relative,
                "line": entry["line"],
                "source_sha256": sources[relative],
                "message_id": entry["message_id"],
                "sender": entry["sender"],
                "source_date": entry["date"],
                "excerpt": body[:1500],
            }
            if PROGRESS.search(body):
                for loop in loops:
                    if (
                        (reference - source_date).days < stale_days
                        and not loop["completed"]
                        and similarity(body, loop["text"]) >= 0.45
                    ):
                        loop["progress_evidence"].append(evidence)
                continue
            if (reference - source_date).days > recent_days:
                skipped_old += 1
                continue
            if not is_assignment and not PROMISE.search(body):
                continue
            task = re.sub(r"^(?:\d+[.)]|[-*])\s+", "", body).strip()
            task = " ".join(task.split())[:1000]
            candidate = {
                "id": digest(
                    {
                        "file": relative,
                        "line": entry["line"],
                        "text": task,
                        "owner": owner,
                    }
                )[:20],
                "text": task,
                "owner": owner,
                "kind": "request_to_owner" if is_assignment else "commitment_candidate",
                "acceptance_confirmed": False,
                "due_date": due_date(task, source_date),
                "source": evidence,
                "possible_matches": [
                    {
                        "loop_id": loop["id"],
                        "completed": loop["completed"],
                        "score": round(similarity(task, loop["text"]), 3),
                    }
                    for loop in loops
                    if similarity(task, loop["text"]) >= 0.45
                ],
            }
            candidates.append(candidate)
            if is_assignment:
                assignment_candidates.append(candidate)
    for loop in loops:
        loop["status"] = (
            "completed"
            if loop["completed"]
            else (
                "needs_review_progress"
                if loop["progress_evidence"]
                else (
                    "stalled_candidate"
                    if loop["stalled_candidate"]
                    else "unknown_date" if loop["last_updated"] is None else "recent"
                )
            )
        )
    # El ID vincula la solicitud normalizada a un snapshot; no se ocultan coincidencias.
    identity = {
        "owner": owner,
        "reference_date": reference.isoformat(),
        "stale_days": stale_days,
        "recent_days": recent_days,
        "sources": sources,
    }
    scan_id = digest(identity)
    report = {
        "status": "incomplete" if errors else "review_required",
        "scan_id": scan_id,
        "created_at": now(),
        "owner": owner,
        "reference_date": reference.isoformat(),
        "source_snapshot": sources,
        "errors": errors,
        "skipped_lines_outside_window": skipped_old,
        "ignored_other_senders": ignored_other_senders,
        "loops": loops,
        "candidates": candidates,
        "persisted": False,
        "notes": [
            "Detección heurística: ausencia de coincidencias no demuestra ausencia de compromisos.",
            "La identidad es declarada; no sustituye autenticación ni autorización.",
            "Cada candidato requiere revisión; una petición de un tercero no confirma aceptación.",
        ],
    }
    target = safe_path(root, f".agentcraft/audit/scans/{scan_id}.json")
    atomic_text(target, canonical(report))
    return report


def apply(root: Path, request: dict) -> dict:
    fields(request, {"action", "scan_id", "candidate_ids", "operation_id"})
    scan_id = text(request["scan_id"], 64)
    if not re.fullmatch(r"[a-f0-9]{64}", scan_id):
        raise DomainError("invalid_scan", "Identificador de auditoría no válido.")
    identifier = operation_id(request["operation_id"])
    ids = request["candidate_ids"]
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 50
        or any(not isinstance(value, str) for value in ids)
        or len(set(ids)) != len(ids)
    ):
        raise DomainError(
            "invalid_selection", "Seleccione de 1 a 50 candidatos sin duplicados."
        )
    request_hash = digest(request)
    receipt_path = safe_path(
        root, f".agentcraft/audit/receipts/{digest(identifier)}.json"
    )
    pending_path = safe_path(
        root, f".agentcraft/audit/pending/{digest(identifier)}.json"
    )
    canonical_path = safe_path(root, "open-loops.md")
    lock_path = safe_path(root, ".agentcraft/audit/apply.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise DomainError(
            "audit_busy",
            "Otra aplicación está activa. Revise el lock si un proceso anterior se interrumpió.",
        ) from exc
    try:
        os.close(descriptor)
        for state_path in (receipt_path, pending_path):
            if state_path.is_file():
                previous = json.loads(state_path.read_text(encoding="utf-8"))
                if previous["request_hash"] != request_hash:
                    raise DomainError(
                        "operation_conflict",
                        "El identificador ya corresponde a otra solicitud.",
                    )
                if state_path == receipt_path or (
                    canonical_path.is_file()
                    and file_hash(canonical_path) == previous["after_sha256"]
                ):
                    if state_path == pending_path:
                        atomic_text(receipt_path, canonical(previous))
                    return {**previous, "replayed": True}
                if state_path == pending_path and (
                    not canonical_path.is_file()
                    or file_hash(canonical_path) != previous["before_sha256"]
                ):
                    raise DomainError(
                        "operation_unconfirmed",
                        "Hay una operación pendiente y el registro cambió; revise el comprobante y el backup antes de continuar.",
                    )
        report_path = safe_path(root, f".agentcraft/audit/scans/{scan_id}.json")
        if not report_path.is_file() or report_path.stat().st_size > 2_000_000:
            raise DomainError(
                "invalid_scan", "No existe un informe local de tamaño válido."
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report["status"] != "review_required":
            raise DomainError(
                "incomplete_scan", "No se puede aplicar una auditoría incompleta."
            )
        if inventory(root) != report["source_snapshot"]:
            raise DomainError(
                "stale_scan",
                "Las fuentes o el registro cambiaron; vuelva a auditar y revisar.",
            )
        by_id = {candidate["id"]: candidate for candidate in report["candidates"]}
        if any(value not in by_id for value in ids):
            raise DomainError(
                "invalid_selection", "Algún candidato no pertenece a esta auditoría."
            )
        selected = [by_id[value] for value in ids]
        if any(candidate["possible_matches"] for candidate in selected):
            raise DomainError(
                "possible_duplicate",
                "Hay coincidencias con tareas existentes; resuélvalas antes de aplicar.",
            )
        original = canonical_path.read_text(encoding="utf-8")
        entries = []
        for candidate in selected:
            due = f" [due: {candidate['due_date']}]" if candidate["due_date"] else ""
            entries.append(
                f"- [ ] [{report['reference_date']}]{due} [agentcraft-id: {candidate['id']}] {candidate['text']}"
            )
        updated = (
            original.rstrip()
            + "\n\n## Compromisos revisados con AgentCraft\n"
            + "\n".join(entries)
            + "\n"
        )
        backup = safe_path(root, f".agentcraft/audit/backups/{digest(identifier)}.md")
        atomic_text(backup, original)
        receipt = {
            "status": "committed",
            "persisted": True,
            "action": "apply",
            "operation_id": identifier,
            "request_hash": request_hash,
            "scan_id": scan_id,
            "candidate_ids": ids,
            "count": len(ids),
            "before_sha256": file_hash(canonical_path),
            "after_sha256": hashlib.sha256(updated.encode()).hexdigest(),
            "backup": backup.relative_to(root).as_posix(),
            "created_at": now(),
            "replayed": False,
        }
        atomic_text(pending_path, canonical(receipt))
        atomic_text(canonical_path, updated)
        if file_hash(canonical_path) != receipt["after_sha256"]:
            raise DomainError(
                "verification_failed", "No pudo verificarse el registro actualizado."
            )
        atomic_text(receipt_path, canonical(receipt))
        return receipt
    finally:
        lock_path.unlink(missing_ok=True)


def handle(root: Path, request: object) -> dict:
    if not isinstance(request, dict):
        raise DomainError("invalid_request", "Se requiere un objeto JSON.")
    if request.get("action") == "scan":
        return scan(root, request)
    if request.get("action") == "apply":
        return apply(root, request)
    raise DomainError(
        "unknown_action", "El auditor admite scan y apply con selección explícita."
    )


def propose(message: str, reference_date: date | None = None) -> dict:
    text(message, 6000)
    return {
        "status": "needs_clarification",
        "persisted": False,
        "model_invoked": False,
        "reason": "Indique responsable y fecha de referencia en una solicitud scan; una petición de chat no aplica cambios automáticamente.",
        "example_request": {
            "action": "scan",
            "owner": "NOMBRE_DEL_RESPONSABLE",
            "reference_date": (reference_date or date.today()).isoformat(),
            "stale_days": 14,
            "recent_days": 30,
        },
    }
