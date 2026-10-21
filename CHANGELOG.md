# Changelog

## 0.2.1 — 2026-10-21

- Resúmenes con fechas, meses explícitos y mes anterior sin sustituirlos por el mes
  actual. Los presupuestos conservan el mes solicitado; un mes sin año pide aclaración.
- Las peticiones mixtas de registro y resumen y los lotes con conceptos sin precio
  piden aclaración en vez de omitir parte del mensaje.
- Los resúmenes SQLite comparten una transacción de lectura para mantener coherencia
  entre movimientos, recuento, categorías y saldo ante escrituras concurrentes.
- JSON estricto en solicitudes y fuentes JSON de auditoría: rechaza claves duplicadas,
  NaN, Infinity, sintaxis inválida y anidación excesiva antes de ejecutar el motor.
- La auditoría no trata negaciones, preguntas ni intenciones futuras reconocidas como
  evidencia de progreso. La sesión interactiva continúa tras un mensaje no válido.
- Rechazo portable de nombres de proyecto reservados en Windows antes de llamar al
  diseñador o crear archivos. Pruebas de regresión y documentación actualizadas.

## 0.2.0 — 2026-10-21

- Adaptador de chat instalable explícitamente, init --json, doctor e inspect.
- Evidencia de origen local y habilidad por proyecto; lectura de proyectos v1 sin
  atribuirles evidencia inexistente.
- Plantilla expenses sin API: importes enteros COP, presupuestos mensuales,
  transacciones, anulaciones e idempotencia con comprobantes persistidos.
- Plantilla audit: identidad declarada, fechas y fuentes, dos formatos WhatsApp,
  revisión de progreso, snapshots y aplicación con backup y recuperación.
- Propuestas separadas de escrituras; errores de resultado incierto no afirman que
  no se haya guardado una operación.
- Pruebas basadas en los casos de la revisión, persistencia entre procesos y smoke
  desde el wheel instalado para cinco plantillas.


## 0.1.0

- CLI Typer/Rich: init interactivo, build y run.
- Diseñador offline y planificador LLM opcional.
- Plantillas RAG, herramientas ReAct y CrewAI.
- Validación declarativa, sintaxis y frescura del build.
- Empaquetado setuptools y workflow de publicación con OIDC.

