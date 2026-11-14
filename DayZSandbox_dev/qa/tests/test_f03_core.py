"""Suite offline del contrato comun F0.3-0 (brief §8.1(3), §8.1(6), §13 A1-A5, §14 F02-H1..H5).

Protege las importaciones de modulos nuevos para que al copiarse sobre e3f530e
cargue sin ImportError y falle por asercion sobre la conducta vieja en cada uno
de los tres grupos: bridge_qa, m1_gate y fake_peer (§7.4 del encargo).
"""

import contextlib
import copy
import http.client
import importlib
import inspect
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import bridge_qa
import fake_peer
import gate_core
import m1_gate
import s_puente_eval
import s_puente_run
from .synth import write_case


def _opt_import(module_name: str):
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError:
        return None


wire = _opt_import("wire")
stamp_probe = _opt_import("stamp_probe")
f03_common = _opt_import("f03_common")
fake_ext_base = _opt_import("fake_ext_base")
f03_base_eval = _opt_import("f03_base_eval")
f03_base_mutants = _opt_import("f03_base_mutants")
f03_base_run = _opt_import("f03_base_run")

QA_DIR = Path(__file__).resolve().parents[1]
DEV_ROOT = QA_DIR.parent
REPO_TOP = DEV_ROOT.parent


def _http_call(port: int, method: str, path: str, key: str, body=None, query: str = ""):
    sep = "&" if query else ""
    full = f"{path}?{query}{sep}key={key}" if key is not None else (f"{path}?{query}" if query else path)
    raw = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"} if raw is not None else {}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    try:
        conn.request(method, full, body=raw, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        return resp.status, (json.loads(data) if data else {})
    finally:
        conn.close()


def _free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def _git_run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def _init_temp_git_repo(root: Path, wire_cap: int = 3500, extra_probe_text: str = "// v1\n") -> str:
    dev = root / "DayZSandbox_dev"
    probe_dir = dev / "qa" / "probe" / "DayZSandbox_QA" / "scripts" / "5_Mission"
    probe_dir.mkdir(parents=True, exist_ok=True)
    (dev / "qa" / "probe" / "DayZSandbox_QA" / "config.cpp").write_bytes(b"class CfgPatches {};\n")
    (probe_dir / "DSBX_QA_Probe.c").write_bytes(f"class DSBX_QA_Probe {{}}\n{extra_probe_text}".encode("utf-8"))
    (probe_dir / "DSBX_QA_Stamp.c").write_bytes(b'const string DSBX_QA_STAMP = "unstamped";\n')
    (dev / "qa" / "wire.py").write_bytes(f"WIRE_CAP = {int(wire_cap)}\n".encode("utf-8"))

    _git_run(root, "init")
    _git_run(root, "config", "user.email", "qa@example.invalid")
    _git_run(root, "config", "user.name", "QA")
    _git_run(root, "add", ".")
    _git_run(root, "commit", "-m", "initial")
    return _git_run(root, "rev-parse", "HEAD").stdout.strip()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")


def _make_read_payload(payload_packed: dict) -> dict:
    r = {
        "fog": 0.0,
        "frame": 10,
        "has": ["payload"],
        "ncell": list(payload_packed["ncell"]),
        "ncol": list(payload_packed["ncol"]),
        "nk": list(payload_packed["nk"]),
        "nv": list(payload_packed["nv"]),
        "pos": [0.0, 0.0, 0.0],
        "rows": int(payload_packed["rows"]),
        "rpc_log": [],
        "scell": list(payload_packed["scell"]),
        "scol": list(payload_packed["scol"]),
        "sk": list(payload_packed["sk"]),
        "sv": list(payload_packed["sv"]),
        "tick_s": 1.0,
        "y": 0.0,
        "ypr": [0.0, 0.0, 0.0],
    }
    return r


def _write_synthetic_base_part(
    part_dir: Path,
    *,
    git_head: str,
    probe_stamp: str,
    wire_cap: int = 3500,
    build: str = "offline",
    git_dirty: bool = False,
    pbo_sha256: str | None = None,
    nonce16: str | None = None,
    exec_port: int = 51000,
    exec_pids: tuple[int | None, int | None] = (1001, 1002),
    fail_check: str | None = None,
    missing_check: str | None = None,
    tech_detail: str | None = None,
) -> dict:
    """Construye una parte sintetica completa de F0.3-0 (13/13 checks en pass por defecto)."""
    pdir = Path(part_dir)
    samples = pdir / "samples"
    samples.mkdir(parents=True, exist_ok=True)

    nonce = nonce16 or secrets.token_hex(8)
    seq = 0

    def _next_id() -> str:
        nonlocal seq
        seq += 1
        return f"{nonce}-{seq}"

    bridge_rows: list[dict] = []
    scen_rows: list[dict] = []
    t_cursor = [100.0]

    def _t(step: float = 5.0) -> float:
        t_cursor[0] = round(t_cursor[0] + step, 3)
        return t_cursor[0]

    for role, inst in (("server", "srv-inst-1"), ("client", "cli-inst-1")):
        bridge_rows.append(
            {
                "args": {
                    "build": build,
                    "inst": inst,
                    "peer": role,
                    "probe_ver": f"dsbx-qa1+{probe_stamp}",
                    "proto": "qa0",
                },
                "ev": "hello",
                "http": 200,
                "inst": inst,
                "ok": True,
                "peer": role,
                "t_ms": _t(),
            }
        )

    def _emit_op(
        peer: str,
        verb: str,
        enq_args: dict,
        res_status: str,
        res_reason: str,
        payload_packed: dict | None,
        *,
        op_id: str | None = None,
        dup: bool = False,
        poll_body_len: int = 320,
        res_body_len: int = 340,
    ) -> str:
        oid = op_id or _next_id()
        inst = "srv-inst-1" if peer == "server" else "cli-inst-1"
        bridge_rows.append(
            {
                "args": enq_args,
                "ev": "enq",
                "inst": inst,
                "op_id": oid,
                "peer": peer,
                "t_ms": _t(1.0),
                "verb": verb,
            }
        )
        now_v = _t(1.0)
        bridge_rows.append(
            {
                "body_len": poll_body_len,
                "ev": "poll",
                "frame": 10,
                "held_ms": 1.0,
                "http": 200,
                "inst": inst,
                "n_ops": 1,
                "now_ms": now_v,
                "op_ids": [oid],
                "peer": peer,
                "t_ms": now_v,
                "tick_s": round(now_v / 1000.0, 3),
            }
        )
        read_obj = (
            _make_read_payload(payload_packed)
            if payload_packed is not None
            else _make_read_payload(wire.empty_payload())
        )
        if res_status != "done" and not dup:
            read_obj["has"] = []
        bridge_rows.append(
            {
                "body_len": res_body_len,
                "ev": "result",
                "http": 200,
                "op_id": oid,
                "peer": peer,
                "result": {
                    "done_ms": _t(1.0),
                    "dup": dup,
                    "frame_done": 11,
                    "frame_recv": 10,
                    "op_id": oid,
                    "read": read_obj,
                    "reason": res_reason,
                    "recv_ms": now_v,
                    "status": res_status,
                },
                "t_ms": _t(0.5),
            }
        )
        return oid

    # BASE-01
    for peer in ("server", "client"):
        enq_a = wire.pack_payload(
            scalars_str={"pad_in": "x" * 80},
            scalars_num={"v1_n": 12.5, "v2_n": -2.5},
            num_cols=["c_n"],
            str_cols=["c_s"],
            row_dicts=[{"c_n": 1.0, "c_s": "ab"}, {"c_n": 2.0, "c_s": "cd"}],
        )
        out_p = wire.pack_payload(
            scalars_num={"sk_n": 1, "nk_n": 2, "rows_n": 2, "sv_chars_n": 84, "num_sum": 13.0}
        )
        oid = _emit_op(peer, "qa_echo", enq_a, "done", "", out_p, poll_body_len=wire_cap - 4)
        scen_rows.append({"check": "BASE-01", "op_id": oid, "peer": peer, "t_ms": _t()})

    # BASE-02
    for peer in ("server", "client"):
        ok_id = _emit_op(
            peer,
            "qa_echo",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_str={"pad": "y" * 20}),
            res_body_len=wire_cap - 6,
        )
        over_id = _emit_op(peer, "qa_echo", wire.empty_payload(), "error", "result_too_large", None)
        scen_rows.append({"check": "BASE-02", "ok_op_id": ok_id, "over_op_id": over_id, "peer": peer, "t_ms": _t()})

    # BASE-03
    for peer in ("server", "client"):
        pre_id = _emit_op(
            peer,
            "qa_echo",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_num={"ext_end_calls_n": 0, "ext_init_b": 1}),
        )
        st_id = _emit_op(
            peer,
            "qa_timer_start",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_str={"job": "j", "state": "running", "resource": "qa_timer"}),
        )
        conc = []
        for _ in range(5):
            cid = _emit_op(
                peer,
                "job_read",
                wire.empty_payload(),
                "done",
                "",
                wire.pack_payload(scalars_str={"state": "running"}, scalars_num={"rows_total_n": 5, "pages_n": 1}),
            )
            conc.append(cid)
        end_state = "done" if fail_check == "BASE-03" else "stopped"
        s1_id = _emit_op(
            peer,
            "job_stop",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_str={"state": end_state}, scalars_num={"rows_total_n": 40}),
        )
        s2_id = _emit_op(
            peer,
            "job_stop",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_str={"state": end_state}, scalars_num={"rows_total_n": 40}),
        )
        post_id = _emit_op(
            peer,
            "qa_echo",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(
                scalars_str={"ext_last_end_state": end_state},
                scalars_num={"ext_end_calls_n": 1, "ext_init_b": 1},
            ),
        )
        if missing_check != "BASE-03":
            scen_rows.append(
                {
                    "check": "BASE-03",
                    "concurrent_op_ids": conc,
                    "peer": peer,
                    "post_echo_op_id": post_id,
                    "pre_echo_op_id": pre_id,
                    "start_op_id": st_id,
                    "stop1_op_id": s1_id,
                    "stop2_op_id": s2_id,
                    "t_ms": _t(),
                }
            )

    # BASE-04 y BASE-05
    for peer in ("server", "client"):
        st_id = _emit_op(peer, "qa_timer_start", wire.empty_payload(), "done", "", wire.empty_payload())
        pe_id = _emit_op(
            peer,
            "qa_echo",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_str={"ext_last_end_state": "done"}),
        )
        pids = []
        for pno in range(5):
            rdicts = [
                {
                    "seq_n": pno * 20 + k,
                    "frame": pno * 20 + k,
                    "tick_ms": 1000.0 + (pno * 20 + k + 1) * 101.0,
                    "dtsum_ms": (pno * 20 + k + 1) * 101.0,
                }
                for k in range(20)
            ]
            pid = _emit_op(
                peer,
                "job_read",
                wire.empty_payload(),
                "done",
                "",
                wire.pack_payload(
                    scalars_str={"state": "done", "reason": ""},
                    scalars_num={
                        "page_n": pno,
                        "pages_n": 5,
                        "rows_total_n": 100,
                        "start_tick_ms": 1000.0,
                        "end_tick_ms": 11100.0,
                        "onjobend_tick_ms": 11100.0,
                        "released_tick_ms": 11100.0,
                    },
                    num_cols=["seq_n", "frame", "tick_ms", "dtsum_ms"],
                    row_dicts=rdicts,
                ),
            )
            pids.append(pid)
        scen_rows.append(
            {"check": "BASE-04", "page_op_ids": pids, "peer": peer, "post_echo_op_id": pe_id, "start_op_id": st_id, "t_ms": _t()}
        )
        scen_rows.append({"check": "BASE-05", "page_op_ids": pids, "peer": peer, "start_op_id": st_id, "t_ms": _t()})

    # BASE-06
    for peer in ("server", "client"):
        f_id = _emit_op(peer, "qa_timer_start", wire.empty_payload(), "done", "", wire.empty_payload())
        s_id = _emit_op(peer, "qa_timer_start", wire.empty_payload(), "rejected", "busy", None)
        fp_id = _emit_op(
            peer,
            "job_read",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_str={"state": "done"}, scalars_num={"page_n": 0, "pages_n": 1, "rows_total_n": 0}),
        )
        scen_rows.append(
            {"check": "BASE-06", "first_op_id": f_id, "first_page_op_ids": [fp_id], "peer": peer, "second_op_id": s_id, "t_ms": _t()}
        )

    # BASE-07
    pre7 = _emit_op("client", "qa_echo", wire.empty_payload(), "done", "", wire.pack_payload(scalars_num={"rpc_ping_count_n": 0}))
    ping7 = _emit_op("server", "qa_rpc_ping", wire.empty_payload(), "done", "", wire.pack_payload(scalars_num={"sent_token_n": 4242}))
    post7 = _emit_op(
        "client",
        "qa_echo",
        wire.empty_payload(),
        "done",
        "",
        wire.pack_payload(scalars_num={"rpc_ping_count_n": 1, "rpc_last_token_n": 4242}),
    )
    pp7 = _emit_op(
        "client",
        "qa_ping_page",
        wire.empty_payload(),
        "done",
        "",
        wire.pack_payload(
            scalars_num={"page_n": 0, "pages_n": 1, "rows_total_n": 1},
            num_cols=["token_n", "recv_ms", "idx_n"],
            row_dicts=[{"token_n": 4242, "recv_ms": 200.0, "idx_n": 0}],
        ),
    )
    scen_rows.append(
        {"check": "BASE-07", "ping_op_id": ping7, "ping_page_op_ids": [pp7], "post_echo_op_id": post7, "pre_echo_op_id": pre7, "t_ms": _t()}
    )

    # BASE-09
    for peer in ("server", "client"):
        fhex = secrets.token_hex(8)
        first_id = f"{fhex}-0"
        last_id = f"{fhex}-1029"
        fill_oid = _emit_op(
            peer,
            "qa_cache_fill",
            wire.pack_payload({"fill_id": fhex}, {"n_n": 1030}),
            "done",
            "",
            wire.pack_payload(
                {"first_id": first_id, "last_id": last_id},
                {"inserted_n": 1030, "cache_size_n": 1024},
            ),
        )
        expected_ids = [f"{fhex}-{i}" for i in range(7, 1030)] + [fill_oid]
        if fail_check == "BASE-09_interior":
            expected_ids = [f"{fhex}-6"] + [x for idx_i, x in enumerate(expected_ids) if idx_i != 500]
        elif fail_check == "BASE-09_order":
            expected_ids = list(expected_ids)
            expected_ids[10], expected_ids[900] = expected_ids[900], expected_ids[10]

        snap_oid = _next_id()
        _emit_op(
            peer,
            "qa_cache_snapshot",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload({"snap_id": snap_oid}, {"rows_total_n": 1024}),
            op_id=snap_oid,
        )
        cpage_ids = []
        for pno in range(21):
            st_i = pno * 50
            en_i = min(st_i + 50, 1024)
            rdicts = [{"idx_n": ix, "op_id": expected_ids[ix]} for ix in range(st_i, en_i)]
            cpid = _emit_op(
                peer,
                "qa_cache_page",
                wire.pack_payload({"snap_id": snap_oid}, {"page_n": pno}),
                "done",
                "",
                wire.pack_payload(
                    scalars_num={"page_n": pno, "pages_n": 21, "rows_total_n": 1024},
                    num_cols=["idx_n"],
                    str_cols=["op_id"],
                    row_dicts=rdicts,
                ),
            )
            cpage_ids.append(cpid)

        _emit_op(peer, "qa_echo", wire.empty_payload(), "done", "", wire.empty_payload(), op_id=last_id, dup=True)
        _emit_op(
            peer,
            "qa_echo",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_num={"sk_n": 1}),
            op_id=first_id,
            dup=False,
        )
        scen_rows.append(
            {"check": "BASE-09", "fill_op_id": fill_oid, "page_op_ids": cpage_ids, "peer": peer, "snap_op_id": snap_oid, "t_ms": _t()}
        )

    # BASE-10
    b10 = _emit_op("server", "rpc_burst", {}, "done", "", None)
    rp10_ids = []
    for pno in range(13):
        st_i = pno * 40
        en_i = min(st_i + 40, 512)
        rdicts = [
            {"seq_n": 1008 + ix, "recv_ms": 500.0 + ix, "lease_age_ms": 20.0, "idx_n": ix, "decision": "accepted"}
            for ix in range(st_i, en_i)
        ]
        rpid = _emit_op(
            "client",
            "qa_rpclog_page",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(
                scalars_num={"page_n": pno, "pages_n": 13, "rows_total_n": 512},
                num_cols=["seq_n", "recv_ms", "lease_age_ms", "idx_n"],
                str_cols=["decision"],
                row_dicts=rdicts,
            ),
        )
        rp10_ids.append(rpid)
    scen_rows.append({"burst_op_id": b10, "check": "BASE-10", "count": 520, "page_op_ids": rp10_ids, "seq0": 1000, "t_ms": _t()})

    # BASE-12
    for peer in ("server", "client"):
        bef12 = _emit_op(
            peer,
            "qa_info",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_num={"callbacks_created_n": 3, "callback_budget_n": 2000, "callbacks_inflight_n": 1}),
        )
        e12_ids = [_emit_op(peer, "qa_echo", wire.empty_payload(), "done", "", wire.empty_payload()) for _ in range(50)]
        aft12 = _emit_op(
            peer,
            "qa_info",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_num={"callbacks_created_n": 3, "callback_budget_n": 2000, "callbacks_inflight_n": 1}),
        )
        scen_rows.append(
            {"after_op_id": aft12, "before_op_id": bef12, "check": "BASE-12", "echo_op_ids": e12_ids, "peer": peer, "t_ms": _t()}
        )

    # BASE-08
    for peer in ("server", "client"):
        st8 = _emit_op(peer, "qa_timer_start", wire.empty_payload(), "done", "", wire.empty_payload())
        cut_s = _t(10.0)
        bridge_rows.append({"ev": "cut_start", "peer": peer, "t_ms": cut_s})
        cut_e = _t(3500.0)
        bridge_rows.append({"ev": "cut_end", "peer": peer, "t_ms": cut_e})
        rec_t = _t(50.0)
        bridge_rows.append(
            {
                "body_len": 25,
                "ev": "poll",
                "frame": 400,
                "held_ms": 0.0,
                "http": 200,
                "inst": "srv-inst-1" if peer == "server" else "cli-inst-1",
                "n_ops": 0,
                "now_ms": rec_t,
                "op_ids": [],
                "peer": peer,
                "t_ms": rec_t,
                "tick_s": round(rec_t / 1000.0, 3),
            }
        )
        rel_tick = rec_t + 50.0 if fail_check == "BASE-08" else cut_s + 1200.0
        w_tick = rec_t + 60.0 if fail_check == "BASE-08" else cut_s + 1216.0
        rdicts8 = [{"seq_n": i, "frame": i, "tick_ms": cut_s + i * 50.0, "dtsum_ms": (i + 1) * 50.0} for i in range(12)]
        if tech_detail == "result_lost" and peer == "server":
            ar8 = _next_id()
            bridge_rows.append({"ev": "lost", "op_id": ar8, "peer": peer, "reason": "result_lost", "t_ms": _t(), "verb": "job_read"})
        else:
            ar8 = _emit_op(
                peer,
                "job_read",
                wire.empty_payload(),
                "done",
                "",
                wire.pack_payload(
                    scalars_str={"state": "expired", "reason": "job_timeout"},
                    scalars_num={
                        "page_n": 0,
                        "pages_n": 1,
                        "rows_total_n": 12,
                        "start_tick_ms": cut_s,
                        "end_tick_ms": cut_s + 1200.0,
                        "onjobend_tick_ms": rel_tick,
                        "released_tick_ms": rel_tick,
                    },
                    num_cols=["seq_n", "frame", "tick_ms", "dtsum_ms"],
                    row_dicts=rdicts8,
                ),
            )
        ec8 = _emit_op(
            peer,
            "qa_echo",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_num={"witness_attempts_n": 20, "witness_started_tick_ms": w_tick}),
        )
        wr8 = _emit_op(
            peer,
            "job_read",
            wire.empty_payload(),
            "done",
            "",
            wire.pack_payload(scalars_str={"state": "done"}, scalars_num={"start_tick_ms": w_tick, "page_n": 0, "pages_n": 0, "rows_total_n": 0}),
        )
        scen_rows.append(
            {
                "a_read_op_ids": [ar8],
                "check": "BASE-08",
                "cut_start_ms": cut_s,
                "echo_op_id": ec8,
                "peer": peer,
                "start_op_id": st8,
                "t_ms": _t(),
                "witness_read_op_id": wr8,
            }
        )

    # BASE-11
    st11 = _emit_op("server", "qa_effect_start", wire.empty_payload(), "done", "", wire.empty_payload())
    cut11_s = _t(10.0)
    bridge_rows.append({"ev": "cut_start", "peer": "server", "t_ms": cut11_s})
    cut11_e = _t(6000.0)
    bridge_rows.append({"ev": "cut_end", "peer": "server", "t_ms": cut11_e})
    rec11_t = _t(50.0)
    bridge_rows.append(
        {
            "body_len": 25,
            "ev": "poll",
            "frame": 800,
            "held_ms": 0.0,
            "http": 200,
            "inst": "srv-inst-1",
            "n_ops": 0,
            "now_ms": rec11_t,
            "op_ids": [],
            "peer": "server",
            "t_ms": rec11_t,
            "tick_s": round(rec11_t / 1000.0, 3),
        }
    )
    eff_state11 = "running" if fail_check == "BASE-11" else "failed"
    er11 = _emit_op(
        "server",
        "job_read",
        wire.empty_payload(),
        "done",
        "",
        wire.pack_payload(
            scalars_str={"state": eff_state11, "reason": "lease_expired"},
            scalars_num={
                "page_n": 0,
                "pages_n": 1,
                "rows_total_n": 3,
                "start_tick_ms": cut11_s,
                "end_tick_ms": cut11_s + 3100.0,
                "onjobend_tick_ms": cut11_s + 3100.0,
                "released_tick_ms": cut11_s + 3100.0,
            },
            num_cols=["token_n", "tick_ms", "lease_age_ms"],
            str_cols=["outcome"],
            row_dicts=[
                {"token_n": 6000, "tick_ms": cut11_s + 300.0, "lease_age_ms": 300.0, "outcome": "sent"},
                {"token_n": 6001, "tick_ms": cut11_s + 600.0, "lease_age_ms": 600.0, "outcome": "sent"},
                {"token_n": 6002, "tick_ms": cut11_s + 3100.0, "lease_age_ms": 3100.0, "outcome": "blocked_lease"},
            ],
        ),
    )
    ec11 = _emit_op(
        "server",
        "qa_echo",
        wire.empty_payload(),
        "done",
        "",
        wire.pack_payload(scalars_num={"witness_started_tick_ms": cut11_s + 3116.0}),
    )
    wr11 = _emit_op(
        "server",
        "job_read",
        wire.empty_payload(),
        "done",
        "",
        wire.pack_payload(scalars_str={"state": "done"}, scalars_num={"start_tick_ms": cut11_s + 3116.0, "page_n": 0, "pages_n": 0, "rows_total_n": 0}),
    )
    pp11 = _emit_op(
        "client",
        "qa_ping_page",
        wire.empty_payload(),
        "done",
        "",
        wire.pack_payload(
            scalars_num={"page_n": 0, "pages_n": 1, "rows_total_n": 2},
            num_cols=["token_n", "recv_ms", "idx_n"],
            row_dicts=[
                {"token_n": 6000, "recv_ms": cut11_s + 305.0, "idx_n": 0},
                {"token_n": 6001, "recv_ms": cut11_s + 605.0, "idx_n": 1},
            ],
        ),
    )
    scen_rows.append(
        {
            "check": "BASE-11",
            "cut_start_ms": cut11_s,
            "echo_op_id": ec11,
            "eff_read_op_ids": [er11],
            "ping_page_op_ids": [pp11],
            "start_op_id": st11,
            "t_ms": _t(),
            "token0_n": 6000,
            "witness_read_op_id": wr11,
        }
    )

    # BASE-13
    for peer in ("server", "client"):
        inst = "srv-inst-1" if peer == "server" else "cli-inst-1"
        hc_ms = _t(10.0)
        bridge_rows.append(
            {
                "args": {"build": build, "inst": inst, "peer": peer, "probe_ver": f"dsbx-qa1+{probe_stamp}", "proto": "qa0"},
                "ev": "hello",
                "http": 200,
                "inst": inst,
                "ok": False,
                "peer": peer,
                "t_ms": _t(5.0),
            }
        )
        bridge_rows.append(
            {
                "args": {"build": build, "inst": inst, "peer": peer, "probe_ver": f"dsbx-qa1+{probe_stamp}", "proto": "qa0"},
                "ev": "hello",
                "http": 200,
                "inst": inst,
                "ok": True,
                "peer": peer,
                "t_ms": _t(250.0),
            }
        )
        ack_id = _next_id()
        bridge_rows.append({"body_len": 120, "ev": "ack_reject", "http": 200, "ok": False, "op_id": ack_id, "peer": peer, "t_ms": _t(5.0)})
        _emit_op(peer, "qa_echo", wire.empty_payload(), "done", "", wire.empty_payload(), op_id=ack_id)
        scen_rows.append({"ack_op_id": ack_id, "check": "BASE-13", "hello_cut_start_ms": hc_ms, "peer": peer, "t_ms": _t()})

    _write_jsonl(samples / "bridge.jsonl", bridge_rows)
    _write_jsonl(samples / "scenario.jsonl", scen_rows)

    gate_core.write_json(
        pdir / "part.json",
        {"op_map": [], "op_nonce": nonce, "part": pdir.name, "spike_id": "F0.3-0"},
    )
    manifest = {
        "argv": ["qa/m1_gate.py", "spike", "F0.3-0"],
        "both": True,
        "build": build,
        "ended_utc": "2026-11-14T22:00:10Z",
        "execution_identity": {
            "fake_peer_pids": {"client": exec_pids[1], "server": exec_pids[0]},
            "key_sha256": {"client": "1111222233334444", "server": "aaaabbbbccccdddd"},
            "peer_insts": {"client": ["cli-inst-1"], "server": ["srv-inst-1"]},
            "port": exec_port,
        },
        "faults": [],
        "harness": {"git_dirty": git_dirty, "git_head": git_head, "platform": "win32", "python": "3.14"},
        "id": "F0.3-0",
        "identity": {
            "build": build,
            "git_dirty": git_dirty,
            "git_head": git_head,
            "params": {
                "hold_ms": 2000,
                "lease_ms": 3000,
                "retry_ms": 2000,
                "seed": 20261026,
                "ttl_ms": 5000,
                "wire_cap": wire_cap,
            },
            "pbo_sha256": pbo_sha256,
            "peer_builds": {"client": build, "server": build},
            "probe_stamp": probe_stamp,
        },
        "kind": "spike",
        "params": {
            "hold_ms": 2000,
            "lease_ms": 3000,
            "port": exec_port,
            "retry_ms": 2000,
            "run_id": "abcd1234",
            "seed": 20261026,
            "ttl_ms": 5000,
        },
        "schema": gate_core.SCHEMA_MANIFEST,
        "started_utc": "2026-11-14T22:00:00Z",
    }
    gate_core.write_json(pdir / "manifest.json", manifest)
    return manifest


