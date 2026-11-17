# Tercera revisión cruzada adversarial — Astra

Fecha: 2026-11-10. Objeto: `ctx/estudio.html`, paquete identificado como `7a047bf`; comparación con `f9a7d97` y `b106329`. Revisión de solo lectura, sin implementación ni agentes auxiliares.

## 1. Veredicto

**NO APTO:** quedan dos bloqueos demostrados, la aceptación falsa de dibujos incorrectos y una reconciliación que confirma una parada después de volver a perder la conexión. **Sí parece ya una interfaz moderna y profesional**, con mejoras verificables de jerarquía, alineación y estabilidad del transporte; los recorridos normales son más claros, pero no la considero todavía fiable ni completamente intuitiva ante pérdida de conexión. Mantendría los trece cambios visuales y los arreglos funcionales cerrados, y corregiría los cinco hallazgos acotados de esta revisión antes de aceptar el prototipo.

Convención de referencias: **E** = `ctx/estudio.html`; **M** = `ctx/pruebas-mejoras.js`; **MU** = `ctx/mutantes.js`; **LI** = `ctx/2026-11-04-ui-mejoras-consolidado.md`; **VI** = `ctx/2026-11-09-ui-revision-visual.md`; **DI** = `ctx/2026-10-28-ui-m1-consolidado.md`. Los números son líneas del paquete recibido, no del repositorio original.

## 2. Pruebas, procedencia y límites

Se leyó primero `medidas/LEEME.txt` y se verificaron los **20 hashes** de `ctx/SHA256SUMS.txt`. Se leyeron el informe AR2, el contrato, las decisiones #4/#7/#9/#10 del plan, las secciones solicitadas de LI/DI, VI, los bloques de sonda/AR2/VIS de M y MU; se compararon completos ambos cambios de HTML. No existe CLAUDE.md en la raíz de este paquete; no se consultó ninguna carpeta exterior.

Chromium arranca dentro del sandbox. Se usó el Playwright local 1.63.0, con `PLAYWRIGHT_BROWSERS_PATH=pw` y TEMP/TMP absolutos dentro de `tmp`, en PowerShell y **sin simultanear corridas de navegador**. No se instalaron dependencias. No hubo acceso al juego, backend real ni mod de F5.

| Corrida | Resultado observado | Evidencia y comparación |
|---|---|---|
| a) M completo contra E | **RESULT 125 pass, 0 fail**, salida 0 | [Log propio](../tmp/r3-a-completa.txt). Coincide con `medidas/mejoras-nuevo.txt`. |
| b) M, SOLO=^AR2, contra b106329 | **RESULT 10 pass, 15 fail**, salida 1 esperada | [Log propio](../tmp/r3-b-ar2-antiguo.txt). Coincide con `medidas/ar2-b106329.txt`: todos los + fallan salvo AR2-02 a 901 px. |
| c) M, SOLO=^VIS, contra f9a7d97 | **RESULT 15 pass, 13 fail**, salida 1 esperada; coincide con medidas/vis-f9a7d97.txt | [Log propio](../tmp/r3-c-vis-antiguo.txt). |
| d) MU, sin ESTUDIO_URL ni SOLO | Control **RESULT 10 pass, 0 fail**; **RESULT 8 mutantes detectados, 0 sin detectar**, salida 0; coincide con medidas/mutantes.txt | [Log propio](../tmp/r3-d-mutantes.txt). |
| `pruebas.js`, aceptación de octubre | **RESULT 64 pass, 0 fail**, salida 0; [log propio](../tmp/r3-pruebas-octubre.txt), coincide con medidas | Resultado aportado inicialmente: **RESULT 64 pass, 0 fail**, en `medidas/pruebas-nuevo.txt`. |
| Capturas propias antes/después | **RESULT 40 capturas propias, 0 errores** | [Script](../tmp/r3-visual.js), [medidas](../tmp/r3-visual.json). Dos prototipos × dos temas × 1366×768/1440×900 × elegido/Añadir/armada/rodando/sin backend. |
| Escenarios propios de reconexión y responsive | **RESULT sondas adversariales terminadas** | [Script](../tmp/r3-adversarial.js), [JSON](../tmp/r3-adversarial.json). Ocho escenarios; este RESULT solo indica terminación, **no PASS funcional**: reproduce AR3-02. |
| Matriz adicional de tecla simulada | **RESULT 9 combinaciones sin conexion, 0 confirmaciones falsas inmediatas; Parando conectada registrado** | [Script](../tmp/r3-tecla-matriz.js), [JSON](../tmp/r3-tecla-matriz.json). Tres estados × tres peers cortados; se inspeccionó también Parando conectada. |
| Mutaciones propias | Seis en el ejecutor, más una variante de rayado | [Resumen](../tmp/r3-mutantes-propios.txt); resultados discriminados en §5.1. No se modificó M para hacerlas pasar. |
| Doctype y Guardar adicionales | **RESULT 21 comparaciones adicionales de doctype y 2 vias de Guardar**, salida 0 | [Script](../tmp/r3-extras.js), [medidas](../tmp/r3-extras.json). |

**Las cifras históricas no son intercambiables.** Los «8 de 23» de LI:282 cuentan los casos AR2; la corrida disponible actual añade dos comprobaciones generales de red y errores JS y acaba en 10/25. Los «15 de 28» de VIS incluyen igualmente sus trece negativos y esas dos comprobaciones. Los 99/99 son la tanda anterior a VIS; 125/125 es la actual. Estas diferencias de denominador no son nuevos fallos del producto.

**Capturas y fuentes Windows.** Las capturas se tomaron con barras nativas visibles, retirando el argumento headless que las oculta. Se verificó por CDP uso real de Segoe UI Variable en título y cabeceras; las geometrías registradas son las de este PC. La consulta posterior de #tlTime devolvió **Consolas**, no Cascadia Mono: no presupongo que el primer nombre de la pila CSS sea la fuente resuelta. Se corrigió un primer ayudante de captura que reconocía «Desarmar» en un botón oculto: la tanda final espera el botón visible y el estado Armada, y sustituye las 40 imágenes anteriores. No se toman fotos de Preparando por fotos de Armada.

