"""Mod falso contra el Bridge real: BR3, BR5-BR12, BR18-BR20, BR22 y BR23 (§7).

Constantes cortas y reloj real (monotonico) compartido por Backend y peers;
el barrido se llama a mano (enable_sweeper=False).
"""
import io
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from app.backend.server import Backend
from app.backend.store import Store
from app.tests.fake_mod import FakeMod, _Entry, valid_ack_response, valid_hello_response, valid_poll_response

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
HK = "clave-persona-fake-1234567890"
AK = "clave-ia-fake-0987654321"
PK = "clave-peer-fake-abcdef1234567890"
REG_SHA = "0" * 64


def wait_until(fn, timeout=8.0, step=0.02):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(step)
    return last


class Env:
    def __init__(self, **bridge_kwargs):
        self.dir = tempfile.mkdtemp(prefix="dsbx-fake-")
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)
        self.store = Store(os.path.join(self.dir, "scene.json"), catalog)
        self.log = io.StringIO()
        kw = {"lease_ms": 600, "hold_ms": 150, "retry_ms": 200, "ttl_ms": 4000,
              "read_retry_ms": (50, 100, 200), "enable_sweeper": False}
        kw.update(bridge_kwargs)
        self.backend = Backend(self.store, HK, AK, port=0, log=self.log,
                               clock=time.monotonic, bridge_port=0, peer_key=PK,
                               bridge_kwargs=kw)
        self.bridge = self.backend.bridge
        import threading
        self.thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        try:
            self.backend.shutdown()
        except Exception:
            pass
        try:
            self.thread.join(timeout=5)
        except Exception:
            pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def apply_direct(self):
        snap = self.store.snapshot()
        return self.backend.apply(snap["doc_id"], snap["rev"], snap["hash"])

    def op(self, op_id):
        return self.backend.ops[op_id]

    def events_for(self, op_id):
        out = []
        for _seq, kind, data in list(self.backend.ring):
            if kind != "op.state":
                continue
            d = json.loads(data)
            if d.get("op_id") == op_id:
                out.append(d)
        return out


class FakeBase(unittest.TestCase):
    def make_env(self, **kw):
        env = Env(**kw)
        self.addCleanup(self._close_env, env)
        return env

    def _close_env(self, env):
        env.close()
        text = env.log.getvalue()
        for secret in (PK, HK, AK):
            self.assertNotIn(secret, text)

    def start_fake(self, env, **kw):
        args = {"maintenance_ms": 20, "result_retry_ms": (30, 60, 90)}
        args.update(kw)
        fake = FakeMod("http://127.0.0.1:%d" % env.bridge.port, PK, **args)
        self.addCleanup(fake.close)
        self.assertTrue(fake.wait_ready(timeout=10), "el mod falso no reconcilio")
        self.assertTrue(env.bridge.reconciled)
        return fake

    def wait_past_ttl(self, env, op_id, extra=0.05, timeout=5.0):
        """Espera a que el bridge vea vencida la orden: su TTL contado desde enqueued_mono y con
        su propio reloj, como sweep(). Un t0 tomado antes de encolar se queda corto con carga."""
        order = env.bridge.orders[(env.bridge.session, op_id)]
        limit = order["enqueued_mono"] + order["ttl_ms"] / 1000.0 + extra
        self.assertTrue(wait_until(lambda: env.bridge._now() > limit, timeout))

    def wait_sent(self, fake, pred, timeout=5.0):
        """El bridge cambia el estado dentro del POST del resultado y el mod falso anota el cuerpo
        al volver el POST: con carga, el estado puede verse antes que sent_results."""
        self.assertTrue(wait_until(lambda: any(pred(b) for b in fake.server.sent_results), timeout),
                        "el resultado esperado no aparece en sent_results")

    def peer_snapshot(self, fake, op_id):
        """Estado del peer servidor para el mensaje de un fallo: entradas de op_id, sesion y envios."""
        s = fake.server
        with s._lock:
            ents = [(e.state, e.pending, e.attempts) for e in s.cache.values() if e.order["op_id"] == op_id]
            n_pending = len(s._pending)
        return "entradas=%r session=%s pendientes=%d" % (ents, "si" if s.session else "no", n_pending)

    def wait_state(self, env, op_id, state, timeout=8.0):
        ok = wait_until(lambda: env.op(op_id)["state"] == state, timeout)
        self.assertTrue(ok, "op %s no llego a %s (esta %s)" % (op_id, state, env.op(op_id)))
        return env.op(op_id)


