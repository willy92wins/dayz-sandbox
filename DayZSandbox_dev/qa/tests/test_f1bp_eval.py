"""Pruebas del evaluador de F1b-peers en partida (EVIDENCIA.md, v1.5: R1-R15; v1.6: R18, R20-R24, R26).

Las pruebas de una regla v1.5 estan escritas para caer si se quita la regla: la fixture la daba por
buena el evaluador anterior y no el nuevo, o al reves (cada prueba lo dice en su comentario).
"""

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


def _wall(t_ms):
    """Hora de pared "HH:MM:SS.mmm" de un instante del arnes, con t0_ms = 0 <-> t0_wall = 00:00:00.000."""
    ms = int(t_ms)
    return "%02d:%02d:%02d.%03d" % (ms // 3600000 % 24, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def _stamp(line):
    """Como el motor: una linea [DSBX] lleva delante su hora de pared. En estas pruebas la hora sale de
    su tick_ms (tick == reloj del arnes); las pruebas del desfase escriben sus lineas ya con hora."""
    if not line.startswith("[DSBX] "):
        return line
    fields = dict(part.split("=", 1) for part in line.split() if "=" in part)
    tick = fields.get("tick_ms")
    if tick is None or not tick.lstrip("-").isdigit():
        return line
    return _wall(int(tick)) + " SCRIPT       : " + line


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(_stamp(line) + "\n" for line in text.splitlines()) if text else text
    path.write_bytes(text.encode("utf-8"))


def _append(path, lines):
    path = Path(path)
    current = path.read_text(encoding="utf-8")
    text = current + "".join(_stamp(line) + "\n" for line in lines)
    path.write_bytes(text.encode("utf-8"))


def _write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(events, key=lambda ev: ev["t_ms"])
    text = "".join(json.dumps(ev, sort_keys=True) + "\n" for ev in ordered)
    path.write_bytes(text.encode("utf-8"))


def _add_events(path, events):
    path = Path(path)
    current = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    _write_jsonl(path, current + events)


INVENTORY = {
    "server": {"dir": "C:/prof/server", "files": ["script_1.log", "server.RPT"]},
    "client": {"dir": "C:/prof/client", "files": ["script_1.log", "client.RPT"]},
    "copies": [
        {"peer": "server", "src": "script_1.log", "dest": "server_script.log"},
        {"peer": "server", "src": "server.RPT", "dest": "server.RPT"},
        {"peer": "client", "src": "script_1.log", "dest": "client_script.log"},
        {"peer": "client", "src": "client.RPT", "dest": "client.RPT"},
    ],
}


def _scan_files(root):
    """key_scan.files como lo escribe el orquestador (R4): ruta absoluta de cada fichero del inventario."""
    paths = []
    for peer in ("server", "client"):
        for name in INVENTORY[peer]["files"]:
            paths.append(INVENTORY[peer]["dir"] + "/" + name)
    for item in INVENTORY["copies"]:
        paths.append(str(Path(root) / "logs" / item["dest"]))
    return paths


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
        "t0_wall": "00:00:00.000",
    }
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "logs_ready.json", {"all_closed": True})  # R2
    _write_text(root / "logs" / "server_script.log", "[DSBX] hello accepted session=srv conn=1\n")
    _write_text(root / "logs" / "client_script.log", "[DSBX] hello accepted session=cli conn=2\n")
    _write_text(root / "logs" / "server.RPT", "RPT sin errores\n")
    _write_text(root / "logs" / "client.RPT", "RPT sin errores\n")
    _write_json(root / "logs" / "inventory.json", INVENTORY)  # R3
    return root


def _px(t_ms, route="poll", peer="server", deliver=1, rule=None, version=1, status=200, done=None, req_bytes=100):
    """Una linea de proxy.jsonl."""
    return {
        "t_ms": float(t_ms),
        "t_done_ms": float(done if done is not None else t_ms + 10),
        "req_id": f"r{int(t_ms)}",
        "rule_id": rule,
        "rules_version": version,
        "method": "POST",
        "route": route,
        "peer": peer,
        "deliver": deliver,
        "session": "s",
        "action": "poll",
        "req_bytes": req_bytes,
        "upstream_status": status,
        "resp_bytes": 100,
        "held_ms": 0.0,
        "aborted": False,
    }


def _rules(t_ms, version, ids):
    """`rules` y su `rules_active` (R9/R10: con ids vacio es el fin de la inyeccion)."""
    return [
        {"t_ms": float(t_ms), "ev": "rules", "version": version, "rule_ids": ids},
        {"t_ms": float(t_ms) + 1, "ev": "rules_active", "version": version},
    ]


def _state(t_ms, session, op, state, reason=""):
    return {"t_ms": float(t_ms), "ev": "op_state", "session": session, "op_id": op, "state": state, "reason": reason}


def _recov(t_ms, op, session="s"):
    """`recovery` y su op_state observado 100 ms despues."""
    return [
        {"t_ms": float(t_ms), "ev": "recovery", "op_id": op},
        _state(t_ms + 100, session, op, "observado"),
    ]


def _eff(step, session, op, tick):
    return f"[DSBX] effect step={step} session={session} op={op} tick_ms={tick}"


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


def _g2(root, epoch_mismatch=False, catalog_bytes=3200, aborted=False, fake=False):
    root = _base(root, ["G2"], fake=fake, build="fake" if fake else "diag")
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
            _px(90, route="hello", req_bytes=3000, done=120),
            _px(140, route="catalog", req_bytes=catalog_bytes, done=180),
        ],
    )
    return root


def _g3(
    root,
    c_observado=False,
    no_rules_active=False,
    recovery_ab=True,
    recovery_c=True,
    c_effects=False,
    dup_effect=False,
    a_effect_session="s1",
    drop_case=None,
    dup_case=None,
    px_t=1110,
    px_version=1,
    px_rule="rewrite",
    c_rule=True,
):
    root = _base(root, ["G3"])
    events = [{"t_ms": 100.0, "ev": "start", "scenario": "G3"}]
    events += _rules(200, 1, ["rewrite"])
    if no_rules_active:
        events = [ev for ev in events if ev["ev"] != "rules_active"]
    cases = {
        "a": {"t_ms": 300.0, "ev": "case", "name": "a", "session": "s1", "op_id": "a1"},
        "b": {"t_ms": 700.0, "ev": "case", "name": "b", "session": "s2", "op_id": "b1"},
        "c": {"t_ms": 1100.0, "ev": "case", "name": "c", "session": "s2", "op_id": "c1"},
    }
    if c_rule:
        cases["c"]["rule_id"] = "rewrite"
    for name, case in cases.items():
        if name == drop_case:
            continue
        events.append(case)
        if name == dup_case:
            events.append(dict(case, t_ms=case["t_ms"] + 1))
    events += [_state(400, "s1", "a1", "observado"), _state(800, "s2", "b1", "observado")]
    if recovery_ab:
        events += _recov(500, "ra1", "s1") + _recov(900, "rb1", "s2")
    events.append(_state(1200, "s2", "c1", "fallido", "lectura_no_cumple"))
    if c_observado:
        events.append(_state(1250, "s2", "c1", "observado"))
    if recovery_c:
        events += _recov(1300, "rc1", "s2")
    events.append({"t_ms": 1500.0, "ev": "end", "status": "ok", "reason": ""})
    _write_jsonl(root / "samples" / "G3.jsonl", events)
    _write_jsonl(root / "samples" / "proxy.jsonl", [_px(px_t, rule=px_rule, version=px_version)])
    lines = [
        _eff("retirar", a_effect_session, "a1", 350),
        _eff("anotar", a_effect_session, "a1", 360),
        _eff("retirar", "s2", "b1", 750),
        _eff("anotar", "s2", "b1", 760),
    ]
    if dup_effect:
        # La misma linea otra vez, con el mismo tick: antes se deduplicaba por tick (R8).
        lines.append(_eff("retirar", a_effect_session, "a1", 350))
    if c_effects:
        # D-P2: el peer anota la revision reescrita; el backend la rechaza despues.
        lines += [_eff("retirar", "s2", "c1", 1150), _eff("anotar", "s2", "c1", 1160)]
    _append(root / "logs" / "server_script.log", lines)
    return root


