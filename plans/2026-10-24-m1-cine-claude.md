# Plan de M1 (cine): lane Claude

2026-10-24 · lane ciega, escrita antes de lanzar las de Codex y Grok · briefing: [`2026-10-24-m1-cine-briefing.md`](2026-10-24-m1-cine-briefing.md) · contrato: `DayZSandbox_dev/product-spec.md`, confirmado con Guillermo el 2026-10-24 sin cambios sobre el borrador con el que se escribió esta lane

Marcas: **[V]** leído en la fuente · **[I]** inferencia · **[verify]** lo decide un spike. Versiones citadas: scripts de BI en `DayZ-Script-Diff` `e8204c6` (build 1.30.164200), Expansion `0d26645` (1.9.80), dayz-mcp `f8cf3b4`.

## 1. Decisiones de arquitectura

| # | Decisión | Alternativa descartada | Por qué |
|---|---|---|---|
| AD1 | Un solo mod (servidor y cliente en el mismo PBO), sin dependencias. El código de servidor corre con `g_Game.IsServer()` y el adaptador de Expansion compila solo con `#ifdef EXPANSIONMODAI`. | Dos PBO (cliente y `-serverMod`) | En local no protege nada y duplica el empaquetado; el define de Expansion basta para cargarlo opcional [V `0_DayZExpansion_AI_Preload/Common/DayZExpansion_AI_Defines.c:3-6`]. |
| AD2 | Un solo canal HTTP: el mod de servidor hace long-poll a 127.0.0.1 con el patrón de dayz-mcp (pull, credencial en `?key=`, id de sesión por arranque, plazo por orden, lotes por tick). El cliente del director recibe sus órdenes por RPC del servidor. | Un segundo bridge HTTP en el cliente | Dos superficies para E1, y la toma tiene que coordinar servidor y cliente de todos modos. |
| AD3 | Backend y web en TypeScript (Node LTS) con npm workspaces: `app/shared` (esquema, tipos y validador Ajv), `app/server` (Fastify: API, SSE, cola y documento) y `app/web` (React + Vite). | Backend en Python reutilizando `loopback.py` | Habría dos validadores del mismo esquema (Ajv en la web, jsonschema en Python) que pueden divergir justo en A1 [I]. El MCP es M3 y habla por HTTP con cualquier backend. |
| AD4 | El documento vive en el backend: la web manda operaciones con nombre y el backend valida, guarda deshacer/rehacer y calcula el hash (JSON canónico con claves ordenadas, SHA-256). | El documento vive en la web | Duplicaría validación y estado, y M3 necesitaría otra copia. |
| AD5 | Aplicar = resetear la escena y crearla entera, en lotes por tick. | Aplicar solo las diferencias | A2 son 35 entidades; el diff es una optimización (R25), y el reset completo es lo que pide una toma repetible. |
| AD6 | Registro de propiedad en memoria del mod (escena → id lógico → entidad). Todo se crea con `ECE_NOLIFETIME \| ECE_NOPERSISTENCY_WORLD`. | Persistir y limpiar al arrancar; o `ECE_DYNAMIC_PERSISTENCY`, como el Object Spawner vanilla | A3 prohíbe tocar la persistencia, y `DYNAMIC` la activa en cuanto un jugador coge el objeto [V `3_game/ce/centraleconomy.c:30-33`, `3_game/objectspawner.c:48-53`]. Tras un reinicio no queda nada que limpiar [verify S-persist]. |
| AD7 | Observar es leer el motor (posición, inventario, `IsEmotePlaying`, pose de la cámara activa), nunca devolver lo pedido. Cada dato lleva su edad. | Confirmar con el valor pedido | Es la puerta de salida del research (consolidado §10) y lo que mide D2. |
| AD8 | El reloj de la toma vive en el juego: `take_start` llega al servidor, que lanza las órdenes de los actores y manda por RPC el camino al cliente; el cliente interpola con su reloj de frames. | Dirigir la cámara frame a frame por HTTP | Latencia y saltos (B2); el research ya lo descarta (consolidado §9). |
| AD9 | El mod da el catálogo y el mundo al conectar: clases de `CfgVehicles` con scope 2 y su base (objeto, infectado, animal), tamaño del mundo, versión del juego y modset. El backend los guarda y el validador los usa. | Catálogo escrito a mano | Se desincroniza con parches y mods, y A1 necesita "clase desconocida" y "fuera del mapa" contra el modset real [V `3_game/global/game.c:594,611`, `3_game/global/world.c:82`]. |
| AD10 | Actores detrás de una interfaz de motor del mod (`spawn`, `marks`, `behaviour`, `gesture`, `state`), con dos implementaciones en M1: Expansion y "no disponible". Personaje fijo por clase, vestuario con la API vanilla de inventario, y "en marca" y "gesto hecho" los decide Sandbox midiendo. | Usar el alta y los loadouts de Expansion | Su alta elige cara al azar (rompe B6) y sus loadouts no sirven sin Expansion (rompe C4) (nota S3, §Consecuencias). |
| AD11 | Cámara en el cliente: cámara libre para encuadrar (teclado y ratón, con tecla para guardar la pose), ir a una pose guardada, reproducir caminos con claves (posición, orientación, FOV y enfoque) interpolados en el cliente, y HUD oculto mientras la cámara de Sandbox está activa. La interpolación es propia. | Derivar de la cámara de COT | COT es CC BY-SA (derivar obliga a su licencia) y PCT no tiene licencia: se miden como referentes, no se copian. API: `Camera.SetFOV` y `SetFocus(distance, blur)` [V `3_game/entities/camera.c:67,74`]. |
| AD12 | Web: React + Vite, Dockview (núcleo MIT) para paneles y layouts, Leaflet con `CRS.Simple` sobre la imagen de Chernarus, árbol de escena como lista agrupada propia, atajos con un mapa de teclas propio, y SSE + POST. | OpenLayers y react-arborist (consolidado §6) | Para una imagen en píxeles con marcadores, Leaflet es más simple; arrastrar para reordenar el árbol no es requisito (R25). |
| AD13 | La imagen de Chernarus se genera en el PC del usuario desde su instalación (textura satélite convertida con DayZ Tools) y no se distribuye. Plan B: sombreado del relieve muestreando la altura del terreno desde el mod. | Teselas de iZurvive o xam.nu | No se pueden reutilizar (consolidado §4) [verify S-mapa]. |
| AD14 | Un mod falso en TypeScript que habla el protocolo del bridge con un mundo en memoria, solo para pruebas (A1, A4-A6, D1-D4 y E1 sin juego). El gate de cada criterio sigue siendo en partida. | Probarlo todo en partida | Cada cambio necesitaría DayZ abierto en el PC de Guillermo. |

