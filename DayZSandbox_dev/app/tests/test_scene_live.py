"""F2-offline §4.2-§4.5: SceneLive con llamadas directas sobre un Backend con Bridge real.

El Bridge escucha en 127.0.0.1:0. No hay ganchos de F2-3: las presentaciones se
hacen con `Bridge.handle_hello`, la capacidad `scene` se emula como la guardara
`handle_hello` (A10) y los resultados y lecturas se pasan a mano a
`SceneLive.on_result_locked` / `on_world_read_locked` bajo `bridge.cond`.
"""
import copy
import io
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.backend.scene_live import SceneLive
from app.backend.server import Backend
from app.backend.store import Store

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
HK = "clave-persona-scene-live-1234567"
AK = "clave-ia-scene-live-7654321"
PK = "clave-peer-scene-live-abcdef12345"
REG_SHA = "0" * 64


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class LiveEnv:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="dsbx-scene-live-")
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            self.library = json.load(f)
        self.store = Store(os.path.join(self.dir, "scene.json"), self.library)
        self.log = io.StringIO()
        self.clock = FakeClock()
        kw = {"lease_ms": 300, "hold_ms": 200, "retry_ms": 150, "ttl_ms": 5000,
              "read_retry_ms": (50, 100, 200), "enable_sweeper": False}
        self.backend = Backend(self.store, HK, AK, port=0, log=self.log, clock=self.clock,
                               bridge_port=0, peer_key=PK, bridge_kwargs=kw)
        self.bridge = self.backend.bridge
        self.live = SceneLive(self.bridge)
        self.thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.thread.start()
        self._closed = False
        self.world_classes = set()
        for kind, classes in self.library["classes"].items():
            self.world_classes.update(classes)
        snap = self.store.snapshot()
        self.rev = snap["rev"]
        self.hash = snap["hash"]
        self.doc_id = snap["doc_id"]
        self.doc = copy.deepcopy(snap["doc"])
        self.doc["entities"] = [e for e in self.doc["entities"] if e.get("kind") != "actor"]

    def close(self):
        if not self._closed:
            self._closed = True
            self.backend.shutdown()
            self.thread.join(timeout=5)
        shutil.rmtree(self.dir, ignore_errors=True)

    # --- cola y presentaciones -------------------------------------------

    def _clear_state_reads(self):
        for o in self.bridge.orders.values():
            if o["verb"] == "state.read" and o["bstate"] in ("pendiente", "ejecutando"):
                o["bstate"] = "terminal"
                o["result_seen"] = True

    def hello(self, inst=None, epoch=None, scene=1, world_size=15360, build="retail"):
        inst = inst or self._inst()
        epoch = epoch or self._epoch()
        body = {"proto": "dsbx1", "peer": "server", "inst": inst, "epoch": epoch,
                "mod_ver": "test-1", "build": build, "map": "chernarus",
                "world_size": world_size, "modset": [], "actor_engine": "none"}
        st, resp = self.bridge.handle_hello(body)
        assert st == 200, resp
        srv = self.bridge.peers["server"]
        if scene is not None:
            # A10/F2-3: handle_hello guarda la capacidad en el registro del peer.
            srv["scene"] = scene
        self.live.on_server_hello_locked(srv)
        self._clear_state_reads()
        return inst, epoch

    _inst_counter = 0
    _epoch_counter = 0

    def _inst(self):
        LiveEnv._inst_counter += 1
        return ("%032x" % LiveEnv._inst_counter)

    def _epoch(self):
        LiveEnv._epoch_counter += 1
        return ("%032x" % LiveEnv._epoch_counter)

    def catalog(self, inst=None, build="texto-libre-del-catalogo"):
        srv = self.bridge.peers.get("server") or {}
        inst = inst or srv.get("inst")
        classes = sorted(self.world_classes)
        self.bridge.catalog = {
            "catalog_id": "a" * 16, "build": build, "modset_hash": "c" * 64,
            "n_classes": len(classes), "sha256": "d" * 64,
            "classes": [[c, "mod"] for c in classes],
        }
        return self.live.on_catalog_complete_locked(inst, build)

    # --- preparacion ------------------------------------------------------

    def prepare(self, doc=None, rev=None, hash_=None):
        return self.live.prepare_apply_locked(
            doc if doc is not None else self.doc,
            self.rev if rev is None else rev,
            self.hash if hash_ is None else hash_,
        )

    def apply(self, doc=None, op_id="op-1"):
        res = self.prepare(doc)
        assert res.get("ok") is True, res
        ok, order = self.live.enqueue_apply_locked(op_id, res["plan"], res["expectation"])
        assert ok is True, order
        return res, order

    def deliver(self, order):
        srv = self.bridge.peers["server"]
        order["bstate"] = "ejecutando"
        order["delivered_inst"] = srv["inst"]
        order["conn"] = srv["conn"]
        if not order.get("internal"):
            self.backend.set_op_state(order["op_id"], "ejecutando", "backend", "entregada")

    # --- lecturas ---------------------------------------------------------

    def apply_gen(self, order):
        args = order["args"]
        return {"session": order["session"], "op_id": order["op_id"], "rev": args["rev"],
                "hash": args["hash"], "plan_sha256": args["plan_sha256"]}

    def ckpt_rows(self, order, y=0):
        # v1.3 §3.6: filas de checkpoint en enteros (mm y milesimas de grado)
        rows = []
        args = order["args"]
        for lid, ci, x, z, yaw in zip(args["lid"], args["ci"], args["x_mm"],
                                      args["z_mm"], args["yaw_mdeg"]):
            rows.append([lid, ci, x, y, z, yaw, y])
        return rows

    def scene_read(self, epoch, doc_id=None, generation=None, pending=None, last=None,
                   n=0, retained_n=0, retained=None, gen_n=1):
        return {
            "epoch": epoch,
            "generation": generation,
            "registry_n": 0,
            "registry_sha256": REG_SHA,
            "scene": {
                "doc_id": doc_id or self.doc_id,
                "gen_n": gen_n,
                "n": n,
                "retained_n": retained_n,
                "retained": [] if retained is None else retained,
                "pending": pending,
                "last": last,
            },
        }

    def apply_read(self, order, generation="auto", pending=None, last="auto", n="auto",
                   retained_n=0, retained=None, rows=None):
        if generation == "auto":
            generation = self.apply_gen(order)
        if last == "auto":
            last = {"session": order["session"], "op_id": order["op_id"],
                    "verb": "scene.apply", "outcome": "done"}
        if n == "auto":
            n = len(order["args"]["lid"])
        read = self.scene_read(order["epoch"], order["args"]["doc_id"], generation, pending,
                               last, n, retained_n, retained)
        read["obs"] = {"at": "checkpoint",
                       "rows": self.ckpt_rows(order) if rows is None else rows}
        return read

    def reset_read(self, order, outcome="done", n=0, retained_n=0, retained=None,
                   generation=None, pending=None, last="auto", gen_n=1):
        if last == "auto":
            last = {"session": order["session"], "op_id": order["op_id"],
                    "verb": "scene.reset", "outcome": outcome}
        return self.scene_read(order["epoch"], order["args"]["doc_id"], generation, pending,
                               last, n, retained_n, retained, gen_n)

    def now_read(self, order, rows):
        read = self.scene_read(order["epoch"], order["args"]["doc_id"], None, None, None, 0)
        read["obs"] = {"at": "now", "rows": rows}
        return read

    def world_read(self, epoch, generation=None):
        return {"epoch": epoch, "generation": generation, "registry_n": 0,
                "registry_sha256": REG_SHA}

    # --- llamadas directas a SceneLive -----------------------------------

    def send(self, order, status="done", reason=None, read=None):
        with self.bridge.cond:
            return self.live.on_result_locked(order, status, reason, read)

    def world(self, read):
        with self.bridge.cond:
            self.live.on_world_read_locked(read)

    # --- consultas --------------------------------------------------------

    def orders(self, verb=None, internal=None):
        out = []
        for o in self.bridge.orders.values():
            if verb is not None and o["verb"] != verb:
                continue
            if internal is not None and bool(o.get("internal")) is not internal:
                continue
            out.append(o)
        return out

    def op_events(self):
        out = []
        for _seq, kind, data in self.backend.ring:
            if kind == "op.state":
                out.append(json.loads(data))
        return out

    def op_states(self, op_id):
        return [e["state"] for e in self.op_events() if e["op_id"] == op_id]

    def f2_internals(self):
        return [o for o in self.bridge.orders.values()
                if o.get("internal") and self.live.is_f2_order(o)]


