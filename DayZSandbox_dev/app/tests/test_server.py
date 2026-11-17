"""Pruebas del servidor F1a: T9-T12 y E1 (brief §6)."""
import copy
import hashlib
import http.client
import io
import json
import os
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

ROOT = Path(__file__).resolve().parents[2]  # DayZSandbox_dev/
FIXTURES = ROOT / "fixtures"
HK, AK = "clave-persona-de-prueba-1234567890", "clave-ia-de-prueba-0987654321"


def doc_hash(doc):
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class Env:
    """Un servidor en un hilo con puerto 0 sobre una escena temporal."""

    def __init__(self, horizon=1000):
        self.dir = tempfile.mkdtemp(prefix="dsbx-srv-")
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)
        self.store = Store(os.path.join(self.dir, "scene.json"), catalog)
        self.log = io.StringIO()
        self.backend = Backend(self.store, HK, AK, port=0, horizon=horizon, log=self.log)
        self.port = self.backend.port
        self.thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.thread.start()
        self.n = 0
        self.bodies = []

    def close(self):
        self.backend.shutdown()
        shutil.rmtree(self.dir, ignore_errors=True)

    def req(self, method, path, body=None, key=HK, host=None, origin=None, raw=None, length=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host or "127.0.0.1:%d" % self.port)
        if origin:
            conn.putheader("Origin", origin)
        if key:
            conn.putheader("Authorization", "Bearer " + key)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(len(data) if length is None else length))
        conn.endheaders(data)
        resp = conn.getresponse()
        text = resp.read().decode("utf-8")
        conn.close()
        self.bodies.append(text)
        return resp.status, json.loads(text)

    def scene(self):
        return self.req("GET", "/api/scene")[1]

    def ops(self, ops, key=HK, base_rev=None, label=None, extra=None, **kw):
        snap = self.store.snapshot()
        self.n += 1
        body = {"doc_id": snap["doc_id"], "request_id": "r-%d-%f" % (self.n, time.time()),
                "base_rev": snap["rev"] if base_rev is None else base_rev, "label": label, "ops": ops}
        body.update(extra or {})
        return self.req("POST", "/api/scene/ops", body, key=key, **kw)


def move(target, x, z):
    return {"name": "entity.move", "target": target, "args": {"x": x, "z": z}}


def fog(v):
    return {"name": "ambient.set", "args": {"niebla": v}}


class Sse:
    """Cliente SSE mínimo sobre http.client."""

    def __init__(self, env, last_id=None, key=HK):
        self.conn = http.client.HTTPConnection("127.0.0.1", env.port, timeout=10)
        headers = {"Authorization": "Bearer " + key}
        if last_id is not None:
            headers["Last-Event-ID"] = str(last_id)
        self.conn.request("GET", "/api/events", headers=headers)
        self.resp = self.conn.getresponse()
        assert self.resp.status == 200, self.resp.status

    def next(self):
        ev = {}
        while True:
            line = self.resp.fp.readline()
            if not line:
                raise EOFError("flujo cerrado")
            line = line.decode("utf-8").rstrip("\n")
            if line == "":
                if "event" in ev:
                    return ev
                ev = {}
                continue
            if line.startswith(":"):
                continue
            k, _, v = line.partition(": ")
            ev[k] = int(v) if k == "id" else json.loads(v) if k == "data" else v

    def take(self, n, kind=None):
        out = []
        while len(out) < n:
            ev = self.next()
            if kind is None or ev["event"] == kind:
                out.append(ev)
        return out

    def close(self):
        try:
            self.resp.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass
        self.conn.close()


class Base(unittest.TestCase):
    horizon = 1000

    def setUp(self):
        self.env = Env(self.horizon)
        self.first = self.env.store.snapshot()

    def tearDown(self):
        self.env.close()
        for text in self.env.bodies + [self.env.log.getvalue()]:
            self.assertNotIn(HK, text)
            self.assertNotIn(AK, text)

    def entity(self, doc, eid):
        return next(e for e in doc["entities"] if e["id"] == eid)


