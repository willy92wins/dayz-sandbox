# DayZ Sandbox: research fase 0, consolidado

2026-10-23 · DayZ 1.30 · consolida las dos lanes del research dual (`workflow.md` §Flujo, paso 0)

- **Lane Claude:** [`2026-10-23-dayz-sandbox-claude.md`](2026-10-23-dayz-sandbox-claude.md), con cinco anexos de investigación web y lectura de `dayz-mcp` en HEAD `f8cf3b4` (2026-10-23).
- **Lane Codex:** [`2026-10-23-dayz-sandbox-codex.md`](2026-10-23-dayz-sandbox-codex.md), ciega (codex-cli 0.160, gpt-6-astra, solo lectura + búsqueda web), con un clon de `dayz-mcp` atrasado (`a41580f`, 2026-09-26).
- **⚠ árbitro=lane.** Claude es lane y árbitro. Regla aplicada: evidencia antes que mayoría; los disensos sin evidencia decisiva van abajo en literal (§11).
- Marcas: **[V]** leído en la fuente, **[I]** inferencia, **✔** re-verificado en la fuente primaria al consolidar.

## 1. Qué es el producto y dónde está el hueco

**DayZ Sandbox** es una herramienta para preparar, aplicar, repetir y rodar **escenas** de DayZ desde el navegador: mapa, hora/clima, objetos, reparto de jugadores, infectados, animales e IA humana con equipo y acciones. La IA (vía MCP) es una capa opcional que propone escenas; el producto funciona entero sin ella.

Las dos lanes coinciden en que controlar DayZ desde la web **ya existe** (CFTools/GameLabs, DZ Commander, Takaro comunitario, menús de COT y VPP) y en que **nadie une el flujo completo**: documento de escena → aplicar a una sesión viva → observar lo aplicado → limpiar solo lo de la escena → recargar. Ese es el diferencial, junto con las herramientas de rodaje. El competidor más cercano es **DayZ Studio**: IDE de escritorio Windows, alpha.7 del 2026-10-22, solo vanilla, licencia propietaria ✔ (solo lo encontró la lane Claude).

## 2. Funciones que se esperan y funciones que diferencian

| Tipo | Función | Referente | Fuente |
|---|---|---|---|
| Se da por hecho | Catálogo buscable, selección múltiple, mover/rotar con rejilla y ajuste al suelo | Eden, Roblox Studio, Reforger Entity Browser, Minecraft Editor | Ambas |
| Se da por hecho | Composiciones/plantillas que guardan atributos, inventario y relaciones, no solo posiciones | Eden (también usables en Zeus), Roblox Packages | Ambas |
| Se da por hecho | Deshacer/rehacer como transacciones con nombre | Roblox, s&box, Eden, Bedrock | Claude |
| Se da por hecho | Hora y clima en vivo, congelables | Reforger GM, Splendid Camera | Ambas |
| Se da por hecho | Presupuestos visibles con tope duro | Reforger (4), UEFN, Forge, Zeus | Claude |
| Se da por hecho | Probar y volver al estado inicial | Eden PLAY | Claude |
| Se da por hecho | Guardar, versionar, exportar | Forge, UEFN, Minecraft | Ambas |
| Se da por hecho | Roles y permisos por acción | txAdmin, Roblox, Forge | Ambas |
| Se da por hecho | Espacio de trabajo personalizable: paneles, escala, tema, atajos | Roblox, Minecraft Editor, Axiom | Ambas |
| Diferencia | Operar durante la partida con capacidad acotada (recursos y áreas) | Zeus, Reforger GM, ZEN (64 módulos con API) | Ambas |
| Diferencia | Capturar el estado vivo como escena | ZEN "Export Mission SQF" | Claude |
| Diferencia | Edición conectada a la sesión, con lo editado distinto de lo aplicado | UEFN Live Edit | Codex |
| Diferencia | Secuencias de cámara con keyframes; grabar y dirigir después | UEFN Sequencer, Rockstar Editor, Replay Mod | Ambas |
| Diferencia | Asistente IA con plan editable que nunca se autoejecuta | Roblox Planning Mode + MCP oficial | Ambas |
| Diferencia | Escenarios sin código con despawn por proximidad y aleatorización | Reforger Scenario Framework | Claude |

