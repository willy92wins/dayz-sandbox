"""Evaluador puro de S-puente (brief F0.1 §9).

Lee manifest.json, samples/bridge.jsonl y samples/scenario.jsonl.
No abre red, no mira el reloj y no usa azar.

Contrato que escribe el escenario (F0.1b) y que este modulo lee:
scenario.jsonl, un objeto por linea, con t_ms y ev:
  step_start|step_end: step
  mix_op: op_id, verb
  expect: step, peer, roles (B, S, read | a, b, repeat, read | c, d, repeat, read | burst, log, read)
  key_rotated|config_restored|resume_timeout: peer
bridge.jsonl (campos del §6, solo los que apliquen):
  hello: peer, args.proto, args.build
  poll: peer, http, held_ms, n_ops, frame
  auth_reject, o http 401: peer
  enq: op_id, verb, args
  deliver|result_drop: op_id
  result: op_id, result (RESULT del §5.2)
  cut_start|cut_end: peer
"""

import json
import math
from pathlib import Path

PEERS = ("server", "client")
MIX_VERBS = ("srv_read", "ground_query", "cam_pose_set", "ambient_set")
CHECK_IDS = (
    ["C0", "H1.server", "H1.client", "M1", "M2"]
    + [f"N{n}.{peer}" for n in range(1, 6) for peer in PEERS]
    + ["N6"]
)


class EvidenceError(Exception):
    pass


def evaluate(directory):
    directory = Path(directory)
    manifest = _read_json(directory / "manifest.json")
    bridge = _read_jsonl(directory / "samples" / "bridge.jsonl")
    scenario = _read_jsonl(directory / "samples" / "scenario.jsonl")
    hold = _need_manifest(manifest, "params", "hold_ms")
    lease = _need_manifest(manifest, "params", "lease_ms")
    build = manifest.get("build")
    if build is None:
        raise EvidenceError("manifest missing build")
    ctx = {
        "bridge": bridge,
        "scenario": scenario,
        "hold": hold,
        "lease": lease,
        "build": build,
        "index": {id(ev): i for i, ev in enumerate(bridge)},
        "skipped": _skipped(scenario),
    }
    checks = []
    metrics = {}
    for cid in CHECK_IDS:
        status, detail, extra = _run_check(cid, ctx)
        checks.append({"detail": detail, "id": cid, "status": status})
        if extra:
            metrics.update(extra)
    statuses = [c["status"] for c in checks]
    if "fail" in statuses:
        code = 1
    elif "missing" in statuses:
        code = 2
    else:
        code = 0
    name = {0: "PASA", 1: "FALLA", 2: "INCONCLUSO"}[code]
    reasons = [c["id"] for c in checks if c["status"] != "pass"]
    return {
        "checks": checks,
        "error": None,
        "exit_code": code,
        "id": manifest.get("id", "S-puente"),
        "metrics": {k: _metric(v) for k, v in metrics.items()},
        "reasons": reasons,
        "schema": "dsbx-qa-verdict/1",
        "verdict": name,
    }


def _run_check(cid, ctx):
    if cid == "C0":
        return _c0(ctx)
    if cid.startswith("H1."):
        return _h1(cid.split(".", 1)[1], ctx)
    if cid == "M1":
        return _m1(ctx)
    if cid == "M2":
        return _m2(ctx)
    if cid == "N6":
        return _n6(ctx)
    step, peer = cid.split(".")
    if step in ctx["skipped"].get(peer, ()):
        return "missing", "resume_timeout", None
    return {
        "N1": _n1,
        "N2": _n2,
        "N3": _n3,
        "N4": _n4,
        "N5": _n5,
    }[step](peer, ctx)


def _skipped(scenario):
    skipped = {"server": set(), "client": set()}
    for ev in scenario:
        if ev["ev"] != "resume_timeout":
            continue
        peer = ev.get("peer")
        if peer not in skipped:
            raise EvidenceError("resume_timeout missing peer")
        skipped[peer].update(("N2", "N3", "N4", "N5"))
        skipped["__n6__"] = True
    return skipped


def _c0(ctx):
    for peer in PEERS:
        hellos = [e for e in ctx["bridge"] if e["ev"] == "hello" and e.get("peer") == peer]
        if not hellos:
            return "missing", f"no hello from {peer}", None
        args = hellos[0].get("args")
        if not isinstance(args, dict) or "proto" not in args or "build" not in args:
            raise EvidenceError(f"hello {peer} missing proto/build")
        if args["proto"] != "qa0" or args["build"] != ctx["build"]:
            return "missing", f"{peer} proto/build not accepted", None
    return "pass", "", None


