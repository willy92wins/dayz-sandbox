# DayZ Sandbox: necesidades de los creadores (investigado 2026-10-23)

**Convención.** `[V#]` = leído en la fuente # (§6); `[I]` = inferencia mía; `†` = fuente anterior a 2024-10-23. Fechas de Workshop sin año = año en curso (convención de Steam) [I]. **Límites:** Reddit devolvió SITE_BLOCKED (r/dayz y r/dayzservers sin leer) y el presupuesto de búsqueda se agotó (Overwolf y diálogos de NPC en DayZ sin comprobar).

**Resumen**
- El cine en DayZ es un nicho vivo: Simple Cinematics ≈23 k suscriptores [V24] frente a COT ≈2,2 M [V26], Expansion-Quests ≈1,13 M, Expansion-AI ≈984 k [V34] y Survivor Animations ≈1,67 M [V37]. [I] La masa de usuarios está en servidores RP/PvE (NPC, misiones, animaciones); la cámara cine es el diferenciador.
- Hueco concreto: PCT (v0.1.0, 2026) ya trae paths, keyframes y DOF, pero "World (time/weather) · actors · lights · continuity assistants" sigue "Planned" (fase 4) y es solo cliente sobre CF+COT [V25]. [I] Control externo (backend/MCP/OBS) y actores son espacio libre.
- Streaming: Crowd Control no lista DayZ [V1]; en mis búsquedas (GitHub, web) no hallé mod de Twitch/Streamer.bot para DayZ [I]; los puentes existentes son HTTP-only o lentos (CFTools: acciones cada 5 s) [V21,22].
- Educadores: sin evidencia de DayZ en aulas; sí machinima, documental y academia [V43,44†,48†].

## 1. Por segmento

| Segmento | Jobs-to-be-done | Pain points | Herramientas hoy | Imprescindible |
|---|---|---|---|---|
| **(a) Machinima, cine, tráilers** | Planos repetibles (establishing, dolly, orbital) con actores, hora y clima controlados; frames sin HUD; componer fuera del juego [V45†,43] | Simple Cinematics no menciona paths/keyframes [V24]; el freecam de COT "isn't remote-controlled" [V25]; rodar con avatares reales costó ~1000 h y 3-4 años, con personajes perdidos, ciclo día/noche y parches [V44†,43] | Offline Mode, COT, Simple Cinematics, PCT, DayZ Editor [V28,26,24,25,27]; OBS/GeForce/capturadora + edición, cine en tercera persona con Offline Mode y zombis desactivados [V45†]; Unreal para componer (2026) [V43] | Paths con easing, FOV/DOF, presets, hora/clima congelables, actores posables, sin HUD, export de cámara a Blender [V25,55] |
| **(b) Streamers y audiencia** | Momentos disparados por chat/puntos/bits; overlays y escenas OBS automáticas; clips [I] | Sin integración DayZ [V1]; stream sniping, se aconsejaba retrasar el directo (2019†) [V47†]; desconfianza por "streams montados" y "streamer loot" (2021†) [V46†]; acciones de CFTools cada 5 s (60 s en Free) [V21]; en Project Zomboid, el mod de Twitch depende de app externa, parches (B42) y OAuth confuso [V17] | OBS; Streamer.bot (467 triggers, WS/HTTP/UDP, OBS, Stream Deck, CC) [V6]; Companion y Stream Deck [V11,13]; overlays oficiales de pago (49,99 EUR), gráficos sin datos en vivo declarados [V20] | Eventos de audiencia → backend → mod con seguridad (cooldown, pausa, zonas seguras, nombre del espectador) [V16]; overlay web [V9]; control OBS [V8] |
| **(c) Eventos, RP, PvE** | Eventos dinámicos, NPC de misión, escenarios repetibles, moderar sin romper inmersión [V32,33,39] | JSON extenso y roturas tras parches (Dynamic AI Missions: dudas sobre 1.30, servidor que no arranca tras actualizar Expansion) [V39]; mods de animación incompatibles entre sí [V37]; voces de NPC solo para traders estáticos y bots IA solo con saludos/amenazas genéricos [V38]; SurvivorMissions se escribe en Enforce Script [V40]; rediseño de COT con quejas y crashes (oct-2026) [V26] | Expansion AI/Quests [V34]; Dynamic AI Missions ≈46 k [V39]; TalkingNPC ≈119 k† [V36]; Survivor Animations (nació para un servidor RP) [V37]; COT ≈2,2 M y VPP ≈3,8 M [V26,35] | Editor visual de patrullas/NPC/misiones con export a JSON de Expansion; plantillas aleatorizables; presupuestos; roles; edición invisible [V31,58,59] |
| **(d) Educación y storytelling** | Narrar y estudiar: machinima, ensayo, documental; proyectos con roles (guion, dirección, voces, montaje) [V43,65†] | Tiempo de render, coste y curva técnica [V65†]; el documental en DayZ exige cientos de horas de juego real [V44†] | Captura + edición [V65†]; festivales y academia [V43,48†] | NPC con diálogo ramificado y botones→acciones (modelo Minecraft) [V62]; escenas guardables y compartibles [I] |
| **(e) Modders y mapeadores** | Escenas de prueba reproducibles, capturas para Workshop/tráiler, regresión [I] | "There is no assertion library and no test runner for Enforce Script" (afirmación del autor, sin fuentes) y sin test visual automático [V41]; DayZ Editor es solo offline [V27]; el freecam de Diag requiere build Diag [V29] | DayZ Editor ≈82 k [V27]; Offline Mode 433★ [V28]; Diag + Script Console [V29,30]; dz-testbench y MCP agéntico [V41] | Snapshot/restore de escena, recorridos de captura automáticos, export init.c/.vpp/JSON [V27,30,41] |

