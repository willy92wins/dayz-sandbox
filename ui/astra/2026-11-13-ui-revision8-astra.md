# Octava y última revisión cruzada adversarial — Astra

## 1. Veredicto

**NO APTO:** un mutante nuevo de contraste obtiene `RESULT 13 pass, 0 fail` con la prueba oficial intacta de `dde1345`, aunque contiene tramos opacos a 2,904:1 en oscuro y 2,186:1 en claro.
AR7-01 queda **a medias** —su ataque original y los cuatro mutantes oficiales ya caen, pero la excepción de los extremos admite el falso PASS de AR8-01— y AR7-02 queda **arreglado**.
La interfaz sigue pareciendo moderna, profesional e intuitiva en las vistas examinadas de ambos temas; el bloqueo corresponde a la garantía del verificador, sin pedir otro diseño ni atribuir esos colores defectuosos al prototipo normal.

Revisión limitada a los arreglos de AR7-01 y AR7-02 del paquete atribuido a `dde1345`, frente a `fc28527`. **M** = `ctx/pruebas-mejoras.js`; **U** = `ctx/mutantes.js`; **E** = `ctx/estudio.html`; **LI** = `ctx/2026-11-04-ui-mejoras-consolidado.md`; **DI** = `ctx/2026-10-28-ui-m1-consolidado.md`. Las referencias de línea corresponden a esos archivos actuales.

**Integridad y alcance.** Los 48 SHA-256 de `ctx/SHA256SUMS.txt` coinciden. E tiene SHA-256 `d573290b09f00ad2aa1969698934512742660e9030fa3626c60acf6231ffa685`: además de coincidir con el informe R7 suministrado, coincide byte a byte con su mutante original después de retirar su única inyección CSS. M conserva SHA-256 `4ae516dfff70cdecac1d40c3803d97f27fd68a9b0bd6356e3ab1cd766736aa9b`. No hay `CLAUDE.md` en la raíz ni en `ctx`. Los identificadores de commit se atribuyen al paquete; no se accedió a un repositorio para certificarlos.

No se consultaron memoria, historial externo, vault, otras carpetas ni web; no se abrieron subagentes ni se instaló nada. Se escribieron este único entregable en `out/` y auxiliares `r8-*` en `tmp/`. Los artefactos de rondas anteriores se usaron solo como lectura. No se modificaron el prototipo, las pruebas oficiales ni las medidas aportadas.

## 2. Pruebas y procedencia

Chromium sí funciona en el sandbox: Node v24.14.1, Playwright 1.63.0, Windows, viewport de planta 1600 × 960 y DPR 1 salvo el control explícito a 1,25. Se fijaron `PLAYWRIGHT_BROWSERS_PATH`, `TEMP` y `TMP` dentro del workspace. Todas las corridas de navegador se ejecutaron secuencialmente.

**El apagado del PC a las 14:57 interrumpió la batería completa.** Su log conserva el control `RESULT 39 pass, 0 fail` y 35 mutantes detectados, pero ningún RESULT global: no se cuenta como una batería terminada. Tras la reanudación se repitieron los cuatro nuevos contra ambos verificadores; para el resultado completo de los 41 y los dos antiguos pendientes se usa la tanda aportada, expresamente identificada abajo.

No se repitió la suite completa de unos 17 minutos: se leyeron sus 260 líneas PASS y su RESULT, y se ejecutaron las selecciones relevantes. Los denominadores son comprobaciones, no escenarios independientes; las dos comprobaciones generales de red y errores aparecen en cada selección.

