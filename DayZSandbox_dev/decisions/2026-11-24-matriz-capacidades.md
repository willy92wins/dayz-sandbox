# Matriz de capacidades de M1 (F0)

Una fila por spike, con su veredicto y su evidencia, como pide el plan (`plans/2026-10-26-m1-cine-v2.md:60`):
PASA, FALLA o INCONCLUSO, con la evidencia en `evidence/m1/<spike>/`. Un FALLA bloquea la fase que lo consume y
vuelve al Grill; INCONCLUSO no cuenta como PASA. El veredicto vale en retail (#25).

| Spike | Veredicto | Fecha | Evidencia | Alimenta | Notas |
|---|---|---|---|---|---|
| S-cot | Estudio hecho, sin partida. Desde el cambio del 2026-11-15 no lleva PASA, FALLA ni INCONCLUSO | 2026-11-24 | `research/2026-11-15-s-cot-estudio-camaras.md`, en la raíz del repo (PR #24, `fbae7ae`) | Ideas para B1, F4 y F6; no bloquea ninguna fase | Ninguna de las tres herramientas (COT, VPPAdminTools y PCT) cubre B4, el HUD oculto durante la toma, como función de la cámara, ni B5, parar en menos de 1 s. El orquestador comprobó las citas antes de la PR |
