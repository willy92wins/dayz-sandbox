"""Tests del detector y de la segmentacion de giros (orquestador, 2026-11-11).

- La calibracion del detector rechaza un caso impreciso pero detectable (franjas: problema de apertura,
  p95 de decenas de px). Mata al mutante `detector_laxo` (DETECTOR_MAX_PX/DEG relajados).
- Control positivo: sobre motivos con textura la calibracion PASA.
- La segmentacion encuentra exactamente 3 giros reales (> 90 deg, >= 0,5 s) con ruido de rumbo,
  e ignora oscilaciones de < 90 deg y giros de > 90 deg mas cortos de 0,5 s.

Cargan el evaluador desde STRACK_EVAL_PATH si existe, como los demas tests.
"""

import importlib.util
import math
import os
import random
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
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _eval_path():
    env_val = os.environ.get("STRACK_EVAL_PATH")
    return Path(env_val).resolve() if env_val else DEFAULT_EVAL_PATH.resolve()


def _fake_run(run_dir, img_u8):
    """Una corrida mount0_Ha de un frame: camara en el origen mirando +z, boca y recamara a 274 px (f = 684)."""
    Image.fromarray(img_u8).convert("RGB").save(run_dir / "f000001.png")
    cam = {"pos": [0.0, 0.0, 0.0], "x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}
    row = {
        "frame": 1, "shot": "f000001.bmp", "hook": "Ha", "caso": "mount0", "inject": "none",
        "cam": cam, "fov_rad": 1.0471976,
        "lecturas": {"usti hlavne": {"a": [-0.2, 0.0, 1.0]}, "konec hlavne": {"a": [0.2, 0.0, 1.0]}},
    }
    return {"dir": run_dir, "run": "mount0_Ha", "caso": "mount0", "hook": "Ha", "inject": "none",
            "samples": [row], "by_frame": {1: row}}


def _turn_samples(segments, fps=60.0, noise_deg=1.5, seed=7):
    """Muestras con el rumbo de la recta boca->recamara siguiendo `segments` = [(duracion_s, grados), ...]."""
    rng = random.Random(seed)
    rows = []
    yaw = 0.0
    frame = 0
    t = 0.0
    for dur, delta in segments:
        n = max(1, int(round(dur * fps)))
        for i in range(n):
            yaw += delta / n
            y = math.radians(yaw + rng.uniform(-noise_deg, noise_deg))
            usti = [0.0, 1.5, 0.0]
            konec = [0.5 * math.sin(y), 1.5, 0.5 * math.cos(y)]
            rows.append({"frame": frame, "t_ms": t * 1000.0, "dt": 1.0 / fps,
                         "lecturas": {"usti hlavne": {"a": usti}, "konec hlavne": {"a": konec}},
                         "cam": {"pos": [0, 0, 0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}})
            frame += 1
            t += 1.0 / fps
    return rows


class DetectorAndWindowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ev = _load_module(_eval_path(), "strack_eval_det_win")
        cls.fx = _load_module(FIXTURES_MOD_PATH, "strack_fixtures_det_win")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_detector_rejects_ambiguous_stripes(self):
        d = self.tmp / "stripes"
        d.mkdir()
        img = 128.0 + 60.0 * np.cos(2.0 * np.pi * np.arange(1920) / 9.0)[None, :].repeat(1080, 0)
        res = self.ev.calibrate_detector([_fake_run(d, np.clip(img, 0, 255).astype(np.uint8))], {"Ha": 0}, {"Ha": 684.0})
        # Detecta (error finito) pero impreciso: tiene que salir INCONCLUSO con los umbrales del contrato.
        self.assertLess(res["p95_px"], 99.0)
        self.assertGreater(res["p95_px"], self.ev.DETECTOR_MAX_PX)
        self.assertEqual(res["verdict"], "INCONCLUSO")

    def test_detector_passes_on_textured_motifs(self):
        d = self.tmp / "motifs"
        d.mkdir()
        img = self.fx._slice_background(0.0).copy()
        self.fx._stamp_motif(img, 960.0 - 136.8, 540.0, kind="usti")
        self.fx._stamp_motif(img, 960.0 + 136.8, 540.0, kind="konec")
        # Vuelta 2 (hallazgos 1-3): mascaras locales por detalle y fondos distintos.
        yy, xx = np.mgrid[0:48, 0:48]
        disc = ((xx - 23.5) ** 2 + (yy - 23.5) ** 2) <= (16.0 ** 2)
        masks = {"usti hlavne": disc, "konec hlavne": disc}
        bgs = [self.fx._slice_background(300.0), self.fx._slice_background(700.0)]
        res = self.ev.calibrate_detector([_fake_run(d, np.clip(img, 0, 255).astype(np.uint8))], {"Ha": 0}, {"Ha": 684.0}, template_mask=masks, background_images=bgs)
        self.assertEqual(res["verdict"], "PASA", res)
        self.assertLessEqual(res["p95_bg_px"], self.ev.DETECTOR_MAX_PX, res)

    def test_windows_three_real_turns_with_noise(self):
        segs = [(3.0, 5.0), (1.75, 180.0), (3.0, -4.0), (3.0, 3.0), (1.75, -180.0), (3.0, 2.0),
                (3.0, -3.0), (1.75, 180.0), (3.0, 0.0)]
        w = self.ev.detect_windows(_turn_samples(segs))
        giros = sorted(k for k in w if k.startswith("giro"))
        self.assertEqual(giros, ["giro1", "giro2", "giro3"])

    def test_windows_ignore_small_swings_and_fast_flicks(self):
        # 60 deg en 1 s (poco giro) y 100 deg en 0,3 s (demasiado corto): ninguno es giro.
        segs = [(2.0, 0.0), (1.0, 60.0), (2.0, 0.0), (0.3, 100.0), (2.0, 0.0), (1.0, -60.0), (2.0, 0.0)]
        w = self.ev.detect_windows(_turn_samples(segs))
        self.assertEqual(sorted(k for k in w if k.startswith("giro")), [])


if __name__ == "__main__":
    unittest.main()
