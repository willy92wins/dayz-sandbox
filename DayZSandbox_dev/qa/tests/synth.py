"""Evidencia sintetica de S-puente para las pruebas de §10.1. Solo carpetas que pase el llamador."""

import json
from pathlib import Path

import gate_core

PEERS = ("server", "client")

SERVER_N = {
    "N1": ("B", 0.10, "S", 0.937),
    "N2": ("B", 0.20, "S", 0.912),
    "N3": ("B", 0.30, "S", 0.927),
    "N4": ("a", 0.40, "b", 0.45),
    "N5": ("c", 0.60, "d", 0.65),
}

CLIENT_N = {
    "N1": ("B", (7400, 380, 7400), "S", (7350, 390, 7350)),
    "N2": ("B", (7410, 380, 7410), "S", (7360, 390, 7360)),
    "N3": ("B", (7420, 380, 7420), "S", (7370, 390, 7370)),
    "N4": ("a", (7430, 380, 7430), "b", (7440, 380, 7440)),
    "N5": ("c", (7450, 380, 7450), "d", (7460, 380, 7460)),
}


def write_case(directory, defect=None):
    directory = Path(directory)
    samples = directory / "samples"
    samples.mkdir(parents=True)
    bridge, scenario = _build()
    _apply(defect, bridge, scenario)
    _write_jsonl(samples / "bridge.jsonl", bridge)
    _write_jsonl(samples / "scenario.jsonl", scenario)
    gate_core.write_json(directory / "manifest.json", _manifest())
    if defect == "corrupt_line":
        with (samples / "bridge.jsonl").open("ab") as handle:
            handle.write(b"{not-json\n")
    return directory


def _manifest():
    return {
        "argv": [],
        "both": True,
        "build": "offline",
        "ended_utc": "2026-10-26T00:00:01Z",
        "faults": [],
        "harness": {
            "git_dirty": None,
            "git_head": None,
            "platform": "test",
            "python": "3.14",
        },
        "id": "S-puente",
        "kind": "spike",
        "params": {
            "hold_ms": 2000,
            "lease_ms": 3000,
            "port": 9,
            "retry_ms": 2000,
            "seed": 20261026,
            "ttl_ms": 5000,
        },
        "schema": gate_core.SCHEMA_MANIFEST,
        "started_utc": "2026-10-26T00:00:00Z",
    }


def _build():
    bridge = []
    scenario = []
    state = {"bridge": bridge, "scenario": scenario, "t": 0, "refs": {}}

    def add(bucket, ev, **fields):
        state["t"] += 10
        row = {"ev": ev, "t_ms": fields.pop("t_ms", state["t"])}
        state["t"] = row["t_ms"]
        row.update(fields)
        bucket.append(row)
        return row

    def b(ev, **fields):
        return add(bridge, ev, **fields)

    def s(ev, **fields):
        return add(scenario, ev, **fields)

    for peer, inst in (("server", "ab" * 16), ("client", "cd" * 16)):
        b(
            "hello",
            peer=peer,
            http=200,
            args={"build": "offline", "inst": inst, "peer": peer, "probe_ver": "fake-qa0", "proto": "qa0"},
        )

    s("step_start", step="S2", t_ms=1000)
    held = []
    for stamp, frame in ((1500, 0), (3500, 100), (5500, 300)):
        for peer in PEERS:
            ev = b(
                "poll",
                t_ms=stamp,
                peer=peer,
                http=200,
                n_ops=0,
                held_ms=2000,
                frame=frame,
            )
            if peer == "server":
                held.append(ev)
    after = b("poll", t_ms=8000, peer="server", http=200, n_ops=0, held_ms=2000, frame=600)
    b("poll", t_ms=8000, peer="client", http=200, n_ops=0, held_ms=2000, frame=600)
    s("step_end", step="S2", t_ms=7000)
    state["refs"]["server_held"] = held
    state["refs"]["server_after"] = after

    verbs = (
        ["srv_read"] * 25
        + ["ground_query"] * 25
        + ["cam_pose_set"] * 25
        + ["ambient_set"] * 25
    )
    mix = []
    state["t"] = 10000
    for i, verb in enumerate(verbs):
        op_id = f"mix-{i:03d}"
        peer = "client" if verb == "cam_pose_set" else "server"
        args = _mix_args(verb, i)
        s("mix_op", op_id=op_id, verb=verb)
        enq = b("enq", op_id=op_id, verb=verb, peer=peer, args=args)
        res = b("result", op_id=op_id, peer=peer, result=_done(verb, args, 1000 + i))
        mix.append((enq, res))
    state["refs"]["mix"] = mix
    state["refs"]["mix_ops"] = [e for e in scenario if e["ev"] == "mix_op"]

    state["t"] = 100000
    for peer in PEERS:
        _negatives(peer, b, s, state["refs"])
    s("step_start", step="N6", peer="client")
    _n6(b, s, state["refs"])
    s("step_end", step="N6", peer="client")
    return bridge, scenario


