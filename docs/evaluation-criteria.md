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
