# F4 parte 1: la cámara del cliente reproduce, para y lee caminos (brief v0.1a)

2026-11-28. Plan `2026-10-26-m1-cine-v2.md` §F4, decisiones #16 y #18. Base: la sonda de S-cam en `claude/s-cam-impl24` (df6b63a, `qa/probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_X_Cam.c`), que todavía no ha compilado en DayZDiag ni ha corrido en partida. Oráculo de Claude, implementación de Grok (E9).

## 1. Qué entra y qué no

Entra:

- El cliente del mod recibe por primera vez órdenes del backend: `camera.play`, `camera.stop` y `camera.read`.
- `camera.play` reproduce una cámara del documento (una clave es «ir a una pose», varias son un camino) con la cámara scripted propia de #16: Catmull-Rom en la posición, slerp en la orientación, lerp de FOV y enfoque, tiempo absoluto sumando el `timeslice` de cada frame. HUD oculto y control del jugador cortado mientras la cámara está activa.
- `camera.stop` suelta la cámara y deja el HUD y el control como estaban antes de activarla.
- `camera.read` devuelve el estado de la cámara.
- En el backend: rutas `/api/camera/*`, el bridge entrega órdenes al peer `client` y un módulo nuevo `camera_live.py` guarda la última lectura.

No entra (otras partes o fases): la cámara libre y «guardar pose» de B1 (F4 parte 2, decisión #17), los botones de la web (F4 parte 2), las tomas y el GO por RPC (F5), el aviso de la opción de DOF (Q5), la cámara que sigue objetos (#4) y cualquier medida en partida. La medida en partida (§7) va en la próxima tanda de partida junto con S-cam.

## 2. Decisiones de este brief (reversibles)

- **D1. `y` de una clave es la altura sobre el terreno** en su `x, z`, como sugiere la fixture (`cam-03`, primer plano a 1,7 m). El mod la pasa a absoluta al empezar (`y_abs = SurfaceY(x, z) + y`) e interpola en absoluto. La pose leída lleva `y` absoluta. Si Guillermo prefiere altura absoluta, solo cambia esa suma.
- **D2. El desenfoque es fijo**: `SetFocus(distancia, DSBX_Const.CAM_FOCUS_BLUR)` con `CAM_FOCUS_BLUR = 1.0`. El esquema solo tiene distancia.
- **D3. Rodar es de la persona** (spec, H1): `play` y `stop` solo con la credencial humana. Leer vale para las dos.
- **D4. Una orden de cámara en vuelo como mucho.** Una segunda da `409 camera_busy`. Dentro del mod, un `play` con un camino sonando se rechaza con `busy` y el camino sigue (plan B2). Un camino que ya acabó no está sonando: un `play` nuevo lo sustituye.
- **D5. Tope de 32 claves por cámara.** 32 claves caben de sobra en `WIRE_CAP`. El backend lo comprueba igualmente con `enqueue_order`.

## 3. El cable

### 3.1 `camera.play`

```json
{"f2": 1, "cam_id": "cam-02",
 "c_t_ms": [0, 3000, 6000],
 "c_x_mm": [6154000, 6168000, 6182000],
 "c_y_mm": [2100, 2400, 1900],
 "c_z_mm": [7610000, 7614000, 7620000],
 "c_yaw_mdeg": [28000, 8000, 348000],
 "c_pitch_mdeg": [-2000, -3000, -1000],
 "c_fov_mdeg": [42000, 36000, 30000],
 "c_focus_mm": [24000, 16000, 12000]}
```

Conversión en el backend, con las funciones de `scene_plan.py`: `c_t_ms = round(t * 1000)`, `c_x_mm`, `c_y_mm`, `c_z_mm` y `c_focus_mm` con `m_to_mm`, `c_yaw_mdeg` con `yaw_to_mdeg` (en `[0, 360000)`), y `c_pitch_mdeg` y `c_fov_mdeg` con `round(v * 1000)`. Las claves van en el orden del documento.

### 3.2 `camera.stop` y `camera.read`

Args `{"f2": 1}`.

### 3.3 La lectura

Las tres órdenes, si salen `done`, devuelven la misma forma:

```json
{"cam": {"active": 1, "playing": 1, "cam_id": "cam-02", "t_ms": 0, "dur_ms": 6000,
         "pose": [6154000, 2100, 7610000, 28000, -2000, 42000]}}
```

`pose` es `[x_mm, y_mm, z_mm, yaw_mdeg, pitch_mdeg, fov_mdeg]`, leída de la cámara activa, con la `y` absoluta (D1). Es válida (`camera_live.valid_cam_read(read)`) si y solo si:

- `read` es un objeto con una sola clave, `cam`, y `cam` tiene exactamente esas seis claves;
- `active` y `playing` valen 0 o 1, y `playing == 1` exige `active == 1`;
- `cam_id` es una cadena de como mucho 40 bytes, y `t_ms` y `dur_ms` son enteros con `0 <= t_ms <= dur_ms`;
- `pose` es una lista de 6 enteros (no `bool`);
- con `active == 0`: `cam_id == ""`, `t_ms == dur_ms == 0` y `pose == [0, 0, 0, 0, 0, 0]`;
- con `active == 1`: `cam_id != ""`, `yaw` en `[0, 360000)`, `pitch` en `[-90000, 90000]`, `fov` en `(0, 180000)`, `|y| <= MAX_Y_MM`, y `x` y `z` en `[0, MAX_XZ_MM]`.

Un `rejected` o un `error` pueden llevar `read: {}`.

## 4. El mod

### 4.1 3_Game (núcleo)

- `DSBX_CamEngine.c`, con `class DSBX_CamEngine : Managed` y los métodos `string Play(DSBX_Args args)`, `string Stop()`, `string ReadJson()` y `void Tick(float timeslice)`. En la base, `Play` y `Stop` devuelven `"unknown_verb"`, `ReadJson` devuelve `""` y `Tick` no hace nada. `Play` y `Stop` devuelven `""` si salen bien o el motivo del rechazo.
- `class DSBX_CamEngineRegistry` con `protected static ref DSBX_CamEngine s_Engine;`, `Register(DSBX_CamEngine engine)` (ignora `null`) y `Get()` (crea la base si no hay ninguna), igual que `DSBX_ActorEngineRegistry`.
- `DSBX_Args` gana `string cam_id;` y los ocho `ref array<int>` de §3.1, con esos nombres.
- `DSBX_Peer.StartOrderExecution` empieza con un bloque `if (m_IsClient)` que es la rama del cliente (M20 lo busca con ese texto): con `args.f2 == 1`, `camera.play`, `camera.stop` y `camera.read` van a `DSBX_CamEngineRegistry.Get()`. Un `Play` o `Stop` que devuelve `""` termina `done` con `ReadJson()` como lectura; si no, termina `rejected` con ese motivo y `"{}"`. `camera.read` termina `done` con `ReadJson()`. Cualquier otro verbo en el cliente sigue con `rejected/unknown_verb`. En el servidor, `camera.*` sigue con `unknown_verb`: el despacho de cámara solo está dentro de la rama del cliente.
- Ningún fichero de 3_Game nombra `MissionGameplay`, `GetMission`, `IngameHud`, `PlayerBase` ni `PlayerControlDisable`, porque esas clases viven en capas de arriba.
- `DSBX_Const.CAM_FOCUS_BLUR = 1.0` y `DSBX_Const.CAM_MAX_KEYS = 32`.

### 4.2 5_Mission (cliente)

- `DSBX_CamClient.c`, con `class DSBX_CamClient : DSBX_CamEngine`, que porta de la sonda `EnsureActiveCam` (`staticcamera`, `YawPitchRollMatrix`, `SetTransform`, `SetFOV`, `SetActive(true)`), `SlerpQuat` (arco corto, lineal si `d > 0.9995`), `SetPlayerControlDisabled`, `HideHudAndSaveState` y `RestoreHudSavedState`, sin el overlay de pruebas ni los fallos inyectados.
- `Play(args)` valida antes de cualquier efecto y devuelve `"bad_args"` sin tocar nada si falla algo de esto: `cam_id == ""`, falta un array o los nueve no miden lo mismo, `N < 1` o `N > CAM_MAX_KEYS`, `c_t_ms[0] != 0`, los tiempos no crecen estrictamente, `yaw` fuera de `[0, 360000)`, `pitch` fuera de `[-90000, 90000]`, `fov` fuera de `(0, 180000)` o `focus <= 0`. Con un camino sonando devuelve `"busy"`. Si todo está bien: la primera activación guarda el HUD y lo oculta y corta el control. Después, `t = 0`, `dur = c_t_ms[N-1]`, y la pose de la clave 0 se aplica en el acto.
- `Tick(timeslice)`: con un camino sonando, `t += timeslice * 1000` y se aplica la pose en `t`. Con `t >= dur`, se aplica la última clave exacta, `t = dur` y el camino deja de sonar. La cámara sigue activa en esa pose.
- La interpolación, en el tramo `k` (`t_k <= t < t_{k+1}`) con `u = (t - t_k) / (t_{k+1} - t_k)`:
  - Posición: con `N == 2`, lineal. Con `N >= 3`, Catmull-Rom uniforme con los extremos duplicados (`P_{-1} = P_0`, `P_N = P_{N-1}`): `p = 0.5 * (2·P1 + (−P0 + P2)·u + (2·P0 − 5·P1 + 4·P2 − P3)·u² + (−P0 + 3·P1 − 3·P2 + P3)·u³)`.
  - Orientación: `slerp` entre los cuaterniones de `YawPitchRollMatrix(yaw, pitch, 0)` de las dos claves, por el arco corto. El roll es 0 en M1.
  - FOV y enfoque: lineales. El FOV pasa a radianes para `SetFOV`. El enfoque se aplica con `SetFocus(dist_m, CAM_FOCUS_BLUR)`.
- `ReadJson()` construye la forma de §3.3 con `GetCurrentCameraPosition`, `GetCurrentCameraDirection` (yaw y pitch) y `Camera.GetCurrentFOV()` (de radianes a milésimas de grado). Es una sola llamada a texto por expresión (M17).
- `Stop()` desactiva y borra la cámara, deja el HUD con el estado guardado (nunca forzado a visible) y devuelve el control. Si no había cámara activa, sale `""` sin hacer nada.
- Ni `InterpolateTo` ni `FreeDebugCamera` (#16).
- `DSBX_Mission.c`, `MissionGameplay`: `OnMissionStart` llama a `DSBX_CamEngineRegistry.Register(new DSBX_CamClient());`, `OnUpdate` a `DSBX_CamEngineRegistry.Get().Tick(timeslice);` y `OnMissionFinish` a `DSBX_CamEngineRegistry.Get().Stop();` antes de `m_DsbxPeer.Shutdown();`. `MissionServer` no toca la cámara.
- `DSBX_CamClient` usa `DSBX_Const.CAM_FOCUS_BLUR` y `DSBX_Const.CAM_MAX_KEYS`, no los números sueltos.

## 5. El backend

### 5.1 Bridge

- `enqueue_order(..., role="server")`: el `conn`, el `epoch` y el `inst` salen del peer de ese rol. `_public_order` usa ese mismo peer de reserva.
- `_pick_order_locked(peer, record)`: cada rol solo ve sus órdenes. El cliente sigue la misma regla de reintento y una en vuelo que el servidor, sin la espera de `reconciled`.
- Los `conn` de los dos roles se cuentan aparte y coinciden: `_check_server_loss_locked` y `_transition_conn_orders_locked` solo tocan órdenes del servidor.
- Hello del cliente: sus órdenes del `conn` anterior todavía `pendiente` o `ejecutando` pasan a `descartada`, y se avisa a `camera_live.on_dropped_locked(order, "conexion_perdida")`.
- Barrido: una orden del cliente que vence su TTL pasa a `descartada`, con `on_dropped_locked(order, "sin_resultado")`. Ni lectura del mundo ni reintentos de lectura.
- `handle_result` de una orden `camera.*`: si sale `done` y la lectura no cumple `valid_cam_read`, devuelve `400 bad_request` y no cambia nada. Si cumple, `camera_live.on_result_locked(order, status, reason, read)`, `result_seen` y `terminal`.

### 5.2 `camera_live.py`

Su estado solo se toca bajo el lock del bridge: la orden en vuelo, el último resultado y la última lectura con su hora en el reloj del bridge.

- `POST /api/camera/play {doc_id, cam_id}`, solo la persona. Devuelve `200 {"ok": true, "op_id": ...}`. Errores, en este orden:
  - `403 forbidden` (IA);
  - `400 bad_request` (campos);
  - `409 scene_unsupported` (sin bridge);
  - `409 doc_changed` (pointer `/doc_id`);
  - `404 not_found` (pointer `/cam_id`);
  - `409 client_not_in_game` (si `bridge.client_in_world()` es falso);
  - `409 camera_busy`;
  - `422 invalid` (más de 32 claves en `/cameras/<i>/keys`, o dos claves en el mismo milisegundo en `/cameras/<i>/keys/<k>/t`, con `<k>` la segunda);
  - `422 out_of_map` (`x` o `z` fuera de `[0, world_size]` del hello del servidor, en `/cameras/<i>/keys/<k>/x` o `/z`);
  - `422 plan_too_large` (no cabe en el cable).

  Ningún error encola nada.
- `POST /api/camera/stop {}` es solo de la persona. `POST /api/camera/read {}` vale para la persona y la IA. Los dos devuelven `200 {"ok": true, "op_id"}`, con `403`, `409 scene_unsupported`, `409 client_not_in_game` y `409 camera_busy` como arriba.
- `GET /api/camera`, para las dos credenciales, devuelve siempre 200:

  ```json
  {"ok": true, "cam": <cam de la última lectura válida o null>, "age_ms": <int o null>,
   "last": {"op_id", "verb", "status", "reason"} | null, "in_flight": <op_id o null>}
  ```

  `status` es `done`, `rejected`, `error` o `dropped`. `reason` es `null` en `done`, el motivo del mod en `rejected` y `error`, o el de §5.1 en `dropped`. Un `rejected` o `error` no cambia `cam`.
- Códigos nuevos en `STATUS`: `client_not_in_game: 409`, `camera_busy: 409`.

### 5.3 Fuera de este brief

La web, el MCP y SSE. `GET /api/camera` basta para la parte 2.

## 6. Pruebas (oráculo de Claude, congelado; Grok no las toca)

En rojo en la rama antes de implementar, por la razón correcta (rutas 404, M1/M20 sin los ficheros nuevos).

- `app/tests/fake_camera.py` (oráculo): la cámara del cliente falso. Cumple §4.2 salvo la interpolación: la pose sale de la clave 0 al empezar y de la última al acabar, y el tiempo es el reloj de pared desde el `play`. `fake_mod._execute` la usa en el peer `client`; el servidor sigue sin verbos de cámara.
- `app/tests/test_f4_camera.py`:
  - **K1** `play` de `cam-02`: args exactos de §3.1 en la orden, rol `client`, `conn` y `epoch` del cliente. El servidor no la ve. `GET` da `done` y la pose de la clave 0.
  - **K2** el camino acaba: `read` da `playing 0`, `t_ms == dur_ms` y la pose de la última clave.
  - **K3** una sola clave (`cam-01`): `playing 0`, `dur_ms 0`.
  - **K4** credenciales: la IA recibe 403 en `play` y `stop` sin encolar nada, y 200 en `read` y en `GET`.
  - **K5** `409 client_not_in_game` sin cliente en el mundo (epoch distinto), sin encolar.
  - **K6** `409 doc_changed`, y `404 not_found` con una cámara que no existe.
  - **K7** `422`: dos claves en el mismo milisegundo, 33 claves y `x` fuera del mapa, cada uno con su pointer y sin encolar. 32 claves sí se encolan.
  - **K8** `409 camera_busy` con una orden en vuelo (polls del cliente cortados).
  - **K9** el mod rechaza `busy` con un camino sonando: `last` da `rejected/busy` y `cam` sigue con el primer camino.
  - **K10** `stop` deja `active 0` y la pose a ceros. Un segundo `stop` también sale `done`.
  - **K11** un hello nuevo del cliente descarta la orden en vuelo: `dropped/conexion_perdida`, `in_flight null`, y el siguiente `play` entra.
  - **K12** el TTL vencido en el barrido da `dropped/sin_resultado`.
  - **K13** un hello nuevo del servidor, o perderlo en el barrido, no toca una orden del cliente pendiente.
  - **K14** una lectura `done` inválida del cliente da 400 en el bridge y `GET` no cambia.
  - **V1** `valid_cam_read`: una tabla de lecturas válidas y una por cada regla de §3.3 rota.
- `app/tests/test_mod_static.py`: M1 con los dos ficheros nuevos, y una regla **M20** que comprueba lo verificable a mano de §4: la base y el registro, los campos de `DSBX_Args`, el despacho solo en la rama del cliente y bajo `f2 == 1`, los tokens prohibidos en 3_Game, en `DSBX_CamClient` los tokens obligatorios (`staticcamera`, `SetActive(true)`, `SetFOV(`, `SetFocus(`, `PlayerControlDisable(`, `PlayerControlEnable(`, `GetCurrentFOV`, `Math3D.MatrixToQuat`, `Math3D.QuatToMatrix`) y los prohibidos (`InterpolateTo`, `FreeDebugCamera` y `SetContextFlag(EHudContextFlags.HUD_HIDE, false)`), y los tres enganches de `MissionGameplay`. Más su X4: cada mutación tumba solo M20.
- Las mutaciones (`plans/f4cam-mutants.py`) se fijan después de la implementación, como en F3-web.

Gate: el offline entero de `reference-cloud-gate-m1` (unittest, build, `e2e_web`, `e2e_studio` S, C y AC). Para aceptar no cuenta que sea «verde en mi máquina», solo el gate en la nube.

## 7. Medida en partida (para la tanda con S-cam, no ahora)

Compilar en DayZDiag. Después, en partida: `play` de `cam-02` muestreado por frame frente a la expectativa analítica de §4.2 (< 0,5 m y < 0,5°), fin entre 6,0 y 6,3 s, `cam-01` con la pose leída a < 0,05 m y < 0,5° con D1 aplicada, HUD y barra rápida ocultos de principio a fin, y `stop` que devuelve el control en < 1 s con el HUD de antes. Los negativos son `busy` y `bad_args` sin efecto.

## 8. Lanes

- **Lane A (Grok), Enforce:** §4. Ficheros: `DayZSandbox/scripts/3_Game/DSBX_CamEngine.c` (nuevo), `DSBX_Messages.c`, `DSBX_Const.c`, `DSBX_Peer.c`, `DayZSandbox/scripts/5_Mission/DSBX_CamClient.c` (nuevo) y `DSBX_Mission.c`. Debe pasar `test_mod_static.py` entero.
- **Lane B (Grok), Python:** §5. Ficheros: `app/backend/bridge.py`, `app/backend/camera_live.py` (nuevo) y `app/backend/server.py`. Debe pasar `test_f4_camera.py` y no romper nada más.
- R25 y R20: nada fuera de esos ficheros. Lo raro de alrededor va a `bugs.md`.

## 9. Resultado (2026-11-28)

- Implementación de Grok (grok-4.6) en Willy, en dos lanes paralelas: A (Enforce) 8c0bba5, 2 min 36 s y 0,68 USD; B (Python) 830f632, 3 min 07 s y 0,71 USD. Ninguna tocó ficheros fuera de su lista.
- Arreglos de Claude después (fallback), cada uno trazado al brief:
  - `DSBX_Peer.StartOrderExecution` declaraba `string verb` dos veces en la misma función. Enforce no lo admite y no habría compilado. La rama del cliente usa ahora `camVerb`.
  - `valid_cam_read` aceptaba `active: true` (§3.3 pide enteros 0 o 1).
- Arreglos del oráculo: M19 buscaba el primer bloque `f2 == 1` de `StartOrderExecution`, que ahora es el del cliente, así que cuenta el que despacha actores. La X4 de M20 cambia la herencia de `DSBX_CamClient`, porque `"staticcamera"` sale dos veces.
- Gate en la nube: 731 unittest, build, e2e_web P1-P9b, S1-S12, C1-C10 y AC1-AC8, todo verde.
- Mutaciones `plans/f4cam-mutants.py` F1-F12: 12/12 muertas.
- Dudas de las lanes (`f4cam-dudas-a.md`, `f4cam-dudas-b.md`): yaw y pitch salen de la dirección como `Atan2(x, z)` y `Asin(y)`, y la pose se redondea con `Math.Round`. Queda abierta una: si no se puede crear la `staticcamera`, `Play` devuelve `""` igualmente. Va a la medida de §7.
- Falta: compilar en DayZDiag y la medida de §7, en la tanda de partida con S-cam.
