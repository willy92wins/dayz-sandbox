# Interfaz web del MVP de cine (M1): consolidado de Claude y Astra

2026-10-28 · Junta las dos lanes ciegas del [brief común](2026-10-28-ui-m1-brief.md): la de [Claude](2026-10-28-ui-m1-claude.md) y la de [Astra](astra/2026-10-28-ui-m1-astra.md) (Codex), por decisión de Guillermo («que la UI se haga entre Astra y tú»). Contrato: [product-spec.md](../product-spec.md) y el plan cerrado [plans/2026-10-26-m1-cine-v2.md](../plans/2026-10-26-m1-cine-v2.md). Si este documento choca con cualquiera de los dos, ganan ellos.

El diseño navegable es [prototipo/estudio.html](prototipo/estudio.html): una sola página con datos de ejemplo, sin backend, con un simulador de fallos del juego. Sus pruebas están en [prototipo/pruebas.js](prototipo/pruebas.js). La Guía del prototipo (botón «Guía») enseña la misma tabla de referentes que la sección 9.

**Estado:** consolidado y probado en el navegador. Falta la revisión cruzada de Astra sobre el prototipo consolidado (sección 11). Nada de esto toca el código de F0 ni el bridge.

## 1. Cómo se consolidó

- Las dos lanes recibieron el mismo brief y la regla de referentes de Guillermo («no lo hagáis a vuestro estilo, mirad lo que funciona»), sin ver la otra.
- Cada parte de la interfaz sale de un juego o una herramienta que ya funciona, con su fuente. Cuando las lanes diferían ganó el referente de prioridad más alta (1 DayZ Editor, COT y el mapa del juego; 2 Eden, Zeus, World Editor y Game Master de Reforger; 3 Rockstar Editor, Replay Mod, Fortnite y SFM; 4 Unreal, UEFN, Roblox y Blender; 5 el transporte de un DAW y OBS), salvo choque con el spec.
- Lo que solo existe en este producto va marcado PROPIO, con el criterio del spec que lo pide y el patrón conocido más cercano.
- La columna «Propuso» dice de dónde sale cada parte: **Claude**, **Astra**, **Las dos** (las dos lanes llegaron a lo mismo) o **Consolidación** (ninguna lo tenía así: salió al juntarlas o al probar el prototipo). De las 54 filas de la sección 9: Las dos 22, Astra 15, Claude 11 y Consolidación 6.

## 2. Arquitectura de la información

Un chasis común y dos modos, como el Game Master de Reforger cambia entre Game Master y Armavision.

