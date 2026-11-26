# S-track·1 — contrato entre el mod, el evaluador y los mutantes

Lo fija el orquestador (Claude) para que tres workers trabajen en paralelo sin verse. Manda el brief
`DayZSandbox_dev/plans/2026-11-10-s-track-1-brief.md`; este fichero solo fija nombres y formatos que el
brief deja abiertos. Si algo de aquí contradice el brief, gana el brief y se avisa en el informe.

## 1. Corridas y argumentos del cliente

- Línea de comandos del cliente: `-strack=<caso>`, `-strack_hook=<Ha|Hb|Hc>`, `-strack_inject=<none|delay1|roll>`
  (`-strack_inject` ausente = `none`). Casos: `calib`, `mount0`, `mount03`, `lookat`, `follow`.
- Respaldo (por si el banco no puede pasar argumentos al cliente): si `-strack` no está en la línea de
  comandos, el mod lee `$profile:strack/strack_args.txt`, una línea `clave=valor` por argumento
  (`strack=mount0`, `strack_hook=Ha`, `strack_inject=none`). Si no hay ninguna de las dos, el mod no hace nada.
- Nombre de la corrida: `<caso>_<hook>` o `<caso>_<hook>_<inject>` si inject ≠ none. Ej.: `mount0_Ha_delay1`.
- Salida del cliente: `$profile:strack/<run>/samples.jsonl` y los BMP en la misma carpeta,
  `f<frame con 6 dígitos>.bmp` (ej. `f000120.bmp`), pasando a `MakeScreenshot` la ruta completa con `$profile:`.
  Al terminar, `$profile:strack/<run>/done.json` con `{"run":..,"frames":N,"shots":M,"ok":true}`.
- Una corrida dura hasta que el orquestador termina su guion de movimiento (3 tandas × (andar 3 s, girar 180°, andar 3 s)).
  El cliente muestrea desde que el arma está en manos hasta que existe `$profile:strack/<run>/stop.txt`
  (lo crea el orquestador) o pasan 90 s, lo que llegue antes. `calib` termina sola a los 200 frames capturados.
- Captura: uno de cada 10 frames (`frame % 10 == 0`), salvo `calib`, que captura todos sus 200 frames.

## 2. `samples.jsonl` — una línea JSON por frame y hook

```json
{"frame": 120, "t_ms": 2001.5, "dt": 0.0166, "hook": "Ha", "invocaciones_en_frame": 1,
 "caso": "mount0", "inject": "none", "run": "mount0_Ha",
 "lecturas": {"usti hlavne": {"a": [x,y,z], "b": [x,y,z], "c": [x,y,z], "d": [x,y,z], "e": [x,y,z], "f": [x,y,z]},
              "konec hlavne": {"a": [..], "b": [..], "c": [..], "d": [..], "e": [..], "f": [..]}},
 "cam": {"pos": [x,y,z], "x": [..], "y": [..], "z": [..]},
 "fov_rad": 1.0471976, "calib_yaw_deg": 0.0, "shot": "f000120.bmp"}
```

- Coordenadas de mundo de DayZ (metros; Y arriba). Una lectura no disponible va como `null`.
- `cam` es la pose ESCRITA en la cámara ese frame: `pos` y los ejes de su matriz (`x` derecha, `y` arriba,
  `z` adelante = eje óptico), tal como se pasan a `SetTransform`/se derivan de la orientación escrita.
- `fov_rad` es el valor pasado a `Camera.SetFOV` (60° = 1.0471976). [ASSUMPTION] Es FOV vertical; el
  evaluador lo comprueba con la calibración y dice qué convención casa (vertical u horizontal).
- `calib_yaw_deg`: solo en `calib`, el giro extra escrito ese frame (10.0 en pares, 0.0 en impares); 0.0 fuera de calib.
- `shot`: nombre del BMP pedido ese frame, o `""`.
- `inject=delay1`: la pose escrita en el frame n es la que correspondía a la entrada del frame n−1; las
  `lecturas` siguen siendo las del frame n. `inject=roll`: la cámara gira 1° sobre su eje óptico tras calcular la pose.
- Imagen: 1920×1080. Proyección del evaluador: v = p − cam.pos; xc = v·x, yc = v·y, zc = v·z;
  u = 960 + f·xc/zc, v_px = 540 − f·yc/zc, con f = 540 / tan(fov_v/2) si el FOV es vertical.

