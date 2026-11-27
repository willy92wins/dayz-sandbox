"""F3-offline-2 §4 y §5, T-S1..T-S14: la etapa de actores de punta a punta.

Bridge y Backend reales en 127.0.0.1:0 y el mod falso con mundo y motor de actores,
con el arnés de `test_f2_live.py`.
"""
import copy
import time

from app.backend.actor_wire import valid_actor_read
from app.tests.fake_world import FakeWorld
from app.tests.test_f2_live import Env, LiveBase, _load, wait_op, wait_until

HK = "clave-persona-f2-live-1234567890"


def _basic_doc(env):
    doc = _load("escena-basica-cine.json")
    doc["doc_id"] = env.snap()["doc_id"]
    return doc


def expire(env, orders):
    """Caduca por TTL las ordenes dadas sin que el servidor parezca caido."""
    with env.bridge.cond:
        for o in orders:
            o["ttl_ms"] = 1
    env.bridge.sweep(now=env.bridge._now() + 0.05)


class ActorBase(LiveBase):
    def setup_env(self, engine="expansion", doc=True, **kw):
        env = self.make_env(**kw)
        fake = self.start(env, world=FakeWorld(), actor_engine=engine)
        if doc:
            env.set_doc(_basic_doc(env))
        return env, fake

    def states(self, env, op_id):
        return [(e["state"], e.get("reason")) for e in env.events_for(op_id)]

    def actor_orders(self, env, verb="actor.apply"):
        return [o for o in env.orders(verb=verb, internal=True)]


class TS1Feliz(ActorBase):
    def test_s1_secuencia_y_actores(self):
        env, fake = self.setup_env()
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        op_id = r["op_id"]
        wait_op(env, op_id, "observado")
        seq = [s for s, _ in self.states(env, op_id)]
        self.assertEqual(seq, ["pendiente", "ejecutando", "aplicado", "observado"])
        stage = self.actor_orders(env)
        self.assertEqual(len(stage), 2)
        self.assertTrue(all(o["bstate"] == "terminal" for o in stage))
        rows = {row[0]: row for row in fake.world.actors.read()["actors"]}
        self.assertEqual(set(rows), {"act-01", "act-02"})
        cat = _load("catalog-m1.json")
        self.assertEqual(rows["act-01"][6], cat["wardrobe_items"]["partisano"])

    def test_s12_sin_actores_con_motor_igual_y_reset_un_actor_reset(self):
        env, fake = self.setup_env(doc=False)
        r = env.apply()
        wait_op(env, r["op_id"], "observado")
        self.assertEqual([s for s, _ in self.states(env, r["op_id"])],
                         ["pendiente", "ejecutando", "aplicado", "observado"])
        self.assertEqual(self.actor_orders(env), [])
        rr = env.reset()
        wait_op(env, rr["op_id"], "observado")
        self.assertEqual(len(self.actor_orders(env, "actor.reset")), 1)

    def test_s12b_sin_motor_reset_sin_actor_reset(self):
        env, fake = self.setup_env(engine="none", doc=False)
        r = env.apply()
        wait_op(env, r["op_id"], "observado")
        rr = env.reset()
        wait_op(env, rr["op_id"], "observado")
        self.assertEqual(self.actor_orders(env, "actor.reset"), [])


class TSFallos(ActorBase):
    def test_s2_rechazado(self):
        env, fake = self.setup_env()
        fake.world.actors.reject_apply("act-02", "combat")
        r = env.apply()
        wait_op(env, r["op_id"], "parcial", "actor_rechazado")
        self.assertNotIn("observado", [s for s, _ in self.states(env, r["op_id"])])

    def test_s3_vestuario(self):
        env, fake = self.setup_env()
        fake.world.actors.wardrobe_drop("act-01", "GorkaPants_Flat")
        r = env.apply()
        wait_op(env, r["op_id"], "parcial", "actor_no_cumple")

    def test_s3b_desplazado(self):
        env, fake = self.setup_env()
        fake.world.actors.displace_spawn("act-01", 1, 0)
        r = env.apply()
        wait_op(env, r["op_id"], "parcial", "actor_no_cumple")

    def test_s3b_desplazado_poco_vale(self):
        env, fake = self.setup_env()
        fake.world.actors.displace_spawn("act-01", 0.3, 0)
        r = env.apply()
        wait_op(env, r["op_id"], "observado")

    def test_s4_error_y_resultado_tardio(self):
        env, fake = self.setup_env()
        fake.world.actors.error_apply("act-01", "prenda")
        r = env.apply()
        wait_op(env, r["op_id"], "parcial", "actor_error")
        wait_until(lambda: all(o["bstate"] == "terminal" for o in self.actor_orders(env)), 5)
        self.assertEqual((env.op(r["op_id"])["state"], env.op(r["op_id"])["reason"]),
                         ("parcial", "actor_error"))

    def test_s14_foto_invalida_no_la_corta_el_bridge(self):
        env, fake = self.setup_env()
        fake.world.actors.cls_swap("act-01", None)
        r = env.apply()
        wait_op(env, r["op_id"], "parcial", "actor_no_cumple")


