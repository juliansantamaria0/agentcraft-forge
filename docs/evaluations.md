# Evaluaciones de agentes generados

Las plantillas v3 incluyen una suite sintética en evals/smoke.json. Preparar una
evaluación funciona sin claves. Ejecutarla usa código del proyecto local, con la
misma confianza necesaria para run: el entorno Python no es una sandbox.

## Preparar sin llamar modelos

```console
agentcraft evaluate --project mi-agente
```

Valida la suite y muestra casos, reglas, huellas y número de intentos. No ejecuta
el agente, no abre proveedores y no genera resultados de calidad. Revise los
casos para su propósito; una suite pequeña de ejemplo no cubre todo un despliegue.
Los proyectos tools nuevos incluyen solo casos compatibles con las herramientas
seleccionadas. Al evaluar una suite previa, se excluyen automáticamente los casos
que requieren capacidades ausentes y se conserva la selección y sus motivos en el
informe. Revise los argumentos de ejemplo si cambia ciudades o repositorios.

Use `--case ID` o `--category capability` (repetibles) para seleccionar casos. Un ID
desconocido, duplicado, incompatible o una selección vacía se rechaza antes de
ejecutar. Una selección parcial no certifica los casos excluidos ni todo el contexto.

## Ejecutar las plantillas deterministas

```console
agentcraft build --project mis-gastos --install
agentcraft evaluate --project mis-gastos --run --report mis-gastos/.agentcraft/eval-01.json
```

expenses y audit usan su motor real con archivos, fechas y solicitudes sintéticas
en una carpeta temporal por intento. Los mensajes solo producen propuestas.
Los casos con requests prueban operaciones y reintentos sobre ese estado temporal.
Los casos de auditoría cubren detección, duplicados y aplicación de una selección
revisada sin modificar los compromisos originales. Adapte estos ejemplos a su flujo
antes de usarlos como puerta de entrega.

## Preparar una ejecución con modelos reales

1. Genere y revise un proyecto nuevo v3; ejecute build --install.
2. Configure localmente OPENAI_API_KEY y los modelos en su entorno o .env. No
   introduzca claves en la suite, las tarifas ni los informes.
3. Cree un JSON con las tarifas vigentes de cada modelo configurado, en USD por
   millón de tokens. CHAT_MODEL y EMBEDDING_MODEL deben coincidir exactamente con
   sus claves; para multi use el valor de CREW_MODEL, incluido su prefijo.
4. Elija un presupuesto y revise los casos antes de activar --live.

Estructura del archivo de tarifas; sustituya los textos por números verificados:

```json
{
  "gpt-4.1-mini": {
    "input_per_million": "INTRODUCIR_TARIFA_NUMERICA",
    "output_per_million": "INTRODUCIR_TARIFA_NUMERICA"
  },
  "text-embedding-3-small": {
    "input_per_million": "INTRODUCIR_TARIFA_NUMERICA",
    "output_per_million": 0
  },
  "openai/gpt-4.1-mini": {
    "input_per_million": "INTRODUCIR_TARIFA_NUMERICA",
    "output_per_million": "INTRODUCIR_TARIFA_NUMERICA"
  }
}
```

No hay precios predeterminados. Ese ejemplo se rechaza hasta introducir números.
El ejecutor comprueba que los modelos configurados tengan tarifa antes de invocarlos.

```console
agentcraft evaluate --project mi-agente --live --rates tarifas.json --max-cost-usd 1 --report mi-agente/.agentcraft/eval-real-01.json
```

El presupuesto es un control entre intentos. Una petición en curso, reintentos del
proveedor o la terminación por timeout pueden generar cargos por encima del límite.
Si falta telemetría o una tarifa, se detiene la suite y el coste total queda
desconocido. Use también los controles de gasto del proveedor.

Antes de ejecutar se reserva el destino del informe con un bloqueo del sistema
operativo y se comprueba la publicación sin sobrescritura. Un proceso terminado
libera el bloqueo; el archivo .lock puede permanecer y no indica por sí solo una
evaluación en curso. Una colisión tardía conserva el JSON completo en la ruta de
recuperación indicada. Los informes admiten hasta 64 MB y las anotaciones 16 MB;
las suites y tarifas conservan su límite de 1 MB.

