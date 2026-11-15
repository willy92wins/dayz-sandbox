# F2 sin juego: escena viva (aplicar, resetear y observar) sobre `dsbx1`, con el mod falso

2026-11-14 · tarea **F2-offline** (la parte de F2 que se hace y se prueba sin DayZ), rama `claude/f2-offline`, que sale de `claude/f1b-bridge` `a0fa14c` (F1bb con el gate en verde: 181 pruebas, E2E P1-P11, X3 17/17) más `7bede68`, que trae aquí la decisión de A3 (`e127ee7` de `claude/f0.3-briefs`) · spec de implementación (R25) de [plan v2](2026-10-26-m1-cine-v2.md) F2 (líneas 95-102), decisiones #9, #10 y #11 (31-33), #23 (45), #28 (50), Q9 (222), CX-01 (246) y CX-07 (252) · contrato: `DayZSandbox_dev/product-spec.md`, A1-A4 y A6 (47-50 y 52), C5 (78) y D2 (88) · protocolo: [F1b-bridge](2026-11-14-m1-f1b-bridge-brief.md) v1.4 (`dsbx1`) · reset y flags: brief de S-persist en `claude/f0.3-briefs` `6f88973` (`plans/2026-11-14-m1-f0.3-s-persist-brief.md`, §3.1 `:122-128` y §3.3 `:145-158`) · **v1.2.2, congelado.** Aplica las dos rondas de Sol (§12). La 2 dio NEEDS-WORK con 2 BLOQ y 4 MAY, y al ser la última los arbitró el orquestador. La v1.2.1 añade las aclaraciones de implementación de §13, que salen de revisar el código parcial y no cambian el contrato. La v1.2.2 añade A15 y M20: el límite del motor de 1023 caracteres por cadena, medido en partida por F0.3-0. Tras el merge de F1b-bridge, la rama se rebasó sobre `main` `0634598`, y A3 quedó en `a928451`.

**Por qué ahora.** F2 depende de F1 y de S-persist. F1 está a falta de los peers reales (F1b-peers) y S-persist no ha corrido. Todo lo que F2 puede fijar sin juego (el contrato de los verbos de escena, el backend y un mod falso con mundo) se hace ya, para que F2 en partida solo tenga que escribir el mod real y medir. Lo pidió Guillermo («Más frentes en paralelo»).

**La decisión de A3 (Guillermo, 2026-11-14), vinculante.** El reset nunca mueve lo ajeno, y lo ajeno conserva siempre su pose. Un contenedor de Sandbox con contenido ajeno dentro se queda en su sitio y no se borra; la operación termina `parcial`, con su motivo, y la web lo enseña. Sustituye a la extracción al suelo de la versión anterior de #10. Texto: A3 del spec (línea 49), #10 (32) y la fila A3 de §4 (153).

**Proceso.** Brief → Sol (`gpt-6.1-sol`, esfuerzo máximo, solo lectura), 2 rondas como mucho, y después arbitra el orquestador → tandas delegadas (§9) → gate y X4, corridos por el orquestador → Sol sobre el código congelado. Sin lanzar DayZ.

**Coordinación con otras sesiones (acordada el 2026-11-14):**
- F1b-web pasa ahora la ronda 1 de Sol del código de F1b-bridge. Hasta que F1b-bridge esté en `main`, F2 solo escribe **ficheros nuevos**. Después, `claude/f2-offline` rebasa sobre `main` y cablea `bridge.py`, `server.py` y `fake_mod.py` (tanda F2-3).
- En `server.py` entra primero F6-web, si tiene antes su PR en verde, y F2 rebasa encima.
- La web es de F6-web (§6).

## 0. Qué es y qué no

Es:
- el **contrato de los verbos de escena** sobre `dsbx1` (§3): `scene.apply` con su plan, `scene.reset`, `scene.observe` y el estado de la escena dentro de `state.read`. Lo cumplen el mod falso de ahora y el mod real de F2 en partida;
- el **lado del backend** (§4): plan ligado al hash, validación contra el mundo antes de mandar nada (A1, A6), predicados de apply, reset y compensación, generación, reconciliación de lo `parcial` y compensación;
- un **mundo falso** (`app/tests/fake_world.py`, §5) para el peer servidor del mod falso: entidades con inventario, suelo, registro de propiedad, censo independiente y fallos inyectables.

