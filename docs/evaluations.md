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
Si un plan tools selecciona solo una herramienta, adapte los casos a esa selección.

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

tools combina el modelo real con respuestas HTTP fijas: clima de 21 °C y viento
de 5 km/h; repositorios con 123 estrellas. El informe declara fixed_http_fixtures.
Esto permite medir decisiones y argumentos de herramientas de forma repetible;
no verifica disponibilidad ni datos actuales de GitHub/Open-Meteo. RAG usa Qdrant
en memoria, corpus sintético y embeddings reales. Su tiempo y coste incluyen la
ingestión nueva por intento. multi usa los tres roles reales de CrewAI.

## Casos, reglas e interpretación

Cada caso tiene un id, categoría, mensaje y checks. Los checks permiten equals,
contains, not_contains, min_length y max_value sobre rutas como
request.expenses.0.amount. No ejecutan expresiones ni código. Las comparaciones
de texto no distinguen mayúsculas. equals distingue tipos JSON.

- documents contiene textos sintéticos para RAG.
- files y requests preparan datos y operaciones de dominio. Cada intento parte
  de una carpeta vacía. El último resultado incluye step_results. Un objeto de la forma
  {"$ref": "0.candidates.0.id"} referencia un dato de un resultado previo, para
  seleccionar IDs y comprobantes sin fijar sus hashes en el caso.
- reference_date fija la fecha de interpretación. Las solicitudes explícitas
  declaran sus propias fechas.
- repetitions controla k, de 1 a 10; timeout_seconds limita cada subproceso.
- human_review marca respuestas abiertas que requieren valorar pertinencia,
  fidelidad, abstención y ausencia de afirmaciones de acciones no ejecutadas.

Las métricas rule_pass_at_1, rule_pass_at_k y rule_pass_power_k son tasas empíricas:
primer intento correcto, al menos uno correcto entre k, y todos los k correctos.
Los casos sin completar permanecen en el denominador. No son estimadores
estadísticos de una población ni equivalen a calidad semántica. Un texto que
contenga una palabra esperada puede superar una regla y seguir siendo incorrecto.

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
sobrescriben informes existentes. La CLI devuelve 2 si hay fallos de reglas o
ejecución incompleta y 1 para una configuración inválida; las revisiones humanas
pendientes aparecen explícitas aunque las reglas pasen.

En esta entrega se validó el evaluador offline. **Las ejecuciones con modelos
reales quedan pendientes por decisión del usuario.** No se publican resultados
simulados como mediciones de un proveedor.

Referencias de las APIs utilizadas: [modelos y metadatos de LangChain](https://docs.langchain.com/oss/python/langchain/models),
[consumo de equipos CrewAI](https://docs.crewai.com/en/concepts/crews) y
[respuesta de embeddings de OpenAI](https://developers.openai.com/api/reference/resources/embeddings/methods/create).
