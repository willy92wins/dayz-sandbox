VEREDICTO: NEEDS-WORK  
BLOQ=4 MAY=0 MEN=0

El cambio de Hc encaja con el banco real. El cambio del reloj debilita el arbitraje: conservar aproximadamente el tiempo total no protege las decisiones que dependen de cada intervalo.

## Hallazgos

### H1 [BLOQ] Los errores compensados pueden producir tanto falso PASA como falso FALLA

- Dónde: [check_runs.py:118](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/check_runs.py:118), [s_track_eval.py:2130](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/s_track_eval.py:2130), [s_track_eval.py:2231](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/s_track_eval.py:2231) y [s_track_eval.py:2711](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/s_track_eval.py:2711).
- Escenario: a 60 FPS, mantener `Δt_ms=16,6667` y cambiar dos `dt` a **30,6667 y 2,6667 ms**, inmediatamente antes de un salto y en su primer frame. La deriva máxima es solo **14 ms**: la comprobación acepta. Para un salto de 1 m con suavizado 0,3 s, la respuesta correcta inicial es **0,054041 m**; una cámara defectuosa que responda **0,008849 m** coincide con el `dt` adulterado y obtiene PASA. Su error respecto al intervalo coherente es **4,519 %**, superior al 2 % permitido.

  También ocurre en sentido contrario con el patrón real: situar `dt=8+32 ms` y `Δt_ms=36+5 ms` después de los primeros 160 ms de un giro correcto. La interpolación a 1/6 s devuelve **70,7614°**, frente a **72,4619°** en otro régimen correcto. La diferencia de **1,7005°** provoca `suave_fps_agree_exceeded`, aunque ambos filtros respondan correctamente a sus intervalos.
- Arreglo propuesto: conservar la deriva global como control adicional, pero establecer una cronología coherente para integración e interpolación. La admisión debe proteger los intervalos y fronteras que consume cada medida, con una incertidumbre derivada de sus tolerancias.

### H2 [BLOQ] El intervalo de carga se excluye del control, pero sigue entrando en la evaluación

- Dónde: [check_runs.py:116](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/check_runs.py:116), [s_track_eval.py:2041](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/s_track_eval.py:2041) y [s_track_eval.py:2068](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/s_track_eval.py:2068).
- Escenario: corrida de **2310 frames**, timestamps regulares a 60 FPS, tramos de 10 s y giros de 4 s; únicamente `dt[1]=5 s`. `check_run` la acepta sin motivos. El evaluador incluye ese intervalo en `N/Σdt`, calcula **53,1238 FPS** y declara **INCONCLUSO / fps_regime**, pese a que la cadencia registrada entre muestras es 60 FPS.

  La exención tampoco tiene límite por el lado de `t_ms`: añadir 100 s a todos los timestamps desde el frame 1 pasa sin deriva posterior.
- Arreglo propuesto: si la carga queda fuera de la medida, excluir explícitamente ese mismo intervalo de todos los consumidores. Si se conserva en la evaluación, debe validarse. Además, el primer par observado no demuestra por sí mismo que sea el par de carga.

### H3 [BLOQ] Un duplicado oculta precisamente el `dt` que conserva el evaluador

- Dónde: [check_runs.py:107](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/check_runs.py:107) y [s_track_eval.py:470](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/s_track_eval.py:470).
- Escenario: duplicar el primer frame de un salto de T-suave, sin `shot`. Primera fila: `dt=16,6667 ms`; segunda: mismo frame y timestamp, pero `dt=300 ms`. El comprobador verifica la primera fila y salta el par duplicado; nunca contrasta el `dt` de la segunda. El lector del evaluador conserva esa segunda fila.

  Una cámara que salte **0,632121 m**, frente a los **0,054041 m** correctos, coincide con la referencia adulterada y puede obtener PASA: **57,808 % de error real**. No hay huecos tras deduplicar y los FPS calculados permanecen dentro de tolerancia.
- Arreglo propuesto: validar exactamente las filas canónicas que consumirá el evaluador, aplicando su misma política de duplicados. Este salto ya existía antes del diff; sigue siendo un agujero del arbitraje.

### H4 [BLOQ] Un `NaN` desactiva la deriva para todo lo que viene después

- Dónde: [check_runs.py:110](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/check_runs.py:110) y [check_runs.py:118](C:/tmp/dsbx-strack2/merge/DayZSandbox_dev/qa/strack/check_runs.py:118).
- Escenario: `dt[10]=NaN` durante `s0`. El parser lo admite y `isinstance` lo considera numérico. `deriva` pasa a `NaN`; `max(max_deriva, abs(deriva))` conserva el máximo anterior. Ningún desacuerdo posterior aumenta ya ese máximo.

  Después se introduce `dt=300 ms` en el primer frame del salto de `s03`, con la cámara defectuosa de H3. Sin duplicados, el comprobador acepta; el evaluador excluye el `NaN` del cálculo de FPS y, durante `s0`, usa `alpha=1`. La referencia posterior acepta la respuesta defectuosa de **57,808 %**.
