"""Pruebas del proxy de inyeccion de fallos (qa/live/fault_proxy.py).

Monta un bridge falso con las cuatro rutas del bridge real y ejercita cada
tipo de accion, las ventanas de then_cut_ms/then_hold_ms, los contadores
nth/count bajo concurrencia, la barrera de abort_inflight, el fichero activo
y la ausencia total de la clave en log, stdout y stderr.
"""

import http.client
import importlib.util
import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
FAULT_PROXY_PATH = os.path.abspath(os.path.join(HERE, "..", "live", "fault_proxy.py"))

_SPEC = importlib.util.spec_from_file_location("fault_proxy", FAULT_PROXY_PATH)
fault_proxy = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fault_proxy)


class FakeBridgeState:
    def __init__(self):
        self.lock = threading.Lock()
        self.requests = []
        self.retain_poll = False
        self.poll_gate = threading.Event()
        self.poll_gate.set()
        self.poll_arrived = threading.Event()

    def record(self, method, path):
        with self.lock:
            self.requests.append({"method": method, "path": path})

    def count(self):
        with self.lock:
            return len(self.requests)


class FakeBridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state = None

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
            self.wfile.flush()
        except OSError:
            self.close_connection = True

    def _query(self):
        return parse_qs(urlsplit(self.path).query)

    def _path(self):
        return urlsplit(self.path).path

    def do_GET(self):
        self.state.record("GET", self.path)
        if self._path() == "/poll":
            query = self._query()
            deliver = query.get("deliver", [None])[0]
            if self.state.retain_poll and deliver != "0":
                self.state.poll_arrived.set()
                self.state.poll_gate.wait(timeout=10)
            if deliver == "0":
                self._send_json(200, {"ok": True, "ops": []})
            else:
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "now_ms": 111,
                        "ops": [
                            {
                                "id": 1,
                                "session": "s",
                                "args": {"rev": 1},
                            }
                        ],
                    },
                )
        else:
            self._send_json(200, {"ok": True})

    def do_POST(self):
        self.state.record("POST", self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        path = self._path()
        if path == "/hello":
            self._send_json(200, {"ok": True, "hello": True, "ops": []})
        elif path == "/result":
            self._send_json(200, {"ok": True})
        elif path == "/catalog":
            self._send_json(200, {"ok": True})
        else:
            self._send_json(404, {"ok": False, "error": "bad_request"})


def request(port, method, path, body=None, timeout=8.0):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        if method == "POST":
            conn.request(
                "POST",
                path,
                body=body if body is not None else b"{}",
                headers={"Content-Type": "application/json"},
            )
        else:
            conn.request(method, path)
        response = conn.getresponse()
        data = response.read()
        return response.status, data
    finally:
        conn.close()


def request_or_none(port, method, path, body=None, timeout=8.0):
    try:
        return request(port, method, path, body, timeout)
    except (ConnectionError, http.client.HTTPException, OSError):
        return None


class FaultProxyTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.rules_path = os.path.join(self.dir, "rules.json")
        self.active_path = os.path.join(self.dir, "active.json")
        self.log_path = os.path.join(self.dir, "proxy.jsonl")
        self.state = FakeBridgeState()

        handler = type("BoundFakeBridgeHandler", (FakeBridgeHandler,), {})
        handler.state = self.state
        self.bridge = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.bridge.daemon_threads = True
        self.bridge_thread = threading.Thread(
            target=self.bridge.serve_forever, daemon=True
        )
        self.bridge_thread.start()
        self.bridge_port = self.bridge.server_address[1]
        self.proxy = None

    def tearDown(self):
        if self.proxy is not None:
            self.proxy.stop()
        self.state.poll_gate.set()
        try:
            self.bridge.shutdown()
        except Exception:
            pass
        self.bridge.server_close()
        self.bridge_thread.join(timeout=5.0)
        self.tmp.cleanup()

    def write_rules(self, version, rules):
        doc = {"version": version, "rules": rules}
        data = json.dumps(doc).encode("utf-8")
        tmp = self.rules_path + ".writer.%d" % threading.get_ident()
        with open(tmp, "wb") as fh:
            fh.write(data)
        for _ in range(20):
            try:
                os.replace(tmp, self.rules_path)
                return
            except PermissionError:
                time.sleep(0.01)
        os.replace(tmp, self.rules_path)

    def start_proxy(self, rules=None, version=1):
        if rules is not None:
            self.write_rules(version, rules)
        self.proxy = fault_proxy.FaultProxy(
            self.bridge_port,
            self.rules_path,
            self.active_path,
            self.log_path,
        )
        self.proxy.start()
        return self.proxy

    def wait_active(self, version, timeout=5.0):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                with open(self.active_path, "r", encoding="utf-8") as fh:
                    last = json.load(fh)
                if last.get("version") == version:
                    return last
            except (OSError, ValueError):
                pass
            time.sleep(0.02)
        self.fail("active_path no refleja la version %r (ultimo: %r)" % (version, last))

    def read_log(self):
        lines = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if raw:
                        lines.append(json.loads(raw))
        except OSError:
            pass
        return lines

    def wait_log(self, count, timeout=6.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            lines = self.read_log()
            if len(lines) >= count:
                return lines
            time.sleep(0.02)
        return self.read_log()


class ActionTests(FaultProxyTestBase):
    def test_action_pass_forwards(self):
        self.start_proxy(
            [
                {
                    "id": "p",
                    "match": {"route": "hello", "peer": "any"},
                    "action": {"type": "pass"},
                }
            ]
        )
        self.wait_active(1)
        status, data = request(
            self.proxy.port, "POST", "/hello?key=K1&peer=server", b"{}"
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])
        self.assertEqual(self.state.count(), 1)
        lines = self.wait_log(1)
        self.assertEqual(lines[0]["action"], "pass")
        self.assertEqual(lines[0]["rule_id"], "p")
        self.assertFalse(lines[0]["aborted"])

    def test_action_status_does_not_forward(self):
        self.start_proxy(
            [
                {
                    "id": "s",
                    "match": {"route": "hello", "peer": "any"},
                    "action": {"type": "status", "code": 503, "error": "injected"},
                }
            ]
        )
        self.wait_active(1)
        status, data = request(
            self.proxy.port, "POST", "/hello?key=K2&peer=server", b"{}"
        )
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(data), {"ok": False, "error": "injected"})
        self.assertEqual(self.state.count(), 0)
        lines = self.wait_log(1)
        self.assertEqual(lines[0]["action"], "status")
        self.assertIsNone(lines[0]["upstream_status"])

    def test_action_hold_ms_delays_then_forwards(self):
        self.start_proxy(
            [
                {
                    "id": "h",
                    "match": {"route": "hello", "peer": "any"},
                    "action": {"type": "hold_ms", "ms": 300},
                }
            ]
        )
        self.wait_active(1)
        start = time.monotonic()
        status, data = request(
            self.proxy.port, "POST", "/hello?key=K3&peer=server", b"{}"
        )
        elapsed = time.monotonic() - start
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertLess(elapsed, 2.0)
        self.assertEqual(self.state.count(), 1)
        lines = self.wait_log(1)
        self.assertGreaterEqual(lines[0]["held_ms"], 150)

    def test_action_hold_resp_ms_delays_response(self):
        self.start_proxy(
            [
                {
                    "id": "hr",
                    "match": {"route": "hello", "peer": "any"},
                    "action": {"type": "hold_resp_ms", "ms": 300},
                }
            ]
        )
        self.wait_active(1)
        start = time.monotonic()
        status, data = request(
            self.proxy.port, "POST", "/hello?key=K4&peer=server", b"{}"
        )
        elapsed = time.monotonic() - start
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ok"])
        self.assertGreaterEqual(elapsed, 0.15)
        self.assertEqual(self.state.count(), 1)
        lines = self.wait_log(1)
        self.assertEqual(lines[0]["action"], "hold_resp_ms")
        self.assertGreaterEqual(lines[0]["held_ms"], 150)

    def test_action_refuse_closes_without_forwarding(self):
        self.start_proxy(
            [
                {
                    "id": "r",
                    "match": {"route": "poll", "peer": "client", "deliver": 0},
                    "action": {"type": "refuse"},
                }
            ]
        )
        self.wait_active(1)
        result = request_or_none(
            self.proxy.port, "GET", "/poll?key=K5&peer=client&deliver=0"
        )
        self.assertIsNone(result)
        self.assertEqual(self.state.count(), 0)
        lines = self.wait_log(1)
        self.assertEqual(lines[0]["action"], "refuse")
        self.assertTrue(lines[0]["aborted"])
        self.assertIsNone(lines[0]["upstream_status"])

    def test_action_drop_resp_forwards_then_closes(self):
        self.start_proxy(
            [
                {
                    "id": "d",
                    "match": {"route": "hello", "peer": "any"},
                    "action": {"type": "drop_resp"},
                }
            ]
        )
        self.wait_active(1)
        result = request_or_none(
            self.proxy.port, "POST", "/hello?key=K6&peer=server", b"{}"
        )
        self.assertIsNone(result)
        self.assertEqual(self.state.count(), 1)
        lines = self.wait_log(1)
        self.assertEqual(lines[0]["action"], "drop_resp")
        self.assertTrue(lines[0]["aborted"])
        self.assertEqual(lines[0]["upstream_status"], 200)
        self.assertGreater(lines[0]["resp_bytes"], 0)

    def test_action_rewrite_applies_set_and_deletes(self):
        self.start_proxy(
            [
                {
                    "id": "rw",
                    "match": {"route": "poll", "peer": "any", "deliver": 1},
                    "action": {
                        "type": "rewrite",
                        "set": {
                            "now_ms": 999,
                            "ops.0.args.rev": 7,
                            "ops.0.session": {"$delete": True},
                        },
                    },
                }
            ]
        )
        self.wait_active(1)
        secret = "SECRETO_REWRITE_%d" % random.randrange(10**9)
        status, data = request(
            self.proxy.port,
            "GET",
            "/poll?key=%s&peer=client&deliver=1&session=abc" % secret,
        )
        self.assertEqual(status, 200)
        obj = json.loads(data)
        self.assertTrue(obj["ok"])
        self.assertEqual(obj["now_ms"], 999)
        self.assertEqual(obj["ops"][0]["args"]["rev"], 7)
        self.assertNotIn("session", obj["ops"][0])
        self.assertEqual(self.state.count(), 1)
        lines = self.wait_log(1)
        self.assertEqual(lines[0]["action"], "rewrite")
        self.assertEqual(lines[0]["deliver"], 1)
        self.assertEqual(lines[0]["session"], "abc")
        self.assertNotIn(secret, json.dumps(lines))
        with open(self.log_path, "r", encoding="utf-8") as fh:
            self.assertNotIn(secret, fh.read())


