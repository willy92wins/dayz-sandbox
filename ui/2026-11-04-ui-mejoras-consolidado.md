# Mejoras de la interfaz M1: las dos críticas juntas

2026-11-04 · Junta la crítica a ciegas de Claude ([2026-11-04-ui-critica-claude.md](2026-11-04-ui-critica-claude.md), problemas CC y mejoras MC) y la de Astra ([astra/2026-11-04-ui-critica-astra.md](astra/2026-11-04-ui-critica-astra.md), problemas AC y mejoras AM). Las dos se hicieron a la vez, sin ver la otra, sobre el prototipo del commit `de37c03`.

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

## 2. Lista con prioridad

AHORA se hace en esta pasada sobre el prototipo. DESPUÉS necesita más estados o una prueba con personas. NO se descarta, con su motivo. La columna «Propuso» dice de quién sale cada mejora: Claude, Astra, las dos, o la consolidación (lo decidido al juntar). Los criterios siguen R26: un caso positivo y uno negativo.

### AHORA

| ID | Qué cambia | Resuelve | Propuso | Referente | Criterio |
|---|---|---|---|---|---|
| UX-01 | Parar gana a todo durante la toma. Esc para aunque haya un menú, un diálogo o la Guía abiertos. La Guía y los Atajos no se abren con la toma armada o rodando. Si se pierde la conexión a mitad, Parar sigue en la barra como «Parada sin confirmar» hasta que una lectura lo confirme. Sin diálogo | AC-01 | Astra | Esc sale de la vista previa en el World Editor de Reforger ([wiki](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor)); Play y Stop fijos en la barra principal de Unreal 5 ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface)) | + Rodando con un menú abierto, un solo Esc para la toma, y Parar sigue a la vista y sin tapar. − Con la toma armada, la Guía y los Atajos no se abren; tras un corte no sale «Control devuelto» sin lectura |
| UX-02 | Paneles acoplados de borde a borde, con separadores de 1 px y sin huecos ni radios. A la derecha, Propiedades y Añadir en pestañas; en Vista se pueden fijar las dos a la vez. Abajo, Actividad plegada en una tira con la última orden (estado, edad y origen) y el número de problemas. En Rodaje la línea de tiempo sigue abierta | CC-01, CC-03, CC-05, AC-03, AC-05 | Las dos; Añadir a la derecha, Astra | Hierarchy, Object Properties y Log Console del World Editor de Reforger ([wiki](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor)); Asset Browser a la derecha en Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Asset_Browser)); Output Log y Content Drawer plegados abajo en Unreal 5 ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface)) | + El mapa ocupa ≥ 50 % de la ventana a 1440 × 900 y ≥ 45 % a 1366 × 768. − Con una orden Parcial, la tira plegada sigue diciendo Parcial con su edad |
| UX-03 | Barra de arriba en tres grupos. A la izquierda, el documento: nombre con su menú, «2 cambios sin aplicar», deshacer y rehacer. En el centro, los modos Escena y Rodaje. A la derecha, las acciones (Parar, Quitar del juego, Aplicar escena, Ir a rodaje) y un menú Herramientas (paneles, atajos y ocultar la interfaz). Las utilidades del prototipo (simulador, referentes y Guía) van aparte, con borde discontinuo. Las tres luces bajan a la barra de estado, con su nombre y su edad siempre a la vista; ahí van también el mapa, la versión del juego, «Escena sin errores» y «MCP apagado» | CC-08, CC-12, AC-02 | Las dos; las luces abajo y con edad, consolidación | Barra principal y barra inferior de Unreal 5, que enseña el estado del control de versiones ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface)); menús con texto del DayZ Editor ([wiki](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar)); modos arriba en el Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)) | + Como mucho 9 controles del producto en la barra a 1366 px; las tres luces con nombre y edad a 1280, 1366 y 1600 px. − Sin backend, las luces se ponen grises con «hace X» (CU-37) y la barra no dice «Sin errores» a secas |
| UX-04 | «Aplicar escena» como nombre fijo, y el número de cambios aparte. La ayuda dice antes del clic que recrea la escena entera. «Resetear» pasa a «Quitar del juego», con «el documento no cambia» en su ayuda y la confirmación de siempre | AC-07, CC-13 | Astra; «Quitar del juego», consolidación | Push Changes de UEFN separa lo editado de lo que corre ([docs](https://dev.epicgames.com/documentation/en-us/fortnite/first-island-04-playtest-your-island-in-fortnite)); que recrea la escena entera sale de #9 | + Con cambios, el botón dice «Aplicar escena» y la cabecera «2 cambios sin aplicar». − Con cero cambios se puede volver a aplicar, y nada va al juego sin pulsar Aplicar |
| UX-05 | Lo técnico, plegado. Fuera de la vista por defecto: la clase en las filas, ids, hashes, verbos de orden, epoch y versiones. Van en «Detalles técnicos» o al pasar el ratón. Los comportamientos se llaman «Quieto», «Recorrer una vez», «Repetir recorrido» y «Deambular», sin cambiar el valor guardado. En Validación va primero el mensaje y después el código. Los textos de uso no citan decisiones ni criterios | CC-02, CC-10, CC-11, AC-06, AC-13 | Las dos | Object Properties del World Editor separa la información de la entidad ([wiki](https://community.bistudio.com/wiki/Arma_Reforger%3AWorld_Editor)); resumen y detalle del error en el Session Inspector de UEFN ([docs](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector)) | + Escena recién abierta: como mucho 6 textos con jerga y 10 % del texto en monoespaciada. − Cada orden sigue enseñando su estado D2, su edad y su origen sin abrir nada; el documento guarda los mismos valores |
| UX-06 | Estado por excepción en la Jerarquía: sin icono cuando la entidad coincide con el juego, y con icono si es nueva o ha cambiado. Arriba, una línea dice qué hay en el juego y la edad de la lectura | CC-07 | Claude | PROPIO (#7), sobre la lista de entidades de Eden | + Con todo aplicado y leído, 0 iconos en las filas; con un cambio, 1. − La línea de arriba dice la edad de la lectura, o «Nada en el juego» si no hay nada |
| UX-07 | Siguiente paso a la vista. Aplicada y leída la escena, aparece «Ir a rodaje». Propiedades sin selección resume la escena (estado, contenido y ambiente) y dice qué toca, con el detalle técnico plegado | CC-06, CC-11, AC-08 | Claude | Scenario properties del Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)) | + Tras aplicar con éxito, «Ir a rodaje» lleva a Rodaje. − Con cambios sin aplicar no aparece, y sin selección no se ve ningún hash ni revisión |
| UX-08 | Añadir, con varios cambios: las categorías son pestañas con su cuenta; la búsqueda se conserva al cambiar de categoría y al volver; si no hay resultados, sale «Limpiar búsqueda»; el selector de clase enseña el nombre legible; el presupuesto va dentro, con «Tope total aún sin certificar». Tab con el mapa activo abre Añadir y Esc vuelve. Al colocar, lo nuevo queda seleccionado con sus propiedades a la vista (Ctrl + clic sigue colocando) | CC-05, AC-09 | Las dos | Entity Browser del Game Master: Tab, Esc, presupuesto dentro y Ctrl + clic ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)); búsqueda por nombre en Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor%3A_Entity_Placing)) | + Buscar «bidón», cambiar a Infectados y volver: la búsqueda sigue. − Al tope no se puede añadir, y el total sin certificar no se presenta como ilimitado |
| UX-09 | Mapa: marcadores un 25 % más grandes y con contorno. Las marcas y claves del seleccionado llevan su dueño («Mirek · M1», «Travelling del autobús · K1») y lo demás se atenúa. Hay una leyenda plegable dentro del mapa, y el candado se dibuja en vez de ser un emoji | CC-09, AC-10, AC-05 | Las dos | Mapa 2D de Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor%3A_Introduction)); claves de cámara de Replay Mod ([docs](https://www.replaymod.com/docs/#camera-paths)) | + Con Mirek seleccionado, sus marcas dicen «Mirek · M1», y la leyenda se abre sin salir del estudio. − Lo que está sin aplicar se sigue dibujando como documento, no como observado |
| UX-10 | Sistema visual: letra del sistema a 13 px con suelo de 12; monoespaciada solo en coordenadas y tiempos; filas de 30 px; una familia de iconos; radios de 0 en paneles, 4 en controles y 8 en lo que flota; sombras solo en lo que flota. Ámbar solo para selección y foco, y verde solo para evidencia: la cámara elegida deja de llevar el check verde | CC-03, CC-04, AC-04, AC-05 | Las dos; 13 px, consolidación | Notas de Unreal 5.0 sobre la interfaz ([docs](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5.0-release-notes?application_version=5.0#unreal-editor-interface)); los valores exactos están [sin verificar] | + Como mucho 15 % del texto visible por debajo de 12 px, y CU-38 sigue pasando en los dos temas. − Ningún texto de uso baja de 12 px para que algo quepa |
| UX-11 | Rodaje, en varias partes. Una cabecera de toma con número, cámara, estado, reloj y la acción que toca, sin la claqueta decorativa ni los cuatro pasos repetidos. Preparación resume «7 de 7 comprobaciones» con su edad y abre los fallos. La línea de tiempo se llama «Vista previa del mapa» y su botón «Previsualizar» no se parece a Rodar. La insignia dice «Rodando» y que el vídeo lo graba una herramienta externa | AC-12 | Astra | Sequencer de Unreal ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine)); Studio Mode de OBS ([guía](https://obsproject.com/kb/obs-studio-overview#studio-mode)); previa de caminos de Replay Mod ([docs](https://www.replaymod.com/docs/#camera-paths)) | + Previsualizar mueve solo la cámara del mapa. − No arma ni rueda, y una comprobación que falta impide Rodar |
| UX-12 | Los fallos dicen qué pasó, qué queda en el juego y qué hacer, sin perder las frases que fija el contrato: «No se entregó», «Falta confirmar el resultado» y «Reconciliada tras el corte» | AC-13 | Astra | Session Inspector de UEFN ([docs](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector)) | + Los tres fallos del simulador dejan causa, efecto y siguiente paso. − Un Parcial por respuesta perdida no ofrece «Reintentar» ni dice que no ocurrió |
| UX-13 | La edad de la evidencia va aparte de la de la petición: «Pedida hace…» y «Leída hace… · servidor», o «Sin lectura» | AC-14 | Astra | Duración frente a fecha de fin en el Session Inspector de UEFN ([docs](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector)); la edad de la muestra es de D2 y #23 | + Reconciliada tras un corte, la lectura es más nueva que la petición. − Un acuse sin lectura dice «Sin lectura», nunca «hace 0 s» |
| UX-14 | Textos: plurales bien; «Tu juego» en vez de «Director»; «Actividad» en vez de «Consola»; nada de `take` ni `scene_apply` a la vista. Los avisos salen de uno en uno, abajo en el centro del mapa | CC-12, CC-13, CC-14 | Claude | Avisos sobre la vista [sin verificar] | + Ningún texto visible con «1 gestos», «Resetear», `take` o `scene_apply`. − Los avisos no tapan Parar ni las pestañas de la derecha |

### DESPUÉS

| ID | Qué cambia | Resuelve | Propuso | Referente |
|---|---|---|---|---|
| UX-15 | Empezar desde una escena vacía: Nueva y Abrir funcionan, la escena vacía invita con «Añade tu primer objeto» y la Guía empieza por el recorrido (crear, aplicar, cámara, preparar, rodar y parar). La procedencia pasa a «Acerca del diseño» | AC-08, CC-06 | Las dos (AM-13, MC-12) | Guided Tour del Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)); New y Open del DayZ Editor ([wiki](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar)) |
| UX-16 | Etiquetas del mapa por prioridad (selección, toma, resto y geografía), con pueblos y controles en la reserva de sitio | AC-11 | Astra (AM-14) | Eden y Replay Mod; la regla exacta está [sin verificar] |
| UX-17 | Ayuda de cámara en tres pasos entre DayZ y el estudio | AC-16 | Astra (AM-15) | Cámara libre de COT ([Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=1564026768)) |
| UX-18 | Ayuda breve junto al mapa según lo seleccionado, con el paso de rejilla y las teclas reasignadas | AC-15 | Astra (AM-16) | Atajos del DayZ Editor ([wiki](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts)) |
| UX-19 | Miniaturas reales de cada clase en Añadir, capturadas en el juego y nunca generadas | CC-05 | Claude (MC-11), con el límite de Astra (AM-17) | Content Browser de Unreal ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/content-browser-in-unreal-engine)) |

