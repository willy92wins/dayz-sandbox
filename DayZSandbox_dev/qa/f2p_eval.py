"""Oráculo E9 de la partida de F2 (F2P-01..F2P-13), semántica v1.3.4 (§6.1).

Decide solo con lecturas independientes: las respuestas crudas de la sonda (censo y testigo), la
traza del proxy del producto, los eventos del backend, las líneas DSBX_SCENE_DEL del mod y los
campos permitidos del manifest. El contrato está en `qa/f2p_evidence_contract.md`.

La base común (§6.1 puntos 1 a 9) está en las funciones `_measurement`, `_terminal_state`,
`_generation`, `_census_union`, `_trace_violations`, `_reconciliation_ok`, `_witness_windows` y
`_server_restart_ok`. Todas las comprobaciones consumen esas funciones.

Códigos de salida: 0 PASA, 1 FALLA, 2 INCONCLUSO (`gate_core.py:73-82`).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import gate_core
import wire

SPIKE_ID = "F2P"

CHECK_IDS = (
    "F2P-01",
    "F2P-02",
    "F2P-03",
    "F2P-04",
    "F2P-05",
    "F2P-06",
    "F2P-07",
    "F2P-08",
    "F2P-09",
    "F2P-10",
    "F2P-11",
    "F2P-12",
    "F2P-13",
)

ALLOWED_MANIFEST_KEYS = frozenset({
    "schema", "id", "kind", "build", "both", "params", "identity", "f2p",
})

PART_ORDER = ("P1", "P2", "P2n", "P3", "P3c", "P4a", "P4b", "P4c", "P5")
OPERATION_PARTS = ("P2", "P2n", "P3", "P4a", "P4b", "P5")

# Etapas canónicas del testigo por parte. `witness_tag` es opcional (interfaz de F0.3): si llega vacío,
# el oráculo lo resuelve por la ventana de la parte y el orden de arranque, nunca lo rechaza.
WITNESS_STAGES = {
    "P1": ("control",),
    "P2": ("apply",),
    "P2n": ("apply",),
    "P3": ("apply1", "apply2"),
    "P4a": ("apply1",),
    "P4b": ("apply",),
    "P5": ("cut",),
}

TERMINAL_STATES = frozenset({"observado", "parcial", "fallido"})
# Comprobaciones que juzga la op de cada parte: una violación de traza tumba la comprobación de su parte
# (revisión del orquestador sobre T2d-1; §6.1 punto 5).
TRACE_PART_CHECKS = {
    "P2": ("F2P-01", "F2P-04"),
    "P2n": ("F2P-03",),
    "P3": ("F2P-05",),
    "P3c": ("F2P-06",),
    "P4a": ("F2P-08",),
    "P4b": ("F2P-07",),
    "P4c": ("F2P-07",),
    "P5": ("F2P-09",),
}
WITNESS_CENTER = (6170.0, 7643.0)
WITNESS_RADIUS = 120.0
COVERAGE_EDGE_M = 15.0

EPS_OBJ_M = 0.5          # posición de una entidad respecto al documento
JUMP_MAX_M = 0.3         # salto entre EEInit y el tick 1 (Q-01)
WITNESS_CENSUS_TOL_M = 0.05  # F2P-12
CONTROL_POS = (6100.0, 7700.0)
CONTROL_CLASS = "WoodenCrate"
CONTROL_HP = 73.0

_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_HEX16 = re.compile(r"^[0-9a-fA-F]{16}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_NET_ID = re.compile(r"^-?\d+:-?\d+$")


def _load_jsonl(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            item = json.loads(s)
            if not isinstance(item, dict):
                return None
            rows.append(item)
    except Exception:
        return None
    return rows


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _unpack(obj: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]] | None:
    if not isinstance(obj, dict):
        return None
    try:
        u = wire.unpack_payload(obj)
        return u["str"], u["num"], u["rows"]
    except Exception:
        return None


def _finite(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _dist(a: dict[str, Any], x: float, y: float, z: float) -> float:
    return math.sqrt((float(a["pos_x_m"]) - x) ** 2 + (float(a["pos_y_m"]) - y) ** 2 +
                     (float(a["pos_z_m"]) - z) ** 2)


def _dist2(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.sqrt((float(a["pos_x_m"]) - float(b["pos_x_m"])) ** 2 +
                     (float(a["pos_y_m"]) - float(b["pos_y_m"])) ** 2 +
                     (float(a["pos_z_m"]) - float(b["pos_z_m"])) ** 2)


def _dist_xz(a: dict[str, Any], b: dict[str, Any]) -> float:
    return math.hypot(float(a["pos_x_m"]) - float(b["pos_x_m"]),
                      float(a["pos_z_m"]) - float(b["pos_z_m"]))


def _valid_net(val: Any) -> bool:
    return isinstance(val, str) and bool(_NET_ID.match(val)) and val != "0:0"


def _load_doc1(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / "fixtures" / "escena-sin-actores.json").read_text(encoding="utf-8"))


def _load_doc2(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / "qa" / "fixtures" / "f2p_scene2.json").read_text(encoding="utf-8"))


def _checks_as_list(checks: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": cid, "status": checks[cid]["status"], "detail": checks[cid]["detail"]}
            for cid in CHECK_IDS]


# ---------------------------------------------------------------------------------------------------
# Parseo de la evidencia
# ---------------------------------------------------------------------------------------------------

def _parse_probe(events: list[dict[str, Any]]) -> dict[str, Any]:
    ops: dict[str, dict[str, Any]] = {}
    hellos: list[dict[str, Any]] = []
    for idx, ev in enumerate(events):
        t = ev.get("t_ms")
        if not _finite(t):
            t = float(idx)
        kind = ev.get("ev")
        if kind == "hello" and ev.get("http") == 200 and ev.get("ok") is not False:
            args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
            hellos.append({"peer": str(ev.get("peer") or ""), "inst": str(ev.get("inst") or ""),
                           "proto": str(args.get("proto") or ""), "build": str(args.get("build") or ""),
                           "probe_ver": str(args.get("probe_ver") or ""), "t_ms": float(t)})
        elif kind == "enq":
            oid = str(ev.get("op_id") or "")
            if oid and oid not in ops:
                ops[oid] = {"op_id": oid, "verb": str(ev.get("verb") or ""), "args": ev.get("args"),
                            "peer": str(ev.get("peer") or ""), "inst": str(ev.get("inst") or ""),
                            "t_enq": float(t), "status": None, "reason": "", "read": {},
                            "t_result": None, "inst_result": ""}
        elif kind == "result" and ev.get("http") == 200:
            res = ev.get("result") if isinstance(ev.get("result"), dict) else {}
            oid = str(res.get("op_id") or ev.get("op_id") or "")
            if not oid:
                continue
            op = ops.setdefault(oid, {"op_id": oid, "verb": str(res.get("verb") or ""),
                                      "args": None, "peer": str(ev.get("peer") or ""),
                                      "inst": str(ev.get("inst") or ""), "t_enq": float(t),
                                      "status": None, "reason": "", "read": {}, "t_result": None,
                                      "inst_result": ""})
            op["status"] = str(res.get("status") or "")
            op["reason"] = str(res.get("reason") or "")
            op["read"] = res.get("read") if isinstance(res.get("read"), dict) else {}
            op["t_result"] = float(t)
            op["inst_result"] = str(ev.get("inst") or "")

    jobs: dict[str, dict[str, Any]] = {}
    bad_jobs: set[str] = set()
    for op in ops.values():
        if op["verb"] in ("per_census_start", "per_witness_start") and op["status"] == "done":
            u = _unpack(op["read"])
            if not u:
                continue
            s, n, _ = u
            jid = str(s.get("job") or "")
            if not jid:
                continue
            if op.get("inst_result") and op.get("inst") and op["inst_result"] != op["inst"]:
                bad_jobs.add(jid)
            tag = str(s.get("area_tag") if op["verb"] == "per_census_start" else s.get("witness_tag"))
            jobs[jid] = {
                "job": jid, "kind": "census" if op["verb"] == "per_census_start" else "witness",
                "tag": tag, "part": tag.split(":")[0] if ":" in tag else tag,
                "stage": tag.split(":", 1)[1] if ":" in tag else "",
                "epoch": str(s.get("server_epoch") or ""), "inst": str(op.get("inst") or ""),
                "start_t": op["t_result"],
                "center_x": float(n.get("center_x_m", 0.0)), "center_z": float(n.get("center_z_m", 0.0)),
                "radius": float(n.get("radius_m", 0.0)), "window_ms": float(n.get("window_ms", 0.0)),
                "snap_tick_ms": float(n["snap_tick_ms"]) if _finite(n.get("snap_tick_ms")) else None,
                "snap_frame": float(n["snap_frame"]) if _finite(n.get("snap_frame")) else None,
                "start_tick_ms": float(n["start_tick_ms"]) if _finite(n.get("start_tick_ms")) else None,
                "pages": {}, "rows": [], "pages_n": None, "rows_total": None, "valid": False,
                "min_page_t": None, "max_page_t": None,
            }
    for op in ops.values():
        if op["verb"] != "job_read" or op["status"] != "done":
            continue
        au = _unpack(op["args"]) if op["args"] is not None else None
        ru = _unpack(op["read"])
        if not au or not ru:
            continue
        a_s, a_n, _ = au
        r_s, r_n, r_rows = ru
        a_job = str(a_s.get("job") or "")
        r_job = str(r_s.get("job") or "")
        if not a_job or not r_job or a_job != r_job:
            if a_job:
                bad_jobs.add(a_job)
            if r_job:
                bad_jobs.add(r_job)
            continue
        jid = a_job
        job = jobs.get(jid)
        if job is None:
            continue
        # Las páginas las devuelve la misma instancia del trabajo (§6.1 punto 1, O-06).
        if op.get("inst") and job.get("inst") and op["inst"] != job["inst"]:
            bad_jobs.add(jid)
            continue
        a_pn = a_n.get("page_n")
        r_pn = r_n.get("page_n")
        if not _finite(a_pn) or not _finite(r_pn) or int(a_pn) != int(r_pn):
            bad_jobs.add(jid)
            continue
        if op.get("inst_result") and op.get("inst") and op["inst_result"] != op["inst"]:
            bad_jobs.add(jid)
            continue
        page_epoch = str(r_s.get("server_epoch") or "")
        if page_epoch and page_epoch != job["epoch"]:
            bad_jobs.add(jid)
            continue
        page_n = int(a_pn)
        job["pages"][page_n] = {"t_ms": op["t_result"], "rows": list(r_rows),
                                "resource": str(r_s.get("resource") or ""),
                                "state": str(r_s.get("state") or ""),
                                "pages_n": r_n.get("pages_n"), "rows_total_n": r_n.get("rows_total_n"),
                                "server_epoch": page_epoch}
        if job["pages_n"] is None and _finite(r_n.get("pages_n")):
            job["pages_n"] = int(r_n["pages_n"])
        if job["rows_total"] is None and _finite(r_n.get("rows_total_n")):
            job["rows_total"] = int(r_n["rows_total_n"])
    for job in jobs.values():
        want_res = "per_census" if job["kind"] == "census" else "per_witness"
        pn = job["pages_n"]
        if pn is None or job["rows_total"] is None:
            continue
        if job["job"] in bad_jobs:
            continue
        ok = True
        for p in range(max(pn, 1)):
            page = job["pages"].get(p)
            if page is None or page["resource"] != want_res or page["state"] != "done":
                ok = False
                break
            page_pn = int(page["pages_n"]) if _finite(page["pages_n"]) else -1
            page_rows = int(page["rows_total_n"]) if _finite(page["rows_total_n"]) else -1
            if page_pn != pn or page_rows != job["rows_total"]:
                ok = False
                break
            job["rows"].extend(page["rows"])
        if ok and len(job["rows"]) == job["rows_total"]:
            job["valid"] = True
            ts = [float(pg["t_ms"]) for pg in job["pages"].values() if _finite(pg.get("t_ms"))]
            job["min_page_t"] = min(ts) if ts else job["start_t"]
            job["max_page_t"] = max(ts) if ts else job["start_t"]
    return {"ops": ops, "hellos": hellos, "jobs": jobs}


def _assign_witness_tags(probe: dict[str, Any], manifest: dict[str, Any]) -> None:
    """Resuelve los testigos con `witness_tag` vacío por ventana de parte y orden canónico de etapas."""
    f2p = manifest.get("f2p") if isinstance(manifest.get("f2p"), dict) else {}
    wins: dict[str, tuple[float, float]] = {}
    for p in f2p.get("parts") or []:
        if isinstance(p, dict) and _finite(p.get("start_t_ms")) and _finite(p.get("end_t_ms")):
            wins[str(p.get("name") or "")] = (float(p["start_t_ms"]), float(p["end_t_ms"]))
    for part, stages in WITNESS_STAGES.items():
        win = wins.get(part)
        if win is None:
            continue
        jobs = sorted(
            [j for j in probe["jobs"].values()
             if j["kind"] == "witness" and win[0] <= j["start_t"] <= win[1]],
            key=lambda j: j["start_t"],
        )
        used = set()
        for j in jobs:
            if j["tag"]:
                stage = j["tag"].split(":", 1)[1] if ":" in j["tag"] else ""
                used.add(stage)
        for j in jobs:
            if j["tag"]:
                continue
            stage = next((s for s in stages if s not in used), None)
            if stage is None:
                continue
            j["tag"] = f"{part}:{stage}"
            j["part"] = part
            j["stage"] = stage
            used.add(stage)


def _parse_tap(events: list[dict[str, Any]]) -> dict[str, Any]:
    hellos: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    acks: list[dict[str, Any]] = []
    for ev in events:
        t = ev.get("t_ms")
        if not _finite(t):
            continue
        t = float(t)
        path = str(ev.get("path") or "")
        if ev.get("dir") == "req" and path == "/hello" and isinstance(ev.get("body"), dict):
            b = ev["body"]
            hellos.append({"t_ms": t, "inst": str(b.get("inst") or ""),
                           "epoch": str(b.get("epoch") or ""), "peer": str(b.get("peer") or ""),
                           "build": str(b.get("build") or ""), "session": ""})
        elif ev.get("dir") == "resp" and path == "/poll" and isinstance(ev.get("body"), dict):
            b = ev["body"]
            for o in b.get("ops") or []:
                if isinstance(o, dict):
                    deliveries.append({"t_ms": t, "op_id": str(o.get("op_id") or ""),
                                       "session": str(o.get("session") or ""),
                                       "conn": o.get("conn"), "epoch": str(o.get("epoch") or ""),
                                       "inst": str(o.get("inst") or ""), "verb": str(o.get("verb") or ""),
                                       "args": o.get("args") if isinstance(o.get("args"), dict) else {}})
        elif ev.get("dir") == "req" and path == "/result" and isinstance(ev.get("body"), dict):
            b = ev["body"]
            q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
            results.append({"t_ms": t, "op_id": str(b.get("op_id") or ""),
                            "session": str(b.get("session") or ""), "epoch": str(b.get("epoch") or ""),
                            "conn": q.get("conn"), "inst": str(q.get("inst") or ""),
                            "status": str(b.get("status") or ""), "reason": str(b.get("reason") or ""),
                            "dup": bool(b.get("dup")), "read": b.get("read") if isinstance(b.get("read"), dict) else {}})
        elif ev.get("dir") == "resp" and path == "/result" and isinstance(ev.get("body"), dict):
            acks.append({"t_ms": t, "ok": bool((ev.get("body") or {}).get("ok"))})
    return {"hellos": hellos, "deliveries": deliveries, "results": results, "acks": acks}


def _parse_backend(events: list[dict[str, Any]]) -> dict[str, Any]:
    op_states: list[dict[str, Any]] = []
    restarts: list[dict[str, Any]] = []
    frozen: list[dict[str, Any]] = []
    pbo: list[dict[str, Any]] = []
    api_obs: list[dict[str, Any]] = []
    api_ops: list[dict[str, Any]] = []
    for ev in events:
        kind = ev.get("kind")
        t = ev.get("t_ms")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if kind == "op.state":
            op_states.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "restart":
            restarts.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "oracle.frozen":
            frozen.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "pbo.stamp":
            pbo.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "api.observation":
            api_obs.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "api.ops":
            api_ops.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
    return {"op_states": op_states, "restarts": restarts, "frozen": frozen, "pbo": pbo,
            "api_obs": api_obs, "api_ops": api_ops}


# ---------------------------------------------------------------------------------------------------
# Base común (§6.1 puntos 1 a 9)
# ---------------------------------------------------------------------------------------------------

def _part_window(manifest: dict[str, Any], part: str) -> dict[str, Any] | None:
    f2p = manifest.get("f2p") if isinstance(manifest.get("f2p"), dict) else {}
    for p in f2p.get("parts") or []:
        if isinstance(p, dict) and p.get("name") == part:
            return p
    return None


def _part_for_time(manifest: dict[str, Any], t_ms: float) -> str:
    """Parte cuya ventana contiene `t_ms`; '' si no cae en ninguna (violación global)."""
    f2p = manifest.get("f2p") if isinstance(manifest.get("f2p"), dict) else {}
    for p in f2p.get("parts") or []:
        if not isinstance(p, dict) or not _finite(p.get("start_t_ms")) or not _finite(p.get("end_t_ms")):
            continue
        if float(p["start_t_ms"]) <= float(t_ms) <= float(p["end_t_ms"]):
            return str(p.get("name") or "")
    return ""


def _validate_manifest(manifest: dict[str, Any], repo_root: Path, backend: dict[str, Any],
                       probe: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    ident = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    f2p = manifest.get("f2p") if isinstance(manifest.get("f2p"), dict) else {}
    build = str(manifest.get("build") or "")
    if manifest.get("schema") != "dsbx-qa-manifest/1" or manifest.get("id") != SPIKE_ID or \
            manifest.get("kind") != "spike" or build not in ("diag", "retail", "offline"):
        reasons.append("manifest_incomplete")
    if not _HEX40.match(str(ident.get("git_head") or "")) or \
            not isinstance(ident.get("git_dirty"), bool) or \
            str(ident.get("build") or "") != build or \
            not isinstance(ident.get("params"), dict) or \
            not _HEX16.match(str(ident.get("probe_stamp") or "")) or \
            not isinstance(ident.get("peer_builds"), dict) or \
            not _SHA256.match(str(ident.get("pbo_sha256") or "")) or \
            not _SHA256.match(str(ident.get("product_pbo_sha256") or "")):
        reasons.append("manifest_incomplete")
    if build in ("diag", "retail") and ident.get("git_dirty") is not False:
        reasons.append("manifest_incomplete")
    # H-7: el commit del oráculo es uno solo. `identity.oracle_commit` (lo escribe PartContext con el
    # commit ya verificado) y `f2p.oracle_commit` tienen que ser el mismo id de 40 hex; si no,
    # INCONCLUSO `oracle_modified`.
    ident_oc = str(ident.get("oracle_commit") or "")
    f2p_oc = str(f2p.get("oracle_commit") or "")
    if not _HEX40.match(f2p_oc) or not _HEX40.match(ident_oc) or ident_oc != f2p_oc:
        reasons.append("oracle_modified")
    files = f2p.get("oracle_files") if isinstance(f2p.get("oracle_files"), dict) else {}
    for name in ("f2p_eval.py", "f2p_mutants.py"):
        recorded = str(files.get(name) or "")
        actual = _sha256_file(Path(__file__).with_name(name))
        if recorded != actual:
            reasons.append("oracle_modified")
            break
    storage = f2p.get("storage") if isinstance(f2p.get("storage"), dict) else {}
    if not str(storage.get("path") or "") or not str(storage.get("id") or ""):
        reasons.append("manifest_incomplete")
    ticks = f2p.get("witness_follow_ticks")
    if not isinstance(ticks, int) or ticks < 1 or ticks > 5:
        reasons.append("manifest_incomplete")
    if f2p.get("p2n_variant") not in ("create_failed_first", "create_failed_after", "displaced"):
        reasons.append("manifest_incomplete")
    parts = f2p.get("parts")
    if not isinstance(parts, list) or len(parts) != len(PART_ORDER):
        reasons.append("manifest_incomplete")
    else:
        names = [p.get("name") for p in parts if isinstance(p, dict)]
        if names != list(PART_ORDER):
            reasons.append("manifest_incomplete")
        prev_end = -math.inf
        for p in parts:
            if not isinstance(p, dict) or not _finite(p.get("start_t_ms")) or \
                    not _finite(p.get("end_t_ms")) or float(p["end_t_ms"]) <= float(p["start_t_ms"]) or \
                    float(p["start_t_ms"]) < prev_end or \
                    not re.match(r"^[0-9a-fA-F]{32}$", str(p.get("server_epoch") or "")) or \
                    str(p.get("storage_id") or "") != str(storage.get("id") or ""):
                reasons.append("manifest_incomplete")
                break
            prev_end = float(p["end_t_ms"])
    if backend["frozen"]:
        ev = backend["frozen"][-1]["data"]
        ev_files = ev.get("files") if isinstance(ev.get("files"), dict) else {}
        if str(ev.get("commit") or "") != str(f2p.get("oracle_commit") or ""):
            reasons.append("oracle_modified")
        for name in ("f2p_eval.py", "f2p_mutants.py"):
            if str(ev_files.get(name) or "") != str(files.get(name) or ""):
                reasons.append("oracle_modified")
                break
    else:
        reasons.append("manifest_incomplete")
    if backend["pbo"]:
        ev = backend["pbo"][-1]["data"]
        if str(ev.get("pbo_sha256") or "") != str(ident.get("pbo_sha256") or "") or \
                str(ev.get("product_pbo_sha256") or "") != str(ident.get("product_pbo_sha256") or ""):
            reasons.append("pbo_mismatch")
    else:
        reasons.append("manifest_incomplete")
    peers = {h["peer"] for h in probe["hellos"]}
    if not {"server", "client"}.issubset(peers):
        reasons.append("build_mismatch")
    expected_pv = "dsbx-qa1+" + str(ident.get("probe_stamp") or "")
    for h in probe["hellos"]:
        if h["proto"] != "qa0" or h["build"] != build or h["probe_ver"] != expected_pv:
            reasons.append("build_mismatch")
            break
    return reasons


def _hello_stamp_ok(probe: dict[str, Any], inst: str, expected_pv: str) -> bool:
    return any(h["peer"] == "server" and h["inst"] == inst and h["probe_ver"] == expected_pv
               for h in probe["hellos"])


def _measurement(job: dict[str, Any], *, manifest: dict[str, Any], probe: dict[str, Any],
                 part: str, judged_t: float | None = None,
                 q9_deadline: float | None = None) -> str:
    """Valida una medición (censo o testigo) según §6.1 punto 1.

    Devuelve '' si es válida; en otro caso el motivo ('unbacked_rows'). Es la ÚNICA función que decide
    si una medición cuenta, y la consumen todas las comprobaciones (F2P-10 incluida).
    """
    if not job.get("valid"):
        return "unbacked_rows"
    if job.get("part") != part:
        return "unbacked_rows"
    win = _part_window(manifest, part)
    if win is None:
        return "unbacked_rows"
    if job["epoch"] != str(win.get("server_epoch") or ""):
        return "unbacked_rows"
    if not (float(win["start_t_ms"]) <= job["start_t"] <= float(win["end_t_ms"])):
        return "unbacked_rows"
    ident = manifest.get("identity") or {}
    pv = "dsbx-qa1+" + str(ident.get("probe_stamp") or "")
    # Origen: la instancia que sirvió el trabajo dio /hello 200 con qa0, build y sello.
    if not _hello_stamp_ok(probe, job.get("inst") or "", pv):
        return "unbacked_rows"
    # Todas las páginas con el mismo epoch de la instancia del trabajo.
    epochs = {str(pg.get("server_epoch") or "") for pg in job["pages"].values()}
    if any(e and e != job["epoch"] for e in epochs):
        return "unbacked_rows"
    if job["kind"] == "census":
        snap = job.get("snap_tick_ms")
        frame = job.get("snap_frame")
        if snap is None or frame is None:
            return "unbacked_rows"
        # La captura no puede ser anterior al arranque ni a las páginas leídas.
        if job["start_t"] < snap or job.get("min_page_t", job["start_t"]) < snap:
            return "unbacked_rows"
        # Frescura frente al efecto que juzga.
        if judged_t is not None and snap <= float(judged_t):
            return "unbacked_rows"
        if q9_deadline is not None and snap <= float(q9_deadline):
            return "unbacked_rows"
    else:
        # El testigo se valida además por su ventana (punto 7).
        if job.get("radius") is None or not _finite(job.get("radius")):
            return "unbacked_rows"
        if abs(float(job["radius"]) - WITNESS_RADIUS) > 1e-6:
            return "unbacked_rows"
        if abs(float(job.get("center_x", 0.0)) - WITNESS_CENTER[0]) > 1.0 or \
                abs(float(job.get("center_z", 0.0)) - WITNESS_CENTER[1]) > 1.0:
            return "unbacked_rows"
        if job.get("window_ms") is None or not _finite(job.get("window_ms")) or \
                float(job["window_ms"]) <= 0.0:
            return "unbacked_rows"
        if job.get("start_tick_ms") is None or not _finite(job.get("start_tick_ms")):
            return "unbacked_rows"
        # Sus páginas son posteriores al cierre de la ventana.
        close_t = float(job["start_tick_ms"]) + float(job["window_ms"])
        if float(job.get("min_page_t", job["start_t"])) < close_t:
            return "unbacked_rows"
    return ""


def _terminal_state(backend: dict[str, Any], op_id: str) -> dict[str, Any] | None:
    """Último estado terminal de `op_id` en los `op.state` del backend (los intermedios no cuentan)."""
    best = None
    for st in backend["op_states"]:
        if str(st["data"].get("op_id") or "") != op_id:
            continue
        state = str(st["data"].get("state") or "")
        if state not in TERMINAL_STATES:
            continue
        if best is None or st["t_ms"] >= best["t_ms"]:
            best = st
    return best


def _generation(probe: dict[str, Any], manifest: dict[str, Any], part: str, stage: str,
                doc: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Reconstruye la generación propia de un apply con SU testigo (raíces que casan con el documento)."""
    tag = f"{part}:{stage}"
    job = _witness(probe, tag)
    if job is None:
        return None
    if _measurement(job, manifest=manifest, probe=probe, part=part) != "":
        return None
    out: dict[str, dict[str, Any]] = {}
    for r in job["rows"]:
        if int(r.get("sample_idx", -1)) != 0:
            continue
        if str(r.get("parent_net_id") or "") != "":
            continue
        e = _find_doc_match(r, doc.get("entities") or [])
        if e is None:
            continue
        out[str(r.get("net_id"))] = r
    return out


