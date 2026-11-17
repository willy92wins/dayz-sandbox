# CO-10 con Claude Code de verdad (2026-11-12)

Guion `app/mcp/CO-10.md`, corrido en el PC de Guillermo (Windows, Python 3.14) por sesión remota, sin DayZ.

| | Primer intento (e4c2fec) | Segundo intento (c585466) |
|---|---|---|
| Suite en Windows | 92/92 OK, 14 s | 93/93 OK, 15 s |
| Claude Code | 2.1.322 | 2.1.322 |
| Paso 6: `changes_since_last_call` trae la tanda humana | **No**: vacío | **Sí**: `b-2`, rev 2, `author.role = human`, «persona mueve el autobús» |
| Paso 7: «aplica la escena» | solo `apply_request`, 0 `op.state` | solo `apply_request`, 0 `op.state` |
| `protocolVersion` negociado | 2025-06-18 | 2025-06-18 |

**Resultado: CO-10 pasa con c585466.**

- Causa del primer fallo: cada `claude -p --resume` arranca una fachada nueva (3 «Connection established» en el debug), y `seen_rev` vivía solo en la memoria del proceso. Arreglo en c585466: sin `seen_rev`, la base es la `base_rev` (o `since_rev`, o `rev`) de la llamada. Prueba `test_fachada_nueva_usa_la_base_de_la_ia`, que falla con la fachada anterior.
- Visto y no arreglado (fuera del alcance de F1-co): con `--allowedTools` limitado a `mcp__dsbx-scene__*`, Claude Code siguió usando Grep y Read de solo lectura sobre el repo para averiguar el formato de las operaciones. Es cosa del cliente, no de la fachada.
- Claude Code pidió una versión más nueva de MCP (los demás servidores negocian 2025-11-25) y aceptó 2025-06-18, la de la fachada por defecto. No se añade 2025-11-25 hasta comprobar qué cambia esa versión.
