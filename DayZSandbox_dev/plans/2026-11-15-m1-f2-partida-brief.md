# Brief F2-partida (R25): escena viva en el mod núcleo y sus partidas (M1)

- **Versión:** v1.0, borrador para la ronda 1 de Sol. 2026-11-15, por el orquestador de F2.
- **Base:** `main` `cacec92`. Rama `claude/f2-partida`.
- **Contrato del que parte:** F2 sin juego, `plans/2026-11-14-m1-f2-offline-brief.md` v1.2.2 (sha256 `4b1664fe…fb852f`), en `main` por el #12. Aquí se citan solo sus deltas; lo que no se cambia sigue igual.
- **Plan:** v2, F2 (`plans/2026-10-26-m1-cine-v2.md:95-102`), y la aceptación A2-A4 (`:152-154`).
- **Entradas de diseño** (fuera del repo, en la carpeta de trabajo del orquestador):
  - `C:\tmp\dsbx-f2p-work\ref\entradas-diseno.md`: F1b-peers, S-persist, el arnés de F0.3 y los 15 huecos;
  - `hechos-enforce.md`: `JsonSerializer`, floats, hash, borrado y flags, con sus fuentes;
  - `censo-interfaz-f03.md`: el censo que pone F0.3.

## 0. Qué es y qué no

**Qué es.** F2 sin juego acreditó el contrato y el backend contra un mundo falso. Esta fase lo lleva a DayZ. Son cuatro tandas:

| Tanda | Qué | Depende de | Cuándo |
|---|---|---|---|
| **T1** | Contrato v1.3 del cable `dsbx1` (§3): enteros y columnas. Backend, mundo falso, mod falso y pruebas. **Sin DayZ.** | nada | ya |
| **T2** | Oráculo E9 de la partida (§6): evaluador, mutantes, pruebas y fixtures | este brief congelado y T1 en `main` | ya, tras congelar |
| **T3** | Mod núcleo en Enforce (§4): `scene.apply`, `scene.reset` y `scene.observe` sobre los peers de F1b-peers | F1b-peers en `main`, S-persist con su gate pasado, T2 congelado | después |
| **T4** | Runner de la partida (§5) y la partida: A2, A3 y A4 con censo independiente | T3, el censo de F0.3 en `main` | después |

**Qué no es:**
- **Actores** (F3): la escena es `fixtures/escena-sin-actores.json`, con 33 raíces (20 objetos, 10 infectados y 3 animales).
- **La web** (F6): la API HTTP no cambia (§3.8).
- **S-persist y S-perf:** este brief usa sus veredictos como parámetros, `[verify S-persist]` y `[verify S-perf]` (§4.4).
- **El censo:** lo pone F0.3 en su sonda (§5.3). Este brief no toca la sonda.

## 1. Entorno y fronteras

- **El repo:**
  - el worktree es `C:\tmp\dsbx-f2p`, linked al repo compartido `C:\tmp\dsbx-strack2\merge`;
  - todo git que escriba el árbol va con `-c core.autocrlf=false`; los ficheros, en UTF-8 sin BOM y con LF.
- **Python:**
  - `C:\Python314\python.exe`, solo con las dependencias que ya usan `app/` y `qa/`;
  - la suite se corre **sin `-X utf8`**: con él fallan dos pruebas de `test_server`, porque el hijo escribe en cp1252.
- **Ficheros de otras sesiones:**
  - **F1b-peers** (`DayZSandbox/scripts/3_Game/DSBX_*.c` y `5_Mission/DSBX_Mission.c`): solo los ganchos de §4.2, acordados con su sesión antes de tocarlos;
  - **la sonda QA de F0.3** (`DayZSandbox_dev/qa/probe/…`): no se toca;
  - **el arnés de F0.3** (`qa/f03_common.py`, `gate_core.py` y `m1_gate.py`): se usa, no se cambia, salvo que su sesión lo pida.
- **Partidas** (E6, `plans/2026-11-14-m1-f0.3-spikes-comun.md:135-145`):
  - OK fijo, con el lease de GPU (`gpu_lease.py adquirir`/`soltar`), sin ningún DayZ ajeno abierto y con `WM_CLOSE` solo a los PID propios;
  - el PBO se construye dentro del lease;
  - en la caja, F2 va detrás de F1b-peers y de S-persist.