**Qué evitar** (Claude): no tener deshacer (Menyoo); aplicar el presupuesto solo al publicar (UEFN); guardar solo en el navegador (mctools.dev); depender de APIs pre-release; un rol de GM rígido (Reforger: el primero que conecta).

**Síntesis (Codex, adoptada):** tres modos con expectativas distintas sobre persistencia, deshacer y autoridad: **Preparar** (documento), **En vivo** (sesión) y **Tomas** (rodaje).

## 3. Necesidades por segmento

| Segmento | Qué necesita | Evidencia | Fuerza |
|---|---|---|---|
| Cine / machinima | Planos repetibles con actores, hora/clima congelables y timelapse; cámaras guardadas y caminos con FOV/DOF; sin HUD; recuperar vestuario y posiciones | Claude: PCT deja "mundo, actores, luces" para su fase 4; Simple Cinematics ≈23 k subs; festival de machinima de Milán. Codex: petición de replay y perspectivas (2025), encargo de cámaras suaves con IA y atmósfera (2026-03) | Media-alta, cualitativa |
| Eventos, RP, PvE | Editor visual de patrullas/NPC/misiones que exporte el JSON de Expansion; NPC de misión sin código; escenarios con reset; presupuestos; edición invisible; registro de intervenciones | Claude: Expansion AI ≈984 k y Quests ≈1,13 M subs, quejas por JSON extensos y roturas tras parches. Codex: DayzUnderground, usos de COT | Alta en volumen (Claude), media en entrevistas (Codex) |
| Modders y mapeadores | Escenas mínimas reproducibles, snapshot/restore, recorridos de captura, comparación de resultados | Ambas: DayZ Editor, Diag, dz-testbench, dayz-mcp; Codex: petición de IA dinámica para servidor local (2026-07) | Media-alta |
| Streamers | Contrato de efectos (id, precio, duración, estado) con cooldown, pausa, zonas seguras y moderación previa; OBS y overlays | Crowd Control no soporta DayZ ✔ (Claude); patrón de Twitch Channel Points/EventSub (ambas) | Baja para DayZ |
| Educación | Sesiones reiniciables, objetivos, exportar evidencias | Minecraft Education; un proyecto universitario en DayZ | Baja |

## 4. Ecosistema y licencias

| Proyecto | Qué aporta | Licencia | Uso en Sandbox | Fuente |
|---|---|---|---|---|
| DayZ Editor + Dabs | Editor 3D offline; exporta DZE, init.c, VPP, `.map` de Expansion, Object Spawner | CC BY-NC-ND 4.0 ✔; el README prohíbe repack | Interoperar por formatos; no bifurcar | Ambas |
| COT | Admin modular, cámara cine con waypoints | CC BY-SA 4.0 ✔ | Derivable con atribución y misma licencia, o dependencia | Ambas |
| VPP Admin Tools | Admin | SARL v1.0 ✔: addons independientes sí, copiar código no | Dependencia en runtime | Ambas |
| Expansion AI / Quests / Animations | IA humana, quests; animaciones propias | CC BY-NC-ND en cabeceras; Workshop restringe republicar | Adaptador opcional con versión fijada | Ambas |
| Simple Cinematics, PCT | Cámara de rodaje en cliente | Simple Cinematics prohíbe repack; PCT sin licencia | Referentes | Ambas |
| DayZ Studio | IDE de escritorio para servidores vanilla | EULA propietaria ✔ | Competidor | Claude |
| CFTools + GameLabs | SaaS con mapa, acciones y API; acciones cada 5 s (60 s gratis) ✔ | Cerrado (EULA propia) | Competidor en control web | Ambas |
| DZ Commander | SaaS; el mod sondea una cola de comandos ✔ | Cerrado | Precedente de patrón | Claude |
| Takaro + integración comunitaria | Mod + sidecar Node (RestApi es solo HTTP, sin WebSocket ✔); operaciones "wired", no verificadas ✔ | MIT declarado, fichero no verificado | Comparar antes de construir otra capa admin | Ambas |
| dayz-ai-survivor, cortexlink | NPC con LLM sobre Expansion AI con daemon y MCP | MIT ✔ / sin licencia | Precedentes de capa IA | Claude |
| dayz-mcp | 88 tools ✔ (`README.md:80`), servidor-autoritativo, local | MIT | Base de código y banco de pruebas | Ambas |

