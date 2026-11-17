# Informe mutantes — S-track·2 (sesión «mutantes», Muse)

## Cambios

- [run_mutants.py](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:110): tres mutantes nuevos mínimos (brief §5.1, contrato §13), por sustitución de la línea exacta, conservando los de S-track·1:
  - `plantilla_en_proyeccion` en [run_mutants.py:112](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:112): `TEMPLATE_SOURCE = "marca"` → `TEMPLATE_SOURCE = "proyeccion"`;
  - `mascara_ignorada` en [run_mutants.py:118](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:118): `USE_MASK = True` → `USE_MASK = False`;
  - `umbral_suave_5pc` en [run_mutants.py:126](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:126): `THRESH_SUAVE_FRAC = 0.02` → `THRESH_SUAVE_FRAC = 0.05`.
  - Línea no encontrada exactamente una vez → `ERROR`, nunca superviviente: sin cambios en `apply_mutant`, cubierto para los tres nuevos en [test_run_mutants.py:226](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:226).
- [run_mutants.py:162](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:162): `parse_killing_tests()` extrae de la salida de `unittest` los tests que fallan; la suite se corre con `-v`. Cada resultado lleva `killed_by` ([run_mutants.py:214](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:214), [run_mutants.py:234](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:234)), la tabla gana la columna «tests que lo matan» ([run_mutants.py:325](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:325)) y tras la tabla se imprime `MUERTO por …` por mutante ([run_mutants.py:383](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:383)), así se ve que cada mutante muere al menos en un test.
- [check_negatives.py:46](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:46): `SCHEMA2_NEGATIVE_RUNS` con las nueve de contrato §14, en orden. [check_negatives.py:99](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:99) `expected_requirements_schema2()`; [check_negatives.py:208](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:208): en schema 2, cualquier `got != "FALLA"` (PASA, INCONCLUSO u otro) o una negativa ausente → exit 1; `main` imprime `MOTIVO: …` por corrida ([check_negatives.py:270](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:270)).
- Decisión schema 1 (se dice, como pide el encargo): **se sigue aceptando** schema 1 con su lógica histórica (ausente → exit 2, veredicto ≠ FALLA → exit 1), para no romper la evidencia de S-track·1. Schema distinto de 1/2 → exit 2 con mensaje claro.
- Tests: [test_run_mutants.py:36](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:36) el evaluador de juguete lleva las tres constantes nuevas y la suite de juguete las comprueba (`test_template_source`, `test_use_mask`, `test_thresh_suave_frac`); [test_run_mutants.py:212](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:212) cada mutante nuevo muere con su test en `killed_by`; el conjunto de mínimos pasa a seis. [test_check_negatives.py:114](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:114) `TestCheckInformeSchema2` y [test_check_negatives.py:151](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:151) `TestCheckNegativesMainSchema2`: todas FALLA → 0, una PASA → 1, una INCONCLUSO → 1, una ausente → 1 (también vía `main`).

## Gate (literal)

```
cd C:\tmp\dsbx-strack2\mut\DayZSandbox_dev
C:\Python314\python.exe -m unittest discover -s qa/strack/mutants/tests -t . -v
C:\Python314\python.exe qa/strack/mutants/run_mutants.py --strack-dir qa/strack
```

Primer comando: **OK** — `Ran 30 tests in 3.951s / OK` (antes: 18).

Segundo comando: no llega a la tabla de mutantes en esta copia (ver DISPUTAS). Salida literal, recortada:

```
BASELINE: ERROR - baseline rojo: la suite no pasa sin mutar; los mutantes no se evaluan
...
ModuleNotFoundError: No module named 'numpy'
...
RESULTADO: ERROR (baseline o entorno)
EXIT:2
```

Informe generado por esa corrida: `qa/strack/mutants/mutants_report.json` (baseline `ok: false`, `mutants: []`).

Tabla esperada según el brief frente a lo observado aquí:

| Mutante | Esperado (brief) | Observado aquí |
|---|---|---|
| De S-track·1 (3 mínimos + 3 extra) | como en S-track·1 | no evaluados: baseline rojo por entorno |
| `plantilla_en_proyeccion` | ERROR (línea no encontrada) | no evaluado por el runner; la línea cuenta 0 en el evaluador (ver abajo) |
| `mascara_ignorada` | ERROR | idem |
| `umbral_suave_5pc` | ERROR | idem |

