# Informe S-track·1, repetición con foco — 2026-11-11/12 — INCONCLUSO; S-track·1 NO cierra

Resumen del orquestador (Claude, PC de Guillermo). PBO ded9de6c…e4b9; 17 corridas con el cliente al frente.
- Calibración: PASA en Ha y Hb, con k = −1 único (100 %) y f = 681,7 / 680,7 px.
- Detector: PASA (p95 0,321 px y 0,056°).
- Capturas: con texturas y sin menú de pausa (mosaico `_informe/montage_v13.png`); el mod cerró el menú en 2 corridas (calib_Hb y lookat_Hb_delay1).
- T-lect: la única corrida con cobertura suficiente es mount0_Hb (H-b, 90-100 % por ventana). Las lecturas a, e y f (idénticas entre sí) quedan a 12,4-14,4 px p95 del detalle detectado: FALLA frente a ≤ 2 px. d (hueso) queda a ~150 px; b y c, sin cobertura. En mount0_Ha (cobertura 50-100 %), a, e y f quedan a 90-113 px. Ninguna lectura pasa, así que no hay lectura ganadora y, según el plan §4.2, se vuelve al plan.
- T-hook: INCONCLUSO en todas las corridas (low_coverage o t_lect_inconcluso).
- Negativas: las 6 INCONCLUSO; criterio 4 NO cumple (check_negatives, exit 1).
- Criterios §4: 1 cumple (6 de 6 mutantes muertos); 2 cumple (0 SCRIPT (E) del mod en cliente y servidor); 3 cumple (17 corridas con SHA256SUMS); 4 NO cumple; 5 cumple en parte (calibración decidida; T-lect FALLA en las ventanas observadas, sin ganadora; T-hook INCONCLUSO).

# Informe S-track·1 — INCONCLUSO (exit_code=2)

## 1. Calibración de imagen (`calib`)

| Hook | k | match_frac | f medida px (p05-p95, std, n) | referencia | Veredicto | Causa |
|---|---|---|---|---|---|---|
| Ha | -1 | 1.0000 | 681.69 (681.25-682.66, 0.482, 101) | f000050.bmp | PASA |  |
| Hb | -1 | 1.0000 | 680.7 (680.63-685.64, 1.421, 88) | f000290.bmp | PASA |  |

## 2. Calibración del detector

- `p95_px`: 0.3209 px (máx 0.5 px)
- `p95_deg`: 0.0562° (máx 0.1°)
- Veredicto: **PASA**

## 3. Decisiones

- **Lectura ganadora (T-lect):** `None`
- **Desfase k por hook:** `{"Ha": -1, "Hb": -1}`
- **Hook por modo (T-hook):** `{"mount0": null, "mount03": null, "lookat": null, "follow": null}`

## 4. Resultados por ventana

108 filas; columnas: run | medida | lectura | ventana | p95_px | roll_deg | cobertura | veredicto | causa