Se inspeccionaron imágenes de ambos prototipos, ambos temas y los cinco estados, además de reconexión, Atajos estrechos y mutantes. Entre las comparaciones principales: [antes armada, 1366 oscuro](../tmp/r3-capturas/antes-dark-1366-armada.png), [actual](../tmp/r3-capturas/actual-dark-1366-armada.png), [antes Añadir, 1366 claro](../tmp/r3-capturas/antes-light-1366-anadir.png), [actual](../tmp/r3-capturas/actual-light-1366-anadir.png), [actual rodando, 1440 claro](../tmp/r3-capturas/actual-light-1440-rodando.png), [actual sin backend](../tmp/r3-capturas/actual-light-1440-sinbackend.png).

**Límites.** Datos y lecturas simulados; no se acredita persistencia real, retorno del control en menos de un segundo, sincronía de actores, seguridad del bridge ni eventos de F5. Firefox, Safari, móviles físicos, escala de Windows distinta de la medida y rueda física siguen **[sin verificar]**. No hay versiones históricas completas de LI/DI/VI para reconstruir todos sus cambios línea a línea: se revisa coherencia vigente y correspondencia con el HTML, sin fingir un diff documental inexistente. Las identidades de commit son las declaradas por el paquete; los contenidos sí se anclan por SHA256.

## 3. Hallazgos de la segunda ronda

| AR2 | Estado | Evidencia | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| AR2-01 | **A medias** | E:1496 fija `lineCap='butt'`; el borrador base recupera huecos. M:174 mide el raster final de rellenos y colores de trazos, pero no el texto; sobreviven los nuevos mutantes de §5.1. | **No como aceptación integral.** Los tres mutantes anteriores ya se detectan y el inventario evita el PASS vacío. Otras rutas conservan falsos verdes: AR3-01. |
| AR2-02 | **Arreglado** en los tamaños comprobados | E:547-572 y observador final de `#status`; M:1064-1106. Parar/MCP accesibles arriba y al final a 390/768/900/901, también pendiente de confirmación. Mi sonda añade Guía, Atajos, menú, selección con scroll y 40 pasos Tab por ancho: sin foco tapado ni errores JS. | **Sí**, geometría vertical y hit-test, además de la mutación que devuelve las barras al flujo. El + antiguo falla a 390/768/900; pasa a 901 porque ya era escritorio. No se extrapola a todos los dispositivos. |
| AR2-03 | **Arreglado** | E:2301,2320,2329: guarda central y menú; Abrir conserva consulta. M:1109-1134 mantiene número de documentos, escena e historial ante acción forzada sin backend. | **Sí**, botón y ejecución forzada; ambos casos fallan en b106329. No acredita guardado real, pero cierra la creación local indebida. «Guardar» es otra ruta, AR3-03. |
| AR2-04 | **Arreglado** | E:1750-1752 devuelve Ctrl/Meta antes de cancelar la rueda. M:1137-1160 comprueba rotación simple/Alt, zoom vacío, documento, historial y evento no cancelado. | **Sí** para el contrato del handler; +/− fallan en b106329. No demuestra por sí solo el zoom nativo de todos los navegadores o dispositivos. |
| AR2-05 | **Arreglado** para los destinos pedidos | E:2714 incluye selección lógica y campo; E:2314 mantiene historial por documento. M:1163-1190 reproduce ráfaga única, dos entidades y K1/K2; deshacer B conserva A. | **Sí**, comprueba resultados y nombre de Deshacer, no solo la cadena de fusión; +/− fallan en b106329. El mismo campo sigue agrupando pasos durante 900 ms. |
| AR2-06 | **A medias** | E:1330-1334 corrige la tecla armada y evita la confirmación directa sin peers; M:1194-1222 pasa conectado y corte durante Parando. E:1304-1310 sigue confirmando tras reconexión interrumpida: AR3-02. | **No completa.** El negativo espera una reconexión estable y no vuelve a cortarla durante los 700 ms de la supuesta lectura. Sí mata el fallo directo antiguo. |
| AR2-07 | **A medias en documentos; arreglo del HTML correcto** | E:679 y 2164 corrigen atribución y previa; M:1225-1237 lo verifica. LI:240 reconoce que el negativo concurrente antiguo no era aplicable; DI resuelve C-16 y cuenta 68. LI:69 y 180 conservan reglas viejas; la nota correcta queda truncada: AR3-04/05. | **Sí** para los textos concretos de HTML y las dos acciones de UX-46; **no** para coherencia documental ni legibilidad del final de la nota. No se leen LI/DI desde esos tests. |

### Qué demuestran los negativos que «ya se cumplían»

- Los cuatro negativos sintéticos de AR2-01 **sí prueban la propia sonda**: construyen imágenes, patrones y trazos, y también una vista sin texto. Su PASS sobre b106329 es esperable porque usan la sonda nueva; no significa que el dibujo de b106329 cumpliera.
- AR2-02 − demuestra que la comprobación descubre las barras fuera del viewport. Los otros dos negativos ya pasaban: unas barras sin fijar no tapaban el último panel y el escritorio no tenía scroll de página.
- UX-46 − ahora exige la tecla del simulador y la parada web: se retiró la antigua aceptación de «solo web». UX-47 − conserva correctamente que reaplicar la misma escena no diga que retiró otra.
- Nueva/Abrir antiguos eran stubs: «no mandaban órdenes» era cierto, pero no demostraba navegación entre documentos. Los nuevos positivos y las guardas centrales son los que aportan esa prueba.
- En VIS, los negativos preservan propiedades anteriores: texto y cuentas de Añadir, scroll, subrayado/contraste, acción ámbar activa, teclas y Borrar, barra/Parar, zoom, teclado/rueda y avisos. Su PASS contra f9a7d97 **no prueba que existiera la mejora**.
- VIS-07 − sobre f9a7d97 es la excepción débil declarada en VI:178: compara **BackCompat con BackCompat**. Es una igualdad trivial allí; sobre E sí compara CSS1Compat con BackCompat y tiene valor para sus tres estados.

