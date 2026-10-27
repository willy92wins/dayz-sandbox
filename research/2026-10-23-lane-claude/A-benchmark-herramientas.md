# Benchmark de herramientas de creación, sandbox y game master (para DayZ Sandbox)

Corte: 2026-10-23. **[V n]** = leído en la fuente n (URL en la sección 5); **[I]** = inferencia mía; **†** = fuente secundaria, comunitaria, de más de 2 años o sin fecha comprobable (puede estar desfasada).

## 1. Matriz feature × herramienta

Leyenda: S = sí [V]; P = parcial o limitado [V]; N = ausente, documentado [V]; ? = sin dato (laguna mía, no implica que no exista); † = solo fuente secundaria o antigua. "Colocar" = gizmos, rejilla o snap (o equivalente por comandos/brochas). Última columna = IDs de la sección 5.

|Herramienta|Colocar|Prefab|NPC/IA|Lógica|Hora/clima|Cine|Guardar/pub.|Colab/roles|Presup.|Test|Undo|Onboard|IA/MCP|Src|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|MC Bedrock Editor|S|P|?|?|?|?|P|P|?|?|S|S|?|1-6|
|MC Creator Tools (mctools.dev)|?|P|?|P|?|?|P|?|?|P|?|S|S|7|
|MC Education|?|?|P|P|?|P|?|S|?|?|?|?|?|14,15|
|MC comandos / structure block / datapack|P|S|P|S|S|P|S|P|S|P|?|?|?|8-13|
|WorldEdit|P|S|?|P|?|?|S|S|S|?|S|?|?|16-20|
|Axiom|S|S|?|P|?|P|S|P|?|?|S|?|?|21,22|
|Replay Mod / Flashback|?|?|?|?|?|S|P|?|?|?|?|?|?|23,24|
|Roblox Studio (+Assistant, MCP)|S|S|P|S|P|P|S|S|P|S|S|P|S|25-38|
|Fortnite Creative / UEFN|S|S|S|S|P|S|S|S|S|S|S†|S|P|39-54|
|Arma 3 Eden|S|S|S|S|S|P|S|?|P|S|S|?|?|55-62,71|
|Arma 3 Zeus + ZEN/Achilles|P|S|S|P|S|P|P|S|S|?|?|?|?|63-68|
|Reforger Game Master|S|P|S|P|S|P|?|P|S|?|?|?|?|69|
|Reforger Workbench + Scenario Framework|?|S|S|S|P|?|P|?|P|S|?|?|?|70,72|
|Garry's Mod (spawnmenu, AD2, Wiremod, PAC3)|P|S|P|S|?|?|S|S|S|?|S|?|?|73-79,108|
|s&box|P|S|P|S|?|?|P|S|?|S|S|?|S|80-90|
|Halo Infinite Forge|S|S|S|S|P|?|S|S|S|S|P|P|?|91-96|
|GTA V Rockstar Editor + Director Mode|P†|?|P†|?|S†|S†|S†|?|?|?|?|?|?|97-100|
|FiveM txAdmin|?|?|?|?|?|?|?|S|P|?|?|S|?|101-103|
|Menyoo / Object Spooner|S|P†|P|?|P†|?|S†|?|?|?|N†|?|?|104,105|

RedM comparte FXServer con FiveM [V 106]; no encontré herramientas de creación propias que añadan algo distinto [I].

## 2. Lista priorizada

"Mejor" es mi juicio [I] sobre lo leído.

### 2A. Estándar: el usuario lo dará por hecho (por orden de prioridad)

