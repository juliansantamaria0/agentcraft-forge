"""El modelo elige capacidades de un catálogo; nunca instrucciones ejecutables."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentcraft_forge.catalog import CAPABILITIES as CAPABILITIES
from agentcraft_forge.catalog import Kind, capabilities


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Kind
    tools: list[str] = Field(min_length=1, max_length=20)
    architecture_notes: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def approved_capabilities(self):
        if not set(self.tools).issubset(capabilities(self.kind)):
            raise ValueError("El plan solicita una capacidad fuera del catálogo.")
        if self.kind != Kind.tools and set(self.tools) != capabilities(self.kind):
            raise ValueError("La plantilla requiere todas sus capacidades declaradas.")
        if len(self.tools) != len(set(self.tools)):
            raise ValueError("No se permiten capacidades duplicadas.")
        if any(
            not note.strip() or len(note) > 1000 for note in self.architecture_notes
        ):
            raise ValueError("Notas de arquitectura no válidas.")
        return self


class AgentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1, le=1)
    template_version: str = Field(default="2", pattern=r"^[123]$")
    generator_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    name: str = Field(
        min_length=2, max_length=48, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
    )
    purpose: str = Field(min_length=10, max_length=6000)
    plan: Plan
    max_steps: int = Field(default=12, ge=2, le=60)
    max_tool_calls: int = Field(default=4, ge=1, le=20)

    @field_validator("name")
    @classmethod
    def portable_name(cls, value: str) -> str:
        reserved = {"con", "prn", "aux", "nul"}
        reserved.update(
            f"{prefix}{index}" for prefix in ("com", "lpt") for index in range(1, 10)
        )
        if value in reserved:
            raise ValueError(
                "Nombre reservado del sistema; elija un nombre portable como mi-agente."
            )
        return value
