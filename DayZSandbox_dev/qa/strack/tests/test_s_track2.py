"""Tests offline de S-track·2 (brief §4, CONTRACT §6-§15).

Cargan el evaluador desde STRACK_EVAL_PATH si existe, como los demas tests.
Fixtures nuevas del brief §4: sesgo constante de 5 px, fondo cambiante,
exponencial de T-suave (correcta / smooth cambiado / QuatLerp / arco largo),
pocas capturas y T-ropa.
"""

import importlib.util
import json
import math
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

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
    return Path(env_val).resolve() if env_val else DEFAULT_EVAL_PATH.resolve()


class STrack2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp_root = Path(cls._tmp.name)
        cls.fx = _load_module(FIXTURES_MOD_PATH, "strack2_make_fixtures")
        cls.dirs = {}
        for kind in ("sesgo5", "fondo_cambiante", "suave_ok", "suave_smooth", "suave_quatlerp", "suave_longarc", "suave_frac35", "suave_entrada_desfasada", "suave_reset_tramo", "ropa_ok", "ropa_falla", "pocas_capturas", "s2_completo"):
            cls.dirs[kind] = cls.fx.generate_fixture(cls.tmp_root / kind, kind=kind)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _load_eval(self):
        return _load_module(_eval_path(), "s_track_eval_target2")

    def test_sesgo_constante_5px_tlect_falla(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["sesgo5"])
        self.assertEqual(rep["schema"], 2)
        tmarca_a = [r for r in rep["results"] if r["measure"] == "T-marca" and r["reading"] == "a"]
        self.assertTrue(tmarca_a, rep["results"][:3])
        self.assertTrue(any(r["verdict"] == "FALLA" and r["p95_px"] > mod.THRESH_PX for r in tmarca_a), tmarca_a)
        tlect_a = [r for r in rep["results"] if r["measure"] == "T-lect" and r["reading"] == "a"]
        self.assertTrue(any(r["verdict"] == "FALLA" for r in tlect_a), tlect_a)
        self.assertNotEqual(rep["decisions"]["lectura"], "a")

    def test_marcas_invalidas_se_descartan(self):
        mod = self._load_eval()
        run_dir = self.dirs["sesgo5"] / "mount0_Ha"
        valid, discarded = mod.load_marcas(self.dirs["sesgo5"] / "marcas", "mount0_Ha", run_dir)
        self.assertGreaterEqual(len(valid), 1)
        self.assertEqual(discarded, [])
        # Una marca con sha corrupto no vale.
        bad_dir = self.tmp_root / "marcas_bad"
        bad_dir.mkdir(exist_ok=True)
        data = json.loads((self.dirs["sesgo5"] / "marcas" / "mount0_Ha.json").read_text(encoding="utf-8"))
        data["marcas"][0]["sha256"] = "0" * 64
        (bad_dir / "mount0_Ha.json").write_text(json.dumps(data), encoding="utf-8")
        valid2, discarded2 = mod.load_marcas(bad_dir, "mount0_Ha", run_dir)
        self.assertTrue(any(d["cause"] == "sha256_mismatch" for d in discarded2))
        self.assertLess(len(valid2), len(valid))

    def test_fondo_cambiante_con_mascara_pasa_sin_mascara_falla(self):
        mod = self._load_eval()
        fondo = self.dirs["fondo_cambiante"] / "fondo_cambiante"
        truth = json.loads((fondo / "truth.json").read_text(encoding="utf-8"))
        src = mod._load_gray(fondo / "source.bmp")
        tgt = mod._load_gray(fondo / "target.bmp")
        mask = np.asarray(Image.open(fondo / "mascara.png").convert("L")) > 0
        sx, sy = truth["source_center"]
        tx, ty = truth["target_center"]
        # Con mascara (USE_MASK del modulo): el detector acierta el centro real.
        self.assertTrue(mod.USE_MASK)
        bank_masked = mod.make_template_bank(src, sx, sy, mask=mask)
        det_m = mod.detect_template_bank(tgt, bank_masked, tx, ty, search_radius=40)
        self.assertIsNotNone(det_m)
        err_m = math.hypot(det_m[0] - tx, det_m[1] - ty)
        self.assertLessEqual(err_m, 1.0, f"masked err={err_m} det={det_m}")
        self.assertGreaterEqual(det_m[2], mod.CORR_MIN)
        # Sin mascara: el anillo engana y el detector falla (o no detecta con CORR_MIN).
        bank_plain = mod.make_template_bank(src, sx, sy, mask=None)
        det_p = mod.detect_template_bank(tgt, bank_plain, tx, ty, search_radius=40)
        plain_fails = det_p is None or det_p[2] < mod.CORR_MIN or math.hypot(det_p[0] - tx, det_p[1] - ty) > 5.0
        self.assertTrue(plain_fails, f"unmasked det={det_p}")

    def test_suave_exponencial_correcta_pasa(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_ok"])
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(suave)
        self.assertTrue(all(r["verdict"] == "PASA" for r in suave), suave)
        self.assertEqual(rep["decisions"]["suave"]["60"], "PASA")
        for r in suave:
            self.assertLessEqual(r["err_max_frac"], mod.THRESH_SUAVE_FRAC, r)
            self.assertLessEqual(r["quat_norm_dev"], mod.QUAT_NORM_TOL, r)

    def test_suave_smooth_cambiado_falla(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_smooth"])
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(any(r["verdict"] == "FALLA" and r["err_max_frac"] > mod.THRESH_SUAVE_FRAC for r in suave), suave)
        self.assertEqual(rep["decisions"]["suave"]["60"], "FALLA")

    def test_suave_quatlerp_falla_en_giro(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_quatlerp"])
        giros = [r for r in rep["results"] if r["measure"] == "T-suave" and str(r.get("tramo", "")).startswith("giro")]
        self.assertTrue(giros)
        # Hallazgo 12: falla por error angular, con norma valida y arco corto (no por arco largo).
        self.assertTrue(
            any(
                r["verdict"] == "FALLA" and r["cause"] == "suave_orient_exceeded" and r.get("arc") == "corto"
                and r["quat_norm_dev"] <= mod.QUAT_NORM_TOL and r["err_max_frac"] > mod.THRESH_SUAVE_FRAC
                for r in giros
            ),
            giros,
        )

    def test_suave_longarc_falla_en_giro(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_longarc"])
        giros = [r for r in rep["results"] if r["measure"] == "T-suave" and str(r.get("tramo", "")).startswith("giro")]
        self.assertTrue(any(r["verdict"] == "FALLA" and r.get("arc") == "largo" for r in giros), giros)

    def test_pocas_capturas_inconcluso_por_muestreo(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["pocas_capturas"])
        # La negativa de 15 se deriva del positivo S2 recortando solo mount0 (hallazgo 13).
        giro1 = [r for r in rep["results"] if r["window"] == "giro1" and r["run"] == "mount0_Ha" and r["measure"] in ("T-lect", "T-hook")]
        self.assertTrue(giro1)
        self.assertTrue(all(r["verdict"] == "INCONCLUSO" and r["cause"] == "insufficient_sampling" for r in giro1), giro1)
        self.assertTrue(all(r.get("n_shots") == 15 for r in giro1), giro1)
        self.assertEqual(rep["exit_code"], 2)

    def test_mascara_desde_mount0_y_detector_fondo(self):
        mod = self._load_eval()
        d = self.tmp_root / "mask_run"
        d.mkdir()
        rng = np.random.default_rng(3)
        rows = []
        for i in range(55):
            img = (100.0 + rng.normal(0.0, 40.0, size=(220, 220))).astype(np.float32)
            img[90:111, 90:111] = 180.0
            name = f"f{i:06d}.bmp"
            Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), mode="L").save(d / name)
            rows.append({"frame": i, "shot": name, "giro": 1, "cam": {"pos": [0, 0, 0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}, "fov_rad": 1.0471976, "lecturas": {}})
        run = {"dir": d, "run": "mount0_Ha", "caso": "mount0", "hook": "Ha", "inject": "none", "samples": rows, "by_frame": {r["frame"]: r for r in rows}, "has_gaps": False}
        marcas = [{"shot": "f000000.bmp", "puntos": {"usti hlavne": (100.0, 100.0)}, "momento": "giro1", "diff_max_px": 0.0}]
        mask = mod.build_mask_from_run(run, marcas, 0, 684.0)
        self.assertIsNotNone(mask)
        self.assertEqual(mask.shape, (mod.TEMPLATE_PX, mod.TEMPLATE_PX))
        self.assertTrue(bool(mask[24, 24]))
        self.assertFalse(bool(mask[0, 0]))

    def test_suave_fps_regimen_inconcluso(self):
        mod = self._load_eval()
        src = self.dirs["suave_ok"] / "suave60_Hb" / "samples.jsonl"
        d = self.tmp_root / "fps_bad" / "suave60_Hb"
        d.mkdir(parents=True)
        rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
        for r in rows:
            r["dt"] = round(1.0 / 30.0, 6)
        (d / "samples.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        rep = mod.evaluate(self.tmp_root / "fps_bad")
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(suave and all(r["verdict"] == "INCONCLUSO" and r["cause"] == "fps_regime" for r in suave), suave[:2])
        self.assertEqual(rep["decisions"]["suave"]["60"], "INCONCLUSO")

    def test_suave_acuerdo_entre_regimenes(self):
        mod = self._load_eval()
        base = self.tmp_root / "suave_multi"
        base.mkdir()
        self.fx._write_suave_run(base, regime=30, mode="ok")
        self.fx._write_suave_run(base, regime=60, mode="ok")
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["30"], "PASA", rep["results"])
        self.assertEqual(rep["decisions"]["suave"]["60"], "PASA", rep["results"])

    def test_ropa_falla_no_sigue(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["ropa_falla"])
        self.assertEqual(rep["decisions"]["ropa"]["mochila"], "no_sigue", rep["results"])

    def test_negativas_suave_salen_falla(self):
        mod = self._load_eval()
        base = self.tmp_root / "suave_neg"
        base.mkdir()
        self.fx._write_suave_run(base, regime=60, mode="smooth_changed", inject="smooth03")
        self.fx._write_suave_run(base, regime=60, mode="quatlerp", inject="quatlerp")
        self.fx._write_suave_run(base, regime=60, mode="longarc", inject="longarc")
        rep = mod.evaluate(base)
        self.assertEqual(len(rep["negativas"]), 3, rep["negativas"])
        for neg in rep["negativas"]:
            self.assertEqual(neg["got"], "FALLA", neg)
            self.assertTrue(neg["ok"], neg)
        # Las negativas no cuentan para las decisiones.
        self.assertEqual(rep["results"], [])

    # --- Vuelta 2 (revision de Sol) ---

    def _fake_detector_run(self, name):
        d = self.tmp_root / name
        d.mkdir()
        img = self.fx._slice_background(0.0).copy()
        self.fx._stamp_motif(img, 960.0 - 136.8, 540.0, kind="usti")
        self.fx._stamp_motif(img, 960.0 + 136.8, 540.0, kind="konec")
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGB").save(d / "f000001.png")
        cam = {"pos": [0.0, 0.0, 0.0], "x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}
        row = {"frame": 1, "shot": "f000001.bmp", "hook": "Ha", "caso": "mount0", "inject": "none",
               "cam": cam, "fov_rad": 1.0471976,
               "lecturas": {"usti hlavne": {"a": [-0.2, 0.0, 1.0]}, "konec hlavne": {"a": [0.2, 0.0, 1.0]}}}
        run = {"dir": d, "run": "mount0_Ha", "caso": "mount0", "hook": "Ha", "inject": "none",
               "samples": [row], "by_frame": {1: row}}
        return run

    def _disc_mask(self):
        yy, xx = np.mgrid[0:48, 0:48]
        return ((xx - 23.5) ** 2 + (yy - 23.5) ** 2) <= (16.0 ** 2)

    def test_v2_mascaras_por_detalle_y_vacia_no_cae_a_sin_mascara(self):
        mod = self._load_eval()
        self.assertTrue(hasattr(mod, "build_masks_from_run"), "falta build_masks_from_run")
        d = self.tmp_root / "masks_run"
        d.mkdir()
        rng = np.random.default_rng(11)
        rows = []
        for i in range(55):
            img = (100.0 + rng.normal(0.0, 40.0, size=(300, 500))).astype(np.float32)
            img[90:111, 90:111] = 180.0
            img[90:111, 340:361] = 180.0
            img[190:211, 90:111] = 180.0
            name = f"f{i:06d}.bmp"
            Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), mode="L").save(d / name)
            rows.append({"frame": i, "shot": name, "giro": 1, "cam": {"pos": [0, 0, 0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}, "fov_rad": 1.0471976, "lecturas": {}})
        run = {"dir": d, "run": "mount0_Ha", "caso": "mount0", "hook": "Ha", "inject": "none", "samples": rows, "by_frame": {r["frame"]: r for r in rows}, "has_gaps": False}
        marcas = [{"shot": "f000000.bmp", "puntos": {"usti hlavne": (100.0, 100.0), "konec hlavne": (350.0, 100.0), "mira": (100.0, 200.0)}, "momento": "giro1", "diff_max_px": 0.0}]
        masks = mod.build_masks_from_run(run, marcas, 0, 684.0)
        # Una mascara por detalle, en coordenadas locales 48x48 (boca y recamara a 250 px no se vacian).
        for punto in ("usti hlavne", "konec hlavne", "mira"):
            self.assertIn(punto, masks)
            self.assertEqual(masks[punto].shape, (mod.TEMPLATE_PX, mod.TEMPLATE_PX))
            self.assertTrue(bool(masks[punto][24, 24]), punto)
            self.assertGreater(int(masks[punto].sum()), 4, punto)
        # Mascara vacia: nunca caida silenciosa a deteccion sin mascara.
        img = mod._load_gray(d / "f000000.bmp")
        bank_empty = mod.make_template_bank(img, 100.0, 100.0, mask=np.zeros((48, 48), dtype=bool))
        self.assertTrue(bank_empty == [] or all(t["norm"] <= 1e-5 for t in bank_empty), bank_empty)
        self.assertIsNone(mod.detect_template_bank(img, bank_empty, 100.0, 100.0, search_radius=20))

    def test_v2_calibrate_detector_fondo_subpixel(self):
        mod = self._load_eval()
        run = self._fake_detector_run("v2_bg_subpixel")
        masks = {"usti hlavne": self._disc_mask(), "konec hlavne": self._disc_mask()}
        bgs = [self.fx._slice_background(300.0), self.fx._slice_background(700.0)]
        res = mod.calibrate_detector([run], {"Ha": 0}, {"Ha": 684.0}, template_mask=masks, background_images=bgs)
        self.assertEqual(res["verdict"], "PASA", res)
        self.assertIn("p95_bg_px", res)
        # Sin el -0,5 px artificial del pegado con semiancho 24 y centro redondeado.
        self.assertLessEqual(res["p95_bg_px"], 0.25, res)

    def test_v2_detector_sin_calibracion_de_fondo_inconcluso(self):
        mod = self._load_eval()
        run = self._fake_detector_run("v2_bg_missing")
        self.assertTrue(mod.USE_MASK)
        res = mod.calibrate_detector([run], {"Ha": 0}, {"Ha": 684.0})
        self.assertEqual(res["verdict"], "INCONCLUSO", res)
        self.assertEqual(res.get("cause"), "sin_calibracion_fondo", res)

    def test_v2_minimo_20_tambien_en_ventanas_inferidas(self):
        mod = self._load_eval()
        by_frame = {f: {"shot": "f000000.bmp", "lecturas": {}} for f in range(15)}
        run = {"by_frame": by_frame, "has_gaps": False}
        _p95, _roll, _cov, verdict, cause, n_shots = mod._eval_window_metrics(run, list(range(15)), {}, 0, 684.0, "a")
        self.assertEqual((verdict, cause, n_shots), ("INCONCLUSO", "insufficient_sampling", 15))

    def test_v2_tlect_tmarca_todos_los_casos_y_hook_condicionado(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["s2_completo"])
        for caso in ("mount0", "mount03", "lookat", "follow"):
            self.assertTrue(any(r["measure"] == "T-marca" and r["caso"] == caso for r in rep["results"]), caso)
            self.assertTrue(any(r["measure"] == "T-lect" and r["caso"] == caso for r in rep["results"]), caso)
            self.assertEqual(rep["decisions"]["hook_por_modo"][caso], "Ha", rep["decisions"])
        # Marcas de follow desplazadas: su T-marca falla y Ha ya no gana en follow.
        mpath = self.dirs["s2_completo"] / "marcas" / "follow_Ha.json"
        data = json.loads(mpath.read_text(encoding="utf-8"))
        for entry in data["marcas"]:
            for punto in entry["puntos"]:
                entry["puntos"][punto] = [entry["puntos"][punto][0] + 10.0, entry["puntos"][punto][1]]
        mpath.write_text(json.dumps(data), encoding="utf-8")
        rep2 = mod.evaluate(self.dirs["s2_completo"])
        self.assertTrue(any(r["measure"] == "T-marca" and r["caso"] == "follow" and r["verdict"] == "FALLA" for r in rep2["results"]))
        self.assertIsNone(rep2["decisions"]["hook_por_modo"]["follow"], rep2["decisions"])

    def test_v2_s2_completo_positivo_e_imagenes(self):
        mod = self._load_eval()
        base = self.dirs["s2_completo"]
        for run_dir in sorted(p for p in base.iterdir() if p.is_dir() and (p / "samples.jsonl").is_file()):
            for line in (run_dir / "samples.jsonl").read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("shot"):
                    self.assertTrue((run_dir / row["shot"]).is_file(), row["shot"])
        rep = mod.evaluate(base)
        rows = [r for r in rep["results"] if r["measure"] in ("T-lect", "T-hook")]
        self.assertTrue(rows)
        self.assertTrue(all(int(r.get("n_shots") or 0) >= mod.MIN_SHOTS_WINDOW for r in rows), rows[:4])

    def test_v2_suave_entrada_desfasada_falla(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_entrada_desfasada"])
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(any(r["verdict"] == "FALLA" and r["cause"] == "entrada_desfasada" for r in suave), suave)

    def test_v2_suave_primer_frame_de_tramo_se_comprueba(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_reset_tramo"])
        s03 = [r for r in rep["results"] if r["measure"] == "T-suave" and r.get("tramo") == "s03"]
        self.assertTrue(any(r["verdict"] == "FALLA" for r in s03), s03)

    def test_v2_suave_error_entre_2_y_5_porciento_falla(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_frac35"])
        s03 = [r for r in rep["results"] if r["measure"] == "T-suave" and r.get("tramo") == "s03"]
        self.assertTrue(s03)
        self.assertTrue(
            any(r["verdict"] == "FALLA" and mod.THRESH_SUAVE_FRAC < r["err_max_frac"] < 0.05 for r in s03),
            s03,
        )

    def test_v2_suave_sin_grupos_o_sin_cuaterniones_inconcluso(self):
        mod = self._load_eval()
        # Sin los cinco grupos: solo tramos de posicion.
        base = self.tmp_root / "v2_suave_sin_giros"
        shutil.copytree(self.dirs["suave_ok"] / "suave60_Hb", base / "suave60_Hb")
        spath = base / "suave60_Hb" / "samples.jsonl"
        rows = [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if int(r.get("tramo") or 1) < 4]
        spath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["60"], "INCONCLUSO", rep["results"])
        self.assertTrue(any(r["verdict"] == "INCONCLUSO" and str(r.get("tramo", "")).startswith("giro") for r in rep["results"]))
        # Giro sin cuaterniones validos: nunca PASA.
        base2 = self.tmp_root / "v2_suave_sin_quat"
        shutil.copytree(self.dirs["suave_ok"] / "suave60_Hb", base2 / "suave60_Hb")
        spath2 = base2 / "suave60_Hb" / "samples.jsonl"
        rows2 = [json.loads(l) for l in spath2.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in rows2:
            if int(r.get("tramo") or 1) == 4:
                r["cam"] = {"pos": (r.get("cam") or {}).get("pos")}
                r["cam_raw"] = {"pos": (r.get("cam_raw") or {}).get("pos")}
        spath2.write_text("\n".join(json.dumps(r) for r in rows2) + "\n", encoding="utf-8")
        rep2 = mod.evaluate(base2)
        giros = [r for r in rep2["results"] if str(r.get("tramo", "")).startswith("giro")]
        self.assertTrue(giros and all(r["verdict"] == "INCONCLUSO" for r in giros), giros)

    def test_v2_suave_orient_1_6_desde_antes_del_salto(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["suave_ok"])
        giros = [r for r in rep["results"] if str(r.get("tramo", "")).startswith("giro")]
        self.assertTrue(giros)
        for r in giros:
            # A 1/6 s con smooth 0,3 el avance esperado desde la orientacion previa al salto es ~72 deg.
            self.assertGreater(r["orient_1_6_deg"], 65.0, r)
            self.assertLess(r["orient_1_6_deg"], 85.0, r)

    def test_v2_regimen_inconcluso_por_fps_no_entra_en_acuerdo(self):
        mod = self._load_eval()
        base = self.tmp_root / "v2_regimenes"
        base.mkdir()
        self.fx._write_suave_run(base, regime=30, mode="ok")
        run60 = self.fx._write_suave_run(base, regime=60, mode="ok")
        spath = run60 / "samples.jsonl"
        rows = [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]
        x, y, z = self.fx._yaw_axes(0.0)
        q0 = self.fx._quat_xyzw_from_wxyz(self.fx._rot_to_quat(x, y, z))
        for r in rows:
            r["dt"] = round(1.0 / 30.0, 6)
            r["cam"] = dict(r["cam"], x=x.tolist(), y=y.tolist(), z=z.tolist(), q=q0)
        spath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["30"], "PASA", rep["results"])
        self.assertEqual(rep["decisions"]["suave"]["60"], "INCONCLUSO", rep["results"])

    def test_v2_informe_finito_y_regimenes_ausentes_inconcluso(self):
        mod = self._load_eval()
        out = self.tmp_root / "v2_out_suave"
        rep = mod.evaluate(self.dirs["suave_ok"], out_dir=out)
        text = (out / "informe.json").read_text(encoding="utf-8")
        self.assertNotIn("Infinity", text)
        self.assertNotIn("NaN", text)
        json.loads(text)
        json.dumps(rep, allow_nan=False)
        self.assertEqual(rep["decisions"]["suave"]["30"], "INCONCLUSO", rep["decisions"])
        self.assertTrue(rep["decisions"]["suave_causas"]["30"], rep["decisions"])

    def test_v2_ropa_cobertura_insuficiente_inconcluso(self):
        mod = self._load_eval()
        base = self.tmp_root / "v2_ropa_cobertura"
        shutil.copytree(self.dirs["ropa_ok"], base)
        spath = base / "ropa_Hb" / "samples.jsonl"
        rows = [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]
        for r in rows[1:]:
            r["ropa"] = None
        spath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        rep = mod.evaluate(base)
        ropa = [r for r in rep["results"] if r["measure"] == "T-ropa"]
        self.assertTrue(any(r["verdict"] == "INCONCLUSO" and "cobertura" in r["cause"] for r in ropa), ropa)
        self.assertNotEqual(rep["decisions"]["ropa"]["mochila"], "sigue", rep["decisions"])

    def test_v2_ropa_sin_calibracion_contraste_mira_inconcluso(self):
        mod = self._load_eval()
        base = self.tmp_root / "v2_ropa_sin_calib"
        (base / "ropa_Hb").mkdir(parents=True)
        shutil.copytree(self.dirs["ropa_ok"] / "ropa_Hb", base / "ropa_Hb", dirs_exist_ok=True)
        shutil.copytree(self.dirs["ropa_ok"] / "marcas", base / "marcas")
        rep = mod.evaluate(base)
        mira = [r for r in rep["results"] if r["measure"] == "T-ropa" and r.get("category") == "mira"]
        self.assertTrue(mira)
        self.assertTrue(all(r["verdict"] == "INCONCLUSO" and "calib" in r["cause"] for r in mira), mira)
        # La parte numerica queda como informacion (finitas, no el 999 de ausencia).
        self.assertTrue(all(r["p95_m"] < mod.ROPA_MAX_M for r in mira), mira)
        self.assertIsNone(rep["decisions"]["ropa"]["mira"], rep["decisions"])

    # --- Vuelta 3 (revision de Sol, LAST_v2) ---

    def _copy_suave_ok(self, name):
        base = self.tmp_root / name
        shutil.copytree(self.dirs["suave_ok"], base)
        return base

    def _fresh_s2(self, name):
        base = self.tmp_root / name
        self.fx.generate_fixture(base, kind="s2_completo")
        return base

    @staticmethod
    def _read_rows(run_dir):
        return [json.loads(l) for l in (Path(run_dir) / "samples.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    @staticmethod
    def _write_rows(run_dir, rows):
        (Path(run_dir) / "samples.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def test_v3_suave_sin_cam_pos_tras_salto_inconcluso(self):
        mod = self._load_eval()
        base = self._copy_suave_ok("v3_suave_sin_pos")
        run_dir = base / "suave60_Hb"
        rows = self._read_rows(run_dir)
        jump_times = []
        prev = None
        for r in rows:
            lata = (r.get("lata") or {}).get("a")
            if lata is not None and prev is not None and math.dist(lata, prev) > 0.5:
                jump_times.append(float(r["t_ms"]))
            if lata is not None:
                prev = lata
        for r in rows:
            if any(0.0 <= float(r["t_ms"]) - jt < 500.0 for jt in jump_times):
                r["cam"] = {k: v for k, v in (r.get("cam") or {}).items() if k != "pos"}
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(any(r["verdict"] == "INCONCLUSO" for r in suave), suave)
        self.assertNotEqual(rep["decisions"]["suave"]["60"], "PASA", rep["decisions"])

    def test_v3_suave_sin_q_escrito_no_certifica_norma(self):
        mod = self._load_eval()
        base = self._copy_suave_ok("v3_suave_sin_q")
        run_dir = base / "suave60_Hb"
        rows = self._read_rows(run_dir)
        for r in rows:
            if int(r.get("tramo") or 1) == 4:
                r["cam"] = {k: v for k, v in (r.get("cam") or {}).items() if k != "q"}
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        giros = [r for r in rep["results"] if str(r.get("tramo", "")).startswith("giro")]
        self.assertTrue(giros and all(r["verdict"] == "INCONCLUSO" for r in giros), giros)

    def test_v3_suave_tiempos_irregulares_oraculo_analitico(self):
        mod = self._load_eval()
        base = self._copy_suave_ok("v3_suave_irregular")
        run_dir = base / "suave60_Hb"
        rows = self._read_rows(run_dir)
        giro1 = [i for i, r in enumerate(rows) if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        pattern = [1.0 / 60.0] * 6 + [1.0 / 30.0, 1.0 / 30.0]
        for j, i in enumerate(giro1[:len(pattern)]):
            rows[i]["dt"] = pattern[j]
        # t_ms = final de cada intervalo (contrato §16): recomputar como suma acumulada de dt.
        t_acc = 0.0
        for r in rows:
            t_acc += float(r["dt"])
            r["t_ms"] = round(t_acc * 1000.0, 3)
        # Respuesta correcta para esos dt: simular el filtro (smooth 0,3) frame a frame en el tramo 4.
        def _wxyz(q_xyzw):
            return np.array([q_xyzw[3], q_xyzw[0], q_xyzw[1], q_xyzw[2]], dtype=np.float64)
        pre = rows[giro1[0] - 1]
        filt_q = _wxyz(pre["cam"]["q"])
        for i, r in enumerate(rows):
            if int(r.get("tramo") or 1) != 4:
                continue
            alpha = 1.0 - math.exp(-float(r["dt"]) / 0.3)
            raw_q = _wxyz(r["cam_raw"]["q"])
            filt_q = self.fx._slerp(filt_q, raw_q, alpha)
            fx_, fy_, fz_ = self.fx._quat_to_axes(filt_q)
            r["cam"] = dict(r["cam"], x=fx_.tolist(), y=fy_.tolist(), z=fz_.tolist(), q=self.fx._quat_xyzw_from_wxyz(filt_q))
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        g1 = [r for r in rep["results"] if r.get("tramo") == "giro+170"]
        self.assertTrue(g1 and all(r["verdict"] == "PASA" for r in g1), g1)
        # Oraculo analitico: 170*(1-exp(-(1/6)/0.3)) = 72,46 deg desde la orientacion previa al salto.
        self.assertTrue(all(70.0 < r["orient_1_6_deg"] < 75.0 for r in g1), g1)

    def test_v3_sin_estimulo_no_entra_en_acuerdo(self):
        mod = self._load_eval()
        base = self.tmp_root / "v3_acuerdo_sin_estimulo"
        base.mkdir()
        self.fx._write_suave_run(base, regime=30, mode="ok")
        run60 = self.fx._write_suave_run(base, regime=60, mode="ok")
        rows = self._read_rows(run60)
        x, y, z = self.fx._yaw_axes(0.0)
        q0 = self.fx._quat_xyzw_from_wxyz(self.fx._rot_to_quat(x, y, z))
        for r in rows:
            if int(r.get("tramo") or 1) == 4:
                r["cam"] = dict(r["cam"], x=x.tolist(), y=y.tolist(), z=z.tolist(), q=q0)
                r["cam_raw"] = dict(r["cam_raw"], x=x.tolist(), y=y.tolist(), z=z.tolist(), q=q0)
        self._write_rows(run60, rows)
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["30"], "PASA", rep["results"])
        self.assertEqual(rep["decisions"]["suave"]["60"], "INCONCLUSO", rep["results"])

    def test_v3_giro_de_20_grados_no_certifica(self):
        mod = self._load_eval()
        base = self.tmp_root / "v3_giro20"
        base.mkdir()
        self.fx._write_suave_run(base, regime=60, mode="giro20")
        rep = mod.evaluate(base)
        giros = [r for r in rep["results"] if str(r.get("tramo", "")).startswith("giro")]
        self.assertTrue(giros and all(r["verdict"] == "INCONCLUSO" for r in giros), giros)
        self.assertNotEqual(rep["decisions"]["suave"]["60"], "PASA", rep["decisions"])

    def test_v3_posicion_en_giros_y_previo(self):
        mod = self._load_eval()
        for name, solo_previo in (("v3_pos_en_giros", False), ("v3_pos_previo_giro", True)):
            base = self._copy_suave_ok(name)
            run_dir = base / "suave60_Hb"
            rows = self._read_rows(run_dir)
            for r in rows:
                if int(r.get("tramo") or 1) == 4 and (int(r.get("giro") or 0) == 0 if solo_previo else int(r.get("giro") or 0) > 0):
                    pos = list(r["cam"]["pos"])
                    pos[0] += 1.0
                    r["cam"] = dict(r["cam"], pos=pos)
            self._write_rows(run_dir, rows)
            rep = mod.evaluate(base)
            giros = [r for r in rep["results"] if str(r.get("tramo", "")).startswith("giro")]
            self.assertTrue(any(r["verdict"] == "FALLA" for r in giros), (name, giros))

    def test_v3_fps_cadencia_real_no_mediana(self):
        mod = self._load_eval()
        base = self.tmp_root / "v3_fps_cadencia"
        base.mkdir()
        self.fx._write_suave_run(base, regime=60, mode="ok", dt_pattern=(1.0 / 60.0, 1.0 / 60.0, 0.1))
        rep = mod.evaluate(base)
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(suave)
        # Cadencia real: 3 frames / (2/60+0.1) s = 22,5 FPS; la mediana de dt seguiria diciendo 60.
        self.assertTrue(all(abs(r["fps_measured"] - 22.5) < 1.0 for r in suave), suave[:2])
        self.assertTrue(all(abs(r.get("fps_median", 0.0) - 60.0) < 1.0 for r in suave), suave[:2])
        self.assertTrue(all(r["verdict"] == "INCONCLUSO" for r in suave), suave[:2])

    def test_v3_caso_regimen_y_tope_incoherentes(self):
        mod = self._load_eval()
        base = self.tmp_root / "v3_caso_incoherente"
        run_dir = base / "suave30_Hb"
        shutil.copytree(self.dirs["suave_ok"] / "suave60_Hb", run_dir)
        rows = self._read_rows(run_dir)
        for r in rows:
            r["caso"] = "suave30"
            r["run"] = "suave30_Hb"
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        self.assertEqual(rep["decisions"]["suave"]["30"], "INCONCLUSO", rep["results"])
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(suave and all(r["verdict"] == "INCONCLUSO" for r in suave), suave[:2])

    def test_v3_mascara_vacia_de_un_hook_no_bloquea_otro(self):
        mod = self._load_eval()
        base = self._fresh_s2("v3_mascara_hook")
        self.fx._write_tracking_run(base, "mount0", "Hb", inject="none", true_k=1, giro_field=True)
        self.fx._write_calib_run(base, "Hb", true_k=1, jitter_pm1=False)
        vacia = np.zeros((mod.TEMPLATE_PX, mod.TEMPLATE_PX), dtype=bool)
        orig = mod.build_masks_from_run
        def fake(run, marcas, k, fov_conv):
            if run["hook"] == "Ha":
                return {"usti hlavne": vacia, "konec hlavne": vacia}
            if run["hook"] == "Hb":
                return {"usti hlavne": self._disc_mask(), "konec hlavne": self._disc_mask()}
            return orig(run, marcas, k, fov_conv)
        mod.build_masks_from_run = fake
        rep = mod.evaluate(base)
        self.assertEqual(rep["detector"]["verdict"], "PASA", rep["detector"])

    def test_v3_sha_png_no_valida_bmp_distinto(self):
        mod = self._load_eval()
        d = self.tmp_root / "v3_sha_run"
        d.mkdir()
        img_bmp = np.full((1080, 1920), 100, dtype=np.uint8)
        img_png = np.full((1080, 1920), 180, dtype=np.uint8)
        Image.fromarray(img_bmp, mode="L").save(d / "f000001.bmp")
        Image.fromarray(img_png, mode="L").save(d / "f000001.png")
        import hashlib as _hl
        sha_png = _hl.sha256((d / "f000001.png").read_bytes()).hexdigest()
        mdir = self.tmp_root / "v3_sha_marcas"
        mdir.mkdir()
        data = {"schema": 1, "run": "mount0_Ha", "marcas": [{"shot": "f000001.bmp", "png": "f000001.png", "sha256": sha_png, "momento": "estable", "puntos": {"usti hlavne": [960.0, 540.0]}, "diff_max_px": 0.0}]}
        (mdir / "mount0_Ha.json").write_text(json.dumps(data), encoding="utf-8")
        valid, discarded = mod.load_marcas(mdir, "mount0_Ha", d)
        self.assertEqual(valid, [], discarded)
        self.assertTrue(discarded)

    def test_v3_follow_sin_giro2_ni_giro3_inconcluso(self):
        mod = self._load_eval()
        base = self._fresh_s2("v3_follow_incompleto")
        run_dir = base / "follow_Ha"
        rows = self._read_rows(run_dir)
        for r in rows:
            if int(r.get("giro") or 0) in (2, 3):
                r["giro"] = 0
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        thook = [r for r in rep["results"] if r["measure"] == "T-hook" and r["run"] == "follow_Ha" and r["window"] in ("giro2", "giro3")]
        self.assertTrue(thook and all(r["verdict"] == "INCONCLUSO" for r in thook), thook)
        self.assertIsNone(rep["decisions"]["hook_por_modo"]["follow"], rep["decisions"])

    def test_v3_ropa_con_huecos_inconcluso(self):
        mod = self._load_eval()
        base = self.tmp_root / "v3_ropa_huecos"
        shutil.copytree(self.dirs["ropa_ok"], base)
        run_dir = base / "ropa_Hb"
        rows = self._read_rows(run_dir)
        rows = [r for r in rows if int(r["frame"]) in (0, 60, 119)]
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        ropa = [r for r in rep["results"] if r["measure"] == "T-ropa"]
        self.assertTrue(any(r["verdict"] == "INCONCLUSO" and "cobertura" in r["cause"] for r in ropa), ropa)
        self.assertNotEqual(rep["decisions"]["ropa"]["mochila"], "sigue", rep["decisions"])

    def test_v3_mascara_anclada_a_marca_no_a_lectura_a(self):
        mod = self._load_eval()
        d = self.tmp_root / "v3_mask_anchor"
        d.mkdir()
        rng = np.random.default_rng(5)
        rows = []
        for i in range(55):
            img = (100.0 + rng.normal(0.0, 40.0, size=(300, 500))).astype(np.float32)
            img[90:111, 90:111] = 180.0
            name = f"f{i:06d}.bmp"
            Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), mode="L").save(d / name)
            # Proyeccion de (a) oscilando +-60 px alrededor de la marca (100,100): z=1, f=684.
            delta = 60.0 if i % 2 == 0 else -60.0
            wx = (100.0 + delta - 960.0) / 684.0
            wy = (540.0 - 100.0) / 684.0
            rows.append({"frame": i, "shot": name, "giro": 1, "cam": {"pos": [0, 0, 0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}, "fov_rad": 1.0471976,
                         "lecturas": {"usti hlavne": {"a": [wx, wy, 1.0]}}})
        run = {"dir": d, "run": "mount0_Ha", "caso": "mount0", "hook": "Ha", "inject": "none", "samples": rows, "by_frame": {r["frame"]: r for r in rows}, "has_gaps": False}
        marcas = [{"shot": "f000000.bmp", "puntos": {"usti hlavne": (100.0, 100.0)}, "momento": "giro1", "diff_max_px": 0.0}]
        masks = mod.build_masks_from_run(run, marcas, 0, 684.0)
        mask = masks.get("usti hlavne")
        self.assertIsNotNone(mask)
        self.assertTrue(mod._mask_valid(mask), masks)
        self.assertTrue(bool(mask[24, 24]))

    def test_v3_fondo_cambiante_ambos_detalles_y_angulo(self):
        mod = self._load_eval()
        run = self._fake_detector_run("v3_bg_ambos")
        src = mod._load_gray(run["dir"] / "f000001.png")
        # Senyuelo de recamara: copia exacta del parche de la recamara desplazada -18,-18 en cada fondo.
        pk = (960.0 + 136.8, 540.0)
        x0, y0 = int(round(pk[0])) - 24, int(round(pk[1])) - 24
        patch = src[y0:y0 + 48, x0:x0 + 48].copy()
        bgs = []
        for shift in (300.0, 700.0):
            bg = self.fx._slice_background(shift).copy()
            # Un senyuelo por desplazamiento de la sintetica, a -18,-18 de su objetivo.
            for du, dv in ((12.0, -7.0), (-9.0, 11.0)):
                bg[y0 + int(dv) - 18:y0 + int(dv) - 18 + 48, x0 + int(du) - 18:x0 + int(du) - 18 + 48] = patch
            bgs.append(bg)
        yy, xx = np.mgrid[0:48, 0:48]
        mask_k_small = ((xx - 23.5) ** 2 + (yy - 23.5) ** 2) <= (8.0 ** 2)
        masks = {"usti hlavne": self._disc_mask(), "konec hlavne": mask_k_small}
        res = mod.calibrate_detector([run], {"Ha": 0}, {"Ha": 684.0}, template_mask=masks, background_images=bgs)
        self.assertNotEqual(res["verdict"], "PASA", res)
        self.assertTrue(res.get("p95_bg_px", 0.0) > mod.DETECTOR_MAX_PX or res.get("p95_bg_deg", 0.0) > mod.DETECTOR_MAX_DEG, res)

    def test_v3_marcas_por_fase_y_falta_de_fase_inconcluso(self):
        mod = self._load_eval()
        base = self._fresh_s2("v3_marcas_fases")
        for run_name in ("mount0_Ha", "mount03_Ha", "lookat_Ha", "follow_Ha"):
            data = json.loads((base / "marcas" / f"{run_name}.json").read_text(encoding="utf-8"))
            momentos = {e["momento"] for e in data["marcas"]}
            self.assertEqual(momentos, {"estable", "giro1", "giro2", "giro3", "resto"}, (run_name, momentos))
        # Sin la fase giro2, T-marca no puede dar PASA.
        mpath = base / "marcas" / "mount0_Ha.json"
        data = json.loads(mpath.read_text(encoding="utf-8"))
        data["marcas"] = [e for e in data["marcas"] if e["momento"] != "giro2"]
        mpath.write_text(json.dumps(data), encoding="utf-8")
        rep = mod.evaluate(base)
        tm = [r for r in rep["results"] if r["measure"] == "T-marca" and r["run"] == "mount0_Ha"]
        self.assertTrue(tm and all(r["verdict"] == "INCONCLUSO" for r in tm), tm)

    def test_v3_ropa_detalle_mira_dibujado_y_fases(self):
        mod = self._load_eval()
        base = self.dirs["ropa_ok"]
        data = json.loads((base / "marcas" / "ropa_Hb.json").read_text(encoding="utf-8"))
        momentos = {e["momento"] for e in data["marcas"]}
        self.assertTrue({"estable", "giro1", "resto"} <= momentos, momentos)
        run_dir = base / "ropa_Hb"
        for entry in data["marcas"]:
            if "mira" not in entry["puntos"]:
                continue
            img = mod._load_gray(run_dir / entry["shot"])
            u, v = entry["puntos"]["mira"]
            self.assertGreaterEqual(mod._crop_std(img, u, v), mod.TEXTURE_MIN_STD, entry)

    # --- Vuelta 4 (revision de Sol, LAST_v3) ---

    def test_v4_suave_lata_ausente_en_salto_inconcluso(self):
        mod = self._load_eval()
        base = self._copy_suave_ok("v4_suave_lata_nula")
        run_dir = base / "suave60_Hb"
        rows = self._read_rows(run_dir)
        prev = None
        for r in rows:
            lata = (r.get("lata") or {}).get("a")
            if lata is not None and prev is not None and math.dist(lata, prev) > 0.5:
                r["lata"] = {"a": None}
            if lata is not None:
                prev = lata
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        suave = [r for r in rep["results"] if r["measure"] == "T-suave"]
        self.assertTrue(any(r["verdict"] == "INCONCLUSO" and r["cause"] == "lata_ausente" for r in suave), suave)
        self.assertEqual(rep["decisions"]["suave"]["60"], "INCONCLUSO", rep["decisions"])

    def test_v4_suave_giro_truncado_sin_1_6_inconcluso(self):
        mod = self._load_eval()
        base = self._copy_suave_ok("v4_suave_truncado")
        run_dir = base / "suave60_Hb"
        rows = self._read_rows(run_dir)
        giro1 = [i for i, r in enumerate(rows) if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        rows = rows[: giro1[3] + 1]
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        g1 = [r for r in rep["results"] if r.get("tramo") == "giro+170"]
        self.assertTrue(g1 and all(r["verdict"] == "INCONCLUSO" for r in g1), g1)
        self.assertTrue(all(r.get("orient_1_6_deg") is None for r in g1), g1)
        self.assertNotEqual(rep["decisions"]["suave"]["60"], "PASA", rep["decisions"])

    def test_v4_suave_interpolacion_exponencial_intervalos_irregulares(self):
        mod = self._load_eval()
        base = self._copy_suave_ok("v4_suave_interp_exp")
        run_dir = base / "suave60_Hb"
        rows = self._read_rows(run_dir)
        giro1 = [i for i, r in enumerate(rows) if int(r.get("tramo") or 1) == 4 and int(r.get("giro") or 0) == 1]
        # Dos primeros intervalos de 100 ms, resto a 60 FPS (Sol v3, hallazgo 3).
        for j, i in enumerate(giro1):
            rows[i]["dt"] = 0.1 if j < 2 else round(1.0 / 60.0, 6)
        t_acc = 0.0
        for r in rows:
            t_acc += float(r["dt"])
            r["t_ms"] = round(t_acc * 1000.0, 3)

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
            r["cam"] = dict(r["cam"], pos=filt_pos.tolist(), x=fx_.tolist(), y=fy_.tolist(), z=fz_.tolist(), q=self.fx._quat_xyzw_from_wxyz(filt_q))
        self._write_rows(run_dir, rows)
        rep = mod.evaluate(base)
        g1 = [r for r in rep["results"] if r.get("tramo") == "giro+170"]
        self.assertTrue(g1 and all(r["verdict"] == "PASA" for r in g1), g1)
        # Oraculo analitico exponencial: 170*(1-exp(-(1/6)/0.3)) = 72.4619 deg;
        # la interpolacion lineal daria 71.2093 deg (1.2526 deg artificiales).
        esperado = 170.0 * (1.0 - math.exp(-(1.0 / 6.0) / 0.3))
        self.assertTrue(all(abs(r["orient_1_6_deg"] - esperado) < 0.6 for r in g1), (esperado, g1))

    def test_v4_giro_160_no_certifica_170(self):
        mod = self._load_eval()
        base = self.tmp_root / "v4_giro160"
        base.mkdir()
        self.fx._write_suave_run(base, regime=60, mode="giro160")
        rep = mod.evaluate(base)
        giros = [r for r in rep["results"] if str(r.get("tramo", "")).startswith("giro")]
        self.assertTrue(giros and all(r["verdict"] == "INCONCLUSO" for r in giros), giros)
        self.assertNotEqual(rep["decisions"]["suave"]["60"], "PASA", rep["decisions"])

    def test_v4_calibracion_por_pareja_de_mascaras_con_procedencia(self):
        mod = self._load_eval()
        run_ha = self._fake_detector_run("v4_det_ha")
        run_hb = self._fake_detector_run("v4_det_hb")
        # Imagen de Ha plana dentro de las mascaras de Hb (disco r=16): incompatible con ellas.
        img_ha = mod._load_gray(run_ha["dir"] / "f000001.png")
        for cu in (960.0 - 136.8, 960.0 + 136.8):
            cx, cy = int(round(cu)), 540
            yy, xx = np.mgrid[cy - 16:cy + 17, cx - 16:cx + 17]
            img_ha[cy - 16:cy + 17, cx - 16:cx + 17][(xx - cu) ** 2 + (yy - 540.0) ** 2 <= 16.0 ** 2] = 100.0
        Image.fromarray(np.clip(img_ha, 0, 255).astype(np.uint8)).save(run_ha["dir"] / "f000001.png")
        run_ha["samples"][0]["shot"] = "f000001.png"
        run_hb["samples"][0]["shot"] = "f000001.png"
        run_hb["hook"] = "Hb"
        run_hb["run"] = "mount0_Hb"
        vacia = np.zeros((mod.TEMPLATE_PX, mod.TEMPLATE_PX), dtype=bool)
        masks_hb = {"usti hlavne": self._disc_mask(), "konec hlavne": self._disc_mask()}
        bgs = [self.fx._slice_background(300.0), self.fx._slice_background(700.0)]
        res = mod.calibrate_detector(
            [run_ha, run_hb], {"Ha": 0, "Hb": 0}, {"Ha": 684.0, "Hb": 684.0},
            mask_by_hook={"Ha": {"usti hlavne": vacia, "konec hlavne": vacia}, "Hb": masks_hb},
            background_images=bgs,
        )
        self.assertEqual(res["verdict"], "PASA", res)

    def test_v4_marcas_solo_png_vincula_imagen_consumida(self):
        mod = self._load_eval()
        d = self.tmp_root / "v4_png_run"
        d.mkdir()
        Image.fromarray(np.full((1080, 1920), 100, dtype=np.uint8), mode="L").save(d / "f000120.png")
        Image.fromarray(np.full((1080, 1920), 180, dtype=np.uint8), mode="L").save(d / "otra.png")
        import hashlib as _hl
        sha_otra = _hl.sha256((d / "otra.png").read_bytes()).hexdigest()
        mdir = self.tmp_root / "v4_png_marcas"
        mdir.mkdir()
        data = {"schema": 1, "run": "mount0_Ha", "marcas": [{"shot": "f000120.bmp", "png": "otra.png", "sha256": sha_otra, "momento": "estable", "puntos": {"usti hlavne": [960.0, 540.0]}, "diff_max_px": 0.0}]}
        (mdir / "mount0_Ha.json").write_text(json.dumps(data), encoding="utf-8")
        valid, discarded = mod.load_marcas(mdir, "mount0_Ha", d)
        self.assertEqual(valid, [], discarded)
        self.assertTrue(discarded)

    def test_v4_deteccion_no_descartada_por_proyeccion_de_a(self):
        mod = self._load_eval()
        d = self.tmp_root / "v4_detect_a_oscila"
        d.mkdir()
        true_u, true_k, vv = (400.0, 700.0), (700.0, 400.0), 400.0
        rows = []
        for i in range(25):
            img = np.full((800, 1200), 100.0, dtype=np.float32)
            self.fx._stamp_motif(img, true_u[0], true_u[1], kind="usti")
            self.fx._stamp_motif(img, true_k[0], true_k[1], kind="konec")
            name = f"f{i:06d}.bmp"
            Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), mode="L").save(d / name)
            delta = 60.0 if i % 2 == 0 else -60.0

            def _world(u, v):
                return [(u - 960.0) / 684.0, (540.0 - v) / 684.0, 1.0]

            lect = {
                "usti hlavne": {"a": _world(true_u[0] + delta, true_u[1]), "f": _world(*true_u)},
                "konec hlavne": {"a": _world(true_k[0] + delta, true_k[1]), "f": _world(*true_k)},
            }
            rows.append({"frame": i, "shot": name, "giro": 1, "cam": {"pos": [0, 0, 0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}, "fov_rad": 1.0471976, "lecturas": lect})
        run = {"dir": d, "run": "mount0_Ha", "caso": "mount0", "hook": "Ha", "inject": "none", "samples": rows, "by_frame": {r["frame"]: r for r in rows}, "has_gaps": False}
        marcas = [{"shot": "f000000.bmp", "puntos": {"usti hlavne": true_u, "konec hlavne": true_k}, "momento": "giro1", "diff_max_px": 0.0}]
        masks = {"usti hlavne": self._disc_mask(), "konec hlavne": self._disc_mask()}
        dets = mod._detect_run_shots(run, 0, 684.0, ref_reading="a", marcas=marcas, mask=masks)
        self.assertTrue(dets and all(v is not None for v in dets.values()), dets)
        _p95, _roll, _cov, verdict, _cause, _n = mod._eval_window_metrics(run, [r["frame"] for r in rows], dets, 0, 684.0, "f")
        self.assertEqual(verdict, "PASA", (_p95, _cov))

    def test_v4_sin_marca_giro2_mount0_no_selecciona_lectura_ni_exit0(self):
        mod = self._load_eval()
        base = self._fresh_s2("v4_sin_giro2_mount0")
        mpath = base / "marcas" / "mount0_Ha.json"
        data = json.loads(mpath.read_text(encoding="utf-8"))
        data["marcas"] = [e for e in data["marcas"] if e["momento"] != "giro2"]
        mpath.write_text(json.dumps(data), encoding="utf-8")
        rep = mod.evaluate(base)
        self.assertIsNone(rep["decisions"]["lectura"], rep["decisions"])
        self.assertEqual(rep["exit_code"], 2, rep["exit_code"])
        self.assertIsNone(rep["decisions"]["hook_por_modo"]["mount0"], rep["decisions"])

    def test_v4_ropa_una_sola_marca_mira_no_sigue(self):
        mod = self._load_eval()
        base = self.tmp_root / "v4_ropa_mira_una"
        shutil.copytree(self.dirs["ropa_ok"], base)
        mpath = base / "marcas" / "ropa_Hb.json"
        data = json.loads(mpath.read_text(encoding="utf-8"))
        for j, entry in enumerate(data["marcas"]):
            if j > 0:
                entry["puntos"].pop("mira", None)
        mpath.write_text(json.dumps(data), encoding="utf-8")
        rep = mod.evaluate(base)
        self.assertNotEqual(rep["decisions"]["ropa"]["mira"], "sigue", rep["decisions"])
        mira = [r for r in rep["results"] if r["measure"] == "T-ropa" and r.get("category") == "mira"]
        self.assertTrue(mira and all(r["verdict"] == "INCONCLUSO" for r in mira), mira)

    def test_ropa_sigue(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["ropa_ok"])
        self.assertEqual(rep["decisions"]["ropa"], {"mochila": "sigue", "mira": "sigue", "silenciador": "sigue"}, rep["results"])
        ropa = [r for r in rep["results"] if r["measure"] == "T-ropa"]
        self.assertTrue(ropa)
        for r in ropa:
            self.assertLess(r["p95_m"], mod.ROPA_MAX_M, r)
            self.assertLess(r["p95_deg"], mod.ROPA_MAX_DEG, r)


if __name__ == "__main__":
    unittest.main()
