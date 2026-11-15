# Brief F2-partida (R25): escena viva en el mod núcleo y sus partidas (M1)

- **Versión:** v1.3.1, **congelada.** Es la ronda 2 de Sol (la última), el arbitraje del orquestador y la decisión de la principal sobre la sonda (§12). Las interfaces de F0.3 de §5.3 están confirmadas por escrito. 2026-11-15, por el orquestador de F2.
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
| **T2** | Oráculo E9 de la partida (§6): evaluador, mutantes, pruebas y fixtures | **solo** este brief congelado y las interfaces de F0.3 de §5.3 fijadas por escrito. Se escribe contra la spec de §3 y §5-§6, sin esperar a que T1 esté en `main` (P-12) | tras congelar |
| **T3** | Mod núcleo en Enforce (§4): `scene.apply`, `scene.reset` y `scene.observe` sobre los peers de F1b-peers | F1b-peers en `main`, S-persist con su gate pasado, T1 en `main`, T2 congelado | después |
| **T4** | Runner de la partida (§5) y la partida: A2, A3 y A4 con censo, testigo e independencia | T3, y las interfaces de F0.3 de §5.3 en `main` | después |

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
  | Claude por `agy` (desde las 20:10) o Muse (desde la 01:00) | T1, T3 y T4, que son implementación; ninguna de esas tandas puede ser DS4.1 ni OpenAI (P-12) |
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
| DP-6 | **Confirmación del borrado (D5):** tras `Delete()`, la entidad cuenta como borrada cuando, en un tick posterior y en un máximo de `DEL_CONFIRM_TICKS`, `GetGame().GetObjectByNetworkId(low, high)` devuelve `null`. Si no, el registro se queda y la orden da `delete_failed` (F2b §3.3 paso 4). `[verify F2 en partida]` | Nadie lo ha medido (`hechos-enforce.md` §4). La partida registra por tick las tres señales (referencia, `IsPendingDeletion`/`IsSetForDeletion` y `GetObjectByNetworkId`), y el censo independiente juzga (§5.4, F2P-10). |
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
`args` `{f2: 1, doc_id}` con un peer con escena; si no, `{}`, como hoy. La marca le sirve **solo al mod**, para añadir el bloque `scene`.

**En el backend, `state.read` nunca es una orden F2 (P-01):**
- su resultado sigue por el camino común de lecturas (`bridge.py`, `_handle_read_result_locked`), que pone `reconciled` y llama a `SceneLive.on_world_read_locked`;
- `is_f2_order` no mira `args.f2` en `state.read`; la marca solo cuenta para `scene.apply`, `scene.reset` y `scene.observe`.

Si `state.read` se clasificara como F2, su resultado iría a `SceneLive.on_result_locked`, la lectura no reconciliaría nunca y no se entregaría ni un apply.

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
  - `scene_live.py`: `is_f2_order` también por `args.f2`, pero **solo** en los verbos `scene.*` (§3.5), y la conversión de `obs`;
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
   - (f) la API devuelve metros: las pruebas de F6 siguen igual;
   - (g) regresión de P-01: con un peer con escena, el primer hello y un reinicio del backend reconcilian (`reconciled` en `True`) y el apply se entrega. Un `state.read` con `args.f2 = 1` clasificado como F2 tiene que tumbar la prueba.
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
  - **la creación ha fallado solo si** `CreateObjectEx` devuelve `null` (la entidad no aparece) o si `gy` sale de rango (F2b `:101`, `:111`). Entonces se compensa dentro de la orden (D8).
  - Una entidad que el motor deja desplazada **sí** se ha creado: el mod no juzga la posición. La desviación la caza el predicado del backend sobre el checkpoint, que da `fallido/lectura_no_cumple` (F2b A2; `test_f2_live.py`, `test_entidad_desplazada_06_fallido`), Q-07;
  - el checkpoint se toma por la vía de Q9 que decida S-persist `[verify S-persist]`.
- **Conjunto borrable y retención (F2b D5, P-02):**
  - el conjunto borrable de una operación son **solo** sus registros:
    - en un apply o un reset, los de esa escena en el epoch;
    - en una compensación, los de esa orden (`session`, `op_id`);
  - es **ajena** cualquier entidad que no esté en ese conjunto, **aunque esté en el registro global**. Por ejemplo, un objeto de la escena B metido en un contenedor de A es ajeno para el reset de A, y un registro de otra orden es ajeno para una compensación;
  - una entidad borrable con algo ajeno dentro (`EnumerateInventory(PREORDER)`, como en S-persist §3.3) se retiene, y se retienen con ella sus antepasados borrables;
  - el cálculo se rehace con el cerrojo antes de **cada** borrado (F2b §3.3 paso 4).
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
| `DEL_CONFIRM_TICKS` | 10 | `[verify F2 en partida]`: lo mide F2P-10 |
| `FLAGS_ROOT` | 29361188 (= 1060 + 4194304 + 8388608 + 16777216) | `[verify S-persist]` PER-01, 07 y 08 |
| `FLAGS_CREATURE` | 29363236 (más `ECE_INITAI`), vía (a) de Q9 | `[verify S-persist]` PER-01 y 02 |
| `ECE_DYNAMIC_PERSISTENCY` | nunca | — |