## 4. Revisión visual VIS-01 a VIS-13

Los trece positivos fallan contra f9a7d97 y pasan en E. Eso acredita sensibilidad frente a la versión anterior, no frente a cualquier implementación incorrecta.

| VIS | Estado | Evidencia en este PC | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| VIS-01 | **Bien** | E:249-279,2203-2226. A 1366/1440: cabecera 46 px y mapa y=90 en lista/armada/rodando/parada/bloqueada; a 1280, 83 px estables. Antes: armada 89 px; rodando 83 px a 1366 y 46 px a 1440 con estas fuentes. Aviso corto cabe; a 1600 aparece entero. | **Sí** para alturas/estabilidad; **incompleta** para presencia: M:1245-1246 permite `!a`, `!c`, `!k`. Quitar un elemento puede satisfacer ese subpredicado. UX-46 y mis capturas aportan la presencia; conviene exigirla por estado. |
| VIS-02 | **Bien** | Cuatro pestañas y cuentas caben en Añadir; 1366/1440/1920. Capturas claras antes/después muestran Animales recuperado. | **Sí**: M:1279-1306 mide contenedor, cada botón y texto, suelo 12 px y selección con subrayado. |
| VIS-03 | **Bien** | E:76-77; las capturas propias con scrollbar visible muestran barras finas integradas en ambos temas. El hover de Jerarquía cambia el tono; sigue desplazándose. Chromium conserva pequeños remates/flechas nativos: no equivale a eliminar toda decoración del sistema. | **Sí** para CSS y scroll en M:1310-1327; **no por sí sola** para apariencia del navegador. Esta última se comprobó aquí mediante capturas. |
| VIS-04 | **Bien** | E:162-171. Cabecera oscura rgb(22,23,27), cuerpo/activa rgb(28,30,35); en claro Añadir 5,28:1. Los paneles se separan sin nuevos radios ni sombras. | **Sí**, M:1331-1354 mide fondos, subrayado, contraste y geometría decorativa; capturas en ambos temas. |
| VIS-05 | **Bien** | E:102: apagado gris como Quitar; activo/aplicando conserva ámbar. Capturas offline claras y oscuras. | **Sí** para fondos/estado activo, M:1357-1375. El + no cubre todos los detalles del borde o texto; el CSS y las capturas no muestran regresión. |
| VIS-06 | **Bien** | E:307,2012,2035: rejilla de órdenes de entidad y grupo. Cinco botones de 145 px, dos columnas, tres filas a 1440. | **Sí** para entidad, M:1378-1396: cuenta, columnas, filas, textos, altura y Borrar rojo. La rama de grupo se verificó en fuente, no mediante un caso equivalente de la suite. |
| VIS-07 | **Bien con límite explícito** | E:1,80,374. File abre CSS1Compat; comparación de M da 876/435/443 cajas sin cambio en tres estados. Ampliación propia en §4.1. | **Sí** para modo y estados probados, M:1400-1440; **no** como afirmación universal «ninguna caja». La Guía es una excepción conocida y la referencia antigua es tautológica. |
| VIS-08 | **Bien** | E:120-136. Documento/segmentos/grupo/botones a 30 px; barra 44 px y una fila a 1366/1440. Parar mantiene posición y hit-test. | **Sí**, M:1443-1477 comprueba geometría y B5, no solo CSS declarado. |
| VIS-09 | **Bien para X** | E:224,234,243: overlays a 24 px del borde. Seis numerales X libres con selección y rodando en los dos anchos. | **Sí** para interferencia de overlays, M:1479-1518. Recoge numerales realmente llamados, por lo que solo este caso no detecta todos los numerales omitidos; AR-03 añade el inventario. La regla Y queda fuera del arreglo declarado. |
| VIS-10 | **Bien** | E:110-121. Teclas ligeras en controles; conservan caja en ayuda/Guía. M registra mínimos 5,62:1 oscuro y 4,71:1 claro, todos ≥12 px. | **Sí**, M:1535-1552 comprueba decoración, contraste y tamaño en ambos temas. No se cambian tokens para conseguirlo. |
| VIS-11 | **Bien** | E:296-297, `.nin input`. Hover no añade flechas en Windows; flecha arriba y rueda incrementan 0,1 y el campo retiene foco/borde. | **Sí**, M:1556-1578 compara píxeles del extremo derecho y comprueba teclado/rueda/historial. No acredita Safari/Firefox. |
| VIS-12 | **Bien** | Lista de Cámaras a 1366/1440: nombre y resumen en una línea; nombre largo elidido, `title` completo y «En la toma» entero. | **Sí** para truncamiento, atributo de ayuda y selección, M:1586-1605. No es una prueba del tooltip nativo en cada plataforma. |
| VIS-13 | **Bien** | Avisos de armada y Espacio desaparecen al rodar; armada siguen apareciendo y los de error offline permanecen. Se marca solo el aviso transitorio correspondiente y se retira tras las guardas de Rodar. | **Sí**, M:1611-1636 comprueba presencia antes, ausencia después y preservación de aviso/error un segundo después. No se aceptaría simplemente vaciar todos los avisos. |

### 4.1. Comprobaciones que faltaban en Windows

**Anchos y fuentes.** La cabecera de una sola franja queda confirmada a 1366 y 1440 en los dos temas. A 1280 se conserva la alternativa de dos filas; a 1600 la frase larga de Parar toma cabe. Son reglas de contenedor (E:272-279), por lo que «unos 1360/1500» presupone los paneles de fábrica: no es un breakpoint absoluto válido para cualquier distribución. La cifra antigua de 59 px rodando a 1440, medida en Linux, aquí es 46 px; es una diferencia de entorno, no una prueba de que no hubiera saltos en otros estados.