def _g4(
    root,
    hits=0,
    drop_inventory=False,
    effect_in_window=False,
    recovery_effect_in_window=False,
    b_effect_old_session=False,
    scan_files="all",
    no_proxy_rule=None,
    b_session="s1",
):
    root = _base(root, ["G4"])
    files = _scan_files(root)
    if scan_files == "missing_one":
        files = files[1:]
    elif scan_files == "other_dir_same_name":
        files = ["D:/otro/" + path.rsplit("/", 1)[-1] if path == files[0] else path for path in files]
    elif scan_files == "upper":
        files = [path.upper() for path in files]
    events = [{"t_ms": 100.0, "ev": "start", "scenario": "G4"}]
    events += _rules(110, 1, ["bad409", "stale_rw", "cut"])
    events += [
        {"t_ms": 150.0, "ev": "bad_key_window", "t_start_ms": 150.0, "t_end_ms": 400.0},
        {"t_ms": 200.0, "ev": "case", "name": "a", "session": "s1", "op_id": "a1", "rule_id": "bad409"},
    ]
    events += _recov(300, "ra1", "s1")
    events += [
        {"t_ms": 500.0, "ev": "case", "name": "b", "session": b_session, "op_id": "b1", "rule_id": "stale_rw"},
        {"t_ms": 550.0, "ev": "stale_order", "op_id": "b1", "old_session": "s0"},
        {
            "t_ms": 600.0,
            "ev": "result_seen",
            "op_id": "b1",
            "status": "rejected",
            "reason": "stale_session",
            "dup": False,
        },
    ]
    events += _recov(700, "rb1", "s1")
    events += [
        {"t_ms": 900.0, "ev": "case", "name": "c", "session": "s1", "op_id": "c1", "rule_id": "cut"},
        _state(1000, "s1", "c1", "fallido", "conexion_perdida"),
    ]
    events += _recov(1100, "rc1", "s1")
    events += [
        {"t_ms": 1300.0, "ev": "key_scan", "files": files, "hits": hits},
        {"t_ms": 1400.0, "ev": "end", "status": "ok", "reason": ""},
    ]
    _write_jsonl(root / "samples" / "G4.jsonl", events)
    proxy = [
        _px(220, rule="bad409", status=409),
        _px(250, route="hello", status=401),
        _px(520, rule="stale_rw"),
        _px(910, rule="cut", status=None),
    ]
    proxy = [ev for ev in proxy if no_proxy_rule is None or ev["rule_id"] != no_proxy_rule]
    _write_jsonl(root / "samples" / "proxy.jsonl", proxy)
    lines = []
    if effect_in_window:
        lines.append(_eff("retirar", "s1", "x1", 300))
    if recovery_effect_in_window:
        lines.append(_eff("retirar", "s1", "ra1", 350))
    if b_effect_old_session:
        lines.append(_eff("retirar", "s0", "b1", 1500))
    if lines:
        _append(root / "logs" / "server_script.log", lines)
    if drop_inventory:
        (root / "logs" / "inventory.json").unlink()
    return root


G5_CASES = [
    ("a2500", "server"),
    ("a4500", "server"),
    ("a2500", "client"),
    ("a4500", "client"),
    ("b2500", "server"),
    ("b4000", "server"),
]


def _g5(
    root,
    b4000_anotar=False,
    drop_server_log=False,
    filler=False,
    skip=None,
    uninjected=False,
    client_lost=True,
    b2500_session="s",
):
    root = _base(root, ["G5"])
    ids = [f"r_{name}_{peer}" for name, peer in G5_CASES]
    events = [{"t_ms": 100.0, "ev": "start", "scenario": "G5"}]
    events += _rules(110, 1, ids)
    proxy = []
    server_lines = []
    client_lines = []
    for index, (name, peer) in enumerate(G5_CASES):
        if (name, peer) == skip:
            continue
        base = 10000.0 * (index + 1)
        rule = f"r_{name}_{peer}"
        op = f"op{index}"
        events.append(
            {"t_ms": base, "ev": "case", "name": name, "peer": peer, "session": "s", "op_id": op, "rule_id": rule}
        )
        injected = rule if not uninjected else None
        if name in ("a2500", "a4500"):
            hold = 2500 if name == "a2500" else 4500
            start = base + 10
            events.append({"t_ms": start, "ev": "window", "t_start_ms": start, "t_end_ms": start + hold})
            if name == "a2500" and filler:
                # Las unicas respuestas de P dejan un hueco de 3200 ms; las del canal R lo rellenan.
                proxy += [
                    _px(start + 490, peer=peer, rule=injected, done=start + 500),
                    _px(start + 3690, peer=peer, done=start + 3700),
                    _px(start + 1490, route="result", peer=peer, done=start + 1500),
                    _px(start + 2490, route="result", peer=peer, done=start + 2500),
                ]
            elif name == "a2500":
                proxy += [
                    _px(start + 790, peer=peer, rule=injected, done=start + 800),
                    _px(start + 1590, peer=peer, done=start + 1600),
                    _px(start + 2390, peer=peer, route="hello", done=start + 2400),
                    _px(start + 2990, peer=peer, done=start + 3000),
                ]
            else:
                proxy.append(_px(start + 90, peer=peer, rule=injected, done=start + 100))
                if client_lost or peer == "server":
                    line = f"{_wall(start + 3200)} SCRIPT       : [DSBX] lease lost age_ms=3100 tick_ms={int(start) + 3200}"
                    (server_lines if peer == "server" else client_lines).append(line)
        elif name == "b2500":
            proxy.append(_px(base + 50, rule=injected))
            events.append(_state(base + 300, "s", op, "observado"))
            server_lines += [_eff("retirar", b2500_session, op, int(base) + 250), _eff("anotar", b2500_session, op, int(base) + 260)]
        elif name == "b4000":
            proxy.append(_px(base + 50, rule=injected))
            events.append(_state(base + 300, "s", op, "parcial", "lease_expired"))
            server_lines.append(_eff("retirar", "s", op, int(base) + 250))
            if b4000_anotar:
                server_lines.append(_eff("anotar", "s", op, int(base) + 260))
        events += _recov(base + 6000, f"rec{index}")
    events.append({"t_ms": 100000.0, "ev": "gap_reset", "confirmed": True})
    events.append({"t_ms": 110000.0, "ev": "end", "status": "ok", "reason": ""})
    _write_jsonl(root / "samples" / "G5.jsonl", events)
    _write_jsonl(root / "samples" / "proxy.jsonl", proxy)
    _append(root / "logs" / "server_script.log", ["[DSBX] config qa_step_gap_ms=0"] + server_lines)
    if client_lines:
        _append(root / "logs" / "client_script.log", client_lines)
    if drop_server_log:
        (root / "logs" / "server_script.log").unlink()
    return root


def _g6(root, late_done=False, no_result=False, order=None, ttl=1500, drop_clock_run=False, px_rule="g6_deliver"):
    root = _base(root, ["G6"])
    pause = {
        "t_ms": 200.0,
        "ev": "pause_order",
        "session": "s",
        "op_id": "p1",
        "rule_id": "g6_deliver",
        "T_d_ms": 1900.0,
        "T_s_ms": 2000.0,
        "T_e_ms": 4000.0,
        "D_ms": 3500.0,
    }
    pause.update(order or {})
    events = [{"t_ms": 100.0, "ev": "start", "scenario": "G6"}]
    events += _rules(110, 1, ["g6_deliver"])
    events += [
        {"t_ms": 150.0, "ev": "apply", "session": "s", "op_id": "p1", "http_status": 200, "ttl_ms": ttl, "t_end_ms": 160.0},
        pause,
    ]
    if not drop_clock_run:
        events.append({"t_ms": 210.0, "ev": "clock_run", "t_start_ms": 2000.0, "t_end_ms": 4000.0})
    if not no_result:
        events.append(
            {
                "t_ms": 4100.0,
                "ev": "result_seen",
                "op_id": "p1",
                "status": "done" if late_done else "rejected",
                "reason": "" if late_done else "expired",
                "dup": False,
            }
        )
    events += _recov(4200, "rp")
    events.append({"t_ms": 4400.0, "ev": "end", "status": "ok", "reason": ""})
    _write_jsonl(root / "samples" / "G6.jsonl", events)
    _write_jsonl(root / "samples" / "proxy.jsonl", [_px(1890, rule=px_rule)])
    _append(
        root / "logs" / "server_script.log",
        [
            "[DSBX] clock tick_ms=2000",
            "[DSBX] clock tick_ms=4000",
            "[DSBX] clock tick_ms=4500",
        ],
    )
    return root


G7_NAMES = (
    [f"status{code}_{ch}" for code in (400, 401, 409, 413, 500) for ch in ("P", "R")]
    + ["timeout_P", "r_held"]
    + [
        "invalid_no_ok_P",
        "invalid_ok_false_P",
        "invalid_now_decimal_P",
        "invalid_now_text_P",
        "measure_no_args_P",
        "invalid_all_P",
    ]
    + ["measure_ok1_P", "measure_args_empty_P", "late_cb"]
)