class WindowTests(FaultProxyTestBase):
    def test_then_cut_only_after_ops_and_scoped_to_peer_and_routes(self):
        self.start_proxy(
            [
                {
                    "id": "cut",
                    "match": {
                        "route": "poll",
                        "peer": "client",
                        "resp_has_op": True,
                        "nth": 1,
                        "count": 1,
                    },
                    "action": {
                        "type": "then_cut_ms",
                        "ms": 600,
                        "routes": ["poll", "hello"],
                    },
                }
            ]
        )
        self.wait_active(1)

        status, data = request(
            self.proxy.port, "GET", "/poll?key=K7&peer=client&deliver=0"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["ops"], [])

        status, data = request(
            self.proxy.port, "GET", "/poll?key=K7&peer=client&deliver=0"
        )
        self.assertEqual(status, 200)

        status, data = request(
            self.proxy.port, "GET", "/poll?key=K7&peer=client&deliver=1"
        )
        self.assertEqual(status, 200)
        self.assertTrue(len(json.loads(data)["ops"]) > 0)

        self.assertIsNone(
            request_or_none(
                self.proxy.port, "GET", "/poll?key=K7&peer=client&deliver=0"
            )
        )
        self.assertIsNone(
            request_or_none(
                self.proxy.port, "POST", "/hello?key=K7&peer=client", b"{}"
            )
        )

        status, data = request(
            self.proxy.port, "GET", "/poll?key=K7&peer=server&deliver=0"
        )
        self.assertEqual(status, 200)
        status, data = request(
            self.proxy.port, "POST", "/hello?key=K7&peer=server", b"{}"
        )
        self.assertEqual(status, 200)

        time.sleep(0.75)
        status, data = request(
            self.proxy.port, "GET", "/poll?key=K7&peer=client&deliver=0"
        )
        self.assertEqual(status, 200)

        lines = self.wait_log(8)
        cut_lines = [line for line in lines if line["action"] == "then_cut_ms"]
        refused = [line for line in cut_lines if line["aborted"]]
        self.assertEqual(len(refused), 2)
        self.assertEqual(len(cut_lines), 3)

    def test_then_hold_only_after_ops_and_scoped_to_peer_and_routes(self):
        self.start_proxy(
            [
                {
                    "id": "hold",
                    "match": {
                        "route": "poll",
                        "peer": "client",
                        "resp_has_op": True,
                        "nth": 1,
                        "count": 1,
                    },
                    "action": {
                        "type": "then_hold_ms",
                        "ms": 500,
                        "routes": ["poll"],
                    },
                }
            ]
        )
        self.wait_active(1)

        status, data = request(
            self.proxy.port, "GET", "/poll?key=K8&peer=client&deliver=0"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["ops"], [])

        status, data = request(
            self.proxy.port, "GET", "/poll?key=K8&peer=client&deliver=1"
        )
        self.assertEqual(status, 200)
        self.assertTrue(len(json.loads(data)["ops"]) > 0)

        start = time.monotonic()
        status, data = request(
            self.proxy.port, "GET", "/poll?key=K8&peer=client&deliver=0"
        )
        elapsed = time.monotonic() - start
        self.assertEqual(status, 200)
        self.assertGreaterEqual(elapsed, 0.35)

        start = time.monotonic()
        status, data = request(
            self.proxy.port, "GET", "/poll?key=K8&peer=server&deliver=0"
        )
        elapsed = time.monotonic() - start
        self.assertEqual(status, 200)
        self.assertLess(elapsed, 0.35)

        lines = self.wait_log(5)
        held = [line for line in lines if line["action"] == "then_hold_ms"]
        held_long = [line for line in held if line["held_ms"] >= 350]
        self.assertEqual(len(held), 2)
        self.assertEqual(len(held_long), 1)


