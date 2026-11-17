# Informe de la vuelta 5 del evaluador S-track·2 (coherencia de timeline) y endurecimiento de `check_runs.py`

Base: copia del evaluador integrado en `4ae0727` más los cambios sin confirmar del orquestador en
`check_runs.py`. Veredicto de partida: `SOL_checkruns_v1.md` (NEEDS-WORK, BLOQ=4). No se ha tocado el mod
(`DZS_STrack/`), ni los mutantes (`mutants/`), ni `CONTRACT.md`. Sin commit ni push.

Idea central de la vuelta: el filtro del mod integra `dt` (el mismo valor que registra,
`STRACK_Session.c:1347` y `:1577`), así que el eje del filtro es **Σdt acumulado**; `t_ms` (`GetTickTime`,
otro reloj) solo queda para medidas de reloj de pared. Mezclar los dos relojes era H1.

## H1 — Una sola timeline por consumidor (`s_track_eval.py`)

Cambios:

- Nuevo ayudante `_cum_dt_s(samples)` en [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2044):
  instante final de cada frame acumulado desde `dt`. Es el eje de todas las medidas del filtro.
- Origen del salto de giro y orientación a 1/6 s: antes se fechaban con `t_ms`
  ([s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2280) y
  [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2304)); ahora `t_start`,
  `prev_t` y `t_eff` salen de `cum_dt`. Esto elimina el falso `suave_fps_agree_exceeded` de Sol: con el tirón
  real (dt 8+32 ms frente a Δt_ms 36+5 ms) dos cámaras correctas diferían 1,7° al medir a 1/6 s sobre `t_ms`.
- Duración del grupo de giro dentro de T-suave (`giro_incomplete`, «al menos 1 s»): pasa de `t_ms` a Σdt en
  [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2416), porque es tiempo del filtro.
  La duración de giro de 4,0 ± 0,3 s de CONTRACT §9 sigue midiéndose con `t_ms` en `check_runs.py` (reloj de pared).
- Referencia de T-suave: ya simulaba frame a frame con `dt` (equivalente a integrar en Σdt); sin cambio de
  comportamiento, queda documentado. El filtro de `mount03` igual: aplicar `alpha` frame a frame con el `dt`
  de cada frame **es** integrar en Σdt; comentario en
  [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:1536).
- Ventanas sin campo `giro` (`detect_windows`): se quedan en `t_ms`, con comentario en
  [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:1286), porque son medida de
  reloj de pared y no fechan nada del filtro.

Consumidor que no puede ir solo en Σdt (**INCONCLUSO declarado**): la respuesta en la **frontera de un salto**
(primer frame de un giro o frame en que `lata.a` salta). Ahí Σdt solo no distingue un `dt` genuino de tirón de
uno adulterado que compensa (caso de Sol: 30,6667 + 2,6667 ms con Δt_ms regular), porque la cámara retrasada
que responde 0,008849 m coincide exactamente con la referencia Σdt. Por eso, si en ese frame `dt` y Δt_ms
discrepan más de `SUAVE_DT_TMS_TOL_MS`, el grupo queda `INCONCLUSO` con causa `intervalo_salto_incoherente`
([s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2410) y
[s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2434)), nunca PASA ni FALLA:
con los datos de hoy no se puede distinguir tirón genuino de adulteración, y el comportamiento del mod con
tirones en `suave*` aún no se ha observado (ver el final).

Tests (fallaban antes, pasan después) en
[test_s_track_timeline_r5.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_s_track_timeline_r5.py):

- `test_tiron_real_en_giro_correcto_sin_falso_acuerdo_fps`: patrón real de `calib_Ha` (8+32 frente a 36+5 ms)
  colocado justo antes del instante 1/6 s de un giro correcto en 60 FPS, con 30 FPS correcto al lado. Antes:
  `suave_fps_agree_exceeded` en ambos regímenes. Después: PASA en 30 y 60, sin esa causa.
- `test_dt_compensado_en_salto_con_camara_retrasada_no_pasa`: caso de Sol (30,6667 y 2,6667 ms alrededor de
  un salto de la lata en `s03`, cámara que responde 0,008849 m). Antes: `s03` PASA. Después: `s03`
  INCONCLUSO por `intervalo_salto_incoherente` y la decisión del régimen no es PASA.

## H2 — Intervalo de carga: misma definición y mismo trato en los dos ficheros

