# Cámara que sigue objetos: armas en manos, accesorios, objetos sueltos y vehículos

2026-11-10 · plan de una lane (Claude) · **v0.4**, tras dos revisiones R22 de Sol (`gpt-6.1-sol`, solo lectura; RECHAZADO sobre la v0.1 y sobre la v0.2; arbitrajes en §7 y §8) y la primera corrida de la sonda, S-track·1 (resultado y cambios en §9) · amplía la ficha **T08** del [backlog post-v1](../../backlog-post-v1.md) («Cámara que sigue al actor», M2) a cualquier objeto · contrato: `DayZSandbox_dev/product-spec.md` · cámara base: decisión #16 y F4 del [plan v2](2026-10-26-m1-cine-v2.md).

Fuentes verificadas: DayZ-Script-Diff `78be1c4` (build 1.30.164289), con rutas relativas a `scripts/`; dayz-mcp `b47d171`; lecciones del vault LL-535 y LL-551. Lo que no está verificado lleva `[sin verificar]` y lo resuelve la sonda S-track (§4).

## 0. Qué es y qué no

**Es** el mecanismo para que una cámara de Sandbox apunte a un objeto que se mueve, lo siga o vaya montada sobre él. Se calcula cada frame, en el cliente del director. Los objetivos son el arma o el objeto que un actor lleva en las manos, un accesorio de ese objeto (mira, silenciador), un objeto suelto y un vehículo.

Antes de escribir el código del producto hace falta una sonda en partida. El riesgo principal no se resuelve leyendo scripts: en qué momento del frame se lee la pose del objeto, y cuál de las lecturas posibles coincide con lo que se dibuja.

**No es:**
- encuadre automático, avisos de composición ni autoenfoque, que siguen en T08 y se certifican aparte;
- elegir el objeto haciendo clic en la vista 3D: el objetivo se elige en la web por id lógico (§3.1);
- shake, lente física ni roll (T07);
- seguir algo que no esté en la burbuja de red del cliente del director;
- probar nada en partida sin el visto bueno de Guillermo.

**Decidido por Guillermo (2026-11-10):** va en M2 y S-track corre antes. La prueba en partida sigue necesitando su visto bueno.

**Trazabilidad (R20):**
- §3 sale de la petición de Guillermo del 2026-11-10 y de T08.
- §4 y §5 salen de §1, §2 y de la revisión de Sol.
- Lo que no trace a esto no entra.

## 1. Lo que ya dice el código del juego