**Barras y campos.** En Windows las barras se ven finas y coloreadas, y los campos no muestran flechas al pasar el ratón; siguen operativos el scroll y el incremento por teclado/rueda. Las capturas con `--hide-scrollbars` por defecto habrían sido insuficientes para el primer punto. La diferencia decimal anotada por Claude **no se reprodujo visualmente aquí**: el campo muestra «6196,0» mientras su propiedad HTML `value` usa punto; ese valor interno no demuestra un defecto de presentación. Si se reproduce en Linux, es una inconsistencia cosmética BAJA, no un cambio de cantidad ni un bloqueo de M1.

**Doctype.** Se compararon, con y sin doctype, elegido/Añadir/línea de tiempo/Atajos/menú/Guía/sin backend, a 1366×768 claro, 1440×900 oscuro y 390×844 claro. En las 18 comparaciones fuera de Guía no cambió ninguna caja ≥0,5 px; Guía sí cambia: altura +5,33 px en ambos escritorios y +71,89 px a 390. No se encontró control perdido ni regresión funcional asociada a esos cambios. El primer auxiliar terminó sus comparaciones pero falló al consultar la fuente por CDP porque no había habilitado el agente CSS; se corrigió el auxiliar y se repitió, sin atribuir ese error al producto. La frase «ninguna caja se mueve» debe conservar el alcance de las pantallas medidas y la excepción Guía, como ya matiza el informe largo.

**Responsive y foco.** A 390/768/900/901 se abrió Atajos, se desplazó Guía, se eligió un objeto con la página bajada y se abrió Herramientas; luego se recorrieron 40 destinos Tab por ancho. Las cajas comprobadas permanecen accesibles y ningún foco de esa muestra queda tras las barras; el mapa puede salir de la vista al navegar por los paneles apilados, consecuencia del layout declarado, sin perder Parar/MCP. La suite además verifica los estados rodando/parando/sin confirmar con scroll. No se encontró una regresión nueva de AR2-02.

### 4.2. Juicio visual y referentes

El cambio es material: Añadir deja de ocultar una categoría, el transporte deja de saltar al armar, las cabeceras ordenan la lectura y los controles secundarios pierden peso. El editor tiene una composición coherente y profesional en los dos temas; **no hace falta otra reforma estética** para aceptar estos cambios. Los problemas pendientes son los de §5, no una preferencia por otra fuente, radio, sombra, ámbar o nombre.

El patrón de barra de herramientas, viewport, jerarquía, propiedades y estado inferior está documentado en [Unreal Editor Interface, UE5](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface). El transporte asociado a una línea de tiempo y a su vista previa está documentado en [Sequencer Cinematic Editor](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine). Son referentes pertinentes para la composición; no justifican por sí solos copiar 46 px, los tokens de color ni todos los gestos de esta web. La referencia a [SSpinBox](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Slate/SSpinBox) apoya control numérico por interacción, no prueba que ocultar flechas HTML sea una copia literal.