def _generation_positions(probe: dict[str, Any], manifest: dict[str, Any],
                          doc1: dict[str, Any], doc2: dict[str, Any]) -> list[dict[str, Any]]:
    """Última posición conocida de las entidades de cualquier generación de F2 (§6.1 F2P-07).

    Se reconstruye con el testigo de cada apply; las que no se pueden reconstruir se omiten.
    """
    rows: list[dict[str, Any]] = []
    for part, stage, doc in (("P2", "apply", doc1), ("P3", "apply1", doc1),
                             ("P3", "apply2", doc2), ("P4a", "apply1", doc1),
                             ("P4b", "apply", doc1), ("P5", "cut", doc1)):
        gen = _generation(probe, manifest, part, stage, doc)
        if gen:
            rows.extend(gen.values())
    return rows


def _census_union(probe: dict[str, Any], manifest: dict[str, Any], part: str, main_tag: str,
                  judged_t: float | None = None) -> dict[str, Any]:
    """Unión deduplicada de los discos de censo tomados para un instante (§6.1 punto 4)."""
    main = _census(probe, main_tag)
    if main is None:
        return {"ok": False, "reason": "unbacked_rows", "rows": {}, "disks": []}
    around = float(main.get("snap_tick_ms") or main["start_t"])
    jobs = []
    for job in probe["jobs"].values():
        if job["kind"] != "census":
            continue
        tag = job["tag"]
        if tag != main_tag and tag != f"{part}:extra" and not tag.startswith(main_tag + ":"):
            continue
        if abs(float(job.get("snap_tick_ms") or job["start_t"]) - around) > 20000.0:
            continue
        jobs.append(job)
    rows: dict[str, dict[str, Any]] = {}
    disks: list[tuple[float, float, float]] = []
    for job in jobs:
        if _measurement(job, manifest=manifest, probe=probe, part=part, judged_t=judged_t) != "":
            continue
        disks.append((float(job["center_x"]), float(job["center_z"]), float(job["radius"])))
        for r in job["rows"]:
            net = str(r.get("net_id"))
            if net not in rows:
                rows[net] = r
    if not disks:
        return {"ok": False, "reason": "unbacked_rows", "rows": {}, "disks": []}
    return {"ok": True, "reason": "", "rows": rows, "disks": disks}


