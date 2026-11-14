VEREDICTO: OK  
BLOQ=0 MAY=0 MEN=0

## Cierre

**N1: CERRADO.** [s_track_eval.py:2802](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2802) preserva los desacuerdos demostrados; [2814](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2814) aplica FALLA.

Reproduje el escenario propio con tramos de 10 s, giros de 4 s y relojes coherentes: +1° en los frames 915–929 de `suave30_Hb`; `cam.pos=null` en el frame 4392 de `suave144_Hb`. Las tres corridas pasan `check_run`.

| Régimen | Resultado | Causa |
|---|---|---|
| 30 | FALLA | `suave_fps_agree_exceeded` |
| 60 | FALLA | `suave_fps_agree_exceeded` |
| 144 | INCONCLUSO | `sin_observaciones_validas` |

Orientaciones a 1/6 s: **73,4619° frente a 72,4619°**. Código **1**, también comprobado mediante `main()`.

**B2 no se reabre.** Sin desacuerdo demostrado, sigue aplicándose [s_track_eval.py:2804](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2804). Sin sesgo y dejando incompleta sucesivamente la referencia de 30, 60 o 144, obtuve **INCONCLUSO / INCONCLUSO / INCONCLUSO**, código **2**. Ningún régimen quedó certificado PASA.

## Hallazgos nuevos

Ningún defecto nuevo demostrado atribuible a la 5c. Pasaron los ocho escenarios propios y la comprobación del CLI.

## LO QUE NO PUDE VERIFICAR

No ejecuté el banco in-game ni repetí los 93 tests, `stdlib_only` o las calibraciones comunicadas por el receptor.

Las sondas ejecutaron descubrimiento, parser, `check_run` y evaluador reales con filesystem en memoria, Python de Blender, NumPy 2.3.4 y un stub de Pillow solo para importar. No ejercité imágenes ni modifiqué archivos.