class TS5Capacidad(ActorBase):
    def test_s5_motor_perdido_entre_validar_y_encolar(self):
        env, fake = self.setup_env()
        snap = env.snap()
        with env.store.lock:
            frozen = env.store.freeze(snap["doc_id"], snap["rev"], snap["hash"])
            res = env.live.prepare_apply_locked(frozen["doc"], frozen["rev"], frozen["hash"])
            self.assertTrue(res["ok"], res)
            env.bridge.peers["server"]["actor_engine"] = "none"
            n_ops = len(env.backend.ops)
            ok, err = env.live.enqueue_apply_locked(None, res)
        self.assertFalse(ok)
        self.assertEqual(err["code"], "expansion_unavailable")
        self.assertEqual(len(env.backend.ops), n_ops)
        self.assertEqual(env.orders(verb="scene.apply"), [])
        self.assertEqual(fake.world.census(), [])

    def test_s5b_guarda_con_servidor_caido(self):
        env, fake = self.setup_env()
        snap = env.snap()
        with env.bridge.cond:
            order = {"op_id": "op-77", "epoch": env.bridge.peers["server"]["epoch"],
                     "actor_orders": [{"a_lid": "act-01"}]}
            env.backend.ops["op-77"] = {"op_id": "op-77", "state": "aplicado", "rev": 1,
                                         "hash": snap["hash"], "at_ms": 0, "origin": "backend",
                                         "reason": None}
            env.bridge.peers["server"]["lost"] = True
            env.live._close_apply_ok_locked(order, None)
            env.bridge.peers["server"]["lost"] = False
        self.assertEqual((env.op("op-77")["state"], env.op("op-77")["reason"]),
                         ("parcial", "conexion_perdida"))
        self.assertEqual(self.actor_orders(env), [])


class TS6Perdidas(ActorBase):
    def test_s6_conexion_perdida_y_resultado_tardio(self):
        env, fake = self.setup_env()
        fake.server.drop_results_for_verb.add("actor.apply")
        r = env.apply()
        op_id = r["op_id"]
        wait_until(lambda: any(o.get("delivered_inst") for o in self.actor_orders(env)), 10)
        with env.bridge.cond:
            env.bridge._check_server_loss_locked(env.bridge._now() + 60)
        wait_op(env, op_id, "parcial", "conexion_perdida")
        fake.server.drop_results_for_verb.clear()
        time.sleep(0.3)
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "conexion_perdida"))

    def test_s6b_ttl(self):
        env, fake = self.setup_env()
        fake.server.drop_results_for_verb.add("actor.apply")
        r = env.apply()
        op_id = r["op_id"]
        wait_until(lambda: any(o.get("delivered_inst") for o in self.actor_orders(env)), 10)
        expire(env, self.actor_orders(env))
        wait_op(env, op_id, "parcial", "sin_resultado")

    def test_s6c_reconciliacion_por_checkpoint_arranca_la_etapa(self):
        env, fake = self.setup_env()
        fake.server.drop_results_for_verb.add("scene.apply")
        r = env.apply()
        op_id = r["op_id"]
        wait_until(lambda: fake.world.census(), 10)
        expire(env, env.orders(verb="scene.apply", internal=False))
        wait_op(env, op_id, "observado", "reconciliada", timeout=20)
        self.assertIn(("aplicado", None), self.states(env, op_id))
        self.assertEqual(len(fake.world.actors.read()["actors"]), 2)

    def test_s7_state_read_no_reconcilia_la_etapa(self):
        env, fake = self.setup_env()
        fake.world.actors.reject_apply("act-02", "combat")
        r = env.apply()
        wait_op(env, r["op_id"], "parcial", "actor_rechazado")
        with env.bridge.cond:
            env.bridge._trigger_state_read_locked()
        time.sleep(0.5)
        self.assertEqual((env.op(r["op_id"])["state"], env.op(r["op_id"])["reason"]),
                         ("parcial", "actor_rechazado"))