def _g7(
    root,
    drop_client_log=False,
    tick_offset=0,
    skip=(),
    no_empty=(),
    uninjected=(),
    held_mode="ok",
    extra=(),
    wall_override=None,
    lease_lost=True,
    late_line=True,
    late_change=False,
    px_version=None,
    measure_effect=False,
    valid_p=False,
    p_second=3600,
):
    """21 casos de G7 de 10000 ms cada uno: reglas, caso, disparo, lineas del log, fin de la inyeccion
    (rules vacio a base+5000) y recuperacion (base+6000). `extra`: (caso, desfase, linea) de efectos.
    Las medidas con orden (H-08) llevan su apply; `measure_effect` le pone un effect a la sin args."""
    root = _base(root, ["G7"])
    wall_override = wall_override or {}
    events = [{"t_ms": 100.0, "ev": "start", "scenario": "G7"}]
    proxy = []
    lines = []

    def log(name, offset, text, base):
        t = wall_override.get(name, base + offset)
        lines.append(f"{_wall(t)} SCRIPT       : [DSBX] {text} tick_ms={int(base + offset) + tick_offset}")

    index = 0
    bases = {}
    for name in G7_NAMES:
        if name in skip:
            continue
        index += 1
        base = 10000.0 * index
        bases[name] = base
        version = 2 * index - 1
        events += _rules(base, version, [name])
        events.append({"t_ms": base + 10, "ev": "case", "name": name, "rule_id": name})
        seen = None if name in uninjected else name
        v = px_version if px_version is not None else version
        if name.startswith("status"):
            channel = name[-1]
            route = "poll" if channel == "P" else "result"
            proxy.append(_px(base + 100, route=route, rule=seen, version=v, status=int(name[6:9])))
            log(name, 150, f"rest error ch={channel} kind=3 state=2", base)
        elif name == "timeout_P":
            proxy.append(_px(base + 100, rule=seen, version=v, done=base + 3100))
            log(name, 3100, "rest timeout ch=P kind=3 src=engine", base)
        elif name == "r_held":
            proxy.append(_px(base + 100, route="result", rule=seen, version=v, done=base + 4100))
            if held_mode == "ok":
                times = [base + 300 + 200 * step for step in range(19)]
            elif held_mode == "tail":
                times = [base + 300 + 200 * step for step in range(14)]  # el ultimo, en base+2900
            elif held_mode == "head":
                times = [base + 1000 + 200 * step for step in range(16)]
            else:
                times = []
            proxy += [_px(t, deliver=0, rule=None, version=v) for t in times]
        elif name.startswith("invalid"):
            proxy.append(_px(base + 100, rule=seen, version=v))
            log(name, 150, "rest invalid ch=P kind=3", base)
            if name == "invalid_all_P":
                proxy.append(_px(base + p_second, rule=seen, version=v))
                log(name, p_second + 50, "rest invalid ch=P kind=3", base)
                if valid_p:
                    # R22: respuestas validas de P (200 sin reescribir) que parten el tramo.
                    proxy += [_px(base + 1000 * k, rule=None, version=v) for k in range(1, 5)]
                if lease_lost:
                    log(name, 3200, "lease lost age_ms=3100", base)
        elif name.startswith("measure_"):
            if name in ("measure_no_args_P", "measure_args_empty_P"):
                op = f"m{index}"
                events.append({"t_ms": base + 50, "ev": "apply", "op_id": op, "session": "s",
                               "http_status": 200, "ttl_ms": 10000, "t_end_ms": base + 60})
                if measure_effect and name == "measure_no_args_P":
                    log(name, 400, f"effect step=retirar session=s op={op}", base)
            proxy.append(_px(base + 100, rule=seen, version=v))
        elif name == "late_cb":
            proxy.append(_px(base + 100, rule=seen, version=v, done=base + 8100))
            if late_line:
                log(name, 3100, "rest late ch=R kind=3", base)
            if late_change:
                events.append(_state(base + 2000, "s", "zz", "parcial"))
        if name not in no_empty:
            events += _rules(base + 5000, version + 1, [])
        events += _recov(base + 6000, f"rec{index}")
    for name, offset, text in extra:
        base = bases[name]
        lines.append(text.replace("@T", str(int(base + offset))))
    events.append({"t_ms": 10000.0 * (index + 2), "ev": "end", "status": "ok", "reason": ""})
    _write_jsonl(root / "samples" / "G7.jsonl", events)
    _write_jsonl(root / "samples" / "proxy.jsonl", proxy)
    _append(root / "logs" / "server_script.log", lines)
    if drop_client_log:
        (root / "logs" / "client_script.log").unlink()
    return root


def _g8(
    root,
    b_two_pairs=False,
    aborted=False,
    reuse_op=False,
    a_session="s1",
    dup_line=False,
    uninjected_b=False,
    skip_c=False,
    a_results=2,
    a_obs=1,
):
    root = _base(root, ["G8"])
    op_c = "op-1" if reuse_op else "c1"
    op_a = "op-1" if reuse_op else "a1"
    events = [{"t_ms": 100.0, "ev": "start", "scenario": "G8"}]
    events += _rules(50, 1, ["drop_a", "st503_b"])
    events += [
        {"t_ms": 200.0, "ev": "case", "name": "a", "session": a_session, "op_id": op_a, "rule_id": "drop_a"},
    ]
    events += [_state(300 + k, a_session, op_a, "observado") for k in range(a_obs)]
    events += [
        {"t_ms": 310.0 + 10 * k, "ev": "result_seen", "op_id": op_a, "status": "done", "reason": "", "dup": False}
        for k in range(a_results)
    ]
    events += [
        {"t_ms": 400.0, "ev": "case", "name": "b", "session": "s2", "op_id": "b1", "rule_id": "st503_b"},
        {"t_ms": 500.0, "ev": "result_seen", "op_id": "b1", "status": "done", "reason": "", "dup": False},
        {"t_ms": 600.0, "ev": "result_seen", "op_id": "b1", "status": "done", "reason": "", "dup": True},
    ]
    if not skip_c:
        events += [
            {"t_ms": 700.0, "ev": "case", "name": "c", "session": "s3", "op_id": op_c},
            _state(800, "s3", op_c, "observado"),
        ]
    events.append(
        {
            "t_ms": 900.0,
            "ev": "end",
            "status": "aborted" if aborted else "ok",
            "reason": "corte" if aborted else "",
        }
    )
    _write_jsonl(root / "samples" / "G8.jsonl", events)
    proxy = [_px(210, route="result", rule="drop_a")]
    if not uninjected_b:
        proxy.append(_px(410, route="result", rule="st503_b", status=503))
    _write_jsonl(root / "samples" / "proxy.jsonl", proxy)
    lines = [
        _eff("retirar", "s1", op_a, 250),
        _eff("anotar", "s1", op_a, 260),
        _eff("retirar", "s2", "b1", 450),
        _eff("anotar", "s2", "b1", 460),
        _eff("retirar", "s3", op_c, 750),
        _eff("anotar", "s3", op_c, 760),
    ]
    if b_two_pairs:
        lines += [_eff("retirar", "s2", "b1", 470), _eff("anotar", "s2", "b1", 480)]
    if dup_line:
        lines.append(_eff("anotar", "s1", op_a, 260))  # la misma linea otra vez (R8)
    _append(root / "logs" / "server_script.log", lines)
    return root


def _g9(
    root,
    slow=False,
    drop_server_log=False,
    negative=False,
    dup_ids=False,
    n_ops=100,
    effect_session="s",
    t_src=None,
):
    root = _base(root, ["G9"])
    events = [
        {"t_ms": 100.0, "ev": "start", "scenario": "G9"},
        {"t_ms": 150.0, "ev": "gap_reset", "confirmed": True},
    ]
    effects = []
    for index in range(n_ops):
        op = f"op{index:03d}"
        if dup_ids and index == 1:
            op = "op000"
        events.append({"t_ms": 200.0 + index, "ev": "mix_op", "op_id": op})
        apply_ms = 1000.0 + index * 10
        events.append(
            {
                "t_ms": apply_ms,
                "t_end_ms": apply_ms + 5,
                "ev": "apply",
                "session": "s",
                "op_id": op,
                "http_status": 200,
                "ttl_ms": 5000,
            }
        )
        observed_ms = apply_ms + (2000.0 if slow and index < 10 else 50.0)
        if negative and index == 5:
            observed_ms = apply_ms - 20.0
        state = _state(observed_ms, "s", op, "observado")
        if t_src:
            state["t_src"] = t_src
        events.append(state)
        effects.append(_eff("retirar", effect_session, op, int(apply_ms)))
        effects.append(_eff("anotar", effect_session, op, int(apply_ms) + 1))
    events.append({"t_ms": 5000.0, "ev": "end", "status": "ok", "reason": ""})
    _write_jsonl(root / "samples" / "G9.jsonl", events)
    _append(root / "logs" / "server_script.log", effects)
    if drop_server_log:
        (root / "logs" / "server_script.log").unlink()
    return root


