# Informe del evaluador S-track·2 — sesión «evaluador» (Argon)

Workspace: `C:\tmp\dsbx-strack2\eval`. Solo se ha escrito en
[s_track_eval.py](DayZSandbox_dev/qa/strack/s_track_eval.py),
[make_fixtures.py](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py),
[test_s_track_eval.py](DayZSandbox_dev/qa/strack/tests/test_s_track_eval.py),
[test_s_track2.py](DayZSandbox_dev/qa/strack/tests/test_s_track2.py) y este informe.
No se ha tocado `CONTRACT.md` ni el brief; no se ha lanzado DayZ; no hay commits.

Resumen: el evaluador pasa a schema 2 con marcas a mano (T-marca), plantilla
enmascarada de `TEMPLATE_PX = 48`, cobertura por capturas con ventanas por
`giro`, T-ropa y T-suave, conservando calibración `k`, `f` medida, umbrales,
códigos 0/1/2 y el reparto positivas/negativas de S-track·1.

## Cambios por punto del brief §4

### Constantes (contrato §4 y §13)

Una por línea, a nivel de módulo, exactamente como en el contrato, y usadas
por el código (sin el número copiado en otro sitio):
[s_track_eval.py:20](DayZSandbox_dev/qa/strack/s_track_eval.py:20) a
[s_track_eval.py:42](DayZSandbox_dev/qa/strack/s_track_eval.py:42)
(`THRESH_PX` … `FPS_REGIME_TOL = 0.10`). La antigua `TEMPLATE_SIZE = 32`
desaparece: el tamaño de plantilla es ahora `TEMPLATE_PX`
([s_track_eval.py:28](DayZSandbox_dev/qa/strack/s_track_eval.py:28)), usado en
[s_track_eval.py:640](DayZSandbox_dev/qa/strack/s_track_eval.py:640),
[s_track_eval.py:658](DayZSandbox_dev/qa/strack/s_track_eval.py:658) y
[s_track_eval.py:812](DayZSandbox_dev/qa/strack/s_track_eval.py:812).

### Marcas a mano (contrato §12)

- CLI `--marcas <dir>` en
  [s_track_eval.py:2380](DayZSandbox_dev/qa/strack/s_track_eval.py:2380);
  `evaluate(runs_dir, out_dir, marcas_dir)` en
  [s_track_eval.py:1962](DayZSandbox_dev/qa/strack/s_track_eval.py:1962).
  Resolución por defecto: `--marcas` si se pasa; si no, `<runs>/marcas` si
  existe; si no, `<carpeta del script>/marcas`
  ([s_track_eval.py:157](DayZSandbox_dev/qa/strack/s_track_eval.py:157)).
- Validación en `load_marcas`
  ([s_track_eval.py:166](DayZSandbox_dev/qa/strack/s_track_eval.py:166)):
  se descarta toda marca con `diff_max_px > MARK_AGREE_PX` o cuyo sha256 no
  case con la PNG (o con el BMP si aún no hay PNG), y el descarte queda en
  `informe.json` bajo `marcas.<run>.discarded`. Una corrida sin marcas
  válidas da INCONCLUSO en T-lect/T-hook con causa `sin_marcas`.
- Con `TEMPLATE_SOURCE = "marca"` la plantilla se recorta en la marca de la
  primera captura marcada en `_detect_run_shots`
  ([s_track_eval.py:1365](DayZSandbox_dev/qa/strack/s_track_eval.py:1365)).
  Con `TEMPLATE_SOURCE = "proyeccion"` se ejecuta el camino de S-track·1
  (plantilla en la proyección de la lectura de referencia): es el camino vivo
  del mutante «plantilla en la proyección».
- Medida `T-marca`: distancia proyección↔marca por lectura y punto (arma y,
  en `ropa`, también `mira`), con `THRESH_PX`/`THRESH_ROLL_DEG`, en
  `_eval_tmarca_rows`
  ([s_track_eval.py:1532](DayZSandbox_dev/qa/strack/s_track_eval.py:1532)).
  Una lectura con T-marca FALLA no puede ser la lectura ganadora.

### Plantilla enmascarada

- `build_mask_from_run`
  ([s_track_eval.py:276](DayZSandbox_dev/qa/strack/s_track_eval.py:276)):
  desde `mount0`, píxeles con desviación típica temporal `< MASK_STD_MAX`
  sobre `>= MASK_MIN_SHOTS` capturas de giro, quedándose la componente
  conexa a la marca (`_connected_to_center`,
  [s_track_eval.py:254](DayZSandbox_dev/qa/strack/s_track_eval.py:254)).
  Se construye una máscara por hook y se guarda en
  `marcas/mascara_<run>.png` (8 bits, tamaño `TEMPLATE_PX`, centrada en la
  marca de la boca) desde `evaluate`
  ([s_track_eval.py:1962](DayZSandbox_dev/qa/strack/s_track_eval.py:1962)).
- La máscara de la recámara es la del arma desplazada entre marcas
  (`_shift_mask`, [s_track_eval.py:237](DayZSandbox_dev/qa/strack/s_track_eval.py:237)).
  En el banco, la máscara se lleva con la plantilla (traslación + giro
  ±2° y escala ±5 %) en `make_template_bank`
  ([s_track_eval.py:812](DayZSandbox_dev/qa/strack/s_track_eval.py:812)).
- Correlación normalizada solo sobre la máscara: `extract_template`
  ([s_track_eval.py:658](DayZSandbox_dev/qa/strack/s_track_eval.py:658)),
  la rama enmascarada de `detect_template`
  ([s_track_eval.py:706](DayZSandbox_dev/qa/strack/s_track_eval.py:706)) y
  `_ncc_at` ([s_track_eval.py:693](DayZSandbox_dev/qa/strack/s_track_eval.py:693)).
  Con `USE_MASK = False` todo ese camino se ignora (camino vivo del mutante
  «máscara ignorada»): plantilla y detección sin máscara.

### Calibración del detector

Como en S-track·1 (p95 ≤ `DETECTOR_MAX_PX` y ≤ `DETECTOR_MAX_DEG`) y además
con fondo cambiante en `calibrate_detector`
([s_track_eval.py:895](DayZSandbox_dev/qa/strack/s_track_eval.py:895)):
sintéticas que pegan el parche enmascarado del arma sobre fondos de otras
capturas (o sobre los `background_images` pasados), con veredicto conjunto y
campo `p95_bg_px` en el bloque `detector` cuando hay casos de fondo.

### Cobertura por capturas y ventanas por `giro`

- No observada = sin detección o con correlación `< CORR_MIN` en
  `_eval_window_metrics`
  ([s_track_eval.py:1463](DayZSandbox_dev/qa/strack/s_track_eval.py:1463));
  la detección guarda su correlación (`corr`) en `_detect_run_shots`.