- **Familias (E9 y reparto):**

  | Quién | Qué |
  |---|---|
  | Sol (OpenAI) | revisa el brief, el oráculo y el código |
  | DS4.1 (GX10) | T2, el oráculo |
  | Claude por `agy` (desde las 20:10) o Muse (desde la 01:00) | T1 y T3; ninguna de esas tandas puede ser DS4.1 ni OpenAI |
  | F0.3 (Claude) | el modo de censo (§5.3), que verifica el oráculo |

  En el GX10, como mucho 3 corridas largas en total; S-persist va primero.
- **El Experto de Enforce** revisa T3 antes del merge (§9.3). Las sesiones no tienen canal con él: el texto lo pasa Guillermo.

## 2. Decisiones de diseño

| # | Decisión | Por qué / fuente |
|---|---|---|
| DP-1 | **El cable `dsbx1` de F2 pasa a enteros y columnas** (contrato v1.3, §3): las filas del plan van en columnas homogéneas; las coordenadas, en milímetros enteros, y el `yaw`, en milésimas de grado, **en los dos sentidos**. La API HTTP no cambia: el backend convierte (§3.8). | `JsonSerializer` solo admite miembros tipados (vanilla `gameplay.c:77-100`), y un valor de otro tipo invalida el cuerpo (F1b-peers G7). No hay escritor de floats, y un float32 a x≈8192-16384 m tiene un paso de ≈1 mm (`hechos-enforce.md` §1-§2). |
| DP-2 | **Todas las claves de una orden van siempre**, con un valor neutro explícito: `if_pending` vacío y `caps.total = -1`. | El mod no distingue un campo ausente de un 0: un `ref` ausente llega instanciado y vacío. |
| DP-3 | **`registry_sha256` pasa a ser un resumen opaco de 64 hex** del JSON canónico del registro. En el mod son 8 `Hash()` salados, como `ModsetHash`; el mundo falso puede seguir usando SHA-256. El nombre del campo se queda, porque es de F1b-bridge. | Enforce no tiene SHA-256 (solo `string.Hash()`, de 32 bits), y el backend solo valida la forma (`app/backend/bridge.py:59`). Sirve para detectar cambios, no para verificar. |
| DP-4 | **El mod no recalcula `plan_sha256`:** lo guarda con la generación y lo devuelve. | Solo se compara como identidad (`scene_live.py:737`, `scene_plan.py:800`). El backend lo calcula sobre el plan v1.3 (`scene_plan.py:201`). |
| DP-5 | **D1 por la orden, con marca:** las órdenes F2 llevan `args.f2 = 1`, y las de F1 lo traen ausente, que llega como 0. Sin `scene: 1` en el hello, el backend manda F1 como hoy. | DP-2. Sustituye a la detección por `rows`/`plan_sha256` de `scene_live.is_f2_order` en el cable; dentro del backend, la marca `f2` de la orden ya existe. |
| DP-6 | **Confirmación del borrado (D5):** tras `Delete()`, la entidad cuenta como borrada cuando, en un tick posterior y en un máximo de `DEL_CONFIRM_TICKS`, `GetGame().GetObjectByNetworkId(low, high)` devuelve `null`. Si no, el registro se queda y la orden da `delete_failed` (F2b §3.3 paso 4). `[verify F2 en partida]` | Nadie lo ha medido (`hechos-enforce.md` §4). La partida registra por tick las tres señales (referencia, `IsPendingDeletion`/`IsSetForDeletion` y `GetObjectByNetworkId`), y el censo independiente juzga (§5.2, F2P-07). |
| DP-7 | **El mod escribe sus JSON a mano, solo con enteros y textos.** Nunca `WriteToString` sobre floats o bools. | `hechos-enforce.md` §2; es lo que ya hace F1b-peers (`DSBX_Wire.c`). |
| DP-8 | **`result_too_large` por verbo:** `scene.observe` da `rejected`; `scene.apply` y `scene.reset` siguen la regla de `GuardFailed`: `error` si hubo efecto y `rejected` si no. | F2b §3.5. Hoy F1b-peers da siempre `error` (`DSBX_Peer.c:1498-1506`). |
| DP-9 | **La lógica de escena va en ficheros nuevos** (`DSBX_Scene*.c`). En los de F1b-peers, solo ganchos (§4.2). | Igual que en F2 sin juego (F2b §4.6); así no hay choques con F1b-peers. |
| DP-10 | **Los flags, la vía de Q9 y la reaparición** son parámetros `[verify S-persist]` (§4.4). Se rellenan con el veredicto de S-persist (PER-01, 02, 06, 07, 08 y 09) y su commit. | S-persist decide (`plans/2026-11-14-m1-f0.3-s-persist-brief.md:124-128,162-164,301-309`). |
| DP-11 | **La partida carga dos mods,** `@DayZSandbox` y `@DayZSandbox_QA`, y habla con dos bridges: el backend real por `dsbx1` y `QABridge` por `qa0`, para el censo. | El censo es de la sonda de F0.3 (`censo-interfaz-f03.md`). |
| DP-12 | **El oráculo decide solo con lecturas independientes:** el censo y los estados de la API. Nunca con las lecturas del mod como prueba de lo que hay en el mundo. | E9 (`spikes-comun.md:221-235`). |
| DP-13 | **El gate comprueba el hash del oráculo** congelado. Si no coincide, sale INCONCLUSO `oracle_modified`. Lo implementa el runner de T4, porque hoy no existe en el arnés. | E9; `oracle_modified` no existe en ningún ref (`entradas-diseno.md`). |
| DP-14 | **Linter offline de Enforce antes de cualquier partida:** `dayz-script-validator`, gateando por `errors` y comparando contra la base. | Regla del proyecto: Enforce/config tocado → linter. |

