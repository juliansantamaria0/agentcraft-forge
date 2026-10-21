# 1. Concepción del meta-agente

Desde 0.2 se incluyen motores de dominio expenses y audit, además de las tres
arquitecturas con modelos. No necesitan una API de IA. El asistente interpreta y
envía solicitudes JSON; el motor valida y confirma escrituras con comprobantes.
Vea [operación por chat](chat-workflow.md) para el contrato completo y sus límites.

## Qué hace el producto

AgentCraft transforma requisitos en un proyecto de software ejecutable. La unidad
de diseño es un `AgentSpec` validado: nombre, propósito, tipo de agente, capacidades,
notas arquitectónicas y límites. El resultado contiene código, configuración,
dependencias, pruebas, Docker y CI. Es un generador con un diseñador de IA opcional.

El modo offline elige entre plantillas mediante reglas simples; no se anuncia como
razonamiento de un LLM. `--ai` usa un modelo configurable para proponer un `Plan`.
Ambos caminos pasan por Pydantic y por el mismo catálogo. La fase de generación es
determinista para una especificación y versión de plantillas dadas.

```text
Requisitos interactivos o flags
  → validación de nombre, longitud y tipo
  → diseñador offline / LLM con salida estructurada
  → Plan validado contra capacidades aprobadas
  → revisión humana del plan, salvo --yes
  → renderizado de recursos incluidos en el wheel
  → carpeta nueva + agentcraft.json
  → build: configuración, sintaxis, archivos y huella
  → instalación explícita en venv del agente
  → run: consulta individual o sesión local
```

## Responsabilidades del orquestador

El diseñador propone arquitectura, herramientas y supuestos. El generador traduce
decisiones a archivos. El validador revisa contratos sin importar el código. El
runtime ejecuta la aplicación local. Separar estas fases evita que un requisito como
«ejecuta este shell» se transforme automáticamente en un comando del generador.

No se permite al diseñador inventar dependencias, rutas o código que después se
ejecute. Una nueva integración debe incorporarse al catálogo, implementarse en la
plantilla, probarse y versionarse. Puede añadirse un futuro diseñador iterativo con
evaluaciones, manteniendo este límite entre propuestas del modelo y capacidades.

## Catálogo inicial

| Arquitectura | Capacidades | Implementación generada |
|---|---|---|
| RAG | search_documents | Qdrant, fragmentación, MMR, filtro de tenant, umbral y citas |
| Tools | repository_info, current_weather | Function calling con registro permitido y APIs fijas |
| Multi | analyze, design, review | Tres tareas CrewAI con contexto explícito |
| Expenses | record_expenses, summarize_expenses, set_budget | SQLite, COP en enteros, presupuestos por mes, anulaciones y comprobantes |
| Audit | scan_commitments, apply_reviewed_commitments | Fuentes con evidencia, revisión, snapshots y aplicación verificada |

El agente RAG es un workflow controlado: recupera evidencia y genera una respuesta.
El agente tools ejecuta un bucle de decisión/acción/observación acotado. El equipo
multiagente divide requisitos, diseño y revisión. No se presupone que más agentes
mejoren calidad; eso debe medirse para cada tarea.

## Datos y configuración

El propósito se guarda en JSON; no se interpola como Python o shell. El nombre
admite minúsculas, dígitos y guiones, y se valida antes de crear una carpeta o enviar
datos al diseñador de IA. Las plantillas proceden de `importlib.resources`; no se
descargan recursos remotos durante `init` ni se usa el directorio de trabajo como
origen de plantillas.

Las claves no se solicitan como flags para evitar el historial de shell. El diseñador
lee `OPENAI_API_KEY` del entorno de la CLI. Los agentes tienen su propio `.env`, leído
con prioridad del entorno. Activar el diseñador envía el propósito al proveedor;
debe usarse con requisitos que esté autorizado a compartir.

## Memoria conversacional

El runtime generado conserva dos turnos recientes por proceso, con extractos acotados
de preguntas y respuestas para contener el contexto. Es memoria efímera, sin guardar
conversación en disco. No constituye una fuente de permisos ni de verdad transaccional.
La consulta actual se limita a 4.000 caracteres y el contexto combinado a 16.000.
Para historiales durables, incorpore almacenamiento por identidad, retención y tests.

## Límites de seguridad y producción

`build` usa compilación sintáctica en memoria; no ejecuta el módulo generado. Su
huella detecta cambios posteriores en configuración y Python, pero no es una firma,
no prueba procedencia ni protege frente a un atacante que modifique también el estado.

`build --install` y `run` ejecutan código y dependencias locales de confianza. El venv
separa paquetes; no es un sandbox del sistema operativo. La herramienta rechaza
destinos existentes y enlaces en sus directorios de estado/entorno, pero no se
pretende resolver carreras con un atacante local concurrente. Los fallos parciales
de escritura se detectan al validar los archivos requeridos.

Una plantilla lista para adaptar no equivale a una aplicación aprobada para cualquier
producción. Antes de promover: identidad autenticada, ACL, límites monetarios,
validación del dominio, observabilidad con redacción, restauración y cancelación del
worker. Las llamadas tienen timeout y límites de pasos; el deadline del loop se
comprueba entre llamadas y no interrumpe de forma estricta una operación síncrona.

Las fuentes recuperadas y las respuestas de APIs son datos no confiables. El control
de herramientas limita el daño incluso cuando un modelo interpreta mal un texto.
No se habilita shell ni escritura remota de forma predeterminada.

