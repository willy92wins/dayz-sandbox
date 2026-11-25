# S-cot: estudio de las funciones de cámara de cine (COT, VPPAdminTools, PCT)

Fecha: 2026-11-15. Sin partida, sin DayZ y sin código nuestro. Se leyeron los scripts de COT (Workshop 1564026768) y de VPPAdminTools (Workshop 1828439124) extraídos de sus PBO, y el README de PCT (`https://github.com/Psyern/PsyernsCinematicTool`). Se comparan con B1-B5 de `product-spec.md`.

Cómo leer las citas: en la matriz cada celda lleva su clave (`C..` COT, `V..` VPP, `P..` PCT). La parte 2 da, para cada clave, el `path:line` (mods instalados) o la URL (PCT). Las rutas de los mods instalados son `<mod>/<ruta dentro del PBO>:<línea>`. El texto literal de cada línea está en `citas.tsv`, al lado de este fichero en la carpeta de trabajo.

No se copia código ni nombres de clases o funciones como diseño propio. Lo que sigue es lo que hace cada función, con nuestras palabras.

## Resumen en cuatro líneas

- COT trae casi todo lo de una cámara de cine en cliente: ruta de claves con tiempo o velocidad por tramo, easing, curva suave, FOV, desenfoque, sacudida, exposición y rutas guardadas en JSON. No tiene ocultar HUD para la cámara ni exportar e importar rutas.
- VPPAdminTools solo tiene cámara libre (con ajustes persistentes) y espectador de jugadores. No tiene rutas, ni DOF, ni sacudida, ni claves.
- PCT, por su README, es la herramienta con enfoque de cineasta: focal en mm, sensor, apertura, encuadre automático, pistas de claves, 11 easings, scrubbing y exportación CSV/JSON. Su código no se pudo leer (solo el README).
- Ninguna de las tres cubre B4 (sin HUD durante toda la toma) como función de cámara.

## Parte 1. Matriz de funciones

Leyenda: «sí» = la herramienta la tiene; «parcial» = solo una parte (se dice cuál); «no» = no la tiene, con el motivo; «no consta» = el README de PCT no la menciona, y no se pudo mirar su código. Columna «Spec»: id de B1-B5 que cubre esa función en `product-spec.md`, o «no».

