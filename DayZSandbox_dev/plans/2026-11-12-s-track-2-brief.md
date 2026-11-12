# S-track·2: cerrar T-lect y T-hook, con la ropa y el suavizado

2026-11-12 · spec de implementación (R25/R26) de la segunda corrida de la sonda S-track del [plan de cámara que sigue objetos](2026-11-10-camara-sigue-objetos.md) v0.4 (§9) · v1.0.

Guillermo pidió el brief el 2026-11-12 («dale»). Para correrlo en partida hace falta su visto bueno aparte.

## 0. Qué es y qué no

S-track·1 (commit `2dab484`) dejó decidida la calibración (k = −1 y f medida) y un indicio de que `mount` necesita H-b. No cerró, por tres causas que esta corrida ataca de frente:
1. **El detector falla en la boca.** La plantilla de 32 px arrastra fondo al girar, y salen 12-14 px de error.
2. **Hay un hueco de medida.** La plantilla sale de la proyección de una lectura, así que un sesgo constante no se ve.
3. **La cobertura es baja.** Se captura 1 frame de cada 10 a ~20 fps durante giros de ~1,75 s. Quedan 3 o 4 capturas por ventana, y con una perdida la ventana es INCONCLUSA.

**Es:**
- T-lect y T-hook con el arma en manos del jugador local, en los tres modos;
- las negativas de imagen (`delay1` y `roll`);
- T-ropa;
- T-suave.

Todo se hace con el jugador local, sin red.

**No es** (va a S-track·3, que necesita el actor de IA, la réplica y el servidor borrando cosas):
- T-red;
- el coche;
- `target_lost` por borrado;
- el arma a la espalda;
- las negativas de «cámara lista»;
- los criterios K.

**Cambio frente al plan** (R20, se anota en la v0.5): el plan pone el coche en T-hook. Pasa a S-track·3 porque necesita un impulso del servidor sobre un vehículo con física, y no aporta nada a cerrar T-lect.

## 1. Banco y preflight

- **El banco es el de S-track·1:** DayZDiag 1.30 propio, en el puerto 2402, lanzado por WMI, con el cliente al frente, a 1920×1080, con `-autotest` y `-limitFPS=60`. LIVE y T130 no se tocan. Antes de lanzar se comprueba que nadie usa el 2402.
- **Preflight de FPS**, nuevo:
  - Después de los 60 s de espera con el arma en manos, el mod mide 10 s.
  - Si el p50 de `dt` es > 18 ms, la corrida no se arma y deja `done.json` con `"ok": false, "causa": "fps"`.
  - El orquestador resuelve la causa y repite. Ni se mide a 20 fps ni se relaja el umbral.
  - En S-track·1, 13 de 17 corridas fueron a ~19 fps aun con foco. La causa no está medida, y averiguarla es el primer paso de la corrida.

## 2. Cambios en el mod (`qa/strack/DZS_STrack/`, sobre `2dab484`)

- **Giro más lento.** El giro en el sitio de `-strack_move=self` dura 4,0 s ± 0,3 s, en lugar de ~1,75 s. Se consigue con la ganancia del lazo de OverrideAimChangeX.
- **Captura.** Durante cada ventana de giro se captura un frame de cada 2. Fuera de los giros, uno de cada 10.
  - A 60 fps, eso da ≥ 100 capturas por giro.
  - Se registra el giro que se tiene en cada captura.
- **Ropa:**
  - con `-strack=ropa`, el jugador se viste con una mochila (`AliceBag_Green`);
  - el M4A1 lleva mira (`ACOGOptic`) y silenciador (`M4_Suppressor`), montados con `GetInventory().CreateAttachment`;
  - las clases se comprueban en el `config.cpp` vanilla antes de escribir.
- **Lecturas nuevas para T-ropa**, en cada frame:
  - la pose completa (posición y tres ejes) de la mochila, de la mira y del silenciador;
  - la del hueso `Spine3` del jugador;
  - la del arma.
  - Todo se lee con la lectura (a) y con la (f).