| Tanda | Resultado literal | Procedencia / alcance |
|---|---|---|
| Planta, `SOLO=^(UX-49\|AR6-02)` | `RESULT 17 pass, 0 fail` | Ejecutada antes del apagado; [log](../tmp/r8-planta.txt). Coincide con esos casos de `medidas/mejoras-nuevo.txt`. |
| Batería completa de mutantes | **Interrumpida; sin RESULT global** | [Log parcial](../tmp/r8-mutantes-oficiales.txt): control 39/39 y primeros 35 detectados. No se suman tandas para inventar un 41/41 ejecutado completo. |
| Cuatro nuevos, prueba actual intacta | Control `RESULT 9 pass, 0 fail`; cada mutante `RESULT 3 pass, 6 fail`; final `RESULT 4 mutantes detectados, 0 sin detectar` | [Ejecutor reducido](../tmp/r8-cuatro-actual.js), [log](../tmp/r8-cuatro-actual.txt). Solo cambia rutas y selecciona las cuatro entradas nuevas de U; coincide con `medidas/mutantes.txt`. |
| Los mismos cuatro, prueba fc28527 intacta | Control y cada mutante `RESULT 9 pass, 0 fail`; final `RESULT 0 mutantes detectados, 4 sin detectar` | [Ejecutor](../tmp/r8-cuatro-baseline.js), [log](../tmp/r8-cuatro-baseline.txt). Coincide con los cuatro supervivientes aportados. |
| Ataque original R7, M intacto | `RESULT 3 pass, 6 fail` | [Log](../tmp/r8-original-r7.txt); lee directamente `tmp-ronda7/r7-mut-contraste.html`, con UX-49+ y AR6-02+ en ambos temas. Caen contraste, autobús, generador y traslación; no es una reconstrucción del ataque. |
| Casos AR7 oficiales completos | `RESULT 16 pass, 0 fail` | [Log](../tmp/r8-ar7.txt): 14 AR7 + 2 generales. Cuatro controles de planta/traslación, ocho negativos de contraste y dos casos de mensajes. |
| Sonda exploratoria propia | `RESULT 4 pass, 0 fail` | [Casos](../tmp/r8-sondeo-casos.js), [log](../tmp/r8-sondeo.txt), [oscuro](../tmp/r8-sondeo-dark.json), [claro](../tmp/r8-sondeo-light.json). **46 observaciones**, 23 por tema; el RESULT solo afirma los dos controles y las dos comprobaciones generales, no que los 46 ataques se rechacen. |
| Mutante nuevo: extremos de segmentos, M intacto | **`RESULT 13 pass, 0 fail`** | [HTML](../tmp/r8-mut-segmentos.html), [log](../tmp/r8-mut-segmentos.txt). Falso PASS: UX-49+, AR6-02+ y AR7-01+, ambos temas, dos objetos y traslaciones. |
| Contramutante: débil en el centro, M intacto | `RESULT 3 pass, 10 fail` | [HTML](../tmp/r8-mut-centro.html), [log](../tmp/r8-mut-centro.txt). Mismos colores, cantidades y geometría; cambia su posición dentro del segmento. Rechazado por contraste. |
| Mutante nuevo: extremo de barra, M intacto | **`RESULT 13 pass, 0 fail`** | [HTML](../tmp/r8-mut-barra-extremo.html), [log](../tmp/r8-mut-barra-extremo.txt). Mismo mecanismo de AR8-01. |
| Capturas directas, sin sonda | `RESULT 12 capturas directas de vistas previas, sin sonda` | [Script](../tmp/r8-capturas.js), [log](../tmp/r8-capturas.txt), [DOM/DPR](../tmp/r8-direct.json): normal y cinco variantes × dos temas; incluye recortes de planta/barra. |
| Mensajes antiguos sobre los casos AR7-02 nuevos | `RESULT 3 pass, 1 fail` | [Copia de prueba](../tmp/r8-mensajes-viejos.js), [log](../tmp/r8-mensajes-viejos.txt). Solo se repone M antiguo:1075 en M actual:1076. El positivo sigue pasando y el negativo rechaza el mensaje antiguo. |
| Caja totalmente transparente sobre toda la cifra | `RESULT 3 pass, 0 fail` | [Sonda](../tmp/r8-caja.js), [log final](../tmp/r8-caja-final.txt). PNG antes/después idénticos; 6275 queda sin acreditar y el mensaje dice «sin ningún píxel de su letra comparado». |
| Control de densidad 1,25 | `RESULT 2 pass, 4 fail` | [Copia](../tmp/r8-dpr125.js), [log](../tmp/r8-dpr125.txt). Solo cambia `deviceScaleFactor`; falla el prototipo normal por mezcla de coordenadas. Es el límite ya publicado en LI:558, no otro hallazgo ni un falso PASS. |
| Suite completa actual | **Aportada:** `RESULT 260 pass, 0 fail` | `medidas/mejoras-nuevo.txt:261`; 260 PASS comprobados, cero FAIL. No reejecutada completa. |
| Mutantes completos actuales | **Aportada:** `RESULT 41 mutantes detectados, 0 sin detectar` | `medidas/mutantes.txt:43`, control 39/39. Los 37 anteriores y cuatro nuevos están detectados en esa tanda. |
| Mutantes actuales con prueba anterior | **Aportada:** `RESULT 37 mutantes detectados, 4 sin detectar` | `medidas/mutantes-dde1345-con-pruebas-fc28527.txt:43`. Sobreviven exactamente los cuatro nuevos. |
| Suite general | **Aportada:** `RESULT 64 pass, 0 fail` | `medidas/pruebas-nuevo.txt:67`; no reejecutada, E no cambia. |

