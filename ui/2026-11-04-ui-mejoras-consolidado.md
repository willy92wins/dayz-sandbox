# Mejoras de la interfaz M1: las cinco críticas juntas

2026-11-04 · Junta cinco críticas a ciegas del prototipo del commit `de37c03`. Todas tienen el mismo encargo y ninguna vio las demás de hoy:

| Lane | Fichero | Problemas | Mejoras |
|---|---|---|---|
| Claude | [2026-11-04-ui-critica-claude.md](2026-11-04-ui-critica-claude.md) | CC | MC |
| Astra | [astra/2026-11-04-ui-critica-astra.md](astra/2026-11-04-ui-critica-astra.md) | AC | AM |
| Grok | [grok/2026-11-04-ui-critica-grok.md](grok/2026-11-04-ui-critica-grok.md) | GRC | GRM |
| Muse | [muse/2026-11-04-ui-critica-muse.md](muse/2026-11-04-ui-critica-muse.md) | MUC | MUM |
| Gemini 4 | [gemini/2026-11-04-ui-critica-gemini.md](gemini/2026-11-04-ui-critica-gemini.md) | GEC | GEM |

Primero se juntaron las de Claude y Astra. Después Guillermo pidió contar también con Grok, Muse y Gemini 4 para propuestas, y sus críticas se sumaron a esta lista. Solo la lane de Claude midió el prototipo en un navegador; las otras cuatro lo critican leyendo el código. Gemini leyó además la lane de Astra de octubre, que iba en su paquete por error. Ninguna lane vio una crítica de hoy.

Responden a lo que dijo Guillermo: «No parece moderna ni profesional, y creo que es poco intuitiva. Hay que mirar mejoras». Sigue mandando su regla de copiar lo que funciona en otros juegos y editores. Para el aspecto pueden mandar Reforger y Unreal 5 sobre el DayZ Editor, porque el aspecto actual sale de este y no convence. Para el comportamiento y los atajos manda el orden de siempre.

El contrato no cambia:

