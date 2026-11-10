# S-track·1: calibración de la imagen, lectura del arma y hook de la cámara

2026-11-10 · spec de implementación (R25/R26) de la primera corrida de la sonda S-track del [plan de cámara que sigue objetos](2026-11-10-camara-sigue-objetos.md) v0.3 (commit `62ebc89`) · v1.0.

Guillermo dio el visto bueno para correr la prueba en partida y calibrar el 2026-11-10 a las 18:07Z («ok probamos y calibramos con ello»).

## 0. Qué es y qué no

**Es** la primera corrida, que deja decidido lo que más pesa:
- la calibración de la referencia por imagen (plan §4.1);
- qué lectura de la pose del arma coincide con lo que se dibuja (T-lect);
- en qué hook tiene que vivir la cámara de cada modo (T-hook).

Lleva sus negativas.

**No es** T-ropa, T-red, T-suave, el coche, el actor de IA ni los criterios K: todo eso queda para S-track·2. Tampoco es código del producto.

**Cambios frente al plan** (R20; motivo en cada uno, y se anotan en la v0.4 del plan):
- **El banco es el de dayz-mcp, no el de F0.** La sonda de F0.2 no llegó a `main`. Se usa el banco de dayz-mcp en una instancia aislada, como la `perf`. LIVE y T130 no se tocan.
- **El portador es el jugador local, no un actor de IA.** T-lect y T-hook no dependen de la red, y el jugador local se puede mover sin teclado con `player_move` de dayz-mcp (`addon/scripts/4_World/MCP_PlayerMove.c`). El actor de IA, que sí es una réplica, va a T-red en S-track·2.
- **Los dos detalles de la imagen son `usti hlavne` y `konec hlavne`** (boca y recámara del arma), no la mira. No hace falta montar una mira y están a más de 200 px en pantalla con los montajes de §2.
- **Captura con `MakeScreenshot`, con el cliente arrancado con `-autotest`.** Está medido en dayz-mcp el 2026-11-03: escribe un BMP del frame compuesto en la siguiente actualización de script (`README.md:167`). Se captura uno de cada 10 frames.
  - Qué frame muestra cada BMP no se supone: lo fija la calibración (§3).
  - Si la calibración no da un desfase constante, se pasa a grabar la ventana con el código de frame pintado en pantalla (plan §4.1), en una segunda corrida.

## 1. El mod de la sonda: `DayZSandbox_dev/qa/strack/DZS_STrack/`

Un solo PBO de cliente y servidor, que se carga junto al bridge de dayz-mcp.

**Servidor.** Al conectar el jugador:
- un `M4A1` en las manos (`CreateInHands`, `humaninventory.c:44`);
- hora fija a las 12:00 y clima despejado.

**Cliente.**
- Una `Camera` de script propia.
- Un escenario que se arranca con la línea `-strack=<caso>` del cliente y escribe en `$profile:strack/<run>/`.
- El número de frame es un contador que solo sube en `MissionGameplay.OnUpdate`.
- **Los tres hooks**, cada uno escribiendo la cámara:
  - **H-a:** `MissionGameplay.OnUpdate`, después del `super`.
  - **H-b:** `EOnPostFrame` de una entidad propia que solo existe en el cliente. Las llamadas que se repitan en un mismo frame se registran todas, pero la cámara se escribe una sola vez por frame.
  - **H-c:** `AddChild(camera, -1)` sobre el arma, con la pose local fijada una vez. Solo sirve para `mount` rígido. Al terminar se suelta con `RemoveChild(camera, true)`.
- **Las seis lecturas de T-lect**, en cada frame y sobre los dos puntos:
  - (a) `arma.ModelToWorld(arma.GetMemoryPointPos(p))`;
  - (b) `arma.GetSelectionPositionWS(p)`;
  - (c) `jugador.ModelToWorld(arma.GetSelectionPositionMS(p))`;
  - (d) el hueso `RightHand_Dummy` (ausente solo si es `-1`) compuesto con la relación arma-hueso del primer frame;
  - (e) `GetRenderTransform` del arma por el punto en espacio de modelo;
  - (f) `GetWorldPosition` del arma más la orientación de `GetTransform`, por el punto.
- **Muestras JSONL**, una línea por frame y hook: `frame`, `t_ms`, `dt`, `hook`, `invocaciones_en_frame`, las lecturas (a) a (f) de los dos puntos, la pose de cámara escrita (posición y los tres ejes), `fov`, `shot` (nombre del BMP o vacío) y `caso`.
- **Inyecciones**, con `-strack_inject=` y una por corrida:
  - `delay1`: la cámara usa la entrada del frame anterior;
  - `roll`: 1° de giro sobre el eje óptico.

Tamaño orientativo: menos de 600 líneas de Enforce. Sin dependencias fuera de vanilla.

## 2. Casos

Cada caso dura 3 tandas de: andar 3 s, girar 180° en el sitio y andar 3 s. El orquestador lo mueve con `player_move` de dayz-mcp, con el arma bajada. FOV de 60° y 1920×1080.

