# Revisión cruzada adversarial — Astra — 2026-11-04

## 1. Veredicto

**NO APTO para cerrar AHORA:** hay falsos positivos de aceptación y fallos reproducidos en la exposición de la parada, la certeza del estado del juego y el contraste. La composición ya parece bastante más moderna y propia de un editor profesional, pero la legibilidad y la recuperación de errores todavía impiden considerarla profesional e intuitiva de forma consistente. Las mejoras se conservan: hacen falta arreglos concretos y pruebas que detecten estos casos, no otra remodelación ni recuperar mis preferencias de la crítica anterior.

Alcance: prototipo suministrado como commit `10274b7`, comparado con el suministrado como `de37c03`; identidad comprobada mediante los diez SHA256 de `ctx/SHA256SUMS.txt`, no mediante el historial del repositorio original. Revisión independiente, sin subagentes, sin modificar `ctx/` ni `medidas/`, sin backend ni juego real. Se declara el conflicto de interés indicado en el encargo y no se usa el número de lanes favorables como evidencia.

Convenciones de evidencia: `E` = `ctx/estudio.html`; `M` = `ctx/pruebas-mejoras.js`; `P` = `ctx/pruebas.js`; `DI` = `ctx/2026-10-28-ui-m1-consolidado.md`; `LI` = `ctx/2026-11-04-ui-mejoras-consolidado.md`. Las líneas corresponden a los archivos intactos del paquete. Los arreglos y criterios siguientes son propuestas [DESIGN], no cambios implementados.

## 2. Pruebas ejecutadas y alcance real del verde

Chromium arrancó dentro del sandbox. Se ejecutaron las tres órdenes prescritas en llamadas independientes, desde la raíz del paquete, con `PLAYWRIGHT_BROWSERS_PATH` apuntando a `pw/`, sin instalar nada.

| Corrida | Destino / condiciones | Resultado literal | Salida | Coincide con medidas |
|---|---|---|---|---|
| a | `node ctx/pruebas-mejoras.js`, `ESTUDIO_URL` = nuevo | `RESULT 41 pass, 0 fail` | 0 | Sí |
| b | `node ctx/pruebas.js`, nuevo, `CAPTURAS` = `out/capturas` | `RESULT 64 pass, 0 fail` | 0 | Sí |
| c | `node ctx/pruebas-mejoras.js`, `ESTUDIO_URL` = anterior | `RESULT 6 pass, 33 fail` | 1 | Sí |

Las dos cifras verdes son ciertas; no equivalen a que se cumpla todo el contrato. La prueba negativa del prototipo anterior produce **39 resultados, no 41**: el envoltorio de M:42–46 captura una excepción por bloque y omite las aserciones posteriores de ese bloque. Por ejemplo, los nuevos selectores de UX-08, UX-09 y UX-14 hacen abortar bloques; no se ha obtenido una comparación semántica independiente de cada positivo. No hay un positivo de mejora que aparezca aprobado contra el anterior, pero un timeout buscando un control nuevo demuestra su ausencia, no la corrección de toda la conducta nueva.

De los seis aprobados en c, cuatro son negativos que **ya se cumplían**: la vista previa no arma ni rueda; una comprobación fallida impide Rodar; un resultado Parcial no se presenta como «no ocurrió» ni ofrece Reintentar; Parar sigue siendo rojo. Los otros dos son ausencia de errores JavaScript y de peticiones externas. DI:309 reconoce los cuatro negativos preexistentes: no hay que atribuir su cumplimiento a noviembre.

Mediciones reproducidas: mapa 34 % → 53 % a 1440×900 y 29 % → 50 % a 1366×768, porcentajes redondeados por M:60; ocho controles de producto arriba a 1366, once contando los tres del prototipo. En el estado inicial a 1600, el contador DOM pasa de 188 a 90 nodos de texto; monoespaciados, de 66 a 1; con jerga detectada, de 31 a 0; menores de 12 px, de 92 a 0. Son nodos de texto del DOM visible según el helper, no palabras, píxeles de canvas ni una inspección de todos los paneles.

### Sondas adversariales adicionales

Se copió la cabecera y los helpers de M a una prueba temporal en `out/`, y se modificó una copia temporal de E en `out/`; nunca los originales. La primera ejecución de la sonda tuvo un error de sintaxis por codificación del pipe de PowerShell, corregido antes de medir. Las dos ejecuciones válidas dieron `RESULT 1 pass, 9 fail` y `RESULT 1 pass, 2 fail`: los FAIL son invariantes buscadas deliberadamente, no el resultado de las suites oficiales. La evidencia y los pasos reproducibles se conservan en §4; las copias temporales se retiraron al terminar.

- Geometría de barra y estado: seis tamaños comprobados, 1600, 1440, 1366, 1280, 1093 y 1024 px de ancho. Sin recortes detectados en las luces y controles examinados; no es una prueba de todos los diálogos o de zoom del navegador.
- Toma interrumpida: Guía y Atajos vuelven a abrirse antes de confirmar la parada; Guía cubre el control. «Reaplicar y preparar» también inicia una orden en esa condición.
- Error de validación: «Ver» selecciona la entidad correcta, pero mantiene Añadir abierto y el campo oculto.
- Orden Fallida: la tira sigue diciendo «Sin problemas». Creación parcial por corte: la cabecera de jerarquía dice «Nada en el juego».
- Texto numérico del canvas: contraste aproximado 2,03:1 en oscuro y 2,19:1 en claro sobre un edificio; ambos incumplen 4,5:1.
- Mutación controlada: marcadores sólidos aunque sean borrador y tipografía del canvas a 8 px siguen pasando los predicados examinados de UX-09, UX-10 y la auditoría DOM de contraste. No se ejecutaron las dos suites completas sobre el mutante.
- Panel Tomas: tres textos visibles de uso a 10 px. El helper de UX-10 solo obtiene cero pequeños porque ese panel no está en su recorrido.

