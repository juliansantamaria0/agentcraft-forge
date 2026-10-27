# 3. Empaquetado, instalación global y publicación

## Nombres y estado de distribución

El producto se llama AgentCraft Forge. Su ejecutable es `agentcraft`, su paquete
importable es `agentcraft_forge` y su distribución propuesta es `agentcraft-forge`.
El nombre `agentcraft` ya está registrado por otro mantenedor en PyPI. La consulta
de `agentcraft-forge` respondió HTTP 404 el 21 de octubre de 2026; eso no reserva el
nombre ni garantiza su disponibilidad futura o los derechos sobre una marca.

El entregable incluye fuente y wheel funcional, y el repositorio público
`juliansantamaria0/agentcraft-forge`. Los ejemplos con OWNER explican cómo publicar
una copia propia. Los comandos con `v0.3.2` son ejemplos y requieren crear antes ese tag; para la
versión actual puede instalarse desde `main`, con Git instalado.
El comando PyPI solo funciona
después de una publicación real. No se presenta una URL planeada como un paquete ya
publicado.

## Empaquetado con setuptools

`pyproject.toml` define el backend, las dependencias y el entry point:

```toml
[build-system]
requires = ["setuptools>=80,<83", "wheel>=0.45,<1"]
build-backend = "setuptools.build_meta"

[project.scripts]
agentcraft = "agentcraft_forge.cli:app"

[tool.setuptools.dynamic]
version = {attr = "agentcraft_forge.__version__"}
```

La versión tiene una única fuente en `src/agentcraft_forge/__init__.py`. Setuptools
incluye los recursos declarados en package-data; MANIFEST.in incluye plantillas,
pruebas y documentación en sdist. Los archivos fuente se llaman `gitignore.j2` y
`env.example.j2`; el generador los transforma en dotfiles. Un glob de setuptools no
debe suponerse que incluye dotfiles ocultos.

`importlib.resources.files` permite acceder a plantillas desde el paquete instalado,
sin depender del checkout ni del cwd. No se empaquetan claves, estado de agentes,
venvs, caches o modelos descargados. El wheel es Python puro; la dependencia de
plataforma aparece cuando un proyecto generado instala componentes como CrewAI.

## Prueba de instalación global desde la fuente

Desde la raíz del repositorio:

```console
python -m pip install --user pipx
python -m pipx ensurepath
pipx install --python 3.12 .
agentcraft --version
agentcraft --help
agentcraft init --name first-agent --purpose "Consultar documentos de soporte de manera controlada" --kind rag --yes
agentcraft build --project first-agent
agentcraft run --project first-agent --dry-run
```

Si el comando no aparece tras ensurepath, reabra la terminal. Para una prueba temporal:

```console
python -m pipx run --spec . agentcraft --help
```

Para probar el wheel construido desde este checkout:

```console
python -m pip install uv==0.13.4
uv sync --locked --all-extras --group dev
uv build --no-sources
uv run --locked twine check dist/*
pipx install --python 3.12 dist/agentcraft_forge-0.3.2-py3-none-any.whl
agentcraft --version
```

Si la distribución ya está instalada para una prueba, use
`pipx reinstall agentcraft-forge` para reinstalar su spec existente, o
`pipx uninstall agentcraft-forge` y después instale el nuevo wheel. No se recomienda
usar `--force` como solución general a conflictos entre herramientas.

## Desde GitHub y PyPI, después de publicar

```console
pipx install --python 3.12 "git+https://github.com/OWNER/agentcraft-forge.git@v0.3.2"
```

Con el extra del diseñador de IA:

```console
pipx install --python 3.12 "agentcraft-forge[ai] @ git+https://github.com/OWNER/agentcraft-forge.git@v0.3.2"
```

La referencia fija un tag; para máxima precisión puede usarse un commit verificado.
Un repositorio privado requiere credenciales de Git del usuario. No incluya tokens
en la URL del comando. Una vez disponible en PyPI:

```console
pipx install --python 3.12 "agentcraft-forge[ai]==0.3.2"
```

También es posible instalar en un venv administrado por el desarrollador:

```console
python -m pip install "git+https://github.com/OWNER/agentcraft-forge.git@v0.3.2"
```

pipx ofrece el comando global en su directorio de ejecutables y aísla dependencias.
No convierte el runtime en un proceso sin permisos de sistema. La CLI genera un
proyecto y `build --install` crea otro venv para ese agente; ambos ciclos de
actualización quedan separados.

## Dependencias y compatibilidad