Definición (justificada en el código de ambos): el intervalo de carga es **solo el par de frames 0→1**.
El mod inicializa `m_Frame = -1` y lo sube a 0 antes de la primera captura, con el armado (`TryArm`, creación
de la cámara) en ese mismo `OnUpdate`; el tirón de la creación cae en el intervalo que acaba en el frame 1.
Que el primer par visto sea el de carga solo está probado si sus frames son exactamente 0 y 1: una corrida que
empieza en otro frame no tiene intervalo exento. Implementación:
`_indice_intervalo_carga` en [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2064)
y `_es_carga` en [check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:105).

Trato idéntico:

- En el evaluador, ese intervalo queda fuera de `N/Σdt` en el cálculo de FPS
  ([s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2111)). Antes contaba:
  el ejemplo de Sol (`dt[1]=5 s`) daba 53,1 FPS e INCONCLUSO `fps_regime` espurio.
- En `check_runs.py`, ese intervalo queda fuera de la deriva acumulada y de la mediana de `dt` de giros
  ([check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:230)), pero **no** queda
  exento de las cotas ni de la finitud: una carga de 5 s o un salto de `t_ms` de 100 s en ese par invalidan.
- Cotas por frame (H2): `INTERVALO_MAX_MS = 100.0` para cada `dt` y cada Δt_ms, en
  [check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:53). Justificación escrita
  junto a la constante: el máximo real tras la carga en la fixture es 48 ms (Hb) y el de carga 39 ms; 100 ms
  duplica ese máximo y es 3× el nominal del régimen más lento (30 FPS). Valores reales calculados de
  `fixtures/real_clock_calib.json`: Ha, dt máximo 39 ms y Δt_ms máximo 39 ms; Hb, 48 ms y 48 ms.

Tests: `test_intervalo_carga_fuera_de_fps` (evaluador, con `dt=2 s` en el frame 1 la cadencia sigue siendo
60 FPS y el régimen PASA), `test_carga_extrema_en_dt_invalida`, `test_salto_extremo_de_t_ms_en_carga_invalida`
y `test_primer_par_visto_no_es_carga_sin_frame_cero` en
[test_check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_check_runs.py).

## H3 — Duplicados: `check_runs` valida las filas canónicas del evaluador

El evaluador (`_read_run`, `s_track_eval.py:470`) conserva la última fila de cada frame (rescatando el `shot`).
`check_runs.py` ahora construye las mismas filas canónicas y valida sobre ellas
([check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:182)); antes ordenaba y saltaba
el par duplicado sin mirar la segunda fila. Dos filas del mismo frame que difieren en `t_ms` o en `dt`
invalidan la corrida (motivo `frames duplicados con t_ms o dt distintos`), así el `dt=300 ms` oculto tras un
duplicado de Sol ya no pasa.

Tests: `test_duplicado_con_dt_distinto_invalida` y `test_duplicado_con_t_ms_distinto_invalida`.

## H4 — Valores no finitos

En [check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:79) el parser JSON rechaza
`NaN`/`Infinity` literales (`parse_constant`) y cualquier flotante no finito (`parse_float`, cubre `1e999`).
Después, cada fila cruda —antes de acumular, deduplicar o excluir nada, incluido el intervalo de carga—
exige `t_ms` y `dt` finitos y `dt > 0`
([check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:158)). El `NaN` que
desactivaba la deriva para el resto de la corrida ya no entra.

Tests: `test_valores_no_finitos_o_no_positivos_invalidan` (dt NaN, dt cero, dt negativo, t_ms NaN) y
`test_infinito_literal_en_json_invalida`.

## H5 — Umbral de deriva desde los consumidores (respuesta 5 de Sol)

`DERIVA_MAX_MS = 50.0` se mantiene, pero ya no «porque supera el máximo observado»: la razón está escrita
junto a la constante en [check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:47).
Tras H1, `t_ms` solo alimenta la duración de giro (4,0 ± 0,3 s) y las ventanas sin etiqueta (pausas de
0,15 s). La oscilación de deriva dentro de una ventana es como mucho 2·50 = 100 ms: un tercio de la
tolerancia del giro y menos que la pausa que une ventanas. Las derivas reales (27,0 ms Ha; 8,0 ms Hb,
calculadas de la fixture excluyendo la carga) quedan por debajo como comprobación, no como razón.