1. **Gizmos de mover/rotar/escalar, local/global, rejilla y snap a superficie.** Mejor: Eden (pasos de 0,25 m y 5°, orientar a la normal del terreno) [V 56]; Roblox suma colisiones on/off, alinear y pivotes [V 28]. Menyoo solo los incorporó en la v2.4.0 [V 104].
2. **Selección múltiple, copiar/pegar, prefab y capas ocultables/bloqueables.** Mejor: Roblox Packages (versiones, diff visual/propiedades/script, auto-update, permisos) [V 29]; Eden Compositions conservan atributos, capas y conexiones [V 58]; las capas anidan [V 57].
3. **Undo/redo como transacciones nombradas.** Convergen cuatro motores: s&box `UndoScope` [V 82], Roblox `TryBeginRecording`/`FinishRecording` [V 35], Eden `collect3DENHistory` [V 61], Bedrock `TransactionManager` (solo nombres de API [V 5]; Undo/Redo anunciado [V 3]). Peor: Menyoo sin undo [V† 105]; Forge solo en solitario [V 91].
4. **Catálogo buscable y filtrable.** Mejor: Entity Browser de Reforger (facción, tipo, rol, rasgo, contenido modeado) [V 69].
5. **Órdenes de IA: waypoints con comportamiento, formación, velocidad y modo de combate.** Mejor: Eden (Careless a Stealth, formaciones, condición/timeout, sincronía con triggers) [V 60]; Reforger lo hace en vivo con Alt+1…6: Move, Forced Move, Move Relaxed, Search and Destroy, Defend, Get In [V 69].
6. **Hora y clima en vivo.** Mejor: Reforger (presets horarios, fecha, multiplicador 0,1×–12×, clima, viento) [V 69]; Eden los fija como atributos de escenario [V 61]; ZEN: Change Weather y Set Date [V 65].
7. **Presupuestos visibles con tope duro.** Reforger: 4 presupuestos; al 100 % no se añade más; "Clear Destroyed Entities" [V 69]. UEFN: 100.000 unidades, impide publicar, lista los 100 assets más pesados [V 40]. Forge: 32 IA como máximo [V 91]; al excederse el presupuesto de ejecución, el motor deja de crear instancias [V† 92]. Zeus: puntos 0–1 con coste por acción [V 63].
8. **Probar sin salir del editor.** Eden: al volver de PLAY, el escenario recupera su estado inicial [V 55]; Roblox: Test, Test Here, Run, hasta 8 clientes y simulador de dispositivo [V 31]; s&box: instancias que se unen a la sesión con hotload reflejado [V 87].
9. **Guardar, compartir y publicar con versión.** Forge: historial de versiones, una sola publicada, protección de copia [V 91]; Eden: .pbo y Workshop [V 62]; AD2: autoguardado de área y "Map Save" que carga al arrancar el servidor [V 75]; UEFN: código de versión privada para compartir antes de publicar, luego clasificación IARC y moderación en el Creator Portal [V 41].
10. **Roles y permisos.** txAdmin, permisos finos como `players.teleport` o `menu.vehicle` [V 102]; Roblox, Owner/Edit/Play [V 30]; WorldEdit, nodos de permiso por comando [V 17].
11. **Presets de jugador, reglas de partida y loadout copiable.** Eden: slots jugables, rol, estado, identidad, equipo [V 61]; Reforger: facciones, spawn points, objetivos, respawn [V 69]; ZEN y Achilles copian/pegan unidades con equipo completo [V 67,68].
12. **Acciones sobre jugadores.** txAdmin: un permiso por acción (`players.freeze`, `players.heal`, `players.spectate`, `players.teleport`) [V 102] y menú con Go To y Bring [V 103]; ZEN: Heal y Teleport Players [V 67].
13. **Comentarios anclados a la escena.** Eden (entidad Comment) [V 61], ZEN [V 64], Roblox con @mención sobre un objeto del viewport [V 30].
14. **UI personalizable.** Bedrock Editor: escala, fuente, tema, barra de acciones y hotbars [V 1]; Axiom: layouts de ventana y keybinds [V 21,22]; ZEN: menú contextual desactivable o solo por tecla [V 67].

### 2B. Diferenciales: pocas herramientas los resuelven bien

