# Contrato de evidencia de F2P (T2 → T4)

Oráculo: `qa/f2p_eval.py` y `qa/f2p_mutants.py`, congelados por Sol. El runner de T4 produce exactamente
esto. El evaluador lee **solo** lo que este documento permite; lo demás se ignora.

## 0. Disposición

Una partida = **una campaña por build** (diag y retail), cada una con **una sola parte `run`** en su
propia `BASE`. No hay parte `run-retail`: el build retail se entrega en su propio `BASE/run/`.

```
run/
  manifest.json                 # §1
  part.json                     # §8 (arnés: `op_nonce` de 16 hex)
  samples/bridge.jsonl          # §2 (sonda, tal cual la escribe f03_common.PartContext.open)
  samples/bridge_tap.jsonl      # §3 (proxy del producto)
  samples/backend.jsonl         # §4 (backend y API)
  samples/scene_del.jsonl       # §5 (líneas DSBX_SCENE_DEL del log de script del mod)
```

Las fixtures normativas de las escenas son `fixtures/escena-sin-actores.json` (escena 1) y
`qa/fixtures/f2p_scene2.json` (escena 2). El evaluador las lee del repo; no son lecturas del mod.

Códigos de salida: 0 PASA, 1 FALLA, 2 INCONCLUSO (`qa/gate_core.py:73-82`). Un fichero de `samples/`
que falte, esté vacío o no sea JSONL de objetos → INCONCLUSO `missing_evidence_files` /
`empty_or_corrupt_samples`.

## 1. `manifest.json`

Se leen **solo** estas claves: `schema`, `id` (=`"F2P"`), `kind` (=`"spike"`), `build`, `both`,
`params`, `identity` y `f2p`. El resto (argv, faults, harness, execution_identity) se ignora.

- `identity` (identidad de F0.3, `plans/2026-11-14-m1-f0.3-0-brief.md` §5.2):
  - `git_head` (40 hex), `git_dirty` (bool; en diag/retail tiene que ser `false`), `build`
    (`diag`|`retail`|`offline`), `params` (`hold_ms`, `lease_ms`, `ttl_ms`, `retry_ms`, `seed`),
    `probe_stamp` (16 hex), `peer_builds` (`{"server":...,"client":...}`), `pbo_sha256` (64 hex, sonda);
  - `product_pbo_sha256` (64 hex, **PBO del producto**, P-11);
  - **`oracle_commit` (40 hex):** el commit congelado que el gate verificó, ya resuelto. Es **el mismo
    id** que `f2p.oracle_commit` y que el `commit` del evento `oracle.frozen` (H-7, §6.1). Si los tres
    no coinciden → INCONCLUSO `oracle_modified`.
- `f2p`:
  - `oracle_commit` (40 hex): el commit congelado del oráculo (igual que `identity.oracle_commit`);
  - `oracle_files`: `{"f2p_eval.py":"<64 hex>","f2p_mutants.py":"<64 hex>"}` — SHA-256 de los bytes
    de cada fichero del oráculo en ese commit (DP-13). Si el gate congela también `f2p_run.py` (T4),
    añade su SHA-256; el oráculo de T2 solo exige las dos entradas de eval/mutants, pero el gate compara
    los tres ficheros y da INCONCLUSO `oracle_modified` si alguno no coincide o ya está en `sys.modules`;
  - `storage`: `{"path":"<ruta>","id":"<id>"}` — ruta e identificador del storage del servidor (P-06);
  - `witness_follow_ticks`: entero en [1,5] (Q-01; 3 por defecto);
  - `p2n_variant`: `"create_failed_first"` | `"create_failed_after"` | `"displaced"` (§5.5);
   - `parts`: lista **en el orden normativo** de las partes de la partida (§5.2 del brief), cada una
     `{"name":"P1"|"P2"|"P2n"|"P3"|"P3c"|"P4a"|"P4b"|"P4c"|"P5","start_t_ms":<float>,
     "end_t_ms":<float>,"storage_id":"<id>"}`. Ventanas crecientes y sin solape; las nueve, una vez
     cada una. Todo evento de `samples/` usado por el evaluador tiene que caer dentro de la ventana de
     su parte.
     **v1.3.11 (F-15):** el epoch **no** es de la parte. Cada evento se juzga con el epoch de su
     instancia (`/hello`) y de su tramo de backend; una parte puede abarcar dos. El `server_epoch` de
     la parte, si está, solo sirve para acreditar el reinicio del servidor (§6.1 punto 8), nunca para
     juzgar los eventos de la sonda ni del `tap`. **Enmienda de identidad (2026-11-23,
     brief:1296-1313):** el epoch con que se juzga un trabajo de la sonda es el del producto en la
     vida del servidor en que se entregó (§2, «Casado por la vida del servidor»).
     **v1.3.12 (Sol r4c, W-01):** el `server_epoch` de la parte **no es obligatorio**. Los manifests
     reales del arnés de F0.3 no lo llevan. Si está, son 32 hex; si no está, no falta nada y el
     reinicio del servidor se acredita por el epoch del `/hello` nuevo y el `restart` (§6.1 punto 8).
     El evaluador y este contrato dicen lo mismo.

Si falta una clave, un valor tiene forma inválida, o `oracle_files`/`oracle_commit`/sellos PBO no
coinciden con lo observado en `backend.jsonl` → INCONCLUSO (`manifest_incomplete`,
`oracle_modified`, `pbo_mismatch`), nunca PASA.

## 2. `samples/bridge.jsonl` (sonda)

Eventos del `QABridge` de F0.3 tal cual (`qa/bridge_qa.py:475-489`, `qa/f03_common.py:504-549`):

- `{"t_ms","ev":"hello","peer":"server"|"client","inst","http":200,"ok":true,"args":{"proto":"qa0","build","probe_ver","inst","peer"}}`
- `{"t_ms","ev":"enq","peer","op_id","verb","args","inst"}`
- `{"t_ms","ev":"deliver","peer","op_id","verb","args","inst"}`
- `{"t_ms","ev":"poll","peer","inst","http":200,"now_ms","op_ids":[...],"n_ops"}`
- `{"t_ms","ev":"result","peer","http":200,"op_id","result":{"op_id","status","reason","read"}}`
  con `read` empaquetado (`sk/sv/nk/nv/ncol/ncell/scol/scell/rows`, `qa/wire.py:212`).
  **v1.3.11 (A-01):** el evento `result` del bridge **no lleva `inst`**. La instancia de una respuesta
  es la que el bridge tenía aceptada para ese peer al recibirla: la del último `/hello` aceptado de
  ese peer antes del `result` en el reloj común. El bridge rechaza con `409 hello_required` cualquier
  `/result` de otra instancia (`qa/bridge_qa.py:833-836`), y ese rechazo queda como `inst_reject`.
  La conformidad se prueba con las líneas reales de las diags (`qa/fixtures/f2p_native_probe.json`).
  **v1.3.11 (F-03):** el `poll` de la sonda lleva `tick_s` (`GetTickTime()`, `DSBX_QA_Probe.c:872`,
  el mismo reloj que `NowMs()`, `:358`). En P5, un nacimiento de la generación cortada cuenta como
  anterior al corte solo si hay un `poll` de la sonda de la misma instancia con `t_ms` anterior al del
  `cut` y `1000 · tick_s >= tick_ms` del nacimiento. Ticks con ticks y `t_ms` con `t_ms` (R-03). Si
  K = 0, INCONCLUSO `p5_sin_efecto`: el estímulo no ocurrió antes del corte.

