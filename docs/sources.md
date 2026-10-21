# Fuentes primarias

Consulta: 21 de octubre de 2026. Las decisiones arquitectónicas son elaboración
propia; las APIs y requisitos de distribución se apoyan en las siguientes fuentes.

| Área | Fuente |
|---|---|
| Typer prompts y comandos | [Typer](https://typer.tiangolo.com/tutorial/prompt/) |
| Interfaces Rich | [Prompt](https://rich.readthedocs.io/en/stable/prompt.html) |
| CLI y entry points | [PyPA command-line tools](https://packaging.python.org/en/latest/guides/creating-command-line-tools/) |
| Datos incluidos en paquetes | [Setuptools package data](https://setuptools.pypa.io/en/stable/userguide/datafiles.html) |
| Recursos portables | [importlib.resources](https://docs.python.org/3/library/importlib.resources.html) |
| Instalación aislada | [pipx examples](https://pipx.pypa.io/stable/reference/examples.html) |
| Nombre existente | [agentcraft en PyPI](https://pypi.org/project/agentcraft/) |
| PyPI + GitHub Actions | [Guía PyPA](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) |
| Trusted Publishing | [PyPI publishers](https://docs.pypi.org/trusted-publishers/using-a-publisher/) |
| Primera publicación | [Pending publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/) |
| Eventos de workflows | [GitHub workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow) |
| Distribuciones en CI | [upload-artifact v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2), [download-artifact v8.0.2](https://github.com/actions/download-artifact/releases/tag/v8.0.2) |
| Acción de publicación | [PyPI publish v1.14.3](https://github.com/pypa/gh-action-pypi-publish/releases/tag/v1.14.3) |
| Modelos y herramientas | [LangChain agents](https://docs.langchain.com/oss/python/langchain/agents) |
| Recuperación Qdrant | [Integración oficial](https://docs.langchain.com/oss/python/integrations/vectorstores/qdrant) |
| Multiagentes | [CrewAI 1.15.28](https://docs.crewai.com/v1.15.28/en/quickstart) |

El runtime reutiliza las implementaciones de referencia desarrolladas previamente,
adaptadas al namespace `agent_app`, selección de arquitectura y configuración del
proyecto. Se incluyen sus fuentes y licencia; no se descargan desde el repositorio
privado anterior durante la generación o instalación.