- **Objeto suelto para T-suave:**
  - con `-strack=suave`, el servidor crea una lata (`Pot`) a 3 m del jugador;
  - la mueve 1 m en horizontal cada 2 s con `SetPosition`;
  - escribe en su log el frame de servidor de cada salto.
  - La cámara va en `follow` sobre la lata.
- **FPS de T-suave:** se hacen tres corridas, con `-limitFPS=30`, `60` y `144`.
- **Inyecciones nuevas**, una por corrida, con `-strack_inject=`:
  - `smooth03`: `smooth_s` fijado a 0,3;
  - `quatlerp`: `QuatLerp` normalizado en lugar de la slerp propia;
  - `longarc`: la slerp sin invertir el signo.
- Lo demás no se toca: lecturas (a)-(f), hooks H-a/H-b/H-c, formato JSONL y origen relativo.

Tamaño orientativo: menos de 400 líneas nuevas de Enforce.

## 3. Casos

FOV de 60°, f medida en `calib` (no supuesta). Distancias como en S-track·1 §12 del anexo: los dos detalles a ≥ 200 px en pantalla.

| Caso | Cámara | Hooks | Movimiento |
|---|---|---|---|
| `calib` | Como S-track·1 | H-a y H-b | Ninguno |
| `mount0` | Rígida, 0,6 m a la derecha y 0,1 m arriba de `usti hlavne`, mirando a la recámara | H-a, H-b y H-c | 3 tandas de andar 3 s, girar 180° y andar 3 s |
| `mount03` | Como `mount0`, con `smooth_s` 0,3 | H-a y H-b | Igual |
| `lookat` | Fija a 1,3 m del punto de giro, mirando a `usti hlavne` | H-a y H-b | 3 giros en el sitio, con 1 s quieto entre giros |
| `follow` | 1,2 m detrás y 0,3 m arriba del ancla, girada con su rumbo | H-a y H-b | Como `mount0` |
| `ropa` | `mount0` sobre el arma con accesorios | El hook que gane `mount0` (o H-b si no gana ninguno) | Como `mount0` |
| `suave30`, `suave60`, `suave144` | `follow` sobre la lata, con `smooth_s` 0, 0,3 y 0,8 en tres tramos de 10 s; además, un giro de cámara de 170° y otro de −170° | H-b | Quieto |

**Negativas:**
- `delay1` en `mount0` (cada hook) y en `lookat` (H-a y H-b);
- `roll` en `mount0` con H-b;
- `smooth03`, `quatlerp` y `longarc` en `suave60`.

## 4. El evaluador (`qa/strack/s_track_eval.py`, sobre `2dab484`)

**Puntos de referencia marcados a mano** (cierra el hueco del sesgo constante):
- **Quién marca y dónde.** El orquestador marca en píxeles la boca y la recámara en 5 capturas por caso: la primera estable y una en mitad de cada giro y del resto. Las marca sin ver ninguna proyección de lectura.
- **Contraste a ciegas.** Grok, en una lane aparte con solo las imágenes, marca las mismas 5. Si las dos marcas difieren en más de 1,5 px en algún punto, esa marca no vale y se elige otra captura.
- **Formato.** Las marcas van en `qa/strack/marcas/<run>.json` con el sha256 de cada captura.
- **Uso.** La plantilla se recorta en la marca, no en la proyección. Las capturas marcadas son la comprobación directa: la distancia entre la proyección de cada lectura y la marca cuenta como una medida más de T-lect, con el mismo umbral.

**Plantilla enmascarada** (quita el error de la boca):
- **La máscara** son los píxeles del arma. Sale de `mount0` con el hook ganador: con la cámara rígida sobre el arma, el arma queda quieta en la imagen y el fondo se mueve.
  - Se toman los píxeles con desviación típica temporal < 8 niveles sobre ≥ 50 capturas de giro, y se quedan los conexos a la marca.
  - Se guarda como PNG junto a las marcas.
- **En los demás casos**, la máscara se lleva con la misma transformación que la plantilla (traslación más el banco de giro ±2° y escala ±5 %).
- **Correlación.** Es correlación normalizada solo sobre los píxeles de la máscara, con una plantilla de 48 px.
- **Calibración del detector:** como en S-track·1 (p95 ≤ 0,5 px y ≤ 0,1°), y además con fondo cambiante. Las imágenes sintéticas pegan el arma enmascarada sobre fondos de otras capturas.

