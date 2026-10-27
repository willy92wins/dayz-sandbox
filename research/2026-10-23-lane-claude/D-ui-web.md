# UI web para DayZ Sandbox: patrones y piezas (informe 2026-10-23)

**Cómo leer.** `[V n]` = leído en la fuente n (§5); cada fila remite a sus fuentes. `[I]` = inferencia mía (columnas «Copiar» y §3 incluidas). `[N]` = registro npm (versión, fecha, licencia, publicaciones en 12 m incl. prereleases; `registry.npmjs.org/<paquete>`, consultado hoy); estrellas de las páginas GitHub citadas. ⚠ = más de 2 años. s/f = sin fecha visible.

**Conclusiones**
- Los editores de escena revisados convergen en árbol + inspector + vista central + biblioteca; lo personalizable se guarda como JSON [I].
- Lo más reutilizable: un vocabulario único de *acciones declaradas como datos* para botones, triggers, timeline y paleta (Companion [V 32], presets de Unreal [V 4], eggs [V 21]).
- Con polling la UI no debe prometer tiempo real: CFTools dice que «DayZ no ofrece forma estable de empujar datos en vivo» (trad.) y sincroniza cada 5-10 s [V 26].
- Trampas de licencia: Theatre Studio (AGPL), funciones de pago aparte en Dockview desde 2026-08, atribución de React Flow, Foxglove ya no es abierto.

## 1. Precedentes

