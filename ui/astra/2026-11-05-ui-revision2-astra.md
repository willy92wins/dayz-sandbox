# Segunda revisión cruzada adversarial — Astra — 2026-11-05

## 1. Veredicto

**NO APTO para cerrar esta ronda:** los arreglos originales son sustanciales, pero quedan falsos aprobados de representación y fallos reproducidos de parada, edición sin backend y rueda. **Sí parece más moderna y tiene una composición profesional**, con acciones y paneles reconocibles; todavía no es consistentemente intuitiva ni fiable en los recorridos señalados aquí. Se conservan el diseño y las decisiones de Guillermo: hacen falta correcciones acotadas y pruebas sensibles, no otra remodelación.

Revisión individual, sin subagentes y sin cambiar código de producto. Identidad: los 14 archivos coinciden con `ctx/SHA256SUMS.txt`; `estudio.html`, presentado como b106329, tiene SHA256 `e2139cae4e0cbae70e495b0bc8f993aaec982066e0699e789ee0b84e575b7892`. La asociación con commits procede del paquete; no se ha consultado el repositorio original. No hay `CLAUDE.md` ni `AGENTS.md` en la raíz suministrada y no se ha leído fuera de ella. El conflicto de interés declarado no se sustituye por confianza en los documentos ni por el número de aprobados.

Convenciones: **E** = `ctx/estudio.html`; **M** = `ctx/pruebas-mejoras.js`; **P** = `ctx/pruebas.js`; **MU** = `ctx/mutantes.js`; **LI** = `ctx/2026-11-04-ui-mejoras-consolidado.md`; **DI** = `ctx/2026-10-28-ui-m1-consolidado.md`. Las líneas son de los originales intactos. Todos los arreglos propuestos son **[DESIGN]**, sin implementación. Interpretación: «a la vista a cualquier ancho» y «Parar siempre a la vista» se refieren al viewport, no a que un nodo exista más abajo en el documento. La tecla del juego se revisa exclusivamente como interacción simulada y presentación web.

## 2. Pruebas y alcance de los resultados

Chromium arranca dentro del sandbox. Playwright instalado: **1.63.0**, comprobado en `node_modules/playwright/package.json`; no se instaló nada. Todas las ejecuciones usaron PowerShell desde la raíz, `PLAYWRIGHT_BROWSERS_PATH` apuntando a `pw` y `TEMP`/`TMP` a `tmp`, con `ESTUDIO_URL` explícita salvo MU. No se escribieron capturas ni salidas en `medidas`.

| Ejecución propia | Resultado literal | Comparación con medidas |
|---|---|---|
| M completo, E actual | `RESULT 76 pass, 0 fail` | Coincide con `medidas/mejoras-nuevo.txt:77` |
| P completo, E actual | `RESULT 64 pass, 0 fail` | Coincide con `medidas/pruebas-nuevo.txt:67` |
| M, `estudio-9d1a644.html`, `SOLO=AR-03` | `RESULT 3 pass, 2 fail` | Coincide con `medidas/mejoras-9d1a644-AR03.txt:6`; ambos positivos fallan |
| MU, sin ESTUDIO_URL | Control `RESULT 9 pass, 0 fail`; `RESULT 5 mutantes detectados, 0 sin detectar` | Coincide con `medidas/mutantes.txt:1-7` |
| Sondas propias sobre E: rueda, backend, tecla armada, historial, viewport y contraste adicional | `RESULT 4 pass, 5 fail` | Fallan cinco invariantes concretas; no son cinco excepciones ni equivalen automáticamente a cinco hallazgos |
| Sondas extra: Parar a 390 px, Ctrl sobre campo, bloqueo de entidad y captura | Primera ejecución `RESULT 3 pass, 2 fail` | Un fallo real de Parar y un timeout del selector de la captura por codificación de «Señalar» en mi script |
| Captura tras corregir ese selector de mi script | `RESULT 3 pass, 0 fail` | No se atribuye el timeout anterior al prototipo |
| Sonda de corte durante Parando + tecla del juego | `RESULT 2 pass, 1 fail` | Falso Observado reproducido, AR2-06 |
| Contraste extra, DPR 1,25, claro y oscuro | `RESULT 4 pass, 0 fail` | Objeto centrado, estimación a 3 s y Linda seleccionada, a 1280 × 800 |
| Mutante propio: numerales como imagen de poco contraste; M, `SOLO=^AR-03 \+` | `RESULT 4 pass, 0 fail` | Sobrevive en los dos temas |
| Mutante propio: patrón uniforme blanco; M, `SOLO=^UX-30` | `RESULT 4 pass, 0 fail` | Sobrevive: + y − verdes sin rayas |
| Mutante propio: guion mayor que el perímetro del borrador; M, `SOLO=^UX-09 −$` | `RESULT 3 pass, 0 fail` | Sobrevive con contorno visualmente continuo |
| Capturas diagnósticas de los tres mutantes, tres ejecuciones | Cada una `RESULT 3 pass, 0 fail` | Son capturas/diagnósticos, no aprobación de su apariencia; textura blanca: un único RGBA `255,255,255,255` |

Las dos variantes exploratorias previas del patrón (blanco translúcido y color del actor) también dieron `RESULT 4 pass, 0 fail`; la evidencia decisiva es la versión final opaca blanca sin trazo, que elimina cualquier ambigüedad de rayas tenues. Otra ejecución fallida de la captura dio `RESULT 2 pass, 1 fail` por el mismo selector mal codificado, antes de corregirlo.

