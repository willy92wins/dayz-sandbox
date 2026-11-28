# F5 parte 1: la toma sin juego (brief v0.1)

2026-11-28. Plan `2026-10-26-m1-cine-v2.md` §F5, decisiones #4 y #33. Base: la rama de la PR #33 (`claude/project-thread-c4y6r9`, ffc2bc6), que trae F4 parte 1 (`camera.*` en el cliente) y F4-web. Oráculo de Claude, implementación de Grok (E9).

## 1. Qué entra y qué no

Entra:

- La máquina de toma del backend (`app/backend/take_live.py`): preparar con las lecturas del servidor y «cámara lista» del cliente, armada, rodando, y terminada, parada o fallida.
- `take_stop` con prioridad sobre cualquier otra orden del servidor.
- El origen de cada parada (`web`, `juego` u `hombre_muerto`), que el backend lee del mod.
- El contrato del cable de la toma (§3), que el mod falso cumple (`app/tests/fake_take.py`, oráculo) y el mod real cumplirá en la parte 2.
- El panel Tomas de la web.

No entra:

- El canal GO real (el RPC del servidor al cliente) y su medida. Dependen de S-toma, que cerró en FALLA y tiene otra ronda. En el mod falso el GO es una llamada directa del servidor falso al cliente falso.
- Todo el Enforce: la máquina en el mod servidor, la tecla de `inputs.xml`, `take_stop_key` con reintentos cada 250 ms, el acuse y el hombre muerto real. Van en la parte 2, cuando S-toma pase.
- La protección del director (Q6), la cancelación real de las cues de Expansion, el reset entre tomas (B6) y el atajo de teclado de Parar (D4).

## 2. Decisiones de este brief (reversibles)

