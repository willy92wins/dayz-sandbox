# DayZ Sandbox - research Fase 0 (lane Codex ciega) - 2026-10-23

**Convenciones:** [V] = leído en la fuente; no implica prueba en juego. [I] = inferencia o propuesta. Las recomendaciones de arquitectura y MVP son **[DESIGN]**, no implementación aprobada.

**Fecha y alcance:** se conserva la fecha solicitada; la consulta se realizó con fecha de entorno **2026-10-24**. Las fuentes web son las disponibles durante la consulta, no una reconstrucción histórica exacta del día 23. Investigación sin escrituras, implementación, ejecución del juego, subagentes ni acceso a ObsidianVault.

## 0. TL;DR

- **[I] El proyecto es viable como director de escenarios y herramienta de rodaje**, combinando un servicio externo, comandos Enforce y un cliente que renderice las cámaras. La evidencia no permite prometer un equivalente completo a UEFN o Rockstar Editor. [Bridge HTTP:233–262][m-bridge]; [cámara cliente:3298–3366][m-client].
- **[V] REST no es el principal obstáculo.** `RestContext` ofrece peticiones HTTP salientes; el MCP existente ya obtiene órdenes mediante `GET` y devuelve resultados mediante `POST`. El servidor HTTP debe residir fuera del juego. [RestApi:84–140][rest]; [MCPBridge:233–262, 3296–3324][m-bridge].
- **[V] El control web de DayZ ya existe:** CFTools/GameLabs ofrece mapa, control de personajes, aparición de objetos y API; Takaro documenta una integración mediante mod y servicio acompañante. **[I] El diferencial debe ser organizar, reproducir y comprobar escenas completas.** [CFTools][cft-integration]; [Takaro][takaro].
- **[V] Hay demanda explícita de herramientas cinematográficas:** usuarios piden replays, perspectivas alternativas, cámaras suaves y preparación de escenas; Simple Cinematics fue financiado originalmente por JLK. Es evidencia cualitativa, no una estimación de mercado. [Petición de replay, 2025][demand-replay]; [encargo cinematográfico, 2026][demand-cine]; [Simple Cinematics][simple].
- **[V] Un humano creado por script no queda acreditado como NPC autónomo.** Expansion AI sí aporta supervivientes con patrullas, combate y formaciones. Su API de emotes espera a que la FSM permita ejecutarlos: solicitar un gesto no equivale a iniciarlo en ese instante. [CreatePlayer:314–326][game]; [Expansion AI][exp-ai]; [eAIBase:10125–10140][eai].
- **[I] “Cambiar mapa” debe presentarse como transición de sesión**, con misión, mods y almacenamiento compatibles. No encontré una API pública que acredite sustituir el terreno de un servidor dedicado activo conservando la sesión. [Configuración del servidor][server-config]; [game.c:1037–1055][game].
- **[V] Las cámaras tienen soporte público real:** activación, FOV, enfoque e interpolación. **[I] Un replay completo con cámara retrospectiva libre es otro proyecto; no debe entrar como compromiso del MVP.** [camera.c:23–75][camera]; [demanda de replay][demand-replay].
- **[V] Las licencias condicionan la arquitectura:** DayZ Editor usa CC BY-NC-ND; VPP tiene una licencia de consulta que permite addons independientes, pero prohíbe copiar código; COT usa CC BY-SA. No son bases intercambiables para reutilización. [Editor][editor-license]; [VPP][vpp-license]; [COT][cot-license].
- **[V] “88 tools” no coincide con el clon autorizado:** su README y registro estático corresponden a **63 herramientas habituales y una opcional, `exec_enforce`**. El HEAD local es del 2026-09-26; no se verificó el registro de un daemon desplegado. [README:65–77][m-readme]; [server.py:5012–5015, 6760–6766][m-server]; [knowledge.py:665–704][m-knowledge].
- **[I] MVP recomendado:** estudio privado en un mapa, escenas versionadas, objetos e inventarios, jugadores como actores, infectados/animales con alcance limitado, cámaras guardadas y lista de acciones con resultados observados. Después: transición entre mapas, actores Expansion y automatización por MCP. [Bridge:578–613][m-bridge]; [inventario:6142–6181][m-server]; [Object Spawner][spawner].

## 1. Q1 — Funciones estándar y diferenciales en otros juegos

“Estándar” significa recurrente entre las herramientas estudiadas; no implica que todos los juegos lo incorporen. La presencia documentada es [V]; la clasificación es [I].

| Función | Referentes verificados | Clasificación e implicación para DayZ Sandbox |
|---|---|---|
| Seleccionar, transformar, duplicar y organizar entidades | Roblox Studio; Minecraft Editor | **Estándar de edición.** Catálogo, selección múltiple, propiedades y organización son expectativas básicas. [Roblox][roblox-ui]; [Minecraft][minecraft-tools] |
| Edición masiva mediante pinceles y selecciones | Minecraft Editor; DayZ Editor | **Estándar en construcción de entornos.** No basta como diferencial propio. [Minecraft][minecraft-tools]; [DayZ Editor][editor] |
| Guardar proyectos y exportar contenido jugable | Minecraft Editor; composiciones de Eden | **Estándar.** Separar documento editable de instancia ejecutada. [Minecraft: proyectos y mundos][minecraft-ui]; [Eden][eden] |
| Composiciones reutilizables | Eden conserva atributos, inventario, capas y conexiones; sus composiciones pueden usarse en Zeus | **Estándar avanzado.** La unidad reutilizable debe incluir relaciones y configuración, no solo posiciones. [Eden][eden] |
| Curación durante una partida | Zeus; Arma Reforger Game Master | **Estándar de game master.** Colocar entidades, ordenar grupos y cambiar condiciones mientras otros juegan. [Zeus][zeus]; [Game Master][reforger] |
| Restricciones al director | Zeus incorpora recursos disponibles y áreas de edición/cámara | **Diferencial operativo.** Un director puede tener capacidad creativa acotada, sin recibir todos los privilegios administrativos. [Zeus][zeus] |
| Colaboración simultánea | Roblox Studio | **Estándar en plataformas de creación completas**, pero costoso para un primer producto. [Colaboración Roblox][roblox-collab] |
| Edición conectada a una sesión | UEFN Live Edit | **Diferencial de iteración.** Distinguir claramente lo editado de lo aplicado al juego. [Live Edit][uefn-live] |
| Secuencias cinematográficas con keyframes | UEFN Cinematic Sequence y Sequencer | **Estándar de cinematografía avanzada.** También tiene coste de memoria, ejecución y replicación. [Cinematic Sequence][uefn-sequence] |
| Grabar clips y editarlos después | Rockstar Editor | **Diferencial frente al control en vivo.** Requiere una representación de lo ocurrido, no únicamente comandos de cámara. [Grabación y edición de clips][rockstar-record] |
| Audio, marcadores y preparación de rodaje | Rockstar Editor/Director Mode | **Diferencial de producción audiovisual.** Es una referencia histórica de producto, no una garantía sobre plataformas actuales. [Actualización oficial de 2015][rockstar-features] |
| Interfaces HTML conectadas al juego | FiveM NUI | **Diferencial de plataforma.** FiveM documenta una UI web integrada; no acredita que DayZ exponga una superficie equivalente. [FiveM NUI][fivem] |
| Personalización del espacio de trabajo | Roblox: paneles y pestañas; Minecraft: escala, fuente, tema y accesos | **Estándar de herramientas maduras.** Conviene ofrecer configuraciones útiles antes que personalización ilimitada. [Roblox][roblox-ui]; [Minecraft][minecraft-ui] |

