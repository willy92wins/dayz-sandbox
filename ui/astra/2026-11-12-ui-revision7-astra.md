# Séptima revisión cruzada adversarial — Astra

## 1. Veredicto

**NO APTO:** los ataques concretos de AR6 ya se detectan y la regla está corregida, pero la nueva medida de la planta admite un falso PASS de contraste, demostrado con el harness oficial intacto.
La interfaz sí parece moderna, profesional e intuitiva en ambos temas; la esquina corregida se entiende y no necesita rediseño.
Doy por arreglados AR6-01 para el falso aprobado denunciado y AR6-03, y por arreglado a medias AR6-02; quedan un hallazgo bloqueante del verificador y una corrección documental de gravedad baja.

Revisión del paquete atribuido a **fc28527**, frente a **5f513d9**. Abreviaturas: **E** = `ctx/estudio.html`; **M** = `ctx/pruebas-mejoras.js`; **U** = `ctx/mutantes.js`; **LI** = `ctx/2026-11-04-ui-mejoras-consolidado.md`; **DI** = `ctx/2026-10-28-ui-m1-consolidado.md`. Las líneas corresponden a esos archivos actuales. Contrato: `ctx/product-spec.md`; decisiones: `ctx/2026-10-26-m1-cine-v2.md`.

Los **43/43 SHA-256** de `ctx/SHA256SUMS.txt` coinciden. E: `d573290b09f00ad2aa1969698934512742660e9030fa3626c60acf6231ffa685`. No hay `CLAUDE.md` en la raíz del paquete. No consulté memoria, historial, vault, repositorios externos, `out-parado` ni `tmp-parado`; no abrí subagentes ni instalé nada. Solo escribí este entregable en `out/` y auxiliares `r7-*` en `tmp/`. Los identificadores de commit son los atribuidos al paquete: no se inspeccionó un repositorio para certificarlos.

## 2. Pruebas y evidencia

Chromium **sí arranca en el sandbox**. Navegadores ejecutados secuencialmente, con Playwright 1.63.0 y navegador/temporales del workspace. Las capturas principales usan DPR 1, Windows y las fuentes de este PC; no trasladé anchos de Linux. `document.fonts.check` devolvió true para las familias solicitadas; no lo uso como prueba de instalación ni de selección efectiva de cada glifo canvas. Los anchos que cito se midieron aquí.

**No repetí la suite completa de 17 minutos ni los 37 mutantes completos:** leí sus salidas aportadas y repetí el delta, sus controles, sus ataques originales y nuevas hipótesis. Los contadores de cada tanda permanecen separados. Un FAIL en mi sonda negativa significa que no logró rechazar el daño; no que el ataque haya sido detectado.

