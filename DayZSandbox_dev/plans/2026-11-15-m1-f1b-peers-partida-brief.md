# F1b-peers en partida: arnés G1-G9 y partidas

2026-11-15 · tarea **F1b-peers**, parte en partida. Rama `claude/f1b-peers` (la parte sin juego está cerrada en `c2b7203`). Spec de implementación (R25) del arnés que acredita §6 del [brief de F1b-peers](2026-11-15-m1-f1b-peers-brief.md) (v1.2, `48452b7`). **v1.0, para la ronda 1 de Sol** (como mucho 2; después arbitra el orquestador).

**Por qué ahora.** F0.3-0 pasó su gate en partida en diag y en retail (`origin/main` `4f18c62`): `WIRE_CAP = 3500` está validado (G10 cumplido). La sesión principal ordenó arrancar las partidas el 2026-11-15. El PR de F1b-peers no se mergea hasta que G1-G9 pasen, porque toca el PBO.

**Qué se reutiliza.** El mapa del arnés de F0.3-0 está en las notas compartidas (`2026-11-15-f1b-peers-mapa-partida-f030.md`). De ahí salen:
- el lanzamiento por WMI y el cierre por WM_CLOSE de los PID propios (`C:\tmp\dsbx-f030-work\partida\run_f030_partida.ps1`, `C:\Users\guill\MCPTest_autotest\harness\probe-lib.ps1`);
- el lease de GPU, con `comprobar --min-vram-libre 4000` y después `adquirir` y `soltar`;
- `gate_core` (PASA, FALLA o INCONCLUSO) y la forma de la evidencia;
- el p95 de `s_puente_eval`;
- las trampas medidas: D12 (unos 560 ms de volcado del log), un solo `script_*.log` por sesión y lo de BattlEye.

`QABridge` y el protocolo `qa0` **no** se reutilizan: aquí habla el backend real (`app/backend/server.py` + `bridge.py`).

## 0. Qué es y qué no

**Es:**
- un arnés que lanza el backend real, un **proxy de fallos** delante del bridge y DayZ (servidor y cliente) con el mod `DayZSandbox`;
- los escenarios G1-G9, con evidencia y veredicto;
- dos ajustes pequeños del mod para que lo medible se pueda medir (§2, D-P3 y D-P4).

**No es:**
- la escena real de F2;
- la web en un navegador (G3 usa la API web por HTTP, como la web);
- G10, que ya está cumplido.

## 1. Entorno y fronteras

- Python 3.14 en `C:\Python314\python.exe`, solo biblioteca estándar y `unittest`. PowerShell 5.1 para el lanzador.
- Todo en 127.0.0.1.
- Ninguna clave en logs, salidas, evidencia ni errores. El proxy quita `key=` de toda ruta antes de escribirla.
- **Partidas con el OK fijo de Guillermo:**
  - lease de GPU como mutex;
  - ningún `DayZ*` ajeno abierto antes de lanzar;
  - cerrar solo los PID propios, por WM_CLOSE;
  - evidencia en `DayZSandbox_dev/evidence/m1/F1b-peers/<build>-<UTC>/`, una carpeta nueva por corrida.
- **Rutas:**
  - DayZ diag: `...\steamapps\common\DayZ\DayZDiag_x64.exe`;
  - servidor retail: `...\common\DayZServer\DayZServer_x64.exe`;
  - cliente retail: `DayZ_BE.exe 0 1 1 -exe DayZ_x64.exe <args>`.
  - Misión y cfg: una copia propia de `C:\tmp\dsbx-f030-work\partida\b1` en la carpeta de trabajo de la partida, con `verifySignatures=0` y, en retail, `BattlEye = 1;`. **No se toca `C:\tmp\dsbx-f02`.**
- **Git:** todo comando que escriba el árbol va con `-c core.autocrlf=false`. Con el árbol sucio fuera de `evidence/`, el veredicto es INCONCLUSO.

## 2. Decisiones de esta parte