**[I] Síntesis de producto:** DayZ Sandbox debería combinar el **documento de escena de un editor**, la **operación durante la partida de un game master** y las **tomas de una herramienta cinematográfica**. Son tres modos relacionados, con expectativas distintas sobre persistencia, deshacer y autoridad. [Eden][eden]; [Game Master][reforger]; [Rockstar Editor][rockstar-record].

## 2. Q2 — Necesidades por segmento y evidencia en DayZ

| Segmento | Evidencia encontrada [V] | Necesidad deducida [I] | Solidez |
|---|---|---|---|
| **Machinima y cine** | En enero de 2025 un usuario pide replay, otras perspectivas y configuración de cámara para un trabajo audiovisual. En marzo de 2026 otro busca contratar cámaras suaves, posicionamiento de IA y atmósfera. Simple Cinematics identifica expresamente este uso. [Petición][demand-replay]; [encargo][demand-cine]; [mod][simple] | Preparar y repetir tomas; recuperar vestuario y posiciones; cámaras guardadas; separar grabación real de reconstrucción; reducir dependencia de actores disponibles. | **Alta como señal cualitativa**, sin encuesta representativa. |
| **Streamers e interacción con audiencia** | Twitch dispone de recompensas personalizadas, cola de solicitudes, límites, pausas y reembolsos; EventSub publica las redenciones. [Guía][twitch-guide]; [EventSub][twitch-events] | Botones de efectos permitidos, votaciones, límites por audiencia y control del presentador; moderación antes de ejecutar acciones sensibles. | **Alta para el patrón general; insuficiente para demanda específica de DayZ.** |
| **Eventos y roleplay** | DayzUnderground documenta facciones, territorios, personajes e historias emergentes. COT permite intervenir sobre jugadores, vehículos y clima. [DUG][dug]; [COT][cot] | Preparación de encuentros, reparto de equipamiento, zonas de actuación, recuperación tras incidencias y registro de intervenciones; preservar la autonomía narrativa de los jugadores. | **Media:** usos reales documentados, sin entrevistas a organizadores. |
| **Educación** | Minecraft Education enseña cámara, portfolio y capturas como evidencias de aprendizaje. La petición cinematográfica de DayZ corresponde a un proyecto universitario. [Minecraft Education, 2022][education]; [DayZ, 2025][demand-replay] | Sesiones reiniciables, objetivos claros, observación y exportación de evidencias. | **Baja como mercado DayZ.** No encontré adopción institucional suficiente. |
| **Modders y diseñadores de escenarios** | DayZ Editor se presenta como herramienta para entornos, capturas y pruebas de mecánicas. El MCP local aporta aparición de entidades, inspección y telemetría. Un usuario de 2026 pide IA dinámica para un servidor local. [Editor][editor]; [README:27–50][m-readme]; [petición de IA][demand-ai] | Fixtures reutilizables, escenarios mínimos de reproducción, catálogos de clases, comprobación visual y comparación de resultados. | **Alta para existencia del trabajo; media para prioridades comerciales.** |

### Qué usan hoy los creadores de DayZ

- **[V] DayZ Editor para preparación offline y exportación.** Su página declara expresamente que el editor funciona offline y que los resultados se llevan después al servidor. [DayZ Editor][editor].
- **[V] COT y VPP para administración y preparación de partidas.** COT documenta cámara libre, teletransporte, estado del jugador, clima y vehículos; VPP se presenta como conjunto de herramientas administrativas. [COT][cot]; [VPP README][vpp].
- **[V] Simple Cinematics para rodaje**, con FOV, velocidad, suavizado y distancia de enfoque; requiere acompañarlo de una herramienta administrativa. [Simple Cinematics][simple].
- **[V] Expansion AI para supervivientes controlados por IA**, patrullas y comportamiento de grupo. [Expansion AI][exp-ai].
- **[V, testimonio] Usuarios describen recrear escenas con servidores privados, administradores y actores**, en lugar de recuperar libremente todas las perspectivas de una partida pasada. No lo tomo como descripción universal del trabajo de todos los creadores. [Conversación de 2025][demand-replay].

**[I] Prioridad recomendada:** empezar por creadores cinematográficos y modders, donde coinciden preparación repetitiva, necesidad de observación y beneficio de guardar escenas. Eventos sería el siguiente segmento; educación y audiencia requieren validación específica antes de orientar el producto hacia ellos. [Encargo cinematográfico][demand-cine]; [Editor][editor]; [MCP README][m-readme].

## 3. Q3 — Ecosistema DayZ, licencias y hueco disponible

Las licencias se refieren al código o distribución citados. No extiendo automáticamente esos permisos a todos sus assets, dependencias o versiones históricas.

