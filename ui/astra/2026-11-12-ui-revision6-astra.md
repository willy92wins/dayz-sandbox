# Sexta revisión cruzada adversarial — Astra

## 1. Veredicto

**NO APTO:** los cuatro ataques exactos de AR5 ya se detectan y la parada pendiente se recupera correctamente, pero quedan dos falsos PASS en la verificación gráfica y una superposición de coordenadas reproducible al redimensionar.
La interfaz sí parece moderna, profesional e intuitiva en los dos temas; la recuperación nueva se entiende y conserva Parar en su sitio, sin pedir un rediseño.
Doy por arreglados AR5-01 como comparador, AR5-03 y AR5-05; AR5-02 y AR5-04 quedan a medias, con tres hallazgos AR6 detallados abajo.

Revisión del paquete atribuido a **5f513d9**, frente a **c6b5296**, exclusivamente dentro del workspace. **E** = `ctx/estudio.html`; **M** = `ctx/pruebas-mejoras.js`; **U** = `ctx/mutantes.js`; **LI** = `ctx/2026-11-04-ui-mejoras-consolidado.md`; **DI** = `ctx/2026-10-28-ui-m1-consolidado.md`. Los sufijos `:línea` se refieren a esos archivos actuales. El contrato es `ctx/product-spec.md` y el plan cerrado `ctx/2026-10-26-m1-cine-v2.md`.

No se ha inspeccionado un repositorio Git ni probado DayZ real. No se han consultado memoria, historial, vault, carpetas ajenas, `out-parado` o `tmp-parado`, ni abierto subagentes. No hay `CLAUDE.md` en la raíz de este paquete. Los **37 hashes** de `ctx/SHA256SUMS.txt` coinciden; E tiene SHA-256 `9c51ce1de789cfb82a1a7df50e80d4f40669fe2a0b669b5297f9ce15b1e0efcd`. No se han instalado dependencias ni modificado las entradas. Este informe es el único entregable nuevo de `out/`; las sondas, copias y logs de esta ronda están en `tmp/r6-*`.

## 2. Pruebas, resultados y límites

Chromium arranca dentro del sandbox. Todas las corridas de navegador fueron **secuenciales**, con Node v24.14.1, Playwright 1.63.0 y las tres variables de navegador/temporales apuntando al workspace. Los contadores incluyen los dos checks generales salvo indicación contraria. Un FAIL de un ataque significa que **la aserción que exigía rechazar el daño falló**, no que el ataque fuese detectado.