- Arreglo propuesto: exigir valores finitos y `dt>0` en **cada fila**, antes de acumular o excluir intervalos; rechazar también constantes JSON no finitas.

## Respuestas 1-6 (breves)

1. **Usos de los relojes.** `dt` controla el filtro de `mount03` (`s_track_eval.py:1526`), la simulación frame a frame de T-suave (`:2130`) y los FPS mediante `N/Σdt` (`:2048`). `t_ms` controla el origen del giro, la interpolación a 1/6 s y su duración (`:2213`, `:2231`, `:2334`). Sin campo `giro`, también interviene en la detección temporal de ventanas (`:1281`); con `giro`, las ventanas se forman por etiquetas (`:249`). **Sí: el tirón compensado puede cambiar un veredicto**, como demuestra H1.

2. **Corrupciones admitidas.** Compensación de `dt`: falso PASA de H1. Error en una frontera: adelantar únicamente **15 ms** el timestamp anterior al giro pasa y desplaza la orientación calculada de **72,4619° a 67,4610°**, provocando un falso desacuerdo entre FPS. Carga: H2.  
   Para huecos simples, renumerar los frames como `0,2,4…` evade este control, pero el lector marca `has_gaps`: T-lect/T-hook y T-suave quedan INCONCLUSOS (`s_track_eval.py:1741`, `:2340`). **No cuento esos huecos solos como falso PASA**. Los duplicados de H3 evaden también esa protección.

3. **Datos reales.** No encontré una corrupción temporal que justifique invalidar estas dos calibraciones:

   | Corrida | Frames | Pares con desacuerdo >1 ms | Máxima deriva acumulada | Deriva final |
   |---|---:|---:|---:|---:|
   | Ha | 1021 | 38 | 27,0045 ms | −0,9955 ms |
   | Hb | 1021 | 224 | 8,0007 ms | −0,9993 ms |

   No hay huecos, duplicados, tiempos no finitos ni `dt≤0`. En el archivo actual, **28 ms es el desacuerdo local del tirón de Ha**, no su máximo acumulado. Además, la calibración decide `k` por correspondencia de frames y yaw, no por estos tiempos (`s_track_eval.py:720`). Esto no demuestra que el mismo patrón sea inocuo en T-suave.

4. **Hc.** Sí, coincide para las corridas que puede producir el mod, **incluidas `2580-2581`**. Hereda `k` y focal de Ha (`:2422`); T-lect y T-hook aceptan Ha (`:2494`, `:2580`); ropa tiene el fallback a Ha (`:2666`); las negativas consumen los valores heredados (`:2738`). Ningún camino exige una `calib_Hc`. Matiz: el cargador genérico admitiría una calibración Hc suministrada artificialmente y podría priorizarla; la equivalencia no es una sustitución incondicional ante cualquier entrada fabricada.

5. **Los 50 ms no quedan justificados independientemente.** Los ±0,3 s regulan la duración completa del giro, no la precisión de la orientación a 1/6 s. Para la exponencial de 170° con constante 0,3 s, aproximadamente **1,54 ms de error diferencial** ya consumen los 0,5° de acuerdo entre FPS. Además, prefijos entre −50 y +50 ms permiten diferencias de hasta **100 ms** dentro de una ventana. Hay que fijar el criterio desde los consumidores, la cuantización y la alineación de las muestras; superar el máximo observado no basta. Tampoco propongo restaurar sin más el antiguo ±1 ms, que rechaza ambos registros reales.

6. **Los 12 tests no detectarían H1-H4.** El positivo del tirón solo comprueba admisión sobre filas de `mount0`; no contrasta el resultado con T-suave. Tampoco prueban carga extrema, duplicados, valores no finitos ni exactamente 50 ms y sus bordes. En Hc, el test cubre Ha ausente y Ha válida, pero **no Ha inválida**: eliminar el rechazo de `check_runs.py:182-183` dejaría ese defecto sin cubrir.

## Gate

**GATE NO CORRIDO: el sandbox de solo lectura impide crear el directorio temporal.** Se intentó el comando solicitado; los 12 tests fallaron en `setUp`, antes de sus comprobaciones:

```text
FileNotFoundError: [Errno 2] No usable temporary directory found [...]
Ran 12 tests in 1.213s

FAILED (errors=12)
```

Sí ejecuté `check_run`, incluido su parser JSON, con archivos simulados en memoria. Los escenarios descritos fueron aceptados sin motivos, también con tramos de 10 s y giros de 4 s.

## LO QUE NO PUDE VERIFICAR

No pude ejecutar el evaluador completo: falta NumPy en este sandbox. Las consecuencias indicadas para sus veredictos se deducen de las ramas leídas y del cálculo exponencial independiente, no de una corrida integral. No revisé imágenes ni otras decisiones del evaluador. No modifiqué archivos.