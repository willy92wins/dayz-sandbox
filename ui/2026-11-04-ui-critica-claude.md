# Crítica de la interfaz M1: lane de Claude

2026-11-04 · Lane ciega: Astra escribe la suya a la vez sin ver esta, y después se juntan. Parte de lo que dijo Guillermo: «No parece moderna ni profesional, y creo que es poco intuitiva. Hay que mirar mejoras». Sigue mandando su regla de referentes: copiar lo que funciona en otros juegos y editores, no un estilo propio.

Qué se ha mirado: el prototipo del commit `de37c03` (`ui/prototipo/estudio.html`) recorrido como una creadora de machinima que viene de DayZ, Arma o Reforger, a 1440 × 900 y 1366 × 768, en los dos temas, en Escena, con una selección, en Rodaje con la toma armada y en la Guía. Las cifras salen de un script de Playwright sobre la página (tema oscuro, Escena recién abierta). El contrato no cambia: [product-spec.md](../product-spec.md), el plan [2026-10-26-m1-cine-v2.md](../plans/2026-10-26-m1-cine-v2.md) y el [consolidado](2026-10-28-ui-m1-consolidado.md).

## 1. Veredicto

Enseña todo a la vez y con el mismo peso: el mapa, que es el escenario, ocupa el 34 % de la pantalla a 1440 × 900 y el 29 % a 1366 × 768. Habla como una herramienta de depuración: 27 textos con clases, revisiones, hashes e ids a la vista, y un tercio del texto en letra monoespaciada. Y no guía: añadir cosas está escondido abajo a la derecha, y nada dice cuál es el siguiente paso después de aplicar.

## 2. Problemas

| ID | Eje | Dónde | Qué pasa | Evidencia | Gravedad |
|---|---|---|---|---|---|
| CC-01 | Moderna, intuitiva | Toda la pantalla | Cuatro paneles, panel inferior de 220 px, presupuesto y barra de estado a la vez; el mapa no manda | Mapa de 778 × 568 px (34 %) a 1440 × 900 y 704 × 436 px (29 %) a 1366 × 768 | ALTA |
| CC-02 | Profesional | Jerarquía, cabecera, Consola, barra de estado | Jerga de ingeniería a la vista: `Land_Wreck_Ikarus` en cada fila, «r14 editada · r12 en el juego», «hash 9053a2f3», «op-7f3d · scene_apply», «Mundo 7c19e2a4», «DayZServer 1.30.164200 retail» | 27 textos con jerga; 57 de 172 textos visibles en monoespaciada | ALTA |
| CC-03 | Moderna | Paneles | Tarjetas redondeadas que flotan sobre negro con borde propio y 8 px de hueco; parece una maqueta, no una aplicación de escritorio | Captura de Escena; `.panel` y `.ws` con `gap` y radio | ALTA |
| CC-04 | Moderna | Letra | Casi la mitad del texto visible está por debajo de 12 px; poca diferencia entre títulos, valores y notas | 84 de 172 textos por debajo de 12 px | MEDIA |
| CC-05 | Intuitiva | Biblioteca | Añadir, la acción más frecuente, va abajo a la derecha compartiendo columna con Propiedades: se ven dos elementos y un aviso de tope encima; las filas son texto con su clase, sin icono de categoría | Captura de Escena | ALTA |
| CC-06 | Intuitiva | Recorrido | Para rodar hay que aplicar en Escena, pasar a Rodaje y preparar. Tras aplicar, el botón dice «Volver a aplicar» y nada apunta a Rodaje | Captura tras aplicar | ALTA |
| CC-07 | Profesional | Jerarquía | Una marca verde por fila cuando todo coincide con el juego; lo que importa (nuevo, cambiado, fuera del juego) se pierde entre 35 marcas iguales | Captura de Escena | MEDIA |
| CC-08 | Profesional | Barra superior | 13 controles: marca, modos, documento, deshacer, rehacer, ambiente, Resetear, Aplicar, tres luces, cuatro iconos sin texto (Vista, Atajos, Referentes, Simulador) y Guía | Script: 13 controles visibles | MEDIA |
| CC-09 | Moderna | Mapa | Marcadores pequeños de formas planas; las etiquetas se pisan (Mirek, Linda y Bidón azul en el cruce); la cámara y su trayectoria compiten con el resto | Captura de Escena | MEDIA |
| CC-10 | Intuitiva | Panel inferior | La Consola, siempre abierta, enseña filas de operación con id, comando y origen técnico; lo útil para la creadora es qué pasó, en una línea | Captura de Escena | MEDIA |
| CC-11 | Intuitiva | Propiedades sin selección | Enseña revisión, hash y «Guardado: cada cambio, al momento (Ctrl+S también vale)»; no dice qué hacer ahora | Captura de Escena | MEDIA |
| CC-12 | Intuitiva | Luces de conexión | «Backend» y «Director» son nombres internos; en cine el director es una persona, aquí es tu cliente de DayZ | Barra superior | BAJA |
| CC-13 | Profesional | Textos | «1 gestos», «Resetear», `take` y `scene_apply` en pantalla | Línea de tiempo y Consola | BAJA |
| CC-14 | Profesional | Avisos | Los avisos tapan la Biblioteca y se apilan de dos en dos | Captura de Escena | BAJA |

