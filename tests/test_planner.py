import pytest
from pydantic import ValidationError

from agentcraft_forge.planner import design, offline_plan
from agentcraft_forge.schema import Kind, Plan


@pytest.mark.parametrize(
    "purpose,expected",
    [
        ("Consultar documentos de la empresa", Kind.rag),
        ("Crear un equipo de agentes técnicos", Kind.multi),
        ("Consultar el clima de Bogotá", Kind.tools),
    ],
)
def test_offline_architecture_selection(purpose, expected):
    assert offline_plan(purpose).kind == expected


def test_ai_backend_is_injectable_without_credentials():
    def designer(purpose, kind):
        return Plan(
            kind=Kind.tools,
            tools=["current_weather"],
            architecture_notes=["Clima solamente"],
        )

    spec = design(
        "weather-agent",
        "Consultar el clima de Bogotá",
        Kind.tools,
        ai=True,
        designer=designer,
    )
    assert spec.plan.tools == ["current_weather"]


def test_invalid_request_rejected_before_ai_call():
    def designer(*args):
        raise AssertionError("No debe llamarse al diseñador")

    with pytest.raises(ValidationError):
        design(
            "../bad", "Propósito válido para este proyecto", ai=True, designer=designer
        )