| Tanda | Resultado literal / evidencia | Qué acredita |
|---|---|---|
| a), suite completa actual | **Aportada, leída, no repetida completa:** `RESULT 225 pass, 0 fail`, `medidas/mejoras-nuevo.txt:226`. | 203 anteriores + 22 AR5. No se presentan como 225 escenarios independientes ni se suman a las otras tandas. |
| Actual, `SOLO=^AR5` | **Ejecutada:** `RESULT 24 pass, 0 fail`, [log](../tmp/r6-ar5-current.txt). | 22 específicos y 2 generales; coincide con esos casos de a). |
| b), prueba actual contra c6b5296, `SOLO=^AR5` | **Ejecutada:** `RESULT 21 pass, 3 fail`, [log](../tmp/r6-ar5-baseline.txt). | Exactamente los tres fallos previstos de AR5-05; coincide con `medidas/ar5-c6b5296.txt`. |
| c), 30 mutantes completos | **Aportada, leída, no repetida completa:** control `RESULT 30 pass, 0 fail`; `RESULT 30 mutantes detectados, 0 sin detectar`, `medidas/mutantes.txt:32`. | Repetí los cuatro de AR5 con ambos harnesses, no los 30. |
| d), prueba original de octubre | **Ejecutada:** `RESULT 64 pass, 0 fail`, [log](../tmp/r6-pruebas.txt). | Coincide con `medidas/pruebas-nuevo.txt`. Sin capturas adicionales en esta corrida. |
| Cuatro mutantes oficiales de AR5 y controles | **Ejecutada:** `RESULT 10 ejecuciones de control y mutantes`, [detalle](../tmp/r6-four.json), [ejecutor](../tmp/r6-four.js). | Cuatro ataques × dos harnesses + dos controles. Los dos controles dan `RESULT 8 pass, 0 fail`; los cuatro ataques mueren con el actual y sobreviven con c6b5296. |
| Sondas propias iniciales | **Ejecutada:** `RESULT 9 pass, 2 fail`, [casos](../tmp/r6-probe-cases.js), [log](../tmp/r6-probe.txt). | Planta recortada y cifra parcialmente cubierta pasan indebidamente; cuatro rutas adicionales de procedencia se rechazan correctamente. |
| Confirmación de geometría, exclusión y apertura directa | **Ejecutada:** `RESULT 6 pass, 2 fail`, [casos](../tmp/r6-extra-cases.js), [log](../tmp/r6-extra.txt). | Contorno interior y velo fuera de superficie pintada sobreviven; abrir directamente a 1440 × 900 o 1280 × 720 sí pasa. |
| Dos mutantes propios de planta, harness oficial intacto | **Ejecutada:** `RESULT 2 mutantes ejecutados; sobreviven outline, clip`; cada uno `RESULT 20 pass, 0 fail`, [resumen](../tmp/r6-own-mutants.json). | Selección UX-49, AR4-02, AR4-04+ y AR5-04+, incluidos los 42 assets en el caso AR4-04+. No son suites completas de 225. |
| Mutante propio de exclusión, harness oficial intacto | **Ejecutada:** `RESULT 3 pass, 0 fail`, [HTML](../tmp/r6-mut-caja-v2.html), [log](../tmp/r6-mut-caja-v2.txt). | AR4-01+ oscuro afirma comparar 29/29 textos aunque parte de 6275 está tapada fuera de la superficie pintada del aviso. |
| Matriz propia de conexiones | **Ejecutada:** `RESULT 14 pass, 1 fail`, [casos](../tmp/r6-take-cases.js), [log](../tmp/r6-takes.txt). | 13 escenarios + 2 generales. El único FAIL es una aserción excesiva de mi prueba, descartada razonadamente en §5; no es otro defecto de la página. |
| Barrido propio de tamaños y tolerancias | **Ejecutada:** `RESULT 12 pass, 12 fail`, [casos](../tmp/r6-pixels-cases.js), [log](../tmp/r6-pixels.txt). | 18 vistas + 4 observaciones de tolerancias + 2 generales. Los 12 FAIL mezclaban una cota demasiado estricta de mi comparación fuera de sombras y seis vistas con coordenadas superpuestas; se desglosan en §4. No son doce bugs. |
| Composición aislada, sin sombras CSS | **Ejecutada:** `RESULT 4 pass, 0 fail`, [log](../tmp/r6-pixels-aislados.txt). | Dos controles, oscuro/claro: 813.058 píxeles por vista, diferencia máxima cero; confirma la copia directa sin remuestreo a altura fraccional. |
| Redimensionado 1600 × 960 → 1440 × 900 | **Ejecutada**, actual y baseline: **ambas** `RESULT 4 pass, 2 fail`, [actual](../tmp/r6-resize-current.txt), [baseline](../tmp/r6-resize-baseline.txt). | Pasa el control inicial en cada tema; falla la legibilidad tras resize en cada tema. Defecto heredado, no regresión del delta. |
| Capturas del recorrido de parada | **Ejecutada:** `RESULT 32 capturas, 0 errores de pagina`, [script](../tmp/r6-visual.js), [datos](../tmp/r6-visual.json). | 2 versiones × 2 temas × 2 tamaños × 4 estados. |
| Confirmación visual del resize sin instrumentación | **Ejecutada:** `RESULT 4 capturas sin sonda`, [script](../tmp/r6-resize-visual.js), [log](../tmp/r6-resize-visual.txt). | Las dos versiones y temas, sin inyectar LIB/PROBE. El solapamiento sigue presente. |

Los dieciocho casos de AR5-01 a AR5-04 pasan contra c6b5296 porque los cambios son del **instrumento de medida** y el dibujo normal no cambió. Sus positivos también miran la página; «prueban la sonda» no significa que sean todos sintéticos, sino que el baseline de la página no discrimina esos arreglos. La sensibilidad la aportan sus negativos y las mutaciones. AR5-05 sin cortes también pasa allí: ese «ya se cumplía» es cierto. Los tres fallos de b) son reinicio durante Parando, recorte del director durante la vuelta y corte de 300 ms durante Parando.

### Fidelidad de los cuatro ataques oficiales

| Ataque de AR5 | Actual | Harness c6b5296 | Motivo comprobado |
|---|---|---|---|
| Planta estrechada y girada 5° | `RESULT 3 pass, 2 fail` | `RESULT 5 pass, 0 fail` | La caja sigue en 114 × 25; ahora detecta `transform` y 8/12 puntos fuera. |
| WebGL redimensionado | `RESULT 2 pass, 2 fail` | `RESULT 4 pass, 0 fail` | Una imagen de procedencia desconocida en cada vista; no un rechazo accidental por tapar otro texto. |
| Morfología CSS, dilatar 1 px | `RESULT 2 pass, 2 fail` | `RESULT 4 pass, 0 fail` | Diferencias de pantalla en las letras, en ambos temas. Usa 1366 × 768, de alto entero, en lugar de redondear el alto como mi copia de R5; preserva el defecto atacado. |
| Bloque negro de 245 × 20 px | `RESULT 2 pass, 1 fail` | `RESULT 3 pass, 0 fail` | Diferencias de pantalla en 6250, 6275 y 6300; ahora se miden los 29 textos. |