| # | Función | COT | VPP | PCT | Spec | Citas |
|---|---|---|---|---|---|---|
| F01 | Cámara libre: mover y mirar con inercia | sí | sí (hay además una cámara libre antigua, ya sin uso) | sí (hereda la de COT) | B1 | C01 C02 V01 V02 V11 V28 P01 |
| F02 | Velocidad de vuelo ajustable en vivo, con turbo y modo lento | sí | sí; además queda guardada en el perfil | no consta (hereda la de COT) | B1 | C03 C04 V03 V04 V05 V32 V06 V07 V08 P01 |
| F03 | Alabeo (roll) de la cámara | sí, con una tecla y la rueda | no: solo cambia guiñada y cabeceo | no consta (nombra un modo «Horizon-lock» sin detalle) | no | C05 V12 P23 |
| F04 | Guardar una pose y volver a ella | parcial: solo la posición, no la orientación | no: solo teletransportar y copiar la posición | sí: guarda y aplica el estado completo del equipo de cámara | B1 | C42 C43 V13 V14 P09 P10 |
| F05 | Copiar y pegar una posición por el portapapeles | sí | parcial: solo copiar | no consta | B1 (auxiliar) | C44 C45 V14 |
| F06 | Claves de posición y orientación (ruta) | sí | no: no hay ruta de claves | sí: ruta de cámara en una línea de tiempo | B2 | C06 C07 C70 C71 C72 P11 |
| F07 | FOV propio en cada clave | sí | no | sí: pistas de claves para la focal | no | C08 C22 P12 |
| F08 | FOV o zoom manual | sí | sí | sí (como focal en mm) | no | C64 C65 C66 V09 V10 V27 P03 |
| F09 | Focal en milímetros ligada a un sensor | no: el FOV es un multiplicador de 0,001 a 4 | no: FOV absoluto | sí: sensores de serie, focal de 8 a 400 mm, FOV derivado y acotado | no | C65 V10 P02 P03 |
| F10 | Tiempo por tramo entre claves | sí | no | no consta: el README no dice cómo se fija el tiempo | B2 | C09 C12 |
| F11 | Velocidad por tramo en m/s, rampa entre tramos y multiplicador global | sí | no | no consta | B2 (parcial) | C10 C11 C13 |
| F12 | Duración estimada de la toma antes de lanzarla | sí | no | no consta | B2 | C69 |
| F13 | Easing por tramo | sí: 5 curvas, una por clave | no | sí: catálogo de 11 | no | C14 C15 C16 P12 P13 |
| F14 | Curva suave por las claves (Catmull-Rom) con velocidad uniforme | sí; solo con 4 claves o más | no | sí | B2 | C17 C18 C19 C73 P13 |
| F15 | Orientación interpolada por el camino corto | sí, solo si las dos claves la guardan | no | parcial: la mirada va en un camino aparte | B2 | C20 C21 P11 |
| F16 | Pausa en una clave | sí | no | no consta | no | C24 C25 |
| F17 | Modos de reproducción: una vez, bucle, ida y vuelta | sí | no | no consta | no | C26 C27 C28 |
| F18 | Reproducir y pausar | sí | no | sí | B5 | C29 C30 C31 P19 |
| F19 | Parar y devolver el control | parcial: no hay botón de parar; la ruta acaba sola y salir de la cámara devuelve el control | parcial: salir del espectador, con un fundido de 0,8 s al entrar en la libre y corte instantáneo al espectar | no consta | B5 | C32 C33 C34 V18 V24 V25 V29 |
| F20 | Scrubbing determinista de la línea de tiempo | no | no | sí | B2 (útil para muestrear) | P14 |
| F21 | Sacudida de cámara (shake) | sí, global y por clave | no | no: el README no la menciona | no | C35 C36 C37 |
| F22 | Rutas con nombre guardadas en un fichero | sí: JSON en el perfil | no | parcial: una toma por fichero JSON; las secuencias en fichero están «previstas» | no | C38 C39 C40 C41 P10 P21 P22 |
| F23 | Exportar e importar rutas | no: solo su propio fichero en el perfil, sin función de exportar o importar | no | parcial: exporta CSV y JSON; importar no se describe | no | C39 P16 |
| F24 | Profundidad de campo: foco y desenfoque | sí | no: solo la quita al espectar | sí | B3 | C46 C47 C48 C49 V26 P04 |
| F25 | Apertura (T/f) como parámetro del desenfoque | no: el desenfoque es un valor abstracto de 0 a 100 | no | sí: de 0,7 a 32 | B3 | C49 P04 |
| F26 | Enfoque automático por rayo y enfoque al objetivo fijado | sí | no | parcial: usa un rayo para encuadrar un sujeto; no describe auto-foco | B3 | C50 C51 P08 |
| F27 | Enfoque o desenfoque distinto en cada clave | parcial: el desenfoque va por clave, la distancia de foco no | no | sí: el foco es una pista de claves | B3 | C23 C22 P12 |
| F28 | Distancia mínima de enfoque de la lente | no | no | sí, con opción para saltársela | no | P05 P06 P24 |
| F29 | Encuadre automático (plano y ángulo a partir de un sujeto) | no: fijar un objetivo no coloca la cámara | no | sí: 10 planos y 11 ángulos de serie | no | C52 P08 |
| F30 | Mirar y seguir un objetivo | sí; la marca «seguir» por clave se guarda, pero en estos scripts nada la lee | parcial: espectar y seguir a un jugador, que no es mirarlo desde un punto fijo | parcial: nombra un modo «Follow» sin explicarlo | no | C52 C53 C54 C55 C56 V19 V20 V23 P23 |
| F31 | Camino de mirada separado del de cámara | no | no | sí | no | P11 |
| F32 | Exposición y viñeta | sí, y por clave | no | no consta | no | C57 C58 C22 |
| F33 | HUD oculto durante toda la toma | no para la cámara: hay un interruptor general que ninguna función de la cámara llama | parcial: el HUD se oculta mientras su menú está abierto; es un efecto colateral, no un ajuste | no consta: su «HUD» es una superposición propia | B4 | C59 C60 V30 V31 P07 |
| F34 | Atajos de teclado de la cámara | sí | sí | sí, pero sin teclas asignadas de serie | B5 (tecla de parada) | C61 C62 C63 V15 V16 V17 V18 P18 P19 P20 |
| F35 | Superposiciones de composición (tercios, cruz, máscaras de aspecto) | no | no | sí | no | P07 |
| F36 | Movimientos preestablecidos (travelling, órbita, dolly-zoom) | no | no | sí | no | P15 |
| F37 | Captura de pantalla por toma | no | no | sí | no | P17 |
| F38 | Primera y tercera persona del jugador o del espectado | sí | sí | no consta | no | C67 V19 V21 V22 |
| F39 | Ocultar la hierba para despejar el plano | sí | no | no consta | no | C68 |

