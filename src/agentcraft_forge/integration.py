"""Descubrimiento para asistentes y evidencia local, sin ejecutar el proyecto."""

import hashlib
import re
import sys
from importlib.resources import files
from pathlib import Path, PurePosixPath

from agentcraft_forge import __version__
from agentcraft_forge.domains.common import fields, parse_json, safe_path
from agentcraft_forge.generator import render
from agentcraft_forge.planner import design
from agentcraft_forge.project import (
    MAX_SOURCE_BYTES,
    read_build_report,
    read_spec,
    source_files,
    validate,
)
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
        evidence = fields(
            parse_json(path.read_text(encoding="utf-8-sig")),
            {
                "schema_version",
                "generator",
                "generator_version",
                "template_version",
                "spec_sha256",
                "original_files",
                "limitations",
            },
        )
        spec_hash = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()
        original = evidence["original_files"]
        if (
            type(evidence["schema_version"]) is not int
            or evidence["schema_version"] != 1
            or evidence["generator"] != "agentcraft-forge"
            or evidence["generator_version"] != spec.generator_version
            or evidence["template_version"] != spec.template_version
            or not isinstance(evidence["spec_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", evidence["spec_sha256"])
            or not isinstance(evidence["limitations"], str)
            or not isinstance(original, dict)
            or not 1 <= len(original) <= 200
            or not {"agentcraft.json", "pyproject.toml", "src/agent_app/runner.py"}
            <= original.keys()
        ):
            raise ValueError("Inventario de origen no válido.")
        changes = []
        for relative, expected_hash in original.items():
            parts = PurePosixPath(relative)
            if (
                parts.is_absolute()
                or ".." in parts.parts
                or "\\" in relative
                or ":" in relative
                or not parts.parts
                or parts.as_posix() != relative
                or not isinstance(expected_hash, str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected_hash)
            ):
                raise ValueError("Ruta no válida en la evidencia.")
            candidate = safe_path(root, relative)
            if (
                not candidate.is_file()
                or candidate.stat().st_size > MAX_SOURCE_BYTES
                or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected_hash
            ):
                changes.append(relative)
        additions = [
            path.relative_to(root).as_posix()
            for path in source_files(root)
            if path.suffix == ".py"
            and path.relative_to(root).as_posix() not in original
        ]
        origin = {
            "status": (
                "matches_recorded_origin"
                if not changes
                and not additions
                and evidence["spec_sha256"] == spec_hash
                else "modified"
            ),
            "generator": evidence["generator"],
            "generator_version": evidence["generator_version"],
            "changed_original_files": changes,
            "added_source_files": additions,
            "spec_matches": evidence["spec_sha256"] == spec_hash,
            "signed": False,
        }
    try:
        report = read_build_report(root)
        build_status = "missing"
        if report is not None:
            fresh = all(
                report[key] == validation[key]
                for key in ("fingerprint", "kind", "python_files")
            )
            build_status = "fresh" if fresh else "stale"
    except (ValueError, OSError):
        build_status = "invalid"
    return {
        "status": "ok",
        "project": str(root),
        "kind": spec.plan.kind.value,
        "origin": origin,
        "syntax_valid": True,
        "python_files": validation["python_files"],
        "build_fresh": build_status == "fresh",
        "build_status": build_status,
        "behavioral_tests": "not_run_by_inspect",
        "model_evaluation": "not_run_by_inspect",
    }
