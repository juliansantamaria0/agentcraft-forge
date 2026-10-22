"""Catálogo explícito de capacidades, recursos y límites revisados localmente."""

from dataclasses import dataclass
from enum import StrEnum


class Kind(StrEnum):
    rag = "rag"
    tools = "tools"
    multi = "multi"
    expenses = "expenses"
    audit = "audit"


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    resource: str
    factory: str
    scope: str
    dependencies: tuple[str, ...] = ()
    configuration: dict | None = None


@dataclass(frozen=True)
class TemplateDefinition:
    capabilities: tuple[str, ...]
    summary: str
    limits: tuple[str, ...]
    runtime: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    domain: bool = False


TOOLS: dict[str, ToolDefinition] = {}


def register_tool(definition: ToolDefinition) -> None:
    """Extensión por código revisado, nunca por importaciones del propósito o del LLM."""
    import re

    if not re.fullmatch(r"[a-z][a-z0-9_]*", definition.name):
        raise ValueError("Nombre de herramienta no válido.")
    if definition.name in TOOLS:
        raise ValueError("Herramienta ya registrada.")
    if definition.resource != f"tool_plugins/{definition.name}.py":
        raise ValueError("El recurso debe estar dentro de tool_plugins.")
    if definition.factory != f"agent_app.tool_plugins.{definition.name}:build":
        raise ValueError("La fábrica debe corresponder al módulo registrado.")
    TOOLS[definition.name] = definition


register_tool(
    ToolDefinition(
        "repository_info",
        "tool_plugins/repository_info.py",
        "agent_app.tool_plugins.repository_info:build",
        "Metadatos públicos de los repositorios autorizados; solo lectura.",
        configuration={
            "repositories": [
                "qdrant/qdrant",
                "langchain-ai/langchain",
                "crewAIInc/crewAI",
            ]
        },
    )
)
register_tool(
    ToolDefinition(
        "current_weather",
        "tool_plugins/current_weather.py",
        "agent_app.tool_plugins.current_weather:build",
        "Temperatura y viento actuales mediante Open-Meteo; Bogotá usa el argumento Bogota.",
        configuration={
            "cities": {"Bogota": [4.711, -74.0721], "Madrid": [40.4168, -3.7038]}
        },
    )
)

AI_DEPENDENCIES = (
    "httpx==0.28.1",
    "pydantic>=2.11.9,<2.13",
    "python-dotenv>=1.2.2,<2",
    "langchain-openai==1.7.2",
)
TEMPLATES = {
    Kind.rag: TemplateDefinition(
        ("search_documents",),
        "Preguntas sobre documentos propios con citas y abstención.",
        (
            "Solo documentos UTF-8 .md y .txt ingeridos explícitamente, hasta 10 MB de corpus.",
            "Colección y tenant configurados; las citas válidas no prueban por sí solas corrección semántica.",
        ),
        ("rag/__init__.py", "rag/store.py", "rag/ingest.py", "rag/service.py"),
        AI_DEPENDENCIES
        + (
            "qdrant-client==1.19.1",
            "langchain-qdrant==1.1.0",
            "langchain-text-splitters==1.1.3",
        ),
    ),
    Kind.tools: TemplateDefinition(
        (),
        "Consultas con herramientas de solo lectura autorizadas.",
        (
            "Sin navegación general, escritura, ejecución de comandos ni otras ciudades o repositorios.",
            "Un propósito escrito no añade capacidades; amplíe el catálogo para cubrir otros requisitos.",
        ),
        ("tools.py", "react.py", "tool_http.py", "tool_plugins/__init__.py"),
        AI_DEPENDENCIES,
    ),
    Kind.multi: TemplateDefinition(
        ("analyze", "design", "review"),
        "Tres roles producen una propuesta técnica estructurada.",
        (
            "Analista, arquitecto y revisor; sin herramientas, navegación ni ejecución de código.",
            "La propuesta necesita revisión y no equivale a una implementación ejecutada.",
        ),
        ("multi.py",),
        AI_DEPENDENCIES + ("crewai==1.15.28",),
    ),
    Kind.expenses: TemplateDefinition(
        ("record_expenses", "summarize_expenses", "set_budget"),
        "Gastos personales en COP y presupuestos locales.",
        (
            "Interpretación determinista de español acotado; pide aclaración ante ambigüedad.",
            "Los mensajes proponen; las escrituras requieren solicitudes JSON explícitas. Sin conexión bancaria.",
        ),
        domain=True,
    ),
    Kind.audit: TemplateDefinition(
        ("scan_commitments", "apply_reviewed_commitments"),
        "Revisión local de compromisos y selección explícita.",
        (
            "Lee open-loops.md, journal y exports locales de WhatsApp; no conecta con cuentas ni envía mensajes.",
            "Propone candidatos; aplicar exige revisar una selección y su informe vigente.",
        ),
        domain=True,
    ),
}


def capabilities(kind: Kind) -> set[str]:
    return set(TOOLS) if kind == Kind.tools else set(TEMPLATES[kind].capabilities)


# Compatibilidad con consumidores que importaban este nombre de schema.
CAPABILITIES = {kind: capabilities(kind) for kind in Kind}


def dependencies(kind: Kind, selected: list[str]) -> list[str]:
    values = list(TEMPLATES[kind].dependencies)
    if kind == Kind.tools:
        for name in selected:
            values.extend(TOOLS[name].dependencies)
    return list(dict.fromkeys(values))


def scope(spec) -> dict:
    definition = TEMPLATES[spec.plan.kind]
    return {
        "kind": spec.plan.kind.value,
        "summary": definition.summary,
        "capabilities": [
            {
                "name": name,
                "scope": (
                    TOOLS[name].scope
                    if spec.plan.kind == Kind.tools
                    else definition.summary
                ),
                "arguments": (
                    TOOLS[name].configuration if spec.plan.kind == Kind.tools else None
                ),
            }
            for name in spec.plan.tools
        ],
        "limits": list(definition.limits),
        "requires_model": not definition.domain,
        "max_steps": spec.max_steps,
        "max_tool_calls": spec.max_tool_calls,
        "purpose_is_configuration": "El propósito orienta las respuestas dentro de este alcance; no crea integraciones nuevas.",
    }