Total: 39 funciones.

### Lo que dice la matriz sobre B1-B5

- **B1** (cámara libre mínima, guardar la pose y volver): F01, F02, F04 y F05. COT guarda solo la posición. Para el criterio (error de 0,05 m y 0,5°) hace falta guardar también la orientación, como hace PCT con su estado completo.
- **B2** (camino de 3 claves en 6 s, sin saltos): F06, F10, F11, F12, F14, F15 y F20. Un detalle de COT: la curva suave solo se aplica con 4 claves o más (C73), así que con 3 claves usa recta entre claves. Eso encaja con medir B2 contra la recta, pero conviene fijarlo en el diseño y no dejarlo implícito.
- **B3** (enfoque por cámara y por clave): F24 a F27. COT y PCT lo tienen en distinto grado. PCT es el único con apertura; COT es el único con auto-foco descrito.
- **B4** (sin HUD durante toda la toma): ninguna de las tres tiene una función de cámara que lo haga. Tenemos que construirlo nosotros.
- **B5** (parar con la web o con una tecla, control en menos de 1 s): COT no tiene botón de parar propio y su salida espera a que el personaje esté en reposo (C74). VPP corta al instante al espectar (V25). Nuestro «parar < 1 s» no está cubierto por ninguna de las tres como función.

## Parte 2. Citas

Una fila por clave. Para COT y VPP: `<mod>/<ruta dentro del PBO>:<línea>`. Para PCT: la URL del README y la sección; los números de línea de PCT los dio la lectura de la página con WebFetch y deben comprobarse a mano, porque el tamaño y el orden del README pueden haber cambiado. El texto literal de cada cita está en `citas.tsv`.

### COT