Se leyeron y recontaron, sin repetir completos, los registros de los anteriores: **76caccb = `RESULT 70 pass, 6 fail`**, **7e2e5c6 = `RESULT 58 pass, 18 fail`**, **10274b7 = `RESULT 52 pass, 24 fail`**. Sus números de líneas PASS/FAIL coinciden con cada RESULT; las diferencias de funciones se contrastaron con los HTML y con los predicados. La repetición dirigida de los cinco UX nuevos contra 76caccb se consigna al final de este informe.

Sensibilidad documentada: contra 76caccb fallan los cinco positivos nuevos y UX-30 −; contra 7e2e5c6 fallan AR-01/02/03/05/06/07 + y la estabilidad de la barra; contra 10274b7 fallan además los seis positivos de la segunda pasada. AR-04 no tiene un positivo funcional independiente que deba fallar en 7e2e5c6: ese dibujo ya era correcto; su aceptación depende de que las mutaciones lo discriminen. AR-08 es revisión documental, no un caso ejecutable oculto dentro de 76.

**Capturas vistas:** las once de `medidas/capturas`, de `01-escena.png` a `11-guia.png`; propias `tmp/A2-antes-gesto.png`, `A2-estimado.png`, `A2-parada-movil.png` y las tres `A2-mut-*.png`. Se compararon mapa, jerarquía, ayudas, Parar, corte, backend apagado, Tomas, Atajos y Guía; no se deduce seguridad funcional de una captura estática.

## 3. Hallazgos de la primera ronda

| Hallazgo | Estado | Evidencia actual | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| AR-01 | **Arreglado** en su reproducción original | E:943-947,1069,1111,1197,1840,2170,2465,2614,2621 extiende la protección a parada sin confirmar. M:560-594 reproduce Guía, ruta, Atajos, órdenes bloqueadas y reconexión. | **Sí**, para esa recuperación y el menú probado: comprueba exposición con `elementFromPoint`, no solo existencia. No certifica el viewport estrecho ni el nuevo camino de tecla; AR2-02/06. |
| AR-02 | **Arreglado** | E:1015-1021,1035-1037,1812,1864-1866,1924-1941 distingue sin lectura de vacío. M:595-616 y la ejecución muestran incertidumbre durante creación/corte y resolución sin otro Aplicar. | **Sí**, para el corte y reset de los criterios originales: comprueba los tres resúmenes y ausencia de Observado indebido. No se usa esta prueba para certificar todos los protocolos del producto. |
| AR-03 | **A medias**: defecto original arreglado, aceptación incompleta | E:1345-1346,1422,1463-1472: placas y halo nuevo. M:618-633 pasa actual y falla 9d1a644 en ambos temas. También pasan las vistas extra y DPR 1,25. | **No como garantía de todo texto visible**: la máscara real mejora la medida, pero las rutas de imagen quedan fuera, AR2-01. Sí detecta las letras de poco contraste por fillText/strokeText y el halo antiguo. |
| AR-04 | **A medias** | Se retiraron los contadores y M:37-73,261-308 usa órdenes de dibujo; los cinco mutantes de MU fallan con control sano. Tres mutantes propios sobreviven. | **No**: `dash` no vacío no acredita huecos visibles; `CanvasPattern` no acredita rayas; las imágenes no se inspeccionan. AR2-01 contiene pruebas concretas. |
| AR-05 | **Arreglado** | E:419 fija `.take small` a 12 px. M:294-308 recorre Tomas y M:581-583 verifica la toma fallida; ambos pasan. | **Sí**, respecto a los textos pequeños denunciados. El negativo también visita las tomas iniciales normales/paradas. El mutante general a 8 px detecta canvas; no se afirma que ese mutante sea una prueba específica de `.take small`. |
| AR-06 | **Arreglado** | E:996-1001,2127,2575-2580: campo asociado y foco; X y tiempo de K2 quedan visibles y enfocados conservando código/puntero y documento. | **Sí**, M:637-659 reproduce el error desde Añadir y el de cámara desde Escena. El viejo falla semánticamente, no por buscar un atributo nuevo. |
| AR-07 | **Arreglado** para la orden fallida original | E:2085-2089 cuenta fallidas/parciales pendientes; M:661-671 muestra 1 problema y después Sin problemas. | **Sí**, para fallo, nueva aplicación observada y fallos históricos. La resolución general por cualquier scene_apply/scene_reset no se ha certificado exhaustivamente entre todas las operaciones. |
| AR-08 | **A medias** | DI:45-47,109,126 y E:659,2361,2363 corrigen blanco/ámbar y separan fuentes/valores propios. E:640-641 conserva una afirmación global incompatible con esas adaptaciones y con UX-44. | **No enteramente**: la comprobación es manual; las filas concretas se arreglaron, pero la Guía todavía dice que lo único propio es conocer el mundo. AR2-07. |

## 4. Segunda pasada y decisiones del 5 de noviembre