def _negatives(peer, b, s, refs):
    table = SERVER_N if peer == "server" else CLIENT_N
    verb = "ambient_set" if peer == "server" else "cam_pose_set"
    read_verb = "ambient_read" if peer == "server" else "cam_pose_read"
    for step in ("N1", "N2", "N3"):
        s("step_start", step=step, peer=peer)
        left, left_v, right, right_v = table[step]
        b_args = _value_args(peer, left_v, sentinel=False)
        s_args = _value_args(peer, right_v, sentinel=True)
        op_b = f"{step}.{peer}.B"
        op_s = f"{step}.{peer}.S"
        op_r = f"{step}.{peer}.read"
        b("enq", op_id=op_b, verb=verb, peer=peer, args=b_args)
        b("result", op_id=op_b, peer=peer, result=_done(verb, b_args, 1))
        if step == "N1":
            s("key_rotated", peer=peer)
            b("enq", op_id=op_s, verb=verb, peer=peer, args=s_args)
            b("auth_reject", peer=peer, http=401)
            s("config_restored", peer=peer)
            b(
                "hello",
                peer=peer,
                http=200,
                args={"build": "offline", "inst": "ef" * 16, "peer": peer, "probe_ver": "fake-qa0", "proto": "qa0"},
            )
        else:
            b("enq", op_id=op_s, verb=verb, peer=peer, args=s_args)
            reason = "stale_instance" if step == "N2" else "expired"
            b("force", op_id=op_s, peer=peer)
            b("deliver", op_id=op_s, peer=peer)
            sentinel = b(
                "result",
                op_id=op_s,
                peer=peer,
                result=_rejected(reason),
            )
            refs[(step, peer, "sentinel")] = sentinel
        b("enq", op_id=op_r, verb=read_verb, peer=peer, args={})
        read = b("result", op_id=op_r, peer=peer, result=_done(read_verb, b_args, 1))
        s("expect", step=step, peer=peer, roles={"B": op_b, "S": op_s, "read": op_r})
        refs[(step, peer, "read")] = read
        refs[(step, peer, "sentinel_args")] = s_args
        s("step_end", step=step, peer=peer)

    for step, source in (("N4", "b"), ("N5", "d")):
        s("step_start", step=step, peer=peer)
        _replica(peer, step, source, table[step], verb, read_verb, b, s, refs)
        s("step_end", step=step, peer=peer)


