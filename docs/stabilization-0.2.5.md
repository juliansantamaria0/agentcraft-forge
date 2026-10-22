# Estabilización 0.2.5

Las correcciones se aplican al generador y a las plantillas para proyectos nuevos.
Una reinstalación de la CLI no sobrescribe agentes existentes ni sus datos.
Genere una copia, compare los archivos y ejecute sus pruebas antes de incorporar cambios.

## Gastos

Las propuestas admiten fechas como 20 de octubre de 2026 y hace tres días, con una
fecha de referencia inyectable para pruebas. El lunes, anoche, periodos no admitidos
y fechas sin año piden aclaración. Un mes sin día no se convierte en un gasto de hoy.
El motor sigue sin escribir al interpretar un mensaje.

## Auditoría

scan_version=3 conserva cada candidato y su evidencia. possible_candidate_matches
relaciona candidatos similares con responsable compatible y sin vencimientos
explícitos distintos. No se fusionan tareas ni se descartan fuentes.
Una selección que contenga candidatos equivalentes se rechaza antes de escribir.
Seleccione un representante o aclare las fechas si son tareas recurrentes.
El límite es 500 candidatos por escaneo; divida fuentes o ventanas si lo supera.
Los informes anteriores deben volver a generarse. Los reintentos con comprobantes
ya confirmados conservan su resultado histórico.

## Cargas documentales

La colección se crea con un manifiesto de carga en estado loading. Solo cambia a
ready después de comprobar el recuento completo. Las consultas exigen versión,
estado, inventario y recuento coherentes antes de usar embeddings o modelo.
Una interrupción, incluso después de guardar un lote, deja bloqueadas las consultas.
Esta transición de estado evita publicar un corpus parcial sin duplicar colecciones.

Las colecciones antiguas sin manifiesto también se rechazan. Conserve las fuentes,
elija otro QDRANT_COLLECTION y repita la ingestión. No se borran ni sobrescriben
colecciones existentes al reintentar. Revise y elimine manualmente las cargas
abandonadas solo después de verificar que ya no las necesita.
El servidor Qdrant debe admitir metadatos de colección, como el cliente 1.19.1
utilizado en las pruebas. Modificar vectores directamente después de ready queda
fuera del contrato de snapshot inmutable.

## Contenedores y datos

Docker copia exclusivamente metadatos de empaquetado, código y agentcraft.json.
El contexto usa una lista de archivos permitidos. No incorpora journal, whatsapp,
open-loops.md, .env ni directorios de estado de la carpeta desde la que se construye.
El código vive en /app y el estado en /workspace, con propietario UID/GID 10001.

Monte almacenamiento persistente sobre /workspace. Un volumen nuevo comienza vacío:
el auditor necesita su open-loops.md y sus fuentes reales, aportados al ejecutar.
Los bind mounts deben permitir escritura al UID/GID de ejecución, incluida la carpeta
que contiene open-loops.md; un reemplazo atómico necesita permisos en ese directorio.
No monte datos personales en /app ni los añada a la imagen para inicializarla.
En las plantillas de IA, AGENTCRAFT_SPEC_PATH=/app/agentcraft.json permite separar la
especificación del directorio de datos. Las credenciales se aportan mediante el entorno.

scripts/docker_smoke.py construye las plantillas expenses y audit con marcadores
personales sintéticos. Comprueba que no se copiaron y ejecuta dos contenedores por
agente contra un volumen: usuario sin privilegios, persistencia, escrituras atómicas
y reintentos. CI lo ejecuta en Linux y publicación lo exige antes de crear el tag.

## Eventos

Los runtimes de IA registran sesión, consultas, cargas documentales, llamadas al
modelo y herramientas en stderr. Las operaciones anidadas comparten run_id y
registran duración y estado. stdout conserva los resultados JSON.
No se registran preguntas, respuestas, argumentos de herramientas ni excepciones
con datos del usuario. No se añade por este cambio una medición monetaria del proveedor.
