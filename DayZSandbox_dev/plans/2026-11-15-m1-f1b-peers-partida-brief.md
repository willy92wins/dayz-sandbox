# F1b-peers en partida: arnés G1-G9 y partidas

2026-11-15 · tarea **F1b-peers**, parte en partida. Rama `claude/f1b-peers` (la parte sin juego está cerrada en `c2b7203`). Spec de implementación (R25) del arnés que acredita §6 del [brief de F1b-peers](2026-11-15-m1-f1b-peers-brief.md) (v1.3; la v1.2 es `48452b7`). **v1.9, congelada: rondas 1 y 2 de Sol sobre el brief y sobre el código del arnés, con el tope cumplido y el resto arbitrado por el orquestador, más los arbitrajes de las partidas en DayZ y de la revisión del experto de Enforce (§10).**

**Por qué ahora.** F0.3-0 pasó su gate en partida en diag y en retail (`origin/main` `4f18c62`): `WIRE_CAP = 3500` está validado (G10 cumplido). La sesión principal ordenó arrancar las partidas el 2026-11-15. El PR de F1b-peers no se mergea hasta que G1-G9 pasen, porque toca el PBO.

**Qué se reutiliza.** El mapa del arnés de F0.3-0 está en las notas compartidas (`2026-11-15-f1b-peers-mapa-partida-f030.md`). De ahí salen:
- el lanzamiento por WMI y el cierre por WM_CLOSE de los PID propios (`C:\tmp\dsbx-f030-work\partida\run_f030_partida.ps1`, `%USERPROFILE%\MCPTest_autotest\harness\probe-lib.ps1`);
- el lease de GPU, con `comprobar --min-vram-libre 4000` y después `adquirir` y `soltar`;
- `gate_core` (PASA, FALLA o INCONCLUSO) y la forma de la evidencia;
- el p95 de `s_puente_eval`;
- las trampas medidas: D12 (unos 560 ms de volcado del log), un solo `script_*.log` por sesión y lo de BattlEye.

`QABridge` y el protocolo `qa0` **no** se reutilizan: aquí habla el backend real (`app/backend/server.py` + `bridge.py`).

## 0. Qué es y qué no

**Es:**
- un arnés que lanza el backend real, un **proxy de fallos** delante del bridge y DayZ (servidor y cliente) con el mod `DayZSandbox`;
- los escenarios G1-G9, con evidencia y veredicto;
- ajustes pequeños del mod para que lo medible se pueda medir: D-P3 y D-P4.

**No es:**
- la escena real de F2;
- la web en un navegador (G3 usa la API web por HTTP, como la web);
- G10, que ya está cumplido.

## 1. Entorno y fronteras

- Python 3.14 en `C:\Python314\python.exe`, solo biblioteca estándar y `unittest`. PowerShell 5.1 para el lanzador.
- Todo en 127.0.0.1.
- **Ninguna clave** en logs, salidas, evidencia, stderr, trazas de excepción ni errores.
  - El proxy quita `key=` de toda ruta antes de escribirla o de pasarla a cualquier log.
  - El `log_message` de `http.server` se sustituye, porque el de Python escribe la URL entera en stderr.
- **Partidas con el OK fijo de Guillermo:**
  - lease de GPU como mutex;
  - ningún `DayZ*` ajeno abierto antes de lanzar;
  - cerrar solo los PID propios, por WM_CLOSE;
  - evidencia en `DayZSandbox_dev/evidence/m1/F1b-peers/<build>-<UTC>/`, una carpeta nueva por corrida.
