"""Validación sin ejecutar código y ejecución explícita en un venv del proyecto."""

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
import venv
from pathlib import Path

from agentcraft_forge.domains.common import atomic_text, fields, parse_json, safe_path
from agentcraft_forge.generator import render
from agentcraft_forge.schema import AgentSpec, Kind

MAX_SOURCE_BYTES = 1_000_000


def read_spec(root: Path) -> AgentSpec:
    path = root / "agentcraft.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Falta agentcraft.json o es un enlace simbólico.")
    if path.stat().st_size > 100_000:
        raise ValueError("El manifiesto supera el tamaño permitido.")
    return AgentSpec.model_validate(parse_json(path.read_text(encoding="utf-8-sig")))


def source_files(root: Path) -> list[Path]:
    candidates = [root / "agentcraft.json", root / "pyproject.toml"]
    for relative in (
        "agentcraft.provenance.json",
        ".agents/skills/agentcraft-project/SKILL.md",
    ):
        if (root / relative).exists():
            candidates.append(root / relative)
    for directory in (root / "src", root / "tests"):
        candidates.extend(directory.rglob("*.py"))
    if len(candidates) > 200:
        raise ValueError("Demasiados archivos para el validador de esta versión.")
    for path in candidates:
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("No se permiten fuentes enlazadas fuera del proyecto.")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise ValueError("Un archivo de código supera 1 MB.")
    return sorted(candidates)


def fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in source_files(root):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def interpreter(root: Path) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def validate(root: Path) -> dict:
    root = root.resolve(strict=True)
    spec = read_spec(root)
    expected = render(spec)
    for relative in expected:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Archivo requerido ausente o enlazado: {relative}")
    sources = source_files(root)
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package = metadata.get("project")
    if not isinstance(package, dict):
        raise ValueError("Falta una tabla [project] válida en pyproject.toml.")
    if package.get("name") != spec.name:
        raise ValueError("El nombre de distribución no coincide con agentcraft.json.")
    if package.get("scripts") != {"agent": "agent_app.runner:main"}:
        raise ValueError("El entry point del proyecto no coincide con la plantilla.")
    count = 0
    for path in sources:
        if path.suffix == ".py":
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
            count += 1
    return {
        "schema_version": 1,
        "kind": spec.plan.kind.value,
        "python_files": count,
        "fingerprint": fingerprint(root),
        "installed": False,
    }


def build(root: Path, install: bool = False) -> dict:
    root = root.resolve(strict=True)
    state_file = safe_path(root, ".agentcraft/build.json")
    if (root / ".venv").is_symlink():
        raise ValueError("Los directorios de estado y entorno no pueden ser enlaces.")
    # Un intento fallido nunca debe dejar vigente un comprobante anterior.
    state_file.unlink(missing_ok=True)
    report = validate(root)
    if install:
        # Una instalación ejecuta el backend de empaquetado: solo proyectos fiables.
        if not interpreter(root).is_file():
            venv.EnvBuilder(with_pip=True).create(root / ".venv")
        subprocess.run(
            [
                str(interpreter(root)),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--cache-dir",
                str(root / ".agentcraft" / "pip-cache"),
                "-e",
                str(root),
            ],
            cwd=root,
            check=True,
            timeout=600,
            shell=False,
            stdout=sys.stderr,
        )
        report["installed"] = True
    if validate(root)["fingerprint"] != report["fingerprint"]:
        raise ValueError(
            "El proyecto cambió durante build; revise y vuelva a compilar."
        )
    atomic_text(state_file, json.dumps(report, indent=2))
    return report


def read_build_report(root: Path) -> dict | None:
    """Lee el comprobante limitado y tipado; None significa que no existe."""
    try:
        path = safe_path(root, ".agentcraft/build.json")
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > 100_000:
            raise ValueError("Tamaño o tipo no admitido.")
        report = fields(
            parse_json(path.read_text(encoding="utf-8-sig")),
            {
                "schema_version",
                "kind",
                "python_files",
                "fingerprint",
                "installed",
            },
        )
        if (
            type(report["schema_version"]) is not int
            or report["schema_version"] != 1
            or report["kind"] not in [kind.value for kind in Kind]
            or type(report["python_files"]) is not int
            or not 1 <= report["python_files"] <= 200
            or type(report["installed"]) is not bool
            or not isinstance(report["fingerprint"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", report["fingerprint"])
        ):
            raise ValueError("Campos no válidos.")
        return report
    except ValueError as exc:
        raise ValueError(
            "Comprobante de build inválido; ejecute agentcraft build de nuevo."
        ) from exc


def ensure_built(root: Path) -> AgentSpec:
    root = root.resolve(strict=True)
    spec = read_spec(root)
    if (root / ".agentcraft").is_symlink() or (root / ".venv").is_symlink():
        raise ValueError("Estado o entorno enlazados fuera del control del proyecto.")
    report = read_build_report(root)
    if report is None:
        raise ValueError("Ejecute agentcraft build antes de run.")
    current = validate(root)
    if any(
        report[key] != current[key] for key in ("kind", "fingerprint", "python_files")
    ):
        raise ValueError("El proyecto cambió: vuelva a ejecutar agentcraft build.")
    return spec


def run_project(root: Path, message: str | None, ingest: Path | None = None) -> int:
    root = root.resolve(strict=True)
    ensure_built(root)
    python = interpreter(root)
    if not python.is_file():
        raise ValueError("Faltan dependencias: ejecute agentcraft build --install.")
    args = [str(python), "-X", "utf8", "-m", "agent_app.runner", "--root", str(root)]
    if message is not None:
        args += ["--message", message]
    if ingest is not None:
        args += ["--ingest", str(ingest.resolve(strict=True))]
    # Sin shell, sin auto-instalación ni evaluación de comandos del manifiesto.
    return subprocess.run(args, cwd=root, check=False, shell=False).returncode


def run_request(root: Path, request: Path) -> int:
    root = root.resolve(strict=True)
    spec = ensure_built(root)
    if spec.plan.kind.value not in {"expenses", "audit"}:
        raise ValueError("invoke solo se admite para expenses y audit.")
    request = request.absolute()
    if request.is_symlink() or not request.is_file() or request.stat().st_size > 64_000:
        raise ValueError("La solicitud debe ser un archivo JSON local de hasta 64 KB.")
    parse_json(request.read_text(encoding="utf-8-sig"))
    python = interpreter(root)
    if not python.is_file():
        raise ValueError("Ejecute build --install para preparar el runtime.")
    return subprocess.run(
        [
            str(python),
            "-X",
            "utf8",
            "-m",
            "agent_app.runner",
            "--root",
            str(root),
            "--request",
            str(request),
        ],
        cwd=root,
        shell=False,
        check=False,
        timeout=120,
    ).returncode
