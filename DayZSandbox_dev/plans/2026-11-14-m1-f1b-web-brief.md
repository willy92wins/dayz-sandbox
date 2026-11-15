# F1b-web sin juego: sesión del navegador, web servida por el backend y vista mínima de la cola

2026-11-14 · tarea **F1b-web**, rama `claude/f1b-web` (desde `main` `577eb85`) · spec de implementación (R25) de la parte de F1b que no depende del bridge ni del juego: [plan v2](2026-10-26-m1-cine-v2.md) F1 (líneas 88 y 90), decisiones #1, #22, #23, #24, #29 y #32, y [F1a](2026-11-11-m1-f1a-brief.md) §0 (línea 19) · contrato: `DayZSandbox_dev/product-spec.md`, D2 y E1 · v1.4: revisión de Sol cerrada en la ronda 4 (VERDE desde la ronda 3, 0 bloqueantes), con los importantes y menores que quedaban arbitrados y aplicados (§11).

**Por qué ahora.** El plan (#29) hace F0 en paralelo con la parte sin juego de F1, y F1a dejó para F1b dos piezas que no dependen de S-puente: la vista mínima de la web y su sesión de navegador con cookie y CSRF (F1a §0, línea 19). Guillermo pidió adelantar trabajo en paralelo porque M1 va retrasado.

**Qué hay ya.** `app/backend/server.py` (F1a y F1-co): credenciales Bearer de persona e IA (`server.py:224-230`), Host y Origin en cada petición (`server.py:257-270`), `POST /api/apply` que deja una orden `pendiente` (`server.py:212-222`) y el SSE `GET /api/events` con `Last-Event-ID` y `snapshot` (`server.py:184-200`, `406-436`). 93 pruebas en verde [V 2026-11-14, 14,8 s]. Este brief **añade**; una línea de F1a o F1-co que no haga falta tocar no se toca (R20).

**Proceso.** Dos tandas en serie (§9): primero el backend, después la web y su prueba de navegador sobre ese backend, para que el worker de la web corra la prueba entera él mismo. El orquestador junta, vuelve a medir y hace el commit. Sol revisa este brief; el código lo revisa el orquestador, de otra familia que los workers, con las mutaciones de X1 y X2; Sol revisa F1 entera al cerrar la fase (R21), como en F1a y F1-co. Un hallazgo fuera de alcance va a `bugs.md`.

## 0. Qué es y qué no

Es:
- la **sesión del navegador**: entrar con la clave de persona, cookie `HttpOnly` de sesión, token CSRF en todo lo que muta y `Origin` obligatorio en lo que muta con cookie (#22, E1);
- la **web servida por el backend**: el build de `app/web` en `/` (#1, #32);
- la **vista mínima de la cola**: cada orden con su estado, su edad y su origen, alimentada por el SSE que ya existe, y un único botón que muta, «Aplicar», que crea la orden (#23, #29, D2);
- el **origen** y la **edad** de cada orden en el backend (#23: «cada dato lleva su edad y su origen»);
- una **prueba de navegador con Playwright** de todo lo anterior.

No es:
- el bridge, los peers, el mod falso, el catálogo del mod, la cola acotada, el TTL por orden ni las transiciones reales de estado: F1b-bridge, después del veredicto de S-puente (F1a §0, línea 18; plan F1, línea 89);
- el resto de la web: mapa, árbol, inspector, biblioteca, Dockview, atajos, pestaña IA, avisos de la co-edición y préstamo desde el navegador (F6, #29; F1-co §0, línea 18);
- cerrar sesión, caducidad por tiempo ni HTTPS (plan §7, línea 228).

Trazabilidad (R20): §2 sale de #22, E1 e I4; §3, de #1, #22 y #32; §4, de #23; §5, de #23, #29, D2 y H1; §6, de D2, E1 y #24 (códigos de salida). Lo que no trace a esto no entra.

## 1. Entorno y fronteras

- **Backend**: Python 3.14 en `C:\Python314\python.exe`, **solo biblioteca estándar**, pruebas con `unittest`, como F1a §1.
- **Web**: TypeScript con React y Vite (#1). Node `v24.14.1` y npm `11.11.0` en el PC [V 2026-11-14]. Dependencias fijadas en §5.1, nada más.
- **Playwright** no es dependencia de la web: la prueba usa el que ya hay en `C:\tmp\dsbx-ui-astra-revision2` (Playwright `1.63.0`) con `NODE_PATH=C:\tmp\dsbx-ui-astra-revision2\node_modules` y `PLAYWRIGHT_BROWSERS_PATH=C:\tmp\dsbx-ui-astra-revision2\pw`; sin esa segunda variable, Chromium no arranca. `NODE_PATH` no aplica a `import` de ESM, así que el guion es CommonJS (`.cjs`, `require("playwright")`).
- La suite de Python **no necesita Node**: las pruebas de estáticos usan una carpeta temporal con ficheros falsos.
- Los comandos se lanzan desde `DayZSandbox_dev/` (#32), en PowerShell 5.1 o en Git Bash, con la sintaxis de §7. Solo 127.0.0.1. Ninguna clave, `sid` ni `csrf` en logs, salidas ni mensajes de error. UTF-8 sin BOM y finales LF.
- **R25.** Sin clases base, registros, capas ni librerías que este brief no pida.

## 2. La sesión del navegador (`server.py`)

### 2.1 Endpoints

| Método y ruta | Credencial | Cuerpo | Respuesta |
|---|---|---|---|
| `POST /api/session` | ninguna: es la entrada | `{key}` | `key` igual a `human_key` → 200 `{ok: true, csrf}` y `Set-Cookie`. Cualquier otra cosa (sin `key`, `key` que no es texto, la clave de la IA o una mala) → 401 `unauthorized`, sin cookie ni sesión nueva y sin decir qué falló (F1a §5.2) |
| `GET /api/session` | cookie | — | sesión viva → 200 exactamente `{ok: true}`, **sin** `csrf`; si no → 401 |

- Cookie: `dsbx_session_<port>=<sid>; HttpOnly; SameSite=Strict; Path=/`. Sin `Max-Age` ni `Expires`: dura lo que el navegador. Sin `Secure`: es HTTP en loopback y HTTPS está fuera de M1 (plan §7). El puerto va en el nombre porque las cookies no distinguen puertos (RFC 6265 §8.5): dos backends en 127.0.0.1 no se pisan la sesión.
- `sid` y `csrf` salen de `secrets.token_urlsafe(32)`, nuevos en cada entrada; un `sid` que traiga la petición nunca se reutiliza.
- **El `csrf` solo viaja en la respuesta de la entrada.** La página lo guarda en `localStorage`, que es de su origen (puerto incluido), y lo lee en cada petición que muta. Una cookie capturada por otro servicio en otro puerto de 127.0.0.1 no basta para mutar: con ella sola no se obtiene el `csrf`, y un `Origin` falsificado no sustituye al token (P6). Con ella sí se puede leer; ver §10.
- Las sesiones viven en memoria del `Backend` como `Backend.sessions: dict[sid, {"csrf": str}]`, bajo un candado propio, distinto de `store.lock`. Mueren con el proceso: reiniciar el backend deja la cookie vieja sin sesión → 401 (la «sesión vieja» de E1).
- Solo la clave de **persona** abre sesión: la IA no aplica ni ejecuta (H1, I4) y sigue entrando solo por Bearer. Por eso el `Backend` no arranca con `human_key` igual a `ai_key` ni con una clave vacía: `Backend.__init__` lanza `ValueError`, y `main` sale con 2 y un mensaje sin las claves. `load_config` ya genera claves distintas; solo un `backend.json` editado a mano puede chocar.

### 2.2 Cómo se autentica cada petición

1. Host y Origin como hoy (`server.py:259-265`), en **toda** petición, estáticos incluidos.
2. `/` y `/assets/...` → estático (§3), sin credencial.
3. `POST /api/session` → la entrada de §2.1, sin credencial.
4. El resto de `/api/...`:
   - si trae `Authorization`, manda el Bearer de F1a (`server.py:224-230`), y uno inválido → 401 aunque haya una cookie válida;
   - sin `Authorization`, una cookie `dsbx_session_<port>` de una sesión viva → autor persona, el mismo `HUMAN` = `{"role": "human", "id": "web"}` (`server.py:29`). Con otras cookies, cookies mal formadas o el nombre repetido en la cabecera `Cookie`, basta con que una de ellas sea una sesión viva;
   - si no → 401.

### 2.3 CSRF y Origin en lo que muta

Toda petición `POST` autenticada por cookie (todas menos la entrada) exige, **antes de leer el cuerpo**:
- `Origin` presente e igual a `http://127.0.0.1:<port>` o `http://localhost:<port>`; sin `Origin` → rechazo;
- `X-CSRF-Token` igual al `csrf` de **esa** sesión, comparado con `hmac.compare_digest`.

Si falla cualquiera → 403 `csrf_failed` (código nuevo en `STATUS`, `server.py:32-40`) y 0 efectos. Con Bearer no cambia nada: un navegador no pone esa cabecera por su cuenta. Un `GET` con cookie no pide token, porque no muta. Sin cabeceras CORS ni `OPTIONS`: un preflight de otro origen recibe el 501 de `BaseHTTPRequestHandler` y el navegador bloquea la petición.

### 2.4 Secretos (#22)

- Ninguna respuesta lleva `human_key`, `ai_key` ni ninguna otra `*_key` de `backend.json`. El JavaScript solo recibe `csrf`, así que la clave de los peers que añada F1b-bridge tampoco le llegará; W6 recorre todas las `*_key` de la configuración y la cubre sin tocar la prueba.
- `log_message` (`server.py:237-239`) solo escribe la línea de petición: ni el cuerpo de la entrada, ni `Cookie`, ni `X-CSRF-Token`.
- Toda respuesta JSON y estática lleva `X-Content-Type-Options: nosniff`, para que otra página no pueda cargar un JSON como script.

## 3. La web servida por el backend (`server.py`)

- `Backend(..., web_root=None)`: carpeta del build. `load_config` (`server.py:439-460`) gana el valor por defecto `"web": "app/web/dist"`, relativo a `DayZSandbox_dev/` como `scene` y `catalog`, y no reescribe un `backend.json` existente por él. `main` se lo pasa al `Backend`.
- Se mira solo la ruta, sin la consulta (`urlsplit`):
  - `GET /` → `<web_root>/index.html`, `text/html; charset=utf-8`;
  - `GET /assets/<nombre>` con `<nombre>` que case `^[A-Za-z0-9][A-Za-z0-9._-]*\.(js|css)$` → `<web_root>/assets/<nombre>`, con `text/javascript; charset=utf-8` o `text/css; charset=utf-8`;
  - cualquier otra ruta fuera de `/api/` → 404 aunque el fichero exista: nada de `..`, subcarpetas, `%2e` ni otras extensiones.
- Cabeceras: `Cache-Control: no-cache` y `nosniff`; el HTML, además, `Content-Security-Policy: default-src 'self'; frame-ancestors 'none'`, para que una web ajena no pueda enmarcar la app y arrancarle un clic (#22).
- Sin `web_root` o sin `index.html`, `GET /` da 503 `text/plain` con `Web sin construir: en app/web, npm ci --ignore-scripts y después npm run build`. El backend arranca igual.

## 4. El origen de cada orden (`server.py`)

`apply` (`server.py:212-222`) crea la orden con `"origin": "backend"`, que viaja sin más cambios en `op.state` y en `snapshot.ops` (`server.py:195-198`). Es el origen de #23, quién produjo el dato. En F1b-web es el único valor; F1b-bridge pondrá el del peer que confirme (el prototipo usa «servidor» y «tu juego», `ui/prototipo/estudio.html:1169`). `at_ms` sigue siendo el instante en que se fijó el estado.

Y la edad, que #23 también pide que lleve cada dato: `apply` anota en `Backend.op_mono[op_id]` el instante de `clock()`, el reloj monotónico que el `Backend` ya recibe (`server.py:54`, el mismo de las leases), y el `snapshot` lleva en cada orden `age_ms` = `(clock() − op_mono[op_id]) × 1000`, entero. Así, una página que abre o recarga no depende del reloj de pared para saber cuánto tiene el dato. `op.state` no lleva `age_ms`: se emite en el instante del cambio y el anillo lo guarda serializado, así que al repetirse tras una reconexión quedaría viejo. Quien cambie el estado de una orden (hoy solo `apply`; el arnés en las pruebas, y F1b-bridge después) actualiza `op_mono` a la vez que `at_ms`.

## 5. La web (`app/web`)

### 5.1 Dependencias [EXACT]

`app/web/package.json`, ya escrito por el orquestador con su `package-lock.json`:

```json
{
  "name": "dsbx-web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "build": "tsc --noEmit -p tsconfig.json && vite build"
  },
  "dependencies": {
    "react": "19.2.3",
    "react-dom": "19.2.3"
  },
  "devDependencies": {
    "@types/react": "19.2.7",
    "@types/react-dom": "19.2.3",
    "typescript": "5.9.3",
    "vite": "6.4.5"
  }
}
```

- Versiones publicadas entre 2025-09-30 y 2026-10-21 [V `npm view <paquete> time`, 2026-11-14]. Vite iba en 6.4.2 hasta que `npm audit` marcó alta `vite <=6.4.3`: siete avisos, todos del servidor de desarrollo, que aquí no se usa (solo `vite build`). Aun así se sube a 6.4.5, el parche más reciente con más de dos semanas, y `npm audit` da 0 vulnerabilidades. Se instalan con `npm ci --ignore-scripts`. `package-lock.json` se versiona; `node_modules/` y `dist/` no (`app/web/.gitignore`).
- Nada más: sin `@vitejs/plugin-react` (el JSX lo compila esbuild con `"jsx": "react-jsx"` en `tsconfig.json`), sin router, sin librería de estado y sin framework de CSS.
- `npm run build` deja `dist/index.html` y `dist/assets/*.js|*.css`, con nombres que casen la expresión de §3. TypeScript en modo `strict`. `index.html` sin scripts ni estilos en línea, por la CSP de §3.
- Medido el 2026-11-14 en una copia aparte: `npm ci --ignore-scripts --offline` desde la caché, `tsc` y `vite build` salen 0 con un componente TSX de prueba, y el build deja un único `<script type="module" crossorigin src="/assets/index-<hash>.js">`.

### 5.2 Comportamiento

1. **Al cargar**: sin `csrf` en `localStorage`, el formulario de entrada. Con él, `GET /api/session`: con 200, la vista de la cola; con 401, el formulario. Un 401 nunca borra el `csrf` guardado: `localStorage` es compartido entre pestañas, y la respuesta vieja de una pestaña no puede invalidar la entrada que otra acaba de hacer (P9a y P9b). El `csrf` solo se sustituye al entrar; uno que ya no casa con la cookie acaba en 403 `csrf_failed` y en el formulario (punto 5).
2. **Entrada**: un campo de contraseña, «Clave de persona (`human_key` de `backend.json`)», y el botón «Entrar», que hace `POST /api/session`. Con 200 guarda el `csrf` en `localStorage`, vacía el campo y abre la vista; con 401 enseña «Clave no válida». La clave no se guarda en ningún sitio (ni `localStorage`, ni `sessionStorage`, ni la consola).
3. **La cola** se alimenta solo de `GET /api/events` (`EventSource` del mismo origen, que manda la cookie):
   - `snapshot`: sustituye todas las filas por `ops` y guarda `doc_id`, `rev` y `hash`;
   - `op.state`: crea o actualiza la fila de su `op_id`;
   - `scene.commit`: actualiza `rev` y `hash`;
   - `ai.state`, `lease.state` y `apply.request` se ignoran en F1b-web (F6).

   Una fila por orden, la más nueva arriba (por el número de `op-<n>`), con cinco columnas:
   - **Orden**: el `op_id`.
   - **Revisión**: `rev` y los 8 primeros caracteres del `hash`.
   - **Estado**: Pendiente, Ejecutando, Aplicado, Observado, Fallido o Parcial (#23, D2; los textos de `ui/prototipo/estudio.html:851`). Cualquier otro valor se enseña como «Desconocido (<valor>)», nunca como uno de los seis.
   - **Edad**: cada fila guarda un ancla, la edad que tenía el dato al recibirlo y el instante `performance.now()` de ese momento, y enseña `edad_al_recibir + (performance.now() − instante)`, como «N s» hasta 59 s, «N min» hasta 59 min y «N h» después, recalculada cada segundo aunque no llegue nada, para que un observador congelado se vea viejo (D2). El ancla se decide en este orden, el primero que aplique:
     1. si la fila ya tiene ancla para el mismo `op_id` y el mismo `at_ms`, la conserva: un `snapshot` de reconexión no reinicia lo contado. Pero si ese `snapshot` trae un `age_ms` mayor que la edad que la fila enseña, sube el ancla a ese `age_ms`: la edad se corrige al alza, nunca a la baja (por ejemplo, si un `snapshot` anterior llegó con retraso);
     2. si el dato llega en un `snapshot`, `edad_al_recibir` = su `age_ms`, que mide el backend con su reloj monotónico (§4);
     3. si llega en un `op.state`, `edad_al_recibir` = `max(0, Date.now() − at_ms)`; pero si `Date.now()` está más de 2 s por detrás de `at_ms` (el reloj del PC retrocedió), no hay con qué medirla y la fila enseña «Edad desconocida» en vez de empezar en 0.

     Así la edad de un dato sin cambios nunca baja dentro de una página, y una página que abre o recarga la toma del backend y no del reloj de pared (P2b).
   - **Origen**: el campo `origin` tal cual, o «—» si falta.

   Ninguna fila nace ni cambia por la respuesta de un `POST`, solo por eventos del SSE: un 200 no es un estado (D2, «nada pendiente aparece como hecho»; plan F6, línea 143).
4. **Conexión**: un indicador «Conectado» o «Reconectando…».
   - Tras un corte de red, `EventSource` reconecta solo (`readyState` CONNECTING): las filas se quedan y su edad sigue creciendo.
   - Si la conexión queda cerrada (CLOSED, por ejemplo un 401 al reconectar después de reiniciar el backend), la web pide `GET /api/session`. Con 401, el formulario con «Sesión caducada: vuelve a entrar»; si no, abre un `EventSource` nuevo, que empieza por un `snapshot`.
5. **«Aplicar rev N»**: `POST /api/apply` con el `doc_id`, la `rev` y el `hash` que la vista enseña, porque se aprueba lo que se ve (H1), con `credentials: "same-origin"` y `X-CSRF-Token` leído de `localStorage` en ese momento.
   - Deshabilitado mientras no haya `snapshot` o haya un `POST` en vuelo.
   - Un rechazo se enseña con su `code` y su `msg` (por ejemplo `stale_apply`); un 401 o un 403 `csrf_failed` llevan al formulario con «Sesión caducada».

### 5.3 Aspecto

Una sola pantalla, sin paneles. Colores y textos de estado del prototipo aprobado: fichas de `ui/prototipo/estudio.html:212-213`, con los tokens oscuros de `:9-16` y los claros de `:26-33`, según `prefers-color-scheme`. El prototipo es referencia visual, no código que portar.

## 6. Prueba de navegador (Playwright)

### 6.1 Arnés (`app/tests/e2e_web.py`)

Solo biblioteca estándar. El nombre no empieza por `test`, así que `unittest discover` no lo recoge y la suite sigue sin Node.

- **Precondiciones**: sin `node`, sin `NODE_PATH` que resuelva `playwright`, sin `PLAYWRIGHT_BROWSERS_PATH` o sin `app/web/dist/index.html`, sale con 2 (INCONCLUSO, #24) y una línea que dice qué falta.
- **Montaje**: una carpeta temporal para la escena (el `Store` la crea desde la fixture) y el log, claves distintas generadas en memoria para la corrida, y `Backend(..., port=0, web_root="app/web/dist", log=<fichero temporal>)` en un hilo.
- **Servidor ajeno**: un `http.server` **real** del arnés en otro puerto de 127.0.0.1 sirve `/evil.html` (§6.2, P6) con el `doc_id`, la `rev` y el `hash` actuales dentro, y guarda las cabeceras `Cookie` que le llegan. Tiene que ser real: con una página servida con `page.route`, Chromium no llega a mandar sus peticiones [V 2026-11-14: 0 peticiones en el servidor; con un servidor real en otro puerto llegan el `fetch` y el formulario, los dos con la cookie `SameSite=Strict` y `Origin: http://127.0.0.1:<otro puerto>`].
- **Guion**: lanza `node app/web/e2e/queue.e2e.cjs` con `DSBX_URL`, `DSBX_HUMAN_KEY` y `DSBX_EVIL_URL` en el entorno, nunca en los argumentos ni en la salida.
- **Órdenes del guion al arnés**: una línea JSON por la salida del guion y la respuesta en una línea por su entrada; cualquier otra línea es log. Solo existen en el arnés: nada de endpoints de depuración (F1a §5.4). `store.lock` envuelve solo las lecturas y los cambios directos del estado del backend: ninguna orden hace peticiones HTTP ni llama a `shutdown` con el candado tomado, porque los hilos del servidor lo necesitan para responder. Toda espera tiene tope: 10 s por petición HTTP del arnés y 5 min para el guion entero.
  - `{"cmd": "op_state", "op_id", "state", "origin"}`: fija `state`, `origin` y `at_ms` = ahora en `backend.ops[op_id]` y `backend.op_mono[op_id]` = `clock()`, emite `op.state` y responde `{"ok": true, "at_ms"}`;
  - `{"cmd": "count_ops"}` → `{"ok": true, "n": <órdenes en backend.ops>}`;
  - `{"cmd": "log_count", "needle": <texto>}` → `{"ok": true, "n": <líneas del log del backend que lo contienen>}`;
  - `{"cmd": "drop_sse"}`: cierra todas las conexiones SSE del backend sin tocar las sesiones → `{"ok": true}`;
  - `{"cmd": "replay_stolen"}`: con la cookie `dsbx_session_<port>` que recibió el servidor ajeno, el arnés hace desde Python, fuera del navegador, `GET /api/session` y `POST /api/apply` con `Origin: http://127.0.0.1:<port>` falsificado, un cuerpo válido y un `X-CSRF-Token` inventado → `{"ok": true, "captured", "session_status", "session_keys", "apply_status", "apply_code", "ops_delta"}`, sin devolver nunca el `sid`. Las órdenes se cuentan antes y después bajo el candado; las dos peticiones van fuera de él;
  - `{"cmd": "restart"}`: `backend.shutdown()` y un `Backend` nuevo en el mismo puerto, con las mismas claves y la misma escena → `{"ok": true}` [V 2026-11-14: Windows deja reabrir el puerto en 0,001 s con una conexión SSE abierta al cerrar].
- **Al terminar**: ni el log del backend ni la salida del guion contienen las claves ni ningún `sid` o `csrf` emitido (el arnés los lee de `Backend.sessions` antes de cada reinicio y al final).
- **Salida**: 0 PASA; 1 FALLA (falla un paso o aparece un secreto); 2 INCONCLUSO (precondición).

### 6.2 Guion (`app/web/e2e/queue.e2e.cjs`)

Chromium sin cabeza. Cada paso falla si no observa lo que dice: nada de `try/catch` que se trague un fallo. Medido el 2026-11-14 con este Chromium: tras un 401, `EventSource` queda CLOSED sin reintentar; su `GET` del mismo origen lleva la cookie y no lleva `Origin`; `page.route` intercepta el `EventSource`, pero no una conexión ya abierta; y tras `unroute`, `EventSource` reenvía el último `id` visto. El reloj falso de Playwright es de todo el contexto, así que P2b va en un contexto propio, con su propia entrada; el resto comparte otro contexto, con la página de la app de P1 abierta de principio a fin.

| # | Pasos | Se espera |
|---|---|---|
| P1 entrada | Abrir `/`. Entrar con una clave mala y luego con la buena | Formulario; «Clave no válida» y ninguna cookie `dsbx_session_<port>` en `context.cookies()`; con la buena, la vista y la cookie con `httpOnly: true` y `sameSite: "Strict"`. `localStorage` guarda el `csrf`; ni él, ni `sessionStorage`, ni `document.cookie` contienen la clave ni el valor de la cookie |
| P2 pendiente que envejece | «Aplicar rev N» y esperar 3 s sin eventos | Fila `op-1` Pendiente con origen `backend`; a los 3 s, edad ≥ 3 s y sigue Pendiente. Nunca enseña Aplicado ni Observado: sin bridge, nada pasa de pendiente (D2) |
| P2b reloj que retrocede | Contexto propio con `clock.install()` antes de abrir `/`; entrar y «Aplicar» (orden K). (0) Parar el reloj de la página (`clock.pauseAt`), esperar 4 s reales y forzar una reconexión que traiga un `snapshot` (como en el paso 3; si la web espera con un temporizador antes de reabrir el `EventSource`, avanzar el reloj lo justo, 1 s como mucho). (1) `runFor(3000)`. (2) `setSystemTime(ahora − 1 h)` y `runFor(2000)`. (3) Una reconexión que traiga un `snapshot` (por ejemplo, una ruta sobre `/api/events` que sirve un 503 una vez y se quita, más `drop_sse`). (4) `op_state` de K en el arnés: su `at_ms` nuevo queda 1 h por delante del reloj de la página. (5) Esperar 2 s reales, `setSystemTime(at_ms + 500)` con el `at_ms` que devolvió el arnés, y recargar | (0) La edad sube a ≥ 3 s aunque la página no haya contado ese tiempo: el ancla se corrige al alza con el `age_ms` del backend; (1) ≥ 3 s más que tras (0); (2) ≥ 2 s más; (3) no menos que antes; (4) «Edad desconocida»; (5) la edad sale del `age_ms` del backend: al menos 1 s y nunca «0 s», aunque el reloj de la página esté a 0,5 s del dato. Medido: con `install`, `setSystemTime` mueve `Date` y no `performance.now()`, y `runFor` dispara los `setInterval` |
| P3 los seis estados | Inyectar `ejecutando`/`backend`, `aplicado`/`servidor`, `observado`/`servidor`, `parcial`/`servidor` y `fallido`/`backend`; luego `hecho` | Cada etiqueta con su origen, y la edad vuelve a < 2 s tras cada inyección; `hecho` → «Desconocido (hecho)» |
| P4 sin estado optimista | Instalar `page.route` sobre `/api/events` y **recargar la página**, para que no quede abierta ninguna conexión real. La ruta sirve una vez un `snapshot` falso con el `doc_id`, la `rev` y el `hash` reales (leídos antes con `page.request`), una orden ficticia `op-9999`, `id: 999999999` (mayor que cualquier `seq` de la corrida: la reconexión real recibirá un `snapshot` completo y no una repetición que se salte eventos) y `retry: 60000` (nada de reconexiones que borren filas mientras se observa). «Aplicar». Después, `unroute` y recargar | `op-9999` a la vista, lo que acredita que se pintó el falso. El `POST` recibe 200 con su `op_id` y `count_ops` sube 1, pero en 3 s no aparece la fila de esa orden. Tras recargar sin la ruta, esa fila está Pendiente y `op-9999` ya no |
| P5 CSRF en el navegador | Desde la página de la app, `fetch("/api/apply", {method: "POST"})` con un cuerpo válido, sin `X-CSRF-Token` y luego con uno malo | 403 `csrf_failed` las dos veces; `count_ops` no cambia y no aparece ninguna fila |
| P6 web ajena | En **otra página** del mismo contexto, con la de la app abierta y conectada, navegar a `DSBX_EVIL_URL`. Su script hace un `fetch` POST a `/api/apply` del backend con `credentials: "include"`, `Content-Type: text/plain` y un cuerpo JSON válido, y envía un formulario `text/plain` cuyo cuerpo también es JSON válido (nombre `{"doc_id":…,"rev":…,"hash":…,"x":"` y valor `"}`). Luego `replay_stolen` | El log del backend tiene 2 líneas más con `"POST /api/apply HTTP/1.1" 403`, así que las dos peticiones llegaron y se rechazaron; `count_ops` no cambia. `replay_stolen`: `captured: true` (el navegador mandó la cookie a otro puerto), `GET /api/session` 200 con `session_keys` = `["ok"]`, `apply` 403 `csrf_failed` y `ops_delta` 0 |
| P7 sesión vieja | Con la página de la app en «Conectado», `restart` en el arnés | En esa página, en menos de 15 s, el formulario con «Sesión caducada»; al volver a entrar, la vista arranca del `snapshot` del backend nuevo y `op-1` ya no sale |
| P8 nada de secretos | Leer `GET /api/session`, `/` y cada `/assets/*` que cite el HTML; recoger la consola de toda la corrida | El cuerpo de la sesión es exactamente `{"ok": true}`; ni el HTML ni los assets contienen ninguna clave; ningún mensaje de consola de la CSP (`Content Security Policy` o `Refused to`) |
| P9a dos pestañas, recuperación | Dos páginas de la app, A y B, en el mismo contexto, con sesión y conectadas. Una ruta en A que retiene su `GET /api/session`. `restart`: la reconexión del SSE de A provoca esa consulta, así que se espera a capturarla después del reinicio, no antes. B vuelve a entrar; solo entonces la ruta sirve a A un 401 | A enseña el formulario; B sigue en la vista y su «Aplicar» da 200 y una fila nueva: el 401 viejo de A no borró el `csrf` que B acababa de guardar |
| P9b dos pestañas, carga inicial | Como P9a, pero la consulta retenida es la de la carga inicial: con la ruta ya puesta, recargar A y esperar a capturar su `GET /api/session`; después `restart`, B vuelve a entrar y solo entonces la ruta sirve a A un 401 | Lo mismo que en P9a |

## 7. Aceptación (R26)

El gate es **un solo comando**, lanzado desde `DayZSandbox_dev/`: corre la suite, el build y el arnés en ese orden, se detiene en el primer paso que falle y sale con su código. Pasa si sale 0. Así nunca se prueba en el navegador un `dist` viejo después de un build fallido. En **PowerShell 5.1**:

```powershell
powershell -NoProfile -Command { & 'C:\Python314\python.exe' -m unittest discover -s app/tests -t app -v; if ($LASTEXITCODE) { exit $LASTEXITCODE }; Push-Location app/web; npm.cmd ci --ignore-scripts; if ($LASTEXITCODE) { exit $LASTEXITCODE }; npm.cmd run build; if ($LASTEXITCODE) { exit $LASTEXITCODE }; Pop-Location; $env:NODE_PATH = 'C:\tmp\dsbx-ui-astra-revision2\node_modules'; $env:PLAYWRIGHT_BROWSERS_PATH = 'C:\tmp\dsbx-ui-astra-revision2\pw'; & 'C:\Python314\python.exe' app/tests/e2e_web.py; exit $LASTEXITCODE }
```

En **Git Bash**:

```bash
/c/Python314/python.exe -m unittest discover -s app/tests -t app -v && (cd app/web && npm ci --ignore-scripts && npm run build) && NODE_PATH='C:\tmp\dsbx-ui-astra-revision2\node_modules' PLAYWRIGHT_BROWSERS_PATH='C:\tmp\dsbx-ui-astra-revision2\pw' /c/Python314/python.exe app/tests/e2e_web.py
```

Medido el 2026-11-14 con un primer paso que sale 7: las dos formas devuelven 7 sin seguir; con el segundo paso fallando, devuelven su código. En PowerShell, el código queda en `$LASTEXITCODE` al volver.

La suite incluye las 93 de antes **sin tocarlas** más las nuevas, sin fallos ni pruebas saltadas, en menos de 3 minutos. Las pruebas nuevas del backend van en `app/tests/test_server_web.py`, con el `Env` y el `Sse` de `test_server.py` si le sirven. Cada fila es al menos un caso con su positivo y su negativo.

| # | Positivo | Negativo (el defecto que detecta) |
|---|---|---|
| W1 entrada | Clave de persona → 200 `{ok, csrf}` y `Set-Cookie` con nombre `dsbx_session_<port>`, `HttpOnly`, `SameSite=Strict` y `Path=/`; `GET /api/session` con esa cookie → 200 y exactamente `{"ok": true}` | Clave mala, sin `key`, `key` que no es texto y **la clave de la IA** → 401, sin `Set-Cookie` ni sesión nueva; dos entradas dan dos `sid` y dos `csrf` distintos; un `sid` puesto por el cliente antes de entrar no se reutiliza |
| W2 cookie | Cookie, `Origin` bueno y `X-CSRF-Token` → `POST /api/apply` 200 y una orden; `GET /api/scene` y `GET /api/events` con la cookie → 200; cabecera `Cookie` con basura y la sesión → 200 | Sin token, con un token malo o con el de otra sesión, sin `Origin`, o con `Origin` `http://evil.test` o `http://127.0.0.1:<otro puerto>` → 403 y 0 órdenes, también en `ops`, `undo`, `ai/pause` y `lease`; cookie de una sesión que no existe → 401; Bearer malo con una cookie buena → 401 |
| W3 Bearer | Las 93 pruebas de F1a y F1-co pasan igual, sin token CSRF | — |
| W4 estáticos | `/` → `index.html` con la CSP de §3, `nosniff` y `no-cache`; `/assets/a-1.js` y `/assets/a-1.css` con su tipo | Con ficheros centinela que **existen** (`<web_root>/otra`, `<web_root>/assets/x.map`, `<web_root>/assets/sub/x.js` y un `secreto.txt` fuera de `web_root`): `/otra`, `/assets/x.map`, `/assets/sub/x.js`, `/assets/../../secreto.txt` y `/assets/%2e%2e/%2e%2e/secreto.txt` → 404 sin el contenido del centinela; Host `evil.test` en `/` → 403; sin build → 503 con el aviso, y el backend arranca |
| W5 origen y edad | `apply` → `op.state` y `snapshot.ops` con `origin: "backend"`; con un `clock` falso, una orden creada en t y un `snapshot` en t + 5,5 s → `age_ms` = 5500 | `op.state` no lleva `age_ms`; mover el reloj de pared no cambia `age_ms` |
| W6 secretos | — | Tras entrar, aplicar y leer el SSE, el log no contiene ninguna `*_key`, ningún `sid` ni ningún `csrf`; ninguna respuesta contiene una `*_key`; las respuestas de `/api/session` solo traen `ok` y, la de la entrada, `csrf` |
| W7 claves iguales | Claves distintas → arranca | `Backend` con `human_key` igual a `ai_key`, o con una vacía → `ValueError`; `server.py --config` con las dos iguales → sale con 2 sin escuchar y sin imprimirlas |
| P1-P9b | §6.2 con el arnés de §6.1 | §6.2 |
| X1 antitautología | — | El orquestador corre `test_server_web.py` contra un `server.py` (a) sin comparar el token CSRF, (b) sin exigir `Origin` en los `POST` con cookie, (c) sin `HttpOnly`, (d) que abre sesión con la clave de la IA, (e) que sirve cualquier fichero de `web_root`, (f) cuyo `GET /api/session` devuelve el `csrf`, (g) que acepta claves iguales y (h) cuyo `age_ms` sale del reloj de pared: cada uno tiene que hacer fallar al menos una prueba |
| X2 antitautología | — | El orquestador construye la web (a) creando la fila con la respuesta 200 de «Aplicar», (b) calculando la edad solo al llegar un evento, (c) con la edad `max(0, Date.now() − at_ms)` recalculada cada segundo, (e) sin la regla de la edad «desconocida», (f) borrando el `csrf` guardado con cualquier 401, (g) borrándolo solo con el 401 de la carga inicial (h) tomando la edad de un `snapshot` del reloj de pared en vez de `age_ms` y (i) conservando el ancla sin subirla con un `age_ms` mayor: P4, P2, P2b (2), P2b (4), P9a, P9b, P2b (5) y P2b (0), respectivamente, tienen que fallar. Y corre el guion contra un `server.py` (d) que no exige `Origin` ni token en los `POST` con cookie: P6 tiene que fallar |

## 8. Ficheros

```
DayZSandbox_dev/
  plans/2026-11-14-m1-f1b-web-brief.md   este brief                    [orquestador]
  app/backend/server.py                  §2, §3 y §4                   [F1bw-1]
  app/tests/test_server_web.py           W1-W7                         [F1bw-1]
  app/web/package.json                   §5.1 [EXACT]                  [orquestador]
  app/web/package-lock.json              §5.1, lo genera npm           [orquestador]
  app/web/.gitignore                     node_modules/ y dist/         [orquestador]
  app/web/tsconfig.json, vite.config.ts, index.html                    [F1bw-2]
  app/web/src/...                        §5.2 y §5.3                   [F1bw-2]
  app/web/e2e/queue.e2e.cjs              §6.2                          [F1bw-2]
  app/tests/e2e_web.py                   §6.1                          [F1bw-2]
```

**No se tocan** `store.py`, `validate.py`, `lease.py`, `app/mcp/`, el esquema, las fixtures, el product-spec ni ninguna prueba existente.

## 9. Entrega

| Tanda | Worker | Escribe | Lee |
|---|---|---|---|
| F1bw-1 | Muse (`muse-wonder-1.0`, CLI nativo) | `server.py` (§2-§4) y `test_server_web.py` | este brief, `server.py`, `test_server.py` y `test_server_co.py` |
| F1bw-2 | Muse, sobre F1bw-1 ya revisada | `app/web` salvo los tres ficheros del orquestador, `e2e/queue.e2e.cjs` y `app/tests/e2e_web.py` | este brief, `server.py` ya junto y el prototipo |

Las dos tandas van en serie sobre el worktree del orquestador, así que no hay copias que juntar. El orquestador:
- ya escribió `package.json` y `.gitignore` e instaló las dependencias;
- comprueba con `git status` y `git diff` que cada tanda toca solo sus ficheros y que el diff de `server.py` solo añade lo de este brief;
- corre el gate de §7, X1 y X2 sin fiarse de los recibos;
- si algo no casa, decide contra este brief y devuelve el arreglo al worker que toque;
- hace el commit en `claude/f1b-web`. Push y PR, solo con el visto bueno de Guillermo.

## 10. Fuera de alcance y riesgos

- **F1b-bridge**: peers, handshake, mod falso, catálogo real, cola acotada, TTL por orden, transiciones reales de estado y reconciliación con el registro del mod al reconectar (#10), después del veredicto de S-puente.
- **F6**: el resto de la web (#29). Hasta entonces el prototipo sigue siendo la referencia de la interfaz.
- **Riesgo aceptado: lectura con una cookie capturada.** Las cookies no distinguen puertos: otro servicio en 127.0.0.1, aunque no pueda leer `backend.json` (otro usuario de Windows o un contenedor con el puerto publicado), recibe la cookie si el navegador le pide algo. Con ella puede **leer** la escena y el flujo (`GET /api/scene`, `/api/scene/changes` y `/api/events`), pero no mutar, porque el `csrf` no viaja con la cookie (P6, `replay_stolen`). Leer no ejecuta órdenes (E1), #22 pide CSRF en lo que muta y la escena no lleva secretos. Cerrar también las lecturas obligaría a autenticar el SSE con algo distinto de la cookie, que es justo lo que la cookie resuelve, y queda fuera de F1b-web.
- **Riesgo aceptado: dos entradas casi a la vez en dos pestañas** (C-01 de la revisión del código, §11). La cookie se fija al llegar las cabeceras de la respuesta y el `csrf` al leer su cuerpo. Si en ese intervalo, de milisegundos, otra pestaña completa su propia entrada, pueden quedar la cookie de una sesión y el `csrf` de la otra. El fallo es seguro: «Aplicar» da 403 `csrf_failed` y la web pide la clave otra vez. Serializar las entradas entre pestañas (Web Locks) no tiene prueba determinista en Chromium, así que no entra en F1b-web.
- **Reiniciar el backend pide entrar otra vez**, porque las sesiones viven en memoria. Es el negativo «sesión vieja» de E1; F6 puede suavizarlo.
- **La edad.** En un `snapshot` la da el backend con su reloj monotónico (`age_ms`), así que abrir o recargar la página no depende del reloj de pared, y dentro de una página la edad de un dato sin cambios nunca baja (P2b). Solo un `op.state` sin ancla previa usa el reloj de pared, al recibirlo: en uso normal llega en el instante del cambio, así que da casi 0 con cualquier reloj; si el reloj del PC retrocedió más de 2 s desde el dato, enseña «Edad desconocida». Queda un caso residual: un `op.state` repetido tras una reconexión corta, con el reloj retrasado menos de 2 s en ese intervalo, subestima la edad como mucho en lo que retrocedió el reloj.
- **La cola se pierde al reiniciar el backend** (F1a): el `snapshot` del backend nuevo la vacía en la vista. Reconciliar con el mundo es de F1b-bridge (#10).
- **Dependencias npm.** Los seis paquetes de §5.1 traen sus transitivas (esbuild, rollup y las de Vite): 21 paquetes en total. Van fijadas por `package-lock.json` e instaladas sin scripts.

## 11. Cambios por la revisión

**Ronda 1 de Sol** (`gpt-6.1-sol`, esfuerzo máximo, solo lectura; veredicto UNSOUND con 2 bloqueantes y 5 importantes). El orquestador comprobó cada hallazgo contra el código y con sondas de Chromium antes de aplicarlo; los siete se aplican:

| Hallazgo | Qué cambia |
|---|---|
| F-01 · bloqueante · cookie capturada por otro puerto de 127.0.0.1 y reutilizada fuera del navegador para sacar el `csrf` y aplicar | El `csrf` solo viaja en la respuesta de la entrada y la página lo guarda en `localStorage` de su origen; `GET /api/session` responde `{ok: true}` sin `csrf` (§2.1, §5.2). Nuevos: `replay_stolen` (§6.1), P6 con servidor real y cookie robada, W1 y X1 (f). La lectura con la cookie queda como riesgo aceptado (§10) |
| F-02 · bloqueante · `human_key` igual a `ai_key` daría sesión de persona a la clave de la IA (`server.py:224-230` resuelve a IA, la entrada no) | El `Backend` no arranca con claves iguales o vacías (§2.1); W7 y X1 (g) |
| F-03 · importante · P4 con un SSE ya abierto, y reconexiones que borran una fila optimista | P4 instala la ruta y recarga, un único `snapshot` falso con `op-9999`, `id` alto y `retry: 60000` |
| F-04 · importante · P6 con cuerpos que el backend rechazaría igual sin defensas, y sin acreditar que las peticiones llegaron | Cuerpos JSON válidos, conteo de los 403 en el log (`log_count`) y mutación X2 (d) |
| F-05 · importante · los negativos de W4 pasan porque los ficheros no existen | Ficheros centinela que existen y uno fuera de `web_root` |
| F-06 · importante · un retroceso del reloj deja la edad en 0 | Edad acumulada con `performance.now()` que no baja para el mismo `op_id` y `at_ms` (§5.2); P2b y X2 (c) |
| F-07 · importante · los comandos de §7 no valen en PowerShell 5.1 | Comandos para PowerShell 5.1 (con `npm.cmd`) y para Git Bash |

**Ronda 2 de Sol** (misma sesión; veredicto UNSOUND con 2 bloqueantes y 3 importantes nuevos). Sol da por cerrados F-01 a F-05 y F-07, deja F-06 abierto en parte (es G-04) y no ve bloqueante el riesgo aceptado de §10 contra el texto de #22, E1 y D2. Los cinco nuevos se aplican:

| Hallazgo | Qué cambia |
|---|---|
| G-01 · bloqueante · los comandos imprimían el código y la shell salía 0, así que un fallo pasaba el gate (y el navegador podía probar un `dist` viejo) | Un solo comando que se detiene en el primer fallo y sale con su código, medido en las dos shells (§7) |
| G-02 · bloqueante · `replay_stolen` con `store.lock` tomado se bloquea contra el `apply` del servidor | El candado solo envuelve lecturas y cambios directos; nada de HTTP ni `shutdown` con él; esperas con tope (§6.1). Las sesiones, con un candado propio (§2.1) |
| G-03 · importante · un 401 viejo de una pestaña borraba el `csrf` que otra acababa de guardar | Un 401 no borra el `csrf`; solo se sustituye al entrar (§5.2); P9 y X2 (f) |
| G-04 · importante · al recargar con el reloj atrasado, la edad empezaba en 0 | Edad «desconocida» si el reloj está más de 2 s por detrás de `at_ms` (§5.2); P2b recarga al final; X2 (e) |
| G-05 · importante · P6 sacaba de la app a la página que P7 necesita | P6 en otra página; P7 sobre la de la app, en «Conectado». Además, P2b en un contexto propio, porque el reloj falso es de todo el contexto (nota de Sol) |

**Ronda 3 de Sol** (misma sesión; veredicto SOUND-CON-FIXES con 0 bloqueantes: **VERDE** según el criterio fijado antes de la ronda 1). Sol da por cerrados G-01, G-02, G-03 y G-05 y deja abierto en parte G-04, junto con lo que quedaba de F-06 (es H-01). El orquestador arbitra y aplica los tres que quedan:

| Hallazgo | Qué cambia |
|---|---|
| H-01 · importante · con un retroceso que deja `Date.now()` cerca de `at_ms`, una página que abre o recarga enseña 0 s para un dato viejo; el umbral de 2 s no lo detecta | La edad del `snapshot` la da el backend con su reloj monotónico, `age_ms` (§4, #23: «cada dato lleva su edad»); P2b (5) deja el reloj de la página a 0,5 s del dato y recarga; W5, X1 (h) y X2 (h) |
| H-02 · importante · P9 no cubría el 401 de la carga inicial | P9a (recuperación del SSE) y P9b (carga inicial), con el momento de la captura explícito; X2 (f) y (g) |
| H-03 · menor · precedencia entre conservar el ancla y la regla «desconocida» | Orden explícito: ancla existente, luego `age_ms` del `snapshot`, luego reloj de pared con la regla «desconocida» (§5.2) |

**Ronda 4 de Sol, la última** (misma sesión, contra el commit congelado `9795efd`; veredicto SOUND-CON-FIXES con 0 bloqueantes nuevos). Sol da por cerrados H-01, H-02 y H-03, y **el bucle de revisión se cierra aquí**. Queda un importante, que arbitra y aplica el orquestador:

| Hallazgo | Qué cambia |
|---|---|
| I-01 · importante · un `snapshot` procesado con retraso deja el ancla baja, y conservarla perpetúa el desfase | El ancla se corrige al alza con un `age_ms` mayor, nunca a la baja (§5.2); P2b (0) con el reloj de la página parado; X2 (i) |

**Revisión del código** (el orquestador, de otra familia que los workers, sobre el diff y sin fiarse de los recibos):
- **F1bw-1** (Muse, en una copia con sandbox de ficheros y aprobación activos). Se acepta tal cual. Desviación aceptada: `GET /api/session` también responde 200 `{ok: true}` a un Bearer válido, nunca con `csrf`, así que no cambia nada de §2. X1 de la (a) a la (h): las 8 mutaciones tumban al menos una prueba.
- **F1bw-2** (Muse, en otra copia con sandbox). El orquestador hace tres arreglos:
  - las etiquetas de estado se buscan solo entre las claves propias: un estado `toString` dejaba la celda vacía en vez de «Desconocido»; P3 lo comprueba ahora y X2 (j) lo mata;
  - la consulta de sesión se reintenta si falla por red: sin eso, «Reconectando…» nunca volvía a conectar;
  - la etiqueta del formulario ya no enseña las comillas invertidas.
- Desviaciones aceptadas del arnés: silencia `handle_error` del backend (ruido de Chromium al cerrar conexiones; los pasos siguen fallando por comportamiento) y sale con 1, no con 2, si no puede reabrir el puerto (medido: lo reabre en 0,001 s).
- **Vite** sube de 6.4.2 a 6.4.5 por `npm audit` (§5.1).
- **X2 del orquestador**, sobre una copia: las 11 mutaciones mueren:

  | Mutación | Paso que falla |
  |---|---|
  | (a), como upsert optimista | P4 |
  | (b) | P2 |
  | (c), (e), (h) e (i) | P2b |
  | (d) | P5 |
  | (d) con P5 saltado | P6: los POST de la web ajena dejan de dar 403 |
  | (f) | P9a |
  | (g) | P9b |
  | (j) | P3 |

  La (a) que añade la fila sin mirar si ya existe duplica `op-1` y cae antes, en P3.

**Revisión del código por Sol** (sesión nueva de `gpt-6.1-sol`, esfuerzo máximo y solo lectura, sobre `de5e565`): veredicto SOUND-CON-FIXES, 0 bloqueantes. El orquestador comprobó los cinco hallazgos y reprodujo C-02 y C-03 contra el servidor real. Guillermo decidió arreglar de C-02 a C-05 y aceptar C-01:

| Hallazgo | Qué cambia |
|---|---|
| C-01 · importante · dos entradas casi simultáneas pueden dejar la cookie de una sesión y el `csrf` de otra | Riesgo aceptado y documentado en §10. El fallo es seguro (403 y volver a entrar) |
| C-02 · importante · `discard_body` esperaba sin plazo un cuerpo anunciado que no llega: un POST rechazado retenía su hilo indefinidamente | Drenaje con plazo total (`Backend.drain_s`, 2 s) y cierre de la conexión. Prueba por socket de los tres rechazos (Host, cookie sin token y Bearer malo); X1 (i) |
| C-03 · importante · la clave `"\ud800"` lanzaba una excepción en vez del 401 | `human_key_matches` trata como no válida una clave que no se puede codificar; W1 con `\ud800` y `\udfff`; X1 (j) |
| C-04 · importante · el E2E recogía la consola del navegador sin buscar secretos en ella | Al final del guion, ni la clave ni ninguno de los `csrf` emitidos (5 entradas) aparecen en la consola de toda la corrida; X2 (k) y (l) |
| C-05 · menor · la precondición aceptaba un `NODE_PATH` que Node no resuelve | La precondición pregunta a Node con el mismo `NODE_PATH` y desde la carpeta del guion; un `NODE_PATH` malo da INCONCLUSO (2) |

Ronda 2, sobre los arreglos (`08809dc`): Sol da por cerrados C-02, C-03, C-04 y C-05, y C-01 por bien documentado. Encuentra un hallazgo nuevo en la prueba de C-02:

| Hallazgo | Qué cambia |
|---|---|
| C-06 · importante · la prueba de C-02 daba por buena una respuesta seguida de un timeout, así que no acreditaba el cierre ni la liberación del hilo; y con solo «no llega ningún byte» no distinguía un plazo total de uno renovable | La lectura exige EOF o corte del servidor, nunca un timeout, en menos de 2 s; un caso nuevo manda el cuerpo a goteo (un byte cada 50 ms) y exige el cierre en menos de 1,5 s. X1 (k), plazo renovable, y (l), hilo retenido tras el 403, tumban cada una su prueba |

Ronda 3, sobre `5efac44`: Sol da por corregida la primera mitad de C-06 (un timeout ya no cuenta como cierre) y deja abierta la segunda. La prueba del goteo podía pasar sin que el goteo ocurriera: con X1 (k) y el emisor arrancando 500 ms tarde, o parado 400 ms tras el primer byte, el plazo renovable cerraba en el hueco y la prueba daba PASA. Con el tope de rondas de Sol ya superado (Guillermo, 2026-11-14: «Máximo 2 rondas de Sol»), el orquestador arbitra: aplica el arreglo que propone Sol y lo comprueba con sus dos negativos, sin una ronda más.

| Hallazgo | Qué cambia |
|---|---|
| C-06 (segunda mitad) · importante · el estímulo del goteo no se comprobaba | La prueba registra cada envío y su instante. Un intento solo cuenta si el goteo no se para nunca 0,2 s o más desde las cabeceras hasta el cierre; si no, se repite, y sin ningún intento válido en 3 la prueba falla. Medido: con el servidor correcto, PASA sin pausas y FALLA con cualquiera de las dos pausas; con X1 (k), FALLA en los tres casos |

**Hallazgos propios del orquestador** (sondas de Chromium del 2026-11-14): una página servida con `page.route` no llega a mandar peticiones a 127.0.0.1, así que P6 necesita un servidor real (§6.1); y tras `unroute`, `EventSource` reenvía el último `id` visto, de ahí el `id` alto del `snapshot` falso de P4.