## 2. Herramientas de referencia

| Herramienta (juego) | Qué hace | Qué copiar |
|---|---|---|
| Replay Mod / Flashback (Minecraft) | Graba la sesión y la reproduce desde cualquier perspectiva; camera paths; render con FFmpeg [V50]. Flashback: overrides de FOV/clima/hora/shake, Track Entity, EXR y depth (web de fans) [V51] | Grabar una vez y re-filmar N veces (recamming [V64]); keyframes también para el entorno |
| Rockstar Editor + Director Mode (GTA V) | Captura start/stop, DOF, filtros; actores y animales que hablan y ejecutan acciones contextuales; hora y clima [V52†] | Reparto de actores + acciones + hora/clima como parámetros de escena |
| Fortnite Replays / Halo Theater | Fortnite: cámaras Drone Free/Follow/Attach, apertura/foco, velocidad, pausa de la hora; no exporta vídeo [V53]. Halo: freecam en cine y "machinima mode" en directo (Halo 5/Infinite) (Halopedia, secundaria) [V54] | Cámaras adjuntas a entidades; freecam en sesión viva |
| CS2 demos + HLAE | mirv_campath/camio/streams/fov en CS2; export a Blender/Cinema4D y matte/depth constan para Source/GoldSrc (paridad CS2 no verificada); aconseja Steam offline contra actualizaciones; riesgo VAC [V55] | Export de cámara a DCC, pases, fijar versión |
| Arma 3: Splendid Camera, UnitCapture, ambientAnim | Parar el tiempo ("la función más importante"), foco en cm, 10 presets de cámara, alternar HUD [V57†]; UnitCapture graba movimiento; sets de animación con nombre con snapTo y equipmentLevel; fallos de localidad en MP [V57] | Congelar tiempo, presets, grabar/reproducir actores, catálogo de poses con nombre |
| Arma Reforger Game Master + Scenario Framework; Zeus Enhanced | Entity Browser, órdenes a IA, presupuestos (objeto/IA/vehículo), hora/clima; Area→Layer→Slot→Task→Trigger con aleatorización sin código [V58]. ZEN: composiciones, indicador de visibilidad de jugadores [V59] | Jerarquía declarativa, presupuestos, aleatorización; ocultar ediciones |
| Unreal Take Recorder; Cyberpunk Photo Mode | Graba animación en secuencias con tomas no destructivas [V60]; Photo Mode: pausa, sin HUD, cámara dron, apertura/foco, 3 presets, poses [V61†] | Tomas; modo foto de un clic |
| Minecraft NPC | Sin código: nombre, diálogo, skin, comandos On Enter/On Exit, botones; ramificación por JSON y /dialogue [V62] | UX del NPC de misión |
| obs-websocket 5.x (OBS ≥28, puerto 4455) | StartRecord, SaveReplayBuffer, SetCurrentProgramScene, SetSceneItemTransform, GetSourceScreenshot, CallVendorRequest [V7,8]; filtro Chroma Key [V10] | Un clic = escena + grabación + nombre de toma |
| Companion / Stream Deck | Disparo por OSC/TCP/UDP/HTTP/WebSocket/ArtNet; módulo OBS con acciones, feedbacks y variables [V11,12]; plugins en TypeScript [V13] | Endpoints HTTP/OSC y estado como variables |
| Crowd Control SDK, Streamer.bot, EventSub | CC: Simple TCP/WebSocket JSON, respuesta ≤5 s, 4 resultados, efectos temporizados, reembolso al minuto [V3,4]; CC↔Streamer.bot [V5]; EventSub notifica canjes de puntos [V14] | Contrato de efecto (id, precio, duración, estado) |
| 7 Days to Die, Project Zomboid, ARK | 7D2D: puntos, cooldown, zonas seguras, pausa, nombre del espectador en el zombi [V16]; PZ: app externa + Streamer.bot [V17,18]; ARK Chaos Creator: Bits/puntos → dinos, loot, teletransporte, 52.922 descargas (2025) [V19] | Seguridad por defecto; alcance "solo streamer" |

