# F3 sin juego (parte 1): contrato de actores, jueces de C1-C3, motor de actores falso e interfaz del núcleo

2026-11-26 · tarea **F3-offline-1**, rama `claude/project-thread-ww378c` (sobre `de4a0c7`, con F6-web parte 2 en la PR #30) · spec de implementación (R25) de la parte de F3 del [plan de M1 v2](2026-10-26-m1-cine-v2.md) (§3 F3, decisiones #5 y #12-#15) que no necesita partida · contrato: `product-spec.md` C1-C5 · v0.2, tras la ronda de Gemini Neon (§14).

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

Unidades como F2 (`scene_plan.py:112-120`): posiciones en milímetros enteros, rumbo en miligrados enteros, tiempos en milisegundos enteros del reloj del servidor (`tick_ms`, F0.3-0 §1). Solo enteros: un `float` o un `bool` invalidan la fila, como en `valid_obs_now_row`. `world_size` es un parámetro con el mismo valor por defecto que en `scene_plan.py` (`_MAX_WORLD_SIZE`).

### 2.1 Fila de actor

`[lid, cls, x_mm, y_mm, z_mm, yaw_mdeg, items, mark_i, mark_st, t_ms]`

| Campo | Tipo y rango |
|---|---|
| `lid` | `act-NN` (el patrón del esquema, `^act-(0[1-9]\|[1-9]\d+)$`) |
| `cls` | cadena no vacía de hasta 64 caracteres ASCII imprimibles. Es **el nombre vanilla del documento** (`SurvivorM_Mirek`), nunca la clase del motor: el adaptador quita el prefijo `eAI_` al leer (#12) |
| `x_mm`, `z_mm` | como `_valid_xz_mm` |
| `y_mm` | como `_valid_y_mm` |
| `yaw_mdeg` | como `_valid_yaw_mdeg` |
| `items` | lista de hasta 32 cadenas (clases de las prendas y objetos que lleva), cada una como `cls`; el orden no cuenta |
| `mark_i` | entero en `[-1, 63]`: el índice en `marks` del documento de la marca a la que va o en la que está; `-1` si no va a ninguna marca del documento (HOLD, ROAM, o acabado) |
| `mark_st` | `"idle"`, `"moving"`, `"arrived"` o `"unreachable"` |
| `t_ms` | entero ≥ 0 |

Un actor que ya no vive: `[lid, null, null, null, null, null, [], -1, "idle", t_ms]`, exactamente así; cualquier otra mezcla de nulos se rechaza.

Coherencia que también se valida: con `mark_i == -1`, `mark_st` solo puede ser `"idle"` o `"moving"`.

`mark_st` es lo que **dice el motor**, y ningún juez lo usa para dar un `PASA` (#12: «"en marca" lo decide Sandbox midiendo»). Solo cuenta para quitarlo: `unreachable` en la marca juzgada da `FALLA` en C2 aunque las posiciones estén cerca.

### 2.2 Evento de gesto

`[lid, gi, st, t_ms, cause]`

| Campo | Tipo y rango |
|---|---|
| `lid` | como en §2.1 |
| `gi` | entero en `[0, 63]`: el índice del gesto en `gestures` del documento |
| `st` | `"requested"`, `"playing"`, `"finished"`, `"canceled"`, `"rejected"` o `"expired"` |
| `t_ms` | entero ≥ 0 |
| `cause` | con `canceled`, `rejected` y `expired`, **obligatoria**: una cadena `^[a-z_]{1,24}$` (por ejemplo `combat`, `stop`, `timeout`, `interrupted`); con `requested`, `playing` y `finished`, `null` |

Las señales son distintas a propósito (#14): pedido, en curso y el fin con su causa.

### 2.3 Validadores

En `app/backend/actor_wire.py`, con estas firmas:

- `valid_actor_row(row, world_size=_MAX_WORLD_SIZE) -> bool`
- `valid_gesture_event(ev) -> bool`
- `valid_actor_read(read, world_size=_MAX_WORLD_SIZE) -> bool`: `{"actors": [fila...], "gestures": [evento...]}`, las dos claves obligatorias y nada más; `lid` sin repetir en `actors`; en `gestures`, `t_ms` no decreciente por `(lid, gi)` y cada `lid` presente en `actors`. Hasta 16 actores y 512 eventos.

Una lectura es **una foto**: una fila por actor. Las muestras que juzga §3 son las filas de un mismo `lid` sacadas de fotos sucesivas.

## 3. Jueces [EXACT salvo lo marcado]

Módulo `app/backend/actor_judge.py`. Cada juez devuelve un `dict` con `"verdict"` (`"PASA"`, `"FALLA"` o `"INCONCLUSO"`), `"why"` (el código de la tabla, o `None` con `PASA`) y las medidas que se nombran.

**Tipos.** `samples`: lista de filas de §2.1. `expected = {"cls": str, "items": list[str]}`. `mark` y `p0`: `{"x": float, "z": float}` en metros. `faltan` y `sobran`: `list[str]` ordenada, con repeticiones. Distancias horizontales (x, z) en metros; `y` no cuenta.

**Comprobaciones comunes de `samples`**, en este orden y antes de nada:
1. alguna fila no pasa `valid_actor_row`, hay dos `lid` distintos o `t_ms` no es creciente estricto → `INCONCLUSO`, `lectura_invalida`;
2. lista vacía → `INCONCLUSO`, `sin_cobertura`;
3. alguna fila de muerto → `INCONCLUSO`, `muerto`.

**Cobertura.** Una ventana `[a, b]` está cubierta si hay una muestra con `t_ms ≤ a`, otra con `t_ms ≥ b`, y entre la última `≤ a` y la primera `≥ b` ningún hueco entre muestras consecutivas mayor que `max_gap_ms` (por defecto 1000). Las medidas de la ventana se toman sobre esas muestras (de la última `≤ a` a la primera `≥ b`, ambas incluidas).

### 3.1 `judge_identity(expected, row)` (C1)

| Veredicto | Cuándo |
|---|---|
| `INCONCLUSO` | `lectura_invalida` (la fila no pasa §2.1) o `muerto` |
| `FALLA` | `clase`: `row[1] != expected["cls"]`. Si no, `vestuario`: `Counter(row[6]) != Counter(expected["items"])`, con `faltan` y `sobran` |
| `PASA` | lo demás |

### 3.2 `judge_mark(samples, mark_i, mark, reach_m=1.5, settle_m=0.5, settle_ms=10000, max_gap_ms=1000)` (C2)

Un `t0` es **candidato** si la muestra en `t0` está a `< reach_m` de `mark`. Precedencia, de arriba abajo:

| Veredicto | Cuándo |
|---|---|
| comunes | las tres de arriba |
| `FALLA`, `inalcanzable` | alguna muestra con `mark_i` igual al juzgado y `mark_st == "unreachable"`, esté cerca o lejos |
| `PASA` | algún candidato con `[t0, t0 + settle_ms]` cubierta y todas sus muestras a `< settle_m` de la posición en `t0`. Devuelve `t0` y `drift_m`. Con `settle_ms == 0`, basta un candidato (marca de paso) |
| `FALLA`, `no_quieto` | algún candidato con la ventana cubierta en el que alguna muestra está a `≥ settle_m` |
| `INCONCLUSO`, `sin_cobertura` | hay candidatos, pero ninguno con la ventana cubierta |
| `FALLA`, `no_llega` | ningún candidato. Devuelve `min_dist_m` |

Las marcas intermedias de `ONCE` y las de `LOOP` se juzgan como marca de paso (`settle_ms = 0`); la última de `ONCE`, con los 10 s (C2).

### 3.3 `judge_gesture(events, lid, gi)` (C3)

Solo cuentan los eventos de ese `(lid, gi)`, en el orden de la lista. Precedencia, de arriba abajo:

| Veredicto | Cuándo |
|---|---|
| `INCONCLUSO`, `lectura_invalida` | algún evento no pasa §2.2 o `t_ms` baja |
| `INCONCLUSO`, `sin_fin` | ningún evento |
| `FALLA`, `sin_pedido` | el primero no es `requested` |
| `FALLA`, `repetido` | algún `st` aparece dos veces |
| `FALLA`, `despues_del_fin` | hay algún evento después del primer terminal (`finished`, `canceled`, `rejected`, `expired`), por ejemplo un arranque tardío tras un `expired` (CX-nv3) |
| `FALLA`, `cancelado` | el terminal es `canceled`, antes o después de `playing` |
| `FALLA`, `rechazado` | el terminal es `rejected` |
| `FALLA`, `agotado` | el terminal es `expired` |
| `FALLA`, `fin_sin_empezar` | el terminal es `finished` y no hubo `playing` |
| `FALLA`, `duracion_cero` | `finished` con el mismo `t_ms` que `playing` |
| `PASA` | `requested`, `playing`, `finished`, con `t_requested ≤ t_playing < t_finished` (como S3-04) |
| `INCONCLUSO`, `sin_fin` | sin terminal (`requested`, o `requested` y `playing`) |

### 3.4 `judge_hold(samples, window_ms, settle_m=0.5, max_gap_ms=1000)` (C4, HOLD)

Ventana `[t_primera, t_primera + window_ms]`. Precedencia: comunes; `FALLA`, `se_mueve` si alguna muestra de la ventana está a `≥ settle_m` de la primera (devuelve `max_drift_m`), aunque la ventana no esté cubierta; `INCONCLUSO`, `sin_cobertura`; `PASA`.

### 3.5 `judge_roam(samples, p0, radius_m, window_ms, min_path_m, min_stops_n, stop_ms=1000, stop_speed_mps=0.2, max_gap_ms=1000)` (C4, ROAM)

Ventana `[t_primera, t_primera + window_ms]`. Medidas, **todas de posiciones** (nada de `mark_st`, #12): `max_dist_m` a `p0`; `path_m`, la suma de las distancias entre muestras consecutivas; `stops_n`, cuántos tramos maximales de muestras consecutivas con velocidad `< stop_speed_mps` duran `≥ stop_ms`.

Precedencia: comunes; `FALLA`, `fuera_radio` si alguna muestra está a `> radius_m` (aunque vuelva dentro); `INCONCLUSO`, `sin_cobertura`; `FALLA`, `quieto` si `path_m < min_path_m` o `stops_n < min_stops_n`; `PASA`.

`radius_m` sale del `roam` del documento. `min_path_m = 40` y `min_stops_n = 4` son los de S3 §12 D1 (allí «llegadas»; aquí paradas medidas) y van como parámetros `[verify S3]`. `window_ms` = 600000 en partida (S3-05); las pruebas usan ventanas cortas.

`LOOP` y `ONCE` encadenado no tienen juez propio: son `judge_mark` sobre cada marca (LOOP, dos vueltas, todas de paso). El orquestador de la partida los compone en F3-partida.

## 4. Presets de vestuario como datos [DESIGN]

`fixtures/catalog-m1.json` gana `wardrobe_items`: para cada nombre de `wardrobes`, la lista de clases vanilla que viste el actor, una prenda por ranura. Cinco por preset (el «5 prendas» de S3-01), revisadas por Neon contra `types.xml` vanilla de memoria, sin el juego delante, así que siguen `[verify S3]`:

| Preset | Clases (ranura) |
|---|---|
| `partisano` | `GorkaEJacket_Flat` (Body), `GorkaPants_Flat` (Legs), `MilitaryBoots_Black` (Feet), `TacticalGloves_Black` (Gloves), `BalaclavaMask_Black` (Mask) |
| `civil` | `Hoodie_Grey` (Body), `Jeans_Blue` (Legs), `AthleticShoes_Grey` (Feet), `BaseballCap_Blue` (Headgear), `TaloonBag_Blue` (Back) |
| `medica` | `ParamedicJacket_Green` (Body), `ParamedicPants_Green` (Legs), `Sneakers_White` (Feet), `SurgicalGloves_White` (Gloves), `SurgicalMask` (Mask) |
| `cazador` | `HuntingJacket_Brown` (Body), `HunterPants_Brown` (Legs), `HikingBoots_Brown` (Feet), `WorkingGloves_Brown` (Gloves), `BoonieHat_DPM` (Headgear) |

El implementador copia la tabla tal cual. Regla que sí se prueba: cada preset de `wardrobes` tiene su entrada en `wardrobe_items`, con entre 1 y 32 clases, cada una válida como `cls` de §2.1, y ninguna entrada sin preset (T-W1).

## 5. Motor de actores falso [DESIGN]

`app/tests/fake_actor_engine.py`, sin red ni hilos: `FakeActorEngine(catalog, clock)` con `clock` inyectado (un `FakeClock` que avanza a mano, con `now_ms()`).

- `spawn(lid, cls, x, z, yaw, wardrobe)`: crea el actor con `items = wardrobe_items[wardrobe]` del catálogo; un `wardrobe` que no esté → `ValueError`.
- `set_marks(lid, marks, behaviour, roam)`: `ONCE` va a las marcas en orden (`mark_i` = la actual) y se para en la última; `LOOP` las recorre en bucle; `HOLD` no se mueve (`mark_i = -1`, `idle`); `ROAM` elige destinos deterministas (semilla por `lid`) en el anillo `[0.35, 0.75] × roam` alrededor de la posición inicial, va a ellos de uno en uno y **se para 1500 ms** en cada uno, siempre con `mark_i = -1` (`moving` o `idle`).
- `request_gesture(lid, gi, emote)`: emite `requested`; en el primer `step` en que el actor no está `moving`, `playing`; `duration_ms` después (por defecto 2000), `finished`.
- `step(dt_ms)`: avanza el reloj y mueve a cada actor hacia su destino a 1,4 m/s, en línea recta; al quedar a menos de 0,3 m, `mark_st = "arrived"` (ONCE y LOOP) y, en LOOP, a la siguiente marca en el próximo `step`.
- `read()`: una foto de §2: una fila por actor y todos los eventos de gesto desde el principio. Siempre pasa `valid_actor_read`.
- `collect(engine, until_ms, step_ms, drop=None)` (función del módulo, no del motor): llama a `step` y `read` hasta `until_ms` y devuelve `({lid: [filas]}, eventos)`. `drop = (lid, t_from, t_to)` quita del resultado las filas de ese `lid` en ese tramo: es el muestreador el que pierde muestras, no el motor.

**Fallos inyectables** (cada uno es lo que un juez tiene que tumbar):

| Fallo | Efecto | Lo tumba |
|---|---|---|
| `unreachable(lid, mark_i)` | se para a 3 m de esa marca con `mark_st = "unreachable"` | `judge_mark` (`inalcanzable`) |
| `unreachable_near(lid, mark_i)` | llega a 1 m pero dice `unreachable` | `judge_mark` (`inalcanzable`) |
| `stop_short(lid, mark_i)` | se para a 1,6 m y **dice `arrived`** | `judge_mark` (`no_llega`): no se fía del motor |
| `jitter(lid, amp_m)` | desde que se pone, en cada `step` en que no va a un destino, oscila ± `amp_m` en x | `judge_mark` (`no_quieto`) y `judge_hold` (`se_mueve`) |
| `drop` de `collect` | el muestreador pierde un tramo | `sin_cobertura` |
| `wardrobe_drop(lid, cls)` / `wardrobe_add(lid, cls)` / `cls_swap(lid, cls)` | quita, añade o cambia | `judge_identity` |
| `combat(lid)` | los gestos de ese actor pasan a `rejected` con `cause = "combat"` sin `playing` | `judge_gesture` (`rechazado`) |
| `cancel_after_start(lid, gi)` | tras `playing`, `canceled` con `cause = "interrupted"` | `judge_gesture` (`cancelado`) |
| `finish_without_start(lid, gi)` | `requested` y después `finished`, sin `playing` | `judge_gesture` (`fin_sin_empezar`) |
| `never_starts(lid, gi, expire_ms)` | `requested` y, pasado `expire_ms`, `expired` con `cause = "timeout"` | `judge_gesture` (`agotado`) |
| `late_start(lid, gi, expire_ms)` | como `never_starts`, y después `playing` y `finished` | `judge_gesture` (`despues_del_fin`) |
| `roam_escape(lid, k, dist_m)` | el destino `k` de ROAM a `dist_m` del centro | `judge_roam` (`fuera_radio`) |
| `roam_stand_still(lid)` | ROAM sin destinos | `judge_roam` (`quieto`) |
| `roam_no_stops(lid)` | ROAM sin las paradas de 1500 ms | `judge_roam` (`quieto`, por `stops_n`) |

## 6. Interfaz del motor de actores en el núcleo del mod [EXACT]

Fichero nuevo `DayZSandbox/scripts/3_Game/DSBX_ActorEngine.c`, sin ninguna referencia a Expansion fuera de los literales de código de error (ni `eAI`, ni `Expansion` con mayúscula, ni `EXPANSIONMODAI`):

```c
class DSBX_ActorEngine : Managed
{
	string Name() { return "none"; }
	bool IsAvailable() { return false; }
	// Las operaciones del plan §3 F3 (spawn, marks, behaviour, gesture y state) más parar y retirar;
	// la base devuelve el código "expansion_unavailable". State devuelve la fila de §2.1 serializada.
	string Spawn(string lid, string cls, vector pos, float yaw, array<string> items) { return "expansion_unavailable"; }
	string SetMarks(string lid, array<vector> marks, string behaviour, float roam) { return "expansion_unavailable"; }
	string RequestGesture(string lid, int gi, string emote) { return "expansion_unavailable"; }
	string State(string lid) { return "expansion_unavailable"; }
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
- La sintaxis de Enforce es `[verify]` hasta que compile en el juego; la comprobación estática de §8.3 solo mira la forma.
- **Pruebas estáticas**: M9 (`test_mod_static.py:734`) deja de exigir el literal `"none"` en la presentación (solo que la clave `actor_engine` esté); la comprobación de dónde sale el valor es solo de M18, para que la mutación A13 tumbe una sola regla (`_assert_only_rule_fails`). M18 busca `eAI`, `Expansion` y `EXPANSIONMODAI` **distinguiendo mayúsculas** y sobre el código sin comentarios, así que `"expansion_unavailable"` no cuenta.

## 7. Lo que no cambia para nadie

Ninguna ruta, ningún verbo, ningún mensaje del bridge y ningún comportamiento del backend cambian. La única diferencia observable fuera de las pruebas nuevas es la clave `wardrobe_items` del catálogo, que nadie lee todavía en producción (`profile.py:165-181` expone `wardrobes` y `emotes`, no esta).

## 8. Pruebas (R26)

### 8.1 `app/tests/test_actor_wire.py`

| # | Positivo | Negativo |
|---|---|---|
| T-A1 fila | una fila viva válida y la fila exacta de un muerto pasan | `float` en `x_mm`; `bool` en `mark_i`; `mark_st` desconocido; `mark_i = -1` con `arrived`; `lid` `obj-01`; `items` con 33; muerto con `cls` no nulo; 9 u 11 campos |
| T-A2 evento | los seis `st`, con `cause` en los tres que la llevan | `cause` no nula con `finished`; `cause` nula con `canceled`, con `rejected` y con `expired`; `cause` con mayúsculas; `gi` 64 |
| T-A3 lectura | `{"actors": [...], "gestures": [...]}` con dos actores | `lid` repetido; clave extra; `t_ms` que baja en un `(lid, gi)`; evento de un `lid` sin fila; 17 actores |

### 8.2 `app/tests/test_actor_judge.py`

Cada fila, positivo y negativo, con muestras escritas a mano (no con el motor falso), y el `why` exacto:

| # | Positivo | Negativo |
|---|---|---|
| T-J1 C1 | misma clase y mismas cinco prendas en otro orden → `PASA` | una prenda de menos (`vestuario`, `faltan` la nombra); una de más (`sobran`); la misma prenda dos veces frente a una (multiconjunto, no conjunto); otra clase (`clase`); muerto → `INCONCLUSO`, `muerto` |
| T-J2 C2 | llega a 1,4 m y se queda 10 s dentro de 0,4 m → `PASA` con su `t0`; marca de paso (`settle_ms = 0`) cruzada a 1,0 m → `PASA` | se queda a 1,6 m (`no_llega`); a **1,5 m justos** (`no_llega`: el límite es estricto); llega y se va 0,6 m a los 8 s (`no_quieto`); deriva de **0,5 m justos** (`no_quieto`); cerca pero `unreachable` en esa marca (`inalcanzable`); `unreachable` en **otra** marca no cuenta (`PASA`); un hueco de 1,5 s en la ventana (`sin_cobertura`); la traza acaba antes de los 10 s (`sin_cobertura`) |
| T-J3 C3 | `requested`, `playing`, `finished` → `PASA`; `requested` y `playing` en el mismo `t_ms` → `PASA` | `requested`, `finished` (`fin_sin_empezar`); `requested`, `playing`, `canceled` (`cancelado`); `requested`, `canceled` (`cancelado`); `requested`, `rejected` (`rechazado`); `requested`, `expired` (`agotado`); `requested`, `expired`, `playing`, `finished` (`despues_del_fin`); `playing`, `finished` (`sin_pedido`); dos `requested` (`repetido`); `finished` en el mismo `t_ms` que `playing` (`duracion_cero`); `t_ms` que baja (`lectura_invalida`); solo `requested` y `requested`, `playing` → `INCONCLUSO`, `sin_fin`; eventos de otro `gi` no cuentan |
| T-J4 HOLD | 0,3 m de deriva en la ventana → `PASA` | 0,5 m justos → `se_mueve` (estricto); hueco → `sin_cobertura` |
| T-J5 ROAM | radio 15, todo a ≤ 15 m, 45 m recorridos, 5 paradas → `PASA` | una muestra **intermedia** a 15,01 m que vuelve a 14 m (`fuera_radio`, `max_dist_m` 15,01); 30 m recorridos con 5 paradas (`quieto`); 3 paradas con 45 m (`quieto`); hueco → `sin_cobertura` |
| T-J6 nunca PASA con lectura mala | — | cada juez con una fila que no pasa §2.1 → `lectura_invalida`; `judge_mark` y `judge_roam` con filas de dos `lid` → `lectura_invalida`; con `t_ms` repetido → `lectura_invalida`; lista vacía → `sin_cobertura` |

### 8.3 `app/tests/test_fake_actor_engine.py` y el mod

| # | Positivo | Negativo |
|---|---|---|
| T-F1 sano | la fixture `escena-basica-cine.json` (act-01 ONCE con dos marcas y un gesto en la 2; act-02 HOLD con un gesto a 1,5 s) en el motor falso con `collect` cada 200 ms → todas las fotos pasan `valid_actor_read`, y dan `PASA` C1 (los dos), C2 (la marca 0 de paso y la 1 con 10 s), C3 (los dos gestos) y HOLD (act-02) | — |
| T-F2 fallos | — | cada fallo de la tabla de §5 → su juez da el veredicto y el `why` de la tabla, y los demás jueces del mismo actor y del otro actor no cambian |
| T-F3 ROAM | ROAM con radio 15 durante 10 min simulados → `PASA`, y todas las fotos con `mark_i = -1` | `roam_escape(k=2, 22 m)` → `fuera_radio`; `roam_stand_still` → `quieto`; `roam_no_stops` → `quieto` |
| T-W1 catálogo | cada preset con 1-32 clases válidas, y la tabla de §4 exacta | un preset sin entrada; una entrada sin preset |
| T-M18 núcleo (en `test_mod_static.py`) | `DSBX_ActorEngine.c` define `DSBX_ActorEngine : Managed` con los seis métodos que devuelven `"expansion_unavailable"` y el registro con `Register`, `Get` y `EngineName`; `DSBX_Wire.c` toma `actor_engine` de `DSBX_ActorEngineRegistry.EngineName()` | ninguna aparición de `eAI`, `Expansion` ni `EXPANSIONMODAI` (con mayúsculas, sin comentarios) en el núcleo; ningún `"actor_engine\":\"none\"` literal en `DSBX_Wire.c` |

### 8.4 Regresión

Las 556 pruebas de hoy siguen en verde, con la de M9 ajustada solo como dice §6.

## 9. Antitautología (R26)

| # | Mutación | Tiene que fallar |
|---|---|---|
| A1 | `judge_identity` compara conjuntos (`set`) en vez de multiconjuntos | T-J1 |
| A2 | `judge_mark` no mira `unreachable` | T-J2 |
| A3 | `judge_mark` no exige cobertura | T-J2 |
| A4 | `judge_mark` usa `<=` en `reach_m` | T-J2 (1,5 m justos) |
| A5 | `judge_gesture` da `PASA` con `finished` aunque falte `playing` | T-J3 |
| A6 | `judge_gesture` trata `canceled` como `finished` | T-J3 |
| A7 | `judge_hold` usa `<` en vez de `≥` para `se_mueve` (0,5 m pasa) | T-J4 |
| A8 | `judge_roam` mira solo la última muestra para el radio | T-J5 |
| A9 | `judge_roam` no exige recorrido mínimo | T-J5 |
| A10 | un juez da `PASA` con lectura inválida | T-J6 |
| A11 | `valid_actor_row` acepta `float` | T-A1 |
| A12 | el motor falso ignora `combat` | T-F2 |
| A13 | `DSBX_Wire.c` vuelve a `"none"` fijo | T-M18 (solo M18) |
| A14 | `judge_gesture` acepta eventos después del fin | T-J3 |
| A15 | `judge_roam` cuenta llegadas por `mark_st` en vez de paradas | T-F3 (`roam_no_stops`) |
| A16 | `judge_mark` se fía de `arrived` | T-F2 (`stop_short`) |
| A17 | `valid_gesture_event` acepta `cause` nula con `canceled` | T-A2 |

## 10. Aceptación

- `python3 -m unittest discover -s app/tests -t app` en verde (556 + las nuevas).
- Las 17 mutaciones de §9 mueren, cada una con la prueba que la nombra.
- `git diff --stat` solo toca los ficheros de §1.

## 11. Ficheros

Los de §1. Ninguno más.

## 12. Reparto

- Revisión del brief: **Gemini Neon** (agy), una ronda (hecha, v0.2).
- Implementación: dos lanes en paralelo, cada una en su clon temporal y su rama local:
  - **Grok** (o Muse si Grok no tiene saldo): §2, §3 y sus pruebas (`actor_wire.py`, `actor_judge.py`, T-A, T-J);
  - **Muse** (o Gemini Argon): §4, §5, §6 y sus pruebas (`fake_actor_engine.py`, catálogo, `DSBX_ActorEngine.c`, `DSBX_Wire.c`, T-F, T-W1, T-M18).
  El motor falso depende de los validadores de §2.3 para T-F1: la segunda lane escribe contra la firma de §2.3 y el orquestador junta las dos ramas.
- Fallback: el orquestador (Claude) escribe lo que una lane no entregue.
- Gate y mutaciones: el orquestador, en la nube.

## 13. Fuera de alcance, riesgos y `[verify]`

- `[verify S3]`: los umbrales de ROAM (`min_path_m`, `min_stops_n`, y que medir paradas equivalga a las llegadas de S3-05), el observador de gestos que produzca de verdad `playing` y la causa del fin (#14), y el orden de carga del adaptador.
- `[verify]`: las clases de §4, revisadas de memoria y no contra los ficheros del juego.
- Riesgo: el formato de §2 lo fija este brief antes de que exista el adaptador. Si S3 no puede dar alguna señal (por ejemplo `playing` separado de `requested`), C3 vuelve al Grill por la cláusula de desafío (plan #14) y el formato se enmienda con su versión.
- Fuera: `actor.apply`, el cableado en `SceneLive`, el adaptador de Expansion, la web y `m1_gate.py phase F3`. Los aborda F3-offline-2 tras esta revisión.

## 14. Cambios por la revisión

| Versión | Cambio |
|---|---|
| v0.1 | Borrador del 26-nov por la noche, para la ronda de Neon. |
| v0.2 | Ronda de Gemini Neon (`gemini-4-neon-high`, 26-nov 01:46-01:54 UTC, APTO CON CAMBIOS, 8 BLOQ, 4 MAY, 1 MEN; resumen en la carpeta del proyecto `dayz-sandbox/f3off/`), todo aplicado: marcas de paso frente a la final (H01); `judge_gesture` con partición completa, orden de `t_ms` y duración cero, como S3-04 (H02, H03); `judge_mark` con `mark_i` y una sola precedencia, `unreachable` siempre `inalcanzable` y `stop_short` nuevo (H04); ROAM por paradas medidas, sin `mark_st` (H05); firmas y tipos exactos (H06); pruebas para A4, A8 y A9 y mutaciones A14-A17 (H07); `TaloonBag_Blue` y `HikingBoots_Brown` (H08); precedencias y ventanas (H09); `mark_i = -1` en ROAM, el muestreador pierde muestras y no el motor, `jitter` en HOLD (H10); `cause` obligatoria (H11); `: Managed`, `State`, M9 y M18 sin choque (H12); `cls` vanilla en la lectura (H13). |
| v0.2a | Implementado el 26-nov por la noche: lane 1 (§2, §3, T-A, T-J) Grok `grok-4.6`, 3,5 min, 0,44 USD; lane 2 (§4-§6, T-F, T-W1, T-M18) Gemini Argon (`gemini-4-argon-high`, 11 min), porque Muse no tenía cuota (resetea el 30-nov). El orquestador juntó las dos ramas y corrigió una muestra de T-J5 (`pocas_paradas` tenía un hueco de 2 s y daba `sin_cobertura`; ahora 45 m con 3 paradas). **Medido en la nube:** 629 pruebas en verde (556 + 73 nuevas); las 18 mutaciones (A1-A17 y A11b, una segunda forma de A11 sobre `x_mm`) mueren. Guion `mutants.py` en la carpeta del proyecto `dayz-sandbox/f3off/`. |