## 3. Contrato v1.3 del cable (T1)

Es un delta sobre F2b §3. Solo cambia la **forma** de lo que viaja por `dsbx1`; la semántica de los verbos, los estados, los predicados (expresados en mm) y los códigos siguen igual.

### 3.1 Unidades
- **`x_mm`, `z_mm`, `y_mm` y `gy_mm`:** enteros, `round(metros × 1000)` con el `round` de Python (mitad al par). Así se calculan en el backend y en el mundo falso; el mod, con su vía de enteros (`hechos-enforce.md` §2).
- **`yaw_mdeg`:** entero en [0, 360000), `round(grados × 1000)` y normalizado después de redondear: un 359999,6 queda en 0.
- **`hp_milli`:** entero en [0, 1000].
- **Tolerancias** (D12): `EPS_Q` = 2 mm y `POS_TOL_M` = 500 mm.

### 3.2 `scene.apply`
`args`, **todas las claves siempre:**

```
{f2: 1, doc_id, rev, hash, plan_sha256,
 caps: {objeto, infectado, animal, total},     // total = -1 si la biblioteca no fija total
 classes: [str],                               // ordenadas, distintas, todas usadas
 lid: [str], ci: [int], x_mm: [int], z_mm: [int], yaw_mdeg: [int]}   // columnas de longitud N
```

- Las columnas tienen la misma longitud y van en el orden del documento. Si no, `rejected/bad_plan`.
- `plan_sha256` es el SHA-256 del JSON canónico (`sort_keys`, separadores `,` y `:`, UTF-8) de `{doc_id, rev, hash, classes, lid, ci, x_mm, z_mm, yaw_mdeg}`.

### 3.3 `scene.reset`
`args` `{f2: 1, doc_id, if_pending: {session, op_id}}`. Con `session == ""` y `op_id == ""` es un reset normal; si no, es una compensación (F2b D8).

### 3.4 `scene.observe`
`args` `{f2: 1, doc_id, at}`, con `at` `"checkpoint"` o `"now"`.

### 3.5 `state.read`
`args` `{f2: 1, doc_id}` con un peer con escena. Si no, `{}`, como hoy.

### 3.6 Filas de las lecturas (del mod al backend)
El mod las escribe a mano. Python las lee sin problema aunque mezclen tipos.

| Fila | Forma v1.3 |
|---|---|
| checkpoint | `[lid, ci, x_mm, y_mm, z_mm, yaw_mdeg, gy_mm]` |
| ahora | `[lid, x_mm, y_mm, z_mm, yaw_mdeg, hp_milli, n_own, n_foreign]`. Una raíz muerta lleva los cinco nulos y los contadores a 0 (M15) |

**Rangos:**
- `x_mm` y `z_mm`: [0, `world_size` × 1000], y como mucho 99 999 000 (cabe en `int` de 32 bits);
- `y_mm` y `gy_mm`: [-9 999 999, 9 999 999];
- los demás, como en F2b §3.6.