- **Barra superior (los dos modos):** Escena y Rodaje (`1`, `2`); el documento con la revisión editada frente a la aplicada («r14 editada · r12 en el juego») y su menú de escena; deshacer y rehacer; la hora y el clima del documento; Resetear; Aplicar cambios con el número de cambios; las luces Backend, Servidor y Director con la edad del último latido; disposición de paneles, rejillas, atajos, referentes, el simulador y la Guía. Durante la toma se esconden Resetear y Aplicar y aparece Parar (o Desarmar) con su tecla.
- **Escena:** Jerarquía a la izquierda; mapa en el centro; Consola, Historial y Validación abajo; Propiedades y Biblioteca a la derecha, con el presupuesto al pie de la Biblioteca.
- **Rodaje:** Cámaras y Tomas a la izquierda; encima del mapa la claqueta (escena, toma, cámara, tiempo, los pasos Preparar, Armada, Rodando y Terminada, y los botones de la toma); Línea de tiempo y Consola abajo; Preparación y Propiedades a la derecha.
- **Barra de estado, que no se toca:** mundo (epoch), build del servidor, Expansion, mapa, errores y «MCP apagado».
- **Tres capas que nunca se mezclan:** el documento (lo que se edita; vive en el backend, #7), el juego (lo que hay de verdad, con su edad y su origen) y la toma (lo que se rueda).

## 3. Flujos

1. **Preparar la escena.** Biblioteca por tipo: clic en el nombre y clic en el mapa (Ctrl + clic para seguir colocando, clic derecho cancela), o Intro, que lo pone en el centro del mapa. Al colocar se lee el suelo en el servidor y Propiedades enseña la altura leída con su edad. Se mueve arrastrando, con las flechas (Alt, 0,1 m) o escribiendo X y Z; se gira con Mayús + arrastrar o escribiendo el rumbo. Las rejillas de movimiento y de giro se encienden y se apagan. Cada cambio es una transacción con nombre en el Historial (A5) y se guarda al momento.
2. **Aplicar.** `Ctrl+Intro` o el botón. La orden pasa por validar, reservar presupuesto, resetear, crear por lotes, leer y publicar (#9). Su fila en la Consola dice el estado de D2, el paso en curso, la edad y el origen. Solo una lectura la deja en Observado; si la respuesta se pierde después de entregarla, queda Parcial («Falta confirmar el resultado») y se reconcilia leyendo al volver la conexión (#23).
3. **Rodar.** En Rodaje, `Mayús+F9` o «Preparar toma» lee el juego: escena aplicada y observada, director conectado, cámara lista con su hash, vestuario, actores en su marca, hora y clima, y HUD. Cada lectura es una fila con su resultado y su arreglo («Reaplicar y preparar»). Solo con todo bien queda Armada, y entonces Intro rueda. La barra superior late y la insignia dice «RODANDO · El vídeo lo graba OBS».
4. **Parar.** `Esc`, `Espacio` o el botón. La toma queda en «Parando…» hasta que el cliente lo confirma, y Tomas apunta el control devuelto en segundos (B5 pide menos de 1 s). Con la toma armada, `Esc` desarma; `Espacio` nunca rueda.
5. **Resetear y repetir.** Tras una toma, «Reaplicar y preparar» aplica la escena entera y vuelve a armar (B6). Resetear quita del juego todo lo de la escena y deja el documento como estaba.
6. **Recargar.** «Recargar desde disco» y «Leer el juego ahora» están en las propiedades de la escena. Recargar la página vuelve a pintar lo último que da el backend.
7. **Cuando algo se cae.** Sin servidor, las órdenes nuevas se quedan Pendiente y caducan a Fallido «No se entregó». Sin backend, las luces quedan en gris con «hace X», un aviso lo dice, la Consola enseña «lo último que se supo» y no se puede guardar ni aplicar nada. Si se pierde el director o el backend durante la toma, la toma falla, su orden queda Parcial citando el hombre muerto del mod (F5) y se reconcilia al leer. Si el servidor se reinicia, aviso de mundo nuevo con el epoch nuevo hasta volver a aplicar.

## 4. Decisiones de la consolidación

Solo donde las lanes diferían o donde la prueba del prototipo cambió algo. El resto coincidía.

| Parte | Claude | Astra | Queda | Por qué |
|---|---|---|---|---|
| Paleta | Chasis oscuro verdoso con acento ámbar, paleta propia | Los tonos de la barra del DayZ Editor medidos en su captura pública (#0F0F0F, #1E1E1E, #FFFFFF) | Astra, con el mapa topográfico de Claude | DayZ Editor es prioridad 1; una paleta propia no tiene referente |
| Letra | Chakra Petch, IBM Plex Sans y Plex Mono, títulos en versalitas | Letra del sistema, sin mayúsculas forzadas | Astra | Los menús del DayZ Editor van en minúscula normal; su familia exacta no está verificada, así que no se copia ninguna |
| Botón principal | Ámbar | Blanco, como el texto y los iconos activos del DayZ Editor | Astra; el ámbar queda para la selección | Prioridad 1 |
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
| Rodando | Insignia REC que parpadea | Sin REC, «Vídeo externo: OBS» | Astra: «RODANDO · El vídeo lo graba OBS» | Grabar vídeo está fuera de M1 |
| Estado de la toma | En la misma pastilla que D2 | Dimensión aparte de los seis estados | Astra: cada toma lleva su etiqueta (Terminada, Parada, Fallida) | Una toma parada no es una orden observada |
| Luces de conexión | Servidor y Director | Backend, Servidor y Director, con su edad | Astra | #7: el documento vive en el backend |
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
| Aplicar cambios al juego (siempre con tecla, D4) | `Ctrl+Intro` | Propio: el Push Changes de UEFN no documenta tecla |
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

Gestos del mapa: clic selecciona; Ctrl + clic añade o quita; Mayús + clic selecciona seguidos (DayZ Editor). Arrastrar mueve lo seleccionado; Mayús + arrastrar lo gira (Eden). Botón derecho y arrastrar mueve el mapa y la rueda acerca (Eden). Mayús + clic derecho añade una marca al actor elegido (Eden). Las flechas mueven lo seleccionado con el paso de la rejilla y Alt mueve fino, 0,1 m y 1° (DayZ Editor). Lo bloqueado no se arrastra.

Reglas: los atajos no actúan mientras se escribe en un campo (`Esc` deshace lo escrito y `Ctrl+Intro` aplica). Una tecla mantenida no repite Aplicar, Preparar ni Rodar. `Intro` coloca mientras se está colocando y rueda con la toma armada: los dos contextos nunca coinciden. Los atajos son de la web y no llegan con DayZ en primer plano (punto abierto C-16).

## 6. Lenguaje visual

Base: la barra del DayZ Editor (superficies planas oscuras, iconos claros, grupos separados por líneas, menús con texto). El mapa es papel topográfico, como el mapa 2D de Eden. Los dos temas salen de los mismos tokens.

| Token | Oscuro | Claro | Uso |
|---|---|---|---|
| `--bg` y `--chassis` | `#0F0F0F` | `#F4F4F4` y `#E3E3E3` | Fondo |
| `--surface` · `--surface-2` · `--surface-3` | `#1E1E1E` · `#272727` · `#313131` | `#FFFFFF` · `#F2F2F2` · `#E7E7E7` | Paneles, campos y realces |
| `--line` · `--line-strong` | `#2D2D2D` · `#404040` | `#DADADA` · `#C3C3C3` | Bordes |
| `--fg` · `--fg-2` · `--muted` · `--faint` | `#FFFFFF` · `#CBCBCB` · `#9C9C9C` · `#6E6E6E` | `#0F0F0F` · `#3C3C3C` · `#646464` · `#8E8E8E` | Texto |
| `--primary` sobre `--primary-ink` | `#FFFFFF` con `#0F0F0F` | `#0F0F0F` con `#FFFFFF` | Botón principal (Aplicar, Rodar) |
| `--accent` | `#e9aa3c` | `#9a5d07` | Selección, tope alcanzado y paso actual |
| `--rec` | `#ef4a3e` | `#cc3226` | Rodando y Parar |
| `--cam` | `#71a8ee` | `#2459a6` | Cámaras y claves |
| `--st-pend` · `--st-exec` · `--st-appl` · `--st-obs` · `--st-fail` · `--st-part` | `#a0a0a0` · `#6fb2ee` · `#5fc6ba` · `#82c662` · `#f05b4d` · `#eb8d3a` | `#6b6b6b` · `#2a71b6` · `#128478` · `#398422` · `#c43327` · `#ab550c` | Estados de D2 |
| `--st-draft` | `#d4cba9` | `#7b7356` | Nuevo o cambiado en el documento |
| `--g-obj` · `--g-zmb` · `--g-ani` · `--g-act` | `#cfc7aa` · `#d3836c` · `#c6a767` · `#f5f2e8` | `#5b5446` · `#a8432f` · `#86691c` · `#1d1f19` | Objeto, infectado, animal y actor en el mapa |

- **Letra:** la del sistema (Segoe UI y Cascadia Mono en Windows), con monoespaciada para clases, coordenadas, hashes, edades y código de tiempo. Títulos sin mayúsculas forzadas.
- **Movimiento:** solo gira Ejecutando y late la barra superior al rodar; con `prefers-reduced-motion` no se mueve nada.

**Estados de una orden (D2), por forma además de color.** Es PROPIO (D2 y #23), apoyado en la cola de comandos de DZ Commander y en el Session Inspector de UEFN.

| Estado | Forma | Qué quiere decir |
|---|---|---|
| Pendiente | Anillo discontinuo | Validada en el backend; ningún mod la ha recogido. Si caduca sin entregarse, pasa a Fallido «No se entregó» |
| Ejecutando | Anillo tenue con un arco que gira | El mod la recogió y la está haciendo; dice el paso |
| Aplicado | Anillo con un punto, sin marca | El mod confirma que la hizo; falta leer el juego |
| Observado | Disco lleno con marca | Una lectura posterior lo confirma |
| Fallido | Octágono lleno con aspa | No se hizo, o la lectura no cumple; dice por qué |
| Parcial | Círculo medio lleno | Falló a mitad, o se perdió la respuesta después de entregarla. Sigue así hasta reconciliar: nunca vuelve a «no ocurrió» |

En la Jerarquía, el estado de cada entidad frente al juego va en cuadros discontinuos aparte (con un más si es nueva, con un punto si cambió, vacío si no está en el juego), para no confundirlo con una orden. En el mapa: relleno sólido es que está en el juego y la lectura coincide; contorno discontinuo, que está en el documento y todavía no en el juego; un fantasma y una línea, dónde sigue en el juego y adónde irá; todo discontinuo, que no hay nada en el juego. Cada tipo tiene su forma: objeto cuadrado, infectado triángulo, animal rombo, actor círculo con una raya hacia donde mira, cámara con su encuadre, marca disco con aro y clave rombo azul.

## 7. Criterios verificables para el brief de F6 (R26)

Juntan los UI-01 a UI-26 de Claude y los R26-01 a R26-39 de Astra; el detalle de cada caso está en la fila de origen. Corren con el mod falso de #24 salvo que digan «en partida», y cada uno tiene que poder ponerse en rojo con la inyección de fallos de #24. No hay umbrales nuevos: los números salen del spec o del plan. PASA quiere decir que el caso positivo y el negativo dan lo esperado; FALLA, que aparece la conducta prohibida; INCONCLUSO, que falta esquema, capacidad, montaje o muestra (regla de Astra, del plan). Lo que enseña la web no cierra por sí solo un gate del juego.

La columna «Prototipo» dice qué hace ya el prototipo con datos falsos: **Probado** (lo comprueba `pruebas.js`), **Se ve** (está en la página, sin prueba) o **No**.

| ID | Traza | Positivo | Negativo | Origen | Prototipo |
|---|---|---|---|---|---|
| CU-01 | D1 | Playwright hace el flujo entero desde un documento vacío (Biblioteca, Propiedades, guardar, aplicar, preparar, rodar, parar, resetear y recargar) solo con clics y teclas, y cruza cada paso con su orden en el backend por `op_id` y con lecturas del juego | Importar una fixture por API no acredita D1; sin el campo Rumbo en Propiedades la prueba falla, porque la fixture lo necesita | UI-01, R26-01, R26-38 | Probado en parte: aplicar, preparar, rodar, parar y reaplicar con teclas |
| CU-02 | A1, #7 | Las cinco fixtures inválidas (clase desconocida, fuera del mapa, presupuesto, campo extra y versión) enseñan su `code` y su ruta, y «Ver» selecciona lo señalado | El bridge no recibe ninguna orden y Aplicar está desactivado; bloquear solo el botón no basta; una ruta a algo que ya no existe queda en el resumen sin enfocar otra cosa | UI-06, R26-02, R26-03 | Probado: `out_of_map` y `expansion_unavailable` con su ruta y Aplicar desactivado |
| CU-03 | D2, #23 | Con eventos controlados se ven los seis estados con su forma, su edad frente a la marca del backend y su origen | Con el bridge caído, Pendiente pasa a Fallido «No se entregó» y nunca a Aplicado ni Observado; un 200 sin evento o una muestra vieja recibida ahora no dan Observado; sin marca de tiempo dice «Sin lectura», nunca «hace 0 s» | UI-02, UI-04, R26-28 | Probado |
| CU-04 | #23, #9 | Se pierde la respuesta después del efecto: Parcial, y al reconectar y leer, Observado («Reconciliada tras el corte») | Nunca vuelve a «No se entregó»; no hay reintento con otro `op_id`; reenviar el mismo `op_id` no añade entidades en el censo | UI-03, R26-04 | Probado |
| CU-05 | #9, A2 | Falla la creación de la entidad k: Parcial que la nombra y dice que se borró lo de esa orden; quitada la causa, aplicar llega a Observado. En partida, la fixture completa (20, 10, 3 y 2) da el multiconjunto exacto por clase y posiciones < 0,5 m | Quitar una raíz o moverla ≥ 0,5 m impide Observado; contar respuestas del spawner en vez de hacer el censo no acredita | UI-24, R26-04, R26-08 | Probado con el fallo simulado |
| CU-06 | A3 | Resetear deja cero entidades propias, hijos incluidos; un segundo reset no cambia nada; el documento sigue igual | Lo puesto a mano, otra escena o lo ajeno dentro de un contenedor propio sobreviven; si no se puede preservar, Parcial, nunca «Reset completado» | R26-10 | No (en partida) |
| CU-07 | A4 | Guardar, cerrar, cargar y reaplicar conserva el hash y el censo (< 0,5 m), con el mismo epoch y con otro; «Recargar desde disco» sin cambios da el mismo hash | Un guardado interrumpido deja la revisión anterior; si el fichero cambió fuera de la web, hash nuevo y aviso | UI-25, R26-07 | No |
| CU-08 | A5 | 20 operaciones variadas (una de varios a la vez y una de cámara), 20 `Ctrl+Z` y 20 `Ctrl+Y`: hash inicial y final; el Historial nombra cada una | Con la pila vacía, Deshacer está desactivado y no sale ninguna petición; deshacer nunca manda nada al juego; durante la toma, `Ctrl+Z` se rechaza con el motivo | UI-05, R26-06 | Probado en parte: el nombre en el Historial y el rechazo durante la toma |
| CU-09 | A6, #28 | Medidores por tipo frente a los topes provisionales (20, 10, 3 y 2) y total con prendas e hijos según el backend; al tope, ese tipo se desactiva en la Biblioteca | Tope + 1 en cualquier tipo, exceso solo de prendas o mezcla: `budget_exceeded` con ruta y cero órdenes; Intro sobre un elemento desactivado no manda nada; sumar máximos no sustituye el tope de S-perf | UI-07, R26-09 | Probado en parte: total «35 entidades + 9 prendas = 44 · tope: S-perf» |
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
| CU-25 | B5, D3 | Parar está a la vista y responde en los layouts de fábrica, con paneles movidos y con avisos (`elementFromPoint` en su centro) | Un panel, un diálogo o la recuperación de un layout que lo tape o lo capture falla | UI-12, R26-32 | Probado en el layout de serie |
| CU-26 | B4, F5 | HUD y barra rápida ocultos toda la toma; al salir (terminar, parar, fallo u hombre muerto) vuelven el control y el permiso de daño de antes | HUD visible, o daño puesto siempre a «sí» al salir, falla; sin cliente, `client_not_in_game` | R26-25 | No (en partida) |
| CU-27 | B6 | Tres tomas, cada una tras reset y reaplicación observados: mismos conteos, personajes y vestuario; actores a < 1,5 m de su marca; camino a < 0,5 m | Saltarse el reset, vestuario cambiado o una entidad de más bloquean la preparación; si el reset acaba Parcial, la cadena se para | UI-14, R26-26 | Probado: «Reaplicar y preparar» |
| CU-28 | B7, #19 | Al empezar cada toma se lee la hora (±1 min) y cada valor de clima actual (±0,01) | Un forecast correcto con el actual distinto, una muestra vieja o un campo inválido impiden arrancar; el valor pedido no rellena el observado | UI-15, R26-27 | Se ve: «Hora y clima del documento» |
| CU-29 | B7, E2, #27 | «Probar ambiente» y «Leer el juego ahora» piden una lectura nueva sin cambiar el documento | Mover un deslizador sin probar no toca el juego; probar no marca aplicada la revisión; durante la toma no se puede probar | R26-39 | Se ve |
| CU-30 | D2, #10, #22 | Recargar durante una orden o una toma recupera snapshot, revisión, generación, epoch y Parar; con epoch nuevo, aviso de mundo nuevo, entidades «no está en el juego» y toma desarmada | Un evento duplicado, fuera de orden o de un epoch viejo no hace retroceder el estado; reconectar no ejecuta órdenes caducadas; con el mismo epoch no hay aviso | UI-23, R26-29 | Probado en parte: aviso de mundo nuevo con su epoch, que se quita al aplicar |
| CU-31 | D3, #21 | El layout se guarda en el perfil del backend y vuelve igual tras recargar, también con el almacenamiento del navegador borrado; cambiar de modo no cambia el hash | Un perfil corrupto da el layout de fábrica con un aviso; guardarlo solo en el navegador incumple #21 | UI-17, R26-30 | No: el prototipo lo guarda en el navegador |
| CU-32 | D4 | Colocar, aplicar, preparar, rodar y parar solo con teclado; reasignar las cinco, recargar y repetir | Un conflicto avisa y no dispara dos órdenes; con el foco en un campo no se ejecutan; ninguna de las cinco se queda sin tecla; una tecla que atiende el navegador falla aunque el botón funcione | UI-18, R26-31 | Probado: teclas de serie, conflicto y obligatorias |
| CU-33 | E1, #22 | Con sesión válida en 127.0.0.1 la orden pasa; el token de los peers no aparece en `window`, en el DOM ni en el almacenamiento | Credencial inválida, Host u Origin falsos, origen de la LAN o TTL vencido: cero efectos; la web no ofrece «continuar de todos modos» | UI-21, R26-33 | No |
| CU-34 | E2, #27 | 100 operaciones (25 lecturas del servidor, 25 de suelo, 25 poses y 25 de ambiente): p95 < 1 s del navegador a lo observado | Retraso > 1 s en 10 o más, respuestas perdidas o solo acuses: falla | R26-34 | No |
| CU-35 | E3, E4 | Todo funciona con el MCP apagado y la barra de estado lo dice | Ninguna petición al MCP; evidencia de Diag presentada como retail deja la aceptación INCONCLUSA | UI-22, R26-35 | Se ve: «MCP apagado» |
| CU-36 | E5, A6, #28 | Escena al tope combinado con actores vestidos, cámara y toma: media > 35 FPS en tres ventanas de 60 s (suelo provisional de #28) | Un pico o un promedio instantáneo no acreditan; si falla, se revisa el presupuesto en S-perf, nunca desde la web | R26-36 | No |
| CU-37 | D2, #7, F5 | Sin backend: luces en gris con «hace X», aviso y Consola con lo último que se supo; al volver, el aviso se va | No se puede guardar ni aplicar nada y Propiedades se bloquean | Consolidación | Probado |

El manifiesto de cada prueba guarda revisión y hash, operación, epoch y generación, build y modset, y origen y hora de cada muestra (Astra, del plan). Son datos para cruzar evidencia, no un formulario para la creadora.

## 8. Puntos abiertos

### Para Guillermo

1. **Tema de serie:** oscuro (lo propuesto, por las sesiones largas junto al juego) o claro. Los dos están hechos.
2. **Pasos de las rejillas:** 0,5 m y 15° (Alt, 0,1 m y 1°) son propios. Si se verifican los de serie de Eden o del DayZ Editor, ganan esos.
3. **Parar desde dentro del juego (C-16):** hoy se para desde el navegador y, si algo se cae, el hombre muerto del mod (F5). Una tecla en el cliente queda fuera de M1 salvo que la quieras.
4. **Vista previa:** al mover el cursor de tiempo, los actores se mueven en el mapa con una velocidad supuesta (va rayado como estimación). La otra opción es enseñar solo sus marcas.
5. **Aplicar otra escena encima de la que hay en el juego:** Astra la bloquea hasta resetear la anterior; #9 ya resetea y crea. Recomiendo seguir #9 con un aviso que nombre la escena que se quita.
6. **Nombre de Aplicar:** «Aplicar cambios (n)», aunque aplica la escena entera (#9). Si sorprende en la prueba de uso, «Aplicar escena».

### Para los contratos (F1, F2 y los spikes)

- **C-02:** el tope combinado de A6 lo fija S-perf; la web lo lee del backend.
- **C-07:** la paridad de cámara con COT y PCT sigue pendiente del banco de cámara del plan.
- **C-09:** orden y reanudación de SSE, correlación del snapshot con los eventos y el TTL de una orden. El prototipo usa 10 s; la web enseñará el que devuelva el backend.
- **C-10:** esquema del enfoque, unidades de la orientación y rangos de cada campo.
- **C-11:** S3 decide ROAM, la lista final de gestos certificados y cómo se observa una cancelación.
- **C-12:** S-mapa decide la imagen, su calibración, la consulta de suelo y el rechazo de puentes y tejados.
- **C-13:** no hay contrato para muestrear la curva de cámara antes de rodar; por eso es «trayectoria prevista».
- **C-14:** el esquema de cues de actores de F5 no está escrito; si pide tiempos editables, la línea de tiempo se cierra contra ese esquema antes de implementarla.

## 9. Procedencia de cada parte

Las fuentes se consultaron el 2026-10-27 y el 2026-10-28.

| # | Parte de la interfaz | Referente | Qué se copia | Fuente | Propuso |
|---|---|---|---|---|---|
| 01 | Modos Escena y Rodaje en la barra superior | Game Master de Arma Reforger | La barra de arriba que cambia entre Game Master y Armavision | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Las dos |
| 02 | Paleta: fondo casi negro, paneles gris oscuro, texto y botón principal en blanco | DayZ Editor | Los tonos de su barra de herramientas, medidos en la captura pública | [raw.githubusercontent.com](https://raw.githubusercontent.com/wiki/InclementDab/DayZ-Editor/assets/images/toolbar.png) | Astra |
| 03 | Letra del sistema y títulos sin mayúsculas forzadas | DayZ Editor | Menús en minúscula normal y sin versalitas; su familia exacta no está verificada, así que no se copia | [raw.githubusercontent.com](https://raw.githubusercontent.com/wiki/InclementDab/DayZ-Editor/assets/images/toolbar.png) | Astra |
| 04 | Selección en ámbar, con color propio | DayZ Editor (Preferences) | El color de selección se ajusta aparte; el ámbar es propio | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.1-Preferences) | Consolidación |
| 05 | Jerarquía a la izquierda, agrupada y con buscador | Eden (Entity List) y World Editor de Reforger (Hierarchy) | Lista de todo lo que hay en la escena, agrupada | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Terminology) | Las dos |
| 06 | Bloquear y ocultar desde la jerarquía | DayZ Editor | Lock (L) y Unlock (Ctrl+L) | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Claude |
| 07 | Biblioteca por tipo con buscador | Eden (Asset Browser) y Game Master (Entity Browser) | Catálogo por tipo; clic en el nombre y clic en el mapa | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Entity_Placing) | Las dos |
| 08 | Colocar: clic, Ctrl + clic para seguir, clic derecho cancela | Eden y Game Master | Los mismos gestos de ratón | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Entity_Placing) | Las dos |
| 09 | Intro coloca lo elegido en el centro del mapa | PROPIO (D4: alternativa al arrastre), sobre Eden | El mismo flujo de colocar, sin ratón | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Entity_Placing) | Claude |
| 10 | Todo se coloca apoyado en el suelo | DayZ Editor (Ground Mode) | Lo colocado se apoya en el terreno; aquí siempre, porque D5 lo pide | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Las dos |
| 11 | Presupuesto por tipo al pie de la biblioteca; al tope no deja añadir más | Game Master de Reforger | Presupuestos a la vista junto al catálogo, que bloquean al llenarse | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Las dos |
| 12 | Total: entidades más prendas, con el tope combinado de S-perf | PROPIO (A6 y decisión #28), sobre Game Master | El desglose de lo gastado | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master) | Astra |
| 13 | Propiedades acopladas; doble clic las abre | World Editor de Reforger (Object Properties) y Eden (doble clic abre Attributes) | Panel de propiedades de lo seleccionado | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Las dos |
| 14 | Alt+Intro lleva a las propiedades | Explorador de Windows | Alt+Intro abre las propiedades de lo seleccionado; el Ctrl+T del DayZ Editor lo atiende el navegador | [support.microsoft.com](https://support.microsoft.com/en-us/windows/keyboard-shortcuts-in-windows-dcc61a57-8ff0-cffe-9796-cb9706c75eec) | Consolidación |
| 15 | Nueva escena sin tecla | Chromium | Ctrl+N, Ctrl+T y Ctrl+W las atiende el navegador antes que la página | [chromium.org](https://www.chromium.org/developers/design-documents/extensions/proposed-changes/apis-under-development/browser-keys/) | Consolidación |
| 16 | Menú de escena: nueva, abrir (Ctrl+O), guardar (Ctrl+S) y guardar como (Ctrl+Mayús+S) | DayZ Editor | El menú File y sus teclas | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Las dos |
| 17 | Ctrl+Z, Ctrl+Y, Ctrl+J, Ctrl+A, Supr, P (copiar coordenadas) e Y (ocultar la interfaz) | DayZ Editor (Ctrl+Y también en el World Editor de Reforger) | Las mismas teclas | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Las dos |
| 18 | Ambiente (fecha, hora y clima) como ajuste de la escena | DayZ Editor (Environment), Game Master (Scenario) y Eden | Fecha, hora y clima en un sitio propio, fuera de las entidades | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Las dos |
| 19 | Probar el ambiente en el juego sin aplicar la escena | DayZ Editor (Environment) | Hora y clima se cambian en vivo; aquí con un botón, porque editar no toca el juego (#7) | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Astra |
| 20 | Órdenes cortas con su estado: leer el suelo, leer el juego, probar el ambiente y mover la cámara | PROPIO (decisión #27 y E2), sobre el Session Inspector de UEFN | Cada operación con su paso en curso y su error | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Consolidación |
| 21 | Selección: clic, Ctrl + clic alterna, Mayús + clic selecciona seguidos | DayZ Editor | Make, Toggle y Continuous Selection | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Las dos |
| 22 | Mover con flechas y Alt + flechas despacio | DayZ Editor | Move XZ y Move Objects Slow; el paso de cada tecla es propio | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/4.-Shortcuts) | Claude |
| 23 | Arrastrar con el botón derecho mueve el mapa y la rueda acerca | Eden | La navegación del mapa con el botón derecho y la rueda | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Astra |
| 24 | Mayús + arrastrar gira lo seleccionado | Eden | Mayús + arrastrar con el botón izquierdo rota | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Astra |
| 25 | Rejillas de movimiento y de giro que se encienden y se apagan | Eden | Los botones de rejilla de traslación y de rotación de su barra; los pasos son propios | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Toolbar) | Astra |
| 26 | Encuadrar la selección (F) | World Editor de Reforger | Focus (F) | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Claude |
| 27 | Marcas de actor con Mayús + clic derecho | Eden | Mayús + clic derecho añade un waypoint rápido a lo seleccionado | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Actions) | Las dos |
| 28 | Mapa 2D con aspecto de mapa topográfico del juego | Eden | El mapa 2D usa el aspecto del mapa del juego, con iconos de entidades | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Las dos |
| 29 | Aplicar cambios con el número de cambios pendientes | UEFN | Push Changes empuja lo editado a la sesión en vivo | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/fortnite/first-island-04-playtest-your-island-in-fortnite) | Las dos |
| 30 | Aplicar resetea y crea la escena entera; Resetear la quita | PROPIO (decisión #9), sobre Eden | Al volver al editor, el escenario vuelve a su estado inicial | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Introduction) | Las dos |
| 31 | Revisión editada frente a la aplicada | PROPIO (A4 y decisión #7), sobre UEFN | Push Changes separa lo editado de lo que corre | [dev.epicgames.com](https://dev.epicgames.com/documentation/en-us/fortnite/first-island-04-playtest-your-island-in-fortnite) | Las dos |
| 32 | Claves de cámara: copiar y pegar ajustes, enfoque por clave | Rockstar Editor | Marcadores con cámara, profundidad de campo y ajustes copiables | [gtabase.com](https://www.gtabase.com/grand-theft-auto-v/rockstar-editor/) | Claude |
| 33 | Capturar la pose de la cámara libre | DayZ Editor | View › Dump Camera y los ajustes de cámara (FOV, desenfoque) | [github.com](https://github.com/InclementDab/DayZ-Editor/wiki/5.-Toolbar) | Las dos |
| 34 | Ver la trayectoria prevista de las cámaras (H) | Replay Mod | Toggle Path Preview con la tecla H | [badlion.net](https://www.badlion.net/wiki/replay-mod-keys) | Claude |
| 35 | Claves en una regla de tiempo: elegir, arrastrar y escribir el tiempo | Replay Mod | La línea de claves de posición y de tiempo de su editor de caminos | [replaymod.com](https://www.replaymod.com/docs) | Astra |
| 36 | Pistas de actores y ambiente bajo la cámara, con transporte | Sequencer de Unreal | Pistas a la izquierda, cursor que se arrastra e ir al principio, clave anterior, reproducir, clave siguiente e ir al final | [docs.unrealengine.com](https://docs.unrealengine.com/4.27/AnimatingObjects/Sequencer/ReferenceEditor) | Claude |
| 37 | Preparar y armar antes de rodar; lo preparado no sale hasta pulsar Rodar | PROPIO (decisión #4), sobre el Studio Mode de OBS | Preparar a un lado y pasarlo a emisión con un paso aparte | [obsproject.com](https://obsproject.com/kb/obs-studio-overview#studio-mode) | Las dos |
| 38 | Preparar la toma con Mayús+F9 | Ableton Live | Mayús+F9 arma la grabación | [ableton.com](https://www.ableton.com/en/manual/live-keyboard-shortcuts/) | Astra |
| 39 | Rodar con Intro cuando la toma está armada | Eden | Intro arranca la vista previa del escenario | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Preview) | Astra |
| 40 | Parar con Esc | World Editor de Reforger | Esc sale de la vista previa | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Claude |
| 41 | Espacio también para la toma que rueda | Ableton Live | Espacio para el transporte; aquí solo para y nunca arranca | [ableton.com](https://www.ableton.com/en/manual/live-keyboard-shortcuts/) | Consolidación |
| 42 | «Parando…» hasta que el cliente confirma la parada | PROPIO (B5 y decisión #23), sobre el transporte de Ableton | Parar se pulsa al momento; la confirmación llega aparte | [ableton.com](https://www.ableton.com/en/manual/live-keyboard-shortcuts/) | Astra |
| 43 | «Rodando» sin botón de grabar: el vídeo lo graba OBS | PROPIO (grabar vídeo está fuera de M1), sobre OBS | OBS es quien graba | [obsproject.com](https://obsproject.com/kb/obs-studio-overview#studio-mode) | Astra |
| 44 | Lista de tomas con su resultado | REAPER | Cada grabación nueva sobre la misma pista es una toma | [reaper.fm](https://www.reaper.fm/guides/REAPER%20Quick%20Start.pdf) | Claude |
| 45 | Durante la toma no se edita la escena | PROPIO (decisiones #4 y #7), sobre la vista previa de Eden | Probar y editar son momentos distintos | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Preview) | Astra |
| 46 | Consola abajo con filtros | World Editor de Reforger | Log Console con filtros de error, aviso e info | [community.bistudio.com](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor) | Claude |
| 47 | Barra de estado que no se toca | Eden | Status Bar no interactiva con información de depuración | [community.bistudio.com](https://community.bistudio.com/wiki/Eden_Editor:_Terminology) | Las dos |
| 48 | Reasignar atajos: avisa del choque y deja elegir Reemplazar o Cancelar | Unreal (Keyboard Shortcuts) | El aviso de conflicto con sustituir o cancelar | [dev.epicgames.com](https://dev.epicgames.com/documentation/unreal-engine/customizing-keyboard-shortcuts-in-unreal-engine?lang=en-US) | Astra |
| 49 | Colocar, Aplicar, Preparar, Rodar y Parar nunca se quedan sin tecla | PROPIO (D4), sobre Unreal | El mismo diálogo, que aquí no deja vaciarlas | [dev.epicgames.com](https://dev.epicgames.com/documentation/unreal-engine/customizing-keyboard-shortcuts-in-unreal-engine?lang=en-US) | Consolidación |
| 50 | Seis estados por orden: pendiente, ejecutando, aplicado, observado, fallido y parcial | PROPIO (D2 y decisión #23), sobre DZ Commander | Su cola de comandos: creado, enviado, confirmado | [dzcommander.com](https://dzcommander.com/) | Claude |
| 51 | Cada estado con forma y color, el paso en curso y el error con su detalle | PROPIO (D2), sobre el Session Inspector de UEFN | Una rueda en el paso en curso y un icono de error con su detalle | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Las dos |
| 52 | Backend, Servidor y Director con la edad del último latido; aviso de mundo nuevo | PROPIO (D2, E1 y decisión #10), sobre el Session Inspector de UEFN | El estado de la sesión siempre a la vista | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Astra |
| 53 | Errores de validación con código y ruta al campo | PROPIO (A1), sobre el Session Inspector de UEFN | Cada problema con su detalle y el sitio donde se arregla | [dev.epicgames.com](https://dev.epicgames.com/documentation/fortnite/uefn-session-inspector) | Las dos |
| 54 | Paneles que se ajustan y se agrupan; layouts guardados | Roblox Studio y Dockview (decisión #21) | Acoplar paneles y guardar la disposición (D3) | [create.roblox.com](https://create.roblox.com/docs/studio/overview#layout-customization) | Las dos |

## 10. Fuera de M1 (R25)

- Una tecla de parar dentro del cliente del juego.
- Una vista de calibración del mapa con los tres puntos de la georreferencia.
- Selección por recuadro en el mapa, cuando se verifique cómo la hace Eden.
- Composiciones reutilizables, exportar a otros editores y temas ampliables (C-05 de Astra).
- Una curva de cámara exacta frente al cliente, si B2 y un contrato de muestreo lo justifican.
- La paleta de comandos y el modo imán del DayZ Editor: no los pide el spec.
- Vista 3D, varios directores, grabar vídeo, cambiar de mapa, MCP e IA, y eventos: fuera del spec.

## 11. Revisión cruzada de Astra

Pendiente. Astra revisa el prototipo consolidado y este documento contra el spec, el plan y la regla de referentes, con atención a lo que se le quitó de su lane: editar durante Aplicar, Aceptar y Cancelar en Propiedades, el giro de un grupo (cada entidad sobre su eje; Eden podría girar sobre el centro del grupo [sin verificar]), la curva rotulada como prevista y `F1`, `Ctrl+F` e `Insert`.

## 12. Verificación y cambios

- `node ui/prototipo/pruebas.js` (Playwright con Chromium, 1600 × 960, tema oscuro): 62 de 62, código de salida 0, sin errores de JavaScript y sin ninguna petición fuera de la página.
- Capturas revisadas a mano: 1280 × 800, 1366 × 768 y 1440 × 900 (escena, sin backend y toma armada), tema claro y oscuro a 1600 × 960, móvil a 390 px con viewport y la Guía entera. A los tres anchos de portátil la barra superior cabe sin cortar nada.
- Lo que no prueba: nada del juego, del backend, de Dockview ni de Leaflet. El terreno del mapa es de ejemplo, no Chernarus.

Cambios del prototipo al consolidar: paleta y letra del DayZ Editor; los atajos de la sección 5; los gestos de Eden en el mapa y las rejillas; «Leer el suelo» al colocar; Parcial tras un corte después de entregar y su reconciliación; las tres luces y el backend caído; «Parando…», control devuelto, hombre muerto, bloqueo de edición durante la toma y la insignia de OBS; el total del presupuesto; «Probar ambiente» y «Leer el juego ahora»; la Guía con 54 referentes y su procedencia.

Fallos que encontraron las pruebas y ya están arreglados:

- La altura del suelo salía como «hace .» hasta el siguiente refresco.
- Una entidad nueva reutilizaba el id de una borrada que seguía en el juego y salía como «Cambiado» (#10 pide ids lógicos que no se repiten).
- A 1366 px la barra superior se salía de la pantalla, y a 1280 px se cortaba el nombre de la escena y se aplastaban las pestañas del panel de abajo.
- El aviso de mundo nuevo no se quitaba después de aplicar la escena en el mundo nuevo.