Verbos y lecturas usados (interfaz de F0.3, `_ref/censo-interfaz-f03.md`):

- `per_census_start`: read `str`: `job`,`state`,`area_tag`,`server_epoch`,`director_uid`; `num`:
  `snap_tick_ms`,`snap_frame`,`rows_captured_n`,`center_x_m`,`center_z_m`,`radius_m`,
  `director_present_b`,`director_alive_b`,`director_inv_readable_b`,`director_inv_count_n`.
  Filas de `job_read`: `scol=["class_name","loc_kind","parent_class","parent_net_id","slot_name","owner_uid","own_logical_id","net_id","pers_id"]`,
  `ncol=["own_b","in_radius_b","alive_b","ai_agent_b","pos_x_m","pos_y_m","pos_z_m","yaw_deg","pitch_deg","roll_deg","max_hp","health_hp","inv_children_n","spawn_tick_ms","surface_y_m"]`.
  - **`surface_y_m` solo sale con `select_all_entityai_b = 1`** (última columna). F2 usa `select_all_entityai_b = 1`;
    sin esa marca las filas no lo llevan y F2P-11 no puede pasar.
  - **El director queda fuera de las raíces del modo 1 del censo.** `include_director_b = 1` sirve para los
    inventarios de jugador, pero el director no es una fila raíz; el oráculo no lo usa.
  - **Los edificios estáticos del mapa pueden salir con `net_id` `0:0`** (o vacío). Se identifican por
    **clase y pose** (y `surface_y_m`), nunca por `net_id`; `net_id` solo identifica lo creado en la sesión.
  - `own_b` y `own_logical_id` son del registro de la sonda de S-persist, no del marcador del producto:
    el oráculo de F2 **no los usa**.
  - **Salud (v1.3.10, §5.3).** `max_hp = health_hp = -1` significa «sin sistema de daño inicializado».
    Lo que crea el QA lleva salud real, `> 0`, con la marca puesta y comprobada al crear (o la op da
    error); `health_mark_pending` no existe. Los objetos del mundo se leen con la guarda: los `Land_*`
    del mapa dan `-1/-1` y el botín de la CE da salud real y gastada. Lo que crea el producto puede dar
    salud real o `-1/-1`; ninguna comprobación depende de esa salud. El testigo no lleva salud.