Si S-persist decide otros valores, se cambia la constante y se anota su commit en §12.

## 5. Partida (T4)

### 5.1 Montaje
- **DayZ** (diag, después retail, como en F1b-peers) con `-mod=@DayZSandbox;@DayZSandbox_QA`.
- **El backend real** (`app/backend/server.py`) con el bridge en `127.0.0.1`. La escena 1 es `fixtures/escena-sin-actores.json`, copiada al directorio de la parte. La escena 2 es una fixture nueva y pequeña, `fixtures/escena-f2p-2.json`: 3 objetos dentro del disco de censo, con otro `doc_id`.
- **`PartContext` de F0.3** (`qa/f03_common.py:504-549`) para la sonda: censo, testigo, ajenos y control persistente (§5.3).
- **El lanzador** sigue el modelo de `qa/live/run_f1bp_partida.ps1` de F1b-peers: WMI, `-mod=`, `--min-vram-libre 4000` y el lease soltado cuando no queda ningún PID propio.
- **Un solo mundo y un solo storage** para toda la partida. El orden de las partes es normativo, y cada una deja el estado que pide la siguiente (P-07).

### 5.2 Partes, en orden

| Parte | Qué hace el runner | Estado al terminar | Fila |
|---|---|---|---|
| P1 | censo de referencia; control persistente puesto (§5.3); **ventana de control** del testigo, en modo de radio y sin crear nada, para medir el ruido que quede | mundo sin nada de F2 | base |
| P2 | testigo activo → `POST /api/apply` → `observado`; segunda entrega forzada del mismo `(session, op_id)` dentro de la retención; censo | escena 1 aplicada (33) | A2 |
| P2n | **negativa real:** apply de una variante de la escena 1 con un estímulo que tiene que acabar en `parcial` o `fallido` (§5.5) | escena 1 limpia otra vez (reset) | A2 (-) |
| P3 | apply de la escena 1; reinicio del backend con la escena 2 → apply de la escena 2; reinicio con la escena 1; ajeno en el suelo y ajeno dentro de `obj-17` (§5.3); reset → `parcial/contenido_ajeno`; censo; segundo reset → igual | `obj-17` retenido | A3 |
| P3c | limpieza: la sonda borra sus ajenos (§5.3); reset de la escena 1 → `observado`; censo | escena 1 vacía; escena 2 aplicada | A3 |
| P4a | reinicio **solo del backend** (mismo epoch): apply de la escena 1 → reconcilia; el reset borra la generación viva; apply → 33; censo sin extras | escena 1 aplicada | A4 |
| P4b | reinicio del **servidor** sin reset (epoch nuevo, mismo storage): censo → nada de F2 reaparece y el control persistente sí; apply → 33 | escena 1 aplicada | A3, A4 |
| P4c | reset de la escena 1 y de la escena 2 → reinicio del servidor con reset previo: censo → nada de F2 reaparece y el control sí | sin F2 | A3 |
| P5 | apply cortado: el runner corta el bridge después de un efecto observado y antes del resultado, y reinicia el backend → lectura de reconciliación **antes** del apply nuevo → `33 + 0` | escena 1 aplicada | A4 (-) |

- **Lo que no se puede provocar en el juego** lo cubren además los mutantes del oráculo (§6): metatests del evaluador, que no sustituyen a P2n (P-04).
- **Hijos propios (P-09):** en M1 el producto solo crea raíces (sin actores, D3), así que no hay hijos propios que resetear en partida. Esa parte de A3 se acredita offline (F2b, filas F2-A3) y aquí queda **N/A con motivo**. F3 la lleva a partida con el equipo de los actores.

### 5.3 Sonda (interfaces de F0.3)
Todas van por el bridge de la sonda (`qa0`), así que quedan en la evidencia.
- **Censo:** `per_census_start`, con:
  - `select_all_entityai_b = 1` e `include_director_b = 1`, para los inventarios de jugador;
  - `radius_m = 120`, centrado en (6170, 7643), más un disco de 60 m por cada entidad seguida cuya última posición quede a menos de 15 m del borde de lo cubierto (P-05);
  - el resultado se deduplica por `net_id`.

  **La cobertura es parte de la evidencia:** si una entidad seguida falta de todos los discos y podía haber salido de lo cubierto (criatura, o a menos de 15 m del borde), la comprobación da **INCONCLUSO**, nunca «borrada».
