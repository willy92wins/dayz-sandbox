# F3 sin juego (parte 1): contrato de actores, jueces de C1-C3, motor de actores falso e interfaz del núcleo

2026-11-26 · tarea **F3-offline-1**, rama `claude/project-thread-ww378c` (sobre `de4a0c7`, con F6-web parte 2 en la PR #30) · spec de implementación (R25) de la parte de F3 del [plan de M1 v2](2026-10-26-m1-cine-v2.md) (§3 F3, decisiones #5 y #12-#15) que no necesita partida · contrato: `product-spec.md` C1-C5 · v0.1, **candidata sin revisar** (§14).

**Por qué ahora.** Guillermo eligió el 26-nov a la 01:36 UTC adelantar F3 sin lanzar el juego. S3 no ha certificado nada todavía (su oráculo está en `origin/claude/s3-impl-e9` y no está congelado), así que esta parte construye solo lo que **no depende de lo que mida S3**: el formato de lo que el mod devuelve de un actor, los jueces que deciden C1, C2, C3, HOLD y ROAM a partir de esas lecturas, un motor de actores falso que las produce (con fallos inyectables) y la interfaz del motor de actores en el núcleo del mod. Lo que S3 tiene que fijar (umbrales de ROAM, observador de gestos, orden de carga del adaptador) va marcado `[verify S3]` y entra como **parámetro**, nunca como constante escondida.

**Proceso.** Esto se puede probar entero sin juego, así que, por la regla de Guillermo del 26-nov, **no pasa por Sol si el gate y las mutaciones lo prueban**. Lo que no se puede probar es el diseño de este brief: lo revisa **Gemini Neon** (Codex sin cuota) en una ronda. Después lo implementan las lanes de su PC (§12) y el gate corre en la nube.

## 0. Qué es y qué no

Es:
- **el formato de lectura de un actor** (§2): la fila que devuelve el mod por actor y los eventos de gesto, con sus validadores en un módulo nuevo `app/backend/actor_wire.py`;
- **los jueces** (§3) en `app/backend/actor_judge.py`, funciones puras sin E/S: identidad y vestuario (C1), llegada a marca (C2), gesto (C3), HOLD y ROAM (C4), cada uno con veredicto `PASA`, `FALLA` o `INCONCLUSO` y su motivo;
- **los presets de vestuario como datos** (§4): `wardrobe_items` en `fixtures/catalog-m1.json`, el multiconjunto de clases que C1 compara;
- **el motor de actores falso** (§5) en `app/tests/fake_actor_engine.py`: simula marcas, comportamientos y gestos con un reloj inyectado y produce lecturas en el formato de §2, con fallos inyectables;
- **la interfaz del motor de actores en el núcleo del mod** (§6): `DSBX_ActorEngine` con la implementación «no disponible» y su registro; la presentación (`hello`) dice el nombre del motor registrado en vez del `"none"` fijo de hoy (`DSBX_Wire.c:181`).

No es (queda para F3-offline-2 o para la partida):
- **mandar actores al mod**: ni `actor.apply` ni su cableado en `SceneLive`. Hoy una escena con actores se rechaza entera con `expansion_unavailable` (`scene_plan.py:536-546`) y **sigue así**: aceptar actores sin aplicarlos sería un éxito en silencio. El diseño del verbo y de su compensación con `scene.reset` es la parte 2, después de esta revisión;
- **el adaptador de Expansion** (su PBO, el grupo por actor, el mapeo de #13 y el observador de #14): depende de lo que certifique S3;
- la web (la biblioteca sigue sin la categoría `actor`, F6-web parte 1 §0), `m1_gate.py phase F3` (sigue `not_implemented`), el esquema y `validate.py`.

Trazabilidad (R20): §2 y §3 salen de C1-C3, C4 (HOLD y ROAM) y de las decisiones #12-#14; §4 de C1 y #12 (vestuario con la API vanilla, presets como datos); §5 de #24 (mod falso para las pruebas sin juego); §6 de #5 (núcleo sin dependencias que define la interfaz) y C5. Lo que no trace a esto no entra.

## 1. Entorno y fronteras

Gate en la nube (Linux, Python 3.13), con los comandos de `reference-cloud-gate-m1`: `python3 -m unittest discover -s app/tests -t app`. Ninguna dependencia nueva.

**Se tocan solo**:
- nuevos: `app/backend/actor_wire.py`, `app/backend/actor_judge.py`, `app/tests/fake_actor_engine.py`, `app/tests/test_actor_wire.py`, `app/tests/test_actor_judge.py`, `app/tests/test_fake_actor_engine.py`, `DayZSandbox/scripts/3_Game/DSBX_ActorEngine.c`;
- `fixtures/catalog-m1.json`: la clave nueva `wardrobe_items` (§4);
- `DayZSandbox/scripts/3_Game/DSBX_Wire.c`: la línea 181 (§6);
- `app/tests/test_mod_static.py`: `EXPECTED_C_FILES` y una comprobación nueva `check_m18` (§6), y la de M9 (`:734`) acepta el nombre que venga del registro.

No se tocan `scene_plan.py`, `scene_live.py`, `bridge.py`, `server.py`, `store.py`, `validate.py`, `profile.py`, `fake_mod.py`, `fake_world.py`, `qa/`, el esquema, la web ni ninguna otra prueba.

## 2. Formato de lectura de un actor [EXACT]

Unidades como F2 (`scene_plan.py:112-120`): posiciones en milímetros enteros, rumbo en miligrados enteros, tiempos en milisegundos enteros del reloj del servidor (`tick_ms`, F0.3-0 §1). Solo enteros: un `float` o un `bool` invalidan la fila, como en `valid_obs_now_row`.

### 2.1 Fila de actor

`[lid, cls, x_mm, y_mm, z_mm, yaw_mdeg, items, mark_i, mark_st, t_ms]`

| Campo | Tipo y rango |
|---|---|
| `lid` | `act-NN` (el patrón del esquema, `^act-(0[1-9]\|[1-9]\d+)$`) |
| `cls` | cadena no vacía de hasta 64 caracteres ASCII imprimibles |
| `x_mm`, `z_mm` | como `_valid_xz_mm` |
| `y_mm` | como `_valid_y_mm` |
| `yaw_mdeg` | como `_valid_yaw_mdeg` |
| `items` | lista de hasta 32 cadenas (clases de las prendas y objetos que lleva), cada una como `cls`; el orden no cuenta |
| `mark_i` | entero en `[-1, 63]`: el índice de la marca a la que va o en la que está; `-1` si no tiene |
| `mark_st` | `"idle"`, `"moving"`, `"arrived"` o `"unreachable"` |
| `t_ms` | entero ≥ 0 |

Un actor que ya no vive: `[lid, null, null, null, null, null, [], -1, "idle", t_ms]`, exactamente así; cualquier otra mezcla de nulos se rechaza.

`mark_st` es lo que **dice el motor**; los jueces no se fían de él para dar un `PASA` (#12: «"en marca" lo decide Sandbox midiendo»). Solo cuenta para dos cosas: `unreachable` da `FALLA` en C2 aunque las posiciones estén cerca, y la coherencia de §2.3.

### 2.2 Evento de gesto

`[lid, gi, st, t_ms, cause]`

| Campo | Tipo y rango |
|---|---|
| `lid` | como en §2.1 |
| `gi` | entero en `[0, 63]`: el índice del gesto en `gestures` del documento |
| `st` | `"requested"`, `"playing"`, `"finished"`, `"canceled"`, `"rejected"` o `"expired"` |
| `t_ms` | entero ≥ 0 |
| `cause` | `null`, o una cadena `^[a-z_]{1,24}$` (por ejemplo `combat`, `stop`, `timeout`, `interrupted`) |

Las señales son distintas a propósito (#14): pedido, en curso y el fin con su causa. `cause` solo va con `canceled`, `rejected` y `expired`; con los otros tres es `null`.

### 2.3 Validadores

`actor_wire.valid_actor_row(row, world_size)` y `actor_wire.valid_gesture_event(ev)` devuelven `True` o `False`. `actor_wire.valid_actor_read(read, world_size)` valida `{"actors": [fila...], "gestures": [evento...]}`: las dos claves obligatorias, nada más; `lid` sin repetir en `actors`; en `gestures`, `t_ms` no decreciente por `(lid, gi)` y cada `(lid, gi)` con `lid` presente en `actors`. Hasta 16 actores y 512 eventos.

## 3. Jueces [EXACT salvo lo marcado]

Módulo `app/backend/actor_judge.py`. Cada juez devuelve `{"verdict": "PASA"|"FALLA"|"INCONCLUSO", "why": <código>, ...medidas}`. Los códigos `why` son los de la tabla; las medidas, las que se nombran. Una entrada que no pasa §2.3 da `INCONCLUSO` con `why = "lectura_invalida"`, nunca `PASA`.

Las muestras de un actor son la lista de sus filas en orden de `t_ms`. **Cobertura**: una ventana `[a, b]` está cubierta si hay una muestra en `a` o antes, otra en `b` o después, y ningún hueco entre muestras consecutivas mayor que `max_gap_ms` (parámetro, 1000 por defecto). Sin cobertura no hay `PASA`: `INCONCLUSO` con `why = "sin_cobertura"`.

| Juez | `PASA` | `FALLA` | `INCONCLUSO` |
|---|---|---|---|
| `judge_identity(expected, row)` (C1) | `row.cls == expected.cls` y `Counter(row.items) == Counter(expected.items)` | otra clase (`clase`) u otro multiconjunto (`vestuario`, con `faltan` y `sobran`) | actor muerto (`muerto`) |
| `judge_mark(samples, mark, reach_m=1.5, settle_m=0.5, settle_ms=10000)` (C2) | hay un `t0` con distancia horizontal a la marca `< reach_m` y la ventana `[t0, t0 + settle_ms]` cubierta, con todas sus muestras a `< settle_m` de la posición en `t0`; devuelve `t0` y `drift_m` | ninguna muestra llega (`no_llega`), llega pero se mueve (`no_quieto`), o alguna muestra dice `unreachable` para esa marca (`inalcanzable`), aunque esté cerca | llega pero la ventana no está cubierta (`sin_cobertura`) |
| `judge_gesture(events, lid, gi)` (C3) | la secuencia de `(lid, gi)` es `requested`, `playing`, `finished`, en ese orden y con `t_ms` creciente estricto entre `requested` y `playing` | **nunca** `finished` sin un `playing` antes (`fin_sin_empezar`); `canceled` después de `playing` (`cancelado`); `rejected` (`rechazado`); `expired` (`agotado`); un evento después del fin (`despues_del_fin`) | sin eventos o solo `requested` (`sin_fin`) |
| `judge_hold(samples, window_ms, settle_m=0.5)` (C4, HOLD) | ventana `[t_primera, t_primera + window_ms]` cubierta y desplazamiento máximo respecto a la primera muestra `< settle_m` | desplazamiento `≥ settle_m` (`se_mueve`) | `sin_cobertura` |
| `judge_roam(samples, p0, radius_m, window_ms, min_path_m, min_dest_n)` (C4, ROAM) | ventana cubierta, **todas** las muestras a `≤ radius_m` de `p0`, recorrido acumulado `≥ min_path_m` y llegadas `≥ min_dest_n` (transiciones a `arrived` contadas en las filas) | una muestra fuera del radio (`fuera_radio`, con `max_dist_m`); recorrido o llegadas por debajo (`quieto`) | `sin_cobertura` |

- `radius_m` sale del `roam` del documento; `min_path_m = 40` y `min_dest_n = 4` son los de S3 §12 D1 y van como parámetros `[verify S3]`. `window_ms` = 600000 en partida (S3-05); las pruebas usan ventanas cortas.
- Distancias horizontales (x, z) en metros a partir de los milímetros; `y` no cuenta.
- `judge_gesture` mira solo los eventos de su `(lid, gi)`. Un `finished` con `cause` no nulo ya lo rechaza §2.3.
- `LOOP` y `ONCE` encadenado no tienen juez propio aquí: son `judge_mark` sobre cada marca (el de LOOP, dos vueltas). El orquestador de la partida los compone en F3-partida.

## 4. Presets de vestuario como datos [DESIGN]

`fixtures/catalog-m1.json` gana `wardrobe_items`: para cada nombre de `wardrobes`, la lista de clases vanilla que viste el actor. Cinco prendas por preset (el «5 prendas» de S3-01), de clases vanilla de ropa `[verify S3]`:

| Preset | Clases |
|---|---|
| `partisano` | `GorkaEJacket_Flat`, `GorkaPants_Flat`, `MilitaryBoots_Black`, `TacticalGloves_Black`, `BalaclavaMask_Black` |
| `civil` | `Hoodie_Grey`, `Jeans_Blue`, `AthleticShoes_Grey`, `BaseballCap_Blue`, `HikingJacket_Blue` *(esta última no: dos chaquetas no caben; ver §13)* |
| `medica` | `ParamedicJacket_Green`, `ParamedicPants_Green`, `Sneakers_White`, `SurgicalGloves_White`, `SurgicalMask` |
| `cazador` | `HuntingJacket_Brown`, `HunterPants_Brown`, `HikingBootsLow_Brown`, `WorkingGloves_Brown`, `BoonieHat_DPM` |

Para `civil`, la quinta es `Glasses_Black`... **no**: el implementador **no elige** clases. Lo que hace es dejar la tabla tal cual salga de la revisión de §14 (Neon comprueba cada nombre contra `types.xml` vanilla y la compatibilidad de ranuras: una prenda por ranura). Si una clase no se puede comprobar sin el juego, va igual y la marca `[verify S3]` queda en §13.

Regla que sí se prueba: cada preset de `wardrobes` tiene su entrada en `wardrobe_items`, con entre 1 y 32 clases, cada una válida como `cls` de §2.1, y ningún preset de más (T-W1).

## 5. Motor de actores falso [DESIGN]

`app/tests/fake_actor_engine.py`, sin red ni hilos: `FakeActorEngine(catalog, clock)` con `clock` inyectado (un `FakeClock` que avanza a mano).

- `spawn(lid, cls, x, z, yaw, wardrobe)`: crea el actor con `items = wardrobe_items[wardrobe]` del catálogo; un `wardrobe` que no esté → `ValueError`.
- `set_marks(lid, marks, behaviour, roam)`: `ONCE` va a las marcas en orden y se para en la última; `LOOP` las recorre en bucle; `HOLD` no se mueve; `ROAM` elige destinos deterministas (semilla por `lid`) en el anillo `[0.35, 0.75] × roam` alrededor de la posición inicial y va a ellos de uno en uno.
- `request_gesture(lid, gi, emote)`: emite `requested`; en el siguiente `step` en que el actor está quieto, `playing`; `duration_ms` después (por defecto 2000), `finished`.
- `step(dt_ms)`: avanza el reloj y mueve a cada actor hacia su destino a 1,4 m/s, en línea recta; al quedar a menos de 0,3 m, `mark_st = "arrived"`.
- `read()`: el `{"actors": [...], "gestures": [...]}` de §2, que tiene que pasar `valid_actor_read`. `gestures` devuelve todos los eventos desde el principio.

**Fallos inyectables** (cada uno es lo que un juez tiene que tumbar):

| Fallo | Efecto | Lo tumba |
|---|---|---|
| `unreachable(lid, mark_i)` | se para a 3 m de esa marca con `mark_st = "unreachable"` | `judge_mark` (`no_llega`) |
| `unreachable_near(lid, mark_i)` | llega a 1 m pero dice `unreachable` | `judge_mark` (`inalcanzable`) |
| `jitter(lid, amp_m)` | tras llegar oscila ± `amp_m` | `judge_mark` (`no_quieto`) y `judge_hold` |
| `drop_samples(t_from, t_to)` | `read` omite las filas con `t_ms` en ese tramo | `sin_cobertura` |
| `wardrobe_drop(lid, cls)` / `wardrobe_add(lid, cls)` / `cls_swap(lid, cls)` | quita, añade o cambia | `judge_identity` |
| `combat(lid)` | los gestos de ese actor pasan a `rejected` con `cause = "combat"` sin `playing` | `judge_gesture` (`rechazado`) |
| `cancel_after_start(lid, gi)` | tras `playing`, `canceled` con `cause = "interrupted"` | `judge_gesture` (`cancelado`) |
| `finish_without_start(lid, gi)` | `requested` y después `finished`, sin `playing` | `judge_gesture` (`fin_sin_empezar`) |
| `never_starts(lid, gi, expire_ms)` | `requested` y, pasado `expire_ms`, `expired` con `cause = "timeout"` | `judge_gesture` (`agotado`) |
| `roam_escape(lid, k, dist_m)` | el destino `k` de ROAM a `dist_m` del centro | `judge_roam` (`fuera_radio`) |
| `roam_stand_still(lid)` | ROAM sin destinos | `judge_roam` (`quieto`) |

## 6. Interfaz del motor de actores en el núcleo del mod [EXACT]

Fichero nuevo `DayZSandbox/scripts/3_Game/DSBX_ActorEngine.c`, sin ninguna referencia a Expansion (ni `eAI`, ni `Expansion`, ni `#ifdef EXPANSIONMODAI`):

```c
class DSBX_ActorEngine
{
	string Name() { return "none"; }
	bool IsAvailable() { return false; }
	// Las cinco operaciones de F3 (plan §3): devuelven un código; la base, "expansion_unavailable".
	string Spawn(string lid, string cls, vector pos, float yaw, array<string> items) { return "expansion_unavailable"; }
	string SetMarks(string lid, array<vector> marks, string behaviour, float roam) { return "expansion_unavailable"; }
	string RequestGesture(string lid, int gi, string emote) { return "expansion_unavailable"; }
	string Stop(string lid) { return "expansion_unavailable"; }
	string Despawn(string lid) { return "expansion_unavailable"; }
}

class DSBX_ActorEngineRegistry
{
	protected static ref DSBX_ActorEngine s_Engine;
	static void Register(DSBX_ActorEngine engine) { if (engine) s_Engine = engine; }
	static DSBX_ActorEngine Get() { if (!s_Engine) s_Engine = new DSBX_ActorEngine(); return s_Engine; }
	static string EngineName() { if (Get().IsAvailable()) return Get().Name(); return "none"; }
}
```

- `DSBX_Wire.c:181` pasa a `body = body + ",\"actor_engine\":" + WireText(DSBX_ActorEngineRegistry.EngineName());`. Sin adaptador, sigue saliendo `"none"`: el backend no ve ningún cambio.
- `EngineName()` solo puede dar `"none"` o el `Name()` de un motor disponible; el backend ya rechaza cualquier valor que no sea `"expansion"` o `"none"` (`bridge.py:440`), y eso no cambia.
- El adaptador (F3, con S3) registrará su motor con `DSBX_ActorEngineRegistry.Register` desde su propio PBO; el orden de carga es `[verify S3]`.
- La sintaxis de Enforce (`ref`, `static`, `array<vector>`) es `[verify]` hasta que compile en el juego; la comprobación estática de §8.3 solo mira la forma.

## 7. Lo que no cambia para nadie

Ninguna ruta, ningún verbo, ningún mensaje del bridge y ningún comportamiento del backend cambian. La única diferencia observable fuera de las pruebas nuevas es la clave `wardrobe_items` del catálogo, que nadie lee todavía en producción (`profile.py:165-181` expone `wardrobes` y `emotes`, no esta).

## 8. Pruebas (R26)

### 8.1 `app/tests/test_actor_wire.py`

| # | Positivo | Negativo |
|---|---|---|
| T-A1 fila | una fila viva válida y la fila exacta de un muerto pasan | `float` en `x_mm`; `bool` en `mark_i`; `mark_st` desconocido; `lid` `obj-01`; `items` con 33; muerto con `cls` no nulo; 9 o 11 campos |
| T-A2 evento | los seis `st` con su `cause` | `cause` no nulo con `finished`; `cause` con mayúsculas; `gi` 64 |
| T-A3 lectura | `{"actors": [...], "gestures": [...]}` con dos actores | `lid` repetido; clave extra; `t_ms` que baja en un `(lid, gi)`; evento de un `lid` sin fila; 17 actores |

### 8.2 `app/tests/test_actor_judge.py`

Cada fila, positivo y negativo, con muestras escritas a mano (no con el motor falso), y el `why` exacto:

| # | Positivo | Negativo |
|---|---|---|
| T-J1 C1 | misma clase y mismas cinco prendas en otro orden → `PASA` | una prenda de menos (`vestuario`, `faltan` la nombra); una de más; la misma prenda dos veces frente a una (multiconjunto, no conjunto); otra clase (`clase`); muerto → `INCONCLUSO` |
| T-J2 C2 | llega a 1,4 m y se queda 10 s dentro de 0,4 m → `PASA` con su `t0` | se queda a 1,6 m (`no_llega`); llega y se va 0,6 m a los 8 s (`no_quieto`); cerca pero `unreachable` (`inalcanzable`); un hueco de 1,5 s en la ventana (`sin_cobertura`); la ventana acaba antes de 10 s (`sin_cobertura`) |
| T-J3 C3 | `requested`, `playing`, `finished` → `PASA` | `requested`, `finished` (`fin_sin_empezar`); `playing`, `canceled` (`cancelado`); `rejected`; `expired`; un `playing` después de `finished` (`despues_del_fin`); solo `requested` → `INCONCLUSO`; eventos de otro `gi` no cuentan |
| T-J4 HOLD | 0,3 m de deriva en la ventana → `PASA` | 0,5 m justos → `FALLA` (el límite es estricto); hueco → `INCONCLUSO` |
| T-J5 ROAM | radio 15, todo a ≤ 15 m, 45 m recorridos, 5 llegadas → `PASA` | una muestra a 15,01 m (`fuera_radio`, `max_dist_m` 15,01); 30 m recorridos (`quieto`); 3 llegadas (`quieto`); hueco → `INCONCLUSO` |
| T-J6 nunca PASA con lectura mala | — | cada juez con una fila que no pasa §2.3 → `INCONCLUSO`, `lectura_invalida` |

### 8.3 `app/tests/test_fake_actor_engine.py` y el mod

| # | Positivo | Negativo |
|---|---|---|
| T-F1 sano | la fixture `escena-basica-cine.json` (act-01 ONCE con dos marcas y un gesto en la 2; act-02 HOLD con un gesto a 1,5 s) en el motor falso → `read()` pasa `valid_actor_read`, y C1, C2 (cada marca de act-01), C3 (los dos gestos) y HOLD (act-02) dan `PASA` | — |
| T-F2 fallos | — | cada fallo de la tabla de §5 → su juez da el `FALLA` o el `INCONCLUSO` con el `why` de la tabla, y los demás jueces del mismo actor no cambian |
| T-F3 ROAM | ROAM con radio 15 durante 10 min simulados → `PASA` | `roam_escape(k=2, 22 m)` → `fuera_radio`; `roam_stand_still` → `quieto` |
| T-W1 catálogo | cada preset con 1-32 clases válidas | un preset sin entrada; una entrada sin preset |
| T-M18 núcleo (en `test_mod_static.py`) | `DSBX_ActorEngine.c` define las dos clases y los cinco métodos con `"expansion_unavailable"`; `DSBX_Wire.c` toma `actor_engine` de `DSBX_ActorEngineRegistry.EngineName()` | ninguna aparición de `eAI`, `Expansion` ni `EXPANSIONMODAI` en el núcleo; ningún `"actor_engine\":\"none\"` literal en `DSBX_Wire.c` |

### 8.4 Regresión

Las 556 pruebas de hoy siguen en verde, con la de M9 ajustada solo para aceptar el `actor_engine` sacado del registro.

## 9. Antitautología (R26)

| # | Mutación | Tiene que fallar |
|---|---|---|
| A1 | `judge_identity` compara conjuntos (`set`) en vez de multiconjuntos | T-J1 |
| A2 | `judge_mark` no mira `unreachable` | T-J2 |
| A3 | `judge_mark` no exige cobertura | T-J2 |
| A4 | `judge_mark` usa `<=` en `reach_m` | T-J2 (1,5 m justos en una fila nueva: `no_llega`) |
| A5 | `judge_gesture` da `PASA` con `finished` aunque falte `playing` | T-J3 |
| A6 | `judge_gesture` trata `canceled` como fin bueno | T-J3 |
| A7 | `judge_hold` usa `<=` | T-J4 |
| A8 | `judge_roam` mira solo la última muestra | T-J5 |
| A9 | `judge_roam` no exige recorrido mínimo | T-J5, T-F3 |
| A10 | un juez da `PASA` con lectura inválida | T-J6 |
| A11 | `valid_actor_row` acepta `float` | T-A1 |
| A12 | el motor falso ignora `combat` | T-F2 |
| A13 | `DSBX_Wire.c` vuelve a `"none"` fijo | T-M18 |

## 10. Aceptación

- `python3 -m unittest discover -s app/tests -t app` en verde (556 + las nuevas).
- Las 13 mutaciones de §9 mueren, cada una con la prueba que la nombra.
- `git diff --stat` solo toca los ficheros de §1.

## 11. Ficheros

Los de §1. Ninguno más.

## 12. Reparto

- Revisión del brief: **Gemini Neon** (agy), una ronda, sobre este fichero, `catalog-m1.json`, `scene_plan.py:740-830` y el brief de S3; pide en especial los nombres de §4 contra `types.xml` vanilla.
- Implementación: dos lanes en paralelo, cada una en su clon temporal y su rama local:
  - **Grok** (o Muse si Grok no tiene saldo): §2, §3 y sus pruebas (`actor_wire.py`, `actor_judge.py`, T-A, T-J);
  - **Muse** (o Gemini Argon): §4, §5, §6 y sus pruebas (`fake_actor_engine.py`, catálogo, `DSBX_ActorEngine.c`, `DSBX_Wire.c`, T-F, T-W1, T-M18).
  El motor falso depende de los validadores de §2.3 para T-F1: la segunda lane escribe contra la firma de §2.3 y el orquestador junta las dos ramas.
- Fallback: el orquestador (Claude) escribe lo que una lane no entregue.
- Gate y mutaciones: el orquestador, en la nube.

## 13. Fuera de alcance, riesgos y `[verify]`

- `[verify S3]`: los umbrales de ROAM (`min_path_m`, `min_dest_n`), el observador de gestos que produzca de verdad `playing` y la causa del fin (#14), y el orden de carga del adaptador.
- `[verify]`: las clases de §4, que solo se ven en el juego. La fila `civil` tiene una errata a propósito en v0.1 (dos chaquetas) que la revisión debe resolver; el implementador no la arregla por su cuenta.
- Riesgo: el formato de §2 lo fija este brief antes de que exista el adaptador. Si S3 no puede dar alguna señal (por ejemplo `playing` separado de `requested`), C3 vuelve al Grill por la cláusula de desafío (plan #14) y el formato se enmienda con su versión.
- Fuera: `actor.apply`, el cableado en `SceneLive`, el adaptador de Expansion, la web y `m1_gate.py phase F3`. Los aborda F3-offline-2 tras esta revisión.

## 14. Cambios por la revisión

| Versión | Cambio |
|---|---|
| v0.1 | Borrador del 26-nov por la noche, para la ronda de Neon. |