## 3. Evidencia específica de DayZ

**Qué existe**
- **Oficial/dev:** Diag: Game > Free Camera (Home/End/Insert; Enter enlaza a un objeto; PgDn congela), spawn de infectados/animales, niebla [V29]. Script Console: FOV, DOF (foco, blur) con presets, ocultar UI [V30]. PluginSceneManager: escena = objetos + enlaces + init scripts + clima + fecha, guardable; editor desactivado en multijugador [V30].
- **Cámara:** Offline Mode (INSERT; spawn de objetos, zombis y animales) [V28]; COT (freecam; 2026-10-14: compatibilidad 1.30, roles en vez de permisos) [V26]; Simple Cinematics (FOV, velocidad, suavizado, DOF; clima/hora con allow-list de SteamID) [V24]; DayZ Editor (offline, "filmmaker tools", export init.c/.vpp) [V27]; PCT (focal 8-400 mm, apertura→DOF, auto-encuadre, Catmull-Rom, export CSV/JSON) [V25]. Dependen de Dabs Framework (Simple Cinematics, DayZ Editor) o CF+COT (PCT) [V24,27,25].
- **Actores:** Expansion AI en JSON: Behaviour (HALT, LOOP, ROAMING…), Faction (Passive, Observers…), DefaultStance/LookAngle; flujo en juego "CTRL+click + Export Patrol" [V31]; NPC con `SetNPCEmoteID` [V32]; 10 tipos de objetivo de quest (AIPatrol, AICamp, AIEscort…) [V33]; TalkingNPC (trigger → sonido + animación de hablar; emotes propios solo como plan futuro; bug con OGG) [V36]; Survivor Animations (~30 emotes; choca con otras mods) [V37]; ZenExpansionAudioAI (.ogg por NPC/quest; traders solo estáticos; bots IA con saludos/amenazas genéricos) [V38]. No hallé lip-sync nativo ni mods de lip-sync [I].
- **Gestión:** CFTools GameLabs agrupa los envíos (acciones cada 5 s; 60 s en Free) porque, según su ayuda, DayZ no ofrece forma estable de empujar datos en vivo [V21]; la home de Takaro no menciona DayZ [V23]; puente comunitario DayZ-Takaro (mod de servidor + sidecar Node porque RestApi de Enforce Script es solo HTTP; modelo polling/POST; teleport/give sin probar; consola solo `say`) [V22]; MCP agéntico: buzón JSON, estado por segundo, `client_shot` [V41].
- **Obras:** Knit's Island (3 avatares: cámara, técnico, entrevistador), Artificial Abyss (2023), película de Santalucia 2026 (DayZ + Unreal + animación procedural) [V43,44†].