No exijo que los mutantes reconstruidos sean copias byte a byte: conservan el mecanismo y el daño pertinente. La primera versión propia del mutante de exclusión dio `RESULT 2 pass, 1 fail`: el aviso inicial borraba mi elemento excluido y quedaba solo el velo, que la prueba detectó. La versión v2 lo inserta después de ese aviso y reproduce el mismo estado que la sonda dirigida; solo v2 sustenta el superviviente. Hubo además un error de nombre duplicado en mi auxiliar de conexiones y un intento de plancha con PIL no instalado; se corrigieron sin instalar nada, antes de los resultados citados. No se atribuyen a E.

## 3. Estado de los cinco hallazgos anteriores

| AR5 | Estado | Evidencia | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| AR5-01 | **Arreglado como comparador** | M:390–432 y 1039–1046; morfología rechazada en página y ancestro; copia directa aislada y controles de altura fraccional. | **Sí para el mecanismo denunciado.** Ya no se acepta el rango de vecinos. Los márgenes son explícitos y no apareció un borrado de letras que pasase por 8/255 o ±1 px. La cobertura de otras vistas no es universal: AR6-03. |
| AR5-02 | **A medias** | M:397–404, 423–431 y 1043; 29/29 en la escena normal y tres cifras medidas; [mutante v2](../tmp/r6-mut-caja-v2.html). | **Sí** para margen de 48 px, texto totalmente tapado y sombra de 95 %. **No** para «solo la superficie que tapa»: sigue excluyendo cajas completas aunque estén recortadas, y basta un resto del texto; AR6-01. |
| AR5-03 | **Arreglado** | M:102–114 y 2654–2675; ODD separado de TXT; cuatro rutas propias adicionales en `r6-probe.txt`. | **Sí** para resize WebGL directo y vía ImageBitmap/OffscreenCanvas, y para mantener limpio un 2D realmente vaciado. WebGPU tiene la misma marca por código, pero dibujar con un dispositivo WebGPU real queda **[sin verificar]**. No encontré otra ruta soportada que lo blanquee. |
| AR5-04 | **A medias** | M:2112–2120, 2682–2712; giro, ancestro, rotate y recorte inferior detectados; `outline` y `clip` sobreviven 20/20 cada uno. | **Sí** para los cuatro ataques concretos. **No** para los lados visibles: los doce puntos hacen hit-testing de la caja, no verifican dónde está el contorno. AR6-02. |
| AR5-05 | **Arreglado en el simulador** | E:1334–1378, 2775–2792; cuatro oficiales y doce escenarios propios admisibles; capturas antes/después. | **Sí.** La confirmación ordinaria exige la misma generación de enlaces; una vuelta invalida aquella confirmación y pasa por lectura estable y epoch. No observé doble confirmación, toma extra, edad inventada ni ocultación de Parar en las secuencias comprobadas. No prueba F2/F5 reales ni todos los ritmos posibles. |

## 4. Hallazgos AR6

BLOQUEA se usa con la definición del encargo: un falso PASS de la propiedad exigida o una ruptura del contrato. AR6-01 y AR6-02 son defectos del **verificador**, demostrados con copias mutantes; no afirman que el HTML normal tenga ese velo o ese contorno. AR6-03 sí ocurre en el HTML normal, y ya ocurría en c6b5296.