| Tanda | Resultado literal y procedencia | Alcance |
|---|---|---|
| a), suite completa | **Aportada, no ejecutada de nuevo:** `RESULT 246 pass, 0 fail`, `medidas/mejoras-nuevo.txt:247`. | 225 comprobaciones anteriores + 21 AR6; no 246 escenarios independientes. |
| Actual, `SOLO=^AR6` | **Ejecutada:** `RESULT 23 pass, 0 fail`, [log](../tmp/r7-ar6-current.txt). | 21 AR6 + 2 generales; coincide con los casos de a). |
| b), contra `5f513d9`, `SOLO=^AR6` | **Ejecutada:** `RESULT 17 pass, 6 fail`, [log](../tmp/r7-ar6-baseline.txt). | Coincide con `medidas/ar6-5f513d9.txt`: fallan exactamente tres tamaños encogidos × dos temas. |
| c), ejecutor completo | **Aportada, no ejecutada de nuevo:** control `RESULT 35 pass, 0 fail`; `RESULT 37 mutantes detectados, 0 sin detectar`, `medidas/mutantes.txt:39`. | Mis repeticiones del delta están en las dos filas siguientes. |
| Siete mutantes oficiales AR6 y controles | **Ejecutada:** `RESULT 14 ejecuciones de controles y mutantes AR6`, [resumen](../tmp/r7-official.json), [ejecutor](../tmp/r7-official.js). | 7 ataques + control con harness actual; 5 ataques + control con harness anterior. Actual control **11/11**; anterior **6/6**. Los siete caen ahora; los cinco de AR6-01/02 sobreviven antes. |
| Tres archivos mutantes originales de R6 | **Ejecutada:** `RESULT 3 ataques originales de R6 ejecutados`, [resumen](../tmp/r7-originales.json). | Se leen directamente `tmp-ronda6/r6-mut-caja-v2.html`, `r6-mut-outline.html` y `r6-mut-clip.html`: **2/1**, **3/2**, **3/2** pass/fail. Los tres daños originales se rechazan con M actual. |
| Sonda propia inicial | **Ejecutada:** `RESULT 16 pass, 9 fail`, [log](../tmp/r7-probe.txt), [casos](../tmp/r7-probe-cases.js). | Dos falsos aprobados de contraste, dos rellenos ignorados, dos barras interrumpidas, dos expectativas propias erróneas sobre una muesca y un falso rechazo de transparencia; desglosados abajo. No son nueve defectos del producto. |
| Mutante propio de contraste, M intacto | **Ejecutada:** `RESULT 9 pass, 0 fail`, [HTML](../tmp/r7-mut-contraste.html), [log](../tmp/r7-mut-contraste.txt). | UX-49+ y AR6-02+ en los dos temas, incluidos autobús, generador y traslación. **Falso PASS**, AR7-01. |
| Hueco de letra y límites de planta | **Ejecutada:** `RESULT 8 pass, 0 fail`, [log](../tmp/r7-extra.txt), [casos](../tmp/r7-extra-cases.js). | Dos aserciones sobre un hueco; cuatro observaciones de límites, que informan si el criterio acepta sin afirmar que deba aceptar; dos generales. |
| Barrido de mapa inicial | **Ejecutada:** `RESULT 55 pass, 3 fail`, [log](../tmp/r7-sweep.txt), [casos](../tmp/r7-sweep-cases.js). | 9 tamaños + 11 pasos de zoom + 7 desplazamientos + control sin sombras, por tema, y 2 generales. Los tres FAIL son lecturas de inventario durante resize sin espera, no colisiones. |
| Repetición del resize asentado | **Ejecutada:** `RESULT 22 pass, 0 fail`, [log](../tmp/r7-settled.txt). | Los mismos 9 tamaños y control sin sombras, por tema; 400 ms tras cada cambio de viewport. No falta ningún texto esperado ni hay solapamientos número/número o número/etiqueta. |
| Capturas propias sin sonda | **Ejecutada:** `RESULT 28 esquinas, 8 vistas previas, 8 avisos, 4 vistas enteras; 0 errores`, [script](../tmp/r7-visual.js), [datos](../tmp/r7-visual.json). | Dos versiones × dos temas × apertura a 1600/1440/1366/1280 y resize desde 1600 a los tres menores. Las ocho vistas previas son autobús y generador en ambas versiones y temas. |

Los **15/21** específicos contra el baseline son **11/11** de AR6-01/02 y **4/10** de AR6-03. «Prueban la sonda» explica correctamente por qué no discriminan las dos páginas, pero sus positivos **también miran la página**; no son once pruebas sintéticas puras. Los cuatro casos de apertura directa ya se cumplían: verificado por ejecución y capturas. Los inventarios M:1039–1053 son idénticos a los del harness anterior, incluido `v(z) >= 36`.

### Fidelidad de los mutantes reconstruidos

| Daño AR6 | Harness actual | Harness 5f513d9 | Motivo pertinente comprobado |
|---|---|---|---|
| Aviso recortado + velo | `RESULT 2 pass, 1 fail` | `RESULT 3 pass, 0 fail` | Diferencia de pantalla en 6275; no rechazo por texto ausente del canvas. |
| Aviso entero sobre tres cifras | `RESULT 2 pass, 1 fail` | `RESULT 3 pass, 0 fail` | Texto parcialmente excluido, `cut > 0`. |
| Contorno interior | `RESULT 3 pass, 2 fail` | `RESULT 5 pass, 0 fail` | Planta visible **96 × 7**, frente a caja **114 × 25**. |
| Muescas entre muestras | `RESULT 3 pass, 2 fail` | `RESULT 5 pass, 0 fail` | Hueco de **24 px** en un lado. |
| Barra recortada, de Claude | `RESULT 3 pass, 2 fail` | `RESULT 5 pass, 0 fail` | Tinta de **40 px**, caja de **50 px**. |
| Restituir solapamiento de regla | `RESULT 4 pass, 3 fail` | No ejecutado con aquel harness | Las tres vistas encogidas oscuras fallan por los numerales superpuestos. |
| Pintar Z antes que X | `RESULT 6 pass, 1 fail` | No ejecutado con aquel harness | Falta **6075** esperado a 1280 × 720. |

No exigí copias byte a byte de los mutantes reconstruidos: comprobé mecanismo y motivo del fallo, y repetí además los tres originales disponibles. Los dos últimos cambios de código se apoyan en la nueva línea de `ruler`; el baseline real ya aporta el negativo pertinente. Los denominadores 35, 11 y 6 son controles de **selecciones distintas**, no resultados contradictorios.

