"""Gastos COP: solicitudes explícitas, enteros, transacciones y recibos idempotentes."""

import json
import re
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from difflib import get_close_matches
from pathlib import Path

from agentcraft_forge.domains.common import (
    DomainError,
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

SCHEMA = """
CREATE TABLE IF NOT EXISTS budgets (
    month TEXT PRIMARY KEY, amount INTEGER NOT NULL CHECK(amount > 0));
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount INTEGER NOT NULL CHECK(amount > 0), description TEXT NOT NULL,
    category TEXT NOT NULL, expense_date TEXT NOT NULL,
    operation_id TEXT NOT NULL, voided_by TEXT);
CREATE INDEX IF NOT EXISTS expenses_date ON expenses(expense_date);
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
    receipt TEXT NOT NULL);
"""


def category(description: str) -> str:
    lower = normalize(description)
    rules = {
        "Transporte": r"\b(?:transporte|trasporte|uber|taxi|pasaje|bus)\b",
        "Alimentación": r"\b(?:mercado|supermercado|almuerzo|comida|corrientazo)\b",
        "Café y snacks": r"\b(?:cafe|starbucks|juan valdez|galleta|postre|frappuccino)\b",
        "Tecnología": r"\b(?:expansor|memoria|disco|software)\b",
        "Entretenimiento": r"\b(?:xbox|consola|cine|videojuego)\b",
        "Servicios": r"\b(?:arriendo|luz|agua|internet)\b",
    }
    return next(
        (name for name, pattern in rules.items() if re.search(pattern, lower)),
        "Sin clasificar",
    )


def month(value: object) -> str:
    value = text(value, 7)
    iso_date(value + "-01")
    return value


def validate_request(request: object) -> dict:
    if not isinstance(request, dict):
        raise DomainError("invalid_request", "Se requiere un objeto JSON.")
    action = request.get("action")
    if action == "summary":
        fields(request, {"action"}, {"month", "date", "limit", "offset"})
        if "month" in request and "date" in request:
            raise DomainError(
                "invalid_period", "Seleccione un día, un mes o todo el historial."
            )
        return {
            "action": action,
            **({"month": month(request["month"])} if "month" in request else {}),
            **({"date": iso_date(request["date"])} if "date" in request else {}),
            "limit": integer(request.get("limit", 100), 1, 1000),
            "offset": integer(request.get("offset", 0), 0, 10_000_000),
        }
    if action == "receipt":
        fields(request, {"action", "operation_id"})
        return {"action": action, "operation_id": operation_id(request["operation_id"])}
    if action == "set_budget":
        fields(request, {"action", "operation_id", "month", "amount", "currency"})
        result = {
            **request,
            "month": month(request["month"]),
            "amount": integer(request["amount"]),
        }
    elif action == "record":
        fields(request, {"action", "operation_id", "currency", "expenses"})
        values = request["expenses"]
        if not isinstance(values, list) or not 1 <= len(values) <= 20:
            raise DomainError(
                "invalid_batch", "Cada compra debe incluir de 1 a 20 gastos."
            )
        items = []
        for item in values:
            fields(item, {"amount", "description", "expense_date"}, {"category"})
            description = text(item["description"], 300)
            items.append(
                {
                    "amount": integer(item["amount"]),
                    "description": description,
                    "expense_date": iso_date(item["expense_date"]),
                    "category": text(item.get("category", category(description)), 80),
                }
            )
        result = {**request, "expenses": items}
    elif action == "void":
        fields(request, {"action", "operation_id", "expense_ids", "reason"})
        ids = request["expense_ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
            raise DomainError("invalid_batch", "Seleccione de 1 a 20 registros.")
        ids = [integer(value) for value in ids]
        if len(ids) != len(set(ids)):
            raise DomainError(
                "invalid_batch", "No repita registros en la misma operación."
            )
        result = {**request, "expense_ids": ids, "reason": text(request["reason"], 300)}
    else:
        raise DomainError(
            "unknown_action", "Acción no admitida por el motor de gastos."
        )
    if action != "void" and result["currency"] != "COP":
        raise DomainError(
            "unsupported_currency",
            "Esta versión admite únicamente COP; no convierte otras monedas.",
        )
    result["operation_id"] = operation_id(result["operation_id"])
    return result


def summary(connection: sqlite3.Connection, request: dict) -> dict:
    period = request.get("date", request.get("month", "all"))
    params = [
        request.get("date"),
        request.get("date"),
        request.get("month"),
        request.get("month"),
    ]
    limit, offset = request.get("limit", 100), request.get("offset", 0)
    rows = [
        dict(row)
        for row in connection.execute(
            """SELECT id,amount,description,category,expense_date,operation_id
            FROM expenses WHERE voided_by IS NULL
            AND (? IS NULL OR expense_date = ?)
            AND (? IS NULL OR substr(expense_date,1,7) = ?)
            ORDER BY expense_date,id LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
    ]
    count, total = connection.execute(
        """SELECT COUNT(*),COALESCE(SUM(amount),0) FROM expenses
        WHERE voided_by IS NULL AND (? IS NULL OR expense_date = ?)
        AND (? IS NULL OR substr(expense_date,1,7) = ?)""",
        params,
    ).fetchone()
    categories = {
        row[0]: row[1]
        for row in connection.execute(
            """SELECT category,SUM(amount) FROM expenses
            WHERE voided_by IS NULL AND (? IS NULL OR expense_date = ?)
            AND (? IS NULL OR substr(expense_date,1,7) = ?) GROUP BY category""",
            params,
        )
    }
    budget_month = request.get("month", request.get("date", "")[:7])
    budget_row = connection.execute(
        "SELECT amount FROM budgets WHERE month = ?", (budget_month,)
    ).fetchone()
    budget = budget_row["amount"] if budget_row else None
    month_total = (
        connection.execute(
            "SELECT COALESCE(SUM(amount),0) FROM expenses WHERE voided_by IS NULL AND substr(expense_date,1,7) = ?",
            (budget_month,),
        ).fetchone()[0]
        if budget_month
        else None
    )
    return {
        "status": "ok",
        "currency": "COP",
        "period": period,
        "count": count,
        "returned_count": len(rows),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(rows) < count,
        "total": total,
        "categories": categories,
        "expenses": rows,
        "monthly_budget": budget,
        "month_total": month_total,
        "remaining_budget": budget - month_total if budget is not None else None,
    }


def handle(root: Path, request: object) -> dict:
    request = validate_request(request)  # Validar todo el lote antes de tocar SQLite.
    database = safe_path(root, ".data/expenses-v1.sqlite3")
    database.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(database, timeout=10)) as connection:
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        action = request["action"]
        if action == "summary":
            # Todas las consultas del resumen deben compartir el mismo snapshot.
            connection.execute("BEGIN")
            return summary(connection, request)
        identifier = request["operation_id"]
        connection.execute("BEGIN IMMEDIATE")
        try:
            previous = connection.execute(
                "SELECT request_hash,receipt FROM operations WHERE operation_id = ?",
                (identifier,),
            ).fetchone()
            if action == "receipt":
                if previous is None:
                    raise DomainError(
                        "not_found", "No existe un comprobante para esa operación."
                    )
                connection.rollback()
                return {**json.loads(previous["receipt"]), "replayed": True}
            request_hash = digest(request)
            if previous:
                if previous["request_hash"] != request_hash:
                    raise DomainError(
                        "operation_conflict",
                        "El identificador ya corresponde a otra solicitud.",
                    )
                connection.rollback()
                return {**json.loads(previous["receipt"]), "replayed": True}
            ids = []
            periods = set()
            if action == "set_budget":
                connection.execute(
                    "INSERT INTO budgets(month,amount) VALUES (?,?) ON CONFLICT(month) DO UPDATE SET amount=excluded.amount",
                    (request["month"], request["amount"]),
                )
                periods.add(request["month"])
            elif action == "record":
                for item in request["expenses"]:
                    cursor = connection.execute(
                        "INSERT INTO expenses(amount,description,category,expense_date,operation_id) VALUES (?,?,?,?,?)",
                        (
                            item["amount"],
                            item["description"],
                            item["category"],
                            item["expense_date"],
                            identifier,
                        ),
                    )
                    ids.append(cursor.lastrowid)
                    periods.add(item["expense_date"][:7])
            elif action == "void":
                for expense_id in request["expense_ids"]:
                    row = connection.execute(
                        "SELECT expense_date,voided_by FROM expenses WHERE id = ?",
                        (expense_id,),
                    ).fetchone()
                    if row is None or row["voided_by"] is not None:
                        raise DomainError(
                            "invalid_expense",
                            "Algún registro no existe o ya está anulado; no se aplicó el lote.",
                        )
                    periods.add(row["expense_date"][:7])
                    connection.execute(
                        "UPDATE expenses SET voided_by = ? WHERE id = ?",
                        (identifier, expense_id),
                    )
                ids = request["expense_ids"]
            period_totals = {}
            for period in sorted(periods):
                totals = summary(connection, {"month": period})
                for key in (
                    "expenses",
                    "limit",
                    "offset",
                    "has_more",
                    "returned_count",
                ):
                    totals.pop(key)
                period_totals[period] = totals
            receipt = {
                "status": "committed",
                "persisted": True,
                "action": action,
                "operation_id": identifier,
                "request_hash": request_hash,
                "record_ids": ids,
                "created_at": now(),
                "replayed": False,
                "periods": period_totals,
                "records": [
                    dict(
                        connection.execute(
                            "SELECT id,amount,description,category,expense_date,voided_by FROM expenses WHERE id = ?",
                            (identifier,),
                        ).fetchone()
                    )
                    for identifier in ids
                ],
            }
            if action == "void":
                receipt["reason"] = request["reason"]
            connection.execute(
                "INSERT INTO operations VALUES (?,?,?)",
                (identifier, request_hash, canonical(receipt)),
            )
            connection.commit()
            # La confirmación se lee después del commit; no se redacta por anticipado.
            return json.loads(
                connection.execute(
                    "SELECT receipt FROM operations WHERE operation_id = ?",
                    (identifier,),
                ).fetchone()[0]
            )
        except Exception:
            connection.rollback()
            raise


MONEY = re.compile(
    r"(?<![\w\d])(?:\$\s*)?(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{1,2})?\s*[kK]?(?:\s*(?:COP|pesos))?(?![\w\d])",
    re.IGNORECASE,
)
DATES = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
MONTH_DATES = re.compile(r"\b\d{4}-\d{2}\b")
MONTH_NAMES = (
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


def proposal_period(message: str, today: date) -> tuple[dict, str]:
    """Resuelve solo periodos soportados y devuelve el texto sin sus cifras."""
    lower = normalize(message)
    if re.search(
        r"\b(?:semana\w*|quincena\w*|ano\w*|entre|desde|hasta|rango)\b", lower
    ):
        raise DomainError(
            "ambiguous_period",
            "Indique un día o mes concreto; no se admiten rangos, semanas ni años completos.",
        )
    days, months = set(), set()
    for token in DATES.findall(lower):
        try:
            if "-" in token:
                value = date.fromisoformat(token)
            else:
                day_part, month_part, year_part = token.split("/")
                year = int(year_part) + (2000 if len(year_part) == 2 else 0)
                value = date(year, int(month_part), int(day_part))
        except ValueError as exc:
            raise DomainError(
                "invalid_date", "La fecha indicada no es válida."
            ) from exc
        days.add(value.isoformat())
    remainder = DATES.sub(" ", lower)
    for token in MONTH_DATES.findall(remainder):
        months.add(month(token))
    remainder = MONTH_DATES.sub(" ", remainder)
    named = re.compile(r"\b(" + "|".join(MONTH_NAMES) + r")(?:\s+(?:de\s+)?(\d{4}))?\b")
    for match in named.finditer(remainder):
        if not match[2]:
            raise DomainError(
                "ambiguous_period",
                "Indique también el año del mes solicitado, por ejemplo noviembre de 2026.",
            )
        months.add(month(f"{match[2]}-{MONTH_NAMES.index(match[1]) + 1:02d}"))
    remainder = named.sub(" ", remainder)
    for word, offset in (("hoy", 0), ("ayer", 1), ("anteayer", 2)):
        if re.search(rf"\b{word}\b", remainder):
            days.add((today - timedelta(days=offset)).isoformat())
    if re.search(r"\bdiario\b", remainder) and not days:
        days.add(today.isoformat())
    for pattern, offset in (
        (r"\b(?:este mes|mes actual)\b", 0),
        (r"\bmes (?:pasado|anterior)\b", -1),
        (r"\b(?:mes (?:proximo|siguiente)|proximo mes)\b", 1),
    ):
        if re.search(pattern, remainder):
            ordinal = today.year * 12 + today.month - 1 + offset
            year, zero_month = divmod(ordinal, 12)
            months.add(month(f"{year:04d}-{zero_month + 1:02d}"))
    if (
        len(days) > 1
        or len(months) > 1
        or (days and months and next(iter(days))[:7] not in months)
    ):
        raise DomainError(
            "ambiguous_period",
            "Hay varios periodos; separe las solicitudes para confirmar su asociación.",
        )
    if days:
        return {"date": next(iter(days))}, remainder
    if months:
        return {"month": next(iter(months))}, remainder
    return {}, remainder


def amount(token: str) -> int | None:
    cleaned = re.sub(r"\$|cop|pesos|\s", "", token, flags=re.IGNORECASE)
    kilo = cleaned.lower().endswith("k")
    cleaned = cleaned.rstrip("kK")
    if not kilo:
        cleaned = re.sub(r"[.,](?=\d{3}(?:[.,]|$))", "", cleaned)
    cleaned = cleaned.replace(",", ".")
    try:
        value = Decimal(cleaned) * (1000 if kilo else 1)
    except InvalidOperation:
        return None
    if (
        not value.is_finite()
        or value != value.to_integral_value()
        or not 0 < value <= 1_000_000_000_000
    ):
        return None
    if (
        not kilo
        and "$" not in token
        and not re.search(r"cop|pesos", token, re.IGNORECASE)
        and value < 100
    ):
        return None  # Cantidades de artículos no se interpretan como dinero.
    return int(value)


def propose(message: str, reference_date: date | None = None) -> dict:
    """Interpreta sin escribir. El chat debe ejecutar después la solicitud explícita."""
    message = text(message, 6000)
    lower = normalize(message)
    today = reference_date or date.today()
    unclear = {
        "status": "needs_clarification",
        "persisted": False,
        "model_invoked": False,
    }
    words = re.findall(r"\w+", lower)
    summary_intent = any(
        get_close_matches(word, ["resumen"], n=1, cutoff=0.72) for word in words
    )
    summary_intent = summary_intent or any(
        term in lower for term in ("cuanto me queda", "saldo restante")
    )
    if summary_intent or "presupuesto" in words:
        try:
            period, without_period = proposal_period(message, today)
        except DomainError as exc:
            return {**unclear, "reason": str(exc)}
    if summary_intent:
        if re.search(r"\b(?:gaste|pague|compre|registra\w*|anota\w*)\b", lower) or any(
            amount(match.group()) is not None
            for match in MONEY.finditer(without_period)
        ):
            return {
                **unclear,
                "reason": "Separe el registro de gastos y la consulta de resumen; no se omitió ni registró ninguna compra.",
            }
        request = {"action": "summary"}
        if period:
            request.update(period)
        elif "todos" in words or "historial" in words:
            pass
        else:
            request["month"] = today.strftime("%Y-%m")
        return {
            "status": "proposal",
            "persisted": False,
            "model_invoked": False,
            "request": request,
        }
    if re.search(
        r"\b(?:no|manana|devolv\w*|reembols\w*|ingreso\w*|recibi\w*|anula\w*|borra\w*|corrig\w*)\b|\bvoy a\b|\b(?:gastare|comprare|pagare)\b",
        lower,
    ):
        return {
            **unclear,
            "reason": "Confirme si es un gasto realizado, una devolución, una corrección o una intención futura.",
        }
    if re.search(r"\b(?:usd|eur|dolares?|euros?)\b|[€£]|-\s*\$?\s*\d", lower):
        # El signo de fecha ISO no representa un importe negativo.
        without_dates = (
            without_period if "presupuesto" in words else DATES.sub(" ", lower)
        )
        if re.search(
            r"\b(?:usd|eur|dolares?|euros?)\b|[€£]|-\s*\$?\s*\d", without_dates
        ):
            return {
                **unclear,
                "reason": "Se admiten gastos positivos en COP; no se realiza conversión de moneda.",
            }
    if "presupuesto" in words:
        if "date" in period:
            return {
                **unclear,
                "reason": "El presupuesto es mensual; indique el mes y el año, no un día.",
            }
        budget_month = period.get("month", today.strftime("%Y-%m"))
        values = [
            value
            for match in MONEY.finditer(without_period)
            if (value := amount(match.group())) is not None
        ]
        if not values:
            return {
                "status": "proposal",
                "persisted": False,
                "model_invoked": False,
                "request": {"action": "summary", "month": budget_month},
            }
        if len(values) != 1:
            return {
                **unclear,
                "reason": "Confirme un único importe y el mes del presupuesto.",
            }
        return {
            "status": "proposal",
            "persisted": False,
            "model_invoked": False,
            "request": {
                "action": "set_budget",
                "currency": "COP",
                "month": budget_month,
                "amount": values[0],
            },
            "assumptions": [
                f"Presupuesto mensual en COP para {budget_month}; añadir un operation_id único y estable antes de ejecutar."
            ],
        }
    explicit_dates = set()
    for token in DATES.findall(message):
        try:
            if "-" in token:
                value = date.fromisoformat(token)
            else:
                day_part, month_part, year_part = token.split("/")
                year = int(year_part) + (2000 if len(year_part) == 2 else 0)
                value = date(year, int(month_part), int(day_part))
        except ValueError:
            return {**unclear, "reason": "La fecha indicada no es válida."}
        explicit_dates.add(value)
    for word, offset in (("hoy", 0), ("ayer", 1), ("anteayer", 2)):
        if word in words:
            explicit_dates.add(today - timedelta(days=offset))
    if len(explicit_dates) > 1:
        return {
            **unclear,
            "reason": "Hay varias fechas; separe los gastos para confirmar su asociación.",
        }
    expense_day = next(iter(explicit_dates), today)
    clean = DATES.sub(" ", message)
    clauses = [
        part.strip()
        for part in re.split(r"\s+y\s+|[;\n]", clean, flags=re.IGNORECASE)
        if part.strip()
    ]
    priced = [
        part
        for part in clauses
        if any(amount(match.group()) is not None for match in MONEY.finditer(part))
    ]
    if len(priced) <= 1:
        if len(clauses) > 1 and re.search(r"[;\n]", clean):
            return {
                **unclear,
                "reason": "Cada gasto separado debe incluir su importe; no se omitirán conceptos sin precio.",
            }
        clauses = [clean]
    else:
        if len(priced) != len(clauses):
            return {
                **unclear,
                "reason": "Cada gasto separado debe incluir su importe; no se omitirán conceptos sin precio.",
            }
    items = []
    for clause in clauses:
        matches = [(match, amount(match.group())) for match in MONEY.finditer(clause)]
        matches = [(match, value) for match, value in matches if value is not None]
        if len(matches) != 1:
            return {
                **unclear,
                "reason": "No se puede asociar inequívocamente cada importe con su concepto.",
            }
        match, value = matches[0]
        description = clause[: match.start()] + " " + clause[match.end() :]
        description = re.sub(
            r"\b(?:gast[eé]|pagu[eé]|compr[eé]|almorc[eé]|hoy|ayer|anteayer)\b",
            " ",
            description,
            flags=re.IGNORECASE,
        )
        description = re.sub(r"\s+", " ", description).strip(" .,")
        description = re.sub(
            r"^(?:en|de|por|un|una)\s+|\s+(?:por|de|en)$",
            "",
            description,
            flags=re.IGNORECASE,
        ).strip()
        if len(description) < 3:
            return {**unclear, "reason": "Falta el concepto del gasto."}
        items.append(
            {
                "amount": value,
                "description": description,
                "expense_date": expense_day.isoformat(),
            }
        )
    return {
        "status": "proposal",
        "persisted": False,
        "model_invoked": False,
        "request": {"action": "record", "currency": "COP", "expenses": items},
        "assumptions": [
            "Moneda COP",
            "Añadir un operation_id único y estable antes de ejecutar; la propuesta todavía no está registrada.",
        ],
    }