def _replica(peer, step, source_role, pair, verb, read_verb, b, s, refs):
    role_a, val_a, role_b, val_b = pair
    args_a = _value_args(peer, val_a, sentinel=False)
    args_b = _value_args(peer, val_b, sentinel=False)
    op_a = f"{step}.{peer}.{role_a}"
    op_b = f"{step}.{peer}.{role_b}"
    op_r = f"{step}.{peer}.read"
    b("enq", op_id=op_a, verb=verb, peer=peer, args=args_a)
    first = b("result", op_id=op_a, peer=peer, result=_done(verb, args_a, 1, dup=False))
    b("enq", op_id=op_b, verb=verb, peer=peer, args=args_b)
    b("result", op_id=op_b, peer=peer, result=_done(verb, args_b, 1, dup=False))
    if step == "N4":
        b("cut_start", peer=peer)
        b("cut_end", peer=peer)
        b("poll", peer=peer, http=200, n_ops=0, held_ms=10, frame=9000)
        b("enq", op_id=op_a, verb=verb, peer=peer, args=args_a)
        repeat = b("result", op_id=op_a, peer=peer, result=_done(verb, args_a, 1, dup=True))
        read_args = args_b
        roles = {"a": op_a, "b": op_b, "repeat": op_a, "read": op_r}
    else:
        b("result_drop", op_id=op_a, peer=peer)
        # c was enqueued above as op_a; drop sits after the first enq and there is no
        # result yet. The first result written above is in the way: remove it so N5's
        # c has no registered result before the repetition.
        _drop_event(first)
        b("enq", op_id=op_a, verb=verb, peer=peer, args=args_a)
        repeat = b("result", op_id=op_a, peer=peer, result=_done(verb, args_a, 1, dup=True))
        read_args = args_b
        roles = {"c": op_a, "d": op_b, "repeat": op_a, "read": op_r}
    read = b("enq", op_id=op_r, verb=read_verb, peer=peer, args={})
    read_res = b("result", op_id=op_r, peer=peer, result=_done(read_verb, read_args, 1))
    s("expect", step=step, peer=peer, roles=roles)
    refs[(step, peer, "repeat")] = repeat
    refs[(step, peer, "read")] = read_res
    refs[(step, peer, "args_a")] = args_a
    refs[(step, peer, "args_b")] = args_b
    refs[(step, peer, "first")] = first


def _n6(b, s, refs):
    burst_args = {
        "pos": [7200, 360, 7200],
        "ypr": [90, 0, 0],
        "count": 40,
        "interval_ms": 300,
        "seq0": 1000,
        "client_inst": "cd" * 16,
    }
    b("cut_start", peer="client")
    b("cut_end", peer="client")
    b("poll", peer="client", http=200, n_ops=0, held_ms=10, frame=9100)
    b("enq", op_id="N6.burst", verb="rpc_burst", peer="server", args=burst_args)
    b("result", op_id="N6.burst", peer="server", result=_done("rpc_burst", {}, 1))
    log = []
    for seq in range(1000, 1040):
        accepted = seq <= 1009
        log.append(
            {
                "decision": "accepted" if accepted else "rejected_lease",
                "lease_age_ms": 100 if accepted else 4000,
                "recv_ms": seq,
                "seq": seq,
            }
        )
    b("enq", op_id="N6.log", verb="rpc_log_read", peer="client", args={})
    log_res = b(
        "result",
        op_id="N6.log",
        peer="client",
        result=_done("rpc_log_read", {}, 1, rpc_log=log),
    )
    pose = {"pos": [7209, 360, 7200], "ypr": [90, 0, 0]}
    b("enq", op_id="N6.read", verb="cam_pose_read", peer="client", args={})
    pose_res = b("result", op_id="N6.read", peer="client", result=_done("cam_pose_read", pose, 1))
    s(
        "expect",
        step="N6",
        peer="client",
        roles={"burst": "N6.burst", "log": "N6.log", "read": "N6.read"},
    )
    refs["n6_log"] = log_res["result"]["read"]["rpc_log"]
    refs["n6_pose"] = pose_res["result"]["read"]


def _drop_event(ev):
    ev["_drop"] = True


