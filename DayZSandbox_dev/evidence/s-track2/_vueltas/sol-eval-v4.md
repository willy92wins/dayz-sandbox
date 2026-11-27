**NEEDS-WORK.** Lectura completa, sin ejecutar tests ni escribir ficheros. El gate de 64 tests sigue siendo declarado.

Cotejo de vuelta 3: **h1, h3, h4, h5, h6, h7 y h8 cierran sus escenarios originales; h2 queda parcialmente abierto**. Constantes §4/§13 exactas y usadas, ambos caminos mutantes vivos y schema 2 presente. La prioridad de `mount0` está aplicada; conserva la limitación del hallazgo 5.

1. **BLOQ — Todavía puede certificar un giro truncado (h2 parcial).** [s_track_eval.py:2336](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2336).  
   **Escenario:** conservar el positivo completo hasta los primeros 66 frames de `giro-170` a 60 FPS y truncarlo ahí. Hay 1,1 s, orientación a 1/6 s, continuidad y error correcto: el giro y el régimen pueden obtener PASA aunque faltan casi tres segundos del mantenimiento contractual. `done.json` tampoco se consulta.  
   **Arreglo:** comprobar la terminación del guion y los cuatro segundos de cada giro, con tolerancia de un frame; adaptar las fixtures positivas a esa duración.

2. **BLOQ — Una orientación de entrada ausente permite ocultar retraso angular.** [s_track_eval.py:2141](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2141), [s_track_eval.py:2286](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2286).  
   **Escenario:** durante el primer 1/3 s de cada giro, quitar `cam_raw.q/x/y/z`, conservando posición y observaciones de `cam`. La cámara mantiene su orientación anterior y empieza a filtrar después. El simulador también congela su estado, obtiene error cero y omite las entradas ausentes al validar el estímulo. Aplicado a los tres regímenes, todos pueden dar PASA y coincidir con avance cero a 1/6 s.  
   **Arreglo:** exigir orientación deseada válida en todos los frames necesarios, incluida la referencia anterior; su ausencia debe dar INCONCLUSO.

3. **BLOQ — Los FPS pueden certificarse contra un reloj distinto del usado para la orientación.** [s_track_eval.py:2048](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2048).  
   **Escenario:** duplicar `t_ms` en positivos correctos de 30/60/144, manteniendo `dt` y poses. Los timestamps indican 15/30/72 FPS, pero se informan 30/60/144 y los regímenes pueden pasar. El acuerdo también puede pasar: los tres comparan aproximadamente 41,23° a 1/6 s, porque el filtro usa `dt` y la interpolación usa `t_ms`. No se comprueba su coherencia.  
   **Arreglo:** contrastar incrementos de `t_ms` con `dt`, exigir tiempos válidos y medir cadencia por frames/tiempo transcurrido; incoherencia → INCONCLUSO.

4. **BLOQ — Una negativa de imagen puede dar FALLA por calibración inventada.** [s_track_eval.py:2739](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2739), [s_track_eval.py:2759](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2759).  
   **Escenario:** negativa `roll` cuya inyección no tiene efecto, con imágenes y marcas correctas, estímulo suficiente y sin calibración. Para una focal real de 684 px y detalles con `xc/zc = ±0,2`, el fallback vertical usa aproximadamente 935,3 px e introduce unos 50,3 px de error. La negativa devuelve `got="FALLA", ok=true` por ese error artificial: no aplica los prechecks de calibración, detector o máscara.  
   **Arreglo:** aplicar también a las negativas las condiciones necesarias para validar la medida; ausencia de calibración o instrumento válido → INCONCLUSO y `ok=false`.

5. **MAY — La calibración sigue dependiendo de que «a» encuentre textura.** [s_track_eval.py:1067](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1067).  
   **Escenario:** arma texturada en sus marcas, fondo plano, «f» correcta y «a» desplazada 60 px desde la primera captura en todas las fuentes. `_textured` falla para «a» y el `break` impide probar «f» en cada frame. Resultado: `sin_fuente_detector` y medidas INCONCLUSAS pese a existir una fuente válida. El test nuevo de detección evita esta calibración.  
   **Arreglo:** obtener captura y centros desde las marcas correspondientes a la máscara; como mínimo, continuar con las demás lecturas cuando una candidata no sirve.

6. **MAY — Una detección débil impide usar los nuevos centros alternativos.** [s_track_eval.py:1674](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1674).  
   **Escenario:** primera captura correcta; después «a» queda a 160 px del arma. Su ventana contiene señuelos texturados con correlación 0,7, mientras la detección previa y la marca permitirían encontrar el arma con correlación 1. El primer intento devuelve objetos no nulos y corta la búsqueda; posteriormente se descartan por `CORR_MIN`, causando baja cobertura e INCONCLUSO.  
   **Arreglo:** exigir correlación y textura válidas antes de aceptar un intento o actualizar `prev_det`; si no, probar el siguiente centro.

RESUMEN: BLOQ=4 MAY=2 MEN=0

PREMISA: Baja varianza temporal no demuestra pertenencia al arma; un fondo uniforme conectado a la marca también cumple el criterio. La calibración reutiliza esa misma máscara para construir sus sintéticas, por lo que no valida independientemente su contorno. Además, el acuerdo entre marcadores no demuestra que el detalle visible coincida con el punto de memoria. Ambas correspondencias requieren contraste independiente en el banco real.

