# F3: adaptador de Expansion AI (el motor de actores real, sin partida)

2026-11-27 · tarea **F3-adaptador**, rama `claude/project-thread-i1z9ir` (sobre `main` 1627463, con F3-offline 1 y 2 dentro) · spec de implementación (R25) del adaptador de Expansion del [plan de M1 v2](2026-10-26-m1-cine-v2.md) (§3 F3, decisiones #5 y #12-#15) · contrato: `product-spec.md` C1-C5 · base técnica: la implementación de S3 `e92fab7` (oráculo congelado `129c6d2`, gate offline en verde el 27-nov), que vive solo en el PC de Guillermo (rama local `claude/s3-impl24`) · v0.1.

**Por qué ahora.** F3-offline 1 y 2 dejaron el núcleo listo para hablar con un motor de actores (`DSBX_ActorEngine` y `DSBX_ActorOps`), pero el único motor disponible es el falso de las pruebas. Este brief escribe el motor real: un PBO aparte que se registra en el núcleo y traduce las órdenes de actor a Expansion AI. Lo que S3 ya reancló contra Expansion 1.9.84 (`DSBX_QA_Exp_Backend.c` de `e92fab7`) se reutiliza tal cual; lo que S3 todavía no ha medido en partida queda marcado `[verify partida]` y lo prueba el hilo de spikes.

**Proceso.** Enforce no compila en la nube. Lo que sí se prueba sin juego es la forma del adaptador: la comprobación estática nueva (§6, reglas E1-E9) con sus mutantes (§7), más el gate offline de M1 entero sin regresión. El comportamiento (que el actor llegue, que el gesto se observe) es de la partida. Por la regla del 26-nov no pasa por Sol: lo que se prueba, se prueba.

## 0. Qué es y qué no

Es:
- **dos cambios pequeños en el núcleo** (§2): `RequestGesture` recibe cuándo disparar el gesto (`g_at`, `g_t_ms`, que hoy `DSBX_ActorOps` recibe y no pasa) y el motor gana `Gestures(lid)`, para que la foto lleve los eventos de gesto (hoy `"gestures":[]` fijo);
- **el PBO del adaptador** `DayZSandbox_Expansion/` (§3-§5): `config.cpp`, el motor `DSBX_ExpansionEngine`, el observador de gestos y el registro en `MissionServer`;
- **la comprobación estática** `app/tests/test_exp_adapter_static.py` (§6) y sus mutantes (§7).

No es:
- la prueba en partida (hilo de spikes; §9 dice qué medir), el linter de Enforce (`dayz-script-validator`, DP-14, en el PC) ni el empaquetado del PBO;
- el muestreo a 10 Hz, la web de actores ni `m1_gate.py phase F3`;
- ningún cambio en el backend, el esquema, `qa/`, el contrato F2 v1.3.16 ni el formato de lectura de F3-offline-1 §2.

Trazabilidad (R20): §2 sale de C3 (gesto observado, plan #14) y de la nota `[verify S3]` de `DSBX_ActorOps.c:83`; §3 de #5; §4 de #11, #12 y #13; §5 de #14 y #15; §6 y §7 de R26. Lo que no trace a esto no entra.

## 1. Ficheros

**Se tocan solo**:
- `DayZSandbox/scripts/3_Game/DSBX_ActorEngine.c` y `DayZSandbox/scripts/3_Game/DSBX_ActorOps.c` (§2);
- nuevos: `DayZSandbox_Expansion/$PBOPREFIX$`, `DayZSandbox_Expansion/include.lst`, `DayZSandbox_Expansion/config.cpp`, `DayZSandbox_Expansion/scripts/4_World/DSBX_ExpEngine.c`, `DayZSandbox_Expansion/scripts/5_Mission/DSBX_ExpMission.c`, `DayZSandbox_dev/app/tests/test_exp_adapter_static.py`.

No se toca nada más: ni `test_mod_static.py` (M18 y M19 tienen que seguir en verde sin editarlas), ni el backend, ni `fake_*`, ni el resto del núcleo. El núcleo sigue sin ninguna referencia a Expansion (M18).

## 2. Núcleo [EXACT]

### 2.1 `DSBX_ActorEngine.c`

Solo dos cambios en la clase base; el registro no cambia:

```c
	string RequestGesture(string lid, int gi, string emote, int atMark, int tMs) { return "expansion_unavailable"; }
	// Eventos de gesto §2.2 de F3-offline-1 de ese actor, serializados y separados por comas ("" si no hay).
	string Gestures(string lid) { return ""; }
```

`atMark` es `g_at[gi]` (índice de marca desde 0, o `-1`) y `tMs` es `g_t_ms[gi]` (milisegundos desde la creación del actor, o `-1`). Exactamente uno de los dos es `-1` (lo garantiza `scene_plan`, F3-offline-2 §2.1).

### 2.2 `DSBX_ActorOps.c`

- En `Apply`, la llamada pasa a `engine.RequestGesture(args.a_lid, gi, args.g_emote[gi], args.g_at[gi], args.g_t_ms[gi])`, y se borra el comentario `// [verify S3] el momento del gesto ...` de encima.
- En `ReadJson`, junto a cada fila incluida, `string ev = engine.Gestures(lid);` y, si no es `""`, se añade a una cadena `events` con comas igual que `rows`. El retorno pasa a `"{\"actors\":[" + rows + "],\"gestures\":[" + events + "]}"`. Con `only`, solo los eventos de ese `lid` (son los de su fila, así que `valid_actor_read` sigue pasando: cada `lid` de `gestures` tiene fila).
- Se actualiza el comentario de `ReadJson` (ya no es «gestures vacío»). Nada más.

## 3. El PBO del adaptador [EXACT]

`DayZSandbox_Expansion/$PBOPREFIX$` = `DayZSandbox_Expansion`; `include.lst` = `*.c`; `config.cpp`:

```cpp
class CfgPatches
{
	class DayZSandbox_Expansion
	{
		units[] = {};
		weapons[] = {};
		requiredVersion = 0.1;
		requiredAddons[] = {"DZ_Data", "DZ_Characters", "DayZSandbox", "DayZExpansion_Core_Scripts", "DayZExpansion_AI_Scripts"};
	};
};

class CfgMods
{
	class DayZSandbox_Expansion
	{
		dir = "DayZSandbox_Expansion";
		name = "DayZSandbox_Expansion";
		type = "mod";
		dependencies[] = {"World", "Mission"};
		class defs
		{
			class worldScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_Expansion/scripts/4_World"};
			};
			class missionScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_Expansion/scripts/5_Mission"};
			};
		};
	};
};
```

Es el `config.cpp` de la sonda de S3 (`qa/probe/DayZSandbox_QA_Expansion/config.cpp` de `e92fab7`) con `DayZSandbox_QA` → `DayZSandbox`. `requiredAddons` de Expansion: `[verify partida]` (S3 los reancló de los PBO instalados).

**Los dos `.c` van enteros dentro de `#ifdef EXPANSIONMODAI` ... `#endif`** (el primer código de cada fichero tras los comentarios y la última línea): sin Expansion el PBO no aporta nada y el núcleo sigue con su motor base (C5, «el núcleo carga sin el adaptador»).

**Registro** (`scripts/5_Mission/DSBX_ExpMission.c`):

```c
#ifdef EXPANSIONMODAI
modded class MissionServer
{
	protected ref DSBX_ExpansionEngine m_DsbxExpEngine;

	override void OnMissionStart()
	{
		super.OnMissionStart();
		m_DsbxExpEngine = new DSBX_ExpansionEngine();
		DSBX_ActorEngineRegistry.Register(m_DsbxExpEngine);
	}

	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		if (m_DsbxExpEngine)
		{
			m_DsbxExpEngine.Tick(timeslice);
		}
	}
}
#endif
```

Orden de carga: el `requiredAddons` pone el núcleo antes, así que `super.OnMissionStart()` crea el peer del núcleo y el registro ocurre en la misma llamada; el primer `hello` se arma en `DSBX_Peer.StepHello` desde `Tick` (`DSBX_Peer.c:1518`), ya después, y sale con `actor_engine = "expansion"`. `[verify partida]`.

## 4. El motor `DSBX_ExpansionEngine` [EXACT salvo lo marcado]

Fichero `scripts/4_World/DSBX_ExpEngine.c`. `class DSBX_ExpansionEngine : DSBX_ActorEngine` con `override` de `Name` (`return "expansion";`), `IsAvailable` (`return true;`), `Spawn`, `SetMarks`, `RequestGesture`, `State`, `Stop`, `Despawn` y `Gestures`, más `void Tick(float timeslice)`. Convención del núcleo: `""` es éxito; otra cadena es el código (`[a-z_]{1,24}`).

Guarda los actores en un `ref map<string, ref DSBX_ExpActor>` por `lid`. `DSBX_ExpActor : Managed` lleva: la entidad (`eAIBase`), la clase del documento (`cls`, el nombre vanilla), la posición de creación `p0`, el instante de creación, las marcas, el comportamiento, el radio, el índice de marca, `mark_st`, el estado de ROAM, los gestos y sus eventos. Los tiempos van en `tick_ms` = `g_Game.GetTickTime() * 1000.0` (como S3), y en la fila como entero.

Las constantes van en una `class DSBX_ExpConst` en el mismo fichero: `REACH_M = 1.5`, `STUCK_M = 0.25`, `STUCK_MS = 5000`, `ROAM_PAUSE_MS = 1500`, `ROAM_GIVEUP_MS = 60000`, `START_TIMEOUT_MS = 5000`, `PLAY_TIMEOUT_MS = 30000`. Todas `[verify partida]`.

### 4.1 `Spawn(lid, cls, pos, yaw, items)` (#11, #12, C1)

1. Si `lid` ya está en el mapa, `Despawn(lid)` primero (una reentrega no deja dos actores; F3-offline-2 §2.1).
2. `string engineCls = "eAI_" + cls;` y, si `!g_Game.ConfigIsExisting("CfgVehicles " + engineCls)`, devuelve `"unknown_class"`. Clase fija desde el nombre vanilla: nunca `GetQuasiRandom()` (#12).
3. Posición en el suelo: `p[1] = g_Game.SurfaceY(pos[0], pos[2])`. Creación con `g_Game.CreateObjectEx(engineCls, p, ECE_PLACE_ON_SURFACE | ECE_INITAI | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD)`, nunca `ECE_DYNAMIC_PERSISTENCY` (#11). `eAIBase.Cast` nulo → `"spawn_failed"`.
4. `ai.SetOrientation(Vector(yaw, 0, 0))`.
5. Un grupo por actor y facción pasiva, como S3: `eAIFaction passive = new eAIFactionPassive(); eAIGroup group = eAIGroup.CreateGroup(passive); ai.SetGroup(group);`.
6. Barrido del equipo con que nazca, como `SweepAttachments` de S3 (`DSBX_QA_X_Actor.c:1157-1185` de `e92fab7`): primero recoge en una lista todos los `GetAttachmentFromIndex(i)` de `AttachmentCount()`, después borra cada uno con `LocalDestroyEntity` o, si falla, `g_Game.ObjectDelete`.
7. Viste cada clase de `items` con `ai.GetInventory().CreateAttachment(itemClass)` (vanilla elige la ranura, `inventory.c:209` de la build 1.30.164289). Si alguna devuelve nulo: retira el actor (`Despawn`) y devuelve `"wardrobe_failed"`.
8. Lo guarda con `mark_i = -1`, `mark_st = "idle"` y sin marcas: el actor se queda donde está hasta `SetMarks`.

### 4.2 `SetMarks(lid, marks, behaviour, roam)` (#13, C2, C4)

`lid` desconocido → `"unknown_actor"`. Las marcas llegan con `y = 0`; cada una se pone en el suelo con `SurfaceY` antes de mandarla. Siempre empieza por `group.ClearWaypoints()`.

| `behaviour` | Qué manda | `mark_i` / `mark_st` |
|---|---|---|
| `HOLD` | nada más que `SetWaypointBehaviour(eAIWaypointBehavior.HALT)` | `-1` / `idle` |
| `ONCE` | `AddWaypoint` de cada marca en orden y `SetWaypointBehaviour(eAIWaypointBehavior.ONCE)` | `0` / `moving` |
| `LOOP` | igual con `eAIWaypointBehavior.LOOP` | `0` / `moving` |
| `ROAM` | deambular propio (§4.3); nunca `ROAMING` ni `ROAMING_LOCAL` (CX-02) | `-1` / `moving` |
| otro | — | devuelve `"bad_behaviour"` |

`ONCE` o `LOOP` sin marcas → `"bad_marks"` (`scene_plan` ya lo rechaza; esto solo protege el motor).

### 4.3 `Tick(timeslice)`: marcas, ROAM y gestos

Para cada actor vivo, con `pos = ai.GetPosition()` y distancias en xz:

- **ONCE y LOOP** (índice propio de Sandbox, #12: «en marca» lo decide Sandbox midiendo; el juez nunca se fía de `mark_st` para un PASA):
  - si `dist(pos, marks[mark_i]) < REACH_M`: la marca cuenta como alcanzada (para los gestos por marca, §5); en `ONCE`, si no es la última, `mark_i + 1` y `moving`; si es la última, `arrived`; en `LOOP`, `mark_i = (mark_i + 1) % n` y `moving`;
  - si no, **atasco**: si en los últimos `STUCK_MS` el actor no se ha movido `STUCK_M`, `mark_st = "unreachable"`; en cuanto vuelve a moverse, `moving`. `[verify partida]`: que la ruta imposible de S3 dé `unreachable` y que un ONCE normal nunca lo dé.
- **ROAM** (#13, CX-02, como `SendRoamDest` de S3): destinos deterministas en el anillo `[0.35, 0.75] × roam` alrededor de `p0`, con un generador congruencial sembrado con la suma de los caracteres de `lid`; cada destino se manda solo, como `ONCE` (`ClearWaypoints`, `AddWaypoint`, `SetWaypointBehaviour(eAIWaypointBehavior.ONCE)`). Al quedar a `< REACH_M`, `mark_st = "idle"` durante `ROAM_PAUSE_MS` y después el siguiente destino (`moving`). Si no llega en `ROAM_GIVEUP_MS`, el siguiente. `mark_i` siempre `-1`.
- **Gestos**: §5.

### 4.4 `State(lid)` (formato de F3-offline-1 §2.1)

`lid` desconocido → `"unknown_actor"`. Actor muerto o borrado (`!ai || !ai.IsAlive()`) → `[lid,null,null,null,null,null,[],-1,"idle",t_ms]`. Vivo: `[lid, cls, x_mm, y_mm, z_mm, yaw_mdeg, items, mark_i, mark_st, t_ms]` con:
- `cls` el nombre del documento (sin `eAI_`, #12), con `DSBX_Wire.WireText`;
- `x_mm`, `z_mm` con `DSBX_SceneWire.MetersToMmChecked(v, 0, DSBX_SceneConst.MAX_XZ_MM, out)`, `y_mm` con límites `±DSBX_SceneConst.MAX_Y_MM`, `yaw_mdeg` con `DSBX_SceneWire.YawDegToMdegChecked(ai.GetOrientation()[0], out)`; si alguna falla, devuelve `"bad_position"` (el núcleo salta la fila);
- `items` = el `GetType()` de cada `GetAttachmentFromIndex(i)`, cada uno con `WireText`.

### 4.5 `Stop(lid)` y `Despawn(lid)`

- `Stop`: `ClearWaypoints()` + `HALT`, `mark_i = -1`, `idle`; el gesto en curso o pedido termina en `canceled` con `cause = "stop"` y se retira la petición de Expansion (§5); los gestos aún sin disparar se descartan sin eventos.
- `Despawn`: como `Stop`; después `group.ClearWaypoints()`, `group.Delete()` (como `ReleaseActor` de S3), `g_Game.ObjectDelete(ai)` y lo quita del mapa. `lid` desconocido → `""` (idempotente: `actor.reset` repite).

## 5. Gestos y su observador (#14, #15, C3) [EXACT salvo lo marcado]

### 5.1 Biblioteca

Solo los ocho de `fixtures/catalog-m1.json` `emotes`, con su constante vanilla (`scripts/3_game/constants.c:366-407` de la build 1.30.164289), en un método con esta forma exacta (E7 la lee):

```c
	int EmoteId(string emote)
	{
		if (emote == "EmoteGreeting") return EmoteConstants.ID_EMOTE_GREETING;
		if (emote == "EmotePoint") return EmoteConstants.ID_EMOTE_POINT;
		if (emote == "EmoteThumb") return EmoteConstants.ID_EMOTE_THUMB;
		if (emote == "EmoteSurrender") return EmoteConstants.ID_EMOTE_SURRENDER;
		if (emote == "EmoteSalute") return EmoteConstants.ID_EMOTE_SALUTE;
		if (emote == "EmoteFacepalm") return EmoteConstants.ID_EMOTE_FACEPALM;
		if (emote == "EmoteTaunt") return EmoteConstants.ID_EMOTE_TAUNT;
		if (emote == "EmoteHeart") return EmoteConstants.ID_EMOTE_HEART;
		return -1;
	}
```

`RequestGesture` con un nombre que da `-1` → `"unknown_emote"`; `lid` desconocido → `"unknown_actor"`. **Desviación que se le enseña a Guillermo**: S3 certifica otros ocho (`nod`, `shake`, `shrug`, ... en `qa/fixtures/s3_emotes.json`), y #15 dice «solo los certificados en S3». El catálogo de M1 ya fijó estos ocho y el adaptador no lo cambia (R20); que en partida se observen los ocho del catálogo es `[verify partida]`, y si alguno no, sale del catálogo.

### 5.2 Disparo

`RequestGesture` solo **encola** `(gi, emoteId, atMark, tMs)`; no emite nada. En `Tick`, un gesto encolado se dispara cuando: con `atMark >= 0`, esa marca ya contó como alcanzada (§4.3); con `tMs >= 0`, han pasado `tMs` desde la creación del actor. Además, solo si ningún otro gesto de ese actor está `requested` o `playing` (uno a la vez, en orden de `gi`).

Disparar: `ai.Expansion_SetEmote(emoteId, false, 0)` (sin `autoCancel`, como S3), evento `requested` y se anota el contador de callbacks en ese instante.

### 5.3 Observador

En el mismo fichero, como el de S3 (`DSBX_QA_W_Actor.c` de `e92fab7`): `modded class EmoteManager` que sobrescribe `CreateEmoteCallback` y, tras `super`, avisa con `m_Callback.DsbxOnBound(m_Player, this, m_CurrentGestureID, id)`; `modded class EmoteCB` que numera la instancia en `DsbxOnBound`, llama a `EnableStateChangeCallback()` y reenvía `OnStateChange` y `OnFinish(bool pCanceled)` (siempre tras `super`) a un receptor estático `DSBX_ExpEmoteHub`, cuyo receptor es el motor. Símbolos vanilla comprobados en la build 1.30.164289: `emotemanager.c:1-5` (`m_player`), `:691` (`CreateEmoteCallback`), `:118`, `:120` y `:144` (`m_Player`, `m_Callback`, `m_CurrentGestureID`); `human.c:362`, `:369`, `:426`, `:429`.

Transiciones (cada una emite su evento §2.2 de F3-offline-1 con `t_ms` del momento):

| Desde | Qué pasa | Evento |
|---|---|---|
| `requested` | `OnBound` del mismo actor, con `gestureId == emoteId` y una instancia nueva (posterior a la petición) | ninguno; el callback queda vinculado |
| `requested` (vinculado) | `OnStateChange` de `STATE_NONE` a otro estado | `playing` |
| `requested` o `playing` (vinculado) | `OnFinish(false)` | `finished` (si no hubo `playing`, el juez da `fin_sin_empezar`) |
| `requested` o `playing` (vinculado) | `OnFinish(true)` | `canceled`, `cause = "interrupted"` |
| `requested` | `START_TIMEOUT_MS` sin `playing` | `expired`, `cause = "timeout"` |
| `playing` | `PLAY_TIMEOUT_MS` sin fin | `expired`, `cause = "timeout"` |
| `requested` o `playing` | `Stop` o `Despawn` | `canceled`, `cause = "stop"` |

Tras cualquier terminal: `ai.Expansion_SetEmote(0, false, 0)` (CX-nv3: Expansion no limpia sola la petición sin `autoCancel`) y el callback se desvincula; un `OnStateChange` u `OnFinish` posterior de ese callback no emite nada. El combate no tiene regla propia: un gesto que el FSM no arranca acaba en `expired` (`agotado` para el juez), que es lo que pide C3. `[verify partida]`: que `playing` y `finished` salgan para los ocho; el caso combate de S3.

`Gestures(lid)` devuelve los eventos de ese actor desde su creación, en orden, serializados como `["act-01",0,"requested",12345,null]` (`cause` con `WireText` o `null`).

## 6. Comprobación estática `test_exp_adapter_static.py` (R26) [EXACT]

Fichero nuevo, `unittest`, solo stdlib. Reutiliza `_strip_comments`, `_find_class_body` y `_find_method_body` importándolos de `app.tests.test_mod_static` (no los copia). Cada regla es una función `check_eN(adapter_dir, core_dir) -> list[str]` (lista de violaciones) y hay una prueba por regla sobre el árbol real que exige `[]`. `adapter_dir` = `<repo>/DayZSandbox_Expansion`, `core_dir` = `<repo>/DayZSandbox`.

| Regla | Positivo (el árbol real pasa) | Qué la rompe |
|---|---|---|
| E1 forma | ficheros exactamente los de §1 bajo `DayZSandbox_Expansion/`; `$PBOPREFIX$` y `include.lst` de §3; en `config.cpp`, `requiredAddons` exactamente la lista de §3 en ese orden, `dependencies` = `{"World", "Mission"}` y `defs` con solo `worldScriptModule` y `missionScriptModule` y sus dos rutas | un fichero de más o de menos; quitar `"DayZSandbox"` o `"DayZExpansion_AI_Scripts"` de `requiredAddons` |
| E2 guarda | en cada `.c`, sin comentarios, la primera línea no vacía es `#ifdef EXPANSIONMODAI` y la última `#endif` | cualquier código fuera de la guarda |
| E3 motor | `class DSBX_ExpansionEngine : DSBX_ActorEngine`; `Name` devuelve `"expansion"` e `IsAvailable` `true`; los siete métodos de §4 con `override` | falta un `override`; `Name` devuelve otra cosa |
| E4 registro | en `modded class MissionServer`, `OnMissionStart` llama a `super.OnMissionStart();` antes de `DSBX_ActorEngineRegistry.Register(`; `OnUpdate` llama a `super.OnUpdate(timeslice);` y a `.Tick(timeslice)` | `Register` antes de `super`; sin `Tick` |
| E5 alta | en `Spawn`: `"eAI_" +`, `ConfigIsExisting`, `CreateObjectEx` con `ECE_INITAI`, `ECE_NOLIFETIME` y `ECE_NOPERSISTENCY_WORLD`, `eAIFactionPassive`, `eAIGroup.CreateGroup(` y `SetGroup(`, `CreateAttachment(` | quitar `ECE_NOLIFETIME`; no crear grupo |
| E6 prohibido | en todo el adaptador, sin comentarios: ni `GetQuasiRandom`, ni `ROAMING` (cubre `ROAMING_LOCAL`), ni `ECE_DYNAMIC_PERSISTENCY`, ni `ExpansionHumanLoadout`; y toda llamada `Expansion_SetEmote(` lleva `false` como segundo argumento | cualquiera de esos tokens; un `Expansion_SetEmote(id, true, 0)` |
| E7 gestos | los pares `(nombre, constante)` de `EmoteId` son exactamente los ocho de §5.1, los nombres son exactamente `emotes` de `fixtures/catalog-m1.json` y el método acaba en `return -1;`; `RequestGesture` contiene `"unknown_emote"` | un gesto de menos o de más, o con otra constante; un nombre que no está en el catálogo |
| E8 núcleo | en `DSBX_ActorEngine` (core), la firma `RequestGesture(string lid, int gi, string emote, int atMark, int tMs)` y `Gestures(string lid)` con cuerpo `return "";`; en `DSBX_ActorOps.Apply`, `args.g_at[gi]` y `args.g_t_ms[gi]` en la llamada a `RequestGesture`; en `ReadJson`, `engine.Gestures(` | la firma vieja; `ReadJson` con `"gestures\":[]"` fijo |
| E9 eventos | las causas que emite el adaptador son literales de `{"timeout", "interrupted", "stop"}`, y los estados de evento que aparecen como literal son un subconjunto de los seis de F3-offline-1 §2.2 | un literal `"cancelled"` o una causa con mayúsculas |

Las reglas E1-E9 se implementan buscando texto sobre el código sin comentarios, como M1-M19. Lo que necesiten de forma exacta (los cuerpos de §3, §5.1 y §2.1) ya está fijado arriba; lo demás, el implementador lo escribe como quiera mientras pase la regla.

## 7. Mutantes (antitautología, R26)

Script `mutants.py` en la carpeta del proyecto (`dayz-sandbox/f3adapt/`), no en el repo, como en F3-offline. Cada mutante copia el árbol a un temporal, aplica un cambio de texto y comprueba que **su** regla devuelve al menos una violación y que las demás siguen en `[]`:

| # | Mutación | Regla |
|---|---|---|
| X1 | `requiredAddons` sin `"DayZExpansion_AI_Scripts"` | E1 |
| X2 | un fichero `.c` de más en `scripts/4_World/` (fuera de la guarda) | E1 (y E2) |
| X3 | una función fuera del `#ifdef` al final de `DSBX_ExpMission.c` | E2 |
| X4 | `Name` devuelve `"none"` | E3 |
| X5 | `Register` antes de `super.OnMissionStart()` | E4 |
| X6 | sin `ECE_NOLIFETIME` | E5 |
| X7 | `eAIWaypointBehavior.ROAMING_LOCAL` en ROAM | E6 |
| X8 | `Expansion_SetEmote(emoteId, true, 0)` | E6 |
| X9 | `EmoteHeart` borrado de `EmoteId` | E7 |
| X10 | `EmotePoint` con `ID_EMOTE_THUMB` | E7 |
| X11 | `RequestGesture` del núcleo con la firma de tres argumentos | E8 |
| X12 | `ReadJson` con `gestures` vacío fijo | E8 |
| X13 | causa `"Timeout"` | E9 |

X2 rompe dos reglas a la vez; para ese mutante basta que falle E1.

## 8. Aceptación

- `python3 -m unittest discover -s app/tests -t app` en verde (las de hoy + E1-E9), con M18 y M19 sin editar.
- `npm run build`, `e2e_web.py` y `e2e_studio.py` en verde (no tocan nada de esto, pero son el gate).
- Los 13 mutantes de §7 mueren con su regla.
- `git diff --stat` solo toca los ficheros de §1 (más este brief).

## 9. Lo que mide la partida (para el hilo de spikes)

Antes de lanzar: el linter de Enforce (DP-14) sobre los dos PBO, con Expansion 1.9.84 cargado. Después, con la escena básica de cine (`escena-basica-cine.json`), el núcleo y este adaptador:
- el `hello` del servidor sale con `actor_engine = "expansion"` (orden de carga, §3);
- C1: las dos filas del `actor.apply` pasan `judge_identity` (sin equipo extra de Expansion tras el barrido);
- C2: ONCE llega y se queda; la marca imposible de S3 da `unreachable`, nunca un PASA; un ONCE normal nunca da `unreachable`;
- C3: los ocho gestos del catálogo, uno a uno, dan `requested`, `playing`, `finished`; un `actor.reset` en mitad de uno da `canceled/stop` y el gesto no arranca más tarde;
- C4: HOLD quieto 10 s; ROAM 10 min dentro del radio;
- C5: sin el PBO del adaptador, el `hello` sale con `"none"` y la escena con actores se rechaza con `expansion_unavailable`.

## 10. Riesgos y `[verify]`

- Las constantes de §4 y el atasco como señal de `unreachable` (§4.3) son de mesa: la partida los ajusta.
- `CreateAttachment` elige la ranura sola; si un preset pide dos prendas para la misma ranura, falla con `wardrobe_failed` (los cuatro presets de §4 de F3-offline-1 tienen una por ranura).
- El tamaño de la foto con muchos eventos de gesto frente a `WIRE_CAP` no se mide aquí: 16 actores con varios gestos cada uno podrían no caber en `actor.observe`. Va al bug-ledger si la partida lo enseña.
- Los ocho gestos del catálogo no son los ocho que certifica S3 (§5.1).

## 11. Reparto

- **Lane A, Grok** (`grok-4.6`): §2, §3, §4 y §5 (el núcleo y el PBO del adaptador). Lee la sonda de S3 como referencia.
- **Lane B, Gemini Argon**: §6 (`test_exp_adapter_static.py`) y el `mutants.py` de §7, sin ver el código de la lane A (escribe las reglas contra el brief; otra familia que el implementador, regla E9 de la otra cuenta).
- Fallback: el orquestador (Claude) escribe lo que una lane no entregue. Gate y mutantes, el orquestador en la nube.

## 12. Cambios

| Versión | Cambio |
|---|---|
| v0.1 | Borrador del 27-nov, desde S3 `e92fab7`. |
| v0.1a | Implementado el 27-nov: lane A (§2-§5) Grok `grok-4.6`, 3 min 49 s, 0,66 USD, 5 dudas en `plans/f3adapt-laneA-dudas.md`, ninguna cambia el brief; lane B (§6, §7) Gemini `gemini-4-argon-high`, 7 min 47 s, a ciegas del código de A. Las dos entregas entraron sin tocar (4bd771f). El orquestador corrigió dos cosas: E9 de la lane B marcaba como causas el literal `"null"` de `causeJson` y el estado interno `"done"` del gesto (ni uno ni otro sale en un evento), así que el regex de asignación ignora las variables `*Json` y `"done"` entra en la lista blanca; y la prueba `test_t_m18_nucleo` de `test_mod_static.py`, que muta la firma vieja de `RequestGesture`, pasa a la firma de §2.1 (§1 decía «sin editar»: la firma nueva la obliga; es la única línea cambiada). **Medido en la nube:** E1-E9 y M1-M19 en verde; los 13 mutantes de §7 mueren con su regla (`python3 plans/f3adapt-mutants.py`). |
