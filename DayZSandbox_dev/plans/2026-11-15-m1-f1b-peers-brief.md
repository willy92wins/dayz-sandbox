# F1b-peers sin juego: mod núcleo `DayZSandbox/` y los dos peers `dsbx1` en Enforce

2026-11-15 · tarea **F1b-peers**, parte sin juego. Rama `claude/f1b-peers` desde `origin/main` (`0634598`, que ya lleva F1b-bridge, PR #9) · spec de implementación (R25) de la continuación que define el brief de F1b-bridge en su §11 ([brief](2026-11-14-m1-f1b-bridge-brief.md), líneas 367-382) · contrato de los peers: el mismo brief, §2.4 (líneas 85-122), congelado y ya en `main` · plan v2, decisiones #3, #5, #8, #10, #22 y #32 · **v1.0, para la revisión de Sol** (como mucho 2 rondas).

**Por qué ahora.** F1b-bridge dejó en `main` el lado del backend y un mod falso en Python que cumple §2.4 (`app/tests/fake_mod.py`). Falta el mod real para cerrar F1 (plan v2, F1, líneas 80-93). La sesión principal asignó F1b-peers el 2026-11-15. La parte en partida espera al gate en partida de F0.3-0 (§6).

**Qué hay ya.**
- **El contrato:** `dsbx1`, en el brief de F1b-bridge §2 (§2.4 es lo que cumple cada peer).
- **El patrón medido en Enforce:** la sonda QA de F0.3-0, en la rama `claude/f0.3-0-impl` (`8ccc926`), con las lecciones de F0.2 aplicadas. Está bajo `DayZSandbox_dev/qa/probe/DayZSandbox_QA/` (en adelante, `PROBE`) y tiene:
  - transporte con `RestCallback` y `RestContext`;
  - `JsonSerializer` para leer y `JsonFileLoader.LoadFile` para la configuración;
  - UUID con `Substring`;
  - polls de mantenimiento `deliver=0`, lease antes de cada efecto y reintentos 250/500/1000;
  - caché con `RemoveOrdered(0)`, presupuesto de callbacks y `WIRE_CAP`;
  - validación de `ok`.
- **La referencia de comportamiento:** el mod falso, que pasa BR3-BR23 contra el bridge real.
- **Mod núcleo:** no existe todavía.

**Proceso.** Como F1b-web y F1b-bridge:
1. Sol revisa este brief, como mucho en 2 rondas (Guillermo, 2026-11-14: «Máximo 2 rondas de Sol»); después arbitra el orquestador.
2. La lógica de los peers la escribe un worker. El esqueleto mecánico puede hacerlo el orquestador.
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
  - la clave sin alias (H6).
- **los verbos mínimos de F1b**, que el mod falso ya simula:
  - `state.read`;
  - `scene.apply` en dos pasos que solo anotan la generación;
  - la subida del catálogo de `CfgVehicles` (#8);
  - el epoch del mundo que el servidor pasa al cliente (#3, #10);
- **el gate sin juego** (§5):
  - linter offline de Enforce por `errors`;
  - pruebas estáticas del mod con antitautología;
  - PBO construido y comprobado byte a byte;
  - la herramienta que escribe la configuración del peer.

**No es:**
- **la parte en partida:** carga del PBO en servidor y cliente, E1 en retail, la ventana de hombre muerto en cada peer, el ritmo del reloj y lo que no se puede saber sin el motor (§6). Va después, como F1b-peers en partida;
- **la escena real** (F2): lotes, etapas, registro de entidades y reset. Aquí la generación se anota y nada más;
- **cámara, ambiente y actores** (F3-F5), la interfaz de motor de actores (#5, F5) ni la acción de parada de `inputs.xml` (#33);
- **la capacidad `scene: 1`** que añade F2 al hello del servidor: estos peers se presentan sin ella y el backend los trata como F1b-bridge.

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
- Vanilla montado en `P:\scripts`.
- Linter: `C:\Users\guill\DayZ-Modding-Knowledge-Pack\tools\dayz-script-validator\scripts\script_validator.py` (en adelante, `VAL`).
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

Sin `4_World` todavía: la interfaz de actores es de F5. El nombre de clase de `CfgMods` es un define de script desde 1.26, así que `#ifdef DayZSandbox` queda disponible.

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
  - `modded class MissionServer`: `OnMissionStart` crea el peer servidor y genera el epoch. `OnUpdate` llama a su `Tick`. `InvokeOnConnect` (`5_mission/mission/missionserver.c:435`) y `OnClientReadyEvent` (`:599`) mandan el epoch al cliente (§3.10).
  - `modded class MissionGameplay`: `OnMissionStart` crea el peer cliente y `OnUpdate` llama a su `Tick`. Es el mismo patrón que `PROBE/scripts/5_Mission/DSBX_QA_Mission.c:1-39`.
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
- **Configuración no usable** (sin fichero, clave vacía o URL mala): el peer escribe el motivo, nunca la clave, y espera `retry_ms` antes de reintentar.
- **La clave solo vive en `m_Key`** y solo sale por `KeyQuery()`: `return "key=" + m_Key;`, como `PROBE/.../DSBX_QA_Probe.c:402-405`. `KeyQuery()` solo aparece dentro del segundo argumento de un `GET`/`POST` de un `RestContext` (regla 5 de F0.3-0 ampliada, F02-H6).
- **Quién escribe el fichero:** `app/tools/peer_config.py --config backend.json --profile <carpeta>` (nuevo).
  - Lee `bridge_port` y `peer_key` de `backend.json` y escribe `<carpeta>/dsbx_peer.json` con escritura atómica.
  - No imprime la clave.
  - Se corre una vez por carpeta de perfil, servidor y cliente.

### 3.2 Transporte y canales

- **Un `RestContext`** sobre la URL de la configuración, con `SetHeader("application/json")`. Se rehace solo si cambia la URL.
- **Dos canales**, cada uno con una petición en vuelo como mucho y su propio callback (patrón de `PROBE`: `RestCallback` con `OnSuccess`, `OnError`, `OnTimeout` y generación por envío):
  - **P**: hello, poll entregador y poll de mantenimiento;
  - **R**: resultados y páginas del catálogo.
- **Pueden estar en vuelo a la vez.** Así un acuse lento no corta los polls de mantenimiento (§2.4.2; es el H3 que Sol encontró en el mod falso).
  - **[verify en partida]** si el motor atiende de verdad las dos peticiones a la vez (§6, G7).
- **Plazos del motor:** `RestApi.SetOption(ERESTOPTION_READOPERATION, 3)` y `SetOption(ERESTOPTION_CONNECTION, 3)` al crear el primer peer. Son los mínimos que admite el motor (`restapi.c:28-35`: entre 3 y 120 s; 10 por defecto).
- **Watchdog de guion:** de 6 s por canal. Una petición sin respuesta se retira y cuenta como fallo, como el de `PROBE` pero más corto.
- **Presupuesto de callbacks (H4):** 2000 creados por misión, como mucho, reusando los que acaban bien (pool de 4 por canal).
  - Al agotarse, el peer deja de pedir y escribe `callback_budget_exhausted` una vez (F0.3-0, decisión D5: se cuenta al crear).

### 3.3 Reloj

- **«Ahora»** es `GetTickTime() * 1000`, como `PROBE/.../DSBX_QA_Probe.c:356-359`, en todo el peer.
- **Prohibido** usar `GetGame().GetTime()` o `CallLater` para plazos.
- **Riesgo abierto:** que `GetTickTime()` se pare en una pausa o un tirón del servidor (brief de F1b-bridge §10, línea 365). Lo mide G6 en partida.

### 3.4 Máquina de estados

Un `Tick(timeslice)` por `OnUpdate` mueve:

| Estado | Qué hace |
|---|---|
| `SIN_CONFIG` | Lee la configuración. El peer cliente, además, espera a tener epoch (§3.10). Cuando puede, pasa a `HELLO` |
| `HELLO` | Manda `POST hello` por P (cuerpo en §3.7) y valida la respuesta (§3.5) |
| `LISTO` | Hace polls por P |

**Hello aceptado:** el peer guarda `session`, `conn`, `lease_ms`, `hold_ms` y `wire_cap`, y renueva el lease. Si la sesión es nueva y el peer es el servidor, programa el catálogo (§3.9).

**En `LISTO`, qué poll se manda:**
- **Mantenimiento** si está ejecutando una orden, si tiene resultados sin acusar (en vuelo o pendientes) o si la caché está llena de entradas vivas. Es `GET poll?…&conn=<conn>&deliver=0`, uno cada 500 ms y uno en vuelo como mucho (§2.4.2).
- **Entregador** en cualquier otro caso: `GET poll?<KeyQuery>&peer=<role>&inst=<inst>&session=<session>&conn=<conn>`.
  - Es una orden por poll como mucho (§2.1).
  - Primero se mandan los resultados pendientes y después vuelve el poll entregador.

**Fallos de un poll:**
- **409 `hello_required`:** el peer olvida `session` y `conn` y vuelve a `HELLO`.
- **Cualquier otro fallo o un 200 que no vale:** no renueva el lease. Se reintenta en el mismo estado, con esperas de 250 ms × 2^(n−1) y tope `retry_ms`. **No se vuelve a presentar.** En esto difiere de `PROBE`, que rehacía el hello con cualquier fallo, y es lo que pide `dsbx1`, con su `conn`.

**La caché sobrevive** a un hello nuevo (§2.4.4).

### 3.5 Validación de todo 200 (§2.4.1, H5)

Funciones con nombre fijo y sin efectos, `ValidHello`, `ValidPoll` y `ValidAck`, más `ValidOrder` para cada orden:
- **hello:** `ok` presente y `true`, `session` de 16 hex, `conn` entero ≥ 1, `lease_ms > 0`, `hold_ms > 0` y `wire_cap ≥ 1024`. El de `conn` lo añadió el mod falso, porque sin él el peer se queda con sesión y sin conexión;
- **poll:** `ok` presente y `true`, `now_ms` finito y `ops` lista de 0 o 1 órdenes;
- **orden:** `op_id` no vacío, `session` de 16 hex, `conn` entero, `epoch` e `inst` de 32 hex, `verb` no vacío, `args` objeto, `issued_ms` entero y `ttl_ms > 0`;
- **acuse:** `ok` presente y `true`.

Las respuestas se leen con `JsonSerializer.ReadFromString` en clases de mensajes (`DSBX_HelloResp`, `DSBX_PollResp`, `DSBX_Order`, `DSBX_Args`, `DSBX_AckResp`), como `PROBE`. Una lectura fallida cuenta como 200 no válido.

**[verify en partida]** cómo lee `JsonSerializer` un `bool` ausente o un número entero en un miembro `float` (F0.3-0 lo marcó `[verify]`).

### 3.6 Órdenes: plazos, deduplicación y comprobaciones (§2.4.3-§2.4.5)

Igual que el mod falso (`app/tests/fake_mod.py`, `handle_order`), en este orden:

**1. Plazos**, con `restante = ttl_ms − (now_ms − issued_ms)`:
- `plazo_local = t_envío + restante − 100`;
- `retención_hasta = t_recepción + restante + 1000`.

Todo en ms del reloj local. `t_envío` es el instante en que se mandó el poll que trajo la orden; `t_recepción`, el de su respuesta.

**2. Deduplicación, antes que nada.**
- La caché se indexa por la cadena `session + "|" + op_id` (H1).
- Una entrada **en curso** hace que la orden repetida se ignore.
- Una entrada **terminada** hace que se reenvíe el resultado guardado con `dup: true`, sin efecto.
- Una entrada cuya `retención_hasta` ya pasó no cuenta.

**3. Capacidad.**
- Antes de guardar una orden nueva se expulsan entradas caducadas: en orden de llegada, solo las que ya pasaron su `retención_hasta`, y con `RemoveOrdered(0)` sobre el array de orden. Nunca `Remove(` (H2).
- Si la caché sigue llena (1024 entradas vivas), la orden no se guarda ni se ejecuta. Con la contrapresión de §3.4 no debería llegar.

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

**Guarda antes de cada paso.** Cada paso empieza llamando a `EffectGuard(order)`, que comprueba:
- `lease_age ≤ lease_ms`, con `lease_age` = ahora menos el último poll 200 válido, sea entregador o de mantenimiento;
- que no haya pasado `plazo_local`.

Si falla:
- antes del primer paso → `rejected/lease_expired` o `rejected/expired`;
- después → `error/lease_expired` o `error/expired`.

`rejected` queda solo para «no se tocó nada».

**Verbo desconocido:** `rejected/unknown_verb`. El peer cliente no recibe órdenes en F1b; si le llega una, la rechaza así.

### 3.8 Resultados (§2.4.7)

**Cuerpo:** `{op_id, session, epoch, status, reason, dup, read}`, **escrito a mano**, como el hello de `PROBE`. Así:
- `dup` sale como booleano JSON;
- la clave `generation` está siempre, con `null` cuando toca. Desde la ronda 2 del bridge, una lectura sin esa clave no reconcilia (H2).

`JsonSerializer.WriteToString` no se usa para cuerpos. **[verify en partida]** qué escribe con `null` y con `bool`; con el cuerpo escrito a mano no hace falta saberlo.

**Escritura de cadenas:** el escritor solo admite caracteres `[0-9A-Za-z_.:-]`. Si encuentra otro, sustituye el resultado por `error/bad_field` con `read` vacío, nunca lo escapa. Los campos son hex, ids y motivos fijos.

**Tope:** un cuerpo de más de `DSBX_WIRE_CAP` bytes se sustituye por `error/result_too_large` con `read` `{}`, el mismo `op_id`, `session` y `epoch`, y se guarda en la caché. Nunca se recorta.

**Envío:**
- por R, con reintentos a los 250, 500 y 1000 ms;
- se abandona tras 4 fallos o con un 409 `unknown_op`, y el resultado queda en la caché para una reentrega;
- cuentan como fallo un acuse no 200, uno que no vale y el watchdog.

**Lo que no se usa para escribir cuerpos:** ni `.Replace(` ni `IndexOf`. Se construyen ya bien.

### 3.9 Catálogo (#8, §5 del brief de F1b-bridge)

**Cuándo:** el peer servidor lo prepara una vez por misión, en el primer tick con configuración usable.

**Qué clases:** las de `CfgVehicles` con `scope == 2` y su base:
- `ConfigGetChildrenCount("CfgVehicles")` y `ConfigGetChildName("CfgVehicles", i, name)`;
- `ConfigGetInt("CfgVehicles " + name + " scope")`;
- `ConfigGetBaseName("CfgVehicles " + name, base)`.

**Campos de cada página:**
- `catalog_id`: 16 hex del UUID;
- `build`: `"retail "` o `"diag "` más `GetVersion`;
- `modset_hash`: 64 hex;
- `classes`: `[[clase, base], ...]`.

**`modset_hash`:** se construye con 8 enteros `string.Hash()` (`1_core/proto/enstring.c:223`) del modset ordenado, cada uno con su sal (`"0|"` … `"7|"`), y cada entero se escribe como 8 hex. **No es SHA-256**, porque el motor no lo tiene. Es un identificador estable de 64 hex, y el backend solo comprueba su forma y que coincida entre páginas.

**Páginas:**
- se llenan clase a clase mientras el cuerpo entero quepa en `DSBX_WIRE_CAP`, midiendo con `Length()`;
- un nombre con caracteres fuera de `[0-9A-Za-z_]` se salta y se cuenta en un log.

**Subida:**
- por R, solo cuando R no tiene resultados pendientes;
- una página en vuelo, con los mismos reintentos;
- tras 4 fallos de una página se abandona el catálogo de esa sesión y se escribe una vez;
- con cada sesión nueva del backend se vuelve a subir.

### 3.10 El epoch del servidor al cliente (#3, §2.2 del brief de F1b-bridge)

- **Envío:** en `InvokeOnConnect` y en `OnClientReadyEvent`, el servidor manda a esa identidad un RPC `DSBX_RPC_EPOCH` con `Param1<string>(epoch)`, garantizado (`RPCSingleParam(null, DSBX_RPC_EPOCH, …, true, identity)`).
  - El id es alto y único: `26111501`.
- **Recepción:** el cliente lo recoge con un manejador en `DayZGame.Event_OnRPC`.
  - Solo acepta el RPC en el cliente, solo con ese id y solo si el valor tiene 32 hex.
  - Guarda el epoch.
  - Si cambia, se vuelve a presentar.
- **Sin epoch, el peer cliente no se presenta.**
- **Al acabar la misión,** el manejador se quita en el `Shutdown()` del peer.

### 3.11 Hello

Cuerpo escrito a mano: `{"proto":"dsbx1","peer":<role>,"inst":<32 hex>,"epoch":<32 hex>,"mod_ver":<constante>,"build":"retail"|"diag"}`.

- `build` sale de `#ifdef DIAG_DEVELOPER`, como `PROBE`.
- El servidor añade:
  - `"map"`: `GetWorldName`;
  - `"world_size"`: `World.GetWorldSize`;
  - `"modset"`: los nombres de `GetModInfos`, ordenados y con el mismo filtro de caracteres;
  - `"actor_engine":"none"`.
- `inst` son 32 hex por peer y por misión (UUID con `Substring`).

### 3.12 Logs

- Un único `Log(msg)` con `Print("[DSBX] " + msg)`. Ningún otro `Print`, `Error` ni `Debug.`.
- **Se escriben:** las transiciones de §3.4, los cambios de `session` y `conn`, la pérdida del lease, los resultados abandonados, el catálogo completo o abandonado y el presupuesto agotado.
- **Nunca** la clave, la URL con la clave ni un cuerpo.

## 4. Lo que se acredita sin juego y lo que no

| Se acredita sin juego (§5) | Solo en partida (§6) |
|---|---|
| Que el mod tiene la forma y las reglas estáticas: ficheros, `config.cpp`, tokens prohibidos, `RemoveOrdered`, clave contenida, `WIRE_CAP`, validadores, guardas antes de cada efecto, escritura a mano de los cuerpos y codificación | Que compila y carga en el motor |
| Que el linter no da errores | Que habla con el bridge real |
| Que el PBO contiene exactamente esos ficheros | Que cumple los plazos con el reloj del motor |
| Que los cuerpos que escribe el mod tienen los campos que el bridge exige (prueba estática contra las claves de `bridge.py`) | Que el motor atiende dos peticiones a la vez y que `JsonSerializer` lee los `bool` |
| | E1, la ventana de hombre muerto y el catálogo real |

Esta parte entrega un mod **sin probar en el motor**, y lo dice en su PR.

## 5. Gate sin juego (R26)

### 5.1 Comandos

Todo desde `DayZSandbox_dev/` en una copia de trabajo limpia.

1. **Suite:** `C:\Python314\python.exe -m unittest discover -s app/tests -t app -v` → 0, sin saltadas. Incluye la prueba estática del mod y la de `peer_config.py`. Las 187 pruebas de `main` siguen pasando.
2. **Linter:** `C:\Python314\python.exe <VAL> ../DayZSandbox --vanilla-root P:/scripts`.
   - Cuenta `errors` del JSON, no el código de salida, y tiene que dar 0.
   - Cada aviso se lista en el PR con su porqué. Es un mod nuevo, así que no hay base con la que compararlo.
3. **PBO:** `C:\Python314\python.exe qa/build_core_pbo.py --out <carpeta>` → `ok: true`. Ver §5.3.
4. **E2E:** el arnés de F1b-web y F1b-bridge sigue dando P1-P11 OK. El mod no lo toca; es la regresión del repo.
5. **Antitautología X4:** de §5.2.

### 5.2 Prueba estática del mod: `app/tests/test_mod_static.py`

Adapta a `DayZSandbox/` las reglas de `qa/tests/test_probe_static.py` de `claude/f0.3-0-impl` y añade las del contrato. Cada regla es una prueba con nombre, y cada mutación de X4 tiene que hacer caer **su** regla.

| Regla | Qué exige | Mutación X4 que la tumba |
|---|---|---|
| M1 forma | Los ficheros de §2.1 y ninguno más. `$PBOPREFIX$` = `DayZSandbox` e `include.lst` = `*.c`. `config.cpp` con `requiredAddons {"DZ_Data"}`, `dependencies {"Game","Mission"}` y en `defs` exactamente `gameScriptModule` y `missionScriptModule` con sus rutas | (a) añadir `4_World` a `defs` |
| M2 tokens prohibidos | Ningún `.Replace(`, `JsonLoadFile`, `GET_now`, `POST_now`, `EnableDebug`, `GetGame().GetTime(` ni `CallLater(` | (b) un `.Replace(` en el UUID |
| M3 FIFO | Ningún `.Remove(` sobre los arrays de orden de la caché; la expulsión con `.RemoveOrdered(0)` | (c) `Remove(0)` en la expulsión |
| M4 clave | `m_Key` solo en su declaración, en `LoadConfig` y en `KeyQuery`. `KeyQuery()` solo en el 2.º argumento de `GET`/`POST` sobre una variable `RestContext`. La clase de configuración solo en `LoadConfig`. `Print`, `Error` y `Debug.` solo en `Log` (F02-H6) | (d) un alias de la clave en otro miembro; (e) `KeyQuery()` dentro del cuerpo de un `POST` |
| M5 `WIRE_CAP` | `const int DSBX_WIRE_CAP = 3500;` una sola vez, igual a `WIRE_CAP` de `app/backend/bridge.py`. El sustituto `"result_too_large"` aparece | (f) `DSBX_WIRE_CAP = 4000` |
| M6 validadores | `ValidHello`, `ValidPoll`, `ValidAck` y `ValidOrder` existen y comprueban los campos de §3.5. Las respuestas solo se usan después de pasar su validador | (g) quitar la comprobación de `ok` en `ValidHello` |
| M7 guarda de efectos | Cada paso de `scene.apply` (funciones `StepRetirar` y `StepAnotar`) empieza llamando a `EffectGuard(`. `EffectGuard` mira `lease` y `plazo_local` | (h) quitar `EffectGuard` de `StepAnotar` |
| M8 dedup primero | En `HandleOrder`, la consulta de la caché va antes de cualquier comprobación de `stale_*` o `expired` | (i) mover la comprobación de `expired` antes de la caché |
| M9 contrato del cable | Los escritores a mano emiten todas las claves que exige `app/backend/bridge.py`: hello y sus campos de servidor, resultado con `generation` incluso `null`, página de catálogo. Las clases de lectura tienen los miembros de las respuestas del bridge. La prueba lee las claves de `bridge.py` o de una lista fija con su cita | (j) quitar `"generation"` del escritor del `read` |
| M10 epoch | `DSBX_RPC_EPOCH` ≥ 1 000 000. El cliente no se presenta sin epoch: el estado `SIN_CONFIG` comprueba el epoch antes de `HELLO`. `Event_OnRPC.Insert` y `.Remove` aparecen exactamente una vez cada uno | (k) presentarse sin epoch |
| M11 codificación | UTF-8 sin BOM y solo LF en todo `DayZSandbox/` | (l) un CRLF |

**X4:** el orquestador aplica cada mutación (a)-(l) sobre una copia y comprueba que cae la regla de su fila. Si cae otra o no cae ninguna, la regla está mal.

### 5.3 PBO: `qa/build_core_pbo.py` (nuevo)

Toma el patrón de `build_pbo.py` de F0.3-0, que hoy vive fuera del repo, en `C:\tmp\dsbx-f030-work\tools\`:
1. exige el árbol limpio;
2. saca `DayZSandbox/` de HEAD con `git -c core.autocrlf=false archive`;
3. empaqueta con AddonBuilder: `[AB, stage, out/@DayZSandbox/Addons, "-prefix=DayZSandbox", "-temp=…", "-clear", "-packonly"]`, siempre con argumentos;
4. vuelve a leer el PBO y compara cada fichero byte a byte (sha256) con HEAD;
5. comprueba que el repo sigue limpio.

Escribe `build_core_pbo.json` con el sha de HEAD, la lista y los hashes. Sin sello de compilación en esta parte.

### 5.4 Pruebas de `app/tools/peer_config.py`

Van en `app/tests/test_peer_config.py`:
- escribe `dsbx_peer.json` con la URL de `bridge_port` y la `peer_key` de un `backend.json` de prueba, con escritura atómica;
- crea la carpeta si no existe;
- sale con 2 y sin escribir nada si falta `peer_key`;
- no imprime la clave en ningún caso.

## 6. Gate en partida (después, F1b-peers en partida)

Va después del gate en partida de F0.3-0. Usa el OK fijo de Guillermo para partidas, con el lease de GPU como mutex, ningún DayZ ajeno abierto y cerrando solo los PID propios por WM_CLOSE. Lo que tiene que medir:

| # | Qué |
|---|---|
| G1 carga | El PBO carga en servidor y cliente retail con BattlEye. Hay que resolver cómo se firma o se acepta el PBO (F0.2 lo hizo así; el brief de F0.2, línea 359) |
| G2 handshake | Los dos peers se presentan. El cliente lleva el epoch del servidor (`client_in_world`). El catálogo llega `complete`, con `n_classes > 0` |
| G3 D2 | Desde la web, `apply` → pendiente → ejecutando → aplicado → observado con peers reales; con el predicado que no se cumple, `fallido/lectura_no_cumple` |
| G4 E1 en retail | Clave mala, sesión vieja, backend reiniciado y polls cortados → 0 efectos nuevos y la cola vieja sin ejecutar (fila E1 del plan, línea 174) |
| G5 hombre muerto | La ventana de cada peer, servidor y cliente: acepta hasta y rechaza desde, alrededor de `lease_ms` |
| G6 reloj | El ritmo de `GetTickTime()` frente al reloj monotónico del backend, en marcha normal y con un tirón o una pausa del servidor, y la cota de 100 ms para un efecto ya empezado (brief de F1b-bridge §11) |
| G7 lo que no se sabe sin motor | Dos peticiones en vuelo a la vez (con un acuse retenido 4 s, los `deliver=0` siguen cada 500 ms). Cómo lee `JsonSerializer` un `bool` y un entero en `float`. Una página de catálogo cerca de `WIRE_CAP` aceptada. Los plazos de `SetOption` |
| G8 `WIRE_CAP` | Con las cifras del gate en partida de F0.3-0, se ajusta el entero en los dos lenguajes si hace falta |

**El PR de esta parte no se mergea hasta que G1-G7 pasen**, porque toca el PBO (regla de Guillermo).

## 7. Ficheros

```
DayZSandbox/                                      §2-§3          [esqueleto: orquestador; lógica: F1bp-1]
  $PBOPREFIX$, include.lst, config.cpp
  scripts/3_Game/DSBX_Const.c                     constantes, WIRE_CAP, id del RPC
  scripts/3_Game/DSBX_Messages.c                  clases de lectura (§3.5)
  scripts/3_Game/DSBX_Wire.c                      escritores a mano y filtro de caracteres (§3.8, §3.11)
  scripts/3_Game/DSBX_Cache.c                     caché, retención y FIFO (§3.6)
  scripts/3_Game/DSBX_World.c                     epoch, generación y read (§3.7)
  scripts/3_Game/DSBX_Catalog.c                   catálogo en páginas (§3.9)
  scripts/3_Game/DSBX_Peer.c                      máquina de estados, canales, verbos, Log (§3.1-§3.4, §3.10, §3.12)
  scripts/5_Mission/DSBX_Mission.c                ganchos y RPC del epoch (§2.2, §3.10)
DayZSandbox_dev/
  plans/2026-11-15-m1-f1b-peers-brief.md          este brief                     [orquestador]
  app/tools/peer_config.py                        §3.1                           [F1bp-1]
  app/tests/test_peer_config.py                   §5.4                           [F1bp-1]
  app/tests/test_mod_static.py                    §5.2                           [F1bp-1]
  qa/build_core_pbo.py                            §5.3                           [F1bp-1]
```

**No se tocan:** `app/backend/`, `app/web/`, `fake_mod.py` y las pruebas existentes. `server.py`, `bridge.py` y `fake_mod.py` los están cableando F2 y F6-web.

## 8. Entrega

| Tanda | Quién | Escribe |
|---|---|---|
| Esqueleto | Orquestador | `$PBOPREFIX$`, `include.lst` y `config.cpp`, más los `.c` vacíos con sus clases, para que el linter tenga árbol |
| F1bp-1 | El primer worker libre, por la cadena acordada: Muse → Argon → Carbon → DeepSeek en el GX10 | La lógica de §3, las herramientas y las pruebas de §5 |

Cada tanda trabaja en una copia aparte del commit congelado. El orquestador:
- revisa el diff;
- corre el gate y X4 sin fiarse de los recibos;
- integra y hace commit.

Después revisa el código Sol, como mucho en 2 rondas; luego, el experto de Enforce, con el texto que el orquestador deja a Guillermo. Push y PR con la palanca de Guillermo. **Merge solo con §6 en verde.**

## 9. Riesgos y lo que no se ha medido

- **Sin motor no hay prueba de comportamiento.** El mod falso acredita el contrato y esta parte, la forma. Lo que hace el mod en el motor solo lo dice §6.
- **`GetTickTime()`** durante pausas o tirones (G6). Si se para, el plazo local cae tarde en tiempo real. Si G6 lo confirma, se cambia la fuente de reloj del peer en esta misma tarea.
- **Concurrencia del `RestContext`.** Si el motor atiende las peticiones en serie, un acuse lento corta el mantenimiento hasta 3 s, y el lease es de 3 s. Si G7 lo confirma, la alternativa es un segundo `RestContext` sobre la misma URL, y hay que ver si `GetRestContext` devuelve uno nuevo. Se decide entonces.
- **`modset_hash` no es criptográfico.** Basta para versionar el catálogo por modset (#8), pero no para nada que necesite resistencia a colisiones buscadas.
- **El catálogo de vanilla** puede pasar de cien páginas y se sube con cada sesión nueva del backend. Es local y se gasta de presupuesto lo que se crea, no lo que se reusa.
- **Firma del PBO en retail con BattlEye:** no está resuelta (G1).
- **`WIRE_CAP = 3500` es provisional** hasta las cifras en partida de F0.3-0 (G8).

## 10. Cambios por la revisión

(vacío: v1.0)
