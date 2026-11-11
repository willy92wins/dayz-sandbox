# Co-edición en vivo persona + IA: plan de diseño (lane única, v0)

Fecha: 2026-11-10. Estado: **alcance decidido** (Guillermo, 2026-11-10 12:35Z: «Adelantarla a M1»; spec: punto 5 de M1 y bloque I). Falta Grill Modo B y la revisión de Sol (R22) antes de tocar código.

Petición de Guillermo (2026-11-10): «es importante que tenga integración completa con la IA, para que pueda trabajar a la vez la persona y la IA y se vean en el momento los cambios que se van haciendo».

Marcas: **[V]** leído en el repo o en la fuente · **[I]** inferencia · **[sin verificar]** referente sin comprobar en su fuente.

## 1. Qué cambia respecto al spec y al plan v2

- El spec pone la IA en **M3** y solo como propuesta: H1 «aplicar exige aprobación en la web ligada al hash del plan», H2 «borrador válido y editable, sin ejecutarlo» [V `product-spec.md` §H]. La petición pide algo nuevo: que la IA **edite el mismo borrador a la vez** que la persona y que se vea al momento. Eso es un cambio de alcance (Grill Modo A, workflow §Árbol 1).
- **No cambia** la regla de que la IA nunca ejecuta en el juego sin aprobación: lo que la IA toca es el **documento** (revisión editada); llevarlo al juego (aplicar, GO, quitar del juego) sigue siendo un clic humano (H1, E3).
- El plan v2 ya trae casi toda la base, así que la co-edición es una extensión pequeña y no una arquitectura nueva [V `plans/2026-10-26-m1-cine-v2.md`]:
  - #1: el backend Python es dueño del documento y empuja eventos por **SSE**; la web solo manda operaciones con nombre.
  - #7: operaciones con nombre, deshacer y rehacer del documento, hash SHA-256 y revisión editada distinta de la aplicada.
  - H1: la fachada MCP va **sobre la misma API**, no sobre el juego.
