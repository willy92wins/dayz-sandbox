# Quinta revisión cruzada adversarial — Astra

## 1. Veredicto

**NO APTO:** sobreviven cuatro mutantes que invalidan la verificación gráfica y queda una vía de parada que confirma sin distinguir el mundo nuevo.
La interfaz sí parece moderna y profesional en ambos temas y tamaños revisados, y los recorridos corregidos de Añadir y Propiedades resultan más intuitivos.
Doy por arreglados **AR4-04, AR4-05 y AR4-06**, y por **a medias AR4-01, AR4-02 y AR4-03**, sin pedir un rediseño ni reabrir las decisiones visuales de Guillermo.

Revisión exclusivamente del paquete atribuido a `c6b5296`, frente a `cd470c5`; no se ha inspeccionado un repositorio Git ni se certifica la partida real. Las referencias **E**, **M**, **U**, **LI** y **DI** significan, respectivamente, `ctx/estudio.html`, `ctx/pruebas-mejoras.js`, `ctx/mutantes.js`, `ctx/2026-11-04-ui-mejoras-consolidado.md` y `ctx/2026-10-28-ui-m1-consolidado.md`; los números tras dos puntos son líneas de esos archivos. El contrato es `ctx/product-spec.md` y las decisiones son las de `ctx/2026-10-26-m1-cine-v2.md`.

Se comprobaron los **31 hashes** de `ctx/SHA256SUMS.txt`: todos coinciden, antes del trabajo y en la comprobación posterior. SHA-256 de E: `0fb85030191e50ade39b9250e32cb835e5c555203dbea31442b2e2ae7e4d565d`. No se modificaron las entradas, ni se instalaron dependencias, ni se abrieron subagentes. Este informe es el único entregable en `out/`; las reproducciones están en `tmp/r5-*`.

## 2. Pruebas y procedencia

Chromium arrancó dentro del sandbox. Se usaron Playwright 1.63.0 y Node v24.14.1 del paquete, con `PLAYWRIGHT_BROWSERS_PATH`, `TEMP` y `TMP` apuntando al workspace. Las ejecuciones de navegador fueron secuenciales. No se sustituye una prueba del producto por la afirmación de su autor: los resultados aportados y los repetidos se separan aquí.

**Incidencia de alcance:** en la primera llamada hice una búsqueda en el índice de memoria del runtime fuera del workspace, contraria al límite de lectura del encargo. No aportó contexto pertinente de este proyecto ni se usó como evidencia; no se continuó esa consulta. Las conclusiones proceden del paquete y de las fuentes públicas indicadas; no se consultaron el vault ni los repositorios.

| Tanda | Resultado literal y evidencia | Qué acredita |
|---|---|---|
| a), suite completa actual | **Aportada, leída, no repetida completa:** `RESULT 203 pass, 0 fail`, `medidas/mejoras-nuevo.txt:204`. | Son 166 comprobaciones anteriores más 37 AR4; no son 203 escenarios independientes. La repetición propia se centró en el delta y sus ataques. |
| Actual, filtro `^AR4` | **Ejecutada:** `RESULT 39 pass, 0 fail`, [log](../tmp/r5-ar4-current.txt). | 37 específicos + 2 generales. Coinciden los 37 resultados AR4 de a), incluidos 42/42 assets en un único caso positivo. |
| b), actual harness contra `cd470c5`, filtro `^AR4` | **Ejecutada:** `RESULT 25 pass, 14 fail`, [log](../tmp/r5-ar4-baseline.txt). | Coincide exactamente con `medidas/ar4-cd470c5.txt`: 24/37 específicos pasan, 13 fallan; pasan las peticiones locales y falla el general de errores JS. |
| c), 26 mutantes oficiales completos | **Aportada, leída:** control `RESULT 29 pass, 0 fail`; `RESULT 26 mutantes detectados, 0 sin detectar`, `medidas/mutantes.txt:28`. | No he reejecutado los 26. Sí los cuatro nuevos, con sus controles y ambos harnesses, abajo. |
| d), prueba original de octubre | **Aportada, leída, no reejecutada:** `RESULT 64 pass, 0 fail`, `medidas/pruebas-nuevo.txt:67`. | No se suma a 203, ni sustituye evidencia in-game. |
| Casos propios de interacción | **Ejecutada:** `RESULT 19 pass, 3 fail`, [prueba](../tmp/r5-additional.js), [log](../tmp/r5-additional.txt). | 20 específicos + 2 generales. Dos FAIL sustentan AR5-04/05; el tercero, retorno temprano, se descarta como hallazgo por la razón de §5. |
| Ataques propios a la sonda, versión corregida | **Ejecutada:** `RESULT 3 pass, 4 fail`, [prueba](../tmp/r5-probe-v2.js), [log](../tmp/r5-probe-v2.txt). | Cinco específicos + dos generales: se exige rechazar el daño; fallan ese rechazo en CSS oscuro/claro, procedencia WebGL y exclusión de 48 px. El caso de pequeño cambio de brillo pasa. |
| Confirmaciones dirigidas | **Ejecutada:** `RESULT 3 pass, 2 fail`, [prueba](../tmp/r5-followup.js), [log](../tmp/r5-followup.txt). | Reproduce Parando/reinicio y planta girada; el control con altura entera pasa y dos filtros pequeños acumulados sí se rechazan. |
| Huecos y patrones adicionales | **Ejecutada:** `RESULT 6 pass, 0 fail`, [prueba](../tmp/r5-shapes.js), [log](../tmp/r5-shapes.txt). | El relleno de otro color se detecta por contraste local. Tres patrones de barras conectadas se evalúan y los tres son rechazados por STRIPES; los tres PASS significan que se obtuvieron sus medidas, no que fueran rayados válidos. |
| Capturas propias | **Ejecutada:** `RESULT 48 capturas, 4 errores de fixture`, [script](../tmp/r5-visual.js), [log](../tmp/r5-visual.txt), [datos](../tmp/r5-visual.json). | Los cuatro errores son exclusivamente el TypeError esperado de tamaño null en `cd470c5`, uno por tema/tamaño. Cero en la versión actual. |