## 3. `informe.json` (lo escribe el evaluador; lo leen los tests y `check_negatives.py`)

```json
{"schema": 1,
 "calib": {"Ha": {"k": 1, "match_frac": 1.0, "verdict": "PASA", "cause": "", "fov_convention": "vertical"},
           "Hb": {...}},
 "detector": {"p95_px": 0.21, "p95_deg": 0.03, "verdict": "PASA"},
 "results": [{"run": "mount0_Ha", "caso": "mount0", "hook": "Ha", "inject": "none",
              "measure": "T-lect" | "T-hook", "reading": "a" | null, "window": "giro1" | "resto" | "...",
              "p95_px": 0.0, "roll_deg": 0.0, "coverage": 1.0, "verdict": "PASA|FALLA|INCONCLUSO", "cause": ""}],
 "decisions": {"lectura": "a" | null, "hook_por_modo": {"mount0": "Ha" | null, "mount03": ..., "lookat": ..., "follow": ...},
               "k": {"Ha": 1, "Hb": 1}},
 "negativas": [{"run": "mount0_Ha_delay1", "inject": "delay1", "expected": "FALLA", "got": "FALLA", "ok": true}],
 "exit_code": 0}
```

Las corridas con `inject != none` no cuentan para las decisiones ni para `exit_code`: van solo a `negativas`.

## 4. Constantes del evaluador (los mutantes las cambian por texto: una por línea, a nivel de módulo, exactamente así)

```python
THRESH_PX = 2.0
THRESH_ROLL_DEG = 0.5
COVERAGE_MIN = 0.95
CALIB_MATCH_MIN = 0.99
K_CANDIDATES = (-2, -1, 0, 1, 2)
STIMULUS_FACTOR = 3.0
DETECTOR_MAX_PX = 0.5
DETECTOR_MAX_DEG = 0.1
```

El evaluador las usa de verdad (nada de copiar el número en otro sitio). Los tests cargan el evaluador desde
la ruta de la variable de entorno `STRACK_EVAL_PATH` si existe (si no, `qa/strack/s_track_eval.py`), con
`importlib`, y lo ejecutan como CLI con esa misma ruta: así un mutante se prueba sin tocar el original.

## 5. Write-sets (no se pisan)

- Grok: `DayZSandbox_dev/qa/strack/DZS_STrack/**`
- Argon: `DayZSandbox_dev/qa/strack/s_track_eval.py`, `qa/strack/requirements.txt`, `qa/strack/tests/**`,
  `qa/strack/fixtures/**` (incluido su generador), y solo la excepción de `qa/tests/test_stdlib_only.py`.
- Muse: `DayZSandbox_dev/qa/strack/mutants/**` y `DayZSandbox_dev/qa/strack/check_negatives.py`.

---

# S-track·2 — ampliación del contrato (2026-11-12)

La fija el orquestador (Claude) antes de lanzar a los workers. Manda el brief
`DayZSandbox_dev/plans/2026-11-12-s-track-2-brief.md`; si algo de aquí lo contradice, gana el brief y se avisa en
el informe. Todo lo de S-track·1 de arriba sigue en vigor salvo lo que se sustituye aquí de forma explícita.
Las marcas `[DESIGN]` son decisiones del orquestador donde el brief deja hueco; van al anexo de desviaciones.

## 6. Hechos ya fijados por el código de `2dab484` (el contrato de arriba no los decía)

- Cada línea de `samples.jsonl` lleva `"origin": [X, Y, Z]` (metros enteros, fijado al armar) y **todas** las
  posiciones (`lecturas`, `cam.pos` y las nuevas de abajo) van relativas a ese origen. `"fov_motor"` es lo que
  devuelve el motor; `fov_rad`, lo escrito.
- Argumentos que ya existen: `-strack_move=self` (el propio mod mueve al jugador) y `-strack_wait=<s>` (espera con
  el arma en manos antes de armar; por defecto 60).
- Lecturas (a)-(f) de un punto de memoria `mp` del arma (`STRACK_Session.c:551-604`): (a) `weapon.ModelToWorld(mp)`;
  (b) `GetSelectionPositionWS`; (c) `player.ModelToWorld(GetSelectionPositionMS)`; (d) hueso `RightHand_Dummy`
  con la relación congelada al armar; (e) `GetRenderTransform`; (f) ejes de `GetTransform` con
  `tm[3] = GetWorldPosition()`.
