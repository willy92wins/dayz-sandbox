# Evidencia de S-track·1

La evidencia binaria (PNG de las capturas, `samples.jsonl`, logs de cliente y servidor) **no está en git**.
Queda en el PC de Guillermo. En git van solo los informes de la tanda con foco (`_informe/`) y esta nota.

## Tanda con foco (2026-11-11/12). Es la que vale
- Ruta: `C:\tmp\dsbx-strack\merge\DayZSandbox_dev\evidence\s-track\<run>\` (17 corridas, 4,5 GB).
- Cada corrida tiene su `SHA256SUMS`, con el sha256 de cada fichero. Índice:
  `SHA256SUMS.index` sha256 `52ff5622489dac1f56d886f864c20666cb4858bb700712cfd43d06de46d4f88b`.
- PBO: `C:\tmp\dsbx-strack\bench\@DZS_STrack\Addons\DZS_STrack.pbo`, sha256
  `ded9de6c1fdb6f289a95f67bd6ccd12685d6622dc99f4e463183917329a8e4b9`.
- Informes: `_informe/informe.md` (resumen, evaluador y anexos), `_informe/informe.json`,
  `_informe/informe_evaluador.md` (salida tal cual de `qa/strack/s_track_eval.py`). En el PC, además,
  `montage_v13.png` y `overlay_mount0_Hb.png`.

## Tanda sin foco (2026-11-10/11). Archivada, no vale para decidir
- Ruta: `C:\tmp\dsbx-strack\evidence_v12_nofocus\<run>\`. Índice `SHA256SUMS.index` sha256
  `7fb5123ab30d14c6afa276679f4dbf421ff2ce7f2ebbda265489ed84f6a6ee9a`.
- No vale porque el arma salía sin texturas y había menú de pausa en algunas capturas, y porque el evaluador
  tenía dos fallos que dejaban el detector sin detecciones (ver `_informe/informe.md`).

## Otras corridas archivadas (solo diagnóstico)
- Precisión de 1 cm en las posiciones: `C:\tmp\dsbx-strack\evidence_old_v11_cm\`.
- H-b roto (House, ScriptedEntity, ItemBase local) y calib de periodo 2:
  `C:\tmp\dsbx-strack\evidence_old_v10\` y `C:\tmp\dsbx-strack\bench\runs\client\profiles\old_v10\`.
- Corrida de prueba sin giro ni límite de fps (6,3 GB de BMP):
  `C:\tmp\dsbx-strack\bench\runs\client\profiles\strack\smoke1_mount0_Ha_noturn_noFPSlimit\`.

## Hueco para S-track·2
La plantilla del detector se recorta centrada en la proyección de una lectura (primera captura válida), así que
T-lect no puede ver un sesgo constante entre la lectura y lo dibujado. Solo ve su variación. En S-track·2
la plantilla tiene que salir de un punto que no venga de ninguna lectura (por ejemplo, marcado a mano en una captura).
