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