Consulte [consumo por mensaje](contexts-and-cost.md) para distinguir el runtime del
asistente anfitrión y ajustar historial, evidencia, salida y reintentos.

tools combina el modelo real con respuestas HTTP fijas: clima de 21 °C y viento
de 5 km/h; repositorios con 123 estrellas. El informe declara fixed_http_fixtures.
Esto permite medir decisiones y argumentos de herramientas de forma repetible;
no verifica disponibilidad ni datos actuales de GitHub/Open-Meteo. RAG usa Qdrant
en memoria, corpus sintético y embeddings reales. Su tiempo y coste incluyen la
ingestión nueva por intento. multi usa los tres roles reales de CrewAI.

## Casos, reglas e interpretación

Cada caso tiene un id, categoría, mensaje y checks. Los checks permiten equals,
contains, not_contains, contains_any, exists, min_length y max_value sobre rutas como
request.expenses.0.amount. No ejecutan expresiones ni código. Las comparaciones
de texto no distinguen mayúsculas. equals distingue tipos JSON también dentro de
listas y objetos: true no equivale a 1. contains_any admite variantes de texto
declaradas; exists diferencia un campo ausente de uno presente con null. Se validan
los operandos antes de ejecutar: por ejemplo, min_length exige un entero no negativo.

- documents contiene textos sintéticos para RAG.
- turns permite entre uno y seis mensajes consecutivos en casos RAG de proyectos
  generados con 0.3.3 o posterior. El primer turno coincide con message. El corpus se
  ingiere una vez por intento y el historial se comparte solo dentro de ese caso;
  turn_results conserva respuestas, rutas de recuperación, uso observado y tiempo
  de cada turno. Los checks pueden usar turn_results.1.answer. El coste total del
  intento incluye ingestión; observed_usage por turno excluye esa preparación.
  La revisión humana del caso debe cubrir todos sus turnos.
- files y requests preparan datos y operaciones de dominio. Cada intento parte
  de una carpeta vacía. El último resultado incluye step_results. Un objeto de la forma
  {"$ref": "0.candidates.0.id"} referencia un dato de un resultado previo, para
  seleccionar IDs y comprobantes sin fijar sus hashes en el caso.
- reference_date fija la fecha de interpretación. Las solicitudes explícitas
  declaran sus propias fechas.
- repetitions controla k, de 1 a 10; timeout_seconds limita cada subproceso.
- human_review marca respuestas abiertas que requieren valorar pertinencia,
  fidelidad, abstención y ausencia de afirmaciones de acciones no ejecutadas.
- review_criteria declara los criterios concretos que debe revisar una persona.
- expected_errors asocia el índice de un paso de requests con su código exacto
  de rechazo, por ejemplo {"1": "operation_conflict"}. Otro error o la ausencia
  del rechazo esperado falla el intento. Los errores de infraestructura siguen
  siendo errores de ejecución. Nunca declare esperado un fallo de persistencia
  de estado incierto como sustituto de comprobar el resultado.

Las métricas rule_pass_at_1, rule_pass_at_k y rule_pass_power_k son tasas empíricas:
primer intento correcto, al menos uno correcto entre k, y todos los k correctos.
Los casos sin completar permanecen en el denominador. No son estimadores
estadísticos de una población ni equivalen a calidad semántica. Un texto que
contenga una palabra esperada puede superar una regla y seguir siendo incorrecto.
Las abstenciones en texto libre se juzgan con rúbrica humana, sin exigir una frase
fija de rechazo. Los alias de texto de los casos RAG son variantes previstas; si
aparecen otras formulaciones válidas, revise el grader antes de comparar modelos.

abstention_rule_pass_rate mide las reglas de los casos marcados como abstención;
incluye aclaración y declaración de requisitos faltantes. En tools y multi la
revisión humana es necesaria porque no hay un campo estructurado de abstención.
No se presenta una tasa de abstención semántica certificada. Registre la revisión
humana en un archivo separado, vinculado a la huella de la suite y al informe.