- Los seis estados de D2, con su edad y su origen.
- Parar siempre a la vista y sin diálogo (B5).
- El documento como fuente (#7).
- Aplicar = resetear y crear (#9).
- Ids lógicos (#10).
- Una sola preparación antes de rodar (#4).
- Nada externo (D5 y E1).

Lo que cambia es la presentación que fijaba el [consolidado de octubre](2026-10-28-ui-m1-consolidado.md). Sus apartados afectados se actualizan al aplicar esta lista, para que no queden dos reglas a la vez.

**Estado:** las mejoras AHORA están en el prototipo y el consolidado de octubre ya está al día. Astra las revisó y las dio por NO APTO con ocho hallazgos, que están arreglados y probados (§7). También está hecha y probada una segunda pasada con tres mejoras de DESPUÉS (§6), que Astra aún no ha revisado. Los criterios pasan en [prototipo/pruebas-mejoras.js](prototipo/pruebas-mejoras.js) y fallan contra el prototipo de antes de cada tanda; el detalle está en la §12 del consolidado de octubre.

## 1. En qué coinciden

Las dos críticas llegan a lo mismo por caminos distintos:

- **El mapa no manda.** Hay cuatro paneles, la Consola abierta y dos mitades a la derecha (CC-01, AC-03).
- **Parece una maqueta.** Tarjetas redondeadas con borde y hueco, pastillas para todo y texto pequeño (CC-03, CC-04, AC-04, AC-05).
- **Habla como una herramienta de pruebas.** Clases, revisiones, hashes, ids de orden, epoch y números de decisiones a la vista (CC-02, AC-06).
- **La barra de arriba tiene demasiado.** Las utilidades del prototipo se mezclan con el producto (CC-08, AC-02).
- **No guía.** Añadir cuesta encontrarlo y, después de aplicar, nada dice qué toca (CC-05, CC-06, AC-08, AC-09).

Astra encontró además dos cosas que la lane de Claude no vio, y van primero:

- **Un fallo de contrato.** Con la Guía, el diálogo de Atajos o un menú abiertos, Esc los cierra antes de parar la toma, y la Guía tapa Parar (AC-01, contra B5 y CU-25).
- **Una edad equivocada.** La Consola enseña la edad de la petición, no la de la lectura (AC-14, D2).

Las tres lanes nuevas confirman esos cinco puntos (por ejemplo GRC-01, GRC-21, MUC-03, MUC-07, GEC-02 y GEC-05). Añaden dos que ni Claude ni Astra habían visto:

- **El botón blanco y el negro plano.** Las tres piden quitar el botón principal blanco y pasar a grises fríos por capas, como Unreal 5 y el World Editor de Reforger (GRC-02, GRC-25, MUC-01, MUC-02, GEC-01).
- **La toma, en dos sitios.** La cabecera de toma y la Preparación repiten el estado, y Parar sale dos veces (GRC-15, GRC-23, MUC-13, GEC-14).

## 2. Lista con prioridad

AHORA se hace en esta pasada sobre el prototipo. DESPUÉS necesita más estados o una prueba con personas. NO se descarta, con su motivo. La columna «Propuso» dice de quién sale cada mejora: Claude, Astra, las dos, Grok, Muse, Gemini o la consolidación (lo decidido al juntar). De las tres lanes nuevas va el id de su propuesta, y se nombra la parte que añadieron a una mejora que ya estaba. Los criterios siguen R26: un caso positivo y uno negativo.

### AHORA

| ID | Qué cambia | Resuelve | Propuso | Referente | Criterio |
|---|---|---|---|---|---|
| UX-01 | Parar gana a todo durante la toma. Esc para aunque haya un menú, un diálogo o la Guía abiertos. La Guía y los Atajos no se abren con la toma armada o rodando. Si se pierde la conexión a mitad, Parar sigue en la barra como «Parada sin confirmar» hasta que una lectura lo confirme. Sin diálogo | AC-01, MUC-14 | Astra; lo apoya Muse (MUC-14) | Esc sale de la vista previa en el World Editor de Reforger ([wiki](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor)); Play y Stop fijos en la barra principal de Unreal 5 ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface)) | + Rodando con un menú abierto, un solo Esc para la toma, y Parar sigue a la vista y sin tapar. − Con la toma armada, la Guía y los Atajos no se abren; tras un corte no sale «Control devuelto» sin lectura |
| UX-02 | Paneles acoplados de borde a borde, con separadores de 1 px y sin huecos ni radios. A la derecha, Propiedades y Añadir en pestañas; en Vista se pueden fijar las dos a la vez. Abajo, Actividad plegada en una tira con la última orden (estado, edad y origen) y el número de problemas. En Rodaje la línea de tiempo sigue abierta | CC-01, CC-03, CC-05, AC-03, AC-05, GRC-01, GEC-02 | Las dos; Añadir a la derecha, Astra; sin radios ni márgenes, también Gemini (GEM-01) | Hierarchy, Object Properties y Log Console del World Editor de Reforger ([wiki](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor)); Asset Browser a la derecha en Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Asset_Browser)); Output Log y Content Drawer plegados abajo en Unreal 5 ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface)) | + El mapa ocupa ≥ 50 % de la ventana a 1440 × 900 y ≥ 45 % a 1366 × 768. − Con una orden Parcial, la tira plegada sigue diciendo Parcial con su edad |
| UX-03 | Barra de arriba en tres grupos. A la izquierda, el documento: nombre con su menú, «2 cambios sin aplicar», deshacer y rehacer. En el centro, los modos Escena y Rodaje. A la derecha, las acciones (Parar, Quitar del juego, Aplicar escena, Ir a rodaje) y un menú Herramientas (paneles, atajos y ocultar la interfaz). Las utilidades del prototipo (simulador, referentes y Guía) van aparte, con borde discontinuo. Las tres luces bajan a la barra de estado, con su nombre y su edad siempre a la vista; ahí van también el mapa, la versión del juego, «Escena sin errores» y «MCP apagado». Los botones de modo enseñan su tecla (1 y 2), y la edad de las luces va en segundos enteros para que no parpadee | CC-08, CC-12, AC-02, GRC-01, GRC-10, GRC-12, GRC-24, MUC-03, MUC-04, MUC-20, MUC-21, GEC-07, GEC-09, GRC-16 | Las dos; las luces abajo y con edad, consolidación; el grupo del prototipo con borde discontinuo, también Gemini (GEM-03); la tecla en los modos, Muse (MUM-12); los segundos enteros, Gemini (GEM-03) | Barra principal y barra inferior de Unreal 5, que enseña el estado del control de versiones ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface)); menús con texto del DayZ Editor ([wiki](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar)); modos arriba en el Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)) | + Como mucho 9 controles del producto en la barra a 1366 px; las tres luces con nombre y edad a 1280, 1366 y 1600 px, y los modos enseñan 1 y 2. − Sin backend, las luces se ponen grises con «hace X» (CU-37) y la barra no dice «Sin errores» a secas |
| UX-04 | «Aplicar escena» como nombre fijo, y el número de cambios aparte. La ayuda dice antes del clic que recrea la escena entera. «Resetear» pasa a «Quitar del juego», con «el documento no cambia» en su ayuda y la confirmación de siempre | AC-07, CC-13, GRC-04, GRC-11, MUC-02 | Astra; «Quitar del juego», consolidación; también Grok (GRM-04) y Muse (MUM-02) | Push Changes de UEFN separa lo editado de lo que corre ([docs](https://dev.epicgames.com/documentation/en-us/fortnite/first-island-04-playtest-your-island-in-fortnite)); que recrea la escena entera sale de #9 | + Con cambios, el botón dice «Aplicar escena» y la cabecera «2 cambios sin aplicar». − Con cero cambios se puede volver a aplicar, y nada va al juego sin pulsar Aplicar |
| UX-05 | Lo técnico, plegado. Fuera de la vista por defecto: la clase en las filas, ids, hashes, verbos de orden, epoch y versiones. Van en «Detalles técnicos» o al pasar el ratón. Los comportamientos se llaman «Quieto», «Recorrer una vez», «Repetir recorrido» y «Deambular», sin cambiar el valor guardado. En Validación va primero el mensaje y después el código. Los textos de uso no citan decisiones ni criterios | CC-02, CC-10, CC-11, AC-06, AC-13, GRC-05, GRC-06, GRC-07, GRC-21, MUC-07, MUC-09, MUC-10, MUC-11, GEC-05, GEC-06 | Las dos; también Grok (GRM-05, GRM-06, GRM-15), Muse (MUM-05, MUM-11) y Gemini (GEM-02) | Object Properties del World Editor separa la información de la entidad ([wiki](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor)); resumen y detalle del error en el Session Inspector de UEFN ([docs](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector)) | + Escena recién abierta: como mucho 6 textos con jerga y 10 % del texto en monoespaciada. − Cada orden sigue enseñando su estado D2, su edad y su origen sin abrir nada; el documento guarda los mismos valores |
| UX-06 | Estado por excepción en la Jerarquía: sin icono cuando la entidad coincide con el juego, y con icono si es nueva o ha cambiado. Arriba, una línea dice qué hay en el juego y la edad de la lectura | CC-07, GRC-14, MUC-06, GEC-08 | Claude; también Grok (GRM-07) y Gemini (GEM-11) | PROPIO (#7), sobre la lista de entidades de Eden | + Con todo aplicado y leído, 0 iconos en las filas; con un cambio, 1. − La línea de arriba dice la edad de la lectura, o «Nada en el juego» si no hay nada |
| UX-07 | Siguiente paso a la vista. Aplicada y leída la escena, aparece «Ir a rodaje». Propiedades sin selección resume la escena (estado, contenido y ambiente) y dice qué toca, con el detalle técnico plegado. El contenido va en una línea, sin repetir la tabla de cuentas de la Jerarquía | CC-06, CC-11, AC-08, MUC-15, GEC-08 | Claude; el contenido en una línea, Gemini (GEM-11) | Scenario properties del Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)) | + Tras aplicar con éxito, «Ir a rodaje» lleva a Rodaje. − Con cambios sin aplicar no aparece, y sin selección no se ve ningún hash ni revisión |
| UX-08 | Añadir, con varios cambios: las categorías son pestañas con su cuenta; la búsqueda se conserva al cambiar de categoría y al volver; si no hay resultados, sale «Limpiar búsqueda»; el selector de clase enseña el nombre legible; el presupuesto va dentro, con «Tope total aún sin certificar». Tab con el mapa activo abre Añadir y Esc vuelve. Al colocar, lo nuevo queda seleccionado con sus propiedades a la vista (Ctrl + clic sigue colocando). Añadir solo tiene lo que se pone en el mapa (objetos, infectados, animales y actores): el vestuario y los gestos se quedan en las propiedades del actor, donde ya se editan. Mientras se coloca, el cursor es una cruz y un fantasma de la entidad sigue al ratón | CC-05, AC-09, GRC-17, GRC-18, GRC-20, MUC-05, GEC-11 | Las dos; también Grok (GRM-05, GRM-14); sin vestuario ni gestos, Gemini (GEM-06); la cruz y el fantasma, Muse (MUM-04) | Entity Browser del Game Master: Tab, Esc, presupuesto dentro y Ctrl + clic ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)); búsqueda por nombre en Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor%3A_Entity_Placing)); el Asset Browser de Eden solo lista lo que se coloca ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Terminology)) | + Buscar «bidón», cambiar a Infectados y volver: la búsqueda sigue. − Al tope no se puede añadir, y el total sin certificar no se presenta como ilimitado |
| UX-09 | Mapa: marcadores un 25 % más grandes y con contorno. Las marcas y claves del seleccionado llevan su dueño («Mirek · M1», «Travelling del autobús · K1») y lo demás se atenúa. Hay una leyenda plegable dentro del mapa, y el candado se dibuja en vez de ser un emoji. Los pueblos van en minúscula normal, no en versalitas, y cada entidad con rumbo lleva una muesca hacia donde mira | CC-09, AC-10, AC-05, GRC-08, MUC-12, MUC-22, GEC-04, GEC-12, GEC-13 | Las dos; también Muse (MUM-08, MUM-09) y Gemini (GEM-04, GEM-10); los pueblos sin versalitas, Grok (GRM-08) y Muse (MUM-08); la muesca, Gemini (GEM-04) | Mapa 2D de Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor%3A_Introduction)); claves de cámara de Replay Mod ([docs](https://www.replaymod.com/docs/#camera-paths)) | + Con Mirek seleccionado, sus marcas dicen «Mirek · M1», la leyenda se abre sin salir del estudio y ningún pueblo va en mayúsculas. − Lo que está sin aplicar se sigue dibujando como documento, no como observado |
| UX-10 | Sistema visual: letra del sistema a 13 px con suelo de 12; monoespaciada solo en coordenadas y tiempos; filas de 30 px; una familia de iconos; radios de 0 en paneles, 4 en controles y 8 en lo que flota; sombras solo en lo que flota. Ámbar solo para selección, foco y la acción principal (UX-25), y verde solo para evidencia: la cámara elegida deja de llevar el check verde. La letra del sistema empieza por Segoe UI Variable, y las cifras de tiempos, coordenadas y edades son tabulares | CC-03, CC-04, AC-04, AC-05, GRC-03, GRC-19, MUC-16, MUC-17, GEC-03 | Las dos; 13 px, consolidación; Segoe UI Variable y cifras tabulares, Gemini y Grok (dirección visual) | Notas de Unreal 5.0 sobre la interfaz ([docs](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5.0-release-notes?application_version=5.0#unreal-editor-interface)); los valores exactos están [sin verificar] | + Como mucho 15 % del texto visible por debajo de 12 px, y CU-38 sigue pasando en los dos temas. − Ningún texto de uso baja de 12 px para que algo quepa |
| UX-11 | Rodaje, en varias partes. Una cabecera de toma con número, cámara, estado, reloj y la acción que toca, sin la claqueta decorativa ni los cuatro pasos repetidos. Preparación resume «7 de 7 comprobaciones» con su edad y abre los fallos. La línea de tiempo se llama «Vista previa del mapa» y su botón «Previsualizar» no se parece a Rodar. La insignia dice «Rodando» y que el vídeo lo graba una herramienta externa. Parar sale solo en la barra de arriba, que es el que no se mueve (B5); la cabecera de toma deja la acción que sigue: Preparar, Rodar o Reaplicar y preparar. Si falla una comprobación, la cabecera dice cuál y ofrece el arreglo | AC-12, GRC-15, GRC-23, MUC-13, GEC-14 | Astra; también Muse (MUM-07, MUM-15); un solo Parar, Grok (GRM-13) y Gemini (GEM-05); el fallo en la cabecera, Gemini (GEM-05) y Muse (MUM-07) | Sequencer de Unreal ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine)); Studio Mode de OBS ([guía](https://obsproject.com/kb/obs-studio-overview#studio-mode)); previa de caminos de Replay Mod ([docs](https://www.replaymod.com/docs/#camera-paths)) | + Previsualizar mueve solo la cámara del mapa; rodando hay un solo Parar a la vista; con una comprobación fallida, la cabecera la nombra y ofrece el arreglo. − No arma ni rueda, y una comprobación que falta impide Rodar |
| UX-12 | Los fallos dicen qué pasó, qué queda en el juego y qué hacer, sin perder las frases que fija el contrato: «No se entregó», «Falta confirmar el resultado» y «Reconciliada tras el corte». «Hombre muerto» va explicado: el mod paró la toma por seguridad | AC-13, MUC-19 | Astra; también Muse (MUM-10); «hombre muerto» explicado, Gemini (bloque C) | Session Inspector de UEFN ([docs](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector)) | + Los tres fallos del simulador dejan causa, efecto y siguiente paso. − Un Parcial por respuesta perdida no ofrece «Reintentar» ni dice que no ocurrió |
| UX-13 | La edad de la evidencia va aparte de la de la petición: «Pedida hace…» y «Leída hace… · servidor», o «Sin lectura» | AC-14, MUC-08 | Astra; lo apoya Muse (MUC-08) | Duración frente a fecha de fin en el Session Inspector de UEFN ([docs](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector)); la edad de la muestra es de D2 y #23 | + Reconciliada tras un corte, la lectura es más nueva que la petición. − Un acuse sin lectura dice «Sin lectura», nunca «hace 0 s» |
| UX-14 | Textos: plurales bien; «Tu juego» en vez de «Director»; «Actividad» en vez de «Consola»; nada de `take` ni `scene_apply` a la vista. Los avisos salen de uno en uno, abajo en el centro del mapa | CC-12, CC-13, CC-14 | Claude | Avisos sobre la vista [sin verificar] | + Ningún texto visible con «1 gestos», «Resetear», `take` o `scene_apply`. − Los avisos no tapan Parar ni las pestañas de la derecha |
| UX-25 | Paleta de estudio y una sola acción principal. El tema oscuro pasa a grises fríos por capas: el fondo del chasis, el panel, el campo y el realce van un paso más claros cada uno, con líneas de 1 px; el mapa sigue siendo la única superficie de papel. El botón blanco desaparece: la acción principal de cada modo va en ámbar con texto oscuro (Aplicar escena con cambios, o Ir a rodaje; en Rodaje, la acción de la cabecera de toma), y nunca hay dos a la vez. Parar sigue en rojo. El tema claro tiene sus equivalentes | GRC-02, GRC-13, GRC-25, MUC-01, MUC-02, MUC-17, GEC-01 | Grok (GRM-02, GRM-11), Muse (MUM-01, MUM-02, MUM-17) y Gemini (GEM-01); los valores, consolidación sobre los de Muse y Gemini, que casi coinciden | Superficies del editor de Unreal 5 ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface)) y del World Editor de Reforger ([wiki](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor)), como citan las tres lanes; los valores exactos están [sin verificar] | + En oscuro, chasis, panel y campo tienen tres fondos distintos, el botón principal no es blanco y CU-38 sigue pasando en los dos temas. − Nunca hay dos botones principales a la vista, y Parar no pierde el rojo |

### DESPUÉS

| ID | Qué cambia | Resuelve | Propuso | Referente |
|---|---|---|---|---|
| UX-15 | Empezar desde una escena vacía: Nueva y Abrir funcionan, la escena vacía invita con «Añade tu primer objeto» y la Guía empieza por el recorrido (crear, aplicar, cámara, preparar, rodar y parar). La procedencia pasa a «Acerca del diseño» | AC-08, CC-06, GRC-09 | Las dos (AM-13, MC-12); también Grok (GRM-12), Muse (MUM-12) y Gemini (GEM-12) | Guided Tour del Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)); New y Open del DayZ Editor ([wiki](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar)) |
| UX-16 | Etiquetas del mapa por prioridad (selección, toma, resto y geografía), con pueblos y controles en la reserva de sitio; las de objetos, al pasar el ratón o con selección, y siluetas dentro de las formas | AC-11 | Astra (AM-14); también Muse (MUM-08); las siluetas, Gemini (GEM-10) | Eden y Replay Mod; la regla exacta está [sin verificar] |
| UX-17 | Ayuda de cámara en tres pasos entre DayZ y el estudio | AC-16 | Astra (AM-15) | Cámara libre de COT ([Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=1564026768)) |
| UX-18 | Ayuda breve junto al mapa según lo seleccionado, con el paso de rejilla y las teclas reasignadas | AC-15, MUC-18 | Astra (AM-16); también Muse (MUM-14) | Atajos del DayZ Editor ([wiki](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts)) |
| UX-19 | Miniaturas reales de cada clase en Añadir, capturadas en el juego y nunca generadas | CC-05 | Claude (MC-11), con el límite de Astra (AM-17) | Content Browser de Unreal ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/content-browser-in-unreal-engine)) |
| UX-26 | Una manija en el aro de selección para girar arrastrando, además de Mayús + arrastrar | GEC-12 | Gemini (GEM-04) | Girar en Eden es Mayús + arrastrar ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Entity_Transforming)); la manija sale del widget de transformación, [sin verificar] |
| UX-27 | Clic derecho sin arrastrar abre un menú de la entidad en el mapa, y se puede arrastrar desde Añadir al mapa | GEC-11 | Gemini (GEM-06) | Colocar en Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Entity_Placing)); el menú contextual está [sin verificar] |
| UX-28 | La Jerarquía de la escena también en Rodaje, y «Nueva cámara desde la cámara libre» también en Escena | GEC-10, MUC-21 | Gemini (GEM-07); Muse (MUC-21) | El Outliner sigue abierto junto al Sequencer en Unreal 5 ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine)) |
| UX-29 | Campos numéricos que se ajustan arrastrando, con una sola transacción al soltar | GEC-03 | Gemini (GEM-09) | Campos numéricos de Blender y panel Details de Unreal 5, [sin verificar] |
| UX-30 | Línea de tiempo: clic en un gesto selecciona al actor. Si Guillermo elige mover los actores con el cursor (§8.4 de octubre), van en su posición estimada y rayados | GEC-15, MUC-13 | Gemini (GEM-08); Muse (MUM-15) | Sequencer de Unreal ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine)); caminos de Replay Mod ([docs](https://www.replaymod.com/docs/#camera-paths)) |
| UX-31 | Varias entidades a la vez: posición y rumbo por campos, que ya era criterio para F6 (CU-11), y giro del grupo alrededor de su centro | GEC-16 | Gemini (GEM-12 y bloque C) | Valores mixtos de Eden (consolidado de octubre, §2); el giro del grupo está [sin verificar] |
| UX-32 | Bloquear y ocultar alcanzables con el teclado en la Jerarquía, no solo al pasar el ratón | MUC-06 | Muse (MUM-13) | Entity List de Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Terminology)) |
| UX-33 | Barra de estado por zonas, con las coordenadas del cursor y el pueblo más cercano | GEC-17, GRC-22 | Gemini (GEM-13); el pueblo, Grok (GRM-08) | La barra de estado de Eden da la posición del cursor y, en el mapa, los metros por píxel ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Status_Bar)) |

