# Interfaz web del MVP de cine (M1): consolidado de Claude y Astra

2026-10-28 · Junta las dos lanes ciegas del [brief común](2026-10-28-ui-m1-brief.md): la de [Claude](2026-10-28-ui-m1-claude.md) y la de [Astra](astra/2026-10-28-ui-m1-astra.md) (Codex), por decisión de Guillermo («que la UI se haga entre Astra y tú»). Contrato: [product-spec.md](../product-spec.md) y el plan cerrado [plans/2026-10-26-m1-cine-v2.md](../plans/2026-10-26-m1-cine-v2.md). Si este documento choca con cualquiera de los dos, ganan ellos.

**Noviembre:** el 2026-11-04 se aplicaron las mejoras AHORA de la [lista de las cinco críticas](2026-11-04-ui-mejoras-consolidado.md) (UX-01 a UX-14 y UX-25), una segunda pasada (UX-18, UX-33 y UX-15) y los arreglos de la revisión de Astra (AR-01 a AR-08). El 2026-11-05 entraron la rueda (UX-44 y UX-45) y tres decisiones de Guillermo sobre la sección 8 (UX-30, UX-46 y UX-47), y después los arreglos de la segunda revisión de Astra (AR2-01 a AR2-07). El 2026-11-09, la revisión visual (VIS-01 a VIS-13). El 2026-11-10, los arreglos de la tercera revisión de Astra (AR3-01 a AR3-05), el icono de cada tipo de objeto (UX-48) y la vista previa al escoger en Añadir (UX-49). Este documento ya describe la interfaz con esos cambios; qué se decidió y por qué está en esa lista.

El diseño navegable es [prototipo/estudio.html](prototipo/estudio.html): una sola página con datos de ejemplo, sin backend, con un simulador de fallos del juego. Sus pruebas están en [prototipo/pruebas.js](prototipo/pruebas.js), y los criterios de las mejoras de noviembre en [prototipo/pruebas-mejoras.js](prototipo/pruebas-mejoras.js). La Guía del prototipo (botón «Guía») enseña la misma tabla de referentes que la sección 9.

**Estado:** consolidado, mejorado en noviembre y probado en el navegador. Astra lo ha revisado ocho veces, y las ocho veces lo dio por NO APTO: con 8 hallazgos el 4 de noviembre, con 7 el 5, con 5 el 10, con 6 el 11, con 5 otra vez el 11, con 3 el 12, con 2 otra vez el 12 y con 1 el 13. Cada ronda miró los arreglos de la anterior, y lo que encontró a medias pasó a ser un hallazgo nuevo. La cuarta miró también los iconos y la vista previa del 10 de noviembre y el arreglo de tres textos del mapa que quedaban tapados o cortados. La octava, declarada la última, dio AR7-02 por arreglado y AR7-01 a medias, con un hallazgo de la prueba (AR8-01) que está arreglado y probado con sus propios HTML como mutantes; Guillermo pidió arreglarlo y mergear sin otra ronda (sección 11). Nada de esto toca el código de F0 ni el bridge.

## 1. Cómo se consolidó

- Las dos lanes recibieron el mismo brief y la regla de referentes de Guillermo («no lo hagáis a vuestro estilo, mirad lo que funciona»), sin ver la otra.
- Cada parte de la interfaz sale de un juego o una herramienta que ya funciona, con su fuente. Cuando las lanes diferían ganó el referente de prioridad más alta (1 DayZ Editor, COT y el mapa del juego; 2 Eden, Zeus, World Editor y Game Master de Reforger; 3 Rockstar Editor, Replay Mod, Fortnite y SFM; 4 Unreal, UEFN, Roblox y Blender; 5 el transporte de un DAW y OBS), salvo choque con el spec.
- Lo que solo existe en este producto va marcado PROPIO, con el criterio del spec que lo pide y el patrón conocido más cercano.
- La columna «Propuso» dice de dónde sale cada parte: **Claude**, **Astra**, **Las dos** (las dos lanes llegaron a lo mismo) o **Consolidación** (ninguna lo tenía así: salió al juntarlas o al probar el prototipo). Desde noviembre también salen **Grok**, **Muse** y **Gemini 4**, las tres lanes que propusieron mejoras a ciegas, y **Las cinco** cuando coinciden todas; si cada una puso una parte, van sus nombres juntos. **Guillermo** es lo que pidió él. De las 70 filas de la sección 9: Las dos 23, Astra 17, Claude 12, Consolidación 6, Guillermo 4 y Gemini 4 una; las otras siete juntan nombres (Grok, Muse y Gemini 4, dos; Consolidación, Gemini 4 y Grok; Astra y Gemini 4; Claude y Astra; Gemini 4 y Muse; y Las cinco).

## 2. Arquitectura de la información

Un chasis común y dos modos, como el Game Master de Reforger cambia entre Game Master y Armavision.

