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