class SceneLiveBase(unittest.TestCase):
    def make_env(self):
        env = LiveEnv()
        self.addCleanup(self._close_env, env)
        return env

    def _close_env(self, env):
        env.close()
        for text in [env.log.getvalue()] + [str(o) for o in env.op_events()]:
            self.assertNotIn(PK, text)

    def ready(self):
        env = self.make_env()
        inst, epoch = env.hello()
        self.assertTrue(env.catalog(inst))
        return env

    def partial_apply(self, env, op_id="op-1", reason="sin_resultado"):
        _res, order = env.apply(op_id=op_id)
        env.deliver(order)
        with env.bridge.cond:
            env.backend.set_op_state(op_id, "parcial", "backend", reason)
            order["bstate"] = "parcial"
        return order

    def compensation(self, env):
        found = [o for o in env.f2_internals() if o.get("purpose") == "compensate"]
        return found[0] if found else None


class CatalogD4(SceneLiveBase):
    def test_catalogo_tras_hello_vigente_es_valido(self):
        env = self.ready()
        self.assertTrue(env.live.catalog_ok_locked())
        res = env.prepare()
        self.assertTrue(res["ok"], res)
        self.assertEqual(len(res["plan"]["lid"]), 33)
        self.assertEqual(len(res["plan"]["classes"]), len(set(res["plan"]["classes"])))
        self.assertRegex(res["plan"]["plan_sha256"], r"^[0-9a-f]{64}$")

    def test_catalogo_de_otra_inst_es_catalog_pending(self):
        env = self.ready()
        inst1 = env.bridge.peers["server"]["inst"]
        inst2, _ = env.hello()
        before = len(env.orders())
        res = env.prepare()
        self.assertEqual((res["ok"], res["code"], res["http"]), (False, "catalog_pending", 409))
        self.assertEqual(res["pointer"], "")
        self.assertEqual(len(env.orders()), before)
        self.assertFalse(env.catalog(inst1))
        self.assertFalse(env.prepare()["ok"])
        self.assertTrue(env.catalog(inst2))
        self.assertTrue(env.prepare()["ok"])

    def test_build_y_conn_ligan_el_catalogo_por_inst(self):
        # A1: la build del catalogo no se compara con la del hello.
        env = self.ready()
        self.assertNotEqual(env.bridge.peers["server"]["build"],
                            env.bridge.catalog["build"])
        self.assertTrue(env.live.catalog_ok_locked())
        # Un hello nuevo del mismo inst invalida hasta completar otra vez.
        inst = env.bridge.peers["server"]["inst"]
        env.hello(inst=inst)
        self.assertFalse(env.live.catalog_ok_locked())
        self.assertTrue(env.catalog(inst, build="otra-build"))
        self.assertTrue(env.live.catalog_ok_locked())

    def test_c03_paginas_de_presentaciones_distintas_no_certifican(self):
        # A manda la pagina 1/2; B se presenta y manda solo la 2/2 con el mismo
        # catalog_id, build y modset_hash. Sin el arreglo, el intento de A se
        # reutiliza y responde complete=true con clases que B nunca envio.
        env = self.make_env()
        inst_a, _epoch = env.hello()
        catalog_id = "a" * 16
        modset_hash = "c" * 64
        body1 = {"catalog_id": catalog_id, "page": 1, "pages": 2,
                 "build": "fake-1", "modset_hash": modset_hash,
                 "classes": [["ClaseA", "BaseA"]]}
        query_a = {"peer": "server", "inst": inst_a, "session": env.bridge.session}
        st, resp = env.bridge.handle_catalog(query_a, body1)
        self.assertEqual(st, 200, resp)
        self.assertFalse(resp.get("complete"))

        inst_b, _ = env.hello()
        self.assertNotEqual(inst_b, inst_a)
        body2 = {"catalog_id": catalog_id, "page": 2, "pages": 2,
                 "build": "fake-1", "modset_hash": modset_hash,
                 "classes": [["ClaseB", "BaseB"]]}
        query_b = {"peer": "server", "inst": inst_b, "session": env.bridge.session}
        st, resp = env.bridge.handle_catalog(query_b, body2)
        self.assertEqual(st, 200, resp)
        self.assertFalse(resp.get("complete"))
        self.assertEqual((resp.get("have"), resp.get("pages")), (1, 2))
        self.assertFalse(env.live.catalog_ok_locked())

