# Brief F2-partida (R25): escena viva en el mod núcleo y sus partidas (M1)

- **Versión:** v1.3.4, **congelada.** Es la ronda 2 de Sol (la última), el arbitraje del orquestador y la decisión de la principal sobre la sonda. Añade la medida de la envolvente v1.3, la alineación con el contrato del testigo tras la diag de F0.3 y con el núcleo del gate, y la semántica exacta del oráculo tras Sol r1 sobre él (§6.1, §12). Las interfaces de F0.3 de §5.3 están confirmadas por escrito y medidas en su diag. 2026-11-16, por el orquestador de F2.
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
- **Medida v1.3** (U-01): sustituye para v1.3 a la tabla de F2b §3.6, que es la de v1.2.2. Es la escena máxima de M1 (20/10/3), con `lid` de 10 caracteres y las clases más largas.

  | Cuerpo | v1.2.2 (F2b §3.6) | **v1.3** |
  |---|---|---|
  | `/poll` con un `scene.apply` | 2722 B | **1985 B** |
  | resultado de `scene.apply` con su checkpoint | 2968 B | **2934 B** |
  | resultado de `scene.observe` `now` | 3362 B | **3198 B** |
  | resultado de `scene.reset` o `state.read` | 925 B | **926 B** |

  El máximo es 3198 B, por debajo de `WIRE_CAP` 3500. Las pruebas de la envolvente acreditan que caben 34 raíces y que 40 dan `plan_too_large`.

  Se reproduce desde `DayZSandbox_dev` con:

  ```
  C:\Python314\python.exe -B -c "from app.tests.test_scene_plan import _max_doc, TestEnvelope; print(TestEnvelope()._env(*_max_doc(20,10,3,3)))"
  ```

  Medido el 2026-11-15 sobre `6a9b29a`.

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
- **Checkout en LF** (`git -c core.autocrlf=false`). El núcleo compara byte a byte los ficheros del oráculo con el commit congelado, sin normalizar los finales de línea, y el repo no tiene `.gitattributes`. Un checkout en CRLF da INCONCLUSO `oracle_modified` (H-5).
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
  - el resultado se deduplica por `net_id`;
  - medido en la diag de F0.3: `max_hp = health_hp = -1` significa «sin sistema de daño», y los edificios del mapa **sí** tienen `net_id` real, con la parte alta negativa (`-2147225600:847447385`). El `net_id` se lee como `high:low` con signo.

  **La cobertura es parte de la evidencia:** si una entidad seguida falta de todos los discos y podía haber salido de lo cubierto (criatura, o a menos de 15 m del borde), la comprobación da **INCONCLUSO**, nunca «borrada».