class HoldWindowV12Tests(FaultProxyTestBase):
    """Brief v1.2 (L-13): en la ventana de then_hold_ms el poll se reenvia al momento como
    mantenimiento (deliver=0, con la clave hacia el bridge) y la respuesta sale al final absoluto."""

    def test_then_hold_reenvia_al_momento_como_mantenimiento(self):
        self.start_proxy([{
            "id": "hold12",
            "match": {"route": "poll", "peer": "client", "resp_has_op": True, "nth": 1, "count": 1},
            "action": {"type": "then_hold_ms", "ms": 800, "routes": ["poll"]},
        }])
        self.wait_active(1)
        status, data = request(self.proxy.port, "GET", "/poll?key=K9&peer=client&deliver=1")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(data)["ops"])
        t_trigger = time.monotonic()
        n0 = self.state.count()
        box = {}

        def held_poll():
            box["resp"] = request(self.proxy.port, "GET", "/poll?key=K9&peer=client&deliver=1")
            box["t"] = time.monotonic()

        th = threading.Thread(target=held_poll)
        th.start()
        deadline = time.monotonic() + 0.5
        while self.state.count() == n0 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreater(self.state.count(), n0, "el poll no llego al bridge al momento")
        self.assertTrue(th.is_alive(), "la respuesta no se retuvo")
        with self.state.lock:
            path = self.state.requests[-1]["path"]
        self.assertIn("deliver=0", path)
        self.assertNotIn("deliver=1", path)
        self.assertIn("key=K9", path)
        th.join(5)
        self.assertEqual(box["resp"][0], 200)
        self.assertGreaterEqual(box["t"] - t_trigger, 0.65)
        line = [x for x in self.wait_log(2) if x["action"] == "then_hold_ms"][-1]
        self.assertGreaterEqual(line["held_ms"], 500)
        self.assertNotIn("K9", json.dumps(self.read_log()))