## 3. Estado de AR6

| Hallazgo | Estado | Evidencia | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| **AR6-01** | **Arreglado para el falso PASS denunciado** | M:405–459, 1072, 2662, 2858–2881; dos mutantes oficiales y el original R6 rechazan el daño. Aviso recortado: **46 píxeles distintos** aquí, `cut=0`; aviso entero parcial: **19 píxeles de letra medidos**, `cut=168`, `diff=0`. | **Sí**, como garantía conservadora: el recorte inseguro se compara, y una letra/hueco muestreado que quede excluido impide acreditar el texto. **No** demuestra una máscara exacta de superficie pintada: transparencia de fondo y radios siguen excluyendo caja completa; AR7-02. No encontré otro falso PASS por estas exclusiones. |
| **AR6-02** | **A medias** | M:2140–2188; autobús **114 × 25**, generador **48 × 32**; contorno interior, muescas y barra corta rechazados; AR7-01 sobre M intacto. | **Sí** para las dimensiones y los tres ataques concretos. **No** para asegurar el contraste de todos los lados: `ink` devuelve el contraste del píxel más apartado del fondo y `planSeen` lo atribuye a la planta completa. |
| **AR6-03** | **Arreglado** | E:1522–1532; M:2924–2935; baseline falla en seis vistas, actual pasa; negativos de solapamiento y prioridad invertida fallan por el motivo esperado; capturas y barrido propio. | **Sí** en las vistas verificadas. No se ha rebajado el inventario. X entra primero en `nums`; `hit(b, LBL)` impide colisiones entre placas; después `drawLabels` usa las placas ocupadas. No se certifican todos los encuadres imaginables. |

## 4. Hallazgos nuevos

BLOQUEA se usa con la definición del encargo: una prueba aprueba una propiedad que el dibujo no cumple. **AR7-01 está en el verificador; no afirma que la planta normal tenga esos colores.** Las propuestas son cambios mínimos de prueba/documentación, no nuevos colores ni rediseño del producto.

| ID | Gravedad | Mejora o regla | Dónde | Qué pasa | Evidencia | Arreglo propuesto, concreto | Criterio verificable + / − |
|---|---|---|---|---|---|---|---|
| **AR7-01** | **BLOQUEA** | AR6-02, CU-40, R26 | M:2152–2158 y 2187; `#libPrev .pv-fp`; afirmación de M:2900 y LI:512 | El contraste máximo de un solo lado acredita los otros tres. Con borde superior `#999` y los demás `#666` en oscuro, la prueba informa **5,85:1**, aunque tres lados tienen **2,904:1**. En claro, superior `#666` y resto `#aaa`: informa **5,40:1**, pero tres lados tienen **2,186:1**. Esos colores débiles superan la mitad del alejamiento máximo y cuentan para dimensión/continuidad, sin que se compruebe su contraste. | [Mutante mínimo](../tmp/r7-mut-contraste.html), [harness oficial 9/9](../tmp/r7-mut-contraste.txt), [captura oscura](../tmp/r7-shots/probe-dark-contraste.png), [clara](../tmp/r7-shots/probe-light-contraste.png), [medida independiente](../tmp/r7-contrast-independent.json). Se conservan dimensiones, traslación válida y 12/12 hits; también pasa el generador. | Para esta planta fija, acreditar cada color/tramo que define sus cuatro lados, tratando el antialias como cobertura, o rechazar como no acreditadas las variantes multicolor/repintadas que no modela la prueba. No usar el máximo como mínimo. Aplicar la misma corrección al contraste de la barra; comparar la razón sin redondearla y redondear solo para mostrar. Actualizar el cierre de LI:512 y CU-40. | **+** Ambas plantas intactas y trasladadas pasan en ambos temas, manteniendo las medidas actuales. **−** Este HTML hace fallar específicamente el contraste en UX-49+/AR6-02+; un único tramo o lado bajo no queda salvado por otro fuerte. Añadir el equivalente en la barra y un valor real inferior a 3 que se redondee a 3,00. |
| **AR7-02** | **BAJA** | AR6-01, CU-38, R26; documentación | M:400–426, LI:511 y 528, DI:189 y 366 | «Solo se aparta donde se pinta» no describe el algoritmo: sigue apartando rectángulos completos de fondos transparentes, semitransparentes o redondeados admitidos por `plain`. La salvaguarda que evita el falso PASS es `cut`, no una máscara de pintura. Un elemento totalmente transparente sobre 6275 hace decir «sin ningún píxel de su letra a la vista», aunque no ha cambiado la imagen. El límite de LI:528 admite precisamente la exclusión rectangular. | [Sonda](../tmp/r7-probe-cases.js), [log: transparente](../tmp/r7-probe.txt); E intacto, overlay sin fondo, borde ni sombra. M:409 comprueba `opacity`, pero no el alfa de `backgroundColor` ni radios. | Unificar la explicación: «se excluye conservadoramente la caja recortada de flotantes admitidos; un texto con muestras de letra/huecos excluidas no queda acreditado». Distinguir «no comparado» de «no visible». No hace falta cambiar los flotantes del producto. Si se quiere conservar la promesa de superficie exacta, entonces hay que implementar y probar esa máscara. | **+** La página normal conserva sus 29 textos acreditados. **−** El transparente se describe como no acreditado por exclusión, no como píxeles físicamente invisibles; los avisos parcial y recortado con velo siguen rechazándose. Una sola formulación coherente en prueba, LI y DI. |

