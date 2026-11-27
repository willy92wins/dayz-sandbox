"""«Desconectar» de la pestaña IA (plan de coedición §2.3): D1-D5."""
import unittest

from .test_server import AK, HK, Base, Sse, move


class AiDisconnect(Base):
    def disconnect(self, key=HK):
        return self.env.req("POST", "/api/ai/disconnect", {}, key=key)

    def test_d1_la_clave_de_la_ia_deja_de_valer_y_la_persona_sigue(self):
        self.assertEqual(self.env.req("GET", "/api/scene", key=AK)[0], 200)
        st, body = self.disconnect()
        self.assertEqual((st, body), (200, {"ok": True, "revoked": True}))
        st, body = self.env.req("GET", "/api/scene", key=AK)
        self.assertEqual((st, body.get("code")), (401, "unauthorized"))
        st, body = self.env.ops([move("obj-01", 100, 100)], key=AK)
        self.assertEqual((st, body.get("code")), (401, "unauthorized"))
        self.assertEqual(self.env.store.snapshot()["rev"], self.first["rev"])
        self.assertEqual(self.env.req("GET", "/api/scene")[0], 200)
        st, _ = self.env.ops([move("obj-01", 100, 100)])
        self.assertEqual(st, 200)

    def test_d2_solo_la_persona_desconecta(self):
        st, body = self.disconnect(key=AK)
        self.assertEqual((st, body.get("code")), (403, "forbidden"))
        self.assertEqual(self.env.req("GET", "/api/scene", key=AK)[0], 200)
        self.assertEqual(self.disconnect(key=None)[0], 401)

    def test_d3_la_vista_y_el_evento(self):
        human = Sse(self.env)
        try:
            human.take(1, "snapshot")
            self.assertIs(self.env.req("GET", "/api/coedit")[1]["ai_revoked"], False)
            self.disconnect()
            ev = human.take(1, "ai.state")[0]
            self.assertEqual(ev["data"], {"paused": False, "revoked": True})
            self.assertIs(self.env.req("GET", "/api/coedit")[1]["ai_revoked"], True)
        finally:
            human.close()

    def test_d4_cierra_el_flujo_de_la_ia_y_no_el_de_la_persona(self):
        ai, human = Sse(self.env, key=AK), Sse(self.env)
        try:
            ai.take(1, "snapshot")
            human.take(1, "snapshot")
            self.disconnect()
            with self.assertRaises(EOFError):
                ai.take(1, "no-llega")
            human.take(1, "ai.state")
            self.env.ops([move("obj-01", 100, 100)])
            self.assertEqual(human.take(1, "scene.commit")[0]["event"], "scene.commit")
        finally:
            ai.close()
            human.close()

    def test_d5_dos_veces_y_la_pausa_no_la_devuelve(self):
        self.assertEqual(self.disconnect()[0], 200)
        self.assertEqual(self.disconnect()[0], 200)
        self.env.req("POST", "/api/ai/pause", {"paused": True})
        self.env.req("POST", "/api/ai/pause", {"paused": False})
        self.assertEqual(self.env.req("GET", "/api/scene", key=AK)[0], 401)


if __name__ == "__main__":
    unittest.main()
