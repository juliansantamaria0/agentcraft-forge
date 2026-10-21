"""Entrada pública: agentcraft init / build / run."""

import json
import subprocess
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
from agentcraft_forge.integration import doctor as inspect_installation
from agentcraft_forge.integration import inspect_project, install_skill
from agentcraft_forge.planner import design
from agentcraft_forge.project import build as build_project
from agentcraft_forge.project import ensure_built, run_project, run_request
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
    kind: Annotated[
        Kind | None, typer.Option(help="rag, tools, multi, expenses o audit")
    ] = None,
    directory: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
    ai: Annotated[
        bool,
        typer.Option("--ai", help="Diseño mediante LLM; requiere extra ai y clave"),
    ] = False,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="No preguntar ni pedir confirmación")
    ] = False,
    json_output: Annotated[
        bool, typer.Option("--json", help="Salida estructurada; requiere --yes")
    ] = False,
):
    """Asistente interactivo o generación automatizada sin credenciales."""
    if yes and (not name or not purpose):
        raise typer.BadParameter("Con --yes debe indicar --name y --purpose.")
    if json_output and not yes:
        raise typer.BadParameter("--json requiere --yes, --name y --purpose.")
    name = name or Prompt.ask("Nombre del nuevo agente", default="my-agent")
    purpose = purpose or Prompt.ask("¿Qué debe hacer el agente?")
    if kind is None and not yes:
        chosen = Prompt.ask(
            "Arquitectura",
            choices=["auto", *[kind.value for kind in Kind]],
            default="auto",
        )
        kind = None if chosen == "auto" else Kind(chosen)
    try:
        spec = design(name, purpose, kind, ai=ai)
        table = Table("Proyecto", "Arquitectura", "Capacidades")
        table.add_row(
            escape(spec.name), spec.plan.kind.value, escape(", ".join(spec.plan.tools))
        )
        if not json_output:
            console.print(table)
        if not yes and not Confirm.ask("¿Generar este proyecto?", default=True):
            raise typer.Abort()
        target = generate(spec, directory)
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "status": "created",
                        "project": str(target),
                        "kind": spec.plan.kind.value,
                        "manifest": "agentcraft.json",
                        "provenance": "agentcraft.provenance.json",
                    },
                    ensure_ascii=False,
                )
            )
        else:
            console.print(Panel(escape(str(target)), title="Proyecto generado"))
            console.print("Siguiente paso: agentcraft build --project <carpeta>")
    except typer.Abort:
        raise
    except Exception as exc:
        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "status": "error",
                        "code": type(exc).__name__,
                        "message": "Revise nombre, plan y destino.",
                    }
                )
            )
        else:
            console.print(
                f"Error: {type(exc).__name__}. Revise nombre, plan y destino.",
                style="red",
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


@app.command()
def doctor():
    """Comprueba instalación y recursos sin red, modelos ni escrituras."""
    typer.echo(json.dumps(inspect_installation(), ensure_ascii=False, indent=2))


@app.command("inspect")
def inspect_command(
    project: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
):
    """Muestra origen registrado, modificaciones y build; no ejecuta pruebas."""
    try:
        typer.echo(json.dumps(inspect_project(project), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, SyntaxError) as exc:
        typer.echo(json.dumps({"status": "error", "code": type(exc).__name__}))
        raise typer.Exit(1) from None


@app.command("install-skill")
def install_skill_command(
    directory: Annotated[
        Path, typer.Option(help="Directorio de habilidades elegido para su asistente")
    ] = Path(".agents/skills"),
):
    """Instala el adaptador de chat sin sobrescribir habilidades existentes."""
    try:
        target = install_skill(directory)
        typer.echo(
            json.dumps(
                {
                    "status": "installed",
                    "path": str(target),
                    "note": "El descubrimiento depende de su asistente; recargue su sesión si hace falta.",
                },
                ensure_ascii=False,
            )
        )
    except (ValueError, OSError) as exc:
        typer.echo(json.dumps({"status": "error", "code": type(exc).__name__}))
        raise typer.Exit(1) from None


@app.command()
def invoke(
    request: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, help="Solicitud JSON explícita")
    ],
    project: Annotated[Path, typer.Option(exists=True, file_okay=False)] = Path("."),
):
    """Ejecuta una operación de dominio en el venv y devuelve su comprobante JSON."""
    try:
        code = run_request(project, request)
    except subprocess.TimeoutExpired:
        typer.echo(
            json.dumps(
                {
                    "status": "unknown",
                    "persisted": None,
                    "code": "timeout",
                    "message": "Consulte el comprobante o reintente la misma solicitud con su operation_id original.",
                }
            )
        )
        raise typer.Exit(2) from None
    except (ValueError, OSError) as exc:
        typer.echo(
            json.dumps(
                {"status": "error", "persisted": False, "code": type(exc).__name__}
            )
        )
        raise typer.Exit(1) from None
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
