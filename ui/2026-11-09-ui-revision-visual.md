# Revisión visual del estudio (2026-11-09)

Guillermo pidió que la interfaz «sea moderna y se vea bien» y antes había dicho que no parecía moderna ni profesional. La revisión visual miró el prototipo `ui/prototipo/estudio.html` tal como está en `f9a7d97`, buscó lo que se ve mal o descolocado y lo arregló sin tocar nada de lo decidido ni de lo probado: los seis estados de D2, Parar fijo en la barra de arriba, las tres luces y «MCP apagado», la letra del sistema a 13 px con el suelo de 12, las filas de 30 px, los radios y las sombras, el ámbar y el verde, los colores del mapa, la barra de arriba en una fila y los nombres de siempre. El dibujo del mapa tampoco se toca. Ningún token cambia de valor: lo que cambia es qué token usa cada pieza y cómo se colocan.

Quedan trece hallazgos. Los seis de la primera ronda (VIS-01 a VIS-06) van del más grave al menos grave. En una segunda ronda, a petición de la coordinación, se arregló también lo que la primera había dejado como menor o fuera del aspecto: son VIS-07 a VIS-13, en el orden en que se hicieron, porque el primero, el modo estándar, cambia la base de los demás. VIS-13 queda fuera del aspecto y lo pide la coordinación. Los trece están arreglados y cada uno tiene un caso + y un caso − en `pruebas-mejoras.js`, en el bloque VIS. Al final van las cosas menores que no se arreglan, las propuestas para Guillermo y lo que se vio de paso y no es del aspecto.

## 1. Cómo se miró

- **Anchos y temas.** 1440 × 900, 1366 × 768 y 1920 × 1080, en oscuro y en claro. Para la cabecera de toma también 1280 × 800, 1600 × 960, 1024 × 768 y 390 × 844.
- **Estados.** Escena recién abierta, con algo elegido y con Añadir abierto; Rodaje armada y rodando; sin backend; fallo a mitad; y la Guía.
- **Capturas.** Cada estado tiene una captura de antes (`antes-<estado>-<ancho>-<tema>.png`) y otra de después (`despues-…`) con el mismo nombre. Las de 1440 × 900 de Escena y Rodaje van a doble resolución. Las capturas no van en el repositorio y se entregan aparte.
- **Barras de desplazamiento.** El navegador de las pruebas esconde las barras de desplazamiento, así que hay capturas aparte con las barras a la vista, antes y después: `tmp/scroll-obj-*.png` y `tmp/despues-scroll-obj-*.png`, y `tmp/antes-atajos-*.png` y `tmp/despues-atajos-*.png`. Allí se ven como en un navegador normal.
- **Recortes.** La cabecera de toma con una comprobación que falla (`tmp/antes-bloqueada-<ancho>.png` y `tmp/despues-bloqueada-<ancho>.png`) y la barra de arriba sin backend (`tmp/crop-top-sinbackend-*.png` y `tmp/despues-crop-top-sinbackend-*.png`).
- **Segunda ronda.** Todas las capturas `despues-*` se rehicieron al final, ya en modo estándar. Hay recortes nuevos en `tmp/r2/`, de `f9a7d97` (`antes-*`) y de ahora (`despues-*`), en los dos temas, a doble resolución y a 1440 × 900: la barra de arriba con algo elegido (`barra`), las órdenes de lo elegido (`ordenes`), el menú Herramientas (`herramientas`), la toma armada (`armada`) y la pantalla entera rodando (`rodando`). Además, `tmp/r2/campo-ab.png` enseña la X con el ratón encima, arriba antes y abajo después, y `tmp/r2/camaras-ahora.png`, la lista de Cámaras de ahora en los dos temas.
- **Modo estándar.** Para ver qué mueve, el mismo archivo se abre dos veces, una sin `<!doctype html>`, en modo de compatibilidad, y otra con él. En las dos se hacen los mismos pasos y se compara cada caja a la vista, por su sitio en el árbol, desde 0,5 px. Se miraron 17 estados a 1440 × 900 en oscuro, 14 a 1366 × 768 en claro y 6 a 390 × 844, y la Guía.
- **La regla del mapa.** Dónde va cada número de la regla de X se saca del propio dibujo del mapa, con su placa, y se cruza con las cajas de lo que flota encima.
- **Referentes.** Para el comportamiento manda el orden de siempre. Para el aspecto pueden mandar el editor de Reforger, Unreal 5 y Blender 4. Lo que no se pudo comprobar en una fuente va marcado [sin verificar], y lo que es solo del producto, PROPIO, con el criterio del spec o del consolidado.

## 2. Hallazgos

