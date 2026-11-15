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
# Informe de cierre del motor. El motor retiene todo RestCallback que recibe: medido en partida
# el 15-nov, N = created_n del peer (5 = 2 + 3 fallos inyectados). Brief v1.3, sec. 10.
_EXIT_LEAK = re.compile(r"Leaked '(DSBX_\w+)' script instance \((-?\d+)x\)!")
TOLERATED_EXIT_LEAK = "DSBX_Callback"
# Reloj de las lineas del log (brief v1.4, sec. 10, H-04). tick_ms es el reloj del motor
# (GetTickTime), no el del arnes. Cada linea lleva su hora de pared ("12:49:39.023 ..."), escrita
# al hacer Print, y el arnes anota una pareja (t_ms, hora de pared) en el `start` de cada
# escenario y en el manifest (t0_ms, t0_wall). Con eso, una linea se situa en el reloj del arnes.
DAY_MS = 86400000
WINDOW_TOL_MS = 250
_WALL = re.compile(r"\s*(\d{1,2}):(\d{2}):(\d{2})\.(\d{3})")
PEER_LOG = {"server": "server_script.log", "client": "client_script.log"}
EXIT = {"PASA": 0, "FALLA": 1, "INCONCLUSO": 2}
RECOVERY_LIMIT_MS = 60000.0
KEY_LEAK_REASON = "clave en los logs"
KEY_INCOMPLETE_REASON = "escaneo incompleto"


class EvidenceError(Exception):
    pass


def evaluate(evidence_dir):
    directory = Path(evidence_dir)
    leak = _key_leak(directory)  # R4: una clave en cualquier escenario tumba el agregado
    incomplete = _key_unreadable(directory)  # R26: un escaneo con ficheros ilegibles no basta
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        rows = {gid: _row("INCONCLUSO", "manifest.json ausente", {}) for gid in ROW_IDS}
        return _aggregate(rows, leak, incomplete)
    try:
        manifest = _read_json(manifest_path)
    except EvidenceError as exc:
        rows = {gid: _row("INCONCLUSO", str(exc), {}) for gid in ROW_IDS}
        return _aggregate(rows, leak, incomplete)
    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list):
        scenarios = []
    dirty = manifest.get("git_dirty") is True
    # R2: sin fake, los logs son finales solo si logs_ready.json dice que todo se cerro.
    final = manifest.get("fake") is True or _logs_final(directory)
    rows = {}
    for gid in scenarios:
        if gid not in ROW_IDS:
            continue
        rows[gid] = _eval_row(directory, manifest, gid, dirty, final)
    return _aggregate(rows, leak, incomplete)


def _logs_final(directory):
    path = directory / "logs_ready.json"
    if not path.is_file():
        return False
    try:
        return _read_json(path).get("all_closed") is True
    except EvidenceError:
        return False