def _apply(defect, bridge, scenario):
    bridge[:] = [e for e in bridge if not e.get("_drop")]
    for ev in bridge:
        ev.pop("_enq_after", None)
        ev.pop("_drop", None)
    if defect in (None, "corrupt_line"):
        return
    if defect == "p95_1000":
        _relat(bridge, [10] * 94 + [1000] * 6)
    elif defect == "six_missing":
        _relat(bridge, [10] * 94 + [None] * 6)
    elif defect == "five_inf":
        _relat(bridge, [50] * 95 + [None] * 5)
    elif defect == "lat_1_100":
        _relat(bridge, list(range(1, 101)))
    elif defect == "p95_999_9":
        _relat(bridge, [1] * 94 + [999.9] * 6)
    elif defect == "h1_frame":
        _zero_server_frames(bridge)
    elif defect == "fail_and_missing":
        _zero_server_frames(bridge)
        _drop_hello(bridge, "client")
    elif defect == "one_poll":
        _drop_extra_server_polls(bridge)
    elif defect == "no_hello":
        _drop_hello(bridge, "server")
    elif defect == "wrong_build":
        for ev in bridge:
            if ev["ev"] == "hello" and ev.get("peer") == "server":
                ev["args"]["build"] = "retail"
                break
    elif defect == "mix_99":
        for ev in scenario:
            if ev["ev"] == "mix_op":
                scenario.remove(ev)
                break
    elif defect == "n_step_empty":
        for ev in scenario:
            if ev["ev"] == "expect" and ev.get("step") == "N2" and ev.get("peer") == "server":
                scenario.remove(ev)
                break
    elif defect == "resume_timeout":
        scenario.append({"ev": "resume_timeout", "peer": "client", "t_ms": 900000})
    elif defect == "n6_no_reject":
        log, pose = _n6_parts(bridge)
        for entry in log:
            entry["decision"] = "accepted"
            entry["lease_age_ms"] = 100
            entry["recv_ms"] = entry["seq"]
        pose["pos"] = [7239, 360, 7200]
    elif defect == "n6_missing_seq":
        log, _pose = _n6_parts(bridge)
        log.pop()
    elif defect == "n6_lease":
        log, _pose = _n6_parts(bridge)
        log[0]["lease_age_ms"] = 5000
    elif defect == "n6_order":
        log, _pose = _n6_parts(bridge)
        for entry in log:
            if entry["seq"] == 1009:
                entry["recv_ms"] = 1011
    elif defect == "n6_pose":
        _log, pose = _n6_parts(bridge)
        pose["pos"] = [pose["pos"][0] + 10, pose["pos"][1], pose["pos"][2]]
    elif defect.startswith("n1_delivered_"):
        peer = defect.rsplit("_", 1)[1]
        bridge.append({"ev": "deliver", "op_id": f"N1.{peer}.S", "peer": peer, "t_ms": 1})
    elif "_read_sentinel_" in defect:
        step, peer = _step_peer(defect, "read_sentinel")
        _set_read(bridge, f"{step}.{peer}.read", _sentinel_args(peer, step))
    elif "_done_" in defect:
        step, peer = _step_peer(defect, "done")
        for ev in bridge:
            if ev["ev"] == "result" and ev.get("op_id") == f"{step}.{peer}.S":
                ev["result"]["status"] = "done"
                ev["result"]["reason"] = ""
    elif "_read_a_" in defect or "_read_c_" in defect:
        step = "N4" if "_read_a_" in defect else "N5"
        peer = defect.rsplit("_", 1)[1]
        role = "a" if step == "N4" else "c"
        args = _enq_args(bridge, f"{step}.{peer}.{role}")
        _set_read(bridge, f"{step}.{peer}.read", args)
    elif "_dup_false_" in defect:
        step = "N4" if defect.startswith("n4_") else "N5"
        peer = defect.rsplit("_", 1)[1]
        op_id = f"{step}.{peer}.{'a' if step == 'N4' else 'c'}"
        results = [e for e in bridge if e["ev"] == "result" and e.get("op_id") == op_id]
        results[-1]["result"]["dup"] = False
    elif defect == "sol01_repeat_both":
        last = next(
            e
            for e in reversed(bridge)
            if e["ev"] == "result" and e.get("op_id") == "N4.server.a"
        )
        earlier = json.loads(json.dumps(last))
        earlier["t_ms"] = last["t_ms"] - 0.5
        earlier["result"]["dup"] = False
        bridge.insert(bridge.index(last), earlier)
    elif defect == "sol02_28_ids":
        ops = [e for e in scenario if e["ev"] == "mix_op"]
        by_verb = {}
        for op in ops:
            by_verb.setdefault(op["verb"], []).append(op)
        for verb, rows in by_verb.items():
            if verb == "srv_read":
                continue
            for op in rows[1:]:
                op["op_id"] = rows[0]["op_id"]
    elif defect == "sol03_no_deliver":
        bridge[:] = [
            e
            for e in bridge
            if not (e["ev"] == "deliver" and e.get("op_id") == "N2.server.S")
        ]
    elif defect == "sol04_n4_client_without_cut":
        start = next(e for e in bridge if e["ev"] == "cut_start" and e.get("peer") == "client")
        end = next(
            e
            for e in bridge
            if e["ev"] == "cut_end" and e.get("peer") == "client" and e["t_ms"] >= start["t_ms"]
        )
        bridge.remove(start)
        bridge.remove(end)
    elif defect == "sol05_read_no_status":
        for ev in bridge:
            if ev["ev"] == "result" and ev.get("op_id") == "N1.server.read":
                del ev["result"]["status"]
                break
    elif defect == "sol05_srv_no_tick":
        for ev in bridge:
            if ev["ev"] == "result" and ev.get("op_id") == "mix-000":
                ev["result"]["read"]["has"] = ["frame"]
                break
    elif defect == "sol06_nan_pose":
        for ev in bridge:
            if ev["ev"] == "result" and ev.get("op_id") == "N1.client.read":
                ev["result"]["read"]["pos"][0] = float("nan")
                break
    elif defect == "sol07_result_before_enq":
        enq = next(e for e in bridge if e["ev"] == "enq" and e.get("op_id") == "mix-000")
        res = next(e for e in bridge if e["ev"] == "result" and e.get("op_id") == "mix-000")
        res["t_ms"] = enq["t_ms"] - 1
    else:
        raise ValueError(defect)


