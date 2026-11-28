"""F5 parte 1: la toma sin juego (brief `plans/2026-11-28-m1-f5-tomas-1-brief.md` §6).

Oráculo de Claude, congelado para la lane de implementación. Backend y bridge reales,
mod falso con la toma de `fake_take.py` y la cámara de `fake_camera.py`.
"""
import copy
import hashlib
import json
import time
import unittest

from app.tests.test_f2_live import AK, DOC_ID, HK, LiveBase, wait_until

T_CAM = {"id": "cam-t", "name": "Travelín", "keys": [
    {"t": 0, "x": 6100.0, "y": 2.0, "z": 7600.0, "yaw": 10, "pitch": 0, "fov": 40, "focus": 5},
    {"t": 0.6, "x": 6110.0, "y": 2.5, "z": 7605.0, "yaw": 20, "pitch": -5, "fov": 35, "focus": 6}]}
LONG_CAM = {"id": "cam-l", "name": "Largo", "keys": [
    {"t": 0, "x": 6100.0, "y": 2.0, "z": 7600.0, "yaw": 10, "pitch": 0, "fov": 40, "focus": 5},
    {"t": 30, "x": 6110.0, "y": 2.5, "z": 7605.0, "yaw": 20, "pitch": -5, "fov": 35, "focus": 6}]}
FIX_CAM = {"id": "cam-f", "name": "Fija", "keys": [
    {"t": 0, "x": 6100.0, "y": 2.0, "z": 7600.0, "yaw": 10, "pitch": 0, "fov": 40, "focus": 5}]}
T_CAM_ARGS = {
    "cam_id": "cam-t",
    "c_t_ms": [0, 600],
    "c_x_mm": [6100000, 6110000],
    "c_y_mm": [2000, 2500],
    "c_z_mm": [7600000, 7605000],
    "c_yaw_mdeg": [10000, 20000],
    "c_pitch_mdeg": [0, -5000],
    "c_fov_mdeg": [40000, 35000],
    "c_focus_mm": [5000, 6000],
}
T_HASH = hashlib.sha256(json.dumps(T_CAM_ARGS, sort_keys=True, separators=(",", ":"))
                        .encode("utf-8")).hexdigest()[:16]
LIVE = ("preparando", "armada", "rodando")


def _read(take_id="tk-a-1", state="armada", origin="", t_ms=0, dur_ms=600, bad=None):
    return {"take": {"take_id": take_id, "state": state, "origin": origin, "t_ms": t_ms,
                     "dur_ms": dur_ms, "bad": [] if bad is None else bad}}


class TakeBase(LiveBase):
    cams = (FIX_CAM, T_CAM, LONG_CAM)
    apply_scene = True

    def setUp(self):
        self.env = self.make_env(bridge_kwargs={"enable_sweeper": True, "sweep_ms": 50})
        self.fake = self.start(self.env)
        self.assertTrue(wait_until(self.env.bridge.client_in_world, 10), "cliente fuera del mundo")
        doc = copy.deepcopy(self.env.snap()["doc"])
        doc["cameras"] = copy.deepcopy(list(self.cams))
        self.env.set_doc(doc)
        if self.apply_scene:
            self.apply_and_observe()

    # --- ayudas -----------------------------------------------------------
    def apply_and_observe(self):
        r = self.env.apply()
        self.assertTrue(r.get("ok"), r)
        self.env.wait_state(r["op_id"], "observado")

    def post(self, path, body=None, key=HK):
        return self.env.http("POST", path, {} if body is None else body, key=key)

    def prepare(self, cam_id="cam-t", key=HK, doc_id=None):
        return self.post("/api/take/prepare",
                         {"doc_id": doc_id or self.env.snap()["doc_id"], "cam_id": cam_id}, key=key)

    def take(self, key=HK):
        status, body = self.env.http("GET", "/api/take", key=key)
        self.assertEqual(status, 200, body)
        return body["take"]

    def wait_take(self, pred, desc, timeout=8.0):
        ok = wait_until(lambda: (lambda t: t is not None and pred(t))(self.take()), timeout)
        self.assertTrue(ok, "la toma no llego a %s: %s" % (desc, self.take()))
        return self.take()

    def wait_state(self, state, timeout=8.0):
        return self.wait_take(lambda t: t["state"] == state, state, timeout)

    def take_orders(self, verb=None):
        out = [o for o in self.env.bridge.orders.values() if o["verb"].startswith("take.")]
        if verb is not None:
            out = [o for o in out if o["verb"] == verb]
        return sorted(out, key=lambda o: o["_seq"])

    def armed(self, cam_id="cam-t"):
        status, body = self.prepare(cam_id)
        self.assertEqual(status, 200, body)
        t = self.wait_state("armada")
        self.assertEqual(t["take_id"], body["take_id"])
        return t["take_id"]

    def rolling(self, cam_id="cam-l"):
        tid = self.armed(cam_id)
        status, body = self.post("/api/take/go", {"take_id": tid})
        self.assertEqual(status, 200, body)
        self.wait_state("rodando")
        return tid

    def gate(self):
        with self.env.store.lock:
            return self.env.backend._gate({"role": "human"})