- **Testigo de creación (P-03):** `per_witness_start`, que añade F0.3 (pendiente del OK de la principal, §11).
  - Es un trabajo `per_witness`, exclusivo, con páginas de 5 y hasta 4096 filas.
  - `nk`: `center_x_m`, `center_z_m`, `radius_m` (120) y `window_ms`, que cubre el apply con margen.
  - Columnas: `scol` `class_name`, `net_id` y `parent_net_id`; `ncol` `pos_x_m`, `pos_y_m`, `pos_z_m`, `yaw_deg`, `tick_ms`, `frame` y `ai_agent_b`. Hay una fila por cada `EntityAI` que pasa por `EEInit` dentro del radio.
  - Es la observación independiente de las 33 posiciones en el momento de crear, **criaturas incluidas**.
  - `[verify F2 en partida]`: que en `EEInit` la posición ya sea la final. Lo contrasta F2P-12.
  - **Trayectoria (Q-01), confirmada por F0.3:**
    - son filas con `sample_idx`: el 0 es `EEInit` y del 1 a `K` son los `K` ticks siguientes;
    - `witness_follow_ticks` = `K`, en [1, 5] y 3 por defecto;
    - `ncol` añade `sample_idx` y `alive_b`, y las filas cuentan para el tope de 4096;
    - un salto de más de `JUMP_MAX_M` = 0,3 m entre `EEInit` y el tick 1 delata un desplazamiento del mod antes del checkpoint. La IA no recorre eso en un tick de unos 33 ms.
  - **Modo de radio:** el oráculo usa el testigo y el censo en modo de radio. El modo mapa entero no entra en M1 (Q-02, §10).
- **Ruido de la CE:**
  - la partida corre con una copia de la misión con `db/globals.xml` en `ZombieMaxCount = 0` y `AnimalMaxCount = 0`, como recomienda F0.3;
  - el testigo solo se abre alrededor de cada operación;
  - `[verify F2 en partida]`: que esos `globals` corten la aparición de criaturas de la CE sin afectar a las que crea el producto por script, y cuánto loot se cuela. Lo mide la ventana de control de P1.
- **Ajenos:** `per_spawn_raw`.
  - En el suelo, `foreign_ground`.
  - En el cargo, `foreign_in_container` con `target_net_id`, el `net_id` del contenedor sacado del censo.
  - Hay que comprobar `obs_parent_net_id`.
- **Borrar ajenos (P-07):** `per_cleanup_qa`, que ya existe (brief de S-persist `:189`).
  - `sk cleanup_tag`, y una tabla de discos `scol ["area_tag"]`, `ncol ["center_x_m", "center_z_m", "radius_m"]`.
  - Solo borra lo creado por `per_spawn_raw`, identificado por `net_id`, `pers_id` o la marca de clase y `health_hp`.
  - Devuelve `cleaned_raw_n`, que tiene que ser igual al número de ajenos puestos. Después se repite el censo.
- **Control persistente (P-06):** `per_spawn_raw` con `mode = "persistent_control"`, que ya existe y es el mismo del PER-06 de S-persist.
  - Se crea sin `ECE_NOPERSISTENCY_WORLD`, con un hijo en el cargo.
  - Tras el reinicio se reconoce por clase y marca de `health_hp`, porque el `net_id` cambia.
  - **Tiene** que reaparecer, para demostrar que el storage se recargó. Si no, P4b y P4c dan INCONCLUSO.
  - Se pone en P1 y lo borra `per_cleanup_qa` al final.

### 5.4 Evidencia (`samples/`)
- **Del bridge del producto, la traza completa** (P-08, Q-04): las entregas por `(session, op_id)` con su `conn`, los resultados recibidos con su `dup`, los acuses y las lecturas de reconciliación con su orden temporal.
  - **La captura la hace el runner con un proxy HTTP** (`tap`) entre el mod y el puerto del bridge del backend. El mod apunta al `tap`, y el `tap` reenvía al backend.
  - El `tap` registra en `samples/bridge_tap.jsonl` los cuerpos crudos de cada petición y respuesta (`/hello`, `/poll`, `/result` con `dup` y `/catalog`), con marca de tiempo, **antes** de que el backend descarte duplicados.
  - El backend no cambia: no hay ganchos de observación.
- **Del backend:** los eventos `op.state`, `GET /api/ops` y `GET /api/observation` (metros).
- **De la sonda:** las respuestas crudas de `QABridge`, cada página del censo y del testigo con su trabajo, página, epoch, sello de sonda y marca de tiempo (P-10).
- **Del mod:** las líneas `DSBX_SCENE_DEL` de su log de script, con las señales de borrado por tick (DP-6).
- **Del manifest:**
  - la identidad de F0.3;
  - **los dos PBO por separado** (`product_pbo_sha256` y `probe_pbo_sha256`, P-11);
  - la ruta y el identificador del storage del servidor (P-06);
  - `oracle_commit`.