| Clave | Función | Cita |
|---|---|---|
| C01 | Cámara libre: mover y mirar con inercia | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:133` |
| C02 | Cámara libre: arrastre de velocidad (inercia) | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:174` |
| C03 | Velocidad ajustable en vivo, turbo y lento | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:159` |
| C04 | Turbo y lento con tecla | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:171` |
| C05 | Alabeo (roll) | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:267` |
| C06 | Clave: posición | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:17` |
| C07 | Clave: orientación capturada | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:22` |
| C08 | Clave: FOV por clave | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:28` |
| C09 | Clave: tiempo del tramo | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:18` |
| C10 | Clave: velocidad del tramo (m/s) | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:19` |
| C11 | Tramo por velocidad o por tiempo | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:517` |
| C12 | Tramo por tiempo / multiplicador global | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:534` |
| C13 | Rampa de velocidad entre tramos | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:211` |
| C14 | Easing por tramo: catálogo | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:5` |
| C15 | Easing por tramo: se guarda en cada clave | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:36` |
| C16 | Easing aplicado a la posición | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:368` |
| C17 | Catmull-Rom opcional por clave | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:35` |
| C18 | Catmull-Rom con velocidad constante (arco) | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:358` |
| C19 | Tabla de longitud de arco | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:562` |
| C20 | Orientación por el camino corto | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:327` |
| C21 | Orientación solo si ambas claves la tienen | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:539` |
| C22 | Efectos por clave interpolados | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:375` |
| C23 | Desenfoque por clave | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:384` |
| C24 | Pausa en clave | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:39` |
| C25 | Pausa en clave aplicada | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:237` |
| C26 | Modos de reproducción | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:1` |
| C27 | Modo bucle | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:411` |
| C28 | Modo ida y vuelta | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:425` |
| C29 | Pausar/reanudar | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:111` |
| C30 | Botón pausa en el panel | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:187` |
| C31 | Botón reproducir | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:182` |
| C32 | Fin de la ruta en modo una vez | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:437` |
| C33 | Salir de la cámara restaura el control | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:485` |
| C34 | Salir: devuelve el control al jugador | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:528` |
| C35 | Shake aditivo | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:307` |
| C36 | Shake por clave | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:31` |
| C37 | Shake: deslizador | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraForm.c:308` |
| C38 | Rutas con nombre | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraSerialize.c:7` |
| C39 | Fichero JSON en el perfil | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraSerialize.c:37` |
| C40 | Guardar ruta | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraSerialize.c:104` |
| C41 | Cargar ruta en el módulo | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:877` |
| C42 | Marcador de posición con nombre | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraSerialize.c:23` |
| C43 | Ir a un marcador | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:931` |
| C44 | Copiar posición de la clave al portapapeles | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:220` |
| C45 | Pegar posición desde el portapapeles | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:226` |
| C46 | Estado DOF | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:9` |
| C47 | DOF: override del motor | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:214` |
| C48 | DOF: deslizador de foco en metros | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraForm.c:293` |
| C49 | DOF: desenfoque 0-100 | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraForm.c:292` |
| C50 | Enfoque automático por rayo | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:201` |
| C51 | Enfocar al objetivo fijado | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:200` |
| C52 | Fijar objetivo por rayo | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:742` |
| C53 | Seguir al objetivo cada frame con offset | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:298` |
| C54 | Selección de objetivo congela la cámara | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraBase.c:71` |
| C55 | Marca TrackTarget en la clave | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCameraWaypoint.c:42` |
| C56 | Marca TrackTarget editable en el panel | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:380` |
| C57 | Exposición | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:188` |
| C58 | Viñeta | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:190` |
| C59 | Infraestructura de ocultar HUD (no usada por la cámara) | `COT/JM/COT/Scripts/4_World/CommunityOnlineTools/Classes/COTModule.c:249` |
| C60 | Infraestructura de ocultar HUD: efecto | `COT/JM/COT/Scripts/4_World/CommunityOnlineTools/Classes/COTModule.c:221` |
| C61 | Atajo: activar cámara | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:289` |
| C62 | Atajos: zoom | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:290` |
| C63 | Atajos en Inputs.xml | `COT/JM/COT/Scripts/Data/Inputs.xml:26` |
| C64 | Zoom por teclas modifica el FOV objetivo | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:725` |
| C65 | FOV como multiplicador 0,001-4 | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraForm.c:286` |
| C66 | FOV aplicado a la cámara | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:182` |
| C67 | Tercera persona: modos | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:826` |
| C68 | Ocultar hierba | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:247` |
| C69 | Duración estimada | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:560` |
| C70 | Orientación de la clave capturada del libre | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:279` |
| C71 | Copiar ajustes de la clave anterior | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:286` |
| C72 | Subir/bajar/borrar claves | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/Components/JMCameraTravelPanel.c:119` |
| C73 | Catmull-Rom exige 4 claves o más | `COT/JM/COT/Scripts/3_Game/CommunityOnlineTools/Entities/Cameras/JMCinematicCamera.c:356` |
| C74 | Salir espera a que el personaje esté en reposo | `COT/JM/COT/Scripts/5_Mission/CommunityOnlineTools/modules/Camera/JMCameraModule.c:545` |

### VPPAdminTools

| Clave | Función | Cita |
|---|---|---|
| V01 | Cámara libre: mover | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:64` |
| V02 | Cámara libre: arrastre | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:99` |
| V03 | Turbo | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:84` |
| V04 | Velocidad con la rueda | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:74` |
| V05 | Ajustes persistidos en el perfil | `VPP/VPPAdminTools/3_Game/VPPAdminTools/VPPATProfileOptions.c:20` |
| V06 | Opciones de cámara | `VPP/VPPAdminTools/3_Game/VPPAdminTools/VPPATProfileOptions.c:3` |
| V07 | Ajustes leídos al entrar | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:24` |
| V08 | Deslizador de velocidad en opciones | `VPP/VPPAdminTools/5_Mission/VPPAdminTools/GUI/Options/OptionsMenuGame.c:30` |
| V09 | FOV con doble pulsación | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:105` |
| V10 | FOV absoluto | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:119` |
| V11 | Límite de cabeceo | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:136` |
| V12 | Solo guiñada y cabeceo | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraFree.c:130` |
| V13 | Atajo teleport al punto de mira | `VPP/VPPAdminTools/data/modded_Inputs.xml:10` |
| V14 | Atajo copiar posición | `VPP/VPPAdminTools/data/modded_Inputs.xml:16` |
| V15 | Atajo activar cámara libre | `VPP/VPPAdminTools/data/modded_Inputs.xml:18` |
| V16 | Entradas de la cámara libre | `VPP/VPPAdminTools/data/modded_Inputs.xml:26` |
| V17 | Entrada FOV | `VPP/VPPAdminTools/data/modded_Inputs.xml:39` |
| V18 | Salir de espectador | `VPP/VPPAdminTools/data/modded_Inputs.xml:42` |
| V19 | Alternar 1ª/3ª persona al espectar | `VPP/VPPAdminTools/data/modded_Inputs.xml:43` |
| V20 | Siguiente objetivo al espectar | `VPP/VPPAdminTools/data/modded_Inputs.xml:44` |
| V21 | Vistas de espectador | `VPP/VPPAdminTools/3_Game/VPPAdminTools/VPPSpectateConstants.c:1` |
| V22 | Indicador 1PP/3PP | `VPP/VPPAdminTools/5_Mission/VPPAdminTools/GUI/VPPSpectateOverlay.c:96` |
| V23 | Seguimiento del objetivo en el servidor | `VPP/VPPAdminTools/3_Game/VPPAdminTools/VPPSpectateConstants.c:27` |
| V24 | Fundido de entrada a cámara libre | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameras.c:20` |
| V25 | Corte instantáneo al espectar | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameras.c:43` |
| V26 | Solo quita el DOF al espectar | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameraSpectate.c:279` |
| V27 | Cámara libre antigua: FOV | `VPP/VPPAdminTools/4_World/VPPAdminTools/Misc/VPPCameras/VPPFreeCam.c:94` |
| V28 | Cámara libre antigua sin uso | `VPP/VPPAdminTools/5_Mission/VPPAdminTools/Freecamera.c:21` |
| V30 | El HUD se oculta mientras está abierto el menú | `VPP/VPPAdminTools/5_Mission/VPPAdminTools/GUI/VPPUIManager.c:398` |
| V31 | El HUD vuelve al cerrar el menú | `VPP/VPPAdminTools/5_Mission/VPPAdminTools/GUI/VPPUIManager.c:413` |
| V32 | Los ajustes de cámara se escriben al perfil | `VPP/VPPAdminTools/3_Game/VPPAdminTools/VPPATProfileOptions.c:70` |
| V29 | Transición registrada hacia libre | `VPP/VPPAdminTools/4_World/VPPAdminTools/Entities/DayZPlayer/DayZPlayerCameras.c:3` |

### PCT (README de GitHub)

| Clave | Función | Cita |
|---|---|---|
| P01 | Cámara libre heredada de COT | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 33, §1 Overview)` |
| P02 | Sensores que fijan el FOV | `https://github.com/Psyern/PsyernsCinematicTool (README, §4a, tras la línea 101)` |
| P03 | Focal en mm 8-400 | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 103, §4a)` |
| P04 | Apertura T/f y DOF | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 105, §4a)` |
| P05 | Bloqueo a focales de primas | `https://github.com/Psyern/PsyernsCinematicTool (README, §4b, línea 108 y siguientes)` |
| P06 | Distancia mínima de enfoque | `https://github.com/Psyern/PsyernsCinematicTool (README, §4b)` |
| P07 | Superposiciones de composición | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 114, §4c)` |
| P08 | Encuadre automático | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 118, §4d)` |
| P09 | Capturar y aplicar el estado completo del rig | `https://github.com/Psyern/PsyernsCinematicTool (README, §4e, tras la línea 120)` |
| P10 | Navegador de tomas: renombrar y borrar | `https://github.com/Psyern/PsyernsCinematicTool (README, §4e)` |
| P11 | Camino de cámara y de mirada separados | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 127, §4f)` |
| P12 | Pistas de claves y 11 easings | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 129, §4f)` |
| P13 | Catmull-Rom con arco | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 130, §4f)` |
| P14 | Scrubbing determinista y visualización del camino | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 131, §4f)` |
| P15 | Movimientos preestablecidos | `https://github.com/Psyern/PsyernsCinematicTool (README, §4f, línea 131)` |
| P16 | Exportar CSV y JSON | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 135, §4g)` |
| P17 | Captura por toma | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 136, §4g)` |
| P18 | Integración con permisos de COT | `https://github.com/Psyern/PsyernsCinematicTool (README, líneas 139-140, §4h)` |
| P19 | Entrar y reproducir/pausar | `https://github.com/Psyern/PsyernsCinematicTool (README, líneas 271 y 277, §10 Workflow)` |
| P20 | Teclas sin asignar por defecto | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 281, §10)` |
| P21 | Estado: secuencias en fichero previstas | `https://github.com/Psyern/PsyernsCinematicTool (README, §8 Profile Structure y §11 Project Status)` |
| P22 | Estado: fases 4-5 previstas | `https://github.com/Psyern/PsyernsCinematicTool (README, §11 Project Status, línea 286 y siguientes)` |
| P23 | Modos de mirada (Follow nombrado, sin detalle) | `https://github.com/Psyern/PsyernsCinematicTool (README, §4 Features)` |
| P24 | Ajuste de enfoque cercano | `https://github.com/Psyern/PsyernsCinematicTool (README, §9a Settings.json)` |

