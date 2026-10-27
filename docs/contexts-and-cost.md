# Contextos de uso y consumo por mensaje

AgentCraft genera agentes para un contexto definido: propósito, usuarios, datos,
capacidades y criterios de aceptación. El ejemplo de gastos demuestra persistencia;
no limita el producto a asistencia personal ni a aplicaciones financieras.

| Contexto | Base disponible | Qué falta definir en cada proyecto |
| --- | --- | --- |
| Documentación de una empresa | rag | Corpus, permisos, preguntas y respuestas esperadas |
| Material de formación o consulta técnica | rag | Fuentes, límites del contenido y criterios de abstención |
| Seguimiento de compromisos de un equipo | audit | Archivos autorizados, responsable y selección revisada |
| Consultas a servicios externos | tools | Herramientas implementadas y argumentos autorizados en el catálogo |
| Propuestas técnicas con revisión | multi | Requisitos, rúbrica y comparación frente a una sola llamada |
| Registro de gastos de una persona o actividad | expenses | COP, fechas y operaciones explícitas; no es contabilidad general |

Un propósito escrito no añade una integración. Consulte `agentcraft plan` y
`scope.json`; si el contexto requiere otra API o comportamiento, amplíe el catálogo
y sus pruebas. Para adoptar un agente, evalúe su utilidad en ese contexto y su coste
por tarea resuelta, además de los tokens por mensaje.

## Dos consumos diferentes

1. **Asistente anfitrión:** Codex, Claude Code o Antigravity interpreta el chat,
   lee la habilidad y opera archivos y comandos. Sus tokens dependen del cliente,
   modelo, historial y plan del usuario. AgentCraft no recibe automáticamente esa
   facturación ni cambia el modelo del anfitrión.
2. **Agente generado:** expenses y audit operan sin llamar a otro modelo. RAG,
   tools y multi pueden hacer llamadas adicionales al proveedor configurado.
   Son estas llamadas las que mide `usage` en las respuestas del runtime.

`usage` incluye llamadas de chat y embeddings, tokens observados por modelo y
`known`. Si falta telemetría, `known=false`; no equivale a cero. `cost_usd=null`
evita inventar una tarifa y `host_assistant_tokens=null` distingue el consumo del
cliente. La medición se devuelve en respuestas terminadas correctamente; un error
o timeout sin respuesta no demuestra ausencia de consumo. Los intentos HTTP del SDK
no se pueden reconstruir a partir de una respuesta final.

Para estimar dólares en las evaluaciones, declare las tarifas del proveedor con
`--rates`. Los descuentos de caché y la factura oficial quedan fuera de esa estimación.
Los informes detienen intentos nuevos cuando falta uso o tarifa, y comprueban el
presupuesto entre intentos; no son un tope bancario de una petición en curso.

## Ajustes disponibles

| Variable | Predeterminado | Efecto |
| --- | ---: | --- |
| MAX_OUTPUT_TOKENS | 1200 | Límite de salida por llamada; también se aplica a cada rol de multi |
| HISTORY_TURNS | 1 | Turnos previos efímeros enviados; permite 0, 1 o 2 |
| MAX_HISTORY_CHARS | 1200 | Máximo de texto por turno guardado: mitad pregunta, mitad extracto |
| TOP_K | 4 | Máximo de fragmentos RAG recuperados |
| MAX_EVIDENCE_CHARS | 4000 | Máximo de texto de evidencia enviado al modelo |
| PROVIDER_RETRIES | 0 | Reintentos automáticos del proveedor; aumentar puede elevar el consumo |
| EMBEDDING_DIMENSIONS | sin fijar | Dimensión opcional del modelo compatible; exige una colección nueva al cambiarla |

Los límites en caracteres no son contadores de tokens. No se recortan fragmentos
RAG a mitad de texto: si la evidencia recuperada no cabe, el agente se abstiene y
solicita acotar la pregunta o revisar el límite. Reducir contexto puede perjudicar
la respuesta; compruebe preguntas de seguimiento, abstenciones y citas antes de
adoptar una configuración menor. Cada proceso interactivo conserva su propio
historial; una llamada aislada con `--message` no tiene historial previo.

Desde 0.3.3, los seguimientos simples reconocidos (por ejemplo «¿Y qué pasa si se
supera?») combinan la pregunta anterior completa con el mensaje actual para una
sola búsqueda. No utilizan la respuesta del asistente como evidencia ni hacen una
llamada adicional para reformular. Una pregunta independiente utiliza únicamente
su propio texto; un cambio de tema puede expresarse como «Ahora, ¿cuál es ...?».
Una referencia vaga («¿Y eso?»), una pregunta anterior con varios temas, un ancla
truncada o una cadena de seguimientos pide aclaración sin invocar embeddings o chat.
HISTORY_TURNS=0 desactiva también esa referencia al turno anterior. Es una regla
conservadora para patrones concretos, no resolución general de referencias; reformule
con el tema explícito cuando solicite aclaración. La calidad con modelos reales
debe evaluarse también con paráfrasis y conversaciones propias del despliegue.

RAG vectoriza una vez la pregunta y usa ese vector en MMR con umbral de relevancia.
La apertura verifica modelo, clase del proveedor, dimensiones, configuración e
ingestión mediante metadatos, sin vectorizar un texto de prueba en cada consulta.
La ingestión sigue teniendo su coste y se ejecuta explícitamente. No hay caché
persistente de preguntas o respuestas ni se ingiere el corpus automáticamente por
mensaje. Los adaptadores de embeddings personalizados deben declarar un atributo
`model` estable y cambiar su identidad cuando cambie la transformación de vectores.

Las colecciones anteriores sin contrato v2 requieren reingestión en otro nombre de
colección. No se migran ni se borran automáticamente. Actualizar la CLI tampoco
modifica el código ya copiado a agentes existentes: genere un proyecto nuevo y
revise diferencias antes de trasladar personalizaciones y datos.

## Comprobación reproducible del trabajo evitado

Con las dependencias de desarrollo instaladas:

```console
python scripts/measure_rag_retrieval.py --output retrieval-check.json
```

La comparación local con Qdrant real y embeddings simulados reproduce la secuencia
de recuperación de 0.3.1: apertura con prueba dimensional, otra prueba en MMR y dos
vectorizaciones de la pregunta. La secuencia actual usa una sola operación. En esa
fixture son cuatro operaciones frente a una, conservando las dos fuentes recuperadas.
Es una reducción de operaciones, no un 75 % demostrado de ahorro en tokens o dólares.

Para verificar ahorro real, use las mismas tareas y fuentes, repeticiones y modelos;
compare resolución correcta, abstenciones, fidelidad de citas, tokens de entrada y
salida, coste y latencia. Añada el consumo del anfitrión desde su propia telemetría.
No se ha demostrado que multi supere a una sola llamada ni se seleccionan modelos
más baratos automáticamente sin evaluar esa sustitución.

## Menos contexto en el asistente anfitrión

Al abrir un proyecto, cargue su habilidad, alcance y ruta. Mantenga las respuestas
breves y pida únicamente resultado, identificador y siguiente dato necesario.
Consulte el motor para saldos o estado; evite releer todo el código, el manual
completo o el historial en cada mensaje. Reconstruya y ejecute pruebas cuando
cambie el código o el entorno; use los comandos de operación en los mensajes
ordinarios. El ahorro concreto depende de cómo el cliente gestione su contexto.

La documentación principal está en README y docs/. El manual autocontenido es una
instantánea histórica y no debe cargarse como instrucciones en cada interacción.