### 3.7 Envolvente
T1 la recalcula con un script, como `sizes5.py`, con los rangos v1.3 y 33-34 raíces. Hay que ajustar `compute_envelope`, `WIRE_CAP` 3500 y la tabla de F2b §3.6.
- **Criterio:** caben 33 raíces. Si 34 ya no caben, el tope baja a lo que quepa, y el backend da `plan_too_large`.

### 3.8 El backend y la API
- **La API HTTP no cambia.** `/api/observation` y `op.state` devuelven metros, como en v1.2.2: el backend convierte al recibir.
- **Cambian:**
  - `scene_plan.py`: el plan, la validación de lecturas y los predicados en mm;
  - `scene_live.py`: `is_f2_order` también por `args.f2` y la conversión de `obs`;
  - `bridge.py`: `state.read` con `f2: 1`;
  - `fake_world.py`: lee y escribe v1.3;
  - `fake_mod.py`: lo que haga falta;
  - las pruebas.
- **v1.2.2 se rechaza:** las filas `[lid, ci, x, z, yaw]` dan `bad_plan` en el mundo falso, y las lecturas con floats las rechaza el backend.

### 3.9 Aceptación de T1
1. La suite entera en verde, sin `-X utf8`, más el gate de F6-web §9 (`e2e_web`, `e2e_studio`), con rc 0.
2. Pruebas nuevas, cada una con su positiva y su negativa:
   - (a) metros → mm → metros sin perder más de `EPS_Q`, con valores en el límite del redondeo (x,5 mm) y en `world_size`;
   - (b) `yaw` de 359,9996° → 0;
   - (c) una orden sin alguna clave (DP-2) → el backend no la manda: lo afirma una prueba del constructor del plan;
   - (d) filas v1.2.2 → `bad_plan`;
   - (e) una lectura con floats → no reconcilia;
   - (f) la API devuelve metros: las pruebas de F6 siguen igual.
3. X4: la conversión con el factor mal (×100), el redondeo cambiado (`floor`), una columna desalineada y `total` ausente tratado como 0 son mutaciones que las pruebas matan.

## 4. Mod núcleo en Enforce (T3)

### 4.1 Ficheros nuevos, en `DayZSandbox/scripts/3_Game/`
- **`DSBX_Scene.c`:**
  - el estado por escena (`doc_id` → `gen_n`, la generación con `plan_sha256`, `pending`, `last`, `retained` y los registros);
  - el registro global del epoch: `(doc_id, lid)` → `{low, high, cls, parent_lid, gen_n}`;
  - el resumen opaco de DP-3.
- **`DSBX_SceneOps.c`:** la máquina por lotes de apply, reset, compensación y observe (F2b §3.3-§3.5). Un paso por tick a través de `AdvanceExecution`, con `SCENE_BATCH` efectos por paso como mucho.
- **`DSBX_SceneWire.c`:** escribe el bloque `scene` y las filas `obs` con enteros (DP-7), y la vía de enteros para mm y mdeg.

### 4.2 Ganchos en F1b-peers
Se acuerdan con su sesión antes de tocarlos. Las citas son del `525da99`.
1. **`DSBX_Messages.c:20-25`, `DSBX_Args`:** los campos v1.3 (`f2`, `plan_sha256`, `caps`, `classes`, `lid`, `ci`, `x_mm`, `z_mm`, `yaw_mdeg`, `if_pending` y `at`). Cada uno es un miembro tipado, y `caps` e `if_pending` son clases.
2. **`DSBX_Peer.c:1175-1200`, `StartOrderExecution`:** con `args.f2 == 1`, `scene.apply`, `scene.reset` y `scene.observe` van a `DSBX_SceneOps`; sin esa marca, todo sigue como hoy.
3. **`DSBX_Peer.c:1275-1296`, `AdvanceExecution`:** si la orden activa es F2, delega en `DSBX_SceneOps`, con el `EffectGuard` antes de cada efecto, como hoy.
4. **`DSBX_Wire.c:185-212`, `WorldReadJson`:** con `args.f2 == 1`, añade `scene` y usa la generación de esa escena. El `registry_n` y el resumen salen de `DSBX_Scene`.
5. **`DSBX_Wire.c:160-180`, `HelloBody`:** `"scene":1` en la rama `server`.
6. **`DSBX_Peer.c:1498-1506`, `result_too_large`:** por verbo, según DP-8.

