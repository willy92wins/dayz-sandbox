# DayZ Sandbox: research fase 0, lane Claude

2026-10-23 · DayZ 1.30 (estable desde 2026-10-15) · lane Claude del research dual (`workflow.md` §Flujo, paso 0)

**Cómo se hizo.** Cinco investigaciones web en paralelo, con sus fuentes completas en los anexos A–E (`2026-10-23-lane-claude/`), más lectura directa de `dayz-mcp` (HEAD `f8cf3b4`, 2026-10-23) y del Knowledge Pack. Marcas: **[V]** leído en la fuente, **[I]** inferencia, **✔** re-verificado por mí en la fuente primaria. Las referencias del tipo [C T4] apuntan al anexo y apartado.

**Ceguera.** Escrito antes de abrir el informe de la lane Codex. Sí vi un resumen suyo de diez líneas; lo declaro para que la reconciliación lo tenga en cuenta.

## 0. Conclusiones

1. **El hueco no es "controlar DayZ desde la web"**, eso ya lo hacen CFTools/GameLabs, DZ Commander y los menús de COT y VPP. El hueco es **la escena como documento único**: mapa, hora/clima, objetos, reparto de jugadores, infectados/animales e IA con equipo y acciones, que se aplica, se resetea y se versiona. Nadie lo une hoy; lo más cercano es DayZ Studio, que es de escritorio, alpha, solo vanilla y propietario [C §2].
2. **Técnicamente viable con el patrón de dayz-mcp.** El mod hace long-poll saliente con RestApi a un backend y no abre puertos. dayz-mcp mantuvo `/poll` 600 ms con 4741 ticks en vuelo sin bloquear la simulación ✔ (`dayz-mcp/README.md:104`), así que la latencia puede bajar de 1 s, frente a los 5 s de pago o 60 s gratis de CFTools ✔.
3. **Dos límites duros marcan el alcance.** Un mapa por proceso: cambiar de mapa obliga a reiniciar con otra misión, y el cliente necesita el mod del mapa. Y un solo mod de animaciones a la vez: las acciones de los actores serán emotes y acciones vanilla o las de Expansion AI [C T1, T4].
4. **La IA humana es Expansion AI** (≈984 k suscriptores): facciones, formaciones, waypoints, loadouts. Se usa como dependencia por Workshop, nunca bifurcada. El bot vanilla de 1.30 es de depuración [C §1, T7].
5. **Las licencias deciden la arquitectura.** El núcleo tiene que ser propio. COT (CC BY-SA 4.0 ✔) es lo único derivable; DayZ Editor y Dabs (CC BY-NC-ND 4.0 ✔) y Expansion (CC BY-NC-ND) no; VPP (SARL v1.0 ✔) admite addons independientes, no copiar código. El EULA de DayZ Tools prohíbe explotar comercialmente el contenido creado con ellas ✔, así que el PBO del mod no puede ser comercial; un backend y una web originales podrían serlo [C L1, L3].
6. **El público se reparte así.** La masa está en servidores RP/PvE (Expansion AI/Quests ≈1 M, COT ≈2,2 M); el cine es un nicho vivo (Simple Cinematics ≈23 k) pero es donde nadie une mundo, actores y cámara. En streaming no hay nada para DayZ: Crowd Control no lo soporta [B §0, §3].
7. **La IA entra como proponente, no como actor.** Escribe una escena declarativa que el backend valida y que una persona aprueba; el director en vivo es determinista con perillas y el LLM solo elige entre beats aprobados. Nunca un LLM por NPC ni por tick. Coincide con la opción B de la propuesta "AI Game Master" de dayz-mcp ✔ (`dayz-mcp/plans/2026-06-30-ai-game-master-proposal.md:61-85`) [E §3-4].
8. **dayz-mcp es base de código y banco de pruebas, no el producto.** Es solo 127.0.0.1, monousuario por diseño, con godmode por defecto y validado en DayZDiag ✔ (`README.md`, `product-spec.md` §Fuera de alcance). Además, la spec MCP 2026-07-28 prohíbe que `tools/list` varíe por conexión ✔, y dayz-mcp revela tools según el lease en modo compacto [E §2].

