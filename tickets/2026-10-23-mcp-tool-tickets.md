# Fichas de tools nuevas para dayz-mcp (DayZ Sandbox, 2026-10-23)

## 1. `camera_path_play`

**Tool nueva camera_path_play: recorrer un camino de cámara con claves (posición, orientación, FOV) en el cliente**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
camera_set solo coloca una cámara fija (orient, lookat, matrix o free) y espera por tiempo de pared, sin IsInterpolationComplete (descripción de camera_set en server.py). Un plano de cine necesita movimiento: travelling, paneo, grúa u órbita. Encadenar camera_set no da movimiento continuo, porque cada orden pasa por el long-poll y llega en un tick distinto.

Propuesta
- Firma: camera_path_play(mode, keys=None, easing='smooth', path_id='', timeout_s). mode = play, state o stop, como los modos de anim_timeline.
- keys: 2 o más claves {t en s (estrictamente creciente desde 0), cam_pos, cam_orientation [yaw, pitch, roll] en grados o look_at, fov en radianes (opcional)}.
- El cliente evalúa el camino cada frame sobre la cámara scripted de camera_set, no sobre la FreeDebugCamera de diag, que congela la simulación.
- Peer: cliente. Requiere lease. state devuelve playing, finished o aborted y t_s; la pose se lee con camera_get.
- Movimiento: interpolación por frame (Catmull-Rom en posición) o Camera.InterpolateTo encadenado entre claves; lo decide el probe.

Evidencia
- API de cámara de BI: InterpolateTo(Camera, tiempo, tipo 0/1/2 con aceleración), IsInterpolationComplete, EnableSmooth y StopInterpolation (camera.c:16-55); SetFOV en radianes (camera.c:64-67). Fuente: BohemiaInteractive/DayZ-Script-Diff.
- Caminos con claves, FOV y suavizado son el estándar de cine en DayZ: la cámara de COT (waypoints con FOV, easing y Catmull-Rom; research, anexo C) y PCT; Simple Cinematics no tiene caminos (anexo B).
- Necesidad P0 de cine en el research: cámara con caminos, focal/DOF y presets (anexo B; consolidado §3).

Criterios de aceptación (R26)
- POS: 3 claves en línea recta, 6 s, easing='linear': camera_get a t=1,5 s y t=4,5 s da posiciones a menos de 0,5 m de las esperadas.
- POS: state pasa a finished entre 6,0 y 6,3 s después de play y la pose final coincide con la última clave (< 0,05 m y < 0,5°).
- POS: capture_screenshot con frames >= 10 durante el movimiento no avisa de render_frozen_signal.
- NEG: Menos de 2 claves o t no creciente: bad_args antes de mover la cámara.
- NEG: play con otro camino en marcha: path_busy y el camino en curso sigue.
- NEG: stop a mitad: la cámara se queda en la pose de ese momento, state=aborted, y restore_gameplay devuelve el control.

Dependencias y riesgos
- Probe previo: InterpolateTo encadenado frente a evaluación por frame; medir saltos entre claves.
- Usa el mismo SuppressGameplay que camera_set (HUD oculto, controles desactivados) y se sale con restore_gameplay.
- Las claves podrán llevar enfoque cuando exista (ficha 'Ampliar camera_set: enfoque').

Prioridad: P0 del MVP de cine/machinima (movimientos de cámara).

## 2. `actor_emote`

**Tool nueva actor_emote: lanzar un emote en un jugador o NPC de Expansion y observar si empieza y termina**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Los actores necesitan gestos en cada toma (saludar, sentarse, rendirse...). No hay tool de emotes. En Expansion, pedir un emote no lo inicia al momento: espera a la FSM, así que 'pedido' no es 'hecho'.

Propuesta
- Firma: actor_emote(object_id, emote, timeout_s). emote de un catálogo cerrado con nombre.
- Jugador: EmoteManager.PlayEmote; NPC de Expansion: Expansion_SetEmote. El peer (servidor o cliente dueño) se decide con un probe previo.
- Requiere lease.
- Devuelve el estado observado: requested, started, finished, rejected o timed_out.