La primera sonda de caja transparente y su diagnóstico dieron `RESULT 2 pass, 1 fail` ([primera](../tmp/r8-caja.txt), [diagnóstico](../tmp/r8-caja-diag.txt)): PowerShell había escrito `ning?n p?xel` en mi aserción. El diagnóstico aisló `r0=true`, `r=false`, PNG idénticos y mensaje correcto. Tras usar escapes Unicode únicamente en esa aserción, pasa 3/3; no fue un fallo del producto ni de M.

La selección AR7 coincide en estado con las medidas aportadas, no en todas las cuentas de raster: el transparente parcial da aquí **19 píxeles de letra comparados, 168 sin comparar, 0 distintos**; la tanda aportada da 22, 168 y 0, y LI:542 cita 20/180 de su contenedor. No mezclo esas cuentas ni atribuyo una causa a esa variación **[sin verificar]**; el rechazo conservador y el mensaje coinciden.

## 3. Estado de los dos hallazgos de R7

| Hallazgo | Estado | Evidencia | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| **AR7-01** | **A medias** | M:2155, 2168–2176, 2195–2204; U:66–69; original R7 3/6 y cuatro oficiales 3/6 cada uno. Mutante nuevo 13/0. | **Sí** para el ataque original, un tramo central largo, la línea inferior de la barra y el redondeo; **no** para todos los colores/tramos opacos: `run.slice(1,-1)` omite los extremos sin comprobar que sean antialias. AR8-01 demuestra el falso PASS. |
| **AR7-02** | **Arreglado** | M:71–74, 401–427, 458–460, 1076, 2875–2905, 2993–3015; LI:479, 511, 528, 542; DI:189, 357, 366, 375, 457. Casos oficiales pasan; mensajes antiguos fallan; transparente total conserva PNG y queda sin comparar. | **Sí**, dentro del muestreo ya definido: se excluye conservadoramente la caja admitida y `cut` impide acreditar texto con muestras excluidas. La explicación vigente ya no promete una máscara exacta de pintura ni llama invisibles a los píxeles omitidos. No se cambió ese algoritmo al corregir el lenguaje. |

El contraste ya **no se redondea antes de decidir**: M:2155 devuelve la razón real y M:2201 compara `lo`/`barLo` con 3; M:2204 solo trunca la presentación. Cálculo independiente de los grises del cuarto mutante: `#68686a` sobre RGB(28,30,35) = **2,999043419:1**, y `#909092` sobre RGB(247,248,250) = **2,998715975:1**. Ambos son inferiores a 3 y se rechazan. Los cuatro nuevos se ejercitan en los dos temas por la selección de U y por los casos AR7-01−, no solo por una afirmación documental.

## 4. Hallazgo nuevo