class HelloPeerFromBodyTests(FaultProxyTestBase):
    """El hello del mod real lleva el peer en el cuerpo JSON, no en la URL (humo diag, 15-nov)."""

    def test_hello_sin_peer_en_la_url_se_atribuye_por_el_cuerpo(self):
        self.start_proxy([{
            "id": "h401",
            "match": {"route": "hello", "peer": "server", "count": 1},
            "action": {"type": "status", "code": 401, "error": "bad_key"},
        }])
        self.wait_active(1)
        status, _ = request(self.proxy.port, "POST", "/hello?key=K7",
                            json.dumps({"peer": "client", "inst": "i"}).encode("utf-8"))
        self.assertEqual(status, 200)
        status, _ = request(self.proxy.port, "POST", "/hello?key=K7",
                            json.dumps({"peer": "server", "inst": "i"}).encode("utf-8"))
        self.assertEqual(status, 401)
        lines = self.wait_log(2)
        self.assertEqual([line["peer"] for line in lines[-2:]], ["client", "server"])
        self.assertNotIn("K7", json.dumps(self.read_log()))


class PollDeliverDefaultTests(FaultProxyTestBase):
    """El poll normal del mod no lleva deliver y entrega, como en el bridge (partida diag, 15-nov)."""

    def test_poll_sin_deliver_cuenta_como_entrega(self):
        self.start_proxy([{
            "id": "d1",
            "match": {"route": "poll", "peer": "server", "deliver": 1, "count": 1},
            "action": {"type": "status", "code": 409, "error": "x"},
        }])
        self.wait_active(1)
        status, _ = request(self.proxy.port, "GET", "/poll?key=K8&peer=server&deliver=0")
        self.assertEqual(status, 200)
        status, _ = request(self.proxy.port, "GET", "/poll?key=K8&peer=server")
        self.assertEqual(status, 409)
        lines = self.wait_log(2)
        self.assertEqual([line["deliver"] for line in lines[-2:]], [0, 1])
        self.assertNotIn("K8", json.dumps(self.read_log()))