**Límites legales (ambas, re-verificados):**
- El EULA de DayZ Tools prohíbe explotar comercialmente el contenido creado con ellas sin permiso ✔. Las reglas de contenido de Bohemia sí permiten herramientas y servicios originales, incluso comerciales, que no usen su contenido ni su IP. Consecuencia [I]: el PBO del mod, no comercial; una web y un backend originales, separables.
- Monetizar servidores exige aprobación, prohíbe ventajas de gameplay ✔ y exige permiso de los autores de cada mod usado ✔. El permiso actual caduca el **2027-01-31** ✔ (portal.bohemia.net/monetization; solo lo recogió la lane Claude).
- Las teselas de iZurvive o xam.nu no se pueden reutilizar; hay que generarlas en la máquina de cada usuario desde su juego (Claude).

## 5. Viabilidad técnica

| Pieza | Veredicto | Evidencia | Fuente |
|---|---|---|---|
| Transporte | Viable. El juego solo es cliente HTTP: el mod hace long-poll asíncrono y el servidor HTTP vive fuera; nunca `*_now` en el tick; la clave va en `?key=` | `restapi.c` (GET/POST asíncronos, `SetHeader` = Content-Type); `MCPBridge.c` ya lo hace | Ambas ✔ |
| Latencia | Subsegundo plausible | dayz-mcp mantuvo `/poll` 600 ms con 4741 ticks en vuelo ✔ (`README.md:104`); falta el p95 | Claude |
| Backend remoto | Sin verificar si RestApi habla HTTPS; alternativa: relay local | DZ Commander/CFTools no documentan el transporte ✔ | Claude |
| Exposición | El bridge de dayz-mcp es loopback con credencial compartida: hace falta una frontera web autenticada delante | `loopback.py` (bind 127.0.0.1, comprobación de credencial) | Ambas |
| Cambiar de mapa | Solo como **transición de sesión**: guardar escena, parar, arrancar otra misión (`template`), reconectar; el cliente necesita el mod del mapa. "Ir a una localización" es otra acción | `serverDZ.cfg`; `game.c` (`PlayMission`/`RestartMission` no acreditan cambio de terreno en caliente) | Ambas |
| Jugadores como actores | Viable: teleport, inventario (`inventory_give`/`attach`), heal/godmode, emotes | `server.py` / `README.md` | Ambas |
| IA humana | Expansion AI; crear un `PlayerBase` por script no da un NPC autónomo | `eAIBase.c` (`eAIBase : PlayerBase`) | Ambas |
| Emotes | Catálogo vanilla (`EmoteManager.PlayEmote`); en Expansion, `Expansion_SetEmote` espera a la FSM: pedido ≠ iniciado | `emotemanager.c`, `eAIBase.c` | Codex (detalle), Claude |
| Animaciones | Un solo mod de animaciones a la vez; nada de grafo propio | Workshop de Expansion; Knowledge Pack | Ambas |
| Infectados | Spawn + `infected_drive` (rumbo con 2,1° de error, `speed` sin calibrar); comportamiento natural por defecto | `README.md` | Ambas |
| Animales | Spawn sí; control por especie sin verificar | `CreateObjectEx` | Ambas |
| Bots vanilla 1.30 | Solo depuración: `bot_start` con acciones permitidas y TTL ≤ 30 s ✔ | `MCP_BotControl.c:1-28`, `loopback.py:1011-1025` | Claude |
| Cámaras | Viables en el **cliente**: `Camera.InterpolateTo`, `SetFOV` (radianes), `SetFocus`, `LookAt`; dayz-mcp ya crea y activa la cámara en cliente ✔ (`MCPClientBridge.c:5696-5776`). La freecam de diag congela la simulación | `camera.c:23-75`; Knowledge Pack | Codex (API), Claude (freecam) |
| Captura | Externa (OBS o captura de ventana): `MakeScreenshot` está roto | `README.md:122` ✔ | Ambas |
| Replay | No existe. Tres productos distintos: grabar vídeo, reejecutar la escena, replay de estado con cámara libre (este último, investigación aparte) | — | Codex (división), Claude |
| Guardar escenas | Formato propio versionado con ids lógicos; los `object_id` del bridge no sobreviven al reinicio; export a Object Spawner | `server.py`, wiki de Bohemia | Ambas |
| Reset | Registro de propiedad por escena; reset nunca toca la persistencia del servidor | — | Ambas |
| Rendimiento IA | Expansion pide FPS de servidor > 60 máx. / > 35 medio; > 30 IA degradan sin Frame Time Optimization | Wiki de Expansion | Claude |
| Multicliente | Validar con servidor dedicado y **dos clientes**: hace falta una segunda cuenta de Steam, porque una cuenta = un cliente ✔ (KP `dayz-mcp-bridge-protocol.md:129`) | — | Codex (requisito), Claude (restricción) |

