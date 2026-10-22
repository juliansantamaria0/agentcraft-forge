# Evidencia de validación — 0.3.0

Fecha: 22 de octubre de 2026. Windows, Python 3.12.14.

- 275 pruebas correctas; 90 % de cobertura de la fuente. Las pruebas bloquean la red
  en el proceso de pytest. Los procesos de dominio usan datos sintéticos y no necesitan red.
- 32 pruebas añadidas para catálogo, alcance, compatibilidad, suites, reglas,
  presupuestos, consumo desconocido, callbacks, metadatos de embeddings, CrewAI
  simulado y protocolo del evaluador en procesos separados.
- Los cinco proyectos generados pasan Ruff y sus 14 pruebas de contrato/dominio.
- Se comprueba la ejecución de las suites de gastos y auditoría, incluidas operaciones,
  reintentos y selección revisada, en carpetas temporales.
- Black verifica 30 archivos de fuente, scripts y pruebas; Ruff sin incidencias.
- uv.lock permanece vigente: comprobación offline con Python 3.12 y 97 paquetes.
- El smoke del wheel comprueba las cinco suites, sus recursos, alcance y preparación
  sin modelos desde una instalación fuera del checkout.

Las pruebas de medición usan respuestas de proveedor simuladas. **No se ejecutaron
modelos reales**: las mediciones de exactitud semántica, coste y latencia con un
proveedor quedan pendientes por decisión del usuario. El coste es una estimación
a partir de tarifas explícitas, y el control de presupuesto opera entre intentos.

La revisión humana de respuestas abiertas sigue pendiente incluso si sus reglas
automáticas pasan. El uso de fixtures HTTP en tools no verifica los servicios reales.
La carpeta temporal de los casos no es una sandbox para código local no fiable.

La comprobación Docker local sigue limitada por el motor Linux inactivo. La CI
mantiene su prueba Docker y sus jobs Windows/Linux; consulte Actions para el commit
que vaya a instalar. Esta preparación no crea tags, releases ni publicaciones PyPI.

# Evidencia histórica — 0.2.5

Fecha: 22 de octubre de 2026. Windows, Python 3.12.14.

- 243 pruebas correctas en un entorno nuevo instalado desde uv.lock, con todos los
  extras y el grupo dev. La fixture mantiene bloqueadas las conexiones de los tests.
- 90 % de cobertura de sentencias en fuente de la CLI y motores de dominio; los
  runtimes generados se prueban por comportamiento y no forman parte de ese porcentaje.
- Ruff correcto en fuente, scripts y pruebas. Black verifica 27 archivos.
- Nuevas regresiones de fechas, candidatos equivalentes y tareas recurrentes;
  manifiesto RAG loading/ready, interrupciones entre lotes y al finalizar, inventario
  incorrecto, pérdida de fragmentos, separación por tenant y colecciones heredadas.
- Los runtimes generados comprueban eventos de modelos y herramientas, errores,
  run_id compartido y ausencia de preguntas o resultados privados en stderr.
- Se han construido wheel y sdist y se ha comprobado una instalación aislada del
  wheel fuera del checkout. Las pruebas de dominio generadas incluyen las regresiones
  de fechas y candidatos equivalentes.

Docker no se ejecutó localmente porque el motor Linux de Docker Desktop no estaba
disponible. El cambio de contexto y permisos tiene revisión estática y pruebas de
las plantillas; scripts/docker_smoke.py ejecuta la comprobación real en el nuevo job
Linux de CI y en publicación. Consulte Actions para el resultado del commit publicado.

Estas comprobaciones corresponden a la preparación local de la versión. No se han
creado tags, releases o publicaciones PyPI. No se usaron modelos reales ni datos personales.
Al incorporar los cambios a un agente existente, siga docs/stabilization-0.2.5.md.

## Evidencia histórica — 0.2.4

Fecha: 22 de octubre de 2026. Plataforma local: Windows, Python 3.12.14.

| Comprobación | Resultado |
|---|---|
| pytest, red bloqueada por fixture | 206 pruebas correctas con todos los extras |
| Cobertura de sentencias | 90 %; incluye los motores de dominio en su fuente, no las copias generadas como código instrumentado |
| Ruff | Correcto en fuente, scripts y pruebas |
| Black | 23 archivos de fuente, scripts y pruebas formateados |
| Plantillas generadas | RAG, herramientas, multiagente, gastos y auditoría generan Python válido |
| Instalación del wheel con pipx | Correcta en un PIPX_HOME temporal, sin cambiar el PATH global del usuario |
| Smoke del wheel fuera del checkout | Cinco tipos pasan init, build, inspect y run --dry-run; adaptador y dos pruebas de dominio correctos |
| build --install desde el wheel instalado | Crea venvs e instala los proyectos expenses y audit correctamente |
| invoke y persistencia entre procesos | Seis gastos sintéticos, total y saldo mensual consistentes |
| Reintentos y conflictos | Misma operación no duplica; argumentos distintos con el mismo ID se rechazan |
| Auditoría de dominio | Tres candidatos con fuentes, progreso reciente revisado, aplicación con backup y reintento sin duplicados |
| Pruebas incluidas en los proyectos generados | unittest de expenses y audit correctos en sus propios venvs |
| Compatibilidad verificada en 0.2.2 contra proyecto 0.2.1 | Inspect y propuesta correctos; hashes del código, manifiesto y base de datos sin cambios |