| Proyecto | Qué aporta [V] | Licencia o condiciones comprobadas [V] | Consecuencia para Sandbox [I] |
|---|---|---|---|
| **DayZ Editor** | Edición 3D offline, colocación, importación/exportación y preparación visual. [Workshop][editor] | `license.md`: **CC BY-NC-ND 4.0**. El README también prohíbe reupload/repack sin permiso. [Licencia][editor-license]; [README][editor-readme] | Priorizar interoperabilidad de datos. No plantear un fork distribuido como base sin resolver permisos. |
| **Community Online Tools — COT** | Administración modular, permisos, cámara libre, jugadores, clima y vehículos. [Workshop][cot] | `LICENSE`: **CC BY-SA 4.0**. El Workshop permite uso en servidores monetizados. [Licencia][cot-license]; [Workshop][cot] | Referente útil y posible integración; cualquier reutilización debe respetar atribución y condiciones de material adaptado. |
| **VPP Admin Tools** | Herramientas administrativas para comunidades. [README][vpp] | `LICENSE`: **Source-Available Reference License v1.0**. Permite estudiar y crear addons independientes dependientes en runtime; prohíbe copiar partes del software, distribuir derivados y repacks. [Licencia][vpp-license] | Usar interfaces o dependencia independiente. No copiar snippets, aunque sean pequeños. |
| **Expansion AI** | Supervivientes IA, patrullas, formaciones, combate, reclutamiento y otras conductas. [Workshop][exp-ai] | El fichero `eAIBase.c` declara **CC BY-NC-ND 4.0**; el Workshop restringe republicación. [Cabecera:1–13][eai]; [Workshop][exp-ai] | Adaptador opcional contra una versión fijada; no incorporar su código al núcleo por defecto. |
| **Simple Cinematics** | Cámara libre, FOV, suavizado, enfoque y controles de rodaje. [Workshop][simple] | La página prohíbe explícitamente repaquetar cualquier parte. No encontré una licencia permisiva de código. [Condiciones de repack][simple] | Referente funcional o dependencia separada, no material para copiar. |
| **Expansion Animations** | Animaciones para vehículos y guitarra; no añade por sí solo una herramienta general de actuación. [Workshop][exp-animations] | La página restringe republicación a la cuenta del equipo. También advierte sobre cargar varios mods de animación. [Workshop][exp-animations] | No asumir compatibilidad con cualquier paquete de animaciones. |
| **CFTools Cloud + GameLabs** | Mapa, logs, control del personaje, aparición de objetos y API. La documentación distingue cadencias de telemetría y entrega de órdenes. [Integración][cft-integration] | GameLabs tiene **EULA propia**, fechada 2023; Workshop declara copyright y derechos reservados. [EULA][gamelabs-eula]; [Workshop][gamelabs-workshop] | El nicho “administración web” ya está ocupado. Una integración requiere respetar sus condiciones y latencias. |
| **Takaro + integración comunitaria DayZ** | Mod de servidor y servicio Node que traduce HTTP a WebSocket; jugadores, mensajes, teletransporte y entrega de objetos. [Documentación][takaro] | El README declara **MIT** y enlaza `LICENSE`, pero el contenido de ese archivo no pudo recuperarse. **Licencia declarada, no plenamente verificada en su fichero.** [Repositorio][takaro-repo] | Alternativa que merece comparación antes de construir otra capa administrativa. Su soporte DayZ es comunitario. |
| **dayz-mcp local** | Control tipado, observación, cámara, inventario, sesiones y lifecycle. [README][m-readme] | **MIT**, leído en `LICENSE:1–21`. [Licencia local][m-license] | Candidato principal para reutilizar transporte y primitivas; todavía falta el modelo de escena del producto. |

**[V] Matiz legal de DayZ Editor:** CC BY-NC-ND permite producir adaptaciones no comerciales, pero no compartirlas bajo esa concesión. Además, el README impone una prohibición amplia de repack. **[I] Esa coexistencia merece aclaración antes de redistribuir; no conviene resolverla suponiendo que “Open Source” en la descripción equivale a permiso de fork.** [Licencia, sección 2][editor-license]; [README][editor-readme].

### El hueco que queda

**[I] En las superficies examinadas no encontré una solución acreditada que reúna todo este flujo:**

1. Documento de escena con mapa, dependencias, actores, equipamiento, cámaras y acciones.
2. Preparación visual y aplicación controlada a una sesión viva.
3. Recuperación de una toma y limpieza limitada a las entidades de esa escena.
4. Estados verificables: preparado, enviado, aplicado, observado, fallido o parcial.
5. La misma operación disponible desde navegador y, opcionalmente, desde MCP.

Es una **oportunidad de integración**, no prueba de ausencia de competidores privados o no indexados. Los componentes están repartidos entre Editor, herramientas administrativas, mods cinematográficos y bridges web. [Editor][editor]; [Simple Cinematics][simple]; [CFTools][cft-integration]; [Takaro][takaro]; [MCP][m-readme].

## 4. Q4 — Viabilidad técnica en DayZ

### 4.1. REST y arquitectura de comunicación

| Evidencia [V] | Implicación [I] |
|---|---|
| `scripts/3_game/http/restapi.c:84–140` declara `GET`, `POST`, callbacks y contextos HTTP; las variantes `_now` están documentadas como bloqueantes. [Fuente][rest] | Usar peticiones asíncronas para el canal de control; mantener el listener HTTP fuera de Enforce. |
| `SetHeader(string)` configura **Content-Type**, según `restapi.c:121–127`. [Fuente][rest] | No diseñar autenticación suponiendo que ese método permite introducir cualquier cabecera HTTP. |
| `MCPBridge.c:185–215` exige URL loopback y configura el contexto. `:233–262` consulta órdenes; `:3296–3324` publica resultados. [Fuente][m-bridge] | El patrón servicio local ↔ mod ya está implementado; no es una hipótesis de integración. |
| `loopback.py:4101–4103` escucha en `127.0.0.1`; `:3169–3194` comprueba credencial y tamaño del cuerpo. [Fuente][m-loopback] | No exponer directamente este puerto como API pública del producto. Añadir una frontera web autenticada. |
| El bridge maneja backpressure antes de aceptar más trabajo, `MCPBridge.c:235–239`. [Fuente][m-bridge] | La UI debe admitir colas y saturación; no tratar cada interacción como operación instantánea. |

**[I][DESIGN] Arquitectura propuesta:** navegador → API de Sandbox → servicio de control local → mod del servidor; un componente cliente recibe las operaciones de cámara y devuelve observaciones. MCP sería otro consumidor de la misma lógica de Sandbox. Las operaciones precisas se programarían dentro del juego, evitando intentar dirigir cada frame mediante peticiones HTTP. [Bridge][m-bridge]; [cámara cliente][m-client]; [control con vencimiento:724–735][m-vehicle].

**Límite de la conclusión:** [V] no encontré un listener HTTP en la superficie pública `RestApi/RestContext` inspeccionada. Esto no demuestra que sea imposible incorporar extensiones nativas; estas quedan fuera del enfoque Enforce investigado. [RestApi][rest].

### 4.2. Cambio de mapa

- **[V] El servidor configura la misión mediante `Missions.DayZ.template`, con formato misión.terreno, cargada al arrancar.** También existen parámetros de misión, mods y almacenamiento. [Configuración oficial][server-config].
- **[V] `game.c:1044–1055` declara `PlayMission`, `RestartMission`, `AbortMission` y funciones del mundo del menú.** `CreateMission` es protegido y su comentario limita el propósito a crear la misión Enforce para recarga de scripts. [Fuente][game].
- **[I] Estas declaraciones no acreditan un cambio de terreno en caliente y transparente en dedicado.** El diseño prudente es guardar la escena, finalizar la sesión de forma controlada, arrancar la misión correspondiente y volver a conectar.
- **[I][DESIGN] Separar dos acciones en la UI:** “ir a una localización” dentro del terreno actual y “abrir otro mapa” mediante transición de sesión. El segundo flujo debe comprobar dependencias y almacenamiento antes de arrancar. [Configuración oficial][server-config].

### 4.3. Jugadores, humanos NPC, infectados y animales

