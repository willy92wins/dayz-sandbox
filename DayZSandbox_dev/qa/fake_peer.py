"""Peer falso del protocolo QA v0 (brief F0.1 §5 y §7).

El bucle de frames corre en el hilo principal. Las peticiones HTTP viven en otro
hilo y dejan el lote en una cola que ese bucle consume. En el cliente, un hilo
UDP encola los cam_rpc. La clave no se escribe en la salida.
"""

import argparse
import json
import math
import queue
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def _excepthook(exc_type, exc, tb):
    sys.stderr.write(exc_type.__name__ + "\n")


class Peer:
    def __init__(self, config, role, rpc_port, frame_hz, fault):
        self.config = config
        self.role = role
        self.rpc_port = rpc_port
        self.frame_hz = frame_hz
        self.fault = fault
        self.inst = secrets.token_hex(16)
        self.frame = 0
        self.fog = 0.0
        self.pose = ([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
        self.effects = []
        self.jobs = []
        self.cache = {}
        self.cache_order = []
        self.processed = 0
        self.hello_ok = False
        self.lease_ms = 3000
        self.last_ok = None
        self.backoff = 0.25
        self.cfg = None
        self.alive = True
        self.t0 = time.monotonic()
        self.inbox = queue.Queue()
        self.rpc_q = []
        self.rpc_lock = threading.Lock()
        self.last_seq = None
        self.rpc_log = []
        self.build = "retail" if fault == "wrong_build" else "offline"
        self.udp = None
        self._batch = None
        self.burst = None

    def local_ms(self):
        return (time.monotonic() - self.t0) * 1000.0

    def run(self):
        if self.role == "client":
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.bind(("127.0.0.1", self.rpc_port))
            self.udp.settimeout(0.2)
            threading.Thread(target=self._udp_loop, daemon=True).start()
        else:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if self.fault != "blocks_on_poll":
            threading.Thread(target=self._http_loop, daemon=True).start()
            self._frame_loop()
        else:
            self._blocking_loop()

    def _udp_loop(self):
        while self.alive:
            try:
                data, _addr = self.udp.recvfrom(65535)
            except (TimeoutError, socket.timeout, OSError):
                continue
            with self.rpc_lock:
                self.rpc_q.append(data)

    def _frame_loop(self):
        period = 1.0 / self.frame_hz
        nxt = time.perf_counter()
        while self.alive:
            now = time.perf_counter()
            if now < nxt:
                time.sleep(min(0.005, nxt - now))
                continue
            nxt += period
            if nxt < time.perf_counter() - period:
                nxt = time.perf_counter() + period
            self.frame += 1
            self._apply()
            self._drain_rpc()
            self._pump()

    def _blocking_loop(self):
        while self.alive:
            self.frame += 1
            self._apply()
            self._drain_rpc()
            self._finish_jobs()
            if self.jobs:
                time.sleep(1.0 / self.frame_hz)
                continue
            cfg = self._cfg()
            if cfg is None:
                time.sleep(2.0)
                continue
            if not self.hello_ok:
                self._hello(cfg)
                continue
            code, payload = self._request(cfg, "GET", "/poll", self._poll_query(), None)
            if code == 200:
                self.last_ok = time.monotonic()
                self.backoff = 0.25
                bucket = []
                ops = list(payload.get("ops") or [])
                now_ms = payload.get("now_ms", 0)
                batch_recv = time.monotonic()
                while self.alive and (ops or self.jobs or self.burst is not None):
                    if self._take_one(ops, now_ms, bucket, batch_recv):
                        time.sleep(1.0 / self.frame_hz)
                        self.frame += 1
                        self._apply()
                        self._drain_rpc()
                self._send_results(cfg, bucket)
            else:
                self._on_http_error(cfg, code)

    def _pump(self):
        if self._batch is None:
            try:
                ops, now_ms, bucket, done = self.inbox.get_nowait()
            except queue.Empty:
                self._finish_jobs()
                return
            self._batch = [list(ops), now_ms, bucket, done, time.monotonic()]
        ops, now_ms, bucket, done, batch_recv = self._batch
        while self.alive:
            if self._take_one(ops, now_ms, bucket, batch_recv):
                return
            if ops or self.jobs or self.burst is not None:
                continue
            done.set()
            self._batch = None
            return

    def _take_one(self, ops, now_ms, bucket, batch_recv):
        self._finish_jobs()
        if self.jobs or self.burst is not None:
            return True
        if not ops:
            return False
        self._start_op(ops.pop(0), now_ms, batch_recv, bucket)
        return bool(self.jobs or self.burst is not None)

    def _finish_jobs(self):
        self._burst_tick()
        still = []
        for job in self.jobs:
            if job["phase"] == "wait" and self.frame < job["read_frame"]:
                if not self._expired(job):
                    still.append(job)
                    continue
            if job["phase"] == "burst":
                if self.burst is not None:
                    still.append(job)
                    continue
                body = self._done(job["op"], _empty_read(), job)
                self._keep(body, job["bucket"])
                continue
            if self._expired(job):
                body = self._rejected(job["op"], "expired", job)
                self._keep(body, job["bucket"])
                continue
            body = self._execute(job)
            if body is None:
                still.append(job)
                continue
            self._keep(body, job["bucket"])
        self.jobs = still
        done = getattr(self, "pending_done", None)
        if done is not None and not self.jobs:
            self.pending_done = None
            done.set()

    def _expired(self, job):
        if self.fault == "ignores_ttl":
            return False
        if job["restante"] <= 0:
            return True
        return time.monotonic() > job["deadline"]

    def _start_op(self, op, now_ms, batch_recv, bucket):
        recv_ms = self.local_ms()
        if self.fault != "ignores_instance" and op.get("inst") != self.inst:
            bucket.append(self._rejected(op, "stale_instance", {"recv_ms": recv_ms, "frame": self.frame}))
            self._remember(bucket[-1])
            return
        ttl = float(op.get("ttl_ms") or 0)
        restante = ttl - (float(now_ms) - float(op.get("issued_ms") or 0))
        plazo = float(batch_recv) + max(restante, 0) / 1000.0
        if self.fault != "ignores_ttl" and (restante <= 0 or time.monotonic() > plazo):
            bucket.append(self._rejected(op, "expired", {"recv_ms": recv_ms, "frame": self.frame}))
            self._remember(bucket[-1])
            return
        if self.fault != "no_dedup" and op["op_id"] in self.cache:
            sent = json.loads(json.dumps(self.cache[op["op_id"]]))
            sent["dup"] = True
            bucket.append(sent)
            return
        verb = op.get("verb")
        if VERBS.get(verb) != self.role:
            bucket.append(self._rejected(op, "unknown_verb", {"recv_ms": recv_ms, "frame": self.frame}))
            self._remember(bucket[-1])
            return
        if _bad_args(verb, op.get("args") or {}):
            bucket.append(self._rejected(op, "bad_args", {"recv_ms": recv_ms, "frame": self.frame}))
            self._remember(bucket[-1])
            return
        self.jobs.append(
            {
                "op": op,
                "bucket": bucket,
                "recv_ms": recv_ms,
                "frame": self.frame,
                "restante": restante,
                "deadline": plazo,
                "phase": "wait",
                "read_frame": self.frame + 1,
                "verb": verb,
            }
        )

    def _execute(self, job):
        verb = job["verb"]
        op = job["op"]
        args = op.get("args") or {}
        if verb == "ambient_set":
            self.effects.append((self.frame, "fog", float(args.get("fog") or 0)))
            self._apply()
        elif verb == "cam_pose_set":
            pos = [float(v) for v in args.get("pos") or [0, 0, 0]]
            ypr = [float(v) for v in args.get("ypr") or [0, 0, 0]]
            self.effects.append((self.frame, "pose", (pos, ypr)))
            self._apply()
        elif verb == "rpc_burst":
            if int(args.get("count") or 0) <= 0:
                return self._done(op, _empty_read(), job)
            self._arm_burst(args, job)
            return None
        read = self._observe(verb, args)
        if self.fault == "ack_only":
            read = _empty_read()
        body = self._done(op, read, job)
        return body

    def _arm_burst(self, args, job):
        job["phase"] = "burst"
        count = int(args.get("count") or 0)
        interval = int(args.get("interval_ms") or 0)
        gap = max(1, int(round(interval * self.frame_hz / 1000.0))) if interval > 0 else 1
        self.burst = {
            "args": args,
            "count": count,
            "gap": gap,
            "i": 0,
            "next": self.frame,
            "seq0": int(args.get("seq0") or 0),
        }

    def _burst_tick(self):
        burst = self.burst
        if burst is None or self.frame < burst["next"]:
            return
        args = burst["args"]
        i = burst["i"]
        if i >= burst["count"]:
            self.burst = None
            return
        pos = [float(v) for v in args.get("pos") or [0, 0, 0]]
        ypr = [float(v) for v in args.get("ypr") or [0, 0, 0]]
        pkt = {
            "pos": [pos[0] + i, pos[1], pos[2]],
            "seq": burst["seq0"] + i,
            "target_inst": args.get("client_inst") or "",
            "ypr": ypr,
        }
        try:
            self.udp.sendto(json.dumps(pkt, separators=(",", ":")).encode("utf-8"), ("127.0.0.1", self.rpc_port))
        except OSError:
            self.burst = None
            return
        burst["i"] = i + 1
        if burst["i"] >= burst["count"]:
            self.burst = None
        else:
            burst["next"] = self.frame + burst["gap"]

    def _observe(self, verb, args):
        if verb == "srv_read":
            return self._read(["frame", "tick_s"])
        if verb == "ground_query":
            return self._read(["y"], x=float(args.get("x") or 0), z=float(args.get("z") or 0))
        if verb in ("ambient_set", "ambient_read"):
            return self._read(["fog"])
        if verb in ("cam_pose_set", "cam_pose_read"):
            return self._read(["pos", "ypr"])
        if verb == "rpc_log_read":
            return self._read(["rpc_log"])
        return _empty_read()

    def _read(self, has, x=0.0, z=0.0):
        read = _empty_read()
        read["has"] = list(has)
        if "frame" in has:
            read["frame"] = self.frame
        if "tick_s" in has:
            read["tick_s"] = self.frame / self.frame_hz
        if "y" in has:
            read["y"] = 100.0 + 10.0 * math.sin(x / 100.0) * math.cos(z / 100.0)
        if "fog" in has:
            read["fog"] = self.fog
        if "pos" in has or "ypr" in has:
            read["pos"] = [float(v) for v in self.pose[0]]
            read["ypr"] = [float(v) for v in self.pose[1]]
        if "rpc_log" in has:
            read["rpc_log"] = list(self.rpc_log)
        return read

    def _done(self, op, read, job):
        return {
            "done_ms": self.local_ms(),
            "dup": False,
            "frame_done": self.frame,
            "frame_recv": job["frame"],
            "op_id": op["op_id"],
            "read": read,
            "reason": "",
            "recv_ms": job["recv_ms"],
            "status": "done",
        }

    def _rejected(self, op, reason, stamp):
        return {
            "done_ms": self.local_ms(),
            "dup": False,
            "frame_done": self.frame,
            "frame_recv": stamp["frame"],
            "op_id": op["op_id"],
            "read": _empty_read(),
            "reason": reason,
            "recv_ms": stamp["recv_ms"],
            "status": "rejected",
        }

    def _keep(self, body, bucket):
        self._remember(body)
        self.processed += 1
        nth = self.processed % 10 == 1
        if self.fault == "drop_results" and nth:
            return
        if self.fault == "slow" and nth:
            body = dict(body)
            body["_slow"] = True
        bucket.append(body)

    def _remember(self, body):
        op_id = body["op_id"]
        stored = {k: v for k, v in body.items() if k != "_slow"}
        if op_id not in self.cache:
            self.cache_order.append(op_id)
        self.cache[op_id] = stored
        while len(self.cache_order) > 1024:
            self.cache.pop(self.cache_order.pop(0), None)

    def _apply(self):
        left = []
        for item in self.effects:
            if item[0] <= self.frame:
                if item[1] == "fog":
                    self.fog = item[2]
                else:
                    self.pose = item[2]
            else:
                left.append(item)
        self.effects = left

    def _drain_rpc(self):
        with self.rpc_lock:
            batch = self.rpc_q
            self.rpc_q = []
        for raw in batch:
            try:
                msg = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                continue
            self._on_rpc(msg)

    def _on_rpc(self, msg):
        now = time.monotonic()
        lease_age = 1.0e9 if self.last_ok is None else (now - self.last_ok) * 1000.0
        if msg.get("target_inst") != self.inst:
            decision = "rejected_inst"
        elif self.fault != "rpc_ignores_lease" and lease_age > self.lease_ms:
            decision = "rejected_lease"
        elif self.last_seq is not None and int(msg.get("seq") or 0) <= self.last_seq:
            decision = "rejected_seq"
        else:
            decision = "accepted"
            self.last_seq = int(msg.get("seq") or 0)
            pos = [float(v) for v in msg.get("pos") or [0, 0, 0]]
            ypr = [float(v) for v in msg.get("ypr") or [0, 0, 0]]
            self.effects.append((self.frame + 1, "pose", (pos, ypr)))
        self.rpc_log.append(
            {
                "decision": decision,
                "lease_age_ms": lease_age,
                "recv_ms": self.local_ms(),
                "seq": int(msg.get("seq") or 0),
            }
        )
        if len(self.rpc_log) > 512:
            self.rpc_log = self.rpc_log[-512:]

    def _http_loop(self):
        while self.alive:
            cfg = self._cfg()
            if cfg is None:
                time.sleep(2.0)
                continue
            if not self.hello_ok:
                self._hello(cfg)
                continue
            code, payload = self._request(cfg, "GET", "/poll", self._poll_query(), None)
            if code != 200:
                self._on_http_error(cfg, code)
                continue
            self.last_ok = time.monotonic()
            self.backoff = 0.25
            bucket = []
            done = threading.Event()
            self.inbox.put((payload.get("ops") or [], payload.get("now_ms", 0), bucket, done))
            while self.alive and not done.wait(timeout=0.2):
                pass
            self._send_results(cfg, bucket)

    def _hello(self, cfg):
        body = {
            "build": self.build,
            "inst": self.inst,
            "peer": self.role,
            "probe_ver": "fake-qa0",
            "proto": "qa0",
        }
        code, payload = self._request(cfg, "POST", "/hello", {}, body)
        if code == 200:
            self.lease_ms = int(payload.get("lease_ms") or self.lease_ms)
            self.hello_ok = True
            self.backoff = 0.25
            return
        self._on_http_error(cfg, code)

    def _on_http_error(self, cfg, code):
        self.hello_ok = False
        retry = (cfg.get("retry_ms") or 2000) / 1000.0
        if code == 401:
            if self.fault != "no_key_reload":
                self.cfg = self._read_config()
            time.sleep(retry)
            return
        if code == 409:
            time.sleep(min(0.05, retry))
            return
        time.sleep(self.backoff)
        self.backoff = min(retry, self.backoff * 2)

    def _send_results(self, cfg, bucket):
        gaps = (0.0, 0.25, 0.5, 1.0)
        for body in bucket:
            slow = body.pop("_slow", False) if isinstance(body, dict) else False
            if slow:
                time.sleep(1.2)
            for gap in gaps:
                if gap:
                    time.sleep(gap)
                code, _payload = self._request(cfg, "POST", "/result", {"peer": self.role, "inst": self.inst}, body)
                if code == 200:
                    break
                if code == 401:
                    self.hello_ok = False
                    return

    def _poll_query(self):
        return {
            "frame": str(self.frame),
            "inst": self.inst,
            "peer": self.role,
            "tick_s": str(self.frame / self.frame_hz),
        }

    def _cfg(self):
        fresh = self._read_config()
        if self.fault == "no_key_reload" and self.cfg is not None:
            return self.cfg
        if fresh is not None:
            self.cfg = fresh
        return fresh

    def _read_config(self):
        try:
            data = json.loads(Path(self.config).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        url = str(data.get("url") or "")
        host = urllib.parse.urlparse(url).hostname
        if host != "127.0.0.1":
            return None
        key = data.get("key")
        if not isinstance(key, str):
            return None
        try:
            retry = int(data.get("retry_ms") or 2000)
        except (TypeError, ValueError):
            retry = 2000
        return {"key": key, "retry_ms": retry, "url": url}

    def _request(self, cfg, method, path, query, body):
        params = {"key": cfg["key"]}
        params.update(query or {})
        url = cfg["url"].rstrip("/") + path + "?" + urllib.parse.urlencode(params)
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
                code = resp.status
        except urllib.error.HTTPError as exc:
            code = exc.code
            try:
                raw = exc.read()
            except Exception:
                raw = b""
        except Exception:
            return 0, {}
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeError, json.JSONDecodeError):
            payload = {}
        return code, payload


VERBS = {
    "ambient_read": "server",
    "ambient_set": "server",
    "cam_pose_read": "client",
    "cam_pose_set": "client",
    "ground_query": "server",
    "rpc_burst": "server",
    "rpc_log_read": "client",
    "srv_read": "server",
}


def _empty_read():
    return {
        "fog": 0.0,
        "frame": 0,
        "has": [],
        "pos": [0, 0, 0],
        "rpc_log": [],
        "tick_s": 0.0,
        "y": 0.0,
        "ypr": [0, 0, 0],
    }


def _bad_args(verb, args):
    if verb == "ambient_set":
        try:
            fog = float(args.get("fog"))
        except (TypeError, ValueError):
            return True
        return fog < 0 or fog > 1
    return False


def main(argv=None):
    sys.excepthook = _excepthook
    parser = argparse.ArgumentParser(prog="qa/fake_peer.py")
    parser.add_argument("--config", required=True)
    parser.add_argument("--peer", required=True, choices=("server", "client"))
    parser.add_argument("--rpc-port", required=True, type=int)
    parser.add_argument("--frame-hz", type=float, default=60)
    parser.add_argument("--fault", default=None)
    args = parser.parse_args(argv)
    Peer(args.config, args.peer, args.rpc_port, args.frame_hz, args.fault).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