| Precedente | Patrón UX (hechos) | Copiar [I] | Fuentes |
|---|---|---|---|
| **Unreal Remote Control + Web App** (Beta en docs UE 5.8; su web app pide Node 8–14.15.5) | El backend publica un *preset* de propiedades/funciones y la web crea widgets enlazados (Button, Toggle, Slider, Dropdown, Label, Panel, Tabs, Vector…); modo diseño; layouts guardados con el preset; varios clientes sincronizados; WS JSON con `preset.register` y eventos `PresetFieldsChanged` | UI generada desde esquema; pocos widgets; suscripción por recurso | V 1-4 |
| **Foundry VTT** (EULA propietaria; v14.369, 2026-10-08) | Escena = fondo + rejilla + placeables, con directorio y barra de marcadores; *Activar* (lleva a todos) vs *Ver* (solo yo); Actor con *prototype token* → Token colocado = copia independiente; hotbar por usuario (10 huecos × 5 páginas); roles y permisos por rol y documento; módulos con `module.json` (esmodules, languages, relationships, compatibility); teclas reasignables con aviso de conflicto | Borrador vs aplicado; plantilla→instancia; hotbar; manifest; keymap | V 5-13 |
| **Owlbear Rodeo** (SDK MIT, 3.1.0 en 2024-12 [N]; app no verificada) | Extensiones = iframes + `manifest.json` mínimo (name, version, manifest_version, description, action, background_url, permissions con `reason`); se instalan pegando la URL; superficies: action/popover, tool, context menu | Extensión aislada y barata | V 14-16 |
| **txAdmin** (MIT; v8.1.1, 5 jun, año no visible) | Consola en vivo con búsqueda e historial, gestor de jugadores, reinicios programados con aviso, *recipes* de despliegue, menú in-game, permisos de admin, modo oscuro | Permisos por acción; scheduler; recetas = escenarios importables | V 17-18 |
| **Pterodactyl, Pelican, AMP** (MIT, v1.15.1 y 2.0 beta / AGPL-3.0, 2,4k★ / comercial según V 25) | Pterodactyl *egg*: variables con reglas de validación y permisos «Users Can View/Edit» → formulario autogenerado. AMP: plantillas comunitarias (repo MIT; `.kvp` + `config.json`) con *Settings Manifest*; temas = CSS sobre el por defecto | Entidades y acciones como datos validados; tema = CSS; repo comunitario de plantillas | V 19-25 |
| **CFTools / DZ Commander** (SaaS DayZ) | CFTools: plugin en servidor, lotes cada 5 s, mapa cada 10 s. DZ Commander: el mod sondea una cola de comandos (solo HTTPS saliente); estados creado→enviado→confirmado; kits, ubicaciones guardadas, roles Viewer…Superadmin con nivel mínimo por comando, confirmación de acciones destructivas, auditoría, tokens con ámbito | Cola visible, kits, roles + confirmación, auditoría, «edad del dato» | V 26-28 |
| **Bitfocus Companion** (MIT + CLA; v5.0.5) | Cuadrícula de botones por páginas; Triggers = Eventos + Condición + Acciones, y toda acción de botón vale en un trigger; Web buttons para tablet con ajustes en la URL; v5.0 desactiva por defecto shell e instalación de módulos por red | Vocabulario único de acciones; botón con feedback; superficie por URL | V 29-33 |
| **Stream Deck / Touch Portal** | SDK Stream Deck 3.0.3 (MIT, 2026-10-19 [N]): Node/TS, `manifest.json`, *property inspector* HTML. Touch Portal API 13.0: acciones, eventos, estados, sliders y ajustes declarados en un archivo | Acciones con campos tipados + estados publicados; dispararlas por HTTP (Companion trae módulo Generic HTTP, MIT [V 34]) | V 34-36 |
| **OBS** (obs-websocket GPL-2.0, integrado desde OBS 28) | Docks = páginas web en la interfaz; Browser Source con fondo transparente por CSS y `window.obsstudio` con niveles de permiso; protocolo 5.x: op-codes, suscripción por máscara de bits, lotes con `haltOnFailure`, negociación de `rpcVersion` | `/surface` como dock, `/overlay` transparente; protocolo versionado con lotes | V 37-40 |
| **three.js editor, PlayCanvas, Babylon** | three.js 0.186 (MIT, 2026-09 [N]): outliner + viewport + inspector; comandos `execute/undo/update/toJSON/fromJSON`, historial que fusiona ediciones <500 ms. PlayCanvas Editor (MIT, 1,3k★; solo el front-end, que se prueba cargándolo en el editor alojado): Hierarchy/Inspector/Viewport/Assets, presencia (avatares, selección, cámaras), Observer para *binding e historial*, Editor API Beta. Babylon: Inspector que se engancha a una escena viva (explorador + property grid, popout, propiedades custom); su Editor es de escritorio (Apache-2.0, v5.5.0); core 9.32 en 2026-10 [N] | Pila de comandos; presencia; inspector sobre datos vivos | V 41-48 |
| **Foxglove, Home Assistant** | Foxglove (código cerrado desde 2024-03 ⚠): layouts personales vs de organización, export/import JSON, extensiones con `activate()`. HA: tarjeta = custom element con `setConfig`, registro `window.customCards`, formulario de edición automático | Layouts compartidos; widget = componente + config JSON | V 49-53 |

## 2. Librerías