### NO

| ID | Qué se descarta | Propuso | Motivo |
|---|---|---|---|
| UX-20 | Cambiar los nombres de los seis estados de D2 o juntarlos en un semáforo | Las dos (MC-13, AM-19) | Son contrato; se explican al pasar el ratón |
| UX-21 | Quitar las tres luces | Claude (MC-14) | CU-37 las pide; bajan a la barra de estado |
| UX-22 | Un cambio de marca con letra futurista, tarjetas grandes y transparencias, o acciones principales solo con icono | Astra (AM-17) | La mejora sale de la composición y la jerarquía |
| UX-23 | Un asistente con «Aceptar» en cada lectura, o preparar por partes | Astra (AM-18) | #4 pide una sola preparación |
| UX-24 | Paleta de comandos | Claude (MC-15) | Fuera por R25 desde octubre |
| UX-34 | Barra de arriba en dos filas | Grok (GRM-01), Muse (MUM-03) | Quita al mapa el alto que gana UX-02; una fila en tres grupos cabe a 1366 px (UX-03) |
| UX-35 | Juntar las tres luces en un solo control, o llevar su edad al «title» | Grok (GRM-09), Muse (MUM-03), Gemini (GEM-03, la edad) | CU-37 y §3.3. Abajo, en la barra de estado, ya no compiten con el trabajo, y en segundos enteros no parpadean |
| UX-36 | Sacar «MCP apagado» de la barra de estado | Grok (GRM-09), Muse (MUM-16) | CU-35 (E3) pide que la barra lo diga |
| UX-37 | Plegar el origen de cada orden o el código de validación | Grok (GRM-07), Muse (MUM-05) | D2 y CU-02 los piden a la vista; se pliegan el id, el verbo y las etapas |
| UX-38 | Cambiar «Aplicado» por «Hecho, falta confirmar» en la pastilla, o rotular cada etapa | Muse (MUM-06) | UX-20: los seis nombres son contrato. La diferencia con Observado la da la línea de lectura (UX-13) |
| UX-39 | Las utilidades del prototipo en un menú o en una banda abajo | Grok (GRM-10), Muse (MUM-16) | §3.5: quien revisa usa el simulador todo el rato; quedan en el grupo discontinuo, como propone Gemini (GEM-03) |
| UX-40 | Paneles con radio de 6 a 10 px y sombra, títulos de 15 px e iconos de 20 px | Grok (GRM-03 y dirección visual), Muse (MUM-01) | Los paneles acoplados no llevan radio (UX-02, también Gemini GEM-01), y la densidad es la de §3.2 |
| UX-41 | Avisos de fallo que no se van solos, en una franja bajo la barra | Muse (MUM-10) | La tira de Actividad guarda la última orden con su estado (UX-02), y el aviso de conexión ya se queda hasta que vuelve; un aviso fijo taparía el trabajo |
| UX-42 | Los colores de tipo del mapa, en una sola tinta | Muse (MUM-09) | Gemini pide lo contrario (GEM-04). Se queda el color, con el contorno de UX-09, que ya lo separa del terreno |
| UX-43 | Ocultar Parar de la barra cuando la cabecera de toma está a la vista | Gemini (GEM-05) | B5: el Parar de la barra es el que no se mueve, así que el que se quita es el de la cabecera (UX-11) |