- **Testigo de creación (P-03):** `per_witness_start`, que añade F0.3 (pendiente del OK de la principal, §11).
  - Es un trabajo `per_witness`, exclusivo, con páginas de 5 y hasta 4096 filas.
  - `nk`: `center_x_m`, `center_z_m`, `radius_m` (120) y `window_ms`, que cubre el apply con margen.
  - Columnas: `scol` `class_name`, `net_id` y `parent_net_id`; `ncol` `pos_x_m`, `pos_y_m`, `pos_z_m`, `yaw_deg`, `tick_ms`, `frame` y `ai_agent_b`.
  - Hay una fila por cada entidad que pasa por `EEInit` dentro del radio **y deriva de una raíz enganchada:** `ItemBase`, `ZombieBase`, `AnimalBase`, `CarScript` o `BuildingBase`, más 4 clases vanilla que no llaman a `super.EEInit()`. `EntityAI` es una clase del motor y no se puede modar (PR #22).
  - Las dos escenas quedan cubiertas. Lo que no deriva de esas raíces no se ve (§10).
  - Es la observación independiente de las 33 posiciones en el momento de crear, **criaturas incluidas**.
  - **Medido en la diag de F0.3:** en lo que crea la sonda con `PLACE_ON_SURFACE`, la posición de `EEInit` es la final, con 1 cm como mucho. En lo que crea el producto lo sigue contrastando F2P-12 `[verify F2 en partida]`.
  - **Trayectoria (Q-01), confirmada por F0.3:**
    - son filas con `sample_idx`: el 0 es `EEInit` y del 1 a `K` son los `K` ticks siguientes;
    - `witness_follow_ticks` = `K`, en [1, 5] y 3 por defecto;
    - `ncol` añade `sample_idx` y `alive_b`, y las filas cuentan para el tope de 4096;
    - un salto de más de `JUMP_MAX_M` = 0,3 m entre `EEInit` y el tick 1 delata un desplazamiento del mod antes del checkpoint. La IA no recorre eso en un tick de unos 33 ms.
  - **La muestra 0, tras la diag de F0.3** (PR #22, `DSBX_QA_X_Persist.c:1987-2036`):
    - lleva la posición, la orientación, `tick_ms`, `frame` y `ai_agent_b` de `EEInit`;
    - lleva el `net_id` y el `parent_net_id` del primer tick, porque en `EEInit` todavía no existen. Es el mismo `net_id` que el de las muestras de la 1 a la K;
    - si en ese tick la entidad ya no existe, sale `0:0` con `alive_b = 0`;
    - **su `ai_agent_b` no sirve para decidir si algo es una criatura.** Que la IA ya exista en `EEInit` al crear con `ECE_INITAI` no está medido. Las muestras de la 1 a la K sí lo releen en cada tick (H-4);
    - en P2, la partida anota para cada criatura el `ai_agent_b` de la muestra 0 frente al de la 1. Es solo para medir H-4; no decide nada.
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
  - **los dos PBO por separado** (`identity.product_pbo_sha256` del producto e `identity.pbo_sha256` de la sonda, P-11);
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
  | F2P-13 | **Sin extras dentro de la cobertura:** durante las ventanas de operación, el testigo en modo de radio no ve nacer ninguna entidad de las clases de la escena que no case con una fila esperada (clase y posición a menos de 0,5 m).<br>Un objeto de más → FALLA.<br>Una criatura de más → FALLA si la ventana de control de P1 no tuvo criaturas, e INCONCLUSO si las tuvo.<br>**Qué es una criatura (H-4):** para un extra de una clase de la escena, lo que el documento declara para esa clase (infectado o animal); en la ventana de control, una entidad con `ai_agent_b = 1` en alguna muestra de la 0 a la K de su `net_id`. El `ai_agent_b` de la muestra 0, por sí solo, no decide (§5.3).<br>**Alcance:** lo que nazca fuera de la cobertura no se ve en M1 (Q-02, §10) | testigo |

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
- **Revisión y congelado:** Sol, como mucho 2 rondas; después se congela (commit y sha). Antes de congelar, las pruebas offline corren **sin saltos** sobre `main` más el núcleo del gate (PR #20), aunque este aún no esté en `main` (H-1).
- **Gate y CLI (DP-13, P-11):** la forma que propone F0.3 para su núcleo (§11):
  - **`F2P` en `SPIKE_REGISTRY`** (`qa/gate_core.py:14`), con `qa/f2p_run.py`, `qa/f2p_eval.py` y `qa/f2p_mutants.py`. Hereda el despacho, las partes, `--evaluate-only` y la agregación;
  - **`m1_gate.py spike F2P --oracle-commit <sha>`:** antes de correr o evaluar nada, compara byte a byte los ficheros del oráculo frente al commit congelado. Si no coinciden, INCONCLUSO `oracle_modified` y sale 2, también con `--evaluate-only`;
  - **`--product-pbo <ruta>`,** junto al `--pbo` de la sonda. En el manifest van `identity.pbo_sha256` (sonda) e `identity.product_pbo_sha256` (producto);
  - la única vía de aceptación es esa entrada con `--oracle-commit`: un `f2p_eval` suelto no cuenta.

  Es un PR de núcleo de F0.3, con su Sol. Quién lo hace lo decide la principal.

### 6.1 Semántica exacta (v1.3.4, tras Sol r1 sobre el oráculo)
Donde esta sección precisa la tabla de §6, manda esta sección.
- **Hallazgos citados (O-nn):** `C:\tmp\dsbx-f2p-work\sol\LAST_sol_o_r1.md`.
- **Contraejemplos ejecutables:** `sol_o_r1_contraejemplos.txt`, en la misma carpeta.
- **Hallazgos H-n:** `C:\tmp\dsbx-f2p-work\recibos\T2-integracion.md`.

#### Base común, para todas las comprobaciones
1. **Medición válida (O-05, O-06).** Una medición es un censo o un testigo de la sonda, y solo cuenta si cumple las tres condiciones siguientes. Las comprueba **una sola función**, que usan todas las comprobaciones, F2P-10 incluida. Si falla, la comprobación que la consume da INCONCLUSO `unbacked_rows`.
   - **Origen:** el trabajo (`per_census_start` o `per_witness_start`) se encoló y se entregó a una instancia del servidor que antes dio `/hello` 200 con `qa0`, el build y `probe_ver = dsbx-qa1+<identity.probe_stamp>`.
   - **Páginas:** están todas, de la 0 a la `n-1`. Cada una lleva el mismo `job`, su índice y el `server_epoch` de esa instancia, y las devuelve la misma instancia del trabajo.
   - **Frescura frente al efecto que juzga:**
     - en el censo, `snap_tick_ms` y `snap_frame` son posteriores al estado terminal de la op que contrasta (punto 2);
     - con la vía (b) de Q9, además, posteriores al plazo de `InitAIAgent`;
     - en el testigo manda la ventana (punto 7).
2. **Estado de una op (O-02).** Es el **último** estado terminal de su `op_id` en los `op.state` del backend, con su marca de tiempo. Los intermedios, como `pendiente`, no cuentan. Tiene que ser anterior a la medición que lo contrasta.
3. **Generaciones (O-03).** El conjunto propio de cada apply (P2, P2n, P3, P4a, P4b y P5) se reconstruye con **su** testigo: las raíces nacidas en su ventana que casan con una fila del documento, por clase y posición a 0,5 m. Cada apply tiene su generación, con `net_id` nuevos, y nunca se reutilizan los de otra. Una creación de más en una generación no queda tapada por buscar solo los `net_id` viejos.
4. **Cobertura (O-07).**
   - Una medición de censo es la **unión** de los trabajos tomados para ese instante (el disco de 120 m más los discos por entidad de §5.3), deduplicada por `net_id`.
   - Una ausencia solo se concluye para un objeto cuya última posición conocida esté a más de 15 m del borde de la unión.
   - Una criatura ausente, o un objeto a menos de 15 m del borde, da INCONCLUSO `coverage_gap`.
5. **Traza (O-11).**
   - Cada op se correlaciona en el `tap` por `(session, op_id)` y `conn`, en orden temporal: entregas, después resultados, después acuses.
   - Rompen la traza una respuesta de otra sesión y un `op.state` sin su `/result` recibido.
   - La única excepción es el corte de P5: hay entrega y no hay resultado, por diseño.
6. **Reconciliación (O-12).** Tras el reinicio del backend (P4a) y tras el corte (P5) tienen que darse tres cosas, todas **antes de la entrega del apply siguiente de esa parte**:
   - `state.read` entregado;
   - su resultado válido recibido (§3.5);
   - el backend en `reconciliada`.

   Un `reconciliada` de otra parte no vale.
7. **Ventanas del testigo (O-14).**
   - Hay un testigo por cada operación: P2, P2n, P3 (apply1 y apply2), P4a, P4b, P5, y la ventana de control de P1.
   - Su centro está en (6170, 7643) y su radio es de 120 m.
   - `[start_tick_ms, start_tick_ms + window_ms]` contiene la entrega y el resultado de la op. En P5 contiene la entrega y el corte.
   - Sus páginas son posteriores al cierre de la ventana.
   - Si falta una ventana o no cubre su op, F2P-13 da INCONCLUSO.
8. **Reinicios (O-10).** Un reinicio del servidor se acredita con un `server_epoch` nuevo en los `/hello` y en la parte, y con el mismo `storage.id`. Sin eso, P4b y P4c dan INCONCLUSO.
9. **Ruido de la CE (H-6, H-10).**
   - El censo puede traer botín de la CE: `net_id` nuevos que no son de ninguna generación, también de clases de la escena (`Barrel_Yellow` aparece como botín en la zona).
   - Ninguna comprobación cuenta la diferencia entera entre dos censos. Se cuentan las generaciones (punto 3) y, como extras, solo los nacimientos que ve el testigo (F2P-13).

#### Por comprobación
- **F2P-01:** el testigo de P2 ve nacer las 33 raíces que casan con el documento, con su multiconjunto de clases, y las 33 están en el censo posterior por el `net_id` del primer tick. La diferencia con P1 no tiene que ser exactamente 33 (punto 9).
- **F2P-02 (O-04):**
  - Cada nacimiento está a menos de 0,5 m, en 3D, de `(x_doc, suelo, z_doc)`.
    - `suelo` es una altura del terreno **independiente** en `(x_doc, z_doc)`. Sale de la `surface_y_m` de la muestra 0 del testigo: `g_Game.SurfaceY` en la x y la z de `EEInit`, como la del censo (`DSBX_QA_X_Persist.c:1704-1705`). Se la pedí a F0.3 para el #22 el 16-nov. Si la fila no la trae, la parte vertical da INCONCLUSO `surface_unbacked`.
    - La `pos_y_m` del propio testigo nunca hace de suelo.
  - **Criaturas:**
    - el salto en 3D de la muestra 0 a la 1 no pasa de `JUMP_MAX_M`;
    - el checkpoint del mod está a `JUMP_MAX_M` o menos de la muestra 1;
    - sin trayectoria, INCONCLUSO.
  - **Objetos:** en el censo posterior, a menos de 0,5 m en 3D.
  - **Q-05:** en un censo válido (punto 1), `alive_b = 1` y `ai_agent_b = 1`.
- **F2P-03:** el estímulo está acreditado (por el testigo o por la traza); el estado es el **terminal**, con el motivo de su variante (§5.5); y el censo lo confirma.
- **F2P-04:** dos entregas del mismo `(session, op_id)`, correlacionadas (punto 5); la segunda respuesta lleva `dup: true`; y el testigo de P2 ve 33 nacimientos, no 66.
- **F2P-05 (O-09):** tras **cada** reset (el primero y el segundo), con la generación de P3:
  - retenidas, solo las propias con contenido ajeno;
  - los ajenos y las tres entidades de la escena 2, intactos en:
    - `net_id` y clase;
    - **pose completa:** x, y, z a 0,05 m y yaw a 1°;
    - padre;
    - **inventario:** clases y `net_id` de los hijos, no solo el contador;
  - estado terminal `parcial/contenido_ajeno` en los dos resets.
- **F2P-06 (O-08, O-09):**
  - Tras la limpieza: 0 propias vivas de la generación de P3, y las tres de la escena 2 intactas con la misma comparación completa.
  - Los estímulos de la sonda, acreditados por sus respuestas crudas:
    - `per_spawn_raw`: cada ajeno con su `net_id`, y en el cargo con `obs_parent_net_id` igual al contenedor pedido;
    - `per_cleanup_qa`: `cleaned_raw_n` igual al número de ajenos puestos.
- **F2P-07 (O-10):**
  - Los reinicios, acreditados (punto 8).
  - El control persistente, creado en P1 (respuesta cruda de `per_spawn_raw persistent_control`), reaparece por clase y por la marca de `health_hp`. Si falta, INCONCLUSO.
  - No aparece ninguna entidad de una clase de la escena 1 a menos de 2 m de la última posición conocida de una entidad de cualquier generación de F2, aunque no case con el documento.
- **F2P-08:** reconciliación (punto 6), y los mismos conteos y poses en 3D (x, y, z), sin extras.
- **F2P-09 (O-13):**
  - K son los nacimientos del testigo del apply cortado que casan con el documento y son anteriores al corte. K tiene que ser mayor que 0.
  - No llega ningún resultado de ese apply.
  - Reconciliación (punto 6).
  - El total final es 33, contando **todas** las entidades vivas de las generaciones de P5 dentro de la cobertura, aunque estén desplazadas.
- **F2P-10 (O-17):**
  - cada borrado «confirmado» falta en la medición siguiente (puntos 1 y 4);
  - cada `delete_failed` sigue vivo;
  - el tick informado es la separación entre la petición y la confirmación **del mismo** borrado, con el mismo reloj.
- **F2P-11 (O-01):** los edificios de referencia, medidos en la diag de F0.3 (PR #22, `run_20261116T000915Z`, censo a 115 m de (6170, 7643)), por clase y pose, a 0,5 m y 2°:

  | Clase | x | z | yaw |
  |---|---|---|---|
  | `Land_Lunapark_Shooting_Gallery` | 6137,06 | 7643,80 | −128,64 |
  | `Land_House_2W01` | 6212,85 | 7644,65 | −138,33 |
  | `Land_City_Stand_Grocery` | 6137,23 | 7702,65 | 39,30 |
  | `Land_House_2B01` | 6184,06 | 7715,68 | −142,45 |

  Llevan `net_id` real, con la parte alta negativa, y `health_hp = -1`.
- **F2P-12:** sin cambios.
- **F2P-13:** el punto 7, más la definición de criatura de §6 (H-4).

#### Mutantes, negativas y fixture
- **Cada contraejemplo de Sol r1 que hoy da PASA** pasa a ser un mutante, con la comprobación que tiene que tumbar, o una negativa.
- **Los casos que hoy dan FALLA siendo una partida buena** pasan a variantes positivas que tienen que dar PASA:
  - `legitimate_fresh_P3_generation`;
  - `normal_opstate_transitions_before_terminal`;
  - `good_creature_tracked_by_extra_disk`;
  - `33_correct_roots_plus_background_Apple`;
  - `H4_control_creature_AI_initializes_at_tick1`.
- **O-16:** la negativa de procedencia copia como filas de la sonda las lecturas del backend (`/api/observation`) y tiene que dar `unbacked_rows`. Va aparte del mutante geométrico de F2P-12.
- **La fixture positiva tiene que ser una partida plausible:**
  - las referencias reales de F2P-11;
  - botín de la CE en los censos, también nuevo entre censos y de una clase de la escena (`Barrel_Yellow`);
  - `net_id` firmados y `hp = -1` en los edificios;
  - una generación con `net_id` nuevos por cada apply;
  - estados `pendiente` y después el terminal;
  - ventanas y páginas con tiempos coherentes;
  - reinicios con epoch nuevo;
  - los artefactos del arnés para la agregación (§7).

#### Gate (O-15, H-7)
- **Una campaña por build** (diag y retail), cada una con una sola parte `run`. No hay parte `run-retail`.
- **Los mutantes de F2P son sin conexión.** `f2p_mutants.py` no exporta `EXPECTED_MUTANTS`: esa tabla del núcleo es para mutantes en partida, con `injection.json`, y no admite `missing` en `must_fail_checks`. La agregación de §7 se prueba con `aggregate_spike`.
- **El commit del oráculo es uno solo:** en el manifest, `identity.oracle_commit` (lo escribe `PartContext` con el commit ya verificado), `f2p.oracle_commit` y el commit del evento `oracle.frozen` son el mismo id de 40 hex. Si no, INCONCLUSO `oracle_modified`.

## 7. Aceptación
- **T1:** §3.9.
- **T2:**
  - las pruebas offline del oráculo en verde;
  - cada mutante tumba su comprobación;
  - con la evidencia sintética de una partida buena, PASA;
  - **por la agregación del núcleo** (H-3): esa misma evidencia, completada como una parte `run` del arnés de F0.3, da PASA en `f03_common.aggregate_spike`. La parte lleva `part.json` con `op_nonce`, la identidad con el `git_head` real, `probe_stamp` calculado en ese commit, `params.wire_cap` y los `/hello`, como en `test_s_persist_offline.py`. Un mutante da FALLA y una negativa nunca da PASA.
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
- **El `net_id` de los edificios del mapa:** F0.3 midió en su diag que es real, con la parte alta negativa, y se lee con signo (§5.3). Los edificios de referencia de P1 se siguen identificando por clase y pose (F2P-11).
- **Cobertura del testigo (F0.3, tras la diag):** solo ve lo que deriva de las 5 raíces enganchadas. Un extra de alguna de estas clases no lo ve F2P-13:
  - jugadores;
  - `BoatScript` y `Helicopter`;
  - edificios que derivan directo de `Building`;
  - `AdvancedCommunication`, `ScriptedEntity` y `EffecterBase`;
  - clases de mods.

  Las clases de las dos escenas sí están cubiertas.
- **Botín de la CE (H-6):** durante una ventana de operación, la CE puede crear dentro del radio un objeto de una clase de la escena; `MediumTent` y `Barrel_Red` salen como botín. F2P-13 daría FALLA con la clase y la posición de ese objeto. Falla cerrado: si pasa, se mira la ventana de control de P1 y se decide con el dato.
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
- v1.3.2 (2026-11-15): **solo documentación**, por U-01 (MEN) de Sol r2 sobre el código de T1. §3.7 trae la envolvente v1.3 medida con su comando reproducible (1985, 2934, 3198 y 926 B) en lugar de remitir a la tabla v1.2.2 de F2b §3.6. Ninguna regla cambia.
- v1.3.3 (2026-11-16): **alineación con la sonda real y con el núcleo del gate,** antes de congelar el oráculo. Los hallazgos H-1 a H-6 de la integración del oráculo están en `C:\tmp\dsbx-f2p-work\recibos\T2-integracion.md`.

  | Origen | Cambio |
  |---|---|
  | F0.3 tras su diag (PR #22, `71697fb`) | las raíces del gancho del testigo y su cobertura; la muestra 0; la posición de `EEInit`, medida; `hp = -1` y el `net_id` real de los edificios del mapa (§5.3, §10) |
  | H-4 | qué es una criatura en F2P-13: no basta el `ai_agent_b` de la muestra 0 (§6) |
  | H-1 a H-3 | la aceptación de T2 por la agregación del núcleo, y el congelado sin saltos sobre `main` más el PR #20 (§6, §7) |
  | H-5 | checkout en LF para la partida (§5.1) |
  | H-6 | riesgo: el botín de la CE (§10) |
  | errata | en el manifest, la sonda va en `identity.pbo_sha256`, no en `probe_pbo_sha256` (§5.4) |

  Nada de §3 (T1) ni de §4 (T3) cambia.
- v1.3.4 (2026-11-16): **la semántica exacta del oráculo (§6.1),** tras la ronda 1 de Sol sobre él.
  - Sol dio UNSOUND, con 15 BLOQ (O-01 a O-15) y 2 MAY (O-16 y O-17). Confirmó H-1 a H-5 y precisó H-6.
  - Varios BLOQ eran huecos del brief:
    - los edificios de referencia sin fijar (O-01, H-9);
    - de dónde sale la altura del suelo (O-04);
    - qué es una medición válida y fresca (O-05, O-06);
    - las generaciones (O-03);
    - la cobertura como unión de discos (O-07);
    - la traza y la reconciliación (O-11, O-12);
    - las ventanas del testigo (O-14).
  - §6.1 los fija, con la fixture positiva plausible y el encaje con el gate (O-15, H-7).
  - En §5.3, la medida informativa de `ai_agent_b` (H-4).
  - Nada de §3 (T1) ni de §4 (T3) cambia.
