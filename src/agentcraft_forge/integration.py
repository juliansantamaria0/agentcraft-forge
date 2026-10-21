"""Descubrimiento para asistentes y evidencia local, sin ejecutar el proyecto."""

import hashlib
import json
import sys
from importlib.resources import files
from pathlib import Path, PurePosixPath

from agentcraft_forge import __version__
from agentcraft_forge.generator import render
from agentcraft_forge.planner import design
from agentcraft_forge.project import fingerprint, read_spec, validate
from agentcraft_forge.schema import Kind


def skill_content() -> str:
    return (
        files("agentcraft_forge")
        .joinpath("templates", "chat", "agentcraft.md")
        .read_text(encoding="utf-8")
    )


def install_skill(directory: Path) -> Path:
    directory = directory.absolute()
    for parent in (directory, *directory.parents):
        if parent.is_symlink():
            raise ValueError("El destino de habilidades no puede contener enlaces.")
    target = directory / "agentcraft" / "SKILL.md"
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Destino enlazado no permitido.")
    content = skill_content()
    if target.exists():
        if target.read_text(encoding="utf-8") != content:
            raise FileExistsError(
                "Ya existe una habilidad distinta; revísela antes de sustituirla."
            )
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return target


def doctor() -> dict:
    skill_hash = hashlib.sha256(skill_content().encode()).hexdigest()
    kinds = []
    for kind in Kind:
        resources = render(
            design("resource-check", "Comprobación local de recursos instalados", kind)
        )
        kinds.append({"kind": kind.value, "template_files": len(resources)})
    return {
        "status": "ok",
        "distribution": "agentcraft-forge",
        "version": __version__,
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "templates": kinds,
        "network_used": False,
        "chat_adapter": "agentcraft install-skill --directory RUTA_DE_HABILIDADES",
        "chat_adapter_sha256": skill_hash,
    }


def inspect_project(root: Path) -> dict:
    root = root.resolve(strict=True)
    spec = read_spec(root)
    validation = validate(root)
    path = root / "agentcraft.provenance.json"
    origin = {"status": "legacy_without_provenance"}
    if path.is_file():
        if path.is_symlink() or path.stat().st_size > 100_000:
            raise ValueError("Evidencia enlazada o demasiado grande.")
        evidence = json.loads(path.read_text(encoding="utf-8"))
        spec_hash = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
        original = evidence["original_files"]
        if not isinstance(original, dict) or len(original) > 200:
            raise ValueError("Inventario de origen no válido.")
        changes = []
        for relative, expected_hash in original.items():
            parts = PurePosixPath(relative)
            if parts.is_absolute() or ".." in parts.parts or "\\" in relative:
                raise ValueError("Ruta no válida en la evidencia.")
            candidate = root.joinpath(*parts.parts)
            if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
                raise ValueError("Archivo enlazado en la evidencia.")
            if (
                not candidate.is_file()
                or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected_hash
            ):
                changes.append(relative)
        origin = {
            "status": (
                "matches_recorded_origin"
                if not changes and evidence["spec_sha256"] == spec_hash
                else "modified"
            ),
            "generator": evidence["generator"],
            "generator_version": evidence["generator_version"],
            "changed_original_files": changes,
            "spec_matches": evidence["spec_sha256"] == spec_hash,
            "signed": False,
        }
    state = root / ".agentcraft/build.json"
    fresh = False
    if (
        state.is_file()
        and not state.is_symlink()
        and not state.parent.is_symlink()
        and state.stat().st_size < 100_000
    ):
        fresh = json.loads(state.read_text(encoding="utf-8")).get(
            "fingerprint"
        ) == fingerprint(root)
    return {
        "status": "ok",
        "project": str(root),
        "kind": spec.plan.kind.value,
        "origin": origin,
        "syntax_valid": True,
        "python_files": validation["python_files"],
        "build_fresh": fresh,
        "behavioral_tests": "not_run_by_inspect",
        "model_evaluation": "not_run_by_inspect",
    }
