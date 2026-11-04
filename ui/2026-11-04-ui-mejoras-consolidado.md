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

**Estado:** las mejoras AHORA están en el prototipo y el consolidado de octubre ya está al día. Sus criterios pasan en [prototipo/pruebas-mejoras.js](prototipo/pruebas-mejoras.js) (41 de 41) y fallan contra el prototipo de antes; el detalle está en la §12 del consolidado de octubre. Falta la revisión cruzada de Astra.

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

Pruebas: `pruebas-mejoras.js` da 51 de 51 contra el prototipo nuevo. Contra el de la primera pasada (`10274b7`) da 43 de 51: fallan los siete «+» nuevos y dos «−», y pasan los dos «−» que ya se cumplían. `pruebas.js` sigue en 64 de 64.

Dos fallos que encontró la prueba y ya están arreglados: un bloque de la Guía se había quedado dentro del fondo de los diálogos, que salía visible y anulaba los atajos, y la ayuda nueva tapaba los botones del mapa.