1. **GM en vivo con menú contextual, módulos y control remoto.** Mejor: ZEN, 64 módulos (conteo mío) y API para módulos propios (`zen_custom_modules_fnc_register`, máx. 200) [V 64-66]. Reforger gana en UX de órdenes (radial, Ping, Take Control) [V 69].
2. **Exportar la sesión en vivo como script.** Único: ZEN "Export Mission SQF", que restaura la misión actual [V 65]. Reforger no documenta guardado de sesión [V 69].
3. **GM acotado por costes y áreas.** Zeus: coeficientes por colocar/editar/borrar, áreas editables y de cámara, varios curadores [V 63]; sirve de "modo evento" limitado [I].
4. **Escenarios sin código con despawn por proximidad.** Scenario Framework: Area→Layer→Slot, tareas, `Balance On Players Count`, chequeo de despawn cada 4 s con spawn escalonado [V 70]; lo más cercano a zombis/animales [I]. Límites: nodos placeholder y depuración no apta para multijugador [V 70].
5. **Lógica visual.** UEFN: direct event binding entre devices [V 39], 214 clases y structs en su Verse API [V 51]; Forge Node Graph (Script Brain: 128 nodos/512 conexiones) [V† 92]; s&box ActionGraph [V 83]. Para no programadores, UEFN + Scenario Framework [I].
6. **Asistente IA: plan, aprobación, ejecución, playtest.** Roblox Planning Mode: los planes nunca se autoejecutan, solo actúa el botón Build [V 25]; agente de playtest en beta y 44 % de sus 1.000 mayores creadores usa Assistant o IA externa vía MCP (cifra de Roblox) [V 27].
7. **MCP oficial en el motor.** Roblox: 26 tools (conteo mío), `studio_id` en cada llamada, `subagent` explore/playtest, `execute_luau`, `screen_capture` [V 26]; s&box: activo por defecto, solo localhost, `search_tools`/`call_tool`, `[McpTool.ReadOnly]` [V 81]; Creator Tools: MCP local sobre el proyecto [V 7].
8. **IA programable por API, con límites documentados.** UEFN `npc_behavior`: `NavigateTo`, `MaintainFocus`, leash; alertas y armas solo en Guard, Custom y Wildlife no equipan armas [V 45]. Roblox Pathfinding: costes, `PathfindingLink`, topes de 3.000 studs y 20.000 nodos [V 32].
9. **Acciones y animaciones de IA humana.** ZEN: Ambient Animation (se corta ante disparos en modo de combate) y Sit On Chair [V 65]; UEFN "Stand Up": NPC actúan ante público con Character, Chair e Input Trigger [V 50]; Menyoo v2.4.0: guardado y carga de animaciones [V 104]; Director Mode: acciones y diálogos [V† 98].
10. **NPC con LLM en runtime.** UEFN Personas: prompts y voz, salidas estructuradas que disparan eventos, Gemini 3.1 Flash-Lite + ElevenLabs; Experimental, aún no publicable [V 52,53].
11. **Cine: grabar primero, dirigir después.** Replay Mod (<10 MB/h, rutas de cámara) [V 23]; Rockstar Editor (marcadores con cámara/DOF/velocidad; en PC solo Story Mode) [V† 98,100; V 97]; UEFN Sequencer con Gameplay Events [V 46]; Bedrock `/camera` (easing, FOV, fade, spline) [V 8].
12. **Colaboración en tiempo real.** Roblox Team Create (Live Scripting, Drafts, historial, comentarios) [V 30]; UEFN Lore (auto-checkout/lock, Auto Revert) [V 42]; Forge (hasta 8 jugadores por sesión; Editor/Co-Owner/Admin) [V 91].
13. **Operación de servidor.** txAdmin: recipes ("servidor en menos de 60 s"), reinicios programados con avisos, monitor CPU/RAM, whitelist/bans [V 101,103].
14. **Director de ritmo de zombis (fuera de lista).** L4D2: `CommonLimit`, `MobSpawnMinTime/MaxTime`, `ZombieSpawnRange` y fases BUILD_UP→RELAX [V† 107].

