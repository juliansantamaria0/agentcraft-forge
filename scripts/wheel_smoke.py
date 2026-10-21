"""Verifica recursos desde un wheel instalado, fuera del checkout."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main(python: str) -> None:
    executable = str(Path(python).resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix="agentcraft-wheel-") as directory:
        root = Path(directory)

        def invoke(*args):
            result = subprocess.run(  # noqa: S603 - Intérprete local validado, argumentos fijos, sin shell.
                [executable, "-m", "agentcraft_forge", *args],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=60,
            )
            return result.stdout

        for kind in ("rag", "tools", "multi"):
            invoke(
                "init",
                "--name",
                f"smoke-{kind}",
                "--purpose",
                "Asistente de soporte técnico de demostración",
                "--kind",
                kind,
                "--yes",
            )
            target = root / f"smoke-{kind}"
            invoke("build", "--project", str(target))
            output = invoke("run", "--project", str(target), "--dry-run")
            if json.loads(output)["model_invoked"] is not False:
                raise RuntimeError("El smoke test no debe usar modelos.")
    print("Wheel instalado: tres plantillas, build y run offline correctos.")


if __name__ == "__main__":
    main(sys.argv[1])
