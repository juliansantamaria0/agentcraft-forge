# Caso completo: un presupuesto y dos gastos

Este caso prueba el recorrido desde la generación hasta la verificación de datos
guardados. Usa datos sintéticos y el motor determinista de expenses. Las llamadas
a modelos reales siguen pendientes; este caso no mide calidad semántica de un LLM.

Con Python 3.12 y AgentCraft instalado en el entorno que ejecuta el script, desde
el checkout:

```console
python scripts/demo_expenses.py --output .demo-expenses
```

La carpeta elegida debe ser nueva. No se mezclan datos con un proyecto existente.
La instalación usa el flujo build --install y puede necesitar acceso al índice
de paquetes para preparar el entorno. No se necesitan claves de modelos.

## Recorrido y cifras esperadas

| Paso | Resultado comprobado |
| --- | --- |
| Vista previa y generación | Capacidades de gastos, código, suite y manifiesto |
| Instalación e inspección | Entorno propio instalado, origen coincidente y build vigente |
| Mensaje de almuerzo | Propuesta de 15.000 COP para 2026-10-22, sin guardar |
| Consulta inicial | Cero gastos; no crea la carpeta de datos |
| Presupuesto explícito | 100.000 COP para octubre de 2026 |
| Registrar almuerzo | Comprobante confirmado e identificador de registro |
| Repetir la misma operación | Mismo registro y comprobante; no duplica el gasto |
| Registrar transporte | 4.500 COP adicionales; total 19.500 y disponible 80.500 |
| Reutilizar un identificador con otro importe | operation_conflict; saldo conservado |
| Lote con un importe inválido | invalid_integer; no aplica parcialmente el lote |
| Anular el transporte | Conserva historial y deja un solo gasto activo |
| Consulta en un proceso nuevo | Total 15.000 COP; disponible 85.000 COP |

El script consulta también SQLite en modo de solo lectura: deben existir dos
registros, uno activo, uno anulado y cuatro operaciones confirmadas. Los importes
esperados se fijan de forma independiente a los totales que devuelva el motor.

## Evidencia guardada

- CASO_COMPLETO.md: explicación y resultado visible.
- result.json: cifras, decisión, tiempos de evaluación y huellas.
- transcript.json y evidence/: solicitudes de CLI y respuestas reales por paso.
- requests/: JSON explícitos que se enviaron al agente.
- gastos-demo/: proyecto generado, entorno propio y base sintética de la demostración.
- evidence/evaluation.json: evaluación de tres intentos del mismo flujo.

Cada llamada utiliza un proceso nuevo. La suite de evaluación usa carpetas
temporales separadas y el script confirma que ejecutarla no cambia los bytes de
la base de la demostración. La prueba se incorpora a CI en Windows y Ubuntu.

Para evaluar solo el flujo en otro proyecto expenses nuevo:

```console
agentcraft evaluate --project mis-gastos --suite mis-gastos/evals/complete.json --run --report mis-gastos/.agentcraft/complete-01.json
```

La suite conserva estado entre los diez pasos de un intento y lo reinicia entre
sus tres repeticiones. Declara los dos rechazos esperados por su código exacto y
comprueba tanto los estados intermedios como el saldo final y el comprobante.

La salida accepted se limita a esos criterios. Extienda los casos con entradas y
errores representativos de su despliegue antes de usarlos para aceptar otros agentes.