class T9Autor(Base):
    def test_credencial_ia_firma_la_tanda(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        st, r = self.env.ops([fog(0.2)], key=AK)
        self.assertEqual((st, r["ok"]), (200, True))
        ev = sse.take(1, "scene.commit")[0]
        sse.close()
        self.assertEqual(ev["data"]["author"]["role"], "ai")
        self.assertEqual(ev["data"]["rev"], r["rev"])

    def test_autor_del_cuerpo_que_no_casa(self):
        st, r = self.env.ops([fog(0.2)], key=AK, extra={"author": {"role": "human", "id": "web"}})
        self.assertEqual((st, r["code"]), (403, "author_mismatch"))
        self.assertEqual(self.env.store.snapshot(), self.first)

    def test_autor_del_cuerpo_que_casa_se_ignora(self):
        st, r = self.env.ops([fog(0.2)], key=AK, extra={"author": {"role": "ai", "id": "mcp"}})
        self.assertEqual((st, r["ok"]), (200, True))


class T10PausaYToma(Base):
    def test_sin_pausa_ni_toma_la_ia_confirma(self):
        st, r = self.env.ops([fog(0.3)], key=AK)
        self.assertEqual((st, r["ok"]), (200, True))

    def test_pausa_por_endpoint(self):
        st, r = self.env.req("POST", "/api/ai/pause", {"paused": True})
        self.assertEqual((st, r["paused"]), (200, True))
        st, r = self.env.ops([fog(0.3)], key=AK)
        self.assertEqual((st, r["code"]), (409, "ai_paused"))
        self.assertEqual(self.env.store.snapshot(), self.first)
        st, r = self.env.ops([move("obj-01", 6190.0, 7627.0)])
        self.assertEqual((st, r["ok"]), (200, True))

    def test_pausa_mientras_una_tanda_de_la_ia_espera_en_el_gate(self):
        # El gate corre dentro del candado: la pausa no puede colarse en medio. O la
        # tanda entra antes de la pausa o la pausa la rechaza; nunca hay un commit de
        # la IA con seq posterior al evento ai.state de la pausa.
        inside, release = threading.Event(), threading.Event()
        real_gate = self.env.store.gate

        def slow_gate(author):
            if author["role"] == "ai":
                inside.set()
                release.wait(5)
            return real_gate(author)

        self.env.store.gate = slow_gate
        sse = Sse(self.env, last_id=self.env.backend.seq)
        out = {}
        t_ai = threading.Thread(target=lambda: out.setdefault("ai", self.env.ops([fog(0.4)], key=AK)))
        t_ai.start()
        self.assertTrue(inside.wait(5))
        t_pause = threading.Thread(target=lambda: out.setdefault(
            "pause", self.env.req("POST", "/api/ai/pause", {"paused": True})))
        t_pause.start()
        time.sleep(0.3)
        self.assertNotIn("pause", out)  # la pausa espera al candado
        release.set()
        t_ai.join(5)
        t_pause.join(5)
        self.env.store.gate = real_gate
        self.assertEqual(out["pause"][0], 200)
        events = sse.take(2)
        self.assertEqual([e["event"] for e in events], ["scene.commit", "ai.state"])
        st, r = self.env.ops([fog(0.5)], key=AK)  # después de la pausa, nada de la IA
        sse.close()
        self.assertEqual((st, r["code"]), (409, "ai_paused"))
        self.assertEqual(self.env.store.snapshot()["rev"], out["ai"][1]["rev"])

    def test_toma_armada_bloquea_a_los_dos(self):
        self.env.backend.take_state = "armada"
        for key in (HK, AK):
            st, r = self.env.ops([fog(0.3)], key=key)
            self.assertEqual((st, r["code"]), (409, "take_locked"))
        self.assertEqual(self.env.store.snapshot(), self.first)


class T11Aplicar(Base):
    def test_aplicar_la_revision_actual(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        snap = self.env.scene()
        st, r = self.env.req("POST", "/api/apply", {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.assertEqual((st, r["ok"]), (200, True))
        ev = sse.take(1, "op.state")[0]
        sse.close()
        self.assertEqual(ev["data"]["op_id"], r["op_id"])
        self.assertEqual((ev["data"]["state"], ev["data"]["rev"], ev["data"]["hash"]),
                         ("pendiente", snap["rev"], snap["hash"]))
        self.assertEqual(self.env.backend.ops[r["op_id"]]["state"], "pendiente")

    def test_tanda_de_la_ia_entre_leer_y_aplicar(self):
        snap = self.env.scene()
        self.assertTrue(self.env.ops([fog(0.25)], key=AK)[1]["ok"])
        st, r = self.env.req("POST", "/api/apply", {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.assertEqual((st, r["code"]), (409, "stale_apply"))
        self.assertEqual(self.env.backend.ops, {})

    def test_la_ia_no_aplica_ni_revierte_ni_pausa(self):
        snap = self.env.scene()
        st, r = self.env.ops([fog(0.25)], key=AK)
        batch = r["batch"]
        snap = self.env.scene()
        calls = [("/api/apply", {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]}),
                 ("/api/scene/batches/%s/revert" % batch, {"doc_id": snap["doc_id"], "request_id": "rv-1"}),
                 ("/api/ai/pause", {"paused": False})]
        for path, body in calls:
            st, r = self.env.req("POST", path, body, key=AK)
            self.assertEqual((st, r["code"]), (403, "forbidden"), path)
        self.assertEqual(self.env.store.snapshot(), snap)
        self.assertEqual(self.env.backend.ops, {})
        self.assertFalse(self.env.backend.paused)


class T12Sse(Base):
    def test_dos_clientes_y_cien_tandas_cruzadas(self):
        start = self.env.backend.seq
        a, b = Sse(self.env, last_id=start), Sse(self.env, last_id=start)

        def run(key, make):
            for i in range(50):
                st, r = self.env.ops([make(i)], key=key)
                self.assertEqual(st, 200, r)

        hum = threading.Thread(target=run, args=(HK, lambda i: move("obj-01", 6000.0 + i, 7000.0 + i)))
        ia = threading.Thread(target=run, args=(AK, lambda i: fog(round(i / 100, 2))))
        hum.start(), ia.start()
        hum.join(60), ia.join(60)
        ea, eb = a.take(100), b.take(100)
        a.close(), b.close()
        self.assertEqual(ea, eb)
        self.assertEqual([e["id"] for e in ea], list(range(start + 1, start + 101)))
        self.assertEqual({e["data"]["author"]["role"] for e in ea}, {"human", "ai"})
        doc = copy.deepcopy(self.first["doc"])
        rev = self.first["rev"]
        for e in ea:
            rec = e["data"]
            rev += 1
            self.assertEqual(rec["rev"], rev)
            for op in rec["ops"]:
                if op["name"] == "entity.move":
                    self.entity(doc, op["target"]).update(op["args"])
                else:
                    doc["ambiente"].update(op["args"])
            self.assertEqual(doc_hash(doc), rec["hash"], rev)
        self.assertEqual(self.env.store.snapshot()["hash"], doc_hash(doc))

    def test_reconectar_con_last_event_id(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        self.env.ops([fog(0.1)], key=AK)
        seen = sse.take(1)[0]
        sse.close()
        self.env.ops([move("obj-01", 6190.0, 7627.0)])
        snap = self.env.scene()
        self.env.req("POST", "/api/apply", {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.env.ops([fog(0.15)], key=AK)
        back = Sse(self.env, last_id=seen["id"])
        got = back.take(3)
        back.close()
        self.assertEqual([e["event"] for e in got], ["scene.commit", "op.state", "scene.commit"])
        self.assertEqual([e["id"] for e in got], [seen["id"] + 1, seen["id"] + 2, seen["id"] + 3])
        self.assertEqual(self.env.backend.seq, seen["id"] + 3)

    def test_id_futuro_o_ilegible_da_instantanea(self):
        for bad in (self.env.backend.seq + 5, "x"):
            s = Sse(self.env, last_id=bad)
            self.assertEqual(s.next()["event"], "snapshot")
            s.close()


class T12AnilloDesbordado(Base):
    horizon = 5

    def test_anillo_desbordado_da_instantanea_y_cada_commit_una_vez(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        old = None
        self.env.ops([fog(0.01)], key=AK)
        old = sse.take(1)[0]["id"]
        sse.close()
        for i in range(8):
            self.env.ops([fog(0.02 + i / 100)], key=AK)
        stop = threading.Event()

        def writer():
            i = 0
            while not stop.is_set():
                i += 1
                self.env.ops([move("obj-01", 6000.0 + i % 300, 7000.0)])

        t = threading.Thread(target=writer)
        t.start()
        try:
            back = Sse(self.env, last_id=old)
            snap = back.next()
            self.assertEqual(snap["event"], "snapshot")
            self.assertEqual(snap["data"]["doc_id"], self.first["doc_id"])
            commits = back.take(5, "scene.commit")
            back.close()
        finally:
            stop.set()
            t.join(10)
        revs = [snap["data"]["rev"]] + [c["data"]["rev"] for c in commits]
        self.assertEqual(revs, list(range(revs[0], revs[0] + 6)))  # ni hueco ni repetido
        self.assertEqual(commits[0]["id"], snap["id"] + 1)


class E1Credenciales(Base):
    def test_clave_host_y_origin_buenos(self):
        st, r = self.env.ops([fog(0.3)], origin="http://127.0.0.1:%d" % self.env.port)
        self.assertEqual((st, r["ok"]), (200, True))
        st, _ = self.env.req("GET", "/api/scene", host="localhost:%d" % self.env.port,
                             origin="http://localhost:%d" % self.env.port)
        self.assertEqual(st, 200)

    def test_rechazos_sin_efectos(self):
        port = self.env.port
        cases = [({"key": None}, 401), ({"key": "otra-clave"}, 401),
                 ({"host": "evil.test"}, 403), ({"origin": "http://evil.test"}, 403),
                 ({"host": "127.0.0.1:%d" % (port + 1)}, 403)]
        for kw, status in cases:
            st, r = self.env.ops([fog(0.3)], **kw)
            self.assertEqual(st, status, kw)
            self.assertFalse(r["ok"])
            st, _ = self.env.req("GET", "/api/scene", **kw)
            self.assertEqual(st, status, kw)
        self.assertEqual(self.env.store.snapshot(), self.first)

    def test_cuerpos_ilegibles(self):
        for raw in (b"{no es json", b"[1,2]", b"\xff\xfe"):
            st, r = self.env.req("POST", "/api/scene/ops", raw=raw)
            self.assertEqual((st, r["code"]), (400, "bad_request"))
        st, r = self.env.req("POST", "/api/scene/ops", raw=b"", length=1024 * 1024 + 1)
        self.assertEqual(st, 400)
        self.assertEqual(self.env.store.snapshot(), self.first)

    def test_solo_escucha_en_127(self):
        self.assertEqual(self.env.backend.httpd.server_address[0], "127.0.0.1")
        for ip in {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)} - {"127.0.0.1"}:
            with self.assertRaises(OSError):
                socket.create_connection((ip, self.env.port), timeout=1).close()


class ArranqueYClaves(unittest.TestCase):
    """`server.py --config`: genera claves sin imprimirlas y sale 2 con una escena ilegible."""

    def run_server(self, cfg_path, wait_line):
        script = ROOT / "app" / "backend" / "server.py"
        p = subprocess.Popen([sys.executable, str(script), "--config", str(cfg_path), "--port", "0"],
                             cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if wait_line:
            line = p.stdout.readline()
            p.terminate()
        else:
            line = ""
        out, err = p.communicate(timeout=20)
        return p.returncode, line + out + err

    def test_genera_claves_y_no_las_imprime(self):
        d = Path(tempfile.mkdtemp(prefix="dsbx-cfg-"))
        cfg = d / "backend.json"
        cfg.write_text(json.dumps({"scene": str(d / "scene.json"),
                                   "catalog": str(FIXTURES / "catalog-m1.json")}), encoding="utf-8")
        _, output = self.run_server(cfg, wait_line=True)
        keys = json.loads(cfg.read_text(encoding="utf-8"))
        shutil.rmtree(d, ignore_errors=True)
        self.assertIn("127.0.0.1", output)
        self.assertGreaterEqual(len(keys["human_key"]), 32)
        self.assertNotEqual(keys["human_key"], keys["ai_key"])
        self.assertNotIn(keys["human_key"], output)
        self.assertNotIn(keys["ai_key"], output)

    def test_escena_ilegible_sale_2_sin_sobrescribir(self):
        d = Path(tempfile.mkdtemp(prefix="dsbx-cfg-"))
        scene = d / "scene.json"
        scene.write_text("{roto", encoding="utf-8")
        cfg = d / "backend.json"
        cfg.write_text(json.dumps({"scene": str(scene), "catalog": str(FIXTURES / "catalog-m1.json"),
                                   "human_key": HK, "ai_key": AK}), encoding="utf-8")
        code, output = self.run_server(cfg, wait_line=False)
        left = scene.read_text(encoding="utf-8")
        shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(code, 2)
        self.assertEqual(left, "{roto")
        self.assertNotIn(HK, output)


if __name__ == "__main__":
    unittest.main()