## 6. Interfaz web

**Patrones (ambas):** catálogo + árbol + mapa + inspector; presets antes que formularios largos; lista de acciones antes que editor de nodos; personalización por rol; accesible por teclado y con alternativa al arrastre (WCAG 2.5.7); sin viewport 3D web al principio.

**Estados observados (Codex, adoptado):** cada operación muestra pendiente, ejecutando, aplicado, observado, fallido o parcial, con la antigüedad del dato. Y no hay un "Deshacer" universal de la partida: "deshacer edición" (documento) es distinto de "compensar una acción ejecutada" (sesión), y la UI dice qué se puede restaurar.

**Layout por defecto (Claude):** barra superior con escena, modo (Preparar / En vivo / Tomas), Aplicar, deshacer y edad del dato; izquierda, árbol y biblioteca de plantillas; centro, mapa con colocar, ruta, zona y medir, y entidades pendientes como "fantasma"; derecha, inspector desde el esquema y paleta de acciones; abajo, secuencia, cola y registro.

**Personalización (Claude):** layouts en JSON por usuario y rol; superficie de botones tipo Companion en `/surface/:id` (tablet o dock de OBS) y `/overlay/:id` transparente; teclas reasignables; temas por tokens CSS; extensiones por fases, empezando por JSON importable.

**Stack mínimo (Claude) [I]:** TypeScript + React + Vite; Dockview (núcleo MIT) tras un servicio de layout propio; OpenLayers con imagen estática en píxeles; react-arborist; React Aria; tinykeys; SSE + POST. Licencias a vigilar: Theatre Studio (AGPL), React Flow (atribución), Dockview enterprise (pago).

## 7. IA y MCP

- **Flujo (ambas):** intención → escena propuesta → validación determinista de capacidades y presupuesto → aprobación humana en la web, ligada al hash del plan → ejecución bajo lease y por lotes → observación → seguir o parar.
- **Permisos fuera del LLM (ambas):** la salida del modelo es una solicitud, no una autorización. Roles (observador, cámara, director, admin) por servidor y escena; presupuesto, vencimiento y parada humana.
- **Entrada no confiable (ambas):** chat, nombres de jugador y nombres de objeto pueden traer instrucciones; nunca cambian la política del director. Regla de dos de Meta (Claude).
- **Niveles (Claude):** N0 verbos del motor (solo desarrollo), N1 operaciones con nombre, N2 escena declarativa (autoría), N3 intención de director (en vivo).
- **Primera IA útil (Codex, adoptada):** convertir "prepara una escena con dos supervivientes y una cámara al amanecer" en un borrador validable. NPC conversacionales persistentes, después.
- **Fachada MCP (Claude):** resources (esquema, catálogo, escenas), prompts y tools `scene_validate`, `scene_plan`, `scene_submit`, `scene_apply` (responde `input_required` y manda a aprobar a la web), `scene_status`, `scene_rollback`, `director_set_intent`. Usa la misma API que la web.
- **Spec MCP 2026-07-28 (Claude) ✔:** sin sesiones ni `initialize`, `tools/list` no varía por conexión, Sampling deprecado (el backend llama al LLM directamente), Tasks y MCP Apps como extensiones opcionales. Choca con el revelado de tools por lease de dayz-mcp en modo compacto.
- **Director (ambas):** determinista con perillas, al estilo del AI Director de Left 4 Dead; el LLM, como mucho, elige cada 30-60 s entre beats aprobados. Es la opción B de la propuesta "AI Game Master" de dayz-mcp ✔. Coste [I, Claude]: unos 3 USD por 4 h con Sonnet, frente a unos 72 USD por hora para 20 NPC con LLM cada 5 s.

