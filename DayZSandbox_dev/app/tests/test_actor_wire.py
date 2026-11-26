"""T-A1, T-A2 y T-A3 (F3-offline-1 §8.1): validadores de actor_wire."""
import unittest

from app.backend import actor_wire as aw

CLS = "SurvivorM_Mirek"
ITEMS = [
    "GorkaEJacket_Flat",
    "GorkaPants_Flat",
    "MilitaryBoots_Black",
    "TacticalGloves_Black",
    "BalaclavaMask_Black",
]


def _live(lid="act-01", t_ms=0, mark_i=0, mark_st="moving", items=None, **kw):
    x = kw.get("x_mm", 100000)
    y = kw.get("y_mm", 0)
    z = kw.get("z_mm", 200000)
    yaw = kw.get("yaw_mdeg", 0)
    cls = kw.get("cls", CLS)
    return [lid, cls, x, y, z, yaw, list(ITEMS if items is None else items), mark_i, mark_st, t_ms]


def _dead(lid="act-01", t_ms=0):
    return [lid, None, None, None, None, None, [], -1, "idle", t_ms]


def _gev(lid="act-01", gi=0, st="requested", t_ms=0, cause=None):
    return [lid, gi, st, t_ms, cause]


class TA1Fila(unittest.TestCase):
    def test_viva_valida(self):
        self.assertTrue(aw.valid_actor_row(_live()))

    def test_muerto_exacto(self):
        self.assertTrue(aw.valid_actor_row(_dead()))

    def test_float_en_x_mm(self):
        row = _live()
        row[2] = 100000.0
        self.assertFalse(aw.valid_actor_row(row))

    def test_bool_en_mark_i(self):
        row = _live()
        row[7] = True
        self.assertFalse(aw.valid_actor_row(row))

    def test_mark_st_desconocido(self):
        self.assertFalse(aw.valid_actor_row(_live(mark_st="walking")))

    def test_mark_i_menos_uno_con_arrived(self):
        self.assertFalse(aw.valid_actor_row(_live(mark_i=-1, mark_st="arrived")))

    def test_lid_obj(self):
        self.assertFalse(aw.valid_actor_row(_live(lid="obj-01")))

    def test_items_33(self):
        items = ["Shirt"] * 33
        self.assertFalse(aw.valid_actor_row(_live(items=items)))

    def test_muerto_cls_no_nulo(self):
        row = _dead()
        row[1] = CLS
        self.assertFalse(aw.valid_actor_row(row))

    def test_nueve_campos(self):
        self.assertFalse(aw.valid_actor_row(_live()[:9]))

    def test_once_campos(self):
        self.assertFalse(aw.valid_actor_row(_live() + [0]))


class TA2Evento(unittest.TestCase):
    def test_seis_st(self):
        self.assertTrue(aw.valid_gesture_event(_gev(st="requested", cause=None)))
        self.assertTrue(aw.valid_gesture_event(_gev(st="playing", cause=None)))
        self.assertTrue(aw.valid_gesture_event(_gev(st="finished", cause=None)))
        self.assertTrue(aw.valid_gesture_event(_gev(st="canceled", cause="interrupted")))
        self.assertTrue(aw.valid_gesture_event(_gev(st="rejected", cause="combat")))
        self.assertTrue(aw.valid_gesture_event(_gev(st="expired", cause="timeout")))

    def test_cause_no_nula_con_finished(self):
        self.assertFalse(aw.valid_gesture_event(_gev(st="finished", cause="ok")))

    def test_cause_nula_con_canceled(self):
        self.assertFalse(aw.valid_gesture_event(_gev(st="canceled", cause=None)))

    def test_cause_nula_con_rejected(self):
        self.assertFalse(aw.valid_gesture_event(_gev(st="rejected", cause=None)))

    def test_cause_nula_con_expired(self):
        self.assertFalse(aw.valid_gesture_event(_gev(st="expired", cause=None)))

    def test_cause_mayusculas(self):
        self.assertFalse(aw.valid_gesture_event(_gev(st="canceled", cause="Combat")))

    def test_gi_64(self):
        self.assertFalse(aw.valid_gesture_event(_gev(gi=64)))


class TA3Lectura(unittest.TestCase):
    def test_dos_actores(self):
        read = {
            "actors": [_live("act-01", t_ms=0), _live("act-02", t_ms=10)],
            "gestures": [
                _gev("act-01", 0, "requested", 0, None),
                _gev("act-01", 0, "playing", 10, None),
            ],
        }
        self.assertTrue(aw.valid_actor_read(read))

    def test_lid_repetido(self):
        read = {
            "actors": [_live("act-01", t_ms=0), _live("act-01", t_ms=10)],
            "gestures": [],
        }
        self.assertFalse(aw.valid_actor_read(read))

    def test_clave_extra(self):
        read = {
            "actors": [_live()],
            "gestures": [],
            "extra": 1,
        }
        self.assertFalse(aw.valid_actor_read(read))

    def test_t_ms_baja_mismo_par(self):
        read = {
            "actors": [_live("act-01")],
            "gestures": [
                _gev("act-01", 0, "requested", 20, None),
                _gev("act-01", 0, "playing", 10, None),
            ],
        }
        self.assertFalse(aw.valid_actor_read(read))

    def test_evento_lid_sin_fila(self):
        read = {
            "actors": [_live("act-01")],
            "gestures": [_gev("act-02", 0, "requested", 0, None)],
        }
        self.assertFalse(aw.valid_actor_read(read))

    def test_diecisiete_actores(self):
        actors = [_live("act-%02d" % i if i < 10 else "act-%d" % i) for i in range(1, 18)]
        self.assertEqual(len(actors), 17)
        self.assertFalse(aw.valid_actor_read({"actors": actors, "gestures": []}))


if __name__ == "__main__":
    unittest.main()