Evidencia
- Lane Codex: EmoteManager.PlayEmote comprueba condiciones y sincroniza servidor/cliente (emotemanager.c:507-542, 629-676); Expansion_SetEmote espera a la FSM (eAIBase.c:10125-10140).
- Lane Claude: estado de FSM eaistate_playemote y EmoteConstants en eAIBase (anexo C).
- Un solo mod de animaciones a la vez: el catálogo es vanilla (anexo C T1).

Criterios de aceptación (R26)
- POS: Emote de saludo en un jugador quieto: started en < 2 s y finished antes del timeout.
- POS: El mismo emote en un NPC de Expansion en reposo: started y finished.
- NEG: emote fuera del catálogo: bad_args con la lista permitida.
- NEG: NPC en combate o jugador en vehículo: rejected o timed_out, nunca finished.

Dependencias y riesgos
- Probe previo: confirmar desde qué peer arranca un emote en un jugador sin input del cliente.
- Ficha relacionada en Sandbox: catálogo de gestos certificados por versión.
- Con la IA propia, el NPC usará la misma vía que el jugador (EmoteManager), no la de Expansion.

Prioridad: P0 del MVP de cine/machinima (interpretación de los actores).

## 3. `loadout_apply`

**Tool nueva loadout_apply: aplicar un loadout completo (ropa, accesorios, carga, manos) a un jugador o NPC**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Equipar un actor exige hoy muchas llamadas a inventory_give e inventory_attach y no hay forma de quitar lo que lleva puesto (ficha aa01). En cine es el vestuario: cada actor tiene que salir igual en todas las tomas.

Propuesta
- Firma: loadout_apply(object_id, loadout, clear_first=False, timeout_s). loadout es JSON con slots de ropa, attachments, cargo y manos; valorar aceptar el formato de loadout de Expansion para compartir presets entre jugadores y NPC.
- Peer: servidor. Requiere lease.
- Devuelve resultado por item (ok o error) y el inventario leído después; estado global ok o partial.

Evidencia
- Lane Codex: las primitivas existen (inventory_give distingue manos/inventario, inventory_attach attachments/cargo) pero falta componerlas en un preset con errores parciales explícitos.
- Estándar en otros editores: slots con equipo en Eden, copiar/pegar equipo en ZEN (anexo A §2A.11).
- Necesidad de cine en el research: recuperar vestuario y posiciones entre tomas (consolidado §3).

Criterios de aceptación (R26)
- POS: Preset de 8 items en un jugador vacío: el inventario leído contiene exactamente esos 8.
- POS: clear_first=True sobre un jugador equipado: solo quedan los items del preset.
- NEG: Un item de clase desconocida entre 8: 7 aplicados, 1 error con la clase; estado partial, no ok.
- NEG: Dos items para el mismo slot: el segundo devuelve slot_occupied; nada se pierde en silencio.

Dependencias y riesgos
- clear_first depende de poder quitar ropa puesta (ficha aa01).
- Con NPC de Expansion, comprobar que el loadout no lo pisa su propia lógica de spawn.

Prioridad: P0 del MVP de cine/machinima (vestuario).

## 4. `loadout_get`

**Tool nueva loadout_get (lectura): leer el equipo completo de un jugador o NPC como preset reutilizable**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Para guardar el estado vivo como escena (la función 'Export Mission' de ZEN) y para la continuidad de vestuario entre tomas y sesiones hay que poder leer el equipo de un actor en el mismo formato que acepta loadout_apply.

Propuesta
- Firma: loadout_get(object_id). Devuelve el JSON de loadout que acepta loadout_apply.
- Peer: servidor. Solo lectura, sin lease.

