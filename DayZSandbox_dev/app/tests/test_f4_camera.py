"""F4 parte 1: la cámara del cliente (brief `plans/2026-11-28-m1-f4-camara-1-brief.md` §6).

Oráculo de Claude, congelado para la lane de implementación. Backend y bridge reales,
mod falso con la cámara de `fake_camera.py` en el peer `client`.
"""
import copy
import time
import unittest

from app.tests.test_f2_live import AK, DOC_ID, HK, LiveBase, wait_until

CAM02_ARGS = {
    "f2": 1, "cam_id": "cam-02",
    "c_t_ms": [0, 3000, 6000],
    "c_x_mm": [6154000, 6168000, 6182000],
    "c_y_mm": [2100, 2400, 1900],
    "c_z_mm": [7610000, 7614000, 7620000],
    "c_yaw_mdeg": [28000, 8000, 348000],
    "c_pitch_mdeg": [-2000, -3000, -1000],
    "c_fov_mdeg": [42000, 36000, 30000],
    "c_focus_mm": [24000, 16000, 12000],
}
ZERO_CAM = {"active": 0, "playing": 0, "cam_id": "", "t_ms": 0, "dur_ms": 0,
            "pose": [0, 0, 0, 0, 0, 0]}


def _key(t, x=6100.0, y=2.0, z=7600.0, yaw=10, pitch=0, fov=40, focus=5):
    return {"t": t, "x": x, "y": y, "z": z, "yaw": yaw, "pitch": pitch, "fov": fov, "focus": focus}


class CamBase(LiveBase):
    def setUp(self):
        self.env = self.make_env()
        self.fake = self.start(self.env)
        self.assertTrue(wait_until(self.env.bridge.client_in_world, 10), "cliente fuera del mundo")

    # --- ayudas -----------------------------------------------------------
    def post(self, path, body=None, key=HK):
        return self.env.http("POST", path, {} if body is None else body, key=key)

    def play(self, cam_id, key=HK, doc_id=DOC_ID):
        return self.post("/api/camera/play", {"doc_id": doc_id, "cam_id": cam_id}, key=key)

    def state(self, key=HK):
        status, body = self.env.http("GET", "/api/camera", key=key)
        self.assertEqual(status, 200, body)
        return body

    def cam_orders(self):
        return [o for o in self.env.bridge.orders.values() if o["verb"].startswith("camera.")]

    def wait_last(self, op_id, timeout=10.0):
        ok = wait_until(lambda: (self.state().get("last") or {}).get("op_id") == op_id, timeout)
        self.assertTrue(ok, "sin resultado de %s: %s" % (op_id, self.state()))
        return self.state()

    def set_cameras(self, cams):
        doc = copy.deepcopy(self.env.snap()["doc"])
        doc["cameras"] = cams
        self.env.set_doc(doc)

    def cut_client(self):
        self.fake.cut_polls("client", 60000)
        time.sleep(0.4)  # el poll largo en vuelo termina sin orden

    def cam_index(self, cam_id):
        return [c["id"] for c in self.env.snap()["doc"]["cameras"]].index(cam_id)


