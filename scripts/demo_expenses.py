"""Demostración reproducible con CLI instalada, venv real y datos sintéticos."""

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path


def save(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def require(condition, message):
    if not condition:
        raise ValueError(message)


def demonstrate(output: Path, python: Path) -> dict:
    python = python.absolute()
    require(python.is_file(), "No existe el intérprete elegido.")
    # Un caso nuevo nunca se mezcla con datos existentes.
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence"
    inputs = output / "requests"
    evidence.mkdir()
    inputs.mkdir()
    project = output / "gastos-demo"
    transcript = []

    def invoke(label, *args, expected_code=0):
        started = time.monotonic()
        result = subprocess.run(  # noqa: S603 - CLI local explícita, argumentos separados, sin shell.
            [str(python), "-X", "utf8", "-m", "agentcraft_forge", *map(str, args)],
            cwd=output,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
            check=False,
        )
        require(
            result.returncode == expected_code,
            f"Falló el paso {label}; código {result.returncode}.",
        )
        response = json.loads(result.stdout)
        entry = {
            "step": len(transcript) + 1,
            "label": label,
            "arguments": list(map(str, args)),
            "exit_code": result.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "response": response,
        }
        transcript.append(entry)
        save(evidence / f"{len(transcript):02}-{label}.json", entry)
        save(output / "transcript.json", transcript)
        print(f"Verificado: {label}", flush=True)
        return response

    def request(label, value, expected_code=0):
        path = inputs / (label + ".json")
        save(path, value)
        return invoke(
            label,
            "invoke",
            "--project",
            project,
            "--request",
            path,
            expected_code=expected_code,
        )

    def summary(label):
        return request(label, {"action": "summary", "month": "2026-10"})

    purpose = "Registrar gastos personales en COP y comprobar presupuestos con solicitudes explícitas"
    invoke(
        "scope",
        "plan",
        "--name",
        "gastos-demo",
        "--purpose",
        purpose,
        "--kind",
        "expenses",
    )
    invoke(
        "generate",
        "init",
        "--name",
        "gastos-demo",
        "--purpose",
        purpose,
        "--kind",
        "expenses",
        "--yes",
        "--json",
    )
    installed = invoke("build-install", "build", "--project", project, "--install")
    require(
        installed["installed"] is True, "No se confirmó la instalación del proyecto."
    )
    origin = invoke("inspect", "inspect", "--project", project)
    require(
        origin["origin"]["status"] == "matches_recorded_origin"
        and origin["build_fresh"],
        "El origen o build no coincide.",
    )
    proposal = invoke(
        "proposal",
        "run",
        "--project",
        project,
        "--message",
        "Gasté 15k en almuerzo el 22 de octubre de 2026",
    )
    require(
        proposal["status"] == "proposal" and proposal["persisted"] is False,
        "El mensaje debe producir una propuesta.",
    )
    require(
        proposal["request"]["expenses"][0]["amount"] == 15000,
        "Importe de la propuesta incorrecto.",
    )
    empty = summary("empty-state")
    require(
        empty["count"] == 0
        and empty["total"] == 0
        and not (project / ".data").exists(),
        "Proponer o consultar creó datos persistentes.",
    )
    budget = request(
        "budget",
        {
            "action": "set_budget",
            "operation_id": "demo-budget-0001",
            "month": "2026-10",
            "amount": 100000,
            "currency": "COP",
        },
    )
    require(budget["persisted"] is True, "No se confirmó el presupuesto.")
    record_request = {**proposal["request"], "operation_id": "demo-lunch-0001"}
    first = request("record-lunch", record_request)
    require(
        first["status"] == "committed" and first["persisted"] is True,
        "El registro no está confirmado.",
    )
    replay = request("retry-lunch", record_request)
    require(
        replay["replayed"] is True and replay["record_ids"] == first["record_ids"],
        "El reintento no conservó su comprobante.",
    )
    transport_request = {
        "action": "record",
        "operation_id": "demo-transport-0001",
        "currency": "COP",
        "expenses": [
            {"amount": 4500, "description": "Transporte", "expense_date": "2026-10-22"}
        ],
    }
    transport = request("record-transport", transport_request)
    before = summary("before-correction")
    require(
        (before["count"], before["total"], before["remaining_budget"])
        == (2, 19500, 80500),
        "Saldo inicial inesperado.",
    )
    conflict_request = {
        **record_request,
        "expenses": [{**record_request["expenses"][0], "amount": 99999}],
    }
    conflict = request("conflicting-id", conflict_request, expected_code=1)
    require(
        conflict["code"] == "operation_conflict" and conflict["persisted"] is False,
        "No se rechazó el conflicto exacto.",
    )
    invalid_request = {
        **transport_request,
        "operation_id": "demo-invalid-0001",
        "expenses": [
            transport_request["expenses"][0],
            {
                "amount": 0,
                "description": "Entrada inválida",
                "expense_date": "2026-10-22",
            },
        ],
    }
    invalid = request("invalid-batch", invalid_request, expected_code=1)
    require(
        invalid["code"] == "invalid_integer" and invalid["persisted"] is False,
        "No se rechazó el lote inválido.",
    )
    unchanged = summary("after-rejections")
    require(
        (unchanged["count"], unchanged["total"], unchanged["remaining_budget"])
        == (2, 19500, 80500),
        "Un rechazo alteró el saldo.",
    )
    correction = request(
        "void-transport",
        {
            "action": "void",
            "operation_id": "demo-void-0001",
            "expense_ids": transport["record_ids"],
            "reason": "Transporte añadido por error en esta demostración sintética",
        },
    )
    require(correction["persisted"] is True, "No se confirmó la corrección.")
    final = summary("final-balance")
    require(
        (final["count"], final["total"], final["remaining_budget"])
        == (1, 15000, 85000),
        "Saldo final inesperado.",
    )
    receipt = request(
        "historical-receipt",
        {"action": "receipt", "operation_id": record_request["operation_id"]},
    )
    require(
        receipt["record_ids"] == first["record_ids"] and receipt["replayed"] is True,
        "No se recuperó el comprobante histórico.",
    )
    database = project / ".data/expenses-v1.sqlite3"
    digest_before = hashlib.sha256(database.read_bytes()).hexdigest()
    evaluation = invoke(
        "complete-evaluation",
        "evaluate",
        "--project",
        project,
        "--suite",
        project / "evals/complete.json",
        "--run",
        "--report",
        evidence / "evaluation.json",
    )
    require(
        evaluation["quality_gate"]["decision"] == "accepted"
        and evaluation["metrics"]["completed_trials"] == 3,
        "La evaluación completa no superó sus criterios.",
    )
    require(
        hashlib.sha256(database.read_bytes()).hexdigest() == digest_before,
        "Evaluar cambió la base de la demostración.",
    )
    reopened = summary("new-process-balance")
    require(
        (reopened["count"], reopened["total"], reopened["remaining_budget"])
        == (1, 15000, 85000),
        "No se conservó el saldo al abrir otro proceso.",
    )
    with closing(
        sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    ) as connection:
        stored, active, voided, active_total = connection.execute(
            "SELECT COUNT(*),SUM(voided_by IS NULL),SUM(voided_by IS NOT NULL),SUM(CASE WHEN voided_by IS NULL THEN amount ELSE 0 END) FROM expenses"
        ).fetchone()
        operations = connection.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        stored_budget = connection.execute(
            "SELECT amount FROM budgets WHERE month = ?", ("2026-10",)
        ).fetchone()[0]
    require(
        (stored, active, voided, operations) == (2, 1, 1, 4),
        "El estado de SQLite no coincide con los comprobantes.",
    )
    require(
        (active_total, stored_budget, stored_budget - active_total)
        == (15000, 100000, 85000),
        "Los importes almacenados no coinciden con el resultado esperado.",
    )
    result = {
        "status": "verified",
        "synthetic_data": True,
        "live_models_executed": False,
        "project": str(project),
        "steps": len(transcript),
        "initial_budget_cop": 100000,
        "before_correction": {"count": 2, "total_cop": 19500, "remaining_cop": 80500},
        "final": {"count": 1, "total_cop": 15000, "remaining_cop": 85000},
        "sqlite": {
            "stored_records": stored,
            "active_records": active,
            "voided_records": voided,
            "operations": operations,
            "active_total_cop": active_total,
            "budget_cop": stored_budget,
            "remaining_cop": stored_budget - active_total,
        },
        "evaluation": evaluation["metrics"],
        "quality_gate": evaluation["quality_gate"],
        "transcript_sha256": hashlib.sha256(
            (output / "transcript.json").read_bytes()
        ).hexdigest(),
        "database_sha256": digest_before,
    }
    save(output / "result.json", result)
    report = f"""# Un caso completo: gastos y presupuesto

**Resultado verificado con datos sintéticos.** Se generó e instaló un proyecto nuevo;
cada operación se ejecutó mediante la CLI en un proceso separado y su entorno propio.
Esta demostración usa el motor determinista de gastos y no llama modelos reales.

| Momento | Gastos activos | Total COP | Disponible COP |
| --- | ---: | ---: | ---: |
| Presupuesto inicial | 0 | 0 | 100.000 |
| Almuerzo y transporte | 2 | 19.500 | 80.500 |
| Reintento y solicitudes rechazadas | 2 | 19.500 | 80.500 |
| Tras anular el transporte | 1 | 15.000 | 85.000 |
| Consulta en otro proceso | 1 | 15.000 | 85.000 |

La petición «Gasté 15k en almuerzo el 22 de octubre de 2026» produjo una propuesta
sin escribir. Después se envió la solicitud explícita y se obtuvo un comprobante.
El reintento recuperó el mismo registro. Un identificador reutilizado con otro
importe y un lote con importe cero se rechazaron sin alterar el saldo.

La anulación conservó el historial: SQLite contiene dos registros, uno activo y
uno anulado, con cuatro operaciones confirmadas. El saldo final se leyó de nuevo
desde otro proceso y se contrastó directamente con SQLite en modo de solo lectura.

## Evaluación del mismo flujo

La suite completa se ejecutó tres veces en carpetas temporales nuevas: tres de tres
intentos correctos, con sus quince reglas por intento. La evaluación dejó intacta
la base de la demostración. Decisión: **{evaluation['quality_gate']['decision']}**
para los criterios declarados; no certifica otras tareas ni el comportamiento de un LLM.

Se verificaron {len(transcript)} pasos. Los tiempos incluyen arranque de procesos.
No hay coste de tokens en este caso determinista. La evaluación semántica de los
agentes con modelos sigue pendiente.

- [Resultado resumido y huellas](result.json)
- [Transcripción de operaciones y respuestas](transcript.json)
- [Informe de evaluación](evidence/evaluation.json)
- [Suite reproducible](gastos-demo/evals/complete.json)

Para repetirlo en otra carpeta nueva, desde el repositorio instalado:

```console
python scripts/demo_expenses.py --output otra-demostracion
```
"""
    (output / "CASO_COMPLETO.md").write_text(report, encoding="utf-8", newline="\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Carpeta nueva para el caso y sus comprobantes",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Intérprete con AgentCraft instalado",
    )
    args = parser.parse_args()
    result = demonstrate(args.output, args.python)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
