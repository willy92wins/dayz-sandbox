"""T-suave, acuerdo entre fps con la rotacion relativa al inicio de cada giro (arbitro 27-nov; contrato §37).
Rumbos de partida distintos y el mismo filtro -> PASA; tau distinto en el tramo 4 (registrado tal cual) -> FALLA."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

STRACK_DIR = Path(__file__).resolve().parents[1]


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _eval():
    p = os.environ.get("STRACK_EVAL_PATH")
    return _load(Path(p).resolve() if p else STRACK_DIR / "s_track_eval.py", "s_track_eval_rel")


class SuaveRelativo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fx = _load(STRACK_DIR / "fixtures" / "make_fixtures.py", "strack_fx_rel")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)

    def test_rumbos_distintos_mismo_filtro_pasa(self):
        self.fx._write_suave_run(self.base, regime=30, mode="ok", base_yaw=0.0)
        self.fx._write_suave_run(self.base, regime=60, mode="ok", base_yaw=75.0)
        rep = _eval().evaluate(self.base)
        self.assertEqual(rep["decisions"]["suave"]["30"], "PASA", rep["results"])
        self.assertEqual(rep["decisions"]["suave"]["60"], "PASA", rep["results"])

    def test_tau_distinto_falla_por_el_acuerdo(self):
        self.fx._write_suave_run(self.base, regime=30, mode="ok", base_yaw=0.0)
        self.fx._write_suave_run(self.base, regime=60, mode="ok", base_yaw=75.0, smooth4=0.45)
        rep = _eval().evaluate(self.base)
        causas = {r.get("cause") for r in rep["results"] if r.get("measure") == "T-suave"}
        self.assertEqual(rep["decisions"]["suave"]["60"], "FALLA", rep["results"])
        self.assertIn("suave_fps_agree_exceeded", causas)


if __name__ == "__main__":
    unittest.main()