## 8. Riesgos

| Severidad | Riesgo | Mitigación | Fuente |
|---|---|---|---|
| Crítica | Acceso remoto no autorizado a la administración | Bridge solo local; API web autenticada; autorización por operación | Ambas |
| Crítica | Reset que borre entidades o datos ajenos | Registro de propiedad; reset acotado; nunca tocar la persistencia | Ambas |
| Alta | Funciona en un cliente y falla en otros | Validar con dedicado + dos clientes, incluida reconexión | Codex |
| Alta | Deriva de versiones de juego, mods y bridge (1.30 cambió navmesh y endureció el compilador) | Versiones fijadas, negociación de capacidades, pruebas por versión | Ambas |
| Alta | Sobrecarga por entidades o IA | Presupuestos por escena medidos con el modset objetivo; spawn escalonado | Ambas |
| Alta | Acciones que nunca arrancan (FSM, grafos de animación) | Catálogo certificado, timeouts, estado observado | Ambas |
| Alta | Licencias: reutilizar código o assets sin permiso | Núcleo propio; dependencias separadas; expediente de licencias por componente | Ambas |
| Alta | Monetización incompatible; permiso de BI que caduca el 2027-01-31 | No basar el negocio en monetizar servidores; nada de ventajas de gameplay | Ambas |
| Alta | Órdenes de audiencia o de LLM fuera de control | Validación externa, límites, moderación, parada | Ambas |
| Media-alta | Prometer replay o sincronía de cine no demostrados | Publicar capacidades por versión y tipo de actor | Codex |
| Media | Dependencia de Expansion AI (API, licencia) | Adaptador fino; producto útil sin IA humana | Claude |
| Media | Competencia (DayZ Studio, CFTools, DZ Commander) | Diferenciar por escena viva, rodaje e IA opcional | Claude |
| Media | Datos de jugadores (identidades, chat, posiciones) | Minimizar, separar permisos, definir retención | Codex |

## 9. Arquitectura recomendada [I]

```
Navegador (web, roles) ⇄ API de Sandbox (HTTP + SSE: escenas, validación, presupuestos, cola, estados, auditoría)
                              ⇅ long-poll HTTP local (el mod llama, el servicio responde)
                       Mod servidor (MissionServer: verbos, registro de propiedad, lotes por tick)
                       Mod cliente (cámaras guardadas; después caminos y rodaje)
Opcionales: fachada MCP → misma API · director determinista (+ LLM opcional) en el backend
Adaptadores: Expansion AI · obs-websocket · Companion/Stream Deck por HTTP
```

- Las dos lanes llegan a la misma forma: el servicio de control vive fuera del juego, solo local, y la API web autenticada va delante. El MCP es un consumidor más de esa API.
- Las acciones precisas se programan dentro del juego (deadline/TTL como en los vehículos de dayz-mcp); no se dirige cada frame por HTTP (Codex).
- De dayz-mcp se copian patrones probados (bridge pull, lease, allowlist en la entrada, deadman con TTL, verbos medidos) a un mod nuevo; dayz-mcp sigue como herramienta de desarrollo y QA (Claude). El lenguaje del backend se decide en el plan: Python reutiliza bridge y SDK MCP; TypeScript unifica con la web.

## 10. MVP recomendado

**Producto:** estudio privado de escenas en PC: una instancia de servidor, un director que escribe, clientes como actores y cámara, un mapa.

**Dentro:** documento de escena versionado con clases y dependencias comprobadas; colocar, inspeccionar y borrar solo entidades de la escena; presets de equipamiento para jugadores actores; infectados y animales con comportamiento natural; hora y clima; **cámaras guardadas** (estáticas); lista secuencial de acciones; guardar, reconstruir y comparar; cola con estados observados, registro y parada; web como interfaz principal.

**Fuera:** replay completo, cambio de terreno en caliente, edición de terreno, animaciones esqueléticas arbitrarias, diálogo LLM persistente, control de audiencia de pago, varios directores escribiendo a la vez, viewport 3D web. Director IA y fachada MCP, en fase 2. Expansion AI entra como adaptador para los NPC actores (§11).

