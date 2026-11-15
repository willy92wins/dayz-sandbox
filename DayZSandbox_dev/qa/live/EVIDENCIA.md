# Evidencia de F1b-peers en partida

Contrato entre `f1bp_live.py` (la escribe) y `f1bp_eval.py` (la juzga, sin efectos). Lo exige el brief `plans/2026-11-15-m1-f1b-peers-partida-brief.md` (v1.5), §5 y §6.

## Carpeta
`DayZSandbox_dev/evidence/m1/F1b-peers/<build>-<UTC>/`, nueva y vacía en cada corrida:
- `manifest.json`;
- `samples/proxy.jsonl` (lo escribe `fault_proxy.py`);
- `samples/G<n>.jsonl`, uno por escenario corrido;
- `logs/server_script.log`, `logs/client_script.log`, `logs/server.RPT`, `logs/client.RPT` y `logs/inventory.json`, copiados tras cerrar el juego;
- `verdict.json`, que escribe el evaluador.

Todos los JSON van con claves ordenadas, en UTF-8 y con LF. **Ningún fichero lleva una clave**: solo su `sha256`.

## `manifest.json`
```json
{"build": "diag|retail|fake", "fake": false, "git_head": "<sha>", "git_dirty": false, "pbo_sha256": "<hex>",
 "dayz_version": "<texto o null>", "ports": {"web": 0, "bridge": 0, "proxy": 0},
 "key_sha256": ["<hex>", "..."], "lease_ms": 3000, "hold_ms": 2000,
 "scenarios": ["G1", "G2"], "t0_ms": 0.0, "t0_wall": "HH:MM:SS.mmm"}
```
`t0_wall` es la hora de pared local en el mismo instante que `t0_ms`, con el formato de las líneas del log.
`fake: true` (con `build: "fake"`) marca el ensayo en seco con el mod falso (brief §7). Ahí los logs de `logs/` los escribe el orquestador a partir del registro de efectos del falso, y no hay RPT. `t0_ms` es el monotónico del arnés al empezar. **Todos los `t_ms` de la carpeta (`samples/*.jsonl` y `proxy.jsonl`) están en ese mismo reloj**, en ms. El backend corre en el mismo proceso, así que su monotónico es ese.

## `samples/G<n>.jsonl`
Una línea por evento: `{"t_ms": <float>, "ev": "<tipo>", ...}`.

**Comunes:**
- `start` `{scenario, wall}` y `end` `{status: "ok"|"aborted", reason}`. `wall` es la hora de pared local (`HH:MM:SS.mmm`) en el instante del `t_ms` del `start`: es el ancla para situar las líneas del log en el reloj del arnés.
- `rules` `{version, rule_ids}` cuando se escribe una versión, y `rules_active` `{version}` cuando `rules_active.json` la confirma. **Una inyección solo cuenta tras su `rules_active`.**
- `apply` `{op_id, http_status, ttl_ms}`: cada `POST /api/apply`.
- `op_state` `{op_id, state, reason}`: cada transición de una op, leída de los eventos del backend.
- `result_seen` `{op_id, status, reason, dup}`: cada resultado que el bridge recibe de una op, leído del bridge en su `t_ms` de recepción. El proxy no ve los cuerpos.
- `bridge` `{session, server, client, catalog}`: foto del bridge.
  - `server` y `client` son `{conn, inst, epoch, lost}` o `null`.
  - `catalog` es `{complete, n_classes, catalog_id}` o `null`.
- `backend_restart` `{old_session, new_session}`.
- `config` `{peer, qa_step_gap_ms, key_sha256}`: cada reescritura de `dsbx_peer.json`.
- `recovery` `{op_id}`: la orden nueva de la recuperación; tiene que llegar a `observado` en 60 s.
- `key_scan` `{files, hits}`: búsqueda literal de todas las claves usadas en los logs copiados. `files` es la lista de rutas y `hits` el número de apariciones.

