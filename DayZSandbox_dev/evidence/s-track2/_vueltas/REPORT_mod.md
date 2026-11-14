# S-track·2 — informe del mod (sesión «mod», Muse)

Workspace: `C:\tmp\dsbx-strack2\mod\DayZSandbox_dev\qa\strack\DZS_STrack\` (base `2dab484`).
Alcance: brief §2 / CONTRACT §7–§11. Sin commits, sin lanzar DayZ, sin tocar CONTRACT/brief.

> Informe redactado por tramos durante la implementación (se actualiza al cerrar cada bloque).

## 0. Mapa cliente/servidor (antes de codificar)

| Dato | Cliente | Servidor | Puente |
|---|---|---|---|
| caso (`ropa`/`suave*`) | args `-strack*` / `strack_args.txt` | lo necesita para vestir / crear la lata | `ScriptInputUserData` nuevo `STRACK_UDT_CASE` (int), reenvío periódico del cliente; fallback local si no hay multijugador |
| mochila/mira/silenciador | réplicas (lectura de poses) | `CreateAttachment` al conocer el caso y haber arma en manos | replicación del motor |
| lata `Pot` | réplica localizada por barrido `GetObjectsAtPosition` | crea con `CreateObject`, mueve con `SetPosition` cada 2 s | replicación del motor |
| `samples.jsonl`, BMP, `done.json`, `preflight.json` | los escribe el cliente | — | ficheros `$profile:strack/<run>/` |

## 1. Firmas del motor verificadas

El árbol `P:\scripts` no está montado en esta copia (no existe la unidad `P:`).
La verificación se hizo sobre el extract vanilla 1.30 de la misma máquina,
`E:\DayZ-Stable-Extract\1.30.164200\P-scripts\` (mismos relativos que `P:\scripts\`).
Se cita la ruta del contrato (`P:\scripts\...`) con la línea comprobada en ese extract.

| Firma | Cita (línea verificada en el extract 1.30) |
|---|---|
| `proto native EntityAI CreateAttachment(string typeName)` | `P:\scripts\3_game\systems\inventory\inventory.c:209` |
| `proto native EntityAI GetEntityInHands()` | `P:\scripts\3_game\systems\inventory\humaninventory.c:16` |
| `proto native EntityAI CreateInHands(string typeName)` (ya usado) | `P:\scripts\3_game\systems\inventory\humaninventory.c:44` |
| `proto native GameInventory GetInventory()` | `P:\scripts\3_game\entities\entityai.c:1884` |
| `proto native int AttachmentCount()` / `GetAttachmentFromIndex(int)` | `P:\scripts\3_game\systems\inventory\inventory.c:218-224` (bloque `CreateAttachment`/`FindAttachment`) |
| `proto native EntityAI FindAttachment(int slot)` | `P:\scripts\3_game\systems\inventory\inventory.c:224` |
| `EntityAI FindAttachmentBySlotName(string)` | `P:\scripts\3_game\entities\entityai.c:1897` |
| `proto static void MatrixToQuat(vector mat[3], out float d[4])` | `P:\scripts\1_core\proto\enmath3d.c:360` |
| `proto static void QuatToMatrix(float q[4], out vector mat[3])` | `P:\scripts\1_core\proto\enmath3d.c:364` |
| `proto static void QuatLerp(out float qout[4], float q1[4], float q2[4], float frac)` | `P:\scripts\1_core\proto\enmath3d.c:397` |
| `proto static void MatrixMultiply4(vector[4], vector[4], out vector[4])` | `P:\scripts\1_core\proto\enmath3d.c:167` |
| `proto static void MatrixInverse4(vector mat[4])` | `P:\scripts\1_core\proto\enmath3d.c:224` |
| `proto static void DirectionAndUpMatrix(vector, vector, out vector[4])` | `P:\scripts\1_core\proto\enmath3d.c:150` |
| `proto external void GetTransform(out vector mat[])` | `P:\scripts\1_core\proto\enentity.c:288` |
| `proto native external void SetTransform(vector mat[4])` | `P:\scripts\1_core\proto\enentity.c:356` |
| `proto external void GetRenderTransform(out vector mat[])` | `P:\scripts\1_core\proto\enentity.c:303` |
| `proto native vector GetPosition()` / `SetPosition(vector)` | `P:\scripts\1_core\proto\enentity.c:287` / `:294` |
| `proto native void GetBoneTransformMS/WS(int, out vector[4])` | `P:\scripts\3_game\entities\object.c:247-248` |
| `proto native vector GetWorldPosition()` | `P:\scripts\3_game\entities\object.c:291` |
| `proto native int GetBoneIndexByName(string)` (en `Human`) | `P:\scripts\3_game\human.c:1417` |
| `proto native vector GetMemoryPointPos(string)` / `MemoryPointExists(string)` | `P:\scripts\3_game\entities\object.c:452-454` |
| `proto vector GetSelectionPositionMS/WS(string)`, `ModelToWorld(vector)` | `P:\scripts\3_game\entities\object.c:864-873` |
| `proto native Object CreateObject(string, vector, bool, bool, bool, bool)` | `P:\scripts\3_game\global\game.c:691` |
| `proto native float GetTickTime()`, `proto int GetTime()` | `P:\scripts\3_game\global\game.c:914`, `:1534` |
| `proto native float SurfaceY(float, float)` | `P:\scripts\3_game\global\game.c:1176` |
| `proto native void GetPlayers(out array<Man>)` | `P:\scripts\3_game\global\game.c:945` |
| `proto native void GetObjectsAtPosition(vector, float, out array<Object>, out array<CargoBase>)` | `P:\scripts\3_game\global\game.c:923` |
| `proto native void DisableSimulation(bool)` (en `Entity`) | `P:\scripts\3_game\entities\entity.c:3` |
| `Math.Acos/Cos/Sin/Sqrt/Clamp/AbsFloat`, ctes `PI/DEG2RAD/RAD2DEG` | `P:\scripts\1_core\proto\enmath.c:379,343,331,305,540,225,12-17` |
| `OnInputUserDataProcess` vanilla (base del override ya presente) | `P:\scripts\4_world\entities\manbase\playerbase.c:6531` |

Clases vanilla (dadas por verificadas por el orquestador en el encargo; no re-verificadas
aquí por no estar `P:\DZ` montado): `AliceBag_Green`, `ACOGOptic`, `M4_Suppressor`, `Pot`.

## 2. Ficheros cambiados y líneas nuevas aprox.

Recuento neto frente a la base (`git diff --no-index --stat` contra
`C:\tmp\dsbx-strack2\merge\...\DZS_STrack`: 1110 inserciones / 22 borrados en total):

| Fichero | Líneas nuevas netas aprox. |
|---|---|
| `scripts/3_Game/STRACK_Math.c` | +129 |
| `scripts/4_World/STRACK_Move.c` | +88 |
| `scripts/4_World/STRACK_Server.c` (nuevo) | +130 |
| `scripts/4_World/STRACK_Session.c` | +735 |
| `scripts/5_Mission/STRACK_Mission.c` | +6 |

Total ≈ +1090 líneas netas, por encima del «< 400 orientativo» del brief §2.
Causa: el contrato §8–§11 exige por línea JSONL muchos campos nuevos con sus
productores (preflight con ordenación de `dt`, poses (a)/(f) de cinco entidades,
filtro con tres modos, guion de cuatro tramos con búsqueda del rumbo base y
localización de la lata), y cada bloque va duplicado en su variante (a)/(f) o
servidor/cliente sin compartir código entre capas. No se ha recortado ningún
campo del contrato para acercarse a la cifra.

## 3. Por punto del brief §2 / contrato §7–§11

### §7 Argumentos y corridas nuevas

- Casos `ropa`, `suave30`, `suave60`, `suave144` aceptados en
  `AcceptArgs` ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:402)),
  con la misma forma de rechazo con log que los casos de S-track·1.
- `-strack_fps_cap=<N>` (CLI y `strack_fps_cap=` en `strack_args.txt`), por
  defecto 60 ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:306)).
- Hooks: `ropa` acepta Ha/Hb/Hc (Hc deja de rechazarse en `ropa`, como en
  `mount0`); `suave*` solo Hb. Inyecciones `smooth03`/`quatlerp`/`longarc`
  solo en `suave*`; `delay1`/`roll` rechazados en `suave*`.
- Nombres de corrida sin cambio de formato (`<caso>_<hook>[_<inject>]`), p. ej.
  `suave60_Hb_quatlerp`.
- El servidor conoce el caso por un canal nuevo `STRACK_UDT_CASE = 78541092`
  junto al existente `STRACK_UDT_MOVE`: el cliente lo reenvía cada 60 ticks
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:107),
  envío desde [STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:222));
  el servidor lo lee en `OnInputUserDataProcess` comprobando `ctx.Read`
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:130)).
  Sin multijugador queda el código en una estática local del mismo proceso.

### §8 Preflight de FPS

- Tras la espera de `-strack_wait` con el arma en manos y antes de armar,
  10 s de `dt` sin capturas ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:500)).
  Ordenación por inserción y percentiles p50/p95 sobre la muestra.
- Umbral `max(18, 1.08*1000/fps_cap)` ms. Si el p50 lo supera: no arma, no
  escribe `samples.jsonl`, escribe `done.json` con
  `{"run":..,"ok":false,"causa":"fps","dt_p50_ms":..,"umbral_ms":..,"n":..}`.
  Si pasa: `preflight.json` con `{"dt_p50_ms":..,"dt_p95_ms":..,"n":..,"umbral_ms":..}`
  y el `done.json` final añade `"preflight_dt_p50_ms"`.
- Log literal: `[STRACK] preflight fps p50=<ms> umbral=<ms> ok=<0|1>`.

### §9 Movimiento y captura

- Giro en el sitio: ganancia/máximo del lazo de `OverrideAimChangeX`
  reescalados por el factor medido en S-track·1 (1,75 s → 4,0 s:
  `s_AimGain` 0,002→0,000875, `s_AimMax` 0,08→0,035) y paso escalado por
  `dt*60` para que la duración no dependa del FPS
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:22),
  `dt` llega desde `CommandHandler(pDt)`). Se conserva el log
  `[STRACK] move giro fin ... t=<s>`.
- Cada línea lleva `"giro"` (0 fuera; 1–3 en el giro n-ésimo del guion
  `self`; en `suave*`, 1 = +170° y 2 = −170°) y `"seg"` = `s_Seg`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1562)).
- Captura: `frame % 2 == 0` con `giro > 0`, `frame % 10 == 0` fuera;
  `calib` sin cambio ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1406)).

### §10 Ropa

- Servidor ([STRACK_Server.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:42)):
  al conocer el caso y haber arma en manos, `CreateAttachment("AliceBag_Green")`
  sobre el jugador y `CreateAttachment("ACOGOptic")` /
  `CreateAttachment("M4_Suppressor")` sobre el M4A1, un solo intento; cada
  fallo deja `[STRACK] ropa <clase> fallo` y la corrida sigue.
- Cliente: cada línea de `ropa` lleva `"ropa"` con `mochila`, `mira`,
  `silenciador`, `spine3` y `arma`, cada uno `{"a":POSE,"f":POSE}` o `null`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1518)).
  Entidades: (a) = `GetTransform` tal cual, (f) = mismos ejes con
  `GetWorldPosition()`; `Spine3`: (a) = `GetBoneTransformWS`, (f) = matriz del
  jugador (con `GetWorldPosition`) × `GetBoneTransformMS`. Posiciones
  relativas al origen, ejes = columnas 0–2.
- `lecturas` añade el punto `"mira"` con las seis lecturas (a)–(f) aplicadas a
  la entidad mira ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:894));
  el punto de memoria se busca entre `eye`, `eyepiece`, `lens`, `optic` con
  `MemoryPointExists` y se anuncia con `[STRACK] ropa punto mira=<nombre>`
  (ver DISPUTAS). Cámara como `mount0` (rama existente de `BuildPose`).

### §11 Suave

- Servidor ([STRACK_Server.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:69)):
  crea la `Pot` a 3 m delante del jugador sobre el suelo
  (`SurfaceY`, `DisableSimulation(true)`), la mueve 1 m en horizontal cada
  2 s sobre el eje X fijo alternando base/base+1 m con `SetPosition`, y por
  salto escribe `[STRACK] suave salto i=<n> frame_srv=<frame> t_srv_ms=<ms> pos=[x,y,z]`
  (`frame_srv` = contador propio de `MissionServer.OnUpdate`;
  `t_srv_ms` = `GetTime()`). El gancho es
  [STRACK_Mission.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/5_Mission/STRACK_Mission.c:81).
- Cliente ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1164)):
  localiza la lata replicada por barrido `GetObjectsAtPosition` (sin padre de
  inventario), cámara `follow` sobre ella con hook Hb, jugador quieto (no se
  arranca `STRACK_Move` en `suave*`).
- Guion: tramo 1 (10 s) `smooth_s` 0; tramo 2 (10 s) 0,3; tramo 3 (10 s) 0,8;
  tramo 4 con la lata quieta y `smooth_s` 0,3: a los 0,5 s la orientación
  deseada salta +170° (`giro`=1, 4 s) y después −170° de vuelta al rumbo base
  (`giro`=2, 4 s); fin con `done.json` a los 38,5 s. Con
  `inject=smooth03`, `smooth_s` = 0,3 en todos los tramos.
- Filtro: el de `mount03` vía `SlerpMode`
  ([STRACK_Math.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/3_Game/STRACK_Math.c:260)):
  modo 0 = `Slerp` de arco corto (misma fórmula que `STRACK_Math.Slerp`),
  modo 1 (`quatlerp`) = `Math3D.QuatLerp` normalizado, modo 2 (`longarc`) =
  la misma slerp sin invertir el signo con producto escalar < 0. Posición con
  lerp por `alpha = 1 - exp(-dt/smooth_s)` (`STRACK_Math.Exp`; alpha = 1 si
  `smooth_s` = 0).
- Rumbo base del tramo 4 `[DESIGN]`: al armar `suave*` se prueban ocho
  rotaciones base (0, ±45, ±90, ±135, 180) y se elige la de menor producto
  escalar previsto entre el cuaternión de partida y el objetivo de +170°
  (si ninguna da < 0 se queda 0); queda en el log
  `[STRACK] suave base_rot=<g> dot_previsto=<d>`. La rotación base se aplica
  desde el primer tramo para no introducir un transitorio en el tramo 4.
  En el primer frame de cada giro se escribe `"quat_dot_inicio": d`.
- Campos por línea en `suave*`: `"tramo"`, `"smooth_s"`, `"fps_cap"`,
  `"lata":{"a":[x,y,z]}` (posición leída en el cliente, relativa al origen),
  `"cam_raw":{"pos","x","y","z","q"}` (pose deseada antes del filtro) y en
  `"cam"` además `"q":[x,y,z,w]` de `MatrixToQuat` sin renormalizar
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1596)).
- Lo demás no se toca: lecturas (a)–(f), hooks H-a/H-b/H-c, formato JSONL
  existente y origen relativo; `giro`/`seg` son los únicos campos añadidos
  a las líneas de los casos antiguos.

## 4. Gate

Comando literal (esta copia):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal (tras sustituir los tres `GetType() ==` por `IsKindOf`, ver abajo):

```json
{
  "addon_root": "C:\\tmp\\dsbx-strack2\\mod\\DayZSandbox_dev\\qa\\strack\\DZS_STrack",
  "status": "PASS",
  "errors": [],
  "warnings": [],
  "info": {
    "files_scanned": 6,
    "elapsed_ms": 2309,
    "skipped_checks": [
      {"rule_id": "ES-UNDEFINED-CLASS-REF", "status": "SKIP", "reason": "vanilla tree not found. Set --vanilla-root or DAYZ_VANILLA_ROOT, or place the tree at P:\\scripts. ..."},
      {"rule_id": "ES-VARIABLE-NAMED-AS-TYPE", "status": "SKIP", "reason": "vanilla tree not found. ..."},
      {"rule_id": "ES-UNDEFINED-BUILTIN-METHOD", "status": "SKIP", "reason": "vanilla tree not found. ..."}
    ]
  }
}
```

Criterio `"errors": []`: cumplido (también `warnings: []`).

Comando literal (base, solo lectura):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal de la base: `"status": "PASS"`, `"errors": []`, `"warnings": []`,
`files_scanned: 5`, con los mismos tres checks en SKIP.

Warnings nuevos respecto a la base: ninguno. En la primera pasada aparecieron
tres `ES-GETTYPE-EXACT-MATCH` en código nuevo (identificación de
accesorios/lata); se sustituyeron por `IsKindOf`, que además es la forma que
pide la regla 31 de `enforce-script-reference`, y el gate quedó en PASS limpio.

Comprobación extra (no exigida): con
`$env:DAYZ_VANILLA_ROOT='E:\DayZ-Stable-Extract\1.30.164200\P-scripts'` el
mismo comando sobre esta copia da también `"status": "PASS"`, `"errors": []`,
`"warnings": []`, ya sin checks en SKIP (38 s), es decir, con
`ES-UNDEFINED-CLASS-REF`, `ES-VARIABLE-NAMED-AS-TYPE` y
`ES-UNDEFINED-BUILTIN-METHOD` ejecutados contra el árbol 1.30.

## 5. DISPUTAS

- **D1 — punto de memoria de la mira.** El contrato §10 pide «un punto de
  memoria de la mira que elige el mod» sin nombrarlo, y el nombre vive en el
  `.p3d` del `ACOGOptic`, no accesible desde esta copia. Implementación: se
  prueban `eye`, `eyepiece`, `lens`, `optic` con `MemoryPointExists` y se
  anuncia el elegido; si ninguno existe se usa el origen de la mira
  (`mp = 0,0,0`) y las lecturas (b)/(c) caen a `ModelToWorld(mp)` en vez de a
  las selecciones. Si en partida sale `punto mira=origin`, el evaluador
  debería saber que el «detalle de la mira» es su origen, no un punto de
  memoria. No he cambiado el contrato; queda escrito aquí.
- **D2 — `frame_srv`.** El contrato §11 pide `frame_srv=<frame>` sin fijar el
  contador. No hay un contador de frames de servidor expuesto a script que
  haya verificado; uso el contador propio de `MissionServer.OnUpdate`
  (incrementa por tick de misión, arranca en 1 al cargar el mod). Si el
  evaluador espera otro origen de frames, este campo no casará.
- **D3 — duración del giro.** El factor de reescalado (×0,4375 sobre ganancia
  y máximo) es analítico a partir del «~1,75 s» del brief, no medido en esta
  copia; el escalado por `dt` supone que `OverrideAimChangeX` actúa como
  incremento por llamada. Solo la corrida en partida puede confirmar los
  4,0 ± 0,3 s del log `move giro fin`.

## 6. LO QUE NO PUDE VERIFICAR

- Todo lo que solo se ve en partida (PBO, logs de cliente/servidor, FPS reales,
  duración real del giro, replicación de la lata y de los accesorios): el encargo
  reserva esa corrida al orquestador.
- El árbol `P:\scripts` / `P:\DZ` no está montado en esta copia; las firmas se
  verificaron en el extract 1.30 citado en §1 de este informe. Las clases
  `AliceBag_Green`, `ACOGOptic`, `M4_Suppressor` y `Pot` se dan por
  verificadas por el orquestador (encargo, «Hechos verificados»).
- Si `MatrixToQuat` devuelve siempre cuaterniones canónicos, ningún rumbo
  base da producto escalar < 0 para un salto de 170° y `longarc` podría no
  ser observable (el código lo deja en `base_rot=0` y lo anuncia en el log
  con `dot_previsto`); eso solo se resuelve en partida.
- Que la `Pot` replicada sea la única `Pot` sin padre a menos de 15 m del
  jugador en el banco (la búsqueda toma la primera que cumple).
- El comportamiento de `DisableSimulation(true)` sobre la `Pot` replicada y
  la llegada exacta de cada `SetPosition` al cliente (la «entrada leída» es
  la posición del cliente, como pide el contrato).

## 7. Vuelta 2 (revisión Sol)

Sin tocar las dos decisiones del orquestador (umbral de `suave30` y captura
de `calib` quedan como estaban). `P:\scripts` sigue sin montar en este
sandbox (solo unidades C/D/E); las firmas nuevas se verificaron en el
extract vanilla 1.30 `E:\DayZ-Stable-Extract\1.30.164200\P-scripts\` con el
mismo relativo `P:\scripts\...`: `Math.Pow`/`Math.EULER`
(`1_core/proto/enmath.c:183`, `:11`; modismo vanilla `Pow(EULER,-mean)` en
`:710`), `Math.Floor` (`enmath.c:427`), `Object.GetNetworkID`
(`3_game/entities/object.c:819`), `ScriptRPC.Send`
(`3_game/gameplay.c:117`), `Object.OnRPC` (`3_game/entities/object.c:860`,
override vanilla en `4_world/entities/manbase/playerbase.c:5727`),
`Object.MemoryPointExists` (`3_game/entities/object.c:454`) y
`memoryPointCamera = "eyeScope"` de la `ACOGOptic`
(`DZ/weapons/attachments/optics/config.cpp:485`, `OpticsInfo` en `:503`).

### 7.1 BLOQ 1 — la lata ya no salta en el tramo 4

El hilo `STRACK_UDT_CASE` lleva ahora `code + tramo + fin`:
[STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:118)
(`SendCaseState`), con cada `ctx.Read` comprobado en
[STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:152).
El cliente manda inicio al armar
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:740)),
cada cambio de tramo al detectarlo
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1318)),
el fin en `Finish`
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1744))
y un reenvío periódico con el tramo vigente
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:268)).
El servidor no crea ni mueve la lata si `ServerPotFrozen()`
(tramo 4 o fin, [STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:194))
en [STRACK_Server.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:92);
en single-player el mismo estado viaja por las estáticas locales.

### 7.2 BLOQ 2 — poses de ropa congeladas en el hook

`Capture` congela `giro`, `seg` y el JSON de ropa en el mismo hook y frame
que la cámara y las lecturas
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:815),
[STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:819));
`WriteLine` solo serializa esos valores
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1661),
[STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1692)),
sin consultar entidades en el `OnUpdate` siguiente.

### 7.3 BLOQ 3 — preflight sin muestras viejas

`ResetPreflight` limpia `m_PfStarted`, `m_PfT0` y `m_PfDts`
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:546))
y se llama al perder jugador, inventario o arma durante la espera
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:651)):
la siguiente espera mide 10 s nuevos.

### 7.4 BLOQ 4 — `quat_dot_inicio` antes del filtro

El producto se calcula entre el cuaternión filtrado anterior (o el objetivo
sin filtrar si aún no había filtro) y el objetivo nuevo, antes de tocar
`m_Filt`
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1410)).

### 7.5 BLOQ 5 — `Exp` estable en [−50, 0]

`STRACK_Math.Exp` ([STRACK_Math.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/3_Game/STRACK_Math.c:8))
reduce por ln 2 con división de Cody-Waite (`n·HI` exacto en float),
Taylor de 14 términos sobre `|r| ≤ 0,35` y escalado exacto por `2^n`.
Medido fuera del motor simulando float32 operación a operación sobre
200 001 puntos de [−50, 0]: error relativo peor 2,54e-07 (< 1e-6); la vía
`Math.Pow(Math.EULER, x)` da 1,57e-06 en `x ≈ −49,9` y no basta, por eso
no se usa pese a existir la nativa citada arriba.

### 7.6 MAY 6 — punto de la mira real o `null`

Se prueban `eyeScope`, `eyeIronsights`, `cameraDir` y
`cameraDirIronsights` con `MemoryPointExists`
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:990))
y el elegido queda en `[STRACK] ropa punto mira=<nombre>`; sin ninguno se
registra `punto mira=ninguno`
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1008)),
las seis lecturas quedan a cero y `lecturas` emite `"mira":null` en vez de
copiar el origen en otras lecturas.

### 7.7 MAY 7 — la lata se identifica por network id

Al crear la `Pot`, el servidor lee su `GetNetworkID` y lo manda al cliente
dueno por `ScriptRPC` garantizado (`STRACK_RPC_POT`,
[STRACK_Server.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:122),
[STRACK_Server.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:129));
el cliente lo recibe en `OnRPC` con cada `ctx.Read` comprobado
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:19))
y `FindLata` solo acepta la `Pot` cuyo id coincide, sin medir hasta
resolverla
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1239)).
En single-player el id se entrega por la estática `SetPotId`
([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:155)).

### 7.8 Gate (vuelta 2)

Comando literal (esta copia):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal: `"status": "PASS"`, `"errors": []`, `"warnings": []`,
`files_scanned: 6`, con los mismos tres checks en SKIP que en la vuelta 1.

Comando literal (base, solo lectura):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal de la base: `"status": "PASS"`, `"errors": []`,
`"warnings": []`, `files_scanned: 5`, mismos SKIP. Warnings nuevos: ninguno.

Comprobación extra: con
`$env:DAYZ_VANILLA_ROOT='E:\DayZ-Stable-Extract\1.30.164200\P-scripts'` la
copia da también `"status": "PASS"`, `"errors": []`, `"warnings": []` sin
checks en SKIP, es decir con las referencias vanilla (incluidas
`Math.Floor`, `GetNetworkID`, `ScriptRPC` y el override de `OnRPC`)
resueltas contra el árbol 1.30.

Sin verificar en esta vuelta (solo se ve en partida): que el RPC de la lata
llegue antes de la primera medida útil, que el servidor deje la lata quieta
al entrar el tramo 4 con el nuevo hilo, y qué nombre de punto anuncia la
ACOG real (`eyeScope` es el del config; el del `.p3d` solo se confirma con
`MemoryPointExists` en partida).

## 8. Vuelta 3 (revisión Sol + contrato §16)

Firmas nuevas verificadas en el extract vanilla 1.30
(`E:\DayZ-Stable-Extract\1.30.164200\P-scripts\`, mismo relativo
`P:\scripts\...`): `ScriptRPC.Send`
(`P:\scripts\3_game\gameplay.c:117`),
`ScriptInputUserData.Send` (`P:\scripts\3_game\gameplay.c:126`) y
`proto native static bool CanStoreInputUserData()`
(`P:\scripts\3_game\gameplay.c:131`; el encargo lo citaba en :130).

Mapa cliente/servidor de esta vuelta:

| Dato | Cliente | Servidor | Puente |
|---|---|---|---|
| parada tramo 4 pendiente | `s_Pend*` en `STRACK_Move`, reintento por frame | `s_ServerTramo=4` ⇒ `ServerPotFrozen()` corta `TickPot` | `STRACK_UDT_CASE` (input user data), no se descarta si `CanStoreInputUserData()` es falso |
| confirmación de parada | `STRACK_Move.FrozenAckReceived()` / ramas SP y listen-server | envía al recibir tramo 4 o `fin` | `ScriptRPC` garantizado `STRACK_RPC_POT_ACK = 78541094`, servidor ⇒ dueño |
| lata válida antes de armar | `FindLata` exige `Pot` sin padre con network-id coincidente | crea la `Pot` y entrega su network-id (`STRACK_RPC_POT`, vuelta 2) | replicación + ese RPC previo |

### 8.1 BLOQ — la parada de la lata ya no se pierde al entrar en el tramo 4

- `SendCaseState` ya no descarta el aviso: guarda
  `s_PendCaso/s_PendTramo/s_PendFin` y llama a `FlushPending`
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:128),
  [STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:155)).
  Si `CanStoreInputUserData()` es falso queda `s_PendActive` y se reintenta
  cada frame desde `Tick`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:286));
  el reenvío periódico de 60 ticks no pisa un pendiente
  (`!STRACK_Move.HasPending()` en ese mismo `Tick`, y `SendCaseState` se
  niega a sobrescribir un pendiente con un tramo distinto que no sea 4/`fin`).
  En SP el pendiente se cierra al instante: las estáticas locales ya son el
  estado del servidor en el mismo proceso.
- Confirmación de vuelta: al leer tramo 4 o `fin`, el servidor manda
  `STRACK_RPC_POT_ACK` garantizado al dueño
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:250),
  `ReadCase(this, ctx)` en
  [STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:540));
  el cliente lo recibe en `OnRPC` comprobando cada `ctx.Read` y lo anota con
  `NoteFrozenAck`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:26),
  [STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:201)).
  En SP la confirmación es `ServerPotFrozen()` sobre las estáticas locales;
  en listen-server se acepta también esa vía (mismo proceso), sin usarla en
  un cliente remoto, donde `s_LocalTramo` daría un falso positivo.
- El reloj del tramo 4 no arranca sin confirmación:
  `SuaveTramo4Gate`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:686))
  pide la parada a los 30 s, mantiene `tramo=3`/`smooth_s=0,8` mientras
  espera (ninguna línea sale ya como tramo 4 con la lata aún libre,
  [STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1478))
  y solo al confirmar fija `m_Tramo4T0 = now`; los giros usan
  `t4 = m_Now - m_Tramo4T0`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1543))
  y la corrida termina a los 8,5 s de ese origen (0,5 + 4 + 4), no a los
  38,5 s desde `m_T0`. Tope de 3 s sin confirmación ⇒
  `WriteFailDone("lata_no_para")` escribe
  `done.json` con `ok:false, causa:"lata_no_para"`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:725)).

### 8.2 MAY — el guion ya no arranca antes de tener la lata

- Tras el preflight y **antes** de abrir `samples.jsonl`, crear la cámara,
  fijar `m_Origin`/`m_T0` o capturar, `TryArm` resuelve la lata con
  `FindLata` (network-id coincidente, `Pot` sin padre: validación de la
  vuelta 2) y solo entonces sigue el armado
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:823)).
  El servidor ya conoce el caso durante la espera/preflight por el envío
  periódico + pendiente de §8.1, así que puede crear la lata en ese tiempo.
- Si no aparece en 10 s desde el primer intento de ese gate,
  `WriteFailDone("sin_lata")` escribe `done.json` con
  `ok:false, causa:"sin_lata"` sin haber abierto `samples.jsonl`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:848)).

### 8.3 Contrato §16 — comprobación (sin cambio de umbrales)

- **`t_ms`/`dt`.** Cumple por construcción, sin tocar código: `Tick` fija
  `m_Dt = dt` (el `timeslice` de `MissionGameplay.OnUpdate` de ese frame)
  antes de capturar en Ha/Hc, y en Hb ese mismo `m_Dt` es el que ve
  `Capture` en `EOnPostFrame`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:314));
  `Capture` congela `m_Now = GetTickTime()` y `WriteLine` emite
  `t_ms = (m_Now - m_T0) * 1000`, es decir el final del intervalo `dt` de
  ese frame (en Hb la línea se vuelca en el `Tick` siguiente pero con el
  `m_Now`/`m_Dt` congelados, no re-leídos). El filtro de `suave*` usa ese
  `m_Dt` del propio frame:
  `alpha = 1 - Exp(-m_Dt / m_SmoothS)`
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1573)).
- **Entrada de T-suave.** Cumple, y el gate de §8.2 lo hace valer desde la
  primera línea: en cada `Capture` de `suave*`, `BuildPoseSuave` lee
  `m_LataPos = lata.GetWorldPosition()` en ese frame y construye la pose
  deseada con esa misma posición (`BuildFollow(m_LataPos, axesRot, raw)`),
  de modo que `cam_raw` (copia de `raw`) sigue a `lata.a` (el mismo
  `m_LataPos` relativo al origen) en el mismo frame, con el desplazamiento
  constante de `follow` (1,2 m atrás, 0,3 m arriba)
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1451),
  [STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1530)).
  No hay frame en que `cam_raw` salga de una posición de lata anterior:
  antes de §8.2 sí podía (líneas con `lata.a = null` y `cam_raw` viejo al
  principio); ahora esas líneas no existen porque no se captura sin lata.
- **Preflight de 30 fps.** Sin cambio: es la decisión del orquestador que
  §16 ratifica (umbral 36 ms en §8); el mod ya lo traía de la vuelta 1.

### 8.4 Gate (vuelta 3)

Comando literal (esta copia):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal: `"status": "PASS"`, `"errors": []`, `"warnings": []`,
`files_scanned: 6`, con los mismos tres checks en SKIP que en las vueltas
1–2 (exit 0).

Comando literal (base, solo lectura):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal de la base: `"status": "PASS"`, `"errors": []`,
`"warnings": []`, `files_scanned: 5`, mismos SKIP. Warnings nuevos: ninguno.

Comprobación extra: con
`$env:DAYZ_VANILLA_ROOT='E:\DayZ-Stable-Extract\1.30.164200\P-scripts'` la
copia da también `"status": "PASS"`, `"errors": []`, `"warnings": []` sin
checks en SKIP, es decir con las referencias vanilla (incluidos
`ScriptRPC.Send`, `CanStoreInputUserData` y el nuevo `OnRPC` de ACK)
resueltas contra el árbol 1.30.

Sin verificar en esta vuelta (solo se ve en partida): que el ACK
`STRACK_RPC_POT_ACK` llegue y el servidor congele la lata dentro de los 3 s
en multijugador real, que el reintento por frame recupere un
`CanStoreInputUserData()` falso transitorio al cruzar los 30 s, y que la
lata replicada aparezca dentro de los 10 s del gate de armado en el banco.
El `fin` que `WriteFailDone` intenta enviar tras un fallo puede quedar
pendiente si el canal sigue cerrado (la corrida ya ha acabado con
`ok:false`; el servidor se entera por el `done.json`, no por ese aviso).

## 9. Vuelta 4 (última)

Sin tocar nada de las vueltas 1–3 salvo los dos puntos de esta revisión.
Sin APIs nuevas: se reutilizan `ScriptRPC.Send`
(`P:\scripts\3_game\gameplay.c:117`), `ScriptInputUserData.Send`
(`P:\scripts\3_game\gameplay.c:126`) y `Object.GetNetworkID`
(`P:\scripts\3_game\entities\object.c:819`), ya verificadas en las
vueltas 2–3 contra el extract vanilla 1.30.

Mapa cliente/servidor de esta vuelta:

| Dato | Cliente | Servidor | Puente |
|---|---|---|---|
| tramo vigente tras pedir el 4 | `m_Tramo4Req` en la sesión y cerrojo `s_Tramo4Sent` en `STRACK_Move`; todo reenvío no-`fin` sale como 4 | `s_ServerTramo` monótono dentro de la corrida; un retroceso se ignora y se registra | `STRACK_UDT_CASE` (input user data), como en la vuelta 2 |
| identificador de la lata en corrida nueva | `s_PotIdOk`/`FindLata` sin cambio | `s_Pot` existente en `STRACK_Server`; al registrar la corrida nueva reenvía su network-id al dueño | `ScriptRPC` garantizado `STRACK_RPC_POT` (vuelta 2), reenviado |

### 9.1 BLOQ — desde que se pide el tramo 4, todo reenvío manda 4; el servidor ignora retrocesos

- Cliente, origen del reenvío: el reenvío periódico de 60 ticks ya no
  lee `m_Tramo` a secas (que sigue en 3 hasta el ACK): si
  `m_Tramo4Req` está activo manda 4
  ([STRACK_Session.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:294)).
- Cliente, cerrojo en el canal: `SendCaseState` levanta
  `s_Tramo4Sent` al pedir el tramo 4 y desde ahí fuerza a 4 cualquier
  reenvío que no sea `fin`, sea cual sea el tramo que pase el llamante
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:143));
  el `fin` de `Finish`/`WriteFailDone` lo baja, así que la corrida
  siguiente no hereda el cerrojo. Esto cubre también la vía local
  (`s_LocalTramo`, single-player/listen) que lee `ServerPotFrozen()`.
- Servidor: `ReadCase` ya no asigna `s_ServerTramo` a ciegas. Dentro
  de la misma corrida (sin `fin` desde el último tramo aceptado) un
  tramo menor que el vigente se ignora entero —no toca caso, tramo
  ni `fin`, y por tanto no descongela la lata— y queda en el log como
  `[STRACK] suave tramo retroceso ignorado recibido=<n> vigente=<m>`
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:277)).
  El `fin` siempre se acepta y marca el fin de corrida
  (`s_ServerRunEnded`); el primer tramo tras un `fin` —o tras una
  conexión nueva, ver §9.2— es la corrida siguiente y sí se acepta
  aunque sea menor. El ACK de parada de la vuelta 3 no cambia.

### 9.2 MAY — la corrida nueva recibe el identificador de la lata que ya existe

- Elección: **reenviar el identificador de la lata existente**, no
  borrarla y crear otra. Es más robusto porque la `Pot` ya está
  replicada en el cliente nuevo (solo le falta el network-id para
  aceptarla en `FindLata`): no hay ventana sin lata, ni carrera
  borrado/creación entre réplicas, ni hace falta una API de borrado
  nueva; el RPC garantizado es idempotente y puede repetirse en cada
  registro sin efecto lateral.
- Registro de corrida nueva en el servidor: el `fin` de la corrida
  anterior lo marca (§9.1) y, por si la corrida anterior acabó sin
  `fin` (cliente caído), `MissionServer.InvokeOnConnect` también lo
  marca con `ServerMarkNewRun`
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:166),
  llamada en
  [STRACK_Mission.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/5_Mission/STRACK_Mission.c:77)).
- Al aceptar ese primer mensaje `suave*` de la corrida nueva,
  `ReadCase` llama a `STRACK_Server.ResendPotId(player)`
  ([STRACK_Move.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:297)):
  si `s_Pot` existe, lee su `GetNetworkID` y lo manda al dueño por
  `STRACK_RPC_POT` garantizado, con el log
  `[STRACK] suave lata netid reenviado nueva corrida`; en el mismo
  proceso (SP/listen) además lo entrega por `STRACK_Session.SetPotId`,
  igual que la creación de la vuelta 2
  ([STRACK_Server.c](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:46)).
  Si aún no hay lata (primera corrida), no hace nada y vale el envío
  de la creación. La lata reutilizada conserva base y contador de
  saltos del servidor; al aceptarse el tramo 1 deja de estar
  congelada y reanuda el guion de saltos.

### 9.3 Gate (vuelta 4)

Comando literal (esta copia):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal:

```json
{
  "addon_root": "C:\\tmp\\dsbx-strack2\\mod\\DayZSandbox_dev\\qa\\strack\\DZS_STrack",
  "status": "PASS",
  "errors": [],
  "warnings": [],
  "info": {
    "files_scanned": 6,
    "elapsed_ms": 2808,
    "skipped_checks": [
      {"rule_id": "ES-UNDEFINED-CLASS-REF", "status": "SKIP", "reason": "vanilla tree not found. Set --vanilla-root or DAYZ_VANILLA_ROOT, or place the tree at P:\\scripts. ..."},
      {"rule_id": "ES-VARIABLE-NAMED-AS-TYPE", "status": "SKIP", "reason": "vanilla tree not found. ..."},
      {"rule_id": "ES-UNDEFINED-BUILTIN-METHOD", "status": "SKIP", "reason": "vanilla tree not found. ..."}
    ]
  }
}
```

Comando literal (base, solo lectura):

```
python C:/Users/guill/DayZ-Modding-Knowledge-Pack/tools/dayz-script-validator/scripts/script_validator.py C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/DZS_STrack
```

Salida literal de la base: `"status": "PASS"`, `"errors": []`,
`"warnings": []`, `files_scanned: 5`, mismos tres checks en SKIP.
Warnings nuevos respecto a la base: ninguno.

Comprobación extra: con
`$env:DAYZ_VANILLA_ROOT='E:\DayZ-Stable-Extract\1.30.164200\P-scripts'`
la copia da también `"status": "PASS"`, `"errors": []`,
`"warnings": []` y ningún check en SKIP (`elapsed_ms: 12640`), es
decir con las referencias vanilla de los dos fixes (incluido el nuevo
llamado `STRACK_Server.ResendPotId` desde `STRACK_Move`) resueltas
contra el árbol 1.30.

Sin verificar en esta vuelta (solo se ve en partida): que tras el ACK
ningún salto de lata reaparezca al cruzar un reenvío periódico, que
el log de retroceso salga si llega un tramo viejo en multijugador
real, y que una segunda corrida `suave*` con el servidor vivo reciba
el reenvío del netid y arme sin `sin_lata` reutilizando la misma
`Pot`.