def _two_rows(root, dirty=False, g2_aborted=False, g2_mismatch=False, key_hits=0, unreadable=None):
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
    g2 = [
        {"t_ms": 100.0, "ev": "start", "scenario": "G2"},
        {
            "t_ms": 200.0,
            "ev": "bridge",
            "session": "s",
            "server": {"conn": 1, "inst": "i", "epoch": 5, "lost": False},
            "client": {"conn": 1, "inst": "i", "epoch": 6 if g2_mismatch else 5, "lost": False},
            "catalog": {"complete": True, "n_classes": 12, "catalog_id": "c"},
        },
    ]
    if key_hits or unreadable is not None:
        scan = {"t_ms": 300.0, "ev": "key_scan", "files": [], "hits": key_hits}
        if unreadable is not None:
            scan["unreadable"] = unreadable
        g2.append(scan)
    g2.append(
        {
            "t_ms": 400.0,
            "ev": "end",
            "status": "aborted" if g2_aborted else "ok",
            "reason": "corte" if g2_aborted else "",
        }
    )
    _write_jsonl(root / "samples" / "G2.jsonl", g2)
    _write_jsonl(
        root / "samples" / "proxy.jsonl",
        [_px(90, route="hello", req_bytes=3000, done=120), _px(140, route="catalog", req_bytes=3200, done=180)],
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

    def test_fail_script_error_formato_real(self):
        # Formato real del motor (humo G1 en diag, 15-nov): "SCRIPT" y "(E)" van separados por varios espacios.
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            _append(Path(root) / "logs" / "server_script.log",
                    ["12:25:27.801   SCRIPT    (E): NULL pointer to instance DSBX_Peer.c(412)"])
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def test_fail_exit_leak_sin_shutdown(self):
        # Sin linea shutdown previa no hay cota: la fuga cuenta como error.
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            _append(Path(root) / "logs" / "server_script.log",
                    ["12:25:27.801   SCRIPT    (E): Leaked 'DSBX_Callback' script instance (2x)!"])
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def _leak(self, tmp, lines, rpt=False):
        root = _g1(tmp)
        _append(Path(root) / "logs" / "server_script.log", lines)
        if rpt:
            _append(Path(root) / "logs" / "server.RPT", lines)
        return EVAL.evaluate(root)

    SHUTDOWN5 = "12:50:01.008  SCRIPT       : [DSBX] shutdown role=server created_n=5 inflight_p=1 inflight_r=0"

    def test_pass_exit_leak_dentro_de_cota(self):
        # Medido en partida (15-nov): el motor retiene todo RestCallback; N = created_n.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = self._leak(tmp, [self.SHUTDOWN5,
                                       "12:50:02.841   SCRIPT    (E): Leaked 'DSBX_Callback' script instance (5x)!"], rpt=True)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")
            self.assertEqual(len(verdict["rows"]["G1"]["metrics"]["exit_leak_cb"]), 2)

    def test_pass_exit_leak_rpt_cliente_sin_lineas_dsbx(self):
        # Como en partida: el RPT del cliente trae la fuga pero no las lineas [DSBX]; la cota sale del script log.
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            leak = "12:49:58.991   SCRIPT    (E): Leaked 'DSBX_Callback' script instance (1x)!"
            _append(Path(root) / "logs" / "client_script.log",
                    ["12:49:58.168  SCRIPT       : [DSBX] shutdown role=client created_n=1 inflight_p=1 inflight_r=0", leak])
            _append(Path(root) / "logs" / "client.RPT", [leak])
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")

    def test_fail_exit_leak_rpt_sobre_cota_del_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            _append(Path(root) / "logs" / "client_script.log",
                    ["12:49:58.168  SCRIPT       : [DSBX] shutdown role=client created_n=1 inflight_p=1 inflight_r=0"])
            _append(Path(root) / "logs" / "client.RPT",
                    ["12:49:58.991   SCRIPT    (E): Leaked 'DSBX_Callback' script instance (2x)!"])
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def test_fail_exit_leak_sobre_cota(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = self._leak(tmp, [self.SHUTDOWN5,
                                       "12:50:02.841   SCRIPT    (E): Leaked 'DSBX_Callback' script instance (6x)!"])
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def test_fail_exit_leak_otra_clase(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = self._leak(tmp, [self.SHUTDOWN5,
                                       "12:50:02.841   SCRIPT    (E): Leaked 'DSBX_Peer' script instance (1x)!"])
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def test_fail_exit_leak_antes_del_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = self._leak(tmp, ["12:50:00.000   SCRIPT    (E): Leaked 'DSBX_Callback' script instance (1x)!",
                                       self.SHUTDOWN5])
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def test_fail_exit_leak_negativo(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = self._leak(tmp, [self.SHUTDOWN5,
                                       "12:50:02.841   SCRIPT    (E): Leaked 'DSBX_Callback' script instance (-2x)!"])
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "FALLA")

    def test_pass_error_ajeno_formato_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            _append(Path(root) / "logs" / "client.RPT",
                    ["12:25:23.789   SCRIPT    (E): Leaked 'BunkerBroadcastManager' script instance (1x)!"])
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")

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


class TestR2LogsFinales(unittest.TestCase):
    """R2: sin `fake`, logs_ready.json no final deja todas las filas INCONCLUSO."""

    def test_sin_logs_ready(self):
        # El evaluador anterior no miraba logs_ready.json: G1 daba PASA.
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            (root / "logs_ready.json").unlink()
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "INCONCLUSO")
            self.assertIn("logs no finales", verdict["rows"]["G1"]["reason"])
            self.assertEqual(verdict["aggregate"], "INCONCLUSO")

    def test_all_closed_falso(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            _write_json(root / "logs_ready.json", {"all_closed": False})
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "INCONCLUSO")

    def test_all_closed_no_booleano(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            _write_json(root / "logs_ready.json", {"all_closed": "true"})
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "INCONCLUSO")

    def test_todas_las_filas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _two_rows(tmp)
            (root / "logs_ready.json").unlink()
            verdict = EVAL.evaluate(root)
            for gid in ("G1", "G2"):
                self.assertEqual(verdict["rows"][gid]["verdict"], "INCONCLUSO")
                self.assertIn("logs no finales", verdict["rows"][gid]["reason"])

    def test_fake_no_lo_exige(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g2(tmp, fake=True)
            (root / "logs_ready.json").unlink()
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "PASA")


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

    def test_pass_c_con_efectos(self):
        # D-P2: el caso c ejecuta sus efectos con la revision reescrita; el criterio es el estado.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, c_effects=True))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "PASA")

    def test_pass_sin_recuperacion_tras_a_y_b(self):
        # P-08: la recuperacion va tras la inyeccion (c); a y b no inyectan nada.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, recovery_ab=False))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "PASA")

    def test_r20_recovery_fallida_seguida_de_otra_que_llega(self):
        # R20: la primera recovery acaba en conexion_perdida, la segunda llega a observado: vale. Antes solo
        # se miraba la primera y daba FALLA.
        with tempfile.TemporaryDirectory() as tmp:
            root = _g3(tmp, recovery_c=False)
            _add_events(
                root / "samples" / "G3.jsonl",
                [
                    {"t_ms": 1300.0, "ev": "recovery", "op_id": "rc1"},
                    _state(1350, "s2", "rc1", "fallido", "conexion_perdida"),
                    {"t_ms": 1400.0, "ev": "recovery", "op_id": "rc2"},
                    _state(1500, "s2", "rc2", "observado"),
                ],
            )
            row = EVAL.evaluate(root)["rows"]["G3"]
            self.assertEqual(row["verdict"], "PASA", row["reason"])
            self.assertEqual(row["metrics"]["cases"]["c"]["recovery_ms"], 400.0)

    def test_r20_todas_las_recovery_fallidas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g3(tmp, recovery_c=False)
            _add_events(
                root / "samples" / "G3.jsonl",
                [
                    {"t_ms": 1300.0, "ev": "recovery", "op_id": "rc1"},
                    _state(1350, "s2", "rc1", "fallido", "conexion_perdida"),
                    {"t_ms": 1400.0, "ev": "recovery", "op_id": "rc2"},
                    _state(1450, "s2", "rc2", "fallido", "conexion_perdida"),
                ],
            )
            row = EVAL.evaluate(root)["rows"]["G3"]
            self.assertEqual(row["verdict"], "FALLA")
            self.assertIn("c: recovery sin observado", row["reason"])

    def test_r20_observado_de_otra_sesion_no_vale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g3(tmp, recovery_c=False)
            _add_events(
                root / "samples" / "G3.jsonl",
                [
                    {"t_ms": 1300.0, "ev": "recovery", "op_id": "rc1", "session": "s2"},
                    _state(1350, "sX", "rc1", "observado"),
                ],
            )
            row = EVAL.evaluate(root)["rows"]["G3"]
            self.assertEqual(row["verdict"], "FALLA")

    def test_r20_observado_pasados_60_s_desde_el_ancla(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g3(tmp, recovery_c=False)
            _add_events(
                root / "samples" / "G3.jsonl",
                [
                    {"t_ms": 1300.0, "ev": "recovery", "op_id": "rc1"},
                    _state(62000, "s2", "rc1", "observado"),
                ],
            )
            row = EVAL.evaluate(root)["rows"]["G3"]
            self.assertEqual(row["verdict"], "FALLA")
            self.assertIn("> 60 s", row["reason"])

    def test_fail_sin_recuperacion_tras_c(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, recovery_c=False))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "FALLA")

    def test_r8_linea_effect_duplicada_cuenta(self):
        # R8: la misma linea effect (mismo tick) dos veces son dos ejecuciones. Antes se deduplicaba por
        # tick y G3 daba PASA con retirar=1.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, dup_effect=True))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "FALLA")
            self.assertIn("retirar=2", verdict["rows"]["G3"]["reason"])

    def test_r5_efectos_de_otra_sesion_no_valen(self):
        # R5: la op a1 es de la sesion s1; sus efectos con session=s9 no son suyos. Antes se casaba por op.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, a_effect_session="s9"))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "FALLA")

    def test_r5_case_sin_session_es_evidencia_invalida(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g3(tmp)
            path = root / "samples" / "G3.jsonl"
            lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for ev in lines:
                if ev.get("ev") == "case" and ev["name"] == "a":
                    del ev["session"]
            _write_jsonl(path, lines)
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")
            self.assertIn("sin session", verdict["rows"]["G3"]["reason"])

    def test_r7_falta_un_caso(self):
        # R7: sin el caso b la fila es INCONCLUSO; antes se evaluaban los casos presentes y daba PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, drop_case="b"))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")
            self.assertIn("cobertura incompleta", verdict["rows"]["G3"]["reason"])

    def test_r7_caso_repetido(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, dup_case="a"))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")
            self.assertIn("repetido a", verdict["rows"]["G3"]["reason"])

    def test_r9_inyeccion_sin_linea_del_proxy(self):
        # R9: la regla esta confirmada pero el proxy no la vio disparar. Antes: PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, px_rule="otra"))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")
            self.assertIn("inyección no observada", verdict["rows"]["G3"]["reason"])

    def test_r9_caso_sin_rule_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, c_rule=False))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")
            self.assertIn("sin rule_id", verdict["rows"]["G3"]["reason"])

    def test_r9_linea_de_version_anterior(self):
        # La version confirmada para el caso es la 1; una linea con rules_version 0 no la acredita.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g3(tmp, px_version=0))
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")

    def test_r9_linea_anterior_al_rules_active(self):
        # La linea lleva la version buena pero cae a t=150, antes del rules_active (t=201).
        with tempfile.TemporaryDirectory() as tmp:
            root = _g3(tmp, px_t=150)
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")

    def test_r9_multiples_rule_ids_todos_deben_verse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g3(tmp)
            path = root / "samples" / "G3.jsonl"
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            for ev in events:
                if ev.get("ev") == "case" and ev["name"] == "c":
                    del ev["rule_id"]
                    ev["rule_ids"] = ["rewrite", "nunca"]
            _write_jsonl(path, events)
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G3"]["verdict"], "INCONCLUSO")


