# F1b-bridge sin juego: protocolo `dsbx1`, lado del backend y mod falso

2026-11-14 · tarea **F1b-bridge**, rama `claude/f1b-bridge` (apilada sobre `claude/f1b-web` `08809dc`, que lleva los arreglos de la revisión del código del PR #7) · spec de implementación (R25) de lo que queda de F1b tras F1b-web: [plan v2](2026-10-26-m1-cine-v2.md) F1 (líneas 88, 89 y 91), decisiones #2, #3, #9, #10, #22, #23 y #24 · contrato: `DayZSandbox_dev/product-spec.md`, D2 (línea 88), E1 (99) y E3 (101) · v1.0, borrador para la revisión de Sol.

**Por qué ahora.** S-puente pasó en retail (PR #6, `origin/claude/f0.2-sonda` `9103b5b`). En `evidence/m1/S-puente/retail-20261114T151150Z/verdict.json` (líneas 84-98): `PASA` 16/16, `p50_ms` 200,8, `p95_ms` 603,1, `max_ms` 8679 (un caso suelto) y 0 timeouts; con `lease_ms` = 3000, la ventana acepta hasta 2756 ms y rechaza desde 3037 ms. Guillermo aprobó F1b-bridge el 2026-11-14 en la sesión principal («Sí, arráncalo»).

**Qué hay ya.** `app/backend/server.py` (F1a, F1-co y F1b-web): `POST /api/apply` crea una orden `pendiente` con la `rev` y el `hash` congelados (`server.py:229-238`), con `origin` y `op_mono` (F1b-web §4, líneas 85-89), y nada la despacha. La web enseña los seis estados de #23 con su edad y su origen. El bridge QA de F0.2 (`qa/bridge_qa.py`, `qa/fake_peer.py` y la sonda en Enforce) es el **patrón medido**, no el producto: `dsbx1` es un protocolo nuevo que corrige sus defectos de diseño (§2.7).

**Proceso.** Como F1b-web: dos tandas en serie (§9), el orquestador revisa e integra, y Sol revisa este brief hasta VERDE (0 bloqueantes, 4 rondas como mucho) y el código después. Sin lanzar DayZ.

## 0. Qué es y qué no

Es:
- el **protocolo `dsbx1`** entre el backend y los dos peers del mod (#3), escrito aquí como contrato que cumplen tanto el mod falso de ahora como el mod real de después (§2);
- el **lado del backend** (`app/backend/bridge.py`, un listener propio en 127.0.0.1): handshake, entrega por long-poll, resultados, TTL por orden, deduplicación, cola acotada, transiciones reales de #23, reconciliación del estado del mundo antes de autorizar nada (#10, CX-07) e ingesta del catálogo (#8, plan F1 línea 89);
- el **mod falso** en Python (`app/tests/fake_mod.py`, #24, plan F1 línea 91): los dos peers con su caché de deduplicación, su TTL, su hombre muerto con polls de mantenimiento, su validación de las respuestas y la inyección de fallos para las pruebas;
- el **cableado**: las órdenes de `POST /api/apply` viajan al peer servidor como `scene.apply`, y sus transiciones llegan a la web por el SSE que ya existe.

No es (decisión por defecto de este brief; si la sesión principal o Guillermo la cambian, se rehace §9):
- **los peers reales en Enforce** (el mod núcleo `DayZSandbox/`, que aún no existe). Implementarán este mismo contrato cuando se puedan probar en partida; con ellos va la medida de E1 en retail, que queda fuera por indicación expresa y pide el visto bueno de Guillermo;
- la semántica real de `scene.apply`, del reset y de la observación (F2, #9: lotes, etapas, compensación y registro con entidades). Aquí el mod falso solo anota la generación aplicada;
- los verbos de cámara, ambiente y actores (F3-F5). El peer cliente solo se presenta, hace poll y mantiene su lease;
- usar el catálogo recibido para validar escenas (F2 decide cómo se mapean clases a tipos y topes): aquí solo se recibe, se valida y se guarda;
- la mezcla de E2 y cualquier medida en partida (F6 y la tarea de E1).

Trazabilidad (R20): §2 sale de #3, #9, #10, #22, #23, de la fila S-puente (plan línea 66) y de la revisión de Sol sobre #6; §3, de #22 y #23; §4, de #10 y CX-07; §5, de #8; §6, de #24; §7, de D2 y E1. Lo que no trace a esto no entra.

## 1. Entorno y fronteras

Como F1b-web §1: Python 3.14 en `C:\Python314\python.exe`, **solo biblioteca estándar**, `unittest`, comandos desde `DayZSandbox_dev/`, solo 127.0.0.1, ninguna clave en logs, salidas ni errores, y UTF-8 sin BOM con LF. Este brief **añade**; una línea que no haga falta tocar no se toca (R20).

## 2. El protocolo `dsbx1`

### 2.1 Transporte

- **Listener propio** en `127.0.0.1:<bridge_port>` (`backend.json`, por defecto `8766`), separado de la API del navegador (8765): sin cookies, sin CSRF, sin CORS y sin rutas de la web. Mismo proceso que el backend.
- **Clave en la consulta**: `?key=<peer_key>` en toda petición, porque el `RestContext` del mod la manda así (plan línea 93; medido en F0.2: `DSBX_QA_Probe.c:294,551`). Se compara con `hmac.compare_digest`; sin ella o mala → 401 `{"ok": false, "error": "bad_key"}` y nada más se procesa.
- **`peer_key`** se genera al primer arranque en `backend.json` como las otras claves (`secrets.token_urlsafe(32)`), es distinta de `human_key` y `ai_key` (el `Backend` no arranca con dos claves iguales o una vacía, como en F1b-web §2.1), y no aparece en ninguna respuesta de la API ni del bridge ni en el JavaScript (#22).
- **Logs**: el bridge escribe solo la línea de petición, con el valor de `key` sustituido por `***`; nunca cuerpos (#22; plan línea 93: «se quita de los logs»).
- **Tope `WIRE_CAP = 3500` bytes** UTF-8 para **todo cuerpo HTTP**, en los dos sentidos, el mismo de F0.3-0 v4.5 (§2.2.1, línea 109 de su brief), que sale de lo medido: `string.Replace` trunca en Enforce y `RestContext.POST` entrega 3728 B enteros (líneas 66-68 de ese brief).
  - Una petición con `Content-Length` mayor → 413 `{"ok": false, "error": "too_large"}`, sin leer el cuerpo, y se cierra la conexión.
  - Una respuesta nunca se trunca: el backend comprueba el cuerpo definitivo antes de enviarlo y, si pasara del tope, responde 500 `{"ok": false, "error": "wire_cap_exceeded"}` y registra el evento. Al encolar, una orden cuyo `/poll` pasaría del tope se rechaza en el acto (§3.1).
- **Una orden por poll** como mucho: es el régimen medido en S-puente (`n_ops` ≤ 1, órdenes de 222-271 B; F0.3-0 v4.5, línea 68) y el que adopta F0.3-0 (línea 119).

### 2.2 Identidades

- **`session`**: 16 hex (`secrets.token_hex(8)`), nueva en cada arranque del backend; la da `/hello`. Todo `/poll` y `/result` la lleva; si no es la actual → 409 `{"ok": false, "error": "hello_required"}` y el peer vuelve a presentarse.
- **`inst`**: 32 hex por arranque de cada peer (en el mod real, el UUID sin guiones construido con `Substring`, nunca con `Replace`: F0.3-0 v4.5, línea 118).
- **`epoch`** del mundo (#10): 32 hex que genera el peer servidor al arrancar la misión y que no cambia si solo se reinicia el backend. El peer cliente lo conoce por el servidor (en el mod real, sincronizado; en el falso, compartido) y lo declara en su `hello`.
- **Identidad de una orden: el par `(session, op_id)`** (corrige H1 de Sol, §2.7). `op_id` es el de la cola de la API (`op-<n>`, `server.py:235`) o, para las lecturas internas, `rd-<n>`; el contador vuelve a 1 en cada arranque del backend, así que **ninguna caché ni ningún registro puede indexar por `op_id` solo**.

### 2.3 Rutas

Todas con `?key=`. Cuerpos JSON compactos; toda respuesta lleva `ok`.

| Ruta | Quién | Petición | Respuesta 200 |
|---|---|---|---|
| `POST /hello` | los dos | `{proto: "dsbx1", peer: "server"\|"client", inst, epoch, mod_ver, build: "retail"\|"diag"}`; el servidor añade `map`, `world_size`, `modset` (lista de nombres) y `actor_engine` (`"expansion"`\|`"none"`) | `{ok: true, session, lease_ms: 3000, hold_ms: 2000, wire_cap: 3500}` |
| `GET /poll?peer=&inst=&session=[&deliver=0]` | los dos | — | `{ok: true, now_ms, ops: []}` o con una orden |
| `POST /result?peer=&inst=&session=` | los dos | `{op_id, session, epoch, status: "done"\|"rejected"\|"error", reason, dup, read}` | `{ok: true}` |
| `POST /catalog?peer=server&inst=&session=` | servidor | una página, §5 | `{ok: true, have, pages}` y, con la última, `complete: true` y `sha256` |

- **Orden**: `{op_id, session, epoch, inst, verb, args, issued_ms, ttl_ms}`, con `issued_ms` y `now_ms` en milisegundos del reloj monotónico del backend.
- **Errores** con `{ok: false, error}`: 400 `bad_request` (forma o tipos), 401 `bad_key`, 409 `proto_mismatch` (hello con otro `proto`), 409 `hello_required` (`session` o `inst` que no son los registrados), 409 `unknown_op` (resultado de una orden que no existe en esta sesión), 409 `bad_catalog`, 413 `too_large` y 500 `wire_cap_exceeded`.
- **`deliver=0`** (poll de mantenimiento): pasa las mismas guardas y responde enseguida `{ok: true, now_ms, ops: []}`, sin retener ni tocar la cola (F0.3-0 v4.5, línea 626).

### 2.4 Lo que cumple cada peer

Es el contrato del mod falso ahora y del mod real después.

1. **Validar todo 200** (corrige H5). Un hello vale solo con `ok` presente y `true`, `session` de 16 hex, `lease_ms > 0`, `hold_ms > 0` y `wire_cap >= 1024`. Un poll vale solo con `ok` `true`, `now_ms` finito y `ops` lista de 0 o 1 órdenes bien formadas. Un acuse vale solo con `ok` presente y `true`. Un 200 que no vale cuenta como fallo: no renueva el lease y se reintenta.
2. **Hombre muerto en los dos peers** (corrige H3). `lease_age` = ahora − último poll 200 válido, sea entregador o de mantenimiento, en el reloj local del peer.
   - Antes de **cada efecto** de una orden, con `lease_age > lease_ms`, no hay efecto y el resultado es `rejected/lease_expired`.
   - Durante un trabajo de más de 500 ms, el peer manda un `/poll?deliver=0` cada 500 ms, siempre uno en vuelo como mucho.
   - La limpieza de seguridad (soltar la cámara, devolver el control) nunca se bloquea (F0.3-0 v4.5, líneas 628-631; aplica desde F4).
3. **Primero, la deduplicación** (corrige H1 y H2). Una caché de los **últimos 1024** resultados, todos (`done`, `rejected` y `error`), indexada por `(session, op_id)`, con expulsión FIFO que conserva el orden (en Enforce, `RemoveOrdered(0)` y nunca `Remove(0)`: F0.3-0 v4.5, línea 595).
   - Una orden repetida devuelve el resultado guardado con `dup: true`, sin efecto y **antes de cualquier otra comprobación**. Si no, una orden ya ejecutada que se reentrega tarde volvería como `expired` y la web daría por fallido algo hecho (D2).
   - La caché no se vacía al presentarse otra vez: las entradas de otras sesiones simplemente envejecen.
4. **Después, las comprobaciones** de una orden nueva, en este orden, cada una con su `rejected/<motivo>` y sin efecto:
   - `order.session` es la actual (`stale_session`);
   - `order.inst` es el propio (`stale_inst`);
   - `order.epoch` es el del mundo que conoce (`stale_epoch`);
   - `ttl_ms − (now_ms − issued_ms) > 0`, con `now_ms` del mismo poll (`expired`).
5. **Resultados**:
   - antes de recibir más órdenes, primero los resultados pendientes;
   - reintentos a los 250, 500 y 1000 ms; se abandona tras 4 fallos o con un 409 `unknown_op`;
   - un resultado que pasaría de `WIRE_CAP` se sustituye por `error/result_too_large` con `read` vacío, nunca recortado; en Enforce, sin `string.Replace` sobre cuerpos (F0.3-0 v4.5, líneas 113 y 118).

### 2.5 Lo que cumple el backend

1. **Entrega**: en cada `/poll` entregador de un peer, la primera orden elegible para su papel y su `inst` actual, con TTL restante > 0. Primero las lecturas internas, luego por orden de llegada. Sin orden, retiene hasta `hold_ms` (2000) y responde con `ops: []`.
2. **Reentrega**: una orden `ejecutando` sin resultado `retry_ms` (2000) después de entregarla vuelve a entregarse, dentro de su TTL, **solo a la misma `inst`** que la recibió. A otra `inst` nunca: un peer reiniciado tiene la caché vacía y repetiría el efecto.
3. **Resultados repetidos**: el resultado de una orden ya terminal se acusa con 200 y no cambia nada (deduplicación en el backend; los reintentos de RestApi, plan línea 93).
4. **TTL**: `ttl_ms` por orden (por defecto 10000, por encima del `max_ms` medido de 8679), contado desde que entra en la cola. Lo vigila un barrido cada 250 ms, `Bridge.sweep()`, que las pruebas llaman directamente con el reloj inyectado.
5. **Cola acotada** (#22): como mucho `queue_max` = 32 órdenes vivas (`pendiente` o `ejecutando`). Con la cola llena, `POST /api/apply` → 409 `queue_full` y no crea nada.

### 2.6 Constantes

`WIRE_CAP` 3500 · `lease_ms` 3000 · `hold_ms` 2000 · mantenimiento cada 500 ms · `retry_ms` 2000 · `ttl_ms` 10000 · `queue_max` 32 · caché 1024 · barrido cada 250 ms. Todas, salvo `WIRE_CAP`, son parámetros de `Bridge(...)` para que las pruebas las acorten.

### 2.7 Qué corrige respecto al bridge QA

La revisión de Sol sobre #6 (`C:\tmp\dsbx-f02\sol\LAST_v1.md`) encontró defectos de diseño que `dsbx1` no repite:
- **H1** (`LAST_v1.md:9-14`): el bridge QA vuelve a contar desde `op-1` y una corrida nueva recibe resultados viejos como `dup` → aquí la identidad es `(session, op_id)` (§2.2) y la caché se indexa por el par.
- **H2** (`:16-21`): en Enforce, `Remove(0)` no conserva el orden y la caché expulsa lo reciente → aquí la expulsión es FIFO (§2.4.4).
- **H3** (`:23-28`): el hombre muerto solo existía en el cliente y no había polls durante los trabajos largos → aquí va en los dos peers, con polls de mantenimiento (§2.4.2).
- **H5** (`:36-40`): la sonda aceptaba un hello con `ok: false` y no comprobaba el acuse → aquí se valida todo 200 (§2.4.1).

H4 y H6 son de la implementación QA (presupuesto de callbacks y regla estática de la clave) y los hereda el mod real cuando exista.

## 3. Estados y transiciones (#23, D2)

### 3.1 La orden de la API

`POST /api/apply` sigue creando la orden `pendiente` con origen `backend` (F1a; F1b-web §4), y ahora además la mete en la cola del bridge como `scene.apply` para el papel `server`, con `args` `{doc_id, rev, hash}`. Si la cola está llena, 409 `queue_full` antes de crearla.

Cada transición pasa por un único método nuevo del `Backend`, `set_op_state(op_id, state, origin, reason=None)`. Dentro de `store.lock`, ese método:
- actualiza `state`, `origin`, `reason` y `at_ms` de `backend.ops[op_id]`;
- actualiza `op_mono[op_id]` (F1b-web §4);
- emite `op.state`, que sigue sin `age_ms` y gana el campo `reason`.

| De | A | Cuándo | `origin` | `reason` |
|---|---|---|---|---|
| — | `pendiente` | al crearla (como hoy) | `backend` | — |
| `pendiente` | `ejecutando` | se entrega en un `/poll` | `backend` | `entregada` |
| `ejecutando` | `aplicado` | resultado `done` | `servidor` | — |
| `aplicado` | `observado` | en el mismo resultado, si el predicado de su verbo (§3.2) se cumple sobre `read` | `servidor` | — |
| `aplicado` | `fallido` | el predicado no se cumple | `servidor` | `lectura_no_cumple` |
| `ejecutando` | `fallido` | resultado `rejected` (el peer no hizo nada) | `servidor` | el motivo del peer |
| `ejecutando` | `parcial` | resultado `error` | `servidor` | el motivo del peer |
| `pendiente` | `fallido` | vence su TTL sin entregarse | `backend` | `no_entregada` |
| `ejecutando` | `parcial` | vence su TTL sin resultado | `backend` | `sin_resultado` |
| `ejecutando` | `parcial` | el peer servidor se presenta con otro `epoch` | `backend` | `mundo_reiniciado` |
| `parcial` | `observado` | una lectura del mundo (§4) muestra su generación | `servidor` | `reconciliada` |

- **Nunca hacia atrás**: ninguna orden vuelve a `pendiente`, y una orden entregada nunca pasa a «no ocurrió» (#23). Desde `ejecutando`, sin resultado, solo cabe `parcial`.
- `observado`, `fallido` y `parcial` son terminales, salvo `parcial` → `observado` por reconciliación.
- `aplicado` y `observado` llegan en el mismo resultado, como dos eventos `op.state` en ese orden.

### 3.2 Verbos

- **`scene.apply`** (servidor), con `args` `{doc_id, rev, hash}`. El mod falso anota la generación `{session, op_id, rev, hash}`; el real aplicará la escena en F2 (#9). `read` es el estado del mundo de §4. **Predicado**: `read.epoch` es el `epoch` actual y `read.generation` es `{session, op_id, rev, hash}` de esta orden.
- **`state.read`** (servidor, interna): `args` `{}`, `read` = el estado del mundo de §4. No crea fila en la cola de la API ni eventos `op.state`.

## 4. Reconciliación del mundo (#10, CX-07)

- **Estado del mundo** (el `read` de los dos verbos): `{epoch, generation: {session, op_id, rev, hash} | null, registry_n, registry_sha256}`. El registro de entidades es de F2; aquí el mod falso da `registry_n` y `registry_sha256` de un registro vacío.
- **Al presentarse el peer servidor** (`inst` nueva, sesión nueva o arranque del backend):
  - el backend lo marca **sin reconciliar** y encola un `state.read` con prioridad;
  - **no entrega ningún `scene.apply` hasta tener su resultado** («antes de autorizar nada»);
  - con el `read`, guarda el estado del mundo y queda reconciliado.
- **`epoch` distinto del conocido en esta sesión del backend** (servidor de DayZ reiniciado): las órdenes `ejecutando` pasan a `parcial/mundo_reiniciado` y las `pendiente` siguen en cola, para entregarse con el `epoch` nuevo.
- **Cada vez que una orden pasa a `parcial`**, se encola un `state.read`, como mucho uno pendiente a la vez. Si la lectura muestra en `generation` el `(session, op_id)` de una orden `parcial`, esta pasa a `observado/reconciliada`. Es el «parcial hasta reconciliar» de D2 (plan línea 170).
- **Peer cliente**: está «en el mundo» solo si su `epoch` es el del servidor reconciliado. En F1b-bridge no recibe órdenes.
- **Tras reiniciar el backend**, la cola de la API se pierde, como en F1a: la primera lectura del mundo fija la base de la sesión nueva.

## 5. Catálogo (#8)

- **Página**: `{catalog_id: 16 hex, page, pages, build, modset_hash: 64 hex, classes: [[clase, base], ...]}`, cada una ≤ `WIRE_CAP`. Las páginas pueden llegar en cualquier orden; una repetida idéntica es idempotente.
- **Al completarse**: el backend comprueba que no hay clases repetidas y que todas las páginas declaran el mismo `catalog_id`, `pages`, `build` y `modset_hash`. Si cuadra, guarda en memoria `Bridge.catalog = {catalog_id, build, modset_hash, n_classes, sha256, classes}`, con `sha256` sobre el JSON canónico de la lista ordenada.
- **Si algo no cuadra** → 409 `bad_catalog` y se descarta ese `catalog_id`.
- **Fuera de alcance**: guardarlo en disco y usarlo para validar (F2).

## 6. El mod falso (`app/tests/fake_mod.py`)

- **Estructura**: `FakeMod(bridge_url, peer_key, ...)` arranca los dos peers en hilos, cada uno con su `inst`, y el servidor genera el `epoch`. Cumple §2.4 entero.
- **Lado servidor**:
  - responde `state.read` y `scene.apply`;
  - sube un catálogo de prueba en páginas al presentarse;
  - lleva un contador de efectos por `(session, op_id)`, para que las pruebas cuenten ejecuciones reales.
- **Inyección de fallos**: atributos y métodos solo para pruebas, sin rutas de depuración en el backend.
  - perder el próximo resultado o el próximo acuse;
  - cortar los polls de un peer durante N ms;
  - un trabajo lento de N ms, con o sin polls de mantenimiento;
  - reiniciar el servidor (`epoch`, `inst` y caché nuevos) o el cliente;
  - presentarse con un 200 inválido simulado (para H5, sobre su función de validación).
- **CLI**: `python app/tests/fake_mod.py --config backend.json` lo conecta al backend local, para ver transiciones reales en la web sin DayZ.

## 7. Aceptación (R26)

Gate: el de F1b-web §7, con las pruebas nuevas dentro de la suite y el arnés E2E con dos pasos más. Las pruebas usan el `Bridge` real en un hilo con puerto 0 y constantes acortadas.

| # | Positivo | Negativo (el defecto que detecta) |
|---|---|---|
| BR1 hello | Hello válido de los dos peers → `ok`, `session` de 16 hex, `lease_ms` y `hold_ms` | Clave mala o ausente → 401 y nada registrado; `proto` distinto → 409; cuerpo mal formado → 400; la línea de log lleva `key=***` |
| BR2 poll | Una orden por poll como mucho; sin órdenes, vuelve con `ops: []` en `hold_ms` ± 0,5 s; `deliver=0` responde enseguida y no entrega aunque haya orden | `session` o `inst` viejas → 409 `hello_required`, sin entrega |
| BR3 D2 de punta a punta | Con el mod falso: `apply` → `pendiente` → `ejecutando` → `aplicado` → `observado`, con orígenes y motivos de §3.1, `op_mono` actualizado y los `op.state` en ese orden por el SSE | Predicado que no se cumple (el mod falso anota otra `rev`) → `fallido/lectura_no_cumple`, nunca `observado` |
| BR4 sin peer | Sin mod falso, la orden sigue `pendiente` hasta su TTL y pasa a `fallido/no_entregada` | Nunca `aplicado` ni `observado` (el negativo de D2) |
| BR5 resultado perdido | El mod ejecuta y pierde el resultado → reentrega a la misma `inst` → `dup: true` → `observado`, y el contador de efectos queda en 1; también si la reentrega llega con el TTL ya vencido en el peer | Acuse perdido → el resultado repetido no crea un segundo evento |
| BR6 peer reiniciado | El mod ejecuta y reinicia el servidor antes de mandar el resultado: no hay reentrega a la `inst` nueva; al vencer el TTL, `parcial/sin_resultado`; la lectura del mundo lo pasa a `observado/reconciliada`; efectos = 1 | Una reentrega a la `inst` nueva haría 2 efectos (X3 e) |
| BR7 H1 | Backend reiniciado con el mod falso vivo: la orden `(S2, op-1)` se ejecuta, `dup: false`, y los efectos de `op-1` suben aunque la caché tenga `(S1, op-1)` | Con la caché indexada por `op_id` solo, devuelve el resultado viejo (X3 a) |
| BR8 H2 | Tras 1025 órdenes distintas, la caché tiene exactamente las últimas 1024 en orden; una reentrega de una reciente sigue siendo `dup` | Una expulsión que no conserva el orden pierde una reciente (X3 b) |
| BR9 H3 | Un trabajo de 5 s con polls de mantenimiento termina `done`; los dos peers renuevan el lease con `deliver=0` | Sin mantenimiento o con los polls cortados más de `lease_ms`: `rejected/lease_expired` y efectos = 0; el peer cliente también deja de dar su lease por bueno |
| BR10 H5 | — | El mod falso no da por buenos un hello con `ok` ausente o `false`, con `lease_ms` 0 o con `session` mal formada, ni un poll sin `now_ms`, ni un acuse sin `ok`: no renueva el lease y reintenta |
| BR11 TTL en el peer | — | Orden con el TTL ya vencido al llegar → `rejected/expired`, efectos = 0 y `fallido` |
| BR12 epoch | Servidor reiniciado (`epoch` nuevo) con una orden `ejecutando` → `parcial/mundo_reiniciado`; la `pendiente` se entrega con el `epoch` nuevo | Cliente con otro `epoch` → fuera del mundo; orden con `epoch` viejo → `rejected/stale_epoch` |
| BR13 reconciliar antes de autorizar | Tras el hello del servidor, el primer `scene.apply` se entrega después del resultado de `state.read` | — |
| BR14 cola acotada | 32 órdenes vivas → la 33.ª `apply` → 409 `queue_full`, sin orden ni evento | — |
| BR15 `WIRE_CAP` | Una página de catálogo de 3500 B entra | Una petición de 3501 B → 413 sin leer el cuerpo; un resultado que pasaría del tope → `error/result_too_large` → `parcial`; una orden que no cabría → rechazada al encolar |
| BR16 catálogo | Páginas desordenadas y una repetida → `complete` con el `sha256` esperado | Clase repetida o `pages` incoherente → 409 `bad_catalog` |
| BR17 secretos | — | `peer_key` igual a otra clave → el `Backend` no arranca; `peer_key` no aparece en ninguna respuesta de la API ni del bridge, ni en logs ni en la salida de las pruebas |
| P10 web con mod falso | En el E2E: con el mod falso conectado, «Aplicar» lleva la fila a Observado con origen `servidor` | — |
| P11 web sin mod | — | Con el mod parado, la fila pasa de Pendiente a Fallido (TTL acortado en el arnés), nunca a Aplicado |
| X3 antitautología | — | El orquestador corre las pruebas contra el código mutado: (a) caché por `op_id` solo; (b) expulsión que no conserva el orden; (c) sin comprobar el lease antes del efecto; (d) aceptar `ok` ausente o `false`; (e) reentrega a otra `inst`; (f) TTL de una entregada → `fallido` en vez de `parcial`; (g) `scene.apply` antes de `state.read`; (h) cola sin tope; (i) resultado repetido que vuelve a transicionar; (j) el peer sin comprobar `epoch`; (k) `observado` sin predicado; (l) `key` sin redactar en el log; (m) la deduplicación después del TTL. Cada una tiene que hacer fallar al menos una prueba |

P1-P9b y las 113 pruebas actuales tienen que seguir pasando sin cambios. El arnés arranca el bridge en todas las corridas, pero con un TTL largo hasta P9b, para que ninguna orden de esos pasos caduque, y solo arranca el mod falso en P10.

## 8. Ficheros

```
DayZSandbox_dev/
  plans/2026-11-14-m1-f1b-bridge-brief.md   este brief                         [orquestador]
  app/backend/bridge.py                     §2, §3, §4 y §5 (lado backend)     [F1bb-1]
  app/backend/server.py                     cableado: Bridge, set_op_state, cola en apply,
                                            peer_key y bridge_port en load_config y main   [F1bb-1]
  app/tests/test_bridge.py                  BR1, BR2, BR4, BR13-BR17, con un peer de prueba
                                            mínimo por HTTP                    [F1bb-1]
  app/tests/fake_mod.py                     §6                                  [F1bb-2]
  app/tests/test_fake_mod.py                BR3, BR5-BR12 contra el Bridge real [F1bb-2]
  app/tests/e2e_web.py, app/web/e2e/queue.e2e.cjs   P10 y P11              [F1bb-2]
```

**No se tocan** `store.py`, `validate.py`, `lease.py`, `app/mcp/`, la web (`app/web/src`, que ya pinta estados, edad y origen), el esquema, las fixtures ni ninguna prueba existente, salvo el arnés y el guion E2E para P10 y P11.

## 9. Entrega

| Tanda | Worker | Escribe |
|---|---|---|
| F1bb-1 | Muse (`muse-wonder-1.0`, CLI nativo, sandbox de ficheros activo y red habilitada) | `bridge.py`, el cableado de `server.py` y `test_bridge.py` |
| F1bb-2 | Muse, sobre F1bb-1 ya revisada | `fake_mod.py`, `test_fake_mod.py`, P10 y P11 |

Cada tanda trabaja en una copia aparte del commit congelado (el sandbox deja restos en el directorio de trabajo). El orquestador:
- revisa el diff;
- corre el gate y X3 sin fiarse de los recibos;
- integra y hace commit en `claude/f1b-bridge`.

Push y PR, solo con el visto bueno de Guillermo. Después, Sol revisa el código.

## 10. Riesgos y lo que no se ha medido

- **El `RestContext` real** solo está medido con la clave en la consulta, 3728 B por POST y órdenes de hasta 271 B. Un `/poll` cerca de `WIRE_CAP`, las cabeceras que manda y sus reintentos propios se miden cuando exista el mod real (F0.3-0 v4.5 lo mide en su base en partida, líneas 66-68).
- **La ventana del hombre muerto** medida en retail (acepta ≤ 2756 ms y rechaza ≥ 3037 ms) es la del cliente QA. La de cada peer de `dsbx1` se mide en partida con el mod real (H3).
- **`max_ms` de 8679 en S-puente**: una orden suelta puede tardar 8,7 s. Por eso el TTL es de 10 s y una orden entregada sin resultado pasa a `parcial`, nunca a «no ocurrió».
- **La cola sigue en memoria** (F1a): reiniciar el backend la pierde, y la reconciliación (§4) solo recupera lo que el mundo diga.
- **Un solo proceso** sirve la API y el bridge; un long-poll ocupa un hilo por peer (2 en total).
