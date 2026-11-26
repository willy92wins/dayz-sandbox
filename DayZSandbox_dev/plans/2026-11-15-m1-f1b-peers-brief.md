# F1b-peers sin juego: mod núcleo `DayZSandbox/` y los dos peers `dsbx1` en Enforce

2026-11-15 · tarea **F1b-peers**, parte sin juego. Rama `claude/f1b-peers` desde `origin/main` (`0634598`, que ya lleva F1b-bridge, PR #9) · spec de implementación (R25) de la continuación que define el brief de F1b-bridge en su §11 ([brief](2026-11-14-m1-f1b-bridge-brief.md), líneas 367-382) · contrato de los peers: el mismo brief, §2.4 (líneas 85-122), congelado y ya en `main` · plan v2, decisiones #3, #5, #8, #10, #22 y #32 · **v1.3, congelada**: ronda 1 de Sol aplicada, ronda 2 arbitrada por el orquestador con el tope de 2 rondas cumplido, y revisión del experto de Enforce aplicada (§10).

**Por qué ahora.** F1b-bridge dejó en `main` el lado del backend y un mod falso en Python que cumple §2.4 (`app/tests/fake_mod.py`). Falta el mod real para cerrar F1 (plan v2, F1, líneas 80-93). La sesión principal asignó F1b-peers el 2026-11-15. La parte en partida espera al gate en partida de F0.3-0 (§6).

**Qué hay ya.**
- **El contrato:** `dsbx1`, en el brief de F1b-bridge §2 (§2.4 es lo que cumple cada peer).
- **El patrón medido en Enforce:** la sonda QA de F0.3-0, en la rama `claude/f0.3-0-impl` (`8ccc926`), bajo `DayZSandbox_dev/qa/probe/DayZSandbox_QA/` (en adelante, `PROBE`). Tiene:
  - transporte con `RestCallback` y `RestContext`;
  - `JsonSerializer` para leer y `JsonFileLoader.LoadFile` para la configuración;
  - UUID con `Substring`;
  - polls de mantenimiento `deliver=0`, lease antes de cada efecto y reintentos 250/500/1000;
  - caché con `RemoveOrdered`, presupuesto de callbacks y `WIRE_CAP`;
  - validación de `ok`.
- **La referencia de comportamiento:** el mod falso, que pasa BR3-BR23 contra el bridge real.
- **El mod núcleo:** no existe todavía.

**Proceso.** Como F1b-web y F1b-bridge:
1. Sol revisa este brief, como mucho en 2 rondas (Guillermo, 2026-11-14: «Máximo 2 rondas de Sol»); después arbitra el orquestador.
2. La lógica de los peers la escribe un worker (F1bp-1) y las herramientas de Python, otro (F1bp-0, §8). El esqueleto mecánico y los ajustes del bridge y del mod falso (§3.4-§3.6) los hace el orquestador.
3. El orquestador revisa, integra y corre el gate.
4. Sol revisa el código.
5. Es Enforce de producto, así que después revisa el experto de Enforce (Guillermo: «Solo el producto»). El orquestador le deja el texto a Guillermo.
6. **El PR no se mergea hasta pasar el gate en partida**, porque toca el PBO (§6).

## 0. Qué es y qué no

**Es** la parte que no necesita el juego:
- **el mod núcleo `DayZSandbox/`** en la raíz del repo (#32): un solo PBO para servidor y cliente, sin dependencias (#5), con `config.cpp`, `$PBOPREFIX$`, `include.lst` y sus módulos de script;
- **los dos peers `dsbx1`** dentro de ese mod, con todo §2.4 del brief de F1b-bridge y las lecciones de F0.2 y F0.3-0:
  - `WIRE_CAP` como constante;
  - `RemoveOrdered`;
  - nada de `.Replace(`;
  - validación de `ok`;
  - presupuesto de callbacks (H4);
  - la clave sin alias (H6);
- **los verbos mínimos de F1b**, que el mod falso ya simula:
  - `state.read`;
  - `scene.apply` en dos pasos que solo anotan la generación;
  - la subida del catálogo de `CfgVehicles` (#8);
  - el epoch del mundo que el servidor pasa al cliente (#3, #10);
- **dos ajustes del bridge**: los ms públicos cuentan desde su arranque (§3.6) y no encola una orden con una cadena que el motor leería cortada (§3.5);
- **dos ajustes del mod falso**: corta las cadenas como el motor (§3.5) y tiene el modo de reintento del peer de Enforce (§3.4, D1);
- **el gate sin juego** (§5):
  - linter offline de Enforce por `errors`;
  - prueba estática del mod con antitautología;
  - PBO construido y comprobado byte a byte;
  - la herramienta que escribe la configuración del peer.

**No es:**
- **la parte en partida:** carga del PBO en servidor y cliente, E1 en retail, la viabilidad del transporte de E2, la ventana de hombre muerto en cada peer, el ritmo del reloj y lo que no se puede saber sin el motor (§6). Va después, como F1b-peers en partida;
- **la escena real** (F2): lotes, etapas, registro de entidades y reset. Aquí la generación se anota y nada más;
- **cámara, ambiente y actores** (F3-F5), la interfaz de motor de actores (#5, F5) ni la acción de parada de `inputs.xml` (#33);
- **la capacidad `scene: 1`** que añade F2 al hello del servidor: estos peers se presentan sin ella y el backend los trata como F1b-bridge.

**El gate sin juego acredita forma y reglas, no comportamiento** (premisa de Sol, ronda 1). El comportamiento de los peers solo lo acredita §6.

Trazabilidad (R20):

| Sección | Origen |
|---|---|
| §2 | #5 y #32 |
| §3 | §2.4 del brief de F1b-bridge, #3, #8, #10 y #22 |
| §5 y §6 | §11 de ese brief y la fila E1 del plan (línea 174) |

Lo que no trace a esto no entra.

## 1. Entorno y fronteras

- Como F1b-bridge §1: Python 3.14 en `C:\Python314\python.exe`, solo biblioteca estándar, `unittest`, comandos desde `DayZSandbox_dev/` y solo 127.0.0.1.
- Ninguna clave en logs, salidas ni errores.
- UTF-8 sin BOM con LF. El worktree se crea con `git -c core.autocrlf=false`, o la copia de trabajo sale en CRLF.
- Vanilla montado en `P:\scripts`. Las líneas de motor de este brief están leídas ahí el 2026-11-15.
- Linter: `%USERPROFILE%\DayZ-Modding-Knowledge-Pack\tools\dayz-script-validator\scripts\script_validator.py` (en adelante, `VAL`).
- AddonBuilder: `C:\Program Files (x86)\Steam\steamapps\common\DayZ Tools\Bin\AddonBuilder\AddonBuilder.exe`.
- **No se lanza DayZ en esta parte.**

## 2. El mod núcleo

### 2.1 Árbol y configuración

```
DayZSandbox/                       raíz del repo (#32)
  $PBOPREFIX$                      DayZSandbox
  include.lst                      *.c   (sin él, AddonBuilder no mete los .c en el PBO: brief de F0.2, línea 105)
  config.cpp
  scripts/3_Game/DSBX_*.c          protocolo y peer (§3)
  scripts/5_Mission/DSBX_Mission.c ganchos de misión y RPC del epoch
```

**`config.cpp`**, con la misma forma que `PROBE/config.cpp` pero con otros módulos:
- `CfgPatches` → `class DayZSandbox` con `units[] = {}`, `weapons[] = {}`, `requiredVersion = 0.1` y `requiredAddons[] = {"DZ_Data"}`;
- `CfgMods` → `class DayZSandbox` con `dir`/`name = "DayZSandbox"`, `type = "mod"` y `dependencies[] = {"Game", "Mission"}`;
- `class defs` con:
  - `gameScriptModule` → `files[] = {"DayZSandbox/scripts/3_Game"}`;
  - `missionScriptModule` → `files[] = {"DayZSandbox/scripts/5_Mission"}`.

Sin `4_World` todavía: la interfaz de actores es de F5. El nombre de clase de `CfgMods` es un define de script desde 1.26.

### 2.2 Dónde va cada cosa

- **`3_Game`: el protocolo, el peer y el mundo de F1b.** Ahí ya está todo lo que usan:
  - `RestApi` (`P:\scripts\3_game\http\restapi.c:95-183`);
  - `JsonSerializer` (`3_game/gameplay.c:68,100`);
  - `UUIDApi` (`3_game/global/uuid.c:10,21`);
  - `ConfigGet*` (`3_game/global/game.c:539,594,602,611`);
  - `GetModInfos` (`game.c:617`), `GetWorldName` (`game.c:932`) y `GetVersion` (`game.c:942`);
  - `World.GetWorldSize` (`3_game/global/world.c:82`);
  - `RPCSingleParam` (`game.c:1013`) y `DayZGame.Event_OnRPC` (`3_game/dayzgame.c:991`).
- **`5_Mission`: solo los ganchos.**
  - `modded class MissionServer`: `OnMissionStart` crea el peer servidor y genera el epoch, y `OnUpdate` llama a su `Tick`.
  - `modded class MissionGameplay`: `OnMissionStart` crea el peer cliente, y `OnUpdate` llama a su `Tick`. Es el mismo patrón que `PROBE/scripts/5_Mission/DSBX_QA_Mission.c:1-39`.
  - El RPC del epoch va en §3.10.
  - Una `modded class` nunca lleva herencia.
- **Nombres:**
  - clases con prefijo `DSBX_`;
  - miembros de las clases `modded` con prefijo propio (`m_Dsbx…`);
  - las clases de mensajes usan como miembros las claves del cable (snake_case y sin `m_`), como `PROBE`.

## 3. Los peers

Una clase, `DSBX_Peer(role)`, con `role` = `"server"` o `"client"`. Cumple **§2.4 entero** del brief de F1b-bridge. Sus constantes son las de §2.6 de ese brief y son miembros, no números sueltos. Lo que sigue concreta cómo, en Enforce, sin cambiar el contrato.

### 3.1 Configuración y clave (H6)

- **Fichero:** `$profile:dsbx_peer.json`, con `{"url": "http://127.0.0.1:<bridge_port>/", "key": "<peer_key>"}`.
  - Se lee con `JsonFileLoader<DSBX_PeerConfig>.LoadFile(...)`, nunca con `JsonLoadFile`, como `PROBE/.../DSBX_QA_Probe.c:625`.
  - Se vuelve a leer antes de cada hello.
- **URL:** solo vale si es exactamente `http://127.0.0.1:<puerto 1-65535>/`, con la `/` final (regla `UrlUsable` de `PROBE`).
- **Alfabeto de la clave (P-07):** solo vale con 16-128 caracteres de `[A-Za-z0-9_-]`, el de `secrets.token_urlsafe` con el que el backend la genera.
  - Así `KeyQuery()` la concatena tal cual, sin codificar, sin que cambie al leer la consulta.
  - Una clave con otro carácter deja la configuración no usable (`bad_key_chars`) y el peer no se presenta.
- **Configuración no usable** (sin fichero, clave vacía, alfabeto malo o URL mala): el peer escribe el motivo, nunca la clave, y espera `retry_ms` antes de reintentar.
- **La clave solo vive en `m_Key`** y solo sale por `KeyQuery()`: `return "key=" + m_Key;`, como `PROBE/.../DSBX_QA_Probe.c:402-405`. `KeyQuery()` solo aparece dentro del argumento de ruta de `Send` (§3.2), que es el único que llama a `GET` y `POST` (regla 5 de F0.3-0 ampliada, F02-H6).
- **Quién escribe el fichero:** `app/tools/peer_config.py --config backend.json --profile <carpeta>` (nuevo).
  - Lee `bridge_port` y `peer_key` de `backend.json` y escribe `<carpeta>/dsbx_peer.json` con escritura atómica.
  - Rechaza, con salida 2, una `peer_key` fuera del alfabeto. No imprime la clave.
  - Se corre una vez por carpeta de perfil, servidor y cliente.

### 3.2 Transporte y canales

- **Un `RestContext`** sobre la URL de la configuración, con `SetHeader("application/json")`. Se rehace solo si cambia la URL.
- **Dos canales**, cada uno con una petición en vuelo como mucho y su propio callback (patrón de `PROBE`: `RestCallback` con `OnSuccess`, `OnError`, `OnTimeout` y generación por envío):
  - **P**: hello, poll entregador y poll de mantenimiento;
  - **R**: resultados y páginas del catálogo.
- **Pueden estar en vuelo a la vez.** Así un acuse lento no corta los polls de mantenimiento (§2.4.2; es el H3 de Sol en el mod falso). **[verify en partida]** si el motor atiende las dos peticiones a la vez (§6, G7).
- **Un solo punto de envío (P-06):** `Send(canal, ruta, body)` es la única función que llama a `GET` o `POST`.
  - Para `POST` compara antes `body.Length() > DSBX_WIRE_CAP`. Si se pasa, no envía y devuelve el fallo `wire_cap` a quien llama.
  - Cubre hello, resultados y páginas del catálogo.
  - **Lo que entra en `Send` no sale de él (P-09).** Dentro de `Send`, `ruta` solo aparece en la firma y como argumento de `.GET(` y `.POST(`; `body`, además, en la comparación con `DSBX_WIRE_CAP`. Ninguno de los dos se concatena, se asigna, se guarda ni se pasa a `Log` ni a otra llamada. Los logs de `Send` dicen el canal y los bytes, nunca la ruta.
- **Callbacks a prueba de repetición:** el motor puede llamar a `OnError` varias veces si reintenta (`restapi.c:53`). Cada callback se cierra con su primera llamada (`m_Done`). Una respuesta de una generación que ya no es la activa de su canal se descarta, como en `PROBE`.
- **Plazos del motor:** `RestApi.SetOption(ERESTOPTION_READOPERATION, 3)` y `SetOption(ERESTOPTION_CONNECTION, 3)` al crear el primer peer. Son los mínimos que admite el motor (`restapi.c:28-35`: entre 3 y 120 s; 10 por defecto).
- **Watchdog de guion:** de 6 s por canal. Una petición sin respuesta se retira y cuenta como fallo de transporte.
- **Presupuesto de callbacks (H4):** 2000 creados por misión, como mucho, reusando los que acaban bien (pool de 4 por canal).
  - Al agotarse, el peer deja de pedir y escribe `callback_budget_exhausted` una vez (F0.3-0, decisión D5: se cuenta al crear).

### 3.3 Reloj (P-02, parte local)

- **«Ahora»** es `GetTickTime() * 1000`, como `PROBE/.../DSBX_QA_Probe.c:356-359` y la regla de relojes de F0.3-0. Prohibido usar `GetGame().GetTime()` o `CallLater` para plazos.
- **Precisión:** `GetTickTime()` es un `float` de 32 bits en segundos desde que arrancó el juego. Su resolución empeora con el tiempo:

  | Tiempo de juego | Resolución |
  |---|---|
  | menos de 4,6 h | ≤ 2 ms |
  | menos de 24 h | ≤ 8 ms |
  | 10 días | 62 ms |

  - Todos los instantes locales (`t_envío`, `t_recepción`, último poll válido) se guardan como `float` de ms con esa cota.
  - El margen de 100 ms del plazo local y el lease de 3000 ms la absorben en misiones de menos de 24 h. Las misiones de servidor de M1 duran horas.
  - Más allá, es un riesgo declarado (§9).
- **Riesgo abierto:** que `GetTickTime()` se pare en una pausa o un tirón del servidor (brief de F1b-bridge §10, línea 365). Lo mide G6 en partida.

### 3.4 Máquina de estados y errores (P-01)

Un `Tick(timeslice)` por `OnUpdate` mueve:

| Estado | Qué hace |
|---|---|
| `SIN_CONFIG` | Lee la configuración. El peer cliente, además, espera a tener epoch (§3.10). Cuando puede, pasa a `HELLO` |
| `HELLO` | Manda `POST hello` por P (cuerpo en §3.11) y valida la respuesta (§3.5) |
| `LISTO` | Hace polls por P |

**Hello aceptado:** el peer guarda `session`, `conn`, `lease_ms`, `hold_ms` y `wire_cap`, y renueva el lease. Si la sesión es nueva y el peer es el servidor, programa el catálogo (§3.9).

**En `LISTO`, qué poll se manda:**
- **Mantenimiento** si está ejecutando una orden, si tiene resultados sin acusar (en vuelo o pendientes) o si la caché está llena de entradas vivas. Es `GET poll?…&conn=<conn>&deliver=0`, uno cada 500 ms y uno en vuelo como mucho (§2.4.2).
- **Entregador** en cualquier otro caso: `GET poll?<KeyQuery>&peer=<role>&inst=<inst>&session=<session>&conn=<conn>`.
  - Es una orden por poll como mucho (§2.1).
  - Primero se mandan los resultados pendientes y después vuelve el poll entregador.

**Lo que el motor deja ver de un fallo** (`restapi.c:8-23`, `:52-73`):
- `OnSuccess(data, size)` trae el cuerpo y no el código HTTP.
- `OnError(code)` trae solo un `ERestResultState` y ningún cuerpo.
- `OnTimeout()` no trae nada.

Así que el peer **no distingue** un 409 `hello_required` de un 401 o un 400 por el cuerpo. La política decide por el estado del motor; en R, con la desviación declarada D1 (abajo):

| Canal y estado | Qué hace el peer |
|---|---|
| P, `OnError` con el estado de un 4xx (`hello_required`, `bad_key` o `bad_request`): `DSBX_Const.REST_STATE_4XX`, que vale 5 | Olvida `session` y `conn` y vuelve a `HELLO`. Las vueltas seguidas por esta fila esperan 250 ms × 2^(n−1), con tope `retry_ms`, y la cuenta vuelve a cero con un poll válido: un 4xx que se repite no presenta al peer en bucle |
| P, cualquier otro fallo (otro `OnError`, `OnTimeout`, watchdog o un 200 que no vale) | No renueva el lease. Reintenta en el mismo estado, con esperas de 250 ms × 2^(n−1) y tope `retry_ms`. **No se vuelve a presentar**, salvo por la regla de abajo |
| P, sin un poll válido durante más de `lease_ms` | Vuelve a `HELLO`, pase lo que pase. Para entonces el backend ya ha dado la conexión por perdida (§2.5.3) |
| R, resultado, cualquier fallo: `OnError` con cualquier estado (el de un 4xx incluido), `OnTimeout`, watchdog o un 200 que no vale | Reintento a los 250, 500 y 1000 ms; se abandona al cuarto fallo y el resultado queda en la caché (§2.4.7). **R no mira el estado del motor** (D1) |
| R, página del catálogo, cualquier fallo | Los mismos reintentos. Al cuarto fallo de una página se abandona el catálogo de esa sesión |

**D1, desviación declarada (arbitraje del orquestador tras la ronda 2 de Sol, P-01).** El contrato abandona un resultado «tras 4 fallos o con un 409 `unknown_op`» (brief de F1b-bridge, línea 121). El motor no deja ver ese 409, así que el peer de Enforce solo aplica la primera rama:
- ante un `unknown_op` manda como mucho 3 POST de más, en 1,75 s;
- el backend contesta a cada uno con el mismo 409 y no toca su estado (`bridge.py:590-610`, en `handle_result`);
- el resultado acaba como en el contrato: abandonado y en la caché para una reentrega;
- un 400 `bad_request` por un cuerpo incompleto se reintenta y puede acabar en 200, como en la referencia (`fake_mod.py`, `_service_pending`).

El mod falso reproduce esta política con `r_retry_unknown=True`. La prueba `ReintentoSinVer409` acredita que así se abandona al cuarto intento sin que el backend cambie, y que con el modo apagado se abandona al primero. El backend ya acepta esos reintentos, así que el contrato no se toca.

- **Medido en partida** (G7, partida diag v1.6, `3806133`): 400, 401, 409 y 413 llegan a `OnError` con el estado 5, en P y en R, y un 500 con el 6. El enum del script es secuencial (`restapi.c:8-22`): `EREST_ERROR_CLIENTERROR` vale 6, aunque su comentario lo iguale a `EREST_ERROR`. Por eso la fila 1 compara con el estado medido y no con el símbolo, que casaba un 500 (revisión de Enforce, §10; brief de partida, H-07 y H-13).
- **Si otra versión del motor cambia ese estado,** la regla de `lease_ms` sigue garantizando que el peer se vuelve a presentar. En R no cambia nada, porque no mira el estado.
- **Una conexión rechazada también llega con 5:** lo midió dayz-mcp en partida (brief de F0.2, `plans/2026-10-27-m1-f0.2-brief.md:103`). Con el backend caído, P vuelve a `HELLO` al primer fallo y no a los `lease_ms`, con la misma espera creciente y el tope `retry_ms`. Es seguro: sin backend no hay sesión que conservar.
- **La caché sobrevive** a un hello nuevo (§2.4.4).

### 3.5 Validación de todo 200 (§2.4.1, H5)

Funciones con nombre fijo y sin efectos, `ValidHello`, `ValidPoll` y `ValidAck`, más `ValidOrder` para cada orden. Las respuestas solo se usan después de pasar su validador.

- **hello:** `ok` presente y `true`, `session` de 16 hex, `conn` entero ≥ 1, `lease_ms > 0`, `hold_ms > 0` y `wire_cap ≥ 1024`. El de `conn` lo añadió el mod falso, porque sin él el peer se queda con sesión y sin conexión.
- **poll:** `ok` presente y `true`, `now_ms` entero ≥ 0 y `ops` lista de 0 o 1 órdenes.
- **orden:** `op_id` no vacío, `session` de 16 hex, `conn` entero, `epoch` e `inst` de 32 hex, `verb` no vacío, `issued_ms` entero ≥ 0 y `ttl_ms` entero > 0. **`args` no se valida aquí: lo decide el verbo.** `scene.apply` rechaza con `bad_args` y `state.read` no lo usa, así que una orden sin `args` y una con `args:{}` tienen la misma conducta (brief de partida, H-08; revisión de Enforce, §10).
- **acuse:** `ok` presente y `true`.

Las respuestas se leen con `JsonSerializer.ReadFromString` en clases de mensajes (`DSBX_HelloResp`, `DSBX_PollResp`, `DSBX_Order`, `DSBX_Args` y `DSBX_AckResp`), como `PROBE`.
- **Los ms del cable son `int`**: `now_ms`, `issued_ms`, `ttl_ms` y `conn` (P-02). Nunca `float`.
- **Una lectura fallida** cuenta como 200 no válido.
- **Cadenas que el motor cortaría.** `JsonSerializer` corta a 1023 cada cadena que lee (F0.3-0, BASE-01; su brief, §15, D10, en `b9b4740`).
  - El bridge no encola una orden con una cadena de más de 1000 bytes en el cable, contada escapada y en UTF-8: `STR_CAP` en `bridge.py`, con rechazo `wire_cap_exceeded` y la prueba `CadenasQueElMotorCorta`. Es la regla de 1000 de D10.
  - El mod falso corta a 1023 al leer, como el motor (`cut_engine_strings`, prueba `MotorCortaCadenas`).
  - Así el peer nunca lee una cadena cortada de una orden y no necesita comprobarlo.

**[verify en partida]** cómo lee `JsonSerializer` un `bool` ausente y un número en un `int` (F0.3-0 lo marcó `[verify]`).

### 3.6 Órdenes: plazos, deduplicación y comprobaciones (§2.4.3-§2.4.5)

**Origen de los ms del bridge (P-02).** El bridge emite `now_ms` e `issued_ms` contando desde su propio arranque. Así son enteros pequeños: caben en un `int` de 32 bits durante 24,8 días de backend y son exactos en `float` durante las primeras 4,6 h. El contrato no fija el origen, solo que son ms del reloj monotónico del backend (brief de F1b-bridge §2.3, línea 73). El cambio va en `app/backend/bridge.py`, en `_t0`, `_ms` y `_now_ms`, con su prueba `MsDesdeElArranque`, y lo hace el orquestador en esta rama.

Igual que el mod falso (`app/tests/fake_mod.py`, `handle_order`), en este orden:

**1. Plazos.** `restante = ttl_ms − (now_ms − issued_ms)` se calcula **en `int`**. Con él:
- `plazo_local = t_envío + restante − 100`;
- `retención_hasta = t_recepción + restante + 1000`.

`t_envío` es el instante local en que se mandó el poll que trajo la orden; `t_recepción`, el de su respuesta. Los dos son `float` de ms (§3.3).

**2. Deduplicación, antes que nada.**
- La caché se indexa por la cadena `session + "|" + op_id` (H1).
- Una entrada **en curso** hace que la orden repetida se ignore.
- Una entrada **terminada** hace que se reenvíe el resultado guardado con `dup: true`, sin efecto.
- Una entrada cuya `retención_hasta` ya pasó no cuenta.

**3. Capacidad (P-05).**
- Antes de guardar una orden nueva, si hay 1024 entradas, se expulsa **la primera caducada en orden de llegada, esté donde esté** (es decir, que ya pasó su `retención_hasta`).
  - Se recorre el array de orden desde el índice 0 y se quita con `RemoveOrdered(i)`, como `_evict_one_expired_locked` del mod falso.
  - Nunca `Remove(`, que no conserva el orden (H2).
  - Las entradas vivas que haya delante se quedan.
- Si no hay ninguna caducada (1024 entradas vivas), la orden no se guarda ni se ejecuta. Con la contrapresión de §3.4 no debería llegar.

**4. Comprobaciones de una orden nueva**, cada una con `rejected/<motivo>` y sin efecto:
- `stale_session`;
- `stale_inst`;
- `stale_conn`;
- `stale_epoch`;
- `expired`, si ya pasó `plazo_local`.

El resultado se guarda en la caché como terminado.

### 3.7 Efectos y verbos (§2.4.6, §3.2 del brief de F1b-bridge)

**Mundo de F1b.** En memoria del mod servidor (#10) viven:
- el `epoch`, de 32 hex, que se genera en `OnMissionStart` con UUID y `Substring` (como `PROBE/.../DSBX_QA_Probe.c:264-274`, nunca `.Replace(`);
- la `generation` (`{session, op_id, rev, hash}`, o `null`), que es `null` al arrancar;
- el registro vacío de F2: `registry_n = 0` y `registry_sha256` = 64 ceros, el mismo valor que el mod falso.

**`state.read`:** sin efectos. Su `read` es `{epoch, generation, registry_n, registry_sha256}`.

**`scene.apply`:** dos pasos con efecto, en ticks consecutivos y uno por tick:
1. **retirar**: `generation = null`;
2. **anotar**: `generation = {session, op_id, rev, hash}`, con los valores de la orden.

El `read` del `done` es el del mundo después del paso 2.

**Guarda antes de cada paso (P-03).** La **primera sentencia** de `StepRetirar(order)` y de `StepAnotar(order)` es literalmente:

```
if (!EffectGuard(order)) { GuardFailed(order); return; }
```

- **`EffectGuard`** comprueba que `lease_age ≤ lease_ms` y que no haya pasado `plazo_local`. `lease_age` es ahora menos el último poll 200 válido, sea entregador o de mantenimiento.
- **Después, que la orden siga siendo de la `session` y la `conn` actuales** (`stale_session`, `stale_conn`). Tras un hello nuevo, los polls de la sesión nueva renuevan el lease, pero una orden de la anterior ya no surte efecto (revisión de Enforce, §10). Estas dos van al final para que un lease perdido se siga leyendo `lease_expired`.
- **`GuardFailed`** cierra la orden:
  - si no hubo efecto todavía, `rejected/<motivo>`, con `lease_expired`, `expired`, `stale_session` o `stale_conn`;
  - después de retirar, `error/<motivo>`.

  `rejected` queda solo para «no se tocó nada».
- **La generación del mundo** solo cambia dentro de esas dos funciones y después de esa línea.

**Verbo desconocido:** `rejected/unknown_verb`. El peer cliente no recibe órdenes en F1b; si le llega una, la rechaza así.

### 3.8 Resultados (§2.4.7)

**Cuerpo:** `{op_id, session, epoch, status, reason, dup, read}`, **escrito a mano**, como el hello de `PROBE`. Así:
- `dup` sale como booleano JSON;
- la clave `generation` está siempre, con `null` cuando toca. Desde la ronda 2 del bridge, una lectura sin esa clave no reconcilia (H2).

`JsonSerializer.WriteToString` no se usa para cuerpos.

**Dos escritores de cadenas (P-04):**
- **`WireId(s)`**, para identificadores (`op_id`, `session`, `epoch`, `inst`, `hash`, motivos fijos y nombres de clase): solo admite `[0-9A-Za-z_.:-]`. Un identificador con otro carácter no se escribe y se trata como un valor malo de quien lo produjo, por ejemplo una orden con un `op_id` raro.
- **`WireText(s)`**, para texto general (`map`, `build`, nombres del modset y `mod_ver`): escribe la cadena JSON con escape, recorriéndola byte a byte, sin `Replace` ni `IndexOf`.
  - `"` sale como `\"`, `\` como `\\`, y los bytes por debajo de 0x20, como `\u00XX`.
  - Los bytes de 0x80 en adelante pasan tal cual: es UTF-8.
  - **Nunca recorta (P-10).** El único tope es el del cuerpo entero, en `Send`. Un cuerpo que no cabe no se manda: el hello, por §3.11; el resultado, por el sustituto de abajo; la página, por §3.9.

**Tope:** un cuerpo de más de `DSBX_WIRE_CAP` bytes (lo comprueba `Send`) se sustituye por `error/result_too_large`, con `read` `{}` y el mismo `op_id`, `session` y `epoch`, y se guarda en la caché. Nunca se recorta.

**Envío:** por R, con los reintentos y abandonos de §3.4. El resultado abandonado queda en la caché para una reentrega.

### 3.9 Catálogo (#8, §5 del brief de F1b-bridge)

**Cuándo:** el peer servidor prepara la lista una vez por misión, **repartida en ticks**: 200 clases de `CfgVehicles` por tick como mucho, para no frenar un tick con miles.

**Qué clases:** las de `scope == 2` y su base:
- `ConfigGetChildrenCount("CfgVehicles")` y `ConfigGetChildName("CfgVehicles", i, name)`;
- `ConfigGetInt("CfgVehicles " + name + " scope")`;
- `ConfigGetBaseName("CfgVehicles " + name, base)`.

**Nombres:** los nombres de clase pasan por `WireId`. Uno que no pase se salta y se cuenta en un log único con el total.

**Campos de cada página:**
- `catalog_id`: 16 hex del UUID;
- `build`: con `WireText`, `"retail "` o `"diag "` más `GetVersion`;
- `modset_hash`: 64 hex;
- `classes`: `[[clase, base], ...]`.

**`modset_hash`:** se construye con 8 enteros `string.Hash()` (`1_core/proto/enstring.c:223`) del modset ordenado, cada uno con su sal (`"0|"` … `"7|"`), y cada entero se escribe como 8 hex de sus 32 bits. **No es SHA-256**, porque el motor no lo tiene. Es un identificador estable de 64 hex, y el backend solo comprueba su forma y que coincida entre páginas. Cubre el modset entero.

**Páginas:** se llenan clase a clase mientras el cuerpo entero quepa en `DSBX_WIRE_CAP`, midiendo con `Length()`. Una clase que no cabe ni sola en una página vacía se salta y se cuenta en el mismo log que las de nombre raro.

**Subida:**
- por R, solo cuando R no tiene resultados pendientes;
- una página en vuelo, con los reintentos y abandonos de §3.4;
- con cada sesión nueva del backend se vuelve a subir.

### 3.10 El epoch del servidor al cliente (#3, §2.2 del brief de F1b-bridge)

**Lo pide el cliente**, porque en `ClientReadyEvent` el servidor llama seguidos a `OnClientReadyEvent` y a `InvokeOnConnect` (`5_mission/mission/missionserver.c:356-357`), y eso no da dos oportunidades independientes de recibirlo:
- **Petición del cliente:** mientras no tiene epoch, manda cada 2000 ms un RPC `DSBX_RPC_EPOCH_REQ` sin parámetros al servidor.
- **Respuesta del servidor:** a cada petición contesta a esa identidad con `DSBX_RPC_EPOCH`, que lleva `Param1<string>(epoch)`, garantizado.
- **Empuje además:** el servidor también lo manda en `InvokeOnConnect`.
- **Ids:** altos y únicos, `26111501` (`EPOCH`) y `26111502` (`EPOCH_REQ`).
- **Recepción en el cliente:** un manejador en `DayZGame.Event_OnRPC`.
  - Solo acepta `EPOCH` en el cliente y solo si el valor tiene 32 hex.
  - Guarda el epoch.
  - Si el epoch cambia, se vuelve a presentar.
- **Recepción en el servidor:** solo acepta `EPOCH_REQ`.
- **Sin epoch, el peer cliente no se presenta.**
- **Al acabar la misión,** los manejadores se quitan en el `Shutdown()` del peer.

### 3.11 Hello

Cuerpo escrito a mano: `{"proto":"dsbx1","peer":<role>,"inst":<32 hex>,"epoch":<32 hex>,"mod_ver":<WireText>,"build":"retail"|"diag"}`.

- `build` sale de `#ifdef DIAG_DEVELOPER`, como `PROBE`.
- El servidor añade:
  - `"map"`: `WireText` de `GetWorldName`;
  - `"world_size"`: `World.GetWorldSize`;
  - `"modset"`: los nombres de `GetModInfos` con `WireText`, ordenados;
  - `"actor_engine":"none"`.
- `inst` son 32 hex por peer y por misión (UUID con `Substring`).
- **Tope (P-06 y P-10): el hello no se recorta nunca.** Si no cabe en `DSBX_WIRE_CAP`, `Send` no lo manda. El peer escribe una vez `hello_too_large bytes=<n>` y se queda en `HELLO` sin conectarse, reintentando cada `retry_ms` (vuelve a leer la configuración).
  - Así el backend nunca guarda un modset parcial como si fuera entero (`bridge.py:421`, `modset` del hello).
  - Con el modset de M1 cabe de sobra; G2 mide el tamaño real.

### 3.12 Logs

- Un único `Log(msg)` con `Print("[DSBX] " + msg)`. Ningún otro `Print`, `Error` ni `Debug.`.
- **Se escriben:**
  - las transiciones de §3.4;
  - los cambios de `session` y `conn`;
  - la pérdida del lease;
  - los resultados abandonados;
  - el catálogo completo o abandonado;
  - el hello que no cabe (`hello_too_large`);
  - el presupuesto agotado.
- **Nunca** la clave, la URL con la clave ni un cuerpo (regla de `Send` de §3.2, M4).

## 4. Lo que se acredita sin juego y lo que no

| Se acredita sin juego (§5) | Solo en partida (§6) |
|---|---|
| La forma y las reglas estáticas del mod: ficheros, `config.cpp`, tokens prohibidos, FIFO con `RemoveOrdered`, clave contenida y con alfabeto, `Send` con su tope, validadores, la guarda literal antes de cada efecto, la política de errores, los dos escritores y la codificación | Que compila y carga en el motor |
| Que el linter no da errores | Que habla con el bridge real y se recupera tras cada corte |
| Que el PBO contiene exactamente esos ficheros | Que cumple los plazos con el reloj del motor |
| Que los cuerpos que escribe el mod tienen los campos que el bridge exige | Qué deja ver el motor de un fallo, si atiende dos peticiones a la vez y cómo lee `JsonSerializer` |
| Que el bridge emite ms pequeños con diferencias exactas | E1, E2 como viabilidad del transporte, la ventana de hombre muerto y el catálogo real |

Esta parte entrega un mod **sin probar en el motor**, y lo dice en su PR.

## 5. Gate sin juego (R26)

### 5.1 Comandos

Todo desde `DayZSandbox_dev/` en una copia de trabajo limpia.

1. **Suite:** `C:\Python314\python.exe -m unittest discover -s app/tests -t app -v` → 0, sin saltadas.
   - Incluye la prueba estática del mod, la de `peer_config.py` y `MsDesdeElArranque`.
   - Las 187 pruebas de `main` siguen pasando.
2. **Linter:** `C:\Python314\python.exe <VAL> ../DayZSandbox --vanilla-root P:/scripts`.
   - Cuenta `errors` del JSON, no el código de salida, y tiene que dar 0.
   - Cada aviso se lista en el PR con su porqué. Es un mod nuevo, así que no hay base con la que compararlo.
3. **PBO:** `C:\Python314\python.exe qa/build_core_pbo.py --out <carpeta>` → `ok: true`. Ver §5.3.
4. **E2E:** el arnés de F1b-web y F1b-bridge sigue dando P1-P11 OK, ahora también con los ms relativos del bridge.
5. **Antitautología X4:** la de §5.2.

### 5.2 Prueba estática del mod: `app/tests/test_mod_static.py`

Adapta a `DayZSandbox/` las reglas de `qa/tests/test_probe_static.py` de `claude/f0.3-0-impl` y añade las del contrato. Cada regla es una prueba con nombre, y cada mutación de X4 tiene que hacer caer **su** regla.

| Regla | Qué exige | Mutaciones X4 que la tumban |
|---|---|---|
| M1 forma | Los ficheros de §2.1 y ninguno más. `$PBOPREFIX$` = `DayZSandbox` e `include.lst` = `*.c`. `config.cpp` con `requiredAddons {"DZ_Data"}`, `dependencies {"Game","Mission"}` y en `defs` exactamente `gameScriptModule` y `missionScriptModule` con sus rutas | (a) añadir `4_World` a `defs` |
| M2 tokens prohibidos | Ningún `.Replace(`, `JsonLoadFile`, `GET_now`, `POST_now`, `EnableDebug`, `GetGame().GetTime(`, `CallLater(` ni `WriteToString(` | (b) un `.Replace(` en el UUID |
| M3 FIFO | Ningún `.Remove(` sobre el array de orden de la caché. La expulsión usa `.RemoveOrdered(`, con cualquier índice | (c) `Remove(i)` en la expulsión |
| M4 clave | `m_Key` solo en su declaración, en `LoadConfig` y en `KeyQuery`. `LoadConfig` comprueba el alfabeto de §3.1. `KeyQuery()` solo dentro del argumento de ruta de `Send`. Dentro de `Send`, `ruta` solo en la firma y como argumento de `.GET(` y `.POST(`, y `body`, además, en la comparación con `DSBX_WIRE_CAP` (P-09). La clase de configuración solo en `LoadConfig`. `Print`, `Error` y `Debug.` solo en `Log` (F02-H6) | (d) un alias de la clave en otro miembro; (e) `KeyQuery()` dentro del cuerpo de un envío; (f) quitar la comprobación del alfabeto; (y) un `Log("send " + ruta);` dentro de `Send` |
| M5 `WIRE_CAP` y `Send` | `const int DSBX_WIRE_CAP = 3500;` una sola vez, igual a `WIRE_CAP` de `app/backend/bridge.py`. `.GET(` y `.POST(` solo dentro de `Send`. `Send` contiene literalmente `body.Length() > DSBX_WIRE_CAP`, y su rama corta el envío. El sustituto `"result_too_large"` aparece | (g) `DSBX_WIRE_CAP = 4000`; (h) quitar la comparación de `Send`; (i) invertirla (`<=`); (j) un `.POST(` fuera de `Send` |
| M6 validadores | `ValidHello`, `ValidPoll`, `ValidAck` y `ValidOrder` existen y comprueban los campos de §3.5. `ValidOrder` no mira `args` (§3.5). Los miembros de ms de las clases de lectura son `int` | (k) quitar la comprobación de `ok` en `ValidHello`; (l) `float now_ms` en `DSBX_PollResp`; volver a rechazar en `ValidOrder` una orden sin `args` |
| M7 guarda de efectos | La primera sentencia de `StepRetirar` y de `StepAnotar` es exactamente `if (!EffectGuard(order)) { GuardFailed(order); return; }`. Los cambios de generación (`SetGeneration(`) solo aparecen en esas dos funciones, después de esa línea. `EffectGuard` corta con `stale_session` y `stale_conn` (§3.7) | (m) quitar la guarda de `StepAnotar`; (n) llamar a `EffectGuard(order);` sin usar su resultado; (o) invertir la condición; (p) `SetGeneration(` antes de la guarda; quitar de `EffectGuard` el corte de `stale_session` o el de `stale_conn` |
| M8 dedup primero | En `HandleOrder`, la consulta de la caché va antes de cualquier comprobación de `stale_*` o `expired` | (q) mover la comprobación de `expired` antes de la caché |
| M9 contrato del cable | Los escritores a mano emiten todas las claves que exige `app/backend/bridge.py`: hello y sus campos de servidor, resultado con `generation` aunque sea `null`, y página de catálogo. Las clases de lectura tienen los miembros de las respuestas del bridge. `map`, `build`, `mod_ver` y el modset pasan por `WireText`, y los identificadores, por `WireId`. `WireText` tiene un solo parámetro y nada recorta: `hello_modset_truncated` no aparece, el escritor del hello no quita elementos del modset (`Remove`, `RemoveOrdered`, `Resize` ni `Clear` sobre él) y `hello_too_large` aparece (P-10) | (r) quitar `"generation"` del escritor del `read`; (s) escribir `map` sin `WireText`; (z) volver a quitar nombres del modset hasta que el hello quepa |
| M10 epoch | `DSBX_RPC_EPOCH` y `DSBX_RPC_EPOCH_REQ` ≥ 1 000 000. El cliente no se presenta sin epoch: `SIN_CONFIG` lo comprueba antes de pasar a `HELLO`. `Event_OnRPC.Insert` y `.Remove` aparecen exactamente una vez cada uno | (t) presentarse sin epoch |
| M11 errores | El manejador de `OnError` del canal P lleva el estado de un 4xx, `DSBX_Const.REST_STATE_4XX` = 5, a `HELLO`, con la espera creciente de §3.4. `REST_STATE_4XX` solo se usa en ese manejador y `EREST_ERROR_CLIENTERROR` en ningún sitio: R trata todo fallo igual y abandona al cuarto (D1). La regla de «sin poll válido durante `lease_ms`» vuelve a `HELLO` | (u) tratar el 4xx en P como un fallo cualquiera; (v) quitar la vuelta a `HELLO` por lease vencido; (x) en R, abandonar al primer `CLIENTERROR`, como la v1.1; volver a comparar con `EREST_ERROR_CLIENTERROR`; `REST_STATE_4XX` = 6; mirar `REST_STATE_4XX` en R |
| M12 codificación | UTF-8 sin BOM y solo LF en todo `DayZSandbox/` | (w) un CRLF |
| M14 peer `Managed` | `class DSBX_Peer : Managed`, y el `m_Peer` de `DSBX_Callback` es una referencia débil, sin `ref` ni `autoptr`. El motor retiene cada callback (BI T188795); con `Managed`, esa referencia pasa a null al destruirse el peer | quitar `: Managed`; `ref DSBX_Peer m_Peer;` |
| M15 cuarentena de callbacks | Un callback cerrado por un fallo (`SettleCallback`) o por un vigilante pasa a cuarentena (`Quarantine`: `Retire`, `m_RetiredMs` y el tope `CALLBACK_QUARANTINE_MAX`). `AcquireCallback` prueba el pool, luego la cuarentena y solo después crea. `TakeFromQuarantine` devuelve el más antiguo, y solo pasado `CALLBACK_QUARANTINE_MS`, que vale al menos 10 veces `WATCHDOG_MS`. `Shutdown` suelta el peer de los callbacks en cuarentena. `Quarantine`, `TakeFromQuarantine` y `DetachAll` van al pie de la letra: cada operación en su sitio y en su orden. `CALLBACK_QUARANTINE_MAX × DEFAULT_RETRY_MS ≥ 2 × CALLBACK_QUARANTINE_MS` | retirar sin cuarentena al fallar; no reutilizar la cuarentena; reutilizarla sin esperar; retirar sin cuarentena en el vigilante de P; `CALLBACK_QUARANTINE_MS` = 6000; no soltar la cuarentena en `Shutdown`; quitar el `Insert`; `return null;` en lugar de `return oldest;`; quitar el `Detach()` de `DetachAll`; `CALLBACK_QUARANTINE_MAX` = 32; quitar el `return null;` del veto de 60 s; `DetachAll` desde `k = 1`; incrementar `k` antes de `Get(k)` |

M13, el gancho de G5 solo en diag, es del brief de partida (D-P3). M14 y M15, y lo nuevo de M6, M7 y M11, son de la revisión de Enforce (§10); sus mutaciones van sin letra.

**X4:** el orquestador aplica cada mutación (a)-(z), y las de la revisión de Enforce, sobre una copia y comprueba que cae la regla de su fila. Si cae otra o no cae ninguna, la regla está mal. Las reglas son de forma: X4 acredita que **discriminan esas mutaciones**, no que el peer se comporte bien (§0).

### 5.3 PBO: `qa/build_core_pbo.py` (nuevo)

Toma el patrón de `build_pbo.py` de F0.3-0, que hoy vive fuera del repo, en `C:\tmp\dsbx-f030-work\tools\`:
1. exige el árbol limpio;
2. saca `DayZSandbox/` de HEAD con `git -c core.autocrlf=false archive`;
3. empaqueta con AddonBuilder: `[AB, stage, out/@DayZSandbox/Addons, "-prefix=DayZSandbox", "-temp=…", "-clear", "-packonly"]`, siempre con argumentos;
4. vuelve a leer el PBO y compara cada fichero byte a byte (sha256) con HEAD;
5. comprueba que el repo sigue limpio.

Escribe `build_core_pbo.json` con el sha de HEAD, el prefijo, la lista y los hashes. Sale con 0 si todo cuadra, con 1 si hay diferencias y con 2 si falta una precondición (repo sucio, sin git o sin AddonBuilder). Sus pruebas sin AddonBuilder ni git van en `app/tests/test_build_core_pbo.py`: el lector sobre un PBO sintético y la comparación.

### 5.4 Pruebas de `app/tools/peer_config.py`

Van en `app/tests/test_peer_config.py`:
- escribe `dsbx_peer.json` con la URL de `bridge_port` y la `peer_key` de un `backend.json` de prueba, con escritura atómica;
- crea la carpeta si no existe;
- sale con 2 y sin escribir nada si falta `peer_key` o si tiene caracteres fuera de `[A-Za-z0-9_-]` (por ejemplo, `+` o `&`);
- sale con 2 también con una clave que acaba en salto de línea (se valida con `re.fullmatch`) y con un `bridge_port` que no es entero, booleano incluido;
- no imprime la clave en ningún caso.

## 6. Gate en partida (después, F1b-peers en partida)

Va después del gate en partida de F0.3-0. Usa el OK fijo de Guillermo para partidas, con el lease de GPU como mutex, ningún DayZ ajeno abierto y cerrando solo los PID propios por WM_CLOSE. **Cada corte o reinicio exige después recuperar la conexión, reconciliar y observar una orden nueva** (P-08). Las negativas sin recuperación no cuentan.

| # | Qué |
|---|---|
| G1 carga | El PBO carga en servidor y cliente retail con BattlEye. Hay que resolver cómo se firma o se acepta el PBO (F0.2 lo hizo así; el brief de F0.2, línea 359) |
| G2 handshake | Los dos peers se presentan. El cliente lleva el epoch del servidor (`client_in_world`). El catálogo llega `complete`, con `n_classes > 0`. El hello del servidor, con el modset real, cabe en `WIRE_CAP`: se anotan sus bytes (P-10) |
| G3 D2 | Desde la web, `apply` → pendiente → ejecutando → aplicado → observado con peers reales; con el predicado que no se cumple, `fallido/lectura_no_cumple` |
| G4 E1 en retail | Clave mala, sesión vieja, backend reiniciado y polls cortados más de `lease_ms` → 0 efectos nuevos y la cola vieja sin ejecutar (fila E1 del plan, línea 174). **Después de cada uno, el peer se recupera** y una orden nueva llega a observado. Al acabar, la clave no aparece en los `script*.log` ni en los `.RPT` de servidor y cliente: búsqueda literal, 0 coincidencias (P-09; el motor podría escribir la URL de una petición) |
| G5 hombre muerto | La ventana de cada peer, servidor y cliente: acepta hasta y rechaza desde, alrededor de `lease_ms`. Con un corte **entre** retirar y anotar, la orden acaba `parcial` (`error/lease_expired`), nunca `fallido` |
| G6 reloj | El ritmo de `GetTickTime()` frente al reloj monotónico del backend, en marcha normal y con un tirón o una pausa del servidor, y la cota de 100 ms para un efecto ya empezado (brief de F1b-bridge §11) |
| G7 lo que no se sabe sin motor | Qué `ERestResultState` entrega el motor para 400, 401, 409, 413, 500 y un plazo agotado, y si llama a `OnSuccess` con un 4xx. Dos peticiones en vuelo a la vez: con un acuse retenido 4 s, los `deliver=0` siguen cada 500 ms. Cómo lee `JsonSerializer` un `bool` y un `int`. Una página de catálogo cerca de `WIRE_CAP` aceptada. Los plazos de `SetOption`. Un callback tardío de una petición ya retirada no cambia nada |
| G8 deduplicación | Con el acuse de un resultado perdido, la reentrega vuelve `dup: true` sin un segundo efecto. Con el backend reiniciado, el `op-1` nuevo se ejecuta (H1) |
| G9 E2 como viabilidad del transporte | 100 órdenes a través de los peers reales (`scene.apply` y las `state.read` internas): p95 de entrega a resultado < 1 s, contando los fallos en el denominador. Es la viabilidad de F1 (plan, F1, línea 93; brief de F1b-bridge §11); la mezcla completa de E2 es de F6 |
| G10 `WIRE_CAP` | Con las cifras del gate en partida de F0.3-0, se ajusta el entero en los dos lenguajes si hace falta |

**El PR de esta parte no se mergea hasta que G1-G9 pasen**, porque toca el PBO (regla de Guillermo).

## 7. Ficheros

```
DayZSandbox/                                      §2-§3          [esqueleto: orquestador; lógica: F1bp-1]
  $PBOPREFIX$, include.lst, config.cpp
  scripts/3_Game/DSBX_Const.c                     constantes, WIRE_CAP, ids de los RPC
  scripts/3_Game/DSBX_Messages.c                  clases de lectura (§3.5)
  scripts/3_Game/DSBX_Wire.c                      WireId, WireText y escritores a mano (§3.8, §3.11)
  scripts/3_Game/DSBX_Cache.c                     caché, retención y FIFO (§3.6)
  scripts/3_Game/DSBX_World.c                     epoch, generación y read (§3.7)
  scripts/3_Game/DSBX_Catalog.c                   catálogo en páginas y en ticks (§3.9)
  scripts/3_Game/DSBX_Peer.c                      máquina de estados, Send, canales, errores, verbos y Log (§3.1-§3.4, §3.10, §3.12)
  scripts/5_Mission/DSBX_Mission.c                ganchos y RPC del epoch (§2.2, §3.10)
DayZSandbox_dev/
  plans/2026-11-15-m1-f1b-peers-brief.md          este brief                     [orquestador]
  app/backend/bridge.py                           origen de los ms (§3.6) y tope de cadenas (§3.5)        [orquestador]
  app/tests/test_bridge.py                        MsDesdeElArranque y CadenasQueElMotorCorta              [orquestador]
  app/tests/fake_mod.py                           corte de cadenas del motor y r_retry_unknown (§3.4)     [orquestador]
  app/tests/test_fake_mod.py                      MotorCortaCadenas, ReintentoSinVer409, 3 esperas sin carrera  [orquestador]
  app/tools/peer_config.py                        §3.1                           [F1bp-0; lo corrige el orquestador]
  app/tests/test_peer_config.py                   §5.4                           [F1bp-0; lo completa el orquestador]
  qa/build_core_pbo.py                            §5.3                           [F1bp-0; lo rehace el orquestador]
  app/tests/test_build_core_pbo.py                §5.3                           [F1bp-0; lo rehace el orquestador]
  app/tests/test_mod_static.py                    §5.2                           [F1bp-1]
```

**No se tocan:**
- `server.py` ni `app/web/`;
- en `bridge.py`, `fake_mod.py` y las pruebas que ya había, nada más que lo de arriba.

F2 y F6-web cablean `server.py`, `bridge.py` y `fake_mod.py`; los cambios de esta rama en `bridge.py` y `fake_mod.py` se les avisan antes de cada commit que los lleve.

## 8. Entrega

| Tanda | Quién | Escribe |
|---|---|---|
| Esqueleto y ajustes | Orquestador | `$PBOPREFIX$`, `include.lst` y `config.cpp`, más los `.c` vacíos con sus clases, para que el linter tenga árbol. Además, los dos ajustes de `bridge.py` y los dos del mod falso, con sus pruebas |
| F1bp-0 | Carril gratis de OpenRouter (`cohere/north-mini-code:free`), de 04:44 a 04:49 | `peer_config.py`, `build_core_pbo.py` y sus pruebas. **Recibido:** `peer_config.py` y sus 13 pruebas sirven de base. El orquestador corrige la herramienta (los casos de §5.4 que se colaban y un JSON que no es objeto, que la tumbaba) y añade 3 pruebas: `main` importado con los bytes exactos, esos casos y la clave fuera de stdout y stderr también en los casos malos. `build_core_pbo.py` no sirve (lee el PBO buscando barras, llama a `subprocess.sha256`, que no existe, y su prueba falla): el orquestador lo rehace desde el patrón de F0.3-0, con 7 pruebas. Las 15 mutaciones de las dos herramientas mueren (X3) |
| F1bp-1 | Argon por `agy` (`gemini-4-argon-high`, `accept-edits`, sin terminal: el gate lo corre el orquestador), con la tanda que cede F0.3. Cadena de Guillermo: Muse, sin cuota hasta el 16-nov → Argon → Carbon → DS4.1 en el GX10 | La lógica de §3 en `DayZSandbox/` y `test_mod_static.py` (§5.2) |

Cada tanda trabaja en una copia aparte del commit congelado. El orquestador:
- revisa el diff;
- corre el gate y X4 sin fiarse de los recibos;
- integra y hace commit.

Después revisa el código Sol, como mucho en 2 rondas; luego, el experto de Enforce, con el texto que el orquestador deja a Guillermo. Push y PR con la palanca de Guillermo. **Merge solo con §6 en verde.**

## 9. Riesgos y lo que no se ha medido

- **Sin motor no hay prueba de comportamiento.** El mod falso acredita el contrato y esta parte, la forma. Lo que hace el mod en el motor solo lo dice §6.
- **Qué deja ver el motor de un fallo (G7).** La política de §3.4 descansa en que un 4xx llegue con el estado 5, como se midió. Si otra versión del motor lo cambia, el peer tarda hasta `lease_ms` en volver a presentarse, y es seguro pero más lento. En R no importa: no mira el estado (D1).
- **El tope de la cuarentena** (64) dobla lo que acumula un periodo con el backend caído: unos 30 callbacks, a un fallo de P cada `retry_ms`. Sol calcula hasta 33 con las esperas iniciales y rechazos instantáneos, y que después no crecen. Si se llenara, el callback sobrante se pierde como antes y el presupuesto sigue cortando.
- **Una respuesta muy tardía a un callback reutilizado.** Un callback sale de la cuarentena a los 60 s. Si el motor contestara a la petición vieja después, esa respuesta se tomaría por la de la nueva. Los plazos de `SetOption` (3 s de conexión y 3 s de lectura) y el vigilante de 6 s lo hacen improbable. No está medido.
- **`SetOption` es global.** Hay una sola `RestApi` (`restapi.c:147`, `:175` y `:183`), así que los plazos de 3 s que pone el peer valen para todos los mods del proceso, y otro mod puede cambiarlos. Queda como deuda y pregunta de producto, sin cambio en esta tarea.
- **La fuga de callbacks es del motor** (BI T188795). No hay forma limpia de liberarlos, y `DestroyRestApi()` afecta a todos los mods (`restapi.c:182`). El informe de salida «Leaked 'DSBX_Callback'» queda acotado por `created_n`, que con la cuarentena deja de crecer cuando el backend está caído.
- **`GetTickTime()`:**
  - su resolución empeora con las horas de juego (§3.3);
  - puede pararse en pausas o tirones (G6).

  Si G6 lo confirma, se cambia la fuente de reloj del peer en esta misma tarea.
- **Concurrencia del `RestContext`.** Si el motor atiende las peticiones en serie, un acuse lento corta el mantenimiento hasta 3 s, y el lease es de 3 s. Si G7 lo confirma, la alternativa es un segundo `RestContext`, y hay que ver si `GetRestContext` devuelve uno nuevo para la misma URL. Se decide entonces.
- **Backend encendido más de 24,8 días seguidos:** los ms del cable dejan de caber en un `int`. M1 reinicia el backend mucho antes.
- **`modset_hash` no es criptográfico.** Basta para versionar el catálogo por modset (#8).
- **El catálogo de vanilla** puede pasar de cien páginas y se sube con cada sesión nueva del backend. Es local, y se gasta de presupuesto lo que se crea, no lo que se reusa.
- **Firma del PBO en retail con BattlEye:** no está resuelta (G1).
- **`WIRE_CAP = 3500` es provisional** hasta las cifras en partida de F0.3-0 (G10).
- **El corte de 1023 está medido con texto ASCII** (BASE-01). Si el motor contara la forma escapada, el tope de 1000 sobre esa forma ya lo cubre (§3.5).
- **Un modset que no cabe en el hello** deja al servidor sin presentarse (§3.11). Es visible y seguro; G2 mide el margen real.

## 10. Cambios por la revisión

**Ronda 1 de Sol** (`gpt-6.1-sol`, esfuerzo máximo, solo lectura, sobre `bc05a14`; veredicto UNSOUND con 2 bloqueantes y 6 importantes). El orquestador comprobó cada hallazgo contra `P:\scripts` en local (Sol no tenía `P:` montado y usó la fuente pública de Bohemia) y los aplica todos:

| Hallazgo | Qué cambia |
|---|---|
| P-01 · bloqueante · el motor no deja ver el código HTTP ni el cuerpo de un error, así que el peer no distingue un 409 `hello_required` de otro fallo (`restapi.c:52-73`) | Política de errores por `ERestResultState`, sin cambiar el contrato: con `CLIENTERROR` en P se vuelve a `HELLO` y en R se abandona; con cualquier otro fallo se reintenta. Además, sin un poll válido durante `lease_ms`, siempre se vuelve a `HELLO` (§3.4). Lo mide G7. Regla M11 y mutaciones (u) y (v) |
| P-02 · bloqueante · los ms absolutos del monotónico del backend no caben en un `int` de Enforce y pierden precisión en `float`, así que el plazo puede caer tarde | El bridge cuenta los ms públicos desde su arranque (`bridge.py`, con la prueba `MsDesdeElArranque`, que cae si se vuelve al origen absoluto). El peer los lee en `int` y calcula `restante` en `int` (§3.5, §3.6). El reloj local tiene su cota de precisión declarada (§3.3). Mutación (l) |
| P-03 · importante · M7 comprobaba que se llama a la guarda, no que su resultado pare el efecto | La guarda es una sentencia literal que sale de la función, y la generación solo cambia después (§3.7). Mutaciones (n), (o) y (p), y un corte entre pasos en G5 |
| P-04 · importante · el filtro de caracteres impedía mandar nombres legítimos del modset y el `build` con espacio | Dos escritores: `WireId` estricto para identificadores y `WireText` con escape byte a byte para texto (§3.8). Mutación (s) |
| P-05 · importante · expulsar solo desde la cabeza podía bloquear una caché con entradas caducadas detrás de una viva | FIFO entre las caducadas, esté donde esté cada una, con `RemoveOrdered(i)`, como el mod falso (§3.6) |
| P-06 · importante · el hello no tenía tope y M5 no acreditaba que `WIRE_CAP` se aplique | Un único `Send` con la comparación literal para todo envío, y el hello recorta el modset para caber (§3.2, §3.11). Mutaciones (h), (i) y (j) |
| P-07 · importante · `KeyQuery` no codificaba una clave con `+` o `&` | La clave solo vale con el alfabeto de `token_urlsafe`; `peer_config.py` y `LoadConfig` rechazan otra (§3.1, §5.4). Mutación (f) |
| P-08 · importante · §6 podía aprobar un peer que no se recupera de un fallo | Recuperación obligatoria tras cada corte o reinicio, más G8 de deduplicación, el corte entre pasos en G5 y G9 con la viabilidad del transporte de E2 (§6) |

Además, por la nota de Sol sobre `missionserver.c`: el epoch lo **pide el cliente** por RPC hasta tenerlo, y el empuje del servidor queda como extra (§3.10).

**Ronda 2 de Sol** (`gpt-6.1-sol`, esfuerzo máximo, solo lectura, sobre `290a4a5`, sesión `01a1dd20…`). Veredicto UNSOUND: cierra P-02..P-08, deja P-01 abierto como bloqueante y añade dos importantes. Con el tope de 2 rondas cumplido, arbitra el orquestador (Guillermo, 2026-11-14: «Máximo 2 rondas de Sol»):

| Hallazgo | Arbitraje |
|---|---|
| P-01 · bloqueante · abandonar en R al primer `CLIENTERROR` incumple el contrato, que abandona tras 4 fallos o con un 409 `unknown_op`; un 400 por un cuerpo incompleto podría acabar en 200 al reintentar | R trata todo fallo igual y abandona al cuarto: es la primera rama del contrato. No ver el 409 cuesta como mucho 3 POST de más, que el backend contesta igual sin cambiar nada. Queda como la desviación declarada D1 (§3.4), con el modo `r_retry_unknown` del mod falso y la prueba `ReintentoSinVer409`. En P, las vueltas seguidas a `HELLO` por un 4xx esperan cada vez más. Regla M11 y mutación (x) |
| P-09 · importante · un `Log(ruta)` dentro de `Send` filtraría la clave sin que M4 ni M5 lo vieran | `ruta` y `body` no salen de `Send` salvo hacia `.GET(` y `.POST(` (§3.2). Regla M4 y mutación (y). En partida, la clave se busca en los logs del motor (G4) |
| P-10 · importante · el hello recortado deja en el backend un modset parcial como si fuera entero | Nada se recorta en silencio: un hello que no cabe no se manda (`hello_too_large`) y `WireText` ya no recorta (§3.8, §3.11). Regla M9 y mutación (z). G2 mide el tamaño real del hello |

Además, fuera de los hallazgos:
- **Cadenas que el motor corta:** la medida de F0.3-0 (BASE-01, D10) pasa al bridge, con la regla de 1000 sobre la forma escapada, y al mod falso, que corta a 1023 como el motor (§3.5).
- **Reparto de la entrega:** F1bp-0 para las herramientas de Python y F1bp-1 para Enforce, con lo recibido de F1bp-0 (§7, §8).
- **Pruebas del mod falso sin carrera:** tres esperas de `test_fake_mod.py` miraban un estado intermedio del envío del resultado. Ahora esperan a la entrada terminada y sin envío pendiente.

**Revisión del experto de Enforce** (15-nov, sobre `e566fa0`, solo lectura, sin compilar; veredicto «OK con arreglos»). El experto avisó de que su copia de vanilla no cuadraba de versión, así que el orquestador comprobó sus citas contra `P:\scripts`:
- el enum secuencial (`3_game/http/restapi.c:8-22`);
- `RestCallback : Managed` (`:50`);
- `SetOption` en la única `RestApi` (`:147`, `:175` y `:183`);
- `DestroyRestApi()` global (`:182`).

Las líneas del mod que citaba eran de `e566fa0`. Se aplican el MUST y los cuatro SHOULD; ninguno pide rediseño:

| Hallazgo | Qué cambia |
|---|---|
| MUST · `DSBX_Callback` guarda un puntero normal al peer y `DSBX_Peer` no hereda de `Managed`. El motor mantiene vivos los callbacks retirados, así que una respuesta tardía tras volver al menú se ejecutaría sobre un peer liberado | `class DSBX_Peer : Managed`, con `m_Peer` débil: pasa a null al destruirse el peer, y los callbacks ya lo comprueban antes de usarlo. Regla M14 y dos mutaciones. El Pack dice que en `3_Game` todo es `Managed` sin declararlo (`skills/_shared/enscript-style.md`); con la herencia explícita no depende de eso |
| SHOULD · `EffectGuard` deja pasar órdenes de una sesión anterior después de un hello nuevo | `EffectGuard` corta con `stale_session` y `stale_conn`, después del lease y del plazo (§3.7). Regla M7 y dos mutaciones |
| SHOULD · la fila 1 de §3.4 compara con el símbolo del enum, que vale 6 y casa un 500, y no con el estado medido | Compara con `DSBX_Const.REST_STATE_4XX` = 5, y `EREST_ERROR_CLIENTERROR` queda prohibido (§3.4). El arnés de partida vuelve a forzar el hello con un 409 (brief de partida, H-13). Regla M11 y tres mutaciones |
| SHOULD · con el backend caído, el presupuesto de 2000 callbacks se agota en unos 67 minutos | Cuarentena: un callback cerrado por un fallo o por el vigilante se reutiliza a los 60 s (§9). Regla M15 y trece mutaciones: seis de las rondas de Sol y una por el tope |
| SHOULD · falta una sola conducta para una orden sin `args` | `ValidOrder` no mira `args`, y lo decide el verbo (§3.5). Regla M6 y una mutación |

**Prueba negativa:** el mod sin estos arreglos (`5881d0f`) cae justo en M6, M7, M11, M14 y M15, y pasa las otras diez reglas.

**Ronda 1 de Sol sobre el delta** (`gpt-6.1-sol`, esfuerzo máximo, solo lectura, sobre `0920ffe`). Veredicto UNSOUND, por un solo hallazgo:
- **E-01, importante:** M15 dejaba pasar tres mutaciones que quitan operaciones de la cuarentena: el `Insert`, el `return oldest;` y el `Detach()` de `DetachAll`.
- **Lo que confirma:** que las 15 reglas y las 53 mutaciones literales discriminan, que el mod contiene esas operaciones, y que los accesos al peer y a `args` están protegidos. También que las guardas nuevas de `EffectGuard` conservan la prioridad de `lease_expired`, y que la fusión de `fake_mod.py` conserva los dos ayudantes y los dos parámetros.

Arreglo: M15 exige cada una de esas operaciones en su sitio, con sus tres mutaciones. Además, el orquestador sube `CALLBACK_QUARANTINE_MAX` de 32 a 64 (§9), y M15 exige que el tope doble lo que acumula un periodo de cuarentena, con una mutación más.

**Ronda 2 de Sol sobre el delta** (sobre `1155973`, la última). Veredicto UNSOUND:
- **E-01 queda cerrado:** las tres mutaciones y la del tope tumban solo M15.
- **E-02, importante:** M15 dejaba quitar el `return null;` del veto de 60 s, y entonces un callback se reutilizaba antes de tiempo.
- **E-03, importante:** M15 dejaba que `DetachAll` se saltara el primer callback (`k = 1`, o el incremento antes de `Get(k)`).
- **Lo que confirma:** que la vuelta a `HELLO` con el backend caído conserva la espera creciente, sin bucle, sin gasto progresivo del presupuesto y sin borrar caché ni resultados. Calcula hasta 33 callbacks de P en cuarentena: el tope de 32 se habría desbordado.

Con el tope de 2 rondas cumplido, arbitra el orquestador: los dos hallazgos son reales y baratos, y se aplican. M15 exige el cuerpo literal de los tres ayudantes de la cuarentena, con las tres mutaciones de Sol. La comprobación es mecánica: X4 y el mod de `5881d0f`.