def _write_synthetic_probe_budget_part(
    part_dir: Path,
    *,
    git_head: str,
    probe_stamp: str,
    wire_cap: int = 3500,
    build: str = "offline",
    git_dirty: bool = False,
    pbo_sha256: str | None = None,
    leak_request_after: bool = False,
) -> None:
    pdir = Path(part_dir)
    samples = pdir / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(8)
    bridge_rows = []
    for idx_r, (role, inst) in enumerate((("server", "srv-inst-b"), ("client", "cli-inst-b"))):
        bridge_rows.append(
            {
                "args": {"build": build, "inst": inst, "peer": role, "probe_ver": f"dsbx-qa1+{probe_stamp}", "proto": "qa0"},
                "ev": "hello",
                "http": 200,
                "inst": inst,
                "ok": True,
                "peer": role,
                "t_ms": 10.0 + idx_r,
            }
        )
    if leak_request_after:
        bridge_rows.append({"ev": "hello", "http": 503, "inst": "srv-inst-b", "peer": "server", "t_ms": 5000.0})
    _write_jsonl(samples / "bridge.jsonl", bridge_rows)
    _write_jsonl(samples / "scenario.jsonl", [{"check": "BASE-12", "quiet_end_ms": 22000.0, "quiet_start_ms": 1000.0, "t_ms": 22001.0}])
    _write_jsonl(
        samples / "probe_log.jsonl",
        [
            {"budget_n": 30, "created_n": 30, "ev": "probe_log", "line": "[DSBX_QA] callback_budget_exhausted created_n=30 budget_n=30", "peer": "server", "tag": "callback_budget_exhausted"},
            {"budget_n": 30, "created_n": 30, "ev": "probe_log", "line": "[DSBX_QA] callback_budget_exhausted created_n=30 budget_n=30", "peer": "client", "tag": "callback_budget_exhausted"},
        ],
    )
    gate_core.write_json(pdir / "part.json", {"op_map": [], "op_nonce": nonce, "part": pdir.name, "spike_id": "F0.3-0"})
    manifest = {
        "argv": ["qa/m1_gate.py", "spike", "F0.3-0"],
        "both": True,
        "build": build,
        "ended_utc": "2026-11-14T22:01:00Z",
        "execution_identity": {
            "fake_peer_pids": {"client": 2002, "server": 2001},
            "key_sha256": {"client": "5555666677778888", "server": "99990000aaaabbbb"},
            "peer_insts": {"client": ["cli-inst-b"], "server": ["srv-inst-b"]},
            "port": 52000,
        },
        "faults": [],
        "harness": {"git_dirty": git_dirty, "git_head": git_head, "platform": "win32", "python": "3.14"},
        "id": "F0.3-0",
        "identity": {
            "build": build,
            "git_dirty": git_dirty,
            "git_head": git_head,
            "params": {
                "hold_ms": 2000,
                "lease_ms": 3000,
                "retry_ms": 2000,
                "seed": 20261026,
                "ttl_ms": 5000,
                "wire_cap": wire_cap,
            },
            "pbo_sha256": pbo_sha256,
            "peer_builds": {"client": build, "server": build},
            "probe_stamp": probe_stamp,
        },
        "kind": "spike",
        "params": {"hold_ms": 2000, "lease_ms": 3000, "port": 52000, "retry_ms": 2000, "run_id": "ef012345", "seed": 20261026, "ttl_ms": 5000},
        "schema": gate_core.SCHEMA_MANIFEST,
        "started_utc": "2026-11-14T22:00:30Z",
    }
    gate_core.write_json(pdir / "manifest.json", manifest)