- `per_witness_start`: read `str`: `job`,`state`,`witness_tag`,`server_epoch`; `num`: `start_tick_ms`,
  `start_frame`,`center_x_m`,`center_z_m`,`radius_m`,`window_ms`. Filas (orden real de la sonda,
  `489f348`, #22): `scol=["class_name","net_id","parent_net_id"]`,
  `ncol=["sample_idx","pos_x_m","pos_y_m","pos_z_m","yaw_deg","tick_ms","frame","ai_agent_b","alive_b","surface_y_m"]`.
  El oráculo lee **siempre por nombre**; el orden de `ncol` no se usa para decidir.
  - **`surface_y_m` es la última columna** (brief v1.3.5 §5.3): `g_Game.SurfaceY` en la x y la z de cada
    muestra. En la muestra 0, en las de `EEInit`; en las de la 1 a la K, en su posición de ese tick; con
    `alive_b = 0`, en la última posición conocida. Es la altura **independiente** que usa F2P-02; la
    `pos_y_m` del testigo nunca hace de suelo. Si una fila no la trae → INCONCLUSO `surface_unbacked`.
  - **`witness_tag` es opcional.** Un testigo con el tag vacío no se rechaza: se identifica por su
    `start_t` dentro de la ventana de su parte y, si la parte tiene varias ventanas (P3), por el orden
    canónico de etapas (`apply1`, `apply2`).
  - **`alive_b` del testigo significa que la entidad existe en ese `EEInit`, no que `IsAlive()` sea
    cierto.** Q-05 («viva y con IA») se mira **solo en el censo** (`alive_b` y `ai_agent_b` de las filas
    de `per_census_start`). Ninguna comprobación usa el `alive_b` del testigo como «viva».
  - En las raíces, `parent_net_id == ""`.
- `job_read`: args `{"job","page_n"}`; read `str`: `job`,`state`,`reason`,`resource`; `num`:
  `page_n`,`pages_n`,`rows_total_n`,`start_tick_ms`,`end_tick_ms`,`onjobend_tick_ms`,
  `released_tick_ms`,`elapsed_dtsum_ms`; más las filas de la página.
- `job_free`: args/read con `job`.
- `per_spawn_raw`: `mode` `foreign_ground`|`foreign_in_container`|`persistent_control`, `tag`,
  `class_name`, `target_net_id`; read `str`: `spawn_status`,`tag`,`class_name`,`net_id`,`pers_id`,
  `obs_loc_kind`,`obs_parent_net_id`,`obs_slot_name`; `num`: `pos_x_m`,`pos_y_m`,`pos_z_m`,`yaw_deg`,
  `pitch_deg`,`roll_deg`,`max_hp`,`health_hp`,`child_count_n`,`tick_ms`,`frame`.
- `per_cleanup_qa`: `cleanup_tag` y tabla de discos; read `num.cleaned_raw_n`.

**Regla de independencia y procedencia (DP-12/P-10).** Cada fila del censo o del testigo que el
evaluador use tiene que estar dentro de la página de un `job_read` cuyo `job` coincida **en la petición
(`enq.args`) y en la respuesta (`result.read`)** con el que sale del `per_census_start`/`per_witness_start`
correspondiente; la `page_n` pedida y la devuelta tienen que coincidir; la instancia (`inst`) que encoló
la op, la que la entregó y la que respondió tienen que ser la misma; `resource` correcto,
`state=="done"`, y `probe_ver=="dsbx-qa1+"+identity.probe_stamp` en el `hello` de esa instancia.
**v1.3.11 (F-01):** las páginas de `job_read` **no llevan `server_epoch`** en su `sk`; en el cable real
solo traen `job`, `state`, `reason` y `resource` (`DSBX_QA_Probe.c:1570-1578`). El epoch del trabajo es
el `server_epoch` de su **lectura de arranque** (`per_census_start` o `per_witness_start`), que sí lo
trae y no puede estar vacío; las páginas se ligan a él por el `job` y por la instancia de su entrega,
que tiene que ser la del arranque. Si una fixture trae `server_epoch` en una página, se valida contra el
del arranque; ausente es lo normal y presente vacío es inválido.
La página 0 se exige **siempre**, también con `pages_n==0`: `read_job_pages` de la sonda lee la 0 y
después hasta `pages_n-1` (`qa/f03_common.py:1130-1149`), y `pages_n`/`rows_total_n` valen 0 cuando el
trabajo no tiene filas. Con `pages_n>0` se exigen las páginas 1..`pages_n-1`. El `t_ms` de la página
tiene que ser **posterior** al arranque del trabajo y al efecto que juzga (resultado del
apply/reset/reinicio). Si no hay página válida → INCONCLUSO (`unbacked_rows`); si la página es anterior
al efecto → INCONCLUSO (`unbacked_rows`), porque una medición no respaldada no es una FALLA (§6.1
punto 1 del brief v1.3.11).

**Casado por la vida del servidor (enmienda de identidad, 2026-11-23, brief:1296-1313).** La sonda y
el producto **no** comparten ids: en el juego son UUID independientes. La sonda da su `inst` como
`server_epoch` (`DSBX_QA_Probe.c:264-274`, #22); el producto genera su `inst` y su epoch por separado
(`DayZSandbox/scripts/3_Game/DSBX_Peer.c:199`, `DSBX_World.c:34`). Hasta `98c7a78` el oráculo exigía
la igualdad, y una partida honesta daba INCONCLUSO en todo. Ahora el evaluador no compara ids entre
los dos lados; los casa por la vida del servidor (`_server_lives`, `_job_life_problem`, `_job_epoch`):
- **Vida del servidor:** el tramo entre dos `restart` con `target: "server"` de `backend.jsonl`, y
  desde el principio hasta el primero y desde el último hasta el final: `[desde, hasta)` en el reloj
  común, como los tramos del backend.
- **Una identidad por lado y por vida:** el producto, una sola `(inst, epoch)` en sus `/hello` de
  servidor aceptados del `tap` (a la hora de su respuesta); la sonda, una sola `(inst,
  server_epoch)` en sus `hello` de servidor aceptados y en las lecturas de arranque de sus trabajos (a
  la hora de su entrega). Un `/hello` repetido con la misma identidad no cuenta como otro: el producto
  vuelve a saludar tras cada reinicio del backend (P3, P4a y P5).
  - Solo cuentan valores de 32 hex: una `inst` o un epoch vacíos o mal formados no casan con nada
    (v1.3.14) y no son la identidad de nadie; el `/hello` o el trabajo que los lleva no casa por sí.
  - De la sonda solo cuentan los trabajos de una `inst` que había saludado antes de su entrega (el
    bridge solo entrega a una instancia registrada). Un trabajo de una `inst` que no saludó no es de la
    sonda: no casa y no tapa nada de su vida (`sol_confirmed_alive_hidden` sigue en FALLA).
- **Cada vida, identidades nuevas:** ningún valor de la identidad de un lado (su `inst` o su epoch)
  apareció en una vida **anterior** de ese lado. Es más estricto que «distinta de la vida anterior»
  (brief:1306), y la repetición la paga la vida nueva: la anterior no se invalida por ella.
- **Cada trabajo** (censo o testigo) **se ata a la vida de su entrega:** su vida casa, su `(inst,
  server_epoch)` es la de la sonda en ella, la sonda saludó en ella y el producto también, con un
  `/hello` aceptado antes de la entrega (lo que ya pedía el `/hello` en vigor antes de la entrega).
  **Para juzgarlo, su epoch es el del producto en esa vida:** con él se buscan las últimas posiciones
  de F2P-07, los censos y las generaciones de F2P-10, y el `/hello` vigente del censo del control.
- **Si no casa, nunca PASA:** la medición no vale y lo que la usa da INCONCLUSO (`unbacked_rows` o el
  motivo de su comprobación). Se exige en todas las mediciones, también en las que antes no miraban
  el `tap`. F2P-07 y F2P-09 usan además la base de P1 (clases de la CE y `net_id` de la base) y F2P-07
  los censos de la vida anterior a cada reinicio del servidor: si esas vidas no casan, dan INCONCLUSO
  `server_life_unbound`, después de sus FALLA que no dependen de ellas; un extra o una reaparición
  que solo fallaría porque la base vacía no lo exime no da FALLA.
- `metrics.server_lives` resume cada vida (`desde_t_ms`, `hasta_t_ms`, `casa`, `motivo`, `producto`
  y `sonda`); es diagnóstico y no decide nada.
- Los estímulos crudos (`per_spawn_raw`, `per_cleanup_qa`) no son trabajos: se validan como antes.

Los **estímulos crudos** (`per_spawn_raw` y `per_cleanup_qa`) pasan por la misma validación de origen:
`deliver` presente, `/hello` con el sello antes de la entrega y dentro de la ventana de su parte. Sin
eso → INCONCLUSO `unbacked_rows` (R-05); una instancia sin sello no acredita el estímulo.

**Control persistente (R-09, §5.3 v1.3.10).** F2P-07 acredita su creación con la respuesta cruda de
`per_spawn_raw` con `mode = persistent_control` **al empezar P4a**, después de la limpieza de P3c y
**fuera de la zona de F2** (4860, 10200): `Barrel_Yellow` con un `Fireplace` en el cargo y
`health_mark_ratio` 0,845 (1300/1098,5), validada por la regla anterior. Sin esa respuesta, el
control no está acreditado y F2P-07 da INCONCLUSO `persistent_control_missing`. Se reconoce en su
censo propio de 30 m por clase y posición a menos de 0,5 m; si la salud es legible, también por la
marca `|health_hp / max_hp − 0,845| <= 0,01`; si da `-1/-1`, bastan clase y posición. El control está
fuera de la zona, así que dentro de ella no se exime a nada por clase ni por salud.

## 3. `samples/bridge_tap.jsonl` (proxy del producto)

`{"req_id":<int>,"t_ms","dir":"req"|"resp","method":"GET"|"POST","path":"/hello"|"/poll"|"/result"|"/catalog",
"http":<int>,"upstream_status":<int>|null,"query":{...},"body":{...}}`. Para GET, `query` lleva `peer`,`inst`,`session`,`conn`,
`deliver`; el `/result` del cable real no lleva `conn` (v1.3.15, K-01); para POST, `body` es el
cuerpo crudo. **v1.3.14 (§5.4):** el `tap` numera cada petición al
llegar con un `req_id` entero, único en la partida, y escribe el mismo `req_id` en el registro de su
respuesta; una petición sin respuesta conserva solo su registro; el orden de los `req_id` puede no ser
el de llegada. **Emparejamiento por `req_id` (v1.3.14):** cada respuesta se empareja solo con la
petición de su mismo `req_id`; nunca por orden, antigüedad ni contenido. Un registro de `/hello`,
`/poll` o `/result` sin `req_id`, una respuesta cuyo `req_id` no tiene petición y dos peticiones o dos
respuestas con el mismo `req_id` dan INCONCLUSO (`missing`, `tap_req_id_missing`) en el check de su
parte. Una petición sin respuesta no se juzga **como pareja**: no hay respuesta con la que compararla.
**v1.3.15 (K-02):** fuera de las partes con check de traza (en P1, entre partes o después de P5) un
problema de `req_id` da INCONCLUSO con el mismo motivo, `tap_req_id_missing`, igual que una violación
de traza fuera de parte; nunca se descarta en silencio. **v1.3.15 (K-08):** un `/result` sin
respuesta es un acuse que falta y rompe la traza con `ack_missing`, salvo el de la identidad cortada
de P5 mandado **hasta el `cut`, o en el mismo instante**, si ninguna petición posterior a ese
`/result` tiene respuesta antes del `cut`, emparejando por `req_id`; uno mandado después del `cut` no
está en vuelo en el corte y no queda exento. Cuentan todas las parejas petición-respuesta del `tap`
de cualquier path, incluido `/catalog` y los que no conozca (brief:554, 577 y 584-587).
**v1.3.16 (§5.4 y §6.1 punto 5):** el registro de cada respuesta puede llevar `upstream_status`: el
HTTP con que respondió el backend, o `null` si la respuesta la fabricó el tap; sin el campo cuenta
como del backend (la fixture y los taps anteriores). **v1.3.16 (T2f-15m, L-01):** un booleano no es ni
el 0 del cierre ni el `null` del tap; cuenta como respuesta del backend, igual que un registro sin el
campo. El `/result` de la identidad cortada de P5 y sus
reintentos quedan exentos dentro de la ventana que cierra la primera respuesta del backend nuevo
posterior al `cut` (cualquier petición y peer), si no tienen respuesta o tienen el 502 del tap: HTTP
502, `upstream_status` nulo y cuerpo exacto `{"ok":false,"error":"upstream_unreachable"}`. **Solo el
primero** tiene que ir mandado hasta el `cut` o en el mismo instante; los reintentos entran hasta esa
primera respuesta del backend nuevo (v1.3.16, T2f-15k, N-06). **v1.3.16 (T2f-15m, H-02):** lo que
sitúa el rechazo en el tramo del backend nuevo es su respuesta, posterior al `cut` y del backend (no
del tap: `upstream_status` ausente o un entero distinto de 0), no la hora de su petición; un reintento
pedido después del `cut` y antes del `restart` puede esperar en el `tap` y llegar al backend nuevo,
que lo rechaza con 409. La primera es la de **menor hora**, no
la primera línea del fichero: el orden de las líneas del `tap` no es el de su hora (§5.4 :338 y
:593). **Un `/result` que sobra** (fuera de la ventana, o un reenvío de la v1.3.11) pasa antes de
eximirse por las mismas reglas que uno emparejado: la sesión del query igual a la del cuerpo, la
`inst` y el `epoch` de su entrega con las anclas, el peer, la hora posterior a la entrega y el acuse
no anterior (v1.3.16, T2f-15k, N-01); si no casa con ninguna entrega de su `(session, op_id)`, rompe.
**El cuerpo del 502** es un objeto con exactamente `ok` y `error`, `ok` el booleano `False` (no `0`
ni `0.0`) y `error` `upstream_unreachable`; una respuesta de `/result` con cuerpo que no es objeto y
no es el cuerpo vacío del cierre (`""`, nulo o ausente) es un acuse no aceptado (N-02). El cierre sin
respuesta lleva el cuerpo vacío (`""`, nulo o ausente); `{}` es un cuerpo, no una respuesta vacía
(T2f-15m, L-06). Un acuse en el **mismo milisegundo** que su
resultado vale (§6.1 :555). Fuera de la ventana, con otra identidad o con el 502
antes del `cut`, rompen con `ack_rejected` o `ack_missing`. «El backend estaba vivo» se lee por la
hora de la petición posterior al primer `/result` y la respuesta del backend antes
del `cut`, de cualquier endpoint; las respuestas del tap no cuentan. En un empate de milisegundo con
un `/hello` valen los dos órdenes, uno solo por par de eventos: la entrega casa con el mismo registro
con el que casó el `/poll` que la trae; una respuesta del backend en el ms del `cut` puede ser
anterior al `cut` (y cuenta para «vivo» si su petición es posterior al primer `/result`) o posterior
(y cierra la ventana), pero no las dos cosas (T2f-15m, O-5; brief:339, 567, 568, 589-600).
**v1.3.16 (T2f-15l, §6.1 :599):** los eventos del ms del `cut` se ordenan juntos con un orden total,
el mismo para todas las reglas; la traza vale si algún orden total, con el `cut` dentro y cada
respuesta después de su petición, es admisible. Con más de cuatro eventos en ese ms, además del `cut`,
INCONCLUSO `tap_tie_group_too_large`. **El cierre sin respuesta** (HTTP 0, `upstream_status` 0 y
cuerpo vacío; §5.4 :339) no es una respuesta del backend: no cierra la ventana ni cuenta para «vivo»;
para el `/result` de la identidad cortada cuenta como «sin respuesta» si su final no es anterior al
`cut`, y si es anterior rompe como el 502 del tap. **La entrega sin registro del `/poll`** (D-02) se
compara con el registro del servidor a su hora, con el empate de C-02; sin ninguno, sigue la regla de
hoy. **W-07 (D-04)** solo exime la sesión del query en un reenvío rechazado con 400 cuyo query está en
la sesión vigente a la hora de su petición; cualquier otro desacuerdo rompe con
`query_body_session_mismatch` (brief:562, 592, 593, 597, 598). **v1.3.16 (T2f-15m, L-05/O-7):** un
400 con el query en la sesión vieja (igual al cuerpo) rompe, también si el query es igual al cuerpo;
el 409 lleva el query en la vieja (igual al cuerpo), y un 409 con el query en la vigente rompe. **El
cierre sin respuesta** (L-03) va después de su petición, como cualquier acuse; si su respuesta es
anterior a su petición rompe con `ack_before_result`.

- `/hello` req: `{"proto":"dsbx1","peer":"server","inst":"<32hex>","epoch":"<32hex>","mod_ver",
  "build","map","world_size","modset":[...],"actor_engine","scene":1}`; resp `{"ok":true,
  "session":"<16hex>",...}`. **v1.3.9:** cada instancia del backend tiene su sesión; un reinicio del
  backend (`restart` con `target: "backend"`) abre una sesión nueva y la respuesta a su `/hello` la
  entrega. La sesión de un `op.state` es la del tramo entre reinicios del backend al que pertenece su
  `t_ms`, que coincide con la de esas respuestas. **v1.3.10:** todas las respuestas a `/hello` de un
  mismo tramo dan la misma sesión, y ninguna sesión se repite entre tramos; si no, la traza se rompe
  y la comprobación de esa parte falla. **v1.3.11 (F-04):** un `/hello` solo abre sesión si su
  respuesta es HTTP 200 con `ok` booleano `true` y la sesión; uno rechazado no vale.
  **v1.3.13 (T2f-11, C-01/C-05):** la sesión de una entrega o de un resultado del servidor la abre un
  `/hello` aceptado DEL SERVIDOR, con respuesta anterior y dentro del tramo de su `t_ms`; un `/hello`
  de cliente o de otro tramo no la abre, y una respuesta a `/hello` de cualquier peer cuya sesión no
  sea la de su tramo rompe la traza. Una respuesta aceptada sin petición pendiente (o una segunda
  respuesta aceptada) no se descarta: cuenta como un `/hello` aceptado con su `resp_t` y su sesión,
  con peer desconocido; no abre la sesión de nadie ni vale como causa c, pero sí para las reglas de la
  sesión que muere y de los tramos.
  **v1.3.14 (T2f-15c):** la respuesta de un `/hello` se empareja con su petición por `req_id`. Un
  `/hello` aceptado sin `inst` no abre sesión ni registra a su peer, y una `inst` o un `epoch` vacíos
  no casan con nada en ninguna comparación de la traza (v1.3.14, anclas de identidad; bridge.py:425-427).
  **Límite:** si el tap registra una respuesta de un peer cuyo `req_id` no tiene petición, la traza no
  se puede juzgar (INCONCLUSO).
  **v1.3.13 (T2f-12, C-01/D-03/D-02):** la hora de un `/hello` aceptado es la de su RESPUESTA
  (`resp_t`), no la de su petición: así se coloca en su tramo, como vigente antes de un tiempo y
  frente a un reinicio o una entrega (brief:484, 558). La sesión de una entrega o de un resultado la
  abre un `/hello` aceptado del servidor DE LA MISMA instancia que la entrega o el resultado
  (brief:546, 558, 334; bridge.py:495-496 y :536-537). El `tap` registra cada petición de `/poll`
  con su `query` y su respuesta: una respuesta aceptada (HTTP 200) cuya sesión no es la de su tramo
  a la hora de la respuesta rompe la traza, y también la de la sesión que muere después del `cut`;
  un 409 o un 400 no la rompe (brief:550, 556-558). Un segundo terminal de la misma `(sesión, op_id)`
  da FALLA `segundo_terminal:<op_id>` en la comprobación de su etapa (o de su parte), añadida a un
  FALLA propio (brief:498); la op cortada de P5 conserva `cut_op_terminals`. El `/hello` vigente del
  censo del control tiene que ser aceptado después del reinicio del servidor que se juzga (brief:660,
  662). Un `scene.reset` de P4c con el `doc_id` de la escena 2 da INCONCLUSO
  `p4c_reset_fuera_de_guion`, sin juzgar su terminal, y nunca tapa un FALLA (§5.2 línea 246).
- `/poll` resp: `{"ok":true,"now_ms":<float>,"ops":[{"op_id","session","conn","epoch","inst","verb",
  "args","issued_ms","ttl_ms"}]}`. **v1.3.9:** tras un reinicio del backend, un `/poll` con la sesión
  vieja recibe `409 {"ok":false,"error":"hello_required"}`; no rompe la traza.
  **v1.3.14 (T2f-15c):** cada respuesta de `/poll` se empareja con su petición por `req_id`; no hay
  emparejamiento por antigüedad. Una petición sin respuesta no se juzga.
  **v1.3.13 (T2f-14, G-01/G-04):** un 200 CON ops es la respuesta a una petición del servidor que
  casa con la sesión, la `inst` y la `conn` de sus ops (solo el servidor recibe órdenes,
  bridge.py:223, :536-537 y :558); si no hay NINGUNA petición pendiente no se juzga; si las hay pero
  ninguna del servidor, consume la más antigua y rompe con `poll_peer_mismatch:<peer>` (T2f-15b,
  H-02; bridge.py:557-559); si hay del servidor y ninguna casa, consume la más antigua del servidor.
  La traza rompe con el motivo que corresponda: `poll_session_mismatch` si su sesión no es la del
  tramo, `poll_conn_mismatch` si la petición no es del registro de su peer, o
  `delivery_conn_mismatch:<op_id>` si la `inst` o la `conn` de la op no son las del registro del
  servidor a la hora de la entrega (T2f-15/T2f-15b, H-01; brief:550, bridge.py:242, :536-537, :575
  y :294-333). Cada `/hello` aceptado registra la
  `conn` de su respuesta; una petición solo admite un 200 si su `inst` y su `conn` son las del
  registro de su peer en ese tramo (bridge.py:443-448, :470 y :492-496), y un 200 a una petición que
  no lo admite rompe con `poll_conn_mismatch:<peer>`. **Anclas (v1.3.14):** una `inst` o una `conn`
  vacías no casan con nada; un `/hello` aceptado sin `inst` no registra a su peer.
  **v1.3.15 (la `conn` como la guarda real):** la `conn` se compara como en `bridge.py:484-489`:
  `int()` y `str(conn) == str(conn_s).strip()` o `conn_s.lstrip("-").isdigit()`. `"01"`, `"001"`,
  `" 1"`, `"1 "`, `"\t1"`, `"1\n"`, `"١"` y el entero `1` son la conexión 1; `"+1"`, `"1_0"`,
  `" 01"`, `"01 "`, `"1.0"`, `"0x1"`, `""` y `None` no casan con nada. La `inst` y el `epoch` se
  comparan como texto exacto, como el backend (`bridge.py:495`). **v1.3.15 (K-03):** el registro se
  toma a la hora de la PETICIÓN y tiene que ser el mismo a la de la respuesta (`bridge.py:506` y
  `:520-523`); un 200 cuyo registro cambia mientras la petición espera rompe con
  `poll_conn_mismatch:<peer>`. **v1.3.16 (C-02):** si la petición tiene el mismo `t_ms` que la
  respuesta de un `/hello` de su peer, valen los dos órdenes: la petición se admite si casa con el
  registro con ese `/hello` o sin él, y el registro a la hora de la respuesta, con el mismo criterio
  de empate, tiene que ser el mismo con el que casó (brief:567).
- `/result` req: `{"op_id","session","epoch":"<32hex>","status":"done"|"rejected"|"error","reason",
  "dup":<bool>,"read":{...}}`; resp `{"ok":true}`. **v1.3.9:** el reenvío del resultado de la op
  cortada al backend nuevo se rechaza con `409 hello_required` o `400 bad_request`; ese reenvío y su
  rechazo no cuentan como resolución y no rompen la traza.
  **v1.3.11 (F-04):** la sesión del `query` de una petición es la misma que la de su cuerpo; la
  instancia y el epoch de cada resultado son los de su entrega. Un acuse vale solo si es HTTP 2xx y
  `ok` es el booleano `true` (una cadena `"false"` o `"true"` no vale). La excepción del reenvío
  cortado vale solo para el `(sesión, op_id)` cortado, después del `cut`, en el tramo del backend
  nuevo y con el rechazo; un resultado rechazado de otra sesión con el mismo `op_id` rompe la traza.
  **v1.3.15 (K-01):** el `/result` del cable real no lleva `conn` (`DSBX_Peer.c:1497` y `:1505`). El
  oráculo no lee ninguna `conn` del `/result`: la conexión de un resultado es la de su entrega. Lo que
  no se afloja, como el backend (`bridge.py:610-617`): el resultado casa con una entrega previa del
  mismo `(session, op_id)` y del mismo peer, con la `inst` entregada y el `epoch` de la orden, y va
  después de ella en el reloj común. Un resultado de otro peer rompe con
  `result_peer_mismatch:<op_id>`; «otra conexión» rompe en las respuestas, no en los resultados.

**Órdenes internas (v1.3.9, v1.3.10).** El `state.read` de reconciliación, el `scene.observe` del
checkpoint y las compensaciones del bridge llevan id `rd-N` (`app/backend/bridge.py:234-236`), no
emiten `op.state` y su resultado aparece en el `tap` con esa identidad. La lectura de reconciliación
es del backend **nuevo**: va en su sesión, después de su `/hello` y antes de la primera entrega de
escena de ese tramo. El bridge real nunca entrega `scene.apply` ni `scene.reset` sin haber
reconciliado: tras **cada** reinicio del backend (P3, P4a y P5) hay una lectura `rd-N` en la sesión
nueva y antes de la primera entrega de escena. El bloque `scene` de una lectura (`generation`,
`pending` y `last`) nombra ops de escena, nunca la propia lectura; en P5 la lectura nombra el apply
cortado, con la sesión vieja. Si falta la lectura de reconciliación antes de `P5:apply2`, F2P-09 da
**FALLA** (§6.1 F2P-09: «Si falta, FALLA»). **El validador de la lectura (S-08, re-congelado de
2026-11-23, brief:1314-1315):** la lectura vale si la acepta el consumidor real, `_valid_read_compat` de
`app/backend/scene_live.py`, importado por el evaluador (`qa/f2p_eval.py`, `_backend_validator`). Si
ese import falla, es un error de montaje: el veredicto entero es INCONCLUSO
`backend_validator_unavailable`, nunca FALLA (hasta `98c7a78` salía como lectura no válida y daba FALLA
en F2P-05 o F2P-08). Una excepción del propio validador, ya importado, sigue siendo lectura no válida.

Entregas: toda orden `scene.apply`/`scene.reset`/`scene.observe`/`state.read` aparece en una respuesta
`/poll` (con su `session` y `op_id`); su resultado aparece en un POST `/result`. El evaluador exige
que la traza de entregas cuadre con las respuestas (`tap_trace_mismatch` → FALLA). El `read` de un
`scene.apply` lleva, además de lo de §3.6 del brief, **el checkpoint en `read.obs` con
`at == "checkpoint"`** (`[lid,ci,x_mm,y_mm,z_mm,yaw_mdeg,gy_mm]` por raíz creada, validado por
`app/backend/scene_plan.py:743-800`). El alias sintético `read.checkpoint` **no** forma parte del
cable v1.3 y se ignora (R-01). **v1.3.13 (Y-04):** una reentrega no es una etapa nueva; la etapa
pertenece a la parte de su primera entrega `(sesión, op_id)`, y una reentrega en la ventana de otra
parte no es una op de esa parte.

**Generaciones (R-08).** Cada apply se reconstruye con su testigo y su documento: cada fila del
documento casa con un solo nacimiento y cada nacimiento con una sola fila; las multiplicidades se
consumen. Un nacimiento de una clase de la escena que no encuentra fila libre es un **extra** de esa
generación, y F2P-13 lo cuenta dentro de la ventana de su apply. Las identidades se siguen por
`net_id` en las mediciones válidas, aunque la entidad se desplace; **nunca** se vuelve a buscar por
pose, tampoco en P2n. **v1.3.12 (X-05):** «raíz» quiere decir sin padre en la muestra 0 **y** sin
padre en el censo siguiente, también en P3:apply1, P3:apply2 y P4a:apply1. P5 cuenta la generación
cortada (`K`) y la del apply nuevo: 33 en correspondencia uno a uno con el documento, y cualquier
superviviente de la generación cortada es un extra (`33 + K` → FALLA). **v1.3.13 (Y-01):** en P4a,
los objetos se juzgan con el apoyo de §6 y la misma pose 3D frente al nacimiento (< 0,5 m); la
horizontal sola no basta.

**Ruido de la CE (R-12).** Las comparaciones entre censos usan solo las identidades seguidas (propias,
ajenas y escena 2). El botín nuevo de la CE no cuenta, aunque sea de una clase de la escena; el total
de P5 sale de las generaciones, no de las clases nuevas frente a P1. **v1.3.11 (F-15):** la atribución
de una entidad a una generación **no** se hace por `spawn_tick_ms` (la sonda lo deja a 0 en lo que crea
el producto); sale de la correspondencia uno a uno con el testigo y el documento, y las identidades se
siguen por `(epoch, net_id)`.

**Geometría de F2P-02 (R-13, S-14, V-10).** El nacimiento se juzga con dos condiciones: **a menos de
0,5 m** en horizontal de `(x_doc, z_doc)` (estricto: 0,5 m exactos no pasan), y apoyado en el suelo
con la `surface_y_m` de la muestra 0 del testigo y la del censo en los objetos: `<= 0,1 m` en
criaturas y `<= 2,0 m` en objetos (el origen de algunos `Land_Wreck_*` no está en el suelo). No se usa
la distancia 3D al suelo del documento: un desplazamiento horizontal de 0,4 m sobre terreno que sube
0,4 m, apoyado en su propio suelo, es PASA. Todos los comparadores usan el mismo umbral estricto.

## 4. `samples/backend.jsonl` (backend y API)

`{"seq":<int>,"t_ms":<float>,"kind":"<kind>","data":{...}}`. Kinds leídos:

- `op.state`: `data` = fila de la op (`op_id`,`state`,`origin`,`reason`,`at_ms`). **v1.3.9:** la
  identidad es `(sesión, op_id)`, con la sesión del tramo entre reinicios del backend; los ids de la
  API son `op-N` sin ceros, vuelven a `op-1` en cada sesión y se repiten entre sesiones. Solo las ops
  de la API emiten `op.state`; un `op.state` con id `rd-N` no es del backend y rompe la traza. El
  `op.state` inicial lleva `origin: "backend"` (`server.py:288`, `scene_live.py:371`). La op cortada
  de P5 no tiene terminal: su backend muere en el corte. **v1.3.13 (W-11b/X-04b):** la única
  identidad cortada es la del primer `cut` de P5 (la sesión que muere y el último `scene.apply`
  entregado en ella antes de ese `cut`); otro `cut` de P5 no exime ninguna op. Si aparece un terminal
  de esa identidad, solo se acepta con una causa probada en la sesión que muere y anterior a su
  `t_ms`: un `/result` con `status: "error"` aceptado por ese backend (acuse 2xx y `ok: true`), un
  `op.state` exactamente `parcial/sin_resultado`, o un `/hello` del servidor aceptado en el tap
  después de la entrega y antes del terminal, sin un resultado aceptado de la op entre medias. Un
  reenvío rechazado (409/400) o un `restart` del servidor solo no son causa. Sin ninguna, FALLA con
  el estado en el motivo. **v1.3.13 (T2f-8/T2f-9, Z-05/Z-03/Z-04/A-01/A-02/A-03):** se juzgan
  TODOS los terminales de la op cortada; el primero que no sea `observado/reconciliada` con causa da
  FALLA, y más de uno da FALLA `cut_op_terminals=<n>`. El terminal y la causa b tienen que ser
  anteriores al `cut`; la causa c exige un `/hello` de la misma instancia y del mismo epoch que la
  entrega, antes del `cut` y del terminal. **v1.3.13 (T2f-10, B-01/B-02/B-03/B-04):** después del
  primer `cut` de P5 (con reinicio del backend) rompen la traza una entrega de la sesión que muere
  (también `rd-N`, de cualquier verbo), un `/result` aceptado suyo de otra op, un acuse aceptado suyo
  posterior al `cut` y un `/hello` aceptado suyo con respuesta posterior al `cut`. **v1.3.13
  (T2f-14, z91):** las entregas de la identidad cortada quedan exentas de resultado solo si están en
  P5, tienen el verbo `scene.apply` de la entrega cortada y su `t_ms` es anterior o igual a su
  corte (T2f-15b, H-04; brief:555, bridge.py:563-568). Una entrega posterior al corte, fuera de P5
  o con otro verbo no queda exenta. La traza añade su
  motivo a un FALLA propio (`<motivo>;tap_trace_mismatch`) en vez de sustituirlo. Cada entrega y cada
  resultado aceptado tienen la sesión de su tramo (`session_at`) y la abrió un `/hello` aceptado
  antes de su `t_ms`. **v1.3.13 (T2f-15/T2f-15b):** la entrega tiene además la `inst` y la `conn`
  del registro del servidor a su hora; si no, `delivery_conn_mismatch:<op_id>` (brief:550,
  bridge.py:242, :536-537, :575). La causa c va por la hora de aceptación del `/hello` (`entrega <
  t(respuesta) < mín(t(cut), t(terminal))`). `_server_inst_at` y `_tap_epoch_for_inst` solo
  consideran `/hello` aceptados. No rompen el reenvío rechazado del resultado cortado ni los 409 de
  `/poll`. **v1.3.13 (T2f-11, C-01/C-03/C-06):** la sesión de cada tramo es la de las respuestas a
  `/hello` de ese tramo, de cualquier peer; tras CADA reinicio del backend (`target: "backend"`) una
  respuesta aceptada con la sesión del tramo que ese reinicio cierra rompe la traza (un acuse por su
  `ack_t` o un `/hello` por su `resp_t`), no solo tras el `cut` de P5. El epoch vigente y el tamaño
  del mundo salen solo de `/hello` aceptados; el del mundo, además, es el vigente antes de la lectura.
  La instancia y el epoch del censo del control salen del MISMO `/hello` aceptado vigente en su
  entrega (enmienda de identidad, brief:1296-1313: ese `/hello` del producto es de la vida del
  servidor del censo y lleva la identidad del producto en ella; los ids de la sonda no se comparan
  con los suyos, §2). **v1.3.13
  (Y-07/Z-06):** el censo `P2n:clean` se juzga fresco frente
  al máximo del terminal del apply y del reset; si se entregó antes, INCONCLUSO `unbacked_rows`.
  **v1.3.13 (Y-08/Z-02):** la etapa de P4c es el reset con el `doc_id` de la escena 1 antes del
  `restart` del servidor; si falta, FALLA `p4c_reset_escena1_ausente`; el censo posterior al reinicio
  también se juzga fresco frente a su terminal. **v1.3.13 (Z-01/Z-07):** `P4a:post_apply2` se juzga
  fresco frente al máximo del terminal del apply2 y del reset; el censo de P5 y la ventana `P5:apply2`
  se atan al mismo apply nuevo de Y-03 (sesión distinta de la que muere, posterior al `cut`).
  **v1.3.11 (F-05):** el estado y su motivo se comparan por **igualdad exacta** con los que emite el
  backend, nunca por prefijo; un estado inventado como `observado_inventado` no es terminal. Cada
  etapa positiva tiene su estado esperado de §5.2 (P2 y los applies, `observado`; los resets de P3,
  `parcial/contenido_ajeno`; el reset de limpieza de P2n y los resets de P4a y P4c, `observado`; P3c,
  `observado`). P4c resetea solo la escena 1 (v1.3.13, §5.2 línea 246); la escena 2 sigue aplicada
  en el backend y no se resetea. Se juzga el terminal de cada reset de P4c que haya. Una etapa
  positiva con otro terminal, como `fallido/create_failed`, hace FALLA la comprobación que la juzga
  aunque el censo cuadre.
- `api.ops`: `data` = `{"ops":[...]}` de `GET /api/ops`.
- `api.observation`: `data` = `{"ok":true,"observation":{...},"age_ms":...}` de `GET /api/observation`
  (metros, §3.8). La observación lleva `rows` con las filas de la lectura `now`. La negativa de copia
  (R-16) usa de verdad esas filas como filas del censo; si no hay respuesta cruda de la sonda que las
  respalde, el censo da INCONCLUSO `unbacked_rows` por la procedencia.
- `oracle.frozen`: `data` = `{"commit":"<40hex>","files":{"f2p_eval.py":"<64hex>",
  "f2p_mutants.py":"<64hex>"}}`.
- `pbo.stamp`: `data` = `{"pbo_sha256":"<64hex>","product_pbo_sha256":"<64hex>"}`. El nombre canónico
  del PBO de la sonda en la evidencia es **`pbo_sha256`** (no `probe_pbo_sha256`); coincide con
  `identity.pbo_sha256` del manifest.
- `restart`: `data` = `{"target":"backend"|"server","epoch":"<32hex>"}`.

Un `op.state` cuya `(sesión, op_id)` no salga de una entrega del tap y de un `/result` recibido →
FALLA (`op_state_without_event`); un `op.state` con id `rd-N` también rompe la traza. El reinicio del
backend parte los tramos de sesión: el último `scene.apply` entregado antes del `cut`, en la sesión
del backend que muere, es la op cortada; no se le exige terminal. `oracle.frozen`/`pbo.stamp` tienen
que coincidir con `manifest.json`.

## 5. `samples/scene_del.jsonl` (mod)

Una línea por señal de borrado, por tick:

```
{"t_ms":<float>,"frame":<int>,"lid":"<id>","net_low":<int>,"net_high":<int>,
 "signal_ref_b":<0|1>,"signal_pending_b":<0|1>,"signal_by_netid_b":<0|1>,
 "deleted_confirmed_b":<0|1>,"delete_failed_b":<0|1>,"confirm_tick_ms":<float>}
```

`deleted_confirmed_b==1` exige que la entidad (`net_id` = `high:low`) falte del censo siguiente
**dentro de la cobertura** (F2P-10); `delete_failed_b==1` exige que siga viva. Un confirmado que sigue
vivo → FALLA (`delete_not_observed`). Un `delete_failed_b==1` que falta → FALLA (`failed_but_missing`).
Si la posición de la entidad no se puede situar dentro del disco del censo siguiente → INCONCLUSO
(`not_covered`), nunca «borrada». **v1.3.11 (F-15):** la posición sale del último censo válido anterior
que tenga la entidad (la unión validada de sus componentes, del mismo epoch); **la posición del
documento nunca hace de posición observada**. Sin esa posición → INCONCLUSO. El epoch del borrado es el
del producto vigente a su hora, y el de cada censo y cada generación, el del producto en la vida del
servidor en que se entregó su trabajo (enmienda de identidad, §2).

**Criaturas (R-04, v1.3.11 F-02).** Para una criatura confirmada como borrada y ausente, la ausencia
se concluye solo si **un único componente** de la unión, el principal o un disco, no la tiene y cubre
el disco de radio `V_MAX · Δt + 2 m` centrado en su última posición válida, con `Δt` calculado al
`snap_tick_ms` de **ese** componente. La unión de componentes capturados en instantes distintos no
prueba nada. `V_MAX = 7 m/s` en infectados y `12 m/s` en animales (§6.1 punto 4). **El tipo** sale de
lo observado (`ai_agent_b` en su última medición válida) y de la fila del documento con la que casó su
nacimiento, **nunca** del prefijo de un `lid`; si se contradicen → INCONCLUSO `kind_mismatch`. Si
ningún componente lo cubre, o los ticks son de epochs distintos, INCONCLUSO `coverage_gap`. El runner
toma un censo justo antes de cada reset y de cada borrado que se juzga (§5.2).

**Métrica de confirmación (O-17, R-17).** El valor informado en `delete_confirm_max_ms` es la separación
entre la **primera** línea de petición del mismo `(lid, net_id)` —señal de borrado con
`deleted_confirmed_b==0` y `delete_failed_b==0`— y la línea de **confirmación**
(`deleted_confirmed_b==1`), con el mismo reloj `t_ms`. Con petición, señal intermedia y confirmación en
tres frames consecutivos separados 33 ms, la métrica es 66 ms, no 33 ms. No se resta el tiempo de la
propia línea confirmatoria.

## 6. Frescura y cobertura

- Cobertura = discos de `per_census_start`/`per_witness_start` declarados en sus `nk`
  (`center_x_m`,`center_z_m`,`radius_m`) más los discos extra por entidad seguida. Una entidad seguida
  que falta de todos los discos y podía haber salido de lo cubierto (criatura, o a menos de 15 m del
  borde) → INCONCLUSO (`coverage_gap`), nunca «borrada».
- **Última posición conocida (R-09).** Para F2P-07, la última posición de una entidad de una
  generación de F2 es la de la **última medición válida anterior al reinicio** que la contenga, no la
  de nacimiento. Una entidad de una clase de la escena 1 que reaparezca a menos de 2 m de esa posición
  (aunque no case con el documento) → FALLA. Los reinicios se acreditan con el epoch del `/hello`
  nuevo, el evento de reinicio del runner y el mismo `storage.id`; el `server_epoch` de la parte, si
  está, tiene que coincidir con ese `/hello`; si no está, no falta nada. Reutilizar el epoch anterior
  → INCONCLUSO. Esa «última medición válida» es de la vida del servidor anterior al reinicio, con el
  epoch del producto en ella; si esa vida no casa (§2), F2P-07 da INCONCLUSO `server_life_unbound`.
- `surface_y_m` tiene que salir en las filas y variar con la posición; constante o ausente → FALLA
  (`surface_y_constant` / `surface_y_missing`), y F2P-11 no PASA.
- `net_id=="0:0"` en una entidad creada → FALLA (`net_id_zero`).

## 7. Negativas contra la fabricación (obligatorias, nunca PASA)

El oráculo lleva estas negativas, y las pruebas offline comprueban que dan FALLA o INCONCLUSO, nunca PASA:

- filas sin respuesta cruda de la sonda que las respalde (`unbacked_rows`), o con trabajo, página,
  epoch o sello que no casan (`job_mismatch`, `page_mismatch`, `epoch_mismatch`,
  `probe_stamp_mismatch`, `missing_page`), o tomadas antes del efecto (`stale_rows`);
- `net_id` `0:0` en lo creado (`net_id_zero`);
- `surface_y_m` constante o ausente (`surface_y_constant`, `surface_y_missing`);
- un `op.state` sin su evento (`op_state_without_event`);
- una traza de entregas que no cuadra con las respuestas (`tap_trace_mismatch`);
- el commit del oráculo o los sellos de los PBO que no coinciden (`oracle_modified`, `pbo_mismatch`);
- un censo vacío o sin los edificios conocidos del baseline por clase y pose (`empty_census`,
  `baseline_missing`);
- filas de censo copiadas de una observación del backend sin respuesta cruda de la sonda que las
  respalde, aunque sean geométricamente aceptables (`unbacked_rows`, R-16);
- **identidades que no casan con la vida del servidor** (enmienda de identidad, §2): dos identidades
  del producto o de la sonda en una misma vida, una vida sin el `hello` de la sonda, una identidad
  repetida en dos vidas, un trabajo con la identidad de otra vida, un reinicio del servidor sin su
  `restart` o un `restart` del servidor sin reinicio (`ID_NEGATIVES`, INCONCLUSO). La positiva con los
  ids del juego (la sonda con los suyos y el producto con una `inst` y un epoch distintos) da PASA
  (`ID_POSITIVES`).

`qa/f2p_mutants.py` expone `SECTION6_MUTANTS` y `SECTION6_NEGATIVES`: el mapa explícito de cada punto de
§6 del brief a los mutantes/negativas reales que lo tumban. Las pruebas offline verifican que no falta
ninguno.

## 8. Arnés del núcleo, builds y checkout (O-15, H-3, H-5, H-7)

- **Una campaña por build.** La partida se entrega como una campaña diag y una campaña retail, cada una
  con **una sola parte `run`**. No existe `run-retail`: el build retail va en su propio `BASE/run/`.
- **Artefactos que exige el núcleo** (`qa/f03_common.py`, `aggregate_spike`) en cada parte `run`:
  - `part.json` con un `op_nonce` **único** de 16 hex en minúsculas;
  - la identidad de implementación común: `git_head` real, `git_dirty` coherente, `build`,
    `identity.params` con `wire_cap = wire.WIRE_CAP` y los parámetros D12 (`probe_budget_log_poll_ms`,
    `probe_budget_retry_ms`), `peer_builds` y `probe_stamp = compute_probe_stamp_at_commit(git_head)`;
  - los `/hello` de server y client con `proto = "qa0"`, el build de la parte y
    `probe_ver = dsbx-qa1+<probe_stamp>`;
  - `verdict.json` de la parte (lo escribe el runner con el veredicto del oráculo);
  - **ningún** evento `wire_cap_exceeded` en `samples/bridge.jsonl`.
- **Los mutantes de F2P son sin conexión.** `qa/f2p_mutants.py` **no** exporta `EXPECTED_MUTANTS`: la
  agregación de §7 se prueba con `f03_common.aggregate_spike`, que exige solo la parte `run`. La tabla
  `EXPECTED_MUTANTS` del núcleo es para mutantes en partida (`injection.json`) y no admite `missing` en
  `must_fail_checks`.
- **El checkout tiene que estar en LF** (H-5, brief §5.1). El núcleo compara bytes sin normalizar y el
  repo no tiene `.gitattributes`; un checkout con `core.autocrlf=true` trae CRLF y da INCONCLUSO
  `oracle_modified`. El runner de T4 corre con `git -c core.autocrlf=false` y entrega ficheros LF,
  UTF-8 sin BOM.