| Pieza (versión · fecha) | Función | Licencia | Madurez | Encaje |
|---|---|---|---|---|
| **Dockview** 8.6.1 · 2026-10-19 | Docking: grupos flotantes, popout, `toJSON`, anuncios ARIA [V 66-70] | MIT; `dockview-enterprise` comercial desde 2026-08-07 (teclado-docking, historial de layout) | 3,5k★; 66 publ./12 m | Alto, solo núcleo |
| **FlexLayout** 0.11.1 · 2026-09-26 | Docking solo React; popout, `Model.toJson`, `doAction`, ARIA (tabs, splitters), `keyMap`, `i18nMapper` [V 71, 99] | MIT | 1,4k★; 16 publ./12 m | Alto; alternativa 100 % MIT |
| react-mosaic 7.2.1 | Tiling N-ario con tabs [V 72] | Apache-2.0 | 4,8k★ | Medio (flotantes sin verificar) |
| GoldenLayout 2.6.0 · 2022-09 ⚠ | Docking multiventana [V 73] | MIT | rama `dev` inestable | Descartar |
| react-resizable-panels 4.14.8 | Splits con `defaultLayout` persistible [V 74] | MIT | 5,4k★; 98 publ. | Plan mínimo |
| react-grid-layout 2.3.0 · gridstack 14.0.0 | Rejilla de widgets serializable [V 75-76] | MIT · MIT | 22,4k★ · 9,1k★ | Solo si tamaño libre |
| React Aria Components 1.22.1 | Primitivas accesibles; Autocomplete para paletas [V 92] | Apache-2.0 | 241 publ./12 m | Alto |
| cmdk 1.1.1 · kbar 1.0.0 | Paleta Ctrl+K; kbar añade atajos y anidación [V 87-88] | MIT · MIT | 13k★, sin release desde 2025-03 · 5,3k★ | Alternativa a React Aria |
| tinykeys 4.0.1 | Atajos y secuencias, ~1 KB [V 89] | MIT | 4,1k★ | Alto |
| Immer 11.2.9 | Parches con inverso para undo/sync [V 90] | MIT | 29k★ | Opcional |
| Yjs 13.6.33 | CRDT, awareness, UndoManager [V 91]; alternativas Automerge 3.5.0, Loro 1.17.1 [N] | MIT | 22,3k★; v14 en beta; y-indexeddb 2023-11 ⚠ | Después |
| @xyflow/react 12.12.0 | Editor de nodos [V 77-78] | MIT; atribución (quitarla exige Pro, desde 169 USD/mes) | 38k★ | Después |
| Rete 2.0.6 · 2025-06 | Nodos + motores dataflow/control [V 79] | MIT | 12,2k★ | Alternativa |
| LiteGraph 0.7.18 · 2024-01 ⚠ | Nodos en canvas [V 80-81] | MIT | fork de Comfy archivado | Evitar |
| Blockly 13.4.0 | Bloques visuales; solo teclado y lector de pantalla [V 82] | Apache-2.0 | 13,6k★; 24 publ. | Después (creadores) |
| Theatre.js 0.7.2 · 2024-05 ⚠ | Secuenciador/keyframes [V 83] | core Apache-2.0; **Studio AGPL-3.0** | 12,8k★; desarrollo movido a repo privado | Evitar |
| animation-timeline-js 2.3.5 · 2024-07 ⚠ | Timeline en canvas [V 84] | MIT | 470★ | Dudoso |
| react-timeline-editor 1.0.0 · 2026-01 | Timeline React [V 85] | MIT | 787★; 79 commits | Posible |
| vis-timeline 8.5.4 | Ítems editables en el tiempo [V 86] | Apache-2.0 OR MIT | 2,6k★ | Válida para carriles |
| react-arborist 4.0.1 · headless-tree 1.8.0 | Outliner virtualizado, DnD, teclado, ARIA [V 93-94] | MIT · MIT | 3,7k★ · 895★ | Alto |
| rjsf 6.11.0 · JSON Forms 3.8.0 | Formularios desde JSON Schema [V 95] | Apache-2.0 · MIT | activas | Opcional |
| i18next 26.5.7 | i18n | MIT | 77 publ./12 m | i18next o diccionario |
| **OpenLayers** 10.11.0 · 2026-10-04 | Mapa; proyección en píxeles, Select/Modify, WebGL [V 57-60] | BSD-2 | 12,6k★ | Alto |
| Leaflet 1.9.4 · 2023-05 ⚠ + Geoman 2.20.4 + rastercoords | Mapa `CRS.Simple` con `[y,x]` [V 54-56, 63-64] | BSD-2 · MIT · MIT | 45,7k★; 2.0.0-alpha.1 (2025-08) sin estable; Geoman fija Leaflet ^1.2 [N] | Alternativa simple |
| deck.gl 9.4.0 | WebGL; `OrthographicView` con `flipY:false` [V 61-62] | MIT | 14,6k★ | Solo densidad/heatmaps |

## 3. Recomendación [I]

