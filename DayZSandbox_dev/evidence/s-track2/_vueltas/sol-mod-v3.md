- **BLOQ — El reenvío periódico todavía puede deshacer la parada de la lata.** [STRACK_Session.c:288](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:288), [STRACK_Move.c:191](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Move.c:191).
  
  Escenario: se envía tramo 4 correctamente; desaparece el pendiente, pero `m_Tramo` permanece en 3 hasta consumir el ACK. Si coincide entonces el reenvío de 60 ticks, vuelve a enviarse 3. El servidor acepta ese retroceso en `STRACK_Move.c:238`; el cliente puede aceptar el ACK anterior y comenzar el tramo 4 con la lata nuevamente libre para saltar.
  
  **Arreglo:** desde `m_Tramo4Req`, los reenvíos deben comunicar 4. Impedir también el retroceso 4→3 dentro de la misma corrida.

- **MAY — Repetir una corrida conservando el servidor deja al cliente sin identificador de lata.** [STRACK_Server.c:96](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:96), [STRACK_Session.c:1383](C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1383).
  
  Escenario: ejecutar `suave30`, cerrar el cliente y lanzar `suave60` manteniendo el servidor 2402. `s_Pot` ya existe y su identificador solo se envía dentro del bloque de creación. El cliente nuevo tiene `s_PotIdOk=false`: `FindLata` devuelve siempre `null` y el armado termina con `sin_lata` tras diez segundos, aunque la lata esté replicada.
  
  **Arreglo:** reenviar al dueño el identificador de la lata existente al registrar la nueva corrida.

RESUMEN: BLOQ=1 MAY=1 MEN=0

PREMISA: El preflight sin capturas no demuestra que los FPS se mantengan al pedir BMP cada dos frames. Deben comprobarse también durante los giros antes de atribuir errores a lecturas o hooks. Revisión estática: firmas contrastadas con el extract vanilla `E:\DayZ-Stable-Extract\1.30.164200\P-scripts`; `P:` no está montada y no se ejecutó DayZ.