- Proyección y focal: la f medida en `calib` (px) sustituye a la f derivada del FOV (`s_track_eval.py:68-78`).

## 7. Argumentos y corridas nuevas

- Casos nuevos: `ropa`, `suave30`, `suave60`, `suave144`. `[DESIGN]` El brief dice `-strack=suave`; aquí el caso
  lleva el régimen en el nombre para que cada régimen tenga su corrida y su carpeta. El mod trata igual los tres
  (`suave*`); el FPS lo fija el banco con `-limitFPS=<N>` y el mod lo recibe en `-strack_fps_cap=<N>` (por
  defecto 60; también vale `strack_fps_cap=<N>` en `strack_args.txt`).
- Hooks: `ropa` acepta Ha/Hb/Hc (el orquestador pasa el ganador de `mount0`, o Hb); `suave*` solo Hb.
- `-strack_inject` acepta además `smooth03`, `quatlerp` y `longarc`, **solo en `suave*`** (en otro caso el mod
  rechaza los argumentos, como hoy). `delay1` y `roll` no valen en `suave*`.
- Nombres de corrida: como en §1. Ej.: `ropa_Hb`, `suave60_Hb`, `suave60_Hb_quatlerp`.

## 8. Preflight de FPS (mod)

- Tras la espera de `-strack_wait` con el arma en manos, y antes de armar, el mod mide 10 s de `dt` (sin
  capturas). Umbral `[DESIGN]`: `max(18 ms, 1,08 × 1000 / fps_cap)` (60 → 18 ms, como el brief; 30 → 36 ms;
  144 → 18 ms: el 10 % de 144 lo juzga el evaluador, no el preflight).
- Si el p50 de `dt` supera el umbral: no arma, escribe `done.json` con
  `{"run":..,"ok":false,"causa":"fps","dt_p50_ms":..,"umbral_ms":..,"n":..}` y no escribe `samples.jsonl`.
- Si pasa, escribe `$profile:strack/<run>/preflight.json` con `{"dt_p50_ms":..,"dt_p95_ms":..,"n":..,"umbral_ms":..}`
  y arma. El `done.json` final lleva además `"preflight_dt_p50_ms"`.
- Log: `[STRACK] preflight fps p50=<ms> umbral=<ms> ok=<0|1>`.

## 9. Movimiento y captura

- Giro en el sitio (`-strack_move=self`, segmento de giro): 180° en 4,0 s ± 0,3 s, independiente del FPS
  (la ganancia del lazo de `OverrideAimChangeX` se escala con `dt` o equivalente). El log de fin de giro que ya
  existe (`[STRACK] move giro fin ... t=<s>`) se conserva: el orquestador comprueba con él los 4,0 ± 0,3 s.
- Campo nuevo en **cada** línea: `"giro": n`, con n = 0 fuera de giro y 1, 2, 3 dentro del giro n-ésimo (en
  `suave*`: 1 = giro de +170°, 2 = giro de −170°), y `"seg": s` = segmento del guion de movimiento (`s_Seg`).
- Captura: con `giro > 0`, un frame de cada 2 (`frame % 2 == 0`); con `giro == 0`, uno de cada 10
  (`frame % 10 == 0`). `calib`, como en S-track·1. El evaluador cuenta las capturas pedidas por `shot != ""`.
- El evaluador usa `giro` para las ventanas (`giro1`, `giro2`, `giro3`, `resto`) en lugar de inferirlas del rumbo.

## 10. Ropa (`-strack=ropa`)

- El servidor viste al jugador con `AliceBag_Green` y monta en el M4A1 `ACOGOptic` (slot `weaponOptics`) y
  `M4_Suppressor` (slot `weaponMuzzleM4`) con `GetInventory().CreateAttachment(type)`
  (`P:\scripts\3_game\systems\inventory\inventory.c:209`, `proto native EntityAI CreateAttachment(string typeName)`).
  Clases comprobadas en el config vanilla: `P:\DZ\characters\backpacks\config.cpp:3466`,
  `P:\DZ\weapons\attachments\optics\config.cpp:722` (slot `WeaponOptics`),
  `P:\DZ\weapons\attachments\muzzle\config.cpp:930` (slot `weaponMuzzleM4`); el M4A1 acepta los dos slots
  (`P:\DZ\weapons\firearms\m4\config.cpp`, `attachments[]`). Si alguno falla al crearse: log
  `[STRACK] ropa <clase> fallo` y la corrida sigue (el evaluador da INCONCLUSO a esa categoría).