### 4.3 Algoritmo (F2b §3.3-§3.5, con estos detalles de motor)
- **Crear:**
  - `CreateObjectEx(cls, Vector(x, SurfaceY(x, z), z), FLAGS)`, con `x = x_mm/1000.0`;
  - después, la orientación con `SetOrientation(Vector(yaw, 0, 0))`;
  - `gy = SurfaceY(x, z)`, guardada en mm;
  - si devuelve `null`, o la clase o la posición no cuadran, la creación ha fallado (F2b §3.3 paso 5);
  - el checkpoint se toma por la vía de Q9 que decida S-persist `[verify S-persist]`.
- **Retención:** es ajeno todo lo que hay en el inventario de una entidad borrable y que no está en el registro. Se recorre con `EnumerateInventory(PREORDER)`, como en S-persist §3.3.
- **Borrar:**
  - primero los hijos y después las raíces (M1);
  - `Delete()` y, después, la confirmación de DP-6;
  - antes de cada borrado, el lease, el plazo y la retención (F2b §3.3 paso 4).
- **Epoch:** antes de cada efecto y de cada escritura de estado, si el epoch cambió, se para sin escribir (M3).
- **`now`:** una fila por raíz registrada. Una raíz muerta da nulos y contadores a 0 (M15).

### 4.4 Constantes y parámetros

| Constante | Valor | Estado |
|---|---|---|
| `SCENE_BATCH` | 8 | `[verify S-perf]` |
| `DEL_CONFIRM_TICKS` | 10 | `[verify F2 en partida]`: lo mide F2P-07 |
| `FLAGS_ROOT` | 29361188 (= 1060 + 4194304 + 8388608 + 16777216) | `[verify S-persist]` PER-01, 07 y 08 |
| `FLAGS_CREATURE` | 29363236 (más `ECE_INITAI`), vía (a) de Q9 | `[verify S-persist]` PER-01 y 02 |
| `ECE_DYNAMIC_PERSISTENCY` | nunca | — |

Si S-persist decide otros valores, se cambia la constante y se anota su commit en §12.

## 5. Partida (T4)

### 5.1 Montaje
- **DayZ** (diag, después retail, como en F1b-peers) con `-mod=@DayZSandbox;@DayZSandbox_QA`.
- **El backend real** (`app/backend/server.py`) con el bridge en `127.0.0.1`, y como escena `fixtures/escena-sin-actores.json` copiada al directorio de la parte.
- **`PartContext` de F0.3** (`qa/f03_common.py:504-549`) para la sonda y el censo.
- **El lanzador** sigue el modelo de `qa/live/run_f1bp_partida.ps1` de F1b-peers: WMI, `-mod=`, `--min-vram-libre 4000` y el lease soltado cuando no queda ningún PID propio.

### 5.2 Partes
Cada parte es una carpeta con `samples/` y el manifest de F0.3.

| Parte | Qué | Fila |
|---|---|---|
| P1 | censo de referencia (`per_census_start`, §5.3) antes de nada | base |
| P2 | `POST /api/apply` → `observado`; censo; segunda entrega del mismo `op_id`, forzada por el runner → ni una entidad de más | A2 |
| P3 | se pone algo ajeno en el suelo y otro ajeno dentro del contenedor de `obj-17`; se siembra una segunda escena; `POST /api/reset` → `parcial/contenido_ajeno` con `obj-17` retenido; censo; segundo reset → otra vez `parcial` | A3 |
| P4 | reinicio **solo del backend** (mismo epoch) → apply → reconcilia, el reset borra la generación viva y el censo no tiene extras. Después, reinicio del **servidor** (epoch nuevo) → censo: nada de F2 reaparece; apply → 33 | A4 |
| P5 | reinicio del backend tras un efecto con la respuesta perdida: el runner corta al bridge a mitad del apply → reconcilia antes de aplicar, 33 y no 66 | A4 (-) |

- **Cómo se pone lo ajeno en P3:** con un verbo de la sonda que F0.3 indique (§11, pregunta 1). Este brief no lo inventa.
- **Lo que no se puede provocar en el juego** lo cubren los mutantes del oráculo sobre evidencia alterada (§6): una creación suprimida, una entidad movida 0,6 m y el ajeno sacado al suelo.

### 5.3 Censo independiente
`per_census_start` en el peer `server` de la sonda, con:
- `select_all_entityai_b = 1`;
- `center` (6170, 7643), `radius_m = 115` e `include_director_b = 0`;
- `area_tag = "f2p-<parte>"`.

