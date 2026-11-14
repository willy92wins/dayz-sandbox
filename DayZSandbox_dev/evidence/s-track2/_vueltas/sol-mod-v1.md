1. **BLOQ — La lata continúa saltando durante los giros.** [STRACK_Server.c:115](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Server.c:115).  
   Ejecutar cualquier `suave*` hasta el tramo 4 → el servidor sigue aplicando `SetPosition` cada dos segundos. No recibe inicio, fase ni parada del cliente; incumple la lata quieta exigida en §11.  
   **Arreglo:** sincronizar el guion con el servidor y detener los saltos antes del tramo 4 y al finalizar.

2. **BLOQ — Las poses de ropa no se toman en H-b.** [STRACK_Session.c:1593](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1593), [STRACK_Session.c:231](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:231).  
   Ejecutar `ropa_Hb` andando o girando → cámara y puntos se guardan en `EOnPostFrame`, pero `RopaJson` consulta las entidades durante el siguiente `OnUpdate`. La línea mezcla momentos distintos y atribuye a Hb poses obtenidas fuera de ese hook. `giro` y `seg` también se consultan al volcar.  
   **Arreglo:** congelar poses, `giro` y `seg` dentro de `Capture`; serializar después únicamente esos valores.

3. **BLOQ — Perder el arma permite aprobar un preflight incompleto.** [STRACK_Session.c:603](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:603).  
   Recoger una muestra de 16,7 ms, quitar el arma y recuperarla cuando el cliente funciona a 20 FPS → se reinicia la espera, pero sobreviven `m_PfStarted`, `m_PfT0` y las muestras. Al reanudarse, `[16,7; 50]` produce p50 = 16,7 ms y arma sin medir diez segundos nuevos.  
   **Arreglo:** invalidar y reiniciar todo el preflight cuando se interrumpan sus condiciones de preparación.

4. **BLOQ — `quat_dot_inicio` mide después del primer paso del filtro.** [STRACK_Session.c:1313](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1313), [STRACK_Session.c:1320](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1320).  
   Iniciar el giro de 170° a 60 FPS → primero se actualiza `m_Filt` y después se calcula el producto. Su magnitud pasa de aproximadamente 0,08716 a 0,16666: el campo describe una respuesta ya filtrada y depende del FPS.  
   **Arreglo:** calcularlo entre la orientación filtrada **anterior** y el objetivo nuevo, antes de modificar `m_Filt`.

5. **BLOQ — La exponencial heredada incumple T-suave ante un frame largo.** [STRACK_Math.c:15](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/3_Game/STRACK_Math.c:15).  
   Un salto de 1 m con `dt=2,4 s` y `smooth_s=0,3` → la serie devuelve un alpha ≈ 0,86769 frente al analítico ≈ 0,99966. El error alcanza el **13,2 % del salto**, superando el 2 % permitido incluso sin inyección. Reproducido aritméticamente en memoria.  
   **Arreglo:** utilizar una evaluación estable de la exponencial para el rango de `dt` admitido.

6. **MAY — La ausencia del punto de mira fabrica lecturas válidas.** [STRACK_Session.c:933](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:933).  
   Si faltan `eye`, `eyepiece`, `lens` y `optic` → se declara `hasMp=true`, se mide el origen y las lecturas b/c se sustituyen por a. El config vanilla declara [`eyeScope`](/E:/DayZ-Stable-Extract/1.30.164200/data/weapon_optics/DZ/weapons/attachments/optics/config.cpp:485), que ni siquiera se prueba. T-ropa puede recibir un punto distinto del detalle marcado y operadores duplicados.  
   **Arreglo:** verificar un punto real del modelo; si falta, emitir `null` y conservar la distinción entre lecturas.

7. **MAY — Puede medirse otra `Pot`.** [STRACK_Session.c:1154](/C:/tmp/dsbx-strack2/mod/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1154).  
   Dejar otra `Pot` sin padre dentro de los 15 m, devuelta primero por el barrido → el cliente la conserva indefinidamente, mientras el servidor mueve la creada para la prueba. La entrada medida queda sin el estímulo previsto.  
   **Arreglo:** comunicar la identidad de la lata creada y esperar a resolver esa entidad antes de medir.

Verificación: código completo y comparación con la base; firmas contrastadas en el extract vanilla 1.30.164200 porque `P:` está ausente. Linter: `PASS`. Todos los `ctx.Read` están comprobados. Sin partida: los 4,0 ± 0,3 s y la semántica temporal nativa de `OverrideAimChangeX` siguen sin confirmarse.

RESUMEN: BLOQ=5 MAY=2 MEN=0

PREMISA: El brief exige p50 ≤ 18 ms, pero también exige `suave30`, cuyo `dt` nominal es 33,3 ms. El contrato lo permite elevando el umbral a 36 ms: contradice el brief prioritario y necesita una excepción explícita. Además, §1 promete captura completa en `calib`, mientras la base suministrada ya captura 1/10; esa discrepancia es heredada.

