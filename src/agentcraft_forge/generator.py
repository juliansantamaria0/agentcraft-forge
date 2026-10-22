"""Generación desde recursos incluidos en el wheel, independiente del cwd."""

import hashlib
import json
from importlib.resources import files
from pathlib import Path, PurePosixPath

from jinja2 import Environment, StrictUndefined

from agentcraft_forge.catalog import TEMPLATES as CATALOG
from agentcraft_forge.catalog import TOOLS, dependencies, scope
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
    Kind.expenses: [],
    Kind.audit: [],
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
    modern = spec.template_version == "3"
    context = {
        "name": spec.name,
        "kind": spec.plan.kind.value,
        "modern": modern,
        "dependencies": dependencies(spec.plan.kind, spec.plan.tools),
    }
    result = {
        destination: env.from_string(
            root.joinpath("common", source).read_text(encoding="utf-8")
        ).render(**context)
        for destination, source in TEMPLATES.items()
    }
    domain = CATALOG[spec.plan.kind].domain
    specific = (
        list(CATALOG[spec.plan.kind].runtime) if modern else SPECIFIC[spec.plan.kind]
    )
    runtime = ["__init__.py"] if domain else COMMON_RUNTIME + specific
    if modern and spec.plan.kind == Kind.tools:
        runtime += [TOOLS[name].resource for name in spec.plan.tools]
    for name in runtime:
        data = root.joinpath(
            "runtime",
            ("tools_legacy.py" if name == "tools.py" and not modern else name)
            + ".tmpl",
        ).read_text(encoding="utf-8")
        result["src/agent_app/" + name] = data
    if domain:
        resources = files("agentcraft_forge.domains")
        for source, destination in (
            ("common.py", "domain_common.py"),
            (spec.plan.kind.value + ".py", "domain.py"),
        ):
            result["src/agent_app/" + destination] = (
                resources.joinpath(source)
                .read_text(encoding="utf-8")
                .replace(
                    "from agentcraft_forge.domains.common import",
                    "from agent_app.domain_common import",
                )
            )
        for destination, source in (
            ("src/agent_app/runner.py", "domain_runner.py.j2"),
            ("README.md", "domain_readme.md.j2"),
            ("tests/test_domain.py", "domain_test.py.j2"),
        ):
            result[destination] = env.from_string(
                root.joinpath("common", source).read_text(encoding="utf-8")
            ).render(**context)
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
    if spec.plan.kind == Kind.audit:
        result["open-loops.md"] = (
            "# Compromisos\n\n<!-- Añada aquí sus tareas reales. No se incluyen ejemplos como datos del usuario. -->\n"
        )
        result["journal/.gitkeep"] = ""
        result["whatsapp/.gitkeep"] = ""
        result[
            ".gitignore"
        ] += "\n# Datos personales del auditor\njournal/*\n!journal/.gitkeep\nwhatsapp/*\n!whatsapp/.gitkeep\nopen-loops.md\n"
    if modern:
        result["scope.json"] = (
            json.dumps(scope(spec), ensure_ascii=False, indent=2) + "\n"
        )
        if spec.plan.kind == Kind.tools:
            factories = {name: TOOLS[name].factory for name in spec.plan.tools}
            configuration = {
                name: TOOLS[name].configuration for name in spec.plan.tools
            }
            result["src/agent_app/tool_registry.py"] = (
                "FACTORIES = "
                + repr(factories)
                + "\n"
                + "CONFIGURATION = "
                + repr(configuration)
                + "\n"
            )
        result["src/agent_app/evaluate.py"] = root.joinpath(
            "runtime", "evaluate.py.tmpl"
        ).read_text(encoding="utf-8")
        result["evals/smoke.json"] = root.joinpath(
            "evals", spec.plan.kind.value + ".json"
        ).read_text(encoding="utf-8")
    if (
        modern
        and spec.plan.kind == Kind.expenses
        and spec.generator_version is not None
        and tuple(map(int, spec.generator_version.split("."))) >= (0, 3, 1)
    ):
        result["evals/complete.json"] = root.joinpath(
            "evals", "expenses-complete.json"
        ).read_text(encoding="utf-8")
    if spec.template_version in {"2", "3"}:
        result[".agents/skills/agentcraft-project/SKILL.md"] = env.from_string(
            root.joinpath("common", "project_skill.md.j2").read_text(encoding="utf-8")
        ).render(**context)
        provenance = {
            "schema_version": 1,
            "generator": "agentcraft-forge",
            "generator_version": spec.generator_version,
            "template_version": spec.template_version,
            "spec_sha256": hashlib.sha256(spec.model_dump_json().encode()).hexdigest(),
            "original_files": {
                name: hashlib.sha256(data.encode()).hexdigest()
                for name, data in sorted(result.items())
            },
            "limitations": "Huella de origen local, no firma ni prueba de autoría frente a un atacante local.",
        }
        result["agentcraft.provenance.json"] = (
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
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