class TestG4(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "PASA", verdict["rows"]["G4"]["reason"])

    def test_fail_key_scan_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, hits=1))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "FALLA")
            self.assertEqual(verdict["aggregate"], "FALLA")
            self.assertEqual(verdict["reason"], "clave en los logs")

    def test_inconclusive_missing_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, drop_inventory=True))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "INCONCLUSO")

    def test_fail_effect_en_la_ventana(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, effect_in_window=True))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "FALLA")

    def test_r10_los_efectos_de_la_recuperacion_quedan_fuera(self):
        # R10: un efecto de la orden de recuperacion dentro de la ventana (o su tolerancia) no es de la
        # inyeccion. Quitar la exclusion lo convierte en FALLA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, recovery_effect_in_window=True))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "PASA", verdict["rows"]["G4"]["reason"])

    def test_r5_efecto_de_la_orden_vieja_en_su_sesion(self):
        # El efecto de b1 con la sesion vieja s0 tambien es de la orden stale: FALLA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, b_effect_old_session=True))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "FALLA")

    def test_r5_efecto_de_otra_sesion_no_es_de_la_orden(self):
        # Un efecto b1 de la sesion s7 es otra orden (el backend reiniciado vuelve a b1).
        with tempfile.TemporaryDirectory() as tmp:
            root = _g4(tmp)
            _append(root / "logs" / "server_script.log", [_eff("retirar", "s7", "b1", 1500)])
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "PASA", verdict["rows"]["G4"]["reason"])

    def test_r3_inventario_completo_sin_mayusculas(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, scan_files="upper"))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "PASA", verdict["rows"]["G4"]["reason"])

    def test_r3_fichero_del_inventario_sin_escanear(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, scan_files="missing_one"))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "FALLA")
            self.assertIn("no cubre", verdict["rows"]["G4"]["reason"])

    def test_r3_mismo_nombre_en_otra_carpeta_no_cubre(self):
        # La cobertura es por ruta, no por nombre: el evaluador anterior aceptaba el basename.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, scan_files="other_dir_same_name"))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "FALLA")

    def test_r3_inventario_con_formato_viejo_es_ilegible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g4(tmp)
            _write_json(root / "logs" / "inventory.json", {"server": ["a.log"], "client": ["b.log"]})
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "INCONCLUSO")

    def test_r7_falta_un_caso(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g4(tmp)
            path = root / "samples" / "G4.jsonl"
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            events = [ev for ev in events if not (ev.get("ev") == "case" and ev["name"] == "c")]
            _write_jsonl(path, events)
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "INCONCLUSO")
            self.assertIn("falta c", verdict["rows"]["G4"]["reason"])

    def test_r9_regla_del_caso_b_sin_disparo(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g4(tmp, no_proxy_rule="stale_rw"))
            self.assertEqual(verdict["rows"]["G4"]["verdict"], "INCONCLUSO")
            self.assertIn("inyección no observada", verdict["rows"]["G4"]["reason"])


class TestG5(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "PASA", verdict["rows"]["G5"]["reason"])

    def test_fail_b4000_with_anotar(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, b4000_anotar=True))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "FALLA")

    def test_inconclusive_missing_server_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, drop_server_log=True))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "INCONCLUSO")

    def test_fail_client_sin_lease_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, client_lost=False))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "FALLA")
            self.assertIn("a4500/client", verdict["rows"]["G5"]["reason"])

    def test_r11_solo_cuentan_las_rutas_de_p(self):
        # R11: las respuestas 200 del canal R (route result) no rellenan el hueco de P. Antes valia
        # cualquier 200 al peer y G5 a2500 daba PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, filler=True))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "FALLA")
            self.assertIn("a2500/server: hueco", verdict["rows"]["G5"]["reason"])

    def test_r7_falta_a4500_del_cliente(self):
        # R7: a4500 hay que correrlo en servidor y en cliente. Sin el del cliente: INCONCLUSO.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, skip=("a4500", "client")))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "INCONCLUSO")
            self.assertIn("a4500/client", verdict["rows"]["G5"]["reason"])

    def test_r7_sin_gap_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g5(tmp)
            path = root / "samples" / "G5.jsonl"
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            events = [ev for ev in events if ev.get("ev") != "gap_reset"]
            _write_jsonl(path, events)
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "INCONCLUSO")
            self.assertIn("gap_reset", verdict["rows"]["G5"]["reason"])

    def test_r9_inyeccion_no_observada(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, uninjected=True))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "INCONCLUSO")
            self.assertIn("inyección no observada", verdict["rows"]["G5"]["reason"])

    def test_r5_efectos_de_b2500_de_otra_sesion(self):
        # La op de b2500 es de la sesion s; sus efectos con session=z no cuentan: FALLA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g5(tmp, b2500_session="z"))
            self.assertEqual(verdict["rows"]["G5"]["verdict"], "FALLA")