| ID | Gravedad | Regla | Dónde | Qué pasa | Evidencia | Arreglo propuesto | Criterio verificable + / − |
|---|---|---|---|---|---|---|---|
| **AR8-01** | **BLOQUEA** | AR7-01 / CU-40: acreditar el contraste de los tramos que forman los lados y la barra, sin confundir un color débil opaco con cobertura antialias | M:2168–2172, 2176 y 2201; `#libPrev .pv-fp::after` y `.pv-sc .scale i::after`; promesa de DI:191 y LI:541 | Se omiten automáticamente la primera y última posición de cada tramo de más de dos posiciones; los de dos valen por su máximo. No se prueba que lo omitido sea un extremo fundido. Cinco segmentos opacos **débil–fuerte–débil** pasan porque solo cuenta el centro. La barra presenta la misma evasión en su extremo. | [Mutante](../tmp/r8-mut-segmentos.html), líneas 589–590, **[RESULT 13 pass, 0 fail](../tmp/r8-mut-segmentos.txt)** con M intacto; [barra](../tmp/r8-mut-barra-extremo.html), **[RESULT 13 pass, 0 fail](../tmp/r8-mut-barra-extremo.txt)**; [píxeles independientes](../tmp/r8-direct-pixels.json). | **[DESIGN]** Separar color de trazo y cobertura: no conceder la excepción por la posición del píxel. Para estas figuras fijas, acreditar los colores y el antialias del dibujo admitido, o rechazar como no acreditadas las variantes multicolor/repintadas que no se modelan; mantener medida geométrica y contraste sin redondear. Añadir los mutantes conservados y corregir la promesa de cierre. No se implementa en esta revisión. | **+** Plantas y barras normales, autobús/generador, ambos temas y traslación conservan PASS con su antialias real. **−** `r8-mut-segmentos.html` y `r8-mut-barra-extremo.html` dejan de obtener aprobación de contraste, sin alterar dimensiones; el contramutante central sigue cayendo. Un color opaco inferior a 3 no se acredita por estar en el extremo. |

### Falso PASS y mecanismo aislado

El mutante añade únicamente las dos reglas CSS de las líneas 589–590 a una copia de E. No cambia JavaScript, dimensiones, datos, `__cv`, `SOLO` ni el código de M. El [delta exacto](../tmp/r8-delta-segmentos.txt) y los hashes permiten comprobarlo. `pointer-events:none` conserva la prueba de los doce puntos sobre la planta; las dimensiones siguen siendo **114 × 25** y **48 × 32**, con barra de **50** y **40 px**, sin giro ni escala.

En 33 px del borde superior dibuja cinco segmentos de tres píxeles, separados por tres píxeles de fondo. Cada segmento lleva dos colores débiles opacos en sus extremos y uno fuerte en el centro. El CSS usa saltos de color abruptos y `opacity:1`; las capturas directas sin instrumentación contienen exactamente esos RGB. **No deduzco antialias a partir de un parecido visual:** aquí se conoce la regla que pinta cada color y la captura confirma su cobertura completa.

| Tema | Fondo capturado | Extremos opacos | Contraste independiente | Centro fuerte | Contraste que M acredita |
|---|---|---|---|---|---|
| Oscuro | RGB(28,30,35) | 10 píxeles RGB(102,102,102) | **2,904159780:1** | RGB(153,153,153), 5,852947744:1 | **5,85:1** |
| Claro | RGB(247,248,250) | 10 píxeles RGB(170,170,170) | **2,186193485:1** | RGB(102,102,102), 5,403401033:1 | **5,40:1** |

Los diez píxeles débiles aparecen en la fila 0 del recorte de planta, columnas **11, 13, 17, 19, 23, 25, 29, 31, 35 y 37**, en ambos temas. Capturas: [oscura](../tmp/r8-direct-fp-dark-segmentos.png), [clara](../tmp/r8-direct-fp-light-segmentos.png); contexto: [vista previa oscura](../tmp/r8-direct-prev-dark-segmentos.png), [clara](../tmp/r8-direct-prev-light-segmentos.png). La caja CSS mide 114 × 25; el PNG del elemento mide 114 × 26 por el recorte de sus coordenadas fraccionarias y conserva una fila adicional de fondo. No se ha reescalado para calcular contrastes.

Los píxeles débiles también superan el umbral de tinta: alejamiento máximo RGB **74 ≥ 62,5** en oscuro y **80 ≥ 74** en claro. No desaparecen por la segmentación de M:2159; entran en el tramo y luego se descartan por su posición.

El [lector independiente](../tmp/r8-direct-pixels.py) decodifica el PNG con `struct`/`zlib` y calcula luminancia sin llamar a `look`, `low` ni a funciones de E. Reutiliza solo el lector PNG suministrado de R7. Los [datos DOM](../tmp/r8-direct.json) registran DPR 1, geometría y las reglas opacas. El mutante de barra contiene **un píxel débil exacto en (0,0)** de su recorte, a los mismos contrastes; M informa 5,85/5,40 y lo aprueba.

