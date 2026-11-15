# Registro de fallos

Lo que aparece fuera del alcance de una tanda, o lo que un arbitraje aplaza, se apunta aquí y no se arregla en silencio (R20).

## 2026-10-27 · SOL-24 (MEN) · `stop()` puede lanzar con un timeout negativo, y S10 no limpia si lanza

- **Origen:** cuarta revisión R21 de Sol sobre `ef7a38a2` (F0.1). Sol la puso en MAY; el arbitraje la deja en MEN y aplaza el arreglo (`AI/10_Projects/DayzSandbox/f0/2026-10-27-f0.1-fix3-arbitraje-sol.md` en el vault).
- **Dónde:** `qa/bridge_qa.py:164-166` y `qa/s_puente_run.py:196-203`.
- **Qué falla:**
  - El bucle de `stop()` lee el reloj en la condición y otra vez al calcular `left`. Si el plazo cae entre las dos lecturas, `left` sale negativo y `self.cv.acquire(timeout=min(0.05, left))` lanza `ValueError`.
  - En S10, `bridge.stop()` no tiene `finally` propio, así que esa excepción se salta `_stop_peers`, el cierre de ficheros y el borrado de perfiles.
- **Medido el 2026-10-27, forzando el reloj:**
  - la corrida sale 2 con `error.type = ValueError` (regla 2), pero sin `manifest.json`;
  - los dos `fake_peer.py` siguen vivos a los 120 s;
  - la carpeta de perfiles, que lleva las claves, queda en disco.
  Sin forzarlo no apareció en 5000 llamadas reales, con y sin carga de CPU.
- **Arreglo mínimo:**
  - acotar ese timeout a 0 como mínimo, o salir del bucle si `left <= 0`;
  - que la limpieza de S10 corra aunque `bridge.stop()` lance.
  Cada parte lleva su prueba de regresión, que falle sobre `ef7a38a2` por la conducta.
- **Cuándo:** en la próxima tanda que toque `bridge_qa.py` o `s_puente_run.py`, con su revisión R21.

## 2026-11-14 · R1-N3 (BLOQ en F0.3-0) · Reutilización de resultados cacheados entre corridas/partes sobre una sonda viva

- **Origen:** primera revisión de ChatGPT Sol sobre el brief de F0.3-0 (`R1-N3`) y revisión de código de F0.2 (`#6`, `F02-H1` en §14 del brief v4.5 de F0.3-0).
- **Dónde:** `qa/bridge_qa.py:193-195`, `qa/s_puente_run.py:382`, `qa/s_puente_eval.py:236-246` y `qa/probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_Probe.c:891-895` en `e3f530e` / `9998c05`.
- **Qué fallaba en F0.2:**
  - `QABridge.enqueue` numeraba las órdenes implícitas desde `op-1` en cada instancia del bridge, y `s_puente_run.py` fijaba `n5-<role>-c` y `seq0 = 1000` constantes.
  - La sonda mantiene `m_Cache` (1024 entradas) y `m_RpcLog` (512 entradas) durante toda la vida de la misión sin vaciarlos al rotar la clave o la URL (P5(c)).
  - En una segunda corrida contra la misma instancia viva de la sonda, los `op_id` colisionaban con entradas cacheadas (`dup = true`) y `_mix_ok` no comprobaba `dup == false`.
- **Estado:** anotado por mandato de R1-N3 (§9 de F0.3-0) y cerrado en F0.3-0 mediante ids opacos con nonce aleatorio por parte en `f03_common.py` (§5.3) y `run_id` por corrida, exigencia de `dup == false` en `_mix_ok` y frontera `boundary_ms`/`seq0` en `S-puente` (§14 `F02-H1`).

## 2026-11-15 · S-puente · `test_point7_fault_matrix` falla según la carga de la máquina

- **Origen:** las suites completas que se lanzaron en paralelo, en varios worktrees, al orquestar los oráculos de los spikes de F0.3 (sesión de los spikes; la del núcleo está archivada).
- **Dónde:** `qa/tests/test_e2e_s_puente.py:220` (`test_point7_fault_matrix`), que corre `qa/s_puente_run.py`.
- **Qué falló el 15-nov, cuatro veces:**
  - **09:58, base `0c730f0`:** `fault='ignores_ttl'` da ERROR por `PermissionError [WinError 5]` en `Path.replace` de `dsbx_qa.json.tmp` a `dsbx_qa.json`, dentro de `_write_cfg` (`qa/s_puente_run.py:561`); y `fault='none'` da 1 en vez de 0. Había 3 suites a la vez.
  - **12:4x, base `0c730f0`:** `fault='wrong_build'` da 1 en vez de 2.
  - **13:1x, `main` en `7754ac0`:** `fault='wrong_build'` da 1 en vez de 2.
  - **13:2x, `fc24197` (sin F2), con el test aislado pero a la vez que otro en `7754ac0`:** `none` da 1 en vez de 0, y `wrong_build`, 1 en vez de 2. En `7754ac0` pasó en esa misma ejecución. No lo causa F2.
