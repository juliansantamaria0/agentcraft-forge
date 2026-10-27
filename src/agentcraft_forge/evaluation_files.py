"""Reserva antes de ejecutar y publicación de JSON completo sin sobrescritura."""

import json
import os
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path

INPUT_JSON_BYTES = 1_000_000
REPORT_JSON_BYTES = 64_000_000
REVIEW_JSON_BYTES = 16_000_000


class ReportLocked(ValueError):
    pass


class ReportPublicationError(OSError):
    def __init__(self, recovery_path: Path):
        super().__init__(
            "No se publicó el destino; el resultado completo está conservado."
        )
        self.recovery_path = recovery_path


def _linked(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def _publish_without_replacement(source: Path, destination: Path):
    if os.name == "nt":
        # En Windows rename falla si el destino existe; no requiere hardlinks.
        os.rename(source, destination)
    else:
        os.link(source, destination)


class ReportOutput:
    def __init__(self, path: Path, max_bytes: int):
        self.path = path.absolute()
        self.max_bytes = max_bytes
        self.lock_fd = None
        self.temp_path = None
        self.ready = False
        self.published = False

    def reserve(self):
        if any(_linked(p) for p in (self.path, *self.path.parents)):
            raise ValueError("El destino contiene un enlace.")
        if self.path.exists():
            raise FileExistsError("El informe ya existe.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name("." + self.path.name + ".lock")
        if _linked(lock):
            raise ValueError("La reserva está enlazada.")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        self.lock_fd = os.open(lock, flags, 0o600)
        if not stat.S_ISREG(os.fstat(self.lock_fd).st_mode):
            raise ValueError("La reserva debe ser un archivo regular.")
        try:
            if os.fstat(self.lock_fd).st_size == 0:
                os.write(self.lock_fd, b"0")
            os.lseek(self.lock_fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.lock_fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ReportLocked("Otro proceso está escribiendo este informe.") from exc
        # El bloqueo pertenece al SO: cerrar o terminar el proceso lo libera.
        # No se borra el archivo de reserva: borrarlo crearía dos inodos bloqueables.
        if self.path.exists() or any(
            _linked(p) for p in (self.path, *self.path.parents)
        ):
            raise ValueError("El destino dejó de estar disponible.")
        fd, name = tempfile.mkstemp(
            prefix="." + self.path.name + ".",
            suffix=".pending.json",
            dir=self.path.parent,
        )
        os.close(fd)
        self.temp_path = Path(name)
        probe = self.temp_path.with_suffix(".probe")
        # Comprueba antes de facturar que el filesystem permite publicar sin reemplazo.
        _publish_without_replacement(self.temp_path, probe)
        if os.name == "nt":
            os.rename(probe, self.temp_path)
        else:
            probe.unlink()
        return self

    def publish(self, value: dict) -> str:
        serialized = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        content = (serialized + "\n").encode("utf-8")
        if len(content) > self.max_bytes:
            raise ValueError(
                "El informe supera el límite declarado de lectura y escritura."
            )
        with self.temp_path.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        self.ready = True
        try:
            _publish_without_replacement(self.temp_path, self.path)
        except OSError as exc:
            raise ReportPublicationError(self.temp_path) from exc
        self.published = True
        return serialized

    def close(self):
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
        if self.temp_path is not None and (not self.ready or self.published):
            self.temp_path.unlink(missing_ok=True)


@contextmanager
def reserve_report(path: Path | None, *, max_bytes: int = REPORT_JSON_BYTES):
    output = ReportOutput(path, max_bytes) if path is not None else None
    try:
        if output is not None:
            output.reserve()
        yield output
    finally:
        if output is not None:
            output.close()