## 3. Mejoras, por prioridad

AHORA cambia la impresión en una pasada; DESPUÉS necesita más que el prototipo; NO se descarta con su motivo.

| ID | Grupo | Resuelve | Qué cambiar | Referente | Coste | Criterio verificable |
|---|---|---|---|---|---|---|
| MC-01 | AHORA | CC-01, CC-03, CC-05 | Paneles acoplados de borde a borde, con cabecera de pestañas y separadores de 1 px. Izquierda: pestañas «Escena» (la jerarquía) y «Añadir» (la biblioteca). Derecha: solo Propiedades, a toda altura. Abajo: Actividad plegada a una tira de una línea que se abre con un clic | Paneles del World Editor de Reforger: Hierarchy, Object Properties, Resource Browser y Log Console ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor)); el Content Drawer de Unreal 5, un navegador que se pliega al perder el foco ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/content-browser-in-unreal-engine)) | M | Mapa ≥ 50 % de la ventana a 1440 × 900 y ≥ 45 % a 1366 × 768; falla si un panel deja el mapa por debajo |
| MC-02 | AHORA | CC-02, CC-10, CC-11 | Lo técnico, plegado. Fuera de la vista por defecto: la clase en las filas (va en Propiedades y en el texto al pasar el ratón), ids, hashes y comandos (van en «Detalles» de cada fila de Actividad) y versiones (van en un desplegable de la barra de estado). La cabecera dice «2 cambios sin aplicar» y «en el juego hace 4 min» en vez de «r14 editada · r12 en el juego». El chip de D2, la edad y el origen de cada operación se quedan a la vista | Object Properties del World Editor separa «Entity information» en su propia sección ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor)); la parte que se pliega es PROPIA (D2 pide estado y edad, no ids) | M | Escena recién abierta: ≤ 6 textos con jerga y ≤ 10 % del texto en monoespaciada; falla si una operación pierde su chip, su edad o su origen |
| MC-03 | AHORA | CC-07 | Estado por excepción en la Jerarquía: sin icono cuando coincide con el juego; icono solo para nuevo, cambiado, fuera del juego o fallido. La cabecera resume: «Todo en el juego · hace 4 min» o «3 por aplicar» | Las listas de entidades de Eden y del DayZ Editor no llevan icono por fila [sin verificar]; marcar lo distinto es PROPIO (#7: revisión editada frente a la aplicada) | S | Con todo aplicado y leído, 0 iconos de estado en las filas; con un cambio, exactamente 1 |
| MC-04 | AHORA | CC-08, CC-12 | Barra superior en tres grupos: documento a la izquierda (nombre, cambios, deshacer y rehacer), modos Escena y Rodaje en el centro, y a la derecha la acción principal, una sola pastilla de conexión con tres puntos (el detalle al pasar el ratón o al pulsar) y un menú «Más» con Vista, Atajos, Referentes, Simulador y Guía | Barra superior del World Editor agrupada en tres secciones ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:World_Editor)); los modos arriba como el Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)) | S | ≤ 9 controles visibles en la barra a 1366 px; con el backend caído la pastilla se pone gris con «hace X» (CU-37 sigue pasando) |
| MC-05 | AHORA | CC-06 | Siguiente paso a la vista: aplicada y observada la escena, el botón principal pasa a «Ir a rodaje»; en Rodaje manda el transporte (Preparar, Rodar, Parar), que ya existe | Botón que cambia de Launch Session a Push Changes en UEFN [sin verificar]; el transporte sale del DAW y de OBS (consolidado §9) | S | Tras aplicar con éxito, el botón principal lleva a Rodaje; con cambios sin aplicar, vuelve a «Aplicar» |
| MC-06 | AHORA | CC-05 | «Añadir» con icono de categoría por fila, búsqueda arriba, categorías como filtro y el presupuesto dentro. Clic para coger, clic en el mapa para colocar, Ctrl+clic para seguir colocando y clic derecho para cancelar. Tab con el mapa enfocado abre Añadir y Esc lo cierra | Entity Browser del Game Master: se abre con Tab, se cierra con Esc, coloca con clic, Ctrl+clic sigue colocando, clic derecho cancela y el presupuesto se ve dentro ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)); filtro por tipo, búsqueda por nombre e icono por entidad en el Asset Browser de Eden ([wiki](https://community.bistudio.com/wiki/Eden_Editor:_Asset_Browser)) | M | Con el mapa enfocado, Tab abre Añadir y Esc lo cierra; con el foco en un campo, Tab sigue moviendo el foco |
| MC-07 | AHORA | CC-09 | Mapa más limpio: marcadores un 25 % más grandes con borde y halo; etiqueta solo para actores, cámaras, lo seleccionado y lo que está bajo el ratón, con halo y sin pisarse; terreno algo más apagado en oscuro | Mapa 2D de Eden con iconos y nombres [sin verificar] | M | En la escena de ejemplo, ninguna etiqueta se pisa con otra a zoom inicial |
| MC-08 | AHORA | CC-03, CC-04 | Sistema visual nuevo (sección 4): superficies, letra de 13 px de base, radios, una familia de iconos | Editor de Unreal 5 y World Editor [sin verificar en el detalle] | M | ≤ 15 % del texto visible por debajo de 12 px; contraste AA (CU-38) sigue pasando en los dos temas |
| MC-09 | AHORA | CC-11 | Propiedades sin selección: resumen de la escena (actores, objetos, cámaras, cambios) y el siguiente paso, sin revisión ni hash | PROPIO, sobre «Scenario properties» del Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master)) | S | Sin selección no aparece ningún hash ni revisión en Propiedades |
| MC-10 | AHORA | CC-12, CC-13, CC-14 | Textos: plurales bien («1 gesto»), «Restablecer» en vez de «Resetear», la luz «Director» pasa a «Tu juego», nada de `take` ni `scene_apply` a la vista; los avisos salen abajo en el centro del mapa, de uno en uno | Avisos sobre la vista, no sobre los paneles [sin verificar] | S | Ningún texto visible con «1 gestos», «Resetear», `take` o `scene_apply` |
| MC-11 | DESPUÉS | CC-05 | Miniaturas reales de cada clase en Añadir | Content Browser de Unreal con miniaturas ([docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/content-browser-in-unreal-engine)) | L | Necesita capturar cada clase en el juego (F6 o después) |
| MC-12 | DESPUÉS | CC-06 | Primera vez: tres pasos sobre la escena de ejemplo (añadir, aplicar, rodar) | Tutorial del Game Master ([wiki](https://community.bistudio.com/wiki/Arma_Reforger:Game_Master_Tutorial)) | M | — |
| MC-13 | NO | — | Cambiar los nombres de los estados de D2 | Son contrato (D2 los nombra); se explican al pasar el ratón | — | — |
| MC-14 | NO | — | Quitar las tres luces | CU-37 y las pruebas las piden; se compactan en una pastilla (MC-04) | — | — |
| MC-15 | NO | — | Paleta de comandos | Fuera por R25 en octubre (consolidado §10) | — | — |

## 4. Dirección visual

| Parte | Propuesta | Referente |
|---|---|---|
| Superficies | Paneles acoplados sin huecos, separadores de 1 px, cabeceras de panel con pestañas; grises algo más claros que el negro del chasis | World Editor de Reforger, Unreal 5 [sin verificar en el detalle] |
| Letra | La del sistema (Segoe UI en Windows): 13 px de base, 12 px para lo secundario, 11 px solo para metadatos; monoespaciada solo en coordenadas y código de tiempo | Unreal 5 [sin verificar] |
| Iconos | Una sola familia lineal de 16 px; las acciones principales llevan icono y texto | Barra del World Editor (iconos agrupados) |
| Acento | Ámbar solo para selección y foco; botón principal claro; rojo solo para Parar y Rodando | Consolidado §6 (CU-38 ya medido) |
| Densidad | Filas de 28 px, controles de 28 a 32 px, rejilla de 4 px | Unreal 5 [sin verificar] |
| Radios | 0 en paneles acoplados, 4 px en controles, 8 px en menús, cajones y avisos | Content Drawer de Unreal 5 (lo que flota) |
| Sombras | Solo en lo que flota: menús, cajones y avisos | Content Drawer de Unreal 5 |

## 5. Fuera de M1 (R25)

- Vista 3D del juego en la web y miniaturas en vivo: fuera del spec.
- Paleta de comandos: sigue fuera.
