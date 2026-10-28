# product-spec.md — DayZ Sandbox

> **Definición de Producto Final (DPF)** — el contrato de "qué es terminado".
> Lo lee toda sesión al entrar (referenciado desde `CLAUDE.md`). Es el target estable;
> el progreso vivo va en handoffs (`30_Sessions/`) y `HANDOFF.md`, NO aquí.
> Se cierra/actualiza con el Grill de producto (workflow.md §"Grill — Modo A").
> Cambiar el alcance = entrada en el Changelog, no deriva silenciosa.

**Estado: CONFIRMADO con Guillermo el 2026-10-24 (Grill Modo A).** Sale del research fase 0 (`research/2026-10-23-dayz-sandbox-consolidado.md`) y de sus decisiones del 2026-10-23 (consolidado §11).

## Qué es "terminado" (alcance acordado)

DayZ Sandbox es un estudio local de escenas para DayZ: desde el navegador, un creador prepara, aplica, rueda, resetea y repite escenas en un servidor que corre en su PC, sin tocar JSON ni scripts. El producto final es standalone: un mod gratuito (servidor + cliente) y una app web con su backend local, sin depender de mods de terceros. Prioridad: cine/machinima.

- **M1 — MVP de cine (Chernarus; Expansion AI como adaptador opcional para los NPC):**
  1. Escena como documento versionado: objetos, infectados, animales, actores NPC con vestuario, marcas y gestos, hora y clima. Guardar, cargar, aplicar, resetear y repetir sin tocar nada ajeno.
  2. Rodaje: cámaras guardadas y caminos de cámara con claves (posición, orientación, FOV y enfoque), sin HUD. Una toma lanza a la vez cámara y actores, y se puede parar.
  3. Web: mapa 2D, árbol de escena, inspector, biblioteca de plantillas (objetos, vestuario, gestos), cola con estados observados y layouts personalizables.
  4. Todo local y funcionando con el MCP apagado.
- **M2 — Standalone:** IA propia de cine en lugar de Expansion: una "marioneta de ruta" (el actor recorre una ruta con tiempos, trazada en el mapa o grabada del pase del creador, igual en cada toma), más ir a marca y gesto, con las mismas escenas guardadas; cambio de mapa con reinicio de sesión entre los mapas instalados.
- **M3 — IA opcional:** fachada MCP sobre la misma API, para que una IA proponga y coordine piezas y escenas siempre con aprobación humana.

Supuestos confirmados el 2026-10-24: M1 es para uso propio (sin instalador); las tomas se graban con OBS u otra herramienta externa; eventos/RP queda fuera de esta versión.

## Cláusula de desafío (el criterio sirve a la intención)

Cada criterio de aceptación de abajo es la forma *verificable* de una **intención** (el `Intent` declarado en su sección). El criterio binario es el gate de aceptación y **no se cumple a la letra rompiendo el espíritu**. Si al planificar o implementar una fase detectas que:

- (a) un criterio **choca** con su `Intent`,
- (b) hay un camino **más simple** que satisface el `Intent` igual o mejor, o
- (c) el `Intent` revela un **criterio que falta**,

estás **obligado** a surfacearlo en el **Grill de plan (Modo B)** ANTES de implementar — no como justificación a posteriori. El usuario adjudica; todo cambio de criterio se anota en el *Changelog de alcance*. La intención **no sustituye** al criterio binario: lo explica y autoriza a renegociarlo con visto bueno.

## Criterios de aceptación verificables (R26)

> Estado: ✓ hecho · ⏳ en curso · ❓ sin empezar · [verify] correcto offline, falta validación final.
> Salvo que se diga otra cosa, cada criterio se mide en DayZServer y cliente retail (no solo DayZDiag), en Chernarus y con el modset fijado.

### A — Escena como documento (M1)

> **Intent**: el creador describe una escena una vez y puede aplicarla, resetearla y recargarla idéntica; nada fuera de la escena se toca.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| A1 | Documento de escena versionado con JSON Schema publicado; 5 fixtures inválidas (clase desconocida, fuera del mapa, presupuesto excedido, campo extra, versión errónea) se rechazan con la ruta JSON del error | Test del backend con fixtures pos y neg (exit 0); el log del bridge no recibe ninguna orden de las inválidas | ❓ |
| A2 | Aplicar `escena-basica-cine.json` (20 objetos, 10 infectados, 3 animales, 2 actores NPC con vestuario) da conteos exactos por clase y error de posición < 0,5 m | Lectura en servidor de las entidades registradas en la escena; infectados y animales, en un checkpoint al crearlos y antes de soltar su IA | ❓ |
| A3 | Reset: borra el 100 % de lo suyo y nada ajeno; nunca toca la persistencia `[intent: el riesgo crítico del research es borrar lo ajeno]` | Fixture negativa: un objeto colocado a mano sobrevive; conteos antes y después | ❓ |
| A4 | Recargar: guardar, cerrar, cargar y aplicar repite los conteos y las posiciones (< 0,5 m); sin cambios, el documento guardado conserva el hash | Test E2E de ida y vuelta | ❓ |
| A5 | Deshacer y rehacer del documento como transacciones con nombre: deshacer 20 operaciones devuelve el hash inicial y rehacerlas, el final | Test del backend | ❓ |
| A6 | Presupuestos con tope duro: una escena que lo excede se rechaza antes de llegar al juego y la web muestra el uso frente al tope | Fixture negativa; los topes salen de medir E5 | ❓ |

