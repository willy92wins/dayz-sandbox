# F4-web: las cámaras en el estudio (brief v0.1)

2026-11-28. Sigue a F4 parte 1 (`2026-11-28-m1-f4-camara-1-brief.md`), que dejó la API `/api/camera` en el backend. Hoy la web no edita cámaras: el panel Cámaras es un hueco («Llega con F4 y F5») y la Jerarquía dice «Llegan con F4». El almacén ya acepta `camera.add`, `camera.set` (`name`, `keys`) y `camera.delete`, y las leases ya valen con ids de cámara. Oráculo de Claude, implementación de Grok (E9). Referentes: los marcadores del Rockstar Editor y el panel de cámaras del prototipo (`ui/prototipo/estudio.html`, `keyProps` y la pestaña Cámaras).

## 1. Qué entra y qué no

Entra: el panel Cámaras (lista, nueva cámara, reproducir y parar en el juego, y el estado del juego), las cámaras en la Jerarquía, Propiedades de una cámara (nombre, claves editables, añadir y quitar clave, ir a una pose, borrar), y en el backend `key` opcional en `POST /api/camera/play`.

No entra: capturar la cámara libre (F4 parte 2, necesita el juego), las cámaras en el mapa (S-mapa), la línea de tiempo, las tomas (F5), el aviso de DOF (Q5) y copiar y pegar ajustes.

## 2. Backend: `key` en `play`

`POST /api/camera/play {doc_id, cam_id, key?}`. `key` es opcional, entero (no `bool`) y empieza en 0. Con `key`, el mod recibe solo esa clave como pose fija: `c_t_ms: [0]`, y los demás arrays con un elemento. Todo lo demás es igual. Un `key` que no es entero da `400 bad_request`. Si está fuera de `[0, N)`, da `404 not_found` con pointer `/key`, y se comprueba después de `/cam_id`. Las comprobaciones de §5.2 de la parte 1 (fuera del mapa, cable) se hacen sobre esa clave sola.

## 3. La web

Todo texto que viene del documento o del backend se pinta como texto, nunca como HTML. Los ids, `data-*` y textos entre comillas o en código de este apartado van tal cual: los comprueba el guion.

### 3.1 Panel Cámaras (`data-panel="camaras"`)

- Sustituye al hueco: el panel ya no lleva `data-hueco`.
- Una fila por cámara del documento, en su orden: `button[data-cam="<id>"]` con `aria-selected` y dentro el nombre y un resumen:
  - con una clave: «Fija»;
  - con varias: «Camino · N claves · D s», con `D` el `t` de la última clave con un decimal y coma decimal (`6,0`).

  Pulsar la fila selecciona la cámara (`selectedIds = [id]`) y enseña Propiedades.
- Sin cámaras: «Todavía no hay cámaras.»
- `#cam-new`, «Nueva cámara»: un solo `POST /api/scene/ops` con `camera.add {name: "Cámara N", keys: [K0]}`. `N` es `doc.next.cam` y `K0` es `{t: 0, x: 7680, y: 2, z: 7680, yaw: 0, pitch: 0, fov: 50, focus: 10}`. La cámara creada queda seleccionada.
- `#cam-play`, «Reproducir en el juego»: está desactivado sin una cámara seleccionada. Manda `POST /api/camera/play {doc_id, cam_id}`.
- `#cam-stop`, «Parar la cámara»: manda `POST /api/camera/stop {}`.
- `[data-cam-juego]`, el estado del juego. Mientras el panel se ve, lee `GET /api/camera` al abrirse, cada 1 000 ms y justo después de cada `play` o `stop` que sale 200. El texto, por orden:
  1. Si la última respuesta de `play` o `stop` fue un error: `409 client_not_in_game` → «Tu juego no está conectado»; `409 camera_busy` → «Hay una orden de cámara en curso»; cualquier otro → «No se pudo: <msg>». El mensaje se queda hasta la siguiente pulsación que sale 200.
  2. `last.status == "rejected"` o `"error"` → «El juego no la aceptó (<reason>)».
  3. `last.status == "dropped"` → «La orden no llegó al juego».
  4. `cam` nulo o `cam.active == 0` → «Sin cámara del estudio en el juego».
  5. `cam.playing == 1` → «Reproduciendo <nombre> · <t> / <dur> s», con un decimal y coma (`1,2 / 6,0 s`). `<nombre>` es el de la cámara del documento con ese id, o el id si ya no existe.
  6. Si no → «Quieta en <nombre>».

### 3.2 Jerarquía

El grupo «Cámaras» lista `[role="treeitem"][data-cam-id="<id>"]` con el nombre. Pulsar selecciona la cámara, como en el panel. Sin cámaras, el grupo dice «Ninguna».