### Medición independiente del falso PASS

El mutante añade únicamente CSS al HTML copiado, sin tocar M ni su sonda. La medida externa decodifica las capturas PNG con `struct`/`zlib` y calcula luminancia/contraste sin llamar a `look`, `planSeen` ni a funciones de E: [lector y cálculo](../tmp/r7-png.py). En el recorte de **114 × 25** hay **70 píxeles** del color débil exacto y **46** del color fuerte exacto, en cada tema; no se están confundiendo píxeles antialias con el color del borde.

| Tema | Fondo medido | Tres lados | Contraste independiente | Lado superior | Contraste que acredita M |
|---|---|---|---|---|---|
| Oscuro | RGB 28, 30, 35 | RGB 102, 102, 102 | **2,9041598:1** | RGB 153, 153, 153 | **5,85:1** |
| Claro | RGB 247, 248, 250 | RGB 170, 170, 170 | **2,1861935:1** | RGB 102, 102, 102 | **5,40:1** |

El umbral **3:1** sí tiene fundamento: [W3C, contraste no textual](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html), para las partes necesarias de una figura. No autoriza acreditar todos los lados con el máximo, ni redondear antes de decidir. M:2152 redondea antes de M:2187; es una corrección adicional de la misma comprobación, no otro hallazgo independiente. La demostración principal queda muy por debajo del umbral y no depende de esa discrepancia de redondeo.

## 5. Qué acreditan las exclusiones, los píxeles y los umbrales

**AR6-01.** Probé fondo transparente, fondo parcialmente transparente, borde redondo, solo borde, pseudo-elemento fuera de caja, `outline`, hijo desbordado y recorte por ancestro. No conseguí un falso PASS de texto dañado en esas variantes: las cajas conservadoras hacen fallar por `cut`, y la pintura fuera de ellas se compara y da distinta. El recorte inocuo por ancestro pasó. No se certifica que `painted` modele cada posible regla CSS: por ejemplo, termina antes de `body` y aproxima un recorte por overflow con un rectángulo. La seguridad observada procede también de no acreditar las muestras omitidas.

La comprobación de un hueco fue específica: añadí **un píxel rojo** sobre un hueco de 6275, dentro de un flotante reconocido. Quedaron **65/65** muestras de letra, `diff=0`, `cut=1`, y la vista falló. Por tanto, el texto entero con un hueco excluido no pasa. Es una regla estricta adecuada para **acreditar cobertura de medida**, no una prueba de que una persona ya no pueda leer una cifra por un píxel. Su exceso produce falsos rechazos conservadores, como el transparente; no justifica relajar `cut` y resucitar el defecto de R6.

«Sus 29 textos se comparan enteros» es correcto en el sentido del instrumento: 29 registros con muestras completas de letra y huecos, sin `cut`. No significa todos los píxeles antialias: M:148–152 toma letra con cobertura ≥383/765, huecos con cobertura <16/765 y contraste previo suficiente; el anillo tampoco entra en `cut`. Esta selección es heredada, no una nueva excepción introducida para pasar AR6. No demostré un texto ilegible que sobreviviera por esa selección.

**Composición en Windows.** El control a 1600 × 960 tiene lienzo **1022 × 856**, caja CSS **1022 × 855,609375** y captura **1022 × 855**. El ajuste es **[0,0]**. Al quitar únicamente las sombras CSS, comparé **813.058 píxeles** por tema con diferencia máxima **0**. Con sombras, el exterior de sus rectángulos modelados llega a **2/255** en oscuro y **0** en claro; no uso una cola de sombra no modelada como prueba de remuestreo. El ±1 de dimensión admite la última fila cortada, no una escala arbitraria. El dato de 18 vistas Linux a ≤1/255 tiene ya entorno y recorrido publicados en LI:478 y DI:450; su ejecución histórica exacta sigue **[sin verificar]** aquí.