Tests de borde: `test_deriva_exactamente_en_el_limite_es_valida` (deriva exactamente 50,0 ms, con
dt = 15,625 ms exacto en binario) y `test_deriva_justo_por_encima_del_limite_invalida` (50,5 ms).

## Tests que faltaban (respuesta 6 de Sol)

Además de los de borde de deriva: `test_hc_con_calib_ha_invalida` (negativa Hc con `calib_Ha` presente pero
inválida: motivo `calib_Ha invalida`; antes solo se cubría Ha ausente y Ha válida), carga extrema y duplicados
y no finitos (arriba), y `test_fixture_real_calibraciones_validas`, que reconstruye `calib_Ha` y `calib_Hb`
desde `fixtures/real_clock_calib.json` y exige VALIDA en ambas.

## Constantes nuevas (formato CONTRACT §4/§13: una por línea, a nivel de módulo)

Evaluador, en [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:50):

```python
SUAVE_DT_TMS_TOL_MS = 6.0
```

Derivación junto a la constante: d(alpha) ≈ (Δdt/smooth)·exp(−dt/smooth) ≤ Δdt/0,3; para no superar
`THRESH_SUAVE_FRAC` (0,02) hace falta Δdt ≤ 6 ms.

`check_runs.py` (no es constante de CONTRACT §4/§13, pero sigue el mismo formato):

```python
INTERVALO_MAX_MS = 100.0
```

Propuesta de contrato (no aplicada; `CONTRACT.md` está fuera del write-set): añadir `SUAVE_DT_TMS_TOL_MS`
a la lista de §13 y la definición de intervalo de carga (frames 0→1) a §16.

## Gate

Entorno: `C:\Python314\python.exe` no trae numpy ni Pillow instalados; se instalaron desde
`qa/strack/requirements.txt` en una carpeta temporal del workspace (`.r5deps`, borrada al terminar) y se
pasó por `PYTHONPATH`. `check_runs.py` es stdlib y no necesita ese añadido.

### Suite completa (desde `DayZSandbox_dev`)

Comando: `C:\Python314\python.exe -m unittest discover -s qa/strack/tests -t .`

```text
----------------------------------------------------------------------
Ran 90 tests in 1909.439s

OK
```

### Stdlib only

Comando: `C:\Python314\python.exe -m unittest qa.tests.test_stdlib_only`

```text
----------------------------------------------------------------------
Ran 1 test in 0.342s

OK
```

### check_runs sobre las calibraciones reales reconstruidas

Comando: `C:\Python314\python.exe qa/strack/check_runs.py <dir temporal con calib_Ha y calib_Hb
reconstruidas desde fixtures/real_clock_calib.json>`

```text
calib_Ha                         VALIDA
calib_Hb                         VALIDA
RESULT 2 validas, 0 invalidas
```

## Vuelta 5b (arbitraje del orquestador sobre la revisión v2 de Sol)

Arbitraje aplicado: B1 queda fuera de contrato. Según CONTRACT §16 el filtro del frame n usa el `dt`
del frame n y el mod registra exactamente ese `dt` (`STRACK_Session.c:318`, `:1347`, `:1577`); el
evaluador juzga el filtro contra el reloj que el filtro usó. Un `dt` registrado distinto del integrado
no puede salir del banco real, y un desajuste entre el `dt` del motor y el tiempo de pared es
comportamiento del motor, no un defecto de cámara. No se añade protección contra un `dt` adulterado.
Se conserva todo lo de la vuelta 5 que pone las medidas del filtro sobre el eje Σdt
([s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2036)).

### 0. Retirada de la guarda de frontera de salto (causa de B2 y M1)

Retirados de [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:41):
la constante `SUAVE_DT_TMS_TOL_MS`, la función `_intervalo_salto_incoherente` y la rama
`INCONCLUSO / intervalo_salto_incoherente` en `evaluate_suave_run`. Ya no queda ninguna referencia a
esos tres nombres en `s_track_eval.py` ni en `check_runs.py` (comprobado por búsqueda). Con esto M1
desaparece por construcción: `s0` (`smooth=0`, `alpha=1`) ya no puede quedar INCONCLUSO por una
guarda que no depende de su respuesta. Se mantienen las medidas del filtro sobre Σdt de la vuelta 5.