- Ventanas por el campo `giro` (contrato §9) en `windows_from_giro`
  ([s_track_eval.py:212](DayZSandbox_dev/qa/strack/s_track_eval.py:212)) y
  `_windows_for_run`
  ([s_track_eval.py:230](DayZSandbox_dev/qa/strack/s_track_eval.py:230));
  sin campo `giro` se conserva la segmentación por rumbo de S-track·1.
- En corridas con campo `giro`, una ventana con `< MIN_SHOTS_WINDOW`
  capturas pedidas (`shot != ""`) es INCONCLUSO con causa
  `insufficient_sampling`, aparte de la cobertura del 95 %; cada fila lleva
  `n_shots`. En corridas sin `giro` (formato S-track·1) no se aplica el
  mínimo: ver DISPUTAS.

### T-ropa (contrato §10)

`evaluate_ropa_run`
([s_track_eval.py:1644](DayZSandbox_dev/qa/strack/s_track_eval.py:1644)):
por categoría (`mochila` respecto a `spine3`; `mira` y `silenciador`
respecto a `arma`) y por lectura (a) y (f), variación de la pose relativa
(posición y rotación) a lo largo de la corrida. «sigue» si p95
`< ROPA_MAX_M` y `< ROPA_MAX_DEG` en ambas lecturas **y** la proyección del
punto `mira` pasa `THRESH_PX` contra su marca (`_mira_mark_distances`,
[s_track_eval.py:1618](DayZSandbox_dev/qa/strack/s_track_eval.py:1618)).
Filas `T-ropa` con `category`, `p95_m`, `p95_deg`; decisión en
`decisions.ropa` (`sigue|no_sigue|null`). Categoría ausente → INCONCLUSO
`categoria_ausente`; sin marca de mira válida → INCONCLUSO.

### T-suave (contrato §11)

`evaluate_suave_run`
([s_track_eval.py:1760](DayZSandbox_dev/qa/strack/s_track_eval.py:1760)):

- Salto = primer frame en que `lata.a` cambia `> JUMP_MIN_M`; respuesta
  simulada tramo a tramo con el `smooth_s` del guion (0 / 0,3 / 0,8 / 0,3,
  [s_track_eval.py:1757](DayZSandbox_dev/qa/strack/s_track_eval.py:1757)) y
  los `dt` reales (`alpha = 1 - exp(-dt/smooth_s)`, 1 si `smooth_s` 0, así
  que con 0 llega en el primer frame). Error ≤ `THRESH_SUAVE_FRAC` del
  salto en cada frame (posición en los tramos `s0|s03|s08`, orientación/170°
  en los giros).
- Giros de ±170°: arco corto por sentido de guiñada acumulado y recorrido
  ≤ 180° (`arc: corto|largo`), norma del cuaternión escrito en
  `1 ± QUAT_NORM_TOL`, y orientación en t = 1/6 s (interpolada al final del
  intervalo del frame) comparada entre regímenes con
  `SUAVE_FPS_AGREE_DEG` en `evaluate`.
- Régimen con FPS medidos a más de `FPS_REGIME_TOL` de su `fps_cap`
  (o del número del caso `suaveNN`) → INCONCLUSO `fps_regime`.
- Filas `T-suave` con `regime`, `tramo` (`s0|s03|s08|giro+170|giro-170`),
  `err_max_frac`, `quat_norm_dev`, `arc`, `fps_measured`,
  `orient_1_6_deg`; decisión en `decisions.suave` por régimen.

### Lo que se conserva

Umbrales del plan §4.2 intactos, `k` de `calib`, `f` medida, códigos de
salida 0/1/2 (ahora también con FALLA/INCONCLUSO de T-suave y T-ropa),
informe por medida, caso y hook, y las corridas con `inject != none` solo
en `negativas` (las de `suave*` se juzgan con T-suave:
`smooth03|quatlerp|longarc` deben salir FALLA). Informe schema 2
(contrato §14) con `decisions.ropa` y `decisions.suave`.

## Fixtures offline nuevas (brief §4)

Generadores en [make_fixtures.py](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py)
(`_write_marcas_file`, `_write_suave_run`, `_write_ropa_run`,
`_write_fondo_run` y los `kind` nuevos de `generate_fixture`); todas las
fixtures de imagen escriben además sus marcas en `<fixture>/marcas/<run>.json`
con sha256 real. Tests en
[test_s_track2.py](DayZSandbox_dev/qa/strack/tests/test_s_track2.py), que
carga el evaluador desde `STRACK_EVAL_PATH` si existe (contrato §4).

| Fixture | Esperado | Obtenido |
|---|---|---|
| `sesgo5` (lectura `a` desplazada 5 px en todas las capturas) | T-lect y T-marca FALLA | FALLA (`test_sesgo_constante_5px_tlect_falla`) |
| `fondo_cambiante` (arma enmascarada sobre fondo distinto con anillo señuelo) | con máscara PASA, sin máscara FALLA | con máscara error ≈0,05 px y corr ≥ `CORR_MIN`; sin máscara no acierta (`test_fondo_cambiante_con_mascara_pasa_sin_mascara_falla`) |
| `suave_ok` (exponencial correcta, giros ±170°) | T-suave PASA | PASA en `s0/s03/s08/giro+170/giro-170` (`test_suave_exponencial_correcta_pasa`) |
| `suave_smooth` (`smooth_s` cambiado en el tramo `s0`) | T-suave FALLA | FALLA, `err_max_frac > THRESH_SUAVE_FRAC` (`test_suave_smooth_cambiado_falla`) |
| `suave_quatlerp` (`QuatLerp` normalizado en vez de la slerp) | FALLA en el giro | FALLA en `giro±170` (`test_suave_quatlerp_falla_en_giro`) |
| `suave_longarc` (slerp sin invertir el signo) | FALLA en el giro, arco largo | FALLA con `arc = largo` (`test_suave_longarc_falla_en_giro`) |
| `suave30` + `suave60` correctas | acuerdo en t = 1/6 s y PASA en ambos regímenes | PASA (`test_suave_acuerdo_entre_regimenes`) |
| régimen con FPS a 30 con tope 60 | INCONCLUSO `fps_regime` | INCONCLUSO (`test_suave_fps_regimen_inconcluso`) |
| `pocas_capturas` (ventana `giro1` con 15 capturas pedidas) | INCONCLUSO por muestreo | INCONCLUSO `insufficient_sampling`, `n_shots = 15`, exit 2 (`test_pocas_capturas_inconcluso_por_muestreo`) |
| `ropa_ok` | T-ropa `sigue` en las tres categorías | `sigue` (`test_ropa_sigue`) |
| `ropa_falla` (mochila deriva 3 cm) | mochila `no_sigue` | `no_sigue` (`test_ropa_falla_no_sigue`) |
| negativas `suave60_Hb_smooth03/quatlerp/longarc` | FALLA en `negativas` | FALLA, sin filas en `results` (`test_negativas_suave_salen_falla`) |
| marcas con sha256 corrupto | marca descartada | descartada `sha256_mismatch` (`test_marcas_invalidas_se_descartan`) |
| máscara desde `mount0` sintético (55 capturas de giro) | máscara 48×48 con centro del arma y fondo fuera | OK (`test_mascara_desde_mount0_y_detector_fondo`) |