Los tiempos p50/p95 incluyen arranque del proceso, trabajo de herramientas y
preparación del corpus. Los tokens se recogen de callbacks de LangChain, respuestas
de embeddings y CrewOutput.token_usage. Se muestran por modelo en cada intento.
El coste estimado no aplica descuentos por caché ni sustituye la factura. Un error
sin consumo completo conserva usage_known=false y estimated_cost_usd=null.

Los informes contienen mensajes sintéticos y respuestas, nunca la clave del
proveedor. Si adapta los casos con datos personales, el informe también puede
contenerlos. El destino recomendado .agentcraft está excluido de Git. No se
sobrescriben informes existentes. Las revisiones humanas pendientes aparecen
explícitas aunque las reglas pasen; los códigos de salida se detallan a continuación.

## Decisión y revisión humana

Desde 0.3.1, acceptance permite fijar min_rule_pass_rate,
min_abstention_rule_pass_rate, max_error_rate y max_latency_p95_seconds. Los tres
primeros valores predeterminados son 1, 1 y 0; la latencia no tiene un límite
predeterminado. En modo live también se comprueba si el coste estimado final
supera el presupuesto; superarlo impide aceptar la evaluación, aunque la llamada
ya haya consumido ese importe. require_human_review es true por defecto. Si se desactiva, la
decisión queda limitada a las reglas y muestra igualmente las revisiones pendientes.

rule_pass_rate divide los intentos aprobados entre todos los previstos;
rule_pass_rate_by_category desglosa capacidad, abstención y límites. La decisión
quality_gate es not_run, incomplete, failed, review_required o accepted. Accepted
significa que se cumplen los criterios declarados de la suite, no que se certifica
el agente para cualquier tarea. El control del coste sigue siendo entre intentos.

Para revisar un informe ejecutado:

```console
agentcraft review-evaluation --report eval-real.json --output revision.json
```

La plantilla deja reviewer y cada respuesta en null. Lea la respuesta, el mensaje,
los documentos y las observaciones de cada caso en el informe original. Introduzca
su nombre, true/false por criterio y una nota que identifique la evidencia utilizada.
Un criterio sin resolver conserva su respuesta null. No copie aprobaciones de otro
caso ni deduzca calidad semántica por el hecho de que sus reglas hayan pasado.

```console
agentcraft review-evaluation --report eval-real.json --reviews revision.json --output resultado-revision.json
```

La revisión debe corresponder al SHA-256 de los bytes exactos del informe. Se
rechazan criterios cambiados, intentos desconocidos, revisiones repetidas,
aprobaciones sin nombre/nota y respuestas que no sean booleanos o null. No se
modifican el informe original ni la revisión. Es una anotación humana declarada,
no una firma ni una comprobación de identidad. Este flujo usa informes nuevos de
0.3.1, que incluyen política y métricas de decisión.

La CLI devuelve 0 al preparar o satisfacer los criterios, 1 ante configuración
inválida, 2 si hay fallos o ejecución incompleta y **3 si falta revisión humana**.
Un proceso automatizado debe tratar el código 3 como pendiente.

## Caso completo reproducible

Los proyectos expenses nuevos generados desde 0.3.1 añaden evals/complete.json:
un flujo de diez operaciones con quince comprobaciones, repetido tres veces
en estado vacío. El ejemplo de [demostración completa](complete-case.md) utiliza
además la CLI y la instalación real, conserva sus comprobantes y comprueba SQLite
por separado. Las pruebas repetidas de un motor determinista demuestran regresión
y aislamiento del estado, no variabilidad de un modelo.

En esta entrega se validó el evaluador offline. **Las ejecuciones con modelos
reales quedan pendientes por decisión del usuario.** No se publican resultados
simulados como mediciones de un proveedor.

Referencias de las APIs utilizadas: [modelos y metadatos de LangChain](https://docs.langchain.com/oss/python/langchain/models),
[consumo de equipos CrewAI](https://docs.crewai.com/en/concepts/crews) y
[respuesta de embeddings de OpenAI](https://developers.openai.com/api/reference/resources/embeddings/methods/create).