**Por escenario:**
- **G1:** `connected` `{peer}` en el primer hello 200 de cada peer (proxy), y `client_alive` `{at_ms, connected}` a los 120 s en retail.
- **G3:** `case` `{name: "a"|"b"|"c", op_id}`. El caso c lleva antes una regla `rewrite` de `ops.0.args.rev`.
- **G4:** `case` `{name: "a"|"b"|"c", op_id}`. En el caso b, `stale_order` `{op_id, old_session}`. En el caso a, `bad_key_window` `{t_start_ms, t_end_ms}`.
- **G5:** `case` `{name: "a2500"|"a4500"|"b2500"|"b4000", peer, op_id}`, más `window` `{t_start_ms, t_end_ms}`. Antes de G9, `gap_reset` `{confirmed}`.
- **G6:** `pause_order` `{op_id, T_d_ms, T_s_ms, T_e_ms, D_ms}` y `clock_run` `{t_start_ms, t_end_ms}`.
- **G7:** `case` `{name, rule_id}`, con nombres `status400_P` … `status500_R`, `timeout_P`, `r_held`, `invalid_*`, `measure_*` y `late_cb`. Las respuestas que el validador puede aceptar (`ok:1`, `args:{}`) son medidas (`measure_*`), no casos `invalid_*`.
- **G8:** `case` `{name: "a"|"b"|"c", op_id}`.
- **G9:** `mix_op` `{op_id}`, cien.

## Líneas del script log (`logs/*_script.log`)
Se extrae el texto que sigue a `[DSBX] ` en cada línea. Formas que se leen (el resto se ignora):

**Reloj** (brief v1.4, §10, H-04):
- `tick_ms` es el reloj del motor de ese proceso, no el del arnés. Solo se usa para la pendiente y el salto de G6.
- Una línea se sitúa en el reloj del arnés por la hora de pared que la encabeza (`HH:MM:SS.mmm`): `t = t_ancla + (hora_línea − hora_ancla)`, con el cruce de medianoche.
- El ancla es el `start` del escenario (`t_ms`, `wall`) o, si no lo trae, el manifest (`t0_ms`, `t0_wall`).
- Las ventanas toleran ±250 ms. Entre casos seguidos de G7, la cota alta es el caso siguiente, sin ensanchar.
- Sin ancla, las filas que usan ventanas (G4, G5 y G7) son INCONCLUSO.
- En el ensayo en seco (`fake: true`), `tick_ms` ya está en el reloj del arnés.
```
effect step=<retirar|anotar> session=<s> op=<op> tick_ms=<n>
rest error ch=<P|R> kind=<n> state=<n> tick_ms=<n>
rest timeout ch=<P|R> kind=<n> src=<engine|watchdog> tick_ms=<n>
rest invalid ch=<P|R> kind=<n> tick_ms=<n>
rest late ch=<P|R> kind=<n> tick_ms=<n>
rest repeat ch=<P|R> kind=<n> via=<success|error|timeout> tick_ms=<n>
lease lost age_ms=<n> tick_ms=<n>
clock tick_ms=<n>
config qa_step_gap_ms=<n>
hello accepted session=<s> conn=<n>
shutdown role=<server|client> created_n=<n> inflight_p=<0|1> inflight_r=<0|1>
```
Las líneas `SCRIPT (E)` o `Can't compile` que mencionan `DSBX_` cuentan como errores de script, también en el RPT. El motor rellena con espacios (`SCRIPT    (E):`).

**Excepción, el informe de cierre del motor** (brief v1.3, §10, H-03). `Leaked 'DSBX_Callback' script instance (Nx)!` no cuenta como error si 0 < N ≤ cota:
- en un script log, la cota es la suma de `created_n` de las líneas `shutdown` anteriores del mismo fichero;
- en un RPT, es la de todo el script log del mismo peer (el RPT del cliente no lleva las líneas `[DSBX]`).