**Cambio por las decisiones del 2026-10-23 (§11):** con cine/machinima como prioridad, los **caminos de cámara con claves** pasan de la fase 2 al MVP, junto con actores NPC que llegan a su marca y hacen gestos, vestuario repetible entre tomas y frames sin HUD. El product-spec ajusta el paso 3 de la tabla a estas entregas.

**Orden de construcción y aceptación** (orden y puertas de Codex; criterios numéricos de Claude):

| Paso | Entrega | Aceptación |
|---|---|---|
| 0 | Matriz de capacidades en la versión y el modset objetivo (spikes: RestApi y HTTPS, p95 del long-poll en retail, API de Expansion) | Dedicado + dos clientes verifican spawn, inventario, cámara, reconexión y limpieza; lo no probado queda INCONCLUSO |
| 1 | API web y adaptación del bridge | Credencial inválida, sesión equivocada o conexión perdida no ejecutan órdenes; nada pendiente se muestra como completado; p95 web → juego → confirmación < 1 s en LAN (N = 100) |
| 2 | Documento de escena y reconstrucción | `escena-basica.json` (20 objetos, 10 infectados, 3 animales, 2 jugadores con loadout): conteos exactos y error de posición < 0,5 m; reconstrucción sin duplicados; 5 fixtures inválidas rechazadas con la ruta JSON y ninguna llega al juego; el reset borra el 100 % de lo suyo y nada ajeno |
| 3 | Cámaras y acciones secuenciales | Una toma de tres cámaras termina o falla de forma explícita; parar devuelve el control |
| 4 | Flujo completo | Un creador prepara, ejecuta, limpia y recarga una escena desde el navegador sin tocar JSON; todo pasa en DayZServer retail; el flujo funciona con el MCP apagado |

Puerta de salida (Codex): entidades observadas en ambos clientes y pruebas negativas. Un HTTP 200, un JSON válido o un número de checks no cuentan como éxito.

## 11. Procedencia y disensos

| Decisión del consolidado | Origen | Evidencia decisiva |
|---|---|---|
| Hueco = escena como documento único, no "control web" | Ambas | CFTools, DZ Commander, Takaro, DayZ Studio |
| Arquitectura pull con servicio externo local y API web autenticada | Ambas | `restapi.c`, `MCPBridge.c`, `loopback.py` ✔ |
| Cambio de mapa = transición de sesión | Ambas | `serverDZ.cfg`, `game.c` |
| IA humana vía Expansion como adaptador, no núcleo | Ambas | Licencia CC BY-NC-ND, `eAIBase.c` |
| Núcleo propio por licencias | Ambas | LICENSE leídos ✔ |
| Estados observados (6) y "compensar" distinto de "deshacer" | Codex | Bridge diferido, emotes por FSM |
| Tres modos: Preparar / En vivo / Tomas | Codex (Tomas), Claude (Borrador/En vivo) | Patrones de Minecraft, UEFN, Rockstar |
| Cámaras guardadas dentro del MVP | Codex | API vanilla `camera.c` y cámara de cliente ya en dayz-mcp ✔ |
| Validación con dos clientes y su coste (segunda cuenta de Steam) | Codex + Claude | KP `dayz-mcp-bridge-protocol.md:129` ✔ |
| Presupuestos, criterios numéricos, spikes S1-S3 | Claude | A1 de dayz-mcp, wiki de Expansion |
| Stack y personalización de la web | Claude | Anexo D (licencias y versiones de npm) |
| Fachada MCP, niveles N0-N3, cambios de la spec 2026-07-28 | Claude | modelcontextprotocol.io ✔ |
| Caducidad del permiso de monetización (2027-01-31) | Claude | portal.bohemia.net ✔ |
| Competidor DayZ Studio | Claude | LICENSE y README leídos ✔ |

**Resuelto por evidencia:**
- *Número de tools de dayz-mcp.* Codex dice "63 herramientas habituales y una opcional"; Claude, 88. Gana **88**: el HEAD actual `f8cf3b4` lo declara (`README.md:80`) ✔ y el MCP vivo expone 88. El dato de Codex sale de un clon de septiembre.
- *Cámaras en el MVP.* Claude las dejaba para la fase 2; Codex las mete en el MVP con la API vanilla verificada y la cámara de cliente que ya existe en dayz-mcp. Gana Codex para cámaras **estáticas**; los caminos con keyframes siguen en la fase 2. (Superado por la decisión 4, abajo: con cine como prioridad, los caminos entran en el MVP.)