| Run | Medida | Lectura | Ventana | p95_px | roll_deg | Cobertura | Veredicto | Causa |
|---|---|---|---|---|---|---|---|---|
| mount0_Ha | T-lect | a | giro1 | 110.4264 | 20.5515 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | T-lect | a | giro2 | 90.4161 | 10.8029 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | a | giro3 | 113.0746 | 21.9869 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | a | resto | 103.7491 | 22.7648 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | b | resto | 148440.6001 | 145.9787 | 0.3571 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | d | giro1 | 533.0715 | 13.8861 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | T-lect | d | giro2 | 526.2272 | 3.9673 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | d | giro3 | 516.7716 | 14.9835 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | d | resto | 560.9938 | 17.0339 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | e | giro1 | 109.938 | 20.609 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | T-lect | e | giro2 | 90.6251 | 10.6861 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | e | giro3 | 113.0746 | 21.9869 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | e | resto | 103.7491 | 23.2181 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | f | giro1 | 109.938 | 20.609 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | T-lect | f | giro2 | 90.6251 | 10.6861 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | f | giro3 | 113.0746 | 21.9869 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-lect | f | resto | 103.7491 | 23.2181 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | a | giro1 | 12.4029 | 3.1721 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | a | giro2 | 13.028 | 3.3063 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | a | giro3 | 12.6162 | 3.2259 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | a | resto | 14.1954 | 3.5118 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | b | giro2 | 29819.2205 | 106.9789 | 0.3333 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | b | giro3 | 5940.2821 | 38.6037 | 0.3333 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | b | resto | 21097.361 | 120.7877 | 0.3171 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | d | giro1 | 148.891 | 5.7978 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | d | giro2 | 150.8863 | 6.1558 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | d | giro3 | 149.4598 | 5.9722 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | d | resto | 153.0645 | 6.0571 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | e | giro1 | 12.4029 | 3.1721 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | e | giro2 | 13.028 | 3.4562 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | e | giro3 | 12.6162 | 3.4394 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | e | resto | 14.4224 | 3.9907 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hb | T-lect | f | giro1 | 12.4029 | 3.1721 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | f | giro2 | 13.028 | 3.4562 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | f | giro3 | 12.6162 | 3.4394 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | T-lect | f | resto | 14.4224 | 3.9907 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | a | resto | 0.0475 | 0.0051 | 0.0222 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | d | resto | 688.2829 | 17.3341 | 0.0222 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | e | resto | 0.0475 | 0.0051 | 0.0222 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-lect | f | resto | 0.0475 | 0.0051 | 0.0222 | INCONCLUSO | low_coverage |
| follow_Ha | T-hook | None | giro1 | 0.4263 | 0.1125 | 0.5 | INCONCLUSO | low_coverage |
| follow_Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| follow_Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| follow_Ha | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| follow_Hb | T-hook | None | giro1 | 73.3039 | 1.3162 | 0.3333 | INCONCLUSO | low_coverage |
| follow_Hb | T-hook | None | giro2 | 78.6819 | 8.243 | 0.5 | INCONCLUSO | low_coverage |
| follow_Hb | T-hook | None | giro3 | 80.1862 | 0.1348 | 0.3333 | INCONCLUSO | low_coverage |
| follow_Hb | T-hook | None | resto | 48.9079 | 1.8657 | 0.4787 | INCONCLUSO | low_coverage |
| lookat_Ha | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Ha | T-hook | None | giro3 | 1.2701 | 0.0528 | 0.3333 | INCONCLUSO | low_coverage |
| lookat_Ha | T-hook | None | resto | 0.626 | 0.4491 | 0.3158 | INCONCLUSO | low_coverage |
| lookat_Hb | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Hb | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Hb | T-hook | None | resto | 0.5741 | 0.3098 | 0.1053 | INCONCLUSO | low_coverage |
| mount03_Ha | T-hook | None | giro1 | 223.6252 | 92.6103 | 0.1429 | INCONCLUSO | low_coverage |
| mount03_Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount03_Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount03_Ha | T-hook | None | resto | 146.452 | 34.3288 | 0.0547 | INCONCLUSO | low_coverage |
| mount03_Hb | T-hook | None | giro1 | 180.4283 | 20.9863 | 0.3333 | INCONCLUSO | low_coverage |
| mount03_Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount03_Hb | T-hook | None | giro3 | 200.0394 | 20.9128 | 0.3333 | INCONCLUSO | low_coverage |
| mount03_Hb | T-hook | None | resto | 138.7986 | 11.2532 | 0.025 | INCONCLUSO | low_coverage |
| mount0_Ha | T-hook | None | giro1 | 178.3985 | 45.2646 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Ha | T-hook | None | giro2 | 149.2036 | 35.4726 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-hook | None | giro3 | 181.37 | 46.2586 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | T-hook | None | resto | 169.6957 | 43.3752 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Hb | T-hook | None | giro1 | 91.7272 | 23.8643 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Hb | T-hook | None | giro2 | 95.8349 | 25.2015 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Hb | T-hook | None | giro3 | 92.4712 | 23.9391 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Hb | T-hook | None | resto | 91.5233 | 24.1175 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hc | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | T-hook | None | resto | 70.6191 | 18.3629 | 0.0222 | INCONCLUSO | low_coverage |

## 5. Negativas