- **D-P1. PBO sin firmar.** Se acepta con `verifySignatures=0` en el servidor, también en retail con BattlEye, como F0.2 y F0.3-0. G1 lo acredita en retail. Firmar con una clave propia queda para el despliegue (§9).
- **D-P2. El negativo de G3 no se alcanza con un peer correcto.**
  - El peer anota la `rev` y el `hash` de su propia orden, y el bridge solo resuelve la orden que nombra la generación (`bridge.py`, `_process_world_read_locked`). Así, `fallido/lectura_no_cumple` no aparece con peers reales.
  - Queda acreditado sin juego: BR23 del mod falso, con `annotate_rev_delta`.
  - En partida se prueba el camino positivo y la supersesión (un `apply` nuevo sobre otro observado).
- **D-P3. El corte entre pasos de G5 necesita tiempo entre `retirar` y `anotar`.** Con el peer real son ticks seguidos (unos 20-30 ms).
  - Gancho **solo en diag** (`#ifdef DIAG_DEVELOPER`): un campo opcional `qa_step_gap_ms` en `dsbx_peer.json` (entero de 0 a 10000; 0 o ausente es sin espera). `anotar` no se ejecuta hasta que han pasado esos ms desde `retirar`, y la guarda literal sigue siendo la primera sentencia de `StepAnotar`.
  - En retail el campo no existe: se lee dentro del `#ifdef`.
  - Regla estática nueva: el campo y su uso solo aparecen dentro de `#ifdef DIAG_DEVELOPER`, y `StepAnotar` conserva su guarda literal.
- **D-P4. Diagnóstico en el log del mod, con `tick_ms` en la propia línea** (D12):
  - `rest error ch=<P|R> kind=<n> state=<n> tick_ms=<n>`: en el `OnError` del callback, antes de despachar al canal. R lo registra pero no lo mira (D1 intacta).
  - `rest timeout ch=<P|R> kind=<n> tick_ms=<n>`: en `OnTimeout` y en el watchdog.
  - `rest invalid ch=<P|R> kind=<n> tick_ms=<n>`: un 200 cuya respuesta no pasa su validador.
  - `rest late ch=<P|R> kind=<n> tick_ms=<n>`: una respuesta de una generación ya retirada, que se descarta.
  - `clock tick_ms=<n>`: cada 5000 ms de su propio reloj.

  Ninguna línea lleva la ruta, la clave ni un cuerpo (M4 ya lo exige para todo `Log`).
- **D-P5. G6 se mide de dos formas:**
  - **pendiente:** las líneas `clock` frente al reloj del arnés cuando aparecen, descontando un volcado constante (D12);
  - **pausa:** el arnés suspende el proceso servidor 2000 ms (`NtSuspendProcess`/`NtResumeProcess` por `ctypes`, solo el PID propio) y mide si `tick_ms` salta unos 2000 o se para.

## 3. Piezas y write-set

```
DayZSandbox_dev/qa/live/
  fault_proxy.py          proxy de fallos (§4)                                  [worker]
  f1bp_live.py            orquestador: setup, backend, escenarios G1-G9 (§5)    [worker]
  f1bp_eval.py            evaluador puro sobre la evidencia (§6)                [worker]
  run_f1bp_partida.ps1    lanzador de DayZ, adaptado de L y PL (§1)             [orquestador]
DayZSandbox_dev/qa/tests/
  test_fault_proxy.py     reglas, log sin clave, códigos, retención, corte      [worker]
  test_f1bp_eval.py       evidencia sintética → PASA/FALLA/INCONCLUSO por fila  [worker]
  test_f1bp_dryrun.py     escenarios contra el mod falso, sin DayZ (§7)          [worker]
DayZSandbox/scripts/3_Game/DSBX_Peer.c   D-P3 y D-P4                            [orquestador]
DayZSandbox_dev/app/tests/test_mod_static.py   reglas de D-P3 y D-P4             [orquestador]
```

No se tocan `app/backend/`, `app/web/` ni el resto del mod.

## 4. El proxy de fallos