def _coverage_status(pos: tuple[float, float], disks: list[tuple[float, float, float]]) -> str:
    """'deep' (>15 m del borde), 'edge' (dentro pero cerca del borde) o 'outside'."""
    best = -math.inf
    for cx, cz, radius in disks:
        d = math.hypot(pos[0] - cx, pos[1] - cz)
        if d <= radius:
            best = max(best, radius - d)
    if best == -math.inf:
        return "outside"
    return "deep" if best > COVERAGE_EDGE_M else "edge"


def _trace_violations(tap: dict[str, Any], backend: dict[str, Any],
                      manifest: dict[str, Any]) -> list[dict[str, str]]:
    """Correlación por (session, op_id) y conn, en orden temporal (§6.1 punto 5).

    Cada violación lleva la parte de la op (por su marca temporal) para que tumbe la comprobación que
    la juzga: P2 → F2P-01/F2P-04, P2n → F2P-03, P3 → F2P-05, P3c → F2P-06, P4a → F2P-08,
    P4b/P4c → F2P-07, P5 → F2P-09. Una violación fuera de parte no tumba una comprobación concreta,
    pero sigue siendo un motivo de INCONCLUSO.
    """
    out: list[dict[str, str]] = []
    deliveries = {}
    for d in tap["deliveries"]:
        deliveries.setdefault(d["op_id"], []).append(d)
    results_by_op = {}
    for r in tap["results"]:
        results_by_op.setdefault(r["op_id"], []).append(r)
    # Una respuesta sin entrega rompe la traza.
    for op_id, rs in results_by_op.items():
        if op_id not in deliveries:
            for r in rs:
                out.append({"part": _part_for_time(manifest, r["t_ms"]),
                            "reason": f"result_without_delivery:{op_id}"})
            continue
        d = min(deliveries[op_id], key=lambda x: x["t_ms"])
        for r in rs:
            if r["session"] and d["session"] and r["session"] != d["session"]:
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"session_mismatch:{op_id}"})
            if r["t_ms"] <= d["t_ms"]:
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"result_before_delivery:{op_id}"})
    # Un op.state sin su /result recibido rompe la traza (salvo el corte de P5, por diseño).
    cut_ops = set()
    p5 = _part_window(manifest, "P5")
    if p5 is not None:
        for d in tap["deliveries"]:
            if d["verb"] == "scene.apply" and \
                    float(p5["start_t_ms"]) <= d["t_ms"] <= float(p5["end_t_ms"]):
                cut_ops.add(d["op_id"])
                break
    for st in backend["op_states"]:
        oid = str(st["data"].get("op_id") or "")
        if not oid:
            continue
        t = float(st.get("t_ms") or 0.0)
        if oid not in deliveries:
            out.append({"part": _part_for_time(manifest, t),
                        "reason": f"op_state_without_delivery:{oid}"})
            continue
        state = str(st["data"].get("state") or "")
        if state in TERMINAL_STATES and oid not in results_by_op and oid not in cut_ops:
            out.append({"part": _part_for_time(manifest, t),
                        "reason": f"op_state_without_result:{oid}"})
    return out


def _reconciliation_ok(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                       part: str, after_t: float, before_t: float) -> bool:
    """Reconciliación (§6.1 punto 6): state.read entregado, resultado válido y backend reconciliada."""
    win = _part_window(manifest, part)
    if win is None:
        return False
    reads = [d for d in tap["deliveries"] if d["verb"] == "state.read" and
             float(win["start_t_ms"]) <= d["t_ms"] <= float(win["end_t_ms"]) and
             after_t <= d["t_ms"] < before_t]
    for d in reads:
        rs = [r for r in tap["results"] if r["op_id"] == d["op_id"] and r["status"] == "done" and
              r["t_ms"] > d["t_ms"] and r["t_ms"] < before_t]
        if not rs:
            continue
        rec = any(str(st["data"].get("op_id") or "") == d["op_id"] and
                  str(st["data"].get("state") or "") in TERMINAL_STATES and
                  str(st["data"].get("reason") or "") == "reconciliada" and
                  st["t_ms"] < before_t
                  for st in backend["op_states"])
        if rec:
            return True
    return False