Sin `shutdown`, con N fuera de la cota o con cualquier otra clase `DSBX_`, cuenta como error. El motor retiene todo `RestCallback` que recibe, así que N = `created_n` es lo esperado.

## `verdict.json`
```json
{"aggregate": "PASA|FALLA|INCONCLUSO",
 "rows": {"G1": {"verdict": "PASA|FALLA|INCONCLUSO", "reason": "<texto>", "metrics": {}}}}
```
- `aggregate` es FALLA si alguna fila falla, INCONCLUSO si alguna lo es y ninguna falla, y PASA en otro caso.
- Una fila de `manifest.scenarios` sin `samples/G<n>.jsonl`, o con un `end` en `aborted`, es INCONCLUSO.
- Con `git_dirty: true`, todas las filas son INCONCLUSO.
- Una fila que necesita un log ausente es INCONCLUSO (la ausencia no es «cero»).

## Criterios por fila
Son los del brief, §5. «Recuperación» quiere decir un `recovery` cuya op llega a `observado` en 60 s desde el evento anterior del caso.
- **G1:** `connected` de los dos peers; ningún error de script de `DSBX_` en los logs ni en el RPT (con la excepción del informe de cierre de arriba, anotado en `metrics.exit_leak_cb` con `file`, `n` y `bound`); en retail, `client_alive.connected`. Con `fake: true`, G1 no se evalúa (INCONCLUSO).
- **G2:** foto `bridge` con el epoch del cliente igual al del servidor y `catalog.complete` con `n_classes > 0`; la mayor `req_bytes` de `route: catalog` en el proxy, con `upstream_status` 200, está entre 3000 y 3499 (con `fake: true` este criterio no aplica y se anota); el `req_bytes` del hello del servidor es < 3500.
- **G3:**
  - a y b: `observado`, con exactamente una `effect retirar` y una `effect anotar` cada una (por `session` y `op`).
  - c: `fallido` con `reason` `lectura_no_cumple`, y nunca `observado`. Sus `effect` son esperables, porque el peer anota la revisión reescrita (D-P2); solo se anotan.
  - Recuperación tras el caso c, que es la inyección; a y b no la necesitan.
- **G4:**
  - a: dentro de `bad_key_window`, hellos del servidor con `upstream_status` 401 y ninguna `effect`; la op del caso a sin `effect` nunca.
  - b: la `stale_order` sin `effect` y con resultado `rejected` (motivo `stale_session`) si llega al proxy.
  - c: `op_state` `fallido/conexion_perdida` y ninguna `effect` para su op.
  - Recuperación tras cada caso, y `key_scan.hits == 0`, con `files` que cubre el inventario de los dos perfiles.
- **G5:**
  - a2500: el mayor intervalo entre dos respuestas 200 a ese peer (proxy, por `t_done_ms`) dentro de la ventana y hasta la primera respuesta tras ella es < `lease_ms`, y no hay `lease lost` en su log en la ventana.
  - a4500: `lease lost` en su log con `lease_ms ≤ age_ms < lease_ms + 200`.
  - b2500: una `retirar`, una `anotar` y `observado`.
  - b4000: una `retirar`, cero `anotar`, `op_state` `parcial` con `reason` `lease_expired`, y nunca `fallido`.
  - Recuperación tras cada caso. `gap_reset.confirmed` con `config qa_step_gap_ms=0` en el log del servidor.
- **G6:**
  - FALLA si hay un `result_seen` de la op de `pause_order` con `status: "done"` y `t_ms > D_ms + 150`;
  - PASA si su `result_seen` es `rejected` o `error` con `reason: "expired"`;
  - INCONCLUSO si hay algún `result_seen` de esa op con `t_ms < T_s_ms`, o ninguno.
  - Son medidas, sobre las `clock` del servidor: la pendiente de su `tick_ms` frente al reloj del arnés (por la hora de pared de cada línea) y el salto de `tick_ms` y de tiempo entre las dos `clock` que rodean la pausa.
  - Recuperación.