### 5.5 La negativa real de P2n (P-04)
Es un estímulo que el motor real hace fallar **antes del checkpoint**, sin inyectar fallos en el producto. Se prueba en este orden y vale el primero que funcione:
1. una clase que está en el catálogo del mundo pero que `CreateObjectEx` no puede instanciar (devuelve `null`):
   - colocada después de otras filas, la creación falla (`create_failed`), se compensa dentro de la orden y la op queda **`parcial/compensada`**;
   - en la primera fila, sin efecto previo: `rejected/create_failed` → **`fallido/create_failed`** (M12);
2. una entidad colocada donde el motor la desplaza 0,5 m o más al crearla, por ejemplo solapada con un edificio estático → se crea, el checkpoint no cumple y la op queda **`fallido/lectura_no_cumple`** (Q-07).

F2P-03 comprueba el estado **y el motivo** que corresponden a la variante usada.

`[verify F2 en partida]`. Si ninguno de los dos falla en el motor real, la comprobación F2P-03 da **INCONCLUSO con su motivo**, nunca PASA. Las dos variantes se preparan como fixtures separadas: `fixtures/escena-f2p-neg-*.json`.

### 5.6 Storage (P-09)
- **Comprobación estática**, en el gate de T3: el mod del producto **entero** (`DayZSandbox/scripts/**`), en su diff frente a la base, no añade ningún uso de las API de persistencia (`OnStoreSave`, `OnStoreLoad` y las de la CE de storage). Hay una lista de búsqueda en el gate. Así entra cualquier gancho de los ficheros de F1b-peers, no solo `DSBX_Scene*.c` (P-09).
- **En partida:** P4b y P4c, con el control persistente reaparecido y nada de F2 reaparecido.

## 6. Oráculo E9 (T2)
- **Ficheros:**
  - `qa/f2p_eval.py`;
  - `qa/f2p_mutants.py`;
  - `qa/tests/test_f2p_offline.py`;
  - `qa/fixtures/f2p_*.json`, con evidencia sintética de cada parte.
- **Contrato:** `evaluate(part_dir)` lee solo `samples/` y los campos del manifest de F0.3-0 §5.2, más los de §5.4. Sale 0 PASA, 1 FALLA y 2 INCONCLUSO (`gate_core.py:73-82`).
- **Independencia (DP-12, P-10):** cada fila del mundo sale de una respuesta cruda de la sonda, identificada por trabajo, página, epoch, sello y frescura (tomada después del efecto que juzga). El oráculo **no** mira si los valores tienen ruido.
- **Comprobaciones:**

  | Id | Qué decide | Con qué |
  |---|---|---|
  | F2P-01 | A2: el testigo ve 33 creaciones nuevas en P2, con el multiconjunto de clases del documento, y el censo posterior las tiene (diferencia con P1 por `net_id`) | testigo y censo |
  | F2P-02 | A2: **cada una de las 33** nace a menos de 0,5 m de `(x_doc, surface_y, z_doc)` según el testigo.<br>**Criaturas (Q-01):** de `EEInit` al tick 1 no saltan más de `JUMP_MAX_M`, y el checkpoint que declara el mod está a menos de `JUMP_MAX_M` de la posición del tick 1; sin trayectoria, INCONCLUSO.<br>**Objetos:** siguen a menos de 0,5 m en el censo.<br>**Q-05:** en el censo posterior las 13 criaturas tienen `alive_b = 1` y `ai_agent_b = 1`. Con la vía (b) de Q9, el censo se toma después del plazo de `InitAIAgent` `[verify S-persist]` | testigo y censo |
  | F2P-03 | A2 (-), en P2n: el estímulo ocurrió (testigo o traza), la op quedó `parcial` o `fallida`, y el censo lo confirma | traza, API y censo |
  | F2P-04 | A2: en P2 hay **dos entregas** del mismo `(session, op_id)` y la segunda respuesta lleva `dup: true`, y no aparece ninguna entidad de más | traza y censo |
  | F2P-05 | A3, en P3: tras el reset, las propias retenidas son solo los contenedores con algo ajeno; los ajenos, intactos en clase, pose y padre.<br>**Q-06:** las **tres** entidades de la escena 2, intactas antes y después, en identidad (`net_id`), clase, pose e inventario.<br>La op, `parcial/contenido_ajeno`; el segundo reset, igual | censo y API |
  | F2P-06 | A3, en P3c: tras la limpieza, 0 propias vivas de la escena 1, y las tres de la escena 2 intactas (Q-06) | censo |
  | F2P-07 | A3, en P4b y P4c: nada de F2 reaparece, con reset y sin él, **y el control persistente reaparece**; si el control no reaparece, INCONCLUSO | censo y manifest |
  | F2P-08 | A4, en P4a: tras el reinicio del backend, reconciliación antes del apply; mismos conteos y posiciones; sin extras | traza y censo |
  | F2P-09 | A4 (-), en P5: hubo efecto antes del corte (K > 0 según el testigo), no llegó la respuesta, la lectura de reconciliación va antes del apply nuevo, y el total es 33, no `33 + K` | traza, testigo y censo |
  | F2P-10 | DP-6: cada borrado que el mod da por confirmado falta en el censo siguiente, dentro de lo cubierto; cada `delete_failed` sigue vivo. Informa del tick medido | log, censo y cobertura |
  | F2P-11 | El modo de censo y el testigo funcionan: hay filas, están los edificios de referencia de P1 (por clase y pose) y `surface_y_m` varía con la posición | censo y testigo |
  | F2P-12 | El testigo es fiable: en los **objetos** de P2, que no se mueven, su posición coincide con la del censo posterior a menos de 0,05 m `[verify F2 en partida]`. Si no, F2P-02 da INCONCLUSO para las criaturas, porque la posición de `EEInit` no sería la final | testigo y censo |
  | F2P-13 | **Sin extras dentro de la cobertura:** durante las ventanas de operación, el testigo en modo de radio no ve nacer ninguna entidad de las clases de la escena que no case con una fila esperada (clase y posición a menos de 0,5 m).<br>Un objeto de más → FALLA.<br>Una criatura de más → FALLA si la ventana de control de P1 no tuvo criaturas, e INCONCLUSO si las tuvo.<br>**Alcance:** lo que nazca fuera de la cobertura no se ve en M1 (Q-02, §10) | testigo |

