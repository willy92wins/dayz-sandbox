# F2 sin juego: escena viva (aplicar, resetear y observar) sobre `dsbx1`, con el mod falso

2026-11-14 · tarea **F2-offline** (la parte de F2 que se hace y se prueba sin DayZ), rama `claude/f2-offline`, que sale de `claude/f1b-bridge` `a0fa14c` (F1bb con el gate en verde: 181 pruebas, E2E P1-P11, X3 17/17) más `7bede68`, que trae aquí la decisión de A3 (`e127ee7` de `claude/f0.3-briefs`) · spec de implementación (R25) de [plan v2](2026-10-26-m1-cine-v2.md) F2 (líneas 95-102), decisiones #9, #10 y #11 (31-33), #23 (45), #28 (50), Q9 (222), CX-01 (246) y CX-07 (252) · contrato: `DayZSandbox_dev/product-spec.md`, A1-A4 y A6 (47-50 y 52), C5 (78) y D2 (88) · protocolo: [F1b-bridge](2026-11-14-m1-f1b-bridge-brief.md) v1.4 (`dsbx1`) · reset y flags: brief de S-persist en `claude/f0.3-briefs` `6f88973` (`plans/2026-11-14-m1-f0.3-s-persist-brief.md`, §3.1 `:122-128` y §3.3 `:145-158`) · **v1.0, borrador para la revisión de Sol**.

**Por qué ahora.** F2 depende de F1 y de S-persist. F1 está a falta de los peers reales (F1b-peers) y S-persist no ha corrido. Todo lo que F2 puede fijar sin juego (el contrato de los verbos de escena, el backend y un mod falso con mundo) se hace ya, para que F2 en partida solo tenga que escribir el mod real y medir. Lo pidió Guillermo («Más frentes en paralelo»).

**La decisión de A3 (Guillermo, 2026-11-14), vinculante.** El reset nunca mueve lo ajeno, y lo ajeno conserva siempre su pose. Un contenedor de Sandbox con contenido ajeno dentro se queda en su sitio y no se borra; la operación termina `parcial`, con su motivo, y la web lo enseña. Sustituye a la extracción al suelo de la versión anterior de #10. Texto: A3 del spec (línea 49), #10 (32) y la fila A3 de §4 (153).

**Proceso.** Brief → revisión de Sol (`gpt-6.1-sol`, esfuerzo máximo, solo lectura), **2 rondas como mucho**, y después arbitra el orquestador → tandas delegadas (§9) → gate y X4 corridos por el orquestador → Sol sobre el código congelado. Sin lanzar DayZ.

## 0. Qué es y qué no

Es:
- el **contrato de los verbos de escena** sobre `dsbx1` (§3): `scene.apply` con su plan, `scene.reset`, `scene.observe` y el estado de la escena dentro de `state.read`. Lo cumplen el mod falso de ahora y el mod real de F2 en partida;
- el **lado del backend** (§4): plan ligado al hash, validación contra el mundo antes de mandar nada (A1, A6), predicados de apply y reset, generación, reconciliación de lo `parcial` y compensación;
- un **mundo falso** (`app/tests/fake_world.py`, §5) para el peer servidor del mod falso: entidades con inventario, suelo, registro de propiedad, censo independiente y fallos inyectables;
- en la web, lo mínimo para que A3 se vea (§6): la operación, el motivo y un botón de reset.

