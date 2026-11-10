# Cámara que sigue objetos: armas en manos, accesorios, objetos sueltos y vehículos

2026-11-10 · plan de una lane (Claude), pendiente de revisión R22 de Sol · v0.1 · amplía la ficha **T08** del [backlog post-v1](../../backlog-post-v1.md) («Cámara que sigue al actor», M2) a cualquier objeto · contrato: `DayZSandbox_dev/product-spec.md` · cámara base: decisión #16 y F4 del [plan v2](2026-10-26-m1-cine-v2.md).

Fuentes verificadas: DayZ-Script-Diff `78be1c4` (build 1.30.164289), rutas relativas a `scripts/`; dayz-mcp `b47d171`; lecciones del vault LL-535 y LL-551. Lo que no está verificado lleva `[sin verificar]` y lo resuelve la sonda S-track (§4).

## 0. Qué es y qué no

**Es** el mecanismo para que una cámara de Sandbox apunte a, siga o vaya montada sobre un objeto que se mueve, cada frame y en el cliente del director: el arma o el objeto que un actor lleva en las manos, un accesorio de ese objeto (mira, silenciador), un objeto suelto y un vehículo. Pide una sonda en partida antes de escribir el código del producto, porque el riesgo principal (en qué momento del frame se lee la pose del objeto) no se resuelve leyendo scripts.

**No es:**
- encuadre automático, avisos de composición ni autoenfoque (siguen en T08, se certifican aparte);
- elegir el objeto haciendo clic en la vista 3D: el objetivo se elige en la web por id lógico (§3.1);
- shake, lente física ni roll (T07);
- seguir algo que no esté en la burbuja de red del cliente del director;
- probar nada en partida sin el visto bueno de Guillermo.

Trazabilidad (R20): §3 sale de la petición de Guillermo del 2026-11-10 y de T08; §4-§5 de §1-§2. Lo que no trace a esto no entra.

## 1. Lo que ya dice el código del juego

| # | Hecho | Fuente |
|---|---|---|
| H1 | Cualquier `Object` da su transform en mundo (`GetTransform`), su posición y la de sus huesos en mundo (`GetBonePositionWS`, `GetBoneTransformWS`) y sus memory points en espacio de modelo (`GetMemoryPointPos`, `MemoryPointExists`), que `ModelToWorld` pasa a mundo. | `1_core/proto/enentity.c:288`; `3_game/entities/object.c:236-248`, `:452-454`, `:873` |
| H2 | El objeto en manos de un humano sale de `GetHumanInventory().GetEntityInHands()`. | `3_game/systems/inventory/humaninventory.c:16` |
| H3 | El juego ya hace que una luz siga a un objeto en manos: la linterna cuelga su luz de su propio memory point con `AttachOnMemoryPoint(this, "beamStart", "beamEnd")`, que usa la jerarquía del motor (`parent.AddChild(this, pivot)`). Así que el objeto en manos se mueve con la mano en el cliente y vale como padre. | `4_world/entities/itembase/flashlight.c:18`; `4_world/entities/scriptedlightbase.c:132-156`, `:165-192` |
| H4 | Para la ropa puesta el juego hace lo contrario: la linterna de cabeza, si va en la cabeza, cuelga la luz del hueso `Head` del jugador y no del objeto; si está en el suelo o en las manos, del objeto. Inferencia (no medida): la ropa puesta no lleva un transform que siga al hueso, y lo que va puesto se sigue por el hueso del portador. | `4_world/entities/itembase/clothing/headtorch_colorbase.c:140-146`, `:163`, `:167-185` |
| H5 | La cámara de apuntar del jugador no lee el transform en mundo del arma: compone la mira con el hueso de la mano (`GetBoneIndexByName("RightHand_Dummy")` y `WeaponGetCameraPointBoneRelative`) y el motor la aplica después de animar. Es el único sitio de vanilla que coloca una cámara sobre un objeto en manos cada frame. | `4_world/entities/manbase/dayzplayer/dayzplayercameraironsights.c:34`, `:148-153`; `3_game/humanitems.c:136-139` |
| H6 | Vanilla lee las posiciones del arma en manos de dos formas que no casan: `weapon.ModelToWorld(weapon.GetSelectionPositionMS("usti hlavne"))` y `player.ModelToWorld(weapon.GetSelectionPositionMS("usti hlavne"))`. Una de las dos, o las dos, depende de un espacio de modelo que no está documentado. | `4_world/static/miscgameplayfunctions.c:730-733`; `5_mission/gui/crosshairselector.c:265-268` |
| H7 | En la 1.30 `GetBoneIndexByName` da ids que son hashes y pueden ser negativos (mano derecha −1405358722): ausente es solo `-1`. | LL-535 |
| H8 | La cámara de dayz-mcp mueve una `Camera` desde `MissionGameplay.OnUpdate` (`Advance` y `Apply` cada frame) y ya tiene `look_at` a un punto fijo. Es el precedente del proyecto para el bucle de cámara. | dayz-mcp `addon/scripts/5_Mission/MissionGameplay.c:20-31`, `MCPClientBridge.c:5551-5580`, `MCP_CameraPath.c:366-417` |
| H9 | El cliente encuentra un objeto del servidor por su id de red (`GetNetworkID` en el servidor, `GetObjectByNetworkId` en el cliente). | `3_game/entities/object.c:819`; `3_game/global/game.c:356` |
| H10 | Hay matemática para todo lo de §3 sin escribir la propia: `DirectionAndUpMatrix`, `MatrixMultiply4`, `MatrixToQuat`, `QuatToMatrix` y `QuatLerp`. | `1_core/proto/enmath3d.c:150`, `:167`, `:360`, `:364`, `:397` |
| H11 | La cámara de moto en tercera persona retrasa su pivote con la velocidad (`m_LagOffsetPosition`): seguir un vehículo rápido con la cámara del jugador no vale como referencia. | LL-551 |