Las fixtures de S-track·1 (`pasa`, `delay1`, `calib_pm1`, `low_coverage`,
`roll_defect`, `weak_stimulus`) siguen dando lo esperado con el evaluador
nuevo (schema 2 y plantilla en la marca).

## Gate

Comandos del encargo, literales, en esta sesión:

```
cd C:\tmp\dsbx-strack2\eval\DayZSandbox_dev
C:\Python314\python.exe -m unittest discover -s qa/strack/tests -t . -v
C:\Python314\python.exe -m unittest qa.tests.test_stdlib_only -v
```

Resultado literal con `C:\Python314\python.exe`: **no ejecutable en esta
sesión** — ese intérprete no tiene `numpy` ni `Pillow`
(`ModuleNotFoundError: No module named 'numpy'` al importar
`make_fixtures.py`), y el encargo prohíbe instalar paquetes. Ver DISPUTAS.

La misma suite, sin tocar una línea, con un intérprete que sí trae las
dependencias declaradas en
[requirements.txt](DayZSandbox_dev/qa/strack/requirements.txt)
(`numpy` 2.3.5 y Pillow 13.0.0 del runtime local de Codex, solo como
intérprete de verificación, sin instalar nada):

```
& C:\Users\guill\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s qa/strack/tests -t . -v
Ran 24 tests in 271.732s
OK

& C:\Users\guill\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest qa.tests.test_stdlib_only -v
Ran 1 test in 0.421s
OK
```

24 tests: 6 de S-track·1 actualizados a schema 2, 4 de detector/ventanas y
14 nuevos de S-track·2. Todo verde, y cada fixture negativa nueva da el
veredicto de la tabla anterior.

## DISPUTAS

1. **El intérprete del gate no tiene las dependencias.** El encargo dice
   que hay `numpy` 2.4.4 y Pillow 12.2.0 en `C:\Python314\python.exe` y
   prohíbe instalar paquetes; en esta sesión `C:\Python314\python.exe -m pip list`
   solo muestra `pip` 25.3 y la suite muere con
   `ModuleNotFoundError: No module named 'numpy'`. No he instalado nada.
   He verificado con el intérprete del runtime de Codex (numpy 2.3.5 /
   Pillow 13.0.0), que no es el del gate: el gate literal queda pendiente
   de un entorno con las dependencias de `requirements.txt`.
2. **[Superada en la Vuelta 2, hallazgo 4: el mínimo se aplica siempre, también a ventanas inferidas.]** `MIN_SHOTS_WINDOW` solo en corridas con campo `giro`. El contrato
   §9 dice que el evaluador usa `giro` para las ventanas en el formato
   nuevo; las fixtures y los datos de S-track·1 no traen `giro` y tienen
   3–4 capturas por ventana, así que aplicarles el mínimo de 20 las haría
   todas INCONCLUSO y rompería el cierre de S-track·1 que el brief manda
   conservar. Aplico el mínimo (causa `insufficient_sampling`) a las
   ventanas de corridas con `giro`, y en las demás solo la cobertura del
   95 %. Si el orquestador quiere el mínimo también sin `giro`, es un
   cambio de una línea en `_eval_window_metrics`, pero invalida las
   fixtures históricas.
3. **T-suave: el `smooth_s` esperado es el del guion, no el escrito.**
   La fila trae `"smooth_s": s` (el usado ese frame, contrato §11); si el
   evaluador simulara con el escrito, la negativa `smooth03` (que escribe
   0,3 en todos los tramos) saldría PASA. Simulo con el `smooth_s` del
   guion por tramo (0 / 0,3 / 0,8 / 0,3) y uso el escrito solo como dato.
   Es lo que hace que `smooth03`, el `smooth_s` cambiado y `QuatLerp`
   salgan FALLA.
4. **Orientación en t = 1/6 s entre regímenes.** Con el filtro por frames,
   tomar «el primer frame ≥ 1/6 s» mete hasta un `dt` de desplazamiento
   (medido: 64,8° a 30 fps frente a 68,5° a 60 fps en la fixture correcta,
   > `SUAVE_FPS_AGREE_DEG`). Interpolo la orientación al final del
   intervalo del frame (`t + dt`), que es cuando la pose escrita existe;
   con eso 30 y 60 coinciden en la fixture. Si el mod entiende que la pose
   vale al inicio del frame, el acuerdo entre regímenes fallará en datos
   reales por cuantización, no por el filtro.
5. **Máscara «del hook ganador».** Construyo la máscara de `mount0` por
   hook (la primera corrida `mount0` con ≥ `MASK_MIN_SHOTS` capturas de
   giro de cada hook) y cada corrida usa la de su hook; la del ganador es
   por tanto la que se usa en sus corridas y en `ropa`. No hay una fase
   previa que elija un único hook antes de detectar, porque la detección
   es lo que decide el hook.
6. **`calibrate_detector` con fondo cambiante necesita máscara.** Sin
   `template_mask` (p. ej. `mount0` sin suficientes capturas de giro) no
   hay casos de fondo y el bloque solo trae el p95 clásico; con máscara,
   `p95_bg_px` gatea el veredicto igual que `DETECTOR_MAX_PX`.

## LO QUE NO PUDE VERIFICAR

- Nada con capturas reales de S-track·2: marcas de dos marcadores con
  `diff_max_px ≤ 1,5 px`, la máscara real de `mount0` con el hook ganador
  (en las fixtures sintéticas no hay 50+ capturas de giro por corrida de
  imagen, así que la máscara de corrida completa solo se ejercita en el
  test unitario de `build_mask_from_run`), ni el detector con fondo
  cambiante sobre BMP del juego (`p95_bg_px` solo se ejercita vía la
  fixture `fondo_cambiante` a nivel de detector, no vía `calibrate_detector`
  con corridas reales).
- Los mutantes de otra sesión (plantilla en la proyección, máscara
  ignorada, umbral de T-suave al 5 %): los caminos vivos están
  (`TEMPLATE_SOURCE = "proyeccion"`, `USE_MASK = False` y el uso real de
  `THRESH_SUAVE_FRAC`), y los tests están escritos contra el comportamiento
  por defecto, pero no he ejecutado ningún mutante.
- El preflight de FPS del mod, los giros de 4,0 s, `quat_dot_inicio` real
  y los logs de servidor de T-suave: son del mod, que esta sesión no ve.
- El gate literal con `C:\Python314\python.exe` (ver DISPUTAS, punto 1).
- **Premisa de las marcas (Sol, vuelta 3):** que el detalle visible marcado a mano coincida geométricamente con el punto de memoria proyectado solo se puede contrastar en el banco real. Dos marcadores pueden coincidir entre sí y compartir un desplazamiento respecto a ese punto; las sintéticas generadas desde las propias proyecciones no prueban esa premisa, y un sesgo constante de 5 px en una fixture no identifica por sí solo una lectura incorrecta sin esa correspondencia.