### B — Rodaje: cámaras y tomas (M1)

> **Intent**: planos repetibles y limpios, sin HUD, con movimientos de cámara suaves dirigidos desde la web.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| B1 | La pose sale de una cámara libre mínima dentro del juego (mover, mirar y velocidad; sin cámara editorial completa). Guardar esa pose y volver a ella: error < 0,05 m y < 0,5° | Lectura de la cámara en el cliente | ❓ |
| B2 | Camino de 3 claves en 6 s: posiciones muestreadas a < 0,5 m de las esperadas; termina entre 6,0 y 6,3 s; pose final igual a la última clave (< 0,05 m, < 0,5°); sin saltos: ningún paso entre frames consecutivos supera 3 veces la mediana | Muestreo de la pose en el cliente; misma prueba contra la cámara de COT (referencia de paridad) | ❓ |
| B3 | Enfoque por cámara y por clave: con el actor a 2 m y el fondo a 50 m, el desenfoque del fondo baja al menos un 30 % la varianza del laplaciano frente a sin desenfoque | Captura y medida sobre un recorte del fondo, con la opción de vídeo de profundidad de campo activada; la web avisa si está apagada `[verify]`: si ni con la opción activada el juego desenfoca, B3 sale de M1 con una entrada en el Changelog | ❓ |
| B4 | Sin HUD durante toda la toma | Estado del HUD leído en el cliente y capturas sin barra rápida | ❓ |
| B5 | Una toma arranca cámara y actores a la vez y se puede parar: parar devuelve el control en < 1 s y deja la escena coherente. "A la vez" quiere decir que cámara y actores reciben su orden en el mismo tick del servidor; el desfase real de cada actor se mide, se muestra en la web y varía ≤ 100 ms entre las tomas de B6 | Test en partida con parada a mitad; desfase de cada actor medido en cada toma | ❓ |
| B6 | Repetibilidad: 3 tomas con reset entre ellas dan los mismos conteos, el mismo personaje en cada actor, actores en su marca (< 1,5 m), vestuario idéntico y camino a < 0,5 m en los mismos instantes | Test en partida con las 3 tomas; infectados y animales se cuentan en un checkpoint al crearlos y no se les exige repetir trayectoria | ❓ |
| B7 | Cada toma arranca con la hora y el clima del documento (hora leída ±1 min; cada valor de clima leído a ±0,01 del pedido) | Lectura en servidor al empezar la toma, del valor actual del clima y no del previsto | ❓ |

### C — Actores NPC (M1 con Expansion, M2 con IA propia)

> **Intent**: un creador solo tiene reparto: con una cuenta de Steam hay un solo cliente, así que el resto de actores son NPC que se visten, van a su marca y actúan. Cambiar de motor de IA no cambia las escenas guardadas.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| C1 | Personaje y vestuario: el actor es el personaje del preset (la misma clase de superviviente cada vez que se aplica) y su equipo leído es el del preset (mismo multiconjunto de clases) | Lectura en servidor | ❓ |
| C2 | Ir a marca: llega a < 1,5 m y se queda quieto (< 0,5 m en 10 s) | Lectura de posición en servidor | ❓ |
| C3 | Gesto: se observa que empieza y termina; si no puede, el estado es rechazado o agotado, nunca terminado | Estado observado del gesto, con fixture negativa (actor en combate) | ❓ |
| C4 | El documento usa un vocabulario propio de comportamiento (HOLD, ONCE, LOOP, ROAM; HOLD es quieto observable y ROAM es deambular sin salir de un radio de su posición inicial, que fija el spike de Expansion): la misma escena da C1-C3 con Expansion (M1) y con la IA propia (M2) | La misma fixture contra los dos motores | ❓ |
| C5 | Sin Expansion cargado en M1, una escena con actores se rechaza entera (`expansion_unavailable`) antes de aplicar nada | Fixture negativa | ❓ |
| C6 | M2: sin Expansion, la IA propia cumple C1-C3 y recorre por navmesh una ruta con tiempos entre marcas (trazada o grabada del pase del creador) de forma repetible: en 3 tomas con reset pasa por sus puntos de control a < 1 m. Puerta: los probes de locomoción de supervivientes de servidor (ficha 15) y de ruta (ficha 14) pasan antes de construirla; si fallan, M2 se replantea en un Grill | Test en partida `[verify]`: la locomoción de supervivientes de servidor no está probada | ❓ |

