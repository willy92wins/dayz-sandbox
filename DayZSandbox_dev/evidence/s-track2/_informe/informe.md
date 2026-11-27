# Informe S-track·2 — cámara que sigue objetos (DayZ 1.30, banco DayZDiag)

**Actualización del 27-nov (§8):** con el evaluador r6c, T-suave 30 y 60 PASAN y 144 queda INCONCLUSO. La negativa quatlerp no inyectaba nada; se corrige en el mod r6c, pendiente de partida. Sale τ = 1,0 s por el criterio de temblor angular, a decidir. T-lect de Hb con giros lentos: lookat PASA en giro2 y giro3, y follow FALLA con 2,1–2,2 px.

**Estado global: INCONCLUSO.** Calibración PASA en Ha y Hb. T-suave PASA a 30 fps. Las negativas `smooth03` y `longarc` FALLAN, como se espera. T-hook de `mount` sobre el arma en manos (medida directa, §34): **aceptado por decisión, con el temblor medido**. Guillermo, 26-nov 15:23Z: «Vale, con suavizado»; plan v0.6, e977533. La medida no da ningún hook rígido con el arma (Hb es el único medible y el más cercano, con 5,1–5,7 px y 0,6–0,9°; Ha y Hc se mueven y giran mucho más en la imagen), y eso se acepta como temblor del arma en manos, con suavizado por defecto y aviso en la web. No es un FALLA del producto. mount03 INCONCLUSO. Negativas de mount: roll y Hb_delay1 FALLA; Ha_delay1 y Hc_delay1 INCONCLUSO. T-lect de lookat/follow por medida directa (§4b): Ha FALLA (la boca se separa de px a decenas de px); Hb INCONCLUSO (mediana 0,15–0,4 px, pero cobertura < 95 % y una cola espuria sensible a la máscara); la negativa lookat_Hb_delay1 FALLA. T-lect de mount y T-ropa quedan INCONCLUSO, cada uno con su causa en §5.