class CounterTests(FaultProxyTestBase):
    def test_nth_count_acts_exactly_count_times_under_concurrency(self):
        self.start_proxy(
            [
                {
                    "id": "throttle",
                    "match": {"route": "hello", "peer": "any", "nth": 3, "count": 4},
                    "action": {"type": "status", "code": 503, "error": "nth"},
                }
            ]
        )
        self.wait_active(1)

        results = []
        lock = threading.Lock()

        def worker():
            try:
                status, _ = request(
                    self.proxy.port,
                    "POST",
                    "/hello?key=K9&peer=server",
                    b"{}",
                    timeout=15.0,
                )
            except Exception:
                status = None
            with lock:
                results.append(status)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15.0)

        self.assertEqual(len(results), 8)
        self.assertEqual(results.count(503), 4)
        self.assertEqual(results.count(200), 4)

        lines = self.wait_log(8)
        status_lines = [line for line in lines if line["action"] == "status"]
        self.assertEqual(len(status_lines), 4)


class AbortInflightTests(FaultProxyTestBase):
    def test_abort_inflight_closes_waiting_long_poll_and_logs(self):
        self.state.retain_poll = True
        self.state.poll_gate.clear()
        self.start_proxy([])
        self.wait_active(1)

        outcome = {}

        def client():
            outcome["value"] = request_or_none(
                self.proxy.port, "GET", "/poll?key=K10&peer=client&deliver=1", timeout=15.0
            )

        thread = threading.Thread(target=client, daemon=True)
        thread.start()
        self.assertTrue(self.state.poll_arrived.wait(8.0))

        self.write_rules(
            2,
            [
                {
                    "id": "abort",
                    "match": {"route": "poll", "peer": "client"},
                    "action": {"type": "pass"},
                    "abort_inflight": True,
                }
            ],
        )
        self.wait_active(2)

        thread.join(timeout=8.0)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(outcome.get("value"))

        lines = self.wait_log(1)
        aborted = [line for line in lines if line["aborted"]]
        self.assertEqual(len(aborted), 1)
        self.assertEqual(aborted[0]["route"], "poll")
        self.assertEqual(aborted[0]["peer"], "client")
        self.assertIsNone(aborted[0]["upstream_status"])

        self.state.poll_gate.set()


