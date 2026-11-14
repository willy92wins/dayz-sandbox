"""Ajuste de P3 y P4 en el peer falso: fallos de hello y de poll (brief F0.2 §3, §5 y §6.1)."""

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
PEER = Path(__file__).resolve().parents[1] / "fake_peer.py"
PY = sys.executable


class _RecordedRequest:
    def __init__(self, method, path, query, raw_body, json_body, recv_s, sent_s):
        self.method = method
        self.path = path
        self.query = query
        self.raw_body = raw_body
        self.json_body = json_body
        self.recv_s = recv_s
        self.sent_s = sent_s


class _QuietHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def handle_error(self, request, client_address):
        return


class _TestBridge:
    def __init__(self):
        self.cv = threading.Condition()
        self.steps = []
        self.requests = []
        self._listener_closed = False
        self._thread = None
        self.httpd = _QuietHTTPServer(("127.0.0.1", 0), self._make_handler())

    @property
    def port(self):
        return self.httpd.server_address[1]

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/"

    def start(self):
        self._thread = threading.Thread(
            target=self.httpd.serve_forever,
            kwargs={"poll_interval": 0.02},
            daemon=True,
        )
        self._thread.start()
        return self

    def close_listener(self):
        if self._listener_closed:
            return
        self._listener_closed = True
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)

    def stop(self):
        self.close_listener()

    def plan(self, code, body=b"", before_reply=None, hold_s=0.0, content_type="application/json"):
        if isinstance(body, dict):
            raw = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = bytes(body)
        with self.cv:
            self.steps.append((int(code), raw, before_reply, float(hold_s), content_type))

    def wait_count(self, count, timeout=6.0):
        deadline = time.monotonic() + timeout
        with self.cv:
            while len(self.requests) < count:
                left = deadline - time.monotonic()
                if left <= 0:
                    return False
                self.cv.wait(left)
            return True

    def snapshot(self):
        with self.cv:
            return list(self.requests)

    def _default_reply(self, method, path):
        if method == "POST" and path == "/hello":
            raw = json.dumps({"lease_ms": 3000, "ok": True}, separators=(",", ":")).encode("utf-8")
            return 200, raw, None, 0.0, "application/json"
        if method == "GET" and path == "/poll":
            raw = json.dumps({"now_ms": 1.0, "ops": []}, separators=(",", ":")).encode("utf-8")
            return 200, raw, None, 0.0, "application/json"
        raw = json.dumps({"ok": True}, separators=(",", ":")).encode("utf-8")
        return 200, raw, None, 0.0, "application/json"

    def _make_handler(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, fmt, *args):
                return

            def do_GET(self):
                bridge._dispatch(self)

            def do_POST(self):
                bridge._dispatch(self)

        return Handler

    def _dispatch(self, handler):
        recv_s = time.monotonic()
        parts = urlsplit(handler.path)
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        length = int(handler.headers.get("Content-Length") or 0)
        raw_body = handler.rfile.read(length) if length else b""
        json_body = None
        if raw_body:
            try:
                json_body = json.loads(raw_body.decode("utf-8"))
            except (UnicodeError, ValueError):
                json_body = None
        with self.cv:
            if self.steps:
                step = self.steps.pop(0)
            else:
                step = self._default_reply(handler.command, parts.path)
        if callable(step):
            code, raw_resp, before_reply, hold_s, content_type = step(
                handler.command, parts.path, query, json_body
            )
        else:
            code, raw_resp, before_reply, hold_s, content_type = step
        if before_reply is not None:
            before_reply()
        if hold_s > 0:
            time.sleep(hold_s)
        handler.send_response(code)
        if content_type:
            handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(raw_resp)))
        handler.end_headers()
        if raw_resp:
            handler.wfile.write(raw_resp)
        handler.wfile.flush()
        sent_s = time.monotonic()
        rec = _RecordedRequest(
            handler.command,
            parts.path,
            query,
            raw_body,
            json_body,
            recv_s,
            sent_s,
        )
        with self.cv:
            self.requests.append(rec)
            self.cv.notify_all()


def _free_udp_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _write_cfg(path, url, key, retry_ms):
    body = {"key": key, "retry_ms": int(retry_ms), "url": url}
    tmp = Path(str(path) + ".tmp")
    tmp.write_bytes(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    for attempt in range(10):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.01)