| Mejora | Estado | Evidencia | ¿La prueba lo comprueba de verdad? |
|---|---|---|---|
| UX-18 | **Hecha** | E:223-224,2189-2203,2549-2550. Ayuda con rejilla/teclas vigentes; capturas aportadas y propia a 1280 muestran dos líneas sin invadir botones. | **Sí**, M:419-445 verifica texto, reasignación, ausencia sin selección/armada y prioridad de colocar. La rama de bloqueado se leyó y se ejercitó al probar rueda; no hay un test exhaustivo de toda selección múltiple. |
| UX-33 | **A medias** | E:83,217-218,427-439,596-597,1386,1634,1707. A 1280/1366 la barra queda estable, a 1024 y 1280 sin backend pasa a dos filas. Bajo 900 queda fuera del viewport inicial. | **Sí** para los tamaños y barrido indicados; **no** para «cualquier ancho». M:468-506 mide principalmente geometría horizontal y no exige top/bottom dentro del viewport. AR2-02. |
| UX-15 | **A medias** | E:879-880,1877,2243-2284 crea/abre escenas de sesión, conserva documento/historial y escena del juego; E:2437-2446 construye el recorrido. Pero Nueva funciona sin backend. | **No completa**: M:511-553 prueba vuelta, no envío de órdenes y bloqueo armada, pero omite crear con backend caído. AR2-03. Su prueba de Guía verifica orden de títulos/pasos, no que cada instrucción sea suficiente para ejecutar el flujo. |
| UX-44 | **A medias** | E:1682-1705 gira entidad/K2 y usa Alt; la suite reproduce 0→30→31° y K2 8→23°. Entidad bloqueada no gira. Ctrl también gira. | **No completa**: M:696-733 cubre esos casos, zoom en vacío/no seleccionado y toma armada; no Ctrl/Meta ni todas las cámaras/grupos. AR2-04. La elección de rueda está marcada PROPIO y atribuida a Guillermo. |
| UX-45 | **A medias** | E:2639-2658 cambia pasos/Mayús, conserva el scroll ya iniciado y respeta Ctrl/campo desactivado. La fusión usa solo el id DOM del campo. | **No completa**: M:737-761 pasa el mismo campo de la misma entidad; no detecta que girar/mover dos entidades seguidas comparta una sola transacción. AR2-05. Mi Ctrl sobre X conserva 6196 y el mapa bloqueado conserva 0°. |
| UX-30 | **A medias en aceptación y explicación; conducta básica hecha** | E:1304-1317 estima a 2,8 m/s; E:1431-1447,1540,2146,2663 añade copia rayada y selección por gesto sin mover el cursor. La captura clara propia muestra original, marcas y estimación distintos. | **No completa**: M:765-791 solo sigue el primer patrón y la presencia de una etiqueta; el patrón blanco pasa. También sigue la nota contradictoria de E:2113. AR2-01/07. |
| UX-46 | **A medias** | E:860,1258-1261,2171,2346,2613 y Guía enseñan la tecla y el origen. La parada normal y la coincidencia web/juego pasan. Armada, la opción simulada está desactivada; con corte durante Parando puede fabricar Observado. | **No completa**: M:795-824 comprueba la mención armada, pero ejecuta la tecla solo rodando/conectada; omite los estados adversos de AR2-06. El mod de cliente no se ha revisado. |
| UX-47 | **Hecha** | E:1074,1080,1103 conserva el nombre anterior para el paso de retirada y el aviso final. Aplicar nueva escena nombra Amanecer; reaplicarla no dice que quitó otra. | **Sí** para el aviso +/− de M:828-839. Por sí sola la prueba del toast no acredita el censo ni el reset real; el mecanismo del prototipo y UX-15 se inspeccionaron aparte. |

## 5. Hallazgos nuevos

BLOQUEA se usa con el sentido pedido: contrato roto o prueba que acepta una representación incorrecta. No implica que un proceso haya muerto, pérdida de datos del juego ni que todas las funciones fallen.