| Umbral/regla | Juicio |
|---|---|
| ±1 px para dimensión de planta/barra | Tolerancia de rasterización razonable para estas figuras fijas, ligada a DPR 1 y su tamaño. Es un margen absoluto: en 25 px permite un 4 %. No prueba precisión ilimitada ni tamaños reales del modelo. Las plantas y barras normales se midieron exactas, sin consumirlo. |
| Máximo 4 px consecutivos sin tinta | Elección local, no estándar. Está cercana a los huecos normales de 2–3 px y detecta las muescas de 24 px. Lo relevante es el **hueco total resultante**, no solo el ancho de la muesca. Mi muesca de 4 px se unió al discontinuo y dejó 8: se rechazó; fue erróneo esperar que pasara. Una de 2 px sí pasó, con hueco máximo 3. |
| Tinta a ≥ la mitad del alejamiento máximo | Segmentación heurística, no medida perceptiva ni garantía de contraste. Sirve para obtener la envolvente normal, pero no basta para propiedades universales. El falso PASS de AR7-01 está demostrado. |
| 3:1 | Umbral externo válido; la aplicación actual usa un máximo y redondea demasiado pronto. No debe exigirse 3:1 a cada píxel antialias bruto, sino acreditar los colores/tramos que transmiten la figura. |
| 8/255 y ajuste global ±1 del mapa | Se conservan sin cambios. El control aislado da cero; el margen no demuestra igualdad matemática. No apareció otro borrado aprobado por este margen en los ataques de esta ronda. |
| 4,5:1 para texto | Tiene fundamento en [W3C, contraste mínimo](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html). Tampoco equivale por sí solo a reconocimiento humano del texto. |

**Límites de la planta ejercitados, sin inflar el número de hallazgos:**

- Cambiar el discontinuo por borde sólido pasa con hueco máximo 0. Coincide con el límite publicado LI:529: no se verifica que el patrón sea exactamente el de la página. No altera la escala y no lo convierto en una nueva exigencia visual.
- Un relleno `#666` en oscuro o `#aaa` en claro se ve dentro, pero queda por debajo del umbral relativo y M declara `inner=0`. [Ejemplo](../tmp/r7-shots/probe-dark-relleno.png). «Nada dentro» debe leerse como «ningún píxel clasificado como tinta», no como ausencia física de otra pintura.
- Una barra con el 80 % central quitado conserva extremos separados 50 px y pasa. M verifica la envolvente de tinta, no la continuidad de la barra; esa envolvente sigue teniendo 50 px. No presento esto como una medida de 40 o 100 px aprobada como 50.
- Un segundo trazo de 100 px **debajo de la fila** tampoco entra en `look`: [oscuro](../tmp/r7-shots/limite-dark-fuera.png), [claro](../tmp/r7-shots/limite-light-fuera.png). El original de 50 px sigue presente. Esto demuestra que recortar a `.pv-plan` no acredita ausencia de dibujos extra en toda la vista previa, no que haya medido 100 como 50. Un trazo extendido dentro del área inspeccionada sí falló, por planta de 219 × 25 y barra de 52 px. No propongo ampliar CU-40 a un comparador universal de CSS.

### Verificaciones complementarias

- **d), ejecutada de nuevo:** `RESULT 64 pass, 0 fail`, [log](../tmp/r7-pruebas.txt), coincidente con `medidas/pruebas-nuevo.txt`. Generó las once capturas en `tmp/r7-original-shots/`; miré directamente suelo/propiedades, rodando, parando y toma reconciliada. No se reabre la batería de reconexión AR5: el delta no toca ese mecanismo.
- **Control exacto del mutante propio:** misma selección UX-49+/AR6-02+, HTML intacto, `RESULT 9 pass, 0 fail`, [log](../tmp/r7-control-contraste.txt). Control y mutante dan ambos 9/9; la medida independiente demuestra cuál incumple el umbral.
- **Densidad de pantalla emulada 1,25:** `RESULT 2 pass, 6 fail`, [log](../tmp/r7-dpr125.txt). Solo cambié `deviceScaleFactor` en una copia de M. Fallan los dos positivos de AR6-01 y los cuatro de AR6-02; los dos PASS son comprobaciones generales. `look` mezcla índices del PNG físico con coordenadas CSS de `r.sc`/`r.bar`: llega a atribuir a la planta toda la fila (**370 × 49**) y barra 0. **No es una planta realmente de 370 px ni prueba de UI ilegible.** Confirma que el verificador no es reutilizable tal cual a esa densidad. No lo declaro regresión del producto: el límite de escala 1 ya está documentado. El zoom real de navegador queda **[sin verificar]**; densidad emulada y zoom no son equivalentes.