def _h1(peer, ctx):
    window = _step_window(ctx["scenario"], "S2")
    if window is None:
        return "missing", "no S2 window", None
    start, end = window
    polls = [e for e in ctx["bridge"] if e["ev"] == "poll" and e.get("peer") == peer]
    qualifying = []
    for ev in polls:
        if not (start <= ev["t_ms"] <= end):
            continue
        if ev.get("http") != 200 or ev.get("n_ops") != 0:
            continue
        if "held_ms" not in ev:
            raise EvidenceError("poll missing held_ms")
        if ev["held_ms"] + 1e-9 >= 0.9 * ctx["hold"]:
            qualifying.append(ev)
    if len(qualifying) < 2:
        return "missing", f"{len(qualifying)} held polls", None
    stalled = False
    no_next = False
    for ev in qualifying:
        nxt = _next_poll(polls, ev)
        if nxt is None:
            no_next = True
            continue
        if "frame" not in ev or "frame" not in nxt:
            raise EvidenceError("poll missing frame")
        need = 10.0 * (ev["held_ms"] / 1000.0)
        if (nxt["frame"] - ev["frame"]) + 1e-9 < need:
            stalled = True
    if stalled:
        return "fail", "frame advance below 10/s", None
    if no_next:
        return "missing", "no following poll", None
    return "pass", "", None


def _m1(ctx):
    ops = [e for e in ctx["scenario"] if e["ev"] == "mix_op"]
    if len(ops) != 100:
        return "missing", f"{len(ops)} mix_op", None
    for verb in MIX_VERBS:
        n = sum(1 for e in ops if e.get("verb") == verb)
        if n != 25:
            return "missing", f"{verb}={n}", None
    return "pass", "", None


def _m2(ctx):
    ops = [e for e in ctx["scenario"] if e["ev"] == "mix_op"]
    if len(ops) != 100:
        return "missing", "mix is not 100", None
    lats = []
    n_timeouts = 0
    n_not_observed = 0
    last_srv = None
    for ev in ops:
        if "op_id" not in ev or "verb" not in ev:
            raise EvidenceError("mix_op missing op_id/verb")
        enq = _first(ctx, "enq", ev["op_id"])
        res = _first(ctx, "result", ev["op_id"])
        ok = False
        if enq is not None and res is not None:
            ok = _mix_ok(ev["verb"], enq, res, last_srv)
            if ok and ev["verb"] == "srv_read":
                last_srv = res["result"]["read"]["frame"]
        if ok:
            lats.append(res["t_ms"] - enq["t_ms"])
        else:
            lats.append(math.inf)
            if res is None:
                n_timeouts += 1
            else:
                n_not_observed += 1
    ordered = sorted(lats, key=lambda v: (math.isinf(v), v if not math.isinf(v) else 0))
    p50 = ordered[math.ceil(0.50 * 100) - 1]
    p95 = ordered[math.ceil(0.95 * 100) - 1]
    worst = ordered[-1]
    metrics = {
        "max_ms": worst,
        "n_not_observed": n_not_observed,
        "n_timeouts": n_timeouts,
        "p50_ms": p50,
        "p95_ms": p95,
    }
    if (math.isinf(p95)) or p95 >= 1000:
        return "fail", "p95 >= 1000", metrics
    return "pass", "", metrics


def _mix_ok(verb, enq, res, last_srv):
    body = res.get("result")
    if not isinstance(body, dict):
        raise EvidenceError("result missing result")
    if body.get("status") != "done":
        return False
    read = body.get("read")
    if not isinstance(read, dict):
        return False
    has = read.get("has") or []
    if verb == "srv_read":
        if "frame" not in has or "frame" not in read:
            return False
        return last_srv is None or read["frame"] > last_srv
    if verb == "ground_query":
        if "y" not in has or "y" not in read:
            return False
        y = read["y"]
        return isinstance(y, (int, float)) and math.isfinite(y)
    if verb == "cam_pose_set":
        return _pose_match(read, _args(enq).get("pos"), _args(enq).get("ypr"))
    if verb == "ambient_set":
        return _fog_match(read, _args(enq).get("fog"))
    return False