Sonda independiente sobre el evaluador real de esta copia (`s_track_eval.py`, solo conteo, sin tocarlo): `TEMPLATE_SOURCE` 0, `USE_MASK` 0, `THRESH_SUAVE_FRAC` 0; `THRESH_PX = 2.0` 1, `COVERAGE_MIN = 0.95` 1. Es decir, con un baseline verde los tres nuevos caerían en `ERROR` por `apply_mutant`, que es justo lo que el brief prevé y lo que los tests de juguete demuestran.

## DISPUTAS

- El gate espera que el segundo comando pinte la tabla con los tres nuevos en ERROR, pero en esta máquina `C:\Python314\python.exe` no tiene `numpy`/`Pillow` (`qa/strack/requirements.txt`: `numpy>=1.26`, `Pillow>=10.0`) y el encargo prohíbe instalar paquetes. El runner, por diseño previo, no evalúa mutantes con el baseline rojo, así que la tabla no se produce aquí. No es un fallo de los mutantes: es el entorno. En el PC del orquestador, con las dependencias del evaluador, el mismo comando debe dar la tabla esperada.

## LO QUE NO PUDE VERIFICAR

- Los tres mutantes nuevos contra el evaluador real de S-track·2: esa copia no está en este workspace (aquí solo está el evaluador de S-track·1, sin `TEMPLATE_SOURCE`/`USE_MASK`/`THRESH_SUAVE_FRAC`). Su muerte real la comprobará el orquestador al juntar las copias; aquí solo está probada contra el evaluador/suite de juguete y la no-aplicabilidad (ERROR) contra el evaluador de S-track·1 por conteo de líneas.
- `check_negatives.py` contra un `informe.json` schema 2 real: no hay ninguno en esta copia; está probado solo con informes sintéticos en los tests.
- Nada de DayZ, PBO ni corridas en partida (fuera del encargo).

## Vuelta 2

Arreglados los cuatro BLOQ del revisor (Sol). Cada uno lleva su test que fallaba antes y pasa después: antes de los arreglos la suite ampliada daba `Ran 46 tests ... FAILED (failures=12, errors=3)`; después, `Ran 46 tests ... OK` (ver gate abajo).

### Cambios por BLOQ