| ID | Gravedad | Mejora o regla | Dónde | Qué pasa | Evidencia | Arreglo concreto [DESIGN] | Criterio verificable + / − |
|---|---|---|---|---|---|---|---|
| AR2-01 | **BLOQUEA** | AR-03, AR-04, UX-30, CU-38, R26 | M:44,68-72,116,280-286,621-626,693,768-775; E:1422,1431-1447 | La aceptación aún confunde llamadas con apariencia: omite texto por drawImage, trata cualquier patrón como rayado y cualquier dash no vacío como discontinuo visible. | Tres mutantes: numerales a **2,05:1 oscuro / 3,16:1 claro** dan `4 pass, 0 fail`; textura de un único color RGBA blanco da `4 pass, 0 fail`; dash `[10000,0.001]` da `3 pass, 0 fail`. Se miraron sus capturas y se leyó el raster 6×6 del patrón. | Mantener la sonda útil, pero añadir un inventario independiente de textos esperados y verificación raster de glifos, huecos y rayas. Las superficies de origen de imágenes con texto deben medirse al componerlas o rechazarse expresamente como no cubiertas; solo el halo identificado puede excluirse. Verificar muestras del perímetro/interior real del marcador, no solo el tipo de fillStyle. | **+** Base actual: numerales, etiquetas esperadas, patrón alternante y borrador con huecos visibles pasan en ambos temas; tras lectura, marcador sólido. **−** Cada uno de estos tres mutantes falla por la propiedad rota aunque no cambien contadores, nombres de función ni CanvasPattern. Ausencia total de texto no da PASS vacío. |
| AR2-02 | **BLOQUEA** | UX-33, B5, CU-25, CU-35 | E:511-529, `.top`, `#bTopStop`, `#status`; M:468-477 | El layout de hasta 900 px convierte toda la página en scroll. MCP queda debajo del viewport y Parar se pierde al desplazarse a los paneles durante la toma. La prueba de barra solo exige borde horizontal y nunca que el texto esté dentro del alto visible. | A 390×768, MCP queda en y=1712,88…1730,27 al abrir; a 768×768, y=1634,09…1651,48. Rodando a 390 px y scrollY=800, Parar tiene top=−750/bottom=−720 y `elementFromPoint` no lo alcanza. Captura `tmp/A2-parada-movil.png`. | Conservar transporte/estado esencial en bandas persistentes también en el layout estrecho, o mantener su equivalente siempre visible al desplazarse; incluir avisos y menús en la comprobación. No ocultar MCP ni sustituir la obligación por «se encuentra haciendo scroll». | **+** A 390, 768, 900 y 901 px, al principio y desplazado hasta el último panel, MCP se ve entero y Parar se alcanza sin diálogo rodando/parando/pendiente de confirmación. **−** Volver a situarlos en el flujo que sale del viewport falla por rectángulo y hit-test, aunque su DOM exista. |
| AR2-03 | **BLOQUEA** | UX-15, CU-37, #7 | E:2246,2264-2270, menú `[data-act=m-new]`; M:540-553 | Nueva escena elude `offline()`/`editBlock()`: crea y abre otro documento con backend apagado, mientras la web afirma que no puede guardar cambios. `docBlock` solo mira toma/orden. | Simular backend apagado → Nueva escena sigue habilitada → cabecera pasa de «Amanecer… 2 cambios sin aplicar» a «Escena sin título… guardado hace 3 s». La sonda falla; el documento creado permanece en la lista de sesión. | Bloquear la creación en la guarda central y en el menú cuando falta backend, con el motivo visible. Abrir una copia ya disponible puede conservarse como consulta si no se presenta como creación/guardado; no es necesario prohibir toda navegación. | **+** Con backend, Nueva crea una vacía con cámara y conserva el mundo; sin backend, consultar no modifica documentos. **−** Sin backend, ni botón ni ejecución de la acción crean entrada/revisión/guardado; la cantidad de documentos y la escena abierta se conservan al intentar Nueva. |
| AR2-04 | **ALTA** | UX-44, UX-45, interacción del navegador | E:1682-1705; M:696-733 | El handler del mapa cancela siempre la rueda y gira aun con Ctrl/Meta. El gesto para ampliar la página puede alterar silenciosamente la escena seleccionada. | Bidón azul elegido y encuadrado; Ctrl + rueda −100: rumbo **0→15°**, transacción de giro. En un campo numérico, la misma combinación conserva la X: 6196→6196. | Salir del handler del mapa antes de `preventDefault` y `wheelTurn` con Ctrl/Meta, igual que se hace en el campo; conservar rueda simple y Alt. | **+** Rueda simple gira 15° y Alt 1° sobre lo elegido, y rueda simple en vacío acerca/aleja. **−** Ctrl/Meta + rueda en selección o vacío no cambia documento ni zoom propio del mapa y no cancela el gesto del navegador. |
| AR2-05 | **MEDIA** | UX-45, A5, #7 | E:958-967,2658; M:737-747 | La clave de fusión es `campo f-x`, sin escena, entidad ni clave de cámara. Dos destinos diferentes editados en menos de 900 ms se agrupan bajo el nombre del primero; un Deshacer revierte ambos. | X de Bidón azul 6196→6196,1; seleccionar Bidón verde y subir su X 6195,5→6195,6 antes de 900 ms: Historial **2→3**, no 2→4. Un Deshacer devuelve ambas X a 6196 y 6195,5. La selección se hizo pulsando el botón real del DOM, sin inyectar estado. | Incluir identidad lógica del destino y ruta del campo en la clave de fusión y cerrar la ráfaga al cambiar selección/escena. No ampliar la ventana temporal ni perder la agrupación de pasos del mismo campo. | **+** Tres pasos sucesivos de la X de una entidad generan una transacción y se deshacen juntos. **−** Un paso en A y otro en B, o K1 y K2, producen dos operaciones; deshacer la segunda conserva el cambio de la primera y nombra el destino correcto. |
| AR2-06 | **BLOQUEA** | UX-46, D2, B5, AR-01 | E:2171,2346,2613,1253-1258,1033; M:795-824 | La tecla simulada no sigue los estados que anuncia la web: armada dice que sirve, pero la opción está apagada. En Parando permite finalizar directamente con Observado aunque Tu juego esté desconectado, sin esperar lectura. | Armada: «También para… (Fin)» con `sim-gamestop.disabled=true`. Rodar → Parar web → cortar Tu juego → Pulsar «Parar toma»: fila **Observado**, «Leída hace 0 s · tu juego», con **Tu juego sin latido 0 s**. `endTake` marca parada confirmada y `setOp` asigna la edad actual. | Hacer que la simulación respete las mismas condiciones de evidencia que Parar web: desarmar cuando corresponda; con conexión perdida no entregar una confirmación a la web por el mero botón de pulsar tecla. Mantener el pendiente y reconciliar al recuperar una lectura; conservar deduplicación y origen. Esto no diseña ni modifica F5. | **+** Armada, tecla simulada desarma sin añadir una toma rodada; conectada y rodando, confirma una única parada con origen del juego. **−** Cortar Tu juego/backend durante Parando y simular la tecla no produce Observado, «leída hace 0 s» ni desaparición de la recuperación antes de reconectar y leer. |
| AR2-07 | **MEDIA** | AR-08, UX-30, UX-46, R20/R26 | E:640-641,2112-2113; LI:240,252; DI:105 | La documentación conserva reglas incompatibles con lo nuevo: la nota de previa dice «Mueve solo la cámara… ni los actores» mientras pinta al actor estimado; la Guía asegura que lo único propio es conocer el mundo aunque rueda/fuentes/paleta sean propias. «UX-46 − ya se cumplía» describe una simultaneidad que el viejo prototipo no podía ejecutar. | Texto `.tlnote` leído y captura con Mirek rayado; E:2424 y659 contradicen la generalización de E:641. M:818-824 acepta explícitamente «solo la web (no hay tecla del juego)» contra la base; DI:105 aún llama C-16 punto abierto aunque DI:199 lo resuelve. | Cambiar la nota a «Vista previa de cámara y actores estimados; no mueve el juego»; limitar la afirmación de procedencia a patrones y separar adaptaciones propias. Marcar el negativo antiguo UX-46 como no aplicable a concurrencia y retirar el puntero a C-16 abierto. | **+** Nota/leyenda/Guía distinguen estimación y mundo; las atribuciones permiten las adaptaciones propias declaradas; la prueba concurrente exige dos acciones presentes. **−** Mensaje «solo cámara», afirmación «lo único propio…» o ejecución de una sola parada no valida esos criterios. |