class TestG6(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "PASA", verdict["rows"]["G6"]["reason"])

    def test_fail_late_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp, late_done=True))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "FALLA")

    def test_inconclusive_without_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp, no_result=True))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "INCONCLUSO")

    def test_r12_preparacion_invalida(self):
        # R12: cada violacion deja la fila INCONCLUSO. El evaluador anterior daba PASA a todas
        # (el resultado es rejected/expired a 4100 en todas).
        casos = {
            "T_d > T_s": {"T_d_ms": 2100.0},
            "T_s - T_d > 300": {"T_d_ms": 1000.0},
            "T_e - T_s < 1900": {"T_e_ms": 3800.0},
            "D <= T_s": {"D_ms": 2000.0},
            "D >= T_e": {"D_ms": 4500.0},
            "T_s >= T_e": {"T_s_ms": 4000.0, "T_d_ms": 3900.0, "D_ms": 4000.0},
        }
        for nombre, order in casos.items():
            with self.subTest(nombre), tempfile.TemporaryDirectory() as tmp:
                verdict = EVAL.evaluate(_g6(tmp, order=order))
                self.assertEqual(verdict["rows"]["G6"]["verdict"], "INCONCLUSO")
                self.assertIn("preparación inválida", verdict["rows"]["G6"]["reason"])

    def test_r12_limites_validos(self):
        # T_s - T_d = 300 y T_e - T_s = 1900 son validos (cotas incluidas), y T_d = T_s tambien.
        for order in ({"T_d_ms": 1700.0}, {"T_e_ms": 3900.0}, {"T_d_ms": 2000.0}):
            with self.subTest(order), tempfile.TemporaryDirectory() as tmp:
                verdict = EVAL.evaluate(_g6(tmp, order=order))
                self.assertEqual(verdict["rows"]["G6"]["verdict"], "PASA", verdict["rows"]["G6"]["reason"])

    def test_r12_apply_con_otro_ttl(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp, ttl=3000))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "INCONCLUSO")
            self.assertIn("ttl_ms 1500", verdict["rows"]["G6"]["reason"])

    def test_r12_sin_apply_de_la_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g6(tmp)
            path = root / "samples" / "G6.jsonl"
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            events = [ev for ev in events if ev.get("ev") != "apply"]
            _write_jsonl(path, events)
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "INCONCLUSO")

    def test_r7_sin_clock_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp, drop_clock_run=True))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "INCONCLUSO")
            self.assertIn("falta clock_run", verdict["rows"]["G6"]["reason"])

    def test_r9_g6_deliver_sin_disparo(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp, px_rule="otra"))
            self.assertEqual(verdict["rows"]["G6"]["verdict"], "INCONCLUSO")
            self.assertIn("inyección no observada", verdict["rows"]["G6"]["reason"])

    def test_medidas_del_reloj(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g6(tmp))
            metrics = verdict["rows"]["G6"]["metrics"]
            self.assertEqual(metrics["clock_n"], 3)
            self.assertEqual(metrics["clock_pause_t_step_ms"], 2000)


class TestG7(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "PASA", verdict["rows"]["G7"]["reason"])

    def test_fail_r_held_sin_polls(self):
        # Sin ningun poll de mantenimiento durante 4000 ms. Antes: INCONCLUSO (menos de dos polls).
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, held_mode="none"))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")

    def test_inconclusive_missing_client_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, drop_client_log=True))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")

    def test_h08_orden_sin_args_rechazada_sin_efecto(self):
        # Ensayo diag del 15-nov: una orden sin args se rechaza (bad_args) con el poll valido; es medida.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "PASA")
            cases = verdict["rows"]["G7"]["metrics"]["cases"]
            self.assertEqual(sorted(cases["measure_no_args_P"]["op_effects"].values()), [0])

    def test_h08_efecto_en_una_orden_rechazada_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, measure_effect=True))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")
            self.assertIn("orden rechazada", verdict["rows"]["G7"]["reason"])

    def test_pass_tick_desfasado_del_reloj_del_arnes(self):
        # Brief v1.4, H-04: en partida tick_ms (GetTickTime) va por ~2e5 y el arnes por ~8e7.
        # La ventana se juzga por la hora de pared de la linea, no por su tick_ms.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, tick_offset=214000))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "PASA", verdict["rows"]["G7"]["reason"])
            self.assertEqual(verdict["rows"]["G7"]["metrics"]["cases"]["invalid_no_ok_P"]["invalid"], 1)

    def test_fail_linea_fuera_por_hora_aunque_su_tick_caiga_dentro(self):
        # tick_ms cae en la ventana de invalid_no_ok_P, pero la linea se escribio a t=500.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, wall_override={"invalid_no_ok_P": 500}))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")

    def test_inconclusive_sin_ancla_de_hora(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g7(tmp)
            manifest = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
            del manifest["t0_wall"]
            _write_json(Path(root) / "manifest.json", manifest)
            verdict = EVAL.evaluate(root)
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")

    def test_r7_falta_un_caso_status(self):
        # R7: sin status413_R la fila es INCONCLUSO; antes los casos presentes daban PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, skip=("status413_R",)))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")
            self.assertIn("falta status413_R", verdict["rows"]["G7"]["reason"])

    def test_r7_falta_una_medida(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, skip=("measure_args_empty_P",)))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")

    def test_r9_r_held_sin_disparo_en_el_proxy(self):
        # r_held no tiene su linea con rule_id en el proxy. Antes (polls de mantenimiento sueltos): PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, uninjected=("r_held",)))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")
            self.assertIn("inyección no observada: r_held", verdict["rows"]["G7"]["reason"])

    def test_r9_late_cb_sin_disparo(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, uninjected=("late_cb",)))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")

    def test_r21_medida_sin_disparo_es_inconcluso(self):
        # R21: status* y measure_* tambien exigen la inyeccion observada. Antes anotaban
        # injection_observed=False y la fila pasaba; ahora es INCONCLUSO.
        for name in ("status400_P", "measure_ok1_P"):
            with tempfile.TemporaryDirectory() as tmp:
                row = EVAL.evaluate(_g7(tmp, uninjected=(name,)))["rows"]["G7"]
                self.assertEqual(row["verdict"], "INCONCLUSO", name)
                self.assertIn("inyección no observada", row["reason"])
                self.assertIn(name, row["reason"])

    def test_r21_medida_con_disparo_anota_lo_medido(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g7(tmp))["rows"]["G7"]
            self.assertEqual(row["verdict"], "PASA", row["reason"])
            self.assertIs(row["metrics"]["cases"]["status400_P"]["injection_observed"], True)
            self.assertEqual(row["metrics"]["cases"]["status400_P"]["state"], 2)

    def test_r9_version_antigua_no_acredita(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, px_version=0))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")

    def test_r10_efecto_tras_el_fin_de_la_inyeccion(self):
        # R10: un efecto a base+5400, despues del rules_active vacio (base+5010) mas tolerancia, no es de la
        # inyeccion de invalid_no_ok_P. Con la ventana anterior (hasta el caso siguiente) daba FALLA.
        with tempfile.TemporaryDirectory() as tmp:
            extra = [("invalid_no_ok_P", 5400, _eff("retirar", "s", "zz", "@T"))]
            verdict = EVAL.evaluate(_g7(tmp, extra=extra))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "PASA", verdict["rows"]["G7"]["reason"])

    def test_r10_efecto_dentro_de_la_ventana(self):
        with tempfile.TemporaryDirectory() as tmp:
            extra = [("invalid_no_ok_P", 2000, _eff("retirar", "s", "zz", "@T"))]
            verdict = EVAL.evaluate(_g7(tmp, extra=extra))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")
            self.assertIn("invalid_no_ok_P: effect en la ventana", verdict["rows"]["G7"]["reason"])

    def test_r10_efecto_de_la_recuperacion_en_la_tolerancia(self):
        # A base+5100 (dentro de los 250 ms de tolerancia) pero de la op de recuperacion (rec{k}): fuera.
        with tempfile.TemporaryDirectory() as tmp:
            index = G7_NAMES.index("invalid_no_ok_P") + 1
            extra = [("invalid_no_ok_P", 5100, _eff("retirar", "s", f"rec{index}", "@T"))]
            verdict = EVAL.evaluate(_g7(tmp, extra=extra))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "PASA", verdict["rows"]["G7"]["reason"])
            extra = [("invalid_no_ok_P", 5100, _eff("retirar", "s", "otra", "@T"))]
            verdict = EVAL.evaluate(_g7(tmp + "/b", extra=extra))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")

    def test_r10_sin_rules_vacio_es_inconcluso(self):
        # Sin el `rules` vacio no hay fin de ventana: la fila es INCONCLUSO, no una ventana inventada.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, no_empty=("invalid_no_ok_P",)))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "INCONCLUSO")
            self.assertIn("rules_active vacio", verdict["rows"]["G7"]["reason"])

    def test_r10_las_medidas_sin_rules_vacio_usan_el_caso_siguiente(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, no_empty=("status400_P",)))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "PASA", verdict["rows"]["G7"]["reason"])

    def test_r11_r_held_hueco_final_hasta_la_liberacion(self):
        # R11: el ultimo poll es a base+2900 y el acuse se libera a base+4100: hueco de 1200 ms.
        # Los huecos entre polls son de 200 ms, que es lo unico que miraba el evaluador anterior.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, held_mode="tail"))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")
            self.assertIn("r_held: hueco > 750", verdict["rows"]["G7"]["reason"])

    def test_r11_r_held_hueco_inicial_desde_el_disparo(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, held_mode="head"))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")

    def test_r11_r_held_mide_hasta_t_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g7(tmp))["rows"]["G7"]
            self.assertEqual(row["metrics"]["cases"]["r_held"]["max_gap_ms"], 200)
            self.assertEqual(row["metrics"]["cases"]["r_held"]["polls"], 19)

    def test_invalid_all_sin_lease_lost(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, lease_lost=False))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")
            self.assertIn("sin lease lost", verdict["rows"]["G7"]["reason"])

    def test_r22_tramo_sin_validas_mayor_que_lease_exige_lease_lost(self):
        # R22: el tramo sale del proxy, no de las lineas rest invalid. Las dos lineas invalid distan 1500 ms
        # (el calculo anterior daba PASA sin lease lost), pero el proxy no ve ninguna respuesta valida de
        # P en 4900 ms.
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g7(tmp, p_second=1600, lease_lost=False))["rows"]["G7"]
            self.assertEqual(row["verdict"], "FALLA")
            self.assertIn("invalid_all_P: sin lease lost", row["reason"])
            self.assertGreater(row["metrics"]["cases"]["invalid_all_P"]["invalid_gap_ms"], 3000)

    def test_r22_con_lease_lost_pasa(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g7(tmp, p_second=1600))["rows"]["G7"]
            self.assertEqual(row["verdict"], "PASA", row["reason"])

    def test_r22_ventana_que_no_supera_el_lease_es_inconcluso(self):
        # R22: respuestas validas de P cada 1000 ms: el mayor tramo no llega a lease_ms (3000). Antes, con
        # las lineas invalid a 3500 ms de distancia, se exigia lease lost (FALLA sin el) o pasaba.
        for lease_lost in (True, False):
            with tempfile.TemporaryDirectory() as tmp:
                row = EVAL.evaluate(_g7(tmp, valid_p=True, lease_lost=lease_lost))["rows"]["G7"]
                self.assertEqual(row["verdict"], "INCONCLUSO", row["reason"])
                self.assertIn("la ventana no superó el lease", row["reason"])

    def test_r24_late_cb_con_effect_en_la_ventana(self):
        # R24: una effect en la ventana de late_cb (sin cambio de op_state) tumba el caso.
        with tempfile.TemporaryDirectory() as tmp:
            extra = [("late_cb", 2000, _eff("retirar", "s", "zz", "@T"))]
            row = EVAL.evaluate(_g7(tmp, extra=extra))["rows"]["G7"]
            self.assertEqual(row["verdict"], "FALLA")
            self.assertIn("late_cb: effect en la ventana", row["reason"])

    def test_r24_late_cb_effect_de_la_recuperacion_no_cuenta(self):
        # late_cb es el caso 21: su recuperacion es rec21 (sesion s).
        with tempfile.TemporaryDirectory() as tmp:
            extra = [("late_cb", 2000, _eff("retirar", "s", "rec21", "@T"))]
            row = EVAL.evaluate(_g7(tmp, extra=extra))["rows"]["G7"]
            self.assertEqual(row["verdict"], "PASA", row["reason"])

    def test_late_cb_sin_invocacion_se_anota(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g7(tmp, late_line=False))["rows"]["G7"]
            self.assertEqual(row["verdict"], "PASA", row["reason"])
            self.assertIn("inconcluso", row["metrics"]["cases"]["late_cb"]["late_cb"])

    def test_late_cb_con_cambio_de_estado(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g7(tmp, late_change=True))
            self.assertEqual(verdict["rows"]["G7"]["verdict"], "FALLA")
            self.assertIn("late_cb", verdict["rows"]["G7"]["reason"])

    def test_timeout_p_plazo_efectivo(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g7(tmp))["rows"]["G7"]
            self.assertEqual(row["metrics"]["cases"]["timeout_P"]["timeout_ms"], 3000)