1. **MUERTO sin test que falle** — [run_mutants.py](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:234) `run_one_mutant(..., baseline_killed_by=())`: `MUERTO` solo si `Ran N` con N≥1 ([run_mutants.py:206](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:206) `parse_tests_run`), hay ≥1 test individual fallido/con error identificado por su nombre (`setUpClass`/`setUpModule`/`tearDown*`/`_FailedTest` ya no cuentan como tests) y ese nombre no está en `baseline_killed_by` (que [run_mutants.py:366](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:366) `run_all` extrae del baseline). Código ≠0 sin resultados, `Ran 0` o solo fallo en `setUpClass` → `ERROR` con `killed_by=[]`. Tests: [test_run_mutants.py:390](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:390) `test_setupclass_failure_is_error_not_muerto`, [test_run_mutants.py:403](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:403) `test_exit2_without_unittest_results_is_error`, [test_run_mutants.py:415](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:415) `test_zero_tests_run_is_error`, [test_run_mutants.py:431](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:431) `test_failure_already_in_baseline_is_not_muerto` y [test_run_mutants.py:447](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:447) `test_named_failure_not_in_baseline_is_muerto`.
2. **Sustitución por subcadena** — [run_mutants.py:148](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:148) `apply_mutant` (apoyo [run_mutants.py:139](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:139) `_line_core`): solo cuenta una línea completa (tras quitar el fin de línea, igual a la del contrato) en asignación activa a nivel de módulo (columna 0, no comentario; la igualdad exacta lo exige); se sustituye solo esa línea conservando su fin de línea. 0 o ≥2 apariciones → `MutationError` → `ERROR`. Ya no se toca un comentario (`USE_MASK = bool(1)` + `# USE_MASK = True` → 0 apariciones) ni un prefijo numérico (`THRESH_SUAVE_FRAC = 0.025` ≠ `... = 0.02`, no se convierte en `0.055`) ni una línea indentada. Tests: [test_run_mutants.py:255](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:255) `test_comment_substring_is_not_a_match`, [test_run_mutants.py:262](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:262) `test_prefix_number_is_not_a_match`, [test_run_mutants.py:271](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:271) `test_indented_line_is_not_a_match`, [test_run_mutants.py:278](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:278) `test_comment_plus_active_line_replaces_only_active`.
3. **check_negatives con metadatos contradictorios** — [check_negatives.py:161](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:161) `_check_schema2`: en schema 2 las nueve se identifican por el nombre completo de `run` (contrato §14), sin que los campos explícitos reubiquen la entrada; `inject` que no casa con el sufijo de `run` → fila `INJECT_NO_CASA`, corrida duplicada → `DUPLICADA`, ambas exit 1 y `main` imprime `MOTIVO: …` ([check_negatives.py:355](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:355)). El caso del revisor (8 buenas + `run="suave60_Hb_quatlerp"`, `inject="longarc"`, `got="FALLA"`) ya no sale 0: `suave60_Hb_quatlerp` queda `DUPLICADA` y `suave60_Hb_longarc`, `FALTA`. Schema 1 conserva su lógica histórica. Tests: [test_check_negatives.py:152](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:152) `test_inject_no_casa_con_run_mas_duplicada_exit_uno`, [test_check_negatives.py:169](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:169) `test_inject_no_casa_sufijo_exit_uno_con_motivo`, [test_check_negatives.py:179](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:179) `test_corrida_duplicada_exit_uno`, [test_check_negatives.py:212](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:212) `test_main_schema2_inject_contradictorio_exit_uno`, [test_check_negatives.py:220](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:220) `test_main_schema2_duplicada_exit_uno`.
4. **Los mutantes extra también tienen que morir** — [run_mutants.py:376](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:376): `report["ok"]` y el exit 0 exigen `MUERTO` en **todos** los mutantes de la lista (mínimos y extras, incluidos `calib_match_cero`, `stimulus_cero`, `detector_laxo`); `minimal`/`kind` quedan solo como información en tabla e informe, y el resumen pasa a «todos los mutantes mueren» / «algun mutante no muere». La suite de juguete ahora también comprueba las tres constantes extra, para que el camino feliz siga dando 0. Tests: [test_run_mutants.py:465](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:465) `test_run_all_all_mutants_die_exit_zero`, [test_run_mutants.py:477](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:477) `test_extra_survivor_blocks_exit_zero` (mínimos muertos + extra vivo → exit 1; antes daba 0).

### Gate vuelta 2 (literal)

```
cd C:\tmp\dsbx-strack2\mut\DayZSandbox_dev
C:\Python314\python.exe -m unittest discover -s qa/strack/mutants/tests -t . -v
C:\Python314\python.exe qa/strack/mutants/run_mutants.py --strack-dir qa/strack
```

Primer comando: **OK** — `Ran 46 tests in 6.042s / OK` (vuelta 1: 30; +16 de los cuatro BLOQ).

Segundo comando en esta copia: como en la vuelta 1, el sandbox no ve `numpy`/`Pillow` y el baseline queda rojo, sin tabla. Salida literal, recortada:

```
BASELINE: ERROR - baseline rojo: la suite no pasa sin mutar; los mutantes no se evaluan
...
ModuleNotFoundError: No module named 'numpy'
...
RESULTADO: ERROR (baseline o entorno)
EXIT:2
```

Sobre la salida del orquestador de la vuelta 1 (en su lado, con dependencias): los seis de S-track·1 más `calib_match_cero`, `stimulus_cero` y `detector_laxo` salían `MUERTO`, y los tres nuevos `ERROR` por línea exacta ausente (0 apariciones). Con la vuelta 2 eso no cambia de signo: los tres nuevos siguen en `ERROR` (nunca supervivientes) hasta que el evaluador junto traiga las líneas exactas de contrato §13, y por el BLOQ 4 cualquier `ERROR`/`SOBREVIVE` —también de un extra— da exit 1.

### DISPUTAS vuelta 2

- Sin cambios respecto a la vuelta 1: el segundo comando del gate no puede producir la tabla en este sandbox (sin `numpy`/`Pillow`, prohibido instalar). Lo corre el orquestador en su lado, como ya hizo en la vuelta 1.

### LO QUE NO PUDE VERIFICAR (vuelta 2)

- El runner contra el evaluador real juntado de S-track·2 (con `numpy`/`Pillow`): no está en este workspace. Aquí el gate verificado es la suite de `qa/strack/mutants/tests` (solo stdlib), 46 tests en verde, con los tests nuevos fallando antes del arreglo (`FAILED (failures=12, errors=3)`) y pasando después.
- Nada de DayZ, PBO ni corridas en partida (fuera del encargo).