def _n1(peer, ctx):
    roles = _roles(ctx, "N1", peer)
    if roles is None:
        return "missing", "no expect", None
    rotated = _scenario_one(ctx, "key_rotated", peer)
    restored = _scenario_one(ctx, "config_restored", peer)
    if rotated is None or restored is None:
        return "missing", "no key window", None
    if not _auth_between(ctx, peer, rotated, restored):
        return "missing", "no 401 in key window", None
    if _delivered(ctx, roles["S"]):
        return "fail", "sentinel delivered", None
    if not _hello_after(ctx, peer, restored):
        return "missing", "no hello after restore", None
    return _read_vs(ctx, peer, roles, "B")


def _n2(peer, ctx):
    return _rejected(peer, ctx, "N2", "stale_instance")


def _n3(peer, ctx):
    return _rejected(peer, ctx, "N3", "expired")


def _rejected(peer, ctx, step, reason):
    roles = _roles(ctx, step, peer)
    if roles is None:
        return "missing", "no expect", None
    res = _first(ctx, "result", roles["S"])
    if res is None:
        return "missing", "no sentinel result", None
    body = _body(res)
    if body.get("status") == "done":
        return "fail", "sentinel done", None
    if body.get("status") != "rejected" or body.get("reason") != reason:
        return "fail", f"sentinel not {reason}", None
    return _read_vs(ctx, peer, roles, "B")


def _n4(peer, ctx):
    roles = _roles(ctx, "N4", peer)
    if roles is None:
        return "missing", "no expect", None
    if _done(ctx, roles["a"]) is None or _done(ctx, roles["b"]) is None:
        return "missing", "a or b not done", None
    cut_end = _cut_end(ctx, peer)
    if _one_ev(ctx, "cut_start", peer) is None or cut_end is None:
        return "missing", "no cut", None
    if _poll_after(ctx, peer, cut_end) is None:
        return "missing", "no poll after cut", None
    rep = _result_after_repeat(ctx, roles["a"])
    if rep is None:
        return "missing", "no repeat result", None
    body = _body(rep)
    if body.get("status") == "done" and body.get("dup") is False:
        return "fail", "dup false", None
    if not (body.get("status") == "done" and body.get("dup") is True):
        return "fail", "repeat not dup", None
    return _read_vs(ctx, peer, roles, "b")


def _n5(peer, ctx):
    roles = _roles(ctx, "N5", peer)
    if roles is None:
        return "missing", "no expect", None
    repeat = _repeat_enq(ctx, roles["c"])
    if repeat is None:
        return "missing", "no repeat enq", None
    drops = [
        e
        for e in ctx["bridge"]
        if e["ev"] == "result_drop" and e.get("op_id") == roles["c"]
    ]
    early = [
        e
        for e in ctx["bridge"]
        if e["ev"] == "result"
        and e.get("op_id") == roles["c"]
        and ctx["index"][id(e)] < ctx["index"][id(repeat)]
    ]
    if not drops or early:
        return "missing", "no clean result_drop", None
    if _done(ctx, roles["d"]) is None:
        res_d = _first(ctx, "result", roles["d"])
        if res_d is None:
            return "missing", "d missing", None
        return "fail", "d not done", None
    rep = _result_after(ctx, roles["c"], repeat)
    if rep is None:
        return "missing", "no repeat result", None
    body = _body(rep)
    if not (body.get("status") == "done" and body.get("dup") is True):
        if body.get("status") == "done" and body.get("dup") is False:
            return "fail", "dup false", None
        return "fail", "repeat not dup", None
    return _read_vs(ctx, peer, roles, "d")