class T1Preparar(TakeBase):
    def test_t1_ordenes_exactas_cam_lista_y_armada(self):
        status, body = self.prepare()
        self.assertEqual(status, 200, body)
        tid = body["take_id"]
        self.assertEqual(tid, "tk-%s-1" % self.env.bridge.session)
        t = self.wait_state("armada")
        snap = self.env.snap()
        self.assertEqual({k: t[k] for k in ("take_id", "doc_id", "rev", "cam_id", "origin", "reason",
                                            "bad", "t_ms", "dur_ms")},
                         {"take_id": tid, "doc_id": snap["doc_id"], "rev": snap["rev"],
                          "cam_id": "cam-t", "origin": None, "reason": None, "bad": [],
                          "t_ms": 0, "dur_ms": 600})
        load = self.take_orders("take.cam_load")
        prep = self.take_orders("take.prepare")
        arm = self.take_orders("take.arm")
        self.assertEqual((len(load), len(prep), len(arm)), (1, 1, 1))
        self.assertEqual(load[0]["role"], "client")
        self.assertEqual(load[0]["args"], dict(T_CAM_ARGS, f2=1, take_id=tid, cam_hash=T_HASH))
        self.assertEqual((prep[0]["role"], prep[0]["internal"]), ("server", True))
        self.assertEqual(prep[0]["args"], {"f2": 1, "take_id": tid, "cam_id": "cam-t",
                                           "rev": snap["rev"], "hash": snap["hash"], "dur_ms": 600})
        self.assertEqual((arm[0]["role"], arm[0]["internal"]), ("server", True))
        self.assertEqual(arm[0]["args"], {"f2": 1, "take_id": tid, "cam_hash": T_HASH})
        self.assertEqual(self.fake.take.state()["state"], "armada")
        self.assertEqual(self.gate(), "take_locked")
        self.assertEqual(self.take(key=AK)["state"], "armada")


class T2Rodar(TakeBase):
    def test_t2_rueda_suena_la_camara_y_termina(self):
        tid = self.armed()
        status, body = self.post("/api/take/go", {"take_id": tid})
        self.assertEqual(status, 200, body)
        go = self.take_orders("take.go")
        self.assertEqual(len(go), 1)
        self.assertEqual(go[0]["args"], {"f2": 1, "take_id": tid})
        self.assertTrue(wait_until(lambda: self.fake.camera.state()["playing"] == 1, 5),
                        self.fake.camera.state())
        self.assertEqual(self.fake.camera.state()["cam_id"], "cam-t")
        self.assertEqual(self.gate(), "take_locked")
        t = self.wait_state("terminada")
        self.assertEqual((t["t_ms"], t["dur_ms"], t["origin"]), (600, 600, None))
        self.assertEqual(self.fake.camera.state()["active"], 0)
        self.assertIsNone(self.gate())
        self.assertGreaterEqual(len(self.take_orders("take.read")), 1)