Las filas traen clase, padre, `net_id` (`high:low`), pose, vida y `surface_y_m`.
- **Ciclo:** `issue_one` → `read_job_pages` → `job_free`.
- **Un censo a la vez.**
- **La identidad:**
  - lo creado en la sesión se reconoce por `net_id`;
  - lo que tenga `net_id` 0 (edificios del mapa, sin verificar) se reconoce por clase y pose redondeada.

### 5.4 Evidencia (`samples/`)
- **Del backend:** los eventos `op.state`, `GET /api/ops` y `GET /api/observation` (metros).
- **De la sonda:** las páginas del censo, tal cual.
- **Del mod,** en su log de script: las líneas `DSBX_SCENE_DEL` con las señales de borrado por tick (DP-6), y nada más.
- **Del manifest:** la identidad de F0.3 (commits, `pbo_sha256`) más `oracle_commit`.

## 6. Oráculo E9 (T2)
- **Ficheros:**
  - `qa/f2p_eval.py`;
  - `qa/f2p_mutants.py`;
  - `qa/tests/test_f2p_offline.py`;
  - `qa/fixtures/f2p_*.json`, con evidencia sintética de cada parte.
- **Contrato:** `evaluate(part_dir)` lee solo `samples/` y los campos del manifest de F0.3-0 §5.2. Sale 0 PASA, 1 FALLA y 2 INCONCLUSO (`gate_core.py:73-82`).
- **Comprobaciones:**

  | Id | Qué decide | Con qué |
  |---|---|---|
  | F2P-01 | A2: 33 raíces nuevas (diferencia con P1); el multiconjunto de clases es el del documento | censo |
  | F2P-02 | A2: cada objeto a menos de 0,5 m de `(x_doc, surface_y_m, z_doc)`. Las criaturas solo cuentan, vivas y como `ai_agent_b` | censo |
  | F2P-03 | A2 (-): la segunda entrega no deja ni una entidad de más | censo |
  | F2P-04 | A3: tras el reset, 0 propias vivas, salvo `obj-17` retenido; el ajeno, intacto en clase, pose y padre; la segunda escena, intacta; la op, `parcial/contenido_ajeno` | censo y API |
  | F2P-05 | A3: tras el reinicio del servidor, nada de F2 reaparece | censo |
  | F2P-06 | A4: tras el reinicio del backend, mismos conteos y posiciones, sin extras; 33 y no 66 en P5 | censo y API |
  | F2P-07 | DP-6: cada borrado que el mod da por confirmado falta en el censo siguiente; cada `delete_failed` sigue vivo. Informa del tick medido | log y censo |
  | F2P-08 | El modo de censo funciona: hay filas, están los edificios de referencia y `surface_y_m` varía con la posición | censo |

- **Negativas contra la fabricación,** obligatorias, que dan FALLA o INCONCLUSO y nunca PASA:
  - filas del censo copiadas de las lecturas del mod (mismos valores en mm en todas);
  - `net_id` `0:0` en lo creado;
  - `surface_y_m` constante;
  - un `op.state` sin su evento;
  - el sello de la sonda o el commit del oráculo que no coinciden;
  - las posiciones exactamente iguales a las del documento con `y` igual a `gy` en todas (sin ruido de float32).
- **Mutantes** (`f2p_mutants.py`), uno por cada caso:
  - creación suprimida;
  - entidad movida 0,6 m;
  - ajeno sacado al suelo;
  - contenedor ajeno borrado;
  - duplicado (66);
  - algo que reaparece tras el reinicio;
  - borrado «confirmado» que sigue vivo.

  Cada mutante tiene que tumbar su comprobación.
- **Revisión y congelado:** Sol, como mucho 2 rondas; después se congela (commit y sha). El gate de T4 comprueba esos bytes (DP-13).

## 7. Aceptación
- **T1:** §3.9.
- **T2:**
  - las pruebas offline del oráculo en verde;
  - cada mutante tumba su comprobación;
  - con la evidencia sintética de una partida buena, PASA.
- **T3:**
  - el linter offline con 0 errores nuevos frente a la base (DP-14);
  - la revisión de Sol;
  - la revisión del Experto de Enforce (§9.3).
- **T4:**
  - el oráculo congelado (DP-13);
  - P1-P5 en diag y después en retail, con `m1_gate`/`f2p_eval`: PASA en F2P-01 a F2P-08;
  - INCONCLUSO solo con su motivo escrito.

