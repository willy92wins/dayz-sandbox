**NEEDS-WORK.** Lectura completa, sin ejecutar tests ni escribir ficheros. Las cifras de tests siguen sin medir.

Los escenarios originales de v2 **1–3, 5–7, 9–13 y 15** quedan corregidos por inspección, incluidos los pendientes de h8/h9/h14. **4, 8 y 14** continúan parcialmente abiertos. Las constantes §4/§13 son exactas y usadas; ambos caminos mutantes siguen vivos.

1. **BLOQ — Una entrada ausente permite ocultar el retraso de T-suave.** [s_track_eval.py:2052](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2052).  
   Entrada: partir de `suave_entrada_desfasada` y poner `lata.a=null` únicamente en cada frame del salto. Ese frame usa `cam_raw.pos` como objetivo; la comprobación de desfase lo omite y el salto observado se desplaza al frame siguiente. La cámara retrasada puede obtener error cero y PASA.  
   **Arreglo:** exigir `lata.a` válida en todos los frames necesarios para juzgar la respuesta; su ausencia debe producir INCONCLUSO, sin sustituirla por `cam_raw`.

2. **BLOQ — Puede certificar un giro sin alcanzar t = 1/6 s.** [s_track_eval.py:2253](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2253), [s_track_eval.py:2584](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2584).  
   Entrada: truncar `suave_ok` después de los primeros cuatro frames de `giro-170`, conservando todo lo anterior. No aparecen huecos ni errores en las observaciones presentes. El giro puede dar PASA con `orient_1_6_deg=null`; después queda excluido del acuerdo y el régimen puede certificarse.  
   **Arreglo:** exigir observación y referencia temporal válidas a 1/6 s antes de emitir PASA, además de comprobar que el guion terminó.

3. **BLOQ — La interpolación temporal puede suspender respuestas exponenciales correctas.** [s_track_eval.py:2159](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2159).  
   Entrada: respuesta correcta con los dos primeros intervalos del giro de 100 ms y los demás a 60 FPS, recalculando tiempos y filtro. La cadencia global sigue siendo aproximadamente 59,27 FPS. La interpolación lineal entre orientaciones devuelve **71,2093°** a 1/6 s; la exponencial da **72,4619°**. Comparada con una corrida uniforme correcta, la diferencia artificial de **1,2526°** provoca FALLA. Son valores calculados analíticamente, sin ejecutar la suite.  
   **Arreglo:** interpolar de forma compatible con la exponencial y los intervalos reales, o declarar resolución temporal insuficiente.

4. **BLOQ — Sigue aceptando estímulos distintos de ±170° (v2-4 parcial).** [s_track_eval.py:2223](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2223).  
   Entrada: sustituir el objetivo de +170° por +160° y volver después al rumbo base, calculando correctamente la respuesta. Amplitud y sentido quedan dentro de 150–190°, el error contra `cam_raw` es cero y ambos giros pueden dar PASA. No se ha ejecutado el estímulo exigido.  
   **Arreglo:** validar el salto de ±170° con una tolerancia numérica justificada y comprobar que el objetivo permanece constante durante cada giro.

5. **BLOQ — Una fuente de otro hook todavía puede bloquear al válido (v2-8 parcial).** [s_track_eval.py:2358](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2358), [s_track_eval.py:1029](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1029).  
   Entrada: Ha produce máscaras vacías; Hb tiene imágenes y máscaras válidas. La primera imagen elegible de Ha tiene textura en el contorno de los recortes, pero es plana dentro de las máscaras de Hb. Se seleccionan las máscaras de Hb, pero la fuente sigue siendo Ha: las plantillas enmascaradas carecen de textura y la calibración global queda INCONCLUSA, bloqueando Hb. El test nuevo conserva imágenes compatibles al sustituir las máscaras.  
   **Arreglo:** conservar la procedencia de cada pareja de máscaras y calibrarla con su captura y sus centros correspondientes; probar otra pareja válida si falla.

6. **BLOQ — El fallback a PNG conserva una vía de validación de otra imagen.** [s_track_eval.py:205](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:205), [s_track_eval.py:137](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:137).  
   Entrada: falta `f000120.bmp`; existen `f000120.png` y otra PNG indicada en `entry.png`, con SHA correcto y píxeles distintos. `load_marcas` valida la segunda; el detector consume `f000120.png`. La igualdad de imágenes solo se comprueba cuando existe el BMP, por lo que vuelve a aceptarse una marca vinculada a otra captura.  
   **Arreglo:** resolver primero la imagen efectivamente consumida y vincular siempre su contenido con la PNG validada, también cuando solo quedan PNG.

7. **MAY — La lectura «a» sigue controlando la observabilidad de las demás.** [s_track_eval.py:2396](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2396), [s_track_eval.py:1613](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1613).  
   Entrada: primera captura correcta; después «a» oscila ±60 px, «f» permanece correcta y el fondo fuera del arma es plano. La máscara ya se obtiene correctamente desde las marcas, pero `_textured` examina las proyecciones de «a» y descarta las capturas antes de buscar dentro de ±80 px. «f» queda INCONCLUSA por cobertura aunque su detalle sea observable.  
   **Arreglo:** comprobar textura en el candidato detectado y permitir búsquedas apoyadas en marcas o detecciones previas, sin descartar todas las lecturas por la proyección de «a».

8. **MAY — Las marcas incompletas no condicionan todas las decisiones (v2-14 parcial).** [s_track_eval.py:2449](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2449), [s_track_eval.py:2555](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2555).  
   Entrada: quitar la marca `giro2` de `mount0` en un positivo completo. T-marca queda INCONCLUSA, pero `marca_ok` solo rechaza FALLA: todavía puede seleccionarse la lectura y terminar con `exit_code=0`, aunque ese modo quede sin hook. En `ropa_ok`, conservar una sola marca de mira también permite declarar `sigue`: el T-marca incompleto se añade después sin condicionar T-ropa.  
   **Arreglo:** exigir T-marca PASA para la lectura/caso certificado y cobertura manual completa de la mira para T-ropa; propagar la ausencia al código de salida.

RESUMEN: BLOQ=6 MAY=2 MEN=0

PREMISA: La baja varianza temporal no demuestra que un píxel pertenezca al arma: un fondo uniforme conectado a la marca también cumple `std < 8`. La calibración reutiliza esa misma máscara para pegar el supuesto arma, por lo que no verifica independientemente su contorno. Esa identificación debe contrastarse en el banco con fondos diferentes de los empleados para construirla.