---

## Vuelta 2 (revisión de Sol, contrato §16)

### Qué cambió por hallazgo

1. **Máscaras por detalle**: `build_masks_from_run` (s_track_eval.py:340) crea una máscara local 48×48 por punto —boca, recámara y `mira`— alineada por su proyección (a); `build_mask_from_run` queda como compatibilidad. Cultivo plano fuera de la máscara (s_track_eval.py:417). `_detect_run_shots` (s_track_eval.py:1487) y `calibrate_detector` usan las dos máscaras locales sin trasladar la de la boca; máscara vacía/inválida → INCONCLUSO con causa (`mascara_vacia`), nunca caída silenciosa a «sin máscara» (`extract_template` devuelve norma 0 marcada en s_track_eval.py:781; pre-causa en `evaluate` s_track_eval.py:2227).
2. **Sintética de fondo subpíxel**: `_paste_masked_patch_subpixel` (s_track_eval.py:318) pega con centro subpíxel coherente con la extracción (offset −23,5) y se usa desde `calibrate_detector` (s_track_eval.py:1010); test a través de `calibrate_detector` con `p95_bg_px ≤ 0,25`.
3. **Sin fondo cambiante no hay PASA**: en `calibrate_detector`, con `USE_MASK=True` y sin casos de fondo (o sin máscara/fondos distintos), veredicto INCONCLUSO con causa `sin_calibracion_fondo` (s_track_eval.py:1158).
4. **Mínimo de 20 siempre**: `_eval_window_metrics` aplica `MIN_SHOTS_WINDOW` también a ventanas inferidas (s_track_eval.py:1591). Fixtures positivas ajustadas: 20 capturas por ventana con `giro` y densidad segura en inferidas (make_fixtures.py:432).
5. **T-lect/T-marca en todos los casos**: el bucle evalúa todas las corridas de imagen (s_track_eval.py:2246), acumula `tmarca_by_run` y el hook ganador exige T-hook PASA y T-marca PASA de su propio caso (s_track_eval.py:2408).
6. **T-suave con objetivo `lata.a` (§16)**: el offset constante de follow se estima de `cam_raw−lata.a`; si `cam_raw` no sigue a `lata.a` en el mismo frame (>0,01 m) → FALLA `entrada_desfasada` (s_track_eval.py:2127). La simulación sigue a `lata.a + offset`.
7. **Estado entre tramos**: la simulación conserva `state_pos/state_q` entre tramos y comprueba también el primer frame de tramo; el generador deja de reiniciar el filtro salvo defecto explícito `reset_en_tramo` (make_fixtures.py:632).
8. **Sin estímulo/grupos → INCONCLUSO**: se exigen `s0,s03,s08,giro+170,giro-170` con observaciones válidas; grupo ausente → `grupo_ausente`, sin salto/sin observaciones → INCONCLUSO (s_track_eval.py:2124), nunca PASA con `err_max_frac=999`.
9. **T-ropa cobertura**: exige `COVERAGE_MIN` y presencia válida en giro y fuera de giro; si no, INCONCLUSO `ropa_cobertura_insuficiente` (s_track_eval.py:1833). Fixture de ropa con tramo en giro (make_fixtures.py:734).
10. **T-ropa sin calibración**: sin calibración válida no se sustituye por `k=0`/focal vertical; contraste visual de la mira INCONCLUSO `calib_inconcluso` y la parte numérica queda en `p95_m/p95_deg` (s_track_eval.py:1836, evaluate s_track_eval.py:2420). Fixtures de ropa traen calib `Hb` con `k=0` (make_fixtures.py:871).
11. **Discriminador 2–5 %**: fixture `suave_frac35` —error del 3,5 % del salto— debe FALLA (make_fixtures.py:641). Verificado contra mutante: con `THRESH_SUAVE_FRAC=0,05` pasa a PASA y con 0,02 FALLA con `err_max_frac=0,035006`.
12. **QuatLerp por error angular**: `_nlerp` de arco corto con signo alineado (make_fixtures.py:567); el test exige FALLA `suave_orient_exceeded`, `arc=corto` y norma válida.
13. **Positivo de imagen S-track·2**: `_write_s2_completo` (make_fixtures.py:793): calib más `mount0/mount03/lookat/follow` con `giro`, todas las capturas con BMP y ≥20 por ventana; la negativa de 15 se deriva con `_trim_giro1_to_15` (make_fixtures.py:802).
14. **Acuerdo solo entre regímenes válidos**: los INCONCLUSO por `fps_regime` quedan fuera de `by_label` (s_track_eval.py:2452).
15. **JSON finito y enum §14**: `_finite_report` (s_track_eval.py:2164) convierte no finitos a 999,0 y se serializa con `allow_nan=False` (s_track_eval.py:2574); regímenes suaves ausentes = `"INCONCLUSO"` con `suave_causas` (s_track_eval.py:2440).
16. **`orient_1_6_deg` previa al salto**: la referencia es la orientación escrita anterior al grupo de giro, no la primera ya filtrada (s_track_eval.py:2098).

### Tests que fallan antes y pasan después (uno por BLOQ/MAY)

Todos en `test_s_track2.py` salvo el detector: `test_v2_mascaras_por_detalle_y_vacia_no_cae_a_sin_mascara` (h1), `test_v2_calibrate_detector_fondo_subpixel` (h2), `test_v2_detector_sin_calibracion_de_fondo_inconcluso` (h3), `test_v2_minimo_20_tambien_en_ventanas_inferidas` (h4), `test_v2_tlect_tmarca_todos_los_casos_y_hook_condicionado` (h5), `test_v2_suave_entrada_desfasada_falla` (h6), `test_v2_suave_primer_frame_de_tramo_se_comprueba` (h7), `test_v2_suave_sin_grupos_o_sin_cuaterniones_inconcluso` (h8), `test_v2_ropa_cobertura_insuficiente_inconcluso` (h9), `test_v2_ropa_sin_calibracion_contraste_mira_inconcluso` (h10), `test_v2_suave_error_entre_2_y_5_porciento_falla` (h11, contra mutante 0,05), `test_suave_quatlerp_falla_en_giro` endurecido (h12), `test_v2_s2_completo_positivo_e_imagenes` + derivada 15 (h13), `test_v2_regimen_inconcluso_por_fps_no_entra_en_acuerdo` (h14), `test_v2_informe_finito_y_regimenes_ausentes_inconcluso` (h15) y `test_v2_suave_orient_1_6_desde_antes_del_salto` (h16). Antes de aplicar los arreglos del evaluador corrían 5 FAIL + 1 ERROR en la primera tanda de discriminadores; el resto fallaba al incorporarse.

### Tabla fixture → esperado → obtenido