## 1. Funciones: qué se da por hecho y qué diferencia (Q1)

Detalle y matriz por herramienta en el anexo A.

| Función | Quién lo hace mejor | Traducción a DayZ Sandbox | Fase |
|---|---|---|---|
| Mover/rotar con rejilla y ajuste al suelo | Eden: pasos de 0,25 m y 5°, orientar a la normal [A 2A.1] | Mapa 2D con ajuste al suelo (`surface_query`) | MVP |
| Multiselección, copiar/pegar, composiciones con capas | Eden Compositions, Roblox Packages con versiones [A 2A.2] | Plantillas y composiciones de escena | MVP (sin versionado de paquetes) |
| Deshacer/rehacer como transacciones nombradas | Roblox, s&box, Eden, Bedrock convergen [A 2A.3] | Pila de comandos con inverso; irreversibles marcados | MVP |
| Catálogo buscable y filtrable | Entity Browser de Reforger [A 2A.4] | Catálogo de clases del juego y de los mods cargados | MVP |
| Órdenes de IA: waypoints, formación, comportamiento | Eden; Reforger GM con Alt+1…6 en vivo [A 2A.5] | Vía Expansion AI (HALT/ONCE/LOOP/ROAMING, formaciones) | MVP si hay Expansion |
| Hora y clima en vivo, congelables | Reforger GM; "parar el tiempo" de Splendid Camera [A 2A.6, B §2] | `world_time_set`/`world_weather_set` | MVP |
| Presupuestos visibles con tope duro | Reforger (4 presupuestos), UEFN, Forge, Zeus [A 2A.7] | Presupuesto por categoría con medidor | MVP |
| Probar y volver al estado inicial | Eden PLAY restaura el escenario [A 2A.8] | Aplicar/resetear escena con registro de propiedad | MVP |
| Guardar, compartir, versionar | Forge (versiones), UEFN (código privado) [A 2A.9] | Escena JSON versionada, export/import | MVP |
| Roles y permisos por acción | txAdmin (`players.teleport`…), Roblox, Forge [A 2A.10] | Owner/editor/viewer + permiso por acción | MVP mínimo |
| Presets de jugador y loadouts copiables | Eden slots, ZEN copiar equipo [A 2A.11] | Slots de reparto con loadout | MVP |
| Capturar el estado vivo como escena | Solo ZEN "Export Mission SQF" [A 2B.2] | "Guardar lo que hay ahora como escena" | MVP ligero, diferencial |
| GM en vivo con menú contextual y módulos | ZEN (64 módulos + API) [A 2B.1] | Modo "En vivo" con acciones contextuales | Fase 2 |
| Escenarios sin código, despawn por proximidad | Scenario Framework de Reforger [A 2B.4] | Triggers simples (evento + condición + acciones) | Fase 2 |
| Lógica visual | UEFN, Forge, s&box [A 2B.5] | Lista de triggers antes que editor de nodos | Fase 3 |
| Asistente IA plan → aprobación → ejecución | Roblox Planning Mode: los planes nunca se autoejecutan [A 2B.6] | Capa MCP opcional | Fase 2 |
| Cine: grabar primero, dirigir después | Replay Mod, Rockstar Editor [A 2B.11] | Caminos de cámara + OBS; replay de estado no existe en DayZ | Fase 2+ |

Qué evitar [A §3]: no tener deshacer (Menyoo); aplicar el presupuesto solo al publicar (UEFN); guardar proyectos solo en el navegador (mctools.dev avisa de que puede borrarlos); apoyarse en APIs pre-release; un rol de GM rígido (en Reforger lo toma el primero que conecta).

## 2. Necesidades por segmento (Q2)

Detalle en el anexo B.

