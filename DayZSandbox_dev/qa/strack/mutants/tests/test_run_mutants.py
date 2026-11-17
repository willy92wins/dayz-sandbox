"""Tests de juguete para run_mutants.py (unittest, solo stdlib).

Crea un evaluador y una suite de juguete en un tmpdir: la suite carga
el evaluador desde STRACK_EVAL_PATH y detecta las constantes que los
mutantes minimos tocan.
"""

import contextlib
import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
TEMPLATE_SOURCE = "marca"
USE_MASK = True
THRESH_SUAVE_FRAC = 0.02
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

    def test_template_source(self):
        self.assertEqual(EVAL.TEMPLATE_SOURCE, "marca")

    def test_use_mask(self):
        self.assertEqual(EVAL.USE_MASK, True)

    def test_thresh_suave_frac(self):
        self.assertEqual(EVAL.THRESH_SUAVE_FRAC, 0.02)

    def test_calib_match_min(self):
        self.assertEqual(EVAL.CALIB_MATCH_MIN, 0.99)

    def test_stimulus_factor(self):
        self.assertEqual(EVAL.STIMULUS_FACTOR, 3.0)

    def test_detector_max_px(self):
        self.assertEqual(EVAL.DETECTOR_MAX_PX, 0.5)


if __name__ == "__main__":
    unittest.main()
'''

MINIMAL_ONLY_SUITE = '''\
"""Suite que mata los minimos pero no los extras."""
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

    def test_template_source(self):
        self.assertEqual(EVAL.TEMPLATE_SOURCE, "marca")

    def test_use_mask(self):
        self.assertEqual(EVAL.USE_MASK, True)

    def test_thresh_suave_frac(self):
        self.assertEqual(EVAL.THRESH_SUAVE_FRAC, 0.02)


if __name__ == "__main__":
    unittest.main()
'''

SETUPCLASS_FAIL_SUITE = '''\
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