Una sonda también marcó como fallo la falta de una etiqueta local de congelación en la tira plegada sin backend. **No lo elevo a hallazgo contractual:** existe el aviso global, `S.qsnap` conserva la última información y la tira muestra su edad; exigir además esa etiqueta local no está demostrado como requisito. Por eso el número de FAIL de las sondas no es el número de hallazgos aceptados.

Capturas inspeccionadas: las once de `medidas/capturas/`, desde `01-escena.png` hasta `11-guia.png`, más las capturas propias de contraste oscuro/claro. La corrida b produjo las once equivalentes en `out/capturas/`; se añadió `AR-01-guia-sin-confirmar.png`, cuya evidencia decisiva es la comprobación geométrica descrita en AR-01. No se deduce seguridad funcional de una captura estática.

## 3. Comprobación por mejora

«Hecha» describe el cambio concreto; no certifica todo M1. «Sí» en la última columna se limita al criterio nombrado; «No» identifica lo que la prueba deja pasar o no llega a examinar.

| Mejora | Estado | Evidencia en implementación / ejecución | ¿La prueba la comprueba de verdad? |
|---|---|---|---|
| UX-01 | A medias | E:1742–1747 fija Parar; E:2570–2576 prioriza la parada. Tras corte, `takeActive()` excluye el estado fallido y Guía tapa «Parada sin confirmar» (AR-01). | **No, completa no.** M:63–91 cubre menú y bloqueo armada, pero tras el corte solo busca el botón y la ausencia de control devuelto; no intenta taparlo. |
| UX-02 | A medias | E:127–141 y 1997–2008; mapa 53/50 %, tira con estado, edad y origen. El contador omite Fallido (AR-07); interacción de pestañas en AR-06. | **Sí** para área y Parcial visible, M:95–100; **no** para el significado de «Sin problemas» ni todos los recorridos con paneles plegados. |
| UX-03 | Hecha | E:1719–1751, 1757–1766, 2108–2109; agrupación, tres luces con edad, MCP abajo. Ocho controles de producto a 1366. | **Sí**, para recuento, nombres/edades y gris sin backend en los tamaños ensayados, M:104–122. No prueba toda combinación de mensajes y zoom. |
| UX-04 | Hecha | Aplicar escena y Quitar del juego, título que conserva el documento, contador en E:1731–1741; borrado de mundo separado de documento en E:1066–1075. | **Sí** para texto, disponibilidad y contador, M:126–136; **no por sí sola** para igualdad del documento antes/después: eso exige la lógica y el recorrido de reset, no un título. |
| UX-05 | Hecha | Detalles técnicos E:1827–1869; nombres de conducta legibles y valores internos en E:1878 y 2547; D2 conservado E:729–740 y 2025. | **No, completa no.** M:140–149 comprueba jerga inicial y un valor del selector; no verifica todos los guardados de conducta ni los seis estados/orígenes. No se encontró ruptura en el código leído. |
| UX-06 | A medias | E:1770–1776 quita insignias repetidas y añade resumen/edad; ese resumen equipara ausencia de lectura y mundo vacío (AR-02). | **No.** M:153–164 cubre conteos y un reset completo; no el corte durante creación. |
| UX-07 | Hecha | E:1731–1741 ofrece Ir a rodaje al estar observado y sin cambios. | **Sí**, M:168–179 comprueba la transición y que editar vuelve a exigir aplicar. |
| UX-08 | Hecha, con regresión de integración | E:1655–1665, 1702–1705, 1955–1989, 2597–2607: pestañas, búsqueda conservada, Tab/Esc, colocación y propiedades. «Ver» no se adaptó al nuevo panel (AR-06). | **Sí** para el flujo probado, M:183–199; **no** para los demás enlaces que deben revelar Propiedades ni para todos los caminos de entrada del límite. |
| UX-09 | Hecha visualmente; aceptación insuficiente | E:1382–1405, 1428–1469 y 1515–1518; etiquetas focales, tamaño reducido y borrador discontinuo vistos. | **No.** M:203–219 confía en `dataset.etiquetas` y `dataset.borrador`; el mutante visualmente incorrecto conserva esos resultados (AR-04). |
| UX-10 | A medias | E:68, 99, 1372–1379; 13 px base y 12 en varios textos. Tomas aún contiene texto a 10 px; números del mapa tienen contraste insuficiente (AR-03/05). | **No.** M:223–238 omite Tomas y el texto pintado en canvas; la mutación a 8 px pasa su positivo. |
| UX-11 | A medias | E:1937–1952 y 2065–2079; cabecera, reloj, comprobaciones plegadas y una acción principal. Recuperación tras parada sin confirmar sin protección equivalente (AR-01). | **No, completa no.** M:242–264 comprueba avance temporal y un fallo; no confirma la pose de cámara de la vista previa, todos los bloqueos ni el ciclo sin lectura. |
| UX-12 | Hecha en los tres casos pedidos | E:1043, 1049–1050 y 1201–1218 diferencia no entregada, compensación y resultado desconocido. | **Sí** para los textos, distinción y ausencia de «Reintentar» que ensaya M:269–298; el resumen general de problemas tiene el defecto AR-07. |
| UX-13 | Hecha en el simulador | E:990–997 y 2025 separa pedido/leído; fixtures E:864–869 y preparación E:1166, 1937–1952 añaden edad explícita. | **Sí** para la semántica de la muestra y ausencia de Observado sin lectura en M:289–298. No acredita marcas temporales emitidas por un backend real. |
| UX-14 | Hecha | E:1757–1766 «Tu juego», E:1968 presupuesto y E:2120–2124 un aviso reemplazable sobre el mapa. | **Sí** para textos y posición probada a 1600, M:303–322. No acredita todos los tamaños ni todos los textos futuros. |
| UX-25 | A medias | Paleta/capas y acción ámbar, cámara elegida neutra E:1915–1919; una principal en los estados ensayados. Falla CU-38 en el mapa (AR-03). | **Sí** para distinción básica y cantidad de principales en M:327–344; **no** para certificar el contraste de todo lo visible ni fidelidad exacta al referente. |