class BR3D2(FakeBase):
    def test_apply_hasta_observado_con_eventos_en_orden(self):
        env = self.make_env()
        fake = self.start_fake(env)
        r = env.apply_direct()
        op_id = r["op_id"]
        self.wait_state(env, op_id, "observado")
        ev = env.events_for(op_id)
        self.assertEqual([(e["state"], e["origin"]) for e in ev],
                         [("pendiente", "backend"), ("ejecutando", "backend"),
                          ("aplicado", "servidor"), ("observado", "servidor")])
        self.assertEqual(ev[1].get("reason"), "entregada")
        self.assertIn(op_id, env.backend.op_mono)
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 1})
        self.assertIsNotNone(env.bridge.catalog)
        self.assertEqual(env.bridge.catalog["n_classes"], 2)

    def test_predicado_que_no_cumple_fallido_nunca_observado(self):
        env = self.make_env()
        fake = self.start_fake(env)
        fake.server.annotate_rev_delta = 3
        r = env.apply_direct()
        op = self.wait_state(env, r["op_id"], "fallido")
        self.assertEqual(op["reason"], "lectura_no_cumple")
        self.assertNotIn("observado", [e["state"] for e in env.events_for(r["op_id"])])


class BR5ResultadoPerdido(FakeBase):
    def test_resultado_perdido_reentrega_dup_y_observado(self):
        env = self.make_env(retry_ms=700)
        fake = self.start_fake(env)
        fake.server.drop_all_results = True
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "anotar") == 1))
        # los 4 intentos caen sin transmitirse
        self.assertTrue(wait_until(
            lambda: any(e.order["op_id"] == op_id and e.state == "terminada" and not e.pending
                        for e in fake.server.cache.values())))
        fake.server.drop_all_results = False
        self.wait_state(env, op_id, "observado")
        self.wait_sent(fake, lambda b: b["op_id"] == op_id and b["dup"] is True)
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 1})

    def test_reentrega_tras_plazo_devuelve_dup_sin_efecto(self):
        # X3 (m): la deduplicacion va antes que el plazo
        env = self.make_env(ttl_ms=900, retry_ms=5000)
        fake = self.start_fake(env)
        fake.server.drop_all_results = True
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "anotar") == 1))
        self.assertTrue(wait_until(
            lambda: any(e.order["op_id"] == op_id and e.state == "terminada" and not e.pending
                        for e in fake.server.cache.values())))
        order = [o for o in fake.server.received_orders if o["op_id"] == op_id][-1]
        entry = [e for e in fake.server.cache.values() if e.order["op_id"] == op_id][0]
        # pasada la ventana de ejecucion pero dentro de la retencion
        self.assertTrue(wait_until(lambda: time.monotonic() > entry.plazo_local, 5))
        self.assertLess(time.monotonic(), entry.retention_until)
        fake.server.drop_all_results = False
        self.assertEqual(fake.server.handle_order(
            order, t_send=time.monotonic(), t_recv=time.monotonic(),
            now_ms=order["issued_ms"] + order["ttl_ms"] + 100), "dup")
        self.wait_state(env, op_id, "observado")
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 1})

    def test_acuse_perdido_resultado_repetido_sin_segundo_evento(self):
        env = self.make_env()
        fake = self.start_fake(env)
        fake.lose_next_ack("server")
        r = env.apply_direct()
        op_id = r["op_id"]
        self.wait_state(env, op_id, "observado")
        self.assertTrue(wait_until(
            lambda: len([b for b in fake.server.sent_results if b["op_id"] == op_id]) >= 2, 15),
            [b for b in fake.server.sent_results if b["op_id"] == op_id])
        seq = env.backend.seq
        time.sleep(0.4)
        self.assertEqual(env.backend.seq, seq)
        self.assertEqual(env.op(op_id)["state"], "observado")


class BR6PeerRecreado(FakeBase):
    def test_recreado_tras_los_dos_pasos_reconcilia(self):
        env = self.make_env()
        fake = self.start_fake(env)
        fake.server.drop_all_results = True
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "anotar") == 1))
        old_inst = fake.server.inst
        fake.restart_peer("server")
        self.assertNotEqual(fake.server.inst, old_inst)
        op = self.wait_state(env, op_id, "observado")
        self.assertEqual(op["reason"], "reconciliada")
        pairs = [(e["state"], e.get("reason")) for e in env.events_for(op_id)]
        self.assertIn(("parcial", "conexion_perdida"), pairs)
        self.assertIn(("observado", "reconciliada"), pairs)
        self.assertLess(pairs.index(("parcial", "conexion_perdida")),
                        pairs.index(("observado", "reconciliada")))
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 1})

    def test_recreado_entre_pasos_se_queda_parcial(self):
        env = self.make_env(ttl_ms=8000)
        fake = self.start_fake(env)
        fake.server.work_between_ms = 1500
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "retirar") == 1))
        fake.restart_peer("server")
        op = self.wait_state(env, op_id, "parcial")
        self.assertEqual(op["reason"], "conexion_perdida")
        self.assertTrue(wait_until(lambda: env.bridge.reconciled))
        time.sleep(0.4)
        self.assertEqual(env.op(op_id)["state"], "parcial")
        self.assertEqual(fake.effect_count(op_id, "anotar"), 0)


