# Informe S-track·2 — INCONCLUSO (exit_code=2)

## 1. Calibración de imagen (`calib`)

| Hook | k | match_frac | f medida px (p05-p95, std, n) | referencia | Veredicto | Causa |
|---|---|---|---|---|---|---|
| Ha | -1 | 1.0000 | 682.01 (682.0-682.02, 0.007, 100) | f000010.bmp | PASA |  |
| Hb | -1 | 0.9950 | 923.94 (923.93-923.95, 0.006, 103) | f000010.bmp | PASA |  |

## 2. Calibración del detector

- `p95_px`: 999.0 px (máx 0.5 px)
- `p95_deg`: 999.0° (máx 0.1°)
- Veredicto: **INCONCLUSO**

## 3. Decisiones

- **Lectura ganadora (T-lect):** `None`
- **Desfase k por hook:** `{"Ha": -1, "Hb": -1}`
- **Hook por modo (T-hook):** `{"mount0": null, "mount03": null, "lookat": null, "follow": null}`
- **T-ropa:** `{"mochila": null, "mira": null, "silenciador": null}`
- **T-suave:** `{"30": "PASA", "60": "INCONCLUSO", "144": "INCONCLUSO"}`

## 4. Resultados por ventana

| Run | Caso | Hook | Medida | Lectura | Ventana | p95_px | roll_deg | Cobertura | Veredicto | Causa |
|---|---|---|---|---|---|---|---|---|---|---|
| follow_Ha | follow | Ha | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | a | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | d | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | e | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-lect | f | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow | follow | Ha,Hb | T-sesgo | a | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| follow | follow | Ha,Hb | T-sesgo | b | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| follow | follow | Ha,Hb | T-sesgo | c | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| follow | follow | Ha,Hb | T-sesgo | d | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| follow | follow | Ha,Hb | T-sesgo | e | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| follow | follow | Ha,Hb | T-sesgo | f | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| lookat | lookat | Ha,Hb | T-sesgo | a | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| lookat | lookat | Ha,Hb | T-sesgo | b | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| lookat | lookat | Ha,Hb | T-sesgo | c | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| lookat | lookat | Ha,Hb | T-sesgo | d | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| lookat | lookat | Ha,Hb | T-sesgo | e | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| lookat | lookat | Ha,Hb | T-sesgo | f | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | a | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | b | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | c | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | d | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | e | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | f | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | a | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | b | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | c | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | d | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | e | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount03 | mount03 | Ha,Hb | T-sesgo | f | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | a | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | b | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | c | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | d | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | e | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | f | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | a | marcas:punto_mira | 494.4162 | 0.0 | 1.0 | FALLA | p95_px_exceeded |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | b | marcas:punto_mira | 2428.125 | 0.0 | 0.2 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | c | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | d | marcas:punto_mira | 777.0583 | 0.0 | 1.0 | FALLA | p95_px_exceeded |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | e | marcas:punto_mira | 494.4162 | 0.0 | 1.0 | FALLA | p95_px_exceeded |
| mount0 | mount0 | Ha,Hb,Hc | T-sesgo | f | marcas:punto_mira | 494.4162 | 0.0 | 1.0 | FALLA | p95_px_exceeded |
| follow_Ha | follow | Ha | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Ha | follow | Ha | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| follow_Hb | follow | Hb | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Ha | lookat | Ha | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| lookat_Hb | lookat | Hb | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Ha | mount03 | Ha | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount03_Hb | mount03 | Hb | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Ha | mount0 | Ha | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hb | mount0 | Hb | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| mount0_Hc | mount0 | Hc | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | mascara_vacia |
| ropa_Hb | ropa | Hb | T-ropa | a | completa | 999.0 | 38.3937 | 1.0 | INCONCLUSO | mira_sin_marca_valida |
| ropa_Hb | ropa | Hb | T-ropa | f | completa | 999.0 | 38.3937 | 1.0 | INCONCLUSO | mira_sin_marca_valida |
| ropa_Hb | ropa | Hb | T-ropa | a | completa | 999.0 | 0.0925 | 1.0 | INCONCLUSO | mira_sin_marca_valida |
| ropa_Hb | ropa | Hb | T-ropa | f | completa | 999.0 | 0.0925 | 1.0 | INCONCLUSO | mira_sin_marca_valida |
| ropa_Hb | ropa | Hb | T-ropa | a | completa | 999.0 | 0.1021 | 1.0 | INCONCLUSO | mira_sin_marca_valida |
| ropa_Hb | ropa | Hb | T-ropa | f | completa | 999.0 | 0.1021 | 1.0 | INCONCLUSO | mira_sin_marca_valida |
| ropa | ropa | Hb | T-sesgo | a | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| ropa | ropa | Hb | T-sesgo | b | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| ropa | ropa | Hb | T-sesgo | c | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| ropa | ropa | Hb | T-sesgo | d | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| ropa | ropa | Hb | T-sesgo | e | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| ropa | ropa | Hb | T-sesgo | f | marcas:boca_anillo | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| ropa | ropa | Hb | T-sesgo | a | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| ropa | ropa | Hb | T-sesgo | f | marcas:punto_mira | 999.0 | 0.0 | 0.0 | INCONCLUSO | sesgo_no_observable |
| suave144_Hb | suave144 | Hb | T-suave | None | s0 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb | suave144 | Hb | T-suave | None | s03 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb | suave144 | Hb | T-suave | None | s08 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb | suave144 | Hb | T-suave | None | giro+170 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave144_Hb | suave144 | Hb | T-suave | None | giro-170 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave30_Hb | suave30 | Hb | T-suave | None | s0 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb | suave30 | Hb | T-suave | None | s03 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb | suave30 | Hb | T-suave | None | s08 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb | suave30 | Hb | T-suave | None | giro+170 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave30_Hb | suave30 | Hb | T-suave | None | giro-170 | 999.0 | 999.0 | 1.0 | PASA |  |
| suave60_Hb | suave60 | Hb | T-suave | None | s0 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave60_Hb | suave60 | Hb | T-suave | None | s03 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave60_Hb | suave60 | Hb | T-suave | None | s08 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave60_Hb | suave60 | Hb | T-suave | None | giro+170 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |
| suave60_Hb | suave60 | Hb | T-suave | None | giro-170 | 999.0 | 999.0 | 1.0 | INCONCLUSO | fps_regime |

## 5. Negativas

| Run | Inyección | Esperado | Obtenido | OK |
|---|---|---|---|---|
| lookat_Ha_delay1 | delay1 | FALLA | INCONCLUSO | False |
| lookat_Hb_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Ha_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Hb_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Hb_roll | roll | FALLA | INCONCLUSO | False |
| mount0_Hc_delay1 | delay1 | FALLA | INCONCLUSO | False |
| suave60_Hb_longarc | longarc | FALLA | FALLA | True |
| suave60_Hb_quatlerp | quatlerp | FALLA | PASA | False |
| suave60_Hb_smooth03 | smooth03 | FALLA | FALLA | True |
