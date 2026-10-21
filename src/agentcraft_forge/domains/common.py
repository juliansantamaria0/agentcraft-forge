"""Validación y persistencia comunes, sin dependencias de proveedores."""

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path


class DomainError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now() -> str:
    return datetime.now(UTC).isoformat()


def normalize(text: str) -> str:
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(c)
    )


def fields(value: object, required: set[str], optional: set[str] | None = None) -> dict:
    if (
        not isinstance(value, dict)
        or not required <= value.keys()
        or value.keys() - required - (optional or set())
    ):
        raise DomainError(
            "invalid_request", "Campos ausentes o no admitidos en la solicitud."
        )
    return value


def text(value: object, maximum: int = 1000) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or "\x00" in value
    ):
        raise DomainError("invalid_text", "Texto ausente o fuera de los límites.")
    return value.strip()


def integer(value: object, minimum: int = 1, maximum: int = 1_000_000_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DomainError(
            "invalid_integer", "Se requiere un entero dentro de los límites."
        )
    return value


def iso_date(value: object) -> str:
    value = text(value, 10)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise DomainError(
            "invalid_date", "La fecha debe ser válida y tener formato YYYY-MM-DD."
        ) from exc
    if parsed.isoformat() != value:
        raise DomainError("invalid_date", "Se requiere el formato YYYY-MM-DD.")
    return value


def operation_id(value: object) -> str:
    value = text(value, 128)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{8,128}", value):
        raise DomainError(
            "invalid_operation_id",
            "El identificador de operación debe tener de 8 a 128 caracteres seguros.",
        )
    return value


def safe_path(root: Path, relative: str) -> Path:
    root = root.resolve(strict=True)
    path = root
    for part in Path(relative).parts:
        if part in {"..", "."} or Path(part).is_absolute():
            raise DomainError("unsafe_path", "Ruta fuera del proyecto.")
        path = path / part
        if path.is_symlink():
            raise DomainError(
                "unsafe_path", "No se permiten enlaces en los datos del agente."
            )
    if not path.resolve().is_relative_to(root):
        raise DomainError("unsafe_path", "Ruta fuera del proyecto.")
    return path


def atomic_text(path: Path, content: str) -> None:
    if path.is_symlink():
        raise DomainError("unsafe_path", "Destino enlazado no permitido.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, encoding="utf-8", newline="\n", delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
