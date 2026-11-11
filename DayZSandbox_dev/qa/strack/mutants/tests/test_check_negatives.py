"""Tests de juguete para check_negatives.py (unittest, solo stdlib).

Informes de juguete que cumplen el criterio 4, que tienen un PASA y a
los que les falta una corrida esperada.
"""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_module(name, path):
    import sys

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CHECK_PATH = Path(__file__).resolve().parents[2] / "check_negatives.py"
check_negatives = _load_module("check_negatives_under_test", CHECK_PATH)

HOOKS = ("Ha", "Hb")


def _results():
    rows = []
    for caso in ("mount0", "lookat"):
        for hook in HOOKS:
            rows.append({
                "run": f"{caso}_{hook}", "caso": caso, "hook": hook,
                "inject": "none", "measure": "T-hook", "reading": None,
                "window": "giro1", "p95_px": 0.1, "roll_deg": 0.0,
                "coverage": 1.0, "verdict": "PASA", "cause": "",
            })
    return rows


def _negativa(run, inject, got):
    return {
        "run": run, "inject": inject, "expected": "FALLA",
        "got": got, "ok": got == "FALLA",
    }


def make_informe(overrides=None, omit=()):
    negativas = []
    for caso in ("mount0", "lookat"):
        for hook in HOOKS:
            run = f"{caso}_{hook}_delay1"
            if run not in omit:
                negativas.append(_negativa(run, "delay1", "FALLA"))
    if "mount0_Ha_roll" not in omit:
        negativas.append(_negativa("mount0_Ha_roll", "roll", "FALLA"))
    for run, got in (overrides or {}).items():
        for entry in negativas:
            if entry["run"] == run:
                entry["got"] = got
                entry["ok"] = got == "FALLA"
    return {
        "schema": 1,
        "calib": {},
        "detector": {"p95_px": 0.1, "p95_deg": 0.01, "verdict": "PASA"},
        "results": _results(),
        "decisions": {"lectura": "a", "hook_por_modo": {}, "k": {}},
        "negativas": negativas,
        "exit_code": 0,
    }


class TestCheckInforme(unittest.TestCase):
    def test_cumple_exit_zero(self):
        code, rows = check_negatives.check_informe(make_informe())
        self.assertEqual(code, 0, rows)
        self.assertTrue(all(r["status"] == "OK" for r in rows))
        # delay1 mount0 x2 + delay1 lookat x2 + roll mount0 Ha.
        self.assertEqual(len(rows), 5, rows)

    def test_pasa_en_negativa_exit_uno(self):
        informe = make_informe(overrides={"lookat_Hb_delay1": "PASA"})
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)
        bad = [r for r in rows if r["status"] == "MAL_VEREDICTO"]
        self.assertEqual([r["run"] for r in bad], ["lookat_Hb_delay1"])

    def test_inconcluso_en_negativa_exit_uno(self):
        informe = make_informe(overrides={"mount0_Ha_roll": "INCONCLUSO"})
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)

    def test_falta_una_corrida_exit_dos(self):
        informe = make_informe(omit={"lookat_Hb_delay1"})
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 2, rows)
        missing = [r for r in rows if r["status"] == "FALTA"]
        self.assertEqual([r["run"] for r in missing], ["lookat_Hb_delay1"])

    def test_falta_roll_exit_dos(self):
        informe = make_informe(omit={"mount0_Ha_roll"})
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 2, rows)

    def test_sin_results_exige_al_menos_ha(self):
        informe = make_informe()
        informe["results"] = []
        code, rows = check_negatives.check_informe(informe)
        # Sin hooks evaluados conocidos se exige Ha: el informe cumple.
        self.assertEqual(code, 0, rows)
        self.assertEqual(len(rows), 3, rows)


class TestCheckNegativesMain(unittest.TestCase):
    def _write(self, informe):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "informe.json"
        path.write_text(json.dumps(informe), encoding="utf-8")
        return path

    def test_main_cumple(self):
        path = self._write(make_informe())
        self.assertEqual(check_negatives.main([str(path)]), 0)

    def test_main_pasa(self):
        path = self._write(
            make_informe(overrides={"mount0_Ha_delay1": "PASA"})
        )
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_falta_corrida(self):
        path = self._write(make_informe(omit={"mount0_Hb_delay1"}))
        self.assertEqual(check_negatives.main([str(path)]), 2)

    def test_main_fichero_ausente(self):
        self.assertEqual(
            check_negatives.main(["no_existe_informe.json"]), 2
        )


if __name__ == "__main__":
    unittest.main()