**Experimento causal.** En [r8-mut-centro.html](../tmp/r8-mut-centro.html) se permutan centro y último extremo de cada segmento: **débil–débil–fuerte**. Se mantienen diez píxeles débiles, cinco fuertes, los mismos huecos, dimensiones y colores. El resultado oficial cambia de **13/0** a **3/10**, y el mínimo informado baja a 2,90/2,18. Esto aísla el descarte posicional de M:2172; no es un fallo provocado por dimensiones, eventos, fuentes o redondeo.

**Tamaño del hueco.** A DPR 1 se omite **una posición longitudinal de un píxel en cada extremo**, dos posiciones por tramo de longitud mayor que dos. En un tramo de tres, se omiten **dos tercios** de sus posiciones; el ejemplo acumula **10 píxeles débiles** en cinco tramos. Para longitud dos, una posición fuerte salva a la débil por `Math.max`; para longitud uno se evalúa ese único valor. Cada posición toma, además, el máximo dentro de una franja de dos píxeles. No existe comprobación de alfa/cobertura que limite esa excepción al antialias real.

LI:556 **ya reconoce** que un píxel fuerte entre dos flojos pasa: no presento ese límite como oculto. Lo nuevo es la reproducción con CSS opaco, el HTML guardado aprobado por M intacto, la medida independiente y el contramutante que aísla la causa. Documentar esa excepción no demuestra la promesa de contraste de CU-40: el encargo pide comprobar si «extremos fundidos con el fondo» admite otro falso PASS, y sí lo admite. Tampoco estoy exigiendo que todo píxel de antialias real alcance 3:1.

### Otras hipótesis de la misma propiedad

- **Esquina:** un píxel débil opaco en la esquina superior izquierda pasa en la sonda en ambos temas; la captura directa lo sitúa en (0,0). [HTML](../tmp/r8-mut-esquina.html). No se usa como una tercera reproducción oficial ni como otro hallazgo.
- **Un tema solamente:** un lado izquierdo débil solo en claro pasa en oscuro y se rechaza en claro. La selección sí distingue ambos temas.
- **Barra en otro sitio:** el mismo píxel débil colocado en medio de la línea inferior se rechaza en ambos temas; situado en el extremo vertical pasa, también en M intacto.
- **Segmentación por intensidad:** un borde sólido con 1–4 px interiores a `#555`/`#bbb` pasa en la sonda, y con 5 px se rechaza por hueco. El caso de 4 tiene ocho píxeles opacos débiles, cuatro arriba y cuatro abajo, a 2,236729/1,806640:1. Quedan por debajo del umbral de tinta de M:2159 y cuentan como hueco, tolerado hasta 4 por M:2195. [HTML](../tmp/r8-mut-solida-floja-4.html), [capturas medidas](../tmp/r8-direct-pixels.json). Es otra limitación de la misma acreditación, sin abrir otro hallazgo ni usarla en lugar del falso PASS oficial.
- **Otra densidad:** a DPR 1,25 el control normal falla; coincide con el límite ya publicado. No se atribuye ese resultado a la UI ni se amplía el contrato a otras densidades en esta ronda.

### Alcance del diff y reproducción

| Archivo | Líneas retiradas / añadidas frente a fc28527 | Lo que cambia |
|---|---|---|
| E | 0 / 0 respecto al HTML de R7 reconstruido quitando solo su inyección | SHA y comparación byte a byte; no hay arreglo de producto en esta ronda. |
| M | 30 / 110 | Mensajes/comentarios de exclusión; contraste sin redondear; franjas y mínimo por tramo; `planGeom`/`planSeen6`/`planSeen`; presentación; cuatro ramas nuevas de `bend`; 14 comprobaciones AR7. |
| U | 3 / 10 | Comentarios, coma al final del antiguo último mutante y cuatro entradas nuevas. Los **37 objetos de mutación anteriores son idénticos**, incluidos nombre, expresión `solo` y reemplazos; el ejecutor no cambia. |
| LI | 9 / 37 | Estado, precisión de las exclusiones y del contraste, procedencia de medidas anteriores y §17 con pruebas/límites de AR7. |
| DI | 7 / 20 | Estado, CU-38/CU-40, historia AR7 y resultados/acotaciones. |