En b) fallan exactamente los tres AR4-03, los cuatro negativos AR4-04, los cuatro AR4-05 y los dos AR4-06 de clase ajena. Los quince AR4-01, los siete AR4-02, el positivo de medidas válidas y el positivo de clase conocida pasan también allí. Por tanto, los dos «ya se cumplían» de LI:458 son ciertos. AR4-01/02 ejercen la sonda o el criterio nuevo sobre dibujo que no cambió; sus positivos también miran la página, pero pasar en el baseline no demuestra sensibilidad al defecto. Esta la aportan las mutaciones.

### Los cuatro mutantes heredados

Ejecutor propio [r5-four.js](../tmp/r5-four.js), resultados [r5-four.json](../tmp/r5-four.json): `RESULT 10 ejecuciones de control y mutantes`. Ambos controles dan `RESULT 7 pass, 0 fail`.

| Mutante | Harness actual | Harness `cd470c5` | Fidelidad y causa del rechazo actual |
|---|---|---|---|
| CSS `contrast(0.15)` | `RESULT 2 pass, 1 fail` | `RESULT 3 pass, 0 fail` | Misma alteración visual. Falla por píxeles distintos **en pantalla**, no por excepción. |
| Primera cifra tapada con su tinta | `RESULT 2 pass, 1 fail` | `RESULT 3 pass, 0 fail` | Misma propiedad rota. Mi archivo R4 tapaba la primera cifra de cada numeral con altura fija; Claude tapa solo la primera del fotograma y usa las métricas del glifo. No es copia literal, pero sigue siendo un negativo válido: «6050» tiene 18/89 píxeles bajos al acabar y 30/135 huecos rellenos. |
| OffscreenCanvas → ImageBitmap → bitmaprenderer → drawImage | `RESULT 2 pass, 2 fail` | `RESULT 4 pass, 0 fail` | Misma ruta. Mi variante libre estaba abajo a la derecha, a 160 × 24; la oficial está a media altura, a 150 × 24. En las ocho vistas AR-03, el único motivo informado es **una imagen sin medir con «SIN LECTURA»**; no bajos, huecos ni textos faltantes por solapamiento. Se corrige el falso rechazo accidental con K2 de la primera prueba R4. |
| Ancho de planta al 20 % | `RESULT 3 pass, 2 fail` | `RESULT 5 pass, 0 fail` | Misma sustitución de `w * s` por `w * s * 0.2`. Falla por el eje corto; sin error JS. |

Los logs completos son `tmp/r5-oficial-{actual,anterior}-{0..4}.txt`; 0 es el control. La afirmación «los cuatro sobreviven con la prueba anterior» queda repetida, con su denominador correcto. La cifra de 26 detectados sigue siendo la tanda aportada, no diez ejecuciones mías convertidas en 26.

### Cuatro nuevos falsos PASS sobre copias del prototipo

El [ejecutor](../tmp/r5-new-muts.js) aplica cada ataque al HTML sin cambiar el harness oficial: `RESULT 4 mutantes ejecutados; sobreviven morph, webgl, exclusion, planta`. [Resumen estructurado](../tmp/r5-new-muts.json).

| Copia | Filtro de criterios | Resultado oficial |
|---|---|---|
| [Morfología CSS](../tmp/r5-morph-dilate-rounded.html) | AR-03+, AR3-01+, UX-50+, AR4-01+ | **`RESULT 11 pass, 0 fail`**, [log](../tmp/r5-mut-morph.txt). |
| [WebGL redimensionado](../tmp/r5-webgl-mut.html) | AR-03+, AR4-01+ | **`RESULT 6 pass, 0 fail`**, [log](../tmp/r5-mut-webgl.txt). |
| [Velo fuera de los controles](../tmp/r5-exclusion-mut.html) | AR4-01+ | **`RESULT 4 pass, 0 fail`**, [log](../tmp/r5-mut-exclusion.txt). |
| [Planta estrechada y girada](../tmp/r5-planta-rotada.html) | UX-49 completo, AR4-02 completo, AR4-04+ | **`RESULT 18 pass, 0 fail`**, [log](../tmp/r5-mut-planta.txt). |