Se intentó consultar también [Blender 4.2: Regions](https://docs.blender.org/manual/en/4.2/interface/window_system/regions.html), su [UILayout](https://docs.blender.org/api/4.2/bpy.types.UILayout.html) y [Reforger: World Editor](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor); la recuperación directa devolvió errores 402/403 o de caché. Su fidelidad visual exacta queda **[sin verificar]** en esta sesión, aunque se leyó la atribución del paquete. No se buscó información pública de DayZ Sandbox. Tampoco se convierte una semejanza con editores conocidos en una prueba de facilidad de uso con jugadores; UX-17 sigue pendiente.

## 5. Hallazgos nuevos

BLOQUEA se usa por ruptura del contrato o aceptación falsa demostrada, no por preferencia estética. No se imputa a la revisión visual el origen de fallos heredados.

| ID | Gravedad | Mejora/regla | Dónde | Qué pasa | Evidencia | Arreglo propuesto, concreto | Criterio verificable + / − |
|---|---|---|---|---|---|---|---|
| **AR3-01** | **BLOQUEA** | AR2-01, AR-03/04, UX-30, CU-38, R26 | M:65-95,97-105,174-199,251-253,757-795 | Sigue aceptando texto que no queda legible en el fotograma final y un patrón a cuadros como «rayado». La afirmación global «mide el fotograma acabado» es falsa para los glifos. | Tres mutantes de texto: **4 pass, 0 fail** cada uno; patrón a cuadros de 2 px: **4 pass, 0 fail**. Logs/capturas y mecanismo en §5.1. | Evaluar los glifos después de toda composición, con su máscara real y fondo pertinente; propagar o rechazar explícitamente las rutas raster que no se miden, incluido putImageData; no declarar halo por coincidencia textual sin verificar la letra final. Para STRIPES, comprobar estructura direccional de franjas, además de ocupación/contraste. Documentar qué cubren los umbrales. | **+** Original, textos esperados y extras legibles por cada ruta soportada, halos con letra final y rayado real pasan en ambos temas. **−** Repintado pálido posterior, transferencia raster sin etiqueta, halo sin letra y patrón a cuadros fallan por su propiedad; no por falta de arranque, excepción o eliminación de textos del inventario. |
| **AR3-02** | **BLOQUEA** | AR2-06, D2, B5, CU-24/25/37 | E:1304-1310,1069-1071; `#dock`, `#bTopStop`, `#status` | Una reconexión de 100 ms programa una «lectura» que sigue confirmando después de perder otra vez el peer. Desaparece la recuperación de parada sin confirmar. | Reproducción por botones con director/backend/servidor. Director y servidor muestran Observado y «Leída hace 0 s» mientras están sin latido; backend conserva su snapshot, pero oculta la recuperación y muestra el toast de confirmación. [Captura director](../tmp/r3-capturas/reconexion-director.png), [JSON](../tmp/r3-adversarial.json). | Invalidar la lectura diferida al cambiar conexión/sesión y comprobar de nuevo los peers al completarla; solo reconciliar la operación y toma correspondientes mediante una lectura vigente. Mantener el pendiente si se interrumpe. | **+** Reconexión estable produce una confirmación con origen/edad de esa lectura, sin duplicar toma. **−** Reconectar y cortar a 100 ms cualquiera de los tres peers no genera Observado/edad nueva ni quita recuperación; al volver de forma estable se confirma una sola vez. |
| **AR3-03** | **MEDIA** | CU-37, #7, UX-14, límite LI §9 | E:944,2335,2642; Guardar y Ctrl+S | Sin backend se anuncia en verde «Guardado. El estudio guarda cada cambio al momento.», aunque la propia web dice que ahora no puede guardar. No se ha probado pérdida de datos: es confirmación engañosa de una acción sin efecto. | Dos rutas reproducidas en el auxiliar; [captura](../tmp/r3-capturas/guardar-sin-backend.png). El handler solo llama a toast y no renueva savedAt. | Hacer que ambas rutas expliquen que se conserva el último guardado y no hay conexión para guardar ahora, o desactivar Guardar con ese motivo. Mantener el documento. No implementar persistencia fuera de esta revisión. | **+** Con conexión, el mensaje concuerda con el guardado simulado. **−** Cortar backend y usar menú/Ctrl+S no muestra nuevo éxito ni cambia documento/edad; explica el bloqueo. |
| **AR3-04** | **MEDIA** | AR2-07, UX-11/30/47, R20/R26 | LI:69,180,241,271-275,308,322; DI:9 | Siguen coexistiendo «Previsualizar mueve solo la cámara» y cámara+actores estimados, y «mientras Guillermo no elija» junto a su elección ya incorporada. El resumen de sonda/doctype excede lo demostrado. DI abre aún con la segunda revisión futura. | Lectura literal de las filas y contraste con E:2164, LI §8/9/10 y esta revisión. | Sustituir las reglas obsoletas en sus filas; marcar antecedentes como históricos. Limitar «fotograma acabado» a lo realmente medido hasta arreglar AR3-01; precisar doctype y excepción Guía; actualizar Estado de DI sin declarar cerrados los bloqueos. | **+** Cada tema tiene una regla vigente única, coincidente con conducta y decisión; las cifras identifican tanda y denominador. **−** Un barrido encuentra cualquier instrucción vigente «solo cámara», elección pendiente o garantía universal que contradiga pruebas y hace fallar la revisión documental. |
| **AR3-05** | **BAJA** | AR2-07, UX-30, límite LI §9 | E:370,2164; `.tlnote` | El texto corregido se corta y el final «no mueve el juego» no puede recuperarse en esa nota mediante ratón ni foco. | Capturas 1366/1440; ancho de contenido mayor que caja, sin title ni destino de foco en el auxiliar. El rótulo de vista previa y la leyenda aportan contexto: no lo elevo a ruptura de D2. | Conservar la franja y la tipografía: ofrecer el texto completo al hover/foco o una redacción breve que incluya explícitamente la separación del juego, sin añadir otra fila obligatoria. | **+** A 1280/1366/1440 se puede conocer la frase completa y que el juego no se mueve. **−** Dejar solo ellipsis sin acceso al final falla, aunque textContent contenga toda la frase. |

### 5.1. AR3-01: mutaciones, mecanismo y alcance de la sonda

Las copias están en `tmp/r3-mut-*.html`; el generador es [r3-make-mutants.py](../tmp/r3-make-mutants.py) y el ejecutor secuencial es [r3-run-mutants.js](../tmp/r3-run-mutants.js). Se alteró el dibujo, **no los nombres de los casos, el inventario ni las aserciones**. Los dos PASS generales de cada corrida son red y errores JS; los otros son las propiedades atacadas.

| Mutante propio | Cambio y criterio ejercitado | RESULT | Lectura correcta |
|---|---|---|---|
| `texto-final` | Después del fillText de numerales, putImageData rebaja su tinta a #888. SOLO de AR-03 + en ambos temas, cuatro vistas cada uno. | **4 pass, 0 fail** | **Sobrevive incorrectamente.** Sobre las placas de E:1393-1394, tinta #888 da 2,05:1 oscuro / 3,16:1 claro; el registro de sonda aún informa 9,34/10,85 y cero píxeles bajos. [Log](../tmp/r3-mut-texto-final.txt), [captura oscura](../tmp/r3-capturas/mut-texto-final-dark.png). |
| `imagen-sin-tag` | Texto pálido en un canvas, transferencia getImageData/putImageData a otro y drawImage al mapa, sin fillText posterior. Se conservan los textos esperados originales. | **4 pass, 0 fail** | **Sobrevive incorrectamente.** El segundo canvas pierde la etiqueta de procedencia; el texto adicional queda fuera del inventario y de la medida. [Log](../tmp/r3-mut-imagen-sin-tag.txt), [captura](../tmp/r3-capturas/mut-imagen-sin-tag-light.png). |
| `halo-sin-letra` | Se conserva halo y fillText nominal, pero la letra final usa filter opacity(0). | **4 pass, 0 fail** | **Sobrevive incorrectamente.** Se ven halos sin nombres; el detector construye su máscara con filter=none. Es una variante más fuerte que una letra pálida cubierta por halo. [Log](../tmp/r3-mut-halo-sin-letra.txt), [captura](../tmp/r3-capturas/mut-halo-sin-letra-dark.png). |
| `ajedrez` | Patrón alterno de píxeles de 1 px, probado por UX-30+ y AR2-01+ claro. | **2 pass, 2 fail** | **Detectado**: al rasterizar, se suaviza; separación de tonos 1,53/1,39:1. No lo cuento como superviviente. |
| `ajedrez2` | Misma sustitución, cuadros de 2 px; casos anteriores sin alterar. | **4 pass, 0 fail** | **Sobrevive como «rayado» sin franjas.** Oscuro: 15/85 %, 7,54:1 y 2,2 cambios medios por fila; claro: 24/76 %, 9,32:1 y 3,3. El checker satisface los umbrales sin tener la estructura declarada. [Log](../tmp/r3-mut-ajedrez2.txt), [captura](../tmp/r3-capturas/mut-ajedrez2-dark.png). |
| `huecos-rellenos` | Primero contorno gris continuo; encima guiones normales. UX-09− y AR2-01+ claro. | **4 pass, 0 fail** | Limitación de la medida de huecos, **no otro bloqueo demostrado de apariencia**: cuenta la topología del trazo sintético y contrasta colores finales. Los intervalos grises aún pueden percibirse como huecos frente al trazo oscuro; no equiparo supervivencia con ilegibilidad probada. |
| `solido-perimetro` | Interior sólido con borde borrado y remate discontinuo. Casos anteriores. | **2 pass, 2 fail** | **Detectado por el conjunto**: SOLID aislado sigue dando 100 %, pero el chequeo adicional encuentra un contorno discontinuo. No se afirma que sobreviviera. |

El ejecutor inicial incluye seis variantes; `ajedrez2` se ejecutó después al refinar el ataque de 1 px fallido. [Capturas y métricas de las variantes](../tmp/r3-mutant-captures.json) registran otra vista/encuadre: sus porcentajes pueden variar y no sustituyen el RESULT de la corrida de aceptación.

**Mecanismo del texto, leído en fuente.** M:76 toma el fondo antes de pintar; M:77 fuerza composición normal y elimina filtro/sombra para construir una máscara; M:81-88 calcula contraste usando la tinta declarada. El fillText real se ejecuta después (M:94-95). `finish()` lee el raster final, pero solo actualiza rellenos y trazos (M:174-199), **nunca esos registros de texto**. La etiqueta WeakMap de M:58/94/98 se propaga por drawImage, no por putImageData. M:777 permite un canvas sin etiquetas como si no llevara texto; por eso la transferencia evita el rechazo. No es una hipótesis: cada ruta produjo el PASS descrito y su captura.

**Inventario independiente.** M:757-774 obtiene encuadre/escala de la página y calcula los numerales, usa las coordenadas de pueblos de la fixture y añade nombres esperados por vista. **No se deriva de `__cv.texts`**, así que sí mejora el oráculo y descubre texto esperado ausente. No descubre por sí solo texto extra pintado por otra ruta, ni prueba que una llamada registrada siga visible al acabar. Tampoco convierte el fixture de pueblos en un inventario general de escenas arbitrarias.

**Umbrales.** Son heurísticas de aceptación, no umbrales perceptivos acreditados por el paquete:
- STRIPES exige dos grupos ≥15 %, contraste medio ≥3:1 y alternancia **media** >1; M:190-191 promedia filas de seis píxeles o más. LI:275 dice «alternando en cada fila», que no es lo que se ejecuta. El checker de 2 px demuestra que ocupación y alternancia no distinguen franjas de otros patrones.
- GAPS suma muestras de píxel clasificadas como hueco y exige seis; **no mide un hueco mínimo de seis píxeles lineales**, ni tres componentes del contorno final. Los componentes vienen del trazo aislado en el instante de la llamada (M:122-148); al final solo se contrasta la mediana de colores (M:194-197). Sí detecta los extremos redondos que cerraban los huecos y el guion demasiado largo.
- SOLID mide el interior tras excluir unos 2 px CSS del borde, con tolerancia 24 por canal y ocupación 85 %. Es útil para relleno; no certifica por sí solo todo el marcador o el perímetro. El ataque al perímetro fue rechazado por la otra condición, que debe conservarse.
- 3:1 aporta separación razonable entre tonos; no hay calibración mostrada que convierta 15 %, seis muestras, 1,5:1 y 85 % en garantías visuales. Hace falta declarar propósito y límites, validar positivos/negativos perceptualmente distintos y conservar inspección raster independiente. No propongo inventar otros números para que pasen estas mismas fixtures.

**Los tres mutantes de AR2.** El contorno de guion enorme falla por ausencia de componentes/huecos; el patrón blanco, por tono único/1:1; los numerales raster pálidos, por inventario incompleto y ruta con texto sin medir. Este último es un rechazo deliberado por falta de cobertura, admisible en el criterio AR2, **no una prueba de que se haya medido su contraste final**. Los fallos reportados son de los casos correspondientes, no errores JS del prototipo. Los ocho detectados no cubren las rutas nuevas de esta sección.

### 5.2. AR3-02: secuencia exacta y distinción entre peers

Reproducción con [r3-adversarial.js](../tmp/r3-adversarial.js), sin escribir el estado interno:
1. Aplicar, preparar hasta Armada visible y Rodar.
2. Cortar Tu juego desde el matraz y esperar «Parada sin confirmar»; abrir Actividad.
3. Restablecer Tu juego, esperar 100 ms y cortarlo otra vez; esperar 850 ms.
4. La fila nueva se vuelve **Observado**, origen **«servidor y tu juego · lectura al volver»**, edad **«Leída hace 0 s»**; Tu juego está **sin latido**, desaparece el control de recuperación y se ofrece Reaplicar.

Se repitió sustituyendo Tu juego por Servidor y por Backend. Con servidor sucede la misma contradicción visible; con backend, Actividad mantiene el snapshot congelado Parcial, **pero el toast confirma y se oculta Parada sin confirmar**. No atribuyo a la captura offline del backend una fila Observado que no enseña.

La guarda E:1305 se evalúa antes de programar 700 ms; dentro solo se mira `o.lost` (1307). `setOp` asigna `readAt=now()` al recibir observado (1071) y la rutina borra `unconfirmed` (1309). Esa es la cadena causal del resultado falso. El fallo ya estaba en reconcileTakes; no lo introduce VIS ni se culpa al guard nuevo de gameStop. Entra en esta revisión porque AR2-06 exige que **ninguna vía** fabrique evidencia al volver la conexión.

La matriz adicional ejecuta **Armada/Rodando/Parando × Backend/Servidor/Tu juego cortado** y registra el estado inmediatamente antes de pulsar la tecla. Las nueve pulsaciones respetan la guarda: ninguna aporta Observado ni edad de lectura nueva durante el corte. Después de recuperar conexión estable, Armada sigue Armada, Rodando acaba como toma fallida reconciliada y Parando puede confirmar su parada; el JSON conserva las filas y sus orígenes. Una décima secuencia pulsa la tecla conectada durante Parando y confirma una única Toma 04 con origen del juego. Esta matriz confirma el arreglo directo, sin contradecir la carrera de reconexión interrumpida que se reproduce aparte.

La tecla armada conectada sí desarma sin sumar toma; rodando conectada sí registra origen del juego; las vías simultáneas deduplican en los casos de la suite. Armada con Tu juego cortado, la pulsación no confirma ni inventa toma; al recuperar conexión permanece Armada en la simulación probada. No exijo entregar retrospectivamente una pulsación que la web declara no recibida, ni diseño el mod de F5. La aceptación pendiente es la lectura de reconciliación, no retirar esa tecla.

### 5.3. Contrato conservado y límites de la aceptación

| Contrato | Conclusión de esta ronda | Evidencia |
|---|---|---|
| D2: seis estados, edad y origen | Se conservan Pendiente/Ejecutando/Aplicado/Observado/Fallido/Parcial y la separación petición/lectura. **No cumple íntegramente** por la lectura falsa AR3-02. | E:794,1066-1075,1304-1310; filas de Actividad. Product-spec:87. |
| B5 y CU-25: Parar visible y sin diálogo | Arreglado el defecto de scroll; acceso comprobado con menú/avisos y en escritorio/estrecho. **AR3-02 elimina prematuramente la recuperación**. No se propone ocultar Parar ni añadir confirmación. | E:1313-1325,1887,2811; M AR2-02/VIS-08; sonda propia. Control real del jugador <1 s: [sin verificar]. |
| #4: una preparación antes de Rodar | La web conserva preparar→armada→rodar y no añade otra validación manual. El simulador permite la tecla armada conforme a AR2-06. | E:1234-1272; plan:26. GO/RPC y sincronía reales: [sin verificar]. |
| #7: documento como fuente | Se conservan documento/mundo separados, Deshacer documental e identidad del destino de rueda. Nueva sin backend queda cerrada. **Guardar comunica mal su bloqueo**, AR3-03. | E:987-1011,2301-2325,2714; plan:29. Backend/persistencia atómica no implementados ni certificados aquí. |
| #9: aplicar = reset y crear | Se mantienen las etapas y el aviso al sustituir otra escena; UX-47 +/− pasan. No se convierte en aplicación incremental. | E:1104-1144; plan:31; LI:241. Censo/borrado real: [sin verificar]. |
| #10: ids lógicos | Los cambios revisados no sustituyen ids por nombres ni handles; selección/entidades/cámaras y la fusión de rueda siguen identificadas. El simulador conserva aviso de mundo nuevo. | E:1014-1023,2304-2324,2714; plan:32. Ownership y registro real del mod: [sin verificar]. |
| CU-35 | MCP apagado sigue visible y ninguna de las suites hace peticiones externas. No se añade integración MCP. | M:1639, AR2-02, UX-33; DI:186. |
| CU-37 | Guardas de creación/edición correctas; snapshot offline y aviso conservados. **Mensaje Guardado y recuperación falsa** pendientes. | E:988,2301,944,1304; DI:188; AR3-02/03. |
| CU-38 y suelo tipográfico | No se encontró en el original una nueva letra de mapa por debajo de contraste, ni regresión del suelo de 12 px en los casos medidos. **La prueba no garantiza todo texto final**, AR3-01. No se presenta el verde como certificación universal. | M AR-03, UX-10, VIS-10; DI:189; capturas y mutaciones. |

El requisito de id lógico y el criterio de lectura no autorizan a simular un resultado nuevo por el mero transcurso de 700 ms; la corrección propuesta para AR3-02 conserva el contrato. Ningún hallazgo solicita 3D, vídeo, multiusuario, cambio de mapa, eventos, MCP ni IA propia.

### 5.4. Trazabilidad de los cambios: R20 y R25

Comparaciones conservadas: [b106329→f9a7d97](../tmp/r3-diff-ar2.txt), [f9a7d97→actual](../tmp/r3-diff-vis.txt), [pruebas de mejoras](../tmp/r3-diff-pruebas-mejoras.txt), [mutadores](../tmp/r3-diff-mutantes.txt). Se revisaron todos los hunks HTML, incluidas sus eliminaciones; la tabla agrupa líneas con una misma finalidad, no deja una categoría de «limpieza» sin justificar.

| Cambio b106329→f9a7d97 | Trazabilidad |
|---|---|
| Sticky superior/inferior bajo 900; avisos sobre status; ResizeObserver para alto variable | AR2-02, B5/CU-25/CU-35. |
| Texto de procedencia en Guía y comentario/texto de la previa | AR2-07. |
| Función gameStop; disponibilidad armada del botón simulado; encaminamiento del evento | AR2-06. |
| Extremos planos del contorno draft y comentario explicativo | AR2-01; corrige el defecto revelado por la nueva medida. |
| Retorno temprano Ctrl/Meta en wheel del mapa | AR2-04. |
| newBlock central, acción Nueva, disabled y motivo en menú | AR2-03. Abrir no se convierte en escritura. |
| Clave de fusión con selección, comentario de rueda | AR2-05. |

| Cambio f9a7d97→actual | Trazabilidad |
|---|---|
| Doctype; svg.sm como bloque; primera celda de qrow como flex | VIS-07: ajustes necesarios a métricas de línea. |
| CSS scrollbar-width/color y hover | VIS-03. |
| Estilo principal disabled:not(.busy) | VIS-05. |
| Estilo de kbd en botones/menús/segmento y excepciones ámbar/Parar | VIS-10. |
| Alturas/padding/gap de segmento, documento y grupo prototipo | VIS-08. |
| Min-width del contenedor de cabecera; container queries, tmeta/tact/tfix; renderSlate, texto corto/largo y ayuda | VIS-01. La franja y el aviso conservan su función. |
| Fondo de cabeceras y pestaña activa | VIS-04. |
| Top de zoom/ayuda/insignia de rodaje | VIS-09. |
| Inputs numéricos sin spin nativo | VIS-11. |
| Rejilla de órdenes y clase acts en entidad/grupo | VIS-06. |
| Reparto de categorías de Añadir | VIS-02. |
| Rejilla y elipsis de Cámaras, title de nombre/resumen | VIS-12. |
| toast devuelve el nodo; se etiquetan los dos avisos de armada y se retira ese aviso al Rodar | VIS-13. Es el único cambio de conducta de esta tanda y está expresamente encargado. |

**No encontré líneas HTML ajenas a AR2/VIS en esos dos diffs.** Las 157 declaraciones/asignaciones de propiedades CSS personalizadas extraídas de f9a7d97 y E son idénticas, en valor y orden; es cierta la afirmación de que VIS no cambia tokens. El bloque de dibujo del mapa desde las fuentes hasta antes de la interacción se conserva en VIS; mover overlays HTML no modifica su paleta ni su raster. Los cambios de altura de envoltorios no alteran las filas pactadas de 30 px ni los tamaños de letra; los botones pequeños de 26 px ya existían.

M añade la sonda y los casos pertinentes, y MU añade los tres mutantes AR2; no son funciones nuevas de producto. Sus límites de prueba están descritos arriba. **R20/R25 de documentos, línea por línea histórico: [sin verificar]**, porque el paquete no incluye las versiones anteriores completas; las reglas vigentes leídas sí tienen las contradicciones de AR3-04. Tampoco se certifica un despliegue publicado por abrir un HTML local.

### 5.5. Documentos y límites anotados por Claude

LI §9 refleja correctamente las siete intenciones y explica por qué los negativos sintéticos pasan en la base; falla al extender a todo texto la garantía de fotograma final. LI §10 y VI describen cambios visuales que se ven y cuyos positivos discriminan la base; la excepción de Guía debe acompañar al resumen de VIS-07. Las observaciones «sin verificar en Windows» de scrollbar, spin y anchos quedan ahora cubiertas en el Chromium y fuentes resueltas de este PC, con los límites expuestos.

El contador 68 de DI está corregido y C-16 deja de ser una decisión abierta; LI §8 incorpora las tres elecciones de Guillermo. Persisten las filas viejas y el Estado inicial indicados en AR3-04: no basta con añadir una sección final correcta si las anteriores siguen dando otra instrucción. No se reclama reabrir UX-20 a 24 ni UX-34 a 43, ni ninguna decisión tipográfica o de color.

De los límites anotados: **nota cortada = BAJA** (AR3-05); **Guardado sin backend = MEDIA** (AR3-03); **punto frente a coma = no reproducido aquí**, y como máximo BAJA cosmética si se acredita en otra plataforma. La posible cobertura de números Y y los solapamientos de etiquetas densas se conservan como límites existentes; no se disfrazan de regresiones nuevas de VIS-09.

## 6. DISENSO-FUERTE

### Mantengo el desacuerdo con cerrar por el verde; cambio sus razones

> Guillermo: la revisión visual sí ha dejado el prototipo más moderno, ordenado y profesional, y conservaría sus trece cambios. He reproducido los 125 aprobados, los fallos esperados contra ambas versiones antiguas y los ocho mutantes detectados; aun así, tres maneras de dejar texto ilegible pasan y un patrón a cuadros se acepta como rayado. También he logrado que una reconexión de 100 ms confirme la parada y anuncie una lectura recién hecha después de perder otra vez la conexión. No cerraría M1 web con estos dos bloqueos: hay que corregir esas rutas y sus pruebas, no volver a diseñar la interfaz.

### Retiro las objeciones anteriores que ya tienen arreglo

> Retiro como pendientes la pérdida de Parar al desplazar la ventana estrecha, Nueva sin backend, Ctrl/Cmd con rueda y el Deshacer conjunto de dos destinos: los arreglos y sus contrapruebas funcionan en las condiciones medidas. También retiro la contradicción de procedencia dentro de la Guía: ahora reconoce las adaptaciones propias. No reabro los 13 px, los nombres, el ámbar ni MCP en la barra; la frase de previa ya es correcta en el HTML, aunque queda hacer accesible su final y retirar las reglas viejas de los documentos.

No añado disenso estético contra decisiones cerradas. La facilidad de uso con personas sigue sin estar demostrada por una batería automática.

## 7. Para más adelante

- UX-16: resolver solapamientos de etiquetas en escenas densas, sin ocultar incertidumbre.
- UX-17: comprobar el recorrido cámara→preparar→rodar con jugadores de DayZ/Arma.
- Repetir los gestos con rueda física, escalado de Windows y navegadores adicionales.

Integridad al cierre: se repitieron los hashes de ctx y siguen coincidiendo los 20/20; el informe es UTF-8 sin BOM.

Cierre: solo se escribió este informe en out; scripts, logs, copias mutantes y capturas quedan en tmp. No se implementó ningún arreglo ni se hizo commit, conforme al encargo de revisión. El inventario de auxiliares con tamaños, líneas cuando procede y SHA256 queda en [r3-manifiesto.json](../tmp/r3-manifiesto.json).
