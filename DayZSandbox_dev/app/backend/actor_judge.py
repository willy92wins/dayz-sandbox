"""Jueces puros C1–C4 (F3-offline-1 §3). Sin E/S; solo stdlib."""
import math
from collections import Counter

from app.backend.actor_wire import valid_actor_row, valid_gesture_event

_TERMINAL = frozenset({"finished", "canceled", "rejected", "expired"})


def _out(verdict, why, **extra):
    rec = {"verdict": verdict, "why": why}
    rec.update(extra)
    return rec


def _xz_m(row):
    return row[2] / 1000.0, row[4] / 1000.0


def _dist(x1, z1, x2, z2):
    return math.hypot(x1 - x2, z1 - z2)


def _is_dead(row):
    return row[1] is None


def _common_samples(samples):
    """Comprobaciones comunes de `samples`, en el orden de §3. None si pasan."""
    if not isinstance(samples, list):
        return _out("INCONCLUSO", "lectura_invalida")
    lids = []
    times = []
    for row in samples:
        if not valid_actor_row(row):
            return _out("INCONCLUSO", "lectura_invalida")
        lids.append(row[0])
        times.append(row[9])
    if samples:
        if len(set(lids)) != 1:
            return _out("INCONCLUSO", "lectura_invalida")
        for a, b in zip(times, times[1:]):
            if b <= a:
                return _out("INCONCLUSO", "lectura_invalida")
    if not samples:
        return _out("INCONCLUSO", "sin_cobertura")
    for row in samples:
        if _is_dead(row):
            return _out("INCONCLUSO", "muerto")
    return None


def _window_covered(samples, a, b, max_gap_ms):
    """True si [a, b] está cubierta según §3 Cobertura."""
    le = [i for i, s in enumerate(samples) if s[9] <= a]
    ge = [i for i, s in enumerate(samples) if s[9] >= b]
    if not le or not ge:
        return False, []
    i0, i1 = le[-1], ge[0]
    if i1 < i0:
        return False, []
    sl = samples[i0 : i1 + 1]
    for u, v in zip(sl, sl[1:]):
        if v[9] - u[9] > max_gap_ms:
            return False, sl
    return True, sl


def _in_time(samples, a, b):
    return [s for s in samples if a <= s[9] <= b]


def _faltan_sobran(expected, got):
    ce, cg = Counter(expected), Counter(got)
    faltan, sobran = [], []
    for key in sorted(set(ce) | set(cg)):
        if ce[key] > cg[key]:
            faltan.extend([key] * (ce[key] - cg[key]))
        if cg[key] > ce[key]:
            sobran.extend([key] * (cg[key] - ce[key]))
    return faltan, sobran


def judge_identity(expected, row):
    """C1: clase vanilla y multiconjunto de prendas."""
    if not valid_actor_row(row):
        return _out("INCONCLUSO", "lectura_invalida")
    if _is_dead(row):
        return _out("INCONCLUSO", "muerto")
    if row[1] != expected["cls"]:
        return _out("FALLA", "clase")
    faltan, sobran = _faltan_sobran(expected["items"], row[6])
    if faltan or sobran:
        return _out("FALLA", "vestuario", faltan=faltan, sobran=sobran)
    return _out("PASA", None)


def judge_mark(
    samples,
    mark_i,
    mark,
    reach_m=1.5,
    settle_m=0.5,
    settle_ms=10000,
    max_gap_ms=1000,
):
    """C2: llegada a marca por distancia medida, no por `mark_st`."""
    common = _common_samples(samples)
    if common is not None:
        return common
    mx, mz = mark["x"], mark["z"]
    for row in samples:
        if row[7] == mark_i and row[8] == "unreachable":
            return _out("FALLA", "inalcanzable")

    pasa = None
    saw_no_quieto = False
    saw_candidate = False
    min_dist = None
    for row in samples:
        x, z = _xz_m(row)
        d = _dist(x, z, mx, mz)
        if min_dist is None or d < min_dist:
            min_dist = d
        if d >= reach_m:
            continue
        saw_candidate = True
        t0 = row[9]
        covered, sl = _window_covered(samples, t0, t0 + settle_ms, max_gap_ms)
        if settle_ms == 0:
            covered, sl = True, [row]
        if not covered:
            continue
        drift = 0.0
        for s in sl:
            sx, sz = _xz_m(s)
            drift = max(drift, _dist(sx, sz, x, z))
        if drift < settle_m:
            if pasa is None:
                pasa = _out("PASA", None, t0=t0, drift_m=drift)
        else:
            saw_no_quieto = True
    if pasa is not None:
        return pasa
    if saw_no_quieto:
        return _out("FALLA", "no_quieto")
    if saw_candidate:
        return _out("INCONCLUSO", "sin_cobertura")
    return _out("FALLA", "no_llega", min_dist_m=min_dist)


