"""Tests de la vuelta 5 (coherencia de timeline) de S-track·2.

H1: toda medida de lo que hace el filtro (orientación a 1/6 s, origen del
salto, referencia de T-suave) va sobre el eje Σdt acumulado de los frames,
no sobre t_ms. t_ms queda solo para medidas de reloj de pared.
"""

import importlib.util
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

STRACK_DIR = Path(__file__).resolve().parents[1]
FIXTURES_MOD_PATH = STRACK_DIR / "fixtures" / "make_fixtures.py"


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_rows(run_dir):
    return [json.loads(l) for l in (Path(run_dir) / "samples.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_rows(run_dir, rows):
    (Path(run_dir) / "samples.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


class TimelineR5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp_root = Path(cls._tmp.name)
        cls.fx = _load_module(FIXTURES_MOD_PATH, "strack_r5_make_fixtures")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _load_eval(self):
        import os
        env_val = os.environ.get("STRACK_EVAL_PATH")
        path = Path(env_val).resolve() if env_val else (STRACK_DIR / "s_track_eval.py").resolve()
        return _load_module(path, "s_track_eval_r5")

    def _rebuild_tramo4(self, rows):
        """Recalcula cam del tramo 4 como el filtro correcto con el dt de cada frame."""
        def _wxyz(q_xyzw):
            return np.array([q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]], dtype=np.float64)
        first4 = next(i for i, r in enumerate(rows) if int(r.get("tramo") or 1) == 4)
        pre = rows[first4 - 1]
        filt_q = _wxyz(pre["cam"]["q"])
        filt_pos = np.array(pre["cam"]["pos"], dtype=np.float64)
        for r in rows:
            if int(r.get("tramo") or 1) != 4:
                continue
            alpha = 1.0 - math.exp(-float(r["dt"]) / 0.3)
            raw_q = _wxyz(r["cam_raw"]["q"])
            raw_pos = np.array(r["cam_raw"]["pos"], dtype=np.float64)
            filt_q = self.fx._slerp(filt_q, raw_q, alpha)
            filt_pos = filt_pos + alpha * (raw_pos - filt_pos)
            fx_, fy_, fz_ = self.fx._quat_to_axes(filt_q)
            r["cam"] = dict(r["cam"], pos=filt_pos.tolist(), x=fx_.tolist(), y=fy_.tolist(), z=fz_.tolist(),
                            q=self.fx._quat_xyzw_from_wxyz(filt_q))

    def test_tiron_real_en_giro_correcto_sin_falso_acuerdo_fps(self):
        # Patrón real de calib_Ha (frames 422-423): dt 8+32 ms frente a
        # Δt_ms 36+5 ms, colocado justo antes del instante 1/6 s de un giro
        # correcto. Las dos cámaras responden bien a su dt; medir la
        # orientación a 1/6 s sobre t_ms las hacía discrepar 1,7° o más.
        mod = self._load_eval()
        base = self.tmp_root / "tiron_giro"
        base.mkdir()
        self.fx._write_suave_run(base, regime=30, mode="ok")
        run60 = self.fx._write_suave_run(base, regime=60, mode="ok")
        rows = _read_rows(run60)
        giro1 = [i for i, r in enumerate(rows) if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        ia, ib = giro1[9], giro1[10]
        orig_t = [float(r["t_ms"]) for r in rows]
        rows[ia]["dt"] = 0.008
        rows[ib]["dt"] = 0.032
        t = orig_t[0]
        for i, r in enumerate(rows):
            if i == 0:
                r["t_ms"] = t
                continue
            paso = orig_t[i] - orig_t[i - 1]
            if i == ia:
                paso = 36.0
            elif i == ib:
                paso = 5.0
            t += paso
            r["t_ms"] = round(t, 3)
        self._rebuild_tramo4(rows)
        _write_rows(run60, rows)
        rep = mod.evaluate(base)
        causas = [r["cause"] for r in rep["results"]]
        self.assertNotIn("suave_fps_agree_exceeded", causas, rep["results"])
        self.assertEqual(rep["decisions"]["suave"]["30"], "PASA", rep["results"])
        self.assertEqual(rep["decisions"]["suave"]["60"], "PASA", rep["results"])
        g1 = [r for r in rep["results"] if r.get("tramo") == "giro+170"]
        self.assertTrue(g1 and all(70.0 < r["orient_1_6_deg"] < 75.0 for r in g1), g1)

    def test_intervalo_carga_fuera_de_fps(self):
        # H2: el intervalo de carga (frames 0→1) queda fuera de N/Σdt en el
        # cálculo de FPS, igual que en check_runs queda fuera de la deriva.
        # Con dt=2 s en el frame 1, contar ese intervalo daría ~52 FPS y un
        # INCONCLUSO fps_regime espurio; la cadencia real es 60 FPS.
        mod = self._load_eval()
        base = self.tmp_root / "carga_fps"
        base.mkdir()
        run_dir = self.fx._write_suave_run(base, regime=60, mode="ok")
        rows = _read_rows(run_dir)
        self.assertEqual((rows[0]["frame"], rows[1]["frame"]), (0, 1))
        rows[1]["dt"] = 2.0
        _write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["60"], "PASA", rep["results"])
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(suave and all(abs(r["fps_measured"] - 60.0) < 1.0 for r in suave), suave[:2])

    def test_dt_compensado_en_salto_se_juzga_contra_el_dt_registrado(self):
        # Arbitraje de la vuelta 5b (B1 fuera de contrato): el filtro usa
        # el dt de cada frame y el mod registra exactamente ese dt
        # (CONTRACT §16), así que el evaluador juzga la cámara contra el
        # reloj que el filtro usó (Σdt). Caso de Sol: dt 30,6667 ms antes
        # del salto y 2,6667 ms en su primer frame, con Δt_ms regular de
        # 16,6667 ms, y cámara rehecha con ese dt registrado. Ya no hay
        # guarda de frontera: el grupo se juzga sobre Σdt y PASA si la
        # cámara sigue al dt registrado. Antes (con la guarda) quedaba
        # INCONCLUSO por intervalo_salto_incoherente.
        mod = self._load_eval()
        base = self.tmp_root / "dt_compensado"
        base.mkdir()
        run_dir = self.fx._write_suave_run(base, regime=60, mode="ok")
        rows = _read_rows(run_dir)
        prev = None
        salto = None
        for i, r in enumerate(rows):
            if int(r.get("tramo") or 1) != 2:
                continue
            lata = (r.get("lata") or {}).get("a")
            if lata is not None and prev is not None and math.dist(lata, prev) > 0.5:
                salto = i
                break
            if lata is not None:
                prev = lata
        self.assertIsNotNone(salto)
        rows[salto - 1]["dt"] = 0.0306667
        rows[salto]["dt"] = 0.0026667
        # Cámara retrasada: filtro de posición rehecho con el dt adulterado.
        smooth_by_tramo = {1: 0.0, 2: 0.3, 3: 0.8, 4: 0.3}
        filt_pos = None
        for r in rows:
            raw_pos = np.array(r["cam_raw"]["pos"], dtype=np.float64)
            smooth = smooth_by_tramo[int(r.get("tramo") or 1)]
            if filt_pos is None:
                filt_pos = raw_pos.copy()
            else:
                alpha = 1.0 if smooth == 0.0 else 1.0 - math.exp(-float(r["dt"]) / smooth)
                filt_pos = filt_pos + alpha * (raw_pos - filt_pos)
            r["cam"] = dict(r["cam"], pos=filt_pos.tolist())
        _write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        s03 = [r for r in rep["results"] if r.get("tramo") == "s03"]
        self.assertTrue(s03, rep["results"])
        self.assertTrue(all(r["verdict"] == "PASA" for r in s03), s03)
        self.assertFalse(any(r["cause"] == "intervalo_salto_incoherente" for r in rep["results"]), rep["results"])
        self.assertEqual(rep["decisions"]["suave"]["60"], "PASA", rep["decisions"])

    def test_acuerdo_fps_pendiente_si_falta_la_referencia_no_certifica_30(self):
        # Vuelta 5b, B2: a 30 FPS la cámara lleva un sesgo de 1° en el
        # primer giro (73,4619° frente a 72,4619° a 1/6 s en el caso de
        # Sol): supera el acuerdo de 0,5° pero no el límite individual de
        # 3,4°. Si la referencia de 60 FPS queda INCONCLUSA por otra causa
        # y la comparación desaparece, el acuerdo queda pendiente y el
        # régimen de 30 no puede certificarse PASA. Antes: 30 PASA.
        mod = self._load_eval()
        base = self.tmp_root / "acuerdo_pendiente"
        base.mkdir()
        run30 = self.fx._write_suave_run(base, regime=30, mode="ok")
        run60 = self.fx._write_suave_run(base, regime=60, mode="ok")
        # Sesgo de +1° en la cámara de 30 durante los primeros 0,5 s del giro 1.
        rows30 = _read_rows(run30)
        giro1_30 = [i for i, r in enumerate(rows30)
                    if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        q_sesgo = self.fx._rot_to_quat(*self.fx._yaw_axes(1.0))
        for i in giro1_30[:15]:
            cam = rows30[i]["cam"]
            q_xyzw = cam["q"]
            q = np.array([q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]], dtype=np.float64)
            w1, x1, y1, z1 = (float(v) for v in q_sesgo)
            w2, x2, y2, z2 = (float(v) for v in q)
            qn = np.array([
                w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            ], dtype=np.float64)
            qn = qn / np.linalg.norm(qn)
            fx_, fy_, fz_ = self.fx._quat_to_axes(qn)
            rows30[i]["cam"] = dict(cam, x=fx_.tolist(), y=fy_.tolist(), z=fz_.tolist(),
                                    q=self.fx._quat_xyzw_from_wxyz(qn))
        _write_rows(run30, rows30)
        # La referencia de 60 queda INCONCLUSA por otra causa: sin
        # observación válida en un frame del giro+170.
        rows60 = _read_rows(run60)
        giro1_60 = [i for i, r in enumerate(rows60)
                    if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        rows60[giro1_60[0]]["cam"] = dict(rows60[giro1_60[0]]["cam"], pos=None)
        _write_rows(run60, rows60)
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["60"], "INCONCLUSO", rep["results"])
        self.assertNotEqual(rep["decisions"]["suave"]["30"], "PASA", rep["decisions"])
        self.assertEqual(rep["decisions"]["suave"]["30"], "INCONCLUSO", rep["decisions"])
        filas30 = [r for r in rep["results"] if r.get("regime") == "30"]
        self.assertTrue(any(r["cause"] == "suave_fps_agree_pendiente" for r in filas30), filas30)

    def test_desacuerdo_demostrado_no_se_borra_por_tercer_regimen_incompleto(self):
        # Vuelta 5c, N1 (escenario exacto de Sol v3): sesgo de +1° en los
        # frames 915–929 de suave30_Hb (primeros 0,5 s de giro+170, aquí
        # los 15 primeros frames del giro 1 a 30 FPS) y cam.pos=null solo
        # en el frame 4392 de suave144_Hb (primer frame de ese giro, aquí
        # el primer frame del giro 1 a 144 FPS). A 1/6 s: 73,4619° frente
        # a 72,4619° (> 0,5°). El desacuerdo ya demostrado entre 30 y 60
        # conserva FALLA en ambos; solo 144 queda INCONCLUSO. Antes:
        # INCONCLUSO / INCONCLUSO / INCONCLUSO con código 2.
        mod = self._load_eval()
        base = self.tmp_root / "desacuerdo_con_tercero_incompleto"
        base.mkdir()
        run30 = self.fx._write_suave_run(base, regime=30, mode="ok")
        self.fx._write_suave_run(base, regime=60, mode="ok")
        run144 = self.fx._write_suave_run(base, regime=144, mode="ok")
        rows30 = _read_rows(run30)
        giro1_30 = [i for i, r in enumerate(rows30)
                    if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        q_sesgo = self.fx._rot_to_quat(*self.fx._yaw_axes(1.0))
        for i in giro1_30[:15]:
            cam = rows30[i]["cam"]
            q_xyzw = cam["q"]
            q = np.array([q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]], dtype=np.float64)
            w1, x1, y1, z1 = (float(v) for v in q_sesgo)
            w2, x2, y2, z2 = (float(v) for v in q)
            qn = np.array([
                w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            ], dtype=np.float64)
            qn = qn / np.linalg.norm(qn)
            fx_, fy_, fz_ = self.fx._quat_to_axes(qn)
            rows30[i]["cam"] = dict(cam, x=fx_.tolist(), y=fy_.tolist(), z=fz_.tolist(),
                                    q=self.fx._quat_xyzw_from_wxyz(qn))
        _write_rows(run30, rows30)
        rows144 = _read_rows(run144)
        giro1_144 = [i for i, r in enumerate(rows144)
                     if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        rows144[giro1_144[0]]["cam"] = dict(rows144[giro1_144[0]]["cam"], pos=None)
        _write_rows(run144, rows144)
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["30"], "FALLA", rep["decisions"])
        self.assertEqual(rep["decisions"]["suave"]["60"], "FALLA", rep["decisions"])
        self.assertEqual(rep["decisions"]["suave"]["144"], "INCONCLUSO", rep["decisions"])
        self.assertEqual(rep["exit_code"], 1, rep["decisions"])
        causas30 = [r["cause"] for r in rep["results"] if r.get("regime") == "30"]
        causas60 = [r["cause"] for r in rep["results"] if r.get("regime") == "60"]
        self.assertIn("suave_fps_agree_exceeded", causas30, rep["results"])
        self.assertIn("suave_fps_agree_exceeded", causas60, rep["results"])


if __name__ == "__main__":
    unittest.main()