class K1Play(CamBase):
    def test_k1_play_args_exactos_rol_cliente_y_pose_inicial(self):
        status, body = self.play("cam-02")
        self.assertEqual(status, 200, body)
        op_id = body["op_id"]
        st = self.wait_last(op_id)
        self.assertEqual(st["last"], {"op_id": op_id, "verb": "camera.play", "status": "done",
                                      "reason": None})
        order = self.env.bridge.orders[(self.env.bridge.session, op_id)]
        self.assertEqual(order["role"], "client")
        self.assertEqual(order["args"], CAM02_ARGS)
        cli = self.env.bridge.peer("client")
        self.assertEqual(order["conn"], cli["conn"])
        self.assertEqual(order["epoch"], cli["epoch"])
        self.assertEqual(order["delivered_inst"], self.fake.client.inst)
        self.assertNotIn(op_id, [o["op_id"] for o in self.fake.server.received_orders])
        self.assertIn(op_id, [o["op_id"] for o in self.fake.client.received_orders])
        cam = st["cam"]
        self.assertEqual((cam["active"], cam["playing"], cam["cam_id"], cam["dur_ms"]),
                         (1, 1, "cam-02", 6000))
        self.assertEqual(cam["pose"], [6154000, 2100, 7610000, 28000, -2000, 42000])
        self.assertIsNone(st["in_flight"])
        self.assertIsInstance(st["age_ms"], int)

    def test_k2_el_camino_acaba_en_la_ultima_clave(self):
        self.set_cameras([{"id": "cam-09", "name": "corto", "keys": [
            _key(0), _key(0.15, x=6101.0, yaw=-90), _key(0.3, x=6102.5, yaw=-12, fov=30)]}])
        status, body = self.play("cam-09")
        self.assertEqual(status, 200, body)
        self.wait_last(body["op_id"])
        time.sleep(0.4)
        status, body = self.post("/api/camera/read")
        self.assertEqual(status, 200, body)
        cam = self.wait_last(body["op_id"])["cam"]
        self.assertEqual((cam["active"], cam["playing"], cam["t_ms"], cam["dur_ms"]), (1, 0, 300, 300))
        self.assertEqual(cam["pose"], [6102500, 2000, 7600000, 348000, 0, 30000])

    def test_k3_una_sola_clave_es_ir_a_una_pose(self):
        status, body = self.play("cam-01")
        self.assertEqual(status, 200, body)
        cam = self.wait_last(body["op_id"])["cam"]
        self.assertEqual((cam["active"], cam["playing"], cam["t_ms"], cam["dur_ms"]), (1, 0, 0, 0))
        self.assertEqual(cam["pose"], [6110000, 12000, 7580000, 48000, -9000, 52000])
        order = self.env.bridge.orders[(self.env.bridge.session, body["op_id"])]
        self.assertEqual(order["args"]["c_t_ms"], [0])
        self.assertEqual(order["args"]["c_focus_mm"], [70000])


class K4Credenciales(CamBase):
    def test_k4_la_ia_lee_pero_no_rueda(self):
        for path, body in (("/api/camera/play", {"doc_id": DOC_ID, "cam_id": "cam-01"}),
                           ("/api/camera/stop", {})):
            status, res = self.post(path, body, key=AK)
            self.assertEqual(status, 403, (path, res))
            self.assertEqual(res.get("code"), "forbidden")
        self.assertEqual(self.cam_orders(), [])
        status, res = self.post("/api/camera/read", key=AK)
        self.assertEqual(status, 200, res)
        self.wait_last(res["op_id"])
        self.assertEqual(self.state(key=AK)["cam"], ZERO_CAM)


class K5SinCliente(CamBase):
    def test_k5_client_not_in_game_sin_encolar(self):
        self.fake.restart_peer("client", epoch="e" * 32)
        self.assertTrue(wait_until(lambda: (self.env.bridge.peer("client") or {}).get("epoch") == "e" * 32))
        self.assertFalse(self.env.bridge.client_in_world())
        for path, body in (("/api/camera/play", {"doc_id": DOC_ID, "cam_id": "cam-01"}),
                           ("/api/camera/stop", {}), ("/api/camera/read", {})):
            status, res = self.post(path, body)
            self.assertEqual((status, res.get("code")), (409, "client_not_in_game"), path)
        self.assertEqual(self.cam_orders(), [])


class K6DocYCamara(CamBase):
    def test_k6_doc_changed_y_not_found(self):
        status, res = self.play("cam-01", doc_id="d-00000000")
        self.assertEqual((status, res.get("code"), res.get("pointer")), (409, "doc_changed", "/doc_id"))
        status, res = self.play("cam-77")
        self.assertEqual((status, res.get("code"), res.get("pointer")), (404, "not_found", "/cam_id"))
        status, res = self.post("/api/camera/play", {"doc_id": DOC_ID})
        self.assertEqual(status, 400, res)
        self.assertEqual(self.cam_orders(), [])


