# Evidencia de S-track·2

Estado a 2026-11-27: **tanda real de 24 corridas hecha (25/26-nov) e informe escrito: [`_informe/informe.md`](_informe/informe.md).**
Estado global INCONCLUSO:
- `mount` con el arma en manos queda aceptado por decisión de Guillermo, con un temblor medido de ≈5 px en H-b.
- look_at y follow quedan FALLA en H-a y sin confirmar en H-b.
- Hay una tanda corta r6b en curso (contrato §36).

Lo que sigue es la historia de las piezas; el detalle de cada vuelta está en `_vueltas/vueltas.md`.

## Evidencia en E: (no va a git)

Las corridas de la tanda del 25/26-nov se movieron a E: durante la noche, porque se llenó el disco C:. Cada fichero se
copió con SHA-256 verificado:
- `E:\dsbx-strack2\evidence\runs\<corrida>\`: PNG, `samples.jsonl`, `done.json` y `SHA256SUMS` por corrida.
- `E:\dsbx-strack2\evidence\runs24\`: uniones a las 24 corridas que evalúa el informe (sin `.prev` ni `.diag`).
- [`SHA256SUMS.index`](SHA256SUMS.index): una copia, en esta carpeta, del índice de los `SHA256SUMS` de cada corrida
  (el original está en `E:\dsbx-strack2\evidence\runs\SHA256SUMS.index`, sha256
  `d7fcecfc87f4e7f4755bf6a734f9b6f56407151ca71a1bf854b144ef69172b52`).
- La tanda corta r6b escribe en `E:\dsbx-strack2\runs_r6\` y su log en `C:\tmp\dsbx-strack2\bench\runlog_r6\`.

Medidas del informe:
- `_informe/informe.json` y `_informe/evaluador.md`: salida del evaluador.
- `_informe/thook_mount/`: T-hook de mount, medida directa (§34).
- `_informe/tlect_directa/`: T-lect de look_at/follow, medida directa (§35).

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

## Pendiente (27-nov)

- **Tanda corta r6b** (`C:\tmp\dsbx-strack2\bench\night_corta.ps1`, 12 corridas):
  - suave sin capturas a 30, 60 y 144 fps, y quatlerp a 30 y 144;
  - mount03_Hb con la posición rígida;
  - barrido de `smooth_s` en mount0_Hb, para elegir el valor por defecto en manos;
  - lookat_Hb y follow_Hb con giros lentos y alternos.
- **Mutantes contra el evaluador integrado:** relanzados el 27-nov; la corrida del 26-nov se cortó al cerrarse la sesión.
- **Revisión de Neon**, una vuelta, de los arbitrajes que no se pueden probar (regla del 26-nov: «si se puede probar no se revisa»).
- **PREMISA de Sol, contrastada en el banco: no se cumple en look_at/follow.** El arma gira en la imagen y la máscara por
  varianza temporal sale vacía. Se sustituyó por medidas directas (contrato §34/§35).

La evidencia binaria (PNG, `samples.jsonl` y logs) no irá a git: se queda en el PC, como en S-track·1.