| ID | Gravedad | Mejora/regla | Dónde | Qué pasa | Evidencia | Arreglo propuesto, concreto | Criterio verificable + / − |
|---|---|---|---|---|---|---|---|
| **AR6-01** | **BLOQUEA** | AR5-02, CU-38, R26 | M:397–404 (`els`, `ov`, `off`), 423–431, 1043; `#toasts > *`, 6275 | La exclusión usa `getBoundingClientRect()` sin comprobar la superficie pintada. Un aviso con `clip-path:inset(0 0 0 90%)` excluye también su 90 % vacío. Un velo ajeno situado ahí tapa parte de 6275 y no se compara; quedan 24/65 píxeles de letra, suficientes para acreditar el texto entero. | [Captura](../tmp/r6-caja-no-pintada.png); `r6-extra.txt`; mutante v2 con prueba oficial **3/3**, que afirma **29/29 textos**. En 6275: `comp.g=24`, `diff=0`, `low=0`, mínimo 8,97:1 en lo que queda. El mismo velo sin la exclusión viva falla por 253 píxeles distintos. | No autorizar una exclusión solo por la caja DOM. Comprobar visibilidad y geometría de recorte/opacidad, incluidos ancestros; una máscara no soportada no debe acreditar píxeles omitidos. Separar texto completo de texto parcialmente medido: el resto visible no demuestra la lectura del numeral entero. Puede fallar o quedar no acreditado sin cambiar cómo se colocan los avisos de la UI. | **+** Página intacta, sombras normales y 29 textos íntegros medidos pasan. **−** El mutante v2 falla por la porción realmente visible tapada; cubrir tres cifras y dejar la última no acredita «6275». Mantener el negativo de cobertura total. |
| **AR6-02** | **BLOQUEA** | AR5-04, UX-49, CU-40, R26 | M:2112–2120; E:366 y 2203; `.pv-fp` | Quitar `border` y dibujar `outline` con `outline-offset:-10px` conserva caja 114 × 25, barra 10 px/m, cero transformaciones y 12/12 hits, pero la planta visible es una tira mucho más pequeña. Tampoco se detectan recortes entre los puntos muestreados. | [Captura del contorno interior](../tmp/r6-planta-outline.png), [recortes](../tmp/r6-planta-recortada.png); `r6-extra.txt`: `bent=[]`, `miss=0`; los dos mutantes pasan **20/20**, incluidos los 42 assets y AR5-04+. | Para esta planta rectangular fija, vincular la caja al trazado que efectivamente se dibuja: rechazar sustituciones de borde por contorno desplazado y recortes/máscaras no modelados, o medir sus extremos visibles en la captura contra la barra independiente. No basta añadir otro puñado de puntos. Acotar CU-40 hasta acreditarlo. | **+** Bus 114 × 25 y generador 48 × 32, con su borde real, y traslación inocua pasan. **−** Contorno interior y recorte entre muestras fallan; conservar giro estrechado, eje corto falso y barra falsa. |
| **AR6-03** | **BLOQUEA** | AR5-01/02, CU-38, UX-50, R26 | E:1522–1530, `ruler`; esquina superior izquierda del mapa después de resize | Abrir a 1600 × 960 y redimensionar a 1440 × 900 conserva la escala del mapa. La placa de Z=7750 se pinta encima de X=6050: `ruler` solo consulta `inMap`, no los números ya pintados. Parte de 6050 desaparece. Abrir directamente a 1440 no reproduce el caso. | [Sin sonda, actual](../tmp/r6-resize-sin-sonda-actual-dark.png), [sin sonda, baseline](../tmp/r6-resize-sin-sonda-antes-dark.png); ambas versiones **4 PASS / 2 FAIL** con la prueba dirigida, en los dos temas. Cajas del texto: 6050 `[9,5,36,13]`, 7750 `[4,7.2,31,15.2]`; **63/89** píxeles de 6050 acaban bajos, mínimo **1:1**. La comparación de pantalla es exacta (`diff=0`): el daño ya está en el lienzo. | Evitar que las placas de ambos ejes se repinten entre sí en la esquina: reservar espacio o desplazar una conservando valor y asociación con su eje. Verificar las colisiones entre números, además de flotantes y etiquetas. Añadir el recorrido resize; no silenciar el inventario para lograr verde. | **+** Apertura directa a 1600 y 1440 y recorrido 1600→1440, en ambos temas, mantienen las coordenadas legibles. **−** Restituir el pintado superpuesto hace fallar por 6050; mostrar solo 7750 sin acreditar el otro numeral no pasa. |

La limitación publicada «un contorno transparente pasaría» (LI:499) es honesta, pero no basta para declarar probados los lados visibles. AR6-02 tiene **otro rectángulo visible**, de tamaño falso, sin girar, escalar ni tapar la planta con otro elemento; es justamente la propiedad que pidió comprobar esta ronda. El recorte entre puntos ilustra además que doce hits no demuestran un contorno completo. AR6-01 tampoco exige prohibir avisos sobre el mapa: exige que la prueba no omita superficie que el aviso no pinta.

### Composición, umbrales y procedencia

**Qué significa «píxel a píxel».** El fallo espacial anterior está corregido: M:407–431 compara cada posición con una única posición de la captura, tras elegir un desplazamiento global; ya no admite el color de cualquier vecino. En la tanda AR5 local el ajuste es `[0,0]`. A 1600 × 960 se mide un canvas **1022 × 856**, caja CSS **1022 × 855,609375** y captura **1022 × 855**: difiere la última fila, no la escala de todas las filas. La tolerancia de un píxel en las dimensiones permite esa fila recortada; M:396 devuelve comparaciones nulas si la diferencia excede uno, y `readable` las rechaza. La promesa documental «si no tiene el tamaño no pasa» debe leerse con esa excepción de ±1, no como igualdad estricta.

Mi barrido de **18 vistas** fue una tanda Windows propia: 1280 × 800, 1366 × 768, 1440 × 900, 1600 × 960, 1920 × 1080, 1536 × 864, 1280 × 720, 1440 × 901 y 1600 × 961, en cada tema, partiendo de 1600 sin volver a encuadrar. No son necesariamente las mismas 18 vistas históricas de Claude: el paquete no trae el registro granular de aquella medición, que queda **[sin verificar]** como tanda exacta.

En el barrido, la comparación directa propia fuera de las cajas de flotantes y de sus sombras modeladas dio máximo **0** en claro y **2** en ocho vistas oscuras (**4** en la primera). No uso ese dato para atribuir remuestreo al navegador: la caja aproximada de una sombra no abarca necesariamente toda su cola pintada. Aislé 1600 × 960 desactivando exclusivamente sombras CSS: en oscuro pasa de **2 a 0**, y en claro permanece **0**, sobre **813.058 píxeles** por vista. Eso sostiene la corrección conceptual de la copia directa; no sostiene que *cualquier* píxel fuera del rectángulo de sombra del harness deba diferir ≤1. No aislé por separado el máximo 4 de la primera vista. La cota ≤1 que impuse a todo ese exterior fue demasiado estricta, y esos FAIL propios no son defectos del producto.