**Cobertura.** Va por capturas, y cuenta como no observada una captura sin detección con correlación ≥ 0,8. Una ventana con < 20 capturas pedidas es INCONCLUSA por muestreo, aparte de la cobertura del 95 %.

**T-ropa:**
- Para cada categoría (mochila respecto a `Spine3`, mira y silenciador respecto al arma), se calcula la variación de la pose relativa a lo largo de la corrida.
- «Sigue» si es < 1 cm y < 0,5° en el p95 y si la proyección de un detalle de la mira (marcado a mano, como arriba) pasa el umbral de T-lect.

**T-suave**, numérica sobre `samples.jsonl`:
- El instante de cada salto es el primer frame en que la entrada leída cambia > 0,5 m.
- La respuesta tiene que seguir la exponencial analítica con un error ≤ 2 % del salto en cada frame. Con `smooth_s` 0, la cámara llega al salto en el primer frame.
- **En los giros de ±170°:**
  - va por el arco corto;
  - la norma del cuaternión queda en 1 ± 1e-4;
  - la orientación en t = 1/6 s coincide entre los FPS logrados a ≤ 0,5°.
- Un régimen cuyos FPS medidos quedan a más de un 10 % de su tope es INCONCLUSO.

**Lo que se conserva:** los umbrales del plan §4.2, k de `calib`, la f medida, los códigos de salida 0/1/2 y el informe por medida, caso y hook. Los umbrales del contrato no se tocan. Un worker que los cambie invalida la corrida.

**Fixtures offline nuevas:**
- **Sesgo constante.** Una lectura desplazada 5 px en todas las capturas: T-lect tiene que salir FALLA. En S-track·1 habría salido PASA.
- **Fondo cambiante.** El detector con máscara pasa y el detector sin máscara falla.
- **Exponencial.** Correcta (PASA), con `smooth_s` cambiado (FALLA) y con `QuatLerp` (FALLA en el giro).
- **Pocas capturas.** Una ventana con 15 capturas da INCONCLUSO.

## 5. Criterios de cierre de S-track·2

1. Los tests offline pasan y cada fixture negativa da lo esperado. Los mutantes de Muse sobre el evaluador mueren todos, cada uno al menos en un test. Son los mutantes de S-track·1 más tres:
   - plantilla en la proyección en lugar de la marca;
   - máscara ignorada;
   - el umbral de T-suave a 5 %.
2. Hay 0 `SCRIPT (E)` del mod en los logs del cliente y del servidor.
3. Todas las corridas pasan el preflight de FPS, terminan y dejan muestras, capturas y `SHA256SUMS`.
4. Las marcas a mano son de dos marcadores, con ≤ 1,5 px de diferencia.
5. Las negativas salen FALLA:
   - `delay1` y `roll` en imagen;
   - `smooth03`, `quatlerp` y `longarc` en T-suave.
   - Si alguna sale PASA o INCONCLUSO, la medida no sirve y S-track·2 no cierra.
6. El informe da una decisión, o un INCONCLUSO con causa medida, para:
   - la lectura (T-lect);
   - el hook de `mount` rígido, `mount` suavizado, `look_at` y `follow`;
   - cada categoría de T-ropa;
   - cada régimen de T-suave.

## 6. Reparto y proceso

- **Grok (escritor, sin shell):** los cambios del mod (§2), en su copia. Aparte, en otra lane, el segundo marcador a ciegas (§4).
- **Argon:** el evaluador (§4), con sus fixtures y tests, en su copia.
- **Muse:** los mutantes nuevos y la comprobación de las negativas. No escribe el evaluador.
- **Claude (orquestador, en el PC de Guillermo, por Remote Control):**
  - junta las copias, compila el PBO y corre;
  - investiga el preflight de FPS;
  - marca las capturas;
  - mide.
  - No hace commit hasta que Guillermo lo pida en el hilo.
- **Sol:** revisa una vez, al cerrar la fase S-track, no en esta corrida.