Evidencia
- Capturar el estado vivo como escena es diferencial (solo ZEN lo tiene) (anexo A §2B.2).
- Necesidad de cine en el research: recuperar vestuario entre tomas (consolidado §3).

Criterios de aceptación (R26)
- POS: Ida y vuelta: loadout_get de A y loadout_apply en B dan el mismo multiconjunto de clases.
- NEG: object_id desconocido: not_found.
- NEG: Objeto que no es jugador ni NPC: bad_target, sin lectura parcial.

Dependencias y riesgos
- Depende del formato de loadout_apply.

Prioridad: P0 del MVP de cine/machinima (continuidad de vestuario).

## 5. `scene_entities`

**Tool nueva scene_entities y parámetro scene_id en los verbos de spawn: registro de propiedad por escena**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Los object_id son de sesión y no sobreviven al reinicio (descripción de object_delete en server.py). Para aplicar y resetear escenas hay que saber qué entidades pertenecen a cada una sin tocar las demás. Las dos lanes del research lo marcan como riesgo crítico.

Propuesta
- Parámetro opcional scene_id en world_spawn, world_spawn_batch y ai_group_spawn que registra cada entidad creada en un registro del bridge.
- Tool scene_entities(scene_id): lista object_id, clase, posición y vivo/eliminado.
- Peer: servidor. Lectura sin lease.

Evidencia
- Consolidado §8: reset que borre entidades ajenas = riesgo crítico; mitigación: registro de propiedad.
- Criterio C2 del research: el reset borra el 100 % de lo suyo y nada ajeno.

Criterios de aceptación (R26)
- POS: 20 objetos con scene_id=a y 5 con scene_id=b: scene_entities(a) devuelve exactamente los 20.
- POS: Un objeto borrado a mano aparece como eliminado, no desaparece de la lista.
- NEG: scene_id desconocido: ok con lista vacía.
- NEG: scene_id con caracteres no permitidos o demasiado largo: bad_args.

Dependencias y riesgos
- Base de scene_clear.

Prioridad: P0 del MVP de cine/machinima (repetir tomas desde el mismo estado).

## 6. `scene_clear`

**Tool nueva scene_clear: borrar solo las entidades registradas en una escena, sin tocar nada más**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Resetear una escena hoy obliga a borrar object_id uno a uno y a recordarlos; no hay borrado por escena y un error deja restos o borra lo que no toca. En cine, cada toma nueva parte de la escena limpia.

Propuesta
- Firma: scene_clear(scene_id, timeout_s). Borra las entidades vivas del registro de esa escena, incluidos los grupos de IA.
- Peer: servidor. Requiere lease.
- Devuelve conteos por categoría: borradas, ya eliminadas y errores.

Evidencia
- Criterio C2 del research (consolidado §10, paso 2).
- Eden restaura el estado inicial al volver de PLAY (anexo A §2A.8).

Criterios de aceptación (R26)
- POS: 20 entidades con scene_id=a y 1 objeto sin escena: tras scene_clear(a), entities_query no encuentra ninguna de las 20 y el objeto sin escena sigue.
- POS: Escena con un grupo de IA de 4: los 4 desaparecen y ai_group_state da not_found.
- NEG: Entidades de la escena b no se tocan al limpiar la a.
- NEG: scene_id desconocido: ok con 0 borradas.

Dependencias y riesgos
- Depende de scene_entities.
- Nunca toca la persistencia del servidor (storage): solo entidades vivas registradas.

Prioridad: P0 del MVP de cine/machinima (reset entre tomas).

## 7. `world_spawn_batch`

**Tool nueva world_spawn_batch: crear muchas entidades en lotes por tick, con ajuste al suelo y resultado por item**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Aplicar una escena con world_spawn uno a uno es lento y propenso a errores, y crear cientos de golpe puede congelar el servidor. Un modelo débil tampoco encadena bien muchas llamadas. En cine es el atrezo y el decorado de cada plano.