def _stop_peers(procs):
    outputs = []
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate(timeout=5)
        outputs.append((out or b"") + (err or b""))
    return outputs


def _owned_fake_peer_pids(parent_pids):
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*.exe' -and $_.CommandLine -like '*fake_peer.py*' } | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)\" }"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    parents = {str(pid) for pid in parent_pids}
    owned = set()
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        pid, parent = line.split("|", 1)
        if parent.strip() in parents:
            owned.add(pid.strip())
    return owned


def _force_kill_pids(pids):
    for pid in pids:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue",
            ],
            capture_output=True,
            timeout=20,
        )


class PeerErrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t0 = time.monotonic()
        cls._parents = {str(os.getpid())}
        cls._owned_before = _owned_fake_peer_pids(cls._parents)

    @classmethod
    def tearDownClass(cls):
        afterwards = _owned_fake_peer_pids(cls._parents)
        leaked = afterwards - cls._owned_before
        try:
            if leaked:
                raise AssertionError(f"surviving fake_peer.py pids: {sorted(leaked)}")
            elapsed = time.monotonic() - cls._t0
            if elapsed >= 60.0:
                raise AssertionError(f"test_peer_errors.py took {elapsed:.2f}s (>= 60s)")
        finally:
            _force_kill_pids(leaked)

    def setUp(self):
        self.procs = []
        self.bridges = []
        self.keys = []
        self.captured_peer_bytes = bytearray()

    def tearDown(self):
        try:
            outputs = _stop_peers(self.procs)
            self.procs.clear()
            for chunk in outputs:
                self.captured_peer_bytes.extend(chunk)
        finally:
            for bridge in reversed(self.bridges):
                bridge.stop()
            self.bridges.clear()
        blob = bytes(self.captured_peer_bytes)
        self.assertNotIn(b"key=", blob, "key query leaked to peer output")
        for key in self.keys:
            self.assertFalse(key.encode("ascii") in blob, "secret key leaked to peer output")

    def _new_key(self):
        key = secrets.token_hex(16)
        self.keys.append(key)
        return key

    def _start_bridge(self):
        bridge = _TestBridge().start()
        self.bridges.append(bridge)
        return bridge

    def _spawn_peer(self, cfg_path, fault=None):
        cmd = [
            PY,
            str(PEER),
            "--config",
            str(cfg_path),
            "--peer",
            "server",
            "--rpc-port",
            str(_free_udp_port()),
        ]
        if fault is not None:
            cmd.extend(["--fault", fault])
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.procs.append(proc)
        return proc

    def _stop_and_record(self, proc):
        if proc in self.procs:
            self.procs.remove(proc)
        for chunk in _stop_peers([proc]):
            self.captured_peer_bytes.extend(chunk)

    def test_poll_failures(self):
        """§6.1 punto 1: 401, 409, 503, 200 ilegible y conexion rechazada."""
        simple_cases = (
            ("401", 401, {"error": "bad_key"}),
            ("409", 409, {"error": "hello_required"}),
            ("503", 503, b""),
            ("ilegible", 200, b"not-json{"),
        )
        for name, code, body in simple_cases:
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory(prefix="dsbx-pe-") as tmp:
                    cfg_path = Path(tmp) / "dsbx_qa.json"
                    k0 = self._new_key()
                    k1 = self._new_key()
                    bridge = self._start_bridge()
                    _write_cfg(cfg_path, bridge.url, k0, 800)

                    bridge.plan(200, {"lease_ms": 3000, "ok": True})
                    bridge.plan(
                        code,
                        body,
                        before_reply=lambda p=cfg_path, u=bridge.url, k=k1: _write_cfg(p, u, k, 800),
                    )
                    bridge.plan(200, {"lease_ms": 3000, "ok": True}, hold_s=0.08)
                    bridge.plan(200, {"now_ms": 2.0, "ops": []})

                    proc = self._spawn_peer(cfg_path)
                    try:
                        self.assertTrue(bridge.wait_count(4, timeout=6.0), f"{name}: fewer than 4 requests")
                    finally:
                        self._stop_and_record(proc)
                        bridge.stop()

                    reqs = bridge.snapshot()
                    self.assertEqual((reqs[0].method, reqs[0].path), ("POST", "/hello"))
                    self.assertTrue(reqs[0].query.get("key") == k0, f"{name}: initial hello key mismatch")
                    self.assertEqual((reqs[1].method, reqs[1].path), ("GET", "/poll"))
                    self.assertTrue(reqs[1].query.get("key") == k0, f"{name}: initial poll key mismatch")

                    recovery = reqs[2]
                    self.assertEqual(
                        (recovery.method, recovery.path),
                        ("POST", "/hello"),
                        f"{name}: first request after failure must be POST /hello",
                    )
                    self.assertTrue(
                        recovery.query.get("key") == k1,
                        f"{name}: recovery hello did not carry K1",
                    )
                    self.assertIsInstance(recovery.json_body, dict)
                    self.assertEqual(recovery.json_body.get("proto"), "qa0")
                    self.assertEqual(recovery.json_body.get("peer"), "server")

                    elapsed_ms = (recovery.recv_s - reqs[1].sent_s) * 1000.0
                    self.assertGreaterEqual(elapsed_ms, 230.0, f"{name}: elapsed {elapsed_ms:.1f}ms < 230ms")
                    self.assertLessEqual(elapsed_ms, 650.0, f"{name}: elapsed {elapsed_ms:.1f}ms > 650ms")

                    polls_after = [r for r in reqs[2:] if r.path == "/poll"]
                    self.assertTrue(polls_after, f"{name}: expected resumed poll after hello 200")
                    for poll_req in polls_after:
                        self.assertGreaterEqual(
                            poll_req.recv_s,
                            recovery.sent_s,
                            f"{name}: poll arrived before recovery hello received its 200",
                        )
                        self.assertTrue(
                            poll_req.query.get("key") == k1,
                            f"{name}: resumed poll did not carry K1",
                        )

        with self.subTest(case="rechazada"):
            with tempfile.TemporaryDirectory(prefix="dsbx-pe-") as tmp:
                cfg_path = Path(tmp) / "dsbx_qa.json"
                k0 = self._new_key()
                k1 = self._new_key()
                bridge1 = self._start_bridge()
                bridge2 = self._start_bridge()
                _write_cfg(cfg_path, bridge1.url, k0, 800)

                def close_and_redirect():
                    bridge1.close_listener()
                    _write_cfg(cfg_path, bridge2.url, k1, 800)

                bridge1.plan(200, {"lease_ms": 3000, "ok": True})
                bridge1.plan(200, {"now_ms": 1.0, "ops": []}, before_reply=close_and_redirect)

                bridge2.plan(200, {"lease_ms": 3000, "ok": True}, hold_s=0.08)
                bridge2.plan(200, {"now_ms": 2.0, "ops": []})

                proc = self._spawn_peer(cfg_path)
                try:
                    self.assertTrue(
                        bridge2.wait_count(2, timeout=12.0),
                        "rechazada: second bridge did not receive recovery hello and poll",
                    )
                finally:
                    self._stop_and_record(proc)
                    bridge1.stop()
                    bridge2.stop()

                reqs1 = bridge1.snapshot()
                self.assertEqual(len(reqs1), 2, "rechazada: bridge1 should only see initial hello and poll")
                self.assertEqual((reqs1[0].method, reqs1[0].path), ("POST", "/hello"))
                self.assertEqual((reqs1[1].method, reqs1[1].path), ("GET", "/poll"))

                reqs2 = bridge2.snapshot()
                recovery = reqs2[0]
                self.assertEqual(
                    (recovery.method, recovery.path),
                    ("POST", "/hello"),
                    "rechazada: first request to new bridge URL must be POST /hello",
                )
                self.assertTrue(
                    recovery.query.get("key") == k1,
                    "rechazada: recovery hello on bridge2 did not carry K1",
                )
                elapsed_ms = (recovery.recv_s - reqs1[1].sent_s) * 1000.0
                self.assertGreaterEqual(
                    elapsed_ms,
                    230.0,
                    f"rechazada: elapsed {elapsed_ms:.1f}ms < 230ms since previous 200",
                )
                polls_after = [r for r in reqs2 if r.path == "/poll"]
                self.assertTrue(polls_after, "rechazada: expected poll after hello 200 on bridge2")
                for poll_req in polls_after:
                    self.assertGreaterEqual(
                        poll_req.recv_s,
                        recovery.sent_s,
                        "rechazada: poll arrived before recovery hello received its 200",
                    )
                    self.assertTrue(
                        poll_req.query.get("key") == k1,
                        "rechazada: resumed poll on bridge2 did not carry K1",
                    )

    def test_backoff_schedule_and_reset(self):
        """§6.1 punto 2: esperas 250, 500, 800 y 800 ms con retry_ms=800 y vuelta a 250 ms."""
        with tempfile.TemporaryDirectory(prefix="dsbx-pe-") as tmp:
            cfg_path = Path(tmp) / "dsbx_qa.json"
            k0 = self._new_key()
            bridge = self._start_bridge()
            _write_cfg(cfg_path, bridge.url, k0, 800)

            bridge.plan(200, {"lease_ms": 3000, "ok": True})  # 0: hello inicial -> 200
            bridge.plan(503, b"")                              # 1: poll -> 503 (espera 250)
            bridge.plan(503, b"")                              # 2: hello -> 503 (espera 500)
            bridge.plan(503, b"")                              # 3: hello -> 503 (espera 800)
            bridge.plan(503, b"")                              # 4: hello -> 503 (espera 800)
            bridge.plan(200, {"lease_ms": 3000, "ok": True})  # 5: hello -> 200 (n := 0)
            bridge.plan(200, {"now_ms": 5.0, "ops": []})      # 6: poll -> 200
            bridge.plan(503, b"")                              # 7: poll -> 503 (espera 250)
            bridge.plan(200, {"lease_ms": 3000, "ok": True})  # 8: hello -> 200

            proc = self._spawn_peer(cfg_path)
            try:
                self.assertTrue(bridge.wait_count(9, timeout=10.0), "fewer than 9 requests recorded")
            finally:
                self._stop_and_record(proc)
                bridge.stop()

            reqs = bridge.snapshot()[:9]
            expected_routes = [
                ("POST", "/hello"),
                ("GET", "/poll"),
                ("POST", "/hello"),
                ("POST", "/hello"),
                ("POST", "/hello"),
                ("POST", "/hello"),
                ("GET", "/poll"),
                ("GET", "/poll"),
                ("POST", "/hello"),
            ]
            self.assertEqual([(r.method, r.path) for r in reqs], expected_routes)

            pairs_and_targets = (
                (1, 2, 250.0),
                (2, 3, 500.0),
                (3, 4, 800.0),
                (4, 5, 800.0),
                (7, 8, 250.0),
            )
            for fail_idx, next_idx, target_ms in pairs_and_targets:
                wait_ms = (reqs[next_idx].recv_s - reqs[fail_idx].sent_s) * 1000.0
                self.assertGreaterEqual(
                    wait_ms,
                    target_ms - 20.0,
                    f"step {fail_idx}->{next_idx}: wait {wait_ms:.1f}ms < {target_ms - 20.0:.1f}ms",
                )
                self.assertLessEqual(
                    wait_ms,
                    target_ms + 400.0,
                    f"step {fail_idx}->{next_idx}: wait {wait_ms:.1f}ms > {target_ms + 400.0:.1f}ms",
                )

    def test_hello_failures_reload_retry_ms_and_reset_on_hello_200(self):
        """§3: fallos de hello (401, 409, 200 ilegible), relectura de retry_ms y n:=0 con hello 200."""
        with tempfile.TemporaryDirectory(prefix="dsbx-pe-") as tmp:
            cfg_path = Path(tmp) / "dsbx_qa.json"
            k0 = self._new_key()
            k1 = self._new_key()
            bridge = self._start_bridge()
            _write_cfg(cfg_path, bridge.url, k0, 950)

            bridge.plan(
                401,
                {"error": "bad_key"},
                before_reply=lambda: _write_cfg(cfg_path, bridge.url, k1, 520),
            )                                                  # 0: hello -> 401 (espera 250, relee retry=520 y K1)
            bridge.plan(409, {"error": "proto_mismatch"})     # 1: hello -> 409 (espera 500)
            bridge.plan(200, b"not-a-json-hello")             # 2: hello -> 200 ilegible (espera min(1000,520)=520)
            bridge.plan(200, {"lease_ms": 3000, "ok": True})  # 3: hello -> 200 (n := 0 sin poll 200)
            bridge.plan(503, b"")                              # 4: poll -> 503 (espera 250)
            bridge.plan(200, {"lease_ms": 3000, "ok": True})  # 5: hello -> 200

            proc = self._spawn_peer(cfg_path)
            try:
                self.assertTrue(bridge.wait_count(6, timeout=8.0), "fewer than 6 requests recorded")
            finally:
                self._stop_and_record(proc)
                bridge.stop()

            reqs = bridge.snapshot()[:6]
            self.assertEqual(
                [(r.method, r.path) for r in reqs],
                [
                    ("POST", "/hello"),
                    ("POST", "/hello"),
                    ("POST", "/hello"),
                    ("POST", "/hello"),
                    ("GET", "/poll"),
                    ("POST", "/hello"),
                ],
            )
            self.assertTrue(reqs[0].query.get("key") == k0)
            for idx in (1, 2, 3, 4, 5):
                self.assertTrue(reqs[idx].query.get("key") == k1, f"request {idx} missing reloaded key K1")

            w1 = (reqs[1].recv_s - reqs[0].sent_s) * 1000.0
            w2 = (reqs[2].recv_s - reqs[1].sent_s) * 1000.0
            w3 = (reqs[3].recv_s - reqs[2].sent_s) * 1000.0
            w4 = (reqs[5].recv_s - reqs[4].sent_s) * 1000.0
            self.assertGreaterEqual(w1, 230.0)
            self.assertLessEqual(w1, 650.0)
            self.assertGreaterEqual(w2, 480.0)
            self.assertLessEqual(w2, 900.0)
            self.assertGreaterEqual(w3, 500.0)
            self.assertLessEqual(w3, 850.0)
            self.assertGreaterEqual(w4, 230.0)
            self.assertLessEqual(w4, 650.0)

    def test_unusable_config_after_failure_waits_in_p2(self):
        """§3 paso 2 y P2: si la relectura no es usable, no hace peticiones hasta que lo sea."""
        with tempfile.TemporaryDirectory(prefix="dsbx-pe-") as tmp:
            cfg_path = Path(tmp) / "dsbx_qa.json"
            k0 = self._new_key()
            k1 = self._new_key()
            bridge1 = self._start_bridge()
            bridge2 = self._start_bridge()
            _write_cfg(cfg_path, bridge1.url, k0, 350)

            bridge1.plan(200, {"lease_ms": 3000, "ok": True})
            bridge1.plan(
                503,
                b"",
                before_reply=lambda: _write_cfg(cfg_path, "http://example.com:80/", k1, 350),
            )
            bridge2.plan(200, {"lease_ms": 3000, "ok": True})

            proc = self._spawn_peer(cfg_path)
            try:
                self.assertTrue(bridge1.wait_count(2, timeout=5.0))
                time.sleep(0.45)
                self.assertEqual(len(bridge1.snapshot()), 2, "peer made requests with unusable config")
                self.assertEqual(len(bridge2.snapshot()), 0, "bridge2 saw premature requests")
                _write_cfg(cfg_path, bridge2.url, k1, 350)
                self.assertTrue(bridge2.wait_count(1, timeout=5.0), "peer did not resume once config became usable")
            finally:
                self._stop_and_record(proc)
                bridge1.stop()
                bridge2.stop()

            req = bridge2.snapshot()[0]
            self.assertEqual((req.method, req.path), ("POST", "/hello"))
            self.assertTrue(req.query.get("key") == k1)

    def test_result_failure_follows_p6_without_touching_n_or_hello(self):
        """§3 y P6: un resultado fallido reintenta segun P6, no fuerza hello y no toca n."""
        with tempfile.TemporaryDirectory(prefix="dsbx-pe-") as tmp:
            cfg_path = Path(tmp) / "dsbx_qa.json"
            k0 = self._new_key()
            bridge = self._start_bridge()
            _write_cfg(cfg_path, bridge.url, k0, 800)
            peer_inst = {"value": ""}

            def on_hello(_method, _path, _query, body):
                peer_inst["value"] = (body or {}).get("inst", "")
                raw = json.dumps({"lease_ms": 3000, "ok": True}, separators=(",", ":")).encode("utf-8")
                return 200, raw, None, 0.0, "application/json"

            def deliver_one(_method, _path, _query, _body):
                op = {
                    "args": {
                        "client_inst": "",
                        "count": 0,
                        "fog": 0.0,
                        "interval_ms": 0,
                        "pos": [0, 0, 0],
                        "seq0": 0,
                        "x": 0.0,
                        "ypr": [0, 0, 0],
                        "z": 0.0,
                    },
                    "inst": peer_inst["value"],
                    "issued_ms": 1.0,
                    "op_id": "op-res-1",
                    "ttl_ms": 5000,
                    "verb": "srv_read",
                }
                raw = json.dumps({"now_ms": 1.0, "ops": [op]}, separators=(",", ":")).encode("utf-8")
                return 200, raw, None, 0.0, "application/json"

            bridge.steps.append(on_hello)                      # 0: hello -> 200
            bridge.steps.append(deliver_one)                   # 1: poll -> entrega op-res-1
            bridge.plan(401, {"error": "bad_key"})             # 2: result intento 1 -> 401 (espera P6 250)
            bridge.plan(503, b"")                              # 3: result intento 2 -> 503 (espera P6 500)
            bridge.plan(200, {"ok": True})                     # 4: result intento 3 -> 200
            bridge.plan(503, b"")                              # 5: siguiente es poll (no hello); falla -> n=1 (250)
            bridge.plan(200, {"lease_ms": 3000, "ok": True})  # 6: hello tras poll fallido

            proc = self._spawn_peer(cfg_path)
            try:
                self.assertTrue(bridge.wait_count(7, timeout=8.0), "fewer than 7 requests recorded")
            finally:
                self._stop_and_record(proc)
                bridge.stop()

            reqs = bridge.snapshot()[:7]
            self.assertEqual(
                [(r.method, r.path) for r in reqs],
                [
                    ("POST", "/hello"),
                    ("GET", "/poll"),
                    ("POST", "/result"),
                    ("POST", "/result"),
                    ("POST", "/result"),
                    ("GET", "/poll"),
                    ("POST", "/hello"),
                ],
            )
            p6_gap1_ms = (reqs[3].recv_s - reqs[2].sent_s) * 1000.0
            p6_gap2_ms = (reqs[4].recv_s - reqs[3].sent_s) * 1000.0
            poll_fail_wait_ms = (reqs[6].recv_s - reqs[5].sent_s) * 1000.0
            self.assertGreaterEqual(p6_gap1_ms, 230.0)
            self.assertLessEqual(p6_gap1_ms, 650.0)
            self.assertGreaterEqual(p6_gap2_ms, 480.0)
            self.assertLessEqual(p6_gap2_ms, 900.0)
            self.assertGreaterEqual(poll_fail_wait_ms, 230.0)
            self.assertLessEqual(poll_fail_wait_ms, 650.0)

    def test_no_key_reload_keeps_url_and_key_after_failure(self):
        """§3: con --fault no_key_reload nunca relee url ni clave tras un fallo."""
        with tempfile.TemporaryDirectory(prefix="dsbx-pe-") as tmp:
            cfg_path = Path(tmp) / "dsbx_qa.json"
            k0 = self._new_key()
            k1 = self._new_key()
            bridge1 = self._start_bridge()
            bridge2 = self._start_bridge()
            _write_cfg(cfg_path, bridge1.url, k0, 800)

            bridge1.plan(200, {"lease_ms": 3000, "ok": True})
            bridge1.plan(
                503,
                b"",
                before_reply=lambda: _write_cfg(cfg_path, bridge2.url, k1, 800),
            )
            bridge1.plan(200, {"lease_ms": 3000, "ok": True})

            proc = self._spawn_peer(cfg_path, fault="no_key_reload")
            try:
                self.assertTrue(bridge1.wait_count(3, timeout=6.0), "bridge1 did not receive retry hello")
            finally:
                self._stop_and_record(proc)
                bridge1.stop()
                bridge2.stop()

            reqs1 = bridge1.snapshot()
            self.assertEqual(len(bridge2.snapshot()), 0, "no_key_reload should not adopt new URL")
            self.assertEqual((reqs1[2].method, reqs1[2].path), ("POST", "/hello"))
            self.assertTrue(reqs1[2].query.get("key") == k0, "no_key_reload should keep original key K0")
            elapsed_ms = (reqs1[2].recv_s - reqs1[1].sent_s) * 1000.0
            self.assertGreaterEqual(elapsed_ms, 230.0)
            self.assertLessEqual(elapsed_ms, 650.0)


if __name__ == "__main__":
    unittest.main()