| # | Hecho | Fuente |
|---|---|---|
| H1 | Cualquier `Object` da su transform en mundo (`GetTransform`), sus huesos en mundo (`GetBonePositionWS`, `GetBoneTransformWS`) y sus memory points en espacio de modelo (`GetMemoryPointPos`, `MemoryPointExists`), que `ModelToWorld` pasa a mundo. Son APIs disponibles: no dicen que devuelvan la pose que se dibuja en ese frame. | `1_core/proto/enentity.c:288`; `3_game/entities/object.c:236-248`, `:452-454`, `:873` |
| H2 | Hay dos lecturas más que la v0.1 no usaba. `GetRenderTransform` es el transform de render de la entidad. `GetWorldPosition` es, según su comentario, la posición en mundo «que tiene en cuenta la transformación del proxy», frente a `GetPosition`. Las dos son candidatas en T-lect, no oráculos. | `1_core/proto/enentity.c:303`; `3_game/entities/object.c:287-291` |
| H3 | El objeto en manos de un humano sale de `GetHumanInventory().GetEntityInHands()`. El inventario del humano es síncrono, y las animaciones de coger y cambiar van por encima. | `3_game/systems/inventory/humaninventory.c:4-7`, `:16` |
| H4 | La linterna cuelga su luz de su propio memory point con la jerarquía del motor (`AttachOnMemoryPoint`, y dentro `parent.AddChild(this, pivotIndex)`). La luz sigue al objeto también cuando está en las manos. Inferencia (no medida): el objeto en manos vale como padre de jerarquía, lo que no dice que su pose leída por script esté al día. | `4_world/entities/itembase/flashlight.c:18`; `4_world/entities/scriptedlightbase.c:132-156`, `:165-192` |
| H5 | La linterna de cabeza puesta cuelga la luz del hueso `Head` del portador, y en el suelo o en las manos, del objeto. Inferencia (no medida): la ropa puesta se sigue mejor por el hueso del portador. | `4_world/entities/itembase/clothing/headtorch_colorbase.c:140-146`, `:163`, `:167-185` |
| H6 | La cámara de apuntar del jugador compone la mira con el hueso de la mano (`GetBoneIndexByName("RightHand_Dummy")` y `WeaponGetCameraPointBoneRelative`) y declara ese hueso como hueso directo de la cámara (`m_iDirectBone`, modo 4). No lee el transform en mundo del arma. | `4_world/entities/manbase/dayzplayer/dayzplayercameraironsights.c:36`, `:153`, `:222-223`; `3_game/humanitems.c:136-139` |
| H7 | Vanilla lee la boca del arma en manos de dos formas: con `weapon.ModelToWorld(...)` y con `player.ModelToWorld(...)` sobre el mismo `GetSelectionPositionMS`. Las dos no pueden estar bien a la vez en el mismo espacio. T-lect lo mide, sin suponer cuál falla. | `4_world/static/miscgameplayfunctions.c:730-733`; `5_mission/gui/crosshairselector.c:265-268` |
| H8 | En la 1.30 `GetBoneIndexByName` da ids negativos válidos (`RightHand` = −1405358722). Ausente es solo `-1`. | LL-535 |
| H9 | La cámara de dayz-mcp mueve una `Camera` desde `MissionGameplay.OnUpdate` (`Advance` y `Apply` cada frame) y ya tiene `look_at` a un punto fijo. | dayz-mcp `addon/scripts/5_Mission/MissionGameplay.c:20-31`, `MCPClientBridge.c:5579-5580`, `MCP_CameraPath.c:403-408` |
| H10 | `EOnPostFrame` no es una barrera de fin de frame: el motor lo llama «al final de cada frame o cuando la entidad se mueve durante el frame», así que puede llegar más de una vez por frame. | `1_core/proto/enentity.c:72-75`, `:189` |
| H11 | `RemoveChild` sin `keepTransform` usa el transform local como mundial: al soltar una cámara hija, la cámara salta. | `1_core/proto/enentity.c:557-560` |
| H12 | El cliente encuentra un objeto del servidor por su id de red. | `3_game/entities/object.c:817-819`; `3_game/global/game.c:356` |
| H13 | `QuatLerp` es una interpolación lineal y su resultado no es unitario. `Math3D` no trae slerp (no se ha buscado en el resto del código). | `1_core/proto/enmath3d.c:380-397` |
| H14 | La cámara de moto en tercera persona retrasa su pivote con la velocidad. Es un caso concreto (la moto), citado solo como aviso de que la cámara del jugador no vale de referencia para vehículos. | LL-551 |

## 2. Lo que no sabemos

1. **El momento del frame.** No se sabe en qué orden corren la actualización de la misión, la animación, la jerarquía, la interpolación de las réplicas, la cámara y el dibujado. Las declaraciones nativas no lo dicen. Si la cámara se coloca con la pose del frame anterior, el objeto «nada» en el plano. `[sin verificar]`
2. **Qué lectura coincide con lo dibujado** entre H1, H2 y H7. `[sin verificar]`
3. **Ropa y accesorios.** Si una mochila, una mira o un silenciador dan una pose que sigue a lo que se ve. `[sin verificar]`
4. **Réplicas de red.** El actor de IA y el coche son réplicas en el cliente del director, y su pose puede ir a saltos. `[sin verificar]`

## 3. Diseño propuesto (lo mínimo)

### 3.1 Cómo se nombra el objetivo

En el documento de escena (§3.5), un **tramo** de cámara puede llevar `track`. Un tramo es una cámara guardada, o un camino entre dos claves.

```json
"track": {
  "target": "<id lógico de actor, objeto o vehículo>",
  "on": "self | hands",
  "slot": "<ranura de accesorio, opcional; solo con hands>",
  "point": "<hueso o memory point, opcional>",
  "mode": "look_at | follow | mount",
  "offset": [0, 0, 0],
  "smooth_s": 0.0
}
```

- `on: "hands"` significa «lo que el actor tenga en las manos». Se resuelve cada frame con `GetEntityInHands` (H3). Si se quiere un objeto concreto, se nombra ese objeto (`on: "self"`).
- `slot` busca un accesorio del objeto en manos por su ranura (p. ej. `weaponOptics`). Se mantiene solo si T-ropa lo certifica.
- `point` es un hueso o un memory point. Para un hueso, ausente es solo `-1` (H8). Para un memory point, se comprueba con `MemoryPointExists`. Sin `point`, se usa el origen del objeto.
- La ropa puesta se sigue con un hueso del actor, salvo que T-ropa mida lo contrario.