Propuesta
- Firma: world_spawn_batch(items, per_tick=10, scene_id='', timeout_s). Cada item: type, pos (y=null ajusta al suelo como surface_query), rotation o ypr, flags.
- Peer: servidor. Requiere lease.
- Devuelve resultado por item (object_id o error) y estado global ok o partial.
- Tope de items por llamada; los infectados se crean con las flags que los inicializan.

Evidencia
- AD2 limita la tasa de pegado y Scenario Framework escalona el spawn (anexo A §3).
- Ficha 0eb8: infectados creados sin ECE_INITAI acaban con health01=0.
- dayz-mcp ya midió que un modelo de 27B llama mejor una operación con nombre que una cadena de tools.

Criterios de aceptación (R26)
- POS: 100 items con per_tick=10: se crean los 100 y la duración máxima de tick del servidor no supera un umbral fijado tras medir sin carga.
- POS: Items con y=null quedan a menos de 0,2 m del suelo según surface_query.
- NEG: 1 clase desconocida entre 10: 9 creados, 1 error con la clase; estado partial.
- NEG: items por encima del tope: bad_args antes de crear nada.

Dependencias y riesgos
- Usa scene_id de la ficha scene_entities.

Prioridad: P0 del MVP de cine/machinima (atrezo y decorado).

## 8. `ai_group_spawn`

**Tool nueva ai_group_spawn: crear un grupo de Expansion AI con facción, loadout, formación y waypoints**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
No hay forma de poner NPC humanos con IA desde el MCP. bot_start solo lanza acciones de depuración con TTL de 30 s como máximo (loopback.py, allowlist BOT_START_ACTIONS) y un PlayerBase creado por script no es un NPC autónomo. El MVP de cine necesita actores y extras: una cuenta de Steam es un solo cliente, así que el resto del reparto tienen que ser NPC.

Propuesta
- Firma: ai_group_spawn(faction, count, pos, loadout, formation, behaviour, waypoints=[], scene_id='', timeout_s).
- behaviour en un vocabulario propio y corto (HOLD, ONCE, LOOP, ROAM) que el bridge traduce a Expansion; así las escenas guardadas no cambian cuando llegue la IA propia.
- Peer: servidor. Requiere lease.
- Devuelve group_id, object_id de cada miembro y los campos aplicados tal como los lee el servidor.
- Fail-closed: si Expansion AI no está cargado responde expansion_unavailable y no crea nada.
- Integración por la API pública de Expansion en tiempo de ejecución, en un addon opcional separado o tras un define de Expansion; nunca copiando su código.

Evidencia
- Expansion AI es la IA humana de facto (≈984 k suscriptores): facciones, 12 formaciones, waypoints, loadouts JSON (research, anexo C §1).
- API citada por el research: eAIGroup.c:123,213,251,633 y spawn en eaicommandmanager.c:376-407 (rama experimental de DayZ-Expansion-Scripts); a re-verificar en la versión fijada.
- README de dayz-mcp: 'whether a synthetic survivor population is viable is open'.
- Una cuenta de Steam es un cliente (Knowledge Pack, dayz-mcp-bridge-protocol.md:129).

Criterios de aceptación (R26)
- POS: Grupo de 4 con behaviour LOOP y 3 waypoints: ai_group_state devuelve 4 miembros vivos a menos de 5 m del punto de spawn en el primer segundo y el grupo alcanza el waypoint 1.
- POS: Actor suelto (count=1, behaviour ONCE, 1 waypoint): llega a su marca a menos de 1,5 m y se queda quieto (menos de 0,5 m en 10 s).
- POS: faction y loadout aplicados coinciden con lo leído en el servidor (no con el eco de la petición).
- NEG: faction o formation desconocidas: bad_args que nombra el campo y los valores permitidos; 0 entidades creadas.
- NEG: Expansion AI no cargado: expansion_unavailable; 0 entidades creadas.
- NEG: count por encima del tope: bad_args antes de crear nada.

