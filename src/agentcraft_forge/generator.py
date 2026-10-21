"""Generación desde recursos incluidos en el wheel, independiente del cwd."""

from importlib.resources import files
from pathlib import Path, PurePosixPath

from jinja2 import Environment, StrictUndefined

from agentcraft_forge.schema import AgentSpec, Kind

TEMPLATES = {
    "pyproject.toml": "pyproject.toml.j2",
    "README.md": "README.md.j2",
    "LICENSE": "LICENSE.j2",
    ".gitignore": "gitignore.j2",
    ".env.example": "env.example.j2",
    ".dockerignore": "dockerignore.j2",
    "Dockerfile": "Dockerfile.j2",
    ".github/workflows/ci.yml": "ci.yml.j2",
    "src/agent_app/runner.py": "runner.py.j2",
    "tests/test_contract.py": "test_contract.py.j2",
}
COMMON_RUNTIME = ["__init__.py", "settings.py", "providers.py", "observability.py"]
SPECIFIC = {
    Kind.rag: ["rag/__init__.py", "rag/store.py", "rag/ingest.py", "rag/service.py"],
    Kind.tools: ["tools.py", "react.py"],
    Kind.multi: ["multi.py"],
}


def template_root():
    return files("agentcraft_forge").joinpath("templates")


def render(spec: AgentSpec) -> dict[str, str]:
    root = template_root()
    env = Environment(
        undefined=StrictUndefined,
        autoescape=False,  # noqa: S701 - Recursos de código/texto, nunca plantillas HTML.
        trim_blocks=True,
        lstrip_blocks=True,
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
        keep_trailing_newline=True,
    )
    context = {"name": spec.name, "kind": spec.plan.kind.value}
    result = {
        destination: env.from_string(
            root.joinpath("common", source).read_text(encoding="utf-8")
        ).render(**context)
        for destination, source in TEMPLATES.items()
    }
    for name in COMMON_RUNTIME + SPECIFIC[spec.plan.kind]:
        data = root.joinpath("runtime", name + ".tmpl").read_text(encoding="utf-8")
        result["src/agent_app/" + name] = data
    result["agentcraft.json"] = spec.model_dump_json(indent=2) + "\n"
    result["docs/architecture.md"] = (
        "# Diseño generado\n\n"
        + "\n".join("- " + note for note in spec.plan.architecture_notes)
        + "\n\nEl propósito completo se conserva como datos en agentcraft.json.\n"
    )
    if spec.plan.kind == Kind.rag:
        result["data/sample/policy.md"] = (
            "# Política ficticia\n\nLos tickets de prioridad alta se atienden en cuatro horas.\n"
        )
    return result


def generate(spec: AgentSpec, parent: Path) -> Path:
    contents = render(spec)  # Renderizar todo antes de tocar el filesystem.
    for name in contents:
        parts = PurePosixPath(name)
        if parts.is_absolute() or ".." in parts.parts or "\\" in name:
            raise ValueError("Ruta de plantilla no permitida.")
    parent = parent.resolve(strict=True)
    target = parent / spec.name
    target.mkdir(exist_ok=False)  # Nunca sobrescribir un proyecto existente.
    for name, value in contents.items():
        destination = target.joinpath(*PurePosixPath(name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(value, encoding="utf-8", newline="\n")
    # Si el disco falla, no se borra nada ajeno: build detectará archivos incompletos.
    return target