def _n6(ctx):
    if ctx["skipped"].get("__n6__"):
        return "missing", "resume_timeout", None
    roles = _roles(ctx, "N6", "client")
    if roles is None:
        return "missing", "no expect", None
    burst = _first(ctx, "enq", roles["burst"])
    log_res = _first(ctx, "result", roles["log"])
    if burst is None or log_res is None:
        return "missing", "no burst or log", None
    read = _body(log_res).get("read")
    if not isinstance(read, dict) or "rpc_log" not in (read.get("has") or []):
        return "missing", "rpc_log absent", None
    log = read.get("rpc_log")
    if not isinstance(log, list):
        raise EvidenceError("rpc_log is not a list")
    seqs = []
    for entry in log:
        if "seq" not in entry or "decision" not in entry:
            raise EvidenceError("rpc_log entry missing seq/decision")
        seqs.append(entry["seq"])
    if any(s not in seqs for s in range(1000, 1040)):
        return "missing", "seq missing", None
    for entry in log:
        if "lease_age_ms" not in entry or "recv_ms" not in entry:
            raise EvidenceError("rpc_log entry missing lease_age_ms/recv_ms")
    decisions = {e["decision"] for e in log}
    accepted = [e for e in log if e["decision"] == "accepted"]
    rejected = [e for e in log if e["decision"] == "rejected_lease"]
    lease = ctx["lease"]
    # Un accepted con lease_age > L es conducta rota (matriz rpc_ignores_lease → 1),
    # aunque no haya ningún rejected_lease que vuelva el caso «missing».
    if accepted and any(e["lease_age_ms"] > lease for e in accepted):
        metrics = {"window_accept_max_ms": max(e["lease_age_ms"] for e in accepted)}
        if rejected:
            metrics["window_reject_min_ms"] = min(e["lease_age_ms"] for e in rejected)
        return "fail", "lease_age outside window", metrics
    if not accepted or not rejected or decisions - {"accepted", "rejected_lease"}:
        return "missing", "lease window not both sides", None
    metrics = {
        "window_accept_max_ms": max(e["lease_age_ms"] for e in accepted),
        "window_reject_min_ms": min(e["lease_age_ms"] for e in rejected),
    }
    bounds_ok = all(e["lease_age_ms"] > lease for e in rejected)
    first_reject = min(rejected, key=lambda e: (e["recv_ms"], e["seq"]))
    order_ok = not any(
        (e["recv_ms"] > first_reject["recv_ms"])
        or (e["recv_ms"] == first_reject["recv_ms"] and e["seq"] > first_reject["seq"])
        for e in accepted
    )
    last = max(accepted, key=lambda e: (e["recv_ms"], e["seq"]))
    k = last["seq"]
    args = _args(burst)
    p0 = args.get("pos")
    if not isinstance(p0, list) or len(p0) != 3:
        raise EvidenceError("rpc_burst missing pos")
    expect = [p0[0] + (k - 1000), p0[1], p0[2]]
    pose_res = _first(ctx, "result", roles["read"])
    if pose_res is None:
        return "missing", "no pose read", metrics
    pose_ok = _pose_match(_body(pose_res).get("read") or {}, expect, [90, 0, 0])
    if not bounds_ok:
        return "fail", "lease_age outside window", metrics
    if not order_ok:
        return "fail", "accepted after rejected_lease", metrics
    if not pose_ok:
        return "fail", "pose is not last accepted", metrics
    return "pass", "", metrics


def _read_vs(ctx, peer, roles, source_role):
    res = _first(ctx, "result", roles["read"])
    if res is None:
        return "missing", "no read", None
    src = _first(ctx, "enq", roles[source_role])
    if src is None:
        return "missing", "no source enq", None
    read = _body(res).get("read") or {}
    args = _args(src)
    if peer == "server":
        ok = _fog_match(read, args.get("fog"))
    else:
        ok = _pose_match(read, args.get("pos"), args.get("ypr"))
    if not ok:
        return "fail", "read mismatch", None
    return "pass", "", None


def _delivered(ctx, op_id):
    for ev in ctx["bridge"]:
        if ev.get("op_id") != op_id:
            continue
        if ev["ev"] in ("deliver", "result"):
            return True
    return False


def _auth_between(ctx, peer, rotated, restored):
    si = _scn_index(ctx, rotated)
    ei = _scn_index(ctx, restored)
    for i, ev in enumerate(ctx["scenario"]):
        if not (si < i < ei):
            continue
        if ev.get("peer") != peer:
            continue
        if ev["ev"] == "auth_reject" or ev.get("http") == 401:
            return True
    # 401 is a bridge event. Place it by t_ms between the two scenario marks.
    t0, t1 = rotated["t_ms"], restored["t_ms"]
    for ev in ctx["bridge"]:
        if ev.get("peer") != peer:
            continue
        if not (t0 < ev["t_ms"] < t1):
            continue
        if ev["ev"] == "auth_reject" or ev.get("http") == 401:
            return True
    return False


def _hello_after(ctx, peer, restored):
    t0 = restored["t_ms"]
    for ev in ctx["bridge"]:
        if ev["ev"] == "hello" and ev.get("peer") == peer and ev["t_ms"] > t0:
            return True
    return False


def _done(ctx, op_id):
    for ev in ctx["bridge"]:
        if ev["ev"] == "result" and ev.get("op_id") == op_id:
            body = _body(ev)
            if body.get("status") == "done":
                return ev
    return None


def _result_after_repeat(ctx, op_id):
    enqs = [e for e in ctx["bridge"] if e["ev"] == "enq" and e.get("op_id") == op_id]
    if len(enqs) < 2:
        return None
    return _result_after(ctx, op_id, enqs[-1])