- **Escucha** en 127.0.0.1 en un puerto propio y reenvía al bridge (`http.client`, una conexión por petición). El peer apunta al proxy: `peer_config.py` recibe un `backend.json` derivado con `bridge_port` = puerto del proxy.
- **Reglas** en un JSON que el orquestador reescribe de forma atómica y el proxy relee si cambia la fecha de modificación. Cada regla tiene un `match` y una `action`.
  - `match`: `route` (`hello`, `poll`, `result` o `catalog`), `peer` (`server` o `client`), `deliver` (`0` o `1`, solo en poll), `nth` (la enésima petición que casa desde que se cargó la regla) y `count` (cuántas veces se aplica).
  - `action`:
    - `pass`;
    - `status` (código y cuerpo JSON `{"ok": false, "error": "<x>"}` como los del bridge, sin reenviar);
    - `hold_ms` (retiene la petición y después la reenvía);
    - `hold_resp_ms` (reenvía y retiene la respuesta);
    - `refuse` (cierra la conexión sin respuesta y sin reenviar);
    - `drop_resp` (reenvía y cierra sin devolver la respuesta);
    - `rewrite` (reenvía y sustituye el cuerpo de la respuesta por uno dado, para G7).
- **Log jsonl**, una línea por petición: `t_ms` (monotónico del arnés), `peer`, `route`, `deliver`, `session` (sí; no es secreto), `action`, `req_bytes`, `upstream_status`, `resp_bytes` y `held_ms`. **Sin `key`**: se quita de la consulta antes de nada.
- Pruebas: cada acción contra un bridge de prueba, y una búsqueda literal de la clave en el log (cero apariciones).

## 5. Escenarios

Cada escenario escribe `samples/<G>.jsonl` (sus pasos y lo que observó) y deja al evaluador el veredicto.

- **El backend corre dentro del proceso del orquestador**, como en las pruebas (`Backend(...)` de `app/backend/server.py`, con su servidor web y el bridge en un puerto fijo).
- **Las órdenes van por la API web**, como la web: `POST /api/session` con la clave humana, `POST /api/apply`, y la lectura por `GET /api/scene` y `GET /api/events` (ver `app/tests/e2e_web.py` y `server.py`).
- **El estado del bridge se lee del objeto**, bajo su candado: peers, epoch, catálogo, sesión y órdenes. La API web no lo expone.
- **Reiniciar el backend** es cerrarlo y crear otro en el mismo puerto, como BR7H1.

| # | Build | Procedimiento | PASA si |
|---|---|---|---|
| G1 carga | diag y retail | Lanzar servidor y cliente con `@DayZSandbox`; esperar el hello de los dos (proxy) hasta 300 s | Los dos peers se presentan; ningún error de script de `DSBX_` en el script log de la sesión; en retail, el cliente sigue conectado a los 120 s (BattlEye no lo echa) |
| G2 handshake | diag | Tras G1 | El cliente lleva el epoch del servidor; catálogo `complete` con `n_classes > 0`; el hello del servidor mide menos de 3500 B (`req_bytes` del proxy) |
| G3 D2 | diag | `apply` de la escena → seguir `pendiente → ejecutando → aplicado → observado`; después, un segundo `apply` (supersesión) | Las dos llegan a `observado` y la generación del mundo es la segunda. El negativo es D-P2 |
| G4 E1 | **retail** | (a) Clave mala: se reescribe `dsbx_peer.json` y se reinicia el backend → 60 s; (b) backend reiniciado con una orden en vuelo (el proxy retiene su resultado); (c) polls cortados 4500 ms (`refuse`) con una orden encolada durante el corte | Durante cada uno, 0 efectos nuevos y la cola vieja sin ejecutar (la generación no cambia por órdenes viejas). **Después de cada uno, recuperación y una orden nueva hasta `observado`** en 60 s. La clave no aparece en ningún `script*.log` ni `.RPT` de servidor o cliente |
| G5 hombre muerto | diag | (a) Cortes de polls de 2500 y 3500 ms a cada peer; (b) `qa_step_gap_ms = 2000` y un corte de polls de 2500 ms que empieza tras `retirar` | (a) Con 2500 no hay re-hello; con 3500, sí, y después hay recuperación. (b) La orden acaba `parcial` (`error/lease_expired`), nunca `fallido`; después, recuperación y orden nueva |
| G6 reloj | diag | 10 min de partida; después, pausa del servidor de 2000 ms | Pendiente `tick_ms`/reloj del arnés entre 0,98 y 1,02; se anota qué hace `tick_ms` en la pausa. Es medida: FALLA solo si la pendiente sale del intervalo |
| G7 lo que no se sabe | diag | Con el proxy: `status` 400, 401, 409, 413 y 500 a P y a R; `hold_resp_ms` 5000 (plazo del motor); `hold_resp_ms` 4000 al acuse de un resultado (dos en vuelo); `hold_resp_ms` 8000 (callback tardío); `rewrite` de un poll sin `ok`, con `ok:1` y con `args:{}` | Es medida: se anota qué línea `rest …` y qué estado da cada código, si P sigue a 500 ms con R retenido, el plazo efectivo y qué hace el validador con cada variante. FALLA solo si el peer pierde la recuperación |
| G8 deduplicación | diag | (a) `drop_resp` al primer resultado; (b) resultado descartado (`status 503` ×4) y reentrega de la orden; (c) backend reiniciado y `op-1` nuevo | (a)(b) un solo efecto y `dup:true` en la reentrega; (c) el `op-1` nuevo se ejecuta |
| G9 E2 | diag | 100 `apply` seguidos por la API | p95 de entrega a resultado < 1000 ms, con los fallos en el denominador (el cálculo de `s_puente_eval`) |