## 2. Lo que no sabemos (y por qué hace falta sonda)

1. **El momento del frame.** Si `MissionGameplay.OnUpdate` corre antes de que el motor anime a los humanos y mueva la jerarquía, la cámara se coloca con la pose del frame anterior y el objeto «nada» en el plano, tanto más cuanto más rápido se mueve. H5 sugiere que vanilla lo esquiva a propósito. `[sin verificar]`
2. **Qué lectura del arma es la buena** (H6), y si `GetTransform` del objeto en manos coincide con el hueso de la mano en el mismo frame. `[sin verificar]`
3. **La ropa y los accesorios.** Si una mochila o un casco puestos dan una posición que sigue al cuerpo (H4 dice que no), y si la mira montada en el arma sigue al arma. `[sin verificar]`
4. **Actores remotos y vehículos.** En el cliente del director, un actor de la IA y un coche son réplicas de red: su pose puede ir a saltos aunque el cálculo sea perfecto. `[sin verificar]`

Esto afecta también a F4 aunque no haya seguimiento: decide en qué hook vive el bucle de la cámara del producto.

## 3. Diseño propuesto (lo mínimo)

### 3.1 Cómo se nombra el objetivo

En el documento de escena (versión de esquema +1, cerrado como el resto, #6), una clave de cámara o una cámara guardada puede llevar `track`:

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

- `on: "hands"` es «lo que el actor tenga en las manos», resuelto cada frame con `GetEntityInHands` (H2): si cambia de arma, la cámara sigue a la nueva. Si se quiere un objeto concreto, se nombra el objeto (`target` = su id lógico, `on: "self"`).
- `slot` busca un accesorio del objeto en manos por su ranura (p. ej. `weaponOptics`).
- `point` es un hueso (humanos y animales, H7: ausente solo si `-1`) o un memory point (objetos y vehículos, `MemoryPointExists`). Sin `point`, el origen del objeto.
- La ropa puesta no se sigue como objeto: se sigue con un hueso del actor (`Head`, `Spine3`…), como hace vanilla (H4), salvo que S-track mida lo contrario.
- La web ofrece una lista corta de puntos por categoría (huesos de humano; `usti hlavne` y `konec hlavne` de armas; los que diga S-track de vehículos), y el servidor valida al aplicar la escena: un punto que no existe se rechaza con `anchor_missing` y 0 efectos.

### 3.2 Los tres modos

- `look_at`: la cámara se queda donde dice su clave o su camino y solo gira para mirar al punto (+ `offset` en mundo).
- `follow`: la cámara va al punto + `offset` girado con el rumbo del objetivo, y mira al punto.
- `mount`: la cámara va rígida en el marco del punto (`offset` y orientación en ese marco), como una cámara atornillada al arma o al coche.

`smooth_s` suaviza posición y orientación con un filtro exponencial que no depende de los FPS (α = 1 − e^(−dt/smooth_s); `QuatLerp` para la orientación, H10). 0 = rígido. Nada más: sin zona muerta, sin predicción.

### 3.3 Dónde se calcula

En el cliente del director, en el hook que gane S-track (§4.3): el mismo bucle que mueve la cámara de F4. El servidor pasa al cliente, al preparar la toma, el id de red de cada objetivo (H9); si el cliente no lo encuentra (fuera de la burbuja), no hay «cámara lista» y la toma no se arma (#4).

### 3.4 Si se pierde el objetivo

Si el objetivo desaparece, el objeto sale de las manos sin otro que lo sustituya, o el punto deja de existir: la cámara se queda en la última pose buena, el cliente informa `target_lost` con el instante, y no hay salto ni pose no finita. No hay cadenas de reserva («entonces sigue a la mano»), que esconden el fallo.

## 4. Sonda S-track (antes de escribir el producto)

En partida, en el banco de F0 (sonda QA de F0.2 con un verbo nuevo, solo cliente para el muestreo), con el visto bueno de Guillermo. Chernarus, un actor de IA que camina en bucle por dos marcas con un fusil en las manos (M4-A1 con mira), una mochila puesta, un objeto suelto que el servidor teletransporta 1 m cada 2 s y un coche al que el servidor da un impulso cuesta abajo. Cada caso 10 s, tres repeticiones, muestreo cada frame.

### 4.1 Medidas

| Id | Qué mide | PASA |
|---|---|---|
| T-lect | La boca del fusil en manos leída de cuatro formas en el mismo frame: (a) `arma.ModelToWorld(arma.GetMemoryPointPos("usti hlavne"))`, (b) `arma.GetSelectionPositionWS`, (c) `actor.ModelToWorld(arma.GetSelectionPositionMS)`, (d) hueso `RightHand_Dummy` del actor compuesto con la transform del arma relativa a ese hueso, tomada en el primer frame. | Informe: qué lecturas coinciden entre sí a < 1 cm en el p95 mientras el actor anda. Se elige la más simple de las que coinciden con (d). Si ninguna coincide con (d), INCONCLUSO y vuelta al plan. |
| T-hook | Con la cámara en `mount` rígido (offset 0,5 m, `smooth_s` 0) sobre la boca del fusil, en tres hooks: H-a `MissionGameplay.OnUpdate`; H-b `EOnPostFrame` de una entidad propia solo de cliente; H-c `AddChild` de la cámara al arma (H3). En cada frame, después del render del anterior, se compara la pose de la cámara activa (`GetCurrentCameraPosition/Direction`, `game.c:731-732`) con la pose esperada desde la boca en ese mismo frame. | Error p95 ≤ 1 cm y ≤ 0,2° con el actor andando. Se elige el primer hook que pase en este orden: H-a (precedente H8), H-b, H-c (H-c solo sirve para `mount` rígido). |
| T-cap | Contraste independiente de T-hook: el arnés graba 5 s de la ventana a 60 fps con el hook elegido y mide la deriva en pantalla de la boca del fusil (plantilla) respecto a su sitio. | Deriva p95 ≤ 2 px a 1080p. Si T-hook pasa y T-cap no, FALLA (la lectura propia se engaña). |
| T-ropa | Posición de la mochila puesta (`GetPosition`) frente al hueso `Spine3` mientras el actor anda; la mira montada frente a la boca del arma. | Informe: mochila «sigue» si la distancia al hueso varía < 2 cm, mira «sigue» si la distancia a la boca varía < 0,5 cm. Decide si §3.1 deja `slot` y si la ropa va por hueso. |
| T-red | Paso entre frames del punto seguido en el actor de IA (réplica de red) y en el coche. | Ningún paso supera 3 veces la mediana de su ventana (mismo criterio que B2). Si no pasa, el informe dice cuánto `smooth_s` hace falta para que pase sobre la pose de la cámara. |
| T-suave | El objeto suelto salta 1 m; `follow` con `smooth_s` 0,3, a 30, 60 y 144 fps (tope de FPS del cliente). | En t = 0,3 s la cámara ha recorrido el 63 % ± 3 % del salto en los tres FPS. |

### 4.2 Negativas (cada una debe salir como dice, nunca PASA en falso)

- Lectura retrasada un frame inyectada a mano en H-a → T-hook FALLA (prueba que la medida ve el retraso).
- `smooth_s` ignorado inyectado → T-suave FALLA.
- El servidor borra el objetivo a mitad → `target_lost`, pose finita y sin salto (paso ≤ 3× mediana).
- El actor guarda el arma en la espalda → con `on: "hands"`, `target_lost`; con el arma nombrada como objeto (`on: "self"`), sigue al arma en la espalda o da `target_lost`, y el informe dice cuál.
- `point` que no existe → rechazo `anchor_missing` al aplicar, 0 efectos.
- Objetivo fuera de la burbuja del cliente → sin «cámara lista»; la toma no se arma.

### 4.3 Salida de la sonda

`DayZSandbox_dev/evidence/s-track/<run>/`: muestras por frame (JSONL), capturas de T-cap, informe con PASA, FALLA o INCONCLUSO por medida y la decisión que fija: lectura elegida (T-lect), hook (T-hook), ropa y accesorios (T-ropa) y `smooth_s` mínimo para réplicas (T-red). Código de salida del evaluador: 0 todo PASA, 1 alguna FALLA, 2 INCONCLUSO. Si el hook ganador no es H-a, la decisión se lleva también a F4.

## 5. Criterios del producto (una vez pasada la sonda)

| Id | Criterio | Negativa |
|---|---|---|
| K1 | `look_at` sobre la boca del fusil de un actor que anda: el punto queda a < 0,5° del eje óptico en el p95 de los frames (`smooth_s` 0). | Punto inexistente → rechazo sin cambios. |
| K2 | `mount` sobre el arma y sobre el coche: la cámara mantiene su offset en el marco del punto con los umbrales de T-hook, y T-cap sigue pasando. | Objetivo borrado → `target_lost` y última pose, sin salto. |
| K3 | `follow` con `smooth_s` > 0: sin pasos > 3× la mediana sobre la pose de la cámara (B2), también con el actor de IA y el coche. | `smooth_s` fuera de [0, 2] → rechazo del esquema. |
| K4 | `on: "hands"` sigue al objeto que entre en las manos en < 1 frame después de que `GetEntityInHands` cambie. | Manos vacías → `target_lost`. |
| K5 | La toma no se arma sin todos los objetivos resueltos en el cliente. | Objetivo fuera de la burbuja → sin «cámara lista». |

## 6. Encaje y decisiones

- **Dónde va.** T08 es M2 y el spec de M1 no tiene seguimiento. Propuesta: T08 pasa a «cámara que sigue a un actor o a un objeto» en M2, y S-track corre antes, en cuanto haya visto bueno para partida, porque su T-hook decide el bucle de cámara de F4. Meterlo en M1 es cambio de alcance: Grill Modo A y un criterio B nuevo en el spec. **Decide Guillermo.**
- **Reparto** (G7 y `feedback-sol-per-phase-workers`): el verbo de muestreo de la sonda en Enforce, Grok (escritor); el evaluador `s_track_eval.py` con sus fixtures positivas y negativas, Argon; las negativas inyectadas (§4.2) y su prueba de que fallan, Muse, que no escribe el evaluador; Claude junta y mide; Sol revisa una vez al cerrar la fase.
