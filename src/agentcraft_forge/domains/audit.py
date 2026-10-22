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
    parse_json,
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
UNCERTAIN_PROGRESS = re.compile(
    r"\b(?:no|nunca|tampoco|sin|voy a|vamos a|tengo que|debo|pendiente de)\b|[¿?]",
    re.IGNORECASE,
)
NEGATED_PROMISE = re.compile(
    r"\b(?:no|nunca|tampoco)\s+(?:me\s+)?(?:comprometi|tengo que|quede de|acorde con|debo)\b|[¿?]"
)
SCAN_VERSION = 3
MAX_REPORT_BYTES = 2_000_000
MAX_SOURCE_BYTES = 1_000_000
MAX_CANDIDATES = 500
WHATSAPP = re.compile(r"^\[(\d{1,2})/(\d{1,2})/(\d{4}),?\s+[^\]]+\]\s*([^:]+):\s*(.*)$")
WHATSAPP_TIME_FIRST = re.compile(
    r"^\[\d{1,2}:\d{2}(?::\d{2})?,\s*(\d{1,2})/(\d{1,2})/(\d{4})\]\s*([^:]+):\s*(.*)$"
)
UNSUPPORTED_HEADER = re.compile(
    r"^\[[^\]]*\d{1,2}:\d{2}[^\]]*\]\s*[^:]+:|^\d{1,4}[/-]\d{1,2}[/-]\d{2,4},?\s+\d{1,2}:\d{2}\s+-\s+[^:]+:"
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


def candidate_similarity(left: dict, right: dict) -> float:
    """Una coincidencia solicita revisión; no borra fuentes ni fusiona tareas."""
    if normalize(left["owner"]) != normalize(right["owner"]):
        return 0.0
    if left["due_date"] and right["due_date"] and left["due_date"] != right["due_date"]:
        return 0.0
    return similarity(left["text"], right["text"])


def due_date(value: str, reference: date) -> str | None:
    lower = normalize(value)
    dates = set()
    try:
        dates.update(
            date.fromisoformat(token)
            for token in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", lower)
        )
        for day_part, month_part, year in re.findall(
            r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", lower
        ):
            dates.add(date(int(year), int(month_part), int(day_part)))
        if re.search(r"\besta manana\b", lower):
            dates.add(reference)
        lower = re.sub(r"\b(?:esta|por la|de la) manana\b", " ", lower)
        if re.search(r"\bpasado manana\b", lower):
            dates.add(reference + timedelta(days=2))
            lower = re.sub(r"\bpasado manana\b", " ", lower)
        if re.search(r"\bmanana\b", lower):
            dates.add(reference + timedelta(days=1))
        if re.search(r"\bhoy\b", lower):
            dates.add(reference)
        for index, day in enumerate(WEEKDAYS):
            if re.search(rf"\b{day}\b", lower):
                offset = (index - reference.weekday()) % 7
                if offset == 0 and re.search(rf"\bproximo {day}\b", lower):
                    offset = 7
                dates.add(reference + timedelta(days=offset))
        for spanish in re.finditer(
            r"\b(\d{1,2}) de ("
            + "|".join(MONTHS[1:])
            + r")(?:\s+(?:del?\s+)?(\d{4}))?\b",
            lower,
        ):
            resolved = date(
                int(spanish[3] or reference.year),
                MONTHS.index(spanish[2]),
                int(spanish[1]),
            )
            if not spanish[3] and resolved < reference:
                raise DomainError(
                    "ambiguous_deadline",
                    "Indique el año del vencimiento; la fecha sin año quedaría antes de la fuente.",
                )
            dates.add(resolved)
    except DomainError:
        raise
    except (ValueError, OverflowError) as exc:
        raise DomainError(
            "invalid_date", "Una fuente contiene un vencimiento inválido."
        ) from exc
    if len(dates) > 1:
        raise DomainError(
            "ambiguous_deadline",
            "Hay varias fechas distintas; revise cuál corresponde al vencimiento.",
        )
    return next(iter(dates)).isoformat() if dates else None


def resolve_deadline(value: str, reference: date) -> tuple[str | None, list[str]]:
    try:
        return due_date(value, reference), []
    except DomainError as exc:
        return None, [str(exc)]


def inventory(root: Path) -> dict[str, str]:
    root = root.resolve(strict=True)
    result = {}
    canonical_file = safe_path(root, "open-loops.md")
    if canonical_file.is_file():
        if canonical_file.stat().st_size > MAX_SOURCE_BYTES:
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
                if path.stat().st_size > MAX_SOURCE_BYTES:
                    raise DomainError("oversized_source", "Una fuente supera 1 MB.")
                result[relative] = file_hash(path)
                if len(result) > 200:
                    raise DomainError(
                        "too_many_sources", "Máximo 200 fuentes por auditoría."
                    )
    return result


def read_source(root: Path, relative: str, expected_hash: str | None = None) -> str:
    with safe_path(root, relative).open("rb") as stream:
        content_bytes = stream.read(MAX_SOURCE_BYTES + 1)
    if len(content_bytes) > MAX_SOURCE_BYTES:
        raise DomainError("oversized_source", "Una fuente supera 1 MB.")
    if (
        expected_hash is not None
        and hashlib.sha256(content_bytes).hexdigest() != expected_hash
    ):
        raise DomainError(
            "sources_changed", "Una fuente cambió durante la lectura; vuelva a auditar."
        )
    try:
        return content_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise DomainError(
            "invalid_source", "Las fuentes deben ser texto UTF-8 válido."
        ) from exc


def source_lines(
    root: Path, relative: str, owner: str, expected_hash: str | None = None
) -> list[dict]:
    content = read_source(root, relative, expected_hash)
    if Path(relative).suffix.lower() == ".json":
        messages = parse_json(content)
        if not isinstance(messages, list) or len(messages) > 5000:
            raise DomainError(
                "invalid_source", "El JSON de WhatsApp debe ser una lista de mensajes."
            )
        result = []
        seen_ids = set()
        for index, item in enumerate(messages, 1):
            fields(item, {"id", "sender", "date", "text"})
            identifier = text(item["id"], 128)
            if identifier in seen_ids:
                raise DomainError(
                    "invalid_source",
                    "El export JSON contiene identificadores de mensaje repetidos.",
                )
            seen_ids.add(identifier)
            metadata = {
                "line": index,
                "sender": text(item["sender"], 100),
                "date": iso_date(item["date"]),
                "message_id": identifier,
            }
            text(item["text"], 6000)
            for message_line, body in enumerate(item["text"].splitlines(), 1):
                result.append(
                    {
                        **metadata,
                        "text": body.strip(),
                        "message_line": message_line,
                        "message_start": message_line == 1,
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
        if (
            not match
            and relative.startswith("whatsapp/")
            and UNSUPPORTED_HEADER.match(line)
        ):
            raise DomainError(
                "invalid_source",
                "Encabezado de WhatsApp no compatible; use los formatos con año de cuatro cifras documentados.",
            )
        if match:
            try:
                message_date = date(
                    int(match[3]), int(match[2]), int(match[1])
                ).isoformat()
            except ValueError as exc:
                raise DomainError(
                    "invalid_source",
                    "El export contiene una fecha de mensaje inválida.",
                ) from exc
            current = {
                "sender": match[4].strip(),
                "date": message_date,
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


def source_evidence(relative: str, entry: dict, source_hash: str) -> dict:
    return {
        "file": relative,
        "line": entry["line"],
        "source_sha256": source_hash,
        "message_id": entry["message_id"],
        "message_line": entry.get("message_line"),
        "sender": entry["sender"],
        "source_date": entry["date"],
        "excerpt": entry["text"][:1500],
    }


def parse_loops(
    root: Path, reference: date, stale_days: int, expected_hash: str | None = None
) -> list[dict]:
    path = safe_path(root, "open-loops.md")
    if not path.is_file():
        return []
    loops = []
    for line_number, line in enumerate(
        read_source(root, "open-loops.md", expected_hash).splitlines(), 1
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
    loops = parse_loops(root, reference, stale_days, sources.get("open-loops.md"))
    candidates = []
    skipped_old = 0
    ignored_other_senders = 0
    for relative in inputs:
        assignment_owner = None
        assignment_candidates = []
        undated_count = 0
        for entry in source_lines(root, relative, owner, sources[relative]):
            body = entry["text"]
            if entry["message_start"]:
                assignment_owner = None
                assignment_candidates = []
            if not entry["date"]:
                if body:
                    undated_count += 1
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
                due, warnings = resolve_deadline(deadline[1], source_date)
                for candidate in assignment_candidates:
                    candidate["deadline_source"] = source_evidence(
                        relative, entry, sources[relative]
                    )
                    if (
                        warnings
                        or candidate["date_warnings"]
                        or (
                            due
                            and candidate["due_date"]
                            and due != candidate["due_date"]
                        )
                    ):
                        candidate["due_date"] = None
                        candidate["date_warnings"] = list(
                            dict.fromkeys(
                                [
                                    *candidate["date_warnings"],
                                    *warnings,
                                    "Revise las fechas del encargo y de la línea de entrega.",
                                ]
                            )
                        )
                    elif due:
                        candidate["due_date"] = due
                continue
            is_assignment = assignment_owner is not None and bool(
                re.match(r"^(?:\d+[.)]|[-*])\s+", body)
            )
            responsible = assignment_owner if is_assignment else entry["sender"]
            if responsible is None or normalize(responsible) != normalize(owner):
                ignored_other_senders += 1
                continue
            evidence = source_evidence(relative, entry, sources[relative])
            if PROGRESS.search(body) and not UNCERTAIN_PROGRESS.search(normalize(body)):
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
            if not is_assignment and NEGATED_PROMISE.search(normalize(body)):
                continue
            task = re.sub(r"^(?:\d+[.)]|[-*])\s+", "", body).strip()
            task = " ".join(task.split())[:1000]
            due, warnings = resolve_deadline(task, source_date)
            candidate = {
                "id": digest(
                    {
                        "file": relative,
                        "line": entry["line"],
                        "message_line": entry.get("message_line"),
                        "text": task,
                        "owner": owner,
                    }
                )[:20],
                "text": task,
                "owner": owner,
                "kind": "request_to_owner" if is_assignment else "commitment_candidate",
                "acceptance_confirmed": False,
                "due_date": due,
                "date_warnings": warnings,
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
            if len(candidates) > MAX_CANDIDATES:
                raise DomainError(
                    "too_many_candidates",
                    "Máximo 500 candidatos; divida las fuentes o reduzca la ventana.",
                )
            if is_assignment:
                assignment_candidates.append(candidate)
        if undated_count:
            errors.append(
                f"Fuente sin fecha comprobable: {relative} ({undated_count} líneas sin fecha)."
            )
    for candidate in candidates:
        candidate["possible_candidate_matches"] = []
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            score = candidate_similarity(left, right)
            if score >= 0.75:
                left["possible_candidate_matches"].append(
                    {"candidate_id": right["id"], "score": round(score, 3)}
                )
                right["possible_candidate_matches"].append(
                    {"candidate_id": left["id"], "score": round(score, 3)}
                )
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
        "scan_version": SCAN_VERSION,
        "owner": owner,
        "reference_date": reference.isoformat(),
        "stale_days": stale_days,
        "recent_days": recent_days,
        "sources": sources,
    }
    scan_id = digest(identity)
    report = {
        "scan_version": SCAN_VERSION,
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
    content = canonical(report)
    if len(content.encode("utf-8")) > MAX_REPORT_BYTES:
        raise DomainError(
            "report_too_large",
            "El informe supera 2 MB; reduzca la ventana o divida las fuentes antes de auditar.",
        )
    if inventory(root) != sources:
        raise DomainError(
            "sources_changed",
            "Las fuentes cambiaron durante la auditoría; vuelva a auditar.",
        )
    target = safe_path(root, f".agentcraft/audit/scans/{scan_id}.json")
    atomic_text(target, content)
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
        if not report_path.is_file() or report_path.stat().st_size > MAX_REPORT_BYTES:
            raise DomainError(
                "invalid_scan", "No existe un informe local de tamaño válido."
            )
        report = parse_json(report_path.read_text(encoding="utf-8-sig"))
        if (
            not isinstance(report, dict)
            or type(report.get("scan_version")) is not int
            or report["scan_version"] != SCAN_VERSION
        ):
            raise DomainError(
                "unsupported_scan",
                "El informe pertenece a otro formato de auditoría; vuelva a escanear y revisar.",
            )
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
        if any(
            candidate_similarity(left, right) >= 0.75
            for index, left in enumerate(selected)
            for right in selected[index + 1 :]
        ):
            raise DomainError(
                "possible_duplicate",
                "La selección contiene candidatos equivalentes; seleccione uno conservando sus fuentes o aclare sus fechas.",
            )
        if any(candidate["possible_matches"] for candidate in selected):
            raise DomainError(
                "possible_duplicate",
                "Hay coincidencias con tareas existentes; resuélvalas antes de aplicar.",
            )
        original_bytes = canonical_path.read_bytes()
        before_hash = hashlib.sha256(original_bytes).hexdigest()
        if before_hash != report["source_snapshot"].get("open-loops.md"):
            raise DomainError(
                "stale_scan",
                "El registro cambió durante la lectura; vuelva a auditar y revisar.",
            )
        original = original_bytes.decode("utf-8")
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
        if len(updated.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise DomainError(
                "oversized_source",
                "El registro actualizado superaría 1 MB; reorganice el registro antes de aplicar.",
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
            "before_sha256": before_hash,
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
    # Unificar rutas relativas y los alias cortos 8.3 que Windows usa en TEMP.
    root = root.resolve(strict=True)
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