class BR7H1(FakeBase):
    def test_backend_reiniciado_op1_se_ejecuta_otra_vez_sin_dup(self):
        env1 = self.make_env()
        fake = self.start_fake(env1, retention_extra_ms=60000)
        r1 = env1.apply_direct()
        self.wait_state(env1, r1["op_id"], "observado")
        s1 = env1.bridge.session
        env1.close()
        env2 = self.make_env()
        s2 = env2.bridge.session
        self.assertNotEqual(s1, s2)
        fake.reconnect("http://127.0.0.1:%d" % env2.bridge.port)
        self.assertTrue(wait_until(lambda: env2.bridge.reconciled, 10))
        r2 = env2.apply_direct()
        self.assertEqual(r2["op_id"], "op-1")
        self.wait_state(env2, r2["op_id"], "observado")
        self.assertEqual(fake.effects_for("op-1", session=s2), {"retirar": 1, "anotar": 1})
        self.wait_sent(fake, lambda b: b["op_id"] == "op-1" and b["session"] == s2)
        sent = [b for b in fake.server.sent_results
                if b["op_id"] == "op-1" and b["session"] == s2]
        self.assertTrue(sent and sent[0]["dup"] is False, sent)


class BR8Cache(FakeBase):
    def test_1025_caducadas_quedan_las_ultimas_1024_en_orden(self):
        env = self.make_env()
        fake = self.start_fake(env)
        from app.tests.fake_mod import _Peer
        peer = _Peer(fake, "server", fake.epoch)
        result = {"status": "done", "reason": None, "read": {}}
        future = time.monotonic() + 10000
        for i in range(1, 1025):
            order = {"session": "a" * 16, "op_id": "op-%d" % i, "conn": 1,
                     "epoch": fake.epoch, "inst": peer.inst, "verb": "scene.apply",
                     "args": {"rev": 1, "hash": "b" * 64}, "issued_ms": 0, "ttl_ms": 1000}
            peer.remember_completed(order, result, future)
        self.assertEqual(len(peer.cache_keys()), 1024)
        with peer._lock:
            for e in peer.cache.values():
                e.retention_until = 0.0
        order = {"session": "a" * 16, "op_id": "op-1025", "conn": 1,
                 "epoch": fake.epoch, "inst": peer.inst, "verb": "scene.apply",
                 "args": {"rev": 1, "hash": "b" * 64}, "issued_ms": 0, "ttl_ms": 1000}
        peer.remember_completed(order, result, future)
        keys = peer.cache_keys()
        self.assertEqual(keys, [("a" * 16, "op-%d" % i) for i in range(2, 1026)])

    def test_cache_llena_de_vivas_contrapresion_y_reconcilia(self):
        # Escenario BR8/B4-01 escalado: capacidad 1, TTL 2 s, poll retenido
        # ~1 s, retencion = recepcion + TTL + 0,25 s; backend vence a +2 s.
        # Con el poll retenido ~1 s, retener solo hasta plazo_local (~+0,9 s) o
        # anclar la retencion al envio (~+1,3 s) libera la cache con margen
        # dentro del TTL del backend, y A se reentrega y se repite: X3 (x).
        env = self.make_env(ttl_ms=2000, hold_ms=1500, retry_ms=200, lease_ms=3000)
        fake = self.start_fake(env, cache_capacity=1, retention_extra_ms=250)
        with fake.server._lock:
            fake.server.cache.clear()
        fake.server.drop_all_results = True
        time.sleep(1.0)  # un poll entregador queda retenido en el bridge
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "anotar") == 1, 5))
        delivering = fake.server.delivering_polls
        maint = fake.server.maintenance_polls
        time.sleep(0.9)
        self.assertEqual(fake.server.delivering_polls, delivering,
                         "con la cache viva llena pidio ordenes nuevas")
        self.assertGreater(fake.server.maintenance_polls, maint)
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 1})
        # vence el TTL en el backend: parcial, aun sin pedir ordenes
        self.wait_past_ttl(env, op_id)
        env.bridge.sweep()
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "sin_resultado"))
        fake.server.drop_all_results = False
        op = self.wait_state(env, op_id, "observado", timeout=8)
        self.assertEqual(op["reason"], "reconciliada")
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 1})


    def test_cache_llena_de_vivas_no_expulsa_ni_acepta(self):
        # X3 (p): con la cache llena de entradas vivas no entra ninguna nueva
        env = self.make_env()
        fake = self.start_fake(env)
        from app.tests.fake_mod import _Peer
        peer = _Peer(fake, "server", fake.epoch)
        peer.session = "a" * 16
        peer.conn = 1
        old_cap = fake.cache_capacity
        fake.cache_capacity = 2
        try:
            result = {"status": "done", "reason": None, "read": {}}
            future = time.monotonic() + 10000
            for i in (1, 2):
                order = {"session": "a" * 16, "op_id": "op-%d" % i, "conn": 1,
                         "epoch": fake.epoch, "inst": peer.inst, "verb": "scene.apply",
                         "args": {"rev": 1, "hash": "b" * 64}, "issued_ms": 0, "ttl_ms": 1000}
                peer.remember_completed(order, result, future)
            nueva = {"session": "a" * 16, "op_id": "op-nueva", "conn": 1,
                     "epoch": fake.epoch, "inst": peer.inst, "verb": "scene.apply",
                     "args": {"rev": 1, "hash": "b" * 64}, "issued_ms": 0, "ttl_ms": 1000}
            self.assertEqual(peer.handle_order(nueva, now_ms=0), "cache_llena")
            self.assertEqual(peer.cache_keys(),
                             [("a" * 16, "op-1"), ("a" * 16, "op-2")])
            self.assertEqual(fake.effect_count("op-nueva"), 0)
            # la reentrega de la mas vieja sigue siendo dup y no repite el efecto (BR8)
            vieja = {"session": "a" * 16, "op_id": "op-1", "conn": 1,
                     "epoch": fake.epoch, "inst": peer.inst, "verb": "scene.apply",
                     "args": {"rev": 1, "hash": "b" * 64}, "issued_ms": 0, "ttl_ms": 1000}
            self.assertEqual(peer.handle_order(vieja, now_ms=0), "dup")
            self.assertEqual(fake.effect_count("op-1"), 0)
        finally:
            fake.cache_capacity = old_cap