**Qué echan en falta (solo lo documentado)**
- Mundo (hora/clima), actores, luces y continuidad en la misma herramienta: PCT lo deja en fase 4 "Planned" [V25]. Cámara gobernable desde fuera del cliente: PCT es solo cliente [V25]; no hallé API externa [I].
- Emotes propios y audio de NPC estable [V36,38]; compatibilidad tras parches [V39,26].
- Foro oficial (DayZ Mod/Arma 2, s/f, antiguo† [I]): quien filma quiere mover la cámara y hacer timelapse día-noche a la vez; el editor lo hace a tirones y el apaño es cámara fija + acelerar el tiempo + montaje [V66†].
- Peticiones de usuarios sobre cámaras en Standalone: no legibles (Workshop de Simple Cinematics y DayZ Editor sin comentarios) [V24,27].

**Streaming:** Crowd Control: DayZ ausente de ≈325 entradas, que sí incluyen Project Zomboid, Rust, ARK:SA y Escape from Tarkov [V1]; CC dice que el multijugador online es improbable sin aprobación del desarrollador (s/f) [V2].

## 4. Prioridades por segmento (P0 = MVP; P1 = siguiente; P2 = después)

**(a) Cine**
- P0 Cámara con paths/keyframes, focal/DOF y presets: PCT ya lo hace, solo en cliente [V25]; Simple Cinematics no tiene paths [V24]; presets en Splendid Camera y Script Console [V57†,30].
- P0 Hora/clima fijables (y acelerables para timelapse) y escena congelada: "parar el tiempo" es la función clave en Arma 3 [V57†]; timelapse con cámara móvil [V66†]; PCT lo deja en fase 4 [V25]; Expansion `HALT` deja la patrulla quieta salvo combate [V31].
- P1 Actores con emotes/poses y marcas: emotes por ID [V32], ~30 extra pero con conflictos [V37]; catálogo con nombre tipo ambientAnim [V57].
- P1 Grabar y reproducir actuaciones (UnitCapture, Take Recorder) [V57,60]; en DayZ no hallé replay [I].
- P2 Export de cámara a Blender, depth/matte, chroma en OBS [V55,10]; voz: audio + animación de hablar [V36]; Rhubarb (audio→formas de boca 2D) solo como idea [V63].

**(b) Streamers**
- P0 Contrato de efectos (id, precio, duración, estado; respuesta ≤5 s) [V3,4] sobre polling ≤1 s [I; V41].
- P0 Seguridad: cooldowns, pausa, zonas seguras, alcance solo-streamer, nombre del espectador [V16].
- P0 OBS por WebSocket (escena, grabación, replay buffer) y overlays web [V8,9].
- P1 Conectores Streamer.bot, Companion/Stream Deck (HTTP/OSC), EventSub [V6,11,13,14].
- P2 Pack CC propio o Twitch Extension: dependen de aprobación de terceros [V2] y el estado de Extensions es incierto [V2,15].

**(c) Eventos, RP**
- P0 Editor visual de patrullas/NPC/quests que exporte JSON de Expansion, con captura en juego (Export Patrol); base instalada enorme [V31,33,34].
- P0 NPC de misión sin código (nombre, diálogo, botones→acciones, emote) [V62,32].
- P0 Escenarios repetibles: plantilla, aleatorización y reset [V58].
- P1 Presupuestos IA/objetos [V58]; roles [V26]; edición invisible a jugadores [V59]; pruebas por versión [V41,39].
- P2 Audio de NPC mapeado automáticamente [V38]; detector de conflictos de animación [V37].

**(d) Educación/storytelling** (evidencia baja)
- P1 Diálogo ramificado + objetivos [V62,33]; P1 exportar/compartir escenas (Workshop de Source Filmmaker [V56]; proyectos compartibles en FiveM [V42]); P2 guion/shot list y subtítulos [I].

**(e) Modders**
- P0 Snapshot/restore de escena (PluginSceneManager guarda objetos, clima y fecha) [V30] y export init.c/.vpp [V27].
- P0 Recorrido de captura automático por waypoints (Tour Mode, `client_shot`) [V41].
- P1 Presets de mapa/hora/clima y diff visual [I]; P2 matriz de spawns (Diag) [V29].

