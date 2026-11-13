- **BLOQ — Un error en `setUp()` puede matar todos los mutantes sin ejecutar sus tests.** [run_mutants.py:298](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:298).
  
  Escenario: `setUp()` carga un recurso situado junto al evaluador. El baseline usa el original y pasa; las copias temporales carecen del recurso y producen `FileNotFoundError`. `_kind()` identifica esos errores como `kind="test"` y los convierte en muertes atribuibles al método que nunca se ejecutó. Sonda en memoria, con E/S simulada: **nueve MUERTO, `report.ok=true`, exit 0**, sin ejecutar ningún cuerpo de test contra los mutantes.
  
  **Arreglo:** distinguir errores de preparación, limpieza y ejecución del método; comprobar también una copia sin mutar con la misma disposición que los mutantes.

- **BLOQ — Se acepta `expected` ausente o contradictorio con §14.** [check_negatives.py:210](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:210).
  
  Escenario: nueve corridas con `run` e `inject` correctos y `got="FALLA"`, pero una con `expected="PASA"`, `null` o sin `expected` → **exit 0 y «CRITERIO 5: OK»**. Reproducido mediante `main()` con lectura simulada; §14 exige `expected="FALLA"` en todas.
  
  **Arreglo:** exigir ese campo y valor, rechazando cada discrepancia con motivo por corrida.

Verificación: lectura completa, 27 tests puros aprobados y sondas en memoria. Sin escribir ficheros ni ejecutar el runner real.

RESUMEN: BLOQ=2 MAY=0 MEN=0

PREMISA: matar mutantes mediante aserciones sobre constantes solo prueba el arnés. La sensibilidad de la medida requiere ejecutar las fixtures del evaluador integrado; esa comprobación sigue correspondiendo al orquestador.