## 2. Fases

**Orden:** F0 en paralelo con F1; después F1 → F2 → F3 → F4 → F5. El módulo de cámara de F4 puede empezar tras S-cam, en paralelo con F3.

**Convención de pruebas:** sin juego, `npm test -w app/<paquete>` (Vitest) sale 0. En partida, `node tools/ingame/<prueba>.mjs` sale 0 si PASA, 1 si FALLA y 2 si INCONCLUSO (sin juego, sin director o sin datos), y deja su evidencia en `evidence/<fecha>/<prueba>.json`. Toda prueba en partida corre en DayZServer y cliente retail, en Chernarus, con el modset fijado y bajo el lease de juego.

### F0. Spikes: matriz de capacidades

**Cumple** el gate de arranque de la Referencia de paridad y da los números de E2, E5 y A6. **Banco:** dayz-mcp, que ya tiene bridge, lease y gates; lo que falte se prueba con la parte mínima de las fichas P0 (la sonda, no la tool completa). **Salida:** `DayZSandbox_dev/decisions/<fecha>-matriz-capacidades.md`, con veredicto, números y evidencia por spike. Un FALLA en una capacidad que pide un criterio vuelve al Grill (cláusula de desafío) antes de construir esa parte; INCONCLUSO no cuenta como PASA.

