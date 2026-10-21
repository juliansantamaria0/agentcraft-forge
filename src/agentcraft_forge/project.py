"""Validación sin ejecutar código y ejecución explícita en un venv del proyecto."""

import hashlib
import json
import os
import subprocess
import tomllib
import venv
from pathlib import Path

from agentcraft_forge.generator import render
from agentcraft_forge.schema import AgentSpec

MAX_SOURCE_BYTES = 1_000_000


def read_spec(root: Path) -> AgentSpec:
    path = root / "agentcraft.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Falta agentcraft.json o es un enlace simbólico.")
    if path.stat().st_size > 100_000:
        raise ValueError("El manifiesto supera el tamaño permitido.")
    return AgentSpec.model_validate_json(path.read_text(encoding="utf-8"))


def source_files(root: Path) -> list[Path]:
    candidates = [root / "agentcraft.json", root / "pyproject.toml"]
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
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    if metadata["project"]["name"] != spec.name:
        raise ValueError("El nombre de distribución no coincide con agentcraft.json.")
    if metadata["project"]["scripts"] != {"agent": "agent_app.runner:main"}:
        raise ValueError("El entry point del proyecto no coincide con la plantilla.")
    count = 0
    for path in source_files(root):
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
    report = validate(root)
    state_dir = root / ".agentcraft"
    if state_dir.is_symlink() or (root / ".venv").is_symlink():
        raise ValueError("Los directorios de estado y entorno no pueden ser enlaces.")
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
        )
        report["installed"] = True
    state_dir.mkdir(exist_ok=True)
    (state_dir / "build.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def ensure_built(root: Path) -> AgentSpec:
    root = root.resolve(strict=True)
    spec = read_spec(root)
    if (root / ".agentcraft").is_symlink() or (root / ".venv").is_symlink():
        raise ValueError("Estado o entorno enlazados fuera del control del proyecto.")
    report_file = root / ".agentcraft" / "build.json"
    if not report_file.is_file() or report_file.is_symlink():
        raise ValueError("Ejecute agentcraft build antes de run.")
    report = json.loads(report_file.read_text(encoding="utf-8"))
    if report.get("fingerprint") != fingerprint(root):
        raise ValueError("El proyecto cambió: vuelva a ejecutar agentcraft build.")
    return spec


def run_project(root: Path, message: str | None, ingest: Path | None = None) -> int:
    root = root.resolve(strict=True)
    ensure_built(root)
    python = interpreter(root)
    if not python.is_file():
        raise ValueError("Faltan dependencias: ejecute agentcraft build --install.")
    args = [str(python), "-m", "agent_app.runner", "--root", str(root)]
    if message is not None:
        args += ["--message", message]
    if ingest is not None:
        args += ["--ingest", str(ingest.resolve(strict=True))]
    # Sin shell, sin auto-instalación ni evaluación de comandos del manifiesto.
    return subprocess.run(args, cwd=root, check=False, shell=False).returncode