class BR9H3(FakeBase):
    def test_trabajo_lento_con_mantenimiento_termina_done(self):
        env = self.make_env(ttl_ms=6000)
        fake = self.start_fake(env)
        fake.server.work_between_ms = 1100
        r = env.apply_direct()
        self.wait_state(env, r["op_id"], "observado")

    def test_polls_cortados_antes_del_primer_paso_rejected_lease(self):
        env = self.make_env(ttl_ms=6000)
        fake = self.start_fake(env)
        fake.server.work_before_ms = 1500
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(
            lambda: any(o["op_id"] == op_id for o in fake.server.received_orders), 5))
        fake.cut_polls("server", 2200)
        op = self.wait_state(env, op_id, "fallido")
        self.assertEqual(op["reason"], "lease_expired")
        self.assertEqual(fake.effects_for(op_id), {"retirar": 0, "anotar": 0})

    def test_cliente_tambien_pierde_su_lease(self):
        env = self.make_env()
        fake = self.start_fake(env)
        fake.cut_polls("client", 1600)
        time.sleep(0.8)
        self.assertFalse(fake.client.lease_ok())
        fake.client.clear_poll_cut()


class BR10H5(FakeBase):
    def test_validacion_de_200(self):
        good_hello = {"ok": True, "session": "a" * 16, "conn": 1, "lease_ms": 300,
                      "hold_ms": 200, "wire_cap": 3500}
        self.assertTrue(valid_hello_response(good_hello))
        sin_conn = {k: v for k, v in good_hello.items() if k != "conn"}
        for bad in ({}, {"ok": False, "session": "a" * 16, "conn": 1, "lease_ms": 1, "hold_ms": 1,
                         "wire_cap": 3500},
                    {"session": "a" * 16, "conn": 1, "lease_ms": 1, "hold_ms": 1, "wire_cap": 3500},
                    dict(good_hello, lease_ms=0), dict(good_hello, session="zz"),
                    dict(good_hello, session="a" * 15), dict(good_hello, wire_cap=10),
                    sin_conn, dict(good_hello, conn=0), dict(good_hello, conn="1")):
            self.assertFalse(valid_hello_response(bad), bad)
        good_order = {"op_id": "op-1", "session": "a" * 16, "conn": 1, "epoch": "b" * 32,
                      "inst": "c" * 32, "verb": "scene.apply", "args": {}, "issued_ms": 1, "ttl_ms": 10}
        self.assertTrue(valid_poll_response({"ok": True, "now_ms": 5, "ops": [good_order]}))
        self.assertFalse(valid_poll_response({"ok": True, "ops": []}))
        self.assertFalse(valid_poll_response({"now_ms": 5, "ops": []}))
        self.assertFalse(valid_poll_response({"ok": True, "now_ms": 5, "ops": [good_order, good_order]}))
        self.assertTrue(valid_ack_response({"ok": True}))
        self.assertFalse(valid_ack_response({}))
        self.assertFalse(valid_ack_response({"ok": False}))

    def test_hello_invalido_simulado_no_renueva_y_reintenta(self):
        env = self.make_env()
        fake = self.start_fake(env)
        from app.tests.fake_mod import _Peer
        peer = _Peer(fake, "client", fake.epoch)
        peer.simulate_next_response("hello", {"ok": False})
        self.assertFalse(peer._do_hello())
        self.assertIsNone(peer.session)
        self.assertIsNone(peer.last_valid_poll_mono)
        # sin la simulacion, el mismo peer se presenta de verdad
        self.assertTrue(peer._do_hello())
        # poll sin now_ms: no renueva el lease
        sentinel = time.monotonic() - 5
        peer.last_valid_poll_mono = sentinel
        peer.simulate_next_response("poll", {"ok": True, "ops": []})
        peer._poll_once(True)
        self.assertEqual(peer.last_valid_poll_mono, sentinel)
        # acuse sin ok: el intento cuenta como fallo
        peer.simulate_next_response("ack", {})
        from app.tests.fake_mod import _Entry
        entry = _Entry(("a" * 16, "op-x"), {"op_id": "op-x", "session": peer.session,
                                            "epoch": fake.epoch, "verb": "scene.apply"},
                       time.monotonic() + 10, time.monotonic() + 10)
        entry.result = {"status": "error", "reason": "x", "read": {}}
        self.assertEqual(peer._attempt_result(entry), "fail")

    def test_acuse_invalido_se_reintenta_y_observa(self):
        env = self.make_env()
        fake = self.start_fake(env)
        fake.server.simulate_next_response("ack", {"sin_ok": True})
        r = env.apply_direct()
        self.wait_state(env, r["op_id"], "observado")


