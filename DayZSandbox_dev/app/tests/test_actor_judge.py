"""T-J1..T-J6 (F3-offline-1 §8.2): jueces con muestras a mano y why exacto."""
import unittest

from app.backend import actor_judge as aj

CLS = "SurvivorM_Mirek"
ITEMS = [
    "GorkaEJacket_Flat",
    "GorkaPants_Flat",
    "MilitaryBoots_Black",
    "TacticalGloves_Black",
    "BalaclavaMask_Black",
]
EXPECTED = {"cls": CLS, "items": list(ITEMS)}
MARK = {"x": 100.0, "z": 200.0}
P0 = {"x": 100.0, "z": 200.0}


def _mm(m):
    return round(m * 1000)


def _row(t_ms, x_m, z_m, lid="act-01", mark_i=0, mark_st="moving", items=None, cls=CLS):
    return [
        lid,
        cls,
        _mm(x_m),
        0,
        _mm(z_m),
        0,
        list(ITEMS if items is None else items),
        mark_i,
        mark_st,
        t_ms,
    ]


def _dead(t_ms=0, lid="act-01"):
    return [lid, None, None, None, None, None, [], -1, "idle", t_ms]


def _gev(st, t_ms, lid="act-01", gi=0, cause=None):
    return [lid, gi, st, t_ms, cause]


class TJ1C1(unittest.TestCase):
    def test_mismo_multiconjunto_otro_orden(self):
        row = _row(0, 100, 200, items=list(reversed(ITEMS)))
        r = aj.judge_identity(EXPECTED, row)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])

    def test_prenda_de_menos(self):
        row = _row(0, 100, 200, items=ITEMS[:-1])
        r = aj.judge_identity(EXPECTED, row)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "vestuario")
        self.assertEqual(r["faltan"], [ITEMS[-1]])

    def test_prenda_de_mas(self):
        row = _row(0, 100, 200, items=ITEMS + ["Hoodie_Grey"])
        r = aj.judge_identity(EXPECTED, row)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "vestuario")
        self.assertEqual(r["sobran"], ["Hoodie_Grey"])

    def test_multiconjunto_duplicada(self):
        got = ITEMS[:-1] + [ITEMS[0]]
        row = _row(0, 100, 200, items=got)
        r = aj.judge_identity(EXPECTED, row)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "vestuario")
        self.assertEqual(r["faltan"], [ITEMS[-1]])
        self.assertEqual(r["sobran"], [ITEMS[0]])

    def test_otra_clase(self):
        row = _row(0, 100, 200, cls="SurvivorF_Eva")
        r = aj.judge_identity(EXPECTED, row)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "clase")

    def test_muerto(self):
        r = aj.judge_identity(EXPECTED, _dead())
        self.assertEqual(r["verdict"], "INCONCLUSO")
        self.assertEqual(r["why"], "muerto")


class TJ2C2(unittest.TestCase):
    def test_llega_y_se_queda(self):
        # 1,4 m de la marca y 10 s dentro de 0,4 m de t0.
        samples = [_row(t, 101.4, 200.0) for t in range(0, 11001, 1000)]
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])
        self.assertEqual(r["t0"], 0)

    def test_marca_de_paso(self):
        samples = [_row(0, 101.0, 200.0)]
        r = aj.judge_mark(samples, 0, MARK, settle_ms=0)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])

    def test_se_queda_a_1_6(self):
        samples = [_row(t, 101.6, 200.0) for t in range(0, 11001, 1000)]
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "no_llega")

    def test_1_5_m_justos(self):
        samples = [_row(t, 101.5, 200.0) for t in range(0, 11001, 1000)]
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "no_llega")

    def test_llega_y_se_va(self):
        samples = [_row(t, 101.0, 200.0) for t in range(0, 8000, 1000)]
        samples.append(_row(8000, 101.6, 200.0))
        samples.extend(_row(t, 101.6, 200.0) for t in range(9000, 11001, 1000))
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "no_quieto")

    def test_deriva_0_5_m_justos(self):
        samples = [_row(t, 101.0, 200.0) for t in range(0, 8000, 1000)]
        samples.append(_row(8000, 101.5, 200.0))
        samples.extend(_row(t, 101.5, 200.0) for t in range(9000, 11001, 1000))
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "no_quieto")

    def test_unreachable_esta_marca(self):
        samples = [_row(t, 101.0, 200.0, mark_st="unreachable") for t in range(0, 11001, 1000)]
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "FALLA")
        self.assertEqual(r["why"], "inalcanzable")

    def test_unreachable_otra_marca_pasa(self):
        samples = [_row(t, 101.0, 200.0, mark_i=1, mark_st="unreachable") for t in range(0, 11001, 1000)]
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])

    def test_hueco_1_5_s(self):
        times = [0, 1000, 2000, 3500, 4500, 5500, 6500, 7500, 8500, 9500, 10500]
        samples = [_row(t, 101.0, 200.0) for t in times]
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "INCONCLUSO")
        self.assertEqual(r["why"], "sin_cobertura")

    def test_traza_corta(self):
        samples = [_row(t, 101.0, 200.0) for t in range(0, 8001, 1000)]
        r = aj.judge_mark(samples, 0, MARK)
        self.assertEqual(r["verdict"], "INCONCLUSO")
        self.assertEqual(r["why"], "sin_cobertura")