| Actor | Lo comprobado [V] | Lo que todavía requiere trabajo [I] |
|---|---|---|
| **Jugador conectado** | `CreatePlayer` y `SelectPlayer` están declarados en `game.c:314–326`; el bridge tiene teletransporte e inventario. [Vanilla][game]; [server.py:6012, 6142–6181][m-server] | Presets de equipamiento, consentimiento/roles de actores y restauración acotada del estado. |
| **Humano autónomo** | Expansion define `eAIBase: PlayerBase` y documenta patrullas, combate y formaciones. [eAIBase:19][eai]; [Workshop][exp-ai] | Crear un `PlayerBase` no basta para demostrar percepción, navegación o combate autónomos. Conviene integrar un backend existente. |
| **Infectado** | El bridge usa `DayZInfectedInputController`, `OverrideMovementSpeed`, `OverrideHeading` y liberación de esos overrides. [MCPBridge:1274–1292][m-bridge] | Es una primitiva de control; no acredita un editor de rutas ni coreografías fiables ante obstáculos. |
| **Animal** | Existe creación genérica mediante `CreateObjectEx`; el contrato del bridge admite clases de objetos. [game.c:666][game]; [MCPBridge:578–613][m-bridge] | No quedó verificada una API equivalente de dirección, animación y finalización para cada especie. Su comportamiento debe probarse por categoría. |

**[V] El equipamiento ya dispone de primitivas útiles:** `inventory_give` distingue manos/inventario; `inventory_attach` distingue attachments/cargo y devuelve una lectura inmediata del inventario. **[I] Falta componerlas en un preset validado, con errores parciales explícitos.** [server.py:6142–6181][m-server].

### 4.4. Emotes y animaciones

- **[V] Vanilla tiene `EmoteManager.PlayEmote(int)`**, que comprueba condiciones, resuelve los datos del gesto y crea su callback. También hay un recorrido de sincronización servidor/cliente. [emotemanager.c:507–542, 629–676][emotes].
- **[V] Expansion ofrece `Expansion_SetEmote(int, bool, int)`**, y su comentario indica que el gesto no empieza inmediatamente: espera a una transición de la FSM. Después llama al gestor de emotes. [eAIBase:10125–10140][eai].
- **[V] `object_anim` del MCP controla fases mediante `SetAnimationPhaseNow`.** No es una herramienta genérica de animación esquelética humana. [server.py:6050–6079][m-server]; [MCPBridge:1161–1203][m-bridge].
- **[V] El Knowledge Pack distingue animación de objetos y animación esquelética.** Advierte de conflictos al reemplazar el grafo principal de personajes/criaturas y matiza que no se aplica por igual a rutas `.asi` subordinadas. [Skill de animación:43–45][kp-animation].
- **[I][DESIGN] El producto debe mostrar “solicitado”, “iniciado”, “terminado” o “rechazado”**, con timeout. Un catálogo de gestos compatibles es abordable; “reproducir cualquier animación en cualquier NPC” no está acreditado. [EmoteManager][emotes]; [Expansion][eai].

### 4.5. Cámara cinematográfica

**[V] APIs públicas verificadas:**

| API | Fuente y alcance |
|---|---|
| `Camera.InterpolateTo(Camera, float, int)` | `camera.c:23`; interpolación entre cámaras. [Fuente][camera] |
| `SetActive`, `EnableSmooth`, `StopInterpolation` | `camera.c:42–52`. [Fuente][camera] |
| `SetFOV(float)` | `camera.c:63`; **radianes**, no grados. [Fuente][camera] |
| `SetFocus(float, float)` | `camera.c:70`; distancia y desenfoque. [Fuente][camera] |
| `LookAt(vector)` | `camera.c:75`. [Fuente][camera] |

**[V] El MCP ya crea una cámara, establece posición/orientación o destino visual, ajusta FOV y la activa en el cliente.** Su contrato distingue grados para orientación y radianes para FOV. [MCPClientBridge:3298–3366][m-client]; [server.py:6480–6495][m-server].

**[I] Son viables cámaras guardadas y movimientos de cámara programados.** Quedan por demostrar suavidad, streaming de terreno, retorno al control normal y consistencia entre clientes. La declaración de interpolación no acredita una toma sin tirones en la configuración objetivo. [camera.c][camera]; [MCPClientBridge][m-client].

### 4.6. Replays

**[V] No se encontró una API pública de replay completo en las superficies investigadas**, ni una herramienta de ese tipo en el registro local del MCP. La petición comunitaria de 2025 refleja precisamente esa carencia percibida. [Registro documentado:65–77][m-readme]; [petición][demand-replay].

**[I] Conviene distinguir tres productos:**

| Producto | Alcance razonable |
|---|---|
| **Grabación de vídeo** | Captura el resultado renderizado. No permite recuperar después una perspectiva que no fue grabada. |
| **Reejecución de una escena** | Reaplica una configuración inicial y sus acciones; física, IA y red pueden producir otra toma. |
| **Replay de estado con cámara retrospectiva** | Necesita capturar entidades, animaciones, inventarios, eventos y evolución suficiente para reconstruir la escena. Es una investigación independiente. |

Esta separación deriva de la diferencia entre las primitivas de control observadas en DayZ y el flujo de clips de Rockstar Editor. [MCP][m-readme]; [Rockstar Editor][rockstar-record].

### 4.7. Guardar y cargar escenarios

- **[V] `JsonFileLoader<T>.LoadFile/SaveFile` devuelve éxito y error**, pero serializa los datos que se le proporcionan; no captura automáticamente una simulación. [jsonfileloader.c:7–62][json].
- **[V] Object Spawner carga listas de objetos al inicio de la misión**, con posición, orientación y otros campos. No se presenta como guardado completo de actores, cámaras y acciones. [Documentación oficial][spawner].
- **[V] Los `object_id` del MCP son propios de la ejecución y no sobreviven al reinicio.** [server.py:5637–5646][m-server].
- **[I][DESIGN] Crear un formato de escena explícito**, con versión, terreno, dependencias, identificadores lógicos, clases, transformaciones, equipamiento, cámaras y acciones. Mantener aparte la asociación entre esos identificadores y los objetos de la sesión actual.
- **[I][DESIGN] Restaurar únicamente el contenido administrado por la escena.** Duplicados, clases ausentes, mapa incorrecto y cargas parciales deben producir estados visibles; “reset” no debe significar borrar la persistencia del servidor. [Identificadores del bridge][m-server]; [alcance de Object Spawner][spawner].

## 5. Q5 — Patrones de UI web intuitiva y personalizable

Las siguientes decisiones son **[I][DESIGN]**, apoyadas en patrones documentados; su usabilidad en DayZ queda pendiente de pruebas con creadores.

