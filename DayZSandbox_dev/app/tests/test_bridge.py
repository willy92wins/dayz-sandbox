"""F1b-bridge lado backend: BR1, BR2, BR4, BR13-BR17 y BR21 (brief §7).

Peer de prueba minimo por HTTP contra el Bridge real (puerto 0), con
constantes acortadas y reloj inyectado donde hace falta.
"""
import hashlib
import http.client
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.backend.server import Backend
from app.backend.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
HK = "clave-persona-bridge-1234567890"
AK = "clave-ia-bridge-0987654321"
PK = "clave-peer-bridge-abcdef1234567890"
REG_SHA = "0" * 64


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def world_read(epoch, generation=None):
    return {"epoch": epoch, "generation": generation, "registry_n": 0, "registry_sha256": REG_SHA}


class Env:
    def __init__(self, clock=None, **bridge_kwargs):
        self.dir = tempfile.mkdtemp(prefix="dsbx-bridge-")
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)
        self.store = Store(os.path.join(self.dir, "scene.json"), catalog)
        self.log = io.StringIO()
        self.clock = clock if clock is not None else FakeClock()
        kw = {"lease_ms": 300, "hold_ms": 200, "retry_ms": 150, "ttl_ms": 5000,
              "read_retry_ms": (50, 100, 200), "enable_sweeper": False}
        kw.update(bridge_kwargs)
        self.backend = Backend(self.store, HK, AK, port=0, log=self.log, clock=self.clock,
                               bridge_port=0, peer_key=PK, bridge_kwargs=kw)
        self.port = self.backend.port
        self.bridge = self.backend.bridge
        self.bport = self.bridge.port
        self.thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.thread.start()
        self.bodies = []
        self.peers = {}
        self._closed = False

    def close(self):
        if not self._closed:
            self._closed = True
            self.backend.shutdown()
            self.thread.join(timeout=5)
        shutil.rmtree(self.dir, ignore_errors=True)

    # --- HTTP al bridge ---
    def breq(self, method, path, body=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.bport, timeout=10)
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else b"")
        headers = {"Content-Type": "application/json", "Content-Length": str(len(data))}
        conn.request(method, path, body=data if data else None, headers=headers)
        resp = conn.getresponse()
        text = resp.read().decode("utf-8")
        status = resp.status
        conn.close()
        self.bodies.append(text)
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        return status, parsed, text

    def hello(self, role="server", inst=None, epoch=None, key=PK, proto="dsbx1", extra=None):
        inst = inst or secrets.token_hex(16)
        epoch = epoch or secrets.token_hex(16)
        body = {"proto": proto, "peer": role, "inst": inst, "epoch": epoch,
                "mod_ver": "test-1", "build": "retail"}
        if role == "server":
            body.update({"map": "chernarus", "world_size": 15360, "modset": [], "actor_engine": "none"})
        body.update(extra or {})
        st, parsed, _ = self.breq("POST", "/hello?key=" + key, body)
        if st == 200 and isinstance(parsed, dict):
            self.peers[role] = {"inst": inst, "epoch": epoch, "session": parsed["session"], "conn": parsed["conn"]}
        return st, parsed

    def poll(self, role="server", deliver=None, inst=None, session=None, conn=None, epoch=None):
        info = self.peers.get(role, {})
        q = ("peer=%s&inst=%s&session=%s&conn=%s" % (
            role, inst if inst is not None else info.get("inst", ""),
            session if session is not None else info.get("session", ""),
            conn if conn is not None else info.get("conn", "")))
        if deliver is not None:
            q += "&deliver=%s" % deliver
        return self.breq("GET", "/poll?key=%s&%s" % (PK, q))

    def result(self, order, status="done", reason=None, read=None, dup=False, inst=None, session=None):
        info = self.peers.get("server", {})
        q = "peer=server&inst=%s&session=%s" % (inst if inst is not None else info.get("inst", ""),
                                               session if session is not None else info.get("session", ""))
        body = {"op_id": order["op_id"], "session": order["session"], "epoch": order["epoch"],
                "status": status, "reason": reason, "dup": dup,
                "read": world_read(order["epoch"]) if read is None else read}
        return self.breq("POST", "/result?key=%s&%s" % (PK, q), body)

    def gen_for(self, order, rev_delta=0):
        return {"session": order["session"], "op_id": order["op_id"],
                "rev": order["args"]["rev"] + rev_delta, "hash": order["args"]["hash"]}

    def done_read(self, order, generation="match"):
        gen = self.gen_for(order) if generation == "match" else generation
        return world_read(order["epoch"], gen)

    def reconcile(self, generation=None):
        st, parsed, _ = self.poll()
        self.assert_poll_order(st, parsed, "state.read")
        order = parsed["ops"][0]
        st, r, _ = self.result(order, "done", None, world_read(order["epoch"], generation))
        assert st == 200, r
        assert self.bridge.reconciled
        return order

    def assert_poll_order(self, st, parsed, verb):
        assert st == 200 and parsed and parsed.get("ok") is True, parsed
        assert len(parsed.get("ops", [])) == 1, parsed
        assert parsed["ops"][0]["verb"] == verb, parsed

    def apply_direct(self):
        snap = self.store.snapshot()
        return self.backend.apply(snap["doc_id"], snap["rev"], snap["hash"])

    def api_apply(self):
        snap = self.store.snapshot()
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        data = json.dumps({"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]}).encode()
        conn.request("POST", "/api/apply", body=data,
                     headers={"Authorization": "Bearer " + HK, "Content-Type": "application/json"})
        resp = conn.getresponse()
        text = resp.read().decode("utf-8")
        conn.close()
        self.bodies.append(text)
        return resp.status, json.loads(text)


class BridgeBase(unittest.TestCase):
    clock = None

    def make_env(self, **kw):
        clock = kw.pop("clock", self.clock)
        env = Env(clock=clock, **kw)
        self.addCleanup(self._close_env, env)
        return env

    def _close_env(self, env):
        env.close()
        for text in env.bodies + [env.log.getvalue()]:
            self.assertNotIn(PK, text)
            self.assertNotIn(HK, text)
            self.assertNotIn(AK, text)


class BR1Hello(BridgeBase):
    def test_hello_valido_dos_peers(self):
        env = self.make_env()
        for role in ("server", "client"):
            st, r = env.hello(role)
            self.assertEqual(st, 200, r)
            self.assertTrue(r["ok"] is True)
            self.assertTrue(re.fullmatch(r"[0-9a-f]{16}", r["session"]))
            self.assertEqual((r["lease_ms"], r["hold_ms"], r["wire_cap"]), (300, 200, 3500))
            self.assertEqual(r["conn"], 1)

    def test_clave_mala_o_ausente_401_y_nada_registrado(self):
        env = self.make_env()
        st, r, _ = env.breq("POST", "/hello?key=clave-mala",
                            {"proto": "dsbx1", "peer": "server", "inst": "a" * 32, "epoch": "b" * 32,
                             "mod_ver": "t", "build": "retail", "map": "m", "world_size": 1,
                             "modset": [], "actor_engine": "none"})
        self.assertEqual((st, r), (401, {"ok": False, "error": "bad_key"}))
        st, r, _ = env.breq("POST", "/hello", {"proto": "dsbx1"})
        self.assertEqual(st, 401)
        self.assertEqual(env.bridge.peers, {})
        self.assertNotIn("clave-mala", env.log.getvalue())
        self.assertIn("key=***", env.log.getvalue())

    def test_proto_distinto_409_y_malformado_400_y_log_redactado(self):
        env = self.make_env()
        st, r = env.hello(proto="otro")
        self.assertEqual((st, r["error"]), (409, "proto_mismatch"))
        st, r, _ = env.breq("POST", "/hello?key=" + PK, raw=b"{roto")
        self.assertEqual((st, r["error"]), (400, "bad_request"))
        st, r = env.hello(extra={"inst": "no-hex"})
        self.assertEqual((st, r["error"]), (400, "bad_request"))
        st, r = env.hello()
        self.assertEqual(st, 200)
        self.assertIn("key=***", env.log.getvalue())


class BR2Poll(BridgeBase):
    def test_una_orden_por_poll_y_deliver0_no_entrega(self):
        env = self.make_env()
        env.hello()
        env.reconcile()
        a, b = env.apply_direct(), env.apply_direct()
        self.assertTrue(a["ok"] and b["ok"])
        t0 = time.monotonic()
        st, r, _ = env.poll(deliver=0)
        self.assertEqual((st, r["ops"]), (200, []))
        self.assertLess(time.monotonic() - t0, 0.15)
        st, r, _ = env.poll()
        self.assertEqual(len(r["ops"]), 1)
        self.assertEqual(r["ops"][0]["op_id"], a["op_id"])

    def test_sin_ordenes_vuelve_en_hold(self):
        env = self.make_env(clock=time.monotonic)
        env.hello()
        env.reconcile()
        t0 = time.monotonic()
        st, r, _ = env.poll()
        took = time.monotonic() - t0
        self.assertEqual((st, r["ops"]), (200, []))
        self.assertTrue(0.1 <= took < 0.7, took)

    def test_session_inst_o_conn_viejas_409_sin_entrega(self):
        env = self.make_env()
        env.hello()
        env.reconcile()
        env.apply_direct()
        for kw in ({"session": "0" * 16}, {"inst": "f" * 32}, {"conn": 99}):
            st, r, _ = env.poll(**kw)
            self.assertEqual((st, r["error"]), (409, "hello_required"), kw)
        st, r, _ = env.poll()
        self.assertEqual(len(r["ops"]), 1)


class BR4SinPeer(BridgeBase):
    def test_pendiente_hasta_ttl_y_fallido_no_entregada(self):
        env = self.make_env(ttl_ms=1000, lease_ms=10000)
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertEqual(env.backend.ops[op_id]["state"], "pendiente")
        env.clock.advance(0.5)
        env.bridge.sweep()
        self.assertEqual(env.backend.ops[op_id]["state"], "pendiente")
        env.clock.advance(0.6)
        env.bridge.sweep()
        op = env.backend.ops[op_id]
        self.assertEqual((op["state"], op["reason"], op["origin"]), ("fallido", "no_entregada", "backend"))


class BR13Reconciliar(BridgeBase):
    def _until_scene(self, env, read_order, advance, expect_status=200):
        env.clock.advance(advance)
        env.bridge.sweep()
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "state.read")
        order = r["ops"][0]
        st, rr, _ = env.result(order, "done", None, world_read(order["epoch"]))
        self.assertEqual(st, 200, rr)
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "scene.apply")
        return r["ops"][0]

    def test_antes_de_lectura_valida_no_se_entrega_scene(self):
        env = self.make_env()
        env.hello()
        env.apply_direct()
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "state.read")

    def test_error_rejected_incompleto_y_epoch_viejo_no_reconcilian(self):
        for kind in ("error", "rejected", "incompleto", "epoch_viejo"):
            with self.subTest(kind=kind):
                env = self.make_env()
                try:
                    env.hello()
                    env.apply_direct()
                    st, r, _ = env.poll()
                    env.assert_poll_order(st, r, "state.read")
                    order = r["ops"][0]
                    if kind in ("error", "rejected"):
                        st, rr, _ = env.result(order, kind, "boom", {})
                        self.assertEqual(st, 200, rr)
                        advance = 0.06
                    elif kind == "incompleto":
                        st, rr, _ = env.result(order, "done", None, {"epoch": order["epoch"]})
                        self.assertEqual((st, rr["error"]), (400, "bad_request"))
                        advance = 0.16
                    else:
                        bad = world_read("e" * 32)
                        st, rr, _ = env.result(order, "done", None, bad)
                        self.assertEqual(st, 200, rr)
                        advance = 0.06
                    self.assertFalse(env.bridge.reconciled)
                    self._until_scene(env, order, advance)
                finally:
                    env.close()

    def test_tras_un_error_no_sale_scene_hasta_la_lectura_valida(self):  # (g) y (r)
        env = self.make_env()
        env.hello()
        env.apply_direct()
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "state.read")
        st, rr, _ = env.result(r["ops"][0], "error", "boom", {})
        self.assertEqual(st, 200, rr)
        st, r, _ = env.poll()
        self.assertEqual((st, r["ops"]), (200, []))
        self.assertFalse(env.bridge.reconciled)

    def test_error_con_read_valido_no_reconcilia(self):  # (r)
        env = self.make_env()
        env.hello()
        env.apply_direct()
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "state.read")
        order = r["ops"][0]
        st, rr, _ = env.result(order, "error", "boom", world_read(order["epoch"]))
        self.assertEqual(st, 200, rr)
        self.assertFalse(env.bridge.reconciled)
        self.assertIsNone(env.bridge.world)

    def test_lectura_de_inst_anterior_no_reconcilia(self):
        env = self.make_env()
        env.hello()
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "state.read")
        old_order = r["ops"][0]
        old_inst = env.peers["server"]["inst"]
        env.hello(inst=secrets.token_hex(16), epoch=env.peers["server"]["epoch"])
        env.apply_direct()
        st, rr, _ = env.result(old_order, "done", None, world_read(old_order["epoch"]), inst=old_inst)
        self.assertEqual(st, 200, rr)
        self.assertFalse(env.bridge.reconciled)
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "state.read")
        order = r["ops"][0]
        st, rr, _ = env.result(order, "done", None, world_read(order["epoch"]))
        self.assertEqual(st, 200)
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "scene.apply")

    def test_lectura_sin_generation_400_y_no_reconcilia(self):
        env = self.make_env()
        env.hello()
        env.apply_direct()
        st, r, _ = env.poll()
        env.assert_poll_order(st, r, "state.read")
        order = r["ops"][0]
        sin_gen = {"epoch": order["epoch"], "registry_n": 0, "registry_sha256": REG_SHA}
        st, rr, _ = env.result(order, "done", None, sin_gen)
        self.assertEqual((st, rr["error"]), (400, "bad_request"))
        self.assertFalse(env.bridge.reconciled)
        st, r, _ = env.poll()
        self.assertEqual((st, r["ops"]), (200, []))