class TJ3C3(unittest.TestCase):
    def test_secuencia_sana(self):
        ev = [
            _gev("requested", 0),
            _gev("playing", 10),
            _gev("finished", 2010),
        ]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])

    def test_requested_playing_mismo_t(self):
        ev = [
            _gev("requested", 5),
            _gev("playing", 5),
            _gev("finished", 2005),
        ]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])

    def test_fin_sin_empezar(self):
        ev = [_gev("requested", 0), _gev("finished", 10)]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "fin_sin_empezar"))

    def test_cancelado_tras_playing(self):
        ev = [
            _gev("requested", 0),
            _gev("playing", 10),
            _gev("canceled", 20, cause="interrupted"),
        ]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "cancelado"))

    def test_cancelado_sin_playing(self):
        ev = [_gev("requested", 0), _gev("canceled", 10, cause="stop")]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "cancelado"))

    def test_rechazado(self):
        ev = [_gev("requested", 0), _gev("rejected", 10, cause="combat")]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "rechazado"))

    def test_agotado(self):
        ev = [_gev("requested", 0), _gev("expired", 100, cause="timeout")]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "agotado"))

    def test_despues_del_fin(self):
        ev = [
            _gev("requested", 0),
            _gev("expired", 50, cause="timeout"),
            _gev("playing", 60),
            _gev("finished", 2060),
        ]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "despues_del_fin"))

    def test_sin_pedido(self):
        ev = [_gev("playing", 0), _gev("finished", 10)]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "sin_pedido"))

    def test_repetido(self):
        ev = [_gev("requested", 0), _gev("requested", 10)]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "repetido"))

    def test_duracion_cero(self):
        ev = [
            _gev("requested", 0),
            _gev("playing", 10),
            _gev("finished", 10),
        ]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "duracion_cero"))

    def test_t_ms_baja(self):
        ev = [
            _gev("requested", 20),
            _gev("playing", 10),
            _gev("finished", 30),
        ]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("INCONCLUSO", "lectura_invalida"))

    def test_solo_requested(self):
        r = aj.judge_gesture([_gev("requested", 0)], "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("INCONCLUSO", "sin_fin"))

    def test_requested_playing_sin_fin(self):
        ev = [_gev("requested", 0), _gev("playing", 10)]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual((r["verdict"], r["why"]), ("INCONCLUSO", "sin_fin"))

    def test_otro_gi_no_cuenta(self):
        ev = [
            _gev("playing", 0, gi=1),
            _gev("requested", 0, gi=0),
            _gev("playing", 10, gi=0),
            _gev("finished", 2010, gi=0),
        ]
        r = aj.judge_gesture(ev, "act-01", 0)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])


class TJ4Hold(unittest.TestCase):
    def test_deriva_0_3(self):
        samples = [_row(0, 100.0, 200.0, mark_i=-1, mark_st="idle")]
        samples.append(_row(1000, 100.3, 200.0, mark_i=-1, mark_st="idle"))
        samples.append(_row(2000, 100.2, 200.0, mark_i=-1, mark_st="idle"))
        r = aj.judge_hold(samples, window_ms=2000)
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])

    def test_0_5_m_justos(self):
        samples = [
            _row(0, 100.0, 200.0, mark_i=-1, mark_st="idle"),
            _row(1000, 100.5, 200.0, mark_i=-1, mark_st="idle"),
        ]
        r = aj.judge_hold(samples, window_ms=1000)
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "se_mueve"))

    def test_hueco(self):
        samples = [
            _row(0, 100.0, 200.0, mark_i=-1, mark_st="idle"),
            _row(2500, 100.0, 200.0, mark_i=-1, mark_st="idle"),
        ]
        r = aj.judge_hold(samples, window_ms=2500)
        self.assertEqual((r["verdict"], r["why"]), ("INCONCLUSO", "sin_cobertura"))


def _roam_ok():
    """Radio 15, ≤15 m, 45 m de camino, 5 paradas de 1 s."""
    samples = []
    t = 0
    x, z = 100.0, 200.0
    legs = [(109.0, 200.0), (109.0, 209.0), (100.0, 209.0), (100.0, 200.0), (109.0, 200.0)]
    samples.append(_row(t, x, z, mark_i=-1, mark_st="idle"))
    t += 1000
    samples.append(_row(t, x, z, mark_i=-1, mark_st="idle"))
    for nx, nz in legs:
        t += 1000
        samples.append(_row(t, nx, nz, mark_i=-1, mark_st="moving"))
        t += 1000
        samples.append(_row(t, nx, nz, mark_i=-1, mark_st="idle"))
        x, z = nx, nz
    return samples, t


