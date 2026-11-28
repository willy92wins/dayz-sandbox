# F3: la foto de actores tiene que caber en el cable (N12)

2026-11-28 · tarea **F3-foto**, rama `claude/project-thread-c4y6r9` (encima de F3-web, PR #33) · arreglo del hallazgo **N12** de la ronda de Sol 6.2 sobre F3-adaptador (PR #32), apuntado en `bugs.md` de esa rama («la foto de actores no cabe en el cable con muchos gestos») · v0.1.

**Qué pasa hoy.** La admisión de F3 (`_actor_errors`, `app/backend/scene_plan.py:332-409`) mide la **orden** de cada actor contra `WIRE_CAP` (3 500 B, `bridge.py:21`), pero no la **foto** que el mod devuelve al observar (`actor.observe`): una fila por actor más hasta tres eventos por gesto (`actor_wire.py:88-139`). Un actor con 64 gestos pasa la admisión (orden de 2 354 B) y su foto mide unos 7 200 B: el mod la cambia por `result_too_large` (`tests/fake_mod.py:592-596`) y la escena nunca se puede juzgar. El fallo sale en partida, tarde y sin decir qué sobra.

**Arreglo.** La admisión rechaza antes de mandar nada una escena cuya **foto peor** no cabe. No cambia el contrato del cable, ni el mod, ni el adaptador, ni el tope.

**Proceso.** Brief y oráculo, Claude; implementa **Grok**; gate offline en la nube. Sin partida.

## 1. Qué se toca

- **Implementador:** solo `app/backend/scene_plan.py` (una función nueva `_actor_photo_len` y su llamada al final de `_actor_errors`).
- **Oráculo (Claude, no se toca):** `app/tests/test_actor_photo_cap.py`.

## 2. La foto peor

`_actor_photo_len(entities, store_catalog, world_size)` devuelve el número de bytes de `compact_json_bytes(env)` (`scene_plan.py:180`), con:

```
env = {"op_id": "rd-999999", "session": "0"*16, "epoch": "0"*32,
       "status": "done", "reason": None, "dup": False,
       "read": {"actors": rows, "gestures": events}}
```

- `rows`: una fila por cada entidad con `kind == "actor"`, en el orden del documento: `[id, cls, X, -MAX_Y_MM, X, 359999, items, 63, "unreachable", 999999999999]`, con `X = int(_xz_limit_mm(world_size))` e `items` = `store_catalog["wardrobe_items"][wardrobe]` si es una lista (si no, `[]`).
- `events`: por cada actor y cada gesto `j` (desde 0) de su `gestures`, tres eventos en este orden: `[id, j, "requested", T, None]`, `[id, j, "playing", T, None]`, `[id, j, "canceled", T, "x"*24]`, con `T = 999999999999`.

Es el peor caso de cada campo según los validadores de `actor_wire.py` (enteros más largos, `mark_st` más largo, causa de 24 caracteres) y la misma envolvente con la que el mod falso mide el resultado (`fake_mod.py:588-592`).

## 3. La admisión

Al final de `_actor_errors`, **solo si no hay ya ningún error**, y si el documento tiene al menos un actor: si `_actor_photo_len(...) > WIRE_CAP`, se añade **un** error `actor_invalid` con `pointer` `"/entities"` y el mensaje `"La foto de los actores (N B) no cabe en el cable."` (N, los bytes medidos). Nada más cambia: ni el orden de los pasos de `validate_for_apply` ni los demás errores.

Sin tope aparte de eventos (512 en `actor_wire.py:26`): con 3 eventos de al menos 30 B cada uno, 512 eventos pasan de 3 500 B mucho antes, así que el tope de bytes ya lo cubre (R25).

## 4. Criterios (oráculo, `test_actor_photo_cap.py`)

| Fila | Positiva | Negativa |
|---|---|---|
| F1 | `escena-basica-cine.json` con motor → `ok` como hoy | — |
| F2 | Un actor `HOLD` con `G` gestos temporizados, donde `G` es el mayor con la foto peor (construida por la prueba, de forma independiente) ≤ 3 500 B → `ok` | El mismo con `G + 1` → `actor_invalid`, un solo error con `pointer` `/entities` y los bytes de la prueba en el mensaje |
| F3 | — | Dos actores con `G // 2 + 1` gestos cada uno (ninguno solo pasa el tope, juntos sí) → `actor_invalid` en `/entities` |
| F4 | — | Un actor con un error propio (vestuario inexistente) y demasiados gestos → solo el error propio, no el de la foto |
| F5 | La foto peor construida por la prueba con `G` gestos pasa `actor_wire.valid_actor_read` (es una foto válida) | — |

Además, todo el gate: `unittest` entero, build y los E2E (P1-P9b, S1-S12, C1-C10, AC1-AC8).

## 5. Mutaciones

| Id | Mutación | La mata |
|---|---|---|
| P1 | Sin la llamada de §3 | F2, F3 |
| P2 | Mide solo el primer actor | F3 |
| P3 | Dos eventos por gesto en vez de tres | F2 |
| P4 | `>=` en vez de `>` | F2 (positiva) |
| P5 | La foto se mide aunque ya haya errores | F4 |
