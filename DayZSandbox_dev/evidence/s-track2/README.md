# Evidencia de S-track·2

Estado a 2026-11-13: **las tres piezas están cerradas y la tanda del banco aún no se ha corrido.** No hay veredicto de
S-track·2 todavía.

## Las piezas (brief `plans/2026-11-12-s-track-2-brief.md`)

Cada pieza la implementó Muse y la revisó Sol (`gpt-6.1-sol`, solo lectura), con un tope de 4 vueltas; lo que quedó
abierto tras la cuarta lo arbitró el orquestador. El detalle, vuelta a vuelta, está en `_vueltas/vueltas.md`; los
informes de cada pieza y los dictámenes de Sol, tal cual, en `_vueltas/`.

| Pieza | Ficheros | Vueltas (BLOQ+MAY de Sol) | Cierre |
|---|---|---|---|
| Mod | `qa/strack/DZS_STrack/` | 7, 2, 2, 3 | Árbitro: los 3 MAY de la vuelta 4 solo pasan con el servidor vivo entre corridas; el banco arranca un servidor nuevo antes de cada `ropa` y `suave*`. Linter PASS 0/0; PBO 72 584 B, sha256 `38f3b7ffce364c84a9a4eb5cf52701c350b667bdb2b80e8b3459e3dc3de94055` |
| Mutantes | `qa/strack/mutants/`, `qa/strack/check_negatives.py` | 4, 4, 2, 1 | Árbitro: cambio mecánico en el runner (solo cuenta como muerte un fallo del cuerpo del test). Tests del runner 64/64 |
| Evaluador | `qa/strack/s_track_eval.py`, `qa/strack/tests/`, `qa/strack/fixtures/` | 15 (+1 MEN), 15, 8, 6 | Árbitro: los 4 BLOQ de la vuelta 4 solo se dan con entradas que el banco real no debería producir; pasan a `qa/strack/check_runs.py`, que se corre sobre las corridas reales antes de aceptar ningún veredicto. Suite 64/64 (receptor, 1342 s) |

## `check_runs.py` (arbitraje del evaluador)

Antes de aceptar un veredicto del evaluador, cada corrida tiene que pasar:
`done.json` con `ok: true` y `preflight.json`; los giros que pide el caso, cada uno de 4,0 ± 0,3 s (más un frame);
en `suave*`, `cam_raw` completo y `lata.a` en todos los frames; `t_ms[n] − t_ms[n−1]` = `1000·dt[n]` ± 1 ms; y,
para cada negativa, su `calib_<hook>` válida. Una corrida que no lo pasa es INVÁLIDA: se repite o queda INCONCLUSA.
Tests: `qa/strack/tests/test_check_runs.py` (8, uno por cada caso).

## Pendiente

- **La tanda del banco**: 25 corridas (`calib` ×3, positivos, `ropa_Hb`, `suave30/60/144_Hb` y las negativas del brief
  §3), con el lanzador del PC (`C:\tmp\dsbx-strack2\bench\run_all2.ps1`), que necesita el PC 15 min sin teclado ni
  ratón antes de cada corrida. Al acabar saca `SHA256SUMS` de cada corrida y pasa `check_runs.py`.
- **Las marcas a mano** del orquestador (contrato §12) y, con ellas, el evaluador.
- **Los mutantes contra el evaluador integrado** (`run_mutants.py`): corre la suite entera por cada mutante (~22 min cada uno),
  así que va después del banco.
- Backlog de la vuelta 4 del evaluador (solo dan INCONCLUSO de más): la búsqueda de textura sigue a la lectura «a», y
  una detección débil corta la búsqueda de centros alternativos.
- PREMISA de Sol, que solo se contrasta en el banco con fondos distintos: que la baja varianza temporal identifique
  los píxeles del arma, y que el detalle marcado a mano coincida con el punto de memoria.

La evidencia binaria (PNG, `samples.jsonl`, logs) no irá en git: se queda en el PC, como en S-track·1.