# ============================================================================
# GRUPO 1: bridge_qa (antitautologia sobre bridge_qa + §5.4 + §8.1(3) + A4 + F02-H1/H3/H5)
# ============================================================================
class BridgeF03Tests(unittest.TestCase):
    def test_full_args_retains_nine_new_payload_fields(self):
        out = bridge_qa.full_args(
            {
                "ncell": [1.0, 2.0],
                "ncol": ["c"],
                "nk": ["n1"],
                "nv": [3.5],
                "rows": 2,
                "scell": ["a", "b"],
                "scol": ["s"],
                "sk": ["k1"],
                "sv": ["v1"],
            }
        )
        for field in ("sk", "sv", "nk", "nv", "ncol", "ncell", "scol", "scell", "rows"):
            self.assertIn(field, out, f"full_args dropped {field}")
        self.assertEqual(out["sk"], ["k1"])
        self.assertEqual(out["sv"], ["v1"])
        self.assertEqual(out["nk"], ["n1"])
        self.assertEqual(out["nv"], [3.5])
        self.assertEqual(out["rows"], 2)

    def test_bridge_run_id_and_auto_op_id_include_run_id(self):
        rows = []
        b = bridge_qa.QABridge(200, 1000, rows.append)
        # Arrancado: stop() sin start() se colgaba en socketserver.shutdown() (tambien en e3f530e, R2-1).
        b.start()
        try:
            self.assertTrue(hasattr(b, "run_id"), "QABridge missing run_id")
            self.assertRegex(b.run_id, r"^[0-9a-f]{8}$")
            oid = b.enqueue("server", "srv_read", {}, "inst1", 1000)
            self.assertEqual(oid, f"op-{b.run_id}-1")
        finally:
            b.stop()

    def test_deliver_zero_keepalive_leaves_queue_intact(self):
        rows = []
        b = bridge_qa.QABridge(500, 1000, rows.append)
        b.set_peer_key("server", "k-srv")
        b.start()
        try:
            code, _ = _http_call(
                b.port,
                "POST",
                "/hello",
                "k-srv",
                {"build": "offline", "inst": "aa", "peer": "server", "probe_ver": "t", "proto": "qa0"},
            )
            self.assertEqual(code, 200)
            oid = b.enqueue("server", "srv_read", {}, "aa", 5000)
            code, payload = _http_call(
                b.port,
                "GET",
                "/poll",
                "k-srv",
                None,
                "peer=server&inst=aa&frame=1&tick_s=0.1&deliver=0",
            )
            self.assertEqual(code, 200)
            self.assertEqual(payload.get("ops"), [])
            self.assertEqual(len(b.queue), 1)
            self.assertEqual(b.queue[0]["op_id"], oid)
            self.assertTrue(any(r.get("ev") == "keepalive" for r in rows))
            self.assertFalse(any(r.get("ev") == "deliver" for r in rows))
        finally:
            b.stop()

    def test_deliver_zero_enforces_key_inst_and_cut_guards(self):
        rows = []
        b = bridge_qa.QABridge(300, 1000, rows.append)
        b.set_peer_key("server", "k-srv")
        b.start()
        try:
            c_auth, _ = _http_call(b.port, "GET", "/poll", "wrong", None, "peer=server&inst=aa&deliver=0")
            self.assertEqual(c_auth, 401)
            c_inst, _ = _http_call(b.port, "GET", "/poll", "k-srv", None, "peer=server&inst=aa&deliver=0")
            self.assertEqual(c_inst, 409)
            _http_call(
                b.port,
                "POST",
                "/hello",
                "k-srv",
                {"build": "offline", "inst": "aa", "peer": "server", "probe_ver": "t", "proto": "qa0"},
            )
            b.cut("server", 500)
            c_cut, _ = _http_call(b.port, "GET", "/poll", "k-srv", None, "peer=server&inst=aa&deliver=0")
            self.assertEqual(c_cut, 503)
        finally:
            b.stop()

    def test_enqueue_wire_cap_strip_qa_fault_real_lengths_and_overflow_guard(self):
        self.assertIsNotNone(wire, "wire.py missing in pre-F0.3 tree")
        self.assertIsNotNone(f03_common, "f03_common.py missing in pre-F0.3 tree")
        rows = []
        tm_rows = []
        b = bridge_qa.QABridge(200, 3000, rows.append, test_mode_sink=tm_rows.append)
        b.set_peer_key("server", "k-srv")
        b.start()
        try:
            _http_call(
                b.port,
                "POST",
                "/hello",
                "k-srv",
                {"build": "offline", "inst": "S1", "peer": "server", "probe_ver": "t", "proto": "qa0"},
            )
            huge = wire.pack_payload(scalars_str={"big": "z" * (wire.WIRE_CAP + 50)})
            with self.assertRaises(ValueError):
                b.enqueue("server", "qa_echo", huge, "S1", 5000)
            self.assertFalse(any(r.get("ev") == "enq" for r in rows))

            # Igualdad exacta de poll.body_len entre sano (24 "_") y mutante ("freeze_on_wait" rellenado a 24)
            # ExitStack dentro del mismo with: cierra los contextos ANTES de borrar el directorio (Windows, R2-4).
            with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as closers:
                ctx1 = f03_common.PartContext.from_bridge(b, Path(tmp) / "p1")
                closers.callback(ctx1.close)
                ctx2 = f03_common.PartContext.from_bridge(b, Path(tmp) / "p2")
                closers.callback(ctx2.close)
                ctx2.op_nonce = ctx1.op_nonce

                def _serve_once():
                    time.sleep(0.03)
                    sc, pl = _http_call(b.port, "GET", "/poll", "k-srv", None, "peer=server&inst=S1&frame=1&tick_s=1.0")
                    if sc == 200 and pl.get("ops"):
                        op = pl["ops"][0]
                        _http_call(
                            b.port,
                            "POST",
                            "/result",
                            "k-srv",
                            {
                                "done_ms": 10.0,
                                "dup": False,
                                "frame_done": 2,
                                "frame_recv": 1,
                                "op_id": op["op_id"],
                                "read": _make_read_payload(wire.empty_payload()),
                                "reason": "",
                                "recv_ms": 5.0,
                                "status": "done",
                            },
                            "peer=server&inst=S1",
                        )

                with mock.patch.object(b, "now_ms", return_value=1234.567):
                    t1 = threading.Thread(target=_serve_once)
                    t1.start()
                    o1 = f03_common.issue_one(ctx1, "server", "qa_timer_start", wire.pack_payload(scalars_num={"duration_ms": 100}), qa_fault=None)
                    t1.join(timeout=3)

                    t2 = threading.Thread(target=_serve_once)
                    t2.start()
                    o2 = f03_common.issue_one(
                        ctx2,
                        "server",
                        "qa_timer_start",
                        wire.pack_payload(scalars_num={"duration_ms": 100}),
                        qa_fault="freeze_on_wait",
                    )
                    t2.join(timeout=3)

                self.assertEqual(o1.status, "done")
                self.assertEqual(o2.status, "done")
                blob = json.dumps(rows)
                self.assertNotIn("qa_fault", blob)
                self.assertNotIn("freeze_on_wait", blob)
                p_ev1 = next(r for r in rows if r.get("ev") == "poll" and o1.op_id in (r.get("op_ids") or []))
                p_ev2 = next(r for r in rows if r.get("ev") == "poll" and o2.op_id in (r.get("op_ids") or []))
                self.assertEqual(p_ev1["body_len"], p_ev2["body_len"])
                self.assertEqual(p_ev1["now_ms"], 1234.567)
                r_ev1 = next(r for r in rows if r.get("ev") == "result" and r.get("op_id") == o1.op_id)
                self.assertGreater(r_ev1["body_len"], 50)

            # Guarda definitiva R2-N8: orden dimensionada a WIRE_CAP en 99999999.999 servida en 100000000.001 -> WIRE_CAP + 1
            pad_len = 0
            cand_id = "0123456789abcdef-99"
            issued_f = 500.0
            while True:
                args_c = wire.pack_payload(scalars_str={"p": "a" * pad_len})
                # Medida como la hace enqueue(): con full_args() (R2-2, el mismo defecto en la prueba).
                w_ord = {"args": bridge_qa.full_args(args_c), "inst": "S1", "issued_ms": issued_f, "op_id": cand_id, "ttl_ms": 500000000, "verb": "qa_echo"}
                ln = len(wire.poll_wire_bytes(w_ord, now_ms=99999999.999))
                if ln == wire.WIRE_CAP:
                    break
                if ln < wire.WIRE_CAP:
                    pad_len += wire.WIRE_CAP - ln
                else:
                    pad_len -= 1
            b.enqueue("server", "qa_echo", args_c, "S1", 500000000, op_id=cand_id, issued_ms=issued_f)
            with mock.patch.object(b, "now_ms", return_value=100000000.001):
                sc_ov, pl_ov = _http_call(b.port, "GET", "/poll", "k-srv", None, "peer=server&inst=S1&frame=5&tick_s=2.0")
            self.assertEqual(sc_ov, 500)
            self.assertEqual(pl_ov.get("error"), "wire_cap_exceeded")
            ov_evs = [r for r in rows if r.get("ev") == "wire_cap_exceeded"]
            self.assertEqual(len(ov_evs), 1)
            self.assertEqual(ov_evs[0]["body_len"], wire.WIRE_CAP + 1)
            # A4: la orden no se pierde de la cola
            self.assertTrue(any(q["op_id"] == cand_id for q in b.queue))
        finally:
            b.stop()

    def test_a4_batching_delivers_all_16_srv_read_within_wire_cap(self):
        cap = wire.WIRE_CAP if wire is not None else 3500
        rows = []
        b = bridge_qa.QABridge(100, 3000, rows.append)
        b.set_peer_key("server", "k-srv")
        b.set_peer_key("client", "k-cli")
        b.start()
        try:
            _http_call(
                b.port,
                "POST",
                "/hello",
                "k-srv",
                {"build": "offline", "inst": "S1", "peer": "server", "probe_ver": "t", "proto": "qa0"},
            )
            _http_call(
                b.port,
                "POST",
                "/hello",
                "k-cli",
                {"build": "offline", "inst": "C1", "peer": "client", "probe_ver": "t", "proto": "qa0"},
            )
            enqueued_ids = [b.enqueue("server", "srv_read", {}, "S1", 10000) for _ in range(16)]
            delivered_ids = []
            for _ in range(20):
                if len(delivered_ids) >= 16:
                    break
                sc, pl = _http_call(b.port, "GET", "/poll", "k-srv", None, "peer=server&inst=S1&frame=1&tick_s=0.5")
                self.assertEqual(sc, 200)
                raw = json.dumps(pl, separators=(",", ":")).encode("utf-8")
                self.assertLessEqual(len(raw), cap)
                delivered_ids.extend(op["op_id"] for op in pl["ops"])
            self.assertEqual(delivered_ids, enqueued_ids)

            # 16 ordenes medianas cuyo conjunto completo supera 3500 B (~4800 B), pero cada sublote cabe en WIRE_CAP
            med_ids = [
                b.enqueue(
                    "client",
                    "cam_pose_set",
                    {"pos": [100.25, 200.5, 300.75], "ypr": [45.0, 15.0, 0.0]},
                    "C1",
                    10000,
                    op_id=f"a4-{'x' * 200}-{idx}",
                )
                for idx in range(16)
            ]
            med_delivered = []
            for _ in range(10):
                if len(med_delivered) >= 16:
                    break
                sc, pl = _http_call(b.port, "GET", "/poll", "k-cli", None, "peer=client&inst=C1&frame=1&tick_s=0.5")
                self.assertEqual(sc, 200)
                raw = json.dumps(pl, separators=(",", ":")).encode("utf-8")
                self.assertLessEqual(len(raw), cap)
                med_delivered.extend(op["op_id"] for op in pl["ops"])
            self.assertEqual(med_delivered, med_ids)
            poll_evs = [r for r in rows if r.get("ev") == "poll"]
            self.assertTrue(all(r.get("body_len", cap + 1) <= cap for r in poll_evs))
        finally:
            b.stop()