## 3. Patrones aplicables a DayZ Sandbox

### Copiar

1. **Dos modos, un mismo formato de escena** [I; base V 55,58,65,69]. Editor web tipo Eden (capas, composiciones, triggers, preview con restauración de estado) y GM en vivo tipo Zeus/Reforger (menú contextual, órdenes, presupuesto). Las composiciones de Eden ya funcionan también en Zeus [V 58]; la sesión en vivo debería volcarse al editor, como el "Export Mission SQF" de ZEN.
2. **Presupuesto servidor-autoritativo y de primera clase** [I; base V 69,63,92,40,61]. Categorías (objetos, zombis, animales, IA humana, vehículos, sistema), tope duro, limpiar destruidos, coste por acción del GM, medidor en la UI y, al agotarse, dejar de crear instancias en vez de degradar el servidor. Exponer limpieza de cadáveres y simulación dinámica como atributos de escenario, como Eden [V 61].
3. **Spawn/despawn por proximidad, escalonado y escalado por jugadores** [I; base V 70,76]. Modelo del Scenario Framework más la tasa de pegado limitada de AD2 (`AdvDupe2_SpawnRate`) para que cargar una escena grande no congele el servidor.
4. **Todo cambio es una transacción nombrada, también los de MCP** [I; base V 82,35,5,18]. Undo por usuario: WorldEdit guarda historial por jugador (15 acciones por defecto), deja deshacer a otros con permiso y no registra efectos indirectos [V 18].
5. **Composiciones con capas, atributos y conexiones, versionado y overrides** [I; base V 29,58,44,84]. Diff entre versiones (Packages), overrides por instancia y prefabs anidados (Scene Graph, s&box).
6. **IA humana como perfiles reutilizables** [I; base V 70,65,45]. Opciones de SlotAI (skill, combat type, formation, perception factor, Waypoint Set), catálogo de comportamientos (Garrison, Patrol, Sit On Chair, Ambient Animation) y límites documentados por tipo de NPC, como UEFN.
7. **Roles como permisos de texto y plantillas de rol** [I; base V 86,30,91,102,63]. Claims tipo s&box (`config/users.json`), Owner/Edit/Play (Roblox), Editor/Co-Owner/Admin (Forge), permisos finos tipo txAdmin; GM por asignación explícita (Zeus asigna por unidad, UID o admin).
8. **Diseño de dayz-mcp** [I; base V 26,81,25]. (a) Pocas herramientas visibles y `search_tools`/`call_tool` para las 88; (b) parámetro de instancia (`server_id`, como el `studio_id` de Roblox) en cada llamada; (c) lecturas libres y mutaciones con plan, aprobación y ejecución; (d) resultados con tope (Roblox: búsquedas de 10 y 50 resultados; s&box: `limit`/`offset`); (e) captura de pantalla y consola como verificación, más un subagente de playtest.
9. **Onboarding y entrada guiada** [I; base V 7,50,2,103,93]. Plantillas por nivel (Creator Tools: Beginner a Advanced), 15 Feature Examples + 14 Game Examples (UEFN), un tutorial guiado único (Bedrock Editor), "recetas" de despliegue (txAdmin) y elegir lienzo como primer paso (Forge: 8 canvases con spawn points).
10. **Modo Director para creadores** [I; base V 23,98†,100†]. Reparto de actores IA, hora, clima, cámara libre y marcadores; grabar y dirigir después, como Replay Mod.

### Evitar