### 3.3 Propiedades de una cámara

Cuando `selectedIds` es una sola cámara, Propiedades enseña:

- `#f-cam-name`: el nombre, con la lease del campo `name`. Al confirmar manda `camera.set {name}`. Un nombre vacío o solo de espacios queda `aria-invalid` y no se manda.
- `[data-section="claves"]` con una `[data-key="k"]` por clave (`k` desde 1). Cada una tiene los campos `#f-key-k-t`, `-x`, `-y`, `-z`, `-yaw`, `-pitch`, `-fov` y `-focus` (numéricos, en las unidades del documento: s, m y °). Al confirmar uno (Intro o perder el foco), con la lease del campo `keys`, se manda un solo `camera.set {keys}` con la lista entera. Un valor no válido deja el campo `aria-invalid` y no manda nada. Las reglas:
  - `t` es finito. En la clave 1 está fijo a 0 (`readonly`). En las demás tiene que ser mayor que el de la clave anterior y menor que el de la siguiente.
  - `x` y `z` en `[0, 15360]`, `y` finito, `yaw` en `[-180, 360)`, `pitch` en `[-90, 90]`, `fov` en `(0, 180)` y `focus > 0`.
- `#cam-key-add`, «Añadir clave»: añade una copia de la última clave con `t + 1` y manda `camera.set {keys}`.
- `[data-key-del="k"]`, «Quitar clave k»: está desactivado si la cámara tiene una sola clave. Manda `camera.set {keys}` sin esa clave. Si quitas la clave 1, la nueva primera pasa a `t = 0`, y las demás conservan su `t` restándole el `t` de la nueva primera.
- `[data-key-goto="k"]`, «Ir a esta pose»: manda `POST /api/camera/play {doc_id, cam_id, key: k-1}`. Su error se pinta en `[data-cam-juego]` igual que en el panel Cámaras, si el panel está abierto.
- `#cam-delete`, «Borrar cámara»: manda `camera.delete` y vacía la selección.

Las claves se escriben con `commitSceneOps` y la lease de campo que ya usan los actores (`acquireFieldLease`, `releaseFieldLease`).

## 4. Pruebas (oráculo de Claude, congelado; Grok no las toca)

- `app/tests/test_f4_camera.py` **K15**: `play` con `key`. Con `key: 1` sobre `cam-02` salen los args de la clave 2 como pose fija. Con `key: 3`, `404` y pointer `/key`. Con `key: true` o `"1"`, `400`. Ninguno de los errores encola.
- `app/web/e2e/camaras.e2e.cjs`, filas CM1-CM8, que se corren con `DSBX_GUION=camaras python3 app/tests/e2e_studio.py`. El guion simula `/api/camera*` con `page.route`, porque el arnés no tiene mod:
  - **CM1** panel y Jerarquía: las filas, los resúmenes «Fija» y «Camino · 3 claves · 6,0 s», y la selección.
  - **CM2** «Nueva cámara»: un solo POST con los args exactos de §3.1.
  - **CM3** editar una clave: un POST `camera.set` con la lista entera. Las negativas (fuera de rango y un `t` que no crece) dejan el campo `aria-invalid` sin POST.
  - **CM4** añadir y quitar clave, con el desplazamiento de `t` al quitar la 1. «Quitar» está desactivado con una sola clave.
  - **CM5** reproducir, parar e ir a una pose: los cuerpos exactos de los POST. `#cam-play` está desactivado sin selección.
  - **CM6** los textos de `[data-cam-juego]` para los seis casos de §3.1.
  - **CM7** nombre y borrar: el nombre vacío no se manda, y borrar manda `camera.delete` y vacía la selección.
  - **CM8** texto hostil: un nombre de cámara con HTML se ve literal y no inyecta nada.
- `studio.e2e.cjs` S1: el panel `camaras` deja de ser un hueco. Es la misma inversión que hizo F6-web parte 2 con `historial` e `ia`.

## 5. Lanes

- **Lane única (Grok):** §2 y §3. Ficheros: `app/backend/camera_live.py` y `app/backend/server.py` (solo `key`), y `app/web/src/` (sobre todo `panels/Placeholders.tsx` o un panel nuevo `panels/CamerasPanel.tsx`, `App.tsx`, `panels/HierarchyPanel.tsx`, `panels/PropertiesPanel.tsx`, `store.ts` y `types.ts`). No toca `app/tests/` ni `app/web/e2e/`, y no añade dependencias.
- R25 y R20: nada fuera de eso. Lo raro de alrededor va a `bugs.md`.
- Gate en la nube: el offline entero más `DSBX_GUION=camaras`. Después, mutaciones `plans/f4web-mutants.py`.
