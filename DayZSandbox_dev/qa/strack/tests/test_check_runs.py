"""Tests de check_runs.py: la comprobación de corridas reales del arbitraje de S-track·2 (2026-11-13)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_runs  # noqa: E402

FPS = 60
DT = 1.0 / FPS


def write_run(root, name, rows, done=None, preflight=True):
    d = Path(root) / name
    d.mkdir(parents=True)
    with (d / "samples.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    (d / "done.json").write_text(json.dumps(done if done is not None else {"ok": True}), encoding="utf-8")
    if preflight:
        (d / "preflight.json").write_text('{"dt_p50_ms": 16.7}', encoding="utf-8")
    return d


def rows_with_giros(n_giros, giro_s=4.0, suave=False, dt=DT):
    """Frames a 60 fps: 1 s quieto, y n giros de giro_s separados por 1 s quieto."""
    rows, frame, t = [], 0, 0.0
    plan = [(0, 1.0)]
    for g in range(1, n_giros + 1):
        plan += [(g, giro_s), (0, 1.0)]
    for giro, dur in plan:
        for _ in range(int(round(dur / dt))):
            frame += 1
            t += dt * 1000.0
            r = {"frame": frame, "t_ms": t, "dt": dt, "giro": giro}
            if suave:
                r["cam_raw"] = {"pos": [0, 0, 0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1], "q": [0, 0, 0, 1]}
                r["lata"] = {"a": [0, 0, 3]}
            rows.append(r)
    return rows


def rows_deriva(pico_ms):
    """Calib de 200 frames con deriva acumulada que sube 1 ms por par hasta pico_ms y luego se mantiene.

    dt = 15,625 ms exacto en binario; Δt_ms = dt + subida. Empieza en el
    frame 1 (sin intervalo de carga 0→1: ningún par queda exento).
    """
    dt = 0.015625
    rows, t, subida_total = [], 0.0, 0.0
    for i in range(200):
        if i == 0:
            paso = dt * 1000.0
        elif subida_total + 1.0 <= pico_ms:
            paso = dt * 1000.0 + 1.0
            subida_total += 1.0
        elif subida_total < pico_ms:
            paso = dt * 1000.0 + (pico_ms - subida_total)
            subida_total = pico_ms
        else:
            paso = dt * 1000.0
        t += paso
        rows.append({"frame": i + 1, "t_ms": round(t, 6), "dt": dt, "giro": 0})
    return rows


class CheckRunsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_check(self, root=None):
        root = Path(root) if root is not None else self.tmp
        out = root / "out.json"
        code = check_runs.main([str(root), "--json", str(out)])
        return code, json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}

    def test_corridas_completas_son_validas(self):
        write_run(self.tmp, "calib_Hb", [{"frame": i, "t_ms": i * 1000 * DT, "dt": DT, "giro": 0} for i in range(1, 201)])
        write_run(self.tmp, "mount0_Hb", rows_with_giros(3))
        write_run(self.tmp, "mount0_Hb_delay1", rows_with_giros(3))
        write_run(self.tmp, "suave60_Hb", rows_with_giros(2, suave=True))
        code, res = self.run_check()
        self.assertEqual(code, 0, res)
        self.assertTrue(all(r["valida"] for r in res.values()))

    def test_giro_truncado_invalida(self):  # BLOQ 1 de Sol v4
        rows = [r for r in rows_with_giros(3) if not (r["giro"] == 3 and r["t_ms"] > 14000)]
        write_run(self.tmp, "mount0_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("giro 3 dura", "; ".join(res["mount0_Hb"]["motivos"]))

    def test_falta_un_giro_invalida(self):
        write_run(self.tmp, "follow_Ha", rows_with_giros(2))
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("falta el giro 3", res["follow_Ha"]["motivos"])

    def test_cam_raw_ausente_invalida(self):  # BLOQ 2
        rows = rows_with_giros(2, suave=True)
        for r in rows[300:320]:
            r["cam_raw"]["q"] = None
        write_run(self.tmp, "suave60_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("20 frames sin cam_raw", "; ".join(res["suave60_Hb"]["motivos"]))

    def test_reloj_incoherente_invalida(self):  # BLOQ 3: t_ms duplicado con el mismo dt
        rows = rows_with_giros(3)
        for r in rows:
            r["t_ms"] *= 2
        write_run(self.tmp, "mount0_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("t_ms incoherente con dt", "; ".join(res["mount0_Hb"]["motivos"]))

    def test_reloj_real_con_tiron_es_valido(self):
        # Patrón de la primera corrida real (calib_Ha, 13-nov 22:56): frames de 16-17 ms enteros, dt redondeado a 1 ms
        # y un tirón en el que t_ms da 36+5 ms y dt 8+32 ms (mismo total). Antes, ± 1 ms par a par lo invalidaba.
        rows = rows_with_giros(3)
        t = 0.0
        for i, r in enumerate(rows):
            paso = 17 if i % 3 else 16
            if i == 400:
                paso, r_dt = 36, 8
            elif i == 401:
                paso, r_dt = 5, 32
            else:
                r_dt = paso
            t += paso
            r["t_ms"], r["dt"] = t, r_dt / 1000.0
        # los giros siguen durando ~4 s con estos pasos (240 frames a 16,67 ms de media)
        write_run(self.tmp, "mount0_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 0, res)

    def test_reloj_con_otro_ritmo_invalida(self):  # un 3 % más rápido: deriva de cientos de ms
        rows = rows_with_giros(3)
        for r in rows:
            r["t_ms"] *= 1.03
        write_run(self.tmp, "mount0_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("deriva acumulada", "; ".join(res["mount0_Hb"]["motivos"]))

    def test_reloj_parado_invalida(self):
        rows = rows_with_giros(3)
        for r in rows[100:110]:
            r["t_ms"] = rows[99]["t_ms"]
        write_run(self.tmp, "mount0_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("t_ms que no crece", "; ".join(res["mount0_Hb"]["motivos"]))

    def test_negativa_sin_calib_invalida(self):  # BLOQ 4
        write_run(self.tmp, "mount0_Hb_roll", rows_with_giros(3))
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("sin calib_Hb", res["mount0_Hb_roll"]["motivos"])

    def test_negativa_hc_usa_calib_ha(self):
        write_run(self.tmp, "mount0_Hc_delay1", rows_with_giros(3))
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("sin calib_Ha", res["mount0_Hc_delay1"]["motivos"])
        write_run(self.tmp, "calib_Ha", [{"frame": i, "t_ms": i * 1000 * DT, "dt": DT, "giro": 0} for i in range(1, 201)])
        code, res = self.run_check()
        self.assertEqual(code, 0, res)

    def test_preflight_fallido_invalida(self):
        write_run(self.tmp, "mount0_Ha", rows_with_giros(3), done={"ok": False, "causa": "fps"}, preflight=False)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertTrue(any("done.ok=False" in m for m in res["mount0_Ha"]["motivos"]))

    def test_deriva_exactamente_en_el_limite_es_valida(self):  # vuelta 5, respuesta 6 de Sol
        write_run(self.tmp, "calib_Hb", rows_deriva(check_runs.DERIVA_MAX_MS))
        code, res = self.run_check()
        self.assertEqual(code, 0, res)

    def test_deriva_justo_por_encima_del_limite_invalida(self):
        write_run(self.tmp, "calib_Hb", rows_deriva(check_runs.DERIVA_MAX_MS + 0.5))
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("deriva acumulada", "; ".join(res["calib_Hb"]["motivos"]))

    def test_intervalo_coherente_de_101_ms_es_valido(self):  # vuelta 5b, M2: sin techo INTERVALO_MAX_MS
        # Un frame coherente de 101 ms (dt y Δt_ms coinciden, deriva ~0)
        # es válido: no hay base contractual para un techo de 100 ms.
        rows, t = [], 0.0
        for i in range(1, 201):
            dt = 0.101 if i == 100 else DT
            t += dt * 1000.0
            rows.append({"frame": i, "t_ms": round(t, 6), "dt": dt, "giro": 0})
        write_run(self.tmp, "calib_Ha", rows, preflight=False)
        code, res = self.run_check()
        self.assertEqual(code, 0, res)
        self.assertTrue(res["calib_Ha"]["valida"], res)

    def test_carga_extrema_coherente_es_valida(self):  # vuelta 5b, M2: sin techo, la carga coherente no invalida
        # Antes (H2) una carga de 5 s invalidaba por INTERVALO_MAX_MS; sin
        # base contractual para ese techo, una carga extrema pero coherente
        # (dt y Δt_ms coinciden y el par 0→1 sigue exento de deriva) es válida.
        rows, t = [], 0.0
        for i in range(200):
            dt = 5.0 if i == 1 else DT
            t += dt * 1000.0 if i > 0 else 0.0
            rows.append({"frame": i, "t_ms": round(t, 6), "dt": dt, "giro": 0})
        write_run(self.tmp, "calib_Ha", rows, preflight=False)
        code, res = self.run_check()
        self.assertEqual(code, 0, res)
        self.assertTrue(res["calib_Ha"]["valida"], res)

    def test_salto_extremo_coherente_de_t_ms_en_carga_es_valido(self):  # vuelta 5b, M2
        # +100 s en el par de carga, coherente con dt: sin techo de
        # intervalo no invalida (el desplazamiento es constante después).
        rows, t = [], 0.0
        for i in range(200):
            dt = 100.0 if i == 1 else DT
            t += dt * 1000.0 if i > 0 else 0.0
            rows.append({"frame": i, "t_ms": round(t, 6), "dt": dt, "giro": 0})
        write_run(self.tmp, "calib_Ha", rows, preflight=False)
        code, res = self.run_check()
        self.assertEqual(code, 0, res)
        self.assertTrue(res["calib_Ha"]["valida"], res)

    def test_primer_par_visto_no_es_carga_sin_frame_cero(self):  # H2: empieza en frame 1, sin exención
        rows = [{"frame": i, "t_ms": i * 1000 * DT, "dt": DT, "giro": 0} for i in range(1, 201)]
        rows[1]["dt"] = 5.0
        write_run(self.tmp, "calib_Ha", rows, preflight=False)
        code, res = self.run_check()
        self.assertEqual(code, 1, res)

    def test_duplicado_con_dt_distinto_invalida(self):  # H3: el evaluador conserva la segunda fila
        rows = rows_with_giros(3)
        dup = dict(rows[100], dt=0.3)
        rows = rows[:101] + [dup] + rows[101:]
        write_run(self.tmp, "mount0_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("duplicado", "; ".join(res["mount0_Hb"]["motivos"]))

    def test_duplicado_con_t_ms_distinto_invalida(self):  # H3
        rows = rows_with_giros(3)
        dup = dict(rows[100], t_ms=rows[100]["t_ms"] + 500.0)
        rows = rows[:101] + [dup] + rows[101:]
        write_run(self.tmp, "mount0_Hb", rows)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("duplicado", "; ".join(res["mount0_Hb"]["motivos"]))

    def test_valores_no_finitos_o_no_positivos_invalidan(self):  # H4
        casos = {
            "dt_nan": ("dt", float("nan")),
            "dt_cero": ("dt", 0.0),
            "dt_negativo": ("dt", -0.016),
            "t_ms_nan": ("t_ms", float("nan")),
        }
        for nombre, (campo, valor) in casos.items():
            with self.subTest(caso=nombre):
                root = self.tmp / nombre
                root.mkdir()
                rows = rows_with_giros(3)
                rows[100][campo] = valor
                write_run(root, "mount0_Hb", rows)
                code, res = self.run_check(root)
                self.assertEqual(code, 1, res)
                # NaN literal lo rechaza el parser JSON (línea ilegible); dt<=0 sale como dt no positivo.
                self.assertTrue(any("finito" in m or "dt>0" in m or "dt positivo" in m or "ilegibles" in m
                                    for m in res["mount0_Hb"]["motivos"]), res)

    def test_infinito_literal_en_json_invalida(self):  # H4: Infinity en el JSON, no solo en t_ms/dt
        d = write_run(self.tmp, "mount0_Hb", rows_with_giros(3))
        path = d / "samples.jsonl"
        lineas = path.read_text(encoding="utf-8").splitlines()
        lineas[10] = lineas[10].replace('"dt": 0.016666666666666666', '"dt": Infinity')
        self.assertIn("Infinity", lineas[10])
        path.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        code, res = self.run_check()
        self.assertEqual(code, 1, res)

    def test_hc_con_calib_ha_invalida(self):  # respuesta 6 de Sol: Ha inválida arrastra a la negativa Hc
        rows = [{"frame": i, "t_ms": i * 2000 * DT, "dt": DT, "giro": 0} for i in range(1, 201)]
        write_run(self.tmp, "calib_Ha", rows, preflight=False)
        write_run(self.tmp, "mount0_Hc_delay1", rows_with_giros(3))
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("calib_Ha invalida", res["mount0_Hc_delay1"]["motivos"])

    def test_fixture_real_calibraciones_validas(self):  # Ha y Hb reales (13-nov) siguen VALIDAS
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "real_clock_calib.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        for nombre, bloque in sorted(data["runs"].items()):
            rows = [{"frame": f, "t_ms": t, "dt": dt, "giro": 0} for f, t, dt in bloque["rows"]]
            write_run(self.tmp, nombre, rows, preflight=False)
        code, res = self.run_check()
        self.assertEqual(code, 0, res)
        self.assertTrue(all(r["valida"] for r in res.values()), res)

    def test_carpetas_apartadas_por_el_banco_no_cuentan(self):
        write_run(self.tmp, "mount0_Hb", rows_with_giros(3))
        write_run(self.tmp, "mount0_Hb.invalid_101010", rows_with_giros(1))
        code, res = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(list(res), ["mount0_Hb"])


if __name__ == "__main__":
    unittest.main()