def _server_restart_ok(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                       part: str) -> bool:
    """Reinicio del servidor acreditado (§6.1 punto 8)."""
    win = _part_window(manifest, part)
    if win is None:
        return False
    epoch = str(win.get("server_epoch") or "")
    storage = manifest.get("f2p", {}).get("storage") if isinstance(manifest.get("f2p"), dict) else {}
    if not isinstance(storage, dict) or str(win.get("storage_id") or "") != str(storage.get("id") or ""):
        return False
    restarts = [r for r in backend["restarts"] if str(r["data"].get("target") or "") == "server" and
                float(win["start_t_ms"]) <= r["t_ms"] <= float(win["end_t_ms"]) and
                str(r["data"].get("epoch") or "") == epoch]
    hellos = [h for h in tap["hellos"] if h["epoch"] == epoch and h["peer"] == "server" and
              float(win["start_t_ms"]) <= h["t_ms"] <= float(win["end_t_ms"])]
    return bool(restarts) and bool(hellos)


def _witness_windows(probe: dict[str, Any], tap: dict[str, Any], manifest: dict[str, Any],
                     part: str) -> dict[str, Any]:
    """Comprueba que hay una ventana de testigo por operación y que cubre su op (§6.1 punto 7)."""
    expected = (("P2", "apply"), ("P2n", "apply"), ("P3", "apply1"), ("P3", "apply2"),
                ("P4a", "apply1"), ("P4b", "apply"), ("P5", "cut"))
    missing: list[str] = []
    win = _part_window(manifest, part)
    if win is None:
        return {"ok": False, "reason": "missing_window"}
    control = _witness(probe, "P1:control")
    if control is None or _measurement(control, manifest=manifest, probe=probe, part="P1") != "":
        missing.append("P1:control")
    for p, stage in expected:
        if p != part and part not in ("P2", "P3"):
            continue
        tag = f"{p}:{stage}"
        job = _witness(probe, tag)
        if job is None:
            missing.append(tag)
            continue
        if _measurement(job, manifest=manifest, probe=probe, part=p) != "":
            missing.append(tag)
            continue
        pwin = _part_window(manifest, p)
        if pwin is None:
            missing.append(tag)
            continue
        start = float(job["start_tick_ms"])
        close = start + float(job["window_ms"])
        # La entrega de la operación tiene que estar dentro de la ventana.
        deliveries = [d for d in tap["deliveries"] if
                      float(pwin["start_t_ms"]) <= d["t_ms"] <= float(pwin["end_t_ms"])]
        applies = [d for d in deliveries if d["verb"] == "scene.apply"]
        if p == "P3":
            want_idx = 0 if stage == "apply1" else 1
        else:
            want_idx = 0
        if len(applies) <= want_idx:
            missing.append(tag + ":no_delivery")
            continue
        d = applies[want_idx]
        if not (start <= d["t_ms"] <= close):
            missing.append(tag + ":delivery_outside")
            continue
        if p == "P5":
            # En P5 la ventana contiene la entrega y el corte (no hay resultado por diseño).
            continue
        results = [r for r in tap["results"] if r["op_id"] == d["op_id"]]
        if not results:
            missing.append(tag + ":no_result")
            continue
        r = min(results, key=lambda x: x["t_ms"])
        if not (start <= r["t_ms"] <= close):
            missing.append(tag + ":result_outside")
    return {"ok": not missing, "reason": ";".join(missing[:5]) if missing else "", "missing": missing}


def _census(probe: dict[str, Any], tag: str) -> dict[str, Any] | None:
    for job in probe["jobs"].values():
        if job["kind"] == "census" and job["tag"] == tag:
            return job
    return None


def _witness(probe: dict[str, Any], tag: str) -> dict[str, Any] | None:
    for job in probe["jobs"].values():
        if job["kind"] == "witness" and job["tag"] == tag:
            return job
    return None


def _tap_op(tap: dict[str, Any], verb: str, part: str, manifest: dict[str, Any],
            before: float | None = None) -> list[dict[str, Any]]:
    win = _part_window(manifest, part)
    if win is None:
        return []
    out = []
    for d in tap["deliveries"]:
        if d["verb"] != verb:
            continue
        if not (float(win["start_t_ms"]) <= d["t_ms"] <= float(win["end_t_ms"])):
            continue
        if before is not None and d["t_ms"] >= before:
            continue
        out.append(d)
    return sorted(out, key=lambda x: x["t_ms"])


def _results_for(tap: dict[str, Any], op_id: str) -> list[dict[str, Any]]:
    return sorted([r for r in tap["results"] if r["op_id"] == op_id], key=lambda x: x["t_ms"])


def _deliveries_for(tap: dict[str, Any], op_id: str) -> list[dict[str, Any]]:
    return sorted([d for d in tap["deliveries"] if d["op_id"] == op_id], key=lambda x: x["t_ms"])