- **Paneles acoplados** de borde a borde, con separadores de 1 px y sin huecos ni radios, como en el World Editor de Reforger y en Unreal 5 (UX-02).
- **Barra superior (los dos modos), en tres grupos (UX-03):** a la izquierda, el documento: su nombre con el menú de escena (nueva escena y abrir, UX-15), «2 cambios sin aplicar» y la edad del guardado (la revisión, al pasar el ratón), deshacer y rehacer. En el centro, Escena y Rodaje con su tecla (`1`, `2`). A la derecha, las acciones: Quitar del juego, Aplicar escena, «Ir a rodaje» cuando la escena está aplicada y leída (UX-07) y el menú Herramientas (paneles, layouts, atajos y ocultar la interfaz). Aparte, con borde discontinuo, lo que solo existe en el prototipo: el simulador, los referentes y la Guía. Durante la toma se esconden Quitar del juego y Aplicar escena y aparece Parar (o Desarmar) con su tecla; tras un corte se queda como «Parada sin confirmar» hasta leer el juego, y hasta entonces no se abren la Guía ni los Atajos ni sale ninguna orden (UX-01, AR-01). Nunca hay dos acciones principales a la vista (UX-25).
- **Escena:** Jerarquía a la izquierda, con una línea arriba que dice qué hay en el juego y la edad de la lectura, o que falta la lectura mientras se aplica o tras un corte (UX-06, AR-02); mapa en el centro, con la leyenda plegable dentro y, con algo seleccionado, una línea arriba a la izquierda que dice cómo moverlo, girarlo (también con la rueda encima, UX-44) y borrarlo con la rejilla y las teclas de ahora (UX-18); a la derecha, Propiedades y Añadir en pestañas, o las dos a la vez desde Herramientas, con el presupuesto dentro de Añadir (UX-08) y, encima de él, la vista previa de lo que se va a colocar: su imagen, su tamaño y su planta a escala (UX-49); abajo, Actividad, Historial y Validación, plegados en una tira con la última orden (estado, edad y origen) y el número de problemas: errores de validación y órdenes fallidas o parciales sin resolver (UX-02, AR-07).
- **Rodaje:** Cámaras y Tomas a la izquierda; encima del mapa, la cabecera de toma con su número, la cámara, el estado, el reloj y la acción que toca (Preparar, Rodar o Reaplicar y preparar), que nombra la comprobación que falla y ofrece su arreglo; abajo, la Vista previa del mapa y Actividad, abiertas; con el cursor de tiempo movido, cada actor con recorrido se ve también rayado donde estaría (UX-30); a la derecha, Preparación («7 de 7 comprobaciones» con su edad, y los fallos abiertos) y Propiedades (UX-11).
- **Barra de estado, que no se toca:** las luces Backend, Servidor y Tu juego con su nombre y su edad en segundos enteros; la X y la Z del cursor y el pueblo más cercano con su distancia (UX-33); el mapa (el epoch, al pasar el ratón), la versión del juego y si Expansion está cargado; la validación («Escena sin errores», o «sin validar» si falta el backend) y «MCP apagado» (UX-03). Si no cabe en una línea, pasa a dos antes que pisar algo.
- **Tres capas que nunca se mezclan:** el documento (lo que se edita; vive en el backend, #7), el juego (lo que hay de verdad, con su edad y su origen) y la toma (lo que se rueda).

## 3. Flujos

1. **Preparar la escena.** Añadir, por tipo (Tab con el mapa activo la abre y Esc vuelve): clic en el nombre y clic en el mapa (Ctrl + clic para seguir colocando, clic derecho cancela), o Intro, que lo pone en el centro del mapa. Al pasar el ratón o el foco por la lista, la vista previa enseña la captura de cada clase, su tamaño y su planta a escala, y al colocar un objeto su planta va bajo el cursor, a la escala del mapa (UX-49). Lo nuevo queda seleccionado con sus propiedades a la vista. Al colocar se lee el suelo en el servidor y Propiedades enseña la altura leída con su edad. Se mueve arrastrando, con las flechas (Alt, 0,1 m) o escribiendo X y Z; se gira con Mayús + arrastrar o escribiendo el rumbo. Las rejillas de movimiento y de giro se encienden y se apagan. Cada cambio es una transacción con nombre en el Historial (A5) y se guarda al momento.
2. **Aplicar.** `Ctrl+Intro` o «Aplicar escena». La orden pasa por validar, reservar presupuesto, quitar lo que había, crear por lotes, leer y publicar (#9). Su fila en Actividad dice el estado de D2, el paso en curso, el origen y la edad de la petición y, aparte, la de la lectura (UX-13). Solo una lectura la deja en Observado; si la respuesta se pierde después de entregarla, queda Parcial («Falta confirmar el resultado») y se reconcilia leyendo al volver la conexión (#23). Mientras no hay lectura, la Jerarquía y Propiedades lo dicen, y nunca «Nada en el juego» (AR-02).
3. **Rodar.** En Rodaje, `Mayús+F9` o «Preparar toma» lee el juego: escena aplicada y observada, tu juego conectado, cámara lista con su hash, vestuario, actores en su marca, hora y clima, y HUD. Cada lectura es una fila con su resultado y su arreglo («Reaplicar y preparar»), y la cabecera de toma nombra la que falla. Solo con todo bien queda Armada, y entonces Intro rueda. La barra superior late y la insignia dice «Rodando» y que el vídeo lo graba una herramienta externa, como OBS.
4. **Parar.** `Esc`, `Espacio` o Parar, fijo en la barra de arriba. `Esc` para aunque haya un menú, un diálogo o la Guía abiertos, y la Guía y los Atajos no se abren durante la toma ni mientras falte confirmar su parada (UX-01, AR-01). La toma queda en «Parando…» hasta que tu juego lo confirma, y Tomas apunta el control devuelto en segundos (B5 pide menos de 1 s). Con la toma armada, `Esc` desarma; `Espacio` nunca rueda. Desde dentro del juego la para la tecla «Parar toma» del mod de cliente, y la cabecera de la toma lo dice con su tecla (UX-46).
5. **Quitar y repetir.** Tras una toma, «Reaplicar y preparar» aplica la escena entera y vuelve a armar (B6). «Quitar del juego» quita todo lo de la escena y deja el documento como estaba.
6. **Recargar.** «Recargar desde disco» y «Leer el juego ahora» están en las propiedades de la escena. Recargar la página vuelve a pintar lo último que da el backend.
7. **Cuando algo se cae.** Sin servidor, las órdenes nuevas se quedan Pendiente y caducan a Fallido «No se entregó». Sin backend, las luces quedan en gris con «hace X», un aviso lo dice, Actividad enseña «lo último que se supo» y no se puede guardar ni aplicar nada. Si se pierde tu juego o el backend durante la toma, la toma falla, su orden queda Parcial explicando el hombre muerto del mod (F5: para la cámara y los actores por seguridad), Parar se queda como «Parada sin confirmar» y todo se reconcilia al leer. Si el servidor se reinicia, aviso de mundo nuevo con el epoch nuevo hasta volver a aplicar.

## 4. Decisiones de la consolidación

Solo donde las lanes diferían o donde la prueba del prototipo cambió algo. El resto coincidía. En noviembre cambiaron cinco filas: la paleta y el botón principal (grises fríos y ámbar, UX-25), la letra (13 px, UX-10), la insignia («Rodando», UX-11) y las luces (abajo, con Tu juego en vez de Director, UX-03 y UX-14). En esas filas, «Queda» dice lo vigente y lo de octubre que sustituye. El porqué está en la §3 de la [lista de mejoras](2026-11-04-ui-mejoras-consolidado.md).

| Parte | Claude | Astra | Queda | Por qué |
|---|---|---|---|---|
| Paleta | Chasis oscuro verdoso con acento ámbar, paleta propia | Los tonos de la barra del DayZ Editor medidos en su captura pública (#0F0F0F, #1E1E1E, #FFFFFF) | Noviembre (UX-25): grises fríos por capas, con el mapa topográfico de Claude. Sustituye a la de Astra de octubre | Para el aspecto, Guillermo prefiere los editores de Reforger y Unreal 5 al DayZ Editor. De ellos se copia el patrón (superficies oscuras, cada capa un paso más clara); los valores de §6 son propios, ajustados al contraste |
| Letra | Chakra Petch, IBM Plex Sans y Plex Mono, títulos en versalitas | Letra del sistema, sin mayúsculas forzadas | Astra, a 13 px desde noviembre (UX-10) | Los menús del DayZ Editor van en minúscula normal; su familia exacta no está verificada, así que no se copia ninguna. La letra del sistema y los 13 px son una elección propia, no copiada de un referente |
| Botón principal | Ámbar | Blanco, como el texto y los iconos activos del DayZ Editor | Noviembre (UX-25): ámbar, con una sola acción principal a la vista. Sustituye al blanco de octubre | Grok, Muse y Gemini pidieron quitar el blanco. El ámbar ya era el acento, así que la acción principal y la selección se leen de la misma familia, y el rojo queda para Parar (§3.7 de la lista de mejoras) |
| Rodar | `Espacio` arranca y para (REAPER, Blender) | `Intro` con la toma armada (vista previa de Eden) | Astra | Eden (2) gana al DAW (5) |
| Parar | `Esc` (vista previa del World Editor de Reforger) | `Espacio` (Ableton) | Las dos: `Esc` para y desarma; `Espacio` solo para la toma que rueda | Reforger (2) da la tecla principal; `Espacio` se queda porque B5 pide parar siempre, pero nunca arranca, para que una pulsación suelta no ruede |
| Preparar | Sin tecla | `Mayús+F9` (armar la grabación en Ableton) | Astra | D4 pide atajo para la toma |
| Colocar sin ratón | `Intro` pone lo elegido en el centro del mapa (PROPIO por D4) | `F1` abre los objetos (Eden), luego Tab, coordenadas e Intro | Claude | En Eden `F1` cambia de pestaña en el Asset Browser, no coloca; aquí la Biblioteca está siempre abierta. Las coordenadas se escriben después en Propiedades |
| Propiedades | `Ctrl+T` (DayZ Editor) | `Ctrl+T` (DayZ Editor) | `Alt+Intro` (Explorador de Windows) | Chromium atiende `Ctrl+T` antes que la página; igual `Ctrl+N`, así que Nueva escena va sin tecla |
| Girar | Campo de rumbo; manija de giro como propuesta | Mayús + arrastrar (Eden) | Astra, y el campo sigue como alternativa de D4 | Eden (2) |
| Mover el mapa | Arrastrar con el izquierdo en vacío (Leaflet) | Botón derecho y arrastrar (Eden) | Las dos | Eden para el gesto; el de Leaflet no estorba y es el que trae #20 |
| Rejillas | Pasos fijos | Rejillas de traslación y de giro que se encienden y se apagan (barra de Eden) | Astra, con pasos propios (0,1 a 10 m y 1° a 90°) | Eden; sus valores de serie no están verificados |
| Reasignar atajos | Aviso de conflicto como Foundry VTT | Reemplazar o Cancelar, como Unreal | Astra | Foundry no está en la lista de referentes |
| Teclas obligatorias | Se podían quitar | Las cuatro de D4 no se quedan sin tecla | Las dos, con cinco: Colocar, Aplicar, Preparar, Rodar y Parar | D4 |
| Aplicado (D2) | Anillo con marca | Cuadrado de contorno, sin marca, «por observar» | Anillo con un punto, sin marca | Astra acierta en que una marca se lee como hecho; la forma redonda sigue la familia de los otros estados |
| Fallido (D2) | Rombo con aspa | Octágono con cruz | Astra | El octágono se lee como alto sin color |
| Parada | El control vuelve al momento | «Parada solicitada; falta confirmar el control» | Astra: «Parando…» hasta que confirma el cliente, y Tomas mide el control devuelto | B5 y #23: nada se da por hecho sin lectura |
| Rodando | Insignia REC que parpadea | Sin REC, «Vídeo externo: OBS» | Noviembre (UX-11): «Rodando», y que el vídeo lo graba una herramienta externa, como OBS. Sustituye a «RODANDO · El vídeo lo graba OBS» | Grabar vídeo está fuera de M1; sin mayúsculas forzadas (UX-10) |
| Estado de la toma | En la misma pastilla que D2 | Dimensión aparte de los seis estados | Astra: cada toma lleva su etiqueta (Terminada, Parada, Fallida) | Una toma parada no es una orden observada |
| Luces de conexión | Servidor y Director | Backend, Servidor y Director, con su edad | Astra, en la barra de estado y con «Tu juego» en vez de Director desde noviembre (UX-03, UX-14) | #7: el documento vive en el backend |
| Backend caído | No estaba | Datos con su edad, sin color; nada se guarda | Astra, más el aviso y la Consola congelada | D2 y #7 |
| Presupuesto | Medidores por tipo (20, 10, 3 y 2) | Además el total con prendas e hijos, que fija S-perf | Las dos | A6 y #28: sumar los máximos no es el tope combinado |
| Ambiente | Cambiar hora y clima solo editaba el documento | «Probar ambiente» lo cambia en vivo | Astra | El DayZ Editor cambia hora y clima en vivo; aquí hace falta el botón porque editar no toca el juego (#7) |
| Suelo al colocar | El mod resuelve la altura al crear | Lecturas cortas dentro de la mezcla de E2 | Consolidación: «Leer el suelo» al colocar, con su edad | D5 (< 0,2 m) y E2 (25 consultas de suelo en la mezcla) |
| Trayectoria de cámara | Curva Catmull-Rom en el mapa | Guía de claves rotulada, nunca una curva «exacta» | Las dos: se dibuja la curva y se rotula «trayectoria prevista (#16)»; la vista previa dice que no mueve el juego | #16 pone la interpolación en el cliente; la web no la mide |
| Editar mientras hay una orden | Nada se bloquea | Se bloquea lo incompatible mientras Aplicar o Preparar usan una revisión | Bloqueo de Preparar a Parando; durante Aplicar se sigue editando y la orden lleva su revisión | Pendiente de la revisión de Astra (sección 11) |
| Propiedades | Cada cambio al momento, deshacer con Ctrl+Z | Aceptar y Cancelar (Atributos de Eden) | Claude | El panel está siempre abierto y cada cambio ya es una transacción que se deshace (A5); el Aceptar de Eden es de una ventana. Pendiente de la revisión de Astra |
| Buscar en la Biblioteca | Campo de búsqueda | `Ctrl+F` con el foco en la Biblioteca o el mapa (Eden) | Claude | `Ctrl+F` taparía la búsqueda del navegador y el campo ya está a la vista |
| Cámara libre | «Nueva cámara desde la cámara libre» | `Insert` la enciende (COT) | Claude en la web; `Insert` es del mod del cliente | La cámara libre vive en el juego (#17); una tecla de la web no llega con DayZ en primer plano |
| Edición de varios a la vez | Mover y girar el grupo | Los valores mixtos no se sobrescriben sin activarlos (Eden) | Criterio para F6 (CU-11) | El prototipo no edita campos de varios a la vez |

## 5. Atajos y gestos por defecto

| Acción | Tecla | De dónde sale |
|---|---|---|
| Colocar lo elegido en el centro del mapa (siempre con tecla, D4) | `Intro` | Propio (D4): alternativa al clic en el mapa |
| Aplicar la escena al juego (siempre con tecla, D4) | `Ctrl+Intro` | Propio: el Push Changes de UEFN no documenta tecla |
| Preparar la toma (siempre con tecla, D4) | `Mayús+F9` | Armar la grabación (Mayús+F9): Ableton Live |
| Rodar la toma armada (siempre con tecla, D4) | `Intro` | Intro arranca la vista previa: Eden |
| Parar la toma, o desarmarla (siempre con tecla, D4) | `Esc` | Esc sale de la vista previa: World Editor de Reforger |
| Parar la toma que rueda | `Espacio` | Espacio para el transporte: Ableton Live (aquí nunca arranca) |
| Deshacer | `Ctrl+Z` | DayZ Editor |
| Rehacer | `Ctrl+Y` | DayZ Editor y World Editor de Reforger |
| Abrir escena | `Ctrl+O` | DayZ Editor |
| Guardar | `Ctrl+S` | DayZ Editor |
| Guardar como | `Ctrl+Mayús+S` | DayZ Editor |
| Borrar lo seleccionado | `Supr` | DayZ Editor y Eden |
| Duplicar | `Ctrl+J` | DayZ Editor |
| Seleccionar todo | `Ctrl+A` | DayZ Editor |
| Ir a las propiedades | `Alt+Intro` | Propiedades (Alt+Intro): Explorador de Windows; el Ctrl+T del DayZ Editor lo atiende el navegador |
| Bloquear | `L` | DayZ Editor |
| Desbloquear | `Ctrl+L` | DayZ Editor |
| Copiar coordenadas | `P` | Copy Object Coords: DayZ Editor |
| Ocultar la interfaz | `Y` | Toggle UI: DayZ Editor |
| Encuadrar la selección | `F` | Focus: World Editor de Reforger |
| Ver la trayectoria prevista de las cámaras | `H` | Toggle Path Preview: Replay Mod |
| Ir a Escena | `1` | Propio |
| Ir a Rodaje | `2` | Propio |

Gestos del mapa: clic selecciona; Ctrl + clic añade o quita; Mayús + clic selecciona seguidos (DayZ Editor). Arrastrar mueve lo seleccionado; Mayús + arrastrar lo gira (Eden). Botón derecho y arrastrar mueve el mapa y la rueda acerca (Eden); con el ratón encima de lo seleccionado, la rueda lo gira con la rejilla de giro, y con Alt de grado en grado (propio, UX-44). La rueda encima de un campo numérico lo sube o lo baja un paso, y con Mayús diez (OBS, UX-45). Con Ctrl o Cmd, la rueda es del navegador, que amplía la página: ni gira lo elegido ni acerca el mapa (AR2-04). Mayús + clic derecho añade una marca al actor elegido (Eden). Las flechas mueven lo seleccionado con el paso de la rejilla y Alt mueve fino, 0,1 m y 1° (DayZ Editor). Lo bloqueado no se arrastra.

Reglas: los atajos no actúan mientras se escribe en un campo (`Esc` deshace lo escrito y `Ctrl+Intro` aplica). Una tecla mantenida no repite Aplicar, Preparar ni Rodar. `Intro` coloca mientras se está colocando y rueda con la toma armada: los dos contextos nunca coinciden. Los atajos son de la web y no llegan con DayZ en primer plano; desde el juego, la toma se para con la tecla «Parar toma» del mod de cliente (C-16, resuelto el 2026-11-05: UX-46).

## 6. Lenguaje visual

Base: grises fríos por capas (UX-25). Del editor de Unreal 5 y del World Editor de Reforger se copia el patrón, superficies oscuras con cada capa un paso más clara; los valores de esta tabla son propios, ajustados para el contraste. El chasis, el panel, el campo y el realce van un paso más claros cada uno, con líneas de 1 px. Del DayZ Editor se quedan los grupos separados por líneas y los menús con texto. El mapa es papel topográfico, como el mapa 2D de Eden, y es la única superficie de papel. Los dos temas salen de los mismos tokens.

| Token | Oscuro | Claro | Uso |
|---|---|---|---|
| `--chassis` · `--bg` | `#111216` · `#16171b` | `#d8dbe0` · `#eceef1` | Chasis, separadores y barras, y la cabecera y las pestañas de cada panel (VIS-04) |
| `--surface` · `--surface-2` · `--surface-3` | `#1c1e23` · `#25272d` · `#2f3239` | `#f7f8fa` · `#ffffff` · `#e3e6ea` | Paneles, campos y realces |
| `--line` · `--line-strong` | `#2a2d33` · `#3b3f47` | `#d5d8dd` · `#bbc0c7` | Bordes |
| `--fg` · `--fg-2` · `--muted` · `--faint` | `#ebedf0` · `#c4c8cf` · `#9a9fa9` · `#6b707a` | `#15171b` · `#3a3e45` · `#5d626b` · `#8c919a` | Texto; `--faint` solo en lo desactivado y en iconos |
| `--primary` con `--primary-ink` | `#e9aa3c` con `#1b1306` | `#dc992e` con `#1b1306` | La acción principal, una sola a la vista: Aplicar escena, Ir a rodaje o la de la cabecera de toma. Apagada no lleva ámbar: va como cualquier botón apagado (VIS-05) |
| `--accent` | `#e9aa3c` | `#865106` | Selección, foco, tope alcanzado y paso actual |
| `--rec` | `#d24137` | `#cc3226` | Rodando y Parar |
| `--cam` | `#71a8ee` | `#2459a6` | Cámaras y claves |
| `--st-pend` · `--st-exec` · `--st-appl` · `--st-obs` · `--st-fail` · `--st-part` | `#a0a0a0` · `#6fb2ee` · `#5fc6ba` · `#82c662` · `#f27468` · `#eb8d3a` | `#616161` · `#2563a0` · `#0f6d63` · `#306e1c` · `#b22e23` · `#984c0b` | Estados de D2 |
| `--st-draft` | `#d4cba9` | `#696249` | Nuevo o cambiado en el documento |
| `--st-ink` | `#111216` | `#FFFFFF` | Texto sobre un relleno de estado (contadores y pasos) |
| `--g-obj` · `--g-zmb` · `--g-ani` · `--g-act` | `#cfc7aa` · `#d3836c` · `#c6a767` · `#f5f2e8` | `#5b5446` · `#a8432f` · `#86691c` · `#1d1f19` | Objeto, infectado, animal y actor en el mapa |

- **Letra:** la del sistema a 13 px, con un suelo de 12 para cualquier texto de uso, también lo que se pinta en el mapa (Segoe UI Variable y Cascadia Mono en Windows). La familia y el tamaño son una elección propia: ningún referente comprobado los fija. La monoespaciada, solo en coordenadas y tiempos, y las cifras de tiempos, coordenadas y edades son tabulares. Títulos sin mayúsculas forzadas (UX-10).
- **Densidad y formas:** filas de 30 px; radio 0 en los paneles, 4 en los controles y 8 en lo que flota (menús, diálogos y avisos); sombra solo en lo que flota; una sola familia de iconos. El ámbar es para la selección, el foco y la acción principal, y el verde solo para lo leído en el juego: la cámara elegida lleva una etiqueta neutra (UX-10). Los controles de la barra de arriba miden todos 30 px (VIS-08). Dentro de un botón o de un menú, la tecla va en texto tenue y sin caja; en el texto corrido sigue en su caja (VIS-10). Las barras de desplazamiento son finas y tenues (VIS-03).
- **Movimiento:** solo gira Ejecutando y late la barra superior al rodar; con `prefers-reduced-motion` no se mueve nada.
- **Contraste:** todo texto visible pasa WCAG 2.1 AA (criterio 1.4.3: 4,5:1, o 3:1 si es grande) en los dos temas, también sobre las rayas de Parcial y dentro de Parar. Los valores de esta tabla ya están ajustados para eso (CU-38). En el mapa, los números de la rejilla van sobre una placa opaca y las etiquetas con un halo opaco de 4 px, porque pasan por encima de edificios y bosque. Las etiquetas se pintan al final, encima de los marcadores, y buscan un sitio donde no tapen ninguno; en un grupo denso, una que tiene que salir puede quedar hasta a 42 px de su marcador o, si no hay sitio libre, tapar uno (AR3-01, con sus límites en la §11 de la lista de noviembre). Los números de la regla van encima de los marcadores, y ningún texto del mapa, salvo los pueblos, va bajo lo que flota encima ni cortado por su borde (UX-50). Lo que flota arriba del mapa (la ayuda, «Rodando» y el zoom) empieza debajo de los números de la regla de X, para no taparlos (VIS-09).

**Estados de una orden (D2), por forma además de color.** Es PROPIO (D2 y #23), apoyado en la cola de comandos de DZ Commander y en el Session Inspector de UEFN.

| Estado | Forma | Qué quiere decir |
|---|---|---|
| Pendiente | Anillo discontinuo | Validada en el backend; ningún mod la ha recogido. Si caduca sin entregarse, pasa a Fallido «No se entregó» |
| Ejecutando | Anillo tenue con un arco que gira | El mod la recogió y la está haciendo; dice el paso |
| Aplicado | Anillo con un punto, sin marca | El mod confirma que la hizo; falta leer el juego |
| Observado | Disco lleno con marca | Una lectura posterior lo confirma |
| Fallido | Octágono lleno con aspa | No se hizo, o la lectura no cumple; dice por qué |
| Parcial | Círculo medio lleno | Falló a mitad, o se perdió la respuesta después de entregarla. Sigue así hasta reconciliar: nunca vuelve a «no ocurrió» |

En la Jerarquía solo lleva icono lo que no coincide con el juego: un más si es nueva, un punto si cambió y otro si no está en el juego; lo que coincide va sin icono, para que lo distinto salte a la vista y no se confunda con una orden (UX-06). En el mapa, los marcadores son un 25 % más grandes, con contorno y una muesca hacia donde miran; lo del seleccionado lleva su dueño («Mirek · M1») y lo demás se atenúa (UX-09). Además: relleno sólido es que está en el juego y la lectura coincide; contorno discontinuo, que está en el documento y todavía no en el juego; un fantasma y una línea, dónde sigue en el juego y adónde irá; todo discontinuo, que no hay nada en el juego. Cada tipo tiene su forma: objeto cuadrado, con el icono de su tipo dentro, el mismo que en la Jerarquía, Añadir y Propiedades (UX-48); infectado triángulo, animal rombo, actor círculo con una raya hacia donde mira, cámara con su encuadre, marca disco con aro y clave rombo azul.

## 7. Criterios verificables para el brief de F6 (R26)

Juntan los UI-01 a UI-26 de Claude y los R26-01 a R26-39 de Astra, y CU-39 y CU-40 salen de lo que pidió Guillermo el 10 de noviembre; el detalle de cada caso está en la fila de origen. Corren con el mod falso de #24 salvo que digan «en partida», y cada uno tiene que poder ponerse en rojo con la inyección de fallos de #24. No hay umbrales nuevos: los números salen del spec o del plan, salvo el de contraste de CU-38, que es el de WCAG 2.1, y el de CU-39, el 3:1 de WCAG 2.1 para lo que no es texto (1.4.11). PASA quiere decir que el caso positivo y el negativo dan lo esperado; FALLA, que aparece la conducta prohibida; INCONCLUSO, que falta esquema, capacidad, montaje o muestra (regla de Astra, del plan). Lo que enseña la web no cierra por sí solo un gate del juego.

La columna «Prototipo» dice qué hace ya el prototipo con datos falsos: **Probado** (lo comprueban `pruebas.js` o `pruebas-mejoras.js`), **Se ve** (está en la página, sin prueba) o **No**.

| ID | Traza | Positivo | Negativo | Origen | Prototipo |
|---|---|---|---|---|---|
| CU-01 | D1 | Playwright hace el flujo entero desde un documento vacío (Añadir, Propiedades, guardar, aplicar, preparar, rodar, parar, quitar del juego y recargar) solo con clics y teclas, y cruza cada paso con su orden en el backend por `op_id` y con lecturas del juego | Importar una fixture por API no acredita D1; sin el campo Rumbo en Propiedades la prueba falla, porque la fixture lo necesita | UI-01, R26-01, R26-38 | Probado en parte: aplicar, preparar, rodar, parar y reaplicar con teclas |
| CU-02 | A1, #7 | Las cinco fixtures inválidas (clase desconocida, fuera del mapa, presupuesto, campo extra y versión) enseñan su `code` y su ruta, y «Ver» selecciona lo señalado | El bridge no recibe ninguna orden y Aplicar está desactivado; bloquear solo el botón no basta; una ruta a algo que ya no existe queda en el resumen sin enfocar otra cosa | UI-06, R26-02, R26-03 | Probado: `out_of_map` y `expansion_unavailable` con su ruta y Aplicar desactivado |
| CU-03 | D2, #23 | Con eventos controlados se ven los seis estados con su forma, su edad frente a la marca del backend y su origen | Con el bridge caído, Pendiente pasa a Fallido «No se entregó» y nunca a Aplicado ni Observado; un 200 sin evento o una muestra vieja recibida ahora no dan Observado; sin marca de tiempo dice «Sin lectura», nunca «hace 0 s» | UI-02, UI-04, R26-28 | Probado |
| CU-04 | #23, #9 | Se pierde la respuesta después del efecto: Parcial, y al reconectar y leer, Observado («Reconciliada tras el corte») | Nunca vuelve a «No se entregó»; no hay reintento con otro `op_id`; reenviar el mismo `op_id` no añade entidades en el censo | UI-03, R26-04 | Probado |
| CU-05 | #9, A2 | Falla la creación de la entidad k: Parcial que la nombra y dice que se borró lo de esa orden; quitada la causa, aplicar llega a Observado. En partida, la fixture completa (20, 10, 3 y 2) da el multiconjunto exacto por clase y posiciones < 0,5 m | Quitar una raíz o moverla ≥ 0,5 m impide Observado; contar respuestas del spawner en vez de hacer el censo no acredita | UI-24, R26-04, R26-08 | Probado con el fallo simulado |
| CU-06 | A3 | Quitar del juego deja cero entidades propias, hijos incluidos; un segundo reset no cambia nada; el documento sigue igual | Lo puesto a mano, otra escena o lo ajeno dentro de un contenedor propio sobreviven; si no se puede preservar, Parcial, nunca «Reset completado» | R26-10 | No (en partida) |
| CU-07 | A4 | Guardar, cerrar, cargar y reaplicar conserva el hash y el censo (< 0,5 m), con el mismo epoch y con otro; «Recargar desde disco» sin cambios da el mismo hash | Un guardado interrumpido deja la revisión anterior; si el fichero cambió fuera de la web, hash nuevo y aviso | UI-25, R26-07 | No |
| CU-08 | A5 | 20 operaciones variadas (una de varios a la vez y una de cámara), 20 `Ctrl+Z` y 20 `Ctrl+Y`: hash inicial y final; el Historial nombra cada una | Con la pila vacía, Deshacer está desactivado y no sale ninguna petición; deshacer nunca manda nada al juego; durante la toma, `Ctrl+Z` se rechaza con el motivo | UI-05, R26-06 | Probado en parte: el nombre en el Historial y el rechazo durante la toma |
| CU-09 | A6, #28 | Medidores por tipo frente a los topes provisionales (20, 10, 3 y 2) y total con prendas e hijos según el backend; al tope, ese tipo se desactiva en Añadir | Tope + 1 en cualquier tipo, exceso solo de prendas o mezcla: `budget_exceeded` con ruta y cero órdenes; Intro sobre un elemento desactivado no manda nada; sumar máximos no sustituye el tope de S-perf | UI-07, R26-09 | Probado en parte: «35 entidades y 9 prendas · Tope total aún sin certificar» y, al tope, nada que añadir |
| CU-10 | A1, C5, #8 | El catálogo es el del build y el modset del handshake y separa lo disponible de lo incompatible | Cambiar el modset o perder el catálogo no certifica una clase con una caché vieja; la web dice qué quedó incompatible y no borra el documento | R26-11 | No |
| CU-11 | A5, D4 | Con varias entidades seleccionadas, posición y rumbo cambian por campos igual que con el gesto, en una transacción con nombre | Lo no seleccionado no cambia; los valores mixtos sin activar no se sobrescriben; un arrastre cancelado no deja transacciones | R26-18 | No |
| CU-12 | C1, B6 | Personaje fijo y vestuario por ranura leídos en el servidor, también tras resetear | Prenda desconocida o ranura incompatible se rechaza antes de aplicar; si falla en el juego, Parcial con la prenda; equipo de más impide la conformidad | R26-12 | Se ve: «Vestuario leído» en la preparación |
| CU-13 | C2 | «En marca» solo con lecturas: llega a < 1,5 m y se queda a < 0,5 m durante 10 s | Marca inalcanzable o amenaza: no alcanzada; un índice de waypoint sin lectura de posición no deja armar | R26-13 | Se ve: «Actores en su marca inicial» |
| CU-14 | C3, #15 | Los gestos certificados se añaden y enseñan pedido, inicio y fin observados | El no certificado no se puede elegir; un documento que lo trae da `unknown_emote` en su ruta; tras parar no aparece un gesto tardío | UI-10, R26-14 | Se ve: los no certificados salen desactivados |
| CU-15 | C4, #13 | HOLD, ONCE, LOOP y ROAM se guardan sin depender del motor; ROAM se mantiene 10 min dentro del radio de S3 | Un enum de Expansion o un comportamiento inventado se rechaza; sin el radio de S3, INCONCLUSO | R26-15 | No |
| CU-16 | C5 | Sin Expansion, una escena sin actores se aplica | La escena con actores da `expansion_unavailable` en Validación, Aplicar se desactiva y el bridge no recibe nada; si se pierde entre validar y aplicar, cero creaciones | UI-08, R26-16 | Probado con el simulador |
| CU-17 | D5, #20 | Colocar en los tres puntos de la georreferencia guarda X y Z dentro del error que mida S-mapa; en partida, el contacto queda a < 0,2 m del terreno | Eje invertido, fuera del mapa, puente o tejado: rechazo; comparar la transformación con su inversa no acredita | UI-20, R26-17 | Probado en parte: «Leer el suelo» al colocar, con su edad, y `out_of_map` |
| CU-18 | D5, E1, E3 | Las imágenes del mapa salen del backend local | Cualquier petición a iZurvive, xam.nu u otro servidor de teselas falla la prueba | UI-19, R26-37 | Probado: ninguna petición sale de la página |
| CU-19 | B1, #6, #17 | «Nueva cámara desde la cámara libre» guarda la pose que lee el cliente (al volver, < 0,05 m y < 0,5°); FOV en grados en la web y en radianes en el documento | Sin director, el botón se desactiva con `no_director`; una pose no finita se rechaza; grados mandados como radianes se detectan con la lectura, no con un eco | UI-16, UI-26, R26-19 | Se ve |
| CU-20 | B2, #16 | Camino de 3 claves en 6 s: lectura < 0,5 m del camino, fin entre 6,0 y 6,3 s, final a < 0,05 m y < 0,5° | Tiempos que no crecen o menos de 2 claves se rechazan; un salto o el giro de 179° a −179° fallan aunque la vista previa parezca bien | R26-20 | Se ve: «trayectoria prevista (#16)» |
| CU-21 | B3 | Con la DOF encendida no hay aviso; el enfoque se acredita con las capturas del arnés | Con la DOF apagada salen el aviso y la nota, y la toma se puede armar igual; el aviso no cierra B3 | UI-11, R26-21 | Probado: el aviso |
| CU-22 | B5, B7, #4 | Armada solo con todas las lecturas de la revisión fijada: escena, director, cámara con su hash, vestuario, marcas y ambiente | Quitar una condición, usar el hash de otro camino o un dato de otro epoch impide rodar; sin director, `no_director` y ningún GO | UI-09, R26-22 | Probado |
| CU-23 | B5 | Rodar manda un único GO y Tomas enseña el desfase medido de cada actor; la variación entre tomas no pasa de 100 ms según S-toma | Un doble clic o un acuse sin inicio no dan éxito; sin medida dice «sin medida», nunca 0 ms | UI-13, R26-23 | Se ve: desfase por actor en Tomas |
| CU-24 | B5, F5 | `Esc`, `Espacio` y el botón paran; «Parando…» hasta que confirma el cliente; control devuelto en < 1 s desde el clic | Un doble parar o un corte tras el clic no dan un falso «Control devuelto»; si se pierde el director o el backend, la toma falla y su orden queda Parcial citando el hombre muerto hasta leer | UI-12, R26-24 | Probado |
| CU-25 | B5, D3 | Parar está a la vista y responde en los layouts de fábrica, con paneles movidos y con avisos (`elementFromPoint` en su centro), a cualquier ancho y también con la página desplazada | Un panel, un diálogo o la recuperación de un layout que lo tape o lo capture falla | UI-12, R26-32 | Probado en el layout de serie, con un menú abierto y de 390 a 901 px, arriba y desplazada (AR2-02) |
| CU-26 | B4, F5 | HUD y barra rápida ocultos toda la toma; al salir (terminar, parar, fallo u hombre muerto) vuelven el control y el permiso de daño de antes | HUD visible, o daño puesto siempre a «sí» al salir, falla; sin cliente, `client_not_in_game` | R26-25 | No (en partida) |
| CU-27 | B6 | Tres tomas, cada una tras reset y reaplicación observados: mismos conteos, personajes y vestuario; actores a < 1,5 m de su marca; camino a < 0,5 m | Saltarse el reset, vestuario cambiado o una entidad de más bloquean la preparación; si el reset acaba Parcial, la cadena se para | UI-14, R26-26 | Probado: «Reaplicar y preparar» |
| CU-28 | B7, #19 | Al empezar cada toma se lee la hora (±1 min) y cada valor de clima actual (±0,01) | Un forecast correcto con el actual distinto, una muestra vieja o un campo inválido impiden arrancar; el valor pedido no rellena el observado | UI-15, R26-27 | Se ve: «Hora y clima del documento» |
| CU-29 | B7, E2, #27 | «Probar ambiente» y «Leer el juego ahora» piden una lectura nueva sin cambiar el documento | Mover un deslizador sin probar no toca el juego; probar no marca aplicada la revisión; durante la toma no se puede probar | R26-39 | Se ve |
| CU-30 | D2, #10, #22 | Recargar durante una orden o una toma recupera snapshot, revisión, generación, epoch y Parar; con epoch nuevo, aviso de mundo nuevo, entidades «no está en el juego» y toma desarmada | Un evento duplicado, fuera de orden o de un epoch viejo no hace retroceder el estado; reconectar no ejecuta órdenes caducadas; con el mismo epoch no hay aviso | UI-23, R26-29 | Probado en parte: aviso de mundo nuevo con su epoch, que se quita al aplicar |
| CU-31 | D3, #21 | El layout se guarda en el perfil del backend y vuelve igual tras recargar, también con el almacenamiento del navegador borrado; cambiar de modo no cambia el hash | Un perfil corrupto da el layout de fábrica con un aviso; guardarlo solo en el navegador incumple #21 | UI-17, R26-30 | No: el prototipo lo guarda en el navegador |
| CU-32 | D4 | Colocar, aplicar, preparar, rodar y parar solo con teclado; reasignar las cinco, recargar y repetir | Un conflicto avisa y no dispara dos órdenes; con el foco en un campo no se ejecutan; ninguna de las cinco se queda sin tecla; una tecla que atiende el navegador falla aunque el botón funcione | UI-18, R26-31 | Probado: teclas de serie, conflicto y obligatorias |
| CU-33 | E1, #22 | Con sesión válida en 127.0.0.1 la orden pasa; el token de los peers no aparece en `window`, en el DOM ni en el almacenamiento | Credencial inválida, Host u Origin falsos, origen de la LAN o TTL vencido: cero efectos; la web no ofrece «continuar de todos modos» | UI-21, R26-33 | No |
| CU-34 | E2, #27 | 100 operaciones (25 lecturas del servidor, 25 de suelo, 25 poses y 25 de ambiente): p95 < 1 s del navegador a lo observado | Retraso > 1 s en 10 o más, respuestas perdidas o solo acuses: falla | R26-34 | No |
| CU-35 | E3, E4 | Todo funciona con el MCP apagado y la barra de estado lo dice, a la vista a cualquier ancho | Ninguna petición al MCP; evidencia de Diag presentada como retail deja la aceptación INCONCLUSA | UI-22, R26-35 | Probado que «MCP apagado» se ve entero de 390 a 1600 px (UX-33 y AR2-02) |
| CU-36 | E5, A6, #28 | Escena al tope combinado con actores vestidos, cámara y toma: media > 35 FPS en tres ventanas de 60 s (suelo provisional de #28) | Un pico o un promedio instantáneo no acreditan; si falla, se revisa el presupuesto en S-perf, nunca desde la web | R26-36 | No |
| CU-37 | D2, #7, F5 | Sin backend: luces en gris con «hace X», aviso y Actividad con lo último que se supo; al volver, el aviso se va | No se puede guardar, aplicar ni crear una escena, y Propiedades se bloquean (AR2-03). Guardar no dice «Guardado»: dice que no se guarda (AR3-03) | Consolidación | Probado |
| CU-38 | D2, B5 y WCAG 2.1 (1.4.3) | Todo texto visible llega a 4,5:1 (3:1 si es grande) en los dos temas, en escena, Añadir, la leyenda, Herramientas, historial, validación, aplicando, fallo a mitad, sin backend, armada, rodando, parada y Guía | Un solo texto por debajo hace fallar la prueba, también sobre las rayas de Parcial; con los colores anteriores fallaban, entre otros, «Parar» en oscuro (3,67:1) y «Observado» en claro (3,96:1). En el mapa también falla si falta un texto de los que tocan, si un texto va en una imagen que no se puede medir (AR2-01) o si lo que se pinta después lo deja por debajo en el fotograma acabado (AR3-01), y si un texto del mapa, salvo los pueblos, queda bajo lo que flota encima o cortado por su borde (UX-50). Desde AR4-01, también si sus huecos acaban con su tinta, si el fondo que tiene cerca lo deja por debajo, si llega por una imagen que no se sabe de dónde sale o si en pantalla no se ve como en el lienzo, por un filtro, una opacidad o un velo de CSS. Desde AR5-01 y AR5-02, en pantalla cada píxel de cada texto es el suyo del lienzo, salvo la caja de lo que flota encima, y en su sombra lo oscurece como mucho ella; ahí también se lee, y un texto del que no se compara ningún píxel no pasa. Hasta AR6-01, esa caja se apartaba también cuando un recorte no la pinta, y bastaba comparar parte de un texto; desde AR6-01, lo que flota con un recorte se compara, y un texto comparado a medias no pasa. Lo apartado es la caja entera de lo que flota, también donde no pinta, como un fondo transparente, y queda sin comparar, que no es lo mismo que no verse (AR7-02). Y desde AR6-03, ningún número de la regla se pinta encima de otro, también al encoger la ventana | Medición de Claude tras la consolidación | Probado |
| CU-39 | #8 y petición de Guillermo | Cada objeto lleva el icono de su tipo, que viene con su clase en el catálogo: el mismo trazado en el mapa, la Jerarquía, Añadir y Propiedades. En el mapa va dentro de su cuadrado, sin salirse, a 3:1 o más de él en sólido y en borrador | Una clase que no tiene tipo lleva el icono genérico, sin errores, y Propiedades enseña esa clase tal cual, sin dar por suya la primera del catálogo (AR4-06). Con el icono, el marcador sigue siendo un cuadrado y sus estados se distinguen igual: discontinuo sin aplicar, y sólido aplicado y leído (UX-48) | Guillermo | Probado |
| CU-40 | #8 y petición de Guillermo | En Añadir, lo que tiene el ratón encima o el foco enseña su captura del juego, en 16:9, su nombre, su clase y su tamaño, y en los objetos su planta a escala en sus dos lados, los de la planta que se ve, medida en una captura, y no los de su caja, con cada tramo de sus lados y de su barra a 3:1 o más (AR4-02, AR5-04, AR6-02, AR7-01). Con el teclado se recorre la lista también al tope, sin poder pasar de él (AR4-05). Al colocar un objeto, su planta va bajo el cursor a la escala del mapa | Sin captura o sin tamaño en el catálogo, la vista previa lo dice y no pinta nada inventado, sin errores (AR4-04). No tapa el mapa ni lo mueve, ninguna letra baja de 12 px y, sin sitio, se aparta y la lista sigue a la vista (UX-49, C-17) | Guillermo | Probado, con el icono en lugar de la captura y medidas de muestra. Hasta la cuarta revisión de Astra no se probaban el ancho de la planta, la falta de tamaño ni el teclado al tope, y hasta la sexta la planta se medía por su caja: en la quinta, sin girar ni tapar. Hasta la séptima, su contraste era el de su píxel más apartado del fondo |

El manifiesto de cada prueba guarda revisión y hash, operación, epoch y generación, build y modset, y origen y hora de cada muestra (Astra, del plan). Son datos para cruzar evidencia, no un formulario para la creadora.

## 8. Puntos abiertos

### Para Guillermo

1. **Tema de serie:** oscuro (lo propuesto, por las sesiones largas junto al juego) o claro. Los dos están hechos.
2. **Pasos de las rejillas:** 0,5 m y 15° (Alt, 0,1 m y 1°) son propios. Si se verifican los de serie de Eden o del DayZ Editor, ganan esos.
3. **Parar desde dentro del juego (C-16):** resuelto el 2026-11-05. Guillermo la quiere en M1: la tecla «Parar toma» del mod de cliente para la toma igual que Parar en la web. La web enseña la tecla que dé el backend (UX-46), y el plan de F5 lo recoge en un hilo aparte.
4. **Vista previa:** resuelto el 2026-11-05. Guillermo elige moverlos: al mover el cursor de tiempo, cada actor con recorrido se pinta también donde estaría, rayado como estimación a la velocidad supuesta, sin quitar su sitio ni sus marcas (UX-30 de la lista de noviembre).
5. **Aplicar otra escena encima de la que hay en el juego:** resuelto el 2026-11-05. Guillermo elige seguir #9: Aplicar quita la escena del juego y crea la nueva, con un aviso que nombra la que se quita (UX-15 y UX-47). Astra la bloqueaba hasta resetear la anterior.
6. **Nombre de Aplicar:** resuelto en noviembre. Es «Aplicar escena», con nombre fijo, y los cambios sin aplicar van junto al nombre de la escena (UX-04).

### Para los contratos (F1, F2 y los spikes)

- **C-02:** el tope combinado de A6 lo fija S-perf; la web lo lee del backend.
- **C-07:** la paridad de cámara con COT y PCT sigue pendiente del banco de cámara del plan.
- **C-09:** orden y reanudación de SSE, correlación del snapshot con los eventos y el TTL de una orden. El prototipo usa 10 s; la web enseñará el que devuelva el backend.
- **C-10:** esquema del enfoque, unidades de la orientación y rangos de cada campo.
- **C-11:** S3 decide ROAM, la lista final de gestos certificados y cómo se observa una cancelación.
- **C-12:** S-mapa decide la imagen, su calibración, la consulta de suelo y el rechazo de puentes y tejados.
- **C-13:** no hay contrato para muestrear la curva de cámara antes de rodar; por eso es «trayectoria prevista».
- **C-14:** el esquema de cues de actores de F5 no está escrito; si pide tiempos editables, la línea de tiempo se cierra contra ese esquema antes de implementarla.
- **C-17:** el catálogo de #8 trae las clases, pero no una imagen ni el tamaño de cada una. La vista previa de Añadir (UX-49) pide una captura por clase, en 16:9, hecha aparte como las de Eden, y la caja del modelo. Falta decidir quién las hace y cómo llegan a la web; hasta entonces, el icono del tipo y ningún tamaño.

## 9. Procedencia de cada parte

Las fuentes se consultaron el 2026-10-27, el 2026-10-28, el 2026-11-04, el 2026-11-05 y el 2026-11-10.

| # | Parte de la interfaz | Referente | Qué se copia | Fuente | Propuso |
|---|---|---|---|---|---|
| 01 | Modos Escena y Rodaje en la barra superior | Game Master de Arma Reforger | La barra de arriba que cambia entre Game Master y Armavision | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Las dos |
| 02 | Paleta de grises fríos por capas: chasis, panel, campo y realce, con líneas de 1 px | Editor de Unreal 5 y World Editor de Reforger | El patrón: superficies oscuras, un paso más claras cada una. Los valores son propios, ajustados al contraste; el mapa es la única superficie de papel | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface) | Grok, Muse y Gemini 4 |
| 03 | Una sola acción principal a la vista, en ámbar con texto oscuro; Parar en rojo | PROPIO (lista de noviembre), sobre la barra principal de Unreal 5 | Play destacado en la barra; aquí el color sale del acento y nunca hay dos | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface) | Grok, Muse y Gemini 4 |
| 04 | Letra del sistema a 13 px, Segoe UI Variable en Windows, cifras tabulares y títulos sin mayúsculas forzadas | DayZ Editor y editor de Unreal 5 | Menús en minúscula normal y sin versalitas (DayZ Editor) y texto denso en paneles (Unreal 5). La letra del sistema y los 13 px son propios | [raw.githubusercontent.com](https://raw.githubusercontent.com/wiki/InclementDab/DayZ-Editor/assets/images/toolbar.png) | Consolidación, Gemini 4 y Grok |
| 05 | Selección en ámbar, con color propio | DayZ Editor (Preferences) | El color de selección se ajusta aparte; el ámbar es propio | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.1-Preferences) | Consolidación |
| 06 | Jerarquía a la izquierda, agrupada y con buscador | Eden (Entity List) y World Editor de Reforger (Hierarchy) | Lista de todo lo que hay en la escena, agrupada | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Terminology) | Las dos |
| 07 | Bloquear y ocultar desde la jerarquía | DayZ Editor | Lock (L) y Unlock (Ctrl+L) | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Claude |
| 08 | Añadir a la derecha, en pestaña con Propiedades: solo lo que se pone en el mapa, por tipo y con buscador | Eden (Asset Browser) y Game Master (Entity Browser) | Catálogo por tipo a la derecha; clic en el nombre y clic en el mapa | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Asset_Browser) | Astra y Gemini 4 |
| 09 | Tab con el mapa activo abre Añadir y Esc vuelve; la búsqueda se conserva | Game Master de Reforger (Entity Browser) | Tab abre el catálogo y Esc lo cierra | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Las dos |
| 10 | Colocar: clic, Ctrl + clic para seguir, clic derecho cancela | Eden y Game Master | Los mismos gestos de ratón | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Entity_Placing) | Las dos |
| 11 | Intro coloca lo elegido en el centro del mapa | PROPIO (D4: alternativa al arrastre), sobre Eden | El mismo flujo de colocar, sin ratón | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Entity_Placing) | Claude |
| 12 | Todo se coloca apoyado en el suelo | DayZ Editor (Ground Mode) | Lo colocado se apoya en el terreno; aquí siempre, porque D5 lo pide | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Las dos |
| 13 | Presupuesto por tipo al pie de Añadir; al tope no deja añadir más | Game Master de Reforger | Presupuestos a la vista junto al catálogo, que bloquean al llenarse | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Las dos |
| 14 | Total: entidades y prendas, con el tope total aún sin certificar | PROPIO (A6 y decisión #28), sobre Game Master | El desglose de lo gastado | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Astra |
| 15 | Propiedades acopladas; doble clic las abre | World Editor de Reforger (Object Properties) y Eden (doble clic abre Attributes) | Panel de propiedades de lo seleccionado | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Las dos |
| 16 | Alt+Intro lleva a las propiedades | Explorador de Windows | Alt+Intro abre las propiedades de lo seleccionado; el Ctrl+T del DayZ Editor lo atiende el navegador | [support.microsoft.com](https://support.microsoft.com/en-us/windows/keyboard-shortcuts-in-windows-dcc61a57-8ff0-cffe-9796-cb9706c75eec) | Consolidación |
| 17 | Nueva escena sin tecla | Chromium | Ctrl+N, Ctrl+T y Ctrl+W las atiende el navegador antes que la página | [chromium.org](https://www.chromium.org/developers/design-documents/extensions/proposed-changes/apis-under-development/browser-keys/) | Consolidación |
| 18 | Menú de escena: nueva, abrir (Ctrl+O), guardar (Ctrl+S) y guardar como (Ctrl+Mayús+S) | DayZ Editor | El menú File y sus teclas | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Las dos |
| 19 | Ctrl+Z, Ctrl+Y, Ctrl+J, Ctrl+A, Supr, P (copiar coordenadas) e Y (ocultar la interfaz) | DayZ Editor (Ctrl+Y también en el World Editor de Reforger) | Las mismas teclas | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Las dos |
| 20 | Ambiente (fecha, hora y clima) como ajuste de la escena | DayZ Editor (Environment), Game Master (Scenario) y Eden | Fecha, hora y clima en un sitio propio, fuera de las entidades | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Las dos |
| 21 | Probar el ambiente en el juego sin aplicar la escena | DayZ Editor (Environment) | Hora y clima se cambian en vivo; aquí con un botón, porque editar no toca el juego (#7) | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Astra |
| 22 | Órdenes cortas con su estado: leer el suelo, leer el juego, probar el ambiente y mover la cámara | PROPIO (decisión #27 y E2), sobre el Session Inspector de UEFN | Cada operación con su paso en curso y su error | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Consolidación |
| 23 | Selección: clic, Ctrl + clic alterna, Mayús + clic selecciona seguidos | DayZ Editor | Make, Toggle y Continuous Selection | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Las dos |
| 24 | Mover con flechas y Alt + flechas despacio | DayZ Editor | Move XZ y Move Objects Slow; el paso de cada tecla es propio | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Claude |
| 25 | Arrastrar con el botón derecho mueve el mapa y la rueda acerca | Eden | La navegación del mapa con el botón derecho y la rueda | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Astra |
| 26 | Mayús + arrastrar gira lo seleccionado | Eden | Mayús + arrastrar con el botón izquierdo rota | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Astra |
| 27 | Rejillas de movimiento y de giro que se encienden y se apagan | Eden | Los botones de rejilla de traslación y de rotación de su barra; los pasos son propios | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Toolbar) | Astra |
| 28 | Encuadrar la selección (F) | World Editor de Reforger | Focus (F) | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Claude |
| 29 | Marcas de actor con Mayús + clic derecho | Eden | Mayús + clic derecho añade un waypoint rápido a lo seleccionado | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Actions) | Las dos |
| 30 | Mapa 2D con aspecto de mapa topográfico del juego | Eden | El mapa 2D usa el aspecto del mapa del juego, con iconos de entidades | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Las dos |
| 31 | «Aplicar escena» con nombre fijo; los cambios sin aplicar, junto al nombre de la escena | UEFN | Push Changes empuja lo editado a la sesión en vivo | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/fortnite/first-island-04-playtest-your-island-in-fortnite) | Las dos |
| 32 | Aplicar quita y crea la escena entera; Quitar del juego solo la quita | PROPIO (decisión #9), sobre Eden | Al volver al editor, el escenario vuelve a su estado inicial | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Las dos |
| 33 | «Ir a rodaje» cuando la escena está aplicada y leída | Game Master de Reforger (Scenario) | El siguiente paso del escenario a la vista | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Claude |
| 34 | Revisión editada frente a la aplicada | PROPIO (A4 y decisión #7), sobre UEFN | Push Changes separa lo editado de lo que corre | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/fortnite/first-island-04-playtest-your-island-in-fortnite) | Las dos |
| 35 | Claves de cámara: copiar y pegar ajustes, enfoque por clave | Rockstar Editor | Marcadores con cámara, profundidad de campo y ajustes copiables | [gtabase.com](https://www.gtabase.com/grand-theft-auto-v/rockstar-editor/) | Claude |
| 36 | Capturar la pose de la cámara libre | DayZ Editor | View › Dump Camera y los ajustes de cámara (FOV, desenfoque) | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Las dos |
| 37 | Ver la trayectoria prevista de las cámaras (H) | Replay Mod | Toggle Path Preview con la tecla H | [badlion.net](https://www.badlion.net/wiki/replay-mod-keys) | Claude |
| 38 | Claves en una regla de tiempo: elegir, arrastrar y escribir el tiempo | Replay Mod | La línea de claves de posición y de tiempo de su editor de caminos | [replaymod.com](https://www.replaymod.com/docs) | Astra |
| 39 | Vista previa del mapa: pistas de actores y ambiente bajo la cámara, con transporte y «Previsualizar» | Sequencer de Unreal | Pistas a la izquierda, cursor que se arrastra e ir al principio, clave anterior, reproducir, clave siguiente e ir al final | [docs.unrealengine.com](https://docs.unrealengine.com/4.27/AnimatingObjects/Sequencer/ReferenceEditor) | Claude |
| 40 | Cabecera de toma con número, cámara, estado, reloj y la acción que toca | Sequencer de Unreal y Studio Mode de OBS | El transporte y el paso a emisión en una sola franja | [obsproject.com](https://obsproject.com/kb/obs-studio-overview#studio-mode) | Astra |
| 41 | Preparar y armar antes de rodar; lo preparado no sale hasta pulsar Rodar | PROPIO (decisión #4), sobre el Studio Mode de OBS | Preparar a un lado y pasarlo a emisión con un paso aparte | [obsproject.com](https://obsproject.com/kb/obs-studio-overview#studio-mode) | Las dos |
| 42 | Preparar la toma con Mayús+F9 | Ableton Live | Mayús+F9 arma la grabación | [ableton.com](https://www.ableton.com/en/manual/live-keyboard-shortcuts/) | Astra |
| 43 | Rodar con Intro cuando la toma está armada | Eden | Intro arranca la vista previa del escenario | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Preview) | Astra |
| 44 | Parar con Esc, aunque haya un menú o un diálogo abiertos | World Editor de Reforger | Esc sale de la vista previa | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Claude y Astra |
| 45 | Parar fijo en la barra de arriba mientras dura la toma | Editor de Unreal 5 | Play y Stop fijos en la barra principal | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-editor-interface) | Astra |
| 46 | Espacio también para la toma que rueda | Ableton Live | Espacio para el transporte; aquí solo para y nunca arranca | [ableton.com](https://www.ableton.com/en/manual/live-keyboard-shortcuts/) | Consolidación |
| 47 | «Parando…» hasta que tu juego confirma la parada | PROPIO (B5 y decisión #23), sobre el transporte de Ableton | Parar se pulsa al momento; la confirmación llega aparte | [ableton.com](https://www.ableton.com/en/manual/live-keyboard-shortcuts/) | Astra |
| 48 | «Rodando» sin botón de grabar: el vídeo lo graba una herramienta externa, como OBS | PROPIO (grabar vídeo está fuera de M1), sobre OBS | OBS es quien graba | [obsproject.com](https://obsproject.com/kb/obs-studio-overview#studio-mode) | Astra |
| 49 | Lista de tomas con su resultado | REAPER | Cada grabación nueva sobre la misma pista es una toma | [reaper.fm](https://www.reaper.fm/guides/REAPER%20Quick%20Start.pdf) | Claude |
| 50 | Durante la toma no se edita la escena | PROPIO (decisiones #4 y #7), sobre la vista previa de Eden | Probar y editar son momentos distintos | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Preview) | Astra |
| 51 | Actividad abajo con filtros, plegada en una tira con la última orden | World Editor de Reforger y editor de Unreal 5 | Log Console con filtros de error, aviso e info; el Output Log de Unreal se pliega abajo | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Claude |
| 52 | Barra de estado que no se toca, con las tres luces, el mapa, el juego, la validación y el MCP | Eden y editor de Unreal 5 | Status Bar no interactiva; la barra inferior de Unreal enseña el estado del control de versiones | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Terminology) | Las dos |
| 53 | Menú Herramientas con texto: paneles, layouts, atajos y ocultar la interfaz | DayZ Editor | Menús con texto en la barra | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Astra |
| 54 | Reasignar atajos: avisa del choque y deja elegir Reemplazar o Cancelar | Unreal (Keyboard Shortcuts) | El aviso de conflicto con sustituir o cancelar | [dev.epicgames.com](https://dev.epicgames.com/documentation/unreal-engine/customizing-keyboard-shortcuts-in-unreal-engine?lang=en-US) | Astra |
| 55 | Colocar, Aplicar, Preparar, Rodar y Parar nunca se quedan sin tecla | PROPIO (D4), sobre Unreal | El mismo diálogo, que aquí no deja vaciarlas | [dev.epicgames.com](https://dev.epicgames.com/documentation/unreal-engine/customizing-keyboard-shortcuts-in-unreal-engine?lang=en-US) | Consolidación |
| 56 | Seis estados por orden: pendiente, ejecutando, aplicado, observado, fallido y parcial | PROPIO (D2 y decisión #23), sobre DZ Commander | Su cola de comandos: creado, enviado, confirmado | [dzcommander.com](https://dzcommander.com/) | Claude |
| 57 | Cada estado con forma y color, el paso en curso y el error con su detalle | PROPIO (D2), sobre el Session Inspector de UEFN | Una rueda en el paso en curso y un icono de error con su detalle | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Las dos |
| 58 | Backend, Servidor y Tu juego con la edad del último latido, en la barra de estado; aviso de mundo nuevo | PROPIO (D2, E1 y decisión #10), sobre el Session Inspector de UEFN | El estado de la sesión siempre a la vista | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Astra |
| 59 | Errores de validación: primero el mensaje, y al lado el código y la ruta al campo | PROPIO (A1), sobre el Session Inspector de UEFN | Cada problema con su detalle y el sitio donde se arregla | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Las dos |
| 60 | Jerarquía con estado por excepción: icono solo si es nuevo o ha cambiado, y una línea con la edad de la lectura | PROPIO (decisión #7), sobre la Entity List de Eden | La lista de entidades, sin decoración por fila | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Terminology) | Claude |
| 61 | Detalles técnicos plegados: ids, clases, huellas y revisiones | World Editor de Reforger (Object Properties) | Las propiedades, separadas de la información de la entidad | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Las dos |
| 62 | Marcas y claves con su dueño, lo demás atenuado, y leyenda plegable dentro del mapa | Eden (mapa 2D) y Replay Mod (caminos de cámara) | Iconos de entidades en el mapa 2D y claves numeradas en el camino | [replaymod.com](https://www.replaymod.com/docs/#camera-paths) | Las cinco |
| 63 | La edad de la lectura, aparte de la de la petición | PROPIO (D2 y decisión #23), sobre el Session Inspector de UEFN | Duración frente a fecha de fin de cada operación | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Astra |
| 64 | Paneles acoplados de borde a borde que se ajustan; layouts guardados | Roblox Studio y Dockview (decisión #21) | Acoplar paneles y guardar la disposición (D3) | [create.roblox.com](https://create.roblox.com/docs/studio/overview#layout-customization) | Las dos |
| 65 | La rueda encima de lo seleccionado lo gira; en el resto del mapa acerca y aleja | PROPIO (petición de Guillermo, UX-44) | Ningún referente de la lista gira con la rueda: Eden y Zeus giran con Mayús + arrastrar, y en su mapa la rueda acerca | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_3_Field_Manual_-_Zeus) | Guillermo |
| 66 | La rueda encima de un campo numérico lo sube o lo baja un paso, y con Mayús diez | OBS Studio (campos de Qt) | La rueda cambia el campo que tiene debajo; aquí, si venía desplazando el panel, lo sigue desplazando | [obsproject.com](https://obsproject.com/forum/threads/in-game-scroll-wheel-changing-settings.83422/) | Guillermo |
| 67 | En Rodaje, con el cursor de tiempo movido, el actor también se pinta rayado donde estaría; clic en un gesto elige a su actor | Sequencer de Unreal y caminos de Replay Mod | Al arrastrar el cursor de tiempo, lo animado se ve donde está en ese instante; aquí es una estimación a la velocidad supuesta y va rayada (UX-30) | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine) | Gemini 4 y Muse |
| 68 | La toma también se para desde tu juego, con la tecla «Parar toma» del mod de cliente | Rockstar Editor | Dentro de GTA V, una tecla empieza a grabar y otra para (F1 y F2 de serie), sin salir del juego (UX-46) | [support.rockstargames.com](https://support.rockstargames.com/articles/4gZPiqdUZD8ZhaJ81IPDJr/how-to-record-clips-and-access-the-rockstar-editor-in-gtav-on-pc) | Gemini 4 |
| 69 | Cada objeto lleva el icono de su tipo, el mismo en el mapa y en las listas | Eden y Arma 3 | Cada entidad con un icono en la vista y en la lista de entidades; en Arma 3 el icono va con la clase. Los dibujos son propios (UX-48) | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Terminology) | Guillermo |
| 70 | Vista previa al escoger en Añadir, con su tamaño y su planta a escala, y la planta del objeto bajo el cursor al colocarlo | Eden (Asset Browser) | Una captura del juego por clase, en 16:9, al escoger, y lo que se coloca va con el cursor. Hasta que lleguen las capturas con el catálogo del mod, el icono del tipo (UX-49) | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Configuring_Asset_Previews) | Guillermo |

La revisión visual del 9 de noviembre (VIS-01 a VIS-13) cambia detalles de presentación de estas partes, no añade partes nuevas. Sus referentes y sus fuentes están en su [informe](2026-11-09-ui-revision-visual.md).

## 10. Fuera de M1 (R25)

- Una vista de calibración del mapa con los tres puntos de la georreferencia.
- Selección por recuadro en el mapa, cuando se verifique cómo la hace Eden.
- Composiciones reutilizables, exportar a otros editores y temas ampliables (C-05 de Astra).
- Una curva de cámara exacta frente al cliente, si B2 y un contrato de muestreo lo justifican.
- La paleta de comandos y el modo imán del DayZ Editor: no los pide el spec.
- Vista 3D, varios directores, grabar vídeo, cambiar de mapa, MCP e IA, y eventos: fuera del spec.

## 11. Revisión cruzada de Astra

Hecha el 2026-11-04 sobre el prototipo con las mejoras AHORA (`10274b7`): [informe de Astra](astra/2026-11-04-ui-revision-astra.md). Lo dio por NO APTO, con ocho hallazgos (AR-01 a AR-08). Están arreglados, cada uno con su criterio + y −, en la §7 de la [lista de noviembre](2026-11-04-ui-mejoras-consolidado.md):

- AR-01: tras un corte en plena toma, la Guía y los Atajos tapaban «Parada sin confirmar». Ahora la toma sigue abierta hasta que una lectura confirma la parada.
- AR-02: salía «Nada en el juego» sin lectura, mientras se aplicaba o tras un corte. Ahora dice que falta la lectura.
- AR-03: los números de la rejilla bajaban a 2:1 sobre los edificios. Ahora van sobre una placa opaca, y CU-38 mira también el texto del mapa, en todos los píxeles de cada letra. Una segunda medida en Windows encontró un hueco del halo dentro del «·»; ahora el halo se pinta como imagen (§7 de la lista).
- AR-04: dos pruebas leían contadores de la propia página. Ahora leen lo que se pinta, y cuatro mutantes comprueban que fallan cuando el dibujo se rompe.
- AR-05: textos de Tomas a 10 px. Ahora a 12.
- AR-06: «Ver» dejaba el campo del error oculto detrás de Añadir. Ahora abre Propiedades con el campo a la vista y con el foco.
- AR-07: la tira decía «Sin problemas» con una orden fallida. Ahora la cuenta hasta que se resuelve.
- AR-08: este documento aún mandaba el botón blanco y atribuía la letra y los grises exactos a Unreal y Reforger. Ya no (§4, §6 y §9).

Mantiene dos disensos fuertes, que llegaron literales a Guillermo: no dar AHORA por cerrado por el verde de las pruebas, y no presentar como copiados de Unreal o Reforger los valores exactos de letra, tamaño y paleta. Al primero responden AR-01 a AR-07 y las pruebas nuevas; al segundo, AR-08. De lo que noviembre eligió frente a su lane, deja de sostener el disenso en los tres puntos: los 13 px (pide comprobar la lectura a escala real antes de elegir entre 13 y 14), «Quitar del juego» y «MCP apagado» en la barra de estado. Ninguno de sus hallazgos toca lo que se le quitó de su lane en octubre.

**Segunda revisión**, el 2026-11-05, sobre `b106329`: la segunda pasada (UX-18, UX-33 y UX-15), estos arreglos y lo del 5 de noviembre (UX-44, UX-45, UX-30, UX-46 y UX-47). [Informe de Astra](astra/2026-11-05-ui-revision2-astra.md). Otra vez NO APTO, con siete hallazgos (AR2-01 a AR2-07), arreglados con su criterio + y − en la §9 de la lista de noviembre:

- AR2-01: la prueba del mapa miraba las llamadas de dibujo y no lo que se ve, y tres dibujos rotos pasaban. Ahora mide lo que queda pintado: los rellenos y los contornos en el fotograma acabado, y la letra al pintarla (desde la tercera revisión, también al acabar). Así salió que el contorno de los borradores casi no tenía huecos.
- AR2-02: por debajo de 900 px, Parar y «MCP apagado» se salían de la ventana. Ahora las dos barras se quedan fijas (CU-25 y CU-35).
- AR2-03: sin backend, «Nueva escena» creaba una. Ahora se apaga y dice por qué (CU-37).
- AR2-04: Ctrl + rueda giraba lo elegido. Ahora la rueda con Ctrl o Cmd es del navegador (§5).
- AR2-05: la rueda juntaba en un cambio los pasos de dos elegidos. Ahora son dos.
- AR2-06: sin conexión, la tecla del juego daba la toma por parada sin leerla. Ahora sigue sin confirmar hasta leer el juego, y con la toma armada la desarma.
- AR2-07: la nota de la vista previa, la Guía y estos documentos contradecían lo nuevo. Ya no: §1 y §5 de este documento, §8 de la lista y la Guía.

Mantiene el disenso fuerte de no cerrar por el verde, ahora por estos fallos, y llegó literal a Guillermo. Retira la queja de atribución exacta en las filas corregidas.

**Tercera revisión**, el 2026-11-10, sobre `7a047bf`: la revisión visual (VIS-01 a VIS-13) y los arreglos de la segunda. [Informe de Astra](astra/2026-11-10-ui-revision3-astra.md). Da por arreglados AR2-02 a AR2-05, y a medias AR2-01, AR2-06 y AR2-07. Otra vez NO APTO, con cinco hallazgos (AR3-01 a AR3-05), arreglados con su criterio + y − en la §11 de la lista de noviembre:

- AR3-01: la prueba del mapa medía la letra al pintarla y no al acabar, y tres maneras de dejar texto ilegible y un tablero de 2 px pasaban. Ahora mide cada letra también en el fotograma acabado, sigue las copias de píxeles con getImageData y putImageData y pide al rayado franjas con dirección. Así salió que, en los grupos densos, los marcadores tapaban media etiqueta; ahora las etiquetas se colocan al final, encima, donde no tapen ningún marcador ni otra etiqueta si hay sitio, a la derecha o a la izquierda (CU-38). Lo que esto aún no veía es AR4-01.
- AR3-02: una reconexión cortada a los 100 ms confirmaba la parada sin leer el juego. Ahora la lectura al volver solo vale si la conexión sigue igual cuando llega (D2 y B5).
- AR3-03: sin backend, Guardar decía «Guardado». Ahora dice que no se guarda, y en el menú sale apagado (CU-37).
- AR3-04: los documentos tenían reglas viejas junto a las nuevas. Ya no: la lista de noviembre, esta cabecera y este documento.
- AR3-05: la nota de la línea de tiempo perdía su final, «no mueve el juego». Ahora empieza por ahí, y la frase entera sale al pasar el ratón.

Mantiene el disenso fuerte de no cerrar por el verde, ahora por AR3-01 y AR3-02, y llegó literal a Guillermo. Retira la pérdida de Parar en la pantalla estrecha, «Nueva escena» sin backend, la rueda con Ctrl o Cmd, el Deshacer que juntaba dos elegidos y la contradicción de procedencia de la Guía. Ve la interfaz moderna y profesional, y conservaría los trece cambios visuales. Estos arreglos los revisó en la cuarta.

**Cuarta revisión**, el 2026-11-11, sobre `cd470c5`: los arreglos de la tercera, los iconos y la vista previa (UX-48 y UX-49) y los textos del mapa (UX-50). [Informe de Astra](astra/2026-11-11-ui-revision4-astra.md). Da por arreglados AR3-03 y AR3-05, y a medias AR3-01, AR3-02 y AR3-04; da por bien UX-48 y UX-50, y a medias UX-49. Otra vez NO APTO, con seis hallazgos (AR4-01 a AR4-06), arreglados con su criterio + y − en la §14 de la lista de noviembre:

- AR4-01: la prueba del mapa medía el lienzo y no la pantalla, y la letra en los píxeles que cubría al pintarla: un filtro de CSS en el mapa, una cifra tapada con su misma tinta, un texto pasado por un ImageBitmap y un rayado de un solo bloque pasaban. Ahora compara cada texto con la pantalla, mide el fondo cerca de cada píxel y los huecos de la letra, sigue las imágenes por ImageBitmap, da por no medido lo que no se sabe de dónde sale y pide que el rayado se repita (CU-38).
- AR4-02: la prueba de la vista previa solo miraba el lado largo de la planta, y una planta con el ancho al 20 % pasaba. Ahora mira los dos (CU-40).
- AR4-03: al reiniciar el servidor mientras rueda, la toma se quedaba sin confirmar al volver, y tocar la profundidad de campo la confirmaba con la lectura del mundo de antes. Ahora la vuelta del reinicio lee el mundo nuevo, donde ya no queda nada de la toma, y solo la vuelta de una conexión lee el juego (D2 y B5).
- AR4-04: una clase del catálogo sin tamaño rompía la vista previa. Ahora lo dice y no pinta ninguna medida (CU-40).
- AR4-05: al tope, el teclado no llegaba a la vista previa, y al escoger se perdía el foco. Ahora se recorre la lista sin poder pasar del tope, y el foco vuelve a su fila o a su pestaña (CU-40).
- AR4-06: con una clase que no está en el catálogo, Propiedades enseñaba la primera del catálogo como si fuera la suya. Ahora enseña la suya tal cual (CU-39).

Mantiene el disenso fuerte de no cerrar por el verde, ahora por AR4-01 a AR4-04, y llegó literal a Guillermo. Retira los cuatro ataques de su tercera revisión y la reconexión de 100 ms, que ahora fallan o se resuelven bien. Ve la interfaz moderna y profesional en los dos temas, más intuitiva al reconocer los objetos, y mantendría el diseño sin reabrir la letra, los colores, los nombres ni la densidad. Estos arreglos los revisó en la quinta.

**Quinta revisión**, el 2026-11-11, sobre `c6b5296`: los arreglos de la cuarta. [Informe de Astra](astra/2026-11-11-ui-revision5-astra.md). Da por arreglados AR4-04, AR4-05 y AR4-06, y a medias AR4-01, AR4-02 y AR4-03. Otra vez NO APTO, con cinco hallazgos (AR5-01 a AR5-05), arreglados con su criterio + y − en la §15 de la lista de noviembre:

- AR5-01: la prueba daba por buena en pantalla una letra que había borrado un filtro de CSS, porque aceptaba cualquier color entre los de sus vecinos. La pantalla pone el lienzo píxel a píxel, sin mezclarlo: ahora cada píxel de cada texto tiene que ser el suyo (CU-38).
- AR5-02: la prueba apartaba 48 px alrededor de lo que flota encima del mapa, y tres números junto a los controles quedaban sin mirar. Ahora solo aparta la caja de lo que flota, modela su sombra y no da por bueno un texto del que no se compara nada (CU-38); desde AR6-01, no aparta lo que lleva un recorte, y lo apartado queda sin comparar (AR7-02).
- AR5-03: un lienzo con WebGL al que se le cambiaba el tamaño perdía su marca de procedencia desconocida. Ya no la pierde (CU-38).
- AR5-04: la planta de la vista previa se medía por su caja, y una estrechada y girada pasaba. Ahora su caja vale si nada la gira ni la tapa; los lados que se ven, desde AR6-02 (CU-40).
- AR5-05: parar y reiniciar el servidor mientras dice «Parando…» confirmaba la toma con el mundo de antes. Ahora, si una conexión cambia mientras para, la parada se confirma leyendo el juego, en su mundo (D2 y B5).

Mantiene el disenso fuerte de no cerrar CU-38 ni la escala de CU-40 por el verde, por AR5-01 a AR5-04, y en parte el de las tomas, por AR5-05; llegó literal a Guillermo. Retira los cuatro ataques de su cuarta revisión, que ahora caen por su propiedad, y los obstáculos de datos ausentes, teclado al tope y clase desconocida. Ve la interfaz moderna y profesional, y no pide reabrir la letra, las filas, los radios, las sombras, el ámbar, los colores del mapa, la barra ni los nombres.

**Sexta revisión**, el 2026-11-12, sobre `5f513d9`: los arreglos de la quinta. [Informe de Astra](astra/2026-11-12-ui-revision6-astra.md). Da por arreglados AR5-01, AR5-03 y AR5-05, y a medias AR5-02 y AR5-04. Otra vez NO APTO, con tres hallazgos (AR6-01 a AR6-03), y los tres bloquean. Están arreglados y probados en la §16 de la lista de noviembre:

- AR6-01: la prueba apartaba la caja entera de lo que flota encima del mapa, también donde un recorte no la pinta, y un velo debajo tapaba parte de una cifra que seguía contando como leída. Ahora lo que flota con un recorte se compara, y un texto comparado a medias no pasa (CU-38); desde AR7-02 se dice así, porque lo apartado sigue siendo su caja.
- AR6-02: la planta de la vista previa con un contorno 10 px por dentro, de otro tamaño, pasaba con la misma caja y los mismos 12 puntos. Ahora la planta y su barra se miden en una captura (CU-40).
- AR6-03: abierta a 1600 × 960 y encogida a 1440 × 900, un número de la regla se pintaba encima de otro y lo dejaba a 1:1; ya pasaba en `c6b5296`. Ahora un número que caería encima de otro no se pinta (CU-38).

Retira su disenso sobre «Parando…» y mantiene Fallida para la toma cortada. Mantiene el disenso fuerte de no cerrar CU-38 ni la escala que se ve de CU-40 por el verde, por estos tres hallazgos; llegó literal a Guillermo. Ve la interfaz moderna, profesional e intuitiva, y no pide reabrir la letra, las filas, los radios, las sombras, el ámbar, los colores del mapa, la barra, los nombres ni C-17.

**Séptima revisión**, el 2026-11-12, sobre `fc28527`: los arreglos de la sexta. [Informe de Astra](astra/2026-11-12-ui-revision7-astra.md). Da por arreglados AR6-01, como garantía conservadora, y AR6-03, y a medias AR6-02. Otra vez NO APTO, con dos hallazgos de la prueba y no de la página (AR7-01 y AR7-02): el primero bloquea y el segundo es de gravedad baja. Están arreglados y probados en la §17 de la lista de noviembre:

- AR7-01: el contraste de la planta de la vista previa era el de su píxel más apartado del fondo, y un lado fuerte valía por tres flojos, a 2,90:1 en oscuro y a 2,19:1 en claro. Ahora cuenta cada tramo de sus lados y de los de su barra, sin redondear (CU-40).
- AR7-02: la prueba decía que lo que flota solo se aparta donde se pinta, y aparta su caja, también la de uno transparente. Ahora lo dice así: lo apartado queda sin comparar, que no es invisible, y un texto con algo sin comparar no pasa (CU-38).

Retira su negativa a cerrar CU-38 por AR6-01 y AR6-03, dentro de las vistas y la escala medidas, y los ataques geométricos de la sexta sobre CU-40; mantiene la de CU-40, ahora por AR7-01. Llegó literal a Guillermo. Mantiene su juicio favorable del diseño y la retirada de su disenso sobre «Parando…».

**Octava revisión**, el 2026-11-13, sobre `dde1345`: solo los arreglos de AR7-01 y AR7-02, y declarada la última. [Informe de Astra](astra/2026-11-13-ui-revision8-astra.md). Da AR7-02 por arreglado y AR7-01 a medias: su ataque y los cuatro mutantes caen, pero la prueba apartaba por su sitio el primer y el último píxel de cada tramo, y cinco guiones opacos débil-fuerte-débil, o un píxel débil en el extremo de la barra, pasaban. NO APTO con ese único hallazgo, AR8-01, de la prueba y no de la página. Retira su objeción a CU-38, mantiene la de CU-40 solo por AR8-01 y sigue viendo la interfaz moderna, profesional e intuitiva. Llegó literal a Guillermo, que pidió arreglarlo y mergear. Arreglado y probado en la §18 de la lista de noviembre:

- AR8-01: la prueba ya no aparta nada por su sitio. Mide cuánto cubre cada píxel lo pintado (dos capturas más, con lo de la fila de la planta en negro y en blanco) y exige 3:1 a todo píxel cubierto entero; los cubiertos en parte son antialias. Se cerraron además la esquina (valía el píxel más contrastado de la posición) y la primera fila de la barra, que no se miraba (CU-40). Los cuatro HTML de Astra son ahora mutantes oficiales y fallan.

## 12. Verificación y cambios

- `node ui/prototipo/pruebas.js` (Playwright con Chromium, 1600 × 960, tema oscuro, más el contraste en claro y oscuro): 64 de 64, código de salida 0, sin errores de JavaScript y sin ninguna petición fuera de la página. Con el prototipo anterior a los cambios de contraste, las dos comprobaciones nuevas fallan (62 de 64, código de salida 1).
- Capturas revisadas a mano: 1280 × 800, 1366 × 768 y 1440 × 900 (escena, sin backend y toma armada), tema claro y oscuro a 1600 × 960, móvil a 390 px con viewport y la Guía entera. A los tres anchos de portátil la barra superior cabe sin cortar nada.
- Lo que no prueba: nada del juego, del backend, de Dockview ni de Leaflet. El terreno del mapa es de ejemplo, no Chernarus.

**Noviembre (UX-01 a UX-14 y UX-25):**

- `node ui/prototipo/pruebas.js`: 64 de 64 en tres pasadas seguidas, código de salida 0. Cambiaron las comprobaciones de presentación, no las de operación ni seguridad. Las luces dicen «Tu juego» y están en la barra de estado. La cabecera dice «2 cambios sin aplicar» y la revisión va al pasar el ratón. El total del presupuesto está en Añadir. Aplicada quiere decir «Sin cambios por aplicar» con el botón libre, en vez de «Volver a aplicar». Consola pasa a Actividad, que empieza plegada. Desarmar y Parar se buscan en la barra de arriba, y la insignia dice «Rodando». El epoch se lee al pasar el ratón por el mapa de la barra de estado, y los Atajos se abren desde Herramientas. El simulador se cierra con un clic fuera, porque con la toma en marcha Esc la para. El contraste mira además Añadir, la leyenda y Herramientas.
- `node ui/prototipo/pruebas-mejoras.js`: los criterios de la lista de noviembre, 41 de 41 en cuatro pasadas. Contra el prototipo de antes (`git show de37c03:ui/prototipo/estudio.html` y `ESTUDIO_URL`) fallan todos los «+». Pasan solo cuatro «−» que ya se cumplían: previsualizar no arma ni rueda, una comprobación que falta impide rodar, un Parcial por respuesta perdida no ofrece «Reintentar» y Parar rueda en rojo. Allí da 6 de 39, contando las dos comprobaciones generales, con código de salida 1.
- Medidas con las mismas cuentas de la crítica, antes y después. El mapa ocupa el 34 % de la ventana a 1440 × 900 y ahora el 53 %; a 1366 × 768, el 29 % y ahora el 50 %. La barra de arriba tenía 13 controles; ahora tiene 11, de los que 8 son del producto y 3 del grupo del prototipo. En la escena recién abierta a 1600 × 960 había 31 textos con jerga, el 35 % en monoespaciada y el 49 % por debajo de 12 px; ahora, ninguno con jerga, el 1 % en monoespaciada y ninguno por debajo de 12 px.
- Capturas revisadas a mano: 1440 × 900 en oscuro y 1366 × 768 en claro, con la escena recién abierta, aplicada, con Mirek seleccionado y con la toma armada.
- Fallo que encontró la prueba y ya está arreglado: en tema claro, la etiqueta de la Guía quedaba a 4,47:1 sobre el fondo nuevo. El ámbar oscuro pasa de `#8d5506` a `#865106`.

**Segunda pasada (UX-18, UX-33 y UX-15) y arreglos de la revisión de Astra (AR-01 a AR-08):**

- `node ui/prototipo/pruebas-mejoras.js`: 66 de 66, código de salida 0. La segunda pasada dio 51 de 51 y, contra `10274b7`, 43 de 51; el detalle está en la §6 de la lista de noviembre. Con los arreglos de Astra, contra `7e2e5c6` da 54 de 66, con código de salida 1 y sin ningún caso cortado a medias. Fallan los ocho «+» de los arreglos y cuatro «−»; pasan los «−» que ya se cumplían y los casos que ahora miran el dibujo del mapa, que ya era correcto (el detalle está en la §7 de la lista).
- `node ui/prototipo/mutantes.js`: el control da 8 de 8 y los cuatro mutantes hacen fallar su caso, con código de salida 0.
- `node ui/prototipo/pruebas.js`: 64 de 64, con código de salida 0.
- La sonda del lienzo reproduce las medidas de Astra: el «6150» de antes, sobre un edificio, da 2,03:1 en oscuro y 2,21:1 en claro.
- Segunda medida, antes de la segunda ronda de Astra: en Windows, AR-03 + fallaba con el margen del 98 % por un hueco del halo dentro del «·», y la prueba de la barra no veía que las zonas se movían. Con el halo como imagen, la sonda sin margen y el criterio de no moverse, `pruebas-mejoras.js` sigue en 66 de 66, y contra `9d1a644` da 64 de 66 (falla AR-03 + en los dos temas). El detalle está en la §7 de la lista.
- Barra de estado a 1024, 1093, 1280, 1366, 1440 y 1600 px, con y sin backend, y a 390 px, con el cursor en 24 puntos del mapa: nada se pisa ni se sale. A 1024 y 1093 px, y sin backend a 1280, pasa a dos líneas.
- Capturas revisadas a mano: la página entera a 1280 × 800 en oscuro y a 1440 × 900 en claro, y la barra de estado en cada ancho.
- Fallos que encontraron las pruebas y ya están arreglados: en la segunda pasada, un bloque de la Guía dentro del fondo de los diálogos, que anulaba los atajos, y la ayuda nueva, que tapaba los botones del mapa; después, la barra de estado, que a 1280 px pisaba sus zonas y a 1024 sacaba «MCP apagado» del borde.

**5 de noviembre (UX-44, UX-45, UX-30, UX-46 y UX-47):**

- `node ui/prototipo/pruebas-mejoras.js`: 76 de 76, código de salida 0. Contra `76caccb`, el prototipo de antes de esta tanda, da 70 de 76: fallan los cinco «+» y UX-30 −, y pasan los «−» que ya se cumplían (el detalle está en la §8 de la lista de noviembre).
- `node ui/prototipo/mutantes.js`: el control da 9 de 9 y los cinco mutantes hacen fallar su caso; el nuevo pinta sin rayado al actor estimado.
- `node ui/prototipo/pruebas.js`: 64 de 64. Con la tabla de referentes de la Guía en 68 filas.
- Capturas revisadas a mano: la línea de ayuda con algo elegido, a 1280 × 800 y 1440 × 900, no tapa los botones del mapa; y Rodaje con Mirek estimado.

**Segunda revisión de Astra (AR2-01 a AR2-07):**

- `node ui/prototipo/pruebas-mejoras.js`: 99 de 99, código de salida 0. Contra `b106329`, los 23 casos de esta tanda dan 8 de 23: fallan todos los «+» menos el de escritorio, que no cambió, y los «−» de AR2-03 a AR2-07. La suite entera da 83 de 99, con código de salida 1 y sin ningún caso cortado a medias. Fallan los 15 de esta tanda y, de lo de antes, solo UX-09 −, que ahora mide los huecos del contorno del borrador. El detalle está en la §9 de la lista de noviembre.
- `node ui/prototipo/mutantes.js`: el control da 10 de 10 y los ocho mutantes hacen fallar su caso, también los tres que Astra dejó vivos.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.
- La sonda del mapa mide ahora lo que queda pintado: los textos que tocan en cada vista, las imágenes con texto y, en el fotograma acabado, los píxeles de las rayas y los huecos. La letra se mide al pintarla; en el fotograma acabado, desde la tercera revisión (AR3-01). Encontró que el contorno de los borradores casi no tenía huecos (0,1 px), por los extremos redondos que heredaba de las carreteras; ahora son planos.
- Capturas revisadas a mano: a 390 y 768 px rodando, arriba y desplazada hasta el final; el menú de la escena sin backend; la tecla del juego sin conexión, al pulsarla y 4 s después; y Rodaje en tema claro con la nota nueva.

**Revisión visual (VIS-01 a VIS-13):**

- `node ui/prototipo/pruebas-mejoras.js`: 125 de 125, código de salida 0. Contra `f9a7d97`, los 26 casos VIS dan 13 de 26, sin contar las dos comprobaciones generales, que también pasan: fallan los trece «+» y pasan los «−», que ya se cumplían, sin ninguno cortado a medias. El detalle está en la §10 de la lista de noviembre y en el [informe](2026-11-09-ui-revision-visual.md).
- `node ui/prototipo/mutantes.js`: el control da 10 de 10 y los ocho mutantes hacen fallar su caso.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.
- La página empieza por `<!doctype html>` y se pinta en modo estándar, abierta como archivo o publicada (VIS-07). Hasta aquí, las pruebas medían en modo de compatibilidad. Comparado caja a caja, el estudio es el mismo en los dos modos, desde 0,5 px; la Guía crece 44,5 px de 8938, como ya se veía publicada.
- Capturas revisadas a mano: antes y después de cada estado a 1366, 1440 y 1920 px, en los dos temas.

**Tercera revisión de Astra (AR3-01 a AR3-05), iconos y vista previa (UX-48 y UX-49):**

- `node ui/prototipo/pruebas-mejoras.js`: 159 de 159, código de salida 0. Contra `7a047bf`, lo que revisó Astra, los 18 casos AR3 dan 8 de 18: fallan los dos AR3-01 +, los tres AR3-02 −, AR3-03 − y los cuatro de AR3-05; pasan los seis «−» de AR3-01, que prueban la sonda, y AR3-02 + y AR3-03 +, que ya se cumplían. Los 16 de UX-48 y UX-49 dan 7 de 16: fallan los siete «+», el icono genérico y el aviso de que no hay captura. Las dos cuentas dejan fuera las dos comprobaciones generales, que también pasan; el detalle está en las §11 y §12 de la lista de noviembre.
- `node ui/prototipo/mutantes.js`: el control da 27 de 27 y los dieciocho mutantes hacen fallar su caso, también los cuatro de la tercera revisión de Astra.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.
- La sonda mide cada letra del mapa también en el fotograma acabado (AR3-01). En Rodaje con el cursor a 3 s, la peor letra al acabar pasa de 1:1 a 9,08:1 en oscuro, y de 1,01:1 a 10,78:1 en claro.
- Fallos que encontraron las pruebas y ya están arreglados: en los grupos densos, el marcador que se pintaba después tapaba media etiqueta; y, con los cuadrados más grandes de los iconos, en Rodaje con la vista alejada dos etiquetas se pintaban encima de otras.
- Capturas revisadas a mano, a 1440 × 900 en oscuro: la escena recién abierta, de cerca, Añadir con la vista previa y colocando; y Rodaje con la vista alejada a 1366 × 768. Fuera de las vistas que mide la prueba, un marcador o una etiqueta aún podían tapar parte de un número de la rejilla, y la regla, la leyenda y la línea de ayuda tapaban lo que caía debajo. Ya pasaba en `7a047bf`, se anotó en la §11 de la lista de noviembre y se arregló después (UX-50, abajo).

**Textos del mapa tapados o cortados (UX-50):**

- `node ui/prototipo/pruebas-mejoras.js`: 166 de 166, código de salida 0. Contra `e5a36bf`, los 7 casos de UX-50 dan 4 de 7, sin contar las dos comprobaciones generales, que también pasan: fallan los tres «+» y pasan los cuatro «−», que prueban la sonda. El detalle está en la §13 de la lista de noviembre.
- `node ui/prototipo/mutantes.js`: el control da 29 de 29 y los veintidós mutantes hacen fallar su caso, también los cuatro de UX-50.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.
- La sonda apunta la caja de cada texto del mapa, y la prueba la cruza con lo que flota encima del mapa y con su borde, que el lienzo no ve.
- Capturas revisadas a mano: a 1440 × 900 en oscuro, la escena recién abierta, de cerca y colocando. Los números de la regla se leen enteros encima de los marcadores, y no queda ningún texto bajo la escala, la leyenda o la ayuda, ni cortado por el borde.

**Cuarta revisión de Astra (AR4-01 a AR4-06):**

- `node ui/prototipo/pruebas-mejoras.js`: 203 de 203, código de salida 0. Contra `cd470c5`, lo que revisó Astra, los 37 casos AR4 dan 24 de 37, sin contar las dos comprobaciones generales: fallan los tres de AR4-03, los cuatro «−» de AR4-04, los cuatro de AR4-05 y los dos de AR4-06 con una clase que no está en el catálogo; pasan los de AR4-01 y AR4-02, que prueban la sonda y el criterio de la prueba, y dos «+» que ya se cumplían. El detalle está en la §14 de la lista de noviembre.
- `node ui/prototipo/mutantes.js`: el control da 29 de 29 y los veintiséis mutantes hacen fallar su caso, también los cuatro de la cuarta revisión de Astra, que con las pruebas de `cd470c5` sobreviven.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.
- La sonda compara con una captura de la pantalla los textos del mapa que no caen bajo lo que flota encima ni a 48 px de él, mide el fondo cerca de cada píxel de la letra y sus huecos, sigue las imágenes por ImageBitmap y da por no medido lo que no se sabe de dónde sale. Lo que esto aún no veía es AR5-01 a AR5-04.
- Capturas revisadas a mano, a 1440 × 900: la vista previa sin tamaño, Añadir al tope con el foco del teclado y Propiedades con una clase que no está en el catálogo.

**Quinta revisión de Astra (AR5-01 a AR5-05):**

- `node ui/prototipo/pruebas-mejoras.js`: 225 de 225, código de salida 0. Contra `c6b5296`, lo que revisó Astra, los 22 casos AR5 dan 19 de 22, sin contar las dos comprobaciones generales: fallan los tres de AR5-05 que miran el reinicio o el corte mientras dice «Parando…»; pasan los de AR5-01 a AR5-04, que prueban la sonda y el criterio de la prueba, y AR5-05 + sin cortes, que ya se cumplía. El detalle está en la §15 de la lista de noviembre.
- `node ui/prototipo/mutantes.js`: el control da 30 de 30 y los treinta mutantes hacen fallar su caso, también los cuatro de la quinta revisión de Astra, que con las pruebas de `c6b5296` sobreviven.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.
- Medido antes de cambiar la comparación con la pantalla, en 18 vistas de una tanda de este contenedor (Linux, con el Chromium de Playwright y la escala del navegador a 1): la escena recién abierta y Rodaje, a 1600 × 960 y a 1366 × 768 en los dos temas, a 1440 × 900 en claro, y a 1600 × 961, 1280 × 800, 1920 × 1080 y 1500 × 937 en oscuro: la pantalla pone el lienzo píxel a píxel, a 1 de 255 como mucho, también con el alto del mapa no entero, si la captura mide lo mismo que el lienzo, con 1 px de diferencia como mucho en cada dimensión. Ahora la sonda compara cada píxel de cada texto del mapa con el suyo de la captura, fuera de la caja de lo que flota encima, que queda sin comparar (hasta AR6-01, también la de lo que lleva un recorte), y de los 3 px del borde, con la sombra de lo que flota sacada de su box-shadow, y mira que en pantalla se lea.
- Capturas revisadas a mano, a 1440 × 900 en oscuro: Parar y reiniciar el servidor enseguida, con «Parando…», «Parada sin confirmar» al volver y la parada confirmada al leer el juego, con el mundo nuevo y sin «Control devuelto».

**Sexta revisión de Astra (AR6-01 a AR6-03):**

- `node ui/prototipo/pruebas-mejoras.js`: 246 de 246, código de salida 0. Contra `5f513d9`, lo que revisó Astra, los 21 casos AR6 dan 15 de 21, sin contar las dos comprobaciones generales: fallan las seis vistas encogidas de AR6-03, con un número de la regla encima de otro; pasan los de AR6-01 y AR6-02, que prueban la sonda y el criterio de la prueba, y los de AR6-03 abierta ya a su tamaño, que se cumplían. El detalle está en la §16 de la lista de noviembre.
- `node ui/prototipo/mutantes.js`: el control da 35 de 35 y los treinta y siete mutantes hacen fallar su caso, también los siete de la sexta revisión, seis de ellos ataques o negativos de Astra. Con las pruebas de `5f513d9`, los cinco de AR6-01 y AR6-02 sobreviven.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.
- Capturas revisadas a mano, en los dos temas: la esquina de la regla, abierta a 1600 × 960 y encogida a 1440 × 900 y a 1280 × 720, sin un número encima de otro, y la planta del autobús en la vista previa.

**Séptima revisión de Astra (AR7-01 y AR7-02):**

- `node ui/prototipo/pruebas-mejoras.js`: 260 de 260, código de salida 0. Los 14 casos AR7 prueban la sonda y el criterio de la prueba, no la página, que es la misma que en `fc28527`, byte a byte. El detalle está en la §17 de la lista de noviembre.
- `node ui/prototipo/mutantes.js`: el control da 39 de 39 y los cuarenta y un mutantes hacen fallar su caso, también los cuatro de la séptima revisión: su ataque y los tres negativos que pide, con los colores de su ataque en cada tema. Con las pruebas de `fc28527`, los cuatro sobreviven.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.

**Octava revisión de Astra (AR8-01)**, en el PC de Guillermo (Windows, escala 1):

- `node ui/prototipo/pruebas-mejoras.js`: 260 de 260, código de salida 0. La página no cambia.
- `node ui/prototipo/mutantes.js`: el control da 43 de 43 y los cuarenta y cinco mutantes hacen fallar su caso, código de salida 0; los cuatro nuevos son los HTML de Astra de AR8-01. Con la prueba de `dde1345`, el de los guiones y el de la barra daban 13 de 13.
- `node ui/prototipo/pruebas.js`: 64 de 64, código de salida 0.

Cambios del prototipo al consolidar: paleta y letra del DayZ Editor; los atajos de la sección 5; los gestos de Eden en el mapa y las rejillas; «Leer el suelo» al colocar; Parcial tras un corte después de entregar y su reconciliación; las tres luces y el backend caído; «Parando…», control devuelto, hombre muerto, bloqueo de edición durante la toma y la insignia de OBS; el total del presupuesto; «Probar ambiente» y «Leer el juego ahora»; la Guía con 54 referentes y su procedencia.

Fallos que encontraron las pruebas y ya están arreglados:

- La altura del suelo salía como «hace .» hasta el siguiente refresco.
- Una entidad nueva reutilizaba el id de una borrada que seguía en el juego y salía como «Cambiado» (#10 pide ids lógicos que no se repiten).
- A 1366 px la barra superior se salía de la pantalla, y a 1280 px se cortaba el nombre de la escena y se aplastaban las pestañas del panel de abajo.
- El aviso de mundo nuevo no se quitaba después de aplicar la escena en el mundo nuevo.
- Textos por debajo de WCAG AA: en oscuro, «Parar», la insignia «RODANDO» y la tecla Esc sobre el rojo (3,2 a 3,7:1), el contador azul de la Consola (2,26:1) y «Borrar» (4,49:1); en claro, los chips de estado (3,9 a 4,3:1), la etiqueta de la Guía (4,14:1) y la tecla Esc de Parar (4,36:1); en los dos, «se aplica al juego» (3,27:1) y las rayas de Parcial (3,7 y 4,3:1). El aviso «Backend de vuelta» salía en verde porque heredaba el color de los textos de éxito.