| Segmento | Imprescindible (P0) | Qué usan hoy | Evidencia |
|---|---|---|---|
| Cine / machinima | Caminos de cámara con easing, focal/DOF y presets; hora/clima congelables y timelapse; actores con emotes; sin HUD | COT, Simple Cinematics, PCT (v0.1.0: caminos, keyframes, DOF; "mundo, actores, luces" en su fase 4 *Planned*), Offline Mode, DayZ Editor | Media-alta: roadmap de PCT, festival de machinima de Milán, Knit's Island |
| Eventos, RP, PvE | Editor visual de patrullas, NPC y misiones que exporte el JSON de Expansion; NPC de misión sin código; escenarios repetibles con reset; presupuestos; edición invisible a los jugadores | Expansion AI/Quests, Dynamic AI Missions, COT, VPP | Alta: base instalada y quejas por JSON extensos y roturas tras parches |
| Streamers | Contrato de efectos (id, precio, duración, estado) con seguridad: cooldown, pausa, zonas seguras, alcance "solo streamer"; OBS y overlays | Nada específico de DayZ; Crowd Control no lo soporta | Baja-media: patrón de 7 Days to Die, Project Zomboid y ARK, sin evidencia propia de DayZ |
| Modders y mapeadores | Snapshot/restore de escena, recorridos de captura automáticos, export a init.c/JSON | Diag, DayZ Editor, dz-testbench, dayz-mcp | Media |
| Educación y storytelling | Diálogo ramificado, escenas compartibles | Captura + edición | Baja |

Hueco concreto para cine: PCT trae cámara pero deja mundo, actores y luces para más adelante y es solo cliente; ninguna herramienta de cámara de DayZ se controla desde fuera del juego [B §0, §3].

## 3. Ecosistema DayZ (Q3)

Detalle en el anexo C.

| Proyecto | Qué cubre | Licencia | Cómo usarlo |
|---|---|---|---|
| DayZ Editor + Dabs | Editor 3D offline; exporta DZE, init.c, VPP, `.map` de Expansion, Object Spawner | CC BY-NC-ND 4.0 ✔ | Importar/exportar sus formatos; no derivar |
| COT | Admin + cámara cine con waypoints (FOV, easing, Catmull-Rom); MapEditor en la rama `dev/1.30` | CC BY-SA 4.0 ✔ | Único derivable (atribución y misma licencia), o dependencia |
| VPP Admin Tools | Admin, freecam, editor XML, webhooks | SARL v1.0 ✔ | Dependencia en runtime |
| Expansion AI / Quests / Missions | IA humana, quests, misiones | CC BY-NC-ND (cabeceras) | Dependencia por Workshop; integrar por API o JSON |
| AI Bandits | IA ligera sobre la simulación de infectados | "No repacks" | Alternativa |
| DayZ Studio (ghosthex-dev) | IDE de escritorio Windows para servidores vanilla: mapa, quests, NPC, export PBO firmado; alpha.7 del 2026-10-22 ✔ | EULA propietaria ✔ | Referente y competidor de escritorio |
| PCT (Psyern) | Cámara cine en cliente, export CSV/JSON | Sin licencia | Referente |
| CFTools Cloud + GameLabs | SaaS: mapa en vivo, acciones; "DayZ does not offer a stable way of pushing data live" ✔ | Cerrado | Competidor en control web |
| DZ Commander | SaaS: el mod sondea una cola de comandos ✔; kits, roles, auditoría | Cerrado | Precedente de patrón |
| dayz-server-manager | Panel web autoalojado con mapa Leaflet | MIT | Casi abandonado (último código 2025-02) |
| dayz-ai-survivor, cortexlink | NPC con LLM sobre Expansion AI con daemon y MCP | MIT ✔ / sin licencia | Precedentes de capa IA |
| Integración Takaro (comunitaria) | Mod + sidecar Node porque RestApi es solo HTTP, sin WebSocket ✔ | — | Precedente |
| dayz-mcp | 88 tools, servidor-autoritativo, local | MIT | Base de código y banco de pruebas |

**Hueco [I]:** (1) escena como documento único aplicable y reseteable; (2) puente web↔juego de baja latencia y autoalojable; (3) acciones de NPC en una línea de tiempo; (4) reparto de jugadores por slot con reset; (5) cámara, actores, mundo y grabación sincronizados; (6) un esquema de escena contra el que pueda escribir una IA.

## 4. Viabilidad técnica (Q4)

