"""Novena extension DSBX_QA_X_Base para fake_peer (prefijo qa_, RPC 26102880..26102889)."""

import math
import re

import wire
from fake_peer import FakeExt

PREFIX = "qa_"
RPC_BASE = 26102880
DSBX_QA_RPC_BASE_PING = 26102880
PING_LOG_CAP = 512

_BOTH_VERBS = frozenset(
    {
        "qa_echo",
        "qa_timer_start",
        "qa_info",
        "qa_cache_fill",
        "qa_cache_snapshot",
        "qa_cache_page",
    }
)
_SERVER_ONLY_VERBS = frozenset(
    {
        "qa_rpc_ping",
        "qa_effect_start",
        "qa_emitlog_page",
    }
)
_CLIENT_ONLY_VERBS = frozenset(
    {
        "qa_rpclog_page",
        "qa_ping_page",
    }
)

_HEX16_RE = re.compile(r"^[0-9a-f]{16}$", re.ASCII)


def _is_int_num(val):
    if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
        return False
    return float(val).is_integer()


class BaseFakeExt(FakeExt):
    def __init__(self):
        super().__init__()
        self.peer = None
        self.jobs = None
        self.ext_init_b = 0
        self.ext_ticks_n = 0
        self.ext_end_calls_n = 0
        self.ext_last_end_job = ""
        self.ext_last_end_state = ""
        self.ext_last_end_reason = ""
        self.witness_armed = False
        self.witness_resource = ""
        self.witness_job_id = ""
        self.witness_started_tick_ms = 0.0
        self.witness_attempts_n = 0
        self.rpc_ping_count_n = 0
        self.rpc_last_token_n = 0
        self.ping_log = []
        self.cache_snapshot = None
        self.active_timers = {}
        self.active_effects = {}

    def init(self, peer, jobs):
        self.peer = peer
        self.jobs = jobs
        self.ext_init_b = 1

    def handles(self, verb, role):
        if verb in _BOTH_VERBS:
            return role in ("server", "client")
        if verb in _SERVER_ONLY_VERBS:
            return role == "server"
        if verb in _CLIENT_ONLY_VERBS:
            return role == "client"
        return False

    def on_start_op(self, op, args_unpacked, raw_args):
        verb = op["verb"]
        if verb == "qa_echo":
            return self._op_echo(args_unpacked, raw_args)
        if verb == "qa_timer_start":
            return self._op_timer_start(op, args_unpacked)
        if verb == "qa_rpc_ping":
            return self._op_rpc_ping(args_unpacked)
        if verb == "qa_info":
            return self._op_info()
        if verb == "qa_cache_fill":
            return self._op_cache_fill(args_unpacked)
        if verb == "qa_cache_snapshot":
            return self._op_cache_snapshot(op)
        if verb == "qa_cache_page":
            return self._op_cache_page(args_unpacked)
        if verb == "qa_rpclog_page":
            return self._op_rpclog_page(args_unpacked)
        if verb == "qa_ping_page":
            return self._op_ping_page(args_unpacked)
        if verb == "qa_effect_start":
            return self._op_effect_start(op, args_unpacked)
        if verb == "qa_emitlog_page":
            return self._op_emitlog_page(args_unpacked)
        return ("rejected", "unknown_verb", wire.empty_payload())

    def _op_echo(self, args_unpacked, raw_args):
        nums = args_unpacked["num"]
        pad_bytes = 0
        if "pad_bytes_n" in nums:
            raw_pad = nums["pad_bytes_n"]
            if not _is_int_num(raw_pad) or int(raw_pad) < 0:
                return ("rejected", "bad_args", wire.empty_payload())
            pad_bytes = int(raw_pad)

        sk = raw_args["sk"]
        sv = raw_args["sv"]
        nk = raw_args["nk"]
        nv = raw_args["nv"]
        ncol = raw_args["ncol"]
        ncell = raw_args["ncell"]
        scol = raw_args["scol"]
        scell = raw_args["scell"]
        rows = raw_args["rows"]

        sv_chars = sum(len(s) for s in sv) + sum(len(s) for s in scell)
        num_sum = float(sum(nv) + sum(ncell))
        first_sk = sk[0] if sk else ""
        last_sv = sv[-1] if sv else ""

        payload = wire.pack_payload(
            scalars_str={
                "first_sk": first_sk,
                "last_sv": last_sv,
                "ext_last_end_job": self.ext_last_end_job,
                "ext_last_end_state": self.ext_last_end_state,
                "ext_last_end_reason": self.ext_last_end_reason,
                "witness_job_id": self.witness_job_id,
                "pad": "x" * pad_bytes,
            },
            scalars_num={
                "sk_n": len(sk),
                "nk_n": len(nk),
                "rows_n": rows,
                "ncol_n": len(ncol),
                "scol_n": len(scol),
                "sv_chars_n": sv_chars,
                "num_sum": num_sum,
                "tick_ms": self.peer.local_ms(),
                "frame": self.peer.frame,
                "ext_init_b": self.ext_init_b,
                "ext_ticks_n": self.ext_ticks_n,
                "ext_end_calls_n": self.ext_end_calls_n,
                "witness_started_tick_ms": self.witness_started_tick_ms,
                "witness_attempts_n": self.witness_attempts_n,
                "rpc_ping_count_n": self.rpc_ping_count_n,
                "rpc_last_token_n": self.rpc_last_token_n,
            },
        )
        return ("done", "", payload)

    def _op_timer_start(self, op, args_unpacked):
        nums = args_unpacked["num"]
        if "duration_ms" not in nums or "sample_step_ms" not in nums:
            return ("rejected", "bad_args", wire.empty_payload())
        duration_ms = float(nums["duration_ms"])
        sample_step_ms = float(nums["sample_step_ms"])
        if duration_ms <= 0.0 or sample_step_ms < 0.0:
            return ("rejected", "bad_args", wire.empty_payload())

        max_rows_n = 4096
        if "max_rows_n" in nums:
            if not _is_int_num(nums["max_rows_n"]) or int(nums["max_rows_n"]) <= 0:
                return ("rejected", "bad_args", wire.empty_payload())
            max_rows_n = int(nums["max_rows_n"])

        max_duration_ms = 900000.0
        if "max_duration_ms" in nums:
            max_duration_ms = float(nums["max_duration_ms"])
            if max_duration_ms <= 0.0:
                return ("rejected", "bad_args", wire.empty_payload())

        witness_b = 0
        if "witness_b" in nums:
            if not _is_int_num(nums["witness_b"]) or int(nums["witness_b"]) not in (0, 1):
                return ("rejected", "bad_args", wire.empty_payload())
            witness_b = int(nums["witness_b"])

        op_id = op["op_id"]
        err = self.jobs.start_job(
            self,
            op_id,
            "qa_timer",
            ["seq_n", "frame", "tick_ms", "dtsum_ms"],
            [],
            20,
            max_rows_n,
            max_duration_ms,
            "continue",
        )
        if err != "":
            return ("rejected", err, wire.empty_payload())

        fault = op.get("qa_fault", "")
        freeze_wait = fault == "freeze_on_wait"
        defer_clean = fault == "defer_cleanup"
        self.jobs.configure_job_faults(op_id, freeze_on_wait=freeze_wait, defer_cleanup=defer_clean)

        self.active_timers[op_id] = {
            "dtsum_ms": 0.0,
            "duration_ms": duration_ms,
            "freeze_on_wait": freeze_wait,
            "next_sample_ms": 0.0,
            "sample_step_ms": sample_step_ms,
            "seq_n": 0,
        }

        if witness_b == 1:
            self.witness_armed = True
            self.witness_resource = "qa_timer"
            self.witness_job_id = f"{op_id}:witness"
            self.witness_started_tick_ms = 0.0
            self.witness_attempts_n = 0

        return ("done", "", self.jobs.fill_start_read(op_id, "qa_timer"))

    def _op_rpc_ping(self, args_unpacked):
        nums = args_unpacked["num"]
        strs = args_unpacked["str"]
        if "token_n" not in nums or not _is_int_num(nums["token_n"]) or int(nums["token_n"]) <= 0:
            return ("rejected", "bad_args", wire.empty_payload())
        client_inst = strs.get("client_inst", "")
        if not isinstance(client_inst, str) or client_inst == "":
            return ("rejected", "bad_args", wire.empty_payload())
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        token_n = int(nums["token_n"])
        self.peer.send_ext_rpc(
            DSBX_QA_RPC_BASE_PING,
            {"token_n": token_n, "client_inst": client_inst},
        )
        return ("done", "", wire.pack_payload(scalars_num={"sent_token_n": token_n}))

    def _op_info(self):
        info = self.peer.info_snapshot()
        payload = wire.pack_payload(
            scalars_str={
                "probe_ver": info["probe_ver"],
                "role": self.peer.role,
            },
            scalars_num={
                "callbacks_created_n": info["callbacks_created_n"],
                "callbacks_pooled_n": info["callbacks_pooled_n"],
                "callbacks_inflight_n": info["callbacks_inflight_n"],
                "callback_budget_n": info["callback_budget_n"],
                "cache_size_n": info["cache_size_n"],
                "rpclog_size_n": info["rpclog_size_n"],
                "jobs_live_n": info["jobs_live_n"],
            },
        )
        return ("done", "", payload)

    def _op_cache_fill(self, args_unpacked):
        nums = args_unpacked["num"]
        strs = args_unpacked["str"]
        if "n_n" not in nums or not _is_int_num(nums["n_n"]):
            return ("rejected", "bad_args", wire.empty_payload())
        n_n = int(nums["n_n"])
        if not (1 <= n_n <= 2048):
            return ("rejected", "bad_args", wire.empty_payload())
        fill_id = strs.get("fill_id", "")
        if not isinstance(fill_id, str) or not _HEX16_RE.fullmatch(fill_id):
            return ("rejected", "bad_args", wire.empty_payload())

        now_ms = self.peer.local_ms()
        frame = self.peer.frame
        for i in range(n_n):
            synth_id = f"{fill_id}-{i}"
            synth_body = self.peer.make_synthetic_cached_result(synth_id, now_ms, frame)
            self.peer.remember_result(synth_body)

        first_id = f"{fill_id}-0"
        last_id = f"{fill_id}-{n_n - 1}"
        payload = wire.pack_payload(
            scalars_str={"first_id": first_id, "last_id": last_id},
            scalars_num={"inserted_n": n_n, "cache_size_n": len(self.peer.cache_order)},
        )
        return ("done", "", payload)

    def _op_cache_snapshot(self, op):
        self.peer.sync_cache_order()
        ids = list(self.peer.cache_order)
        snap_id = op["op_id"]
        self.cache_snapshot = {"snap_id": snap_id, "ids": ids}
        payload = wire.pack_payload(
            scalars_str={"snap_id": snap_id},
            scalars_num={"rows_total_n": len(ids)},
        )
        return ("done", "", payload)

    def _op_cache_page(self, args_unpacked):
        nums = args_unpacked["num"]
        strs = args_unpacked["str"]
        snap_id = strs.get("snap_id", "")
        if self.cache_snapshot is None or snap_id != self.cache_snapshot["snap_id"]:
            return ("rejected", "bad_args", wire.empty_payload())
        if "page_n" not in nums or not _is_int_num(nums["page_n"]):
            return ("rejected", "bad_args", wire.empty_payload())
        page_n = int(nums["page_n"])
        ids = self.cache_snapshot["ids"]
        rows_total = len(ids)
        page_size = 50
        pages_n = 0 if rows_total == 0 else (rows_total + page_size - 1) // page_size
        if page_n < 0 or (rows_total == 0 and page_n > 0) or (rows_total > 0 and page_n >= pages_n):
            return ("rejected", "bad_args", wire.empty_payload())
        start = page_n * page_size
        end = min(start + page_size, rows_total)
        row_dicts = [{"idx_n": idx, "op_id": ids[idx]} for idx in range(start, end)]
        payload = wire.pack_payload(
            scalars_num={"page_n": page_n, "pages_n": pages_n, "rows_total_n": rows_total},
            num_cols=["idx_n"],
            str_cols=["op_id"],
            row_dicts=row_dicts,
        )
        return ("done", "", payload)

    def _op_rpclog_page(self, args_unpacked):
        nums = args_unpacked["num"]
        if "page_n" not in nums or not _is_int_num(nums["page_n"]):
            return ("rejected", "bad_args", wire.empty_payload())
        page_n = int(nums["page_n"])
        entries = list(self.peer.rpc_log)
        rows_total = len(entries)
        page_size = 40
        pages_n = 0 if rows_total == 0 else (rows_total + page_size - 1) // page_size
        if page_n < 0 or (rows_total == 0 and page_n > 0) or (rows_total > 0 and page_n >= pages_n):
            return ("rejected", "bad_args", wire.empty_payload())
        start = page_n * page_size
        end = min(start + page_size, rows_total)
        row_dicts = [
            {
                "seq_n": int(entries[idx]["seq"]),
                "recv_ms": float(entries[idx]["recv_ms"]),
                "lease_age_ms": float(entries[idx]["lease_age_ms"]),
                "idx_n": idx,
                "decision": str(entries[idx]["decision"]),
            }
            for idx in range(start, end)
        ]
        payload = wire.pack_payload(
            scalars_num={"page_n": page_n, "pages_n": pages_n, "rows_total_n": rows_total},
            num_cols=["seq_n", "recv_ms", "lease_age_ms", "idx_n"],
            str_cols=["decision"],
            row_dicts=row_dicts,
        )
        return ("done", "", payload)

    def _op_ping_page(self, args_unpacked):
        nums = args_unpacked["num"]
        if "page_n" not in nums or not _is_int_num(nums["page_n"]):
            return ("rejected", "bad_args", wire.empty_payload())
        page_n = int(nums["page_n"])
        entries = list(self.ping_log)
        rows_total = len(entries)
        page_size = 40
        pages_n = 0 if rows_total == 0 else (rows_total + page_size - 1) // page_size
        if page_n < 0 or (rows_total == 0 and page_n > 0) or (rows_total > 0 and page_n >= pages_n):
            return ("rejected", "bad_args", wire.empty_payload())
        start = page_n * page_size
        end = min(start + page_size, rows_total)
        row_dicts = [
            {
                "token_n": int(entries[idx]["token_n"]),
                "recv_ms": float(entries[idx]["recv_ms"]),
                "idx_n": idx,
            }
            for idx in range(start, end)
        ]
        payload = wire.pack_payload(
            scalars_num={"page_n": page_n, "pages_n": pages_n, "rows_total_n": rows_total},
            num_cols=["token_n", "recv_ms", "idx_n"],
            str_cols=[],
            row_dicts=row_dicts,
        )
        return ("done", "", payload)

    def _op_effect_start(self, op, args_unpacked):
        nums = args_unpacked["num"]
        strs = args_unpacked["str"]
        if "period_ms" not in nums or "count_n" not in nums or "token0_n" not in nums:
            return ("rejected", "bad_args", wire.empty_payload())
        period_ms = float(nums["period_ms"])
        if period_ms < 100.0:
            return ("rejected", "bad_args", wire.empty_payload())
        if not _is_int_num(nums["count_n"]) or int(nums["count_n"]) < 1:
            return ("rejected", "bad_args", wire.empty_payload())
        if not _is_int_num(nums["token0_n"]) or int(nums["token0_n"]) <= 0:
            return ("rejected", "bad_args", wire.empty_payload())
        client_inst = strs.get("client_inst", "")
        if not isinstance(client_inst, str) or client_inst == "":
            return ("rejected", "bad_args", wire.empty_payload())

        witness_b = 1
        if "witness_b" in nums:
            if not _is_int_num(nums["witness_b"]) or int(nums["witness_b"]) not in (0, 1):
                return ("rejected", "bad_args", wire.empty_payload())
            witness_b = int(nums["witness_b"])

        count_n = int(nums["count_n"])
        token0_n = int(nums["token0_n"])
        op_id = op["op_id"]
        err = self.jobs.start_job(
            self,
            op_id,
            "qa_effect",
            ["token_n", "tick_ms", "lease_age_ms"],
            ["outcome"],
            20,
            4096,
            900000.0,
            "stop",
        )
        if err != "":
            return ("rejected", err, wire.empty_payload())
        self.jobs.configure_job_faults(op_id, ext_handles_deadman=True)

        self.active_effects[op_id] = {
            "client_inst": client_inst,
            "count_n": count_n,
            "dtsum_ms": 0.0,
            "next_emit_ms": 0.0,
            "period_ms": period_ms,
            "qa_fault": op.get("qa_fault", ""),
            "sent_count": 0,
            "token0_n": token0_n,
        }

        if witness_b == 1:
            self.witness_armed = True
            self.witness_resource = "qa_effect"
            self.witness_job_id = f"{op_id}:witness"
            self.witness_started_tick_ms = 0.0
            self.witness_attempts_n = 0

        return ("done", "", self.jobs.fill_start_read(op_id, "qa_effect"))

    def _op_emitlog_page(self, args_unpacked):
        nums = args_unpacked["num"]
        if "page_n" not in nums or not _is_int_num(nums["page_n"]):
            return ("rejected", "bad_args", wire.empty_payload())
        page_n = int(nums["page_n"])
        entries = list(self.peer.emit_log)
        rows_total = len(entries)
        page_size = 40
        pages_n = 0 if rows_total == 0 else (rows_total + page_size - 1) // page_size
        if page_n < 0 or (rows_total == 0 and page_n > 0) or (rows_total > 0 and page_n >= pages_n):
            return ("rejected", "bad_args", wire.empty_payload())
        start = page_n * page_size
        end = min(start + page_size, rows_total)
        row_dicts = [
            {
                "seq_n": int(entries[idx]["seq_n"]),
                "tick_ms": float(entries[idx]["tick_ms"]),
                "lease_age_ms": float(entries[idx]["lease_age_ms"]),
                "idx_n": idx,
                "op_id": str(entries[idx]["op_id"]),
                "outcome": str(entries[idx]["outcome"]),
            }
            for idx in range(start, end)
        ]
        payload = wire.pack_payload(
            scalars_num={"page_n": page_n, "pages_n": pages_n, "rows_total_n": rows_total},
            num_cols=["seq_n", "tick_ms", "lease_age_ms", "idx_n"],
            str_cols=["op_id", "outcome"],
            row_dicts=row_dicts,
        )
        return ("done", "", payload)

    def on_tick(self, timeslice_s):
        self.ext_ticks_n += 1
        dt_ms = float(timeslice_s) * 1000.0

        for jid, timer in list(self.active_timers.items()):
            if self.jobs.get_state(jid) != "running":
                self.active_timers.pop(jid, None)
                continue
            if timer["freeze_on_wait"] and not self.peer.is_transport_connected():
                continue
            timer["dtsum_ms"] += dt_ms
            if timer["dtsum_ms"] >= timer["duration_ms"]:
                seq = timer["seq_n"]
                timer["seq_n"] = seq + 1
                ok = self.jobs.append_row(
                    jid,
                    [seq, self.peer.frame, self.peer.local_ms(), timer["dtsum_ms"]],
                    [],
                )
                if ok:
                    self.jobs.end_job(jid, "done", "")
                continue
            if timer["dtsum_ms"] >= timer["next_sample_ms"]:
                seq = timer["seq_n"]
                timer["seq_n"] = seq + 1
                ok = self.jobs.append_row(
                    jid,
                    [seq, self.peer.frame, self.peer.local_ms(), timer["dtsum_ms"]],
                    [],
                )
                if not ok:
                    continue
                if timer["sample_step_ms"] > 0.0:
                    timer["next_sample_ms"] += timer["sample_step_ms"]
                else:
                    timer["next_sample_ms"] = timer["dtsum_ms"]

        for jid, eff in list(self.active_effects.items()):
            if self.jobs.get_state(jid) != "running":
                self.active_effects.pop(jid, None)
                continue
            eff["dtsum_ms"] += dt_ms
            if eff["dtsum_ms"] < eff["next_emit_ms"]:
                continue
            now_tick = self.peer.local_ms()
            lease_age = self.peer.lease_age_ms()
            tok = eff["token0_n"] + eff["sent_count"]
            if eff["qa_fault"] != "ignore_deadman" and self.jobs.is_deadman_tripped(jid):
                self.jobs.append_row(jid, [tok, now_tick, lease_age], ["blocked_lease"])
                self.jobs.end_job(jid, "failed", "lease_expired")
                continue
            if eff["qa_fault"] != "skip_send":
                self.peer.send_ext_rpc(
                    DSBX_QA_RPC_BASE_PING,
                    {"token_n": tok, "client_inst": eff["client_inst"]},
                )
            ok = self.jobs.append_row(jid, [tok, now_tick, lease_age], ["sent"])
            eff["sent_count"] += 1
            eff["next_emit_ms"] += eff["period_ms"]
            if ok and eff["sent_count"] >= eff["count_n"]:
                self.jobs.end_job(jid, "done", "")

        if self.witness_armed:
            self.witness_attempts_n += 1
            res_name = self.witness_resource
            w_id = self.witness_job_id
            w_err = self.jobs.start_job(
                self,
                w_id,
                res_name,
                ["seq_n", "frame", "tick_ms", "dtsum_ms"],
                [],
                20,
                4096,
                900000.0,
                "continue",
            )
            if w_err == "":
                # §13 A2: unica lectura del reloj, recuperada del registro de B.
                self.witness_started_tick_ms = self.jobs.get_start_tick_ms(w_id)
                self.witness_armed = False
                self.active_timers[w_id] = {
                    "dtsum_ms": 0.0,
                    "duration_ms": 200.0,
                    "freeze_on_wait": False,
                    "next_sample_ms": 0.0,
                    "sample_step_ms": 50.0,
                    "seq_n": 0,
                }

    def on_job_end(self, job_id, state, reason):
        self.active_timers.pop(job_id, None)
        self.active_effects.pop(job_id, None)
        self.ext_end_calls_n += 1
        self.ext_last_end_job = job_id
        self.ext_last_end_state = state
        self.ext_last_end_reason = reason

    def on_rpc(self, rpc_type, payload):
        if rpc_type != DSBX_QA_RPC_BASE_PING or self.peer.role != "client":
            return
        if not isinstance(payload, dict):
            return
        if payload.get("client_inst") != self.peer.inst:
            return
        try:
            token_n = int(payload.get("token_n") or 0)
        except (TypeError, ValueError):
            return
        # §5.3 encargo: registrar en m_PingLog antes de comprobar lease.
        self.ping_log.append(
            {
                "token_n": token_n,
                "recv_ms": self.peer.local_ms(),
            }
        )
        while len(self.ping_log) > PING_LOG_CAP:
            self.ping_log.pop(0)
        if self.peer.fault == "rpc_ignores_lease" or self.peer.lease_valid():
            self.rpc_ping_count_n += 1
            self.rpc_last_token_n = token_n

    def on_shutdown(self):
        self.active_timers.clear()
        self.active_effects.clear()
        self.witness_armed = False


def create_ext(peer, jobs):
    return BaseFakeExt()