### D — Web e interfaz (M1)

> **Intent**: intuitiva y personalizable; el creador nunca edita JSON y siempre sabe qué está aplicado de verdad.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| D1 | El flujo completo (preparar, aplicar, rodar, resetear, recargar) se hace desde el navegador sin editar JSON | Test E2E (Playwright) que no abre ningún editor de JSON | ❓ |
| D2 | Cada operación muestra su estado observado (pendiente, ejecutando, aplicado, observado, fallido, parcial) y la edad del dato; nada pendiente aparece como hecho | Test con el bridge desconectado: la operación queda pendiente o fallida, nunca aplicada | ❓ |
| D3 | Layout personalizable: paneles movibles, guardados por usuario y restaurados al recargar la página | Test E2E | ❓ |
| D4 | Las acciones principales (colocar, aplicar, toma, parar) tienen atajo reasignable y alternativa al arrastre | Test E2E solo con teclado | ❓ |
| D5 | Mapa 2D de Chernarus con imagen propia (sin teselas de iZurvive ni xam.nu); colocar por clic con ajuste al suelo | Revisión de licencias de la imagen; el punto de contacto de la plantilla colocada queda a < 0,2 m del terreno (puentes y tejados, fuera de M1) | ❓ |

### E — Local y robusto (M1)

> **Intent**: todo corre en el PC del creador sin abrir la administración del servidor a nadie, y lo que se pide al juego llega rápido y comprobado.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| E1 | Bridge y API solo en 127.0.0.1 y con credencial; credencial inválida, sesión equivocada o conexión perdida no ejecutan órdenes | Fixtures negativas | ❓ |
| E2 | Latencia web → juego → confirmación con p95 < 1 s en local (N = 100) | Medida del navegador a la confirmación observada en el juego, con una mezcla fija de 100 operaciones cortas (25 lecturas del servidor, 25 consultas de suelo, 25 cambios de pose de la cámara y 25 cambios de ambiente); los timeouts cuentan | ❓ |
| E3 | Todo A-D funciona con el MCP apagado y sin LLM | Test E2E sin el proceso MCP | ❓ |
| E4 | A-D pasan en DayZServer retail, no solo en DayZDiag | Mismo test en las dos builds | ❓ |
| E5 | FPS de servidor por encima del umbral con el presupuesto máximo. La métrica se fija antes de medir: FPS medio del servidor por ventana de 60 s, con suelo provisional > 35 | Medida en servidor; el umbral definitivo y los topes de A6 salen de aquí | ❓ |

### F — Standalone y licencias (M2)

> **Intent**: el producto final se puede distribuir, y la app se puede vender, sin incumplir ninguna licencia.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| F1 | Expediente de licencias por componente; el núcleo no contiene código copiado de Expansion, COT, VPP, DayZ Editor ni de los scripts de BI | Auditoría de licencias y de procedencia del código | ❓ |
| F2 | El producto final pasa A-E sin Expansion ni otros mods de terceros | Test con solo los mods propios | ❓ |
| F3 | El mod se publica gratis y la app con su backend se instala aparte; Bohemia ha confirmado el modelo antes de cobrar `[intent: el EULA de DayZ Tools impide explotar comercialmente lo creado con ellas]` | Confirmación escrita de Bohemia archivada | ❓ |

### G — Mapas (M2)

> **Intent**: cargar distintos mapas, sabiendo que en DayZ cambiar de mapa reinicia la sesión.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| G1 | Cambiar de mapa desde la web avisa del reinicio, arranca la misión correcta y aplica la escena del mapa nuevo | Test en partida con dos mapas instalados `[verify]` | ❓ |

### H — IA opcional y MCP (M3)

> **Intent**: una IA puede proponer y coordinar escenas, pero nunca ejecuta sin aprobación humana y el producto no depende de ella.

| # | Criterio | Cómo se verifica | Estado |
|---|----------|------------------|--------|
| H1 | Fachada MCP sobre la misma API (validar, planificar, enviar, aplicar, estado); aplicar exige aprobación en la web ligada al hash del plan | Fixture negativa: una propuesta sin aprobar no llega al juego | ❓ |
| H2 | Primera IA útil: "prepara una escena con dos supervivientes y una cámara al amanecer" produce un borrador válido y editable, sin ejecutarlo | Test con el borrador validado por A1 | ❓ |

## Fuera de alcance (explícito) — R25