## 5. Dudas abiertas
- Demanda en Reddit/Discord sin medir (SITE_BLOCKED); en foros y tracker de BI solo hallé un hilo antiguo [V66†] y ninguna petición de cámara para DayZ (búsqueda limitada). Overwolf y diálogos de NPC en DayZ sin comprobar.
- Workshop mostró "removed/incompatible" en todos los ítems, incluso COT (activo hoy) [V26]: lo trato como artefacto de acceso; confirmar en navegador.
- Animaciones de NPC más allá de emotes en DayZ vanilla y viabilidad de lip-sync: sin evidencia; hace falta un spike técnico.
- Latencia extremo a extremo: scripts HTTP-only [V22], CFTools 5 s [V21], CC exige respuesta ≤5 s [V3].
- Twitch Extensions: CC dijo que no hay actualizaciones (s/f) [V2]; Twitch indica revisiones reanudadas [V15].
- Licencias: scripts de BI bajo DPL no comercial [V30]; COT CC-BY-SA-4.0 [V26]; PCT sin licencia y en v0.1.0 con pocos commits, continuidad incierta [V25]; Simple Cinematics prohíbe repack [V24]; monetización de servidores: la página primaria no muestra caducidad, una fuente secundaria cita 2027-01-31 (no verificado) [V49].

## 6. Fuentes
(† = anterior a 2024-10-23; s/f = sin fecha. Suscriptores y comentarios de Workshop: páginas públicas leídas el 2026-10-23.)