class BR11PlazoAlLlegar(FakeBase):
    def test_orden_vencida_al_llegar_rejected_expired(self):
        env = self.make_env(ttl_ms=500)
        fake = self.start_fake(env)
        fake.server.poll_response_delay_ms = 700
        r = env.apply_direct()
        op = self.wait_state(env, r["op_id"], "fallido")
        self.assertEqual(op["reason"], "expired")
        self.assertEqual(fake.effects_for(r["op_id"]), {"retirar": 0, "anotar": 0})


class BR12Mision(FakeBase):
    def test_restart_mission(self):
        env = self.make_env(ttl_ms=8000)
        fake = self.start_fake(env)
        old_epoch = fake.epoch
        fake.server.work_between_ms = 1500
        r1 = env.apply_direct()
        self.assertTrue(wait_until(lambda: fake.effect_count(r1["op_id"], "retirar") == 1))
        r2 = env.apply_direct()
        self.assertEqual(env.op(r2["op_id"])["state"], "pendiente")
        fake.restart_mission()
        self.assertNotEqual(fake.epoch, old_epoch)
        op1 = self.wait_state(env, r1["op_id"], "parcial")
        self.assertEqual(op1["reason"], "mundo_reiniciado")
        op2 = self.wait_state(env, r2["op_id"], "fallido")
        self.assertEqual(op2["reason"], "mundo_reiniciado")
        self.assertTrue(wait_until(lambda: env.bridge.reconciled, 8))
        self.assertEqual(fake.mission_effects, {"retirar": 0, "anotar": 0})
        time.sleep(0.3)
        self.assertEqual(env.op(r1["op_id"])["state"], "parcial")
        fake.server.work_between_ms = 0
        r3 = env.apply_direct()
        self.wait_state(env, r3["op_id"], "observado")
        self.assertEqual(fake.mission_effects, {"retirar": 1, "anotar": 1})

    def test_cliente_con_otro_epoch_fuera_y_orden_stale_epoch(self):
        env = self.make_env()
        fake = self.start_fake(env)
        self.assertTrue(env.bridge.client_in_world())
        fake.restart_peer("client", epoch="f" * 32)
        self.assertTrue(wait_until(lambda: fake.client.session is not None))
        time.sleep(0.2)
        self.assertFalse(env.bridge.client_in_world())
        # orden con epoch viejo: rechazada sin efecto (via directa al manejador)
        srv = fake.server
        order = {"op_id": "op-stale", "session": srv.session, "conn": srv.conn,
                 "epoch": "f" * 32, "inst": srv.inst, "verb": "scene.apply",
                 "args": {"rev": 1, "hash": "b" * 64},
                 "issued_ms": int(time.monotonic() * 1000), "ttl_ms": 4000}
        self.assertEqual(srv.handle_order(order, now_ms=order["issued_ms"]), "rejected")
        entry = [e for e in srv.cache.values() if e.order["op_id"] == "op-stale"][0]
        self.assertEqual(entry.result, {"status": "rejected", "reason": "stale_epoch", "read": {}})
        self.assertEqual(fake.effect_count("op-stale"), 0)


