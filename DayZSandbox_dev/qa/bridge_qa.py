"""Bridge QA v0 (brief F0.1 §5-§6). Solo escucha en 127.0.0.1."""

import json
import hmac
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ARG_KEYS = ("x", "z", "fog", "pos", "ypr", "count", "interval_ms", "seq0", "client_inst")


def full_args(args):
    base = {
        "client_inst": "",
        "count": 0,
        "fog": 0.0,
        "interval_ms": 0,
        "pos": [0, 0, 0],
        "seq0": 0,
        "x": 0.0,
        "ypr": [0, 0, 0],
        "z": 0.0,
    }
    for key, value in (args or {}).items():
        if key not in base:
            continue
        base[key] = list(value) if isinstance(value, list) else value
    return base


class QABridge:
    def __init__(self, hold_ms, lease_ms, sink, port=0):
        self.hold_ms = hold_ms
        self.lease_ms = lease_ms
        self.sink = sink
        self.t0 = time.monotonic_ns()
        self.cv = threading.Condition()
        self.keys = {}
        self.inst = {}
        self.queue = []
        self.results = {}
        self.events = []
        self.cut_until = {}
        self.drop = set()
        self.force = set()
        self._seq = 0
        self.failure = None
        self._stopping = False
        self._sink_closed = False
        self._live = 0
        self.STOP_JOIN_S = 5.0
        handler = self._handler()
        self.httpd = _Server(("127.0.0.1", port), handler)
        self.httpd.qa_bridge = self
        self._thread = None


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True

    def handle_error(self, request, client_address):
        bridge = getattr(self, "qa_bridge", None)
        if bridge is not None:
            bridge.note_handler_error()

    def process_request_thread(self, request, client_address):
        bridge = self.qa_bridge
        try:
            super().process_request_thread(request, client_address)
        finally:
            if bridge.cv.acquire(timeout=bridge.STOP_JOIN_S):
                try:
                    bridge._live -= 1
                    bridge.cv.notify_all()
                finally:
                    bridge.cv.release()
            else:
                bridge._live -= 1

    def process_request(self, request, client_address):
        bridge = self.qa_bridge
        if bridge._stopping:
            try:
                request.close()
            except OSError:
                pass
            return
        if not bridge.cv.acquire(timeout=bridge.STOP_JOIN_S):
            try:
                request.close()
            except OSError:
                pass
            if bridge.failure is None:
                bridge.failure = TimeoutError("handler still running after stop")
            return
        try:
            if bridge._stopping:
                request.close()
                return
            bridge._live += 1
        finally:
            bridge.cv.release()
        try:
            super().process_request(request, client_address)
        except Exception:
            if bridge.cv.acquire(timeout=bridge.STOP_JOIN_S):
                try:
                    bridge._live -= 1
                    bridge.cv.notify_all()
                finally:
                    bridge.cv.release()
            else:
                bridge._live -= 1
            raise