### Reproducciones y límites de cada demostración

**AR2-01 — tres cambios mínimos, sin modificar pruebas.** Se copiaron E y las sondas a `out` para ensayar; al terminar, los auxiliares se trasladan a `tmp` y el único entregable en `out` es este informe.

1. **Texto como imagen.** Solo en el cierre de `nums.forEach` (E:1422), sustituir `g.fillStyle = P.label; g.fillText(t, x, y);` por un canvas auxiliar oculto dentro de la página, tamaño 100×30, `q.font=g.font`, `q.fillStyle='#888'`, `q.fillText(t,2,15)`, y `g.drawImage(c,x-2,y-15)`; quitar el auxiliar después. La placa original permanece. El contraste WCAG de #888 con los fondos opacos actuales es 2,04554:1 y 3,15725:1. La prueba cuenta **8/4/5/9** textos por vista, frente a **19/15/26/26** del control, y aun así declara que todos los textos cumplen. El numeral sigue dibujado: la captura confirma que simplemente se ha vuelto pálido.
2. **Patrón uniforme.** En `hatch`, hacer opaco blanco el relleno de E:1433 y quitar `h.stroke()` de E:1434; mantener el tamaño 6×6 y `createPattern`. La lectura de los 36 píxeles devuelve un solo color, `255,255,255,255`. M:693 sigue contando un «rayado», y a 3/5 s mide movimiento de 11 px. La etiqueta «estimado» permanece: no afirmo que desaparezca toda distinción, sino que falta precisamente la distinción por rayas exigida.
3. **Discontinuo nominal.** En la rama draft de E:1447, cambiar `[3,2]` por `[10000,0.001]`. El perímetro completo cabe dentro del primer segmento; la captura muestra el contorno continuo. M:281 clasifica el string no vacío como discontinuo y solo considera sólido un stroke sin dash con grosor ≥3, por lo que acepta el borrador incorrecto a 1,9 px. No se ha cambiado el estilo después de Aplicar.

No afirmo que los numerales o los borradores de E sin mutar estén ya rotos. El hallazgo es el falso aprobado demostrado. El halo actual pasa el control, las cuatro vistas previstas y las adicionales medidas: no encontré una regresión de contraste introducida por ese halo. La sonda mide la cobertura de la letra real en el mismo lienzo; «todos los píxeles» significa **todos los que su máscara considera cubiertos al menos al 50 %**, como explica LI:203 y aplica M:60, no los bordes de antialiasing de cualquier cobertura. No se detectó retorno al margen del 98 %.

La comparación con 9d1a644 tiene dos causas distintas: registra como texto los halos antiguos de strokeText y también encuentra **letras reales** con huecos. En esta máquina «Mirek · M1» oscuro arroja 3,69:1 en 3/133 píxeles en la vista inicial; en claro hay además 4,43:1 en 1/133 en Rodaje. No se toma el contraste bajo del halo contra terreno como prueba aislada de ilegibilidad; los píxeles del fill son la evidencia material. Las cifras de un hueco a 4,43 y halo a 2,46 del documento son ejemplos, no un resumen completo del resultado Windows.

**AR2-02 — heredado, pero contractual.** La regla responsive de E:511-529 ya existía en 10274b7. No se imputa su origen al arreglo de noviembre; queda abierto porque se pidió verificar B5 y MCP a cualquier ancho. La medición aportada de barra a 390 px no acredita visibilidad permanente: un rectángulo puede caber horizontalmente y quedar a más de dos pantallas de distancia.

**AR2-03 — alcance de la prueba.** Es un cambio del documento local simulado, no una escritura en disco ni en backend real. Precisamente el prototipo debe enseñar el bloqueo de CU-37: no puede usar «solo existe en esta sesión» para representar como permitida una creación que el diseño niega sin backend.

**AR2-06 — parte web exclusivamente.** El botón se llama «Pulsar “Parar toma” en tu juego», no «inyectar una lectura confirmada pese a la desconexión». La secuencia se ejecutó con clics ordinarios mientras Parando espera: no se asignó `S.take`, ni se falsificó un evento del backend en la prueba. Si se quiere distinguir pulsación local y notificación recibida en el simulador, deben ser estados distintos; la web no debe fabricar evidencia por la pulsación. La corrección sigue dentro del prototipo y no presupone un contrato de F5 inexistente aquí.

## 6. Contrato y trazabilidad

