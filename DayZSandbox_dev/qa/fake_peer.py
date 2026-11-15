"""Peer falso del protocolo QA v0 / F0.3-0 (briefs F0.1 §5/§7, F0.2 §3/§5, F0.3-0 §2-§4, §13, §14).

El bucle de frames corre en el hilo principal. Las peticiones HTTP viven en otro
hilo y dejan el lote en una cola que ese bucle consume. En el cliente, un hilo
UDP encola los RPC. La clave no se escribe en la salida.
"""

import argparse
import hashlib
import importlib
import json
import math
import os
import queue
import re
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.modules.setdefault("fake_peer", sys.modules[__name__])

import wire

CALLBACK_POOL_MAX = 4
DEFAULT_CALLBACK_BUDGET = 2000
CACHE_CAP = 1024
LOG_CAP = 512

JOB_MAX_LIVE = 8
JOB_MAX_ROWS = 4096
JOB_MAX_DURATION_MS = 900000.0
JOB_MAX_RETAINED = 16

EXT_MODULES = (
    "fake_ext_persist",
    "fake_ext_actor",
    "fake_ext_cam",
    "fake_ext_cot",
    "fake_ext_env",
    "fake_ext_take",
    "fake_ext_perf",
    "fake_ext_map",
    "fake_ext_base",
)

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

CORE_JOB_VERBS = frozenset({"job_read", "job_stop", "job_free"})


WIT_PREFIX = "[DSBX_WIT] "
_WIT_LOCK = threading.Lock()