# ============================================================================
# GRUPO 2: m1_gate y gate_core (antitautologia sobre m1_gate + §5.1 + §13 A1)
# ============================================================================
class GateF03Tests(unittest.TestCase):
    def test_f03_spike_registered_and_pbo_flag_enforced(self):
        self.assertTrue(hasattr(gate_core, "SPIKE_REGISTRY"), "SPIKE_REGISTRY missing in gate_core")
        self.assertIn("F0.3-0", gate_core.SPIKES)
        self.assertIn("F0.3-0", gate_core.IMPLEMENTED_SPIKES)
        parser = m1_gate.build_parser()
        with tempfile.TemporaryDirectory() as tmp:
            srv = Path(tmp) / "srv"
            cli = Path(tmp) / "cli"
            pbo = Path(tmp) / "probe.pbo"
            ev = Path(tmp) / "ev"
            srv.mkdir()
            cli.mkdir()
            pbo.write_bytes(b"sealed-pbo")

            rc_no_pbo = m1_gate.main(
                [
                    "spike",
                    "F0.3-0",
                    "--build",
                    "retail",
                    "--evidence",
                    str(ev),
                    "--server-profile",
                    str(srv),
                    "--client-profile",
                    str(cli),
                ]
            )
            self.assertEqual(rc_no_pbo, 2)
            self.assertFalse(ev.exists())

            parsed = parser.parse_args(
                [
                    "spike",
                    "F0.3-0",
                    "--build",
                    "retail",
                    "--evidence",
                    str(ev),
                    "--server-profile",
                    str(srv),
                    "--client-profile",
                    str(cli),
                    "--pbo",
                    str(pbo),
                    "--part",
                    "run",
                ]
            )
            m1_gate.validate(parser, parsed)
            self.assertEqual(parsed.part, "run")

    def test_git_harness_excludes_evidence_dir_a1(self):
        def _eval_harness(repo_root: Path):
            sig = inspect.signature(gate_core.git_harness)
            if "repo_root" in sig.parameters:
                return gate_core.git_harness(repo_root=repo_root)
            # e3f530e: git_harness() sin argumentos corre git en el cwd; se ejecuta dentro del repo temporal para que
            # la prueba llegue a su asercion de conducta (alli la evidencia ensucia la identidad), R2-6.
            prev_cwd = os.getcwd()
            os.chdir(repo_root / "DayZSandbox_dev")
            try:
                return gate_core.git_harness()
            finally:
                os.chdir(prev_cwd)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_temp_git_repo(root)
            # Simular evidencia escrita por S-puente y por partes de F0.3-0 bajo DayZSandbox_dev/evidence
            ev_s = root / "DayZSandbox_dev" / "evidence" / "m1" / "S-puente" / "diag-1" / "verdict.json"
            ev_f = root / "DayZSandbox_dev" / "evidence" / "m1" / "F0.3-0" / "diag-1" / "run" / "verdict.json"
            gate_core.write_json(ev_s, {"ok": True})
            gate_core.write_json(ev_f, {"ok": True})

            h_clean = _eval_harness(root)
            self.assertIs(h_clean["git_dirty"], False)

            # Un fichero fuera de DayZSandbox_dev/evidence si ensucia la identidad
            (root / "DayZSandbox_dev" / "qa" / "extra.txt").write_bytes(b"dirty\n")
            h_dirty = _eval_harness(root)
            self.assertIs(h_dirty["git_dirty"], True)