class ApplyDirecto(SceneLiveBase):
    def test_rev_de_nueve_digitos_vale_a2(self):
        env = self.ready()
        _res, order = env.apply()
        read = env.apply_read(order)
        read["generation"]["rev"] = 1234567
        self.assertTrue(env.live.valid_read(order, read))
        read["generation"]["rev"] = 1234567890  # 10 digitos
        self.assertFalse(env.live.valid_read(order, read))

    def test_error_de_prepare_no_crea_orden_ni_evento(self):
        env = self.make_env()
        env.hello()
        before_events = len(env.backend.ring)
        before_orders = len(env.orders())
        res = env.prepare()
        self.assertEqual(res["code"], "catalog_pending")
        self.assertEqual(len(env.backend.ring), before_events)
        self.assertEqual(len(env.orders()), before_orders)

    def test_encola_con_args_de_la_orden_y_fila_sin_verb(self):
        env = self.ready()
        res, order = env.apply()
        self.assertEqual(order["verb"], "scene.apply")
        self.assertTrue(order["f2"])
        self.assertEqual(order["args"], res["plan"])
        self.assertNotIn("verb", env.backend.ops["op-1"])
        events = env.op_events()
        self.assertEqual(events[-1]["op_id"], "op-1")
        self.assertEqual(events[-1]["state"], "pendiente")
        self.assertNotIn("verb", events[-1])

    def test_done_bueno_observado(self):
        env = self.ready()
        _res, order = env.apply()
        env.deliver(order)
        self.assertIs(env.send(order, "done", None, env.apply_read(order)), True)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"], op["origin"]), ("observado", None, "servidor"))
        self.assertEqual(env.op_states("op-1"), ["pendiente", "ejecutando", "aplicado", "observado"])
        self.assertFalse(order["result_seen"])  # A10: lo marca handle_result

    def test_done_malo_fallido(self):
        env = self.ready()
        _res, order = env.apply()
        env.deliver(order)
        rows = env.ckpt_rows(order)
        rows[0][2] = rows[0][2] + 1000
        env.send(order, "done", None, env.apply_read(order, rows=rows))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))

    def test_rejected_fallido_sin_tocar_lectura(self):
        env = self.ready()
        _res, order = env.apply()
        env.deliver(order)
        read = env.apply_read(order)
        frozen = copy.deepcopy(read)
        env.send(order, "rejected", "bad_plan", read)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "bad_plan"))
        self.assertEqual(read, frozen)  # A14
        self.assertEqual(order["bstate"], "terminal")

    def test_error_parcial_y_pide_state_read(self):
        env = self.ready()
        _res, order = env.apply()
        env.deliver(order)
        self.assertEqual([o for o in env.orders("state.read")
                          if o["bstate"] in ("pendiente", "ejecutando")], [])
        env.send(order, "error", "lease_expired", env.world_read(order["epoch"]))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "lease_expired"))
        self.assertEqual(order["bstate"], "parcial")
        reads = [o for o in env.orders("state.read")
                 if o["bstate"] in ("pendiente", "ejecutando")]
        self.assertEqual(len(reads), 1)


class ResetDirecto(SceneLiveBase):
    def test_reset_limpio_observado_sin_reason(self):
        env = self.ready()
        ok, order = env.live.enqueue_reset_locked("op-2", env.doc_id)
        self.assertTrue(ok, order)
        self.assertEqual(env.backend.ops["op-2"]["verb"], "scene.reset")
        env.deliver(order)
        env.send(order, "done", None, env.reset_read(order))
        op = env.backend.ops["op-2"]
        self.assertEqual((op["state"], op["reason"]), ("observado", None))
        self.assertTrue(all(e.get("verb") == "scene.reset" for e in env.op_events()
                            if e["op_id"] == "op-2"))

    def test_reset_retenido_parcial_contenido_ajeno(self):
        env = self.ready()
        ok, order = env.live.enqueue_reset_locked("op-2", env.doc_id)
        self.assertTrue(ok, order)
        env.deliver(order)
        read = env.reset_read(order, outcome="retained", n=1, retained_n=1,
                              retained=["obj-17"])
        env.send(order, "done", None, read)
        op = env.backend.ops["op-2"]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "contenido_ajeno"))
        self.assertEqual(order["bstate"], "terminal")
        self.assertFalse(env.live.has_unresolved_locked())

    def test_reset_interrumpido_e_incoherente(self):
        for outcome, expected in (("interrupted", ("parcial", "interrumpida")),
                                  ("done", ("fallido", "lectura_no_cumple"))):
            with self.subTest(outcome=outcome):
                env = self.ready()
                ok, order = env.live.enqueue_reset_locked("op-2", env.doc_id)
                self.assertTrue(ok)
                env.deliver(order)
                n = 1 if outcome == "done" else 0
                env.send(order, "done", None, env.reset_read(order, outcome=outcome, n=n))
                op = env.backend.ops["op-2"]
                self.assertEqual((op["state"], op["reason"]), expected)

    def test_precondiciones_doc_scene_y_cola(self):
        env = self.ready()
        ok, err = env.live.enqueue_reset_locked("op-9", "d-00000000")
        self.assertFalse(ok)
        self.assertEqual((err["code"], err["http"]), ("doc_changed", 409))
        env2 = self.make_env()
        env2.hello(scene=0)
        ok, err = env2.live.enqueue_reset_locked("op-9", env2.doc_id)
        self.assertFalse(ok)
        self.assertEqual((err["code"], err["http"]), ("scene_unsupported", 409))
        env3 = self.ready()
        env3.bridge.queue_max = 0
        ok, err = env3.live.enqueue_reset_locked("op-9", env3.doc_id)
        self.assertFalse(ok)
        self.assertEqual(err["code"], "queue_full")

    def test_sin_peer_se_encola_igual(self):
        env = self.make_env()
        ok, order = env.live.enqueue_reset_locked("op-2", env.doc_id)
        self.assertTrue(ok, order)
        self.assertEqual(order["verb"], "scene.reset")
        self.assertEqual(env.backend.ops["op-2"]["state"], "pendiente")


def err2http(err):
    return err.get("http")


