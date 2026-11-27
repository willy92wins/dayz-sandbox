**NEEDS-WORK.** Revisión estática completa, sin ejecutar tests ni escribir archivos. Los 39 tests OK siguen siendo un resultado declarado.

Cotejo de vuelta 1: los escenarios h1–h7, h10–h13, h15 y h16 quedan corregidos por inspección. h8, h9 y h14 conservan los huecos indicados abajo. Las constantes §4/§13 son exactas y usadas; ambos caminos mutantes están vivos.

1. **BLOQ — T-suave todavía aprueba observaciones ausentes (h8 parcial).** [s_track_eval.py:2049](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2049).  
   Entrada: quitar `cam.pos` durante los primeros 0,5 s posteriores a cada salto, conservando las observaciones posteriores correctas. Los errores ausentes se omiten; cada grupo puede dar PASA con `coverage=1.0`, sin haber observado la respuesta inicial. Además, quitar `cam.q` conservando los ejes permite certificar norma con desviación cero, aunque falta el cuaternión escrito.  
   **Arreglo:** exigir las observaciones necesarias en cada frame evaluado y el cuaternión original para comprobar norma; ausencia → INCONCLUSO.

2. **BLOQ — La comparación temporal vuelve a sumar `dt`.** [s_track_eval.py:2071](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2071).  
   §16 fija que `t_ms` ya fecha el final del intervalo. Con una respuesta correcta a 60 FPS, seis intervalos posteriores al inicio de 1/60 s y el siguiente de 1/30 s, `t_eff` sitúa en 1/6 s una orientación de aproximadamente 66,89°. Una corrida uniforme obtiene 72,46°: ambas pueden terminar FALLA por una diferencia artificial de 5,57°.  
   **Arreglo:** fijar explícitamente el origen del salto y usar las fechas finales sin sumar nuevamente `dt`; contrastar con un oráculo analítico de tiempos irregulares.

3. **BLOQ — Una corrida sin estímulo puede suspender otra válida (h14 parcial).** [s_track_eval.py:2452](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2452).  
   Entrada: combinar una corrida correcta de 30 FPS con otra de 60 FPS cuyos grupos de giro mantienen identidad tanto en `cam_raw` como en `cam`. La segunda queda INCONCLUSA por `sin_estimulo`, pero su orientación entra en `by_label` y convierte los giros correctos de 30 FPS en FALLA. Solo se excluye `fps_regime`.  
   **Arreglo:** admitir en el acuerdo únicamente giros con estímulo, observaciones y referencia temporal válidos.

4. **BLOQ — Un giro de 20° puede certificar la prueba de ±170°.** [s_track_eval.py:2120](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2120).  
   Entrada: sustituir los objetivos angulares por +20° y vuelta, manteniendo sus etiquetas y calculando correctamente la respuesta. Superan el requisito `>10°`, tienen error cero y ambos grupos dan PASA. No se comprueba que se haya ejercitado el giro exigido; además, el error continúa dividiéndose entre 170°.  
   **Arreglo:** validar amplitud, sentido y objetivos del guion antes de juzgar la respuesta; estímulo incorrecto → INCONCLUSO.

5. **BLOQ — Se descarta el error de posición durante los giros.** [s_track_eval.py:2139](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2139).  
   Entrada: una corrida correcta salvo por sumar 1 m a `cam.pos` durante ambos giros. `err_pos_frac` detecta el error, pero la rama angular lo sustituye por el error de orientación. Ambos giros y el régimen pueden dar PASA con `err_max_frac=0`, aunque la cámara abandona su posición de seguimiento.  
   **Arreglo:** comprobar también la posición durante esos frames y cubrir el intervalo previo de `tramo=4, giro=0`, actualmente excluido de los grupos.

6. **BLOQ — Los FPS informados pueden diferir mucho de los logrados.** [s_track_eval.py:1924](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1924).  
   Entrada: repetir `dt=[1/60, 1/60, 0.1]`, con respuesta correcta para esos intervalos. El evaluador informa 60 FPS y acepta el régimen 60; la cadencia efectiva es `3/(2/60+0.1)=22.5 FPS`, muy fuera del 10 %. Las fixtures actuales solo discriminan intervalos uniformes.  
   **Arreglo:** medir la cadencia por frames y tiempo transcurrido, comprobando continuidad; informar la mediana separadamente.

7. **BLOQ — `fps_cap` permite certificar el régimen equivocado.** [s_track_eval.py:1938](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1938).  
   Entrada: datos correctos de 60 FPS con `fps_cap=60`, pero `caso=suave30`. Se evalúan contra 60 y se escribe `decisions.suave["30"]="PASA"`. El mismo procedimiento permite certificar 144 sin haberlo ejecutado.  
   **Arreglo:** exigir coherencia entre caso, régimen y tope registrado; comprobar los FPS contra el régimen que se pretende certificar.