**Layout por defecto** (docking, una pantalla):
- **Barra superior**: escenario ▾ · modo **Borrador / En vivo** (patrón Ver/Activar [V 5]) · **Aplicar al juego** · deshacer/rehacer · enlace («último latido hace N s») · Ctrl+K.
- **Izquierda**: Outliner (árbol por facción/tipo; buscar, ocultar, bloquear) y Biblioteca de plantillas (jugador, zombi, animal, IA, loadouts).
- **Centro**: Mapa con herramientas (seleccionar, colocar, ruta, zona, medir), coordenadas X/Z copiables (como otros mapas DayZ [V 65]), entidades pendientes como «fantasma» hasta confirmar y HUD contextual sobre la entidad (patrón Token HUD [V 7]).
- **Derecha**: Inspector (formulario desde esquema: equipo, comportamiento, animación) y Acciones (paleta buscable con favoritos).
- **Abajo**: Secuencia (pasos con disparador = evento + condición, como Companion [V 32]) · Cola de comandos · Registro. **Botonera** como pestaña o ventana flotante.

**Personalización** (todo JSON versionado, importable/exportable):
1. **Layouts**: `toJSON()` + `onDidLayoutChange` de Dockview [V 70] por usuario; nombrados, personales o compartidos [V 49]; popout del mapa a otro monitor [V 67]; de fábrica: Director, Moderador, Streamer/táctil.
2. **Perfiles por rol**: rol = layout por defecto + paneles visibles + acciones permitidas (nivel mínimo por acción) + teclas + tema. Niveles, confirmación de acciones destructivas y auditoría como DZ Commander [V 27-28].
3. **Superficie de control**: cuadrícula fija filas × columnas por página (como Companion), ≤8 tipos de widget (los de Unreal [V 3]); widget = acción + parámetros + feedback ligado a estado. Servida en `/surface/:id?token=…` sin cromo (tablet [V 33], dock de OBS [V 37]) y `/overlay/:id` transparente [V 40]; token de ámbito limitado [V 27]; mismas acciones por HTTP para Companion/Stream Deck [V 34].
4. **Teclas**: mapa JSON por usuario con aviso de conflictos [V 13].
5. **Temas**: tokens CSS y «tema = archivo CSS sobre el por defecto» [V 24]; claro, oscuro, alto contraste.
6. **Extensiones por fases**: F0 solo JSON importable (plantillas, botoneras, layouts, escenarios); F1 módulo ES + manifest mínimo (id, versión, compatibilidad, permisos con motivo) que registra acciones, paneles y widgets [V 10, 15]; F2 iframes aislados para terceros [V 14]. Widget = componente con `setConfig` + estado [V 53].

**Stack mínimo**: TypeScript + React + Vite; backend con esquemas versionados de entidades y acciones (`/schema`) · Zustand con pila de comandos propia (patrón three.js [V 47-48]; cada comando con su inverso, irreversibles marcados) · Dockview (solo núcleo MIT) tras un `LayoutService` propio, para poder cambiar a FlexLayout · OpenLayers con proyección en píxeles [V 57], Select/Modify [V 59] y `WebGLVectorLayer` si hay miles de entidades [V 58] · react-arborist · React Aria Components (diálogos, menús, tabs, paleta con Autocomplete [V 92]) · tinykeys · mapeador propio esquema→controles · diccionarios JSON es/en + `Intl` · transporte: SSE servidor→navegador + `fetch` POST, snapshot inicial + eventos, un stream por pestaña (HTTP/1.1 limita a 6 conexiones por dominio [V 98]); WebSocket solo si hace falta petición/respuesta (diseño obs-websocket [V 39]).

**MVP**: mapa en vivo con edad del dato; colocar/mover/borrar desde plantillas; inspector; cola de comandos con estados y undo compensatorio; paleta + Ctrl+K; layouts guardables y 2-3 roles; botonera y URL de superficie; export/import de escenarios; auditoría; es/en; accesibilidad básica (árbol según APG [V 97], alternativa a arrastrar por WCAG 2.5.7 AA [V 96]).
**Después**: editor de nodos (React Flow; Rete), CRDT, carriles de keyframes, marketplace/sandbox de extensiones, heatmaps (plan alto de DZ Commander [V 27]), obs-websocket, viewport 3D.
**Alternativas**: (a) más simple: react-resizable-panels con presets fijos, sin docking; (b) FlexLayout si prefieren 100 % MIT sin tier comercial; (c) Leaflet 1.9.4 + Geoman si prefieren API más simple y aceptan quedarse en 1.x.