Los otros FAIL del barrido son de `readable`: **1440 × 900, 1280 × 720 y 1440 × 901**, en ambos temas, tras resize. El caso mínimo 1600→1440 está aislado en AR6-03. Su captura y su lienzo coinciden (`diff=0`), pero ambos contienen la superposición. **Composición fiel no implica dibujo legible.**

| Umbral | Juicio y evidencia |
|---|---|
| **8/255 por canal** | Margen de ingeniería, no estándar perceptivo ni valor deducido de que el control aislado dé cero. `brightness(.974)` pasa, con máximo 8 en mi comparación directa; no elimina las letras ni lleva la lectura por debajo de 4,5. No encontré un borrado que sobreviviera por este margen. Es razonable para ruido pequeño con la comprobación adicional de contraste, pero «exacto» debe conservar explícito el ±8. |
| **Desplazamiento global −1..1** | Tiene sentido para registrar dos rasters que pueden empezar en píxeles contiguos. No permite elegir un vecino distinto por cada píxel. Un `feOffset(1,1)` pasa y la sonda declara `[1,1]`; conserva la forma y el contraste de los textos. No lo cuento como daño ilegible ni como mutante sobreviviente relevante. |
| **Sombra hasta su opacidad** | Coherente como cota para la sombra negra actual, no como reconstrucción exacta de su desenfoque. Una sombra de extensión 2000 px y alpha 0,15 pasa: oscurece sin perder legibilidad, justamente el límite declarado en LI:498. La de alpha 0,95 cae por contraste (1,48–1,61:1). La forma espacial de una sombra arbitraria y la mezcla de sombras de colores distintos no quedan certificadas. |
| **4,5:1** | Tiene fundamento externo: WCAG 2.1, 1.4.3. M:314 calcula el contraste de la tinta reconstruida, descontando la cobertura parcial del píxel; no exige que cada píxel antialias bruto llegue a 4,5. El booleano compara el valor sin redondear; el mínimo mostrado se redondea después. Esto es coherente con distinguir color de tinta de suavizado, no con afirmar reconocimiento universal. [Referencia W3C](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html). |
| **Fondo 9 × 9, mínimo 3 muestras** | Elección local declarada, no estándar: busca muestras del anillo a ±4 en cada eje, y con menos de tres vuelve a la mediana del anillo completo (M:313). Mejora el fondo global anterior, pero no demuestra el fondo de cualquier letra alterada. No apareció un contraejemplo nuevo por esta sola vía. |
| **Huecos a menos de 1,5:1** | Heurística para sobrepintado parecido a la tinta, no prueba de que todos los huecos del carácter sigan reconocibles. Solo recoge muestras inicialmente separadas de la tinta a ≥3:1 (M:139–149); pueblos exceptuados. El límite ya declarado sigue siendo necesario. |

En Windows, los tres números próximos a los controles dan **9,06 / 8,97 / 8,88:1** en pantalla, sin diferencias de composición; no se han sustituido por el mínimo Linux de 8,7. La nueva comparación de todos los textos sí mejora de 26/29 a 29/29 en ese control. AR6-01 demuestra la diferencia entre **contar todos los registros de texto** y haber medido **todos sus píxeles visibles**; `allSeen` en M:2594 solo exige `comp.g>0` y ausencia de diferencias en lo conservado.

**Procedencia.** ODD ya no se vacía con los setters de tamaño; `ofCanvas` añade esa marca a las copias e ImageBitmap. Probé, además de los oficiales: WebGL→createImageBitmap→2D→mapa; Worker 2D→ImageBitmap→bitmaprenderer→mapa; HTML transferido a OffscreenCanvas con resize; y WebGL redimensionado mediante `setAttribute`. Las cuatro quedan `unknown:true`, sin excepciones, como muestra `r6-probe.txt`. Las rutas de byte a byte/ImageData manual siguen fuera, expresamente aceptadas en R5. No abro una exigencia de OCR ni de reconocer texto arbitrario de GPU; tampoco doy por ejecutada una prueba WebGPU real que no hice.

## 5. Parada, reconexión y semántica de Fallida

El mecanismo leído es concreto: `stopTake` captura `linkGen` después de solicitar Parar y solo publica la respuesta ordinaria si los tres peers siguen arriba y la generación no cambió (E:1369–1375). Si hubo cambio, termina la toma como fallida/parcial y llama a `reconcileTakes`. La lectura de 700 ms captura otra generación, vuelve a comprobar peers y compara el epoch de la toma con el actual (E:1354–1362). `setOp` quita `lost` al observarla (E:1115), lo que impide a callbacks pendientes volver a confirmar. Reiniciar y cada cambio de backend/servidor/director incrementan la generación; DOF y Expansion no disparan esa reconciliación.