Dependencias y riesgos
- Licencia de Expansion CC BY-NC-ND: aclarar con sus autores si un addon que llama a su API (o hace modded class) es aceptable; preferir llamadas a la API pública.
- Uso comercial decidido: por la cláusula NC, Expansion queda como adaptador del MVP y el producto final usará una IA propia (fichas nav_path_query y survivor_drive).
- Rendimiento: Expansion pide FPS de servidor > 60 máx. y > 35 medio; más de 30 IA degradan sin Frame Time Optimization (research, anexo C T6). Fijar un tope de count.
- Depende de la ficha de scene_entities para el parámetro scene_id.

Prioridad: P0 del MVP de cine/machinima (actores y extras).

## 9. `ai_group_order`

**Tool nueva ai_group_order: cambiar comportamiento, waypoints, formación o velocidad de un grupo de Expansion AI**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Tras crear un grupo no hay forma de dirigirlo: en un rodaje hay que pararlo en su marca, mandarlo a otro punto o cambiar su formación entre tomas, como las órdenes del Game Master de Reforger.

Propuesta
- Firma: ai_group_order(group_id, behaviour=None, waypoints=None, formation=None, speed=None, hold=None, timeout_s). Solo se aplican los campos presentes.
- Peer: servidor. Requiere lease.
- Devuelve los valores aplicados leídos del grupo después del cambio.

Evidencia
- Órdenes en vivo como estándar de game master: Reforger (Move, Defend, Search and Destroy...), Eden, ZEN (research, anexo A §2A.5).
- Expansion ya define behaviour y formaciones del grupo (research, anexo C).

Criterios de aceptación (R26)
- POS: behaviour=HOLD: el desplazamiento de cada miembro es < 1 m durante 10 s (sin combate).
- POS: Nuevo waypoint a 50 m: el centroide del grupo se acerca al menos 20 m en 30 s.
- NEG: group_id desconocido o grupo ya eliminado: not_found; nada cambia.
- NEG: formation no válida: bad_args con los valores permitidos; el grupo conserva su estado.

Dependencias y riesgos
- Depende de ai_group_spawn y ai_group_state.
- En combate, la FSM de Expansion puede ignorar órdenes: el resultado debe decirlo, no fingir éxito.

Prioridad: P0 del MVP de cine/machinima (dirigir actores y extras).

## 10. `ai_group_state`

**Tool nueva ai_group_state (lectura): miembros, posiciones, salud, comportamiento y waypoint actual de un grupo de IA**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Sin una lectura del grupo no se puede pasar de 'orden enviada' a 'orden observada', que es la regla del bridge (Sent is not verified) y la base de los estados de la UI de Sandbox.

Propuesta
- Firma: ai_group_state(group_id) o ai_group_state(scene_id) para todos los grupos de una escena.
- Peer: servidor. Solo lectura, sin lease.
- Devuelve por miembro: object_id, pos, health, vivo/muerto, estado de la FSM si es legible; por grupo: behaviour, formation, índice de waypoint actual.

Evidencia
- Consolidado §6: estados pendiente, ejecutando, aplicado, observado, fallido, parcial.
- ARCHITECTURE-DECISIONS de dayz-mcp: un resultado ambiguo no se reenvía; se verifica con lecturas.

Criterios de aceptación (R26)
- POS: Las posiciones coinciden con object_inspect de cada miembro con error < 0,5 m.
- POS: Tras matar a un miembro con player_kill o daño, aparece como muerto en la siguiente lectura.
- NEG: group_id desconocido: not_found.
- NEG: Grupo sin miembros vivos: ok con la lista y alive=0, no error.

Dependencias y riesgos
- Depende de ai_group_spawn.

Prioridad: P0 del MVP de cine/machinima.

## 11. `camera_set`

**Ampliar camera_set: enfoque (profundidad de campo) con focus_distance y focus_blur**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Un plano de cine separa al actor del fondo con la profundidad de campo. camera_set tiene fov pero no enfoque, aunque la cámara scripted de BI lo admite con Camera.SetFocus.

