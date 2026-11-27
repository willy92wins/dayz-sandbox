# F3 sin juego (parte 2): mandar los actores al mod, observarlos y retirarlos con el reset

2026-11-26 · tarea **F3-offline-2**, sobre F3-offline-1 (`39c972e`) · spec de implementación (R25) de la parte de F3 del [plan de M1 v2](2026-10-26-m1-cine-v2.md) (§3 F3, decisiones #5, #12-#15 y #29) que no necesita partida · contrato: `product-spec.md` C1, C5 y el cierre de A2-A4 con actores (CX-01) · v0.2, tras la ronda de Gemini Neon (§14).

**Por qué ahora.** La parte 1 fijó qué devuelve el mod de un actor (§2 de su brief) y cómo se juzga. Falta el camino de ida: que una escena con actores, con un motor de actores presente, llegue al mod, se compruebe y se pueda retirar. Igual que la parte 1, **nada de esto depende de lo que mida S3**: el motor real (el adaptador de Expansion) sigue fuera; aquí el único motor «disponible» es el falso de las pruebas.

**Regla que manda sobre todo el brief.** El contrato F2 v1.3.16 está **congelado** (`plans/2026-11-15-m1-f2-partida-brief.md`) y su oráculo (`qa/f2p_*`) se comprueba byte a byte. Por eso los actores **no entran en `scene.apply` ni en `scene.reset`**: van en una familia de verbos propia (`actor.*`) que `SceneLive` encadena **después** de un `scene.apply` observado y **después** de un `scene.reset` cumplido. Una escena sin actores, o un servidor con `actor_engine = "none"`, recorre exactamente el camino de hoy, orden a orden y estado a estado (§9.4, T-R).

**Proceso.** Se prueba entero sin juego, así que no pasa por Sol si el gate y las mutaciones lo prueban (regla del 26-nov). El diseño lo revisa **Gemini Neon** en una ronda; lo implementan las lanes (§12); gate y mutaciones en la nube.

## 0. Qué es y qué no

Es:
- **validar los actores** cuando el servidor presentado tiene motor (§3): un paso nuevo en `validate_for_apply` que solo corre con `actor_engine = "expansion"`; sin motor, el paso 1 de hoy (`expansion_unavailable`) no cambia;
- **las órdenes de actor** (§2): `actor.apply` (una por actor), `actor.reset` y `actor.observe`, con su forma exacta en el cable;
- **el encadenado en `SceneLive`** (§4): tras el `observado` de la escena, una etapa de actores que deja la operación en `aplicado` hasta juzgar a todos; tras el reset de la escena, un `actor.reset`; y la pérdida de una orden de la etapa (§4.4);
- **la lectura de actores por la API** (§5): `POST /api/actors/observe` y `GET /api/actors/observation`, la base del muestreo de C2-C4 en partida;
- **el mod falso y el mundo falso con motor** (§6): `FakeMod(actor_engine=...)` y los tres verbos en `fake_world.py` sobre el `FakeActorEngine` de la parte 1;
- **el despacho en el núcleo del mod** (§7): `DSBX_ActorOps.c` llama al motor registrado; con el motor base, todo verbo de actor se rechaza con `expansion_unavailable`.

No es:
- el adaptador de Expansion, el muestreo a 10 Hz en partida (`[verify S-perf]`: si `actor.observe` por el bridge no da 10 Hz, el muestreo pasa al mod con su propia ventana) ni `m1_gate.py phase F3`;
- la web: no muestra actores ni los motivos nuevos (sale el motivo tal cual, como hoy cualquier `reason`);
- compensar la etapa de actores: si un actor falla, la operación queda `parcial` con su motivo y el reset del usuario lo limpia todo (§4.3). No hay compensación automática de actores en esta parte;
- cambiar `scene.apply`, `scene.reset`, `scene.observe`, `state.read`, `build_plan`, la expectativa, los predicados de F2, `qa/`, el esquema ni `validate.py`.

Trazabilidad (R20): §2-§4 salen de C1, C5, #5 y #29 (CX-01); §5 de C2-C4 (la lectura que consumen los jueces de la parte 1); §6 de #24; §7 de #5. Lo que no trace a esto no entra.

## 1. Entorno y fronteras

Gate en la nube (Linux, Python 3.13), comandos de `reference-cloud-gate-m1`: `python3 -m unittest discover -s app/tests -t app` y `python3 -m unittest discover -s qa/tests -t .`. Ninguna dependencia nueva.

**Se tocan solo**:
- `app/backend/scene_plan.py`: `validate_for_apply` gana el parámetro `actor_engine="none"` y el paso 1b (§3); el paso 6 salta los actores (§3); función nueva `build_actor_orders` (§2.1);
- `app/backend/scene_live.py`: §4 y §5;
- `app/backend/bridge.py`: el aviso a `SceneLive` cuando se descarta una orden interna (§4.4), en los tres sitios que hoy la marcan `descartada` (`:298`, `:344`, `:373`), siempre con `sl = getattr(self.backend, "scene_live", None)` y solo si `sl is not None` (los backends mínimos de `test_bridge.py` no tienen `scene_live`);
- `app/backend/server.py`: `Backend.apply` (`:289-290`) pasa `actor_orders` (§4.1); las dos rutas de §5; `STATUS["actor_invalid"] = 422`; `send_result` (`:414`) usa `result["http"]` cuando la respuesta lo trae (`result.get("http") or STATUS.get(code, 409)`), sin cambiar `STATUS["expansion_unavailable"] = 422`;
- `app/tests/fake_mod.py`, `app/tests/fake_world.py`, `app/tests/fake_actor_engine.py` (§6);
- nuevos: `app/tests/test_actor_plan.py`, `app/tests/test_actor_live.py`, `DayZSandbox/scripts/3_Game/DSBX_ActorOps.c`;
- `DayZSandbox/scripts/3_Game/DSBX_Peer.c` (miembro `m_ActorOps` junto a `m_SceneOps`, `:176`, `:260`, `:292`, y el despacho de `:1247`) y `DSBX_Messages.c` (`DSBX_Args`, `:34-50`) (§7);
- `app/tests/test_mod_static.py`: `EXPECTED_C_FILES` y `check_m19` (§7).

No se tocan `qa/`, `store.py`, `validate.py`, `profile.py`, `actor_wire.py`, `actor_judge.py`, el esquema, la web ni las pruebas existentes (todas siguen en verde sin editarlas; §9).

## 2. Órdenes de actor [EXACT]

Las tres llevan la marca `f2: 1` (la familia de envolvente de F2, DP-5) y `doc_id`. Unidades como F2: milímetros y miligrados enteros, milisegundos enteros. Solo enteros: nada de `float` ni `bool` donde va un entero.

### 2.1 `actor.apply` (una por actor)

```json
{"f2":1,"doc_id":"<str>","rev":<int>,"hash":"<str>","a_lid":"act-01","a_cls":"SurvivorM_Mirek",
 "a_x_mm":6176000,"a_z_mm":7632000,"a_yaw_mdeg":35000,"a_items":["..."],
 "a_behaviour":"ONCE","a_roam_mm":15000,
 "mk_x_mm":[6181000,6185000],"mk_z_mm":[7635000,7639000],
 "g_emote":["EmotePoint"],"g_at":[1],"g_t_ms":[-1]}
```

- `build_actor_orders(doc, rev, hash_, store_catalog)` devuelve la lista de estos `args`, **en el orden de `entities`**, solo para `kind == "actor"`. Lista vacía si no hay actores.
- **Por qué el prefijo `a_`**: `DSBX_Args` ya tiene `lid`, `x_mm`, `z_mm` y `yaw_mdeg` como **columnas** (`ref array<...>`, `DSBX_Messages.c:42-46`) y `JsonSerializer` solo acepta un tipo por nombre (DP-1). Los escalares del actor llevan nombre propio.
- `a_items` = `store_catalog["wardrobe_items"][wardrobe]`, copiado en su orden.
- `a_x_mm`, `a_z_mm`, marcas, `a_roam_mm`: con `m_to_mm` de `scene_plan`; `a_yaw_mdeg` con `yaw_to_mdeg`.
- Gestos, columnas alineadas con la lista `gestures` del documento (el índice es el `gi` de §2.2 de la parte 1): `g_emote` el nombre; `g_at` = `at - 1` (índice de marca desde 0, como `mark_i`) o `-1` si el gesto va por tiempo; `g_t_ms` = `round(t * 1000)` o `-1` si va por marca. Exactamente uno de los dos es `-1`.
- Claves siempre todas, aunque las listas vayan vacías (DP-2).
- **Lectura** al `done`: una foto §2.3 de la parte 1 con exactamente la fila de ese `a_lid` en `actors` (y `gestures` vacía o con eventos de ese `lid`). Otra cosa es `lectura_no_cumple` (§4.2).
- **Idempotente** en el mod: un `actor.apply` cuyo `a_lid` ya está vivo **de la misma orden** (`order["session"]`, `order["op_id"]`, el `rd-N` que llega por el cable; la reentrega trae el mismo) no crea otro; devuelve su fila. Un `a_lid` vivo creado por otra orden se retira primero y se crea de nuevo.

### 2.2 `actor.reset`

`{"f2":1,"doc_id":"<str>"}`. Retira **todos** los actores que el registro de Sandbox tiene vivos, de cualquier operación. Lectura al `done`: foto §2.3 de los que siguen vivos (lo esperado: `{"actors":[],"gestures":[]}`). Idempotente.

### 2.3 `actor.observe`

`{"f2":1,"doc_id":"<str>"}`. No cambia nada. Lectura al `done`: foto §2.3 de todos los actores vivos del registro, con los eventos de gesto desde su creación.

### 2.4 Rechazos del mod

`rejected` con `reason`: `expansion_unavailable` (no hay motor disponible), `unknown_verb` (sin la marca `f2`), `bad_args` (falta una clave o columnas desalineadas). `error` con `reason` libre (`[a-z_]{1,24}`) para un fallo a medias (por ejemplo una prenda que no se pudo poner).

## 3. Validación con motor [EXACT]

`validate_for_apply(..., actor_engine="none")`. El valor lo pasa `prepare_apply_locked` desde el `hello` del servidor (`bridge.peers["server"]["actor_engine"]`).

- **Paso 1**, sin cambios cuando `actor_engine != "expansion"`: cualquier actor → `expansion_unavailable` (422), una entrada por actor. Las pruebas de hoy (`test_scene_plan.py:335,457`, `test_scene_live.py:998-1013`, `test_f2_live.py:335-340`) no pasan el parámetro y siguen igual.
- **Paso 1b** `actor_invalid` (422, nuevo en `HTTP_STATUS` de `scene_plan.py:58` y en `STATUS` de `server.py:37-48`), solo con `actor_engine == "expansion"`, **antes** del paso 2 (`catalog_pending`). Una entrada por fallo, con su `pointer`, todas las del documento:

| Fallo | `pointer` |
|---|---|
| más de 16 actores (`_MAX_ACTORS = 16`, `actor_wire.py:25`) | `/entities/<i>` del 17.º |
| `id` que no cumple `^act-(0[1-9]|[1-9]\d+)$` o pasa de 10 caracteres | `/entities/<i>/id` |
| `behaviour` fuera de `HOLD`/`ONCE`/`LOOP`/`ROAM`, o `roam` no positivo | `/entities/<i>/behaviour` o `/roam` |
| `cls` fuera de `store_catalog["classes"]["actor"]` | `/entities/<i>/cls` |
| `wardrobe` fuera de `wardrobe_items` | `/entities/<i>/wardrobe` |
| `emote` fuera de `store_catalog["emotes"]` | `/entities/<i>/gestures/<j>/emote` |
| más de 64 marcas o más de 64 gestos | `/entities/<i>/marks` o `/gestures` |
| `ONCE` o `LOOP` sin marcas | `/entities/<i>/marks` |
| un gesto sin `at` ni `t`, o con los dos | `/entities/<i>/gestures/<j>` |
| `at` no entero, `at < 1`, `at` mayor que el número de marcas, o `at` en `HOLD`/`ROAM` | `/entities/<i>/gestures/<j>/at` |
| `t` no numérico o `t < 0` | `/entities/<i>/gestures/<j>/t` |
| una marca fuera de `[0, world_size]` (cerrado, como el paso 4 y `_valid_xz_mm`) | `/entities/<i>/marks/<k>` |
| la orden de §2.1 no cabe: el sondeo `{"ok","now_ms","ops":[orden]}` con `op_id = "rd-999999"` pasa de `WIRE_CAP`, o `_max_str_bytes` de la orden pasa de `STR_CAP` (los dos importados de `bridge.py`, como ya se importa `WIRE_CAP` en `scene_plan.py:41`). **Solo** se mide en un actor que no tenga ningún otro fallo de esta tabla (para no construir la orden con un `wardrobe` que no existe) | `/entities/<i>` |

- **Paso 6** (`plan_too_large`, `scene_plan.py:634-680`): el bucle que llena `lids` y `classes` y llama a `valid_lid` salta las entidades con `kind == "actor"` (su `id` ya lo validó el 1b). Sin motor no llega nunca un actor a este paso, así que no cambia nada para F2.
- Si todo pasa, la respuesta de éxito gana la clave `actor_orders` (la lista de §2.1). `plan`, `expectation` y `envelope` son **los mismos bytes** que daría el documento sin sus actores (`build_plan` ya los filtra; T-V2 lo comprueba).
- **Capacidad perdida entre validar y encolar** (C5): `enqueue_apply_locked` vuelve a mirar el `hello` actual; con `actor_orders` no vacía y `actor_engine != "expansion"` → `expansion_unavailable` (422), sin fila de operación y sin orden. Entre encolar y entregar, la pérdida del servidor ya deja la orden `pendiente` en `fallido` (`bridge.py:316-319` y `:348-351`): 0 creaciones.

## 4. Encadenado en `SceneLive` [EXACT]

`F2_VERBS` pasa a `("scene.apply", "scene.reset", "scene.observe", "actor.apply", "actor.reset", "actor.observe")` para que `is_f2_order` y el camino de resultados de F2 las acepten. Las órdenes de actor son **siempre internas** (`internal=True`, `op_id` `rd-N`) y llevan `order["purpose"]` y, las de etapa, `order["parent_op"]` con el `op_id` de la operación. `_scene_queue_len_locked`, `_pick_order_locked` (`bridge.py:579`), la reconciliación y la compensación **no las ven** (filtran por `scene.apply`/`scene.reset` o por no internas, y eso no cambia).

**`valid_read` y el bridge.** `bridge.py:624` corta con `400` cualquier `done` de una orden F2 cuyo `read` no pase `sl.valid_read`. Para los verbos `actor.*`, `valid_read` devuelve solo `isinstance(read, dict)`; el juicio con `valid_actor_read` va **entero** en `_handle_internal_result_locked` (§4.2, §4.3, §5), para que una foto mala dé su `parcial` y no se quede sin resultado hasta el TTL. Para `scene.*`, `valid_read` no cambia. Las lecturas de actor no llevan `epoch`: no se copia el chequeo `read.get("epoch")` de `scene_live.py:601` (el epoch de la orden ya lo mira `bridge.py:618`).

**Guarda común antes de encolar una orden de actor** (`_actor_engine_ok_locked(order)`): servidor presente y no `lost`, `srv["epoch"] == order["epoch"]` de la `scene.*` que la dispara y `srv["actor_engine"] == "expansion"`. Si no se cumple, no se encola y la operación se cierra en el acto (§4.1, §4.3) con `parcial/conexion_perdida`, `parcial/mundo_reiniciado` o `parcial/expansion_unavailable`, en ese orden de comprobación. Esto cubre el resultado tardío que A8 acepta (`scene_live.py:553-558`) con el servidor ya caído o en otro epoch.

### 4.1 Etapa de actores tras el apply

- Firma: `enqueue_apply_locked(op_id, plan, expectation=None, actor_orders=None)`. Si recibe la respuesta entera de `validate_for_apply` (la rama de `:384` que ya saca `plan` y `expectation`), saca también `actor_orders`. `Backend.apply` (`server.py:289-290`) pasa `actor_orders=res.get("actor_orders")`. La orden guarda `order["actor_orders"]` (copia, lista vacía si no hay).
- Un solo punto de cierre del apply con el predicado cumplido, `_close_apply_ok_locked(order, reason)`, que usan **los dos** caminos: el resultado directo (`on_result_locked`, `reason = None`) y la reconciliación por `scene.observe checkpoint` (`scene_live.py:635-636`, `reason = "reconciliada"`). Con `actor_orders` vacía → `observado/<reason>` como hoy. Si no, la operación **se queda en `aplicado`**, se guarda `reason` para el `observado` final, pasa la guarda común y se encola un `actor.apply` por actor (`purpose = "actor_stage"`, `parent_op`), todos a la vez; `SceneLive` guarda `stage[op_id] = {lid: None}`.
- Un `enqueue_order` que falle al encolar (no debería: §3 ya lo midió) → `parcial/actor_error`.

### 4.2 Juicio de cada `actor.apply`

En `_handle_internal_result_locked`, para `purpose == "actor_stage"`, si la operación padre sigue en `aplicado` (si no, el resultado se acusa y no cambia nada):

| Resultado | Veredicto del actor |
|---|---|
| `done`, `valid_actor_read(read, world_size)`, exactamente una fila y es la de `args["a_lid"]`, `judge_identity({"cls": a_cls, "items": a_items}, fila)` = `PASA` y la fila a < 0,5 m en xz de (`a_x_mm`, `a_z_mm`) | `ok` |
| `done` con cualquier otra cosa | `no_cumple` |
| `rejected` | `rechazado` |
| `error` | `error` |

En cuanto un actor no da `ok`, la operación pasa a `parcial` con `reason` = `actor_no_cumple`, `actor_rechazado` o `actor_error` (el del **primer** actor que falle, por orden de llegada del resultado) y la etapa se cierra: los resultados que lleguen después se acusan y no cambian nada. Cuando todos dan `ok` → `observado` con el `reason` guardado en §4.1 (`None` o `reconciliada`). Nunca `observado` antes de juzgar al último. Todos los cambios de estado de la etapa llevan `origin = "servidor"` salvo los de §4.4 y de la guarda común, que llevan `origin = "backend"`.

Estos tres motivos **no** entran en `TERMINAL_PARCIAL_REASONS` ni en `RESULT_BLOCKING_REASONS`: no hace falta, porque la reconciliación solo mira órdenes no internas en `parcial` (`_is_order_unresolved_locked`, `scene_live.py:668-682`) y la `scene.apply` de esa operación ya está `terminal`. T-S7 lo comprueba con un `state.read` posterior.

### 4.3 `actor.reset` tras el reset

- Un solo punto de cierre del reset de API (no el de compensación), `_close_reset_locked(order, st, rsn)`, que usan el resultado directo (`on_result_locked`) y la reconciliación por `scene.last` (`scene_live.py:868-872`, con `rsn = "reconciliada"` si `st == "observado"`). Con `actor_engine == "expansion"` en el `hello` actual: `(st, rsn)` se guarda en `order["scene_verdict"]`, la operación pasa a `aplicado` (como hoy antes del predicado), pasa la guarda común y se encola un `actor.reset` (`purpose = "actor_reset"`, `parent_op`).
- Si la guarda común falla o `enqueue_order` falla: la operación toma la regla de fallo de abajo (con el motivo de la guarda en vez de `actores_vivos` si `scene_verdict` era `observado`).
- Su resultado: `done` con `valid_actor_read` y `actors == []` → la operación toma `scene_verdict` tal cual (`observado`, o el `parcial`/`fallido` de la escena con su motivo). Cualquier otra cosa (incluida una foto que no pase `valid_actor_read`) → si `scene_verdict` era `observado`, `parcial/actores_vivos`; si no, se queda `scene_verdict` (el motivo de la escena manda).
- Con `actor_engine == "none"` no se encola nada y el reset es el de hoy.

### 4.4 Una orden de la etapa que se pierde

`bridge.py`, en los tres sitios donde una orden interna pasa a `descartada` (pérdida de conexión, cambio de conexión y TTL), llama a `self.backend.scene_live.on_internal_dropped_locked(order, reason)` con `reason` = `conexion_perdida`, `mundo_reiniciado` o `sin_resultado` (el mismo que hoy pondría a una orden de API en ese sitio). `sin_resultado` vale para el TTL tanto si la interna estaba `pendiente` como `ejecutando` (`bridge.py:378-385`). `SceneLive`, con `origin = "backend"`: si `order["purpose"]` es `actor_stage` y la operación padre sigue en `aplicado` → `parcial/<reason>`; si es `actor_reset`, la regla de fallo de §4.3 con `<reason>` en lugar de `actores_vivos` (un `scene_verdict` que no era `observado` se queda). Si es `actor_observe` (§5), se libera el hueco. Cualquier otra orden interna: nada (lo de hoy).

## 5. Lectura de actores por la API [EXACT]

Igual que `scene.observe now` (`request_observe_locked`, `observation_locked`), con su propio hueco:
- `POST /api/actors/observe` `{"doc_id"}` → `{"ok":true,"read_id":"rd-N"}`; una sola en vuelo (la segunda devuelve el `read_id` de la primera). `actor_engine != "expansion"` → `expansion_unavailable` con `"http": 409` en la respuesta (el documento no tiene la culpa; `send_result` lo respeta, §1); `doc_changed` (409) como en `/api/observe`.
- `GET /api/actors/observation` → **siempre** `200` `{"ok":true,"observation":<foto §2.3 o null>,"age_ms":<int o null>}`, haya motor o no. Solo se guarda una lectura que pase `valid_actor_read` (en `_handle_internal_result_locked`, `purpose = "actor_observe"`); una inválida se descarta y la anterior se queda.
- Las dos son de lectura para cualquier cliente (como `/api/observe` y `/api/observation`).

## 6. Mod falso y mundo falso con motor [DESIGN]

- `FakeMod(..., actor_engine="none")`: el valor sale en el `hello` (`fake_mod.py:292`). `_execute` manda `actor.apply`, `actor.reset` y `actor.observe` con la marca `f2` a `_execute_world`; sin la marca, `unknown_verb` como hoy.
- `fake_world.py`: `actor_apply(order)`, `actor_reset(order)`, `actor_observe(order)`, que devuelven `(status, reason, read)` como los otros verbos. Con `actor_engine == "none"` en el mod, los tres → `rejected/expansion_unavailable` (lo decide `fake_mod`, el mundo no lo sabe). El mundo tiene un `FakeActorEngine` (atributo `actors`, reloj propio `FakeClock`) que las pruebas usan para inyectar los fallos de la tabla de §5 de la parte 1.
- `FakeActorEngine` gana lo mínimo:
  - firma `spawn(lid, cls, x, z, yaw, wardrobe=None, *, items=None)`: con `items`, usa esa lista; sin `items`, busca `wardrobe` como hoy; sin los dos → `ValueError`;
  - `spawn_count` (entero): cuántas veces se creó un actor de verdad (no sube en la reentrega idempotente);
  - `despawn(lid)`: retira el actor y sus eventos de gesto (para que la foto siga pasando `valid_actor_read`); un `lid` que no está → no hace nada;
  - `schedule_gestures(lid, emotes, at, t_ms)`: guarda los gestos del cable; uno con `t_ms >= 0` se pide (`request_gesture`) en el primer `step` en que han pasado `t_ms` desde el `spawn`; uno con `at >= 0`, en el primer `step` en que el actor queda `arrived` en esa marca;
  - fallos nuevos: `displace_spawn(lid, dx_m, dz_m)` (crea el actor desplazado), `reject_apply(lid, reason)` (el `actor.apply` de ese `lid` → `rejected/reason`), `error_apply(lid, reason)` (crea el actor y devuelve `error/reason`), `despawn_fails(lid)` (el `actor.reset` lo deja vivo y devuelve `done` con su fila).
  - **Fallos armados antes de crear**: los fallos de identidad de la parte 1 (`wardrobe_drop(lid, cls)`, `wardrobe_add`, `cls_swap`) y `displace_spawn` se pueden llamar con un `lid` que aún no existe: quedan armados y se aplican justo al crearlo, antes de la foto.
- `FakeWorld`: atributo `actors` (`FakeActorEngine` con el catálogo completo de `fixtures/catalog-m1.json`, `wardrobe_items` incluido); `restart()` (`fake_world.py:2338-2375`) lo cambia por uno nuevo vacío.
- `actor_apply` en el mundo: idempotencia por `(order["session"], order["op_id"])` (§2.1), `spawn` + `set_marks` + `schedule_gestures` y devuelve la foto filtrada a `a_lid` **en `actors` y en `gestures`**. `step` lo avanza la prueba cuando lo necesita; el apply no espera a que el actor ande.

## 7. Despacho en el núcleo del mod [EXACT]

- `DSBX_Messages.c`, `DSBX_Args`: los campos tipados nuevos (DP-1), **uno por línea** como los de hoy: `string a_lid;`, `string a_cls;`, `string a_behaviour;`, `int a_x_mm;`, `int a_z_mm;`, `int a_yaw_mdeg;`, `int a_roam_mm;`, `ref array<string> a_items;`, `ref array<string> g_emote;`, `ref array<int> mk_x_mm;`, `ref array<int> mk_z_mm;`, `ref array<int> g_at;`, `ref array<int> g_t_ms;`. Ninguno choca con los de hoy (`:34-50`).
- `DSBX_Peer.c`: `ref DSBX_ActorOps m_ActorOps;` declarado e instanciado junto a `m_SceneOps` (`:176`, `:260`, `:292`); en `:1247`, con `args.f2 == 1`, los tres verbos `actor.*` van a `m_ActorOps.StartOrder(this, entry)`; el resto como hoy.
- Fichero nuevo `DSBX_ActorOps.c` (`class DSBX_ActorOps : Managed`): `StartOrder` toma `DSBX_ActorEngineRegistry.Get()`; si `!IsAvailable()` → `rejected/expansion_unavailable`. Si está: convención de la interfaz de la parte 1, **`""` es éxito** y cualquier otra cadena es el código de fallo (→ `error/<código>`); `Spawn` + `SetMarks` + un `RequestGesture` por gesto (apply), `Despawn` de cada actor del registro de Sandbox (reset) o `State` (observe), y arma la foto §2.3 con `gestures` siempre `[]` en el núcleo (los eventos de gesto y el disparo por `g_at`/`g_t_ms` son del adaptador, `[verify S3]`). Con el motor base de la parte 1 este segundo camino no corre nunca en este repo: es `[verify]` hasta que haya adaptador.
- Sin `eAI`, `Expansion` ni `EXPANSIONMODAI` en el código sin comentarios (como M18). Respeta M17 (`test_mod_static.py:1070-1102`): nunca dos llamadas a funciones `string` del producto en la misma expresión.
- **M19** (`test_mod_static.py`): `DSBX_ActorOps.c` en `EXPECTED_C_FILES`; `DSBX_Peer.c` despacha los tres verbos solo bajo `f2 == 1`; `DSBX_ActorOps.c` llama a `IsAvailable()` y rechaza con `expansion_unavailable` cuando da falso; `DSBX_Args` tiene los campos de arriba con su tipo. La búsqueda de símbolos de Expansion **no** se duplica en M19 (ya la hace M18 sobre todos los ficheros), para que B15 tumbe solo M19.

## 8. Lo que no cambia para nadie

- Sin motor (`actor_engine = "none"`, que es lo único que hay hoy fuera de las pruebas): mismos códigos, mismas órdenes, mismos estados. La única diferencia visible es que existen `/api/actors/observe` (que responde `expansion_unavailable`, 409) y `/api/actors/observation` (que responde `200` con `observation: null`).
- Con motor y sin actores en el documento: mismo camino que hoy **más** un `actor.reset` tras cada `scene.reset` cumplido.

## 9. Pruebas (R26)

Cada prueba con su positiva y su negativa. Los fixtures son `fixtures/escena-basica-cine.json` (2 actores, 33 raíces) y su copia sin actores, construida en la prueba.

### 9.1 `app/tests/test_actor_plan.py` (T-V)

- **T-V1** sin motor: la básica → `expansion_unavailable` con 2 entradas (`/entities/0`, `/entities/1`); igual que hoy.
- **T-V2** con motor: la básica → `ok`; `actor_orders` tiene 2 entradas y la de `act-01` es **igual, clave a clave, al JSON literal de §2.1** con los `items` de `partisano`; `plan`, `expectation` y `envelope` iguales (`==`) a los de la copia sin actores.
- **T-V3** una negativa por fila de la tabla de §3, cada una con su `pointer` exacto y nada más en `errors`; más un documento con `wardrobe` desconocido **y** una cadena enorme en el mismo actor → una sola entrada (`/entities/<i>/wardrobe`), sin excepción.
- **T-V2b** con motor, la básica no da `plan_too_large` en `/entities/0/id` (paso 6 salta los actores).
- **T-V4** precedencia: un actor inválido **y** sin catálogo del mundo → `actor_invalid` (1b va antes de 2). Sin motor, el mismo documento → `expansion_unavailable`.
- **T-V5** gesto por tiempo `t = 1.5` → `g_t_ms = [1500]`, `g_at = [-1]`; por marca `at = 2` → `g_at = [1]`, `g_t_ms = [-1]`.

### 9.2 `app/tests/test_actor_live.py` (T-S, con `FakeMod` + `FakeWorld`, como `test_f2_live.py`)

- **T-S1** feliz: motor `expansion`, apply de la básica → la secuencia de `op.state` de la operación es exactamente `pendiente, ejecutando, aplicado, observado`; un solo `observado` y llega **después** de los dos resultados de `actor.apply`; el motor falso tiene `act-01` y `act-02` con sus prendas.
- **T-S2** `reject_apply("act-02", "combat")` → `parcial/actor_rechazado`, ningún `observado`.
- **T-S3** `wardrobe_drop("act-01", "TaloonBag_Blue")` armado antes del apply (o la prenda que toque del preset `partisano`) → `parcial/actor_no_cumple`.
- **T-S3b** `displace_spawn("act-01", 1, 0)` → `parcial/actor_no_cumple`; con `0.3` → `observado`.
- **T-S4** `error_apply("act-01", "prenda")` → `parcial/actor_error`; el resultado de `act-02` que llega después no cambia el estado.
- **T-S5** C5: validar con `hello` `expansion`, cambiar el `hello` a `none` y encolar → `expansion_unavailable`, sin operación nueva y 0 creaciones en el mundo.
- **T-S5b** resultado `done` tardío del `scene.apply` llegado con el servidor ya `lost` (A8) → no se encola ningún `actor.apply` y la operación queda `parcial/conexion_perdida`.
- **T-S6** se pierde la conexión con un `actor.apply` entregado y sin resultado → `parcial/conexion_perdida`; su resultado tardío no cambia nada.
- **T-S6b** TTL de un `actor.apply` sin resultado → `parcial/sin_resultado`.
- **T-S6c** reconciliación: `scene.apply` con actores cuyo resultado se pierde (`parcial/sin_resultado`), y la reconexión en el mismo epoch lo reconcilia por checkpoint → arranca la etapa y acaba `observado/reconciliada` con 2 actores en el motor falso. Lo mismo para el reset por `scene.last`: acaba con 0 actores.
- **T-S7** tras T-S2, un `state.read` del mismo mundo no cambia la operación (no hay reconciliación de la etapa).
- **T-S8** reset con motor tras T-S1 → la operación del reset termina `observado`, el motor falso no tiene actores y el mundo tiene 0 propios.
- **T-S9** `despawn_fails("act-01")` → el reset termina `parcial/actores_vivos`.
- **T-S10** reset con motor cuya escena da `parcial/contenido_ajeno` y `despawn_fails` → se queda `parcial/contenido_ajeno`; lo mismo si se pierde la conexión durante el `actor.reset`.
- **T-S11** directo sobre `world.actor_apply` (sin la caché de `FakeMod`, `fake_mod.py:377-391`): la misma orden dos veces → `spawn_count` no sube; la misma `a_lid` con otro `op_id` → `spawn_count` sube 1 y sigue habiendo un actor por `lid`.
- **T-S12** con motor, documento sin actores → misma secuencia de `op.state` que sin motor; tras el reset se encola exactamente un `actor.reset`.
- **T-S13** `/api/actors/observe` con motor → `read_id`; tras el resultado, `/api/actors/observation` da una foto que pasa `valid_actor_read` con 2 filas. Sin motor → `expansion_unavailable` 409. Una lectura inválida del mod no pisa la anterior y no se corta en el bridge (el mod recibe `200`). `GET /api/actors/observation` sin motor → `200` con `null`.
- **T-S14** un `done` de `actor.apply` con una foto que no pasa `valid_actor_read` → el bridge responde `200` y la operación queda `parcial/actor_no_cumple` (no `sin_resultado`).

### 9.3 Mod falso y mod real (T-M, T-M19)

- **T-M1** el `hello` lleva el `actor_engine` configurado; los tres verbos con motor `none` → `rejected/expansion_unavailable`; sin marca `f2` → `unknown_verb`.
- **T-M2** `FakeActorEngine.despawn` deja una foto válida; `spawn(items=...)` usa esas prendas; los tres fallos nuevos hacen lo que dice §6.
- **T-M19** la comprobación estática de §7, con una mutación que la tumba sola (`_assert_only_rule_fails`).

### 9.4 Regresión

`python3 -m unittest discover -s app/tests -t app` (629 + las nuevas) y `qa/tests` en verde **sin editar ninguna prueba existente**. `git diff --stat` no toca `qa/` ni los briefs de F2. **T-R**: las pruebas existentes de `test_scene_live.py`, `test_f2_live.py`, `test_bridge.py` y `qa/tests` son la prueba de que sin motor nada cambia.

## 10. Antitautología (R26)

Mutaciones que tienen que morir, cada una con la prueba que la mata:

| # | Mutación | La mata |
|---|---|---|
| B1 | el paso 1 rechaza los actores aunque haya motor (no mira `actor_engine`) | T-V2 |
| B1b | el paso 1 no rechaza nunca (sin motor, los actores pasan) | T-V1 |
| B2 | 1b después del paso 2 | T-V4 |
| B3 | `g_at = at` (sin restar 1) | T-V2, T-V5 |
| B4 | `actor_orders` sin `items` del preset (lista vacía) | T-V2 |
| B4b | el paso 6 no salta los actores | T-V2b |
| B4c | `Backend.apply` no pasa `actor_orders` | T-S1 |
| B5 | `observado` al llegar el primer `actor.apply` `ok` | T-S1 |
| B6 | `observado` sin etapa (se ignora `actor_orders`) | T-S1 |
| B7 | `no_cumple` sin mirar `judge_identity` | T-S3 |
| B8 | sin la segunda mirada del `hello` en `enqueue_apply_locked` | T-S5 |
| B9 | `on_internal_dropped_locked` no hace nada | T-S6, T-S6b |
| B9b | la reconciliación por checkpoint da `observado` sin etapa | T-S6c |
| B9c | sin la guarda común (no mira `lost`) | T-S5b |
| B9d | `valid_read` valida `valid_actor_read` (el bridge corta la foto mala) | T-S14 |
| B10 | el reset con motor no encola `actor.reset` | T-S8, T-S12 |
| B11 | `actor.reset` con actores vivos da `observado` | T-S9 |
| B12 | `actores_vivos` pisa el motivo de la escena | T-S10 |
| B13 | el mundo falso crea otro actor en la reentrega | T-S11 |
| B14 | `/api/actors/observation` guarda una lectura inválida | T-S13 |
| B15 | `DSBX_ActorOps.c` no mira `IsAvailable()` | T-M19 |
| B16 | tolerancia de pose 5 m en vez de 0,5 m | T-S3b |
| B17 | `/api/actors/observe` sin motor responde con el 422 de `STATUS` | T-S13 |

## 11. Aceptación

- Los dos `unittest discover` de §9.4 en verde.
- Las 23 mutaciones de §10 mueren.
- `git diff --stat` solo toca los ficheros de §1.

## 12. Reparto

- Revisión del brief: **Gemini Neon** (agy), una ronda.
- Implementación, por dependencias:
  1. en paralelo: **lane A Grok** (`grok-4.6`): §2.1 y §3 con T-V (`scene_plan.py`, `test_actor_plan.py`); **lane B Gemini Argon**: §6 y §7 con T-M y T-M19 (`fake_mod.py`, `fake_world.py`, `fake_actor_engine.py`, el mod, `test_mod_static.py`);
  2. después, sobre las dos juntas: **lane C Grok**: §4 y §5 con T-S (`scene_live.py`, `bridge.py`, `server.py`, `test_actor_live.py`).
- Fallback: el orquestador (Claude) escribe lo que una lane no entregue.
- Gate y mutaciones: el orquestador, en la nube.

## 13. Fuera de alcance, riesgos y `[verify]`

- `[verify S-perf]`: si `actor.observe` por el bridge aguanta 10 Hz con 2 actores. Si no, el muestreo de C2-C4 pasa a una ventana en el mod y esta ruta queda para leer una vez.
- `[verify S3]`: que el adaptador pueda pedir los gestos por marca al llegar (`g_at`) y que su `State` dé la fila de §2.1 de la parte 1.
- Riesgo: la etapa de actores deja la operación en `aplicado` mientras los actores se crean. La web de hoy lo muestra como «Aplicado» y no como terminado, que es lo correcto.
- Riesgo: sin compensación automática, un apply con un actor rechazado deja el decorado y los otros actores puestos (`parcial`, visible). Es lo que pide C1 («parcial con la prenda nombrada»); el reset lo limpia todo.
- Fuera: adaptador, muestreo en partida, `m1_gate.py phase F3`, la web.

## 14. Cambios por la revisión

| Versión | Cambio |
|---|---|
| v0.1 | Borrador del 26-nov por la noche, para la ronda de Neon. |
| v0.2 | Ronda de Gemini Neon (`gemini-4-neon-high`, 26-nov 02:35-02:44 UTC, APTO CON CAMBIOS, 8 BLOQ, 3 MAY, 1 MEN; informe en la carpeta del proyecto `dayz-sandbox/f3off2/`), todo aplicado: `valid_read` deja pasar las fotos de actor y el juicio va en `SceneLive` (H01); `enqueue_apply_locked` y `Backend.apply` pasan `actor_orders` (H02); el paso 6 salta los actores y el 1b valida su `id` (H03); un solo cierre del apply y del reset, también para la reconciliación (H04); `expansion_unavailable` 409 por `result["http"]` sin tocar el 422 de F2, y `GET /api/actors/observation` siempre 200 (H05); `getattr` para `scene_live` en el bridge (H06); guarda común de servidor, epoch y motor, fallo al encolar y `scene_verdict` que manda también en la pérdida (H07); B1 partida en B1/B1b, `spawn_count` y T-S11 sin la caché, T-S3b con `displace_spawn` y fallos armados antes de crear (H08); `DSBX_ActorOps`: `""` es éxito, `gestures` vacío en el núcleo, `m_ActorOps` en `DSBX_Peer`, un campo por línea, M17 y B15 solo para M19 (H09); el 1b completo (`at < 1`, `t < 0`, `at` y `t` a la vez, `behaviour`, intervalo cerrado, sondeo con `rd-999999` y `STR_CAP`, sin medir un actor ya inválido) (H10); el mundo falso filtra también los gestos, `spawn` con `items`, `schedule_gestures`, `restart()` y el `op_id` del cable (H11); citas, T-S5 sin hora ni clima, T-R y la nota del `epoch` (H12). Mutaciones nuevas B1b, B4b, B4c, B9b-B9d y B17. |
| v0.2a | Implementado por Claude el 26-nov por la noche, sin delegar: el paquete para las lanes eran unos 30 KB de contexto y escribirlo costaba menos que mandarlo y revisarlo. Desvío del §1: `POST /api/actors/observe` usa `res["http"]` en su propia ruta y `send_result` no cambia, para que otros códigos (como `bad_plan`) conserven su estado. `[verify]`: los pasos 3 (`unknown_class`) y 4 (`out_of_map`) siguen mirando también los actores, así que el catálogo del mundo tiene que traer las clases de superviviente; lo confirma S3. Mutantes del §10 en `dayz-sandbox/f3off2/mutants.py`. |