La prueba propia ejerció:

- Las **seis permutaciones de caída** de backend, servidor y director, retorno en orden inverso, con esperas tras la caída de **0, 20, 100, 350, 3900 y 4050 ms**, respectivamente. Después del retorno completo se recorta otro peer a **0, 20, 100, 350, 600 o 650 ms**, respectivamente; DOF y Expansion se alternan dos veces y se espera 850 ms. En las seis no hay Observado, nueva edad, aviso de confirmada ni «Control devuelto» durante ese recorte; al volver, hay una confirmación, lectura al volver y una sola entrada adicional de toma.
- Un pulso caída/vuelta de cada uno de los **tres peers dentro del mismo turno de eventos, después de Parar**. Los tres invalidan la respuesta vieja incluso sin esperar un frame. A 300 ms siguen sin confirmar y luego hay una lectura y una sola confirmación.
- **Armada + reinicio + otros dos peers caídos:** se desarma, Tomas sigue 3→3 y no se inventa confirmación. **Ya parada + reinicio:** mantiene su lectura histórica, con edad que envejece; no la convierte en una lectura del mundo nuevo. **Dos reinicios separados por 1800 ms durante Parando:** se obtiene una sola confirmación del mundo nuevo, sin devolución ordinaria ni toma extra.

Son doce escenarios admisibles, más los cuatro oficiales; **no** las 36 combinaciones de órdenes de caída/retorno ni todas las combinaciones de tiempos. En las capturas rodando y parando, Parar está en la barra y su centro da en el botón; no se abre diálogo. Durante Parando está desactivado para no duplicar la petición, y después permanece como «Parada sin confirmar» hasta la lectura. Esto no certifica control devuelto real en menos de un segundo: sigue siendo un simulador.

**FAIL propio descartado.** En el decimotercer escenario hice caer y volver al director de forma síncrona mientras rodaba y **después** solicité Parar. Mi aserción rechazaba cualquier «Control devuelto», y falló con una respuesta ordinaria de 0,44 s. No demuestra una respuesta vieja: la solicitud de Parar es posterior al retorno y su generación permanece estable. El simulador puede confirmar ese nuevo stop; no exigiría una reconciliación adicional solo para satisfacer aquella aserción. Distinto sería aceptar el temporizador que nació antes del corte, que los tres pulsos anteriores sí impiden.

**Fallida es la clasificación adecuada cuando el mundo cambió mientras paraba.** La orden de recuperación puede quedar Observada porque se leyó que no quedan actores y que la cámara está parada; eso no convierte la toma interrumpida en una parada ordinaria con escena coherente. DI:60–62 y CU-24 distinguen el resultado de la toma de los seis estados de operación. Mantendría «Fallida» con causa de interrupción/mundo nuevo en su fila, sin cambiar el contrato ni inventar otra toma. La lectura no rescata la continuidad perdida de aquella escena.

## 6. Aspecto y observaciones pedidas

Revisé las **32 capturas** mediante cuatro planchas comparativas: [rodando](../tmp/r6-capturas/plancha-rodando.png), [parando/reinicio](../tmp/r6-capturas/plancha-parando-reinicio.png), [vuelta](../tmp/r6-capturas/plancha-vuelta.png) y [leída](../tmp/r6-capturas/plancha-leida.png), y amplié la vuelta actual oscura a 1440 y la confirmación clara a 1366. También miré las capturas de los ataques y del resize sin sonda. Las imágenes de `medidas/capturas` son evidencia aportada; mi juicio visual procede de las propias.

La composición conserva jerarquía, paneles estables y una acción clara para continuar. El aviso nuevo distingue «falta confirmar» de «confirmada en mundo nuevo», y Actividad enseña Parcial/Sin lectura antes de pasar a Observado con origen y edad. La fila transitoria es larga, pero se lee y no tapa el control de parada. A 1440 el mensaje de cabecera cabe en Windows; a 1366 se recorta, aunque «Parada sin confirmar» sigue completa en el botón superior. No encuentro motivo para reabrir letra, filas, radios, sombras, ámbar, colores del mapa, barra o nombres.

El patrón de viewport central, árbol, propiedades contextuales y controles Play/Stop en la barra coincide con el referente público de [Unreal Editor Interface](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface). Es un referente de organización, no una prueba de que la tipografía o colores concretos sean los correctos. No se buscó DayZ Sandbox ni se usaron referentes para añadir nuevas mejoras. WCAG y esa documentación de Epic fueron las únicas fuentes web consultadas.

CDP identifica **Segoe UI Variable** en el título y el estado de la toma; no he usado anchos Linux para juzgar el recorte. La consulta CDP a `.mono` no devolvió glifos en el nodo elegido: no doy por demostrada Cascadia Mono como fuente efectiva de los textos canvas. El CSS no cambió entre los dos HTML, comprobado por igualdad completa del bloque `<style>`.