| Fixture | Esperado | Obtenido |
|---|---|---|
| `s2_completo` | PASA, ventanas ≥20, imagen en toda captura | PASA (`test_v2_s2_completo_positivo_e_imagenes`) |
| `s2_pocas15`/`pocas_capturas` (giro1 mount0 a 15) | INCONCLUSO muestreo | INCONCLUSO `insufficient_sampling`, `n_shots=15`, exit 2 |
| `suave_ok` | T-suave PASA, 5 grupos | PASA; `orient_1_6_deg` ≈72° desde orientación previa |
| `suave_frac35` | FALLA 2–5 % | FALLA `suave_frac_exceeded`, err 0,035006; mutante 0,05 → PASA |
| `suave_entrada_desfasada` | FALLA §16 | FALLA `entrada_desfasada` |
| `suave_reset_tramo` | FALLA primer frame de tramo | FALLA en `s03` |
| `suave_quatlerp` | FALLA angular, arco corto | FALLA `suave_orient_exceeded`, `arc=corto`, norma OK |
| `suave_longarc` | FALLA arco largo | FALLA `arc=largo` |
| `suave_smooth` | FALLA | FALLA `err_max_frac > THRESH_SUAVE_FRAC` |
| `suave60` FPS a 30 con tope 60 | INCONCLUSO régimen | INCONCLUSO `fps_regime`, fuera del acuerdo |
| régimen 30 vs 60 válido | Acuerdo 1/6 s | PASA ambos (`test_suave_acuerdo_entre_regimenes`) |
| `sesgo5` | T-lect/T-marca FALLA | FALLA |
| `fondo_cambiante` | Con máscara pasa, sin máscara falla | OK; detector fondo `p95_bg_px ≤ 0,25` en subpíxel |
| detector sin fondos | INCONCLUSO | INCONCLUSO `sin_calibracion_fondo` |
| `ropa_ok` | Sigue (con calib) | `sigue` en las tres categorías |
| ropa 1 pose válida | INCONCLUSO cobertura | INCONCLUSO `ropa_cobertura_insuficiente` |
| ropa sin calib | Mira INCONCLUSO, numérica informativa | INCONCLUSO `calib_inconcluso`, `p95_m` finito |
| `ropa_falla` | Mochila no sigue | `no_sigue` |
| `pasa` heredada S-track·1 | PASA exit 0 | PASA exit 0 |
| `delay1` / `roll_defect` heredados | FALLA exit 1 | FALLA exit 1 |
| `low_coverage` heredada | INCONCLUSO exit 2 | INCONCLUSO exit 2 |

### Gate vuelta 2

Comandos corridos en `C:\tmp\dsbx-strack2\eval\DayZSandbox_dev` con el intérprete del runtime de Codex (numpy/Pillow disponibles; `C:\Python314\python.exe` sigue sin numpy en esta sesión y no se instaló nada):

```
& C:\Users\guill\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s qa/strack/tests -t .
Ran 39 tests in 1616.013s
OK

& C:\Users\guill\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest qa.tests.test_stdlib_only -v
Ran 1 test in 0.174s
OK
```

39 tests: la suite heredada de S-track·1, detector/ventanas y los tests de S-track·2 incluidos los discriminadores `test_v2_*` de los hallazgos 1–16. El `exit_code 1` que devuelve el harness de PowerShell es su `NativeCommandError` al capturar stderr de `python.exe`; la señal válida es la salida literal de unittest (`OK`) en ambas corridas.

---

## Vuelta 3 (revisión de Sol, `LAST_v2.md`)

### Qué cambió por hallazgo

1. **BLOQ h8 — observaciones ausentes en T-suave**: en [s_track_eval.py](DayZSandbox_dev/qa/strack/s_track_eval.py) (`evaluate_suave_run`, bloque de grupos) cada frame evaluado exige `cam.pos` y el cuaternión escrito `cam.q`; si falta alguno, o el error del grupo no está definido en todos sus frames, el grupo es INCONCLUSO `sin_observaciones_validas` y la cobertura de la fila ya no es un `1.0` fijo sino la fracción de frames con error definido. Test: `test_v3_suave_sin_cam_pos_tras_salto_inconcluso` y `test_v3_suave_sin_q_escrito_no_certifica_norma` (antes PASA; después INCONCLUSO).
2. **BLOQ — tiempo §16**: el origen del salto es explícito (instante `t_ms` del frame previo al grupo) y la orientación a 1/6 s se interpola con fechas finales `t_ms` sin sumar `dt`. Test con oráculo analítico e intervalos irregulares (6×1/60 + 2×1/30): `test_v3_suave_tiempos_irregulares_oraculo_analitico` (antes 66,73°; después ≈72,46° y PASA).
3. **BLOQ h14 — acuerdo entre regímenes**: a `by_label` solo entran etiquetas `giro*` cuya fila no es INCONCLUSO y con `orient_1_6_deg` válido; una corrida `sin_estimulo` ya no suspende a la válida. Test: `test_v3_sin_estimulo_no_entra_en_acuerdo`.
4. **BLOQ — giro de 20°**: antes de juzgar se validan amplitud (150–190°), sentido firmado y objetivo del guion en `cam_raw`; estímulo distinto → INCONCLUSO `estimulo_giro_invalido`. El error sigue dividiéndose entre los 170° del guion validado. Tests: `test_v3_giro_de_20_grados_no_certifica` (fixture `mode="giro20"` en [make_fixtures.py](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py)).
5. **BLOQ — posición durante los giros**: la rama angular también comprueba `err_pos_frac` (incluidos los frames previos `tramo=4, giro=0`, que alimentan `giro+170` sin ser un grupo propio) y `err_max_frac` es el máximo entre fracción angular y de posición. Test: `test_v3_posicion_en_giros_y_previo` (+1 m en giros y solo en el previo; antes PASA, después FALLA).
6. **BLOQ — FPS por cadencia**: `fps_measured` = frames / tiempo transcurrido de los intervalos `dt` (con `t_ms` como final de cada intervalo, §16), con `fps_median` (1/mediana de `dt`) informado aparte en cada fila; se comprueba además la continuidad de frames (`has_gaps` → INCONCLUSO `continuidad_frames`). Test: `test_v3_fps_cadencia_real_no_mediana` (`dt=[1/60,1/60,0.1]` repetido, respuesta correcta vía `dt_pattern` del generador; antes 60 FPS y PASA, después 22,5 FPS, mediana 60 e INCONCLUSO).
7. **BLOQ — coherencia caso/régimen/tope**: si `fps_cap` no coincide con el régimen del caso (`suaveNN`) → INCONCLUSO `fps_cap_incoherente`, y los FPS se miden contra el régimen que se certifica. Test: `test_v3_caso_regimen_y_tope_incoherentes` (`caso=suave30` con `fps_cap=60` ya no escribe `decisions.suave["30"]="PASA"`).
8. **BLOQ — máscara de un hook no bloquea a los demás**: la calibración del detector usa la primera pareja válida (boca+recámara) de `mask_by_hook`; si ninguna pareja es válida conserva la primera y el detector queda INCONCLUSO por `mascara_vacia`, pero un hook descartado no invalida al válido. Test: `test_v3_mascara_vacia_de_un_hook_no_bloquea_otro` (`mount0_Ha` vacío, `mount0_Hb` válido → detector PASA).
9. **BLOQ — SHA e imagen consumida**: en `load_marcas`, si existen la PNG validada y el BMP homónimo que consume el detector, se exige además que sus píxeles decodificados sean idénticos; si difieren, la marca se descarta (`imagen_distinta_png_bmp`). Test: `test_v3_sha_png_no_valida_bmp_distinto`.
10. **BLOQ — ventanas exigidas por caso**: con campo `giro`, `_require_expected_windows` añade como vacías `giro1|giro2|giro3|resto` ausentes en los bucles de T-lect y T-hook, y cada repetición ausente sale INCONCLUSO. Test: `test_v3_follow_sin_giro2_ni_giro3_inconcluso` (`follow` solo con `giro1` ya no elige hook).
11. **MAY h9 — T-ropa con huecos**: la cobertura se calcula sobre el span de frames esperado (máx−mín+1) y `has_gaps` fuerza INCONCLUSO `ropa_cobertura_insuficiente`. Test: `test_v3_ropa_con_huecos_inconcluso` (frames 0, 60 y 119; antes cobertura 100 % y `sigue`, después INCONCLUSO).
12. **MAY — máscara anclada a la marca**: `build_masks_from_run` ya no sigue la proyección de la lectura (a); en `mount0` (montaje rígido) los cultivos se anclan a la marca de cada detalle. Test: `test_v3_mascara_anclada_a_marca_no_a_lectura_a` (proyección de (a) oscilando ±60 px, arma fija en imagen; antes máscara vacía, después válida y centrada).
13. **MAY — fondo cambiante con dos detalles y ángulo**: `calibrate_detector` pega y detecta boca y recámara sobre cada fondo, acumula el error de ambos en `p95_bg_px` y el ángulo del segmento en el nuevo `p95_bg_deg`, que también gatea con `DETECTOR_MAX_DEG`. Test: `test_v3_fondo_cambiante_ambos_detalles_y_angulo` (señuelo exacto de recámara a −18,−18 px de cada objetivo, con disco de recámara de 8 px para no solapar el señuelo; antes PASA solo con la boca, después no PASA).
14. **MAY — marcas por fase**: el generador (`_write_tracking_run` en [make_fixtures.py](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py)) selecciona las cinco marcas del brief §4 (primera estable, mitad de cada giro y mitad del resto) en vez de las cinco primeras capturas, y `_eval_tmarca_rows` exige esos cinco `momento` utilizables por lectura; si falta una fase → INCONCLUSO `marcas_fases_ausentes`. Test: `test_v3_marcas_por_fase_y_falta_de_fase_inconcluso`.
15. **MAY — detalle de mira dibujado en ropa**: `_write_ropa_run` define tres giros (`giro` 1–3), captura y marca las fases estable/giro1/giro2/giro3/resto y dibuja boca, recámara y mira en sus posiciones de verdad del mundo generado (proyección del generador, independiente del evaluador) en cada captura marcada. Test: `test_v3_ropa_detalle_mira_dibujado_y_fases` (antes la marca de mira caía sobre fondo plano; después hay textura en la marca en todas las fases).