## 4. Hallazgos y arreglos verificables

Se usa BLOQUEA con el sentido del encargo: incumplimiento contractual o prueba que acepta un resultado incorrecto. No significa crash ni pérdida de datos demostrada. ALTA afecta al uso previsto sin justificar por sí sola un incumplimiento de contrato; MEDIA afecta a información secundaria o consistencia documental.

| ID | Gravedad | Mejora / regla | Dónde | Qué pasa | Evidencia | Arreglo concreto propuesto [DESIGN] | Criterio verificable R26 [DESIGN] |
|---|---|---|---|---|---|---|---|
| AR-01 | **BLOQUEA** | UX-01, UX-11, B5 | E:921, 1205–1218, 1743–1751, 2076, 2454 y 2461; `#bTopStop`, `#bGuide` | Al perder Tu juego durante una toma, se conserva `unconfirmed`, pero `takeActive()` ya es falso. Guía cubre toda la interfaz y oculta «Parada sin confirmar» antes de la lectura; Atajos también se permite. | Sonda: `guide=true`, `stopText=Parada sin confirmar`, `stopExposed=false`, `cover=true`; Atajos abre. Además, Reaplicar inicia una orden con la parada aún sin confirmar. M:63–91 queda verde. | Mantener visible el estado de parada pendiente hasta reconciliar, también al navegar/abrir superposiciones. Extender la protección de Guía/Atajos a esa condición o dejar una barra de parada persistente fuera de ellas. No rearmar silenciosamente durante esta recuperación; mantener explícita la lectura pendiente. No simular una confirmación ni habilitar una orden de parada que no pueda enviarse. | **+** Rodar, cortar Tu juego y abrir Guía, ruta de Guía y Atajos: la parada pendiente sigue expuesta sin diálogo; al reconectar, solo la lectura permite confirmar y preparar otra toma. **−** Sin lectura, una superposición que la tape o una indicación de control devuelto debe fallar; probar también corte con menú abierto. |
| AR-02 | **BLOQUEA** | UX-06, D2, #7/#9 | E:1039–1043, 1723, 1774–1776; `.worldline` | «Nada en el juego» se deduce de `!S.world`. Durante la creación el snapshot se anula; si se corta después de crear parte, la orden reconoce resultado desconocido mientras el resumen asegura que no hay nada. Confunde falta de lectura con vacío confirmado. | Corte al ir por 9 de 35: Actividad dice «Puede que siga creando» y «Sin lectura»; jerarquía dice «Nada en el juego». No es el caso distinto de compensación confirmada de E:1049. | Representar en el resumen la incertidumbre durante aplicación y tras corte, con última lectura/origen disponibles. Reservar «Nada en el juego» para una lectura o un resultado confirmado de retirada, distinguiendo la compensación del corte. Aplicar la misma semántica a los demás resúmenes que usan `!S.world`. | **+** Reset confirmado muestra vacío; aplicación completada y leída muestra contenido/edad. **−** Cortar después de iniciar lotes nunca muestra vacío confirmado ni Observado; reconectar y leer resuelve el desconocido sin depender de repetir Aplicar. |
| AR-03 | **BLOQUEA** | CU-38, UX-10, UX-25, R26 | E:1302–1303 y 1372–1374; texto numérico de rejilla en `canvas`; P:225–247 | Los números pequeños se dibujan sobre edificios sin fondo/halo suficiente. El auditor de contraste solo recorre nodos de texto DOM y no los ve; por eso CU-38 sale verde en ambos temas. | A 1366×768, número «6150», sobre edificio: **2,03:1 oscuro / 2,19:1 claro**, menor que 4,5:1. Capturas propias `AR-canvas-dark.png` y `AR-canvas-light.png`; detalle de cálculo debajo. | Asegurar contraste efectivo de los números sobre todos los fondos que atraviesan, por ejemplo mediante una placa o halo opaco apropiado a cada tema. Incorporar a CU-38 texto del canvas y sus fondos reales; no basta comprobar colores CSS de la página. | **+** Ambos temas, números sobre suelo y edificio en el encuadre de reproducción, mínimo 4,5:1. **−** Reintroducir los fills actuales sobre esos fondos hace fallar el test aunque los textos DOM sigan cumpliendo. |
| AR-04 | **BLOQUEA** | R26, UX-09 y UX-10 | E:1379, 1466–1469, 1505; M:203–238 | Los atributos de conteo los produce la misma lógica que se pretende certificar, sin verificar la representación. El marcador puede ser sólido y el texto ilegible mientras las pruebas dicen borrador distinguible y suelo de 12 px. | En copia, forzar `'solid'` en E:1469 y bajar tipografía de canvas a 8 px: `borrador` sigue 2 antes / 0 después de aplicar; predicados UX-09 negativo y UX-10 positivo siguen aprobando; auditor DOM no detecta contraste bajo. | Conservar los contadores como diagnóstico, pero verificar el resultado independiente: registro de órdenes reales de dibujo o comparación visual acotada que distinga contorno discontinuo de sólido, tamaño de glifo y texto. Añadir mutantes controlados a la comprobación de sensibilidad del test. | **+** Entidad nueva/cambiada se representa como borrador y pasa a sólida solo tras lectura, verificando el dibujo. **−** Forzar sólido antes de aplicar, reducir la letra a 8 px o suprimir una etiqueta obligatoria debe fallar aunque no cambien los `data-*`. |
| AR-05 | **ALTA** | UX-10, R26 | E:410 y 1809; Rodaje → Tomas → `.take small`; M:223–238 | El panel usa 12 px en `.take`, pero `small` reduce tres textos visibles a 10 px. Incumple el suelo acordado de 12 px para texto de uso. Es una carencia heredada que noviembre declara resuelta, no una regresión de tamaño inventada. | `getComputedStyle(...).fontSize` devuelve `10px` para el nombre de cámara y para «Travelling del autobús · Parada por la directora a los 2,9 s.». DI:126 exige suelo de 12; la prueba no abre Tomas. | Dar tamaño explícito de al menos 12 px a esos textos y añadir Tomas al recorrido de UX-10, incluidos finales normales y fallidos. | **+** Abrir Tomas tras parada normal y tras corte: nombres y causas visibles tienen al menos 12 px, con sus textos completos accesibles. **−** Restaurar `small` a 10 px hace fallar UX-10 aunque Escena inicial siga sin textos pequeños. |
| AR-06 | **ALTA** | UX-02, UX-08, recorrido CU-02 | E:1636–1640, 1702–1705 y 2424; `[data-act=val-go]` | «Ver» selecciona la entidad inválida, pero no cambia de Añadir a Propiedades. El campo a corregir queda oculto precisamente cuando el usuario llega desde el error. Los códigos y punteros sí están presentes: no se afirma que CU-02 los haya eliminado. | Bidón azul, X=-100; abrir Validación y después Añadir; pulsar Ver: entidad seleccionada `true`, campo X visible `false`. Texto mantiene `out_of_map /entities/14`. | Hacer que la navegación de error revele el panel de propiedades correspondiente y el campo señalado; conservar la selección y el encuadre actuales. Revisar el recorrido equivalente para errores de cámara. | **+** Con Añadir activo y error de X, Ver muestra Propiedades, selecciona la entidad y hace accesible X junto al error/código/puntero. **−** El test falla si solo cambia la selección mientras el campo sigue oculto; incluir error de una clave de cámara. |
| AR-07 | **MEDIA** | UX-02, UX-12 | E:1992–2007; `.strip .probs` | El contador llamado «problemas» incluye validación y Parcial, pero omite Fallido. La misma tira anuncia que Aplicar escena falló y afirma «Sin problemas», induciendo a ignorar una acción que no se entregó. | Servidor apagado → Aplicar → esperar caducidad: «Actividad Fallido Aplicar escena … pedida hace 10 s backend Sin problemas». | Contar los fallos relevantes no resueltos, o nombrar el contador de forma que delimite exactamente lo que cuenta. Establecer cuándo una acción posterior resuelve el fallo para no acumular alertas históricas para siempre. | **+** Una entrega fallida reciente hace visible el problema y una recuperación confirmada lo resuelve. **−** Con última orden Fallida sin resolver no aparece «Sin problemas»; fallos históricos ya resueltos no mantienen una alarma falsa. |
| AR-08 | **MEDIA** | R20, documento de diseño | DI:5, 41, 45–47 frente a 109–127; E:632 y tabla de referentes de la Guía | La introducción dice describir noviembre y anuncia cinco filas cambiadas, pero «Queda» aún prescribe paleta DayZ y principal blanco, en contradicción con el ámbar aprobado y la tabla actual. Además, atribuir la tipografía exacta a Unreal/Reforger no queda respaldado por las fuentes públicas examinadas. | DI:47: «Astra; el ámbar queda para la selección»; DI:127: ámbar para acción principal. Código y LI siguen la decisión de noviembre. Referencias consultadas acreditan estructura/patrones, no Segoe UI Variable/Cascadia Mono, 13 px ni esos hex exactos. | Actualizar las filas que siguen pareciendo normativas o identificarlas inequívocamente como histórico reemplazado. Atribuir al referente el patrón probado y marcar la elección exacta de fuente/medida/color como adaptación del proyecto mientras no haya fuente verificable. No volver al botón blanco. | **+** Documento y Guía señalan una única decisión vigente y separan patrón documentado de adaptación. **−** Una tabla que siga mandando blanco mientras la especificación vigente manda ámbar, o una atribución exacta sin evidencia, no pasa la revisión documental. |

