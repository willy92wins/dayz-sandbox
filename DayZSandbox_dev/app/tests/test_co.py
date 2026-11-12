"""F1-co §4: CO-1 (oráculo y p95), la fachada MCP y lo que cambió desde la última llamada."""
import copy
import json
import os
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from .test_server import AK, HK, Env, Sse, doc_hash, fog, move

ROOT = Path(__file__).resolve().parents[2]  # DayZSandbox_dev/
FACADE = ROOT / "app" / "mcp" / "facade.py"


class Oracle:
    """Copia propia del documento: aplica cada scene.commit (solo entity.move y ambient.set)
    y compara SU hash con el del evento. Devuelve la primera revisión rota o None."""

    def __init__(self, snap):
        self.doc = copy.deepcopy(snap["doc"])
        self.rev = snap["rev"]

    def paint(self, ops):  # un cliente que pinta lo que mandó, no lo que llegó
        for op in ops:
            if op["name"] == "entity.move":
                next(e for e in self.doc["entities"] if e["id"] == op["target"]).update(op["args"])
            else:
                self.doc["ambiente"].update(op["args"])

    def feed(self, rec):
        self.rev += 1
        if rec["rev"] != self.rev:
            return self.rev
        self.paint(rec["ops"])
        return None if doc_hash(self.doc) == rec["hash"] else self.rev

    def run(self, records):
        for rec in records:
            bad = self.feed(rec)
            if bad is not None:
                return bad
        return None