| Pieza | Veredicto | Cómo | Fuente |
|---|---|---|---|
| Transporte web → juego | Viable | El mod hace long-poll con `RestContext.GET/POST` asíncronos a un backend; nunca `*_now` dentro del tick; la clave va en `?key=` porque `SetHeader` solo fija Content-Type | ✔ `dayz-mcp-architecture.md` §2-3; `README.md:122-124` |
| Backend remoto | Sin verificar | Que RestApi hable HTTPS no está comprobado; DZ Commander y CFTools sondean desde el mod pero no documentan el transporte ✔. Alternativa segura: relay local en el host del servidor | Spike S1 |
| Latencia | Subsegundo plausible | Long-poll; falta medir el p95 | `README.md:104` ✔ [I p95] |
| Cambiar de mapa | Solo reiniciando | `template` en `serverDZ.cfg`, `-mod` del mapa en servidor y cliente; DLC Sakhal/Nasdara con fuentes en conflicto sobre la posesión | [C T4] |
| Objetos estáticos | Viable | `CreateObjectEx`; persistencia en formato Object Spawner (`spawnerData.json`) | `dayz-mcp-architecture.md` §2; KP `wiki-systems:109` |
| Infectados | Viable con límites | Spawn + `infected_drive` (rumbo con 2,1° de error; `speed` sin calibrar) | `README.md` §In-game numbers |
| Animales | Spawn sí; comportamiento solo vanilla | No hay verbo de control en dayz-mcp | [I] |
| Jugadores como actores | Viable | Teleport, loadout, heal/godmode, emotes, `player_move` | `README.md` |
| IA humana | Vía Expansion AI | Grupos, facciones, formaciones, waypoints, loadouts JSON; el emote pasa por su FSM y no es inmediato; >30 IA degradan sin Frame Time Optimization | [C §1, T6] |
| Bots vanilla 1.30 | No para producción | Guardados tras `DAYZ_1_30`/`ROBOCLIENT`/`INPUT_OVERRIDE`; `bot_start` solo acciones de depuración, TTL ≤ 30 s | ✔ `addon/scripts/5_Mission/MCP_BotControl.c:1-28`; `tools/dayz_mcp/loopback.py:1011-1025` |
| Animaciones | Catálogo vanilla | Un solo mod de animaciones (dos provocan crash); emotes y acciones vanilla o los de Expansion; nada de grafo propio | [C T1] |
| Cámara cine | Viable en cliente | Mod cliente propio o COT como dependencia. La freecam de diag congela la simulación y `SetTimeMultiplier(0)` también las animaciones | KP `dayz-mcp-bridge-protocol.md` §Freecam ✔; `README.md:126` |
| Captura de vídeo/imagen | Externa | `MakeScreenshot` roto (T165276): OBS o captura de ventana | `README.md:122` ✔ |
| Replay | No existe en DayZ | Re-ejecutar la escena y grabar con OBS; el replay de estado con cámara libre sería un proyecto aparte | [B §3] [I] |
| Guardar/cargar escenas | Viable | JSON en el backend; export a Object Spawner/init.c; import de DZE/`.map` | [C §1] |
| Reset limpio | Necesita registro de propiedad | Los IDs runtime del bridge no son estables: el mod debe registrar qué entidades pertenecen a cada escena | [I] |
| Retail frente a Diag | A probar | dayz-mcp está validado en DayZDiag; el producto debe pasar en DayZServer retail | [I] |

## 5. UI web (Q5)

Detalle, librerías y licencias en el anexo D.

**Layout por defecto** (paneles acoplables): arriba, escena activa, modo Borrador/En vivo (patrón Ver/Activar de Foundry VTT), Aplicar, deshacer y edad del dato; izquierda, outliner y biblioteca de plantillas; centro, mapa con herramientas de colocar, ruta, zona y medir, con las entidades pendientes como "fantasma" hasta que el juego confirma; derecha, inspector generado desde el esquema y paleta de acciones; abajo, secuencia de triggers, cola de comandos y registro.

**Personalización:** layouts en JSON por usuario y por rol (Director, Moderador, Streamer táctil); superficie de control tipo Companion servida en `/surface/:id` para tablet o dock de OBS y `/overlay/:id` transparente; teclas reasignables; temas por tokens CSS; extensiones por fases (primero solo JSON importable).

