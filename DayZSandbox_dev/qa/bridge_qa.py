"""Bridge QA v0 (brief F0.1 §5-§6, F0.3-0 §2.2, §5.4, §13 A4, §14). Solo escucha en 127.0.0.1."""

import hmac
import json
import math
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import wire

ARG_KEYS = (
    "x",
    "z",
    "fog",
    "pos",
    "ypr",
    "count",
    "interval_ms",
    "seq0",
    "client_inst",
    "sk",
    "sv",
    "nk",
    "nv",
    "ncol",
    "ncell",
    "scol",
    "scell",
    "rows",
)


def full_args(args):
    base = {
        "client_inst": "",
        "count": 0,
        "fog": 0.0,
        "interval_ms": 0,
        "ncell": [],
        "ncol": [],
        "nk": [],
        "nv": [],
        "pos": [0, 0, 0],
        "rows": 0,
        "scell": [],
        "scol": [],
        "seq0": 0,
        "sk": [],
        "sv": [],
        "x": 0.0,
        "ypr": [0, 0, 0],
        "z": 0.0,
    }
    for key, value in (args or {}).items():
        if key not in base:
            continue
        base[key] = list(value) if isinstance(value, list) else value
    wire.validate_payload(base)
    # D10 (§15): toda orden pasa por aqui (enqueue y las medidas de BASE-01); una cadena de args de mas de 1000
    # caracteres se rechaza antes de salir, porque la sonda la leeria cortada en 1023.
    wire.check_arg_strings(base)
    return base


def _strip_qa_fault(args):
    copied = {}
    for k, v in args.items():
        copied[k] = list(v) if isinstance(v, list) else v
    sk = copied.get("sk")
    sv = copied.get("sv")
    if isinstance(sk, list) and isinstance(sv, list) and "qa_fault" in sk:
        idx = sk.index("qa_fault")
        sk.pop(idx)
        if idx < len(sv):
            sv.pop(idx)
    return copied


def _mode_active(val):
    if isinstance(val, bool):
        return bool(val)
    if isinstance(val, float) and math.isinf(val) and val > 0:
        return True
    if isinstance(val, (int, float)):
        return val > 0 or val < 0
    return False


def _mode_decrement(val):
    if isinstance(val, bool):
        return 0
    if isinstance(val, float) and math.isinf(val):
        return val
    if isinstance(val, (int, float)) and val < 0:
        return val
    if isinstance(val, (int, float)) and val > 0:
        return val - 1
    return 0


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