class TestH09FireLine(unittest.TestCase):
    """Brief v1.5, H-09: la regla cuenta por la version con que el proxy etiqueta la linea y por cuando
    se sirvio, no por el t_ms con que el orquestador anota rules_active (retraso de sondeo)."""

    def _ctx(self):
        return {"manifest": {"fake": False}, "scenario": [
            {"t_ms": 100.0, "ev": "rules", "version": 3, "rule_ids": ["r"]},
            {"t_ms": 140.0, "ev": "rules_active", "version": 3},
            {"t_ms": 150.0, "ev": "case", "name": "c", "rule_id": "r"},
        ]}

    def test_long_poll_recibido_antes_y_servido_despues(self):
        ctx = self._ctx()
        proxy = [{"t_ms": 110.0, "t_done_ms": 160.0, "rule_id": "r", "rules_version": 3}]
        self.assertIsNotNone(EVAL._fire_line(ctx, ctx["scenario"][2], "r", proxy))

    def test_version_vieja_no_cuenta(self):
        ctx = self._ctx()
        proxy = [{"t_ms": 110.0, "t_done_ms": 160.0, "rule_id": "r", "rules_version": 2}]
        self.assertIsNone(EVAL._fire_line(ctx, ctx["scenario"][2], "r", proxy))

    def test_r18_rule_version_manda_sobre_rules_version(self):
        # R18: la linea trae rules_version 3 (la vigente al recibirla) pero la regla actuo con la 2: no
        # acredita la version 3. Antes se leia rules_version y contaba.
        ctx = self._ctx()
        proxy = [{"t_ms": 110.0, "t_done_ms": 160.0, "rule_id": "r", "rules_version": 3, "rule_version": 2}]
        self.assertIsNone(EVAL._fire_line(ctx, ctx["scenario"][2], "r", proxy))

    def test_r18_rule_version_nueva_acredita_aunque_rules_version_sea_vieja(self):
        ctx = self._ctx()
        proxy = [{"t_ms": 110.0, "t_done_ms": 160.0, "rule_id": "r", "rules_version": 2, "rule_version": 3}]
        self.assertIsNotNone(EVAL._fire_line(ctx, ctx["scenario"][2], "r", proxy))

    def test_r18_sin_rule_version_se_usa_rules_version(self):
        ctx = self._ctx()
        proxy = [{"t_ms": 110.0, "t_done_ms": 160.0, "rule_id": "r", "rules_version": 3, "rule_version": None}]
        self.assertIsNotNone(EVAL._fire_line(ctx, ctx["scenario"][2], "r", proxy))

    def test_servida_antes_de_escribir_la_version_no_cuenta(self):
        ctx = self._ctx()
        proxy = [{"t_ms": 80.0, "t_done_ms": 90.0, "rule_id": "r", "rules_version": 3}]
        self.assertIsNone(EVAL._fire_line(ctx, ctx["scenario"][2], "r", proxy))


class TestLineClock(unittest.TestCase):
    def _ctx(self, fake=False, start_wall=None):
        scenario = [{"t_ms": 5000.0, "ev": "start", "scenario": "G7"}]
        if start_wall is not None:
            scenario[0]["wall"] = start_wall
        return {"manifest": {"fake": fake, "t0_ms": 1000.0, "t0_wall": "23:59:59.000"}, "scenario": scenario}

    def test_cruce_de_medianoche(self):
        ev = {"wall_ms": EVAL._wall_ms("00:00:01.000"), "tick_ms": 7}
        self.assertEqual(EVAL._line_t(self._ctx(), ev), 3000.0)

    def test_ancla_del_start_antes_que_la_del_manifest(self):
        ev = {"wall_ms": EVAL._wall_ms("12:00:01.500"), "tick_ms": 7}
        self.assertEqual(EVAL._line_t(self._ctx(start_wall="12:00:00.000"), ev), 6500.0)

    def test_fake_usa_tick(self):
        ev = {"wall_ms": None, "tick_ms": 4242}
        self.assertEqual(EVAL._line_t(self._ctx(fake=True), ev), 4242)

    def test_linea_sin_hora(self):
        self.assertIsNone(EVAL._line_t(self._ctx(), {"wall_ms": None, "tick_ms": 1}))