- **Estado:** MITIGADO (la tasa de fallo con carga pasa de ~100 % a ~10 %; ver el residual al final) el 2026-11-15 en la rama `claude/s-puente-point7-estable`.
- **Causa medida:** inanición de CPU. Bridge (hilos del proceso de la prueba) y peers falsos corrían a prioridad normal, compitiendo con cualquier otro proceso; con la máquina cargada, las latencias que mide la propia matriz se pasan de su umbral.
  - Reproducido sin tocar nada del resto: 24-32 procesos de Python girando en bucle (16 núcleos) mientras corre `s_puente_run.run`. Sin el arreglo, `none` dio 1 en 3 de 3 corridas (M2 `p95 >= 1000`; N5.client `d not done`; N4.server y N6 `missing`) y `wrong_build` dio 1 en vez de 2 en 2 de 3 (M2 `fail` además de C0 `missing`; la tercera dio 2). Cada corrida tardaba 90-210 s en vez de 27 s. Con el arreglo y la misma carga: `none` 0, `wrong_build` 2, 29-34 s.
  - Los umbrales fallidos son contrato (M2: p95 < 1000 ms), no plazos de espera de la matriz; por eso no se tocan.
- **Hipótesis descartadas o no necesarias:**
  - `_free_udp_port`: no se observó ningún fallo de bind en los peers (los fallos eran de latencia: M2, N5, N4, N6); no se ha tocado. Sigue siendo una ventana teórica entre soltar el puerto y que el peer cliente lo ocupe.
  - `Path.replace`: el `PermissionError [WinError 5]` del 09:58 no se reprodujo con esta carga, pero la carrera es real en Windows (el peer o un antivirus tienen `dsbx_qa.json` abierto un instante), así que se añade un reintento corto y acotado.
- **Arreglo:** `qa/s_puente_run.py`: peers lanzados con `HIGH_PRIORITY_CLASS`, proceso de la corrida subido a prioridad alta y restaurado al acabar (solo `build == offline` y solo Windows), y `_write_cfg` reintenta hasta 40 veces con 50 ms si `Path.replace` da `PermissionError`.
- **Límites de la subida** (sesión principal, 2026-11-15):
  - **Alcance:** solo los procesos de la corrida (el runner y sus peers) y como mucho HIGH, nunca REALTIME.
  - **Con una partida en curso, no se sube:** si `gpu_lease.py comprobar` da OCUPADA, una corrida offline podría deformar una medición en partida, como la de S-perf. Si no se puede saber el estado del lease (falta el script, error o timeout), tampoco se sube.
  - **Registro:** la decisión queda en `<evidencia>/priority_boost.json`, con `applied`, `skipped_gpu_lease_busy`, `skipped_gpu_lease_unknown`, `not_offline` o `not_windows`.
  - **Script del lease:** `DSBX_GPU_LEASE_SCRIPT` lo cambia; por defecto, `~/.claude/tools/gpu_lease.py`.
  - **Pruebas:** `test_gpu_lease_check_reads_the_lease_script`, `test_priority_decision_respects_the_gpu_lease` y `test_run_does_not_boost_while_a_game_holds_the_gpu_lease`. `test_point7_rows_hold_under_cpu_load` y `test_point7_priority_boost_is_restored` se saltan si ahora no toca subir.
- **Pruebas** (`qa/tests/test_e2e_s_puente.py`): `test_point7_rows_hold_under_cpu_load` (carga de 2 x núcleos procesos; falla sin el arreglo, pasa con él), `test_point7_priority_boost_is_restored`, `test_write_cfg_retries_a_busy_file`, `test_write_cfg_retry_is_bounded`.
- **Residual medido (no cerrado del todo):** con el arreglo y carga extrema (2 x núcleos de procesos girando, a veces con otras suites a la vez) quedan fallos esporádicos: 1 de 3 corridas de `test_point7_rows_hold_under_cpu_load` con 1 x núcleos, 1 de unas 9 con 2 x núcleos (`wrong_build` da 1 por N6 `fail`) y 1 `none` = 1 con tres suites a la vez. N6 compara `lease_age_ms` contra un lease de 600 ms con aceptados hasta ~566 ms, es decir ~34 ms de margen entre aceptar y aplicar la pose; un tirón de ese tamaño en un peer a prioridad alta es lo que queda. Sin el arreglo, `none` falló en 4 de 4 corridas con carga. Si molesta, el siguiente paso sería que el peer decida la ventana por reloj lógico del bridge en vez de reloj de pared.