### Licencias

| Clave | Herramienta | Qué | Cita |
|---|---|---|---|
| L01 | COT | Licencia CC BY-SA 4.0 | `https://github.com/Jacob-Mango/DayZ-CommunityOnlineTools (barra lateral Resources y sección de licencia del README)` |
| L02 | COT | Origen del mod instalado | `COT/mod.cpp:8` |
| L03 | VPP | Condiciones de uso: monetización | `https://steamcommunity.com/sharedfiles/filedetails/?id=1828439124 (descripción del Workshop)` |
| L04 | VPP | Condiciones de uso: sin reempaquetado | `https://steamcommunity.com/sharedfiles/filedetails/?id=1828439124 (descripción del Workshop)` |
| L05 | VPP | Sin licencia de código declarada | `https://steamcommunity.com/sharedfiles/filedetails/?id=1828439124 (descripción del Workshop)` |
| L06 | PCT | Sin licencia: todos los derechos reservados | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 319, §13)` |
| L08 | COT | Iconos de COT con CC BY 3.0 | `COT/JM/COT/GUI/textures/icons/CREDITS.md:13` |
| L07 | PCT | Depende de COT y CF | `https://github.com/Psyern/PsyernsCinematicTool (README, línea 316, §13)` |

## Parte 3. Ideas a adoptar