class BR14Cola(BridgeBase):
    def test_32_vivas_y_la_33_queue_full(self):
        env = self.make_env(ttl_ms=60000)
        for _ in range(32):
            st, r = env.api_apply()
            self.assertEqual(st, 200, r)
        seq = env.backend.seq
        st, r = env.api_apply()
        self.assertEqual((st, r["code"]), (409, "queue_full"))
        self.assertEqual(len(env.backend.ops), 32)
        self.assertEqual(env.backend.seq, seq)


class BR15WireCap(BridgeBase):
    def test_pagina_de_3500_entra_y_3501_da_413(self):
        env = self.make_env()
        env.hello()
        info = env.peers["server"]
        base = {"catalog_id": "a" * 16, "page": 1, "pages": 1, "build": "b1",
                "modset_hash": "c" * 64, "classes": [["X", "Base"]]}
        raw = json.dumps(base, separators=(",", ":")).encode()
        pad = 3500 - len(raw)
        base["classes"] = [["X" * (1 + pad), "Base"]]
        raw = json.dumps(base, separators=(",", ":")).encode()
        self.assertEqual(len(raw), 3500)
        path = "/catalog?key=%s&peer=server&inst=%s&session=%s" % (PK, info["inst"], info["session"])
        st, r, _ = env.breq("POST", path, raw=raw)
        self.assertEqual(st, 200, r)
        st, r, _ = env.breq("POST", path, raw=b"x" * 3501)
        self.assertEqual((st, r["error"]), (413, "too_large"))

    def test_result_too_large_pasa_a_parcial_y_orden_que_no_cabe_se_rechaza(self):
        env = self.make_env()
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        st, rr, _ = env.result(order, "error", "result_too_large", {})
        self.assertEqual(st, 200, rr)
        op = env.backend.ops[r["op_id"]]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "result_too_large"))
        before = env.bridge.live_scene_count()
        ok, info = env.bridge.enqueue_order("scene.apply", {"blob": "x" * 4000}, op_id="op-grande")
        self.assertEqual((ok, info), (False, "wire_cap_exceeded"))
        self.assertEqual(env.bridge.live_scene_count(), before)