### Reproducciones y evidencia de las sondas

**AR-01.** Página nueva → aplicar hasta Observado → Rodaje → Preparar → Rodar → simulador, desconectar Tu juego → esperar «Parada sin confirmar» → Guía. El elemento existe en el DOM, pero eso no significa que esté expuesto: la comprobación del rectángulo y del elemento situado encima devuelve `stopExposed:false, cover:true`. La captura queda en [AR-01-guia-sin-confirmar.png](capturas/AR-01-guia-sin-confirmar.png). Al cerrar Guía, Atajos abre igualmente; Reaplicar da `ran:true` mientras el texto de parada pendiente persiste. La diferencia que falta en el código es entre «toma terminada y confirmada» y «toma fallida pendiente de lectura»; no se exige que el navegador confirme lo que aún no sabe.

**AR-02/07.** Son dos rutas distintas: cortar Servidor durante «Creando por lotes» produce Parcial; apagarlo antes de Aplicar produce Pendiente y luego Fallido por caducidad. No se mezcla el corte con el fallo de creación compensado mediante el matraz. Las salidas observadas fueron, respectivamente, `iba por 9 de 35 / Puede que siga creando / Sin lectura` junto a `Nada en el juego`, y `Fallido / pedida hace 10 s / backend / Sin problemas`.