class K7Limites(CamBase):
    def test_k7_mismo_milisegundo_33_claves_fuera_del_mapa_y_32_si(self):
        cams = [
            {"id": "cam-10", "name": "ms", "keys": [_key(0), _key(0.0004)]},
            {"id": "cam-11", "name": "33", "keys": [_key(i * 0.1) for i in range(33)]},
            {"id": "cam-12", "name": "fuera", "keys": [_key(0), _key(1, z=15361.0)]},
            {"id": "cam-13", "name": "32", "keys": [_key(i * 0.1, x=6100.0 + i, yaw=359.999,
                                                         pitch=-89.999, fov=179.5, focus=9999.999)
                                                    for i in range(32)]},
        ]
        self.set_cameras(cams)
        status, res = self.play("cam-10")
        self.assertEqual((status, res.get("code"), res.get("pointer")),
                         (422, "invalid", "/cameras/0/keys/1/t"))
        status, res = self.play("cam-11")
        self.assertEqual((status, res.get("code"), res.get("pointer")), (422, "invalid", "/cameras/1/keys"))
        status, res = self.play("cam-12")
        self.assertEqual((status, res.get("code"), res.get("pointer")),
                         (422, "out_of_map", "/cameras/2/keys/1/z"))
        self.assertEqual(self.cam_orders(), [])
        status, res = self.play("cam-13")
        self.assertEqual(status, 200, res)
        order = self.env.bridge.orders[(self.env.bridge.session, res["op_id"])]
        self.assertEqual(len(order["args"]["c_t_ms"]), 32)
        self.assertEqual(order["args"]["c_yaw_mdeg"][0], 359999)
        self.wait_last(res["op_id"])


class K8EnVuelo(CamBase):
    def test_k8_camera_busy_con_una_orden_en_vuelo(self):
        self.cut_client()
        status, res = self.post("/api/camera/read")
        self.assertEqual(status, 200, res)
        self.assertEqual(self.state()["in_flight"], res["op_id"])
        for path, body in (("/api/camera/play", {"doc_id": DOC_ID, "cam_id": "cam-01"}),
                           ("/api/camera/stop", {}), ("/api/camera/read", {})):
            status, res2 = self.post(path, body)
            self.assertEqual((status, res2.get("code")), (409, "camera_busy"), path)
        self.assertEqual(len(self.cam_orders()), 1)


class K9MuchoCamino(CamBase):
    def test_k9_el_mod_rechaza_busy_y_el_camino_sigue(self):
        status, res = self.play("cam-02")
        self.wait_last(res["op_id"])
        status, res = self.play("cam-01")
        self.assertEqual(status, 200, res)
        st = self.wait_last(res["op_id"])
        self.assertEqual(st["last"]["status"], "rejected")
        self.assertEqual(st["last"]["reason"], "busy")
        self.assertEqual(st["cam"]["cam_id"], "cam-02")
        self.assertEqual(self.fake.camera.state()["cam_id"], "cam-02")


class K10Stop(CamBase):
    def test_k10_stop_suelta_la_camara_y_repite_bien(self):
        status, res = self.play("cam-01")
        self.wait_last(res["op_id"])
        for _ in range(2):
            status, res = self.post("/api/camera/stop")
            self.assertEqual(status, 200, res)
            st = self.wait_last(res["op_id"])
            self.assertEqual(st["last"]["status"], "done")
            self.assertEqual(st["cam"], ZERO_CAM)