- **Negativas contra la fabricación,** obligatorias, que dan FALLA o INCONCLUSO y nunca PASA:
  - filas sin respuesta cruda de la sonda que las respalde, o con trabajo, página, epoch o sello que no casan, o tomadas antes del efecto (frescura);
  - `net_id` `0:0` en lo creado;
  - `surface_y_m` constante;
  - un `op.state` sin su evento;
  - una traza de entregas que no cuadra con las respuestas;
  - el commit del oráculo o los sellos de los PBO que no coinciden.
- **Mutantes** (`f2p_mutants.py`). Cada uno tiene que tumbar su comprobación:
  - creación suprimida;
  - entidad movida 0,6 m, en el testigo y en el censo;
  - criatura que nace a 1 m;
  - ajeno sacado al suelo;
  - contenedor ajeno borrado;
  - objeto de la escena 2 borrado;
  - duplicado (`33 + K`);
  - algo que reaparece tras el reinicio;
  - control persistente ausente;
  - criatura desplazada por el mod entre `EEInit` y el checkpoint, con un salto mayor que `JUMP_MAX_M` en el tick 1 y un checkpoint inventado en su sitio (Q-01);
  - criatura con `alive_b = 0` o `ai_agent_b = 0` en el censo posterior (Q-05);
  - una de las entidades de la escena 2 que están en el suelo, borrada por el reset (Q-06);
  - un extra de una clase de la escena nacido dentro de la cobertura, en un sitio que no es del documento (F2P-13);
  - borrado «confirmado» que sigue vivo;
  - **copia de las lecturas del mod con una perturbación por debajo de la tolerancia** (P-10);
  - una sola entrega en P2;
  - corte antes del primer efecto en P5;
  - testigo cuya posición en `EEInit` no es la final: los objetos estáticos discrepan del censo y F2P-12 da INCONCLUSO, no PASA.
- **Revisión y congelado:** Sol, como mucho 2 rondas; después se congela (commit y sha).
- **Gate y CLI (DP-13, P-11):** la forma que propone F0.3 para su núcleo (§11):
  - **`F2P` en `SPIKE_REGISTRY`** (`qa/gate_core.py:14`), con `qa/f2p_run.py`, `qa/f2p_eval.py` y `qa/f2p_mutants.py`. Hereda el despacho, las partes, `--evaluate-only` y la agregación;
  - **`m1_gate.py spike F2P --oracle-commit <sha>`:** antes de correr o evaluar nada, compara byte a byte los ficheros del oráculo frente al commit congelado. Si no coinciden, INCONCLUSO `oracle_modified` y sale 2, también con `--evaluate-only`;
  - **`--product-pbo <ruta>`,** junto al `--pbo` de la sonda. En el manifest van `identity.pbo_sha256` (sonda) e `identity.product_pbo_sha256` (producto);
  - la única vía de aceptación es esa entrada con `--oracle-commit`: un `f2p_eval` suelto no cuenta.

  Es un PR de núcleo de F0.3, con su Sol. Quién lo hace lo decide la principal.

