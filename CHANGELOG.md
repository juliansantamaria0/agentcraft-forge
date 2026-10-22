# Changelog

## 0.3.0 — 2026-10-22

- Vista previa offline con agentcraft plan y alcance exacto antes de confirmar init.
- Catálogo central para capacidades, límites, configuración permitida, recursos y dependencias.
  Las herramientas se generan mediante un registro de fábricas y módulos independientes.
- Plantilla v3 con scope.json y suites sintéticas para las cinco arquitecturas;
  se conserva el contrato de archivos y validación de proyectos v1/v2.
- Evaluador optativo con reglas, huellas, repeticiones, abstenciones, revisión humana,
  tiempos, tokens y costes estimados. Sin ejecución por defecto; los modelos reales
  requieren --live, tarifas por modelo y presupuesto explícitos.
- Casos de dominio en carpetas temporales; herramientas con respuestas HTTP fijas
  declaradas y RAG con corpus sintético/Qdrant en memoria.
- README centrado en una demostración breve; instalación y operación detalladas en docs/usage.md.
- Las evaluaciones con modelos reales quedan preparadas y pendientes de ejecución.

## 0.2.5 — 2026-10-22

- Fechas de gastos escritas y hace N días; referencias temporales no resueltas
  piden aclaración antes de proponer una fecha.
- Auditor con scan_version=3, coincidencias entre candidatos nuevos y rechazo de
  selecciones equivalentes antes de escribir; fuentes conservadas y límite de 500.
- Manifiesto RAG loading/ready con inventario y recuento; consultas bloqueadas para
  cargas incompletas o colecciones antiguas sin comprobante.
- Docker con contexto permitido explícitamente, código en /app y datos escribibles
  en /workspace; los datos personales no se incorporan a la imagen.
- Eventos operativos en stderr con run_id compartido, duración y errores,
  sin registrar contenido privado; stdout conserva los resultados JSON.
- Regresiones sobre agentes generados, pruebas RAG locales y smoke Docker en CI
  y en el flujo de publicación.

## 0.2.4 — 2026-10-22

- Auditoría de JSON multilínea con BOM y extensión .JSON, IDs de mensaje únicos y
  evidencia por línea interna. Encabezados no compatibles no heredan otro remitente.
- Fechas explícitas DD/MM/AAAA, pasado mañana, próximo día semanal y mañana como
  franja horaria. Fechas contradictorias o sin año dudoso conservan la tarea con
  date_warnings y sin vencimiento inventado; se conserva la evidencia de la entrega.
- Negaciones y preguntas reconocidas no se convierten en promesas; «no olvidar»
  sigue siendo un recordatorio. Los diagnósticos sin fecha se agrupan por fuente.
- Lecturas verificadas contra el snapshot y comprobación final antes de publicar.
  Informes limitados a 2 MB y registro actualizado limitado a 1 MB antes de escribir.
- Informes con scan_version=2 e IDs vinculados al formato. Un informe previo de otro
  formato requiere volver a escanear; se conservan los reintentos de operaciones previas.
- Respaldos fieles a los bytes originales, incluidos CRLF y BOM, con before_sha256
  calculado sobre esa misma copia y revalidación del registro antes de preparar cambios.
- Regresiones y pruebas en las copias generadas; formatos inválidos fallan con error
  de dominio sin publicar un informe parcial ni modificar el registro canónico.

## 0.2.3 — 2026-10-21

- Summary y receipt consultan SQLite mediante URI de solo lectura y un snapshot.
  Consultar un proyecto sin datos no crea .data; un comprobante ausente tampoco.
- Las consultas no inicializan ni reparan bases existentes y no solicitan el lock
  de escritura para leer comprobantes. Rutas con espacios, Unicode, # y % verificadas.
- ReAct valida cada respuesta completa antes de ejecutar su lote: rechaza llamadas
  mal formadas e identificadores ausentes, vacíos o repetidos dentro de la sesión.
- Los presupuestos ReAct exigen contadores enteros y tiempo positivo finito; la
  validación ocurre antes de invocar el modelo. Se conservan denegaciones y límites.
- Pruebas sin modelos ni APIs reales para el runtime ReAct, lecturas concurrentes y
  copias generadas. El proyecto de gastos incluye su prueba de consulta sin escritura.

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