| Regla | Resultado de esta revisión | Anclas y límite |
|---|---|---|
| D2: seis estados, edad y origen | Se conservan los seis y la separación petición/lectura. **Roto en la nueva vía de AR2-06.** | E:744-757,1027-1037,2101 y filas de Actividad. El test completo pasa éxito/corte/caducidad; un nuevo botón puede saltarse esa disciplina. |
| Estimado / borrador / observado | El original usa rayado interior, contorno discontinuo y marcador sólido, respectivamente; la copia estimada conserva original y marcas. | E:1446-1448,1532-1540,2326; captura propia en claro. El verificador no garantiza sus diferencias, AR2-01. La estimación no acredita locomoción real. |
| B5 y CU-25: Parar visible, sin diálogo | Recorrido de escritorio y protección de Guía/Atajos arreglados; **no cumple en scroll estrecho** y la tecla simulada tiene AR2-06. | E:1273-1285,1830-1836 y 2753 en adelante; ninguna exigencia de quitar Parar ni introducir un diálogo. <1 s de control real **[sin verificar]**. |
| #4: una sola preparación antes de rodar | Conservada en el recorrido normal | E:1196-1234,2162-2171; preparar comprueba y arma, Intro inicia. No se añade una segunda preparación manual. El backend y el GO real no están en este paquete. |
| #7: documento como fuente | La separación documento/mundo se conserva, pero Nueva elude el bloqueo offline y la rueda fusiona destinos distintos | E:959-974,1065-1104,2249-2270,2658. AR2-03/05. Persistencia y autoridad del backend real **[sin verificar]**. |
| #9: aplicar = reset y crear | Conservado; el cambio de escena mantiene esta operación | E:1077-1103; se retira la otra escena, crea por lotes, lee y publica. Aviso UX-47 correcto. No hay aplicación incremental añadida. Compensación real/censo de juego **[sin verificar]**. |
| #10: ids lógicos, epoch y propiedad | No se introduce selección o borrado por proximidad en el diff | E:976-981,1735 y2268 usan ids; el reinicio limpia también `S.other` en2610. Registro real, hijos, objetos ajenos y reencuentro tras reinicio **[sin verificar]**. |
| CU-02 | Se conservan códigos y rutas y se corrige Ver en los dos casos ensayados | E:996-1001,2127,2575-2580. No se afirma cobertura total de las cinco fixtures del producto por estas dos. |
| CU-18 | Conservado en el prototipo | Las dos suites y las sondas no registran peticiones externas. No acredita el proveedor de teselas de Leaflet futuro. |
| CU-35 | **No cumple la visibilidad a cualquier ancho solicitada** | AR2-02; MCP permanece escrito, pero fuera del viewport inicial estrecho. |
| CU-37 | Los campos/Aplicar se bloquean, pero **Nueva no** | AR2-03; el verde de P sobre cambios de propiedades no cubre esa nueva ruta. |
| CU-38 | Base actual pasa las vistas medidas en ambos temas; aceptación global insuficiente | AR2-01. Sin un fallo de contraste encontrado en E sin mutar, no se declara que el halo actual incumpla. |

### Diff completo 10274b7 → b106329: R20 y R25

Comparación textual de ambos HTML con `difflib.SequenceMatcher(autojunk=False)`: **101 bloques de cambio, 290 líneas nuevas frente a 107 antiguas** (incluye sustituciones, movimientos y líneas en blanco). Se inspeccionaron tanto las líneas añadidas como las retiradas. Esta agrupación cubre los bloques; justificar su alcance no acredita que sean correctos.

| Grupo del cambio | Anclas nuevas | Traza |
|---|---|---|
| Rejilla de aplicación, barra flexible, anchuras de coordenadas/pueblo, nota de prototipo | E:83,217-218,425-439,507,578,596-597 | UX-33 y segunda medida / CU-35 |
| Traslado/estilo de ayuda, texto según selección, rejilla y teclas actuales | E:223-224,530,2189-2203,2549-2550 | UX-18; ampliación de texto por UX-44 |
| Tamaño de small en Tomas | E:419 | AR-05 |
| Guía reordenada, seis pasos, estilo de lista, nuevas secciones | E:477-480,609-664,2437-2446 | UX-15; textos de rueda/tecla por UX-44/46 |
| Retirada de atribuciones exactas y ajuste de tabla de referentes | E:659,2361,2363,2423-2427 | AR-08 y referentes de UX-44/45/30/46 |
| Estado de sesión de escenas, Nueva/Abrir/Guardar como, CTA y otros resúmenes | E:879-880,905-921,1812-1829,1866,1877,1924-1925,2243-2284,2582-2586,2610 | UX-15; limpiar otra escena al reiniciar es dependencia necesaria |
| Mantener abierta la toma sin confirmar y guardas de órdenes/Guía/Atajos | E:944-947,1069,1111,1197,1824-1829,1840,2170,2307,2465,2614,2621 | AR-01 |
| Estado desconocido de mundo y refresco de resúmenes | E:197,1013-1021,1035-1037,1812,1860,1864-1865,1924-1941 | AR-02 |
| Placas, halo opaco/como imagen, eliminación de contadores LBLT/drafts/data-* | E:1345-1346,1417-1424,1453-1472 y retiradas junto a1532/1573 | AR-03, AR-04 y segunda medida |
| Foco/campo de errores y botón Ver | E:996-1001,2127,2575-2580 | AR-06 |
| Contar problemas y explicar el contador | E:2085-2089,2101 | AR-07 |
| Pueblo y cursor | E:1385-1386,1634,1707 | UX-33 |
| Giro por rueda y ayuda de rejilla | E:1679-1703,2342 | UX-44 |
| Agrupar rueda de campos y consumir eventos numéricos | E:958-960,2639-2658 | UX-45 |
| Patrón, actor estimado, leyenda y selección por gesto | E:380,1428-1447,1530-1540,2146,2326,2661-2663 | UX-30 |
| Tecla conocida, origen/aviso de parada y opción de simulación | E:859-860,1248-1261,1836,2171,2346,2613 | UX-46 |
| Capturar el nombre retirado y nombrarlo en el aviso final | E:1074,1080,1103 | UX-47 y UX-15 |