Las tres lanes nuevas descartan además lo mismo que el contrato: tocar los atajos de D4 (GRM-16), un diálogo antes de Parar (MUM-19), quitar el id de orden del todo (MUM-18), teselas externas o una vista 3D (MUM-20), meter Dockview en el prototipo (GEM-14), fuentes por red (GEM-15), lo que está fuera de M1 (GRM-17) y la paleta verde que ya se descartó en octubre (GRM-18).

## 3. Dónde chocaban y qué se eligió

1. **Dónde va Añadir.**
   - Claude la quería a la izquierda, en pestañas con la Jerarquía, como en Unreal y Roblox.
   - Astra, a la derecha, en pestañas con Propiedades.
   - Gana la derecha: Eden pone el Asset Browser a la derecha y en comportamiento manda antes que Unreal. Además, así la Jerarquía no se esconde nunca.
   - Lo que pedía Claude, ver Propiedades mientras se busca, queda como opción en Vista.
2. **Tamaño de letra.**
   - Claude proponía 13 px con suelo de 12. Astra, 14 px de cuerpo y filas de 32.
   - Se queda en 13 px, con suelo de 12 y filas de 30. La Jerarquía tiene 35 entidades y Propiedades muchos campos, y los editores de referencia son densos.
   - Las dos piden lo mismo en lo que importa: ningún texto de uso por debajo de 12 px.