1. Sin undo (Menyoo) [V† 105]; undo solo en solitario y sin autosave tras caída (Forge) [V 91,94].
2. Presupuesto aplicado solo al publicar: UEFN deja excederlo mientras editas [V 40]. Aplicarlo en vivo [I].
3. Guardar proyectos solo en el navegador: mctools.dev avisa de que puede borrarlos [V 7]. Persistir en el backend [I].
4. Depender de forks o APIs inestables: Achilles dejó de tener desarrollo activo a favor de ZEN [V 68]; `@minecraft/server-editor` es pre-release y "puede eliminarse" [V 5]. Versionar API y MCP desde el día uno [I].
5. Marcos con nodos placeholder y depuración no pensada para multijugador (Scenario Framework) [V 70].
6. Rol de GM rígido: en Reforger lo toma el primer jugador que conecta (host/admin siempre acceden) y no se transfiere salvo desconexión [V 69]. Permitir asignarlo desde la UI [I].
7. NPC con LLM sin guardarraíles: Epic añade capas de seguridad, reglas y aún no permite publicar [V 52,53]. Si se añade diálogo por IA, filtrar y registrar [I].

## 4. Dudas abiertas

1. Las páginas de Epic sobre el lenguaje Verse y sobre publicar islas en Fortnite Creative, y el newswire de Rockstar, cargan por JavaScript y no pude leerlas (la publicación de UEFN sí [V 41]); Verse y Director Mode quedan en fuentes secundarias†.
2. BI wiki: fallaron "Eden Editor: Modules" y la página de Zeus; la de Workbench es mínima [V 72]. No verifiqué coedición en Eden ni undo en Zeus o Game Master de Reforger.
3. Forge: solo hallé "incremental magnet snapping" [V 93]; los 7.000 objetos vienen de Halopedia† [V 95] y el soporte oficial dice "miles" [V 91]. El artículo de presupuestos es de 2023† [V 92].
4. Axiom: permisos de servidor, límites por jugador y timeline no verificados (documentación truncada); multijugador privado exige whitelist o licencia comercial [V 22].
5. Bedrock Editor: sin evidencia de spawn de entidades, hora/clima ni cine en la UI (solo nombres `ITimelinePlayer` y `DaylightCycle` en la API pre-release [V 5]); el README de Mojang dice "solo Preview" y Learn "Retail y Preview" [V 4,6†].
6. GMod: physgun, menú contextual, Wiremod E2 y eventos de PAC3 apenas leídos [V 73-79]; la página Sandbox de Facepunch indica "Updated: A Long Time Ago" [V† 108].
7. txAdmin: formato de recipes no leído; RedM sin nada propio. s&box: snap/rejilla del editor no verificados; la página del juego Sandbox no devolvió contenido.
8. Fuera de alcance: licencias (FiveM exige el Rockstar Games Creator Platform License Agreement [V 106]; Bohemia no investigada), necesidades reales de creadores DayZ y ecosistema DayZ existente.

## 5. Fuentes

Entre paréntesis, la fecha de actualización cuando la página la muestra; † = secundaria, comunitaria o antigua.

