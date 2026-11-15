"""Pruebas de punta a punta de F2 (brief F2-offline §7).

Bridge real en un hilo con puerto 0, Backend real, y el mod falso con mundo
(`FakeMod(..., world=FakeWorld(...))`). Constantes cortadas como en
`test_fake_mod.py`; esperas por sondeo con tope, nunca sleeps fijos largos.
Solo biblioteca estandar y 127.0.0.1.
"""
import copy
import http.client
import io
import json
import math
import os
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.backend.scene_plan import (
    check_apply_predicate,
    evaluate_compensation_predicate,
    evaluate_reset_predicate,
)
from app.backend.server import Backend
from app.backend.store import Store
from app.tests.fake_mod import FakeMod
from app.tests.fake_world import (
    POS_TOL_M,
    FakeWorld,
    build_plan,
    compute_plan_sha256,
    hash_doc,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
HK = "clave-persona-f2-live-1234567890"
AK = "clave-ia-f2-live-0987654321"
PK = "clave-peer-f2-live-abcdef1234567890"
REG_SHA = "0" * 64
DOC_ID = "d-7c19e2a5"


def wait_until(fn, timeout=10.0, step=0.02):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = fn()
        if last:
            return last
        time.sleep(step)
    return last


def wait_op(env, op_id, state, reason=None, timeout=15.0):
    ok = wait_until(
        lambda: env.op(op_id)["state"] == state
        and (reason is None or env.op(op_id).get("reason") == reason), timeout)
    assert ok, "op %s no llego a (%s,%s): %s" % (
        op_id, state, reason, env.op(op_id))
    return env.op(op_id)


def dist3(a, b):
    return math.sqrt(
        (float(a[0]) - float(b[0])) ** 2
        + (float(a[1]) - float(b[1])) ** 2
        + (float(a[2]) - float(b[2])) ** 2
    )


def _load(name):
    with (FIXTURES / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _doc_without_actors():
    doc = _load("escena-sin-actores.json")
    return doc


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class Env:
    """Backend real + Bridge real en 127.0.0.1:0, con Store sobre la fixture copiada."""

    def __init__(self, *, dir=None, clock=None, bridge_kwargs=None, remove_dir=True):
        self.remove_dir = remove_dir
        self.dir = dir or tempfile.mkdtemp(prefix="dsbx-f2-live-")
        self.own_dir = dir is None
        scene_path = os.path.join(self.dir, "scene.json")
        if not os.path.exists(scene_path):
            doc = _doc_without_actors()
            with open(scene_path, "w", encoding="utf-8") as fh:
                json.dump({"rev": 1, "doc": doc}, fh)
        catalog = _load("catalog-m1.json")
        self.store = Store(scene_path, catalog)
        self.log = io.StringIO()
        self.clock = clock or time.monotonic
        kw = {"lease_ms": 600, "hold_ms": 150, "retry_ms": 200, "ttl_ms": 4000,
              "read_retry_ms": (50, 100, 200), "enable_sweeper": False}
        kw.update(bridge_kwargs or {})
        self.backend = Backend(self.store, HK, AK, port=0, log=self.log,
                               clock=self.clock, bridge_port=0, peer_key=PK,
                               bridge_kwargs=kw)
        self.bridge = self.backend.bridge
        self.live = self.backend.scene_live
        self.thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.thread.start()
        self.fake = None
        self.world = None
        self._closed = False

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.backend.shutdown()
        except Exception:
            pass
        try:
            self.thread.join(timeout=5)
        except Exception:
            pass
        if self.remove_dir:
            shutil.rmtree(self.dir, ignore_errors=True)

    def start_fake(self, *, world=None, **kw):
        args = {"maintenance_ms": 20, "result_retry_ms": (30, 60, 90),
                "catalog_page_size": 200}
        args.update(kw)
        self.world = world
        fake = FakeMod("http://127.0.0.1:%d" % self.bridge.port, PK, world=world, **args)
        self.fake = fake
        assert fake.wait_ready(timeout=15), "el mod falso no reconcilio"
        assert wait_until(lambda: self.bridge.reconciled, 10), "bridge no reconcilio"
        return fake

    def snap(self):
        return self.store.snapshot()

    def apply(self, doc_id=None, rev=None, hash_=None):
        snap = self.snap()
        return self.backend.apply(doc_id or snap["doc_id"],
                                  snap["rev"] if rev is None else rev,
                                  snap["hash"] if hash_ is None else hash_)

    def reset(self, doc_id=None):
        return self.backend.reset(doc_id or self.snap()["doc_id"])

    def set_doc(self, doc, rev=None):
        with self.store.lock:
            self.store._doc = copy.deepcopy(doc)
            self.store._rev = (self.store._rev + 1) if rev is None else rev
        return self.store.snapshot()

    def op(self, op_id):
        return self.backend.ops[op_id]

    def wait_state(self, op_id, state, timeout=12.0):
        ok = wait_until(lambda: self.op(op_id)["state"] == state, timeout)
        assert ok, "op %s no llego a %s: %s" % (op_id, state, self.op(op_id))
        return self.op(op_id)

    def events_for(self, op_id):
        out = []
        for _seq, kind, data in list(self.backend.ring):
            if kind != "op.state":
                continue
            d = json.loads(data)
            if d.get("op_id") == op_id:
                out.append(d)
        return out

    def orders(self, verb=None, internal=None):
        out = []
        for o in self.bridge.orders.values():
            if verb is not None and o.get("verb") != verb:
                continue
            if internal is not None and bool(o.get("internal")) is not internal:
                continue
            out.append(o)
        return out

    def f2_internals(self):
        return [o for o in self.orders(internal=True)
                if self.live.is_f2_order(o)]

    def http(self, method, path, body=None, key=AK):
        conn = http.client.HTTPConnection("127.0.0.1", self.backend.port, timeout=10)
        data = None
        headers = {}
        if key is not None:
            headers["Authorization"] = "Bearer " + key
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            status = resp.status
        finally:
            conn.close()
        try:
            obj = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            obj = {}
        return status, obj


class LiveBase(unittest.TestCase):
    def make_env(self, **kw):
        env = Env(**kw)
        self.addCleanup(self._close_env, env)
        return env

    def _close_env(self, env):
        if env.fake is not None:
            env.fake.close()
        env.close()
        text = env.log.getvalue()
        for secret in (PK, HK, AK):
            self.assertNotIn(secret, text)

    def start(self, env, world=None, **kw):
        fake = env.start_fake(world=world, **kw)
        self.addCleanup(fake.close)
        return fake

    # --- lecturas sinteticas validas (para ramas de predicado) ----------

    def scene_read(self, epoch, doc_id=DOC_ID, generation=None, n=0, retained_n=0,
                   retained=None, pending=None, last=None, obs_at=None, rows=None):
        read = {
            "epoch": epoch,
            "generation": generation,
            "registry_n": 0,
            "registry_sha256": REG_SHA,
            "scene": {
                "doc_id": doc_id,
                "gen_n": 1,
                "n": n,
                "retained_n": retained_n,
                "retained": [] if retained is None else retained,
                "pending": pending,
                "last": last,
            },
        }
        if obs_at is not None:
            read["obs"] = {"at": obs_at, "rows": [] if rows is None else rows}
        return read


class F2A1Plan(LiveBase):
    def test_apply_valido_plan_reproducible_filas_y_yaw_normalizado(self):
        env = self.make_env()
        fake = self.start(env, world=FakeWorld())
        doc = env.snap()["doc"]
        doc["entities"][0]["yaw"] = 359.9999
        snap = env.set_doc(doc)
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        op_id = r["op_id"]
        env.wait_state(op_id, "observado")
        orders = [o for o in env.orders(verb="scene.apply", internal=False)
                  if o["op_id"] == op_id]
        self.assertEqual(len(orders), 1)
        args = orders[0]["args"]
        self.assertEqual(len(args["rows"]), 33)
        self.assertIn("plan_sha256", args)
        recomputed = compute_plan_sha256(
            args["doc_id"], args["rev"], args["hash"], args["classes"], args["rows"])
        self.assertEqual(recomputed, args["plan_sha256"])
        row = next(r for r in args["rows"] if r[0] == "obj-01")
        self.assertEqual(row[4], 0.0)
        # D11: las filas son las del documento congelado (redondeadas)
        exp = {}
        for ent in doc["entities"]:
            if ent.get("kind") == "actor":
                continue
            exp[ent["id"]] = (ent["cls"], round(float(ent["x"]), 3),
                              round(float(ent["z"]), 3))
        self.assertEqual({r[0] for r in args["rows"]}, set(exp))
        for lid, ci, x, z, _yaw in args["rows"]:
            cls, ex, ez = exp[lid]
            self.assertEqual(args["classes"][ci], cls)
            self.assertLess(dist3((x, 0.0, z), (ex, 0.0, ez)), POS_TOL_M - 0.002)
        self.assertEqual(fake.world.census() and len(fake.world.census()), 33)

    def test_negativos_antes_de_mandar_nada(self):
        env = self.make_env()
        fake = self.start(env, world=FakeWorld())
        base = _doc_without_actors()
        long_cls = "C" * 1024
        with env.bridge.cond:
            env.bridge.catalog["classes"].append([long_cls, "EntityAI"])

        cases = []
        # expansion_unavailable
        doc = copy.deepcopy(base)
        actor = _load("escena-basica-cine.json")["entities"][0]
        self.assertEqual(actor["kind"], "actor")
        doc["entities"].append(copy.deepcopy(actor))
        cases.append((doc, None, "expansion_unavailable", "/entities/33"))
        # unknown_class
        doc = copy.deepcopy(base)
        doc["entities"][4]["cls"] = "ClaseQueNoExiste"
        cases.append((doc, None, "unknown_class", "/entities/4/cls"))
        # out_of_map
        doc = copy.deepcopy(base)
        doc["entities"][2]["x"] = 20000.0
        cases.append((doc, None, "out_of_map", "/entities/2/x"))
        # plan_too_large: lid de 11
        doc = copy.deepcopy(base)
        doc["entities"][1]["id"] = "obj-0000001"
        cases.append((doc, None, "plan_too_large", "/entities/1/id"))
        # plan_too_large: lid con digitos no ASCII
        doc = copy.deepcopy(base)
        doc["entities"][6]["id"] = "obj-\u0660\u0661"
        cases.append((doc, None, "plan_too_large", "/entities/6/id"))
        # A15: clase de 1024 caracteres
        doc = copy.deepcopy(base)
        doc["entities"][8]["cls"] = long_cls
        cases.append((doc, None, "plan_too_large", "/entities/8/cls"))

        for doc, _rev, code, pointer in cases:
            snap = env.set_doc(doc)
            before_orders = len(env.bridge.orders)
            before_seq = env.backend.seq
            r = env.apply(snap["doc_id"], snap["rev"], snap["hash"])
            self.assertFalse(r.get("ok"), (code, r))
            self.assertEqual(r.get("code"), code, (code, r))
            self.assertEqual(r.get("pointer"), pointer, (code, r))
            self.assertEqual(len(env.bridge.orders), before_orders, code)
            self.assertEqual(env.backend.seq, before_seq, code)
            self.assertNotIn("scene.apply", env.log.getvalue())

        # rev de 10 digitos
        snap = env.set_doc(copy.deepcopy(base), rev=1234567890)
        before_orders = len(env.bridge.orders)
        before_seq = env.backend.seq
        r = env.apply(snap["doc_id"], snap["rev"], snap["hash"])
        self.assertEqual(r.get("code"), "plan_too_large", r)
        self.assertEqual(len(env.bridge.orders), before_orders)
        self.assertEqual(env.backend.seq, before_seq)

    def test_catalog_pending_catalogo_de_otro_arranque(self):
        env = self.make_env()
        fake = self.start(env, world=FakeWorld())
        srv = env.bridge.peers["server"]
        with env.bridge.cond:
            env.live.on_server_hello_locked(srv)
        self.assertFalse(env.live.catalog_ok_locked())
        # un catalogo completo de otra inst no vale
        self.assertFalse(env.live.on_catalog_complete_locked("a" * 32, "retail"))
        before_orders = len(env.bridge.orders)
        before_seq = env.backend.seq
        r = env.apply()
        self.assertEqual(r.get("code"), "catalog_pending", r)
        self.assertEqual(r.get("pointer"), "", r)
        self.assertEqual(len(env.bridge.orders), before_orders)
        self.assertEqual(env.backend.seq, before_seq)
        # el catalogo del servidor vigente vuelve a valer
        self.assertTrue(env.live.on_catalog_complete_locked(srv["inst"], "retail"))
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        env.wait_state(r["op_id"], "observado")


class F2A6Caps(LiveBase):
    def test_topos_exactos_observado(self):
        env = self.make_env()
        self.start(env, world=FakeWorld())
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        env.wait_state(r["op_id"], "observado")

    def test_topos_bajados_uno_por_uno_y_total(self):
        env = self.make_env()
        self.start(env, world=FakeWorld())
        caps = env.store.catalog["caps"]
        original = dict(caps)
        for key, value in (("objeto", 19), ("infectado", 9), ("animal", 2)):
            caps.update(original)
            caps[key] = value
            before_orders = len(env.bridge.orders)
            before_seq = env.backend.seq
            r = env.apply()
            self.assertEqual(r.get("code"), "budget_exceeded", (key, r))
            self.assertEqual(r.get("pointer"), "/entities", r)
            self.assertEqual(len(env.bridge.orders), before_orders, key)
            self.assertEqual(env.backend.seq, before_seq, key)
        caps.clear()
        caps.update(original)
        caps["total"] = 30
        r = env.apply()
        self.assertEqual(r.get("code"), "budget_exceeded", r)
        caps.clear()
        caps.update(original)
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        env.wait_state(r["op_id"], "observado")

    def test_orden_directa_al_mod_por_encima_de_sus_caps(self):
        env = self.make_env()
        fake = self.start(env, world=FakeWorld())
        doc = _doc_without_actors()
        plan = build_plan(doc, rev=1, hash=hash_doc(doc),
                          caps={"objeto": 19, "infectado": 10, "animal": 3})
        srv = fake.server
        before = fake.world.census()
        order = {
            "op_id": "op-caps", "session": srv.session, "conn": srv.conn,
            "epoch": fake.epoch, "inst": srv.inst, "verb": "scene.apply",
            "args": plan, "issued_ms": int(time.monotonic() * 1000), "ttl_ms": 4000,
        }
        srv.handle_order(order, now_ms=order["issued_ms"])
        entry = wait_until(
            lambda: next((e for e in srv.cache.values()
                          if e.order["op_id"] == "op-caps" and e.state == "terminada"), None),
            8)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.result.get("status"), "rejected")
        self.assertEqual(entry.result.get("reason"), "budget_exceeded")
        self.assertEqual(fake.world.census(), before)


class F2A2Apply(LiveBase):
    def test_apply_33_censo_checkpoint_y_deriva(self):
        env = self.make_env()
        world = FakeWorld(tick_s=0.02)
        fake = self.start(env, world=world)
        doc = _doc_without_actors()
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        op_id = r["op_id"]
        env.wait_state(op_id, "observado")
        census = world.census()
        own = [c for c in census if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 33)
        expected = {}
        for ent in doc["entities"]:
            expected[ent["id"]] = (ent["kind"], ent["cls"], float(ent["x"]), float(ent["z"]))
        self.assertEqual(sorted(c["cls"] for c in own),
                         sorted(e[1] for e in expected.values()))
        # objetos: censo a < 0,5 m de (x_doc, gy, z_doc); hay clases repetidas,
        # asi que se compara contra la mejor de las posiciones del documento.
        for c in own:
            if c["cls"].startswith("Zmb") or c["cls"].startswith("Animal_"):
                continue
            best = min(
                dist3(c["pos"], (e["x"], world.ground_y(e["x"], e["z"]), e["z"]))
                for e in doc["entities"] if e["cls"] == c["cls"])
            self.assertLess(best, POS_TOL_M - 0.002, c["cls"])
        # checkpoint del resultado: las 33, incluidas criaturas, a < 0,5 m
        bodies = [b for b in fake.server.sent_results
                  if b["op_id"] == op_id and b.get("status") == "done"]
        self.assertTrue(bodies)
        read = bodies[-1]["read"]
        self.assertEqual(read["obs"]["at"], "checkpoint")
        rows = read["obs"]["rows"]
        self.assertEqual(len(rows), 33)
        by_lid = {e["id"]: e for e in doc["entities"]}
        for row in rows:
            lid, ci, x, y, z, _yaw, gy = row
            ent = by_lid[lid]
            self.assertEqual(row[1], read_classes_index(doc, ent["cls"], bodies[-1]),
                             lid)
            self.assertLess(dist3((x, y, z), (float(ent["x"]), gy, float(ent["z"]))),
                            POS_TOL_M - 0.002)
        # deriva activa: la lectura `now` del mundo ya no coincide con el checkpoint
        order = {"op_id": "obs-a2", "session": "a" * 16, "epoch": world.epoch,
                 "verb": "scene.observe", "args": {"doc_id": DOC_ID, "at": "now"}}
        st, rsn, now_read = world.observe(order)
        self.assertEqual(st, "done", rsn)
        now_rows = {r[0]: r for r in now_read["obs"]["rows"]}
        ckpt_rows = {r[0]: r for r in rows}
        moved = 0
        for lid, ent in by_lid.items():
            if not (ent["kind"] in ("infectado", "animal")):
                continue
            nrow = now_rows[lid]
            crow = ckpt_rows[lid]
            if dist3((nrow[1], nrow[2], nrow[3]), (crow[2], crow[3], crow[4])) > 0.5:
                moved += 1
        self.assertGreater(moved, 0)

    def test_creacion_suprimida_fallido_y_censo_32(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        world.suppress_create("obj-05")
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        op = env.wait_state(r["op_id"], "fallido")
        self.assertEqual(op.get("reason"), "lectura_no_cumple")
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 32)

    def test_doble_entrega_censo_33_y_creados_33(self):
        env = self.make_env()
        world = FakeWorld()
        fake = self.start(env, world=world)
        # la orden se queda en la barrera tras la creacion 8: la doble entrega
        # llega con la orden en curso, no despues (el mundo sin tick es instantaneo)
        world.barrier_after(8)
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(world.wait_barrier_reached(8))
        self.assertEqual(world.effects(fake.server.session, op_id)["created"], 8)
        order = next(o for o in fake.server.received_orders if o["op_id"] == op_id)
        try:
            self.assertEqual(fake.force_double_delivery(order), ("en_curso", "en_curso"))
        finally:
            world.release_barrier()
        env.wait_state(op_id, "observado")
        self.assertEqual(world.effects(fake.server.session, op_id)["created"], 33)
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 33)

    def test_entidad_desplazada_06_fallido(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        world.displace_on_create("obj-03", 0.6)
        r = env.apply()
        op = env.wait_state(r["op_id"], "fallido")
        self.assertEqual(op.get("reason"), "lectura_no_cumple")
        self.assertNotIn("observado", [e["state"] for e in env.events_for(r["op_id"])])

    def test_error_real_05004_que_el_redondeo_deja_en_04999(self):
        # EPS_Q: con tolerancia 0,5 el 0,4999 redondeado pasaria; con 0,498 no.
        order = {
            "session": "a" * 16, "op_id": "op-1", "epoch": "e" * 32,
            "verb": "scene.apply",
            "args": {
                "doc_id": DOC_ID, "rev": 1, "hash": "0" * 64,
                "plan_sha256": "0" * 64, "classes": ["WoodenCrate"],
                "rows": [["obj-01", 0, 0.0, 0.0, 0.0]],
            },
            "expectation": {"obj-01": ("WoodenCrate", 0.0, 0.0)},
        }
        gen = {"session": "a" * 16, "op_id": "op-1", "rev": 1,
               "hash": "0" * 64, "plan_sha256": "0" * 64}
        last = {"session": "a" * 16, "op_id": "op-1",
                "verb": "scene.apply", "outcome": "done"}
        read = self.scene_read(
            "e" * 32, generation=gen, n=1, last=last, obs_at="checkpoint",
            rows=[["obj-01", 0, 0.07, 0.0, 0.495, 0.0, 0.0]])
        self.assertFalse(check_apply_predicate(order, read))
        read_ok = self.scene_read(
            "e" * 32, generation=gen, n=1, last=last, obs_at="checkpoint",
            rows=[["obj-01", 0, 0.0, 0.0, 0.0, 0.0, 0.0]])
        self.assertTrue(check_apply_predicate(order, read_ok))

    def test_fila_omitida_y_ci_de_otra_clase(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        snap = env.snap()
        full = _doc_without_actors()
        res = env.live.prepare_apply_locked(full, snap["rev"], snap["hash"])
        self.assertTrue(res.get("ok"), res)
        expectation = res["expectation"]

        # fila omitida: plan de 32 filas contra una expectativa de 33
        reduced = copy.deepcopy(full)
        reduced["entities"] = [e for e in reduced["entities"] if e["id"] != "zmb-01"]
        plan = build_plan(reduced, rev=snap["rev"], hash=hash_doc(reduced),
                          caps=env.store.catalog["caps"])
        ok, order = env.live.enqueue_apply_locked("op-901", plan, expectation)
        self.assertTrue(ok, order)
        op = env.wait_state("op-901", "fallido")
        self.assertEqual(op.get("reason"), "lectura_no_cumple")

        # ci de otra clase: dos entidades comparten clase, una fila apunta a otra
        mutated = copy.deepcopy(full)
        mutated["entities"][0]["cls"] = mutated["entities"][1]["cls"]
        plan = build_plan(mutated, rev=snap["rev"], hash=hash_doc(mutated),
                          caps=env.store.catalog["caps"])
        exp2 = env.live.prepare_apply_locked(mutated, snap["rev"], hash_doc(mutated))
        self.assertTrue(exp2.get("ok"), exp2)
        rows = copy.deepcopy(plan["rows"])
        other_ci = plan["classes"].index("Land_Wreck_V3S")
        for row in rows:
            if row[0] == "obj-01":
                row[1] = other_ci
        plan2 = dict(plan)
        plan2["rows"] = rows
        plan2["plan_sha256"] = compute_plan_sha256(
            plan["doc_id"], plan["rev"], plan["hash"], plan["classes"], rows)
        ok, order = env.live.enqueue_apply_locked("op-902", plan2, exp2["expectation"])
        self.assertTrue(ok, order)
        op = env.wait_state("op-902", "fallido")
        self.assertEqual(op.get("reason"), "lectura_no_cumple")


def read_classes_index(doc, cls, body):
    # el checkpoint lleva el indice de la clase en `classes` del plan; se reconstruye
    classes = sorted({e["cls"] for e in doc["entities"] if e.get("kind") != "actor"})
    return classes.index(cls)


class F2A3Reset(LiveBase):
    def _applied(self, env):
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        env.wait_state(r["op_id"], "observado")
        return r["op_id"]

    def test_reset_limpio_con_hijos_propios_y_segundo_reset(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        self._applied(env)
        world.spawn_own_child(DOC_ID, "obj-17", "WoodenCrate", "obj-90")
        child2 = world.spawn_own_child(DOC_ID, "obj-15", "Pot", "obj-91")
        world.move_to_ground(child2)
        r = env.reset()
        self.assertTrue(r.get("ok"), r)
        op = env.wait_state(r["op_id"], "observado")
        self.assertIsNone(op.get("reason"))
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(own, [])
        self.assertEqual(world.storage_ops, 0)
        r2 = env.reset()
        self.assertTrue(r2.get("ok"), r2)
        env.wait_state(r2["op_id"], "observado")
        self.assertEqual(world.effects(env.fake.server.session, r2["op_id"]),
                         {"created": 0, "deleted": 0})

    def test_ajeno_en_suelo_y_segunda_escena_intactos(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        self._applied(env)
        f_eid = world.spawn_foreign("FirstAidKit", 6190.0, 7630.0, 45.0)
        world.seed_scene("d-5ec00001", [["obj-01", "WoodenCrate", 6100.0, 7600.0, 0.0]])
        foreign_before = {c["eid"]: copy.deepcopy(c) for c in world.census()
                          if c["origin"] == "foreign"}
        second_before = {c["eid"]: copy.deepcopy(c) for c in world.census()
                         if c["scene"] == "d-5ec00001"}
        r = env.reset()
        env.wait_state(r["op_id"], "observado")
        after = {c["eid"]: c for c in world.census()}
        for eid, row in foreign_before.items():
            self.assertIn(eid, after)
            self.assertEqual(after[eid]["cls"], row["cls"])
            self.assertEqual(after[eid]["pos"], row["pos"])
        for eid, row in second_before.items():
            self.assertIn(eid, after)
            self.assertEqual(after[eid]["pos"], row["pos"])
        self.assertIn(f_eid, after)

    def test_ajeno_dentro_de_obj_17_parcial_contenido_ajeno(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        self._applied(env)
        obj17_before = next(copy.deepcopy(c) for c in world.census()
                            if c["scene"] == DOC_ID and c["cls"] == "SeaChest")
        f_eid = world.spawn_foreign("FirstAidKit", 6140.0, 7676.0, 200.0,
                                    inside="obj-17")
        foreign_before = next(copy.deepcopy(c) for c in world.census()
                              if c["eid"] == f_eid)
        r = env.reset()
        op = env.wait_state(r["op_id"], "parcial")
        self.assertEqual(op.get("reason"), "contenido_ajeno")
        self.assertEqual(op.get("verb"), "scene.reset")
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]["cls"], "SeaChest")
        self.assertEqual(own[0]["pos"], obj17_before["pos"])
        after_f = next(c for c in world.census() if c["eid"] == f_eid)
        self.assertEqual(after_f["pos"], foreign_before["pos"])
        self.assertEqual(after_f["parent"], obj17_before["eid"])
        r2 = env.reset()
        op2 = env.wait_state(r2["op_id"], "parcial")
        self.assertEqual(op2.get("reason"), "contenido_ajeno")

    def test_ajeno_en_hijo_contenedor_de_obj_15_retiene_cadena(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        self._applied(env)
        child = world.spawn_own_child(DOC_ID, "obj-15", "WoodenCrate", "obj-92")
        f_eid = world.spawn_foreign("Pot", 6163.0, 7663.0, 30.0,
                                    inside=(DOC_ID, "obj-92"))
        r = env.reset()
        op = env.wait_state(r["op_id"], "parcial")
        self.assertEqual(op.get("reason"), "contenido_ajeno")
        after = {c["eid"]: c for c in world.census()}
        self.assertIn(child, after)
        self.assertIn(f_eid, after)
        parent = after[child]["parent"]
        self.assertIn(parent, after)
        self.assertEqual(after[parent]["cls"], "WoodenCrate")
        self.assertEqual(after[f_eid]["parent"], child)

    def test_hijo_de_segunda_escena_dentro_de_obj_16_retiene_obj_16(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        self._applied(env)
        world.seed_scene("d-5ec00002", [["obj-01", "WoodenCrate", 6100.0, 7600.0, 0.0]])
        sec_child = world.spawn_own_child("d-5ec00002", "obj-01", "FirstAidKit", "obj-51")
        world.move_inside(sec_child, (DOC_ID, "obj-16"))
        r = env.reset()
        op = env.wait_state(r["op_id"], "parcial")
        self.assertEqual(op.get("reason"), "contenido_ajeno")
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 1)
        self.assertEqual(own[0]["cls"], "WoodenCrate")
        self.assertIn(sec_child, [c["eid"] for c in world.census()])

    def test_apply_con_contenedor_retenido_fallido_sin_cambios(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        self._applied(env)
        world.spawn_foreign("FirstAidKit", 6140.0, 7676.0, 200.0, inside="obj-17")
        before = world.census()
        r = env.apply()
        op = env.wait_state(r["op_id"], "fallido")
        self.assertEqual(op.get("reason"), "foreign_content_retained")
        self.assertEqual(world.census(), before)

    def test_toctou_barrera_en_apply_y_reset(self):
        env = self.make_env()
        world = FakeWorld()
        fake = self.start(env, world=world)
        self._applied(env)
        # apply detenido por retencion a mitad de su reset
        world.barrier_after(8)
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(world.wait_barrier_reached(8))
        world.spawn_foreign("FirstAidKit", 6140.0, 7676.0, 200.0, inside="obj-17")
        world.release_barrier()
        op = wait_op(env, op_id, "parcial", "contenido_ajeno")
        self.assertEqual(world.effects(fake.server.session, op_id)["created"], 0)
        self.assertNotEqual(len(world.census()), 34)
        # reset detenido por retencion a mitad de su borrado
        world.clear_faults()
        r2 = env.reset()
        self.assertTrue(world.wait_barrier_reached(8))
        # el ajeno ya esta dentro de obj-17; el reset debe retenerlo
        world.release_barrier()
        op2 = wait_op(env, r2["op_id"], "parcial", "contenido_ajeno")

    def test_fail_delete_en_reset_y_apply(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        self._applied(env)
        # fail_delete en obj-02 (se borra despues de obj-01): reset interrumpido
        world.fail_delete("obj-02")
        r = env.reset()
        op = wait_op(env, r["op_id"], "parcial", "interrumpida")
        self.assertTrue(any(c["cls"] == "Land_Wreck_Volha_Police"
                            for c in world.census()))
        snap = world.registry_snapshot()
        self.assertTrue(any(rec["lid"] == "obj-02" for rec in snap))
        # apply: no crea nada y el censo nunca llega a 34
        world.clear_faults()
        # reponer la generacion para el apply
        r = env.apply()
        env.wait_state(r["op_id"], "observado")
        world.fail_delete("obj-02")
        r2 = env.apply()
        op2 = wait_op(env, r2["op_id"], "parcial", "interrumpida")
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertLessEqual(len(own), 33)
        # fail_delete en obj-01, primer borrado: rechazo sin efecto. El apply
        # anterior ya borro obj-01, asi que antes se repone la escena entera.
        world.clear_faults()
        r = env.apply()
        env.wait_state(r["op_id"], "observado")
        world.fail_delete("obj-01")
        before = world.census()
        r3 = env.apply()
        op3 = env.wait_state(r3["op_id"], "fallido")
        self.assertEqual(op3.get("reason"), "delete_failed")
        self.assertEqual(world.census(), before)

    def test_reset_con_epoch_viejo_tras_restart_mission(self):
        env = self.make_env()
        world = FakeWorld()
        fake = self.start(env, world=world)
        self._applied(env)
        old_epoch = fake.epoch
        fake.restart_mission()
        self.assertTrue(wait_until(lambda: env.bridge.reconciled, 10))
        before = world.census()
        srv = fake.server
        order = {
            "op_id": "op-stale-reset", "session": srv.session, "conn": srv.conn,
            "epoch": old_epoch, "inst": srv.inst, "verb": "scene.reset",
            "args": {"doc_id": DOC_ID}, "issued_ms": int(time.monotonic() * 1000),
            "ttl_ms": 4000,
        }
        srv.handle_order(order, now_ms=order["issued_ms"])
        entry = wait_until(
            lambda: next((e for e in srv.cache.values()
                          if e.order["op_id"] == "op-stale-reset"
                          and e.state == "terminada"), None), 8)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.result.get("status"), "rejected")
        self.assertEqual(entry.result.get("reason"), "stale_epoch")
        self.assertEqual(world.census(), before)


class F2A4Restart(LiveBase):
    def test_mismo_fichero_y_epoch_nuevo(self):
        shared = tempfile.mkdtemp(prefix="dsbx-f2-shared-")
        self.addCleanup(shutil.rmtree, shared, True)
        env1 = self.make_env(dir=shared, remove_dir=False)
        fake = self.start(env1, world=FakeWorld())
        r1 = env1.apply()
        self.assertTrue(r1.get("ok"), r1)
        env1.wait_state(r1["op_id"], "observado")
        hash1 = env1.snap()["hash"]
        env1.close()
        env2 = self.make_env(dir=shared, remove_dir=False)
        fake.reconnect("http://127.0.0.1:%d" % env2.bridge.port)
        self.assertTrue(wait_until(lambda: env2.bridge.reconciled, 12))
        r2 = env2.apply()
        self.assertTrue(r2.get("ok"), r2)
        env2.wait_state(r2["op_id"], "observado")
        self.assertEqual(env2.snap()["hash"], hash1)
        own = [c for c in fake.world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 33)
        doc = _doc_without_actors()
        for c in own:
            if c["cls"].startswith("Zmb") or c["cls"].startswith("Animal_"):
                continue
            best = min(
                dist3(c["pos"], (e["x"], fake.world.ground_y(e["x"], e["z"]), e["z"]))
                for e in doc["entities"] if e["cls"] == c["cls"])
            self.assertLess(best, POS_TOL_M - 0.002, c["cls"])
        # epoch nuevo: registro vacio justo despues y apply nuevo sin extras
        fake.restart_mission()
        self.assertEqual(fake.world.registry_snapshot(), [])
        self.assertTrue(wait_until(lambda: env2.bridge.reconciled, 12))
        r3 = env2.apply()
        self.assertTrue(r3.get("ok"), r3)
        env2.wait_state(r3["op_id"], "observado")
        own = [c for c in fake.world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 33)

    def test_resultado_perdido_y_backend_reiniciado_33_no_66(self):
        shared = tempfile.mkdtemp(prefix="dsbx-f2-shared-")
        self.addCleanup(shutil.rmtree, shared, True)
        env1 = self.make_env(dir=shared, remove_dir=False)
        fake = self.start(env1, world=FakeWorld())
        fake.server.drop_all_results = True
        r1 = env1.apply()
        self.assertTrue(r1.get("ok"), r1)
        self.assertTrue(wait_until(
            lambda: fake.world.effects(fake.server.session, r1["op_id"])["created"] == 33, 10))
        env1.close()
        env2 = self.make_env(dir=shared, remove_dir=False)
        fake.server.drop_all_results = False
        fake.reconnect("http://127.0.0.1:%d" % env2.bridge.port)
        self.assertTrue(wait_until(lambda: env2.bridge.reconciled, 12))
        r2 = env2.apply()
        self.assertTrue(r2.get("ok"), r2)
        env2.wait_state(r2["op_id"], "observado")
        own = [c for c in fake.world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 33)

    def test_parcial_de_epoch_viejo_no_compensa_ni_observa(self):
        env = self.make_env(bridge_kwargs={"ttl_ms": 1200})
        fake = self.start(env, world=FakeWorld())
        fake.server.drop_all_results = True
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(wait_until(
            lambda: fake.world.effects(fake.server.session, op_id)["created"] == 33, 10))
        self.assertTrue(wait_until(lambda: time.monotonic() > 0, 1))
        time.sleep(1.3)
        env.bridge.sweep()
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "sin_resultado"))
        fake.server.drop_all_results = False
        fake.restart_mission()
        self.assertTrue(wait_until(lambda: env.bridge.reconciled, 12))
        time.sleep(0.5)
        op = env.op(op_id)
        self.assertEqual(op["state"], "parcial")
        self.assertEqual(op["reason"], "mundo_reiniciado")
        self.assertFalse(env.live.has_unresolved_locked())
        self.assertEqual(env.f2_internals(), [])


class F2CCompensation(LiveBase):
    def test_fail_create_fila_12_compensada_y_segunda_escena_intacta(self):
        env = self.make_env()
        world = FakeWorld()
        fake = self.start(env, world=world)
        world.seed_scene("d-5ec00003", [["obj-01", "WoodenCrate", 6100.0, 7600.0, 0.0]])
        second_before = {c["eid"]: copy.deepcopy(c) for c in world.census()
                         if c["scene"] == "d-5ec00003"}
        world.fail_create("obj-12")
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        op_id = r["op_id"]
        op = wait_op(env, op_id, "parcial", "compensada", timeout=15)
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(own, [])
        self.assertEqual(world.effects(fake.server.session, op_id)["created"], 11)
        after = {c["eid"]: c for c in world.census()}
        for eid, row in second_before.items():
            self.assertIn(eid, after)
            self.assertEqual(after[eid]["pos"], row["pos"])

    def test_lease_caducado_con_barrera_y_compensacion_del_backend(self):
        env = self.make_env()
        world = FakeWorld()
        fake = self.start(env, world=world)
        world.barrier_after(5)
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(world.wait_barrier_reached(8))
        fake.cut_polls("server", 1500)
        self.assertTrue(wait_until(lambda: (fake.server.lease_age_ms() or 0) > 700, 5))
        world.release_barrier()
        op = env.wait_state(op_id, "parcial", timeout=12)
        self.assertIn(op.get("reason"), ("lease_expired", "conexion_perdida"), op)
        # el backend compensa (if_pending) y termina compensada
        self.assertTrue(wait_until(
            lambda: (env.op(op_id)["state"], env.op(op_id)["reason"])
            == ("parcial", "compensada"), 15), env.op(op_id))
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(own, [])
        self.assertEqual(world.effects(fake.server.session, op_id)["created"], 5)

    def test_fail_delete_permanente_limite_de_compensaciones(self):
        # con el barrido en marcha, como en produccion: la lectura que sigue a una
        # compensacion fallida la pide el calendario de F1b-bridge §4 (§4.5)
        env = self.make_env(bridge_kwargs={"enable_sweeper": True, "sweep_ms": 25})
        world = FakeWorld()
        fake = self.start(env, world=world)
        world.barrier_after(5)
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(world.wait_barrier_reached(8))
        # antes de soltar: ninguna compensacion puede adelantarse al fallo
        world.fail_delete("obj-03")
        fake.cut_polls("server", 1500)
        self.assertTrue(wait_until(lambda: (fake.server.lease_age_ms() or 0) > 700, 5))
        world.release_barrier()
        env.wait_state(op_id, "parcial", timeout=12)
        self.assertTrue(wait_until(
            lambda: (env.op(op_id)["state"], env.op(op_id)["reason"])
            == ("parcial", "interrumpida"), 20), env.op(op_id))
        self.assertEqual(env.op(op_id)["origin"], "backend")
        order = env.bridge.orders.get((env.bridge.session, op_id))
        self.assertGreaterEqual(order.get("compensations", 0), 1)
        self.assertLessEqual(order.get("compensations", 0), 3)
        # sin mas ordenes: ninguna interna F2 en vuelo y el total no crece
        n_internal = len(env.f2_internals())
        time.sleep(0.6)
        self.assertEqual(len(env.f2_internals()), n_internal)
        self.assertEqual([o["op_id"] for o in env.f2_internals()
                          if o["bstate"] in ("pendiente", "ejecutando")], [])
        # M1: la compensacion borra en el orden del registro (obj-01, obj-02) y
        # para en obj-03; quedan obj-03, obj-04 y obj-05
        own = sorted(c["cls"] for c in world.census()
                     if c["origin"] == "sandbox" and c["scene"] == DOC_ID)
        self.assertEqual(own, sorted(["Land_Wreck_V3S", "Land_Wreck_Volha_Blue",
                                      "Land_Container_1Bo"]))

    def test_compensacion_con_otro_if_pending_rejected_sin_efecto(self):
        env = self.make_env()
        world = FakeWorld()
        fake = self.start(env, world=world)
        r = env.apply()
        env.wait_state(r["op_id"], "observado")
        before = world.census()
        srv = fake.server
        order = {
            "op_id": "op-ifp", "session": srv.session, "conn": srv.conn,
            "epoch": fake.epoch, "inst": srv.inst, "verb": "scene.reset",
            "args": {"doc_id": DOC_ID,
                     "if_pending": {"session": srv.session, "op_id": "op-999"}},
            "issued_ms": int(time.monotonic() * 1000), "ttl_ms": 4000,
        }
        srv.handle_order(order, now_ms=order["issued_ms"])
        entry = wait_until(
            lambda: next((e for e in srv.cache.values()
                          if e.order["op_id"] == "op-ifp" and e.state == "terminada"), None),
            8)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.result.get("status"), "rejected")
        self.assertEqual(entry.result.get("reason"), "not_pending")
        self.assertEqual(world.census(), before)

    def test_registros_de_otra_orden_sobreviven_a_la_compensacion(self):
        # Mundo sin red: pending de A con 5, se siembra B de la misma escena,
        # y la compensacion if_pending de A no borra B (X4-ah / F2-05).
        world = FakeWorld()
        doc = _doc_without_actors()
        plan = build_plan(doc, rev=1, hash=hash_doc(doc),
                          caps={"objeto": 20, "infectado": 10, "animal": 3})
        calls = {"n": 0}

        def check():
            calls["n"] += 1
            return "lease_expired" if calls["n"] > 5 else None

        order = {"op_id": "op-A", "session": "a" * 16, "epoch": world.epoch,
                 "verb": "scene.apply", "args": plan}
        st, rsn, rd = world.apply(order, check=check, tick=lambda: None)
        self.assertEqual(st, "error", rsn)
        self.assertEqual(rd["scene"]["pending"]["op_id"], "op-A")
        self.assertEqual(rd["scene"]["pending"]["n"], 5)
        world.seed_record(DOC_ID, "obj-99", "WoodenCrate", 6300.0, 7700.0,
                          "b" * 16, "op-B")
        reset_order = {"op_id": "op-comp", "session": "a" * 16,
                       "epoch": world.epoch, "verb": "scene.reset",
                       "args": {"doc_id": DOC_ID,
                                "if_pending": {"session": "a" * 16, "op_id": "op-A"}}}
        st, rsn, rd = world.reset(reset_order, check=lambda: None, tick=lambda: None)
        self.assertEqual(st, "done", rsn)
        self.assertEqual(rd["scene"]["last"]["outcome"], "compensated")
        self.assertIsNone(rd["scene"]["pending"])
        snap = world.registry_snapshot()
        self.assertEqual([r["lid"] for r in snap], ["obj-99"])
        self.assertTrue(any(c["cls"] == "WoodenCrate" for c in world.census()))

    def test_predicados_de_compensacion_negativos(self):
        order = {"session": "a" * 16, "op_id": "op-A", "epoch": "e" * 32,
                 "verb": "scene.apply", "args": {"doc_id": DOC_ID}}
        other_gen = {"session": "b" * 16, "op_id": "op-B", "rev": 1,
                     "hash": "0" * 64, "plan_sha256": "0" * 64}
        last = {"session": "a" * 16, "op_id": "op-A",
                "verb": "scene.apply", "outcome": "retained"}
        read = self.scene_read("e" * 32, generation=other_gen, n=1,
                               retained_n=1, retained=["obj-17"], last=last)
        self.assertEqual(evaluate_compensation_predicate(order, read),
                         ("fallido", "lectura_no_cumple"))
        read = self.scene_read("e" * 32, generation=None, n=1,
                               retained_n=1, retained=[], last=last)
        self.assertEqual(evaluate_compensation_predicate(order, read),
                         ("fallido", "lectura_no_cumple"))
        read = self.scene_read("e" * 32, generation=None, n=0,
                               retained_n=0, retained=[],
                               last={"session": "a" * 16, "op_id": "op-A",
                                     "verb": "scene.apply", "outcome": "compensated"})
        self.assertEqual(evaluate_compensation_predicate(order, read),
                         ("parcial", "compensada"))


class F2RReconcile(LiveBase):
    def test_reset_perdido_reconciliado_observado(self):
        env = self.make_env(bridge_kwargs={"ttl_ms": 1200})
        world = FakeWorld()
        fake = self.start(env, world=world)
        r = env.apply()
        env.wait_state(r["op_id"], "observado")
        fake.server.drop_all_results = True
        r2 = env.reset()
        op_id = r2["op_id"]
        self.assertTrue(wait_until(
            lambda: world.effects(fake.server.session, op_id)["deleted"] == 33, 10))
        time.sleep(1.3)
        env.bridge.sweep()
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "sin_resultado"))
        # el resultado del reset se pierde para siempre; las lecturas, no
        fake.server.drop_results_for.add(op_id)
        fake.server.drop_all_results = False
        op = env.wait_state(op_id, "observado", timeout=15)
        self.assertEqual(op.get("reason"), "reconciliada")
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(own, [])

    def test_apply_perdido_reconciliado_por_checkpoint(self):
        env = self.make_env(bridge_kwargs={"ttl_ms": 1200})
        world = FakeWorld()
        fake = self.start(env, world=world)
        fake.server.drop_all_results = True
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(wait_until(
            lambda: world.effects(fake.server.session, op_id)["created"] == 33, 10))
        time.sleep(1.3)
        env.bridge.sweep()
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "sin_resultado"))
        # el resultado del apply se pierde para siempre; las lecturas, no. Si
        # llegara tarde, seria el primer resultado y daria `observado` sin reason (§4.4)
        fake.server.drop_results_for.add(op_id)
        fake.server.drop_all_results = False
        op = env.wait_state(op_id, "observado", timeout=20)
        self.assertEqual(op.get("reason"), "reconciliada")
        own = [c for c in world.census()
               if c["origin"] == "sandbox" and c["scene"] == DOC_ID]
        self.assertEqual(len(own), 33)

    def test_orden_de_la_conn_anterior_del_mismo_epoch_se_resuelve(self):
        env = self.make_env(bridge_kwargs={"ttl_ms": 1200})
        world = FakeWorld()
        fake = self.start(env, world=world)
        fake.server.drop_all_results = True
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(wait_until(
            lambda: world.effects(fake.server.session, op_id)["created"] == 33, 10))
        time.sleep(1.3)
        env.bridge.sweep()
        self.assertEqual(env.op(op_id)["state"], "parcial")
        fake.server.drop_all_results = False
        fake.restart_peer("server")
        self.assertTrue(wait_until(lambda: env.bridge.reconciled, 12))
        op = env.wait_state(op_id, "observado", timeout=20)
        self.assertEqual(op.get("reason"), "reconciliada")

    def test_reconciliacion_no_da_observado_por_identidad_sola(self):
        env = self.make_env(bridge_kwargs={"ttl_ms": 1200})
        world = FakeWorld()
        fake = self.start(env, world=world)
        world.displace_on_create("obj-03", 0.6)
        fake.server.drop_all_results = True
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(wait_until(
            lambda: world.effects(fake.server.session, op_id)["created"] == 33, 10))
        time.sleep(1.3)
        env.bridge.sweep()
        self.assertEqual(env.op(op_id)["state"], "parcial")
        fake.server.drop_all_results = False
        op = env.wait_state(op_id, "fallido", timeout=20)
        self.assertEqual(op.get("reason"), "lectura_no_cumple")
        self.assertNotIn("observado", [e["state"] for e in env.events_for(op_id)])

    def test_negativos_de_predicados_de_reset_y_apply(self):
        # last/done con restos (n=1) -> fallido/lectura_no_cumple (X4-ag)
        order = {"session": "a" * 16, "op_id": "op-r", "epoch": "e" * 32,
                 "verb": "scene.reset", "args": {"doc_id": DOC_ID}}
        last = {"session": "a" * 16, "op_id": "op-r",
                "verb": "scene.reset", "outcome": "done"}
        read = self.scene_read("e" * 32, n=1, last=last)
        self.assertEqual(evaluate_reset_predicate(order, read),
                         ("fallido", "lectura_no_cumple"))
        read = self.scene_read("e" * 32, n=0, last=last)
        self.assertEqual(evaluate_reset_predicate(order, read), ("observado", None))
        # otra rev/hash/plan_sha en la generacion -> fallido (F1b-bridge B2-02)
        order_a = {
            "session": "a" * 16, "op_id": "op-1", "epoch": "e" * 32,
            "verb": "scene.apply",
            "args": {"doc_id": DOC_ID, "rev": 1, "hash": "0" * 64,
                     "plan_sha256": "0" * 64, "classes": ["WoodenCrate"],
                     "rows": [["obj-01", 0, 0.0, 0.0, 0.0]]},
            "expectation": {"obj-01": ("WoodenCrate", 0.0, 0.0)},
        }
        good = self.scene_read(
            "e" * 32, generation={"session": "a" * 16, "op_id": "op-1", "rev": 1,
                                  "hash": "0" * 64, "plan_sha256": "0" * 64},
            n=1, last={"session": "a" * 16, "op_id": "op-1",
                       "verb": "scene.apply", "outcome": "done"},
            obs_at="checkpoint",
            rows=[["obj-01", 0, 0.0, 0.0, 0.0, 0.0, 0.0]])
        self.assertTrue(check_apply_predicate(order_a, good))
        bad = copy.deepcopy(good)
        bad["generation"]["rev"] = 2
        self.assertFalse(check_apply_predicate(order_a, bad))
        bad = copy.deepcopy(good)
        bad["generation"]["hash"] = "1" * 64
        self.assertFalse(check_apply_predicate(order_a, bad))
        bad = copy.deepcopy(good)
        bad["generation"]["plan_sha256"] = "1" * 64
        self.assertFalse(check_apply_predicate(order_a, bad))

    def test_parcial_resuelto_no_mantiene_lecturas_vivas(self):
        env = self.make_env()
        world = FakeWorld()
        self.start(env, world=world)
        world.fail_create("obj-12")
        r = env.apply()
        op = wait_op(env, r["op_id"], "parcial", "compensada", timeout=15)
        self.assertFalse(env.live.has_unresolved_locked())
        self.assertFalse(env.bridge._has_live_parcial_locked())
        self.assertEqual(env.f2_internals(), [])