3. **Edad de las conexiones.**
   - Claude la enseñaba solo cuando algo falla. Astra, siempre, porque D2 pide la edad.
   - Gana Astra. Para que quepa, las luces bajan a la barra de estado, como el estado del control de versiones en la barra inferior de Unreal 5.
4. **Nombre de Resetear.**
   - Claude proponía «Restablecer» y Astra «Vaciar del juego».
   - Se elige «Quitar del juego». «Restablecer» suena a volver a los valores de fábrica o al documento. «Vaciar del juego» suena a vaciar el juego entero, cuando solo se va lo de la escena.
5. **Menú de utilidades.**
   - Claude proponía «Más» (⋯). Astra, «Herramientas» con texto y el prototipo en otro menú.
   - Se queda «Herramientas» con texto, porque los menús del DayZ Editor llevan texto.
   - Las utilidades del prototipo quedan a la vista en un grupo aparte con borde discontinuo, porque quien revisa usa el simulador todo el rato.
6. **Barra de estado.**
   - Astra pedía llevar el MCP a «Detalles de sesión». CU-35 pide que la barra de estado diga que está apagado, así que se queda en la barra.
   - La versión exacta y el epoch se ven al pasar el ratón.
7. **El color del botón principal.**
   - UX-10 dejaba el ámbar solo para selección y foco, y el botón principal seguía blanco, como en el DayZ Editor.
   - Las tres lanes nuevas piden quitar el blanco. Muse y Gemini lo quieren ámbar; Grok, ámbar o el azul del Play de Unreal.
   - Gana el ámbar (UX-25). Ya es el acento de la interfaz, así que la acción principal y la selección se leen de la misma familia, y el rojo queda para Parar. El tono exacto lo fija el contraste de CU-38.
   - Para que el ámbar no sobre, hay una sola acción principal a la vista (Muse, MUM-17).
8. **Las luces, otra vez.**
   - Grok y Muse las quieren en un solo control, y Gemini quiere la edad solo cuando algo falla.
   - Se queda lo de §3.3: tres luces con nombre y edad, ahora abajo. Lo que tenían razón en pedir es que no parpadeen, y la edad pasa a segundos enteros.