class T3PararWeb(TakeBase):
    def test_t3_parada_web_idempotente_y_take_state(self):
        tid = self.rolling()
        r1 = self.post("/api/take/stop", {"take_id": tid})
        r2 = self.post("/api/take/stop", {"take_id": tid})
        self.assertEqual(r1[0], 200, r1)
        self.assertIn(r2[0], (200, 409), r2)
        t = self.wait_state("parada")
        self.assertEqual(t["origin"], "web")
        self.assertEqual(len(self.take_orders("take.stop")), 1)
        self.assertEqual(self.fake.camera.state()["active"], 0)
        self.assertEqual([e for e in self.fake.take.events if e[0] == "parada"], [("parada", tid)])
        for path in ("/api/take/go", "/api/take/stop"):
            status, res = self.post(path, {"take_id": tid})
            self.assertEqual((status, res.get("code")), (409, "take_state"), path)
        self.assertIsNone(self.gate())


class T4StopPrimero(TakeBase):
    def test_t4_el_stop_sale_antes_que_la_lectura_pendiente(self):
        tid = self.rolling()
        self.fake.cut_polls("server", 450)
        time.sleep(0.35)
        self.assertTrue([o for o in self.take_orders("take.read") if o["bstate"] == "pendiente"],
                        "sin take.read pendiente")
        n0 = len(self.fake.server.received_orders)
        status, body = self.post("/api/take/stop", {"take_id": tid})
        self.assertEqual(status, 200, body)
        self.wait_state("parada")
        after = [o["verb"] for o in self.fake.server.received_orders[n0:] if o["verb"].startswith("take.")]
        self.assertTrue(after, "el servidor no recibio nada")
        self.assertEqual(after[0], "take.stop", after)


class T5Tecla(TakeBase):
    def test_t5_tecla_para_con_origen_juego(self):
        tid = self.rolling()
        self.assertFalse(self.fake.take.press_stop_key(menu_open=True))
        time.sleep(0.4)
        self.assertEqual(self.take()["state"], "rodando")
        self.assertTrue(self.fake.take.press_stop_key())
        t = self.wait_state("parada")
        self.assertEqual((t["take_id"], t["origin"]), (tid, "juego"))
        self.assertEqual(self.fake.camera.state()["active"], 0)
        self.assertEqual(self.take_orders("take.stop"), [])

    def test_t5b_tecla_y_web_a_la_vez_una_sola_parada(self):
        tid = self.rolling()
        self.assertTrue(self.fake.take.press_stop_key())
        status, body = self.post("/api/take/stop", {"take_id": tid})
        self.assertIn(status, (200, 409), body)
        t = self.wait_state("parada")
        self.assertEqual(t["origin"], "juego")
        time.sleep(0.4)
        self.assertEqual(self.take()["origin"], "juego")
        self.assertEqual([e for e in self.fake.take.events if e[0] == "parada"], [("parada", tid)])


class T6HombreMuerto(TakeBase):
    def test_t6_sin_backend_la_toma_se_para_por_hombre_muerto(self):
        tid = self.rolling()
        self.fake.take.deadman_ms = 400
        self.fake.cut_polls("server", 1200)
        self.assertTrue(wait_until(lambda: self.fake.take.state()["state"] == "parada", 5))
        self.assertEqual(self.fake.camera.state()["active"], 0)
        t = self.wait_state("parada", timeout=10)
        self.assertEqual((t["take_id"], t["origin"]), (tid, "hombre_muerto"))


class T7Lecturas(TakeBase):
    def test_t7_lecturas_que_no_cumplen_dan_fallida(self):
        self.fake.take.fail_checks = ["env", "marks"]
        status, body = self.prepare()
        self.assertEqual(status, 200, body)
        t = self.wait_state("fallida")
        self.assertEqual((t["reason"], t["bad"], t["origin"]), ("checks", ["marks", "env"], None))
        time.sleep(0.3)
        self.assertEqual(self.take_orders("take.arm"), [])
        self.assertIsNone(self.gate())