**AR-03.** En Escena, encuadre inicial a 1366×768, se interceptó `fillText` del numeral 6150 y se leyó el fondo antes de pintarlo; se comparó la máscara de sus píxeles interiores y se recalculó el contraste desde los valores CSS y el fondo. La posición local del texto es aproximadamente x=343, y=5 dentro del canvas; el fondo oscuro es RGB(88,83,74), con tinta rgba(25,25,15,0.8), que compone RGB(37.6,36.6,26.8) y da 2,0285:1. En claro, fondo RGB(123,117,105), tinta rgba(50,50,35,0.75), compone RGB(68.25,66.75,52.5) y da 2,1912:1. Se usó luminancia sRGB linealizada y `(Lmayor+0.05)/(Lmenor+0.05)`; el muestreo raster inicial de claro dio 2,22:1 por redondeo de la tinta, igualmente insuficiente. En oscuro los 72 píxeles interiores examinados del numeral quedan por debajo de 4,5:1; no se funda el fallo en bordes suavizados aislados. Capturas: [oscuro](capturas/AR-canvas-dark.png), [claro](capturas/AR-canvas-light.png).

**AR-04.** Mutaciones de la copia: cambiar el argumento `draft ? 'draft' : 'solid'` de la llamada a `drawGlyph` por `'solid'`; cambiar de 12 a 8 px las fuentes de rejilla/etiquetas/nombres del canvas. Los contadores siguen actualizándose por `drafts++` y `dataset.borrador`, sin observar el trazo. Resultado del ensayo de los predicados: `draftCountBefore:2`, `draftCountAfter:0`, `ux09negPass:true`, `ux10posPass:true`, `ux10small:0`, `domContrastLows:[]`. Esto demuestra dos falsos positivos concretos; no que todos los tests estén mal ni que el prototipo original dibuje ya sólidos sus borradores.

**AR-05/06.** Tomas se inspeccionó como panel visible, no como contenido oculto del DOM. Para el enlace de validación, X=-100 se introdujo por el campo de propiedades de Bidón azul y se confirmó con Tab antes de cambiar a Añadir: la selección correcta que hace Ver está comprobada, lo que falla es revelar el editor del campo.

## 5. Contrato preservado, roto o no acreditable en este paquete

| Regla | Resultado de revisión | Evidencia y límite |
|---|---|---|
| D2: seis estados con edad y origen | **Representación conservada; resumen de mundo incorrecto en AR-02** | E:729–740 conserva Pendiente, Ejecutando, Aplicado, Observado, Fallido y Parcial. E:2007 conserva estado, edad y origen de la última orden plegada; E:2025 muestra filas completas y diferencia edad de petición/lectura o Sin lectura. No se ha sustituido Aplicado por Observado. Las suites recorren éxito, fallo y corte; no certifican exhaustivamente todas las transiciones ni todas las combinaciones de antigüedad. |
| B5: Parar visible, sin diálogo | **No conforme en recuperación**, AR-01 | La prioridad de Esc funciona con menú y campo enfocado; el botón durante Rodando existe y no pide confirmación. La superposición tras corte rompe la persistencia visible requerida por UX-01. El plazo real de devolver control en menos de 1 s es **[sin verificar]**: este archivo solo simula el juego. |
| #7: documento fuente | **Conservado en el modelo del prototipo** | E:932–945 edita documento e historial sin tratar el canvas como fuente; E:1025–1034 aplica un snapshot separado. No existe backend aquí: persistencia/autoridad real del servidor **[sin verificar]**. No confundir selección, previsualización o texto de guardado con prueba de guardado real. |
| #9: aplicar = reset y crear | **Conservado** | E:1034–1058 enumera y ejecuta la simulación de validar, reservar, borrar, crear, leer y publicar. No se introdujo aplicación incremental. La semántica de incertidumbre del resumen requiere AR-02. |
| #10: ids lógicos | **Conservado en el código revisado** | E:1646 mantiene generación de ids y las operaciones usan los ids del documento; no se sustituyen por ids de red. Registro/reconciliación con entidades reales **[sin verificar]**. |
| #4: una preparación antes de rodar | **Conservado el camino normal; recuperación en AR-01** | E:1138–1181 reúne comprobaciones, prepara y solo permite Rodar armada; E:1937–1952 muestra edad y fallos. No aparece un segundo paso manual nuevo. El caso de repetir tras corte necesita conservar la distinción entre fallo y parada confirmada. |
| CU-18: sin peticiones externas | **Cumple en recorridos ejecutados** | M:347–348 y P pasan; página local y recursos incrustados. La navegación deliberada a fuentes públicas de esta revisión no es tráfico del prototipo. |
| CU-35: MCP apagado | **Cumple** | E:2109, texto de la barra de estado visible en las medidas. No se movió a un panel plegado ni se añadió integración MCP. |
| CU-37: sin backend, gris y edad | **Cumple en casos examinados** | E:1757–1766 vuelve obsoletas/grises las luces dependientes; Backend señala su propio fallo. E:2439–2441 conserva snapshot de Actividad; aviso global, edades y bloqueo de edición/aplicación presentes. La tira plegada usa `S.qsnap` y no inventa frescura. |
| CU-38: contraste en ambos temas | **No cumple**, AR-03 | Auditor DOM verde en los estados ensayados; numeral de canvas por debajo de 4,5:1 en ambos temas. No se certifica contraste global por cantidad de capturas o checks. |
| CU-02: código y puntero | **Conservados; recorrido de corrección incompleto**, AR-06 | E:964–974 produce código/puntero y E:2033 los conserva al poner el mensaje humano primero. `out_of_map /entities/14` sigue visible. El fallo es dejar el campo detrás de Añadir, no borrar el diagnóstico técnico. |