Propuesta
- Parámetros nuevos en camera_set: focus_distance (m, > 0) y focus_blur (>= 0); si se omiten, el enfoque no cambia.
- Eco focus_applied, como fov_applied: no hay GetFocus en camera.c, así que es eco y no lectura nativa.
- Solo con cámara scripted: la cámara del jugador no es una instancia de Camera (camera.c:4).

Evidencia
- Camera.SetFocus(distance, blur), 'Depth of Field settings' (camera.c:70-74). Fuente: BohemiaInteractive/DayZ-Script-Diff.
- Necesidad P0 de cine en el research: cámaras guardadas y caminos con FOV/DOF (anexo B; consolidado §3).
- Relacionada con la ficha 983a (FOV aplicado en camera_set/camera_get); no la sustituye.

Criterios de aceptación (R26)
- POS: Actor a 2 m y fondo a 50 m, focus_distance=2: con focus_blur alto, la varianza del laplaciano de un recorte del fondo en capture_screenshot baja al menos un 30 % respecto a focus_blur=0.
- POS: focus_applied devuelve los valores enviados.
- NEG: focus_distance <= 0 o no finito, o focus_blur negativo: bad_args y la cámara no cambia.
- NEG: Con la cámara del jugador (camera_get.view='player'): no_scripted_camera y nada cambia.

Dependencias y riesgos
- Probe previo: comprobar si el desenfoque depende de la opción de vídeo de profundidad de campo del cliente y documentarlo en la descripción.
- camera_path_play podrá llevar el enfoque en cada clave.

Prioridad: P1 (aspecto de cine; no bloquea el primer rodaje).

## 12. `hud_set`

**Tool nueva hud_set: ocultar o mostrar el HUD sin tocar los controles, con lectura del estado aplicado**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Hoy el HUD solo se oculta como efecto de camera_set (SuppressGameplay desactiva los controles y hace GetHud().Show(false), MCPClientBridge.c:6858-6878), y restore_gameplay no puede comprobarlo: no hay lector de HUD en el wire. Para planos en primera persona o por encima del hombro, con el jugador actuando, el HUD tiene que desaparecer sin desactivar los controles.

Propuesta
- Firma: hud_set(visible, timeout_s). Peer: cliente. Requiere lease.
- Usa los mismos flags que la tecla de ocultar HUD de vanilla: HUD_HIDE y QUICKBAR_HIDE, vía ShowHudPlayer y ShowQuickbarPlayer; no toca HUD_DISABLE, que es la opción del menú.
- Devuelve el estado leído con IngameHudVisibility.IsContextFlagActive, no el eco.

Evidencia
- ingamehud.c:897-907 (ShowQuickbarPlayer, ShowHudPlayer) e ingamehudvisibility.c:17-25 (HUD_HIDE y QUICKBAR_HIDE son los flags de la tecla); IsContextFlagActive en ingamehudvisibility.c:120. IsHudVisible() está obsoleto y siempre devuelve false (ingamehud.c:1313).
- El bridge ya lee esos flags en MCP_ActionCursor.c:80.
- Necesidad de cine en el research: frames sin HUD (anexo B; consolidado §3).

Criterios de aceptación (R26)
- POS: hud_set(false) en tercera persona: el estado leído dice oculto y player_move sigue moviendo al jugador (los controles siguen activos).
- POS: Con un item asignado a la barra rápida, capture_screenshot no la muestra tras hud_set(false) y la vuelve a mostrar tras hud_set(true); el estado leído coincide en los dos casos.
- NEG: visible no booleano: bad_args.
- NEG: Sin cliente en partida: client_not_in_game y nada cambia.

Dependencias y riesgos
- El mismo lector permitiría que restore_gameplay verifique el HUD, que hoy deja en not_verified.