**PREMISA (no es código, no se ha «arreglado»):** que el detalle marcado a mano coincida con el punto de memoria proyectado solo se puede contrastar en el banco real. Queda dicho en «LO QUE NO PUDE VERIFICAR».

Referencias `path:line` por hallazgo: (1) [s_track_eval.py:2117](DayZSandbox_dev/qa/strack/s_track_eval.py:2117) y [test_s_track2.py:466](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:466); (2) [s_track_eval.py:2135](DayZSandbox_dev/qa/strack/s_track_eval.py:2135) y [test_s_track2.py:501](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:501); (3) [s_track_eval.py:2577](DayZSandbox_dev/qa/strack/s_track_eval.py:2577) y [test_s_track2.py:535](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:535); (4) [s_track_eval.py:2243](DayZSandbox_dev/qa/strack/s_track_eval.py:2243), [make_fixtures.py:681](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py:681) y [test_s_track2.py:553](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:553); (5) [s_track_eval.py:2095](DayZSandbox_dev/qa/strack/s_track_eval.py:2095) y [test_s_track2.py:563](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:563); (6) [s_track_eval.py:1973](DayZSandbox_dev/qa/strack/s_track_eval.py:1973), [make_fixtures.py:611](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py:611) y [test_s_track2.py:579](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:579); (7) [s_track_eval.py:2227](DayZSandbox_dev/qa/strack/s_track_eval.py:2227) y [test_s_track2.py:592](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:592); (8) [s_track_eval.py:2341](DayZSandbox_dev/qa/strack/s_track_eval.py:2341) y [test_s_track2.py:607](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:607); (9) [s_track_eval.py:203](DayZSandbox_dev/qa/strack/s_track_eval.py:203) y [test_s_track2.py:624](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:624); (10) [s_track_eval.py:254](DayZSandbox_dev/qa/strack/s_track_eval.py:254) y [test_s_track2.py:642](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:642); (11) [s_track_eval.py:1879](DayZSandbox_dev/qa/strack/s_track_eval.py:1879) y [test_s_track2.py:656](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:656); (12) [s_track_eval.py:411](DayZSandbox_dev/qa/strack/s_track_eval.py:411) y [test_s_track2.py:669](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:669); (13) [s_track_eval.py:1174](DayZSandbox_dev/qa/strack/s_track_eval.py:1174) y [test_s_track2.py:694](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:694); (14) [s_track_eval.py:1761](DayZSandbox_dev/qa/strack/s_track_eval.py:1761), [make_fixtures.py:550](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py:550) y [test_s_track2.py:716](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:716); (15) [make_fixtures.py:742](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py:742) y [test_s_track2.py:732](DayZSandbox_dev/qa/strack/tests/test_s_track2.py:732).

### Tabla fixture → esperado → obtenido (vuelta 3)

