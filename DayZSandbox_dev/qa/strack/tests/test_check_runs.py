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


class CheckRunsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_check(self):
        out = self.tmp / "out.json"
        code = check_runs.main([str(self.tmp), "--json", str(out)])
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

    def test_negativa_sin_calib_invalida(self):  # BLOQ 4
        write_run(self.tmp, "mount0_Hb_roll", rows_with_giros(3))
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("sin calib_Hb", res["mount0_Hb_roll"]["motivos"])

    def test_preflight_fallido_invalida(self):
        write_run(self.tmp, "mount0_Ha", rows_with_giros(3), done={"ok": False, "causa": "fps"}, preflight=False)
        code, res = self.run_check()
        self.assertEqual(code, 1)
        self.assertTrue(any("done.ok=False" in m for m in res["mount0_Ha"]["motivos"]))

    def test_carpetas_apartadas_por_el_banco_no_cuentan(self):
        write_run(self.tmp, "mount0_Hb", rows_with_giros(3))
        write_run(self.tmp, "mount0_Hb.invalid_101010", rows_with_giros(1))
        code, res = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(list(res), ["mount0_Hb"])


if __name__ == "__main__":
    unittest.main()
