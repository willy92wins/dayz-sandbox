"""T-hook de mount por medida directa (contrato §34): deriva sintética 5 px → FALLA; roll 1° → FALLA; brillo 63→119 → PASA."""
import importlib.util
import math
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

_P = Path(__file__).resolve().parents[1] / "thook_mount.py"
_spec = importlib.util.spec_from_file_location("thook_mount", _P)
TM = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TM)

RNG = np.random.default_rng(7)
BASE = RNG.uniform(0, 255, size=(600, 600))
# textura suave (como una superficie del arma) para que la correlacion sea estable
K = np.ones((5, 5)) / 25.0
BASE = np.real(np.fft.ifft2(np.fft.fft2(BASE) * np.fft.fft2(K, s=BASE.shape)))
C1, C2 = (300.0, 400.0), (300.0, 180.0)  # 220 px de separacion


def _shift(img, dx, dy):
    return np.roll(np.roll(img, int(dy), axis=0), int(dx), axis=1)


def _rotate(img, deg):
    pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    return np.asarray(pil.rotate(deg, resample=Image.BICUBIC, center=C1), dtype=np.float64)


def _brightness(img, mean_target):
    return np.clip(img * (mean_target / img.mean()), 0, 255)


class THookMount(unittest.TestCase):
    def _verdict(self, imgs):
        meas = TM.measure_images(BASE, imgs, C1, C2)
        return TM.verdict(meas)

    def test_sin_movimiento_pasa(self):
        res = self._verdict([BASE.copy() for _ in range(25)])
        self.assertEqual(res["verdict"], "PASA", res)

    def test_deriva_5px_falla(self):
        res = self._verdict([_shift(BASE, 5, 0) for _ in range(25)])
        self.assertEqual(res["verdict"], "FALLA", res)
        self.assertEqual(res["cause"], "p95_px_exceeded")
        self.assertAlmostEqual(res["p95_px"], 5.0, delta=0.3)

    def test_roll_1_grado_falla(self):
        imgs = [_rotate(BASE, 1.0) for _ in range(25)]
        res = self._verdict(imgs)
        self.assertEqual(res["verdict"], "FALLA", res)
        # el roll de 1 grado alrededor de la recamara mueve el segundo cultivo ~3,8 px: falla por deriva o por roll
        self.assertIn(res["cause"], ("p95_px_exceeded", "roll_exceeded"))

    def test_roll_pequeno_detectado_como_roll(self):
        # 0,8 grados con el segundo cultivo a 220 px: desplazamiento ~3 px; el angulo medido es ~0,8 grados
        meas = TM.measure_images(BASE, [_rotate(BASE, 0.8)], C1, C2)
        self.assertAlmostEqual(meas[0][1], 0.8, delta=0.25)

    def test_cambio_de_brillo_sin_movimiento_pasa(self):
        imgs = [_brightness(BASE, m) for m in np.linspace(63, 119, 25)]
        res = self._verdict(imgs)
        self.assertEqual(res["verdict"], "PASA", res)

    def test_deriva_grande_20px_falla_y_se_mide(self):
        # en mount0_Ha el arma se desplaza hasta ±23 px: una deriva grande debe dar FALLA medida, no INCONCLUSO
        res = self._verdict([_shift(BASE, -20, 12) for _ in range(25)])
        self.assertEqual(res["verdict"], "FALLA", res)
        self.assertAlmostEqual(res["p95_px"], math.hypot(20, 12), delta=0.5)

    def test_arma_mas_cerca_y_desplazada_falla_y_se_mide(self):
        # como mount0_Ha: lo dibujado sale ~20 % mas grande y desplazado (+60, +40 px) respecto a la referencia
        pil = Image.fromarray(np.clip(BASE, 0, 255).astype(np.uint8))
        z = 1.2
        big = pil.resize((int(600 * z), int(600 * z)), Image.BICUBIC)
        # el punto C1 de la referencia acaba en C1 + (60, 40) en la imagen nueva
        ox, oy = int(round(C1[0] * z - (C1[0] + 60))), int(round(C1[1] * z - (C1[1] + 40)))
        img = np.asarray(big.crop((ox, oy, ox + 600, oy + 600)), dtype=np.float64)
        meas = TM.measure_images(BASE, [img], C1, C2)
        self.assertIsNotNone(meas[0])
        d1 = meas[0][0]
        self.assertGreater(d1, 2.0)
        res = TM.verdict(meas * 25)
        self.assertEqual(res["verdict"], "FALLA", res)
        self.assertGreater(meas[0][2], TM.CALIDAD_MIN)

    def test_deriva_subpixel_bajo_umbral_pasa(self):
        # 1,5 px (desplazamiento subpixel por interpolacion) queda bajo el umbral de 2 px
        sub = np.real(np.fft.ifft2(np.fft.fft2(BASE) * np.exp(-2j * np.pi * np.fft.fftfreq(600)[None, :] * 1.5)))
        res = self._verdict([sub for _ in range(25)])
        self.assertEqual(res["verdict"], "PASA", res)
        self.assertAlmostEqual(res["p95_px"], 1.5, delta=0.3)

    def test_cultivos_evitan_el_punto_de_la_hud(self):
        # konec se proyecta al centro exacto (camara en el eje del cañon), donde esta el punto fijo de la HUD
        cam = {"pos": [0, 0, 0], "x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
        lect = {"konec hlavne": {"a": [0, 0, 1]}, "usti hlavne": {"a": [0, 0.4, 1]}}
        rows = [{"frame": 30, "giro": 0, "shot": "f000030.bmp", "cam": cam, "lecturas": lect},
                {"frame": 29, "giro": 0, "cam": cam, "lecturas": lect}]
        rows.sort(key=lambda r: r["frame"])
        _, (c1, c2, sep) = TM.crop_centers(rows, -1, 900.0)
        self.assertFalse(TM._toca_hud(c1))
        self.assertFalse(TM._toca_hud(c2))
        self.assertGreater(c1[1], 540.0)  # se aleja de la boca (que esta arriba)
        self.assertAlmostEqual(math.hypot(c2[0] - c1[0], c2[1] - c1[1]), 200.0, delta=0.01)

    def test_emparejamiento_espurio_no_rigido_se_descarta(self):
        # como Hb giro3: el cultivo 1 se mueve 5 px y el 2 "salta" 60 px a lo largo del cañon (nervios repetidos)
        img = _shift(BASE, 0, 5)
        img[:330, :] = _shift(BASE, 0, 60)[:330, :]
        meas = TM.measure_images(BASE, [img], C1, C2)
        self.assertFalse(meas[0][3])
        res = TM.verdict(meas * 25)
        self.assertEqual(res["verdict"], "INCONCLUSO", res)
        self.assertEqual(res["cause"], "cultivos_no_rigidos")

    def test_rigido_con_escala(self):
        c1, c2 = (300.0, 400.0), (300.0, 180.0)
        self.assertTrue(TM.es_rigido(c1, c2, (60, 40, 0.9, 1.2), (60, 40 - 0.2 * 220, 0.9, 1.2)))
        self.assertFalse(TM.es_rigido(c1, c2, (60, 40, 0.9, 1.2), (60, 40, 0.9, 1.0)))

    def test_pocas_capturas_inconcluso(self):
        res = self._verdict([BASE.copy() for _ in range(15)])
        self.assertEqual(res["verdict"], "INCONCLUSO", res)


if __name__ == "__main__":
    unittest.main()