Cada RESULT incluye los dos generales. Son cuatro supervivientes en criterios seleccionados, **no** cuatro corridas completas de 203. La primera prueba morfológica, sin redondear la altura del canvas, dio `RESULT 4 pass, 2 fail`: pasaban ambas vistas AR-03 a 1366 px y fallaban los dos AR4-01 a 1600 por el remuestreo fraccional. Se aisló este efecto con altura entera, cuyo control también pasa, y entonces desapareció el rechazo accidental. La primera prueba de la franja usó una leyenda oculta: esa observación se invalida; solo se usa la versión v2 con controles visibles y tres números realmente tapados. El primer arranque del auxiliar de interacción tuvo un error de codificación del script propio, corregido antes de medir; no se atribuye a la página ni se cuenta como corrida con RESULT.

## 3. Estado de los hallazgos de la cuarta ronda

| AR4 | Estado | Evidencia | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| AR4-01 | **A medias** | M:95–109,303–319,375–405,994–1011; cuatro ataques anteriores rechazados correctamente; AR5-01/02/03. | **Sí para los ataques exactos anteriores; no para la garantía declarada.** La comparación compuesta acepta desaparición de letras; excluye números visibles; se pierde la procedencia WebGL al redimensionar. Los sintéticos no son una garantía universal. |
| AR4-02 | **A medias** | M:2067–2084,2306–2332; ambos lados del bus 114 × 25 y generador 48 × 32 correctos; AR5-04. | **Sí para ancho, largo, intercambio simple y barra alterados; no para dimensiones reales de una planta transformada.** Mide la caja envolvente alineada con los ejes, no sus lados. El mutante girado conserva esa caja y pasa 18/18. |
| AR4-03 | **A medias** | E:1318,1351–1361,1364–1376,2786–2788; tres pruebas oficiales verdes, seis permutaciones propias verdes; AR5-05. | **Sí para el reinicio rodando que ya llegó a Parcial; no para todas las vías de confirmación.** `stopTake` resuelve Parando por otro temporizador, sin comprobar epoch ni pasar por la reconciliación nueva. |
| AR4-04 | **Arreglado** | E:866–868,2189–2201; M:2404–2447; 42 entradas válidas, null/ausente/dos medidas, y seis datos inválidos propios. | **Sí.** Los negativos de null, ausencia y longitud 2 fallan en el baseline; las copias con 0, negativo, texto numérico, NaN e Infinity también muestran el aviso y permiten navegar/colocar sin excepción. |
| AR4-05 | **Arreglado en el recorrido encargado** | E:341,2207–2214,2226–2249; M:2457–2509; todos fallan en baseline; caso propio Espacio/tope/backend. | **Sí** para Tab, Espacio, Intro, clic, límite, cancelación, rehacer por Aplicar/selección y categoría. El foco queda en fila o pestaña en estos casos. «Nunca» no prueba todos los cambios de panel posibles. El árbol accesible expone nombre y disabled; lector de pantalla real **[sin verificar]**. |
| AR4-06 | **Arreglado** | E:2077–2084; M:2513–2543; prueba propia de guardar/cambiar/deshacer/rehacer/volver. | **Sí.** Se conserva `Land_Prueba_SinCatalogo`, guardar no añade historia, cambiar a Ikarus sí cambia, deshacer devuelve la clase ajena y rehacer la conocida. No se fabrica una transacción por enfocar/salir. La coletilla recortada se clasifica aparte como baja. |

## 4. Hallazgos nuevos

BLOQUEA se usa con la definición del encargo: una prueba acredita una propiedad falsa, o se rompe el contrato. Los cuatro primeros afectan a la **capacidad del verificador**, no demuestran que la página normal tenga hoy ese daño gráfico. El quinto sí reproduce un comportamiento del simulador actual sin modificar E.