1. https://crowdcontrol.live/games (CC: juegos)
2. https://crowdcontrol.live/games-and-features-not-coming-to-crowd-control-anytime-soon/ (CC: no llegará, s/f)
3. https://developer.crowdcontrol.live/sdk/simpletcp/index.html
4. https://developer.crowdcontrol.live/sdk
5. https://crowdcontrol.live/guides/streamerbot/
6. https://streamer.bot/features
7. https://github.com/obsproject/obs-websocket
8. https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md
9. https://obsproject.com/kb/browser-source
10. https://obsproject.com/kb/filters-guide (Chroma Key)
11. https://bitfocus.io/companion
12. https://bitfocus.io/connections/obs-studio
13. https://docs.elgato.com/streamdeck/sdk/introduction/getting-started
14. https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/
15. https://dev.twitch.tv/docs/extensions/
16. https://7daystodie.wiki.gg/wiki/Twitch_Integration
17. https://steamcommunity.com/sharedfiles/filedetails/?id=2629375490 (PZ Twitch Events, act. 2024-01†)
18. https://steamcommunity.com/sharedfiles/filedetails/?id=3637116523 (PZ ChatterZ)
19. https://www.curseforge.com/ark-survival-ascended/mods/chaos-creator (2025)
20. https://www.own3d.tv/en/shop/day-z-overlays/ (s/f)
21. https://cftools.com/help/platform/day-z
22. https://github.com/mad-001/DayZ-Takaro-Integration (2026)
23. https://takaro.io/
24. https://steamcommunity.com/sharedfiles/filedetails/?id=2547108825 (Simple Cinematics)
25. https://github.com/Psyern/PsyernsCinematicTool (README 2026)
26. https://steamcommunity.com/sharedfiles/filedetails/?id=1564026768 (COT; también https://steamcommunity.com/sharedfiles/filedetails/changelog/1564026768, https://steamcommunity.com/sharedfiles/filedetails/comments/1564026768, https://github.com/Jacob-Mango/DayZ-CommunityOnlineTools)
27. https://steamcommunity.com/sharedfiles/filedetails/?id=2250764298 (DayZ Editor; también https://github.com/InclementDab/DayZ-Editor)
28. https://github.com/Arkensor/DayZCommunityOfflineMode
29. https://community.bistudio.com/wiki/DayZ:Diag_Menu
30. https://github.com/BohemiaInteractive/DayZ-Script-Diff (scripts BI)
31. https://github-wiki-see.page/m/salutesh/DayZ-Expansion-Scripts/wiki/%5BServer-Hosting%5D-How-to-create-AI-Patrols (patrullas)
32. https://github.com/salutesh/DayZ-Expansion-Scripts/wiki/%5BModding%5D-Advanced-quest-events-and-features (quests y NPC)
33. https://github.com/salutesh/DayZ-Expansion-Scripts/wiki/%5BServer-Hosting%5D-Quest-Configuration-%E2%80%90-Experimental/2aa92d111b5d0e5672a97ee6aa3f9ed8f5638f24 (config de quests)
34. https://steamcommunity.com/sharedfiles/filedetails/?id=2792982069 y https://steamcommunity.com/sharedfiles/filedetails/?id=2828486817 (Expansion-AI y -Quests)
35. https://steamcommunity.com/sharedfiles/filedetails/?id=1828439124 (VPP Admin Tools)
36. https://steamcommunity.com/sharedfiles/filedetails/?id=2599373319 (TalkingNPC, act. 2024-02†)
37. https://steamcommunity.com/sharedfiles/filedetails/?id=2918418331 (Survivor Animations)
38. https://github.com/ZenarchistCode/ZenExpansionAudioAI/wiki
39. https://steamcommunity.com/sharedfiles/filedetails/?id=3277130230 (Dynamic AI Missions)
40. https://github.com/Bitverbieger/SurvivorMissions
41. https://github.com/LucasSKrewer/dz-testbench y https://github.com/covalschi/dayz-agentic-modding-mcp (2026)
42. https://forum.cfx.re/t/standalone-professional-camera-system/5320916 (FiveM, 2025)
43. https://milanmachinimafestival.org/blog/tag/DayZ
44. https://www.screenslate.com/articles/teleported-ekiem-barbier-and-guilhem-causse-knits-island (2023†)
45. https://www.youtube.com/watch?v=Z8XcKFgMhGM (Scalespeeder, 2021†)
46. https://steamcommunity.com/app/221100/discussions/0/3130541122085593812/ (2021†)
47. https://steamcommunity.com/app/221100/discussions/0/3140616601476614364 (2019†)
48. https://www.researchgate.net/publication/262282970_Death_and_dying_in_DayZ (2013†)
49. https://www.bohemia.net/monetization (secundaria: https://www.gameserverkings.com/knowledge-base/dayz/server-monetisation/)
50. https://www.replaymod.com/ (también https://github.com/ReplayMod/ReplayMod, https://www.replaymod.com/docs)
51. https://modrinth.com/mod/flashback (web de fans: https://flashback-mod.com/flashback-vs-replay-mod/)
52. https://www.pcgamer.com/gta-5-pc-director-mode/ (2015†)
53. https://dev.epicgames.com/documentation/en-us/fortnite/replays-feature-in-fortnite-creative
54. https://www.halopedia.org/Theater_Mode (secundaria)
55. https://github.com/advancedfx/advancedfx (también https://github.com/advancedfx/advancedfx/wiki)
56. https://store.steampowered.com/app/1840/Source_Filmmaker/
57. https://community.bistudio.com/wiki/Arma_3_Splendid_Camera (también https://arma3.com/news/this-is-war-photography, 2013†; https://community.bistudio.com/wiki/BIS_fnc_unitCapture; https://community.bistudio.com/wiki/BIS_fnc_ambientAnim)
58. https://community.bistudio.com/wiki/Arma_Reforger:Game_Master (también https://community.bistudio.com/wiki/Arma_Reforger:Scenario_Framework)
59. https://github.com/zen-mod/ZEN
60. https://dev.epicgames.com/documentation/en-us/unreal-engine/take-recorder-in-unreal-engine
61. https://www.techradar.com/news/cyberpunk-2077-photo-mode-how-to-take-next-level-snaps-in-night-city (2020†)
62. https://learn.microsoft.com/en-us/minecraft/creator/documents/createnpcs (también https://learn.microsoft.com/minecraft/creator/documents/NPCDialogue)
63. https://github.com/DanielSWolf/rhubarb-lip-sync
64. https://en.wikipedia.org/wiki/Machinima
65. https://iste.org/blog/The-complete-guide-to-using-machinima-in-the-classroom (2015†)
66. https://forums.dayz.com/topic/132413-questions-of-how-to-make-dayz-cinematics/ (DayZ Mod/Arma 2, s/f, antiguo† [I])