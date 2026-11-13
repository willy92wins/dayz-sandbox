# Co-edición en vivo persona + IA: plan de diseño (lane única, v1)

Fecha: 2026-11-10, v1 el 2026-11-11. Estado: **plan v1 cerrado tras la revisión R22 de Sol** (aprobado con cambios, 17 hallazgos, todos incorporados; tabla en §8). Alcance decidido por Guillermo el 2026-11-10 12:35Z («Adelantarla a M1»: punto 5 de M1 y bloque I del spec) y Grill Modo B del 2026-11-11 (§6). Siguiente paso: brief de implementación de F1-co cuando exista el backend de F1.

Petición de Guillermo (2026-11-10): «es importante que tenga integración completa con la IA, para que pueda trabajar a la vez la persona y la IA y se vean en el momento los cambios que se van haciendo».

Marcas: **[V]** leído en el repo o en la fuente · **[I]** inferencia · **[sin verificar]** referente sin comprobar en su fuente · **SOL-Cnn** cambio que sale de la revisión R22 de Sol (§8).

## 1. Qué cambia respecto al spec y al plan v2

- El spec ponía la IA en **M3** y solo como propuesta: H1 «aplicar exige aprobación en la web ligada al hash del plan», H2 «borrador válido y editable, sin ejecutarlo» [V `product-spec.md` §H]. La petición pide que la IA **edite el mismo borrador a la vez** que la persona y que se vea al momento. Es un cambio de alcance, ya decidido.
- **No cambia** la regla de que la IA nunca ejecuta en el juego sin aprobación: la IA toca el **documento** (revisión editada); llevarlo al juego (aplicar, GO, quitar del juego) sigue siendo un clic humano (H1, E3).
- El plan v2 ya trae la base [V `plans/2026-10-26-m1-cine-v2.md`]: #1 backend Python dueño del documento con **SSE**; #7 operaciones con nombre, deshacer, hash SHA-256 y revisión editada distinta de la aplicada; H1 fachada MCP **sobre la misma API**.
- La IA habla con el **backend de Sandbox**, no con las tools de `dayz-mcp`, que actúan directamente en el juego (#2, #25: dayz-mcp es patrón y banco de Diag; #26: sus fichas son casos de prueba).

## 2. Diseño

### 2.1 Una sola fuente de verdad: commits serializados

Todo cambio, venga de la web o de la IA, es una **tanda**: una llamada con una o varias operaciones con nombre, que el backend aplica **entera o nada** (SOL-C04).

```
POST /api/scene/ops
{ "doc": "d-7c1f", "request_id": "uuid", "base_rev": 41, "label": "IA: dos supervivientes al amanecer" | null,
  "ops": [ { "name": "entity.move", "target": "obj-12", "args": { "pos": [x, y, z] } } ] }
```

- **El autor sale de la credencial, nunca del cuerpo** (SOL-C01). La web y la fachada MCP tienen credenciales distintas; el backend sabe por la credencial si es «persona» o «IA». Un cuerpo que diga otra cosa se rechaza con `author_mismatch` y 0 cambios.
- **Una sola sección crítica** en el backend (un candado de commit; el backend es un proceso local) hace, en este orden, todas las comprobaciones finales y el commit (SOL-C11): credencial vigente y no en pausa, toma no armada ni rodando, documento abierto igual a `doc`, base dentro del horizonte (§2.2), conflictos y uso (§2.2), validación A1 sobre el estado provisional, y solo entonces publica a la vez documento, revisión, historial y evento. Pausar la IA, armar la toma y aplicar entran por el mismo candado, así que una operación «en vuelo» o se confirmó antes (y se ve en el registro) o se rechaza.
- **Deduplicación** (SOL-C05): `request_id` repetido con el mismo contenido devuelve el resultado guardado; con otro contenido, `request_conflict`. La fachada MCP genera el `request_id` una vez por llamada de la IA y lo reutiliza en sus reintentos.
- **Identidad** (SOL-C03): cada petición nombra el documento (`doc`); al abrir otro documento, lo que llegue del anterior se rechaza con `doc_changed`. Los ids de entidad no se reutilizan nunca dentro de un documento (el contador sigue aunque se borre la entidad), así que borrar y recrear da otro id.
- Cada commit guarda, por operación, la **huella** (§2.2) y la **inversa calculada desde el estado real justo antes del commit**, no desde `base_rev` (SOL-C06).

Cada cliente pinta lo que llega del servidor, no lo que mandó; la web puede mostrar el arrastre local mientras dura, pero el valor final es el del evento.

### 2.2 Concurrencia: huellas por campo, la persona manda

- **Huella de cada operación** (SOL-C02): el conjunto de (entidad, campo) que lee o escribe. Mover = `pos`; girar = `yaw`; editar campos = esos campos; vestir = `wardrobe`; marcas y gestos = la lista entera; **borrar o sustituir una entidad = existencia + todos sus campos + lo que cuelga de ella** (marcas, gestos, prendas); crear = existencia del id nuevo. Una tanda tiene la unión de las huellas de sus operaciones. El catálogo de operaciones con su huella es parte del esquema de F1.
- **Base atrasada**: se acepta si ninguna operación confirmada después de `base_rev` tiene huella que se cruce con la suya. Si se cruza:
  - **IA**: `conflict` con el valor actual de lo cruzado; la IA relee y decide. Nunca pisa un cambio humano.
  - **Persona**: gana su escritura en ese campo (Figma: el servidor manda y en el mismo campo gana «the last value that was sent to the server» [V 2026-11-11] `https://www.figma.com/blog/how-figmas-multiplayer-technology-works/`).
- **Horizonte** (SOL-C08): el backend guarda las huellas de las últimas N revisiones (N fijo en F1, p. ej. 1000). Una `base_rev` más vieja que el horizonte se rechaza con `stale_base` y el estado actual, sea de quien sea; así nunca se acepta una base cuyo conflicto ya no se puede comprobar.
- **Entidad en uso por la persona** (SOL-C10): la web pide un **préstamo** al empezar a arrastrar una entidad o al abrir uno de sus campos, y no habilita la edición hasta que el backend lo confirma (ida y vuelta local). El préstamo dura 3 s y la web lo renueva cada segundo; si deja de renovarse (pestaña cerrada, corte), caduca solo. Mientras está vivo, la IA recibe `busy_human`. Si caduca con el campo aún abierto, la web lo dice y lo vuelve a pedir; aunque la IA hubiera cambiado algo en ese hueco, al confirmar la persona su cambio gana ella (regla de arriba), así que la caducidad nunca hace perder lo humano. Seleccionar no pide préstamo (Grill 3). Referente del bloqueo: Multi-User Editing de Unreal [sin verificar]; Roblox no lo documenta [V 2026-11-11], así que es sobre todo PROPIO (I2).
- Con la toma armada o rodando no edita nadie (`take_locked`), dentro del mismo candado.

### 2.3 Presencia y autoría visibles

- La IA tiene un color y una etiqueta propios. Lo que acaba de tocar lleva su anillo en el mapa y «IA · hace 2 s» en el mapa y en la Jerarquía durante 10 s. Referente: en Team Create de Roblox, lo seleccionado por cada colaborador se resalta con su color propio [V 2026-11-11, `https://create.roblox.com/docs/studio/collaboration`].
- La barra de estado dice «MCP apagado», «IA conectada», «IA editando» o «IA en pausa» (texto, sin botones: la barra de estado no se toca). **Pausar IA** y **Desconectar** van en la pestaña IA de la Actividad, con las tandas.
- Cada tanda de la IA tiene nombre y **Deshacer tanda**.

### 2.4 Deshacer condicionado por campo

(SOL-C07) Deshacer nunca destruye un retoque posterior de otro autor:

- **Ctrl+Z** deshace la última tanda propia. Por cada campo de su huella: si el valor actual es el que dejó esa tanda, vuelve al de antes; si alguien lo cambió después, se conserva y se avisa («Se conserva el cambio de la IA en el rumbo del Camión V3S»). Rehacer funciona igual y A5 sigue valiendo.
- **Deshacer tanda** (IA) igual, por campo. Una inversa destructiva solo se aplica entera: deshacer la **creación** de una entidad la borra solo si nadie la tocó después; si la persona la retocó, la entidad se queda y se avisa. Deshacer un **borrado** la recrea con su id original solo si ese id sigue libre (lo está siempre, porque no se reutilizan).
- El resultado parcial se dice en la Actividad, nunca en silencio.

### 2.5 Transporte y reconexión

- **Dos contadores distintos** (SOL-C13): la **revisión** del documento (`rev`) sube solo con commits; la **secuencia** del flujo SSE (`seq`) sube con cada evento, sea un commit o un cambio de estado de D2 (pendiente, ejecutando, aplicado, observado…). El `id:` del SSE es `seq`.
- **Reconexión sin huecos** (SOL-C09): con `Last-Event-ID` dentro del registro, el backend repite los eventos que faltan. Si no, manda una **instantánea** con su `rev` y su `seq`, tomada dentro del mismo candado en que el cliente queda suscrito: el cliente guarda los eventos que lleguen mientras instala la instantánea, descarta los de `seq` ≤ la de la instantánea y aplica el resto. Además resincroniza el estado de las órdenes (D2). Un hueco de `seq` o un hash que no casa con el que calcula el propio cliente fuerzan otra instantánea con aviso «Escena recargada».
- Clientes → servidor: `POST /api/scene/ops`, con el Host/Origin, la credencial y el CSRF de E1.

### 2.6 La IA: fachada MCP sobre la API

Proceso aparte y opcional (E3), en Python, otro cliente de la misma API con su propia credencial de alcance **solo documento**. Cliente soportado en M1: **Claude Code** (Grill 1); Claude Desktop entra cuando se pruebe con él (SOL-C17).

| Tool | Qué hace |
|---|---|
| `scene_get()` | el documento actual con `rev`, `doc` y las últimas tandas con su autor |
| `scene_ops(base_rev, label, ops[])` | manda una tanda atómica; devuelve `rev` o `conflict`/`busy_human`/`take_locked`/`stale_base`/`doc_changed` con su JSON Pointer |
| `scene_validate(ops[])` | valida sin aplicar |
| `scene_wait_changes(since_rev, timeout_s)` | espera cambios de la persona, para cuando la IA no tiene nada que hacer |
| `apply_request()` | **no aplica**: pone en la web una tarjeta «La IA propone aplicar la escena» con la revisión y el hash del momento |

- **La IA ve lo de la persona antes de cada acción** (SOL-C17): toda respuesta de la fachada lleva, además de su resultado, «lo que cambió desde tu última llamada» (tandas de la persona con su revisión). Así no depende de que el cliente MCP soporte notificaciones de recursos; la suscripción a `sandbox://scene` queda fuera de M1 hasta medirla en un cliente real.
- La credencial de la IA no puede aplicar, armar, rodar, parar ni quitar del juego: 403 y 0 órdenes al bridge.

### 2.7 Aplicar lo aprobado, no lo último

(SOL-C12) La tarjeta de `apply_request` y el botón «Aplicar escena» de la web llevan la `rev` y el hash que la persona tiene delante. Al pulsar, el backend congela **esa** revisión dentro del candado: si el documento ya no es esa revisión (la IA confirmó algo entre medias), rechaza con `stale_apply`, dice qué cambió y no manda nada; si lo es, aplica esa instantánea y registra como **revisión aplicada** la que se mandó, no la que haya después (#7, D2 #23).

## 3. Criterios verificables (R26, positivo y negativo)

Detallan el bloque I del spec (I1-I5); H1 sin cambios.

| # | Positivo | Negativo (el defecto que detecta) |
|---|---|---|
| CO-1 | La persona mueve A mientras la IA cambia B: en cada revisión, la web y `scene_get` tienen el mismo estado y el hash que **calcula cada cliente** casa con el del servidor. Latencia del POST al evento en el otro cliente: 100 operaciones correlacionadas por `request_id`, reloj monotónico del mismo arnés, perdidas y timeouts cuentan como > 1 s en el denominador (método de E2); p95 < 200 ms (SOL-C14, SOL-C15) | Se inyectan un reordenamiento de dos eventos y una tanda rechazada que el cliente pinta igual: el oráculo por revisión los detecta sin fiarse del hash recibido; 10 operaciones con 300 ms de retraso inyectado hacen fallar el p95 |
| CO-2 | La IA cambia un campo que nadie tocó desde su `base_rev` → aceptado | La persona cambió ese campo después → `conflict`, valor humano intacto y 0 cambios. Igual con huellas estructurales: la IA borra A con base vieja tras un retoque humano de A.pos → `conflict`. Base más vieja que el horizonte → `stale_base` (SOL-C02, SOL-C08) |
| CO-3 | Préstamo confirmado mientras la persona arrastra → `busy_human`; al soltar, la IA entra | Latidos perdidos con el campo abierto → el préstamo caduca, la web lo dice, y el cambio humano confirmado después gana al de la IA; pestaña cerrada → nada queda bloqueado más de 3 s (SOL-C10) |
| CO-4 | Ctrl+Z tras cambios cruzados deshace solo lo humano; «Deshacer tanda» revierte la tanda entera; rehacer vuelve a lo mismo (A5) | Campo retocado después por el otro autor, creación retocada, o escritura humana atrasada que ganó con base vieja → se conserva lo posterior, la inversa sale del estado real y se avisa del parcial (SOL-C06, SOL-C07) |
| CO-5 | `apply_request` crea la tarjeta; aplica la revisión aprobada tras el clic humano y queda como revisión aplicada | La IA confirma una revisión entre la tarjeta y el clic → `stale_apply`, 0 órdenes; credencial de la IA contra aplicar, GO, parar y quitar → 403 y 0 órdenes en el log del bridge (H1, SOL-C12) |
| CO-6 | Corte del SSE con commits y cambios de estado D2 en medio → al volver se repiten exactamente los eventos que faltan, incluidas las transiciones sin cambio de documento (SOL-C13) | Registro forzado a desbordarse con capacidad conocida y N commits → instantánea con aviso, sin perder el commit que cae entre la instantánea y la suscripción (SOL-C09) |
| CO-7 | «Pausar IA» → la siguiente operación se rechaza | Una tanda de la IA detenida entre validación y commit mientras se pausa o se arma la toma → se rechaza; nada se confirma después de la pausa (SOL-C11). La parte offline de E3 (backend sin MCP) aquí; el cierre completo de E3, en la suite de F6 (SOL-C16) |
| CO-8 | Toma terminada → la IA vuelve a editar | Toma armada o rodando → `take_locked` para los dos |
| CO-9 | Una tanda repetida con el mismo `request_id` devuelve el mismo resultado sin duplicar | El mismo `request_id` con otro contenido → `request_conflict`; cuerpo que dice ser «persona» con la credencial de la IA → `author_mismatch`, 0 cambios; petición del documento anterior tras abrir otro → `doc_changed` (SOL-C01, SOL-C03, SOL-C05) |
| CO-10 | Con Claude Code como cliente real, la persona cambia algo y la siguiente respuesta de la fachada a la IA lo trae | Un cliente MCP falso que nunca llama no cuenta como prueba de que la IA ve los cambios (SOL-C17) |

CO-1 a CO-9 se prueban **sin el juego** (backend + web + cliente MCP falso); CO-10 con Claude Code. Ninguno arranca DayZ.

## 4. Dónde encaja en las fases

- **F1** (backend y API, aún sin empezar): commits serializados con el candado, autor por credencial, `doc` y `request_id`, huellas e inversas, horizonte, `rev` y `seq` separados, SSE con reconexión e instantánea, y aplicar por revisión (§2.7). Es lo que ya pide #7 con el contrato más preciso.
- **F1-co** después de F1, sin juego: préstamo de uso, deshacer condicionado, fachada MCP y CO-1..CO-10.
- **F6** (web completa): presencia, pestaña IA, tandas y «Pausar IA» en la interfaz; cierre completo de E3.
- **Prototipo, hecho el 2026-11-11**: IA de ejemplo en `ui/prototipo/estudio.html` (Simular → «IA co-editora conectada»), con color, «IA · hace…», tandas, «Deshacer tanda», «Pausar IA», conflicto, espera por uso, Ctrl+Z por autor y propuesta de aplicar; casos CO-01 a CO-06 en `pruebas-mejoras.js`.

## 5. Fuera de alcance (R25)

- Varios humanos a la vez (el spec deja fuera «varios directores»): el diseño no lo impide, pero no se prueba.
- CRDT u OT completos: con un backend que serializa y huellas por campo basta para dos autores.
- Que la IA ejecute en el juego sin aprobación.
- Chat con la IA dentro de la web (Grill 1). Notificaciones de recursos MCP, hasta medirlas en un cliente real.

## 6. Grill Modo B (Guillermo, 2026-11-11 17:03Z: «1. cliente 2. ok 3. ok 4. ok»)

Gate DPF: la fase traza al bloque I del spec (I1-I5) y a H1. Respuestas:

1. La IA se usa desde el cliente MCP de la persona. La web solo enseña lo que hace la IA; el chat dentro de la web queda fuera de M1.
2. Mismo campo a la vez: gana la persona; a la IA se le rechaza con `conflict`. Entre ventanas de la persona gana la última escritura.
3. «En uso por la persona» = solo mientras arrastra la entidad o tiene uno de sus campos abiertos; seleccionarla no la bloquea.
4. Antes del backend, el prototipo gana una IA simulada, coordinado con el hilo de la interfaz.

## 7. Pendiente

1. Brief de implementación de F1 que incluya §2.1, §2.2 (huellas y horizonte), §2.5 y §2.7, y de F1-co con el resto; reparto entre Grok, Muse y Argon; Sol revisa en R21 al cerrar la fase.
2. Verificar el bloqueo de Multi-User Editing de Unreal en su fuente, o dejar el préstamo como PROPIO.

## 8. Revisión R22 de Sol (2026-11-11) y arbitraje

Sol (`gpt-6.1-sol`, sesión nueva y ciega, solo lectura) sobre la v0 (sha `8a18c736`). Veredicto: **APROBADO CON CAMBIOS**, sin disenso fuerte, 17 hallazgos. Su veredicto decía que bloquean C01-C14 y C17, pero su tabla solo marca BLOQ siete; se arbitra por la tabla. Son hallazgos de diseño, sin código que reproducir: se aceptan leyendo el plan, y cada uno tiene su negativa en §3.

| id | Sol | final | por qué | dónde queda |
|---|---|---|---|---|
| SOL-C01 | BLOQ | BLOQ | Cierto: el autor venía del cuerpo y la IA podía decir que era la persona | §2.1, CO-9 |
| SOL-C02 | BLOQ | BLOQ | Cierto: borrar frente a mover no se cruzaban | §2.2 huellas, CO-2 |
| SOL-C03 | MAY | MAY | Cierto: sin documento ni ids sin reutilizar | §2.1, CO-9 |
| SOL-C04 | MAY | MAY | Cierto; se toma su camino simple: una llamada es una tanda atómica | §2.1 |
| SOL-C05 | MAY | MAY | Cierto: el reintento MCP duplicaba | §2.1, CO-9 |
| SOL-C06 | MAY | MAY | Cierto | §2.1, CO-4 |
| SOL-C07 | BLOQ | BLOQ | Cierto: deshacer podía destruir retoques posteriores | §2.4, CO-4 |
| SOL-C08 | BLOQ | BLOQ | Cierto; se toma su arreglo mínimo, `stale_base` | §2.2, CO-2 |
| SOL-C09 | MAY | MAY | Cierto | §2.5, CO-6 |
| SOL-C10 | BLOQ | **MAY** | El hueco existe, pero no pierde nada humano: aunque caduque el préstamo, el cambio humano confirmado después gana (§2.2). Queda préstamo confirmado con caducidad | §2.2, CO-3 |
| SOL-C11 | BLOQ | BLOQ | Cierto; un candado de commit lo cierra en un backend local | §2.1, CO-7 |
| SOL-C12 | BLOQ | BLOQ | Cierto: aplicar podía mandar una revisión no aprobada | §2.7, CO-5 |
| SOL-C13 | MAY | MAY | Cierto: `rev` y `seq` separados | §2.5, CO-6 |
| SOL-C14 | MAY | MAY | Cierto: dos operaciones que conmutan dan el mismo hash final | CO-1 |
| SOL-C15 | MEN | MEN | Se toma el método de E2 | CO-1 |
| SOL-C16 | MEN | MEN | Cierto: el cierre de E3 es de F6 | CO-7 |
| SOL-C17 | MAY | MAY | Cierto; arreglo propio y más simple que una suscripción: cada respuesta trae lo que cambió la persona; cliente soportado Claude Code | §2.6, CO-10 |

Resultado: 6 BLOQ, 9 MAY y 2 MEN, todos incorporados. El prototipo ya cumplía en pequeño C04 (una tanda a la vez), C07 (por campo, con aviso) y C12 (la tarjeta compara el hash antes de aplicar).
