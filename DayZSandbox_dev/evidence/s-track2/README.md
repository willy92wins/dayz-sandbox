# Evidencia de S-track·2

Estado a 2026-11-14: **las tres piezas están cerradas, y el evaluador además pasó una quinta vuelta tras la primera
corrida real.** La tanda del banco no ha terminado: hay 2 corridas válidas, `calib_Ha` y `calib_Hb`. Todavía no hay
veredicto de S-track·2.

## Las piezas (brief `plans/2026-11-12-s-track-2-brief.md`)

Cada pieza la implementó Muse y la revisó Sol (`gpt-6.1-sol`, solo lectura), con un tope de 4 vueltas. Lo que quedó
abierto tras la cuarta lo arbitró el orquestador. El detalle, vuelta a vuelta, está en `_vueltas/vueltas.md`. Los
informes de cada pieza y los dictámenes de Sol están tal cual en `_vueltas/`.

| Pieza | Ficheros | Vueltas (BLOQ+MAY de Sol) | Cierre |
|---|---|---|---|
| Mod | `qa/strack/DZS_STrack/` | 7, 2, 2, 3 | Arbitraje: los 3 MAY de la vuelta 4 solo pasan si el servidor sigue vivo entre corridas, así que el banco arranca un servidor nuevo antes de cada `ropa` y `suave*`. Linter PASS 0/0. PBO de 72 584 B, sha256 `38f3b7ffce364c84a9a4eb5cf52701c350b667bdb2b80e8b3459e3dc3de94055` |
| Mutantes | `qa/strack/mutants/`, `qa/strack/check_negatives.py` | 4, 4, 2, 1 | Arbitraje: cambio mecánico en el runner (solo cuenta como muerte un fallo del cuerpo del test). Tests del runner 64/64 |
| Evaluador, vueltas 1-4 | `qa/strack/s_track_eval.py`, `qa/strack/tests/`, `qa/strack/fixtures/` | 15 (+1 MEN), 15, 8, 6 | Arbitraje: los 4 BLOQ de la vuelta 4 solo se dan con entradas que el banco real no debería producir, y pasan a `qa/strack/check_runs.py`. Suite 64/64 (receptor, 1342 s) |
| Evaluador y `check_runs`, vuelta 5 (relojes) | los mismos, más `tests/test_s_track_timeline_r5.py` y `fixtures/real_clock_calib.json` | 4, 4, 1, **0** | Sin arbitraje pendiente. Sol cerró con **OK** en su cuarta vuelta. Suite 93/93 (receptor, 1483 s) |

## La vuelta 5: relojes reales (14-nov)

La primera corrida real, `calib_Ha`, mostró que en el banco `dt` (el timeslice de `OnUpdate`) y `t_ms`
(`GetTickTime`) no coinciden frame a frame:
- `dt` viene redondeado a 1 ms;
- en un tirón, los dos relojes reparten el tiempo de forma distinta entre dos frames: 36+5 ms frente a 8+32 ms;
- en 17 s solo se separan 1 ms.

En `calib_Ha` hay 38 de 1020 pares con un desacuerdo mayor de 1 ms; en `calib_Hb`, 224. Las columnas de reloj de las
dos corridas están en `qa/strack/fixtures/real_clock_calib.json`.

Sol (`_vueltas/sol-checkruns-v1..4.md`) demostró que el evaluador mezclaba los dos relojes: simulaba el filtro con `dt`
y medía la orientación a 1/6 s con `t_ms`. Con el tirón real, eso daba un desacuerdo entre FPS falso.

El arreglo (Muse; `_vueltas/REPORT_eval_r5.md` y `brief_eval_r5*.md`):
- Lo que integra el filtro (el origen del salto, la orientación a 1/6 s y la referencia de T-suave) se mide sobre
  `Σdt`, que es el reloj que usa el mod (`STRACK_Session.c:1347` y `:1577`; CONTRACT §16).
- `t_ms` queda solo para medidas de pared: la duración del giro y las ventanas sin etiqueta.
- El intervalo de carga 0→1 se trata igual en el evaluador y en `check_runs`.
- Si falta una comparación entre regímenes, el acuerdo entre FPS queda pendiente y no se da por cumplido. Un
  desacuerdo ya demostrado se mantiene en FALLA.

Arbitraje (vuelta 2, aceptado por Sol en la 3): un `dt` registrado distinto del que integra el filtro no puede salir
del banco real, así que no se protege contra `dt` adulterados.

## `check_runs.py` (arbitraje del evaluador)

Antes de aceptar un veredicto del evaluador, cada corrida tiene que pasar estas comprobaciones:
- `done.json` con `ok: true`, y `preflight.json` fuera de `calib`.
- Los giros que pide el caso, cada uno de 4,0 ± 0,3 s (más un frame).
- En `suave*`, `cam_raw` completo y `lata.a` en todos los frames.
- El reloj de cada fila:
  - `t_ms` y `dt` finitos, y `dt > 0`; también se rechazan `NaN` e `Infinity` en el JSON;
  - si hay filas duplicadas de un mismo frame, deben coincidir en `t_ms` y `dt`;
  - sobre las filas que consume el evaluador, `t_ms` estrictamente creciente;
  - la deriva acumulada frente a `1000·Σdt` no pasa de 50 ms. El límite sale de los consumidores de pared, no de los
    datos.
- Para cada negativa, su `calib_<hook>` válida. Las de Hc usan `calib_Ha`: el mod no admite `calib` con Hc y el
  evaluador usa la de Ha.

Una corrida que no lo pasa es INVÁLIDA: se repite o queda INCONCLUSA. Tests: `qa/strack/tests/test_check_runs.py` (24).
Las dos calibraciones reales son VÁLIDAS.

## Pendiente

- **La tanda del banco**: 24 corridas. Son las `calib` Ha y Hb, ya válidas; los positivos; `ropa_Hb`;
  `suave30/60/144_Hb`; y las negativas del brief §3. Se lanzan con `C:\tmp\dsbx-strack2\bench\run_all2.ps1`, que
  necesita el PC 15 min sin teclado ni ratón antes de cada corrida y espera mientras haya otro DayZ abierto o un lease
  de GPU ajeno. Al acabar saca `SHA256SUMS` de cada corrida y pasa `check_runs.py`.
- **Las marcas a mano** del orquestador (contrato §12) y, con ellas, el evaluador.
- **Los mutantes contra el evaluador de la vuelta 5** (`run_mutants.py`). Corre la suite entera por cada mutante, unos 25
  min cada uno. La corrida del 13-nov sobre el evaluador anterior se paró sin resultado.
- Backlog de la vuelta 4 del evaluador (solo da INCONCLUSO de más): la búsqueda de textura sigue a la lectura «a», y
  una detección débil corta la búsqueda de centros alternativos.
- PREMISA de Sol, que solo se contrasta en el banco con fondos distintos: que la baja varianza temporal identifique
  los píxeles del arma, y que el detalle marcado a mano coincida con el punto de memoria.

La evidencia binaria (PNG, `samples.jsonl` y logs) no irá a git: se queda en el PC, como en S-track·1.