Test actualizado (fallaba antes con la guarda, pasa después):
`test_dt_compensado_en_salto_se_juzga_contra_el_dt_registrado` en
[test_s_track_timeline_r5.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_s_track_timeline_r5.py:130):
el caso de Sol (30,6667 + 2,6667 ms con Δt_ms regular y cámara rehecha con el `dt` registrado) ahora
da `s03` PASA y decisión 60 PASA, sin ninguna causa `intervalo_salto_incoherente`. Es el antiguo test
de la guarda con la expectativa invertida según el arbitraje, no un test nuevo de adulteración.

### 1. B2 (BLOQ): el acuerdo entre FPS nunca queda satisfecho porque falte una comparación

En [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2777) se
calcula `acuerdo_pendiente` antes de certificar decisiones. Entre los regímenes cualificados para el
acuerdo (fps válido, hallazgo 14; estímulo de giro válido por etiqueta, hallazgo 3), si la orientación
a 1/6 s de alguno no entra en `by_label` por otra causa (fila INCONCLUSA o ausente en `giro+170` o
`giro-170`), el acuerdo queda pendiente: todas las filas de giro PASA de los regímenes que iban a
certificarse pasan a `INCONCLUSO` con causa `suave_fps_agree_pendiente`
([s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2801)), y su
decisión ya no puede ser PASA. Un régimen FALLA sigue aportando su orientación y no deja el acuerdo
pendiente por sí solo; un régimen descalificado por fps o por estímulo no es una referencia que el
acuerdo necesite (por eso los tests cerrados `test_v2_regimen_inconcluso_por_fps_no_entra_en_acuerdo`
y `test_v3_sin_estimulo_no_entra_en_acuerdo` conservan su expectativa; verificado con una sonda
equivalente construida con `_write_suave_run`: en ambos la decisión de 30 sigue siendo PASA y la de
60 INCONCLUSO).

Test (fallaba antes, pasa después):
`test_acuerdo_fps_pendiente_si_falta_la_referencia_no_certifica_30` en
[test_s_track_timeline_r5.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_s_track_timeline_r5.py:179):
el régimen de 30 lleva un sesgo de 1° durante los primeros 0,5 s del primer giro (el caso de Sol:
73,4619° frente a 72,4619° a 1/6 s, por encima del acuerdo de 0,5° y por debajo del límite individual
de 3,4°) y la referencia de 60 queda INCONCLUSA por otra causa (sin observación válida en un frame de
`giro+170`). Antes: 30 PASA. Después: 60 INCONCLUSO, 30 INCONCLUSO con causa
`suave_fps_agree_pendiente`, nunca PASA.

### 2. M2: sin `INTERVALO_MAX_MS` en `check_runs.py`

Retirada la constante `INTERVALO_MAX_MS` y sus dos usos (por `dt` en cada fila cruda y por Δt_ms en
las filas canónicas) de [check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:160)
y [check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:199): no hay base
contractual para un techo de 100 ms y duplicar el máximo observado (48 ms) no demuestra que un
intervalo mayor corrompa Σdt ni el filtro. Se mantiene: valores finitos y `dt > 0` en cada fila cruda
([check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:166)), rechazo de
`NaN`/`Infinity` en el JSON, `t_ms` estrictamente creciente sobre las filas canónicas
([check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:207)), la política
de duplicados de H3, el par de carga 0→1 como único exento de deriva
([check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:210)) y el límite
de deriva acumulada ([check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:216)).

Test (fallaba antes, pasa después): `test_intervalo_coherente_de_101_ms_es_valido` en
[test_check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_check_runs.py:191):
el run coherente de Sol (un frame de 101 ms con `dt` y Δt_ms coincidentes y deriva ~0) es VALIDA.
Antes de retirar el techo, la salida literal era:

```text
calib_Ha                         INVALIDA  1 intervalos con dt por encima de 100 ms; 1 intervalos con salto de t_ms por encima de 100 ms
RESULT 0 validas, 1 invalidas
```

Consecuencia sobre los tests de la vuelta 5: `test_carga_extrema_en_dt_invalida` y
`test_salto_extremo_de_t_ms_en_carga_invalida` afirmaban la invalidez por ese techo; se han
reescrito como `test_carga_extrema_coherente_es_valida`
([test_check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_check_runs.py:204))
y `test_salto_extremo_coherente_de_t_ms_en_carga_es_valido`
([test_check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_check_runs.py:218)),
con la carga extrema coherente (`dt` y Δt_ms coinciden) y válida. `test_primer_par_visto_no_es_carga_sin_frame_cero`
se conserva: sin frame 0 no hay exención y el `dt` de 5 s sigue invalidando por deriva.