- **D1.** El hombre muerto deja la toma `parada` con origen `hombre_muerto`. No usa `fallida`: la toma se corta igual que con un stop.
- **D2.** Cualquier final (terminada o parada) suelta la cámara del cliente y devuelve el control, también `terminada`.
- **D3.** Preparar, rodar y parar son solo de la persona (spec I4). Leer la toma vale para las dos credenciales.
- **D4.** La toma dura lo que el camino de su cámara (el `t` de la última clave). Una cámara con una sola clave no sirve para una toma: `422 invalid`.
- **D5.** Rodar es una pulsación aparte. La toma no rueda sola al quedar armada.
- **D6.** `take_id = "tk-" + session + "-" + n`, con `n` el contador de tomas del backend desde 1 y `session` la del bridge. Así no se repite dentro de un epoch aunque se reinicie el backend (#33).

## 3. El cable

Todas las órdenes llevan `f2: 1`. Las del servidor se encolan con `internal=True`. `take.cam_load` va al peer `client`.

### 3.1 Órdenes

| Verbo | Rol | Args además de `f2` |
|---|---|---|
| `take.cam_load` | client | los nueve campos de `camera.play` de F4 parte 1 §3.1 (`cam_id` y los ocho arrays), más `take_id` y `cam_hash` |
| `take.prepare` | server | `take_id`, `cam_id`, `rev`, `hash`, `dur_ms` |
| `take.arm` | server | `take_id`, `cam_hash` |
| `take.go` | server | `take_id` |
| `take.stop` | server | `take_id` |
| `take.read` | server | ninguno |

- `cam_hash` son los 16 primeros caracteres hex de `sha256` sobre `json.dumps(cam_args, sort_keys=True, separators=(",", ":"))`, donde `cam_args` son los nueve campos de `camera.play` (sin `f2`, `take_id` ni `cam_hash`).
- `dur_ms` es `c_t_ms[-1]`.
- `rev` y `hash` son los del documento al preparar.
- `take.stop` sale antes que cualquier otra orden pendiente del servidor: `enqueue_order` le da `priority = -1`. No adelanta a la orden que el servidor ya está ejecutando.

### 3.2 Lectura del servidor

`take.prepare`, `take.arm`, `take.go`, `take.stop` y `take.read`, si salen `done`, devuelven:

```json
{"take": {"take_id": "tk-…-1", "state": "rodando", "origin": "", "t_ms": 1200, "dur_ms": 6000, "bad": []}}
```

`bridge` la valida con `take_live.valid_take_read(read)`, que es cierta si y solo si:

- `read` tiene una sola clave, `take`, y `take` tiene exactamente esas seis claves;
- `take_id` es una cadena de como mucho 64 bytes;
- `state` es `ninguna`, `preparada`, `armada`, `rodando`, `terminada` o `parada`;
- `origin` es `""`, `web`, `juego` u `hombre_muerto`, y es distinto de `""` si y solo si `state == "parada"`;
- `t_ms` y `dur_ms` son enteros (no `bool`) con `0 <= t_ms <= dur_ms`. `t_ms == 0` en `ninguna`, `preparada` y `armada`, y `t_ms == dur_ms` en `terminada`;
- `bad` es una lista sin repetidos de nombres de `CHECKS = ("scene", "marks", "wardrobe", "env", "director")`, y solo puede tener elementos con `state == "preparada"`;
- con `state == "ninguna"`: `take_id == ""` y `dur_ms == 0`. En el resto, `take_id != ""`.

### 3.3 Lectura del cliente

`take.cam_load`, si sale `done`, devuelve `{"ready": {"take_id": "...", "cam_hash": "..."}}`, con las dos cadenas no vacías y sin más claves. La valida `take_live.valid_ready_read(read)`.

### 3.4 Lo que hace el mod (contrato; el falso lo cumple)

- `take.prepare` comprueba la escena, las marcas, el vestuario, el ambiente y el director, y responde `preparada` con la lista `bad` de lo que no cumple. Sustituye a una toma anterior que esté `preparada` o terminada. Con una toma `armada` o `rodando`, la rechaza con `busy`.
- `take.cam_load` (cliente) guarda el camino y responde «cámara lista» con su `take_id` y `cam_hash`. El cliente se lo dice también al servidor; en el mod falso, el servidor lo lee directamente del cliente falso.
- `take.arm` exige la toma `preparada` con ese `take_id` (si no, `rejected/bad_state`) y que el cliente haya cargado ese `take_id` con ese `cam_hash` (si no, `rejected/cam_not_ready`). Responde `armada`.
- `take.go` exige `armada` con ese `take_id` (si no, `rejected/bad_state`). En el mismo tick arranca los actores y manda el GO al cliente, que reproduce el camino cargado si no tiene esa toma como parada pendiente. Responde `rodando`. A los `dur_ms` la toma pasa a `terminada` y el cliente suelta la cámara (D2).
- `take.stop` con una toma `preparada`, `armada` o `rodando` de ese `take_id`: la deja `parada` con origen `web`, cancela las cues y el cliente suelta la cámara. Con la toma ya terminada, responde lo que ya tiene sin cambiar nada. Con otro `take_id` o sin toma, `rejected/unknown_take`.
- La tecla del juego (#33) con la toma `armada` o `rodando`: `parada` con origen `juego`. Sin toma viva, o con un menú o el chat abiertos, no hace nada.
- Hombre muerto: con la toma `armada` o `rodando`, si el servidor lleva más de la ventana sin un poll que conteste, la toma pasa a `parada` con origen `hombre_muerto` y el cliente suelta la cámara (D1).
- La primera transición a un estado final fija el estado y el origen. Lo que llega después no los cambia.
- `take.read` devuelve la toma actual o la última (`ninguna` si no hubo).

## 4. El backend

### 4.1 Estado y `GET /api/take`

`TakeLive` vive en `server.take_live` y se crea junto a `camera_live` cuando hay bridge. Su estado solo se toca bajo el lock del bridge.

`GET /api/take`, con cualquiera de las dos credenciales, devuelve siempre 200:

```json
{"ok": true, "take": {"take_id", "doc_id", "rev", "cam_id", "state", "origin", "reason", "bad", "t_ms", "dur_ms"} | null}
```

- `state` es `preparando`, `armada`, `rodando`, `terminada`, `parada` o `fallida`.
- `origin` es `null` salvo en `parada`, donde es `web`, `juego` u `hombre_muerto`.
- `reason` es `null` salvo en `fallida`.
- `bad` es la lista de la lectura de `take.prepare` (vacía mientras no llega).
- `t_ms` y `dur_ms` son los de la última lectura válida de esa toma (0 y el `dur_ms` del backend hasta entonces).
- `take` es `null` hasta la primera toma. Después enseña la última.

`server.take_state` sigue al estado de la toma (`"libre"` sin toma), así que `TAKE_LOCKED` bloquea las ediciones con la toma `armada` o `rodando`, como ya hace el gate.

### 4.2 `POST /api/take/prepare {doc_id, cam_id}`

Solo la persona. Devuelve `200 {"ok": true, "take_id": ...}`. Los errores, en este orden, y ninguno encola nada:

1. `403 forbidden` (IA);
2. `400 bad_request` (campos que no son cadenas no vacías);
3. `409 scene_unsupported` (sin bridge);
4. `409 doc_changed` (pointer `/doc_id`);
5. `404 not_found` (pointer `/cam_id`);
6. `409 no_director` (si `bridge.client_in_world()` es falso);
7. `409 take_busy` (hay una toma `preparando`, `armada` o `rodando`);
8. `409 scene_not_observed`: la última operación de `backend.ops` (por orden de inserción) tiene que ser un `scene.apply` (sin `verb` o con `verb == "scene.apply"`) en estado `observado`, con el `rev` y el `hash` del documento actual. Si no, este error;
9. `422 invalid`, pointer `/cameras/<i>/keys`, si la cámara tiene menos de 2 claves (D4);
10. los `422` y el `plan_too_large` de `camera.play` (F4 parte 1 §5.2), con los mismos pointers. Para no duplicar esas comprobaciones, se saca de `CameraLive.request_play_locked` una función que construye los args de `camera.play` o devuelve el error, y `request_play_locked` la usa sin cambiar su comportamiento.

Si todo vale: nueva toma en `preparando` con su `take_id` (D6), y se encolan `take.cam_load` (cliente) y `take.prepare` (servidor). Si una de las dos no cabe en el cable, `422 plan_too_large` y no queda ninguna encolada.

### 4.3 Avance de la toma

| Llega | Con | Pasa |
|---|---|---|
| `take.prepare` `done` | `take_id` de la toma | guarda `bad`. Si `bad` no está vacía: `fallida`, `reason = "checks"` |
| `take.cam_load` `done` | `ready.take_id` y `ready.cam_hash` de la toma | marca la cámara lista. Si no coinciden: `fallida`, `reason = "cam_not_ready"` |
| las dos anteriores bien | sin parada pedida | si el `rev` o el `hash` del documento cambiaron desde que se preparó: `fallida`, `reason = "doc_changed"`. Si no, encola `take.arm` |
| `take.arm` `done` con `state == "armada"` | | `armada` |
| `take.go` `done` con `state == "rodando"` | | `rodando` |
| cualquier lectura `done` de la toma con `state` `terminada` o `parada` | | ese estado y su origen, con `t_ms` y `dur_ms` |
| `rejected` o `error` de `take.cam_load`, `take.prepare`, `take.arm` o `take.go` | toma viva | `fallida`, `reason` = el motivo del mod |
| orden descartada de esos cuatro verbos | toma viva | `fallida`, `reason` = el motivo del descarte |
| `take.stop` `rejected/unknown_take` | toma `preparando` | `parada`, origen `web` |
| hello del servidor con otro `epoch` | toma viva | `fallida`, `reason = "mundo_reiniciado"` |

- «Toma viva» es `preparando`, `armada` o `rodando`. Una toma terminada (`terminada`, `parada` o `fallida`) no cambia nunca más.
- Una lectura con otro `take_id` no cambia nada.
- Un `take.read` o un `take.stop` descartados, o un `take.read` `rejected` o `error`, no cambian el estado.
- Con una lectura `rodando` válida de la toma, el backend actualiza `t_ms` y `dur_ms`.

### 4.4 Rodar, parar y leer

- `POST /api/take/go {take_id}`, solo la persona: `403`, `400`, `409 scene_unsupported`, `404 not_found` (no es la toma actual; pointer `/take_id`) y `409 take_state` (la toma no está `armada`, o ya se pidió pararla). Si vale, encola `take.go` y devuelve `200 {"ok": true}`.
- `POST /api/take/stop {take_id}`, solo la persona: `403`, `400`, `409 scene_unsupported`, `404 not_found` y `409 take_state` (la toma no está viva). Si vale, marca la parada pedida, encola `take.stop` (si no hay ya uno pendiente o en curso) y devuelve `200 {"ok": true}`. Un segundo stop mientras el primero sigue en curso da 200 y no encola otro.
- Tick, llamado desde `Bridge.sweep` bajo su lock: con una toma viva y el servidor sin perder,
  - si hay parada pedida y no hay un `take.stop` pendiente o en curso, encola otro (así se reintenta si se descartó);
  - con la toma `armada` o `rodando`, si no hay un `take.read` pendiente o en curso y pasaron al menos `TAKE_READ_MS = 250` desde el último que se encoló, encola un `take.read`. Así ve la tecla del juego, el hombre muerto y el final.

### 4.5 Bridge

- `handle_result` de una orden `take.*`: si sale `done` y la lectura no cumple `valid_take_read` (servidor) o `valid_ready_read` (cliente), devuelve `400 bad_request` y no cambia nada. Si cumple, `take_live.on_result_locked(order, status, reason, read)`, `result_seen` y `terminal`, como las de cámara.
- Las órdenes descartadas avisan a `take_live.on_dropped_locked(order, reason)`: las internas del servidor en `_internal_dropped_locked`, y las del cliente donde ya se avisa a `camera_live` (hello del cliente y TTL del barrido).
- El hello del servidor avisa a `take_live.on_server_hello_locked(peer_record)`.
- Códigos nuevos en `STATUS`: `no_director`, `take_busy`, `take_state` y `scene_not_observed`, todos 409.

## 5. La web: panel Tomas (`data-panel="tomas"`)

Sustituye al hueco: el panel deja de llevar `data-hueco`. Todo texto del documento o del backend se pinta como texto. Los ids, `data-*` y textos entre comillas van tal cual.

- `#take-cam`, un `select` con una opción por cámara del documento que tenga 2 claves o más, en su orden (`value` = id, texto = nombre). Sin ninguna, el `select` está desactivado y `[data-take-vacio]` dice «Crea una cámara con un camino para rodar.»
- `#take-prepare`, «Preparar»: desactivado sin cámara elegida o con una toma viva. Manda `POST /api/take/prepare {doc_id, cam_id}`.
- `#take-go`, «Rodar»: activo solo con la toma `armada`. Manda `POST /api/take/go {take_id}`.
- `#take-stop`, «Parar»: activo solo con una toma viva. Manda `POST /api/take/stop {take_id}`.
- El panel lee `GET /api/take` al montarse, cada 500 ms y justo después de cada POST que sale 200.
- `[data-take-estado]`, el texto, por orden:
  1. Si el último POST salió con error: `409 no_director` → «Tu juego no está conectado»; `409 scene_not_observed` → «Aplica la escena antes de preparar»; `409 take_busy` → «Ya hay una toma en curso»; cualquier otro → «No se pudo: <msg>». Se queda hasta el siguiente POST que sale 200.
  2. Sin toma → «Sin tomas todavía».
  3. `preparando` → «Preparando <nombre>».
  4. `armada` → «Lista para rodar <nombre>».
  5. `rodando` → «Rodando <nombre> · <t> / <dur> s», con un decimal y coma decimal (`1,2 / 6,0 s`).
  6. `terminada` → «Terminada».
  7. `parada` → según el origen: `web` → «Parada desde la web»; `juego` → «Parada con la tecla del juego»; `hombre_muerto` → «Parada por hombre muerto».
  8. `fallida` con `reason == "checks"` → «No está lista: » y los nombres de `bad` separados por «, »: `scene` → «escena distinta», `marks` → «actores fuera de marca», `wardrobe` → «vestuario distinto», `env` → «hora o clima distintos», `director` → «sin director».
  9. `fallida` con otro motivo → «Falló (<reason>)».

  `<nombre>` es el de la cámara del documento con el `cam_id` de la toma, o el id si ya no existe.

## 6. Pruebas (oráculo de Claude, congelado; Grok no las toca)

En rojo en la rama antes de implementar, por la razón correcta (rutas 404 y el hueco de Tomas).

- `app/tests/fake_take.py` (oráculo): la toma del mod falso, servidor y cliente, según §3.4. Ganchos de prueba: `fail_checks` (lista para `bad`), `press_stop_key(menu_open=False)`, `deadman_ms` y `hold_go` (retiene el GO del cliente). El GO llama directamente a la cámara falsa de F4 con los args cargados.
- `app/tests/test_f5_take.py`:
  - **T1** preparar: las dos órdenes con los args exactos de §3.1 (roles, `cam_hash`, `dur_ms`, `internal`), después `take.arm` con el mismo `cam_hash`, y la toma `armada`. Ediciones de la escena con la toma armada → `take_locked`.
  - **T2** rodar: `rodando`, la cámara del cliente falso suena con `cam_id` de la toma, y al acabar `terminada`, `t_ms == dur_ms`, la cámara suelta y las ediciones vuelven.
  - **T3** parar desde la web rodando: `parada` con origen `web`, cámara suelta. Un segundo stop da 200 sin otra orden. `take_state` en `go` y `stop` después.
  - **T4** `take.stop` adelanta: con el servidor cortado, un `take.read` pendiente y un stop, el stop sale primero al volver.
  - **T5** la tecla del juego: `parada` con origen `juego`. Con el menú abierto, nada. Tecla y web a la vez → una sola parada con el origen de la que llegó primero.
  - **T6** hombre muerto: polls del servidor cortados más de la ventana con la toma rodando → al volver, `parada` con origen `hombre_muerto`.
  - **T7** `fail_checks = ["marks", "env"]` → `fallida`, `reason = "checks"`, `bad` así, y ningún `take.arm`.
  - **T8** errores de `prepare` en el orden de §4.2: IA 403, 400, `doc_changed`, `not_found`, `no_director`, `take_busy`, `scene_not_observed` (sin aplicar, y aplicado y luego editado), y una sola clave → 422. Ninguno encola.
  - **T9** el documento cambia entre preparar y armar → `fallida/doc_changed` y ningún `take.arm`.
  - **T10** stop durante `preparando` → `parada` web y ningún `take.arm`.
  - **T11** epoch nuevo del servidor con la toma armada → `fallida/mundo_reiniciado`.
  - **T12** credenciales: la IA recibe 403 en `go` y `stop`, y 200 en `GET /api/take`.
  - **T13** `take.go` retenido (`hold_go`) y tecla antes de entregarlo → `parada/juego` y la cámara no vuelve a sonar al soltar el GO.
  - **V1** `valid_take_read` y `valid_ready_read`: una tabla de lecturas válidas y una por cada regla rota.
- `app/web/e2e/tomas.e2e.cjs`, filas TM1-TM6, con `DSBX_GUION=tomas python3 app/tests/e2e_studio.py`. Simula `/api/take*` con `page.route`:
  - **TM1** el `select` solo con cámaras de 2 claves o más; sin ninguna, el texto de vacío y el `select` desactivado.
  - **TM2** Preparar manda el cuerpo exacto, y los botones se activan y desactivan según el estado.
  - **TM3** Rodar y Parar mandan el `take_id` de la toma.
  - **TM4** los textos de los estados, del 2 al 7 de §5.
  - **TM5** los textos de error (paso 1) y de `fallida` (pasos 8 y 9).
  - **TM6** texto hostil: un nombre de cámara con HTML se ve literal.
- `studio.e2e.cjs` S1: `tomas` deja de ser un hueco.
- `e2e_studio.py` gana `DSBX_GUION=tomas`.
- Las mutaciones (`plans/f5take-mutants.py`) se fijan después de la implementación.

Gate: el offline entero de `reference-cloud-gate-m1` más `DSBX_GUION=camaras` y `DSBX_GUION=tomas`. Solo cuenta el gate en la nube.

## 7. Lanes (Grok, en paralelo)

- **Lane A, Python:** §3 y §4. Ficheros: `app/backend/take_live.py` (nuevo), `app/backend/bridge.py`, `app/backend/camera_live.py` (solo la función de §4.2.10) y `app/backend/server.py`. Debe pasar `test_f5_take.py` y no romper nada más.
- **Lane B, web:** §5. Ficheros bajo `app/web/src/`: un panel nuevo `panels/TakesPanel.tsx`, `App.tsx` para montarlo en lugar del hueco, `store.ts` y `types.ts`. Debe pasar `tomas.e2e.cjs`.
- R25 y R20: nada fuera de esos ficheros. Lo raro de alrededor va a `bugs.md`.