La batería prueba validación, menú interactivo, cancelación, generación de las cinco
arquitecturas, recursos instalados, no sobrescritura, tratamiento del propósito como
datos, permisos del catálogo, sintaxis sin ejecución, frescura y JSON de salida largo.
El camino del diseñador se prueba con un sustituto inyectado; no es una evaluación
del proveedor real. La instalación del runtime se prueba por separado del conjunto
unitario, que no debe necesitar credenciales ni acceso de red.

Desde 0.2 se añaden las dos plantillas de dominio, importes y fechas ambiguas,
presupuestos por mes, paginación sin alterar totales, anulaciones atómicas, responsable
declarado, dos formatos de export WhatsApp, snapshots y recuperación del comprobante
tras una interrupción posterior a la escritura. Los recibos describen el resultado
histórico de una operación; una consulta nueva obtiene el estado actual.

La versión 0.2.1 añade regresiones de periodos explícitos y relativos, cambio de año,
solicitudes mixtas, conceptos sin precio, progreso negado/interrogado/futuro y nombres
reservados de Windows. Los procesos del runtime generado prueban el rechazo de JSON
ambiguo sin crear SQLite y la continuidad del chat tras un mensaje inválido.
Una prueba intercala el commit de otro escritor en modo WAL entre las consultas de
un resumen y verifica que filas, recuento y categorías conserven el mismo snapshot.

La versión 0.2.2 añade 27 casos de estado del proyecto: instalación fallida, escritura
interrumpida, modificación durante build, archivos requeridos ausentes, JSON y tipos
inválidos, destinos declarados como enlaces y recuperación mediante un nuevo build.
Comprueba el rechazo de inventarios de origen mal formados y la detección de nuevas
fuentes Python. Los fallos de instalación se inyectan sin ejecutar pip dentro de la suite;
el camino de instalación real se comprueba por separado desde el paquete instalado.
Inspect también conserva su respuesta JSON ante Python inválido o una tabla project
de tipo incorrecto en pyproject.toml.

La versión 0.2.3 añade 21 casos: cinco de consultas de gastos sin escritura y dieciséis
del runtime ReAct con modelo y herramientas simulados. Se verifica el rechazo del lote
antes de cualquier herramienta ante llamadas mal formadas, IDs inválidos o presupuesto
insuficiente, y que un ID reutilizado no repita la llamada en un turno posterior.
Se comprueban denegaciones, plazo expirado y conservación de observaciones válidas.
La cobertura indicada instrumenta fuente de la CLI y de los motores de dominio;
la plantilla ReAct .tmpl se prueba por comportamiento y no figura en ese porcentaje.
La consulta de comprobantes se prueba con otro escritor que mantiene cambios sin
confirmar, y el resumen de una copia generada no crea una base al consultar sin datos.

La versión 0.2.4 añade 36 casos del auditor: UTF-8/BOM, JSON multilínea y extensión
mayúscula, IDs únicos, preguntas y negaciones, fechas explícitas/relativas, advertencias
de vencimiento, coherencia del snapshot y versionado de informes. Se comprueban límites
antes de guardar el informe o ampliar el registro, y el rechazo de encabezados que
podrían heredar un remitente incorrecto. Las pruebas de dominio generadas también
incluyen un encargo JSON multilínea con BOM y evidencia por línea interna.
Los respaldos se comparan byte a byte con archivos CRLF, con y sin BOM, y con la
huella before_sha256 del comprobante.

El flujo completo se verificó con datos sintéticos en una carpeta de work, desde la
CLI instalada con pipx y procesos separados. No se importó ni modificó prueba.zip,
su gastos.db ni los datos originales del dispositivo de prueba del usuario.

Los tests locales usan un basetemp dentro del workspace por las restricciones del
directorio temporal del entorno de ejecución. Esta configuración no cambia el código.

## Reproducción desde el repositorio

```console
uv sync --locked --all-extras --group dev
uv run --locked pytest --cov=agentcraft_forge --cov-report=term-missing
uv run --locked ruff check .
uv run --locked black --check .
uv build --no-sources
uv run --locked twine check dist/*
pipx install --python 3.12 dist/agentcraft_forge-0.2.4-py3-none-any.whl
agentcraft --version
agentcraft doctor
```

En entornos que restrinjan el directorio temporal, añada un `--basetemp` nuevo y
específico dentro del workspace. Pytest administra y puede limpiar ese directorio;
no seleccione una carpeta que contenga trabajo que quiera conservar.

## Validaciones pendientes de una publicación real

No se han llamado modelos reales ni ejecutado embeddings contra el proveedor. La
imagen Docker no se construyó. CI ejecuta la matriz Linux/Windows, incluidas las
pruebas del wheel fuera del checkout; consulte Actions para el resultado del commit.
No se crearon tags, GitHub Releases ni una publicación PyPI de AgentCraft Forge.

La primera distribución en PyPI necesita disponibilidad del nombre, Trusted Publisher
y el environment pypi. El repositorio fuente es público e instalable desde GitHub.
La aceptación de un agente generado
en producción requiere sus propias pruebas de dominio, seguridad, costes, restauración
y rendimiento. Un smoke sin modelo no demuestra la calidad de sus respuestas.

El descubrimiento de la habilidad en Antigravity u otros clientes debe comprobarse
en esos clientes: el instalador verifica el archivo, no su activación en otra aplicación.
No hay conector WhatsApp operativo ni autenticación multiusuario en estos motores locales.