**Disenso sin evidencia decisiva (literal, para que decidas):**
- **Codex:** "Prioridad recomendada: empezar por creadores cinematográficos y modders, donde coinciden preparación repetitiva, necesidad de observación y beneficio de guardar escenas. Eventos sería el siguiente segmento; educación y audiencia requieren validación específica antes de orientar el producto hacia ellos."
- **Claude:** "La masa está en servidores RP/PvE (Expansion AI/Quests ≈1 M, COT ≈2,2 M); el cine es un nicho vivo (Simple Cinematics ≈23 k) pero es donde nadie une mundo, actores y cámara." La lane Claude no eligió y lo dejó como decisión tuya.
- **Consecuencia:** con cine y modders primero, Expansion AI queda fuera del MVP (Codex); con eventos/RP primero, entra como adaptador opcional (Claude).
- ~~**Decidido por Guillermo (2026-10-23): eventos y roleplay.**~~ Sustituido el mismo día por la segunda tanda de decisiones (abajo): cine/machinima pasa a ser la prioridad y eventos/RP queda para la fase siguiente.

**Decisiones de Guillermo, segunda tanda (2026-10-23), sobre las preguntas del §10 de la lane Claude:**

| # | Decisión | Consecuencia [I] |
|---|---|---|
| 1 | **Uso comercial: sí** | Se aplica el §4: el PBO del mod no puede ser comercial (EULA de DayZ Tools), así que se publica gratis y lo vendible es la web y el backend originales, separables. Antes de cobrar, confirmar con Bohemia. Expansion AI (CC BY-NC-ND) no puede formar parte del producto comercial: solo adaptador opcional en el MVP. |
| 2 | **Despliegue local** | Mod, API y web en el PC del creador; el mod hace polling a 127.0.0.1, así que el spike S1 (HTTPS desde RestApi) se aplaza. Un solo usuario; credencial local como en dayz-mcp. |
| 3 | **Expansion AI en el MVP, IA propia como meta; producto final standalone** | La IA propia es viable en concepto con piezas vanilla: navmesh (`AIWorld.FindPath`), supervivientes de servidor (`CreatePlayer` sin identidad), locomoción por script (`HumanCommandScript` u overrides de `HumanInputController`) y emotes vanilla. Diseño limpio, sin copiar ni derivar código de Expansion (la cláusula ND lo prohíbe). La escena guarda un vocabulario propio de comportamiento, para que cambiar de motor de IA no cambie las escenas guardadas. Primeros probes: fichas `nav_path_query` y `survivor_drive`. |
| 4 | **Prioridad: cine/machinima** (sustituye a eventos/RP) | Coincide con la recomendación de la lane Codex. P0: caminos de cámara con claves, FOV y enfoque; actores con marcas y gestos; vestuario repetible; reset entre tomas; frames sin HUD; hora y clima controlados. Como una cuenta de Steam es un solo cliente, el reparto más allá del creador tiene que ser NPC, y por eso Expansion sigue en el MVP. |
| 5 | **Mapa: Chernarus** | Sin DLC; confirmado. |

Las fichas de tools nuevas para dayz-mcp (`../tickets/2026-10-23-mcp-tool-tickets.md`) siguen estas prioridades.

## 12. Decisiones pendientes (para el Grill Modo A y el product-spec)

1. ~~**Público del MVP**~~ → **cine/machinima** (decidido el 2026-10-23, segunda tanda; antes eventos y roleplay).
2. ~~**Uso comercial algún día**~~ → **sí**; consecuencias en el §11.
3. ~~**Despliegue**~~ → **local** en el PC del creador.
4. ~~**Mapa del MVP**~~ → **Chernarus**.

Queda para el Grill Modo A: el alcance exacto del MVP de cine, cuándo entra la IA propia y qué parte se vende.

**Siguiente paso:** Grill Modo A para cerrar `DayZSandbox_dev/product-spec.md` con estas decisiones; después, los spikes del paso 0 y el plan en lanes ciegas (Claude + Codex + Grok).