| Patrón propuesto | Aplicación concreta | Referente |
|---|---|---|
| **Modos Preparar / En vivo / Tomas** | Diferenciar edición del documento, cambios aplicados a la sesión y material de rodaje. | Proyectos/mundos de [Minecraft][minecraft-ui], [Live Edit][uefn-live], clips de [Rockstar][rockstar-record]. |
| **Catálogo + escena + inspector** | Biblioteca de entidades; árbol de grupos/actores; mapa o vista; propiedades de la selección. | [Roblox Studio][roblox-ui]. |
| **Presets antes que formularios extensos** | Equipamiento de actor, grupo de infectados, iluminación y cámaras reutilizables; propiedades avanzadas disponibles al desplegar. | Composiciones con atributos de [Eden][eden]. |
| **Estado observado separado del solicitado** | Mostrar pendiente, ejecutando, aplicado, observado, fallido y parcial; incluir antigüedad de la telemetría. | Cola y resultado del [bridge:3232–3257][m-loopback]; [mensajes de estado WCAG][wcag-status]. |
| **Lista de acciones antes que grafo complejo** | “Preparar actores → mover cámara → iniciar gesto → esperar finalización”. Añadir ramas y nodos cuando haya necesidad real. | Secuencias de [UEFN][uefn-sequence]; posibilidades de edición de [React Flow][react-save]. |
| **Personalización por rol** | Espacios “Rodaje”, “Evento” y “Prueba”; favoritos, paneles y atajos; opción visible de restablecer disposición. | [Roblox][roblox-ui]; [Minecraft][minecraft-ui]. |
| **Operación accesible** | Entrada numérica de posición, botones de movimiento, navegación por teclado y alternativa al arrastre. | [WCAG 2.5.7][wcag-drag]; [React Flow Accessibility][react-access]. |
| **Control de efectos sobre el juego** | Separar “deshacer edición” de “compensar acción ejecutada”; mostrar qué puede restaurarse y qué no. | Diferencia entre documento y sesión en [Minecraft][minecraft-ui] y operaciones del [bridge][m-bridge]. |

**[I] No haría del viewport 3D web una dependencia inicial.** Un mapa con entidades, inspector y vista del cliente permite comprobar el flujo central antes de asumir la conversión y distribución de terrenos y assets. La cámara de DayZ sigue ejecutándose en el cliente del juego. [MCPClientBridge:3298–3366][m-client]; [reglas de contenido de Bohemia][bi-content].

**[I] Tampoco presentaría un botón universal “Deshacer” para la partida.** Teletransportar un actor de vuelta puede ser reversible; restaurar todos los efectos de una muerte, combate o interacción requiere otro contrato de estado. [Controles de personaje existentes][cft-integration]; [serialización explícita][json].

## 6. Q6 — IA coordinando escenas y patrones seguros

### Tres usos distintos de IA

| Uso | Evidencia [V] | Aplicación a Sandbox [I] |
|---|---|---|
| **Asistente de autoría mediante MCP** | Roblox Studio incorpora MCP para inspeccionar, editar y probar; MCP for Unity expone operaciones sobre escenas, objetos y scripts. [Roblox][roblox-mcp]; [Unity][unity-mcp] | Generar borradores de escenas y preparar tomas mediante herramientas tipadas. |
| **Director adaptativo** | Valve documenta un director que regula la población y el ritmo según una estimación de intensidad. Es un referente de 2009, no una solución LLM. [Presentación, pp. 77–80][valve-director] | Un director de oleadas puede empezar con reglas y presupuestos medibles, sin conversación generativa. |
| **NPC con LLM** | *Generative Agents* demuestra memoria, reflexión y planificación en un entorno con 25 agentes. Es investigación de 2023. [Artículo][generative-agents] | Usar el modelo para objetivos y diálogo; delegar movimiento, combate y animación a controladores verificables. |
| **Personajes generativos con voz/animación** | NVIDIA documenta componentes ACE para voz, modelos de lenguaje y animación en Unreal. [ACE][nvidia-ace] | Referente de descomposición; no prueba compatibilidad de esos plugins con DayZ. |

### Qué aporta ya el MCP local

- **[V] Separación de servidor y cliente:** aparición de objetos por el servidor y cámaras en el cliente. [server.py:5618–5635][m-server]; [MCPClientBridge:3298–3366][m-client].
- **[V] Autorización de operaciones mediante identidad y lease cuando la coordinación está configurada.** [loopback.py:1657–1710][m-loopback].
- **[V] Control sostenido con vencimiento:** el controlador de vehículos deja de aplicar la orden cuando supera su deadline. Esto acredita ese mecanismo concreto, no un watchdog universal para toda acción. [MCP_CarScript.c:724–735][m-vehicle].
- **[V] Ejecución Enforce opcional y restringida**, condicionada a configuración y lista de expresiones permitidas. [server.py:6760–6766][m-server].
- **[V] No se encontró un modelo completo de escena, timeline o actores humanos IA en su catálogo actual.** [README:65–77][m-readme].

### Patrón recomendado

**[I][DESIGN] Flujo:** intención → propuesta de escena → validación de capacidades y presupuesto → ejecución → observación → continuación o parada.

| Control | Motivo y fundamento |
|---|---|
| **Herramientas acotadas por función** | El director no necesita shell, scripts arbitrarios ni todas las herramientas administrativas. OWASP identifica exceso de funcionalidad y permisos como origen de agencia excesiva. [OWASP][owasp-agency] |
| **Permisos aplicados fuera del LLM** | Roles de observador, cámara, director y administrador; alcance por servidor y escena. La salida del modelo es una solicitud, no una autorización. [OWASP][owasp-agency]; [MCP Security][mcp-security] |
| **Chat y nombres tratados como datos no fiables** | Un mensaje de espectador o nombre de objeto puede contener instrucciones maliciosas. No debe modificar la política del director. [OWASP Prompt Injection][owasp-injection] |
| **Presupuesto y vencimiento** | Máximos de entidades, operaciones, duración y gasto; cancelar la ejecución si pierde conexión o autoridad. El MCP ya muestra una aplicación acotada del patrón de deadline. [Control local][m-vehicle] |
| **Precondiciones e idempotencia** | Antes de actuar, comprobar sesión y entidad; no repetir ciegamente un spawn tras perder una respuesta. Los objetos actuales tienen identificadores de ejecución. [Contrato de objetos][m-server] |
| **Resultado observado** | “Orden aceptada” y “acción terminada” son estados diferentes, especialmente en emotes y tareas diferidas. [Expansion][eai]; [trabajos de spawn:600–613][m-bridge] |
| **Parada humana y recuperación** | La automatización debe poder detenerse, conservar el registro y liberar control sin continuar órdenes antiguas. [OWASP][owasp-agency]; [lease y sesiones][m-server] |

**[I] Primera IA útil:** convertir “prepara una escena con dos supervivientes y una cámara al amanecer” en un borrador validable. El NPC conversacional persistente añade memoria, privacidad, latencia, voz y comportamiento; conviene evaluarlo después. [Roblox MCP][roblox-mcp]; [Generative Agents][generative-agents].

## 7. Q7 — Riesgos y MVP propuesto

### Riesgos

La severidad es [I], estimada para una herramienta con capacidad de modificar una partida.