## 6. Regla y aspecto

Miré las **28 capturas de esquina** y las **8 vistas previas** propias, además de las dos páginas completas actuales a 1440 × 900, los dos avisos actuales tras encoger a 1280 × 720, cuatro capturas del flujo de d), los ataques y las anomalías iniciales de resize. No presento las capturas no miradas como una revisión visual completa.

Al encoger desde 1600, la diferencia visible es precisa: a 1440 queda **6050** íntegro y luego **7725** en el eje vertical; a 1280 queda **6075** íntegro y luego **7700**. El baseline enseña las cifras superpuestas en esas esquinas. A 1366 y en las cuatro aperturas directas no hay daño que corregir en la esquina capturada. [Actual 1440 oscuro](../tmp/r7-shots/actual-dark-1440-r1-esquina.png), [baseline](../tmp/r7-shots/antes-dark-1440-r1-esquina.png), [actual 1280 claro](../tmp/r7-shots/actual-light-1280-r1-esquina.png).

No vi confusión por omitir aquel Z: quedan el eje, las líneas de rejilla y el siguiente numeral vertical; tampoco aparece otro valor fingiendo ocupar su sitio. Es una salida mínima coherente con la regla ya existente de no pintar números cortados u ocultos. El inventario independiente ya dejaba fuera la franja superior de Z: no se cambió después para conseguir verde. **No equivale a permitir borrar cualquier Z**: a partir de 36 px los esperados siguen exigidos, y el negativo que borra X falla.

El barrido adicional recorre 1600×960 → 1366×768 → 1280×720 → 1440×900 → 1440×901 → 1920×1080 → 1280×800 → 1600×961 → 1536×864, más cinco alejamientos, seis acercamientos y siete desplazamientos con botón derecho. No encontré colisiones de números ni con etiquetas. Las tres lecturas inicialmente fallidas mezclaban el inventario con el resize todavía sin asentar; repitiendo tamaños con 400 ms, pasan los 20 controles específicos. No uso esos falsos negativos propios como un hallazgo de E.

La composición mantiene mapa central, jerarquía a la izquierda, propiedades/Añadir a la derecha y controles de rodaje estables. La vista previa explica el objeto, sus medidas de muestra y su planta sin ocupar el mapa. Es moderna y profesional dentro del diseño acordado; no veo razón para reabrir letra, filas, radios, sombras, ámbar, colores, barra o nombres. El [referente público de Unreal](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface) respalda esa organización de viewport, Outliner, Details y Play/Stop; no se usa para atribuirle los valores exactos de esta maqueta. No se buscó DayZ Sandbox en la web.

### Observaciones heredadas que pidió juzgar Guillermo

No las convierto en regresiones de fc28527 ni en una lista nueva de implementación fuera del encargo.

| Observación | Dictamen y evidencia |
|---|---|
| Punto decimal en los campos de posición | **No reproducido visualmente en esta tanda Windows.** En [suelo/propiedades](../tmp/r7-original-shots/03-suelo.png) se ven **6207,6** y **7651,5**, con coma. E:2043 usa `toFixed` para el atributo `value` de `input type=number`; eso no acredita qué separador pinta el control nativo. Puede ser una inconsistencia **BAJA** en otro entorno, pero la frase universal de LI:533 necesita acotarse. No afirmo un problema de conversión de datos. |
| Bidones superpuestos a escala de escena | **BAJA de legibilidad espacial, heredada.** Visible en las capturas generales; son marcadores próximos en el encuadre de toda la escena. No se cambió la fixture para ocultarlo ni afecta al arreglo de regla. |
| Aviso de bienvenida tapa «Plano general» a 1280 × 720 | **MEDIA de legibilidad transitoria, heredada y declarada**, no otro bloqueo AR6. Confirmado en [oscuro](../tmp/r7-shots/actual-dark-1280-r1-aviso.png) y [claro](../tmp/r7-shots/actual-light-1280-r1-aviso.png). E:1577 excluye `.ovl`, leyenda, ayuda y rec, pero no toasts al colocar etiquetas. La sonda ahora rechaza texto tapado si se mide mientras está el aviso; esperar a que se vaya no certifica ese instante. No contradigo el límite ya declarado convirtiéndolo aquí en una nueva obligación de recolocar avisos. |
| Selector cerrado de clase ajena recorta la advertencia | **BAJA heredada, sin reproducción visual nueva.** E:2086–2090 conserva clase y coletilla; el código es idéntico al revisado en R6. El recorte actual de esa fixture queda **[sin verificar]** por captura en esta ronda. No reabre AR4-06 ni se confunde clase desconocida con primera opción del catálogo. |
| «Fallida · parada sin confirmar» junto a «Reaplicar y preparar la 05» | **BAJA heredada**, sin un nuevo defecto de estado. E:255–256 y 2336–2349 conservan ellipsis y texto completo en `title`; ese CSS/HTML no cambió. El informe R6 del paquete, §6, documenta **131/170 px a 1366** y **170/170 a 1440** en Windows. No repetí aquella fixture exacta; su persistencia visual hoy queda **[sin verificar]**, aunque no hay delta que la corrija. La captura nueva de d) muestra otra toma, ya reconciliada: no la hago pasar por esa evidencia. |