9. **Dónde se para.**
   - Grok, Muse y Gemini señalan que Parar sale dos veces cuando rueda la toma.
   - Gemini propone ocultar el de la barra mientras la cabecera de toma está a la vista. Se hace al revés: se queda el de la barra, que no se mueve (B5), y la cabecera deja solo la acción que sigue.
10. **Vestuario y gestos en Añadir.**
    - Gemini los saca de Añadir (GEM-06). Muse deja las pestañas y añade un botón «Elegir un actor» (MUM-04).
    - Gana Gemini. Las propiedades del actor ya traen el vestuario y los gestos, así que las pestañas repetían lo mismo, y el Asset Browser de Eden solo lista lo que se coloca.
11. **Dos incoherencias que encontró Gemini.**
    - El §8.4 de octubre propone que los actores se muevan al mover el cursor de tiempo, pero el prototipo enseña la otra opción: solo sus marcas. Sigue siendo una decisión de Guillermo, y el consolidado de octubre lo dirá (UX-30).
    - Editar varias entidades por campos (CU-11) no falta por error: el consolidado de octubre ya lo dejó para F6 (§2, «Edición de varios a la vez»).

## 4. Qué cambia fuera del prototipo

- **El consolidado de octubre.** Se actualizan con esta lista:
  - §2: barra superior, paneles, Biblioteca, Consola y barra de estado.
  - §6: tipos, radios y densidad.
  - La tabla de referentes de la Guía.
  - §8.4: que el prototipo enseña la opción de las marcas mientras Guillermo no elija.
  
  §7 conserva sus 38 criterios, y §12 dice qué pruebas cambiaron.
- **`pruebas.js`.** Las comprobaciones de presentación se actualizan: «Aplicar escena» en vez de «Volver a aplicar», Actividad plegada, Añadir en pestaña y los textos nuevos. Las invariantes de operación y seguridad no se tocan. Las comprobaciones de esta lista van aparte, en `pruebas-mejoras.js`, para poder pasarlas también contra el prototipo de antes.

## 5. Fuera de M1 (R25)

Las cinco lanes coinciden en que nada de esto pide ampliar M1. Siguen fuera la vista 3D, grabar o controlar OBS, la colaboración, el cambio de mapa, el MCP, los eventos y una IA propia. Parar desde dentro de DayZ con una sola pantalla sigue como decisión aparte (consolidado de octubre, §10). Las lanes nuevas añaden a esta lista las composiciones guardables y un aspecto «de cine» con grano o claqueta en 3D (Gemini y Grok).

## 6. Segunda pasada: lo de DESPUÉS que no necesita el juego

Mientras Astra revisaba lo de AHORA, se hicieron tres mejoras de DESPUÉS que se pueden comprobar sin el juego: UX-18, UX-33 y UX-15. Astra no las ha revisado; entran en su siguiente revisión.

| ID | Qué se hizo | Criterio + | Criterio − |
|---|---|---|---|
| UX-18 | Con algo seleccionado, una línea arriba a la izquierda del mapa dice cómo moverlo y girarlo con el paso de la rejilla de ahora, y cómo borrarlo y duplicarlo con las teclas de ahora. Si está bloqueado, dice cómo desbloquearlo. Va en gris, para no confundirse con la de colocar. Las dos ayudas pasan a esa esquina porque, centradas, tapaban los botones del mapa a 1280 y 1440 px | Con «Bidón azul» seleccionado, la línea dice 0,5 m, 15°, Mayús y Supr. Con la rejilla a 1 m y Borrar reasignado a X, dice 1 m y X, y ya no Supr | Sin selección no hay línea. Colocando, la ayuda es la de colocar, sin la de edición. Con la toma armada no hay ayuda de edición. Ya se cumplía antes, porque no había ayuda de edición |
| UX-33 | La barra de estado lleva, entre las luces y el mundo, la X y la Z del cursor y el pueblo más cercano con su distancia («Stary Sobor, a 160 m»). El mapa ya no lleva las coordenadas en una esquina | Con el cursor sobre el mapa, la barra dice X, Z y el pueblo más cercano con su distancia, y el mapa no lleva coordenadas | Con el cursor fuera del mapa, la barra dice «X — · Z —» y ningún pueblo |
| UX-15 | «Nueva escena» abre una escena vacía con una cámara. La Jerarquía vacía invita con «Añade tu primer objeto», que abre Añadir. «Abrir…» lista las escenas de la sesión y marca cuál está en el juego. La cabecera avisa de que en el juego hay otra escena, y la nombran su ayuda, la línea de la Jerarquía y la ayuda de Aplicar. Aplicar otra escena quita la del juego y crea la nueva, con un paso que la nombra: es la recomendación de §8.5 del consolidado de octubre mientras Guillermo no elija. La Guía empieza por el recorrido en seis pasos con las teclas de ahora, y la procedencia, la paleta y los referentes pasan a «Acerca del diseño» | «Nueva escena» abre la escena vacía y su botón abre Añadir. La cabecera dice que en el juego hay otra escena, y la ayuda de Aplicar nombra «Amanecer en Stary Sobor». «Abrir…» lista las dos escenas, y al volver trae sus 35 entidades y sus 2 cambios sin aplicar. La Guía empieza por «Recorrido» con seis pasos, y la tabla de referentes va en «Acerca del diseño» | Crear y abrir escenas no manda órdenes al juego ni cambia lo que hay en él hasta aplicar; ya se cumplía antes, porque Nueva y Abrir no hacían nada. Con la toma armada no se crea ni se abre otra escena |

Límites (R25): Nueva y Abrir viven en la sesión del prototipo, sin guardar en disco, y «Guardar como» dice que no está en el prototipo. La escena nueva trae una cámara porque Rodaje necesita al menos una.

Pruebas: `pruebas-mejoras.js` da 51 de 51 contra el prototipo nuevo. Contra el de la primera pasada (`10274b7`) da 43 de 51: fallan los seis «+» nuevos y dos «−», y pasan los dos «−» que ya se cumplían. `pruebas.js` sigue en 64 de 64.

Dos fallos que encontró la prueba y ya están arreglados: un bloque de la Guía se había quedado dentro del fondo de los diálogos, que salía visible y anulaba los atajos, y la ayuda nueva tapaba los botones del mapa.

