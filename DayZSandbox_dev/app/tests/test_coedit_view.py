"""Pruebas de la vista de coedición (brief F6-web parte 2 §8.1, T11-T14)."""
import unittest

from .test_server import AK, HK, Base, move
from .test_server_web import FakeClock, cookie_header, login, raw

KEYS = {"ok", "paused", "ai_last_call_age_ms", "can_undo", "can_redo"}


class CoeditBase(Base):
    def view(self):
        st, body = self.env.req("GET", "/api/coedit")
        self.assertEqual(st, 200, body)
        return body

    def doc_id(self):
        return self.env.store.snapshot()["doc_id"]

    def post(self, path, body, key=HK):
        return self.env.req("POST", path, body, key=key)


class T11Permisos(CoeditBase):
    def test_persona_con_cookie_y_bearer(self):
        _, _, _, sid, _ = login(self.env)
        st_c, _, _, body_c = raw(self.env, "GET", "/api/coedit",
                                 headers={"Cookie": cookie_header(self.env, sid)})
        self.assertEqual(st_c, 200)
        body_b = self.view()
        for body in (body_c, body_b):
            self.assertEqual(set(body), KEYS)
            self.assertIs(body["ok"], True)
            self.assertIsInstance(body["paused"], bool)
            self.assertIsInstance(body["can_undo"], bool)
            self.assertIsInstance(body["can_redo"], bool)
            self.assertTrue(body["ai_last_call_age_ms"] is None
                            or isinstance(body["ai_last_call_age_ms"], int))

    def test_rechazos(self):
        st, body = self.env.req("GET", "/api/coedit", key=AK)
        self.assertEqual((st, body.get("code")), (403, "forbidden"))
        st, body = self.env.req("GET", "/api/coedit", key=None)
        self.assertEqual(st, 401)
        st, body = self.env.req("GET", "/api/coedit?x=1")
        self.assertEqual((st, body.get("code")), (404, "not_found"))
        st, _ = self.env.req("GET", "/api/coedit", host="evil.example:80")
        self.assertEqual(st, 403)


class T12Pausa(CoeditBase):
    def test_pausa_y_reanudar(self):
        self.assertIs(self.view()["paused"], False)
        self.assertEqual(self.post("/api/ai/pause", {"paused": True})[0], 200)
        self.assertIs(self.view()["paused"], True)
        self.assertEqual(self.post("/api/ai/pause", {"paused": False})[0], 200)
        self.assertIs(self.view()["paused"], False)


class T13UltimaLlamada(CoeditBase):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock(1000.0)
        self.env.backend.clock = self.clock

    def test_sin_llamadas_y_con_llamadas(self):
        self.assertIsNone(self.view()["ai_last_call_age_ms"])
        self.env.req("GET", "/api/scene", key=AK)
        self.clock.t += 4.0
        self.assertEqual(self.view()["ai_last_call_age_ms"], 4000)
        self.env.req("GET", "/api/catalog", key=AK)
        self.assertEqual(self.view()["ai_last_call_age_ms"], 0)

    def test_la_persona_y_una_clave_mala_no_cuentan(self):
        self.env.req("GET", "/api/scene")
        self.env.ops([move("obj-01", 7000, 7000)])
        _, _, _, sid, _ = login(self.env)
        raw(self.env, "GET", "/api/scene", headers={"Cookie": cookie_header(self.env, sid)})
        self.assertIsNone(self.view()["ai_last_call_age_ms"])
        st, _ = self.env.req("GET", "/api/scene", key=AK + "x")
        self.assertEqual(st, 401)
        self.assertIsNone(self.view()["ai_last_call_age_ms"])
        self.env.req("GET", "/api/scene", key=AK)
        self.clock.t += 2.0
        self.env.ops([move("obj-01", 7100, 7100)])
        self.assertEqual(self.view()["ai_last_call_age_ms"], 2000)


class T14Pilas(CoeditBase):
    def flags(self):
        v = self.view()
        return v["can_undo"], v["can_redo"]

    def test_transiciones(self):
        self.assertEqual(self.flags(), (False, False))
        self.assertEqual(self.env.ops([move("obj-01", 7000, 7000)])[0], 200)
        self.assertEqual(self.flags(), (True, False))
        st, _ = self.post("/api/scene/undo", {"doc_id": self.doc_id(), "request_id": "u-1"})
        self.assertEqual(st, 200)
        self.assertEqual(self.flags(), (False, True))
        st, _ = self.post("/api/scene/redo", {"doc_id": self.doc_id(), "request_id": "r-1"})
        self.assertEqual(st, 200)
        self.assertEqual(self.flags(), (True, False))

    def test_pilas_por_autor(self):
        self.assertEqual(self.env.ops([move("obj-01", 7000, 7000)], key=AK)[0], 200)
        self.assertEqual(self.flags(), (False, False))

    def test_tanda_revertida_coincide_con_el_backend(self):
        st, body = self.env.ops([move("obj-01", 7000, 7000)])
        self.assertEqual(st, 200)
        st, _ = self.post("/api/scene/batches/%s/revert" % body["batch"],
                          {"doc_id": self.doc_id(), "request_id": "rv-1"})
        self.assertEqual(st, 200)
        self.assertIs(self.view()["can_undo"], False)
        st, body = self.post("/api/scene/undo", {"doc_id": self.doc_id(), "request_id": "u-2"})
        self.assertEqual(body.get("code"), "nothing_to_undo")

    def test_leer_no_poda_las_pilas(self):
        st, body = self.env.ops([move("obj-01", 7000, 7000)])
        self.post("/api/scene/batches/%s/revert" % body["batch"],
                  {"doc_id": self.doc_id(), "request_id": "rv-2"})
        store = self.env.store
        before = {k: list(v) for k, v in store._undo.items()}
        self.assertEqual(store.stacks({"role": "human", "id": "web"}),
                         store.stacks({"role": "human", "id": "web"}))
        self.assertEqual({k: list(v) for k, v in store._undo.items()}, before)


if __name__ == "__main__":
    unittest.main()
