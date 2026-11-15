"""Evaluador puro de la evidencia de F1b-peers en partida.

Contrato: qa/live/EVIDENCIA.md. `evaluate()` solo lee la carpeta y devuelve el
verdict; el CLI es el unico que escribe `verdict.json`.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROW_IDS = tuple(f"G{n}" for n in range(1, 10))
SCRIPT_LOGS = ("server_script.log", "client_script.log")
RPT_LOGS = ("server.RPT", "client.RPT")
# El motor rellena con espacios: "SCRIPT    (E): Leaked 'DSBX_Callback' ..." (RPT y script_*.log).
_SCRIPT_ERROR = re.compile(r"SCRIPT\s+\(E\)")
PEER_LOG = {"server": "server_script.log", "client": "client_script.log"}
EXIT = {"PASA": 0, "FALLA": 1, "INCONCLUSO": 2}
RECOVERY_LIMIT_MS = 60000.0


class EvidenceError(Exception):
    pass


def evaluate(evidence_dir):
    directory = Path(evidence_dir)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        rows = {gid: _row("INCONCLUSO", "manifest.json ausente", {}) for gid in ROW_IDS}
        return _aggregate(rows)
    try:
        manifest = _read_json(manifest_path)
    except EvidenceError as exc:
        rows = {gid: _row("INCONCLUSO", str(exc), {}) for gid in ROW_IDS}
        return _aggregate(rows)
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        scenarios = []
    dirty = manifest.get("git_dirty") is True
    rows = {}
    for gid in scenarios:
        if gid not in ROW_IDS:
            continue
        rows[gid] = _eval_row(directory, manifest, gid, dirty)
    return _aggregate(rows)


def _aggregate(rows):
    verdicts = [row["verdict"] for row in rows.values()]
    if "FALLA" in verdicts:
        aggregate = "FALLA"
    elif "INCONCLUSO" in verdicts:
        aggregate = "INCONCLUSO"
    else:
        aggregate = "PASA"
    return {"aggregate": aggregate, "rows": rows}


def _row(verdict, reason, metrics):
    return {"verdict": verdict, "reason": reason, "metrics": metrics}


def _eval_row(directory, manifest, gid, dirty):
    if dirty:
        return _row("INCONCLUSO", "git_dirty: true", {})
    sample = directory / "samples" / f"{gid}.jsonl"
    if not sample.is_file():
        return _row("INCONCLUSO", f"sin samples/{gid}.jsonl", {})
    try:
        scenario = _read_events(sample)
    except EvidenceError as exc:
        return _row("INCONCLUSO", str(exc), {})
    ends = [ev for ev in scenario if ev.get("ev") == "end"]
    if not ends:
        return _row("INCONCLUSO", "sin end", {})
    if ends[-1].get("status") == "aborted":
        reason = ends[-1].get("reason")
        return _row("INCONCLUSO", f"end aborted: {reason}", {})
    confirmed, why = _rules_confirmed(scenario)
    if not confirmed:
        return _row("INCONCLUSO", why, {})
    ctx = _context(directory, manifest, scenario)
    try:
        verdict, reason, metrics = _ROWS[gid](ctx)
    except EvidenceError as exc:
        verdict, reason, metrics = "INCONCLUSO", str(exc), {}
    except Exception as exc:  # una fila rota no tumba el resto
        verdict, reason, metrics = "INCONCLUSO", f"excepcion en {gid}: {exc}", {}
    return _row(verdict, reason, metrics)


def _context(directory, manifest, scenario):
    return {
        "dir": directory,
        "manifest": manifest,
        "scenario": scenario,
        "_logs": {},
        "_proxy": None,
        "_proxy_loaded": False,
    }


def _rules_confirmed(scenario):
    for ev in scenario:
        if ev.get("ev") != "rules":
            continue
        version = ev.get("version")
        active = any(
            other.get("ev") == "rules_active"
            and other.get("version") == version
            and _num(other.get("t_ms"))
            and _num(ev.get("t_ms"))
            and other["t_ms"] >= ev["t_ms"]
            for other in scenario
        )
        if not active:
            return False, f"rules {version} sin rules_active"
    return True, ""


def _log(ctx, name):
    if name not in ctx["_logs"]:
        path = ctx["dir"] / "logs" / name
        if not path.is_file():
            ctx["_logs"][name] = None
        else:
            try:
                ctx["_logs"][name] = parse_script_log(path)
            except EvidenceError:
                ctx["_logs"][name] = None
    return ctx["_logs"][name]


def _proxy(ctx):
    if not ctx["_proxy_loaded"]:
        ctx["_proxy_loaded"] = True
        path = ctx["dir"] / "samples" / "proxy.jsonl"
        if path.is_file():
            ctx["_proxy"] = _read_proxy(path)
    return ctx["_proxy"]


def _missing_logs(ctx, names):
    return [name for name in names if not (ctx["dir"] / "logs" / name).is_file()]


def _events(ctx, name):
    return [ev for ev in ctx["scenario"] if ev.get("ev") == name]


def _effects(ctx):
    seen = set()
    effects = []
    for name in SCRIPT_LOGS:
        for ev in _log(ctx, name) or []:
            if ev.get("kind") != "effect":
                continue
            key = (ev.get("step"), ev.get("session"), ev.get("op"), ev.get("tick_ms"))
            if key in seen:
                continue
            seen.add(key)
            effects.append(ev)
    return effects


def _all_lines(ctx):
    lines = []
    for name in SCRIPT_LOGS:
        lines.extend(_log(ctx, name) or [])
    lines.sort(key=lambda ev: ev.get("tick_ms") if _num(ev.get("tick_ms")) else -1)
    return lines


def _script_errors(ctx):
    errors = []
    for name in SCRIPT_LOGS + RPT_LOGS:
        for ev in _log(ctx, name) or []:
            if ev.get("kind") == "script_error":
                errors.append(ev)
    return errors


def _pair_map(effects, op):
    pairs = {}
    for ev in effects:
        if ev.get("op") != op:
            continue
        group = pairs.setdefault(ev.get("session"), {"retirar": 0, "anotar": 0})
        if ev.get("step") in group:
            group[ev["step"]] += 1
    return pairs


def _exact_pair(pairs):
    if not pairs:
        return False, "sin effects"
    if len(pairs) != 1:
        return False, f"effects en {len(pairs)} sesiones"
    group = next(iter(pairs.values()))
    if group["retirar"] != 1 or group["anotar"] != 1:
        return False, f"retirar={group['retirar']} anotar={group['anotar']}"
    return True, ""


def _op_effects(effects, op):
    return [ev for ev in effects if ev.get("op") == op]


def _recovery(ctx, anchor, anchors):
    t0 = anchor.get("t_ms")
    if not _num(t0):
        return False, None, "ancla sin t_ms"
    limit = math.inf
    for other in anchors:
        if _num(other) and other > t0:
            limit = min(limit, other)
    candidates = [
        ev
        for ev in _events(ctx, "recovery")
        if _num(ev.get("t_ms")) and t0 <= ev["t_ms"] < limit
    ]
    if not candidates:
        return False, None, "sin recovery"
    rec = candidates[0]
    op = rec.get("op_id")
    observed = [
        ev
        for ev in _events(ctx, "op_state")
        if ev.get("op_id") == op
        and ev.get("state") == "observado"
        and _num(ev.get("t_ms"))
        and ev["t_ms"] >= rec["t_ms"]
    ]
    if not observed:
        return False, None, "recovery sin observado"
    latency = observed[0]["t_ms"] - t0
    if latency > RECOVERY_LIMIT_MS:
        return False, latency, "recuperacion > 60 s"
    return True, latency, ""


def _g1(ctx):
    manifest = ctx["manifest"]
    if manifest.get("fake") is True:
        return "INCONCLUSO", "fake: G1 no se evalua", {"fake": True}
    missing = _missing_logs(ctx, SCRIPT_LOGS + RPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    errors = _script_errors(ctx)
    connected = sorted(
        {ev.get("peer") for ev in _events(ctx, "connected") if ev.get("peer") in PEER_LOG}
    )
    metrics = {"connected": connected, "script_errors": len(errors)}
    if errors:
        return "FALLA", "error de script DSBX_ en logs/RPT", metrics
    if len(connected) != 2:
        return "FALLA", "sin connected de los dos peers", metrics
    if manifest.get("build") == "retail":
        alive = _events(ctx, "client_alive")
        if not alive:
            return "INCONCLUSO", "sin client_alive en retail", metrics
        metrics["client_alive_connected"] = bool(alive[-1].get("connected"))
        if not alive[-1].get("connected"):
            return "FALLA", "client_alive.connected falso", metrics
    return "PASA", "", metrics


def _g2(ctx):
    proxy = _proxy(ctx)
    if proxy is None:
        return "INCONCLUSO", "sin samples/proxy.jsonl", {}
    photos = _events(ctx, "bridge")
    good = None
    for ev in photos:
        server = ev.get("server")
        client = ev.get("client")
        catalog = ev.get("catalog")
        if not isinstance(server, dict) or not isinstance(client, dict) or not isinstance(catalog, dict):
            continue
        if (
            server.get("epoch") == client.get("epoch")
            and catalog.get("complete") is True
            and isinstance(catalog.get("n_classes"), int)
            and not isinstance(catalog.get("n_classes"), bool)
            and catalog["n_classes"] > 0
        ):
            good = ev
            break
    metrics = {"bridge_photos": len(photos)}
    if good is None:
        return "FALLA", "sin foto bridge con epochs iguales y catalogo completo", metrics
    fake = ctx["manifest"].get("fake") is True
    catalog_entries = [
        ev
        for ev in proxy
        if ev.get("route") == "catalog"
        and ev.get("upstream_status") == 200
        and _num(ev.get("req_bytes"))
    ]
    metrics["catalog_200"] = len(catalog_entries)
    if fake:
        metrics["catalog_req_bytes"] = "no aplica (fake)"
    elif not catalog_entries:
        return "INCONCLUSO", "sin respuesta catalog 200 en proxy", metrics
    else:
        biggest = max(catalog_entries, key=lambda ev: ev["req_bytes"])
        metrics["catalog_max_req_bytes"] = biggest["req_bytes"]
        if not 3000 <= biggest["req_bytes"] <= 3499:
            return "FALLA", "req_bytes de catalog fuera de [3000,3499]", metrics
    hellos = [
        ev
        for ev in proxy
        if ev.get("route") == "hello"
        and ev.get("peer") == "server"
        and ev.get("upstream_status") == 200
        and _num(ev.get("req_bytes"))
    ]
    if not hellos:
        return "INCONCLUSO", "sin hello 200 del servidor", metrics
    metrics["server_hello_req_bytes"] = max(ev["req_bytes"] for ev in hellos)
    if any(ev["req_bytes"] >= 3500 for ev in hellos):
        return "FALLA", "req_bytes del hello del servidor >= 3500", metrics
    return "PASA", "", metrics


def _g3(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    effects = _effects(ctx)
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G3", {}
    anchors = [case.get("t_ms") for case in cases if _num(case.get("t_ms"))]
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        op = case.get("op_id")
        entry = {"pairs": {}}
        metrics["cases"][str(name)] = entry
        if op is None:
            problems.append(f"{name}: sin op_id")
            continue
        pairs = _pair_map(effects, op)
        entry["pairs"] = pairs
        if name in ("a", "b"):
            ok, detail = _exact_pair(pairs)
            if not ok:
                problems.append(f"{name}: {detail}")
            observed = [
                ev
                for ev in _events(ctx, "op_state")
                if ev.get("op_id") == op and ev.get("state") == "observado"
            ]
            if not observed:
                problems.append(f"{name}: sin observado")
        elif name == "c":
            states = [ev for ev in _events(ctx, "op_state") if ev.get("op_id") == op]
            if any(ev.get("state") == "observado" for ev in states):
                problems.append("c: llego a observado")
            if not any(
                ev.get("state") == "fallido" and ev.get("reason") == "lectura_no_cumple"
                for ev in states
            ):
                problems.append("c: sin fallido/lectura_no_cumple")
            if pairs:
                problems.append("c: con effects")
        else:
            problems.append(f"caso desconocido {name}")
        ok, latency, why = _recovery(ctx, case, anchors)
        entry["recovery_ms"] = latency
        if not ok:
            problems.append(f"{name}: {why}")
    if problems:
        return "FALLA", "; ".join(problems), metrics
    return "PASA", "", metrics


def _g4(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS + ("inventory.json",))
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    proxy = _proxy(ctx) or []
    effects = _effects(ctx)
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G4", {}
    bad = _events(ctx, "bad_key_window")
    stale = _events(ctx, "stale_order")
    anchors = [case.get("t_ms") for case in cases if _num(case.get("t_ms"))]
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        op = case.get("op_id")
        metrics["cases"][str(name)] = {}
        if op is None:
            problems.append(f"{name}: sin op_id")
            continue
        if name == "a":
            if not bad:
                return "INCONCLUSO", "sin bad_key_window", metrics
            window = bad[0]
            start = window.get("t_start_ms")
            end = window.get("t_end_ms")
            if not (_num(start) and _num(end)):
                return "INCONCLUSO", "bad_key_window sin ventana", metrics
            hellos = [
                ev
                for ev in proxy
                if ev.get("route") == "hello"
                and ev.get("peer") == "server"
                and ev.get("upstream_status") == 401
                and _num(ev.get("t_ms"))
                and start <= ev["t_ms"] <= end
            ]
            if not hellos:
                problems.append("a: sin hello 401 del servidor en la ventana")
            bad_ok = [
                ev
                for ev in proxy
                if ev.get("route") == "hello"
                and ev.get("peer") == "server"
                and ev.get("upstream_status") == 200
                and _num(ev.get("t_ms"))
                and start <= ev["t_ms"] <= end
            ]
            if bad_ok:
                problems.append("a: hello 200 del servidor con clave mala")
            window_effects = [
                ev
                for ev in effects
                if _num(ev.get("tick_ms")) and start <= ev["tick_ms"] <= end
            ]
            if window_effects:
                problems.append("a: effect en la ventana")
            if _op_effects(effects, op):
                problems.append("a: effect para la op")
            metrics["cases"]["a"] = {
                "hellos_401": len(hellos),
                "effects_in_window": len(window_effects),
            }
        elif name == "b":
            if not stale:
                return "INCONCLUSO", "sin stale_order", metrics
            if _op_effects(effects, op):
                problems.append("b: effect para la op stale")
            results = [ev for ev in _events(ctx, "result_seen") if ev.get("op_id") == op]
            if results:
                last = results[-1]
                if not (last.get("status") == "rejected" and last.get("reason") == "stale_session"):
                    problems.append("b: resultado no rejected/stale_session")
            metrics["cases"]["b"] = {"results": len(results)}
        elif name == "c":
            states = [ev for ev in _events(ctx, "op_state") if ev.get("op_id") == op]
            if not any(
                ev.get("state") == "fallido" and ev.get("reason") == "conexion_perdida"
                for ev in states
            ):
                problems.append("c: sin fallido/conexion_perdida")
            if _op_effects(effects, op):
                problems.append("c: effect para la op")
        else:
            problems.append(f"caso desconocido {name}")
        ok, latency, why = _recovery(ctx, case, anchors)
        metrics["cases"].setdefault(str(name), {})["recovery_ms"] = latency
        if not ok:
            problems.append(f"{name}: {why}")
    scans = _events(ctx, "key_scan")
    if not scans:
        return "INCONCLUSO", "sin key_scan", metrics
    scan = scans[-1]
    hits = scan.get("hits")
    metrics["key_scan_hits"] = hits
    if hits != 0:
        problems.append(f"key_scan.hits={hits}")
    inventory = _inventory_paths(ctx)
    if inventory is None:
        return "INCONCLUSO", "inventory.json ilegible", metrics
    if not inventory:
        return "INCONCLUSO", "inventario vacio", metrics
    files = scan.get("files")
    if not isinstance(files, list):
        return "INCONCLUSO", "key_scan.files no es lista", metrics
    uncovered = _uncovered(inventory, files)
    metrics["inventory_paths"] = len(inventory)
    metrics["key_scan_files"] = len(files)
    if uncovered:
        problems.append("key_scan.files no cubre: " + ", ".join(uncovered[:3]))
    if problems:
        return "FALLA", "; ".join(problems), metrics
    return "PASA", "", metrics


def _g5(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    lease = _manifest_int(ctx, "lease_ms")
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G5", {}
    windows = _events(ctx, "window")
    anchors = [case.get("t_ms") for case in cases if _num(case.get("t_ms"))]
    effects = _effects(ctx)
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        peer = case.get("peer")
        op = case.get("op_id")
        entry = {}
        metrics["cases"][str(name)] = entry
        if op is None:
            problems.append(f"{name}: sin op_id")
            continue
        if name == "a2500":
            window = _window_for(case, windows)
            if window is None:
                return "INCONCLUSO", "sin window para a2500", metrics
            start = window.get("t_start_ms")
            end = window.get("t_end_ms")
            if not (_num(start) and _num(end)):
                return "INCONCLUSO", "window sin ventana", metrics
            responses = [
                ev
                for ev in _proxy(ctx) or []
                if ev.get("peer") == peer
                and ev.get("upstream_status") == 200
                and _num(ev.get("t_done_ms"))
            ]
            inside = [ev for ev in responses if start <= ev["t_done_ms"] <= end]
            after = [ev for ev in responses if ev["t_done_ms"] > end]
            if after:
                inside.append(min(after, key=lambda ev: ev["t_done_ms"]))
            times = sorted(ev["t_done_ms"] for ev in inside)
            if len(times) < 2:
                return "INCONCLUSO", "sin dos respuestas 200 en la ventana", metrics
            gaps = [b - a for a, b in zip(times, times[1:])]
            entry["responses"] = len(times)
            entry["max_gap_ms"] = max(gaps)
            if max(gaps) >= lease:
                problems.append(f"a2500: hueco {max(gaps)} >= lease_ms")
            lost = [
                ev
                for ev in _log(ctx, PEER_LOG.get(peer, "")) or []
                if ev.get("kind") == "lease_lost"
                and _num(ev.get("tick_ms"))
                and start <= ev["tick_ms"] <= end
            ]
            if lost:
                problems.append("a2500: lease lost en la ventana")
        elif name == "a4500":
            log_name = PEER_LOG.get(peer)
            if log_name is None:
                return "INCONCLUSO", "a4500 sin peer valido", metrics
            lost = [
                ev
                for ev in _log(ctx, log_name) or []
                if ev.get("kind") == "lease_lost"
                and _num(ev.get("age_ms"))
                and lease <= ev["age_ms"] < lease + 200
            ]
            entry["lease_lost"] = len(lost)
            if not lost:
                problems.append("a4500: sin lease lost en [lease, lease+200)")
        elif name == "b2500":
            pairs = _pair_map(effects, op)
            ok, detail = _exact_pair(pairs)
            if not ok:
                problems.append(f"b2500: {detail}")
            observed = [
                ev
                for ev in _events(ctx, "op_state")
                if ev.get("op_id") == op and ev.get("state") == "observado"
            ]
            if not observed:
                problems.append("b2500: sin observado")
        elif name == "b4000":
            pairs = _pair_map(effects, op)
            if len(pairs) != 1:
                problems.append(f"b4000: effects en {len(pairs)} sesiones")
            else:
                group = next(iter(pairs.values()))
                if group["retirar"] != 1 or group["anotar"] != 0:
                    problems.append(
                        f"b4000: retirar={group['retirar']} anotar={group['anotar']}"
                    )
            states = [ev for ev in _events(ctx, "op_state") if ev.get("op_id") == op]
            if not any(
                ev.get("state") == "parcial" and ev.get("reason") == "lease_expired"
                for ev in states
            ):
                problems.append("b4000: sin parcial/lease_expired")
            if any(ev.get("state") == "fallido" for ev in states):
                problems.append("b4000: llego a fallido")
        else:
            problems.append(f"caso desconocido {name}")
        ok, latency, why = _recovery(ctx, case, anchors)
        entry["recovery_ms"] = latency
        if not ok:
            problems.append(f"{name}: {why}")
    if problems:
        return "FALLA", "; ".join(problems), metrics
    gap = _events(ctx, "gap_reset")
    if not gap:
        return "INCONCLUSO", "sin gap_reset", metrics
    if gap[-1].get("confirmed") is not True:
        return "FALLA", "gap_reset no confirmado", metrics
    config_lines = [
        ev
        for ev in _log(ctx, "server_script.log") or []
        if ev.get("kind") == "config_gap" and ev.get("qa_step_gap_ms") == 0
    ]
    if not config_lines:
        return "FALLA", "sin config qa_step_gap_ms=0 en el log del servidor", metrics
    return "PASA", "", metrics


def _g6(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    orders = _events(ctx, "pause_order")
    if not orders:
        return "INCONCLUSO", "sin pause_order", {}
    order = orders[-1]
    op = order.get("op_id")
    deadline = order.get("D_ms")
    start = order.get("T_s_ms")
    end = order.get("T_e_ms")
    if not (_num(deadline) and _num(start) and _num(end)):
        return "INCONCLUSO", "pause_order sin tiempos", {}
    metrics = _clock_metrics(ctx, start, end)
    results = [ev for ev in _events(ctx, "result_seen") if ev.get("op_id") == op]
    if not results:
        return "INCONCLUSO", "sin result_seen de la op", metrics
    if any(_num(ev.get("t_ms")) and ev["t_ms"] < start for ev in results):
        return "INCONCLUSO", "result_seen antes de T_s", metrics
    late = [
        ev
        for ev in results
        if ev.get("status") == "done" and _num(ev.get("t_ms")) and ev["t_ms"] > deadline + 150
    ]
    metrics["results"] = len(results)
    if late:
        metrics["late_done_ms"] = late[0]["t_ms"]
        return "FALLA", f"done en {late[0]['t_ms']} > D_ms+150", metrics
    expired = [
        ev
        for ev in results
        if ev.get("status") in ("rejected", "error") and ev.get("reason") == "expired"
    ]
    if not expired:
        return "INCONCLUSO", "done sin retraso ni expired", metrics
    ok, latency, why = _recovery(ctx, order, [])
    metrics["recovery_ms"] = latency
    if not ok:
        return "FALLA", why, metrics
    return "PASA", "", metrics


def _g7(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    proxy = _proxy(ctx)
    if proxy is None:
        return "INCONCLUSO", "sin samples/proxy.jsonl", {}
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G7", {}
    lease = _manifest_int(ctx, "lease_ms")
    effects = _effects(ctx)
    lines = _all_lines(ctx)
    problems = []
    metrics = {"cases": {}}
    measure_lines = [
        ev for ev in lines if ev.get("kind") in ("rest_error", "rest_invalid")
    ]
    for index, case in enumerate(cases):
        name = case.get("name")
        rule = case.get("rule_id")
        start = case.get("t_ms")
        if not _num(start):
            problems.append(f"{name}: sin t_ms")
            continue
        next_start = math.inf
        for later in cases[index + 1 :]:
            if _num(later.get("t_ms")) and later["t_ms"] > start:
                next_start = later["t_ms"]
                break
        window_end = next_start
        entry = {}
        metrics["cases"][str(name)] = entry
        if name == "r_held":
            polls = [
                ev
                for ev in proxy
                if ev.get("peer") == "server"
                and ev.get("deliver") == 0
                and ev.get("route") == "poll"
                and _num(ev.get("t_ms"))
                and start <= ev["t_ms"] <= window_end
            ]
            times = sorted(ev["t_ms"] for ev in polls)
            if len(times) < 2:
                return "INCONCLUSO", "r_held: menos de dos polls", metrics
            gaps = [b - a for a, b in zip(times, times[1:])]
            entry["polls"] = len(times)
            entry["max_gap_ms"] = max(gaps)
            if max(gaps) > 750:
                problems.append("r_held: hueco > 750 ms")
        elif name.startswith("invalid"):
            channel = None
            if name.endswith("_P"):
                channel = "P"
            elif name.endswith("_R"):
                channel = "R"
            invalid = [
                ev
                for ev in lines
                if ev.get("kind") == "rest_invalid"
                and (channel is None or ev.get("ch") == channel)
                and _num(ev.get("tick_ms"))
                and start <= ev["tick_ms"] <= window_end
            ]
            rewritten = [
                ev
                for ev in proxy
                if ev.get("rule_id") == rule
                and ev.get("route") == "poll"
                and ev.get("upstream_status") == 200
            ]
            if not rewritten:
                return "INCONCLUSO", f"{name}: sin respuestas reescritas", metrics
            entry["invalid"] = len(invalid)
            entry["rewritten"] = len(rewritten)
            if len(invalid) != len(rewritten):
                problems.append(
                    f"{name}: {len(invalid)} rest invalid != {len(rewritten)} reescritas"
                )
            window_effects = [
                ev
                for ev in effects
                if _num(ev.get("tick_ms")) and start <= ev["tick_ms"] <= window_end
            ]
            if window_effects:
                problems.append(f"{name}: effect en la ventana")
            if channel == "P":
                p_lines = [ev for ev in invalid if ev.get("ch") == "P"]
                if len(p_lines) == len(rewritten) and len(p_lines) >= 2:
                    span = max(ev["tick_ms"] for ev in p_lines) - min(
                        ev["tick_ms"] for ev in p_lines
                    )
                    entry["invalid_span_ms"] = span
                    if span > lease and not _any_lease_lost(ctx, start, window_end):
                        problems.append(f"{name}: sin lease lost pese a > lease_ms")
        elif name == "late_cb":
            late_lines = [
                ev
                for ev in lines
                if ev.get("kind") in ("rest_late", "rest_repeat")
                and _num(ev.get("tick_ms"))
                and start <= ev["tick_ms"] <= window_end
            ]
            if not late_lines:
                entry["late_cb"] = "inconcluso (sin rest late/repeat)"
            else:
                stop = min(window_end, _first_recovery_after(ctx, start))
                changes = [
                    ev
                    for ev in _events(ctx, "op_state")
                    if _num(ev.get("t_ms")) and start <= ev["t_ms"] < stop
                ]
                entry["changes"] = len(changes)
                if changes:
                    problems.append("late_cb: cambio de estado en la ventana")
        else:
            if name.startswith("status"):
                channel = name.rsplit("_", 1)[-1]
                line = _take_measure_line(measure_lines, channel)
                if line is None:
                    entry["state"] = None
                elif line.get("kind") == "rest_invalid":
                    entry["state"] = "invalid"
                else:
                    entry["state"] = line.get("state")
            elif name == "timeout_P":
                timeout = next(
                    (
                        ev
                        for ev in lines
                        if ev.get("kind") == "rest_timeout" and ev.get("ch") == "P"
                    ),
                    None,
                )
                entry["timeout_ms"] = (
                    timeout["tick_ms"] - start if timeout is not None else None
                )
        ok, latency, why = _recovery(ctx, case, [])
        entry["recovery_ms"] = latency
        if not ok:
            problems.append(f"{name}: {why}")
    if problems:
        return "FALLA", "; ".join(problems), metrics
    return "PASA", "", metrics


def _g8(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    effects = _effects(ctx)
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G8", {}
    results = _events(ctx, "result_seen")
    states = _events(ctx, "op_state")
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        op = case.get("op_id")
        entry = {}
        metrics["cases"][str(name)] = entry
        if op is None:
            problems.append(f"{name}: sin op_id")
            continue
        pairs = _pair_map(effects, op)
        entry["pairs"] = pairs
        if name in ("a", "b", "c"):
            ok, detail = _exact_pair(pairs)
            if not ok:
                problems.append(f"{name}: {detail}")
        else:
            problems.append(f"caso desconocido {name}")
        if name == "a":
            observed = [
                ev
                for ev in states
                if ev.get("op_id") == op and ev.get("state") == "observado"
            ]
            entry["observed"] = len(observed)
            if len(observed) > 1:
                problems.append("a: cambio extra por resultado repetido")
        elif name == "b":
            duplicates = [
                ev for ev in results if ev.get("op_id") == op and ev.get("dup") is True
            ]
            entry["dups"] = len(duplicates)
            if not duplicates:
                problems.append("b: sin result_seen dup true")
            else:
                op_results = [ev for ev in results if ev.get("op_id") == op]
                if len(op_results) > 1:
                    first = min(
                        ev["t_ms"] for ev in op_results if _num(ev.get("t_ms"))
                    )
                    if not _num(duplicates[0].get("t_ms")) or duplicates[0]["t_ms"] <= first:
                        problems.append("b: dup no posterior a la reentrega")
    if problems:
        return "FALLA", "; ".join(problems), metrics
    return "PASA", "", metrics


def _g9(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    ops = _events(ctx, "mix_op")
    if len(ops) != 100:
        return "FALLA", f"{len(ops)} mix_op (se esperan 100)", {"n_ops": len(ops)}
    gap = _events(ctx, "gap_reset") or _gap_reset_from_g5(ctx)
    if not gap:
        return "INCONCLUSO", "sin gap_reset", {}
    if gap[-1].get("confirmed") is not True:
        return "FALLA", "gap_reset no confirmado", {}
    effects = _effects(ctx)
    applies = {}
    for ev in _events(ctx, "apply"):
        if ev.get("op_id") is not None:
            applies.setdefault(ev["op_id"], ev)
    observed = {}
    for ev in _events(ctx, "op_state"):
        if ev.get("state") == "observado" and ev.get("op_id") is not None:
            observed.setdefault(ev["op_id"], ev)
    latencies = []
    missing_pairs = 0
    for ev in ops:
        op = ev.get("op_id")
        apply = applies.get(op)
        done = observed.get(op)
        if (
            apply is not None
            and done is not None
            and _num(apply.get("t_ms"))
            and _num(done.get("t_ms"))
        ):
            latencies.append(done["t_ms"] - apply["t_ms"])
        else:
            latencies.append(math.inf)
        if not _exact_pair(_pair_map(effects, op))[0]:
            missing_pairs += 1
    ordered = sorted(
        latencies, key=lambda value: (math.isinf(value), value if not math.isinf(value) else 0)
    )
    p50 = ordered[math.ceil(0.50 * 100) - 1]
    p95 = ordered[math.ceil(0.95 * 100) - 1]
    metrics = {
        "n_ops": 100,
        "ops_sin_pareja": missing_pairs,
        "p50_ms": _metric(p50),
        "p95_ms": _metric(p95),
        "max_ms": _metric(ordered[-1]),
    }
    if missing_pairs:
        return "FALLA", f"{missing_pairs} ops sin pareja de effect", metrics
    if math.isinf(p95) or p95 >= 1000:
        return "FALLA", "p95 >= 1000", metrics
    return "PASA", "", metrics


_ROWS = {
    "G1": _g1,
    "G2": _g2,
    "G3": _g3,
    "G4": _g4,
    "G5": _g5,
    "G6": _g6,
    "G7": _g7,
    "G8": _g8,
    "G9": _g9,
}


def parse_script_log(path):
    path = Path(path)
    if not path.is_file():
        raise EvidenceError(f"missing {path.name}")
    text = path.read_text(encoding="utf-8", errors="replace")
    events = []
    for raw in text.splitlines():
        line = raw.strip()
        marker = line.find("[DSBX] ")
        if marker >= 0:
            event = _parse_line(line[marker + 7 :].strip())
            if event is not None:
                events.append(event)
            continue
        if (_SCRIPT_ERROR.search(line) or "Can't compile" in line) and "DSBX_" in line:
            events.append({"kind": "script_error", "text": line})
    return events


def _parse_line(payload):
    fields = dict(re.findall(r"([A-Za-z_]+)=(\S+)", payload))
    if payload.startswith("effect "):
        step = fields.get("step")
        tick = _as_int(fields.get("tick_ms"))
        if step not in ("retirar", "anotar") or tick is None:
            return None
        return {
            "kind": "effect",
            "step": step,
            "session": fields.get("session"),
            "op": fields.get("op"),
            "tick_ms": tick,
        }
    if payload.startswith("rest error "):
        channel = fields.get("ch")
        kind = _as_int(fields.get("kind"))
        state = _as_int(fields.get("state"))
        tick = _as_int(fields.get("tick_ms"))
        if channel not in ("P", "R") or None in (kind, state, tick):
            return None
        return {
            "kind": "rest_error",
            "ch": channel,
            "kind_id": kind,
            "state": state,
            "tick_ms": tick,
        }
    if payload.startswith("rest timeout "):
        channel = fields.get("ch")
        kind = _as_int(fields.get("kind"))
        src = fields.get("src")
        tick = _as_int(fields.get("tick_ms"))
        if channel not in ("P", "R") or kind is None or src not in ("engine", "watchdog") or tick is None:
            return None
        return {
            "kind": "rest_timeout",
            "ch": channel,
            "kind_id": kind,
            "src": src,
            "tick_ms": tick,
        }
    if payload.startswith("rest invalid "):
        channel = fields.get("ch")
        kind = _as_int(fields.get("kind"))
        tick = _as_int(fields.get("tick_ms"))
        if channel not in ("P", "R") or kind is None or tick is None:
            return None
        return {"kind": "rest_invalid", "ch": channel, "kind_id": kind, "tick_ms": tick}
    if payload.startswith("rest late "):
        channel = fields.get("ch")
        kind = _as_int(fields.get("kind"))
        tick = _as_int(fields.get("tick_ms"))
        if channel not in ("P", "R") or kind is None or tick is None:
            return None
        return {"kind": "rest_late", "ch": channel, "kind_id": kind, "tick_ms": tick}
    if payload.startswith("rest repeat "):
        channel = fields.get("ch")
        kind = _as_int(fields.get("kind"))
        via = fields.get("via")
        tick = _as_int(fields.get("tick_ms"))
        if channel not in ("P", "R") or kind is None or via not in ("success", "error", "timeout") or tick is None:
            return None
        return {
            "kind": "rest_repeat",
            "ch": channel,
            "kind_id": kind,
            "via": via,
            "tick_ms": tick,
        }
    if payload.startswith("lease lost "):
        age = _as_int(fields.get("age_ms"))
        tick = _as_int(fields.get("tick_ms"))
        if age is None or tick is None:
            return None
        return {"kind": "lease_lost", "age_ms": age, "tick_ms": tick}
    if payload.startswith("clock "):
        tick = _as_int(fields.get("tick_ms"))
        if tick is None:
            return None
        return {"kind": "clock", "tick_ms": tick}
    if payload.startswith("config "):
        gap = _as_int(fields.get("qa_step_gap_ms"))
        if gap is None:
            return None
        return {"kind": "config_gap", "qa_step_gap_ms": gap}
    if payload.startswith("hello accepted "):
        conn = _as_int(fields.get("conn"))
        if conn is None:
            return None
        return {"kind": "hello_accepted", "session": fields.get("session"), "conn": conn}
    return None


def _clock_metrics(ctx, start, end):
    clocks = []
    for name in SCRIPT_LOGS:
        for ev in _log(ctx, name) or []:
            if ev.get("kind") == "clock" and _num(ev.get("tick_ms")):
                clocks.append(ev["tick_ms"])
    clocks.sort()
    metrics = {"clock_n": len(clocks)}
    if len(clocks) >= 2:
        deltas = [b - a for a, b in zip(clocks, clocks[1:])]
        metrics["clock_max_step_ms"] = max(deltas)
        straddle = [
            delta
            for a, b, delta in zip(clocks, clocks[1:], deltas)
            if a <= end and b >= start
        ]
        metrics["clock_pause_step_ms"] = max(straddle) if straddle else None
        count = len(clocks)
        mean_index = (count - 1) / 2.0
        mean_tick = sum(clocks) / count
        numerator = sum((i - mean_index) * (tick - mean_tick) for i, tick in enumerate(clocks))
        denominator = sum((i - mean_index) ** 2 for i in range(count))
        metrics["clock_slope_ms_per_line"] = numerator / denominator if denominator else None
    return metrics


def _window_for(case, windows):
    moment = case.get("t_ms")
    best = None
    best_key = None
    for window in windows:
        start = window.get("t_start_ms")
        if not _num(start) or not _num(moment):
            continue
        key = (start < moment, abs(start - moment))
        if best_key is None or key < best_key:
            best_key = key
            best = window
    return best


def _take_measure_line(lines, channel):
    for index, ev in enumerate(lines):
        if ev.get("ch") == channel:
            return lines.pop(index)
    return None


def _first_recovery_after(ctx, moment):
    times = [
        ev["t_ms"]
        for ev in _events(ctx, "recovery")
        if _num(ev.get("t_ms")) and ev["t_ms"] > moment
    ]
    return min(times) if times else math.inf


def _any_lease_lost(ctx, start, end):
    for name in SCRIPT_LOGS:
        for ev in _log(ctx, name) or []:
            if (
                ev.get("kind") == "lease_lost"
                and _num(ev.get("tick_ms"))
                and start <= ev["tick_ms"] <= end
            ):
                return True
    return False


def _gap_reset_from_g5(ctx):
    path = ctx["dir"] / "samples" / "G5.jsonl"
    if not path.is_file():
        return []
    try:
        events = _read_events(path)
    except EvidenceError:
        return []
    return [ev for ev in events if ev.get("ev") == "gap_reset"]


def _inventory_paths(ctx):
    path = ctx["dir"] / "logs" / "inventory.json"
    if not path.is_file():
        return None
    try:
        data = _read_json(path)
    except EvidenceError:
        return None
    paths = []
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                paths.extend(item for item in value if isinstance(item, str))
            elif isinstance(value, str):
                paths.append(value)
    elif isinstance(data, list):
        paths.extend(item for item in data if isinstance(item, str))
    else:
        return None
    return paths


def _uncovered(inventory, files):
    scanned = [item for item in files if isinstance(item, str)]
    normalized = {item.replace("\\", "/") for item in scanned}
    basenames = {Path(item.replace("\\", "/")).name for item in scanned}
    missing = []
    for item in inventory:
        candidate = item.replace("\\", "/")
        if candidate in normalized:
            continue
        if Path(candidate).name in basenames:
            continue
        missing.append(item)
    return missing


def _manifest_int(ctx, key):
    value = ctx["manifest"].get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise EvidenceError(f"manifest sin {key}")
    return value


def _as_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _num(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _metric(value):
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"{path.name} no es objeto")
    return data


def _read_events(path):
    events = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"{path.name}:{lineno}: {exc}") from exc
        if not isinstance(obj, dict) or "ev" not in obj or not _num(obj.get("t_ms")):
            raise EvidenceError(f"{path.name}:{lineno}: falta ev o t_ms")
        if events and obj["t_ms"] < events[-1]["t_ms"]:
            raise EvidenceError(f"{path.name}:{lineno}: t_ms retrocede")
        events.append(obj)
    return events


def _read_proxy(path):
    events = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvidenceError(f"{path.name}:{lineno}: {exc}") from exc
        if not isinstance(obj, dict) or not _num(obj.get("t_ms")):
            raise EvidenceError(f"{path.name}:{lineno}: falta t_ms")
        events.append(obj)
    return events


def _write_verdict(directory, verdict):
    text = json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (Path(directory) / "verdict.json").write_bytes(text.encode("utf-8"))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: f1bp_eval.py <evidence_dir>", file=sys.stderr)
        return 2
    directory = Path(argv[0])
    verdict = evaluate(directory)
    _write_verdict(directory, verdict)
    for gid in sorted(verdict["rows"]):
        row = verdict["rows"][gid]
        print(f"{gid} {row['verdict']} {row['reason']}".rstrip())
    print(f"AGGREGATE {verdict['aggregate']}")
    return EXIT[verdict["aggregate"]]


if __name__ == "__main__":
    sys.exit(main())