## 7. Contrato, alcance y documentación

| Obligación | Resultado comprobado y límite |
|---|---|
| D2: seis estados, edad y origen | E:811 conserva Pendiente/Ejecutando/Aplicado/Observado/Fallido/Parcial; E:1111–1118 y 2293 distinguen petición, lectura y origen. d) verifica aplicación, parcial, pérdida/vuelta, pendiente y estados de toma. No se inventa Observado por el cambio de regla. Son datos simulados, no observaciones de DayZ real. |
| B5 y CU-25: Parar visible, sin diálogo | E:606, 1366–1380 y 1967 en adelante no cambian; d) pasa y las capturas 07/08 muestran Parar/Parando en la barra superior. No se certifican otra vez todos los layouts personalizados ni el retorno de control retail <1 s. |
| #4: una preparación | E:1279–1320 conserva una preparación y Armada como precondición de `roll`. d) arma y rueda. No se añadió una segunda preparación. |
| #7: documento como fuente | E:1156 usa snapshot del documento; el delta no altera edición/guardado/deshacer. El backend real y su guardado atómico siguen fuera de esta maqueta. |
| #9: aplicar = reset y crear | E:1159–1186 conserva quitar lo anterior, crear por lotes, leer y publicar; d) lo recorre. No hay aplicación incremental añadida. |
| #10: ids lógicos | E:1870 y 1914 mantienen ids lógicos, evitando reutilizar los de la escena viva; E:1318 conserva epoch de toma. Sin cambios en ese mecanismo, sin handles de motor introducidos. |
| CU-35 | E:2392 mantiene «MCP apagado»; capturas y d) lo muestran. Las pruebas ejecutadas no registraron peticiones externas de la página. No se ha iniciado MCP. |
| CU-37 | Se mantiene bloqueo sin backend; d) verifica aviso, guardado bloqueado, propiedades bloqueadas y recuperación. |
| CU-38 | Los dos obstáculos AR6-01/03 están resueltos en el ámbito medido. Ajustar el lenguaje de exclusión, AR7-02; no convertir el resultado en garantía universal de vistas/densidades/avisos. |
| CU-39 | No se modifica iconografía ni tratamiento de clases ajenas. La selección UX-49 conserva el icono esperado. No se reabre AR4-06 ni se vuelve a certificar toda su matriz. |
| CU-40 | Tamaños normales y los ataques geométricos de R6 están acreditados. La nueva garantía de contraste de planta queda bloqueada por AR7-01. La ausencia de capturas reales/caja de modelo sigue siendo C-17 y **no es hallazgo**. |

**R20/R25:** no hay ampliación de M1. El único cambio del prototipo son dos líneas retiradas y cuatro añadidas en `ruler`/comentario; todo el resto de E, incluido su CSS, permanece idéntico. Los diffs están en `tmp/r7-diff-*.txt`.

| Archivo y delta de líneas | Trazabilidad completa |
|---|---|
| E: −2 / +4 | AR6-03: comprobar las placas ya pintadas y explicar prioridad X. |
| M: −13 / +173 | AR6-01: `plain`, `painted`, `cut`, `readable`, `allSeen` y positivos/negativos; AR6-02: `look`, adaptación async de `preview`, `planFits5`, `planSeen`, mensajes, tres ramas de `bend` y casos; AR6-03: `rulerHits` y recorridos. Comentarios respectivos. Inventario sin cambios. |
| U: −5 / +16 | Siete nuevos ataques AR6, comentarios y actualización de dos anclas de mutantes previos a la nueva línea `ruler`; se conserva el mecanismo de aquellos negativos. |
| LI: −9 / +40 | Estado, acotaciones solicitadas en §15 y nueva §16: hallazgos, pruebas y límites AR6. |
| DI: −7 / +22 | Estado, CU-38/CU-40, historia de §11, precisión de la tanda Linux y resultados AR6 de §12. |