Fecha: 26-nov-2026. Corridas: 24 de la tanda nocturna del 25/26-nov en Willy, en `E:\dsbx-strack2\evidence\runs24\` (uniones a `runs\<corrida>`, con `SHA256SUMS` por corrida y `SHA256SUMS.index`). Evaluador: `qa/strack/s_track_eval.py`; su salida íntegra está en [evaluador.md](evaluador.md) e [informe.json](informe.json) (exit 2). Si se vuelve a correr el evaluador, reescribe `informe.md`: este informe se regenera a mano a partir de `evaluador.md`.

## 1. Validez de las corridas

- `check_runs.py` sobre las 24: **24 válidas / 0 inválidas**, tras el arbitraje del anexo A.4. `test_check_runs` 29/29 OK.
- Suite de S-track·2: 113/113 OK; `test_stdlib_only` OK.

## 2. Calibración

| Hook | k | f medida (px) | p05–p95 | n | Veredicto |
|---|---|---|---|---|---|
| Ha | −1 | 682,01 | 682,00–682,02 | 100 | PASA |
| Hb | −1 | 923,94 | 923,93–923,95 | 103 | PASA |

**Hallazgo:** con el mismo `fov_rad` = `fov_motor` = 1,0472 (60°), la focal efectiva depende del hook. Hb da 923,94 px, que corresponde a 60° horizontales; Ha da 682,01 px, unos 77°. La f de cada hook se usa en sus medidas. Qué hace el motor con el FOV en el hook Ha está por investigar sin partida (decisión del coordinador, 14:17Z).

Calibración del detector: INCONCLUSO, porque depende de las máscaras (ver §5).

## 3. Decisiones del evaluador

- Desfase k por hook: Ha −1, Hb −1.
- Lectura ganadora (T-lect): ninguna (INCONCLUSO, §5).
- Hook por modo: sin decisión del evaluador; para `mount`, ver §4.

## 4. T-hook de `mount` por medida directa (contrato §34, árbitro el coordinador)

Método: [qa/strack/thook_mount.py](../../../qa/strack/thook_mount.py), con 12 tests en [qa/strack/tests/test_thook_mount.py](../../../qa/strack/tests/test_thook_mount.py), 12/12 OK. Con la cámara montada sobre el arma, el arma solo se mueve en la imagen si la pose de la cámara no casa con la dibujada. Por cada captura de giro se miden dos cultivos fijos sobre el arma frente a la primera captura estable (frame ≥ 30): uno en la recámara (proyección de `konec hlavne`) y otro a 200 px hacia el receptor. Cada cultivo va normalizado (media 0, varianza 1). Deriva = p95 del mayor desplazamiento; roll = p95 del ángulo entre el segmento de referencia y el desplazado. Umbrales: ≤ 2 px y ≤ 0,5°. Las diferencias con el método pedido están en el anexo A.7.

Resultados (JSON por corrida en [thook_mount/](thook_mount/), k = −1; f = 682,01 en Ha y Hc, 923,94 en Hb). En cada ventana: p95 de la deriva en px / roll en grados (válidas/capturas). Medida final: búsqueda ±120 px con escalas y **comprobación de rigidez** (los dos cultivos deben elegir la misma escala y el segmento desplazado debe casar con ella; si no, la lectura se descarta como «no rígida»).

| Corrida | Esperado | giro1 | giro2 | giro3 | Veredicto | Lectura |
|---|---|---|---|---|---|---|
| mount0_Hb | — | 5,69 / 0,92 (108/112) | 5,46 / 0,81 (98/115) | 5,10 / 0,63 (111/118) | temblor medido (FALLA frente a 2 px) | robusto: coincide con la búsqueda estrecha (±40: 5,69 / 5,15 / 5,10) y la validación (b) confirma que el desplazamiento es real |
| mount0_Hb_roll | FALLA | 9,24 / 1,09 | 10,13 / 1,54 | 8,73 / 1,12 | **FALLA** ✔ | discrimina: deriva y roll por encima de mount0_Hb sin inyección |
| mount0_Hb_delay1 | FALLA | no rígidas (84 de 96) | 168 / 13 (25/119) | no rígidas | **FALLA** ✔ | veredicto por giro2; el resto, no rígidas |
| mount0_Ha | — | no rígidas (77) | no rígidas (92) | no rígidas (69) | INCONCLUSO `cultivos_no_rigidos` | el arma se mueve mucho más de 2 px (a ojo ≈+80/+53 px y un 20 % mayor en f000812), pero también gira en la imagen, y eso queda fuera del modelo de la medida (traslación + escala) |
| mount0_Hc | (coordinador: ≈0) | no rígidas | no rígidas | no rígidas | INCONCLUSO `cultivos_no_rigidos` | a ojo el arma gira ≈20° y se desplaza cientos de px: Hc no es rígida con el arma en estos datos |
| mount0_Hc_delay1 | FALLA | no rígidas | no rígidas | no rígidas | INCONCLUSO ✘ | no discrimina: Hc ya se mueve sin inyección |
| mount0_Ha_delay1 | FALLA | 2/120 | 0/119 | 0/121 | INCONCLUSO ✘ | `correlacion_debil` |
| mount03_Ha / mount03_Hb | — | ≤1 válida | ≤1 | 0 | INCONCLUSO `correlacion_debil` | el arma queda en la esquina y la tapa el cuerpo: el filtro de mount03 retrasa también la **posición**, y la cámara se aleja de la boca hasta 0,84 m al andar (0,608 m en mount0). La tanda corta lo repite con la posición rígida |

Sin la comprobación de rigidez, la búsqueda ancha daba en Hb giro3 68,6 px (emparejamiento espurio sobre los nervios del raíl) y en Ha/Hc cifras de 150–210 px en el límite de la búsqueda. Esas cifras no eran medidas y ya no se dan.

**Lectura.** En `mount` ningún hook da una cámara rígida con el arma. Hb es el único medible y el más cercano: ≈5 px de deriva y 0,6–0,9° de roll, que ya oscilan sin girar (validación (a)). Ha y Hc se mueven mucho más y además giran en la imagen. Negativas: roll y Hb_delay1 FALLAN como se espera; Ha_delay1 y Hc_delay1 quedan INCONCLUSO.

**Decisión (Guillermo, 15:23Z, «Vale, con suavizado»):** `mount` sobre el arma en manos se acepta con un temblor de ≈5 px, suavizado por defecto y aviso en la web. Los FALLA de esta tabla miden ese temblor frente al umbral de 2 px de una cámara rígida: son el dato de la decisión, no un FALLA del producto. Ya no se busca una lectura más precisa. El `smooth_s` por defecto en manos (el que deja la deriva p95 ≤ 2 px) sale de la tanda corta (§7).

**Validación de la medida** (pedida por el coordinador, 14:55Z):

- La corrida «de respuesta conocida» propuesta, mount0_Hc (cámara hija del arma, deriva esperada ≈0), **no lo es en estos datos**. A ojo, entre `f000030` y `f000812` el arma gira unos 20° en la imagen y se desplaza cientos de píxeles (vista lateral). Si Hc fuera hija rígida del arma, eso no pasaría. Queda como hallazgo y no como validación.
- Validación hecha en mount0_Hb:
  - (a) Capturas sin giro (giro 0, n = 117): deriva p50 2,20 px, p95 5,34, máx. 6,65. Oscila entre 0,06 y 6 px sin tendencia: el arma se balancea en las manos (respiración o sway) frente a una cámara Hb que no está atada al arma. No es ≈0 porque el arma no está quieta, no por un sesgo de la medida.
  - (b) En las capturas de giro con deriva medida ≥ 3 px (n = 35), desplazar la captura lo medido baja el error cuadrático del cultivo normalizado frente a la referencia en el **100 %** de los casos (p50 1,72 → 0,36). Si fuera luz o escala, desplazar no lo bajaría: el desplazamiento es real.
  - Contradice el «1,9 px» de S-track·1 para Hb. Aquel número salía de una plantilla anclada en la proyección y de un cultivo con el punto fijo de la HUD (anexo A.7).
- Lo que no se ha validado: una corrida con deriva conocida distinta de cero en partida (la negativa `roll` hace ese papel, con su resultado en la tabla) ni la precisión absoluta en Ha, donde el arma cambia de escala.

## 4b. T-lect de lookat/follow por medida directa (contrato §35, árbitro el coordinador, 15:39Z)

Método: [qa/strack/tlect_direct.py](../../../qa/strack/tlect_direct.py), con 7 tests en [qa/strack/tests/test_tlect_direct.py](../../../qa/strack/tests/test_tlect_direct.py), 7/7 OK. Los tres pedidos: lectura desplazada 5 px → FALLA; 3° de error en el ángulo predicho sin deriva → PASA; fondo cambiante → PASA. Además: el punto de la HUD no atrae la búsqueda, el banco no usa su propio giro, y una detección ambigua se descarta. Funcionamiento:
- La lectura (a) solo fija el ángulo 2D y la escala (f/z) de la plantilla.
- La posición se busca por NCC enmascarada en ±40 px, sin preferencia por el centro. La máscara es una franja sobre el cañón y el apagallamas.
- Deriva de cada lectura = posición detectada − proyección de esa lectura.
- El punto fijo de la HUD se borra de cada captura.

Tres cosas añadidas al aplicarlo a los datos reales (anexo A.8):
- Afinado del ángulo en ±4°.
- Banco de plantillas por vista 3D: con el giro el cañón cambia de escorzo y una sola plantilla no casa. Cada captura usa la plantilla de otro giro con vista a ≤ 10°, recortada en la proyección de su propia captura, que es el mismo hueco del sesgo.
- Rechazo de detecciones ambiguas (margen < 0,03 frente al segundo máximo local).

**Parámetros congelados el 26-nov 16:25Z** (contrato §35). La máscara de 1,2 cm por delante de la punta se fija por geometría (casquete del mismo radio que el apagallamas, sin una longitud elegida a mano), no por cuál pasa. Las cifras de abajo son con esos parámetros; los de 3 y 5 cm y las calidades de 0,4 y 0,35 son solo sensibilidad.

Resultados, lectura (a): p50 / p95 en px, fracción > 2 px, cobertura. JSON en [tlect_directa/](tlect_directa/).

| Corrida | giro1 | giro2 | giro3 | Veredicto (a) | ¿Robusto? |
|---|---|---|---|---|---|
| lookat_Hb | 0,18 / 0,69 · 0 % · 99 % | sin plantilla de otro giro en 57 de 122 (cob. 52 %) | 0,21 / 1,30 · 3 % · 98 % | (PASA en giro1/3) → **INCONCLUSO** | **no**: con 3 cm de fondo delante de la punta en la máscara, giro1/3 pasan a FALLA por una cola del 10–19 % (p95 5–6 px); la mediana sigue en 0,2 px |
| follow_Hb | 0,23 / 0,99 · 2 % · 76 % | 0,21 / **30,8** · 6 % · 80 % | 0,15 / 0,76 · 4 % · 93 % | **INCONCLUSO** (`low_coverage` + cola) | **no**: el 6 % de giro2 son emparejamientos espurios cañón arriba, en una junta parecida a la punta (comprobado a ojo en f000990: la proyección de (a) cae en el apagallamas). Con 3 cm la cola desaparece, pero la cobertura sigue < 95 % |
| lookat_Ha | 3,08 / 25,3 · 63 % | 0,65 / 6,8 · 17 % (cob. 50 %) | 4,39 / 25,6 · 75 % | **FALLA** | sí: con todos los parámetros probados, la mediana es 0,6–4,4 px y el 15–77 % de las capturas pasa de 2 px |
| follow_Ha | 1,18 / 17,2 · 34 % | 7,86 / 15,9 · 79 % | 1,31 / 11,4 · 37 % | **FALLA** | sí (mediana 1,2–7,9 px, 32–79 % > 2 px) |
| lookat_Hb_delay1 (negativa) | 1,29 / 5,28 · 36 % | 0,81 / 10,7 · 17 % | 1,91 / 5,26 · 48 % | **FALLA** ✔ | sí: mediana 4–10 veces la de lookat_Hb y entre el 16 % y el 54 % > 2 px con todos los parámetros |
| lookat_Ha_delay1 (negativa) | 2,93 / 19,7 · 58 % | 0,20 / 10,9 · 17 % | 6,51 / 37,4 · 73 % | FALLA | no discrimina: Ha ya FALLA sin inyección |

Lecturas b, c y d: FALLA en todas las corridas, por cientos o miles de píxeles. Lecturas e y f: igual que (a) (p95 a ≤ 0,15 px de (a) en lookat_Hb).

**Lectura.** En lookat y follow, Ha se separa de la boca real (deriva de px a decenas de px), como en `mount`. Hb queda en una mediana de 0,15–0,4 px, pero su p95 depende de una cola del 0–19 % de emparejamientos espurios que cambia con los parámetros de la máscara. Por la regla del tope (coordinador, 15:39Z: sin cobertura ≥ 95 % → INCONCLUSO con su causa), **T-lect de Hb en lookat/follow queda INCONCLUSO**, con causa «cobertura < 95 % y cola espuria sensible a la máscara». Lo dejo aquí. La negativa delay1 de Hb sí discrimina.

**Conclusión para el plan** (coordinador, 16:25Z): lookat y follow tampoco van en H-a (FALLA robusto); H-b queda como candidato sin confirmar.

**Por qué giro2 no tiene plantilla:** los tres giros suman 180° en el mismo sentido. giro1 recorre los rumbos 0→180, giro2 180→360 y giro3 360→540, que equivale a 0→180. giro1 y giro3 comparten vistas y giro2 está solo. Girar más despacio no lo arregla, porque solo da más capturas dentro del mismo giro, y el banco excluye su propio giro. Por eso el mod r6b añade, además de `-strack_giro_lento`, `-strack_giro_alterno=1`: giro2 vuelve en sentido contrario y recorre los mismos rumbos (§7).

## 5. Medidas INCONCLUSO y su causa

| Medida | Corridas | Causa |
|---|---|---|
| T-lect (todas las lecturas a–f) | lookat, follow, mount0, mount03 | `mascara_vacia`: la desviación típica temporal del cultivo en bruto nunca baja de `MASK_STD_MAX` = 8 (p50 15). En Ha el arma se mueve en la imagen (lo que mide T-hook); en Hb el brillo del cultivo pasa de 63 a 119 al girar con el sol. Decisión del coordinador (14:17Z): registro de máscara solo para su forma, normalización en dos pasadas para lookat/follow. **Probada sin partida y no basta en lookat** (`bench\diag_mascara3.py`): la boca queda en el centro exacto, sobre el punto fijo de la HUD, pero el arma gira en la imagen (el cañón apunta en direcciones distintas entre giros) y el fondo se desplaza. Con dos pasadas el 75 % del cultivo baja de 8, pero el centro sube (de 7,7 a 13,4 en Hb y de 3,8 a 17,3 en Ha) y la máscara conexa al centro queda vacía (0 px). Una máscara por varianza temporal necesita un objeto quieto en la imagen; la luz se corrige, la rotación no |
| T-hook lookat/follow (evaluador) | lookat_Ha/Hb, follow_Ha/Hb | `mascara_vacia`, misma causa. Sustituido por la medida directa de §4b: Ha FALLA; Hb INCONCLUSO |
| Calibración del detector | — | depende de las máscaras |
| T-ropa | ropa_Hb | `mira_sin_marca_valida`: en ropa las marcas a mano dan 15–18 px entre marcadores y caen en el silenciador, no en el apagallamas; se descartaron (anexo A.6) |
| T-sesgo | todos los casos | informativo (no bloquea, anexo A.3). Solo es observable en mount0, `punto_mira`: p95 494 px en las lecturas a/e/f y 777 px en d, con 5 marcas por hook (15 en total). El resto: `sesgo_no_observable` |
| T-suave 60 y 144 | suave60_Hb, suave144_Hb | `fps_regime`: la corrida fue a 47 y 116 fps reales con capturas, no a 60/144. La próxima tanda repite estas corridas sin capturas (§7) |

## 6. T-suave y negativas

| Corrida | Esperado | Obtenido | Comentario |
|---|---|---|---|
| suave30_Hb | PASA | **PASA** | las 5 ventanas |
| suave60_Hb_smooth03 | FALLA | **FALLA** | OK |
| suave60_Hb_longarc | FALLA | **FALLA** | OK |
| suave60_Hb_quatlerp | FALLA | PASA | no discrimina a fps fijo: a α ≈ 0,055, `Math3D.QuatLerp` (nlerp) se separa < 2 % de slerp. Decisión del coordinador: juzgarla entre fps (30 y 144) por la orientación a t = 1/6 s, ≤ 0,5° (§7) |
| lookat_Hb_delay1 | FALLA | **FALLA** | medida directa de T-lect (§4b) |
| lookat_Ha_delay1 | FALLA | FALLA | no discrimina: Ha ya FALLA sin inyección (§4b) |
| mount0_Hb_roll, mount0_Hb_delay1 | FALLA | **FALLA** | medida directa de T-hook (§4) |
| mount0_Ha_delay1 | FALLA | INCONCLUSO | `correlacion_debil` (§4) |
| mount0_Hc_delay1 | FALLA | INCONCLUSO | `cultivos_no_rigidos`: Hc ya se mueve sin inyección (§4) |

## 7. Pendiente (necesita la partida; no se ha corrido)

Tanda corta para otra noche, **preparada y no lanzada** (la caja es de M1; necesita el OK de esa noche). Va en un solo script, `C:\tmp\dsbx-strack2\bench\night_corta.ps1`, que usa `run_case3.ps1` y el mod r6b (`bench\@DZS_STrack_r6`, PBO de 74 266 B, sha256 `eaf22bb916b684a1…`, linter PASS 0/0; contrato §36). Perfiles en `E:\dsbx-strack2\runs_r6`. Las 12 corridas:

1. suave30_Hb, suave60_Hb y suave144_Hb **sin capturas** (`-strack_noshots=1`), para juzgar T-suave en su régimen de fps.
2. suave30_Hb_quatlerp y suave144_Hb_quatlerp sin capturas, juzgadas entre fps por la orientación a t = 1/6 s (≤ 0,5°).
3. mount03_Hb con la posición rígida (`-strack_smooth_pos=0`, filtro de 0,3 s solo en la orientación): el «mejor encuadre» pedido.
4. Barrido de `smooth_s` en mount0_Hb con la posición rígida: 0,1 / 0,2 / 0,5 / 1,0 s. El punto 0 es mount0_Hb de runs24 y el 0,3 es el punto 3. Sirve para sacar el `smooth_s` por defecto en manos: el menor τ con `sin_giro` p95 ≤ 2 px (decisión A del coordinador, 15:39Z). El retraso en giros se da aparte, en grados y en ms.
5. lookat_Hb y follow_Hb con giros a la mitad de velocidad y alternos (`-strack_giro_lento=0.5 -strack_giro_alterno=1`), para T-lect directa de Hb. Sus giros duran ≈8 s y `check_runs` (4,0 ± 0,3 s) los marcará: es esperado.

**Premisa a confirmar antes de usar el barrido:** con suavizado, la deriva durante los giros incluye también el retraso del filtro, que crece con τ. Puede no haber ningún τ que deje p95 ≤ 2 px en los giros aunque quite el temblor. Por eso la medida da además una ventana `sin_giro` (quieto y andando), donde solo hay temblor. Propuesta: elegir τ por `sin_giro` ≤ 2 px e informar del retraso en giros aparte.

Sin partida: la f del hook Ha. La máscara de lookat/follow, ver §5.

## 8. Tanda corta r6b (27-nov, madrugada) y parches r6c (27-nov, tarde)

La tanda corta de §7 corrió el 27-nov, entre las 02:35 y las 04:10 (hora de Madrid), con el mod r6b. Los datos están en `E:\dsbx-strack2\runs_r6`, y la evidencia de este informe en [tanda_r6b/](tanda_r6b/). A las 04:35Z se llenó C:, por un proceso ajeno a S-track (el pagefile llegó a 123 GB). La suite y los mutantes murieron por ese motivo, no por un test, y Windows se reinició a las 06:16. Las decisiones de esta sección son del coordinador (árbitro el orquestador, 27-nov 04:45Z).

**T-suave.** La primera evaluación de r6b ([tanda_r6b/suave/](tanda_r6b/suave/)) daba FALLA del acuerdo entre fps en 30 y 60 (`suave_fps_agree_exceeded`). Era un artefacto del evaluador: comparaba la orientación **absoluta** a t = 1/6 s, y cada corrida empieza con otro rumbo (entre 74 y 98° de diferencia). r6c compara la rotación **relativa** al inicio de cada giro, q·conj(q_origen) en ejes del mundo (`_quat_rel_mundo` en `qa/strack/s_track_eval.py`), con el test `qa/strack/tests/test_suave_relativo.py`: con rumbos distintos y el mismo filtro da PASA, y con otro τ en el tramo 4 da FALLA por el acuerdo. Reevaluadas las corridas r6b con el evaluador r6c ([tanda_r6b/suave_r6c_eval/](tanda_r6b/suave_r6c_eval/)): **T-suave 30 PASA, 60 PASA y 144 INCONCLUSO** (`fps_regime`).

**suave144 a 59 fps.** `-limitFPS=144` llegó al cliente: consta en la línea de comandos de los RPT de las 02:39 y las 02:47. El perfil del banco (`E:\dsbx-strack2\runs_r6\client\profiles\Users\guill\DayZ.cfg`, que el cliente reescribió a las 03:51) tiene `VSync=1`; el DayZ.cfg de Guillermo, en Documentos, tiene `VSync=0`. **Hipótesis, sin probar:** VSync lo limita al refresco del monitor. La prueba que la confirma o la tumba es repetir suave144 con VSync=0 en el perfil del banco.

**Negativa quatlerp.** En r6b no inyectaba nada. `Math3D.QuatLerp` (con normalización posterior) daba el mismo camino que el slerp: el primer paso de un salto de 170° a 30 fps sale 18,21° con quatlerp frente a 18,22° sin él, y lo mismo a 144 fps (9,37 frente a 8,83, dentro de la variación entre corridas). Era un fallo del mod. r6c lo cambia por un nlerp explícito (lerp por componentes y normalización) en `STRACK_Math.SlerpMode`, modo 1. La negativa vuelve a la próxima tanda con el mod r6c.

**`smooth_s` por defecto en manos.** El criterio A (`sin_giro` p95 ≤ 2 px) queda descartado: suavizar no fija el arma en pantalla. Al andar, el arma se balancea, la cámara suavizada va detrás y el arma se mueve más en la imagen ([tanda_r6b/barrido_smooth.json](tanda_r6b/barrido_smooth.json), `thook_*.json`). El nuevo criterio es el menor τ con un temblor angular de la cámara, por encima de 2 Hz, de p95 ≤ 0,1° entre frames ([tanda_r6b/temblor_camara.json](tanda_r6b/temblor_camara.json): incremento de rotación entre frames, paso alto por FFT a 2 Hz).

| τ (s) | Temblor > 2 Hz, p95 (°) | sin giro / en giros | Arma en pantalla, `sin_giro` p95 (válidas/capturas) | Retraso en giros, p50 |
|---|---|---|---|---|
| 0 | 0,972 | 0,703 / 1,212 | 5,54 px (116/117) | 0,00° |
| 0,1 | 0,388 | 0,303 / 0,553 | 82,0 px (35/119; 84 no rígidas) | 1,41° / 62 ms |
| 0,2 | 0,519 | 0,214 / 0,775 | 115,5 px (34/118) | 3,35° / 115 ms |
| 0,3 | 0,259 | 0,112 / 0,453 | 118,9 px (29/118) | 5,80° / 157 ms |
| 0,5 | 0,163 | 0,079 / 0,247 | 142,0 px (44/113) | 10,3° / 265 ms |
| 1,0 | **0,089** ✔ | 0,039 / 0,148 | INCONCLUSO (7/115) | 19,2° / 488 ms |

Por este criterio sale **τ = 1,0 s**, el único que lo cumple, a costa de casi medio segundo de retraso en los giros. La cifra de 0,2 no es monótona con las demás, y el umbral de 0,1° y la elección entre 1,0 y el 0,3 propuesto quedan para la decisión del coordinador o de Guillermo.

**T-lect de Hb con giros lentos y alternos** (lectura a; [tanda_r6b/tlect_*.json](tanda_r6b/)). Va tal cual, sin tocar parámetros:

| Corrida | giro1 | giro2 | giro3 |
|---|---|---|---|
| lookat_Hb_lento | INCONCLUSO, 1,48 px (cobertura 0,50) | **PASA**, 1,10 px (1,0) | **PASA**, 1,10 px (1,0) |
| follow_Hb_lento | FALLA, 2,12 px (1,0) | FALLA, 2,18 px (0,98) | FALLA, 2,14 px (1,0) |

**Mod r6c.** `C:\tmp\dsbx-strack2\bench\@DZS_STrack_r6c\Addons\DZS_STrack.pbo`, de 74 331 B, sha256 `90bdccd6af058fa2397ba12d1e8f60d143d84b6bd56d23fd4b1efc22fb8d897d`. AddonBuilder con `-packonly` (exit 0). El linter offline `script_validator.py` da PASS, con `errors: []` en 6 ficheros. El texto del nlerp está en el PBO; no se ha probado en partida.

**Pruebas r6c** ([tanda_r6b/suite_r6c.txt](tanda_r6b/suite_r6c.txt)). Se corrieron de uno en uno los módulos que cargan el evaluador o los fixtures parcheados, y los que no llegaron a correr antes del disco lleno:

| Módulo | Tests | Resultado |
|---|---|---|
| suave_relativo | 2 | OK |
| s_track2 | 54 | OK |
| s_track_eval | 6 | OK |
| timeline_r5 | 5 | OK |
| detector_windows | 4 | OK |
| sesgo | 20 | OK |
| thook_mount | 12 | OK |
| tlect_direct | 7 | OK |
| `test_stdlib_only` | 3 | OK |

`test_check_runs` no se repitió, porque no carga código parcheado: vale su 29/29 del 27-nov a las 05:26. Los mutantes se relanzan aparte, con tope de 2 h.

---

## Anexo — desviaciones, cambios de trabajador y arbitrajes

Registro completo: `C:\tmp\dsbx-strack2\vueltas.md`.

### A.1 El foco no explicaba los 19 fps de S-track·1
Prueba de foco (`bench\diag\diag_foco_0302`, `diag_fps.ps1` y `diag_analiza.py`) con el cliente siempre sin el foco (0 %):

| Fase | n | dt p50 | dt p95 |
|---|---|---|---|
| A (foco pedido al cliente) | 1679 | 17 ms | 29 ms |
| B (foco en el servidor) | 1671 | 17 ms | 30 ms |
| C (foco pedido al cliente) | 1076 | 17 ms | 31 ms |

El cliente sin primer plano corre a 60 fps. Los 19 fps de S-track·1 no venían del foco. El banco sigue forzando el primer plano (`run_case2.ps1`), pero eso no explica la diferencia.

### A.2 Disco lleno durante la noche
El disco C: se llenó (por M1) durante la tanda. Se paró con `PARAR` y la evidencia se movió a E: con SHA-256 por fichero (`mover_a_e.py`, `SHA256SUMS` por corrida, `SHA256SUMS.index`). En C: solo queda `MOVIDO_A_E.txt` en cada carpeta. `run_case2.ps1` llegó a intentar rehacer mount0_Hc_delay1 (el renombrado falló sin daño); desde entonces salta las carpetas con `MOVIDO_A_E.txt`. La diferencia de mutantes 87/93 del 14-nov también era el disco lleno (`OSError [Errno 28]` en las fixtures), no el código. Las suites corren ahora con TEMP en E:.

### A.3 Cambios de trabajador
- **Muse** (implementador de mutantes, evaluador y mod, vueltas 1–4 del 12/13-nov; sesgo v1): cuota agotada hasta el 30-nov.
- **Sol** (Codex, revisor): cuota al 100 % hasta el 27-nov 10:07. Lo sustituyó **Argon** (agy gemini-4-argon-high, modo plan) en las vueltas 2–4 del sesgo. Desde el 26-nov 13:15Z se quita la revisión bloqueante de Sol (regla de Guillermo: «si se puede probar no se revisa»); lo que no se puede probar lo revisa Gemini Neon, una vuelta, al terminar.
- **Marcadores a ciegas A y B**: dos subagentes Opus. El A no es el orquestador, por contexto.
- **Carbon** (agy gemini-4-carbon-high): implementador en S-track·3.

### A.4 Arbitrajes (orquestador o coordinador)
1. **Mutantes** (orquestador, tras 4 vueltas): el runner solo cuenta una muerte si falla el cuerpo del test; setUp, tearDown y addCleanup dan ERROR, y un mutante en ERROR sale con exit 2.
2. **Evaluador** (orquestador, tras 4 vueltas): los 4 BLOQ de Sol v4 pasan a comprobación mecánica de las corridas (`check_runs.py`) y no se cambia el código.
3. **Sesgo §17/§18** (coordinador, tras 4 vueltas): vuelta a la v3 para T-lect/T-hook, con la parte A de la v4. T-sesgo queda informativo; «cerrar el sesgo» pasa a «observado e informado».
4. **check_runs** (orquestador, tras la tanda real, exit 1): (a) intervalos con dt exactamente en el tope del motor (0,3 s, tirones de BMP) exentos de deriva; (b) solo cuenta la deriva que persiste dos frames (el sello de Hb da ±61 ms en un par); (c) calib exenta de la deriva acumulada pero obligada a |Σdt/Σt − 1| ≤ 5 %. Tests positivo y negativo por regla. Resultado: 24/24 válidas.
5. **Marcas** (coordinador): rasgos visibles del p3d en lugar de `usti`/`konec` (distancia p3d 0,407969 m frente a 0,407952 m en partida). Rasgos: centro del anillo exterior del apagallamas (0,22 mm fuera del eje) y punto de mira (media de las dos orejas).
6. **Máscara** (coordinador, 14:17Z): registro solo para la forma; la deriva se mide en las capturas sin registrar. Se probó una normalización fotométrica con máscara compartida y se **deshizo** (copia en `lanes\sesgo\s_track_eval.py.before_mask_photometric`).
7. **T-hook de mount por medida directa** (coordinador, 14:21Z): ver A.7.

### A.8 Cambio de método para T-lect de lookat/follow
Árbitro: el coordinador (15:39Z). La normalización en dos pasadas no sirve (§5) y se sustituye por la medida directa de §4b, con las condiciones del coordinador. Lo añadí yo al aplicarla:
1. **Afinado del ángulo en ±4°:** con 3° de error, la franja deja de casar al final del cañón y un anillo desplazado un periodo puntuaba igual (saltos de 8 px en la escena sintética). La ventana gira alrededor de la proyección y la posición se sigue buscando sin preferencia.
2. **Banco de plantillas por vista 3D** (≤ 10°, de otro giro, cada una recortada en la proyección de su captura): con una sola plantilla, en lookat_Hb las capturas con otra vista daban NCC 0,45–0,6 y detecciones espurias de hasta 60 px. Con el banco, giro1/3 dan cobertura del 99 %. Límite: giro2 recorre vistas que los otros giros no repiten (> 20°), así que tiene cobertura del 52 %.
3. **Rechazo de detecciones ambiguas** (margen < 0,03 frente al segundo máximo local; en las sintéticas el peor caso bueno da 0,044 y dos cañones idénticos 0,021).
4. **Error mío corregido:** convención de centro de píxel de PIL (+0,5). Sin esto, la medida tenía un sesgo de hasta 1,2 px que crecía con la rotación.
5. **Sensibilidad probada y declarada:** fondo delante de la punta en la máscara (1,2 / 3 / 5 cm) y calidad mínima (0,5 / 0,4 / 0,35). La configuración que se informa (1,2 cm, 0,5) está fijada antes del barrido. Bajar la calidad mete colas espurias en lookat_Hb.

### A.5 Errores de diagnóstico corregidos
- «En mount0_Hb el arma está quieta en la imagen (0/±1 px)» (diagnóstico de máscara, 26-nov): **falso**. El cultivo contenía el punto blanco fijo de la HUD en el centro exacto (960,540), y la correlación de fase se enganchaba a él. Con cultivos que lo evitan, el arma se mueve 2–6 px en Hb (§4).

### A.6 Marcas a mano
Dos marcadores a ciegas. En mount0 y mount03, 25 de 26 capturas quedan ≤ 1,5 px entre marcadores. f000304 de mount03_Hb dio 2,15 px y se sustituyó por f000310 (0,61 px). En lookat y follow no hay nada marcable (vista lateral). En ropa salen 15–18 px y caen en el rasgo del silenciador, así que se descartaron.

### A.7 Cambio de método para T-hook de `mount`
Árbitro: el coordinador (14:21Z). La máscara temporal se sustituye por una medida directa de desplazamiento de dos cultivos fijos sobre el arma. lookat/follow siguen con máscara (próxima vuelta) y T-lect sigue INCONCLUSO por máscara. Al aplicarla a los datos reales hubo que hacer tres ajustes, y los decidí yo:
1. **Punto de la HUD:** `konec` se proyecta en el centro exacto, donde hay un punto blanco fijo. El primer cultivo se aleja a lo largo del eje hasta no contenerlo (`HUD_PUNTO`, `HUD_MARGEN_PX`). Test: `test_cultivos_evitan_el_punto_de_la_hud`.
2. **Segundo cultivo hacia el receptor y no hacia la boca:** hacia la boca el cañón es fino y el cultivo es casi todo suelo, que se mueve al girar (calidad de correlación 0,10–0,28). Por eso es «recámara + receptor» y no «recámara + guardamanos». Siguen separados 200 px.
3. **Búsqueda antes de la fase:** en Ha el arma se desplaza unos +80/+53 px y sale un 20 % más grande, así que una correlación de fase en sitio fijo no la encuentra (todo `correlacion_debil`). Ahora una NCC por FFT busca en ±120 px y en escalas 0,8–1,3. La correlación de fase afina el subpíxel en el sitio encontrado cuando gana la escala 1. La calidad es el pico de NCC, con un mínimo de 0,5. Tests: `test_deriva_grande_20px_falla_y_se_mide` y `test_arma_mas_cerca_y_desplazada_falla_y_se_mide`.

4. **Rigidez entre los dos cultivos** (pedida por el coordinador, 15:24Z): los dos cultivos deben elegir la misma escala, y la longitud del segmento desplazado debe casar con ella (tolerancia de un paso, 0,05). Si no, la lectura se descarta como «no rígida» y, si no quedan 20 válidas, la ventana sale INCONCLUSO `cultivos_no_rigidos`. Quita el emparejamiento espurio de Hb giro3 (68,6 → 5,10 px). Tests: `test_emparejamiento_espurio_no_rigido_se_descarta` y `test_rigido_con_escala`. Límite: con dos puntos no se distingue una rotación grande del arma en la imagen de un emparejamiento espurio, así que Ha y Hc quedan INCONCLUSO aunque a ojo se muevan decenas de píxeles.
5. **Ventana `sin_giro`** (tanda r6): las capturas sin giro tras la referencia, para medir el temblor separado del retraso del filtro en los giros.

Mod r6 (26-nov, para la tanda corta): argumentos nuevos `-strack_noshots`, `-strack_smooth_s`, `-strack_smooth_pos` y `-strack_tag`. Sin ellos se comporta igual que r5. Copia previa en `C:\tmp\dsbx-strack2\lanes\STRACK_Session.c.before_r6`. Linter PASS 0/0 y PBO empaquetado (`bench\pack_r6.ps1`). **No se ha probado en partida.**

Lo que no cambia: normalización por cultivo, p95 de la deriva, roll como ángulo entre desplazamientos, umbrales de 2 px y 0,5°, y los tres tests pedidos (5 px → FALLA, 1° → FALLA, brillo 63→119 → PASA).