| Run | Inyección | Esperado | Obtenido | OK |
|---|---|---|---|---|
| lookat_Ha_delay1 | delay1 | FALLA | INCONCLUSO | False |
| lookat_Hb_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Ha_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Ha_roll | roll | FALLA | INCONCLUSO | False |
| mount0_Hb_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Hc_delay1 | delay1 | FALLA | INCONCLUSO | False |

## Anexo del orquestador: desviaciones del brief v1.0 y hallazgos

Corrida del 2026-11-10 en el PC de Guillermo. Base `eea096b9`, merge en `C:\tmp\dsbx-strack\merge` (sin commit).

### Desviaciones (cada una con motivo y quién la decidió)

1. **Banco.** No es el de dayz-mcp: `dayz_test_run` no acepta argumentos de cliente (ni `-autotest` ni `-strack=`; dayz-mcp README.md:167 y dayz-mcp-architecture.md §11). Instancia propia lanzada por WMI como el probe del 2026-11-03: DayZDiag 1.30, puerto 2402, perfiles y misión en `C:\tmp\dsbx-strack\bench`. Sin lease de dayz-mcp: esa instancia queda fuera de su lifecycle guard. LIVE y T130 no se tocaron. Cierre con WM_CLOSE, solo de los PID lanzados. Decidido por el hilo, opción (b).
2. **Movimiento.** No con `player_move`, porque no se puede usar fuera de un run gestionado, y además no gira el cuerpo («The camera is not turned»). Lo mueve el modo `-strack_move=self` del mod: OverrideMovementSpeed/Angle para andar y **OverrideAimChangeX** (human.c:259) en lazo cerrado sobre el rumbo para girar 180° en el sitio, en dueño y servidor por ScriptInputUserData. El giro lo escribí yo en el merge (decisión del hilo). Medido: giros de 180° en ~1,75 s, con el rumbo final a menos de 3° del objetivo.
3. **H-b.** No es una entidad propia de cliente: es `modded PlayerBase.EOnPostFrame` (super, y luego solo si `this` es el jugador local). Motivo en el hallazgo 2. Decisión del hilo, opción (a).
4. **Calibración, §2 y §3 (brief v1.1 B).** El patrón 10°/0° en pares/impares tiene periodo 2: k y k±2 son indistinguibles. Se cambió por una secuencia pseudoaleatoria con semilla fija (dos pasos LCG mod 65536 del número de frame, semilla 12345; `CalibBit`, STRACK_Session.c), escrita por frame en `calib_yaw_deg`. Se captura 1 de cada 10 frames, 200 capturas. Referencia: la primera captura estable (luminancia media < 200 y variación ≤ 2 % en 10 seguidas). Decisión del hilo.
5. **Focal (brief v1.1 C).** Ningún convenio de FOV supuesto: f = desplazamiento / tan(10°), medida en calib, con p05-p95, std y n en el informe. Decisión del hilo.
6. **Medida del desplazamiento en calib.** El §3 pide «correlación horizontal de bandas». En las capturas reales la de Argon daba de −81 a −163 px para el mismo giro, y con ella k no pasaba del 88,7 %. Se cambió por correlación de fase 2D sin la franja inferior del HUD (`_phase_shift_x`), que da dos grupos limpios: 0 y 120-121 px. Decisión mía; tests del evaluador 6/6 después.
7. **`_shot_path` en el evaluador.** Los BMP se convierten a PNG sin pérdida (píxeles idénticos comprobados uno a uno con numpy `array_equal` antes de borrar el BMP). El evaluador abre el PNG cuando falta el BMP nombrado en `shot`. Cambio mío, de 10 líneas. El sha256 de la evidencia va sobre los PNG.
8. **Posiciones relativas a un origen.** `float.ToString()` da ~6 cifras significativas, es decir 1 cm a x≈8400 m, hasta ~11 px a 0,6 m de la cámara. Las posiciones se escriben relativas a un origen de metros enteros fijado al armar (`origin` en cada línea). Límite que queda: el float32 del motor, ~1 mm, es decir ~1 px a 0,6 m. Todas las corridas de medida se repitieron con esto; las anteriores están archivadas y no se evalúan.
9. **60 fps.** `-limitFPS=60` limita la media (58,7 fps con foco) pero no es un tope por frame, y sin foco el cliente baja a ~20 fps. No se robó el foco. FPS y dt reales de cada corrida: anexo de FPS.
10. **Arreglos del mod en el merge (Grok no tenía shell):** `local` como nombre de variable (Enforce lo rechaza; lo vio el linter); `m_File = 0` sobre `FileHandle`, que es `typedef int[]` (ensystem.c:390; error de compilación real); firma de `ConsumeMove` (`protected override event`, pawn.c:274); `fov_motor` = `Camera.GetCurrentFOV()` en cada muestra (camera.c:13).
12. **`lookat` (§2), decisión del hilo del 2026-11-11.** En `lookat` el jugador no anda: solo gira tres veces en el sitio, con 1 s quieto entre giros, y la cámara fija va a 1,3 m del punto de giro (antes 4 m). Motivo: con f = 684 px y 0,408 m entre boca y recámara, 200 px exigen ≤ 1,40 m con el arma perpendicular, y con el jugador andando no hay distancia fija que lo cumpla. En `follow`, offset de 1,2 m detrás y 0,3 m arriba (antes 2,0/0,5), con 233 px de mediana sobre las muestras reales.
13. **Evaluador, 2026-11-11 (orquestador):** segmentación de giros (> 90° monótonos y ≥ 0,5 s); plantilla de 32 px (antes 48) con un banco de giro ±2° y escala ±5 %; capturas sin textura (std del recorte < 15) o de carga (media ≥ 200) cuentan como no observadas; arreglos de la ruta PNG y de la primera captura con k = −1 en `_detect_run_shots`. Mod: espera de 60 s con el arma en manos (`-strack_wait`) y cierre del menú de pausa.
11. **Tamaño.** El mod tiene ~1600 líneas de Enforce frente a las <600 orientativas: el modo self y el giro suman ~350.