El plegado es aceptable cuando conserva la información exigida: estados y edad/origen de la última orden en la tira, luces y MCP en la barra, comprobaciones con edad y fallos abiertos. No recomiendo ocultar ninguna de estas obligaciones para simplificar la interfaz.

## 6. Comparación de las pruebas y trazabilidad del diff

### Pruebas de octubre: no hay ablandamiento material demostrado

Se comparó `pruebas.js` con `pruebas-antes.js`. Se mantienen las 64 comprobaciones y sus familias funcionales; el número por sí solo no fue el criterio de revisión. Los cambios observados adaptan selectores, paneles y textos a las mejoras, y añaden preparación de estados para las comprobaciones de contraste.

- `waitTxt` ahora exige rectángulo visible (P:21), una condición más fuerte que encontrar texto oculto.
- El helper del simulador cierra haciendo clic fuera, para no usar Esc cuando Esc ya debe parar. Es una adaptación correcta a UX-01, no una pérdida de su comprobación funcional.
- Esperar la disponibilidad de Aplicar y «sin cambios» sustituye el antiguo texto del botón; el recorrido conserva la comprobación de Observado en Actividad. La nueva espera sola sería insuficiente, pero no es toda la evidencia del caso.
- El presupuesto deja de exigir la composición tipográfica «= 44»; conserva los conteos relevantes de entidades/vestuario y la advertencia de límite no certificado. No encontré un límite funcional eliminado para satisfacer la suite.
- La comprobación de contraste sigue usando nodos de texto DOM y añade estados adecuados al nuevo diseño. Su omisión del canvas es un **hueco de cobertura**, no una condición recientemente eliminada. Noviembre conserva una declaración de aceptación demasiado amplia para ese mecanismo.

No hay evidencia de manipulación deliberada ni base para atribuir intención. Sí hay evidencia de que las nuevas pruebas aceptan implementaciones equivocadas (AR-04) y de que la cobertura combinada deja pasar incumplimientos reales (AR-01/02/03/05/06/07).

### R20/R25: correspondencia de cambios

Se revisaron los bloques del diff de E frente a `estudio-antes.html`, además del diff de pruebas. No apareció una función de producto fuera de M1 ni un control nuevo sin relación con AHORA. La siguiente agrupación hace explícita esa correspondencia; no convierte la existencia de comentarios `UX-xx` en prueba de corrección.

| Cambio del diff | Anclas actuales | Mejora que lo justifica |
|---|---|---|
| Colores, tipografía, dimensiones, separadores, radios y disposición | E:68–141, 410–500 | UX-02, UX-03, UX-10, UX-25 |
| D2 legible, nombres de conducta, detalles técnicos y edición del valor original | E:729–740, 1827–1878, 2547 | UX-05, UX-14 |
| Edades de muestras/órdenes/preparación y separación de última lectura | E:864–869, 990–997, 1166, 1937–1952, 2025 | UX-13 |
| Resúmenes de juego, iconos solo para diferencias, contador de problemas | E:1723–1741, 1770–1776, 1992–2008 | UX-02, UX-04, UX-06, UX-07; con AR-02/07 |
| Pestañas, acceso a Añadir, conservación de búsqueda, retorno a Propiedades y límites existentes | E:1655–1665, 1702–1705, 1955–1989, 2369–2373, 2597–2607 | UX-02, UX-08 |
| Jerarquía visual del mapa, glifos/hit targets, borrador, etiquetas, leyenda | E:1372–1518, 2176–2192 | UX-09, UX-10; `data-*` auxiliares de R26, insuficientes en AR-04 |
| Cabecera de toma, reloj, preparación plegada, acción contextual y protección de Parar | E:1201–1243, 1742–1751, 1937–1952, 2065–2079, 2454–2461, 2570–2576 | UX-01, UX-11, UX-12; con AR-01 |
| Barra de estado, grupo de utilidades y avisos reemplazables | E:1757–1766, 2108–2124, 2168–2171 | UX-03, UX-14 |
| Guardado/restauración de la disposición con nuevo estado de paneles | E:2151–2155 y consumidores de `L.de`, `L.dr` | UX-02, UX-08; la adaptación de estructura tiene un consumidor real |
| Guía y referencias actualizadas | Guía, E:632 y 2224–2226; DI | Documentación de AHORA; AR-08 exige coherencia, no una función nueva |

