1. **MAY — El aviso final puede quedar pendiente para siempre.** [STRACK_Session.c:260](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:260), [STRACK_Session.c:1921](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1921).
   **Escenario:** aparece `stop.txt` durante el tramo 2 con el canal ocupado → `Finish` activa `m_Done` y deja `fin` pendiente → los siguientes `Tick` retornan antes de `FlushPending`. El servidor continúa moviendo la lata indefinidamente. La salida por preflight fallido tampoco envía `fin`.
   **Arreglo:** mantener el vaciado del aviso final después del cierre, con timeout explícito, y emitirlo también al fallar el preflight.

2. **MAY — La lata reutilizada conserva la ubicación del jugador anterior.** [STRACK_Server.c:65](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:65), [STRACK_Server.c:127](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:127), [STRACK_Session.c:1402](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1402).
   **Escenario:** termina una corrida; el servidor sigue vivo y el siguiente jugador aparece 40 m más allá → recibe el identificador correcto, pero la lata conserva su base anterior y queda fuera del barrido de 15 m → termina con `sin_lata`. El reenvío de esta vuelta no asegura los 3 m exigidos por §11.
   **Arreglo:** al registrar una corrida nueva, recolocar la lata respecto al jugador actual y reiniciar su base y temporizador antes de reenviar el identificador.

3. **MAY — El cerrojo del vestido sobrevive al cambio de jugador.** [STRACK_Server.c:82](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:82).
   **Escenario:** una corrida `ropa` deja `s_RopaDone=true`; después entra un personaje nuevo sin accesorios, manteniendo el servidor → `DressRopa` retorna siempre, sin intentar vestirlo ni registrar fallos de creación → las categorías salen ausentes aunque los argumentos sean correctos.
   **Arreglo:** asociar el intento de vestido al jugador y arma de la corrida, reiniciándolo cuando cambien.

Lectura completa y comparación con la base realizadas. Linter: seis ficheros, PASS sin checks omitidos. Firmas contrastadas con el extract vanilla `E:/DayZ-Stable-Extract/1.30.164200/P-scripts`; `P:/scripts` no existe aquí. Sin ejecución en partida: los 4,0 ± 0,3 s siguen sin confirmación en el motor.

RESUMEN: BLOQ=0 MAY=3 MEN=0

PREMISA: el preflight sin capturas no demuestra que se mantengan los FPS durante los giros con captura 1/2. Una corrida podría pasar a 60 FPS inicialmente, caer después y conservar las 20 capturas mínimas para resultar evaluable. El banco debe comprobar también el `dt` efectivo de las ventanas medidas.