class TSReset(ActorBase):
    def _applied(self):
        env, fake = self.setup_env()
        r = env.apply()
        wait_op(env, r["op_id"], "observado")
        return env, fake

    def test_s8_reset_retira_actores(self):
        env, fake = self._applied()
        rr = env.reset()
        wait_op(env, rr["op_id"], "observado")
        self.assertEqual(fake.world.actors.read()["actors"], [])
        self.assertEqual(fake.world.census(), [])

    def test_s9_actores_vivos(self):
        env, fake = self._applied()
        fake.world.actors.despawn_fails("act-01")
        rr = env.reset()
        wait_op(env, rr["op_id"], "parcial", "actores_vivos")

    def test_s10_el_motivo_de_la_escena_manda(self):
        env, fake = self._applied()
        fake.world.spawn_foreign("FirstAidKit", 6140.0, 7676.0, 200.0, inside="obj-17")
        fake.world.actors.despawn_fails("act-01")
        rr = env.reset()
        wait_op(env, rr["op_id"], "parcial", "contenido_ajeno")

    def test_s6c_reset_reconciliado_retira_actores(self):
        env, fake = self._applied()
        fake.server.drop_results_for_verb.add("scene.reset")
        rr = env.reset()
        wait_until(lambda: not fake.world.census(), 10)
        expire(env, env.orders(verb="scene.reset", internal=False))
        wait_op(env, rr["op_id"], "observado", "reconciliada", timeout=20)
        self.assertEqual(len(self.actor_orders(env, "actor.reset")), 1)
        self.assertEqual(fake.world.actors.read()["actors"], [])


class TS11Reentrega(ActorBase):
    def test_s11_misma_orden_no_duplica(self):
        world = FakeWorld()
        eng = world.actors
        args = _load_args()
        order = {"op_id": "rd-5", "session": "s" * 16, "verb": "actor.apply", "args": args}
        world.actor_apply(order)
        world.actor_apply(copy.deepcopy(order))
        self.assertEqual(eng.spawn_count, 1)
        world.actor_apply(dict(order, op_id="rd-6"))
        self.assertEqual(eng.spawn_count, 2)
        self.assertEqual(len(eng.read()["actors"]), 1)


def _load_args():
    from app.backend import scene_plan as sp
    doc = _load("escena-basica-cine.json")
    return sp.build_actor_orders(doc, 1, "a" * 64, _load("catalog-m1.json"))[0]


class TS13Observe(ActorBase):
    def test_s13_observe_con_motor(self):
        env, fake = self.setup_env()
        r = env.apply()
        wait_op(env, r["op_id"], "observado")
        st, body = env.http("POST", "/api/actors/observe", {"doc_id": env.snap()["doc_id"]}, key=HK)
        self.assertEqual(st, 200, body)
        self.assertTrue(body["read_id"].startswith("rd-"))
        ok = wait_until(lambda: env.http("GET", "/api/actors/observation", key=HK)[1].get("observation"), 10)
        self.assertTrue(ok)
        obs = env.http("GET", "/api/actors/observation", key=HK)[1]["observation"]
        self.assertTrue(valid_actor_read(obs))
        self.assertEqual(len(obs["actors"]), 2)

    def test_s13_lectura_invalida_no_pisa(self):
        env, fake = self.setup_env()
        r = env.apply()
        wait_op(env, r["op_id"], "observado")
        doc_id = env.snap()["doc_id"]
        env.http("POST", "/api/actors/observe", {"doc_id": doc_id}, key=HK)
        wait_until(lambda: env.http("GET", "/api/actors/observation", key=HK)[1].get("observation"), 10)
        first = env.http("GET", "/api/actors/observation", key=HK)[1]["observation"]
        fake.world.actors.cls_swap("act-01", 7)
        st, body = env.http("POST", "/api/actors/observe", {"doc_id": doc_id}, key=HK)
        self.assertEqual(st, 200)
        wait_until(lambda: env.orders(verb="actor.observe")
                   and all(o["bstate"] == "terminal" for o in env.orders(verb="actor.observe")), 10)
        self.assertEqual(env.http("GET", "/api/actors/observation", key=HK)[1]["observation"], first)

    def test_s13_sin_motor(self):
        env, fake = self.setup_env(engine="none", doc=False)
        st, body = env.http("POST", "/api/actors/observe", {"doc_id": env.snap()["doc_id"]}, key=HK)
        self.assertEqual(st, 409)
        self.assertEqual(body["code"], "expansion_unavailable")
        st, body = env.http("GET", "/api/actors/observation", key=HK)
        self.assertEqual(st, 200)
        self.assertIsNone(body["observation"])