No es:
- **el mod real en Enforce**, ni el censo independiente en partida, ni el reinicio del servidor (§11). Van después de S-persist y de F1b-peers;
- lo que decide **S-persist** (flags de persistencia de #11, vía del checkpoint de Q9, qué reaparece tras reiniciar). Aquí va marcado `[verify S-persist]` y no bloquea;
- los **actores**, las prendas y los hijos que cree Sandbox (F3). El registro ya admite hijos, y las pruebas los inyectan para probar el reset (A3 «con hijos propios»);
- los **topes finales** (S-perf y F6). Valen los provisionales de #28: los `caps` de `fixtures/catalog-m1.json`.

Trazabilidad (R20): §2 y §3 salen de #9, #10, #11, Q9 y del protocolo `dsbx1`; §4, de #9, #10, #23, #28, A1, A6 y CX-07; §5, de #24 y de S-persist §3.3; §6, de la decisión de A3 y D2; §7, de A1-A4 y A6. Lo que no trace a esto no entra.

## 1. Entorno y fronteras

Como F1b-bridge §1: Python 3.14 en `C:\Python314\python.exe`, **solo biblioteca estándar** y `unittest`, comandos desde `DayZSandbox_dev/`, solo 127.0.0.1, ninguna clave en logs ni salidas, UTF-8 sin BOM con LF. En la web, solo las dependencias que ya fija `app/web/package.json`. El brief **añade**: una línea que no haga falta tocar no se toca (R20). No se tocan `qa/` ni la sonda.

## 2. Decisiones de diseño

| # | Decisión | Por qué |
|---|---|---|
| D1 | **Capacidad en el hello.** El peer servidor que cumple este contrato añade `"scene": 1` a su `/hello`. Solo con él el backend construye el plan y usa los verbos de §3; un peer sin él (los peers de prueba de F1b-bridge, el mod falso sin mundo y los peers reales de F1b-peers, que solo anotan la generación) sigue con el `scene.apply` de F1b-bridge §3.2. | F1b-peers llegará antes que el mod real de F2, y las 181 pruebas de F1 aplican la fixture con actores contra peers sin escena: tienen que seguir pasando **sin tocarlas**. `handle_hello` ya ignora campos de más (`bridge.py:347-397`). |
| D2 | **El plan lo construye el backend** a partir del documento congelado (`Store.freeze`, `store.py:124-137`) y viaja **entero en una sola orden**, con las clases indexadas. Lleva su propio `plan_sha256`, que el mod no recalcula: lo devuelve en la generación, y el predicado lo exige. «Por lotes» es la creación por ticks dentro del mod (#9), no páginas en el cable. | Medido con los formatos de §3.6 en el peor caso de los topes provisionales (§3.6): la orden ocupa 2549 B y el resultado más grande 3048 B, por debajo de `WIRE_CAP` (3500). Un plan que no quepa se rechaza antes de mandarlo (`plan_too_large`). Las páginas llegarán con F3, cuando los hijos y los actores hagan crecer las lecturas. Recalcular el hash en Enforce obligaría a imitar el JSON canónico de Python. |
| D3 | **Una escena con actores se rechaza entera** (`expansion_unavailable`) antes de mandar nada. | F2 cubre la escena sin actores (CX-01) y en F2 el mod no tiene motor de actores (`actor_engine: "none"`). Es el sentido de C5: nunca aplicar a medias. |
| D4 | **Tipos y topes salen de la biblioteca de M1** (`fixtures/catalog-m1.json`: clases por tipo y `caps` provisionales de #28). El catálogo del mundo (#8, `Bridge.catalog`) solo certifica que la clase existe en esa build y ese modset; su `base` no se usa en M1. Un `caps.total`, si existe, también se aplica. | #28 fija los topes provisionales en la fixture. El catálogo del mundo no dice cuánto se puede crear. `total` cubre la negativa de A6 «mezcla por encima del total» cuando S-perf lo fije. |
| D5 | **Lo borrable de una escena es todo lo registrado de esa escena en el epoch vigente**, raíces e hijos, de cualquier generación. La retención se calcula cada vez, con el algoritmo de S-persist §3.3 (`:145-158`): un registro con un descendiente que no es borrable se queda, y con él sus antepasados borrables. | Con apply = resetear y crear (#9), todo lo registrado de una escena es su generación viva más los restos de una compensación incompleta: así no queda nada huérfano. Lo de otra escena no es borrable (S-persist N43). |
| D6 | **Reset con algo retenido → `parcial` con el motivo `contenido_ajeno`.** El mod devuelve `done` y su lectura enseña lo retenido; el estado lo decide el backend a partir de la lectura, no de una etiqueta del mod. | Es la decisión de A3. Decidirlo con la lectura hace que el caso en que no se borró nada (solo había el contenedor retenido) también salga `parcial`, como dice A3. |
| D7 | **Apply con algo retenido en la generación anterior → rechazado sin efecto** (`foreign_content_retained`); la orden termina `fallido` con ese motivo. | Así la escena anterior no queda a medias. Una generación nueva junto a un contenedor viejo retenido daría duplicados en el censo (A4) y dejaría huérfano lo retenido. El usuario saca lo ajeno en el juego y vuelve a aplicar. |
| D8 | **Compensación en dos niveles.** Si falla una creación con el lease y el plazo vivos, el mod compensa en la misma orden: borra lo que creó esa orden, con la misma retención. Si se pierde el lease o el plazo, el mod para sin más efectos y deja lo creado marcado como pendiente; el backend lo ve en una lectura y manda la compensación (`scene.reset` con `if_pending`). | #9: «un fallo a mitad deja `parcial` y compensa solo lo de esa operación». Plan F2: la compensación de los parciales es del backend. `dsbx1` prohíbe efectos sin lease (F1b-bridge §2.4.6). |
| D9 | **Checkpoint (Q9) en el mismo tick de la creación**, antes de soltar la IA, y guardado en el registro. La observación «ahora» es otra lectura. | Q9 (4): infectados y animales se miden al crearlos, antes de soltar su IA. La vía exacta la decide S-persist `[verify S-persist]`. |
| D10 | **Altura `"ground"` resuelta al crear.** El documento no tiene `y` (`schemas/scene.schema.json`, `nonActorEntity`). El mod usa `gy = SurfaceY(x, z)` al crear, lo guarda y lo devuelve. El error de posición de A2 es la distancia 3D a `(x, gy, z)`. | Plan F2 línea 99. Mismo criterio que S-persist §3.2 `[verify S-persist]`. |

## 3. Contrato de los verbos de escena

Lo cumplen el mod falso con mundo (§5) y, en partida, el mod real. Todo lo de F1b-bridge §2 sigue igual: deduplicación por `(session, op_id)`, comprobaciones de la orden, lease y plazo antes de **cada** efecto, y `rejected` solo sin ningún efecto.

### 3.1 Hello

El peer servidor que cumple §3 añade `"scene": 1`. Cualquier otro valor, o su ausencia, es un peer sin escena (D1).

### 3.2 Estado del mundo y de la escena

Con un peer con escena, `state.read` lleva `args` `{doc_id}`: el `doc_id` del documento del backend. Su `read` es el de F1b-bridge §4 más `scene`:

```
{epoch, generation, registry_n, registry_sha256, scene: {doc_id, gen_n, n, retained_n, retained, pending, last}}
```

- `generation`: la generación **viva** de esa escena, `{session, op_id, rev, hash, plan_sha256}`, o `null` si no tiene ninguna publicada (nunca aplicada, reseteada o compensada). Es el campo de F1b-bridge con `plan_sha256` de más.
- `registry_n` y `registry_sha256`: todo el registro del epoch, todas las escenas. El hash es SHA-256 del JSON canónico de la lista ordenada de `[scene_id, lid, parent_lid|null, cls, gen_n]`.
- `scene.gen_n`: generaciones publicadas de esa escena en este epoch (entero ≥ 0). `scene.n`: registros de la escena, raíces e hijos. `scene.retained_n`: cuántos de ellos se quedaron en el último reset o compensación por tener algo no borrable dentro; `scene.retained`: sus `lid`, como mucho 16.
- `scene.pending`: `{session, op_id, n}` si un apply empezó a crear, no publicó y no está compensado del todo; si no, `null`.
- `scene.last`: la última orden de escena que tocó esta escena, `{session, op_id, verb, outcome}`, o `null`. `verb` es `scene.apply` o `scene.reset`; una compensación anota el `op_id` del apply que compensa. `outcome`:
  - `done`: terminó entera;
  - `retained`: terminó, pero quedó algo retenido;
  - `compensated`: un apply que falló y está compensado del todo;
  - `interrupted`: paró por lease o plazo.

El backend valida la forma: tipos de F1b-bridge §4 para lo de antes, y para `scene` `doc_id` como el del esquema, enteros ≥ 0, `retained` lista de textos con `len ≤ 16` y `≤ retained_n`, y `pending` y `last` con su forma o `null`. Un `read` sin `scene` de un peer con escena no vale (F1b-bridge §2.7).

### 3.3 `scene.apply`

`args` `{doc_id, rev, hash, plan_sha256, caps, classes, rows}`:
- `classes`: las clases distintas de las filas, ordenadas;
- `rows`: una fila por entidad no actor del documento, en el orden del documento, `[lid, ci, x, z, yaw]`, con `ci` el índice en `classes` y los números redondeados a 3 decimales;
- `caps`: `{objeto, infectado, animal}` de la biblioteca, más `total` si existe;
- `plan_sha256`: SHA-256 del JSON canónico (`sort_keys`, separadores `,` y `:`, UTF-8) de `{doc_id, rev, hash, classes, rows}`.

El tipo sale del prefijo del `lid` (`obj`, `zmb`, `ani`). Etapas, en este orden (#9):

1. **Validar**, sin efecto: forma (`lid` único y con el patrón del esquema, `ci` en rango, números finitos, `yaw` en [0, 360)) → si no, `rejected/bad_plan`; cada clase existe en el mundo → si no, `rejected/unknown_class`; `x` y `z` en [0, `world_size`] → si no, `rejected/out_of_map`.
2. **Reservar presupuesto**, sin efecto: cuentas por tipo ≤ `caps` y total ≤ `caps.total` → si no, `rejected/budget_exceeded`.
3. **Retención previa**, sin efecto: se calcula lo borrable de la escena (D5) y su retención. Si algo se quedaría → `rejected/foreign_content_retained`, con el `read` de §3.2 (D7).
4. **Resetear**, con efecto: borra lo borrable en dos pasadas, primero los hijos y luego las raíces (S-persist §3.3 punto 3). Al primer borrado, `generation` pasa a `null`.
5. **Crear**, con efecto: `pending` = esta orden, y sus registros llevan `gen_n` = `scene.gen_n + 1`. Por cada fila:
   - `gy = SurfaceY(x, z)`;
   - crea la entidad en `(x, gy, z)` con `yaw` y los flags de §3.7;
   - la registra con `{epoch, scene_id: doc_id, gen_n, op: {session, op_id}, lid, parent_lid: null, cls, gy}`;
   - en ese mismo tick, antes de soltar la IA, lee el checkpoint y lo guarda en el registro (D9).

   Va por lotes de `SCENE_BATCH` creaciones por tick `[verify S-perf]`.
6. **Publicar**, sin efecto en el mundo: `generation` = `{session, op_id, rev, hash, plan_sha256}`, `scene.gen_n` pasa al valor de sus registros, `pending` = `null`, `last` = `{…, verb: "scene.apply", outcome: "done"}`. El resultado es `done` con el `read` de §3.2 más `obs: {at: "checkpoint", rows}`, una fila por cada fila del plan (§3.6).

**Antes de cada efecto** (cada borrado y cada creación) se comprueban el lease y el plazo (F1b-bridge §2.4.6). Si fallan:
- antes del primer efecto → `rejected/<motivo>`;
- después → se para sin ningún efecto más, `last.outcome = "interrupted"` y `error/<motivo>`. Si ya había creaciones, `pending` sigue con esta orden.

**Si falla una creación** (la entidad no aparece), con el lease y el plazo vivos, el mod compensa en la misma orden (D8):
- borra los registros de esta orden con la retención de D5;
- si no queda ninguno, `pending` pasa a `null`;
- `last.outcome` = `compensated`, o `retained` si algo se quedó;
- termina en `error/create_failed`.

Una fila del checkpoint de una entidad que ya no vive lleva `ci = -1` y `x`, `y`, `z` y `yaw` a `null`.

### 3.4 `scene.reset`

`args` `{doc_id}`, o `{doc_id, if_pending: {session, op_id}}` para una compensación que manda el backend.

1. Con `if_pending`, si `scene.pending` no es esa orden → `rejected/not_pending`, sin efecto.
2. Lo borrable: con `if_pending`, los registros de esa orden; si no, lo de D5. Se calcula la retención (S-persist §3.3 punto 2).
3. Se borra lo borrable no retenido en dos pasadas (hijos y luego raíces), por lotes, con lease y plazo antes de cada borrado (§3.3).
4. Con `doc_id` solo: `generation` = `null`, `pending` = `null` y `last` = `{session, op_id, verb: "scene.reset", outcome}`, con `outcome` `retained` si algo se quedó y `done` si no. Con `if_pending`: `pending` = `null` si de esa orden solo quedan registros retenidos, y `last` = `{session, op_id del apply, verb: "scene.apply", outcome: "compensated"}` (o `retained`).
5. Resultado `done` con el `read` de §3.2, aunque haya algo retenido: el estado lo decide el backend (D6). Un segundo reset sobre una escena vacía es `done` sin efecto (A3: idempotente).

Nunca: borrar lo que no está en lo borrable (por radio, por clase o por parecido), mover algo, sacar lo ajeno al suelo ni tocar el storage.

### 3.5 `scene.observe`

`args` `{doc_id, at}`, con `at` `"checkpoint"` o `"now"`. Lectura sin efecto. Su `read` es el de §3.2 más `obs: {at, rows}`:
- `checkpoint`: las filas guardadas al crear la generación viva (§3.6), o `[]` si no hay ninguna viva;
- `now`: una fila por raíz registrada de la escena, con su estado actual (§3.6).

Un resultado que pasaría de `WIRE_CAP` → `rejected/result_too_large`, porque no hubo efecto.

### 3.6 Filas y tamaños

| Fila | Forma | Notas |
|---|---|---|
| plan | `[lid, ci, x, z, yaw]` | números con 3 decimales |
| checkpoint | `[lid, ci, x, y, z, yaw, gy]` | `ci` es el índice en `classes` de la clase leída (`GetType()`), o `-1` si no está o si la entidad no vive |
| ahora | `[lid, x, y, z, yaw, hp, n_own, n_foreign]` | `hp` en [0, 1]; `n_own`, descendientes registrados de la escena; `n_foreign`, descendientes no borrables |

Los números de las lecturas van redondeados a 3 decimales. Peor caso con los topes provisionales: 33 raíces con las clases más largas de `catalog-m1.json`, 32 clases distintas, números de 9 caracteres (`yaw` de 7) y 16 `lid` retenidos. Medido el 2026-11-14 con el script del orquestador `sizes3.py`:

| Cuerpo | Bytes |
|---|---|
| `/poll` con un `scene.apply` | 2549 |
| resultado de `scene.apply` con su checkpoint | 2815 |
| resultado de `scene.observe` `now` | 3048 |
| resultado de `scene.reset` o `state.read` | 942 |

### 3.7 Flags y lotes

- **Flags (#11) `[verify S-persist]`.**
  - Raíces: `ECE_PLACE_ON_SURFACE | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD | ECE_NOPERSISTENCY_CHAR` (29361188).
  - Infectados y animales: además `ECE_INITAI` (29363236), en la vía (a) de Q9.
  - Nunca `ECE_DYNAMIC_PERSISTENCY` (33554432).

  Son los valores de S-persist §3.1 (`:124-128`). `ECE_NOPERSISTENCY_CHAR` lo añade S-persist sobre el texto de #11.
- **`SCENE_BATCH` = 8** creaciones o borrados por tick `[verify S-perf]`.
- **Tolerancia de posición** `POS_TOL_M` = 0,5 m (A2).

## 4. Backend

### 4.1 Plan y validación antes de mandar nada (A1, A6)

`app/backend/scene_plan.py`: funciones puras, sin red.

`POST /api/apply`, con un peer servidor con escena (D1), después de `Store.freeze`. Valida **en este orden** y para en el primer código. Cada error lleva su JSON Pointer y la lista completa en `errors`. Ninguno crea orden, ni la mete en la cola, ni emite eventos:

| Código | HTTP | Cuándo | Pointer |
|---|---|---|---|
| `expansion_unavailable` | 422 | el documento tiene actores (D3) | `/entities/<i>` del primero |
| `catalog_pending` | 409 | `Bridge.catalog` no está completo | `""` |
| `unknown_class` | 422 | una clase que no está en `Bridge.catalog` | `/entities/<i>/cls` |
| `out_of_map` | 422 | `x` o `z` fuera de [0, `world_size` del hello] | `/entities/<i>/x` o `/z` |
| `budget_exceeded` | 422 | cuentas por tipo por encima de `caps` del catálogo del `Store`, o total por encima de `caps.total` | `/entities` |
| `plan_too_large` | 422 | la orden o la cota superior del resultado pasarían de `WIRE_CAP` | `""` |

La cota superior se calcula con los `lid` y los `ci` reales y números de 9 caracteres. Si todo pasa, la orden se encola con los `args` de §3.3. Sin bridge, o con un peer sin escena, `apply` hace lo mismo que en F1b-bridge.

### 4.2 Rutas nuevas

| Ruta | Quién | Cuerpo | Respuesta |
|---|---|---|---|
| `POST /api/reset` | solo la persona (403 si no) | `{doc_id}` | `{ok, op_id}`; 409 `doc_changed`, `scene_unsupported` (peer servidor sin escena) o `queue_full` |
| `POST /api/observe` | persona o IA | `{doc_id}` | `{ok, read_id}`; 409 `doc_changed` o `scene_unsupported` (sin peer servidor con escena) |
| `GET /api/observation` | persona o IA | — | `{ok, observation, age_ms}`: la última lectura `now` (`{read_id, doc_id, epoch, generation, rows, at_ms, origin: "servidor"}`) o `null` |

- **Pipeline:** las rutas nuevas pasan por el mismo camino que las de hoy: Host, Origin, CSRF y credencial (F1b-web §2).
- **Tabla `STATUS`:** recoge los códigos nuevos con el HTTP de §4.1.
- **Reset:** crea una orden de la API `{op_id, verb: "scene.reset", state: "pendiente", rev: null, hash: null, at_ms, origin: "backend", reason: null}` y encola `scene.reset {doc_id}`. Si aún no hay peer servidor, se encola igual: como en BR4, sin peer termina `fallido/no_entregada`.
- **Órdenes de apply:** conservan sus campos de hoy, sin `verb`, así que la web lee la falta de `verb` como «aplicar».
- **Cola:** `queue_full` cuenta `scene.apply` y `scene.reset`.
- **Observe:** encola una lectura interna `scene.observe {doc_id, at: "now"}`. Al llegar su resultado válido, guarda `Backend.observation` y emite el evento SSE `scene.observation` con el mismo objeto.

### 4.3 Predicados

**Apply** (vía directa y reconciliación, la misma función). Se cumple si se cumple todo esto:
1. el `read` vale (§3.2) y su `epoch` es el de la orden;
2. `generation` es `{session, op_id, rev, hash, plan_sha256}` de la orden;
3. `scene.pending` es `null`;
4. `obs.at` es `"checkpoint"`, y el conjunto de `lid` de `obs.rows` es exactamente el del plan, sin repetidos;
5. en cada fila, `ci` es el del plan, `x`, `y` y `z` no son `null`, y `dist3((x, y, z), (x_plan, gy, z_plan)) < POS_TOL_M`.

Así salen el multiconjunto exacto por clase, las 33 raíces y el error de posición de A2.

**Reset**, sobre un resultado `done`:
- `last` es esta orden con `outcome: "done"`, `scene.n == 0` y `generation == null` → `observado`;
- `last` es esta orden con `outcome: "retained"`, `scene.n == scene.retained_n > 0` y `generation == null` → `parcial/contenido_ajeno`;
- cualquier otra cosa → `fallido/lectura_no_cumple`.

### 4.4 Transiciones (se suman a F1b-bridge §3.1)

| Orden | De | A | Cuándo | `origin` | `reason` |
|---|---|---|---|---|---|
| reset | — | `pendiente` | `POST /api/reset` | `backend` | — |
| reset | `pendiente` | `ejecutando` / `fallido` | como un apply: entrega, TTL o cambio de `conn` | `backend` | los de F1b-bridge |
| reset | `ejecutando` o `parcial` | `aplicado` → `observado` | primer resultado `done` y predicado de reset limpio | `servidor` | — |
| reset | `ejecutando` o `parcial` | `aplicado` → `parcial` | primer resultado `done` con retención | `servidor` | `contenido_ajeno` |
| reset | `ejecutando` o `parcial` | `aplicado` → `fallido` | primer resultado `done` que no cumple | `servidor` | `lectura_no_cumple` |
| reset | `ejecutando` | `fallido` / `parcial` | primer `rejected` / primer `error` | `servidor` | el del peer |
| apply | `parcial` | `observado` / `fallido` | reconciliación: la lectura enseña su generación y el checkpoint (§4.5) cumple / no cumple | `servidor` | `reconciliada` / `lectura_no_cumple` |
| apply | `parcial` | `parcial` | su compensación termina (§4.5) | `servidor` | `compensada` o `contenido_ajeno` |
| apply | `parcial` | `parcial` | la lectura enseña `last` de esta orden con `compensated` | `servidor` | `compensada` |
| apply o reset | `parcial` | `parcial` | la lectura enseña `last` de esta orden con `interrupted` y nada pendiente de ella | `servidor` | `interrumpida` |
| reset | `parcial` | `observado` / `parcial` | reconciliación: `last` de esta orden con `done` / con `retained` | `servidor` | `reconciliada` / `contenido_ajeno` |

- **`parcial` resuelta:** un `parcial` con `contenido_ajeno`, `compensada` o `interrumpida` es terminal. La orden del bridge pasa a `terminal` y deja de contar como «`parcial` viva» (`_has_live_parcial_locked`), así que no se piden más lecturas por ella.
- **Lo de F1b-bridge sigue igual:** nunca hacia atrás; el primer resultado manda; un `parcial` de otro `epoch` se queda `parcial/mundo_reiniciado` y no se reconcilia ni se compensa (#10: sus referencias ya no valen).

### 4.5 Reconciliación y compensación (#9, #10, CX-07)

Con un peer con escena, cada lectura del mundo que reconcilia (F1b-bridge §4) pasa por `SceneLive.on_world_read_locked(read)`. Esa función sustituye la reconciliación de apply de F1b-bridge. Recorre, en el orden de la cola, cada orden de la API de esta sesión que esté en `parcial` sin resolver y sea del mismo `epoch` que la lectura. Su `conn` da igual: tras perder el lease, la orden es de la `conn` anterior y la lectura del mismo mundo sigue mandando, como en `_process_world_read_locked`. Para cada una:
- **apply con `generation` = su identidad completa** → encola `scene.observe {doc_id, at: "checkpoint"}`. Con su resultado aplica el predicado de §4.3. Si ese resultado enseña otra generación, la orden no cambia.
- **apply con `scene.pending` = su `(session, op_id)`** → encola la compensación `scene.reset {doc_id, if_pending}` (D8). Con su resultado `done`:
  - pasa a `parcial/compensada`, o a `parcial/contenido_ajeno` si quedó algo retenido;
  - un `rejected/not_pending` no cambia nada.
- **apply o reset con `scene.last` de esa orden** → transición de §4.4 según `outcome`.
- **Cualquier otra cosa** → sigue `parcial` y la lectura se repite (F1b-bridge §4).

Como mucho hay **una** orden interna de F2 en vuelo a la vez (observe o compensación). Son internas como `state.read`: no crean fila en la API ni `op.state`, se descartan al cambiar la `conn` y vuelven a pedirse con la siguiente lectura válida. Tampoco se entregan antes de reconciliar, igual que `scene.apply` y `scene.reset`.

Tras **reiniciar el backend**, las órdenes de la sesión anterior ya no existen (la cola vive en memoria, F1a). La primera lectura válida fija la base, y el siguiente apply resetea todo lo registrado de la escena aunque lo creara otra sesión (D5). Así no se duplica el mundo (A4).

### 4.6 Cambios en `bridge.py` y `server.py`

Solo los ganchos. La lógica de F2 vive en `scene_plan.py` y en `scene_live.py`.

En `bridge.py`:
- `handle_hello` guarda `scene` en el registro del peer;
- `_trigger_state_read_locked` y el reintento de `sweep` piden `state.read` con los `args` de §3.2;
- `handle_result` valida el `read` de los verbos de F2 (§3.2) y delega en `SceneLive` los resultados de `scene.reset`, `scene.observe`, las compensaciones y el predicado de un `scene.apply` con plan;
- `_process_world_read_locked` delega en `SceneLive` con un peer con escena;
- en `_pick_order_locked`, `_transition_conn_orders_locked`, `sweep`, `live_scene_count` y `_has_live_parcial_locked`, la comparación con `"scene.apply"` pasa a cubrir también `"scene.reset"` donde hace falta.

En `server.py`:
- `STATUS`;
- `Backend.apply` con el plan;
- `Backend.reset`, `Backend.request_observe` y `Backend.observation`;
- las tres rutas nuevas.

`set_op_state` no cambia.

## 5. El mundo falso (`app/tests/fake_world.py`)

Un `FakeWorld` en memoria, con su cerrojo, que el peer servidor del mod falso usa cuando se le pasa (`FakeMod(..., world=FakeWorld(...))`). Sin `world`, el mod falso es el de F1b-bridge, sin cambios.

**Lo que hay en el mundo:**
- **Entidades** con id interno, clase, posición `[x, y, z]`, `yaw`, `hp`, padre y hueco (`cargo` o `att:<nombre>`), flags de creación y vida.
- **Clases con inventario:** `LargeTent`, `MediumTent`, `CarTent`, los `Barrel_*`, `WoodenCrate`, `SeaChest`, `Fireplace` y `PowerGenerator`.
- **Suelo:** `ground_y(x, z)` determinista y no plano, inyectable.
- **Ticks simulados:** `tick_s`, 0 por defecto. Infectados y animales con la IA suelta derivan `creature_drift_m` por tick, 1,5 m por defecto.
- **Contador `storage_ops`:** cualquier llamada a la API de storage del mundo lo sube, y nada del mod la llama.

**Registro de propiedad** (#10), en memoria, como en §3.3. Es lo único que el código del mod consulta para decidir qué es suyo. El origen real de cada entidad solo lo ve el censo.

**Verbos:** `read(doc_id)`, `apply(order, check, tick)`, `reset(order, check, tick)` y `observe(order)`, que cumplen §3 al pie de la letra. `check()` es el `_check_before_effect` del peer: devuelve `None`, `"lease_expired"` o `"expired"`. Los efectos se cuentan por `(session, op_id)` (creados y borrados), para contar ejecuciones reales.

**Censo independiente** (para las pruebas): `census()` devuelve todas las entidades vivas con clase, pose, `hp`, padre, origen real (`sandbox`, `foreign` o `persistent`) y escena real. No lee el registro.

**Ganchos de prueba:**
- `spawn_foreign(cls, x, z, yaw, inside=None)`, en el suelo o dentro de una entidad;
- `spawn_own_child(doc_id, parent_lid, cls, lid)`, un hijo registrado como los que creará F3;
- `move_to_ground(eid)`, para un hijo soltado;
- `seed_scene(doc_id, rows)`, otra escena registrada con el mismo algoritmo, la «segunda escena»;
- `fail_create(lid)`, `suppress_create(lid)` (la entidad se crea y desaparece en el mismo tick), `displace_on_create(lid, d)` y `fail_delete(lid)`;
- `restart(epoch)`: mundo nuevo y registro vacío. Desaparece todo lo creado con `ECE_NOPERSISTENCY_WORLD` y se quedan las entidades `persistent` `[verify S-persist]`.

**`FakeMod`** solo gana los ganchos:
- el `hello` con `"scene": 1` cuando hay mundo;
- el catálogo, por defecto las clases de `catalog-m1.json`;
- el despacho de `state.read`, `scene.apply` con `rows`, `scene.reset` y `scene.observe` al mundo;
- `restart_mission()`, que llama a `world.restart`;
- `--world` en el CLI, con la escena de `fixtures/escena-sin-actores.json`.

**`fixtures/escena-sin-actores.json`:** `escena-basica-cine.json` sin `act-01` ni `act-02`, con `doc_id` `d-7c19e2a5` y el nombre «Amanecer en Stary Sobor (sin actores)». Lo demás, idéntico: 20 objetos, 10 infectados y 3 animales.

## 6. Web

Lo mínimo para la decisión de A3 («la web lo enseña»), en `app/web/src/App.tsx`. El reparto con la sesión de F6-web está pendiente; si F6 lo absorbe, aquí solo quedan la API y las pruebas de backend.
- **Columna «Operación»:** «Aplicar» sin `verb`, «Resetear» con `scene.reset`.
- **Columna «Motivo»:** `reason`, o «—» si no hay.
- **Botón «Resetear»:** junto a «Aplicar», manda `POST /api/reset` con el `doc_id` actual.
- **P12 (E2E):** con el mod falso con mundo y `escena-sin-actores.json`, «Aplicar» → Observado. Se mete un objeto ajeno en `obj-17` (`SeaChest`) y «Resetear» → fila «Resetear» en Parcial con el motivo `contenido_ajeno` visible.

## 7. Aceptación (R26)

**Gate**: el comando único de F1b-web §7 (suite, `npm ci`, build y arnés E2E), desde `DayZSandbox_dev/`, con rc 0. La suite incluye las **181 pruebas de hoy sin tocarlas** más las nuevas, sin fallos ni saltadas, tres corridas seguidas en verde. Las pruebas nuevas usan el `Bridge` real en un hilo con puerto 0, constantes acortadas y `tick_s` = 0 salvo donde se diga.

| # | Positivo | Negativo (el defecto que detecta) |
|---|---|---|
| F2-A1 | Escena válida → plan con `plan_sha256` reproducible (dos construcciones dan los mismos bytes) y una orden en el bridge | Con actores → `expansion_unavailable`; clase fuera del catálogo del mundo → `unknown_class` con `/entities/<i>/cls`; `x` por encima del `world_size` del hello → `out_of_map`; sin catálogo → `catalog_pending`. En todos, 0 órdenes en `Bridge.orders`, ninguna línea `scene.apply` en el log del bridge y ningún evento (un backend que valida pero despacha) |
| F2-A6 | Escena justo en los topes (20/10/3) → `observado` | Topes bajados después de guardar el documento (`caps.objeto` = 19) → `budget_exceeded`; `caps.total` = 30 con 20/10/3 → `budget_exceeded`; en los dos, 0 órdenes. Una orden directa al mod con más filas que sus `caps` → `rejected/budget_exceeded` y el censo sin cambios |
| F2-A2 | `escena-sin-actores` → `observado`; el censo tiene el multiconjunto por clase del plan, 33 raíces de Sandbox y cada una a < 0,5 m de `(x, gy, z)`; los infectados y animales también, en el checkpoint, con `tick_s` > 0 y deriva activa | Creación suprimida → `fallido/lectura_no_cumple` y el censo con 32; entidad desplazada 0,6 m al crearla → `fallido/lectura_no_cumple`; la misma orden entregada dos veces (`force_double_delivery`) → censo con 33 y creados = 33 |
| F2-A3 | Reset con dos hijos propios (uno en el cargo de `obj-17` y otro soltado en el suelo) → `observado`; censo con 0 entidades de Sandbox de la escena; segundo reset → `observado` sin efectos; `storage_ops` = 0 | (a) Objeto ajeno en el suelo entre las entidades de la escena → intacto en clase, pose e inventario. (b) Segunda escena (`seed_scene`) → intacta. (c) Objeto ajeno dentro de `obj-17` → `obj-17` sigue en pie, en su pose, con el ajeno dentro y en su pose; el reset termina `parcial/contenido_ajeno` con `obj-17` en `retained`; lo demás de la escena, borrado. (d) Ajeno dentro de un hijo propio contenedor dentro de `obj-15` → se quedan los dos contenedores. (e) Hijo de la segunda escena dentro de `obj-16` → `obj-16` se queda. (f) Apply con un contenedor retenido → `fallido/foreign_content_retained` y el censo sin cambios. (g) Orden de reset con el `epoch` viejo tras `restart_mission()` → `rejected/stale_epoch` y el censo sin cambios |
| F2-A4 | Mismo `epoch`: aplicar, cerrar el backend, abrir otro sobre el mismo fichero, reconectar el mod falso, reconciliar y aplicar → `observado`, censo con 33 sin extras y el mismo hash del documento. `epoch` nuevo (`restart_mission`) → lo mismo | Resultado del apply perdido y backend reiniciado antes de recibirlo → el apply nuevo deja 33, no 66. Un `parcial` del `epoch` viejo no provoca ni compensación ni observe en el mundo nuevo. Guardado interrumpido: lo cubre `test_store.py:134` (F1), que debe seguir pasando |
| F2-C | Creación que falla en la fila 12 → `parcial`, y luego `parcial/compensada`; censo con 0 de la escena y nada ajeno tocado | Polls cortados después de la 5.ª creación → `error/lease_expired`, `pending` con 5, ninguna creación más tras el corte. Al volver, el backend compensa (`if_pending`) → `parcial/compensada` y el censo con 0. Una compensación con otro `if_pending` → `rejected/not_pending` sin efecto |
| F2-R | Resultado de un reset perdido → `parcial/sin_resultado` → la lectura enseña `last` con `done` → `observado/reconciliada`. Resultado de un apply perdido → la lectura enseña su generación → checkpoint → `observado/reconciliada` | Checkpoint que no cumple (entidad desplazada) → `fallido/lectura_no_cumple`, nunca `observado` por identidad sola; un `parcial` resuelto (`contenido_ajeno`, `compensada`) no mantiene vivas las lecturas |
| F2-O | `POST /api/observe` → `scene.observation` por el SSE y `GET /api/observation` con `age_ms`; tras mover una entidad 2 m, la fila `now` lo refleja | Sin peer con escena → 409 `scene_unsupported` y 0 órdenes |
| F2-D1 | Las 181 pruebas de hoy y P1-P11 pasan sin tocarlas | Un peer sin `scene` recibe `scene.apply` con `args` `{doc_id, rev, hash}` y `state.read` con `{}` |
| P12 | §6 | — |

**X4 (antitautología).** El orquestador corre las pruebas contra el código mutado, y cada mutación tiene que hacer fallar al menos una prueba:
- (a) el reset borra por radio alrededor de la escena;
- (b) se borra un contenedor con algo ajeno dentro;
- (c) lo ajeno se saca al suelo y se borra el contenedor;
- (d) se retiene sin subir a los antepasados;
- (e) lo borrable no se filtra por escena;
- (f) un hijo de otra escena cuenta como propio;
- (g) solo se borra lo registrado por la sesión actual del backend;
- (h) el apply crea sin resetear antes;
- (i) el checkpoint se lee después de soltar la IA;
- (j) el predicado sin posición, o con tolerancia de 0,7 m;
- (k) el predicado sin el conjunto de `lid` ni las clases;
- (l) el apply no valida contra el catálogo del mundo;
- (m) el apply sin `caps` o sin `total`;
- (n) el apply manda las escenas con actores;
- (o) la compensación borra más allá de la orden;
- (p) un fallo de creación sin compensar;
- (q) efectos después de perder el lease, sin comprobar antes de cada efecto;
- (r) un reset con algo retenido sale `observado`;
- (s) un apply con algo retenido sigue adelante;
- (t) el registro sobrevive a `restart_mission`;
- (u) la reconciliación da `observado` por identidad, sin checkpoint;
- (v) el predicado sin `plan_sha256`;
- (w) el reset toca el storage;
- (x) un peer sin `scene` recibe el plan.

**Terminado cuando:**
1. el gate sale con rc 0 tres veces seguidas;
2. X4 deja todas sus mutaciones muertas;
3. el diff solo toca el write-set de §8;
4. Sol sobre el código congelado no deja pendientes, o el orquestador los arbitra tras 2 rondas;
5. el sha256 de este brief congelado figura en el commit.

## 8. Ficheros

```
DayZSandbox_dev/
  plans/2026-11-14-m1-f2-offline-brief.md   este brief                                  [orquestador]
  app/backend/scene_plan.py                 §4.1 y §4.3: plan, validación, cota y predicados   [F2-1]
  app/backend/scene_live.py                 §4.4 y §4.5: SceneLive (transiciones de F2)   [F2-1]
  app/backend/bridge.py                     ganchos de §4.6                              [F2-1]
  app/backend/server.py                     §4.2 y ganchos de §4.6                        [F2-1]
  app/tests/test_scene_plan.py              F2-A1, F2-A6 y predicados, sin red             [F2-1]
  app/tests/fake_world.py                   §5                                            [F2-2]
  app/tests/test_fake_world.py              §3.3-§3.5 contra el mundo, sin red             [F2-2]
  fixtures/escena-sin-actores.json          §5                                            [F2-2]
  app/tests/fake_mod.py                     ganchos de §5                                 [F2-3]
  app/tests/test_f2_live.py                 F2-A2, F2-A3, F2-A4, F2-C, F2-R, F2-O y F2-D1 de punta a punta   [F2-3]
  app/web/src/App.tsx, app/tests/e2e_web.py, app/web/e2e/queue.e2e.cjs   §6 y P12            [F2-3, si F6 no lo absorbe]
```

**No se tocan** `store.py`, `validate.py`, `lease.py`, `app/mcp/`, el esquema, las fixtures de hoy, ninguna prueba de hoy (salvo el arnés y el guion E2E para P12), `qa/` ni la sonda.

## 9. Entrega

| Tanda | Escribe | Depende de |
|---|---|---|
| F2-1 | backend: `scene_plan.py`, `scene_live.py`, ganchos y `test_scene_plan.py` | este brief congelado |
| F2-2 | `fake_world.py`, `test_fake_world.py` y la fixture | este brief congelado (en paralelo con F2-1) |
| F2-3 | ganchos de `fake_mod.py`, `test_f2_live.py` y la web | F2-1 y F2-2 integradas |

**Workers** (skill `delegar`): Muse (`muse-wonder-1.0`). Si se queda sin créditos, el mismo encargo pasa a Gemini por `agy`, primero Argon y si da 429 Carbon. Cada tanda trabaja en una copia aparte del commit congelado, porque el sandbox deja restos.

El orquestador:
- revisa el diff, de otra familia que el worker;
- corre el gate y X4 sin fiarse de los recibos;
- integra y hace commit en `claude/f2-offline`.

Después, Sol revisa el código congelado. Push, PR y merge, con merge commit, cuando Sol no deje pendientes y el gate esté en verde (autorización de Guillermo para esta parte, que no toca el PBO).

## 10. Riesgos y lo que no se ha medido

- **El mundo es un modelo.** Esta subfase acredita el contrato y el backend, no el mundo de DayZ. El censo de aquí es el del mundo falso: un mod real que mienta en su lectura solo lo caza el censo independiente en partida (§11).
- **`[verify S-persist]`:** los flags de #11 (§3.7), la vía del checkpoint de Q9, si una prenda o un hijo propio se persiste, y qué reaparece tras reiniciar el servidor. El `restart` del mundo falso no reaparece nada por construcción: **no acredita nada** de A3 «nada reaparece».
- **`[verify S-perf]`:** `SCENE_BATCH` y el TTL de un apply grande. Con 33 raíces y 8 por tick, son unos 5 ticks de creación y otros 5 de borrado.
- **Tamaños:** medidos con el peor caso de los topes provisionales. Unos topes mayores (S-perf) o los hijos y actores de F3 obligan a paginar `scene.observe` y el checkpoint. `plan_too_large` y `result_too_large` lo convierten en un rechazo visible, nunca en un truncado.
- **Números en Enforce:** el redondeo a 3 decimales y la forma del número en el JSON del mod real (`[verify F2 en partida]`). Si un número sale con más caracteres, la cota de §4.1 puede quedarse corta: el mod lo sustituye por `result_too_large` (F1b-bridge §2.4.7).
- **`gy` lo resuelve el propio mod.** El error vertical de A2 se mide contra su `SurfaceY`; el censo de partida lo contrasta con una lectura de suelo independiente.
- **Un apply bloqueado por algo ajeno retenido** obliga al usuario a sacarlo en el juego (D7). Es lo seguro, pero hay que enseñarlo bien en la web (F6).

## 11. Continuación: F2 en partida

- **Qué:** `scene.apply`, `scene.reset` y `scene.observe` de §3 en el mod núcleo (Enforce), con el registro, la retención y los lotes por tick. Encima, el censo independiente antes y después, el reinicio del servidor y el reinicio solo del backend (plan F2, línea 102).
- **Prerrequisitos:**
  - F1b-peers (los peers reales de `dsbx1`);
  - S-persist (flags, vía de Q9 y lo que reaparece);
  - este brief congelado y su código en verde.
- **Gate:**
  - linter offline de Enforce antes de declarar nada;
  - en partida, con el visto bueno de Guillermo para lanzar DayZ: A2, A3 y A4 sobre la escena sin actores, con censo independiente.

## 12. Cambios por la revisión

(vacío en v1.0)
