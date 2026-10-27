# Criterios de aceptación de las evaluaciones

Definidos antes de implementar el evaluador.

- Preparar y validar una suite no ejecuta código del agente ni llama proveedores.
- Cada plantilla incluye casos sintéticos de capacidad, límites y abstención o aclaración.
- Las pruebas de reglas informan su criterio exacto; las respuestas abiertas requieren revisión humana y no se presentan como exactitud semántica certificada.
- La ejecución utiliza el runtime generado y conserva huellas del proyecto y la suite.
- Se informa pass@1, éxito en k intentos, éxito en todos los k intentos, abstenciones, errores, latencia p50/p95 y consumo conocido o desconocido.
- Una ejecución incompleta nunca mejora sus métricas omitiendo los intentos faltantes.
- El coste estimado usa tarifas explícitas del usuario; no se inventan tarifas ni se interpreta consumo desconocido como cero.
- Los casos de dominio usan carpetas temporales con datos sintéticos. Las herramientas usan respuestas HTTP fijas y declaradas, con modelos reales solo mediante activación explícita.
- Se detiene entre intentos al alcanzar el presupuesto o si falta telemetría. Este control no garantiza un límite de facturación durante una petición en curso.
- Deben seguir funcionando los cinco tipos, el flujo interactivo, la generación desde wheel y la inspección de proyectos antiguos.

## Refinamiento y caso completo — 0.3.1

Criterios definidos antes de implementar esta ampliación:

- Un fallo de herramienta no puede aprobar un caso de consulta por mencionar el número esperado.
- Las equivalencias booleano/número dentro de listas y objetos tampoco cuentan como igualdad JSON.
- Se aceptan variantes correctas previstas, como cuatro horas y 4 horas, sin certificar su semántica solo con texto.
- Las reglas inválidas se rechazan al preparar la suite, antes de cualquier llamada de pago.
- Los rechazos de dominio solo cuentan como esperados si el caso declara el código exacto y el paso; no se ocultan otros errores.
- La decisión final distingue reglas fallidas, ejecución incompleta, revisión humana pendiente y criterios satisfechos.
- Una revisión se vincula a los bytes exactos del informe, identifica a quien revisa y no rellena aprobaciones automáticamente.
- El caso completo genera e instala un proyecto de gastos; usa procesos nuevos y solicitudes explícitas, y conserva comprobantes, estado final y una evaluación reproducible.
- La demostración incluye reintento, conflicto, rechazo de lote inválido, anulación y lectura posterior al reinicio, con importes esperados calculados de forma independiente.
- Las evaluaciones con modelos reales siguen pendientes por decisión del usuario.

## Informes y selección de casos — 0.3.2

- Los informes válidos pueden revisarse aunque superen 1 MB; suites y tarifas conservan su límite pequeño e independiente.
- El destino de un informe se reserva de forma exclusiva antes de ejecutar un agente. Dos procesos no pueden empezar a facturar para el mismo destino.
- Un destino no escribible se detecta antes de llamar modelos, y una evaluación fallida no deja un bloqueo abandonado.
- El informe se publica completo; una interrupción no expone un JSON parcialmente escrito como si fuese el resultado final.
- La selección por ID o categoría se valida antes de ejecutar y conserva los casos excluidos, sus motivos y la huella de la suite completa.
- Los denominadores de las métricas corresponden a la selección efectiva; una evaluación parcial no se presenta como cobertura de toda la suite.
- Los casos de herramientas declaran las capacidades que requieren. Los no aplicables se excluyen explícitamente y una selección incompatible no inicia llamadas.
- Se prepara una demostración RAG con corpus sintético, embeddings y chat OpenAI reales. El usuario autorizó hasta US$1; no se ejecuta sin una clave local disponible ni se sustituye por una simulación presentada como real.
