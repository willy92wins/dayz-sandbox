VEREDICTO: NEEDS-WORK
BLOQ=2 MAY=2 MEN=0

## Cierre de la vuelta 1

| Punto | Estado | Evidencia y conclusión |
|---|---|---|
| H1: mezcla de relojes | **A MEDIAS** | [s_track_eval.py:2304](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2304) usa correctamente Σdt, pero la protección de [2410](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2410) solo mira fronteras y deja pasar la compensación durante el transitorio descrita en B1. |
| H2: carga | **CERRADO** | [s_track_eval.py:2111](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2111) excluye exactamente 0→1 de FPS y [check_runs.py:216](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:216) solo lo exime de deriva; los dos extremos originales quedan rechazados. |
| H3: duplicados | **CERRADO** | [check_runs.py:190](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:190) conserva la última fila canónica y rechaza diferencias de `dt` o `t_ms`, cerrando el ocultamiento original. |
| H4: `NaN` | **CERRADO** | El parser de [check_runs.py:87](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:87) rechaza constantes y flotantes no finitos, y [166](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:166) valida cada fila antes de deduplicar o excluir. |
| Umbral de 50 ms | **A MEDIAS** | La explicación de [check_runs.py:37](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:37) ya considera consumidores de pared, pero falta acotar la incertidumbre de los intervalos que alimentan el filtro: B1 demuestra que bastan 14 ms admitidos para cambiar el veredicto. |

## Decisiones nuevas

**Guarda de 6 ms.** Puede retirar medidas correctas con discrepancias que el banco ya produce. Además, su interacción con el acuerdo entre FPS puede producir un **PASA falso** —B2— y su aplicación a `s0` oculta fallos independientes del reloj —M1—.

Cálculo sobre [real_clock_calib.json:1](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/fixtures/real_clock_calib.json:1), excluyendo carga:

| Calibración | Frames afectados | `dt`, ms | `Δt_ms`, ms | Desacuerdo absoluto, ms |
|---|---|---|---|---|
| Ha | 422, 423 | 8; 32 | 36; 5 | **28; 27** |
| Hb | 383, 384 | 21; 16 | 31,010; 7 | **10,010; 9** |

Son **4 de 2038 pares posteriores a carga**, un **0,196 %**. Si cada par coincidiese con la frontera de una ventana distinta, quedarían **cuatro ventanas INCONCLUSAS**. Son dos episodios de tirón con dos pares consecutivos cada uno: si ambos pares pertenecen a la misma ventana, esa ventana se cuenta una vez. La fixture contiene calibraciones, no cuatro ventanas suaves observadas.

Incluyendo carga serían **6 de 2040 pares**; los dos adicionales terminan en el frame 1.

**Límite de 100 ms.** Las calibraciones actuales pasan: máximos de 39 ms en Ha y 48 ms en Hb. El límite puede excluir una corrida coherente y evaluable —M2—; por sí mismo solo añade rechazos. Duplicar el máximo observado no demuestra que un intervalo mayor corrompa Σdt o el filtro exponencial.

## Hallazgos nuevos

**B1 [BLOQ, continuación de H1] — La compensación después de la frontera sigue engañando al evaluador.**

Dónde: [check_runs.py:218](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:218), [s_track_eval.py:2201](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2201) y [2410](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2410).

Entrada: 2310 frames a 60 FPS, tramos de 10 s, giros de 4 s y salto de 1 m en el frame 720 de `s03`. Mantener intacto el frame del salto; cambiar:

```text
dt[721] =  2,666667 ms
dt[722] = 30,666667 ms
Δt_ms   = 16,666667 ms en ambos
```

La deriva máxima es **14 ms** y `check_run` devuelve **sin motivos**. Una cámara defectuosa que siga esos intervalos adulterados escribe **0,062411799 m** en el frame 721, frente a los **0,105160683 m** correctos: **4,2749 % de error**. T-suave devuelve **PASA**, con error frente a su referencia de cero.

En sentido contrario, conservar la cámara correcta y adulterar únicamente esos relojes produce **FALLA / suave_frac_exceeded**.

Arreglo: proteger la incertidumbre temporal durante **todo el transitorio**; cuando los intervalos admisibles puedan cambiar la decisión, devolver INCONCLUSO. Comprobar únicamente el frame del salto no basta.

**B2 [BLOQ] — La nueva guarda puede convertir un desacuerdo entre FPS en PASA.**

Dónde: nueva exclusión en [s_track_eval.py:2433](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2433), combinada con [2789](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2789) y [2809](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2809).

Entrada: regímenes 30 y 60; el de 60 es correcto. En el primer giro, el de 30 lleva un sesgo de 1° durante los primeros 0,5 s, todavía inferior al límite individual de 3,4°. A 1/6 s resultan **73,4619° frente a 72,4619°**.

Antes del tirón, ambos obtienen **FALLA / suave_fps_agree_exceeded**. Introducir el patrón real `dt=8+32 ms`, `Δt_ms=36+5 ms` en la frontera del giro correcto de 60, recalculando su cámara correctamente, deja ambas corridas aceptadas por `check_runs`, pero produce:

```text
30: PASA
60: INCONCLUSO / intervalo_salto_incoherente
```

La comparación desaparece y el régimen discrepante queda certificado.

Arreglo: conservar como pendiente el criterio de acuerdo cuando faltan las comparaciones necesarias; excluir una referencia no debe convertir ese criterio en satisfecho.

**M1 [MAY] — La guarda invalida `s0`, aunque su respuesta no depende de `dt`.**

Dónde: [s_track_eval.py:2410](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2410) y [2433](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2433); independencia explícita en [2204](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/s_track_eval.py:2204).

Entrada: patrón real 8+32 frente a 36+5 ms situado en un salto de `s0`. La cámara correcta da INCONCLUSO. Incluso introduciendo **0,5 m de error**, el resultado sigue siendo **INCONCLUSO**, con `err_max_frac=0.5`, aunque `alpha=1` permite demostrar el fallo.

Arreglo: omitir esta guarda cuando `smooth=0` y juzgar la respuesta observable.

**M2 [MAY] — Un intervalo coherente de 101 ms invalida una corrida que conserva todas las medidas.**

Dónde: [check_runs.py:171](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:171) y [214](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/check_runs.py:214).

Entrada: corrida anterior, con `dt=101 ms` en el frame 100, `Δt_ms=101 ms`, timestamps posteriores desplazados correspondientemente y cámara correcta. Deriva prácticamente cero; **59,869 FPS**; los cinco grupos de T-suave dan PASA.

Salida mala: `check_runs` declara INVALIDA por ambos límites de 100 ms. El productor toma directamente `dt` en [STRACK_Session.c:318](C:/tmp/dsbx-strack2/eval5/DayZSandbox_dev/qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:318); no impone ese techo. Es un escenario permitido por el código, **no observado en estas calibraciones**.

Arreglo: decidir por cadencia, continuidad y suficiencia de las medidas; cualquier techo operativo adicional necesita un criterio contractual propio.

## LO QUE NO PUDE VERIFICAR

No ejecuté la suite ni el evaluador integral con NumPy/Pillow, ausentes en este entorno. Ejecuté `check_run` y su parser reales con archivos simulados en memoria; para T-suave y el acuerdo entre FPS ejecuté las ramas originales extraídas por AST con un adaptador vectorial mínimo de biblioteca estándar y cálculos independientes.

No comprobé corridas `suave*` reales, imágenes ni comportamiento in-game. Base verificada: `4ae0727`. No modifiqué archivos.