class TestSetupClassFail(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError("fallo en setUpClass")

    def test_thresh_px(self):
        self.assertEqual(EVAL.THRESH_PX, 2.0)


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

SETUP_INSTANCE_FAIL_SUITE = '''\
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


class TestSetupInstanceFail(unittest.TestCase):
    def setUp(self):
        raise RuntimeError("recurso de preparacion ausente")

    def test_thresh_px(self):
        self.assertEqual(EVAL.THRESH_PX, 2.0)


class TestOtherPasses2(unittest.TestCase):
    def test_other_passes(self):
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
'''

TEARDOWN_FAIL_SUITE = '''\
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


class TestTeardownFail(unittest.TestCase):
    def tearDown(self):
        raise RuntimeError("fallo en tearDown")

    def test_thresh_px(self):
        self.assertEqual(EVAL.THRESH_PX, 2.0)


if __name__ == "__main__":
    unittest.main()
'''

RESOURCE_SUITE = '''\
import importlib.util
import os
import unittest
from pathlib import Path


def _load_eval():
    path = os.environ["STRACK_EVAL_PATH"]
    spec = importlib.util.spec_from_file_location("toy_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVAL = _load_eval()


class TestNeedsSiblingResource(unittest.TestCase):
    def setUp(self):
        recurso = Path(os.environ["STRACK_EVAL_PATH"]).parent / "recurso.txt"
        self.data = recurso.read_text(encoding="utf-8")

    def test_thresh_px(self):
        self.assertEqual(EVAL.THRESH_PX, 2.0)

    def test_template_source(self):
        self.assertEqual(EVAL.TEMPLATE_SOURCE, "marca")

    def test_use_mask(self):
        self.assertEqual(EVAL.USE_MASK, True)

    def test_thresh_suave_frac(self):
        self.assertEqual(EVAL.THRESH_SUAVE_FRAC, 0.02)

    def test_coverage(self):
        self.assertEqual(EVAL.COVERAGE_MIN, 0.95)

    def test_k_candidates(self):
        self.assertIn(2, EVAL.K_CANDIDATES)

    def test_thresh_roll(self):
        self.assertEqual(EVAL.THRESH_ROLL_DEG, 0.5)

    def test_calib_match_min(self):
        self.assertEqual(EVAL.CALIB_MATCH_MIN, 0.99)

    def test_stimulus_factor(self):
        self.assertEqual(EVAL.STIMULUS_FACTOR, 3.0)

    def test_detector_max_px(self):
        self.assertEqual(EVAL.DETECTOR_MAX_PX, 0.5)


if __name__ == "__main__":
    unittest.main()
'''


# Vuelta 3 BLOQ1: imprime un nombre que no es un test y falla en setUpClass;
# el otro test pasa. El texto libre no debe fabricar un killed_by.
FIXTURE_MISSING_SUITE = '''\
import sys
import unittest


class TestFixtureMissing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("ERROR: fixture_missing", file=sys.stderr)
        raise RuntimeError("fixture_missing")

    def test_never_runs(self):
        self.assertTrue(True)


class TestOtherPasses(unittest.TestCase):
    def test_other_passes(self):
        self.assertTrue(True)


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

    def test_new_mutants_are_minimal_with_exact_lines(self):
        expected = {
            "plantilla_en_proyeccion": (
                ('TEMPLATE_SOURCE = "marca"', 'TEMPLATE_SOURCE = "proyeccion"'),
            ),
            "mascara_ignorada": (("USE_MASK = True", "USE_MASK = False"),),
            "umbral_suave_5pc": (
                ("THRESH_SUAVE_FRAC = 0.02", "THRESH_SUAVE_FRAC = 0.05"),
            ),
        }
        for name, replacements in expected.items():
            mutant = mutant_by_name(name)
            self.assertTrue(mutant.minimal, name)
            self.assertEqual(mutant.replacements, replacements, name)
            mutated = run_mutants.apply_mutant(TOY_EVALUATOR, mutant)
            self.assertIn(replacements[0][1], mutated)
            self.assertNotIn(replacements[0][0], mutated)

    def test_no_free_text_killing_parser(self):
        # Vuelta 3: los fallos no salen del texto libre del log.
        self.assertFalse(hasattr(run_mutants, "parse_killing_tests"))

    # BLOQ2: sustitucion por subcadena
    def test_comment_substring_is_not_a_match(self):
        text = TOY_EVALUATOR.replace(
            "USE_MASK = True\n", "USE_MASK = bool(1)\n# USE_MASK = True\n"
        )
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(text, mutant_by_name("mascara_ignorada"))

    def test_prefix_number_is_not_a_match(self):
        text = TOY_EVALUATOR.replace(
            "THRESH_SUAVE_FRAC = 0.02\n", "THRESH_SUAVE_FRAC = 0.025\n"
        )
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(
                text, mutant_by_name("umbral_suave_5pc")
            )

    def test_indented_line_is_not_a_match(self):
        text = TOY_EVALUATOR.replace(
            "USE_MASK = True\n", "  USE_MASK = True\n"
        )
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(text, mutant_by_name("mascara_ignorada"))

    def test_comment_plus_active_line_replaces_only_active(self):
        text = "# USE_MASK = True\n" + TOY_EVALUATOR
        mutated = run_mutants.apply_mutant(
            text, mutant_by_name("mascara_ignorada")
        )
        self.assertIn("# USE_MASK = True\n", mutated)
        self.assertIn("\nUSE_MASK = False\n", mutated)
        # La unica linea activa exacta desaparece; queda solo el comentario.
        active = [
            ln for ln in mutated.splitlines() if ln == "USE_MASK = True"
        ]
        self.assertEqual(active, [])

    # Vuelta 3 BLOQ2: ast, no texto libre
    def test_multiline_string_plus_bool_assign_is_not_a_match(self):
        text = TOY_EVALUATOR.replace(
            "USE_MASK = True\n",
            'NOTES = """\nUSE_MASK = True\n"""\nUSE_MASK = bool(1)\n',
        )
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(text, mutant_by_name("mascara_ignorada"))

    def test_second_assign_to_same_constant_is_error(self):
        text = TOY_EVALUATOR + "USE_MASK = False\n"
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(text, mutant_by_name("mascara_ignorada"))

    def test_multiline_string_occurrence_alone_is_error(self):
        text = TOY_EVALUATOR.replace(
            "USE_MASK = True\n",
            'NOTES = """\nUSE_MASK = True\n"""\n',
        )
        with self.assertRaises(run_mutants.MutationError):
            run_mutants.apply_mutant(text, mutant_by_name("mascara_ignorada"))


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

    def test_new_minimal_mutants_die_with_killed_by(self):
        cases = {
            "plantilla_en_proyeccion": "test_template_source",
            "mascara_ignorada": "test_use_mask",
            "umbral_suave_5pc": "test_thresh_suave_frac",
        }
        for name, test_name in cases.items():
            result = run_mutants.run_one_mutant(
                sys.executable, self.strack_dir, self.source,
                mutant_by_name(name),
            )
            self.assertEqual(result["status"], "MUERTO", result)
            self.assertTrue(
                any(k.endswith("." + test_name) for k in result["killed_by"]),
                result,
            )

    def test_new_mutant_not_applicable_is_error_not_survival(self):
        cases = {
            "plantilla_en_proyeccion": 'TEMPLATE_SOURCE = "marca"\n',
            "mascara_ignorada": "USE_MASK = True\n",
            "umbral_suave_5pc": "THRESH_SUAVE_FRAC = 0.02\n",
        }
        for name, line in cases.items():
            strack_dir = make_toy_strack(
                Path(self._tmp.name) / f"sin_{name}",
                evaluator_text=TOY_EVALUATOR.replace(line, ""),
            )
            source = (strack_dir / "s_track_eval.py").read_text(
                encoding="utf-8"
            )
            result = run_mutants.run_one_mutant(
                sys.executable, strack_dir, source, mutant_by_name(name)
            )
            self.assertEqual(result["status"], "ERROR", result)
            self.assertEqual(result["killed_by"], [], result)

    def test_run_all_minimals_die_exit_zero(self):
        exit_code, report = run_mutants.run_all(
            self.strack_dir, sys.executable
        )
        self.assertTrue(report["baseline"]["ok"], report)
        minimals = [m for m in report["mutants"] if m["minimal"]]
        self.assertEqual(
            {m["name"] for m in minimals},
            {
                "umbral_relajado", "k_cero", "cobertura_ignorada",
                "plantilla_en_proyeccion", "mascara_ignorada",
                "umbral_suave_5pc",
            },
        )
        for m in minimals:
            self.assertEqual(m["status"], "MUERTO", m)
            self.assertTrue(m["killed_by"], m)
        self.assertEqual(exit_code, 0, report)
        self.assertTrue(report["ok"])

    # BLOQ1: MUERTO sin test que falle
    def test_setupclass_failure_is_error_not_muerto(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "setupclass",
            suite_text=SETUPCLASS_FAIL_SUITE,
        )
        source = (strack_dir / "s_track_eval.py").read_text(encoding="utf-8")
        result = run_mutants.run_one_mutant(
            sys.executable, strack_dir, source,
            mutant_by_name("umbral_relajado"),
        )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)

    def test_exit2_without_unittest_results_is_error(self):
        structured = {"testsRun": None, "failures": [], "errors": []}
        with mock.patch.object(
            run_mutants, "run_suite",
            return_value=(2, "usage: error\n", structured),
        ):
            result = run_mutants.run_one_mutant(
                sys.executable, self.strack_dir, self.source,
                mutant_by_name("k_cero"),
            )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)
        self.assertIsNone(result["tests_run"], result)

    def test_zero_tests_run_is_error(self):
        structured = {
            "testsRun": 0, "failures": [],
            "errors": [{
                "id": "setUpClass (tests.test_toy.TestX)",
                "kind": "setup_class", "is_setup_error": True,
            }],
        }
        with mock.patch.object(
            run_mutants, "run_suite", return_value=(1, "", structured)
        ):
            result = run_mutants.run_one_mutant(
                sys.executable, self.strack_dir, self.source,
                mutant_by_name("k_cero"),
            )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)

    def test_failure_already_in_baseline_is_not_muerto(self):
        tid = "tests.test_toy.TestToyEval.test_thresh_px"
        structured = {
            "testsRun": 7,
            "failures": [{"id": tid, "kind": "test",
                          "is_setup_error": False}],
            "errors": [],
        }
        with mock.patch.object(
            run_mutants, "run_suite", return_value=(1, "", structured)
        ):
            result = run_mutants.run_one_mutant(
                sys.executable, self.strack_dir, self.source,
                mutant_by_name("umbral_relajado"),
                baseline_killed_by=[tid],
            )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)

    def test_named_failure_not_in_baseline_is_muerto(self):
        tid = "tests.test_toy.TestToyEval.test_thresh_px"
        structured = {
            "testsRun": 7,
            "failures": [{"id": tid, "kind": "test",
                          "is_setup_error": False, "body_kill": True}],
            "errors": [],
        }
        with mock.patch.object(
            run_mutants, "run_suite", return_value=(1, "", structured)
        ):
            result = run_mutants.run_one_mutant(
                sys.executable, self.strack_dir, self.source,
                mutant_by_name("umbral_relajado"),
                baseline_killed_by=[],
            )
        self.assertEqual(result["status"], "MUERTO", result)
        self.assertEqual(result["killed_by"], [tid], result)

    # Vuelta 3 BLOQ1: runner estructurado, no texto libre
    def test_fixture_missing_setupclass_is_error_not_muerto(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "fixture_missing",
            suite_text=FIXTURE_MISSING_SUITE,
        )
        source = (strack_dir / "s_track_eval.py").read_text(encoding="utf-8")
        result = run_mutants.run_one_mutant(
            sys.executable, strack_dir, source,
            mutant_by_name("umbral_relajado"),
        )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)
        self.assertNotIn("fixture_missing", result["killed_by"], result)
        self.assertGreaterEqual(result["tests_run"], 1, result)

    def test_tests_run_none_is_rejected_as_error(self):
        tid = "tests.test_toy.TestToyEval.test_thresh_px"
        structured = {
            "testsRun": None,
            "failures": [{"id": tid, "kind": "test",
                          "is_setup_error": False}],
            "errors": [],
        }
        with mock.patch.object(
            run_mutants, "run_suite", return_value=(1, "", structured)
        ):
            result = run_mutants.run_one_mutant(
                sys.executable, self.strack_dir, self.source,
                mutant_by_name("umbral_relajado"),
                baseline_killed_by=[],
            )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)
        self.assertIsNone(result["tests_run"], result)

    def test_setup_error_with_passing_test_is_error(self):
        structured = {
            "testsRun": 1, "failures": [],
            "errors": [{
                "id": "setUpClass (tests.test_toy.TestFixtureMissing)",
                "kind": "setup_class", "is_setup_error": True,
            }],
        }
        with mock.patch.object(
            run_mutants, "run_suite", return_value=(1, "", structured)
        ):
            result = run_mutants.run_one_mutant(
                sys.executable, self.strack_dir, self.source,
                mutant_by_name("umbral_relajado"),
            )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)

    # BLOQ4: los extras tambien tienen que morir
    def test_run_all_all_mutants_die_exit_zero(self):
        exit_code, report = run_mutants.run_all(
            self.strack_dir, sys.executable
        )
        self.assertTrue(report["baseline"]["ok"], report)
        self.assertEqual(len(report["mutants"]), len(run_mutants.MUTANTS))
        for m in report["mutants"]:
            self.assertEqual(m["status"], "MUERTO", m)
            self.assertTrue(m["killed_by"], m)
        self.assertEqual(exit_code, 0, report)
        self.assertTrue(report["ok"])

    def test_extra_survivor_blocks_exit_zero(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "extra_vive",
            suite_text=MINIMAL_ONLY_SUITE,
        )
        exit_code, report = run_mutants.run_all(strack_dir, sys.executable)
        self.assertTrue(report["baseline"]["ok"], report)
        extras = [m for m in report["mutants"] if not m["minimal"]]
        self.assertTrue(extras, report)
        self.assertTrue(
            any(m["status"] == "SOBREVIVE" for m in extras), report
        )
        # Aunque los minimos mueran, un extra vivo impide el 0.
        minimals = [m for m in report["mutants"] if m["minimal"]]
        self.assertTrue(
            all(m["status"] == "MUERTO" for m in minimals), report
        )
        self.assertEqual(exit_code, 1, report)
        self.assertFalse(report["ok"])

    # Vuelta 3 MAY: fallo al guardar el informe
    def test_report_write_failure_is_not_exit_zero(self):
        fake_report = {
            "strack_dir": str(self.strack_dir),
            "eval_path": str(self.strack_dir / "s_track_eval.py"),
            "python": sys.executable,
            "baseline": {"ok": True, "returncode": 0,
                         "detail": "suite verde sin mutar",
                         "output_tail": ""},
            "mutants": [{
                "name": "k_cero", "kind": "minimo", "status": "MUERTO",
                "killed_by": ["tests.test_toy.TestToyEval.test_k_candidates"],
                "detail": "muerto",
            }],
            "ok": True,
        }
        buf = io.StringIO()
        with mock.patch.object(
            run_mutants, "run_all", return_value=(0, fake_report)
        ), mock.patch.object(
            Path, "write_text", side_effect=OSError("disco lleno")
        ), contextlib.redirect_stdout(buf), \
                contextlib.redirect_stderr(io.StringIO()):
            code = run_mutants.main(
                ["--strack-dir", str(self.strack_dir)]
            )
        self.assertNotEqual(code, 0)
        self.assertNotIn("RESULTADO: OK", buf.getvalue())

    # Vuelta 4 BLOQ1(b): setUp/tearDown de instancia no es cuerpo de test
    def test_setup_instance_failure_is_error_not_muerto(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "setup_instance",
            suite_text=SETUP_INSTANCE_FAIL_SUITE,
        )
        source = (strack_dir / "s_track_eval.py").read_text(encoding="utf-8")
        result = run_mutants.run_one_mutant(
            sys.executable, strack_dir, source,
            mutant_by_name("umbral_relajado"),
        )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)

    def test_teardown_failure_is_error_not_muerto(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "teardown_instance",
            suite_text=TEARDOWN_FAIL_SUITE,
        )
        source = (strack_dir / "s_track_eval.py").read_text(encoding="utf-8")
        result = run_mutants.run_one_mutant(
            sys.executable, strack_dir, source,
            mutant_by_name("calib_match_cero"),
        )
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)

    # Vuelta 4 BLOQ1(a): control sin mutar con la disposicion del mutante
    def test_control_sin_mutar_recurso_ausente_todos_error(self):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / "recurso_hermano",
            suite_text=RESOURCE_SUITE,
        )
        (strack_dir / "recurso.txt").write_text("dato", encoding="utf-8")
        exit_code, report = run_mutants.run_all(strack_dir, sys.executable)
        self.assertNotEqual(exit_code, 0, report)
        self.assertTrue(report["baseline"]["ok"], report)
        self.assertFalse(report["ok"], report)
        self.assertTrue(report["mutants"], report)
        self.assertTrue(
            all(m["status"] == "ERROR" for m in report["mutants"]), report
        )
        self.assertTrue(
            all(m["killed_by"] == [] for m in report["mutants"]), report
        )
        control = report.get("control") or {}
        self.assertFalse(control.get("ok"), report)

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


# Arbitro del orquestador tras 4 vueltas (S-track-2): la suite sintetica
# con la que Sol reprodujo el BLOQ de la vuelta 4. setUp por alias que
# lanza solo con el mutante, y un addCleanup que falla con AssertionError
# solo con el mutante; los cuerpos de los tests pasan siempre.
SETUP_ALIAS_SUITE = """import importlib.util
import os
import unittest


def _load_eval():
    path = os.environ["STRACK_EVAL_PATH"]
    spec = importlib.util.spec_from_file_location("toy_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVAL = _load_eval()


class SetupAlias(unittest.TestCase):
    def preparar(self):
        if EVAL.THRESH_PX != 2.0:
            raise FileNotFoundError("recurso junto al evaluador original")

    setUp = preparar

    def test_imagen(self):
        self.assertTrue(True)


class CleanupOnly(unittest.TestCase):
    def test_con_limpieza(self):
        def limpiar():
            assert EVAL.THRESH_ROLL_DEG == 0.5, "limpieza ve el mutante"
        self.addCleanup(limpiar)
        self.assertTrue(True)

"""

BODY_ASSERT_SUITE = """import importlib.util
import os
import unittest


def _load_eval():
    path = os.environ["STRACK_EVAL_PATH"]
    spec = importlib.util.spec_from_file_location("toy_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVAL = _load_eval()


class BodyAssert(unittest.TestCase):
    def test_cuerpo(self):
        self.assertEqual(EVAL.THRESH_PX, 2.0)

    def test_subtest(self):
        for value in (2.0,):
            with self.subTest(value=value):
                self.assertEqual(EVAL.THRESH_PX, value)
"""


class TestArbitroFaseDelFallo(unittest.TestCase):
    """Solo es MUERTO un failure del cuerpo del test (arbitro, vuelta 4)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _run(self, name, suite_text, mutant):
        strack_dir = make_toy_strack(
            Path(self._tmp.name) / name, suite_text=suite_text,
        )
        source = (strack_dir / "s_track_eval.py").read_text(encoding="utf-8")
        return run_mutants.run_one_mutant(
            sys.executable, strack_dir, source, mutant_by_name(mutant),
        )

    def test_setup_alias_cleanup_teardown_are_error_not_muerto(self):
        result = self._run("alias", SETUP_ALIAS_SUITE, "umbral_relajado")
        self.assertEqual(result["status"], "ERROR", result)
        self.assertEqual(result["killed_by"], [], result)

    def test_body_assert_and_subtest_are_muerto(self):
        result = self._run("body", BODY_ASSERT_SUITE, "umbral_relajado")
        self.assertEqual(result["status"], "MUERTO", result)
        self.assertTrue(result["killed_by"], result)
        self.assertTrue(
            any(k.endswith("BodyAssert.test_cuerpo") for k in result["killed_by"]),
            result,
        )