| Observación del encargo | Dictamen en esta ronda |
|---|---|
| Punto decimal en campos frente a coma en otros textos | **BAJA de consistencia, heredada.** La construcción de los campos y su lectura siguen iguales (E:2089, 2915). La evidencia visual detallada es la de R5; no repetí una edición numérica en esta ronda. No hay evidencia aquí de corrupción del número. |
| Bidones superpuestos a escala de escena | **BAJA de legibilidad espacial, heredada**, visible en las capturas de escena. No se ha movido la fixture ni cambiado la escala para ocultarlo. |
| Avisos no incluidos al colocar etiquetas | Sigue siendo un **límite declarado de UX-50**, no un hallazgo nuevo por su mera existencia: E:1575 enumera los flotantes, sin banner/toasts. No confundirlo con AR6-01: ese caso acredita superficie que el aviso ni siquiera pinta. |
| Aviso recortado de clase ajena en el selector cerrado | **BAJA, heredada.** R5 lo comprobó y E:2085 conserva la clase correcta y la coletilla. No he repetido esa fixture ni la presento como una captura nueva. No reabre AR4-06. |
| «Fallida · parada sin confirmar» junto a «Reaplicar y preparar la 05» | **BAJA de presentación, heredada**, pero la anchura declarada necesita procedencia: aquí a **1440** el texto ocupa **170/170 px** y cabe; a **1366** dispone de **131/170 px** y se recorta, en ambos temas. El title del contenedor conserva el texto completo y el botón superior informa sin recorte. `r6-visual.json` y capturas de vuelta. No impide comprender ni usar la recuperación. |

## 7. Contrato, R20/R25 y documentación

| Obligación | Resultado y límite |
|---|---|
| D2, seis estados, edad y origen | Se mantienen. La nueva vía no pone Observado ni edad reciente antes de la lectura estable en los casos comprobados. La edad de petición y de lectura se separa en E:1111–1118. No equivale a datos observados de DayZ real. |
| B5 / CU-25 | Parar visible y sin diálogo en los tamaños y estados capturados, más la suite original 64/64. No se han revalidado aquí todos los layouts personalizados ni una devolución de control retail <1 s. |
| #4, una preparación antes de rodar | E:1279–1320 conserva una preparación de siete comprobaciones y Armada como precondición para rodar. Ningún cambio de AR5 añade otra preparación. |
| #7, documento como fuente | El delta no modifica autoridad, guardado ni deshacer. La persistencia real del backend no está implementada en esta maqueta y no se certifica. |
| #9, aplicar = reset y crear | E:1147 y siguientes conservan la operación completa; tras la lectura del mundo nuevo se habilita reaplicar. No se introducen diferencias incrementales. |
| #10, ids lógicos / epoch | La toma conserva el epoch de su operación (E:1318) y la reconciliación distingue el nuevo mundo. No aparecen handles de motor ni adopción por parecido. |
| CU-35 | «MCP apagado» sigue visible; las corridas no registran peticiones externas de la página. No se está ejecutando un backend real. |
| CU-37 | Permanece el bloqueo sin backend; d) pasa 64/64 y los nuevos casos conservan la recuperación pendiente. |
| CU-38 | La composición mejoró y los cuatro ataques anteriores caen; no se cierra por AR6-01 y el caso real AR6-03. |
| CU-39 | Sin cambios: iconos y clase ajena mantienen lo aprobado en R5; no se reabre su autoría. |
| CU-40 | La consulta previa y las medidas de muestra permanecen; la garantía de escala visible sigue bloqueada por AR6-02. Capturas reales y caja de modelo siguen en C-17 y su falta no es un hallazgo. |

**Trazabilidad del delta disponible.** Se guardaron diffs de los cinco archivos comparables en `tmp/r6-diff-*.txt`. Son **3 bloques / 39 líneas de diff de HTML**, **10 / 426 de pruebas**, **2 / 33 de mutantes**, **3 / 81 de LI** y **4 / 60 de DI**; son tamaños de los diffs, no líneas funcionales nuevas.

| Cambio | AR5 al que traza |
|---|---|
| CUT_WHY, alternativa de aviso de endTake y guarda linkGen de stopTake | AR5-05. Son los únicos cambios de HTML; no hay cambio de CSS ni otro flujo de producto. |
| ODD/ofCanvas y conservación de procedencia al transferir/copiar | AR5-03. |
| Extraer legible para reutilizar el mismo cálculo en canvas y captura | AR5-01/02. El cálculo de fondo, cobertura y huecos se conserva; se aplica también a pantalla. |
| Sustituir rango de vecinos, ajustar captura, sombras, visibilidad y readable | AR5-01/02. |
| Comprobar transformaciones, ancestros y doce puntos; planFits0 para comparar el criterio anterior | AR5-04. |
| AR4-01 exige todos los registros; bloque de 22 casos AR5; cuatro mutantes añadidos | Los cinco hallazgos y los cuatro ataques de R5, sin eliminar los anteriores. |
| Estado, acotaciones de §14, nueva §15, CU-38/CU-40 y cronología de DI | Cierre documental de R5; sin ampliación de M1. |

