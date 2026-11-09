# Revisión visual del estudio (2026-11-09)

Guillermo pidió que la interfaz «sea moderna y se vea bien» y antes había dicho que no parecía moderna ni profesional. La revisión visual miró el prototipo `ui/prototipo/estudio.html` tal como está en `f9a7d97`, buscó lo que se ve mal o descolocado y lo arregló sin tocar nada de lo decidido ni de lo probado: los seis estados de D2, Parar fijo en la barra de arriba, las tres luces y «MCP apagado», la letra del sistema a 13 px con el suelo de 12, las filas de 30 px, los radios y las sombras, el ámbar y el verde, los colores del mapa, la barra de arriba en una fila y los nombres de siempre. El dibujo del mapa tampoco se toca. Ningún token cambia de valor: lo que cambia es qué token usa cada pieza y cómo se colocan.

Quedan seis hallazgos, del más grave al menos grave. Los seis están arreglados y cada uno tiene un caso + y un caso − en `pruebas-mejoras.js`, en el bloque VIS. Al final van las cosas menores que no se arreglan, las propuestas para Guillermo y lo que se vio de paso y no es del aspecto.

## 1. Cómo se miró

- **Anchos y temas.** 1440 × 900, 1366 × 768 y 1920 × 1080, en oscuro y en claro. Para la cabecera de toma también 1280 × 800, 1600 × 960, 1024 × 768 y 390 × 844.
- **Estados.** Escena recién abierta, con algo elegido y con Añadir abierto; Rodaje armada y rodando; sin backend; fallo a mitad; y la Guía.
- **Capturas.** Cada estado tiene una captura de antes (`antes-<estado>-<ancho>-<tema>.png`) y otra de después (`despues-…`) con el mismo nombre. Las de 1440 × 900 de Escena y Rodaje van a doble resolución. Las capturas no van en el repositorio y se entregan aparte.
- **Barras de desplazamiento.** El navegador de las pruebas esconde las barras de desplazamiento, así que hay capturas aparte con las barras a la vista, antes y después: `tmp/scroll-obj-*.png` y `tmp/despues-scroll-obj-*.png`, y `tmp/antes-atajos-*.png` y `tmp/despues-atajos-*.png`. Allí se ven como en un navegador normal.
- **Recortes.** La cabecera de toma con una comprobación que falla (`tmp/antes-bloqueada-<ancho>.png` y `tmp/despues-bloqueada-<ancho>.png`) y la barra de arriba sin backend (`tmp/crop-top-sinbackend-*.png` y `tmp/despues-crop-top-sinbackend-*.png`).
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

## 3. Lo que se vio y no se cambia

**Menores, sin arreglar (R25).**

- **La barra de arriba mezcla altos.** El documento mide 36 px, Escena y Rodaje 34, los botones 30 y el grupo del prototipo 32.
- **El aviso de ayuda del mapa tapa la regla.** Es una tarjeta de dos líneas arriba a la izquierda que, a 1366 y 1440 px, tapa los primeros números de la regla de X. El grupo del zoom tapa los últimos (`antes-elegido-1440-dark.png`).
- **Las teclas pesan.** Dentro de los botones, las teclas («Intro», «Esc», «Mayús+F9») son cajitas con borde que pesan casi tanto como el nombre.
- **Las flechas de los campos numéricos.** Los campos numéricos enseñan las flechas del navegador al pasar el ratón.
- **Los nombres largos de Cámaras.** En la lista, «Travelling del autobús» se parte en dos líneas junto a «En la toma», y su resumen en otras dos (`antes-armada-1440-dark.png`).
- **La cabecera de toma más estrecha.** Por debajo de unos 1360 px va en dos filas fijas, más altas que la franja. Y con un nombre de cámara muy largo, el estado o el aviso se cortan antes con puntos suspensivos.

**Propuestas para Guillermo.**

- **La variante de la letra.** En Windows, los títulos, las pestañas y los botones usan la variante «Display» de Segoe UI Variable, pensada para letra grande, aunque van a 12 y 13 px. Para ese tamaño Microsoft tiene la variante «Text». Aquí no se puede ver, porque esta máquina no tiene Segoe UI, así que queda como propuesta [sin verificar]. La Guía dice que la familia es una elección propia.
- **Los dos temas.** La decisión del tema por defecto sigue abierta. Los dos temas se han revisado y los cambios valen igual en los dos.

**Fuera del aspecto (R20), anotado sin tocarlo.**