- Cámara como `mount0`.
- Campo nuevo en cada línea de `ropa`: `"ropa": {"mochila": P, "mira": P, "silenciador": P, "spine3": P, "arma": P}`,
  con `P = {"a": POSE, "f": POSE}` o `null` si no existe, y `POSE = {"pos": [x,y,z], "x": [..], "y": [..], "z": [..]}`
  (pos relativa al origen; `x`, `y`, `z` = columnas 0, 1 y 2 de la matriz del objeto).
  - Entidades (mochila, mira, silenciador, arma): (a) = `GetTransform(m)` tal cual; (f) = ejes de `GetTransform`
    con `pos = GetWorldPosition()`.
  - Hueso `Spine3` del jugador: (a) = `GetBoneTransformWS`; (f) = la matriz del jugador (`GetTransform` con
    `GetWorldPosition()` como traslación) × `GetBoneTransformMS`. `[DESIGN]`
- Además, en `ropa`, `lecturas` lleva un tercer punto `"mira"`: un punto de memoria de la mira que elige el mod
  (lo nombra en el log: `[STRACK] ropa punto mira=<nombre>`), con las seis lecturas (a)-(f) aplicadas a la entidad
  mira. Es el «detalle de la mira» del brief §4.

## 11. Suave (`-strack=suave*`)

- El servidor crea una `Pot` a 3 m delante del jugador, sobre el suelo y sin física que la mueva, y la mueve 1 m en
  horizontal cada 2 s con `SetPosition`, alternando +1 m y −1 m sobre un eje fijo. Log de servidor por salto:
  `[STRACK] suave salto i=<n> frame_srv=<frame> t_srv_ms=<ms> pos=[x,y,z]`.
- Cámara `follow` sobre la lata (ancla = posición de la lata; rumbo = el de la lata), hook Hb. El jugador, quieto.
- Guion `[DESIGN]`: tramo 1 (10 s) `smooth_s` = 0; tramo 2 (10 s), 0,3; tramo 3 (10 s), 0,8; tramo 4: la lata
  quieta, `smooth_s` 0,3; a los 0,5 s la orientación deseada salta +170° en guiñada respecto al rumbo base y se
  mantiene 4 s (`giro` = 1); luego salta −170° (vuelve al rumbo base) y se mantiene 4 s (`giro` = 2); fin y
  `done.json`. Con `inject=smooth03`, `smooth_s` = 0,3 en todos los tramos.
- Filtro: el de `mount03` (`STRACK_Session.c:710-729`): `alpha = 1 − exp(−dt/smooth_s)` (alpha = 1 si
  `smooth_s` = 0), posición con lerp y orientación con la `Slerp` de arco corto (`STRACK_Math.c:151`).
  `quatlerp`: `Math3D.QuatLerp` y normalización en lugar de la `Slerp`. `longarc`: la `Slerp` sin invertir el
  signo cuando el producto escalar es < 0.
- Para que `longarc` sea observable `[DESIGN]`: el rumbo base del tramo 4 se elige de modo que, con la convención
  de `Math3D.MatrixToQuat`, el producto escalar entre el cuaternión de partida y el objetivo sea < 0 en al menos
  uno de los dos giros. El mod escribe en la línea del primer frame de cada giro `"quat_dot_inicio": d`.
- Campos nuevos en cada línea de `suave*`: `"tramo": 1..4`, `"smooth_s": s` (el usado ese frame),
  `"fps_cap": N`, `"lata": {"a": [x,y,z]}` (posición leída en el cliente, relativa al origen: es la «entrada
  leída» del brief), `"cam_raw": {"pos": .., "x": .., "y": .., "z": .., "q": [x,y,z,w]}` (pose deseada antes del
  filtro) y, en `cam`, además `"q": [x,y,z,w]` (el cuaternión escrito tal como sale de `MatrixToQuat`, sin
  renormalizar).
- Captura en `suave*`: la regla de §9 (los giros de ±170° cuentan como `giro > 0`).

## 12. Marcas a mano — `qa/strack/marcas/<run>.json` (las escribe el orquestador)

