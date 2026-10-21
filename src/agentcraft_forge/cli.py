"""Entrada pública: agentcraft init / build / run."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from agentcraft_forge import __version__
from agentcraft_forge.generator import generate
from agentcraft_forge.planner import design
from agentcraft_forge.project import build as build_project
from agentcraft_forge.project import ensure_built, run_project
from agentcraft_forge.schema import Kind

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"AgentCraft Forge {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool, typer.Option("--version", callback=version_callback, is_eager=True)
    ] = False,
):
    """Diseña, genera, valida y ejecuta agentes con plantillas controladas."""


@app.command()
def init(
    name: Annotated[
        str | None, typer.Option(help="Nombre del proyecto, con guiones")
    ] = None,
    purpose: Annotated[str | None, typer.Option(help="Propósito y requisitos")] = None,
    kind: Annotated[Kind | None, typer.Option(help="rag, tools o multi")] = None,
    directory: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    ai: Annotated[
        bool,
        typer.Option("--ai", help="Diseño mediante LLM; requiere extra ai y clave"),
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="No preguntar ni pedir confirmación")
    ] = False,
):
    """Asistente interactivo o generación automatizada sin credenciales."""
    if yes and (not name or not purpose):
        raise typer.BadParameter("Con --yes debe indicar --name y --purpose.")
    name = name or Prompt.ask("Nombre del nuevo agente", default="my-agent")
    purpose = purpose or Prompt.ask("¿Qué debe hacer el agente?")
    if kind is None and not yes:
        chosen = Prompt.ask(
            "Arquitectura", choices=["auto", "rag", "tools", "multi"], default="auto"
        )
        kind = None if chosen == "auto" else Kind(chosen)
    try:
        spec = design(name, purpose, kind, ai=ai)
        table = Table("Proyecto", "Arquitectura", "Capacidades")
        table.add_row(
            escape(spec.name), spec.plan.kind.value, escape(", ".join(spec.plan.tools))
        )
        console.print(table)
        if not yes and not Confirm.ask("¿Generar este proyecto?", default=True):
            raise typer.Abort()
        target = generate(spec, directory)
        console.print(Panel(escape(str(target)), title="Proyecto generado"))
        console.print("Siguiente paso: agentcraft build --project <carpeta>")
    except typer.Abort:
        raise
    except Exception as exc:
        console.print(
            f"Error: {type(exc).__name__}. Revise nombre, plan y destino.", style="red"
        )
        raise typer.Exit(1) from None


@app.command()
def build(
    project: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    install: Annotated[
        bool,
        typer.Option("--install", help="Instala el proyecto fiable en su propio .venv"),
    ] = False,
):
    """Valida esquema, configuración y sintaxis. No llama al modelo."""
    try:
        report = build_project(project, install=install)
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as exc:
        console.print(
            f"Build falló ({type(exc).__name__}). Revise el proyecto y sus dependencias.",
            style="red",
        )
        raise typer.Exit(1) from None


@app.command()
def run(
    project: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    message: Annotated[
        str | None, typer.Option(help="Una consulta; si falta, abre sesión interactiva")
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", help="Muestra el plan sin ejecutar modelo ni herramientas"
        ),
    ] = False,
    ingest: Annotated[
        Path | None,
        typer.Option(exists=True, file_okay=False, help="Ingerir documentos para RAG"),
    ] = None,
):
    """Ejecuta el agente en el venv del proyecto, o muestra su plan offline."""
    try:
        spec = ensure_built(project)
        if dry_run:
            typer.echo(
                json.dumps(
                    {
                        "mode": "offline-plan",
                        "model_invoked": False,
                        "name": spec.name,
                        "kind": spec.plan.kind.value,
                        "tools": spec.plan.tools,
                        "message": message,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            return
        code = run_project(project, message, ingest)
    except Exception as exc:
        console.print(
            f"Run falló ({type(exc).__name__}). Revise build, entorno y credenciales.",
            style="red",
        )
        raise typer.Exit(1) from None
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
