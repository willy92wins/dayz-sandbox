"""F1-co por HTTP: CO-2 a CO-9, WAIT y lease.state (brief F1-co §4)."""
import collections
import threading
import time
import unittest

from . import test_server as ts
from .test_server import AK, HK, Sse, fog, move


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class Base(ts.Base):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.env.backend.leases.clock = self.clock

    def lease(self, target="obj-01", field=None, key=HK):
        return self.env.req("POST", "/api/lease", {"target": target, "field": field}, key=key)

    def x(self, eid="obj-01"):
        return self.entity(self.env.store.snapshot()["doc"], eid)["x"]




class CO2Conflicto(Base):
    def test_campo_libre_aceptado_y_campo_humano_rechazado(self):
        base = self.env.store.snapshot()["rev"]
        st, r = self.env.ops([fog(0.3)], key=AK, base_rev=base)
        self.assertEqual(st, 200, r)
        self.env.ops([move("obj-01", 6190.0, 7627.0)])
        before = self.env.store.snapshot()
        st, r = self.env.ops([move("obj-01", 6100.0, 7600.0)], key=AK, base_rev=base)
        self.assertEqual((st, r["code"], r["current"]["obj-01"]["x"]), (409, "conflict", 6190.0))
        st, r = self.env.ops([{"name": "entity.delete", "target": "obj-01"}], key=AK, base_rev=base)
        self.assertEqual(r["code"], "conflict")
        self.assertEqual(self.env.store.snapshot(), before)


