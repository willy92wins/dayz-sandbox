# F1b-bridge sin juego: protocolo `dsbx1`, lado del backend y mod falso

2026-11-14 · tarea **F1b-bridge** (subfase offline de F1b), rama `claude/f1b-bridge` (apilada sobre `claude/f1b-web`, que lleva los arreglos de la revisión del código del PR #7) · spec de implementación (R25) de lo que queda de F1b tras F1b-web: [plan v2](2026-10-26-m1-cine-v2.md) F1 (líneas 88, 89 y 91), decisiones #2, #3, #8, #9, #10, #22, #23 y #24 · contrato: `DayZSandbox_dev/product-spec.md`, D2 (línea 88), E1 (99) y E3 (101) · v1.2, tras la ronda 2 de Sol (§12).

**Por qué ahora.** S-puente pasó en retail (PR #6, `origin/claude/f0.2-sonda` `9103b5b`). En `evidence/m1/S-puente/retail-20261114T151150Z/verdict.json` (líneas 84-98): `PASA` 16/16, `p50_ms` 200,8, `p95_ms` 603,1, `max_ms` 8679 (un caso suelto) y 0 timeouts; con `lease_ms` = 3000, la ventana acepta hasta 2756 ms y rechaza desde 3037 ms. Guillermo aprobó F1b-bridge el 2026-11-14 en la sesión principal («Sí, arráncalo»).

**Qué hay ya.** `app/backend/server.py` (F1a, F1-co y F1b-web): `POST /api/apply` crea una orden `pendiente` con la `rev` y el `hash` congelados (`server.py:229-238`), con `origin` y `op_mono` (F1b-web §4, líneas 85-89), y nada la despacha. La web enseña los seis estados de #23 con su edad y su origen. El bridge QA de F0.2 (`qa/bridge_qa.py`, `qa/fake_peer.py` y la sonda en Enforce) es el **patrón medido**, no el producto: `dsbx1` es un protocolo nuevo que corrige sus defectos de diseño (§2.8).

**Proceso.** Como F1b-web: dos tandas en serie (§9), el orquestador revisa e integra, y Sol revisa este brief hasta VERDE (0 bloqueantes, 4 rondas como mucho) y el código después. Sin lanzar DayZ.

## 0. Qué es y qué no

**Es una subfase offline.** Cierra el contrato y el lado del backend. **No cierra F1b**, que necesita además los peers reales en partida (F1b-peers, §11).

Es:
- el **protocolo `dsbx1`** entre el backend y los dos peers del mod (#3), escrito aquí como contrato que cumplen tanto el mod falso de ahora como el mod real de después (§2);
- el **lado del backend** (`app/backend/bridge.py`, un listener propio en 127.0.0.1):
  - handshake y entrega por long-poll;
  - resultados, TTL por orden y deduplicación;
  - cola acotada con las transiciones reales de #23;
  - generaciones de conexión, para que reconectar no ejecute la cola vieja (E1);
  - reconciliación del mundo antes de autorizar nada (#10, CX-07);
  - ingesta del catálogo (#8, plan F1 línea 89);
- el **mod falso** en Python (`app/tests/fake_mod.py`, #24, plan F1 línea 91): los dos peers con todo §2.4 y la inyección de fallos para las pruebas;
- el **cableado**: las órdenes de `POST /api/apply` viajan al peer servidor como `scene.apply`, y sus transiciones llegan a la web por el SSE que ya existe.

No es:
- **los peers reales en Enforce** (el mod núcleo `DayZSandbox/`, que aún no existe), ni la medida de E1 en retail. Es la continuación **F1b-peers** (§11), con su dueño, sus ficheros y su gate en partida, y pide el visto bueno de Guillermo para lanzar DayZ;
- la semántica real de `scene.apply`, del reset y de la observación (F2, #9: lotes, etapas, compensación y registro con entidades). Aquí el mod falso solo simula dos pasos con efecto y anota la generación;
- los verbos de cámara, ambiente y actores (F3-F5). El peer cliente solo se presenta, hace poll y mantiene su lease;
- usar el catálogo recibido para validar escenas (F2 decide cómo se mapean clases a tipos y topes): aquí solo se recibe, se valida y se guarda;
- la mezcla de E2 y cualquier medida en partida (F6 y F1b-peers).

Trazabilidad (R20): §2 sale de #3, #9, #10, #22, #23, de la fila S-puente (plan línea 66), de la fila E1 (174) y de la revisión de Sol sobre #6; §3, de #22 y #23; §4, de #10 y CX-07; §5, de #8; §6, de #24; §7, de D2 y E1; §11, de F1 (líneas 89 y 93). Lo que no trace a esto no entra.

## 1. Entorno y fronteras

Como F1b-web §1: Python 3.14 en `C:\Python314\python.exe`, **solo biblioteca estándar**, `unittest`, comandos desde `DayZSandbox_dev/`, solo 127.0.0.1, ninguna clave en logs, salidas ni errores, y UTF-8 sin BOM con LF. Este brief **añade**; una línea que no haga falta tocar no se toca (R20).

## 2. El protocolo `dsbx1`

### 2.1 Transporte

- **Listener propio** en `127.0.0.1:<bridge_port>` (`backend.json`, por defecto `8766`), separado de la API del navegador (8765): sin cookies, sin CSRF, sin CORS y sin rutas de la web. Mismo proceso que el backend.
- **Clave en la consulta**: `?key=<peer_key>` en toda petición, porque el `RestContext` del mod la manda así (plan línea 93; medido en F0.2: `DSBX_QA_Probe.c:294,551`). Se compara con `hmac.compare_digest`; sin ella o mala → 401 `{"ok": false, "error": "bad_key"}` y nada más se procesa.
- **`peer_key`** se genera al primer arranque en `backend.json` como las otras claves (`secrets.token_urlsafe(32)`), es distinta de `human_key` y `ai_key` (el `Backend` no arranca con dos claves iguales o una vacía, como en F1b-web §2.1), y no aparece en ninguna respuesta de la API ni del bridge ni en el JavaScript (#22).
- **Logs**: el bridge escribe solo la línea de petición, con el valor de `key` sustituido por `***`; nunca cuerpos (#22; plan línea 93: «se quita de los logs»).
- **Tope `WIRE_CAP = 3500` bytes** UTF-8 para **todo cuerpo HTTP**, en los dos sentidos, el mismo de F0.3-0 v4.5 (`9998c05`, línea 109 de su brief), que sale de lo medido: `string.Replace` trunca en Enforce y `RestContext.POST` entrega 3728 B enteros (líneas 66-68 de ese brief).
  - Una petición con `Content-Length` mayor → 413 `{"ok": false, "error": "too_large"}`, sin leer el cuerpo, y se cierra la conexión.
  - Una respuesta nunca se trunca: el backend comprueba el cuerpo definitivo antes de enviarlo y, si pasara del tope, responde 500 `{"ok": false, "error": "wire_cap_exceeded"}` y registra el evento. Al encolar, una orden cuyo `/poll` pasaría del tope se rechaza en el acto (§3.1).
- **Una orden por poll** como mucho, y **una orden en curso por peer** (§2.4.2): es el régimen medido en S-puente (`n_ops` ≤ 1, órdenes de 222-271 B; F0.3-0 v4.5, línea 68) y el que adopta F0.3-0 (líneas 119 y 623).

### 2.2 Identidades

- **`session`**: 16 hex (`secrets.token_hex(8)`), nueva en cada arranque del backend; la da `/hello`. Todo `/poll` y `/result` la lleva; si no es la actual → 409 `{"ok": false, "error": "hello_required"}` y el peer vuelve a presentarse.
- **`inst`**: 32 hex por arranque de cada peer (en el mod real, el UUID sin guiones construido con `Substring`, nunca con `Replace`: F0.3-0 v4.5, línea 118).
- **`epoch`** del mundo (#10): 32 hex que genera el peer servidor al arrancar la misión y que no cambia si solo se reinicia el backend o se recrea el peer. El peer cliente lo conoce por el servidor (en el mod real, sincronizado; en el falso, compartido) y lo declara en su `hello`.
- **Generación de conexión `conn`**, un entero del backend por peer. Sube cada vez que ese peer se presenta y cada vez que el backend lo da por perdido (§2.5.3). **Viaja en el protocolo** (corrige B2-01): la devuelve `/hello`, cada `/poll` la lleva y cada orden la lleva. Así, un poll retenido de una conexión anterior se distingue de uno nuevo aunque la `session` y la `inst` sean las mismas.
- **Toda orden nace atada a la `conn` vigente del servidor y solo se entrega dentro de ella**: reconectar nunca ejecuta la cola vieja (E1, plan línea 174).
- **Identidad de una orden: el par `(session, op_id)`** (corrige H1 de Sol, §2.8). `op_id` es el de la cola de la API (`op-<n>`, `server.py:235`) o, para las lecturas internas, `rd-<n>`. El contador vuelve a 1 en cada arranque del backend, así que **ninguna caché ni ningún registro puede indexar por `op_id` solo**.

### 2.3 Rutas

Todas con `?key=`. Cuerpos JSON compactos; toda respuesta lleva `ok`.

| Ruta | Quién | Petición | Respuesta 200 |
|---|---|---|---|
| `POST /hello` | los dos | `{proto: "dsbx1", peer: "server"\|"client", inst, epoch, mod_ver, build: "retail"\|"diag"}`; el servidor añade `map`, `world_size`, `modset` (lista de nombres) y `actor_engine` (`"expansion"`\|`"none"`) | `{ok: true, session, conn, lease_ms: 3000, hold_ms: 2000, wire_cap: 3500}` |
| `GET /poll?peer=&inst=&session=&conn=[&deliver=0]` | los dos | — | `{ok: true, now_ms, ops: []}` o con una orden |
| `POST /result?peer=&inst=&session=` | los dos | `{op_id, session, epoch, status: "done"\|"rejected"\|"error", reason, dup, read}` | `{ok: true}` |
| `POST /catalog?peer=server&inst=&session=` | servidor | una página, §5 | `{ok: true, have, pages}` y, con la última, `complete: true` y `sha256` |

- **Orden**: `{op_id, session, conn, epoch, inst, verb, args, issued_ms, ttl_ms}`, con `issued_ms` y `now_ms` en milisegundos del reloj monotónico del backend.
- **Errores** con `{ok: false, error}`:
  - 400 `bad_request` (forma o tipos);
  - 401 `bad_key`;
  - 409 `proto_mismatch` (hello con otro `proto`);
  - 409 `hello_required` (`session`, `inst` o `conn` que no son las vigentes, también la de una conexión que el backend dio por perdida);
  - 409 `unknown_op` (resultado de una orden que no existe en esta sesión);
  - 409 `bad_catalog`;
  - 413 `too_large`;
  - 500 `wire_cap_exceeded`.
- **`deliver=0`** (poll de mantenimiento): pasa las mismas guardas y responde enseguida `{ok: true, now_ms, ops: []}`, sin retener ni tocar la cola (F0.3-0 v4.5, línea 626).

### 2.4 Lo que cumple cada peer

Es el contrato del mod falso ahora y del mod real después.

1. **Validar todo 200** (corrige H5). Un 200 que no vale cuenta como fallo: no renueva el lease y se reintenta.
   - Un hello vale solo con `ok` presente y `true`, `session` de 16 hex, `lease_ms > 0`, `hold_ms > 0` y `wire_cap >= 1024`.
   - Un poll vale solo con `ok` `true`, `now_ms` finito y `ops` lista de 0 o 1 órdenes bien formadas.
   - Un acuse vale solo con `ok` presente y `true`.
2. **Una orden en curso** (corrige B-03). Mientras ejecuta una orden o tiene un resultado sin acusar, el peer solo manda `/poll?deliver=0`, uno cada 500 ms, uno en vuelo como mucho, y nunca un poll entregador. Primero se envían los resultados pendientes; después vuelve el poll entregador (F0.3-0 v4.5, líneas 119 y 623).
3. **Plazo local** (corrige B-01). Al recibir una orden, el peer fija `plazo_local = t_envío + (ttl_ms − (now_ms − issued_ms)) − 100 ms`, en su reloj local:
   - `t_envío` es el instante local en que **mandó** el poll que la trajo;
   - `now_ms` es el de la respuesta de ese mismo poll.

   El backend genera la respuesta después de que el peer manda la petición, así que el instante local de `now_ms` es ≥ `t_envío`. Por eso `t_envío` + lo que queda es ≤ el plazo real, haya el tránsito o la espera que haya. Los 100 ms cubren la duración de un efecto ya empezado.
4. **Primero, la deduplicación** (corrige H1, H2, B-03 y B-04). La caché, indexada por `(session, op_id)`, guarda tanto las órdenes **en curso** como los resultados (`done`, `rejected` y `error`).
   - Una orden repetida que ya está en curso se ignora: no se ejecuta otra vez y el resultado lo dará la primera.
   - Una repetida ya terminada devuelve el resultado guardado con `dup: true`, sin efecto.
   - Las dos reglas van **antes de cualquier otra comprobación**. Si no, una orden ya ejecutada que se reentrega tarde volvería como `expired` y la web daría por fallido algo hecho (D2).
   - **Retención.** Una entrada no se expulsa mientras su orden pueda reentregarse, es decir, hasta su `plazo_local` + 1 s. Pasado eso, se expulsa en orden FIFO (en Enforce, `RemoveOrdered(0)` y nunca `Remove(0)`: F0.3-0 v4.5, línea 595).
   - **Capacidad.** Hay sitio para 1024 entradas. Con la caché llena de entradas vivas, el peer no pide órdenes nuevas (solo `deliver=0`) hasta que caduque alguna: es contrapresión, no expulsión.
   - La caché no se vacía al presentarse otra vez: las entradas de otras sesiones simplemente envejecen.
5. **Comprobaciones de una orden nueva**, en este orden, cada una con su `rejected/<motivo>` y sin efecto:
   - `order.session` es la actual (`stale_session`);
   - `order.inst` es el propio (`stale_inst`);
   - `order.conn` es la de su presentación vigente (`stale_conn`);
   - `order.epoch` es el del mundo que conoce (`stale_epoch`);
   - todavía no ha pasado `plazo_local` (`expired`).
6. **Antes de cada efecto** (corrige H3, B-01 y B-05), el peer comprueba dos cosas:
   - **`lease_age ≤ lease_ms`**, con `lease_age` = ahora − último poll 200 válido, entregador o de mantenimiento, en su reloj local;
   - **que no haya pasado `plazo_local`**.

   Si falla alguna, se para: **sin ningún efecto todavía**, `rejected/lease_expired` o `rejected/expired`; **con algún efecto ya hecho**, `error/lease_expired` o `error/expired`. `rejected` queda reservado para «el peer no tocó nada». La limpieza de seguridad (soltar la cámara, devolver el control) nunca se bloquea (F0.3-0 v4.5, líneas 628-631; aplica desde F4).
7. **Resultados**:
   - `done` si terminó, `error` si se interrumpió o falló después de algún efecto, `rejected` solo sin ningún efecto;
   - reintentos a los 250, 500 y 1000 ms; se abandona tras 4 fallos o con un 409 `unknown_op`, y el resultado queda en la caché para una reentrega;
   - un resultado que pasaría de `WIRE_CAP` se sustituye por `error/result_too_large` con `read` vacío, nunca recortado; en Enforce, sin `string.Replace` sobre cuerpos (F0.3-0 v4.5, líneas 113 y 118).

### 2.5 Lo que cumple el backend

1. **Entrega**: en cada `/poll` entregador de un peer, la primera orden elegible para su papel. Primero las lecturas internas y luego por orden de llegada. Es elegible si:
   - es de la `conn` vigente;
   - se entrega a la `inst` actual del peer;
   - le queda TTL;
   - en el caso de `scene.apply`, el servidor está reconciliado (§4).

   Sin orden, el backend retiene hasta `hold_ms` (2000) y responde con `ops: []`.
2. **Reentrega**: una orden `ejecutando` sin resultado `retry_ms` (2000) después de entregarla vuelve a entregarse, dentro de su TTL, **solo a la misma `inst` y en la misma `conn`**. A otra `inst` nunca: un peer recreado tiene la caché vacía y repetiría el efecto.
3. **Conexión perdida** (corrige B-02 y B-06). El backend da por perdido al servidor cuando no tiene ningún poll en curso y han pasado más de `lease_ms` desde el último poll que atendió, sea entregador o de mantenimiento: es la misma ventana que el peer usa para dejar de actuar. También cuando el servidor se presenta otra vez, con `inst` nueva, `epoch` nuevo o en una sesión nueva. Entonces `conn` sube y:
   - las órdenes `pendiente` de la `conn` anterior pasan a `fallido`, con motivo `mundo_reiniciado` si cambió el `epoch` y `conexion_perdida` si no: nunca se entregaron, así que no hubo efecto;
   - las `ejecutando` de la `conn` anterior pasan a `parcial`, con el mismo criterio de motivo;
   - los polls de la conexión perdida reciben 409 `hello_required`, porque reconectar exige presentarse y reconciliar (#10).
4. **Resultados** (corrige B-08). El **primer** resultado de una orden se aplica tanto si está `ejecutando` como si ya está `parcial` (una confirmación tardía es información, §3.1). Los siguientes se acusan con 200 y no cambian nada: es la deduplicación del backend, que también cubre los reintentos de RestApi (plan línea 93).
   - Un resultado se acepta **aunque su `conn` se haya perdido**: es un hecho sobre una orden que ya se entregó. Se identifica por `(session, op_id)` y por la `inst` a la que se entregó.
   - Solo los polls de una conexión perdida reciben 409; los resultados no.
5. **TTL**: `ttl_ms` por orden (por defecto 10000, por encima del `max_ms` medido de 8679), contado desde que entra en la cola. Lo vigila un barrido cada 250 ms, `Bridge.sweep()`, que también vigila la pérdida de conexión del punto 3. Las pruebas lo llaman directamente con el reloj inyectado.
6. **Cola acotada** (#22): como mucho `queue_max` = 32 órdenes vivas (`pendiente` o `ejecutando`). Con la cola llena, `POST /api/apply` → 409 `queue_full` y no crea nada.

### 2.6 Constantes

`WIRE_CAP` 3500 · `lease_ms` 3000 · `hold_ms` 2000 · mantenimiento cada 500 ms · margen del plazo local 100 ms · retención extra de la caché 1 s · `retry_ms` 2000 · `ttl_ms` 10000 · `queue_max` 32 · caché 1024 · barrido cada 250 ms · reintento de la lectura del mundo 1, 2, 4 y 8 s (y después cada 8 s). Todas, salvo `WIRE_CAP`, son parámetros de `Bridge(...)` y del mod falso, para que las pruebas las acorten.

### 2.7 Validez de un resultado

Un resultado vale solo si:
- su `session` es la actual;
- su `epoch` es el de la `conn` de la orden;
- su `status` es uno de los tres;
- con `status` `done`, su `read` tiene la forma de §4 cuando el verbo lo pide.

Un `rejected` o un `error` pueden llevar el `read` vacío (`{}`), como el sustituto `error/result_too_large` (§2.4.7, corrige B2-04). Si no vale → 400 `bad_request`, y la orden no cambia.

### 2.8 Qué corrige respecto al bridge QA

La revisión de Sol sobre #6 (`C:\tmp\dsbx-f02\sol\LAST_v1.md`) encontró defectos de diseño que `dsbx1` no repite:
- **H1** (`LAST_v1.md:9-14`): el bridge QA vuelve a contar desde `op-1` y una corrida nueva recibe resultados viejos como `dup` → aquí la identidad es `(session, op_id)` (§2.2) y la caché se indexa por el par.
- **H2** (`:16-21`): en Enforce, `Remove(0)` no conserva el orden y la caché expulsa lo reciente → aquí la expulsión es FIFO y solo de entradas caducadas (§2.4.4).
- **H3** (`:23-28`): el hombre muerto solo existía en el cliente y no había polls durante los trabajos largos → aquí va en los dos peers, con polls de mantenimiento (§2.4.2 y §2.4.6).
- **H5** (`:36-40`): la sonda aceptaba un hello con `ok: false` y no comprobaba el acuse → aquí se valida todo 200 (§2.4.1).

H4 y H6 son de la implementación QA (presupuesto de callbacks y regla estática de la clave) y los hereda F1b-peers (§11).

## 3. Estados y transiciones (#23, D2)

### 3.1 La orden de la API

`POST /api/apply` sigue creando la orden `pendiente` con origen `backend` (F1a; F1b-web §4). Ahora además la mete en la cola del bridge como `scene.apply` para el papel `server`, con `args` `{doc_id, rev, hash}` y atada a la `conn` vigente. Si la cola está llena, 409 `queue_full` antes de crearla.

Cada transición pasa por un único método nuevo del `Backend`, `set_op_state(op_id, state, origin, reason=None)`. Dentro de `store.lock`, ese método:
- actualiza `state`, `origin`, `reason` y `at_ms` de `backend.ops[op_id]`;
- actualiza `op_mono[op_id]` (F1b-web §4);
- emite `op.state`, que sigue sin `age_ms` y gana el campo `reason`.

| De | A | Cuándo | `origin` | `reason` |
|---|---|---|---|---|
| — | `pendiente` | al crearla (como hoy) | `backend` | — |
| `pendiente` | `ejecutando` | se entrega en un `/poll` | `backend` | `entregada` |
| `pendiente` | `fallido` | vence su TTL sin entregarse | `backend` | `no_entregada` |
| `pendiente` | `fallido` | cambia la `conn` (§2.5.3) | `backend` | `conexion_perdida` o `mundo_reiniciado` |
| `ejecutando` o `parcial` | `aplicado` | **primer** resultado `done` | `servidor` | — |
| `aplicado` | `observado` | en el mismo resultado, si el predicado de su verbo (§3.2) se cumple sobre `read` | `servidor` | — |
| `aplicado` | `fallido` | el predicado no se cumple | `servidor` | `lectura_no_cumple` |
| `ejecutando` o `parcial` | `fallido` | **primer** resultado `rejected` (el peer no tocó nada) | `servidor` | el motivo del peer |
| `ejecutando` | `parcial` | primer resultado `error` (hubo algún efecto) | `servidor` | el motivo del peer |
| `parcial` | `parcial` | primer resultado `error`, tardío: se registra, consume el primer resultado y se emite `op.state` con el motivo nuevo (corrige B2-03) | `servidor` | el motivo del peer |
| `ejecutando` | `parcial` | vence su TTL sin resultado | `backend` | `sin_resultado` |
| `ejecutando` | `parcial` | cambia la `conn` (§2.5.3) | `backend` | `conexion_perdida` o `mundo_reiniciado` |
| `parcial` | `observado` | una lectura válida del mundo (§4) muestra su generación y cumple el predicado completo de su verbo | `servidor` | `reconciliada` |
| `parcial` | `fallido` | una lectura válida muestra su `(session, op_id)` pero no cumple el predicado (otra `rev` u otro `hash`) | `servidor` | `lectura_no_cumple` |

- **Nunca hacia atrás**: ninguna orden vuelve a `pendiente`, y una orden entregada nunca pasa a «no ocurrió» por un plazo (#23). Desde `ejecutando`, sin respuesta del peer, solo cabe `parcial`.
- **Solo el peer, con su resultado o con una lectura del mundo, puede llevar una `parcial` a `fallido`**, nunca un plazo, y solo de tres maneras (corrige B2-05):
  - un primer resultado `rejected`, que por contrato significa que no hubo efecto (§2.4.6);
  - un primer resultado `done` cuyo `read` no cumple el predicado;
  - una lectura válida que muestra la orden con otra `rev` u otro `hash`.

  Las tres son la misma regla, «la lectura no cumple», por dos vías.
- `observado` y `fallido` son terminales. `parcial` solo sale por un primer resultado tardío o por reconciliación.
- `aplicado` y `observado` llegan en el mismo resultado, como dos eventos `op.state` en ese orden.

### 3.2 Verbos

- **`scene.apply`** (servidor), con `args` `{doc_id, rev, hash}`. El mod falso lo hace en dos pasos con efecto, «retirar la generación anterior» y «anotar la nueva `{session, op_id, rev, hash}»`, con un trabajo configurable entre ellos. El mod real aplicará la escena en F2 (#9). `read` es el estado del mundo de §4. **Predicado**: `read.epoch` es el `epoch` de su `conn` y `read.generation` es `{session, op_id, rev, hash}` de esta orden.
- **`state.read`** (servidor, interna): `args` `{}`, sin efectos; `read` = el estado del mundo de §4. No crea fila en la cola de la API ni eventos `op.state`.

## 4. Reconciliación del mundo (#10, CX-07)

- **Estado del mundo** (el `read` de los dos verbos): `{epoch, generation: {session, op_id, rev, hash} | null, registry_n, registry_sha256}`. Sus tipos: 32 hex; objeto o `null`; entero ≥ 0; 64 hex. El registro de entidades es de F2; aquí el mod falso da `registry_n` y `registry_sha256` de un registro vacío.
- **Al presentarse el peer servidor** (§2.5.3, `conn` nueva):
  - el backend lo marca **sin reconciliar** y encola un `state.read` con prioridad;
  - **no entrega ningún `scene.apply` hasta que esté reconciliado**.
- **Una lectura reconcilia solo si** (corrige B-07):
  - es el resultado de un `state.read` de la `conn` vigente, entregado a la `inst` vigente;
  - es válido (§2.7) y tiene `status` `done`;
  - su `read` está completo, con la forma de arriba;
  - `read.epoch` es el `epoch` con el que se presentó el servidor.

  Cualquier otra cosa deja al servidor sin reconciliar: un `error`, un `rejected`, un TTL vencido, una lectura incompleta o de otro `epoch`. Mientras tanto, el `state.read` se repite a los 1, 2, 4 y 8 s, y después cada 8 s.
- **Con una lectura válida**, el backend guarda el estado del mundo y queda reconciliado. Además, para toda orden `parcial` de esta sesión cuya `(session, op_id)` aparezca en `read.generation`, aplica **el mismo predicado completo que la vía directa** (§3.2: `epoch` de su `conn`, y `session`, `op_id`, `rev` y `hash` de la orden; corrige B2-02):
  - si se cumple, pasa a `observado/reconciliada`;
  - si no, a `fallido/lectura_no_cumple`.

  Una misma lectura nunca da `observado` por una vía y `fallido` por la otra.
- **Recuperación de lo `parcial`** (corrige B-08): cada vez que una orden pasa a `parcial`, y mientras quede alguna `parcial` con la `conn` viva, se encola un `state.read`, como mucho uno pendiente a la vez, con el mismo calendario de reintentos. Es el «parcial hasta reconciliar» de D2 (plan línea 170). Una orden `parcial` de un mundo anterior (`epoch` distinto) no se recupera con el mundo nuevo: #10 invalida sus referencias (plan línea 32) y se queda `parcial/mundo_reiniciado`.
- **Peer cliente**: está «en el mundo» solo si su `epoch` es el del servidor reconciliado. En F1b-bridge no recibe órdenes.
- **Tras reiniciar el backend**, la cola de la API se pierde, como en F1a: la primera lectura válida fija la base de la sesión nueva.

## 5. Catálogo (#8)

- **Página**: `{catalog_id: 16 hex, page, pages, build, modset_hash: 64 hex, classes: [[clase, base], ...]}`, cada una ≤ `WIRE_CAP`. Las páginas pueden llegar en cualquier orden; una repetida idéntica es idempotente.
- **Al completarse**: el backend comprueba que no hay clases repetidas y que todas las páginas declaran el mismo `catalog_id`, `pages`, `build` y `modset_hash`. Si cuadra, guarda en memoria `Bridge.catalog = {catalog_id, build, modset_hash, n_classes, sha256, classes}`, con `sha256` sobre el JSON canónico de la lista ordenada.
- **Si algo no cuadra** → 409 `bad_catalog` y se descarta ese `catalog_id`.
- **Fuera de alcance**: guardarlo en disco y usarlo para validar (F2).

## 6. El mod falso (`app/tests/fake_mod.py`)

- **Estructura**: `FakeMod(bridge_url, peer_key, ...)` arranca los dos peers en hilos, cada uno con su `inst`, y el servidor genera el `epoch`. Cumple §2.4 entero.
- **Lado servidor**:
  - responde `state.read` y `scene.apply` (dos pasos con efecto, §3.2);
  - sube un catálogo de prueba en páginas al presentarse;
  - lleva un **contador de efectos** por `(session, op_id)` y paso, para que las pruebas cuenten ejecuciones reales.
- **Inyección de fallos**: atributos y métodos solo para pruebas, sin rutas de depuración en el backend.
  - perder el próximo resultado o el próximo acuse;
  - cortar los polls de un peer durante N ms;
  - un trabajo lento de N ms antes o después del primer paso, con o sin polls de mantenimiento;
  - retrasar N ms el procesado de la respuesta de un poll, para simular tránsito (B-01);
  - `restart_peer(rol)`: `inst` y caché nuevas, **mismo `epoch` y misma generación** (el peer se recrea y el mundo sigue);
  - `restart_mission()`: `epoch`, `inst` y caché nuevos, y un mundo vacío (generación `null`);
  - responder a `state.read` con `error`, con un `epoch` viejo o con un `read` incompleto;
  - forzar dos entregas de la misma orden antes de que termine la primera (llamando dos veces a su manejador);
  - presentarse con un 200 inválido simulado (para H5, sobre su función de validación).
- **CLI**: `python app/tests/fake_mod.py --config backend.json` lo conecta al backend local, para ver transiciones reales en la web sin DayZ.

## 7. Aceptación (R26)

Gate: el de F1b-web §7, con las pruebas nuevas dentro de la suite y el arnés E2E con dos pasos más. Las pruebas usan el `Bridge` real en un hilo con puerto 0, constantes acortadas y el reloj inyectado donde haga falta.

| # | Positivo | Negativo (el defecto que detecta) |
|---|---|---|
| BR1 hello | Hello válido de los dos peers → `ok`, `session` de 16 hex, `lease_ms` y `hold_ms` | Clave mala o ausente → 401 y nada registrado; `proto` distinto → 409; cuerpo mal formado → 400; la línea de log lleva `key=***` |
| BR2 poll | Una orden por poll como mucho; sin órdenes, vuelve con `ops: []` en `hold_ms` ± 0,5 s; `deliver=0` responde enseguida y no entrega aunque haya orden | `session` o `inst` viejas → 409 `hello_required`, sin entrega |
| BR3 D2 de punta a punta | Con el mod falso: `apply` → `pendiente` → `ejecutando` → `aplicado` → `observado`, con orígenes y motivos de §3.1, `op_mono` actualizado y los `op.state` en ese orden por el SSE | Predicado que no se cumple (el mod falso anota otra `rev`) → `fallido/lectura_no_cumple`, nunca `observado` |
| BR4 sin peer | Sin mod falso, la orden sigue `pendiente` hasta su TTL y pasa a `fallido/no_entregada` | Nunca `aplicado` ni `observado` (el negativo de D2) |
| BR5 resultado perdido | El mod ejecuta y pierde todos los envíos del resultado → reentrega a la misma `inst` → `dup: true` → `observado`, con efectos = 1; también si la reentrega llega con el plazo ya vencido en el peer | Acuse perdido → el resultado repetido no crea un segundo evento |
| BR6 peer recreado, mundo conservado | Con los dos pasos ya hechos y antes de mandar el resultado, `restart_peer("server")` → `conn` sube → `parcial/conexion_perdida` enseguida, sin esperar al TTL; la lectura válida muestra la generación → `observado/reconciliada`; efectos = 1 | Sin reentrega a la `inst` nueva: con ella habría 2 efectos (X3 e). Recreado **entre** los dos pasos, la generación no es la suya y se queda `parcial` |
| BR7 H1 | Backend reiniciado con el mod falso vivo: la orden `(S2, op-1)` se ejecuta, `dup: false`, y los efectos de `op-1` suben aunque la caché tenga `(S1, op-1)` | Con la caché indexada por `op_id` solo, devuelve el resultado viejo (X3 a) |
| BR8 caché | Tras 1025 órdenes con el plazo vencido, la caché tiene exactamente las últimas 1024 en orden | Con el reloj controlado, una caché llena de entradas vivas no pide órdenes (solo `deliver=0`), y la reentrega de la más vieja sigue siendo `dup` y no repite el efecto (X3 b y p) |
| BR9 H3 | Un trabajo de 5 s con polls de mantenimiento termina `done`; los dos peers renuevan el lease con `deliver=0` | Polls cortados más de `lease_ms` **antes** del primer paso → `rejected/lease_expired`, efectos = 0 y `fallido`; el peer cliente también deja de dar su lease por bueno |
| BR10 H5 | — | El mod falso no da por buenos un hello con `ok` ausente o `false`, con `lease_ms` 0 o con `session` mal formada, ni un poll sin `now_ms`, ni un acuse sin `ok`: no renueva el lease y reintenta |
| BR11 plazo al llegar | — | Orden con el plazo ya vencido al llegar → `rejected/expired`, efectos = 0 y `fallido` |
| BR12 misión reiniciada | `restart_mission()` con una orden `ejecutando` y otra `pendiente`: la primera → `parcial/mundo_reiniciado` y la segunda → `fallido/mundo_reiniciado`; ninguna se ejecuta en el mundo nuevo (efectos en el mundo nuevo = 0) y una orden creada tras reconciliar sí se ejecuta | Cliente con otro `epoch` → fuera del mundo; orden con `epoch` viejo → `rejected/stale_epoch`; la `parcial` del mundo viejo no pasa a `observado` con la lectura del nuevo |
| BR13 reconciliar antes de autorizar | Tras el hello del servidor, el primer `scene.apply` se entrega solo después de una lectura válida | `state.read` con `error`, con un `epoch` viejo, con un `read` incompleto o de una `inst` anterior → no se entrega ningún `scene.apply` y la lectura se repite (X3 r) |
| BR14 cola acotada | 32 órdenes vivas → la 33.ª `apply` → 409 `queue_full`, sin orden ni evento | — |
| BR15 `WIRE_CAP` | Una página de catálogo de 3500 B entra | Una petición de 3501 B → 413 sin leer el cuerpo; un resultado que pasaría del tope → `error/result_too_large` con `read` vacío, acusado con 200 al momento, y la orden pasa a `parcial` enseguida, sin esperar al TTL; una orden que no cabría → rechazada al encolar |
| BR16 catálogo | Páginas desordenadas y una repetida → `complete` con el `sha256` esperado | Clase repetida o `pages` incoherente → 409 `bad_catalog` |
| BR17 secretos | — | `peer_key` igual a otra clave → el `Backend` no arranca; `peer_key` no aparece en ninguna respuesta de la API ni del bridge, ni en logs ni en la salida de las pruebas |
| BR18 plazo durante el trabajo (B-01) | — | Un trabajo de más de un TTL con el lease sano: si el plazo vence **antes** del primer paso → `rejected/expired` y efectos = 0; si vence **entre** los dos pasos → `error/expired`, solo el primer paso hecho y `parcial`; nunca un efecto después de `plazo_local` (X3 n). Con la respuesta del poll retrasada 1,5 s (TTL de 2 s y trabajo de 0,6 s), ningún efecto ocurre después del TTL del backend: el plazo se ancla al envío del poll, no a la recepción (X3 u) |
| BR19 una en curso (B-03) | — | Dos entregas de la misma orden antes de que termine la primera → cada paso se hace una vez (retirar = 1, anotar = 1; corrige B2-06); el peer no manda ningún poll entregador mientras ejecuta (X3 o) |
| BR20 lease perdido tras un efecto (B-05) | — | Polls cortados después del primer paso → `error/lease_expired` → `parcial`, nunca `fallido` (X3 q) |
| BR21 reconectar no ejecuta la cola vieja (E1, B-02) | Una orden creada tras reconectar y reconciliar se ejecuta | Servidor sin polls más de `lease_ms` con una orden `pendiente` → `fallido/conexion_perdida`; al volver, esa orden no se ejecuta (efectos = 0). Un poll con la **misma `session` y la misma `inst`** pero la `conn` anterior, mandado después del nuevo hello, recibe 409 y no entrega nada (X3 s y w; corrige B2-01) |
| BR22 confirmación tardía (B-08) | Una orden `parcial/sin_resultado` cuyo primer resultado `done` llega después → `aplicado` → `observado` | Primer resultado tardío `rejected` → `fallido`; primer resultado tardío `error` → sigue `parcial`, con un `op.state` que lleva el motivo nuevo (B2-03); uno repetido → nada; una lectura que falla se repite hasta reconciliar (X3 t) |
| BR23 reconciliar con el predicado completo (B2-02) | — | Orden con `rev` 7 cuyos resultados se pierden y cuya generación queda con `rev` 8: la lectura del mundo la pasa a `fallido/lectura_no_cumple`, nunca a `observado` (X3 v) |
| P10 web con mod falso | En el E2E: con el mod falso conectado, «Aplicar» lleva la fila a Observado con origen `servidor` | — |
| P11 web sin mod | — | Con el mod parado, la fila pasa de Pendiente a Fallido (TTL acortado en el arnés), nunca a Aplicado |
| X3 antitautología | — | El orquestador corre las pruebas contra el código mutado y cada mutación tiene que hacer fallar al menos una prueba. La lista, abajo |

Las mutaciones de X3:
- (a) la caché indexada por `op_id` solo;
- (b) una expulsión que no conserva el orden;
- (c) sin comprobar el lease antes del efecto;
- (d) aceptar `ok` ausente o `false`;
- (e) reentregar a otra `inst`;
- (f) el TTL de una orden entregada lleva a `fallido` en vez de a `parcial`;
- (g) `scene.apply` antes de `state.read`;
- (h) la cola sin tope;
- (i) un resultado repetido que vuelve a transicionar;
- (j) el peer sin comprobar `epoch`;
- (k) `observado` sin predicado;
- (l) `key` sin redactar en el log;
- (m) la deduplicación después del plazo;
- (n) el plazo solo al recibir y no antes de cada efecto;
- (o) un poll entregador mientras ejecuta, sin deduplicar lo que está en curso;
- (p) expulsar entradas vivas de la caché;
- (q) `rejected` después de un efecto;
- (r) aceptar como reconciliación una lectura que falla o es de otro `epoch`;
- (s) entregar órdenes de una `conn` anterior;
- (t) ignorar el primer resultado tardío de una `parcial`;
- (u) anclar el plazo local a la recepción de la respuesta en vez de al envío del poll;
- (v) reconciliar comparando solo `(session, op_id)` y `epoch`, sin `rev` ni `hash`;
- (w) aceptar un poll con una `conn` anterior.

P1-P9b y las 114 pruebas actuales tienen que seguir pasando sin cambios. El arnés arranca el bridge en todas las corridas, pero con un TTL largo hasta P9b, para que ninguna orden de esos pasos caduque, y solo arranca el mod falso en P10.

## 8. Ficheros

```
DayZSandbox_dev/
  plans/2026-11-14-m1-f1b-bridge-brief.md   este brief                         [orquestador]
  app/backend/bridge.py                     §2, §3, §4 y §5 (lado backend)     [F1bb-1]
  app/backend/server.py                     cableado: Bridge, set_op_state, cola en apply,
                                            peer_key y bridge_port en load_config y main   [F1bb-1]
  app/tests/test_bridge.py                  BR1, BR2, BR4, BR13-BR17 y BR21, con un peer de prueba
                                            mínimo por HTTP                    [F1bb-1]
  app/tests/fake_mod.py                     §6                                  [F1bb-2]
  app/tests/test_fake_mod.py                BR3, BR5-BR12, BR18-BR20, BR22 y BR23 contra el Bridge real   [F1bb-2]
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

- **Esta subfase acredita el contrato y el lado del backend, no el bridge de producción.** El mod falso comprueba el intercambio y las transiciones, pero no aplica ni observa un mundo de verdad. Eso lo acredita F1b-peers en partida (§11), con E1 en retail (nota de Sol sobre la premisa, ronda 1).
- **El `RestContext` real** solo está medido con la clave en la consulta, 3728 B por POST y órdenes de hasta 271 B. Un `/poll` cerca de `WIRE_CAP`, las cabeceras que manda y sus reintentos propios se miden con el mod real (F0.3-0 v4.5 lo mide en su base en partida, líneas 66-68).
- **La ventana del hombre muerto** medida en retail (acepta ≤ 2756 ms y rechaza ≥ 3037 ms) es la del cliente QA. La de cada peer de `dsbx1` se mide en F1b-peers (H3).
- **`max_ms` de 8679 en S-puente**: una orden suelta puede tardar 8,7 s. Por eso el TTL es de 10 s, y una orden entregada sin resultado pasa a `parcial`, nunca a «no ocurrió».
- **Perder la conexión falla las órdenes que esperan**: el usuario las vuelve a pedir. Es lo seguro, porque reconectar nunca ejecuta la cola vieja (E1).
- **La cola sigue en memoria** (F1a): reiniciar el backend la pierde, y la reconciliación (§4) solo recupera lo que el mundo diga.
- **Un solo proceso** sirve la API y el bridge; un long-poll ocupa un hilo por peer (2 en total).

## 11. Continuación: F1b-peers (los peers reales)

La parte de F1b que esta subfase no cierra (corrige B-09). La asigna la sesión principal.

- **Qué**: los dos peers de `dsbx1` en Enforce, dentro del mod núcleo `DayZSandbox/` (#32), con todo §2.4. Incluyen hello, poll y resultados, deduplicación y retención, plazo local, lease con mantenimiento, `state.read` y `scene.apply` mínimos (la generación, sin escena hasta F2) y el catálogo de `CfgVehicles` en páginas (#8). Respetan las lecciones de F0.2 y F0.3-0 v4.5: `WIRE_CAP` como constante, `RemoveOrdered`, nada de `.Replace(`, validación de `ok`, presupuesto de callbacks (H4) y la clave sin alias (H6).
- **Prerrequisitos**:
  - el esqueleto del mod núcleo (`config.cpp`, PBO y carga en servidor y cliente);
  - este brief congelado y su código en verde;
  - las cifras de F0.3-0 en partida para `WIRE_CAP` (su gate de base, línea 115 de su brief).
- **Gate**:
  - el linter offline de Enforce (`dayz-script-validator`) antes de declarar nada;
  - después, en partida y con el visto bueno de Guillermo para lanzar DayZ, E1 en retail (plan §4, línea 174) y la viabilidad del transporte de E2 con la mezcla de la sonda (plan F1, línea 93), con el bridge de esta subfase y el mismo contrato;
  - la ventana del hombre muerto medida en cada peer (H3).
- **Cierre de F1**: F1 se cierra con los entregables del plan (líneas 86-91) y su gate (línea 80), no con esta subfase sola.

## 12. Cambios por la revisión

**Ronda 1 de Sol** (`gpt-6.1-sol`, esfuerzo máximo, solo lectura, sobre `86736e2`; veredicto UNSOUND con 7 bloqueantes y 2 importantes). El orquestador comprobó cada hallazgo contra el texto y los aplica todos:

| Hallazgo | Qué cambia |
|---|---|
| B-01 · bloqueante · el TTL solo se miraba al recibir: un trabajo largo podía hacer efectos fuera de plazo | `plazo_local` comprobado antes de cada efecto (§2.4.3 y §2.4.6); BR18 y X3 (n) |
| B-02 · bloqueante · reconectar o un mundo nuevo ejecutaban la cola vieja (E1, plan línea 174) | Generación de conexión `conn`: las órdenes solo se entregan dentro de la suya, y la pérdida o la nueva presentación falla las que esperan (§2.2 y §2.5.3); BR12 cambia de signo; BR21 y X3 (s) |
| B-03 · bloqueante · una reentrega durante la ejecución podía ejecutar dos veces | Una orden en curso por peer, solo `deliver=0` mientras ejecuta, y deduplicación de lo que está en curso (§2.4.2 y §2.4.4); BR19 y X3 (o) |
| B-04 · bloqueante · la FIFO de 1024 podía expulsar una entrada aún reentregable | Retención hasta `plazo_local` + 1 s y contrapresión con la caché llena de entradas vivas (§2.4.4); BR8 y X3 (p) |
| B-05 · bloqueante · perder el lease después de un efecto se comunicaba como «no hizo nada» | `rejected` solo sin ningún efecto; tras un efecto, `error` y `parcial` (§2.4.6 y §3.1); BR20 y X3 (q) |
| B-06 · bloqueante · BR6 y BR12 pedían resultados incompatibles del mismo reinicio | Dos fallos distintos, `restart_peer` (mundo conservado) y `restart_mission` (`epoch` nuevo), cada uno con su expectativa (§6; BR6 y BR12) |
| B-07 · bloqueante · BR13 probaba el orden temporal, no la validez de la reconciliación | Condición normativa de lectura válida y reintentos (§4); negativas en BR13 y X3 (r) |
| B-08 · importante · una `parcial` descartaba confirmaciones tardías y no tenía vía de recuperación | Se aplica el primer resultado aunque llegue tarde, y se repiten las lecturas mientras quede algo `parcial` (§2.5.4, §3.1 y §4); BR22 y X3 (t) |
| B-09 · importante · aplazar los peers en Enforce dejaba sin dueño parte de F1b | Subfase offline declarada (§0) y continuación F1b-peers con dueño por asignar, prerrequisitos y gate (§11) |

**Ronda 2 de Sol** (misma sesión, sobre `95bec2c`; veredicto UNSOUND). Sol da por cerrados B-02 a B-09, deja abierto B-01 y añade dos bloqueantes, dos importantes y dos menores. Se aplican todos:

| Hallazgo | Qué cambia |
|---|---|
| B-01 · bloqueante (sigue) · anclar el plazo local a la recepción con un margen fijo no es conservador: con 1 s de tránsito, el efecto puede caer después del TTL del backend | El plazo se ancla al envío del poll, `t_envío`: por causalidad, `t_envío` + lo que queda es ≤ el plazo real, haya el tránsito que haya (§2.4.3). BR18 con la respuesta retrasada 1,5 s y X3 (u) |
| B2-01 · bloqueante · `conn` no viajaba en el protocolo, así que un poll viejo retenido era indistinguible de uno nuevo con la misma `session` e `inst` | `conn` en la respuesta del hello, en cada poll y en cada orden, comprobada en los dos extremos (§2.2, §2.3 y §2.4.5). BR21 con la misma `session` e `inst` y X3 (w) |
| B2-02 · bloqueante · la reconciliación comparaba solo la identidad y daba `observado` a una generación con otra `rev` | Mismo predicado completo en las dos vías; si no se cumple, `fallido/lectura_no_cumple` (§3.1 y §4). BR23 y X3 (v) |
| B2-03 · importante · faltaba la fila de un primer `error` tardío sobre una `parcial` | Fila `parcial` → `parcial` con motivo y `op.state` (§3.1); BR22 |
| B2-04 · importante · el sustituto `error/result_too_large`, con `read` vacío, chocaba con §2.7 | `rejected` y `error` pueden llevar `read` vacío (§2.7); BR15 exige acuse inmediato y `parcial` enseguida |
| B2-05 · menor · la regla «`parcial` → `fallido` solo por `rejected`» no casaba con la tabla | Regla reescrita: solo el resultado del peer o una lectura llevan una `parcial` a `fallido`, nunca un plazo (§3.1) |
| B2-06 · menor · BR19 decía «un solo efecto» con dos pasos por ejecución | Contadores por paso: retirar = 1, anotar = 1 |
