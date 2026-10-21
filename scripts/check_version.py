"""Valida versión estable declarada sin ejecutar módulos del paquete."""

import ast
import re
import sys
from pathlib import Path


def declared_version(root: Path = Path(".")) -> str:
    source = root / "src/agentcraft_forge/__init__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if not isinstance(value, str):
                raise ValueError("Versión no textual.")
            return value
    raise ValueError("No se encontró __version__.")


def check(version: str) -> None:
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("Formato esperado: MAJOR.MINOR.PATCH sin prefijo v.")
    if version != declared_version():
        raise ValueError("El input no coincide con la versión del commit.")


if __name__ == "__main__":
    check(sys.argv[1])
    print("Versión validada.")
