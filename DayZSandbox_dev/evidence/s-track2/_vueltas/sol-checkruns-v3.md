VEREDICTO: NEEDS-WORK  
BLOQ=0 MAY=1 MEN=0

## Cierre

| Punto | Estado | Evidencia |
|---|---|---|
| B2 | **CERRADO** | La comparación ausente deja el acuerdo pendiente en [s_track_eval.py:2793](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2793). Reproduje el escenario original con sesgo de 1° y tirón real: ahora ambos regímenes dan FALLA. |
| M1 | **CERRADO** | Sin la guarda, `s0` llega a la comprobación de error de [s_track_eval.py:2432](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2432): con el tirón real, cámara correcta → PASA; error de 0,5 m → FALLA / `suave_frac_exceeded`. |
| M2 | **CERRADO** | [check_runs.py:198](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:198) comprueba coherencia acumulada sin techo por intervalo. La corrida con 101 ms coherentes resulta VÁLIDA y sus cinco grupos pasan. |
| H1 | **CERRADO** | El origen y la medida usan Σdt en [s_track_eval.py:2263](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2263) y [2281](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2281). Con el tirón real, ambas cámaras correctas conservan **72,4619°** a 1/6 s y PASA. |
| Umbral | **CERRADO** | La justificación de [check_runs.py:37](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:37) queda limitada a consumidores de pared. Verifiqué el borde de [216](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:216): 50 ms → VÁLIDA; 50,5 ms → INVÁLIDA. |

## Arbitraje de B1

**Acepto el arbitraje y retiro B1 como bloqueo.** Mi contraejemplo anterior no demostraba un defecto de cámara conforme a CONTRACT §16.

El productor vacía la fila Hb anterior antes de sustituir `m_Dt` en [STRACK_Session.c:308](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:308), evita capturas Hb repetidas en [341](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:341), integra ese campo en [1577](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1577) y lo serializa en [1835](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1835).

Existe una salida sin filtrar cuando falta la lata, pero produce `lata.a=null`, rechazada por [check_runs.py:241](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:241). No aporta un contraejemplo que engañe al evaluador.

## Hallazgos nuevos

**N1 — MAY: una referencia incompleta oculta un desacuerdo ya demostrado.**

Dónde: [s_track_eval.py:2795](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2795) convierte los giros PASA en INCONCLUSO; después, [2806](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2806) solo convierte en FALLA los que todavía sean PASA.

Entrada exacta reproducida:

- Corridas a 30, 60 y 144 FPS, relojes coherentes, tramos de 10 s y giros de 4 s.
- Cámara correcta salvo un sesgo de guiñada de **+1°** en los frames **915–929** de `suave30_Hb`, primeros 0,5 s de `giro+170`.
- `cam.pos=null` únicamente en el frame **4392** de `suave144_Hb`, primer frame de ese giro.
- Las tres corridas pasan `check_run` sin motivos.

A 1/6 s se observan **73,4619° frente a 72,4619°**: desacuerdo de 1°, superior al límite de 0,5°.

| Entrada al evaluador | Decisión 30 / 60 / 144 | Código |
|---|---|---|
| Solo 30 y 60 | FALLA / FALLA / INCONCLUSO | 1 |
| Añadiendo 144 incompleta | INCONCLUSO / INCONCLUSO / INCONCLUSO | 2 |

La falta de una tercera comparación borra dos fallos que ya estaban demostrados. Debe conservarse FALLA para 30 y 60, dejando 144 INCONCLUSO. Arreglo sugerido: dar prioridad al desacuerdo demostrado antes de aplicar el estado pendiente.

**En negativo:** no he demostrado ninguna corrupción temporal producida por el banco real que siga engañando al evaluador. El patrón observado `dt=8+32 ms`, `Δt_ms=36+5 ms` permite pasar al filtro correcto y sigue detectando el sesgo de 1°. N1 ocurre con relojes coherentes.

## LO QUE NO PUDE VERIFICAR

No ejecuté el banco in-game ni corridas `suave*` reales. Tampoco repetí la suite de 92 tests: ese resultado procede del receptor.

Ejecuté el evaluador y `check_run` reales mediante sondas en memoria, con NumPy de Blender y un sustituto de PIL únicamente para permitir el import; no ejercité imágenes. Ambas calibraciones de la fixture resultaron VÁLIDAS. No modifiqué archivos.