| ID | Gravedad | Mejora o regla | Dónde | Qué pasa | Evidencia | Arreglo concreto propuesto | Criterio verificable, + y − |
|---|---|---|---|---|---|---|---|
| **AR5-01** | **BLOQUEA** | AR4-01, CU-38, R26 | M:386–397, `cv.composite/seen`; `#map` | Aceptar cualquier canal entre el mínimo y máximo de 3 × 3 vecinos permite sustituir tinta por fondo. Un filtro morfológico `dilate` de radio 1 borra los números y casi todas las etiquetas y sigue dentro del intervalo permitido. No hace falta explotar los 8 niveles: el problema es admitir todo el rango espacial. | [Captura](../tmp/r5-morph-rounded-dark.png): placas de números vacías y nombres ilegibles. Mutante `r5-morph-dilate-rounded.html`: **11/11**. Control con altura entera: PASS; ambas variantes de tema, PASS falso. | No equiparar pertenencia al rango con fidelidad de composición. Para este prototipo, rechazar como no acreditados filtros CSS sin modelo verificado, o comparar con un remuestreo esperado que conserve posición, tinta y huecos, incluyendo ancestros. Mantener el control de altura fraccional y los ataques anteriores. Acotar LI/DI mientras no se cumpla. | **+** Página intacta, alturas enteras/fraccionales y ambos temas pasan. **−** Morfología que elimina la letra se rechaza por composición/contraste visible, aunque cada color quede dentro del rango de sus vecinos y no haya error JS. |
| **AR5-02** | **BLOQUEA** | AR4-01, UX-50, CU-38, R26 | M:380–381,395–396,1007,2224; regla superior junto a `.ovl.tr` | Se excluye un rectángulo adicional de **48 px** alrededor de cada flotante y se admite `comp.n === 0`. Eso deja sin comprobar números que están fuera del control y son exigidos por el inventario. UX-50 solo cruza cajas del canvas con flotantes enumerados: no cubre este velo CSS. | A 1600 × 960, controles en y=68..106; cifras en y=49..57. Un pseudo-elemento negro de 245 × 20 en la esquina superior derecha tapa **6250, 6275 y 6300**. Las tres dan `comp={n:0,diff:0,moved:0}`; **4/4** AR4-01+generales. [Captura](../tmp/r5-exclusion-48-v2.png), [datos](../tmp/r5-probe-v2.txt). | Medir los textos visibles fuera de la superficie realmente tapada; no usar el margen de sombra como autorización de cero muestras. Si una etiqueta exigida queda sin medida, declararla no acreditada. Tratar explícitamente la sombra en la composición o en el contraste final, y conservar el rechazo de cajas bajo controles de UX-50. | **+** Los tres números intactos y la sombra normal son legibles y medidos. **−** Tapar solo esa franja, sin tocar el DOM de los controles ni los píxeles del canvas, hace fallar el criterio por esos números. |
| **AR5-03** | **BLOQUEA** | AR4-01, CU-38, R26 | M:95–109 y154–163; setters de `width/height`, `srcOf`, marca `unknown` | Redimensionar un canvas borra TXT, incluida su marca WebGL. El contexto WebGL sigue existiendo y puede volver a dibujar sin otra llamada a `getContext`; al copiarlo al mapa se acepta como canvas limpio, de procedencia conocida. | Control WebGL sin resize: `unknown:true`; mismo contexto después de asignar width/height y dibujar cifras con scissor/clear: `unknown:false`, `texts:[]`. [Captura comparada](../tmp/r5-webgl-resize.png). Mutante con cifras pálidas por esa ruta: **6/6** AR-03/AR4-01+generales, sin errores. | Separar el tipo/procedencia de la superficie del inventario de contenido borrable. Una superficie WebGL/WebGPU o delegada conserva su condición no medible después de un resize mientras esa ruta pueda producir contenido; no basta borrar las etiquetas y asumirla limpia. | **+** Canvas 2D vacío tras resize continúa admitido; halo y copias soportadas siguen funcionando. **−** WebGL, antes y después de resize con el contexto retenido, continúa sin acreditar y hace fallar si se compone texto no medido en el mapa. |
| **AR5-04** | **BLOQUEA** | AR4-02, UX-49, CU-40, R26 | M:2067–2080; `.pv-fp.getBoundingClientRect()` y `planFits` | La caja envolvente de una planta girada puede medir lo esperado aunque su lado corto sea falso. Girar 5° y ajustar los lados para conservar la caja de cada asset pasa también los positivos de las 42 entradas. | Autobús: lados CSS **113,109 × 15,1875 px**, rotación 5°; caja **114,003 × 24,988 px**, barra 10 px/m, texto 11,4 × 2,5 m. Se representa aproximadamente 1,52 m de ancho en vez de 2,5. **18/18**; [captura](../tmp/r5-planta-rotada.png), [medida](../tmp/r5-followup.txt). | Verificar los lados reales y la orientación exigida, incluyendo transformaciones propias y de ancestros; para la planta fija actual, exigir rectángulo sin transformación que altere sus ejes y medir contra la barra independiente. No aceptar una caja envolvente como medida del rectángulo. | **+** Bus y generador intactos pasan en sus escalas y con el redondeo tolerado. **−** El rectángulo estrechado y girado 5°, con caja 114 × 25, falla; también ancho/largo intercambiados, giro simple no permitido y barra falsa. Un giro de 90° más intercambio que restituya exactamente la misma planta visible no es por sí solo daño. |
| **AR5-05** | **BLOQUEA** | AR4-03, D2, B5, #10, CU-30, R26 | E:1364–1376 `stopTake`,1333–1345 `endTake`,1351–1361,2788; Actividad y aviso de parada | Si se pulsa Parar y se reinicia inmediatamente, la toma sigue Parando durante la caída. A la vuelta, su temporizador antiguo solo mira peers y tiempo: publica Observado con origen ordinario, inventa la duración de devolución como si fuera una confirmación normal y quita la recuperación. No usa el epoch guardado por el arreglo. | Dos reproducciones sin mutar E: **«Control devuelto en 2,25/2,26 s»**, **«Leída hace 0 s · servidor y tu juego»**, mientras el banner dice que el mundo es nuevo. [Captura](../tmp/r5-parando-reboot.png), [log dirigido](../tmp/r5-followup.txt). No hay otra toma: 4 entradas. | Invalidar la confirmación pendiente de Parando al cortar/cambiar mundo y resolverla por la misma lectura estable con epoch que la toma perdida. Publicar una sola confirmación del mundo nuevo; no atribuir al stop viejo una devolución normal ni un tiempo medido que el reinicio no acredita. | **+** Parar conectado confirma normalmente una vez; reiniciar desde Rodando y desde Parando confirma una vez con el mundo nuevo y permite reaplicar. **−** Cortar otro peer durante esa vuelta, o completar el temporizador de la parada del epoch anterior, no publica Observado/edad nueva/origen ordinario antes de la lectura válida. |

## 5. Qué se ha comprobado y qué no demuestra el verde

### Sonda: umbrales, huecos, rayado y procedencia