| Caso | Cámara | Hooks |
|---|---|---|
| `calib` | Fija a 3 m del jugador. Gira la cámara 10° a la derecha en los frames pares y la devuelve en los impares, durante 200 frames, capturando en cada uno. | H-a y H-b, por separado |
| `mount0` | `mount` rígido, offset 0,6 m a la derecha y 0,1 m arriba del marco de `usti hlavne`, mirando a la recámara | H-a, H-b y H-c |
| `mount03` | Como `mount0`, con `smooth_s` 0,3 (slerp propia, plan §3.3) | H-a y H-b |
| `lookat` | Fija a 4 m, mirando a `usti hlavne` | H-a y H-b |
| `follow` | 2 m detrás y 0,5 m arriba del ancla, girada con su rumbo | H-a y H-b |

Las negativas son las mismas corridas con `delay1` (los casos `mount0` y `lookat`, en cada hook) y con `roll` (`mount0`, con H-a).

## 3. El evaluador: `DayZSandbox_dev/qa/strack/s_track_eval.py`

Usa Python con numpy y Pillow, solo en `qa/strack/`, que tiene su propio `requirements.txt`. La regla de solo stdlib sigue valiendo para el resto de `qa/`; si `test_stdlib_only.py` mira también esta carpeta, se le añade la excepción, con el motivo en un comentario.

**Calibración (`calib`):**
- Para cada BMP del frame n se mide el giro de la imagen frente a la imagen de referencia, por correlación horizontal de bandas.
- Se busca el desfase k ∈ {−2, …, 2} con el que el giro de la imagen coincide con el escrito en el frame n + k en ≥ 99 % de los BMP.
- Si no hay un único k que lo cumpla, sale INCONCLUSO.

**Detector:**
- Plantilla de 48×48 px alrededor de cada punto, tomada del primer BMP del caso.
- Búsqueda en una ventana de ±80 px alrededor de la proyección de la lectura, con precisión de subpíxel.
- Se calibra antes de medir, con imágenes sintéticas sacadas de BMP reales y desplazadas, giradas ±2° y escaladas ±5 %. Tiene que dar un error p95 ≤ 0,5 px y ≤ 0,1°.

**Medidas.** Proyección con la pose de cámara y el FOV del frame n + k. Los umbrales son los del plan §4.2, evaluados por ventana: cada giro, y el resto por separado.
- **T-lect:** por lectura, p95 de la distancia entre la proyección y el detalle detectado, y el veredicto.
- **T-hook:** por caso y por hook, deriva p95 de los dos detalles, giro aparente (por el ángulo del segmento boca-recámara) y cobertura de detección.
- **Cobertura:** un BMP sin detección cuenta como no observado; si una ventana se queda por debajo del 95 %, es INCONCLUSA.
- **Estímulo:** antes de T-hook se comprueba en las muestras que el giro da diferencias entre frames de más de 3 veces los umbrales. Si no, la ventana es INCONCLUSA.

**Salida:** `informe.md` y `informe.json`, con PASA, FALLA o INCONCLUSO por medida, caso y hook, y las decisiones:
- la lectura ganadora;
- el hook de cada modo;
- el k de la calibración.

Código de salida: 0 si todo PASA, 1 si alguna FALLA y 2 si queda algo INCONCLUSO. Las negativas esperadas se evalúan aparte: el informe dice para cada una si salió como tenía que salir.

**Fixtures offline:** carpetas sintéticas (muestras más BMP generados) para PASA, para un retraso de un frame (FALLA), para una asociación ±1 (calibración FALLA) y para una cobertura baja (INCONCLUSO). Los tests en `qa/strack/tests/` corren sin juego.

## 4. Criterios de cierre de S-track·1

1. Los tests offline del evaluador pasan, y cada fixture negativa da el resultado esperado. Muse escribe los mutantes del evaluador (umbral relajado, k fijado a 0, cobertura ignorada) y cada uno tiene que hacer fallar al menos un test.
2. El PBO compila sin `SCRIPT (E)` en los logs del cliente y del servidor durante las corridas.
3. Todas las corridas en partida terminan y dejan muestras y BMP en `DayZSandbox_dev/evidence/s-track/<run>/`, con el sha256 de cada fichero.
4. Las negativas `delay1` y `roll` salen FALLA en el evaluador. Si una sale PASA, la medida no sirve y S-track·1 no cierra.
5. El informe da una decisión, o un INCONCLUSO con causa, para la calibración, para T-lect y para el hook de cada modo.

## 5. Reparto y proceso

- **Grok (escritor, sin shell):** el mod del §1, en su propia copia.
- **Argon:** el evaluador, sus fixtures y sus tests (§3), en su propia copia.
- **Muse:** los mutantes del evaluador y las negativas (§4.1). No escribe el evaluador.
- **Claude (orquestador, en el PC de Guillermo):** junta, empaqueta el PBO, corre en partida con el banco de dayz-mcp y mide.
  - Toma el lease de dayz-mcp; si está ocupado, para y avisa.
  - Usa una instancia aislada y no toca LIVE ni T130.
  - No hace commit hasta que el hilo lo arbitre.
- **Sol:** revisa al cerrar la fase, no esta corrida.