### 3. Umbral de deriva (Sol, «A MEDIAS»): comentario actualizado

Comentario junto a `DERIVA_MAX_MS = 50.0` en
[check_runs.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:53): ya no menciona
ninguna guarda que proteger (no queda ninguna) y dice explícitamente que la corrección del filtro no
depende de `t_ms` en absoluto — el filtro integra el `dt` registrado (CONTRACT §16) y todas sus
medidas van sobre el eje Σdt —, y que `t_ms` solo alimenta la duración de giro (4,0 ± 0,3 s) y las
ventanas sin etiqueta, que son los únicos consumidores para los que vale el límite. El valor no cambia.

### 4. Tests de la vuelta 5 actualizados

Además de los citados: se retiró la aserción de `INCONCLUSO / intervalo_salto_incoherente` del test
del `dt` compensado (punto 0) y se añadieron el test de B2 y el de M2. Las dos calibraciones reales
siguen VALIDAS (ver la puerta). Ninguna constante nueva: las retiradas son `SUAVE_DT_TMS_TOL_MS` del
evaluador e `INTERVALO_MAX_MS` de `check_runs.py`; la causa nueva es `suave_fps_agree_pendiente`.

### Puerta de la vuelta 5b (salida literal)

Entorno: en este sandbox `C:\Python314\python.exe` no ve numpy ni Pillow (constan en el host:
numpy 2.4.4 y Pillow 12.2.0), y el intento de instalarlos en `.r5deps` como en la vuelta 5 falló por
el proxy (`ProxyError('Cannot connect to proxy.', TimeoutError('timed out'))` contra PyPI, en los dos
intentos). Por eso la suite completa con el intérprete prescrito queda `GATE NOT RUN` en su forma
íntegra; abajo va su salida literal de intento y las puertas que sí corrieron.

Suite completa, comando prescrito desde `DayZSandbox_dev`
(`C:\Python314\python.exe -m unittest discover -s qa/strack/tests -t .`):

```text
GATE NOT RUN: numpy y Pillow no visibles en C:\Python314 dentro de este sandbox y PyPI inaccesible por el proxy; los 4 módulos que importan numpy fallan al importar y el resto corre (ver siguiente bloque).
ModuleNotFoundError: No module named 'numpy'
Ran 27 tests in 1.179s
FAILED (errors=4)
```

Los 27 tests que no importan numpy (incluidos los 24 de `check_runs`) pasaron dentro de esa misma
corrida de descubrimiento salvo los 4 errores de importación citados; `test_check_runs` por separado:

```text
Ran 24 tests in 0.824s

OK
```

Tests de timeline de la vuelta 5/5b con el numpy 2.3.4 del Python de Blender 5.1 del host y un stub
mínimo de Pillow en una carpeta temporal borrada después (las rutas `suave` no usan Pillow; solo se
necesitaba que el import de módulo no fallara). Esto no es el intérprete de la puerta y se declara
como verificación sustituta, no como puerta:

```text
test_acuerdo_fps_pendiente_si_falta_la_referencia_no_certifica_30 (qa.strack.tests.test_s_track_timeline_r5.TimelineR5Tests.test_acuerdo_fps_pendiente_si_falta_la_referencia_no_certifica_30) ... ok
test_dt_compensado_en_salto_se_juzga_contra_el_dt_registrado (qa.strack.tests.test_s_track_timeline_r5.TimelineR5Tests.test_dt_compensado_en_salto_se_juzga_contra_el_dt_registrado) ... ok
test_intervalo_carga_fuera_de_fps (qa.strack.tests.test_s_track_timeline_r5.TimelineR5Tests.test_intervalo_carga_fuera_de_fps) ... ok
test_tiron_real_en_giro_correcto_sin_falso_acuerdo_fps (qa.strack.tests.test_s_track_timeline_r5.TimelineR5Tests.test_tiron_real_en_giro_correcto_sin_falso_acuerdo_fps) ... ok
Ran 4 tests in 1.835s

OK
```

Stdlib only (`C:\Python314\python.exe -m unittest qa.tests.test_stdlib_only`):