def _doc_poses(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return list(doc.get("entities") or [])


def _find_doc_match(row: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for e in docs:
        if str(row.get("class_name")) != str(e["cls"]):
            continue
        if abs(float(row["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and \
                abs(float(row["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M:
            return e
    return None


def _doc2_nets_in(rows: list[dict[str, Any]], doc2: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for e in doc2.get("entities") or []:
        for r in rows:
            if str(r.get("class_name")) != str(e["cls"]):
                continue
            if abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and \
                    abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M:
                out[str(e["id"])] = str(r.get("net_id"))
                break
    return out


def _yaw_delta(a: Any, b: Any) -> float:
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def _baseline_ok(census_rows: list[dict[str, Any]], buildings: list[tuple[str, float, float, float]]) -> bool:
    for cls, x, z, yaw in buildings:
        found = False
        for r in census_rows:
            if str(r.get("class_name")) != cls:
                continue
            if abs(float(r["pos_x_m"]) - x) <= 0.5 and abs(float(r["pos_z_m"]) - z) <= 0.5 and \
                    _yaw_delta(r.get("yaw_deg"), yaw) <= 2.0:
                found = True
                break
        if not found:
            return False
    return True


# Edificios de referencia reales medidos en la diag de F0.3 (PR #22, run_20261116T000915Z),
# censo a 115 m de (6170, 7643). §6.1 F2P-11.
BUILDINGS = [
    ("Land_Lunapark_Shooting_Gallery", 6137.06, 7643.80, -128.64),
    ("Land_House_2W01", 6212.85, 7644.65, -138.33),
    ("Land_City_Stand_Grocery", 6137.23, 7702.65, 39.30),
    ("Land_House_2B01", 6184.06, 7715.68, -142.45),
]


def _foreign_spawns(probe: dict[str, Any], part: str, manifest: dict[str, Any],
                    probe_ctx: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Reconstruye los ajenos desde sus respuestas crudas de `per_spawn_raw` (F2P-05/F2P-06)."""
    win = _part_window(manifest, part)
    if win is None:
        return None
    out: dict[str, dict[str, Any]] = {}
    for op in probe["ops"].values():
        if op["verb"] != "per_spawn_raw" or op["status"] != "done":
            continue
        t = op.get("t_result")
        if t is None or not (float(win["start_t_ms"]) <= float(t) <= float(win["end_t_ms"])):
            continue
        u = _unpack(op["read"])
        au = _unpack(op["args"]) if op.get("args") is not None else None
        if not u or not au:
            continue
        s, n, _ = u
        mode = str(au[0].get("mode") or "")
        if mode not in ("foreign_ground", "foreign_in_container"):
            continue
        net = str(s.get("net_id") or "")
        if not _valid_net(net):
            continue
        out[net] = {"mode": mode, "class_name": str(s.get("class_name") or ""),
                    "net_id": net, "obs_parent_net_id": str(s.get("obs_parent_net_id") or ""),
                    "target_net_id": str(au[0].get("target_net_id") or ""),
                    "pos_x_m": float(n.get("pos_x_m") or 0.0),
                    "pos_y_m": float(n.get("pos_y_m") or 0.0),
                    "pos_z_m": float(n.get("pos_z_m") or 0.0),
                    "yaw_deg": float(n.get("yaw_deg") or 0.0),
                    "health_hp": float(n.get("health_hp") or 0.0)}
    return out


def _row_inventory(rows: list[dict[str, Any]], net: str) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(r.get("class_name")), str(r.get("net_id")))
                        for r in rows if str(r.get("parent_net_id") or "") == net))


def _pose_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return _dist2(before, after) > 0.05 or _yaw_delta(before.get("yaw_deg", 0.0),
                                                     after.get("yaw_deg", 0.0)) > 1.0


def _delete_confirm_separation(del_rows: list[dict[str, Any]]) -> float:
    """Separación máxima entre la petición y la confirmación del mismo borrado (§6.1 F2P-10, O-17).

    La petición es una línea del mismo `(lid, net_id)` con alguna señal de borrado y sin resultado;
    la confirmación es la línea con `deleted_confirmed_b == 1`. Se usa el reloj común de `t_ms`. Si
    una sola línea lleva señal y confirmación, se usa su `confirm_tick_ms` como confirmación.
    """
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for line in del_rows:
        net = f"{int(line.get('net_high', 0))}:{int(line.get('net_low', 0))}"
        key = (str(line.get("lid") or ""), net)
        by_key.setdefault(key, []).append(line)
    max_sep = 0.0
    for lines in by_key.values():
        ordered = sorted(lines, key=lambda x: float(x.get("t_ms") or 0.0))
        requests = [x for x in ordered
                    if int(x.get("deleted_confirmed_b", 0)) == 0 and
                    int(x.get("delete_failed_b", 0)) == 0 and
                    (int(x.get("signal_ref_b", 0)) == 1 or
                     int(x.get("signal_pending_b", 0)) == 1 or
                     int(x.get("signal_by_netid_b", 0)) == 1)]
        for conf in ordered:
            if int(conf.get("deleted_confirmed_b", 0)) != 1:
                continue
            conf_t = float(conf.get("t_ms") or 0.0)
            req_t = None
            for req in requests:
                rt = float(req.get("t_ms") or 0.0)
                if rt <= conf_t:
                    req_t = rt
            if req_t is not None:
                sep = conf_t - req_t
            else:
                ctk = conf.get("confirm_tick_ms")
                sep = float(ctk) - conf_t if _finite(ctk) and float(ctk) > conf_t else 0.0
            max_sep = max(max_sep, sep)
    return max_sep


def evaluate(part_dir: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    part_dir = Path(part_dir)
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    repo_root = Path(repo_root)

    checks: dict[str, dict[str, str]] = {cid: {"status": "missing", "detail": "not_evaluated"}
                                        for cid in CHECK_IDS}
    reasons: list[str] = []
    metrics: dict[str, Any] = {"delete_confirm_max_ms": 0.0, "witness_census_max_delta_m": 0.0}

    manifest_path = part_dir / "manifest.json"
    samples = part_dir / "samples"
    paths = {name: samples / name for name in
             ("bridge.jsonl", "bridge_tap.jsonl", "backend.jsonl", "scene_del.jsonl")}
    if not manifest_path.is_file() or not all(p.is_file() for p in paths.values()):
        reasons.append("missing_evidence_files")
        return gate_core.make_verdict(SPIKE_ID, 2, checks=_checks_as_list(checks),
                                      metrics=metrics, reasons=reasons)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("manifest_not_dict")
        manifest = {k: v for k, v in raw.items() if k in ALLOWED_MANIFEST_KEYS}
    except Exception:
        reasons.append("corrupt_manifest")
        return gate_core.make_verdict(SPIKE_ID, 2, checks=_checks_as_list(checks),
                                      metrics=metrics, reasons=reasons)

    bridge = _load_jsonl(paths["bridge.jsonl"])
    tap_rows = _load_jsonl(paths["bridge_tap.jsonl"])
    backend_rows = _load_jsonl(paths["backend.jsonl"])
    del_rows = _load_jsonl(paths["scene_del.jsonl"])
    if bridge is None or tap_rows is None or backend_rows is None or del_rows is None or \
            not bridge or not tap_rows or not backend_rows:
        reasons.append("empty_or_corrupt_samples")
        return gate_core.make_verdict(SPIKE_ID, 2, checks=_checks_as_list(checks),
                                      metrics=metrics, reasons=reasons)
    if any(ev.get("ev") == "wire_cap_exceeded" for ev in bridge):
        reasons.append("wire_cap_exceeded")

    probe = _parse_probe(bridge)
    tap = _parse_tap(tap_rows)
    backend = _parse_backend(backend_rows)
    manifest_reasons = _validate_manifest(manifest, repo_root, backend, probe)
    if manifest_reasons:
        reasons.extend(sorted(set(manifest_reasons)))
        return gate_core.make_verdict(SPIKE_ID, 2, checks=_checks_as_list(checks),
                                      metrics=metrics, reasons=reasons)

    _assign_witness_tags(probe, manifest)

    doc1 = _load_doc1(repo_root)
    doc2 = _load_doc2(repo_root)
    docs = _doc_poses(doc1) + _doc_poses(doc2)
    scene_classes = {str(e["cls"]) for e in docs}
    doc1_entities = _doc_poses(doc1)
    scene1_classes = {str(e["cls"]) for e in doc1_entities}

    def fail(cid: str, detail: str) -> None:
        checks[cid] = {"status": "fail", "detail": detail}

    def missing(cid: str, detail: str) -> None:
        checks[cid] = {"status": "missing", "detail": detail}

    def passing(cid: str, detail: str = "ok") -> None:
        checks[cid] = {"status": "pass", "detail": detail}

    def measured(tag: str, kind: str, part: str, judged_t: float | None = None) -> dict[str, Any] | None:
        j = _census(probe, tag) if kind == "census" else _witness(probe, tag)
        if j is None:
            return None
        if _measurement(j, manifest=manifest, probe=probe, part=part, judged_t=judged_t) != "":
            reasons.append("unbacked_rows")
            return None
        return j

    # --- traza del producto (§6.1 punto 5) ---
    trace_bad = _trace_violations(tap, backend, manifest)
    if trace_bad:
        reasons.append("tap_trace_mismatch")

    # --- P1 / P2 base ---
    p1 = measured("P1:base", "census", "P1")
    p2 = measured("P2:post", "census", "P2")
    wit2 = measured("P2:apply", "witness", "P2")

    # Generación de P2 por su testigo (punto 3).
    gen2 = _generation(probe, manifest, "P2", "apply", doc1)
    base_nets = {str(r.get("net_id")) for r in (p1["rows"] if p1 else [])}
    base_rows = {str(r.get("net_id")): r for r in (p1["rows"] if p1 else [])}

    wit_ee = []
    if wit2:
        wit_ee = [r for r in wit2["rows"] if int(r.get("sample_idx", -1)) == 0 and
                  str(r.get("parent_net_id") or "") == "" and
                  _find_doc_match(r, doc1_entities) is not None]
    doc_counter = Counter(str(e["cls"]) for e in doc1["entities"])

    # --- F2P-12 primero: fiabilidad del testigo en objetos (alimenta F2P-02) ---
    witness_reliable = False
    if wit2 and p2:
        objs = [e for e in doc1["entities"] if e["kind"] == "objeto"]
        deltas = []
        ok = True
        for e in objs:
            w = next((r for r in wit_ee if str(r.get("class_name")) == str(e["cls"]) and
                      abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and
                      abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M), None)
            if w is None:
                ok = False
                break
            c = next((r for r in p2["rows"] if str(r.get("net_id")) == str(w.get("net_id"))), None)
            if c is None:
                ok = False
                break
            deltas.append(_dist(w, float(c["pos_x_m"]), float(c["pos_y_m"]), float(c["pos_z_m"])))
        if deltas:
            metrics["witness_census_max_delta_m"] = round(max(deltas), 4)
        if ok and deltas and max(deltas) <= WITNESS_CENSUS_TOL_M:
            witness_reliable = True
            passing("F2P-12", "ok")
        elif ok and deltas:
            missing("F2P-12", "witness_not_final")
        else:
            missing("F2P-12", "witness_or_census_missing")
    else:
        missing("F2P-12", "witness_or_census_missing")

    # --- F2P-01 (§6.1: 33 raíces que casan con el documento, multiconjunto, y presentes en el censo) ---
    if not (p1 and p2 and wit2 and wit_ee and gen2 is not None):
        missing("F2P-01", "missing_witness_or_census")
    else:
        if Counter(str(r.get("class_name")) for r in wit_ee) != doc_counter:
            fail("F2P-01", "witness_class_multiset")
        elif len(wit_ee) != 33:
            fail("F2P-01", "witness_creation_count")
        else:
            nets = [str(r.get("net_id")) for r in wit_ee]
            if len(set(nets)) != 33 or not all(_valid_net(n) for n in nets):
                fail("F2P-01", "net_id_invalid_or_duplicate")
            else:
                union = _census_union(probe, manifest, "P2", "P2:post", judged_t=_p2_terminal_t(tap, backend, manifest))
                if not union["ok"]:
                    missing("F2P-01", "unbacked_rows")
                elif any(n not in union["rows"] for n in nets):
                    fail("F2P-01", "witness_net_missing_in_census")
                else:
                    passing("F2P-01")

    # --- F2P-02 ---
    if not (wit2 and p2 and wit_ee):
        missing("F2P-02", "missing_witness_or_census")
    else:
        fails: list[str] = []
        for e in doc1["entities"]:
            w = next((r for r in wit_ee if str(r.get("class_name")) == str(e["cls"]) and
                      abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and
                      abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M), None)
            if w is None:
                fails.append(f"{e['id']}:not_in_witness")
                continue
            surf = w.get("surface_y_m")
            if not _finite(surf):
                missing("F2P-02", "surface_unbacked")
                break
            if _dist(w, float(e["x"]), float(surf), float(e["z"])) > EPS_OBJ_M:
                fails.append(f"{e['id']}:witness_far")
        else:
            if fails:
                fail("F2P-02", ";".join(fails[:5]))
            else:
                # objetos: censo posterior a < 0.5 m del documento
                union2 = _census_union(probe, manifest, "P2", "P2:post",
                                       judged_t=_p2_terminal_t(tap, backend, manifest))
                obj_fail = []
                obj_unbacked = False
                if not union2["ok"]:
                    missing("F2P-02", "unbacked_rows")
                else:
                    for e in doc1["entities"]:
                        if e["kind"] != "objeto":
                            continue
                        w = next((r for r in wit_ee if str(r.get("class_name")) == str(e["cls"]) and
                                  abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and
                                  abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M), None)
                        net = str(w.get("net_id")) if w else ""
                        c = union2["rows"].get(net)
                        if c is None:
                            obj_fail.append(f"{e['id']}:census_missing")
                            continue
                        surf_c = c.get("surface_y_m")
                        if not _finite(surf_c):
                            # El suelo del censo es la altura independiente de la fila; sin ella, INCONCLUSO.
                            obj_unbacked = True
                            break
                        if _dist(c, float(e["x"]), float(surf_c), float(e["z"])) > EPS_OBJ_M:
                            obj_fail.append(f"{e['id']}:census_far")
                    if obj_unbacked:
                        missing("F2P-02", "surface_unbacked")
                    elif obj_fail:
                        fail("F2P-02", ";".join(obj_fail[:5]))
                    elif not witness_reliable:
                        missing("F2P-02", "witness_not_final")
                    else:
                        cre_fail: list[str] = []
                        cre_missing: list[str] = []
                        _check_creatures(manifest, tap, backend, wit2, union2, doc1, doc_counter,
                                         cre_fail, cre_missing)
                        if cre_fail:
                            fail("F2P-02", ";".join(cre_fail[:5]))
                        elif cre_missing:
                            missing("F2P-02", ";".join(cre_missing[:5]))
                        else:
                            passing("F2P-02")

    # --- F2P-03 (§6.1: estímulo acreditado, estado terminal con su motivo, censo lo confirma) ---
    variant = str((manifest.get("f2p") or {}).get("p2n_variant") or "")
    expected = {"create_failed_first": ("fallido", "create_failed"),
                "create_failed_after": ("parcial", "compensada"),
                "displaced": ("fallido", "lectura_no_cumple")}[variant]
    p2n_apply = _tap_op(tap, "scene.apply", "P2n", manifest)
    p2n_census = measured("P2n:clean", "census", "P2n",
                         judged_t=(_terminal_t(tap, backend, p2n_apply[0]["op_id"])
                                   if p2n_apply else None))
    if not p2n_apply:
        missing("F2P-03", "stimulus_not_observed")
    else:
        oid = p2n_apply[0]["op_id"]
        res = _results_for(tap, oid)
        st = _terminal_state(backend, oid)
        wit2n = measured("P2n:apply", "witness", "P2n")
        if not res:
            missing("F2P-03", "no_result")
        elif st is None:
            missing("F2P-03", "no_op_state")
        elif wit2n is None and not res:
            missing("F2P-03", "stimulus_unbacked")
        elif str(st["data"].get("state")) != expected[0] or str(st["data"].get("reason") or "") != expected[1]:
            fail("F2P-03", f"state={st['data'].get('state')}/{st['data'].get('reason')}")
        elif p2n_census is None:
            missing("F2P-03", "census_missing")
        else:
            # El censo posterior no puede conservar ninguna raíz de la escena 1 (ni siquiera con un
            # `net_id` nuevo: se compara por clase y posición con el documento).
            leftovers = []
            for r in p2n_census["rows"]:
                if _find_doc_match(r, doc1_entities) is not None:
                    leftovers.append(f"{r.get('class_name')}@{r.get('net_id')}")
            if leftovers:
                fail("F2P-03", "census_still_has_scene1:" + ",".join(leftovers[:5]))
            else:
                passing("F2P-03")

    # --- F2P-04 (§6.1: dos entregas correlacionadas, dup, y el testigo ve 33, no 66) ---
    p2_apply = _tap_op(tap, "scene.apply", "P2", manifest)
    if not p2_apply or not p2 or wit2 is None:
        missing("F2P-04", "missing_apply")
    else:
        oid = p2_apply[0]["op_id"]
        dels = _deliveries_for(tap, oid)
        res = _results_for(tap, oid)
        if len(dels) < 2:
            fail("F2P-04", "single_delivery")
        elif len(res) < 2:
            fail("F2P-04", "single_result")
        elif len({d.get("session") for d in dels[:2]}) != 1 or \
                len({r.get("session") for r in res[:2]}) != 1:
            fail("F2P-04", "session_mismatch")
        elif res[0].get("dup") is not False or res[1].get("dup") is not True:
            fail("F2P-04", "dup_flag")
        elif _finite((manifest.get("params") or {}).get("ttl_ms")) and \
                res[1]["t_ms"] - res[0]["t_ms"] > float(manifest["params"]["ttl_ms"]):
            fail("F2P-04", "outside_retention")
        else:
            births = [r for r in wit2["rows"] if int(r.get("sample_idx", -1)) == 0 and
                      str(r.get("parent_net_id") or "") == "" and
                      _find_doc_match(r, doc1_entities) is not None]
            if len(births) != 33:
                fail("F2P-04", f"witness_births:{len(births)}")
            else:
                passing("F2P-04")

    # --- F2P-05 ---
    p2_term = _p2_terminal_t(tap, backend, manifest)
    pre3 = measured("P3:pre_reset", "census", "P3",
                    judged_t=_apply_terminal_t(tap, backend, manifest, "P3", 1))
    post31 = measured("P3:post_reset1", "census", "P3", judged_t=_p3_terminal_t(tap, backend, manifest, "reset1"))
    post32 = measured("P3:post_reset2", "census", "P3", judged_t=_p3_terminal_t(tap, backend, manifest, "reset2"))
    wit3 = measured("P3:apply1", "witness", "P3")
    wit3b = measured("P3:apply2", "witness", "P3")
    if not (pre3 and post31 and post32 and p2):
        missing("F2P-05", "missing_p3_census")
    else:
        gen3 = _generation(probe, manifest, "P3", "apply1", doc1)
        gen3b = _generation(probe, manifest, "P3", "apply2", doc2)
        scene1_nets = set(gen3 or {})
        scene2_map = {k: str(v.get("net_id")) for k, v in (gen3b or {}).items()} if gen3b else {}
        # Mapear por id de doc2 (el testigo casa por clase y posición).
        scene2_map = {}
        if gen3b:
            for e in doc2.get("entities") or []:
                for net, r in gen3b.items():
                    if str(r.get("class_name")) == str(e["cls"]) and \
                            abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and \
                            abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M:
                        scene2_map[str(e["id"])] = net
                        break
        scene2_nets = set(scene2_map.values())
        foreigners = _foreign_spawns(probe, "P3", manifest, probe) or {}
        foreign_nets = set(foreigners)
        retained = {str(r.get("net_id")) for r in post31["rows"]} & scene1_nets
        expected_retained = {net for net in retained
                             if any(str(r.get("net_id")) in foreign_nets and
                                    str(r.get("parent_net_id") or "") == net
                                    for r in post31["rows"])}
        fails = []
        if gen3 is None or gen3b is None:
            fails.append("generation_missing")
        if len(scene2_map) != len(doc2["entities"]):
            fails.append("scene2_not_found")
        if retained != expected_retained or len(retained) != 1:
            fails.append("retained_set")
        # ajenos intactos (identidad, clase, pose completa, padre e inventario)
        for net in sorted(foreign_nets):
            before = next((r for r in pre3["rows"] if str(r.get("net_id")) == net), None)
            after = next((r for r in post31["rows"] if str(r.get("net_id")) == net), None)
            if before is None or after is None:
                fails.append(f"{net}:foreign_missing")
                continue
            if str(before.get("class_name")) != str(after.get("class_name")) or \
                    _pose_changed(before, after) or \
                    str(before.get("parent_net_id") or "") != str(after.get("parent_net_id") or "") or \
                    _row_inventory(pre3["rows"], net) != _row_inventory(post31["rows"], net):
                fails.append(f"{net}:foreign_changed")
        # escena 2 intacta antes y después (identidad, clase, pose completa, padre e inventario)
        for e in doc2["entities"]:
            net = scene2_map.get(str(e["id"]))
            if not net:
                continue
            b = next((r for r in pre3["rows"] if str(r.get("net_id")) == net), None)
            a = next((r for r in post31["rows"] if str(r.get("net_id")) == net), None)
            if b is None or a is None or str(b.get("class_name")) != str(a.get("class_name")) or \
                    _pose_changed(b, a) or \
                    str(b.get("parent_net_id") or "") != str(a.get("parent_net_id") or "") or \
                    _row_inventory(pre3["rows"], net) != _row_inventory(post31["rows"], net):
                fails.append(f"{net}:scene2_changed")
        # op parcial/contenido_ajeno dos veces, con su estado terminal y resultado recibido
        resets = _tap_op(tap, "scene.reset", "P3", manifest)
        states = [_terminal_state(backend, d["op_id"]) for d in resets]
        if len(resets) < 2 or any(s is None for s in states[:2]) or \
                any(str(s["data"].get("state")) != "parcial" or str(s["data"].get("reason") or "") != "contenido_ajeno"
                    for s in states[:2]):
            fails.append("reset_state")
        # segundo reset igual (comparación completa de identidad, pose e inventario)
        if {str(r.get("net_id")) for r in post32["rows"]} != {str(r.get("net_id")) for r in post31["rows"]}:
            fails.append("second_reset_diff")
        else:
            for net in {str(r.get("net_id")) for r in post31["rows"]}:
                a = next((r for r in post31["rows"] if str(r.get("net_id")) == net), None)
                b = next((r for r in post32["rows"] if str(r.get("net_id")) == net), None)
                if a is None or b is None or str(a.get("class_name")) != str(b.get("class_name")) or \
                        _pose_changed(a, b) or \
                        str(a.get("parent_net_id") or "") != str(b.get("parent_net_id") or "") or \
                        _row_inventory(post31["rows"], net) != _row_inventory(post32["rows"], net):
                    fails.append(f"{net}:second_reset_changed")
                    break
        if fails:
            # Una generación que no se puede reconstruir es una medición no respaldada, no una FALLA.
            if "generation_missing" in fails:
                missing("F2P-05", ";".join(fails[:5]))
            else:
                fail("F2P-05", ";".join(fails[:5]))
        else:
            passing("F2P-05")

    # --- F2P-06 ---
    clean3c = measured("P3c:clean", "census", "P3c", judged_t=_p3_terminal_t(tap, backend, manifest, "clean"))
    if not (clean3c and pre3 and p2):
        missing("F2P-06", "missing_census")
    else:
        gen3 = _generation(probe, manifest, "P3", "apply1", doc1)
        gen3b = _generation(probe, manifest, "P3", "apply2", doc2)
        scene2_map = {}
        if gen3b:
            for e in doc2.get("entities") or []:
                for net, r in gen3b.items():
                    if str(r.get("class_name")) == str(e["cls"]) and \
                            abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and \
                            abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M:
                        scene2_map[str(e["id"])] = net
                        break
        scene1_nets = set(gen3 or {})
        alive_scene1 = {str(r.get("net_id")) for r in clean3c["rows"]} & scene1_nets
        fails = []
        if gen3b is None or len(scene2_map) != len(doc2["entities"]):
            fails.append("scene2_not_found")
        for e in doc2["entities"]:
            net = scene2_map.get(str(e["id"]))
            if not net:
                continue
            b = next((r for r in pre3["rows"] if str(r.get("net_id")) == net), None)
            a = next((r for r in clean3c["rows"] if str(r.get("net_id")) == net), None)
            if b is None or a is None or str(b.get("class_name")) != str(a.get("class_name")) or \
                    _pose_changed(b, a) or \
                    str(b.get("parent_net_id") or "") != str(a.get("parent_net_id") or "") or \
                    _row_inventory(pre3["rows"], net) != _row_inventory(clean3c["rows"], net):
                fails.append(f"{net}:scene2_changed")
        if alive_scene1:
            fails.append(f"scene1_alive={len(alive_scene1)}")
        # estímulos de la sonda acreditados por sus respuestas crudas
        foreigners = _foreign_spawns(probe, "P3", manifest, probe)
        if not foreigners or len(foreigners) != 2:
            fails.append("foreign_stimulus_unbacked")
        else:
            for net, f in foreigners.items():
                if f["mode"] == "foreign_in_container":
                    if not f["obs_parent_net_id"]:
                        fails.append(f"{net}:obs_parent_missing")
                    elif f["obs_parent_net_id"] != f["target_net_id"]:
                        fails.append(f"{net}:obs_parent_mismatch")
        win3c = _part_window(manifest, "P3c")
        cleanup = [op for op in probe["ops"].values()
                   if op["verb"] == "per_cleanup_qa" and op["status"] == "done" and
                   op.get("t_result") is not None and win3c is not None and
                   float(win3c["start_t_ms"]) <= float(op["t_result"]) <= float(win3c["end_t_ms"])]
        cleaned = None
        for op in cleanup:
            u = _unpack(op["read"])
            if u and _finite(u[1].get("cleaned_raw_n")):
                cleaned = int(u[1]["cleaned_raw_n"])
        if cleaned is None:
            fails.append("cleanup_unbacked")
        elif foreigners and cleaned != len(foreigners):
            fails.append(f"cleaned_raw_n={cleaned}")
        if gen3 is None:
            # Sin la generación de P3 no se puede probar que no queda ninguna propia viva.
            missing("F2P-06", "generation_unbacked")
        elif fails:
            fail("F2P-06", ";".join(fails[:5]))
        else:
            passing("F2P-06")

    # --- F2P-07 ---
    b4 = measured("P4b:post_restart", "census", "P4b", judged_t=_part_restart_t(backend, manifest, "P4b"))
    c4 = measured("P4c:post_restart", "census", "P4c", judged_t=_part_restart_t(backend, manifest, "P4c"))
    if not (b4 and c4):
        missing("F2P-07", "missing_census")
    else:
        fails = []
        control_ok = True
        gen_positions = _generation_positions(probe, manifest, doc1, doc2)
        for j in (b4, c4):
            for r in j["rows"]:
                m = _find_doc_match(r, docs)
                if m is not None:
                    fails.append(f"{j['tag']}:reappeared:{m['id']}")
                # Ninguna entidad de una clase de la escena 1 a menos de 2 m de la última posición
                # conocida de una entidad de cualquier generación, aunque no case con el documento.
                if str(r.get("class_name")) in scene1_classes:
                    if any(_dist2(r, g) < 2.0 for g in gen_positions):
                        fails.append(f"{j['tag']}:near_generation:{r.get('net_id')}")
            ctrl = [r for r in j["rows"] if str(r.get("class_name")) == CONTROL_CLASS and
                    abs(float(r["pos_x_m"]) - CONTROL_POS[0]) <= 0.5 and
                    abs(float(r["pos_z_m"]) - CONTROL_POS[1]) <= 0.5 and
                    abs(float(r.get("health_hp", 0.0)) - CONTROL_HP) <= 1.0]
            if not ctrl:
                control_ok = False
        if fails:
            fail("F2P-07", ";".join(fails[:5]))
        elif not _server_restart_ok(tap, backend, manifest, "P4b") or \
                not _server_restart_ok(tap, backend, manifest, "P4c"):
            missing("F2P-07", "restart_unbacked")
        elif not control_ok:
            missing("F2P-07", "persistent_control_missing")
        else:
            passing("F2P-07")

    # --- F2P-08 (§6.1: reconciliación tras reinicio del backend, conteos y poses 3D, sin extras) ---
    p4a_c = measured("P4a:post_apply2", "census", "P4a", judged_t=_p4a_terminal_t(tap, backend, manifest))
    p4a_apply = _tap_op(tap, "scene.apply", "P4a", manifest)
    rs = _part_restarts(tap, backend, manifest, "P4a")
    if not (p4a_c and p4a_apply and rs):
        missing("F2P-08", "missing_restart_or_apply")
    else:
        restart_t = min(r["t_ms"] for r in rs)
        first_apply_t = min(d["t_ms"] for d in p4a_apply)
        if not _reconciliation_ok(tap, backend, manifest, "P4a", restart_t, first_apply_t):
            missing("F2P-08", "no_reconciliation_before_apply")
        else:
            wit4 = measured("P4a:apply1", "witness", "P4a")
            if wit4 is None:
                missing("F2P-08", "generation_missing")
            else:
                witness_by_doc = {}
                for r in wit4["rows"]:
                    if int(r.get("sample_idx", -1)) != 0 or                             str(r.get("parent_net_id") or "") != "":
                        continue
                    e = _find_doc_match(r, doc1_entities)
                    if e is not None:
                        witness_by_doc[str(e["id"])] = r
                bad = []
                for e in doc1_entities:
                    w = witness_by_doc.get(str(e["id"]))
                    if w is None:
                        bad.append(f"{e['id']}:no_witness")
                        continue
                    matches = [r for r in p4a_c["rows"]
                               if str(r.get("class_name")) == str(e["cls"]) and
                               abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and
                               abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M]
                    if len(matches) != 1:
                        bad.append(f"{e['id']}:count={len(matches)}")
                    elif _dist(matches[0], float(w["pos_x_m"]), float(w["pos_y_m"]),
                               float(w["pos_z_m"])) > EPS_OBJ_M:
                        bad.append(f"{e['id']}:pose")
                if bad:
                    fail("F2P-08", ";".join(bad[:5]))
                else:
                    passing("F2P-08")

    # --- F2P-09 ---
    p5c = measured("P5:post_apply", "census", "P5",
                   judged_t=_apply_terminal_t(tap, backend, manifest, "P5", 1))
    wit5 = measured("P5:cut", "witness", "P5")
    p5_applies = _tap_op(tap, "scene.apply", "P5", manifest)
    if not (p5c and wit5 and p5_applies):
        missing("F2P-09", "missing_cut_evidence")
    else:
        # El corte ocurre antes del reinicio del backend de P5; el reinicio es la cota superior
        # disponible para «anterior al corte». Si no hay reinicio, la última muestra del testigo.
        p5_restarts = _part_restarts(tap, backend, manifest, "P5")
        if p5_restarts:
            cut_boundary = min(float(r["t_ms"]) for r in p5_restarts)
        else:
            cut_boundary = max((float(r.get("tick_ms") or 0.0) for r in wit5["rows"]),
                               default=_p5_cut_t(tap, manifest)) + 1.0
        births = [r for r in wit5["rows"] if int(r.get("sample_idx", -1)) == 0 and
                  str(r.get("parent_net_id") or "") == "" and
                  _find_doc_match(r, doc1_entities) is not None and
                  _finite(r.get("tick_ms")) and float(r["tick_ms"]) < cut_boundary]
        k = len(births)
        cut_oid = p5_applies[0]["op_id"]
        cut_res = _results_for(tap, cut_oid)
        new_apply = [d for d in p5_applies if d["op_id"] != cut_oid]
        if k == 0:
            fail("F2P-09", "no_effect_before_cut")
        elif cut_res:
            fail("F2P-09", "cut_op_had_result")
        elif not new_apply:
            missing("F2P-09", "no_new_apply")
        elif not _reconciliation_ok(tap, backend, manifest, "P5", cut_boundary,
                                    min(d["t_ms"] for d in new_apply)):
            missing("F2P-09", "no_reconciliation_before_new_apply")
        elif p1 is None:
            missing("F2P-09", "unbacked_rows")
        else:
            union5 = _census_union(probe, manifest, "P5", "P5:post_apply",
                                   judged_t=_apply_terminal_t(tap, backend, manifest, "P5", 1))
            if not union5["ok"]:
                missing("F2P-09", "unbacked_rows")
            else:
                # Total final: todas las vivas de las generaciones de P5 dentro de la cobertura,
                # aunque estén desplazadas. Se excluye el baseline de P1 (botín/edificios/control)
                # y se cuenta por clase de la escena 1 y `net_id` nuevo.
                total = 0
                for r in union5["rows"].values():
                    if str(r.get("net_id")) in base_nets:
                        continue
                    if str(r.get("class_name")) not in scene1_classes:
                        continue
                    if int(r.get("alive_b", 0)) != 1:
                        continue
                    # El control persistente reaparece con un `net_id` nuevo; no es generación de P5.
                    if str(r.get("class_name")) == CONTROL_CLASS and \
                            abs(float(r["pos_x_m"]) - CONTROL_POS[0]) <= 0.5 and \
                            abs(float(r["pos_z_m"]) - CONTROL_POS[1]) <= 0.5 and \
                            abs(float(r.get("health_hp", 0.0)) - CONTROL_HP) <= 1.0:
                        continue
                    pos = (float(r["pos_x_m"]), float(r["pos_z_m"]))
                    if _coverage_status(pos, union5["disks"]) == "outside":
                        continue
                    total += 1
                if total != 33:
                    fail("F2P-09", f"total={total}")
                else:
                    passing("F2P-09")

    # --- F2P-10 ---
    if not del_rows:
        missing("F2P-10", "no_delete_lines")
    else:
        census_jobs = sorted([j for j in probe["jobs"].values() if j["kind"] == "census"],
                             key=lambda j: float(j.get("snap_tick_ms") or j["start_t"]))
        doc_pos = {str(e["id"]): (float(e["x"]), float(e["z"])) for e in doc1["entities"]}
        kind_of = {str(e["cls"]): str(e["kind"]) for e in doc1["entities"]}
        fails = []
        gaps = []
        max_confirm = _delete_confirm_separation(del_rows)
        for line in del_rows:
            net = f"{int(line.get('net_high', 0))}:{int(line.get('net_low', 0))}"
            t = float(line.get("t_ms") or 0.0)
            nxt = None
            for j in census_jobs:
                if float(j.get("snap_tick_ms") or j["start_t"]) <= t:
                    continue
                if _measurement(j, manifest=manifest, probe=probe,
                                part=str(j.get("part") or ""), judged_t=t) == "":
                    nxt = j
                    break
            if nxt is None:
                gaps.append(f"{net}:no_next_census")
                continue
            union = _census_union(probe, manifest, str(nxt.get("part") or ""), nxt["tag"], judged_t=t)
            if not union["ok"]:
                gaps.append(f"{net}:no_next_census")
                continue
            # Posición: el último censo anterior que tenga la entidad; si no, el documento por `lid`.
            pos = None
            for j in reversed(census_jobs):
                if float(j.get("snap_tick_ms") or j["start_t"]) >= t:
                    continue
                row = next((r for r in j["rows"] if str(r.get("net_id")) == net), None)
                if row is not None:
                    pos = (float(row["pos_x_m"]), float(row["pos_z_m"]))
                    break
            if pos is None:
                pos = doc_pos.get(str(line.get("lid") or ""))
            if pos is None:
                gaps.append(f"{net}:no_position")
                continue
            cov = _coverage_status(pos, union["disks"])
            present = net in union["rows"]
            lid = str(line.get("lid") or "")
            is_creature = lid.startswith(("zmb-", "ani-"))
            if int(line.get("deleted_confirmed_b", 0)) == 1:
                if present:
                    fails.append(f"{net}:confirmed_but_alive")
                elif is_creature:
                    # Una criatura ausente no prueba el borrado: INCONCLUSO.
                    gaps.append(f"{net}:coverage_gap")
                elif cov != "deep":
                    gaps.append(f"{net}:coverage_gap")
            if int(line.get("delete_failed_b", 0)) == 1:
                if not present:
                    if is_creature or cov != "deep":
                        gaps.append(f"{net}:coverage_gap")
                    else:
                        fails.append(f"{net}:failed_but_missing")
        metrics["delete_confirm_max_ms"] = round(max_confirm, 3)
        if fails:
            fail("F2P-10", ";".join(fails[:5]))
        elif gaps:
            missing("F2P-10", ";".join(gaps[:5]))
        else:
            passing("F2P-10")

    # --- F2P-11 (§6.1: edificios reales, net_id firmado y hp=-1) ---
    if not p1:
        missing("F2P-11", "no_baseline_census")
    elif not p1["rows"]:
        fail("F2P-11", "empty_census")
    else:
        surfaces = [float(r.get("surface_y_m")) for r in p1["rows"] if _finite(r.get("surface_y_m"))]
        fails = []
        if len(surfaces) != len(p1["rows"]) or not surfaces:
            fails.append("surface_y_missing")
        elif max(surfaces) - min(surfaces) <= 1e-6:
            fails.append("surface_y_constant")
        if not _baseline_ok(p1["rows"], BUILDINGS):
            fails.append("baseline_missing")
        else:
            for cls, x, z, _yaw in BUILDINGS:
                r = next((r for r in p1["rows"] if str(r.get("class_name")) == cls and
                          abs(float(r["pos_x_m"]) - x) <= 0.5 and
                          abs(float(r["pos_z_m"]) - z) <= 0.5), None)
                if r is None:
                    fails.append(f"{cls}:missing")
                    continue
                net = str(r.get("net_id") or "")
                if not _valid_net(net) or not _NET_ID.match(net):
                    fails.append(f"{cls}:net_invalid")
                    continue
                hi = int(net.split(":")[0])
                if hi >= 0:
                    fails.append(f"{cls}:net_not_signed")
                if not _finite(r.get("health_hp")) or abs(float(r["health_hp"]) + 1.0) > 1e-6:
                    fails.append(f"{cls}:hp")
        if fails:
            fail("F2P-11", ";".join(fails))
        elif wit2 is None:
            # El censo está bien pero el testigo no se puede medir: no se prueba su funcionamiento.
            missing("F2P-11", "witness_unbacked")
        elif not wit2["rows"]:
            fail("F2P-11", "witness_empty")
        else:
            passing("F2P-11")

    # --- F2P-13 (§6.1 punto 7 + criatura por el documento, H-4) ---
    ctl_wit = measured("P1:control", "witness", "P1")
    ctl_known = ctl_wit is not None
    ctl_creatures = 0
    if ctl_wit:
        # H-4: cuenta como criatura la entidad con `ai_agent_b = 1` en alguna muestra de la 0 a la K
        # de su `net_id`; el `ai_agent_b` de la muestra 0 por sí solo no decide.
        ticks = int((manifest.get("f2p") or {}).get("witness_follow_ticks") or 3)
        ctl_nets = set()
        for r in ctl_wit["rows"]:
            if str(r.get("parent_net_id") or "") != "":
                continue
            if not _finite(r.get("sample_idx")) or int(r["sample_idx"]) > ticks:
                continue
            if int(r.get("ai_agent_b", 0)) == 1:
                ctl_nets.add(str(r.get("net_id")))
        ctl_creatures = len(ctl_nets)
    windows = _witness_windows(probe, tap, manifest, "P3")
    if not windows["ok"]:
        missing("F2P-13", "missing_witness_window:" + windows["reason"])
    else:
        wit_ops = []
        for p, s in (("P2", "apply"), ("P2n", "apply"), ("P3", "apply1"), ("P3", "apply2"),
                     ("P4a", "apply1"), ("P4b", "apply"), ("P5", "cut")):
            w = measured(f"{p}:{s}", "witness", p)
            if w:
                wit_ops.append(w)
        if not wit_ops:
            missing("F2P-13", "no_witness_windows")
        else:
            extras_obj = []
            extras_cre = []
            kind_by_cls = {str(e["cls"]): str(e["kind"]) for e in docs}
            for w in wit_ops:
                for r in w["rows"]:
                    if int(r.get("sample_idx", -1)) != 0:
                        continue
                    if str(r.get("parent_net_id") or "") != "":
                        continue
                    if str(r.get("class_name")) not in scene_classes:
                        continue
                    if _find_doc_match(r, docs) is not None:
                        continue
                    tag = f"{w['tag']}:{r.get('class_name')}@{float(r.get('pos_x_m')):.1f},{float(r.get('pos_z_m')):.1f}"
                    if kind_by_cls.get(str(r.get("class_name"))) in ("infectado", "animal"):
                        extras_cre.append(tag)
                    else:
                        extras_obj.append(tag)
            if extras_obj:
                fail("F2P-13", ";".join(extras_obj[:5]))
            elif extras_cre:
                if not ctl_known:
                    missing("F2P-13", "control_window_missing:" + ";".join(extras_cre[:5]))
                elif ctl_creatures == 0:
                    fail("F2P-13", ";".join(extras_cre[:5]))
                else:
                    # §6 (v1.3.6, errata de la v1.3.4): con criaturas en la ventana de control, una
                    # criatura de más no se puede atribuir a F2: INCONCLUSO, nunca PASA ni FALLA.
                    missing("F2P-13", "control_had_creatures:" + ";".join(extras_cre[:5]))
            else:
                passing("F2P-13")

    # La traza rota es una comprobación de fabricación: tumba la comprobación de la parte de cada op.
    for violation in trace_bad:
        for cid in TRACE_PART_CHECKS.get(violation.get("part") or "", ()):
            fail(cid, "tap_trace_mismatch")

    checks_list = _checks_as_list(checks)
    failed = [c["id"] for c in checks_list if c["status"] == "fail"]
    if failed:
        out = list(failed)
        for r in reasons:
            if r not in out:
                out.append(r)
        return gate_core.make_verdict(SPIKE_ID, 1, checks=checks_list, metrics=metrics, reasons=out)
    if any(c["status"] != "pass" for c in checks_list) or reasons:
        out = list(reasons)
        for c in checks_list:
            if c["status"] != "pass":
                if c["detail"] not in out:
                    out.append(c["detail"])
                if c["id"] not in out:
                    out.append(c["id"])
        return gate_core.make_verdict(SPIKE_ID, 2, checks=checks_list, metrics=metrics, reasons=out)
    return gate_core.make_verdict(SPIKE_ID, 0, checks=checks_list, metrics=metrics, reasons=[])


# ---------------------------------------------------------------------------------------------------
# Auxiliares de tiempo de los efectos juzgados
# ---------------------------------------------------------------------------------------------------

def _first_apply_op(tap: dict[str, Any], manifest: dict[str, Any], part: str,
                    index: int = 0) -> dict[str, Any] | None:
    ops = _tap_op(tap, "scene.apply", part, manifest)
    return ops[index] if len(ops) > index else None


def _terminal_t(tap: dict[str, Any], backend: dict[str, Any], op_id: str) -> float | None:
    st = _terminal_state(backend, op_id)
    return float(st["t_ms"]) if st is not None else None


def _p2_terminal_t(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any]) -> float | None:
    d = _first_apply_op(tap, manifest, "P2")
    if d is None:
        return None
    return _terminal_t(tap, backend, d["op_id"])


def _p3_terminal_t(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                   which: str) -> float | None:
    part = "P3" if which in ("reset1", "reset2") else "P3c"
    ops = _tap_op(tap, "scene.reset", part, manifest)
    if which == "reset1":
        d = ops[0] if ops else None
    elif which == "reset2":
        d = ops[1] if len(ops) > 1 else None
    else:
        d = ops[0] if ops else None
    return _terminal_t(tap, backend, d["op_id"]) if d else None


def _p4a_terminal_t(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any]) -> float | None:
    ops = _tap_op(tap, "scene.apply", "P4a", manifest)
    if len(ops) < 2:
        return None
    return _terminal_t(tap, backend, ops[1]["op_id"])


def _p5_cut_t(tap: dict[str, Any], manifest: dict[str, Any]) -> float:
    ops = _tap_op(tap, "scene.apply", "P5", manifest)
    return float(ops[0]["t_ms"]) if ops else 0.0


def _apply_terminal_t(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                      part: str, index: int) -> float | None:
    ops = _tap_op(tap, "scene.apply", part, manifest)
    if len(ops) <= index:
        return None
    return _terminal_t(tap, backend, ops[index]["op_id"])


def _part_restart_t(backend: dict[str, Any], manifest: dict[str, Any],
                    part: str) -> float | None:
    win = _part_window(manifest, part)
    if win is None:
        return None
    ts = [r["t_ms"] for r in backend["restarts"]
          if str(r["data"].get("target") or "") == "server" and
          float(win["start_t_ms"]) <= r["t_ms"] <= float(win["end_t_ms"])]
    return min(ts) if ts else None


def _part_restarts(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                   part: str) -> list[dict[str, Any]]:
    win = _part_window(manifest, part)
    if win is None:
        return []
    out = []
    for rs in backend["restarts"]:
        if str(rs["data"].get("target") or "") == "backend" and \
                float(win["start_t_ms"]) <= rs["t_ms"] <= float(win["end_t_ms"]):
            out.append(rs)
    return out


def _check_creatures(manifest: dict[str, Any], tap: dict[str, Any], backend: dict[str, Any],
                     wit2: dict[str, Any], union2: dict[str, Any], doc1: dict[str, Any],
                     doc_counter: Counter, cre_fail: list[str], cre_missing: list[str]) -> None:
    ticks = int((manifest.get("f2p") or {}).get("witness_follow_ticks") or 3)
    ck = None
    for d in _tap_op(tap, "scene.apply", "P2", manifest):
        for r in _results_for(tap, d["op_id"]):
            read = r.get("read") or {}
            if isinstance(read.get("checkpoint"), list):
                ck = {str(row[0]): row for row in read["checkpoint"]
                      if isinstance(row, list) and len(row) >= 7}
                break
        if ck is not None:
            break
    for e in doc1["entities"]:
        if e["kind"] not in ("infectado", "animal"):
            continue
        w = next((r for r in wit2["rows"] if int(r.get("sample_idx", -1)) == 0 and
                  str(r.get("class_name")) == str(e["cls"]) and
                  abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and
                  abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M), None)
        if w is None:
            cre_fail.append(f"{e['id']}:no_eeinit")
            continue
        net = str(w.get("net_id"))
        traj = sorted([r for r in wit2["rows"] if str(r.get("net_id")) == net and
                       int(r.get("sample_idx", -1)) >= 1], key=lambda r: int(r["sample_idx"]))
        idxs = [int(r["sample_idx"]) for r in traj]
        if idxs != list(range(1, ticks + 1)):
            cre_missing.append(f"{e['id']}:no_trajectory")
            continue
        # Las muestras 1..K son los K ticks siguientes: los frames tienen que ser consecutivos. Un tick 1
        # retrasado 33 s (aunque la posición no cambie) no es la trayectoria declarada (§5.3, Q-01).
        f0 = w.get("frame")
        if not _finite(f0):
            cre_fail.append(f"{e['id']}:frame_missing")
        else:
            for r in traj:
                fr = r.get("frame")
                if not _finite(fr) or int(fr) != int(float(f0)) + int(r["sample_idx"]):
                    cre_fail.append(f"{e['id']}:trajectory_not_consecutive")
                    break
        jump = _dist2(w, traj[0])
        if jump > JUMP_MAX_M:
            cre_fail.append(f"{e['id']}:jump={jump:.3f}")
        if ck is None or e["id"] not in ck:
            cre_missing.append(f"{e['id']}:no_checkpoint")
            continue
        row = ck[e["id"]]
        cx, cy, cz = float(row[2]) / 1000.0, float(row[3]) / 1000.0, float(row[4]) / 1000.0
        if math.sqrt((cx - float(traj[0]["pos_x_m"])) ** 2 + (cy - float(traj[0]["pos_y_m"])) ** 2 +
                     (cz - float(traj[0]["pos_z_m"])) ** 2) > JUMP_MAX_M:
            cre_fail.append(f"{e['id']}:checkpoint_far")
        c = union2["rows"].get(net)
        if c is None:
            pos = (float(w["pos_x_m"]), float(w["pos_z_m"]))
            cov = _coverage_status(pos, union2["disks"])
            if cov == "outside":
                cre_missing.append(f"{e['id']}:coverage_gap")
            else:
                cre_missing.append(f"{e['id']}:coverage_gap")
        elif int(c.get("alive_b", 0)) != 1 or int(c.get("ai_agent_b", 0)) != 1:
            cre_fail.append(f"{e['id']}:alive_or_ai")


def aggregate_parts(part_dirs: list[Path], *, repo_root: Path | None = None) -> dict[str, Any]:
    """Agrega varias campañas (p. ej. diag y retail). Solo PASA si todas PASA."""
    members = []
    codes = []
    for p in part_dirs:
        v = evaluate(Path(p), repo_root=repo_root)
        members.append({"id": str(Path(p).name), "exit_code": int(v.get("exit_code", 2)),
                        "verdict": v.get("verdict"), "reasons": list(v.get("reasons") or [])})
        codes.append(int(v.get("exit_code", 2)))
    code = gate_core.aggregate(codes)
    reasons = []
    if code == 1:
        reasons = [m["id"] for m in members if m["exit_code"] == 1]
    elif code == 2:
        reasons = [m["id"] for m in members if m["exit_code"] != 0]
    return gate_core.make_verdict(SPIKE_ID, code, checks=[], metrics={}, reasons=reasons, members=members)