class BR18PlazoDuranteTrabajo(FakeBase):
    def test_vence_antes_del_primer_paso(self):
        env = self.make_env(ttl_ms=800, lease_ms=5000)
        fake = self.start_fake(env)
        fake.server.work_before_ms = 1100
        r = env.apply_direct()
        op = self.wait_state(env, r["op_id"], "fallido")
        self.assertEqual(op["reason"], "expired")
        self.assertEqual(fake.effects_for(r["op_id"]), {"retirar": 0, "anotar": 0})

    def test_vence_entre_pasos_error_y_parcial(self):
        env = self.make_env(ttl_ms=1500, lease_ms=5000)
        fake = self.start_fake(env)
        fake.server.work_between_ms = 2000
        r = env.apply_direct()
        op = self.wait_state(env, r["op_id"], "parcial")
        self.assertEqual(op["reason"], "expired")
        self.assertEqual(fake.effects_for(r["op_id"]), {"retirar": 1, "anotar": 0})

    def test_transito_el_plazo_se_ancla_al_envio(self):
        # X3 (u): respuesta retrasada 1,8 s, TTL 3 s, trabajo entre pasos 1,4 s. BR18 exige que ningun
        # efecto ocurra despues del TTL del backend. Con el plazo anclado al envio del poll, el paso 2
        # nunca llega: la orden acaba parcial/expired tras el paso 1 o, si la maquina va tan cargada que
        # la respuesta tarda mas de ~1,1 s, fallido/expired sin ningun efecto, que tambien cumple el
        # contrato. Con el plazo anclado a la recepcion, el paso 2 cae dentro de ese plazo falso y la
        # orden llega a observado con anotar = 1.
        env = self.make_env(ttl_ms=3000, lease_ms=8000)
        fake = self.start_fake(env)
        fake.server.poll_response_delay_ms = 1800
        fake.server.work_between_ms = 1400
        r = env.apply_direct()
        op_id = r["op_id"]
        acabada = wait_until(
            lambda: env.op(op_id)["state"] in ("parcial", "fallido", "aplicado", "observado"), 10)
        op = env.op(op_id)
        self.assertTrue(acabada, op)
        self.assertIn((op["state"], op["reason"]), (("parcial", "expired"), ("fallido", "expired")), op)
        efectos = fake.effects_for(op_id)
        self.assertEqual(efectos["anotar"], 0)
        self.assertEqual(efectos["retirar"], 1 if op["state"] == "parcial" else 0)


class BR19UnaEnCurso(FakeBase):
    def test_doble_entrega_y_sin_poll_entregador_mientras_ejecuta(self):
        env = self.make_env(ttl_ms=8000)
        fake = self.start_fake(env)
        fake.server.work_between_ms = 1500
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "retirar") == 1))
        order = [o for o in fake.server.received_orders if o["op_id"] == op_id][-1]
        self.assertEqual(fake.force_double_delivery(order), ("en_curso", "en_curso"))
        delivering = fake.server.delivering_polls
        maint = fake.server.maintenance_polls
        time.sleep(0.35)
        self.assertEqual(fake.server.delivering_polls, delivering)
        self.assertGreater(fake.server.maintenance_polls, maint)
        self.wait_state(env, op_id, "observado")
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 1})