Prioridad: P1 (con la cámara scripted el HUD ya se oculta).

## 13. `server_perf`

**Tool nueva server_perf (lectura): FPS del servidor y recuento de entidades por categoría para los presupuestos**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
Los presupuestos de escena (IA, infectados, animales, objetos) necesitan una medida del coste real. Hoy no hay lectura del FPS del servidor ni conteos por categoría.

Propuesta
- Firma: server_perf(window_s=10). Devuelve FPS medio y mínimo de la ventana y conteos de IA, infectados, animales, vehículos, jugadores e items.
- Peer: servidor. Solo lectura, sin lease.
- API para el FPS a confirmar con un probe; no inventar una si no existe.

Evidencia
- Umbrales de Expansion: FPS de servidor > 60 máx. y > 35 medio; > 0,5 ms por IA indica el techo (anexo C T6).
- Criterio C6 del research: FPS por encima de un umbral con el presupuesto máximo.

Criterios de aceptación (R26)
- POS: El FPS reportado coincide con una medida independiente del servidor (log o diag) con ±10 %.
- POS: Tras crear 10 infectados, el conteo de infectados sube en 10.
- NEG: window_s fuera de rango: bad_args.
- NEG: Sin datos suficientes en la ventana: ok con insufficient_samples, no un valor por defecto (regla de dayz-mcp: un setter sin getter no se vuelve campo).

Dependencias y riesgos
- Probe previo de la API de FPS en servidor.

Prioridad: P1.

## 14. `nav_path_query`

**Tool nueva nav_path_query (lectura): ruta por navmesh entre dos puntos, para marcas de actores e IA propia**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
La meta es un producto standalone con IA propia, y su base es saber por dónde puede andar un NPC. También sirve en el MVP para comprobar que la marca de un actor es alcanzable. Nada en el MCP consulta el navmesh: el README de dayz-mcp lista FindPath, RaycastNavMesh, SampleNavmeshPosition y PGFilter como no probados.

Propuesta
- Firma: nav_path_query(from, to, snap_radius=2.0). Devuelve ok, la lista de puntos, length_m y los extremos ajustados al navmesh, o no_path.
- Peer: servidor. Solo lectura, sin lease.
- AIWorld se obtiene con GetGame().GetWorld().GetAIWorld() (su constructor es privado); FindPath con un PGFilter; SampleNavmeshPosition para ajustar los extremos.

Evidencia
- aiworld.c: PGFilter (59-67), constructor privado de AIWorld (72), FindPath (98), RaycastNavMesh (110), SampleNavmeshPosition (122); world.c:116 GetAIWorld. Fuente: BohemiaInteractive/DayZ-Script-Diff.
- README de dayz-mcp, 'Not tested': navmesh follow; new PGFilter() nunca instanciado en partida.

Criterios de aceptación (R26)
- POS: Dos puntos de la misma calle de Chernogorsk a 50 m: ok, longitud entre 50 y 75 m y cada punto a menos de 1 m del suelo según surface_query.
- POS: Extremos a 1 m del navmesh: los puntos ajustados están a menos de snap_radius de los pedidos.
- NEG: to en el mar, sin navmesh dentro de snap_radius: no_navmesh_at_to y ninguna ruta.
- NEG: Punto no finito: bad_args.

Dependencias y riesgos
- Probe previo: new PGFilter() y FindPath en DayZDiag y en servidor retail.
- Base de la IA propia, junto con survivor_drive.

Prioridad: P1 (base de la IA propia; en el MVP valida marcas).

## 15. `survivor_drive`

**Tool nueva survivor_drive (probe): mover por script un superviviente de servidor sin cliente, base de la IA propia**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
El producto final debe ser standalone, con IA propia y sin Expansion. La pieza mínima es mover por script un superviviente creado en el servidor, sin cliente: rumbo, velocidad y parada. Nada lo demuestra hoy: el README de dayz-mcp deja abierto si una población de supervivientes sintéticos es viable. infected_drive ya hizo lo mismo con infectados y tiene medidas.

