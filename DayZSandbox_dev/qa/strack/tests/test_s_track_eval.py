"""Tests offline del evaluador de S-track·1 (brief §3, §4 y CONTRACT.md §3, §4).

Cargan el evaluador desde STRACK_EVAL_PATH (si existe en el entorno) con importlib y como CLI,
generan las fixtures sinteticas en un tmpdir y comprueban PASA, FALLA e INCONCLUSO, k=1,
convencion de FOV, detector, estimulo, cobertura, negativas y esquema de informe.json.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

STRACK_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_PATH = STRACK_DIR / "s_track_eval.py"
FIXTURES_MOD_PATH = STRACK_DIR / "fixtures" / "make_fixtures.py"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _eval_path():
    env_val = os.environ.get("STRACK_EVAL_PATH")
    if env_val:
        return Path(env_val).resolve()
    return DEFAULT_EVAL_PATH.resolve()


class STrackEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp_root = Path(cls._tmp.name)
        cls.fixtures_mod = _load_module(FIXTURES_MOD_PATH, "strack_make_fixtures")
        cls.fixture_dirs = cls.fixtures_mod.generate_all_fixtures(cls.tmp_root / "fixtures")
        cls.fixture_dirs["roll_defect"] = cls.fixtures_mod.generate_fixture(
            cls.tmp_root / "fixtures" / "roll_defect", kind="roll_defect"
        )
        cls.fixture_dirs["weak_stimulus"] = cls.fixtures_mod.generate_fixture(
            cls.tmp_root / "fixtures" / "weak_stimulus", kind="weak_stimulus"
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _load_eval(self):
        return _load_module(_eval_path(), "s_track_eval_target")

    def _run_cli(self, runs_dir, out_dir):
        script = _eval_path()
        proc = subprocess.run(
            [sys.executable, str(script), str(runs_dir), "--out", str(out_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        report_path = Path(out_dir) / "informe.json"
        md_path = Path(out_dir) / "informe.md"
        self.assertTrue(report_path.is_file(), f"Missing informe.json; stderr={proc.stderr}")
        self.assertTrue(md_path.is_file(), f"Missing informe.md; stderr={proc.stderr}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return proc.returncode, report

    def _assert_schema(self, report):
        self.assertEqual(report.get("schema"), 2)
        for key in ("calib", "detector", "results", "decisions", "negativas", "exit_code"):
            self.assertIn(key, report)
        self.assertIsInstance(report["calib"], dict)
        for hook, c in report["calib"].items():
            self.assertIn(hook, ("Ha", "Hb", "Hc"))
            for ck in ("k", "match_frac", "verdict", "cause", "fov_convention"):
                self.assertIn(ck, c)
            self.assertEqual(c["fov_convention"], "medida")  # brief v1.1 C
            self.assertIn(c["verdict"], ("PASA", "FALLA", "INCONCLUSO"))

        det = report["detector"]
        for dk in ("p95_px", "p95_deg", "verdict"):
            self.assertIn(dk, det)
        self.assertIn(det["verdict"], ("PASA", "FALLA", "INCONCLUSO"))

        self.assertIsInstance(report["results"], list)
        self.assertGreater(len(report["results"]), 0)
        for r in report["results"]:
            for rk in (
                "run",
                "caso",
                "hook",
                "inject",
                "measure",
                "reading",
                "window",
                "p95_px",
                "roll_deg",
                "coverage",
                "verdict",
                "cause",
            ):
                self.assertIn(rk, r)
            self.assertEqual(r["inject"], "none")
            self.assertIn(r["measure"], ("T-lect", "T-hook", "T-marca", "T-ropa", "T-suave"))
            self.assertIn(r["verdict"], ("PASA", "FALLA", "INCONCLUSO"))

        dec = report["decisions"]
        for dk in ("lectura", "hook_por_modo", "k", "ropa", "suave"):
            self.assertIn(dk, dec)
        for mode in ("mount0", "mount03", "lookat", "follow"):
            self.assertIn(mode, dec["hook_por_modo"])

        for neg in report["negativas"]:
            for nk in ("run", "inject", "expected", "got", "ok"):
                self.assertIn(nk, neg)
            self.assertNotEqual(neg["inject"], "none")

    def test_module_constants_exist(self):
        mod = self._load_eval()
        for name in (
            "THRESH_PX",
            "THRESH_ROLL_DEG",
            "COVERAGE_MIN",
            "CALIB_MATCH_MIN",
            "K_CANDIDATES",
            "STIMULUS_FACTOR",
            "DETECTOR_MAX_PX",
            "DETECTOR_MAX_DEG",
            "TEMPLATE_PX",
            "CORR_MIN",
            "MIN_SHOTS_WINDOW",
            "MASK_STD_MAX",
            "MASK_MIN_SHOTS",
            "MARK_AGREE_PX",
            "TEMPLATE_SOURCE",
            "USE_MASK",
            "ROPA_MAX_M",
            "ROPA_MAX_DEG",
            "JUMP_MIN_M",
            "THRESH_SUAVE_FRAC",
            "QUAT_NORM_TOL",
            "SUAVE_FPS_AGREE_DEG",
            "FPS_REGIME_TOL",
        ):
            self.assertTrue(hasattr(mod, name), f"Missing constant {name}")
        self.assertEqual(mod.TEMPLATE_PX, 48)
        self.assertEqual(mod.TEMPLATE_SOURCE, "marca")
        self.assertTrue(mod.USE_MASK)

    def test_pasa_fixture_cli_and_decisions(self):
        out_dir = self.tmp_root / "out_pasa"
        code, report = self._run_cli(self.fixture_dirs["pasa"], out_dir)
        self._assert_schema(report)

        self.assertEqual(code, 0)
        self.assertEqual(report["exit_code"], 0)

        # Calibracion: k=1 en Ha y Hb, convencion vertical
        self.assertEqual(report["calib"]["Ha"]["verdict"], "PASA")
        self.assertEqual(report["calib"]["Ha"]["k"], 1)
        self.assertGreaterEqual(report["calib"]["Ha"]["match_frac"], 0.99)
        # brief v1.1 C: la focal sale medida del giro de calib; la fixture la pinta con FOCAL_V (935,3 px)
        self.assertAlmostEqual(report["calib"]["Ha"]["f_px"], 935.3, delta=0.02 * 935.3)
        self.assertEqual(report["calib"]["Hb"]["verdict"], "PASA")
        self.assertEqual(report["calib"]["Hb"]["k"], 1)

        # Detector calibrado dentro de 0.5 px y 0.1 deg
        self.assertEqual(report["detector"]["verdict"], "PASA")
        self.assertLessEqual(report["detector"]["p95_px"], 0.5)
        self.assertLessEqual(report["detector"]["p95_deg"], 0.1)

        # Decisiones: lectura 'a' (y 'b'..'f' deben fallar en T-lect), k=1, Ha gana en cada modo
        self.assertEqual(report["decisions"]["lectura"], "a")
        self.assertEqual(report["decisions"]["k"]["Ha"], 1)
        for mode in ("mount0", "mount03", "lookat", "follow"):
            self.assertEqual(report["decisions"]["hook_por_modo"][mode], "Ha")

        tlect_a = [r for r in report["results"] if r["measure"] == "T-lect" and r["reading"] == "a"]
        tlect_b = [r for r in report["results"] if r["measure"] == "T-lect" and r["reading"] == "b"]
        self.assertTrue(all(r["verdict"] == "PASA" for r in tlect_a))
        self.assertTrue(any(r["verdict"] == "FALLA" for r in tlect_b))

        # Ventanas separadas: giro1, giro2, giro3 y resto
        windows_seen = {r["window"] for r in report["results"] if r["measure"] == "T-hook"}
        for w_expected in ("giro1", "giro2", "giro3", "resto"):
            self.assertIn(w_expected, windows_seen)

        # Negativas (inject != none) van solo a `negativas` y salen todas FALLA (ok=True)
        self.assertEqual(len(report["negativas"]), 3)
        for neg in report["negativas"]:
            self.assertEqual(neg["expected"], "FALLA")
            self.assertEqual(neg["got"], "FALLA")
            self.assertTrue(neg["ok"])

    def test_delay1_fixture_fails_with_exit_code_1(self):
        out_dir = self.tmp_root / "out_delay1"
        code, report = self._run_cli(self.fixture_dirs["delay1"], out_dir)
        self._assert_schema(report)
        self.assertEqual(code, 1)
        self.assertEqual(report["exit_code"], 1)
        thook_giros = [
            r for r in report["results"] if r["measure"] == "T-hook" and r["window"].startswith("giro")
        ]
        self.assertTrue(len(thook_giros) > 0)
        self.assertTrue(all(r["verdict"] == "FALLA" for r in thook_giros))
        self.assertIsNone(report["decisions"]["hook_por_modo"]["mount0"])
        self.assertIsNone(report["decisions"]["hook_por_modo"]["lookat"])

    def test_calib_pm1_fixture_rejects_calibration(self):
        out_dir = self.tmp_root / "out_calib_pm1"
        code, report = self._run_cli(self.fixture_dirs["calib_pm1"], out_dir)
        self._assert_schema(report)
        self.assertNotEqual(code, 0)
        self.assertNotEqual(report["calib"]["Ha"]["verdict"], "PASA")
        self.assertIsNone(report["calib"]["Ha"]["k"])
        self.assertIsNone(report["decisions"]["k"]["Ha"])

    def test_low_coverage_fixture_is_inconcluso_exit_code_2(self):
        out_dir = self.tmp_root / "out_low_cov"
        code, report = self._run_cli(self.fixture_dirs["low_coverage"], out_dir)
        self._assert_schema(report)
        self.assertEqual(code, 2)
        self.assertEqual(report["exit_code"], 2)
        thook = [r for r in report["results"] if r["measure"] == "T-hook"]
        self.assertTrue(any(r["verdict"] == "INCONCLUSO" and r["cause"] == "low_coverage" for r in thook))
        self.assertTrue(any(r["coverage"] < 0.95 for r in thook))

    def test_roll_defect_fails_and_weak_stimulus_is_inconcluso(self):
        mod = self._load_eval()
        rep_roll = mod.evaluate(self.fixture_dirs["roll_defect"])
        self.assertEqual(rep_roll["exit_code"], 1)
        thook_roll = [r for r in rep_roll["results"] if r["measure"] == "T-hook"]
        self.assertTrue(any(r["verdict"] == "FALLA" and r["roll_deg"] > 0.5 for r in thook_roll))

        rep_stim = mod.evaluate(self.fixture_dirs["weak_stimulus"])
        self.assertEqual(rep_stim["exit_code"], 2)
        thook_stim = [
            r for r in rep_stim["results"] if r["measure"] == "T-hook" and r["window"].startswith("giro")
        ]
        self.assertTrue(all(r["verdict"] == "INCONCLUSO" and r["cause"] == "insufficient_stimulus" for r in thook_stim))


if __name__ == "__main__":
    unittest.main()
