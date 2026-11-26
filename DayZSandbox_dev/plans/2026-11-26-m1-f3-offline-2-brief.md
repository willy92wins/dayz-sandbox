# F3 sin juego (parte 2): mandar los actores al mod, observarlos y retirarlos con el reset

2026-11-26 · tarea **F3-offline-2**, sobre F3-offline-1 (`39c972e`) · spec de implementación (R25) de la parte de F3 del [plan de M1 v2](2026-10-26-m1-cine-v2.md) (§3 F3, decisiones #5, #12-#15 y #29) que no necesita partida · contrato: `product-spec.md` C1, C5 y el cierre de A2-A4 con actores (CX-01) · v0.1, para la ronda de Gemini Neon.

**Por qué ahora.** La parte 1 fijó qué devuelve el mod de un actor (§2 de su brief) y cómo se juzga. Falta el camino de ida: que una escena con actores, con un motor de actores presente, llegue al mod, se compruebe y se pueda retirar. Igual que la parte 1, **nada de esto depende de lo que mida S3**: el motor real (el adaptador de Expansion) sigue fuera; aquí el único motor «disponible» es el falso de las pruebas.

**Regla que manda sobre todo el brief.** El contrato F2 v1.3.16 está **congelado** (`plans/2026-11-15-m1-f2-partida-brief.md`) y su oráculo (`qa/f2p_*`) se comprueba byte a byte. Por eso los actores **no entran en `scene.apply` ni en `scene.reset`**: van en una familia de verbos propia (`actor.*`) que `SceneLive` encadena **después** de un `scene.apply` observado y **después** de un `scene.reset` cumplido. Una escena sin actores, o un servidor con `actor_engine = "none"`, recorre exactamente el camino de hoy, orden a orden y estado a estado (§9, T-R).

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
- `app/backend/scene_plan.py`: `validate_for_apply` gana el parámetro `actor_engine="none"` y el paso 1b (§3); función nueva `build_actor_orders` (§2.1);
- `app/backend/scene_live.py`: §4 y §5;
- `app/backend/bridge.py`: el aviso a `SceneLive` cuando se descarta una orden interna (§4.4), en los tres sitios que hoy la marcan `descartada` (`:298`, `:344`, `:373`);
- `app/backend/server.py`: las dos rutas de §5 y su fila en `STATUS` si hace falta un código nuevo (§3);
- `app/tests/fake_mod.py`, `app/tests/fake_world.py`, `app/tests/fake_actor_engine.py` (§6);
- nuevos: `app/tests/test_actor_plan.py`, `app/tests/test_actor_live.py`, `DayZSandbox/scripts/3_Game/DSBX_ActorOps.c`;
- `DayZSandbox/scripts/3_Game/DSBX_Peer.c` (`:1247`), `DSBX_SceneOps.c` (nada) y `DSBX_Messages.c` (`DSBX_Args`, `:34-50`) (§7);
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
- **Idempotente** en el mod: un `actor.apply` cuyo `lid` ya está vivo **de la misma orden** (`session`, `op_id` de la operación) no crea otro; devuelve su fila. Un `lid` vivo de otra operación se retira primero y se crea de nuevo.

### 2.2 `actor.reset`

`{"f2":1,"doc_id":"<str>"}`. Retira **todos** los actores que el registro de Sandbox tiene vivos, de cualquier operación. Lectura al `done`: foto §2.3 de los que siguen vivos (lo esperado: `{"actors":[],"gestures":[]}`). Idempotente.

### 2.3 `actor.observe`

`{"f2":1,"doc_id":"<str>"}`. No cambia nada. Lectura al `done`: foto §2.3 de todos los actores vivos del registro, con los eventos de gesto desde su creación.

### 2.4 Rechazos del mod

`rejected` con `reason`: `expansion_unavailable` (no hay motor disponible), `unknown_verb` (sin la marca `f2`), `bad_args` (falta una clave o columnas desalineadas). `error` con `reason` libre (`[a-z_]{1,24}`) para un fallo a medias (por ejemplo una prenda que no se pudo poner).

## 3. Validación con motor [EXACT]

`validate_for_apply(..., actor_engine="none")`. El valor lo pasa `prepare_apply_locked` desde el `hello` del servidor (`bridge.peers["server"]["actor_engine"]`).

- **Paso 1**, sin cambios cuando `actor_engine != "expansion"`: cualquier actor → `expansion_unavailable` (422), una entrada por actor. Las pruebas de hoy (`test_scene_plan.py:335,457`, `test_scene_live.py:998-1013`, `test_f2_live.py:335-340`) no pasan el parámetro y siguen igual.
- **Paso 1b** `actor_invalid` (422, nuevo en `STATUS` de `scene_plan.py:59` y `server.py:46`), solo con `actor_engine == "expansion"`, **antes** del paso 2 (`catalog_pending`). Una entrada por fallo, con su `pointer`, todas las del documento:

| Fallo | `pointer` |
|---|---|
| más de 16 actores (`_MAX_ACTORS` de `actor_wire`) | `/entities/<i>` del 17.º |
| `cls` fuera de `store_catalog["classes"]["actor"]` | `/entities/<i>/cls` |
| `wardrobe` fuera de `wardrobe_items` | `/entities/<i>/wardrobe` |
| `emote` fuera de `store_catalog["emotes"]` | `/entities/<i>/gestures/<j>/emote` |
| más de 64 marcas o más de 64 gestos | `/entities/<i>/marks` o `/gestures` |
| `ONCE` o `LOOP` sin marcas | `/entities/<i>/marks` |
| `at` mayor que el número de marcas, o `at` en `HOLD`/`ROAM` | `/entities/<i>/gestures/<j>/at` |
| una marca fuera de `[0, world_size)` | `/entities/<i>/marks/<k>` |
| la orden de §2.1 no cabe: largo del sondeo > `WIRE_CAP` o una cadena > `STR_CAP`, medido como en `:697` | `/entities/<i>` |

- Si todo pasa, la respuesta de éxito gana la clave `actor_orders` (la lista de §2.1). `plan`, `expectation` y `envelope` son **los mismos bytes** que daría el documento sin sus actores (`build_plan` ya los filtra; T-V2 lo comprueba).
- **Capacidad perdida entre validar y encolar** (C5): `enqueue_apply_locked` vuelve a mirar el `hello` actual; con `actor_orders` no vacía y `actor_engine != "expansion"` → `expansion_unavailable` (422), sin fila de operación y sin orden. Entre encolar y entregar, la pérdida del servidor ya deja la orden `fallido` (`bridge.py:318-322`): 0 creaciones.

## 4. Encadenado en `SceneLive` [EXACT]

`F2_VERBS` pasa a `("scene.apply", "scene.reset", "scene.observe", "actor.apply", "actor.reset", "actor.observe")` para que `is_f2_order` y el camino de resultados de F2 las acepten. Las órdenes de actor son **siempre internas** (`internal=True`, `op_id` `rd-N`) y llevan `order["purpose"]` y, las de etapa, `order["parent_op"]` con el `op_id` de la operación. `_scene_queue_len_locked`, `_pick_order_locked` (`bridge.py:579`), la reconciliación y la compensación **no las ven** (filtran por `scene.apply`/`scene.reset` o por no internas, y eso no cambia).

### 4.1 Etapa de actores tras el apply

- `enqueue_apply_locked` guarda `order["actor_orders"]` (copia).
- En `on_result_locked`, rama `done` de `scene.apply`, con el predicado cumplido: si `order["actor_orders"]` está vacía o no existe → `observado` como hoy. Si no, la operación **se queda en `aplicado`** y se encola un `actor.apply` por actor (`purpose = "actor_stage"`, `parent_op`), todos a la vez; `SceneLive` guarda `stage[op_id] = {lid: None}`.
- Un `wire_cap_exceeded` al encolar (no debería pasar: §3 ya lo midió) → `parcial/actor_error`.

### 4.2 Juicio de cada `actor.apply`

En `_handle_internal_result_locked`, para `purpose == "actor_stage"`, si la operación padre sigue en `aplicado` (si no, el resultado se acusa y no cambia nada):

| Resultado | Veredicto del actor |
|---|---|
| `done`, `valid_actor_read(read, world_size)`, exactamente una fila y es la de `args["a_lid"]`, `judge_identity({"cls": a_cls, "items": a_items}, fila)` = `PASA` y la fila a < 0,5 m en xz de (`a_x_mm`, `a_z_mm`) | `ok` |
| `done` con cualquier otra cosa | `no_cumple` |
| `rejected` | `rechazado` |
| `error` | `error` |

En cuanto un actor no da `ok`, la operación pasa a `parcial` con `reason` = `actor_no_cumple`, `actor_rechazado` o `actor_error` (el del **primer** actor que falle, por orden de llegada del resultado) y la etapa se cierra: los resultados que lleguen después se acusan y no cambian nada. Cuando todos dan `ok` → `observado`. Nunca `observado` antes de juzgar al último.

Estos tres motivos **no** entran en `TERMINAL_PARCIAL_REASONS` ni en `RESULT_BLOCKING_REASONS`: no hace falta, porque la reconciliación solo mira órdenes no internas en `parcial` (`_is_order_unresolved_locked`, `scene_live.py:668-682`) y la `scene.apply` de esa operación ya está `terminal`. T-S7 lo comprueba con un `state.read` posterior.

### 4.3 `actor.reset` tras el reset

- En la rama `done` de `scene.reset` de API (no la de compensación), con `actor_engine == "expansion"` en el `hello` actual: el veredicto de `_reset_predicate` se guarda en `order["scene_verdict"]`, la operación pasa a `aplicado` (como hoy antes del predicado) y se encola un `actor.reset` (`purpose = "actor_reset"`, `parent_op`).
- Su resultado: `done` con `valid_actor_read` y `actors == []` → la operación toma `scene_verdict` tal cual (`observado`, o el `parcial`/`fallido` de la escena con su motivo). Cualquier otra cosa → si `scene_verdict` era `observado`, `parcial/actores_vivos`; si no, se queda `scene_verdict` (el motivo de la escena manda).
- Con `actor_engine == "none"` no se encola nada y el reset es el de hoy.

### 4.4 Una orden de la etapa que se pierde

`bridge.py`, en los tres sitios donde una orden interna pasa a `descartada` (pérdida de conexión, cambio de conexión y TTL), llama a `self.backend.scene_live.on_internal_dropped_locked(order, reason)` con `reason` = `conexion_perdida`, `mundo_reiniciado` o `sin_resultado` (el mismo que hoy pondría a una orden de API en ese sitio). `SceneLive`: si `order["purpose"]` es `actor_stage` o `actor_reset` y la operación padre sigue en `aplicado` → `parcial/<reason>`. Cualquier otra orden interna: nada (lo de hoy).

## 5. Lectura de actores por la API [EXACT]

Igual que `scene.observe now` (`request_observe_locked`, `observation_locked`), con su propio hueco:
- `POST /api/actors/observe` `{"doc_id"}` → `{"ok":true,"read_id":"rd-N"}`; una sola en vuelo (la segunda devuelve el `read_id` de la primera). `actor_engine != "expansion"` → `expansion_unavailable` (409 aquí: el documento no tiene la culpa); `doc_changed` (409) como en `/api/observe`.
- `GET /api/actors/observation` → `{"ok":true,"observation":<foto §2.3 o null>,"age_ms":<int o null>}`. Solo se guarda una lectura que pase `valid_actor_read`; una inválida se descarta y la anterior se queda.
- Las dos son de lectura para cualquier cliente (como `/api/observe` y `/api/observation`).

## 6. Mod falso y mundo falso con motor [DESIGN]

- `FakeMod(..., actor_engine="none")`: el valor sale en el `hello` (`fake_mod.py:292`). `_execute` manda `actor.apply`, `actor.reset` y `actor.observe` con la marca `f2` a `_execute_world`; sin la marca, `unknown_verb` como hoy.
- `fake_world.py`: `actor_apply(order)`, `actor_reset(order)`, `actor_observe(order)`, que devuelven `(status, reason, read)` como los otros verbos. Con `actor_engine == "none"` en el mod, los tres → `rejected/expansion_unavailable` (lo decide `fake_mod`, el mundo no lo sabe). El mundo tiene un `FakeActorEngine` (atributo `actors`, reloj propio `FakeClock`) que las pruebas usan para inyectar los fallos de la tabla de §5 de la parte 1.
- `FakeActorEngine` gana lo mínimo:
  - `spawn(..., items=None)`: con `items`, usa esa lista en vez de buscar `wardrobe` (el cable trae prendas, no el nombre del preset);
  - `despawn(lid)`: retira el actor y sus eventos de gesto (para que la foto siga pasando `valid_actor_read`); un `lid` que no está → no hace nada;
  - `owner(lid)` / registro `(session, op_id)` por actor para la idempotencia de §2.1;
  - fallos nuevos: `reject_apply(lid, reason)` (el `actor.apply` de ese `lid` → `rejected/reason`), `error_apply(lid, reason)` (crea el actor y devuelve `error/reason`), `despawn_fails(lid)` (el `actor.reset` lo deja vivo y devuelve `done` con su fila).
- `actor_apply` en el mundo: `spawn` + `set_marks` + `request_gesture` por cada gesto por tiempo (los de marca los pide el motor al llegar; en el falso, al pasar a `arrived` en esa marca) y devuelve la foto con la fila de ese `lid`. `step` lo avanza la prueba cuando lo necesita; el apply no espera a que el actor ande.

## 7. Despacho en el núcleo del mod [EXACT]

- `DSBX_Messages.c`, `DSBX_Args`: los campos tipados nuevos (DP-1): `string a_lid, a_cls, a_behaviour; int a_x_mm, a_z_mm, a_yaw_mdeg, a_roam_mm; ref array<string> a_items, g_emote; ref array<int> mk_x_mm, mk_z_mm, g_at, g_t_ms;`. Ninguno choca con los de hoy (`:34-50`).
- `DSBX_Peer.c:1247`: con `args.f2 == 1`, los tres verbos `actor.*` van a `m_ActorOps.StartOrder(...)`; el resto como hoy.
- Fichero nuevo `DSBX_ActorOps.c` (`class DSBX_ActorOps : Managed`): `StartOrder` toma `DSBX_ActorEngineRegistry.Get()`; si `!IsAvailable()` → `rejected/expansion_unavailable`. Si está, llama a `Spawn`/`SetMarks`/`RequestGesture` (apply), `Despawn` (reset) o `State` (observe) y arma la foto §2.3. Con el motor base de la parte 1 el segundo camino no corre nunca en este repo: es `[verify]` hasta que haya adaptador.
- Sin `eAI`, `Expansion` ni `EXPANSIONMODAI` en el código sin comentarios (como M18).
- **M19** (`test_mod_static.py`): `DSBX_ActorOps.c` en `EXPECTED_C_FILES`; `DSBX_Peer.c` despacha los tres verbos solo bajo `f2 == 1`; `DSBX_ActorOps.c` no tiene símbolos de Expansion y rechaza con `expansion_unavailable` cuando el motor no está disponible; `DSBX_Args` tiene los campos de arriba con su tipo.

## 8. Lo que no cambia para nadie

- Sin motor (`actor_engine = "none"`, que es lo único que hay hoy fuera de las pruebas): mismos códigos, mismas órdenes, mismos estados. La única diferencia visible es que existen `/api/actors/observe` y `/api/actors/observation` (que responden `expansion_unavailable`).
- Con motor y sin actores en el documento: mismo camino que hoy **más** un `actor.reset` tras cada `scene.reset` cumplido.

## 9. Pruebas (R26)

Cada prueba con su positiva y su negativa. Los fixtures son `fixtures/escena-basica-cine.json` (2 actores, 33 raíces) y su copia sin actores, construida en la prueba.

### 9.1 `app/tests/test_actor_plan.py` (T-V)

- **T-V1** sin motor: la básica → `expansion_unavailable` con 2 entradas (`/entities/0`, `/entities/1`); igual que hoy.
- **T-V2** con motor: la básica → `ok`; `actor_orders` tiene 2 entradas y la de `act-01` es **igual, clave a clave, al JSON literal de §2.1** con los `items` de `partisano`; `plan`, `expectation` y `envelope` iguales (`==`) a los de la copia sin actores.
- **T-V3** una negativa por fila de la tabla de §3, cada una con su `pointer` exacto y nada más en `errors`.
- **T-V4** precedencia: un actor inválido **y** sin catálogo del mundo → `actor_invalid` (1b va antes de 2). Sin motor, el mismo documento → `expansion_unavailable`.
- **T-V5** gesto por tiempo `t = 1.5` → `g_t_ms = [1500]`, `g_at = [-1]`; por marca `at = 2` → `g_at = [1]`, `g_t_ms = [-1]`.

### 9.2 `app/tests/test_actor_live.py` (T-S, con `FakeMod` + `FakeWorld`, como `test_f2_live.py`)

- **T-S1** feliz: motor `expansion`, apply de la básica → la secuencia de `op.state` de la operación es exactamente `pendiente, ejecutando, aplicado, observado`; un solo `observado` y llega **después** de los dos resultados de `actor.apply`; el motor falso tiene `act-01` y `act-02` con sus prendas.
- **T-S2** `reject_apply("act-02", "combat")` → `parcial/actor_rechazado`, ningún `observado`.
- **T-S3** `wardrobe_drop("act-01")` antes de leer → `parcial/actor_no_cumple`.
- **T-S4** `error_apply("act-01", "prenda")` → `parcial/actor_error`; el resultado de `act-02` que llega después no cambia el estado.
- **T-S5** C5: validar con `hello` `expansion`, cambiar el `hello` a `none` y encolar → `expansion_unavailable`, sin operación nueva, 0 creaciones en el mundo y hora y clima intactos.
- **T-S6** se pierde la conexión con un `actor.apply` entregado y sin resultado → `parcial/conexion_perdida`; su resultado tardío no cambia nada.
- **T-S7** tras T-S2, un `state.read` del mismo mundo no cambia la operación (no hay reconciliación de la etapa).
- **T-S8** reset con motor tras T-S1 → la operación del reset termina `observado`, el motor falso no tiene actores y el mundo tiene 0 propios.
- **T-S9** `despawn_fails("act-01")` → el reset termina `parcial/actores_vivos`.
- **T-S10** reset con motor cuya escena da `parcial/contenido_ajeno` y `despawn_fails` → se queda `parcial/contenido_ajeno`.
- **T-S11** reentrega del mismo `actor.apply` (mismo `op_id`) → el motor falso sigue con un actor por `lid`.
- **T-S12** con motor, documento sin actores → misma secuencia de `op.state` que sin motor; tras el reset se encola exactamente un `actor.reset`.
- **T-S13** `/api/actors/observe` con motor → `read_id`; tras el resultado, `/api/actors/observation` da una foto que pasa `valid_actor_read` con 2 filas. Sin motor → `expansion_unavailable` 409. Una lectura inválida del mod no pisa la anterior.

### 9.3 Mod falso y mod real (T-M, T-M19)

- **T-M1** el `hello` lleva el `actor_engine` configurado; los tres verbos con motor `none` → `rejected/expansion_unavailable`; sin marca `f2` → `unknown_verb`.
- **T-M2** `FakeActorEngine.despawn` deja una foto válida; `spawn(items=...)` usa esas prendas; los tres fallos nuevos hacen lo que dice §6.
- **T-M19** la comprobación estática de §7, con una mutación que la tumba sola (`_assert_only_rule_fails`).

### 9.4 Regresión

`python3 -m unittest discover -s app/tests -t app` (629 + las nuevas) y `qa/tests` en verde **sin editar ninguna prueba existente**. `git diff --stat` no toca `qa/` ni los briefs de F2.

## 10. Antitautología (R26)

Mutaciones que tienen que morir, cada una con la prueba que la mata:

| # | Mutación | La mata |
|---|---|---|
| B1 | paso 1b sin mirar `actor_engine` (siempre corre) | T-V1 |
| B2 | 1b después del paso 2 | T-V4 |
| B3 | `g_at = at` (sin restar 1) | T-V2, T-V5 |
| B4 | `actor_orders` sin `items` del preset (lista vacía) | T-V2 |
| B5 | `observado` al llegar el primer `actor.apply` `ok` | T-S1 |
| B6 | `observado` sin etapa (se ignora `actor_orders`) | T-S1 |
| B7 | `no_cumple` sin mirar `judge_identity` | T-S3 |
| B8 | sin la segunda mirada del `hello` en `enqueue_apply_locked` | T-S5 |
| B9 | `on_internal_dropped_locked` no hace nada | T-S6 |
| B10 | el reset con motor no encola `actor.reset` | T-S8, T-S12 |
| B11 | `actor.reset` con actores vivos da `observado` | T-S9 |
| B12 | `actores_vivos` pisa el motivo de la escena | T-S10 |
| B13 | el mod falso crea otro actor en la reentrega | T-S11 |
| B14 | `/api/actors/observation` guarda una lectura inválida | T-S13 |
| B15 | `DSBX_ActorOps.c` no mira `IsAvailable()` | T-M19 |
| B16 | tolerancia de pose 5 m en vez de 0,5 m | T-S3b (actor desplazado 1 m en el falso) |

## 11. Aceptación

- Los dos `unittest discover` de §9.4 en verde.
- Las 16 mutaciones de §10 mueren.
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