class Reconciliacion(SceneLiveBase):
    def test_generacion_encola_checkpoint_y_resultado_bueno(self):
        env = self.ready()
        order = self.partial_apply(env)
        read = env.scene_read(order["epoch"], env.doc_id, env.apply_gen(order), None, None, 33)
        env.world(read)
        internals = [o for o in env.f2_internals() if o.get("purpose") == "reconcile_checkpoint"]
        self.assertEqual(len(internals), 1)
        self.assertEqual(internals[0]["args"], {"f2": 1, "doc_id": env.doc_id, "at": "checkpoint"})
        self.assertEqual(internals[0]["target_op_id"], "op-1")
        env.deliver(internals[0])
        env.send(internals[0], "done", None, env.apply_read(order))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("observado", "reconciliada"))
        self.assertEqual(order["bstate"], "terminal")
        self.assertFalse(env.live.has_unresolved_locked())

    def test_checkpoint_malo_fallido(self):
        env = self.ready()
        order = self.partial_apply(env)
        env.world(env.scene_read(order["epoch"], env.doc_id, env.apply_gen(order), None, None, 33))
        internal = [o for o in env.f2_internals() if o.get("purpose") == "reconcile_checkpoint"][0]
        env.deliver(internal)
        rows = env.ckpt_rows(order)
        rows[0][2] = rows[0][2] + 5000
        env.send(internal, "done", None, env.apply_read(order, rows=rows))
        self.assertEqual(env.backend.ops["op-1"]["state"], "fallido")
        self.assertEqual(env.backend.ops["op-1"]["reason"], "lectura_no_cumple")

    def test_identidad_otra_rev_fallido_sin_interna(self):
        env = self.ready()
        order = self.partial_apply(env)
        gen = env.apply_gen(order)
        gen["rev"] = gen["rev"] + 1
        env.world(env.scene_read(order["epoch"], env.doc_id, gen, None, None, 33))
        self.assertEqual(env.backend.ops["op-1"]["state"], "fallido")
        self.assertEqual(env.backend.ops["op-1"]["reason"], "lectura_no_cumple")
        self.assertEqual(env.f2_internals(), [])

    def test_v2_otro_plan_sha256_fallido_sin_interna(self):
        env = self.ready()
        order = self.partial_apply(env)
        gen = env.apply_gen(order)
        gen["plan_sha256"] = "e" * 64
        env.world(env.scene_read(order["epoch"], env.doc_id, gen, None, None, 33))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))
        self.assertEqual(env.f2_internals(), [])

    def test_pending_encola_compensacion_y_compensada(self):
        env = self.ready()
        order = self.partial_apply(env)
        pending = {"session": order["session"], "op_id": "op-1", "n": 10}
        last = {"session": order["session"], "op_id": "op-1",
                "verb": "scene.apply", "outcome": "interrupted"}
        env.world(env.scene_read(order["epoch"], env.doc_id, None, pending, last, 10))
        comp = self.compensation(env)
        self.assertIsNotNone(comp)
        self.assertEqual(comp["args"], {"f2": 1, "doc_id": env.doc_id,
                                        "if_pending": {"session": order["session"], "op_id": "op-1"}})
        env.deliver(comp)
        done = env.scene_read(order["epoch"], env.doc_id, None, None,
                              {"session": order["session"], "op_id": "op-1",
                               "verb": "scene.apply", "outcome": "compensated"}, 0)
        env.send(comp, "done", None, done)
        self.assertEqual(env.backend.ops["op-1"]["state"], "parcial")
        self.assertEqual(env.backend.ops["op-1"]["reason"], "compensada")
        self.assertEqual(order["bstate"], "terminal")
        self.assertFalse(env.live.has_unresolved_locked())

    def test_pending_sin_progreso_interrumpida(self):
        env = self.ready()
        order = self.partial_apply(env)
        pending = {"session": order["session"], "op_id": "op-1", "n": 10}
        interrupted = {"session": order["session"], "op_id": "op-1",
                       "verb": "scene.apply", "outcome": "interrupted"}
        read = env.scene_read(order["epoch"], env.doc_id, None, pending, interrupted, 10)
        env.world(read)
        comp = self.compensation(env)
        env.deliver(comp)
        env.send(comp, "done", None, read)
        self.assertEqual(env.backend.ops["op-1"]["state"], "parcial")
        env.world(read)  # misma n: sin progreso
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"], op["origin"]),
                         ("parcial", "interrumpida", "backend"))
        self.assertEqual(order["bstate"], "terminal")
        self.assertEqual(len([o for o in env.f2_internals()
                              if o.get("purpose") == "compensate"]), 1)

    def test_limite_de_tres_compensaciones_cuenta_rejected(self):
        env = self.ready()
        order = self.partial_apply(env)
        for n in (30, 20, 10):
            pending = {"session": order["session"], "op_id": "op-1", "n": n}
            read = env.scene_read(order["epoch"], env.doc_id, None, pending, None, n)
            env.world(read)
            comp = [o for o in env.f2_internals()
                    if o.get("purpose") == "compensate" and o["bstate"] == "pendiente"]
            self.assertEqual(len(comp), 1)
            env.deliver(comp[0])
            env.send(comp[0], "rejected", "not_pending", env.world_read(order["epoch"]))
            self.assertEqual(env.backend.ops["op-1"]["state"], "parcial")
        pending = {"session": order["session"], "op_id": "op-1", "n": 5}
        env.world(env.scene_read(order["epoch"], env.doc_id, None, pending, None, 5))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"], op["origin"]),
                         ("parcial", "interrumpida", "backend"))
        self.assertEqual(len([o for o in env.f2_internals()
                              if o.get("purpose") == "compensate"]), 3)

    def _lost_compensation(self, env, order, n, delivered=True):
        pending = {"session": order["session"], "op_id": order["op_id"], "n": n}
        read = env.scene_read(order["epoch"], env.doc_id, None, pending, None, n)
        env.world(read)
        comps = [o for o in env.f2_internals()
                 if o.get("purpose") == "compensate" and o["bstate"] == "pendiente"]
        self.assertEqual(len(comps), 1)
        comp = comps[0]
        if delivered:
            env.deliver(comp)
        comp["bstate"] = "descartada"  # resultado perdido y caducidad
        return comp, read

    def test_c01_compensacion_entregada_con_resultado_perdido_cuenta(self):
        env = self.ready()
        order = self.partial_apply(env)
        self._lost_compensation(env, order, 10, delivered=True)
        env.world(env.scene_read(order["epoch"], env.doc_id, None,
                                 {"session": order["session"], "op_id": order["op_id"], "n": 10},
                                 None, 10))
        self.assertEqual(order.get("compensations"), 1)

    def test_c01_compensacion_no_entregada_no_cuenta(self):
        env = self.ready()
        order = self.partial_apply(env)
        first, read = self._lost_compensation(env, order, 10, delivered=False)
        env.world(read)
        self.assertEqual(order.get("compensations"), 0)
        comps = [o for o in env.f2_internals()
                 if o.get("purpose") == "compensate" and o["bstate"] == "pendiente"]
        self.assertEqual(len(comps), 1)
        self.assertIsNot(comps[0], first)

    def test_c01_sin_progreso_tras_descartada_interrumpida(self):
        env = self.ready()
        order = self.partial_apply(env)
        self._lost_compensation(env, order, 10, delivered=True)
        env.world(env.scene_read(order["epoch"], env.doc_id, None,
                                 {"session": order["session"], "op_id": order["op_id"], "n": 10},
                                 None, 10))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"], op["origin"]),
                         ("parcial", "interrumpida", "backend"))
        self.assertEqual(order["bstate"], "terminal")

    def test_c01_con_progreso_a_la_cuarta_interrumpida_por_limite(self):
        env = self.ready()
        order = self.partial_apply(env)
        for n in (40, 30, 20):
            self._lost_compensation(env, order, n, delivered=True)
        self.assertEqual(order.get("compensations"), 2)
        env.world(env.scene_read(order["epoch"], env.doc_id, None,
                                 {"session": order["session"], "op_id": order["op_id"], "n": 10},
                                 None, 10))
        self.assertEqual(order.get("compensations"), 3)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"], op["origin"]),
                         ("parcial", "interrumpida", "backend"))
        self.assertEqual(order["bstate"], "terminal")
        self.assertEqual(len([o for o in env.f2_internals()
                              if o.get("purpose") == "compensate"]), 3)

    def test_c01_compensacion_en_vuelo_no_se_juzga(self):
        # Una lectura que llega con la compensacion entregada y todavia en vuelo
        # (p. ej. entre lotes) ensena el mismo pending.n: no es "sin progreso".
        env = self.ready()
        order = self.partial_apply(env)
        before = dict(env.backend.ops["op-1"])
        pending = {"session": order["session"], "op_id": order["op_id"], "n": 10}
        read = env.scene_read(order["epoch"], env.doc_id, None, pending, None, 10)
        env.world(read)
        comps = [o for o in env.f2_internals()
                 if o.get("purpose") == "compensate" and o["bstate"] == "pendiente"]
        self.assertEqual(len(comps), 1)
        comp = comps[0]
        env.deliver(comp)  # entregada y en vuelo: ejecutando, con delivered_inst
        env.world(read)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), (before["state"], before["reason"]))
        self.assertNotEqual(order["bstate"], "terminal")
        self.assertEqual(len([o for o in env.f2_internals()
                              if o.get("purpose") == "compensate"]), 1)
        # cuando termina sin progreso (resultado perdido y caducidad), la lectura
        # siguiente si juzga: parcial/interrumpida
        comp["bstate"] = "descartada"
        env.world(read)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"], op["origin"]),
                         ("parcial", "interrumpida", "backend"))
        self.assertEqual(order["bstate"], "terminal")

    def test_c02_compensacion_fallida_cierra_la_orden_del_bridge(self):
        env = self.ready()
        order = self.partial_apply(env)
        pending = {"session": order["session"], "op_id": order["op_id"], "n": 10}
        env.world(env.scene_read(order["epoch"], env.doc_id, None, pending, None, 10))
        comp = self.compensation(env)
        self.assertIsNotNone(comp)
        env.deliver(comp)
        other_last = {"session": order["session"], "op_id": "op-99",
                      "verb": "scene.apply", "outcome": "done"}
        read = env.scene_read(order["epoch"], env.doc_id, None, None, other_last, 0)
        env.send(comp, "done", None, read)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))
        self.assertEqual(order["bstate"], "terminal")
        self.assertFalse(env.bridge._has_live_parcial_locked())
        # el calendario no pide otra lectura
        env.bridge.reconciled = True
        env.bridge._read_next_at = 0
        before = len([o for o in env.orders("state.read")
                      if o["bstate"] in ("pendiente", "ejecutando")])
        env.bridge.sweep()
        after = len([o for o in env.orders("state.read")
                     if o["bstate"] in ("pendiente", "ejecutando")])
        self.assertEqual(after, before)
        time.sleep(0.5)
        self.assertEqual(len([o for o in env.orders("state.read")
                              if o["bstate"] in ("pendiente", "ejecutando")]), before)

    def test_orden_de_conn_anterior_mismo_epoch_cuenta_y_se_resuelve(self):
        env = self.ready()
        order = self.partial_apply(env)
        order["conn"] = env.bridge.peers["server"]["conn"] + 99
        self.assertTrue(env.live.has_unresolved_locked())
        env.world(env.scene_read(order["epoch"], env.doc_id, env.apply_gen(order), None, None, 33))
        self.assertEqual(len([o for o in env.f2_internals()
                              if o.get("purpose") == "reconcile_checkpoint"]), 1)

    def test_lectura_de_otro_epoch_no_juzga(self):
        env = self.ready()
        order = self.partial_apply(env)
        other = "f" * 32
        env.world(env.scene_read(other, env.doc_id, env.apply_gen(order), None, None, 33))
        self.assertEqual(env.backend.ops["op-1"]["state"], "parcial")
        self.assertEqual(env.f2_internals(), [])

    def test_servidor_perdido_no_juzga(self):
        env = self.ready()
        order = self.partial_apply(env)
        with env.bridge.cond:
            env.bridge.peers["server"]["lost"] = True
        env.world(env.scene_read(order["epoch"], env.doc_id, env.apply_gen(order), None, None, 33))
        self.assertEqual(env.f2_internals(), [])

    def test_interna_descartada_se_vuelve_a_pedir(self):
        env = self.ready()
        order = self.partial_apply(env)
        pending = {"session": order["session"], "op_id": "op-1", "n": 10}
        read = env.scene_read(order["epoch"], env.doc_id, None, pending, None, 10)
        env.world(read)
        first = self.compensation(env)
        first["bstate"] = "descartada"
        env.world(read)
        comps = [o for o in env.f2_internals()
                 if o.get("purpose") == "compensate" and o["bstate"] == "pendiente"]
        self.assertEqual(len(comps), 1)
        self.assertIsNot(first, comps[0])

    def test_como_mucho_una_interna_en_vuelo(self):
        env = self.ready()
        order = self.partial_apply(env)
        pending = {"session": order["session"], "op_id": "op-1", "n": 10}
        read = env.scene_read(order["epoch"], env.doc_id, None, pending, None, 10)
        env.world(read)
        env.world(read)
        self.assertEqual(len([o for o in env.f2_internals()
                              if o.get("purpose") == "compensate"]), 1)

    def test_last_con_otro_verb_fallido_a4(self):
        env = self.ready()
        order = self.partial_apply(env)
        last = {"session": order["session"], "op_id": "op-1",
                "verb": "scene.reset", "outcome": "done"}
        env.world(env.scene_read(order["epoch"], env.doc_id, None, None, last, 0))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))

    def test_apply_detenido_retenido_admite_restos(self):
        env = self.ready()
        order = self.partial_apply(env)
        last = {"session": order["session"], "op_id": "op-1",
                "verb": "scene.apply", "outcome": "retained"}
        read = env.scene_read(order["epoch"], env.doc_id, None, None, last, 33, 1, ["obj-17"])
        env.world(read)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "contenido_ajeno"))
        self.assertEqual(order["bstate"], "terminal")

    def test_apply_detenido_con_generation_viva_fallido(self):
        env = self.ready()
        order = self.partial_apply(env)
        last = {"session": order["session"], "op_id": "op-1",
                "verb": "scene.apply", "outcome": "retained"}
        other_gen = env.apply_gen(order)
        other_gen["op_id"] = "op-99"
        other_gen["plan_sha256"] = "e" * 64
        read = env.scene_read(order["epoch"], env.doc_id, other_gen,
                              None, last, 33, 1, ["obj-17"])
        env.world(read)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))

    def test_ak2_apply_detenido_retained_con_lista_vacia_fallido(self):
        env = self.ready()
        order = self.partial_apply(env)
        last = {"session": order["session"], "op_id": "op-1",
                "verb": "scene.apply", "outcome": "retained"}
        env.world(env.scene_read(order["epoch"], env.doc_id, None, None, last, 33, 1, []))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))

    def test_ag2_reset_sin_resultado_con_last_done(self):
        for n, expected in ((1, ("fallido", "lectura_no_cumple")),
                            (0, ("observado", "reconciliada"))):
            with self.subTest(n=n):
                env = self.ready()
                ok, order = env.live.enqueue_reset_locked("op-2", env.doc_id)
                self.assertTrue(ok, order)
                env.deliver(order)
                with env.bridge.cond:
                    env.backend.set_op_state("op-2", "parcial", "backend", "sin_resultado")
                    order["bstate"] = "parcial"
                env.world(env.reset_read(order, outcome="done", n=n))
                op = env.backend.ops["op-2"]
                self.assertEqual((op["state"], op["reason"]), expected)

    def test_apply_detenido_interrumpido(self):
        env = self.ready()
        order = self.partial_apply(env)
        last = {"session": order["session"], "op_id": "op-1",
                "verb": "scene.apply", "outcome": "interrupted"}
        env.world(env.scene_read(order["epoch"], env.doc_id, None, None, last, 0))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "interrumpida"))
        self.assertEqual(order["bstate"], "terminal")

    def test_orden_superada_a12(self):
        env = self.ready()
        order = self.partial_apply(env)
        ok, later = env.live.enqueue_reset_locked("op-2", env.doc_id)
        self.assertTrue(ok, later)
        last = {"session": later["session"], "op_id": "op-2",
                "verb": "scene.reset", "outcome": "done"}
        env.world(env.scene_read(order["epoch"], env.doc_id, None, None, last, 0))
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"], op["origin"]),
                         ("parcial", "superada", "servidor"))
        self.assertEqual(order["bstate"], "terminal")
        self.assertFalse(env.live.has_unresolved_locked())

    def test_resultado_tardio_de_mundo_reiniciado_se_aplica_a8(self):
        env = self.ready()
        order = self.partial_apply(env, reason="mundo_reiniciado")
        read = env.apply_read(order)
        # el epoch de la lectura es el de la orden (mismo mundo para el resultado tardio)
        env.send(order, "done", None, read)
        self.assertEqual(env.backend.ops["op-1"]["state"], "observado")