class K11HelloCliente(CamBase):
    def test_k11_hello_nuevo_del_cliente_descarta_la_orden(self):
        self.cut_client()
        status, res = self.play("cam-01")
        op_id = res["op_id"]
        self.fake.restart_peer("client")
        st = self.wait_last(op_id)
        self.assertEqual(st["last"], {"op_id": op_id, "verb": "camera.play", "status": "dropped",
                                      "reason": "conexion_perdida"})
        self.assertIsNone(st["in_flight"])
        self.assertTrue(wait_until(self.env.bridge.client_in_world, 10))
        status, res = self.play("cam-01")
        self.assertEqual(status, 200, res)
        self.assertEqual(self.wait_last(res["op_id"])["last"]["status"], "done")


class K12Ttl(CamBase):
    def test_k12_ttl_vencido_es_sin_resultado(self):
        self.cut_client()
        status, res = self.play("cam-01")
        op_id = res["op_id"]
        self.env.bridge.sweep(now=self.env.bridge._now() + 5.0)
        st = self.state()
        self.assertEqual(st["last"], {"op_id": op_id, "verb": "camera.play", "status": "dropped",
                                      "reason": "sin_resultado"})
        self.assertIsNone(st["in_flight"])
        self.assertEqual(self.env.bridge.orders[(self.env.bridge.session, op_id)]["bstate"], "descartada")


class K13Servidor(CamBase):
    def test_k13_hello_del_servidor_no_toca_la_orden_del_cliente(self):
        self.cut_client()
        status, res = self.play("cam-01")
        order = self.env.bridge.orders[(self.env.bridge.session, res["op_id"])]
        self.fake.restart_peer("server")
        self.assertTrue(wait_until(lambda: self.env.bridge.peer("server")["conn"] >= 2))
        self.assertEqual(order["bstate"], "pendiente")
        self.assertEqual(self.state()["in_flight"], res["op_id"])

    def test_k13_perder_el_servidor_no_toca_la_orden_del_cliente(self):
        self.cut_client()
        status, res = self.play("cam-01")
        order = self.env.bridge.orders[(self.env.bridge.session, res["op_id"])]
        self.fake.cut_polls("server", 60000)
        time.sleep(0.4)
        self.env.bridge.sweep(now=self.env.bridge._now() + 1.0)
        self.assertTrue(self.env.bridge.peer("server")["lost"])
        self.assertEqual(order["bstate"], "pendiente")
        self.assertEqual(self.state()["in_flight"], res["op_id"])


class K14LecturaRota(CamBase):
    def test_k14_lectura_done_invalida_no_cambia_nada(self):
        status, res = self.play("cam-01")
        self.wait_last(res["op_id"])
        before = self.state()
        self.fake.camera.break_next_read = True
        status, res = self.post("/api/camera/read")
        op_id = res["op_id"]
        self.assertTrue(wait_until(lambda: any(r.get("op_id") == op_id
                                               for r in self.fake.client.sent_results), 5))
        time.sleep(0.3)
        st = self.state()
        self.assertEqual(st["last"], before["last"])
        self.assertEqual(st["cam"], before["cam"])
        self.assertEqual(st["in_flight"], op_id)


class K15Clave(CamBase):
    """F4-web §2: `key` opcional en play reproduce una sola clave como pose fija."""

    def test_k15_key_es_una_pose_fija_y_sus_errores(self):
        for bad in (True, "1", 1.0):
            status, res = self.post("/api/camera/play", {"doc_id": DOC_ID, "cam_id": "cam-02", "key": bad})
            self.assertEqual(status, 400, (bad, res))
        for bad in (3, -1):
            status, res = self.post("/api/camera/play", {"doc_id": DOC_ID, "cam_id": "cam-02", "key": bad})
            self.assertEqual((status, res.get("code"), res.get("pointer")), (404, "not_found", "/key"), bad)
        status, res = self.post("/api/camera/play", {"doc_id": DOC_ID, "cam_id": "cam-77", "key": 0})
        self.assertEqual((status, res.get("pointer")), (404, "/cam_id"))
        self.assertEqual(self.cam_orders(), [])
        status, res = self.post("/api/camera/play", {"doc_id": DOC_ID, "cam_id": "cam-02", "key": 1})
        self.assertEqual(status, 200, res)
        order = self.env.bridge.orders[(self.env.bridge.session, res["op_id"])]
        want = {k: ([0] if k == "c_t_ms" else [v[1]]) for k, v in CAM02_ARGS.items() if k.startswith("c_")}
        want.update(f2=1, cam_id="cam-02")
        self.assertEqual(order["args"], want)
        cam = self.wait_last(res["op_id"])["cam"]
        self.assertEqual((cam["playing"], cam["dur_ms"]), (0, 0))
        self.assertEqual(cam["pose"], [6168000, 2400, 7614000, 8000, -3000, 36000])