### Hallazgos

1. **FOV efectivo.** `Camera.SetFOV(1.0471976)` (60°) a 1920×1080 da f ≈ 684 px medida en calib, es decir ~76,6° de FOV vertical efectivo (~109° horizontal). Ni 60° vertical (935 px) ni 60° horizontal (1663 px). Valor que da el motor (`fov_motor`): ver la tabla de calib. Importa para F4 y para el FOV en radianes del documento de escena.
2. **Entidades ECE_LOCAL sin eventos por frame.** Tres intentos de entidad propia de cliente para H-b, ninguno recibió FRAME ni POSTFRAME: (i) House con config HouseNoDestruct, frames=0; (ii) ScriptedEntity, que no se puede crear porque vanilla no tiene `CfgVehicles/ScriptedEntity` (RPT: «No entry 'config.bin/CfgVehicles/ScriptedEntity.scope'»); (iii) ItemBase local (config Inventory_Base) con `ECE_LOCAL`, máscara 66 tras crearla y 82 tras poner POSTFRAME|FRAME, flags 512 y 513 (ACTIVE), visible u oculta: ni un EOnFrame ni un EOnPostFrame en ~80 s. `PlayerBase.EOnPostFrame` sí llega: 1 invocación por frame en las corridas Hb.
3. **Asociación captura-frame.** Con la calibración nueva, k = −1 en Ha (100 % de coincidencia, único): la captura pedida en el frame n muestra la vista escrita en el frame n−1.

## Anexo del orquestador: FPS y dt reales por corrida

Calculado de `samples.jsonl` (una fila por frame; en Hb se toma una por frame). Ventanas de 1 s por dt acumulado; ~60 = media ≥ 40 fps, ~20 = media < 30 fps.