| Fixture / entrada | Esperado | Obtenido |
|---|---|---|
| `suave_ok` sin `cam.pos` 0,5 s tras cada salto | INCONCLUSO | INCONCLUSO `sin_observaciones_validas` |
| `suave_ok` sin `cam.q` escrito en tramo 4 | INCONCLUSO (norma no certificable) | INCONCLUSO en ambos giros |
| Tiempos irregulares 6×1/60+2×1/30, respuesta correcta | PASA, `orient_1_6_deg` ≈ 72,46° | PASA, dentro de 70–75° |
| 30 FPS válido + 60 FPS `sin_estimulo` | 30 PASA, 60 INCONCLUSO | 30 PASA, 60 INCONCLUSO |
| `giro20` (objetivos ±20° con etiquetas ±170°) | INCONCLUSO | INCONCLUSO `estimulo_giro_invalido` |
| +1 m en `cam.pos` durante los giros / solo en el previo | FALLA | FALLA `suave_frac_exceeded` |
| `dt=[1/60,1/60,0.1]` repetido, respuesta correcta | INCONCLUSO, cadencia 22,5 FPS | INCONCLUSO `fps_regime`, `fps_measured`≈22,5, `fps_median`≈60 |
| `caso=suave30` con `fps_cap=60` y datos de 60 FPS | INCONCLUSO | INCONCLUSO `fps_cap_incoherente` |
| `mount0_Ha` máscaras vacías + `mount0_Hb` válidas | Detector PASA | Detector PASA |
| PNG marcada válida + BMP homónimo distinto | Marca descartada | Descartada `imagen_distinta_png_bmp` |
| `follow` solo con `giro1` y `resto` | INCONCLUSO por repetición | `giro2`/`giro3` INCONCLUSO, sin hook en `follow` |
| `ropa_ok` solo con frames 0, 60, 119 | INCONCLUSO cobertura | INCONCLUSO `ropa_cobertura_insuficiente` |
| Máscara con (a) oscilando ±60 px, arma fija | Máscara válida centrada en la marca | Máscara válida, centro verdadero |
| Fondo con señuelo de recámara | Detector no PASA | No PASA (`p95_bg_px`/`p95_bg_deg` fuera de umbral) |
| Marcas sin fase `giro2` | T-marca INCONCLUSO | INCONCLUSO `marcas_fases_ausentes` |
| `ropa_ok` (detalle de mira) | Textura en la marca en cada fase | `_crop_std(mira) ≥ TEXTURE_MIN_STD` en las 5 fases |
| `s2_completo` (positivo) | PASA con marcas por fase | PASA; momentos = {estable, giro1, giro2, giro3, resto} por corrida |

---

## Vuelta 4 (revisión de Sol, `LAST_v3.md`; última vuelta)

No se reabre lo que Sol dio por cerrado en la vuelta 3 (1–3, 5–7, 9–13 y 15 de la vuelta 2, y h8/h9/h14). Las dos carpetas `tmp_znawivs` y `tmpgcrxsyn0` de `DayZSandbox_dev/` no se han tocado ni se depende de ellas.

### Qué cambió por hallazgo

1. **BLOQ — `lata.a=null` en el frame del salto:** en [s_track_eval.py:2126](DayZSandbox_dev/qa/strack/s_track_eval.py:2126) el objetivo de posición ya no cae a `cam_raw.pos` cuando falta `lata.a` (queda `None`), y en [s_track_eval.py:2331](DayZSandbox_dev/qa/strack/s_track_eval.py:2331) cualquier frame juzgado (grupo, más el previo en `giro+170`) sin `lata.a` válida hace el grupo INCONCLUSO `lata_ausente` ([s_track_eval.py:2348](DayZSandbox_dev/qa/strack/s_track_eval.py:2348)). Test: `test_v4_suave_lata_ausente_en_salto_inconcluso` (antes PASA con error 0; después INCONCLUSO).
2. **BLOQ — giro truncado sin t = 1/6 s:** en [s_track_eval.py:2332](DayZSandbox_dev/qa/strack/s_track_eval.py:2332) un giro sin `orient_1_6`/`orient_1_6_deg`, sin origen, o con duración < 1 s (el contrato lo mantiene 4 s y la fixture 2 s; cuatro frames a 60 FPS son 0,07 s) es INCONCLUSO `giro_incompleto` ([s_track_eval.py:2350](DayZSandbox_dev/qa/strack/s_track_eval.py:2350)), así que no sale PASA con `orient_1_6_deg=null` ni entra en el acuerdo entre regímenes (que ya exigía fila no INCONCLUSA). Test: `test_v4_suave_giro_truncado_sin_1_6_inconcluso` (antes PASA con `orient_1_6_deg=None`; después INCONCLUSO).
3. **BLOQ — interpolación a 1/6 s:** en [s_track_eval.py:2233](DayZSandbox_dev/qa/strack/s_track_eval.py:2233) la interpolación ya no es lineal en el ángulo: el ángulo que falta hasta el objetivo constante del giro decae como `exp(-t/smooth_s)`, así que se interpola linealmente su logaritmo entre los dos frames que abrazan t = 1/6 s usando sus `t_ms`/`dt` reales. Test con oráculo analítico: `test_v4_suave_interpolacion_exponencial_intervalos_irregulares` (dos primeros intervalos de 100 ms, resto a 60 FPS; antes 71,2093° y FALLA, después ≈72,4619° = `170*(1-exp(-(1/6)/0.3))` y PASA).
4. **BLOQ (v2-4) — estímulo de ±170°:** constante `GIRO_TARGET_TOL_DEG = 1.0` en [s_track_eval.py:48](DayZSandbox_dev/qa/strack/s_track_eval.py:48) — el objetivo se escribe como rotación exacta, extraerlo con `atan2`/`acos` en doble precisión yerra muy por debajo de 0,01°, así que 1,0° deja dos órdenes de margen sobre el ruido numérico y es diez veces menor que la desviación de un objetivo de 160° — y validación en [s_track_eval.py:2323](DayZSandbox_dev/qa/strack/s_track_eval.py:2323): amplitud y avance firmado a ±170° dentro de esa tolerancia y objetivo constante durante el giro (desviación máxima entre lecturas `cam_raw` del grupo ≤ tolerancia), si no INCONCLUSO `estimulo_giro_invalido`. El generador gana el modo `giro160` en [make_fixtures.py:683](DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py:683). Test: `test_v4_giro_160_no_certifica_170` (antes PASA; después INCONCLUSO).
5. **BLOQ (v2-8) — procedencia de las máscaras:** `calibrate_detector` ([s_track_eval.py:1216](DayZSandbox_dev/qa/strack/s_track_eval.py:1216)) acepta `mask_by_hook` y calibra cada pareja válida solo con corridas de su hook (su captura fuente y sus centros, vía `_calibrate_detector_once` en [s_track_eval.py:1028](DayZSandbox_dev/qa/strack/s_track_eval.py:1028)), probando la siguiente pareja válida si una no pasa y saltándose las vacías; `evaluate` lo pasa en [s_track_eval.py:2474](DayZSandbox_dev/qa/strack/s_track_eval.py:2474). Sin `mask_by_hook` se conserva el camino previo. Test: `test_v4_calibracion_por_pareja_de_mascaras_con_procedencia`, con la imagen de Ha plana dentro de las máscaras de Hb (antes `TypeError`/fuente de Ha incompatible; después detector PASA con la pareja de Hb).
6. **BLOQ — vínculo PNG consumida:** `load_marcas` ([s_track_eval.py:172](DayZSandbox_dev/qa/strack/s_track_eval.py:172)) resuelve primero la imagen consumida con `_shot_path` ([s_track_eval.py:198](DayZSandbox_dev/qa/strack/s_track_eval.py:198)) y vincula siempre su contenido con la PNG validada por sha256, también cuando solo hay PNG (si difieren, descarte `imagen_distinta_png_bmp`). Test: `test_v4_marcas_solo_png_vincula_imagen_consumida` (sin BMP, `entry.png` apunta a otra PNG válida pero distinta de `f000120.png`; antes marca válida, después descartada).
7. **MAY — textura en el candidato detectado:** en [s_track_eval.py:1656](DayZSandbox_dev/qa/strack/s_track_eval.py:1656) la proyección de «a» ya no descarta la captura con `_textured`; los centros de búsqueda son, en orden, la proyección de «a», la detección previa y la marca, y la textura (`_crop_std ≥ TEXTURE_MIN_STD`) se comprueba en el candidato detectado. Test: `test_v4_deteccion_no_descartada_por_proyeccion_de_a` («a» oscilando ±60 px, «f» correcta y fondo plano fuera del arma; antes todas las detecciones `None`, después detección en todas y T-lect de «f» PASA).
8. **MAY (v2-14) — T-marca y T-ropa condicionan la decisión:** la lectura ganadora exige T-marca PASA en todas sus corridas, no solo «no FALLA» ([s_track_eval.py:2569](DayZSandbox_dev/qa/strack/s_track_eval.py:2569)), así que sin la marca `giro2` de `mount0` no se selecciona lectura, `mount0` queda sin hook y el código de salida es 2; y T-ropa exige la cobertura manual completa de la mira (las cinco fases y todas sus marcas) en [s_track_eval.py:1893](DayZSandbox_dev/qa/strack/s_track_eval.py:1893), con INCONCLUSO `mira_marca_incompleta` si falta alguna. Tests: `test_v4_sin_marca_giro2_mount0_no_selecciona_lectura_ni_exit0` y `test_v4_ropa_una_sola_marca_mira_no_sigue` (antes lectura «a», `exit_code` no condicionado y `sigue` con una sola marca; después lectura `null`, exit 2 e INCONCLUSO).

