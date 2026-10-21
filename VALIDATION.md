# Evidencia de validación — 0.2.2

Fecha: 21 de octubre de 2026. Plataforma local: Windows, Python 3.12.14.

| Comprobación | Resultado |
|---|---|
| pytest, red bloqueada por fixture | 149 pruebas correctas |
| Cobertura de sentencias | 89 %; incluye los motores de dominio en su fuente, no las copias generadas como código instrumentado |
| Ruff | Correcto en fuente, scripts y pruebas |
| Black | 22 archivos de fuente, scripts y pruebas formateados |
| Plantillas generadas | RAG, herramientas, multiagente, gastos y auditoría generan Python válido |
| Instalación del wheel con pipx | Correcta en un PIPX_HOME temporal, sin cambiar el PATH global del usuario |
| Smoke del wheel fuera del checkout | Cinco tipos pasan init, build, inspect y run --dry-run; adaptador y dos pruebas de dominio correctos |
| build --install desde el wheel instalado | Crea venvs e instala los proyectos expenses y audit correctamente |
| invoke y persistencia entre procesos | Seis gastos sintéticos, total y saldo mensual consistentes |
| Reintentos y conflictos | Misma operación no duplica; argumentos distintos con el mismo ID se rechazan |
| Auditoría de dominio | Tres candidatos con fuentes, progreso reciente revisado, aplicación con backup y reintento sin duplicados |
| Pruebas incluidas en los proyectos generados | unittest de expenses y audit correctos en sus propios venvs |
| CLI nueva contra proyecto 0.2.1 | Inspect y propuesta correctos; hashes del código, manifiesto y base de datos sin cambios |

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
pipx install --python 3.12 dist/agentcraft_forge-0.2.2-py3-none-any.whl
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