No encontré líneas ajenas a esas familias ni cambios de diseño no autorizados. AR6-03 es heredado y se encontró al ampliar precisamente el control de tamaños pedido para AR5-01; **no lo atribuyo al commit de arreglo**. Las propuestas anteriores se limitan a cumplir legibilidad, superficie medida y escala ya exigidas. No entran 3D, multiusuario, grabación, MCP, mapas, eventos ni IA propia.

**Documentos.** La separación histórica en §14 y §15 es útil y no encontré dos reglas visuales vigentes incompatibles. La aritmética es correcta: **22 = 5 + 5 + 2 + 6 + 4**, **225 = 203 + 22**; **19/22** específicos del baseline más dos generales dan **21/24**, con tres fallos. El **30/30** de control del ejecutor completo y el **8/8** de mi selección no son el mismo denominador; **30 mutantes** y mis **10 ejecuciones** tampoco. La tanda de este PC en `medidas/LEEME.txt` está identificada; mis cifras son otras ejecuciones aquí.

Deben corregirse con los hallazgos, sin duplicar reglas:

- LI:479 y DI:189: «solo lo que tapa» sigue siendo caja DOM, y «29 textos» no significa cobertura íntegra de todos sus glifos. Vincular el cierre a AR6-01, no al contador.
- LI:481,484,499 y DI:191: no afirmar lados visibles probados mientras pase un contorno interior de otro tamaño; la advertencia sobre transparencia no subsana esa garantía. Vincular a AR6-02.
- LI:478,497 y DI §12: conservar la condición de registro a escala 1, la tolerancia de ±1 en dimensiones y la exclusión/modelado de sombras; identificar la tanda y las 18 vistas históricas si se cita su máximo 1/255. No convertir copia directa en legibilidad universal; añadir el recorrido AR6-03.
- LI:493,502: etiquetar el recorte a 1440 como observación de su entorno/tipografía. En Windows esta tanda lo reproduce a 1366, no a 1440. La nueva fila sí distingue Sin lectura de lectura del mundo nuevo, tal como dice el documento.

No añado otro ID por repetir documentalmente AR6-01/02/03. La afirmación de que Parar se confirma una vez con el mundo nuevo sí queda respaldada en esta ronda; no debe extrapolarse a F2/F5 sin sus pruebas.

## 8. DISENSO-FUERTE

> **Mantengo el diseño y retiro el disenso pendiente sobre «Parando…».** La interfaz ya parece moderna, profesional e intuitiva. El arreglo conserva Parar visible y distingue la parada sin confirmar de su lectura en el mundo nuevo; las secuencias comprobadas no duplican confirmaciones ni tomas. Mantendría Fallida para la toma interrumpida y Observado para la operación reconciliada. No pido cambiar letra, filas, radios, sombras, ámbar, colores del mapa, barra, nombres ni C-17, y la lectura real sigue en F2/F5.

> **Retiro los cuatro ataques exactos de la quinta ronda, pero mantengo la negativa a cerrar CU-38 por el verde.** Los cuatro ya se detectan por la propiedad pertinente. Ahora he demostrado que un aviso recortado excluye también superficie que no pinta: un velo ajeno borra parte de 6275 y AR4-01 sigue diciendo 29/29 textos. Además, redimensionar la página intacta desde 1600 × 960 a 1440 × 900 superpone 7750 sobre 6050 en los dos temas, también en c6b5296; la sonda lo detecta cuando se ejecuta ese recorrido. La copia fiel del canvas no convierte ese dibujo en legible.

> **Mantengo la negativa a cerrar la escala visible de CU-40.** La guarda nueva detecta los giros anteriores, pero un contorno interior mucho más estrecho conserva caja, barra y doce hits y pasa veinte comprobaciones seleccionadas, incluido el positivo de 42 assets. No es una planta transparente ni una preferencia estética: la planta que se ve tiene otras dimensiones. Cerraría este punto vinculando la medida al contorno visible o rechazando como no acreditadas esas variantes, sin pedir un rediseño de la vista previa.

## 9. Para más adelante

- Conservar los contraejemplos con su daño y motivo de rechazo, además del RESULT agregado.
- Identificar cada tanda gráfica por sistema, fuentes, viewport, escala y recorrido de resize.
- No propongo otras mejoras de producto en esta ronda.

Entrega: `out/ui-revision6-astra.md`. Evidencia auxiliar e integridad: [manifiesto](../tmp/r6-manifiesto.tsv). No hay commit: esta lane es una revisión sobre una copia, sin implementación ni publicación. Claude debe corregir los tres hallazgos y sus garantías documentales, manteniendo cerrados los mecanismos que aquí sí pasan. No se actualizó memoria compartida.