class F2OObserve(LiveBase):
    def test_observe_sse_get_age_y_movimiento(self):
        clock = FakeClock()
        # el salto de 5 s del reloj inyectado no debe parecer un servidor perdido
        env = self.make_env(clock=clock, bridge_kwargs={"lease_ms": 60000})
        world = FakeWorld()
        self.start(env, world=world)
        r = env.apply()
        env.wait_state(r["op_id"], "observado")
        st, resp = env.http("POST", "/api/observe", {"doc_id": DOC_ID})
        self.assertEqual(st, 200, resp)
        self.assertTrue(resp.get("ok"), resp)
        read_id = resp["read_id"]
        self.assertTrue(wait_until(
            lambda: (getattr(env.backend, "observation", None) or {}).get("read_id") == read_id, 10))
        obs = env.backend.observation
        self.assertEqual(obs["origin"], "servidor")
        self.assertEqual(obs["doc_id"], DOC_ID)
        rows = {row[0]: row for row in obs["rows"]}
        self.assertIn("obj-01", rows)
        x_before = rows["obj-01"][1]
        # el evento SSE scene.observation esta en el anillo
        kinds = [json.loads(data).get("read_id") for _s, kind, data in env.backend.ring
                 if kind == "scene.observation"]
        self.assertIn(read_id, kinds)
        st, resp = env.http("GET", "/api/observation")
        self.assertEqual(st, 200, resp)
        self.assertTrue(resp.get("ok"), resp)
        age0 = resp["age_ms"]
        self.assertIsNotNone(age0)
        clock.advance(5.0)
        st, resp = env.http("GET", "/api/observation")
        self.assertEqual(st, 200, resp)
        self.assertEqual(resp["age_ms"], age0 + 5000)
        # mover 2 m y volver a observar: la fila now lo refleja
        world.move_entity((DOC_ID, "obj-01"), dx=2.0)
        st, resp = env.http("POST", "/api/observe", {"doc_id": DOC_ID})
        self.assertEqual(st, 200, resp)
        read_id2 = resp["read_id"]
        self.assertNotEqual(read_id2, read_id)
        self.assertTrue(wait_until(
            lambda: (getattr(env.backend, "observation", None) or {}).get("read_id") == read_id2, 10))
        rows2 = {row[0]: row for row in env.backend.observation["rows"]}
        self.assertAlmostEqual(rows2["obj-01"][1] - x_before, 2.0, places=2)

    def test_sin_peer_con_escena_409_y_sin_ordenes(self):
        env = self.make_env()
        self.start(env, world=None)
        before = len(env.orders(verb="scene.observe"))
        st, resp = env.http("POST", "/api/observe", {"doc_id": DOC_ID})
        self.assertEqual(st, 409, resp)
        self.assertEqual(resp.get("code"), "scene_unsupported")
        self.assertEqual(len(env.orders(verb="scene.observe")), before)