| Severidad | Riesgo | Evidencia y mitigación propuesta |
|---|---|---|
| **Crítica** | Acceso remoto no autorizado a administración, ejecución o lifecycle | [V] El bridge actual está diseñado para loopback y usa credencial compartida. [I] Mantenerlo local; autenticar la API web, autorizar cada operación y limitar destinos y recursos. [loopback.py:3169–3194, 4101–4103][m-loopback]; [MCP Security][mcp-security] |
| **Crítica** | Reset que borre entidades o datos ajenos a la escena | [V] Los identificadores del bridge son temporales. [I] Registro de propiedad por escena, restauración acotada y copia verificable antes de tocar persistencia real. [server.py:5637–5646][m-server] |
| **Alta** | Funciona en un cliente, falla o difiere en los demás | [V] Cámara y otras operaciones tienen autoridad cliente; mundo e inventario usan otra ruta. [I] Validar con dedicado y dos clientes, incluida reconexión. [mundo][m-bridge]; [cámara][m-client] |
| **Alta** | Deriva entre versión del juego, mods y bridge | [V] El clon es de septiembre; fuentes web consultadas reflejan actualizaciones posteriores. [I] Fijar versiones y negociar capacidades antes de cargar una escena. [MCPBridge:254–260][m-bridge]; [Expansion Workshop][exp-ai] |
| **Alta** | Sobrecarga por entidades, IA, inventarios o telemetría | [V] Bohemia advierte del impacto de muchos objetos; el bridge limita admisión. [I] Presupuestos por escena y medición con el modset objetivo; no inventar un límite universal. [Object Spawner][spawner]; [MCPBridge:235–239][m-bridge] |
| **Alta** | Animaciones incompatibles o acciones que nunca arrancan | [V] Hay restricciones de grafos y ejecución condicionada por FSM. [I] Catálogo certificado, timeouts y resultado observado. [Knowledge Pack:45][kp-animation]; [eAIBase][eai] |
| **Alta** | Reutilización de código o assets sin permiso | [V] Editor, VPP, Expansion y Simple Cinematics tienen restricciones diferentes. [I] Núcleo propio; dependencias separadas; expediente de licencias por componente. [Editor][editor-license]; [VPP][vpp-license]; [Expansion][eai]; [Simple][simple] |
| **Alta** | Monetización incompatible | [V] Bohemia exige aprobación para monetizar servidores y prohíbe recompensas que afecten al gameplay; también exige permiso de autores de mods. [I] No incluir compras de spawns, armas o ventajas como supuesto del producto. [Reglas oficiales][monetization] |
| **Alta** | Órdenes de audiencia o LLM fuera de control | [I] Validación externa, límites, moderación y parada; nunca ejecutar texto recibido como código. [OWASP][owasp-injection]; [Twitch][twitch-guide] |
| **Media/alta** | Prometer replay o sincronización cinematográfica no demostrados | [I] Distinguir vídeo, reejecución y replay; publicar capacidades por versión y tipo de actor. [Rockstar][rockstar-record]; [emotes Expansion][eai] |
| **Media** | Exposición de datos de jugadores y conversación | [V] Las integraciones pueden manejar identidades, chat, posiciones y logs. [I] Minimizar datos, separar permisos de cámara y administración y definir retención. [Takaro][takaro-repo]; [MCP Security][mcp-security] |

### Límites legales relevantes

- **[V] El EULA de DayZ permite crear y compartir imágenes/vídeos, con condiciones para su monetización.** Eso no constituye permiso general para comercializar cualquier derivado o servicio basado en contenido del juego. [EULA DayZ][bi-eula].
- **[V] El EULA de DayZ Tools limita el software y el contenido creado con él a usos no comerciales salvo permiso.** La copia consultada en la wiki tiene antigüedad de indexación; debe revalidarse al decidir el modelo comercial. [EULA Tools][bi-tools].
- **[V] Las reglas de contenido permiten herramientas y servicios originales, incluso comerciales, si no utilizan contenido, herramientas u otra propiedad intelectual de Bohemia.** **[I] La separación entre web original, mod, assets y servicios importa jurídicamente; una etiqueta “SaaS” no resuelve por sí sola esa frontera.** [Reglas de contenido][bi-content].
- **[V] Steam distingue las contribuciones al Workshop y sus condiciones específicas.** **[I] Publicar o descargar en Workshop no debe interpretarse como permiso general para incorporar y redistribuir código o assets ajenos.** [Steam, sección 6][steam-terms].

### MVP concreto — [I][DESIGN]

**Producto:** “Estudio privado de escenas DayZ para PC”, orientado a preparar y repetir tomas y pruebas. Una instancia de servidor, un director con capacidad de escritura y clientes actores/cámara. El foco se apoya en la demanda cinematográfica y en las primitivas ya existentes. [Demanda][demand-cine]; [MCP][m-readme].

**Alcance:**

- Un mapa inicial y localizaciones guardadas.
- Documento de escena versionado, con clases y dependencias comprobadas.
- Colocar, inspeccionar y eliminar únicamente entidades administradas por la escena.
- Presets básicos de equipamiento para jugadores actores.
- Aparición de infectados y animales; comportamiento natural inicialmente. Control adicional de infectados solo tras su prueba específica.
- Hora, clima, cámaras guardadas y una lista secuencial de acciones.
- Guardar, reconstruir y comparar el estado de la escena.
- Registro de operaciones, estados parciales y parada de ejecución.
- Navegador como interfaz principal; MCP opcional.

Estas capacidades son una composición propuesta de las herramientas observadas, no una afirmación de que exista ya ese producto. [Spawn e inventario][m-server]; [control de infectados][m-bridge]; [cámara][m-client]; [JSON][json].

**Fuera del MVP:** replay completo, cambio de terreno en caliente, edición de terreno, animaciones esqueléticas arbitrarias, diálogo LLM persistente, control de audiencia de pago, múltiples directores escribiendo a la vez y viewport web con todos los assets. La exclusión responde a los límites técnicos, operativos y legales descritos. [Mapa][server-config]; [animaciones][kp-animation]; [licencias][bi-content]; [agencia][owasp-agency].

**Orden de construcción y aceptación:**

| Orden | Entrega | Criterio propuesto de aceptación |
|---|---|---|
| **0** | Matriz de capacidades en la versión y modset objetivo | Dedicado y dos clientes verifican spawn, inventario, cámara, reconexión y limpieza. Declaración de API sin prueba queda **INCONCLUSO**. |
| **1** | API web y adaptación al bridge | Credenciales inválidas, sesión equivocada y pérdida de conexión no ejecutan órdenes nuevas. Resultados pendientes no se muestran como completados. |
| **2** | Documento de escena y reconstrucción | Una escena de prueba con objetos, dos jugadores, infectados y un animal se reconstruye sin duplicados; clases ausentes y mapa incorrecto se rechazan antes de aplicar. |
| **3** | Cámaras y acciones secuenciales | Una toma de tres cámaras termina o falla de forma explícita; parar devuelve el control al operador. Guardar una escena no guarda falsamente el estado completo del motor. |
| **4** | Flujo de uso completo | Un creador prepara, ejecuta, limpia y vuelve a cargar una escena desde el navegador sin editar JSON manualmente. |
| **Después** | Otros mapas, Expansion AI y MCP de escenas | Transición controlada entre misiones; actor IA y emotes con observación de inicio/final; MCP utiliza el mismo contrato validado que la UI. |