| Spike | Positiva | Negativa | Alimenta | Ficha |
|---|---|---|---|---|
| S2 latencia | 100 lecturas web → juego → confirmación con p95 < 1 s en retail | backend parado con una orden en vuelo: el mod no la ejecuta pasado su plazo | E1, E2 | tools existentes |
| S3 Expansion | actor `eAI_SurvivorM_Mirek` en facción pasiva; 5 prendas leídas iguales al preset; ONCE a 20 m: < 1,5 m y quieto 10 s; gesto observado empezar y terminar; mapeo HOLD/ONCE/LOOP/ROAM; orden de carga del define | marca inalcanzable: nunca "en marca"; gesto con un infectado atacando: rechazado o agotado; sin Expansion: compila y responde `expansion_unavailable` | C1-C5 | `ai_group_spawn`, `ai_group_order`, `ai_group_state`, `actor_emote`, `loadout_apply` |
| S-cam | pose guardada y vuelta a < 0,05 m y < 0,5°; camino de 3 claves en 6 s muestreado por frame; enfoque con `SetFocus`: −30 % de varianza del laplaciano en el fondo | parar a mitad devuelve el control en < 1 s; enfoque con la opción de vídeo de DOF apagada | B1-B3, B5 | `camera_set`, `camera_path_play` |
| S-cot | el mismo camino en la cámara de COT y en PCT, medido con el mismo muestreador (`GetCurrentCameraPosition/Direction`, [V `3_game/global/game.c:731-732`]) | — | B2 (paridad) | — |
| S-hud | HUD leído oculto y captura sin barra rápida mientras la cámara está activa | al salir de la cámara, el HUD vuelve | B4 | `hud_set` |
| S-tiempo | `SetDate` y `Set` de nubes, niebla y lluvia con el clima congelado: hora ±1 min y valores leídos iguales a los pedidos durante 5 min [V `3_game/global/world.c:28,46`, `3_game/weather.c:49,387,397`] | — | B7 | tools existentes o sonda |
| S-persist | escena aplicada y servidor reiniciado: no reaparece nada | un objeto puesto a mano sobrevive al reset y al reinicio; los infectados y animales de la escena siguen ahí a los 10 min (la economía central no los retira) | A3 | — |
| S-perf | FPS de servidor con 10, 20 y 40 infectados y con 2, 4 y 8 actores | — | E5, topes de A6 | `server_perf` |
| S-mapa | imagen de Chernarus generada en local; 3 puntos leídos en partida caen a < 10 m de su sitio en la imagen | — | D5 | — |

**Riesgo:** S-cot exige instalar CF y COT en el banco (Q6).

### F1. Esqueleto, bridge y API local

**Cumple** E1, E2 y la base de D2; E3 por construcción. **Depende** del repo y de S2.

- **Repo:** `DayZSandbox/` (mod), `app/{shared,server,web}`, `tools/ingame/`, `fixtures/` y `DayZSandbox_dev/` (product-spec, CLAUDE.md, HANDOFF.md, bugs.md, `plans/`, `decisions/`).
- **Mod:** el bridge y los verbos `hello` (sesión, versión, mapa, tamaño del mundo, modset y si hay motor de actores) y `catalog`.
- **Backend:** `POST /api/ops`, `GET /api/events` (SSE), `GET /bridge/poll` y `POST /bridge/result`; cola con estados pendiente → ejecutando → aplicado → observado, o fallido / parcial; credencial local generada en el primer arranque; escucha solo en 127.0.0.1.
- **Web:** una vista de la cola con el estado y la edad de cada operación.