La CLI base instala Typer, Rich, Pydantic y Jinja2. El extra ai agrega el adaptador
de chat. El lock fija desarrollo y pruebas de esta versión. Los rangos del wheel
permiten al instalador resolver compatibilidad dentro de límites; un lock de uv no
se aplica automáticamente cuando un usuario ejecuta pip/pipx contra un wheel.

Cada proyecto generado declara sus dependencias por tipo. Antes de desplegar uno:
genere su propio lock, pruebe su imagen, valide los modelos accesibles y documente
sus límites de datos y coste. No se promete que una dependencia futura cumpla sin
pruebas solo porque encaje en un rango.

## Publicar el repositorio fuente

Desde una carpeta independiente, después de revisar licencia y archivos:

```console
git init -b main
git add .
git diff --cached --stat
git commit -m "feat: initial AgentCraft Forge CLI"
gh auth login
gh repo create agentcraft-forge --private --source . --remote origin --push
```

Elija conscientemente visibilidad privada o pública. Para un proyecto open source
que cualquiera pueda instalar desde GitHub, cree el remoto con `--public` tras revisar
el contenido. No publique sobre el repositorio anterior sin decidir si será una
herramienta independiente o parte de un monorepo.

## Configurar Trusted Publishing

En PyPI, configure un publisher o pending publisher con:

| Campo | Valor |
|---|---|
| PyPI project | agentcraft-forge, si está disponible |
| Owner | propietario real de GitHub |
| Repository | agentcraft-forge, o el nombre definitivo |
| Workflow | publish.yml |
| Environment | pypi |

El nombre del environment debe coincidir exactamente. Configure el environment
`pypi` en GitHub con revisores y restricciones de ramas/tags apropiadas. Un pending
publisher no reserva el nombre. La primera publicación no puede sustituir una
distribución que pertenezca a otro mantenedor.

No se necesita PYPI_API_TOKEN en este diseño: el job de publicación usa OIDC y
`id-token: write`. El job de build solo lee contenido. El job que publica únicamente
descarga los artefactos y llama a la acción de PyPI; no ejecuta el código fuente del
proyecto con permisos OIDC.

## Workflow único de etiquetado y publicación

`publish.yml` implementa cuatro jobs en la misma ejecución:

1. **build:** valida que la versión de entrada coincida con la del commit de main,
   ejecuta pruebas, construye wheel/sdist y verifica el wheel instalado.
2. **tag:** crea `vVERSION` sobre el SHA validado. Si ya existe, debe señalar al mismo
   commit; no se sobrescribe.
3. **pypi:** espera al tag, requiere el environment protegido y publica mediante OIDC.
4. **release:** después del éxito en PyPI, crea la GitHub Release y adjunta artefactos.

Las acciones se fijan por SHA. Los hashes corresponden a las revisiones consultadas
y deben actualizarse con revisión de cambios. La publicación no se ejecuta en cada
push ni depende de que un tag creado con GITHUB_TOKEN dispare otro workflow: GitHub
normalmente no encadena esos eventos. Todos los pasos permanecen en publish.yml.

## Lanzar una versión

Actualice `__version__`, changelog y lock, y confirme los cambios:

```console
uv lock
uv run --locked ruff check .
uv run --locked black --check .
uv run --locked pytest
uv build --no-sources
uv run --locked twine check dist/*
git add src/agentcraft_forge/__init__.py CHANGELOG.md uv.lock
git commit -m "chore: release 0.3.2"
git push origin main
gh workflow run publish.yml --ref main -f version=0.3.2
gh run list --workflow publish.yml
```

Para la primera versión ya confirmada, omita el commit vacío. No cree el tag a mano
si usará este flujo: el workflow lo crea después de validar el commit. Para releases
posteriores use la versión nueva en todos los pasos.

El workflow no aumenta automáticamente MAJOR/MINOR/PATCH: el mantenedor declara la
versión según el cambio y la automatización valida y etiqueta. Esta versión admite
releases estables; prereleases requieren definir una política explícita y ampliar
el validador.

Si falla PyPI, el tag puede existir sin distribución. Se puede repetir el flujo sobre
el mismo commit; no mueva un tag publicado ni reutilice una versión para contenido
distinto. Si una distribución llegó a PyPI, revise el estado antes de reintentar:
las versiones publicadas son inmutables. GitHub Release usa `--verify-tag`.

## Validación final y condiciones pendientes

La instalación local y el smoke del wheel verifican el empaquetado. No prueban
permisos OIDC, disponibilidad del nombre, coste de modelos ni políticas de una cuenta.
La primera publicación requiere configurar el publisher con la identidad real del
mantenedor. No se han creado tags, releases ni distribuciones públicas durante la
preparación de este entregable.