```json
{"schema": 1, "run": "mount0_Hb",
 "convencion": "px de la PNG 1920x1080, origen arriba-izquierda, centro del pixel (0,0) en (0.0,0.0); mismo marco que la proyeccion de §2",
 "marcadores": {"A": "claude-orquestador", "B": "<lane y modelo>"},
 "marcas": [{"shot": "f000120.bmp", "png": "f000120.png", "sha256": "<sha256 de la PNG>",
             "momento": "estable",
             "A": {"usti hlavne": [960.0, 540.0], "konec hlavne": [700.5, 610.0]},
             "B": {"usti hlavne": [960.5, 540.2], "konec hlavne": [700.0, 610.4]},
             "puntos": {"usti hlavne": [960.25, 540.1], "konec hlavne": [700.25, 610.2]},
             "diff_max_px": 0.64}]}
```

- `momento` ∈ `estable | giro1 | giro2 | giro3 | resto`. `puntos` = media de A y B. En `ropa` se añade el punto
  `"mira"`. Un punto que no se ve se omite.
- El evaluador descarta (y lo dice en el informe) cualquier marca con `diff_max_px` > `MARK_AGREE_PX` o cuyo
  sha256 no case con la PNG; una corrida sin marcas válidas da INCONCLUSO en T-lect con causa `sin_marcas`.
- La máscara la genera el evaluador y la guarda en `qa/strack/marcas/mascara_<run>.png` (8 bits, 0/255, tamaño de la
  plantilla, centrada en la marca de la boca de la primera captura marcada).

## 13. Constantes nuevas del evaluador (mismas reglas que §4: una por línea, a nivel de módulo, exactamente así)

```python
TEMPLATE_PX = 48
CORR_MIN = 0.8
MIN_SHOTS_WINDOW = 20
MASK_STD_MAX = 8.0
MASK_MIN_SHOTS = 50
MARK_AGREE_PX = 1.5
TEMPLATE_SOURCE = "marca"
USE_MASK = True
ROPA_MAX_M = 0.01
ROPA_MAX_DEG = 0.5
JUMP_MIN_M = 0.5
THRESH_SUAVE_FRAC = 0.02
QUAT_NORM_TOL = 1e-4
SUAVE_FPS_AGREE_DEG = 0.5
FPS_REGIME_TOL = 0.10
```

Las de §4 no cambian. `TEMPLATE_SOURCE = "proyeccion"` (plantilla centrada en la proyección de una lectura, como en
S-track·1) y `USE_MASK = False` tienen que seguir siendo caminos de código ejecutables: son mutantes nuevos.

## 14. `informe.json` — ampliación (schema 2)

- `"schema": 2`. `results[]` admite `"measure": "T-ropa"`, `"T-suave"` y `"T-marca"` (distancia proyección↔marca por
  lectura, mismo umbral `THRESH_PX`). Campos extra opcionales por fila: `"category"` (`mochila|mira|silenciador`),
  `"regime"` (`"30"|"60"|"144"`), `"tramo"` (`"s0"|"s03"|"s08"|"giro+170"|"giro-170"`), `"n_shots"`, `"p95_m"`,
  `"p95_deg"`, `"err_max_frac"`, `"quat_norm_dev"`, `"arc"` (`"corto"|"largo"`), `"fps_measured"`,
  `"orient_1_6_deg"`.
- `decisions` añade `"ropa": {"mochila": "sigue"|"no_sigue"|null, "mira": .., "silenciador": ..}` y
  `"suave": {"30": "PASA"|"FALLA"|"INCONCLUSO", "60": .., "144": ..}`; `hook_por_modo` sigue con sus cuatro modos.
- `negativas[]` esperadas, todas con `expected: "FALLA"`: `mount0_Ha_delay1`, `mount0_Hb_delay1`, `mount0_Hc_delay1`,
  `lookat_Ha_delay1`, `lookat_Hb_delay1`, `mount0_Hb_roll`, `suave60_Hb_smooth03`, `suave60_Hb_quatlerp`,
  `suave60_Hb_longarc`.
- `exit_code`: 0/1/2, como en S-track·1.

## 15. Write-sets de S-track·2 (no se pisan)

- Muse, sesión «mod»: `DayZSandbox_dev/qa/strack/DZS_STrack/**`.
- Muse, sesión «evaluador» (no ve el mod): `qa/strack/s_track_eval.py`, `qa/strack/requirements.txt`,
  `qa/strack/tests/**`, `qa/strack/fixtures/**`.
