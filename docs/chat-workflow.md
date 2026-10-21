# Operación por chat y comprobantes — 0.2.2

El asistente del chat interpreta la intención y usa la CLI como herramienta. El motor
generado decide si la solicitud es válida, ejecuta y devuelve el resultado. El asistente
redacta a partir de ese resultado. Esta versión no añade una aplicación de chat ni una
conexión con WhatsApp: procesa exports y mensajes proporcionados al asistente.

```text
Petición del usuario
  → habilidad del asistente: AgentCraft instalado y catálogo real
  → init --json → manifiesto + origen registrado + código + habilidad local
  → build --install → inspect → pruebas del proyecto
  → mensaje → propuesta / aclaración
  → solicitud JSON autorizada → invoke → motor del proyecto
  → transacción o actualización verificada → comprobante → respuesta del chat
```

## Instalar y descubrir el adaptador

```console
pipx install --python 3.12 "git+https://github.com/juliansantamaria0/agentcraft-forge.git@main"
agentcraft --version
agentcraft doctor
agentcraft install-skill --directory .agents/skills
```

Para una instalación ya existente, `pipx reinstall agentcraft-forge` repite su origen
original. Si quiere cambiar de un wheel local al repositorio, desinstale esa distribución
y vuelva a instalar usando la URL anterior. El adaptador es un archivo SKILL.md; la
compatibilidad y recarga dependen del cliente. Para Codex global puede seleccionar
`$HOME/.codex/skills` en PowerShell. Para Antigravity seleccione el directorio que tenga
configurado su instalación; no se presume que todos los clientes usen la misma ruta.

Si existe una habilidad personalizada, el instalador falla para conservarla. Revise y
actualice esa copia explícitamente. Instalar el paquete no activa habilidades por sí solo.

## Creación demostrable

```console
agentcraft init --name gastos-personales --purpose "Registrar gastos personales y consultar mi presupuesto" --kind expenses --yes --json
agentcraft build --project gastos-personales --install
agentcraft inspect --project gastos-personales
```

La respuesta de init da la ruta absoluta. Use esa ruta en el chat, incluso si cambia
el directorio actual. El manifiesto registra requisitos, tipo, versión y capacidades.
La evidencia conserva hashes originales; inspect muestra cambios y frescura del build.
Ni una huella ni sintaxis válida prueban autoría externa, seguridad o comportamiento.
Los proyectos de plantilla v1 pueden seguir validándose sin inventar un archivo de origen.

Desde 0.2.2, `build_status` distingue `missing` (sin comprobante), `invalid` (estado
dañado o no legible), `stale` (no coincide con el proyecto) y `fresh` (coincide con
la validación actual). `build_fresh` sigue disponible como booleano. Un estado inválido
no impide inspeccionar el código válido, pero bloquea run/invoke hasta reconstruir.
Una evidencia de origen mal formada produce un error estructurado y no se reescribe.
`origin.added_source_files` enumera Python nuevo dentro de src/tests y cambia el
estado de origen a modified, aunque los archivos originales no se hayan tocado.

Cada nuevo build retira primero su comprobante anterior y guarda el nuevo por reemplazo
atómico solo después de completar el proceso. Si la instalación falla o el código cambia
durante ella, repita build --install antes de ejecutar. Una validación sin --install
no comprueba ni repara dependencias. Run revalida archivos requeridos y sintaxis;
no importa módulos como parte de esa validación. El estado local no es una firma.

## Gastos: interpretación y escritura

```console
agentcraft run --project gastos-personales --message 'Compré una xbox de 2.400.000 y un expansor de memoria de $450.000'
```

En PowerShell, para mensajes con `$` use comillas simples o pase el mensaje mediante
una herramienta que envíe argumentos separados; las comillas dobles pueden expandir
variables. Este ejemplo de consola es ilustrativo para shells que preserven el texto.
El resultado de run es una propuesta, persisted=false, sin modificar SQLite. Para
una escritura autorizada, el asistente prepara un archivo JSON en
`gastos-personales/.agentcraft/requests/compra.json`:

