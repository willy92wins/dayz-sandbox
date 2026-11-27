# Informe S-track·2 — INCONCLUSO (exit_code=2)

## 1. Calibración de imagen (`calib`)

| Hook | k | match_frac | f medida px (p05-p95, std, n) | referencia | Veredicto | Causa |
|---|---|---|---|---|---|---|

## 2. Calibración del detector

- `p95_px`: 999.0 px (máx 0.5 px)
- `p95_deg`: 999.0° (máx 0.1°)
- Veredicto: **INCONCLUSO**

## 3. Decisiones

- **Lectura ganadora (T-lect):** `None`
- **Desfase k por hook:** `{}`
- **Hook por modo (T-hook):** `{"mount0": null, "mount03": null, "lookat": null, "follow": null}`
- **T-ropa:** `{"mochila": null, "mira": null, "silenciador": null}`
- **T-suave:** `{"30": "PASA", "60": "PASA", "144": "INCONCLUSO"}`

## 4. Resultados por ventana

| Run | Caso | Hook | Medida | Lectura | Ventana | p95_px | roll_deg | Cobertura | Veredicto | Causa |
|---|---|---|---|---|---|---|---|---|---|---|
| suave144_Hb_ns | suave144 | Hb | T-suave | None | s0 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb_ns | suave144 | Hb | T-suave | None | s03 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb_ns | suave144 | Hb | T-suave | None | s08 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb_ns | suave144 | Hb | T-suave | None | giro+170 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb_ns | suave144 | Hb | T-suave | None | giro-170 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave30_Hb_ns | suave30 | Hb | T-suave | None | s0 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb_ns | suave30 | Hb | T-suave | None | s03 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb_ns | suave30 | Hb | T-suave | None | s08 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb_ns | suave30 | Hb | T-suave | None | giro+170 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb_ns | suave30 | Hb | T-suave | None | giro-170 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave60_Hb_ns | suave60 | Hb | T-suave | None | s0 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave60_Hb_ns | suave60 | Hb | T-suave | None | s03 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave60_Hb_ns | suave60 | Hb | T-suave | None | s08 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave60_Hb_ns | suave60 | Hb | T-suave | None | giro+170 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave60_Hb_ns | suave60 | Hb | T-suave | None | giro-170 | 999.0 | 999.0 | 1.0 | PASA |  |

## 5. Negativas

| Run | Inyección | Esperado | Obtenido | OK |
|---|---|---|---|---|
| suave144_Hb_quatlerp_ns | quatlerp | FALLA | INCONCLUSO | False |
| suave30_Hb_quatlerp_ns | quatlerp | FALLA | PASA | False |