8. **BLOQ — La máscara del primer hook bloquea todos los demás.** [s_track_eval.py:2225](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2225).  
   Entrada: `mount0_Ha` produce máscaras vacías y `mount0_Hb` produce máscaras válidas. El diccionario de Ha se conserva aunque sus máscaras sean inválidas; `first_mask` lo selecciona y la calibración global devuelve `mascara_vacia`. `det_ok=False` impide elegir Hb aunque su detector y sus medidas sean correctos.  
   **Arreglo:** calibrar con una pareja válida de máscaras y su fuente correspondiente, evitando que un hook descartado invalide los restantes.

9. **BLOQ — El SHA puede validar una imagen distinta de la consumida.** [s_track_eval.py:188](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:188), [s_track_eval.py:139](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:139).  
   Entrada: conservar la PNG marcada y su SHA correcto, pero reemplazar el BMP homónimo. `load_marcas` verifica la PNG; el detector y la máscara leen preferentemente el BMP. La marca queda aceptada sobre una captura distinta, pudiendo introducir o absorber un desplazamiento constante.  
   **Arreglo:** consumir la imagen efectivamente validada o comprobar igualdad de píxeles decodificados entre ambas representaciones.

10. **BLOQ — Basta un giro para decidir un modo.** [s_track_eval.py:2363](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:2363).  
    Entrada: conservar calibración y `mount0` completos, pero aportar un `follow` continuo con únicamente `giro1` y `resto`, ambos con ≥20 capturas y medidas correctas. Solo se comprueba que exista algún giro: puede elegirse el hook y emitirse PASA sin las repeticiones segunda y tercera exigidas.  
    **Arreglo:** exigir las ventanas previstas por caso y emitir INCONCLUSO para cada repetición ausente.

11. **MAY — T-ropa ignora los huecos entre frames (h9 parcial).** [s_track_eval.py:1830](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1830).  
    Entrada: en `ropa_ok`, conservar solo los frames 0, 60 y 119. `has_gaps=True` queda ignorado; las tres poses presentes dan cobertura 100 %, incluyen giro y reposo, y pueden declarar `sigue`. Eliminar registros evita precisamente el control añadido para poses ausentes.  
    **Arreglo:** comprobar continuidad y calcular cobertura sobre el intervalo esperado, incluyendo las fases de movimiento requeridas.

12. **MAY — La construcción de máscara presupone correcta la lectura «a».** [s_track_eval.py:405](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:405).  
    Entrada: arma fija en imagen durante `mount0`, lectura «f» correcta y proyección de «a» oscilando ±60 px. Los recortes siguen a «a» y muestrean fondo cambiante; la máscara queda vacía y se impide certificar «f». Una candidata controla el instrumento que debe compararlas.  
    **Arreglo:** obtener la varianza en coordenadas de imagen ancladas a las marcas del montaje rígido, o alinear mediante evidencia independiente de las lecturas candidatas.

13. **MAY — El fondo cambiante solo calibra la boca.** [s_track_eval.py:1136](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1136).  
    Entrada: boca correctamente enmascarada y recámara con el fondo señuelo de `fondo_cambiante` incluido en su máscara. La prueba de fondo solo pega y detecta la boca: no incorpora el error de recámara ni el angular al veredicto. La calibración clásica transforma conjuntamente arma y fondo, por lo que no discrimina este defecto.  
    **Arreglo:** repetir el contraste de fondo con ambos detalles y comprobar también el ángulo del segmento.

14. **MAY — Las marcas positivas no cubren las fases exigidas.** [make_fixtures.py:542](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py:542), [s_track_eval.py:1713](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/s_track_eval.py:1713).  
    El generador toma las primeras cinco capturas disponibles: `s2_completo` no marca las mitades de giro2 y giro3. El evaluador tampoco exige esa distribución; dejando una única marca utilizable puede seguir dando T-marca PASA. Los tests positivos no prueban la cobertura manual del brief §4.  
    **Arreglo:** generar las cinco marcas por fase y devolver INCONCLUSO cuando falte la evidencia requerida.

15. **MAY — La fixture de ropa marca un detalle que no está dibujado.** [make_fixtures.py:741](C:/tmp/dsbx-strack2/eval/DayZSandbox_dev/qa/strack/fixtures/make_fixtures.py:741).  
    La imagen contiene únicamente un motivo centrado en `(960,540)`, mientras la marca de mira calculada en las líneas 746–750 cae aproximadamente en `(1116,550)`, sobre fondo plano. `ropa_ok` puede certificar el contraste visual comparando dos cálculos geométricos, sin un detalle correspondiente en la captura.  
    **Arreglo:** dibujar el detalle en las posiciones de verdad independientes y aportar capturas y marcas de las fases exigidas.

RESUMEN: BLOQ=10 MAY=5 MEN=0

PREMISA: Se presupone que el detalle visible marcado coincide geométricamente con el punto de memoria proyectado. Dos marcadores pueden coincidir y compartir un desplazamiento respecto a ese punto. Esa correspondencia debe contrastarse en el banco real: sin ella, un error constante de 5 px no identifica por sí solo una lectura incorrecta. Las sintéticas generadas desde las propias proyecciones no prueban esa premisa.