## 8. Ficheros y write-set por tanda
- **T1:**
  - `app/backend/scene_plan.py`, `scene_live.py`, `bridge.py` (solo `state.read`) y `server.py` (solo la conversión, si hace falta);
  - `app/tests/fake_world.py`, `fake_mod.py` y `test_*.py`;
  - este brief (§12).
- **T2:** `qa/f2p_eval.py`, `qa/f2p_mutants.py`, `qa/tests/test_f2p_offline.py` y `qa/fixtures/f2p_*.json`.
- **T3:** `DayZSandbox/scripts/3_Game/DSBX_Scene*.c` y los ganchos de §4.2.
- **T4:** `qa/f2p_run.py` (o `qa/live/run_f2p_partida.ps1` y un `.py`) y `evidence/m1/F2P/…`.

## 9. Entrega
### 9.1 Orden
1. Brief: Sol r1 → arreglos → Sol r2 → arbitraje → congelado.
2. T1 y T2 en paralelo. T2 se escribe contra el contrato v1.3 de §3 y la interfaz de censo; no espera a que T1 esté en `main`.
3. Sol sobre T1 → PR → merge. Sol sobre T2 → congelado.
4. T3 cuando F1b-peers esté en `main` y S-persist haya pasado su gate.
5. T4 con el censo de F0.3 en `main`.
6. La partida.

### 9.2 PR
- T1 va en su propio PR (`claude/f2-contrato-v13`). T2, T3 y T4, en el de esta rama.
- Las PR se mergean con merge commit, y el merge lo hace la sesión principal.

### 9.3 Texto para el Experto de Enforce (lo pasa Guillermo)
> Hola. Te paso para revisión el mod núcleo de DayZ Studio, fase F2 (escena viva): rama `claude/f2-partida`, ficheros `DayZSandbox/scripts/3_Game/DSBX_Scene*.c` más ganchos en `DSBX_Peer.c`, `DSBX_Wire.c` y `DSBX_Messages.c`. Hace `scene.apply` (crea entidades por lotes por tick con `CreateObjectEx` y los flags de S-persist), `scene.reset` (borra lo de la escena: primero los hijos y después las raíces; confirma cada borrado con `GetObjectByNetworkId`; retiene los contenedores con contenido ajeno) y `scene.observe`. Me interesa sobre todo:
> 1. `Delete()` y su confirmación;
> 2. `EnumerateInventory` para detectar lo ajeno;
> 3. lectura de JSON con `JsonSerializer` y escritura a mano solo con enteros;
> 4. que no se quede nada en la persistencia ni en el storage.
>
> El contrato está en `DayZSandbox_dev/plans/2026-11-15-m1-f2-partida-brief.md` §3-§4.

## 10. Riesgos y lo que no se ha medido
- **DP-6:** la confirmación del borrado no está medida. Si `GetObjectByNetworkId` tarda más de `DEL_CONFIRM_TICKS`, salen `delete_failed` falsos; los ve F2P-07 y se ajusta la constante con el dato.
- **El `net_id` de los edificios del mapa** puede ser 0: se identifican por clase y pose (§5.3).
- **Las filas del censo a 115 m:** F0.3 calcula unas cientos, sin medir; el tope es 4096.
- **TTL:** el plazo cuenta desde el envío del poll (F1b-peers). Un apply de 33 son unos 10 ticks `[verify S-perf]`.
- **Una orden a la vez en el mod:** las lecturas no se entregan durante un apply. Es coherente con el backend, porque la guarda «en vuelo» de C-01 sigue siendo válida.
- **`registry_sha256` opaco (DP-3):** no se puede verificar de forma independiente. Nadie lo consume.
- **El orden en la caja:** F2 va detrás de F1b-peers y de S-persist. Si S-persist cambia los flags o la vía de Q9, T3 cambia constantes y T2 no cambia.

## 11. Preguntas abiertas a otras sesiones
1. **F0.3:** ¿con qué verbo de la sonda se pone un objeto ajeno en el suelo y otro dentro del cargo de un contenedor de la escena (P3)? ¿Lo trae S-persist?
2. **F1b-peers:** ¿aceptáis los ganchos de §4.2? ¿Cambia algo de `StartOrderExecution`, `AdvanceExecution`, `WorldReadJson`, `HelloBody` o del camino de `result_too_large` después de `525da99`?

## 12. Registro de cambios
- v1.0 (2026-11-15): primer borrador.