class D1SinEscena(SceneLiveBase):
    def test_state_read_vacio_y_apply_f1_no_es_f2(self):
        env = self.make_env()
        env.hello(scene=0)
        self.assertFalse(env.live.server_has_scene_locked())
        self.assertEqual(env.live.state_read_args_locked(), {})
        ok, order = env.bridge.enqueue_order(
            "scene.apply", {"doc_id": env.doc_id, "rev": env.rev, "hash": env.hash},
            op_id="op-7", internal=False)
        self.assertTrue(ok)
        self.assertFalse(env.live.is_f2_order(order))

    def test_f2_parcial_con_servidor_sin_scene_sigue_parcial(self):
        env = self.ready()
        order = self.partial_apply(env)
        epoch = env.bridge.peers["server"]["epoch"]
        env.hello(epoch=epoch, scene=0)
        read = env.world_read(order["epoch"])
        env.world(read)
        self.assertEqual(env.backend.ops["op-1"]["state"], "parcial")
        self.assertEqual(env.f2_internals(), [])

    def test_aa1_scene_apply_con_plan_v13_sin_marca_en_la_orden_es_f2(self):
        # DP-5: en el cable, la marca es `args.f2 == 1`, aunque la orden del backend no la lleve
        env = self.ready()
        res = env.prepare()
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["plan"]["f2"], 1)
        ok, order = env.bridge.enqueue_order(
            "scene.apply", res["plan"], op_id="op-5", internal=False
        )
        self.assertTrue(ok, order)
        self.assertNotIn("f2", order)
        self.assertTrue(env.live.is_f2_order(order))

    def test_aa3_orden_f2_parcial_sigue_siendo_f2_sin_scene_y_se_juzga(self):
        env = self.ready()
        order = self.partial_apply(env)
        epoch = env.bridge.peers["server"]["epoch"]
        env.hello(epoch=epoch, scene=0)
        self.assertTrue(env.live.is_f2_order(order))
        handled = env.send(order, "done", None, env.world_read(order["epoch"]))
        self.assertTrue(handled, "on_result_locked no la trata como F2")
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("fallido", "lectura_no_cumple"))

    def test_capacidad_scene_es_el_entero_1_a7(self):
        for value, expected in ((True, False), (1.0, False), (1, True), ("1", False)):
            with self.subTest(value=value):
                env = self.make_env()
                env.hello(scene=value)
                self.assertEqual(env.live.server_has_scene_locked(), expected)