def judge_gesture(events, lid, gi):
    """C3: secuencia de gesto de un (lid, gi)."""
    seq = [ev for ev in events if isinstance(ev, list) and len(ev) >= 2 and ev[0] == lid and ev[1] == gi]
    for ev in seq:
        if not valid_gesture_event(ev):
            return _out("INCONCLUSO", "lectura_invalida")
    times = [ev[3] for ev in seq]
    for a, b in zip(times, times[1:]):
        if b < a:
            return _out("INCONCLUSO", "lectura_invalida")
    if not seq:
        return _out("INCONCLUSO", "sin_fin")
    if seq[0][2] != "requested":
        return _out("FALLA", "sin_pedido")
    seen = []
    for ev in seq:
        if ev[2] in seen:
            return _out("FALLA", "repetido")
        seen.append(ev[2])
    terminals = [i for i, ev in enumerate(seq) if ev[2] in _TERMINAL]
    if terminals:
        first_term = terminals[0]
        if first_term != len(seq) - 1:
            return _out("FALLA", "despues_del_fin")
        term = seq[first_term][2]
        if term == "canceled":
            return _out("FALLA", "cancelado")
        if term == "rejected":
            return _out("FALLA", "rechazado")
        if term == "expired":
            return _out("FALLA", "agotado")
        had_playing = any(ev[2] == "playing" for ev in seq[:first_term])
        if not had_playing:
            return _out("FALLA", "fin_sin_empezar")
        t_req = next(ev[3] for ev in seq if ev[2] == "requested")
        t_play = next(ev[3] for ev in seq if ev[2] == "playing")
        t_fin = seq[first_term][3]
        if t_play == t_fin:
            return _out("FALLA", "duracion_cero")
        if t_req <= t_play < t_fin:
            return _out("PASA", None)
        return _out("FALLA", "duracion_cero")
    return _out("INCONCLUSO", "sin_fin")


def judge_hold(samples, window_ms, settle_m=0.5, max_gap_ms=1000):
    """C4 HOLD: deriva horizontal respecto de la primera muestra."""
    common = _common_samples(samples)
    if common is not None:
        return common
    t0 = samples[0][9]
    x0, z0 = _xz_m(samples[0])
    win = _in_time(samples, t0, t0 + window_ms)
    max_drift = 0.0
    for row in win:
        x, z = _xz_m(row)
        max_drift = max(max_drift, _dist(x, z, x0, z0))
    if max_drift >= settle_m:
        return _out("FALLA", "se_mueve", max_drift_m=max_drift)
    covered, _sl = _window_covered(samples, t0, t0 + window_ms, max_gap_ms)
    if not covered:
        return _out("INCONCLUSO", "sin_cobertura")
    return _out("PASA", None, max_drift_m=max_drift)


def judge_roam(
    samples,
    p0,
    radius_m,
    window_ms,
    min_path_m,
    min_stops_n,
    stop_ms=1000,
    stop_speed_mps=0.2,
    max_gap_ms=1000,
):
    """C4 ROAM: radio, recorrido y paradas medidas (sin `mark_st`)."""
    common = _common_samples(samples)
    if common is not None:
        return common
    t0 = samples[0][9]
    win = _in_time(samples, t0, t0 + window_ms)
    px, pz = p0["x"], p0["z"]
    max_dist = 0.0
    for row in win:
        x, z = _xz_m(row)
        max_dist = max(max_dist, _dist(x, z, px, pz))
    path_m = 0.0
    for a, b in zip(win, win[1:]):
        ax, az = _xz_m(a)
        bx, bz = _xz_m(b)
        path_m += _dist(ax, az, bx, bz)
    stops_n = _count_stops(win, stop_ms, stop_speed_mps)
    if max_dist > radius_m:
        return _out(
            "FALLA",
            "fuera_radio",
            max_dist_m=max_dist,
            path_m=path_m,
            stops_n=stops_n,
        )
    covered, _sl = _window_covered(samples, t0, t0 + window_ms, max_gap_ms)
    if not covered:
        return _out("INCONCLUSO", "sin_cobertura")
    if path_m < min_path_m or stops_n < min_stops_n:
        return _out(
            "FALLA",
            "quieto",
            max_dist_m=max_dist,
            path_m=path_m,
            stops_n=stops_n,
        )
    return _out(
        "PASA",
        None,
        max_dist_m=max_dist,
        path_m=path_m,
        stops_n=stops_n,
    )


def _count_stops(win, stop_ms, stop_speed_mps):
    """Tramos maximales consecutivos con velocidad < umbral y duración ≥ stop_ms."""
    if len(win) < 2:
        return 0
    n = 0
    run_start = None
    prev = win[0]
    for cur in win[1:]:
        dt_s = (cur[9] - prev[9]) / 1000.0
        px, pz = _xz_m(prev)
        cx, cz = _xz_m(cur)
        speed = _dist(px, pz, cx, cz) / dt_s if dt_s > 0 else float("inf")
        slow = speed < stop_speed_mps
        if slow:
            if run_start is None:
                run_start = prev[9]
        else:
            if run_start is not None and prev[9] - run_start >= stop_ms:
                n += 1
            run_start = None
        prev = cur
    if run_start is not None and prev[9] - run_start >= stop_ms:
        n += 1
    return n
