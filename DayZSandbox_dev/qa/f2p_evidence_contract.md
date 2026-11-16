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
    "end_t_ms":<float>,"server_epoch":"<32 hex>","storage_id":"<id>"}`. Ventanas crecientes y sin
    solape; las nueve, una vez cada una. Todo evento de `samples/` usado por el evaluador tiene que
    caer dentro de la ventana de su parte.

Si falta una clave, un valor tiene forma inválida, o `oracle_files`/`oracle_commit`/sellos PBO no
coinciden con lo observado en `backend.jsonl` → INCONCLUSO (`manifest_incomplete`,
`oracle_modified`, `pbo_mismatch`), nunca PASA.

## 2. `samples/bridge.jsonl` (sonda)

Eventos del `QABridge` de F0.3 tal cual (`qa/bridge_qa.py:475-489`, `qa/f03_common.py:504-549`):

- `{"t_ms","ev":"hello","peer":"server"|"client","inst","http":200,"ok":true,"args":{"proto":"qa0","build","probe_ver","inst","peer"}}`
- `{"t_ms","ev":"enq","peer","op_id","verb","args","inst"}`
- `{"t_ms","ev":"deliver","peer","op_id","verb","args","inst"}`
- `{"t_ms","ev":"poll","peer","inst","http":200,"now_ms","op_ids":[...],"n_ops"}`
- `{"t_ms","ev":"result","peer","inst","http":200,"op_id","result":{"op_id","status","reason","read"}}`
  con `read` empaquetado (`sk/sv/nk/nv/ncol/ncell/scol/scell/rows`, `qa/wire.py:212`).

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
la op y la que respondió tienen que ser la misma; `resource` correcto, `state=="done"`, `server_epoch`
igual al de su parte, y `probe_ver=="dsbx-qa1+"+identity.probe_stamp` en el `hello` de esa instancia.
La página 0 se exige **siempre**, también con `pages_n==0`: `read_job_pages` de la sonda lee la 0 y
después hasta `pages_n-1` (`qa/f03_common.py:1130-1149`), y `pages_n`/`rows_total_n` valen 0 cuando el
trabajo no tiene filas. Con `pages_n>0` se exigen las páginas 1..`pages_n-1`. El `t_ms` de la página
tiene que ser **posterior** al arranque del trabajo y al efecto que juzga (resultado del
apply/reset/reinicio). Si no hay página válida → INCONCLUSO (`unbacked_rows`); si la página es anterior
al efecto → INCONCLUSO (`unbacked_rows`), porque una medición no respaldada no es una FALLA (§6.1
punto 1 del brief v1.3.4).

## 3. `samples/bridge_tap.jsonl` (proxy del producto)

`{"t_ms","dir":"req"|"resp","method":"GET"|"POST","path":"/hello"|"/poll"|"/result"|"/catalog",
"http":<int>,"query":{...},"body":{...}}`. Para GET, `query` lleva `peer`,`inst`,`session`,`conn`,
`deliver`; para POST, `body` es el cuerpo crudo.

- `/hello` req: `{"proto":"dsbx1","peer":"server","inst":"<32hex>","epoch":"<32hex>","mod_ver",
  "build","map","world_size","modset":[...],"actor_engine","scene":1}`.
- `/poll` resp: `{"ok":true,"now_ms":<float>,"ops":[{"op_id","session","conn","epoch","inst","verb",
  "args","issued_ms","ttl_ms"}]}`.
- `/result` req: `{"op_id","session","epoch":"<32hex>","status":"done"|"rejected"|"error","reason",
  "dup":<bool>,"read":{...}}`; resp `{"ok":true}`.

Entregas: toda orden `scene.apply`/`scene.reset`/`scene.observe`/`state.read` aparece en una respuesta
`/poll` (con su `session` y `op_id`); su resultado aparece en un POST `/result`. El evaluador exige
que la traza de entregas cuadre con las respuestas (`tap_trace_mismatch` → FALLA). El `read` de un
`scene.apply` lleva, además de lo de §3.6 del brief, `checkpoint` con una fila
`[lid,ci,x_mm,y_mm,z_mm,yaw_mdeg,gy_mm]` por raíz creada (el checkpoint que declara el mod).

## 4. `samples/backend.jsonl` (backend y API)

`{"seq":<int>,"t_ms":<float>,"kind":"<kind>","data":{...}}`. Kinds leídos:

- `op.state`: `data` = fila de la op (`op_id`,`state`,`origin`,`reason`,`at_ms`).
- `api.ops`: `data` = `{"ops":[...]}` de `GET /api/ops`.
- `api.observation`: `data` = `{"ok":true,"observation":{...},"age_ms":...}` de `GET /api/observation`
  (metros, §3.8).
- `oracle.frozen`: `data` = `{"commit":"<40hex>","files":{"f2p_eval.py":"<64hex>",
  "f2p_mutants.py":"<64hex>"}}`.
- `pbo.stamp`: `data` = `{"pbo_sha256":"<64hex>","product_pbo_sha256":"<64hex>"}`. El nombre canónico
  del PBO de la sonda en la evidencia es **`pbo_sha256`** (no `probe_pbo_sha256`); coincide con
  `identity.pbo_sha256` del manifest.
- `restart`: `data` = `{"target":"backend"|"server","epoch":"<32hex>"}`.

Un `op.state` cuyo `op_id` no salga de una entrega del tap y de un `/result` recibido → FALLA
(`op_state_without_event`). `oracle.frozen`/`pbo.stamp` tienen que coincidir con `manifest.json`.

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
(`not_covered`), nunca «borrada». La posición se toma del último censo anterior que tenga la entidad;
si no está, del documento por `lid`.

**Métrica de confirmación (O-17).** El tick informado en `delete_confirm_max_ms` es la separación entre
la primera línea de **petición** del mismo `(lid, net_id)` —señal de borrado con
`deleted_confirmed_b==0` y `delete_failed_b==0`— y la línea de **confirmación**
(`deleted_confirmed_b==1`), con el mismo reloj `t_ms`. Una sola línea que lleve señal y confirmación usa
su `confirm_tick_ms` como confirmación. No se resta el tiempo de la propia línea confirmatoria.

## 6. Frescura y cobertura

- Cobertura = discos de `per_census_start`/`per_witness_start` declarados en sus `nk`
  (`center_x_m`,`center_z_m`,`radius_m`) más los discos extra por entidad seguida. Una entidad seguida
  que falta de todos los discos y podía haber salido de lo cubierto (criatura, o a menos de 15 m del
  borde) → INCONCLUSO (`coverage_gap`), nunca «borrada».
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
  `baseline_missing`).

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

