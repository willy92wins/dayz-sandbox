# Lane A — dudas (brief v0.1 sin decidir)

- `t_ms` de fila y de evento: uso `(int)(g_Game.GetTickTime() * 1000.0)` (reloj de S3). El disparo por tiempo sí resta el instante de creación.
- Transición a `playing`: `oldState == 0 && newState != 0` (STATE_NONE vanilla = 0). No puse el token `STATE_NONE` en el motor porque no está en ámbito fuera de `EmoteCB`.
- `Stop` de `lid` desconocido: `"unknown_actor"`. `Despawn` desconocido: `""` (idempotente, como el brief).
- `SetMarks` con actor vivo pero `GetGroup()` nulo: actualizo estado local y devuelvo `""` (el brief no da código).
- ROAM: un solo `AddWaypoint` al destino (texto del brief). S3 mandaba posición actual + destino.