- Muse, sesión «mutantes» (no ha escrito el evaluador): `qa/strack/mutants/**`, `qa/strack/check_negatives.py`.
- Orquestador: este `CONTRACT.md`, `qa/strack/marcas/*.json`, el banco y la evidencia.
- Nadie cambia los umbrales de §4 ni de §13: un worker que los cambie invalida la corrida.

## 16. Aclaraciones tras la primera revisión de Sol (2026-11-12, orquestador)

- **Tiempo.** En cada línea, `dt` es el intervalo que acaba en ese frame (el `timeslice` de `OnUpdate` de ese frame,
  `STRACK_Session.c`) y `t_ms` es el instante de ese frame (`(GetTickTime() − T0) × 1000`): `t_ms` fecha el
  **final** del intervalo `dt`. El filtro del frame n usa el `dt` del frame n.
- **Preflight de 30 fps.** El umbral de 36 ms para `fps_cap` = 30 (§8) es decisión del orquestador: el brief §1 fija
  18 ms para el banco de 60 fps y a la vez exige `suave30` con `-limitFPS=30`, imposible con 18 ms. Va al anexo de
  desviaciones del informe.
- **T-suave, entrada.** La «entrada leída» es `lata.a`. `cam_raw` es la pose deseada que el mod construye con esa
  entrada en el mismo frame; el evaluador debe comprobar que `cam_raw.pos` sigue a `lata.a` (con el desplazamiento
  constante de `follow`) en el mismo frame, y si no, la ventana es FALLA (`entrada_desfasada`).

## 17. Comprobación del sesgo con rasgos visibles del modelo (2026-11-25, árbitro: coordinador; sustituye a «marcar boca y recámara» del §12)

Motivo: `usti hlavne` (centro del ánima) y `konec hlavne` (dentro del cajón) no son rasgos visibles, así que no se pueden
marcar a mano a < 2 px. Se marcan rasgos visibles cuya posición en el espacio del modelo sale del p3d vanilla
`P:\DZ\weapons\firearms\m4\m4a1.p3d` (ODOL v54; puerta: la distancia usti↔konec del p3d, 0,407969 m, coincide con la
de las lecturas (a) en partida, mediana 0,407952 m sobre 1967 frames, diferencia 0,017 mm).

- **Espacio del modelo del M4A1:** el eje del cañón es el eje x del modelo (`usti hlavne` x = −0,41976, `konec hlavne`
  x = −0,01179, los dos en y = 0,06566, z = 0,00006).
- **Rasgo `boca_anillo`:** centro del anillo exterior de la cara frontal del apagallamas (LOD 0, polígono de 16 lados,
  radio ~11,3 mm, x = −0,43565). Su centro está a 0,22 mm del eje de usti/konec (+0,205 mm en y, −0,085 mm en z): se
  acepta por escrito, porque el giro del arma sobre su eje desconocido mueve su proyección ≤ 0,25 px a la distancia
  de mount0. Se proyecta con cualquier lectura como el punto del eje
  `usti + t · (konec − usti)`, con `t = (x_anillo − x_usti) / (x_konec − x_usti)`.
  Marca: cada marcador pone **5 puntos del borde** de la boca; la herramienta ajusta una elipse y guarda su centro.
  Los centros de los dos marcadores tienen que coincidir a ≤ `MARK_AGREE_PX`.
- **Rasgo `punto_mira`:** vértice de la punta del punto de mira delantero (LOD 0), fuera del eje. Solo en `mount0`,
  `mount03` y `ropa`, donde se conoce la pose completa del arma:
  - `mount0`/`mount03`: de la cámara escrita, porque `BuildMount` (`STRACK_Session.c`) pone la cámara en
    `usti + ax0 · 0,6 + ax1 · 0,1` (con `ax0`, `ax1` los ejes x, y del arma), así que `ax1 = (cam_raw.pos − usti − 0,6 · ax0) / 0,1`
    con `ax0 = (konec − usti)/|konec − usti|`; en `mount03` se usa `cam_raw` (antes del filtro) si existe y, si no, la
    corrida no da `punto_mira`;
  - `ropa`: de la pose `ropa.arma` (a) del mismo frame.
  Se marca como **las dos puntas de las orejas** (`punto_mira_orejas`) y se usa su media, que es lo que da
  `m4a1_rasgos.json` (marcar una sola oreja metería ~11 px de sesgo artificial).