**No encontré líneas funcionales ajenas a esos encargos ni una ampliación a 3D, multiusuario, grabación de vídeo, mapas distintos, MCP, eventos o IA propia.** Los defectos de integración identificados no justifican ampliar M1. La rueda y el aviso de sustitución tienen autorización directa en la petición; no requieren volver a consultar decisiones cerradas.

No hay versiones antiguas completas de LI/DI en el paquete: **[sin verificar] el diff documental línea por línea desde 10274b7**. Sí se revisaron sus secciones vigentes pedidas, las citas precisas del informe anterior y la correspondencia con el diff HTML. Tampoco está la versión anterior de P para repetir su comparación histórica; se inspeccionó P actual y se ejecutó entero. La comparación M con `pruebas-mejoras-10274b7.js` confirma la sustitución de contadores de canvas por sonda y la ampliación de escenarios, sin que eso elimine AR2-01.

### Qué significa «ya se cumplía»

| Afirmación | Juicio sobre la base y la prueba |
|---|---|
| UX-18 − | Cierta en su alcance: no había ayuda de edición que tapase la de colocar o apareciese armada. No acredita que una ayuda nueva sea correcta. |
| UX-15 −, crear/abrir no manda órdenes | Cierta, pero antes Nueva/Abrir eran stubs. La ausencia de efectos del stub no demuestra conservación de estado al implementar varias escenas; el positivo nuevo aporta esa parte. El bloqueo armada sí falla en el viejo. |
| AR-01 −, corte con menú y Esc | Cierta para el menú ensayado: ya mantenía la indicación sin confirmar. La novedad que fallaba era Guía/Atajos y reaplicación, cubierta por el +. |
| AR-07 −, fallos históricos resueltos | Cierta para la fixture inicial, también en el viejo. No demuestra por sí sola el algoritmo de resolución; el + falla en el viejo y prueba el nuevo fallo-recuperación. |
| UX-44 − | Cierta en la base: solo había zoom; no modificaba lo no seleccionado ni la toma armada. No prueba modificadores de la nueva rotación. |
| UX-45 − | Cierta para los inputs y el foco ensayados en la base; no prueba la identidad de la nueva transacción ni todos los scrolls. |
| UX-46 − | **No válida como concurrencia ya resuelta.** M:818-824 reconoce que solo ejecuta la web si no existe la tecla. En actual sí hay ambas acciones y el caso conectado pasa. El viejo debería anotarse no aplicable para concurrencia, aunque la parada web ya fuera única. |
| UX-47 − | Cierta: reaplicar la misma escena no anunciaba haber retirado otra. El + nuevo prueba la diferencia del aviso. |

### Documentos y referentes

Las secciones 3-8 de LI y 2-6/8-12 de DI reflejan correctamente los cambios principales: ámbar vigente, 13 px propios, correcciones originales, segunda medida y decisiones de noviembre. El historial de cifras 51/66/76 y cuatro/cinco mutantes está separado por tandas en las secciones de verificación; no debe leerse 66 como resultado actual. Quedan las contradicciones concretas de AR2-07; además DI:16 cuenta 64 filas mientras la tabla de esa sección tiene **68**: actualización editorial pendiente, no un bloqueo nuevo.