## 4. Dudas abiertas
1. **Licencia de DayZ Sandbox**: condiciona AGPL (Theatre Studio, Pelican), Dockview Enterprise y la atribución de React Flow.
2. **Usuarios y concurrencia**: ¿un director o varios editores a la vez? Servidor autoritativo + presencia basta salvo edición concurrente.
3. **Cadencia y volumen**: intervalo real de polling y nº de entidades (CFTools cifra 5-10 s [V 26]; no lo medí). Decide canvas vs WebGL.
4. **Mapa**: origen y permisos de las teselas (otros usan iZurvive [V 65]; licencia no verificada) y si (0,0) es la esquina SO.
5. **Undo en vivo**: acciones irreversibles (matar, loot recogido): ¿compensar o avisar?
6. **Accesibilidad**: mover/acoplar paneles por teclado no está en la versión libre de ninguna (Dockview: solo Enterprise [V 68]; FlexLayout: no documentado [V 99]) → comandos de paleta «Mover panel a…» sobre la API del layout [I]; el mapa es visual: lista equivalente.
7. **Seguridad**: tokens en URLs y extensiones de terceros (Companion 5.0 apagó por defecto shell e instalación por red [V 30]).
8. **No verificado**: Zeus de Arma 3 (página BI inaccesible), docs de txAdmin, feedbacks de Companion, licencia de obs-browser y de las apps de Stream Deck/Touch Portal. Sin API de GitHub: no leí fechas de commits; uso publicaciones npm [N] como proxy de actividad.