class CO3Prestamo(Base):
    def test_lease_bloquea_solo_su_entidad(self):
        st, l = self.lease("obj-01")
        self.assertEqual((st, l["ok"]), (200, True))
        st, r = self.env.ops([move("obj-01", 6100.0, 7600.0)], key=AK)
        self.assertEqual((st, r["code"], r["pointer"]), (409, "busy_human", "/ops/0"))
        self.assertEqual(r["current"]["obj-01"]["x"], 6188.0)
        self.assertEqual(self.env.ops([move("obj-02", 6170.0, 7640.0)], key=AK)[0], 200)
        self.assertEqual(self.env.ops([move("obj-01", 6189.0, 7626.0)])[0], 200)  # la persona sí
        self.env.req("POST", "/api/lease/%s/release" % l["lease_id"])
        self.assertEqual(self.env.ops([move("obj-01", 6100.0, 7600.0)], key=AK)[0], 200)

    def test_lease_por_campo(self):
        self.lease("obj-01", "yaw")
        st, r = self.env.ops([{"name": "entity.set", "target": "obj-01", "args": {"yaw": 90}}], key=AK)
        self.assertEqual(r["code"], "busy_human")
        self.assertEqual(self.env.ops([move("obj-01", 6100.0, 7600.0)], key=AK)[0], 200)

    def test_caduca_sin_latidos_y_gana_la_persona(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        base = self.env.store.snapshot()["rev"]
        _, l = self.lease("obj-01")
        self.clock.t += 2.0
        self.assertEqual(self.env.req("POST", "/api/lease/%s/renew" % l["lease_id"])[0], 200)
        self.clock.t += 3.1  # sin renovar más de 3 s
        st, r = self.env.ops([move("obj-01", 6100.0, 7600.0)], key=AK)
        self.assertEqual(st, 200, r)
        st, r = self.env.req("POST", "/api/lease/%s/renew" % l["lease_id"])
        self.assertEqual((st, r["code"]), (409, "lease_expired"))
        st, r = self.env.ops([move("obj-01", 6195.0, 7630.0)], base_rev=base)  # base vieja: gana ella
        self.assertEqual(st, 200, r)
        self.assertEqual(self.x(), 6195.0)
        states = [e["data"]["state"] for e in sse.take(4) if e["event"] == "lease.state"]
        sse.close()
        self.assertEqual(states, ["viva", "caducada"])
        self.env.ops([fog(0.2)], key=AK)
        self.assertEqual(sum(1 for ev in self.env.backend.ring if ev[1] == "lease.state"), 2)  # caducada una vez

    def test_la_ia_no_toma_ni_suelta(self):
        st, r = self.lease("obj-01", key=AK)
        self.assertEqual((st, r["code"]), (403, "forbidden"))
        _, l = self.lease("obj-01")
        st, _ = self.env.req("POST", "/api/lease/%s/release" % l["lease_id"], key=AK)
        self.assertEqual(st, 403)
        self.assertEqual(self.env.ops([move("obj-01", 6100.0, 7600.0)], key=AK)[1]["code"], "busy_human")

    def test_lease_de_entidad_que_no_existe(self):
        st, r = self.lease("obj-99")
        self.assertEqual((st, r["code"]), (409, "entity_gone"))


class CO4Deshacer(Base):
    def test_deshacer_escritura_atrasada_devuelve_lo_de_la_ia(self):
        base = self.env.store.snapshot()["rev"]
        self.env.ops([move("obj-01", 6100.0, 7600.0)], key=AK)
        st, r = self.env.ops([move("obj-01", 6195.0, 7630.0)], base_rev=base)
        self.assertEqual(st, 200)
        snap = self.env.store.snapshot()
        st, r = self.env.req("POST", "/api/scene/undo", {"doc_id": snap["doc_id"], "request_id": "u-1"})
        self.assertEqual((st, r["ok"]), (200, True))
        self.assertEqual(self.x(), 6100.0)  # el valor real de antes, el de la IA; no el de la base

    def test_revertir_tanda_de_la_ia_y_parcial(self):
        snap = self.env.store.snapshot()
        _, r = self.env.ops([move("obj-01", 6100.0, 7600.0), fog(0.4)], key=AK)
        self.env.ops([fog(0.5)])  # la persona retoca después la niebla
        st, back = self.env.req("POST", "/api/scene/batches/%s/revert" % r["batch"],
                                {"doc_id": snap["doc_id"], "request_id": "rv-1"})
        self.assertEqual(st, 200)
        self.assertEqual(self.x(), 6188.0)
        self.assertEqual(self.env.store.snapshot()["doc"]["ambiente"]["niebla"], 0.5)
        self.assertEqual([(p["target"], p["field"], p["why"]) for p in back["partial"]],
                         [("ambiente", "niebla", "changed_later")])


class CO5Aplicar(Base):
    def apply_request(self, key=AK, rev=None, hash_=None):
        snap = self.env.store.snapshot()
        return self.env.req("POST", "/api/apply/request", {"doc_id": snap["doc_id"], "rev": rev or snap["rev"],
                                                           "hash": hash_ or snap["hash"]}, key=key)

    def test_tarjeta_y_luego_aplica_la_persona(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        snap = self.env.store.snapshot()
        st, r = self.apply_request()
        self.assertEqual((st, r["ok"]), (200, True))
        self.assertEqual(self.env.backend.ops, {})
        st, r = self.env.req("POST", "/api/apply", {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.assertEqual(st, 200)
        evs = sse.take(2)
        sse.close()
        self.assertEqual([e["event"] for e in evs], ["apply.request", "op.state"])
        self.assertEqual(evs[1]["data"]["rev"], snap["rev"])

    def test_revision_vieja_y_tanda_entre_medias(self):
        snap = self.env.store.snapshot()
        self.env.ops([fog(0.3)], key=AK)
        seq = self.env.backend.seq
        st, r = self.apply_request(rev=snap["rev"], hash_=snap["hash"])
        self.assertEqual((st, r["code"]), (409, "stale_apply"))
        self.assertEqual(self.env.backend.seq, seq)  # ningún evento
        st, r = self.env.req("POST", "/api/apply", {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.assertEqual((st, r["code"]), (409, "stale_apply"))
        self.assertEqual(self.env.backend.ops, {})


class CO6Reconexion(Base):
    def test_lease_y_op_state_se_repiten(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        self.env.ops([fog(0.1)], key=AK)
        seen = sse.take(1)[0]
        sse.close()
        _, l = self.lease("obj-02")
        snap = self.env.store.snapshot()
        self.env.req("POST", "/api/apply", {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.env.ops([move("obj-01", 6190.0, 7627.0)])
        back = Sse(self.env, last_id=seen["id"])
        got = back.take(3)
        back.close()
        self.assertEqual([e["event"] for e in got], ["lease.state", "op.state", "scene.commit"])
        self.assertEqual([e["id"] for e in got], [seen["id"] + i for i in (1, 2, 3)])


class CO7Pausa(Base):
    def test_pausa_y_vuelta(self):
        self.env.req("POST", "/api/ai/pause", {"paused": True})
        self.assertEqual(self.env.ops([fog(0.3)], key=AK)[1]["code"], "ai_paused")
        self.env.req("POST", "/api/ai/pause", {"paused": False})
        self.assertEqual(self.env.ops([fog(0.3)], key=AK)[0], 200)

    def test_pausa_mientras_una_tanda_espera_en_busy(self):
        inside, release = threading.Event(), threading.Event()
        real = self.env.store.busy

        def slow(author, fp):
            if author["role"] == "ai":
                inside.set()
                release.wait(5)
            return real(author, fp)

        self.env.store.busy = slow
        sse = Sse(self.env, last_id=self.env.backend.seq)
        out = {}
        t1 = threading.Thread(target=lambda: out.setdefault("ai", self.env.ops([fog(0.4)], key=AK)))
        t1.start()
        self.assertTrue(inside.wait(5))
        t2 = threading.Thread(target=lambda: out.setdefault("p", self.env.req("POST", "/api/ai/pause", {"paused": True})))
        t2.start()
        time.sleep(0.3)
        self.assertNotIn("p", out)  # la pausa espera al candado
        release.set()
        t1.join(5), t2.join(5)
        self.env.store.busy = real
        evs = sse.take(2)
        self.assertEqual([e["event"] for e in evs], ["scene.commit", "ai.state"])
        self.assertEqual(self.env.ops([fog(0.5)], key=AK)[1]["code"], "ai_paused")
        sse.close()


class CO8Toma(Base):
    def test_toma_y_vuelta(self):
        snap = self.env.store.snapshot()
        for state in ("armada", "rodando"):
            self.env.backend.take_state = state
            for key in (HK, AK):
                self.assertEqual(self.env.ops([fog(0.3)], key=key)[1]["code"], "take_locked")
            st, r = self.env.req("POST", "/api/scene/validate",
                                 {"doc_id": snap["doc_id"], "base_rev": snap["rev"], "ops": [fog(0.3)]}, key=AK)
            self.assertEqual(r["code"], "take_locked")
        self.env.backend.take_state = "libre"
        self.assertEqual(self.env.ops([fog(0.3)], key=AK)[0], 200)


class CO9Identidad(Base):
    def test_dedup_autor_y_documento(self):
        snap = self.env.store.snapshot()
        body = {"doc_id": snap["doc_id"], "request_id": "same", "base_rev": snap["rev"], "label": None, "ops": [fog(0.3)]}
        a = self.env.req("POST", "/api/scene/ops", body, key=AK)
        b = self.env.req("POST", "/api/scene/ops", body, key=AK)
        self.assertEqual(a, b)
        self.assertEqual(self.env.store.snapshot()["rev"], snap["rev"] + 1)
        st, r = self.env.req("POST", "/api/scene/ops", dict(body, ops=[fog(0.9)]), key=AK)
        self.assertEqual(r["code"], "request_conflict")
        st, r = self.env.ops([fog(0.6)], key=AK, extra={"author": {"role": "human", "id": "web"}})
        self.assertEqual((st, r["code"]), (403, "author_mismatch"))
        st, r = self.env.ops([fog(0.6)], key=AK, extra={"doc_id": "d-00000000"})
        self.assertEqual(r["code"], "doc_changed")
        self.assertEqual(self.env.store.snapshot()["rev"], snap["rev"] + 1)


class Validar(Base):
    def test_valida_sin_cambios(self):
        snap = self.env.store.snapshot()
        seq = self.env.backend.seq
        st, r = self.env.req("POST", "/api/scene/validate",
                             {"doc_id": snap["doc_id"], "base_rev": snap["rev"], "ops": [fog(0.3)]}, key=AK)
        self.assertEqual((st, r["ok"], r["rev_if_applied"]), (200, True, snap["rev"] + 1))
        self.assertEqual((self.env.store.snapshot(), self.env.backend.seq), (snap, seq))
        st, r = self.env.req("POST", "/api/scene/validate",
                             {"doc_id": snap["doc_id"], "base_rev": snap["rev"], "ops": [move("obj-01", -5.0, 7600.0)]}, key=AK)
        self.assertEqual((st, r["code"], r["pointer"]), (422, "invalid", "/entities/2/x"))
        self.assertEqual(self.env.store.snapshot(), snap)


class Esperar(Base):
    def test_espera_y_vuelve_con_la_tanda(self):
        rev = self.env.store.snapshot()["rev"]
        threading.Timer(0.3, lambda: self.env.ops([move("obj-01", 6190.0, 7627.0)], label="tarde")).start()
        t0 = time.monotonic()
        st, r = self.env.req("GET", "/api/scene/changes?since_rev=%d&timeout_s=5" % rev, key=AK)
        took = time.monotonic() - t0
        self.assertEqual((st, [b["label"] for b in r["batches"]]), (200, ["tarde"]))
        self.assertLess(took, 1.0)

    def test_sin_cambios_y_fuera_del_horizonte(self):
        rev = self.env.store.snapshot()["rev"]
        t0 = time.monotonic()
        st, r = self.env.req("GET", "/api/scene/changes?since_rev=%d&timeout_s=1" % rev, key=AK)
        self.assertEqual((st, r["batches"]), (200, []))
        self.assertGreaterEqual(time.monotonic() - t0, 0.9)
        self.env.store._hist = collections.deque(maxlen=2)  # horizonte de 2 revisiones
        for v in (0.2, 0.25, 0.3):
            self.env.ops([fog(v)])
        st, r = self.env.req("GET", "/api/scene/changes?since_rev=%d&timeout_s=0" % rev, key=AK)
        self.assertEqual((st, r["code"]), (409, "stale_base"))


if __name__ == "__main__":
    unittest.main()