Son líneas de texto sustituidas/añadidas, no un recuento de cambios funcionales independientes. No encontré una línea nueva ajena a AR6 o a las acotaciones de §7 de R6. No se tocaron parada, reconexión ni procedencia WebGL; AR5-01, AR5-03 y AR5-05 permanecen cerrados con el alcance anterior. No entra 3D, multiusuario, vídeo, otro mapa, MCP, eventos o IA propia.

**Documentos:** las acotaciones históricas de §15 y los cambios de Estado/§11/§12 están hechos, y la aritmética es correcta: **4 + 7 + 10 = 21**, **225 + 21 = 246**, **15 + 6 = 21**, **30 + 7 = 37**. Seis nuevos mutantes proceden de los ataques/negativos de Astra y uno, la barra, es de Claude. Los informes distinguen ronda revisada de arreglos todavía pendientes de revisión.

Quedan estas correcciones precisas, sin crear otra regla vigente:

- **AR7-01:** no afirmar que el contraste de la planta completa está probado hasta rechazar el mutante; la cifra máxima no lo demuestra. Mantener la corrección geométrica que sí está acreditada.
- **AR7-02:** sustituir la promesa de «superficie pintada» por la exclusión conservadora real, coherente con LI:528. «Sin comparar» no significa «invisible». Acotar también «nada dentro» al clasificador que se está usando.
- Identificar expresamente como **Linux/Claude** los números de píxeles de LI:511/513/520: **57 distintos**, **74/94**, **70–74 de 92/94** y **41/81**. No son los de la reproducción Windows actual (**46**, **63/89**, **65/89**, **32/76**). No es evidencia de que aquella tanda fuera falsa; sí exige no mezclarlas bajo un mismo «aquí».
- Mantener el denominador y procedencia: 246/246 y 37 mutantes son las tandas aportadas; esta revisión repite selecciones distintas. Las 18 vistas Linux históricas están identificadas, pero su raster granular no se ha reejecutado aquí.
- La anotación del separador decimal no describe la captura Windows de esta ronda; especificar entorno, en vez de derivar la presentación del atributo HTML.

## 8. DISENSO-FUERTE

> **Retiro la negativa a cerrar CU-38 basada en AR6-01 y AR6-03, dentro de las vistas y escala verificadas.** Los ataques de exclusión de la sexta ronda ahora se rechazan, incluido mi archivo original, y un solo hueco muestreado excluido impide acreditar el texto. La regla deja de superponer los numerales al encoger y conserva el inventario independiente. La omisión del Z de la esquina se entiende. Hay que describir la exclusión como conservadora, no como una máscara exacta de pintura, y no vender el verde como cobertura de cualquier densidad, aviso o encuadre.

> **Cambio el motivo por el que no cerraría CU-40 por el verde.** Retiro los ataques del contorno interior y las muescas de la sexta ronda: ahora caen y las plantas normales miden aquí 114 × 25 y 48 × 32. Pero la nueva prueba aprueba tres lados a 2,90:1 en oscuro y 2,19:1 en claro porque un lado fuerte acredita toda la planta; el harness oficial intacto da 9/9 al mutante. Mantengo NO APTO hasta que la comprobación de contraste rechace ese caso por la propiedad pertinente. No pido cambiar colores, medidas ni diseño de la planta normal.

> **Mantengo el juicio favorable sobre el diseño y la retirada del disenso sobre Parando.** La interfaz parece moderna, profesional e intuitiva; Parar sigue visible y la web distingue la toma fallida de su reconciliación observada. No reabro letra, filas, radios, sombras, ámbar, colores del mapa, barra, nombres ni C-17. Las confirmaciones reales de F2/F5 siguen requiriendo sus propias pruebas.

## 9. Para más adelante

- Mantener los mutantes con sus controles y motivo de rechazo, además del RESULT agregado.
- Si se amplía la aceptación a otras densidades, unificar coordenadas CSS/raster antes de reutilizar la sonda.
- Registrar sistema, fuentes, DPR, viewport y recorrido en cada tanda gráfica.
- No propongo otras mejoras de producto en esta ronda.

**Entrega y handoff:** `out/ui-revision7-astra.md`. Claude debe corregir AR7-01 y ajustar AR7-02/documentación; conservar los cierres y límites explícitos anteriores. No hay commit: esta lane es una revisión de solo lectura sobre el paquete, sin implementación ni publicación. No se escribe memoria compartida ni archivos fuera del workspace autorizado.

Integridad de entrega: UTF-8 sin BOM, enlaces locales comprobados y 43/43 hashes de entrada intactos al cerrar. [Manifiesto de archivos y evidencia auxiliar](../tmp/r7-manifiesto.tsv).
