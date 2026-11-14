# Informe S-track·1 — INCONCLUSO (exit_code=2)

## 1. Calibración de imagen (`calib`)

| Hook | k | match_frac | f medida px (p05-p95, std, n) | referencia | Veredicto | Causa |
|---|---|---|---|---|---|---|
| Ha | -1 | 1.0000 | 681.69 (681.25-682.66, 0.482, 101) | f000050.bmp | PASA |  |
| Hb | -1 | 1.0000 | 680.7 (680.63-685.64, 1.421, 88) | f000290.bmp | PASA |  |

## 2. Calibración del detector

- `p95_px`: 0.3209 px (máx 0.5 px)
- `p95_deg`: 0.0562° (máx 0.1°)
- Veredicto: **PASA**

## 3. Decisiones

- **Lectura ganadora (T-lect):** `None`
- **Desfase k por hook:** `{"Ha": -1, "Hb": -1}`
- **Hook por modo (T-hook):** `{"mount0": null, "mount03": null, "lookat": null, "follow": null}`

## 4. Resultados por ventana

| Run | Caso | Hook | Medida | Lectura | Ventana | p95_px | roll_deg | Cobertura | Veredicto | Causa |
|---|---|---|---|---|---|---|---|---|---|---|
| mount0_Ha | mount0 | Ha | T-lect | a | giro1 | 110.4264 | 20.5515 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | mount0 | Ha | T-lect | a | giro2 | 90.4161 | 10.8029 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | a | giro3 | 113.0746 | 21.9869 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | a | resto | 103.7491 | 22.7648 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | b | resto | 148440.6001 | 145.9787 | 0.3571 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | d | giro1 | 533.0715 | 13.8861 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | mount0 | Ha | T-lect | d | giro2 | 526.2272 | 3.9673 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | d | giro3 | 516.7716 | 14.9835 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | d | resto | 560.9938 | 17.0339 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | e | giro1 | 109.938 | 20.609 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | mount0 | Ha | T-lect | e | giro2 | 90.6251 | 10.6861 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | e | giro3 | 113.0746 | 21.9869 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | e | resto | 103.7491 | 23.2181 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | f | giro1 | 109.938 | 20.609 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Ha | mount0 | Ha | T-lect | f | giro2 | 90.6251 | 10.6861 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | f | giro3 | 113.0746 | 21.9869 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-lect | f | resto | 103.7491 | 23.2181 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | a | giro1 | 12.4029 | 3.1721 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | a | giro2 | 13.028 | 3.3063 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | a | giro3 | 12.6162 | 3.2259 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | a | resto | 14.1954 | 3.5118 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | b | giro2 | 29819.2205 | 106.9789 | 0.3333 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | b | giro3 | 5940.2821 | 38.6037 | 0.3333 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | b | resto | 21097.361 | 120.7877 | 0.3171 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | d | giro1 | 148.891 | 5.7978 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | d | giro2 | 150.8863 | 6.1558 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | d | giro3 | 149.4598 | 5.9722 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | d | resto | 153.0645 | 6.0571 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | e | giro1 | 12.4029 | 3.1721 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | e | giro2 | 13.028 | 3.4562 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | e | giro3 | 12.6162 | 3.4394 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | e | resto | 14.4224 | 3.9907 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-lect | f | giro1 | 12.4029 | 3.1721 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | f | giro2 | 13.028 | 3.4562 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | f | giro3 | 12.6162 | 3.4394 | 1.0 | FALLA | p95_px_exceeded |
| mount0_Hb | mount0 | Hb | T-lect | f | resto | 14.4224 | 3.9907 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | a | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | a | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | a | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | a | resto | 0.0475 | 0.0051 | 0.0222 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | b | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | b | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | b | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | b | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | c | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | c | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | c | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | c | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | d | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | d | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | d | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | d | resto | 688.2829 | 17.3341 | 0.0222 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | e | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | e | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | e | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | e | resto | 0.0475 | 0.0051 | 0.0222 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | f | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | f | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | f | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-lect | f | resto | 0.0475 | 0.0051 | 0.0222 | INCONCLUSO | low_coverage |
| follow_Ha | follow | Ha | T-hook | None | giro1 | 0.4263 | 0.1125 | 0.5 | INCONCLUSO | low_coverage |
| follow_Ha | follow | Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| follow_Ha | follow | Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| follow_Ha | follow | Ha | T-hook | None | resto | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| follow_Hb | follow | Hb | T-hook | None | giro1 | 73.3039 | 1.3162 | 0.3333 | INCONCLUSO | low_coverage |
| follow_Hb | follow | Hb | T-hook | None | giro2 | 78.6819 | 8.243 | 0.5 | INCONCLUSO | low_coverage |
| follow_Hb | follow | Hb | T-hook | None | giro3 | 80.1862 | 0.1348 | 0.3333 | INCONCLUSO | low_coverage |
| follow_Hb | follow | Hb | T-hook | None | resto | 48.9079 | 1.8657 | 0.4787 | INCONCLUSO | low_coverage |
| lookat_Ha | lookat | Ha | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Ha | lookat | Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Ha | lookat | Ha | T-hook | None | giro3 | 1.2701 | 0.0528 | 0.3333 | INCONCLUSO | low_coverage |
| lookat_Ha | lookat | Ha | T-hook | None | resto | 0.626 | 0.4491 | 0.3158 | INCONCLUSO | low_coverage |
| lookat_Hb | lookat | Hb | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Hb | lookat | Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Hb | lookat | Hb | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| lookat_Hb | lookat | Hb | T-hook | None | resto | 0.5741 | 0.3098 | 0.1053 | INCONCLUSO | low_coverage |
| mount03_Ha | mount03 | Ha | T-hook | None | giro1 | 223.6252 | 92.6103 | 0.1429 | INCONCLUSO | low_coverage |
| mount03_Ha | mount03 | Ha | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount03_Ha | mount03 | Ha | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount03_Ha | mount03 | Ha | T-hook | None | resto | 146.452 | 34.3288 | 0.0547 | INCONCLUSO | low_coverage |
| mount03_Hb | mount03 | Hb | T-hook | None | giro1 | 180.4283 | 20.9863 | 0.3333 | INCONCLUSO | low_coverage |
| mount03_Hb | mount03 | Hb | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount03_Hb | mount03 | Hb | T-hook | None | giro3 | 200.0394 | 20.9128 | 0.3333 | INCONCLUSO | low_coverage |
| mount03_Hb | mount03 | Hb | T-hook | None | resto | 138.7986 | 11.2532 | 0.025 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-hook | None | giro1 | 178.3985 | 45.2646 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Ha | mount0 | Ha | T-hook | None | giro2 | 149.2036 | 35.4726 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-hook | None | giro3 | 181.37 | 46.2586 | 0.5 | INCONCLUSO | low_coverage |
| mount0_Ha | mount0 | Ha | T-hook | None | resto | 169.6957 | 43.3752 | 0.9048 | INCONCLUSO | low_coverage |
| mount0_Hb | mount0 | Hb | T-hook | None | giro1 | 91.7272 | 23.8643 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Hb | mount0 | Hb | T-hook | None | giro2 | 95.8349 | 25.2015 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Hb | mount0 | Hb | T-hook | None | giro3 | 92.4712 | 23.9391 | 1.0 | INCONCLUSO | t_lect_inconcluso |
| mount0_Hb | mount0 | Hb | T-hook | None | resto | 91.5233 | 24.1175 | 0.9024 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-hook | None | giro1 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-hook | None | giro2 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-hook | None | giro3 | 999.0 | 999.0 | 0.0 | INCONCLUSO | low_coverage |
| mount0_Hc | mount0 | Hc | T-hook | None | resto | 70.6191 | 18.3629 | 0.0222 | INCONCLUSO | low_coverage |

## 5. Negativas

| Run | Inyección | Esperado | Obtenido | OK |
|---|---|---|---|---|
| lookat_Ha_delay1 | delay1 | FALLA | INCONCLUSO | False |
| lookat_Hb_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Ha_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Ha_roll | roll | FALLA | INCONCLUSO | False |
| mount0_Hb_delay1 | delay1 | FALLA | INCONCLUSO | False |
| mount0_Hc_delay1 | delay1 | FALLA | INCONCLUSO | False |