### 3.2 El marco del ancla

- **Objeto sin `point`:** su transform (la lectura elegida en T-lect).
- **Hueso:** el transform del hueso en mundo (`GetBoneTransformWS`).
- **Memory point:** la posición del punto, con los ejes del objeto que lo lleva. Un memory point no tiene orientación propia.

### 3.3 Los tres modos

- `look_at`: la cámara conserva la posición de su clave o de su camino y solo gira para mirar al ancla, más un `offset` en mundo. El eje arriba es el del mundo.
- `follow`: la cámara va al ancla más un `offset` girado con el rumbo (yaw) del marco del ancla, y mira al ancla. El `offset` debe medir 0,1 m o más; si no, el esquema lo rechaza.
- `mount`: la cámara va rígida en el marco del ancla. El `offset` se da en ese marco y la orientación de la clave también se toma relativa a él.

`smooth_s` suaviza con un filtro exponencial que no depende de los FPS: α = 1 − e^(−dt/smooth_s).
- La posición se interpola de forma lineal con ese α.
- La orientación usa una slerp propia, la misma que pide la decisión #16 para los caminos: arco corto (si el producto escalar es negativo, se invierte el signo de un cuaternión) y q ← slerp(q, objetivo, α). Con el objetivo quieto, el ángulo que falta se multiplica por e^(−dt/smooth_s) en cada frame, así que no depende de los FPS. `QuatLerp` normalizado no vale: con un giro de 170° y `smooth_s` 0,3, en t = 1/6 s da 61,02° a 30 fps y 59,47° a 144 fps (SOL-T22, recalculado).
- `smooth_s` = 0 es rígido; su rango válido es [0, 2].
- Nada más: sin zona muerta ni predicción.

### 3.4 Activación, pérdida y parada

- **Activación.** El `track` está activo todo su tramo. Pasar a un tramo con otro objetivo, o sin objetivo, es un corte, nunca una interpolación entre objetivos.
- **Pérdida.** El objetivo se pierde si desaparece, si el objeto sale de las manos sin otro que lo sustituya, o si el punto deja de existir. Entonces:
  - la cámara se queda exactamente en su última pose escrita;
  - el filtro se para;
  - si iba como hija (H-c), se suelta con `keepTransform = true` (H11);
  - el cliente informa `target_lost` con el frame.
- **Recuperación.** Si el objeto vuelve a aparecer en el mismo tramo, el `track` lo recupera desde la pose congelada, con el filtro reiniciado.
- **Parada.** El stop de la toma hace lo mismo que la pérdida, más la restauración de F4.

### 3.5 Esquema y validación

