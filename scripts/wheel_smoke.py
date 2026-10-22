"""Verifica recursos desde un wheel instalado, fuera del checkout."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main(python: str) -> None:
    # Conservar la ruta del venv: resolve() seguiría bin/python hasta el Python base.
    executable_path = Path(python).absolute()
    if not executable_path.is_file():
        raise FileNotFoundError("No existe el intérprete del entorno de prueba.")
    executable = str(executable_path)
    with tempfile.TemporaryDirectory(prefix="agentcraft-wheel-") as directory:
        root = Path(directory)

        def invoke(*args):
            result = subprocess.run(  # noqa: S603 - Intérprete local validado, argumentos fijos, sin shell.
                [executable, "-X", "utf8", "-m", "agentcraft_forge", *args],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=60,
            )
            if result.returncode:
                raise RuntimeError(f"La CLI falló en {args!r}: {result.stderr[-2500:]}")
            return result.stdout

        if len(json.loads(invoke("doctor"))["templates"]) != 5:
            raise RuntimeError("Faltan plantillas en la instalación.")
        invoke("install-skill", "--directory", str(root / "skills"))
        if not (root / "skills/agentcraft/SKILL.md").is_file():
            raise RuntimeError("Falta el adaptador de chat.")
        for kind in ("rag", "tools", "multi", "expenses", "audit"):
            invoke(
                "init",
                "--name",
                f"smoke-{kind}",
                "--purpose",
                "Asistente de soporte técnico de demostración",
                "--kind",
                kind,
                "--yes",
                "--json",
            )
            target = root / f"smoke-{kind}"
            preview = json.loads(invoke("evaluate", "--project", str(target)))
            if preview["mode"] != "plan" or preview["model_execution_requested"]:
                raise RuntimeError("Preparar evaluaciones no debe ejecutar modelos.")
            if not (target / "scope.json").is_file() or not preview["suite"]["cases"]:
                raise RuntimeError("Faltan alcance o casos de evaluación en el wheel.")
            if preview["quality_gate"]["decision"] != "not_run":
                raise RuntimeError(
                    "Un plan sin ejecutar no debe tener una decisión de aceptación."
                )
            if kind == "expenses" and not (target / "evals/complete.json").is_file():
                raise RuntimeError("Falta la suite del caso completo de gastos.")
            invoke("build", "--project", str(target))
            output = invoke("run", "--project", str(target), "--dry-run")
            if json.loads(output)["model_invoked"] is not False:
                raise RuntimeError("El smoke test no debe usar modelos.")
            if (
                json.loads(invoke("inspect", "--project", str(target)))["origin"][
                    "status"
                ]
                != "matches_recorded_origin"
            ):
                raise RuntimeError("La evidencia no coincide con el proyecto generado.")
            if kind in {"expenses", "audit"}:
                result = subprocess.run(  # noqa: S603 - Código de prueba generado localmente desde recursos del wheel.
                    [
                        executable,
                        "-X",
                        "utf8",
                        "-I",
                        "-c",
                        "import sys,unittest;sys.path.insert(0,sys.argv[1]);suite=unittest.defaultTestLoader.discover(sys.argv[2],pattern='test_domain.py');r=unittest.TextTestRunner().run(suite);raise SystemExit(not r.wasSuccessful())",
                        str(target / "src"),
                        str(target / "tests"),
                    ],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=60,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError(result.stderr)
    print(
        "Wheel instalado: cinco plantillas, alcance, suites, adaptador, origen y pruebas de dominio correctos."
    )


if __name__ == "__main__":
    main(sys.argv[1])