**PREMISA de Sol (no es código, no se ha «arreglado»):** que la baja varianza temporal identifique píxeles del arma solo se contrasta en el banco con fondos distintos de los usados para construir la máscara. Queda añadido a «LO QUE NO PUDE VERIFICAR».

Cada test de arriba falló antes del arreglo y pasa después (corrida enfocada de los 9 tests `test_v4_*`: antes 8 FAIL + 1 ERROR, después 9 OK).

### Tabla fixture → esperado → obtenido (vuelta 4)

| Fixture / entrada | Esperado | Obtenido |
|---|---|---|
| `suave_ok` con `lata.a=null` solo en cada frame de salto | INCONCLUSO | INCONCLUSO `lata_ausente`, régimen 60 INCONCLUSO |
| `suave_ok` truncado tras 4 frames de `giro-170` | INCONCLUSO, sin certificar el régimen | INCONCLUSO `giro_incompleto`, `orient_1_6_deg=None`, régimen no PASA |
| Giro correcto, intervalos 100 ms + 60 FPS, oráculo analítico | PASA, `orient_1_6_deg` ≈ 72,4619° | PASA, dentro de 0,6° del oráculo |
| Objetivo de +160° (`giro160`) con respuesta correcta | INCONCLUSO | INCONCLUSO `estimulo_giro_invalido` en ambos giros |
| Ha con máscaras vacías e imagen incompatible + Hb válida | Detector PASA con la pareja de Hb | PASA (`mask_hook=Hb`) |
| Sin BMP: PNG validada distinta de la PNG consumida | Marca descartada | Descartada `imagen_distinta_png_bmp` |
| «a» oscila ±60 px, «f» correcta, fondo plano | Detección y T-lect de «f» PASA | Detecciones en las 25 capturas, T-lect «f» PASA |
| `s2_completo` sin marca `giro2` de `mount0` | Sin lectura, sin hook en `mount0`, exit 2 | Lectura `null`, hook `mount0` `null`, `exit_code=2` |
| `ropa_ok` con una sola marca de mira | T-ropa no `sigue` | INCONCLUSO `mira_marca_incompleta`, mira no `sigue` |

### Gate vuelta 4

**Fallo preexistente encontrado por el gate completo (no causado por la vuelta 4):** la primera corrida del gate dio `FAILED (failures=1)` — `test_delay1_fixture_fails_with_exit_code_1` salía con `exit_code=2` porque el detector quedaba INCONCLUSO (`p95_bg_px=999`) en la fixture `delay1`. Reproducido con la llamada antigua a la calibración (sin `mask_by_hook`): el mismo 999, así que no lo introdujo el hallazgo 5. La causa: la fuente de calibración era la primera captura elegible (`lookat`, con la boca exactamente en (960, 540)), cuya plantilla de boca degrada sobre los fondos sintéticos (corr 0,78–0,86, un caso bajo `CORR_MIN`), mientras que la fuente de `mount0` —de donde sale la máscara— calibra limpia (corr 0,88–0,96, error ≤ 0,26 px). Arreglo en la misma línea de procedencia del hallazgo 5: la fuente se busca primero en `mount0` ([s_track_eval.py:1036](DayZSandbox_dev/qa/strack/s_track_eval.py:1036)); con él, `delay1` vuelve a `exit_code=1` y el detector a PASA (`p95_bg_px=0,258`).

Comandos del encargo, desde `C:\tmp\dsbx-strack2\eval\DayZSandbox_dev`. Salida literal de la suite completa (intérprete con las dependencias de `requirements.txt`; el `exit_code 1` del harness de PowerShell es su `NativeCommandError` al capturar el stderr de `python.exe`, la señal válida es el `OK` de unittest):

```
& C:\Users\guill\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s qa/strack/tests -t . -v
Ran 64 tests in 1426.241s
OK

& C:\Users\guill\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest qa.tests.test_stdlib_only -v
Ran 1 test in 0.364s
OK
```

El gate `qa.tests.test_stdlib_only` también pasa literal con el intérprete del encargo:

```
C:\Python314\python.exe -m unittest qa.tests.test_stdlib_only -v
Ran 1 test in 0.242s
OK
```

La suite completa con `C:\Python314\python.exe` sigue sin poder correr en esta sesión (ver DISPUTAS, punto 1: ese intérprete no tiene `numpy` y el encargo prohíbe instalar paquetes):

```
C:\Python314\python.exe -m unittest discover -s qa/strack/tests -t .
ModuleNotFoundError: No module named 'numpy'
Ran 2 tests in 0.168s
FAILED (errors=3)
```

64 tests: los heredados de S-track·1, detector/ventanas, los de S-track·2 de las vueltas 2 y 3 y los 9 nuevos `test_v4_*`. Todo verde, y cada fixture negativa nueva da el veredicto de la tabla anterior.

## LO QUE NO PUDE VERIFICAR (añadido en la vuelta 4)

- **Premisa de la máscara por varianza temporal (Sol, vuelta 3):** que la baja varianza temporal (`std < MASK_STD_MAX`) identifique píxeles del arma no está demostrado: un fondo uniforme pegado a la marca también cumple `std < 8`, y la calibración reutiliza esa misma máscara para pegar el supuesto arma, así que no verifica independientemente su contorno. Solo se puede contrastar en el banco con fondos distintos de los empleados para construir la máscara; las fixtures sintéticas no lo prueban.






