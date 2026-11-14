- **BLOQ — Se puede declarar `MUERTO` sin ningún test individual fallido.** [run_mutants.py:176](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:176). Una clase imprime `ERROR: fixture_missing` en `setUpClass` y lanza una excepción; otro test pasa → el runner declara `MUERTO`, con `killed_by=["fixture_missing"]`. Reproducido con salida real de unittest: ese supuesto test no existe. Además, en la línea 282 tampoco se rechaza `tests_run=None`.
  **Arreglo:** obtener fallos identificados desde resultados de unittest separados del log y exigir un resumen válido con N≥1.

- **BLOQ — La sustitución todavía acepta líneas que no son asignaciones activas.** [run_mutants.py:162](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:162). Fuente con `USE_MASK = True` únicamente dentro de una cadena multilínea y asignación real `USE_MASK = bool(1)` → cambia la cadena, conserva el valor efectivo `True` y, con suite verde, declara `SOBREVIVE`. Sigue incumpliéndose «mutante no aplicado → ERROR».
  **Arreglo:** comprobar que la coincidencia pertenece a una asignación directa del módulo antes de sustituirla; excluir cadenas y otros contextos sintácticos.

- **BLOQ — Una inyección vacía evade la comprobación de coherencia.** [check_negatives.py:207](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:207). Nueve negativas con `got="FALLA"`, pero `suave60_Hb_longarc` lleva `inject=null`, `""` o carece del campo → exit 0 y fila `OK`. Se acepta una entrada que incumple el contrato y se muestra `longarc` reconstruido del nombre, ocultando el metadato inválido.
  **Arreglo:** exigir que el campo `inject` exista y coincida exactamente con el sufijo; cualquier ausencia o diferencia debe dar exit 1 con motivo.

- **MAY — Fallar al guardar el informe conserva el éxito.** [run_mutants.py:443](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:443). Mutantes muertos y `PermissionError` al escribir `mutants_report.json` → exit 0 y `RESULTADO: OK`, aunque quede un informe anterior. Reproducido simulando exclusivamente las operaciones de entrada/salida.
  **Arreglo:** devolver error de entorno cuando no pueda guardarse el informe y evitar anunciar éxito.

Verificación: entrega completa leída, comparación con S-track·1, 23 pruebas sin escrituras aprobadas y sondas en memoria. Sin ejecutar el runner integrado ni modificar ficheros.

RESUMEN: BLOQ=3 MAY=1 MEN=0

PREMISA: matar mutantes y obtener nueve `FALLA` no demuestra por sí solo sensibilidad a las inyecciones: pueden fallar por causas ajenas. El cierre necesita controles positivos comparables y fallos atribuibles al defecto introducido. La validación contra el evaluador integrado de S-track·2 sigue pendiente del orquestador.