- **G7:**
  - Invariantes:
    - `r_held`: los polls de mantenimiento del servidor (proxy, `deliver: 0`) sin huecos de más de 750 ms mientras el acuse de R está retenido;
    - `invalid_*`: una línea `rest invalid` por cada respuesta reescrita no válida, ninguna `effect` en la ventana, y `lease lost` si todas las de P fueron no válidas durante más de `lease_ms`;
    - `late_cb`: si hay `rest late` o `rest repeat`, ningún cambio de estado en su ventana; si no hay ninguna, el caso es INCONCLUSO (anotado) sin tumbar la fila.
  - Medidas: el estado de cada `status*` (de su línea `rest error` o `rest invalid`) y el plazo efectivo de `timeout_P`.
  - Recuperación.
- **G8:**
  - a: una pareja de `effect` y ningún cambio por el resultado repetido;
  - b: una sola pareja de `effect` y un `result_seen` con `dup: true` después de la reentrega;
  - c: la op de la sesión nueva con su propia pareja de `effect`.
- **G9:** cien `mix_op`. Latencia de cada una = `t_ms` del `op_state` `observado` − `t_ms` de su `apply`; `inf` si no llega. p95 sobre las cien, con los fallos en el denominador (como `qa/s_puente_eval.py`, `_m2`), < 1000 ms. Una pareja de `effect` por op.

## v1.5: reglas tras la ronda 1 de Sol (brief §10, Q-01..Q-15)
Mandan sobre lo anterior cuando choquen. Quién lo hace: **L** = lanzador (`run_f1bp_partida.ps1`), **O** = orquestador (`f1bp_live.py`), **E** = evaluador (`f1bp_eval.py`), **P** = proxy (`fault_proxy.py`).

- **R1, procedencia (Q-14; O, L).**
  - `manifest.git_head` es el SHA completo de `HEAD` de la raíz del worktree.
  - `git_dirty` es `true` si `git status --porcelain -- . ":(exclude)DayZSandbox_dev/evidence"`, corrido en esa raíz, da algo. Cubre también `DayZSandbox/`.
  - El lanzador usa la misma comprobación antes de lanzar.
- **R2, logs finales (Q-15; L, O, E).**
  - `logs_ready.json` (en la carpeta de evidencia) es `{"all_closed": <bool>}`.
  - Sin `fake`, si falta o `all_closed` no es `true`, **todas las filas son INCONCLUSO** («logs no finales») y el orquestador sale con 2.
- **R3, inventario (Q-12; L).** `logs/inventory.json` es:
  ```json
  {"server": {"dir": "<ruta absoluta del perfil>", "files": ["<nombre>", "..."]},
   "client": {"dir": "...", "files": ["..."]},
   "copies": [{"peer": "server", "src": "<nombre>", "dest": "server_script.log"}, "..."]}
  ```
  `files` son todos los `.log`, `.RPT`, `.ADM` y `.mdmp` del perfil al cerrar.
- **R4, claves (Q-13; O, E).**
  - `key_scan` busca todas las claves en cada fichero del inventario (`dir` + nombre, en el perfil) y en las copias de `logs/`. `files` son rutas absolutas.
  - Cualquier `hits > 0` en cualquier escenario hace **FALLA el agregado**, con el motivo «clave en los logs», sean cuales sean las filas. El orquestador sale con 1.
  - G4 exige además que `files` cubra todo el inventario (comparación de rutas sin distinguir mayúsculas).
- **R5, sesión (Q-07; O, E).**
  - `apply`, `case` (cuando lleva `op_id`) y `op_state` llevan `session`: la sesión del bridge a la que pertenece la op.
  - Los efectos se casan por `(session, op)`, nunca solo por `op` (el backend reiniciado vuelve a `op-1`).