**[I] Puerta de salida del MVP:** demostrar el flujo completo con entidades observadas en ambos clientes, pruebas negativas y reconstrucción de escena. No aceptar como éxito únicamente un HTTP 200, un JSON válido o un número de checks. Este criterio responde a los trabajos diferidos del bridge, la separación cliente/servidor y los emotes condicionados. [Spawn diferido][m-bridge]; [cámara cliente][m-client]; [Expansion][eai].

## 8. Lo que NO se pudo verificar y ángulos que faltan

1. **Ejecución real:** no se arrancó DayZ, no se ejecutaron tests ni se comprobaron PBO desplegados. Toda viabilidad técnica presentada procede de lectura de código y documentación.
2. **Build objetivo:** falta fijar versión retail/diag, mapas, modset y topología. El clon local tiene HEAD `a41580f490657ffbc4f4e10f76fedd31398e6e60`, fechado 2026-09-26; esto no acredita lo desplegado.
3. **“88 tools”:** no se reprodujo esa cifra. El registro estático inspeccionado concuerda con 63 herramientas habituales más `exec_enforce` opcional; no se consultó un servidor MCP en ejecución. [README][m-readme]; [registro][m-server]; [herramientas de conocimiento][m-knowledge].
4. **Cambio de mapa en caliente y replay completo:** no encontrados como contratos públicos utilizables en las fuentes examinadas. No equivale a una prueba exhaustiva de imposibilidad. [game.c][game]; [catálogo local][m-readme].
5. **NPC humanos y animales:** falta demostrar navegación, actuación, equipamiento, sincronización de emotes y recuperación ante interrupciones con las clases concretas del producto. [Expansion][eai]; [spawn genérico][m-bridge].
6. **Rendimiento:** no hay benchmark de entidades, IA, frecuencia HTTP, capturas o tamaño de escena. No se propone un aforo ni una tasa de actualización acreditados. [Advertencia oficial][spawner].
7. **Takaro:** se leyó la declaración MIT del README; no pudo recuperarse el contenido de `LICENSE`. La licencia debe verificarse antes de reutilizar su código. [Repositorio][takaro-repo].
8. **Usabilidad y mercado:** no hubo entrevistas, pruebas con usuarios ni medición de disposición a pagar. Educación e interacción de audiencia en DayZ tienen evidencia especialmente insuficiente.
9. **Fuentes históricas:** Valve 2009, Rockstar 2015, Minecraft Education 2022 y *Generative Agents* 2023 sirven como referentes de diseño, no como prueba de disponibilidad o rendimiento actual.
10. **Acceso a fuentes:** algunas páginas de Bohemia devolvieron 403 y algunas rutas GitHub fallaron. Se usaron otras fuentes primarias accesibles; no se rellenaron esos huecos con APIs supuestas.
11. **Workshop:** las extracciones mostraron avisos genéricos de retirada/incompatibilidad junto a descripciones y actualizaciones. No se usaron esos avisos como prueba de que todos esos mods estuvieran retirados.
12. **Cobertura ciega:** no se consultó material de la otra lane ni memoria de proyecto en ObsidianVault. Falta la comparación posterior del coordinador y la validación del modelo comercial con las licencias aplicables.

## 9. Fuentes

Las referencias siguientes enlazan directamente a los documentos, código y páginas utilizados.

**Herramientas de creación**

- [Minecraft: herramientas][minecraft-tools] · [interfaz, proyectos y mundos][minecraft-ui].
- [Roblox Studio: interfaz][roblox-ui] · [colaboración][roblox-collab] · [MCP][roblox-mcp].
- [UEFN: Live Edit][uefn-live] · [Cinematic Sequence][uefn-sequence].
- [Eden: composiciones][eden] · [Zeus: módulos][zeus] · [Reforger: Game Master][reforger].
- [Rockstar: grabación y edición][rockstar-record] · [funciones históricas de Editor/Director Mode][rockstar-features].
- [FiveM: NUI][fivem].

**Necesidades y usuarios**

- [DayZ: petición de replay, enero de 2025][demand-replay].
- [DayZ: encargo cinematográfico, marzo de 2026][demand-cine].
- [DayZ: petición de IA dinámica, julio de 2026][demand-ai].
- [DayzUnderground][dug].
- [Twitch: recompensas para creadores][twitch-guide] · [EventSub][twitch-events].
- [Minecraft Education: evidencias y evaluación][education].

**Ecosistema y licencias**

- [DayZ Editor][editor] · [licencia][editor-license] · [README][editor-readme].
- [COT][cot] · [licencia][cot-license].
- [VPP][vpp] · [licencia][vpp-license].
- [Expansion AI][exp-ai] · [código y licencia de eAIBase][eai] · [Expansion Animations][exp-animations].
- [Simple Cinematics y condiciones de repack][simple].
- [CFTools: integración DayZ][cft-integration] · [GameLabs Workshop][gamelabs-workshop] · [EULA][gamelabs-eula].
- [Takaro: integración DayZ][takaro] · [repositorio y declaración de licencia][takaro-repo].

**DayZ público**

- [RestApi][rest] · [CGame][game] · [EmoteManager][emotes] · [Camera][camera] · [JsonFileLoader][json].
- [Configuración del servidor][server-config] · [Object Spawner][spawner].

**UI, IA y seguridad**

- [React Flow: guardar/restaurar][react-save] · [accesibilidad][react-access].
- [WCAG: alternativa al arrastre][wcag-drag] · [mensajes de estado][wcag-status].
- [MCP for Unity][unity-mcp] · [Valve: AI Systems of Left 4 Dead][valve-director].
- [Generative Agents][generative-agents] · [NVIDIA ACE][nvidia-ace].
- [MCP Security][mcp-security] · [OWASP: prompt injection][owasp-injection] · [agencia excesiva][owasp-agency].

**Bohemia y Steam**

- [EULA DayZ][bi-eula] · [EULA DayZ Tools][bi-tools] · [uso de contenido][bi-content].
- [Monetización de servidores][monetization] · [Steam Subscriber Agreement, sección 6][steam-terms].

**Fuentes locales**

