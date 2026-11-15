"""Pruebas del evaluador de F1b-peers en partida (EVIDENCIA.md)."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _load():
    path = Path(__file__).resolve().parents[1] / "live" / "f1bp_eval.py"
    spec = importlib.util.spec_from_file_location("f1bp_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EVAL = _load()
EVAL_PATH = Path(__file__).resolve().parents[1] / "live" / "f1bp_eval.py"


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, sort_keys=True, indent=2) + "\n"
    path.write_bytes(text.encode("utf-8"))


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _append(path, lines):
    path = Path(path)
    current = path.read_text(encoding="utf-8")
    text = current + "".join(line + "\n" for line in lines)
    path.write_bytes(text.encode("utf-8"))


def _write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(events, key=lambda ev: ev["t_ms"])
    text = "".join(json.dumps(ev, sort_keys=True) + "\n" for ev in ordered)
    path.write_bytes(text.encode("utf-8"))


def _base(root, scenarios, fake=False, build="diag", dirty=False):
    root = Path(root)
    manifest = {
        "build": build,
        "fake": fake,
        "git_head": "0" * 40,
        "git_dirty": dirty,
        "pbo_sha256": "a" * 64,
        "dayz_version": None,
        "ports": {"web": 0, "bridge": 0, "proxy": 0},
        "key_sha256": ["b" * 64],
        "lease_ms": 3000,
        "hold_ms": 2000,
        "scenarios": scenarios,
        "t0_ms": 0.0,
    }
    _write_json(root / "manifest.json", manifest)
    _write_text(root / "logs" / "server_script.log", "[DSBX] hello accepted session=srv conn=1\n")
    _write_text(root / "logs" / "client_script.log", "[DSBX] hello accepted session=cli conn=2\n")
    _write_text(root / "logs" / "server.RPT", "RPT sin errores\n")
    _write_text(root / "logs" / "client.RPT", "RPT sin errores\n")
    _write_json(
        root / "logs" / "inventory.json",
        {
            "server": ["logs/server_script.log", "logs/server.RPT"],
            "client": ["logs/client_script.log", "logs/client.RPT"],
        },
    )
    return root


def _g1(root, errors=False, drop_rpt=False, fake=False):
    root = _base(root, ["G1"], fake=fake, build="fake" if fake else "diag")
    _write_jsonl(
        root / "samples" / "G1.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G1"},
            {"t_ms": 200.0, "ev": "connected", "peer": "server"},
            {"t_ms": 300.0, "ev": "connected", "peer": "client"},
            {"t_ms": 400.0, "ev": "end", "status": "ok", "reason": ""},
        ],
    )
    if errors:
        _append(root / "logs" / "server.RPT", ["SCRIPT (E): DSBX_ no compila"])
    if drop_rpt:
        (root / "logs" / "client.RPT").unlink()
    return root


def _g2(root, epoch_mismatch=False, catalog_bytes=3200, aborted=False):
    root = _base(root, ["G2"])
    _write_jsonl(
        root / "samples" / "G2.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G2"},
            {
                "t_ms": 200.0,
                "ev": "bridge",
                "session": "s",
                "server": {"conn": 1, "inst": "i", "epoch": 5, "lost": False},
                "client": {
                    "conn": 1,
                    "inst": "i",
                    "epoch": 6 if epoch_mismatch else 5,
                    "lost": False,
                },
                "catalog": {"complete": True, "n_classes": 12, "catalog_id": "c"},
            },
            {
                "t_ms": 400.0,
                "ev": "end",
                "status": "aborted" if aborted else "ok",
                "reason": "corte" if aborted else "",
            },
        ],
    )
    _write_jsonl(
        root / "samples" / "proxy.jsonl",
        [
            {
                "t_ms": 90.0,
                "t_done_ms": 120.0,
                "req_id": "r1",
                "rule_id": None,
                "rules_version": 1,
                "method": "POST",
                "route": "hello",
                "peer": "server",
                "deliver": 1,
                "session": "s",
                "action": "hello",
                "req_bytes": 3000,
                "upstream_status": 200,
                "resp_bytes": 100,
                "held_ms": 0.0,
                "aborted": False,
            },
            {
                "t_ms": 140.0,
                "t_done_ms": 180.0,
                "req_id": "r2",
                "rule_id": None,
                "rules_version": 1,
                "method": "POST",
                "route": "catalog",
                "peer": "server",
                "deliver": 1,
                "session": "s",
                "action": "catalog",
                "req_bytes": catalog_bytes,
                "upstream_status": 200,
                "resp_bytes": 200,
                "held_ms": 0.0,
                "aborted": False,
            },
        ],
    )
    return root


def _g3(root, c_observado=False, no_rules_active=False):
    root = _base(root, ["G3"])
    events = [
        {"t_ms": 100.0, "ev": "start", "scenario": "G3"},
        {"t_ms": 200.0, "ev": "rules", "version": 1, "rule_ids": ["rewrite"]},
    ]
    if not no_rules_active:
        events.append({"t_ms": 250.0, "ev": "rules_active", "version": 1})
    events += [
        {"t_ms": 300.0, "ev": "case", "name": "a", "op_id": "a1"},
        {"t_ms": 400.0, "ev": "op_state", "op_id": "a1", "state": "observado", "reason": ""},
        {"t_ms": 500.0, "ev": "recovery", "op_id": "ra1"},
        {"t_ms": 600.0, "ev": "op_state", "op_id": "ra1", "state": "observado", "reason": ""},
        {"t_ms": 700.0, "ev": "case", "name": "b", "op_id": "b1"},
        {"t_ms": 800.0, "ev": "op_state", "op_id": "b1", "state": "observado", "reason": ""},
        {"t_ms": 900.0, "ev": "recovery", "op_id": "rb1"},
        {"t_ms": 1000.0, "ev": "op_state", "op_id": "rb1", "state": "observado", "reason": ""},
        {"t_ms": 1100.0, "ev": "case", "name": "c", "op_id": "c1"},
        {
            "t_ms": 1200.0,
            "ev": "op_state",
            "op_id": "c1",
            "state": "fallido",
            "reason": "lectura_no_cumple",
        },
    ]
    if c_observado:
        events.append(
            {"t_ms": 1250.0, "ev": "op_state", "op_id": "c1", "state": "observado", "reason": ""}
        )
    events += [
        {"t_ms": 1300.0, "ev": "recovery", "op_id": "rc1"},
        {"t_ms": 1400.0, "ev": "op_state", "op_id": "rc1", "state": "observado", "reason": ""},
        {"t_ms": 1500.0, "ev": "end", "status": "ok", "reason": ""},
    ]
    _write_jsonl(root / "samples" / "G3.jsonl", events)
    _append(
        root / "logs" / "server_script.log",
        [
            "[DSBX] effect step=retirar session=s1 op=a1 tick_ms=350",
            "[DSBX] effect step=anotar session=s1 op=a1 tick_ms=360",
            "[DSBX] effect step=retirar session=s2 op=b1 tick_ms=750",
            "[DSBX] effect step=anotar session=s2 op=b1 tick_ms=760",
        ],
    )
    return root


def _g4(root, hits=0, drop_inventory=False):
    root = _base(root, ["G4"])
    files = [
        "logs/server_script.log",
        "logs/server.RPT",
        "logs/client_script.log",
        "logs/client.RPT",
    ]
    _write_jsonl(
        root / "samples" / "G4.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G4"},
            {"t_ms": 150.0, "ev": "bad_key_window", "t_start_ms": 150.0, "t_end_ms": 400.0},
            {"t_ms": 200.0, "ev": "case", "name": "a", "op_id": "a1"},
            {"t_ms": 300.0, "ev": "recovery", "op_id": "ra1"},
            {"t_ms": 400.0, "ev": "op_state", "op_id": "ra1", "state": "observado", "reason": ""},
            {"t_ms": 500.0, "ev": "case", "name": "b", "op_id": "b1"},
            {"t_ms": 550.0, "ev": "stale_order", "op_id": "b1", "old_session": "s0"},
            {
                "t_ms": 600.0,
                "ev": "result_seen",
                "op_id": "b1",
                "status": "rejected",
                "reason": "stale_session",
                "dup": False,
            },
            {"t_ms": 700.0, "ev": "recovery", "op_id": "rb1"},
            {"t_ms": 800.0, "ev": "op_state", "op_id": "rb1", "state": "observado", "reason": ""},
            {"t_ms": 900.0, "ev": "case", "name": "c", "op_id": "c1"},
            {
                "t_ms": 1000.0,
                "ev": "op_state",
                "op_id": "c1",
                "state": "fallido",
                "reason": "conexion_perdida",
            },
            {"t_ms": 1100.0, "ev": "recovery", "op_id": "rc1"},
            {"t_ms": 1200.0, "ev": "op_state", "op_id": "rc1", "state": "observado", "reason": ""},
            {"t_ms": 1300.0, "ev": "key_scan", "files": files, "hits": hits},
            {"t_ms": 1400.0, "ev": "end", "status": "ok", "reason": ""},
        ],
    )
    _write_jsonl(
        root / "samples" / "proxy.jsonl",
        [
            {
                "t_ms": 250.0,
                "t_done_ms": 260.0,
                "req_id": "r1",
                "rule_id": None,
                "rules_version": 1,
                "method": "POST",
                "route": "hello",
                "peer": "server",
                "deliver": 1,
                "session": "s0",
                "action": "hello",
                "req_bytes": 3000,
                "upstream_status": 401,
                "resp_bytes": 50,
                "held_ms": 0.0,
                "aborted": False,
            },
        ],
    )
    if drop_inventory:
        (root / "logs" / "inventory.json").unlink()
    return root


def _g5(root, b4000_anotar=False, drop_server_log=False):
    root = _base(root, ["G5"])
    _write_jsonl(
        root / "samples" / "G5.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G5"},
            {"t_ms": 150.0, "ev": "window", "t_start_ms": 150.0, "t_end_ms": 3000.0},
            {"t_ms": 200.0, "ev": "case", "name": "a2500", "peer": "server", "op_id": "a1"},
            {"t_ms": 300.0, "ev": "recovery", "op_id": "ra1"},
            {"t_ms": 400.0, "ev": "op_state", "op_id": "ra1", "state": "observado", "reason": ""},
            {"t_ms": 500.0, "ev": "case", "name": "a4500", "peer": "client", "op_id": "a2"},
            {"t_ms": 600.0, "ev": "recovery", "op_id": "ra2"},
            {"t_ms": 700.0, "ev": "op_state", "op_id": "ra2", "state": "observado", "reason": ""},
            {"t_ms": 800.0, "ev": "case", "name": "b2500", "peer": "server", "op_id": "b1"},
            {"t_ms": 900.0, "ev": "recovery", "op_id": "rb1"},
            {"t_ms": 1000.0, "ev": "op_state", "op_id": "rb1", "state": "observado", "reason": ""},
            {"t_ms": 1010.0, "ev": "op_state", "op_id": "b1", "state": "observado", "reason": ""},
            {"t_ms": 1100.0, "ev": "case", "name": "b4000", "peer": "server", "op_id": "b2"},
            {"t_ms": 1200.0, "ev": "recovery", "op_id": "rb2"},
            {
                "t_ms": 1250.0,
                "ev": "op_state",
                "op_id": "b2",
                "state": "parcial",
                "reason": "lease_expired",
            },
            {"t_ms": 1300.0, "ev": "op_state", "op_id": "rb2", "state": "observado", "reason": ""},
            {"t_ms": 1400.0, "ev": "gap_reset", "confirmed": True},
            {"t_ms": 1500.0, "ev": "end", "status": "ok", "reason": ""},
        ],
    )
    proxy = []
    for index, done in enumerate((200.0, 700.0, 1200.0, 1700.0)):
        proxy.append(
            {
                "t_ms": done - 10.0,
                "t_done_ms": done,
                "req_id": f"r{index}",
                "rule_id": None,
                "rules_version": 1,
                "method": "POST",
                "route": "poll",
                "peer": "server",
                "deliver": 1,
                "session": "s",
                "action": "poll",
                "req_bytes": 100,
                "upstream_status": 200,
                "resp_bytes": 100,
                "held_ms": 0.0,
                "aborted": False,
            }
        )
    _write_jsonl(root / "samples" / "proxy.jsonl", proxy)
    _append(root / "logs" / "server_script.log", ["[DSBX] config qa_step_gap_ms=0"])
    _append(root / "logs" / "client_script.log", ["[DSBX] lease lost age_ms=3100 tick_ms=1000"])
    _append(
        root / "logs" / "server_script.log",
        [
            "[DSBX] effect step=retirar session=s1 op=b1 tick_ms=850",
            "[DSBX] effect step=anotar session=s1 op=b1 tick_ms=860",
            "[DSBX] effect step=retirar session=s2 op=b2 tick_ms=1150",
        ],
    )
    if b4000_anotar:
        _append(
            root / "logs" / "server_script.log",
            ["[DSBX] effect step=anotar session=s2 op=b2 tick_ms=1160"],
        )
    if drop_server_log:
        (root / "logs" / "server_script.log").unlink()
    return root


def _g6(root, late_done=False, no_result=False):
    root = _base(root, ["G6"])
    events = [
        {"t_ms": 100.0, "ev": "start", "scenario": "G6"},
        {
            "t_ms": 200.0,
            "ev": "pause_order",
            "op_id": "p1",
            "T_d_ms": 1000.0,
            "T_s_ms": 2000.0,
            "T_e_ms": 4000.0,
            "D_ms": 5000.0,
        },
        {"t_ms": 210.0, "ev": "clock_run", "t_start_ms": 2000.0, "t_end_ms": 4000.0},
    ]
    if not no_result:
        events.append(
            {
                "t_ms": 6000.0,
                "ev": "result_seen",
                "op_id": "p1",
                "status": "done" if late_done else "rejected",
                "reason": "" if late_done else "expired",
                "dup": False,
            }
        )
    events += [
        {"t_ms": 6100.0, "ev": "recovery", "op_id": "rp"},
        {"t_ms": 6200.0, "ev": "op_state", "op_id": "rp", "state": "observado", "reason": ""},
        {"t_ms": 6300.0, "ev": "end", "status": "ok", "reason": ""},
    ]
    _write_jsonl(root / "samples" / "G6.jsonl", events)
    _append(
        root / "logs" / "server_script.log",
        [
            "[DSBX] clock tick_ms=2000",
            "[DSBX] clock tick_ms=4000",
            "[DSBX] clock tick_ms=4500",
        ],
    )
    return root


def _g7(root, r_held_gap=200, drop_client_log=False):
    root = _base(root, ["G7"])
    _write_jsonl(
        root / "samples" / "G7.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G7"},
            {"t_ms": 150.0, "ev": "rules", "version": 1, "rule_ids": ["r_held", "invalid_P", "late_cb"]},
            {"t_ms": 160.0, "ev": "rules_active", "version": 1},
            {"t_ms": 1000.0, "ev": "case", "name": "r_held", "rule_id": "r_held"},
            {"t_ms": 2000.0, "ev": "case", "name": "invalid_P", "rule_id": "invalid_P"},
            {"t_ms": 3000.0, "ev": "case", "name": "late_cb", "rule_id": "late_cb"},
            {"t_ms": 4000.0, "ev": "recovery", "op_id": "rg"},
            {"t_ms": 4500.0, "ev": "op_state", "op_id": "rg", "state": "observado", "reason": ""},
            {"t_ms": 5000.0, "ev": "end", "status": "ok", "reason": ""},
        ],
    )
    if r_held_gap == 200:
        held_times = [1100.0, 1300.0, 1500.0, 1700.0]
    else:
        held_times = [1050.0, 1950.0]
    proxy = [
        {
            "t_ms": moment - 10.0,
            "t_done_ms": moment,
            "req_id": f"h{index}",
            "rule_id": "r_held",
            "rules_version": 1,
            "method": "POST",
            "route": "poll",
            "peer": "server",
            "deliver": 0,
            "session": "s",
            "action": "poll",
            "req_bytes": 100,
            "upstream_status": 200,
            "resp_bytes": 100,
            "held_ms": 0.0,
            "aborted": False,
        }
        for index, moment in enumerate(held_times)
    ]
    proxy.append(
        {
            "t_ms": 2090.0,
            "t_done_ms": 2100.0,
            "req_id": "inv",
            "rule_id": "invalid_P",
            "rules_version": 1,
            "method": "POST",
            "route": "poll",
            "peer": "server",
            "deliver": 1,
            "session": "s",
            "action": "poll",
            "req_bytes": 100,
            "upstream_status": 200,
            "resp_bytes": 100,
            "held_ms": 0.0,
            "aborted": False,
        }
    )
    _write_jsonl(root / "samples" / "proxy.jsonl", proxy)
    _append(
        root / "logs" / "server_script.log",
        [
            "[DSBX] rest invalid ch=P kind=3 tick_ms=2100",
            "[DSBX] rest late ch=R kind=3 tick_ms=3100",
        ],
    )
    if drop_client_log:
        (root / "logs" / "client_script.log").unlink()
    return root


def _g8(root, b_two_pairs=False, aborted=False):
    root = _base(root, ["G8"])
    _write_jsonl(
        root / "samples" / "G8.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G8"},
            {"t_ms": 200.0, "ev": "case", "name": "a", "op_id": "a1"},
            {"t_ms": 300.0, "ev": "op_state", "op_id": "a1", "state": "observado", "reason": ""},
            {"t_ms": 310.0, "ev": "result_seen", "op_id": "a1", "status": "done", "reason": "", "dup": False},
            {"t_ms": 320.0, "ev": "result_seen", "op_id": "a1", "status": "done", "reason": "", "dup": False},
            {"t_ms": 400.0, "ev": "case", "name": "b", "op_id": "b1"},
            {"t_ms": 500.0, "ev": "result_seen", "op_id": "b1", "status": "done", "reason": "", "dup": False},
            {"t_ms": 600.0, "ev": "result_seen", "op_id": "b1", "status": "done", "reason": "", "dup": True},
            {"t_ms": 700.0, "ev": "case", "name": "c", "op_id": "c1"},
            {"t_ms": 800.0, "ev": "op_state", "op_id": "c1", "state": "observado", "reason": ""},
            {
                "t_ms": 900.0,
                "ev": "end",
                "status": "aborted" if aborted else "ok",
                "reason": "corte" if aborted else "",
            },
        ],
    )
    _append(
        root / "logs" / "server_script.log",
        [
            "[DSBX] effect step=retirar session=s1 op=a1 tick_ms=250",
            "[DSBX] effect step=anotar session=s1 op=a1 tick_ms=260",
            "[DSBX] effect step=retirar session=s2 op=b1 tick_ms=450",
            "[DSBX] effect step=anotar session=s2 op=b1 tick_ms=460",
            "[DSBX] effect step=retirar session=s3 op=c1 tick_ms=750",
            "[DSBX] effect step=anotar session=s3 op=c1 tick_ms=760",
        ],
    )
    if b_two_pairs:
        _append(
            root / "logs" / "server_script.log",
            [
                "[DSBX] effect step=retirar session=s2 op=b1 tick_ms=470",
                "[DSBX] effect step=anotar session=s2 op=b1 tick_ms=480",
            ],
        )
    return root


def _g9(root, slow=False, drop_server_log=False):
    root = _base(root, ["G9"])
    events = [
        {"t_ms": 100.0, "ev": "start", "scenario": "G9"},
        {"t_ms": 150.0, "ev": "gap_reset", "confirmed": True},
    ]
    effects = []
    for index in range(100):
        op = f"op{index:03d}"
        events.append({"t_ms": 200.0 + index, "ev": "mix_op", "op_id": op})
        apply_ms = 1000.0 + index * 10
        events.append(
            {
                "t_ms": apply_ms,
                "ev": "apply",
                "op_id": op,
                "http_status": 200,
                "ttl_ms": 5000,
            }
        )
        observed_ms = apply_ms + (2000.0 if slow and index < 10 else 50.0)
        events.append(
            {
                "t_ms": observed_ms,
                "ev": "op_state",
                "op_id": op,
                "state": "observado",
                "reason": "",
            }
        )
        effects.append(f"[DSBX] effect step=retirar session=s op={op} tick_ms={int(apply_ms)}")
        effects.append(f"[DSBX] effect step=anotar session=s op={op} tick_ms={int(apply_ms) + 1}")
    events.append({"t_ms": 5000.0, "ev": "end", "status": "ok", "reason": ""})
    _write_jsonl(root / "samples" / "G9.jsonl", events)
    _append(root / "logs" / "server_script.log", effects)
    if drop_server_log:
        (root / "logs" / "server_script.log").unlink()
    return root


def _two_rows(root, dirty=False, g2_aborted=False, g2_mismatch=False):
    root = _base(root, ["G1", "G2"], dirty=dirty)
    _write_jsonl(
        root / "samples" / "G1.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G1"},
            {"t_ms": 200.0, "ev": "connected", "peer": "server"},
            {"t_ms": 300.0, "ev": "connected", "peer": "client"},
            {"t_ms": 400.0, "ev": "end", "status": "ok", "reason": ""},
        ],
    )
    _write_jsonl(
        root / "samples" / "G2.jsonl",
        [
            {"t_ms": 100.0, "ev": "start", "scenario": "G2"},
            {
                "t_ms": 200.0,
                "ev": "bridge",
                "session": "s",
                "server": {"conn": 1, "inst": "i", "epoch": 5, "lost": False},
                "client": {
                    "conn": 1,
                    "inst": "i",
                    "epoch": 6 if g2_mismatch else 5,
                    "lost": False,
                },
                "catalog": {"complete": True, "n_classes": 12, "catalog_id": "c"},
            },
            {
                "t_ms": 400.0,
                "ev": "end",
                "status": "aborted" if g2_aborted else "ok",
                "reason": "corte" if g2_aborted else "",
            },
        ],
    )
    _write_jsonl(
        root / "samples" / "proxy.jsonl",
        [
            {
                "t_ms": 90.0,
                "t_done_ms": 120.0,
                "req_id": "r1",
                "rule_id": None,
                "rules_version": 1,
                "method": "POST",
                "route": "hello",
                "peer": "server",
                "deliver": 1,
                "session": "s",
                "action": "hello",
                "req_bytes": 3000,
                "upstream_status": 200,
                "resp_bytes": 100,
                "held_ms": 0.0,
                "aborted": False,
            },
            {
                "t_ms": 140.0,
                "t_done_ms": 180.0,
                "req_id": "r2",
                "rule_id": None,
                "rules_version": 1,
                "method": "POST",
                "route": "catalog",
                "peer": "server",
                "deliver": 1,
                "session": "s",
                "action": "catalog",
                "req_bytes": 3200,
                "upstream_status": 200,
                "resp_bytes": 200,
                "held_ms": 0.0,
                "aborted": False,
            },
        ],
    )
    return root


class TestG1(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g1(tmp))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")
            self.assertEqual(verdict["aggregate"], "PASA")

    def test_fail_script_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g1(tmp, errors=True))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def test_inconclusive_missing_rpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g1(tmp, drop_rpt=True))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "INCONCLUSO")

    def test_fake_not_evaluated(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g1(tmp, fake=True))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "INCONCLUSO")


class TestG2(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g2(tmp))
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "PASA")

    def test_fail_epoch_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g2(tmp, epoch_mismatch=True))
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "FALLA")

    def test_inconclusive_aborted(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g2(tmp, aborted=True))
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "INCONCLUSO")


class TestG3(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "PASA")

    def test_fail_c_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, c_observado=True))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "FALLA")

    def test_inconclusive_rules_unconfirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, no_rules_active=True))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")


class TestG4(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "PASA")

    def test_fail_key_scan_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, hits=1))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "FALLA")

    def test_inconclusive_missing_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, drop_inventory=True))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "INCONCLUSO")


class TestG5(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "PASA")

    def test_fail_b4000_with_anotar(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, b4000_anotar=True))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "FALLA")

    def test_inconclusive_missing_server_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, drop_server_log=True))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "INCONCLUSO")


class TestG6(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "PASA")

    def test_fail_late_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp, late_done=True))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "FALLA")

    def test_inconclusive_without_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp, no_result=True))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "INCONCLUSO")


class TestG7(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "PASA")

    def test_fail_r_held_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, r_held_gap=1000))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")

    def test_inconclusive_missing_client_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, drop_client_log=True))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")


class TestG8(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "PASA")

    def test_fail_b_two_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, b_two_pairs=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "FALLA")

    def test_inconclusive_aborted(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, aborted=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "INCONCLUSO")


class TestG9(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "PASA")

    def test_fail_p95(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, slow=True))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "FALLA")

    def test_inconclusive_missing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, drop_server_log=True))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "INCONCLUSO")


class TestAggregate(unittest.TestCase):
    def test_git_dirty_all_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, dirty=True))
            for gid in ("G1", "G2"):
                self.assertEqual(verdict["rows"][gid]["verdict"], "INCONCLUSO")
            self.assertEqual(verdict["aggregate"], "INCONCLUSO")

    def test_aggregate_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, g2_mismatch=True))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "FALLA")
            self.assertEqual(verdict["aggregate"], "FALLA")

    def test_aggregate_inconcluso(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, g2_aborted=True))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "INCONCLUSO")
            self.assertEqual(verdict["aggregate"], "INCONCLUSO")

    def test_aggregate_pasa(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp))
            self.assertEqual(verdict["aggregate"], "PASA")


class TestParseScriptLog(unittest.TestCase):
    def test_ten_forms_and_integers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server_script.log"
            _write_text(
                path,
                "\n".join(
                    [
                        "[DSBX] effect step=retirar session=s1 op=o1 tick_ms=10",
                        "[DSBX] rest error ch=P kind=3 state=2 tick_ms=20",
                        "[DSBX] rest timeout ch=R kind=4 src=watchdog tick_ms=30",
                        "[DSBX] rest invalid ch=P kind=5 tick_ms=40",
                        "[DSBX] rest late ch=R kind=6 tick_ms=50",
                        "[DSBX] rest repeat ch=P kind=7 via=error tick_ms=60",
                        "[DSBX] lease lost age_ms=3100 tick_ms=70",
                        "[DSBX] clock tick_ms=80",
                        "[DSBX] config qa_step_gap_ms=0",
                        "[DSBX] hello accepted session=srv conn=7",
                        "SCRIPT (E): DSBX_ no compila",
                        "linea desconocida",
                    ]
                )
                + "\n",
            )
            events = EVAL.parse_script_log(path)
            kinds = [ev["kind"] for ev in events]
            self.assertEqual(
                kinds,
                [
                    "effect",
                    "rest_error",
                    "rest_timeout",
                    "rest_invalid",
                    "rest_late",
                    "rest_repeat",
                    "lease_lost",
                    "clock",
                    "config_gap",
                    "hello_accepted",
                    "script_error",
                ],
            )
            self.assertEqual(events[0]["step"], "retirar")
            self.assertEqual(events[0]["tick_ms"], 10)
            self.assertIsInstance(events[0]["tick_ms"], int)
            self.assertEqual(events[1]["kind_id"], 3)
            self.assertEqual(events[1]["state"], 2)
            self.assertIsInstance(events[1]["state"], int)
            self.assertEqual(events[2]["src"], "watchdog")
            self.assertEqual(events[2]["kind_id"], 4)
            self.assertEqual(events[5]["via"], "error")
            self.assertEqual(events[6]["age_ms"], 3100)
            self.assertIsInstance(events[6]["age_ms"], int)
            self.assertEqual(events[7]["tick_ms"], 80)
            self.assertEqual(events[8]["qa_step_gap_ms"], 0)
            self.assertEqual(events[9]["conn"], 7)
            self.assertIsInstance(events[9]["conn"], int)


class TestCli(unittest.TestCase):
    def _run(self, root):
        return subprocess.run(
            [sys.executable, str(EVAL_PATH), str(root)],
            capture_output=True,
            text=True,
        )

    def test_exit_0_pasa(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            result = self._run(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["aggregate"], "PASA")
            self.assertIn("AGGREGATE PASA", result.stdout)
            raw = (root / "verdict.json").read_bytes()
            self.assertNotIn(b"\r\n", raw)
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))

    def test_exit_1_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp, errors=True)
            result = self._run(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["aggregate"], "FALLA")

    def test_exit_2_inconcluso(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp, drop_rpt=True)
            result = self._run(root)
            self.assertEqual(result.returncode, 2, result.stderr)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["aggregate"], "INCONCLUSO")

    def test_evaluate_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            EVAL.evaluate(root)
            self.assertFalse((root / "verdict.json").exists())


if __name__ == "__main__":
    unittest.main()