### NO

| ID | Qué se descarta | Propuso | Motivo |
|---|---|---|---|
| UX-20 | Cambiar los nombres de los seis estados de D2 o juntarlos en un semáforo | Las dos (MC-13, AM-19) | Son contrato; se explican al pasar el ratón |
| UX-21 | Quitar las tres luces | Claude (MC-14) | CU-37 las pide; bajan a la barra de estado |
| UX-22 | Un cambio de marca con letra futurista, tarjetas grandes y transparencias, o acciones principales solo con icono | Astra (AM-17) | La mejora sale de la composición y la jerarquía |
| UX-23 | Un asistente con «Aceptar» en cada lectura, o preparar por partes | Astra (AM-18) | #4 pide una sola preparación |
| UX-24 | Paleta de comandos | Claude (MC-15) | Fuera por R25 desde octubre |

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

## 4. Qué cambia fuera del prototipo

- **El consolidado de octubre.** Se actualizan con esta lista:
  - §2: barra superior, paneles, Biblioteca, Consola y barra de estado.
  - §6: tipos, radios y densidad.
  - La tabla de referentes de la Guía.
  
  §7 conserva sus 38 criterios, y §12 dice qué pruebas cambiaron.
- **`pruebas.js`.** Las comprobaciones de presentación se actualizan: «Aplicar escena» en vez de «Volver a aplicar», Actividad plegada, Añadir en pestaña y los textos nuevos. Las invariantes de operación y seguridad no se tocan. Se añaden las comprobaciones de esta lista.

## 5. Fuera de M1 (R25)

Las dos lanes coinciden en que nada de esto pide ampliar M1. Siguen fuera la vista 3D, grabar o controlar OBS, la colaboración, el cambio de mapa, el MCP, los eventos y una IA propia. Parar desde dentro de DayZ con una sola pantalla sigue como decisión aparte (consolidado de octubre, §10).
