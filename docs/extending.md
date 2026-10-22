# Extender capacidades sin dispersar el catálogo

El catálogo de src/agentcraft_forge/catalog.py reúne las cinco arquitecturas, sus
capacidades, límites, recursos de runtime y dependencias. El planificador, la
validación, la generación y la vista previa consultan ese catálogo.

## Añadir una herramienta

1. Añada templates/runtime/tool_plugins/mi_herramienta.py.tmpl con una función
   build(client) que devuelva una herramienta tipada cuyo nombre sea mi_herramienta.
2. Registre un ToolDefinition en catalog.py mediante register_tool. Declare nombre,
   recurso, fábrica, alcance, dependencias y configuración permitida.
3. Añada casos que prueben entradas autorizadas, denegadas y fallos externos.

El generador copia solo los módulos seleccionados y produce tool_registry.py con
sus fábricas y configuración. El constructor común recorre ese registro. El LLM
solo selecciona nombres validados: no aporta módulos, direcciones ni código Python.
Las ciudades/coordenadas y repositorios se declaran en configuration, se muestran
en el alcance y alimentan los esquemas de argumentos del runtime. Para ampliar
esas listas cambie esa configuración y sus casos, sin duplicarlas en la plantilla.

Las implementaciones son código revisado incluido en el paquete. No se descargan
plugins ni se descubren puntos de entrada externos automáticamente. Cambiar el
catálogo no altera el código ya generado; genere una copia para revisar la migración.

## Adaptar una plantilla

Cada TemplateDefinition declara capabilities, summary, limits, runtime,
dependencies y domain. Las dependencias del proyecto nuevo se renderizan desde
esa definición. Las capacidades no son etiquetas decorativas: una plantilla de
dominio exige su conjunto completo y tools permite subconjuntos.

Para una arquitectura nueva añada su Kind público y una definición, implemente
el contrato del runner y una suite sintética. Las arquitecturas tienen contratos
distintos de ejecución; el registro no inventa esos contratos. Los cinco contratos
actuales conservan sus adaptadores explícitos. Las semillas RAG/audit y los archivos
comunes se mantienen en generator.py.

Las listas SPECIFIC y la implementación tools_legacy se conservan únicamente para
validar el inventario de plantillas v1/v2. La plantilla v3 usa el catálogo moderno;
no añada nuevas capacidades a las listas heredadas.

Antes de distribuir, ejecute las pruebas del generador, las pruebas del runtime
generado y la comprobación del wheel desde otra carpeta. Use agentcraft plan para
verificar que el alcance anunciado coincide con los argumentos aceptados.