Los menús Nueva/Abrir que solo muestran un aviso, la captura externa de vídeo y el simulador no se presentan como funciones de producto recién implementadas. No se añadió vista 3D, multiusuario, grabación de vídeo, cambio de mapa, eventos, IA ni un backend MCP. Las discrepancias halladas son de cumplimiento o integración, no razón para ampliar M1.

## 7. Aspecto, uso y referentes

**El cambio visual funciona en lo principal.** En las capturas iniciales, el mapa tiene espacio de trabajo real; los paneles acoplados ya no compiten como tarjetas; las categorías del catálogo y la propiedad seleccionada son localizables; una acción ámbar identifica mejor el siguiente paso. En Rodaje, el transporte y el reloj hacen más evidente el modo y la tarea. Es una mejora visible y medida respecto a la captura anterior, no un premio por adoptar mi propuesta.

Lo que impide cerrar la valoración profesional no es que el gris o la fuente sean «de mi gusto»: un número de mapa pierde contraste sobre un edificio, las causas de fin de toma quedan a 10 px, un enlace de error no lleva al editor visible y dos resúmenes dicen más de lo que se sabe. En una tarea de machinima, esas incoherencias obligan a interpretar el estado de la herramienta cuando debería poder dedicarse atención a la escena. La concentración de etiquetas de actores/claves sigue siendo imperfecta en la muestra; su refinamiento pertenece al aplazado UX-16, no se introduce como nuevo bloqueo.