| ID | Gravedad | Qué se ve mal | Qué se cambió | Referente |
|---|---|---|---|---|
| VIS-01 | Alta | La cabecera de toma cambia de alto con el estado y mueve el mapa hasta 43 px. Armada, «Rodar» cae a otra fila, lejos del reloj | Una sola franja de 46 px en todos los estados; más estrecho, dos filas fijas | Sequencer de Unreal y Control Bar de Ableton Live; fila 40 del consolidado de octubre |
| VIS-02 | Alta | En Añadir, la pestaña «Animales» se sale del panel a todos los anchos, y nada dice que hay una cuarta | Las cuatro pestañas se reparten el ancho y caben | PROPIO (UX-08), apoyado en el Asset Browser de Eden |
| VIS-03 | Media | Las barras de desplazamiento son las clásicas: anchas, grises y con flechas. Comen ancho y cortan nombres | Barras finas con los colores del tema, tenues, que se avivan con el ratón encima | Blender 4 |
| VIS-04 | Media | Los paneles se ven planos: cabecera, pestañas y cuerpo tienen el mismo gris | La cabecera y las pestañas van en el fondo de las barras; la pestaña activa, en el del panel | Blender 4 y Unreal 5 |
| VIS-05 | Media | En oscuro, «Aplicar escena» apagado parece un botón marrón encendido | La acción principal apagada se ve como cualquier botón apagado | PROPIO (tabla de tokens de octubre), apoyado en Blender |
| VIS-06 | Baja | Las órdenes de lo elegido forman una nube de cinco anchos distintos en tres filas desiguales | Dos columnas iguales | Blender 4 |
| VIS-07 | Media | Abierto como archivo, el prototipo se pinta en modo de compatibilidad, y publicado, en modo estándar: las pruebas miden otra página. En modo estándar, la línea «En el juego…» crece 1 px y empuja toda la Jerarquía | `<!doctype html>` al principio, y los iconos de estado ya no abren una línea de texto: en el estudio no se mueve nada | PROPIO, con la norma HTML y la del modo de compatibilidad |
| VIS-08 | Baja | En la barra de arriba, el documento mide 36 px, Escena y Rodaje 34, el grupo del prototipo 32 y los botones 30 | Todo a 30 px, en la misma fila de 44 | PROPIO (UX-03) |
| VIS-09 | Media | Con algo elegido o rodando, la ayuda del mapa, «Rodando» y el grupo del zoom tapan los números de la regla de X: a 1366 px, todos | Lo que flota arriba del mapa empieza debajo de los números | PROPIO (CU-38 y AR-03, la placa de los números) |
| VIS-10 | Baja | Dentro de los botones, las teclas son cajitas con borde y fondo que pesan casi tanto como el nombre | Texto tenue y sin caja, a 4,5:1 o más | Blender |
| VIS-11 | Baja | Con el ratón encima, los campos numéricos enseñan las flechas del navegador, pegadas al número | Sin esas flechas; siguen las del teclado y la rueda | Unreal 5 (`SSpinBox`) |
| VIS-12 | Baja | En Cámaras, «Travelling del autobús» se parte en dos líneas junto a «En la toma», y su resumen en otras dos | Nombre y resumen en una línea, con puntos suspensivos y enteros al pasar el ratón | Blender, y como la Jerarquía |
| VIS-13 | Baja, fuera del aspecto | Rodando, sigue a la vista «Toma 04 armada. Intro para rodar y Esc para desarmar.» | El aviso se quita al rodar | Lo pide la coordinación (con UX-14 y UX-41) |

### VIS-01. La cabecera de toma salta de alto (Alta)

**Qué se ve mal.** La cabecera de toma cambia de alto según el estado, y el mapa sube y baja con ella justo cuando hay que mirarlo.

- **A 1440 px** mide 46 px lista, 89 armada, 59 rodando, 46 parada y 87 con una comprobación que falla. Al armar, el mapa baja 43 px; al rodar, sube 30.
- **A 1366 px** mide 85, 89, 83, 46 y 87.
- **A 1280 px** mide 85, 89, 87, 85 y 87.
- **Armada** (`antes-armada-1440-dark.png`), «Rodar» cae a una segunda fila, debajo de «Toma 04» y lejos del reloj. La tecla «Fin» del aviso se queda sola en otra línea, entre paréntesis.
- **Rodando**, en claro, pasa lo mismo con el aviso (`antes-rodando-1440-light.png`).
- **Con una comprobación que falla** (`tmp/antes-bloqueada-1440.png`), el arreglo y su explicación bajan a otra fila.

**Referente.** Ningún referente de más prioridad tiene cabecera de toma, porque ni el DayZ Editor, ni COT, ni Eden, ni Zeus, ni Reforger graban tomas. Manda, por tanto, el Sequencer de Unreal.