class BR16Catalogo(BridgeBase):
    def _page(self, env, catalog_id, page, pages, classes, build="b1", modset_hash="c" * 64):
        info = env.peers["server"]
        path = "/catalog?key=%s&peer=server&inst=%s&session=%s" % (PK, info["inst"], info["session"])
        body = {"catalog_id": catalog_id, "page": page, "pages": pages, "build": build,
                "modset_hash": modset_hash, "classes": classes}
        return env.breq("POST", path, body)

    def test_paginas_desordenadas_repetida_y_sha(self):
        env = self.make_env()
        env.hello()
        cid = "a" * 16
        self.assertEqual(self._page(env, cid, 2, 3, [["ClaseB", "BaseB"]])[0], 200)
        self.assertEqual(self._page(env, cid, 1, 3, [["ClaseA", "BaseA"]])[0], 200)
        self.assertEqual(self._page(env, cid, 1, 3, [["ClaseA", "BaseA"]])[0], 200)
        st, r, _ = self._page(env, cid, 3, 3, [["ClaseC", "BaseC"]])
        self.assertEqual(st, 200, r)
        self.assertTrue(r["complete"] is True)
        clases = [["ClaseA", "BaseA"], ["ClaseB", "BaseB"], ["ClaseC", "BaseC"]]
        sha = hashlib.sha256(json.dumps(clases, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(r["sha256"], sha)
        self.assertEqual((env.bridge.catalog["n_classes"], env.bridge.catalog["sha256"]), (3, sha))

    def test_clase_repetida_y_pages_incoherente_409(self):
        env = self.make_env()
        env.hello()
        cid = "b" * 16
        self._page(env, cid, 1, 2, [["ClaseA", "BaseA"]])
        st, r, _ = self._page(env, cid, 2, 2, [["ClaseA", "Otra"]])
        self.assertEqual((st, r["error"]), (409, "bad_catalog"))
        cid2 = "c" * 16
        self._page(env, cid2, 1, 2, [["X1", "B"]])
        st, r, _ = self._page(env, cid2, 2, 3, [["X2", "B"]])
        self.assertEqual((st, r["error"]), (409, "bad_catalog"))


class BR17Secretos(BridgeBase):
    def test_peer_key_igual_o_vacia_no_arranca(self):
        d = tempfile.mkdtemp(prefix="dsbx-br17-")
        self.addCleanup(shutil.rmtree, d, True)
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)
        store = Store(os.path.join(d, "scene.json"), catalog)
        for pk in (HK, AK, ""):
            with self.assertRaises(ValueError):
                Backend(store, HK, AK, port=0, log=io.StringIO(), bridge_port=0, peer_key=pk)

    def test_peer_key_no_aparece_en_respuestas_ni_logs(self):
        env = self.make_env()
        env.hello()
        env.hello("client")
        env.reconcile()
        env.api_apply()
        env.poll(deliver=0)
        for text in env.bodies + [env.log.getvalue()]:
            self.assertNotIn(PK, text)


class BR21Reconectar(BridgeBase):
    def test_sin_polls_pendiente_falla_y_no_se_ejecuta_al_volver(self):
        env = self.make_env()
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        op_id = r["op_id"]
        env.clock.advance(0.35)
        env.bridge.sweep()
        op = env.backend.ops[op_id]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "conexion_perdida"))
        old_conn = env.peers["server"]["conn"]
        env.hello(epoch=env.peers["server"]["epoch"], inst=env.peers["server"]["inst"])
        st, poll, _ = env.poll()
        env.assert_poll_order(st, poll, "state.read")
        read_order = poll["ops"][0]
        st, rr, _ = env.result(read_order, "done", None, world_read(read_order["epoch"]))
        self.assertEqual(st, 200)
        st, poll, _ = env.poll()
        self.assertEqual(poll["ops"], [])
        r2 = env.apply_direct()
        st, poll, _ = env.poll()
        env.assert_poll_order(st, poll, "scene.apply")
        self.assertEqual(poll["ops"][0]["op_id"], r2["op_id"])
        st, rr, _ = env.poll(conn=old_conn)
        self.assertEqual((st, rr["error"]), (409, "hello_required"))

    def test_poll_con_conn_anterior_misma_session_e_inst_409(self):
        env = self.make_env()
        env.hello()
        first_conn = env.peers["server"]["conn"]
        env.hello(epoch=env.peers["server"]["epoch"], inst=env.peers["server"]["inst"])
        env.apply_direct()
        st, r, _ = env.poll(conn=first_conn)
        self.assertEqual((st, r["error"]), (409, "hello_required"))
        self.assertNotIn("ops", r)


