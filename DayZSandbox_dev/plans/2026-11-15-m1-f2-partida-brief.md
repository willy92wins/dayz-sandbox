# Brief F2-partida (R25): escena viva en el mod núcleo y sus partidas (M1)

- **Versión:** v1.3.16, **congelada.** La v1.3.16 ajusta dos reglas de la traza al mod y al `tap` reales (§5.4, §6.1 punto 5, §12):
  - el `/result` de la op cortada y sus reintentos están exentos hasta la primera respuesta del backend nuevo, sin respuesta o con el 502 del `tap`, que se distingue por `upstream_status`;
  - «el backend estaba vivo» tiene una sola lectura;
  - en un empate de milisegundo con un `/hello`, valen los dos órdenes, y el oráculo mira la hora de cada línea del `tap`, no su lugar en el fichero.

  La v1.3.15 corrige la traza tras el cierre acotado de T2f-15. Un `/result` no lleva conexión: es la de su entrega, porque el cable real no la trae. La `conn` se compara como la compara el backend. El registro del peer se exige a la hora de la petición. Un problema de `req_id` fuera de las partes da INCONCLUSO. Un `/result` sin respuesta es un acuse que falta, salvo el de la op cortada de P5 (§6.1 punto 5, §12). La v1.3.14 añade el `req_id` del `tap`: cada petición y su respuesta llevan el mismo, la traza se empareja solo por él y, sin él, da INCONCLUSO. También fija las anclas de identidad de la traza: la conexión registrada de cada peer, y que una `inst` o un `epoch` vacíos no casan con nada. Y escribe el alcance de la excepción del corte de P5, que exime todas las reentregas de la op cortada hasta el `cut` (§5.4, §6.1 punto 5, §12). La v1.3.13 corrige §5.2: P4c resetea solo la escena 1, y la escena 2 sigue aplicada en el backend (X-03 de la pasada de Claude sobre T2f-5, decisión de la principal; §5.2, §10, §12). La v1.3.12 recoge el cierre de Sol r4 y la pasada de Claude sobre T2f-4: en una etapa positiva, `observado` es exactamente `("observado", "")`; el `server_epoch` de la parte deja de ser obligatorio; y T2f-5, antes de congelar (§6, §6.1, §12). La v1.3.11 recoge el arbitraje de Sol r4: el oráculo se ajusta al cable real de la sonda (las páginas no llevan `server_epoch` y el `result` no lleva `inst`) y cierra los PASA falsos y el FALLA espurio que encontró Sol (§6.1, §12). La v1.3.9 corrige lo que pasa al reiniciar el backend: sesión nueva, ids que se repiten y la op cortada de P5 sin terminal (§6.1, puntos 2, 5 y 6, y F2P-09). La v1.3.10 recoge el contrato de salud del censo de F0.3 (§5.3). Ver §12. Es la ronda 2 de Sol (la última), el arbitraje del orquestador y la decisión de la principal sobre la sonda. Añade la medida de la envolvente v1.3, la alineación con el contrato del testigo tras la diag de F0.3 y con el núcleo del gate, y la semántica exacta del oráculo tras Sol r1 sobre él (§6.1, §12). Las interfaces de F0.3 de §5.3 están confirmadas por escrito y medidas en su diag. 2026-11-16, por el orquestador de F2.
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
| P1 | censo de referencia; **ventana de control** del testigo, en modo de radio y sin crear nada, para medir el ruido que quede | mundo sin nada de F2 | base |
| P2 | testigo activo → `POST /api/apply` → `observado`; segunda entrega forzada del mismo `(session, op_id)` dentro de la retención; censo | escena 1 aplicada (33) | A2 |
| P2n | **negativa real:** apply de una variante de la escena 1 con un estímulo que tiene que acabar en `parcial` o `fallido` (§5.5) | escena 1 limpia otra vez (reset) | A2 (-) |
| P3 | apply de la escena 1; reinicio del backend con la escena 2 → apply de la escena 2; reinicio con la escena 1; ajeno en el suelo y ajeno dentro de `obj-17` (§5.3); reset → `parcial/contenido_ajeno`; censo; segundo reset → igual | `obj-17` retenido | A3 |
| P3c | limpieza: la sonda borra sus ajenos (§5.3); reset de la escena 1 → `observado`; censo | escena 1 vacía; escena 2 aplicada | A3 |
| P4a | control persistente puesto, **después** de la limpieza de P3c y fuera de la zona de F2 (§5.3, V-09); reinicio **solo del backend** (mismo epoch): apply de la escena 1 → reconcilia; el reset borra la generación viva; apply → 33; censo sin extras | escena 1 aplicada | A4 |
| P4b | reinicio del **servidor** sin reset (epoch nuevo, mismo storage): censo → nada de F2 reaparece y el control persistente sí; apply → 33 | escena 1 aplicada | A3, A4 |
| P4c | reset de la escena 1 → reinicio del servidor con reset previo: censo → nada de F2 reaparece y el control sí (v1.3.13) | sin F2 en el mundo; la escena 2 sigue aplicada en el backend y no se resetea | A3 |
| P5 | apply cortado: el runner corta el bridge después de un efecto observado y antes del resultado, y reinicia el backend → lectura de reconciliación **antes** del apply nuevo → `33 + 0` | escena 1 aplicada | A4 (-) |

- **Lo que no se puede provocar en el juego** lo cubren además los mutantes del oráculo (§6): metatests del evaluador, que no sustituyen a P2n (P-04).
- **Censos que añade la v1.3.8** (R-04, V-07). Dan la última posición válida de cada entidad para la cobertura de §6.1, punto 4, y cada borrado se juzga en su epoch:
  - **un censo justo antes de cada reset** y de cada borrado que se juzga (P3, P3c, P4a y P4c);
  - **un censo justo después** de cada uno, con un disco por criatura centrado en su posición de antes: 60 m para infectados y 120 m para animales;
  - **un censo antes de cada reinicio del servidor;**
  - **un censo antes de P2n y antes de P5.**
- **P5 tiene dos testigos que no se solapan** (V-03, S-05):
  - `P5:cut`, el del apply cortado;
  - `P5:apply2`, el del apply nuevo después de reconciliar.
- **El corte de P5** lo registra el runner como evento `cut`, con su `t_ms` en el reloj común (R-11, §5.4).
  - **v1.3.11 (F-03):** el efecto previo al corte se acredita con los `poll` de la sonda como ancla (§6.1, F2P-09). El runner no añade nada, pero corta después de al menos un `poll` de la sonda posterior al primer nacimiento del apply cortado. Si corta antes, P5 da INCONCLUSO y se repite.
  - Tras el corte, el runner reinicia el backend y lo registra como `restart` con `target: backend` (§5.4).
- **Discos por criatura (v1.3.11, F-02):** cada disco se juzga en su propio instante (§6.1, punto 4). El runner toma el censo principal enseguida y los discos lo antes posible; un disco tardío deja su criatura en INCONCLUSO `coverage_gap`.
- **Hijos propios (P-09):** en M1 el producto solo crea raíces (sin actores, D3), así que no hay hijos propios que resetear en partida. Esa parte de A3 se acredita offline (F2b, filas F2-A3) y aquí queda **N/A con motivo**. F3 la lleva a partida con el equipo de los actores.

