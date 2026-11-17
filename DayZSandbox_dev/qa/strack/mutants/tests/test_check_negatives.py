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


SCHEMA2_RUNS = (
    "mount0_Ha_delay1",
    "mount0_Hb_delay1",
    "mount0_Hc_delay1",
    "lookat_Ha_delay1",
    "lookat_Hb_delay1",
    "mount0_Hb_roll",
    "suave60_Hb_smooth03",
    "suave60_Hb_quatlerp",
    "suave60_Hb_longarc",
)


def make_informe_schema2(overrides=None, omit=()):
    negativas = []
    for run in SCHEMA2_RUNS:
        if run in omit:
            continue
        inject = run.rsplit("_", 1)[1]
        negativas.append(_negativa(run, inject, "FALLA"))
    for run, got in (overrides or {}).items():
        for entry in negativas:
            if entry["run"] == run:
                entry["got"] = got
                entry["ok"] = got == "FALLA"
    return {
        "schema": 2,
        "calib": {},
        "detector": {"p95_px": 0.1, "p95_deg": 0.01, "verdict": "PASA"},
        "results": [],
        "decisions": {
            "lectura": "a", "hook_por_modo": {}, "k": {},
            "ropa": {}, "suave": {},
        },
        "negativas": negativas,
        "exit_code": 0,
    }


class TestCheckInformeSchema2(unittest.TestCase):
    def test_schema2_runs_match_contract(self):
        self.assertEqual(
            check_negatives.SCHEMA2_NEGATIVE_RUNS, SCHEMA2_RUNS
        )
        self.assertEqual(len(check_negatives.SCHEMA2_NEGATIVE_RUNS), 9)

    def test_todas_falla_exit_cero(self):
        code, rows = check_negatives.check_informe(make_informe_schema2())
        self.assertEqual(code, 0, rows)
        self.assertEqual(len(rows), 9, rows)
        self.assertTrue(all(r["status"] == "OK" for r in rows))

    def test_una_pasa_exit_uno(self):
        informe = make_informe_schema2(
            overrides={"suave60_Hb_quatlerp": "PASA"}
        )
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)
        bad = [r for r in rows if r["status"] == "MAL_VEREDICTO"]
        self.assertEqual([r["run"] for r in bad], ["suave60_Hb_quatlerp"])

    def test_una_inconcluso_exit_uno(self):
        informe = make_informe_schema2(
            overrides={"mount0_Hb_roll": "INCONCLUSO"}
        )
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)

    def test_una_ausente_exit_uno(self):
        informe = make_informe_schema2(omit={"suave60_Hb_longarc"})
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)
        missing = [r for r in rows if r["status"] == "FALTA"]
        self.assertEqual([r["run"] for r in missing], ["suave60_Hb_longarc"])


    # BLOQ3: metadatos contradictorios / duplicadas (por run completo)
    def test_inject_no_casa_con_run_mas_duplicada_exit_uno(self):
        # 8 buenas (todas menos longarc) + novena run=quatlerp
        # inject=longarc: por (caso,hook,inject) tapaba longarc.
        informe = make_informe_schema2(omit={"suave60_Hb_longarc"})
        informe["negativas"].append(
            _negativa("suave60_Hb_quatlerp", "longarc", "FALLA")
        )
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)
        by_run = {r["run"]: r for r in rows}
        self.assertNotEqual(
            by_run["suave60_Hb_longarc"]["status"], "OK", rows
        )
        self.assertNotEqual(
            by_run["suave60_Hb_quatlerp"]["status"], "OK", rows
        )

    def test_inject_no_casa_sufijo_exit_uno_con_motivo(self):
        informe = make_informe_schema2()
        for entry in informe["negativas"]:
            if entry["run"] == "suave60_Hb_quatlerp":
                entry["inject"] = "longarc"
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)
        row = [r for r in rows if r["run"] == "suave60_Hb_quatlerp"][0]
        self.assertEqual(row["status"], "INJECT_NO_CASA", rows)

    def test_corrida_duplicada_exit_uno(self):
        informe = make_informe_schema2()
        informe["negativas"].append(
            _negativa("suave60_Hb_quatlerp", "quatlerp", "FALLA")
        )
        code, rows = check_negatives.check_informe(informe)
        self.assertEqual(code, 1, rows)
        row = [r for r in rows if r["run"] == "suave60_Hb_quatlerp"][0]
        self.assertEqual(row["status"], "DUPLICADA", rows)

    # Vuelta 3 BLOQ3: inject ausente, null o "" no pasa
    def test_inject_ausente_null_o_vacio_exit_uno(self):
        for mode in ("ausente", "null", "vacio"):
            with self.subTest(mode=mode):
                informe = make_informe_schema2()
                for entry in informe["negativas"]:
                    if entry["run"] == "suave60_Hb_quatlerp":
                        if mode == "ausente":
                            del entry["inject"]
                        elif mode == "null":
                            entry["inject"] = None
                        else:
                            entry["inject"] = ""
                code, rows = check_negatives.check_informe(informe)
                self.assertEqual(code, 1, rows)
                row = [
                    r for r in rows if r["run"] == "suave60_Hb_quatlerp"
                ][0]
                self.assertEqual(row["status"], "INJECT_NO_CASA", rows)


    # Vuelta 4 BLOQ2: expected ausente, null o distinto de "FALLA"
    def test_expected_ausente_null_o_distinto_exit_uno(self):
        for mode in ("ausente", "null", "distinto"):
            with self.subTest(mode=mode):
                informe = make_informe_schema2()
                for entry in informe["negativas"]:
                    if entry["run"] == "suave60_Hb_quatlerp":
                        if mode == "ausente":
                            del entry["expected"]
                        elif mode == "null":
                            entry["expected"] = None
                        else:
                            entry["expected"] = "PASA"
                code, rows = check_negatives.check_informe(informe)
                self.assertEqual(code, 1, rows)
                row = [
                    r for r in rows if r["run"] == "suave60_Hb_quatlerp"
                ][0]
                self.assertNotEqual(row["status"], "OK", rows)


