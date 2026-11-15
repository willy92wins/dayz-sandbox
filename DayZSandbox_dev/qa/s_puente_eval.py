"""Evaluador puro de S-puente (brief F0.1 §9 y F0.3-0 §14 F02-H1/F02-H3).

Lee manifest.json, samples/bridge.jsonl y samples/scenario.jsonl.
No abre red, no mira el reloj y no usa azar.

Contrato que escribe el escenario y que este modulo lee:
scenario.jsonl, un objeto por linea, con t_ms y ev:
  step_start|step_end: step
  mix_op: op_id, verb
  expect: step, peer, roles
  key_rotated|config_restored|resume_timeout: peer
bridge.jsonl:
  hello: peer, http, args.proto, args.build
  poll: peer, http, held_ms, n_ops, frame
  auth_reject, o http 401: peer
  enq: op_id, verb, args
  deliver|result_drop: op_id
  result: op_id, result
  cut_start|cut_end: peer
"""

import json
import math
from pathlib import Path

import wire

PEERS = ("server", "client")
MIX_VERBS = ("srv_read", "ground_query", "cam_pose_set", "ambient_set")
CHECK_IDS = (
    ["C0", "H1.server", "H1.client", "M1", "M2"]
    + [f"N{n}.{peer}" for n in range(1, 6) for peer in PEERS]
    + ["N6", "N6.server"]
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
    _validate_results(bridge)
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
    if cid == "N6.server":
        return _n6_server(ctx)
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
        hellos = [
            e
            for e in ctx["bridge"]
            if e["ev"] == "hello"
            and e.get("peer") == peer
            and e.get("http", 200) == 200
            and e.get("ok", True) is True
        ]
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
        if _finite(ev["held_ms"]) and ev["held_ms"] + 1e-9 >= 0.9 * ctx["hold"]:
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
        advanced = nxt["frame"] - ev["frame"]
        if not (_finite(ev["frame"]) and _finite(nxt["frame"]) and _finite(advanced) and advanced + 1e-9 >= need):
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
    ids = []
    for ev in ops:
        if "op_id" not in ev or "verb" not in ev:
            raise EvidenceError("mix_op missing op_id/verb")
        ids.append(ev["op_id"])
        if _first(ctx, "enq", ev["op_id"]) is None:
            return "missing", "mix op without enq", None
    if len(set(ids)) != 100:
        return "missing", f"{len(set(ids))} distinct op_id", None
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
        if ok and _finite(res.get("t_ms")) and _finite(enq.get("t_ms")):
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
    if body.get("status") != "done" or body.get("dup") is not False:
        return False
    read = body.get("read")
    if not isinstance(read, dict):
        return False
    has = read.get("has") or []
    if verb == "srv_read":
        if "frame" not in has or "tick_s" not in has:
            return False
        if not _finite(read.get("frame")) or not _finite(read.get("tick_s")):
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
    return _read_vs(ctx, "N1", peer, roles, "B")


def _n2(peer, ctx):
    return _rejected(peer, ctx, "N2", "stale_instance")


def _n3(peer, ctx):
    return _rejected(peer, ctx, "N3", "expired")


def _rejected(peer, ctx, step, reason):
    roles = _roles(ctx, step, peer)
    if roles is None:
        return "missing", "no expect", None
    for ev in ctx["bridge"]:
        if ev["ev"] == "result" and ev.get("op_id") == roles["S"] and _body(ev).get("status") == "done":
            return "fail", "sentinel done", None
    res = _in_step(ctx, step, peer, "result", roles["S"])
    if res is None:
        return "missing", "no sentinel result", None
    if not _handed(ctx, step, peer, roles["S"], res):
        return "missing", "sentinel not delivered", None
    body = _body(res)
    if body.get("status") == "done":
        return "fail", "sentinel done", None
    if body.get("status") != "rejected" or body.get("reason") != reason:
        return "fail", f"sentinel not {reason}", None
    return _read_vs(ctx, step, peer, roles, "B")


def _n4(peer, ctx):
    roles = _roles(ctx, "N4", peer)
    if roles is None:
        return "missing", "no expect", None
    if _done_in(ctx, "N4", peer, roles["a"]) is None or _done_in(ctx, "N4", peer, roles["b"]) is None:
        return "missing", "a or b not done", None
    if not _cut_then_poll(ctx, "N4", peer):
        return "missing", "no cut", None
    verdict = _repeat_dup(ctx, "N4", peer, roles["a"])
    if verdict != "pass":
        return verdict, "dup false" if verdict == "fail" else "no repeat result", None
    return _read_vs(ctx, "N4", peer, roles, "b")


def _n5(peer, ctx):
    roles = _roles(ctx, "N5", peer)
    if roles is None:
        return "missing", "no expect", None
    repeat = _repeat_enq(ctx, "N5", peer, roles["c"])
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
    if _done_in(ctx, "N5", peer, roles["d"]) is None:
        res_d = _in_step(ctx, "N5", peer, "result", roles["d"])
        if res_d is None:
            return "missing", "d missing", None
        return "fail", "d not done", None
    verdict = _repeat_dup(ctx, "N5", peer, roles["c"])
    if verdict != "pass":
        return verdict, "dup false" if verdict == "fail" else "no repeat result", None
    return _read_vs(ctx, "N5", peer, roles, "d")


def _n6(ctx):
    if ctx["skipped"].get("__n6__"):
        return "missing", "resume_timeout", None
    roles = _roles(ctx, "N6", "client")
    if roles is None:
        return "missing", "no expect", None
    if "pre_log" not in roles:
        return "missing", "no pre_log", None
    pre_res = _in_step(ctx, "N6", "client", "result", roles["pre_log"])
    if pre_res is None:
        return "missing", "no pre_log result", None
    pre_body = _body(pre_res)
    pre_read = pre_body.get("read") if isinstance(pre_body.get("read"), dict) else {}
    if pre_body.get("status") != "done" or "rpc_log" not in (pre_read.get("has") or []):
        return "missing", "pre_log not done", None
    boundary_ms = pre_body.get("done_ms")
    if not _finite(boundary_ms):
        raise EvidenceError("pre_log invalid done_ms")

    burst = _in_step(ctx, "N6", "client", "enq", roles["burst"])
    log_res = _in_step(ctx, "N6", "client", "result", roles["log"])
    if burst is None or log_res is None:
        return "missing", "no burst or log", None
    args = _args(burst)
    seq0 = args.get("seq0")
    count = args.get("count")
    if (
        isinstance(seq0, bool)
        or not isinstance(seq0, int)
        or isinstance(count, bool)
        or not isinstance(count, int)
        or count <= 0
    ):
        raise EvidenceError("rpc_burst invalid seq0/count")

    log_body = _body(log_res)
    read = log_body.get("read") if isinstance(log_body.get("read"), dict) else {}
    if log_body.get("status") != "done" or "rpc_log" not in (read.get("has") or []):
        return "missing", "rpc_log absent", None
    raw_log = read.get("rpc_log")
    if not isinstance(raw_log, list):
        raise EvidenceError("rpc_log is not a list")
    for entry in raw_log:
        if not isinstance(entry, dict) or "seq" not in entry or "decision" not in entry:
            raise EvidenceError("rpc_log entry missing seq/decision")
        if "lease_age_ms" not in entry or "recv_ms" not in entry:
            raise EvidenceError("rpc_log entry missing lease_age_ms/recv_ms")

    expected_seqs = range(seq0, seq0 + count)
    log = [
        entry
        for entry in raw_log
        if entry["seq"] in expected_seqs
        and (not _finite(entry["recv_ms"]) or entry["recv_ms"] > boundary_ms)
    ]
    if not log and raw_log:
        return "fail", "stale rpc_log from previous burst", None
    seqs = [entry["seq"] for entry in log]
    if any(s not in seqs for s in expected_seqs):
        return "missing", "seq missing", None

    decisions = {e["decision"] for e in log}
    accepted = [e for e in log if e["decision"] == "accepted"]
    rejected = [e for e in log if e["decision"] == "rejected_lease"]
    lease = ctx["lease"]

    def _age_holds(entry, over):
        age = entry.get("lease_age_ms")
        if not _finite(age):
            return False
        return age > lease if over else age <= lease

    finite_ages = [e["lease_age_ms"] for e in accepted if _finite(e.get("lease_age_ms"))]
    if accepted and not all(_age_holds(e, False) for e in accepted):
        metrics = {}
        if finite_ages:
            metrics["window_accept_max_ms"] = max(finite_ages)
        return "fail", "lease_age outside window", metrics or None
    if not accepted or not rejected or decisions - {"accepted", "rejected_lease"}:
        return "missing", "lease window not both sides", None
    reject_ages = [e["lease_age_ms"] for e in rejected if _finite(e.get("lease_age_ms"))]
    metrics = {
        "window_accept_max_ms": max(finite_ages),
        "window_reject_min_ms": min(reject_ages) if reject_ages else None,
    }
    bounds_ok = all(_age_holds(e, True) for e in rejected)

    def _stamp(entry):
        return _finite(entry.get("recv_ms")) and _finite(entry.get("seq"))

    if all(_stamp(e) for e in accepted) and all(_stamp(e) for e in rejected):
        first_reject = min(rejected, key=lambda e: (e["recv_ms"], e["seq"]))
        order_ok = not any((e["recv_ms"], e["seq"]) > (first_reject["recv_ms"], first_reject["seq"]) for e in accepted)
        last = max(accepted, key=lambda e: (e["recv_ms"], e["seq"]))
    else:
        order_ok = False
        last = None
    k = last["seq"] if last is not None else None
    p0 = args.get("pos")
    if not isinstance(p0, list) or len(p0) != 3 or not all(_finite(v) for v in p0):
        raise EvidenceError("rpc_burst missing pos")
    expect = [p0[0] + (k - seq0), p0[1], p0[2]] if k is not None and _finite(k) else None
    pose_res = _in_step(ctx, "N6", "client", "result", roles["read"])
    if pose_res is None:
        return "missing", "no pose read", metrics
    pose_body = _body(pose_res)
    pose_read = pose_body.get("read") if isinstance(pose_body.get("read"), dict) else {}
    pose_has = pose_read.get("has") or []
    if pose_body.get("status") != "done" or "pos" not in pose_has or "ypr" not in pose_has:
        return "missing", "pose read not done", metrics
    pose_ok = expect is not None and _pose_match(pose_read, expect, [90, 0, 0])
    if not bounds_ok:
        return "fail", "lease_age outside window", metrics
    if not order_ok:
        return "fail", "accepted after rejected_lease", metrics
    status, detail = _n6_pose_check(accepted, lease, seq0, p0, pose_read, pose_ok)
    return status, detail, metrics


_N6_APPLY_KEYS = ("apply_ms", "apply_lease_age_ms", "applied_b")


def _n6_has_apply_record(entry):
    applied = entry.get("applied_b")
    return (
        _finite(entry.get("apply_ms"))
        and _finite(entry.get("apply_lease_age_ms"))
        and not isinstance(applied, bool)
        and applied in (0, 1)
    )


def _n6_pose_check(accepted, lease, seq0, p0, pose_read, pose_ok):
    """Pose final de N6 alineada con F02-H3 (`plans/2026-11-14-m1-f0.3-0-brief.md:669-673`).

    El peer aplica la pose aceptada en el frame siguiente y la descarta si en ese frame su lease ya no
    vale (`fake_peer.py`, `_apply`). Solo el registro del propio peer acredita un descarte: en cada
    aceptada del `rpc_log`, `apply_ms`, `apply_lease_age_ms` y `applied_b`, anotados al aplicar.
    - **Cada registro presente se valida siempre,** aunque falten otros: un registro a medias o mal
      formado es FALLA, y uno que contradiga el lease en ese instante (aplicada si y solo si
      `apply_lease_age_ms <= lease`) tambien.
    - **Con registro en todas las aceptadas:** la pose leida tiene que ser la de la ultima aplicada. Si no
      se aplico ninguna, la pose de antes de la rafaga no esta en la evidencia: `missing`.
    - **Sin registro completo** (la sonda real todavia no lo da): con la pose de la ultima aceptada,
      `pass`, salvo que su propio registro diga que se descarto. Cualquier otra pose es `missing`, nunca
      `pass` ni `fail`: sin identidad de frame ni de aplicacion no se puede acreditar que pose debia
      quedar. Que el lease caducara antes de leer no acredita nada, porque en la rafaga todas las
      aceptadas comparten caducidad.
    """
    ordered = sorted(accepted, key=lambda e: (e["recv_ms"], e["seq"]))
    if not ordered:
        return "missing", "no accepted entries"
    for entry in ordered:
        present = [key for key in _N6_APPLY_KEYS if key in entry]
        if not present:
            continue
        if len(present) != len(_N6_APPLY_KEYS) or not _n6_has_apply_record(entry):
            return "fail", "malformed apply record"
        if entry["apply_ms"] < entry["recv_ms"]:
            return "fail", "pose applied before received"
        if bool(entry["applied_b"]) != (entry["apply_lease_age_ms"] <= lease):
            return "fail", "pose apply contradicts lease"
    if not all(_n6_has_apply_record(e) for e in ordered):
        if pose_ok:
            last_entry = ordered[-1]
            if _n6_has_apply_record(last_entry) and last_entry["applied_b"] == 0:
                return "fail", "pose contradicts apply record"
            return "pass", ""
        return "missing", "pose mismatch without apply evidence"
    applied = [e for e in ordered if e["applied_b"] == 1]
    if not applied:
        return ("fail", "pose applied without apply record") if pose_ok else ("missing", "no burst pose applied")
    last_applied = max(applied, key=lambda e: (e["apply_ms"], e["recv_ms"], e["seq"]))
    expect_j = [p0[0] + (last_applied["seq"] - seq0), p0[1], p0[2]]
    if not _pose_match(pose_read, expect_j, [90, 0, 0]):
        return "fail", "pose is not last applied"
    if last_applied is ordered[-1]:
        return "pass", ""
    return "pass", "pose discarded after lease expiry"


def _n6_server(ctx):
    if ctx["skipped"].get("__n6__"):
        return "missing", "resume_timeout", None
    roles = _roles(ctx, "N6", "server")
    if roles is None:
        return "missing", "no expect", None
    burst_id = roles.get("burst")
    emit_pages = roles.get("emit_pages")
    if not isinstance(burst_id, str) or not isinstance(emit_pages, list) or not emit_pages:
        return "missing", "missing burst or emit_pages", None

    burst_enq = _in_step(ctx, "N6", "server", "enq", burst_id)
    burst_res = _in_step(ctx, "N6", "server", "result", burst_id)
    if burst_enq is None or burst_res is None:
        return "missing", "no server burst or result", None
    if not _cut_then_poll(ctx, "N6", "server"):
        return "missing", "no server cut", None

    burst_body = _body(burst_res)
    burst_ok = (
        burst_body.get("status") == "error"
        and burst_body.get("reason") == "lease_expired"
        and burst_body.get("dup") is False
    )

    all_rows = []
    expected_pages = None
    expected_total = None
    for idx, pid in enumerate(emit_pages):
        pres = _in_step(ctx, "N6", "server", "result", pid)
        if pres is None:
            if not burst_ok:
                return "fail", "burst not error/lease_expired", None
            return "missing", "missing emitlog page result", None
        pbody = _body(pres)
        pread = pbody.get("read") if isinstance(pbody.get("read"), dict) else {}
        if (
            pbody.get("status") != "done"
            or pbody.get("dup") is not False
            or "payload" not in (pread.get("has") or [])
        ):
            if not burst_ok:
                return "fail", "burst not error/lease_expired", None
            return "missing", "emitlog page not done", None
        try:
            unpacked = wire.unpack_payload(pread)
        except ValueError as exc:
            raise EvidenceError(f"invalid emitlog payload: {exc}") from exc
        nums = unpacked["num"]
        if "page_n" not in nums or "pages_n" not in nums or "rows_total_n" not in nums:
            raise EvidenceError("emitlog page missing pagination scalars")
        if int(nums["page_n"]) != idx:
            return "missing", "emitlog page_n mismatch", None
        p_n = int(nums["pages_n"])
        tot_n = int(nums["rows_total_n"])
        if expected_pages is None:
            expected_pages = p_n
            expected_total = tot_n
        elif p_n != expected_pages or tot_n != expected_total:
            return "missing", "emitlog pagination changed across pages", None
        all_rows.extend(unpacked["rows"])

    if expected_pages is not None and expected_pages > 0 and len(emit_pages) != expected_pages:
        if not burst_ok:
            return "fail", "burst not error/lease_expired", None
        return "missing", "incomplete emitlog pages", None
    if expected_total is not None and len(all_rows) != expected_total:
        if not burst_ok:
            return "fail", "burst not error/lease_expired", None
        return "missing", "emitlog rows_total_n mismatch", None

    required_cols = ("seq_n", "tick_ms", "lease_age_ms", "idx_n", "op_id", "outcome")
    for row in all_rows:
        if any(col not in row for col in required_cols):
            raise EvidenceError("emitlog row missing required columns")

    own_rows = [row for row in all_rows if row["op_id"] == burst_id]
    if not own_rows:
        return "fail", "no emit rows for current burst", None

    if not all(
        _finite(r["seq_n"]) and _finite(r["tick_ms"]) and _finite(r["lease_age_ms"]) and _finite(r["idx_n"])
        for r in own_rows
    ):
        return "fail", "non-finite emitlog fields", None

    outcomes = {r["outcome"] for r in own_rows}
    if outcomes - {"sent", "blocked_lease"}:
        return "fail", "unexpected emit outcome", None

    sent = [r for r in own_rows if r["outcome"] == "sent"]
    blocked = [r for r in own_rows if r["outcome"] == "blocked_lease"]
    lease = ctx["lease"]

    metrics = {}
    if sent:
        metrics["server_window_accept_max_ms"] = max(r["lease_age_ms"] for r in sent)
    if blocked:
        metrics["server_window_reject_min_ms"] = min(r["lease_age_ms"] for r in blocked)

    if not sent:
        return "fail", "no sent rows for current burst", metrics or None
    if not all(r["lease_age_ms"] <= lease for r in sent):
        return "fail", "sent lease_age outside window", metrics or None
    if not blocked or not all(r["lease_age_ms"] > lease for r in blocked):
        return "fail", "missing or invalid blocked_lease", metrics or None

    first_blk_idx = min(r["idx_n"] for r in blocked)
    first_blk_stamp = min((r["tick_ms"], r["seq_n"]) for r in blocked)
    if any(
        r["idx_n"] > first_blk_idx or (r["tick_ms"], r["seq_n"]) > first_blk_stamp
        for r in sent
    ):
        return "fail", "sent after blocked_lease", metrics

    if not burst_ok:
        return "fail", "burst did not end with error/lease_expired", metrics

    return "pass", "", metrics


def _read_vs(ctx, step, peer, roles, source_role):
    res = _in_step(ctx, step, peer, "result", roles["read"])
    if res is None:
        return "missing", "no read", None
    body = _body(res)
    if body.get("status") != "done":
        return "missing", "read not done", None
    src = _in_step(ctx, step, peer, "enq", roles[source_role])
    if src is None:
        return "missing", "no source enq", None
    read = body.get("read") or {}
    need = ("fog",) if peer == "server" else ("pos", "ypr")
    has = read.get("has") or []
    if any(name not in has for name in need):
        return "missing", "read fields", None
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
        if (
            ev["ev"] == "hello"
            and ev.get("peer") == peer
            and ev.get("http", 200) == 200
            and ev.get("ok", True) is True
            and ev["t_ms"] > t0
        ):
            return True
    return False


def _span(ctx, step, peer):
    start = end = None
    for ev in ctx["scenario"]:
        if ev.get("step") != step or ev.get("peer") != peer:
            continue
        if ev["ev"] == "step_start" and start is None:
            start = ev["t_ms"]
        elif ev["ev"] == "step_end" and start is not None and end is None:
            end = ev["t_ms"]
    if start is None or end is None or end < start:
        return None
    return start, end


def _during(ctx, step, peer):
    window = _span(ctx, step, peer)
    if window is None:
        return []
    start, end = window
    return [ev for ev in ctx["bridge"] if start <= ev["t_ms"] <= end]


def _in_step(ctx, step, peer, ev_name, op_id):
    for ev in _during(ctx, step, peer):
        if ev["ev"] == ev_name and ev.get("op_id") == op_id:
            return ev
    return None


def _done_in(ctx, step, peer, op_id):
    for ev in _during(ctx, step, peer):
        if ev["ev"] == "result" and ev.get("op_id") == op_id and _body(ev).get("status") == "done":
            return ev
    return None


def _handed(ctx, step, peer, op_id, before):
    limit = ctx["index"][id(before)]
    for ev in _during(ctx, step, peer):
        if ctx["index"][id(ev)] >= limit:
            break
        if ev.get("op_id") == op_id and ev["ev"] == "deliver":
            return True
    return False


def _cut_then_poll(ctx, step, peer):
    started = None
    end = None
    for ev in _during(ctx, step, peer):
        if ev.get("peer") != peer:
            continue
        if ev["ev"] == "cut_start" and started is None:
            started = ev
        elif ev["ev"] == "cut_end" and started is not None and ctx["index"][id(ev)] > ctx["index"][id(started)]:
            end = ev
            break
    if started is None or end is None:
        return False
    mi = ctx["index"][id(end)]
    for ev in _during(ctx, step, peer):
        if (
            ev["ev"] == "poll"
            and ev.get("peer") == peer
            and ev.get("http") == 200
            and ctx["index"][id(ev)] > mi
        ):
            return True
    return False


def _repeat_enq(ctx, step, peer, op_id):
    enqs = [e for e in _during(ctx, step, peer) if e["ev"] == "enq" and e.get("op_id") == op_id]
    if len(enqs) < 2:
        return None
    return enqs[-1]


def _repeat_dup(ctx, step, peer, op_id):
    mark = _repeat_enq(ctx, step, peer, op_id)
    if mark is None:
        return "missing"
    mi = ctx["index"][id(mark)]
    window = _span(ctx, step, peer)
    later = [
        ev
        for ev in ctx["bridge"]
        if ev["ev"] == "result" and ev.get("op_id") == op_id and ctx["index"][id(ev)] > mi
    ]
    if not later:
        return "missing"
    in_window = False
    for ev in later:
        body = _body(ev)
        if body.get("status") != "done" or body.get("dup") is not True:
            return "fail"
        if window is not None and window[0] <= ev["t_ms"] <= window[1]:
            in_window = True
    return "pass" if in_window else "missing"


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


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _fog_match(read, fog):
    if not isinstance(read, dict):
        return False
    if "fog" not in (read.get("has") or []) or not _finite(read.get("fog")) or not _finite(fog):
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
    if not all(_finite(v) for v in list(read["pos"]) + list(pos) + list(read["ypr"]) + list(ypr)):
        return False
    dist = math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(read["pos"], pos)))
    if not _finite(dist) or dist > 0.05:
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