Son diferencias textuales, no cambios funcionales independientes. [Estadística e intervalos](../tmp/r8-diff-stats.json); diffs completos conservados como `tmp/r8-diff-*.txt`. No aparecen cambios ajenos a los dos arreglos y a las precisiones documentales solicitadas en R7. Las 246 comprobaciones anteriores más las 14 nuevas suman 260; los 37 mutantes anteriores más cuatro suman 41. El código de `plain`/`painted`/`cut` y el resto de la página no cambian. La evidencia de los 37 anteriores completos procede de `medidas/`; la ejecución propia llegó a los primeros 35 antes del apagado.

Reproducción mínima del bloqueo, en una única llamada PowerShell desde `C:\tmp\dsbx-ui-astra-revision2`:

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH="C:\tmp\dsbx-ui-astra-revision2\pw"; $env:TEMP="C:\tmp\dsbx-ui-astra-revision2\tmp"; $env:TMP="C:\tmp\dsbx-ui-astra-revision2\tmp"; $env:ESTUDIO_URL="file:///C:/tmp/dsbx-ui-astra-revision2/tmp/r8-mut-segmentos.html"; $env:SOLO="^UX-49 \+$|^AR6-02 \+ |^AR7-01 \+ "; node ctx\pruebas-mejoras.js
```

Resultado obtenido: **`RESULT 13 pass, 0 fail`**, código de salida 0. Para el contraste causal, cambiar únicamente la URL a `r8-mut-centro.html`: **`RESULT 3 pass, 10 fail`**, código 1. Para la barra, URL `r8-mut-barra-extremo.html`: **`RESULT 13 pass, 0 fail`**, código 0. Las tres usan exactamente M, sin copiarlo ni editarlo.

SHA-256 del mutante principal: `72e941a6e17235a3f9345e178e9a0f2c8db8a476b5df00a679dbcc730ce03508`; de la barra: `317b3f6a6556589b7b7794521f9654c2f826f0a0f554e9d17e42f641b8abdd7d`. El inventario final de auxiliares, con líneas o bytes y hashes, queda en [r8-artifacts.tsv](../tmp/r8-artifacts.tsv).

**Choques con el plan/spec.** El único conflicto que impide cerrar es la acreditación universal de contraste de CU-40 frente a AR8-01. No se propone cambiar el umbral ni convertir una excepción de medición en un cambio de contrato. No se reabren letra, filas, radios, sombras, ámbar, colores del mapa, nombres, C-17 ni decisiones NO. No se certifica de nuevo todo M1, la usabilidad con usuarios ni el comportamiento del backend/juego; están fuera de esta revisión. El estado exacto del commit fuera de los archivos entregados queda **[sin verificar]**.

## 5. DISENSO-FUERTE

> **Mantengo la negativa a cerrar CU-40 por el verde, ahora por AR8-01.** Retiro el ataque concreto de R7: los tres lados débiles ya se rechazan, igual que los otros tres mutantes nuevos y el contraste real inferior a 3 que antes se redondeaba. Pero la prueba oficial intacta aprueba cinco segmentos opacos con extremos a 2,904:1 en oscuro y 2,186:1 en claro, y también un extremo débil de la barra: ambos HTML dan 13/13. Al mover esos mismos colores débiles al centro, sin cambiar cantidades ni geometría, falla 10 comprobaciones. El algoritmo no distingue un extremo antialias de un color opaco débil: lo omite por posición. Es un falso PASS demostrado dentro del alcance acordado, no una petición de rediseño ni de otra ronda abierta.

> **Doy por resuelto AR7-02 y mantengo mi juicio favorable del diseño.** Las cajas excluidas se describen ahora como no comparadas; una caja totalmente transparente conserva exactamente la imagen y ya no provoca un mensaje de invisibilidad. No mantengo una objeción a CU-38 por ese lenguaje, ni reabro las objeciones cerradas de R6. La interfaz examinada sigue pareciendo moderna, profesional e intuitiva; el único motivo de este NO APTO es la prueba de contraste de CU-40.

## 6. Para más adelante

- Conservar los mutantes y su motivo de rechazo como regresiones, además del RESULT agregado.
- Si se admite otra densidad, unificar las coordenadas CSS/raster antes de extender la garantía; DPR 1,25 sigue fuera de la medición válida.
- Registrar sistema, DPR, viewport y procedencia de cada tanda; no presentar la corrida interrumpida como completada.