class TestCheckNegativesMainSchema2(unittest.TestCase):
    def _write(self, informe):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "informe.json"
        path.write_text(json.dumps(informe), encoding="utf-8")
        return path

    def test_main_schema2_cumple(self):
        path = self._write(make_informe_schema2())
        self.assertEqual(check_negatives.main([str(path)]), 0)

    def test_main_schema2_inconcluso_exit_uno(self):
        path = self._write(make_informe_schema2(
            overrides={"mount0_Ha_delay1": "INCONCLUSO"}
        ))
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_schema2_ausente_exit_uno(self):
        path = self._write(make_informe_schema2(omit={"lookat_Hb_delay1"}))
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_schema2_inject_contradictorio_exit_uno(self):
        informe = make_informe_schema2(omit={"suave60_Hb_longarc"})
        informe["negativas"].append(
            _negativa("suave60_Hb_quatlerp", "longarc", "FALLA")
        )
        path = self._write(informe)
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_schema2_duplicada_exit_uno(self):
        informe = make_informe_schema2()
        informe["negativas"].append(
            _negativa("mount0_Ha_delay1", "delay1", "FALLA")
        )
        path = self._write(informe)
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_schema2_inject_ausente_exit_uno(self):
        informe = make_informe_schema2()
        for entry in informe["negativas"]:
            if entry["run"] == "mount0_Ha_delay1":
                del entry["inject"]
        path = self._write(informe)
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_schema2_expected_ausente_exit_uno(self):
        informe = make_informe_schema2()
        for entry in informe["negativas"]:
            if entry["run"] == "mount0_Ha_delay1":
                del entry["expected"]
        path = self._write(informe)
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_schema2_expected_distinto_exit_uno(self):
        informe = make_informe_schema2()
        for entry in informe["negativas"]:
            if entry["run"] == "mount0_Ha_delay1":
                entry["expected"] = "PASA"
        path = self._write(informe)
        self.assertEqual(check_negatives.main([str(path)]), 1)

    def test_main_schema2_inject_vacio_exit_uno(self):
        informe = make_informe_schema2()
        for entry in informe["negativas"]:
            if entry["run"] == "mount0_Ha_delay1":
                entry["inject"] = ""
        path = self._write(informe)
        self.assertEqual(check_negatives.main([str(path)]), 1)


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