class TJ5Roam(unittest.TestCase):
    def test_pasa(self):
        samples, end = _roam_ok()
        r = aj.judge_roam(
            samples, P0, radius_m=15, window_ms=end, min_path_m=40, min_stops_n=4,
        )
        self.assertEqual(r["verdict"], "PASA")
        self.assertIsNone(r["why"])
        self.assertGreaterEqual(r["path_m"], 45.0 - 1e-9)
        self.assertGreaterEqual(r["stops_n"], 5)

    def test_muestra_intermedia_15_01(self):
        samples = [
            _row(0, 100.0, 200.0, mark_i=-1, mark_st="idle"),
            _row(1000, 115.01, 200.0, mark_i=-1, mark_st="moving"),
            _row(2000, 114.0, 200.0, mark_i=-1, mark_st="moving"),
        ]
        r = aj.judge_roam(
            samples, P0, radius_m=15, window_ms=2000, min_path_m=1, min_stops_n=0,
        )
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "fuera_radio"))
        self.assertAlmostEqual(r["max_dist_m"], 15.01, places=5)

    def test_recorrido_corto(self):
        samples = []
        t = 0
        for i in range(5):
            samples.append(_row(t, 100.0 + i * 1.5, 200.0, mark_i=-1, mark_st="idle"))
            t += 1000
            samples.append(_row(t, 100.0 + i * 1.5, 200.0, mark_i=-1, mark_st="idle"))
            t += 1000
        r = aj.judge_roam(
            samples, P0, radius_m=15, window_ms=t - 1000, min_path_m=40, min_stops_n=4,
        )
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "quieto"))

    def test_pocas_paradas(self):
        # 45 m recorridos en tres tramos de 15 m, con solo 3 paradas de 1 s.
        samples = [_row(0, 100.0, 200.0, mark_i=-1, mark_st="moving")]
        x = 100.0
        t = 0
        for _leg in range(3):
            for _i in range(3):
                x += 5.0
                t += 1000
                samples.append(_row(t, x, 200.0, mark_i=-1, mark_st="moving"))
            t += 1000
            samples.append(_row(t, x, 200.0, mark_i=-1, mark_st="idle"))
        t += 1000
        samples.append(_row(t, x + 5.0, 200.0, mark_i=-1, mark_st="moving"))
        r = aj.judge_roam(
            samples,
            P0,
            radius_m=50,
            window_ms=t,
            min_path_m=40,
            min_stops_n=4,
        )
        self.assertEqual((r["verdict"], r["why"]), ("FALLA", "quieto"))
        self.assertGreaterEqual(r["path_m"], 45.0)
        self.assertEqual(r["stops_n"], 3)

    def test_hueco(self):
        samples = [
            _row(0, 100.0, 200.0, mark_i=-1, mark_st="idle"),
            _row(2500, 109.0, 200.0, mark_i=-1, mark_st="moving"),
        ]
        r = aj.judge_roam(
            samples, P0, radius_m=15, window_ms=2500, min_path_m=1, min_stops_n=0,
        )
        self.assertEqual((r["verdict"], r["why"]), ("INCONCLUSO", "sin_cobertura"))


class TJ6LecturaMala(unittest.TestCase):
    def test_fila_invalida_cada_juez(self):
        bad = _row(0, 100, 200)
        bad[2] = 100000.0
        self.assertEqual(
            aj.judge_identity(EXPECTED, bad)["why"], "lectura_invalida",
        )
        self.assertEqual(
            aj.judge_mark([bad], 0, MARK)["why"], "lectura_invalida",
        )
        self.assertEqual(
            aj.judge_hold([bad], 1000)["why"], "lectura_invalida",
        )
        self.assertEqual(
            aj.judge_roam([bad], P0, 15, 1000, 40, 4)["why"], "lectura_invalida",
        )
        bad_ev = _gev("canceled", 0, cause=None)
        self.assertEqual(
            aj.judge_gesture([bad_ev], "act-01", 0)["why"], "lectura_invalida",
        )

    def test_dos_lid(self):
        samples = [_row(0, 100, 200, lid="act-01"), _row(1000, 100, 200, lid="act-02")]
        self.assertEqual(aj.judge_mark(samples, 0, MARK)["why"], "lectura_invalida")
        self.assertEqual(
            aj.judge_roam(samples, P0, 15, 1000, 40, 4)["why"], "lectura_invalida",
        )

    def test_t_ms_repetido(self):
        samples = [_row(0, 100, 200), _row(0, 101, 200)]
        self.assertEqual(aj.judge_mark(samples, 0, MARK)["why"], "lectura_invalida")
        self.assertEqual(
            aj.judge_roam(samples, P0, 15, 1000, 40, 4)["why"], "lectura_invalida",
        )

    def test_lista_vacia(self):
        self.assertEqual(aj.judge_mark([], 0, MARK)["why"], "sin_cobertura")
        self.assertEqual(aj.judge_hold([], 1000)["why"], "sin_cobertura")
        self.assertEqual(aj.judge_roam([], P0, 15, 1000, 40, 4)["why"], "sin_cobertura")


if __name__ == "__main__":
    unittest.main()