class Observe(SceneLiveBase):
    def test_observe_encola_y_guarda_observacion(self):
        env = self.ready()
        res = env.live.request_observe_locked(env.doc_id)
        self.assertTrue(res["ok"], res)
        self.assertEqual(len(env.orders("scene.observe")), 1)
        order = env.orders("scene.observe")[0]
        self.assertTrue(order["internal"])
        self.assertEqual(order["args"], {"f2": 1, "doc_id": env.doc_id, "at": "now"})
        env.deliver(order)
        # v1.3: el cable trae mm y milesimas; la API sigue en metros (§3.8)
        rows = [["obj-01", 6188000, 0, 7626000, 62000, 1000, 0, 0]]
        rows_m = [["obj-01", 6188.0, 0.0, 7626.0, 62.0, 1.0, 0, 0]]
        self.assertIsNone(env.live.observation_locked()["observation"])
        env.send(order, "done", None, env.now_read(order, rows))
        obs = env.live.observation_locked()
        self.assertEqual(obs["observation"]["read_id"], order["op_id"])
        self.assertEqual(obs["observation"]["rows"], rows_m)
        self.assertEqual(obs["observation"]["origin"], "servidor")
        self.assertEqual(env.backend.observation["rows"], rows_m)
        self.assertEqual(obs["age_ms"], 0)
        env.clock.advance(5)
        self.assertEqual(env.live.observation_locked()["age_ms"], 5000)

    def test_un_solo_observe_now_en_vuelo_a9(self):
        env = self.ready()
        first = env.live.request_observe_locked(env.doc_id)
        second = env.live.request_observe_locked(env.doc_id)
        self.assertEqual(first["read_id"], second["read_id"])
        self.assertEqual(len(env.orders("scene.observe")), 1)
        order = env.orders("scene.observe")[0]
        env.deliver(order)
        env.send(order, "done", None, env.now_read(order, []))
        third = env.live.request_observe_locked(env.doc_id)
        self.assertNotEqual(third["read_id"], first["read_id"])

    def test_internas_no_crean_op_ni_op_state(self):
        env = self.ready()
        res = env.live.request_observe_locked(env.doc_id)
        rid = res["read_id"]
        self.assertNotIn(rid, env.backend.ops)
        self.assertFalse([e for e in env.op_events() if e["op_id"] == rid])

    def test_observe_sin_scene_rechazado(self):
        env = self.make_env()
        env.hello(scene=0)
        res = env.live.request_observe_locked(env.doc_id)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "scene_unsupported")
        self.assertEqual(env.orders("scene.observe"), [])