class QABridge:
    def __init__(self, hold_ms, lease_ms, sink, port=0, *, test_mode_sink=None):
        self.hold_ms = hold_ms
        self.lease_ms = lease_ms
        self.sink = sink
        self.run_id = secrets.token_hex(4)
        self.t0 = time.monotonic_ns()
        self.cv = threading.Condition()
        self.keys = {}
        self.inst = {}
        self.queue = []
        self.delivered = {}
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
        self._timers = set()
        self._hello_503 = 0
        self._hello_ok_false = 0
        self._ack_ok_false = 0
        self.test_mode_events = []
        self.test_mode_sink = test_mode_sink
        self.STOP_JOIN_S = 5.0
        handler = self._handler()
        self.httpd = _Server(("127.0.0.1", port), handler)
        self.httpd.qa_bridge = self
        self._thread = None

    def _record_test_mode(self, mode, action, **extra):
        val = extra.get("count")
        if isinstance(val, float) and math.isinf(val):
            extra["count"] = "inf"
        row = {"t_ms": self.now_ms(), "ev": "test_mode", "mode": mode, "action": action}
        row.update({k: v for k, v in extra.items() if v is not None})
        self.test_mode_events.append(row)
        if self.test_mode_sink is not None:
            self.test_mode_sink(row)

    @property
    def hello_503(self):
        return self._hello_503

    @hello_503.setter
    def hello_503(self, value):
        with self.cv:
            self._hello_503 = value
            self._record_test_mode("hello_503", "set", count=value)

    @property
    def hello_ok_false(self):
        return self._hello_ok_false

    @hello_ok_false.setter
    def hello_ok_false(self, value):
        with self.cv:
            self._hello_ok_false = value
            self._record_test_mode("hello_ok_false", "set", count=value)

    @property
    def ack_ok_false(self):
        return self._ack_ok_false

    @ack_ok_false.setter
    def ack_ok_false(self, value):
        with self.cv:
            self._ack_ok_false = value
            self._record_test_mode("ack_ok_false", "set", count=value)

    def _consume_mode(self, attr_name, mode_name, **extra):
        cur = getattr(self, attr_name)
        if not _mode_active(cur):
            return False
        nxt = _mode_decrement(cur)
        setattr(self, attr_name, nxt)
        self._record_test_mode(mode_name, "intercept", remaining=nxt, **extra)
        return True

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

    def _spawn_timer(self, delay_s, fn, args):
        timer = None

        def _wrapper():
            with self.cv:
                self._timers.discard(timer)
            fn(*args)

        timer = threading.Timer(max(0.0, delay_s), _wrapper)
        timer.daemon = True
        self._timers.add(timer)
        timer.start()
        return timer

    def stop(self):
        self._stopping = True
        deadline = time.monotonic() + self.STOP_JOIN_S
        if self.cv.acquire(timeout=max(0.0, deadline - time.monotonic())):
            try:
                timers = list(self._timers)
                self._timers.clear()
                self.cv.notify_all()
            finally:
                self.cv.release()
            for t in timers:
                t.cancel()
        # shutdown() espera a que salga serve_forever(): sin start() no vuelve nunca (R2-1).
        if self._thread is not None:
            self.httpd.shutdown()
        self.httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=max(0.0, deadline - time.monotonic()))
        while time.monotonic() < deadline:
            left = deadline - time.monotonic()
            if left <= 0:
                break
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
            auto_id = op_id is None
            cand_id = f"op-{self.run_id}-{self._seq + 1}" if auto_id else op_id
            issued = self.now_ms() if issued_ms is None else issued_ms
            ttl_int = int(ttl_ms)
            wire_order = {
                "args": args,
                "inst": target_inst,
                "issued_ms": issued,
                "op_id": cand_id,
                "ttl_ms": ttl_int,
                "verb": verb,
            }
            probe_now = max(float(issued), 99999999.999)
            if len(wire.poll_wire_bytes(wire_order, now_ms=probe_now)) > wire.WIRE_CAP:
                raise ValueError("poll body exceeds WIRE_CAP")
            if auto_id:
                self._seq += 1
            self.queue.append(
                {
                    "args": args,
                    "force": cand_id in self.force,
                    "inst": target_inst,
                    "issued_ms": issued,
                    "op_id": cand_id,
                    "peer": peer,
                    "ttl_ms": ttl_int,
                    "verb": verb,
                }
            )
            self._emit(
                {
                    "args": _strip_qa_fault(args),
                    "ev": "enq",
                    "inst": target_inst,
                    "op_id": cand_id,
                    "peer": peer,
                    "verb": verb,
                }
            )
            self.cv.notify_all()
            return cand_id

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
            if not self._stopping:
                self._spawn_timer(ms / 1000.0, self._cut_end, (peer,))

    def _cut_end(self, peer):
        with self.cv:
            self.cut_until.pop(peer, None)
            if self._stopping or self._sink_closed:
                return
            self._emit({"ev": "cut_end", "peer": peer})
            self.cv.notify_all()

    def _on_lost_timer(self, _op_id):
        with self.cv:
            if self._stopping or self._sink_closed:
                return
            if self.delivered:
                self._expire_delivered(self.now_ms())

    def _expire_delivered(self, now):
        for oid, rec in list(self.delivered.items()):
            if now >= rec["deadline_ms"]:
                self.delivered.pop(oid, None)
                self._emit(
                    {
                        "ev": "lost",
                        "inst": rec["inst"],
                        "op_id": oid,
                        "peer": rec["peer"],
                        "reason": "result_lost",
                        "verb": rec["verb"],
                    }
                )

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
                if self.delivered:
                    self._expire_delivered(self.now_ms())
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
                if self.delivered:
                    self._expire_delivered(self.now_ms())
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
            except (UnicodeError, json.JSONDecodeError) as exc:
                if isinstance(exc, json.JSONDecodeError):
                    err = f"{exc.msg} at {exc.pos}"
                else:
                    err = f"{exc.reason} at {exc.start}"
                with self.cv:
                    self._emit(
                        {
                            "ev": "bad_body",
                            "http": 400,
                            "peer": query.get("peer") or "",
                            "path": parts.path,
                            "len": len(raw),
                            "err": err,
                        }
                    )
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
                self._result(handler, query, body, len(raw))
            else:
                self._send(handler, 404, {"error": "not_found"})

    def _key_ok(self, peer, key):
        expected = self.keys.get(peer)
        if not expected or not key:
            return False
        return hmac.compare_digest(str(expected), str(key))

    def _hello(self, handler, body):
        peer = body.get("peer")
        inst = body.get("inst")
        hello_args = {
            "build": body.get("build"),
            "inst": inst,
            "peer": peer,
            "probe_ver": body.get("probe_ver"),
            "proto": body.get("proto"),
        }
        if self._consume_mode("_hello_503", "hello_503", peer=peer, inst=inst):
            self._emit(
                {
                    "args": hello_args,
                    "ev": "hello",
                    "http": 503,
                    "inst": inst,
                    "peer": peer,
                }
            )
            self._send(handler, 503, {"error": "unavailable"})
            return
        if body.get("proto") != "qa0":
            self._emit({"ev": "inst_reject", "http": 409, "peer": peer, "reason": "proto_mismatch"})
            self._send(handler, 409, {"error": "proto_mismatch"})
            return
        if self._consume_mode("_hello_ok_false", "hello_ok_false", peer=peer, inst=inst):
            self.inst.pop(peer, None)
            self._emit(
                {
                    "args": hello_args,
                    "ev": "hello",
                    "http": 200,
                    "inst": inst,
                    "ok": False,
                    "peer": peer,
                }
            )
            self._send(handler, 200, {"lease_ms": self.lease_ms, "ok": False})
            return
        self.inst[peer] = inst
        self._emit(
            {
                "args": hello_args,
                "ev": "hello",
                "http": 200,
                "inst": inst,
                "ok": True,
                "peer": peer,
            }
        )
        self._send(handler, 200, {"lease_ms": self.lease_ms, "ok": True})

    def _poll(self, handler, query):
        if self.delivered:
            self._expire_delivered(self.now_ms())
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
        if query.get("deliver") == "0":
            now = self.now_ms()
            resp_raw = json.dumps({"now_ms": now, "ops": []}, allow_nan=False, separators=(",", ":")).encode("utf-8")
            self._emit(
                {
                    "body_len": len(resp_raw),
                    "ev": "keepalive",
                    "frame": frame,
                    "http": 200,
                    "inst": inst,
                    "n_ops": 0,
                    "now_ms": now,
                    "peer": peer,
                    "tick_s": tick_s,
                }
            )
            self._send_raw(handler, 200, resp_raw)
            return

        start = time.monotonic()
        deadline = start + self.hold_ms / 1000.0
        ops = []
        take_now = None
        overflow = None
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
            ops, take_now, overflow = self._take(peer, inst)
            if overflow is not None or ops or time.monotonic() >= deadline:
                break
            self.cv.wait(max(0.0, deadline - time.monotonic()))
        if overflow is not None:
            ov_op, ov_len, ov_now = overflow
            self._emit(
                {
                    "body_len": ov_len,
                    "ev": "wire_cap_exceeded",
                    "http": 500,
                    "inst": inst,
                    "n_ops": 1,
                    "now_ms": ov_now,
                    "op_ids": [ov_op["op_id"]],
                    "peer": peer,
                    "wire_cap": wire.WIRE_CAP,
                }
            )
            self._send(handler, 500, {"error": "wire_cap_exceeded"})
            return
        if self.inst.get(peer) != inst:
            if ops:
                restored = [
                    {
                        "args": op["args"],
                        "force": False,
                        "inst": op["inst"],
                        "issued_ms": op["issued_ms"],
                        "op_id": op["op_id"],
                        "peer": peer,
                        "ttl_ms": op["ttl_ms"],
                        "verb": op["verb"],
                    }
                    for op in ops
                ]
                self.queue = restored + self.queue
            self._emit({"ev": "inst_reject", "http": 409, "peer": peer, "inst": inst, "reason": "hello_required"})
            self._send(handler, 409, {"error": "hello_required"})
            return
        held = round((time.monotonic() - start) * 1000.0, 3)
        now = take_now if ops and take_now is not None else self.now_ms()
        resp_obj = {"now_ms": now, "ops": ops}
        resp_raw = json.dumps(resp_obj, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(resp_raw) > wire.WIRE_CAP:
            if ops:
                restored = [
                    {
                        "args": op["args"],
                        "force": False,
                        "inst": op["inst"],
                        "issued_ms": op["issued_ms"],
                        "op_id": op["op_id"],
                        "peer": peer,
                        "ttl_ms": op["ttl_ms"],
                        "verb": op["verb"],
                    }
                    for op in ops
                ]
                self.queue = restored + self.queue
            self._emit(
                {
                    "body_len": len(resp_raw),
                    "ev": "wire_cap_exceeded",
                    "http": 500,
                    "inst": inst,
                    "n_ops": len(ops),
                    "now_ms": now,
                    "op_ids": [op["op_id"] for op in ops],
                    "peer": peer,
                    "wire_cap": wire.WIRE_CAP,
                }
            )
            self._send(handler, 500, {"error": "wire_cap_exceeded"})
            return
        self._emit(
            {
                "body_len": len(resp_raw),
                "ev": "poll",
                "frame": frame,
                "held_ms": held,
                "http": 200,
                "inst": inst,
                "n_ops": len(ops),
                "now_ms": now,
                "op_ids": [op["op_id"] for op in ops],
                "peer": peer,
                "tick_s": tick_s,
            }
        )
        for op in ops:
            self._emit(
                {
                    "args": _strip_qa_fault(op["args"]),
                    "ev": "deliver",
                    "inst": op["inst"],
                    "op_id": op["op_id"],
                    "peer": peer,
                    "verb": op["verb"],
                }
            )
            lost_delay_ms = float(op["ttl_ms"]) + 1750.0 + 2000.0
            self.delivered[op["op_id"]] = {
                "deadline_ms": now + lost_delay_ms,
                "delivered_ms": now,
                "inst": inst,
                "op_id": op["op_id"],
                "peer": peer,
                "verb": op["verb"],
            }
            if not self._stopping:
                self._spawn_timer(lost_delay_ms / 1000.0, self._on_lost_timer, (op["op_id"],))
        self._send_raw(handler, 200, resp_raw)

    def _take(self, peer, inst):
        now = self.now_ms()
        if self.delivered:
            self._expire_delivered(now)
        kept = []
        ops = []
        stop_adding = False
        for idx, order in enumerate(self.queue):
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
            if not deliver or stop_adding or len(ops) >= 16:
                kept.append(order)
                continue
            wire_op = {
                "args": order["args"],
                "inst": order["inst"],
                "issued_ms": order["issued_ms"],
                "op_id": order["op_id"],
                "ttl_ms": order["ttl_ms"],
                "verb": order["verb"],
            }
            cand_raw = json.dumps(
                {"now_ms": now, "ops": ops + [wire_op]},
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
            if len(cand_raw) <= wire.WIRE_CAP:
                ops.append(wire_op)
                self.force.discard(order["op_id"])
            elif ops:
                stop_adding = True
                kept.append(order)
            else:
                kept.extend(self.queue[idx:])
                self.queue = kept
                return [], now, (wire_op, len(cand_raw), now)
        self.queue = kept
        return ops, now, None

    def _result(self, handler, query, body, body_len=0):
        if self.delivered:
            self._expire_delivered(self.now_ms())
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
        if self._consume_mode("_ack_ok_false", "ack_ok_false", peer=peer, inst=inst, op_id=op_id):
            self._emit(
                {
                    "body_len": body_len,
                    "ev": "ack_reject",
                    "http": 200,
                    "ok": False,
                    "op_id": op_id,
                    "peer": peer,
                }
            )
            self._send(handler, 200, {"ok": False})
            return
        self.delivered.pop(op_id, None)
        self.results.setdefault(op_id, []).append({"result": body, "t_ms": self.now_ms()})
        self._emit(
            {
                "body_len": body_len,
                "ev": "result",
                "http": 200,
                "op_id": op_id,
                "peer": peer,
                "result": body,
            }
        )
        self._send(handler, 200, {"ok": True})

    def _send_raw(self, handler, code, raw):
        handler.send_response(code)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(raw)))
        handler.end_headers()
        handler.wfile.write(raw)

    def _send(self, handler, code, obj):
        raw = json.dumps(obj, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self._send_raw(handler, code, raw)