**26 de 29 textos es una cuenta cierta, pero insuficiente.** La repetición AR4-01 registra 13.780 muestras en oscuro y 13.802 en claro. No son todos píxeles únicos: las listas de letra, anillo y huecos pueden compartir coordenadas. Los tres textos sin muestras no están físicamente bajo un botón: son los números demostrados en AR5-02. Admitir el 80 % permite precisamente ese falso PASS. Los marcadores siguen midiéndose en el backing store del canvas; la exclusión declarada de un velo CSS que solo afecte a marcadores es real por lectura del código, no una comprobación de composición de esos marcadores.

**Fondo a cuatro píxeles y mínimo de tres muestras.** M:311 filtra con `abs(dx) <= 4 && abs(dy) <= 4`: es una vecindad cuadrada de coordenadas del raster, no un radio euclídeo de 4 px. Si reúne menos de tres muestras del anillo, vuelve a la mediana de todo el texto. La proximidad es una mejora razonable frente a usar siempre el anillo completo; **4 y 3 son elecciones heurísticas**, no una derivación de CU-38 ni una validación perceptiva. LI:446 omite ese fallback y simplifica la geometría. Lo observado aquí es DPR 1; otros DPR no están verificados. No he demostrado un nuevo bypass debido exclusivamente a esos dos números.

**Huecos a 1,5:1.** M:139 solo registra huecos cuyo fondo inicial se distingue al menos 3:1 de la tinta; M:314 considera rellenados los que terminan a menos de 1,5:1 de ella. El objetivo tiene sentido como detector de sobrepintado de igual tinta, pero esos umbrales no reconocen caracteres. Intenté rellenar los huecos del primer 6 de «6000» con `#555`, a más de 1,5:1 de su tinta `#222116`: `filled=0`, pero **16/96 píxeles** caen hasta **2,17:1** por el fondo local y el detector conjunto lo rechaza. No lo presento como superviviente ni afirmo haber demostrado un carácter ilegible que pase por ese camino. Sigue siendo incorrecto equiparar estos checks a reconocimiento universal de legibilidad.

**Vecinos 3 × 3 y margen 8/255.** El remuestreo por altura fraccional justifica alguna tolerancia; no justifica permitir cualquier extremo de la vecindad. La morfología de AR5-01 prueba el mecanismo, no una objeción subjetiva. Un `brightness(0.974)` pasa; dos filtros iguales acumulados fallan en la comparación final. Por tanto, no encontré un fallo que «reinicie» el margen por cada filtro: sí se compara el resultado acumulado. El margen pequeño aislado no hizo ilegible el dibujo normal, cuyo contraste tiene holgura. El falso PASS probado es el intervalo espacial completo.

**Dos franjas de cada tono y trozos ≤ franjas + 1.** La repetición mínima corrige el bloque único y la limitación de componentes corrige los puntos alargados. Son reglas calibradas para estos marcadores, no un estándar perceptivo ni prueba de periodicidad/anchura uniforme. Repetí sus controles: los giros 0°, 5° y 20° pasan ambos criterios; el de **40° falla ambos**, con 0,5 cambios por fila, aunque haya dirección reconocible. Esa frase de LI:449 es correcta: el rechazo procede de la condición anterior de alternancia por filas, no del añadido nuevo. Mis tres intentos de barras verticales unidas por puentes también caen: los dos primeros por seis componentes claros frente a tres franjas claras; el tercero ya pierde dirección. No apareció un superviviente nuevo de rayado en estos intentos.

**Límites declarados.** Acepto la copia manual byte a byte entre ImageData, createImageData y los huecos de contornos rellenados con otro color como límites de una prueba acotada del dibujo actual, acompañada de capturas. No equivalen a «ningún texto visible sin medir» ni a «cualquier discontinuo sigue discontinuo». El terreno usa createImageData legítimamente (E:1451–1468), por lo que rechazar cualquier píxel manual sin distinguir su uso rompería el control positivo. No pediría OCR general para cerrar esta ronda: sí cerrar las rutas concretas reproducidas y dejar la garantía escrita al nivel de la evidencia. La limitación declarada de no reconocer letras **no excusa** acreditar CSS que elimina sus píxeles visibles, ni aceptar como conocida una superficie WebGL que la propia sonda había marcado desconocida.

### Recuperación, datos y foco

La toma nueva guarda `epoch` en E:1318; `reconcileTakes` compara ese mundo con el actual, exige los tres peers y conserva la guarda `linkGen`. Al pasar a Observado, `setOp` borra `lost`, por lo que callbacks posteriores no confirman de nuevo. El reinicio rodando normal, el corte de tu juego durante la vuelta y la lectura vieja interrumpida por reinicio pasan en el actual y fallan en `cd470c5` por la propiedad esperada.

Ejecuté las **seis permutaciones de caída de backend/servidor/director**, devolución en orden inverso y un recorte posterior por permutación a **0, 20, 100, 350, 600 o 650 ms**, respectivamente. Durante el recorte se alternaron DOF y Expansion dos veces. En las seis se conserva Sin lectura/Parcial, después hay una sola confirmación y no se suma otra toma. Son seis combinaciones concretas, **no** las 36 combinaciones de seis órdenes por seis tiempos ni una prueba de todos los ritmos posibles. Reiniciar con toma armada y dos peers caídos desarma sin tomar ni confirmar; reiniciar una toma ya parada conserva su evidencia histórica sin volverla a leer. No observé que quitar la lectura de DOF/Expansion eliminase una recuperación necesaria en esos recorridos.