| Referente público consultado | Qué acredita | Límite |
|---|---|---|
| [Unreal Editor Interface](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface) | Jerarquía de zonas de editor, Outliner/Details, controles de ejecución y barra de estado. | No fija Segoe UI, Cascadia, 13 px ni los hex del prototipo. La distinción patrón/valores en las filas corregidas es adecuada. |
| [Sequencer Editor](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine) | Mover el playhead permite previsualizar cambios en el viewport; pistas, transporte y navegación. | La copia adicional rayada, velocidad de 2,8 m/s y clic en gesto para seleccionar actor son adaptaciones; el artículo no certifica esos detalles. |
| [Replay Mod, documentación](https://www.replaymod.com/docs/#camera-paths) | Referencia de edición de caminos de cámara. | No acredita por sí sola la estimación de actores de DayZ ni su velocidad. |
| [Hilo de OBS sobre rueda](https://obsproject.com/forum/threads/in-game-scroll-wheel-changing-settings.83422/) | Testimonio de primera mano de 2018: la rueda sobre controles de OBS puede modificar ajustes accidentalmente; discusión de Qt y foco. | Respalda la procedencia histórica del comportamiento y su riesgo, no una recomendación normativa de UX ni la conducta de todas las versiones actuales de OBS. La protección del scroll y Mayús×10 deben entenderse como decisiones del prototipo. |
| [Soporte de Rockstar](https://support.rockstargames.com/articles/4gZPiqdUZD8ZhaJ81IPDJr/how-to-record-clips-and-access-the-rockstar-editor-in-gtav-on-pc) | Grabación y parada desde dentro del juego, mediante indicaciones y teclas F1/F2 por defecto. | Es captura de clips, no el protocolo de control de actores/cámara de Sandbox. La adaptación no habilita grabación de vídeo en M1. |
| [Manual Zeus](https://community.bistudio.com/wiki/Arma_3_Field_Manual_-_Zeus) y [navegación de Arma 3](https://community.bistudio.com/wiki/Arma_3%3A_Field_Manual_-_Navigation) | La búsqueda pública oficial de navegación respalda zoom del mapa con rueda. | La apertura de Zeus devolvió 403; su combinación precisa de rotación queda **[sin verificar]** en esta revisión. UX-44 ya se declara PROPIO por petición de Guillermo, por lo que no depende de fingir copia literal. |

No se buscó nada sobre DayZ Sandbox ni se consultaron fuentes privadas. No se verificó cada uno de los 68 enlaces históricos: se contrastaron las atribuciones corregidas y los referentes pertinentes a las incorporaciones.

## 7. DISENSO-FUERTE

### Mantengo el desacuerdo con cerrar por el verde; cambio sus razones

> Guillermo: los arreglos de la primera ronda mejoran de verdad la interfaz y no pido rehacerla. Pero no daría esta segunda ronda por cerrada: he reproducido los 76 y 64 aprobados y los cinco mutantes detectados, y aun así tres dibujos incorrectos pasan sus pruebas; Nueva crea un documento con el backend apagado; Parar desaparece al desplazar una ventana estrecha; y la tecla simulada puede anunciar Observado después de cortar Tu juego durante Parando. Corrijamos esas rutas y sus comprobaciones, además de Ctrl + rueda y la separación del Deshacer por entidad. Son defectos concretos de los cambios y del contrato, no votos sobre estilos.

### Retiro la acusación de atribución exacta en las filas corregidas; queda una contradicción acotada

> La tabla ya distingue bien las fuentes y colores propios de los patrones tomados de otros editores. Retiro esa parte de mi objeción anterior: no propongo volver al blanco ni cambiar los 13 px por gusto. Solo queda ajustar la frase de la Guía que asegura que lo único propio es conocer el mundo, porque contradice la rueda que tú pediste y las adaptaciones que la propia tabla reconoce. También debe decir claramente que la vista previa mueve actores estimados sin mover el juego.

Se mantienen retirados los disensos por 13 frente a 14 px, por el nombre «Quitar del juego» y por mostrar MCP en la barra. Las capturas son más claras y actuales; los solapamientos de etiquetas en escenas densas siguen siendo un límite visual conocido, no una nueva exigencia para esta ronda.

## 8. Para más adelante

- UX-16: resolver solapamientos de etiquetas sin perder su dueño.
- UX-17: prueba del recorrido de cámara con usuarios de DayZ/Arma, tras corregir los fallos actuales.
- Verificación con escala de Windows y dispositivos de rueda reales; DPR 1,25 no equivale a esa prueba.

## 9. Cierre y evidencia

Entrega única: `out/ui-revision2-astra.md`. Se preservan `ctx`, `medidas` y `medidas-9d1a644`; las copias de ensayo y seis capturas propias quedan como auxiliares temporales en `tmp`. No hubo implementación, instalación, cambio del contrato, commit ni escritura en memoria compartida: es una auditoría de un paquete, no una modificación de su repositorio.

**[Sin verificar]** backend y juego reales, Leaflet/Dockview, persistencia/atomicidad de documentos, topología de conexión, protocolo de F5, censo/propiedad de entidades, tiempos de control y repetibilidad en DayZ, uso asistivo y todas las combinaciones de zoom/viewport. No se convierte ninguno de esos límites en PASS a partir del prototipo.

Siguiente iteración de Claude: resolver AR2-01 a AR2-07, conservar los arreglos cerrados y las decisiones de Guillermo, añadir los casos discriminantes indicados y repetir controles antes de mutantes. No hace falta reabrir diseño ni pedir permiso sobre decisiones ya cerradas.

### Comprobaciones de cierre añadidas

- Repetición propia contra `ctx/estudio-76caccb.html`, `SOLO=UX-(44|45|30|46|47)`: **`RESULT 6 pass, 6 fail`**, salida 1. Fallan los cinco + y UX-30 −; los otros cuatro − y los dos controles generales pasan. Es exactamente el subconjunto correspondiente de los 70/6 aportados, sin casos abortados.
- Repetición dirigida del historial entre entidades, leyendo además el valor de B antes de deshacer: **`RESULT 2 pass, 1 fail`**. B efectivamente queda en **6195,6**, la ayuda de Deshacer sigue diciendo **«Mover Bidón azul»**, e invocarla revierte A y B. Confirma que no era un evento de rueda omitido.
- Los auxiliares reproducibles son `tmp/sondas-astra.js`, `tmp/sondas-extra.js`, `tmp/raster-astra.js` y las tres copias `tmp/mut-*.html`. Para repetir las mutaciones, M sigue siendo el original de ctx, ESTUDIO_URL apunta a la copia concreta y SOLO usa el filtro de la tabla de §2. Las sondas propias usan los mismos prefijos de entorno y ESTUDIO_URL explícita al original; no modifican su código.
- La última lectura comprueba UTF-8 sin BOM y los 14 hashes de ctx de nuevo; no hubo escrituras en ctx ni medidas. El inventario final con líneas y SHA256 se emite en el bloque A de la entrega.