def _relat(bridge, lats):
    enqs = [e for e in bridge if e["ev"] == "enq" and str(e.get("op_id", "")).startswith("mix-")]
    results = {
        e["op_id"]: e
        for e in bridge
        if e["ev"] == "result" and str(e.get("op_id", "")).startswith("mix-")
    }
    ordered = sorted(enqs, key=lambda e: e["op_id"])
    for enq, lat in zip(ordered, lats):
        res = results.get(enq["op_id"])
        if lat is None:
            if res is not None:
                bridge.remove(res)
        elif res is not None:
            res["t_ms"] = enq["t_ms"] + lat


def _zero_server_frames(bridge):
    for ev in bridge:
        if ev["ev"] == "poll" and ev.get("peer") == "server":
            ev["frame"] = 0


def _drop_hello(bridge, peer):
    bridge[:] = [e for e in bridge if not (e["ev"] == "hello" and e.get("peer") == peer)]


def _drop_extra_server_polls(bridge):
    held = [
        e
        for e in bridge
        if e["ev"] == "poll" and e.get("peer") == "server" and e["t_ms"] <= 7000
    ]
    for ev in held[1:]:
        bridge.remove(ev)


def _n6_parts(bridge):
    log_res = next(e for e in bridge if e["ev"] == "result" and e.get("op_id") == "N6.log")
    pose_res = next(e for e in bridge if e["ev"] == "result" and e.get("op_id") == "N6.read")
    return log_res["result"]["read"]["rpc_log"], pose_res["result"]["read"]


