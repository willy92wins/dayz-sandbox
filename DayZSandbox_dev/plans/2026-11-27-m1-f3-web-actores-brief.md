# F3-web: actores en el estudio (Añadir, Propiedades, marcas y gestos)

2026-11-27 · tarea **F3-web**, rama `claude/project-thread-c4y6r9` (desde `main` `1627463`, con F3-offline 1 y 2 y Desconectar mergeados, PR #31) · spec de implementación (R25) de lo que F6-web parte 1 dejó fuera de su §0 («actores, vestuario y gestos (F3): la biblioteca no ofrece la categoría `actor` y Propiedades enseña los campos de un actor en solo lectura», `plans/2026-11-14-m1-f6-web-1-brief.md:24`) y de la biblioteca de F6 (plan M1 §3 F6: «biblioteca (objetos, vestuario y gestos)») · contrato: `DayZSandbox_dev/product-spec.md` C1, C4, A6 y D1 · v0.1.

**Por qué ahora.** No depende de ningún spike: el almacén ya tiene las operaciones de actor (`entity.add` con `wardrobe/behaviour/roam/marks/gestures`, `entity.set` de `wardrobe/behaviour/roam`, `entity.marks`, `entity.gestures`; `app/backend/store.py:19-20`, `:627-680`, `:847-868`), el validador ya juzga actores (`app/backend/validate.py:334-470`) y el catálogo ya trae clases, vestuarios, prendas y gestos (`fixtures/catalog-m1.json`). Lo que falta es la web. Cuando S3 pase en partida, la persona podrá montar la escena con actores desde el estudio sin tocar JSON (D1). Qué gestos valen lo decide el catálogo (la decisión de Guillermo sobre los gestos de S3 cambia el catálogo, no esta web).

**Proceso.** Brief y oráculo (guion E2E y prueba del backend) los escribe Claude; implementa **Grok** (prioridad de Guillermo hasta el 2026-11-28 ~10:00Z) sin ver otra implementación; el gate offline y las mutaciones corren en la nube (`reference-cloud-gate-m1`). Familia distinta en oráculo e implementación (E9). Sin lanzar DayZ.

## 0. Qué es y qué no

Es:
- `GET /api/catalog` con una clave más, `wardrobe_items` (§2);
- en **Añadir**, la pestaña **Actores** activa: colocar un actor de una clase del catálogo con valores de serie (§3.1);
- en **Propiedades**, un actor editable: nombre, clase, posición y rumbo como cualquier entidad, más **Vestuario** (con sus prendas a la vista), **Comportamiento** y **Radio** (§3.2);
- las secciones **Marcas** y **Gestos** de un actor: añadir, editar y quitar (§3.3, §3.4);
- las pruebas: una prueba del backend, un guion E2E nuevo `actores.e2e.cjs` con las filas AC1-AC8 y el ajuste de la negativa de S6 que esperaba la pestaña desactivada (§5).

No es:
- marcas sobre el **mapa** (D5, necesita S-mapa): se escriben con números;
- el **estado en el juego** del actor (`GET /api/actors/observation`, F3-offline-2): queda para la gate de F3 en partida;
- **Duplicar** un actor: sigue desactivado (`store.ts:1518`), como hoy;
- cambiar el esquema, las fixtures, el validador, el almacén, el bridge, el mod, el adaptador de Expansion ni el product-spec.

Trazabilidad (R20): §2 sale de C1 («multiconjunto exacto... con sus ranuras») y de la biblioteca de vestuario del plan F6; §3 de F6-web 1 §0 línea 24, de C1-C4 y de D1. Lo que no trace a esto no entra; lo que se vea roto fuera, a `bugs.md`.

## 1. Entorno y fronteras

Como F6-web parte 2 §1: gate en la nube (Linux, Python 3.13, Node 22, `NODE_PATH=/opt/node-tools/node_modules`, `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`). Ninguna dependencia nueva: `package.json` y `package-lock.json` no cambian.

**El implementador toca solo**:
- `app/backend/profile.py`: `get_catalog` (§2);
- `app/web/src/**`.

**No toca** (oráculo, lo escribe Claude): `app/tests/test_catalog_actores.py`, `app/web/e2e/actores.e2e.cjs`, `app/tests/e2e_studio.py` (selección `DSBX_GUION=actores`) y la negativa de S6 en `app/web/e2e/studio.e2e.cjs:2803-2811`.

## 2. Backend: prendas de cada vestuario

`GET /api/catalog` (`profile.py:152-182`) añade `wardrobe_items`: un objeto con una clave por cada nombre de `wardrobes` de la respuesta, y como valor la lista de clases de `catalog["wardrobe_items"][nombre]` en el orden del catálogo, solo las que sean cadenas no vacías. Un vestuario sin entrada, o con una entrada que no es lista, lleva `[]`. Sin `wardrobe_items` en el catálogo, todas `[]`. Nada más cambia en la respuesta.

## 3. Web

### 3.1 Añadir → Actores

- La pestaña **Actores** deja de estar desactivada y pierde el `title` «Llega con F3». Su lista sale de `catalog.classes.actor`, con el buscador, la vista previa, el medidor `data-budget="actor"` y el tope (2) como las demás pestañas (F6-web 1 §5.3).
- **Colocar** un actor manda un solo `POST /api/scene/ops` con una sola operación `entity.add` y estos `args`, exactamente: `kind: "actor"`, `cls`, `name: cls`, `x: 7680`, `z: 7680`, `yaw: 0`, `wardrobe`: el primero de `catalog.wardrobes` (la lista viene ordenada), `behaviour: "HOLD"`, `roam: 15`, `marks: []`, `gestures: []`. La etiqueta es «Colocar <cls>», como hoy. Sin vestuarios en el catálogo, la fila del actor queda `aria-disabled="true"` con la nota «El catálogo no tiene vestuarios» y no manda nada.

### 3.2 Propiedades de un actor

- Desaparece el aviso «Actores, vestuario y gestos: llegan con F3». Los campos `cls`, `name`, `x`, `z` y `yaw` se editan igual que en las demás entidades (mismos `id="f-<prop>"`, `data-field`, lease, Intro confirma, Esc deshace, `aria-invalid` sin petición si el valor no vale).
- **Vestuario**: `<select id="f-wardrobe" data-field="wardrobe">` con una opción por cada `catalog.wardrobes`. Cambiarlo manda `entity.set` con `{wardrobe}` en un solo `POST /api/scene/ops`. Debajo, una lista `[data-wardrobe-items]` con un `li` por cada clase de `catalog.wardrobe_items[<vestuario del actor>]`, en ese orden y con el texto literal de la clase; si la lista está vacía o falta, un único `li` con «Sin prendas en el catálogo».
- **Comportamiento**: `<select id="f-behaviour" data-field="behaviour">` con las opciones `HOLD`, `ONCE`, `LOOP` y `ROAM`, tomadas del `enum` del esquema servido. Cambiarlo manda `entity.set` con `{behaviour}`.
- **Radio**: `id="f-roam"`, `data-field="roam"`, numérico, como el rumbo. Un valor ≤ 0, vacío o no numérico queda `aria-invalid="true"` y no manda nada (el esquema dice `exclusiveMinimum: 0`). Válido → `entity.set` con `{roam}`.
- Un valor que el backend rechace (p. ej. un vestuario que ya no está) sale en Validación con su ruta, como las demás ediciones.
- Mientras se edita un campo de esta sección se toma la lease de `(id del actor, campo)`, como con los campos de hoy.

### 3.3 Marcas

Sección `[data-section="marcas"]` con el título «Marcas» y, por cada marca `k` (desde 1, en el orden de `marks`), una fila `[data-mark="k"]` con:
- `#f-mark-k-x` y `#f-mark-k-z`, numéricos, con su `label` («Marca k · X», «Marca k · Z»);
- el botón «Quitar marca k».

Debajo, el botón «Añadir marca». Sin marcas, el texto «Sin marcas».

- **Añadir marca** → un `POST /api/scene/ops` con una sola operación `entity.marks` cuyo `marks` es la lista actual más `{x: <x del actor>, z: <z del actor>}` al final.
- **Editar** una coordenada (Intro o salir del campo con un valor distinto) → una sola operación `entity.marks` con la lista entera y ese valor cambiado. Fuera de `[0, 15360]`, vacío o no numérico → `aria-invalid="true"` y ninguna petición.
- **Quitar marca k**: si algún gesto tiene `at == k`, el botón queda `aria-disabled="true"` (enfocable, clic e Intro no mandan nada) con la nota «La usa el gesto n» (n = el primero de esos gestos, desde 1). Si no, un solo `POST /api/scene/ops` con **dos** operaciones, en este orden: `entity.marks` sin la marca `k`, y `entity.gestures` con cada `at > k` bajado en 1; la segunda solo va si algún gesto cambia.
- Al editar cualquier campo de la sección se toma la lease de `(id del actor, "marks")`.

### 3.4 Gestos

Sección `[data-section="gestos"]` con el título «Gestos» y, por cada gesto `g` (desde 1), una fila `[data-gesture="g"]` con:
- `<select id="f-gesture-g-emote">` con una opción por cada `catalog.emotes`; si el gesto guardado no está en el catálogo, una opción más con su texto literal, seleccionada (el validador lo marcará);
- `<select id="f-gesture-g-when">` con dos opciones: `at` («En la marca») y `t` («A los segundos»), según la clave que tenga el gesto;
- `#f-gesture-g-value`, numérico: el número de marca si `at`, los segundos si `t`;
- el botón «Quitar gesto g».

Debajo, el botón «Añadir gesto». Sin gestos, el texto «Sin gestos». Sin gestos en el catálogo, «Añadir gesto» queda `aria-disabled="true"` y no manda nada.

- Toda edición manda **una sola** operación `entity.gestures` con la lista entera, cada gesto con `emote` y exactamente una de `at` o `t`.
- **Añadir gesto** → la lista más `{emote: <el primero de catalog.emotes>, t: 0}`.
- **Cambiar «cuándo»** de `t` a `at` → ese gesto pasa a `{emote, at: 1}`; sin marcas, la opción `at` está desactivada. De `at` a `t` → `{emote, t: 0}`.
- **Valor**: con `at`, un entero entre 1 y el número de marcas; con `t`, un número ≥ 0. Fuera de eso, vacío o no numérico → `aria-invalid="true"` y ninguna petición.
- **Quitar gesto g** → la lista sin él.
- Al editar cualquier campo de la sección se toma la lease de `(id del actor, "gestures")`.

### 3.5 Lo que no cambia

La Jerarquía ya lista los actores en su grupo; Actividad, Validación, la cola, los atajos, el perfil y la coedición no cambian. Ningún texto que venga del documento o del catálogo se pinta como HTML (S11 de F6-web 1).

## 4. Criterios de aceptación

El cambio está hecho cuando, en la nube, desde `DayZSandbox_dev/`:

1. `python3 -m unittest discover -s app/tests -t app` → 0 fallos (incluida `test_catalog_actores.py`, §5.1).
2. `cd app/web && npm ci --ignore-scripts && npm run build` → 0, sin avisos nuevos de TypeScript.
3. `python3 app/tests/e2e_web.py` → 0 (P1-P9b).
4. `python3 app/tests/e2e_studio.py` → 0 (S1-S12, con la negativa de S6 ajustada).
5. `DSBX_GUION=coedit python3 app/tests/e2e_studio.py` → 0 (C1-C10).
6. `DSBX_GUION=actores python3 app/tests/e2e_studio.py` → 0 (AC1-AC8).
7. Las mutaciones de §6 mueren todas.

## 5. Pruebas (oráculo)

### 5.1 Backend: `app/tests/test_catalog_actores.py`

| Fila | Positiva | Negativa |
|---|---|---|
| K1 | Con `fixtures/catalog-m1.json`: `wardrobe_items` tiene exactamente las claves de `wardrobes` y cada lista es la del catálogo, en orden | — |
| K2 | — | Catálogo con un vestuario sin entrada, otro con una entrada que no es lista y otro con `["A", 3, "", "B"]` → `[]`, `[]` y `["A", "B"]`; sin `wardrobe_items` → todas `[]`; las demás claves de la respuesta, iguales que sin el cambio |

### 5.2 E2E: `app/web/e2e/actores.e2e.cjs` (`DSBX_GUION=actores`)

Escena vacía, 1280×720, como S1-S12. Cada fila empieza con la escena vacía (borrado por `ai_ops`) y cuenta las peticiones a `/api/scene/ops` con `page.on("request")`.

| Fila | Positiva | Negativa (el falso verde que caza) |
|---|---|---|
| AC1 colocar | Pestaña Actores activa; sus filas son `catalog.classes.actor`; colocar `SurvivorF_Linda` → un `POST /api/scene/ops` y en el `snapshot` un actor con los `args` exactos de §3.1; medidor «1 / 2» | Con 2 actores, la fila de una clase `aria-disabled` y clic e Intro → 0 peticiones; con el catálogo sin vestuarios (`page.route` sobre `/api/catalog`) → la nota y 0 peticiones |
| AC2 vestuario | Elegir `medica` en `#f-wardrobe` → `snapshot` con `wardrobe: "medica"`; `[data-wardrobe-items] li` = las 5 prendas de `medica` en orden | Con `wardrobe_items` vacío para ese vestuario (`page.route`) → un solo `li` «Sin prendas en el catálogo»; las prendas siguen el vestuario del documento cuando lo cambia la IA (`ai_ops`) |
| AC3 comportamiento y radio | `#f-behaviour` → `ROAM` y `#f-roam` → `30` + Intro → `snapshot` con los dos | `#f-roam` a `0`, `-5` y vacío → `aria-invalid="true"` y 0 peticiones nuevas |
| AC4 marcas | Añadir marca dos veces → dos marcas en la posición del actor; editar `#f-mark-2-x` a `6200` + Intro → `snapshot` con ese valor y la marca 1 intacta | `#f-mark-1-z` a `20000` → `aria-invalid` y 0 peticiones |
| AC5 quitar marca | Con marcas 1-3 y un gesto `at: 3`: quitar la marca 1 → un `POST` con `entity.marks` y `entity.gestures` en ese orden; `snapshot` con 2 marcas y el gesto en `at: 2` | Quitar la marca 2 con un gesto `at: 2` → botón `aria-disabled`, nota «La usa el gesto 1», clic e Intro → 0 peticiones y documento igual |
| AC6 gestos | Añadir gesto → `{emote: <primero de catalog.emotes>, t: 0}`; cambiar el gesto a `EmoteSalute`, «cuándo» a `at` y valor `1` (con una marca) → `snapshot` con `{emote: "EmoteSalute", at: 1}` y sin `t` | Sin marcas, la opción `at` desactivada; con `at` y valor `2` habiendo una sola marca, `0` o `1.5` → `aria-invalid` y 0 peticiones; `t` = `-1` → igual |
| AC7 quitar gesto y deshacer | Quitar el gesto 1 de 2 → queda el que era el 2; Deshacer de la barra → vuelve el de antes (hash del `snapshot` igual al de antes de quitar) | — |
| AC8 texto hostil y catálogo raro | Un actor puesto por `ai_ops` con nombre `<img src=x onerror="window.__x=1">` y un gesto `"<b>x</b>"` que no está en el catálogo → se ven como texto literal, el `select` del gesto lo enseña seleccionado y Validación da su ruta | Ningún `img[src="x"]` ni `b` nuevo en Propiedades, `window.__x` sin definir; ningún error de JS ni de CSP en la consola |

### 5.3 Ajuste de S6

La negativa «Actores existe, desactivada, con «Llega con F3» en su title» (`studio.e2e.cjs:2803-2811`) pasa a: «Actores existe y está activa, sin ese title». El resto de S6 no cambia.

## 6. Mutaciones

Script `plans/f3web-mutants.py` (lo escribe Claude tras la implementación): cada mutación se aplica sobre el código entregado, se corre solo la fila que la debe matar y se restaura. Mueren todas o el gate no cierra.

| Id | Mutación | La mata |
|---|---|---|
| W1 | La pestaña Actores sigue desactivada | AC1 |
| W2 | `entity.add` de actor sin `marks` (o con `behaviour: "ONCE"`) | AC1 |
| W3 | El tope no se aplica a la pestaña Actores | AC1 |
| W4 | `[data-wardrobe-items]` lee el primer vestuario en vez del del actor | AC2 |
| W5 | `get_catalog` sin `wardrobe_items` | K1, AC2 |
| W6 | Radio sin comprobar `> 0` | AC3 |
| W7 | Editar una marca manda solo esa marca | AC4 |
| W8 | Quitar marca sin bajar los `at` | AC5 |
| W9 | Quitar marca usada por un gesto se permite | AC5 |
| W10 | El gesto con `at` conserva `t` | AC6 |
| W11 | `at` mayor que el número de marcas se acepta en la web | AC6 |
| W12 | El nombre del actor se pinta con `dangerouslySetInnerHTML` | AC8 |

## 7. Entrega

Un commit del oráculo (este brief, §5) y uno de la implementación, separados, en la rama de arriba; después las mutaciones y un PR en borrador. Revisión: lo que se puede probar se prueba (regla de Guillermo del 2026-11-26); sin ronda de Sol salvo que la pida.