- **Formato de marcas (§12):** cada captura puede llevar, por marcador, `"boca_anillo_borde": [[u,v] × 5]` y
  `"punto_mira": [u,v]`; `puntos` lleva `"boca_anillo"` (media de los centros ajustados) y `"punto_mira"`.
- **Medida T-sesgo:** por **caso** (`mount0`, `mount03`, `lookat`, `follow`, `ropa`; se juntan las corridas sin inyección
  de ese caso, de todos sus hooks) y lectura, distancia entre la proyección del rasgo y la marca, p95 sobre las
  capturas marcadas (5 por corrida, §12). Aclaración del orquestador (25-nov) tras la revisión de Argon: con 5 marcas
  por corrida y `SESGO_MIN_MARCAS = 10`, «caso» es el caso, no la corrida. `mount03` no da `punto_mira` porque el mod
  solo escribe `cam_raw` en `suave*`. Es una **comprobación**, no la medida principal: T-lect decide con la plantilla enmascarada.
  T-sesgo da FALLA si p95 > `THRESH_PX` en un caso con ≥ `SESGO_MIN_MARCAS` capturas marcables; con menos, INCONCLUSO
  con causa `sesgo_no_observable`.
- Constante nueva (misma regla de §4): `SESGO_MIN_MARCAS = 10`.

## 18. Árbitro del sesgo tras 4 vueltas (coordinador, 2026-11-26 00:23Z; manda sobre §17 donde choquen)

- T-lect y T-hook siguen la plantilla enmascarada sobre `usti hlavne` y `konec hlavne`, con roll (comportamiento de la
  vuelta 3). Motivo de deshacer la vuelta 4 (ancla en un rasgo §17): con un solo punto ancla el roll deja de medirse y la
  negativa `mount0_Hb_roll` podría pasar.
- `usti hlavne` y `konec hlavne` no se marcan (no son visibles). Sin marcas de §12, la plantilla se ancla en la
  **proyección de la lectura (a)** en la primera captura con textura, y el informe lo dice así (`ancla: "proyeccion_a"`).
- **T-sesgo es informativo:** se calcula y se informa por caso, lectura y rasgo, pero no cambia `decisions` ni
  `exit_code`. El criterio del brief que pedía cerrar el sesgo constante pasa a «observado e informado».
- En `ropa` (un solo hook) se marcan 10 capturas para que T-sesgo sea observable.

## 34. T-hook de `mount` por medida directa (árbitro: coordinador, 2026-11-26 14:21Z; parámetros congelados el 2026-11-26)

`qa/strack/thook_mount.py`. Por cada captura de giro y en la ventana `sin_giro` (capturas sin giro tras la referencia), se mide el desplazamiento de dos cultivos fijos sobre el arma frente a la primera captura estable (frame ≥ 30). Cultivo 1: proyección de `konec hlavne` (lectura a), apartado a lo largo del eje, en sentido contrario a la boca, hasta no contener el punto fijo de la HUD (centro exacto). Cultivo 2: a 200 px del 1 en ese mismo sentido. Cada cultivo se normaliza (media 0, varianza 1). NCC por FFT en ±BUSQUEDA_PX y en ESCALAS; correlación de fase para el subpíxel cuando gana la escala 1. Deriva = p95 del mayor desplazamiento; roll = p95 del ángulo entre los segmentos.

Parámetros congelados (no se tocan para que un resultado pase):
```
THRESH_PX = 2.0
THRESH_ROLL_DEG = 0.5
MIN_SHOTS_WINDOW = 20
CROP_PX = 48
SEPARACION_PX = 200.0
CALIDAD_MIN = 0.5
BUSQUEDA_PX = 120
ESCALAS = (1.0, 0.8, 0.85, 0.9, 0.95, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3)
ESCALA_MEJORA_MIN = 0.05
RIGIDEZ_ESCALA_TOL = 0.05
HUD_MARGEN_PX = 4.0
ESTABLE_FRAME = 30
```
Una lectura vale si tiene calidad ≥ CALIDAD_MIN y es rígida: los dos cultivos eligen la misma escala (± RIGIDEZ_ESCALA_TOL) y la longitud del segmento desplazado casa con ella. Veredicto por ventana: < 20 válidas → INCONCLUSO (`insufficient_sampling`, `cultivos_no_rigidos` o `correlacion_debil`); p95 > 2 px o roll > 0,5° → FALLA; cobertura < 0,95 → INCONCLUSO; si no, PASA. Decisión de producto (Guillermo, 2026-11-26 15:23Z, «Vale, con suavizado»): en `mount` con el arma en manos, un FALLA de esta medida es temblor medido y no un FALLA del producto. El `smooth_s` por defecto en manos es el menor τ con `sin_giro` p95 ≤ 2 px. El retraso en giros se informa aparte, por τ, en grados y en ms (coordinador, 15:39Z).

