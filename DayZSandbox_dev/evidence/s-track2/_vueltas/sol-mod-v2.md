1. **BLOQ — La parada de la lata puede perderse al entrar en el tramo 4.** [STRACK_Move.c:140](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:140), [STRACK_Session.c:1318](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1318).

   **Escenario:** `suave30_Hb` en el banco cliente-servidor local; al cumplir 30 s, `CanStoreInputUserData()` devuelve falso. El cliente avanza al tramo 4, pero descarta su aviso. El siguiente reenvío periódico puede tardar casi 2 s; entretanto, un salto pendiente del servidor ocurre durante el giro que empieza a los 30,5 s. Sigue incumpliéndose «la lata quieta» de §11. La condición de canal ocupado está documentada en el vanilla `3_game/gameplay.c:130`.

   **Arreglo:** conservar y reintentar el estado pendiente; confirmar la parada del servidor antes de iniciar el reloj del tramo 4.

2. **MAY — El guion comienza antes de disponer del ancla que debe medir.** [STRACK_Session.c:732](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:732), [STRACK_Session.c:1284](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1284).

   **Escenario:** termina el preflight, pero el identificador o la réplica de la `Pot` todavía no está disponible. Ya se ha abierto `samples.jsonl` y fijado `m_T0`; aunque `BuildPoseSuave` devuelve falso, `Capture` sigue pidiendo capturas y registrando poses sin inicializar. Si la lata se resuelve a los 12 s, se entra directamente en el tramo 2: falta el primer tramo completo, y aun así termina con `ok:true` a los 38,5 s. Identificar correctamente la lata no resuelve esta barrera de arranque.

   **Arreglo:** resolver y validar la lata antes de fijar `m_T0` y comenzar las muestras; aplicar un timeout con causa explícita si no aparece.

RESUMEN: BLOQ=1 MAY=1 MEN=0

PREMISA: El contrato conserva contradicciones ya aceptadas por el orquestador: `calib` pide capturas consecutivas, pero hereda 1/10; y `suave30` conserva el umbral de 36 ms frente a los 18 ms literales del brief. No las cuento como defectos nuevos. Además, un preflight sin capturas no garantiza los FPS durante la escritura intensiva de BMP. Los 4,0 ± 0,3 s del giro siguen pendientes de comprobación en motor. Revisé toda la entrega y las ocho lecturas `ctx.Read` están comprobadas; las firmas se contrastaron en `E:/DayZ-Stable-Extract/1.30.164200/P-scripts`, porque `P:` no está montada. No ejecuté DayZ ni escribí ficheros.