def p95(latencies, expected):
    """Percentil 95 por rango más cercano; lo perdido cuenta como > 1 s."""
    vals = sorted(list(latencies) + [float("inf")] * (expected - len(latencies)))
    return vals[max(0, -(-95 * expected // 100) - 1)]


class Mcp:
    """La fachada como subproceso, con stdin y stdout por tubería."""

    def __init__(self, env, cfg=None):
        self.cfg = os.path.join(env.dir, "backend-ai.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump(cfg if cfg is not None else {"port": env.port, "ai_key": AK}, f)
        self.p = subprocess.Popen([sys.executable, str(FACADE), "--config", self.cfg], cwd=str(ROOT),
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8")
        self.n = 0
        self.lines = []

    def send_raw(self, line):
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def read(self):
        line = self.p.stdout.readline()
        self.lines.append(line)
        return json.loads(line)

    def rpc(self, method, params=None):
        self.n += 1
        self.send_raw(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}))
        return self.read()

    def init(self):
        r = self.rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                    "clientInfo": {"name": "prueba", "version": "0"}})
        self.send_raw(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        return r

    def call(self, name, **args):
        r = self.rpc("tools/call", {"name": name, "arguments": args})
        return json.loads(r["result"]["content"][0]["text"]), r["result"]["isError"]

    def close(self):
        self.p.stdin.close()
        self.p.wait(10)
        err = self.p.stderr.read()
        self.p.stderr.close()
        self.p.stdout.close()
        return "".join(self.lines) + err


class Base(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.first = self.env.store.snapshot()
        self.mcp = None

    def tearDown(self):
        out = self.mcp.close() if self.mcp else ""
        self.env.close()
        for text in self.env.bodies + [self.env.log.getvalue(), out]:
            self.assertNotIn(HK, text)
            self.assertNotIn(AK, text)

    def start_mcp(self):
        self.mcp = Mcp(self.env)
        self.mcp.init()
        return self.mcp


class CO1Oraculo(unittest.TestCase):
    def setUp(self):
        self.snap = {"rev": 1, "doc": {"entities": [{"id": "obj-01", "x": 1.0, "z": 1.0}], "ambiente": {"niebla": 0.1}}}
        doc = copy.deepcopy(self.snap["doc"])
        self.records = []
        for i, op in enumerate([move("obj-01", 2.0, 2.0), fog(0.2), move("obj-01", 3.0, 3.0), fog(0.3)]):
            o = Oracle({"doc": doc, "rev": 0})
            o.paint([op])
            doc = o.doc
            self.records.append({"rev": 2 + i, "ops": [op], "hash": doc_hash(doc)})

    def test_flujo_bueno(self):
        self.assertIsNone(Oracle(self.snap).run(self.records))

    def test_dos_eventos_permutados(self):
        recs = copy.deepcopy(self.records)
        recs[0]["rev"], recs[2]["rev"] = recs[2]["rev"], recs[0]["rev"]
        recs[0], recs[2] = recs[2], recs[0]
        self.assertEqual(Oracle(self.snap).run(recs), 2)

    def test_tanda_rechazada_pintada(self):
        o = Oracle(self.snap)
        self.assertIsNone(o.feed(self.records[0]))
        o.paint([move("obj-01", 99.0, 99.0)])  # la IA recibió conflict, pero el cliente la pinta
        self.assertEqual(o.feed(self.records[1]), 3)

    def test_p95(self):
        fast = [0.01] * 100
        self.assertLess(p95(fast, 100), 0.2)
        slow = [0.01] * 90 + [0.31] * 10
        self.assertGreaterEqual(p95(slow, 100), 0.2)
        self.assertEqual(p95([0.01] * 94, 100), float("inf"))  # 6 perdidas cuentan como > 1 s


class CO1EnVivo(Base):
    def test_cien_operaciones_cruzadas(self):
        mcp = self.start_mcp()
        start = self.env.backend.seq
        web, ia = Sse(self.env, last_id=start), Sse(self.env, last_id=start, key=AK)
        sent = {}
        lock = threading.Lock()

        def human():
            for i in range(50):
                label = "persona-%d" % i
                with lock:
                    sent[label] = time.monotonic()
                st, r = self.env.ops([move("obj-01", 6000.0 + i, 7000.0)], label=label)
                self.assertEqual(st, 200, r)

        def ai():
            for i in range(50):
                label = "ia-%d" % i
                base = self.env.store.snapshot()["rev"]
                with lock:
                    sent[label] = time.monotonic()
                res, err = mcp.call("scene_ops", base_rev=base, label=label, ops=[fog(round(i / 100, 2))])
                self.assertFalse(err, res)

        got = {}

        def reader(name, sse):
            out = []
            while len(out) < 100:
                ev = sse.next()
                if ev["event"] == "scene.commit":
                    out.append((time.monotonic(), ev))
            got[name] = out

        readers = [threading.Thread(target=reader, args=(n, s)) for n, s in (("web", web), ("ia", ia))]
        for t in readers:
            t.start()
        writers = [threading.Thread(target=human), threading.Thread(target=ai)]
        for t in writers:
            t.start()
        for t in writers + readers:
            t.join(60)
        web.close(), ia.close()
        evw = [e for _, e in got["web"]]
        self.assertEqual(evw, [e for _, e in got["ia"]])
        self.assertIsNone(Oracle(self.first).run([e["data"] for e in evw]))
        lat = []
        for side, other in (("persona-", "ia"), ("ia-", "web")):
            for t, ev in got[other]:
                label = ev["data"]["label"]
                if label.startswith(side):
                    lat.append(t - sent[label])
        self.assertLess(p95(lat, 100), 0.2, "p95 %.3f s" % p95(lat, 100))
        snap = self.env.store.snapshot()
        res, _ = mcp.call("scene_get")
        self.assertEqual((res["result"]["rev"], res["result"]["hash"]), (snap["rev"], snap["hash"]))


class FachadaMcp(Base):
    def test_initialize_y_tools(self):
        mcp = Mcp(self.env)
        self.mcp = mcp
        r = mcp.init()
        self.assertEqual(r["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r["result"]["capabilities"])
        tools = mcp.rpc("tools/list")["result"]["tools"]
        self.assertEqual({t["name"] for t in tools},
                         {"scene_get", "scene_ops", "scene_validate", "scene_wait_changes", "apply_request"})
        for t in tools:
            self.assertEqual(t["inputSchema"]["type"], "object")
        self.assertEqual(mcp.rpc("ping")["result"], {})

    def test_errores_json_rpc(self):
        mcp = self.start_mcp()
        self.assertEqual(mcp.rpc("no/existe")["error"]["code"], -32601)
        mcp.send_raw("{esto no es json")
        self.assertEqual(mcp.read()["error"]["code"], -32700)
        self.assertEqual(mcp.rpc("ping")["result"], {})  # sigue viva
        for line in mcp.lines:
            json.loads(line)  # stdout solo lleva JSON-RPC

    def test_sin_ai_key_sale_con_2(self):
        cfg = os.path.join(self.env.dir, "solo-persona.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"port": self.env.port, "human_key": HK}, f)
        p = subprocess.run([sys.executable, str(FACADE), "--config", cfg], cwd=str(ROOT), input="",
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(p.returncode, 2)
        self.assertNotIn(HK, p.stdout + p.stderr)
        self.assertEqual(self.env.backend.seq, 0)  # ni una petición llegó a cambiar nada

    def test_cambios_desde_la_ultima_llamada(self):
        mcp = self.start_mcp()
        res, _ = mcp.call("scene_get")
        self.assertEqual(res["changes_since_last_call"], [])
        st, h = self.env.ops([move("obj-01", 6190.0, 7627.0)], label="persona mueve")
        self.assertEqual(st, 200)
        res, err = mcp.call("scene_ops", base_rev=res["result"]["rev"], label="ia gira",
                            ops=[{"name": "entity.set", "target": "obj-03", "args": {"yaw": 260}}])
        self.assertFalse(err, res)
        ch = res["changes_since_last_call"]
        self.assertEqual([(c["rev"], c["label"], c["author"]["role"]) for c in ch], [(h["rev"], "persona mueve", "human")])
        res, _ = mcp.call("scene_validate", base_rev=res["result"]["rev"], ops=[fog(0.3)])
        self.assertEqual(res["changes_since_last_call"], [])  # ni se repite lo humano ni sale lo de la IA

    def test_rechazo_del_backend_es_iserror(self):
        mcp = self.start_mcp()
        res, _ = mcp.call("scene_get")
        self.env.ops([move("obj-01", 6190.0, 7627.0)])
        res, err = mcp.call("scene_ops", base_rev=res["result"]["rev"], label=None, ops=[move("obj-01", 6100.0, 7600.0)])
        self.assertTrue(err)
        self.assertEqual(res["result"]["code"], "conflict")
        self.assertEqual(self.env.store.snapshot()["doc"], self.entity_doc_after_human())

    def entity_doc_after_human(self):
        doc = copy.deepcopy(self.first["doc"])
        next(e for e in doc["entities"] if e["id"] == "obj-01").update({"x": 6190.0, "z": 7627.0})
        return doc

    def test_apply_request_no_aplica(self):
        mcp = self.start_mcp()
        sse = Sse(self.env, last_id=self.env.backend.seq)
        res, _ = mcp.call("scene_get")
        r, err = mcp.call("apply_request", rev=res["result"]["rev"], hash=res["result"]["hash"])
        self.assertFalse(err, r)
        ev = sse.take(1, "apply.request")[0]
        sse.close()
        self.assertEqual((ev["data"]["rev"], ev["data"]["author"]["role"]), (res["result"]["rev"], "ai"))
        self.assertEqual(self.env.backend.ops, {})


if __name__ == "__main__":
    unittest.main()