| Prueba | Tipo | Cómo | Salida esperada |
|---|---|---|---|
| T-E1-clave | neg | credencial mala en `/bridge/poll` y en `/api` | 401 y la cola no entrega nada · Vitest 0 |
| T-E1-sesion | neg | resultado que llega con la sesión de otro arranque | rechazado; la operación no pasa a aplicada · Vitest 0 |
| T-E1-corte | neg | backend caído con una orden en vuelo que llega tarde | el mod la descarta por plazo (log del mod) · ingame 0 |
| T-E1-bind | neg | conectar desde una IP que no es 127.0.0.1 | rechazado · script 0 |
| T-D2-desconectado | neg | pedir una operación con el bridge desconectado | pendiente y luego fallida al vencer, nunca aplicada · Vitest 0 con el mod falso; ingame 0 |
| T-E2 | pos | 100 `hello` en retail, con marcas de tiempo en los dos extremos | p95 < 1 s · ingame 0 |

### F2. Escena como documento

**Cumple** A1-A6 y D5, y D2 en aplicar y resetear. **Depende** de F1, S-persist y S-mapa; de S-perf para los topes (mientras tanto, topes provisionales marcados como tales).

- **Esquema:** `app/shared/scene.schema.json` v1 (JSON Schema 2020-12, `additionalProperties: false`), más las reglas que el esquema no expresa: clase en el catálogo y de la base correcta, dentro del mundo y dentro del presupuesto. Esbozo:

  ```json
  { "schema": "dayz-sandbox/scene", "version": 1, "id": "escena-basica-cine", "map": "chernarusplus",
    "time": { "year": 2026, "month": 6, "day": 15, "hour": 6, "minute": 30, "frozen": true },
    "weather": { "overcast": 0.2, "fog": 0.1, "rain": 0, "frozen": true },
    "entities": [
      { "id": "obj-001", "kind": "object", "class": "Land_Wreck_Volha_Police",
        "pos": { "x": 6650.0, "y": "ground", "z": 2550.0 }, "ypr": [90, 0, 0] },
      { "id": "zed-001", "kind": "infected", "class": "ZmbM_HermitSkinny_Beige",
        "pos": { "x": 6660.0, "y": "ground", "z": 2555.0 } } ] }
  ```

- **Documento en el backend:** operaciones con nombre, deshacer/rehacer, hash canónico, y guardar y cargar en `scenes/*.json`.
- **Mod:** `scene_apply` (reset, hora y clima, y el lote con ids lógicos), `scene_reset` y `scene_observe` (clase y posición leídas por id lógico). La altura `"ground"` la resuelve el mod al crear.
- **Web:** mapa, árbol, inspector generado del esquema para objetos, infectados y animales, biblioteca de plantillas (catálogo con búsqueda), y aplicar y resetear con su estado observado.

| Prueba | Tipo | Cómo | Salida esperada |
|---|---|---|---|
| T-A1-pos | pos | `fixtures/scenes/valid/escena-basica-cine.json` (sin actores hasta F3) | válida · Vitest 0 |
| T-A1-neg ×5 | neg | clase desconocida, fuera del mapa, presupuesto excedido, campo extra y versión errónea | cada una rechazada con su ruta JSON (`/entities/3/class`, …); el mod falso no recibe ninguna orden · Vitest 0 |
| T-A2 | pos | aplicar en partida | conteos exactos por clase; posición leída a < 0,5 m · ingame 0 |
| T-A3 | neg | un objeto puesto a mano al lado; reset | el objeto sigue y la escena queda a 0 · ingame 0 |
| T-A3-reinicio | neg | aplicar y reiniciar el servidor | no reaparece nada de la escena · ingame 0 |
| T-A4 | pos | guardar, parar el backend, cargar y aplicar | mismos conteos y posiciones a < 0,5 m; sin cambios, mismo hash · ingame 0 y Vitest 0 |
| T-A5 | pos | 20 operaciones; deshacer 20; rehacer 20 | hash inicial y hash final · Vitest 0 |
| T-A6 | neg | escena por encima del tope | rechazada antes del mod; la web muestra el uso frente al tope · Vitest 0 y Playwright 0 |
| T-D5 | pos | colocar por clic con `"ground"` | altura leída a < 0,2 m del suelo · ingame 0 |