**Stack mínimo [I]:** TypeScript + React + Vite; Dockview (solo el núcleo MIT) detrás de un servicio de layout propio; OpenLayers con imagen estática en píxeles; react-arborist; React Aria Components; tinykeys; SSE del servidor al navegador + POST. Trampas de licencia: Theatre Studio es AGPL, React Flow exige atribución, Dockview tiene una edición enterprise de pago.

**Mapas:** no reutilizar teselas de iZurvive o xam.nu; generarlas en la máquina de cada usuario desde su juego, o empezar con rejilla sin imagen [C L5].

## 6. IA y MCP (Q6)

Detalle en el anexo E.

- **Niveles de acción:** N0 verbos del motor, N1 operaciones con nombre, N2 escena declarativa, N3 intención de director. La autoría va en N2, la dirección en vivo en N3 y N0 queda para desarrollo. dayz-mcp ya midió que un modelo de 27B no encadena tres lecturas pero sí llama un checklist con nombre (`plans/2026-08-17-weak-agent-consumer-ux.md:30,56`).
- **SceneSpec v1:** JSON Schema plano y versionado con ids estables, clases, loadouts, animaciones y facciones de catálogo cerrado, sin campos ejecutables ni URLs; los textos libres son datos de pantalla, nunca instrucciones.
- **Flujo:** validar → plan con hash, diff y coste → aprobación humana en la web → aplicar bajo lease y por lotes → verificar con lecturas → iterar.
- **Fachada MCP aparte:** resources (esquema, catálogo, escenas), prompts (`/design_encounter`, `/review_scene`) y tools (`scene_validate`, `scene_plan`, `scene_submit`, `scene_apply` que responde `input_required` y manda a aprobar a la web, `scene_status`, `scene_rollback`, `director_set_intent`).
- **Spec MCP 2026-07-28 ✔:** sin sesiones ni `initialize`, listas que no varían por conexión, Sampling deprecado (el backend llama al LLM directamente), Tasks y MCP Apps como extensiones opcionales.
- **Coste [I, cálculo del anexo E]:** un director cada 30 s ronda 3 USD por 4 h con Sonnet; 20 NPC con LLM cada 5 s, unos 72 USD por hora.
- **Seguridad:** nombres de jugador, chat y nombres de objeto son entrada no confiable; regla de dos de Meta; la aprobación se liga al hash del plan.

## 7. Riesgos

| Riesgo | Prob. / impacto | Mitigación |
|---|---|---|
| Licencias NC-ND de dependencias y EULA de Tools no comercial | Alta / alto | Núcleo propio; dependencias por Workshop; decidir el modelo comercial antes del plan |
| Monetización: el permiso de BI caduca el 2027-01-31 ✔ y prohíbe ventajas de gameplay ✔ | Media / medio | No basar el negocio en monetizar servidores |
| Roturas por parches (1.30 cambió navmesh y endureció el compilador; Expansion se rompe tras updates) | Alta / medio | Matriz de versiones y pruebas en juego por versión |
| Rendimiento con mucha IA | Media / alto | Presupuestos duros, spawn escalonado, despawn por proximidad |
| Backend expuesto: tokens en URL, comandos destructivos | Media / alto | Auth, roles, confirmación, auditoría; el mod habla solo con loopback o relay |
| Un reset que borre entidades ajenas | Media / alto | Registro de propiedad por escena |
| Dependencia de Expansion AI (API y licencia) | Media / alto | Adaptador fino; el producto funciona sin IA humana |
| Competencia (DayZ Studio, CFTools, DZ Commander) | Media / medio | Diferenciar por escena viva, cine e IA opcional |
| DLC de mapas | Baja / medio | Mapa del MVP sin DLC |

## 8. Arquitectura propuesta [I]

```
Navegador (web, roles) ⇄ Backend (HTTP + SSE: escenas, validación, presupuestos, cola, auditoría)
                              ⇅ long-poll HTTP (el mod llama, el backend responde)
                       Mod servidor SandboxBridge (MissionServer: verbos, registro de propiedad)
                       Mod cliente (fase 2: cámara, HUD, rodaje)
Opcionales: fachada MCP → API del backend · director (determinista + LLM opcional) en el backend
Adaptadores: Expansion AI (si está cargado) · obs-websocket · Companion/Stream Deck por HTTP
```