class FallaCerradoA6(SceneLiveBase):
    def test_sin_caps_budget_exceeded(self):
        env = self.ready()
        saved = env.store.catalog
        try:
            env.store.catalog = {"classes": copy.deepcopy(saved["classes"])}
            res = env.prepare()
            self.assertEqual((res["ok"], res["code"], res["http"]),
                             (False, "budget_exceeded", 422))
            self.assertEqual(res["pointer"], "/entities")
            self.assertEqual(env.orders("scene.apply"), [])
        finally:
            env.store.catalog = saved

    def test_enqueue_apply_exige_servidor_con_scene(self):
        env = self.make_env()
        env.hello(scene=0)
        ok, err = env.live.enqueue_apply_locked(
            "op-8", {"rev": 1, "hash": "a" * 64}, {})
        self.assertFalse(ok)
        self.assertEqual(err["code"], "scene_unsupported")
        self.assertEqual(env.orders("scene.apply"), [])

    def test_expectativa_obligatoria(self):
        env = self.ready()
        res = env.prepare()
        ok, err = env.live.enqueue_apply_locked("op-8", res["plan"], None)
        self.assertFalse(ok)
        self.assertEqual(err["code"], "bad_args")
        self.assertEqual(env.orders("scene.apply"), [])

    def test_c07_expansion_unavailable_antes_que_los_topes(self):
        # §4.1: la secuencia manda. Sin topes validos, el primer error sigue
        # siendo el primer actor del documento (no budget_exceeded).
        env = self.ready()
        with open(FIXTURES / "escena-basica-cine.json", encoding="utf-8") as fh:
            doc = json.load(fh)
        idx = next(i for i, ent in enumerate(doc["entities"])
                   if ent.get("kind") == "actor")
        saved = env.store.catalog
        try:
            env.store.catalog = dict(saved, caps={})
            res = env.prepare(doc=doc)
        finally:
            env.store.catalog = saved
        self.assertFalse(res["ok"], res)
        self.assertEqual(res["code"], "expansion_unavailable")
        self.assertEqual(res["http"], 422)
        self.assertEqual(res["pointer"], "/entities/%d" % idx)
        self.assertEqual(env.orders("scene.apply"), [])