```json
{
  "action": "record",
  "operation_id": "mensaje-compra-0001",
  "currency": "COP",
  "expenses": [
    {"amount": 2400000, "description": "Xbox", "expense_date": "2026-10-21"},
    {"amount": 450000, "description": "Expansor de memoria", "expense_date": "2026-10-21"}
  ]
}
```

```console
agentcraft invoke --project gastos-personales --request gastos-personales/.agentcraft/requests/compra.json
```

Los ejemplos tienen fecha fija para ser reproducibles; el asistente debe resolver la
fecha real del usuario antes de operar. El parser usa la fecha local del dispositivo
cuando no se proporciona una fecha en el mensaje. En un servicio, resuelva la zona
horaria del usuario fuera de este parser y envíe expense_date explícitamente.

Record valida todo el lote y guarda los registros y el comprobante en una transacción.
Devuelve status=committed, persisted=true, operation_id, record_ids y totales por mes.
COP usa pesos enteros; se rechazan floats, importes no positivos, campos desconocidos
y otras monedas. Las categorías son reglas neutrales que pueden corregirse al enviar
el registro explícito. No se califican compras como innecesarias ni se inventa un saldo.

El presupuesto no existe hasta que se configura para un mes:

```json
{"action":"set_budget","operation_id":"presupuesto-2026-10-001","month":"2026-10","amount":2500000,"currency":"COP"}
```

Otros archivos de solicitud pueden contener:

```json
{"action":"summary","month":"2026-10"}
```

```json
{"action":"summary","date":"2026-10-21"}
```

```json
{"action":"summary"}
```

La última consulta comprende todo el historial, sin comparar varios meses con un
único presupuesto. `dame un reumen de todos mis gastos` produce esa solicitud; el
asistente debe ejecutarla y usar los datos nuevos. La comprensión incorporada es
conservadora: negaciones, devoluciones, planes futuros y fechas contradictorias piden
aclaración. La interpretación más amplia del asistente no elimina la validación JSON.

Desde 0.2.1, `resumen de ayer` consulta ese día; `resumen del mes pasado` respeta
el cambio de año y `resumen de septiembre de 2025` conserva el mes y año indicados.
`Presupuesto de $2.500.000 para 2026-11` propone noviembre de 2026. Un mes nombrado
sin año, varios periodos o una semana/rango requieren aclaración. El presupuesto
es mensual; no se transforma un día indicado por el usuario en un presupuesto de mes.
Sin periodo se mantiene el mes actual, salvo la consulta de todo el historial.

Una petición que mezcla registrar y consultar se debe separar. En un lote con varios
importes no se descartan las cláusulas sin precio: se solicita completar los datos.
Estas reglas no sustituyen la interpretación del chat ni cubren todo el lenguaje natural.
Las solicitudes y los exports JSON rechazan claves duplicadas y valores NaN/Infinity.
Un error de formato detectado antes de ejecutar el motor devuelve persisted=false.

Los totales y categorías abarcan todo el período. La lista de movimientos está paginada:
limit=100 por defecto, máximo 1000, y offset=0. has_more indica si faltan páginas.
Los comprobantes conservan los registros de su operación y totales compactos; no
duplican todo el historial del mes con cada escritura.
Los componentes de cada resumen se leen desde el mismo snapshot SQLite, aunque otro
proceso registre un gasto durante la consulta. Una consulta posterior refleja ese gasto.

## Reintentos, correcciones y estado incierto

Cada intención de escritura tiene un operation_id único. El mismo ID con la misma
solicitud normalizada devuelve el comprobante original con replayed=true. El mismo ID
con otros argumentos produce conflicto. Dos gastos legítimos iguales usan IDs distintos.

Si una llamada expira, no se presupone que falló el commit. Consulte el recibo:

```json
{"action":"receipt","operation_id":"mensaje-compra-0001"}
```