### F3. Actores NPC con Expansion como adaptador

**Cumple** C1, C2, C3, C5 y la parte de C4 que cabe en M1. **Depende** de F2 y de S3 en partida.

- **Esquema:** `kind: "actor"` con `character` (nombre vanilla, p. ej. `SurvivorM_Mirek`), `wardrobe` (id de preset), `marks`, `behaviour` (HOLD, ONCE, LOOP o ROAM) y `gestures` (id del catálogo vanilla de emotes, con su instante).
- **Biblioteca:** presets de vestuario como documentos (clases por ranura).
- **Mod:** la interfaz de motor de actores y la implementación de Expansion bajo `#ifdef EXPANSIONMODAI`: clase `eAI_Survivor{M,F}_<Nombre>`, grupo en facción pasiva, marcas y comportamiento mapeados, y gesto con `Expansion_SetEmote`. Estado observado `en_marca` (a < 1,5 m y quieto) y del gesto (iniciado, terminado, rechazado o agotado), leyendo `EmoteManager.IsEmotePlaying` [V `4_world/classes/emotemanager.c:1328`].
- **Backend:** si `hello` dice que no hay motor de actores, una escena con actores se rechaza entera con `expansion_unavailable` antes de mandar nada.
- **Web:** inspector de actor (personaje, vestuario, marcas sobre el mapa, comportamiento y gestos).

| Prueba | Tipo | Cómo | Salida esperada |
|---|---|---|---|
| T-C1 | pos | preset de 5 prendas | multiconjunto leído = preset · ingame 0 |
| T-C2 | pos | ONCE a una marca a 20 m | a < 1,5 m y < 0,5 m de movimiento en 10 s · ingame 0 |
| T-C2-inalcanzable | neg | marca dentro de una roca o en el mar | tras el tiempo límite, `no_alcanzada`, nunca `en_marca` · ingame 0 |
| T-C3 | pos | gesto | iniciado y después terminado · ingame 0 |
| T-C3-combate | neg | gesto con un infectado atacando | rechazado o agotado, nunca terminado · ingame 0 |
| T-C4-documento | pos | el esquema y las fixtures no contienen clases `eAI_`, enums ni nombres de Expansion | Vitest 0 |
| T-C5 | neg | servidor sin Expansion y escena con actores | rechazo entero con `expansion_unavailable`; el mod no recibe ninguna orden · ingame 0 y Vitest 0 |

**Riesgo:** una amenaza corta el recorrido de marcas (`eaistate_traversingwaypoints.c:269`); la facción pasiva cubre infectados y animales, no jugadores.

### F4. Rodaje: cámaras, caminos y tomas

**Cumple** B1-B7. **Depende** de F3 (actores en la toma) y de S-cam, S-hud y S-tiempo.

- **Cliente:** cámara libre para encuadrar con tecla de guardar pose; ir a una pose; reproducir un camino (claves con tiempo, posición, orientación, FOV y enfoque, con interpolación suave propia [I: Catmull-Rom en la posición y slerp en la orientación]); muestreador de pose por frame que entrega las muestras al acabar; HUD oculto mientras está activa; parar.
- **Servidor:** `take_start` (hora y clima del documento con lectura de vuelta, órdenes de los actores con su instante y RPC del camino al director) y `take_stop`. El director es el jugador conectado con el mod; sin él, `no_director`.
- **Web:** panel de cámaras (guardar desde el juego, ir a una pose), editor de camino (lista de claves con tiempo, y añadir la pose actual como clave) y panel de toma (rodar, parar, estado y edad).