## Vuelta 3

Arreglados los tres BLOQ y el MAY de Sol. Antes de los arreglos, la suite ampliada daba `Ran 56 tests ... FAILED (failures=12, errors=6)`; después, `Ran 56 tests ... OK`.

### Cambios por punto

1. **BLOQ — MUERTO por un nombre que no es un test** — [run_mutants.py](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:277) `_RUNNER_SCRIPT`: un script propio usa `unittest.TestLoader.discover` + `unittest.TestResult` y escribe en JSON `testsRun`, `failures` y `errors` con el `id()` de cada test y su `kind` (`test` solo para un método de test individual; `setup_class`/`setup_module`/`import`/`other` para `setUpClass`/`setUpModule`/importación, con `is_setup_error`). [run_mutants.py:412](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:412) `run_suite` ahora devuelve `(returncode, salida, structured)` y ya no se parsea el texto libre del log (fuera `parse_killing_tests`/`parse_tests_run`). [run_mutants.py:460](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:460) `run_one_mutant`: `MUERTO` solo si `testsRun ≥ 1` (vía [run_mutants.py:402](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:402) `_structured_tests_run`), hay ≥ 1 fallo/error de un test individual ([run_mutants.py:360](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:360) `_individual_ids`) que no esté en el baseline, y no hay errores de setup/importación; `testsRun=None`, `testsRun=0` o un error de `setUpClass`/`setUpModule`/importación → `ERROR` con `killed_by=[]`. `killed_by` lleva ahora los `id()` completos (p. ej. `tests.test_toy.TestToyEval.test_thresh_px`). Los tracebacks se imprimen a stderr solo como diagnóstico humano. Tests: [test_run_mutants.py:520](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:520) `test_fixture_missing_setupclass_is_error_not_muerto` (clase que imprime `ERROR: fixture_missing` y lanza en `setUpClass`, con otro test que pasa → `ERROR`, sin `fixture_missing` en `killed_by`), [test_run_mutants.py:535](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:535) `test_tests_run_none_is_rejected_as_error`, [test_run_mutants.py:555](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:555) `test_setup_error_with_passing_test_is_error`, [test_run_mutants.py:271](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:271) `test_no_free_text_killing_parser`.
2. **BLOQ — La sustitución acepta texto que no es una asignación activa** — [run_mutants.py:185](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:185) `apply_mutant` usa `ast` (apoyo [run_mutants.py:174](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:174) `_module_assigns`): la línea a sustituir debe ser exactamente el `lineno` de un `ast.Assign` de nivel de módulo con un solo destino `Name` igual a la constante, y esa línea debe ser exactamente la del contrato; 0 o ≥ 2 asignaciones a la constante → `MutationError` → `ERROR`. Tras sustituir, vuelve a parsear y comprueba con `ast.literal_eval` que el valor literal de esa asignación es el nuevo (con el mismo tipo). Una `USE_MASK = True` dentro de una cadena multilínea con la asignación real `USE_MASK = bool(1)` ya no se sustituye: hay una sola asignación a `USE_MASK`, pero su línea es `USE_MASK = bool(1)`, no la exacta → `ERROR`. Tests: [test_run_mutants.py:313](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:313) `test_multiline_string_plus_bool_assign_is_not_a_match`, [test_run_mutants.py:321](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:321) `test_second_assign_to_same_constant_is_error`, [test_run_mutants.py:326](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:326) `test_multiline_string_occurrence_alone_is_error`.
3. **BLOQ — `inject` ausente, `null` o `""` pasa** — [check_negatives.py:206](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:206) `_check_schema2`: en schema 2 el campo `inject` debe existir (`"inject" in entry`) y ser exactamente el sufijo de `run`; ausente, `null`, `""` o cualquier otro valor → fila `INJECT_NO_CASA`, exit 1 y `MOTIVO: …` vía `main`. Tests: [test_check_negatives.py:190](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:190) `test_inject_ausente_null_o_vacio_exit_uno` (tres subtests), [test_check_negatives.py:248](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:248) `test_main_schema2_inject_ausente_exit_uno`, [test_check_negatives.py:256](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:256) `test_main_schema2_inject_vacio_exit_uno`.
4. **MAY — Fallo al guardar `mutants_report.json` con exit 0** — [run_mutants.py:691](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:691) `main`: si la escritura del informe falla (`OSError` en `mkdir`/`write_text`), se marca `write_failed` y al final ([run_mutants.py:721](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:721)) imprime `RESULTADO: ERROR (no se pudo escribir el informe)` y devuelve 2 si el código era 0 (o conserva un código ya ≠ 0); nunca imprime `RESULTADO: OK` sin informe. Test: [test_run_mutants.py:607](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:607) `test_report_write_failure_is_not_exit_zero` (`run_all` simulado en verde + `Path.write_text` que lanza `OSError` → exit ≠ 0 y sin `RESULTADO: OK`).