class BR20LeaseTrasEfecto(FakeBase):
    def test_polls_cortados_tras_primer_paso_error_parcial(self):
        env = self.make_env(ttl_ms=8000)
        fake = self.start_fake(env)
        fake.server.work_between_ms = 1300
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "retirar") == 1))
        fake.cut_polls("server", 1800)
        op = self.wait_state(env, op_id, "parcial")
        self.assertEqual(op["reason"], "lease_expired")
        self.assertEqual(fake.effects_for(op_id), {"retirar": 1, "anotar": 0})


class BR22ConfirmacionTardia(FakeBase):
    def _parcial_sin_resultado(self, env, fake, op_id):
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "anotar") == 1, 5))
        self.assertTrue(wait_until(
            lambda: any(e.order["op_id"] == op_id and e.state == "terminada" and not e.pending
                        for e in fake.server.cache.values()), 5))
        self.wait_past_ttl(env, op_id)
        env.bridge.sweep()
        self.assertEqual(env.op(op_id)["state"], "parcial")
        self.assertEqual(env.op(op_id)["reason"], "sin_resultado")

    def test_done_tardio_aplicado_observado_y_repetido_nada(self):
        env = self.make_env(ttl_ms=1000, retry_ms=10000)
        fake = self.start_fake(env)
        fake.set_state_read_mode("error")
        fake.server.drop_all_results = True
        r = env.apply_direct()
        op_id = r["op_id"]
        self._parcial_sin_resultado(env, fake, op_id)
        fake.server.drop_all_results = False
        self.assertTrue(fake.resend_cached_result(op_id))
        self.wait_state(env, op_id, "observado")
        states = [e["state"] for e in env.events_for(op_id)]
        self.assertEqual(states[-2:], ["aplicado", "observado"])
        # repetido: nada cambia
        self.assertTrue(fake.resend_cached_result(op_id))
        self.assertTrue(wait_until(
            lambda: len([b for b in fake.server.sent_results if b["op_id"] == op_id]) >= 2, 15))
        seq = env.backend.seq
        time.sleep(0.35)
        self.assertEqual(env.backend.seq, seq)

    def test_rejected_tardio_fallido(self):
        env = self.make_env(ttl_ms=700, retry_ms=10000, lease_ms=5000)
        fake = self.start_fake(env)
        fake.set_state_read_mode("error")
        fake.server.drop_all_results = True
        fake.server.poll_response_delay_ms = 900
        r = env.apply_direct()
        op_id = r["op_id"]
        # la orden llega vencida: rejected/expired en cache, sin transmitir. Con la maquina muy
        # cargada los hilos del mod falso pueden quedarse segundos sin CPU: esperas de 15 s.
        self.assertTrue(wait_until(
            lambda: any(e.order["op_id"] == op_id and e.state == "terminada" and not e.pending
                        for e in fake.server.cache.values()), 15),
            self.peer_snapshot(fake, op_id))
        self.wait_past_ttl(env, op_id, timeout=15)
        env.bridge.sweep()
        self.assertEqual(env.op(op_id)["state"], "parcial", self.peer_snapshot(fake, op_id))
        fake.server.drop_all_results = False
        fake.server.poll_response_delay_ms = 0
        self.assertTrue(fake.resend_cached_result(op_id))
        op = self.wait_state(env, op_id, "fallido", timeout=15)
        self.assertEqual(op["reason"], "expired")

    def test_error_tardio_sigue_parcial_con_motivo_nuevo(self):
        env = self.make_env(ttl_ms=900, retry_ms=10000, lease_ms=5000)
        fake = self.start_fake(env)
        fake.set_state_read_mode("error")
        fake.server.drop_all_results = True
        fake.server.work_between_ms = 1100
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(
            lambda: any(e.order["op_id"] == op_id and e.state == "terminada" and not e.pending
                        and e.result and e.result["status"] == "error"
                        for e in fake.server.cache.values()), 6))
        self.wait_past_ttl(env, op_id)
        env.bridge.sweep()
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "sin_resultado"))
        seq = env.backend.seq
        fake.server.drop_all_results = False
        self.assertTrue(fake.resend_cached_result(op_id))
        self.assertTrue(wait_until(lambda: env.backend.seq > seq, 5))
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "expired"))


class BR23ReconciliacionPredicado(FakeBase):
    def test_generacion_con_otra_rev_fallido_por_lectura(self):
        env = self.make_env(ttl_ms=1000, retry_ms=10000)
        fake = self.start_fake(env)
        fake.server.annotate_rev_delta = 8
        fake.server.drop_all_results = True
        r = env.apply_direct()
        op_id = r["op_id"]
        self.assertTrue(wait_until(lambda: fake.effect_count(op_id, "anotar") == 1, 5))
        # los 4 intentos caen sin transmitirse antes de abrir los envios
        self.assertTrue(wait_until(
            lambda: any(e.order["op_id"] == op_id and e.state == "terminada" and not e.pending
                        for e in fake.server.cache.values()), 5))
        self.wait_past_ttl(env, op_id)
        fake.server.drop_all_results = False
        env.bridge.sweep()
        self.assertEqual(env.op(op_id)["state"], "parcial")
        op = self.wait_state(env, op_id, "fallido")
        self.assertEqual(op["reason"], "lectura_no_cumple")
        self.assertNotIn("observado", [e["state"] for e in env.events_for(op_id)])