Cada idea va con su herramienta de origen, la fase propuesta y el porqué. Todas están descritas con nuestras palabras. Ninguna implica copiar código.

1. **Guardar la pose completa, no solo la posición.** Origen: PCT (F04); COT guarda solo la posición. Fase: F4. Porqué: B1 exige volver a la pose con un error menor de 0,5°, y eso solo se cumple si la orientación se guarda con la posición.
2. **Tiempo total por tramo como dato de entrada y duración mostrada.** Origen: COT (F10, F12). Fase: F4. Porqué: B2 pide que la toma dure entre 6,0 y 6,3 s; si el usuario fija el tiempo de cada tramo y ve la suma antes de lanzar, esa condición se comprueba sin partida.
3. **Velocidad por tramo como alternativa al tiempo, con suavizado entre tramos.** Origen: COT (F11). Fase: backlog. Porqué: es cómoda para cámaras de seguimiento, pero B2 se mide por tiempo; no hace falta en la primera versión.
4. **Easing por tramo, con un catálogo corto.** Origen: COT (5 curvas) y PCT (11) (F13). Fase: F6. Porqué: es la mejora visual más barata de una ruta; no cambia el modelo de datos más que con un campo por clave.
5. **Curva suave con velocidad uniforme, opcional por clave.** Origen: COT y PCT (F14). Fase: F6. Porqué: hace que el movimiento se vea natural. Hay que fijar que con 3 claves se use recta (como hace COT), para que B2 sea reproducible.
6. **Orientación interpolada por el camino corto, y solo si ambas claves la guardan.** Origen: COT (F15). Fase: F4. Porqué: sin esto el giro da una vuelta larga al cruzar ±180°, y B2 mira la pose final con 0,5°.
7. **Focal en milímetros con un sensor de referencia (8 a 400 mm).** Origen: PCT (F09). Fase: F6. Porqué: un cineasta piensa en focales, no en un multiplicador de FOV; y la conversión se puede probar sin partida. Una vez que se acepta, hay que fijar el sensor de referencia por defecto.
8. **Apertura como parámetro del desenfoque.** Origen: PCT (F25). Fase: F6. Porqué: B3 mide el desenfoque del fondo; una apertura da al usuario un control que se entiende. Si el motor no desenfoca, B3 sale de M1 por el Changelog del spec, así que esta idea depende de eso.
9. **Enfoque y desenfoque por clave, además de por cámara.** Origen: PCT (F27) y COT (parcial). Fase: F4. Porqué: B3 pide «por cámara y por clave» de forma literal.
10. **Enfoque automático por rayo al centro y al objetivo fijado.** Origen: COT (F26). Fase: F6. Porqué: ahorra al usuario calcular la distancia del actor; COT lo hace con un rayo largo y con la distancia al objetivo.
11. **Encuadre automático por presets de plano y ángulo.** Origen: PCT (F29). Fase: F6. Porqué: es la función más diferencial de PCT. Colocar la cámara a partir del actor es muy útil en rodajes con actores.
12. **Exportar e importar rutas en JSON o CSV.** Origen: PCT (exporta; F23) y COT (su fichero JSON en el perfil). Fase: F6. Porqué: ninguna importa. Para nosotros, importar permite compartir tomas y es una prueba sencilla de ida y vuelta.
13. **Guardar la toma entera en un fichero por toma, con nombre.** Origen: PCT (F22) y COT. Fase: F4. Porqué: es la unidad natural de B6; un fichero por toma facilita revisar, versionar y borrar.
14. **Scrubbing determinista de la línea de tiempo.** Origen: PCT (F20). Fase: F6. Porqué: permite muestrear la pose en cualquier instante, sin esperar a que la toma corra, y ayuda a medir B2.
15. **Parar la toma con una tecla y con la web, con salida inmediata.** Origen: ninguna lo resuelve del todo (F19); VPP corta al instante al entrar y salir del espectador, COT espera a que el personaje esté en reposo. Fase: F4. Porqué: B5 pide menos de 1 s. Hay que tomar de VPP el corte instantáneo y de COT la restauración de los controles.
16. **Ocultar el HUD durante toda la toma, como parte de la cámara.** Origen: ninguna; COT y VPP solo tienen el interruptor como efecto colateral (F33). Fase: F4. Porqué: B4 lo exige y nadie lo ofrece hecho. La idea aprovechable es que el HUD vuelva al terminar, y no antes.
17. **Pausa en una clave.** Origen: COT (F16). Fase: backlog. Porqué: útil para planos de espera, pero no hace falta para los criterios.
18. **Modos de reproducción (bucle, ida y vuelta).** Origen: COT (F17). Fase: backlog. Porqué: sirven para pruebas y demos, no para tomas.
19. **Sacudida de cámara con intensidad y frecuencia, global y por clave.** Origen: COT (F21). Fase: backlog. Porqué: efecto vistoso, pero ningún criterio de B lo pide.
20. **Superposiciones de composición (tercios, cruz, máscara de aspecto) y movimientos preestablecidos.** Origen: PCT (F35, F36). Fase: backlog. Porqué: mejoran la experiencia de cámara, pero no entran en B1-B5.
21. **Distancia mínima de enfoque de la lente.** Origen: PCT (F28). Fase: backlog. Porqué: realismo de lente; secundario.
22. **Camino de mirada separado del de cámara.** Origen: PCT (F31). Fase: backlog. Porqué: permite mirar a un punto mientras la cámara se mueve; en COT esto se hace con un objetivo fijado.
23. **Mirar y seguir a un actor desde una clave.** Origen: COT (F30). Fase: F6. Porqué: es útil con actores. Atención: en COT la marca por clave existe pero no se usa, así que no hay que fiarse de su diseño completo; lo que sí funciona es fijar un objetivo y mirarlo cada frame con un desplazamiento.
24. **Ajustes de la cámara libre persistentes en el perfil del usuario.** Origen: VPP (F02). Fase: backlog. Porqué: comodidad.