# ============================================================================
# GRUPO 3: fake_peer (antitautologia sobre fake_peer + R1-N2 + §13 A2 + §14 F02-H2/H3/H4/H5)
# ============================================================================
class FakePeerF03Tests(unittest.TestCase):
    def test_valid_hello_resp_rejects_missing_ok_v9(self):
        self.assertFalse(fake_peer._valid_hello_resp(200, {"lease_ms": 3000}))
        self.assertFalse(fake_peer._valid_hello_resp(200, {"lease_ms": 3000, "ok": False}))
        self.assertTrue(fake_peer._valid_hello_resp(200, {"lease_ms": 3000, "ok": True}))
        self.assertFalse(fake_peer._valid_result_resp(200, {}))
        self.assertFalse(fake_peer._valid_result_resp(200, {"ok": False}))
        self.assertTrue(fake_peer._valid_result_resp(200, {"ok": True}))

    def test_legacy_f02_verbs_preserve_exact_contract(self):
        self.assertTrue(hasattr(fake_peer, "JobMgr"), "JobMgr missing in fake_peer")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "dsbx_qa.json"
            cfg.write_bytes(b'{"key":"k","retry_ms":200,"url":"http://127.0.0.1:9"}\n')
            srv = fake_peer.Peer(str(cfg), "server", _free_udp_port(), 60.0, None)
            cli = fake_peer.Peer(str(cfg), "client", _free_udp_port(), 60.0, None)
            srv.last_ok = time.monotonic()
            cli.last_ok = time.monotonic()

            legacy_args = {
                "client_inst": cli.inst,
                "count": 0,
                "fog": 0.25,
                "interval_ms": 50,
                "pos": [1.0, 2.0, 3.0],
                "seq0": 10,
                "x": 50.0,
                "ypr": [4.0, 5.0, 6.0],
                "z": 60.0,
            }
            cases = [
                (srv, "srv_read", ["frame", "tick_s"]),
                (srv, "ground_query", ["y"]),
                (srv, "ambient_set", ["fog"]),
                (srv, "ambient_read", ["fog"]),
                (cli, "cam_pose_set", ["pos", "ypr"]),
                (cli, "cam_pose_read", ["pos", "ypr"]),
                (srv, "rpc_burst", []),
                (cli, "rpc_log_read", ["rpc_log"]),
            ]
            for peer_obj, verb, exp_has in cases:
                bucket = []
                op = {
                    "args": dict(legacy_args),
                    "inst": peer_obj.inst,
                    "issued_ms": 0.0,
                    "op_id": f"leg-{verb}",
                    "ttl_ms": 5000,
                    "verb": verb,
                }
                peer_obj._start_op(op, 10.0, time.monotonic(), bucket)
                for _ in range(5):
                    peer_obj.frame += 1
                    peer_obj._apply()
                    peer_obj._finish_jobs()
                    if bucket:
                        break
                self.assertEqual(len(bucket), 1, verb)
                res = bucket[0]
                self.assertEqual(res["status"], "done", verb)
                self.assertEqual(res["reason"], "", verb)
                self.assertEqual(res["read"]["has"], exp_has, verb)
                self.assertNotIn("sk", res["read"], verb)
            srv.shutdown()
            cli.shutdown()

    def test_saturated_peer_fifo_1024_cache_and_512_logs_and_deadman_cleanup(self):
        self.assertIsNotNone(wire, "wire.py missing")
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "dsbx_qa.json"
            cfg.write_bytes(b'{"key":"k","retry_ms":200,"url":"http://127.0.0.1:9"}\n')
            srv = fake_peer.Peer(str(cfg), "server", _free_udp_port(), 60.0, None)
            cli = fake_peer.Peer(str(cfg), "client", _free_udp_port(), 60.0, None)
            srv.last_ok = time.monotonic()
            cli.last_ok = time.monotonic()

            for i in range(1100):
                srv.remember_result(srv.make_synthetic_cached_result(f"c-{i}", float(i), i))
            self.assertEqual(len(srv.cache_order), 1024)
            self.assertEqual(srv.cache_order, [f"c-{i}" for i in range(76, 1100)])

            for i in range(600):
                cli._handle_cam_rpc({"pos": [0, 0, 0], "seq": i + 1, "target_inst": cli.inst, "ypr": [0, 0, 0]})
                cli.exts[8].on_rpc(26102880, {"client_inst": cli.inst, "token_n": i + 1})
                srv._record_emit("op-b", i + 1, float(i), 10.0, "sent")
            self.assertEqual([r["seq"] for r in cli.rpc_log], list(range(89, 601)))
            self.assertEqual([r["token_n"] for r in cli.exts[8].ping_log], list(range(89, 601)))
            self.assertEqual([r["seq_n"] for r in srv.emit_log], list(range(89, 601)))

            # OnJobEnd unico para las 4 causas terminales (done, stopped, failed/rows_cap, expired) y deadman="stop"
            end_events = []

            class _ProbeExt(fake_peer.FakeExt):
                def on_job_end(self, job_id, state, reason):
                    end_events.append((job_id, state, reason))

            pext = _ProbeExt()
            pext.init(srv, srv.job_mgr)
            self.assertEqual(srv.job_mgr.start_job(pext, "bad-dm", "r1", [], [], 20, 10, 5000.0, "invalid"), "bad_deadman")

            self.assertEqual(srv.job_mgr.start_job(pext, "j-done", "r1", ["v"], [], 20, 10, 5000.0, "continue"), "")
            self.assertTrue(srv.job_mgr.end_job("j-done", "done", ""))
            self.assertFalse(srv.job_mgr.end_job("j-done", "stopped", ""))

            self.assertEqual(srv.job_mgr.start_job(pext, "j-stop", "r1", ["v"], [], 20, 10, 5000.0, "continue"), "")
            self.assertTrue(srv.job_mgr.end_job("j-stop", "stopped", ""))

            self.assertEqual(srv.job_mgr.start_job(pext, "j-cap", "r1", ["v"], [], 20, 2, 5000.0, "continue"), "")
            self.assertTrue(srv.job_mgr.append_row("j-cap", [1.0], []))
            self.assertTrue(srv.job_mgr.append_row("j-cap", [2.0], []))
            self.assertFalse(srv.job_mgr.append_row("j-cap", [3.0], []))

            self.assertEqual(srv.job_mgr.start_job(pext, "j-exp", "r1", ["v"], [], 20, 10, 100.0, "continue"), "")
            srv.job_mgr.tick_jobs(0.05, srv.local_ms() + 250.0)

            # Trabajo de efectos (deadman="stop") que pierde el lease cesa y limpia una vez antes de reconectar (V2)
            srv.hello_ok = False
            srv.last_ok = time.monotonic() - 10.0
            self.assertEqual(srv.job_mgr.start_job(pext, "j-dm", "r_eff", ["v"], [], 20, 10, 5000.0, "stop"), "")
            srv.job_mgr.tick_jobs(0.016, srv.local_ms())
            self.assertNotIn("r_eff", srv.job_mgr.held_resources)

            self.assertEqual(
                end_events,
                [
                    ("j-done", "done", ""),
                    ("j-stop", "stopped", ""),
                    ("j-cap", "failed", "rows_cap"),
                    ("j-exp", "expired", "job_timeout"),
                    ("j-dm", "failed", "lease_expired"),
                ],
            )
            srv.shutdown()
            cli.shutdown()

    def test_a2_single_clock_read_on_witness_and_base08_mutants(self):
        self.assertIsNotNone(wire, "wire.py missing")
        # Reloj falso que avanza en CADA llamada (+1.0 ms por lectura)
        ticks = [1000.0]

        def _advancing_clock():
            ticks[0] += 1.0
            return ticks[0]

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "dsbx_qa.json"
            cfg.write_bytes(b'{"key":"k","retry_ms":200,"url":"http://127.0.0.1:9"}\n')
            srv = fake_peer.Peer(str(cfg), "server", _free_udp_port(), 60.0, None, clock_ms_fn=_advancing_clock)
            srv.hello_ok = False
            base_ext = srv.exts[8]

            # Sano: A expira durante desconexion y B arranca con UNA sola lectura del reloj
            op_a = {
                "args": wire.pack_payload(scalars_num={"duration_ms": 8000, "max_duration_ms": 200, "sample_step_ms": 50, "witness_b": 1}),
                "inst": srv.inst,
                "issued_ms": 0.0,
                "op_id": "jobA",
                "ttl_ms": 5000,
                "verb": "qa_timer_start",
            }
            bucket = []
            srv._start_op(op_a, 10.0, time.monotonic(), bucket)
            # El reloj falso avanza por LECTURA, no por frame: se avanza hasta que A sea terminal y B haya arrancado.
            for _ in range(5000):
                srv.frame += 1
                srv._step_extensions_and_jobs(0.02)
                if srv.job_mgr.get_state("jobA") != "running" and "jobA:witness" in srv.job_mgr.jobs_by_id:
                    break
            reconnect_ms = _advancing_clock()
            self.assertIn("jobA:witness", srv.job_mgr.jobs_by_id, "el testigo B no arranco tras expirar A")
            job_a = srv.job_mgr.jobs_by_id["jobA"]
            job_b = srv.job_mgr.jobs_by_id["jobA:witness"]
            self.assertEqual(job_a["state"], "expired")
            self.assertEqual(base_ext.witness_started_tick_ms, job_b["start_tick_ms"])
            self.assertLess(job_a["start_tick_ms"], job_a["end_tick_ms"])
            self.assertLessEqual(job_a["end_tick_ms"], job_a["onjobend_tick_ms"])
            self.assertLessEqual(job_a["onjobend_tick_ms"], job_a["released_tick_ms"])
            self.assertLessEqual(job_a["released_tick_ms"], base_ext.witness_started_tick_ms)
            self.assertLess(base_ext.witness_started_tick_ms, reconnect_ms)
            srv.job_mgr.end_job("jobA:witness", "stopped", "")

            # mut-defer_cleanup: A expira pero OnJobEnd y liberacion se aplazan hasta reconectar
            op_def = {
                "args": wire.pack_payload(
                    scalars_str={"qa_fault": wire.format_qa_fault("defer_cleanup")},
                    scalars_num={"duration_ms": 8000, "max_duration_ms": 200, "sample_step_ms": 50, "witness_b": 1},
                ),
                "inst": srv.inst,
                "issued_ms": 0.0,
                "op_id": "jobDef",
                "ttl_ms": 5000,
                "verb": "qa_timer_start",
            }
            srv._start_op(op_def, 10.0, time.monotonic(), [])
            # Hasta que A expire de verdad (si no, onjobend_tick_ms == 0.0 se cumpliria sin probar nada) y unos
            # frames mas en los que el testigo podria arrancar si la limpieza no se aplazara.
            for _ in range(5000):
                srv.frame += 1
                srv._step_extensions_and_jobs(0.02)
                if srv.job_mgr.get_state("jobDef") != "running":
                    break
            self.assertEqual(srv.job_mgr.get_state("jobDef"), "expired")
            for _ in range(20):
                srv.frame += 1
                srv._step_extensions_and_jobs(0.02)
            self.assertEqual(srv.job_mgr.jobs_by_id["jobDef"]["onjobend_tick_ms"], 0.0)
            self.assertNotIn("jobDef:witness", srv.job_mgr.jobs_by_id)
            rec_def_ms = _advancing_clock()
            srv.job_mgr.flush_deferred_cleanup()
            self.assertGreater(srv.job_mgr.jobs_by_id["jobDef"]["released_tick_ms"], rec_def_ms)
            srv.shutdown()

    def test_fake_peer_keepalive_no_double_poll_no_ka_with_pending_result_and_12s_burst(self):
        rows = []
        b = bridge_qa.QABridge(400, 3000, rows.append)
        b.set_peer_key("server", "k-srv")
        b.set_peer_key("client", "k-cli")
        b.start()
        procs = []
        with tempfile.TemporaryDirectory() as tmp:
            rpc_port = _free_udp_port()
            for role, key in (("server", "k-srv"), ("client", "k-cli")):
                cpath = Path(tmp) / f"{role}.json"
                cpath.write_bytes(json.dumps({"callback_budget": 2000, "key": key, "retry_ms": 150, "url": f"http://127.0.0.1:{b.port}"}).encode("utf-8"))
                p = subprocess.Popen(
                    [sys.executable, str(QA_DIR / "fake_peer.py"), "--peer", role, "--config", str(cpath), "--rpc-port", str(rpc_port)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                procs.append(p)
            try:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and (b.registered("server") is None or b.registered("client") is None):
                    time.sleep(0.05)
                self.assertIsNotNone(b.registered("server"))
                self.assertIsNotNone(b.registered("client"))

                # Retardar deliver=0 y comprobar que nunca hay 2 polls en vuelo para el servidor
                inflight_srv = 0
                max_inflight_srv = 0
                lock = threading.Lock()
                orig_poll = b._poll

                def _wrapped_poll(handler, query):
                    nonlocal inflight_srv, max_inflight_srv
                    is_srv = query.get("peer") == "server"
                    if is_srv:
                        with lock:
                            inflight_srv += 1
                            max_inflight_srv = max(max_inflight_srv, inflight_srv)
                    try:
                        if is_srv and query.get("deliver") == "0":
                            time.sleep(0.18)
                        return orig_poll(handler, query)
                    finally:
                        if is_srv:
                            with lock:
                                inflight_srv -= 1

                b._poll = _wrapped_poll
                # Rafaga de 12 s (40 * 300 ms) con lease_ms=3000: no se cancela gracias a deliver=0
                burst_id = b.enqueue(
                    "server",
                    "rpc_burst",
                    {"client_inst": b.registered("client"), "count": 40, "interval_ms": 300, "pos": [1, 2, 3], "seq0": 100, "ypr": [0, 0, 0]},
                    b.registered("server"),
                    20000,
                )
                res = b.wait_result(burst_id, 0.0, 18000)
                self.assertIsNotNone(res, "12s rpc_burst failed or cancelled")
                self.assertEqual(res["status"], "done")
                self.assertEqual(max_inflight_srv, 1)
                self.assertGreaterEqual(sum(1 for r in rows if r.get("ev") == "keepalive" and r.get("peer") == "server"), 5)

                # Con resultado terminado pendiente (P6 reintentando), no sale ningun keepalive deliver=0
                b.ack_ok_false = 2
                ka_before = sum(1 for r in rows if r.get("ev") == "keepalive" and r.get("peer") == "server")
                op2 = b.enqueue("server", "srv_read", {}, b.registered("server"), 5000)
                res2 = b.wait_result(op2, 0.0, 5000)
                self.assertIsNotNone(res2)
                first_ack_rej_t = next(r["t_ms"] for r in rows if r.get("ev") == "ack_reject" and r.get("op_id") == op2)
                final_res_t = next(r["t_ms"] for r in rows if r.get("ev") == "result" and r.get("op_id") == op2)
                ka_during_p6 = [
                    r
                    for r in rows
                    if r.get("ev") == "keepalive"
                    and r.get("peer") == "server"
                    and first_ack_rej_t <= r["t_ms"] <= final_res_t
                ]
                self.assertEqual(ka_during_p6, [])
                del ka_before
            finally:
                for p in procs:
                    p.terminate()
                for p in procs:
                    p.wait(timeout=5)
                b.stop()

    def test_callback_budget_exhaustion_and_hello_without_ok_http(self):
        rows = []
        b = bridge_qa.QABridge(200, 3000, rows.append)
        b.set_peer_key("server", "k-srv")
        b.start()
        with tempfile.TemporaryDirectory() as tmp:
            # 1) Servidor HTTP que devuelve 200 {"lease_ms":3000} sin "ok": fake_peer debe rechazarlo y no pedir /poll
            srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv_sock.bind(("127.0.0.1", 0))
            srv_sock.listen(5)
            bad_port = srv_sock.getsockname()[1]
            seen_paths = []
            stop_bad = threading.Event()

            def _bad_srv():
                srv_sock.settimeout(0.1)
                while not stop_bad.is_set():
                    try:
                        conn, _ = srv_sock.accept()
                    except OSError:
                        continue
                    try:
                        req = conn.recv(4096).decode("utf-8", errors="replace")
                        first = req.splitlines()[0] if req else ""
                        seen_paths.append(first)
                        body_bytes = b'{"lease_ms":3000}'
                        conn.sendall(
                            b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                            + str(len(body_bytes)).encode("ascii")
                            + b"\r\n\r\n"
                            + body_bytes
                        )
                    finally:
                        conn.close()

            th = threading.Thread(target=_bad_srv, daemon=True)
            th.start()
            cfg_no_ok = Path(tmp) / "no_ok.json"
            log_no_ok = Path(tmp) / "no_ok.log"
            cfg_no_ok.write_bytes(json.dumps({"callback_budget": 4, "key": "k-srv", "retry_ms": 80, "url": f"http://127.0.0.1:{bad_port}"}).encode("utf-8"))
            log_fh = log_no_ok.open("w", encoding="utf-8", newline="\n")
            p1 = subprocess.Popen(
                [sys.executable, str(QA_DIR / "fake_peer.py"), "--peer", "server", "--config", str(cfg_no_ok), "--rpc-port", str(_free_udp_port())],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 4.0
                while time.monotonic() < deadline:
                    if log_no_ok.is_file() and "callback_budget_exhausted" in log_no_ok.read_text(encoding="utf-8"):
                        break
                    time.sleep(0.05)
                time.sleep(0.3)
                self.assertFalse(any("/poll" in line for line in seen_paths), f"unexpected /poll after missing ok: {seen_paths}")
                lines = [ln for ln in log_no_ok.read_text(encoding="utf-8").splitlines() if "callback_budget_exhausted" in ln]
                self.assertEqual(len(lines), 1)
                self.assertIn("created_n=4 budget_n=4", lines[0])
                count_after = len(seen_paths)
                time.sleep(0.35)
                self.assertEqual(len(seen_paths), count_after)
            finally:
                p1.terminate()
                p1.wait(timeout=5)
                log_fh.close()
                stop_bad.set()
                srv_sock.close()
                b.stop()


# ============================================================================
# GRUPO 4: wire.py, stamp_probe.py y sello historico en git_head
# ============================================================================
class WireAndStampF03Tests(unittest.TestCase):
    def _require_f03(self):
        self.assertIsNotNone(wire, "wire.py missing in pre-F0.3 tree")
        self.assertIsNotNone(stamp_probe, "stamp_probe.py missing in pre-F0.3 tree")
        self.assertIsNotNone(f03_common, "f03_common.py missing in pre-F0.3 tree")

    def test_wire_roundtrip_validation_and_qa_fault_format(self):
        self._require_f03()
        self.assertEqual(wire.format_qa_fault(None), "_" * 24)
        self.assertEqual(wire.format_qa_fault(""), "_" * 24)
        fw = wire.format_qa_fault("freeze_on_wait")
        self.assertEqual(len(fw), 24)
        self.assertEqual(wire.parse_qa_fault(fw), "freeze_on_wait")
        self.assertEqual(wire.parse_qa_fault("_" * 24), "")
        for bad_f in ("trailing_", "a" * 25, "bad space", "ñ"):
            with self.assertRaises(ValueError):
                wire.format_qa_fault(bad_f)
        for bad_raw in ("short", "_" * 23, "a" * 25):
            with self.assertRaises(ValueError):
                wire.parse_qa_fault(bad_raw)

        packed = wire.pack_payload(
            scalars_str={"empty_s": "", "k": "val"},
            scalars_num={"zero_n": 0.0, "pi": 3.25},
            num_cols=["a_n", "b_n"],
            str_cols=["tag"],
            row_dicts=[{"a_n": 1, "b_n": 2.5, "tag": ""}, {"a_n": 0, "b_n": -4.0, "tag": "ok"}],
        )
        self.assertEqual(packed["rows"], 2)
        unpacked = wire.unpack_payload(packed)
        self.assertIn("empty_s", unpacked["str"])
        self.assertEqual(unpacked["str"]["empty_s"], "")
        self.assertNotIn("missing_s", unpacked["str"])
        self.assertIn("zero_n", unpacked["num"])
        self.assertEqual(unpacked["num"]["zero_n"], 0.0)
        self.assertNotIn("missing_n", unpacked["num"])
        self.assertEqual(len(unpacked["rows"]), 2)
        self.assertEqual(unpacked["rows"][1]["tag"], "ok")

        # Rechazos de validacion
        bad_payloads = [
            dict(wire.empty_payload(), sk=["a", "a"], sv=["1", "2"]),
            dict(wire.empty_payload(), nk=["a", "a"], nv=[1.0, 2.0]),
            dict(wire.empty_payload(), sk=["dup"], sv=["1"], nk=["dup"], nv=[1.0]),
            dict(wire.empty_payload(), ncol=["c", "c"], ncell=[1.0, 2.0], rows=1),
            dict(wire.empty_payload(), scol=["c", "c"], scell=["a", "b"], rows=1),
            dict(wire.empty_payload(), ncol=["c"], ncell=[1.0], scol=["c"], scell=["a"], rows=1),
            dict(wire.empty_payload(), sk=["a"], sv=[]),
            dict(wire.empty_payload(), ncol=["c"], ncell=[1.0, 2.0], rows=1),
            dict(wire.empty_payload(), nk=["x"], nv=[float("nan")]),
            dict(wire.empty_payload(), nk=["x"], nv=[float("inf")]),
        ]
        for bp in bad_payloads:
            with self.assertRaises(ValueError):
                wire.validate_payload(bp)

    def test_stamp_probe_and_historical_git_head_stamp(self):
        self._require_f03()
        self.assertTrue(callable(wire.compute_probe_stamp_from_pairs))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head1 = _init_temp_git_repo(root, extra_probe_text="// commit 1\n")
            src_probe = root / "DayZSandbox_dev" / "qa" / "probe" / "DayZSandbox_QA"
            stage_dst = root / "stage" / "DayZSandbox_QA"

            stamp1 = f03_common.compute_probe_stamp_at_commit(head1, repo_root=root)
            self.assertRegex(stamp1, r"^[0-9a-f]{16}$")

            proc = subprocess.run(
                [sys.executable, str(QA_DIR / "stamp_probe.py"), "--src", str(src_probe), "--dst", str(stage_dst)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
            self.assertEqual(proc.stdout.strip(), stamp1)
            self.assertIn('"unstamped"', (src_probe / "scripts" / "5_Mission" / "DSBX_QA_Stamp.c").read_text(encoding="utf-8"))
            self.assertIn(f'"{stamp1}"', (stage_dst / "scripts" / "5_Mission" / "DSBX_QA_Stamp.c").read_text(encoding="utf-8"))

            # Cambiar DSBX_QA_Stamp.c en un commit nuevo no cambia el sello; cambiar otra fuente si, pero head1 conserva stamp1
            (src_probe / "scripts" / "5_Mission" / "DSBX_QA_Stamp.c").write_bytes(b'const string DSBX_QA_STAMP = "0123456789abcdef";\n')
            _git_run(root, "add", ".")
            _git_run(root, "commit", "-m", "stamp-only")
            head_stamp_only = _git_run(root, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(f03_common.compute_probe_stamp_at_commit(head_stamp_only, repo_root=root), stamp1)

            (src_probe / "scripts" / "5_Mission" / "DSBX_QA_Probe.c").write_bytes(b"class DSBX_QA_Probe { int x; }\n")
            _git_run(root, "add", ".")
            _git_run(root, "commit", "-m", "probe-v2")
            head2 = _git_run(root, "rev-parse", "HEAD").stdout.strip()
            stamp2 = f03_common.compute_probe_stamp_at_commit(head2, repo_root=root)
            self.assertNotEqual(stamp1, stamp2)
            # Modificacion sin confirmar en el arbol de trabajo tampoco altera compute_probe_stamp_at_commit(head1)
            (src_probe / "scripts" / "5_Mission" / "DSBX_QA_Probe.c").write_bytes(b"dirty working tree\n")
            self.assertEqual(f03_common.compute_probe_stamp_at_commit(head1, repo_root=root), stamp1)

            with self.assertRaises(f03_common.StampSourceUnavailableError):
                f03_common.compute_probe_stamp_at_commit("deadbeef" * 5, repo_root=root)


# ============================================================================
# GRUPO 5: f03_common, f03_base_eval, aggregate_spike, A3, F02-H2/H4, check_12 e invariancia
# ============================================================================
class CommonAndEvalF03Tests(unittest.TestCase):
    def _require_f03(self):
        self.assertIsNotNone(wire, "wire.py missing in pre-F0.3 tree")
        self.assertIsNotNone(f03_common, "f03_common.py missing in pre-F0.3 tree")
        self.assertIsNotNone(f03_base_eval, "f03_base_eval.py missing in pre-F0.3 tree")
        self.assertIsNotNone(f03_base_mutants, "f03_base_mutants.py missing in pre-F0.3 tree")

    def test_opaque_op_ids_across_two_bridges_slot_lock_after_timeout_and_lost_recovery(self):
        self._require_f03()
        # ExitStack dentro del mismo with: cierra los contextos ANTES de borrar el directorio (Windows, R2-4).
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as closers:
            tpath = Path(tmp)
            rpc_port = _free_udp_port()
            cfg_path = tpath / "srv_cfg.json"
            log_path = tpath / "srv.log"

            b1_rows = []
            b1 = bridge_qa.QABridge(300, 3000, b1_rows.append)
            b1.set_peer_key("server", "k1")
            b1.start()
            cfg_path.write_bytes(json.dumps({"callback_budget": 2000, "key": "k1", "retry_ms": 120, "url": f"http://127.0.0.1:{b1.port}"}).encode("utf-8"))
            peer_proc = subprocess.Popen(
                [sys.executable, str(QA_DIR / "fake_peer.py"), "--peer", "server", "--config", str(cfg_path), "--rpc-port", str(rpc_port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline and b1.registered("server") is None:
                    time.sleep(0.03)
                self.assertIsNotNone(b1.registered("server"))

                ctx1 = f03_common.PartContext.from_bridge(b1, tpath / "base" / "p1")
                closers.callback(ctx1.close)
                out1 = f03_common.issue_one(ctx1, "server", "qa_echo", wire.pack_payload(scalars_num={"x_n": 1}))
                self.assertEqual(out1.status, "done")
                self.assertFalse(out1.dup)
                self.assertRegex(out1.op_id, r"^[0-9a-f]{16}-[1-9][0-9]*$")
                b1.stop()

                # 2.a sesion QABridge contra la MISMA instancia viva de fake_peer.py
                b2_rows = []
                b2 = bridge_qa.QABridge(300, 3000, b2_rows.append)
                b2.set_peer_key("server", "k2")
                b2.start()
                try:
                    cfg_path.write_bytes(json.dumps({"callback_budget": 2000, "key": "k2", "retry_ms": 120, "url": f"http://127.0.0.1:{b2.port}"}).encode("utf-8"))
                    deadline = time.monotonic() + 5.0
                    while time.monotonic() < deadline and b2.registered("server") is None:
                        time.sleep(0.03)
                    self.assertIsNotNone(b2.registered("server"))

                    ctx2 = f03_common.PartContext.from_bridge(b2, tpath / "base" / "p2")
                    closers.callback(ctx2.close)
                    self.assertNotEqual(ctx1.op_nonce, ctx2.op_nonce)
                    out2 = f03_common.issue_one(ctx2, "server", "qa_echo", wire.pack_payload(scalars_num={"x_n": 2}))
                    self.assertEqual(out2.status, "done")
                    self.assertFalse(out2.dup)
                    self.assertNotEqual(out1.op_id, out2.op_id)

                    # read_job_pages rechaza "running" y verifica len(rows) == rows_total_n
                    jt = f03_common.issue_one(ctx2, "server", "qa_timer_start", wire.pack_payload(scalars_num={"duration_ms": 2000, "sample_step_ms": 50}))
                    with self.assertRaises(ValueError):
                        f03_common.read_job_pages(ctx2, "server", jt.op_id)
                    f03_common.issue_one(ctx2, "server", "job_stop", wire.pack_payload({"job": jt.op_id}))
                    paged_ok = f03_common.read_job_pages(ctx2, "server", jt.op_id)
                    self.assertEqual(len(paged_ok["rows"]), paged_ok["rows_total_n"])

                    # R2-N7: orden en vuelo tras timeout bloquea 2.a orden hasta resolverse
                    b2.cut("server", 350)
                    to_out = f03_common.issue_one(ctx2, "server", "qa_echo", None, ttl_ms=3000, timeout_ms=5)
                    self.assertEqual(to_out.status, "timeout")
                    with self.assertRaises(RuntimeError):
                        f03_common.issue_one(ctx2, "server", "qa_echo")
                    slot_ev = ctx2.wait_peer_idle("server", 3000)
                    self.assertEqual(slot_ev, "result")

                    # N3: orden entregada pierde todos sus /result (P6 agotado) -> ev="lost" a ttl+1750+2000, libera turno y admite job_stop
                    next_lost_id = ctx2.peek_next_op_id()
                    b2.drop_results(next_lost_id, True)
                    lost_out = f03_common.issue_one(
                        ctx2,
                        "server",
                        "qa_timer_start",
                        wire.pack_payload(scalars_num={"duration_ms": 9000, "sample_step_ms": 100}),
                        ttl_ms=100,
                        timeout_ms=6500,
                    )
                    self.assertEqual(lost_out.status, "lost")
                    self.assertEqual(lost_out.reason, "result_lost")
                    stop_after_lost = f03_common.issue_one(ctx2, "server", "job_stop", wire.pack_payload({"job": lost_out.op_id}))
                    self.assertEqual(stop_after_lost.status, "done")
                    for pev in (r for r in b2_rows if r.get("ev") == "poll"):
                        self.assertLessEqual(pev["n_ops"], 1)
                        self.assertLessEqual(pev["body_len"], wire.WIRE_CAP)
                finally:
                    b2.stop()
            finally:
                peer_proc.terminate()
                peer_proc.wait(timeout=5)
                b1.stop()

    def test_aggregation_identities_historical_params_a3_mutants_harness_and_invariance(self):
        self._require_f03()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            head1 = _init_temp_git_repo(root, wire_cap=3500)
            stamp1 = f03_common.compute_probe_stamp_at_commit(head1, repo_root=root)

            base = Path(tmp) / "ev_ok"
            _write_synthetic_base_part(base / "run", git_head=head1, probe_stamp=stamp1, exec_port=51001, exec_pids=(101, 102))

            # Renovar execution_identity entre partes (como --part separados en offline, R2-N3)
            mut_map = {
                "ignore_stop": "BASE-03",
                "freeze_on_wait": "BASE-08",
                "defer_cleanup": "BASE-08",
                "ignore_deadman": "BASE-11",
                "skip_send": "BASE-11",
            }
            for idx_m, (mname, fchk) in enumerate(mut_map.items(), start=1):
                mdir = base / f"mut-{mname}"
                _write_synthetic_base_part(
                    mdir,
                    git_head=head1,
                    probe_stamp=stamp1,
                    exec_port=51010 + idx_m,
                    exec_pids=(200 + idx_m, 300 + idx_m),
                    fail_check=fchk,
                )
                gate_core.write_json(
                    mdir / "injection.json",
                    {"applied": True, "kind": "qa_fault", "mutant": mname, "observable_effect": {"check": fchk}, "target": "op", "when_h_ms": 1.0},
                )
                gate_core.write_json(mdir / "verdict.json", f03_base_eval.evaluate(mdir, repo_root=root))

            _write_synthetic_probe_budget_part(base / "probe-budget", git_head=head1, probe_stamp=stamp1)
            gate_core.write_json(base / "probe-budget" / "verdict.json", f03_base_eval.evaluate(base / "probe-budget", repo_root=root))
            gate_core.write_json(base / "run" / "verdict.json", f03_base_eval.evaluate(base / "run", repo_root=root))

            agg_ok = f03_common.aggregate_spike(base, "F0.3-0", repo_root=root)
            self.assertEqual(agg_ok["exit_code"], 0, agg_ok)

            # A3 + N5: avanzar repo con nuevas fuentes de sonda y WIRE_CAP distinto (2800); --evaluate-only conserva 0 PASA
            (root / "DayZSandbox_dev" / "qa" / "probe" / "DayZSandbox_QA" / "scripts" / "5_Mission" / "DSBX_QA_Probe.c").write_bytes(b"class Changed {}\n")
            (root / "DayZSandbox_dev" / "qa" / "wire.py").write_bytes(b"WIRE_CAP = 2800\n")
            _git_run(root, "add", ".")
            _git_run(root, "commit", "-m", "change-probe-and-wire-cap")
            with mock.patch.object(wire, "WIRE_CAP", 2800):
                rc_eval = subprocess.run(
                    [sys.executable, str(QA_DIR / "m1_gate.py"), "spike", "F0.3-0", "--both", "--build", "offline", "--evaluate-only", "--evidence", str(base)],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(rc_eval.returncode, 0, rc_eval.stderr)
                self.assertEqual(f03_base_eval.evaluate(base / "run", repo_root=root)["exit_code"], 0)

            # Negativas de BASE-09: expulsion interior (V5) y traza desordenada
            for kind_9 in ("BASE-09_interior", "BASE-09_order"):
                p9 = Path(tmp) / kind_9
                _write_synthetic_base_part(p9, git_head=head1, probe_stamp=stamp1, fail_check=kind_9)
                v9 = f03_base_eval.evaluate(p9, repo_root=root)
                self.assertEqual(v9["exit_code"], 1)
                c9 = next(c for c in v9["checks"] if c["id"] == "BASE-09")
                self.assertEqual(c9["status"], "fail")

            # Invariancia completa del evaluador (R1-N5, R2-N1, N2)
            orig_run_verdict = f03_base_eval.evaluate(base / "run", repo_root=root)
            inv_dir = Path(tmp) / "mut-freeze_on_wait"
            shutil.copytree(base / "run", inv_dir)
            gate_core.write_json(inv_dir / "injection.json", {"applied": True, "mutant": "freeze_on_wait", "observable_effect": {"x": 1}})
            gate_core.write_json(inv_dir / "part.json", {"op_nonce": "ffffffffffffffff", "part": "mut-freeze_on_wait", "spike_id": "F0.3-0"})
            man_inv = gate_core.read_json(inv_dir / "manifest.json")
            man_inv["faults"] = ["slow", "freeze_on_wait"]
            man_inv["argv"] = ["--fault", "freeze_on_wait", "--part", "mut-freeze_on_wait"]
            gate_core.write_json(inv_dir / "manifest.json", man_inv)

            # Renombrar coherentemente todos los op_id en samples/
            old_nonce = gate_core.read_json(base / "run" / "part.json")["op_nonce"]
            new_nonce = "fedcba9876543210"
            for spath in (inv_dir / "samples" / "bridge.jsonl", inv_dir / "samples" / "scenario.jsonl"):
                txt = spath.read_text(encoding="utf-8").replace(old_nonce, new_nonce)
                spath.write_bytes(txt.encode("utf-8"))
            self.assertEqual(f03_base_eval.evaluate(inv_dir, repo_root=root), orig_run_verdict)

            # Negativas de identidad, build_mismatch, stamp_source_unavailable, artifact_unverified, params_unverified y mutantes
            def _clone_base(name: str) -> Path:
                dst = Path(tmp) / name
                shutil.copytree(base, dst)
                return dst

            # 1) mixed_parts
            b_mix = _clone_base("b_mix")
            m_run = gate_core.read_json(b_mix / "run" / "manifest.json")
            m_run["identity"]["params"]["ttl_ms"] = 9999
            gate_core.write_json(b_mix / "run" / "manifest.json", m_run)
            self.assertEqual(f03_common.aggregate_spike(b_mix, "F0.3-0", repo_root=root)["reasons"], ["mixed_parts"])

            # 2) git_dirty en retail
            b_dirty = _clone_base("b_dirty")
            for sub in b_dirty.iterdir():
                if (sub / "manifest.json").is_file():
                    mm = gate_core.read_json(sub / "manifest.json")
                    mm["build"] = "retail"
                    mm["identity"]["build"] = "retail"
                    mm["identity"]["git_dirty"] = True
                    mm["identity"]["pbo_sha256"] = "aa" * 32
                    mm["identity"]["peer_builds"] = {"client": "retail", "server": "retail"}
                    gate_core.write_json(sub / "manifest.json", mm)
            self.assertEqual(f03_common.aggregate_spike(b_dirty, "F0.3-0", repo_root=root)["reasons"], ["git_dirty"])

            # 3) build_mismatch: hello con build="diag" en corrida retail (N6)
            p_bm = Path(tmp) / "p_bm"
            _write_synthetic_base_part(p_bm, git_head=head1, probe_stamp=stamp1, build="retail", git_dirty=False, pbo_sha256="bb" * 32)
            br_bm = f03_common.read_jsonl(p_bm / "samples" / "bridge.jsonl")
            br_bm[0]["args"]["build"] = "diag"
            _write_jsonl(p_bm / "samples" / "bridge.jsonl", br_bm)
            v_bm = f03_base_eval.evaluate(p_bm, repo_root=root)
            self.assertEqual(v_bm["exit_code"], 2)
            self.assertEqual(v_bm["reasons"], ["build_mismatch"])

            # 4) stamp_source_unavailable (git_head inexistente)
            p_ssu = Path(tmp) / "p_ssu"
            _write_synthetic_base_part(p_ssu, git_head="11111111" * 5, probe_stamp=stamp1)
            self.assertEqual(f03_base_eval.evaluate(p_ssu, repo_root=root)["reasons"], ["stamp_source_unavailable"])

            # 5) artifact_unverified ("dsbx-qa1+unstamped")
            p_au = Path(tmp) / "p_au"
            _write_synthetic_base_part(p_au, git_head=head1, probe_stamp=stamp1)
            br_au = f03_common.read_jsonl(p_au / "samples" / "bridge.jsonl")
            br_au[0]["args"]["probe_ver"] = "dsbx-qa1+unstamped"
            _write_jsonl(p_au / "samples" / "bridge.jsonl", br_au)
            self.assertEqual(f03_base_eval.evaluate(p_au, repo_root=root)["reasons"], ["artifact_unverified"])

            # 6) params_unverified (A3)
            p_pu = Path(tmp) / "p_pu"
            _write_synthetic_base_part(p_pu, git_head=head1, probe_stamp=stamp1, wire_cap=3400)
            self.assertEqual(f03_base_eval.evaluate(p_pu, repo_root=root)["reasons"], ["params_unverified"])

            # 7) mutante en 0 PASA -> 1 FALLA (mutant_not_detected)
            b_mnd = _clone_base("b_mnd")
            shutil.copy2(b_mnd / "run" / "verdict.json", b_mnd / "mut-ignore_stop" / "verdict.json")
            v_mnd = f03_common.aggregate_spike(b_mnd, "F0.3-0", repo_root=root)
            self.assertEqual(v_mnd["exit_code"], 1)
            self.assertEqual(v_mnd["reasons"], ["mutant_not_detected:ignore_stop"])

            # 8) mutante con must_fail_checks en "missing" (R2-N2), sin injection.json, con wrong_check o con result_lost -> 2 INCONCLUSO
            b_miss = _clone_base("b_miss")
            _write_synthetic_base_part(b_miss / "mut-ignore_stop", git_head=head1, probe_stamp=stamp1, missing_check="BASE-03")
            gate_core.write_json(b_miss / "mut-ignore_stop" / "verdict.json", f03_base_eval.evaluate(b_miss / "mut-ignore_stop", repo_root=root))
            v_miss = f03_common.aggregate_spike(b_miss, "F0.3-0", repo_root=root)
            self.assertEqual(v_miss["exit_code"], 2)
            self.assertEqual(v_miss["reasons"], ["mutant_inconclusive:ignore_stop"])

            b_noinj = _clone_base("b_noinj")
            (b_noinj / "mut-ignore_stop" / "injection.json").unlink()
            self.assertEqual(f03_common.aggregate_spike(b_noinj, "F0.3-0", repo_root=root)["reasons"], ["missing_injection_proof:ignore_stop"])

            b_wrong = _clone_base("b_wrong")
            vw = gate_core.read_json(b_wrong / "mut-ignore_stop" / "verdict.json")
            for c in vw["checks"]:
                if c["id"] == "BASE-06":
                    c["status"] = "fail"
            gate_core.write_json(b_wrong / "mut-ignore_stop" / "verdict.json", vw)
            v_wr = f03_common.aggregate_spike(b_wrong, "F0.3-0", repo_root=root)
            self.assertEqual(v_wr["exit_code"], 2)
            self.assertEqual(v_wr["reasons"], ["mutant_wrong_check:ignore_stop:BASE-06"])

            b_lost = _clone_base("b_lost")
            _write_synthetic_base_part(b_lost / "mut-freeze_on_wait", git_head=head1, probe_stamp=stamp1, tech_detail="result_lost")
            gate_core.write_json(b_lost / "mut-freeze_on_wait" / "verdict.json", f03_base_eval.evaluate(b_lost / "mut-freeze_on_wait", repo_root=root))
            self.assertEqual(f03_common.aggregate_spike(b_lost, "F0.3-0", repo_root=root)["reasons"], ["mutant_inconclusive:freeze_on_wait"])

            # 9) F02-H4 probe-budget: si sigue pidiendo tras agotar presupuesto -> 1 FALLA; si run/ se topa sonda agotada -> 2 INCONCLUSO
            b_hfail = _clone_base("b_hfail")
            _write_synthetic_probe_budget_part(b_hfail / "probe-budget", git_head=head1, probe_stamp=stamp1, leak_request_after=True)
            gate_core.write_json(b_hfail / "probe-budget" / "verdict.json", f03_base_eval.evaluate(b_hfail / "probe-budget", repo_root=root))
            v_hf = f03_common.aggregate_spike(b_hfail, "F0.3-0", repo_root=root)
            self.assertEqual(v_hf["exit_code"], 1)
            self.assertEqual(v_hf["reasons"], ["harness_test_failed:probe-budget"])

            b_run_exh = _clone_base("b_run_exh")
            _write_jsonl(
                b_run_exh / "run" / "samples" / "probe_log.jsonl",
                [{"budget_n": 2000, "created_n": 2000, "ev": "probe_log", "line": "[DSBX_QA] callback_budget_exhausted created_n=2000 budget_n=2000", "peer": "server", "tag": "callback_budget_exhausted"}],
            )
            gate_core.write_json(b_run_exh / "run" / "verdict.json", f03_base_eval.evaluate(b_run_exh / "run", repo_root=root))
            v_rexh = f03_common.aggregate_spike(b_run_exh, "F0.3-0", repo_root=root)
            self.assertEqual(v_rexh["exit_code"], 2)

    def test_check_12_evaluators_are_blind_to_mutants_and_faults(self):
        self._require_f03()
        mutant_names = set()
        for mpath in sorted(QA_DIR.glob("*_mutants.py")):
            spec_mod = importlib.import_module(mpath.stem)
            mutant_names.update(getattr(spec_mod, "EXPECTED_MUTANTS", {}).keys())
        forbidden = [
            "qa_fault",
            '"faults"',
            '"mut-"',
            "--fault",
            "injection.json",
            "part.json",
            "EXPECTED_MUTANTS",
            *sorted(mutant_names),
        ]
        violations = []
        for epath in sorted(QA_DIR.glob("*_eval.py")):
            text = epath.read_text(encoding="utf-8")
            for tok in forbidden:
                if tok in text:
                    violations.append(f"{epath.name}: {tok}")
        self.assertEqual(violations, [])


# ============================================================================
# GRUPO 6: S-puente F02-H1 y F02-H3 (dos corridas seguidas, dup=true, N6 frontera, N6.server W3, clock offset)
# ============================================================================
def _write_spuente_defect_case(target: str, defect: str) -> None:
    try:
        write_case(target, defect=defect)
        return
    except ValueError:
        pass
    # Respaldo para arboles pre-F0.3 (e3f530e) donde synth.py aun no define los defectos F02-H1/H3:
    write_case(target)
    bpath = Path(target) / "samples" / "bridge.jsonl"
    rows = [json.loads(ln) for ln in bpath.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if defect == "all_done_dup_true":
        for r in rows:
            if r.get("ev") == "result" and isinstance(r.get("result"), dict) and r["result"].get("status") == "done":
                r["result"]["dup"] = True
    elif defect == "n6_stale_before_boundary":
        cut_ends = [r["t_ms"] for r in rows if r.get("ev") == "cut_end"]
        last_cut = cut_ends[-1] if cut_ends else 50000.0
        for r in reversed(rows):
            if r.get("ev") == "result" and r.get("peer") == "client":
                r["t_ms"] = last_cut - 10.0
                break
    elif defect == "n6_stale_old_seq":
        for r in reversed(rows):
            if r.get("ev") == "result" and r.get("peer") == "client":
                rd = (r.get("result") or {}).get("read") or {}
                if rd.get("rpc_log"):
                    for entry in rd["rpc_log"]:
                        entry["seq"] = 1
                    break
    _write_jsonl(bpath, rows)


class SPuenteF02H1H3Tests(unittest.TestCase):
    def test_spuente_eval_negatives_f02_h1_and_h3_w3(self):
        for defect, exp_code in (
            ("all_done_dup_true", 1),
            ("n6_stale_before_boundary", 1),
            ("n6_stale_old_seq", 1),
            ("n6_srv_foreign_op_id", 1),
            ("n6_srv_empty_own_after_valid_history", 1),
        ):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                _write_spuente_defect_case(tmp, defect)
                v = s_puente_eval.evaluate(tmp)
                self.assertEqual(v["exit_code"], exp_code, f"{defect}: {v}")

    def test_two_spuente_runs_against_same_live_fake_peers_f02_h1(self):
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)
            srv_prof = tpath / "srv_prof"
            cli_prof = tpath / "cli_prof"
            srv_prof.mkdir()
            cli_prof.mkdir()
            rpc_port = _free_udp_port()
            # Precrear dsbx_qa.json inicial (en puerto cerrado hasta que arranque la 1.a corrida)
            for prof in (srv_prof, cli_prof):
                (prof / "dsbx_qa.json").write_bytes(b'{"key":"init","retry_ms":150,"url":"http://127.0.0.1:9"}\n')

            procs = []
            for role, prof in (("server", srv_prof), ("client", cli_prof)):
                p = subprocess.Popen(
                    [
                        sys.executable,
                        str(QA_DIR / "fake_peer.py"),
                        "--peer",
                        role,
                        "--config",
                        str(prof / "dsbx_qa.json"),
                        "--rpc-port",
                        str(rpc_port),
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                procs.append(p)
            try:
                parser = m1_gate.build_parser()
                for run_no in (1, 2):
                    ev_dir = tpath / f"sp_run_{run_no}"
                    ev_dir.mkdir()
                    argv = [
                        "spike",
                        "S-puente",
                        "--both",
                        "--build",
                        "offline",
                        "--evidence",
                        str(ev_dir),
                        "--server-profile",
                        str(srv_prof),
                        "--client-profile",
                        str(cli_prof),
                        "--hold-ms",
                        "300",
                        "--lease-ms",
                        "1200",
                        "--retry-ms",
                        "250",
                        "--ttl-ms",
                        "3000",
                    ]
                    args = parser.parse_args(argv)
                    m1_gate.validate(parser, args)
                    rc = s_puente_run.run(args, ev_dir, argv)
                    verdict = gate_core.read_json(ev_dir / "verdict.json")
                    self.assertEqual(rc, 0, f"run {run_no} failed: {verdict}")
                    self.assertTrue(all(c["status"] == "pass" for c in verdict["checks"]))
                    self.assertTrue(any(c["id"] == "N6.server" and c["status"] == "pass" for c in verdict["checks"]))
            finally:
                for p in procs:
                    p.terminate()
                for p in procs:
                    p.wait(timeout=5)

    def test_spuente_offline_with_clock_offset_f02_h3(self):
        self.assertIn("clock_offset_ms", inspect.signature(fake_peer.Peer.__init__).parameters)
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp) / "sp_offset"
            ev_dir.mkdir()
            parser = m1_gate.build_parser()
            argv = [
                "spike",
                "S-puente",
                "--both",
                "--build",
                "offline",
                "--evidence",
                str(ev_dir),
                "--hold-ms",
                "300",
                "--lease-ms",
                "1200",
                "--retry-ms",
                "250",
                "--ttl-ms",
                "3000",
            ]
            args = parser.parse_args(argv)
            m1_gate.validate(parser, args)
            args.clock_offset_ms = 500000.0
            rc = s_puente_run.run(args, ev_dir, argv)
            verdict = gate_core.read_json(ev_dir / "verdict.json")
            self.assertEqual(rc, 0, f"clock-offset run failed: {verdict}")
            self.assertTrue(all(c["status"] == "pass" for c in verdict["checks"]))
            self.assertTrue(any(c["id"] == "N6.server" and c["status"] == "pass" for c in verdict["checks"]))


if __name__ == "__main__":
    unittest.main()
