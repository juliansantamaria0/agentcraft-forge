# 2. Implementación de la CLI y los boilerplates

0.2 agrega init --json, doctor, inspect, install-skill e invoke, y los motores
expenses/audit sin proveedor LLM. Las implementaciones de dominio se mantienen en
`src/agentcraft_forge/domains` y se copian al namespace del proyecto generado para
conservar independencia del entorno global. Las pruebas también ejecutan esas copias
desde procesos separados. Vea [el contrato y ejemplos JSON](chat-workflow.md).

## Paquetes y módulos

La distribución es `agentcraft-forge`, el módulo Python es `agentcraft_forge` y el
ejecutable es `agentcraft`. Son nombres distintos con responsabilidades diferentes.
Python 3.12 es la plataforma soportada inicialmente.

| Módulo | Responsabilidad |
|---|---|
| cli.py | Menús Rich y parámetros Typer; composición de fases |
| schema.py | Modelos Pydantic y catálogo por arquitectura |
| planner.py | Reglas locales y adaptador opcional del diseñador LLM |
| generator.py | Carga de recursos, Jinja2 y escritura en carpeta nueva |
| project.py | Validación, fingerprint, venv y ejecución sin shell |
| templates/common | Metadatos, README, variables, Docker, CI y runner |
| templates/runtime | Implementaciones de RAG, herramientas y CrewAI |

Las dependencias pesadas de runtime no son dependencias globales de la CLI. El
extra `ai` añade el adaptador del diseñador. Cada proyecto generado declara solo
los componentes necesarios para su arquitectura. CrewAI no se instala para RAG ni
para un agente de herramientas.

## Comandos implementados

### init

Sin opciones abre un asistente. Pregunta nombre, propósito y tipo, propone un plan
y pide confirmación antes de escribir. `--yes` evita prompts y exige nombre y
propósito. `--kind` puede fijar la arquitectura; si falta, se infiere localmente.
`--ai` cambia el diseñador, manteniendo validación y plantillas.

```console
agentcraft init
agentcraft init --name document-bot --purpose "Consultar documentos autorizados de soporte" --kind rag --yes
```

Una carpeta existente produce error; no hay `--force` que borre o mezcle el trabajo.
La CLI devuelve códigos de salida distintos de cero para errores de validación.
El texto suministrado por el usuario no se interpreta como marcado Rich en el plan.

### build

Valida `agentcraft.json`, campos permitidos, archivos requeridos, nombre de paquete,
entry point y sintaxis de los archivos Python. No importa los módulos. Registra la
huella en `.agentcraft/build.json`, que se excluye de Git. No es una auditoría del
comportamiento ni una compilación a binario.

```console
agentcraft build --project document-bot
agentcraft build --project document-bot --install
```

La segunda variante crea `.venv` e instala el proyecto editable con un proceso
separado de pip, argumentos separados y `shell=False`. Cambiar código exige repetir
build. Una modificación de dependencias exige además repetir `--install`.

### run

Verifica frescura del build. `--dry-run` muestra el plan sin modelo, herramientas ni
instalación. La ejecución real usa el Python de `.venv`, sin instalar automáticamente.

```console
agentcraft run --project document-bot --dry-run
agentcraft run --project document-bot --message "¿Cuál es el plazo de prioridad alta?"
agentcraft run --project document-bot
```

En RAG, `--ingest` carga archivos `.md` y `.txt` antes de preguntar. La ingestión
rechaza colecciones existentes para conservar un flujo de snapshots nuevos y promoción
explícita. Seleccione QDRANT_COLLECTION para cada versión del corpus.

## Estructura de un proyecto generado

```text
document-bot/
├── agentcraft.json
├── pyproject.toml
├── README.md / LICENSE
├── .env.example / .gitignore / .dockerignore
├── Dockerfile
├── .github/workflows/ci.yml
├── src/agent_app/
│   ├── runner.py
│   ├── settings.py
│   ├── providers.py
│   ├── observability.py
│   └── módulos de rag/, tools + react, o multi
├── tests/test_contract.py
└── docs/architecture.md
```

El nombre de distribución cambia por proyecto; el módulo interno `agent_app` y el
entry point `agent` se mantienen en sus propios venvs. Así pueden coexistir varios
agentes sin instalar todos sus comandos en el mismo entorno global.

## Plantilla RAG

El pipeline conserva fuente, revisión SHA-256 y tenant; fragmenta con solapamiento;
genera embeddings y consulta Qdrant. MMR aporta diversidad y una consulta con umbral
filtra candidatos. Ambas consultas llevan el mismo filtro de tenant. El backend
valida IDs de citas y reconstruye su mapa de fuentes, sin confiar en enlaces inventados.
Ausencia de evidencia produce abstención sin llamar al modelo.

El umbral y el tamaño de fragmentos son valores iniciales para calibrar. No se incluye
un reranker ni búsqueda híbrida en esta versión. Dos búsquedas pueden generar trabajo
repetido; si el volumen lo exige, reutilice embeddings y evalúe un flujo equivalente.
Comprobar que una cita existe no prueba soporte semántico de todas las afirmaciones.

## Plantilla con herramientas

Function calling vincula un esquema a cada herramienta. El runtime resuelve el nombre
en su registro, valida argumentos, ejecuta y devuelve un `ToolMessage`. Solo se
permiten repositorios y ciudades definidos en enums; nunca una URL libre.

Los intentos inválidos también cuentan para el presupuesto. Si un modelo solicita
varias llamadas en una respuesta, se verifica el presupuesto total antes de ejecutar.
Los resultados HTTP tienen límite de tamaño, y los errores se convierten en
observaciones acotadas. Los modelos y APIs reales requieren pruebas de integración.

## Plantilla multiagente

CrewAI divide análisis, arquitectura y revisión. Las tareas declaran dependencias
mediante `context`; el proceso es secuencial. El revisor devuelve un esquema Pydantic.
Se desactivan delegación abierta, memoria persistente y ejecución de código.
El límite por agente no equivale a un presupuesto monetario global; ese control
debe incorporarse al gateway del despliegue.

## Extender capacidades

1. Incorporar la capacidad al catálogo del tipo correcto.
2. Implementar su función con esquema, autorización, límites y errores tipados.
3. Registrar la herramienta en el runtime de la plantilla.
4. Añadir dependencias solo a la arquitectura que la usa.
5. Probar argumentos, denegaciones, errores y efectos.
6. Generar un proyecto desde el wheel instalado y ejecutar sus pruebas.

Para escrituras reales, añadir aprobación vinculada a argumentos, precondiciones,
idempotencia y comprobación del recibo. No basta con describir esos controles en el prompt.

## Tests y evidencias

La batería de la CLI verifica los tres boilerplates, el modo interactivo, cancelación,
rutas inválidas, no sobrescritura, inyección de texto, capacidades no aprobadas,
frescura del build y que validar sintaxis no ejecute código. Se usa un diseñador
inyectado para probar el camino de IA sin credenciales.

`wheel_smoke.py` se ejecuta desde un directorio temporal usando el Python donde se
instaló el wheel. Genera los tres tipos, ejecuta build y run offline. Esto detecta
plantillas ausentes que no se verían en una instalación editable.

Los tests básicos generados comprueban contratos e importación. Deben ampliarse con
pruebas de dominio y de herramientas; no equivalen a la batería de la CLI ni a una
evaluación de modelos. Mantenga separados los resultados locales, CI y pruebas reales.

