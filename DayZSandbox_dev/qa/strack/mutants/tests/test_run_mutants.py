"""Tests de juguete para run_mutants.py (unittest, solo stdlib).

Crea un evaluador y una suite de juguete en un tmpdir: la suite carga
el evaluador desde STRACK_EVAL_PATH y detecta las constantes que los
mutantes minimos tocan.
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


RUN_MUTANTS_PATH = Path(__file__).resolve().parents[1] / "run_mutants.py"
run_mutants = _load_module("run_mutants_under_test", RUN_MUTANTS_PATH)

TOY_EVALUATOR = '''\
"""Evaluador de juguete."""
THRESH_PX = 2.0
THRESH_ROLL_DEG = 0.5
COVERAGE_MIN = 0.95
CALIB_MATCH_MIN = 0.99
K_CANDIDATES = (-2, -1, 0, 1, 2)
STIMULUS_FACTOR = 3.0
DETECTOR_MAX_PX = 0.5
DETECTOR_MAX_DEG = 0.1
'''

TOY_SUITE = '''\
"""Suite de juguete: detecta las constantes de los mutantes minimos."""
import importlib.util
import os
import unittest


def _load_eval():
    path = os.environ["STRACK_EVAL_PATH"]
    spec = importlib.util.spec_from_file_location("toy_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVAL = _load_eval()


class TestToyEval(unittest.TestCase):
    def test_thresh_px(self):
        self.assertEqual(EVAL.THRESH_PX, 2.0)

    def test_thresh_roll(self):
        self.assertEqual(EVAL.THRESH_ROLL_DEG, 0.5)

    def test_coverage(self):
        self.assertEqual(EVAL.COVERAGE_MIN, 0.95)

    def test_k_candidates(self):
        self.assertIn(-2, EVAL.K_CANDIDATES)
        self.assertIn(2, EVAL.K_CANDIDATES)


if __name__ == "__main__":
    unittest.main()
'''

RED_SUITE = '''\
import unittest


class TestRed(unittest.TestCase):
    def test_always_fails(self):
        self.fail("baseline rojo de juguete")


if __name__ == "__main__":
    unittest.main()
'''


def make_toy_strack(root, evaluator_text=TOY_EVALUATOR, suite_text=TOY_SUITE):
    strack_dir = Path(root) / "strack"
    tests_dir = strack_dir / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")
    (strack_dir / "s_track_eval.py").write_text(
        evaluator_text, encoding="utf-8"
    )
    (tests_dir / "test_toy.py").write_text(suite_text, encoding="utf-8")
    return strack_dir


def mutant_by_name(name):
    for mutant in run_mutants.MUTANTS:
        if mutant.name == name:
            return mutant
    raise AssertionError(f"mutante desconocido: {name}")


class TestApplyMutant(unittest.TestCase):
    def test_apply_replaces_exact_line(self):
        mutant = mutant_by_name("k_cero")
        mutated = run_mutants.apply_mutant(TOY_EVALUATOR, mutant)
        self.assertIn("K_CANDIDATES = (0,)", mutated)
        self.assertNotIn("K_CANDIDATES = (-2, -1, 0, 1, 2)", mutated)

    def test_missing_constant_line_raises(self):
        without = TOY_EVALUATOR.replace("THRESH_PX = 2.0\n", "")
        mutant = mutant_by_name("umbral_relajado")
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(without, mutant)

    def test_duplicated_constant_line_raises(self):
        duplicated = TOY_EVALUATOR + "COVERAGE_MIN = 0.95\n"
        mutant = mutant_by_name("cobertura_ignorada")
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(duplicated, mutant)


class TestRunMutantsOnToy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.strack_dir = make_toy_strack(self._tmp.name)
        self.source = (self.strack_dir / "s_track_eval.py").read_text(
            encoding="utf-8"
        )

    def test_minimal_mutant_dies(self):
        result = run_mutants.run_one_mutant(
            sys.executable, self.strack_dir, self.source,
            mutant_by_name("umbral_relajado"),
        )
        self.assertEqual(result["status"], "MUERTO", result)
        self.assertNotEqual(result["returncode"], 0)

    def test_unchecked_mutant_survives(self):
        survivor = run_mutants.Mutant(
            name="toy_sobrevive",
            replacements=(("DETECTOR_MAX_DEG = 0.1",
                           "DETECTOR_MAX_DEG = 99.0"),),
            minimal=False,
        )
        result = run_mutants.run_one_mutant(
            sys.executable, self.strack_dir, self.source, survivor
        )
        self.assertEqual(result["status"], "SOBREVIVE", result)
        self.assertEqual(result["returncode"], 0)

    def test_missing_constant_line_is_error_not_survival(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "otro",
            evaluator_text=TOY_EVALUATOR.replace("THRESH_PX = 2.0\n", ""),
        )
        source = (strack_dir / "s_track_eval.py").read_text(encoding="utf-8")
        result = run_mutants.run_one_mutant(
            sys.executable, strack_dir, source,
            mutant_by_name("umbral_relajado"),
        )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertIn("THRESH_PX", result["detail"])

    def test_run_all_minimals_die_exit_zero(self):
        exit_code, report = run_mutants.run_all(
            self.strack_dir, sys.executable
        )
        self.assertTrue(report["baseline"]["ok"], report)
        minimals = [m for m in report["mutants"] if m["minimal"]]
        self.assertEqual(
            {m["name"] for m in minimals},
            {"umbral_relajado", "k_cero", "cobertura_ignorada"},
        )
        for m in minimals:
            self.assertEqual(m["status"], "MUERTO", m)
        self.assertEqual(exit_code, 0, report)
        self.assertTrue(report["ok"])

    def test_red_baseline_is_error_and_stops(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "rojo", suite_text=RED_SUITE
        )
        exit_code, report = run_mutants.run_all(strack_dir, sys.executable)
        self.assertEqual(exit_code, 2, report)
        self.assertFalse(report["baseline"]["ok"])
        self.assertEqual(report["mutants"], [])
        self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