| Patrón adoptado | Qué está respaldado por el referente | Qué no se debe afirmar |
|---|---|---|
| Paneles, Outliner/Details, controles de ejecución arriba y log inferior | La documentación oficial muestra esas zonas y Play/Stop en la barra principal. El prototipo adapta esa jerarquía a su mapa y a Escena/Rodaje. [Unreal Editor Interface](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface). | No prueba los tamaños o colores exactos del prototipo ni su seguridad al cortar la conexión. |
| Ganar área de trabajo plegando contenido y agrupando información secundaria | Las notas de UE5 explican un tema oscuro, iconos consistentes, Content Drawer, paneles que se ocultan/fijan y progreso agrupado. Son patrones reconocibles en UX-02/25. [Unreal Engine 5.0 Release Notes](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5.0-release-notes?application_version=5.0#unreal-editor-interface). | No demuestran que Segoe UI Variable/Cascadia Mono, 13 px ni estos grises/ámbar sean los tokens de Unreal o Reforger. |
| Barra de documento y herramientas conocidas por usuarios de DayZ Editor | La wiki del autor documenta las categorías de la barra y acciones como deshacer/rehacer y cámara. La estructura familiar tiene fuente. [DayZ Editor — Toolbar](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar). | No convierte los grupos exactos, el borde discontinuo del simulador o los mensajes D2 en una copia literal de DayZ Editor. |
| Abrir catálogo, salir, colocar repetidamente y presupuesto | El texto oficial indexado de Game Master respalda Tab/Esc, colocación continuada con Ctrl y presupuesto que limita colocar. El prototipo usa patrones equivalentes con sus propias restricciones. [Arma Reforger — Game Master](https://community.bistudio.com/wiki/Arma_Reforger%3AGame_Master?useskin=darkvector). | La apertura directa de la wiki devolvió 403; no se compararon sus píxeles ni una sesión del juego. La coincidencia exacta del flujo de búsqueda conservada con Eden queda **[sin verificar]** en esta revisión. |

Se consultaron también los resultados oficiales de [World Editor](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor), [Eden Asset Browser](https://community.bistudio.com/wiki/Eden_Editor%3A_Asset_Browser) y [Eden Entity Placing](https://community.bistudio.com/wiki/Eden_Editor%3A_Entity_Placing); el acceso directo a páginas de la wiki estuvo limitado por 403. Se usan como pistas de patrones, no como verificación visual completa. No se buscó información sobre DayZ Sandbox.

Lo propio o adaptado es legítimo cuando se nombra: el panel que separa documento/juego/toma, los seis estados D2, la pareja Escena/Rodaje, el aviso de MCP apagado y el simulador responden al contrato o al prototipo. La paleta exacta y la elección de fuentes son decisiones locales inspiradas en referentes, hasta aportar una evidencia más específica. La familiaridad funcional está mejor justificada que una afirmación de copia exacta del aspecto.

## 8. DISENSO-FUERTE

### No cerrar AHORA por el verde de las suites

> Guillermo: la mejora visual es real, pero no aceptaría este estado como cerrado. He reproducido una parada pendiente que la Guía tapa, un resultado de creación desconocido presentado como «Nada en el juego» y texto del mapa por debajo del contraste exigido en ambos temas. También he hecho que una copia dibuje sólidos sus borradores y reduzca el canvas a 8 px sin que los predicados de UX-09/10 lo rechacen. Los 41 y 64 aprobados son cifras correctas, pero no son evidencia suficiente de esos criterios. Pido arreglar AR-01 a AR-07 y endurecer solo las comprobaciones que hoy dejan pasar esos fallos; no rehacer la UI a mi estilo.

### Referentes: distinguir patrón de adaptación

> Mantengo la regla de mirar lo que funciona en otros editores, pero no aceptaría presentar los valores exactos de fuente, tamaño y paleta como copiados de Unreal/Reforger sin una fuente que los respalde. Sí están respaldados la jerarquía de paneles, el contenido plegable y el transporte fijo. La corrección es documental: conservar la decisión vigente y marcar honestamente qué se adapta, sin volver a abrir el diseño por preferencia personal. AR-08 recoge la contradicción concreta que hay que eliminar.

**Decisiones de mi lane que no sostengo como disenso fuerte:** no he demostrado que 13 px de base sean un error frente a 14; el fallo comprobado son los 10 px y el contraste. «Quitar del juego» distingue de forma suficiente la retirada del mundo respecto al documento, con título y flujo coherentes; no exijo «Vaciar». «MCP apagado» debe continuar visible en la barra por CU-35, no ocultarse en Detalles de sesión. Tampoco hay evidencia aquí para exigir que desaparezca el grupo de utilidades del prototipo; ya está separado y no cuenta como producto en el recuento.

## 9. Para más adelante

- UX-15: revisar la experiencia inicial con una escena utilizable y el alcance real de Nueva/Abrir, cuando toque ese bloque.
- UX-16: ajustar solapamientos de etiquetas de actores y claves sin perder identificación al seleccionar.
- UX-17: probar el recorrido completo de cámara con usuarios de DayZ/Arma, conservando M1.
- Comprobar lectura a escala de Windows/navegador y monitores reales antes de elegir entre 13 y 14 px por preferencia.

## 10. Entrega y límites

Un único documento de revisión; las catorce imágenes de `out/capturas/` son evidencia auxiliar de las pruebas autorizadas. No se cambió código, contrato ni pruebas en `ctx/`, ni las mediciones aportadas. No se hizo commit: el encargo es revisar un paquete y entregar el informe, no editar o publicar el repositorio de implementación.

Quedan **[sin verificar]** el backend real, la autoridad/persistencia del documento fuera del simulador, la reconciliación con ids reales, el tiempo de devolución de control de B5 en DayZ, el rendimiento del juego, la fidelidad visual exacta a los editores de referencia y el uso con lector de pantalla o escalado distinto. No se infiere PASS de esos ámbitos a partir del prototipo. El siguiente paso corresponde a Claude: resolver los hallazgos con los casos positivos/negativos indicados y devolver evidencia, conservando los cambios visuales que sí funcionan.

## Anexo: sensibilidad contra el prototipo anterior

Desglose de la corrida c, cotejado con `medidas/mejoras-antes.txt`. «FAIL por excepción» no se cuenta aquí como validación semántica del criterio; «no alcanzado» conserva explícitamente lo que la suite no llegó a evaluar.

| Mejora | Positivo contra anterior | Negativo contra anterior |
|---|---|---|
| UX-01 | FAIL: un solo Esc no para con menú abierto | FAIL: Guía/Atajos abren armada; no conserva Parada sin confirmar |
| UX-02 | FAIL: mapa 34 % y 29 % | FAIL: no existe la tira plegada |
| UX-03 | FAIL: 13 controles y luces fuera de la ubicación/nombres requeridos | FAIL: barra mantiene Sin errores sin backend |
| UX-04 | FAIL: etiquetas/contador antiguos | FAIL: el estado tras editar conserva las revisiones antiguas como presentación; volver a aplicar ya estaba permitido |
| UX-05 | FAIL: jerga y proporción monoespaciada | FAIL por excepción al buscar el nuevo selector de conducta |
| UX-06 | FAIL: 36 iconos tanto aplicado como tras un cambio | FAIL: resumen de lectura/vacío ausente |
| UX-07 | FAIL: no existe Ir a rodaje | FAIL: aún se ve r14 aunque no se ofrezca Ir a rodaje |
| UX-08 | FAIL por excepción en búsqueda; FAIL en Tab/Esc | FAIL por excepción antes de evaluar el límite |
| UX-09 | FAIL por excepción antes de verificar etiquetas | FAIL: no existe el contador de dibujo esperado; no demuestra por sí solo cómo se pintaba |
| UX-10 | FAIL: 92/188 nodos menores de 12 px | FAIL por excepción durante el recorrido de paneles |
| UX-11 | FAIL: etiqueta/cabecera ausente, dos Parar y falta resumen de fallo | PASS ×2: previa no arma/rueda y comprobación pendiente bloquea Rodar; ya se cumplían |
| UX-12 | FAIL: faltan las tres formulaciones nuevas de fallo | PASS: Parcial no ofrece Reintentar ni niega que ocurriera; ya se cumplía |
| UX-13 | FAIL: no separa edad de petición/lectura | FAIL: el acuse no dice Sin lectura |
| UX-14 | No alcanzado: el bloque aborta por excepción | No alcanzado en ese bloque; se contabiliza un único FAIL de ejecución |
| UX-25 | FAIL: botón principal blanco | FAIL: dos principales en Rodaje con cambios; PASS en rojo de Parar, ya se cumplía |

Los otros dos PASS son los controles globales de red y errores JavaScript. El desglose conserva los 6 PASS / 33 FAIL observados sin convertir los abortos en 41 casos completos ni atribuir a noviembre lo que ya funcionaba.