| Prueba | Tipo | Cómo | Salida esperada |
|---|---|---|---|
| T-B1 | pos | guardar pose, moverse y volver | a < 0,05 m y < 0,5° · ingame 0 |
| T-B2 | pos | camino de 3 claves en 6 s | muestras a < 0,5 m; fin entre 6,0 y 6,3 s; pose final a < 0,05 m y < 0,5°; ningún paso mayor que 3 veces la mediana; tabla junto a COT y PCT · ingame 0 |
| T-B3 | pos | actor a 2 m y fondo a 50 m | varianza del laplaciano del recorte del fondo −30 % · script de captura 0 [verify] |
| T-B4 | pos | HUD durante toda la toma | oculto en todas las muestras; capturas sin barra rápida · ingame 0 |
| T-B5 | pos | parar a mitad | control devuelto en < 1 s; la escena sigue aplicada · ingame 0 |
| T-B5-sin-director | neg | rodar sin director conectado | `no_director` y no arranca nada · ingame 0 |
| T-B6 | pos | 3 tomas con reset entre ellas | mismos conteos; actores a < 1,5 m de su marca; vestuario y personaje idénticos; camino a < 0,5 m en los mismos instantes · ingame 0 |
| T-B7 | pos | empezar una toma | hora ±1 min y clima leído igual al pedido · ingame 0 |

Las capturas de B3 y B4 las toma un script de pruebas (captura de ventana u OBS), no el producto, porque `MakeScreenshot` está roto (consolidado §5).

### F5. Web completa y aceptación de M1

**Cumple** D1, D3, D4, E3, E4, E5 y los topes finales de A6 (D2 y D5 llegan de F1 y F2). **Depende** de F1-F4.

- Layouts con Dockview guardados en el backend por perfil local, no solo en el navegador (consolidado §2, "Qué evitar").
- Atajos reasignables y alternativa al arrastre: mover desde el inspector y con el teclado.
- La batería completa en retail y en Diag, y la medida de E5 con la escena al tope.

| Prueba | Tipo | Cómo | Salida esperada |
|---|---|---|---|
| T-D1 | pos | Playwright: preparar, aplicar, rodar, resetear y recargar sin abrir ningún editor de JSON | 0 |
| T-D3 | pos | mover paneles y recargar la página | mismo layout · Playwright 0 |
| T-D4 | pos | el flujo solo con teclado; reasignar el atajo de rodar y usarlo | Playwright 0 |
| T-E3 | pos | T-D1 sin proceso MCP ni variables de LLM | 0 |
| T-E4 | pos | toda la batería en DayZServer retail, y también en Diag | 0 en los dos |
| T-E5 | pos | escena al tope durante 10 min | FPS de servidor por encima del umbral fijado en S-perf · ingame 0 |

## 3. Trazabilidad

| Criterio | Fase | Pruebas |
|---|---|---|
| A1 | F2 | T-A1-pos, T-A1-neg ×5 |
| A2 | F2 | T-A2 |
| A3 | F2 (S-persist) | T-A3, T-A3-reinicio |
| A4 | F2 | T-A4 |
| A5 | F2 | T-A5 |
| A6 | F2; topes en F5 (S-perf) | T-A6, T-E5 |
| B1-B7 | F4 (S-cam, S-cot, S-hud, S-tiempo) | T-B1 a T-B7 |
| C1-C3, C5 | F3 (S3) | T-C1 a T-C5 |
| C4 | F3 el documento; la IA propia, en M2 | T-C4-documento |
| D1, D3, D4 | F5 | T-D1, T-D3, T-D4 |
| D2 | F1 y cada fase | T-D2-desconectado |
| D5 | F2 (S-mapa) | T-D5 |
| E1 | F1 | T-E1-* |
| E2 | F1 (S2) | T-E2 |
| E3 | F1 por construcción; F5 | T-E3 |
| E4 | cada prueba en partida; F5 | T-E4 |
| E5 | F5 (S-perf) | T-E5 |