- **Punto y coma decimal.** Los campos de posición escriben «6196.0» con punto, y el resto de la interfaz «6195,97» con coma.
- **Un aviso que se queda.** Rodando, sigue a la vista el aviso «Toma 04 armada. Intro para rodar y Esc para desarmar.», que ya no vale (`antes-rodando-1440-light.png`).
- **Modo de compatibilidad.** El prototipo no empieza por `<!doctype html>`, así que abierto como archivo el navegador lo pinta en modo de compatibilidad, y las pruebas lo miran así. Una página publicada con su esqueleto se pintaría en modo estándar, y algunos detalles podrían cambiar.

## 4. Textos, Guía y consolidados

- **El único texto que cambia** es el aviso de la cabecera de toma por debajo de unos 1500 px: «En tu juego: «Parar toma» (Fin)» en vez de «También para desde tu juego, con «Parar toma» (Fin)». Lo pide VIS-01. Desde unos 1500 px sale entero, y entero también al pasar el ratón.
- **La Guía y «Acerca del diseño».** Ninguna de sus frases pasa a ser falsa. La fila de la cabecera de toma, «El transporte y el paso a emisión en una sola franja», ahora se cumple en todos los estados desde unos 1360 px; antes, a 1440 px, solo lista y parada. Por debajo de ese ancho la cabecera va en dos filas fijas.
- **Consolidados.** No se tocan. Ninguna frase pasa a ser falsa, pero dos quedan imprecisas:
  - En la tabla de tokens del consolidado de octubre, `--chassis · --bg` se usa para «Chasis, separadores y barras». Ahora `--bg` también pinta la cabecera y las pestañas de cada panel.
  - En la misma tabla, `--primary` es «La acción principal, una sola a la vista». Conviene añadir que, apagada, no lleva ámbar (VIS-05).

## 5. Pruebas

Cada corrida se lanzó sola, sin otra a la vez.

- **`node ui/prototipo/pruebas.js`**: `RESULT 64 pass, 0 fail`, con el repaso de contraste de todos los textos.
- **`node ui/prototipo/pruebas-mejoras.js`**: `RESULT 111 pass, 0 fail`. Son las 99 comprobaciones de antes y las 12 del bloque VIS, un caso + y un caso − por hallazgo, puestas justo antes de la comprobación de que ninguna petición sale de la página.
- **`node ui/prototipo/mutantes.js`**: el control pasa (`RESULT 10 pass, 0 fail`) y `RESULT 8 mutantes detectados, 0 sin detectar`.
- **Contra `f9a7d97`**, con `SOLO='^VIS'`: `RESULT 8 pass, 6 fail`. Fallan los seis casos +, pasan los seis − y las dos comprobaciones del final, y ningún caso se corta a medias. Esto es lo que dice cada + en `f9a7d97`:
  - **VIS-01 +.** A 1440 px la cabecera mide 46, 89, 59, 46 y 87 px según el estado, y a 1366 px el mapa empieza en cinco alturas distintas.
  - **VIS-02 +.** «Animales 5» se sale a 1366, 1440 y 1920 px, y la tira se desplaza.
  - **VIS-03 +.** Todas las barras piden «auto auto», la del sistema.
  - **VIS-04 +.** La cabecera y el cuerpo de cada panel, los dos en rgb(28, 30, 35).
  - **VIS-05 +.** «Aplicar escena» apagado sigue en el ámbar, rgb(233, 170, 60).
  - **VIS-06 +.** Anchos de 126, 145, 143, 91 y 123 px, en tres filas desiguales.

**Choques con las pruebas que ya había.** Ninguna comprobación se cambió ni se aflojó. Dos cambios chocaron con el repaso de contraste de `pruebas.js` y se quitaron:

- **El reloj a 22 px.** Rodando, en oscuro, dejaba de contar como texto grande, y su rojo se quedaba en 3,61:1. Sigue a 24 px.
- **La tira plegada de Actividad en el fondo de las barras.** El chip verde «Observado» bajaba a 4,49:1 en claro. La tira se queda en el fondo del panel.

## 6. Límites

- Las fuentes de esta máquina no son las de Windows: aquí salen Inter y DejaVu Sans Mono, en vez de Segoe UI Variable y Cascadia Mono. Los anchos se midieron con las de aquí, que son algo más anchas, así que en Windows debería sobrar algo de sitio.
- Las barras de desplazamiento se miraron en Chromium para Linux, donde la barra fina conserva dos flechas pequeñas, una arriba y otra abajo. Cómo la dibujan Chrome y Edge en Windows está [sin verificar].
