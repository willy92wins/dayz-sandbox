- **BLOQ — Persisten muertes atribuidas a preparación o limpieza.** [run_mutants.py:305](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:305), también líneas 383 y 609.

  **Escenario:** una clase define `setUp = preparar`; `preparar` lanza `FileNotFoundError` cuando `USE_MASK=False`. Sin mutación pasa; con `mascara_ignorada`, el traceback contiene `in preparar`, que el clasificador considera `kind="test"`. Resultado reproducido: `MUERTO`, `killed_by=["__main__.SetupAlias.test_imagen"]`, **cero ejecuciones del cuerpo del test**. El control sin mutar queda verde y no evita esta falsa atribución. Un fallo exclusivo de `addCleanup(limpiar)` también produce `MUERTO`.

  **Arreglo:** registrar estructuralmente la fase de ejecución —preparación, cuerpo, desmontaje y limpieza— antes de formatear el traceback. Añadir negativos para alias de `setUp` y callbacks de limpieza.

Verificación sin escribir ficheros: 28 tests puros pasan; 45 perturbaciones de las nueve negativas se rechazan. Los seis mutantes anteriores se conservan y los tres nuevos coinciden con §13. Runner integrado pendiente del orquestador.

RESUMEN: BLOQ=1 MAY=0 MEN=0

PREMISA: “Muere algún test” solo demuestra sensibilidad si el fallo procede de una comprobación pertinente del comportamiento. Las comparaciones de constantes del evaluador de juguete prueban el cableado, pero no que el evaluador real detecte sesgo, máscara ignorada o error exponencial. Ese cierre requiere la entrega integrada de S-track·2.