## 7. Revisión de Astra: hallazgos y arreglos

Astra revisó las mejoras AHORA (`10274b7`) en el PC de Guillermo, sobre una copia y sin ver la segunda pasada: [su informe](astra/2026-11-04-ui-revision-astra.md). Lo dio por NO APTO, con ocho hallazgos: cuatro que bloquean, dos de gravedad alta y dos de gravedad media. La mejora visual le parece real; pide arreglos concretos y pruebas que detecten estos fallos, no rehacer la interfaz. Su bloque DISENSO-FUERTE llegó literal a Guillermo. Deja de sostener como disenso los 13 px, «Quitar del juego» y el MCP en la barra de estado.

| ID | Gravedad | Qué fallaba | Qué se cambió | Criterio + | Criterio − |
|---|---|---|---|---|---|
| AR-01 | Bloquea | Si se cortaba Tu juego en plena toma, la parada quedaba sin confirmar, pero la Guía y los Atajos se abrían y tapaban «Parada sin confirmar», y «Reaplicar y preparar» mandaba una orden | Mientras falte confirmar la parada, la toma cuenta como abierta: la Guía y los Atajos no se abren, y Aplicar, Quitar del juego, Preparar y «Reaplicar y preparar» no mandan nada. Sus botones se apagan con una ayuda que dice por qué, y sus atajos lo avisan. Al volver la conexión, la lectura confirma la parada y todo vuelve | Tras cortar Tu juego rodando, ni la Guía (botón y ruta) ni los Atajos tapan «Parada sin confirmar», y no sale ninguna orden hasta leer el juego. Al volver la conexión, la lectura la confirma y Reaplicar vuelve | Un corte con un menú abierto no tapa «Parada sin confirmar», y ni el menú ni Esc la dan por confirmada sin lectura. Ya se cumplía |
| AR-02 | Bloquea | La Jerarquía decía «Nada en el juego» siempre que faltaba la lectura: mientras se aplicaba y tras un corte a mitad de crear, cuando no se sabe qué hay | Con una orden de escena en curso, la cabecera, la línea de la Jerarquía y Propiedades dicen «Aplicando: aún sin lectura» (o «Quitando»). Si se cortó, dicen «Falta confirmar qué hay en el juego», que se comprueba solo al volver la conexión, sin repetir la orden. «Nada en el juego» queda para una lectura o una retirada confirmada | Mientras se aplica, la Jerarquía dice que aún no hay lectura, y no «Nada en el juego». Aplicada y leída, dice qué hay y su edad; quitada y confirmada, «Nada en el juego» | Con la conexión cortada a mitad de crear, ni la cabecera, ni la Jerarquía, ni Propiedades dicen «Nada en el juego» ni Observado. Al volver se resuelve leyendo, sin repetir Aplicar |
| AR-03 | Bloquea | Los números de la rejilla se pintaban con tinta translúcida y sin fondo, y sobre un edificio bajaban a 2,03:1 en oscuro y 2,2:1 en claro. La prueba de contraste solo miraba el texto de la página, no el del mapa | Los números van sobre una placa opaca del color del halo de las etiquetas, y ese halo pasa a ser opaco. Desde la segunda medida, el halo es la letra repetida 2 px alrededor (ver abajo) | En los dos temas, a 1366 × 768 y en cuatro vistas (al abrir, con Mirek elegido, alejado y en Rodaje), cada texto pintado en el mapa llega a 4,5:1 en todos los píxeles de su letra | La sonda mide un número pintado como antes sobre un edificio y le da 2,03:1, como Astra, también si se pinta con strokeText: no da por bueno lo que fallaba |
| AR-04 | Bloquea | Las pruebas de UX-09 y UX-10 leían contadores que escribía la propia página (`data-etiquetas` y `data-borrador`), así que un dibujo roto pasaba | Se quitan los contadores. Las pruebas leen lo que se pinta de verdad con una sonda del lienzo: cada texto con su tamaño y su contraste, y cada trazo con su guion y su grosor. `mutantes.js` rompe el dibujo de cuatro maneras y comprueba que su prueba falla | UX-09 y UX-10 miran el dibujo: «Mirek · M1» pintado junto a sus marcas, lo cambiado con contorno discontinuo y sólido solo tras aplicar y leer, y ningún texto del mapa por debajo de 12 px | Cada mutante hace fallar su caso: borradores pintados sólidos, letra del mapa a 8 px, marcas sin «Mirek · M1» y números sin placa. Antes se pasan esos casos contra la página sin tocar, y pasan |
| AR-05 | Alta | En Tomas, el nombre de la cámara y la causa del final se leían a 10 px | Pasan a 12 px, y la prueba de UX-10 recorre también Tomas | En Tomas, la toma cortada y su causa se leen a 12 px o más | Ningún texto de uso baja de 12 px en Escena, Rodaje y sus paneles, Tomas incluida |
| AR-06 | Alta | «Ver» de un error elegía la entidad, pero dejaba Añadir delante y el campo que había que corregir oculto | «Ver» abre Propiedades y lleva el foco al campo del error: la X de una posición, el gesto, o el tiempo de una clave de cámara, que lleva a Rodaje. El código y el puntero siguen en Validación | Con Añadir delante, «Ver» de un error de posición abre Propiedades con la entidad elegida y el campo X a la vista y con el foco | «Ver» no cambia el documento, y en el error de una clave de cámara lleva a Rodaje con el tiempo a la vista y con el foco |
| AR-07 | Media | El contador de problemas de la tira no contaba las órdenes fallidas: decía «Sin problemas» con un «Aplicar escena» fallido | Cuenta los errores de validación y las órdenes fallidas o parciales sin resolver. Una orden queda resuelta cuando otra igual posterior se lee bien, o al aplicar y leer la escena entera | Un «Aplicar escena» que no se entregó cuenta como problema en la tira, y aplicar y leer después lo resuelve | Los fallos ya resueltos no mantienen la alarma: con fallos antiguos en Actividad, la tira dice «Sin problemas». Ya se cumplía |
| AR-08 | Media | El consolidado de octubre aún mandaba el botón principal blanco y la paleta del DayZ Editor, y atribuía a Unreal y Reforger la letra y los grises exactos | Las filas de octubre dicen qué rige ahora y qué sustituyen (§4, §6 y §9 de octubre). La Guía y la tabla de referentes separan el patrón que se copia (tema oscuro por capas, paneles acoplados y texto denso) de los valores, que son propios | Revisión del documento: una sola decisión vigente por tema, y el patrón separado de la adaptación | Ninguna fila manda el botón blanco ni atribuye a un referente una letra o un color exactos sin una fuente que lo diga |

