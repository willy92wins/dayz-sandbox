"""F3-offline-2 §6, T-M1 y T-M2: el mod falso y el mundo falso con motor de actores."""
from __future__ import annotations

import copy
import types
import unittest

from app.backend.actor_wire import valid_actor_read
from app.tests.fake_mod import _Peer
from app.tests.fake_world import FakeWorld

SESSION = "a" * 16
HASH = "a" * 64
ITEMS = ["GorkaEJacket_Flat", "GorkaPants_Flat", "MilitaryBoots_Black",
         "TacticalGloves_Black", "BalaclavaMask_Black"]


def _args(lid="act-01", **kw):
    args = {
        "f2": 1, "doc_id": "d-7c19e2a4", "rev": 1, "hash": HASH,
        "a_lid": lid, "a_cls": "SurvivorM_Mirek",
        "a_x_mm": 6176000, "a_z_mm": 7632000, "a_yaw_mdeg": 35000,
        "a_items": list(ITEMS), "a_behaviour": "ONCE", "a_roam_mm": 15000,
        "mk_x_mm": [6181000, 6185000], "mk_z_mm": [7635000, 7639000],
        "g_emote": ["EmotePoint"], "g_at": [1], "g_t_ms": [-1],
    }
    args.update(kw)
    return args


def _order(verb="actor.apply", args=None, op_id="rd-1"):
    return {"op_id": op_id, "session": SESSION, "epoch": "e" * 32, "verb": verb,
            "args": args if args is not None else _args()}


def _stub(engine, world=None):
    finished = []
    world = world if world is not None else FakeWorld()
    stub = types.SimpleNamespace(
        fake=types.SimpleNamespace(world=world, actor_engine=engine),
        _check_before_effect=lambda _entry: None,
        _tick=lambda: None,
        _finish=lambda entry, status, reason, read: finished.append((status, reason, read)),
    )
    stub._execute_world = lambda entry, verb: _Peer._execute_world(stub, entry, verb)
    return stub, finished


class TM1FakeMod(unittest.TestCase):
    def test_sin_motor_rechaza_los_tres_verbos(self):
        for verb in ("actor.apply", "actor.reset", "actor.observe"):
            stub, finished = _stub("none")
            _Peer._execute(stub, types.SimpleNamespace(order=_order(verb, {"f2": 1, "doc_id": "d"})))
            self.assertEqual(finished, [("rejected", "expansion_unavailable", {})], verb)

    def test_con_motor_va_al_mundo(self):
        stub, finished = _stub("expansion")
        _Peer._execute(stub, types.SimpleNamespace(order=_order()))
        status, reason, read = finished[0]
        self.assertEqual((status, reason), ("done", None))
        self.assertTrue(valid_actor_read(read))
        self.assertEqual([r[0] for r in read["actors"]], ["act-01"])

    def test_sin_marca_f2_unknown_verb(self):
        stub, finished = _stub("expansion")
        args = _args()
        del args["f2"]
        _Peer._execute(stub, types.SimpleNamespace(order=_order(args=args)))
        self.assertEqual(finished, [("rejected", "unknown_verb", {})])

    def test_hello_lleva_el_motor_configurado(self):
        for engine in ("none", "expansion"):
            sent = []
            stub = types.SimpleNamespace(
                hello_attempts=0, role="server", inst="i" * 32, epoch="e" * 32,
                fake=types.SimpleNamespace(mod_ver="fake-1", world=None, actor_engine=engine),
                _http=lambda method, path, body, route=None: (sent.append(body), (500, None, 0, 0))[1],
            )
            self.assertFalse(_Peer._do_hello(stub))
            self.assertEqual(sent[0]["actor_engine"], engine)


