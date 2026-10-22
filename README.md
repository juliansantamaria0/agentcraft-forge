# AgentCraft Forge

De una idea a un proyecto de agente con capacidades explícitas, código y pruebas.

## Una demostración en un minuto

Con Python 3.12, instale desde el checkout:

```console
python -m pip install --user pipx
pipx install --python 3.12 .
agentcraft init --name mis-gastos --purpose "Organizar mis gastos personales" --kind expenses --yes
agentcraft build --project mis-gastos --install
agentcraft run --project mis-gastos --message "Gasté 15k en almuerzo hoy"
```

Resultado abreviado:

```json
{
  "status": "proposal",
  "persisted": false,
  "model_invoked": false,
  "request": {
    "action": "record",
    "currency": "COP",
    "expenses": [{"amount": 15000, "description": "almuerzo", "expense_date": "FECHA_DE_HOY"}]
  }
}
```

La propuesta permite revisar importe y fecha. Para registrar el gasto, añada un
operation_id estable a la solicitud JSON y ejecute agentcraft invoke. Las consultas,
presupuestos y comprobantes se explican en la [guía de uso](docs/usage.md).

## Compruebe el alcance antes de generar

```console
agentcraft plan --name mi-agente --purpose "Consultar el clima mundial" --kind tools
```

La vista previa no crea archivos ni llama modelos. Explica qué puede hacer realmente
la plantilla; también aparece antes de la confirmación interactiva de init y se
guarda en scope.json. Un propósito más amplio no añade integraciones.

| Plantilla | Capacidades incluidas | Límite principal |
| --- | --- | --- |
| expenses | Propuestas de gastos en COP, registro explícito, consultas y presupuesto | Español acotado; sin conexión bancaria ni modelo |
| audit | Revisar compromisos de archivos locales y aplicar selecciones revisadas | Sin conexión a WhatsApp ni envío de mensajes |
| rag | Buscar documentos propios con citas y abstenerse sin evidencia | Ingestión explícita de .md/.txt; requiere modelo y embeddings |
| tools | Clima de Bogotá/Madrid y metadatos de qdrant/qdrant, langchain-ai/langchain, crewAIInc/crewAI | Solo lectura de esos destinos; requiere modelo |
| multi | Analista, arquitecto y revisor producen una propuesta | Sin navegación ni ejecución de código; requiere modelo |

## Evaluar los agentes generados

Cada proyecto nuevo incluye evals/smoke.json con casos sintéticos y reglas revisables.

```console
agentcraft evaluate --project mis-gastos
agentcraft evaluate --project mis-gastos --run --report mis-gastos/.agentcraft/eval-01.json
```

El primer comando prepara el plan. El segundo ejecuta casos deterministas en datos
temporales. RAG, tools y multi requieren activación explícita con --live, tarifas
por modelo y un presupuesto; vea la [guía de evaluaciones](docs/evaluations.md).
Los informes incluyen reglas, revisión humana pendiente, abstenciones, tiempos,
tokens y costes estimados. Las pruebas offline no demuestran la calidad de un modelo
real. Las evaluaciones reales de esta versión quedan pendientes de ejecución.

## Instalar y continuar

Desde el [repositorio público](https://github.com/juliansantamaria0/agentcraft-forge):

```console
pipx install --python 3.12 "git+https://github.com/juliansantamaria0/agentcraft-forge.git@main"
agentcraft doctor
```

La distribución se llama agentcraft-forge; el comando es agentcraft. No se ha publicado
esta distribución en PyPI. Para reproducibilidad, use un commit verificado en lugar
de main. Reinstalar la CLI no migra ni sobrescribe agentes existentes.

- [Instalación, uso en chat, Docker y operación](docs/usage.md)
- [Añadir herramientas y adaptar plantillas](docs/extending.md)
- [Evaluaciones y preparación de una ejecución real](docs/evaluations.md)
- [Validación y límites de la evidencia](VALIDATION.md)
- [Historial de cambios](CHANGELOG.md)
- [Seguridad](SECURITY.md)

Licencia MIT. Python 3.12.