class X3Backend(BridgeBase):
    """Mutaciones del lado backend: cada prueba caza al menos una de §7 X3."""

    def test_ttl_de_entregada_a_parcial_no_a_fallido(self):  # (f)
        env = self.make_env(ttl_ms=1000, lease_ms=10000)
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        env.clock.advance(1.1)
        env.bridge.sweep()
        op = env.backend.ops[r["op_id"]]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "sin_resultado"))

    def test_resultado_repetido_no_transiciona(self):  # (i)
        env = self.make_env()
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        read = env.done_read(order)
        self.assertEqual(env.result(order, "done", None, read)[0], 200)
        seq = env.backend.seq
        self.assertEqual(env.result(order, "done", None, read, dup=True)[0], 200)
        self.assertEqual(env.backend.seq, seq)
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "observado")

    def test_predicado_exige_rev_y_hash(self):  # (k) y (v) por la via directa
        env = self.make_env()
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        read = env.done_read(order, generation=env.gen_for(order, rev_delta=9))
        self.assertEqual(env.result(order, "done", None, read)[0], 200)
        op = env.backend.ops[r["op_id"]]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))

    def test_primer_resultado_tardio_de_parcial_se_aplica(self):  # (t)
        env = self.make_env(ttl_ms=1000, lease_ms=10000)
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        env.clock.advance(1.1)
        env.bridge.sweep()
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "parcial")
        self.assertEqual(env.result(order, "done", None, env.done_read(order))[0], 200)
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "observado")

    def test_error_tardio_sigue_parcial_con_motivo_nuevo(self):  # (t), fila parcial->parcial
        env = self.make_env(ttl_ms=1000, lease_ms=10000)
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        env.clock.advance(1.1)
        env.bridge.sweep()
        seq = env.backend.seq
        self.assertEqual(env.result(order, "error", "tarde", {})[0], 200)
        op = env.backend.ops[r["op_id"]]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "tarde"))
        self.assertGreater(env.backend.seq, seq)

    def test_reconciliacion_con_rev_distinta_falla_no_observa(self):  # (v)
        env = self.make_env(ttl_ms=1000, lease_ms=10000)
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        env.clock.advance(1.1)
        env.bridge.sweep()
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "parcial")
        st, poll, _ = env.poll()
        env.assert_poll_order(st, poll, "state.read")
        read_order = poll["ops"][0]
        gen = {"session": order["session"], "op_id": order["op_id"],
               "rev": order["args"]["rev"] + 5, "hash": order["args"]["hash"]}
        st, rr, _ = env.result(read_order, "done", None, world_read(read_order["epoch"], gen))
        self.assertEqual(st, 200, rr)
        op = env.backend.ops[r["op_id"]]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))

    def test_elegibilidad_rechaza_orden_de_conn_anterior(self):  # (s): aisla la elegibilidad de la transicion del hello
        env = self.make_env()
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        with env.bridge.lock:
            env.bridge.orders[(env.bridge.session, r["op_id"])]["conn"] = 0
        st, poll, _ = env.poll()
        self.assertEqual((st, poll["ops"]), (200, []))

    def test_reentrega_no_cambia_de_inst_en_la_misma_conn(self):  # (e): aisla la guarda de reentrega
        env = self.make_env()
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        self.assertEqual(poll["ops"][0]["op_id"], r["op_id"])
        nueva = secrets.token_hex(16)
        with env.bridge.lock:
            env.bridge.peers["server"]["inst"] = nueva
        env.clock.advance(0.2)
        st, poll, _ = env.poll(inst=nueva)
        self.assertEqual((st, poll["ops"]), (200, []))

    def test_reentrega_solo_a_la_misma_inst(self):  # (e): la nueva inst recibe lectura, no la orden vieja
        env = self.make_env(ttl_ms=60000)
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        self.assertEqual(poll["ops"][0]["op_id"], r["op_id"])
        env.hello(epoch=env.peers["server"]["epoch"], inst=secrets.token_hex(16))
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "parcial")
        st, poll, _ = env.poll()
        env.assert_poll_order(st, poll, "state.read")
        self.assertNotEqual(poll["ops"][0]["op_id"], r["op_id"])