## 7. Aceptación
- **T1:** §3.9.
- **T2:**
  - las pruebas offline del oráculo en verde;
  - cada mutante tumba su comprobación;
  - con la evidencia sintética de una partida buena, PASA.
- **T3:**
  - el linter offline con 0 errores nuevos frente a la base (DP-14);
  - la comprobación estática de storage de §5.6;
  - la revisión de Sol;
  - la revisión del Experto de Enforce (§9.3).
- **T4:**
  - el oráculo congelado, comprobado antes de evaluar (DP-13);
  - P1 a P5, en el orden de §5.2, en diag y después en retail, por la entrada del gate de §6: PASA en F2P-01 a F2P-13;
  - INCONCLUSO solo con su motivo escrito: cobertura, control persistente o el estímulo de P2n.
  - La parte de A3 de los hijos propios es N/A con motivo en M1 (§5.2).

## 8. Ficheros y write-set por tanda
- **T1:**
  - `app/backend/scene_plan.py`, `scene_live.py`, `bridge.py` (solo `state.read`) y `server.py` (solo la conversión, si hace falta);
  - `app/tests/fake_world.py`, `fake_mod.py` y `test_*.py`;
  - este brief (§12).
- **T2:** `qa/f2p_eval.py`, `qa/f2p_mutants.py`, `qa/tests/test_f2p_offline.py` y `qa/fixtures/f2p_*.json`.
- **T3:** `DayZSandbox/scripts/3_Game/DSBX_Scene*.c` y los ganchos de §4.2.
- **T4:**
  - `qa/f2p_run.py` (o `qa/live/run_f2p_partida.ps1` y un `.py`);
  - las fixtures `fixtures/escena-f2p-2.json` y `fixtures/escena-f2p-neg-*.json`;
  - `evidence/m1/F2P/…`;
  - el registro en el gate, con la forma que fije F0.3 (§11);
  - el proxy `tap` del bridge (§5.4), dentro del runner.

## 9. Entrega
### 9.1 Orden
1. Brief: Sol r1 → arreglos → Sol r2 → arbitraje → congelado.
2. T1 y T2 en paralelo, con la única dependencia normativa de la tabla de §0. T2 arranca cuando F0.3 fije por escrito las interfaces de §5.3 que siguen pendientes.
3. Sol sobre T1 → PR → merge. Sol sobre T2 → congelado.
4. T3 cuando F1b-peers esté en `main`, S-persist haya pasado su gate y T1 esté en `main`.
5. T4 con las interfaces de F0.3 en `main`.
6. La partida.

### 9.2 PR
- T1 va en su propio PR (`claude/f2-contrato-v13`). T2, T3 y T4, en el de esta rama.
- Las PR se mergean con merge commit, y el merge lo hace la sesión principal.

### 9.3 Texto para el Experto de Enforce (lo pasa Guillermo)
> Hola. Te paso para revisión el mod núcleo de DayZ Studio, fase F2 (escena viva): rama `claude/f2-partida`, ficheros `DayZSandbox/scripts/3_Game/DSBX_Scene*.c` más ganchos en `DSBX_Peer.c`, `DSBX_Wire.c` y `DSBX_Messages.c`. Hace `scene.apply` (crea entidades por lotes por tick con `CreateObjectEx` y los flags de S-persist), `scene.reset` (borra solo los registros de la escena: primero los hijos y después las raíces; confirma cada borrado con `GetObjectByNetworkId`; retiene los contenedores con algo fuera de lo borrable dentro, también objetos de otra escena) y `scene.observe`. Me interesa sobre todo:
> 1. `Delete()` y su confirmación;
> 2. `EnumerateInventory` para detectar lo ajeno;
> 3. lectura de JSON con `JsonSerializer` y escritura a mano solo con enteros;
> 4. que no se quede nada en la persistencia ni en el storage.
>
> El contrato está en `DayZSandbox_dev/plans/2026-11-15-m1-f2-partida-brief.md` §3-§4.