def wit_digest(obj):
    """sha256 hex del JSON canonico (claves ordenadas, sin espacios). Lo usa tests/e2e_witness.py."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def wit_line(**fields):
    """Traza para el testigo de los e2e: una linea por stdout, con flush. No cambia el cable ni la conducta."""
    line = WIT_PREFIX + json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    try:
        with _WIT_LOCK:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
    except Exception:
        pass


def _excepthook(exc_type, exc, tb):
    sys.stderr.write(exc_type.__name__ + "\n")


def _reject_nonfinite(_token):
    raise ValueError("non-finite JSON constant")


def _valid_hello_resp(code, payload):
    if code != 200 or not isinstance(payload, dict):
        return False
    if payload.get("ok") is not True:
        return False
    lease = payload.get("lease_ms")
    if isinstance(lease, bool) or not isinstance(lease, (int, float)) or not math.isfinite(lease):
        return False
    return lease > 0


def _valid_poll_resp(code, payload):
    if code != 200 or not isinstance(payload, dict):
        return False
    now_ms = payload.get("now_ms")
    if isinstance(now_ms, bool) or not isinstance(now_ms, (int, float)) or not math.isfinite(now_ms):
        return False
    ops = payload.get("ops")
    if not isinstance(ops, list):
        return False
    return all(isinstance(op, dict) and isinstance(op.get("op_id"), str) for op in ops)


def _valid_result_resp(code, payload):
    return code == 200 and isinstance(payload, dict) and payload.get("ok") is True


class FakeExt:
    def init(self, peer, jobs):
        pass

    def handles(self, verb, role):
        return False

    def on_start_op(self, op, args_unpacked, raw_args):
        return ("rejected", "unknown_verb", wire.empty_payload())

    def on_tick(self, timeslice_s):
        pass

    def on_job_end(self, job_id, state, reason):
        pass

    def on_rpc(self, rpc_type, payload):
        pass

    def on_shutdown(self):
        pass


class JobMgr:
    def __init__(self, peer):
        self.peer = peer
        self.jobs_by_id = {}
        self.live_ids = []
        self.retained_ids = []
        self.held_resources = {}
        self.deferred_cleanup_ids = []

    def live_count(self):
        return len(self.live_ids)

    def start_job(
        self,
        owner,
        job_id,
        resource,
        ncol,
        scol,
        page_size,
        max_rows,
        max_duration_ms,
        deadman,
    ):
        if deadman not in ("stop", "continue"):
            return "bad_deadman"
        if not isinstance(resource, str) or resource == "":
            return "bad_args"
        if not isinstance(job_id, str) or job_id == "" or job_id in self.jobs_by_id:
            return "bad_args"
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size <= 0:
            return "bad_args"
        if isinstance(max_rows, bool) or not isinstance(max_rows, int) or max_rows <= 0:
            return "bad_args"
        if (
            isinstance(max_duration_ms, bool)
            or not isinstance(max_duration_ms, (int, float))
            or not math.isfinite(max_duration_ms)
            or max_duration_ms <= 0.0
        ):
            return "bad_args"
        if not isinstance(ncol, list) or not isinstance(scol, list):
            return "bad_args"
        try:
            ncol_set = set(ncol)
            scol_set = set(scol)
        except TypeError:
            return "bad_args"
        if (
            len(ncol_set) != len(ncol)
            or len(scol_set) != len(scol)
            or any(not isinstance(c, str) or c == "" for c in ncol)
            or any(not isinstance(c, str) or c == "" for c in scol)
            or not ncol_set.isdisjoint(scol_set)
        ):
            return "bad_args"

        if resource in self.held_resources:
            return "busy"
        if len(self.live_ids) >= JOB_MAX_LIVE:
            return "too_many_jobs"

        start_tick = self.peer.local_ms()
        eff_max_rows = min(int(max_rows), JOB_MAX_ROWS)
        eff_max_dur = min(float(max_duration_ms), JOB_MAX_DURATION_MS)
        self.jobs_by_id[job_id] = {
            "deadman": deadman,
            "defer_cleanup": False,
            "elapsed_dtsum_ms": 0.0,
            "end_tick_ms": 0.0,
            "ext_handles_deadman": False,
            "freeze_on_wait": False,
            "job_id": job_id,
            "max_duration_ms": eff_max_dur,
            "max_rows": eff_max_rows,
            "ncell": [],
            "ncol": list(ncol),
            "onjobend_tick_ms": 0.0,
            "owner": owner,
            "page_size": int(page_size),
            "reason": "",
            "released_tick_ms": 0.0,
            "resource": resource,
            "rows_total": 0,
            "scell": [],
            "scol": list(scol),
            "start_tick_ms": start_tick,
            "state": "running",
        }
        self.live_ids.append(job_id)
        self.held_resources[resource] = job_id
        return ""

    def configure_job_faults(self, job_id, freeze_on_wait=False, defer_cleanup=False, ext_handles_deadman=False):
        job = self.jobs_by_id.get(job_id)
        if job is not None:
            job["freeze_on_wait"] = bool(freeze_on_wait)
            job["defer_cleanup"] = bool(defer_cleanup)
            job["ext_handles_deadman"] = bool(ext_handles_deadman)

    def get_start_tick_ms(self, job_id):
        job = self.jobs_by_id.get(job_id)
        return 0.0 if job is None else float(job["start_tick_ms"])

    def is_deadman_tripped(self, job_id):
        job = self.jobs_by_id.get(job_id)
        if job is None or job["deadman"] != "stop":
            return False
        return not self.peer.lease_valid()

    def fill_start_read(self, job_id, resource):
        return wire.pack_payload(
            scalars_str={
                "job": job_id,
                "state": "running",
                "resource": resource,
            }
        )

    def append_row(self, job_id, nvals, svals):
        job = self.jobs_by_id.get(job_id)
        if job is None or job["state"] != "running":
            return False
        if len(nvals) != len(job["ncol"]) or len(svals) != len(job["scol"]):
            return False
        if job["rows_total"] + 1 > job["max_rows"]:
            self.end_job(job_id, "failed", "rows_cap")
            return False
        for v in nvals:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                return False
        for s in svals:
            if not isinstance(s, str):
                return False
        job["ncell"].extend(nvals)
        job["scell"].extend(svals)
        job["rows_total"] += 1
        return True

    def get_state(self, job_id):
        job = self.jobs_by_id.get(job_id)
        return "" if job is None else job["state"]

    def end_job(self, job_id, state, reason):
        if state not in ("done", "stopped", "failed", "expired"):
            return False
        job = self.jobs_by_id.get(job_id)
        if job is None or job["state"] != "running":
            return False
        if job_id in self.live_ids:
            self.live_ids.remove(job_id)
        job["state"] = state
        job["reason"] = str(reason or "")
        job["end_tick_ms"] = self.peer.local_ms()

        if job.get("defer_cleanup") and not self.peer.is_transport_connected() and reason != "shutdown":
            self.deferred_cleanup_ids.append(job_id)
            return True

        self._finalize_cleanup(job)
        return True

    def _finalize_cleanup(self, job):
        jid = job["job_id"]
        job["owner"].on_job_end(jid, job["state"], job["reason"])
        job["onjobend_tick_ms"] = self.peer.local_ms()
        if self.held_resources.get(job["resource"]) == jid:
            self.held_resources.pop(job["resource"], None)
        job["released_tick_ms"] = self.peer.local_ms()
        self.retained_ids.append(jid)
        while len(self.retained_ids) > JOB_MAX_RETAINED:
            evicted = self.retained_ids.pop(0)
            self.jobs_by_id.pop(evicted, None)

    def flush_deferred_cleanup(self):
        if not self.deferred_cleanup_ids:
            return
        pending = list(self.deferred_cleanup_ids)
        self.deferred_cleanup_ids.clear()
        for jid in pending:
            job = self.jobs_by_id.get(jid)
            if job is not None:
                self._finalize_cleanup(job)

    def tick_jobs(self, timeslice_s, now_ms):
        dt_ms = float(timeslice_s) * 1000.0
        for jid in list(self.live_ids):
            job = self.jobs_by_id.get(jid)
            if job is None or job["state"] != "running":
                continue
            if job.get("freeze_on_wait") and not self.peer.is_transport_connected():
                continue
            job["elapsed_dtsum_ms"] += dt_ms
            if job["deadman"] == "stop" and not job.get("ext_handles_deadman") and not self.peer.lease_valid():
                self.end_job(jid, "failed", "lease_expired")
                continue
            if now_ms - job["start_tick_ms"] > job["max_duration_ms"]:
                self.end_job(jid, "expired", "job_timeout")

    def shutdown_all(self):
        for jid in list(self.live_ids):
            self.end_job(jid, "stopped", "shutdown")
        self.flush_deferred_cleanup()

    def dispatch_core_verb(self, op, args_unpacked):
        verb = op["verb"]
        strs = args_unpacked["str"]
        nums = args_unpacked["num"]
        job_id = strs.get("job", "")
        if not isinstance(job_id, str) or job_id == "":
            return ("rejected", "bad_args", wire.empty_payload())

        if verb == "job_read":
            if "page_n" not in nums:
                return ("rejected", "bad_args", wire.empty_payload())
            raw_page = nums["page_n"]
            if isinstance(raw_page, bool) or not isinstance(raw_page, (int, float)) or not math.isfinite(raw_page) or not float(raw_page).is_integer():
                return ("rejected", "bad_args", wire.empty_payload())
            page_n = int(raw_page)
            job = self.jobs_by_id.get(job_id)
            if job is None:
                return ("rejected", "unknown_job", wire.empty_payload())
            rows_total = job["rows_total"]
            page_size = job["page_size"]
            pages_n = 0 if rows_total == 0 else (rows_total + page_size - 1) // page_size
            if page_n < 0 or (rows_total == 0 and page_n > 0) or (rows_total > 0 and page_n >= pages_n):
                return ("rejected", "bad_args", wire.empty_payload())
            start = page_n * page_size
            end = min(start + page_size, rows_total)
            n_nc = len(job["ncol"])
            n_sc = len(job["scol"])
            ncell = list(job["ncell"][start * n_nc : end * n_nc])
            scell = list(job["scell"][start * n_sc : end * n_sc])
            payload = {
                "sk": ["job", "state", "reason", "resource"],
                "sv": [job_id, job["state"], job["reason"], job["resource"]],
                "nk": [
                    "page_n",
                    "pages_n",
                    "rows_total_n",
                    "start_tick_ms",
                    "end_tick_ms",
                    "onjobend_tick_ms",
                    "released_tick_ms",
                    "elapsed_dtsum_ms",
                ],
                "nv": [
                    page_n,
                    pages_n,
                    rows_total,
                    job["start_tick_ms"],
                    job["end_tick_ms"],
                    job["onjobend_tick_ms"],
                    job["released_tick_ms"],
                    job["elapsed_dtsum_ms"],
                ],
                "ncol": list(job["ncol"]),
                "ncell": ncell,
                "scol": list(job["scol"]),
                "scell": scell,
                "rows": end - start,
            }
            wire.validate_payload(payload)
            return ("done", "", payload)

        if verb == "job_stop":
            job = self.jobs_by_id.get(job_id)
            if job is None:
                return ("rejected", "unknown_job", wire.empty_payload())
            if job["state"] == "running":
                self.end_job(job_id, "stopped", "")
            payload = wire.pack_payload(
                scalars_str={
                    "job": job_id,
                    "state": job["state"],
                    "reason": job["reason"],
                },
                scalars_num={"rows_total_n": job["rows_total"]},
            )
            return ("done", "", payload)

        if verb == "job_free":
            job = self.jobs_by_id.get(job_id)
            if job is None:
                return ("rejected", "unknown_job", wire.empty_payload())
            if job["state"] == "running" or job_id in self.deferred_cleanup_ids:
                return ("rejected", "busy", wire.empty_payload())
            if job_id in self.retained_ids:
                self.retained_ids.remove(job_id)
            self.jobs_by_id.pop(job_id, None)
            payload = wire.pack_payload(scalars_str={"job": job_id, "freed": "1"})
            return ("done", "", payload)

        return ("rejected", "unknown_verb", wire.empty_payload())


class Peer:
    def __init__(
        self,
        config,
        role,
        rpc_port,
        frame_hz,
        fault,
        *,
        clock_offset_ms=0.0,
        git_head=None,
        probe_ver=None,
        clock_ms_fn=None,
        log_path=None,
    ):
        self.config = config
        self.role = role
        self.rpc_port = rpc_port
        self.frame_hz = frame_hz
        self.fault = fault
        self.clock_offset_ms = float(clock_offset_ms)
        self.git_head = git_head
        self._probe_ver_override = probe_ver
        self._probe_ver_cached = None
        self._clock_ms_fn = clock_ms_fn
        self.log_path = Path(log_path) if log_path else None
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
        self._reconnected_poll = False
        self.lease_ms = 3000
        self.last_ok = None
        self.last_ok_ms = None
        self.failures = 0
        self.cfg = None
        self.alive = True
        self._shutdown_done = False
        self.t0 = time.monotonic()
        self.inbox = queue.Queue()
        self.rpc_q = []
        self.rpc_lock = threading.Lock()
        self.last_seq = None
        self.rpc_log = []
        self.emit_log = []
        self.build = "retail" if fault == "wrong_build" else "offline"
        self.udp = None
        self._batch = None
        self.burst = None

        self.callback_budget = DEFAULT_CALLBACK_BUDGET
        self.callbacks_created_n = 0
        self._cb_pool = []
        self._poll_cb_alive = False
        self._callbacks_inflight = 0
        self.budget_exhausted = False
        self._logged_budget_exhausted = False
        self.status_logs = []

        self.job_mgr = JobMgr(self)
        self.exts = []
        for mod_name in EXT_MODULES:
            mod = importlib.import_module(mod_name)
            ext = mod.create_ext(self, self.job_mgr)
            ext.init(self, self.job_mgr)
            self.exts.append(ext)

    def local_ms(self):
        if self._clock_ms_fn is not None:
            return float(self._clock_ms_fn())
        return self.clock_offset_ms + (time.monotonic() - self.t0) * 1000.0

    def is_transport_connected(self):
        return bool(self.hello_ok)

    def lease_age_ms(self):
        if self.last_ok_ms is not None:
            return max(0.0, self.local_ms() - self.last_ok_ms)
        if self.last_ok is not None:
            return max(0.0, (time.monotonic() - self.last_ok) * 1000.0)
        return 1.0e9

    def lease_valid(self):
        return (self.last_ok_ms is not None or self.last_ok is not None) and self.lease_age_ms() <= float(self.lease_ms)

    def resolve_probe_ver(self):
        if self._probe_ver_override is not None:
            return self._probe_ver_override
        if self._probe_ver_cached is None:
            if self.git_head:
                f03_common = importlib.import_module("f03_common")
                stamp = f03_common.compute_probe_stamp_at_commit(self.git_head)
            else:
                stamp = wire.compute_probe_stamp()
            self._probe_ver_cached = f"dsbx-qa1+{stamp}"
        return self._probe_ver_cached

    def info_snapshot(self):
        self.sync_cache_order()
        return {
            "callback_budget_n": self.callback_budget,
            "callbacks_created_n": self.callbacks_created_n,
            "callbacks_inflight_n": self._callbacks_inflight,
            "callbacks_pooled_n": len(self._cb_pool),
            "cache_size_n": len(self.cache_order),
            "jobs_live_n": self.job_mgr.live_count(),
            "probe_ver": self.resolve_probe_ver(),
            "rpclog_size_n": len(self.rpc_log),
        }

    def sync_cache_order(self):
        if not self.cache and self.cache_order:
            self.cache_order.clear()

    def make_synthetic_cached_result(self, op_id, now_ms, frame):
        return {
            "done_ms": now_ms,
            "dup": False,
            "frame_done": frame,
            "frame_recv": frame,
            "op_id": op_id,
            "read": _new_payload_read(wire.empty_payload(), has_payload=True),
            "reason": "",
            "recv_ms": now_ms,
            "status": "done",
        }

    def remember_result(self, body):
        self._remember(body)

    def send_ext_rpc(self, rpc_type, payload):
        if self.udp is None:
            return
        pkt = {"rpc_type": int(rpc_type), "payload": payload}
        try:
            self.udp.sendto(
                json.dumps(pkt, separators=(",", ":")).encode("utf-8"),
                ("127.0.0.1", self.rpc_port),
            )
        except OSError:
            return

    def shutdown(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self.alive = False
        self.job_mgr.shutdown_all()
        for ext in self.exts:
            ext.on_shutdown()
        if self.udp is not None:
            try:
                self.udp.close()
            except OSError:
                pass

    def run(self):
        self.resolve_probe_ver()
        if self.role == "client":
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.bind(("127.0.0.1", self.rpc_port))
            self.udp.settimeout(0.2)
            threading.Thread(target=self._udp_loop, daemon=True).start()
        else:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            if self.fault != "blocks_on_poll":
                threading.Thread(target=self._http_loop, daemon=True).start()
                self._frame_loop()
            else:
                self._blocking_loop()
        finally:
            self.shutdown()

    def _udp_loop(self):
        while self.alive:
            try:
                data, _addr = self.udp.recvfrom(65535)
            except (TimeoutError, socket.timeout, OSError):
                continue
            with self.rpc_lock:
                self.rpc_q.append(data)

    def _step_extensions_and_jobs(self, dt_s):
        now_ms = self.local_ms()
        if self._reconnected_poll:
            self._reconnected_poll = False
            self.job_mgr.flush_deferred_cleanup()
        self.job_mgr.tick_jobs(dt_s, now_ms)
        for ext in self.exts:
            ext.on_tick(dt_s)

    def _frame_loop(self):
        period = 1.0 / self.frame_hz
        nxt = time.perf_counter()
        prev_mono = time.monotonic()
        while self.alive:
            now = time.perf_counter()
            if now < nxt:
                time.sleep(min(0.005, nxt - now))
                continue
            nxt += period
            if nxt < time.perf_counter() - period:
                nxt = time.perf_counter() + period
            cur_mono = time.monotonic()
            dt_s = max(0.0, cur_mono - prev_mono)
            prev_mono = cur_mono
            self.frame += 1
            self._apply()
            self._drain_rpc()
            self._step_extensions_and_jobs(dt_s)
            self._pump()

    def _blocking_loop(self):
        period = 1.0 / self.frame_hz
        while self.alive:
            self.frame += 1
            self._apply()
            self._drain_rpc()
            self._step_extensions_and_jobs(period)
            self._finish_jobs()
            if self.jobs:
                time.sleep(period)
                continue
            if self.budget_exhausted:
                time.sleep(0.05)
                continue
            if self.cfg is None:
                fresh = self._read_config()
                if fresh is None:
                    time.sleep(self._p2_retry_s())
                    continue
                self.cfg = fresh
            cfg = self.cfg
            if not self.hello_ok:
                self._hello(cfg)
                continue
            code, payload = self._request(cfg, "GET", "/poll", self._poll_query(), None, kind="poll")
            if _valid_poll_resp(code, payload):
                self.last_ok = time.monotonic()
                self.last_ok_ms = self.local_ms()
                self._reconnected_poll = True
                self.failures = 0
                bucket = []
                ops = list(payload["ops"])
                now_ms = payload["now_ms"]
                batch_recv = time.monotonic()
                while self.alive and (ops or self.jobs or self.burst is not None):
                    if self._take_one(ops, now_ms, bucket, batch_recv):
                        time.sleep(period)
                        self.frame += 1
                        self._apply()
                        self._drain_rpc()
                        self._step_extensions_and_jobs(period)
                self._send_results(cfg, bucket)
            elif not self.budget_exhausted:
                self._on_http_error()

    def _pump(self):
        if self._reconnected_poll:
            self._reconnected_poll = False
            self.job_mgr.flush_deferred_cleanup()
        if self._batch is None:
            try:
                ops, now_ms, bucket, done = self.inbox.get_nowait()
            except queue.Empty:
                self._finish_jobs()
                return
            self.last_ok = time.monotonic()
            self.last_ok_ms = self.local_ms()
            self.job_mgr.flush_deferred_cleanup()
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
                err_reason = job.get("error_reason")
                if err_reason:
                    body = self._error(job["op"], err_reason, job, is_new=False)
                else:
                    body = self._done(job["op"], _empty_read(), job)
                self._keep(body, job["bucket"])
                continue
            if self._expired(job):
                body = self._rejected(job["op"], "expired", job, is_new=False)
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

    def _is_f02_verb(self, verb):
        return verb in VERBS

    def _find_ext_for_verb(self, verb):
        for ext in self.exts:
            if ext.handles(verb, self.role):
                return ext
        return None

    def _start_op(self, op, now_ms, batch_recv, bucket):
        recv_ms = self.local_ms()
        stamp = {"recv_ms": recv_ms, "frame": self.frame}
        verb = op.get("verb")
        is_f02 = self._is_f02_verb(verb)

        if self.fault != "ignores_instance" and op.get("inst") != self.inst:
            body = self._rejected(op, "stale_instance", stamp, is_new=not is_f02)
            body = self._cap_new_result(body, is_new=not is_f02)
            bucket.append(body)
            self._remember(body)
            return

        ttl = float(op.get("ttl_ms") or 0)
        restante = ttl - (float(now_ms) - float(op.get("issued_ms") or 0))
        plazo = float(batch_recv) + max(restante, 0) / 1000.0
        if self.fault != "ignores_ttl" and (restante <= 0 or time.monotonic() > plazo):
            body = self._rejected(op, "expired", stamp, is_new=not is_f02)
            body = self._cap_new_result(body, is_new=not is_f02)
            bucket.append(body)
            self._remember(body)
            return

        self.sync_cache_order()
        if self.fault != "no_dedup" and op["op_id"] in self.cache:
            sent = json.loads(json.dumps(self.cache[op["op_id"]]))
            sent["dup"] = True
            bucket.append(sent)
            return

        if is_f02:
            if VERBS.get(verb) != self.role:
                bucket.append(self._rejected(op, "unknown_verb", stamp, is_new=False))
                self._remember(bucket[-1])
                return
            if _bad_args(verb, op.get("args") or {}):
                bucket.append(self._rejected(op, "bad_args", stamp, is_new=False))
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
            return

        ext = None
        if verb not in CORE_JOB_VERBS:
            ext = self._find_ext_for_verb(verb)
            if ext is None:
                body = self._rejected(op, "unknown_verb", stamp, is_new=True)
                body = self._cap_new_result(body, is_new=True)
                self._keep(body, bucket)
                return

        raw_args = op.get("args")
        if not isinstance(raw_args, dict):
            body = self._rejected(op, "bad_args", stamp, is_new=True)
            body = self._cap_new_result(body, is_new=True)
            self._keep(body, bucket)
            return

        try:
            wire.validate_payload(raw_args)
        except ValueError:
            body = self._rejected(op, "bad_args", stamp, is_new=True)
            body = self._cap_new_result(body, is_new=True)
            self._keep(body, bucket)
            return

        clean_args = {k: (list(v) if isinstance(v, list) else v) for k, v in raw_args.items()}
        op_fault = ""
        if "qa_fault" in clean_args["sk"]:
            idx = clean_args["sk"].index("qa_fault")
            raw_fault = clean_args["sv"][idx]
            try:
                op_fault = wire.parse_qa_fault(raw_fault)
            except ValueError:
                body = self._rejected(op, "bad_args", stamp, is_new=True)
                body = self._cap_new_result(body, is_new=True)
                self._keep(body, bucket)
                return
            clean_args["sk"].pop(idx)
            clean_args["sv"].pop(idx)

        # D10 (brief v4.5.5, §15): la sonda real corta en 1023 las cadenas que lee; el peer falso rechaza la orden para
        # que offline falle tambien (en vez de aceptar una cadena que en partida llegaria truncada).
        try:
            wire.check_arg_strings(clean_args)
        except ValueError:
            body = self._rejected(op, "bad_args", stamp, is_new=True)
            body = self._cap_new_result(body, is_new=True)
            self._keep(body, bucket)
            return

        args_unpacked = wire.unpack_payload(clean_args)
        op_ctx = dict(op)
        op_ctx["qa_fault"] = op_fault

        if verb in CORE_JOB_VERBS:
            status, reason, payload_out = self.job_mgr.dispatch_core_verb(op_ctx, args_unpacked)
        else:
            status, reason, payload_out = ext.on_start_op(op_ctx, args_unpacked, clean_args)

        if status == "done":
            read_out = _new_payload_read(payload_out, has_payload=True)
            if self.fault == "ack_only":
                read_out = _new_empty_read()
            body = self._done(op, read_out, stamp)
        elif status == "error":
            body = self._error(op, reason, stamp, is_new=True)
        else:
            body = self._rejected(op, reason, stamp, is_new=True)

        body = self._cap_new_result(body, is_new=True)
        self._keep(body, bucket)

    def _cap_new_result(self, body, is_new):
        if not is_new:
            return body
        raw = wire.result_wire_bytes(body)
        if len(raw) <= wire.WIRE_CAP:
            return body
        return {
            "done_ms": body["done_ms"],
            "dup": body["dup"],
            "frame_done": body["frame_done"],
            "frame_recv": body["frame_recv"],
            "op_id": body["op_id"],
            "read": _new_empty_read(),
            "reason": "result_too_large",
            "recv_ms": body["recv_ms"],
            "status": "error",
        }

    def _execute(self, job):
        verb = job["verb"]
        op = job["op"]
        args = op.get("args") or {}
        if verb == "ambient_set":
            if self.fault != "rpc_ignores_lease" and not self.lease_valid():
                return self._error(op, "lease_expired", job, is_new=False)
            self.effects.append((self.frame, "fog", float(args.get("fog") or 0)))
            self._apply()
        elif verb == "cam_pose_set":
            if self.fault != "rpc_ignores_lease" and not self.lease_valid():
                return self._error(op, "lease_expired", job, is_new=False)
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
        frame_ms = 1000.0 / self.frame_hz
        gap = max(1, int(round(interval * self.frame_hz / 1000.0))) if interval > 0 else 1
        per_frame = max(1, int(frame_ms // interval)) if 0 < interval < frame_ms else 1
        self.burst = {
            "args": args,
            "count": count,
            "gap": gap,
            "i": 0,
            "job": job,
            "next": self.frame,
            "op_id": job["op"]["op_id"],
            "per_frame": per_frame,
            "seq0": int(args.get("seq0") or 0),
        }

    def _record_emit(self, op_id, seq_n, tick_ms, lease_age_ms, outcome):
        self.emit_log.append(
            {
                "lease_age_ms": float(lease_age_ms),
                "op_id": str(op_id),
                "outcome": str(outcome),
                "seq_n": int(seq_n),
                "tick_ms": float(tick_ms),
            }
        )
        while len(self.emit_log) > LOG_CAP:
            self.emit_log.pop(0)

    def _burst_tick(self):
        burst = self.burst
        if burst is None or self.frame < burst["next"]:
            return
        args = burst["args"]
        per_frame = int(burst.get("per_frame", 1))
        for _ in range(per_frame):
            i = burst["i"]
            if i >= burst["count"]:
                self.burst = None
                return
            seq_n = burst["seq0"] + i
            now_tick_ms = self.local_ms()
            lease_age = self.lease_age_ms()
            if self.fault != "rpc_ignores_lease" and not self.lease_valid():
                self._record_emit(burst["op_id"], seq_n, now_tick_ms, lease_age, "blocked_lease")
                burst["job"]["error_reason"] = "lease_expired"
                self.burst = None
                return

            pos = [float(v) for v in args.get("pos") or [0, 0, 0]]
            ypr = [float(v) for v in args.get("ypr") or [0, 0, 0]]
            pkt = {
                "pos": [pos[0] + i, pos[1], pos[2]],
                "seq": seq_n,
                "target_inst": args.get("client_inst") or "",
                "ypr": ypr,
            }
            try:
                self.udp.sendto(json.dumps(pkt, separators=(",", ":")).encode("utf-8"), ("127.0.0.1", self.rpc_port))
            except OSError:
                self.burst = None
                return
            self._record_emit(burst["op_id"], seq_n, now_tick_ms, lease_age, "sent")
            burst["i"] = i + 1
            if burst["i"] >= burst["count"]:
                self.burst = None
                return
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
            offset_s = self.clock_offset_ms / 1000.0
            read["tick_s"] = (self.frame / self.frame_hz) if offset_s == 0.0 else (offset_s + self.frame / self.frame_hz)
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

    def _rejected(self, op, reason, stamp, is_new=False):
        return {
            "done_ms": self.local_ms(),
            "dup": False,
            "frame_done": self.frame,
            "frame_recv": stamp["frame"],
            "op_id": op["op_id"],
            "read": _new_empty_read() if is_new else _empty_read(),
            "reason": reason,
            "recv_ms": stamp["recv_ms"],
            "status": "rejected",
        }

    def _error(self, op, reason, stamp, is_new=False):
        return {
            "done_ms": self.local_ms(),
            "dup": False,
            "frame_done": self.frame,
            "frame_recv": stamp["frame"],
            "op_id": op["op_id"],
            "read": _new_empty_read() if is_new else _empty_read(),
            "reason": reason,
            "recv_ms": stamp["recv_ms"],
            "status": "error",
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
        self.sync_cache_order()
        op_id = body["op_id"]
        stored = {k: v for k, v in body.items() if k != "_slow"}
        if op_id not in self.cache:
            self.cache_order.append(op_id)
        self.cache[op_id] = stored
        while len(self.cache_order) > CACHE_CAP:
            self.cache.pop(self.cache_order.pop(0), None)

    def _apply(self):
        left = []
        for item in self.effects:
            if item[0] <= self.frame:
                if item[1] == "fog":
                    self.fog = item[2]
                elif item[1] == "rpc_pose":
                    # Igual que DSBX_QA_Probe.ApplyPendingPose: sin lease vigente en este frame, la pose se descarta
                    # (F02-H3; el registro P7 no cambia; H5 de Sol r1).
                    if self.lease_valid():
                        self.pose = item[2]
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
        if not isinstance(msg, dict):
            return
        if "rpc_type" in msg:
            try:
                rpc_type = int(msg["rpc_type"])
            except (TypeError, ValueError):
                return
            if 26102800 <= rpc_type <= 26102889:
                idx = (rpc_type - 26102800) // 10
                if 0 <= idx < len(self.exts):
                    self.exts[idx].on_rpc(rpc_type, msg.get("payload"))
                return
            if rpc_type == 26102701 and self.role == "client":
                inner = msg.get("payload")
                if isinstance(inner, dict):
                    self._handle_cam_rpc(inner)
                return
            return
        if self.role == "client":
            self._handle_cam_rpc(msg)

    def _handle_cam_rpc(self, msg):
        lease_age = self.lease_age_ms()
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
            # Pose diferida al frame siguiente, como m_HasPendingPose de la sonda: se vuelve a mirar el lease al aplicarla.
            self.effects.append((self.frame + 1, "rpc_pose", (pos, ypr)))
        self.rpc_log.append(
            {
                "decision": decision,
                "lease_age_ms": lease_age,
                "recv_ms": self.local_ms(),
                "seq": int(msg.get("seq") or 0),
            }
        )
        while len(self.rpc_log) > LOG_CAP:
            self.rpc_log.pop(0)

    def _acquire_cb(self, kind):
        if self.budget_exhausted:
            return False
        if kind == "poll":
            if not self._poll_cb_alive:
                if self.callbacks_created_n >= self.callback_budget:
                    self._trip_budget_exhausted()
                    return False
                self.callbacks_created_n += 1
                self._poll_cb_alive = True
        else:
            if self._cb_pool:
                self._cb_pool.pop()
            else:
                if self.callbacks_created_n >= self.callback_budget:
                    self._trip_budget_exhausted()
                    return False
                self.callbacks_created_n += 1
        self._callbacks_inflight += 1
        return True

    def _settle_cb(self, kind, http_ok):
        self._callbacks_inflight = max(0, self._callbacks_inflight - 1)
        if kind == "poll":
            if not http_ok:
                self._poll_cb_alive = False
        else:
            if http_ok and len(self._cb_pool) < CALLBACK_POOL_MAX:
                self._cb_pool.append(True)

    def _trip_budget_exhausted(self):
        self.budget_exhausted = True
        if not self._logged_budget_exhausted:
            self._logged_budget_exhausted = True
            line = (
                f"[DSBX_QA] callback_budget_exhausted "
                f"created_n={self.callbacks_created_n} budget_n={self.callback_budget}"
            )
            self.status_logs.append(line)
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            if self.log_path is not None:
                try:
                    with self.log_path.open("a", encoding="utf-8", newline="\n") as fh:
                        fh.write(line + "\n")
                except OSError:
                    pass

    def _http_loop(self):
        while self.alive:
            if self.budget_exhausted:
                time.sleep(0.05)
                continue
            if self.cfg is None:
                fresh = self._read_config()
                if fresh is None:
                    time.sleep(self._p2_retry_s())
                    continue
                self.cfg = fresh
            cfg = self.cfg
            if not self.hello_ok:
                if self.fault != "no_key_reload":
                    reloaded = self._read_config()
                    if reloaded is None:
                        self.cfg = None
                        time.sleep(self._p2_retry_s())
                        continue
                    self.cfg = reloaded
                    cfg = reloaded
                self._hello(cfg)
                continue
            code, payload = self._request(cfg, "GET", "/poll", self._poll_query(), None, kind="poll")
            if self.budget_exhausted:
                continue
            if not _valid_poll_resp(code, payload):
                self._on_http_error()
                continue
            self.last_ok = time.monotonic()
            self.last_ok_ms = self.local_ms()
            self._reconnected_poll = True
            self.failures = 0
            bucket = []
            done = threading.Event()
            self.inbox.put((payload["ops"], payload["now_ms"], bucket, done))
            last_ka_ms = self.local_ms()
            while self.alive and not done.wait(timeout=0.05):
                if self.budget_exhausted or not self.hello_ok:
                    continue
                if bucket:
                    continue
                if not (self.jobs or self.burst is not None):
                    continue
                now_ka_ms = self.local_ms()
                if now_ka_ms - last_ka_ms < 500.0:
                    continue
                last_ka_ms = now_ka_ms
                ka_q = self._poll_query()
                ka_q["deliver"] = "0"
                ka_code, ka_payload = self._request(cfg, "GET", "/poll", ka_q, None, kind="poll")
                if self.budget_exhausted:
                    continue
                if _valid_poll_resp(ka_code, ka_payload):
                    self.last_ok = time.monotonic()
                    self.last_ok_ms = self.local_ms()
                    last_ka_ms = self.last_ok_ms
                # Un keepalive fallido no cambia el estado del transporte (igual que DSBX_QA_Probe.OnHttpDone,
                # rama KIND_KEEPALIVE): se reintenta a los 500 ms mientras dure la orden; el poll normal posterior
                # gestiona el fallo. Antes ponia hello_ok = False y cortaba las renovaciones (H4 de Sol r1).
            self._send_results(cfg, bucket)

    def _hello(self, cfg):
        body = {
            "build": self.build,
            "inst": self.inst,
            "peer": self.role,
            "probe_ver": self.resolve_probe_ver(),
            "proto": "qa0",
        }
        code, payload = self._request(cfg, "POST", "/hello", {}, body, kind="hello")
        if self.budget_exhausted:
            return
        if _valid_hello_resp(code, payload):
            self.lease_ms = int(payload["lease_ms"])
            self.hello_ok = True
            self.failures = 0
            return
        self._on_http_error()

    def _on_http_error(self):
        self.hello_ok = False
        self.failures += 1
        retry_ms = self.cfg["retry_ms"] if self.cfg is not None else 2000
        shift = min(self.failures - 1, 30)
        wait_ms = min(250 * (1 << shift), retry_ms)
        time.sleep(wait_ms / 1000.0)
        if self.fault != "no_key_reload":
            self.cfg = self._read_config()

    def _send_results(self, cfg, bucket):
        gaps = (0.0, 0.25, 0.5, 1.0)
        for body in bucket:
            slow = body.pop("_slow", False) if isinstance(body, dict) else False
            if slow:
                time.sleep(1.2)
            for gap in gaps:
                if not self.alive or self.budget_exhausted:
                    return
                if gap:
                    time.sleep(gap)
                code, payload = self._request(
                    cfg,
                    "POST",
                    "/result",
                    {"peer": self.role, "inst": self.inst},
                    body,
                    kind="result",
                )
                if self.budget_exhausted:
                    return
                if _valid_result_resp(code, payload):
                    break

    def _poll_query(self):
        return {
            "frame": str(self.frame),
            "inst": self.inst,
            "peer": self.role,
            "tick_s": str(self.local_ms() / 1000.0),
        }

    def _p2_retry_s(self):
        try:
            data = json.loads(Path(self.config).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return 2.0
        if not isinstance(data, dict):
            return 2.0
        try:
            retry = int(data.get("retry_ms") or 2000)
        except (TypeError, ValueError):
            retry = 2000
        if retry <= 0:
            retry = 2000
        return retry / 1000.0

    def _read_config(self):
        try:
            data = json.loads(Path(self.config).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        url = data.get("url")
        # Misma validacion que UrlUsable() de la sonda: exactamente "http://127.0.0.1:<1..5 digitos>/" con puerto
        # 1..65535. Si el peer falso fuera mas permisivo, el gate offline aprobaria configuraciones que la sonda real
        # rechaza (H1 de Sol r1).
        if not isinstance(url, str):
            return None
        url_m = re.fullmatch(r"http://127\.0\.0\.1:([0-9]{1,5})/", url)
        if url_m is None or not (1 <= int(url_m.group(1)) <= 65535):
            return None
        key = data.get("key")
        if not isinstance(key, str) or not key:
            return None
        try:
            retry = int(data.get("retry_ms") or 2000)
        except (TypeError, ValueError):
            retry = 2000
        if retry <= 0:
            retry = 2000
        try:
            budget = int(data.get("callback_budget") or DEFAULT_CALLBACK_BUDGET)
        except (TypeError, ValueError):
            budget = DEFAULT_CALLBACK_BUDGET
        if budget <= 0:
            budget = DEFAULT_CALLBACK_BUDGET
        self.callback_budget = budget
        return {"callback_budget": budget, "key": key, "retry_ms": retry, "url": url}

    def _request(self, cfg, method, path, query, body, kind="hello"):
        if not self._acquire_cb(kind):
            return 0, None
        params = {"key": cfg["key"]}
        params.update(query or {})
        url = cfg["url"].rstrip("/") + path + "?" + urllib.parse.urlencode(params)
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body, allow_nan=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        if kind == "result" and isinstance(body, dict):
            wit_line(
                ev="wit",
                phase="sent",
                pid=os.getpid(),
                role=self.role,
                inst=self.inst,
                op_id=body.get("op_id"),
                verb=body.get("verb"),
                status=body.get("status"),
                digest=wit_digest(body),
            )
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
            self._settle_cb(kind, False)
            return 0, None
        self._settle_cb(kind, code == 200)
        if not raw:
            return code, None
        try:
            payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_nonfinite)
        except (UnicodeError, ValueError):
            return code, None
        if kind == "poll" and code == 200 and isinstance(payload, dict) and isinstance(payload.get("ops"), list):
            for op in payload["ops"]:
                if isinstance(op, dict):
                    wit_line(
                        ev="wit",
                        phase="recv",
                        pid=os.getpid(),
                        role=self.role,
                        inst=self.inst,
                        op_id=op.get("op_id"),
                        verb=op.get("verb"),
                        status=None,
                        digest=wit_digest(op.get("args")),
                    )
        return code, payload


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


def _new_empty_read():
    out = _empty_read()
    out.update(wire.empty_payload())
    return out


def _new_payload_read(payload, has_payload=True):
    out = _empty_read()
    out["has"] = ["payload"] if has_payload else []
    out.update(payload)
    return out


def _bad_args(verb, args):
    if "pos" in args and args["pos"] is not None:
        pos = args["pos"]
        if not isinstance(pos, list) or len(pos) != 3:
            return True
    if "ypr" in args and args["ypr"] is not None:
        ypr = args["ypr"]
        if not isinstance(ypr, list) or len(ypr) != 3:
            return True
    if verb == "ambient_set":
        try:
            fog = float(args.get("fog"))
        except (TypeError, ValueError):
            return True
        if not math.isfinite(fog):
            return True
        return fog < 0 or fog > 1
    return False


def main(argv=None):
    sys.excepthook = _excepthook
    parser = argparse.ArgumentParser(prog="qa/fake_peer.py")
    parser.add_argument("--config", required=True)
    parser.add_argument("--peer", "--role", dest="peer", required=True, choices=("server", "client"))
    parser.add_argument("--rpc-port", required=True, type=int)
    parser.add_argument("--frame-hz", type=float, default=60)
    parser.add_argument("--fault", default=None)
    parser.add_argument("--clock-offset-ms", type=float, default=0.0)
    parser.add_argument("--git-head", default=None)
    parser.add_argument("--probe-ver", default=None)
    parser.add_argument("--log", default=None)
    parser.add_argument("--build", default=None)
    args = parser.parse_args(argv)
    wit_line(ev="wit_start", pid=os.getpid(), role=args.peer)
    Peer(
        args.config,
        args.peer,
        args.rpc_port,
        args.frame_hz,
        args.fault,
        clock_offset_ms=args.clock_offset_ms,
        git_head=args.git_head,
        probe_ver=args.probe_ver,
        log_path=args.log,
    ).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