- **Sequencer de Unreal.** Pone las herramientas en una barra: «The Sequencer Editor Toolbar contains a suite of tools, options and settings», y el transporte siempre en el mismo sitio: «The playback controls can be found in the bottom-left corner of Sequencer» ([docs de Unreal](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-cinematic-editor-unreal-engine)).
- **Ableton Live 12.** Lo junta en una sola barra: «The Control Bar is where you'll find Live's transport and tempo controls» ([manual de Live](https://www.ableton.com/en/live-manual/12/live-concepts/)).
- **El consolidado de octubre.** Ya lo pedía en la fila 40, con el Studio Mode de OBS: «El transporte y el paso a emisión en una sola franja».

**Cambio.**

- **Desde unos 1360 px de ventana**, con los paneles a su ancho de siempre, la cabecera es una sola franja de 46 px en todos los estados. De izquierda a derecha lleva el número, la cámara, el estado, el reloj y la acción que toca. Lo que cuenta es el ancho que queda para el mapa: si se ensanchan o se esconden los paneles, el cambio a dos filas llega antes o después.
- **Debajo del estado** va, en una segunda línea de 12 px, el aviso de «Parar toma» o la explicación de lo que falla. Si no cabe, se corta con puntos suspensivos; entera sale al pasar el ratón, y la de lo que falla también está en Preparación, al lado.
- **Por debajo de unos 1360 px** no cabe en una fila. Pasa a dos filas fijas de 83 px en total, que tampoco cambian con el estado: arriba, el número, la cámara y el reloj; abajo, el estado y la acción.
- **El aviso, más corto.** Por debajo de unos 1500 px, «También para desde tu juego, con «Parar toma» (Fin)» se acorta a «En tu juego: «Parar toma» (Fin)». Es el único texto que cambia en esta revisión, y lo pide este hallazgo: entero no cabe a 1366 ni a 1440 sin cortar la tecla. Desde unos 1500 px sale entero, como antes.
- **El reloj** sigue a 24 px. A 22 px dejaba de contar como texto grande, y el rojo de rodando bajaba a 3,61:1 en oscuro.

**Criterio.**

- **+** A 1280, 1366 y 1440 px, lista, armada, rodando, parada y con una comprobación que falla, la cabecera no cambia de alto y el mapa no se mueve. A 1366 y 1440 px, además, es una sola franja de 48 px o menos, con la acción en la fila del reloj. Armada o rodando, la tecla de «Parar toma» se ve entera. En `f9a7d97` falla.
- **−** A 1600 × 960, armada, la cabecera dice entera «También para desde tu juego, con «Parar toma» (Fin)» y el estado es solo «Armada». Rodando, el estado es solo «Rodando». A 390 px de ancho, la cabecera se parte en líneas sin salirse de la pantalla. Ya se cumplía en `f9a7d97`.

### VIS-02. La cuarta pestaña de Añadir se sale del panel (Alta)

**Qué se ve mal.** En Añadir, las cuatro pestañas de tipo miden 342 px y el panel 320. «Animales» queda cortada por el borde a 1366, 1440 y 1920 px (`antes-anadir-1440-light.png`). La tira esconde su barra, así que nada avisa de que hay una cuarta categoría ni de que se puede desplazar.

**Referente.** Es PROPIO, con el criterio de UX-08: «las categorías son pestañas con su cuenta». Una pestaña a medias incumple ese criterio. Se apoya en el Asset Browser de Eden (prioridad 2), donde el tipo es «the main functional filter, divides assets by entity types» ([wiki de Bohemia](https://community.bistudio.com/wiki/Eden_Editor:_Asset_Browser)), y un filtro escondido no filtra. Cómo dibuja Eden esa tira está [sin verificar].

**Cambio.** Las cuatro pestañas se reparten el ancho del panel a partes iguales, con 4 px de margen a cada lado en vez de 8. La tira conserva el desplazamiento por si alguna letra fuera más ancha.

**Criterio.**

- **+** A 1366, 1440 y 1920 px, las cuatro pestañas caben enteras en el panel y la tira no se desplaza. En `f9a7d97` falla.
- **−** Cada pestaña enseña su nombre y su cuenta enteros, a 12 px o más. «Animales» se puede elegir, y la elegida lleva el subrayado ámbar. Ya se cumplía en `f9a7d97`.

### VIS-03. Barras de desplazamiento clásicas (Media)

**Qué se ve mal.** Con las barras a la vista, cada panel, menú y diálogo lleva la barra clásica del sistema: 15 px de ancho, gris claro y con flechas arriba y abajo (`tmp/scroll-obj-dark.png` y `tmp/antes-atajos-dark.png`). En columnas de 256 y 320 px se come el ancho. En la Jerarquía corta «Contenedor abierto», que se queda en «Contenedor abie…». Y en oscuro es lo único que no sigue el tema.

**Referente.** En Blender 4 las barras son finas y tenues, y crecen y se avivan cuando el ratón se acerca: «Changes to scrollbars so that they are always visible, but thin and dim, and widen and become more visible as your mouse approaches» ([cambio de Blender, 2022](https://archive.blender.org/lists/bf-blender-cvs/2022-June/174991.html)).

**Cambio.**

- Todas las barras pasan a ser finas, con el color de los bordes fuertes y sin fondo.
- La del panel que tiene el ratón encima se aviva al gris de los textos secundarios.
- Las tiras de pestañas siguen sin barra.

**Criterio.**

- **+** La Jerarquía, Propiedades, los menús y la Guía piden una barra fina con los colores del tema, tenue. La del panel que tiene el ratón encima se aviva y la de los demás no. En `f9a7d97` falla.
- **−** A 1366 × 768, la Jerarquía se sigue desplazando, y las tiras de pestañas siguen sin barra. Ya se cumplía en `f9a7d97`.

### VIS-04. Paneles planos (Media)

**Qué se ve mal.** La cabecera de cada panel, sus pestañas y su cuerpo tienen el mismo gris. Solo los separan una línea de 1 px y el subrayado ámbar, y la pestaña activa no se distingue más que por ese subrayado (`antes-elegido-1440-dark.png` y `antes-armada-1440-light.png`). Es buena parte de lo que hace que la interfaz no parezca de un editor profesional.

**Referente.**

- **Blender 4.** El tema da colores propios a la pestaña activa, a las demás y al fondo de la tira: `tab_active`, `tab_inactive` y `tab_back`, este último con el nombre «Tab Background» ([cambio de Blender](https://projects.blender.org/archive/blender-archive/commit/80af3d685773d58dbe73dc697658ddf93e81b0b7)). Así la pestaña activa se ve unida a su panel.
- **Unreal 5 y Reforger.** El patrón de capas ya lo cita la Guía («tema oscuro por capas»), y Unreal 5 lo oscureció: «The default colors have been adjusted for a darker default theme» ([notas de Unreal 5.0](https://dev.epicgames.com/documentation/unreal-engine/unreal-engine-5.0-release-notes?application_version=5.0)). Cómo dibuja Unreal sus pestañas está [sin verificar].

**Cambio.**

- La cabecera y la tira de pestañas de cada panel van en el fondo de las barras, el mismo de la barra de arriba y la de estado.
- La pestaña activa va en el fondo del panel, así que se lee unida a lo que enseña, y conserva el subrayado ámbar.
- No cambia ningún valor de la paleta.
- La tira plegada de Actividad se queda como estaba. Con el fondo de las barras, el chip verde «Observado» bajaba a 4,49:1 en claro.

**Criterio.**

- **+** En oscuro, la cabecera de cada panel tiene un fondo distinto del cuerpo. La pestaña activa lleva el fondo del cuerpo, y las demás, el de la cabecera. En `f9a7d97` falla.
- **−** En claro, la pestaña activa sigue subrayada en ámbar, y los paneles, sus cabeceras y sus pestañas siguen sin radio ni sombra. El nombre de una pestaña sin elegir se lee a 4,5:1 o más sobre su cabecera; ahora a 5,28:1. Ya se cumplía en `f9a7d97`, a 5,77:1.

### VIS-05. La acción principal apagada parece encendida (Media)

**Qué se ve mal.** Sin backend, «Aplicar escena» está apagado, pero en oscuro se ve como un botón marrón y no como uno apagado (`antes-sinbackend-1440-dark.png` y el recorte `tmp/crop-top-sinbackend-dark.png`). Al lado, «Quitar del juego» apagado sí se ve gris. En claro sale un melocotón pálido. Pasa con cualquier acción principal apagada, como «Reaplicar y preparar» con la parada sin confirmar.

**Referente.** Es PROPIO, con la tabla de tokens del consolidado de octubre, que reserva el ámbar para «La acción principal, una sola a la vista» y deja lo desactivado en gris. Una acción que no se puede hacer no es la que toca ahora. Se apoya en Blender, donde lo que está apagado se dibuja en gris: `UILayout.enabled`, «When false, this (sub)layout is grayed out» ([API de Blender](https://docs.blender.org/api/4.2/bpy.types.UILayout.html)). Esa frase la devuelve el buscador en esa página, pero la página no se pudo leer entera: [sin verificar].

**Cambio.**

- La acción principal apagada se ve como cualquier botón apagado: el mismo fondo y el mismo borde que «Quitar del juego» apagado, igual de desvaída.
- Encendida, y mientras aplica («Aplicando…»), sigue en ámbar.

**Criterio.**

- **+** Sin backend, «Aplicar escena» apagado pierde el ámbar y se ve igual que «Quitar del juego» apagado. En `f9a7d97` falla.
- **−** Encendido, «Aplicar escena» sigue en ámbar con el texto oscuro, y mientras aplica también. Ya se cumplía en `f9a7d97`.

### VIS-06. Las órdenes de lo elegido, en una nube (Baja)

**Qué se ve mal.** Con un objeto elegido, Propiedades acaba con cinco botones de cinco anchos distintos (126, 145, 143, 91 y 123 px), repartidos en tres filas desiguales: Encuadrar y Coordenadas, Duplicar y Bloquear, y Borrar solo (`tmp/scroll-obj-dark.png`). Pasa lo mismo con varios elegidos.

**Referente.** En Blender 4 los botones de una rejilla pueden ir en columnas del mismo ancho: `UILayout.grid_flow` con `even_columns`, «All columns will have the same width» ([API de Blender](https://docs.blender.org/api/4.2/bpy.types.UILayout.html)). Esa frase también la da el buscador sin que la página se pudiera leer: [sin verificar].

**Cambio.**

- Las órdenes van en dos columnas iguales, con el icono y el nombre a la izquierda y la tecla a la derecha.
- Lo mismo para las de varios elegidos.

**Criterio.**

- **+** Con un objeto elegido, sus cinco órdenes van en dos columnas del mismo ancho y en tres filas. En `f9a7d97` falla.
- **−** Cada orden enseña su nombre y su tecla enteros, siguen con el alto de 26 px y «Borrar» sigue en rojo. Ya se cumplía en `f9a7d97`.

### VIS-07. El archivo se pinta en modo de compatibilidad (Media)

**Qué se ve mal.** El prototipo no empezaba por `<!doctype html>`. Abierto como archivo, el navegador lo pinta en modo de compatibilidad, y así lo miden las pruebas. La página publicada lleva su esqueleto y se pinta en modo estándar. Las dos no son iguales:

- **En la Jerarquía.** En modo estándar, el icono de la línea «En el juego, leída hace…» toma el alto de una línea de texto, 18,5 px en vez de sus 14, y sube 1,5 px. La línea crece 1 px y empuja 1 px hacia abajo todo lo que va debajo: con algo elegido cambian 530 cajas.
- **En el panel de abajo.** La celda con el estado de cada orden pasa de 20 a 20,5 px.
- **En la Guía** también cambian algunas cosas (§3).

**Referente.** Es PROPIO, porque ningún editor de la lista habla de esto. Lo que se aplica son las normas:

- **La norma HTML** pide el doctype: «DOCTYPEs are required for legacy reasons». Y sigue: «When omitted, browsers tend to use a different rendering mode that is incompatible with some specifications» ([HTML, §13.1.1](https://html.spec.whatwg.org/syntax.html)).
- **La norma del modo de compatibilidad** explica lo que se mueve. Una caja en línea sin texto, sin borde y sin relleno «must, for the purpose of line height calculation, act as if the box had a line-height of zero» ([Quirks Mode, §3.3](https://quirks.spec.whatwg.org)). En modo estándar no existe esa excepción: un icono solo en su línea toma el alto de una línea de texto.

**Cambio.**

- `<!doctype html>` al principio de `estudio.html`. Abierto como archivo o publicado, se pinta igual.
- Los iconos de estado son bloques y no abren una línea de texto. La celda del estado de cada orden del panel de abajo también deja de abrirla.
- Medido entre los dos modos, ninguna caja cambia 0,5 px o más en ninguno de los estados mirados:
  - 17 estados a 1440 × 900 en oscuro: Escena recién abierta, con un objeto elegido, con Mirek elegido y con Añadir abierto; Rodaje armada y rodando; sin backend; fallo a mitad con el panel de abajo abierto; los menús Herramientas y de la escena; los atajos; la validación; la toma parada; Tomas; la leyenda; Ambiente; y las etiquetas de los referentes;
  - 14 a 1366 × 768 en claro;
  - 6 a 390 × 844.
  
  Rodando solo cambia el ancho de «Rodando 00:00.62»: el reloj corre entre una página y otra, y unas veces la caja crece y otras encoge.
- Las pruebas que ya había pasan todas en modo estándar (§5).

**Criterio.**

- **+** El estudio, abierto con file://, se pinta en modo estándar. En `f9a7d97` falla: modo de compatibilidad.
- **−** La composición no se mueve. Se compara con una copia del mismo archivo sin doctype, en modo de compatibilidad. En Escena con algo elegido y el panel de abajo abierto, en Rodaje con la toma armada y sin backend, cada caja (unas 1750) está en el mismo sitio y con el mismo tamaño. Antes de medir se igualan los «hace N s», se paran las animaciones y se quitan los avisos, porque van con el reloj. Ya se cumplía en `f9a7d97`, donde las dos copias van en modo de compatibilidad. Sin el arreglo de los iconos falla, con 553 cajas que cambian.

### VIS-08. La barra de arriba mezcla altos (Baja)

**Qué se ve mal.** En la barra de arriba, el documento mide 36 px, Escena y Rodaje 34, el grupo del prototipo 32 y los botones 30 (`tmp/r2/antes-barra-dark.png`). Van centrados en la misma fila, pero sus bordes no se alinean ni arriba ni abajo, y la barra parece hecha de piezas sueltas.

**Referente.** Es PROPIO, con UX-03: la barra va en tres grupos y en una sola fila que cabe a 1366 px. Dos filas es UX-34, en la lista del NO. El estilo de las barras de herramientas de Unreal 5 tiene una propiedad `uniform_block_height` ([API de Python de Unreal](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/ToolBarStyle)), pero la página no dice qué hace: [sin verificar].

**Cambio.**

- **El documento** pasa de 36 a 30 px. Sus dos líneas, el nombre y «2 cambios sin aplicar · guardado hace…», van a 2 px una de otra en vez de a 3.
- **Escena y Rodaje** pasan de 34 a 30 px: cada botón, de 28 a 26 px, con 1 px de margen en vez de 2.
- **El grupo del prototipo** pasa de 32 a 30 px, con 1 px de margen en vez de 2.
- **Lo demás no cambia.** Los botones siguen en 30 px y la barra, en una fila de 44 px.

**Criterio.**

- **+** A 1366 y 1440 px, en Escena, armada y rodando, el documento, Escena y Rodaje, los botones y el grupo del prototipo miden lo mismo. En `f9a7d97` falla: 36, 34, 30 y 32 px.
- **−** A 1366 y 1440 px, en Escena, armada y rodando, la barra sigue en una fila de 44 px y cabe entera. Parar está en la barra, acaba en el mismo sitio armada y rodando, y nada lo tapa (B5). Ya se cumplía en `f9a7d97`.

### VIS-09. Lo que flota arriba del mapa tapa la regla (Media)

**Qué se ve mal.** Los números de la regla de X van arriba del mapa, sobre su placa, de 2 a 16 px del borde. La ayuda del mapa, «Rodando» y el grupo del zoom empezaban a 10 px, así que los tapaban (`antes-elegido-1440-dark.png` y `tmp/r2/antes-barra-dark.png`). Medido en `f9a7d97`:

- **Con «Bidón azul» elegido**, a 1366 y a 1440 px, quedan tapados los seis números que se ven: los primeros, por la ayuda, y los últimos, por el grupo del zoom.
- **Rodando**, «Rodando» y el grupo del zoom tapan cinco de seis a 1440 px y los seis a 1366.

**Referente.** Es PROPIO, con el consolidado de octubre: «En el mapa, los números de la rejilla van sobre una placa opaca y las etiquetas con un halo opaco de 4 px, porque pasan por encima de edificios y bosque» (CU-38 y AR-03). La placa está para que se lean, y una tarjeta encima los esconde igual. La ayuda sigue arriba a la izquierda, como pide UX-18.

**Cambio.**

- El grupo del zoom, la ayuda y «Rodando» empiezan a 24 px del borde de arriba del mapa en vez de a 10, debajo de los números. A los lados siguen a 10 px.
- El dibujo del mapa no cambia.

**Criterio.**

- **+** A 1366 y 1440 px, con algo elegido y rodando, ni la ayuda, ni el grupo del zoom, ni «Rodando» tapan ningún número de la regla de X. Dónde va cada número se saca del propio dibujo del mapa. En `f9a7d97` falla: los tapan todos o casi todos.
- **−** Con algo elegido, la ayuda sigue diciendo cómo moverlo, a 10 px del borde izquierdo del mapa, el grupo del zoom sigue a 10 px del derecho y «Acercar» sigue acercando. Rodando, «Rodando» sigue a 10 px del borde izquierdo. Ya se cumplía en `f9a7d97`.

### VIS-10. Las teclas pesan dentro de los botones (Baja)

**Qué se ve mal.** Dentro de los botones, de Escena y Rodaje y de los menús, cada tecla («1», «2», «F», «Ctrl+J», «Intro», «Esc»…) es una cajita con borde, fondo y relleno, y pesa casi tanto como el nombre del botón (`tmp/r2/antes-ordenes-dark.png` y `tmp/r2/antes-herramientas-dark.png`).

**Referente.**

- **Blender.** Desde la 2.80, la tecla de cada orden de los menús y de la barra de herramientas va más tenue. El cambio se titula «blender2.8: UI: Dim color of shortcut label in menus and toolbar» y dice: «The shortcut labels now use the "Item" theme color» ([cambio de Blender, 2018](https://archive.blender.org/lists/bf-blender-cvs/2018-July/111455.html)). El manual lo resume así: «All menu entries show the relevant shortcut keys, if any» ([manual de Blender](https://docs.blender.org/manual/en/3.4/interface/controls/buttons/menus.html)).
- **Unreal 5.** Cómo dibuja la tecla en sus menús está [sin verificar].

**Cambio.**

- **Dentro de un botón, de Escena y Rodaje o de un menú**, la tecla va en texto tenue, sin borde, sin fondo y sin relleno, y con peso normal. En los botones y los menús usa el gris de los textos secundarios.
- **En Escena y Rodaje, y sobre el ámbar**, como en «Rodar», la tecla va al 80 % del color del texto de su botón. Escena y Rodaje van sobre el color del chasis, donde ese gris se queda en 4,46:1 en claro.
- **En Parar**, la tecla va en el mismo color que el nombre, porque el blanco sobre el rojo no se puede atenuar sin bajar de 4,5:1.
- **Las teclas dentro del texto** siguen en su caja: en la ayuda del mapa, en la Guía, en el aviso de la cabecera de toma y en Propiedades sin nada elegido. Ahí la caja es lo que dice que es una tecla.
- **Contraste medido.** La tecla que menos llega a 5,62:1 en oscuro y a 4,71:1 en claro, y todas van a 12 px.

**Criterio.**

- **+** Las teclas dentro de los botones, de Escena y Rodaje y de los menús Herramientas y de la escena van sin borde, sin fondo y sin relleno, también en «Rodar» y en «Desarmar». En `f9a7d97` falla: «1», «2», «F», «P», «Ctrl+J» y las demás llevan caja.
- **−** En oscuro y en claro, cada tecla dentro de un botón encendido, de Escena y Rodaje o de un menú se lee a 4,5:1 o más sobre su fondo y a 12 px o más, también en «Rodar» y en «Desarmar». Las teclas dentro del texto, en la ayuda del mapa y en la Guía, siguen en su caja. Ya se cumplía en `f9a7d97`.

### VIS-11. Las flechas del navegador en los campos numéricos (Baja)

**Qué se ve mal.** Con el ratón encima, los campos numéricos de Propiedades (la X, la Z, el Rumbo…) enseñan las dos flechitas del navegador, pegadas al número y distintas de todo lo demás (`tmp/r2/campo-ab.png`, arriba).

**Referente.** En Unreal 5, el campo numérico, `SSpinBox`, es «a widget that provides keyboard-based and mouse-based manipulation of a numeric value», y con el ratón basta con «drag anywhere on the spinbox to change the value» ([API de Unreal](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Slate/SSpinBox)). La página no habla de flechas, así que si las lleva o no está [sin verificar]. Arrastrar para cambiar el valor es UX-29, que está en DESPUÉS, y aquí no se hace.

**Cambio.**

- Los campos numéricos piden el aspecto de un campo de texto, sin las flechas del navegador.
- El valor sigue cambiando con las flechas del teclado y con la rueda (UX-45), y con el foco el borde se sigue poniendo ámbar.

**Criterio.**

- **+** Los campos numéricos de Propiedades piden el aspecto de un campo de texto. Con el ratón en el extremo derecho de la X no salen las flechas: esa zona queda igual, píxel a píxel, con el ratón encima y sin él. En `f9a7d97` falla: salen las flechas.
- **−** Con el foco en la X, la flecha arriba la sube 0,1 m en un solo cambio del historial, y el borde se pone ámbar. La rueda encima de la Z la sigue subiendo 0,1 m por paso. Ya se cumplía en `f9a7d97`.

### VIS-12. Los nombres largos de Cámaras se parten (Baja)

**Qué se ve mal.** En la lista de Cámaras, a 1366 y 1440 px, «Travelling del autobús» se parte en dos líneas junto a «En la toma», y su resumen, «Camino · 3 claves · 6,0 s», en otras dos. Esa fila mide 89 px y las demás 53 (`antes-armada-1440-dark.png`).

**Referente.**

- **Blender.** Corta con puntos suspensivos el texto que no cabe. El cambio se titula «UI: Use Ellipsis for Short Truncated Text» y dice: «Allow use of ellipsis to indicate truncated text down to a single character» ([cambio de Blender, 2021](https://archive.blender.org/lists/bf-blender-cvs/2021-January/152634.html)).
- **La Jerarquía.** Ya corta así los nombres largos.

**Cambio.**

- El nombre y el resumen de cada cámara van en una línea. Lo que no cabe acaba en puntos suspensivos, y al pasar el ratón sale entero.
- «En la toma» va en la línea del nombre, y el resumen pasa por debajo con todo el ancho, así que no se corta.
- Todas las filas miden 53 px.

**Criterio.**

- **+** A 1366 y 1440 px, cada nombre y cada resumen van en una línea. El nombre cortado acaba en puntos suspensivos y se lee entero al pasar el ratón, y «En la toma» va en la línea del nombre. En `f9a7d97` falla: «Travelling del autobús» va en dos líneas, su resumen en otras dos, y ningún nombre sale entero al pasar el ratón.
- **−** A 1366 px, «Plano general» y «Primer plano de Linda» no se cortan, y «En la toma» se lee entero en una línea. Los resúmenes siguen diciendo «Fija» o el camino con sus claves y sus segundos, y un clic en una cámara la elige. Ya se cumplía en `f9a7d97`.

### VIS-13. El aviso de la toma armada se queda al rodar (Baja, fuera del aspecto)

**Qué se ve mal.** Al armar sale «Toma 04 armada. Intro para rodar y Esc para desarmar.», que dura 3,4 s. Si se rueda antes, el aviso sigue a la vista rodando, cuando Esc ya no desarma sino que para (`antes-rodando-1440-light.png`). Lo mismo pasa con «Espacio solo para una toma que rueda. Intro rueda y Esc desarma.», que sale al pulsar Espacio con la toma armada.

**Referente.** Queda fuera del aspecto: lo pide la coordinación, porque rodando dice «Esc para desarmar» y ya no vale. No cambia cómo salen los avisos. Siguen saliendo de uno en uno, abajo en el centro del mapa (UX-14), y los de fallo se siguen yendo solos, porque UX-41, que los dejaba fijos, está en el NO.

**Cambio.** Al rodar se quitan los dos avisos de la toma armada. Los demás no se tocan.

**Criterio.**

- **+** Al rodar, el aviso «Toma NN armada…» ya no está a la vista, ni el que sale con Espacio y la toma armada. En `f9a7d97` falla: los dos siguen a la vista rodando.
- **−** Armada, sigue saliendo «Toma NN armada. Intro para rodar y Esc para desarmar.». Los demás avisos no cambian. Sin backend sale «Backend parado…» con la franja de conexión. Intro dice «Sin conexión con el backend: la toma no sale de la web.», la toma no rueda y el aviso sigue a la vista un segundo después. Ya se cumplía en `f9a7d97`.

## 3. Lo que se vio y no se cambia

**Menores, sin arreglar (R25).** Las cinco que la primera ronda dejaba aquí, de la barra de arriba a los nombres de Cámaras, se arreglaron en la segunda (VIS-08 a VIS-12).

- **La cabecera de toma más estrecha.** Por debajo de unos 1360 px va en dos filas fijas, más altas que la franja. Y con un nombre de cámara muy largo, el estado o el aviso se cortan antes con puntos suspensivos.
- **Los números de la regla de Y.** Van a la izquierda del mapa, y alguno puede quedar debajo de la ayuda, de «Rodando» o de la escala con la leyenda, según dónde caiga la rejilla. VIS-09 mira solo la regla de X, que es lo que se pidió.
- **La Guía, en modo estándar.** Es una página de lectura y ahora se pinta como ya se veía publicada. Frente al modo de compatibilidad crece 44,5 px de 8938:
  - las tarjetas que empiezan con una etiqueta («Documento», «Juego» y «Toma», y las de los seis estados), 1 px;
  - la línea con la etiqueta de los consolidados y sus fechas, de 18 a 21 px;
  - la tabla de referencias, 39 px de 4841. En modo de compatibilidad las tablas no heredan la variante de la letra, así que ahora sus números van en `tabular-nums` y las columnas cambian de 1 a 5 px. Lo dice la norma HTML, que en sus reglas para las tablas («In quirks mode, the following rules are also expected to apply:») pone `font-variant` en `initial` ([HTML, Rendering](https://html.spec.whatwg.org/rendering.html)).
  
  Igualarlo pediría reglas que solo copian un comportamiento antiguo de los navegadores (R25).

**Propuestas para Guillermo.**

- **La variante de la letra.** En Windows, los títulos, las pestañas y los botones usan la variante «Display» de Segoe UI Variable, pensada para letra grande, aunque van a 12 y 13 px. Para ese tamaño Microsoft tiene la variante «Text». Aquí no se puede ver, porque esta máquina no tiene Segoe UI, así que queda como propuesta [sin verificar]. La Guía dice que la familia es una elección propia.
- **Los dos temas.** La decisión del tema por defecto sigue abierta. Los dos temas se han revisado y los cambios valen igual en los dos.

**Fuera del aspecto (R20), anotado sin tocarlo.**

- **Punto y coma decimal.** Los campos de posición escriben «6196.0» con punto, y el resto de la interfaz «6195,97» con coma.
- **Lo que la primera ronda anotaba aquí.** El aviso de la toma armada que se quedaba rodando y el modo de compatibilidad se arreglaron en la segunda ronda (VIS-13 y VIS-07).

## 4. Textos, Guía y consolidados

- **El único texto que cambia** es el aviso de la cabecera de toma por debajo de unos 1500 px: «En tu juego: «Parar toma» (Fin)» en vez de «También para desde tu juego, con «Parar toma» (Fin)». Lo pide VIS-01. Desde unos 1500 px sale entero, y entero también al pasar el ratón.
- **La segunda ronda no cambia ningún texto**, pero cambian dos cosas que se leen:
  - En Cámaras, al pasar el ratón por el nombre o el resumen de una cámara sale ese mismo texto entero (VIS-12). Antes salía la huella de las claves, que sigue saliendo en el resto de la fila.
  - Los dos avisos de la toma armada se quitan al rodar, sin esperar a sus 3,4 s (VIS-13).
- **La Guía y «Acerca del diseño».** Ninguna de sus frases pasa a ser falsa. La fila de la cabecera de toma, «El transporte y el paso a emisión en una sola franja», ahora se cumple en todos los estados desde unos 1360 px; antes, a 1440 px, solo lista y parada. Por debajo de ese ancho la cabecera va en dos filas fijas. En modo estándar la Guía se recoloca un poco (§3), pero no cambia lo que dice.
- **Consolidados.** No se tocan. Ninguna frase pasa a ser falsa, pero dos quedan imprecisas:
  - En la tabla de tokens del consolidado de octubre, `--chassis · --bg` se usa para «Chasis, separadores y barras». Ahora `--bg` también pinta la cabecera y las pestañas de cada panel.
  - En la misma tabla, `--primary` es «La acción principal, una sola a la vista». Conviene añadir que, apagada, no lleva ámbar (VIS-05).
  
  Con la segunda ronda siguen ciertas las frases que la tocan. La ayuda del mapa sigue siendo «una línea arriba a la izquierda» (octubre y UX-18), ahora 14 px más abajo. Los números de la rejilla siguen sobre su placa (CU-38), y la rueda de los campos sigue como dice UX-45.

## 5. Pruebas

Cada corrida se lanzó sola, sin otra a la vez. Estas son las de después de la segunda ronda, ya en modo estándar.

- **`node ui/prototipo/pruebas.js`**: `RESULT 64 pass, 0 fail`, con el repaso de contraste de todos los textos.
- **`node ui/prototipo/pruebas-mejoras.js`**: `RESULT 125 pass, 0 fail`. Son las 99 comprobaciones de antes y las 26 del bloque VIS, un caso + y un caso − por hallazgo, puestas justo antes de la comprobación de que ninguna petición sale de la página.
- **`node ui/prototipo/mutantes.js`**: el control pasa (`RESULT 10 pass, 0 fail`) y `RESULT 8 mutantes detectados, 0 sin detectar`.
- **Contra `f9a7d97`**, con `SOLO='^VIS'`: `RESULT 15 pass, 13 fail`. Fallan los trece casos +, pasan los trece − y las dos comprobaciones del final, y ningún caso se corta a medias. Esto es lo que dice cada + en `f9a7d97`:
  - **VIS-01 +.** A 1440 px la cabecera mide 46, 89, 59, 46 y 87 px según el estado, y a 1366 px el mapa empieza en cinco alturas distintas.
  - **VIS-02 +.** «Animales 5» se sale a 1366, 1440 y 1920 px, y la tira se desplaza.
  - **VIS-03 +.** Todas las barras piden «auto auto», la del sistema.
  - **VIS-04 +.** La cabecera y el cuerpo de cada panel, los dos en rgb(28, 30, 35).
  - **VIS-05 +.** «Aplicar escena» apagado sigue en el ámbar, rgb(233, 170, 60).
  - **VIS-06 +.** Anchos de 126, 145, 143, 91 y 123 px, en tres filas desiguales.
  - **VIS-07 +.** Modo de compatibilidad (`BackCompat`).
  - **VIS-08 +.** En Escena, armada y rodando, a 1366 y 1440 px: el documento a 36 px, Escena y Rodaje a 34, los botones a 30 y el grupo del prototipo a 32.
  - **VIS-09 +.** Con algo elegido, los seis números de la regla de X, tapados a 1366 y 1440 px. Rodando, cinco de seis a 1440 px y los seis a 1366.
  - **VIS-10 +.** «1», «2», «F», «P», «Ctrl+J» y las demás teclas de los botones, con caja.
  - **VIS-11 +.** Los campos piden el aspecto `auto`, y con el ratón encima salen las flechas.
  - **VIS-12 +.** «Travelling del autobús» en dos líneas, su resumen en dos, y ningún nombre entero al pasar el ratón.
  - **VIS-13 +.** Rodando, siguen a la vista «Toma 04 armada…» y «Espacio solo para una toma que rueda…».

**Choques con las pruebas que ya había.** Ninguna comprobación se cambió ni se aflojó. En la primera ronda, dos cambios chocaron con el repaso de contraste de `pruebas.js` y se quitaron:

- **El reloj a 22 px.** Rodando, en oscuro, dejaba de contar como texto grande, y su rojo se quedaba en 3,61:1. Sigue a 24 px.
- **La tira plegada de Actividad en el fondo de las barras.** El chip verde «Observado» bajaba a 4,49:1 en claro. La tira se queda en el fondo del panel.

En la segunda ronda no chocó ninguno. Dos colores de tecla de VIS-10 no llegaban a 4,5:1 y no se usaron: el gris de los textos secundarios en Escena y Rodaje (4,46:1 en claro) y el blanco atenuado en Parar. Y el caso − de VIS-07, que lo compara todo, encontró la celda del estado de las órdenes medio píxel más alta en modo estándar. Se arregló esa celda, y la comparación anterior, que solo avisaba de diferencias de más de 0,5 px, no la había visto.

## 6. Límites

- Las fuentes de esta máquina no son las de Windows: aquí salen Inter y DejaVu Sans Mono, en vez de Segoe UI Variable y Cascadia Mono. Los anchos se midieron con las de aquí, que son algo más anchas, así que en Windows debería sobrar algo de sitio.
- Las barras de desplazamiento se miraron en Chromium para Linux, donde la barra fina conserva dos flechas pequeñas, una arriba y otra abajo. Cómo la dibujan Chrome y Edge en Windows está [sin verificar].
- El modo estándar (VIS-07) y los campos sin flechas (VIS-11) se miraron solo en Chromium. En Firefox y Safari está [sin verificar].