## 10. Riesgos y lo que no se ha medido
- **DP-6:** la confirmación del borrado no está medida. Si `GetObjectByNetworkId` tarda más de `DEL_CONFIRM_TICKS`, salen `delete_failed` falsos; los ve F2P-10 y se ajusta la constante con el dato.
- **El `net_id` de los edificios del mapa** puede ser 0: se identifican por clase y pose (§5.3).
- **Las filas del censo a 120 m más los discos extra:** F0.3 calcula unas cientos, sin medir; el tope es 4096 por trabajo.
- **Cobertura (P-05):** las criaturas que se alejan pueden dejar la comprobación en INCONCLUSO. Es lo honesto; los discos extra lo reducen.
- **P2n (P-04):** puede que ningún estímulo natural haga fallar al motor. Entonces la negativa del producto queda INCONCLUSA y se queda con los mutantes y con lo acreditado offline (F2b F2-A2).
- **El testigo de creación (P-03) y el control persistente (P-06)** dependen de F0.3. Sin ellos, T2 no se congela y P4b/P4c dan INCONCLUSO.
- **Limitación conocida (Q-02), para después de M1:** «sin extras» se acredita **dentro de la cobertura** del censo y del testigo, en modo de radio. Un huérfano nacido fuera de esa cobertura no se ve en M1. El testigo de mapa entero quedó fuera por decisión de la principal: era MAY, no BLOQ, y cada pieza de Enforce en la sonda cuesta una ronda de Sol, partida y riesgo.
- **Limitación conocida (Q-03), para después de M1:** en partida no se mete un objeto **registrado** de la escena 2 dentro de un contenedor de la escena 1, porque haría falta un traslado por `net_id` (`per_transfer`) que no entra en M1. Esa propiedad (P-02: lo ajeno es lo que está fuera del conjunto borrable de la operación) se acredita offline (F2b F2-A3 e), y en el código Enforce la cubren la revisión de Sol y la del Experto (§9.3). En partida se cubren el ajeno no registrado dentro de `obj-17` y las tres entidades de la escena 2 en el suelo.
- **`globals` a 0:** no está medido si `ZombieMaxCount = 0` o `AnimalMaxCount = 0` afectan a las criaturas que crea el producto por script. Si F2P-02 encuentra criaturas muertas o sin IA solo con esos `globals`, se repite P2 con los `globals` originales y se anota.
- **TTL:** el plazo cuenta desde el envío del poll (F1b-peers). Un apply de 33 son unos 10 ticks `[verify S-perf]`.
- **Una orden a la vez en el mod:** las lecturas no se entregan durante un apply. Es coherente con el backend, porque la guarda «en vuelo» de C-01 sigue siendo válida.
- **`registry_sha256` opaco (DP-3):** no se puede verificar de forma independiente. Nadie lo consume.
- **El orden en la caja:** F2 va detrás de F1b-peers y de S-persist. Si S-persist cambia los flags o la vía de Q9, T3 cambia constantes y T2 no cambia.

## 11. Preguntas abiertas a otras sesiones
1. **F0.3, ajenos:** **resuelto.** `per_spawn_raw`, en modo `foreign_ground` y `foreign_in_container` con `target_net_id`, lo añade F0.3 en el commit del modo de censo (`censo-interfaz-f03.md`).
2. **F0.3, respondido el 15-nov tras Sol r1:**
   - (b) **resuelto:** `per_cleanup_qa`, que ya existe;
   - (c) **resuelto:** `per_spawn_raw` en modo `persistent_control`, que ya existe;
   - (a) testigo `per_witness_start` y (d) registro `F2P` con `--oracle-commit` y `--product-pbo`: **aprobados por la principal.**
     - Van en el PR aparte de F0.3, «sonda: extensiones para F2», que lleva también el modo de censo y `target_net_id`; el núcleo del gate va en otro PR.
     - Los dos los escribe F0.3 (Claude), con Sol.
     - El testigo lleva `super.EEInit()` primero, está apagado por defecto (con un bool estático), tiene tope de filas por ventana (`failed/rows_cap`), `sk witness_tag` y una partida diag corta con el testigo encendido y apagado.

   **Tras Sol r2** (confirmado por F0.3 por escrito y recortado por la principal):
   - **(e)** trayectoria del testigo, con `witness_follow_ticks` entre 1 y 5 y 3 por defecto: **entra** en el PR de F0.3 (Q-01, que era BLOQ);
   - **(f)** testigo en modo mapa entero (Q-02) y **(g)** `per_transfer` (Q-03): **no entran en M1**. Eran MAY, y quedan como limitación conocida (§10);
   - **ruido de la CE:** copia de la misión con `ZombieMaxCount = 0` y `AnimalMaxCount = 0`, más la ventana de control de P1, como recomienda F0.3.

   El oráculo (T2) se escribe ya contra estas interfaces. La partida (T4) espera a que estén en `main`.
3. **F1b-peers:** está en el PR #19 (`02fb06e`), con el mod idéntico a `525da99` (`git diff` vacío, comprobado el 15-nov). Los ganchos de §4.2 se ponen en T3, cuando F1b-peers ya esté en `main`, así que no hay edición concurrente.