## 5. Fuentes
`[N]` https://registry.npmjs.org/<paquete>. Todas consultadas 2026-10-23; docs s/f salvo indicación.
1 https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-for-unreal-engine
2 https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-api-websocket-reference-for-unreal-engine
3 https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-web-application-for-unreal-engine
4 https://dev.epicgames.com/documentation/en-us/unreal-engine/remote-control-presets-and-web-application-for-unreal-engine
5 https://foundryvtt.com/article/scenes/
6 https://foundryvtt.com/article/actors/
7 https://foundryvtt.com/article/tokens/
8 https://foundryvtt.com/article/macros/
9 https://foundryvtt.com/article/users/
10 https://foundryvtt.com/article/module-development/
11 https://foundryvtt.com/article/license/
12 https://foundryvtt.com/releases/
13 https://foundryvtt.com/article/keybinds/
14 https://docs.owlbear.rodeo/extensions/getting-started
15 https://docs.owlbear.rodeo/extensions/reference/manifest
16 https://github.com/owlbear-rodeo/sdk
17 https://github.com/citizenfx/txAdmin
18 https://github.com/citizenfx/txAdmin/releases
19 https://github.com/pterodactyl/panel
20 https://github.com/pterodactyl/panel/releases
21 https://pterodactyl.io/community/config/eggs/creating_a_custom_egg.html
22 https://github.com/pelican-dev/panel
23 https://github.com/CubeCoders/AMPTemplates
24 https://github.com/CubeCoders/AMP/wiki/Creating-and-using-AMP-themes
25 https://space-node.net/blog/amp-cubecoders-game-server-panel-2026 (tercero, 2026-04-15)
26 https://cftools.com/help/platform/day-z
27 https://dzcommander.com/
28 https://dzcommander.com/docs/api
29 https://github.com/bitfocus/companion
30 https://github.com/bitfocus/companion/releases
31 https://github.com/bitfocus/companion/blob/main/LICENSE.md
32 https://companion.free/user-guide/v5.0/config/triggers (docs v5.0, sin mantenimiento)
33 https://companion.free/user-guide/v5.0/interactive-buttons/web-buttons (ídem)
34 https://github.com/bitfocus/companion-module-generic-http
35 https://docs.elgato.com/streamdeck/sdk/introduction/getting-started
36 https://www.touch-portal.com/api/
37 https://github.com/obsproject/obs-browser
38 https://github.com/obsproject/obs-websocket
39 https://raw.githubusercontent.com/obsproject/obs-websocket/master/docs/generated/protocol.md
40 https://obsproject.com/kb/browser-source
41 https://github.com/playcanvas/editor
42 https://developer.playcanvas.com/user-manual/editor/
43 https://developer.playcanvas.com/user-manual/editor/editor-api/
44 https://developer.playcanvas.com/user-manual/editor/realtime-collaboration/
45 https://github.com/BabylonJS/Editor
46 https://doc.babylonjs.com/legacy/inspector/
47 https://github.com/mrdoob/three.js/blob/dev/editor/js/History.js
48 https://github.com/mrdoob/three.js/blob/dev/editor/js/commands/SetPositionCommand.js
49 https://docs.foxglove.dev/docs/visualization/layouts
50 https://docs.foxglove.dev/docs/visualization/extensions/introduction
51 https://discourse.openrobotics.org/t/foxglove-2-0-integrated-ui-new-pricing-and-open-source-changes/36583 (2024-03-11 ⚠)
52 https://www.home-assistant.io/dashboards/
53 https://developers.home-assistant.io/docs/frontend/custom-ui/custom-card/
54 https://leafletjs.com/examples/crs-simple/crs-simple.html (Leaflet 1.9.4, 2023 ⚠)
55 https://leafletjs.com/2025/05/18/leaflet-2.0.0-alpha.html
56 https://github.com/Leaflet/Leaflet
57 https://openlayers.org/en/latest/examples/static-image.html
58 https://openlayers.org/en/latest/examples/webgl-points-layer.html
59 https://openlayers.org/en/latest/examples/modify-features.html
60 https://github.com/openlayers/openlayers
61 https://deck.gl/docs/api-reference/core/orthographic-view
62 https://github.com/visgl/deck.gl
63 https://github.com/geoman-io/leaflet-geoman
64 https://github.com/commenthol/leaflet-rastercoords
65 https://xgamingserver.com/tools/dayz/map
66 https://github.com/dockview/dockview
67 https://dockview.dev/docs/overview/licence
68 https://dockview.dev/blog/dockview-enterprise (2026-08-07)
69 https://dockview.dev/docs/advanced/accessibility
70 https://dockview.dev/docs/core/state/save
71 https://github.com/caplin/FlexLayout
72 https://github.com/nomcopter/react-mosaic
73 https://github.com/golden-layout/golden-layout
74 https://github.com/bvaughn/react-resizable-panels
75 https://github.com/react-grid-layout/react-grid-layout
76 https://github.com/gridstack/gridstack.js
77 https://github.com/xyflow/xyflow
78 https://reactflow.dev/learn/troubleshooting/remove-attribution
79 https://github.com/retejs/rete
80 https://github.com/jagenjo/litegraph.js
81 https://github.com/Comfy-Org/litegraph.js
82 https://github.com/RaspberryPiFoundation/blockly
83 https://github.com/theatre-js/theatre
84 https://github.com/ievgennaida/animation-timeline-control
85 https://github.com/xzdarcy/react-timeline-editor
86 https://github.com/visjs/vis-timeline
87 https://github.com/pacocoursey/cmdk
88 https://github.com/timc1/kbar
89 https://github.com/jamiebuilds/tinykeys
90 https://immerjs.github.io/immer/patches
91 https://github.com/yjs/yjs
92 https://react-aria.adobe.com/Autocomplete
93 https://github.com/brimdata/react-arborist
94 https://github.com/lukasbach/headless-tree
95 https://jsonforms.io/
96 https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html
97 https://www.w3.org/WAI/ARIA/apg/patterns/treeview/
98 https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
99 https://github.com/caplin/FlexLayout/blob/master/docs/accessibility.md