Las filas «es medida» acreditan el dato, no un umbral, salvo lo que dicen.

## 6. Evidencia y veredicto

- `manifest.json`: `git_head`, `git_dirty`, `pbo_sha256`, build, puertos, `key_sha256` (nunca la clave) y versión de DayZ.
- `samples/proxy.jsonl`, `samples/<G>.jsonl` y una copia del `script_*.log` de la sesión de servidor y de cliente (uno por perfil; con dos, `log_ambiguous`).
- `verdict.json` por fila y agregado, como `gate_core`: PASA, FALLA o INCONCLUSO, más el motivo.
- JSON ordenado, en UTF-8 y con LF.

## 7. Gate sin juego del arnés

- `test_fault_proxy.py` y `test_f1bp_eval.py` pasan.
- **Ensayo en seco:** `test_f1bp_dryrun.py` corre G2-G5, G8 y G9 contra el backend real y el **mod falso** (`app/tests/fake_mod.py`) a través del proxy, sin DayZ, y el evaluador da PASA. G1, G6 y G7 se saltan, porque necesitan el motor.
- La suite de `app/tests` sigue verde, y la prueba estática acepta D-P3 y D-P4 con sus reglas y mutaciones.

## 8. Entrega

| Tanda | Quién | Escribe |
|---|---|---|
| L0 | Orquestador | D-P3 y D-P4 en el mod, sus reglas estáticas y el lanzador `run_f1bp_partida.ps1` |
| L1 | DS4.1 en el GX10 (puesto 5), o Nemotron por OpenRouter si está libre | `fault_proxy.py` y `test_fault_proxy.py` |
| L2 | DS4.1 en el GX10 | `f1bp_live.py`, `f1bp_eval.py`, `test_f1bp_eval.py` y `test_f1bp_dryrun.py` |

Cada tanda trabaja en una copia del commit congelado. El orquestador revisa, corre el gate de §7, integra, hace commit y lanza las partidas: diag primero (G1, G2, G3 y G5-G9), después retail (G1 y G4). Sol revisa el código del arnés como mucho en 2 rondas.

## 9. Riesgos

- **Firma del PBO para el despliegue:** sin resolver; aquí, D-P1.
- **El estado del motor para cada código** puede no distinguir 4xx de un fallo de transporte (`restapi.c:16-17`). G7 lo mide; la política de §3.4 ya lo cubre.
- **Suspender el servidor** puede tumbar la conexión del cliente. Va al final de la sesión diag.
- **D12:** el log se ve unos 560 ms tarde. Por eso las líneas llevan `tick_ms` y el evaluador no usa la hora de llegada para nada más que la pendiente de G6.
- **BattlEye:** el cliente lanzado sin BattlEye se cae en retail; el lanzador lo hace como F0.3-0.