**Caso descartado:** hice volver manualmente el servidor unos 120 ms después de iniciar el reinicio. A los 700 ms de esa vuelta se confirmó la toma con el epoch viejo; el callback de reinicio cambió el mundo más tarde. Mi aserción exigía que la fila histórica terminase diciendo mundo nuevo y falló. Eso, aislado, **no demuestra una lectura fabricada**: al confirmarse, el simulador aún estaba en el mundo anterior y sus tres peers estaban conectados. Retiro esa aserción como criterio de defecto; no es un sexto hallazgo. Es distinto de AR5-05, donde el mundo ya cambió antes de que se publique la confirmación ordinaria.

El código de tamaños comprueba longitud tres, valores finitos y positivos antes de usarlos. Las pruebas propias con 0, negativo, cadena numérica, NaN, Infinity y dos valores mantienen nombre/clase/icono/aviso sin captura, eliminan planta/medidas y permiten colocar. El caso oficial ya cubre null y ausencia. No se ha exigido que existan todavía las medidas o capturas reales de C-17.

Añadir al tope permite consultar sin crear. Además de las pruebas oficiales, Espacio al tope y Espacio/Intro/clic con backend caído no colocan; Tab conserva foco visible y preview. El árbol accesible de la fila dice `button "Autobús Ikarus" [disabled]`. La preview existe como grupo etiquetado, pero no hay asociación `aria-describedby` ni región viva en `#libPrev`; no afirmo que un lector pronuncie automáticamente sus dimensiones al enfocar. La lectura de voz y los modos de navegación de un lector real quedan **[sin verificar]**; esto no se convierte en una promesa de accesibilidad completa.

También probé un **actor** con hueco: se elimina Linda, se recorre Actores, se elige Mirek con Espacio, se cancela, se elige con Intro y se coloca con otro Intro. Mantiene el foco en la fila hasta colocar, luego en Propiedades, y acaba en 2/2: **`RESULT 3 pass, 0 fail`** — un específico y dos generales, [log](../tmp/r5-actor.txt), [prueba](../tmp/r5-actor.js). El caso oficial «con hueco» recorría un Volga, no un actor.

### Aspecto y referentes

Se generaron y miraron las **48 capturas** solicitadas: antes/actual × oscuro/claro × 1366 × 768/1440 × 900 × hover, teclado al tope, tamaño ausente, clase ajena, rodando y reiniciado. Se revisaron en [seis planchas comparativas](../tmp/r5-capturas/plancha-hover.png), además de ampliar las vistas actuales de tamaño ausente, teclado al tope, clase ajena y las capturas de defectos. Las otras planchas son `plancha-tope-teclado.png`, `plancha-sin-tamano.png`, `plancha-clase-ajena.png`, `plancha-rodando.png` y `plancha-reiniciado.png`, en la misma carpeta.

La vista previa sin tamaño mantiene una composición estable y dice claramente lo que falta. El foco ámbar permite seguir el catálogo al tope y la preview corresponde a la fila enfocada; la advertencia de presupuesto sigue visible. Propiedades ya no enseña Ikarus para el baúl de clase ajena. La barra de rodaje mantiene su posición y Parar se ve mientras rueda; tras el reinicio normal se ofrece reaplicar/preparar, a diferencia del bloqueo anterior. Mantendría estos cambios.