class ContratoV13(SceneLiveBase):
    """Contrato v1.3 del cable (brief de F2-partida §3): marca f2, DP-2, P-01 y unidades."""

    def _result(self, env, order, read, status="done"):
        srv = env.bridge.peers["server"]
        query = {"peer": "server", "inst": srv["inst"], "session": env.bridge.session}
        body = {"op_id": order["op_id"], "session": env.bridge.session, "epoch": order["epoch"],
                "status": status, "reason": None, "dup": False, "read": read}
        return env.bridge.handle_result(query, body)

    def test_g_state_read_con_escena_lleva_f2_y_no_es_orden_f2(self):
        env = self.ready()
        self.assertEqual(env.live.state_read_args_locked(), {"f2": 1, "doc_id": env.doc_id})
        with env.bridge.cond:
            order = env.bridge._trigger_state_read_locked()
        self.assertIsNotNone(order)
        self.assertEqual(order["args"], {"f2": 1, "doc_id": env.doc_id})
        self.assertFalse(env.live.is_f2_order(order))

    def test_g_is_f2_order_solo_en_verbos_de_escena(self):
        env = self.make_env()
        live = env.live
        args_f2 = {"f2": 1, "doc_id": env.doc_id}
        # P-01: state.read nunca es F2, ni con args.f2 = 1 ni con la marca de la orden
        self.assertFalse(live.is_f2_order({"verb": "state.read", "args": args_f2}))
        self.assertFalse(live.is_f2_order({"verb": "state.read", "args": args_f2, "f2": True}))
        self.assertFalse(live.is_f2_order({"verb": "otro.verbo", "args": args_f2}))
        # DP-5: en los verbos de escena la marca del cable cuenta
        self.assertTrue(live.is_f2_order({"verb": "scene.apply", "args": dict(args_f2, rev=1)}))
        self.assertTrue(live.is_f2_order({"verb": "scene.reset", "args": args_f2}))
        self.assertTrue(live.is_f2_order({"verb": "scene.observe", "args": args_f2}))
        # un scene.apply F1 (sin f2) no es F2; f2 = 0, True o 1.0 tampoco
        f1 = {"doc_id": env.doc_id, "rev": 1, "hash": "a" * 64}
        self.assertFalse(live.is_f2_order({"verb": "scene.apply", "args": f1}))
        for bad in (0, True, 1.0, "1"):
            self.assertFalse(live.is_f2_order({"verb": "scene.apply", "args": dict(f1, f2=bad)}), bad)

    def test_g_lectura_de_state_read_con_f2_reconcilia_por_el_camino_comun(self):
        env = self.ready()
        order = self.partial_apply(env)
        self.assertFalse(env.bridge.reconciled)
        with env.bridge.cond:
            rd = env.bridge._trigger_state_read_locked()
        self.assertEqual(rd["args"], {"f2": 1, "doc_id": env.doc_id})
        env.deliver(rd)
        read = env.scene_read(order["epoch"], env.doc_id, env.apply_gen(order), None, None, 33)
        st, resp = self._result(env, rd, read)
        self.assertEqual(st, 200, resp)
        # camino comun del bridge: reconciled y on_world_read_locked (la generacion encola el checkpoint)
        self.assertTrue(env.bridge.reconciled)
        internals = [o for o in env.f2_internals() if o.get("purpose") == "reconcile_checkpoint"]
        self.assertEqual(len(internals), 1)
        self.assertEqual(internals[0]["args"], {"f2": 1, "doc_id": env.doc_id, "at": "checkpoint"})

    def test_c_enqueue_no_manda_un_plan_sin_alguna_clave(self):
        env = self.ready()
        res = env.prepare()
        self.assertTrue(res["ok"], res)
        before_events = len(env.backend.ring)
        for key in ("f2", "caps", "lid", "x_mm", "yaw_mdeg", "plan_sha256"):
            plan = copy.deepcopy(res["plan"])
            del plan[key]
            ok, err = env.live.enqueue_apply_locked("op-8", plan, res["expectation"])
            self.assertFalse(ok, key)
            self.assertEqual((err["code"], err["pointer"]), ("bad_plan", "/plan/%s" % key))
        no_total = copy.deepcopy(res["plan"])
        del no_total["caps"]["total"]
        ok, err = env.live.enqueue_apply_locked("op-8", no_total, res["expectation"])
        self.assertFalse(ok)
        self.assertEqual(err["code"], "bad_plan")
        misaligned = copy.deepcopy(res["plan"])
        misaligned["ci"] = misaligned["ci"][:-1]
        ok, err = env.live.enqueue_apply_locked("op-8", misaligned, res["expectation"])
        self.assertFalse(ok)
        self.assertEqual(env.orders("scene.apply"), [])
        self.assertNotIn("op-8", env.backend.ops)
        self.assertEqual(len(env.backend.ring), before_events)
        # el plan completo si se manda
        ok, order = env.live.enqueue_apply_locked("op-8", res["plan"], res["expectation"])
        self.assertTrue(ok, order)
        self.assertEqual(order["args"]["caps"]["total"], -1)

    def test_reset_normal_manda_if_pending_vacio_y_se_juzga_como_reset(self):
        env = self.ready()
        ok, order = env.live.enqueue_reset_locked("op-2", env.doc_id)
        self.assertTrue(ok, order)
        self.assertEqual(order["args"], {"f2": 1, "doc_id": env.doc_id,
                                         "if_pending": {"session": "", "op_id": ""}})
        env.deliver(order)
        env.send(order, "done", None, env.reset_read(order))
        op = env.backend.ops["op-2"]
        self.assertEqual((op["state"], op["reason"]), ("observado", None))

    def test_e_checkpoint_con_floats_no_reconcilia(self):
        env = self.ready()
        order = self.partial_apply(env)
        env.world(env.scene_read(order["epoch"], env.doc_id, env.apply_gen(order), None, None, 33))
        internal = [o for o in env.f2_internals() if o.get("purpose") == "reconcile_checkpoint"][0]
        env.deliver(internal)
        rows = env.ckpt_rows(order)
        rows[0][2] = float(rows[0][2])
        bad = env.apply_read(order, rows=rows)
        self.assertFalse(env.live.valid_read(internal, bad))
        st, resp = self._result(env, internal, bad)
        self.assertEqual(st, 400, resp)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("parcial", "sin_resultado"))
        self.assertTrue(env.live.has_unresolved_locked())
        # con enteros, la misma lectura reconcilia
        st, resp = self._result(env, internal, env.apply_read(order))
        self.assertEqual(st, 200, resp)
        op = env.backend.ops["op-1"]
        self.assertEqual((op["state"], op["reason"]), ("observado", "reconciliada"))

    def test_e_lectura_del_mundo_con_floats_no_juzga(self):
        env = self.ready()
        order = self.partial_apply(env)
        pending = {"session": order["session"], "op_id": "op-1", "n": 10}
        read = env.scene_read(order["epoch"], env.doc_id, None, pending, None, 10)
        read["obs"] = {"at": "now", "rows": [["obj-01", 1000.0, 0, 0, 0, 1000, 0, 0]]}
        env.world(read)
        self.assertEqual(env.f2_internals(), [])
        self.assertEqual(env.backend.ops["op-1"]["state"], "parcial")
        read["obs"]["rows"][0][1] = 1000
        env.world(read)
        self.assertIsNotNone(self.compensation(env))

    def test_f_observe_now_con_floats_no_cambia_la_observacion(self):
        env = self.ready()
        res = env.live.request_observe_locked(env.doc_id)
        order = env.orders("scene.observe")[0]
        self.assertEqual(order["op_id"], res["read_id"])
        env.deliver(order)
        rows = [["obj-01", 6188.0, 0.0, 7626.0, 62.0, 1.0, 0, 0]]  # forma v1.2.2: metros
        env.send(order, "done", None, env.now_read(order, rows))
        self.assertIsNone(env.live.observation_locked()["observation"])
        self.assertIsNone(env.backend.observation)


if __name__ == "__main__":
    unittest.main()