- **Despliegue:** (a) local, todo en el PC del creador; (b) servidor alojado, con el backend en el mismo host (o relay local si RestApi no habla HTTPS) y la web con autenticación.
- **Relación con dayz-mcp:** copiar sus patrones probados (bridge pull, lease, allowlist en la entrada, deadman con TTL, verbos medidos) al nuevo mod, y seguir usando dayz-mcp como herramienta de desarrollo y QA para probar Sandbox.
- **Lenguaje del backend:** decisión del plan. Python reutiliza el bridge y el SDK MCP de dayz-mcp; TypeScript unifica el stack con la web.

## 9. MVP propuesto y criterios verificables (R26)

**Alcance:** "estudio privado, un mapa".
1. Mod servidor con verbos para objetos, infectados, animales, hora/clima y jugadores (teleport, loadout, godmode, emote), y aplicar/resetear escena con registro de propiedad.
2. Backend con SceneSpec v1 y su JSON Schema, validación, presupuestos, cola con estados (creado → enviado → confirmado), auditoría y export/import (JSON propio y Object Spawner).
3. Web con mapa 2D, outliner, inspector desde el esquema, biblioteca de plantillas, cola, deshacer compensatorio, Ctrl+K, layouts guardables y dos roles.
4. Adaptador opcional de Expansion AI: grupos con loadout, waypoints y comportamiento.

**Fuera del MVP:** cámara cine (fase 2, sobre COT o un mod cliente propio), streaming, director IA y fachada MCP (fase 2), replay, cambio de mapa en caliente, NPC con LLM.

**Criterios con fixtures positivas y negativas:**
- **C1** Aplicar `escena-basica.json` (20 objetos, 10 infectados, 3 animales, 2 jugadores con loadout): conteos exactos por clase y error de posición < 0,5 m, el mismo umbral que A1 de dayz-mcp.
- **C2** Reset: borra el 100 % de las entidades de la escena y ninguna ajena (fixture negativa: un objeto colocado a mano sobrevive).
- **C3** Validación: cinco fixtures inválidas (clase desconocida, fuera del mapa, presupuesto excedido, campo extra, versión de spec errónea) se rechazan con la ruta JSON del error y ninguna llega al juego.
- **C4** Latencia web → juego → confirmación con p95 < 1 s en LAN, medido con N = 100.
- **C5** Sin capa IA: el flujo completo funciona con el MCP apagado y sin dependencias de LLM.
- **C6** FPS del servidor por encima de un umbral fijado tras medir con el presupuesto máximo.
- **C7** C1–C3 pasan en DayZServer retail, no solo en DayZDiag.

**Spikes antes del plan:** S1 RestApi contra HTTPS remoto; S2 latencia del long-poll en retail; S3 API de Expansion AI para crear grupos y lanzar emotes desde un mod ajeno (y si `modded class` sobre CC BY-NC-ND es lícito, preguntando a los autores).

## 10. Decisiones de Guillermo (para el Grill Modo A y el product-spec)

1. ¿Habrá uso comercial algún día? Cambia qué partes separar y qué licencias aceptar.
2. ¿Despliegue local (creador en su PC) o servidor alojado multiusuario?
3. ¿Aceptas Expansion AI como dependencia para los NPC humanos?
4. ¿Público del MVP: eventos/RP o cine/machinima?
5. ¿Mapa del MVP? Por defecto, Chernarus.

## Anexos (lane Claude)

- A. [Benchmark de herramientas de creación de otros juegos](2026-10-23-lane-claude/A-benchmark-herramientas.md)
- B. [Necesidades de los creadores por segmento](2026-10-23-lane-claude/B-necesidades-creadores.md)
- C. [Ecosistema DayZ, hueco y restricciones](2026-10-23-lane-claude/C-ecosistema-dayz.md)
- D. [UI web personalizable: patrones y librerías](2026-10-23-lane-claude/D-ui-web.md)
- E. [IA y MCP coordinando escenas](2026-10-23-lane-claude/E-ia-mcp.md)