O reintente la solicitud idéntica con el ID original. persisted=null significa que
no pudo confirmarse el estado; no es un comprobante de que no se haya escrito nada.
El recibo describe el momento de la operación. Use summary para el saldo actual.

Las anulaciones conservan el registro y su motivo:

```json
{"action":"void","operation_id":"correccion-0001","expense_ids":[1],"reason":"Registro duplicado confirmado por el usuario"}
```

Una corrección de importe puede requerir anular y registrar una nueva operación; esas
dos operaciones son independientes, no una única transacción de reemplazo. El chat debe
informar el resultado de cada una. No hay migración automática desde gastos.db: esa base
original permanece intacta y debe mapearse mediante un procedimiento de importación futuro.

## Auditor: solicitudes, fuentes y selección

```console
agentcraft init --name compromisos --purpose "Auditar open loops y compromisos pendientes" --kind audit --yes --json
agentcraft build --project compromisos --install
```

El proyecto incluye un registro vacío, journal/ y whatsapp/. Los datos personales se
excluyen de Git por defecto. No se cargan ejemplos ficticios como si fueran compromisos reales.
El auditor admite ambos encabezados de export: `[21/10/2026, 09:40] Nombre: texto`
y `[09:40, 21/10/2026] Nombre: texto`. Conserva el mensaje multilinea. El formato JSON es:

```json
[{"id":"mensaje-001","sender":"Persona","date":"2026-10-21","text":"Me comprometí a entregar el informe mañana"}]
```

La solicitud de auditoría es:

```json
{"action":"scan","owner":"Persona","reference_date":"2026-10-21","stale_days":14,"recent_days":30}
```

El informe muestra candidatos con archivo, línea, hash, emisor, responsable declarado,
fecha de fuente y vencimiento propuesto. Los encargos de terceros son peticiones con
aceptación sin confirmar; no se convierten en promesas aceptadas por defecto.
Un avance reciente relacionado evita presentar el loop como simplemente estancado y
se marca para revisión. Las coincidencias con tareas cerradas se muestran, no se ocultan.
Las negaciones, preguntas y expresiones futuras reconocidas por las reglas no cuentan
como progreso. Una frase ambigua puede necesitar revisión manual; el motor no prueba
comprensión semántica completa ni marca automáticamente un compromiso como terminado.

Scan guarda su informe local, pero persisted=false indica que no modificó el registro
canónico. Fuentes ausentes o sin fecha producen incomplete. La ausencia de candidatos
no demuestra sincronización total: el extractor sigue siendo heurístico. La identidad
owner es declarada y no constituye autenticación.

Después de revisar y autorizar IDs concretos:

```json
{"action":"apply","scan_id":"ID_DEVUELTO_POR_SCAN","candidate_ids":["ID_REVISADO"],"operation_id":"aplicar-compromisos-0001"}
```

Apply comprueba que las fuentes y open-loops.md sigan en el mismo snapshot; rechaza
posibles duplicados sin resolver y candidatos ajenos al informe. Guarda backup, escribe
por reemplazo atómico y verifica el hash resultante antes de confirmar. Un journal
pendiente permite recuperar un recibo si hubo interrupción después de escribir.
La integridad local no impide que alguien con los mismos permisos modifique también
los informes. No se pretende proporcionar aislamiento frente a atacantes locales.

Un lock evita dos aplicaciones concurrentes del motor. Si un proceso se interrumpe,
revise que haya terminado antes de retirar el lock residual; no se elimina a ciegas.
Editar manualmente el registro no usa ese lock: vuelva a escanear después de editar.

## Pruebas antes de prometer que funciona

Después de instalar el proyecto, desde su raíz use el Python de su venv:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_domain.py
```

```console
.venv/bin/python -m unittest discover -s tests -p test_domain.py
```

La prueba generada utiliza datos temporales. La suite del generador añade casos de
montos, reintentos, atomicidad, presupuestos históricos, fechas, atribución, progreso,
snapshots y recuperación. La instalación real del adaptador en un cliente distinto
debe comprobarse en ese cliente; ninguna prueba de Python demuestra su descubrimiento.