No es:
- **la web.** La pone F6-web (§6). F2 le da la API y prueba en el backend que `op.state` lleva `verb` y `reason`;
- **el mod real en Enforce**, ni el censo independiente en partida, ni el reinicio del servidor (§11). Van después de S-persist y de F1b-peers;
- lo que decide **S-persist** (flags de persistencia de #11, vía del checkpoint de Q9, qué reaparece tras reiniciar). Aquí va marcado `[verify S-persist]` y no bloquea;
- los **actores**, las prendas y los hijos que cree Sandbox (F3). El registro ya admite hijos, y las pruebas los inyectan para probar el reset (A3 «con hijos propios»);
- los **topes finales** (S-perf y F6). Valen los provisionales de #28: los `caps` de `fixtures/catalog-m1.json`.

Trazabilidad (R20): §2 y §3 salen de #9, #10, #11, Q9 y del protocolo `dsbx1`; §4, de #9, #10, #23, #28, A1, A6 y CX-07; §5, de #24 y de S-persist §3.3; §6, de la decisión de A3 y D2; §7, de A1-A4 y A6. Lo que no trace a esto no entra.

## 1. Entorno y fronteras

Como F1b-bridge §1: Python 3.14 en `C:\Python314\python.exe`, **solo biblioteca estándar** y `unittest`, comandos desde `DayZSandbox_dev/`, solo 127.0.0.1, ninguna clave en logs ni salidas, UTF-8 sin BOM con LF. El brief **añade**: una línea que no haga falta tocar no se toca (R20). No se tocan `qa/`, la sonda ni la web.

## 2. Decisiones de diseño

| # | Decisión | Por qué |
|---|---|---|
| D1 | **Capacidad en el hello, y contrato fijado por orden.** El peer servidor que cumple §3 añade `"scene": 1` a su `/hello`. Al crear una orden se decide su contrato. Con un peer con escena es una **orden F2** (`scene.apply` con plan, `scene.reset` y las internas de §4.5), y se juzga y se reconcilia **solo** con lo de §4, aunque después el peer se presente sin `scene`. Con un peer sin escena, o sin peer, `scene.apply` es una **orden F1** (F1b-bridge §3.2) y se juzga como allí. | F1b-peers llegará antes que el mod real de F2, y las 181 pruebas de F1 aplican la fixture con actores contra peers sin escena: tienen que seguir pasando **sin tocarlas**. `handle_hello` ya ignora campos de más (`bridge.py:347-397`). Fijarlo por orden impide que una orden F2 se dé por buena con el predicado de F1 (F1-02). |
| D2 | **El plan lo construye el backend** a partir del documento congelado (`Store.freeze`, `store.py:124-137`) y viaja **entero en una sola orden**, con las clases indexadas. Lleva su propio `plan_sha256`, que el mod no recalcula: lo devuelve en la generación, y el predicado lo exige. «Por lotes» es la creación por ticks dentro del mod (#9), no páginas en el cable. Los rangos de §3.6 son **normativos**: con ellos, todo cuerpo admisible de una escena de 33 raíces cabe en `WIRE_CAP`. | Envolvente con esos rangos (§3.6): 2722 B la orden, 2968 B el resultado de apply y 3362 B el de observe; caben hasta 34 raíces. Un plan cuya envolvente no quepa se rechaza antes de mandarlo (`plan_too_large`). Las páginas llegarán con F3, cuando los hijos y los actores hagan crecer las lecturas. Recalcular el hash en Enforce obligaría a imitar el JSON canónico de Python. |
| D3 | **Una escena con actores se rechaza entera** (`expansion_unavailable`) antes de mandar nada. | F2 cubre la escena sin actores (CX-01) y en F2 el mod no tiene motor de actores (`actor_engine: "none"`). Es el sentido de C5: nunca aplicar a medias. |
| D4 | **Tipos y topes salen de la biblioteca de M1** (`fixtures/catalog-m1.json`: clases por tipo y `caps` provisionales de #28; `caps.total` si existe). El catálogo del mundo (#8, `Bridge.catalog`) solo certifica que la clase existe, y **solo vale para el servidor presentado ahora**: tiene que haberse completado después del último hello del servidor, desde su `inst`, y con la `build` de ese hello. Si no, `catalog_pending`. Su `base` no se usa en M1. | #28 fija los topes provisionales en la fixture. Un catálogo de otra build o de otro arranque certificaría clases que el mundo de ahora no tiene (F1-01). `total` cubre la negativa de A6 «mezcla por encima del total» cuando S-perf lo fije. |
| D5 | **Lo borrable de una escena es todo lo registrado de esa escena en el epoch vigente**, raíces e hijos, de cualquier generación. La retención (S-persist §3.3, `:145-158`: un registro con un descendiente no borrable se queda, y con él sus antepasados borrables) se calcula al empezar **y otra vez justo antes de cada borrado**, en el mismo tick. **Un borrado solo cuenta si se confirma**: después de pedirlo, la entidad ya no vive o está marcada para borrarse. Si no se confirma, el registro se queda y la operación para con `delete_failed`. **Lo propio se borra esté donde esté**: en el suelo, en un contenedor propio o en uno ajeno. A un contenedor ajeno solo se le quita lo propio. | Con apply = resetear y crear (#9), todo lo registrado de una escena es su generación viva más lo que haya dejado una operación interrumpida: así no queda nada huérfano. Entre ticks alguien puede meter algo ajeno en un contenedor (F1-06). Un borrado que falla en silencio daría 34 raíces con un checkpoint perfecto (F1-04). Lo de otra escena no es borrable (S-persist N43). |
| D6 | **Reset con algo retenido → `parcial` con el motivo `contenido_ajeno`.** El mod devuelve `done` y su lectura enseña lo retenido; el estado lo decide el backend a partir de la lectura, no de una etiqueta del mod. | Es la decisión de A3. Decidirlo con la lectura hace que el caso en que no se borró nada (solo quedaba el contenedor retenido) también salga `parcial`, como dice A3. |
| D7 | **Apply y retención.** Si al empezar algo de la generación anterior quedaría retenido, el apply se rechaza **sin efecto** (`foreign_content_retained`) y termina `fallido`. Si la retención aparece después de haber borrado algo, el apply para: no crea nada, conserva lo protegido y termina `parcial`. **Nunca se crea mientras lo borrable de la escena no esté vacío.** | Así la escena anterior no queda a medias y la generación nueva nunca convive con restos de la vieja: eso daría duplicados en el censo (A4) y huérfanos (F1-04). El usuario saca lo ajeno en el juego y vuelve a aplicar. |
| D8 | **Compensación en dos niveles.** Si falla una creación con el lease y el plazo vivos, el mod compensa en la misma orden: borra lo que creó esa orden, con D5. Si se pierde el lease o el plazo, el mod para sin más efectos y deja lo creado como pendiente; el backend lo ve en una lectura y manda la compensación (`scene.reset` con `if_pending`). En las dos vías, una compensación solo se da por hecha si la lectura lo confirma (§4.3). | #9: «un fallo a mitad deja `parcial` y compensa solo lo de esa operación». Plan F2: la compensación de los parciales es del backend. `dsbx1` prohíbe efectos sin lease (F1b-bridge §2.4.6). |
| D9 | **Checkpoint (Q9) en el mismo tick de la creación**, antes de soltar la IA, y guardado en el registro. La observación «ahora» es otra lectura. | Q9 (4): infectados y animales se miden al crearlos, antes de soltar su IA. La vía exacta la decide S-persist `[verify S-persist]`. |
| D10 | **Altura `"ground"` resuelta al crear.** El documento no tiene `y` (`schemas/scene.schema.json`, `nonActorEntity`). El mod usa `gy = SurfaceY(x, z)` al crear, lo guarda y lo devuelve. | Plan F2, línea 99. Mismo criterio que S-persist §3.2 `[verify S-persist]`. |
| D11 | **La expectativa sale del documento congelado, no del constructor del plan.** Al aplicar, el backend extrae directamente del documento congelado `{lid: (cls, x, z)}` de cada entidad no actor, sin pasar por el constructor del plan. Con eso juzga las filas del plan y las lecturas. | Un constructor que desplace todas las `x` 2 m daría un plan determinista, una generación coherente y error cero contra sí mismo (F1-07). |
| D12 | **Margen de redondeo.** Se acepta `dist3 < POS_TOL_M − EPS_Q`, con `POS_TOL_M` = 0,5 m y `EPS_Q` = 0,002 m. | La lectura redondeada a mm se aparta como mucho √3·0,0005 ≈ 0,00087 m y el plan como mucho √2·0,0005 ≈ 0,00071 m: un error real ≥ 0,5 m nunca pasa (F1-11). |

## 3. Contrato de los verbos de escena

Lo cumplen el mod falso con mundo (§5) y, en partida, el mod real. Todo lo de F1b-bridge §2 sigue igual: deduplicación por `(session, op_id)`, comprobaciones de la orden, lease y plazo antes de **cada** efecto, y `rejected` solo sin ningún efecto.

### 3.1 Hello

El peer servidor que cumple §3 añade `"scene": 1`. Cualquier otro valor, o su ausencia, es un peer sin escena (D1).

### 3.2 Estado del mundo y de la escena

Con un peer con escena, `state.read` lleva `args` `{doc_id}`: el `doc_id` del documento del backend. Su `read` es el de F1b-bridge §4 más `scene`:

```
{epoch, generation, registry_n, registry_sha256, scene: {doc_id, gen_n, n, retained_n, retained, pending, last}}
```

- `generation`: la generación **viva** de esa escena, `{session, op_id, rev, hash, plan_sha256}`, o `null` si no tiene ninguna publicada (nunca aplicada, reseteada, compensada o interrumpida). La clave está siempre, como exige `valid_world_read`.
- `registry_n` y `registry_sha256`: todo el registro del epoch, todas las escenas. El hash es SHA-256 del JSON canónico de la lista ordenada de `[scene_id, lid, parent_lid|null, cls, gen_n]`.
- `scene.gen_n`: generaciones publicadas de esa escena en este epoch. `scene.n`: registros de la escena, raíces e hijos. `scene.retained_n`: cuántos de ellos se quedaron, en el último reset, compensación o apply, por tener algo no borrable dentro; `scene.retained`: sus `lid`, como mucho 8.
- `scene.pending`: `{session, op_id, n}` si un apply empezó a crear, no publicó y no está compensado del todo; si no, `null`.
- `scene.last`: la última orden de escena que tocó esta escena, `{session, op_id, verb, outcome}`, o `null`. `verb` es `scene.apply` o `scene.reset`; una compensación anota el `op_id` del apply que compensa. `outcome`:
  - `done`: terminó entera;
  - `retained`: terminó, o paró, con algo retenido;
  - `compensated`: un apply que falló y está compensado del todo;
  - `interrupted`: paró por lease, plazo o un borrado que no se confirmó.

El backend valida la forma y los rangos de §3.6: tipos de F1b-bridge §4 para lo de antes, y para `scene` `doc_id` como el del esquema, enteros en [0, 999999], `retained` con ≤ 8 textos y `≤ retained_n`, y `pending` y `last` con su forma o `null`. Un `read` de una orden F2 sin `scene` no vale (F1b-bridge §2.7).

### 3.3 `scene.apply`

`args` `{doc_id, rev, hash, plan_sha256, caps, classes, rows}`:
- `classes`: las clases distintas de las filas, ordenadas;
- `rows`: una fila por entidad no actor del documento, en el orden del documento, `[lid, ci, x, z, yaw]`, con `ci` el índice en `classes` y los números redondeados a 3 decimales. El `yaw` se normaliza después de redondear a [0, 360): un 359,9999 queda en 0,0;
- `caps`: `{objeto, infectado, animal}` de la biblioteca, más `total` si existe;
- `plan_sha256`: SHA-256 del JSON canónico (`sort_keys`, separadores `,` y `:`, UTF-8) de `{doc_id, rev, hash, classes, rows}`.

El tipo sale del prefijo del `lid` (`obj`, `zmb`, `ani`). Etapas, en este orden (#9):

1. **Validar**, sin efecto: forma y rangos de §3.6 (`lid` único y con el patrón del esquema, `ci` en rango, números finitos) → si no, `rejected/bad_plan`; cada clase existe en el mundo → si no, `rejected/unknown_class`; `x` y `z` en [0, `world_size`] → si no, `rejected/out_of_map`.
2. **Reservar presupuesto**, sin efecto: cuentas por tipo ≤ `caps` y total ≤ `caps.total` → si no, `rejected/budget_exceeded`.
3. **Retención previa**, sin efecto: lo borrable de la escena (D5) y su retención. Si algo se quedaría → `rejected/foreign_content_retained`, con el `read` de §3.2 (D7).
4. **Resetear**, con efecto: borra lo borrable en dos pasadas, primero los hijos y luego las raíces (S-persist §3.3 punto 3), por lotes de `SCENE_BATCH` por tick. Antes de **cada** borrado, en el mismo tick:
   - lease y plazo;
   - retención otra vez (D5). Si ahora la entidad es retenible, no se borra: se retiene con sus antepasados borrables y el apply para con `last.outcome = "retained"` y `error/foreign_content_retained` (D7);
   - confirmación del borrado (D5). Si no se confirma, el registro se queda y el apply para con `last.outcome = "interrupted"` y `error/delete_failed`.

   Al primer borrado confirmado, `generation` pasa a `null`. Solo se pasa a crear si lo borrable de la escena quedó **vacío**.
5. **Crear**, con efecto: `pending` = esta orden, y sus registros llevan `gen_n` = `scene.gen_n + 1`. Por cada fila, por lotes de `SCENE_BATCH` por tick, con lease y plazo antes de cada creación:
   - `gy = SurfaceY(x, z)`. Si `gy` sale fuera del rango de §3.6, cuenta como creación fallida;
   - crea la entidad en `(x, gy, z)` con `yaw` y los flags de §3.7;
   - la registra con `{epoch, scene_id: doc_id, gen_n, op: {session, op_id}, lid, parent_lid: null, cls, gy}`;
   - en ese mismo tick, antes de soltar la IA, lee el checkpoint y lo guarda en el registro (D9).
6. **Publicar**, sin efecto en el mundo: `generation` = `{session, op_id, rev, hash, plan_sha256}`, `scene.gen_n` pasa al valor de sus registros, `pending` = `null`, `last` = `{…, verb: "scene.apply", outcome: "done"}`. El resultado es `done` con el `read` de §3.2 (con `retained` vacío y `pending` nulo) más `obs: {at: "checkpoint", rows}`, una fila por cada fila del plan (§3.6).

**Si fallan el lease o el plazo antes de un efecto:**
- antes del primer efecto → `rejected/<motivo>`;
- después → se para sin ningún efecto más, `last.outcome = "interrupted"` y `error/<motivo>`. Si ya había creaciones, `pending` sigue con esta orden.

**Si falla una creación** (la entidad no aparece, o `gy` fuera de rango), con el lease y el plazo vivos, el mod compensa en la misma orden (D8):
- borra los registros de esta orden con D5;
- `pending` pasa a `null` si de esta orden ya solo quedan registros retenidos (la misma regla que en §3.4). Si un borrado no se confirma, `pending` sigue con esta orden;
- `last.outcome` es `compensated`, `retained` si algo se quedó, o `interrupted` si un borrado no se confirmó;
- termina en `error/create_failed`.

Una fila del checkpoint de una entidad que ya no vive, o con una lectura fuera de rango, lleva `ci = -1` y `x`, `y`, `z` y `yaw` a `null`.

### 3.4 `scene.reset`

`args` `{doc_id}`, o `{doc_id, if_pending: {session, op_id}}` para una compensación que manda el backend.

1. Con `if_pending`, si `scene.pending` no es esa orden → `rejected/not_pending`, sin efecto.
2. Lo borrable: con `if_pending`, los registros de esa orden; si no, lo de D5. Se calcula la retención (S-persist §3.3 punto 2).
3. Se borra lo borrable no retenido en dos pasadas (hijos y luego raíces), por lotes. Antes de cada borrado: lease y plazo (§3.3), retención otra vez y confirmación del borrado (D5). Un borrado que se vuelve retenible se salta y se retiene. Uno que no se confirma para la operación con `outcome = "interrupted"` y `error/delete_failed`.
4. Con `doc_id` solo: `generation` = `null`, `pending` = `null` y `last` = `{session, op_id, verb: "scene.reset", outcome}`, con `outcome` `retained` si algo se quedó y `done` si no. Con `if_pending`:
   - `pending` = `null` si de esa orden ya solo quedan registros retenidos, la misma regla que en §3.3;
   - `last` = `{session, op_id del apply, verb: "scene.apply", outcome}`, con `outcome` `compensated`, `retained` o `interrupted`;
   - si un borrado no se confirma, `pending` sigue con esa orden y su `n` con lo que quede.
5. Resultado `done` con el `read` de §3.2, aunque haya algo retenido: el estado lo decide el backend (D6). Un segundo reset sobre una escena vacía es `done` sin efecto (A3: idempotente). Si solo quedaba un contenedor retenido que sigue guardando algo ajeno, vuelve a salir `retained`.

Nunca: borrar lo que no está en lo borrable (por radio, por clase o por parecido), mover algo, sacar lo ajeno al suelo ni tocar el storage.

### 3.5 `scene.observe`

`args` `{doc_id, at}`, con `at` `"checkpoint"` o `"now"`. Lectura sin efecto. Su `read` es el de §3.2 más `obs: {at, rows}`:
- `checkpoint`: las filas guardadas al crear la generación viva (§3.6), o `[]` si no hay ninguna viva;
- `now`: una fila por raíz registrada de la escena, con su estado actual (§3.6).

Un resultado que pasaría de `WIRE_CAP` → `rejected/result_too_large`, porque no hubo efecto.

### 3.6 Filas, rangos y envolvente

| Fila | Forma | Notas |
|---|---|---|
| plan | `[lid, ci, x, z, yaw]` | números con 3 decimales |
| checkpoint | `[lid, ci, x, y, z, yaw, gy]` | `ci` es el índice en `classes` de la clase leída (`GetType()`), o `-1` si no está o si la entidad no vive |
| ahora | `[lid, x, y, z, yaw, hp, n_own, n_foreign]` | `n_own`, descendientes registrados de la escena; `n_foreign`, descendientes no borrables |

**Rangos normativos.** Un peer no manda nada fuera de ellos y el backend no acepta una lectura que se salga.
- **Textos:** todos ASCII (`lid`, clases, `doc_id`, motivos), así que su tamaño en el cable no depende de `ensure_ascii`.
- `lid`: el patrón del esquema **solo con dígitos ASCII** y ≤ 10 caracteres, también los de los hijos. `validate.py` acepta dígitos Unicode en `\d`; F2 no.
- **Enteros de la orden:** `rev` de 9 dígitos como mucho, número de `op_id` de 6 y `conn` de 6.
- `x` y `z`: [0, `world_size`], con `world_size` ≤ 99999.
- `y` y `gy`: [-9999,999, 9999,999].
- `yaw`: [0, 360).
- `hp`: [0, 1].
- Contadores (`gen_n`, `n`, `retained_n`, `pending.n`, `registry_n`, `n_own`, `n_foreign`, `ci`): enteros en [0, 999999] (`ci` también puede ser -1).
- Números de las filas: como mucho 3 decimales.

**Envolvente** con esos rangos y 33 raíces con las clases más largas de `catalog-m1.json`. Calculada el 2026-11-14 con el script del orquestador `sizes5.py`, con separadores compactos. Como todo es ASCII, sale igual con el serializador de `FakeMod`, `ensure_ascii` por defecto. El backend no se fía de la tabla: calcula la cota de cada apply con los valores **reales** de la orden (`lid`, clases, `rev`, `op_id`, `conn`) y los máximos de esta sección para lo que pone el mod.

| Cuerpo | Bytes |
|---|---|
| `/poll` con un `scene.apply` | 2722 |
| resultado de `scene.apply` con su checkpoint | 2968 |
| resultado de `scene.observe` `now` | 3362 |
| resultado de `scene.reset` o `state.read` | 925 |

Caben hasta 34 raíces.

### 3.7 Flags y lotes

- **Flags (#11) `[verify S-persist]`.**
  - Raíces: `ECE_PLACE_ON_SURFACE | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD | ECE_NOPERSISTENCY_CHAR` (29361188).
  - Infectados y animales: además `ECE_INITAI` (29363236), en la vía (a) de Q9.
  - Nunca `ECE_DYNAMIC_PERSISTENCY` (33554432).

  Son los valores de S-persist §3.1 (`:124-128`). `ECE_NOPERSISTENCY_CHAR` lo añade S-persist sobre el texto de #11.
- **`SCENE_BATCH` = 8** creaciones o borrados por tick `[verify S-perf]`.
- **`POS_TOL_M` = 0,5 m y `EPS_Q` = 0,002 m** (A2, D12).

## 4. Backend

### 4.1 Plan y validación antes de mandar nada (A1, A6)

`app/backend/scene_plan.py`: funciones puras, sin red.

`POST /api/apply`, con un peer servidor con escena (D1), después de `Store.freeze`. Valida **en este orden** y para en el primer código. Cada error lleva su JSON Pointer y la lista completa en `errors`. Ninguno crea orden, ni la mete en la cola, ni emite eventos:

| Código | HTTP | Cuándo | Pointer |
|---|---|---|---|
| `expansion_unavailable` | 422 | el documento tiene actores (D3) | `/entities/<i>` del primero |
| `catalog_pending` | 409 | no hay catálogo del mundo válido para el servidor de ahora (D4) | `""` |
| `unknown_class` | 422 | una clase que no está en ese catálogo | `/entities/<i>/cls` |
| `out_of_map` | 422 | `x` o `z` fuera de [0, `world_size` del hello] | `/entities/<i>/x` o `/z` |
| `budget_exceeded` | 422 | cuentas por tipo por encima de `caps` del catálogo del `Store`, o total por encima de `caps.total` | `/entities` |
| `plan_too_large` | 422 | un `lid` que no sea ASCII o tenga más de 10 caracteres, una `rev` de más de 9 dígitos o un `op_id` de más de 6, o la orden o la envolvente del resultado pasarían de `WIRE_CAP` | `/entities/<i>/id` si es un `lid`; si no, `""` |

La envolvente se calcula como dice §3.6: valores reales de la orden y máximos para lo que pone el mod. Si todo pasa, el backend guarda con la orden la expectativa de D11 y la encola con los `args` de §3.3. Sin bridge, o con un peer sin escena, `apply` hace lo mismo que en F1b-bridge.

### 4.2 Rutas nuevas

| Ruta | Quién | Cuerpo | Respuesta |
|---|---|---|---|
| `POST /api/reset` | solo la persona (403 si no) | `{doc_id}` | `{ok, op_id}`; 409 `doc_changed`, `scene_unsupported` (peer servidor sin escena) o `queue_full` |
| `POST /api/observe` | persona o IA | `{doc_id}` | `{ok, read_id}`; 409 `doc_changed` o `scene_unsupported` (sin peer servidor con escena) |
| `GET /api/observation` | persona o IA | — | `{ok, observation, age_ms}`: la última lectura `now` (`{read_id, doc_id, epoch, generation, rows, at_ms, origin: "servidor"}`) o `null` |

- **Pipeline:** las rutas nuevas pasan por el mismo camino que las de hoy: Host, Origin, CSRF y credencial (F1b-web §2).
- **Tabla `STATUS`:** recoge los códigos nuevos con el HTTP de §4.1.
- **Reset:** crea una orden de la API `{op_id, verb: "scene.reset", state: "pendiente", rev: null, hash: null, at_ms, origin: "backend", reason: null}` y encola `scene.reset {doc_id}`. Si aún no hay peer servidor, se encola igual: como en BR4, sin peer termina `fallido/no_entregada`.
- **Órdenes de apply:** conservan sus campos de hoy, sin `verb`.
- **Cola:** `queue_full` cuenta `scene.apply` y `scene.reset`.
- **Observe:** encola una lectura interna `scene.observe {doc_id, at: "now"}`. Al llegar su resultado válido, guarda `Backend.observation` con su instante en el reloj inyectado y emite el evento SSE `scene.observation` con el mismo objeto. `age_ms` se calcula con ese reloj.

### 4.3 Predicados

La misma función sirve para la vía directa y para la reconciliación. Antes de evaluar se identifica la orden por `(session, op_id)`; después se comprueba **toda** su identidad. Una lectura de la misma `(session, op_id)` con otra `rev`, otro `hash` u otro `plan_sha256` → `fallido/lectura_no_cumple` (F1b-bridge B2-02).

**Apply.** Se cumple si se cumple todo esto:
1. el `read` vale (§3.2 y rangos de §3.6) y su `epoch` es el de la orden;
2. `generation` es `{session, op_id, rev, hash, plan_sha256}` de la orden;
3. `scene.pending` es `null`, `scene.n` es el número de entidades de la expectativa y `scene.retained_n` es 0;
4. `obs.at` es `"checkpoint"`, y el conjunto de `lid` de `obs.rows` es exactamente el de la expectativa (D11), sin repetidos;
5. en cada fila, `ci` ≠ -1 y `classes[ci]` es la clase de la expectativa; `x`, `y` y `z` no son `null`; y `dist3((x, y, z), (x_doc, gy, z_doc)) < POS_TOL_M − EPS_Q`, con `x_doc` y `z_doc` del documento congelado.

Así salen el multiconjunto exacto por clase, las 33 raíces y el error de posición de A2.

**Reset**, sobre una lectura cuyo `last` es esta orden:
- `outcome: "done"`, `scene.n == 0`, `retained_n == 0`, `generation == null` y `pending == null` → `observado`;
- `outcome: "retained"`, `scene.n == retained_n > 0`, `retained` no vacío, `generation == null` y `pending == null` → `parcial/contenido_ajeno`;
- `outcome: "interrupted"` → `parcial/interrumpida`;
- cualquier otra cosa → `fallido/lectura_no_cumple`.

**Apply detenido.** Cubre un apply A que no publicó: lo paró una retención o un borrado durante su reset, o tuvo que compensar. Se juzga sobre una lectura con `last` = A y `verb: "scene.apply"`, `generation == null` y `scene.pending` distinto de A:
- `outcome: "compensated"` y `scene.n == 0` → `parcial/compensada`;
- `outcome: "retained"`, `retained` no vacío y `scene.n >= retained_n >= 1` → `parcial/contenido_ajeno`. Los registros que pasen de `retained_n` son restos sin procesar de la generación anterior; los borrará el siguiente reset o apply (D5);
- `outcome: "interrupted"` → `parcial/interrumpida`;
- cualquier otra cosa, incluida una `generation` no nula, → `fallido/lectura_no_cumple`.

Si `scene.pending` sigue siendo A, la orden no está resuelta y toca compensar (§4.5). Un `done` de la orden de compensación no basta: manda la lectura.

### 4.4 Transiciones (se suman a F1b-bridge §3.1; solo para órdenes F2)

| Orden | De | A | Cuándo | `origin` | `reason` |
|---|---|---|---|---|---|
| reset | — | `pendiente` | `POST /api/reset` | `backend` | — |
| reset | `pendiente` | `ejecutando` / `fallido` | como un apply: entrega, TTL o cambio de `conn` | `backend` | los de F1b-bridge |
| reset | `ejecutando` o `parcial` | `aplicado` → `observado` / `parcial` / `fallido` | primer resultado `done`: predicado de reset | `servidor` | — / `contenido_ajeno` o `interrumpida` / `lectura_no_cumple` |
| reset | `ejecutando` | `fallido` / `parcial` | primer `rejected` / primer `error` | `servidor` | el del peer |
| apply | `ejecutando` o `parcial` | `aplicado` → `observado` / `fallido` | primer resultado `done`: predicado de apply | `servidor` | — / `lectura_no_cumple` |
| apply | `parcial` | `observado` / `fallido` | reconciliación: generación de esta orden y predicado de apply sobre su checkpoint | `servidor` | `reconciliada` / `lectura_no_cumple` |
| apply | `parcial` | `parcial` / `fallido` | reconciliación: predicado de apply detenido (§4.3) | `servidor` | `compensada`, `contenido_ajeno` o `interrumpida` / `lectura_no_cumple` |
| apply | `parcial` | `parcial` | compensación sin progreso (§4.5) | `backend` | `interrumpida` |
| reset | `parcial` | lo del predicado de reset | reconciliación: `last` de esta orden | `servidor` | `reconciliada`, `contenido_ajeno`, `interrumpida` o `lectura_no_cumple` |

- **`parcial` resuelta:** un `parcial` con `contenido_ajeno`, `compensada` o `interrumpida` es terminal. La orden del bridge pasa a `terminal` y deja de pedir lecturas.
- **Lo de F1b-bridge sigue igual:** nunca hacia atrás; el primer resultado manda; un `parcial` de otro `epoch` se queda `parcial/mundo_reiniciado` y no se reconcilia ni se compensa (#10: sus referencias ya no valen).

### 4.5 Reconciliación y compensación (#9, #10, CX-07)

- **Qué está sin resolver.** Una orden F2 de la API de esta sesión en `parcial`, sin resolución terminal (§4.4) y del mismo `epoch` que el servidor presentado ahora, **sea cual sea su `conn`**. Tras perder el lease, la orden es de la `conn` anterior, y la lectura del mismo mundo sigue mandando.
- **Lecturas.** Mientras quede alguna sin resolver y el servidor esté presentado en ese `epoch`, se siguen pidiendo lecturas con el calendario de F1b-bridge §4 (F1-03). Cada lectura que reconcilia pasa por `SceneLive.on_world_read_locked(read)`, que juzga las órdenes F2; las órdenes F1 las sigue juzgando F1b-bridge.
- **Qué se hace con cada orden sin resolver**, en el orden de la cola:
  - **apply cuya `(session, op_id)` está en `generation`** → si la identidad completa no casa, `fallido/lectura_no_cumple`. Si casa, se encola `scene.observe {doc_id, at: "checkpoint"}` y, con su resultado, el predicado de apply. Si ese resultado enseña otra generación, la orden no cambia.
  - **apply cuya `(session, op_id)` está en `scene.pending`** → se encola la compensación `scene.reset {doc_id, if_pending}` (D8). Con la lectura siguiente se aplica el predicado de apply detenido.
    - **Límite:** como mucho 3 compensaciones por orden.
    - **Sin progreso:** si tras una compensación la lectura enseña `pending` todavía en A con el mismo `n` (un borrado que falla siempre), no hay más intentos y A pasa a `parcial/interrumpida`, terminal, con `origin` `backend`. Los registros siguen en el mod y los borrará un reset explícito.
  - **apply o reset con `scene.last` de esa orden** (y, si es un apply, `pending` distinto de él) → su predicado: reset, o apply detenido (§4.3).
  - **cualquier otra cosa** → sigue sin resolver.
- **Órdenes internas.** Hay **una** orden interna de F2 en vuelo a la vez (observe o compensación). Son internas como `state.read`: no crean fila en la API ni `op.state`, no se entregan antes de reconciliar y nunca reentregan la orden original a otra `conn`. Si una termina `rejected`, `error`, caduca o se descarta, la orden no cambia y la siguiente lectura válida la vuelve a pedir.
- **Tras reiniciar el backend,** las órdenes de la sesión anterior ya no existen (la cola vive en memoria, F1a). La primera lectura válida fija la base, y el siguiente apply resetea todo lo registrado de la escena aunque lo creara otra sesión (D5). Así no se duplica el mundo (A4).

### 4.6 Ganchos en `bridge.py`, `server.py` y `fake_mod.py` (tanda F2-3)

La lógica de F2 vive en `scene_plan.py` y en `scene_live.py`. En los ficheros de hoy solo entran ganchos, y **después** de que F1b-bridge esté en `main` (§0). Los nombres son los de `a0fa14c`. La ronda 1 de Sol de F1b-bridge añade `_check_server_loss_locked(t)` (lo llaman `sweep` y `handle_poll`), un registro de conexiones vivas y el hilo `_result_loop` en el peer del mod falso, y `valid_world_read` pasa a exigir la clave `generation`. F2-3 cablea sobre el código de `main` y respeta la intención de cada gancho:

En `bridge.py`:
- `handle_hello` guarda `scene` en el registro del peer y avisa a `SceneLive` para invalidar el catálogo (D4);
- `handle_catalog`, al completar un catálogo, avisa a `SceneLive` con la `inst` y la `build`;
- `state.read` lleva los `args` de §3.2 con un peer con escena;
- `handle_result` decide **por la orden** (D1): una orden F2 se valida con §3.2 y la juzga `SceneLive`; una orden F1, como hoy;
- la reconciliación de F1b-bridge (`_process_world_read_locked`) solo toca órdenes F1, y llama a `SceneLive` para las F2;
- «hay `parcial` viva» (`_has_live_parcial_locked`) también es verdad si `SceneLive` tiene órdenes sin resolver (§4.5);
- la elección de orden, los cambios de `conn`, el barrido y `live_scene_count` tratan `scene.reset` como `scene.apply`.

En `server.py`: `STATUS`, `Backend.apply` con el plan y la expectativa, `Backend.reset`, `Backend.request_observe`, `Backend.observation` y las tres rutas nuevas. `set_op_state` no cambia.

En `fake_mod.py`, los ganchos de §5.

## 5. El mundo falso (`app/tests/fake_world.py`)

Un `FakeWorld` en memoria, con su cerrojo, que el peer servidor del mod falso usa cuando se le pasa (`FakeMod(..., world=FakeWorld(...))`). Sin `world`, el mod falso es el de F1b-bridge, sin cambios.

**Lo que hay en el mundo:**
- **Entidades** con id interno, clase, posición `[x, y, z]`, `yaw`, `hp`, padre y hueco (`cargo` o `att:<nombre>`), flags de creación y vida.
- **Clases con inventario:** `LargeTent`, `MediumTent`, `CarTent`, los `Barrel_*`, `WoodenCrate`, `SeaChest`, `Fireplace` y `PowerGenerator`.
- **Suelo:** `ground_y(x, z)` determinista y no plano, inyectable.
- **Ticks simulados:** `tick_s`, 0 por defecto. Infectados y animales se mueven **en el momento de soltar su IA** y después, cada tick, `creature_drift_m` (1,5 m por defecto). Leer después de soltarlos ya da otra pose, aunque sea en el mismo tick.
- **Contador `storage_ops`:** cualquier llamada a la API de storage del mundo lo sube, y nada del mod la llama.

**Registro de propiedad** (#10), en memoria, como en §3.3. Es lo único que el código del mod consulta para decidir qué es suyo. El origen real de cada entidad solo lo ve el censo.

**Verbos:** `read(doc_id)`, `apply(order, check, tick)`, `reset(order, check, tick)` y `observe(order)`, que cumplen §3 al pie de la letra. `check()` es el `_check_before_effect` del peer: devuelve `None`, `"lease_expired"` o `"expired"`. Los efectos se cuentan por `(session, op_id)` (creados y borrados), para contar ejecuciones reales.

**Censo independiente** (para las pruebas): `census()` devuelve todas las entidades vivas con clase, pose, `hp`, padre, origen real (`sandbox`, `foreign` o `persistent`) y escena real. No lee el registro.

**Ganchos de prueba:**
- `spawn_foreign(cls, x, z, yaw, inside=None)`, en el suelo o dentro de una entidad;
- `spawn_own_child(doc_id, parent_lid, cls, lid)`, un hijo registrado como los que creará F3;
- `move_to_ground(eid)`, para un hijo soltado;
- `seed_scene(doc_id, rows)`, otra escena registrada con el mismo algoritmo, la «segunda escena»;
- `fail_create(lid)`, `suppress_create(lid)` (la entidad se crea y desaparece en el mismo tick) y `displace_on_create(lid, d)`;
- `fail_delete(lid)`: el borrado de esa entidad se pide pero no ocurre, y la entidad sigue viva;
- `barrier_after(n)`: tras el efecto n.º `n` de la orden siguiente, `tick()` se queda esperando hasta que la prueba libera la barrera. Sirve para cortar el mantenimiento, esperar a que caduque el lease y soltar (F2-C);
- `restart(epoch)`: mundo nuevo y registro vacío. Desaparece todo lo creado con `ECE_NOPERSISTENCY_WORLD` y se quedan las entidades `persistent` `[verify S-persist]`.

**`FakeMod`** solo gana ganchos (tanda F2-3):
- el `hello` con `"scene": 1` cuando hay mundo;
- el catálogo, por defecto las clases de `catalog-m1.json`;
- el despacho de `state.read`, `scene.apply` con `rows`, `scene.reset` y `scene.observe` al mundo;
- `restart_mission()`, que llama a `world.restart`;
- `--world` en el CLI, con la escena de `fixtures/escena-sin-actores.json`.

**`fixtures/escena-sin-actores.json`:** `escena-basica-cine.json` sin `act-01` ni `act-02`, con `doc_id` `d-7c19e2a5` y el nombre «Amanecer en Stary Sobor (sin actores)». Lo demás, idéntico: 20 objetos, 10 infectados y 3 animales.

## 6. Web (F6-web)

La web es de F6-web (acordado el 2026-11-14). F2 no toca `app/web/`. Lo que pone F6, con los nombres de su diseño:
- **«Motivo»:** sexta columna, con `reason` en crudo, o «—» si no hay.
- **«Operación»:** séptima columna. `verb: "scene.reset"` → «Quitar del juego»; sin `verb` → «Aplicar».
- **Botón «Quitar del juego»:** junto a «Aplicar», con su confirmación, llama a `POST /api/reset {doc_id}` y enseña `code`, `pointer` y `msg` de cada error.
- **Errores de «Aplicar»:** enseña `code`, `pointer` y `msg`, también los nuevos de §4.1.

F2 prueba en el backend que `op.state` lleva `verb: "scene.reset"` y el `reason` de cada caso: `contenido_ajeno` en el reset con algo retenido, y ninguno en el reset limpio, que termina `observado`.

## 7. Aceptación (R26)

**Gate**: el comando único de F1b-web §7 (suite, `npm ci`, build y arnés E2E con P1-P11), desde `DayZSandbox_dev/`, con rc 0. La suite incluye las **pruebas de hoy sin tocarlas** (181 en `a0fa14c`, más las que añada F1b-bridge antes del rebase) más las nuevas, sin fallos ni saltadas, tres corridas seguidas en verde. Las pruebas nuevas usan el `Bridge` real en un hilo con puerto 0, constantes acortadas, reloj inyectado donde haga falta y `tick_s` = 0 salvo donde se diga.

| # | Positivo | Negativo (el defecto que detecta) |
|---|---|---|
| F2-A1 | Escena válida → plan con `plan_sha256` reproducible, filas iguales al documento congelado (D11) y una orden en el bridge; `yaw` 359,9999 → 0,0 en el plan | Con actores → `expansion_unavailable`; clase fuera del catálogo del mundo → `unknown_class` con `/entities/<i>/cls`; `x` por encima del `world_size` del hello → `out_of_map`; sin catálogo → `catalog_pending`; **catálogo completo de un arranque anterior** (otra `inst` o `build`) y el nuevo sin completar → `catalog_pending`; `lid` de 11 caracteres, `lid` con dígitos no ASCII o `rev` de 10 dígitos → `plan_too_large`. En todos, 0 órdenes en `Bridge.orders`, ninguna línea `scene.apply` en el log del bridge y ningún evento (un backend que valida pero despacha) |
| F2-A6 | Escena justo en los topes (20/10/3) → `observado` | Topes bajados después de guardar el documento, uno por uno (`objeto` = 19, `infectado` = 9, `animal` = 2) → `budget_exceeded`; `caps.total` = 30 con 20/10/3 → `budget_exceeded`; en todos, 0 órdenes. Una orden directa al mod con más filas que sus `caps` → `rejected/budget_exceeded` y el censo sin cambios |
| F2-A2 | `escena-sin-actores` → `observado`; el censo tiene el multiconjunto por clase del documento, 33 raíces de Sandbox y cada una a < 0,5 m de `(x_doc, gy, z_doc)`; los infectados y animales también, en el checkpoint, con `tick_s` > 0 y deriva activa | Fila omitida → `fallido/lectura_no_cumple`; `ci` de otra clase → `fallido`; generación con otro `plan_sha256` → `fallido`; creación suprimida → `fallido` y el censo con 32; entidad desplazada 0,6 m → `fallido`; error real de 0,5004 m que el redondeo deja en 0,4999 (posición real `(0,0704, 0, 0,4954)` sobre el objetivo `(0, 0, 0)`) → `fallido`; la misma orden entregada dos veces (`force_double_delivery`) → censo con 33 y creados = 33 |
| F2-A3 | Reset con dos hijos propios (uno en el cargo de `obj-17` y otro soltado en el suelo) → `observado`, sin `reason`; censo con 0 entidades de Sandbox de la escena; segundo reset → `observado` sin efectos; `storage_ops` = 0 | (a) Objeto ajeno en el suelo entre las entidades de la escena → intacto en clase, pose e inventario. (b) Segunda escena (`seed_scene`) → intacta. (c) Ajeno dentro de `obj-17` → `obj-17` sigue en pie, en su pose, con el ajeno dentro y en su pose; el reset termina `parcial/contenido_ajeno` con `obj-17` en `retained` y `op.state` con `verb: "scene.reset"` y ese `reason`; lo demás de la escena, borrado. Un segundo reset → otra vez `parcial/contenido_ajeno`. (d) Ajeno dentro de un hijo propio contenedor dentro de `obj-15` → se quedan los dos contenedores. (e) Hijo de la segunda escena dentro de `obj-16` → `obj-16` se queda. (f) Apply con un contenedor retenido → `fallido/foreign_content_retained` y el censo sin cambios. (g) Ajeno metido en `obj-17` **después** del primer lote de borrados (`barrier_after(8)`) → `obj-17` no se borra y el reset termina `parcial/contenido_ajeno`. En un apply, lo mismo: el apply no crea nada, la lectura enseña restos sin procesar (`n > retained_n`) y la orden termina `parcial/contenido_ajeno`. Con su resultado perdido, la reconciliación llega a lo mismo. (h) `fail_delete` en un reset y en el reset de un apply: sobre `obj-02`, que se borra después de `obj-01` (§13 M1), → `parcial/interrumpida`, `obj-02` sigue registrado y el apply no crea nada (el censo nunca llega a 34); sobre `obj-01`, el primer borrado, → `rejected/delete_failed`, `fallido` y el mundo sin cambios. (i) Orden de reset con el `epoch` viejo tras `restart_mission()` → `rejected/stale_epoch` y el censo sin cambios |
| F2-A4 | Mismo `epoch`: aplicar, cerrar el backend, abrir otro sobre el mismo fichero, reconectar el mod falso, reconciliar y aplicar → `observado`, censo con 33 sin extras, **cada una a < 0,5 m** y el mismo hash del documento. `epoch` nuevo (`restart_mission`) → lo mismo, y el registro vacío justo después del reinicio | Resultado del apply perdido y backend reiniciado antes de recibirlo → el apply nuevo deja 33, no 66. Un `parcial` del `epoch` viejo no provoca ni compensación ni observe en el mundo nuevo. Guardado interrumpido: lo cubre `test_store.py:134` (F1), que debe seguir pasando |
| F2-C | Creación que falla en la fila 12 → `parcial`, y luego `parcial/compensada`; censo con 0 de la escena; la segunda escena, intacta (compensación que no va más allá de su orden) | Con `barrier_after(5)`: cortar el mantenimiento, esperar a que caduque el lease y soltar → `error/lease_expired`, `pending` con 5 y ninguna creación más. Al volver, el backend compensa (`if_pending`) → `parcial/compensada` y el censo con 0. Resultado de la compensación perdido → se vuelve a pedir y termina igual. `fail_delete` permanente sobre una de las 5 → como mucho 3 compensaciones y, sin progreso, `parcial/interrumpida` sin más órdenes. Lectura con `last` = A/`retained` pero una `generation` viva de otra orden, o `retained` vacío → `fallido/lectura_no_cumple`. Plazo vencido durante el reset de la generación anterior y durante una compensación → `interrumpida`. Una compensación con otro `if_pending` → `rejected/not_pending` sin efecto. En el mundo, sin red: registros de **otra orden de la misma escena**, sembrados a mano, sobreviven a la compensación de A |
| F2-R | Resultado de un reset perdido → `parcial/sin_resultado` → la lectura enseña `last` con `done` y escena vacía → `observado/reconciliada`. Resultado de un apply perdido → la lectura enseña su generación → checkpoint → `observado/reconciliada`. Una orden de la `conn` anterior del mismo `epoch` también se resuelve | `last/done` con restos (`n` = 1) → `fallido/lectura_no_cumple`; misma `(session, op_id)` con otra `rev`, otro `hash` u otro `plan_sha256` → `fallido`; checkpoint que no cumple → `fallido`, nunca `observado` por identidad sola; un `parcial` resuelto (`contenido_ajeno`, `compensada`) no mantiene vivas las lecturas |
| F2-O | `POST /api/observe` → `scene.observation` por el SSE y `GET /api/observation`; con el reloj inyectado avanzado 5 s, `age_ms` crece 5000; tras mover una entidad 2 m, la fila `now` lo refleja | Sin peer con escena → 409 `scene_unsupported` y 0 órdenes |
| F2-D1 | Las pruebas de hoy y P1-P11 pasan sin tocarlas; un peer sin `scene` recibe `scene.apply` con `args` `{doc_id, rev, hash}` y `state.read` con `{}` | Una orden F2 `parcial` cuyo servidor vuelve a presentarse **sin** `scene`, en el mismo `epoch`, con una lectura que casa con la identidad F1 pero sin `scene` ni checkpoint → sigue `parcial`, nunca `observado` |

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
- (k) el predicado sin el conjunto de `lid` o sin las clases;
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
- (x) un peer sin `scene` recibe el plan;
- (y) el constructor del plan suma 2 m a las `x` (F1-07);
- (z) se acepta un catálogo de otro arranque;
- (aa) una orden F2 se juzga con el predicado de F1 cuando el peer pierde la capacidad;
- (ab) la compensación se da por hecha con un `done` sin mirar la lectura;
- (ac) sin revisar la retención antes de cada borrado;
- (ad) se crea después de un borrado no confirmado;
- (ae) el predicado sin `EPS_Q`;
- (af) las órdenes sin resolver de otra `conn` no mantienen vivas las lecturas;
- (ag) la reconciliación de reset con `last/done` sin mirar `n`;
- (ah) la compensación filtra solo por escena, no por orden (F2-05);
- (ai) compensaciones sin límite ni detección de falta de progreso (F2-02);
- (aj) `yaw` sin normalizar tras redondear (F2-06);
- (ak) la rama retenida del apply detenido sin exigir `generation` nula ni `retained` no vacío (F2-03);
- (al) un apply detenido por retención durante su reset exige `n == retained_n` (F2-01).

**Terminado cuando:**
1. el gate sale con rc 0 tres veces seguidas;
2. X4 deja todas sus mutaciones muertas;
3. el diff solo toca el write-set de §8;
4. Sol sobre el código congelado no deja pendientes, o el orquestador los arbitra tras 2 rondas;
5. el sha256 de este brief congelado figura en el commit.

## 8. Ficheros

```
DayZSandbox_dev/
  plans/2026-11-14-m1-f2-offline-brief.md   este brief                                          [orquestador]
  app/backend/scene_plan.py                 §4.1 y §4.3: plan, expectativa, validación, envolvente y predicados   [F2-1]
  app/backend/scene_live.py                 §4.4 y §4.5: SceneLive (transiciones de F2, reconciliación y compensación)   [F2-1]
  app/tests/test_scene_plan.py              plan, validación y predicados, sin red                 [F2-1]
  app/tests/test_scene_live.py              SceneLive con llamadas directas sobre un Bridge sin ganchos   [F2-1]
  app/tests/fake_world.py                   §5                                                    [F2-2]
  app/tests/test_fake_world.py              §3.3-§3.5 contra el mundo, sin red                     [F2-2]
  fixtures/escena-sin-actores.json          §5                                                    [F2-2]
  app/backend/bridge.py, app/backend/server.py, app/tests/fake_mod.py   ganchos de §4.6 y §5, tras el merge de F1b-bridge   [F2-3]
  app/tests/test_f2_live.py                 las filas de §7 de punta a punta, con el mod falso con mundo   [F2-3]
```

**No se tocan** `store.py`, `validate.py`, `lease.py`, `app/mcp/`, `app/web/`, el esquema, las fixtures de hoy, ninguna prueba de hoy, `qa/` ni la sonda.

## 9. Entrega

| Tanda | Escribe | Cuándo |
|---|---|---|
| F2-1 | `scene_plan.py`, `scene_live.py`, `test_scene_plan.py` y `test_scene_live.py`: solo ficheros nuevos | ya, en paralelo con F2-2 |
| F2-2 | `fake_world.py`, `test_fake_world.py` y la fixture: solo ficheros nuevos | ya |
| F2-3 | ganchos de §4.6 y §5 y `test_f2_live.py` | con F1b-bridge en `main` y `claude/f2-offline` rebasada encima (y encima de F6-web en `server.py`, si entró antes) |

**Workers** (skill `delegar`): Muse no tiene cupo hasta el 2026-11-16 00:00 UTC. Por la regla de Guillermo, los encargos van a Gemini por `agy`: F2-1 con Argon, F2-2 con Carbon (sin terminal: el gate se lo corre el orquestador), y F2-3 con quien esté libre. Cada tanda trabaja en una copia aparte del commit congelado.

El orquestador:
- revisa el diff, de otra familia que los workers;
- corre el gate y X4 sin fiarse de los recibos;
- integra y hace commit en `claude/f2-offline`.

Después, Sol revisa el código congelado. Push y PR con el gate en verde; el merge, con merge commit, lo hace la sesión principal cuando Sol no deje pendientes (autorización de Guillermo para esta parte, que no toca el PBO).

## 10. Riesgos y lo que no se ha medido

- **El mundo es un modelo.** Esta subfase acredita el contrato y el backend, no el mundo de DayZ. El censo de aquí es el del mundo falso: un mod real que mienta en su lectura solo lo caza el censo independiente en partida (§11).
- **`[verify S-persist]`:** los flags de #11 (§3.7), la vía del checkpoint de Q9, si una prenda o un hijo propio se persiste, y qué reaparece tras reiniciar el servidor. El `restart` del mundo falso no reaparece nada por construcción: **no acredita nada** de A3 «nada reaparece».
- **`[verify S-perf]`:** `SCENE_BATCH` y el TTL de un apply grande. Con 33 raíces y 8 por tick, son unos 5 ticks de creación y otros 5 de borrado.
- **`[verify F2 en partida]`:**
  - la confirmación del borrado en Enforce (`IsPendingDeletion` e `IsSetForDeletion`, S-persist §3.3 pasada 1);
  - el redondeo a 3 decimales y la forma de los números en el JSON del mod real;
  - los rangos de §3.6 sobre el terreno real.
- **Tamaños:** la envolvente de §3.6 vale para los rangos normativos y 33 raíces (34 como mucho). Unos topes mayores (S-perf) o los hijos y actores de F3 obligan a paginar `scene.observe` y el checkpoint. `plan_too_large` y `result_too_large` lo convierten en un rechazo visible, nunca en un truncado.
- **`gy` lo resuelve el propio mod.** El error vertical de A2 se mide contra su `SurfaceY`; el censo de partida lo contrasta con una lectura de suelo independiente.
- **Un apply bloqueado por algo ajeno retenido** obliga al usuario a sacarlo en el juego (D7). Es lo seguro, pero la web de F6 tiene que enseñarlo bien.
- **Orden de entrada:** F2-3 espera a F1b-bridge en `main` y, en `server.py`, a F6-web si su PR llega antes. Los nombres de los ganchos pueden haber cambiado con la ronda de Sol de F1b-bridge; manda la intención de §4.6.

## 11. Continuación: F2 en partida

- **Qué:** `scene.apply`, `scene.reset` y `scene.observe` de §3 en el mod núcleo (Enforce), con el registro, la retención, la confirmación de borrados y los lotes por tick. Encima, el censo independiente antes y después, el reinicio del servidor y el reinicio solo del backend (plan F2, línea 102).
- **Prerrequisitos:**
  - F1b-peers (los peers reales de `dsbx1`);
  - S-persist (flags, vía de Q9 y lo que reaparece);
  - este brief congelado y su código en verde.
- **Gate:**
  - linter offline de Enforce antes de declarar nada;
  - en partida, con el visto bueno de Guillermo para lanzar DayZ: A2, A3 y A4 sobre la escena sin actores, con censo independiente.

## 12. Cambios por la revisión

**Ronda 1 de Sol** (`gpt-6.1-sol`, esfuerzo máximo, solo lectura, sobre `fdcdb27`; veredicto NEEDS-WORK con 8 BLOQ y 3 MAY). El orquestador comprobó cada hallazgo contra el texto y el código, y los aplica todos:

| Hallazgo | Qué cambia |
|---|---|
| F1-01 · BLOQ · `Bridge.catalog` de un arranque anterior certificaba clases del mundo nuevo | Catálogo válido solo para el servidor presentado ahora (D4); gancho en `handle_hello` y `handle_catalog` (§4.6); negativa en F2-A1 y X4 (z) |
| F1-02 · BLOQ · una orden F2 podía reconciliarse con el predicado de F1 si el peer volvía sin `scene` | Contrato fijado por orden (D1); `handle_result` y la reconciliación deciden por la orden (§4.6); negativa en F2-D1 y X4 (aa) |
| F1-03 · BLOQ · el filtro por `conn` de `_has_live_parcial_locked` paraba la recuperación de D8 | «Sin resolver» = mismo `epoch`, cualquier `conn`, y mantiene vivas las lecturas; internas que fallan se vuelven a pedir (§4.5); F2-C y X4 (af) |
| F1-04 · BLOQ · `fail_delete` sin semántica: 34 raíces con un checkpoint perfecto | Confirmación del borrado y `delete_failed` (D5, §3.3, §3.4); nunca crear con lo borrable no vacío (D7); `scene.n` y `retained_n` en el predicado (§4.3); F2-A3 (h) y X4 (ad) |
| F1-05 · BLOQ · la reconciliación no exigía las poscondiciones de la vía directa | Predicados completos de reset y de compensación, iguales en las dos vías; identidad por `(session, op_id)` y después completa (§4.3, §4.5); F2-R, F2-C y X4 (ab), (ag) |
| F1-06 · BLOQ · la retención calculada al empezar se quedaba vieja entre lotes | Retención revisada antes de cada borrado; un apply que la encuentra a mitad para y termina `parcial` (D5, D7, §3.3, §3.4); F2-A3 (g) y X4 (ac) |
| F1-07 · BLOQ · el predicado juzgaba contra el constructor del plan | Expectativa extraída del documento congelado (D11, §4.3); X4 (y) |
| F1-08 · BLOQ · F2-C confundía cortar los polls con un lease caducado | `barrier_after(n)` en el mundo falso (§5); F2-C con barrera, mantenimiento cortado y lease caducado |
| F1-09 · MAY · X4 tenía mutaciones sin una negativa que las matara | Negativas de fila omitida, clase cambiada, solo `plan_sha256`, compensación con otra escena al lado, registro vacío tras reiniciar, IA que se mueve al soltarla, y plazo vencido durante el borrado y la compensación (§5, §7) |
| F1-10 · MAY · los tamaños medidos no eran una cota del contrato | Rangos normativos y envolvente con ellos (§3.6); `plan_too_large` para `lid` largos (§4.1) |
| F1-11 · MAY · el redondeo a 3 decimales dejaba pasar un error real de 0,5004 m | `EPS_Q` = 0,002 m (D12, §4.3); negativa en F2-A2 y X4 (ae) |

Además, el orquestador cambia el reparto (§0, §6, §8 y §9): la web pasa a F6-web, y el cableado de los ficheros de hoy espera a que F1b-bridge esté en `main`. Son cambios de coordinación, no del contrato.

**Ronda 2 de Sol, la última** (misma configuración, sobre `98abe19`; veredicto NEEDS-WORK). Sol da por cerrados F1-01, F1-02, F1-03, F1-04, F1-07, F1-08 y F1-11, deja parciales F1-05, F1-06, F1-09 y F1-10, y añade 2 BLOQ y 4 MAY. Con esta ronda se llega al tope fijado antes de la ronda 1, así que **arbitra el orquestador**: comprueba cada hallazgo, aplica el arreglo que propone Sol y congela el brief.

| Hallazgo | Qué cambia |
|---|---|
| F2-01 · BLOQ · un apply parado por retención durante su reset acababa en `fallido`, contra D7 | Predicado de «apply detenido», que admite restos sin procesar (`n >= retained_n`) (§4.3, §4.4); F2-A3 (g) con resultado perdido; X4 (al) |
| F2-02 · MAY · un borrado que falla siempre provocaba compensaciones sin fin | Como mucho 3 compensaciones y salida terminal sin progreso (§4.5); F2-C; X4 (ai) |
| F2-03 · BLOQ · la rama retenida de la compensación aceptaba una generación viva de otra orden | La rama exige `generation` nula y `retained` no vacío; la regla para limpiar `pending` es la misma en §3.3 y en §3.4; F2-C; X4 (ak) |
| F2-04 · MAY · la envolvente no era normativa (dígitos Unicode, `rev` sin cota) | Textos ASCII, `lid` con dígitos ASCII y cotas de los enteros de la orden; cota calculada con los valores reales (§3.6, §4.1); F2-A1 |
| F2-05 · MAY · F2-C no distinguía una compensación por escena de una por orden | Prueba del mundo con registros de otra orden de la misma escena (F2-C); X4 (ah) |
| F2-06 · MAY · `yaw` 359,9999 redondeaba a 360,0, fuera de rango | Normalización a [0, 360) tras redondear (§3.3); F2-A1; X4 (aj) |

## 13. Aclaraciones de implementación (v1.2.1)

Salen de dos revisiones del código parcial (Claude, de otra familia que los workers) y las arbitra el orquestador. Precisan el contrato donde dejaba hueco; **no cambian ninguna decisión de §2**. Cada una lleva su prueba.

**Backend (`scene_plan.py` y `scene_live.py`):**

| # | Aclaración | Prueba |
|---|---|---|
| A1 | D4 liga el catálogo a la presentación vigente **por `inst`**: tiene que haberse completado después del último hello del servidor y desde su `inst`. No se compara la `build`: en el hello es `retail` o `diag`, y en la página de catálogo es texto libre (F1b-bridge §2.3 y §5). | F2-A1: catálogo de una `inst` anterior → `catalog_pending` |
| A2 | `generation.rev` admite hasta 9 dígitos. No es un contador de [0, 999999]. | `read` con `rev` 1234567 → vale |
| A3 | La prueba de la envolvente exige ≤ `WIRE_CAP` con 33 raíces y los máximos, y `plan_too_large` con 35, no los bytes exactos de la tabla. | F2-A1 |
| A4 | Si `last` es la orden pero con otro `verb` → `fallido/lectura_no_cumple`. | F2-R |
| A5 | `SceneLive` solo juzga con lecturas que reconcilian (`epoch` del servidor presentado y conexión no perdida). | F2-R |
| A6 | **Falla cerrado:** sin `caps` válidos → `budget_exceeded` («sin topes»); el catálogo no vale por defecto; la expectativa sale **siempre** del documento congelado, sin plan B con el documento vivo; un apply o reset F2 exige que el servidor presentado tenga escena. La excepción es el reset sin ningún servidor, que se encola como en §4.2. | F2-A1, F2-A6 y F2-D1 |
| A7 | La capacidad es exactamente el entero JSON `1`. `true` y `1.0` no valen. | F2-D1 |
| A8 | Un primer resultado tardío de una orden F2 `parcial/mundo_reiniciado` sigue F1b-bridge §2.5.4: se aplica. | F2-A4 |
| A9 | Hay como mucho un observe `now` en vuelo. Las peticiones de más reciben el `read_id` del que ya va. | F2-O |
| A10 | **Contrato de los ganchos (F2-3):** `SceneLive` crea la fila de la API de un apply o reset F2 y emite su `op.state`; `Backend.apply` y `Backend.reset` delegan y no crean otra. `handle_result` llama a `SceneLive.on_result_locked` para las órdenes F2 **antes** de marcar `result_seen`. `handle_hello` guarda `scene` en el registro del peer. Las internas (`rd-N`) nunca llaman a `set_op_state`. | F2-3 |
| A11 | Las precondiciones del reset (`doc_changed`, `scene_unsupported` y `queue_full`, que cuenta `scene.reset`) están en `SceneLive.enqueue_reset_locked`. | F2-3 |
| A12 | **Orden superada:** si una orden F2 sin resolver no está en `generation` ni en `pending`, y `last` es una orden de escena **posterior** de esta sesión, en el orden de la cola → `parcial/superada`, terminal, con `origin` `servidor`. Así no hay lecturas sin fin. | F2-R |
| A13 | Toda compensación entregada cuenta para el límite de 3, también una `rejected`. «Sin progreso» se mira en la lectura que sigue a cada compensación. | F2-C |
| A14 | Una orden de escena `rejected` (sin efecto) no cambia `last`, `pending`, `generation` ni `retained`. | F2-A3 (h) |
| A15 | **1023 caracteres por cadena.** El motor corta cada cadena de un JSON leído a 1023 caracteres; lo midió en partida diag F0.3-0 (`JsonSerializer.ReadFromString`). Por eso `scene_plan` rechaza con `plan_too_large` un plan con algún texto de más de 1023 caracteres (clase, `lid` o `doc_id`), con su pointer. En F2 no hay ninguno: §3.6 los acota muy por debajo. | una clase de 1024 caracteres → `plan_too_large` y 0 órdenes |

**Mundo falso (`fake_world.py`):**

| # | Aclaración | Prueba |
|---|---|---|
| M1 | Orden de borrado: la pasada 1 va del hijo más profundo al menos profundo y, a igual profundidad, en el orden del registro; la pasada 2, en el orden del registro, que es el de creación. | F2-A3 (h) |
| M2 | Borrar una entidad borra todo lo que contiene, como en DayZ `[verify S-persist]`. La comprobación de «ajeno intacto» mira también que su padre siga vivo y sea el mismo. | X4 (b) y (c) |
| M3 | Cada verbo guarda el `epoch` de su orden. Antes de cada efecto, con el cerrojo, si el mundo cambió de `epoch` (`restart`), para sin más efectos: `error/stale_epoch`, o `rejected` si aún no hubo ninguno. | `restart` a mitad de un apply → ningún registro ni entidad de la orden vieja en el mundo nuevo |
| M4 | `registry_snapshot()` devuelve el registro entero, sin filtrar por `epoch`, para las pruebas. | X4 (t): registro vacío justo después de `restart` |
| M5 | Una compensación con `if_pending` que se interrumpe deja `last` = `{session, op_id del apply, "scene.apply", "interrupted"}`. | F2-C |
| M6 | Una operación solo toca el `pending` de la orden a la que se refiere. Si el reset de un apply A borra restos de otra orden B, el `n` de B baja, y su `pending` pasa a `null` cuando a B ya solo le quedan registros retenidos. | F2-C |
| M7 | Motivos: la compensación dentro de la orden mantiene `create_failed`; la compensación con `if_pending` usa `delete_failed` si un borrado no se confirma. | F2-C |
| M8 | `barrier_after(n)` espera en el efecto n.º `n`, **fuera del cerrojo**, también cuando `tick` es el callback del peer. | prueba entre hilos: un ajeno metido desde otro hilo mientras el verbo espera, sin bloqueo mutuo y con tope de tiempo |
| M9 | Antes de crear (§3.3 paso 5) se vuelve a leer lo borrable de la escena, sin usar una lista fija. Si no está vacío, no se crea. | hijo propio añadido durante el reset → el apply no crea |
| M10 | La compensación dentro de la orden respeta `SCENE_BATCH`: tick antes de compensar, y el contador de lote sigue. | F2-C: ≤ 8 efectos por tick |
| M11 | `retained_n` y `retained` reflejan la última operación: un apply, reset o compensación que no retiene nada los deja a 0 y `[]`. | F2-A3 |
| M12 | Una creación que falla antes de ningún efecto → `rejected/create_failed`, sin tocar `last`. | F2-C |
| M13 | En un reset, si viene `if_pending` tiene que ser `{session, op_id}` válido; si no → `rejected/bad_args`. El `doc_id` sigue el patrón del esquema. | `if_pending: null` → `rejected/bad_args` sin efecto |
| M14 | Forma del plan: `rev` de 9 dígitos como mucho; `doc_id` con el patrón; `classes` ordenadas, sin repetir y todas usadas. Las pruebas usan `doc_id` válidos (`d-` y 8 hex). | `bad_plan` en cada caso |
| M15 | Filas `now`: `yaw` normalizado; una raíz muerta da nulos en `x`, `y`, `z`, `yaw` y `hp`, y contadores a 0. | F2-O |
| M16 | `seed_scene` nunca amplía el catálogo del mundo: una clase desconocida es un error. | apply con una clase inventada → `unknown_class` |
| M17 | Los ganchos de fallo van por `(doc_id, lid)`. | `fail_delete` en una escena no afecta a la otra |
| M18 | `spawn_orphan_sandbox(cls, x, z)`: una entidad con origen Sandbox que **no** está en el registro. El mod no la toca nunca. | caza mutantes que decidan lo propio por el origen real |
| M19 | **X4 (d):** reset con un hijo contenedor propio dentro de `obj-15` en el que entra algo ajeno durante un tick y sale al siguiente → se retienen los dos contenedores, nunca solo el de dentro. | X4 (d) |
| M20 | El despacho del mod falso con mundo corta a 1023 caracteres cada cadena de los `args` antes de pasarlos a `FakeWorld`, igual que el motor (A15). | una orden directa con un texto de 1030 caracteres llega cortada a 1023 |
