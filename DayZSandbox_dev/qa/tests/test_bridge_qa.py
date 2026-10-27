"""Puente QA v0 aislado (brief F0.1 §10.2 punto 5)."""

import json
import socket
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from bridge_qa import QABridge


def _call(bridge, method, path, key, body=None, query=""):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    url = f"http://127.0.0.1:{bridge.port}{path}?key={key}"
    if query:
        url += "&" + query
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return exc.code, payload


class BridgeQaTests(unittest.TestCase):
    def setUp(self):
        self.rows = []
        self.bridge = QABridge(200, 600, self.rows.append, port=0)
        self.bridge.start()
        self.bridge.set_peer_key("server", "k-server")
        self.bridge.set_peer_key("client", "k-client")

    def tearDown(self):
        self.bridge.stop()

    def test_bind_is_loopback_without_reuse(self):
        self.assertEqual(self.bridge.httpd.server_address[0], "127.0.0.1")
        self.assertIs(self.bridge.httpd.allow_reuse_address, False)

    def test_bad_key_is_401_and_does_not_register(self):
        code, hello = _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "aa", "build": "offline", "probe_ver": "t"},
        )
        self.assertEqual(code, 200)
        self.assertEqual(hello["ok"], True)
        for method, path, body in (
            ("POST", "/hello", {"proto": "qa0", "peer": "server", "inst": "bb", "build": "offline"}),
            ("GET", "/poll", None),
            ("POST", "/result", {"op_id": "z", "status": "done"}),
        ):
            code, payload = _call(self.bridge, method, path, "nope", body, "peer=server&inst=aa")
            self.assertEqual(code, 401)
            self.assertEqual(payload["error"], "bad_key")
        self.assertEqual(self.bridge.registered("server"), "aa")

    def test_unregistered_is_409(self):
        code, payload = _call(self.bridge, "GET", "/poll", "k-server", None, "peer=server&inst=missing")
        self.assertEqual(code, 409)
        self.assertEqual(payload["error"], "hello_required")

    def test_empty_poll_holds_then_returns_no_ops(self):
        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "aa", "build": "offline", "probe_ver": "t"},
        )
        t0 = time.monotonic()
        code, payload = _call(self.bridge, "GET", "/poll", "k-server", None, "peer=server&inst=aa&frame=1")
        elapsed = (time.monotonic() - t0) * 1000.0
        self.assertEqual(code, 200)
        self.assertEqual(payload["ops"], [])
        self.assertGreaterEqual(elapsed, 0.9 * 200)
        self.assertLess(elapsed, 200 + 500)

    def test_ttl_expires_without_deliver_and_force_overrides_inst(self):
        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "aa", "build": "offline", "probe_ver": "t"},
        )
        oid = self.bridge.enqueue("server", "srv_read", {}, "aa", 30, issued_ms=self.bridge.now_ms() - 100)
        code, payload = _call(self.bridge, "GET", "/poll", "k-server", None, "peer=server&inst=aa&frame=2")
        self.assertEqual(code, 200)
        self.assertEqual(payload["ops"], [])
        self.assertTrue(any(row.get("ev") == "expire" and row.get("op_id") == oid for row in self.rows))
        self.assertFalse(any(row.get("ev") == "deliver" and row.get("op_id") == oid for row in self.rows))
        other = self.bridge.enqueue("server", "srv_read", {}, "not-aa", 5000)
        self.bridge.force_deliver(other)
        code, payload = _call(self.bridge, "GET", "/poll", "k-server", None, "peer=server&inst=aa&frame=3")
        self.assertEqual([op["op_id"] for op in payload["ops"]], [other])

    def test_cut_releases_inflight_poll(self):
        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-client",
            {"proto": "qa0", "peer": "client", "inst": "cc", "build": "offline", "probe_ver": "t"},
        )
        box = {}

        def _poll():
            t0 = time.monotonic()
            box["result"] = _call(self.bridge, "GET", "/poll", "k-client", None, "peer=client&inst=cc&frame=1")
            box["elapsed"] = time.monotonic() - t0

        thread = threading.Thread(target=_poll)
        thread.start()
        time.sleep(0.05)
        self.bridge.cut("client", 5000)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(box["result"][0], 503)
        self.assertLess(box["elapsed"], 1.0)

    def test_drop_results_is_503_and_not_stored(self):
        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "aa", "build": "offline", "probe_ver": "t"},
        )
        self.bridge.drop_results("gone", True)
        code, payload = _call(
            self.bridge,
            "POST",
            "/result",
            "k-server",
            {"op_id": "gone", "status": "done", "dup": False},
            "peer=server&inst=aa",
        )
        self.assertEqual(code, 503)
        self.assertEqual(payload["error"], "drop")
        self.assertIsNone(self.bridge.wait_result("gone", 0, 50))

    def test_sol11_hello_uses_body_peer_key(self):
        code, _payload = _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "client", "inst": "cc", "build": "offline", "probe_ver": "t"},
            "peer=server",
        )
        self.assertEqual(code, 401)
        self.assertIsNone(self.bridge.registered("client"))

    def test_sol12_poll_rechecks_instance_when_released(self):
        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "I1", "build": "offline", "probe_ver": "t"},
        )
        box = {}

        def _poll():
            box["result"] = _call(self.bridge, "GET", "/poll", "k-server", None, "peer=server&inst=I1&frame=1")

        thread = threading.Thread(target=_poll)
        thread.start()
        time.sleep(0.05)
        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "I2", "build": "offline", "probe_ver": "t"},
        )
        oid = self.bridge.enqueue("server", "srv_read", {}, "I1", 5000)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(box["result"][0], 409)
        self.assertFalse(any(row.get("ev") == "deliver" and row.get("op_id") == oid for row in self.rows))

    def test_key_absent_from_events(self):
        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "aa", "build": "offline", "probe_ver": "t"},
        )
        blob = json.dumps(self.rows)
        self.assertNotIn("k-server", blob)
        self.assertNotIn("k-client", blob)

    def _hello_server(self):
        return _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "aa", "build": "offline", "probe_ver": "t"},
        )

    def test_sol08_stop_drains_handlers_and_then_the_sink_is_quiet(self):
        log = Path(tempfile.mkdtemp(prefix="dsbx-bridge-")) / "bridge.jsonl"
        handle = log.open("a", encoding="utf-8", newline="\n")

        def sink(row):
            self.rows.append(row)
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()

        self.bridge.sink = sink
        self._hello_server()
        thread = threading.Thread(
            target=_call,
            args=(self.bridge, "GET", "/poll", "k-server"),
            kwargs={"query": "peer=server&inst=aa&frame=1"},
        )
        thread.start()
        deadline = time.monotonic() + 2
        while self.bridge._live < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertGreater(self.bridge._live, 0)
        self.bridge.stop()
        thread.join(timeout=2)
        handle.close()
        self.assertEqual(self.bridge._live, 0)
        self.assertFalse(thread.is_alive())
        lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(lines), len(self.bridge.events))
        self.assertEqual(len(self.rows), len(self.bridge.events))
        time.sleep(0.05)
        self.assertEqual(len(self.rows), len(self.bridge.events))

    def test_sol08_stop_stores_error_when_a_handler_never_finishes(self):
        gate = threading.Event()

        def sink(row):
            self.rows.append(row)
            if row.get("ev") == "poll":
                gate.wait(timeout=5)

        self.bridge.sink = sink
        self.bridge.STOP_JOIN_S = 0.05
        self._hello_server()
        thread = threading.Thread(
            target=_call,
            args=(self.bridge, "GET", "/poll", "k-server"),
            kwargs={"query": "peer=server&inst=aa&frame=1"},
        )
        thread.start()
        deadline = time.monotonic() + 2
        while not any(row.get("ev") == "poll" for row in self.rows) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.bridge.stop()
        self.assertIsInstance(self.bridge.failure, TimeoutError)
        gate.set()
        thread.join(timeout=2)

    def test_sol09_sink_oserror_during_stop_exits_2(self):
        import m1_gate
        import s_puente_run

        real_stop = s_puente_run.QABridge.stop
        keys = {}
        real_set = s_puente_run.QABridge.set_peer_key

        def set_peer_key(self, peer, key):
            keys[peer] = key
            return real_set(self, peer, key)

        def stop(self):
            def worker():
                try:
                    body = {"proto": "qa0", "peer": "server", "inst": "aa" * 16, "build": "retail", "probe_ver": "t"}
                    _call(self, "POST", "/hello", keys["server"], body)
                    _call(self, "GET", "/poll", keys["server"], None, "peer=server&inst=" + ("aa" * 16) + "&frame=1")
                except Exception:
                    return

            thread = threading.Thread(target=worker)
            thread.start()
            deadline = time.monotonic() + 2
            while self._live < 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            real_stop(self)
            thread.join(timeout=2)

        real_init = s_puente_run.QABridge.__init__

        def init(self, hold_ms, lease_ms, sink, port=0):
            def wrapped(row):
                if self._stopping:
                    raise OSError("sink during stop")
                sink(row)

            real_init(self, hold_ms, lease_ms, wrapped, port)

        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            root = Path(tmp)
            (root / "s").mkdir()
            (root / "c").mkdir()
            evidence = root / "run"
            with (
                mock.patch.object(s_puente_run.QABridge, "__init__", init),
                mock.patch.object(s_puente_run.QABridge, "set_peer_key", set_peer_key),
                mock.patch.object(s_puente_run.QABridge, "stop", stop),
            ):
                code = m1_gate.main(
                    [
                        "spike",
                        "S-puente",
                        "--both",
                        "--build",
                        "retail",
                        "--evidence",
                        str(evidence),
                        "--peer-timeout",
                        "0",
                        "--server-profile",
                        str(root / "s"),
                        "--client-profile",
                        str(root / "c"),
                    ]
                )
            verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 2)
        self.assertEqual(verdict["error"]["type"], "OSError")
        self.assertTrue(verdict["error"]["traceback"])

    def test_sol14_hello_54ms_after_the_single_deadline_is_absent(self):
        import s_puente_run

        clock = {"values": []}
        real_now = s_puente_run.QABridge.now_ms

        def now_ms(self):
            clock["values"].append(real_now(self) + 100.0 * (len(clock["values"]) + 1))
            return clock["values"][-1]

        real_wait = s_puente_run.QABridge.wait_event

        def wait_event(self, pred, timeout_ms):
            if not clock.get("armed"):
                clock["armed"] = True
                anchor = clock["values"][-2]
                plazo = anchor + 200.0
                self.events.append(
                    {"ev": "hello", "peer": "server", "http": 200, "t_ms": plazo + 54}
                )
            return real_wait(self, pred, timeout_ms)

        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            root = Path(tmp)
            (root / "s").mkdir()
            (root / "c").mkdir()
            evidence = root / "run"
            args = _retail_args(root)
            args.peer_timeout = 0.2
            with (
                mock.patch.object(s_puente_run.QABridge, "now_ms", now_ms),
                mock.patch.object(s_puente_run.QABridge, "wait_event", wait_event),
            ):
                code = s_puente_run.run(args, evidence, [])
            scenario = (evidence / "samples" / "scenario.jsonl").read_text(encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertIn('"peer": "server"', scenario)
        self.assertIn('"ev": "peers_absent"', scenario)

    def test_sol14_late_hello_t_ms_does_not_count(self):
        import s_puente_run

        real = s_puente_run.QABridge.start

        def start(self):
            real(self)
            self.events.append({"ev": "hello", "peer": "server", "http": 200, "t_ms": 0})
            self.events.append({"ev": "hello", "peer": "client", "http": 200, "t_ms": 1e15})

        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            root = Path(tmp)
            (root / "s").mkdir()
            (root / "c").mkdir()
            evidence = root / "run"
            with mock.patch.object(s_puente_run.QABridge, "start", start):
                code = s_puente_run.run(
                    _retail_args(root),
                    evidence,
                    [],
                )
            scenario = (evidence / "samples" / "scenario.jsonl").read_text(encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertIn('"ev": "peers_absent"', scenario)
        self.assertIn('"peer": "client"', scenario)


    def test_sol22_enq_blocks_poll_until_the_sink_returns(self):
        gate = threading.Event()

        def sink(row):
            self.rows.append(row)
            if row.get("ev") == "enq":
                gate.wait(timeout=3)

        self.bridge.sink = sink
        self._hello_server()
        box = {}

        def do_enq():
            box["oid"] = self.bridge.enqueue("server", "srv_read", {}, "aa", 5000)

        enq = threading.Thread(target=do_enq)
        enq.start()
        deadline = time.monotonic() + 2
        while not any(row.get("ev") == "enq" for row in self.rows) and time.monotonic() < deadline:
            time.sleep(0.01)

        def do_poll():
            box["poll"] = _call(self.bridge, "GET", "/poll", "k-server", None, "peer=server&inst=aa&frame=1")

        poll = threading.Thread(target=do_poll)
        poll.start()
        time.sleep(0.15)
        self.assertFalse(any(row.get("ev") == "deliver" for row in self.rows))
        gate.set()
        enq.join(timeout=2)
        poll.join(timeout=2)
        self.assertEqual(box["poll"][0], 200)
        self.assertEqual(box["poll"][1]["ops"][0]["op_id"], box["oid"])
        code, _payload = _call(
            self.bridge,
            "POST",
            "/result",
            "k-server",
            {
                "op_id": box["oid"],
                "status": "done",
                "reason": "",
                "dup": False,
                "recv_ms": 1,
                "done_ms": 2,
                "frame_recv": 1,
                "frame_done": 2,
                "read": {"has": []},
            },
            "peer=server&inst=aa",
        )
        self.assertEqual(code, 200)
        names = [row["ev"] for row in self.rows if row["ev"] in ("enq", "deliver", "result")]
        self.assertEqual(names, ["enq", "deliver", "result"])
        stamps = [row["t_ms"] for row in self.rows]
        self.assertEqual(stamps, sorted(stamps))

    def test_sol22_poll_blocks_the_next_hello(self):
        gate = threading.Event()

        def sink(row):
            self.rows.append(row)
            if row.get("ev") == "poll" and row.get("inst") == "I1":
                gate.wait(timeout=3)

        _call(
            self.bridge,
            "POST",
            "/hello",
            "k-server",
            {"proto": "qa0", "peer": "server", "inst": "I1", "build": "offline", "probe_ver": "t"},
        )
        self.bridge.sink = sink
        self.bridge.enqueue("server", "srv_read", {}, "I1", 5000)
        poll = threading.Thread(
            target=_call,
            args=(self.bridge, "GET", "/poll", "k-server"),
            kwargs={"query": "peer=server&inst=I1&frame=1"},
        )
        poll.start()
        deadline = time.monotonic() + 2
        while not any(row.get("ev") == "poll" for row in self.rows) and time.monotonic() < deadline:
            time.sleep(0.01)
        box = {}

        def do_hello():
            box["hello"] = _call(
                self.bridge,
                "POST",
                "/hello",
                "k-server",
                {"proto": "qa0", "peer": "server", "inst": "I2", "build": "offline", "probe_ver": "t"},
            )

        hello = threading.Thread(target=do_hello)
        hello.start()
        time.sleep(0.15)
        self.assertNotIn("hello", box)
        gate.set()
        poll.join(timeout=2)
        hello.join(timeout=2)
        self.assertEqual(box["hello"][0], 200)
        deliver_at = next(i for i, row in enumerate(self.rows) if row.get("ev") == "deliver")
        hello_at = next(i for i, row in enumerate(self.rows) if row.get("ev") == "hello" and row.get("inst") == "I2")
        self.assertLess(deliver_at, hello_at)

    def test_sol08_stop_waits_for_a_request_accepted_before_its_thread(self):
        release = threading.Event()
        entered = threading.Event()
        self._hello_server()
        server_cls = type(self.bridge.httpd)
        original = server_cls.process_request_thread

        def delayed(self_server, request, client_address):
            entered.set()
            release.wait(timeout=3)
            return original(self_server, request, client_address)

        box = {}
        seen = {}
        with mock.patch.object(server_cls, "process_request_thread", delayed):
            def do_poll():
                box["poll"] = _call(
                    self.bridge, "GET", "/poll", "k-server", None, "peer=server&inst=aa&frame=1"
                )

            poll = threading.Thread(target=do_poll)
            poll.start()
            self.assertTrue(entered.wait(2))
            stopped = threading.Event()

            def do_stop():
                self.bridge.stop()
                seen["rows"] = list(self.rows)
                stopped.set()

            stopper = threading.Thread(target=do_stop)
            stopper.start()
            # serve_forever polls every 0.5s; shutdown() on c458c699 returns inside that window.
            time.sleep(1.2)
            self.assertFalse(stopped.is_set())
            release.set()
            self.assertTrue(stopped.wait(3))
            poll.join(timeout=2)
        self.assertTrue(any(row.get("ev") == "poll" for row in seen["rows"]))
        recorded = len(seen["rows"])
        time.sleep(0.05)
        self.assertEqual(len(self.rows), recorded)
        self.assertEqual(box["poll"][0], 200)

    def test_sol09_reset_during_the_run_is_a_bridge_error(self):
        import s_puente_run

        self._hello_server()
        sock = socket.create_connection(("127.0.0.1", self.bridge.port))
        sock.sendall(b"GET /poll?key=k-server&peer=server&inst=aa HTTP/1.0\r\n")
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("hh", 1, 0))
        sock.close()
        found = None
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                s_puente_run._raise_if_bridge_failed(self.bridge)
            except Exception as exc:
                found = exc
                break
            time.sleep(0.05)
        self.assertIsInstance(found, ConnectionError)


def _retail_args(root):
    import argparse

    return argparse.Namespace(
        both=True,
        build="retail",
        client_profile=str(root / "c"),
        evaluate_only=False,
        fault=None,
        hold_ms=300,
        lease_ms=600,
        peer_timeout=0,
        retry_ms=300,
        seed=20261026,
        server_profile=str(root / "s"),
        ttl_ms=1000,
    )


if __name__ == "__main__":
    unittest.main()