## 4. Cláusula de desafío

1. **Falta un criterio: mismo personaje en cada toma.** B6 pide vestuario idéntico, pero el alta de Expansion cambia la cara en cada toma (nota S3). Propongo añadir "misma clase de personaje" a B6 y a C1.
2. **Falta un criterio: de dónde sale la pose de B1.** Sin cámara libre no hay forma de encuadrar en retail, y la freecam de diag congela la simulación (consolidado §5). Propongo decir en B1 que la pose se guarda desde una cámara libre en el juego.
3. **Camino más simple: sin segundo cliente en M1.** El research pedía dos clientes cuando los actores eran jugadores; con NPC, el único cliente es el del director.
4. **Camino más simple: aplicar = reset y crear todo** (AD5). Cumple A2-A4 igual y evita el diff.
5. **Choque con el Intent: C4 no se puede cerrar en M1**, porque necesita la IA propia. En M1 solo se prueba que el documento no depende de Expansion. Propongo marcar C4 como "M1 parcial, cierre en M2".
6. **D3 dice "por usuario"** en un producto local de un solo usuario. Propongo "por perfil local", con layouts con nombre.
7. **B3 puede depender de la opción de vídeo de profundidad de campo** (ya marcado `[verify]`). Si en retail no se puede forzar, propongo "con la opción activada" o sacar B3 de M1.
8. **Riesgo sin criterio: el cuerpo del director** puede salir en plano o recibir ataques de infectados durante la toma (Q5).
9. **A3 por construcción:** con `ECE_NOPERSISTENCY_WORLD` la escena nunca entra en la persistencia, aunque el servidor sea el de pruebas habitual (Q7).

## 5. Preguntas para el Grill Modo B, con mi recomendación

- **Q1.** ¿Backend en TypeScript (AD3)? → Sí: un solo validador para la web y el backend.
- **Q2.** ¿Encuadras volando la cámara dentro del juego (AD11)? → Sí, y se escribe en B1.
- **Q3.** ¿Añadimos "mismo personaje" a B6 y a C1? → Sí.
- **Q4.** ¿Quitamos el segundo cliente de M1? → Sí.
- **Q5.** ¿Qué hacemos con el cuerpo del director durante la toma? → Modo dios solo durante la toma [I: `SetAllowDamage(false)` en su jugador]. Hacerlo invisible queda fuera de M1 (ficha P2 `players_visibility`); mientras, el director deja su cuerpo fuera de plano.
- **Q6.** ¿Medimos COT y PCT en una instancia de banco aparte, con CF y COT? → Sí, como pide la Referencia de paridad.
- **Q7.** ¿Sandbox corre en una instancia propia de DayZServer (perfil y misión suyos) o en tu servidor de pruebas? → Instancia propia: aísla la persistencia y los mods del resto de tus pruebas.

## 6. Fuera de este plan

- **M2 y M3:** la IA propia y C6, el cambio de mapa (G1), licencias y Bohemia (F1-F3), y la fachada MCP con la IA (H1-H2).
- **Del research, sin criterio en el spec (R25):** temas por tokens CSS, superficie de botones tipo Companion y overlay, adaptador de OBS (empezar y parar la grabación con la toma), director determinista, compensar acciones ejecutadas más allá del reset, instalador, HTTPS y varios usuarios.

## 7. Reparto y cierre de cada fase

- Implementa Grok, con Opus de reserva; revisa ChatGPT Sol sobre el commit congelado (R21, otra familia); lo mecánico (fixtures, catálogos y tests repetitivos), al GX10 según su skill. Las pruebas en partida corren en el PC de Guillermo bajo el lease de juego.
- Una fase se cierra con sus pruebas en 0, la evidencia guardada, el test del senior engineer (R25) y cada línea cambiada trazada a este plan (R20). Lo que aparezca fuera va a `bugs.md`.