class TestG8(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "PASA", verdict["rows"]["G8"]["reason"])

    def test_r23_a_con_un_solo_result_seen(self):
        # R23: el acuse perdido y la repeticion son dos result_seen. Con uno, FALLA (antes PASA).
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g8(tmp, a_results=1))["rows"]["G8"]
            self.assertEqual(row["verdict"], "FALLA")
            self.assertIn("a: menos de 2 result_seen", row["reason"])

    def test_r23_a_sin_transicion_a_observado(self):
        # R23: exactamente una transicion a observado. Con cero, FALLA (antes PASA).
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g8(tmp, a_obs=0))["rows"]["G8"]
            self.assertEqual(row["verdict"], "FALLA")
            self.assertIn("a: 0 transiciones a observado", row["reason"])

    def test_r23_a_con_dos_observado(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g8(tmp, a_obs=2))["rows"]["G8"]
            self.assertEqual(row["verdict"], "FALLA")
            self.assertIn("a: 2 transiciones a observado", row["reason"])

    def test_r23_a_aborted_es_inconcluso(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g8(tmp, aborted=True, a_results=1))["rows"]["G8"]
            self.assertEqual(row["verdict"], "INCONCLUSO")

    def test_fail_b_two_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, b_two_pairs=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "FALLA")

    def test_inconclusive_aborted(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, aborted=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "INCONCLUSO")

    def test_r5_mismo_op_id_en_sesiones_distintas(self):
        # R5: el backend reiniciado vuelve a op-1. a y c usan "op-1" en sesiones s1 y s3: cada una tiene su
        # pareja. Casando solo por op, el evaluador anterior veia 2 sesiones y daba FALLA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, reuse_op=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "PASA", verdict["rows"]["G8"]["reason"])

    def test_r5_session_del_caso_distinta_de_la_del_efecto(self):
        # El caso a dice sesion s9; las parejas son de s1: no son suyas. Antes se casaba por op y daba PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, a_session="s9"))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "FALLA")

    def test_r8_linea_duplicada(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, dup_line=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "FALLA")
            self.assertIn("anotar=2", verdict["rows"]["G8"]["reason"])

    def test_r7_falta_c(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, skip_c=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "INCONCLUSO")

    def test_r9_b_sin_disparo(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g8(tmp, uninjected_b=True))
            self.assertEqual(verdict["rows"]["G8"]["verdict"], "INCONCLUSO")
            self.assertIn("inyección no observada: b", verdict["rows"]["G8"]["reason"])


class TestG9(unittest.TestCase):
    def test_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "PASA", verdict["rows"]["G9"]["reason"])

    def test_fail_p95(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, slow=True))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "FALLA")

    def test_inconclusive_missing_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, drop_server_log=True))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "INCONCLUSO")

    def test_r6_latencia_negativa(self):
        # R6: un op_state anterior a su apply es evidencia invalida. Antes la latencia negativa entraba en el
        # p95 y G9 daba PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, negative=True))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "INCONCLUSO")
            self.assertIn("evidencia inválida", verdict["rows"]["G9"]["reason"])

    def test_r6_t_src_lectura_se_anota(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = EVAL.evaluate(_g9(tmp, t_src="lectura"))["rows"]["G9"]
            self.assertEqual(row["verdict"], "PASA", row["reason"])
            self.assertEqual(row["metrics"]["op_state_t_lectura"], 100)

    def test_r7_menos_de_cien_op(self):
        # R7: 99 mix_op es cobertura incompleta (INCONCLUSO). Antes era FALLA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, n_ops=99))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "INCONCLUSO")
            self.assertIn("cobertura incompleta", verdict["rows"]["G9"]["reason"])

    def test_r7_op_id_repetidos(self):
        # Cien mix_op pero con un op_id repetido: no son cien ops distintas.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, dup_ids=True))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "INCONCLUSO")

    def test_r5_efectos_de_otra_sesion(self):
        # Las cien ops son de la sesion s; sus efectos dicen session=z: ninguna tiene pareja. Antes: PASA.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_g9(tmp, effect_session="z"))
            self.assertEqual(verdict["rows"]["G9"]["verdict"], "FALLA")
            self.assertIn("100 ops sin pareja", verdict["rows"]["G9"]["reason"])


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

    def test_r26_unreadable_deja_el_agregado_inconcluso(self):
        # R26: filas PASA pero un key_scan con ficheros ilegibles: el agregado es INCONCLUSO (antes PASA).
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, unreadable=["C:/prof/server/script_1.log"]))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "PASA")
            self.assertEqual(verdict["aggregate"], "INCONCLUSO")
            self.assertEqual(verdict["reason"], "escaneo incompleto")

    def test_r26_unreadable_vacio_no_cuenta(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, unreadable=[]))
            self.assertEqual(verdict["aggregate"], "PASA")

    def test_r26_una_fila_falla_sigue_siendo_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, g2_mismatch=True, unreadable=["x"]))
            self.assertEqual(verdict["aggregate"], "FALLA")

    def test_r26_clave_encontrada_sigue_siendo_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, key_hits=1, unreadable=["x"]))
            self.assertEqual(verdict["aggregate"], "FALLA")
            self.assertEqual(verdict["reason"], "clave en los logs")

    def test_aggregate_pasa(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp))
            self.assertEqual(verdict["aggregate"], "PASA")
            self.assertNotIn("reason", verdict)

    def test_r4_clave_en_cualquier_escenario_tumba_el_agregado(self):
        # R4: un key_scan con hits en G2 (que no es G4) hace FALLA el agregado aunque G1 y G2 den PASA.
        # El evaluador anterior solo miraba key_scan dentro de G4.
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, key_hits=2))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "PASA")
            self.assertEqual(verdict["rows"]["G2"]["verdict"], "PASA")
            self.assertEqual(verdict["aggregate"], "FALLA")
            self.assertEqual(verdict["reason"], "clave en los logs")

    def test_r4_clave_tumba_aunque_las_filas_sean_inconclusas(self):
        with tempfile.TemporaryDirectory() as tmp:
            verdict = EVAL.evaluate(_two_rows(tmp, key_hits=1, dirty=True))
            self.assertEqual(verdict["rows"]["G1"]["verdict"], "INCONCLUSO")
            self.assertEqual(verdict["aggregate"], "FALLA")

    def test_r4_clave_en_un_escenario_fuera_del_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _two_rows(tmp)
            _write_jsonl(
                root / "samples" / "G7.jsonl",
                [{"t_ms": 1.0, "ev": "key_scan", "files": [], "hits": 1}],
            )
            self.assertEqual(EVAL.evaluate(root)["aggregate"], "FALLA")

    def test_r4_cero_hits_no_tumba(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _two_rows(tmp)
            _write_jsonl(
                root / "samples" / "G7.jsonl",
                [{"t_ms": 1.0, "ev": "key_scan", "files": [], "hits": 0}],
            )
            self.assertEqual(EVAL.evaluate(root)["aggregate"], "PASA")


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

    def test_r8_cada_linea_effect_lleva_fichero_y_numero(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server_script.log"
            _write_text(
                path,
                "\n".join(
                    [
                        "[DSBX] effect step=retirar session=s1 op=o1 tick_ms=10",
                        "otra linea",
                        "[DSBX] effect step=retirar session=s1 op=o1 tick_ms=10",
                    ]
                )
                + "\n",
            )
            events = EVAL.parse_script_log(path)
            self.assertEqual([ev["lineno"] for ev in events], [1, 3])
            self.assertEqual({ev["file"] for ev in events}, {"server_script.log"})


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

    def test_r4_exit_1_y_motivo_con_clave_en_los_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _two_rows(tmp, key_hits=1)
            result = self._run(root)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("clave en los logs", result.stdout)
            verdict = json.loads((root / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["reason"], "clave en los logs")

    def test_r2_exit_2_con_logs_no_finales(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            _write_json(root / "logs_ready.json", {"all_closed": False})
            result = self._run(root)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("logs no finales", result.stdout)

    def test_evaluate_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _g1(tmp)
            EVAL.evaluate(root)
            self.assertFalse((root / "verdict.json").exists())


if __name__ == "__main__":
    unittest.main()