### Gate vuelta 3 (literal)

```
cd C:\tmp\dsbx-strack2\mut\DayZSandbox_dev
C:\Python314\python.exe -m unittest discover -s qa/strack/mutants/tests -t . -v
C:\Python314\python.exe qa/strack/mutants/run_mutants.py --strack-dir qa/strack
```

Primer comando: **OK** — `Ran 56 tests in 6.234s / OK` (vuelta 2: 46; +10 de la vuelta 3, contando los subtests de `inject` dentro de su test). Antes de los arreglos: `Ran 56 tests ... FAILED (failures=12, errors=6)`.

Segundo comando en esta copia: como en las vueltas 1 y 2, el sandbox no ve `numpy`/`Pillow` y el baseline queda rojo, sin tabla. Salida literal, recortada:

```
BASELINE: ERROR - baseline rojo: la suite no pasa sin mutar; los mutantes no se evaluan
...
ModuleNotFoundError: No module named 'numpy'
...
RESULTADO: ERROR (baseline o entorno)
EXIT:2
```

El informe de esa corrida (`qa/strack/mutants/mutants_report.json`) trae ahora `baseline.tests_run: 1` (el runner estructurado contó el test que sí cargó; el resto son `_FailedTest`/`setUpClass` por `numpy`).

### DISPUTAS vuelta 3

- Sin cambios respecto a las vueltas 1 y 2: el segundo comando del gate no puede producir la tabla en este sandbox (sin `numpy`/`Pillow`, prohibido instalar). Lo corre el orquestador en su lado.
- `killed_by` cambia de formato: nombres cortos (`test_thresh_px`) → `id()` completos (`tests.test_toy.TestToyEval.test_thresh_px`), como pide el punto 1 de Sol al exigir el fallo «de un test individual (`id()` de un método de test)». Los tests de juguete se actualizaron a ese formato.

### LO QUE NO PUDE VERIFICAR (vuelta 3)

- El runner estructurado contra el evaluador real juntado de S-track·2 (con `numpy`/`Pillow`): no está en este workspace. Aquí el gate verificado es la suite de `qa/strack/mutants/tests` (solo stdlib), 56 tests en verde, con los tests nuevos fallando antes del arreglo (`FAILED (failures=12, errors=6)`) y pasando después; el segundo comando se verificó hasta el baseline rojo por entorno (exit 2, con el `ModuleNotFoundError: numpy` ahora visible vía el stderr de diagnóstico del runner).
- Nada de DayZ, PBO ni corridas en partida (fuera del encargo).

## Vuelta 4

Arreglados los dos BLOQ. Antes de los arreglos, los tests nuevos daban `FAILED` (los 6 invocados: `test_setup_instance_failure_is_error_not_muerto` y `test_teardown_failure_is_error_not_muerto` salían `MUERTO`, `test_control_sin_mutar_recurso_ausente_todos_error` salía exit 0 con todos `MUERTO`, y los tres de `expected` salían exit 0); después, `Ran 62 tests ... OK`.

### Cambios por BLOQ

