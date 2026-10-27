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
