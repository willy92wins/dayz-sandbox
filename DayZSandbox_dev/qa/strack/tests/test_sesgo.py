"""Tests offline de la comprobacion del sesgo con rasgos visibles (S17).

(a) marcas exactas -> PASA; (b) una lectura con sesgo constante de 5 px -> FALLA;
(c) 9 capturas -> INCONCLUSO sesgo_no_observable; (d) ajuste de elipse;
(e) quiralidad con ax2 invertido detectada.
"""

import hashlib
import importlib.util
import json
import math
import os
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

STRACK_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_PATH = STRACK_DIR / "s_track_eval.py"
FIXTURES_MOD_PATH = STRACK_DIR / "fixtures" / "make_fixtures.py"
MARCAS_TOOL_PATH = STRACK_DIR / "marcas_tool.py"


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


class SesgoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp_root = Path(cls._tmp.name)
        cls.fx = _load_module(FIXTURES_MOD_PATH, "strack_sesgo_make_fixtures")
        cls.dirs = {}
        for kind in ("sesgo_ok", "sesgo_bias5", "sesgo_pocas", "sesgo_bias_a",
                     "sesgo_caso_doble", "sesgo_caso_simple",
                     "sesgo_decision", "sesgo_decision_pocas"):
            cls.dirs[kind] = cls.fx.generate_fixture(cls.tmp_root / kind, kind=kind)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _load_eval(self):
        return _load_module(_eval_path(), "s_track_eval_sesgo")

    def _tsesgo(self, mod, rep, reading=None, feature=None):
        rows = [r for r in rep["results"] if r["measure"] == "T-sesgo"]
        if reading is not None:
            rows = [r for r in rows if r["reading"] == reading]
        if feature is not None:
            rows = [r for r in rows if r.get("feature") == feature]
        return rows

    # (a) marcas exactas -> PASA
    def test_a_marcas_exactas_pasa(self):
        mod = self._load_eval()
        self.assertEqual(mod.SESGO_MIN_MARCAS, 10)
        rep = mod.evaluate(self.dirs["sesgo_ok"])
        rows = self._tsesgo(mod, rep)
        self.assertTrue(rows)
        self.assertEqual({r["feature"] for r in rows}, {"boca_anillo", "punto_mira"})
        for r in rows:
            self.assertEqual(r["window"], f"marcas:{r['feature']}", r)
            self.assertEqual(r["n_shots"], 12, r)
            self.assertEqual(r["verdict"], "PASA", r)
            self.assertLessEqual(r["p95_px"], mod.THRESH_PX, r)

    # (b) una lectura con sesgo constante de 5 px -> FALLA; las demas pasan
    def test_b_sesgo_constante_5px_falla(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["sesgo_bias5"])
        self.assertEqual({r["feature"] for r in self._tsesgo(mod, rep)}, {"boca_anillo", "punto_mira"})
        biased = self._tsesgo(mod, rep, reading="b")
        self.assertTrue(biased)
        self.assertEqual({r["feature"] for r in biased}, {"boca_anillo", "punto_mira"})
        for r in biased:
            self.assertEqual(r["verdict"], "FALLA", r)
            self.assertGreater(r["p95_px"], mod.THRESH_PX, r)
            self.assertGreaterEqual(r["p95_px"], 4.0, r)
        unbiased = self._tsesgo(mod, rep, reading="a")
        self.assertTrue(unbiased)
        self.assertTrue(all(r["verdict"] == "PASA" for r in unbiased), unbiased)

    # (c) 9 capturas -> INCONCLUSO sesgo_no_observable
    def test_c_nueve_capturas_sesgo_no_observable(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["sesgo_pocas"])
        rows = self._tsesgo(mod, rep)
        self.assertTrue(rows)
        self.assertEqual({r["feature"] for r in rows}, {"boca_anillo", "punto_mira"})
        for r in rows:
            self.assertEqual(r["n_shots"], 9, r)
            self.assertEqual(r["verdict"], "INCONCLUSO", r)
            self.assertEqual(r["cause"], "sesgo_no_observable", r)

    # (d) ajuste de elipse: centro exacto y rechazo de casi colineales
    def test_d_elipse_centro_y_rechazo(self):
        tool = _load_module(MARCAS_TOOL_PATH, "marcas_tool_sesgo")
        cx, cy, rx, ry, ang = 700.25, 410.5, 30.0, 12.0, 0.6
        pts = []
        for t in (0.3, 1.4, 2.5, 3.6, 5.1):
            x = rx * math.cos(t)
            y = ry * math.sin(t)
            pts.append([cx + x * math.cos(ang) - y * math.sin(ang),
                        cy + x * math.sin(ang) + y * math.cos(ang)])
        got = tool.fit_ellipse_center(pts)
        self.assertLess(math.hypot(got[0] - cx, got[1] - cy), 0.01, got)
        colineales = [[100.0 + 10.0 * i, 200.0 + 0.01 * i] for i in range(5)]
        with self.assertRaises(ValueError):
            tool.fit_ellipse_center(colineales)

    def test_d_cerrar_usa_centro_de_elipse_y_media_de_orejas(self):
        tool = _load_module(MARCAS_TOOL_PATH, "marcas_tool_sesgo_cerrar")
        borde = []
        for t in (0.2, 1.5, 2.8, 4.0, 5.3):
            borde.append([960.0 + 20.0 * math.cos(t), 540.0 + 9.0 * math.sin(t)])
        data = {"schema": 1, "run": "mount0_Ha", "marcas": [{
            "shot": "f000000.bmp", "png": "f000000.png", "sha256": "x", "momento": "estable",
            "A": {"boca_anillo_borde": borde, "punto_mira_orejas": [[950.0, 500.0], [954.0, 502.0]]},
            "B": {"boca_anillo_borde": borde, "punto_mira_orejas": [[950.0, 500.0], [954.0, 502.0]]},
        }]}
        out = tool.cerrar(data)
        m = out["marcas"][0]
        self.assertLess(math.hypot(m["puntos"]["boca_anillo"][0] - 960.0, m["puntos"]["boca_anillo"][1] - 540.0), 0.01, m)
        self.assertEqual(m["puntos"]["punto_mira"], [952.0, 501.0])
        self.assertLessEqual(m["diff_max_px"], 0.01, m)

    def test_d_poner_borde_y_orejas_guardan_formato(self):
        tool = _load_module(MARCAS_TOOL_PATH, "marcas_tool_sesgo_poner")
        with tempfile.TemporaryDirectory() as td:
            marcas_dir = Path(td)
            data = {"schema": 1, "run": "mount0_Ha", "convencion": "fixture",
                    "marcadores": {"A": "t", "B": "t"},
                    "marcas": [{"shot": "f000000.bmp", "png": "f000000.png", "sha256": "x", "momento": "estable", "A": {}, "B": {}}]}
            (marcas_dir / "mount0_Ha.json").write_text(json.dumps(data), encoding="utf-8")

            class Args:
                pass

            a = Args(); a.run = "mount0_Ha"; a.png = "f000000.png"; a.marcador = "A"; a.marcas = str(marcas_dir)
            a.coords = [940.0, 540.0, 980.0, 540.0, 960.0, 531.0, 960.0, 549.0, 975.0, 535.0]
            tool.cmd_poner_borde(a)
            a.coords = [950.0, 500.0, 954.0, 502.0]
            tool.cmd_poner_orejas(a)
            saved = json.loads((marcas_dir / "mount0_Ha.json").read_text(encoding="utf-8"))
            marker = saved["marcas"][0]["A"]
            self.assertEqual(len(marker["boca_anillo_borde"]), 5)
            self.assertEqual(marker["punto_mira_orejas"], [[950.0, 500.0], [954.0, 502.0]])
            self.assertEqual(marker["punto_mira"], [952.0, 501.0])

    # (e) quiralidad: ax2 invertido detectado
    def test_e_quiralidad_ax2_invertido(self):
        mod = self._load_eval()
        self.assertTrue(mod._chirality_ok([1, 0, 0], [0, 1, 0], [0, 0, 1]))
        self.assertFalse(mod._chirality_ok([1, 0, 0], [0, 1, 0], [0, 0, -1]))
        # Tambien con ejes ndarray ya calculados (regresion vuelta 2: _vec3
        # solo aceptaba list/tuple y _punto_mira_world_mount devolvia siempre
        # None al comprobar la quiralidad con sus propios ejes ndarray).
        self.assertTrue(mod._chirality_ok(np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0])))
        self.assertFalse(mod._chirality_ok(np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, -1.0])))
        # Camara segun STRACK_Math.Look desde camPos=(0.6,1.6,0) hacia
        # konec con up=ax1=(0,1,0): z=dir, x=normalize(up x z)=ax0 x ax1,
        # y=z x x (up ortogonalizado, ax1.y=0,887 y no 1).
        look_y = [-0.461876, 0.886945, 0.0]
        look_z = [-0.886945, -0.461876, 0.0]
        # En mount, una x de camara invertida omite el punto de mira.
        target = {
            "caso": "mount0",
            "lecturas": {"usti hlavne": {"a": [0.0, 1.5, 0.0]}, "konec hlavne": {"a": [0.407969, 1.5, 0.0]}},
            "cam": {"pos": [0.6, 1.6, 0.0], "x": [0.0, 0.0, -1.0], "y": look_y, "z": look_z},
        }
        self.assertIsNone(mod._punto_mira_world_mount(target, "a"))
        target["cam"]["x"] = [0.0, 0.0, 1.0]
        self.assertIsNotNone(mod._punto_mira_world_mount(target, "a"))

    def test_e_mount03_sin_cam_raw_omite_punto_mira(self):
        mod = self._load_eval()
        look_y = [-0.461876, 0.886945, 0.0]
        look_z = [-0.886945, -0.461876, 0.0]
        target = {
            "caso": "mount03",
            "lecturas": {"usti hlavne": {"a": [0.0, 1.5, 0.0]}, "konec hlavne": {"a": [0.407969, 1.5, 0.0]}},
            "cam": {"pos": [0.6, 1.6, 0.0], "x": [0.0, 0.0, 1.0], "y": look_y, "z": look_z},
        }
        self.assertIsNone(mod._punto_mira_world_mount(target, "a"))
        target["cam_raw"] = {"pos": [0.6, 1.6, 0.0], "x": [0.0, 0.0, 1.0], "y": look_y, "z": look_z}
        self.assertIsNotNone(mod._punto_mira_world_mount(target, "a"))

    # (f) ruido float32 en ax1: |ax1|=1,012 y ax0.ax1=0,0075 (medido en
    # mount0_Ha real) no debe mover el punto_mira proyectado >= 0,5 px una
    # vez ortogonalizado y normalizado contra ax0.
    def test_f_ax1_ruido_float32_proyeccion_menor_05px(self):
        mod = self._load_eval()
        ax0 = np.array([1.0, 0.0, 0.0])
        ax1_true = np.array([0.0, 1.0, 0.0])
        ax2_true = np.array([0.0, 0.0, 1.0])
        usti = np.array([0.0, 1.5, 0.0])
        konec = usti + 0.407969 * ax0
        # ax1 crudo con el ruido medido: norma 1,012 y producto con ax0 0,0075.
        ax1_noisy = np.array([0.0075, math.sqrt(1.012 ** 2 - 0.0075 ** 2), 0.0])
        self.assertAlmostEqual(float(np.linalg.norm(ax1_noisy)), 1.012, places=12)
        self.assertAlmostEqual(float(np.dot(ax1_noisy, ax0)), 0.0075, places=12)
        cam_pos_noisy = usti + 0.6 * ax0 + 0.1 * ax1_noisy
        # Camara Look verdadera (up=ax1_true) para proyectar verdad y resultado.
        z_cam = (konec - (usti + 0.6 * ax0 + 0.1 * ax1_true))
        z_cam = z_cam / float(np.linalg.norm(z_cam))
        x_cam = np.cross(ax1_true, z_cam)
        x_cam = x_cam / float(np.linalg.norm(x_cam))
        y_cam = np.cross(z_cam, x_cam)
        cam = {"pos": (usti + 0.6 * ax0 + 0.1 * ax1_true).tolist(),
               "x": x_cam.tolist(), "y": y_cam.tolist(), "z": z_cam.tolist()}
        target = {
            "caso": "mount0",
            "lecturas": {"usti hlavne": {"a": usti.tolist()}, "konec hlavne": {"a": konec.tolist()}},
            "cam": {"pos": cam_pos_noisy.tolist(), "x": ax2_true.tolist(), "y": ax1_true.tolist(), "z": (-ax0).tolist()},
        }
        world = mod._punto_mira_world_mount(target, "a")
        self.assertIsNotNone(world)
        rasgos = mod._load_rasgos()
        usti_m = np.array(rasgos["usti_modelo"], dtype=np.float64)
        pm_m = np.array(rasgos["punto_mira_modelo"], dtype=np.float64)
        delta = pm_m - usti_m
        world_true = usti + float(delta[0]) * ax0 + float(delta[1]) * ax1_true + float(delta[2]) * ax2_true
        proj = mod.project_point(world, cam, 1.0471976, "vertical")
        proj_true = mod.project_point(world_true, cam, 1.0471976, "vertical")
        self.assertIsNotNone(proj)
        self.assertIsNotNone(proj_true)
        self.assertLess(math.hypot(proj[0] - proj_true[0], proj[1] - proj_true[1]), 0.5,
                        (proj, proj_true))

    # (d2) elipse valida en varias posiciones de pantalla, esquinas incluidas
    def test_d_elipse_varias_posiciones(self):
        tool = _load_module(MARCAS_TOOL_PATH, "marcas_tool_sesgo_pos")
        for cx, cy in ((960.0, 540.0), (40.0, 40.0), (1880.0, 1040.0), (35.0, 1050.0), (1890.0, 30.0)):
            pts = []
            for t in (0.3, 1.4, 2.5, 3.6, 5.1):
                x, y = 30.0 * math.cos(t), 12.0 * math.sin(t)
                pts.append([cx + x * math.cos(0.6) - y * math.sin(0.6),
                            cy + x * math.sin(0.6) + y * math.cos(0.6)])
            got = tool.fit_ellipse_center(pts)
            self.assertLess(math.hypot(got[0] - cx, got[1] - cy), 0.01, (cx, cy, got))

    # (d3) poner/poner-borde/poner-orejas dan de alta una captura no elegida
    def test_d_poner_extra_da_de_alta(self):
        tool = _load_module(MARCAS_TOOL_PATH, "marcas_tool_sesgo_extra")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            marcas_dir = root / "marcas"; marcas_dir.mkdir()
            run_dir = root / "mount0_Ha"; run_dir.mkdir()
            png_bytes = b"png-extra-fixture"
            (run_dir / "f000999.png").write_bytes(png_bytes)
            data = {"schema": 1, "run": "mount0_Ha", "convencion": "fixture",
                    "marcadores": {"A": "t", "B": "t"}, "marcas": []}
            (marcas_dir / "mount0_Ha.json").write_text(json.dumps(data), encoding="utf-8")

            class Args:
                pass

            a = Args(); a.run = "mount0_Ha"; a.png = "f000999.png"; a.marcador = "A"
            a.marcas = str(marcas_dir); a.run_dir = str(run_dir)
            a.coords = [940.0, 540.0, 980.0, 540.0, 960.0, 531.0, 960.0, 549.0, 975.0, 535.0]
            tool.cmd_poner_borde(a)
            a.coords = [950.0, 500.0, 954.0, 502.0]
            tool.cmd_poner_orejas(a)
            a.punto = "punto_mira"; a.u = 952.0; a.v = 501.0
            tool.cmd_poner(a)
            saved = json.loads((marcas_dir / "mount0_Ha.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["marcas"]), 1, saved)
            m = saved["marcas"][0]
            self.assertEqual(m["momento"], "extra", m)
            self.assertEqual(m["shot"], "f000999.bmp", m)
            self.assertEqual(m["sha256"], hashlib.sha256(png_bytes).hexdigest(), m)
            self.assertEqual(m["A"]["punto_mira"], [952.0, 501.0], m)
            a.png = "f000998.png"
            with self.assertRaises(SystemExit):
                tool.cmd_poner_borde(a)

    # (e2) ropa: pose dextrogira pasa, eje invertido no; mount sin cam.x no
    def test_e_ropa_quiralidad_y_mount_sin_x(self):
        mod = self._load_eval()
        target = {"caso": "ropa", "ropa": {"arma": {"a": {
            "pos": [0.0, 1.5, 0.0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}}}}
        self.assertIsNotNone(mod._punto_mira_world_ropa(target, "a"))
        target["ropa"]["arma"]["a"]["z"] = [0, 0, -1]
        self.assertIsNone(mod._punto_mira_world_ropa(target, "a"))
        look_y = [-0.461876, 0.886945, 0.0]
        look_z = [-0.886945, -0.461876, 0.0]
        mount = {"caso": "mount0",
                 "lecturas": {"usti hlavne": {"a": [0.0, 1.5, 0.0]}, "konec hlavne": {"a": [0.407969, 1.5, 0.0]}},
                 "cam": {"pos": [0.6, 1.6, 0.0], "y": look_y, "z": look_z}}
        self.assertIsNone(mod._punto_mira_world_mount(mount, "a"))

    # (g) agregacion por caso: 2 corridas de 5 -> 10 y veredicto; 1 de 5 no
    def test_g_agregacion_por_caso(self):
        mod = self._load_eval()
        rep = mod.evaluate(self.dirs["sesgo_caso_doble"])
        rows = self._tsesgo(mod, rep)
        self.assertTrue(rows)
        self.assertEqual({r["feature"] for r in rows}, {"boca_anillo", "punto_mira"})
        for r in rows:
            self.assertEqual(r["caso"], "mount0", r)
            self.assertEqual(r["n_shots"], 10, r)
            self.assertEqual(r["verdict"], "PASA", r)
        rep1 = mod.evaluate(self.dirs["sesgo_caso_simple"])
        for r in self._tsesgo(mod, rep1):
            self.assertEqual(r["n_shots"], 5, r)
            self.assertEqual(r["verdict"], "INCONCLUSO", r)
            self.assertEqual(r["cause"], "sesgo_no_observable", r)

    # (h) sin calibracion valida, T-sesgo de imagen es calib_inconcluso
    def test_h_sin_calibracion_tsesgo_inconcluso(self):
        mod = self._load_eval()
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "runs"
            shutil.copytree(self.dirs["sesgo_ok"], dst)
            shutil.rmtree(dst / "calib_Ha")
            rows = self._tsesgo(mod, mod.evaluate(dst))
            self.assertTrue(rows)
            for r in rows:
                self.assertEqual(r["verdict"], "INCONCLUSO", r)
                self.assertEqual(r["cause"], "calib_inconcluso", r)

    # (i) sesgo en «a»: la camara se construye desde la usti sesgada y solo
    # la lectura «a» falla (las marcas son la verdad con la camara escrita)
    def test_i_sesgo_en_a_camara_desde_a(self):
        mod = self._load_eval()
        rows_jsonl = (self.dirs["sesgo_bias_a"] / "mount0_Ha" / "samples.jsonl").read_text(encoding="utf-8")
        row0 = json.loads(rows_jsonl.splitlines()[0])
        usti_a = row0["lecturas"]["usti hlavne"]["a"]
        self.assertGreater(abs(usti_a[2]), 1e-4, row0)
        self.assertAlmostEqual(row0["cam"]["pos"][2], usti_a[2], places=9, msg=row0["cam"])
        rep = mod.evaluate(self.dirs["sesgo_bias_a"])
        biased = self._tsesgo(mod, rep, reading="a")
        self.assertEqual({r["feature"] for r in biased}, {"boca_anillo", "punto_mira"})
        self.assertTrue(all(r["verdict"] == "FALLA" for r in biased), biased)
        unbiased = self._tsesgo(mod, rep, reading="b")
        self.assertTrue(all(r["verdict"] == "PASA" for r in unbiased), unbiased)

    # (j) A2: un punto repetido (rango 4) se rechaza por el 5.º valor singular
    def test_j_elipse_punto_repetido_rechaza(self):
        tool = _load_module(MARCAS_TOOL_PATH, "marcas_tool_sesgo_rep")
        pts = [[960.0, 531.0], [980.0, 540.0], [960.0, 549.0], [940.0, 540.0], [940.0, 540.0]]
        with self.assertRaises(ValueError):
            tool.fit_ellipse_center(pts)

    # (k) A6: poner punto_mira borra punto_mira_orejas del marcador
    def test_k_poner_punto_mira_borra_orejas(self):
        tool = _load_module(MARCAS_TOOL_PATH, "marcas_tool_sesgo_poner_pm")
        with tempfile.TemporaryDirectory() as td:
            marcas_dir = Path(td)
            data = {"schema": 1, "run": "mount0_Ha", "convencion": "fixture",
                    "marcadores": {"A": "t", "B": "t"},
                    "marcas": [{"shot": "f000000.bmp", "png": "f000000.png", "sha256": "x", "momento": "estable",
                                "A": {"punto_mira_orejas": [[1.0, 2.0], [3.0, 4.0]], "punto_mira": [2.0, 3.0]}, "B": {}}]}
            (marcas_dir / "mount0_Ha.json").write_text(json.dumps(data), encoding="utf-8")

            class Args:
                pass

            a = Args(); a.run = "mount0_Ha"; a.png = "f000000.png"; a.marcador = "A"
            a.marcas = str(marcas_dir); a.run_dir = None; a.punto = "punto_mira"; a.u = 9.0; a.v = 8.0
            tool.cmd_poner(a)
            saved = json.loads((marcas_dir / "mount0_Ha.json").read_text(encoding="utf-8"))
            marker = saved["marcas"][0]["A"]
            self.assertEqual(marker["punto_mira"], [9.0, 8.0], marker)
            self.assertNotIn("punto_mira_orejas", marker, marker)

    # (l) A3: una corrida sin calibracion no contamina la agregacion por caso
    def test_l_agregacion_sin_calibracion_no_contamina(self):
        mod = self._load_eval()
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "runs"
            shutil.copytree(self.dirs["sesgo_caso_doble"], dst)
            shutil.rmtree(dst / "calib_Hb")
            rows = self._tsesgo(mod, mod.evaluate(dst))
            self.assertTrue(rows)
            for r in rows:
                self.assertEqual(r["verdict"], "INCONCLUSO", r)
                self.assertEqual(r["cause"], "calib_inconcluso", r)
                self.assertEqual(r["n_shots"], 5, r)
                self.assertEqual(r["p95_px"], 999.0, r)

    # (m) Vuelta 4b, punto 3: ancla de la plantilla. Sin marcas §12 (solo
    # §17, como en partida) la plantilla se ancla en la proyeccion de la
    # lectura (a) y las filas lo dicen con ancla="proyeccion_a"; con marcas
    # §12 de los dos puntos, ancla="marca" como hasta ahora.
    def test_m_ancla_proyeccion_a_y_marca(self):
        mod = self._load_eval()
        self.assertEqual(mod._ancla_plantilla(
            [{"puntos": {"usti hlavne": (1.0, 2.0), "konec hlavne": (3.0, 4.0)}}]), "marca")
        self.assertEqual(mod._ancla_plantilla(
            [{"puntos": {"boca_anillo": (3.0, 4.0), "punto_mira": (1.0, 2.0)}}]), "proyeccion_a")
        self.assertEqual(mod._ancla_plantilla([]), "proyeccion_a")
        # Camino proyeccion_a: solo marcas §17 -> la corrida llega a
        # decision con la plantilla de los dos puntos §12 y roll, sin
        # filas T-marca (solo existen con marcas §12).
        rep = mod.evaluate(self.dirs["sesgo_decision"])
        self.assertFalse([r for r in rep["results"] if r["measure"] == "T-marca"], rep["results"][:3])
        tlect = [r for r in rep["results"] if r["measure"] in ("T-lect", "T-hook")]
        self.assertTrue(tlect)
        self.assertTrue(all(r.get("ancla") == "proyeccion_a" for r in tlect), tlect[:3])
        self.assertEqual(rep["decisions"]["lectura"], "a", rep["decisions"])
        boca_a = [r for r in self._tsesgo(mod, rep, reading="a") if r["feature"] == "boca_anillo"]
        self.assertTrue(boca_a and all(r["verdict"] == "PASA" for r in boca_a), boca_a)
        # Camino marca: la misma corrida con marcas §12 de usti/konec en
        # la verdad de (a) (con las cinco fases) -> ancla="marca".
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "runs"
            shutil.copytree(self.dirs["sesgo_decision"], dst)
            marcas_path = dst / "marcas" / "mount0_Ha.json"
            data = json.loads(marcas_path.read_text(encoding="utf-8"))
            rows = [json.loads(line) for line in
                    (dst / "mount0_Ha" / "samples.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            by_shot = {r["shot"]: r for r in rows if r.get("shot")}
            fases = ["estable", "giro1", "giro2", "giro3", "resto"]
            for i, entry in enumerate(data["marcas"]):
                row = by_shot[entry["shot"]]
                cam = row["cam"]
                fov = float(row.get("fov_rad", 1.0471976))
                for punto in ("usti hlavne", "konec hlavne"):
                    proj = mod.project_point(row["lecturas"][punto]["a"], cam, fov, "vertical")
                    self.assertIsNotNone(proj)
                    entry["puntos"][punto] = [proj[0], proj[1]]
                if i < len(fases):
                    entry["momento"] = fases[i]
            marcas_path.write_text(json.dumps(data), encoding="utf-8")
            rep_m = mod.evaluate(dst)
            tlect_m = [r for r in rep_m["results"] if r["measure"] in ("T-lect", "T-hook")]
            self.assertTrue(tlect_m)
            self.assertTrue(all(r.get("ancla") == "marca" for r in tlect_m), tlect_m[:3])
            self.assertEqual(rep_m["decisions"]["lectura"], "a", rep_m["decisions"])

    # (n) Vuelta 4b, punto 4: T-sesgo es solo informativo. Un caso con
    # T-sesgo FALLA deja la decision de lectura y el exit_code iguales que
    # sin marcas §17; con 9 marcas queda INCONCLUSO y tampoco bloquea.
    def test_n_tsesgo_falla_no_cambia_decision_ni_exit_code(self):
        mod = self._load_eval()
        with tempfile.TemporaryDirectory() as td:
            dst_bias = Path(td) / "bias"
            shutil.copytree(self.dirs["sesgo_decision"], dst_bias)
            marcas_path = dst_bias / "marcas" / "mount0_Ha.json"
            data = json.loads(marcas_path.read_text(encoding="utf-8"))
            for entry in data["marcas"]:
                u, v = entry["puntos"]["boca_anillo"]
                entry["puntos"]["boca_anillo"] = [u + 30.0, v]
            marcas_path.write_text(json.dumps(data), encoding="utf-8")
            rep_bias = mod.evaluate(dst_bias)
            dst_sin = Path(td) / "sin"
            shutil.copytree(self.dirs["sesgo_decision"], dst_sin)
            (dst_sin / "marcas" / "mount0_Ha.json").unlink()
            rep_sin = mod.evaluate(dst_sin)
        boca_bias = [r for r in self._tsesgo(mod, rep_bias, reading="a") if r["feature"] == "boca_anillo"]
        self.assertTrue(boca_bias and all(r["verdict"] == "FALLA" for r in boca_bias), boca_bias)
        self.assertEqual(rep_bias["decisions"], rep_sin["decisions"], (rep_bias["decisions"], rep_sin["decisions"]))
        self.assertEqual(rep_bias["exit_code"], rep_sin["exit_code"], (rep_bias["exit_code"], rep_sin["exit_code"]))
        self.assertEqual(rep_bias["decisions"]["lectura"], "a", rep_bias["decisions"])
        rep_p = mod.evaluate(self.dirs["sesgo_decision_pocas"])
        boca_p = [r for r in self._tsesgo(mod, rep_p, reading="a") if r["feature"] == "boca_anillo"]
        self.assertTrue(boca_p and all(r["verdict"] == "INCONCLUSO" and r["cause"] == "sesgo_no_observable" for r in boca_p), boca_p)
        self.assertEqual(rep_p["decisions"]["lectura"], "a", rep_p["decisions"])


if __name__ == "__main__":
    unittest.main()

