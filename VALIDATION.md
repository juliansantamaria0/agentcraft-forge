# Evidencia de validación — 0.1.0

Fecha: 21 de octubre de 2026. Plataforma local: Windows, Python 3.12.14.

| Comprobación | Resultado |
|---|---|
| pytest, red bloqueada por fixture | 32 pruebas correctas |
| Cobertura de sentencias de la CLI | 82 %; no incluye plantillas como código instrumentado |
| Ruff | Correcto en fuente, scripts y pruebas |
| Black | 13 archivos correctos, sin cambios pendientes |
| Plantillas generadas | RAG, herramientas y multiagente generan Python válido y pasan Ruff |
| Instalación del wheel con pipx | Correcta en un PIPX_HOME temporal, sin cambiar el PATH global del usuario |
| Smoke del wheel fuera del checkout | Los tres tipos pasan init, build y run --dry-run |
| build --install del proyecto de herramientas | Crea un venv e instala sus dependencias correctamente |
| run conversacional del proyecto instalado | Arranque y salida con salir correctos, sin llamadas al modelo |

La batería prueba validación, menú interactivo, cancelación, generación de las tres
arquitecturas, recursos instalados, no sobrescritura, tratamiento del propósito como
datos, permisos del catálogo, sintaxis sin ejecución, frescura y JSON de salida largo.
El camino del diseñador se prueba con un sustituto inyectado; no es una evaluación
del proveedor real. La instalación del runtime se prueba por separado del conjunto
unitario, que no debe necesitar credenciales ni acceso de red.

La primera ejecución final de pytest encontró una restricción del directorio temporal
del entorno de ejecución. Usar un basetemp dentro del workspace permitió ejecutar
las 32 pruebas sin cambios de código. Esto no fue un fallo funcional de la CLI.

## Reproducción desde el repositorio

```console
uv sync --locked --all-extras --group dev
uv run --locked pytest --cov=agentcraft_forge --cov-report=term-missing
uv run --locked ruff check .
uv run --locked black --check .
uv build --no-sources
uv run --locked twine check dist/*
pipx install --python 3.12 dist/agentcraft_forge-0.1.0-py3-none-any.whl
agentcraft --version
```

En entornos que restrinjan el directorio temporal, añada un `--basetemp` nuevo y
específico dentro del workspace. Pytest administra y puede limpiar ese directorio;
no seleccione una carpeta que contenga trabajo que quiera conservar.

## Validaciones pendientes de una publicación real

No se han llamado modelos reales ni ejecutado embeddings contra el proveedor. La
imagen Docker no se construyó. No se ejecutó aún la matriz Linux/Windows en GitHub
para este nuevo repositorio. Los workflows se entregan configurados, pero no se
crearon tags, GitHub Releases ni una publicación PyPI de AgentCraft Forge.

La primera distribución pública necesita un remoto definitivo, disponibilidad del
nombre, Trusted Publisher y el environment pypi. La aceptación de un agente generado
en producción requiere sus propias pruebas de dominio, seguridad, costes, restauración
y rendimiento. Un smoke sin modelo no demuestra la calidad de sus respuestas.