class BR9MantenimientoDuranteAcuse(FakeBase):
    def test_acuse_lento_mantiene_polls_y_ejecuta_siguiente(self):
        env = self.make_env()
        fake = self.start_fake(env)
        fake.server.ack_delay_ms = 1500
        a = env.apply_direct()
        b = env.apply_direct()
        self.wait_state(env, a["op_id"], "observado")
        maint_antes = fake.server.maintenance_polls
        self.assertTrue(wait_until(lambda: fake.server.maintenance_polls > maint_antes, 1.2))
        self.wait_state(env, b["op_id"], "observado")
        self.assertNotIn("fallido", [e["state"] for e in env.events_for(b["op_id"])])


class MotorCortaCadenas(FakeBase):
    """El mod falso lee las respuestas cortando cada cadena a 1023 bytes, como el motor."""

    def test_cut_engine_strings(self):
        from app.tests.fake_mod import cut_engine_strings
        obj = {"a": "x" * 3037, "b": ["y" * 5, {"c": "ñ" * 600}], "n": 7}
        cortado = cut_engine_strings(obj)
        self.assertEqual(len(cortado["a"]), 1023)
        self.assertEqual(cortado["b"][0], "y" * 5)
        self.assertLessEqual(len(cortado["b"][1]["c"].encode("utf-8")), 1023)
        self.assertEqual(cortado["n"], 7)

    def test_el_peer_lee_cortada_una_cadena_larga_de_una_orden(self):
        # Sin la guarda del bridge (STR_CAP subido a mano), una orden con una cadena de 2000 bytes
        # llega al peer cortada a 1023, que es lo que veria el mod real.
        from app.backend import bridge as bridge_mod
        env = self.make_env()
        fake = self.start_fake(env)
        tope = bridge_mod.STR_CAP
        bridge_mod.STR_CAP = 10 ** 6
        try:
            ok, order = env.bridge.enqueue_order("state.read", {"pad": "x" * 2000}, internal=True)
        finally:
            bridge_mod.STR_CAP = tope
        self.assertTrue(ok)
        recibidas = lambda: [o for o in fake.server.received_orders if o["op_id"] == order["op_id"]]
        self.assertTrue(wait_until(lambda: bool(recibidas()), 8))
        self.assertEqual(len(recibidas()[0]["args"]["pad"]), 1023)


class ReintentoSinVer409(FakeBase):
    """D1 (brief de F1b-peers §3.4): el peer de Enforce no ve el 409 unknown_op y lo reintenta
    como cualquier fallo. El backend contesta igual a cada intento y no cambia nada."""

    def _intentos_con_unknown(self, retry_unknown):
        env = self.make_env()
        fake = self.start_fake(env, r_retry_unknown=retry_unknown)
        peer = fake.server
        order = {"op_id": "op-no-existe", "session": peer.session, "epoch": peer.epoch,
                 "verb": "state.read", "args": {}}
        entry = _Entry(peer.session + "|op-no-existe", order, 0.0, 0.0)
        entry.state = "terminada"
        entry.result = {"status": "rejected", "reason": "stale_conn", "read": {}}
        foto = {k: (v["bstate"], v["result_seen"]) for k, v in env.bridge.orders.items()}
        n0 = len(peer.sent_results)
        with peer._lock:
            entry.pending = True
            peer._pending.append(entry)
        self.assertTrue(wait_until(lambda: not entry.pending, 8), "el envio no se abandono")
        self.assertNotIn(entry, peer._pending)
        self.assertEqual({k: (v["bstate"], v["result_seen"]) for k, v in env.bridge.orders.items()}, foto)
        return len(peer.sent_results) - n0

    def test_con_el_409_visible_se_abandona_al_primero(self):
        self.assertEqual(self._intentos_con_unknown(False), 1)

    def test_sin_ver_el_409_se_abandona_al_cuarto_sin_cambiar_el_backend(self):
        self.assertEqual(self._intentos_con_unknown(True), 4)


if __name__ == "__main__":
    unittest.main()