class V1LecturaValida(unittest.TestCase):
    def setUp(self):
        from app.backend.camera_live import valid_cam_read
        self.valid = valid_cam_read

    def good(self):
        return {"cam": {"active": 1, "playing": 1, "cam_id": "cam-02", "t_ms": 10, "dur_ms": 6000,
                        "pose": [6154000, -9999999, 7610000, 359999, -90000, 179999]}}

    def test_v1_validas(self):
        self.assertTrue(self.valid(self.good()))
        self.assertTrue(self.valid({"cam": dict(ZERO_CAM, pose=[0] * 6)}))
        r = self.good()
        r["cam"].update(playing=0, t_ms=6000)
        self.assertTrue(self.valid(r))
        r = self.good()
        r["cam"].update(cam_id="c" * 40, pose=[0, 9999999, 99999000, 0, 90000, 1])
        self.assertTrue(self.valid(r))

    def test_v1_cada_regla_rota(self):
        def mut(fn):
            r = self.good()
            fn(r)
            return r
        bad = [
            None, [], {}, {"cam": None},
            mut(lambda r: r.update(extra=1)),
            mut(lambda r: r["cam"].update(extra=1)),
            mut(lambda r: r["cam"].pop("t_ms")),
            mut(lambda r: r["cam"].update(active=2)),
            mut(lambda r: r["cam"].update(active=True)),
            mut(lambda r: r["cam"].update(playing=-1)),
            mut(lambda r: r["cam"].update(cam_id=5)),
            mut(lambda r: r["cam"].update(cam_id="c" * 41)),
            mut(lambda r: r["cam"].update(t_ms=6001)),
            mut(lambda r: r["cam"].update(t_ms=-1)),
            mut(lambda r: r["cam"].update(dur_ms=1.5)),
            mut(lambda r: r["cam"].update(pose=[1, 2, 3, 4, 5])),
            mut(lambda r: r["cam"].update(pose=[1, 2, 3, 4, 5, 6.0])),
            mut(lambda r: r["cam"].update(pose=[1, 2, 3, 4, 5, True])),
            mut(lambda r: r["cam"].update(cam_id="")),
            mut(lambda r: r["cam"]["pose"].__setitem__(3, 360000)),
            mut(lambda r: r["cam"]["pose"].__setitem__(3, -1)),
            mut(lambda r: r["cam"]["pose"].__setitem__(4, 90001)),
            mut(lambda r: r["cam"]["pose"].__setitem__(5, 0)),
            mut(lambda r: r["cam"]["pose"].__setitem__(5, 180000)),
            mut(lambda r: r["cam"]["pose"].__setitem__(1, 10000000)),
            mut(lambda r: r["cam"]["pose"].__setitem__(0, -1)),
            mut(lambda r: r["cam"]["pose"].__setitem__(2, 99999001)),
            {"cam": dict(ZERO_CAM, playing=1)},
            {"cam": dict(ZERO_CAM, cam_id="cam-01")},
            {"cam": dict(ZERO_CAM, dur_ms=5)},
            {"cam": dict(ZERO_CAM, pose=[0, 0, 0, 0, 0, 1])},
        ]
        for i, r in enumerate(bad):
            self.assertFalse(self.valid(r), (i, r))


if __name__ == "__main__":
    unittest.main()