def _repeat_enq(ctx, op_id):
    enqs = [e for e in ctx["bridge"] if e["ev"] == "enq" and e.get("op_id") == op_id]
    if len(enqs) < 2:
        return None
    return enqs[-1]


def _result_after(ctx, op_id, mark):
    mi = ctx["index"][id(mark)]
    found = None
    for ev in ctx["bridge"]:
        if ev["ev"] == "result" and ev.get("op_id") == op_id and ctx["index"][id(ev)] > mi:
            found = ev
    return found


def _cut_end(ctx, peer):
    found = None
    for ev in ctx["bridge"]:
        if ev["ev"] == "cut_end" and ev.get("peer") == peer:
            found = ev
    return found


def _one_ev(ctx, name, peer):
    for ev in ctx["bridge"]:
        if ev["ev"] == name and ev.get("peer") == peer:
            return ev
    return None


def _poll_after(ctx, peer, mark):
    mi = ctx["index"][id(mark)]
    for ev in ctx["bridge"]:
        if (
            ev["ev"] == "poll"
            and ev.get("peer") == peer
            and ev.get("http") == 200
            and ctx["index"][id(ev)] > mi
        ):
            return ev
    return None


def _first(ctx, ev_name, op_id):
    for ev in ctx["bridge"]:
        if ev["ev"] == ev_name and ev.get("op_id") == op_id:
            return ev
    return None


def _roles(ctx, step, peer):
    for ev in ctx["scenario"]:
        if ev["ev"] == "expect" and ev.get("step") == step and ev.get("peer") == peer:
            roles = ev.get("roles")
            if not isinstance(roles, dict):
                raise EvidenceError(f"expect {step} {peer} missing roles")
            return roles
    return None


def _scenario_one(ctx, name, peer):
    for ev in ctx["scenario"]:
        if ev["ev"] == name and ev.get("peer") == peer:
            return ev
    return None


def _scn_index(ctx, ev):
    for i, other in enumerate(ctx["scenario"]):
        if other is ev:
            return i
    raise EvidenceError("scenario event not in log")


def _step_window(scenario, step):
    start = end = None
    for ev in scenario:
        if ev.get("step") != step:
            continue
        if ev["ev"] == "step_start" and start is None:
            start = ev["t_ms"]
        elif ev["ev"] == "step_end" and start is not None and end is None:
            end = ev["t_ms"]
    if start is None or end is None:
        return None
    return start, end


def _next_poll(polls, ev):
    seen = False
    for other in polls:
        if other is ev:
            seen = True
            continue
        if seen:
            return other
    return None


def _args(enq):
    args = enq.get("args")
    if not isinstance(args, dict):
        raise EvidenceError("enq missing args")
    return args


def _body(res):
    body = res.get("result")
    if not isinstance(body, dict):
        raise EvidenceError("result event missing result")
    return body


def _fog_match(read, fog):
    if not isinstance(read, dict):
        return False
    if "fog" not in (read.get("has") or []) or "fog" not in read or fog is None:
        return False
    return abs(float(read["fog"]) - float(fog)) <= 0.01


def _pose_match(read, pos, ypr):
    if not isinstance(read, dict) or not isinstance(pos, (list, tuple)) or not isinstance(ypr, (list, tuple)):
        return False
    has = read.get("has") or []
    if "pos" not in has or "ypr" not in has:
        return False
    if "pos" not in read or "ypr" not in read:
        return False
    if len(read["pos"]) != 3 or len(pos) != 3 or len(read["ypr"]) != 3 or len(ypr) != 3:
        return False
    dist = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(read["pos"], pos)))
    if dist > 0.05:
        return False
    return all(_ang(a, b) <= 0.5 for a, b in zip(read["ypr"], ypr))


def _ang(a, b):
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def _metric(value):
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


def _need_manifest(manifest, group, key):
    block = manifest.get(group)
    if not isinstance(block, dict) or key not in block:
        raise EvidenceError(f"manifest missing {group}.{key}")
    return block[key]


def _read_json(path):
    if not path.is_file():
        raise EvidenceError(f"missing {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"{path.name} is not an object")
    return data


def _read_jsonl(path):
    if not path.is_file():
        raise EvidenceError(f"missing {path.name}")
    events = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"{path.name}:{lineno}: {exc}") from exc
        if not isinstance(obj, dict) or "ev" not in obj or "t_ms" not in obj:
            raise EvidenceError(f"{path.name}:{lineno}: missing ev or t_ms")
        events.append(obj)
    return events
