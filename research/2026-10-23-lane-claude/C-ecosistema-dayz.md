# DayZ Sandbox — ecosistema existente, hueco y restricciones duras

Verificado el 2026-10-23 sobre DayZ 1.30 (estable 2026-10-15) [V32]. **[Vn]** = leído en la fuente n (sección 5); **[I]** = inferencia mía; **(>2a)** = fuente de más de 2 años; `scratchpad/src/` = clones de `willy92wins/dayz-mcp` (HEAD f8cf3b4, 2026-10-23) y `willy92wins/DayZ-Modding-Knowledge-Pack`.

## 1. Mapa del ecosistema

| Proyecto | Qué hace | Licencia | ¿Reutilizable/integrable? [I] | Estado |
|---|---|---|---|---|
| **DayZ Editor** [1] + **Dabs** [2] | Editor 3D de objetos; exporta a DZE (+Loader), init.c, VPP, Expansion `.map`, ObjectSpawner.json, eventos. La wiki dice "offline, no funciona en servidor", pero la rama `legacy` trae sincronía multijugador (`…/modules/EditorClientManager.c`, RPC `PLAYER_JOINED`, `EDITOR_CREATE`). Dabs: framework UI | CC BY-NC-ND 4.0 ambos, aunque sus README dicen "open source" [V1][V2] | Solo dependencia y ficheros exportados; no bifurcar ni reempaquetar | HEAD 2026-10-18 / 2026-10-07 |
| **COT** [3] | Admin: cámara cinematográfica (waypoints con FOV, shake, easing, Catmull-Rom; `JMCameraWaypoint.c`; rutas en `$profile:…\CameraPaths.json`, `JMCameraSerialize.c:37`), loadout, objetos, teleport, clima. Rama `dev/1.30`: MapEditor servidor-autoritativo con undo/redo, eventos, roles | CC BY-SA 4.0 [V3] | El más reutilizable: el copyleft admite derivados (atribución y misma licencia) | 2,23 M subs; commits hasta 2026-10-23 |
| **VPP Admin Tools** [4] | Object/Item Manager, clima, teleport, spectate, freecam, editor XML, webhooks, permisos | SARL v1.0: admite "addons independientes" que dependan en runtime; prohíbe copiar código, derivados y monetizar [V4] | Solo dependencia en runtime | 3,82 M subs; 2026-10-13 |
| **Expansion** Quests/Missions [5][7] | Quests JSON (objetivos AI Patrol/Camp/VIP); Missions (airdrops, misiones IA); plantillas de misión por mapa | CC BY-NC-ND 4.0 en cabeceras [V5]; repo de plantillas sin LICENSE [V7] | Dependencia. Misiones poco extensibles: la wiki pospone el tutorial de eventos propios [V5] | v1.9.78 (2026-10-15); plantillas 2026-02-15 |
| **Expansion AI (eAI)** [5][6] | IA humana: facciones (West, East, Raiders, Mercenaries…), 12 formaciones, waypoints (HALT/ONCE/LOOP/ROAMING…), loadouts JSON, menú in-game (T, restringido a SteamIDs de `AISettings.json`) con "Export Patrol", emotes vanilla. API `eAIGroup.c:123,213,251,633`, spawn `eaicommandmanager.c:376-407`. Requiere CF, Dabs y Expansion-Core [V6] | CC BY-NC-ND 4.0; Workshop: "not authorized for posting on Steam, except under the Steam account" [V5][V6] | La mejor base de PNJ humanos; integrar por API, nunca fork | 984 k subs; v1.9.78, grafo IA 1.30 |
| **AI Bandits** [8] | IA sobre la simulación de infectados (más barata): patrullas, francotiradores, estáticos con emotes | Workshop: "No repacks allowed"; no hallé licencia formal [V8] | Alternativa ligera a eAI | 62 k subs; "far from complete" |
| **DayZ Studio** [9] | IDE de escritorio para servidores vanilla: mapa, quests, grafos de comportamiento de NPC; importa .dze/.map/init.c; exporta PBO firmado; extrae terreno del juego del usuario | EULA propietaria: uso personal no comercial [V9] | Solo referencia de diseño | alpha.7, 2026-10-22 |
| **dayz-ai-survivor** [10], **cortexlink** [11], **BZ_AutoDrive**/**TACLEX** [12] | NPC con LLM (≤10) sobre eAI vía demonio Python + MCP + puente JSON; IPC en `$profile:` a 1 Hz; vehículos autónomos con DSL de escenarios; misiones dinámicas por chat | MIT [V10][V12]; cortexlink sin LICENSE [V11] | Patrones y código MIT reutilizables | 2026-10 (cortexlink: 2026-04) |
| **CFTools Cloud + GameLabs** [16]; **Architect** [17] | SaaS: mapa en vivo, logs, control de personaje, spawn de ítems; intervalos de 60 s (gratis) a 5 s (pago), mapa en vivo solo de pago. Architect (Manager+Agent+Toolbox) sustituye a OmegaManager, deprecado [V17] | Cerrado; GameLabs "© CFTools", uso comercial prohibido por el EULA de Tools [V16] | Solo vía Data API (exige ≥ Basic) | activo |
| **dayz-server-manager** [18] | App TS autoalojada: SteamCMD, RCon, Discord, REST + UI web, mapa Leaflet con jugadores; exige máquina con control total | MIT [V18] | Reutilizable, pero casi abandonado | último código 2025-02-26 |
| **BE RCon / BattleMetrics** [19][20] | UDP: players, kick, bans, say; BM añade triggers y scheduler (10 $/mes tras 7 días) | Protocolo público (2011, >2a); BM SaaS | Solo moderación | estable |
| **iZurvive/Ginfo**, **xam.nu** [21] | Mapas Leaflet (Chernarus+, Livonia, Nasdara, Sakhal, 25 mapas Workshop); xam.nu: mapas 1.30 con niveles de loot | "© Bohemia Interactive" en atribuciones; sin permiso de reuso [V21] | No reusar teselas; sin API ni embed | activo |
| **BI: Central-Economy, Samples, Misc** [25] | Plantillas CE (`chernarusplus`, `enoch`, `nasdara`, `sakhal`), ejemplos, FBX | ADPL-SA [V25] | Con share-alike y sin uso comercial | oficial |
| **dayz-mcp** (propio) [14] | 88 tools MCP, servidor-autoritativo: `world_spawn`, `camera_set`, `bot_start` | MIT [V14] | Capa IA opcional | v1.4 en 1.30 |

- **Zeus/Game Master:** mis búsquedas web y de GitHub no hallaron equivalente en DayZ (solo salió Arma 3/Reforger). Lo más cercano: MapEditor de COT, Editor multijugador, menú IA de Expansion y DayZ Studio [I].
- **Eventos:** vanilla = Central Economy (`events.xml`, ambient spawner) [V15 wiki-systems:50-52]; Expansion Missions añade airdrops y misiones IA [V5].
- **Mapas:** oficiales Chernarus+, Livonia (gratis desde 1.25, mayo 2024, >2a [V33]), Sakhal (DLC Frostline), Nasdara (DLC Badlands) [V21][V31]; comunitarios: Namalsk, Deer Isle, Chiemsee, Rostow, Esseker, Takistan Plus, Banov, Iztek, Valning… [V21]. Plantillas de Expansion: Chernarus, Enoch, Namalsk, Chiemsee, Takistan Plus; "incompletas" (su README): Banov, Deer Isle, Esseker, Iztek, Rostow, Valning; ninguna para Sakhal ni Nasdara [V7].

## 2. Hueco que queda para DayZ Sandbox (todo [I])

1. **Escenario como documento único.** Nada une mapa + hora/clima + posiciones + reparto de jugadores + infectados/animales + IA humana con equipo y acciones, ni lo carga/descarga en un servidor vivo. Hoy está fragmentado: diseño (Editor, COT, VPP), IA (JSON de eAI), misiones (Expansion), equipo (COT, `cfgGameplay.json` [V15 wiki-systems:112-115]). DayZ Studio es lo más cercano, pero es de escritorio, alpha, solo vanilla y propietario [V9].
2. **Puente web↔juego.** RCon solo modera: lista cerrada de comandos [V19][V20]. CFTools reconoce que "DayZ does not offer a stable way of pushing data live" [V16]; dayz-server-manager está parado [V18]. Hace falta un mod servidor propio y un canal: RestApi asíncrono (dayz-mcp, solo loopback) o JSON en `$profile:` (cortexlink lo defiende por fiabilidad) [V11][V14 README:124].
3. **Acciones/animaciones de PNJ como línea de tiempo.** eAI ofrece waypoints, formaciones y emotes vanilla (estado FSM `…/FSM/states/eaistate_playemote.c:1-16`; `EmoteConstants` en `eAIBase.c:2892-2907`) [V5], pero ningún editor de "en t=12 s haz X"; DayZ Studio lo intenta con grafos a 1 Hz y 19 emotes vanilla (afirmación del autor) [V9]. El límite de un solo mod de animación obliga a emotes/acciones vanilla (T1).
4. **Reparto y reinicio.** Preconfigurar jugadores por "slot" (equipo, posición, estado) y volver al punto de partida: piezas sueltas (COT Loadout, Expansion), sin snapshot ni reset de mundo.
5. **Herramientas de creador.** La cámara de COT es lo más avanzado [V3]; en el Editor, el gestor de pistas de cámara está comentado (`DayZEditor/Scripts/4_World/DayZEditor/modules/EditorCameraTrackManager.c:33-157`) [V1]. No hay cámara + acciones de IA + disparo de grabación sincronizados, y la captura nativa es imposible (T3).
6. **Capa IA/MCP.** Hay precedentes (dayz-ai-survivor, cortexlink, plan "AI Game Master" de dayz-mcp: el LLM propone JSON y un validador determinista ejecuta, `plans/2026-06-30-ai-game-master-proposal.md:75`) [V10][V11][V14]; falta un esquema de escena contra el que apunte el LLM. Expansion Quests no tiene API server-side limpia (`…proposal.md:599`): integrar vía JSON de quests, no vía API.
7. **Multimapa.** Ninguna herramienta cambia de mapa en caliente (T4); el editor web necesita metadatos por mapa y una vía legal para teselas (L5).
8. **Estrategia.** Orquestar, no reimplementar: Sandbox como capa de escenario sobre eAI, exportaciones del Editor y cámara de COT, con mod servidor propio.

## 3. Restricciones duras

**Técnicas**
- **T1 — Un solo mod de animación.** "Due to a limitation with DayZ, only ONE animation mod can be loaded at the same time" [V6]; dos mods provocan crash cliente/servidor (límite del motor) [V15 capacidades:147-148]. Expansion-Animations sustituye el grafo de `SurvivorBase` (`DayZExpansion/Dta/Animations/config.cpp:17-25`); eAI usa un grafo propio por clase `eAI_SurvivorM_*` (`DayZExpansion/AI/Animations/config.cpp:50-56`) y avisa de "AI stuck in specific poses" si el grafo es ajeno (`…/3_Game/DayZExpansion_AI/DayZGame.c:81-82`) [V5]. **[I]** Sandbox no debe sustituir el grafo global; solo emotes/acciones vanilla o clases de entidad propias.
- **T2 — RCon no muta el mundo [I].** Comandos BE: players, kick, bans, say… [V19]; BattleMetrics: chat, kick, bans, shutdown, reload scripts/events, max ping, raw [V20]. Protocolo: UDP, paquete "BE"+CRC32, login 0x00 / comando 0x01 / mensaje de servidor 0x02, keep-alive ≤45 s, respuestas multiparte (spec 2011, >2a) [V19]. Hace falta mod servidor.
- **T3 — Sin framebuffer ni DLL.** Sin lectura del framebuffer ni `CallExtension`; `MakeScreenshot` no hace nada [V15 capacidades:14-21][V14 README:122]; `SetTimeMultiplier(0)` congela toda la simulación [V14 README:126]; en el banco de pruebas de dayz-mcp la cámara libre también detiene la simulación [V15 bridge-protocol:110-112].
- **T4 — Un proceso, un mapa.** `template = "<Misión>.<Terreno>"` en `class Missions` [V27]; cambiar de mapa exige cambiar plantilla y reiniciar [V28]; un mapa Workshop requiere suscribir el mod y copiar la carpeta a `mpmissions` [V29]. **[I]** el cliente necesita el mod (`-mod=` va a cliente y servidor [V15 wiki-systems:85]). DLC: "Players need the Frostline DLC to join a Sakhal server" [V28], frente a un hilo de Steam que dice que pueden entrar pero no jugar Sakhal [V30, ≈2a].
- **T5 — Cambios de 1.30.** Navmesh nuevo sin compatibilidad hacia atrás (los terrenos deben regenerarlo), compilador más estricto, `OnCEUpdate` obsoleto [V32, secundarias]. El grafo IA de 1.30 no funciona en 1.29 (`DayZGame.c:92-93`); `bot_start` está especificado para devolver `bot_unavailable` en 1.29, sin prueba ejecutada (`SPEC_B.md:142`, `ingame-v11/RESULTS.md:31`) [V14].
- **T6 — Presupuesto de IA.** Expansion pide FPS de servidor máx. >60 y medio >35; un coste >0,5 ms por IA indica el techo; sin Frame Time Optimization hay degradación con >30 IA; las patrullas se descargan según jugadores (`LoadBalancingCategories`) [V5: wiki AI-Performance-Tuning y AI-Load-Balancing].
- **T7 — El bot vanilla de 1.30 es de depuración** (`ROBOCLIENT`); "whether a synthetic survivor population is viable is open" [V14 README:143].
- **T8 — dayz-mcp:** solo Windows, escucha en 127.0.0.1, sin modo remoto, clave en `?key=` [V14 README:124,418].

**Legales**
- **L1 — Tools EULA.** "You may use the software and the content you create using the software for non-commercial purposes only"; sin redistribución; uso comercial con permiso de BI [V23]. Las reglas de contenido permiten herramientas/plug-ins originales, comerciales o no, que no usen contenido/IP de BI [V22]. **[I]** backend y UI web separables y potencialmente comerciales; el PBO del mod, no comercial.
- **L2 — Monetización.** Solo servidores privados; cuotas de acceso si lo extra no afecta a la jugabilidad; permiso revocable que "will expire on January 31st 2027"; usar mods ajenos exige permiso de todos los autores; contenido bajo licencias de datos de BI sin paywall [V26]; donaciones permitidas sin condicionar acceso [V22][V26].
- **L3 — Licencias de dependencias.** CC BY-NC-ND (Expansion, Editor, Dabs): sin uso comercial ni redistribución modificada; COT CC BY-SA; VPP SARL (solo addons independientes, sin copiar código); AI Bandits "no repacks"; DayZ Studio propietaria [V1][V2][V3][V4][V5][V8][V9]. eAI declara estar "Partly based on Enfusion AI Project Copyright 2021 William Bowers" (`eAIBase.c:4`) [V5]. Hay que depender vía Workshop, nunca reempaquetar.
- **L4 — ADPL-SA.** Muestras y plantillas CE de BI: no comercial, solo Arma/DayZ, share-alike [V25]; **[I]** mezclarlas obliga a licenciar Sandbox igual.
- **L5 — Teselas de mapa.** "Do not redistribute our games or any files extracted from it" [V22]; iZurvive/Ginfo atribuye a Bohemia y no declara permiso de reuso [V21]; DayZ Studio extrae localmente y "distributes zero proprietary game files" [V9]; DayZ puede generar un mapa 2D desde el terreno [V27]. **[I]** diseño seguro: generar teselas en la máquina de cada usuario, sin alojarlas.
- **L6 — EULA de DayZ.** Prohíbe "hack, modify or reverse engineer the game or any game files, its data or network services"; el contenido de usuario da a BI permiso irrevocable [V24]. La nota local advierte que RTM es ingeniería inversa según aviso de BI [V15 capacidades:149-150]: evitar crear animaciones propias por esa vía.

## 4. Dudas abiertas

1. ¿Es lícito `modded class` sobre mods CC BY-NC-ND (Expansion, Editor, Dabs)? Las licencias no lo aclaran (VPP sí lo permite expresamente [V4]); pedir permiso por escrito.
2. ¿El multijugador del Editor (rama `legacy`) está en la versión Workshop y funciona en dedicado? La wiki dice offline [V1]; el código sugiere lo contrario.
3. ¿Hay que poseer el DLC para servir/jugar Sakhal y Nasdara? Fuentes en conflicto [V28][V30]; la FAQ de Badlands no lo dice [V31]; el hilo oficial forums.dayz.com/topic/264091 no se pudo abrir.
4. Cambio de mapa sin reinicio y descarga automática del mapa Workshop por el cliente: sin fuente; supongo imposible y obligatoria [I].
5. Teselas propias: BI no tiene cláusula explícita sobre mapas derivados [V23]; pedir aclaración. Tampoco analicé el texto de DPL/DPL-ND [V25] ni hallé regla específica de BI sobre mods de pago en Workshop, solo la FAQ de monetización [V26].
6. ¿Se renovará el permiso de monetización tras 2027-01-31? [V26]
7. Estado 1.30 de mapas comunitarios: Namalsk exportado el 15–16 oct [V32]; Deer Isle sin entrada 1.30 (última actualización 2025-06). Las páginas Workshop mostraban un banner "removed/incompatible" en todos los ítems; lo traté como artefacto del fetcher.
8. Licencias sin verificar: Community Offline Mode [13], cortexlink [V11] y plantillas Expansion Missions [V7] (sin LICENSE). GameLabs menciona un "Open GameLabs compatible API server" sin especificación pública [V16]. Términos de xam.nu y API de BattleMetrics: no revisados (presupuesto de búsqueda agotado).
9. Sin cifras propias de rendimiento eAI en 1.30 ni pruebas multiusuario.

## 5. Fuentes

[1] https://github.com/InclementDab/DayZ-Editor (rama `legacy`; `license.md`; wiki `/wiki`; Workshop https://steamcommunity.com/sharedfiles/filedetails/?id=2250764298)
[2] https://github.com/InclementDab/DayZ-Dabs-Framework (`LICENSE.md`)
[3] https://github.com/Jacob-Mango/DayZ-CommunityOnlineTools (rama `dev/1.30`); Workshop https://steamcommunity.com/sharedfiles/filedetails/?id=1564026768
[4] https://github.com/VanillaPlusPlus/VPP-Admin-Tools (`LICENSE`); Workshop https://steamcommunity.com/sharedfiles/filedetails/?id=1828439124
[5] https://github.com/salutesh/DayZ-Expansion-Scripts (rama `experimental`) y wiki https://github.com/salutesh/DayZ-Expansion-Scripts/wiki
[6] Workshop Expansion-AI https://steamcommunity.com/sharedfiles/filedetails/?id=2792982069; Expansion-Animations https://steamcommunity.com/sharedfiles/filedetails/?id=2793893086
[7] https://github.com/ExpansionModTeam/DayZ-Expansion-Missions (`README_TRADERS.txt`, `Template/`, `Template/0_INCOMPLETE/README.txt`)
[8] https://steamcommunity.com/sharedfiles/filedetails/?id=3628006769
[9] https://github.com/ghosthex-dev/dayz-studio
[10] https://github.com/Isualc/dayz-ai-survivor
[11] https://github.com/CloudJMK/cortexlink
[12] https://github.com/sonom4n/BZ_AutoDrive; https://github.com/TreeoM-ManhheiM/TACLEX_DAYZ
[13] https://github.com/Arkensor/DayZCommunityOfflineMode
[14] local: `scratchpad/src/dayz-mcp/README.md`, `…/plans/2026-06-30-ai-game-master-proposal.md`, `…/reviews/2026-10-06-ticketing/specs/SPEC_B.md`, `…/reviews/2026-10-06-ticketing/ingame-v11/RESULTS.md`
[15] local, bajo `scratchpad/src/DayZ-Modding-Knowledge-Pack/knowledge/`: `dayz-mcp-bridge-protocol.md` ("bridge-protocol"), `vault-notes/dayz-capacidades-verificadas.md` ("capacidades"), `vault-notes/dayz-wiki-systems-reference.md` ("wiki-systems")
[16] https://cftools.com/help/platform/day-z; https://cftools.com/help/platform/game-integration; https://cftools.com/help/api-services/data-api; GameLabs https://steamcommunity.com/sharedfiles/filedetails/?id=2464526692
[17] https://cftools.com/help/architect/omega-manager; https://help.cftools.com/en/omega-manager/configuration-and-workflows; https://cftools.com/help/architect/getting
[18] https://github.com/mr-guard/dayz-server-manager
[19] https://www.battleye.com/downloads/BERConProtocol.txt; https://www.battleye.com/support/documentation/
[20] https://www.battlemetrics.com/rcon/dayz
[21] https://dayz.ginfo.gg/attributions; https://www.izurvive.com/attributions/; https://dayz.xam.nu/
[22] https://www.bohemia.net/en/community/game-content-usage-rules
[23] https://store.steampowered.com/eula/830640_eula_0; https://www.bohemia.net/community/licenses/bohemia-interactives-tools-end-user-license
[24] https://www.bohemia.net/en/licenses/dayz-end-user-license
[25] https://www.bohemia.net/community/licenses; https://github.com/BohemiaInteractive/DayZ-Central-Economy (+ DayZ-Samples, DayZ-Misc)
[26] https://portal.bohemia.net/monetization; https://www.bohemia.net/monetization/faq; https://www.bohemia.net/monetization/approved/dayz
[27] https://community.bistudio.com/wiki/DayZ:Server_Configuration; https://community.bistudio.com/wiki/DayZ:Configuring_2D_Map
[28] https://my.logicservers.com/knowledgebase/775/How-to-enable-Frostline-Sakhal-on-your-DayZ-server.html (hosting, secundaria)
[29] https://ggservers.com/knowledgebase/article/dayz-server-how-to-install-a-custom-map/ (hosting, secundaria)
[30] https://steamcommunity.com/app/221100/discussions/0/4694531693358393496/ (oct. 2024, ≈2a)
[31] https://forums.dayz.com/topic/266372-dayz-badlands-expansion-faq/
[32] https://patchbot.io/games/dayz/articles/1794-update-130; https://www.bisecthosting.com/es-es/blog/dayz-1-30-update-patch-notes-badlands-expansion-new-motorbikes-survival-mechanics-full-changelog; https://space-node.net/blog/dayz-1-30-mods-not-working-server-fix-2026 (todas secundarias)
[33] https://www.thesixthaxis.com/2024/05/28/dayz-update-1-25-live-as-major-dlc-goes-free/ (>2a)

Los repos externos se leyeron en clones temporales de solo lectura (no publicados).