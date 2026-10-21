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

Los motores de dominio son locales y no autentican usuarios. owner es identidad
declarada, no ACL. La evidencia de origen y los snapshots son hashes sin firma;
no resisten a alguien que pueda modificar también el estado del proyecto. Los
comprobantes afirman el resultado de una operación local, no un movimiento bancario.
No hay conector WhatsApp ni importación automática de bases preexistentes.

Un timeout o fallo posterior al commit puede devolver persisted=null. Consulte el
comprobante o reintente con el mismo ID. No afirme que no se escribió nada solo
porque la llamada terminó con error. Las aplicaciones del auditor guardan backups;
pruebe restauración y gestione locks residuales antes de usarlas como servicio.

