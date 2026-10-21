from datetime import date

import pytest

from agentcraft_forge.domains.common import DomainError
from agentcraft_forge.domains.expenses import handle, propose

TODAY = date(2026, 10, 21)


def record(identifier="message-0001", amount=12000, day="2026-10-21"):
    return {
        "action": "record",
        "operation_id": identifier,
        "currency": "COP",
        "expenses": [
            {"amount": amount, "description": "Transporte", "expense_date": day}
        ],
    }


def test_conversation_survives_restarts_and_matches_synthetic_totals(tmp_path):
    handle(
        tmp_path,
        {
            "action": "set_budget",
            "operation_id": "budget-2026-10",
            "month": "2026-10",
            "amount": 2500000,
            "currency": "COP",
        },
    )
    for index, value in enumerate((12000, 22000, 24500, 2400000, 450000, 15000)):
        receipt = handle(tmp_path, record(f"message-{index:04}", value))
        assert receipt["persisted"] is True
        assert len(receipt["record_ids"]) == 1
    summary = handle(tmp_path, {"action": "summary", "month": "2026-10"})
    assert summary["count"] == 6
    assert summary["total"] == 2923500
    assert summary["remaining_budget"] == -423500
    assert not (tmp_path / "data/gastos.db").exists()


def test_idempotency_distinguishes_retries_from_new_identical_expenses(tmp_path):
    first = handle(tmp_path, record())
    replay = handle(tmp_path, record())
    assert replay["replayed"] is True
    assert replay["record_ids"] == first["record_ids"]
    handle(tmp_path, record("message-0002"))
    assert handle(tmp_path, {"action": "summary"})["total"] == 24000
    with pytest.raises(DomainError, match="otra solicitud"):
        handle(tmp_path, record(amount=15000))
    assert (
        handle(tmp_path, {"action": "receipt", "operation_id": "message-0001"})[
            "record_ids"
        ]
        == first["record_ids"]
    )


def test_whole_batch_rejected_before_writing(tmp_path):
    request = record()
    request["expenses"].append(
        {"amount": 0, "description": "inválido", "expense_date": "2026-10-21"}
    )
    with pytest.raises(DomainError):
        handle(tmp_path, request)
    assert not (tmp_path / ".data").exists()


def test_failure_mid_transaction_rolls_back_every_void(tmp_path):
    receipt = handle(tmp_path, record())
    with pytest.raises(DomainError):
        handle(
            tmp_path,
            {
                "action": "void",
                "operation_id": "void-message-001",
                "expense_ids": [receipt["record_ids"][0], 999],
                "reason": "Corrección",
            },
        )
    assert handle(tmp_path, {"action": "summary"})["count"] == 1
    assert handle(tmp_path, {"action": "receipt", "operation_id": "message-0001"})[
        "persisted"
    ]
    handle(
        tmp_path,
        {
            "action": "void",
            "operation_id": "void-message-002",
            "expense_ids": receipt["record_ids"],
            "reason": "Corrección",
        },
    )
    assert handle(tmp_path, {"action": "summary"})["total"] == 0


def test_month_budgets_do_not_rewrite_history(tmp_path):
    for period, value in (("2026-09", 100000), ("2026-10", 200000)):
        handle(
            tmp_path,
            {
                "action": "set_budget",
                "operation_id": "budget-" + period,
                "month": period,
                "amount": value,
                "currency": "COP",
            },
        )
    handle(tmp_path, record(day="2026-09-20"))
    assert (
        handle(tmp_path, {"action": "summary", "month": "2026-09"})["remaining_budget"]
        == 88000
    )
    assert (
        handle(tmp_path, {"action": "summary", "month": "2026-10"})["remaining_budget"]
        == 200000
    )
    assert handle(tmp_path, {"action": "summary"})["monthly_budget"] is None


@pytest.mark.parametrize("value", [-1, 0, 1.2, True, "12000", float("nan")])
def test_money_requires_positive_integer_cop(tmp_path, value):
    with pytest.raises(DomainError):
        handle(tmp_path, record(amount=value))


def test_currency_and_extra_fields_rejected(tmp_path):
    request = record()
    request["currency"] = "USD"
    with pytest.raises(DomainError):
        handle(tmp_path, request)
    request = record()
    request["shell"] = "bad"
    with pytest.raises(DomainError):
        handle(tmp_path, request)


@pytest.mark.parametrize(
    "message,value",
    [
        ("Gasté $12.000 en transporte", 12000),
        ("gaste 15k en trasporte", 15000),
        ("Compré un frappuccino y una galleta en Juan Valdez por $24.5k", 24500),
        ("Compré 2 cafés por $12.000", 12000),
    ],
)
def test_proposals_handle_quantities_and_formats_without_claiming_write(message, value):
    result = propose(message, TODAY)
    assert result["status"] == "proposal"
    assert result["persisted"] is False
    assert result["request"]["expenses"][0]["amount"] == value


def test_multiple_purchase_proposal():
    result = propose(
        "Compré una xbox de 2.400.000 y un expansor de memoria de $450.000", TODAY
    )
    assert [item["amount"] for item in result["request"]["expenses"]] == [
        2400000,
        450000,
    ]


@pytest.mark.parametrize(
    "message",
    [
        "No gasté $12.000 en transporte",
        "Mañana compraré un café por $12.000",
        "Me devolvieron $12.000",
        "Gasté $12 USD en café",
        "Gasté -$12.000 en transporte",
        "Gasté $12.000 y $15.000",
        "Gasté $12.000 el 31/02/2026",
    ],
)
def test_ambiguous_or_non_expenses_never_become_record_proposals(message):
    assert propose(message, TODAY)["status"] == "needs_clarification"


@pytest.mark.parametrize("token", ["2026-09-20", "20/09/2026"])
def test_explicit_date_is_not_treated_as_money(token):
    result = propose(f"El {token} gasté $12.000 en transporte", TODAY)
    item = result["request"]["expenses"][0]
    assert item["amount"] == 12000
    assert item["expense_date"] == "2026-09-20"


def test_typo_summary_has_explicit_all_history_scope():
    result = propose("dame un reumen de todos mis gastos", TODAY)
    assert result["request"] == {"action": "summary"}
    assert propose("resumen mensual", TODAY)["request"]["month"] == "2026-10"


def test_budget_intent_and_conflicting_dates():
    result = propose("presupuesto $2.500.000", TODAY)
    assert result["request"]["action"] == "set_budget"
    assert result["request"]["amount"] == 2500000
    assert result["persisted"] is False
    assert (
        propose("Hoy gasté $12.000 y ayer gasté $15.000", TODAY)["status"]
        == "needs_clarification"
    )
    assert (
        propose("El 2026-10-21 y el 2026-10-20 gasté $12.000", TODAY)["status"]
        == "needs_clarification"
    )


def test_summary_pagination_does_not_change_authoritative_totals(tmp_path):
    for index in range(3):
        receipt = handle(tmp_path, record(f"message-page-{index}", 12000))
        assert "expenses" not in receipt["periods"]["2026-10"]
        assert len(receipt["records"]) == 1
    page = handle(tmp_path, {"action": "summary", "limit": 1})
    assert page["count"] == 3
    assert page["total"] == 36000
    assert page["returned_count"] == 1
    assert page["has_more"]
    assert page["categories"]["Transporte"] == 36000