Notas sobre lo que no se adopta: VPP no aporta nada de cámara de cine más allá de la libre; su valor para nosotros es el corte instantáneo al salir (idea 15) y los ajustes persistentes (idea 24).

## Parte 4. Licencias

| Herramienta | Licencia | Fuente | Qué implica para nosotros |
|---|---|---|---|
| COT | CC BY-SA 4.0 | `https://github.com/Jacob-Mango/DayZ-CommunityOnlineTools` (la página nombra «CC-BY-SA-4.0 license», con un fichero `LICENSE`); `COT/mod.cpp:8` apunta a ese repositorio | Copiar código obligaría a atribuir y a compartir lo derivado con la misma licencia. Solo tomamos ideas, que no están protegidas, y el repositorio de M1 es público y debe estar libre de código copiado (criterio F1). Los iconos de COT son aparte: la lista de créditos de su GUI cita CC BY 3.0 para los de game-icons.net (`COT/JM/COT/GUI/textures/icons/CREDITS.md`); no reutilizamos ninguno. |
| VPPAdminTools | Sin licencia nombrada. Condiciones de uso de la página del Workshop: permite usarlo en servidores monetizados mientras se cumplan las reglas de Bohemia; no se puede publicar en Steam, salvo la cuenta del autor; «Copyright 2026 DayZ SA Vanilla++.» | `https://steamcommunity.com/sharedfiles/filedetails/?id=1828439124`; la descripción enlaza un GitHub con el código fuente, sin licencia declarada en la página | Sin licencia de código declarada, el código no se copia ni se adapta. Solo ideas. No reempaquetamos nada de VPP. La pregunta de Guillermo («aparte de COT no puedes usar VPP?») se responde así: se puede leer y usar de referente de funciones, no como fuente de código. |
| PCT | Ninguna: «todos los derechos reservados» hasta que el autor añada una | `https://github.com/Psyern/PsyernsCinematicTool` (README, §13, línea 319) | Sin licencia, todo derecho queda reservado: ni código ni activos. Solo ideas. Depende de COT y de Community Framework (README, §13, línea 316), así que cualquier derivado heredaría también sus licencias. Los nombres de lentes de marca de su kit (primas ZEISS) son marcas ajenas: si usamos focales de serie, que sean genéricas. |

Resumen: las tres herramientas son referentes de funciones y de ideas. Ninguna da permiso para copiar código a un repositorio público bajo otra licencia. COT es la única con una licencia clara y reutilizable, y aun así su condición de «compartir igual» pesa sobre cualquier código derivado.

## Lo que no se pudo comprobar

- El código de PCT: solo se leyó su README. Lo que se dice de PCT es lo que su documentación afirma, no lo que hace el código. «No consta» significa que el README no lo menciona.
- Los textos de PCT y de las páginas de licencias (COT en GitHub, VPP en Steam) llegaron a través de WebFetch, que resume y puede abreviar las frases. Los números de línea de PCT y las frases entre comillas deben comprobarse en la página.
- No se vio ninguna ejecución: nada de esto se midió en partida. Cada afirmación sobre COT o VPP es lectura de código.
- La versión de COT es la instalada en esta máquina (`version = "2026.10.151130"` en su `mod.cpp`); la de VPP es la instalada, sin versión en su `mod.cpp`.
- «Nada llama a la marca de seguimiento por clave» y «nada llama al interruptor general de HUD» salen de buscar el nombre en todos los scripts extraídos de COT; no se miró código de otros mods que dependan de COT.