- `~\Repos\dayz-mcp\`: [README.md][m-readme], [LICENSE][m-license], [tools/dayz_mcp/server.py][m-server], [loopback.py][m-loopback], [knowledge.py][m-knowledge], [addon/scripts/5_Mission/MCPBridge.c][m-bridge], [MCPClientBridge.c][m-client], [addon/scripts/4_World/MCP_CarScript.c][m-vehicle].
- `~\DayZ-Modding-Knowledge-Pack\`: [verified-api-catalog.md:124–131, 179–192][kp-api], [dayz-animation-pipeline/SKILL.md:43–45][kp-animation].
- Huella de lectura de `server.py`: `B99ADEB59055F2E0FA4722DDF8EB31A544A69241CA7D1FDA8040FC7DA3DA6102`.
- Huella de lectura de `MCPBridge.c`: `2D6701F8D2FB065DBEE295932B55995F5404788F716CB4A4B41AA66CA7B80AF4`.

[minecraft-tools]: https://www.minecraft.net/en-us/creator/tools
[minecraft-ui]: https://learn.microsoft.com/en-us/minecraft/creator/documents/editoroverview
[roblox-ui]: https://create.roblox.com/docs/studio/overview
[roblox-collab]: https://create.roblox.com/docs/projects/collaboration
[roblox-mcp]: https://create.roblox.com/docs/studio/mcp
[uefn-live]: https://dev.epicgames.com/documentation/en-us/fortnite/live-edit
[uefn-sequence]: https://dev.epicgames.com/documentation/fortnite/using-cinematic-sequence-device-in-unreal-editor-for-fortnite?lang=en-US
[eden]: https://community.bistudio.com/wiki/Eden_Editor%3A_Composition
[zeus]: https://community.bistudio.com/wiki/Modules
[reforger]: https://community.bistudio.com/wiki/Arma_Reforger%3AGame_Master?useskin=vector
[rockstar-record]: https://support.rockstargames.com/articles/4gZPiqdUZD8ZhaJ81IPDJr/how-to-record-clips-and-access-the-rockstar-editor-in-gtav-on-pc
[rockstar-features]: https://www.rockstargames.com/mx/newswire/article/51974aa3a7o218/rockstar-editor-updates-coming-in-september-to-ps4-xbox
[fivem]: https://docs.fivem.net/docs/scripting-manual/nui-development/full-screen-nui/
[demand-replay]: https://www.reddit.com/r/dayz/comments/1i5sy3x/
[demand-cine]: https://www.reddit.com/r/dayz/comments/1s90x4q/looking_for_a_dayz_editor_cinematic_creator/
[demand-ai]: https://www.reddit.com/r/dayz/comments/1uw1bo8/looking_for_ai_mod_for_local_server/
[dug]: https://www.dayzunderground.com/
[twitch-guide]: https://help.twitch.tv/s/article/channel-points-guide?language=en_US
[twitch-events]: https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/#channelchannel_points_custom_reward_redemptionadd
[education]: https://education.minecraft.net/en-us/lessons/assessment-in-minecraft-education-edition-a-guide-for-teachers
[editor]: https://steamcommunity.com/sharedfiles/filedetails/?id=2250764298
[editor-license]: https://raw.githubusercontent.com/InclementDab/DayZ-Editor/master/license.md
[editor-readme]: https://raw.githubusercontent.com/InclementDab/DayZ-Editor/master/README.md
[cot]: https://steamcommunity.com/sharedfiles/filedetails/?id=1564026768
[cot-license]: https://raw.githubusercontent.com/Jacob-Mango/DayZ-CommunityOnlineTools/production/LICENSE
[vpp]: https://raw.githubusercontent.com/VanillaPlusPlus/VPP-Admin-Tools/master/README.md
[vpp-license]: https://raw.githubusercontent.com/VanillaPlusPlus/VPP-Admin-Tools/master/LICENSE
[exp-ai]: https://steamcommunity.com/sharedfiles/filedetails/?id=2792982069
[eai]: https://raw.githubusercontent.com/salutesh/DayZ-Expansion-Scripts/experimental/DayZExpansion/AI/Scripts/4_World/DayZExpansion_AI/Entities/AI/eAIBase.c
[exp-animations]: https://steamcommunity.com/sharedfiles/filedetails/?id=2793893086
[simple]: https://steamcommunity.com/sharedfiles/filedetails/?id=2547108825
[cft-integration]: https://cftools.com/help/platform/game-integration
[gamelabs-workshop]: https://steamcommunity.com/sharedfiles/filedetails/?id=2464526692&l=portuguese
[gamelabs-eula]: https://cftools.com/legal/eula
[takaro]: https://docs.takaro.io/supported-games/community/dayz/
[takaro-repo]: https://github.com/mad-001/DayZ-Takaro-Integration
[rest]: https://raw.githubusercontent.com/BohemiaInteractive/DayZ-Script-Diff/main/scripts/3_game/http/restapi.c
[game]: https://raw.githubusercontent.com/BohemiaInteractive/DayZ-Script-Diff/main/scripts/3_game/global/game.c
[emotes]: https://raw.githubusercontent.com/BohemiaInteractive/DayZ-Script-Diff/main/scripts/4_world/classes/emotemanager.c
[camera]: https://raw.githubusercontent.com/BohemiaInteractive/DayZ-Script-Diff/main/scripts/3_game/entities/camera.c
[json]: https://raw.githubusercontent.com/BohemiaInteractive/DayZ-Script-Diff/main/scripts/3_game/tools/jsonfileloader.c
[server-config]: https://community.bistudio.com/wiki/DayZ%3AServer_Configuration
[spawner]: https://community.bistudio.com/wiki/DayZ%3AObject_Spawner
[react-save]: https://reactflow.dev/examples/interaction/save-and-restore
[react-access]: https://reactflow.dev/learn/advanced-use/accessibility
[wcag-drag]: https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements
[wcag-status]: https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html
[unity-mcp]: https://raw.githubusercontent.com/CoplayDev/unity-mcp/main/README.md
[valve-director]: https://steamcdn-a.akamaihd.net/apps/valve/2009/ai_systems_of_l4d_mike_booth.pdf
[generative-agents]: https://arxiv.org/abs/2304.03442
[nvidia-ace]: https://developer.nvidia.com/ace-for-games
[mcp-security]: https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices
[owasp-injection]: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
[owasp-agency]: https://genai.owasp.org/llmrisk/llm062025-excessive-agency/
[bi-eula]: https://portal.bohemia.net/community/licenses/dayz-end-user-license
[bi-tools]: https://community.bistudio.com/wiki/DayZ%3AEnd_User_License_Agreement_for_DayZ_Tools
[bi-content]: https://portal.bohemia.net/community/game-content-usage-rules
[monetization]: https://www.bohemia.net/en/monetization
[steam-terms]: https://store.steampowered.com/subscriber_agreement/
[m-readme]: ~/Repos/dayz-mcp/README.md:65
[m-license]: ~/Repos/dayz-mcp/LICENSE:1
[m-server]: ~/Repos/dayz-mcp/tools/dayz_mcp/server.py:5618
[m-loopback]: ~/Repos/dayz-mcp/tools/dayz_mcp/loopback.py:1657
[m-knowledge]: ~/Repos/dayz-mcp/tools/dayz_mcp/knowledge.py:665
[m-bridge]: ~/Repos/dayz-mcp/addon/scripts/5_Mission/MCPBridge.c:233
[m-client]: ~/Repos/dayz-mcp/addon/scripts/5_Mission/MCPClientBridge.c:3298
[m-vehicle]: ~/Repos/dayz-mcp/addon/scripts/4_World/MCP_CarScript.c:724
[kp-api]: ~/DayZ-Modding-Knowledge-Pack/skills/enforce-script-reference/references/verified-api-catalog.md:124
[kp-animation]: ~/DayZ-Modding-Knowledge-Pack/skills/dayz-animation-pipeline/SKILL.md:45