- Replay completo con cámara libre a posteriori: es otro proyecto.
- Grabar vídeo dentro del producto: se graba con OBS u otra herramienta.
- Cambiar de mapa sin reiniciar la sesión, y editar el terreno.
- Animaciones propias o arbitrarias: solo el catálogo vanilla de gestos (un solo mod de animaciones a la vez).
- NPC conversacionales con LLM persistente.
- IA autónoma de actores (combate, decisiones propias) en M2: M2 se queda en la marioneta de ruta; la IA autónoma se reabre después con un Grill.
- Servidor alojado multiusuario, control de audiencia y streamers.
- Varios directores editando a la vez.
- Viewport 3D en la web.
- Monetizar servidores o dar ventajas de gameplay.
- Eventos y roleplay (patrullas exportables al JSON de Expansion, edición invisible a jugadores): fuera de esta versión; se reabre con un Grill Modo A.

## Referencia de paridad (PREREQUISITO si existe referente) — LL-030

- Referencia:
  - **Cámara de cine:** cámara cinematográfica de COT (CC BY-SA 4.0) y PCT (solo cliente). Son dos referentes, así que B1-B3 se miden contra los dos.
  - **Editor de escena:** Eden de Arma 3 y DayZ Editor, más la tabla "se da por hecho" del research (consolidado §2).
  - **NPC:** Expansion AI, que además es el motor de M1.
  - **Bridge:** dayz-mcp (bridge pull, lease, allowlist en la entrada, deadman con TTL, verbos medidos).
- Anatomía extraída:
  - Cámara (COT y PCT): waypoints con posición, orientación y FOV; duración o velocidad por tramo; easing; Catmull-Rom; shake; rutas guardadas en JSON; reproducir y parar; DOF (PCT: focal 8-400 mm y apertura). Medible en B1-B3.
  - Editor (Eden y §2): catálogo buscable, selección múltiple, mover y rotar con rejilla y ajuste al suelo, plantillas que guardan atributos e inventario, deshacer como transacciones, hora y clima en vivo, presupuestos con tope duro, probar y volver al estado inicial, guardar, versionar y exportar, espacio de trabajo personalizable. Medible en A y D.
  - NPC (Expansion): facciones, 12 formaciones, waypoints con comportamiento, loadouts en JSON y emotes que esperan a la FSM. Rendimiento: FPS de servidor > 60 máx. y > 35 medio; más de 30 IA degradan. Medible en C y E5.
  - Bridge (dayz-mcp): error de posición 0,0313 m frente a una marca independiente (umbral < 0,5 m); /poll retenido 600 ms con 4741 ticks en vuelo. Base de A2 y E2.
- Estado de extracción: hecha a nivel de funciones el 2026-10-23 (research §2 y anexos B y C). **Pendiente y gate de arranque:** medir en partida la cámara de COT (B2) y verificar la API de Expansion en la versión fijada (spike S3). Se puede hacer ya: no necesita que Sandbox exista.

## Changelog de alcance

- 2026-10-23 — alcance inicial propuesto tras el research fase 0 y las decisiones de Guillermo (cine/machinima prioritario, local, uso comercial, Expansion en M1 con IA propia como meta, Chernarus). **Pendiente de confirmar en el Grill Modo A.**
- 2026-10-24 — **confirmado con Guillermo** sin cambios (tarjeta del Grill Modo A, opción "Ciérralo así"), con sus tres supuestos: uso propio sin instalador, grabación con OBS fuera del producto y eventos/RP fuera de esta versión.
- 2026-10-26 — **Grill Modo B del plan de M1** con Guillermo (tarjeta "Ciérralo así"; preguntas y porqués en `plans/2026-10-24-m1-cine-v1.md` §5 y §6). No entra ni sale ningún criterio. Cambian estos textos: B1 dice de dónde sale la pose, una cámara libre mínima dentro del juego (Q2); B6 y C1 piden el mismo personaje en cada toma (Q3); B5 define "a la vez" (Q4); B3 se mide con la profundidad de campo activada y sale de M1 si ni así desenfoca (Q5); y A2, B6, B7, C4, D5, E2 y E5 aclaran cómo se miden (Q9).
- 2026-10-27 — **C6 reorientado a "marioneta de ruta"** con el visto bueno de Guillermo en el hilo del council post-v1 (`backlog-post-v1.md`, T17; votos en `reviews/2026-10-27-council-post-v1/`). Cambian el texto de M2 y C6: la IA propia de M2 es una ruta con tiempos repetible (trazada o grabada del pase del creador), con los probes de las fichas 14 y 15 como puerta; la IA autónoma pasa a Fuera de alcance. C4 no cambia: el vocabulario HOLD, ONCE, LOOP y ROAM debe dar lo mismo con los dos motores. No afecta a M1 ni a F0.