### 5.3 Sonda (interfaces de F0.3)
Todas van por el bridge de la sonda (`qa0`), así que quedan en la evidencia.
- **Censo:** `per_census_start`, con:
  - `select_all_entityai_b = 1` e `include_director_b = 1`, para los inventarios de jugador;
  - `radius_m = 120`, centrado en (6170, 7643), más un disco de 60 m por cada entidad seguida cuya última posición quede a menos de 15 m del borde de lo cubierto (P-05);
  - el resultado se deduplica por `net_id`;
  - medido en la diag de F0.3: `max_hp = health_hp = -1` significa «sin sistema de daño», y los edificios del mapa **sí** tienen `net_id` real, con la parte alta negativa (`-2147225600:847447385`). El `net_id` se lee como `high:low` con signo.
  - **La salud en el censo (v1.3.10; contrato de F0.3 del 16-nov, para #22 rebasado sobre #21):**
    - `-1/-1` quiere decir «sin sistema de daño **inicializado**». `HasDamageSystem()` dice si ya está inicializado, no si lo tiene (vanilla `object.c:974-976`). Un objeto recién creado devuelve false;
    - **lo que crea el QA** (`per_apply_scene`, `per_spawn_raw` y los spawns del testigo) lleva salud real, `> 0`. Con marca, `health_hp` es `max_hp × ratio`: la sonda la pone al crear y la comprueba releyendo. Si no puede, la op da error; nunca `ok` con `-1`. **`health_mark_pending` no existe.** Por ejemplo, el control de S-persist quedó en 1098,5 = 1300 × 0,845;
    - **los objetos del mundo** se leen con la guarda. Medido en las diags 1 y 2 de F0.3 (copias en `C:\tmp\dsbx-f2p-t2d\_ref\diag_bridge.jsonl` y `diag2_bridge.jsonl`): los 34 `Land_*` dan `-1/-1`, y los objetos del botín de la CE (47 y 46) dan salud real, gastada (`Barrel_Yellow` 1300/1214,6, `BarbedWire` 300/131,5);
    - **lo que crea el producto** es, para la sonda, un objeto del mundo. Sin medir: puede dar salud real o `-1/-1` según si su sistema de daño ya está inicializado. Ninguna comprobación depende de la salud de lo que crea el producto, y las dos formas tienen que dar PASA;
    - **el testigo no lleva salud** (§5.3, su `ncol`).

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
    - **`surface_y_m`, la última columna del `ncol`** (F0.3 en el #22, confirmado el 16-nov): `g_Game.SurfaceY` en la x y la z de cada muestra. En la muestra 0 son las de `EEInit`; se calcula al emitir la fila, y como el terreno no cambia, el valor es el mismo;
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
  - **F2 la llama sin discos** (`rows = 0`; V-09):
    - con discos, la sonda además barre las clases centinela (`Barrel_*`, `WoodenCrate`, `SeaChest`…; `DSBX_QA_X_Persist.c:215-226`, #22), que son clases de las escenas;
    - sin discos, borra todos los registros crudos (`:2150-2166`). Por eso el control persistente se crea después de la limpieza de P3c.
- **Control persistente (P-06; V-09, V-11):** `per_spawn_raw` con `mode = "persistent_control"`, que ya existe, con los mismos valores que el PER-06 de S-persist:
  - `Barrel_Yellow` con un `Fireplace` en el cargo y `health_mark_ratio` 0,845, en **(4860, 10200), fuera de la zona de F2**. `Barrel_Yellow` es clase de la escena 1 y aparece como botín de la CE en la zona; fuera de ella no se confunde con nada de F2.
  - **Cuándo:** se crea al empezar P4a, **después** de la limpieza de P3c, que borraría cualquier registro crudo anterior.
  - Se crea sin `ECE_NOPERSISTENCY_WORLD`.
  - **Cómo se reconoce:** tras cada reinicio, con un censo propio de 30 m centrado en su posición, por clase y posición a 0,5 m.
    - Si la salud es legible, también por la marca: `|health_hp / max_hp − 0,845| ≤ 0,01`.
    - Si la sonda da `health_hp = −1`, basta clase y posición `[verify F2 en partida]`.
  - **Tiene** que reaparecer, para demostrar que el storage se recargó. Si no, P4b y P4c dan INCONCLUSO.
  - Lo borra `per_cleanup_qa` al final de P4c.

### 5.4 Evidencia (`samples/`)
- **Del bridge del producto, la traza completa** (P-08, Q-04): las entregas por `(session, op_id)` con su `conn`, los resultados recibidos con su `dup`, los acuses y las lecturas de reconciliación con su orden temporal.
  - **La captura la hace el runner con un proxy HTTP** (`tap`) entre el mod y el puerto del bridge del backend. El mod apunta al `tap`, y el `tap` reenvía al backend.
  - El `tap` registra en `samples/bridge_tap.jsonl` los cuerpos crudos de cada petición y respuesta (`/hello`, `/poll`, `/result` con `dup` y `/catalog`), con marca de tiempo, **antes** de que el backend descarte duplicados.
  - **La identidad de cada petición (v1.3.14), obligatoria para T4:**
    - el `tap` numera cada petición al llegar con un `req_id` entero, único en la partida, y escribe el **mismo** `req_id` en el registro de su respuesta;
    - es lo que hace el proxy de F1b-peers: un contador desde 0, asignado bajo lock al llegar, y el mismo número en la línea del final (`qa/live/fault_proxy.py:255`, `:434-438` y `:893-906`);
    - una petición sin respuesta (la conexión se cortó) se queda solo con su registro de petición;
    - el orden de los `req_id` no tiene por qué ser el de llegada. El proxy toma la hora antes de leer el cuerpo y de tomar el lock (`fault_proxy.py:413`). En cada una de las dos partidas retail de F1b-peers del 15-nov hay una pareja con el orden cambiado (16 ms y 1 ms). Se empareja solo por igualdad. Tampoco el orden de las líneas tiene por qué ser el de su hora: el proxy estampa el final antes de coger el lock de escritura (`fault_proxy.py:897` y `:921`). El oráculo mira siempre la hora, nunca el lugar de la línea (v1.3.16). **El `tap` de T4 estampa una respuesta antes de escribirla al peer** (v1.3.16, T2f-15m): el proxy de F1b la estampa después (`fault_proxy.py:642-643` y `:897`), y una petición que el mod manda en cuanto recibe esa respuesta (`DSBX_Peer.c:991` y `:1497`) puede quedar estampada antes que ella;
    - **quién contestó (v1.3.16), obligatorio para T4:** el registro de cada respuesta lleva `upstream_status`. Es el HTTP con que respondió el backend, o nulo si la respuesta la fabricó el propio `tap` porque el backend no estaba: es lo que guarda el proxy de F1b (`fault_proxy.py:765`, `:798-808` y `:914`). Un registro de respuesta sin el campo cuenta como respuesta del backend, como en la fixture y en los `tap` anteriores. **El cierre sin respuesta (v1.3.16, T2f-15l):** un `upstream_status` 0 es lo que graba el proxy de F1b cuando el backend acepta la conexión y la cierra sin contestar, por ejemplo al apagarse. `fault_proxy.py:765` guarda el estado de `_parse_headers`, que es 0 sin línea de estado, y la respuesta va vacía. No es una respuesta del backend, igual que una nula. **Los valores (v1.3.16, T2f-15m):** `upstream_status` es un entero o nulo; un booleano no es ni el 0 del cierre ni el nulo del `tap`, y cuenta como respuesta del backend, igual que un registro sin el campo. El `tap` escribe una respuesta sin bytes con el cuerpo nulo o sin el campo; `{}` es un cuerpo, no una respuesta vacía. Pasa en las tres partidas de F1b-peers con reinicio: un `/poll` retenido del cliente, 0,8-1,6 s antes del `backend_restart`;
  - El backend no cambia: no hay ganchos de observación.
- **Del backend:** los eventos `op.state`, `GET /api/ops` y `GET /api/observation` (metros).
- **De la sonda:** las respuestas crudas de `QABridge`, cada página del censo y del testigo con su trabajo, página, epoch, sello de sonda y marca de tiempo (P-10).
- **Del mod:** las líneas `DSBX_SCENE_DEL` de su log de script, con las señales de borrado por tick (DP-6).
- **Un solo reloj (R-03):** todos los `t_ms` de `samples/` salen del monotónico del proceso del runner, con un único origen por parte. Eso incluye el `tap`, los eventos del backend, el bridge de la sonda y los eventos del runner (`cut` y los reinicios). Los ticks del motor van aparte y solo se comparan entre sí (§6.1, punto 10).
- **El epoch, por evento (S-10, V-07):** cada evento del `tap` y de la sonda lleva la instancia (`inst`) y el `epoch` vigentes. Una parte puede abarcar dos (§6.1, punto 8).
- **Los reinicios (v1.3.9):** el runner registra cada reinicio en `samples/backend.jsonl` como evento `restart`, con `target` (`backend` o `server`) y el epoch del mundo, igual que el `cut` (contrato, `qa/f2p_evidence_contract.md`). Los `restart` del backend parten los `op.state` en tramos, uno por sesión (§6.1, punto 2). **Cuándo (v1.3.16, T2f-15m):** el runner registra el `restart` del backend al relanzarlo, antes de que el backend nuevo pueda aceptar un `/hello`. El tramo nuevo empieza en ese evento. El runner de F1b lo registraba entre 0,8 y 1,6 s después del apagado, ya tras el `/hello` nuevo: con un `restart` así, ese `/hello` caería en el tramo viejo.
- **Las etiquetas de los censos (V-08):** el disco principal lleva `<tag>`, y cada disco por entidad, `<tag>:disk:<lid>` (§6.1, punto 4).
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
- **Contrato:**
  - `evaluate(part_dir)` lee solo `samples/`, los campos del manifest de F0.3-0 §5.2, los de §5.4 y el `oracle_check.json` que el núcleo deja en la raíz de la evidencia (§6.1, Gate; R-14);
  - sale 0 PASA, 1 FALLA y 2 INCONCLUSO (`gate_core.py:73-82`).
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
- **Revisión y congelado:**
  - **Rondas:** Sol, como mucho 2; después se congela (commit y sha). Antes de congelar, las pruebas offline corren **sin saltos** sobre `main` más el núcleo del gate (PR #20), aunque este aún no esté en `main` (H-1).
  - **Lo que pasó:** Sol r1 y r2 dieron UNSOUND. El orquestador arbitró (v1.3.7) y aceptó todos los R-nn de r2.
  - **Corrección de la principal (16-nov, v1.3.8):** Sol revisa **siempre** el código final antes de congelar.
    - Sol r3, sobre `2865362`, dio UNSOUND (S-01 a S-16).
    - Queda como mucho **una ronda más, r4**.
    - Después arbitra el orquestador y deja escrito qué cierra cada commit. El arbitraje de r3 está en `C:\tmp\dsbx-f2p-work\recibos\arbitraje-r3.md`.
    - La revisión adversarial de otra familia (un subagente de Claude: ni DeepSeek, autor, ni OpenAI) va **en paralelo y como extra**, nunca en lugar de Sol. La de `2865362` dio UNSOUND (V-01 a V-18).
    - Si el filtro de OpenAI corta a Sol sin veredicto, se arbitra con las negativas y esa pasada.
    - **Sol r4,** sobre `7ed2615`, dio UNSOUND: F-01 a F-11 BLOQ, F-12 a F-14 MAY y F-15 MEN. El orquestador los acepta todos, más A-01, que encontró al comprobar F-01, y los recoge en esta v1.3.11 (`C:\tmp\dsbx-f2p-work\recibos\arbitraje-r4.md`).
      - **Cierre:** cada caso pasa primero en rojo sobre `7ed2615` (el resultado espurio que dijo Sol) y después en verde con el arreglo, con su motivo. A eso se suman la prueba de conformidad con el cable real (§6.1, fixture) y la pasada de Claude sobre el diff como extra.
      - **Cierre de r4 (v1.3.12):** la principal pidió a Sol un cierre limitado al diff de T2f-4 (`7ed2615..bf498a5`), sin ronda nueva de ataques. Dio **OK en su alcance** (`C:\tmp\dsbx-f2p-work\sol\LAST_sol_o_r4c.md`), con 3 MAY y 1 MEN fuera de él.
      - **La pasada de Claude** sobre el mismo diff dio UNSOUND, con 5 PASA falsos reproducidos (W-01 a W-05) y dos regresiones de T2f-4, W-04 y W-07 (`C:\tmp\dsbx-f2p-work\review\adv_t2f4\REVIEW_claude_t2f4.md`). El orquestador los volvió a reproducir sobre el candidato.
      - **T2f-5, por decisión de la principal, antes de congelar:**
        - **bloquean el congelado:** W-01 a W-05, W-07, el `server_epoch` de la parte (§6.1 punto 8) y W-11 (§6.1 punto 2);
        - **si caben en la misma corrida:** W-06, W-08, W-09 y W-10;
        - **al backlog del recibo de congelado:** W-12, W-13 y lo que no quepa.
      - **Método de T2f-5:**
        - cada reproductor de un PASA falso queda como caso permanente: rojo sobre `bf498a5`, verde y su motivo;
        - un caso por cada etapa que lista §6.1 para cada regla, no uno solo;
        - al final, la tabla entera de rojo y verde sobre el head: los `r4_*` y los antiguos.
      - **Cierre de T2f-5:**
        - confirmación de Sol limitada a su diff, con la pasada de Claude en paralelo y como extra;
        - después se congela;
        - solo un PASA falso reproducido abre otra ronda, y la arbitra la principal. Lo MAY o MEN que salga entonces va al backlog.
  - **Antes de congelar:** cada ataque de Sol (O, R y S) y de la pasada (V) tiene su mutante, su negativa o su variante positiva, y da lo que dice §6.1.
- **Gate y CLI (DP-13, P-11):** la forma que propone F0.3 para su núcleo (§11):
  - **`F2P` en `SPIKE_REGISTRY`** (`qa/gate_core.py:14`), con `qa/f2p_run.py`, `qa/f2p_eval.py` y `qa/f2p_mutants.py`. Hereda el despacho, las partes, `--evaluate-only` y la agregación;
  - **`m1_gate.py spike F2P --oracle-commit <sha>`:** antes de correr o evaluar nada, compara byte a byte los ficheros del oráculo frente al commit congelado. Si no coinciden, INCONCLUSO `oracle_modified` y sale 2, también con `--evaluate-only`;
  - **`--product-pbo <ruta>`,** junto al `--pbo` de la sonda. En el manifest van `identity.pbo_sha256` (sonda) e `identity.product_pbo_sha256` (producto);
  - la única vía de aceptación es esa entrada con `--oracle-commit`: un `f2p_eval` suelto no cuenta.

  Es un PR de núcleo de F0.3, con su Sol. Quién lo hace lo decide la principal.

### 6.1 Semántica exacta (v1.3.4 tras Sol r1; v1.3.7 tras Sol r2 sobre el oráculo)
Donde esta sección precisa la tabla de §6, manda esta sección.
- **Hallazgos citados:**
  - O-nn (Sol r1): `C:\tmp\dsbx-f2p-work\sol\LAST_sol_o_r1.md`;
  - R-nn (Sol r2): `LAST_sol_o_r2.md`, en la misma carpeta.
- **Contraejemplos ejecutables de Sol r1:** `sol_o_r1_contraejemplos.txt`, en la misma carpeta.
- **Hallazgos H-n:** `C:\tmp\dsbx-f2p-work\recibos\T2-integracion.md`.

#### Base común, para todas las comprobaciones
1. **Medición válida (O-05, O-06, R-05, R-06).** Una medición es un censo o un testigo de la sonda, y solo cuenta si cumple las tres condiciones siguientes.
   - **Quién la comprueba:** **una sola función**, que usan todas las comprobaciones, F2P-10 incluida. Si falla, la comprobación que la consume da INCONCLUSO `unbacked_rows`.
   - **Qué pasa también por ella:**
     - los estímulos crudos de la sonda (`per_spawn_raw` y `per_cleanup_qa`);
     - toda fila que aporte una posición, incluidas la «última posición conocida» y la búsqueda hacia atrás de F2P-10. Esas filas, además, tienen que ser del mismo epoch.
   - **Origen (S-01):**
     - el trabajo (`per_census_start`, `per_witness_start` o el estímulo) se encoló y **se entregó** (evento `deliver` del bridge de la sonda) a una instancia del servidor;
     - esa instancia dio `/hello` 200 con `qa0`, el build y `probe_ver = dsbx-qa1+<identity.probe_stamp>`, **antes** de esa entrega en el reloj común (punto 10);
     - la instancia del encolado, la de la entrega y la de la respuesta (páginas o resultado del estímulo) son **la misma**, también en los estímulos;
     - **la instancia de una respuesta (v1.3.11, A-01):** el evento `result` del bridge de la sonda **no lleva `inst`** (`qa/bridge_qa.py:858-866`). Es la instancia que el bridge tenía aceptada para ese peer al recibirlo, la del último `hello` aceptado de ese peer antes del `result` en el reloj común. El bridge rechaza con `409 hello_required` cualquier `/result` de otra instancia (`qa/bridge_qa.py:833-836`), y ese rechazo queda en el registro como `inst_reject`;
     - sin `deliver`, con el `/hello` después de la entrega o con instancias que no casan, INCONCLUSO.
   - **Páginas (S-01, S-15):**
     - están todas, de la 0 a la `n-1`; con 0 filas, `pages_n = 0` y se lee la página 0 (`DSBX_QA_Probe.c:1553-1557`);
     - cada una lleva el mismo `job` y su índice (`page_n`). **No llevan `server_epoch`** (v1.3.11, F-01): en el cable real, las páginas de `job_read` traen en `sk` solo `job`, `state`, `reason` y `resource` (`DSBX_QA_Probe.c:1570-1578`);
     - **el epoch del trabajo** es el `server_epoch` de su **lectura de arranque**, que sí lo trae (censo y testigo, `censo-interfaz-f03.md:28` y `:121`). No puede estar vacío. Sus páginas se ligan a él por el `job` y por la instancia de su entrega, que tiene que ser la del arranque;
     - **conformidad (v1.3.11):** el oráculo acepta tal cual las líneas reales de las diags de F0.3. Lo comprueba una prueba (fixture, abajo);
     - en el censo, `snap_tick_ms` y `snap_frame` son mayores que 0, y `rows_captured_n` es igual al número de filas;
     - los selectores del censo tienen los valores de §5.3: `select_all_entityai_b = 1`, `include_director_b = 1`, el centro y el radio de su disco.
   - **Frescura frente al efecto que juzga:**
     - en el reloj común (punto 10), la **entrega** del trabajo a la sonda es posterior al estado terminal de la op que contrasta (punto 2);
     - si esa op no tiene estado terminal, la medición no es fresca y da INCONCLUSO, nunca «sin comprobar»;
     - los ticks del motor (`snap_tick_ms`, `start_tick_ms` y `tick_ms`) **nunca** se comparan con `t_ms` (R-03);
     - en el testigo manda la ventana (punto 7);
     - M1 usa la vía (a) de Q9 (`FLAGS_CREATURE` con `ECE_INITAI`, §4.4), así que no hay plazo de `InitAIAgent` que comprobar.
2. **Estado de una op (O-02, S-09).**
   - Es el **último** estado **terminal** de su `(sesión, op_id)` en los `op.state` del backend, con su marca de tiempo. Tiene que ser anterior a la medición que lo contrasta.
   - **La identidad de una op es `(sesión, op_id)`, nunca el `op_id` solo** (v1.3.9):
     - cada instancia del backend tiene su sesión (`app/backend/bridge.py:112`, `secrets.token_hex(8)`), y cada reinicio del backend (los dos de P3, P4a y P5) abre una sesión nueva;
     - los ids de la API vuelven a empezar en `op-1` con cada instancia (`app/backend/server.py:88-89`, `scene_live.py:360-362`), así que se **repiten** entre sesiones;
     - el `op.state` del backend no lleva la sesión: es la de la instancia que lo emitió, el tramo entre dos eventos `restart` del backend en el registro del runner (§5.4), que coincide con la sesión de las respuestas a `/hello` de ese tramo;
     - solo las ops de la API emiten `op.state` (`server.py:259`, `:297`; `scene_live.py:378`). Las órdenes internas del bridge, como la lectura de reconciliación, el `scene.observe` del checkpoint y las compensaciones, llevan id `rd-N` (`bridge.py:234-236`) y no emiten ninguno.
   - **La op cortada de P5 no tiene terminal, y no se le exige:** su backend muere en el corte, y el nuevo no conoce sus ops (`server.py:88`). Ninguna medición se contrasta con ella: K sale de la ventana `P5:cut` (punto 7).
   - **Terminales, los del backend:**
     - `observado/*`;
     - `fallido/*`;
     - `parcial` solo con los motivos `contenido_ajeno`, `compensada`, `interrumpida`, `superada` y `mundo_reiniciado` (`app/backend/scene_live.py:116-124` y `:676-682`).
   - **No son terminales,** y no cuentan: `pendiente` y cualquier otro `parcial`, como `parcial/sin_resultado`.
   - **Igualdad exacta (v1.3.11, F-05):** el estado y su motivo se comparan con los que emite el backend por igualdad exacta, nunca por prefijo. Un estado que el backend no emite, como `observado_inventado`, no es terminal.
   - **El estado esperado de cada etapa** es el de §5.2: por ejemplo, el apply de P2 da `observado`, los resets de P3 dan `parcial/contenido_ajeno` y el reset de P3c da `observado`. Una etapa positiva con otro terminal, como `fallido/create_failed`, hace fallar la comprobación que la juzga, aunque el censo cuadre. La única etapa sin terminal es la op cortada de P5.
   - **`observado` es exactamente `("observado", "")` (v1.3.12, W-11, decisión de la principal).** Es el terminal del `/result` normal, que deja el motivo vacío (`app/backend/scene_live.py:566-568`).
     - `observado/reconciliada` solo lo da la reconciliación de una orden que sigue sin resolver (`scene_live.py:624` y `:767`). La cierra el checkpoint (`:796-801`, que acaba en `:636`) o, en el reset, `:870`.
     - Una orden se queda sin resolver por un resultado con error (`:578-581`), por no recibir resultado a tiempo (`app/backend/bridge.py:385`, `parcial/sin_resultado`) o por una reconexión del servidor con la orden en vuelo (`bridge.py:460-468`).
     - Fuera de esas inyecciones, `reconciliada` quiere decir que se perdió el `/result`, y aceptarlo dejaría pasar una implementación que los pierde. Donde una etapa inyecte la pérdida del resultado o una reconexión del mod con una orden en vuelo, `reconciliada` sigue valiendo. **Hoy ninguna etapa positiva de §5.2 lo hace**: el corte de P5 mata la op con su backend, y P4b reinicia el servidor sin ninguna orden en vuelo. En todas vale solo `("observado", "")`, y otro terminal hace fallar la comprobación que juzga la etapa.
     - El backend nunca da un segundo terminal a una op ya resuelta. Ningún caso del oráculo lo inventa.
3. **Generaciones (O-03, R-08, S-03, S-04, V-06).**
   - **Reconstrucción:** el conjunto propio de cada apply (P2, P2n, P3, P4a, P4b y los dos de P5) se reconstruye con **su** testigo.
     - Son las **raíces** nacidas en su ventana que casan con una fila del documento, por clase y a menos de 0,5 m en horizontal.
     - Raíz quiere decir sin padre en la muestra 0, y también sin padre en el censo.
     - Un nacimiento de una clase que **no** es del documento no entra en la generación: es ruido (punto 9).
   - **Correspondencia uno a uno:**
     - cada fila del documento de ese apply casa con un solo nacimiento, y cada nacimiento con una sola fila; las multiplicidades se consumen;
     - un nacimiento de una clase del documento que no encuentra fila libre es un **extra** de esa generación;
     - **los hijos (v1.3.11, F-10):** en M1 el producto solo crea raíces (§5.2, P-09). Un nacimiento **con padre** de una clase de las escenas no entra en la generación, pero tampoco se descarta: es un **extra** (F2P-13), con el trato de la CE del punto 9 si su clase la crea la CE.
   - **Completa y disjunta (S-03):**
     - **completa:** cada fila del documento del apply está casada. Una fila sin nacimiento hace fallar la comprobación que juzga ese apply. Por ejemplo, P4b tiene que crear sus 33;
     - **viva (v1.3.11, F-06):** en **cada** apply positivo (P2, los dos de P3, los dos de P4a, P4b y el apply nuevo de P5), la generación completa está viva en el censo válido siguiente a ese apply, seguida por identidad, con la pose de §6 en los objetos. Una generación que nace y desaparece antes de su censo hace fallar la comprobación que juzga ese apply. P2n queda fuera, porque es la negativa;
     - **disjunta (v1.3.11, F-11):** los `net_id` son nuevos, nunca de otra generación **del mismo epoch**. La interfaz solo garantiza el `net_id` durante la sesión del servidor (`censo-interfaz-f03.md:39`), así que un `net_id` repetido en otro epoch es otra entidad y no rompe la disjunción. Que nada vuelva tras un reinicio lo juzga F2P-07;
     - **sin restos:** donde la parte exige que la generación anterior ya no esté (después de un reset), no queda ninguna entidad suya viva.
   - **Identidades (S-04):**
     - la identidad de una entidad es `(epoch, net_id)` (v1.3.11, F-11). El seguimiento no cruza un reinicio del servidor;
     - la generación se sigue después por esa identidad en las mediciones válidas, aunque la entidad se desplace;
     - **nunca** se vuelve a buscar por pose. Tampoco en P2n;
     - de las criaturas se comprueba la identidad y que estén vivas, **no su pose**, porque se mueven. La pose solo se compara en los objetos.
4. **Cobertura (O-07, R-04, R-07, S-02, S-12, V-08).**
   - **La unión:**
     - una medición de censo es la **unión** de sus trabajos: el disco principal, con etiqueta `<tag>`, y los discos por entidad, con etiqueta `<tag>:disk:<lid>`. Se ligan **por etiqueta**, no por cercanía en el tiempo;
     - se deduplica por `net_id`;
     - **cada componente** pasa la validación y la frescura del punto 1 frente al efecto que juzga. Si uno no las pasa, la medición entera da INCONCLUSO; nunca se omite en silencio.
   - **Quién la usa:** **todas** las comprobaciones, para posiciones, inventarios y el control: F2P-03, 05, 06, 07, 08, 10 y 12 incluidas. Ninguna lee un trabajo suelto. Tampoco el censo propio del control ni las búsquedas hacia atrás de F2P-10 (v1.3.11, F-08).
   - **Discos prescritos (v1.3.11, F-08):** cada componente lleva el centro y el radio de §5.2: el disco principal en (6170, 7643) con 115 m; el de cada criatura, centrado en su última posición válida, con 60 m para infectados y 120 m para animales; el del control, el de §5.3. Un componente con otros argumentos no vale, y la medición da INCONCLUSO. No basta con que la respuesta repita los argumentos pedidos.
   - **Contención:** «la unión cubre un disco» se comprueba contra la **unión** de los discos, no contra uno solo. Vale una rejilla de 0,5 m o un cálculo exacto.
   - **La última posición válida:**
     - sale de una medición válida (punto 1) **del mismo epoch** que la medición que muestra la ausencia;
     - la posición del documento **nunca** hace de posición observada (S-12);
     - sin esa posición, INCONCLUSO.
   - **Ausencia de un objeto:** se concluye solo si su última posición válida está dentro de la unión y a más de 15 m de su borde. Si no, INCONCLUSO `coverage_gap`.
   - **Ausencia de una criatura (R-04; v1.3.11, F-02):**
     - se concluye solo si **un único componente** de la unión, el principal o un disco, no la tiene y cubre el disco centrado en su última posición válida con radio `V_MAX · Δt + 2 m`, con Δt calculado al tick de **ese** componente. Los componentes se capturan en instantes distintos: la unión de varios no prueba nada, porque la criatura puede moverse entre capturas;
     - `V_MAX` = 7 m/s para infectados y 12 m/s para animales `[verify F2 en partida]`;
     - Δt es el `snap_tick_ms` de ese componente menos el tick de esa última posición (`snap_tick_ms` del censo o `tick_ms` del testigo), los dos del mismo epoch;
     - **el tipo** (criatura u objeto, y qué criatura) sale de lo observado, `ai_agent_b` en su última medición válida, y de la fila del documento con la que casó su nacimiento. **Nunca** del prefijo de un `lid` que informe el producto. Si se contradicen, INCONCLUSO `kind_mismatch`;
     - el runner toma, justo después de cada reset, un disco por criatura centrado en su posición de antes: 60 m para infectados y 120 m para animales (§5.2);
     - si no lo cubre, o los ticks son de epochs distintos, INCONCLUSO `coverage_gap`, que §7 admite con su motivo.
5. **Traza (O-11, R-10).**
   - **Correlación:** **cada** entrega, resultado y acuse se correlaciona en el `tap` con su identidad completa y con su orden en el reloj común. La identidad de una entrega es `(session, op_id)` con la `inst` y la `conn` de su op; la de un resultado, `(session, op_id)` con su peer, la `inst` de su query y el `epoch` de su cuerpo:
     - **cada resultado va después de una entrega previa** del mismo `(session, op_id)` y del mismo peer, con la `inst` entregada y el `epoch` de la orden. La conexión de un resultado es la de esa entrega (v1.3.15, K-01):
       - el `/result` del cable real no lleva `conn` (`DSBX_Peer.c:1497` y `:1505`);
       - el backend no la lee: acepta el resultado por la orden `(session, op_id)` de ese peer, la `inst` entregada y el epoch (`bridge.py:610-617`);
       - el oráculo no lee ninguna `conn` del `/result`: si un `tap` la trae, no cuenta ni para FALLA ni para PASA;
     - cada acuse va después de su resultado. En el mismo milisegundo vale: el `tap` estampa milisegundos enteros, y el proxy de F1b graba `/result` que el backend responde en el mismo ms (`req_id` 187 de la diag de F1b-peers del 15-nov) (v1.3.16);
     - en P2, la segunda respuesta va después de la segunda entrega.
   - **Emparejamiento por `req_id` (v1.3.14):**
     - cada respuesta del `tap` se empareja con la petición de su mismo `req_id` (§5.4); nunca por orden de llegada, por antigüedad ni por contenido;
     - un registro de `/hello`, `/poll` o `/result` sin `req_id`, una respuesta cuyo `req_id` no tiene petición y dos peticiones o dos respuestas con el mismo `req_id` dan **INCONCLUSO** (`missing`) en el check de su parte: esa traza no se puede juzgar. Fuera de las partes con check de traza (en P1, entre partes o después de P5), el problema da INCONCLUSO con el mismo motivo, igual que una violación de traza fuera de parte. Nunca se descarta en silencio (v1.3.15, K-02);
     - una petición sin respuesta no se juzga **como pareja**: no hay respuesta con la que compararla. Eso no la exime de las demás reglas. Un `/result` sin respuesta es un acuse que falta y rompe la traza por la regla de una resolución por entrega, más abajo, con la única excepción del resultado de la op cortada de P5 (v1.3.15, K-08).
   - **Identidad completa (v1.3.11, F-04):**
     - la sesión del query de una petición es la misma que la de su cuerpo;
     - la instancia y el epoch de cada resultado son los de su entrega;
     - la sesión vale solo si su `/hello` del producto fue **aceptado**: HTTP 200 con la sesión en la respuesta. Un `/hello` rechazado no abre sesión;
     - un desacuerdo en cualquiera de estas cosas rompe la traza.
   - **La conexión registrada (v1.3.14).** Cada `/hello` aceptado registra a su peer con la `inst` de la petición y la `conn` de la respuesta (`bridge.py:443-448` y `:470`). El registro de un peer en un momento dado es su último `/hello` aceptado de ese tramo. Rompen la traza:
     - un 200 de `/poll` a una petición cuya `inst` o cuya `conn` no son las del registro de su peer. El backend contesta 409 a esa petición, también si estaba retenida (`bridge.py:484-497` y `:520-523`). El registro se toma a la hora de la **petición** y tiene que ser el mismo a la de la respuesta: el backend evalúa la guarda al llegar (`bridge.py:506`) y contesta 409 si el registro cambia mientras espera (v1.3.15, K-03). **Empate de milisegundo (v1.3.16, C-02):** si la petición tiene el mismo `t_ms` que la respuesta de un `/hello` de su peer, valen los dos órdenes. La petición se admite si casa con el registro con ese `/hello` o sin él, y el registro a la hora de la respuesta, con el mismo criterio de empate, tiene que ser el mismo con el que casó. Es causal: el mod pone la `conn` nueva solo después de recibir la respuesta (`DSBX_Peer.c:992`), el backend registra antes de contestar (`bridge.py:442-471`) y el `tap` estampa milisegundos enteros;
     - una op entregada cuya `inst` o cuya `conn` no son las del registro del servidor. El backend solo entrega órdenes de la conexión registrada, con su `inst` (`bridge.py:536-537`, `:563-564` y `:575`). Si la entrega tiene el mismo `t_ms` que la respuesta de un `/hello` del servidor, valen los dos órdenes, como en la petición, pero uno solo: la entrega casa con el mismo registro con el que casó el `/poll` que la trae (v1.3.16, C-02);
     - un 200 con ops a una petición que no es del servidor: solo el servidor recibe órdenes (`bridge.py:557-559`).
     - **La `conn` se compara como la compara el backend (v1.3.15).** Se convierte con `int()` y vale si cumple la condición de la guarda (`bridge.py:484-489`):
       - `"01"`, `"001"`, `" 1"`, `"1 "` y `"\t1"` son la conexión 1;
       - `"+1"`, `"1_0"`, `" 01"`, `"01 "`, `"1.0"` y la cadena vacía no son ninguna conexión: el backend los rechaza con 400 y no casan con nada;
       - la `inst` y el `epoch` se comparan como texto exacto, como el backend (`bridge.py:495`).
   - **Las anclas de identidad (v1.3.14).** Una `inst` o un `epoch` vacíos no casan con nada, en ninguna comparación de la traza:
     - el backend rechaza con 400 un `/hello` cuya `inst` o cuyo `epoch` no son hex de 32 (`bridge.py:425-427`), y cada evento del `tap` lleva la `inst` y el `epoch` (§5.4);
     - un `/hello` aceptado sin `inst` no abre sesión ni registra a su peer;
     - una entrega, un resultado o una petición sin `inst` no casan con ningún `/hello`.
   - **Una sola resolución por entrega (S-07, V-15):** cada entrega tiene **una** resolución: su resultado y un acuse **aceptado**, HTTP 2xx con `ok` igual al booleano `true` (una cadena `"false"` o `"true"` no vale; v1.3.11, F-04). La excepción es el corte de P5. En P2, la segunda entrega tiene su resultado con `dup: true`.
   - **Rompen la traza:**
     - una respuesta de otra sesión o de otra conexión. Vale para las respuestas del backend, no para los resultados: un resultado no lleva conexión (v1.3.15);
     - un resultado de otra sesión, de otro peer, con otra `inst` que la entregada o con otro `epoch` que el de la orden;
     - un resultado sin entrega previa, o anterior a su entrega;
     - un acuse que falta o que se rechaza (`ok: false` o un HTTP que no es 2xx). Un `/result` sin respuesta es un acuse que falta (v1.3.15, K-08);
     - una entrega sin resolución;
     - un `op.state` sin su `/result` recibido.
   - **La única excepción es el corte de P5:** hay entrega y no hay resultado, por diseño.
     - **Las reentregas (v1.3.14, z91).** La excepción vale para **todas** las entregas de la identidad cortada que estén en P5, lleven el verbo del apply cortado y lleguen antes del `cut` o en el mismo instante. El backend reentrega a la misma conexión una op en curso sin resultado cada `retry_ms`, 2 s por defecto, mientras vive (`bridge.py:88` y `:563-568`). Una entrega de esa identidad después del `cut`, fuera de P5 o con otro verbo no queda exenta.
     - Si el producto reenvía el resultado de la op cortada al backend nuevo, el backend lo rechaza con `409 hello_required` o `400 bad_request`, porque la sesión ya no es la vigente (`bridge.py:592-593` y `:610-611`). Ese reenvío y su rechazo tampoco rompen la traza, y no cuentan como resolución. **Qué sesión lleva cada uno (v1.3.16, T2f-15l, D-04):** el mod pone en el query su sesión vigente, nunca vacía, y en el cuerpo la de la orden (`DSBX_Peer.c:1483`, `:1494` y `:1497`). El `409` sale cuando el query no está en la sesión del backend nuevo (`bridge.py:592-593`): un reenvío anterior al `/hello` nuevo, con el query en la sesión vieja, la del cuerpo. El `400` sale con el query en la sesión vigente y el cuerpo en la vieja (`:610-611`). Ese es el único desacuerdo entre query y cuerpo (`:562`) que no rompe la traza: un `409` con el query en otra sesión que la del cuerpo, o un `400` con el query fuera de la sesión del tramo del backend nuevo (el que abre su `restart`, §6.1 punto 2, `:346`), no lo produce el sistema real y rompe la traza, también si ese query es igual al cuerpo. El mod solo conoce esa sesión por la respuesta del `/hello` nuevo, que llega después del `restart`.
     - **Alcance de la excepción (v1.3.11, F-04):** vale solo para el `(sesión, op_id)` de la op cortada, después del `cut`, en el tramo del backend nuevo y con el rechazo. Un resultado rechazado con otra identidad, en otro momento o en otro tramo rompe la traza. Por ejemplo, uno de una sesión desconocida en P2 cuyo `op_id` coincide con el de la futura op cortada. **El reenvío que espera en el `tap` (v1.3.16, T2f-15m, H-02):** un reintento pedido después del `cut` y antes del `restart` del runner puede esperar en el `connect` del `tap` (`fault_proxy.py:734`, hasta 5 s) y llegar al backend nuevo, que lo rechaza con `409 hello_required` porque el query lleva la sesión que muere (`bridge.py:592-593`). Pasa en las capturas reales por ese mismo camino, con un `/poll`: el `req_id` 424 de la diag de F1b-peers del 15-nov, un `/poll` del servidor con el query en la sesión que muere, se pidió 257 ms antes de la primera respuesta del backend nuevo y lo contestó él, con un 409. En las cuatro capturas no hay ningún `/result` reenviado así, pero el `/result` pasa por el mismo `tap` y por la misma comprobación del query (`bridge.py:592-593`). Lo que sitúa ese rechazo en el tramo del backend nuevo es su respuesta, posterior al `cut`, no la hora de su petición: el `/result` de la identidad cortada pedido después del `cut` y rechazado con `409` o `400` por el backend (no por el `tap`: `upstream_status` ausente o un entero distinto de 0) después del `cut` es este reenvío, aunque su petición sea anterior al `restart` o a la primera respuesta del backend nuevo. Vale para él `:562` con `:588`.
     - **El resultado de la op cortada en el corte (v1.3.15 y v1.3.16, K-08).** El backend muere en el corte (`:497` y `:614`). El mod reintenta el `/result` tras un error (`DSBX_Peer.c:826-849`; 250 ms de base y hasta 4 fallos, `DSBX_Const.c:30` y `:46`). Un `tap` como el proxy de F1b contesta él mismo cuando el backend no está (`fault_proxy.py:798-808`). Por eso la excepción cubre, en una ventana:
       - **qué:** el `/result` de la identidad cortada de P5 y sus reintentos, con el mismo `(session, op_id)`. El primero, mandado **hasta el `cut`** o en el mismo instante: uno mandado después del `cut` no está en vuelo en el corte y no abre la ventana;
       - **con qué respuesta:** ninguna, o el 502 del `tap`, reconocido por los tres campos a la vez: HTTP 502, `upstream_status` explícitamente nulo (§5.4) y el cuerpo exacto `{"ok":false,"error":"upstream_unreachable"}`. El backend nunca contesta 502. Cualquier otra respuesta que fabrique el `tap`, de otro modo de fallo o con otro cuerpo, no entra. El cierre sin respuesta del backend (HTTP 0, `upstream_status` 0 y cuerpo vacío; §5.4) cuenta como «ninguna» si no es anterior al `cut` (v1.3.16, T2f-15l). Su registro es la respuesta de su petición y va después de ella, como cualquier acuse (`:555`; v1.3.16, T2f-15m);
       - **hasta cuándo:** entran los reintentos mandados hasta la primera respuesta del backend nuevo en el `tap`, por la hora de la petición. Esa respuesta es la primera por su hora, no por su línea en el fichero, de las posteriores al `cut` cuyo `upstream_status` no es nulo ni 0, a cualquier petición y de cualquier peer. La ventana no se cierra en el evento `restart`, que es el registro del runner (`:346`): el reinicio solo se acredita con un `/hello` aceptado después (`:604`). Desde esa primera respuesta rige la regla de v1.3.11 (`:589`): el rechazo del backend nuevo;
       - **qué hace:** dentro de la ventana, esos `/result` no cuentan como resolución y no rompen la traza.
       - **Lo que no entra y rompe la traza:**
         - fuera de la ventana, o con otra identidad, un 502 rompe la traza con `ack_rejected`, y un `/result` sin respuesta, con `ack_missing`; si es un reintento que sobra frente a las entregas de esa identidad, con `extra_result`. También el de otra op que estuviera en vuelo en el corte;
         - un 502 del `tap` o un cierre sin respuesta a la identidad cortada cuya respuesta sea anterior al `cut`: el backend no estaba accesible, o soltó el `/result`, cuando tenía que estar vivo;
         - **el backend estaba vivo:** una petición mandada después del primer `/result` (por la hora de la petición, emparejada por `req_id`) y respondida por el backend antes del `cut`. Cuenta cualquier endpoint, `/catalog` incluido. Las respuestas que fabrica el `tap` y los cierres sin respuesta (`upstream_status` 0) no cuentan. Si la hubo, el `/result` no queda exento y rompe la traza como cualquier otro acuse: con `ack_missing` si no tuvo respuesta y con `ack_rejected` si tuvo el 502.
       - **Los empates de milisegundo** se resuelven como en la conexión registrada: valen los dos órdenes, pero cada par de eventos tiene uno solo, el mismo para todas las reglas, y la traza no se rompe si es admisible en uno de ellos. Una respuesta del backend en el ms del `cut` es anterior al `cut` (y cuenta para «estaba vivo» si su petición es posterior al primer `/result`) o posterior (y cierra la ventana), no las dos cosas a la vez. Con tres o más eventos en el mismo milisegundo, los órdenes de los pares tienen que formar un orden total, sin ciclos: un ciclo tampoco lo produce el sistema real. Los eventos del ms del `cut` se ordenan juntos: la traza vale si algún orden total de todos ellos, con el `cut` dentro y cada respuesta después de su petición, es admisible para todas las reglas. Si en ese ms hay más de cuatro eventos, además del `cut`, la traza da INCONCLUSO (`tap_tie_group_too_large`): no se espera en una partida (v1.3.16, T2f-15l).
       - **Si el cable real muestra otra cosa,** por ejemplo que el runner registra el `cut` después de matar el backend, saldrá como un FALLA falso reproducible y se tratará entonces.
   - **Sesiones (v1.3.9):** la traza se correlaciona dentro de cada sesión del backend (punto 2). Tras cada reinicio del backend, el peer recibe `409 hello_required` con la sesión vieja y repite `/hello`, que le da la sesión nueva. Ese `409` en un `/poll` no rompe la traza.
6. **Reconciliación (O-12, R-02, S-08, V-01).**
   - **Cuándo (v1.3.11, F-03):** tras **cada** reinicio del backend, los dos de P3, el de P4a y el de P5 tras el corte.
     - **El reinicio se acredita** con el evento `restart` del runner (`target: backend`) y con un `/hello` aceptado después, con una sesión distinta de la del tramo anterior.
     - Si no se acredita, la comprobación de esa parte da INCONCLUSO, porque el escenario no ocurrió. Esa comprobación es F2P-05 en P3, F2P-08 en P4a y F2P-09 en P5.
     - Si se acredita y falta la lectura, o va antes del `restart`, o en la sesión vieja, o después de la primera entrega de escena del tramo, es **FALLA**.
   - **La evidencia:** tras ese reinicio tiene que aparecer en el `tap`, **antes de la primera entrega de escena (`scene.apply` o `scene.reset`) del tramo nuevo**:
     - un `state.read` entregado al servidor del epoch vigente;
     - y su `/result` con `status: done` y una lectura **válida**: la que acepta el consumidor real, `_valid_read_compat` de `app/backend/scene_live.py:147` (que delega en `valid_scene_read`, `scene_plan.py:806`), con el tamaño del mundo del servidor y sin exigir `obs`. El oráculo usa ese validador tal cual, para no divergir del backend en ningún sentido;
     - el `epoch` de la lectura es el del `/hello` vigente, y su bloque `scene` lleva el `doc_id` de la orden;
     - `obs` es **opcional**: la lectura real de `state.read` no lo trae (`app/tests/fake_world.py:1053-1059`). Si viene, el validador lo comprueba. Una lectura `{}` no vale.
   - **El backend no emite ningún evento propio de reconciliación.** Lo garantiza que el bridge no entrega `scene.apply` ni `scene.reset` sin haber reconciliado (`app/backend/bridge.py:579` y `:687-699`), así que no se exige ningún evento.
   - **La lectura de reconciliación es una orden interna** (`rd-N`, sin `op.state`; punto 2) del backend **nuevo**: va en su sesión, después de su `/hello`.
   - **En P5, la op cortada no recibe estado terminal** (v1.3.9, corrige la v1.3.8): su backend muere en el corte, y el nuevo arranca con otra sesión y sin sus ops (`bridge.py:112`, `server.py:88-89`). El oráculo no lo exige. Lo que exige es la lectura de reconciliación de arriba, en la sesión nueva, antes de la entrega de `P5:apply2`.
7. **Ventanas del testigo (O-14, R-03, R-11, S-05, S-06, S-11, V-02, V-05).**
   - **Cuántas:** hay un testigo por cada operación:
     - P2 y P2n;
     - P3, apply1 y apply2;
     - P4a, los dos apply;
     - P4b;
     - P5, con dos: `P5:cut` y `P5:apply2`;
     - la ventana de control de P1.

     Su centro está en (6170, 7643) y su radio es de 120 m.
   - **Cobertura de la op, en el reloj común:**
     - la entrega del trabajo del testigo a la sonda va antes de la primera entrega de la op;
     - `entrega + window_ms` supera el último evento de la op que se juzga: en P2, las dos entregas y los dos resultados; en `P5:cut`, la entrega y el corte; en `P5:apply2`, la entrega y el resultado del apply nuevo.
   - **Filas:** su `tick_ms` cae dentro de `[start_tick_ms, start_tick_ms + window_ms]`, comparando ticks del mismo epoch.
   - **Páginas (S-11):** solo valen después del **cierre acreditado** de la ventana. La primera página tiene un `t_ms` mayor o igual que `entrega + window_ms` en el reloj común, y el trabajo acaba `done`.
   - **Exclusividad (S-06, V-02, V-05):**
     - los testigos no se solapan, y los censos tampoco: van en serie. El gestor de trabajos de la sonda responde `busy` mientras otro trabajo sin liberar use el mismo recurso (`DSBX_QA_Jobs.c:211-216`, #22);
     - dentro de un epoch, se comparan ticks;
     - entre epochs, el orden en el reloj común: el trabajo anterior se libera antes de que se entregue el siguiente;
     - si dos ventanas se solapan, INCONCLUSO.
   - Si falta una ventana o no cubre su op, F2P-13 da INCONCLUSO.
8. **Reinicios y epochs (O-10, R-09, S-10, V-07).**
   - **Un reinicio del servidor se acredita con tres cosas:**
     - el `server_epoch` del primer `/hello` después del reinicio, **distinto** del de antes;
     - el evento de reinicio del runner entre los dos;
     - el mismo `storage.id`.

     Sin eso, P4b y P4c dan INCONCLUSO.
   - **El epoch es por evento,** no por parte: cada evento de la sonda y del `tap` lleva el de la instancia que lo produjo o lo recibió. Una parte puede abarcar dos epochs; P4c, por ejemplo, hace el reset en e2 y reinicia a e3. El epoch del manifest de la parte no sirve para juzgar eventos.
   - **El `server_epoch` de la parte no es obligatorio (v1.3.12, Sol r4c).** Los manifests reales del arnés de F0.3 no llevan epoch, ni por parte ni en otro sitio (`diag_manifest.json` y `diag2_manifest.json`, en `C:\tmp\dsbx-f2p-t2d\_ref\`). El reinicio del servidor se acredita por el `/hello`. Si la parte lo trae, son 32 hex; si no, no falta nada. El contrato de evidencias y el evaluador dicen lo mismo.
9. **Ruido de la CE (H-6, H-10, R-12, S-13, V-17).**
   - El censo puede traer botín de la CE: `net_id` nuevos que no son de ninguna generación, también de clases de la escena (`Barrel_Yellow` aparece como botín en la zona).
   - Ninguna comprobación cuenta la diferencia entera entre dos censos. Se cuentan las generaciones (punto 3) y, como extras, solo los nacimientos que ve el testigo (F2P-13).
   - Las comparaciones entre censos (el segundo reset de P3, P3c y P4) usan solo las identidades seguidas: las propias, las ajenas y las de la escena 2.
   - El total de P5 sale de las generaciones, no de las clases nuevas frente a P1. Nunca se usa `spawn_tick_ms` de lo que crea el producto: la sonda lo deja a 0 (`DSBX_QA_X_Persist.c:1648-1659`, #22; V-03).
   - **Clases que la CE crea en la zona:** las que el censo de P1 trae fuera de toda generación. Para ellas, un extra o una reaparición que **no** se distingue del botín da INCONCLUSO `posible_botin_ce`, no FALLA (S-13). Los casos concretos están en F2P-07 y F2P-13.
   - **En todas las comprobaciones (v1.3.11, F-12):** el mismo trato vale en **cada** comprobación que cuenta extras o compara conteos: F2P-01, 04, 07, 08, 09 y 13. Un extra de una clase que crea la CE nunca da FALLA en una y `posible_botin_ce` en otra; da INCONCLUSO `posible_botin_ce` en todas, nunca PASA.
10. **Reloj común (R-03).**
    - Todos los `t_ms` de `samples/` salen del mismo reloj: el monotónico del proceso del runner, con un único origen por parte (§5.4). Eso incluye el `tap`, el backend, el bridge de la sonda y los eventos del runner (`cut` y los reinicios).
    - Los `t_ms` solo se comparan entre sí.
    - Los ticks del motor solo se comparan con ticks del mismo epoch.

#### Por comprobación
- **F2P-01:** el testigo de P2 ve nacer las 33 raíces que casan con el documento, con su multiconjunto de clases, y las 33 están en el censo posterior por el `net_id` del primer tick. La diferencia con P1 no tiene que ser exactamente 33 (punto 9).
- **F2P-02 (O-04, R-01, R-13):**
  - **Nacimiento.** Cada nacimiento cumple las dos condiciones siguientes. Sustituyen a la distancia 3D a `(x_doc, suelo, z_doc)` de la v1.3.4, que mezclaba el suelo del documento con el observado (R-13).
    - **En horizontal:** a **menos** de 0,5 m de `(x_doc, z_doc)`. El umbral es estricto: 0,5 m exactos no pasan (S-14). Todos los comparadores usan el mismo.
    - **Apoyado en el suelo (V-10):**
      - criaturas, `|pos_y_m − surface_y_m| ≤ 0,1 m`;
      - objetos, `|pos_y_m − surface_y_m| ≤ 2,0 m`, porque el origen de algunos modelos no está en el suelo: el `Land_Wreck_Ikarus` del mapa lo tiene a +1,291 m;
      - los dos umbrales, `[verify F2 en partida]`. T4 mide el desfase de cada clase, y la tabla puede afinar el umbral en una versión posterior;
      - la `surface_y_m` es la de la propia muestra 0: `g_Game.SurfaceY` en la x y la z de `EEInit` (§5.3).
      - Si la fila no trae `surface_y_m`, INCONCLUSO `surface_unbacked`.
      - La `pos_y_m` nunca hace de suelo.
  - **Criaturas:**
    - el salto en 3D de la muestra 0 a la 1 no pasa de `JUMP_MAX_M`;
    - el checkpoint del mod está a `JUMP_MAX_M` o menos de la muestra 1. Sale de la lectura real del producto (R-01): `read.obs` con `at = "checkpoint"` (§3.6), con filas `[lid, ci, x_mm, y_mm, z_mm, yaw_mdeg, gy_mm]` (`app/backend/scene_plan.py:868-880`);
    - sin trayectoria o sin checkpoint, INCONCLUSO.
  - **Objetos:** en el censo posterior, a menos de 0,5 m en horizontal y apoyados en el suelo: `|pos_y_m − surface_y_m| ≤ 2,0 m`, con la `surface_y_m` del censo.
  - **Q-05:** en un censo válido (punto 1), `alive_b = 1` y `ai_agent_b = 1`.
- **F2P-03:** el estímulo está acreditado (por el testigo o por la traza); el estado es el **terminal**, con el motivo de su variante (§5.5); y el censo lo confirma.
- **F2P-04:**
  - dos entregas del mismo `(session, op_id)`, correlacionadas (punto 5);
  - la segunda respuesta lleva `dup: true`;
  - el testigo de P2 ve 33 nacimientos, no 66;
  - la segunda entrega cae dentro de la retención, medida con `params.ttl_ms` del manifest. Si falta, INCONCLUSO; nunca «sin comprobar» (V-16).
- **F2P-05 (O-09):** tras **cada** reset (el primero y el segundo), con la generación de P3:
  - retenidas, solo las propias con contenido ajeno;
  - los ajenos y las tres entidades de la escena 2, intactos en:
    - `net_id` y clase;
    - **pose completa:** x, y, z a 0,05 m y yaw a 1°;
    - padre;
    - **inventario:** clases y `net_id` de los hijos, no solo el contador;
  - estado terminal `parcial/contenido_ajeno` en los dos resets;
  - **tras cada reset, las retenidas se recalculan desde cero** (v1.3.11, F-07): todas las propias presentes en el censo de después de ese reset se contrastan con el conjunto permitido completo, los contenedores con algo ajeno. No basta con que siga lo que quedó tras el primero. Una raíz de más de la generación de P3, como `1:201` en `P3:post_reset2`, es FALLA;
  - la reconciliación tras los dos reinicios del backend de P3 (punto 6);
  - sin ningún estímulo crudo de ajenos, INCONCLUSO, no FALLA (V-18).
- **F2P-06 (O-08, O-09):**
  - Tras la limpieza: 0 propias vivas de la generación de P3, y las tres de la escena 2 intactas con la misma comparación completa.
  - Los estímulos de la sonda, acreditados por sus respuestas crudas:
    - `per_spawn_raw`: cada ajeno con su `net_id`, y en el cargo con `obs_parent_net_id` igual al contenedor pedido;
    - `per_cleanup_qa`, llamada **sin discos** (§5.3): `cleaned_raw_n` igual al número de ajenos puestos. El control persistente todavía no existe en P3c.
  - **Lo declarado frente a lo observado (v1.3.11, F-07):** cada ajeno que la limpieza dice haber borrado falta en el censo válido de después. Si `cleaned_raw_n` cuadra pero un ajeno sigue vivo, como el `Apple`, es FALLA.
  - Sin estímulos, INCONCLUSO (V-18).
- **F2P-07 (O-10, R-09, S-13, V-09, V-11):**
  - **Los reinicios:** acreditados (punto 8).
  - **El control persistente:**
    - su creación se acredita con la respuesta cruda de `per_spawn_raw persistent_control` al empezar P4a, validada (punto 1): la clase, el `net_id`, la posición fuera de la zona y la marca pedida (§5.3). **La creación exige salud real con la marca** (§5.3 v1.3.10: lo que crea el QA lleva salud real). Una creación con `-1/-1` no acredita el control (v1.3.11, F-08). La lectura después del reinicio se juzga aparte, en su censo propio;
    - su censo propio pasa por la unión validada (punto 4), de la instancia y el epoch vigentes después de ese reinicio. Un censo de la instancia anterior no vale (v1.3.11, F-08);
    - reaparece después de cada reinicio, reconocido en su censo propio como dice §5.3;
    - si no reaparece, INCONCLUSO;
    - está **fuera** de la zona de F2, así que dentro de ella no se exime a nada por clase ni por salud (V-11).
  - **Nada de F2 reaparece:**
    - La «última posición conocida» de cada entidad de cualquier generación de F2 es la de la **última medición válida anterior al reinicio**, no la de nacimiento.
    - **FALLA** si aparece una entidad de su misma clase con la pose de esa última posición: a 0,1 m en x, y y z y a 1° en yaw. Es lo que restaura la persistencia.
    - **FALLA** también si la entidad es de una clase de la escena 1 a menos de 2 m de esa posición, aunque no case con el documento, siempre que la clase no la cree la CE en la zona (punto 9).
    - **INCONCLUSO `posible_botin_ce`** si la clase sí la crea la CE en la zona y la pose no es exacta. Nunca PASA.
    - **Las criaturas (v1.3.11, F-09):** se mueven, así que la pose no sirve. Cuenta cualquier criatura (`ai_agent_b = 1`) de una clase de criatura de las escenas de F2 en la zona, en el censo después del reinicio y antes del apply siguiente, sin umbral de distancia:
      - **FALLA** si su clase no la crea la CE en la zona (punto 9);
      - **INCONCLUSO `posible_criatura_ce`** si la crea. Nunca PASA.
      - M1 corta las criaturas de la CE con los `globals` a 0 (§5.3, `[verify F2 en partida]`), así que en una partida buena no debería haber ninguna.
- **F2P-08 (S-04):**
  - reconciliación (punto 6);
  - los mismos conteos;
  - los objetos, con la misma pose en 3D (x, y, z);
  - las criaturas, con la misma identidad y vivas, sin comparar su pose;
  - sin extras.
- **F2P-09 (O-13, R-08, R-11, S-05, S-09, V-03, V-04):**
  - **K** son los nacimientos de la generación del apply cortado (punto 3) en la ventana `P5:cut` **anteriores al corte** (v1.3.11, F-03). Tiene que ser mayor que 0; si no, INCONCLUSO `p5_sin_efecto`, porque el estímulo no ocurrió antes del corte (§6: «corte antes del primer efecto en P5»).
  - **Anterior al corte, con un ancla:** un nacimiento es anterior al corte si hay un `poll` de la sonda de la misma instancia con estas dos condiciones:
    - su `t_ms` en el reloj común (evento `poll` del bridge) es anterior al `t_ms` del `cut`;
    - `1000 · tick_s` (el tick que la sonda manda en ese `poll`, `DSBX_QA_Probe.c:872`, el mismo reloj que `NowMs()`, `:358`) es mayor o igual que el `tick_ms` del nacimiento.

    Así se comparan ticks con ticks y `t_ms` con `t_ms` (R-03). Los nacimientos posteriores al último `poll` de antes del corte no cuentan para K, pero sí para la generación cortada y para el total final.
  - **El reinicio del backend tras el corte** se acredita como dice el punto 6. Si no se acredita, INCONCLUSO.
  - **La generación del apply nuevo** sale de la ventana `P5:apply2`. Las dos ventanas no se solapan (punto 7).
  - **La op cortada** no tiene estado terminal, y no se le exige (punto 2). Lo que se exige es la lectura de reconciliación del backend nuevo, en su sesión, después de su `/hello` y antes de la entrega de `P5:apply2` (punto 6). Si falta, o va antes del `restart` o en la sesión vieja, FALLA.
  - **El corte:**
    - lo registra el runner como evento `cut` en `samples/backend.jsonl`, en el reloj común (§5.4);
    - cae después de la entrega del apply y antes de cualquier resultado suyo, que no llega;
    - no se compara con ticks del motor.
  - **Reconciliación:** la del punto 6.
  - **El total final:**
    - exactamente 33 entidades vivas, en correspondencia uno a uno con las filas del documento;
    - se cuentan las de **todas** las generaciones de P5, seguidas por identidad aunque estén desplazadas dentro de la cobertura;
    - si sobra alguna, FALLA (33 + K).
- **F2P-10 (O-17, R-06, R-17):**
  - cada borrado «confirmado» falta en la medición siguiente **del mismo epoch** que el borrado (puntos 1, 4 y 8);
  - la posición anterior que decide si esa ausencia es concluyente sale de una medición válida del mismo epoch (punto 1). Sin ella, INCONCLUSO; la posición del documento nunca la sustituye (S-12);
  - cada `delete_failed` sigue vivo;
  - el tick informado va desde la **primera** petición de ese borrado hasta su confirmación, con el mismo reloj.
- **F2P-11 (O-01):** los edificios de referencia, medidos en la diag de F0.3 (PR #22, `run_20261116T000915Z`, censo a 115 m de (6170, 7643)), por clase y pose, a 0,5 m y 2°:

  | Clase | x | z | yaw |
  |---|---|---|---|
  | `Land_Lunapark_Shooting_Gallery` | 6137,06 | 7643,80 | −128,64 |
  | `Land_House_2W01` | 6212,85 | 7644,65 | −138,33 |
  | `Land_City_Stand_Grocery` | 6137,23 | 7702,65 | 39,30 |
  | `Land_House_2B01` | 6184,06 | 7715,68 | −142,45 |

  Llevan `net_id` real, con la parte alta negativa, y `health_hp = -1`.
- **F2P-12:** sin cambios.
- **F2P-13 (R-08, S-13):**
  - el punto 7, más la definición de criatura de §6 (H-4);
  - los extras se cuentan con la correspondencia uno a uno del punto 3, **dentro de la ventana de su apply**: un nacimiento de una clase de la escena que no consume una fila libre del documento de ese apply es un extra;
  - **un objeto de más:**
    - FALLA si su clase no la crea la CE en la zona;
    - INCONCLUSO `posible_botin_ce` si sí la crea, porque no se distingue del botín (punto 9).

#### Mutantes, negativas y fixture
- **Sol r4 (v1.3.11):** cada F-nn y A-01 tiene su caso (mutante, negativa o variante positiva), que pasa en dos pasos:
  - **en rojo,** sobre el evaluador de `7ed2615`, da el resultado espurio que dijo Sol: PASA, o FALLA en F-11;
  - **en verde,** con el arreglo, da el estado y el motivo de esta sección.

  Las pruebas exigen el motivo, no solo el estado (F-13).
- **Conformidad con el cable real (v1.3.11, F-01 y A-01):**
  - `qa/fixtures/f2p_native_probe.json` guarda líneas reales de `diag_bridge.jsonl` y `diag2_bridge.jsonl` de F0.3, **copiadas como cadenas sin tocar**, con su fichero y su número de línea: los `hello`, `enq`, `deliver`, `poll` y `result` de sus trabajos de censo y de testigo;
  - una prueba las pasa por el parser del evaluador y comprueba que cada trabajo es válido y toma el epoch de su lectura de arranque;
  - la fixture sintética sigue las mismas formas: páginas sin `server_epoch`, `result` sin `inst` y `pages_n = 0` con 0 filas.
- **Cronología de la fixture (v1.3.11, F-14):**
  - los discos van en serie, con `snap_tick_ms` crecientes;
  - cada lectura de reconciliación pide el documento vigente del backend (`app/backend/scene_live.py:320`);
  - `P5:cut` trae las muestras 1…K de sus nacimientos;
  - hay `poll` de la sonda con `tick_s` antes y después del corte.
- **Cada contraejemplo de Sol r1 que hoy da PASA** pasa a ser un mutante, con la comprobación que tiene que tumbar, o una negativa.
- **Los casos que hoy dan FALLA siendo una partida buena** pasan a variantes positivas que tienen que dar PASA:
  - `legitimate_fresh_P3_generation`;
  - `normal_opstate_transitions_before_terminal`;
  - `good_creature_tracked_by_extra_disk`;
  - `33_correct_roots_plus_background_Apple`.
- **`H4_control_creature_AI_initializes_at_tick1` no es una partida buena** (errata de la v1.3.4, corregida en la v1.3.6).
  - Lleva una criatura de más en P3, con la IA inicializada en el tick 1, y una criatura en la ventana de control.
  - Por F2P-13 (§6) tiene que dar **INCONCLUSO**, con F2P-13 en `missing`: ni FALLA, que es lo que daba con el `ai_agent_b` de la muestra 0, ni PASA.
  - Lo mismo vale para cualquier criatura de más cuando la ventana de control tuvo criaturas.
- **O-16 y R-16:**
  - la negativa de procedencia **copia de verdad** una observación del backend (`/api/observation`) como filas de la sonda, con valores que son aceptables en lo geométrico;
  - tiene que dar `unbacked_rows` por la procedencia;
  - va aparte del mutante geométrico de F2P-12.
- **Los ataques de Sol r2** (R-01 a R-17):
  - cada uno que hoy da PASA pasa a ser un mutante o una negativa, con la comprobación que tiene que tumbar;
  - los que hoy dan FALLA o INCONCLUSO en una partida buena pasan a variantes positivas que dan PASA:
    - R-01, con el checkpoint real;
    - R-02, sin el evento de reconciliación inventado;
    - R-03, con otro origen del reloj externo;
    - R-04, con borrados de criaturas;
    - R-12, con botín de la CE entre resets y antes de P5.
- **La fixture positiva tiene que ser una partida plausible:**
  - las referencias reales de F2P-11;
  - botín de la CE en los censos, también nuevo entre censos y de una clase de la escena (`Barrel_Yellow`);
  - `net_id` firmados y `hp = -1` en los edificios;
  - una generación con `net_id` nuevos por cada apply;
  - estados `pendiente` y después el terminal;
  - ventanas y páginas con tiempos coherentes;
  - reinicios con epoch nuevo;
  - los artefactos del arnés para la agregación (§7);
  - y, tras Sol r2 (R-15):
    - lecturas del producto válidas para los validadores reales (`_valid_read_compat` de `app/backend/scene_live.py:147` y `valid_world_read` de `app/backend/bridge.py:53`), con el checkpoint en `read.obs`;
    - testigos exclusivos, sin solaparse;
    - argumentos completos en las llamadas de arranque;
    - todos los nacimientos de cada apply dentro de su ventana, también los del segundo apply de P4a;
    - borrados de criaturas;
    - un único reloj (punto 10);
    - el censo de antes de cada reset;
    - el evento `cut` de P5;
  - y, tras Sol r3 y la pasada de Claude (v1.3.8; S-15, V-14):
    - **contra la sonda real:**
      - censos en serie, cada uno liberado antes de entregar el siguiente;
      - frames que crecen;
      - `rows_captured_n` igual a las filas;
      - ticks que vuelven a empezar en cada epoch;
      - `spawn_tick_ms` a 0 en lo que crea el producto;
      - la salud de §5.3 (v1.3.10): `-1/-1` en los `Land_*`; real y gastada en el botín de la CE; real en lo que crea el QA, con la marca exacta en el control (`Barrel_Yellow` 1300/1098,5); en lo que crea el producto, una variante con salud real y otra con `-1/-1`, las dos PASA; nunca `health_mark_pending`;
    - **contra el backend real:**
      - `state.read` sin `obs`;
      - la op cortada **sin** terminal (v1.3.9);
      - una sesión nueva por cada reinicio del backend, con el `409 hello_required` y el `/hello` que le siguen;
      - ids `op-N` sin ceros a la izquierda, que vuelven a empezar en cada sesión y se repiten;
      - lecturas internas `rd-N`, sin `op.state`;
      - el `op.state` inicial con `origin: "backend"` (`server.py:288`, `scene_live.py:371`);
      - el epoch de cada observación de la API, el de su lectura, es decir, el del mundo vigente (`scene_live.py:601-606`);
    - **la partida completa:**
      - P4c con sus dos epochs y su censo antes del reinicio;
      - P5 con sus dos testigos y los 33 nacimientos del apply nuevo;
      - el control persistente en P4a, fuera de la zona;
      - borrados de criaturas con sus discos de después del reset;
      - los censos antes de P2n y de P5;
    - **las pruebas:**
      - la de los validadores reales va en los dos sentidos: lo que el backend acepta no puede dar INCONCLUSO por la lectura, y lo que rechaza no puede pasar;
      - los mutantes del checkpoint editan `read.obs`;
      - los de `oracle_check` exigen `oracle_unverified`;
      - el de R-06 aísla la criatura objetivo y comprueba el motivo (S-16);
      - y, en la v1.3.9: una variante positiva con los ids de la API repetidos entre sesiones (`op-1` en P2 y otra vez en P4a), que tiene que dar PASA, y un mutante que toma el terminal de la op del mismo id de otra sesión, que no puede pasar.

#### Gate (O-15, H-7)
- **Una campaña por build** (diag y retail), cada una con una sola parte `run`. No hay parte `run-retail`.
- **Los mutantes de F2P son sin conexión.** `f2p_mutants.py` no exporta `EXPECTED_MUTANTS`: esa tabla del núcleo es para mutantes en partida, con `injection.json`, y no admite `missing` en `must_fail_checks`. La agregación de §7 se prueba con `aggregate_spike`.
- **El commit del oráculo es uno solo:** en el manifest, `identity.oracle_commit` (lo escribe `PartContext` con el commit ya verificado), `f2p.oracle_commit` y el commit del evento `oracle.frozen` son el mismo id de 40 hex. Si no, INCONCLUSO `oracle_modified`.
- **Y es el que verificó el gate (R-14):**
  - `evaluate(part_dir)` lee también `part_dir/../oracle_check.json`. Lo escribe el núcleo en la raíz de la evidencia antes de correr o evaluar nada (`qa/m1_gate.py`, el bloque de `--oracle-commit` de `main()`);
  - exige `ok: true`, y que su `commit` sea el mismo que esos tres;
  - sin ese fichero, INCONCLUSO `oracle_unverified`: un `f2p_eval` suelto no cuenta (§6);
  - las pruebas sin conexión lo escriben en su evidencia.

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
- **Un solo componente por criatura (v1.3.11, F-02):**
  - la ausencia de una criatura solo se concluye con un disco que la cubra en su propio instante;
  - si los discos van en serie y despacio (unos 4,4 s cada uno), las criaturas de los últimos discos pueden quedar en INCONCLUSO `coverage_gap`: a 7 m/s, 60 m cubren unos 8 s;
  - T4 toma el principal enseguida, porque con un Δt corto cubre la mayoría, y después los discos de las criaturas más cercanas al borde. Se mide en partida.
- **Criaturas tras un reinicio (v1.3.11, F-09):** si la CE cuela criaturas de las clases de las escenas pese a los `globals` a 0, F2P-07 da INCONCLUSO `posible_criatura_ce`, nunca PASA. Lo mide la ventana de control de P1.
- **El cable real (v1.3.11, F-01 y A-01):**
  - la conformidad se prueba con las dos diags de F0.3 del 16-nov;
  - si el #22 o un PBO posterior cambia las páginas, el `result` o los `poll`, se repite la prueba con una diag nueva antes de T4;
  - el ancla del corte depende de que el `poll` siga llevando `tick_s` (`DSBX_QA_Probe.c:872`).
- **P2n (P-04):** puede que ningún estímulo natural haga fallar al motor. Entonces la negativa del producto queda INCONCLUSA y se queda con los mutantes y con lo acreditado offline (F2b F2-A2).
- **El testigo de creación (P-03) y el control persistente (P-06)** dependen de F0.3. Sin ellos, T2 no se congela y P4b/P4c dan INCONCLUSO.
- **Limitación conocida (Q-02), para después de M1:** «sin extras» se acredita **dentro de la cobertura** del censo y del testigo, en modo de radio. Un huérfano nacido fuera de esa cobertura no se ve en M1. El testigo de mapa entero quedó fuera por decisión de la principal: era MAY, no BLOQ, y cada pieza de Enforce en la sonda cuesta una ronda de Sol, partida y riesgo.
- **Limitación conocida (Q-03), para después de M1:** en partida no se mete un objeto **registrado** de la escena 2 dentro de un contenedor de la escena 1, porque haría falta un traslado por `net_id` (`per_transfer`) que no entra en M1. Esa propiedad (P-02: lo ajeno es lo que está fuera del conjunto borrable de la operación) se acredita offline (F2b F2-A3 e), y en el código Enforce la cubren la revisión de Sol y la del Experto (§9.3). En partida se cubren el ajeno no registrado dentro de `obj-17` y las tres entidades de la escena 2 en el suelo.
- **Limitación conocida (v1.3.13, X-03), para después de M1:** M1 no juzga el reset de una escena aplicada cuyas entidades se fueron con un reinicio del servidor.
  - En P4c, la escena 2 sigue aplicada en el backend, sin entidades en el mundo desde el reinicio de P4b, y no se resetea (§5.2).
  - Que no vuelva lo juzga F2P-07 en P4b, con la regla de cualquier generación y pose exacta (§6.1).
  - En P4c no se juzga, porque el seguimiento no cruza un reinicio del servidor (§6.1, punto 3).
- **`globals` a 0:** no está medido si `ZombieMaxCount = 0` o `AnimalMaxCount = 0` afectan a las criaturas que crea el producto por script. Si F2P-02 encuentra criaturas muertas o sin IA solo con esos `globals`, se repite P2 con los `globals` originales y se anota.
- **TTL:** el plazo cuenta desde el envío del poll (F1b-peers). Un apply de 33 son unos 10 ticks `[verify S-perf]`.
- **Una orden a la vez en el mod:** las lecturas no se entregan durante un apply. Es coherente con el backend, porque la guarda «en vuelo» de C-01 sigue siendo válida.
- **`registry_sha256` opaco (DP-3):** no se puede verificar de forma independiente. Nadie lo consume.
- **El orden en la caja:** F2 va detrás de F1b-peers y de S-persist. Si S-persist cambia los flags o la vía de Q9, T3 cambia constantes y T2 no cambia.
- **BLOQ conocidos del oráculo congelado (22-nov, T2f-15m).** Tras las dos últimas rondas que dio Guillermo (T2f-15l y T2f-15m), el oráculo se congela sin FALLA ni INCONCLUSO falsos sobre evidencia válida y con tres PASA falsos del delta de T2f-15m, reproducidos por la decimosexta pasada de Claude y por el orquestador. Los tres necesitan evidencia que el sistema real (motor, backend, proxy o bridge) no produce; solo la daría una implementación rota. Por eso no vuelven a Guillermo como los de ancla de identidad (criterio de la principal, 22-nov), y la identidad `(sesión, op_id)` de la op cortada sí se comprueba. La revisión de Sol de T3 y de T4 los mira con esta lista:
  - **M-01:** un reintento del `/result` de la op cortada pedido entre el `cut` y el `restart`, rechazado con `400` y con el query en la sesión que muere (igual que el cuerpo), queda exento y da PASA. `:588` y `:589` lo prohíben, pero `_query_session_ok` (`qa/f2p_eval.py:1626-1634`) compara el query con la sesión del tramo de la petición, no con la del backend nuevo. El backend real contesta `409` a ese reintento antes de mirar el cuerpo (`app/backend/bridge.py:592-593`).
    - **Lo que mira la revisión:** que el `tap` de T4 graba el HTTP y el cuerpo del backend sin cambiarlos, y que el backend no cambia.
    - **Reproductor:** `C:\tmp\dsbx-f2p-t2f6\_ref\t2f15\orq_m\m01_400_query_sesion_que_muere.py`. Da PASA con el oráculo congelado y FALLA con el evaluador de `4744eaa`.
  - **J-01:** en ese mismo reenvío, un `upstream_status` que no es entero, nulo ni booleano (`0.0`, `409.0`, `"409"`, `"null"`, `[]` o `{}`) cuenta como respuesta del backend (`qa/f2p_eval.py:1620-1623`). `:589` pide el campo ausente o un entero distinto de 0, y `:339` añade el booleano. El proxy de F1b graba un entero o nulo (`fault_proxy.py:765` y `:798-808`).
    - **Lo que mira la revisión:** que el `tap` de T4 escribe `upstream_status` como entero o nulo.
    - **Reproductor:** `C:\tmp\dsbx-f2p-work\review\adv_t2f15m\scratch\c04_reenvio_upstream_no_entero.py`. De `a1` a `a6` dan PASA con el oráculo congelado y FALLA con `4744eaa`.
  - **J-02:** el `400` de ese reenvío con el query vacío o sin `session`, en un tramo sin `/hello` aceptado (un `restart` después de P5), da PASA: la sesión de ese tramo es `""` y casa. Según `:588`, el mod pone en el query su sesión vigente, nunca vacía, y no manda el `/result` sin sesión (`DSBX_Peer.c:1483` y `:1497`).
    - **Lo que mira la revisión:** que T3 conserva esa guarda del mod.
    - **Reproductor:** `C:\tmp\dsbx-f2p-work\review\adv_t2f15m\scratch\c05_reenvio_400_query_vacio.py`. Da PASA con el oráculo congelado e INCONCLUSO con `4744eaa`.
  - **PASA falsos de rondas anteriores (MAY), fuera del delta de su ronda.** Se añadieron el 22-nov, tras el congelado, para que la lista sea una sola. No se ha juzgado si el sistema real produce su evidencia:
    - **Y-05:** una op de más fuera del guion de §5.2 en una parte que no es P4c da PASA: un segundo reset fallido en P2n, P3c o P4a, o un segundo apply fallido en P4b. La regla de P4c (`p4c_reset_fuera_de_guion`) no se aplica en las demás partes.
      - **Lo que mira la revisión:** que el runner de T4 manda solo las ops del guion.
      - **Reproductor:** `C:\tmp\dsbx-f2p-work\review\t2f15r\bat_ref\t2f7\adv\y05_extra_ops_twins.py`. De `y05a` a `y05d` dan PASA con el oráculo congelado.
    - **A-04:** de la clase de Y-05, en P4c. Un segundo reset de la escena 1 con el terminal posterior al censo `P4c:post_restart` da PASA, porque Z-02 solo mide frente al primer reset.
      - **Lo que mira la revisión:** lo mismo que en Y-05.
      - **Reproductor:** `C:\tmp\dsbx-f2p-work\review\adv_t2f8\scratch\a04_p4c_second_scene1_reset_late_terminal.py` (`a04a` y `a04b`). Es anterior al `req_id`, y con el oráculo congelado da INCONCLUSO `tap_req_id_missing`, también en su control. **No está comprobado sobre el congelado.**
    - **C-05:** una línea del `tap` con el `t_ms` nulo o no finito se descarta en silencio. Unas ops entregadas al cliente con el `t_ms` nulo (`c03f`) dan PASA.
      - **Lo que mira la revisión:** que el `tap` y el runner de T4 estampan cada línea con un `t_ms` numérico y finito.
      - **Reproductor:** `C:\tmp\dsbx-f2p-t2f6\_ref\t2f15i\adv\c03_k02_fuera_de_parte.py` (`c03f`). Da PASA con el oráculo congelado.
    - **`c05e`** (MEN): dos `/hello` intercalados, del cliente y del servidor, con una sola respuesta aceptada que puede ser de cualquiera de los dos, dan PASA. Sale así porque el reproductor no trae `req_id`, y la batería se lo pone eligiendo uno de los dos emparejamientos. Con el `req_id` obligatorio del `tap` (§5.4) esa ambigüedad no se da.
      - **Lo que mira la revisión:** que el `tap` de T4 escribe en cada respuesta el `req_id` de su petición.
      - **Reproductor:** `C:\tmp\dsbx-f2p-work\review\t2f15r\bat_ref\t2f11\adv\c05_b03_orphan_hello_response.py` (`c05e`).

  El sha del congelado, los veredictos, los MAY y MEN de la ronda y las notas para T4 están en el recibo de congelado (`C:\tmp\dsbx-f2p-work\recibos\T2-congelado.md`).

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
- v1.3.5 (2026-11-16): F0.3 confirma `surface_y_m` en el testigo (#22), como última columna del `ncol`. Va en §5.3 y en F2P-02 de §6.1. Ninguna otra regla cambia.
- v1.3.6 (2026-11-16): **errata de la v1.3.4.**
  - El orquestador puso `H4_control_creature_AI_initializes_at_tick1` entre las variantes positivas que tenían que dar PASA. No es una partida buena: lleva una criatura de más.
  - Por F2P-13, con criaturas en la ventana de control, da INCONCLUSO (§6.1).
  - La regla de F2P-13 no cambia: era la errata la que la contradecía.
- v1.3.7 (2026-11-16): **arbitraje tras Sol r2** sobre el oráculo, que dio UNSOUND.
  - **Lo que encontró Sol:** O-01, O-02 y O-15 cerrados; el resto, parciales; 14 BLOQ nuevos (R-01 a R-14) y 3 MAY (R-15 a R-17). El orquestador los acepta todos.
  - **Huecos del brief, corregidos en §6.1:**
    - el checkpoint real está en `read.obs` (R-01);
    - la reconciliación se acredita con lo que el backend sí produce (R-02);
    - un reloj común, sin mezclarlo con los ticks del motor (R-03);
    - la ausencia de una criatura, con `V_MAX_CRIATURA · Δt`, más un censo antes de cada reset (R-04);
    - el corte de P5 lo registra el runner, y K es la generación cortada (R-11);
    - F2P-02, en horizontal más «apoyado en el suelo», en vez de la distancia 3D al suelo del documento (R-13);
    - el enlace con el commit que verifica el gate, por `oracle_check.json` (R-14).
  - **Reglas precisadas en §6.1 para los defectos del oráculo:**
    - la medición válida (R-05, R-06);
    - la cobertura en todos sus consumidores (R-07);
    - las generaciones uno a uno (R-08);
    - el control y la última posición (R-09);
    - la traza completa (R-10);
    - el ruido de la CE (R-12);
    - la fixture plausible (R-15);
    - la copia de verdad (R-16);
    - la primera petición (R-17).
  - **Para el runner (T4):** §5.2 añade el censo antes de los resets y el evento `cut`; §5.4, el reloj común.
  - **El cierre:** Sol ya no tiene más rondas. El congelado exige los ataques de r2 convertidos en pruebas y una revisión adversarial de otra familia (§6).
  - Nada de §3 (T1) ni de §4 (T3) cambia.
- v1.3.8 (2026-11-16): **arbitraje tras Sol r3 y la pasada adversarial de Claude,** las dos sobre `2865362` y las dos UNSOUND.
  - **Lo aceptado:** todos los S-nn (S-01 a S-16) y V-nn (V-01 a V-18). La tabla de decisiones, con su porqué, está en `C:\tmp\dsbx-f2p-work\recibos\arbitraje-r3.md`.
  - **Hechos de la sonda y del backend que comprobé yo:**
    - `spawn_tick_ms` vale 0 en lo que crea el producto;
    - `per_cleanup_qa` borra todos los registros crudos, y con discos barre clases de las escenas;
    - la marca de salud solo existe con sistema de daño;
    - el control de S-persist es un `Barrel_Yellow`;
    - `state.read` no lleva `obs`;
    - los terminales del backend.
  - **Cambios:**
    - **§5.2:** censos antes y después de cada reset, con discos por criatura; un censo antes de cada reinicio, de P2n y de P5; P5 con dos testigos;
    - **§5.3:** la limpieza va sin discos; el control persistente se crea en P4a, fuera de la zona y después de la limpieza;
    - **§5.4:** el epoch por evento y las etiquetas de los discos;
    - **§6.1, la base común:**
      - instancias y epoch en la medición válida (S-01);
      - los terminales del backend (S-09);
      - generaciones completas y disjuntas, con las criaturas por identidad y sin pose (S-03, S-04, V-06);
      - la unión con componentes válidos y la contención (S-02, V-08);
      - la última posición, sin el documento (S-12);
      - `V_MAX` por tipo (R-04);
      - una resolución por entrega y acuses aceptados (S-07, V-15);
      - la reconciliación, con el validador real del backend y `obs` opcional (S-08, V-01);
      - el cierre de las ventanas, y la exclusividad por epoch (S-11, S-06, V-02, V-05);
      - el epoch por evento (S-10, V-07);
      - el botín de la CE indistinguible da INCONCLUSO (S-13);
    - **§6.1, las comprobaciones:**
      - F2P-02, estricto a 0,5 m (S-14), con «apoyado» a 0,1 m en criaturas y a 2,0 m en objetos (V-10);
      - F2P-04, la retención (V-16);
      - F2P-05 y F2P-06, sin estímulos da INCONCLUSO (V-18);
      - F2P-07, el control fuera de la zona y la reaparición exacta frente a la CE (V-11, S-13);
      - F2P-08, sin pose de criaturas (S-04);
      - F2P-09, dos testigos y el terminal de la op cortada (S-05, S-09, V-03, V-04);
      - F2P-10, el mismo epoch y sin documento (S-12);
      - F2P-13, el botín de la CE (S-13).
  - **§6, «Revisión y congelado»:** Sol revisa siempre el código final, como mucho con una ronda más (r4). La pasada de otra familia es un extra.
  - Nada de §3 (T1) ni de §4 (T3) cambia.
- v1.3.9 (2026-11-16): **el reinicio del backend,** visto por el orquestador al revisar la salida de T2f-1, antes de Sol r4.
  - **Hechos del backend que comprobé yo:**
    - cada instancia del backend tiene su sesión (`app/backend/bridge.py:112`, `secrets.token_hex(8)`), y sus ops viven en memoria (`server.py:88-89`): un reinicio las pierde, y los ids vuelven a `op-1`;
    - una petición con la sesión vieja recibe `409 hello_required` o `400 bad_request` (`bridge.py:592-593`, `:610-611`);
    - las órdenes internas del bridge (`state.read`, `scene.observe` del checkpoint y compensaciones) llevan id `rd-N` (`bridge.py:234-236`) y no emiten `op.state`; solo las ops de la API lo emiten (`server.py:259`, `:297`; `scene_live.py:378`);
    - `_valid_read_compat` está en `app/backend/scene_live.py:147`, no en `scene_plan.py`, como decían las v1.3.7 y v1.3.8.
  - **Error de la v1.3.8 que corrijo:** exigía un terminal posterior a la reconciliación para la op cortada de P5 (puntos 6 y F2P-09, por S-09 y V-04). Es imposible: el backend que la emitió muere en el corte. Se retira esa exigencia. De S-09 queda el conjunto de terminales para las ops vivas.
  - **Cambios en §6.1:**
    - punto 2: la identidad de una op es `(sesión, op_id)`, la sesión de un `op.state` es la del tramo entre reinicios del backend, solo las ops de la API emiten `op.state`, y la op cortada no tiene terminal;
    - punto 5: la traza va por sesión, el `409` del `/poll` tras un reinicio no la rompe, y el reenvío rechazado del resultado cortado tampoco;
    - punto 6: la lectura de reconciliación es interna (`rd-N`) y del backend nuevo; la ruta del validador;
    - F2P-09: sin terminal de la op cortada;
    - la fixture y las pruebas: sesiones nuevas, ids repetidos, lecturas `rd-N` sin `op.state`, el `origin` inicial y el epoch de las observaciones.
  - Nada de §3 (T1) ni de §4 (T3) cambia.
- v1.3.10 (2026-11-16): **la salud en el censo,** con el contrato que mandó F0.3, dueño de la sonda, para #22 rebasado sobre #21.
  - **El contrato:**
    - `-1/-1` es «sin sistema de daño inicializado» (vanilla `object.c:974-976`);
    - lo que crea el QA lleva salud real, con la marca puesta y comprobada al crear, o la op da error;
    - `health_mark_pending` no existe;
    - el testigo no lleva salud.
  - **Medido por mí en las diags:** `Land_*` dan `-1/-1`; el botín de la CE da salud real y gastada.
  - **Cambios:**
    - §5.3, el censo: el contrato, y que ninguna comprobación depende de la salud de lo que crea el producto, que está sin medir;
    - §6.1, la fixture: la salud por tipo de entidad, con las dos variantes en lo que crea el producto.
  - **Pendiente en el motor (F0.3, en la diag de después del rebase):** que `WoodenCrate`, `Barrel_Green`, `SeaChest` y la gallina acepten la marca al crear.
  - Nada de §3 (T1) ni de §4 (T3) cambia.
- v1.3.11 (2026-11-16): **arbitraje de Sol r4,** sobre `7ed2615` (UNSOUND: F-01 a F-11 BLOQ, F-12 a F-14 MAY y F-15 MEN). Los acepto todos, más A-01, que encontré al comprobar F-01. La tabla y su porqué están en `C:\tmp\dsbx-f2p-work\recibos\arbitraje-r4.md`.
  - **Comprobado por mí en el cable real** (las diags de F0.3 y el código de `7ed2615`):
    - las páginas de `job_read` no llevan `server_epoch`, que solo va en la lectura de arranque (`DSBX_QA_Probe.c:1570-1578`; `censo-interfaz-f03.md:28` y `:121`);
    - el evento `result` del bridge de la sonda no lleva `inst`, aunque el bridge la valida (`qa/bridge_qa.py:833-836` y `:858-866`);
    - el `poll` de la sonda lleva `tick_s`, del mismo reloj que `NowMs()` (`DSBX_QA_Probe.c:872` y `:358`).
  - **Error de spec mío que corrijo (F-01):** la v1.3.4 pedía `server_epoch` en cada página. Con páginas reales, ninguna partida podía dar PASA.
  - **Cambios en §6.1:**
    - punto 1: la instancia de un `result` y el epoch de un trabajo, como los da el cable real; la conformidad con las diags (F-01, A-01);
    - punto 2: igualdad exacta y estado esperado por etapa (F-05); los reinicios del backend, P3 incluido;
    - punto 3: los hijos de clases de las escenas son extras (F-10); la generación viva en cada apply (F-06); la identidad `(epoch, net_id)` y la disjunción dentro del epoch (F-11);
    - punto 4: todos los consumidores usan la unión, con los discos prescritos (F-08); la ausencia de una criatura, con un solo componente y su Δt, y el tipo, de lo observado (F-02);
    - punto 5: la identidad completa en la traza, el `/hello` aceptado, `ok` booleano y el alcance del reenvío cortado (F-04);
    - punto 6: la reconciliación tras cada reinicio del backend, con el reinicio acreditado (F-03);
    - punto 9: el trato de la CE en todas las comprobaciones (F-12);
    - F2P-05 y F2P-06: las retenidas, recalculadas tras cada reset, y lo declarado frente a lo observado (F-07);
    - F2P-07: la creación del control con salud real y su censo de la instancia vigente (F-08); las criaturas tras el reinicio, sin umbral de distancia (F-09);
    - F2P-09: K, solo con nacimientos anteriores al corte, con el ancla del `poll` (F-03);
    - la fixture y las pruebas: los casos en rojo y en verde, la conformidad, y la cronología (F-13, F-14).
  - **§5.2:** el corte, después de un `poll` posterior al primer nacimiento; el reinicio del backend tras el corte; los discos, cada uno en su instante.
  - **§6, «Revisión y congelado»:** lo que dio r4 y cómo se cierra. Queda pendiente que la principal decida sobre un cierre de Sol limitado al diff de T2f-4.
  - **§10:** el riesgo de `coverage_gap` con un solo componente, las criaturas de la CE tras un reinicio y el cable real.
  - Nada de §3 (T1) ni de §4 (T3) cambia. El contrato de evidencias (`qa/f2p_evidence_contract.md`) se pone al día en T2f-4 (F-15).
- v1.3.12 (2026-11-17): **cierre de Sol r4 y pasada de Claude sobre T2f-4.**
  - **Sol r4c,** limitado al diff `7ed2615..bf498a5`: OK en su alcance. Fuera de él deja 3 MAY y 1 MEN.
  - **La pasada de Claude** sobre el mismo diff: UNSOUND, con 5 PASA falsos reproducidos (W-01 a W-05) y dos regresiones de T2f-4 (W-04 y W-07). El orquestador los volvió a reproducir sobre el candidato a congelar.
  - **La principal manda T2f-5 antes de congelar,** con su alcance, su método y su cierre (§6, «Revisión y congelado»).
  - **§6.1, punto 2 (W-11, decisión de la principal):**
    - en una etapa positiva, `observado` es exactamente `("observado", "")`;
    - `observado/reconciliada` quiere decir que se perdió el `/result`, salvo donde una etapa inyecte esa pérdida o una reconexión del mod, y hoy ninguna lo hace;
    - las citas del backend, comprobadas por el orquestador en `main` `2135f20`.
  - **§6.1, punto 8 (Sol r4c, MAY):** el `server_epoch` de la parte no es obligatorio, en la dirección de los manifests reales de F0.3, que no llevan epoch.
  - Nada de §3, §4 ni §5 cambia.
- v1.3.13 (2026-11-17): **P4c resetea solo la escena 1.** Es X-03 de la pasada de Claude sobre T2f-5, con la opción (a) que eligió la principal.
  - **Lo que había:** §5.2 pedía en P4c el reset de la escena 1 y el de la escena 2. La fixture del oráculo solo trae el de la escena 1, y el oráculo no exigía el de la escena 2.
  - **Por qué se quita:**
    - la escena 2 sigue aplicada desde P3c y pasa sin reset el reinicio del servidor de P4b, donde F2P-07 ya la juzga con la regla de cualquier generación y pose exacta (§6.1);
    - si el producto va bien, en P4c ya no queda nada suyo que borrar;
    - resetearla en P4c añadía a T4 dos reinicios del backend, a la escena 2 y vuelta, y el reset de una escena sin entidades, un resultado que ninguna regla juzga. Era limpieza, no una prueba.
  - **Comprobado por el orquestador** sobre el oráculo de T2f-5 (`0536ae4`), con `C:\tmp\dsbx-f2p-work\review\t2f5\repro\scene2_reappears_after_restart.py`:
    - los tres objetos de la generación de la escena 2, si reaparecen con la pose exacta de su última medición válida tras el reinicio de P4b, dan FALLA en F2P-07 (`reappeared`), tanto con su `net_id` como con uno nuevo;
    - tras el reinicio de P4c, la misma reaparición no se juzga: es la limitación de §10.
  - **El oráculo** juzga el terminal de cada reset de P4c que aparezca (T2f-6): un reset `fallido` en P4c nunca da PASA.
  - **Cambios:** en §5.2, la fila de P4c y su estado final; en §10, la limitación. Nada de §3, §4 ni §6.1 cambia. El runner de T4 sigue el §5.2 corregido.
- v1.3.14 (2026-11-17): **el `req_id` del `tap`, las anclas de identidad y el alcance de las reentregas del corte.** Lo decide la principal tras el cierre acotado que aprobó Guillermo.
  - **De dónde viene:**
    - de T2f-12 a T2f-15, el emparejamiento de peticiones y respuestas por orden o por contenido dio un PASA falso o un FALLA falso tras otro (D-02, G-01, G-04 y H-01 a H-05);
    - sin identidad de petición, un backend que cruzara las respuestas de la sesión vieja y la nueva deja el mismo `tap` que una partida válida;
    - la regla de la principal: un PASA falso por falta de ancla de identidad bloquea el congelado, aunque esté fuera del delta.
  - **Cambios:**
    - **§5.4:** el `req_id` de cada petición y de su respuesta, obligatorio para T4. El mecanismo ya existe en el proxy de F1b-peers, y la fixture se contrasta con sus partidas reales del 15-nov.
    - **§6.1, punto 5:**
      - el emparejamiento por `req_id`; sin él, INCONCLUSO;
      - la conexión registrada de cada peer (G-04 y H-01);
      - el 200 con ops solo para el servidor (G-01 y H-02);
      - las anclas de identidad (E-04: una `inst` vacía hacía pasar en vacío la comprobación del `/hello` de la misma instancia);
      - el alcance de la excepción del corte para las reentregas (z91 y H-04).
  - **Nada de §3, §4 ni §5.2 cambia.** El runner de T4 estampa el `req_id` en su `tap`.
- v1.3.15 (2026-11-18): **la traza, tras el cierre acotado de T2f-15** (Sol y la undécima pasada de Claude). Lo decide la principal.
  - **De dónde viene:**
    - **Sol:** la `conn` de `/poll` se comparaba como texto, y `"01"` o `" 1"`, que el backend acepta como conexión 1, daban FALLA. Era un FALLA falso dentro del delta.
    - **K-01:** el `/result` del mod real no lleva `conn` (`DSBX_Peer.c:1497` y `:1505`), y el oráculo comparaba la ausente con la de la entrega. Daba FALLA con el cable real: un FALLA falso sobre evidencia válida.
    - **K-02:** un problema de `req_id` en P1, entre partes o después de P5 se descartaba en silencio. Era un PASA falso.
    - **K-03:** el registro del peer se miraba a la hora de la respuesta, y un `/poll` retenido que llegaba con una identidad aún sin registrar pasaba. Era un PASA falso.
    - **K-08:** `:551` y `:569` de la v1.3.14 parecían contradecirse para un `/result` sin respuesta.
  - **Cambios, todos en §6.1, punto 5:**
    - la conexión de un resultado es la de su entrega, y el oráculo no lee ninguna `conn` del `/result`; lo que no se afloja: `(session, op_id)`, el peer, la `inst` entregada, el `epoch` de la orden y el orden en el reloj común;
    - «otra conexión» rompe la traza en las respuestas, no en los resultados;
    - la `conn` se compara con la guarda del backend (`bridge.py:484-489`);
    - el registro del peer se exige a la hora de la petición y hasta la respuesta;
    - un problema de `req_id` fuera de parte da INCONCLUSO;
    - cómo se combinan «una petición sin respuesta no se juzga» y «un acuse que falta rompe la traza»: un `/result` sin respuesta es un acuse que falta, con la excepción estrecha del resultado de la op cortada de P5.
  - **Nada de §3, §4 ni §5.2 cambia.** El producto no cambia: el `/result` sigue sin `conn`.
- v1.3.16 (2026-11-18): **la traza, ajustada al mod y al `tap` reales** (duodécima pasada de Claude, sobre T2f-15f y T2f-15g). Lo decide la principal.
  - **De dónde viene:**
    - **C-02:** un `/poll` con la `conn` o la `inst` nueva, estampado en el mismo milisegundo que la respuesta del `/hello` que se la da, daba FALLA. Es causal (`DSBX_Peer.c:992`; `bridge.py:442-471`) y el `tap` estampa milisegundos enteros: un FALLA falso dentro del delta.
    - **C-03:** el proxy de F1b contesta él mismo 502 al `/result` en vuelo cuando el backend muere (`fault_proxy.py:798-808`), y el mod lo reintenta (`DSBX_Peer.c:826-849`). Con un `tap` así, la carrera del corte que K-08 quería cubrir daba FALLA `ack_rejected`.
    - **C-04:** «estaba vivo» admitía dos lecturas: la hora de la petición posterior o la de su respuesta.
    - **Verificación de T2f-15i (orquestador):** la ventana se cerraba con la primera respuesta del backend en el fichero, no en el tiempo. Con la línea del 409 fuera de orden, un reintento con 502 fuera de la ventana daba PASA: un PASA falso dentro del delta.
    - **Confirmación acotada de T2f-15h/i/j (Sol y decimotercera pasada de Claude):**
      - un `/result` exento por sobrar, en la ventana o por el reenvío de la v1.3.11, no pasaba por las reglas de resultado. Daba PASA con otra `inst`, otro `epoch`, otro peer o sin anclas;
      - el 502 del `tap` aceptaba `ok` igual a `0`, y un cuerpo que no es objeto dejaba el `/result` «sin respuesta»;
      - un mismo empate se resolvía en un orden para una regla y en el contrario para otra (precisión del orquestador, confirmada por la principal: un solo orden por par de eventos, como en C-02; con tres o más eventos en el mismo ms, los órdenes forman un orden total, sin ciclos);
      - un acuse en el mismo ms que su `/result` daba FALLA. El proxy de F1b lo graba con el backend real: era un FALLA falso sobre evidencia válida.
  - **Cambios:**
    - **§5.4:**
      - `upstream_status` en cada respuesta del `tap`, obligatorio para T4. Sin el campo, la respuesta cuenta como del backend;
      - el orden de las líneas del `tap` no es el de su hora, y el oráculo mira la hora.
    - **§6.1, punto 5:**
      - el empate de milisegundo con un `/hello`, en la petición y en la entrega, frente al registro: valen los dos órdenes, uno solo por par de eventos;
      - la ventana del resultado de la op cortada: sin respuesta o con el 502 del `tap`, hasta la primera respuesta del backend nuevo;
      - «el backend estaba vivo», con una sola lectura: la hora de la petición y la respuesta del backend;
      - un acuse en el mismo ms que su resultado vale (`:555`).
  - **Nada de §3, §4 ni §5.2 cambia, ni la fixture.** El producto no cambia. El `tap` de T4 guarda el `upstream_status`, como el proxy de F1b.
- Congelado del oráculo (2026-11-22, T2f-15m): **sin cambios de semántica;** la v1.3.16 sigue vigente. Se añaden los BLOQ conocidos M-01, J-01 y J-02, con su reproductor (§10), y se precisa en `:589` que el `req_id` 424 de las capturas reales es un `/poll`. Las líneas de antes de §10 no se mueven, porque el código las cita.
- Tras el congelado (2026-11-22): se añaden al final de §10 los PASA falsos MAY de rondas anteriores (Y-05, A-04, C-05 y `c05e`), para que la lista sea una sola. Sin cambios de semántica ni del oráculo.
- T3 (2026-11-22): el mod núcleo de la escena viva (§4), de Gemini 4 Neon (`agy`, `gemini-4-neon-high`).
  - Los ganchos de F1b-peers (§4.2) se acordaron con la principal el 22-nov. El #19 está mergeado y no tiene sesión activa.
  - Las constantes de §4.4 se cotejaron con el veredicto de S-persist (#21, `90c6d6b`) y no cambian: `FLAGS_ROOT` = `FLAGS_STATIC` y `FLAGS_CREATURE` = `FLAGS_AI_A`, por la vía (a) de Q9.
  - El write-set de T3 (§8) suma `app/tests/test_mod_static.py`, que lista el árbol exacto de ficheros del mod (M1). Es un arreglo del orquestador.
- **Precisiones de contrato de T3 (2026-11-22; decisiones de la principal, con revisión de Argon):**
  - **Clases con `scope = 1` (T3-01).** El mod (`DSBX_SceneOps.c`) y el catálogo de F1b-peers (`DSBX_Catalog.c`) aceptan las clases de `CfgVehicles` con `scope >= 1`. Las de `scope = 0` siguen fuera.
    - Cambia el contrato de F1b-peers, que pedía `scope == 2` (`plans/2026-11-15-m1-f1b-peers-brief.md:328`). `DSBX_Catalog.c` pasa a ser el séptimo gancho de §4.2, y el texto para el Experto (§9.3) lo incluye.
    - **Por qué:** la escena 1 de M1 (`fixtures/escena-sin-actores.json`) lleva cinco clases con `scope = 1` que vanilla crea por script: `Land_Wreck_Ikarus`, `Land_Wreck_V3S`, `Land_Wreck_Volha_Blue`, `Land_Container_1Aoh` y `Land_Container_1Bo` (`P:\DZ\structures\wrecks\config.cpp:448-450` y `P:\DZ\structures\industrial\config.cpp:2258-2260`, entre otras). Con `scope == 2`, el backend responde 422 `unknown_class` y P2 no empieza.
    - **Alcance:** solo se amplía el catálogo del mundo (`Bridge.catalog`, el que sube `DSBX_Catalog.c` por `/catalog` para comprobar `unknown_class`). La biblioteca que ve la web (`fixtures/catalog-m1.json`, el `Store`) no cambia.
    - **Clases con `scope = 1` que no se pueden crear:** pasan la comprobación de existencia y fallan en la etapa de creación con `create_failed`, que se compensa (D8 y M12). Esto deja a mano la variante 1 de P2n (§5.5, `:356-358`).
    - **En T4:**
      - `/catalog` tiene más páginas, así que el runner espera a que acabe de subirse antes de cada `POST /api/apply`, tras el arranque y tras cada reinicio del backend (409 `catalog_pending`);
      - la partida comprueba que las cinco clases se crean sin errores en el RPT. Que pase el linter no lo demuestra.
    - Ningún test ni oráculo congelado afirma `scope == 2`.
  - **La posición tras crear y el predicado del checkpoint (T3-03).** El mod **no** hace `SetPosition` tras `CreateObjectEx`: §4.3 queda como está (`:198-202`).
    - **Por qué no:** el testigo toma la muestra 0 en `EEInit`, que corre dentro de `CreateObjectEx` (`:291` y `:422`). Un `SetPosition` posterior movería un modelo con el origen por encima de su base, como el `Land_Wreck_Ikarus` (+1,291 m, `:664`). Con el oráculo congelado, F2P-08 daría FALLA (`qa/f2p_eval.py:3815-3817` y `:3845-3847`) y F2P-12 daría INCONCLUSO `witness_not_final` (`:2952-2964`), que arrastra a F2P-02.
    - **El predicado del backend** (`check_apply_predicate`, `app/backend/scene_plan.py`) se alinea con §6.1 (`:660-665`, R-13 y V-10):
      - objetos: distancia horizontal menor de 498 mm y `|y − gy|` de 1998 mm como mucho (2000 mm menos el `EPS_Q` de D12);
      - criaturas: la distancia 3D, como hasta ahora.

      En los objetos es un cambio sobre F2 sin juego §4.3, punto 5 (`plans/2026-11-14-m1-f2-offline-brief.md:226`) y D12 (`:51`), que medían 3D.

      Lo implementa T3, con el OK de la principal para tocar esas líneas y `app/tests`. El oráculo congelado no cambia.
  - **P2n con el oráculo congelado (para las fixtures negativas y el runner de T4).**
    - **Todas las filas de P2n que llegan a crearse usan clases de `doc1`.** `_generation_rebuild` deja fuera de la generación los nacimientos de clases ajenas al documento (`qa/f2p_eval.py:1269-1271`). Con una clase ajena, F2P-03 (`:3162-3183`) y F2P-07 no verían ni su limpieza ni su persistencia, y un reset que no la borrara daría PASA. La excepción es la fila que falla en la variante 1: `CreateObjectEx` devuelve `null`, no hay nacimiento y `_generation_rebuild` no la ve.
    - **La variante 2** sigue siendo un desplazamiento que hace el motor (§5.5, `:355`); el runner no lo provoca. F2P-13 (`:4318-4320`) y `_generation_rebuild` (`:1278-1280`) casan los nacimientos con `doc1` solo en horizontal, a menos de 0,5 m. Por eso la variante 2 solo encaja si se cumplen las dos cosas:
      - el nacimiento queda a menos de 0,5 m en horizontal de una fila de `doc1` de su clase;
      - el checkpoint incumple el predicado: en un objeto, más de 1998 mm en vertical (por ejemplo, el motor lo apoya sobre un obstáculo); en una criatura, 498 mm o más en 3D.

      Un desplazamiento de 0,5 m o más en horizontal cuenta como extra en F2P-13 y da FALLA o INCONCLUSO (`:4341-4351`). Si el motor real no da un estímulo así, F2P-03 queda INCONCLUSO con su motivo (§5.5, `:363`), nunca PASA.
    - **La variante 1 basta para que F2P-03 dé PASA; la variante 2 no hace falta.** P2n aplica sobre la escena 1 viva de P2 (§5.2, `:246`), así que la etapa 4 borra antes la generación de P2 y ya hay efecto. Por eso una clase que no se puede crear se compensa dentro de la orden aunque vaya en la primera fila, sin pasar por M12 (`DSBX_SceneOps.c:1211-1215`). El mod deja `last.outcome = compensated` (`:1092-1098`) y el backend cierra la op en `parcial/compensada` (`app/backend/scene_plan.py:1112-1113`).
      - **La línea que lo decide:** T4 declara `p2n_variant = create_failed_after`, que espera `parcial/compensada` (`qa/f2p_eval.py:3108`), y F2P-03 lo compara en `:3143`.
      - **Ni F2P-03 (`:3105-3183`) ni F2P-13 (`:4259-4353`) piden nacimientos ni desplazamientos.** `_generation_rebuild` da `ok` con cero nacimientos (`:1288-1289`), y un testigo sin filas vale, porque la página 0 se exige siempre (`:359` y `:372-373`; `qa/f2p_evidence_contract.md:147-149`).
      - **La clase que falla va en la primera fila del documento,** que es la primera que se crea (`app/backend/scene_plan.py:249-252` y `:263-267`; `DSBX_SceneOps.c:1290`). Detrás de otras filas, la compensación borraría sus nacimientos sin que quepa un censo previo, y F2P-10 daría INCONCLUSO `no_position` (`qa/f2p_eval.py:4152-4156`).
      - **La clase tiene que estar también en la biblioteca web** (`fixtures/catalog-m1.json`) con su tipo, porque el Store valida contra ella las clases del documento (`app/backend/validate.py:304-311`). Si ninguna clase de la biblioteca hace fallar a `CreateObjectEx`, la variante 1 no se puede provocar en el juego: queda la variante 2 o el INCONCLUSO con su motivo (§5.5, `:363`).
    - **F2P-10:** cada borrado que se juzga necesita un censo previo de la misma parte y el mismo epoch, también en P2n y en P5. El runner lo toma, como ya pide el contrato del oráculo (`qa/f2p_evidence_contract.md:466`). En P5 son dos: uno antes de `P5:cut` (§5.2, `:259`) y otro entre el corte y la entrega de `P5:apply2`, con los nacimientos de `P5:cut` ya en el mundo, porque la etapa 4 del apply nuevo los borra (`DSBX_SceneOps.c:589-616`; `qa/f2p_eval.py:4138-4156`).
  - **`now` fuera de rango.** En la fila `now` de `scene.observe` (M15), una raíz viva cuya lectura se sale de los rangos normativos (F2 sin juego §3.6, `:150`) va como en el checkpoint (`:117`): la fila de nulos, con los contadores a 0.
    - Si se mandara la lectura, el backend rechazaría el resultado entero: `valid_obs_now_row` (`app/backend/scene_plan.py:776`) falla y `bridge.py:624-625` responde 400.
    - Es lo que ya hace T3 (`DSBX_SceneOps.c:356-359`).
- **Ronda 2 de la revisión de T3 (2026-11-22; Sol y la pasada de Claude sobre `c683f06`, arbitradas por el orquestador con el OK de la principal):**
  - **El apoyo de los objetos lleva el margen de D12 (N-05).** El checkpoint acepta `|y − gy|` de 1998 mm como mucho (`SUPPORT_TOL_OBJETO − EPS_Q`, `app/backend/scene_plan.py:1004`), igual que la distancia horizontal y la 3D usan `POS_TOL − EPS_Q` (`:987`; F2 sin juego D12, `plans/2026-11-14-m1-f2-offline-brief.md:51`). Las pruebas fijan 1998 y 1999 en los dos signos, la distancia horizontal euclidiana, los animales como criaturas y la medida 3D de las criaturas (`app/tests/test_f2_live.py`, `test_predicado_checkpoint_objetos_apoyo_y_criaturas_3d`).
  - **Un registro `0:0` cuya entidad ya no existe bloquea la escena (N-02, comportamiento conocido).** El mod no puede confirmar ese borrado por `GetObjectByNetworkId` (DP-6, `:71`) y para con `delete_failed` (`DSBX_SceneOps.c:811-816`), así que los reset y los apply fallan hasta reiniciar el servidor. El mundo falso, en cambio, quita el registro. Es fallar cerrado, a propósito: el oráculo no juzga un borrado sin posición observada en un censo anterior y da INCONCLUSO, no FALLA (`qa/f2p_evidence_contract.md:452-456`). Si sale en T4, el informe lo dice con su motivo.
  - **El TTL y el borrado en serie (N-03).** La línea de §10 «Un apply de 33 son unos 10 ticks» (`:944`) es anterior al borrado en serie. Un apply de 33 sobre una generación viva son ahora unos 33·L ticks más la creación, con L los ticks que tarda cada borrado en confirmarse (como mucho `DEL_CONFIRM_TICKS` = 10, `:223`). A 30 ticks/s y con L de 9 o más, se pasa del TTL de 10 s (`app/backend/bridge.py:88`). T4 mide L (F2P-10 da `delete_confirm_max_ms`) y el tick real del servidor, y con eso se decide si cambian `DEL_CONFIRM_TICKS`, el TTL o esa línea. Con L de 3 o menos y el servidor a 30 ticks/s o más, sobra margen.
  - **El texto para el Experto (§9.3) nombra también `DSBX_Catalog.c` (N-06),** el séptimo gancho (`scope >= 1`, en «Clases con `scope = 1`»), aunque la lista de `:904` no lo diga.
  - **A la lista, sin arreglo:**
    - un plan v1.2.2 vacío marcado F2 (`rows: []`, `classes: []` y sin columnas) se lee como un plan v1.3 vacío, que es válido. Por DP-2 el mod no distingue una columna ausente de una vacía (`:67`), y §3.8 rechaza las filas v1.2.2 (`:163`), que aquí no hay;
    - `rejected/result_too_large` después de publicar cambia `last` y la generación (`DSBX_SceneOps.c:1394`). Solo pasa con un `op_id` que el backend no emite: emite `(op|rd)-[0-9]{1,6}` (`app/backend/scene_plan.py:77`);
    - una entidad propia marcada para borrar en una orden anterior que no confirmó cuenta como ajena (`DSBX_Scene.c:753` y `:800-806`) y sale de los contadores de `now` (`DSBX_SceneOps.c:382`). Solo pasa tras un `delete_failed`, que ya hace fallar la partida. Lo tumbaría ver en T4 una entidad con `IsSetForDeletion` a 1 que no se borra;
    - un poll F1 con `args.at` de tipo objeto se invalida por el miembro tipado (`DSBX_Messages.c:49`). La ruta F1 canónica no cambia.
- **Enmienda de identidad: la sonda y el producto se casan por la vida del servidor (2026-11-23; descongela F2P).** Decisión de Guillermo, literal: «Sí, descongela F2P».
  - **El problema.** El oráculo congelado en `98c7a78` casaba la sonda y el producto por igualdad de ids:
    - la `inst` de cada trabajo de la sonda tenía que tener un `/hello` del producto en el `tap` con esa misma `inst` y el mismo epoch (`qa/f2p_eval.py:1005-1008`, con `_tap_epoch_for_inst` en `:757-774`);
    - el censo del control pedía la `inst` y el epoch del trabajo iguales a los del `/hello` vigente del producto (`:2581-2585`);
    - F2P-10 filtraba los censos por el epoch del producto (`_epoch_at`, `:4133-4142`).

    En el juego son UUID independientes. La sonda genera su `inst` (`qa/probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_Probe.c:264-274`, en la #22) y da como `server_epoch` esa misma `inst`. El producto genera su `inst` (`DayZSandbox/scripts/3_Game/DSBX_Peer.c:199`) y su epoch (`DSBX_World.c:34`). Con los ids reales, una partida honesta daba INCONCLUSO en todas las comprobaciones. Este brief nunca dijo que compartieran identidad (`:345`, `:480` y `:643`); la igualdad solo estaba en el oráculo.
  - **La regla nueva: casado por la vida del servidor.**
    - **Vida del servidor:** el tramo entre dos eventos `restart` con `target: server` del runner (§5.4), o entre el principio de la partida y el primero, y entre el último y el final, en el reloj común (R-03).
    - **Una identidad por lado y por vida.** En cada vida, el producto tiene una sola identidad (`inst`, `epoch`) en sus `/hello` aceptados del `tap`, y la sonda una sola (`inst`, `server_epoch`) en sus `/hello` aceptados y en las lecturas de arranque de sus trabajos. Un `/hello` repetido con la misma identidad no cuenta como otro: el producto vuelve a saludar tras cada reinicio del backend (P3, P4a y P5) sin cambiar de `inst` ni de epoch.
    - **Cada vida, identidades nuevas.** La identidad de cada lado en una vida es distinta de la de su vida anterior (en el producto, el epoch nuevo que ya pide `_server_restart_ok`, `:2209`).
    - **Cada trabajo de la sonda se ata a la vida en que se entregó,** y su identidad tiene que ser la de la sonda en esa vida. Para juzgarlo, su epoch es el del producto en esa vida.
    - **Si no casa, nunca PASA.** Si una vida tiene dos identidades distintas del mismo lado, le falta la de uno de los lados, repite la identidad de la vida anterior, o un trabajo de la sonda no cae en ninguna vida o no trae la identidad de la sonda de su vida, las comprobaciones que lo usan dan `missing` (INCONCLUSO).
  - **Verificación del re-congelado:**
    - un comparador caso a caso contra `98c7a78`, en el que solo pueden cambiar los casos del casado;
    - la reproducción con los ids reales de la sonda (distintos de los del producto) pasa de INCONCLUSO a PASA;
    - negativas nuevas que no pueden dar PASA: dos identidades del producto en una misma vida, y una vida sin la identidad de la sonda.
  - **Quién (E9).** El delta del oráculo lo escribe un subagente de Claude: ni Gemini, que implementó T3, ni Muse, que escribe el runner. Lo revisan Sol, solo sobre el delta y con el criterio de la partida automática, y una pasada de Claude; si el filtro corta a Sol, Argon. Después se vuelve a congelar.
  - **El validador del backend, en el mismo re-congelado** (decisión de la principal):
    - **Si no se puede importar, INCONCLUSO.** S-08 (el import de `app.backend.scene_live` en `qa/f2p_eval.py`) es la última condición de `_valid_read`, cuyo único uso es un requisito positivo de `_reconciliation_ok`. Con `except Exception: return False`, un import roto dejaba todas las lecturas como no válidas y daba FALLA en F2P-05 o F2P-08. Un import que falla es un error de montaje (p. ej. el oráculo corrido desde una copia sin `app/`), así que da INCONCLUSO con su motivo. Las excepciones del propio validador, ya importado, siguen contando como lectura no válida.
    - **`qa/tests/test_stdlib_only.py` admite esos imports, cerrados por módulo** (decisión de Guillermo, «Sí, en el re-congelado»): el evaluador solo `app.backend.scene_live`, y sus pruebas solo `app.backend`, `app.backend.bridge` y `app.backend.scene_live`. Esa prueba ya fallaba en el primer congelado (`98c7a78`), así que el recibo de este re-congelado tiene que traer la suite entera de `qa/tests` en verde, no solo la del oráculo.
- **Ronda 1 de la revisión del descongelado (2026-11-23; Sol, la pasada de DeepSeek V4.1 y la entrada real del gate sobre `38d0de4`, arbitradas por el orquestador).** Guillermo aceptó el delta de identidad de Claude con una revisión de Sol caso a caso (literal: «Aceptar el de Claude»). Sol y DS4.1 dan RED; los casos que cambian salen como manda la enmienda, y ninguno de los dos encuentra un PASA falso de identidad en la ruta automática. Tres bloqueantes ya estaban en `98c7a78` (B1, B3 y B4):
  - **El reinicio del servidor se juzga con el primer `/hello` posterior a su `restart` (B1).** `_server_restart_ok` tomaba el primer `/hello` aceptado de la ventana de la parte, aunque fuera anterior al `restart`. El mod vuelve a saludar en la misma vida cuando vence el lease (`DayZSandbox/scripts/3_Game/DSBX_Peer.c:882-899`; pasa en una partida retail de F1b, `evidence/m1/F1b-peers/retail-20261115T165243Z/logs/server_script.log:58-60`), y una partida honesta daba INCONCLUSO. Se compara el primer `/hello` aceptado posterior a cada `restart` del servidor con el último anterior a ese mismo `restart`.
  - **Si `P1:base` no vale, por la razón que sea, lo que depende de la base da INCONCLUSO (B3).** El guardián del delta solo saltaba si la vida de `P1:base` no casaba. Con una página perdida, el `/hello` del producto después de la entrega u otra razón, F2P-09 perdía la exención del botín de la CE y daba FALLA (`extras:`), y F2P-07 juzgaba sin base. Lo que depende de la base (las clases de la CE en la zona y sus `net_id`) da `missing`; los FALLA que no dependen de ella se conservan, también el terminal acreditado de la op en F2P-07, que el guardián tapaba (M2).
  - **La reutilización de `net_id` se mira dentro de una misma vida (B4).** El motor recicla los `net_id` al reiniciar el servidor: en una partida diag de S-persist (16-nov), el mismo `0:23230` es primero un `TShirt_White` y después un `Barrel_Red`. F2P-09 comparaba los `net_id` de P5 con los de la base de P1, de otra vida, y daba FALLA `reuses_baseline_nets`; y eximía filas de P5 por esa misma coincidencia. Se compara la pareja (vida, `net_id`): entre vidas distintas, un `net_id` igual no dice nada. La exención del botín por clase sigue usando las clases de P1.
  - **Los casos sintéticos repiten la build de la campaña (G-01).** Por la entrada real del gate, la positiva `id_sonda_rehello_misma_identidad` daba INCONCLUSO `build_mismatch`: el `hello` que añade la mutación (`_add_bridge_hello`, `qa/f2p_mutants.py:3007-3011`) fija `build: diag`, y el constructor del gate parte de la campaña en `offline`. Lo mismo, con el código esperado pero por ese motivo, en `id_sonda_dos_identidades_en_una_vida` y `r4_A01_result_other_inst`.
  - **Lo que la regla pide al runner (B2 de Sol; hallazgos 2 y 3 de DS4.1).** El `restart` del servidor se registra después de que salga el proceso viejo (con su volcado si cae, como `StopBoth` de F0.3) y de que el `tap` y el bridge de la sonda hayan registrado todo lo que tenían en vuelo del servidor viejo, y antes de arrancar el nuevo. En cada vida, el runner espera el `/hello` aceptado del producto y el `hello` de la sonda antes de entregar el primer trabajo. Si no lo hace, el oráculo da INCONCLUSO.
  - **La identidad de la sonda en sus `hello` es su `inst` (hallazgo 6 de DS4.1).** El `hello` de la sonda no lleva `server_epoch` (`HelloBody` en `qa/probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_Probe.c`, en la #22); su pareja (`inst`, `server_epoch`) sale de las lecturas de arranque de sus trabajos. Donde la enmienda dice (`inst`, `server_epoch`) en sus `/hello` aceptados, léase la `inst` en sus `hello` y la pareja en las lecturas de arranque.
  - **`qa/tests/test_stdlib_only.py` (M1 de Sol).** Un paquete de app no se admite como tal: en `from app.backend import X`, X cuenta como el submódulo `app.backend.X`. Las pruebas del oráculo importan `app.backend.scene_plan` (ya en `98c7a78`), `app.backend.bridge` y `app.backend.scene_live`; la línea anterior que dice `app.backend` se lee así.
  - **A la lista (§10), sin arreglo en esta ronda:** L1 de Sol, un `restart` del servidor de más tras el último trabajo de P5 deja una vida sin identidad y la partida en PASA (el guion automático no lo hace).
  - **Al backlog:** los MAY 4 y 5 de DS4.1 (tres casos de Sol con un `/hello` de otra identidad, que el juego no produce, pasan de FALLA a INCONCLUSO, y `r7_w11_ctrl_reconexion_servidor_con_hello` pasa a mutante) y sus MEN 7, 8 y 9 (un id mal formado del producto se ignora si su vida tiene otro válido; un `hello` de la sonda de otra vida da `probe_hello_missing`; cualquier excepción del import del validador da INCONCLUSO).
  - **Quién (ronda 2, la última).** Los arreglos del oráculo (B1, B3, B4, M2 y G-01), DeepSeek V4.1, autor del congelado; `test_stdlib_only` y estas precisiones, el orquestador. Revisan Sol y la pasada de Neon por `agy`: ni Claude, autor del delta de identidad, ni DS4.1, autor de los arreglos.
- **Ronda 2 y re-congelado del oráculo (2026-11-24).** Los arreglos los escribe DeepSeek V4.1, autor del oráculo (`a5216b8` y la ronda 2b); estas precisiones, el orquestador.
  - **Método (Guillermo, por la principal, 23-nov, literal «Sí, desde ya»):** manda la política de evidencia. No hay ronda 2 de Sol ni pasada de Neon, así que lo que dice `:1327` sobre quién revisa no se aplica. El oráculo se congela con evidencia ejecutable: cada hallazgo de la ronda 1, como test que falla con `38d0de4` y pasa con el arreglo; el comparador contra `38d0de4`; la entrada real del gate con todos los casos; una pasada de mutación; y la suite entera. La excepción de E9 del delta de identidad (literal «Aceptar el de Claude») sigue: su evidencia es esa misma, más la mutación de las guardas del casado.
  - **L1 se arregla en esta ronda,** porque el arreglo era directo (`:1325` lo dejaba a la lista). Si todas las comprobaciones pasan y una vida del servidor que solapa alguna parte de la campaña no casa, la partida da INCONCLUSO con `server_life_unbound`. Un reinicio fuera de las partes no abre una vida que haya que casar.
  - **Si `P1:base` no vale, el motivo es `baseline_unbacked`** en F2P-07 y F2P-09, también cuando la causa es que su vida no casa (antes, `server_life_unbound`). F2P-07 conserva `server_life_unbound` para la vida anterior a un reinicio que no casa. El veredicto no cambia.
  - **B4 en la partida automática.** P1 y P5 caen en vidas distintas, así que la reutilización de los `net_id` de la base no se puede ver en ella. Un `net_id` de la base que aparece en P5 es otra entidad: su `net_id` no la exime. La exención por clase sigue.
  - **Ronda 2b.** La pasada de mutación dejó vivos dos mutantes sin caso que los mate: la exención por `net_id` de B4 (una fila de P5 con un `net_id` reciclado de la base) y una vida con el `hello` de la sonda y sin `/hello` del producto (L1). DS4.1 añade una negativa para cada uno, sin cambiar el evaluador.