- **Versión.** `track` sube en 1 la versión entera del esquema de escena (#6, cerrado).
- **Escenas viejas.** Una escena de la versión anterior carga igual y sale sin `track`. Una versión no soportada se rechaza con 0 órdenes al juego.
- **Validación estática.** Al aplicar la escena, el backend valida la forma: modos, rangos, `offset` de `follow` y que el `target` exista en la escena.
- **Validación en el cliente.** Que el punto o la ranura existan se comprueba sobre la entidad real, al preparar la toma. Si falla, no hay «cámara lista» y la toma no se arma (#4).
  - No hay catálogo de puntos por clase, porque los mods cambian los modelos.
  - La web ofrece una lista corta de sugerencias por categoría: huesos de humano, más `usti hlavne` y `konec hlavne` en las armas.
- **Vigencia de «cámara lista».** La da cada objetivo resuelto hasta su ancla final: entidad, manos, ranura y punto. Va ligada a la escena y a su generación.
  - Si se pierde el objetivo o cambia la generación antes del GO, el cliente la retira y el servidor no arma.
  - La retirada puede cruzarse con el GO. Por eso, al recibir el GO, el cliente revalida sus objetivos antes de arrancar la cámara. Si alguno falla, la cámara no arranca, el cliente informa el fallo y el servidor para la toma, que acaba `fallida` con su parada observada, como cualquier otra pérdida de un peer después de armar (S-toma).

### 3.6 Dónde se calcula

En el cliente del director, en el bucle de cámara de F4, con el hook que gane S-track para cada modo (§4.3). El servidor pasa al cliente el id de red de cada objetivo al preparar la toma (H12).

## 4. Sonda S-track

Corre en partida, sobre el banco de F0: la sonda QA de F0.2 con un verbo nuevo, solo de cliente, para el muestreo. Necesita el visto bueno de Guillermo.

**Montaje:**
- Mapa: Chernarus.
- Actor de IA que, en bucle, anda entre dos marcas y gira 180° en cada una, con un fusil M4-A1 con mira y silenciador en las manos y una mochila puesta.
- Objeto suelto al que el servidor da saltos de 1 m cada 2 s.
- Coche al que el servidor da un impulso cuesta abajo.

Cada caso dura 10 s y se repite tres veces.

**Registro por frame:** número de frame del cliente, `dt`, FPS medidos, pose de entrada leída, pose escrita en la cámara y, en H-b, cada invocación del evento con su frame. Las invocaciones duplicadas de un frame se cuentan una vez; si quedan frames sin muestra, la medida es INCONCLUSA.

**Estímulo:** el giro de 180° del actor da en la boca del fusil, entre frames, diferencias de pose mayores que 3 veces los umbrales de T-hook. El evaluador lo comprueba en los datos antes de evaluar T-hook. Si no se da, la medida es INCONCLUSA. Cada giro es una **ventana propia**: un retraso que solo se nota al girar no se diluye en el p95 de toda la corrida.

### 4.1 La referencia es lo que se dibuja

Una lectura de la cámara hecha en el mismo hook que la coloca solo devuelve lo que se escribió (Sol, SOL-T02). Por eso la referencia de S-track es la imagen:
- El arnés graba la ventana sin pérdida, con el juego limitado a 60 fps. La comprobación visual se hace solo a 60 fps; a 30 y 144 fps solo hay comprobación numérica sobre el registro (T-suave).
- Cada imagen lleva un código del frame: un widget de 8×8 px que el cliente pinta en el mismo hook en que escribe la cámara.
- **Que el código corresponda a la vista no se supone: se calibra por hook.** En una corrida de calibración, en frames alternos conocidos, el hook gira la cámara 10° y escribe el código. La imagen con el código n tiene que mostrar la vista del frame n. Si el desfase medido es k frames, constante en ≥ 99 % de las imágenes, el evaluador asocia con ese k. Si no es constante, ese hook es INCONCLUSO. Negativa: el evaluador con la asociación desplazada ±1 frame tiene que suspender la calibración.
- Sobre el arma se miden dos detalles, la boca y la mira, con el FOV y el montaje fijados para que queden a ≥ 200 px entre sí en pantalla. Con esa separación, 0,5° de giro sobre el eje óptico mueve 1,75 px y es medible.
- Antes de medir, el detector se calibra con imágenes fijas, desplazadas, giradas y escaladas a mano: error p95 ≤ 0,5 px y ≤ 0,1°. Si no llega, la medida es INCONCLUSA.
- Las imágenes repetidas o perdidas se cuentan. Una medida visual sin imagen única para ≥ 95 % de los frames de su ventana es INCONCLUSA.

### 4.2 Medidas

| Id | Qué mide | PASA |
|---|---|---|
| T-lect | La boca y la mira del fusil en manos, leídas de seis formas en el mismo frame: (a) `arma.ModelToWorld(GetMemoryPointPos)`; (b) `GetSelectionPositionWS`; (c) `actor.ModelToWorld(arma.GetSelectionPositionMS)`; (d) hueso `RightHand_Dummy` compuesto con la relación tomada en el primer frame; (e) a partir de `arma.GetRenderTransform`; (f) a partir de `arma.GetWorldPosition` y la orientación del objeto. Cada una se proyecta a pantalla con la pose de cámara del frame identificado. | La lectura cuya proyección cae a ≤ 2 px del detalle detectado en el p95, en las tres repeticiones y también durante el giro. De las que pasen, se elige la más simple. Si ninguna pasa, la medida es INCONCLUSA y se vuelve al plan. (d) no es referencia: es una candidata más. |
| T-hook | Con la lectura ganadora y para cada modo (`mount` 0,5 m, `look_at` desde una pose fija y `follow` 2 m), en tres hooks: H-a, `MissionGameplay.OnUpdate`; H-b, `EOnPostFrame` del `PlayerBase` local (`modded`; una entidad propia solo de cliente no recibe eventos por frame, §9), con duplicados resueltos; H-c, `AddChild` de la cámara al arma (solo `mount`). `mount` se prueba rígido (`smooth_s` 0) y suavizado (0,3), y sobre el arma y sobre el coche. Se mide la deriva en pantalla de la boca y de la mira respecto a donde el modo las deja. | En cada ventana de giro y en el resto por separado: deriva p95 ≤ 2 px a 1080p, los dos detalles observables en ≥ 95 % de los frames de la ventana, y giro aparente sobre el eje óptico ≤ 0,5°. La decisión es por modo, por variante de `mount` y por categoría de objetivo: el primer hook que pase en el orden H-a, H-b, H-c. Lo que no pase con ninguno queda INCONCLUSO y no entra. |
| T-ropa | La pose completa, posición y orientación, de la mochila (`GetWorldPosition` y transform) relativa al hueso `Spine3`, y la de la mira y el silenciador relativa al arma, mientras el actor anda y gira. Contraste en imagen como en T-lect. | Cada categoría por separado. «Sigue» si la pose relativa varía < 1 cm y < 0,5° y su proyección pasa T-lect. Si la mochila no sigue, la ropa va por hueso; si la mira o el silenciador no siguen, `slot` sale de §3.1. |
| T-red | Tres cosas por separado, en el actor de IA y en el coche. (1) **La cámara frente a lo dibujado:** como T-hook, en imagen. (2) **El filtro:** la pose de la cámara frente a la respuesta analítica del filtro aplicada al ancla leída en el cliente, con su `offset`. (3) **La réplica:** el retraso del ancla leída frente a la pose del servidor, alineada con la base temporal de S-toma. Solo se informa, no es fallo de la cámara. Los pasos se miden en ventanas de 1 s a velocidad casi constante (cambio < 10 %), que es donde vale la regla de la mediana (plan v2, nota de B2). | (1) como T-hook. (2) Error ≤ 2 cm p95. (3) Informe con el retraso, que vale solo si la cota de la base temporal por la velocidad máxima es ≤ 1 cm; si no, (3) es INCONCLUSA. Además, el `smooth_s` mínimo en [0, 2] con el que la cámara cumple «ningún paso mayor que 3 veces la mediana». Si ninguno lo cumple, se informa y la web avisa al elegir ese objetivo, sin prohibirlo. |
| T-suave | Numérica, sobre el registro (la imagen solo a 60 fps). El objeto suelto salta 1 m. Con `follow`, `smooth_s` en 0, 0,3 y 0,8, con el cliente limitado a 30, 60 y 144 fps. Un régimen cuyos FPS medidos se queden a más de un 10 % de su tope es INCONCLUSO, no se sustituye por otro. El tiempo cuenta desde el primer frame en que el cliente observa el salto en la entrada, no desde la orden del servidor. Además se mide un giro de la cámara de 170° y otro de −170°. | La respuesta medida sigue la exponencial analítica con un error ≤ 2 % del salto en cada frame, para cada `smooth_s` y cada FPS logrado (los FPS medidos, no el tope); con 0, igual al salto en el primer frame. En los giros, la orientación intermedia va por el arco corto, sigue siendo unitaria y coincide entre los FPS a ≤ 0,5°. |

### 4.3 Negativas (cada una debe salir como se dice, nunca PASA en falso)

- **Pose de entrada retrasada un frame**, inyectada en cada hook candidato a ganar → T-hook FALLA en ese hook, también en la imagen.
- **`smooth_s` fijado a 0,3 en el código** → T-suave FALLA en 0 y en 0,8.
- **Arco largo, y `QuatLerp` normalizado en vez de la slerp**, inyectados → T-suave FALLA en el giro.
- **Asociación de imagen desplazada ±1 frame** en el evaluador → la calibración de §4.1 FALLA.
- **Retirada de «listo» retrasada** hasta después del GO → la cámara no arranca, la toma acaba `fallida` con parada observada y nunca `terminada`.
- **Cámara congelada** (deja de escribirse) → T-red y T-hook FALLAN, aunque no haya pasos grandes.
- **Rotación inyectada alrededor del eje óptico** → T-hook FALLA por la mira.
- **El servidor borra el objetivo a mitad**, con H-a y con H-c → `target_lost`; la pose de la cámara en los frames siguientes es igual a la última escrita (≤ 1 mm, ≤ 0,01°); no hay salto al soltar la hija.
- **El actor guarda el arma en la espalda** → con `on: "hands"`, `target_lost`; con el arma nombrada (`on: "self"`), el informe dice si la sigue o da `target_lost`.
- **Punto o ranura que no existen** → no hay «cámara lista», la toma no se arma y el error dice qué falta.
- **Objetivo fuera de la burbuja, o perdido después de «listo» y antes del GO** → el cliente retira «listo» y el servidor no arma.

### 4.4 Salida de la sonda

Todo va a `DayZSandbox_dev/evidence/s-track/<run>/`:
- las muestras por frame, en JSONL;
- la grabación;
- el informe, con PASA, FALLA o INCONCLUSO por medida y por modo, y las decisiones que fija: la lectura (T-lect), el hook por modo (T-hook), la ropa y los accesorios (T-ropa) y el `smooth_s` mínimo por tipo de réplica (T-red).

El evaluador sale con código 0 si todo PASA, 1 si alguna FALLA y 2 si queda algo INCONCLUSO. Si el hook ganador de algún modo no es H-a, se propone llevarlo a F4, y F4 solo lo adopta si vuelve a pasar B2 con sus caminos sin seguimiento.

## 5. Criterios del producto (una vez pasada la sonda)

Se miden con el mismo montaje de imagen de §4.1.

| Id | Criterio | Negativa |
|---|---|---|
| K1 | `look_at` sobre la boca del fusil de un actor que anda, con `smooth_s` 0. Con la cámara fija, y otra vez con un camino conocido: la boca queda a ≤ 0,5° del eje óptico en el p95, y la posición de la cámara es la de la pose o el camino (< 1 cm). | La mirada congelada, o la cámara movida para centrar el objetivo, → FALLA. |
| K2 | `mount` sobre el arma y sobre el coche: deriva en pantalla dentro de los umbrales de T-hook para ese modo. | Objetivo borrado → `target_lost`, con la última pose ≤ 1 mm y ≤ 0,01° y sin salto. |
| K3 | `follow` con `smooth_s` > 0 sobre el actor de IA y el coche: el error frente a la trayectoria de referencia y los pasos cumplen T-red. | Cámara congelada → FALLA. `smooth_s` fuera de [0, 2], u `offset` < 0,1 m en `follow` → el esquema lo rechaza. |
| K4 | Con `on: "hands"` y los cambios A→B, A→manos vacías→B y retirar la mira (con `slot`): el primer frame en que el cliente ve el cambio de identidad, la cámara ya usa la pose del objeto nuevo o declara `target_lost`. La pose del objeto anterior no se usa nunca después. | Referencia vieja inyectada → FALLA. Manos vacías → `target_lost`, y recuperación cuando entra B. |
| K5 | Una toma con todos los objetivos resueltos se arma de verdad y rueda. | Objetivo perdido después de «listo», ranura ausente o acuse de una generación vieja → no se arma. |
| K6 | En la web, crear un `track` en una cámara guardada y en un tramo de camino, guardar, recargar y aplicar: se conserva tal cual. Una escena de la versión anterior carga. | Versión no soportada, o `track` mal formado → rechazo con 0 órdenes al juego. |

## 6. Reparto

Sigue G7 y `feedback-sol-per-phase-workers`:
- **Grok (escritor):** el verbo de muestreo en Enforce y el código de frame en pantalla.
- **Argon:** el evaluador `s_track_eval.py`, con el detector de plantilla y sus fixtures positivas y negativas.
- **Muse:** las negativas inyectadas de §4.3 y la prueba de que fallan. No escribe el evaluador.
- **Claude:** junta y mide.
- **Sol:** revisa una vez al cerrar la fase.

## 7. Revisión de Sol (R22) y arbitraje

Sol revisó la v0.1 el 2026-11-10: `gpt-6.1-sol`, solo lectura, 14 min y 109.110 tokens. El informe está en `C:\tmp\dsbx-camara-objetos-sol\out\sol-r22.md` (sha256 `d1571a6a…`), en el PC de Guillermo.

Su veredicto fue RECHAZADO por SOL-T01 y SOL-T02. Arbitra Claude, que escribió el plan (**⚠ árbitro=lane**).

**Verificación de §1 de la v0.1.** Se aceptan todas las correcciones:
- citas de la cámara de apuntar (`:36`, `:222-223`);
- ids de hueso «hashes» rebajado a «negativos válidos»;
- `QuatLerp` lineal;
- LL-551 solo para la moto;
- H3, H4 y H6 marcados como inferencias.

Sol citó `GetRenderTransform` y `GetWorldPosition`; se verificaron y entran como H2.

| Hallazgo | Sev | Decisión | Dónde |
|---|---|---|---|
| SOL-T01 calibración del primer frame no es referencia | BLOQ | Aceptado: la referencia pasa a ser la imagen y se añaden (e) y (f) | §4.1, T-lect |
| SOL-T02 T-hook se mide contra lo que escribe | BLOQ | Aceptado: T-hook se mide en imagen, con la mira fuera del eje | §4.1, T-hook |
| SOL-T03 `EOnPostFrame` varias veces por frame | MAY | Aceptado | H10, §4 registro |
| SOL-T04 un hook único para todos los modos | MAY | Aceptado: decisión por modo | T-hook |
| SOL-T05 un frame de retraso puede quedar bajo el umbral | MAY | Aceptado: giro de 180° comprobado en los datos, inyección en cada candidato | §4, §4.3 |
| SOL-T06 captura sin correspondencia de frames | MAY | Aceptado: código de frame, calibración del detector, INCONCLUSO sin detalle | §4.1 |
| SOL-T07 distancia escalar en ropa y accesorios | MAY | Aceptado: pose completa, por categoría | T-ropa |
| SOL-T08 «3× mediana» no prueba seguimiento | MAY | Aceptado: error frente a la trayectoria de referencia y negativa de cámara congelada | T-red, K3 |
| SOL-T09 un solo `smooth_s` y comienzo indefinido | MAY | Aceptado | T-suave |
| SOL-T10 marco del memory point, tramos y `offset` 0 | MAY | Aceptado | §3.2-§3.4 |
| SOL-T11 orientación con `QuatLerp` | MAY | Aceptado: arco corto y normalización | §3.3, T-suave |
| SOL-T12 validar puntos «al aplicar» sin entidades | MAY | Aceptado con otro arreglo: sin catálogo por clase (R25, los mods cambian modelos); validación estática al aplicar y del punto en el cliente al preparar, sin «cámara lista» si falta | §3.5 |
| SOL-T13 pérdida con H-c y filtro activo | MAY | Aceptado | §3.4, §4.3 |
| SOL-T14 K1 pasa moviendo la cámara | MAY | Aceptado | K1 |
| SOL-T15 «< 1 frame» no observable | MAY | Aceptado: plazo ligado al frame en que el cliente ve el cambio | K4 |
| SOL-T16 vigencia de «listo» | MAY | Aceptado | §3.5, K5 |
| SOL-T17 esquema, ida y vuelta y web | MAY | Aceptado | §3.5, K6 |

## 8. Segunda revisión de Sol (R22 sobre la v0.2) y arbitraje

El 2026-11-10 por la tarde: `gpt-6.1-sol`, 12 min, 127.632 tokens. El informe está en `C:\tmp\dsbx-camara-objetos-sol\out\sol-r22-v0.2.md` (sha256 `a6bfc199…`).

- **Cerrados:** 10 de 17 (T01, T03, T07, T09, T10, T12, T13, T14, T15 y T17). Sol da por válido el arreglo alternativo de SOL-T12.
- **Parciales:** 7.
- **Hallazgos nuevos:** SOL-T18 a SOL-T26.
- **Veredicto:** RECHAZADO.

Arbitra Claude (**⚠ árbitro=lane**). SOL-T22 se recalculó y se sostiene.

| Hallazgo | Sev | Decisión | Dónde |
|---|---|---|---|
| SOL-T18 el código de frame supone la correspondencia | BLOQ | Aceptado: calibración por hook con giros conocidos y negativa ±1 frame | §4.1, §4.3 |
| SOL-T19 0,3° no medible con un detalle cerca | MAY | Aceptado: dos detalles a ≥ 200 px, umbral 0,5°, detector calibrado en ángulo | §4.1, T-hook |
| SOL-T20 captura a 60 fps frente a T-suave a 144 | MAY | Aceptado: imagen solo a 60, el resto numérico; régimen no alcanzado → INCONCLUSO | §4.1, T-suave |
| SOL-T21 el p95 diluye los giros | MAY | Aceptado: ventanas de giro propias | §4, T-hook |
| SOL-T22 `QuatLerp` normalizado depende de los FPS | MAY | Aceptado: slerp propia, como #16 | §3.3, §4.3 |
| SOL-T23 S-tiempo no es la base temporal | MAY | Aceptado: S-toma, con cota × velocidad ≤ 1 cm | T-red |
| SOL-T24 T-red mezcla cámara, filtro y réplica | MAY | Aceptado: tres medidas separadas; la réplica se informa y no prohíbe | T-red |
| SOL-T25 carrera entre la retirada de «listo» y el GO | MAY | Aceptado: revalidación al recibir el GO y toma `fallida` con parada | §3.5, §4.3 |
| SOL-T26 cita de `GetRenderTransform` | MEN | Aceptado: `:303` | H2 |
| SOL-T04 (parcial) `mount` rígido y suavizado, categorías, regresión de F4 | MAY | Aceptado | T-hook, §4.4 |
| SOL-T08 (parcial) la mediana solo a velocidad constante | MAY | Aceptado | T-red |
| H13 «no hay slerp» | — | Aceptado: «`Math3D` no trae slerp» | H13 |

## 9. Resultado de S-track·1 y cambios de la v0.4

Corrida del 2026-11-10/12 en el PC de Guillermo, según el [brief](2026-11-10-s-track-1-brief.md) v1.1, commit `2dab484`. Informe: `DayZSandbox_dev/evidence/s-track/_informe/informe.md`; la evidencia binaria (capturas PNG y muestras) se queda en el PC, en las rutas de `evidence/s-track/README.md`. **S-track·1 no cierra** (exit 2): cumple los criterios 1, 2 y 3, el 5 en parte y no el 4.

**Lo decidido:**
- **Calibración de la imagen: PASA.** Con `MakeScreenshot` y `-autotest`, la captura pedida en el frame n muestra la vista escrita en el frame n−1 (k = −1, 100 % y único, en H-a y en H-b). La secuencia de giros es pseudoaleatoria con semilla fija: la alterna de §4.1 tiene periodo 2 y no distingue k de k ± 2.
- **Detector calibrado: PASA** (p95 0,32 px y 0,056°).

**Lo que sale, sin decidir aún:**
- **`mount` necesita H-b.** En H-a (`OnUpdate`) la boca y la recámara se desvían juntas entre 30 y 100 px. En H-b la recámara queda a 1,9 px. Los 12-14 px de la boca se atribuyen al detector, no a la cámara: con la cámara rígida sobre el arma la boca no se puede mover respecto a la recámara, y el error crece con la velocidad de giro, como cuando la plantilla arrastra fondo `[inferido]`.
- **T-lect sin ganadora.** Las lecturas (a), (e) y (f) coinciden entre sí y quedan a 12-14 px por ese error de la boca; (d), el hueso, a ~150 px; (b) y (c), sin cobertura.
- **Hueco de medida.** La plantilla se toma centrada en la proyección de la primera captura, así que un sesgo constante entre la lectura y el arma no se vería.
- `look_at`, `follow`, `mount03`, H-c y las seis negativas: INCONCLUSO por cobertura baja.

**Hechos del motor medidos** (también valen para F4):
- `Camera.SetFOV(1.0472)` a 1920×1080 da f ≈ 681-684 px, ~77° de FOV vertical efectivo, mientras `GetCurrentFOV` devuelve 1,0472. El FOV del documento de escena no se puede convertir a píxeles con el convenio vertical ni con el horizontal: hay que medirlo.
- Las entidades `ECE_LOCAL` no reciben FRAME ni POSTFRAME (House, ItemBase); `PlayerBase.EOnPostFrame` sí, una vez por frame. Por eso H-b vive en el `PlayerBase` local.
- `float.ToString` da ~6 cifras: 1 cm a x ≈ 8400 m. Las posiciones de los registros van relativas a un origen entero.
- Un cliente sin foco no carga texturas, muestra el menú de pausa y baja a ~20 fps. Las corridas se hacen con el cliente al frente.
- `dayz_test_run` de dayz-mcp no acepta argumentos de cliente, así que el banco es una instancia propia (DayZDiag, puerto 2402).

**Cambios del plan:**
- §3.6: la cámara de `mount` se escribe en H-b, salvo que S-track·2 lo desmienta. Para `look_at` y `follow` no hay decisión.
- §4.2, H-b: es el `PlayerBase` local, no una entidad propia.
- §4.1: la calibración usa una secuencia pseudoaleatoria con semilla fija y mide la focal en lugar de suponerla.

**S-track·2** hereda de S-track·1 T-ropa, T-red, T-suave, el coche, el actor de IA y los criterios K, y suma:
1. Un detector con plantilla enmascarada sobre el arma, para quitar el error de la boca.
2. Una plantilla marcada a mano en una captura, independiente de las lecturas, para cerrar el hueco del sesgo constante.
3. Más cobertura en `look_at`, `follow`, `mount03` y H-c.
4. Las negativas, que tienen que salir FALLA para que S-track cierre.
