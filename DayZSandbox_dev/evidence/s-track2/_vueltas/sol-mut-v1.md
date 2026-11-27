- **BLOQ — Se declara MUERTO sin que falle ningún test.** [run_mutants.py:232](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:232). Entrada: la ejecución termina con código 2 y sin resultados de unittest → `MUERTO`, `killed_by=[]`. También un fallo de `setUpClass`, con **0 tests ejecutados**, figura como muerte por `setUpClass`. Esto puede aprobar el cierre sin cumplir §5.1.  
  **Arreglo:** exigir una ejecución válida y un test individual identificado; los errores de infraestructura deben producir `ERROR`.

- **BLOQ — Un mutante no aplicado puede contar como superviviente.** [run_mutants.py:146](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:146). Con `USE_MASK = bool(1)` y el comentario `# USE_MASK = True`, la sustitución cambia únicamente el comentario. La constante continúa siendo `True`, pero una suite verde produce `SOBREVIVE`. Además, `THRESH_SUAVE_FRAC = 0.025` se transforma incorrectamente en `0.055`: se buscan subcadenas, no líneas exactas.  
  **Arreglo:** comprobar la línea completa y que corresponde a una asignación activa de módulo; ausencia o duplicación → `ERROR`.

- **BLOQ — Puede aprobarse una negativa ausente mediante metadatos contradictorios.** [check_negatives.py:144](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/check_negatives.py:144). Entrada: ocho negativas correctas y una novena con `run="suave60_Hb_quatlerp"`, `inject="longarc"` y `got="FALLA"` → salida **0**, aunque no existe `suave60_Hb_longarc`. El campo `inject` sobrescribe lo indicado por `run`.  
  **Arreglo:** identificar las nueve corridas mediante su nombre completo y rechazar contradicciones con los campos explícitos.

- **BLOQ — El cierre permite que sobrevivan tres mutantes incluidos en la entrega.** [run_mutants.py:301](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/mutants/run_mutants.py:301). Situación: mueren los seis mínimos y sobreviven `calib_match_cero`, `stimulus_cero` y `detector_laxo` → `ok=True`, salida **0**. El brief §5.1 exige que mueran **todos**, sin exceptuar los denominados extras.  
  **Arreglo:** exigir la muerte de los nueve para cerrar S-track·2; si se pretende excluir alguno, resolver primero esa discrepancia con el brief.

Verificación: lectura completa y sondas en memoria, sin escribir ficheros. Las nueve negativas normales se aceptan y las 27 variantes individuales PASA/INCONCLUSO/ausente se rechazan. La suite real queda pendiente del orquestador.

RESUMEN: BLOQ=4 MAY=0 MEN=0

PREMISA: El [brief:37](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/plans/2026-11-12-s-track-2-brief.md:37) exige p50 de `dt` ≤18 ms, pero también pide corridas limitadas a 30 FPS, cuyo intervalo estable ronda 33,3 ms. El [contrato:124](C:/tmp/dsbx-strack2/mut/DayZSandbox_dev/qa/strack/CONTRACT.md:124) introduce 36 ms para permitirlas, contradiciendo el brief que prevalece. Debe resolverse antes de correr en partida.