## 35. T-lect de lookat/follow por medida directa (árbitro: coordinador, 2026-11-26 15:39Z; parámetros congelados el 2026-11-26 16:25Z)

`qa/strack/tlect_direct.py`. La lectura (a) solo fija el ángulo 2D (boca→recámara proyectadas) y la escala (f/z de la boca) de la plantilla. La posición se busca por NCC enmascarada en ±BUSQUEDA_PX, sin preferencia por el centro. Deriva de cada lectura = posición detectada − proyección de esa lectura. Plantillas: la primera captura estable más un banco con una de cada BANCO_PASO capturas de giro, cada una recortada en la proyección de (a) de su propia captura (el hueco del sesgo declarado en §17/§18). Cada captura usa la plantilla de OTRO giro con la vista 3D del cañón más parecida, dentro de VISTA_MAX_DEG. El punto fijo de la HUD se borra de cada imagen. El ángulo se afina en ANG_BUSQUEDA_DEG. Una detección se descarta si la calidad es < CALIDAD_MIN o el margen frente al segundo máximo local (a más de AMBIG_RADIO_PX) es < AMBIG_MIN.

Parámetros congelados. La máscara es una cápsula: radio RADIO_BOCA_M (radio exterior del apagallamas más margen), LARGO_FRANJA_M de cañón y FRENTE_M = RADIO_BOCA_M por delante de la punta. FRENTE_M se fija igual al radio por geometría (casquete simétrico, sin una longitud elegida a mano), no por resultado. Era también el valor anterior al barrido de sensibilidad (1,2 / 3 / 5 cm), que solo se informa como sensibilidad.
```
THRESH_PX = 2.0
COVERAGE_MIN = 0.95
MIN_SHOTS_WINDOW = 20
ESTABLE_FRAME = 30
TPL_PX = 64
BUSQUEDA_PX = 40
CALIDAD_MIN = 0.5
RADIO_BOCA_M = 0.012
LARGO_FRANJA_M = 0.12
FRENTE_M = 0.012
HUD_RADIO = 4
ANG_BUSQUEDA_DEG = (0, -1, 1, -2, 2, -3, 3, -4, 4)
VISTA_MAX_DEG = 10.0
BANCO_PASO = 3
AMBIG_RADIO_PX = 4
AMBIG_MIN = 0.03
```
Veredicto por ventana y lectura: < 20 capturas → INCONCLUSO `insufficient_sampling`; < 20 válidas → INCONCLUSO `correlacion_debil`; p95 > 2 px → FALLA; cobertura < 0,95 → INCONCLUSO `low_coverage`; si no, PASA. Se informan también p50 y la fracción > 2 px.

## 36. Mod r6 / r6b (orquestador, 2026-11-26; para la tanda corta)

Argumentos nuevos de la línea de comandos. Sin ellos, el mod se comporta igual que r5.
- `-strack_noshots=1` (solo en suave): sin capturas; la línea lleva `"noshots":true`.
- `-strack_smooth_s=<s>` (mount0/mount03): filtro de la cámara con τ = s (mount03 usa 0,3 si no se da). La línea lleva `"mount_tau_s"` y `"smooth_pos"`.
- `-strack_smooth_pos=0`: el filtro solo suaviza la orientación; la posición queda rígida sobre el arma.
- `-strack_tag=<t>`: sufijo del nombre de la corrida (`<caso>_<hook>[_<inject>]_<t>`).
- `-strack_giro_lento=<f>` (r6b): velocidad del giro × f; el tope del giro pasa de 6 s a 6/f s.
- `-strack_giro_alterno=1` (r6b): el segundo giro vuelve en sentido contrario, así que los tres giros recorren los mismos rumbos.
PBO r6b: `bench\@DZS_STrack_r6\Addons\DZS_STrack.pbo`, 74 266 B, sha256 `eaf22bb916b684a12268f14698acaac0cbe19cfbd8db202038ded241b7b8c251`. Linter PASS 0/0. No probado en partida.