- **R6, tiempo del apply (Q-11; O, E).**
  - `apply.t_ms` es el instante **antes** de enviar el POST, y `apply.t_end_ms` el de su respuesta.
  - `op_state.t_ms` es el instante del suceso según el backend, si su evento lo trae; si no, el de lectura, con `t_src: "lectura"`.
  - Una latencia negativa en G9 hace la fila INCONCLUSO («evidencia inválida»).
- **R7, cobertura (Q-03; E).** Sin el conjunto obligatorio de casos, cada uno una sola vez, la fila es **INCONCLUSO** («cobertura incompleta: …»):
  - G3: a, b, c.
  - G4: a, b, c.
  - G5: a2500 y a4500 de `server` y de `client`, b2500, b4000 y `gap_reset`.
  - G6: `clock_run` y `pause_order`.
  - G7: `status{400,401,409,413,500}_{P,R}`, `timeout_P`, `r_held`, `invalid_no_ok_P`, `invalid_ok_false_P`, `invalid_now_decimal_P`, `invalid_now_text_P`, `invalid_no_args_P`, `invalid_all_P`, `measure_ok1_P`, `measure_args_empty_P` y `late_cb`.
  - G8: a, b, c.
  - G9: cien `mix_op` con cien `op_id` distintos.
- **R8, efectos (Q-04; E).** Cada línea `effect` del script log cuenta una vez, identificada por fichero y número de línea; no se deduplica por tick.
- **R9, inyección observada (Q-05; O, E).**
  - Todo `case` con inyección lleva `rule_id` (o `rule_ids`).
  - El caso solo cuenta si `proxy.jsonl` trae al menos una línea con ese `rule_id` y un `rules_version` igual o mayor que el confirmado para el caso, después de su `rules_active`. Si no, la fila es **INCONCLUSO** («inyección no observada»).
  - Aplica a G3 c, G4 a/b/c, G5, G6 (`g6_deliver`), G7 y G8 a/b.
  - Las medidas (`status*`, `measure_*`) anotan lo observado en su ventana: la línea `rest …` o ninguna, y el estado de la op si la hay.
- **R10, fin de una inyección (Q-09; O, E).**
  - Al quitar las reglas de un caso, el orquestador escribe `rules` con `rule_ids: []` y su `rules_active`.
  - La ventana de prohibición de un caso va de su primer disparo en el proxy a ese `rules_active` vacío; la recuperación posterior queda fuera.
- **R11, cadencia (Q-08; E).**
  - G5 a solo cuenta respuestas 200 de las rutas de P (`hello`, `poll`) a ese peer.
  - G7 `r_held` mide los huecos entre polls de mantenimiento en toda la ventana: del disparo del acuse retenido a su liberación (`t_done_ms` de esa línea del proxy), extremos incluidos.
- **R12, validez de G6 (Q-10; E).** Si algo de esto falla, la fila es INCONCLUSO («preparación inválida»):
  - `T_d ≤ T_s < T_e`;
  - `T_e − T_s ≥ 1900`;
  - `T_s − T_d ≤ 300`;
  - `T_s < D < T_e`;
  - el `apply` de la op con `ttl_ms` 1500.
- **R13, barrera (Q-02; P).** Al activar una versión, el proxy **primero** aborta las peticiones en vuelo que casan con sus reglas `abort_inflight`, y **después** publica `rules_active.json`.
- **R14, identidad de procesos (Q-01; L).**
  - El cliente retail propio es el único `DayZ_x64` cuyo comando lleva el perfil de cliente de la corrida (`-profiles=<C>`).
  - Con cero o varios candidatos no se adopta ninguno, no se cierra ninguno y **no se suelta el lease**.
  - Una identidad sin instante de creación nunca se cierra y bloquea la suelta del lease mientras su PID exista.
- **R15, ensayo en seco (Q-06; O).** El seco no añade `peer` a la URL del hello: el proxy lo saca del cuerpo, como con el mod real.