class T8Errores(TakeBase):
    apply_scene = False

    def expect(self, res, status, code, pointer=None):
        self.assertEqual((res[0], res[1].get("code")), (status, code), res)
        if pointer is not None:
            self.assertEqual(res[1].get("pointer"), pointer, res)

    def test_t8_errores_en_orden_y_sin_encolar(self):
        doc_id = self.env.snap()["doc_id"]
        self.expect(self.prepare(key=AK), 403, "forbidden")
        self.expect(self.post("/api/take/prepare", {"doc_id": doc_id}), 400, "bad_request")
        self.expect(self.post("/api/take/prepare", {"doc_id": doc_id, "cam_id": ""}), 400, "bad_request")
        self.expect(self.post("/api/take/prepare", {"doc_id": 3, "cam_id": "cam-t"}), 400, "bad_request")
        self.expect(self.prepare(doc_id="d-otro"), 409, "doc_changed", "/doc_id")
        self.expect(self.prepare(cam_id="cam-x"), 404, "not_found", "/cam_id")
        self.expect(self.prepare(), 409, "scene_not_observed")
        self.apply_and_observe()
        self.expect(self.prepare(cam_id="cam-f"), 422, "invalid", "/cameras/0/keys")
        doc = copy.deepcopy(self.env.snap()["doc"])
        doc["cameras"][1]["name"] = "Otro nombre"
        self.env.set_doc(doc)
        self.expect(self.prepare(), 409, "scene_not_observed")
        self.apply_and_observe()
        self.assertEqual(self.take_orders(), [])
        self.assertIsNone(self.take())
        tid = self.armed()
        self.expect(self.prepare(), 409, "take_busy")
        self.post("/api/take/stop", {"take_id": tid})
        self.wait_state("parada")
        self.fake.restart_peer("client", epoch="e" * 32)
        self.assertTrue(wait_until(lambda: (self.env.bridge.peer("client") or {}).get("epoch") == "e" * 32))
        n = len(self.take_orders())
        self.expect(self.prepare(), 409, "no_director")
        self.assertEqual(len(self.take_orders()), n)

    def test_t8b_go_y_stop_sin_toma(self):
        self.apply_and_observe()
        self.expect(self.post("/api/take/go", {"take_id": "tk-x"}), 404, "not_found", "/take_id")
        self.expect(self.post("/api/take/stop", {"take_id": "tk-x"}), 404, "not_found", "/take_id")
        self.expect(self.post("/api/take/go", {"take_id": 7}), 400, "bad_request")
        self.assertEqual(self.take_orders(), [])


class T9DocCambia(TakeBase):
    def test_t9_documento_cambia_antes_de_armar(self):
        self.fake.cut_polls("client", 60000)
        time.sleep(0.4)
        status, body = self.prepare()
        self.assertEqual(status, 200, body)
        self.assertTrue(wait_until(lambda: self.fake.take.state()["state"] == "preparada", 5))
        doc = copy.deepcopy(self.env.snap()["doc"])
        doc["cameras"][0]["name"] = "Renombrada"
        self.env.set_doc(doc)
        self.fake.client.clear_poll_cut()
        t = self.wait_state("fallida")
        self.assertEqual(t["reason"], "doc_changed")
        time.sleep(0.3)
        self.assertEqual(self.take_orders("take.arm"), [])


class T10StopPreparando(TakeBase):
    def test_t10_parar_mientras_se_prepara(self):
        self.fake.cut_polls("client", 60000)
        time.sleep(0.4)
        status, body = self.prepare()
        self.assertEqual(status, 200, body)
        tid = body["take_id"]
        self.assertEqual(self.take()["state"], "preparando")
        status, res = self.post("/api/take/stop", {"take_id": tid})
        self.assertEqual(status, 200, res)
        t = self.wait_state("parada")
        self.assertEqual(t["origin"], "web")
        self.fake.client.clear_poll_cut()
        time.sleep(0.6)
        self.assertEqual(self.take_orders("take.arm"), [])
        self.assertEqual(self.take()["state"], "parada")


class T11EpochNuevo(TakeBase):
    def test_t11_mundo_reiniciado_con_la_toma_armada(self):
        self.armed()
        self.fake.restart_peer("server", epoch="f" * 32)
        t = self.wait_state("fallida", timeout=10)
        self.assertEqual(t["reason"], "mundo_reiniciado")
        self.assertIsNone(self.gate())


