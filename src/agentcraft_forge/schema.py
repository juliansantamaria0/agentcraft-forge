"""El modelo elige capacidades de un catálogo; nunca instrucciones ejecutables."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Kind(StrEnum):
    rag = "rag"
    tools = "tools"
    multi = "multi"


CAPABILITIES = {
    Kind.rag: {"search_documents"},
    Kind.tools: {"repository_info", "current_weather"},
    Kind.multi: {"analyze", "design", "review"},
}


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Kind
    tools: list[str] = Field(min_length=1, max_length=3)
    architecture_notes: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def approved_capabilities(self):
        if not set(self.tools).issubset(CAPABILITIES[self.kind]):
            raise ValueError("El plan solicita una capacidad fuera del catálogo.")
        if self.kind != Kind.tools and set(self.tools) != CAPABILITIES[self.kind]:
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
    template_version: str = Field(default="1", pattern=r"^1$")
    name: str = Field(
        min_length=2, max_length=48, pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$"
    )
    purpose: str = Field(min_length=10, max_length=6000)
    plan: Plan
    max_steps: int = Field(default=12, ge=2, le=60)
    max_tool_calls: int = Field(default=4, ge=1, le=20)