## 12. Registro de cambios
- v1.0 (2026-11-15): primer borrador.
- v1.1 (2026-11-15): ronda 1 de Sol (UNSOUND, con 3 BLOQ, 8 MAY y 1 MEN), todo aplicado:

  | Hallazgo | Arreglo |
  |---|---|
  | P-01 | `state.read` nunca es una orden F2 en el backend (§3.5); regresión (§3.9 g) |
  | P-02 | lo ajeno es lo que está fuera del conjunto borrable de la operación, aunque esté en el registro global (§4.3) |
  | P-03 | testigo de creación de la sonda para las 33 raíces, criaturas incluidas (§5.3, F2P-01 y F2P-02) |
  | P-04 | negativa real P2n antes del checkpoint (§5.5, F2P-03) |
  | P-05 | cobertura con disco de 120 m más discos por entidad, e INCONCLUSO si falta cobertura (§5.3) |
  | P-06 | control persistente y mismo storage; P4b sin reset y P4c con reset (§5.2, F2P-07) |
  | P-07 | ciclo de vida normativo entre partes y limpieza P3c (§5.2) |
  | P-08 | traza completa de entregas y respuestas (§5.4); F2P-04 y F2P-09 acreditan el estímulo; el duplicado es `33 + K` |
  | P-09 | hijos propios N/A con motivo en M1; storage con comprobación estática más P4b/P4c (§5.2, §5.6) |
  | P-10 | independencia por la captura cruda de la sonda; mutante «copia con perturbación» (§6) |
  | P-11 | entrada de gate con comprobación previa de bytes y los dos PBO; la forma la fija F0.3 (§6, §11) |
  | P-12 | una sola dependencia normativa para T2; T4 lo hace una familia de implementación (§0, §1) |
- v1.2 (2026-11-15): las interfaces de F0.3 en §5.3, §6 y §11:
  - el testigo `per_witness_start`, con F2P-12 contrastando testigo y censo;
  - `per_cleanup_qa`;
  - el control persistente `persistent_control`;
  - `F2P` en `SPIKE_REGISTRY`, con `--oracle-commit` y `--product-pbo`.
- v1.3 (2026-11-15): **congelada.** Ronda 2 de Sol (la última; UNSOUND, con 7 cerrados y 5 parciales, Q-01 BLOQ, Q-02 a Q-06 MAY y Q-07 MEN), arbitrada por el orquestador y aplicada entera:

  | Hallazgo | Arreglo |
  |---|---|
  | Q-01 (cierra P-03) | trayectoria del testigo y `JUMP_MAX_M`; comprobación del checkpoint de criaturas contra el tick 1; sin trayectoria, INCONCLUSO; mutante de salto (§5.3, F2P-02) |
  | Q-02 (cierra P-05) | testigo en modo mapa entero y F2P-13; INCONCLUSO para criaturas si la CE está activa |
  | Q-03 (cierra P-07) | `per_transfer` por `net_id` para la entidad de la escena 2 (P3, P3c) |
  | Q-04 (cierra P-08) | proxy `tap` en el runner, con los cuerpos crudos antes de deduplicar; el backend no cambia (§5.4) |
  | Q-05 | criaturas con `alive_b = 1` y `ai_agent_b = 1` en el censo posterior, más sus mutantes (F2P-02) |
  | Q-06 | las tres entidades de la escena 2 intactas en identidad, clase, pose e inventario (F2P-05, F2P-06) |
  | Q-07 | una creación fallida es solo `null` o `gy` fuera de rango; el desplazamiento lo decide el predicado (`fallido/lectura_no_cumple`); P2n espera el motivo de su variante (§4.3, §5.5) |
  | P-09 (parcial) | la comprobación estática de storage cubre todo `DayZSandbox/scripts/**` (§5.6) |

  Lo que depende de F0.3 queda como requisito de interfaz (§11.2), con la regla de INCONCLUSO si falta.
- v1.3.1 (2026-11-15): **arbitraje tras el congelado, por la decisión de la sesión principal sobre la sonda.** Sustituye lo de la v1.3 para Q-02 y Q-03:
  - **Q-01:** la trayectoria se queda, confirmada por F0.3: filas `sample_idx`, K en [1, 5] y 3 por defecto, más `alive_b` (§5.3).
  - **Q-02** (era MAY): fuera el modo mapa entero. F2P-13 queda en «sin extras dentro de la cobertura», en modo de radio, y lo de fuera es limitación conocida para después de M1 (§10).
  - **Q-03** (era MAY): fuera `per_transfer` y el estímulo «objeto registrado de la escena 2 dentro de un contenedor de la escena 1». P-02 se acredita offline (F2b F2-A3 e) y con la revisión de código; queda como limitación conocida para después de M1 (§10).
  - **El ruido de la CE:** `globals` a 0 y ventana de control en P1 (§5.2, §5.3). F2P-13 la usa para decidir entre FALLA e INCONCLUSO en las criaturas.

  Nada de §3 (el contrato v1.3, T1) cambia.