class T12Credenciales(TakeBase):
    def test_t12_la_ia_lee_pero_no_rueda_ni_para(self):
        tid = self.armed()
        for path in ("/api/take/go", "/api/take/stop"):
            status, res = self.post(path, {"take_id": tid}, key=AK)
            self.assertEqual((status, res.get("code")), (403, "forbidden"), path)
        self.assertEqual(self.take_orders("take.go"), [])
        self.assertEqual(self.take_orders("take.stop"), [])
        self.assertEqual(self.take(key=AK)["take_id"], tid)


class T13GoTardio(TakeBase):
    def test_t13_go_retenido_tras_la_tecla_no_reactiva_la_camara(self):
        self.fake.take.hold_go = True
        tid = self.rolling()
        self.assertEqual(self.fake.camera.state()["active"], 0)
        self.assertTrue(self.fake.take.press_stop_key())
        self.fake.take.release_go()
        self.assertEqual(self.fake.camera.state()["active"], 0)
        t = self.wait_state("parada")
        self.assertEqual((t["take_id"], t["origin"]), (tid, "juego"))


class V1Lecturas(unittest.TestCase):
    def test_v1_valid_take_read_y_valid_ready_read(self):
        from app.backend.take_live import valid_ready_read, valid_take_read
        good = [
            {"take": {"take_id": "", "state": "ninguna", "origin": "", "t_ms": 0, "dur_ms": 0, "bad": []}},
            _read(state="preparada", bad=["marks", "env"]),
            _read(state="preparada"),
            _read(state="armada"),
            _read(state="rodando", t_ms=300),
            _read(state="terminada", t_ms=600),
            _read(state="parada", origin="web", t_ms=200),
            _read(state="parada", origin="juego", t_ms=0),
            _read(state="parada", origin="hombre_muerto", t_ms=600),
            _read(take_id="t" * 64),
        ]
        for r in good:
            self.assertTrue(valid_take_read(r), r)
        bad = [
            None, [], {}, {"take": None},
            dict(_read(), extra=1),
            {"take": dict(_read()["take"], extra=1)},
            {"take": {k: v for k, v in _read()["take"].items() if k != "bad"}},
            _read(take_id="t" * 65),
            _read(take_id=3),
            _read(state="lista"),
            _read(state="parada"),
            _read(state="rodando", origin="web"),
            _read(state="parada", origin="otro"),
            _read(t_ms=True),
            _read(state="rodando", t_ms=700),
            _read(state="rodando", t_ms=-1),
            _read(dur_ms=1.5),
            _read(state="armada", t_ms=10),
            _read(state="preparada", t_ms=10),
            _read(state="terminada", t_ms=500),
            _read(state="preparada", bad=["marks", "marks"]),
            _read(state="preparada", bad=["luz"]),
            _read(state="armada", bad=["marks"]),
            _read(state="preparada", bad="marks"),
            {"take": {"take_id": "tk", "state": "ninguna", "origin": "", "t_ms": 0, "dur_ms": 0, "bad": []}},
            {"take": {"take_id": "", "state": "ninguna", "origin": "", "t_ms": 0, "dur_ms": 5, "bad": []}},
            _read(take_id=""),
        ]
        for r in bad:
            self.assertFalse(valid_take_read(r), r)
        self.assertTrue(valid_ready_read({"ready": {"take_id": "tk-1", "cam_hash": "ab"}}))
        for r in (None, {}, {"ready": {"take_id": "tk-1"}}, {"ready": {"take_id": "", "cam_hash": "ab"}},
                  {"ready": {"take_id": "tk-1", "cam_hash": ""}},
                  {"ready": {"take_id": "tk-1", "cam_hash": "ab", "x": 1}},
                  {"ready": {"take_id": "tk-1", "cam_hash": 3}},
                  {"ready": {"take_id": "tk-1", "cam_hash": "ab"}, "x": 1}):
            self.assertFalse(valid_ready_read(r), r)


if __name__ == "__main__":
    unittest.main()