1. **BLOQ — error en `setUp()` contado como `kind="test"`** — dos arreglos:
   - (a) **Control sin mutar**: [run_mutants.py](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:503) `_run_control()` copia el evaluador SIN mutar en un directorio temporal aislado con solo `s_track_eval.py` (la misma disposición que usa `run_one_mutant` para cada mutante) y corre la suite. [run_mutants.py:687](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:687) `run_all`, tras un baseline verde, corre el control y exige verde exactamente igual que el baseline (`returncode == 0`, mismo `testsRun`, sin fallos individuales ni de preparación); si no, [run_mutants.py:710](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:710) todos los mutantes quedan en `ERROR` (vía `_error_result`, `killed_by=[]`), el informe trae `control.ok: false` y el runner sale con 2 (≠ 0). `main` imprime `CONTROL: OK`/`CONTROL: ERROR - …`.
   - (b) **Distinción `setUp`/`tearDown`**: el runner propio ([run_mutants.py:290](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:290) `_kind`, [run_mutants.py:315](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:315) `_entries`) mira el traceback de cada fallo/error: si pasa por `, in setUp` o `, in tearDown` (instancia, clase o módulo) la entrada queda `kind="setup"`/`"teardown"` con `is_setup_error: true` y el traceback en el JSON, nunca `kind="test"`. En el lado del runner, [run_mutants.py:374](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:374) `_is_setup_entry` reaplica ese criterio (también sobre un `traceback` presente en una entrada marcada `test`), así `_individual_ids` no lo cuenta como muerte y `_setup_error_ids` lo lleva a `ERROR`. Tests: [test_run_mutants.py:758](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:758) `test_setup_instance_failure_is_error_not_muerto`, [test_run_mutants.py:771](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:771) `test_teardown_failure_is_error_not_muerto` (solo `tearDown` falla → `ERROR`) y [test_run_mutants.py:785](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_run_mutants.py:785) `test_control_sin_mutar_recurso_ausente_todos_error` (recurso junto al evaluador original, ausente junto a la copia: baseline verde, control rojo, todos `ERROR`, exit ≠ 0).
2. **BLOQ — `expected` ausente, `null` o distinto de `"FALLA"`** — [check_negatives.py:211](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:211) `_check_schema2`: en schema 2 cada una de las nueve debe traer `expected == "FALLA"` (`"expected" in entry` y valor exacto); si no, fila `EXPECTED_NO_CASA`, exit 1 y `main` imprime `MOTIVO: <run> tiene expected=… y se esperaba 'FALLA'` por corrida ([check_negatives.py:378](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:378)). Tests: [test_check_negatives.py:211](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:211) `test_expected_ausente_null_o_distinto_exit_uno` (tres subtests), [test_check_negatives.py:277](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:277) `test_main_schema2_expected_ausente_exit_uno` y [test_check_negatives.py:285](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/tests/test_check_negatives.py:285) `test_main_schema2_expected_distinto_exit_uno`.

### Gate vuelta 4 (literal)

```
cd C:\tmp\dsbx-strack2\mut\DayZSandbox_dev
C:\Python314\python.exe -m unittest discover -s qa/strack/mutants/tests -t . -v
C:\Python314\python.exe qa/strack/mutants/run_mutants.py --strack-dir qa/strack
```

Primer comando: **OK** — `Ran 62 tests in 6.044s / OK` (vuelta 3: 56; +6 de la vuelta 4, contando los subtests de `expected` dentro de su test).

Segundo comando en esta copia: como en las vueltas 1–3, el sandbox no ve `numpy`/`Pillow` y el baseline queda rojo, sin tabla (el control ni siquiera se alcanza: con el baseline rojo el runner ya sale 2). Salida literal, recortada:

```
BASELINE: ERROR - baseline rojo: la suite no pasa sin mutar; los mutantes no se evaluan
...
ModuleNotFoundError: No module named 'numpy'
...
RESULTADO: ERROR (baseline o entorno)
EXIT:2
```

### DISPUTAS vuelta 4

- Sin cambios respecto a las vueltas 1–3: el segundo comando del gate no puede producir la tabla en este sandbox (sin `numpy`/`Pillow`, prohibido instalar). Lo corre el orquestador en su lado. En su lado, con el baseline verde, el nuevo control sin mutar corre con la disposición aislada de los mutantes: si el evaluador real no depende de ficheros hermanos, el control sale verde y la tabla es la de antes; si dependiera de alguno, todos los mutantes saldrían `ERROR` y el runner ≠ 0, que es justo el comportamiento pedido.

### LO QUE NO PUDE VERIFICAR (vuelta 4)

- El control sin mutar y la distinción `setUp`/`tearDown` contra el evaluador real juntado de S-track·2 (con `numpy`/`Pillow`): no está en este workspace. Aquí están probados contra el evaluador/suite de juguete (recurso hermano, `setUp` y `tearDown` de instancia), 62 tests en verde, con los tests nuevos fallando antes del arreglo y pasando después.
- Nada de DayZ, PBO ni corridas en partida (fuera del encargo).