def _key_leak(directory):
    """True si algun `key_scan` de samples/G*.jsonl trae hits > 0 (R4), sean cuales sean las filas."""
    samples = directory / "samples"
    if not samples.is_dir():
        return False
    for path in sorted(samples.glob("G*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if (
                isinstance(obj, dict)
                and obj.get("ev") == "key_scan"
                and _num(obj.get("hits"))
                and obj["hits"] > 0
            ):
                return True
    return False


def _key_unreadable(directory):
    """True si algun `key_scan` de samples/G*.jsonl trae `unreadable` no vacio (R26)."""
    samples = directory / "samples"
    if not samples.is_dir():
        return False
    for path in sorted(samples.glob("G*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("ev") == "key_scan" and obj.get("unreadable"):
                return True
    return False


def _aggregate(rows, leak=False, incomplete=False):
    verdicts = [row["verdict"] for row in rows.values()]
    if leak:
        return {"aggregate": "FALLA", "reason": KEY_LEAK_REASON, "rows": rows}
    if "FALLA" in verdicts:
        aggregate = "FALLA"
    elif incomplete:
        # R26: sin FALLA previa, un escaneo incompleto deja el agregado en INCONCLUSO.
        return {"aggregate": "INCONCLUSO", "reason": KEY_INCOMPLETE_REASON, "rows": rows}
    elif "INCONCLUSO" in verdicts:
        aggregate = "INCONCLUSO"
    else:
        aggregate = "PASA"
    return {"aggregate": aggregate, "rows": rows}


def _row(verdict, reason, metrics):
    return {"verdict": verdict, "reason": reason, "metrics": metrics}


def _eval_row(directory, manifest, gid, dirty, final=True):
    if dirty:
        return _row("INCONCLUSO", "git_dirty: true", {})
    if not final:
        return _row("INCONCLUSO", "logs no finales", {})
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


def _wall_ms(text):
    """ms desde la medianoche local de una hora "HH:MM:SS.mmm" al principio del texto, o None."""
    if not isinstance(text, str):
        return None
    match = _WALL.match(text)
    if not match:
        return None
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def _anchor(ctx):
    """(t_ms, wall_ms) del escenario (su `start`) o, si no, del manifest (t0_ms, t0_wall)."""
    for ev in ctx["scenario"]:
        if ev.get("ev") == "start" and _num(ev.get("t_ms")):
            wall = _wall_ms(ev.get("wall"))
            if wall is not None:
                return ev["t_ms"], wall
    manifest = ctx["manifest"]
    wall = _wall_ms(manifest.get("t0_wall"))
    if wall is not None and _num(manifest.get("t0_ms")):
        return manifest["t0_ms"], wall
    return None


def _clock_ok(ctx):
    return ctx["manifest"].get("fake") is True or _anchor(ctx) is not None


def _line_t(ctx, ev):
    """Instante de una linea del log en el reloj del arnes (ms), o None.

    En el ensayo en seco (fake) el arnes escribe tick_ms con su propio reloj.
    """
    if ctx["manifest"].get("fake") is True:
        tick = ev.get("tick_ms")
        return tick if _num(tick) else None
    wall = ev.get("wall_ms")
    anchor = _anchor(ctx)
    if wall is None or anchor is None:
        return None
    t_anchor, wall_anchor = anchor
    diff = wall - wall_anchor
    if diff < -DAY_MS // 2:
        diff += DAY_MS
    elif diff > DAY_MS // 2:
        diff -= DAY_MS
    return t_anchor + diff


def _in_window(ctx, ev, start, end, tol_lo=WINDOW_TOL_MS, tol_hi=WINDOW_TOL_MS):
    t = _line_t(ctx, ev)
    return t is not None and start - tol_lo <= t <= end + tol_hi


def _effects(ctx):
    """Cada linea `effect` cuenta una vez, por fichero y numero de linea (R8): sin deduplicar por tick."""
    effects = []
    for name in SCRIPT_LOGS:
        for ev in _log(ctx, name) or []:
            if ev.get("kind") == "effect":
                effects.append(ev)
    return effects


def _all_lines(ctx):
    """Lineas de los dos script logs ordenadas por su instante en el reloj del arnes.

    Cada peer tiene su propio tick_ms (otro proceso, otro origen): no se mezclan por tick.
    """
    lines = []
    for name in SCRIPT_LOGS:
        lines.extend(_log(ctx, name) or [])

    def key(ev):
        t = _line_t(ctx, ev)
        return t if t is not None else -math.inf

    lines.sort(key=key)
    return lines


def _script_errors(ctx, tolerated=None):
    """Errores de script DSBX_ de los logs y los RPT.

    El informe de cierre `Leaked 'DSBX_Callback' script instance (Nx)!` solo se tolera con
    0 < N <= cota. En el script log, la cota es la suma de `created_n` de las lineas `shutdown`
    anteriores. En el RPT es la de todo el script log del mismo peer, porque el RPT del cliente
    no lleva las lineas [DSBX]. Sin `shutdown`, con N fuera de la cota o con otra clase, es un error.
    """
    errors = []
    for name in SCRIPT_LOGS + RPT_LOGS:
        rpt_bound = None
        if name in RPT_LOGS:
            peer_log = PEER_LOG["server" if name.startswith("server") else "client"]
            rpt_bound = sum(max(0, ev.get("created_n", 0)) for ev in (_log(ctx, peer_log) or [])
                            if ev.get("kind") == "shutdown")
        created = 0  # sin linea shutdown previa la cota es 0 y nada se tolera
        for ev in _log(ctx, name) or []:
            kind = ev.get("kind")
            if kind == "shutdown":
                created += max(0, ev.get("created_n", 0))
            elif kind == "exit_leak":
                n = ev.get("n", 0)
                bound = created if rpt_bound is None else rpt_bound
                if ev.get("cls") == TOLERATED_EXIT_LEAK and 0 < n <= bound:
                    if tolerated is not None:
                        tolerated.append({"file": name, "n": n, "bound": bound})
                else:
                    errors.append(ev)
            elif kind == "script_error":
                errors.append(ev)
    return errors


def _pair(effects, session, op):
    """Efectos de la op `op` de la sesion `session` por paso (R5: nunca solo por op)."""
    counts = {"retirar": 0, "anotar": 0}
    for ev in effects:
        if ev.get("session") == session and ev.get("op") == op and ev.get("step") in counts:
            counts[ev["step"]] += 1
    return counts


def _exact_pair(pair):
    if pair["retirar"] != 1 or pair["anotar"] != 1:
        return False, f"retirar={pair['retirar']} anotar={pair['anotar']}"
    return True, ""


def _op_effects(effects, sessions, op):
    return [ev for ev in effects if ev.get("op") == op and ev.get("session") in sessions]


def _case_key(case):
    """(session, op) de un caso con op_id (R5), o None si no lleva op_id."""
    op = case.get("op_id")
    if op is None:
        return None
    session = case.get("session")
    if session is None:
        raise EvidenceError(f"evidencia invalida: case {case.get('name')} sin session")
    return session, op


def _states(ctx, session, op):
    return [
        ev
        for ev in _events(ctx, "op_state")
        if ev.get("op_id") == op and ev.get("session") == session
    ]


def _coverage(found, required):
    """Texto de lo que falta o sobra (R7): cada obligatorio una sola vez. "" si esta completo."""

    def label(key):
        return "/".join(str(part) for part in key) if isinstance(key, tuple) else str(key)

    absent = [label(key) for key in required if found.count(key) == 0]
    repeated = [label(key) for key in required if found.count(key) > 1]
    parts = []
    if absent:
        parts.append("falta " + ", ".join(absent))
    if repeated:
        parts.append("repetido " + ", ".join(repeated))
    return "; ".join(parts)


def _case_rule_ids(case):
    ids = []
    rule = case.get("rule_id")
    if isinstance(rule, str) and rule:
        ids.append(rule)
    many = case.get("rule_ids")
    if isinstance(many, list):
        ids.extend(item for item in many if isinstance(item, str) and item)
    return ids


def _fire_line(ctx, case, rule_id, proxy):
    """Primera linea del proxy que acredita la inyeccion `rule_id` de un caso (R9), o None.

    La version confirmada del caso es la de la ultima `rules` con ese rule_id no posterior al caso
    (o la primera posterior) que tiene su `rules_active`. Cuenta una linea con ese rule_id y
    rules_version igual o mayor (el proxy etiqueta cada linea con la version activa al recibirla),
    servida despues de escribirse esa version (`t_done_ms`, o `t_ms` si no lo hay). No se compara con
    el t_ms del `rules_active`: el orquestador lo anota al detectar el fichero, con su retraso de
    sondeo, y un long-poll recibido antes del caso actua al servir la respuesta (brief v1.5, H-09).
    """
    actives = _events(ctx, "rules_active")
    candidates = []
    for ev in _events(ctx, "rules"):
        ids = ev.get("rule_ids")
        if not isinstance(ids, list) or rule_id not in ids:
            continue
        active = next(
            (
                other
                for other in actives
                if other.get("version") == ev.get("version")
                and _num(other.get("t_ms"))
                and other["t_ms"] >= ev["t_ms"]
            ),
            None,
        )
        if active is not None and _num(ev.get("version")):
            candidates.append((ev["t_ms"], ev["version"], active["t_ms"]))
    if not candidates:
        return None
    moment = case.get("t_ms")
    before = [item for item in candidates if _num(moment) and item[0] <= moment]
    t_written, version, _ = max(before) if before else min(candidates)

    def served(ev):
        return ev["t_done_ms"] if _num(ev.get("t_done_ms")) else ev.get("t_ms")

    def acted_version(ev):
        # R18: `rule_version` es la version vigente cuando la regla actuo; sin ella, `rules_version`.
        return ev["rule_version"] if _num(ev.get("rule_version")) else ev.get("rules_version")

    lines = [
        ev
        for ev in proxy
        if ev.get("rule_id") == rule_id
        and _num(acted_version(ev))
        and acted_version(ev) >= version
        and _num(served(ev))
        and served(ev) >= t_written
    ]
    return min(lines, key=lambda ev: ev["t_ms"]) if lines else None


def _injection(ctx, cases):
    """R9: cada caso con inyeccion trae rule_id y el proxy lo vio disparar.

    Devuelve (motivo, disparos): motivo "" si todo se observo; disparos mapea id(caso) a su
    primera linea del proxy.
    """
    fires = {}
    proxy = _proxy(ctx)
    if proxy is None:
        return "sin samples/proxy.jsonl", fires
    for case in cases:
        label = str(case.get("name", case.get("ev")))
        ids = _case_rule_ids(case)
        if not ids:
            return f"inyección no observada: {label} sin rule_id", fires
        first = None
        for rule_id in ids:
            line = _fire_line(ctx, case, rule_id, proxy)
            if line is None:
                return f"inyección no observada: {label} ({rule_id})", fires
            if first is None or line["t_ms"] < first["t_ms"]:
                first = line
        fires[id(case)] = first
    return "", fires


def _prohibition_end(ctx, fire_t):
    """R10: fin de la ventana de prohibicion = rules_active del primer `rules` vacio tras el disparo.

    Si antes de ese `rules` vacio se escribe otro con reglas, la inyeccion del caso no se cerro
    (el vacio es de un caso posterior): no hay fin y devuelve None.
    """
    actives = _events(ctx, "rules_active")
    best = None
    for ev in _events(ctx, "rules"):
        if ev.get("rule_ids") != []:
            continue
        for other in actives:
            if (
                other.get("version") == ev.get("version")
                and _num(other.get("t_ms"))
                and other["t_ms"] >= ev["t_ms"]
                and other["t_ms"] >= fire_t
            ):
                if best is None or other["t_ms"] < best[0]:
                    best = (other["t_ms"], ev["t_ms"])
                break
    if best is None:
        return None
    for ev in _events(ctx, "rules"):
        if ev.get("rule_ids") and fire_t < ev["t_ms"] < best[1]:
            return None
    return best[0]


def _recovery_ops(ctx):
    """{(session, op)} de las ordenes de recuperacion: sus efectos quedan fuera de las ventanas."""
    ops = set()
    for rec in _events(ctx, "recovery"):
        op = rec.get("op_id")
        session = rec.get("session")
        if session is None:
            for ev in _events(ctx, "op_state"):
                if (
                    ev.get("op_id") == op
                    and ev.get("session") is not None
                    and _num(ev.get("t_ms"))
                    and ev["t_ms"] >= rec["t_ms"]
                ):
                    session = ev["session"]
                    break
        ops.add((session, op))
    return ops


def _window_effects(ctx, effects, start, end, tol_hi=WINDOW_TOL_MS):
    """Efectos en la ventana, sin los de las ordenes de recuperacion (que quedan fuera, R10)."""
    recovery = _recovery_ops(ctx)
    return [
        ev
        for ev in effects
        if _in_window(ctx, ev, start, end, tol_hi=tol_hi)
        and (ev.get("session"), ev.get("op")) not in recovery
    ]


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
    # R20: vale si ALGUNA recovery del tramo llega a observado (casada por sesion) dentro de 60 s
    # desde el ancla; una fallida (conexion_perdida) seguida de otra que llega es valida.
    latencies = []
    for rec in candidates:
        op = rec.get("op_id")
        session = rec.get("session")
        for ev in _events(ctx, "op_state"):
            if (
                ev.get("op_id") == op
                and (session is None or ev.get("session") == session)
                and ev.get("state") == "observado"
                and _num(ev.get("t_ms"))
                and ev["t_ms"] >= rec["t_ms"]
            ):
                latencies.append(ev["t_ms"] - t0)
                break
    if not latencies:
        return False, None, "recovery sin observado"
    within = [value for value in latencies if value <= RECOVERY_LIMIT_MS]
    if not within:
        return False, min(latencies), "recuperacion > 60 s"
    return True, min(within), ""


def _g1(ctx):
    manifest = ctx["manifest"]
    if manifest.get("fake") is True:
        return "INCONCLUSO", "fake: G1 no se evalua", {"fake": True}
    missing = _missing_logs(ctx, SCRIPT_LOGS + RPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    tolerated = []
    errors = _script_errors(ctx, tolerated)
    connected = sorted(
        {ev.get("peer") for ev in _events(ctx, "connected") if ev.get("peer") in PEER_LOG}
    )
    metrics = {"connected": connected, "script_errors": len(errors), "exit_leak_cb": tolerated}
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
    why = _coverage([case.get("name") for case in cases], ["a", "b", "c"])
    if why:
        return "INCONCLUSO", "cobertura incompleta: " + why, {}
    why, _ = _injection(ctx, [case for case in cases if case.get("name") == "c"])
    if why:
        return "INCONCLUSO", why, {}
    anchors = [case.get("t_ms") for case in cases if _num(case.get("t_ms"))]
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        entry = {"pair": None}
        metrics["cases"][str(name)] = entry
        key = _case_key(case)
        if key is None:
            problems.append(f"{name}: sin op_id")
            continue
        session, op = key
        pair = _pair(effects, session, op)
        entry["pair"] = pair
        states = _states(ctx, session, op)
        if name in ("a", "b"):
            ok, detail = _exact_pair(pair)
            if not ok:
                problems.append(f"{name}: {detail}")
            if not any(ev.get("state") == "observado" for ev in states):
                problems.append(f"{name}: sin observado")
        elif name == "c":
            if any(ev.get("state") == "observado" for ev in states):
                problems.append("c: llego a observado")
            if not any(
                ev.get("state") == "fallido" and ev.get("reason") == "lectura_no_cumple"
                for ev in states
            ):
                problems.append("c: sin fallido/lectura_no_cumple")
            # D-P2: el peer anota lo que recibe (la revision reescrita) y es el backend quien lo
            # rechaza; sus efectos son esperables y solo se anotan (pair).
        else:
            problems.append(f"caso desconocido {name}")
        if name == "c":
            # Recuperacion tras la inyeccion (P-08); a y b no inyectan nada.
            ok, latency, why = _recovery(ctx, case, anchors)
            entry["recovery_ms"] = latency
            if not ok:
                problems.append(f"{name}: {why}")
    if problems:
        return "FALLA", "; ".join(problems), metrics
    return "PASA", "", metrics


def _norm_path(path):
    return path.replace("\\", "/").lower()


def _inventory(ctx):
    """(rutas del perfil, destinos de copia) del inventario R3, o None si no es legible."""
    path = ctx["dir"] / "logs" / "inventory.json"
    if not path.is_file():
        return None
    try:
        data = _read_json(path)
    except EvidenceError:
        return None
    profile = []
    for peer in ("server", "client"):
        section = data.get(peer)
        if (
            not isinstance(section, dict)
            or not isinstance(section.get("dir"), str)
            or not isinstance(section.get("files"), list)
        ):
            return None
        base = section["dir"].replace("\\", "/").rstrip("/")
        for name in section["files"]:
            if not isinstance(name, str):
                return None
            profile.append(base + "/" + name)
    copies = []
    raw = data.get("copies", [])
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("dest"), str):
            return None
        copies.append(item["dest"])
    return profile, copies


def _uncovered(inventory, files):
    """Elementos del inventario que `key_scan.files` no cubre (R3/R4, sin distinguir mayusculas).

    Un fichero del perfil se cubre con su ruta completa. Una copia de logs/ se cubre con una ruta que
    acabe en logs/<dest>: la carpeta de evidencia puede haberse movido despues del escaneo.
    """
    profile, copies = inventory
    scanned = {_norm_path(item) for item in files if isinstance(item, str)}
    missing = [item for item in profile if _norm_path(item) not in scanned]
    for dest in copies:
        suffix = "/logs/" + _norm_path(dest)
        if not any(item.endswith(suffix) for item in scanned):
            missing.append("logs/" + dest)
    return missing


def _g4(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS + ("inventory.json",))
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G4", {}
    if not _clock_ok(ctx):
        return "INCONCLUSO", "sin ancla de hora de pared (manifest.t0_wall o start.wall)", {}
    why = _coverage([case.get("name") for case in cases], ["a", "b", "c"])
    if why:
        return "INCONCLUSO", "cobertura incompleta: " + why, {}
    why, _ = _injection(ctx, cases)
    if why:
        return "INCONCLUSO", why, {}
    proxy = _proxy(ctx) or []
    effects = _effects(ctx)
    bad = _events(ctx, "bad_key_window")
    stale = _events(ctx, "stale_order")
    anchors = [case.get("t_ms") for case in cases if _num(case.get("t_ms"))]
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        metrics["cases"][str(name)] = {}
        key = _case_key(case)
        if key is None:
            problems.append(f"{name}: sin op_id")
            continue
        session, op = key
        if name == "a":
            if not bad:
                return "INCONCLUSO", "sin bad_key_window", metrics
            window = bad[0]
            start = window.get("t_start_ms")
            end = window.get("t_end_ms")
            if not (_num(start) and _num(end)):
                return "INCONCLUSO", "bad_key_window sin ventana", metrics
            in_window = [
                ev
                for ev in proxy
                if ev.get("route") == "hello"
                and ev.get("peer") == "server"
                and _num(ev.get("t_ms"))
                and start <= ev["t_ms"] <= end
            ]
            hellos = [ev for ev in in_window if ev.get("upstream_status") == 401]
            if not hellos:
                problems.append("a: sin hello 401 del servidor en la ventana")
            if any(ev.get("upstream_status") == 200 for ev in in_window):
                problems.append("a: hello 200 del servidor con clave mala")
            window_effects = _window_effects(ctx, effects, start, end)
            if window_effects:
                problems.append("a: effect en la ventana")
            if _op_effects(effects, (session,), op):
                problems.append("a: effect para la op")
            metrics["cases"]["a"] = {
                "hellos_401": len(hellos),
                "effects_in_window": len(window_effects),
            }
        elif name == "b":
            if not stale:
                return "INCONCLUSO", "sin stale_order", metrics
            sessions = {session}
            for ev in stale:
                if ev.get("op_id") == op and ev.get("old_session") is not None:
                    sessions.add(ev["old_session"])
            if _op_effects(effects, sessions, op):
                problems.append("b: effect para la op stale")
            results = [ev for ev in _events(ctx, "result_seen") if ev.get("op_id") == op]
            if results:
                last = results[-1]
                if not (last.get("status") == "rejected" and last.get("reason") == "stale_session"):
                    problems.append("b: resultado no rejected/stale_session")
            metrics["cases"]["b"] = {"results": len(results)}
        elif name == "c":
            states = _states(ctx, session, op)
            if not any(
                ev.get("state") == "fallido" and ev.get("reason") == "conexion_perdida"
                for ev in states
            ):
                problems.append("c: sin fallido/conexion_perdida")
            if _op_effects(effects, (session,), op):
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
    inventory = _inventory(ctx)
    if inventory is None:
        return "INCONCLUSO", "inventory.json ilegible", metrics
    if not inventory[0] and not inventory[1]:
        return "INCONCLUSO", "inventario vacio", metrics
    files = scan.get("files")
    if not isinstance(files, list):
        return "INCONCLUSO", "key_scan.files no es lista", metrics
    uncovered = _uncovered(inventory, files)
    metrics["inventory_paths"] = len(inventory[0]) + len(inventory[1])
    metrics["key_scan_files"] = len(files)
    if uncovered:
        problems.append("key_scan.files no cubre: " + ", ".join(uncovered[:3]))
    if problems:
        return "FALLA", "; ".join(problems), metrics
    return "PASA", "", metrics


P_ROUTES = ("hello", "poll")  # R11: solo las rutas de P renuevan el lease


def _assign_windows(cases, windows):
    """Una ventana distinta para cada caso: la mas cercana sin usar (prefiere las que empiezan despues)."""
    used = set()
    assigned = {}
    for case in cases:
        moment = case.get("t_ms")
        best = None
        for index, window in enumerate(windows):
            start = window.get("t_start_ms")
            if index in used or not _num(start) or not _num(moment):
                continue
            key = (start < moment, abs(start - moment))
            if best is None or key < best[0]:
                best = (key, index)
        if best is not None:
            used.add(best[1])
            assigned[id(case)] = windows[best[1]]
    return assigned


def _g5(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    if not _clock_ok(ctx):
        return "INCONCLUSO", "sin ancla de hora de pared (manifest.t0_wall o start.wall)", {}
    lease = _manifest_int(ctx, "lease_ms")
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G5", {}
    gap = _events(ctx, "gap_reset")
    found = []
    for case in cases:
        name = case.get("name")
        found.append((name, case.get("peer")) if name in ("a2500", "a4500") else (name,))
    found.extend([("gap_reset",)] * len(gap))
    required = [
        ("a2500", "server"),
        ("a2500", "client"),
        ("a4500", "server"),
        ("a4500", "client"),
        ("b2500",),
        ("b4000",),
        ("gap_reset",),
    ]
    why = _coverage(found, required)
    if why:
        return "INCONCLUSO", "cobertura incompleta: " + why, {}
    why, _ = _injection(ctx, cases)
    if why:
        return "INCONCLUSO", why, {}
    proxy = _proxy(ctx) or []
    windows = _assign_windows(
        [case for case in cases if case.get("name") in ("a2500", "a4500")],
        _events(ctx, "window"),
    )
    anchors = [case.get("t_ms") for case in cases if _num(case.get("t_ms"))]
    effects = _effects(ctx)
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        peer = case.get("peer")
        entry = {}
        label = f"{name}/{peer}" if name in ("a2500", "a4500") else str(name)
        metrics["cases"][label] = entry
        key = _case_key(case)
        if key is None:
            problems.append(f"{label}: sin op_id")
            continue
        session, op = key
        if name in ("a2500", "a4500"):
            window = windows.get(id(case))
            if window is None or not (_num(window.get("t_start_ms")) and _num(window.get("t_end_ms"))):
                return "INCONCLUSO", f"sin window para {label}", metrics
            start = window["t_start_ms"]
            end = window["t_end_ms"]
            log_name = PEER_LOG.get(peer)
            if log_name is None:
                return "INCONCLUSO", f"{name} sin peer valido", metrics
            if name == "a2500":
                # R11: solo cuentan las respuestas 200 de las rutas de P a ese peer.
                responses = [
                    ev
                    for ev in proxy
                    if ev.get("peer") == peer
                    and ev.get("route") in P_ROUTES
                    and ev.get("upstream_status") == 200
                    and _num(ev.get("t_done_ms"))
                ]
                inside = [ev for ev in responses if start <= ev["t_done_ms"] <= end]
                after = [ev for ev in responses if ev["t_done_ms"] > end]
                if after:
                    inside.append(min(after, key=lambda ev: ev["t_done_ms"]))
                times = sorted(ev["t_done_ms"] for ev in inside)
                if len(times) < 2:
                    return "INCONCLUSO", "sin dos respuestas 200 de P en la ventana", metrics
                gaps = [b - a for a, b in zip(times, times[1:])]
                entry["responses"] = len(times)
                entry["max_gap_ms"] = max(gaps)
                if max(gaps) >= lease:
                    problems.append(f"{label}: hueco {max(gaps)} >= lease_ms")
                lost = [
                    ev
                    for ev in _log(ctx, log_name) or []
                    if ev.get("kind") == "lease_lost" and _in_window(ctx, ev, start, end)
                ]
                if lost:
                    problems.append(f"{label}: lease lost en la ventana")
            else:
                lost = [
                    ev
                    for ev in _log(ctx, log_name) or []
                    if ev.get("kind") == "lease_lost"
                    and _num(ev.get("age_ms"))
                    and lease <= ev["age_ms"] < lease + 200
                    and _in_window(ctx, ev, start, end)
                ]
                entry["lease_lost"] = len(lost)
                if not lost:
                    problems.append(f"{label}: sin lease lost en [lease, lease+200)")
        elif name == "b2500":
            ok, detail = _exact_pair(_pair(effects, session, op))
            if not ok:
                problems.append(f"b2500: {detail}")
            if not any(ev.get("state") == "observado" for ev in _states(ctx, session, op)):
                problems.append("b2500: sin observado")
        elif name == "b4000":
            pair = _pair(effects, session, op)
            if pair["retirar"] != 1 or pair["anotar"] != 0:
                problems.append(f"b4000: retirar={pair['retirar']} anotar={pair['anotar']}")
            states = _states(ctx, session, op)
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
            problems.append(f"{label}: {why}")
    if problems:
        return "FALLA", "; ".join(problems), metrics
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
    runs = _events(ctx, "clock_run")
    why = _coverage(
        ["pause_order"] * len(orders) + ["clock_run"] * len(runs), ["pause_order", "clock_run"]
    )
    if why:
        return "INCONCLUSO", "cobertura incompleta: " + why, {}
    order = orders[0]
    why, _ = _injection(ctx, [order])
    if why:
        return "INCONCLUSO", why, {}
    op = order.get("op_id")
    t_d = order.get("T_d_ms")
    start = order.get("T_s_ms")
    end = order.get("T_e_ms")
    deadline = order.get("D_ms")
    if not (_num(t_d) and _num(start) and _num(end) and _num(deadline)):
        return "INCONCLUSO", "preparación inválida: pause_order sin tiempos", {}
    # R12: la pausa tiene que estar bien preparada para que el veredicto valga.
    invalid = []
    if not t_d <= start < end:
        invalid.append("T_d <= T_s < T_e")
    if end - start < 1900:
        invalid.append("T_e - T_s >= 1900")
    if start - t_d > 300:
        invalid.append("T_s - T_d <= 300")
    if not start < deadline < end:
        invalid.append("T_s < D < T_e")
    applies = [
        ev
        for ev in _events(ctx, "apply")
        if ev.get("op_id") == op
        and (order.get("session") is None or ev.get("session") == order["session"])
    ]
    if not applies or any(ev.get("ttl_ms") != 1500 for ev in applies):
        invalid.append("apply con ttl_ms 1500")
    if invalid:
        return "INCONCLUSO", "preparación inválida: " + ", ".join(invalid), {}
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


G7_INVALID = (
    "invalid_no_ok_P",
    "invalid_ok_false_P",
    "invalid_now_decimal_P",
    "invalid_now_text_P",
    "invalid_all_P",
)
# Brief v1.5, H-08: una orden sin args (o con args:{}) es valida como respuesta y el verbo la rechaza
# (rejected/bad_args): son medidas, y las ops que las llevan no pueden tener effect.
G7_MEASURE_OPS = ("measure_no_args_P", "measure_args_empty_P")
G7_REQUIRED = (
    [f"status{code}_{ch}" for code in (400, 401, 409, 413, 500) for ch in ("P", "R")]
    + ["timeout_P", "r_held"]
    + list(G7_INVALID)
    + ["measure_ok1_P"]
    + list(G7_MEASURE_OPS)
    + ["late_cb"]
)


def _is_measure(case):
    name = str(case.get("name"))
    return name.startswith("status") or name.startswith("measure_")


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
    if not _clock_ok(ctx):
        return "INCONCLUSO", "sin ancla de hora de pared (manifest.t0_wall o start.wall)", {}
    why = _coverage([case.get("name") for case in cases], G7_REQUIRED)
    if why:
        return "INCONCLUSO", "cobertura incompleta: " + why, {}
    lease = _manifest_int(ctx, "lease_ms")
    # R21: las medidas tambien exigen la inyeccion observada; lo medido puede ser cualquier cosa.
    why, _ = _injection(ctx, cases)
    if why:
        return "INCONCLUSO", why, {}
    effects = _effects(ctx)
    lines = _all_lines(ctx)
    anchors = [case.get("t_ms") for case in cases if _num(case.get("t_ms"))]
    problems = []
    metrics = {"cases": {}}
    measure_lines = [ev for ev in lines if ev.get("kind") in ("rest_error", "rest_invalid")]
    for index, case in enumerate(cases):
        name = str(case.get("name"))
        ids = _case_rule_ids(case)
        rule = ids[0] if ids else None
        moment = case.get("t_ms")
        entry = {}
        metrics["cases"][name] = entry
        if not _num(moment):
            problems.append(f"{name}: sin t_ms")
            continue
        next_start = math.inf
        for later in cases[index + 1 :]:
            if _num(later.get("t_ms")) and later["t_ms"] > moment:
                next_start = later["t_ms"]
                break
        measure = _is_measure(case)
        fire_line = _fire_line(ctx, case, rule, proxy) if rule is not None else None
        # R10: de su primer disparo en el proxy al rules_active vacio; la recuperacion queda fuera.
        start = fire_line["t_ms"] if fire_line is not None else moment
        end = _prohibition_end(ctx, start)
        tol_hi = WINDOW_TOL_MS
        if end is None:
            if not measure:
                raise EvidenceError(f"{name}: sin rules_active vacio que cierre la inyeccion")
            end, tol_hi = next_start, 0
        if name == "r_held":
            # R11: huecos entre polls de mantenimiento del disparo del acuse retenido a su
            # liberacion (t_done_ms de esa linea), extremos incluidos.
            release = fire_line.get("t_done_ms")
            if not _num(release):
                return "INCONCLUSO", "r_held: la linea del proxy sin t_done_ms", metrics
            polls = [
                ev
                for ev in proxy
                if ev.get("peer") == "server"
                and ev.get("deliver") == 0
                and ev.get("route") == "poll"
                and _num(ev.get("t_ms"))
                and start <= ev["t_ms"] <= release
            ]
            times = [start] + sorted(ev["t_ms"] for ev in polls) + [release]
            gaps = [b - a for a, b in zip(times, times[1:])]
            entry["polls"] = len(polls)
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
                and _in_window(ctx, ev, start, end, tol_hi=tol_hi)
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
                problems.append(f"{name}: {len(invalid)} rest invalid != {len(rewritten)} reescritas")
            window_effects = _window_effects(ctx, effects, start, end, tol_hi=tol_hi)
            if window_effects:
                problems.append(f"{name}: effect en la ventana")
            if name == "invalid_all_P":
                # R22: mayor tramo del caso sin respuestas validas de P al servidor, del proxy.
                gap = _longest_invalid_p_gap(proxy, rule, start, end)
                entry["invalid_gap_ms"] = gap
                if gap > lease:
                    if not _any_lease_lost(ctx, start, end):
                        problems.append(f"{name}: sin lease lost pese a > lease_ms")
                else:
                    return "INCONCLUSO", f"{name}: la ventana no superó el lease", metrics
        elif name == "late_cb":
            late_lines = [
                ev
                for ev in lines
                if ev.get("kind") in ("rest_late", "rest_repeat")
                and _in_window(ctx, ev, start, end, tol_hi=tol_hi)
            ]
            if not late_lines:
                entry["late_cb"] = "inconcluso (sin rest late/repeat)"
            else:
                stop = min(end, _first_recovery_after(ctx, start))
                recovery = _recovery_ops(ctx)
                changes = [
                    ev
                    for ev in _events(ctx, "op_state")
                    if _num(ev.get("t_ms"))
                    and start <= ev["t_ms"] < stop
                    and (ev.get("session"), ev.get("op_id")) not in recovery
                ]
                entry["changes"] = len(changes)
                if changes:
                    problems.append("late_cb: cambio de estado en la ventana")
            # R24: ninguna linea effect en la ventana, salvo las de las ops de recuperacion.
            window_effects = _window_effects(ctx, effects, start, end, tol_hi=tol_hi)
            entry["effects_in_window"] = len(window_effects)
            if window_effects:
                problems.append("late_cb: effect en la ventana")
        elif name == "timeout_P":
            # Plazo efectivo: desde que el proxy recibe la peticion retenida hasta la linea
            # rest timeout de P dentro del caso (las dos en el reloj del arnes).
            timeout = next(
                (
                    ev
                    for ev in lines
                    if ev.get("kind") == "rest_timeout"
                    and ev.get("ch") == "P"
                    and _in_window(ctx, ev, start, end, tol_hi=tol_hi)
                ),
                None,
            )
            t_timeout = _line_t(ctx, timeout) if timeout is not None else None
            entry["timeout_ms"] = t_timeout - start if t_timeout is not None else None
        else:
            # Medidas (status*, measure_*): se anota lo observado, sin tumbar la fila (R9).
            entry["injection_observed"] = fire_line is not None
            channel = name.rsplit("_", 1)[-1]
            line = next(
                (
                    ev
                    for ev in measure_lines
                    if ev.get("ch") == channel and _in_window(ctx, ev, start, end, tol_hi=tol_hi)
                ),
                None,
            )
            if line is None:
                entry["state"] = None
            elif line.get("kind") == "rest_invalid":
                entry["state"] = "invalid"
            else:
                entry["state"] = line.get("state")
            key = _case_key(case)
            if key is not None:
                states = _states(ctx, *key)
                entry["op_state"] = states[-1].get("state") if states else None
            if name in G7_MEASURE_OPS:
                # H-08: la orden con args ausentes o vacios se rechaza; nunca puede tener effect.
                # Su op es la del apply del caso (el case se escribe antes del apply).
                applies = [
                    ev
                    for ev in _events(ctx, "apply")
                    if _num(ev.get("t_ms")) and moment <= ev["t_ms"] < min(end, next_start)
                    and ev.get("op_id")
                ]
                if not applies:
                    problems.append(f"{name}: sin apply en el caso")
                for ev in applies:
                    bad = [
                        eff
                        for eff in effects
                        if eff.get("op") == ev.get("op_id") and eff.get("session") == ev.get("session")
                    ]
                    entry.setdefault("op_effects", {})[str(ev.get("op_id"))] = len(bad)
                    if bad:
                        problems.append(f"{name}: effect para una orden rechazada ({ev.get('op_id')})")
        ok, latency, why = _recovery(ctx, case, anchors)
        entry["recovery_ms"] = latency
        if not ok:
            problems.append(f"{name}: {why}")
    if problems:
        return "FALLA", "; ".join(problems), metrics
    return "PASA", "", metrics


def _longest_invalid_p_gap(proxy, rule, start, end):
    """R22: mayor tramo de [start, end] sin una respuesta valida de P (hello/poll) al servidor.

    Valida = un 200 que la regla del caso no reescribio. Cuenta por `t_done_ms`; los extremos de la
    ventana cierran el primer y el ultimo tramo.
    """
    done = sorted(
        (ev["t_done_ms"] if _num(ev.get("t_done_ms")) else ev["t_ms"])
        for ev in proxy
        if ev.get("peer") == "server"
        and ev.get("route") in P_ROUTES
        and ev.get("upstream_status") == 200
        and ev.get("rule_id") != rule
        and _num(ev.get("t_ms"))
    )
    inside = [value for value in done if start <= value <= end]
    times = [start] + inside + [end]
    return max(b - a for a, b in zip(times, times[1:]))


def _g8(ctx):
    missing = _missing_logs(ctx, SCRIPT_LOGS)
    if missing:
        return "INCONCLUSO", "log ausente: " + ", ".join(missing), {}
    effects = _effects(ctx)
    cases = _events(ctx, "case")
    if not cases:
        return "INCONCLUSO", "sin casos G8", {}
    why = _coverage([case.get("name") for case in cases], ["a", "b", "c"])
    if why:
        return "INCONCLUSO", "cobertura incompleta: " + why, {}
    why, _ = _injection(ctx, [case for case in cases if case.get("name") in ("a", "b")])
    if why:
        return "INCONCLUSO", why, {}
    results = _events(ctx, "result_seen")
    problems = []
    metrics = {"cases": {}}
    for case in cases:
        name = case.get("name")
        entry = {}
        metrics["cases"][str(name)] = entry
        key = _case_key(case)
        if key is None:
            problems.append(f"{name}: sin op_id")
            continue
        session, op = key
        pair = _pair(effects, session, op)
        entry["pair"] = pair
        if name in ("a", "b", "c"):
            ok, detail = _exact_pair(pair)
            if not ok:
                problems.append(f"{name}: {detail}")
        else:
            problems.append(f"caso desconocido {name}")
        if name == "a":
            observed = [ev for ev in _states(ctx, session, op) if ev.get("state") == "observado"]
            entry["observed"] = len(observed)
            # R23: al menos 2 result_seen de la op (el que perdio su acuse y la repeticion) y una
            # sola transicion a observado.
            op_results = [ev for ev in results if ev.get("op_id") == op]
            entry["result_seen"] = len(op_results)
            if len(op_results) < 2:
                problems.append("a: menos de 2 result_seen de la op")
            if len(observed) != 1:
                problems.append(f"a: {len(observed)} transiciones a observado (debe ser 1)")
        elif name == "b":
            duplicates = [ev for ev in results if ev.get("op_id") == op and ev.get("dup") is True]
            entry["dups"] = len(duplicates)
            if not duplicates:
                problems.append("b: sin result_seen dup true")
            else:
                op_results = [ev for ev in results if ev.get("op_id") == op]
                if len(op_results) > 1:
                    first = min(ev["t_ms"] for ev in op_results if _num(ev.get("t_ms")))
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
    distinct = {ev.get("op_id") for ev in ops if ev.get("op_id") is not None}
    if len(ops) != 100 or len(distinct) != 100:
        return (
            "INCONCLUSO",
            f"cobertura incompleta: {len(ops)} mix_op con {len(distinct)} op_id distintos (se esperan 100)",
            {"n_ops": len(ops)},
        )
    gap = _events(ctx, "gap_reset") or _gap_reset_from_g5(ctx)
    if not gap:
        return "INCONCLUSO", "sin gap_reset", {}
    if gap[-1].get("confirmed") is not True:
        return "FALLA", "gap_reset no confirmado", {}
    effects = _effects(ctx)
    applies = {}
    for ev in _events(ctx, "apply"):
        if ev.get("op_id") is not None:
            applies.setdefault((ev.get("session"), ev["op_id"]), ev)
    observed = {}
    for ev in _events(ctx, "op_state"):
        if ev.get("state") == "observado" and ev.get("op_id") is not None:
            observed.setdefault((ev.get("session"), ev["op_id"]), ev)
    latencies = []
    missing_pairs = 0
    read_time = 0
    for ev in ops:
        op = ev.get("op_id")
        session = ev.get("session")
        if session is None:
            owners = {key[0] for key in applies if key[1] == op}
            if len(owners) > 1:
                raise EvidenceError(f"evidencia invalida: mix_op {op} en varias sesiones")
            session = next(iter(owners), None)
        apply = applies.get((session, op))
        done = observed.get((session, op))
        if (
            apply is not None
            and done is not None
            and _num(apply.get("t_ms"))
            and _num(done.get("t_ms"))
        ):
            latency = done["t_ms"] - apply["t_ms"]
            if latency < 0:
                raise EvidenceError(f"evidencia inválida: latencia negativa en {op} ({latency} ms)")
            if done.get("t_src") == "lectura":
                read_time += 1
            latencies.append(latency)
        else:
            latencies.append(math.inf)
        if not _exact_pair(_pair(effects, session, op))[0]:
            missing_pairs += 1
    ordered = sorted(
        latencies, key=lambda value: (math.isinf(value), value if not math.isinf(value) else 0)
    )
    p50 = ordered[math.ceil(0.50 * 100) - 1]
    p95 = ordered[math.ceil(0.95 * 100) - 1]
    metrics = {
        "n_ops": 100,
        "ops_sin_pareja": missing_pairs,
        "op_state_t_lectura": read_time,
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
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        marker = line.find("[DSBX] ")
        if marker >= 0:
            event = _parse_line(line[marker + 7 :].strip())
            if event is not None:
                event["wall_ms"] = _wall_ms(line)
                event["file"] = path.name
                event["lineno"] = lineno
                events.append(event)
            continue
        leak = _EXIT_LEAK.search(line) if _SCRIPT_ERROR.search(line) else None
        if leak is not None:
            events.append({"kind": "exit_leak", "cls": leak.group(1), "n": int(leak.group(2)), "text": line})
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
    if payload.startswith("shutdown "):
        created = _as_int(fields.get("created_n"))
        if created is None:
            return None
        return {"kind": "shutdown", "role": fields.get("role"), "created_n": created}
    return None


def _clock_metrics(ctx, start, end):
    """Medidas de G6 con las lineas clock del servidor (solo su reloj; el cliente es otro proceso).

    clock_slope: pendiente de tick_ms frente al reloj del arnes (por la hora de pared de cada linea).
    clock_pause_*: salto entre las dos lineas clock que rodean la pausa [start, end].
    """
    points = []
    for ev in _log(ctx, "server_script.log") or []:
        if ev.get("kind") == "clock" and _num(ev.get("tick_ms")):
            t = _line_t(ctx, ev)
            if t is not None:
                points.append((t, ev["tick_ms"]))
    points.sort()
    metrics = {"clock_n": len(points)}
    if len(points) >= 2:
        times = [t for t, _ in points]
        ticks = [tick for _, tick in points]
        mean_t = sum(times) / len(times)
        mean_tick = sum(ticks) / len(ticks)
        denominator = sum((t - mean_t) ** 2 for t in times)
        numerator = sum((t - mean_t) * (tick - mean_tick) for t, tick in points)
        metrics["clock_slope"] = numerator / denominator if denominator else None
        straddle = [(a, b) for a, b in zip(points, points[1:]) if a[0] <= start and b[0] >= end]
        if straddle:
            a, b = straddle[0]
            metrics["clock_pause_t_step_ms"] = b[0] - a[0]
            metrics["clock_pause_tick_step_ms"] = b[1] - a[1]
        else:
            metrics["clock_pause_t_step_ms"] = None
            metrics["clock_pause_tick_step_ms"] = None
    return metrics


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
            if ev.get("kind") == "lease_lost" and _in_window(ctx, ev, start, end):
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
    if verdict.get("reason"):
        print(f"REASON {verdict['reason']}")
    print(f"AGGREGATE {verdict['aggregate']}")
    return EXIT[verdict["aggregate"]]


if __name__ == "__main__":
    sys.exit(main())