- Consecuencia importante: la IA de la co-edición habla con el **backend de Sandbox**, no con las tools de `dayz-mcp` (que actúan directamente en el juego; #2 y #25 dejan dayz-mcp como patrón y banco de Diag, nunca como runtime del producto). Las fichas MCP siguen siendo casos de prueba (#26).

## 2. Diseño

### 2.1 Una sola fuente de verdad: el registro de operaciones

Todo cambio, venga de la web o de la IA, es una operación con nombre que el backend serializa:

```
POST /api/scene/ops
{ "op_id": "uuid", "base_rev": 41, "batch": "ia-7f3" | null,
  "author": { "kind": "human" | "ai", "id": "web-1" | "mcp-claude", "label": "Tú" | "IA" },
  "ops": [ { "name": "entity.move", "target": "obj-12", "args": { "pos": [x, y, z] } } ] }
```

El backend valida (mismo validador de A1), aplica, sube la revisión (`rev` 42), guarda la operación y su inversa en un registro acotado y lo emite por SSE a **todos** los clientes, el que la mandó incluido:

```
event: scene.op   id: 42
data: { "rev": 42, "op_id": "...", "author": {...}, "batch": "...", "ops": [...], "hash": "sha256..." }
```

Cada cliente pinta lo que llega por SSE, no lo que mandó (sin estado optimista que diverja; la web puede mostrar el arrastre local mientras dura, pero el valor final es el del evento). Así la persona y la IA ven exactamente la misma secuencia y el mismo hash.

### 2.2 Concurrencia: granularidad por campo, la persona manda

- Una operación con `base_rev` atrasada se acepta si ninguna operación posterior tocó el mismo **(entidad, campo)**; si lo tocó, depende del autor:
  - **IA**: se rechaza con `conflict` y el valor actual; la IA relee y decide. Nunca pisa en silencio un cambio humano.
  - **Persona**: gana la última escritura en ese campo (Figma: el servidor es la autoridad y en el mismo campo gana «the last value that was sent to the server» [V 2026-11-11] `https://www.figma.com/blog/how-figmas-multiplayer-technology-works/`).
- Entidad borrada entre medias → `entity_gone`.
- **Bloqueo blando por uso**: mientras la persona arrastra o tiene abierto un campo de una entidad, el backend la marca «en uso por la persona» (latido desde la web) y la IA recibe `busy_human` si la toca. Referente: bloqueo de objetos al editar en Multi-User Editing de Unreal [sin verificar] `https://dev.epicgames.com/documentation/en-us/unreal-engine/multi-user-editing-in-unreal-engine`; la página de Roblox Studio no habla de bloqueos [V 2026-11-11, `https://create.roblox.com/docs/studio/collaboration`], así que el bloqueo blando se queda con un solo referente sin verificar y es sobre todo PROPIO (I2).
- Con la toma armada o rodando no edita nadie (`take_locked`), igual que hoy para la persona (prototipo: «durante la toma no se edita la escena»).

### 2.3 Presencia y autoría visibles

- La IA tiene un color y una etiqueta propios. Lo que acaba de tocar parpadea una vez en el mapa y en la Jerarquía con «IA · hace 2 s»; lo que tiene «en la mano» lleva su insignia. Referente: en Team Create de Roblox, lo seleccionado por cada colaborador se resalta con su color propio [V 2026-11-11, `https://create.roblox.com/docs/studio/collaboration`].
- La Actividad dice quién hizo cada cambio. En la barra de estado, el «MCP apagado» actual pasa a tres estados: apagado, conectado y «IA editando» con botón **Pausar IA** (revoca su credencial al momento; las operaciones en vuelo se rechazan).
- Las operaciones de la IA van en **tandas** con nombre («IA: dos supervivientes al amanecer»). Cada tanda tiene **Deshacer tanda** en la Actividad.

### 2.4 Deshacer

- Ctrl+Z deshace solo las operaciones propias (deshacer por autor [I]: en Figma el deshacer vive en el cliente que hizo el cambio [V 2026-11-11, mismo artículo], de lo que se infiere que cada uno deshace lo suyo).
- «Deshacer tanda» revierte una tanda de la IA con sus inversas. Si la persona cambió después un campo de esa tanda, ese campo no se toca y la Actividad lo dice (nunca pérdida silenciosa).

### 2.5 Transporte y reconexión

- Servidor → clientes: el SSE de #1. Cada evento lleva `id: rev`. Al reconectar con `Last-Event-ID`, el backend repite lo que falta desde el registro; si es más viejo que el registro, manda una instantánea entera con aviso «Escena recargada», nunca un estado a medias.
- Clientes → servidor: `POST /api/scene/ops`. Mismo Host/Origin, credencial y CSRF de E1.

### 2.6 La IA: fachada MCP sobre la API

Proceso aparte y opcional (E3), en Python, que es otro cliente de la misma API con su propia credencial de alcance **solo documento**:

| Tool / recurso | Qué hace |
|---|---|
| `scene_get(since_rev?)` | instantánea o cambios desde una revisión, con autor |
| `scene_ops(base_rev, batch_label, ops[])` | manda una tanda; devuelve `rev` o `conflict`/`busy_human`/`take_locked` con su JSON Pointer |
| `scene_validate(ops[])` | valida sin aplicar |
| `scene_wait_changes(since_rev, timeout_s)` | espera cambios de la persona (long-poll), para los clientes MCP que no tienen notificaciones |
| recurso `sandbox://scene` | con suscripción: avisa `resources/updated` en cada revisión |
| `apply_request(hash)` | **no aplica**: pone en la web una tarjeta «La IA propone aplicar la escena (hash …)»; aplica la persona |

La credencial de la IA no puede aplicar, armar, rodar, parar ni quitar del juego: esos endpoints devuelven 403 y 0 órdenes al bridge.

## 3. Criterios verificables (R26, positivo y negativo)

Propuesta de bloque nuevo en el spec («I — Co-edición en vivo»), con H1 sin cambios:

| # | Positivo | Negativo (el defecto que detecta) |
|---|---|---|
| CO-1 | La persona mueve A mientras la IA añade B: los dos cambios salen en la web y en `scene_get` con el mismo orden de revisiones y el mismo hash; del POST al evento SSE en el otro cliente, p95 < 200 ms en local con 100 operaciones | Un cliente que pinta lo que mandó y no lo que llegó → hashes distintos al final |
| CO-2 | La IA cambia un campo que nadie ha tocado desde su `base_rev` → aceptado | La persona cambió ese campo después → `conflict`, el valor humano sigue y 0 cambios |
| CO-3 | Sin uso humano, la IA mueve la entidad → aceptado | Con la persona arrastrándola → `busy_human`; al soltar y pasar el latido, se acepta |
| CO-4 | Ctrl+Z tras cambios cruzados deshace solo lo humano; «Deshacer tanda» revierte toda la tanda | Tanda con un campo retocado después por la persona → ese campo se conserva y se avisa |
| CO-5 | `apply_request` crea la tarjeta y aplica solo tras el clic humano | Credencial de la IA contra aplicar, GO, parar y quitar → 403 y 0 órdenes en el log del bridge (fixture negativa de H1) |
| CO-6 | Cortar el SSE 5 s con cambios en medio y reconectar → se repiten exactamente los que faltan | Corte más largo que el registro → instantánea con aviso, nunca estado parcial |
| CO-7 | «Pausar IA» → la siguiente operación de la IA se rechaza | Con el proceso MCP apagado, A-D siguen igual (E3) |
| CO-8 | Toma terminada → la IA vuelve a poder editar | Toma armada o rodando → `take_locked` para los dos |

Todos estos se prueban **sin el juego** (backend + web + MCP falso), así que no requieren arrancar DayZ.

## 4. Dónde encaja en las fases

- **F1** (backend y API, aún sin empezar): el registro de operaciones con autor, `rev`, inversas y SSE con `Last-Event-ID`. Es lo que ya pide #7 más tres campos, así que no retrasa F1 [I].
- **Nueva subfase «F1-co»** después de F1, sin juego: reglas de concurrencia (2.2), presencia, deshacer por autor, fachada MCP y CO-1..CO-8 contra un cliente MCP falso.
- **F6** (web completa): presencia, tandas y «Pausar IA» en la interfaz.
- **Ya mismo, en el prototipo**: un «co-editor IA simulado» en `estudio.html` para ver cómo se siente antes de construir backend (la persona edita y una IA falsa añade y mueve cosas con su color). Hay que coordinarlo con el hilo de la interfaz, que tiene el mismo archivo abierto en su PR.

## 5. Fuera de alcance (R25)

- Varios humanos a la vez (el spec deja fuera «varios directores»): el diseño no lo impide, pero no se prueba.
- CRDT u OT completos: con un servidor que serializa y conflictos por campo basta para dos autores.
- Que la IA ejecute en el juego sin aprobación.
- Chat con la IA dentro de la web: la IA entra por su cliente MCP (Claude Code, Claude Desktop…). Se puede añadir después.

## 6. Grill Modo B (Guillermo, 2026-11-11 17:03Z: «1. cliente 2. ok 3. ok 4. ok»)

Gate DPF: la fase traza al bloque I del spec (I1-I5) y a H1. Respuestas:

1. La IA se usa desde el cliente MCP de la persona (Claude Code, Claude Desktop…). La web solo enseña lo que hace la IA; el chat dentro de la web queda fuera de M1 (§5).
2. Mismo campo a la vez: gana la persona; a la IA se le rechaza con `conflict`. Entre ventanas de la persona gana la última escritura (§2.2).
3. «En uso por la persona» = solo mientras arrastra la entidad o tiene uno de sus campos abiertos; seleccionarla no la bloquea (§2.2, CO-3).
4. Antes del backend, el prototipo `ui/prototipo/estudio.html` gana una IA simulada que añade y mueve entidades con su color, sus tandas y «Pausar IA», coordinado con el hilo de la interfaz (§4).

## 7. Pendiente

1. ~~Decisión de alcance~~: en M1, con F1 + F1-co + F6 (2026-11-10).
2. ~~Verificar referentes~~ (2026-11-11): Figma y Roblox verificados; la página de Multi-User de Unreal no trae el detalle de bloqueos, que sigue [sin verificar].
3. Grill Modo B y revisión de Sol (R22) del plan; después, brief de implementación y reparto (Grok/Muse/Argon), con Sol en R21.
