# Seguridad

El generador usa un catálogo cerrado de capacidades. El LLM no emite código libre ni
comandos que el generador ejecute. Los requisitos se escriben en JSON como datos.
La validación sintáctica no es un sandbox ni certifica seguridad de código editado.

`build --install` instala un proyecto de confianza y puede ejecutar su backend de
empaquetado. `run` ejecuta código local y dependencias en un venv, que aísla paquetes
pero no restringe permisos del sistema operativo. No use proyectos desconocidos
con estos comandos. Aplique un contenedor/worker aislado cuando sea necesario.

Nunca se sobrescribe una carpeta existente. Un fallo de disco puede dejar un proyecto
incompleto, detectable por build. Los directorios de desarrollo deben ser controlados
por el operador; no se pretende resolver carreras con un atacante local concurrente.

Los agentes generados requieren controles de identidad, permisos, costes y evaluación
del dominio antes de producción. No registrar claves ni datos personales en issues.
El mantenedor debe configurar un canal privado de vulnerabilidades antes de publicar.

