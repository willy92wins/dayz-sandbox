"""T-lect directa de lookat/follow (contrato §35). Tests pedidos por el coordinador (26-nov 15:39Z):
lectura desplazada 5 px en posicion -> FALLA; error de 3 grados en el angulo predicho sin deriva -> PASA;
fondo cambiante -> PASA. Mas: el punto fijo de la HUD no atrae la deteccion."""
import importlib.util
import math
import unittest
from pathlib import Path

import numpy as np

_P = Path(__file__).resolve().parents[1] / "tlect_direct.py"
_spec = importlib.util.spec_from_file_location("tlect_direct", _P)
TD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TD)

H, W = 400, 400


def _fondo(seed):
    rng = np.random.default_rng(seed)
    f = rng.uniform(40, 200, size=(H, W))
    k = np.ones((3, 3)) / 9.0
    return np.real(np.fft.ifft2(np.fft.fft2(f) * np.fft.fft2(k, s=f.shape)))


SS = 4  # supersampling: el motor entrega imagen suavizada; dibujar sin antialiasing crea patrones falsos al girar


def _escena(boca, ang, pxm, seed, hud=None):
    """Cañon con anillos cada 2 cm y ranuras en el apagallamas, desde `boca` en la direccion `ang` (hacia la recamara),
    dibujado a SS x y reducido (antialiasing)."""
    img = _fondo(seed)
    yy, xx = np.mgrid[0:H * SS, 0:W * SS].astype(np.float64)
    x, y = (xx + 0.5) / SS - 0.5 - boca[0], (yy + 0.5) / SS - 0.5 - boca[1]
    t = (x * math.cos(ang) + y * math.sin(ang)) / pxm          # m a lo largo
    s = (-x * math.sin(ang) + y * math.cos(ang)) / pxm         # m de traves
    dentro = (t >= 0) & (t <= 0.30) & (np.abs(s) <= 0.011)
    val = 110 + 50 * np.sin(2 * math.pi * t / 0.02) + np.where(t < 0.05, 45 * np.sign(np.sin(2 * math.pi * s / 0.008)), 0)
    alto = np.repeat(np.repeat(img, SS, axis=0), SS, axis=1)
    alto[dentro] = val[dentro]
    img = alto.reshape(H, SS, W, SS).mean(axis=(1, 3))
    if hud is not None:
        img[int(hud[1]) - 1:int(hud[1]) + 2, int(hud[0]) - 1:int(hud[0]) + 2] = 255.0
    return img


BOCA0, ANG0, PXM0 = (200.0, 200.0), math.radians(30), 400.0


class TLectDirecta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pl = TD.Plantilla(_escena(BOCA0, ANG0, PXM0, 1), BOCA0, ANG0, PXM0)

    def _derivas(self, casos):
        out = []
        for boca, ang, pxm, seed, lect_boca, lect_ang in casos:
            img = _escena(boca, ang, pxm, seed)
            det = TD.detectar(self.pl, img, lect_boca, lect_ang, pxm)
            self.assertTrue(TD.aceptada(det), det)
            out.append(math.hypot(det[0] - lect_boca[0], det[1] - lect_boca[1]))
        return out

    def test_lectura_desplazada_5px_falla(self):
        casos = []
        for i in range(25):
            ang = ANG0 + math.radians(4 * i)
            boca = (200.0 + (i % 5), 200.0 - (i % 3))
            lect = (boca[0] + 5.0, boca[1])          # la lectura dice 5 px a la derecha
            casos.append((boca, ang, PXM0, 1, lect, ang))
        d = self._derivas(casos)
        v = TD.veredicto(d, 25)
        self.assertEqual(v["verdict"], "FALLA", v)
        self.assertAlmostEqual(v["p95_px"], 5.0, delta=0.6)

    def test_error_de_angulo_3_grados_sin_deriva_pasa(self):
        casos = []
        for i in range(25):
            ang = ANG0 + math.radians(7 * i)
            boca = (195.0 + i % 7, 205.0 - i % 4)
            casos.append((boca, ang, PXM0, 1, boca, ang + math.radians(3.0)))
        d = self._derivas(casos)
        v = TD.veredicto(d, 25)
        self.assertEqual(v["verdict"], "PASA", v)

    def test_fondo_cambiante_y_arma_girando_pasa(self):
        casos = []
        for i in range(25):
            ang = ANG0 + math.radians(13 * i)
            pxm = PXM0 * (0.85 + 0.012 * i)
            boca = (190.0 + 0.7 * i, 210.0 - 0.4 * i)
            casos.append((boca, ang, pxm, 100 + i, boca, ang))
        d = self._derivas(casos)
        v = TD.veredicto(d, 25)
        self.assertEqual(v["verdict"], "PASA", v)

    def test_punto_hud_borrado_no_atrae(self):
        # la boca a 6 px del punto fijo; sin borrarlo, el punto (borde fuerte y fijo) podria enganchar la busqueda
        hud = (206.0, 200.0)
        img = _escena(BOCA0, ANG0 + 0.3, PXM0, 7, hud=hud)
        img = TD.borrar_hud(img, centro=hud)
        det = TD.detectar(self.pl, img, BOCA0, ANG0 + 0.3, PXM0)
        self.assertLess(math.hypot(det[0] - BOCA0[0], det[1] - BOCA0[1]), 1.0, det)

    def test_banco_nunca_usa_su_propio_giro_y_respeta_la_vista(self):
        def v(deg):
            a = math.radians(deg)
            return np.array([math.cos(a), 0.0, math.sin(a)])
        banco = [{"giro": 1, "vista": v(0), "pl": "g1_0"}, {"giro": 2, "vista": v(8), "pl": "g2_8"},
                 {"giro": 3, "vista": v(30), "pl": "g3_30"}]
        self.assertEqual(TD.elegir_plantilla(banco, v(1), 1)["pl"], "g2_8")      # la de su giro (0 grados) no vale
        self.assertEqual(TD.elegir_plantilla(banco, v(1), 2)["pl"], "g1_0")
        self.assertIsNone(TD.elegir_plantilla(banco, v(19), 1))                # g2 y g3 a 11 grados > 10
        self.assertEqual(TD.elegir_plantilla(banco, v(25), 1)["pl"], "g3_30")  # 5 grados

    def test_deteccion_ambigua_se_descarta(self):
        # dos cañones identicos a 20 px sobre fondo uniforme: dos picos casi iguales -> no aceptada (no se elige uno)
        def pegar(img, boca):
            e = _escena(boca, ANG0, PXM0, 1)
            return np.where(np.abs(e - _fondo(1)) > 1e-6, e, img)
        img = np.full((H, W), 120.0)
        img = pegar(img, BOCA0)
        img = pegar(img, (BOCA0[0] + 20 * math.cos(ANG0 + math.pi / 2), BOCA0[1] + 20 * math.sin(ANG0 + math.pi / 2)))
        det = TD.detectar(self.pl, img, BOCA0, ANG0, PXM0)
        self.assertFalse(TD.aceptada(det), det)

    def test_veredicto_poca_cobertura_inconcluso(self):
        v = TD.veredicto([0.5] * 21, 25)
        self.assertEqual(v["verdict"], "INCONCLUSO")
        self.assertEqual(v["cause"], "low_coverage")


if __name__ == "__main__":
    unittest.main()