class IntegracionOrquestador(BridgeBase):
    """Arreglos de la revision de F1bb-1 al integrarla (orquestador)."""

    def test_error_repetido_no_vuelve_a_transicionar(self):  # (i) con la orden aun parcial
        env = self.make_env()
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        self.assertEqual(env.result(order, "error", "primero", {})[0], 200)
        op = env.backend.ops[r["op_id"]]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "primero"))
        seq = env.backend.seq
        self.assertEqual(env.result(order, "error", "segundo", {}, dup=True)[0], 200)
        self.assertEqual(env.backend.seq, seq)
        self.assertEqual(env.backend.ops[r["op_id"]]["reason"], "primero")

    def test_poll_retenido_de_una_conn_sustituida_recibe_409(self):
        env = self.make_env(hold_ms=1500)
        env.hello()
        env.reconcile()
        info = dict(env.peers["server"])
        out = {}

        def retenido():
            out["r"] = env.poll(inst=info["inst"], session=info["session"], conn=info["conn"])

        t = threading.Thread(target=retenido)
        t.start()
        time.sleep(0.3)
        env.hello(inst=info["inst"], epoch=info["epoch"])
        t.join(timeout=5)
        st, r, _ = out["r"]
        self.assertEqual((st, r["error"]), (409, "hello_required"))

    def test_lecturas_de_recuperacion_siguen_el_calendario(self):
        env = self.make_env(ttl_ms=1000, lease_ms=60000, read_retry_ms=(50, 100, 200))
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        env.assert_poll_order(st, poll, "scene.apply")
        env.clock.advance(1.1)
        env.bridge.sweep()
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "parcial")

        def leer():
            st, poll, _ = env.poll()
            env.assert_poll_order(st, poll, "state.read")
            o = poll["ops"][0]
            st, rr, _ = env.result(o, "done", None, world_read(o["epoch"]))
            self.assertEqual(st, 200, rr)

        def lectura_pendiente():
            with env.bridge.lock:
                return env.bridge._active_read_locked() is not None

        leer()  # la lectura no muestra la orden: sigue parcial y se programan reintentos
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "parcial")
        for espera in (0.05, 0.1, 0.2, 0.2):
            env.clock.advance(espera - 0.01)
            env.bridge.sweep()
            self.assertFalse(lectura_pendiente(), espera)
            env.clock.advance(0.02)
            env.bridge.sweep()
            self.assertTrue(lectura_pendiente(), espera)
            leer()

    def test_resultado_tardio_de_orden_ya_reconciliada_se_acusa_sin_cambios(self):
        env = self.make_env(ttl_ms=1000, lease_ms=60000)
        env.hello()
        env.reconcile()
        r = env.apply_direct()
        st, poll, _ = env.poll()
        order = poll["ops"][0]
        env.clock.advance(1.1)
        env.bridge.sweep()
        st, poll, _ = env.poll()
        env.assert_poll_order(st, poll, "state.read")
        ro = poll["ops"][0]
        st, rr, _ = env.result(ro, "done", None, world_read(ro["epoch"], env.gen_for(order)))
        self.assertEqual(st, 200, rr)
        op = env.backend.ops[r["op_id"]]
        self.assertEqual((op["state"], op["reason"]), ("observado", "reconciliada"))
        seq = env.backend.seq
        st, rr, _ = env.result(order, "done", None, env.done_read(order))
        self.assertEqual((st, rr), (200, {"ok": True}))
        self.assertEqual(env.backend.seq, seq)
        self.assertEqual(env.backend.ops[r["op_id"]]["state"], "observado")

    def _rechazo_espera_al_cuerpo(self, env, path, anunciado, parcial, codigo):
        s = socket.create_connection(("127.0.0.1", env.bport))
        self.addCleanup(s.close)
        cabecera = ("POST %s HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                    "Content-Length: %d\r\n\r\n" % (path, anunciado)).encode("latin-1")
        s.sendall(cabecera + b"x" * parcial)
        s.settimeout(0.4)
        with self.assertRaises(socket.timeout):  # vacia el cuerpo antes de contestar: no hay RST
            s.recv(1)
        s.settimeout(5)
        s.sendall(b"x" * (anunciado - parcial))
        datos = b""
        while True:
            trozo = s.recv(65536)
            if not trozo:
                break
            datos += trozo
        texto = datos.decode("utf-8")
        self.assertTrue(texto.startswith("HTTP/1.0 %d" % codigo), texto[:60])
        return texto

    def test_rechazos_con_cuerpo_lo_vacian_antes_de_contestar(self):
        env = self.make_env()
        env.hello()
        info = env.peers["server"]
        texto = self._rechazo_espera_al_cuerpo(env, "/hello?key=clave-mala", 300, 100, 401)
        self.assertIn('"bad_key"', texto)
        path = "/catalog?key=%s&peer=server&inst=%s&session=%s" % (PK, info["inst"], info["session"])
        texto = self._rechazo_espera_al_cuerpo(env, path, 3501, 1000, 413)
        self.assertIn('"too_large"', texto)

    def test_cuerpo_que_no_llega_no_retiene_el_hilo(self):
        env = self.make_env()
        env.bridge.drain_s = 0.3
        s = socket.create_connection(("127.0.0.1", env.bport))
        self.addCleanup(s.close)
        s.sendall(b"POST /hello?key=clave-mala HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                  b"Content-Length: 300\r\n\r\nxx")
        s.settimeout(3)
        t0 = time.monotonic()
        datos = b""
        try:
            while True:
                trozo = s.recv(65536)
                if not trozo:
                    break
                datos += trozo
        except OSError:
            pass  # lo que se mide es que conteste y cierre a tiempo
        self.assertLess(time.monotonic() - t0, 1.5)
        self.assertTrue(datos.startswith(b"HTTP/1.0 401"), datos[:60])

    def test_resultado_con_session_ajena_en_el_cuerpo_400(self):
        env = self.make_env()
        env.hello()
        env.reconcile()
        env.apply_direct()
        st, poll, _ = env.poll()
        order = dict(poll["ops"][0])
        read = env.done_read(order)
        order["session"] = "0" * 16
        st, rr, _ = env.result(order, "done", None, read)
        self.assertEqual((st, rr["error"]), (400, "bad_request"))

    def test_poll_tardio_sin_sweep_declara_perdida_y_da_409(self):
        for deliver in (None, 0):
            with self.subTest(deliver=deliver):
                env = self.make_env(lease_ms=300, ttl_ms=60000)
                env.hello()
                env.reconcile()
                r = env.apply_direct()
                op_id = r["op_id"]
                env.clock.advance(0.35)
                st, poll, _ = env.poll(deliver=deliver)
                self.assertEqual((st, poll["error"]), (409, "hello_required"))
                op = env.backend.ops[op_id]
                self.assertEqual((op["state"], op["reason"]), ("fallido", "conexion_perdida"))

    @staticmethod
    def _read_until_closed(s):
        """(texto, cerrada). Solo cuenta como cierre el EOF o el corte del servidor; un timeout, no."""
        got = b""
        try:
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    return got.decode("latin-1"), True
                got += chunk
        except socket.timeout:
            return got.decode("latin-1"), False
        except OSError:
            return got.decode("latin-1"), True

    def test_cuerpo_aceptado_que_no_llega_da_400_y_cierra(self):
        env = self.make_env()
        env.bridge.body_s = 0.3
        s = socket.create_connection(("127.0.0.1", env.bport))
        self.addCleanup(s.close)
        s.settimeout(3.0)
        req = ("POST /hello?key=%s HTTP/1.1\r\nHost: 127.0.0.1\r\n"
               "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{" % PK).encode("latin-1")
        t0 = time.monotonic()
        s.sendall(req)
        texto, cerrada = self._read_until_closed(s)
        elapsed = time.monotonic() - t0
        self.assertTrue(cerrada, "el servidor no cerro la conexion")
        self.assertLess(elapsed, 1.5)
        self.assertTrue(texto.startswith("HTTP/1.0 400"), texto[:60])
        self.assertIn('"bad_request"', texto)

    def test_shutdown_cierra_conexion_colgada_en_cuerpo(self):
        env = self.make_env()
        env.bridge.body_s = 30.0
        s = socket.create_connection(("127.0.0.1", env.bport))
        self.addCleanup(s.close)
        s.settimeout(3.0)
        req = ("POST /hello?key=%s HTTP/1.1\r\nHost: 127.0.0.1\r\n"
               "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{" % PK).encode("latin-1")
        s.sendall(req)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            with env.bridge._conns_lock:
                if env.bridge._conns:
                    break
            time.sleep(0.01)
        time.sleep(0.05)
        t0 = time.monotonic()
        env.backend.shutdown()
        _, cerrada = self._read_until_closed(s)
        elapsed = time.monotonic() - t0
        self.assertTrue(cerrada, "shutdown no cerro la conexion colgada")
        self.assertLess(elapsed, 2.0)

    def test_conexion_que_se_registra_tras_el_cierre_se_corta(self):
        # H4, ronda 2 de Sol: el handler de una conexion ya aceptada se para justo antes de
        # registrarse; shutdown() toma su copia sin ella y, al registrarse despues, la conexion
        # tiene que cortarse sola en vez de quedarse esperando las cabeceras.
        from app.backend import bridge as bridge_mod
        env = self.make_env()
        original = bridge_mod._BridgeHandler.setup
        entra, sigue = threading.Event(), threading.Event()

        def setup_tardio(handler):
            entra.set()
            sigue.wait(5)
            original(handler)

        bridge_mod._BridgeHandler.setup = setup_tardio
        self.addCleanup(setattr, bridge_mod._BridgeHandler, "setup", original)
        s = socket.create_connection(("127.0.0.1", env.bport))
        self.addCleanup(s.close)
        s.settimeout(3.0)
        s.sendall(b"GET /poll HTTP/1.1\r\n")  # cabeceras sin terminar
        self.assertTrue(entra.wait(2), "el handler no llego a setup")
        env.backend.shutdown()
        sigue.set()
        _, cerrada = self._read_until_closed(s)
        self.assertTrue(cerrada, "una conexion registrada despues del cierre siguio abierta")
        with env.bridge._conns_lock:
            self.assertEqual(env.bridge._conns, set())


class MsDesdeElArranque(BridgeBase):
    """Los ms publicos cuentan desde el arranque del bridge (brief de F1b-peers, P-02 de Sol)."""

    def test_ms_pequenos_y_diferencia_exacta_con_reloj_enorme(self):
        # 4294967,5 s y 0,5 s son exactos en binario: la diferencia esperada es exactamente 500.
        env = self.make_env(clock=FakeClock(4294967.5), lease_ms=60000)
        env.hello()
        env.reconcile()
        env.apply_direct()
        env.clock.advance(0.5)
        st, poll, _ = env.poll()
        env.assert_poll_order(st, poll, "scene.apply")
        order = poll["ops"][0]
        # Un peer de Enforce los lee en int de 32 bits; por debajo de 2^24 tambien caben exactos en float.
        self.assertTrue(0 <= order["issued_ms"] < 2 ** 24, order["issued_ms"])
        self.assertTrue(0 <= poll["now_ms"] < 2 ** 24, poll["now_ms"])
        self.assertEqual(poll["now_ms"] - order["issued_ms"], 500)


class CadenasQueElMotorCorta(BridgeBase):
    """Ninguna cadena de una orden pasa de 1000 bytes en el cable: el motor corta a 1023 lo que lee
    (F0.3-0, BASE-01 y D10). Se cuenta la forma escapada (brief de F1b-peers §3.5)."""

    def test_cadena_de_mas_de_1000_bytes_no_se_encola_y_1000_si(self):
        env = self.make_env()
        env.hello()
        env.reconcile()
        antes = dict(env.bridge.orders)
        # 1001 bytes en el cable: ASCII, UTF-8 de dos bytes y comillas que se escapan como \"
        for larga in ("d" * 1001, "ñ" * 500 + "d", '"' * 500 + "d"):
            ok, info = env.bridge.enqueue_order(
                "scene.apply", {"doc_id": larga, "rev": 1, "hash": "a" * 64}, op_id="op-larga")
            self.assertEqual((ok, info), (False, "wire_cap_exceeded"), larga[:12])
        self.assertEqual(env.bridge.orders, antes)
        for i, justa in enumerate(("d" * 1000, "ñ" * 500, '"' * 500)):  # 1000 bytes en el cable
            ok, order = env.bridge.enqueue_order(
                "scene.apply", {"doc_id": justa, "rev": 1, "hash": "a" * 64}, op_id="op-justa-%d" % i)
            self.assertTrue(ok, justa[:12])
            self.assertEqual(order["op_id"], "op-justa-%d" % i)


class ArranqueConBridge(unittest.TestCase):
    """`server.py --config` con bridge: guarda peer_key y con --port 0 no usa el puerto fijo."""

    def test_main_guarda_peer_key_y_con_port_0_el_bridge_es_efimero(self):
        d = Path(tempfile.mkdtemp(prefix="dsbx-br-main-"))
        self.addCleanup(shutil.rmtree, d, True)
        cfgp = d / "backend.json"
        cfgp.write_text(json.dumps({"scene": str(d / "scene.json"),
                                    "catalog": str(FIXTURES / "catalog-m1.json"),
                                    "human_key": HK, "ai_key": AK}), encoding="utf-8")
        script = ROOT / "app" / "backend" / "server.py"
        p = subprocess.Popen([sys.executable, str(script), "--config", str(cfgp), "--port", "0"],
                             cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            first = p.stdout.readline()
            second = p.stdout.readline()
        finally:
            p.terminate()
            out, err = p.communicate(timeout=20)
        output = first + second + out + err
        self.assertIn("Escuchando en http://127.0.0.1:", first, output)
        m = re.search(r"Bridge dsbx1 en 127\.0\.0\.1:(\d+)", second)
        self.assertTrue(m, output)
        self.assertNotEqual(int(m.group(1)), 8766)
        cfg = json.loads(cfgp.read_text(encoding="utf-8"))
        self.assertTrue(cfg.get("peer_key"))
        self.assertNotIn(cfg["peer_key"], (HK, AK))
        self.assertEqual((cfg["human_key"], cfg["ai_key"]), (HK, AK))
        self.assertNotIn(cfg["peer_key"], output)


if __name__ == "__main__":
    unittest.main()
