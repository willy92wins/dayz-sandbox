# Spike S3, parte sin juego: API de Expansion AI en la versión fijada

2026-10-24 · DayZ-Expansion-Scripts, rama `release`, commit `0d26645` ("Updated to version 1.9.80", 2026-10-17) · clon parcial de `DayZExpansion/AI` y lectura de `0_DayZExpansion_AI_Preload`

Lectura de su código para usarlo como adaptador desde fuera (llamar a su API pública con el mod cargado). Nada de este código se copia ni se deriva: la licencia CC BY-NC-ND lo prohíbe. Las rutas son relativas a `DayZExpansion/AI/Scripts/` salvo que se diga otra cosa. Falta la parte en partida (abajo).

## Lo que confirma el código

| Pieza | Dónde | Qué dice |
|---|---|---|
| Grupos | `4_World/DayZExpansion_AI/Classes/eAIGroup.c:123,138` | `static eAIGroup CreateGroup(eAIFaction faction = null)` y sobrecarga con `Class` |
| Marcas | `eAIGroup.c:213,222,241,251` | `AddWaypoint(vector)`, `GetWaypoints()`, `ClearWaypoints()` (pone el índice a 0), `SetWaypointBehaviour(eAIWaypointBehavior)` |
| Facción y formación | `eAIGroup.c:633,661,933` | `SetFaction(eAIFaction)`, `SetFaction(Class)`, `SetFormation(eAIFormation)` |
| Comportamientos | `3_Game/DayZExpansion_AI/Enums/AIenums.c:1-13` | `HALT, LOOP, ALTERNATE, ONCE, HALT_OR_LOOP, HALT_OR_ALTERNATE, LOOP_OR_ALTERNATE, ROAMING, ROAMING_LOCAL, MIXED` (MIXED es un TODO) |
| Fin de recorrido | `4_World/.../FSM/states/eaistate_traversingwaypoints.c:148,175-200` | `HALT`, un solo punto o **ruta inalcanzable** dan `isFinal`; fuera de `LOOP`/`ALTERNATE`, el índice se queda en el último punto (ONCE acaba en la última marca) |
| Sin marcas | `eaistate_traversingwaypoints.c:260` | sin waypoints y sin `ROAMING`, el estado falla: el actor se queda donde está |
| Amenaza | `eaistate_traversingwaypoints.c:269` | con amenaza ≥ 0,4 deja de recorrer marcas |
| Alta de un NPC | `5_Mission/DayZExpansion_AI/eaicommandmanager.c:376-390` | `g_Game.CreateObject(eAISurvivor.GetQuasiRandom(), pos)` y después `ExpansionHumanLoadout.Apply(ai, loadout, true)`; el grupo se asigna con `ai.SetGroup(group)` (`:348-351`) |
| Alta en patrullas | `4_World/.../Classes/Patrols/eAIDynamicPatrol.c:371-373,649` | `CreateObjectEx(unit, pos, ECE_CREATEPHYSICS \| ECE_KEEPHEIGHT \| ECE_NOSURFACEALIGN)`; el grupo espera en `HALT` hasta que han aparecido todos |
| Personajes | `4_World/.../Entities/AI/eAISurvivor.c:1-60,79+` | 31 clases fijas `eAI_SurvivorM_<Nombre>` (20) y `eAI_SurvivorF_<Nombre>` (11), con los mismos nombres que los supervivientes vanilla; `GetQuasiRandom()` elige uno al azar |
| Asignar grupo | `4_World/.../Entities/AI/eAIBase.c:3926` | `override void SetGroup(eAIGroup group, bool autoDeleteFormerGroupIfEmpty = true, int groupMemberIndex = -1)` |
| Gestos | `eAIBase.c:10859-10876` | `Expansion_SetEmote(int emoteID, bool autoCancel = false, int autoCancelDelay = 0)` solo guarda la petición; la nota dice que el gesto no empieza al instante sino cuando la FSM pasa a PlayEmote. `Expansion_PlayEmote()` llama a `m_EmoteManager.PlayEmote` si `!IsEmotePlaying() && CanPlayEmote(id)` |
| Facción pasiva | `3_Game/.../Factions/eAIFactionPassive.c:1-12`, `eAIFaction.c:7,116` | `eAIFactionPassive : eAIFactionCivilian` con `m_IsPassive = true`; amistosa con `DayZCreatureAI` (infectados y animales). `eAIFactionCivilian` es amistosa con todas las facciones |
| Define para cargarlo opcional | `0_DayZExpansion_AI_Preload/Common/DayZExpansion_AI_Defines.c:3-6` | `#define EXPANSIONMODAI` solo si no es `DAYZ_1_29` |
| Guardia de 1.29 | `3_Game/.../DayZGame.c:92-93`, `eaicommandmanager.c:378-381` | en 1.29 avisa "DayZ 1.29 is not compatible with the 1.30 AI animgraph" y `SpawnAIEx` devuelve null |
| Dependencias | `Scripts/config.cpp:8-12` | `requiredAddons`: `DZ_Characters`, `DayZExpansion_Core_Scripts` (Expansion Core, que a su vez pide CF) |

## Consecuencias para el adaptador de M1

1. **Personaje fijo, no aleatorio.** Su alta normal elige cara y cuerpo al azar, así que tres tomas darían tres actores distintos. El adaptador crea la clase pedida (`eAI_SurvivorM_Mirek`) con `CreateObject` y no llama a `SpawnAIEx`. El documento guarda el personaje con el nombre vanilla (`SurvivorM_Mirek`), que vale igual para la IA propia de M2 (C4).
2. **Vestuario con código propio.** El inventario se pone con la API vanilla y no con `ExpansionHumanLoadout`, para que el mismo preset sirva sin Expansion (C1, C4).
3. **Vocabulario propio → Expansion** (a confirmar en partida): HOLD → sin marcas; ONCE → marcas + `ONCE`; LOOP → `LOOP`; ROAM → `ROAMING_LOCAL`, porque `ROAMING` usa las localizaciones de todo el mapa.
4. **"Llegó" lo decide Sandbox, no Expansion.** Una ruta inalcanzable también acaba en `isFinal`, así que el estado "en marca" sale de medir la distancia a la marca (C2), con tiempo límite.
5. **Gesto pedido no es gesto hecho.** El estado sale de observar `IsEmotePlaying()` pasar a verdadero y luego a falso; si no empieza antes del tiempo límite, queda agotado (C3).
6. **Carga opcional.** El código del adaptador va dentro de `#ifdef EXPANSIONMODAI`; sin Expansion compila igual e informa `expansion_unavailable` (C5). Falta comprobar el orden de carga: el preload de Expansion tiene que compilarse antes que los módulos de Sandbox.
7. **Facción pasiva para el reparto**, para que los actores no se pongan a pelear con infectados ni animales durante la toma; las amenazas de jugadores siguen pudiendo cortar el recorrido (`:269`).

## Falta, en partida (necesita tu visto bueno para arrancar DayZ)

- Positivas: un actor `eAI_SurvivorM_Mirek` en facción pasiva con 5 prendas leídas iguales al preset; ONCE a una marca a 20 m: llega a < 1,5 m y se mueve < 0,5 m en 10 s; un gesto se observa empezar y terminar.
- Negativas: marca inalcanzable → nunca "en marca"; gesto con un infectado atacando → rechazado o agotado; servidor sin Expansion → `expansion_unavailable` antes de crear nada.
- El mapeo HOLD/ONCE/LOOP/ROAM del punto 3 y el orden de carga del punto 6.