class F2D1Contract(LiveBase):
    def test_peer_sin_scene_recibe_orden_f1_y_state_read_vacio(self):
        env = self.make_env()
        self.start(env, world=None)
        r = env.apply()
        self.assertTrue(r.get("ok"), r)
        op_id = r["op_id"]
        env.wait_state(op_id, "observado")
        order = next(o for o in env.orders(verb="scene.apply", internal=False)
                     if o["op_id"] == op_id)
        self.assertEqual(set(order["args"].keys()), {"doc_id", "rev", "hash"})
        reads = env.orders(verb="state.read", internal=True)
        self.assertTrue(reads)
        for o in reads:
            self.assertEqual(o["args"], {})
        self.assertFalse(env.live.server_has_scene_locked())

    def test_parcial_f2_sigue_parcial_si_el_servidor_vuelve_sin_scene(self):
        env = self.make_env(bridge_kwargs={"ttl_ms": 1200})
        world = FakeWorld()
        fake = self.start(env, world=world)
        fake.server.drop_all_results = True
        r = env.apply()
        op_id = r["op_id"]
        self.assertTrue(wait_until(
            lambda: world.effects(fake.server.session, op_id)["created"] == 33, 10))
        time.sleep(1.3)
        env.bridge.sweep()
        self.assertEqual((env.op(op_id)["state"], env.op(op_id)["reason"]),
                         ("parcial", "sin_resultado"))
        order = env.bridge.orders.get((env.bridge.session, op_id))
        # una lectura que casaria con la identidad F1, pero sin scene ni checkpoint
        fake._set_generation({
            "session": order["session"], "op_id": order["op_id"],
            "rev": order["args"]["rev"], "hash": order["args"]["hash"],
        })
        fake.server.drop_all_results = False
        fake.world = None
        fake.restart_peer("server")
        self.assertTrue(wait_until(lambda: env.bridge.reconciled, 12))
        time.sleep(0.5)
        op = env.op(op_id)
        self.assertEqual(op["state"], "parcial")
        self.assertNotIn("observado", [e["state"] for e in env.events_for(op_id)])


if __name__ == "__main__":
    unittest.main()