- **Rutas:**
  - DayZ diag: `...\steamapps\common\DayZ\DayZDiag_x64.exe`;
  - servidor retail: `...\common\DayZServer\DayZServer_x64.exe`;
  - cliente retail: `DayZ_BE.exe 0 1 1 -exe DayZ_x64.exe <args>`.
  - Misión y cfg: una copia propia de `C:\tmp\dsbx-f030-work\partida\b1` en la carpeta de trabajo de la partida (`C:\tmp\dsbx-f1bpeers-work\partida\`), con `verifySignatures=0` y, en retail, `BattlEye = 1;`. **No se toca `C:\tmp\dsbx-f02`.**
- **Git:** todo comando que escriba el árbol va con `-c core.autocrlf=false`. Con el árbol sucio fuera de `evidence/`, el veredicto es INCONCLUSO.

## 2. Decisiones de esta parte

- **D-P1. PBO sin firmar.** Se acepta con `verifySignatures=0` en el servidor, también en retail con BattlEye, como F0.2 y F0.3-0. G1 lo acredita en retail. Firmar con una clave propia queda para el despliegue (§9).
- **D-P2. El negativo de G3, en partida.**
  - El proxy reescribe `args.rev` en la respuesta del poll que entrega la orden; los demás campos siguen válidos.
  - El peer anota lo que recibe y el backend compara con la revisión original: el camino directo del resultado (`bridge.py`, tras `done`) acaba en `fallido/lectura_no_cumple`.
  - Se exige ese motivo exacto y que la orden nunca llegue a `observado`. BR23 del mod falso lo complementa.
- **D-P3. Gancho solo en diag para G5.**
  - Campo opcional `qa_step_gap_ms` en `dsbx_peer.json` (entero de 0 a 10000; 0 o ausente es sin espera), leído en `LoadConfig` dentro de `#ifdef DIAG_DEVELOPER`. En retail el campo no existe.
  - `anotar` no se ejecuta hasta que han pasado esos ms desde `retirar`. La guarda literal sigue siendo la primera sentencia de `StepAnotar`.
  - Se registra `config qa_step_gap_ms=<n>` en cada `LoadConfig` de diag, para comprobar que vuelve a 0 antes de G9.
  - Reglas estáticas nuevas: el campo y su uso solo dentro de `#ifdef DIAG_DEVELOPER`; `StepAnotar` conserva su guarda literal.
- **D-P4. Diagnóstico en el log del mod, con `tick_ms` en la propia línea** (D12). En diag y en retail.
  - `effect step=<retirar|anotar> session=<s> op=<op> tick_ms=<n>`: en el punto exacto del efecto, justo después de `SetGeneration`. **Es la evidencia de cuántos efectos hay** (L-04).
  - `rest error ch=<P|R> kind=<n> state=<n> tick_ms=<n>`: en `OnHttpDone`, antes de despachar al canal. R lo registra pero no lo mira (D1 intacta: `OnChannelRError` sigue sin ver el estado).
  - `rest timeout ch=<P|R> kind=<n> src=<engine|watchdog> tick_ms=<n>`.
  - `rest invalid ch=<P|R> kind=<n> tick_ms=<n>`: un 200 cuya respuesta no pasa su validador.
  - `rest late ch=<P|R> kind=<n> tick_ms=<n>`: una respuesta de una petición ya retirada, que se descarta.
  - `rest repeat ch=<P|R> kind=<n> via=<success|error|timeout> tick_ms=<n>`: en el propio callback, cuando el motor lo invoca otra vez después de cerrado (`m_Done`, también tras `Retire`). Antes, ese descarte era invisible (L-15).
  - `lease lost age_ms=<n> tick_ms=<n>`: en `CheckLeaseTimeout`, con la edad desde el último poll válido.
  - `clock tick_ms=<n>`: cada 5000 ms de su propio reloj.
  - `shutdown role=<server|client> created_n=<n> inflight_p=<0|1> inflight_r=<0|1>`: al cerrar el peer. `created_n` acota el informe de fuga del motor (v1.3, §10).

  Ninguna línea lleva la ruta, la clave ni un cuerpo; M4 ya lo exige para todo `Log`. `session` y `op` no son secretos.

  **`tick_ms` es el reloj del motor** (`GetTickTime`, propio de cada proceso), no el del arnés. Para situar una línea en el reloj del arnés se usa su hora de pared, la que el motor escribe al principio de cada línea al hacer `Print` (v1.4, §10, H-04).
- **D-P5. Reloj.**
  - **Pendiente** (medida complementaria): las líneas `clock` frente al reloj del arnés al aparecer, con un volcado constante (D12).
  - **Plazo con efecto pendiente durante una pausa** (lo que acredita la cota de 100 ms): en cuanto el proxy sirve la respuesta que entrega una orden de TTL 1500 ms, el arnés suspende el servidor 2000 ms (`NtSuspendProcess`/`NtResumeProcess` por `ctypes`, solo el PID propio, reanudación garantizada en `finally`).
    - **El veredicto usa solo referencias independientes del reloj del peer**, todas en el monotónico del arnés, que es el del backend porque corre en el mismo proceso: `T_d` (respuesta de entrega servida), `T_s` y `T_e` (suspensión y reanudación), `D` (emisión + TTL) y `T_r` (llegada del resultado al proxy).
    - Efecto pendiente demostrado: no llega ningún resultado de esa orden antes de `T_s`.
    - **FALLA** si el resultado es `done` (los dos efectos) y `T_r > D + 150 ms` (100 ms de cota más 50 de envío por R, con R libre). **PASA** con `rejected/expired` o `error/expired`.
    - Las líneas `effect` y `clock` solo sirven para medir la discontinuidad de `tick_ms` en la pausa; nunca absuelven un efecto (L-09).
    - Si G6 falla, se cambia la fuente de reloj del peer en esta misma tarea (brief de F1b-peers §9).

## 3. Piezas y write-set

```
DayZSandbox_dev/qa/live/
  fault_proxy.py          proxy de fallos (§4)                                  [worker]
  f1bp_live.py            orquestador: setup, backend, escenarios G1-G9 (§5)    [worker]
  f1bp_eval.py            evaluador puro sobre la evidencia (§6)                [worker]
  run_f1bp_partida.ps1    lanzador de DayZ, adaptado de L y PL (§1, §8)         [orquestador]
DayZSandbox_dev/qa/tests/
  test_fault_proxy.py     reglas, barrera, log y salidas sin clave              [worker]
  test_f1bp_eval.py       evidencia sintética → PASA/FALLA/INCONCLUSO por fila  [worker]
  test_f1bp_dryrun.py     ensayo con el mod falso, sin DayZ (§7)                [worker]
DayZSandbox/scripts/3_Game/DSBX_Peer.c   D-P3 y D-P4                            [orquestador]
DayZSandbox_dev/app/tests/test_mod_static.py   reglas de D-P3 y D-P4             [orquestador]
```

No se tocan `app/backend/`, `app/web/` ni el resto del mod.

## 4. El proxy de fallos

- **Escucha** en 127.0.0.1 en un puerto propio y reenvía al bridge con una conexión por petición; atiende varias conexiones a la vez (`ThreadingHTTPServer`). El peer apunta al proxy: `peer_config.py` recibe un `backend.json` derivado con `bridge_port` = puerto del proxy.
- **Reglas versionadas.**
  - El orquestador escribe de forma atómica un JSON `{version, rules: [...]}`.
  - El proxy lo relee y, al activarlo, escribe `rules_active.json` con esa `version`. **Una inyección solo cuenta desde que `rules_active.json` confirma su versión.**
  - Cada regla tiene un `id`, un `match` y una `action`.
- **`match`:**
  - `route`: `hello`, `poll`, `result` o `catalog`;
  - `peer`: `server` o `client`;
  - `deliver`: `0` o `1`, solo en poll;
  - `resp_has_op`: `true` si la respuesta del bridge trae una orden; sirve de disparador;
  - `nth` y `count`: se consumen de forma atómica bajo un candado.
- **`action`:**
  - `pass`;
  - `status`: código y cuerpo JSON `{"ok": false, "error": "<x>"}`, sin reenviar;
  - `hold_ms`: retiene la petición y después la reenvía;
  - `hold_resp_ms`: reenvía y retiene la respuesta;
  - `refuse`: cierra la conexión sin respuesta y sin reenviar;
  - `drop_resp`: reenvía y cierra sin devolver la respuesta;
  - `rewrite`: reenvía y sustituye campos de la respuesta, conservando el resto válido;
  - `then_cut_ms`: tras servir esta respuesta, `refuse` a todas las peticiones de ese peer en las rutas indicadas durante N ms. Es el disparador sincronizado de G5 (b).
  - `then_hold_ms`: tras servir esta respuesta, durante N ms reenvía al momento cada petición de ese peer en las rutas indicadas y retiene su respuesta hasta el final absoluto de la ventana (instante de disparo + N), y entonces la devuelve. Un poll entregador se reenvía como mantenimiento (`deliver=0`) para que el bridge conteste ya y no sume su long-poll (L-13). No provoca errores de conexión (que el motor puede dar como `CLIENTERROR`, `restapi.c:16-17`). Si la ventana pasa del plazo del motor (3 s), la petición vence por ese plazo. Es el corte de G5 (a).
- **Barrera de corte:** una regla de corte con `abort_inflight: true` cierra al activarse las conexiones de cliente de las peticiones ya reenviadas y pendientes de ese peer (los long-polls), y lo registra. Así un poll anterior no entrega una orden «durante el corte».
- **Log jsonl**, una línea por petición:
  - `req_id`, `rule_id` y `rules_version`;
  - `t_ms`, monotónico del arnés;
  - `peer`, `route`, `deliver` y `session` (no es secreto);
  - `action`, `req_bytes`, `upstream_status`, `resp_bytes`, `held_ms` y `aborted`.
  - **Sin `key`.**
- **Pruebas:**
  - cada acción contra un bridge de prueba;
  - la barrera con un long-poll pendiente;
  - el consumo de `nth`/`count` con conexiones concurrentes;
  - la búsqueda literal de todas las claves usadas en el jsonl, stdout, stderr y las trazas de excepción del proceso (cero apariciones).

## 5. Escenarios

Cada escenario escribe `samples/<G>.jsonl` (sus pasos, las versiones de reglas confirmadas y lo que observó) y deja al evaluador el veredicto.
- **El backend corre dentro del proceso del orquestador**, como en las pruebas (`Backend(...)` de `app/backend/server.py`, con su servidor web y el bridge en un puerto fijo).
- **Las órdenes van por la API web**, como la web: `POST /api/session` con la clave humana, `POST /api/apply`, y la lectura por `GET /api/scene` y `GET /api/events` (ver `app/tests/e2e_web.py` y `server.py`).
- **El estado del bridge se lee del objeto**, bajo su candado: peers, epoch, catálogo, sesión y órdenes. La API web no lo expone.
- **Reiniciar el backend** es cerrarlo y crear otro en el mismo puerto, como BR7H1.
- **Los efectos se cuentan** con las líneas `effect` del script log del servidor (D-P4), leídas tras el volcado y, al final, tras cerrar.
- **Recuperación (P-08):** después de cada corte, reinicio o inyección, el peer vuelve a presentarse, el backend reconcilia y **una orden nueva llega a `observado`** en 60 s. Sin eso, la fila es FALLA.
- **INCONCLUSO:** una inyección que no se observa (regla sin casar o versión sin confirmar) deja su fila en INCONCLUSO.

| # | Build | Procedimiento | PASA si |
|---|---|---|---|
| G1 carga | diag y retail | Lanzar servidor y cliente con `@DayZSandbox`; esperar el hello de los dos (proxy), hasta 300 s | Los dos peers se presentan. Ningún error de script de `DSBX_` en el script log ni en el RPT de la sesión; el informe de cierre de `DSBX_Callback` solo se admite dentro de su cota (v1.3, §10). En retail, el cliente sigue conectado a los 120 s |
| G2 handshake | diag | Tras G1 | El cliente lleva el epoch del servidor; catálogo `complete` con `n_classes > 0`; la mayor página de catálogo mide ≥ 3000 B y < 3500 (`req_bytes`) y fue aceptada; el hello del servidor mide < 3500 |
| G3 D2 | diag | (a) `apply` → `pendiente → ejecutando → aplicado → observado`; (b) un segundo `apply` (supersesión); (c) negativo de D-P2 | (a)(b) las dos `observado`, con una `retirar` y una `anotar` cada una. (c) `fallido/lectura_no_cumple`, nunca `observado`. Recuperación |
| G4 E1 | **retail** | (a) Clave mala pero válida de forma: se escribe en `dsbx_peer.json` y se fuerza un hello con un 409 al siguiente poll; 60 s con una orden de TTL 2000 ms encolada al principio (el TTL, por los `bridge_kwargs` del backend en proceso); después, la clave buena. (b) Backend reiniciado con una orden en vuelo; tras recuperar la sesión nueva, el proxy entrega (`rewrite` de un poll) una orden con la sesión vieja. (c) Corte de polls de 4500 ms con `abort_inflight`, y una orden de TTL 30000 ms encolada durante el corte, todavía vigente al recuperar | (a) Hellos rechazados por el bridge (401 en el proxy), 0 `effect` durante la ventana, y la orden encolada nunca tiene `effect`, tampoco tras recuperar. (b) La orden vieja da `rejected/stale_session` sin `effect`. (c) El backend da la orden por perdida con la conexión (`fallido/conexion_perdida` en sus eventos) y la orden nunca tiene `effect`, ni durante su vigencia ni después de recuperar. **En los tres, recuperación.** La clave no aparece en ningún `script*.log` ni `.RPT` de servidor o cliente, leídos tras cerrar |
| G5 hombre muerto | diag | (a) Por peer, `then_hold_ms` de hello y poll, disparado por una respuesta de poll válida, de 2500 ms y de 4500 ms. (b) En el servidor, `qa_step_gap_ms` de 2500 y de 4000 ms, con `then_cut_ms = 6000` de hello y poll disparado por la respuesta que entrega la orden. Al final, `qa_step_gap_ms = 0` confirmado por el log | (a) Con 2500, el mayor intervalo entre respuestas válidas a ese peer (proxy, reloj del arnés, con el tiempo del backend) es menor que `lease_ms` y no hay `lease lost`. Con 4500, `lease lost` con `age_ms` ≥ `lease_ms` y < `lease_ms + 200`. En servidor y en cliente. (b) Con 2500, una `retirar` y una `anotar`, y la orden `observado`. Con 4000, una `retirar`, ninguna `anotar`, y la orden en `parcial` (`error/lease_expired`), nunca `fallido`. Así se acota «acepta hasta y rechaza desde» a los dos lados de `lease_ms`. Recuperación |
| G6 reloj | diag | 10 min de partida (líneas `clock`); después, el plazo con pausa de D-P5 | El criterio de D-P5 con referencias independientes: FALLA un `done` con `T_r > D + 150 ms`. Pendiente entre 0,98 y 1,02 (complementaria); se anota la discontinuidad de `tick_ms` en la pausa. Recuperación |
| G7 lo que no se sabe | diag | Invariantes, más medidas exploratorias | **Invariantes** (FALLA si no se cumplen): con el acuse de R retenido 4000 ms, los polls de mantenimiento de P siguen sin huecos de más de 750 ms; las respuestas reescritas no válidas (sin `ok`, `ok:false`, `now_ms` con decimales o en texto, sin `args`) dan `rest invalid`, ningún `effect` y no renuevan el lease (con todas las de P no válidas durante más de `lease_ms`, aparece `lease lost`); el resultado se acusa una vez. **Callback tardío** (L-15): se retiene 8000 ms la respuesta de un poll; si el motor invoca después el callback ya cerrado o retirado, tiene que salir `rest late` o `rest repeat` sin ningún cambio de estado; si no se observa ninguna invocación tardía, ese caso queda INCONCLUSO, sin tumbar las demás invariantes. **Medidas** (se anotan): la línea `rest …` y el estado de cada `status` 400, 401, 409, 413 y 500 a P y a R; el plazo efectivo de `hold_resp_ms` 5000 (desde que el proxy recibe la petición hasta que el motor cierra la conexión); qué hace el validador con `ok:1` y `args:{}`. Recuperación |
| G8 deduplicación | diag | (a) `drop_resp` al primer resultado; (b) resultado bloqueado (`status 503` ×4) y reentrega de la orden por el backend; (c) backend reiniciado y `op-1` nuevo | (a) Una `retirar` y una `anotar`; el resultado repetido no cambia nada. (b) Una sola pareja de `effect` y `dup:true` en el reenvío. (c) El `op-1` de la sesión nueva tiene su propia pareja de `effect` |
| G9 E2 | diag | Con `qa_step_gap_ms = 0` confirmado: 100 `apply` seguidos por la API | p95 de entrega a resultado < 1000 ms, con los fallos en el denominador (cálculo de `s_puente_eval`); una pareja de `effect` por orden |

## 6. Evidencia y veredicto

- `manifest.json`: `git_head`, `git_dirty`, `pbo_sha256`, build, puertos, `key_sha256` de cada clave usada (nunca la clave) y versión de DayZ.
- `samples/proxy.jsonl` y `samples/<G>.jsonl`.
- Copia del `script_*.log` **y del `.RPT`** de la sesión, de servidor y de cliente, con un inventario de los logs de cada perfil. Con dos `script_*.log` de la sesión, `log_ambiguous`. Se leen tras cerrar el juego; la ausencia de un fichero es INCONCLUSO, no «cero filtraciones».
- `verdict.json` por fila y agregado, como `gate_core`: PASA, FALLA o INCONCLUSO, más el motivo.
- JSON ordenado, en UTF-8 y con LF.

## 7. Gate sin juego del arnés

- `test_fault_proxy.py` y `test_f1bp_eval.py` pasan.
- **Ensayo en seco:** `test_f1bp_dryrun.py` corre, contra el backend real y el **mod falso** a través del proxy, sin DayZ, **solo** lo que el falso puede acreditar:
  - G2, salvo la página de 3000 B;
  - G3, con el negativo por `rewrite`;
  - G4 (b) con la orden de sesión vieja;
  - G8 (a), (b) y (c);
  - G9.

  El falso va con `r_retry_unknown=True` (D1), y el evaluador real da PASA. Los efectos del falso se cuentan por su propio registro de efectos, no fabricando líneas `effect`. G1, G4 (a) y (c), G5, G6 y G7 se saltan: necesitan el motor, o la transición local por vencimiento que el falso no tiene.
- La suite de `app/tests` sigue verde. La prueba estática acepta D-P3 y D-P4, con sus reglas y mutaciones.

## 8. Entrega

| Tanda | Quién | Escribe |
|---|---|---|
| L0 | Orquestador | D-P3 y D-P4 en el mod, sus reglas estáticas y el lanzador `run_f1bp_partida.ps1` |
| L1 | DS4.1 en el GX10 (puesto 5), o Nemotron por OpenRouter si está libre | `fault_proxy.py` y `test_fault_proxy.py` |
| L2 | DS4.1 en el GX10 | `f1bp_live.py`, `f1bp_eval.py`, `test_f1bp_eval.py` y `test_f1bp_dryrun.py` |

**El lanzador (L0)**, sobre el esqueleto de F0.3-0:
- comprueba las condiciones previas y toma el lease;
- arranca el orquestador, que escribe las configuraciones del peer;
- lanza servidor y cliente por WMI y escribe `pids.json` con PID e instante de creación de cada proceso propio, incluido el lanzador de BattlEye;
- al acabar, cierra por WM_CLOSE y **solo suelta el lease cuando confirma que no queda vivo ningún PID propio** (mismo PID e instante). Si queda alguno, no suelta, lo registra y sale con error.

Cada tanda trabaja en una copia del commit congelado. El orquestador revisa, corre el gate de §7, integra, hace commit y lanza las partidas: diag primero (G1-G3 y G5-G9), después retail (G1 y G4). Sol revisa el código del arnés como mucho en 2 rondas.

## 9. Riesgos

- **Firma del PBO para el despliegue:** sin resolver; aquí, D-P1.
- **El estado del motor para cada código** puede no distinguir 4xx de un fallo de transporte (`restapi.c:16-17`). G7 lo mide; la política de §3.4 ya lo cubre.
- **Suspender el servidor** puede tumbar la conexión del cliente. Va al final de la sesión diag, con reanudación garantizada.
- **D12:** el log se ve unos 560 ms tarde. Por eso las líneas llevan `tick_ms` y la hora de llegada solo se usa para la pendiente de G6.
- **BattlEye:** el cliente lanzado sin BattlEye se cae en retail; el lanzador lo hace como F0.3-0.

## 10. Cambios por la revisión

**Ronda 1 de Sol** (`gpt-6.1-sol`, solo lectura, sobre `d5ae0c4`; UNSOUND con 4 bloqueantes y 8 importantes). Se aplican todos:

| Hallazgo | Qué cambia |
|---|---|
| L-01 · bloqueante · el corte de G5 (b) no hacía vencer el lease entre pasos | Huecos de 2500 y 4000 ms, a los dos lados de `lease_ms`, con corte de 6000 ms de hello y poll sincronizado con la respuesta que entrega la orden (`then_cut_ms`). Hueco a 0 confirmado por el log antes de G9 (D-P3) |
| L-02 · bloqueante · perder el acuse no provoca reentrega | G8 separa la idempotencia del resultado (a) de la reentrega provocada (b), y exige `dup:true` solo en (b) |
| L-03 · bloqueante · G7 solo fallaba sin recuperación | Invariantes obligatorias (cadencia de P con R retenido, respuestas no válidas sin efecto ni renovación, callback tardío neutro) y medidas aparte; casos de `now_ms` con decimales o en texto y página de catálogo de ≥ 3000 B en G2; inyección no observada → INCONCLUSO |
| L-04 · bloqueante · no se contaban los efectos | Línea `effect` en el punto del efecto, también en retail (D-P4); el evaluador rechaza una ejecución doble aunque la generación final sea la misma |
| L-05 · importante · el negativo de G3 sí se alcanza | Se reescribe `args.rev` en el poll de entrega y se exige `fallido/lectura_no_cumple` (D-P2) |
| L-06 · importante · G4 (b) no probaba el rechazo de una orden con sesión vieja | Entrega tardía de una orden de la sesión vieja tras recuperar; clave mala válida de forma, aislada del reinicio |
| L-07 · importante · faltaba una barrera para las peticiones en vuelo | Reglas versionadas con confirmación, `abort_inflight` para los long-polls, consumo atómico de `nth`/`count` e identificadores de regla y de petición |
| L-08 · importante · G5 (a) no medía la ventana | `lease lost age_ms`; retención `then_hold_ms` disparada por un poll válido (edad cero al empezar, y sin errores de conexión que el motor daría como `CLIENTERROR`) a los dos lados del umbral; el observable del cliente; la recuperación de P-08 |
| L-09 · importante · la pendiente no acreditaba la cota de 100 ms | Plazo con efecto pendiente durante la pausa, medido contra el monotónico del backend (D-P5) |
| L-10 · importante · el falso no acredita todo el ensayo | §7 delimita lo que acredita el falso, con D1 activada y sin fabricar estados |
| L-11 · importante · la clave podía salir por stderr; faltaban los RPT | `log_message` sustituido y búsqueda en todas las salidas; RPT e inventario de logs en la evidencia; lectura tras cerrar |
| L-12 · importante · el lanzador soltaba el lease con procesos vivos | Cierre confirmado por PID e instante de creación antes de soltar; reanudación de la pausa en `finally` |

**Ronda 2 de Sol** (sobre `f89eb4c`, la última). Cierra L-01, L-02, L-04 a L-07 y L-10 a L-12. Deja abiertos L-03, L-08 y L-09, y añade L-13, L-14 y L-15, todos importantes. Con el tope cumplido, arbitra el orquestador:

| Hallazgo | Arbitraje |
|---|---|
| L-08 y L-13 · retener y después reenviar suma el long-poll del bridge: unos 4500 ms sin respuesta válida con un peer correcto | `then_hold_ms` reenvía al momento como mantenimiento (`deliver=0`) y retiene la respuesta hasta el final absoluto de la ventana. G5 (a) mide el mayor intervalo entre respuestas válidas en el reloj del arnés, con el tiempo del backend incluido |
| L-09 · G6 fechaba los efectos con el reloj en duda | Veredicto solo con referencias independientes (`T_d`, `T_s`, `T_e`, `D`, `T_r`), con efecto pendiente demostrado y la discontinuidad de `tick_ms` como medida (D-P5) |
| L-14 · en G4 (c) el TTL corto hacía caducar la orden antes de perder la conexión | TTL de 30000 ms, todavía vigente al recuperar; se exige `fallido/conexion_perdida` y ningún `effect` |
| L-03 y L-15 · un callback tardío puede no llegar nunca, y su descarte por `m_Done` era invisible | `rest repeat` en el propio callback (D-P4); el caso del callback tardío exige `rest late` o `rest repeat` sin cambios si hay invocación, y queda INCONCLUSO si no la hay |

**v1.3: humos de G1 en DayZDiag** (15-nov, sin escenarios, con un orquestador mínimo de G1). El orquestador arbitra con esta evidencia:

| Hallazgo | Arbitraje |
|---|---|
| H-01 · el evaluador buscaba el literal `SCRIPT (E)`, pero el motor escribe `SCRIPT    (E):` con relleno; G1 daba PASA en falso | Regex `SCRIPT\s+\(E\)` y pruebas con el formato real (`5bf25cc`) |
| H-02 · el lanzador perdía su `-Root`, porque `probe-lib.ps1` fija `$script:Root` | El parámetro pasa a llamarse `-WorkRoot` y el evaluador se lanza con ruta absoluta (`5bf25cc`) |
| H-03 · al cerrar, el motor informa `Leaked 'DSBX_Callback' script instance (Nx)!` (2x en el servidor y 1x en el cliente), con `Shutdown()` ya ejecutado | **Medido: el motor retiene todo `RestCallback` que recibe**, no solo los que están en vuelo. Con 3 respuestas 500 inyectadas a los polls del servidor, el servidor registra `created_n=5 inflight_p=1 inflight_r=0` y el motor informa 5x. El cliente, `created_n=1` y 1x. Siguen vivos los 3 retirados tras su `OnError` y el de R, ocioso en el pool. `RestContext.reset()` no cambia nada (probado en partida, `a4ea40a`). El cierre es limpio: sin volcados y con `Termination successfully completed`. El mod ya acota la retención: el pool reutiliza y solo se crea un callback tras un fallo, con presupuesto de 2000. Reutilizar uno tras su `OnError` rompería la defensa contra `OnError` repetidos. **Regla:** la línea `shutdown` lleva `created_n` (`e566fa0`). El informe de `DSBX_Callback` no cuenta como error de script si 0 < N ≤ la suma de `created_n` de las líneas `shutdown` anteriores del mismo script log; para el RPT, la de todo el script log del mismo peer, porque el RPT del cliente no lleva las líneas `[DSBX]`. Sin `shutdown`, con N fuera de la cota o con otra clase `DSBX_`, sigue siendo error. G1 anota cada informe tolerado en `exit_leak_cb` |

**v1.4: el reloj de las líneas del log** (15-nov, revisando el evaluador antes de las partidas de G4-G7). El orquestador arbitra:

| Hallazgo | Arbitraje |
|---|---|
| H-04 · Ni el brief ni EVIDENCIA decían cómo comparar el `tick_ms` de una línea con una ventana del arnés, y el evaluador comparaba los dos relojes directamente. En partida, `tick_ms` va por unos 2·10⁵ (`GetTickTime` desde que arranca el proceso) y el arnés por unos 8·10⁷. Con eso, G5 a4500 y G7 `invalid_*` fallaban siempre; G5 a2500, G4 (a) y G7 «sin efecto en la ventana» pasaban en vacío; `late_cb` quedaba INCONCLUSO siempre. La pendiente de G6 mezclaba el reloj del servidor con el del cliente | **Cada línea se sitúa por su hora de pared**: el motor la escribe al hacer `Print` (`12:49:39.023 …`), y el arnés anota la pareja (`t_ms`, hora de pared) en el `start` de cada escenario (`wall`) y en el manifest (`t0_ms`, `t0_wall`). Un error de mapeo de ±250 ms se tolera en las ventanas; entre casos seguidos de G7, la cota alta no se ensancha. Sin ancla, G4, G5 y G7 son INCONCLUSO. En el ensayo en seco, el arnés escribe `tick_ms` con su propio reloj y se usa tal cual. `tick_ms` solo se usa para la pendiente y el salto de G6, sobre las líneas `clock` del servidor |
| H-05 · el evaluador de G3 pedía recuperación tras a y b, y ningún `effect` en c; el contrato no pide ninguna de las dos cosas. Con el mod falso, el ensayo en seco de L2b1 no podía pasar | La recuperación va tras el caso c, que es la inyección (P-08). En c, el peer anota la revisión reescrita y el backend la rechaza (D-P2): sus `effect` son esperables y solo se anotan. El criterio de c sigue siendo `fallido/lectura_no_cumple` y nunca `observado` |
| H-06 · G7 mezclaba las medidas con las invariantes | `ok:1` y `args:{}`, que el validador puede aceptar, van como `measure_*`, no como `invalid_*` (que exige un `rest invalid` por respuesta reescrita) |

**v1.5: ronda 1 de Sol sobre el código del arnés** (`gpt-6.1-sol`, solo lectura, sobre `6e11c61`; UNSOUND con 4 bloqueantes y 11 importantes). Está de acuerdo con H-01..H-06. Se aplican todos sus hallazgos; las reglas exactas están en EVIDENCIA, «v1.5», R1-R15:

| Hallazgo | Regla |
|---|---|
| Q-01 · bloqueante · el lanzador podía adoptar o cerrar un cliente ajeno y soltar el lease con el propio abierto | R14 |
| Q-02 · bloqueante · `rules_active` se publicaba antes de la barrera de corte | R13 |
| Q-03 · bloqueante · cobertura incompleta dada por buena | R7 |
| Q-04 · bloqueante · la deduplicación por tick escondía ejecuciones dobles | R8 |
| Q-05 · importante · una regla confirmada no prueba que se inyectara | R9 |
| Q-06 · importante · el proxy no veía el peer de los hellos reales | `189c365` y R15 |
| Q-07 · importante · ops de sesiones distintas mezcladas | R5 |
| Q-08 · importante · cadencias con huecos sin medir | R11 |
| Q-09 · importante · G7 atribuía a la inyección los efectos de su recuperación | R10 |
| Q-10 · importante · G6 aceptaba pausas no válidas | R12 |
| Q-11 · importante · G9 fechaba el `apply` tras el HTTP | R6 |
| Q-12 · importante · inventario y escaneo con nombres incompatibles | R3, R4 |
| Q-13 · importante · una clave filtrada no tumbaba la corrida | R4 |
| Q-14 · importante · procedencia sin comprobar | R1 |
| Q-15 · importante · `logs_ready` no acreditaba el cierre | R2 |

**H-07, el estado del motor para un 4xx (ensayo diag del 15-nov, `b95a8b2`), arbitraje del orquestador:**
- **Lo medido:** un 409 llega a `OnError` como 5 (`EREST_ERROR`) y un 500 como 6. El enum es secuencial (`restapi.c:16-17`): `EREST_ERROR_CLIENTERROR` vale 6, aunque el comentario diga que es igual a `EREST_ERROR`.
- **El mod cumple su brief.** La fila `CLIENTERROR` de P (brief de F1b-peers §3.4) salta con un 500. Un 4xx cae en «cualquier otro fallo», y el peer se vuelve a presentar por la regla de `lease_ms`, que es justo lo que §3.4 preveía «si el motor no entrega `CLIENTERROR` para un 4xx». El mod no se toca.
- **El arnés sí cambia.** Para forzar un hello (G4 a y G5 b), el proxy inyecta un **500** a un poll, no un 409; con un 409 G5 b no llegaba a releer la configuración.
- **Pregunta de producto, para el experto de Enforce y Guillermo:** que la fila 1 compare con `EREST_ERROR` para presentarse antes tras un 4xx.

**H-08, una orden sin `args` (mismo ensayo):**
- **Lo medido:** el poll sigue siendo válido y el verbo rechaza la orden (`rejected/bad_args`, `fallido/bad_args`), sin efectos y sin `rest invalid` (`DSBX_Peer.c:1123-1126`). Lo mismo con `args:{}`.
- **El mod cumple su brief:** la validación de §3.5 es de la respuesta, y la orden se rechaza en el verbo. La expectativa de G7 («sin args → `rest invalid`») era errónea.
- **El caso pasa a ser medida** (`measure_no_args_P`). Las dos medidas con orden exigen que su op no tenga `effect`.

**H-09, la inyección observada (R9):**
- **El problema:** el `rules_active` lo anota el orquestador al ver el fichero, con su retraso de sondeo. Un long-poll recibido antes del caso actúa al servir la respuesta (G3 c en el seco). Comparar la línea del proxy con ese `t_ms` daba «no observada» en falso.
- **El arbitraje:** cuenta la versión con que el proxy etiqueta la línea, servida después de escribirse esa versión.

**v1.6: ronda 2 de Sol sobre el código del arnés** (sobre `5804459`; UNSOUND). Cierra 12 de 15 Q y deja abiertas Q-01, Q-02 y Q-05. Está de acuerdo con H-07 y H-08, y con H-09 solo a medias. Era la última ronda: arbitra el orquestador. Todos los hallazgos son reales y baratos, así que se aplican todos; las reglas están en EVIDENCIA, «v1.6», R16-R27:

| Hallazgo | Regla |
|---|---|
| Z-01 · bloqueante (Q-01) · se adoptaba el cliente retail por cercanía en el tiempo | R16: solo un descendiente del lanzador BattlEye |
| Z-02 · bloqueante (Q-02) · una petición ya enviada podía cruzar la barrera | R17 |
| Z-03 · `invalid_all_P` pasaba con respuestas no válidas espaciadas | R22 |
| Z-04 · G8 a pasaba sin ver el resultado repetido | R23 |
| Z-05 · un callback tardío con efecto no tumbaba G7 | R24 |
| Z-06 (Q-05) · medidas de G7 sin inyección observada | R21 |
| Z-07 (Q-05, H-09) · el proxy anotaba la versión de recepción, no la de la acción | R18 |
| Z-08 · G4 a podía fallar por un poll anterior autenticado | R25 |
| Z-09 · un escaneo incompleto podía acabar en PASA | R26 |
| Z-10 · la retención de 1500 ms no garantizaba el orden | R27 |

**H-10 y H-11, de la partida diag final (`5804459`).** El arbitraje es del orquestador:
- **Resultado:** G1, G2, G3, G8 y G9 PASA; G5 y G7 FALLA; G6 INCONCLUSO.
- **H-10:** la regla `resp_has_op` de G5 b se disparó con `rd-4`, la lectura interna con que el backend reconcilia tras un hello, y no con la orden del caso. El corte empezó antes de entregarla, y la orden acabó en `conexion_perdida`. Corregido con R19, el prefijo `op-`.
- **H-11:** las recuperaciones que fallaron acabaron en `fallido/conexion_perdida`. Se encolaron mientras el servidor volvía a presentarse: tras un lease vencido, o tras un paro del servidor de ~1,7 s después de a2500, con `clock` y `lease lost` en el mismo tick. El bridge falla lo pendiente cuando cambia la `conn` (§2.5.3). Corregido con R20.
- **G6:** su INCONCLUSO es Z-07. La línea de `g6_deliver` llevaba la versión de recepción (67) y no la de la regla (68). La pausa en sí fue válida: suspensión 73 ms después de la entrega, 2156 ms de pausa y el plazo `D` dentro.

**H-12, emparejar ventana y caso en G5 (partida diag v1.6, `3806133`), arbitraje del orquestador:**
- **El problema:** el disparo de una regla de G5 a puede caer fracciones de milisegundo antes de que se escriba su `case`. El evaluador emparejaba por `t_start_ms` y prefería las ventanas posteriores al caso, así que daba a cada a2500 la ventana del a4500 siguiente. Salía «hueco 4501» en a2500 y «sin lease lost» en a4500.
- **El arbitraje:** la ventana lleva el `rule_id` de su regla y se empareja por él. Si no lo lleva, va con el caso entre cuyo `t_ms` y el del caso siguiente se escribió la ventana.
- **Con eso, la partida v1.6 tiene las ocho filas diag en PASA**, G5 incluida: hueco máximo de 2500/2501 ms y `lease lost` en a4500 con la edad en rango.

**H-13, revisión del experto de Enforce (15-nov, «OK con arreglos»), arbitraje del orquestador:**
- **El mod sí cambia.** Se aplican el MUST y los cuatro SHOULD (brief de F1b-peers §10). Cada arreglo tiene su regla estática y sus mutaciones en `test_mod_static.py` (M6, M7, M11, M14 y M15).
- **Responde a la pregunta de producto de H-07:** la fila 1 de §3.4 compara ahora con `DSBX_Const.REST_STATE_4XX` (5, lo medido). Un 4xx devuelve el peer al hello sin esperar a `lease_ms`, y un 500 cae en «cualquier otro fallo».
- **El arnés vuelve al 409.** G4 a (`g4a_409`) y G5 b fuerzan el hello con un 409, el código del `hello_required` del backend (`app/backend/bridge.py:491`). Con el mod nuevo, un 500 ya no devuelve el peer al hello.
- **G7 no cambia:** sus casos `status*` son medidas. Lo que cambia es qué códigos de P vuelven a presentar el peer: ahora los cuatro 4xx, y ya no el 500.

**H-14, G6 encola tras un poll del servidor (partida diag sobre `1155973`), arbitraje del orquestador:**
- **Lo medido:** G1, G2, G3, G5, G7, G8 y G9 PASA, y G6 INCONCLUSO por «result_seen antes de T_s».
  - La orden de 1500 ms se encoló cuando el long-poll del servidor llevaba 1928 ms retenido: el poll anterior terminó en 94894014 y el apply fue en 94895942 (`proxy.jsonl`).
  - El plazo local cuenta desde el envío del poll (P-02, `DSBX_Peer.c:1116-1117`). Por eso la orden llegó vencida y el peer la rechazó (`rejected/expired`) 63 ms después, antes de la suspensión.
  - El evaluador acertó: sin la orden en curso, G6 no prueba la pausa.
- **No es del mod:** `HandleOrder` no cambió, y la regla es la conservadora de P-02. Con `hold_ms` = 2000 y `ttl_ms` = 1500, G6 cae así cuando el apply llega con el poll retenido más de ~1,4 s. Es un 30 % de las veces, según una estimación con polls de ~2,1 s. La partida v1.6 pasó porque el apply cayó antes.
- **El arnés cambia:** G6 espera a que termine un poll del servidor y encola entonces, con el siguiente poll recién salido (`_g6_wait_server_poll`, `G6_POLL_ALIGN_S` = 5 s). Las pruebas están en `test_f1bp_g56.py`. El evaluador y R12 no cambian.

**H-15, la procedencia del cliente retail (partida retail sobre `525da99`), arbitraje del orquestador:**
- **Lo medido:**
  - el lanzador no adoptó el cliente, así que G1 y G4 quedaron INCONCLUSO por «logs no finales»;
  - por R14, dejó el lease sin soltar.
- **La causa:** bajo BattlEye, el padre de `DayZ_x64` (62876) era un intermedio que ya había salido (PID 66172). La cadena de R16 se cortaba antes de llegar a `DayZ_BE.exe` (60528), que sí era propio.
- **La identidad sí se podía acreditar.** El cliente era el único `DayZ_x64`, creado 21 s después del lanzador propio. Escribía en el perfil propio `DayZ_x64_2026-11-15_17-38-40.RPT`, cuya segunda línea `== ` es la línea de órdenes exacta del lanzador: el `-mod` del PBO de `1155973`, `-port=2502`, el perfil y `-name=DSBXQA`.
  - El orquestador lo cerró por WM_CLOSE, con la guarda del instante de creación. El lanzador BattlEye salió solo, y se soltó el lease.
- **R16 cambia (EVIDENCIA):** además de la cadena, cuenta como procedencia el RPT del perfil propio con nuestra línea de órdenes, si su instante dista 10 s o menos de la creación del candidato. La ventana de adopción pasa de 60 a 120 s.
  - La función `RptPropio` del lanzador se probó sobre el RPT real: positivo, más ocho negativos y un caso sintético. Los negativos son otro puerto, un puerto prefijo, un mod con sufijo o recortado, un RPT anterior al lanzador, el RPT en otro perfil, `-profiles` con sufijo y una cabecera sin línea de órdenes.