class TM2FakeWorld(unittest.TestCase):
    def setUp(self):
        self.world = FakeWorld()
        self.eng = self.world.actors

    def test_apply_crea_y_filtra_la_foto(self):
        self.world.actor_apply(_order(args=_args("act-02", g_emote=["EmoteGreeting"],
                                                 g_at=[-1], g_t_ms=[0]), op_id="rd-2"))
        self.eng.step(100)  # el gesto por tiempo de act-02 ya se pidio
        status, reason, read = self.world.actor_apply(_order())
        self.assertEqual((status, reason), ("done", None))
        self.assertTrue(valid_actor_read(read))
        self.assertEqual([r[0] for r in read["actors"]], ["act-01"])
        self.assertEqual(read["gestures"], [])
        row = read["actors"][0]
        self.assertEqual((row[1], row[2], row[4], row[6]), ("SurvivorM_Mirek", 6176000, 7632000, ITEMS))

    def test_idempotencia_por_orden(self):
        self.world.actor_apply(_order())
        self.world.actor_apply(_order())
        self.assertEqual(self.eng.spawn_count, 1)
        self.world.actor_apply(_order(op_id="rd-9"))
        self.assertEqual(self.eng.spawn_count, 2)
        self.assertEqual(len(self.world.actor_observe(_order("actor.observe"))[2]["actors"]), 1)

    def test_reset_y_despawn_fails(self):
        self.world.actor_apply(_order())
        self.world.actor_apply(_order(args=_args("act-02"), op_id="rd-2"))
        self.eng.despawn_fails("act-02")
        status, _r, read = self.world.actor_reset(_order("actor.reset", {"f2": 1, "doc_id": "d"}))
        self.assertEqual(status, "done")
        self.assertTrue(valid_actor_read(read))
        self.assertEqual([r[0] for r in read["actors"]], ["act-02"])

    def test_reset_deja_vacio(self):
        self.world.actor_apply(_order())
        _s, _r, read = self.world.actor_reset(_order("actor.reset", {"f2": 1, "doc_id": "d"}))
        self.assertEqual(read, {"actors": [], "gestures": []})

    def test_reject_y_error(self):
        self.eng.reject_apply("act-01", "combat")
        self.assertEqual(self.world.actor_apply(_order()), ("rejected", "combat", {}))
        self.assertEqual(self.eng.spawn_count, 0)
        self.eng.apply_reject.clear()
        self.eng.error_apply("act-01", "prenda")
        self.assertEqual(self.world.actor_apply(_order()), ("error", "prenda", {}))
        self.assertEqual(self.eng.spawn_count, 1)

    def test_fallos_armados_antes_de_crear(self):
        self.eng.wardrobe_drop("act-01", "GorkaPants_Flat")
        self.eng.displace_spawn("act-01", 1, 0)
        _s, _r, read = self.world.actor_apply(_order())
        row = read["actors"][0]
        self.assertNotIn("GorkaPants_Flat", row[6])
        self.assertEqual(row[2], 6177000)

    def test_bad_args(self):
        args = _args()
        args["g_at"] = []
        self.assertEqual(self.world.actor_apply(_order(args=args)), ("rejected", "bad_args", {}))
        args = _args()
        del args["a_items"]
        self.assertEqual(self.world.actor_apply(_order(args=args)), ("rejected", "bad_args", {}))

    def test_gesto_por_marca_al_llegar(self):
        args = _args(mk_x_mm=[6177000], mk_z_mm=[7632000], g_at=[0])
        self.world.actor_apply(_order(args=args))
        self.eng.step(100)
        self.assertEqual(self.eng.read()["gestures"], [])
        for _ in range(20):
            self.eng.step(100)
        states = [ev[2] for ev in self.eng.read()["gestures"]]
        self.assertIn("requested", states)

    def test_gesto_por_tiempo(self):
        args = _args(g_emote=["EmotePoint"], g_at=[-1], g_t_ms=[500])
        self.world.actor_apply(_order(args=args))
        self.eng.step(400)
        self.assertEqual(self.eng.read()["gestures"], [])
        self.eng.step(100)
        self.assertEqual(self.eng.read()["gestures"][0][2], "requested")

    def test_restart_vacia_los_actores(self):
        self.world.actor_apply(_order())
        old = self.world.actors
        self.world.restart()
        self.assertIsNot(self.world.actors, old)
        self.assertEqual(self.world.actor_observe(_order("actor.observe"))[2]["actors"], [])

    def test_despawn_quita_gestos(self):
        args = _args(g_at=[-1], g_t_ms=[0])
        self.world.actor_apply(_order(args=args))
        self.eng.step(100)
        self.assertTrue(self.eng.read()["gestures"])
        self.eng.despawn("act-01")
        self.eng.despawn("act-99")
        self.assertEqual(self.eng.read(), {"actors": [], "gestures": []})


if __name__ == "__main__":
    unittest.main()