| corrida | frames | dt p50 ms | dt p95 ms | fps medio | s a ~60 | s a ~20 | s otro | frac dt<15,5 ms |
|---|---|---|---|---|---|---|---|---|
| calib_Ha | 1991 | 52.0 | 54.0 | 19.2 | 0 | 99 | 0 | 0.000 |
| calib_Hb | 1991 | 52.0 | 54.0 | 21.6 | 4 | 81 | 3 | 0.044 |
| follow_Ha | 486 | 52.0 | 54.0 | 19.2 | 0 | 24 | 0 | 0.000 |
| follow_Hb | 1114 | 17.0 | 52.0 | 44.8 | 16 | 8 | 0 | 0.156 |
| lookat_Ha | 264 | 52.0 | 53.0 | 19.2 | 0 | 13 | 0 | 0.000 |
| lookat_Ha_delay1 | 271 | 52.0 | 54.0 | 19.1 | 0 | 13 | 0 | 0.000 |
| lookat_Hb | 268 | 52.0 | 53.0 | 19.2 | 0 | 13 | 0 | 0.000 |
| lookat_Hb_delay1 | 261 | 52.0 | 54.0 | 19.0 | 0 | 13 | 0 | 0.000 |
| mount03_Ha | 1517 | 17.0 | 29.0 | 60.0 | 25 | 0 | 0 | 0.219 |
| mount03_Hb | 481 | 52.0 | 54.0 | 19.1 | 0 | 24 | 0 | 0.000 |
| mount0_Ha | 475 | 52.0 | 54.0 | 19.1 | 0 | 23 | 0 | 0.000 |
| mount0_Ha_delay1 | 484 | 52.0 | 54.0 | 19.2 | 0 | 24 | 0 | 0.000 |
| mount0_Ha_roll | 492 | 52.0 | 54.0 | 18.9 | 0 | 24 | 0 | 0.000 |
| mount0_Hb | 497 | 52.0 | 54.0 | 19.1 | 0 | 24 | 0 | 0.000 |
| mount0_Hb_delay1 | 1535 | 17.0 | 27.0 | 60.0 | 25 | 0 | 0 | 0.201 |
| mount0_Hc | 503 | 52.0 | 54.0 | 19.1 | 0 | 25 | 0 | 0.000 |
| mount0_Hc_delay1 | 504 | 52.0 | 54.0 | 19.2 | 0 | 25 | 0 | 0.000 |

## Anexo del orquestador: separación boca-recámara en pantalla

Lectura (a), f = 681,7 px (calib Ha de esta tanda), pose del frame n−1 (k = −1). Mediana y p05 sobre los frames con captura.

| corrida | capturas | sep. mediana px | sep. p05 px |
|---|---|---|---|
| calib_Ha | 200 | 106 | 43 |
| calib_Hb | 200 | 102 | 33 |
| follow_Ha | 49 | 232 | 231 |
| follow_Hb | 112 | 232 | 231 |
| lookat_Ha | 27 | 186 | 102 |
| lookat_Ha_delay1 | 28 | 223 | 77 |
| lookat_Hb | 27 | 224 | 74 |
| lookat_Hb_delay1 | 27 | 222 | 80 |
| mount03_Ha | 152 | 350 | 125 |
| mount03_Hb | 49 | 316 | 204 |
| mount0_Ha | 48 | 222 | 220 |
| mount0_Ha_delay1 | 49 | 196 | 179 |
| mount0_Ha_roll | 50 | 222 | 220 |
| mount0_Hb | 50 | 222 | 220 |
| mount0_Hb_delay1 | 154 | 204 | 198 |
| mount0_Hc | 51 | 222 | 220 |
| mount0_Hc_delay1 | 51 | 197 | 180 |

## Anexo: FOV que da el motor

| corrida | fov_motor | frames |
|---|---|---|
| calib_Ha | 1.0472 | 1991 |
| calib_Hb | 1.0472 | 1991 |
| follow_Ha | 1.0472 | 486 |
| follow_Hb | 1.0472 | 1114 |
| lookat_Ha | 1.0472 | 264 |
| lookat_Ha_delay1 | 1.0472 | 271 |
| lookat_Hb | 1.0472 | 268 |
| lookat_Hb_delay1 | 1.0472 | 261 |
| mount03_Ha | 1.0472 | 1517 |
| mount03_Hb | 1.0472 | 481 |
| mount0_Ha | 1.0472 | 475 |
| mount0_Ha_delay1 | 1.0472 | 484 |
| mount0_Ha_roll | 1.0472 | 492 |
| mount0_Hb | 1.0472 | 497 |
| mount0_Hb_delay1 | 1.0472 | 1535 |
| mount0_Hc | 1.0472 | 503 |
| mount0_Hc_delay1 | 1.0472 | 504 |
