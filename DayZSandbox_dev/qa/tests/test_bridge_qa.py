"""Puente QA v0 aislado (brief F0.1 §10.2 punto 5)."""

import json
import threading
import time
import unittest
import urllib.error
import urllib.request

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


if __name__ == "__main__":
    unittest.main()