Propuesta
- Verbo probe como infected_drive: survivor_drive(object_id, heading=None, speed=None, mode=None, timeout_s); mode='release' devuelve el control. Peer: servidor. Requiere lease.
- El superviviente se crea con CreatePlayer sin identidad (game.c:332) o con world_spawn de una clase Survivor; el probe anota cuál queda simulado.
- Dos mecanismos a comparar: overrides de HumanInputController (human.c:253-262) y un HumanCommandScript arrancado con StartCommand_ScriptInst (human.c:1236, 1624). El resultado dice cuál mueve al superviviente.
- Rechaza cualquier superviviente con PlayerIdentity: nunca mueve a un jugador conectado.

Evidencia
- README de dayz-mcp: 'Survivor locomotion overrides ... Whether a synthetic survivor population is viable is open' (Not tested).
- infected_drive a 90°: rumbo medido 92,1° y release devuelve la IA vanilla (README, In-game numbers).
- Expansion demuestra que hay supervivientes de servidor viables, pero su código no se puede copiar ni derivar (CC BY-NC-ND): diseño propio desde la API de BI.

Criterios de aceptación (R26)
- POS: heading=90 y velocidad de paso durante 10 s: avanza al menos 5 m con rumbo 90° ± 5° según object_inspect.
- POS: mode='release': velocidad < 0,1 m/s en menos de 2 s.
- NEG: object_id de un jugador conectado: refused_player_controlled y nada cambia.
- NEG: object_id que no es un superviviente: bad_target.

Dependencias y riesgos
- Si ningún mecanismo lo mueve, ese es el hallazgo (como en infected_drive) y la IA propia necesita otra vía.
- Sin código de Expansion: implementación limpia sobre scripts de BI.
- Con nav_path_query forma el primer paso de la IA propia (seguir una ruta).

Prioridad: P1 (spike de la IA propia; no bloquea el MVP, que usa Expansion).

## 16. `players_visibility`

**Tool nueva players_visibility (lectura): qué jugadores ven una posición, para editar o spawnear sin ser visto**

Tipo: request (tool nueva). Proyecto: DayZ Sandbox, MVP de cine/machinima en Chernarus, local y con uso comercial (decidido el 2026-10-23). Expansion AI entra en el MVP como adaptador; la meta es una IA propia y un producto final standalone.
Origen: research fase 0, AI/10_Projects/DayzSandbox/research/2026-10-23-dayz-sandbox-consolidado.md (vault).
Por qué en dayz-mcp: se implementa y mide primero aquí, que ya tiene bridge, lease y gates in-game; el mod de Sandbox copia después el patrón (consolidado §9).

Problema
En eventos y RP hay que preparar o cambiar cosas sin que los jugadores lo vean. Hoy habría que encadenar query_all_players y scene_raycast por jugador.

Propuesta
- Firma: players_visibility(pos, radius=0). Por jugador: distancia, si la posición queda dentro de su campo de visión aproximado y si hay línea de visión desde la cabeza.
- Peer: servidor. Solo lectura, sin lease.
- Documentar que el servidor no conoce la cámara exacta del cliente: es una aproximación.

Evidencia
- ZEN muestra un indicador de visibilidad de jugadores para el Zeus (anexo B §2).
- Necesidad P1 de eventos/RP: edición invisible a los jugadores (consolidado §3).

Criterios de aceptación (R26)
- POS: Objeto a 20 m delante de un jugador sin obstáculos: visible=true.
- POS: Mismo objeto detrás de un edificio (confirmado con scene_raycast): visible=false.
- NEG: Sin jugadores conectados: ok con lista vacía.
- NEG: pos no finita o radius negativo: bad_args.

Dependencias y riesgos
- Ninguna.

Prioridad: P2: fase de eventos/RP. En local y con cine como prioridad no hay jugadores a los que ocultar nada.