RESULT_FIELDS = (
    "done_ms",
    "dup",
    "frame_done",
    "frame_recv",
    "op_id",
    "read",
    "reason",
    "recv_ms",
    "status",
)
READ_FIELDS = ("fog", "frame", "has", "pos", "rpc_log", "tick_s", "y", "ypr")


def _validate_results(bridge):
    first_enq = {}
    for ev in bridge:
        if ev["ev"] == "enq" and ev.get("op_id") is not None:
            first_enq.setdefault(ev["op_id"], ev["t_ms"])
        elif ev["ev"] == "result":
            _require_result(ev.get("result"))
    for ev in bridge:
        if ev["ev"] != "result":
            continue
        op_id = ev.get("op_id")
        if op_id in first_enq and (
            not _finite(ev.get("t_ms")) or not _finite(first_enq[op_id]) or ev["t_ms"] < first_enq[op_id]
        ):
            raise EvidenceError("result registered before its enq")


def _require_result(body):
    if not isinstance(body, dict):
        raise EvidenceError("result event missing result")
    missing = [name for name in RESULT_FIELDS if name not in body]
    if missing:
        raise EvidenceError("RESULT missing " + ",".join(missing))
    read = body.get("read")
    if not isinstance(read, dict):
        raise EvidenceError("RESULT missing read")
    missing_read = [name for name in READ_FIELDS if name not in read]
    if missing_read:
        raise EvidenceError("READ missing " + ",".join(missing_read))


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
        if events and obj["t_ms"] < events[-1]["t_ms"]:
            raise EvidenceError(f"{path.name}:{lineno}: t_ms went backwards")
        events.append(obj)
    return events
