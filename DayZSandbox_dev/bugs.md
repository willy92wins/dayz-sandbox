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
- **Estado:** el 2026-11-15 (rama `claude/s-puente-point7-estable`, PR #18) se **retiró la subida de prioridad** y se arregló N6 de raíz en el evaluador. Quedan como mitigaciones el reintento acotado de `_write_cfg` y la creación protegida de burners. M2 (`p95` con carga extrema) queda como residual del entorno.
- **Causa medida:** inanición de CPU. Bridge (hilos del proceso de la prueba) y peers falsos corrían a prioridad normal, compitiendo con cualquier otro proceso; con la máquina cargada, las latencias que mide la propia matriz se pasan de su umbral.
  - Reproducido sin tocar nada del resto: 24-32 procesos de Python girando en bucle (16 núcleos) mientras corre `s_puente_run.run`. Sin mitigación, `none` dio 1 en 3 de 3 corridas (M2 `p95 >= 1000`; N5.client `d not done`; N4.server y N6 `missing`) y `wrong_build` dio 1 en vez de 2 en 2 de 3 (M2 `fail` además de C0 `missing`; la tercera dio 2). Cada corrida tardaba 90-210 s en vez de 27 s. Con las mitigaciones y la misma carga: `none` 0, `wrong_build` 2, 29-34 s.
  - Los umbrales fallidos son contrato (M2: p95 < 1000 ms), no plazos de espera de la matriz; por eso no se tocan.
- **Subida de prioridad retirada (5 BLOQ de Sol r2, `_encargo/sol_r2.md`):**
  1. **Protección después de elevar:** la subida ocurría antes del `try` y la primera escritura; inyectando `PermissionError` en esa escritura, el runner quedaba en HIGH sin restauración.
  2. **Lectura fallida que ocultaba una subida efectiva:** `SetPriorityClass` podía tener éxito y `GetPriorityClass` devolver 0; `applied` quedaba falso y la restauración no restauraba.
  3. **Vigía fuera de plazo y bajadas abandonadas:** esperaba 2 s pero la consulta admitía 15; la revocación se marcaba antes de confirmar las bajadas y terminaba aunque fallaran.
  4. **Peer que nacía en HIGH tras la revocación:** los flags se calculaban fuera de la sección que registraba el proceso; la compensación lo bajaba después, incumpliendo la prohibición de lanzarlo elevado.
  5. **Integración real contaminante:** la prueba elevaba sin consultar el lease ni `finally`; con lease ocupado subía igualmente y, si fallaba la aserción, dejaba la suite en HIGH.
  Se quitaron `_HIGH_PRIORITY_CLASS`, `_gpu_lease_busy`, `_priority_decision`, `_PriorityBoost` (apply/lower/restore), `_lower_process_priority`, `_read_priority`/`_set_priority`/`_process_handle`/`_observed_priority`/`_priority_api`, el vigía del lease, `priority_boost.json`, los `creationflags` de prioridad de los peers y las restauraciones, junto con sus ocho pruebas. No queda ningún gancho ni flag de prioridad.
- **Causa real de N6:** desajuste entre F02-H3 y el oráculo. F02-H3 obliga al peer a comprobar el lease antes de cada efecto (`plans/2026-11-14-m1-f0.3-0-brief.md:669-673`) y el peer descarta la pose diferida si el lease caducó en el frame en que la aplica (`qa/fake_peer.py:1106-1110`). El evaluador exigía siempre la «última pose aceptada» (`qa/s_puente_eval.py:482`), así que una aceptación a 566 ms y una aplicación a 601 ms (lease 600) daban `pose is not last accepted` sin carga real. No era un fallo del peer: era el oráculo exigiendo una pose que F02-H3 manda descartar.
- **Arreglo de N6** (`_n6_discard_credited` en `qa/s_puente_eval.py`): el evaluador acredita el descarte con la evidencia del propio peer, sin etiquetas del runner.
  - De cada aceptada del `rpc_log` toma el lease restante al recibirla, `lease_ms - lease_age_ms`, en el reloj del peer.
  - Solo una aceptada con lease restante `<= N6_DEFER_MAX_MS` (250 ms) pudo encontrarse el lease caducado en el frame siguiente. Las demás son **obligadas**: tuvieron que aplicarse.
  - **Si hay obligadas,** la pose leída tiene que ser la de la última obligada o la de una aceptada posterior. Una pose anterior, o ninguna de la ráfaga, es FALLA `pose is not last accepted`, aunque el lease haya caducado antes de leer.
  - **Si ninguna es obligada,** basta con que el lease haya caducado antes de leer la pose (`recv_ms - lease_age_ms + lease_ms <= done_ms` de la última aceptada).
  - **Por qué no basta con «caducó antes de leer»** (era el primer arreglo de la ronda, y lo corrigió el orquestador): en la ráfaga de N6 el lease no se renueva, así que todas las aceptadas comparten la misma caducidad, y la lectura de la pose siempre llega después. Con ese criterio, un peer que no aplicara ninguna pose pasaba N6.
  - No se relaja ningún otro predicado de N6: ventana de aceptados y rechazados, orden y métricas.
- **Pruebas de N6 con reloj controlado** (`clock_ms_fn`, `qa/fake_peer.py:431`), en `qa/tests/test_e2e_s_puente.py`:
  - aceptación a 566 ms y aplicación a 599 → `pass`;
  - aplicación a 601, descartada por lease caducado → `pass` (no se exige como última aceptada);
  - negativa con la pose descartada mientras el lease seguía vigente → FALLA `pose is not last accepted`;
  - **negativas nuevas:**
    - una obligada descartada aunque la lectura sea posterior a la caducidad → FALLA;
    - una pose anterior a la última obligada → FALLA;
    - ninguna pose de la ráfaga aplicada → FALLA;
  - **positiva nueva:** cola descartable tras la última obligada → `pass`.
  - Las negativas nuevas pasaban con el primer criterio.
- **Mitigaciones que se mantienen:** `_write_cfg` reintenta hasta 40 veces con 50 ms si `Path.replace` da `PermissionError` (`test_write_cfg_retries_a_busy_file`, `test_write_cfg_retry_is_bounded`); los burners de la prueba de carga se crean dentro del bloque protegido (`test_cpu_load_kills_partially_created_burners`).
- **Residual (M2):** con carga extrema (2 x núcleos de procesos girando, a veces con otras suites a la vez) puede fallar M2 (`p95 >= 1000 ms`) y arrastrar N5/N4/N6. Es un residual del entorno, no del código: los plazos son contrato y no se tocan. La prueba de carga corre solo con `DSBX_STRESS=1`, fuera del gate determinista; su docstring lo deja dicho.