**El contraste del mapa, píxel a píxel.** La sonda intercepta cada texto que se pinta en el lienzo, con fillText o con strokeText. Antes de dejarlo pintar, lo pinta una vez en blanco y otra en negro sobre lo que ya hay, y deja el fondo como estaba: la diferencia dice qué píxeles cubre la letra que pinta el propio lienzo. En cada píxel cubierto al menos a la mitad calcula el contraste de WCAG entre la tinta, con su transparencia, y lo que había debajo, y pide 4,5:1 en todos, sin margen. La sonda reproduce las cifras de Astra: 2,03:1 en oscuro y 2,21:1 en claro (ella midió 2,03 y 2,19).

**Segunda medida, en el PC de Guillermo.** La primera versión de la sonda daba un margen: bastaba con el 98 % de los píxeles de cada letra, porque junto al «·» y al punto de la «i» quedaban unos pocos píxeles por debajo aunque la letra se leyera bien. Antes de lanzar la segunda ronda de Astra se repitieron las pruebas en Windows, y AR-03 + falló en los dos temas: «Mirek · M1» y «Mirek · M2» tenían 3 de 136 y 137 píxeles por debajo de 4,5:1, un 2,2 %. Con eso falló también el control de los mutantes, y la ronda se paró hasta arreglarlo. Había dos causas:

- El halo se pintaba con strokeText, que solo traza el contorno de cada letra. Dentro de los contornos pequeños, como el «·» o el punto de la «i», quedaba un hueco sin halo, con el mapa debajo.
- La sonda no medía la letra real: la sacaba de un lienzo aparte, y un lienzo suelto elige en Chromium otra variante de la letra, más estrecha, así que su máscara no casaba con lo pintado.

Ahora el halo se pinta como imagen, con la letra repetida 2 px alrededor, en un lienzo oculto dentro de la página, que elige la misma variante que el mapa. La sonda mide la letra que pinta el propio mapa, y la regla pasa a ser todos los píxeles, sin margen. Contra `9d1a644`, AR-03 + falla ahora en los dos temas por dos cosas: el «·» deja un píxel a 4,43:1, que es el fallo de verdad, y la sonda mide como letra el halo de antes, pintado con strokeText en el color del fondo, y le da 2,46:1.

**Un fallo de la segunda pasada (UX-33).** Al comprobar la barra de estado a los anchos de portátil salió un fallo: a 1280 px las coordenadas tocaban el pueblo y «MCP apagado» tocaba la nota del prototipo, y a 1024 px, o a 1280 sin backend, «MCP apagado» se salía del borde (CU-35 pide que se vea). Ahora las coordenadas y el pueblo tienen un hueco fijo, para que nada se mueva al pasar el cursor. La nota del prototipo solo ocupa lo que sobra en la línea y se oculta a 1500 px o menos. Si las zonas no caben en una línea, la barra pasa a dos.

- Criterio +: a 1280 × 800 y 1366 × 768, con el cursor en 24 puntos del mapa, la barra es una línea que no cambia de alto, sus zonas no se pisan ni se mueven más de 1 px, y «MCP apagado» se ve entero.
- Criterio −: a 1024 × 768, y a 1280 × 800 sin backend, la barra pasa a dos líneas antes que pisar sus zonas o sacar «MCP apagado» del borde.

Lo de no moverse se añadió en la segunda medida. En Windows, contra `7e2e5c6`, el criterio + pasaba: con la letra de Windows las zonas no llegaban a pisarse a 1280 px, aunque se movían al pasar el cursor, que es justo lo que el arreglo quitó. Contra `7e2e5c6` se mueven hasta 123 px.

Pruebas:

- `pruebas-mejoras.js` da 66 de 66 contra el prototipo arreglado, con código de salida 0, también con la sonda estricta y el halo nuevo de la segunda medida (en este equipo: Linux y el Chromium de Playwright; la medida en Windows llega con la ronda de Astra).
- Contra `9d1a644`, los arreglos con el halo de contorno, da 64 de 66: solo falla AR-03 + en los dos temas, por lo dicho arriba.
- Contra el de antes de estos arreglos (`7e2e5c6`) da 54 de 66, con código de salida 1, y ningún caso se corta a medias. Fallan los ocho «+» de esta tanda: AR-01, AR-02, AR-03 en los dos temas, AR-05, AR-06, AR-07 y la barra. Fallan también cuatro «−»: AR-02, AR-06 (porque «Ver» no llevaba el foco al campo), UX-10 con Tomas y la barra.
- Allí pasan los «−» de AR-01 y AR-07, que ya se cumplían, y la comprobación de la sonda (AR-03 −). Pasan también los casos de UX-09 y UX-10 que ahora miran el dibujo, porque el dibujo ya estaba bien: lo que fallaba era la prueba. Que ahora la prueba sí lo mira lo demuestran los mutantes.
- `mutantes.js`: el control da 8 de 8 y los cuatro mutantes hacen fallar su caso, con código de salida 0, también tras la segunda medida.
- `pruebas.js`: 64 de 64, con código de salida 0.
- Otra queja de Astra era que contra la versión de antes algunos casos fallaban «por excepción», sin llegar a medir. Tres de los nuevos lo hacían: AR-01 + se quedaba parado en un clic que tapaba la Guía, y los dos de AR-06 buscaban un atributo nuevo. Ahora cierran la Guía si se abre y buscan «Ver» por la fila de su error, así que fallan diciendo qué está mal: «Guía abierta, Atajos abiertos, Parar tapado, Reaplicar libre» y «Propiedades detrás, X oculto».

Límites: la sonda mide el lienzo del prototipo en Chromium; el mapa del producto (Leaflet) tendrá que pasar la misma regla cuando exista. Astra no ha revisado aún la segunda pasada ni estos arreglos: entran en su siguiente revisión.