class QABridge(QABridge):
    def _handler(self):
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

    @property
    def port(self):
        return self.httpd.server_address[1]

    def start(self):
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def note_handler_error(self):
        exc = sys.exception()
        if exc is None or self.failure is not None:
            return
        self.failure = exc

    def stop(self):
        self._stopping = True
        deadline = time.monotonic() + self.STOP_JOIN_S
        if self.cv.acquire(timeout=max(0.0, deadline - time.monotonic())):
            try:
                self.cv.notify_all()
            finally:
                self.cv.release()
        self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        while time.monotonic() < deadline:
            left = deadline - time.monotonic()
            if not self.cv.acquire(timeout=min(0.05, left)):
                continue
            try:
                idle = self._live == 0
            finally:
                self.cv.release()
            if idle:
                break
            time.sleep(0.01)
        if self._live != 0 and self.failure is None:
            self.failure = TimeoutError("handler still running after stop")
        self._sink_closed = True

    def now_ms(self):
        return round((time.monotonic_ns() - self.t0) / 1e6, 3)

    def set_peer_key(self, peer, key):
        with self.cv:
            self.keys[peer] = key

    def registered(self, peer):
        with self.cv:
            return self.inst.get(peer)

    def enqueue(self, peer, verb, args, target_inst, ttl_ms, op_id=None, issued_ms=None):
        args = full_args(args)
        with self.cv:
            if op_id is None:
                self._seq += 1
                op_id = f"op-{self._seq}"
            issued = self.now_ms() if issued_ms is None else issued_ms
            self.queue.append(
                {
                    "args": args,
                    "force": op_id in self.force,
                    "inst": target_inst,
                    "issued_ms": issued,
                    "op_id": op_id,
                    "peer": peer,
                    "ttl_ms": int(ttl_ms),
                    "verb": verb,
                }
            )
            self._emit(
                {
                    "args": args,
                    "ev": "enq",
                    "inst": target_inst,
                    "op_id": op_id,
                    "peer": peer,
                    "verb": verb,
                }
            )
            self.cv.notify_all()
            return op_id

    def force_deliver(self, op_id):
        with self.cv:
            self.force.add(op_id)
            for order in self.queue:
                if order["op_id"] == op_id:
                    order["force"] = True
            self._emit({"ev": "force", "op_id": op_id})
            self.cv.notify_all()

    def cut(self, peer, ms):
        with self.cv:
            self.cut_until[peer] = time.monotonic() + ms / 1000.0
            self._emit({"ev": "cut_start", "peer": peer})
            self.cv.notify_all()
        timer = threading.Timer(ms / 1000.0, self._cut_end, args=(peer,))
        timer.daemon = True
        timer.start()

    def _cut_end(self, peer):
        with self.cv:
            self.cut_until.pop(peer, None)
            self._emit({"ev": "cut_end", "peer": peer})
            self.cv.notify_all()

    def drop_results(self, op_id, on):
        with self.cv:
            if on:
                self.drop.add(op_id)
            else:
                self.drop.discard(op_id)

    def wait_result(self, op_id, after_t_ms, timeout_ms):
        deadline = time.monotonic() + timeout_ms / 1000.0
        with self.cv:
            while True:
                for rec in self.results.get(op_id, ()):
                    if rec["t_ms"] >= after_t_ms:
                        return rec["result"]
                self._raise_failure()
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.cv.wait(left)

    def wait_event(self, pred, timeout_ms):
        deadline = time.monotonic() + timeout_ms / 1000.0
        with self.cv:
            index = 0
            while True:
                while index < len(self.events):
                    ev = self.events[index]
                    index += 1
                    if pred(ev):
                        return ev
                self._raise_failure()
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.cv.wait(left)

    def _raise_failure(self):
        if self.failure is not None:
            raise self.failure.with_traceback(self.failure.__traceback__)

    def _emit(self, fields):
        if self._sink_closed:
            return
        row = {"t_ms": self.now_ms()}
        for key, value in fields.items():
            if value is not None:
                row[key] = value
        self.events.append(row)
        try:
            self.sink(row)
        except Exception as exc:
            if self.failure is None:
                self.failure = exc
            raise
        self.cv.notify_all()

    def _cut_active(self, peer):
        until = self.cut_until.get(peer)
        return until is not None and time.monotonic() < until

    def _dispatch(self, handler):
        parts = urlsplit(handler.path)
        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        length = int(handler.headers.get("Content-Length") or 0)
        raw = handler.rfile.read(length) if length else b""
        body = {}
        if raw:
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                self._send(handler, 400, {"error": "bad_json"})
                return
        path = parts.path
        key = query.get("key", "")
        with self.cv:
            if path == "/hello" and handler.command == "POST":
                peer = body.get("peer") if isinstance(body, dict) else None
                if peer in ("server", "client") and self._cut_active(peer):
                    self._send(handler, 503, {"error": "cut"})
                    return
                if not self._key_ok(peer, key):
                    self._emit({"ev": "auth_reject", "http": 401, "peer": peer})
                    self._send(handler, 401, {"error": "bad_key"})
                    return
                self._hello(handler, body)
                return
            peer = query.get("peer")
            if peer in ("server", "client") and self._cut_active(peer):
                self._send(handler, 503, {"error": "cut"})
                return
            if not self._key_ok(peer, key):
                self._emit({"ev": "auth_reject", "http": 401, "peer": peer})
                self._send(handler, 401, {"error": "bad_key"})
                return
            if path == "/poll" and handler.command == "GET":
                self._poll(handler, query)
            elif path == "/result" and handler.command == "POST":
                self._result(handler, query, body)
            else:
                self._send(handler, 404, {"error": "not_found"})

    def _key_ok(self, peer, key):
        expected = self.keys.get(peer)
        if not expected or not key:
            return False
        return hmac.compare_digest(str(expected), str(key))

    def _hello(self, handler, body):
        peer = body.get("peer")
        if body.get("proto") != "qa0":
            self._emit({"ev": "inst_reject", "http": 409, "peer": peer, "reason": "proto_mismatch"})
            self._send(handler, 409, {"error": "proto_mismatch"})
            return
        inst = body.get("inst")
        self.inst[peer] = inst
        self._emit(
            {
                "args": {
                    "build": body.get("build"),
                    "inst": inst,
                    "peer": peer,
                    "probe_ver": body.get("probe_ver"),
                    "proto": body.get("proto"),
                },
                "ev": "hello",
                "http": 200,
                "inst": inst,
                "peer": peer,
            }
        )
        self._send(handler, 200, {"lease_ms": self.lease_ms, "ok": True})

    def _poll(self, handler, query):
        peer = query.get("peer")
        inst = query.get("inst")
        if self.inst.get(peer) != inst:
            self._emit({"ev": "inst_reject", "http": 409, "peer": peer, "inst": inst, "reason": "hello_required"})
            self._send(handler, 409, {"error": "hello_required"})
            return
        try:
            frame = int(float(query.get("frame", "0")))
        except ValueError:
            frame = 0
        try:
            tick_s = float(query.get("tick_s", "0"))
        except ValueError:
            tick_s = 0.0
        start = time.monotonic()
        deadline = start + self.hold_ms / 1000.0
        ops = []
        while True:
            if self._stopping:
                break
            if self.inst.get(peer) != inst:
                self._emit({"ev": "inst_reject", "http": 409, "peer": peer, "inst": inst, "reason": "hello_required"})
                self._send(handler, 409, {"error": "hello_required"})
                return
            if self._cut_active(peer):
                self._send(handler, 503, {"error": "cut"})
                return
            ops = self._take(peer, inst)
            if ops or time.monotonic() >= deadline:
                break
            self.cv.wait(max(0.0, deadline - time.monotonic()))
        if self.inst.get(peer) != inst:
            self._emit({"ev": "inst_reject", "http": 409, "peer": peer, "inst": inst, "reason": "hello_required"})
            self._send(handler, 409, {"error": "hello_required"})
            return
        held = round((time.monotonic() - start) * 1000.0, 3)
        now = self.now_ms()
        self._emit(
            {
                "ev": "poll",
                "frame": frame,
                "held_ms": held,
                "http": 200,
                "inst": inst,
                "n_ops": len(ops),
                "peer": peer,
                "tick_s": tick_s,
            }
        )
        for op in ops:
            self._emit(
                {
                    "args": op["args"],
                    "ev": "deliver",
                    "inst": op["inst"],
                    "op_id": op["op_id"],
                    "peer": peer,
                    "verb": op["verb"],
                }
            )
        self._send(handler, 200, {"now_ms": now, "ops": ops})

    def _take(self, peer, inst):
        now = self.now_ms()
        kept = []
        ops = []
        for order in self.queue:
            if order["peer"] != peer:
                kept.append(order)
                continue
            age = now - order["issued_ms"]
            forced = order["op_id"] in self.force or order["force"]
            if not forced and age >= order["ttl_ms"]:
                self._emit(
                    {
                        "ev": "expire",
                        "op_id": order["op_id"],
                        "peer": peer,
                        "reason": "expired",
                        "verb": order["verb"],
                    }
                )
                continue
            deliver = forced or (order["inst"] == inst and age < order["ttl_ms"])
            if deliver and len(ops) < 16:
                ops.append(
                    {
                        "args": order["args"],
                        "inst": order["inst"],
                        "issued_ms": order["issued_ms"],
                        "op_id": order["op_id"],
                        "ttl_ms": order["ttl_ms"],
                        "verb": order["verb"],
                    }
                )
                self.force.discard(order["op_id"])
            else:
                kept.append(order)
        self.queue = kept
        return ops

    def _result(self, handler, query, body):
        peer = query.get("peer")
        inst = query.get("inst")
        if self.inst.get(peer) != inst:
            self._emit({"ev": "inst_reject", "http": 409, "peer": peer, "inst": inst, "reason": "hello_required"})
            self._send(handler, 409, {"error": "hello_required"})
            return
        op_id = body.get("op_id") if isinstance(body, dict) else None
        if op_id in self.drop:
            self._emit({"ev": "result_drop", "http": 503, "op_id": op_id, "peer": peer})
            self._send(handler, 503, {"error": "drop"})
            return
        self.results.setdefault(op_id, []).append({"result": body, "t_ms": self.now_ms()})
        self._emit({"ev": "result", "http": 200, "op_id": op_id, "peer": peer, "result": body})
        self._send(handler, 200, {"ok": True})

    def _send(self, handler, code, obj):
        raw = json.dumps(obj, allow_nan=False, separators=(",", ":")).encode("utf-8")
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)