```text
Ran 1 test in 0.249s

OK
```

`check_runs.py` sobre `calib_Ha` y `calib_Hb` reconstruidas desde
`fixtures/real_clock_calib.json` en una carpeta temporal:

```text
calib_Ha                         VALIDA
calib_Hb                         VALIDA
RESULT 2 validas, 0 invalidas
```

## Vuelta 5c (N1 de Sol v3: un desacuerdo demostrado no se borra por un tercer régimen incompleto)

Sol v3: 0 BLOQ; B2, M1, M2, H1 y el umbral CERRADOS; arbitraje de B1 aceptado. Único punto abierto:
N1 (MAY). No se ha tocado nada más.

### Arreglo

En [s_track_eval.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2795), el bloque de
acuerdo pendiente de la vuelta 5b convertía en `INCONCLUSO` (causa `suave_fps_agree_pendiente`) las filas de
giro `PASA` de todos los regímenes, y el bloque siguiente solo convertía en `FALLA` las que todavía eran
`PASA`: un desacuerdo ya demostrado entre dos regímenes quedaba borrado si un tercer régimen estaba
incompleto. Ahora ese bloque salta los regímenes que están en `disagree_runs` (desacuerdo por pares ya
demostrado, orientación a 1/6 s con diferencia > 0,5°), de modo que conservan el `FALLA` por
`suave_fps_agree_exceeded` que les asigna el bloque siguiente. El régimen incompleto conserva su propia
causa `INCONCLUSO`, y el estado pendiente de la vuelta 5b (B2) sigue aplicando cuando no hay ningún
desacuerdo demostrado. Sin constantes nuevas.

### Test (fallaba antes, pasa después)

`test_desacuerdo_demostrado_no_se_borra_por_tercer_regimen_incompleto` en
[test_s_track_timeline_r5.py](/C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/tests/test_s_track_timeline_r5.py:227):
escenario exacto de Sol v3 — sesgo de guiñada de +1° en los frames 915–929 de `suave30_Hb` (primeros 0,5 s
de `giro+170`; en la fixture sintética, los 15 primeros frames del giro 1 a 30 FPS) y `cam.pos=null` solo
en el frame 4392 de `suave144_Hb` (primer frame de ese giro; en la fixture, el primer frame del giro 1 a
144 FPS), con 30, 60 y 144 FPS y relojes coherentes. A 1/6 s: 73,4619° frente a 72,4619° (> 0,5°).

Antes del arreglo (salida literal):

```text
AssertionError: 'INCONCLUSO' != 'FALLA'
 : {'30': 'INCONCLUSO', '60': 'INCONCLUSO', '144': 'INCONCLUSO'} (causas: suave_fps_agree_pendiente / suave_fps_agree_pendiente / sin_observaciones_validas)
Ran 1 test in 1.083s
FAILED (failures=1)
```

Después: decisiones `FALLA` / `FALLA` / `INCONCLUSO`, código de salida 1, con causa
`suave_fps_agree_exceeded` en 30 y 60. El test de B2 de la vuelta 5b
(`test_acuerdo_fps_pendiente_si_falta_la_referencia_no_certifica_30`) sigue verde en la misma corrida:
sin desacuerdo demostrado, el acuerdo pendiente sigue dejando el régimen en `INCONCLUSO`.

### Puerta de la vuelta 5c (salida literal)

Entorno: en este sandbox `C:\Python314\python.exe` no ve numpy ni Pillow y el intento de instalarlos en
una carpeta temporal falló por el proxy (`ProxyError('Cannot connect to proxy.', TimeoutError('timed out'))`
contra PyPI), igual que en la vuelta 5b. Por eso la suite completa con el intérprete prescrito queda
`GATE NOT RUN` en su forma íntegra; el orquestador corre la suite completa.

Suite completa, comando prescrito desde `DayZSandbox_dev`
(`C:\Python314\python.exe -m unittest discover -s qa/strack/tests -t .`):

```text
GATE NOT RUN: numpy y Pillow no visibles en C:\Python314 dentro de este sandbox y PyPI inaccesible por el proxy; los 4 módulos que importan numpy fallan al importar y el resto corre (ver siguiente bloque).
ModuleNotFoundError: No module named 'numpy'
Ran 27 tests in 0.894s
FAILED (errors=4)
```

