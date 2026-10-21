# Changelog

## 0.2.2 — 2026-10-21

- Un nuevo build invalida su comprobante anterior antes de validar o instalar. Si
  falla o el código cambia durante la instalación, run exige un nuevo build correcto.
- Comprobantes de build escritos mediante reemplazo atómico y leídos con límite de
  tamaño, JSON estricto y validación de tipos. Se rechazan destinos enlazados.
- Run vuelve a comprobar archivos requeridos y sintaxis, además de la huella del
  proyecto. Inspect distingue build missing, invalid, stale y fresh.
- Inspect detecta Python añadido dentro de src/tests y valida estructura, rutas y
  hashes del inventario de origen; los registros dañados producen errores controlados.
- Inspect conserva su salida JSON ante errores de sintaxis Python o configuración
  TOML de proyecto incorrecta.
- El manifiesto rechaza claves JSON repetidas. Regresiones de instalación fallida,
  escritura interrumpida, metadatos dañados y cambios durante build.

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