class AbortBarrierOrderTests(FaultProxyTestBase):
    """R13 (Q-02): la barrera va ANTES de publicar rules_active.json."""

    def test_barrier_aborts_before_publishing_and_late_upstream_reply_is_not_served(self):
        self.state.retain_poll = True
        self.state.poll_gate.clear()
        self.start_proxy([])
        self.wait_active(1)

        outcome = {}

        def client():
            outcome["value"] = request_or_none(
                self.proxy.port, "GET", "/poll?key=K13&peer=client&deliver=1", timeout=15.0
            )

        thread = threading.Thread(target=client, daemon=True)
        thread.start()
        self.assertTrue(self.state.poll_arrived.wait(8.0))
        with self.proxy._lock:
            pending = list(self.proxy._inflight.values())
        self.assertEqual(len(pending), 1)
        entry = pending[0]

        seen = {}
        original = fault_proxy._atomic_write_json

        def hook(path, obj):
            # Gancho de orden: justo antes de publicar la version nueva, el bridge de prueba
            # contesta al poll retenido y se da tiempo a que el proxy lo sirva si pudiera.
            if path == self.proxy.active_path and obj.get("version") == 2:
                seen["aborted_at_publish"] = bool(entry["aborted"])
                self.state.poll_gate.set()
                time.sleep(0.5)
            return original(path, obj)

        fault_proxy._atomic_write_json = hook
        try:
            self.write_rules(
                2,
                [
                    {
                        "id": "cut",
                        "match": {"route": "poll", "peer": "client"},
                        "action": {"type": "pass"},
                        "abort_inflight": True,
                    }
                ],
            )
            self.wait_active(2)
            thread.join(timeout=8.0)
        finally:
            fault_proxy._atomic_write_json = original

        self.assertFalse(thread.is_alive())
        self.assertTrue(
            seen.get("aborted_at_publish"),
            "rules_active.json se publico antes de abortar el poll en vuelo",
        )
        self.assertIsNone(
            outcome.get("value"), "el cliente recibio la respuesta de un poll abortado"
        )
        lines = self.wait_log(1)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0]["aborted"])
        self.assertEqual(lines[0]["rules_version"], 1)
        self.assertEqual(lines[0]["resp_bytes"], 0)

    def test_request_entering_after_install_runs_under_new_version(self):
        self.start_proxy(
            [
                {
                    "id": "abort",
                    "match": {"route": "poll", "peer": "client"},
                    "action": {"type": "pass"},
                    "abort_inflight": True,
                }
            ]
        )
        self.wait_active(1)
        status, _ = request(self.proxy.port, "GET", "/poll?key=K13&peer=client&deliver=1")
        self.assertEqual(status, 200)
        lines = self.wait_log(1)
        self.assertFalse(lines[0]["aborted"])
        self.assertEqual(lines[0]["rules_version"], 1)


class ActivePathTests(FaultProxyTestBase):
    def test_active_path_reflects_activated_version(self):
        self.start_proxy([])
        first = self.wait_active(1)
        self.assertIn("t_ms", first)

        self.write_rules(
            2,
            [
                {
                    "id": "pass",
                    "match": {"route": "any", "peer": "any"},
                    "action": {"type": "pass"},
                }
            ],
        )
        second = self.wait_active(2)
        self.assertIn("t_ms", second)
        self.assertGreaterEqual(second["t_ms"], first["t_ms"])

        with open(self.active_path, "r", encoding="utf-8") as fh:
            raw = fh.read()
        self.assertNotIn("\ufeff", raw)


class CliSecretTests(unittest.TestCase):
    def test_cli_never_leaks_secret(self):
        secret = "SECRETO_UNICO_%d" % random.randrange(10**9)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        rules_path = os.path.join(tmp.name, "rules.json")
        active_path = os.path.join(tmp.name, "active.json")
        log_path = os.path.join(tmp.name, "proxy.jsonl")
        with open(rules_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(
                {
                    "version": 1,
                    "rules": [
                        {
                            "id": "pass",
                            "match": {"route": "any", "peer": "any"},
                            "action": {"type": "pass"},
                        }
                    ],
                },
                fh,
            )

        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        dead_port = probe.getsockname()[1]
        probe.close()

        cmd = [
            sys.executable,
            FAULT_PROXY_PATH,
            "--upstream-port",
            str(dead_port),
            "--rules",
            rules_path,
            "--active",
            active_path,
            "--log",
            log_path,
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            line = proc.stdout.readline()
            while line and "listening port=" not in line:
                line = proc.stdout.readline()
            self.assertIn("listening port=", line)
            port = int(line.strip().split("=")[1])

            status, data = request(
                port, "POST", "/hello?key=%s&peer=server" % secret, b"{}"
            )
            self.assertEqual(status, 502)
            self.assertEqual(
                json.loads(data), {"ok": False, "error": "upstream_unreachable"}
            )
            request_or_none(
                port,
                "GET",
                "/poll?key=%s&peer=client&deliver=0&session=s1" % secret,
            )
        finally:
            proc.terminate()
            try:
                out, err = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                out, err = proc.communicate()

        self.assertNotIn(secret, out)
        self.assertNotIn(secret, err)
        with open(log_path, "r", encoding="utf-8") as fh:
            log_text = fh.read()
        self.assertNotIn(secret, log_text)
        self.assertGreater(len(log_text.strip()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