Tests de timeline (vueltas 5/5b/5c) con el numpy 2.3.4 del Python de Blender 5.1 del host y un stub
mínimo de Pillow en una carpeta temporal borrada después (las rutas `suave` no usan Pillow; solo se
necesitaba que el import de módulo no fallara). Esto no es el intérprete de la puerta y se declara como
verificación sustituta, no como puerta:

```text
test_acuerdo_fps_pendiente_si_falta_la_referencia_no_certifica_30 ... ok
test_desacuerdo_demostrado_no_se_borra_por_tercer_regimen_incompleto ... ok
test_dt_compensado_en_salto_se_juzga_contra_el_dt_registrado ... ok
test_intervalo_carga_fuera_de_fps ... ok
test_tiron_real_en_giro_correcto_sin_falso_acuerdo_fps ... ok
Ran 5 tests in 2.123s
OK
```

`test_check_runs` con el intérprete prescrito (stdlib, sin numpy):

```text
Ran 24 tests in 0.696s
OK
```

Stdlib only (`C:\Python314\python.exe -m unittest qa.tests.test_stdlib_only`):

```text
Ran 1 test in 0.157s
OK
```

## WHAT I COULD NOT VERIFY

- (Vuelta 5c) La suite completa con el intérprete prescrito (`C:\Python314\python.exe`) no se pudo
  correr íntegra en este sandbox: ese intérprete no ve numpy ni Pillow aquí y PyPI no responde por el
  proxy, así que queda `GATE NOT RUN` en esa forma (salida literal en la sección «Vuelta 5c»). Los
  tests de timeline 5/5b/5c sí corrieron con el numpy 2.3.4 del Python de Blender 5.1 del host y un
  stub mínimo de Pillow ya borrado, y los de `check_runs` y `test_stdlib_only` con el intérprete
  prescrito; el orquestador corre la suite completa. El test nuevo de N1 sí se observó fallando antes
  del arreglo y pasando después con ese intérprete sustituto.
- (Vuelta 5b) La suite completa con el intérprete prescrito (`C:\Python314\python.exe`) no se pudo
  correr íntegra en este sandbox: ese intérprete no ve numpy ni Pillow aquí y PyPI no responde por el
  proxy, así que queda `GATE NOT RUN` en esa forma (salida literal en la sección «Vuelta 5b»). Los
  tests de timeline 5/5b sí corrieron con el numpy 2.3.4 del Python de Blender 5.1 del host y un stub
  mínimo de Pillow ya borrado, y los de `check_runs` y `test_stdlib_only` con el intérprete prescrito;
  en un intérprete con los paquetes de `requirements.txt` instalados la suite completa no se repitió.
  Los tests nuevos de timeline se escribieron antes del arreglo, pero su primera ejecución posible fue
  después, con ese intérprete sustituto; el de M2 sí se observó fallando antes y pasando después con
  el intérprete prescrito.
- El comportamiento del mod con tirones en corridas `suave*` **no se ha observado todavía** (el banco sigue
  corriendo; solo hay calibraciones reales). Mi arreglo depende de ello en un punto acotado: la guarda de
  frontera de salto declara INCONCLUSO (no FALLA) cuando `dt` y Δt_ms discrepan en el frame del salto,
  precisamente porque un tirón genuino del mod en `suave*` podría producir esa misma firma y hoy no hay
  datos para separarla de una adulteración. El resto de H1 no depende de esa observación: que el filtro
  integra el `dt` registrado está leído en el código del mod (`STRACK_Session.c:1347` y `:1577`), no inferido
  del banco.
- No se ha corrido el banco real ni ninguna corrida `suave*` real con el evaluador nuevo: toda la evidencia
  de T-suave es de fixtures sintéticas generadas por `fixtures/make_fixtures.py`. Tampoco se ha comprobado
  `check_runs.py` contra una carpeta de corridas reales completa (solo contra `calib_Ha`/`calib_Hb`
  reconstruidas desde la fixture de relojes, que es lo que pide la puerta).
- La suite completa se corrió con numpy/Pillow instalados en una carpeta temporal del workspace vía
  `PYTHONPATH`, porque `C:\Python314\python.exe` no los trae; el comando de la puerta es el indicado
  arriba y el código probado es el del workspace, pero en un intérprete con los paquetes de
  `requirements.txt` ya instalados la corrida no se repitió.