def _set_read(bridge, op_id, args):
    for ev in bridge:
        if ev["ev"] == "result" and ev.get("op_id") == op_id:
            read = ev["result"]["read"]
            if "fog" in args:
                read["fog"] = args["fog"]
                if "fog" not in read["has"]:
                    read["has"].append("fog")
            if "pos" in args:
                read["pos"] = list(args["pos"])
                read["ypr"] = list(args["ypr"])
                for key in ("pos", "ypr"):
                    if key not in read["has"]:
                        read["has"].append(key)
            return
    raise KeyError(op_id)


def _enq_args(bridge, op_id):
    for ev in bridge:
        if ev["ev"] == "enq" and ev.get("op_id") == op_id:
            return ev["args"]
    raise KeyError(op_id)


def _step_peer(defect, token):
    # n1_read_sentinel_server / n2_done_server
    head, peer = defect.rsplit("_", 1)
    step = head.split("_", 1)[0].upper()
    return step, peer


def _sentinel_args(peer, step):
    if peer == "server":
        _role, _bv, _srole, value = SERVER_N[step]
        return _value_args(peer, value, sentinel=True)
    _role, _bv, _srole, value = CLIENT_N[step]
    return _value_args(peer, value, sentinel=True)


def _value_args(peer, value, sentinel):
    if peer == "server":
        return {"fog": value}
    ypr = [45, 0, 0] if sentinel else [0, 0, 0]
    return {"pos": [value[0], value[1], value[2]], "ypr": ypr}


def _mix_args(verb, index):
    if verb == "cam_pose_set":
        return {"pos": [7500, 400, 7500], "ypr": [float(index), 0, 0]}
    if verb == "ambient_set":
        return {"fog": 0.05 * ((index % 19) + 1)}
    if verb == "ground_query":
        return {"x": float(index), "z": float(index)}
    return {}


def _done(verb, args, frame, dup=False, rpc_log=None):
    read = {
        "fog": 0.0,
        "frame": 0,
        "has": [],
        "pos": [0, 0, 0],
        "rpc_log": [] if rpc_log is None else rpc_log,
        "tick_s": 0.0,
        "y": 0.0,
        "ypr": [0, 0, 0],
    }
    if verb == "srv_read":
        read["has"] = ["frame", "tick_s"]
        read["frame"] = frame
        read["tick_s"] = frame / 60.0
    elif verb == "ground_query":
        read["has"] = ["y"]
        read["y"] = 100.0
    elif verb in ("cam_pose_set", "cam_pose_read"):
        read["has"] = ["pos", "ypr"]
        read["pos"] = list(args.get("pos", [0, 0, 0]))
        read["ypr"] = list(args.get("ypr", [0, 0, 0]))
    elif verb in ("ambient_set", "ambient_read"):
        read["has"] = ["fog"]
        read["fog"] = args.get("fog", 0.0)
    elif verb == "rpc_log_read":
        read["has"] = ["rpc_log"]
    return {
        "done_ms": 1.0,
        "dup": dup,
        "frame_done": frame if isinstance(frame, int) else 0,
        "frame_recv": 0,
        "op_id": "synth",
        "read": read,
        "reason": "",
        "recv_ms": 0.0,
        "status": "done",
    }


def _rejected(reason):
    return {
        "dup": False,
        "read": {
            "fog": 0.0,
            "frame": 0,
            "has": [],
            "pos": [0, 0, 0],
            "rpc_log": [],
            "tick_s": 0.0,
            "y": 0.0,
            "ypr": [0, 0, 0],
        },
        "done_ms": 1.0,
        "frame_done": 0,
        "frame_recv": 0,
        "op_id": "synth",
        "reason": reason,
        "recv_ms": 0.0,
        "status": "rejected",
    }


def _write_jsonl(path, rows):
    lines = [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows]
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