Como referencia de composición, la documentación pública de [Unreal Editor Interface](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface) describe viewport, Outliner, Details contextuales y controles de Play/Stop en la barra. La separación de tareas del prototipo es coherente con ese patrón; no atribuyo a Unreal sus tamaños, colores o tipografía concretos. Las páginas de [Asset Browser de Eden](https://community.bistudio.com/wiki/Eden_Editor:_Asset_Browser) y [Asset Previews](https://community.bistudio.com/wiki/Eden_Editor:_Configuring_Asset_Previews) devolvieron 403 en esta sesión: no se ha refrescado su contenido y no sostienen aquí un hallazgo nuevo. No se buscó DayZ Sandbox en la web.

Las fuentes se comprobaron mediante CDP en el DOM de Windows: **Segoe UI Variable** para título y selector, **Consolas** para una muestra `.mono`. Aunque la lista CSS contiene Cascadia Mono, va precedida por `ui-monospace` (E:22); no doy por hecho que Cascadia haya sido la fuente efectiva de esa muestra. No se usaron las métricas Linux de Inter/DejaVu para juzgar estas capturas; la fuente rasterizada de cada texto canvas no se identificó individualmente por CDP.

| Observación que el encargo pide clasificar | Dictamen |
|---|---|
| Punto decimal de los campos frente a coma en textos | **BAJA de consistencia, heredada.** El valor HTML y su presentación localizada no son la misma cosa; no apareció alteración numérica. No exige tocar las reglas visuales en esta ronda. |
| Bidones superpuestos a escala de escena | **BAJA de legibilidad espacial, heredada**, visible en las comparaciones. No justifica mover la fixture ni rehacer símbolos; existe encuadre cercano/Jerarquía. |
| Avisos encima del mapa excluidos de UX-50 | **Límite de cobertura declarado**, no nuevo hallazgo por sí solo. Que el aviso pueda ocupar mapa no equivale a demostrar que todos los textos están libres de cualquier superposición. AR5-02 afecta números fuera de controles, no es una reapertura de la exclusión de avisos. |
| «No está en el catálogo» cortado en el selector cerrado | **BAJA**, visible en los cuatro casos actuales. El identificador sí aparece y el DOM conserva la coletilla completa; no vuelve a atribuir una clase falsa. No bloqueo AR4-06 por este recorte. |

## 6. Contrato, alcance y documentos

| Contrato | Resultado en esta revisión |
|---|---|
| D2, seis estados, edad y origen | Los seis nombres permanecen en E:811 y las edades/orígenes separados en E:1111–1119 y2287. Las reconexiones ordinarias comprobadas no inventan Observado. **Excepción: AR5-05** confirma por la vía antigua una parada pendiente después del cambio de mundo. |
| B5 / CU-25, Parar visible y sin diálogo | No se encontró regresión de visibilidad en las capturas de rodaje ni cambio de las prioridades de teclado de E:2936–2942. La suite original aportada conserva sus 64 PASS. **No** se certifica devolución de control real <1 s: es F5; el tiempo de 2,26 s de AR5-05 es una afirmación del simulador que no debería presentarse como confirmación ordinaria del stop. |
| #4, una preparación antes de rodar | E:1280–1321 conserva una preparación con siete comprobaciones y la guarda de Armada para rodar. No se añadió una segunda preparación. |
| #7, documento como fuente | No hay cambio de autoridad: hover/preview no escriben en el juego, deshacer modifica documento y guardar no fabrica éxito con backend caído. Persistencia real del backend **[sin verificar]**, fuera de esta maqueta. |
| #9, aplicar = reset y crear | E:1147 y siguientes conserva el flujo completo y sus etapas; no se introduce aplicar diferencias. Tras el reinicio normal actual se habilita reaplicar. |
| #10, ids lógicos y epoch | Se conserva el registro lógico del prototipo y se añade epoch a la operación de toma. No se introducen handles de motor ni borrado por parecido. AR5-05 muestra la vía de confirmación que todavía no consume ese epoch. |
| CU-35, MCP apagado | Se ve en las capturas; las ejecuciones propias no hicieron peticiones externas desde la página. Esto no certifica el funcionamiento del producto retail ni su backend futuro. |
| CU-37, sin backend | Aviso y bloqueo de edición/creación comprobados, incluyendo las nuevas filas enfocables. Las pruebas anteriores de Guardar siguen verdes en la tanda completa aportada. |
| CU-38 | El aspecto normal es legible en las vistas miradas; la **garantía de detección** sigue bloqueada por AR5-01/02/03. |
| CU-39 | Iconos conservados y clase ajena representada correctamente, con recorte de texto de gravedad baja. |
| CU-40 | Falta de tamaño y consulta por teclado corregidas; captura real y caja del modelo siguen en C-17. No cierro su verificación de escala mientras sobreviva AR5-04. |

AR5-05 es una vía preexistente que el arreglo de AR4-03 dejó fuera, no una nueva funcionalidad exigida ni una regresión atribuida sin prueba. No propongo quitar estados, edad, origen, Parar, preparación, reset, documento o identidad lógica. Tampoco se revisó la implementación de la tecla del mod ni la lectura real F2/F5, ni IA concurrente, 3D, vídeo o multiusuario.

### R20/R25: trazabilidad del delta disponible

Se compararon los archivos suministrados, no un Git remoto. Hay **11 bloques / 138 líneas de diff de HTML**, **16 / 729 de pruebas**, **2 / 29 de mutantes**, **5 / 101 de LI** y **5 / 75 de DI**. Son tamaños de los archivos diff, no líneas funcionales añadidas. Evidencia: `tmp/r5-diff-estudio.html.txt`, `r5-diff-pruebas-mejoras.js.txt`, `r5-diff-mutantes.js.txt` y los dos `r5-diff-2026-*.md.txt`.

| Familia de cambios | Trazabilidad |
|---|---|
| Estado CSS de fila, aria-disabled, captura/restauración de foco en renderRight | AR4-05. No altera el límite de creación ni autoriza edición bloqueada. |
| sizeOf, dimsOf y bifurcación de preview sin dimensiones | AR4-04. No aporta dimensiones nuevas ni una captura ficticia. |
| Opción seleccionada de clase ajena en entProps | AR4-06. No añade una clase al catálogo. |
| Epoch de la toma, reconciliación del mundo nuevo, separación de peers frente a DOF/Expansion, llamada al volver del reinicio | AR4-03. El callback pendiente de stop señalado no fue corregido. |
| TXT/IMG/PAT, procedencia, huecos, fondo local, componentes de franjas, composición y readable | AR4-01. Todos los cambios del núcleo de sonda trazan a sus propiedades; sus fallos nuevos son de suficiencia del arreglo. |
| preview/planFits y aserciones de ambos ejes | AR4-02. No se modificó el dibujo normal de la planta. |
| Localizador UX-08 negativo | AR4-05: incluye filas aria-disabled además de disabled; sigue comprobando el presupuesto. |
| Bloque de 37 AR4 y cuatro mutantes añadidos | Los seis hallazgos y los cuatro ataques descritos por Astra. No sustituyen ni eliminan los ataques anteriores. |
| Estados de cabecera, acotaciones históricas, §14, CU-38/39/40 y salvedad de densidad | Cierre documental pedido en R4, ligado a esos hallazgos. |

No encontré una línea cambiada fuera de estas familias ni una ampliación de producto. Las **152 declaraciones CSS** obtenidas con el mismo patrón de extracción en ambas versiones son idénticas en nombre/valor; no se han reabierto tokens de letra, color, radios, sombras o barra. Las rutas fuente y funciones del simulador fueron leídas antes de formular los arreglos; estos son propuestas de revisión, no una implementación autorizada en esta lane.

### Documentos: qué acepto y qué debe ajustarse con los arreglos

Las acotaciones históricas de LI §11/12 son útiles: separan backing store de composición, get/put de ImageBitmap, el antiguo único eje de la planta y la mayoría del área libre del icono frente al 42,5 % posible del interior total. DI:129 ya incorpora la salvedad de etiquetas prioritarias en grupos densos. CU-40 dice desde cuándo se cubren tamaño ausente, eje corto y teclado al tope. No encontré dos decisiones visuales vigentes incompatibles por esos cambios; la historia anterior se presenta como historia.

La aritmética de §14 es correcta: **37 = 15 + 7 + 3 + 5 + 4 + 3** específicos; **203 = 166 + 37**; **24/37** en baseline más dos generales producen **25 pass / 14 fail**, porque el de JS falla. Los controles **29** y **7** son selecciones diferentes; **26** y **4** son cantidades de mutantes, no de aserciones. Los números de Windows de `medidas/LEEME.txt` son una tanda propia y mis resultados se identifican aparte. No se deben mezclar con los mínimos de contraste o fuentes de tandas Linux anteriores.

Deben corregirse, junto con los cinco hallazgos:

- «En pantalla no se ve como en el lienzo» y «compara cada texto» no quedan acreditados por un intervalo de vecinos ni por 26/29 con números visibles sin muestra. Referencias: LI:444, DI:189 y sección 12.
- «Lo que no se sabe de dónde sale queda sin medir» tiene la excepción no declarada del resize WebGL; no la cubre el límite de copiar bytes a mano.
- «Fondo a 4 px» debe precisar vecindad, unidades y fallback de M:303–314; «huecos» es una selección de muestras, no reconocimiento de todos los espacios internos del carácter.
- «Compara los dos lados» debe significar los lados de la planta visible, no solo su caja envolvente. El actual positivo de 42 assets comparte ese mismo oráculo vulnerable.
- «Confirma una vez, con ese origen» se verifica en el retorno desde Parcial, pero no en Parando. La restricción de DOF/Expansion es correcta para la recuperación automática; no significa que Preparar o el botón Leer el juego dejen de leer.

«Prueba la propia sonda» es cierto para los controles sintéticos concretos, incluidos bloque/puntos/giros. No equivale a que cualquier superficie, composición o forma esté cubierta. «El foco nunca queda en la página» y «no hay ningún cambio que deshacer» describen correctamente los recorridos AR4 probados y los ampliados aquí; no son promesas sobre todos los paneles y gestos imaginables. No añado un sexto hallazgo documental duplicado: las precisiones anteriores forman parte de cerrar AR5-01 a AR5-05.

## 7. DISENSO-FUERTE

> **Mantengo el diseño y retiro los obstáculos de datos ausentes, teclado al tope y clase desconocida.** La interfaz ya parece moderna y profesional, y estas correcciones la hacen más intuitiva. No pido reabrir letra, filas, radios, sombras, ámbar, colores del mapa, barra ni nombres. Tampoco exijo las capturas y cajas del modelo que aún corresponden a C-17.

> **Mantengo la negativa a cerrar CU-38 y la escala de CU-40 por el verde.** Retiro como pendientes mis cuatro ataques exactos de la cuarta ronda: ahora se detectan por la propiedad pertinente. Pero cuatro nuevos mutantes pasan: borrar letras con CSS, tapar números fuera de los controles, perder la procedencia de WebGL al redimensionar y estrechar una planta girándola para conservar su caja. Son falsos PASS demostrados sobre el harness actual, no una preferencia estética ni una petición de rehacer la UI.

> **Mantengo parcialmente el disenso sobre recuperación de tomas.** El reinicio rodando normal está arreglado y las seis secuencias de cortes comprobadas no duplican ni inventan confirmaciones. Falta el caso de Parar y reiniciar mientras sigue Parando: todavía publica Observado, edad nueva y una devolución ordinaria de control sin distinguir que el mundo ya cambió. Cerraría ese punto con la misma disciplina de epoch y lectura estable, conservando Parar visible y sin diálogo; la lectura real del mod sigue siendo otro trabajo, F2/F5.

## 8. Para más adelante

- Conservar estos contraejemplos como regresiones, con el daño observado y el motivo concreto del rechazo, además del contador final.
- No añado otras mejoras de producto: lo pendiente de esta lane son los cinco arreglos y la precisión de sus garantías.

Entrega: `out/ui-revision5-astra.md`. Evidencia e inventario de archivos con hashes en [tmp/r5-manifiesto.tsv](../tmp/r5-manifiesto.tsv). No hay commit porque se revisó una copia de solo lectura y no se implementó ni publicó ningún arreglo. No se actualizó memoria compartida. El siguiente paso de Claude es corregir los cinco puntos y repetir sus positivos/negativos más los supervivientes, conservando los tres AR4 que aquí quedan cerrados.