1. https://learn.microsoft.com/en-us/minecraft/creator/documents/editoroverview (act. 2026-10-15)
2. https://learn.microsoft.com/en-us/minecraft/creator/documents/editortutorial
3. https://minecraft.net/en-us/creator/tools
4. https://learn.microsoft.com/en-us/minecraft/creator/documents/editorinstallation (act. 2025-10-22)
5. https://learn.microsoft.com/en-us/minecraft/creator/scriptapi/minecraft/server-editor/minecraft-server-editor (pre-release)
6. https://github.com/Mojang/minecraft-editor †
7. https://learn.microsoft.com/en-us/minecraft/creator/documents/mctoolsoverview (act. 2026-05-05)
8. https://learn.microsoft.com/en-us/minecraft/creator/commands/commands/camera
9. https://learn.microsoft.com/en-us/minecraft/creator/documents/commandspopularcommands
10. https://minecraft.wiki/w/Structure_Block
11. https://minecraft.wiki/w/Data_pack
12. https://minecraft.wiki/w/Commands/fill
13. https://minecraft.wiki/w/Commands
14. https://minecraft.wiki/w/Education
15. https://edusupport.minecraft.net/hc/en-us/articles/360047116992-Code-Builder-in-Minecraft-Education
16. https://worldedit.enginehub.org/en/latest/
17. https://worldedit.enginehub.org/en/latest/permissions/
18. https://worldedit.enginehub.org/en/latest/usage/general/history/
19. https://worldedit.enginehub.org/en/latest/usage/clipboard/
20. https://worldedit.enginehub.org/en/latest/usage/tools/brushes/
21. https://axiomdocs.moulberry.com/print.html (docs act. 2025-07-31)
22. https://modrinth.com/mod/axiom
23. https://www.replaymod.com/
24. https://modrinth.com/mod/flashback
25. https://create.roblox.com/docs/en-us/assistant/guide
26. https://create.roblox.com/docs/en-us/studio/mcp.md
27. https://about.roblox.com/newsroom/2026/04/roblox-studio-going-agentic (2026-04-15)
28. https://create.roblox.com/docs/studio/model-tab
29. https://create.roblox.com/docs/studio/packages
30. https://create.roblox.com/docs/en-us/projects/collaboration.md
31. https://create.roblox.com/docs/en-us/studio/testing-modes.md
32. https://create.roblox.com/docs/characters/pathfinding.md
33. https://create.roblox.com/docs/performance-optimization/design.md
34. https://create.roblox.com/docs/en-us/animation/editor
35. https://create.roblox.com/docs/reference/engine/classes/ChangeHistoryService.md
36. https://create.roblox.com/docs/production/publishing/publish-experiences-and-places
37. https://create.roblox.com/docs/en-us/reference/engine/classes/Lighting
38. https://create.roblox.com/docs/get-started/tools.md
39. https://dev.epicgames.com/documentation/fortnite/getting-started-with-devices-in-fortnite
40. https://dev.epicgames.com/documentation/en-us/fortnite/memory-management-in-unreal-editor-for-fortnite
41. https://dev.epicgames.com/documentation/en-us/uefn/publishing-projects-in-unreal-editor-for-fortnite
42. https://dev.epicgames.com/documentation/fortnite/lore-version-control-in-unreal-editor-for-fortnite
43. https://dev.epicgames.com/documentation/en-us/uefn/collaborating-in-unreal-editor-for-fortnite
44. https://dev.epicgames.com/documentation/uefn/getting-started-in-scene-graph-in-fortnite
45. https://dev.epicgames.com/documentation/uefn/create-custom-npc-behavior-in-unreal-editor-for-fortnite
46. https://dev.epicgames.com/documentation/uefn/animation-and-cinematics-in-unreal-editor-for-fortnite
47. https://dev.epicgames.com/documentation/fortnite/using-day-sequence-devices-in-unreal-editor-for-fortnite
48. https://dev.epicgames.com/documentation/en-us/uefn/using-grid-snapping-in-unreal-editor-for-fortnite
49. https://dev.epicgames.com/documentation/fortnite/packed-level-instance
50. https://dev.epicgames.com/documentation/uefn/unreal-editor-for-fortnite-starter-templates
51. https://dev.epicgames.com/documentation/uefn/verse-api/fortnitedotcom/devices
52. https://www.fortnite.com/news/bring-npcs-to-life-with-ai-powered-conversations (2026-04-16)
53. https://dev.epicgames.com/documentation/fortnite/developing-personas-overview-in-unreal-editor-for-fortnite
54. https://en.wikipedia.org/wiki/Unreal_Editor_for_Fortnite †
55. https://community.bistudio.com/wiki/Eden_Editor:_Introduction
56. https://community.bistudio.com/wiki/Eden_Editor:_Actions
57. https://community.bistudio.com/wiki/Eden_Editor:_Layer
58. https://community.bistudio.com/wiki/Eden_Editor:_Composition
59. https://community.bistudio.com/wiki/Eden_Editor:_Trigger
60. https://community.bistudio.com/wiki/Eden_Editor:_Waypoint
61. https://community.bistudio.com/wiki/Eden_Editor:_Setting_Attributes
62. https://community.bistudio.com/wiki/Eden_Editor:_Publishing
63. https://community.bistudio.com/wiki/Curator
64. https://github.com/zen-mod/ZEN
65. https://raw.githubusercontent.com/zen-mod/ZEN/master/docs/user_guide/modules_list.md
66. https://raw.githubusercontent.com/zen-mod/ZEN/master/docs/frameworks/custom_modules.md
67. https://raw.githubusercontent.com/zen-mod/ZEN/master/docs/user_guide/context_actions.md
68. https://github.com/ArmaAchilles/Achilles
69. https://community.bistudio.com/wiki/Arma_Reforger:Game_Master
70. https://community.bistudio.com/wiki/Arma_Reforger:Scenario_Framework
71. https://community.bistudio.com/wiki/Arma_3_Splendid_Camera
72. https://community.bistudio.com/wiki/Arma_Reforger:Workbench
73. https://store.steampowered.com/app/4000/Garrys_Mod/
74. https://wiki.facepunch.com/gmod/Opening_The_Spawnmenu
75. https://github.com/wiremod/advdupe2/wiki/Tool-Explanation
76. https://github.com/wiremod/advdupe2/wiki/Server-settings
77. https://github.com/wiremod/wire/wiki
78. https://github.com/CapsAdmin/pac3
79. https://github.com/CapsAdmin/pac3/wiki/PAC-in-gamemodes
80. https://sbox.game/llms.txt
81. https://sbox.game/dev/doc/editor/mcp-server.md
82. https://sbox.game/dev/doc/editor/undo-system.md
83. https://sbox.game/dev/doc/actiongraph.md
84. https://sbox.game/dev/doc/scene.md
85. https://sbox.game/dev/doc/scene/prefabs.md
86. https://sbox.game/dev/doc/networking/dedicated-servers/user-permissions.md
87. https://sbox.game/dev/doc/networking/testing-multiplayer.md
88. https://sbox.game/dev/doc/editor/mapping.md
89. https://sbox.game/dev/doc/gameplay/navigation.md
90. https://en.wikipedia.org/wiki/S%26box †
91. https://support.halowaypoint.com/hc/en-us/articles/10581874119828-Halo-Infinite-Forge-Overview
92. https://www.halowaypoint.com/news/forge-update-overview-season4 † (Season 4; 2023 según mi conocimiento, la página no muestra año)
93. https://www.halowaypoint.com/en/halo-infinite/forge
94. https://support.halowaypoint.com/hc/en-us/articles/10661655974804-Halo-Infinite-Forge-Known-Issues (2025-08-05)
95. https://www.halopedia.org/HINF:Forge †
96. https://www.halowaypoint.com/news/halo-infinite-forge-fundamentals †
97. https://support.rockstargames.com/articles/4gZPiqdUZD8ZhaJ81IPDJr/how-to-record-clips-and-access-the-rockstar-editor-in-gtav-on-pc
98. https://www.gtabase.com/grand-theft-auto-v/rockstar-editor/ †
99. https://gtaintel.com/news/gta-5-director-mode-rockstar-editor-guide †
100. https://www.pcgamer.com/au/getting-the-best-out-of-gta-vs-rockstar-editor † (2015)
101. https://docs.fivem.net/docs/resources/txAdmin/
102. https://docs.fivem.net/docs/resources/txAdmin/permissions/
103. https://github.com/tabarra/txAdmin
104. https://www.gta5-mods.com/scripts/menyoo-2-0 (v2.4.4, 2026-09-12)
105. https://github-wiki-see.page/m/5mods/tutorials/wiki/Menyoo-%5BObject-Spooner%5DTutorial †
106. https://github.com/citizenfx/fivem
107. https://developer.valvesoftware.com/wiki/L4D2_Director_Scripts †
108. https://wiki.facepunch.com/gmod/gamemodes/Sandbox † ("Updated: A Long Time Ago")