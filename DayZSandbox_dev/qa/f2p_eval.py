"""Oráculo E9 de la partida de F2 (F2P-01..F2P-13), semántica v1.3.9 (§6.1).

Decide solo con lecturas independientes: las respuestas crudas de la sonda (censo y testigo), la
traza del proxy del producto, los eventos del backend, las líneas DSBX_SCENE_DEL del mod y los
campos permitidos del manifest. El contrato está en `qa/f2p_evidence_contract.md`.

La base común (§6.1 puntos 1 a 10) está en `_measurement`, `_terminal_state`, `_generation`,
`_census_union`, `_trace_violations`, `_reconciliation_ok`, `_witness_windows`, `_server_restart_ok`
y `_oracle_check_ok`. Todas las comprobaciones consumen esas funciones.

Reloj (R-03): los `t_ms` solo se comparan con `t_ms`; los ticks del motor (`snap_tick_ms`,
`start_tick_ms` y `tick_ms`) solo se comparan con ticks del mismo epoch.

Identidad (enmienda del brief:1296-1313, 2026-11-23): la sonda y el producto se casan por la vida
del servidor (`_server_lives`, `_job_life_problem` y `_job_epoch`), no por igualdad de ids.

Códigos de salida: 0 PASA, 1 FALLA, 2 INCONCLUSO (`gate_core.py:73-82`).
"""

from __future__ import annotations

import copy
import hashlib
import itertools
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

WITNESS_STAGES = {
    "P1": ("control",),
    "P2": ("apply",),
    "P2n": ("apply",),
    "P3": ("apply1", "apply2"),
    "P4a": ("apply1", "apply2"),
    "P4b": ("apply",),
    "P5": ("cut", "apply2"),
}

TERMINAL_STATES = frozenset({"observado", "parcial", "fallido"})
# §6.1 punto 2 (v1.3.8): solo son terminales los del backend. `parcial/sin_resultado` no lo es.
TERMINAL_PARCIAL_REASONS = frozenset({
    "contenido_ajeno", "compensada", "interrumpida", "superada", "mundo_reiniciado",
})
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
MAIN_CENSUS_RADIUS_M = 115.0
COVERAGE_EDGE_M = 15.0

EPS_OBJ_M = 0.5
JUMP_MAX_M = 0.3
# §6.1 F2P-02 y V-10 (v1.3.10): criaturas a 0,1 m y objetos a 2,0 m (el origen de algunos
# `Land_Wreck_*` no está en el suelo).
SUPPORT_TOL_CRIATURA_M = 0.1
SUPPORT_TOL_OBJETO_M = 2.0
WITNESS_CENSUS_TOL_M = 0.05
# §5.3 (v1.3.10): el control persistente es `Barrel_Yellow` con un `Fireplace` en el cargo y
# `health_mark_ratio` 0,845, en (4860, 10200), fuera de la zona de F2.
CONTROL_CLASS = "Barrel_Yellow"
CONTROL_POS = (4860.0, 10200.0)
CONTROL_RATIO = 0.845
CONTROL_CENSUS_RADIUS_M = 30.0
# §6.1 punto 4 y R-04 (v1.3.10): `V_MAX` por tipo.
V_MAX_INFECTADO = 7.0
V_MAX_ANIMAL = 12.0

_HEX40 = re.compile(r"^[0-9a-fA-F]{40}$")
_HEX16 = re.compile(r"^[0-9a-fA-F]{16}$")
_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")
_NET_ID = re.compile(r"^-?\d+:-?\d+$")
_RD_ID = re.compile(r"^rd-\d+$")
_LID = re.compile(r"^(obj|zmb|ani)-(0[1-9]|[1-9][0-9]+)$")
_DOC_ID = re.compile(r"^d-[0-9a-f]{8}$")

OUTCOMES = frozenset({"done", "retained", "compensated", "interrupted"})


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


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


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
    # v1.3.11 (A-01): el evento `result` del bridge no lleva `inst`. La instancia de una respuesta es
    # la que el bridge tenía aceptada para ese peer al recibirla: el último `hello` aceptado de ese
    # peer antes del `result` en el reloj común.
    accepted_hellos: list[dict[str, Any]] = []
    for idx, ev in enumerate(events):
        if ev.get("ev") != "hello" or ev.get("http") != 200 or ev.get("ok") is False:
            continue
        t = ev.get("t_ms")
        if not _finite(t):
            t = float(idx)
        accepted_hellos.append({"peer": str(ev.get("peer") or ""),
                                "inst": str(ev.get("inst") or ""), "t_ms": float(t)})

    def accepted_inst_at(peer: str, t_ms: float) -> str:
        best = None
        for h in accepted_hellos:
            if h["peer"] != peer or not h["inst"]:
                continue
            if h["t_ms"] < t_ms and (best is None or h["t_ms"] > best["t_ms"]):
                best = h
        return str(best["inst"]) if best is not None else ""

    ops: dict[str, dict[str, Any]] = {}
    hellos: list[dict[str, Any]] = []
    polls: list[dict[str, Any]] = []
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
        elif kind == "poll":
            polls.append({"t_ms": float(t), "inst": str(ev.get("inst") or ""),
                          "tick_s": (float(ev["tick_s"]) if _finite(ev.get("tick_s")) else None)})
        elif kind == "enq":
            oid = str(ev.get("op_id") or "")
            if oid and oid not in ops:
                ops[oid] = {"op_id": oid, "verb": str(ev.get("verb") or ""), "args": ev.get("args"),
                            "peer": str(ev.get("peer") or ""), "inst": str(ev.get("inst") or ""),
                            "inst_enq": str(ev.get("inst") or ""), "inst_deliver": "",
                            "t_enq": float(t), "t_deliver": None, "status": None, "reason": "",
                            "read": {}, "t_result": None, "inst_result": ""}
        elif kind == "deliver":
            oid = str(ev.get("op_id") or "")
            op = ops.get(oid)
            if op is not None and op.get("t_deliver") is None:
                op["t_deliver"] = float(t)
                op["inst_deliver"] = str(ev.get("inst") or "")
        elif kind == "result" and ev.get("http") == 200:
            res = ev.get("result") if isinstance(ev.get("result"), dict) else {}
            oid = str(res.get("op_id") or ev.get("op_id") or "")
            if not oid:
                continue
            peer = str(ev.get("peer") or "")
            inst_result = accepted_inst_at(peer, float(t))
            op = ops.setdefault(oid, {"op_id": oid, "verb": str(res.get("verb") or ""),
                                      "args": None, "peer": peer,
                                      "inst": inst_result, "inst_enq": "",
                                      "inst_deliver": "",
                                      "t_enq": float(t),
                                      "t_deliver": None, "status": None, "reason": "",
                                      "read": {}, "t_result": None, "inst_result": ""})
            op["status"] = str(res.get("status") or "")
            op["reason"] = str(res.get("reason") or "")
            op["read"] = res.get("read") if isinstance(res.get("read"), dict) else {}
            op["t_result"] = float(t)
            op["inst_result"] = inst_result

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
            insts = (op.get("inst_enq"), op.get("inst_deliver"), op.get("inst_result"))
            if not all(insts) or len(set(insts)) != 1:
                bad_jobs.add(jid)
            tag = str(s.get("area_tag") if op["verb"] == "per_census_start" else s.get("witness_tag"))
            jobs[jid] = {
                "job": jid, "kind": "census" if op["verb"] == "per_census_start" else "witness",
                "tag": tag, "part": tag.split(":")[0] if ":" in tag else tag,
                "stage": tag.split(":", 1)[1] if ":" in tag else "",
                "epoch": str(s.get("server_epoch") or ""), "inst": str(op.get("inst") or ""),
                "args": op.get("args"), "deliver_t": op.get("t_deliver"), "free_t": None,
                "start_t": op["t_result"],
                "rows_captured_n": (float(n["rows_captured_n"])
                                    if _finite(n.get("rows_captured_n")) else None),
                "center_x": float(n.get("center_x_m", 0.0)), "center_z": float(n.get("center_z_m", 0.0)),
                "radius": float(n.get("radius_m", 0.0)), "window_ms": float(n.get("window_ms", 0.0)),
                "snap_tick_ms": float(n["snap_tick_ms"]) if _finite(n.get("snap_tick_ms")) else None,
                "snap_frame": float(n["snap_frame"]) if _finite(n.get("snap_frame")) else None,
                "start_tick_ms": float(n["start_tick_ms"]) if _finite(n.get("start_tick_ms")) else None,
                "pages": {}, "rows": [], "pages_n": None, "rows_total": None, "valid": False,
                "min_page_t": None, "max_page_t": None,
            }
    for op in ops.values():
        if op["verb"] == "job_free" and op["status"] == "done":
            au = _unpack(op["args"]) if op["args"] is not None else None
            if au:
                jid = str(au[0].get("job") or "")
                if jid in jobs and jobs[jid].get("free_t") is None:
                    jobs[jid]["free_t"] = op["t_result"]
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
        insts = (op.get("inst_enq"), op.get("inst_deliver"), op.get("inst_result"))
        if not all(insts) or len(set(insts)) != 1 or insts[0] != job.get("inst"):
            bad_jobs.add(jid)
            continue
        a_pn = a_n.get("page_n")
        r_pn = r_n.get("page_n")
        if not _finite(a_pn) or not _finite(r_pn) or int(a_pn) != int(r_pn):
            bad_jobs.add(jid)
            continue
        # v1.3.11 (F-01): las páginas nativas no llevan `server_epoch`. Si una fixture lo trae, se
        # valida contra el epoch del arranque; ausente es lo normal, presente y vacío es inválido.
        page_epoch = str(r_s.get("server_epoch") or "")
        if "server_epoch" in r_s and (not page_epoch or page_epoch != job["epoch"]):
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
    return {"ops": ops, "hellos": hellos, "jobs": jobs, "polls": polls}


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
             if j["kind"] == "witness" and j.get("deliver_t") is not None and
             win[0] <= float(j["deliver_t"]) <= win[1]],
            key=lambda j: float(j["deliver_t"]),
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
    """Empareja cada respuesta con la peticion de su mismo `req_id` (v1.3.14, §6.1 punto 5).

    No hay emparejamiento por orden, antiguedad ni contenido. Un registro sin `req_id`, una respuesta
    cuyo `req_id` no tiene peticion y dos peticiones o dos respuestas con el mismo `req_id` se
    anotan en `req_id_problems`; el check de su parte da INCONCLUSO (`tap_req_id_missing`).
    """
    hellos: list[dict[str, Any]] = []
    deliveries: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    acks: list[dict[str, Any]] = []
    polls: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    hello_by_id: dict[int, dict[str, Any]] = {}
    poll_by_id: dict[int, dict[str, Any]] = {}
    result_by_id: dict[int, dict[str, Any]] = {}
    req_at: dict[int, dict[str, Any]] = {}
    pairs: list[dict[str, Any]] = []
    seen_req_ids: set[int] = set()

    def _rid(ev: dict[str, Any], t: float, path: str) -> int | None:
        rid = ev.get("req_id")
        if not _is_int(rid):
            problems.append({"t_ms": t, "reason": f"tap_req_id_missing:{path}"})
            return None
        if rid in seen_req_ids:
            problems.append({"t_ms": t, "reason": f"tap_req_id_duplicate:{path}"})
            return None
        seen_req_ids.add(rid)
        return int(rid)

    for ev in events:
        t = ev.get("t_ms")
        if not _finite(t):
            continue
        t = float(t)
        path = str(ev.get("path") or "")
        if ev.get("dir") != "req":
            continue
        rid = _rid(ev, t, path)
        if rid is not None:
            req_at[rid] = {"t_ms": t, "path": path}
        if path == "/hello" and isinstance(ev.get("body"), dict):
            b = ev["body"]
            rec = {"t_ms": t, "inst": str(b.get("inst") or ""),
                   "epoch": str(b.get("epoch") or ""), "peer": str(b.get("peer") or ""),
                   "build": str(b.get("build") or ""), "session": "", "accepted": False,
                   "resp_t": None, "world_size": b.get("world_size"), "conn": "",
                   "req_id": rid}
            hellos.append(rec)
            if rid is not None:
                hello_by_id[rid] = rec
        elif path == "/poll":
            q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
            rec = {"t_ms": t, "peer": str(q.get("peer") or ""),
                   "inst": str(q.get("inst") or ""), "session": str(q.get("session") or ""),
                   "conn": str(q.get("conn")), "resp_t": None, "http": None, "ops": [],
                   "req_id": rid}
            polls.append(rec)
            if rid is not None:
                poll_by_id[rid] = rec
        elif path == "/result" and isinstance(ev.get("body"), dict):
            b = ev["body"]
            q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
            rec = {"t_ms": t, "op_id": str(b.get("op_id") or ""),
                   "session": str(b.get("session") or ""), "epoch": str(b.get("epoch") or ""),
                   "query_session": str(q.get("session") or ""),
                   "peer": str(q.get("peer") or ""), "inst": str(q.get("inst") or ""),
                   "status": str(b.get("status") or ""), "reason": str(b.get("reason") or ""),
                   "dup": bool(b.get("dup")), "read": b.get("read") if isinstance(b.get("read"), dict) else {},
                   "ack_t": None, "req_id": rid}
            results.append(rec)
            if rid is not None:
                result_by_id[rid] = rec

    seen_resp_ids: set[int] = set()
    for ev in events:
        t = ev.get("t_ms")
        if not _finite(t):
            continue
        t = float(t)
        path = str(ev.get("path") or "")
        if ev.get("dir") != "resp":
            continue
        rid = ev.get("req_id")
        if not _is_int(rid):
            problems.append({"t_ms": t, "reason": f"tap_req_id_missing:{path}"})
            continue
        rid = int(rid)
        if rid in seen_resp_ids:
            problems.append({"t_ms": t, "reason": f"tap_req_id_duplicate:{path}"})
            continue
        seen_resp_ids.add(rid)
        b = ev.get("body")
        if rid in req_at:
            # v1.3.15 (T2f-15h, K-08): todas las parejas peticion-respuesta del tap por `req_id`,
            # de cualquier path, tambien `/catalog` y los que no conozca. De cada una, la hora de
            # la peticion y la de la respuesta.
            # v1.3.16 (§5.4): `upstream_status` dice quien contesto; ausente cuenta como backend.
            pairs.append({"t_ms": req_at[rid]["t_ms"], "resp_t": t,
                          "path": req_at[rid]["path"], "req_id": rid,
                          "http": ev.get("http"),
                          "upstream_present": "upstream_status" in ev,
                          "upstream_status": ev.get("upstream_status"),
                          "body": b if isinstance(b, dict) else {}})
        if path == "/hello":
            rec = hello_by_id.get(rid)
            if rec is None:
                problems.append({"t_ms": t, "reason": f"tap_req_id_orphan:{path}"})
                continue
            bb = b if isinstance(b, dict) else {}
            accepted = ev.get("http") == 200 and bb.get("ok") is True and \
                bool(str(bb.get("session") or ""))
            rec["accepted"] = accepted
            rec["resp_t"] = t
            rec["session"] = str(bb.get("session") or "") if accepted else ""
            rec["conn"] = str(bb.get("conn") or "") if accepted else ""
        elif path == "/poll":
            rec = poll_by_id.get(rid)
            if rec is None:
                problems.append({"t_ms": t, "reason": f"tap_req_id_orphan:{path}"})
                continue
            bb = b if isinstance(b, dict) else {}
            rec["resp_t"] = t
            rec["http"] = ev.get("http")
            rec["ops"] = [o for o in bb.get("ops") or [] if isinstance(o, dict)]
            for o in rec["ops"]:
                deliveries.append({"t_ms": t, "op_id": str(o.get("op_id") or ""),
                                   "session": str(o.get("session") or ""),
                                   "peer": str(rec.get("peer") or ""),
                                   "conn": str(o.get("conn")), "epoch": str(o.get("epoch") or ""),
                                   "inst": str(o.get("inst") or ""), "verb": str(o.get("verb") or ""),
                                   "poll_t_ms": float(rec.get("t_ms") or 0.0),
                                   "poll_peer": str(rec.get("peer") or ""),
                                   "poll_inst": str(rec.get("inst") or ""),
                                   "poll_conn": str(rec.get("conn")),
                                   "poll_session": str(rec.get("session") or ""),
                                   "args": o.get("args") if isinstance(o.get("args"), dict) else {}})
        elif path == "/result":
            rec = result_by_id.get(rid)
            if rec is None:
                problems.append({"t_ms": t, "reason": f"tap_req_id_orphan:{path}"})
                continue
            ok = (b.get("ok") is True) if isinstance(b, dict) else False
            rec["ack_t"] = t
            rec["ack_ok"] = ok
            rec["ack_http"] = ev.get("http")
            rec["ack_upstream_present"] = "upstream_status" in ev
            rec["ack_upstream"] = ev.get("upstream_status")
            rec["ack_body"] = b
            acks.append({"t_ms": t, "ok": ok, "http": ev.get("http"), "req_id": rid})

    return {"hellos": hellos, "deliveries": deliveries, "results": results, "acks": acks,
            "polls": polls, "req_id_problems": problems, "pairs": pairs}

def _parse_backend(events: list[dict[str, Any]]) -> dict[str, Any]:
    op_states: list[dict[str, Any]] = []
    restarts: list[dict[str, Any]] = []
    frozen: list[dict[str, Any]] = []
    pbo: list[dict[str, Any]] = []
    api_obs: list[dict[str, Any]] = []
    api_ops: list[dict[str, Any]] = []
    cuts: list[dict[str, Any]] = []
    for ev in events:
        kind = ev.get("kind")
        t = ev.get("t_ms")
        data = ev.get("data") if isinstance(ev.get("data"), dict) else {}
        if kind == "op.state":
            op_states.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "restart":
            restarts.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "cut":
            cuts.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "oracle.frozen":
            frozen.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "pbo.stamp":
            pbo.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "api.observation":
            api_obs.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
        elif kind == "api.ops":
            api_ops.append({"t_ms": float(t) if _finite(t) else 0.0, "data": data})
    return {"op_states": op_states, "restarts": restarts, "frozen": frozen, "pbo": pbo,
            "api_obs": api_obs, "api_ops": api_ops, "cuts": cuts}


# ---------------------------------------------------------------------------------------------------
# Base común (§6.1 puntos 1 a 10)
# ---------------------------------------------------------------------------------------------------

def _part_window(manifest: dict[str, Any], part: str) -> dict[str, Any] | None:
    f2p = manifest.get("f2p") if isinstance(manifest.get("f2p"), dict) else {}
    for p in f2p.get("parts") or []:
        if isinstance(p, dict) and p.get("name") == part:
            return p
    return None


def _part_for_time(manifest: dict[str, Any], t_ms: float) -> str:
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
            not _HEX64.match(str(ident.get("pbo_sha256") or "")) or \
            not _HEX64.match(str(ident.get("product_pbo_sha256") or "")):
        reasons.append("manifest_incomplete")
    if build in ("diag", "retail") and ident.get("git_dirty") is not False:
        reasons.append("manifest_incomplete")
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
                    ("server_epoch" in p and
                     not _HEX32.match(str(p.get("server_epoch") or ""))) or \
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


def _oracle_check_ok(part_dir: Path, manifest: dict[str, Any],
                     backend: dict[str, Any]) -> str:
    """R-14: el commit verificado por el gate tiene que ser el cuarto vínculo.

    Lee `part_dir/../oracle_check.json` (lo escribe el núcleo antes de evaluar). Sin él, INCONCLUSO
    `oracle_unverified`. Exige `ok: true` y que su `commit` sea el mismo que los tres del manifest.
    """
    path = part_dir.parent / "oracle_check.json"
    if not path.is_file():
        return "oracle_unverified"
    try:
        check = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "oracle_unverified"
    if not isinstance(check, dict) or check.get("ok") is not True:
        return "oracle_unverified"
    commit = str(check.get("commit") or "")
    ident = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    f2p = manifest.get("f2p") if isinstance(manifest.get("f2p"), dict) else {}
    frozen_commit = ""
    if backend.get("frozen"):
        frozen_commit = str(backend["frozen"][-1]["data"].get("commit") or "")
    if not _HEX40.match(commit) or commit != str(ident.get("oracle_commit") or "") or \
            commit != str(f2p.get("oracle_commit") or "") or commit != frozen_commit:
        return "oracle_unverified"
    return ""


def _hello_stamp_ok(probe: dict[str, Any], inst: str, expected_pv: str) -> bool:
    return any(h["peer"] == "server" and h["inst"] == inst and h["probe_ver"] == expected_pv
               for h in probe["hellos"])


def _hello_before(probe: dict[str, Any], inst: str, expected_pv: str, t_ms: float) -> bool:
    return any(h["peer"] == "server" and h["inst"] == inst and h["probe_ver"] == expected_pv and
               h["t_ms"] < t_ms for h in probe["hellos"])


def _hello_resp_time(h: dict[str, Any]) -> float | None:
    """v1.3.13 (T2f-12, §6.1 punto 2 línea 484 y punto 5 línea 558): un `/hello` existe para el
    backend cuando lo ACEPTA, no cuando se pide. Su hora es la de su respuesta (`resp_t`)."""
    rt = h.get("resp_t")
    return float(rt) if _finite(rt) else None


def _anchor_eq(a: Any, b: Any) -> bool:
    """v1.3.14 (§6.1 punto 5): una `inst` o un `epoch` vacios no casan con nada."""
    sa = str(a or "")
    sb = str(b or "")
    return bool(sa) and bool(sb) and sa == sb


def _tap_epoch_for_inst(tap: dict[str, Any], inst: str, t_ms: float) -> str:
    """Epoch de la instancia del servidor en vigor antes de `t_ms` (punto 8: epoch por evento).

    v1.3.13 (B-04): solo cuentan los `/hello` aceptados (brief:546).
    v1.3.13 (T2f-12): la hora es la de la respuesta (brief:484, 558).
    """
    best = None
    best_t = None
    for h in tap.get("hellos") or []:
        if h.get("peer") != "server" or h.get("inst") != inst or not h.get("accepted"):
            continue
        rt = _hello_resp_time(h)
        if rt is None or not (rt < t_ms):
            continue
        if best is None or rt > best_t:
            best = h
            best_t = rt
    return str(best["epoch"]) if best is not None else ""


def _epoch_at(tap: dict[str, Any], t_ms: float) -> str:
    """Epoch vigente en el reloj común (último `/hello` de servidor ACEPTADO anterior a `t_ms`).

    v1.3.13 (T2f-11, C-02/C-04/C-08): un `/hello` rechazado no abre sesión (brief:546); su epoch no
    es el vigente (brief:567).
    """
    best = None
    best_t = None
    for h in tap.get("hellos") or []:
        if h.get("peer") != "server" or not h.get("accepted"):
            continue
        rt = _hello_resp_time(h)
        if rt is None or not (rt < t_ms):
            continue
        if best is None or rt > best_t:
            best = h
            best_t = rt
    return str(best["epoch"]) if best is not None else ""


def _server_hello_at(tap: dict[str, Any], t_ms: float) -> dict[str, Any] | None:
    """Último `/hello` de servidor ACEPTADO anterior a `t_ms` (instancia y epoch del mismo evento).

    v1.3.13 (T2f-11, C-04): la instancia y el epoch vigentes salen del MISMO `/hello` aceptado
    (brief:546, 660, 662).
    """
    best = None
    best_t = None
    for h in tap.get("hellos") or []:
        if str(h.get("peer") or "") != "server" or not h.get("accepted"):
            continue
        rt = _hello_resp_time(h)
        if rt is None or not (rt < t_ms):
            continue
        if best is None or rt > best_t:
            best = h
            best_t = rt
    return best


def _server_inst_at(tap: dict[str, Any], t_ms: float) -> str:
    """Instancia del servidor vigente en el reloj común (último `/hello` aceptado).

    v1.3.13 (B-04): un `/hello` rechazado no abre sesión (brief:546).
    """
    best = _server_hello_at(tap, t_ms)
    return str(best["inst"]) if best is not None else ""


def _session_opened_before(tap: dict[str, Any], backend: dict[str, Any], session: str,
                           t_ms: float, inst: str) -> bool:
    """v1.3.13 (T2f-11, C-01; brief:484, 546, 550, 558): la sesión de una entrega o de un resultado
    del servidor la abre un `/hello` aceptado DEL SERVIDOR, con respuesta anterior y dentro del tramo
    de `session_at(t_ms)`. Un `/hello` de cliente o de otro tramo no la abre.
    v1.3.13 (T2f-12, D-03; brief:546, 558 y 334): además tiene que ser el `/hello` de la MISMA
    instancia que la entrega o el resultado; el backend real solo atiende a su instancia registrada
    (bridge.py:495-496) y sella cada entrega con ella (:536-537).
    """
    seg = next((s for s in _backend_session_segments(tap, backend)
                if float(s["lo"]) <= float(t_ms) < float(s["hi"])), None)
    if seg is None:
        return False
    lo, hi = float(seg["lo"]), float(seg["hi"])
    for h in tap.get("hellos") or []:
        if not h.get("accepted") or str(h.get("peer") or "") != "server":
            continue
        if str(h.get("session") or "") != session:
            continue
        if not _anchor_eq(str(h.get("inst") or ""), str(inst or "")):
            continue
        rt = h.get("resp_t")
        if rt is None or not _finite(rt):
            continue
        rt = float(rt)
        if rt < float(t_ms) and lo <= rt < hi:
            return True
    return False


def _backend_session_segments(tap: dict[str, Any], backend: dict[str, Any]) -> list[dict[str, Any]]:
    """Tramos de sesión del backend entre reinicios (§6.1 punto 2, v1.3.9).

    Cada tramo lleva todas las respuestas a `/hello` que caen dentro de él. La sesión de un tramo
    tiene que ser única: todas las respuestas a `/hello` de un tramo dan la misma sesión (v1.3.10), y
    ninguna sesión se repite entre tramos; si no, la traza se rompe.
    v1.3.13 (T2f-11, C-01): cuentan los `/hello` de CUALQUIER peer (brief:484, 550). Una respuesta
    huérfana sin petición cuenta por su `resp_t` (C-05).
    """
    boundaries = sorted(float(r["t_ms"]) for r in backend.get("restarts") or []
                        if str((r.get("data") or {}).get("target") or "") == "backend")
    hellos: list[tuple[float, str]] = []
    for h in tap.get("hellos") or []:
        s = str(h.get("session") or "")
        if not s:
            continue
        t = _hello_resp_time(h)
        if t is None:
            continue
        hellos.append((t, s))
    segments: list[dict[str, Any]] = []
    edges = [float("-inf")] + boundaries + [float("inf")]
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        cands = [(t, s) for t, s in hellos if lo <= t < hi]
        sessions = sorted({s for _t, s in cands})
        segments.append({"lo": lo, "hi": hi, "hellos": cands, "sessions": sessions,
                         "first_session": cands[0][1] if cands else ""})
    return segments


def _backend_session_problems(tap: dict[str, Any],
                              backend: dict[str, Any]) -> list[dict[str, Any]]:
    """v1.3.10: una sesión por tramo y sin repetir sesiones entre tramos.

    Devuelve una lista de violaciones con su `t_ms` (el del primer `/hello` del tramo que las
    produce) para que la traza las atribuya a la parte correspondiente.
    """
    out: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for idx, seg in enumerate(_backend_session_segments(tap, backend)):
        if len(seg["sessions"]) > 1:
            # La violación se atribuye al `/hello` que introduce la segunda sesión, no al primero
            # del tramo: es el evento que rompe la traza en su parte.
            first = seg["first_session"]
            bad_t = next((t for t, s in seg["hellos"] if s != first), seg["hellos"][0][0])
            out.append({"t_ms": float(bad_t),
                        "reason": f"two_sessions_one_segment:{seg['sessions'][0]}/{seg['sessions'][1]}"})
        for s in seg["sessions"]:
            if s in seen and seen[s] != idx:
                out.append({"t_ms": float(seg["hellos"][0][0]),
                            "reason": f"session_repeats_between_segments:{s}"})
            seen[s] = idx
    return out


def _backend_sessions(tap: dict[str, Any], backend: dict[str, Any]):
    """v1.3.9: la sesión de un `op.state` es la del tramo entre reinicios del backend.

    Los `restart` con `target: "backend"` parten los tramos; la sesión de cada tramo es la de las
    respuestas a `/hello` de ese tramo (§6.1 punto 2). Devuelve `session_at(t_ms)`. La unicidad de la
    sesión por tramo la comprueba `_backend_session_problems` (v1.3.10).
    """
    segments = _backend_session_segments(tap, backend)

    def session_at(t_ms: float) -> str:
        for seg in segments:
            if seg["lo"] <= float(t_ms) < seg["hi"]:
                return seg["first_session"]
        return ""

    return session_at


def _assign_op_sessions(tap: dict[str, Any], backend: dict[str, Any]) -> None:
    session_at = _backend_sessions(tap, backend)
    for st in backend.get("op_states") or []:
        st["session"] = session_at(float(st.get("t_ms") or 0.0))


def _ttl_ms(manifest: dict[str, Any]) -> float | None:
    """V-16: la retención de F2P-04 sale de `params.ttl_ms` (o de `identity.params.ttl_ms`).

    Si falta, la comprobación da INCONCLUSO; nunca «sin comprobar».
    """
    candidates = [manifest.get("params")]
    ident = manifest.get("identity")
    if isinstance(ident, dict):
        candidates.append(ident.get("params"))
    for src in candidates:
        if isinstance(src, dict) and _finite(src.get("ttl_ms")):
            return float(src["ttl_ms"])
    return None


def _world_size(tap: dict[str, Any], t_ms: float) -> int:
    """Tamaño del mundo del servidor vigente antes de `t_ms` (§6.1 punto 6, brief:566).

    v1.3.13 (T2f-11, C-06): solo cuentan los `/hello` de servidor aceptados (brief:546) y el vigente
    antes de la lectura; un `/hello` rechazado posterior no agranda el mundo.
    """
    best = None
    best_t = None
    for h in tap.get("hellos") or []:
        if h.get("peer") != "server" or not h.get("accepted"):
            continue
        rt = _hello_resp_time(h)
        if rt is None or not (rt < t_ms):
            continue
        if best is None or rt > best_t:
            best = h
            best_t = rt
    if best is not None and _finite(best.get("world_size")):
        return int(best["world_size"])
    return 16384


# ---------------------------------------------------------------------------------------------------
# Enmienda de identidad (brief:1296-1313, 2026-11-23; descongela F2P): la sonda y el producto se
# casan por la VIDA DEL SERVIDOR, no por igualdad de ids. En el juego son UUID independientes: la
# sonda genera su `inst` y la da como `server_epoch` (`DSBX_QA_Probe.c:264-274`, en la #22); el
# producto genera su `inst` (`DayZSandbox/scripts/3_Game/DSBX_Peer.c:199`) y su epoch
# (`DSBX_World.c:34`) por separado. El oráculo de 98c7a78 exigía la igualdad (`_measurement` con
# `_tap_epoch_for_inst`, el censo del control y F2P-10) y una partida honesta daba INCONCLUSO en todo.
# ---------------------------------------------------------------------------------------------------

def _server_lives(probe: dict[str, Any], tap: dict[str, Any],
                  backend: dict[str, Any]) -> dict[str, Any]:
    """Vidas del servidor y la identidad de cada lado en cada una (brief:1304-1308).

    - Vida (brief:1304): el tramo entre dos `restart` con `target: server` del runner (§5.4), o
      desde el principio hasta el primero y desde el último hasta el final, en el reloj común
      (R-03). Cada vida es `[lo, hi)`, como los tramos del backend (`_backend_session_segments`).
    - Producto (brief:1305): la `(inst, epoch)` de sus `/hello` de servidor ACEPTADOS del `tap`, a la
      hora de su respuesta (`_hello_resp_time`). Un `/hello` repetido con la misma identidad no
      cuenta como otro: el producto vuelve a saludar tras cada reinicio del backend (P3, P4a, P5).
    - Sonda (brief:1305): la `inst` de sus `hello` de servidor aceptados (`bridge.jsonl`) y la
      `(inst, server_epoch)` de la lectura de arranque de cada trabajo (`per_census_start` o
      `per_witness_start`), a la hora de su entrega (`deliver`).

    Qué cuenta como identidad (INTERPRETACIÓN, ninguna abre un PASA):
    - solo valores de 32 hex. Una `inst` o un epoch vacíos o mal formados no casan con nada
      (v1.3.14) y no son la identidad de nadie: no cuentan como otra identidad de la vida; el
      `/hello` o el trabajo que los lleva no casa por su cuenta;
    - de la sonda, solo los trabajos de una instancia que había saludado antes de la entrega (el
      bridge solo entrega a una instancia registrada). Un trabajo de una `inst` que no saludó no es
      de la sonda: no cuenta como identidad suya y no casa (ya fallaba `_hello_before`). Así un censo
      espurio no tapa un FALLA de su vida (Sol r1, `sol_confirmed_alive_hidden`).

    Una vida CASA si (brief:1305-1308):
    - cada lado tiene UNA sola identidad (la sonda: una `inst` y, si tiene trabajos, un epoch);
    - la sonda saludó en ella;
    - ningún valor de esas identidades (la `inst` o el epoch de un lado) apareció en una vida
      ANTERIOR del mismo lado (cada vida, identidades nuevas). INTERPRETACIÓN: la enmienda dice «la
      vida anterior» (brief:1306); aquí cuenta cualquiera anterior, que es más estricto. La vida
      anterior no se invalida por lo que traiga la siguiente.

    Si una vida no casa, sus trabajos no se juzgan: las comprobaciones que los usan dan INCONCLUSO
    (brief:1308). La igualdad de ids ENTRE lados no se pide ni se prohíbe.
    """
    edges = sorted(float(r["t_ms"]) for r in backend.get("restarts") or []
                   if str((r.get("data") or {}).get("target") or "") == "server")
    bounds = [float("-inf")] + edges + [float("inf")]
    lives: list[dict[str, Any]] = []
    for i in range(len(bounds) - 1):
        lives.append({"lo": bounds[i], "hi": bounds[i + 1], "prod_ids": set(),
                      "prod_hello_t": [], "probe_insts": set(), "probe_epochs": set(),
                      "probe_hello": False})

    def at(t: float) -> dict[str, Any]:
        for life in lives:
            if life["lo"] <= t < life["hi"]:
                return life
        return lives[-1]

    for h in tap.get("hellos") or []:
        if str(h.get("peer") or "") != "server" or not h.get("accepted"):
            continue
        rt = _hello_resp_time(h)
        inst = str(h.get("inst") or "")
        epoch = str(h.get("epoch") or "")
        if rt is None or not _HEX32.match(inst) or not _HEX32.match(epoch):
            continue
        life = at(float(rt))
        life["prod_ids"].add((inst, epoch))
        life["prod_hello_t"].append(float(rt))
    probe_hello_t: dict[str, list[float]] = {}
    for h in probe.get("hellos") or []:
        inst = str(h.get("inst") or "")
        if str(h.get("peer") or "") != "server" or not _finite(h.get("t_ms")) or \
                not _HEX32.match(inst):
            continue
        probe_hello_t.setdefault(inst, []).append(float(h["t_ms"]))
        life = at(float(h["t_ms"]))
        life["probe_insts"].add(inst)
        life["probe_hello"] = True
    for job in (probe.get("jobs") or {}).values():
        t = job.get("deliver_t")
        inst = str(job.get("inst") or "")
        epoch = str(job.get("epoch") or "")
        if t is None or not _finite(t) or not _HEX32.match(inst) or not _HEX32.match(epoch):
            continue
        if not any(ht < float(t) for ht in probe_hello_t.get(inst) or ()):
            continue
        life = at(float(t))
        life["probe_insts"].add(inst)
        life["probe_epochs"].add(epoch)

    first: dict[str, dict[str, int]] = {"prod_inst": {}, "prod_epoch": {},
                                        "probe_inst": {}, "probe_epoch": {}}

    def values_of(life: dict[str, Any]) -> tuple[tuple[str, set[str]], ...]:
        return (("prod_inst", {i for i, _e in life["prod_ids"]}),
                ("prod_epoch", {e for _i, e in life["prod_ids"]}),
                ("probe_inst", set(life["probe_insts"])),
                ("probe_epoch", set(life["probe_epochs"])))

    for idx, life in enumerate(lives):
        for key, values in values_of(life):
            for v in values:
                first[key].setdefault(v, idx)
    for idx, life in enumerate(lives):
        problems: list[str] = []
        if len(life["prod_ids"]) != 1:
            problems.append(f"product_ids={len(life['prod_ids'])}")
        if len(life["probe_insts"]) != 1:
            problems.append(f"probe_insts={len(life['probe_insts'])}")
        if len(life["probe_epochs"]) > 1:
            problems.append(f"probe_epochs={len(life['probe_epochs'])}")
        if not life["probe_hello"]:
            problems.append("probe_hello_missing")
        for key, values in values_of(life):
            if any(first[key][v] < idx for v in values):
                problems.append(f"repeated:{key}")
        life["ok"] = not problems
        life["reason"] = ",".join(problems)
        life["prod"] = next(iter(life["prod_ids"])) if len(life["prod_ids"]) == 1 else None
        life["probe"] = ((next(iter(life["probe_insts"])),
                          next(iter(life["probe_epochs"])) if life["probe_epochs"] else "")
                         if len(life["probe_insts"]) == 1 and len(life["probe_epochs"]) <= 1
                         else None)
        life["prod_hello_t"].sort()
    return {"edges": edges, "lives": lives}


def _life_at(probe: dict[str, Any], t_ms: float) -> dict[str, Any] | None:
    """Vida del servidor que contiene `t_ms` (`[lo, hi)`), o None sin vidas calculadas."""
    lives = probe.get("lives")
    if not isinstance(lives, dict) or not _finite(t_ms):
        return None
    for life in lives.get("lives") or []:
        if life["lo"] <= float(t_ms) < life["hi"]:
            return life
    return None


def _life_index_at(probe: dict[str, Any], t_ms: float) -> int | None:
    """Índice de la vida del servidor que contiene `t_ms`, o None (ronda 2, B4: la reutilización de
    `net_id` se mira dentro de una misma vida; entre vidas distintas un `net_id` igual no dice nada)."""
    lives = probe.get("lives")
    if not isinstance(lives, dict) or not _finite(t_ms):
        return None
    for idx, life in enumerate(lives.get("lives") or []):
        if life["lo"] <= float(t_ms) < life["hi"]:
            return idx
    return None


def _job_life_problem(probe: dict[str, Any], job: dict[str, Any]) -> str:
    """'' si el trabajo de la sonda casa con la vida en que se entregó (brief:1307-1308).

    - El trabajo se ata a la vida de su entrega; sin entrega o sin vidas calculadas no casa (las
      calcula `evaluate`; una llamada sin ellas falla cerrada).
    - La vida casa (`_server_lives`) y la `(inst, server_epoch)` de su lectura de arranque es la de
      la sonda en esa vida.
    - El producto saludó en esa vida antes de la entrega: un `/hello` suyo aceptado, con respuesta
      anterior a la entrega. Es lo que ya pedía `_tap_epoch_for_inst` (un `/hello` del producto en
      vigor antes de la entrega), sin la igualdad de ids.
    """
    t = job.get("deliver_t")
    if t is None or not _finite(t):
        return "no_delivery"
    life = _life_at(probe, float(t))
    if life is None:
        return "no_life"
    if not life.get("ok"):
        return "life_unbound:" + str(life.get("reason") or "")
    if life.get("probe") is None or \
            (str(job.get("inst") or ""), str(job.get("epoch") or "")) != tuple(life["probe"]):
        return "probe_identity_mismatch"
    if not any(float(rt) < float(t) for rt in life.get("prod_hello_t") or []):
        return "product_hello_after_delivery"
    return ""


def _job_epoch(probe: dict[str, Any], job: dict[str, Any] | None) -> str:
    """Epoch con que se juzga un trabajo de la sonda: el del producto en su vida (brief:1307).

    Vacío si el trabajo no casa: un epoch vacío no casa con nada (v1.3.14).
    """
    if job is None or _job_life_problem(probe, job) != "":
        return ""
    life = _life_at(probe, float(job["deliver_t"]))
    return str(life["prod"][1]) if life is not None and life.get("prod") else ""


def _lives_metric(lives: dict[str, Any]) -> list[dict[str, Any]]:
    """Resumen de las vidas para `metrics.server_lives` (diagnóstico; no decide nada)."""
    out: list[dict[str, Any]] = []
    for life in lives.get("lives") or []:
        out.append({
            "desde_t_ms": life["lo"] if math.isfinite(life["lo"]) else None,
            "hasta_t_ms": life["hi"] if math.isfinite(life["hi"]) else None,
            "casa": bool(life.get("ok")),
            "motivo": str(life.get("reason") or ""),
            "producto": list(life["prod"]) if life.get("prod") else None,
            "sonda": list(life["probe"]) if life.get("probe") else None,
        })
    return out


def _measurement(job: dict[str, Any], *, manifest: dict[str, Any], probe: dict[str, Any],
                 tap: dict[str, Any] | None = None, part: str,
                 judged_t: float | None = None, fresh: bool = False) -> str:
    """Valida una medición (censo o testigo) según §6.1 punto 1.

    Devuelve '' si es válida; en otro caso 'unbacked_rows'. Es la ÚNICA función que decide si una
    medición cuenta, y la consumen todas las comprobaciones (F2P-10 incluida). Reloj (R-03): la
    frescura se mide con `t_ms` de la entrega frente al terminal (también `t_ms`); los ticks solo se
    validan contra sí mismos y contra su ventana. El epoch es por evento (punto 8): sale del trabajo
    y tiene que casar con el `/hello` de su instancia en vigor antes de la entrega.
    Enmienda de identidad (brief:1296-1313): ese casado ya no es por igualdad de ids con el `/hello`
    del producto, sino por la vida del servidor (`_job_life_problem`), y se exige SIEMPRE, con `tap`
    o sin él; el parámetro `tap` se conserva por las llamadas, pero la identidad no depende de él.
    """
    if not job.get("valid"):
        return "unbacked_rows"
    if not _job_args_ok(job):
        return "unbacked_rows"
    if job.get("part") != part:
        return "unbacked_rows"
    win = _part_window(manifest, part)
    if win is None:
        return "unbacked_rows"
    epoch = str(job.get("epoch") or "")
    if not _HEX32.match(epoch):
        return "unbacked_rows"
    deliver_t = job.get("deliver_t")
    if deliver_t is None or not _finite(deliver_t):
        return "unbacked_rows"
    if not (float(win["start_t_ms"]) <= float(deliver_t) <= float(win["end_t_ms"])):
        return "unbacked_rows"
    if job.get("start_t") is None or float(job["start_t"]) < float(deliver_t):
        return "unbacked_rows"
    ident = manifest.get("identity") or {}
    pv = "dsbx-qa1+" + str(ident.get("probe_stamp") or "")
    if not _hello_before(probe, job.get("inst") or "", pv, float(deliver_t)):
        return "unbacked_rows"
    # Enmienda de identidad (brief:1296-1313). Antes: el epoch del trabajo igual al del `/hello` del
    # producto con la MISMA `inst` (`_tap_epoch_for_inst`), solo con `tap`. Ahora: el trabajo se ata
    # a la vida del servidor en que se entregó, su identidad es la de la sonda en esa vida y la vida
    # casa con una sola identidad del producto, que saludó antes de la entrega. Si no casa, nunca PASA.
    if _job_life_problem(probe, job) != "":
        return "unbacked_rows"
    # v1.3.11 (F-01): el epoch del trabajo es el de su lectura de arranque; las páginas no lo traen.
    if job.get("min_page_t") is not None and job.get("start_t") is not None and \
            float(job["min_page_t"]) < float(job["start_t"]):
        return "unbacked_rows"
    if job["kind"] == "census":
        # v1.3.11 (F-08): discos prescritos. El principal va en (6170, 7643) con 115 m; el censo del
        # control, en la posición del control con 30 m. Un componente con otros argumentos no vale.
        tag = str(job.get("tag") or "")
        cx = float(job.get("center_x", 0.0))
        cz = float(job.get("center_z", 0.0))
        rad = float(job.get("radius", 0.0))
        if tag.endswith(":control"):
            if abs(cx - CONTROL_POS[0]) > 0.5 or abs(cz - CONTROL_POS[1]) > 0.5 or \
                    abs(rad - CONTROL_CENSUS_RADIUS_M) > 1e-6:
                return "unbacked_rows"
        elif ":disk:" in tag:
            if not tag.split(":disk:", 1)[1] or rad <= 0.0 or rad > WITNESS_RADIUS:
                return "unbacked_rows"
        else:
            if abs(cx - WITNESS_CENTER[0]) > 1.0 or abs(cz - WITNESS_CENTER[1]) > 1.0 or \
                    abs(rad - MAIN_CENSUS_RADIUS_M) > 1e-6:
                return "unbacked_rows"
        snap = job.get("snap_tick_ms")
        frame = job.get("snap_frame")
        if snap is None or frame is None or not _finite(snap) or not _finite(frame):
            return "unbacked_rows"
        if float(snap) <= 0.0 or float(frame) <= 0.0:
            return "unbacked_rows"
        captured = job.get("rows_captured_n")
        if captured is None or not _finite(captured) or int(captured) != len(job["rows"]):
            return "unbacked_rows"
        if fresh:
            if judged_t is None or not _finite(judged_t):
                return "unbacked_rows"
            if float(deliver_t) <= float(judged_t):
                return "unbacked_rows"
    else:
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
        # S-11: las páginas solo valen después del cierre acreditado de la ventana (reloj común).
        if job.get("min_page_t") is None or \
                float(job["min_page_t"]) < float(deliver_t) + float(job["window_ms"]):
            return "unbacked_rows"
        start = float(job["start_tick_ms"])
        close = start + float(job["window_ms"])
        for r in job["rows"]:
            tick = r.get("tick_ms")
            if not _finite(tick) or not (start <= float(tick) <= close):
                return "unbacked_rows"
    return ""


def _stimulus_ok(op: dict[str, Any], *, manifest: dict[str, Any], probe: dict[str, Any],
                 part: str) -> str:
    """Valida un estímulo crudo de la sonda (`per_spawn_raw`, `per_cleanup_qa`) según punto 1."""
    win = _part_window(manifest, part)
    if win is None:
        return "unbacked_rows"
    if op.get("status") != "done":
        return "unbacked_rows"
    deliver_t = op.get("t_deliver")
    result_t = op.get("t_result")
    if deliver_t is None or result_t is None or not _finite(deliver_t) or not _finite(result_t):
        return "unbacked_rows"
    if float(result_t) < float(deliver_t):
        return "unbacked_rows"
    insts = (op.get("inst_enq"), op.get("inst_deliver"), op.get("inst_result"))
    if not all(insts) or len(set(insts)) != 1:
        return "unbacked_rows"
    if not (float(win["start_t_ms"]) <= float(deliver_t) <= float(win["end_t_ms"])):
        return "unbacked_rows"
    ident = manifest.get("identity") or {}
    pv = "dsbx-qa1+" + str(ident.get("probe_stamp") or "")
    if not _hello_before(probe, op.get("inst") or "", pv, float(deliver_t)):
        return "unbacked_rows"
    return ""


def _stimulus_unbacked(probe: dict[str, Any], manifest: dict[str, Any], part: str) -> bool:
    """R-05: hay estímulos crudos de esa parte y alguno no pasa `_stimulus_ok`.

    Distingue «hay estímulos pero no están acreditados» (INCONCLUSO `unbacked_rows`) de «no hay
    estímulos» (el consumidor decide). Solo cuenta los estímulos cuya cola o entrega cae en la
    ventana de la parte.
    """
    win = _part_window(manifest, part)
    if win is None:
        return False
    start = float(win["start_t_ms"])
    end = float(win["end_t_ms"])
    for op in probe["ops"].values():
        if op.get("verb") not in ("per_spawn_raw", "per_cleanup_qa"):
            continue
        deliver_t = op.get("t_deliver")
        if deliver_t is not None and _finite(deliver_t):
            t = float(deliver_t)
        else:
            t = op.get("t_enq")
            if t is None or not _finite(t):
                continue
            t = float(t)
        if not (start <= t <= end):
            continue
        if _stimulus_ok(op, manifest=manifest, probe=probe, part=part) != "":
            return True
    return False


def _is_terminal(state: str, reason: str) -> bool:
    """§6.1 punto 2 (v1.3.11, F-05): terminales del backend, por igualdad exacta.

    `observado_inventado` no es terminal: el backend no emite ese estado.
    """
    if state in ("observado", "fallido"):
        return True
    return state == "parcial" and reason in TERMINAL_PARCIAL_REASONS


def _stage_terminal(manifest: dict[str, Any], part: str, stage: str) -> tuple[str, str] | None:
    """Estado terminal esperado de una etapa positiva (§6.1 punto 2, v1.3.11 F-05).

    Devuelve `(estado, motivo)` o None si la etapa no tiene terminal esperado (P5:cut).
    """
    if part == "P2n":
        variant = str((manifest.get("f2p") or {}).get("p2n_variant") or "")
        return {"create_failed_first": ("fallido", "create_failed"),
                "create_failed_after": ("parcial", "compensada"),
                "displaced": ("fallido", "lectura_no_cumple")}.get(variant)
    if part in ("P2", "P4b", "P5") and stage in ("apply", "apply2"):
        return ("observado", "")
    if part == "P3":
        if stage in ("apply1", "apply2"):
            return ("observado", "")
        if stage in ("reset1", "reset2"):
            return ("parcial", "contenido_ajeno")
    if part == "P3c" and stage == "clean":
        return ("observado", "")
    if part == "P4a":
        return ("observado", "")
    if part == "P4c" and stage == "reset":
        return ("observado", "")
    return None


def _terminal_state(backend: dict[str, Any], op_id: str,
                    session: str) -> dict[str, Any] | None:
    """§6.1 punto 2 (v1.3.9): el terminal de `(sesión, op_id)`, nunca del `op_id` suelto."""
    best = None
    for st in backend["op_states"]:
        if str(st["data"].get("op_id") or "") != op_id:
            continue
        if str(st.get("session") or "") != session:
            continue
        state = str(st["data"].get("state") or "")
        reason = str(st["data"].get("reason") or "")
        if not _is_terminal(state, reason):
            continue
        if best is None or st["t_ms"] >= best["t_ms"]:
            best = st
    return best


_STAGE_CHECK = {
    ("P2", "scene.apply", 0): "F2P-01",
    ("P2n", "scene.apply", 0): "F2P-03",
    ("P2n", "scene.reset", 0): "F2P-03",
    ("P3", "scene.apply", 0): "F2P-05",
    ("P3", "scene.apply", 1): "F2P-05",
    ("P3", "scene.reset", 0): "F2P-05",
    ("P3", "scene.reset", 1): "F2P-05",
    ("P3c", "scene.reset", 0): "F2P-06",
    ("P4c", "scene.reset", 0): "F2P-07",
    ("P4b", "scene.apply", 0): "F2P-07",
    ("P4a", "scene.apply", 0): "F2P-08",
    ("P4a", "scene.apply", 1): "F2P-08",
    ("P4a", "scene.reset", 0): "F2P-08",
    ("P5", "scene.apply", 1): "F2P-09",
}


def _second_terminal_check(tap: dict[str, Any], backend: dict[str, Any],
                           manifest: dict[str, Any], session: str, op_id: str) -> str:
    """v1.3.13 (T2f-12, B-05; brief:498): comprobación de la etapa de la op, o de su parte."""
    ds = [d for d in tap["deliveries"] if str(d["op_id"]) == op_id and
          str(d["session"]) == session]
    if ds:
        d = min(ds, key=lambda x: float(x["t_ms"]))
        part = _part_for_time(manifest, float(d["t_ms"]))
        ops = _tap_op(tap, str(d["verb"]), part, manifest)
        idx = next((i for i, x in enumerate(ops) if str(x["op_id"]) == op_id and
                    str(x["session"]) == session), 0)
        cid = _STAGE_CHECK.get((part, str(d["verb"]), idx))
        if cid:
            return cid
        ids = TRACE_PART_CHECKS.get(part) or ()
        return ids[0] if ids else ""
    for st in backend["op_states"]:
        if str(st["data"].get("op_id") or "") == op_id and \
                str(st.get("session") or "") == session:
            part = _part_for_time(manifest, float(st["t_ms"]))
            ids = TRACE_PART_CHECKS.get(part) or ()
            return ids[0] if ids else ""
    return ""


def _p5_cut_key(tap: dict[str, Any], backend: dict[str, Any],
                manifest: dict[str, Any]) -> tuple[str, str] | None:
    """Identidad de la op cortada de P5 (la que ya juzga A-02 con `cut_op_terminals`)."""
    cuts = [c for c in backend.get("cuts", []) if
            _part_for_time(manifest, float(c["t_ms"])) == "P5"]
    if not cuts:
        return None
    t = float(min(cuts, key=lambda x: float(x["t_ms"]))["t_ms"])
    sess = _backend_sessions(tap, backend)(t)
    cands = [d for d in tap["deliveries"] if d["verb"] == "scene.apply" and
             d["session"] == sess and float(d["t_ms"]) <= t]
    if not cands:
        return None
    d = max(cands, key=lambda x: x["t_ms"])
    return (str(d["session"]), str(d["op_id"]))


def _generation_rebuild(probe: dict[str, Any], manifest: dict[str, Any], part: str, stage: str,
                        doc: dict[str, Any]) -> dict[str, Any]:
    """Reconstruye la generación de un apply con SU testigo (§6.1 punto 3, R-08).

    Correspondencia uno a uno entre las filas del documento y los nacimientos: cada nacimiento
    consume como mucho una fila libre; los que no encuentran fila son extras. Las identidades se
    siguen por `net_id`; nunca se vuelve a buscar por pose después de nacer.
    """
    tag = f"{part}:{stage}"
    job = _witness(probe, tag)
    empty = {"ok": False, "reason": "unbacked_rows", "pairs": {}, "births": {}, "extras": [],
             "unmatched": [], "nets": set()}
    if job is None or _measurement(job, manifest=manifest, probe=probe, part=part) != "":
        return empty
    doc_entities = list(doc.get("entities") or [])
    doc_classes = {str(e["cls"]) for e in doc_entities}
    used: set[int] = set()
    pairs: dict[str, str] = {}
    births: dict[str, dict[str, Any]] = {}
    extras: list[dict[str, Any]] = []
    for r in job["rows"]:
        if int(r.get("sample_idx", -1)) != 0:
            continue
        if str(r.get("parent_net_id") or "") != "":
            continue
        net = str(r.get("net_id"))
        if net in births:
            continue
        if str(r.get("class_name")) not in doc_classes:
            # V-06: un nacimiento de una clase ajena al documento no entra en la generación.
            continue
        births[net] = r
        match = None
        for i, e in enumerate(doc_entities):
            if i in used or str(r.get("class_name")) != str(e["cls"]):
                continue
            # S-14: el umbral es estricto, < 0,5 m; 0,5 m exactos no casan.
            if math.hypot(float(r["pos_x_m"]) - float(e["x"]),
                          float(r["pos_z_m"]) - float(e["z"])) < EPS_OBJ_M:
                match = (i, e)
                break
        if match is None:
            extras.append(r)
        else:
            used.add(match[0])
            pairs[str(match[1]["id"])] = net
    unmatched = [str(e["id"]) for i, e in enumerate(doc_entities) if i not in used]
    return {"ok": True, "reason": "", "pairs": pairs, "births": births, "extras": extras,
            "unmatched": unmatched, "nets": set(births)}


def _generation_epoch(probe: dict[str, Any], part: str, stage: str) -> str:
    job = _witness(probe, f"{part}:{stage}")
    return str(job.get("epoch") or "") if job is not None else ""


def _k_before_cut(probe: dict[str, Any], gen: dict[str, Any], cut_t: float,
                  inst: str) -> int:
    """Nacimientos de la generación cortada anteriores al corte, con el ancla del `poll` (F-03).

    Un nacimiento es anterior al corte si hay un `poll` de la sonda de la misma instancia con
    `t_ms` anterior al del `cut` y `1000 · tick_s >= tick_ms` del nacimiento. Ticks con ticks y
    `t_ms` con `t_ms` (R-03).
    """
    if not gen.get("ok"):
        return 0
    polls = [p for p in probe.get("polls") or []
             if p.get("tick_s") is not None and str(p.get("inst") or "") == inst and
             float(p["t_ms"]) < float(cut_t)]
    k = 0
    for net in gen["pairs"].values():
        birth = gen["births"].get(net)
        if birth is None:
            continue
        tick = birth.get("tick_ms")
        if not _finite(tick):
            continue
        if any(1000.0 * float(p["tick_s"]) >= float(tick) for p in polls):
            k += 1
    return k


def _generation(probe: dict[str, Any], manifest: dict[str, Any], part: str, stage: str,
                doc: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Generación propia de un apply: solo las identidades que consumieron una fila del documento."""
    gen = _generation_rebuild(probe, manifest, part, stage, doc)
    if not gen["ok"]:
        return None
    return {net: gen["births"][net] for net in gen["pairs"].values()}


def _generation_positions(probe: dict[str, Any], manifest: dict[str, Any],
                          doc1: dict[str, Any], doc2: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for part, stage, doc in (("P2", "apply", doc1), ("P2n", "apply", doc1),
                             ("P3", "apply1", doc1), ("P3", "apply2", doc2),
                             ("P4a", "apply1", doc1), ("P4a", "apply2", doc1),
                             ("P4b", "apply", doc1), ("P5", "cut", doc1)):
        gen = _generation_rebuild(probe, manifest, part, stage, doc)
        if gen["ok"]:
            rows.extend(gen["births"].values())
    return rows


def _last_known_positions(probe: dict[str, Any], manifest: dict[str, Any],
                          before_t: float, doc1: dict[str, Any],
                          doc2: dict[str, Any], epoch: str = "") -> dict[str, dict[str, Any]]:
    """Última posición válida de cada entidad de una generación de F2 anterior a un reinicio (R-09).

    Se siguen las identidades por `net_id` en los censos válidos anteriores al reinicio; la última
    medición válida manda, no la de nacimiento. Devuelve la fila completa (clase, x, y, z y yaw) para
    poder juzgar la reaparición exacta de §6.1 F2P-07 (0,1 m y 1°).
    """
    gen_nets: set[str] = set()
    for part, stage, doc in (("P2", "apply", doc1), ("P2n", "apply", doc1),
                             ("P3", "apply1", doc1), ("P3", "apply2", doc2),
                             ("P4a", "apply1", doc1), ("P4a", "apply2", doc1),
                             ("P4b", "apply", doc1), ("P5", "cut", doc1)):
        gen = _generation_rebuild(probe, manifest, part, stage, doc)
        if gen["ok"]:
            gen_nets |= gen["nets"]
    jobs = sorted([j for j in probe["jobs"].values() if j["kind"] == "census"],
                  key=lambda j: float(j.get("deliver_t") or 0.0), reverse=True)
    found: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if job.get("deliver_t") is None or float(job["deliver_t"]) >= before_t:
            continue
        # v1.3.11 (F-11): la identidad es `(epoch, net_id)`; el seguimiento no cruza un reinicio.
        # Enmienda de identidad (brief:1307): el epoch del censo es el del producto en su vida.
        if epoch and _job_epoch(probe, job) != epoch:
            continue
        if _measurement(job, manifest=manifest, probe=probe, part=job["part"]) != "":
            continue
        for r in job["rows"]:
            net = str(r.get("net_id"))
            if net in gen_nets and net not in found:
                found[net] = r
    return found


def _exact_reappearance(row: dict[str, Any], last_known: dict[str, dict[str, Any]]) -> bool:
    """§6.1 F2P-07: misma clase y pose de la última posición conocida a 0,1 m y 1°."""
    cls = str(row.get("class_name"))
    for lk in last_known.values():
        if str(lk.get("class_name")) != cls:
            continue
        if abs(float(row["pos_x_m"]) - float(lk["pos_x_m"])) <= 0.1 and \
                abs(float(row["pos_y_m"]) - float(lk["pos_y_m"])) <= 0.1 and \
                abs(float(row["pos_z_m"]) - float(lk["pos_z_m"])) <= 0.1 and \
                _yaw_delta(row.get("yaw_deg"), lk.get("yaw_deg")) <= 1.0:
            return True
    return False


def _near_last_known(row: dict[str, Any], last_known: dict[str, dict[str, Any]]) -> bool:
    """§6.1 F2P-07: a menos de 2 m en horizontal de una última posición conocida."""
    for lk in last_known.values():
        if math.hypot(float(row["pos_x_m"]) - float(lk["pos_x_m"]),
                      float(row["pos_z_m"]) - float(lk["pos_z_m"])) < 2.0:
            return True
    return False


def _census_union(probe: dict[str, Any], manifest: dict[str, Any], part: str, main_tag: str,
                  judged_t: float | None = None, fresh: bool = False,
                  tap: dict[str, Any] | None = None) -> dict[str, Any]:
    """Unión deduplicada de los discos de censo tomados para un instante (§6.1 punto 4).

    La consumen TODAS las comprobaciones. Los discos suplementarios se ligan por etiqueta
    (`<tag>:disk:<lid>`), nunca por cercanía temporal (V-08). Cada componente pasa la validación y la
    frescura; si uno no las pasa, la unión entera da INCONCLUSO y no se omite en silencio (S-02).
    """
    main = _census(probe, main_tag)
    if main is None:
        return {"ok": False, "reason": "unbacked_rows", "rows": {}, "disks": []}
    if _measurement(main, manifest=manifest, probe=probe, part=part, judged_t=judged_t,
                    fresh=fresh, tap=tap) != "":
        return {"ok": False, "reason": "unbacked_rows", "rows": {}, "disks": []}
    jobs = [main]
    for job in probe["jobs"].values():
        if job is main or job["kind"] != "census":
            continue
        if not str(job["tag"]).startswith(main_tag + ":disk:"):
            continue
        jobs.append(job)
    rows: dict[str, dict[str, Any]] = {}
    row_tick: dict[str, float] = {}
    disks: list[tuple[float, float, float]] = []
    components: list[dict[str, Any]] = []
    for job in jobs:
        if _measurement(job, manifest=manifest, probe=probe, part=part, judged_t=judged_t,
                        fresh=fresh, tap=tap) != "":
            return {"ok": False, "reason": "unbacked_rows", "rows": {}, "disks": [],
                    "row_tick": {}, "components": []}
        disks.append((float(job["center_x"]), float(job["center_z"]), float(job["radius"])))
        components.append({"tag": str(job.get("tag") or ""),
                           "center": (float(job["center_x"]), float(job["center_z"])),
                           "radius": float(job["radius"]),
                           "snap_tick_ms": job.get("snap_tick_ms"),
                           "rows": list(job["rows"])})
        for r in job["rows"]:
            net = str(r.get("net_id"))
            if net not in rows:
                rows[net] = r
                if _finite(job.get("snap_tick_ms")):
                    row_tick[net] = float(job["snap_tick_ms"])
    if not disks:
        return {"ok": False, "reason": "unbacked_rows", "rows": {}, "disks": [],
                "row_tick": {}, "components": []}
    return {"ok": True, "reason": "", "rows": rows, "disks": disks,
            "row_tick": row_tick, "components": components}


def _point_in_union(pos: tuple[float, float], disks: list[tuple[float, float, float]]) -> bool:
    return any(math.hypot(pos[0] - cx, pos[1] - cz) <= radius for cx, cz, radius in disks)


def _coverage_status(pos: tuple[float, float], disks: list[tuple[float, float, float]]) -> str:
    if not _point_in_union(pos, disks):
        return "outside"
    return "deep" if _covered(pos, disks, COVERAGE_EDGE_M) else "edge"


def _covered(pos: tuple[float, float], disks: list[tuple[float, float, float]],
             required: float) -> bool:
    """Contención contra la UNIÓN de discos (S-02), por rejilla de 0,5 m (o más fina)."""
    for cx, cz, radius in disks:
        if math.hypot(pos[0] - cx, pos[1] - cz) + required <= radius:
            return True
    if not disks or required <= 0:
        return _point_in_union(pos, disks)
    step = max(0.5, required / 120.0)
    n = max(1, int(math.ceil(required / step)))
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            dx = i * step
            dz = j * step
            if dx * dx + dz * dz > required * required + 1e-9:
                continue
            if not _point_in_union((pos[0] + dx, pos[1] + dz), disks):
                return False
    return True


def _backend_validator() -> Any:
    """S-08: el validador del consumidor real (`app.backend.scene_live._valid_read_compat`), o None si
    no se puede importar.

    Re-congelado de 2026-11-23 (decisión de la principal, brief:1314-1315): un import que falla es un
    error de montaje, no una lectura no válida. `evaluate` lo mira antes de juzgar nada y da INCONCLUSO
    `backend_validator_unavailable`, nunca FALLA. Hasta 98c7a78 el fallo del import salía como lectura no
    válida: `_reconciliation_ok` daba False y F2P-05 o F2P-08 daban FALLA. No se guarda entre llamadas:
    cada evaluación mira el import de su momento.
    """
    import sys
    root = str(Path(__file__).resolve().parents[1])
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from app.backend.scene_live import _valid_read_compat
    except Exception:
        return None
    return _valid_read_compat if callable(_valid_read_compat) else None


def _backend_valid_read(read: Any, world_size: int) -> bool:
    """S-08: el validador del consumidor real, importado y usado tal cual (sin exigir `obs`).

    Una excepción del propio validador, ya importado, cuenta como lectura no válida, como antes. Sin
    validador (import roto) también da False, pero `evaluate` ya ha dado INCONCLUSO antes de llegar
    aquí (`_backend_validator`); una llamada suelta falla cerrada.
    """
    validator = _backend_validator()
    if validator is None:
        return False
    try:
        return bool(validator(read, require_obs=None, world_size=world_size))
    except Exception:
        return False


def _valid_read(read: Any, doc_id: str, epoch: str, world_size: int | None = None) -> bool:
    """Lectura de reconciliación: forma del consumidor real, epoch vigente y `doc_id` de la orden."""
    if not isinstance(read, dict):
        return False
    if not isinstance(read.get("epoch"), str) or not _HEX32.match(read["epoch"]) or \
            read["epoch"] != epoch:
        return False
    scene = read.get("scene")
    if not isinstance(scene, dict):
        return False
    if not isinstance(scene.get("doc_id"), str) or not _DOC_ID.match(scene["doc_id"]) or \
            scene["doc_id"] != doc_id:
        return False
    return _backend_valid_read(read, 16384 if world_size is None else world_size)


def _trace_violations(tap: dict[str, Any], backend: dict[str, Any],
                      manifest: dict[str, Any]) -> list[dict[str, str]]:
    """Correlación por `(sesión, op_id)` y conn, en orden temporal (§6.1 punto 5, v1.3.9).

    Una sola resolución por entrega (S-07, V-15): su resultado y un acuse aceptado (2xx y `ok: true`),
    salvo el corte de P5. La traza va por sesión: un `409 hello_required` de un `/poll` tras un
    reinicio del backend no la rompe, y el reenvío rechazado del resultado cortado tampoco cuenta
    como resolución. Un `op.state` de un id `rd-N` no es del backend y rompe la traza.
    """
    out: list[dict[str, str]] = []
    # v1.3.10: todas las respuestas a `/hello` de un tramo dan la misma sesión y ninguna sesión se
    # repite entre tramos; si no, la traza se rompe.
    for prob in _backend_session_problems(tap, backend):
        out.append({"part": _part_for_time(manifest, prob["t_ms"]), "reason": prob["reason"]})
    session_at = _backend_sessions(tap, backend)
    # La op cortada es SOLO el último `scene.apply` entregado antes del `cut`, en la sesión del
    # backend que muere (v1.3.9). No se infiere de un terminal `reconciliada`.
    cut_keys: set[tuple[str, str]] = set()
    cut_ids: set[str] = set()
    cut_meta: dict[tuple[str, str], tuple[float, str]] = {}
    # v1.3.13 (X-04b, §6.1 punto 5 líneas 548 y 553-557): una sola identidad cortada, la del
    # PRIMER `cut` de P5 (la sesión que muere y el último `scene.apply` entregado en ella antes de
    # ese `cut`); otro `cut` de P5 no exime ninguna op.
    p5_cut_events = [c for c in backend.get("cuts", [])
                     if _part_for_time(manifest, float(c["t_ms"])) == "P5"]
    if p5_cut_events:
        c = min(p5_cut_events, key=lambda x: float(x["t_ms"]))
        t = float(c["t_ms"])
        sess = session_at(t)
        candidates = [d for d in tap["deliveries"] if d["verb"] == "scene.apply" and
                      d["session"] == sess and float(d["t_ms"]) <= t]
        if candidates:
            d = max(candidates, key=lambda x: x["t_ms"])
            key = (str(d["session"]), str(d["op_id"]))
            cut_keys.add(key)
            cut_ids.add(str(d["op_id"]))
            cut_meta[key] = (t, sess)
    deliveries: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for d in tap["deliveries"]:
        deliveries.setdefault((str(d["session"]), str(d["op_id"])), []).append(d)
    for v in deliveries.values():
        v.sort(key=lambda x: x["t_ms"])
    results_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in tap["results"]:
        results_by_key.setdefault((str(r["session"]), str(r["op_id"])), []).append(r)
    for v in results_by_key.values():
        v.sort(key=lambda x: x["t_ms"])

    def accepted_ack(r: dict[str, Any]) -> bool:
        return r.get("ack_ok") is True and _is_int(r.get("ack_http")) and \
            200 <= int(r["ack_http"]) < 300

    # Fallback: si el runner no registró el `cut`, la entrega del último `scene.apply` de una sesión
    # que muere en un reinicio del backend y que no tiene resultado aceptado se trata como cortada,
    # para que la traza no se rompa por la ausencia del evento (F2P-09 sigue dando INCONCLUSO).
    # v1.3.13 (X-04b/Y-03, §6.1 punto 5): el respaldo SOLO vale cuando P5 no tiene ningún `cut`.
    # Entonces exime la identidad del último `scene.apply` de la sesión que muere en el primer
    # reinicio del backend de P5; nunca otra.
    p5_cuts = [float(c["t_ms"]) for c in backend.get("cuts", [])
               if _part_for_time(manifest, float(c["t_ms"])) == "P5"]
    p5_cut_t = min(p5_cuts) if p5_cuts else None
    if p5_cut_t is None:
        p5_backend_restarts = [r for r in backend.get("restarts") or []
                               if str((r.get("data") or {}).get("target") or "") == "backend" and
                               _part_for_time(manifest, float(r["t_ms"])) == "P5"]
        if p5_backend_restarts:
            r = min(p5_backend_restarts, key=lambda x: float(x["t_ms"]))
            # La sesión que muere es la vigente justo antes del reinicio.
            sess = session_at(float(r["t_ms"]) - 1e-6)
            cands = [d for d in tap["deliveries"] if d["verb"] == "scene.apply" and
                     d["session"] == sess and float(d["t_ms"]) <= float(r["t_ms"])]
            if cands:
                d = max(cands, key=lambda x: x["t_ms"])
                key = (str(d["session"]), str(d["op_id"]))
                rs = results_by_key.get(key) or []
                if not any(accepted_ack(x) for x in rs):
                    cut_keys.add(key)
                    cut_ids.add(str(d["op_id"]))
                    cut_meta.setdefault(key, (float(r["t_ms"]), sess))

    def rejected_ack(r: dict[str, Any]) -> bool:
        return r.get("ack_ok") is not True or \
            not (_is_int(r.get("ack_http")) and 200 <= int(r["ack_http"]) < 300)

    def cut_resend(r: dict[str, Any]) -> bool:
        """Reenvío del resultado cortado al backend nuevo, rechazado con 409 o 400.

        v1.3.11 (F-04): la excepción vale solo para la identidad `(sesión, op_id)` cortada, después
        del `cut`, en el tramo del backend nuevo y con el rechazo. Un resultado rechazado de otra
        sesión con el mismo `op_id` (p. ej. en P2) no se exime.
        v1.3.16 (T2f-15m, H-02, :589): lo que sitúa el rechazo en el tramo del backend nuevo es su
        respuesta, posterior al cut y del backend (no del tap), no la hora de su petición: un
        reintento pedido después del cut y antes del restart puede esperar en el tap.
        """
        key = (str(r.get("session") or ""), str(r.get("op_id") or ""))
        if key not in cut_keys:
            return False
        if not rejected_ack(r) or not _is_int(r.get("ack_http")) or \
                int(r["ack_http"]) not in (400, 409):
            return False
        cut_t, dying = cut_meta.get(key, (float("-inf"), ""))
        if float(r["t_ms"]) <= cut_t:
            return False
        if r.get("ack_t") is None or float(r["ack_t"]) <= cut_t:
            return False
        # La respuesta la fabrica el tap si upstream_status es nulo (o un entero 0); el resto,
        # incluido un booleano y el campo ausente, es del backend (L-01).
        if r.get("ack_upstream_present"):
            _u = r.get("ack_upstream")
            if _u is None or (_is_int(_u) and int(_u) == 0):
                return False
        return True

    def _query_session_ok(r: dict[str, Any]) -> bool:
        """v1.3.16 (D-04 y T2f-15m, L-05, :588): el query de un reenvío cortado tiene que ser el de
        la sesión vigente si es 400 (W-07), o el del cuerpo si es 409; cualquier otro desacuerdo
        rompe, también si el query es igual al cuerpo."""
        if not cut_resend(r):
            return str(r.get("query_session") or "") == str(r.get("session") or "")
        if int(r["ack_http"]) == 400:
            return str(r.get("query_session") or "") == session_at(float(r["t_ms"]))
        return str(r.get("query_session") or "") == str(r.get("session") or "")

    def _tap_502(r: dict[str, Any]) -> bool:
        """v1.3.16 (§5.4 y §6.1 punto 5): el 502 que fabrica el tap, por los tres campos a la vez.

        v1.3.16 (T2f-15k, N-02): el cuerpo es un objeto con exactamente las claves `ok` y `error`,
        `ok` es el booleano `False` (no `0` ni `0.0`) y `error` es `upstream_unreachable`.
        """
        if not _is_int(r.get("ack_http")) or int(r["ack_http"]) != 502:
            return False
        if not r.get("ack_upstream_present") or r.get("ack_upstream") is not None:
            return False
        body = r.get("ack_body")
        if not isinstance(body, dict) or set(body) != {"ok", "error"}:
            return False
        if body.get("ok") is not False:
            return False
        return body.get("error") == "upstream_unreachable"

    def _tap_close(r: dict[str, Any]) -> bool:
        """v1.3.16 (T2f-15l, §5.4 :339): el cierre sin respuesta del backend (HTTP 0,
        `upstream_status` el entero 0 y cuerpo vacio). No es una respuesta del backend.

        v1.3.16 (T2f-15m, L-01/L-06): un booleano no es el 0 del cierre; el cuerpo vacio es el
        campo ausente, nulo o `""`; `{}` es un cuerpo, no una respuesta vacia.
        """
        if not _is_int(r.get("ack_http")) or int(r["ack_http"]) != 0:
            return False
        if not r.get("ack_upstream_present") or not _is_int(r.get("ack_upstream")) or \
                int(r["ack_upstream"]) != 0:
            return False
        body = r.get("ack_body")
        return body is None or body == ""

    def _backend_pair(_pair: dict[str, Any]) -> bool:
        """v1.3.16 (§5.4): una respuesta del backend; las del tap llevan `upstream_status` nulo, y
        el cierre sin respuesta lo lleva al entero 0 (T2f-15l). Un booleano y el campo ausente
        cuentan como del backend (T2f-15m, L-01)."""
        if not _pair.get("upstream_present"):
            return True
        _u = _pair.get("upstream_status")
        if _u is None:
            return False
        return not (_is_int(_u) and int(_u) == 0)

    def _first_cut_result(key: tuple[str, str], cut_t: float) -> dict[str, Any] | None:
        """v1.3.16 (K-08): el primer `/result` de la identidad cortada mandado hasta el cut."""
        first = None
        for _r in results_by_key.get(key) or []:
            if float(_r["t_ms"]) > float(cut_t):
                continue
            if first is None or float(_r["t_ms"]) < float(first["t_ms"]):
                first = _r
        return first

    def _k08_window(key: tuple[str, str], cut_t: float) -> tuple[float, float] | None:
        """v1.3.16 (K-08): ventana de los `/result` de la identidad cortada, hasta la primera
        respuesta del backend nuevo posterior al cut (cualquier peticion y peer).

        v1.3.16 (T2f-15j, §5.4 :338 y :593): la primera es la de MENOR hora, no la primera linea
        del fichero; el tap puede no ir ordenado por su hora.
        """
        first = _first_cut_result(key, cut_t)
        if first is None:
            return None
        end = float("inf")
        for _pair in tap.get("pairs") or []:
            if float(_pair.get("resp_t") or 0.0) >= float(cut_t) and _backend_pair(_pair):
                end = min(end, float(_pair["resp_t"]))
        return (float(first["t_ms"]), end)

    def _backend_alive(key: tuple[str, str], cut_t: float) -> bool:
        """v1.3.16 (K-08 b): una peticion mandada despues del primer `/result` y respondida por el
        backend antes del cut, de cualquier endpoint. Las respuestas del tap no cuentan."""
        first = _first_cut_result(key, cut_t)
        if first is None:
            return False
        for _pair in tap.get("pairs") or []:
            if float(_pair.get("t_ms") or 0.0) > float(first["t_ms"]) and \
                    float(_pair.get("resp_t") or 0.0) < float(cut_t) and \
                    _backend_pair(_pair):
                return True
        return False

    def _k08_exempt(r: dict[str, Any], key: tuple[str, str], cut_t: float | None) -> bool:
        """v1.3.15 y v1.3.16 (K-08 a): el `/result` de la identidad cortada y sus reintentos, dentro
        de la ventana, sin respuesta, con el 502 del tap o con el cierre sin respuesta del backend
        (T2f-15l), y sin una respuesta del backend antes del cut que pruebe que estaba vivo. El 502
        del tap o el cierre anteriores al cut no quedan exentos."""
        if cut_t is None or key not in cut_keys:
            return False
        _win = _k08_window(key, cut_t)
        if _win is None or float(r["t_ms"]) > float(_win[1]):
            return False
        if r.get("ack_t") is not None:
            if not (_tap_502(r) or _tap_close(r)) or float(r["ack_t"]) < float(cut_t):
                return False
        return not _backend_alive(key, cut_t)

    # v1.3.13 (A-01/B-01, §6.1 punto 5 líneas 550 y 556-558): después del primer `cut` de P5, la
    # sesión que muere no actúa. Una entrega suya (también `rd-N`, de cualquier verbo) o un
    # `/result` aceptado suyo de otra op rompen la traza. No rompen el reenvío rechazado del
    # resultado cortado (cut_resend) ni los 409 de `/poll` con la sesión vieja (no son entregas ni
    # resultados). Solo hay «sesión que muere» si hay un reinicio del backend posterior al cut.
    _p5_restarts_after_cut = [r for r in backend.get("restarts") or []
                              if str((r.get("data") or {}).get("target") or "") == "backend" and
                              _part_for_time(manifest, float(r["t_ms"])) == "P5" and
                              p5_cut_t is not None and float(r["t_ms"]) > p5_cut_t]
    if p5_cut_t is not None and _p5_restarts_after_cut:
        _dying = session_at(p5_cut_t)
        _cut_oid = next((k[1] for k, (t, s) in cut_meta.items()
                         if s == _dying and t == p5_cut_t), "")
        for d in tap["deliveries"]:
            if str(d["session"]) != _dying or float(d["t_ms"]) <= p5_cut_t:
                continue
            out.append({"part": _part_for_time(manifest, d["t_ms"]),
                        "reason": f"dying_delivery_after_cut:{d['op_id']}"})
        for r in tap["results"]:
            if str(r["session"]) != _dying:
                continue
            if accepted_ack(r) and float(r["t_ms"]) > p5_cut_t and \
                    str(r["op_id"]) != _cut_oid:
                out.append({"part": _part_for_time(manifest, r["t_ms"]),
                            "reason": f"dying_result_after_cut:{r['op_id']}"})
            if accepted_ack(r) and r.get("ack_t") is not None and \
                    float(r["ack_t"]) > p5_cut_t:
                out.append({"part": _part_for_time(manifest, r["t_ms"]),
                            "reason": f"dying_ack_after_cut:{r['op_id']}"})
        for h in tap.get("hellos") or []:
            if not h.get("accepted") or str(h.get("session") or "") != _dying:
                continue
            _rt = h.get("resp_t")
            if _rt is None or not _finite(_rt):
                continue
            if float(_rt) > p5_cut_t:
                out.append({"part": _part_for_time(manifest, float(_rt)),
                            "reason": f"dying_hello_after_cut:{h.get('inst') or ''}"})

    # v1.3.13 (T2f-11, C-03; §6.1 punto 2 líneas 482 y 550, punto 5 línea 558): tras CADA reinicio
    # del backend, una respuesta ACEPTADA con la sesión del tramo que ese reinicio cierra rompe la
    # traza: un acuse aceptado (por su `ack_t`) o un `/hello` aceptado (por su `resp_t`). Las reglas
    # de P5 tras el `cut` siguen arriba y no se sustituyen.
    for _r in backend.get("restarts") or []:
        if str((_r.get("data") or {}).get("target") or "") != "backend":
            continue
        _rst = float(_r["t_ms"])
        _old = session_at(_rst - 1e-6)
        if not _old:
            continue
        for _res in tap["results"]:
            if str(_res.get("session") or "") != _old:
                continue
            if accepted_ack(_res) and _res.get("ack_t") is not None and \
                    float(_res["ack_t"]) > _rst:
                out.append({"part": _part_for_time(manifest, float(_res["ack_t"])),
                            "reason": f"old_session_ack_after_restart:{_res['op_id']}"})
        for _h in tap.get("hellos") or []:
            if not _h.get("accepted") or str(_h.get("session") or "") != _old:
                continue
            _hrt = _h.get("resp_t")
            if _hrt is None or not _finite(_hrt):
                continue
            if float(_hrt) > _rst:
                out.append({"part": _part_for_time(manifest, float(_hrt)),
                            "reason": f"old_session_hello_after_restart:{_h.get('inst') or ''}"})

    # v1.3.13 (T2f-12, D-02; §6.1 punto 5 líneas 550 y 556-558): una respuesta ACEPTADA (HTTP 200) a
    # un `/poll` cuya sesión no es la de su tramo a la hora de la respuesta rompe la traza; tambien
    # la de la sesion que muere despues del `cut`. Un 409 o un 400 no la rompe (558).
    _dying_sess = session_at(p5_cut_t) if p5_cut_t is not None else ""

    # v1.3.13 (T2f-13, E-02/E-03; brief:550, 556-558): cada respuesta de `/poll` consume UNA
    # peticion pendiente pedida antes que ella. Un 200 consume la mas antigua que LO ADMITE (su
    # sesion es la del tramo a la hora de la respuesta y, tras el `cut` de P5, no es la que muere);
    # si ninguna lo admite, la mas antigua (y la traza se rompe). Cualquier otra respuesta consume la
    # mas antigua que NO admitiria un 200; si no hay ninguna, la mas antigua; nunca rompe la traza.
    def _conn_number(_v: Any) -> int | None:
        """v1.3.15 (§6.1 punto 5; bridge.py:484-489): la `conn` que la guarda real acepta.

        La guarda convierte con `int()` y exige que el texto sea el del número o que, sin el signo,
        sea todo digitos. `"01"`, `" 1"`, `"1 "`, `"\t1"` y `"١"` son la conexion 1; `"+1"`, `"1_0"`,
        `" 01"`, `"01 "`, `"1.0"`, `""` y `None` no son ninguna conexion.
        """
        if _v is None:
            return None
        try:
            _n = int(_v)
        except (TypeError, ValueError):
            return None
        if str(_n) != str(_v).strip() and \
                not (isinstance(_v, str) and _v.lstrip("-").isdigit()):
            return None
        return _n

    def _conn_eq(_a: Any, _b: Any) -> bool:
        _na = _conn_number(_a)
        _nb = _conn_number(_b)
        return _na is not None and _nb is not None and _na == _nb

    def _peer_registry(_peer: str, _rt: float) -> dict[str, Any] | None:
        """v1.3.13 (T2f-14, G-04): ultimo `/hello` aceptado de ese peer con respuesta anterior a
        `_rt` y dentro del mismo tramo. Se conserva para las variantes de ablacion que parchean su
        linea; la traza usa `_registry_candidates` y `_poll_conn_ok` (v1.3.16, C-02)."""
        _seg = next((x for x in _backend_session_segments(tap, backend)
                     if float(x["lo"]) <= float(_rt) < float(x["hi"])), None)
        if _seg is None:
            return None
        _best = None
        _best_t = None
        for _h in tap.get("hellos") or []:
            if not _h.get("accepted") or str(_h.get("peer") or "") != _peer:
                continue
            _hrt = _hello_resp_time(_h)
            if _hrt is None or not (_hrt < float(_rt)):
                continue
            if not (float(_seg["lo"]) <= _hrt < float(_seg["hi"])):
                continue
            if _best is None or _hrt > _best_t:
                _best = _h
                _best_t = _hrt
        return _best

    def _registry_candidates(_peer: str, _rt: float) -> list[dict[str, Any]]:
        """v1.3.13 (T2f-14, G-04) y v1.3.16 (C-02): registros candidatos de ese peer a la hora `_rt`.

        El ultimo `/hello` aceptado de ese peer con respuesta estrictamente anterior, y, si hay un
        `/hello` aceptado de ese peer en el MISMO milisegundo, tambien ese. El empate vale en los dos
        ordenes; el registro elegido tiene que seguir siendo el mismo a la hora de la respuesta.
        """
        _seg = next((x for x in _backend_session_segments(tap, backend)
                     if float(x["lo"]) <= float(_rt) < float(x["hi"])), None)
        if _seg is None:
            return []
        _out: list[dict[str, Any]] = []
        _best = None
        _best_t = None
        _tie = None
        for _h in tap.get("hellos") or []:
            if not _h.get("accepted") or str(_h.get("peer") or "") != _peer:
                continue
            _hrt = _hello_resp_time(_h)
            if _hrt is None:
                continue
            if not (float(_seg["lo"]) <= _hrt < float(_seg["hi"])):
                continue
            if _hrt < float(_rt):
                if _best is None or _hrt > _best_t:
                    _best = _h
                    _best_t = _hrt
            elif _hrt == float(_rt):
                if _tie is None or _hrt >= _tie[0]:
                    _tie = (_hrt, _h)
        if _best is not None:
            _out.append(_best)
        if _tie is not None:
            _out.append(_tie[1])
        return _out

    def _same_reg(_a: dict[str, Any], _b: dict[str, Any]) -> bool:
        return str(_a.get("inst") or "") == str(_b.get("inst") or "") and \
            _conn_eq(_a.get("conn"), _b.get("conn"))

    def _poll_registries(_r: dict[str, Any], _rt: float) -> list[dict[str, Any]]:
        """v1.3.15 (K-03) y v1.3.16 (C-02): los registros con los que casa la peticion a su hora y
        que siguen siendo los mismos a la de la respuesta, con el empate de milisegundo en los dos
        lados. La entrega tiene que casar con uno de ellos (v1.3.16, :568)."""
        _req_cands = _registry_candidates(str(_r.get("peer") or ""),
                                          float(_r.get("t_ms") or 0.0))
        _matched = [c for c in _req_cands
                    if _anchor_eq(str(c.get("inst") or ""), str(_r.get("inst") or "")) and
                    _conn_eq(c.get("conn"), _r.get("conn"))]
        if not _matched:
            return []
        _resp_cands = _registry_candidates(str(_r.get("peer") or ""), _rt)
        return [c for c in _matched if any(_same_reg(c, d) for d in _resp_cands)]

    def _poll_conn_ok(_r: dict[str, Any], _rt: float) -> bool:
        return bool(_poll_registries(_r, _rt))

    def _poll_admits(_r: dict[str, Any], _rt: float) -> bool:
        _qs = str(_r.get("session") or "")
        _exp = session_at(_rt)
        if not _exp or _qs != _exp:
            return False
        if p5_cut_t is not None and _qs == _dying_sess and _rt > float(p5_cut_t):
            return False
        # v1.3.13 (T2f-14, G-04; brief:550, bridge.py:492-496): la `inst` y la `conn` de la
        # peticion tienen que ser las del registro de su peer en ese tramo; sin registro, no admite.
        # v1.3.15 (K-03; bridge.py:506 y :520-523): el registro se toma a la hora de la PETICION y
        # tiene que ser el mismo a la hora de la respuesta.
        # v1.3.16 (C-02): empate de milisegundo en los dos lados.
        return _poll_conn_ok(_r, _rt)

    def _poll_op_matches(_r: dict[str, Any], _o: dict[str, Any]) -> bool:
        """v1.3.13 (T2f-14, G-01; bridge.py:223, :536-537, :558): solo el servidor recibe ops, y la
        op lleva la sesion, la `inst` y la `conn` de la peticion que la recibe."""
        if str(_r.get("peer") or "") != "server":
            return False
        if str(_r.get("session") or "") != str(_o.get("session") or ""):
            return False
        if str(_r.get("inst") or "") != str(_o.get("inst") or ""):
            return False
        return _conn_eq(_r.get("conn"), _o.get("conn"))

    def _anchor_eq(_a: Any, _b: Any) -> bool:
        """v1.3.14 (§6.1 punto 5): una `inst` o un `epoch` vacios no casan con nada."""
        _sa = str(_a or "")
        _sb = str(_b or "")
        return bool(_sa) and bool(_sb) and _sa == _sb

    for _p in tap.get("polls") or []:
        if _p.get("resp_t") is None or not _is_int(_p.get("http")) or int(_p["http"]) != 200:
            continue
        _prt = float(_p["resp_t"])
        _pqs = str(_p.get("session") or "")
        _ppeer = str(_p.get("peer") or "")
        _pexp = session_at(_prt)
        if not _pexp or _pqs != _pexp:
            out.append({"part": _part_for_time(manifest, _prt),
                        "reason": f"poll_session_mismatch:{_pqs}"})
        _conn_bad = not _poll_conn_ok(_p, _prt)
        if _conn_bad:
            out.append({"part": _part_for_time(manifest, _prt),
                        "reason": f"poll_conn_mismatch:{_ppeer}"})
        # G-01/H-02: un 200 con ops solo puede ser del servidor.
        if _p.get("ops") and _ppeer != "server":
            out.append({"part": _part_for_time(manifest, _prt),
                        "reason": f"poll_peer_mismatch:{_ppeer}"})
        if p5_cut_t is not None and _pqs == _dying_sess and _prt > p5_cut_t:
            out.append({"part": _part_for_time(manifest, _prt),
                        "reason": f"dying_poll_after_cut:{_pqs}"})

    # v1.3.13 (B-02, §6.1 punto 5 líneas 546-547 y 550): la sesión de cada entrega y de cada
    # resultado aceptado es la de su tramo y la abrió un `/hello` aceptado antes de su `t_ms`.
    # Las excepciones son las que ya existen: el reenvío rechazado de la op cortada y los 409 de
    # `/poll` (no son entregas ni resultados aceptados).
    for d in tap["deliveries"]:
        _exp = session_at(float(d["t_ms"]))
        _s = str(d["session"] or "")
        if not _exp or _s != _exp:
            out.append({"part": _part_for_time(manifest, d["t_ms"]),
                        "reason": f"delivery_session_mismatch:{d['op_id']}"})
        elif not _session_opened_before(tap, backend, _s, float(d["t_ms"]),
                                        str(d.get("inst") or "")):
            out.append({"part": _part_for_time(manifest, d["t_ms"]),
                        "reason": f"delivery_session_unbacked:{d['op_id']}"})
        else:
            # v1.3.13 (T2f-15; brief:550, bridge.py:242, :575 y :294-333): si hay registro del
            # servidor a la hora de la entrega y la conn de la op no es la suya, la traza se rompe.
            # Sin registro, decide la regla de hoy (delivery_session_unbacked), sin otro motivo.
            # v1.3.16 (C-02, :568): la entrega casa con el mismo registro con el que caso el `/poll`
            # que la trae, con el empate de milisegundo.
            _poll_req = {"peer": str(d.get("poll_peer") or ""),
                         "t_ms": float(d.get("poll_t_ms") or 0.0),
                         "inst": str(d.get("poll_inst") or ""),
                         "conn": str(d.get("poll_conn") or ""),
                         "session": str(d.get("poll_session") or "")}
            _cands = _poll_registries(_poll_req, float(d["t_ms"]))
            if not _cands:
                # v1.3.16 (T2f-15l, D-02): si el `/poll` que trae la entrega no caso con ningun
                # registro (409, http no entero...), se compara con el registro del servidor a su
                # hora, con el empate de C-02; sin ninguno, sigue la regla de hoy.
                _cands = _registry_candidates("server", float(d["t_ms"]))
            if _cands and not any(
                    _anchor_eq(str(c.get("inst") or ""), str(d.get("inst") or "")) and
                    _conn_eq(c.get("conn"), d.get("conn")) for c in _cands):
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"delivery_conn_mismatch:{d['op_id']}"})
    for r in tap["results"]:
        if not accepted_ack(r):
            continue
        _exp = session_at(float(r["t_ms"]))
        _s = str(r["session"] or "")
        if not _exp or _s != _exp:
            out.append({"part": _part_for_time(manifest, r["t_ms"]),
                        "reason": f"result_session_mismatch:{r['op_id']}"})
        elif not _session_opened_before(tap, backend, _s, float(r["t_ms"]),
                                        str(r.get("inst") or "")):
            out.append({"part": _part_for_time(manifest, r["t_ms"]),
                        "reason": f"result_session_unbacked:{r['op_id']}"})

    # Cada entrega tiene su resolución: resultado y acuse aceptado, salvo la entrega cortada de P5.
    for key, ds in deliveries.items():
        rs = results_by_key.get(key) or []
        is_cut = key in cut_keys
        _cut_t = cut_meta.get(key, (float("-inf"), ""))[0] if is_cut else None
        for i, d in enumerate(ds):
            if i >= len(rs):
                # v1.3.13 (T2f-14, z91; brief:555): TODAS las entregas de la identidad cortada
                # anteriores o iguales a su corte quedan exentas de resultado, no solo la ultima
                # (el bridge reentrega la op `ejecutando` cada retry_ms antes del corte). Una
                # entrega posterior al corte NO queda exenta y rompe la traza.
                # v1.3.13 (T2f-15b, H-04; brief:555): la exencion solo vale para las entregas de la
                # identidad cortada en P5, con el verbo `scene.apply` de la entrega cortada y hasta
                # su corte. Una entrega fuera de P5 o con otro verbo no queda exenta.
                if is_cut and _cut_t is not None and float(d["t_ms"]) <= float(_cut_t) and \
                        _part_for_time(manifest, float(d["t_ms"])) == "P5" and \
                        str(d.get("verb") or "") == "scene.apply":
                    continue
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"delivery_without_result:{key[1]}"})
                continue
            r = rs[i]
            # v1.3.11 (F-04): la sesión del query es la del cuerpo, y la instancia y el epoch del
            # resultado son los de su entrega.
            # v1.3.12 (W-07): el reenvío del corte rechazado con 400 lleva por construcción el
            # query en la sesión vigente y el cuerpo en la vieja; esa excepción no rompe la traza.
            # v1.3.16 (T2f-15m, L-05, :588): el 400 con el query igual al cuerpo (la vieja) y el
            # 409 con el query fuera de la vieja rompen, también con query == cuerpo.
            if not _query_session_ok(r):
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"query_body_session_mismatch:{key[1]}"})
            if not _anchor_eq(str(r.get("inst") or ""), str(d.get("inst") or "")) or \
                    not _anchor_eq(str(r.get("epoch") or ""), str(d.get("epoch") or "")):
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"result_identity_mismatch:{key[1]}"})
            # v1.3.15 (K-01; §6.1 punto 5): el resultado no lleva conexion; la suya es la de su
            # entrega. Lo que no se afloja es el peer: el backend casa la orden por (sesion, op_id)
            # y por el rol que la recibio (bridge.py:610-617).
            if str(r.get("peer") or "") != str(d.get("peer") or ""):
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"result_peer_mismatch:{key[1]}"})
            if r["t_ms"] <= d["t_ms"]:
                out.append({"part": _part_for_time(manifest, d["t_ms"]),
                            "reason": f"result_before_delivery:{key[1]}"})
            if r.get("ack_t") is None:
                # v1.3.15 y v1.3.16 (K-08; §6.1 punto 5): un `/result` sin respuesta es un acuse
                # que falta, salvo el de la identidad cortada de P5 dentro de la ventana de K-08
                # (mandado hasta el cut, sin respuesta o con el 502 del tap, y sin una respuesta del
                # backend antes del cut que pruebe que estaba vivo).
                if not _k08_exempt(r, key, _cut_t):
                    out.append({"part": _part_for_time(manifest, r["t_ms"]),
                                "reason": f"ack_missing:{key[1]}"})
            elif float(r["ack_t"]) < float(r["t_ms"]):
                # v1.3.16 (T2f-15k, §6.1 :555): un acuse en el MISMO ms que su resultado vale.
                # v1.3.16 (T2f-15m, L-03): también un cierre cuya respuesta es anterior a su
                # petición; va antes de la rama del cierre.
                out.append({"part": _part_for_time(manifest, r["t_ms"]),
                            "reason": f"ack_before_result:{key[1]}"})
            elif _tap_close(r):
                # v1.3.16 (T2f-15l, :592): el cierre sin respuesta cuenta como «sin respuesta» si
                # su final no es anterior al cut; si es anterior, rompe como el 502 del tap.
                if _cut_t is not None and float(r["ack_t"]) < float(_cut_t):
                    out.append({"part": _part_for_time(manifest, r["t_ms"]),
                                "reason": f"ack_rejected:{key[1]}"})
                elif not _k08_exempt(r, key, _cut_t):
                    out.append({"part": _part_for_time(manifest, r["t_ms"]),
                                "reason": f"ack_missing:{key[1]}"})
            elif rejected_ack(r):
                if not (is_cut and (cut_resend(r) or _k08_exempt(r, key, _cut_t))):
                    out.append({"part": _part_for_time(manifest, r["t_ms"]),
                                "reason": f"ack_rejected:{key[1]}"})
    for key, rs in results_by_key.items():
        ds = deliveries.get(key) or []
        _ct = cut_meta.get(key, (float("-inf"), ""))[0] if key in cut_keys else None
        for i in range(len(ds), len(rs)):
            r = rs[i]
            # v1.3.16 (T2f-15k, N-01): un `/result` que sobra pasa por las mismas reglas de
            # resultado que uno emparejado antes de eximirlo. Contra las entregas de su
            # (session, op_id); si no casa con ninguna, rompe con el mismo motivo.
            _fails: list[str] = []
            if ds:
                d0 = ds[0]
                if not _query_session_ok(r):
                    _fails.append("query_body_session_mismatch")
                if not _anchor_eq(str(r.get("inst") or ""), str(d0.get("inst") or "")) or \
                        not _anchor_eq(str(r.get("epoch") or ""), str(d0.get("epoch") or "")):
                    _fails.append("result_identity_mismatch")
                if str(r.get("peer") or "") != str(d0.get("peer") or ""):
                    _fails.append("result_peer_mismatch")
                if float(r["t_ms"]) <= float(d0["t_ms"]):
                    _fails.append("result_before_delivery")
            if r.get("ack_t") is not None and float(r["ack_t"]) < float(r["t_ms"]):
                # v1.3.16 (T2f-15m, L-03): también el cierre, no solo las respuestas del backend.
                _fails.append("ack_before_result")
            _ok = not _fails
            _exempt = _ok and (cut_resend(r) or _k08_exempt(r, key, _ct))
            if not _exempt:
                if r.get("ack_t") is None:
                    _fails.append("ack_missing")
                elif _tap_close(r):
                    if _ct is not None and float(r["ack_t"]) < float(_ct):
                        _fails.append("ack_rejected")
                    else:
                        _fails.append("ack_missing")
                elif rejected_ack(r):
                    _fails.append("ack_rejected")
                _fails.append("extra_result")
            for _motive in _fails:
                out.append({"part": _part_for_time(manifest, r["t_ms"]),
                            "reason": f"{_motive}:{key[1]}"})
        if key not in deliveries:
            for r in rs:
                if cut_resend(r):
                    continue
                out.append({"part": _part_for_time(manifest, r["t_ms"]),
                            "reason": f"result_without_delivery:{key[1]}"})
    for st in backend["op_states"]:
        oid = str(st["data"].get("op_id") or "")
        if not oid:
            continue
        t = float(st.get("t_ms") or 0.0)
        if _RD_ID.match(oid):
            out.append({"part": _part_for_time(manifest, t),
                        "reason": f"op_state_for_internal:{oid}"})
            continue
        sess = str(st.get("session") or "")
        if not sess:
            out.append({"part": _part_for_time(manifest, t),
                        "reason": f"op_state_session_unbacked:{oid}"})
            continue
        key = (sess, oid)
        if key not in deliveries:
            out.append({"part": _part_for_time(manifest, t),
                        "reason": f"op_state_without_delivery:{oid}"})
            continue
        state = str(st["data"].get("state") or "")
        reason = str(st["data"].get("reason") or "")
        if _is_terminal(state, reason) and key not in results_by_key and key not in cut_keys:
            out.append({"part": _part_for_time(manifest, t),
                        "reason": f"op_state_without_result:{oid}"})
    return out


def _reconciliation_ok(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                       part: str, after_t: float, before_t: float) -> bool:
    """Reconciliación (§6.1 punto 6, R-02): `state.read` entregado y su `/result` `done` válido.

    No exige ningún evento `reconciliada`: el backend no lo emite para la lectura interna.
    """
    win = _part_window(manifest, part)
    if win is None:
        return False
    session_at = _backend_sessions(tap, backend)
    for d in tap["deliveries"]:
        if d["verb"] != "state.read":
            continue
        # v1.3.9: la lectura de reconciliación es una orden interna (`rd-N`) del backend nuevo, en su
        # sesión y después de su `/hello`.
        if not _RD_ID.match(str(d.get("op_id") or "")):
            continue
        if not (float(win["start_t_ms"]) <= float(d["t_ms"]) <= float(win["end_t_ms"])):
            continue
        if not (after_t < float(d["t_ms"]) < before_t):
            continue
        # v1.3.11 (F-03): la lectura va en la sesión nueva, después del reinicio y de su `/hello`,
        # nunca en la sesión vieja ni antes del reinicio.
        sess = session_at(float(d["t_ms"]))
        prev_sess = session_at(float(after_t) - 1e-6)
        if not sess or sess == prev_sess or str(d.get("session") or "") != sess:
            continue
        if not any(str(h.get("session") or "") == sess and
                   str(h.get("peer") or "") == "server" and
                   _hello_resp_time(h) is not None and
                   float(after_t) < float(_hello_resp_time(h)) < float(d["t_ms"])
                   for h in tap.get("hellos") or []):
            continue
        epoch = str(d.get("epoch") or "")
        if not _HEX32.match(epoch) or epoch != _epoch_at(tap, float(d["t_ms"])):
            continue
        doc_id = str((d.get("args") or {}).get("doc_id") or "")
        # v1.3.13 (T2f-11, C-06): el tamaño del mundo es el del servidor aceptado vigente ANTES de
        # esta lectura (brief:566); un `/hello` rechazado no cuenta (brief:546).
        world_size = _world_size(tap, float(d["t_ms"]))
        for r in tap["results"]:
            if r["op_id"] != d["op_id"] or r["session"] != d["session"] or \
                    r["status"] != "done":
                continue
            if not (float(d["t_ms"]) < float(r["t_ms"]) < before_t):
                continue
            if _valid_read(r.get("read"), doc_id, epoch, world_size):
                return True
    return False


def _server_restart_ok(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                       part: str) -> bool:
    """Reinicio del servidor acreditado (§6.1 punto 8): epoch nuevo, evento y mismo storage.

    v1.3.12 (Sol r4c): el `server_epoch` de la parte no es obligatorio. Si está, tiene que coincidir
    con el epoch del `/hello` nuevo; si no está, el epoch se toma del `/hello` y del `restart`.
    """
    win = _part_window(manifest, part)
    if win is None:
        return False
    storage = manifest.get("f2p", {}).get("storage") if isinstance(manifest.get("f2p"), dict) else {}
    if not isinstance(storage, dict) or str(win.get("storage_id") or "") != str(storage.get("id") or ""):
        return False
    restarts = [r for r in backend["restarts"] if str(r["data"].get("target") or "") == "server" and
                float(win["start_t_ms"]) <= r["t_ms"] <= float(win["end_t_ms"])]
    hellos = [h for h in tap["hellos"] if h["peer"] == "server" and h.get("accepted") and
              _hello_resp_time(h) is not None and
              float(win["start_t_ms"]) <= float(_hello_resp_time(h)) <= float(win["end_t_ms"])]
    if not restarts or not hellos:
        return False
    declared = str(win.get("server_epoch") or "")
    # B1 (ronda 2, brief:1318): por cada `restart` del servidor de la parte, el primer `/hello`
    # aceptado POSTERIOR a ese `restart`, comparado con el último aceptado ANTERIOR a ese mismo
    # `restart`. El mod vuelve a saludar en la misma vida cuando vence el lease
    # (DSBX_Peer.c:882-899), y ese `/hello` repetido puede caer antes del `restart`: el oráculo de
    # 98c7a78 tomaba el primero de la ventana y lo comparaba con el epoch previo a la ventana, y
    # daba INCONCLUSO una partida honesta. El `/hello` repetido no acredita una vida nueva; el que
    # acredita el reinicio es el primero posterior a él.
    for r in restarts:
        rt = float(r["t_ms"])
        after = [h for h in hellos if float(_hello_resp_time(h)) > rt]
        if not after:
            continue
        first_hello = min(after, key=lambda h: float(_hello_resp_time(h)))
        epoch = str(first_hello.get("epoch") or "")
        if not _HEX32.match(epoch):
            continue
        if declared and declared != epoch:
            continue
        # Último `/hello` aceptado anterior a ESE `restart` (no el previo a la ventana de la parte).
        prev_epoch = _epoch_at(tap, rt - 1e-6)
        if prev_epoch == epoch:
            continue
        if str(r["data"].get("epoch") or "") != epoch:
            continue
        return True
    return False


def _witness_windows(probe: dict[str, Any], tap: dict[str, Any], backend: dict[str, Any],
                     manifest: dict[str, Any]) -> dict[str, Any]:
    """Ventanas del testigo (§6.1 punto 7, R-11): una por op, cobertura en el reloj común y
    exclusividad real."""
    expected = (("P1", "control"), ("P2", "apply"), ("P2n", "apply"), ("P3", "apply1"),
                ("P3", "apply2"), ("P4a", "apply1"), ("P4a", "apply2"), ("P4b", "apply"),
                ("P5", "cut"), ("P5", "apply2"))
    missing: list[str] = []
    jobs: list[dict[str, Any]] = []
    for p, stage in expected:
        tag = f"{p}:{stage}"
        job = _witness(probe, tag)
        if job is None:
            missing.append(tag)
            continue
        if _measurement(job, manifest=manifest, probe=probe, part=p, tap=tap) != "":
            missing.append(tag + ":unbacked")
            continue
        jobs.append(job)
        if p == "P1":
            continue
        pwin = _part_window(manifest, p)
        if pwin is None:
            missing.append(tag + ":no_part")
            continue
        # v1.3.13 (Y-04): primera entrega GLOBAL por `(sesión, op_id)`; la op pertenece a la parte
        # de su primera entrega, así que una reentrega en otra parte no desplaza el índice.
        applies = sorted([d for d in _first_deliveries(tap, "scene.apply").values()
                          if float(pwin["start_t_ms"]) <= float(d["t_ms"]) <= float(pwin["end_t_ms"])],
                         key=lambda x: x["t_ms"])
        idx = 1 if stage == "apply2" else 0
        # v1.3.13 (Z-07): la ventana del testigo `P5:apply2` se ata al mismo apply nuevo de Y-03.
        if p == "P5" and stage == "apply2":
            _new_p5 = _p5_new_apply(tap, backend, manifest)
            if _new_p5:
                d = _new_p5[0]
            elif len(applies) <= idx:
                missing.append(tag + ":no_delivery")
                continue
            else:
                d = applies[idx]
        else:
            if len(applies) <= idx:
                missing.append(tag + ":no_delivery")
                continue
            d = applies[idx]
        if float(job["deliver_t"]) >= float(d["t_ms"]):
            missing.append(tag + ":delivery_after_op")
            continue
        if p == "P5" and stage == "cut":
            cuts = [c for c in backend.get("cuts", []) if
                    float(pwin["start_t_ms"]) <= c["t_ms"] <= float(pwin["end_t_ms"])]
            if not cuts:
                missing.append(tag + ":no_cut_event")
                continue
            last_event = min(float(c["t_ms"]) for c in cuts)
            if last_event <= float(d["t_ms"]):
                missing.append(tag + ":cut_before_delivery")
                continue
        else:
            op_events = [float(x["t_ms"]) for x in tap["deliveries"]
                         if x["op_id"] == d["op_id"] and x["session"] == d["session"]]
            op_events += [float(x["t_ms"]) for x in tap["results"]
                          if x["op_id"] == d["op_id"] and x["session"] == d["session"]]
            if not op_events:
                missing.append(tag + ":no_result")
                continue
            last_event = max(op_events)
        if float(job["deliver_t"]) + float(job["window_ms"]) <= last_event:
            missing.append(tag + ":window_too_short")
    # Exclusividad (§6.1 punto 7): ticks solo dentro del mismo epoch; entre epochs, el orden del
    # reloj común (el trabajo anterior se libera antes de entregar el siguiente). Solape → INCONCLUSO.
    ordered = sorted([j for j in probe["jobs"].values() if j["kind"] == "witness" and
                      j.get("deliver_t") is not None], key=lambda j: float(j["deliver_t"]))
    for i, j in enumerate(ordered):
        if i + 1 >= len(ordered):
            continue
        nxt = ordered[i + 1]
        if j.get("epoch") and nxt.get("epoch") and j["epoch"] == nxt["epoch"]:
            start = j.get("start_tick_ms")
            nstart = nxt.get("start_tick_ms")
            if start is not None and _finite(start) and nstart is not None and _finite(nstart):
                end = float(start) + float(j.get("window_ms") or 0.0)
                if end > float(nstart):
                    missing.append(f"{j['tag']}:overlap")
        if j.get("free_t") is None or float(j["free_t"]) >= float(nxt["deliver_t"]):
            missing.append(f"{j['tag']}:not_freed")
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


def _first_deliveries(tap: dict[str, Any], verb: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Primera entrega por `(sesión, op_id)` en TODO el tap (v1.3.13, Y-04).

    Una op pertenece a la parte de su primera entrega; una reentrega en la ventana de otra parte no
    es una op de esa parte. Se usa en todas las búsquedas de etapa por entrega.
    """
    firsts: dict[tuple[str, str], dict[str, Any]] = {}
    for d in tap["deliveries"]:
        if d["verb"] != verb:
            continue
        key = (str(d["session"]), str(d["op_id"]))
        cur = firsts.get(key)
        if cur is None or float(d["t_ms"]) < float(cur["t_ms"]):
            firsts[key] = d
    return firsts


def _p5_new_apply(tap: dict[str, Any], backend: dict[str, Any],
                  manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply nuevo de P5 (v1.3.13, Z-07): un `scene.apply` de una sesión distinta de la que muere,
    posterior al primer `cut`, con el reinicio del backend ya presente. Sin `cut` o sin reinicio,
    devuelve [] y el consumidor conserva su criterio anterior."""
    p5_cuts = [float(c["t_ms"]) for c in backend.get("cuts", [])
               if _part_for_time(manifest, float(c["t_ms"])) == "P5"]
    if not p5_cuts:
        return []
    cut_t = min(p5_cuts)
    dying = _backend_sessions(tap, backend)(cut_t)
    p5_restarts = [r for r in _part_backend_restarts(backend, manifest, "P5")
                   if float(r["t_ms"]) > cut_t]
    if not p5_restarts:
        return []
    return sorted([d for d in _first_deliveries(tap, "scene.apply").values()
                   if _part_for_time(manifest, float(d["t_ms"])) == "P5" and
                   str(d["session"]) != dying and float(d["t_ms"]) > cut_t],
                  key=lambda x: x["t_ms"])


def _cut_cause_ok(tap: dict[str, Any], backend: dict[str, Any],
                  cut_d: dict[str, Any] | None, cut_oid: str, cut_delivery: float,
                  cut_t: float, dying_session: str, term_t: float,
                  cut_res: list[dict[str, Any]]) -> bool:
    """Una causa de W-11b para el terminal de la op cortada (Z-03/Z-04/A-01/A-03).

    Todas las pruebas van en la sesión que muere y antes del primer `cut` de P5.
    """
    # a. un resultado con error aceptado antes del terminal (y antes del cut).
    if any(str(r.get("status") or "") == "error" and
           float(r["t_ms"]) < min(term_t, cut_t) for r in cut_res):
        return True
    # b. parcial/sin_resultado después de la entrega, antes del cut y antes o igual al terminal.
    for st in backend.get("op_states") or []:
        if str(st.get("session") or "") != dying_session:
            continue
        d = st.get("data") or {}
        if str(d.get("op_id") or "") != cut_oid:
            continue
        if (str(d.get("state") or ""), str(d.get("reason") or "")) != \
                ("parcial", "sin_resultado"):
            continue
        t = float(st.get("t_ms") or 0.0)
        if cut_delivery < t < cut_t and t <= term_t:
            return True
    # c. /hello del servidor aceptado, misma instancia y epoch que la entrega, antes del cut y del
    #    terminal, sin un resultado aceptado de la op entre medias (Z-04/A-03).
    if not any(cut_delivery < float(r["t_ms"]) < term_t for r in cut_res):
        cut_inst = str(cut_d.get("inst") or "") if cut_d is not None else ""
        if not cut_inst or cut_inst != _server_inst_at(tap, cut_delivery):
            return False
        cut_epoch = _tap_epoch_for_inst(tap, cut_inst, cut_delivery)
        for h in tap.get("hellos") or []:
            if str(h.get("peer") or "") != "server" or not h.get("accepted"):
                continue
            # v1.3.13 (B-03): la causa c va por la hora de la ACEPTACIÓN, no de la petición.
            _resp_t = h.get("resp_t")
            if _resp_t is None or not _finite(_resp_t):
                continue
            if not (cut_delivery < float(_resp_t) < min(cut_t, term_t)):
                continue
            if str(h.get("inst") or "") != cut_inst:
                continue
            if not _anchor_eq(str(h.get("epoch") or ""), str(cut_epoch or "")):
                continue
            if str(h.get("session") or "") != dying_session:
                continue
            return True
    return False


def _tap_op(tap: dict[str, Any], verb: str, part: str, manifest: dict[str, Any],
            before: float | None = None) -> list[dict[str, Any]]:
    """Entregas de una etapa, deduplicadas por `(sesión, op_id)` con la primera entrega GLOBAL.

    v1.3.12 (X-01): el bridge reentrega una orden sin resultado (retry_ms); una reentrega no es una
    etapa nueva. v1.3.13 (Y-04): la deduplicación va antes del filtro de la ventana; una op
    pertenece a la parte de su primera entrega.
    """
    win = _part_window(manifest, part)
    if win is None:
        return []
    out = []
    for d in _first_deliveries(tap, verb).values():
        if not (float(win["start_t_ms"]) <= float(d["t_ms"]) <= float(win["end_t_ms"])):
            continue
        if before is not None and float(d["t_ms"]) >= before:
            continue
        out.append(d)
    return sorted(out, key=lambda x: x["t_ms"])


def _results_for(tap: dict[str, Any], op_id: str,
                 session: str | None = None) -> list[dict[str, Any]]:
    return sorted([r for r in tap["results"] if r["op_id"] == op_id and
                   (session is None or str(r["session"]) == session)], key=lambda x: x["t_ms"])


def _deliveries_for(tap: dict[str, Any], op_id: str,
                    session: str | None = None) -> list[dict[str, Any]]:
    return sorted([d for d in tap["deliveries"] if d["op_id"] == op_id and
                   (session is None or str(d["session"]) == session)], key=lambda x: x["t_ms"])


def _doc_poses(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return list(doc.get("entities") or [])


def _find_doc_match(row: dict[str, Any], docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """S-14: mismo comparador estricto (< 0,5 m) que el resto de la geometría."""
    for e in docs:
        if str(row.get("class_name")) != str(e["cls"]):
            continue
        if math.hypot(float(row["pos_x_m"]) - float(e["x"]),
                      float(row["pos_z_m"]) - float(e["z"])) < EPS_OBJ_M:
            return e
    return None


def _yaw_delta(a: Any, b: Any) -> float:
    return abs((float(a) - float(b) + 180.0) % 360.0 - 180.0)


def _baseline_ok(census_rows: list[dict[str, Any]], buildings: list[tuple[str, float, float, float]]) -> bool:
    for cls, x, z, yaw in buildings:
        found = False
        for r in census_rows:
            if str(r.get("class_name")) != cls:
                continue
            # S-14: estricto, < 0,5 m; el yaw sigue a 2°.
            if abs(float(r["pos_x_m"]) - x) < 0.5 and abs(float(r["pos_z_m"]) - z) < 0.5 and \
                    _yaw_delta(r.get("yaw_deg"), yaw) <= 2.0:
                found = True
                break
        if not found:
            return False
    return True


BUILDINGS = [
    ("Land_Lunapark_Shooting_Gallery", 6137.06, 7643.80, -128.64),
    ("Land_House_2W01", 6212.85, 7644.65, -138.33),
    ("Land_City_Stand_Grocery", 6137.23, 7702.65, 39.30),
    ("Land_House_2B01", 6184.06, 7715.68, -142.45),
]


def _control_creation(probe: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any] | None:
    """Creación del control persistente al empezar P4a desde su respuesta cruda (R-09, §5.3).

    Sin la respuesta de `per_spawn_raw` con `mode = persistent_control`, validada (punto 1), el
    control no está acreditado y F2P-07 da INCONCLUSO. Se exige clase, `net_id`, posición fuera de la
    zona de F2 y la marca pedida (`health_mark_ratio` 0,845), con salud real; si la sonda da `-1/-1`,
    la marca no es legible.
    """
    for op in probe["ops"].values():
        if op["verb"] != "per_spawn_raw":
            continue
        au = _unpack(op["args"]) if op.get("args") is not None else None
        if not au or str(au[0].get("mode") or "") != "persistent_control":
            continue
        if _stimulus_ok(op, manifest=manifest, probe=probe, part="P4a") != "":
            continue
        u = _unpack(op["read"])
        if not u:
            continue
        s, n, _ = u
        net = str(s.get("net_id") or "")
        if not _valid_net(net):
            continue
        cls = str(s.get("class_name") or "")
        if cls != CONTROL_CLASS:
            continue
        x = float(n.get("pos_x_m") or 0.0)
        z = float(n.get("pos_z_m") or 0.0)
        # Fuera de la zona de F2 (disco de 120 m en el centro del testigo).
        if math.hypot(x - WITNESS_CENTER[0], z - WITNESS_CENTER[1]) <= WITNESS_RADIUS:
            continue
        max_hp = float(n.get("max_hp") or 0.0)
        health_hp = float(n.get("health_hp") or 0.0)
        # `health_mark_ratio` va en los escalares numéricos del estímulo, no en los de texto.
        ratio = float(au[1].get("health_mark_ratio") or 0.0)
        if abs(ratio - CONTROL_RATIO) > 1e-9:
            continue
        # v1.3.11 (F-08): la creación exige salud real con la marca; `-1/-1` no acredita el control.
        if max_hp <= 0 or health_hp <= 0 or \
                abs(health_hp / max_hp - CONTROL_RATIO) > 0.01:
            continue
        return {"class_name": cls, "net_id": net, "pos_x_m": x, "pos_z_m": z,
                "max_hp": max_hp, "health_hp": health_hp}
    return None


def _control_census_ok(probe: dict[str, Any], manifest: dict[str, Any], part: str,
                       creation: dict[str, Any], judged_t: float | None,
                       tap: dict[str, Any] | None = None) -> bool:
    """§5.3 (v1.3.10): el control se reconoce en su censo propio de 30 m.

    Por clase y posición a menos de 0,5 m; si la salud es legible, también por la marca
    `|health_hp / max_hp - 0,845| <= 0,01`; si da `-1/-1`, bastan la clase y la posición.
    v1.3.11 (F-08): el censo propio tiene que ser de la instancia y el epoch vigentes después del
    reinicio; un censo de la instancia anterior no vale.
    Enmienda de identidad (brief:1296-1313): «la instancia y el epoch vigentes» son los de la vida
    del servidor; el censo casa con su vida en `_measurement`, y el `/hello` vigente del producto en
    su entrega tiene que ser de esa misma vida y con su identidad.
    """
    job = _census(probe, f"{part}:control")
    if job is None:
        return False
    if _measurement(job, manifest=manifest, probe=probe, part=part, judged_t=judged_t,
                    fresh=True) != "":
        return False
    if tap is not None:
        deliver_t = job.get("deliver_t")
        if deliver_t is None or not _finite(deliver_t):
            return False
        # v1.3.13 (T2f-11, C-04): la instancia y el epoch del trabajo salen del MISMO `/hello`
        # aceptado vigente en su entrega; un `/hello` rechazado no aporta ninguno de los dos
        # (brief:546, 660, 662).
        # Enmienda de identidad (brief:1296-1313): antes, la `inst` y el epoch del censo iguales a
        # los de ese `/hello` del producto (en el juego nunca lo son). Ahora, ese `/hello` es de la
        # vida del censo (por la hora de su respuesta) y lleva la identidad del producto en ella.
        vig = _server_hello_at(tap, float(deliver_t))
        life = _life_at(probe, float(deliver_t))
        _vig_t = _hello_resp_time(vig) if vig is not None else None
        if vig is None or life is None or not life.get("ok") or not life.get("prod") or \
                _vig_t is None or not (life["lo"] <= float(_vig_t) < life["hi"]) or \
                (str(vig.get("inst") or ""), str(vig.get("epoch") or "")) != tuple(life["prod"]):
            return False
        # v1.3.13 (T2f-12, D-05; brief:660, 662): el `/hello` vigente del control tiene que ser
        # ACEPTADO despues del reinicio del servidor que se juzga, por su respuesta. Un censo de la
        # instancia anterior entregado entre el reinicio y el `/hello` nuevo no vale.
        _vig_rt = _hello_resp_time(vig)
        if judged_t is not None and (_vig_rt is None or _vig_rt <= float(judged_t)):
            return False
    if abs(float(job.get("center_x", 0.0)) - float(creation["pos_x_m"])) > 0.5 or \
            abs(float(job.get("center_z", 0.0)) - float(creation["pos_z_m"])) > 0.5:
        return False
    if abs(float(job.get("radius", 0.0)) - CONTROL_CENSUS_RADIUS_M) > 1e-6:
        return False
    for r in job["rows"]:
        if str(r.get("class_name")) != str(creation["class_name"]):
            continue
        # S-14: estricto, < 0,5 m.
        if math.hypot(float(r["pos_x_m"]) - float(creation["pos_x_m"]),
                      float(r["pos_z_m"]) - float(creation["pos_z_m"])) >= 0.5:
            continue
        max_hp = float(r.get("max_hp") or 0.0)
        health_hp = float(r.get("health_hp") or 0.0)
        if max_hp > 0 and health_hp > 0:
            if abs(health_hp / max_hp - CONTROL_RATIO) > 0.01:
                continue
        return True
    return False


def _foreign_spawns(probe: dict[str, Any], part: str, manifest: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    """Reconstruye los ajenos desde sus respuestas crudas de `per_spawn_raw` (F2P-05/F2P-06).

    Cada estímulo pasa por `_stimulus_ok` (punto 1): sin `deliver`, sin `/hello` previo o fuera de
    la ventana, no cuenta (R-05).
    """
    win = _part_window(manifest, part)
    if win is None:
        return None
    out: dict[str, dict[str, Any]] = {}
    for op in probe["ops"].values():
        if op["verb"] != "per_spawn_raw":
            continue
        if _stimulus_ok(op, manifest=manifest, probe=probe, part=part) != "":
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


def _cleanup_ok(probe: dict[str, Any], manifest: dict[str, Any], part: str) -> int | None:
    win = _part_window(manifest, part)
    if win is None:
        return None
    cleaned = None
    for op in probe["ops"].values():
        if op["verb"] != "per_cleanup_qa":
            continue
        if _stimulus_ok(op, manifest=manifest, probe=probe, part=part) != "":
            continue
        u = _unpack(op["read"])
        if u and _finite(u[1].get("cleaned_raw_n")):
            cleaned = int(u[1]["cleaned_raw_n"])
    return cleaned


def _row_inventory(rows: list[dict[str, Any]], net: str) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(r.get("class_name")), str(r.get("net_id")))
                        for r in rows if str(r.get("parent_net_id") or "") == net))


def _pose_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return _dist2(before, after) > 0.05 or _yaw_delta(before.get("yaw_deg", 0.0),
                                                     after.get("yaw_deg", 0.0)) > 1.0


def _delete_confirm_separation(del_rows: list[dict[str, Any]]) -> float:
    """Separación entre la primera petición y la confirmación del mismo borrado (§6.1 F2P-10).

    Solo se usa el reloj común `t_ms` (R-03): si la línea confirmatoria no tiene una petición previa
    en el mismo `(lid, net_id)`, la separación es 0; nunca se resta un tick del motor.
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
                    break
            if req_t is not None:
                max_sep = max(max_sep, conf_t - req_t)
    return max_sep


def _job_args_ok(job: dict[str, Any]) -> bool:
    """R-15 y S-01: los arranques llevan argumentos completos y los selectores de §5.3."""
    kind = str(job.get("kind") or "")
    u = _unpack(job.get("args")) if isinstance(job.get("args"), dict) else None
    if not u:
        return False
    s, n, _ = u
    if kind == "census":
        if "area_tag" not in s:
            return False
        if not all(k in n for k in ("center_x_m", "center_z_m", "radius_m",
                                    "include_director_b", "select_all_entityai_b")):
            return False
        if float(n.get("select_all_entityai_b", 0.0)) != 1.0 or \
                float(n.get("include_director_b", 0.0)) != 1.0:
            return False
        if abs(float(n.get("center_x_m", 0.0)) - float(job.get("center_x", 0.0))) > 1e-6 or \
                abs(float(n.get("center_z_m", 0.0)) - float(job.get("center_z", 0.0))) > 1e-6 or \
                abs(float(n.get("radius_m", 0.0)) - float(job.get("radius", 0.0))) > 1e-6:
            return False
        return True
    if "witness_tag" not in s:
        return False
    if not all(k in n for k in ("center_x_m", "center_z_m", "radius_m", "window_ms")):
        return False
    return abs(float(n.get("center_x_m", 0.0)) - float(job.get("center_x", 0.0))) <= 1e-6 and \
        abs(float(n.get("center_z_m", 0.0)) - float(job.get("center_z", 0.0))) <= 1e-6 and \
        abs(float(n.get("radius_m", 0.0)) - float(job.get("radius", 0.0))) <= 1e-6 and \
        abs(float(n.get("window_ms", 0.0)) - float(job.get("window_ms", 0.0))) <= 1e-6


def _trace_with_cut_tie(tap_rows: list[dict[str, Any]], backend_rows: list[dict[str, Any]],
                        manifest: dict[str, Any], tap: dict[str, Any],
                        backend: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """v1.3.16 (T2f-15l, §6.1 :599): un solo orden total para el grupo de eventos del ms del `cut`.

    El grupo son los registros crudos del `tap` y los eventos del backend con el mismo `t_ms` que el
    primer `cut` de P5, sin contar el `cut`. Se permutan los registros crudos y se vuelven a pasar
    `_parse_tap` y `_parse_backend` (asi una entrega y la respuesta de su `/poll` quedan juntas), con
    cada respuesta despues de su peticion. Las horas del grupo son `cut + (pos - pos_cut)/(n+2)`.
    Devuelve la traza del orden con menos motivos (o vacia si alguno la da vacia) y si el grupo tiene
    mas de cuatro eventos (INCONCLUSO `tap_tie_group_too_large`).
    """
    # v1.3.16 (T2f-15m, O-2/O-3): el cut de la traza es el primero de P5 de cualquier target (no
    # solo `backend`); la hora es numerica (`_finite`) y un registro con la hora no numerica no
    # entra en el grupo. `data` puede no ser un objeto; no se lee aqui.
    cuts = [c for c in backend.get("cuts") or []
            if _part_for_time(manifest, float(c.get("t_ms") or 0.0)) == "P5"]
    if not cuts:
        return _trace_violations(tap, backend, manifest), False
    cut_t = min(float(c.get("t_ms") or 0.0) for c in cuts)
    cut = next((r for r in backend_rows if r.get("kind") == "cut" and
                _finite(r.get("t_ms")) and float(r["t_ms"]) == cut_t), None)
    if cut is None:
        return _trace_violations(tap, backend, manifest), False
    group: list[tuple[str, dict[str, Any]]] = [
        ("tap", r) for r in tap_rows
        if _finite(r.get("t_ms")) and float(r["t_ms"]) == cut_t]
    group += [("backend", r) for r in backend_rows
              if r is not cut and _finite(r.get("t_ms")) and float(r["t_ms"]) == cut_t]
    if not group:
        return _trace_violations(tap, backend, manifest), False
    if len(group) > 4:
        # v1.3.16 (T2f-15m, L-04): el grupo grande solo deja sin juzgar la traza de P5; las de las
        # otras partes siguen contando.
        base = _trace_violations(tap, backend, manifest)
        return [v for v in base if str(v.get("part") or "") != "P5"], True
    req_pos: dict[int, int] = {}
    pairs: list[tuple[int, int]] = []
    for idx, (kind, row) in enumerate(group):
        if kind == "tap" and row.get("dir") == "req" and _is_int(row.get("req_id")):
            req_pos[int(row["req_id"])] = idx
    for idx, (kind, row) in enumerate(group):
        if kind == "tap" and row.get("dir") == "resp" and _is_int(row.get("req_id")):
            if int(row["req_id"]) in req_pos:
                pairs.append((req_pos[int(row["req_id"])], idx))
    n = len(group) + 1
    best: list[dict[str, Any]] | None = None
    best_len: int | None = None
    for perm in itertools.permutations(range(len(group))):
        for cut_pos in range(len(group) + 1):
            order = list(perm[:cut_pos]) + [-1] + list(perm[cut_pos:])
            place = {g: i for i, g in enumerate(order) if g != -1}
            if any(place[a] >= place[b] for a, b in pairs):
                continue
            times = {}
            for i, g in enumerate(order):
                if g == -1:
                    continue
                times[id(group[g][1])] = cut_t + (i - cut_pos) / (n + 2)
            tap2 = []
            for r in tap_rows:
                if id(r) in times:
                    r2 = copy.deepcopy(r)
                    r2["t_ms"] = times[id(r)]
                    tap2.append(r2)
                else:
                    tap2.append(r)
            be2 = []
            for r in backend_rows:
                if id(r) in times:
                    r2 = copy.deepcopy(r)
                    r2["t_ms"] = times[id(r)]
                    be2.append(r2)
                else:
                    be2.append(r)
            t2 = _parse_tap(tap2)
            b2 = _parse_backend(be2)
            _assign_op_sessions(t2, b2)
            bad = _trace_violations(t2, b2, manifest)
            if not bad:
                return [], False
            if best_len is None or len(bad) < best_len:
                best = bad
                best_len = len(bad)
    return (best or []), False


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
    # v1.3.9: cada `op.state` pertenece a la sesión del tramo entre reinicios del backend.
    _assign_op_sessions(tap, backend)
    manifest_reasons = _validate_manifest(manifest, repo_root, backend, probe)
    if manifest_reasons:
        reasons.extend(sorted(set(manifest_reasons)))
        return gate_core.make_verdict(SPIKE_ID, 2, checks=_checks_as_list(checks),
                                      metrics=metrics, reasons=reasons)
    oracle_reason = _oracle_check_ok(part_dir, manifest, backend)
    if oracle_reason:
        reasons.append(oracle_reason)
        return gate_core.make_verdict(SPIKE_ID, 2, checks=_checks_as_list(checks),
                                      metrics=metrics, reasons=reasons)
    # S-08 (re-congelado de 2026-11-23, brief:1314-1315): sin el validador del backend no se puede
    # juzgar ninguna lectura de reconciliación. Un import que falla es un error de montaje: INCONCLUSO
    # `backend_validator_unavailable`, nunca FALLA (antes daba FALLA en F2P-05 o F2P-08).
    if _backend_validator() is None:
        reasons.append("backend_validator_unavailable")
        return gate_core.make_verdict(SPIKE_ID, 2, checks=_checks_as_list(checks),
                                      metrics=metrics, reasons=reasons)

    _assign_witness_tags(probe, manifest)
    # Enmienda de identidad (brief:1296-1313): vidas del servidor y casado de las identidades de la
    # sonda y del producto en cada una. Las usan todas las mediciones (`_measurement`), el censo del
    # control, F2P-07 y F2P-10. El resumen va a las métricas para diagnosticar un INCONCLUSO.
    probe["lives"] = _server_lives(probe, tap, backend)
    metrics["server_lives"] = _lives_metric(probe["lives"])

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

    def union(tag: str, part: str, judged_t: float | None = None,
              fresh: bool = False) -> dict[str, Any]:
        u = _census_union(probe, manifest, part, tag, judged_t=judged_t, fresh=fresh, tap=tap)
        if not u["ok"]:
            reasons.append("unbacked_rows")
        return u

    # --- traza del producto (§6.1 punto 5, R-10) ---
    # v1.3.16 (T2f-15l, :599): el grupo de eventos del ms del `cut` se resuelve con un solo orden
    # total; si es demasiado grande, INCONCLUSO.
    trace_bad, _tie_too_large = _trace_with_cut_tie(tap_rows, backend_rows, manifest, tap, backend)
    if trace_bad:
        reasons.append("tap_trace_mismatch")

    # --- P1 / P2 base ---
    p1_u = union("P1:base", "P1")
    p1 = {"rows": list(p1_u["rows"].values())} if p1_u["ok"] else None
    baseline_classes = {str(r.get("class_name")) for r in (p1["rows"] if p1 else [])}
    # Enmienda de identidad (brief:1308) y ronda 2 (B3, brief:1319): el censo base de P1 da a
    # comprobaciones de otras vidas (F2P-07 y F2P-09) las clases de la CE en la zona y los `net_id`
    # de la base. Si P1:base no vale por la razón que sea (páginas, frescura, el `/hello` del
    # producto después de su entrega, la vida sin casar...), esas comprobaciones lo usan y no pueden
    # juzgar con él: lo que dependa de la base da INCONCLUSO `baseline_unbacked`, nunca PASA ni un
    # FALLA por la base vacía. `p1` es None exactamente cuando la unión de P1:base no vale; el delta
    # de identidad solo miraba `life_unbound` y una página perdida daba FALLA `extras:` en F2P-09.
    _p1_base_job = _census(probe, "P1:base")
    baseline_bad = p1 is None
    _p1_life_idx = _life_index_at(probe, float(_p1_base_job["deliver_t"])) \
        if _p1_base_job is not None and _finite(_p1_base_job.get("deliver_t")) else None
    p2_u = union("P2:post", "P2", judged_t=_p2_terminal_t(tap, backend, manifest), fresh=True)
    p2 = {"rows": list(p2_u["rows"].values())} if p2_u["ok"] else None
    wit2 = _witness(probe, "P2:apply")
    if wit2 is not None and _measurement(wit2, manifest=manifest, probe=probe, part="P2") != "":
        wit2 = None

    gen2r = _generation_rebuild(probe, manifest, "P2", "apply", doc1)
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
                      math.hypot(float(r["pos_x_m"]) - float(e["x"]),
                                 float(r["pos_z_m"]) - float(e["z"])) < EPS_OBJ_M), None)
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

    # --- F2P-01 (R-08: correspondencia uno a uno con las filas del documento) ---
    p2_apply_ops = _tap_op(tap, "scene.apply", "P2", manifest)
    p2_term = None
    if p2_apply_ops:
        p2_term = _terminal_state(backend, p2_apply_ops[0]["op_id"],
                                  str(p2_apply_ops[0]["session"]))
    kinds1 = {str(e["id"]): str(e["kind"]) for e in doc1["entities"]}
    pose_bad: list[str] = []
    if gen2r["ok"]:
        for lid, net in gen2r["pairs"].items():
            c = p2_u["rows"].get(net)
            if c is None:
                pose_bad.append(f"{lid}:census_missing")
                continue
            if str(c.get("parent_net_id") or "") != "":
                pose_bad.append(f"{lid}:not_root")
                continue
            if kinds1.get(lid) in ("infectado", "animal"):
                if int(c.get("alive_b", 0)) != 1:
                    pose_bad.append(f"{lid}:not_alive")
                continue
            e = next((x for x in doc1["entities"] if str(x["id"]) == lid), None)
            if e is None:
                continue
            if math.hypot(float(c["pos_x_m"]) - float(e["x"]),
                          float(c["pos_z_m"]) - float(e["z"])) >= EPS_OBJ_M:
                pose_bad.append(f"{lid}:pose")
            elif not _finite(c.get("surface_y_m")) or \
                    abs(float(c["pos_y_m"]) - float(c["surface_y_m"])) > SUPPORT_TOL_OBJETO_M:
                pose_bad.append(f"{lid}:unsupported")
    if not (p1 and p2 and wit2 and gen2r["ok"]):
        # v1.3.11 (A-01): una medición no válida da INCONCLUSO `unbacked_rows`.
        if "unbacked_rows" not in reasons:
            reasons.append("unbacked_rows")
        missing("F2P-01", "unbacked_rows")
    elif p2_term is None:
        missing("F2P-01", "no_op_state")
    elif _stage_terminal(manifest, "P2", "apply") is not None and \
            (str(p2_term["data"].get("state") or ""),
             str(p2_term["data"].get("reason") or "")) != _stage_terminal(manifest, "P2", "apply"):
        fail("F2P-01", f"state={p2_term['data'].get('state')}/{p2_term['data'].get('reason')}")
    elif gen2r["unmatched"]:
        fail("F2P-01", "unmatched_doc_rows:" + ",".join(gen2r["unmatched"][:5]))
    elif pose_bad:
        # v1.3.12 (W-06): la pose se juzga antes del INCONCLUSO de la CE; un FALLA independiente no
        # queda tapado por un extra de la CE.
        fail("F2P-01", ";".join(pose_bad[:5]))
    elif gen2r["extras"]:
        # v1.3.11 (F-12): un extra de una clase que la CE crea en la zona no se distingue del botín.
        extra_classes = {str(r.get("class_name")) for r in gen2r["extras"]}
        if extra_classes and extra_classes <= baseline_classes:
            missing("F2P-01", "posible_botin_ce")
        else:
            fail("F2P-01", "extra_births:" + str(len(gen2r["extras"])))
    elif len(gen2r["pairs"]) != 33:
        fail("F2P-01", f"witness_creation_count:{len(gen2r['pairs'])}")
    else:
        nets = list(gen2r["pairs"].values())
        if len(set(nets)) != 33 or not all(_valid_net(n) for n in nets):
            fail("F2P-01", "net_id_invalid_or_duplicate")
        elif set(nets) & base_nets:
            fail("F2P-01", "reuses_baseline_nets")
        elif pose_bad:
            fail("F2P-01", ";".join(pose_bad[:5]))
        else:
            passing("F2P-01")

    # --- F2P-02 (R-01: checkpoint real en read.obs con at == "checkpoint") ---
    if not (wit2 and p2 and wit_ee):
        missing("F2P-02", "missing_witness_or_census")
    else:
        fails: list[str] = []
        for e in doc1["entities"]:
            w = next((r for r in wit_ee if str(r.get("class_name")) == str(e["cls"]) and
                      math.hypot(float(r["pos_x_m"]) - float(e["x"]),
                                 float(r["pos_z_m"]) - float(e["z"])) < EPS_OBJ_M), None)
            if w is None:
                fails.append(f"{e['id']}:not_in_witness")
                continue
            surf = w.get("surface_y_m")
            if not _finite(surf):
                missing("F2P-02", "surface_unbacked")
                break
            # R-13: horizontal contra (x_doc, z_doc) y apoyo en el suelo de la muestra 0.
            # S-14: estricto, < 0,5 m. V-10: 0,1 m en criaturas y 2,0 m en objetos.
            tol = SUPPORT_TOL_CRIATURA_M if e["kind"] in ("infectado", "animal") \
                else SUPPORT_TOL_OBJETO_M
            if math.hypot(float(w["pos_x_m"]) - float(e["x"]),
                          float(w["pos_z_m"]) - float(e["z"])) >= EPS_OBJ_M:
                fails.append(f"{e['id']}:witness_horizontal")
            elif abs(float(w["pos_y_m"]) - float(surf)) > tol:
                fails.append(f"{e['id']}:witness_unsupported")
        else:
            if fails:
                fail("F2P-02", ";".join(fails[:5]))
            else:
                obj_fail = []
                obj_unbacked = False
                for e in doc1["entities"]:
                    if e["kind"] != "objeto":
                        continue
                    w = next((r for r in wit_ee if str(r.get("class_name")) == str(e["cls"]) and
                              math.hypot(float(r["pos_x_m"]) - float(e["x"]),
                                         float(r["pos_z_m"]) - float(e["z"])) < EPS_OBJ_M), None)
                    net = str(w.get("net_id")) if w else ""
                    c = p2_u["rows"].get(net)
                    if c is None:
                        obj_fail.append(f"{e['id']}:census_missing")
                        continue
                    surf_c = c.get("surface_y_m")
                    if not _finite(surf_c):
                        obj_unbacked = True
                        break
                    if math.hypot(float(c["pos_x_m"]) - float(e["x"]),
                                  float(c["pos_z_m"]) - float(e["z"])) >= EPS_OBJ_M:
                        obj_fail.append(f"{e['id']}:census_horizontal")
                    elif abs(float(c["pos_y_m"]) - float(surf_c)) > SUPPORT_TOL_OBJETO_M:
                        obj_fail.append(f"{e['id']}:census_unsupported")
                if obj_unbacked:
                    missing("F2P-02", "surface_unbacked")
                elif obj_fail:
                    fail("F2P-02", ";".join(obj_fail[:5]))
                elif not witness_reliable:
                    missing("F2P-02", "witness_not_final")
                else:
                    cre_fail: list[str] = []
                    cre_missing: list[str] = []
                    _check_creatures(manifest, tap, backend, wit2, p2_u, doc1, doc_counter,
                                     cre_fail, cre_missing)
                    if cre_fail:
                        fail("F2P-02", ";".join(cre_fail[:5]))
                    elif cre_missing:
                        missing("F2P-02", ";".join(cre_missing[:5]))
                    else:
                        passing("F2P-02")

    # --- F2P-03 ---
    variant = str((manifest.get("f2p") or {}).get("p2n_variant") or "")
    expected = {"create_failed_first": ("fallido", "create_failed"),
                "create_failed_after": ("parcial", "compensada"),
                "displaced": ("fallido", "lectura_no_cumple")}[variant]
    p2n_apply = _tap_op(tap, "scene.apply", "P2n", manifest)
    # v1.3.12 (X-02, §5.2 línea 241 y §6.1 punto 2 líneas 493 y 497): P2n termina con la escena 1
    # limpia otra vez (reset), y ese reset es una etapa positiva con terminal `observado`/``.
    p2n_resets = _tap_op(tap, "scene.reset", "P2n", manifest)
    p2n_reset_term = _terminal_state(backend, p2n_resets[0]["op_id"],
                                     str(p2n_resets[0]["session"])) if p2n_resets else None
    # v1.3.13 (Z-06): el censo `P2n:clean` juzga el apply negativo y el reset de limpieza; su
    # frescura va contra el máximo de los dos terminales (se conserva el del apply y se añade el
    # del reset, como en Y-07).
    _p2n_apply_t = _terminal_t(tap, backend, p2n_apply[0]["op_id"],
                               str(p2n_apply[0]["session"])) if p2n_apply else None
    _p2n_reset_t = float(p2n_reset_term["t_ms"]) if p2n_reset_term is not None else None
    _p2n_judged = max([_t for _t in (_p2n_apply_t, _p2n_reset_t) if _t is not None],
                      default=None)
    p2n_u = union("P2n:clean", "P2n", judged_t=_p2n_judged, fresh=True)
    p2n_census = {"rows": list(p2n_u["rows"].values())} if p2n_u["ok"] else None
    if not p2n_apply:
        missing("F2P-03", "stimulus_not_observed")
    else:
        oid = p2n_apply[0]["op_id"]
        sess = str(p2n_apply[0]["session"])
        res = _results_for(tap, oid, sess)
        st = _terminal_state(backend, oid, sess)
        wit2n = _witness(probe, "P2n:apply")
        if wit2n is not None and _measurement(wit2n, manifest=manifest, probe=probe,
                                              part="P2n") != "":
            wit2n = None
        if not res:
            missing("F2P-03", "no_result")
        elif st is None:
            missing("F2P-03", "no_op_state")
        elif wit2n is None and not res:
            missing("F2P-03", "stimulus_unbacked")
        elif str(st["data"].get("state")) != expected[0] or str(st["data"].get("reason") or "") != expected[1]:
            fail("F2P-03", f"state={st['data'].get('state')}/{st['data'].get('reason')}")
        elif not p2n_resets:
            missing("F2P-03", "reset_not_observed")
        elif p2n_reset_term is None:
            missing("F2P-03", "reset_no_op_state")
        elif (str(p2n_reset_term["data"].get("state") or ""),
              str(p2n_reset_term["data"].get("reason") or "")) != ("observado", ""):
            fail("F2P-03", f"reset_state={p2n_reset_term['data'].get('state')}/"
                           f"{p2n_reset_term['data'].get('reason')}")
        elif p2n_census is None:
            # v1.3.13 (Y-07, §6.1 punto 1 líneas 473-475): el censo `P2n:clean` contrasta el reset
            # de limpieza; si se entregó antes de su terminal, la medición no es fresca.
            _p2n_clean = _census(probe, "P2n:clean")
            _stale = (_p2n_clean is not None and _p2n_judged is not None and
                      _finite(_p2n_clean.get("deliver_t")) and
                      float(_p2n_clean["deliver_t"]) <= float(_p2n_judged))
            missing("F2P-03", "unbacked_rows" if _stale else "census_missing")
        else:
            gen2n = _generation_rebuild(probe, manifest, "P2n", "apply", doc1)
            if not gen2n["ok"]:
                missing("F2P-03", "stimulus_unbacked")
            else:
                # R-08/V-12: la generación se sigue por `net_id`, nunca por pose; tampoco en P2n.
                # El reset de P2n borra también la generación viva de P2.
                gen2 = _generation_rebuild(probe, manifest, "P2", "apply", doc1)
                previous = set(gen2["nets"]) if gen2["ok"] else set()
                known = set(gen2n["nets"]) | previous
                leftovers = [net for net in known if net in p2n_u["rows"]]
                # Una entidad de una clase del documento en su pose de documento, fuera de la
                # generación, sigue siendo un extra del censo (no se busca la identidad por pose).
                pose_extra = [f"{r.get('class_name')}@{r.get('net_id')}"
                              for r in p2n_census["rows"]
                              if str(r.get("net_id")) not in known and
                              _find_doc_match(r, doc1_entities) is not None]
                if leftovers:
                    fail("F2P-03", "census_still_has_generation:" + ",".join(sorted(leftovers)[:5]))
                elif pose_extra:
                    fail("F2P-03", "census_extra_at_doc_pose:" + ",".join(pose_extra[:5]))
                else:
                    passing("F2P-03")

    # --- F2P-04 ---
    p2_apply = _tap_op(tap, "scene.apply", "P2", manifest)
    if not p2_apply or not p2 or wit2 is None:
        missing("F2P-04", "missing_apply")
    else:
        oid = p2_apply[0]["op_id"]
        sess = str(p2_apply[0]["session"])
        dels = _deliveries_for(tap, oid, sess)
        res = _results_for(tap, oid, sess)
        if len(dels) < 2:
            fail("F2P-04", "single_delivery")
        elif len(res) < 2:
            fail("F2P-04", "single_result")
        elif len({d.get("session") for d in dels[:2]}) != 1 or \
                len({r.get("session") for r in res[:2]}) != 1:
            fail("F2P-04", "session_mismatch")
        elif res[0].get("dup") is not False or res[1].get("dup") is not True:
            fail("F2P-04", "dup_flag")
        elif _ttl_ms(manifest) is None:
            # V-16: sin `params.ttl_ms` no se puede comprobar la retención → INCONCLUSO.
            missing("F2P-04", "ttl_missing")
        elif float(dels[1]["t_ms"]) - float(dels[0]["t_ms"]) > float(_ttl_ms(manifest)):
            fail("F2P-04", "outside_retention")
        else:
            doc_classes = {str(e["cls"]) for e in doc1["entities"]}
            births = ([r for r in gen2r["births"].values()
                       if str(r.get("class_name")) in doc_classes] if gen2r["ok"] else [])
            if gen2r["unmatched"]:
                fail("F2P-04", "unmatched:" + ",".join(gen2r["unmatched"][:5]))
            elif gen2r["extras"]:
                # v1.3.11 (F-12): el extra de una clase CE da INCONCLUSO en F2P-04, nunca FALLA.
                extra_classes = {str(r.get("class_name")) for r in gen2r["extras"]}
                if extra_classes and extra_classes <= baseline_classes:
                    missing("F2P-04", "posible_botin_ce")
                else:
                    fail("F2P-04", f"witness_births:{len(births)}")
            elif len(births) != 33:
                fail("F2P-04", f"witness_births:{len(births)}")
            else:
                passing("F2P-04")

    # --- F2P-05 ---
    # v1.3.13 (gemela de Z-06/Z-01): `P3:pre_reset` juzga la generación de apply1 y apply2; su
    # frescura va contra el máximo de los dos terminales, no solo el de apply2.
    _p3_apply1_t = _apply_terminal_t(tap, backend, manifest, "P3", 0)
    _p3_apply2_t = _apply_terminal_t(tap, backend, manifest, "P3", 1)
    _p3_pre_judged = max([_t for _t in (_p3_apply1_t, _p3_apply2_t) if _t is not None],
                         default=None)
    pre3_u = union("P3:pre_reset", "P3", judged_t=_p3_pre_judged, fresh=True)
    post31_u = union("P3:post_reset1", "P3",
                     judged_t=_p3_terminal_t(tap, backend, manifest, "reset1"), fresh=True)
    post32_u = union("P3:post_reset2", "P3",
                     judged_t=_p3_terminal_t(tap, backend, manifest, "reset2"), fresh=True)
    pre3 = {"rows": list(pre3_u["rows"].values())} if pre3_u["ok"] else None
    post31 = {"rows": list(post31_u["rows"].values())} if post31_u["ok"] else None
    post32 = {"rows": list(post32_u["rows"].values())} if post32_u["ok"] else None
    wit3 = _witness(probe, "P3:apply1")
    wit3b = _witness(probe, "P3:apply2")
    if not (pre3 and post31 and post32 and p2):
        if not pre3:
            # v1.3.13 (gemela): si el censo no es fresco frente a apply1/apply2, motivo de frescura.
            _pre3_job = _census(probe, "P3:pre_reset")
            _stale = (_pre3_job is not None and _p3_pre_judged is not None and
                      _finite(_pre3_job.get("deliver_t")) and
                      float(_pre3_job["deliver_t"]) <= float(_p3_pre_judged))
            missing("F2P-05", "unbacked_rows" if _stale else "missing_p3_census")
        else:
            missing("F2P-05", "missing_p3_census")
    else:
        gen3 = _generation_rebuild(probe, manifest, "P3", "apply1", doc1)
        gen3b = _generation_rebuild(probe, manifest, "P3", "apply2", doc2)
        gen2 = _generation_rebuild(probe, manifest, "P2", "apply", doc1)
        scene1_nets = set(gen3["pairs"].values()) if gen3["ok"] else set()
        scene2_map = dict(gen3b["pairs"]) if gen3b["ok"] else {}
        scene2_nets = set(scene2_map.values())
        stim_unbacked = _stimulus_unbacked(probe, manifest, "P3")
        foreigners = _foreign_spawns(probe, "P3", manifest) or {}
        # V-18: sin ningún estímulo crudo de ajenos, F2P-05 es INCONCLUSO, no FALLA.
        stimuli_missing = not foreigners
        foreign_nets = set(foreigners)
        def own_with_foreign(rows: list[dict[str, Any]]) -> set[str]:
            """Propias presentes que son contenedores con algo ajeno en ese censo (F-07)."""
            present = {net for net in scene1_nets
                       if any(str(r.get("net_id")) == net for r in rows)}
            return {net for net in present
                    if any(str(r.get("net_id")) in foreign_nets and
                           str(r.get("parent_net_id") or "") == net for r in rows)}

        fails = []
        if not gen3["ok"] or not gen3b["ok"]:
            fails.append("generation_missing")
        # S-03: completa, disjunta y con raíces reales (sin padre también en el censo).
        if gen3["ok"]:
            if gen3["unmatched"]:
                fails.append("p3_unmatched:" + ",".join(gen3["unmatched"][:5]))
            if len(gen3["pairs"]) != len(doc1["entities"]):
                fails.append(f"p3_generation={len(gen3['pairs'])}")
        if gen3b["ok"]:
            if gen3b["unmatched"]:
                fails.append("p3b_unmatched:" + ",".join(gen3b["unmatched"][:5]))
        if gen2["ok"] and scene1_nets & set(gen2["nets"]):
            fails.append("p3_reuses_p2_nets")
        if scene1_nets & scene2_nets:
            fails.append("p3_scene_nets_overlap")
        for r in post31["rows"]:
            net = str(r.get("net_id"))
            if net in (scene1_nets | scene2_nets) and str(r.get("parent_net_id") or "") != "":
                fails.append(f"{net}:not_root")
                break
        if len(scene2_map) != len(doc2["entities"]):
            fails.append("scene2_not_found")
        # v1.3.11 (F-07): tras cada reset, las retenidas se recalculan desde cero y se contrastan
        # con el conjunto permitido completo; una raíz de más (p. ej. 1:201) es FALLA.
        present31 = {net for net in scene1_nets
                     if any(str(r.get("net_id")) == net for r in post31["rows"])}
        exp31 = own_with_foreign(pre3["rows"])
        if present31 != exp31 or len(exp31) != 1:
            fails.append("retained_set1")
        present32 = {net for net in scene1_nets
                     if any(str(r.get("net_id")) == net for r in post32["rows"])}
        exp32 = own_with_foreign(post31["rows"])
        if present32 != exp32 or len(exp32) != 1:
            fails.append("retained_set2")
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
        applies3 = _tap_op(tap, "scene.apply", "P3", manifest)
        apply_states = [_terminal_state(backend, d["op_id"], str(d["session"])) for d in applies3]
        for idx, stage in ((0, "apply1"), (1, "apply2")):
            exp = _stage_terminal(manifest, "P3", stage)
            if exp is not None:
                if len(apply_states) <= idx or apply_states[idx] is None:
                    fails.append(f"{stage}_no_op_state")
                else:
                    st = apply_states[idx]
                    pair = (str(st["data"].get("state") or ""),
                            str(st["data"].get("reason") or ""))
                    if pair != exp:
                        fails.append(f"{stage}_state={pair[0]}/{pair[1]}")
        resets = _tap_op(tap, "scene.reset", "P3", manifest)
        states = [_terminal_state(backend, d["op_id"], str(d["session"])) for d in resets]
        if len(resets) < 2 or any(s is None for s in states[:2]):
            fails.append("reset_no_op_state")
        else:
            for idx, stage in ((0, "reset1"), (1, "reset2")):
                exp = _stage_terminal(manifest, "P3", stage)
                st = states[idx]
                pair = (str(st["data"].get("state") or ""),
                        str(st["data"].get("reason") or ""))
                if exp is not None and pair != exp:
                    fails.append(f"{stage}_state={pair[0]}/{pair[1]}")
        # v1.3.11 (F-03): reconciliación tras CADA reinicio del backend de P3, en la sesión nueva y
        # después de su `/hello`, antes de la primera entrega de escena del tramo.
        p3_restarts = _part_backend_restarts(backend, manifest, "P3")
        recon_missing = len(p3_restarts) < 2
        recon_fail: list[str] = []
        session_at = _backend_sessions(tap, backend)
        for rs in p3_restarts:
            rt = float(rs["t_ms"])
            if not _backend_restart_accredited(tap, backend, rt):
                recon_missing = True
                continue
            new_sess = session_at(rt + 1e-6)
            first = [float(d["t_ms"]) for d in tap["deliveries"]
                     if d["verb"] in ("scene.apply", "scene.reset") and
                     str(d["session"]) == new_sess and float(d["t_ms"]) > rt]
            if not first:
                recon_fail.append(f"no_scene_delivery_after_restart:{rt}")
                continue
            if not _reconciliation_ok(tap, backend, manifest, "P3", rt, min(first)):
                recon_fail.append(f"no_reconciliation_after_restart:{rt}")
        # R-12: el segundo reset compara solo las identidades seguidas (propias retenidas, ajenas y
        # escena 2); el botín nuevo de la CE no cuenta.
        nets31 = {str(r.get("net_id")) for r in post31["rows"]}
        followed = (scene1_nets & nets31) | foreign_nets | scene2_nets
        nets32 = {str(r.get("net_id")) for r in post32["rows"]}
        missing_followed = sorted(followed - nets32)
        if missing_followed:
            fails.append("second_reset_diff:" + ",".join(missing_followed[:5]))
        else:
            for net in sorted(followed):
                a = next((r for r in post31["rows"] if str(r.get("net_id")) == net), None)
                b = next((r for r in post32["rows"] if str(r.get("net_id")) == net), None)
                if a is None or b is None or str(a.get("class_name")) != str(b.get("class_name")) or \
                        _pose_changed(a, b) or \
                        str(a.get("parent_net_id") or "") != str(b.get("parent_net_id") or "") or \
                        _row_inventory(post31["rows"], net) != _row_inventory(post32["rows"], net):
                    fails.append(f"{net}:second_reset_changed")
                    break
        # v1.3.12 (W-05, §6.1 punto 3): la generación de CADA apply de P3 está viva en el censo
        # válido siguiente (P3:pre_reset), por identidad y con la pose de §6 en los objetos.
        for _gen, _doc, _label in ((gen3, doc1, "apply1"), (gen3b, doc2, "apply2")):
            if not _gen["ok"]:
                continue
            _kinds = {str(e["id"]): str(e["kind"]) for e in _doc["entities"]}
            for _lid, _net in _gen["pairs"].items():
                row = next((r for r in pre3["rows"] if str(r.get("net_id")) == _net), None)
                if row is None:
                    fails.append(f"{_label}:{_lid}:census_missing")
                    continue
                # v1.3.12 (X-05, §6.1 punto 3 línea 502): raíz es sin padre en la muestra 0 y
                # también sin padre en el censo siguiente.
                if str(row.get("parent_net_id") or "") != "":
                    fails.append(f"{_label}:{_lid}:not_root")
                    continue
                if _kinds.get(_lid) in ("infectado", "animal"):
                    if int(row.get("alive_b", 0)) != 1 or int(row.get("ai_agent_b", 0)) != 1:
                        fails.append(f"{_label}:{_lid}:alive_or_ai")
                    continue
                w = _gen["births"][_net]
                if math.hypot(float(row["pos_x_m"]) - float(w["pos_x_m"]),
                              float(row["pos_z_m"]) - float(w["pos_z_m"])) >= EPS_OBJ_M:
                    fails.append(f"{_label}:{_lid}:pose")
                elif not _finite(row.get("surface_y_m")) or \
                        abs(float(row["pos_y_m"]) - float(row["surface_y_m"])) > SUPPORT_TOL_OBJETO_M:
                    fails.append(f"{_label}:{_lid}:unsupported")
        if stim_unbacked:
            reasons.append("unbacked_rows")
            missing("F2P-05", "unbacked_rows")
        elif stimuli_missing:
            missing("F2P-05", "stimulus_missing")
        elif recon_missing:
            missing("F2P-05", "restart_unbacked")
        elif recon_fail:
            fail("F2P-05", ";".join(recon_fail[:5]))
        elif fails:
            if "generation_missing" in fails:
                missing("F2P-05", ";".join(fails[:5]))
            else:
                fail("F2P-05", ";".join(fails[:5]))
        else:
            passing("F2P-05")

    # --- F2P-06 ---
    clean3c_u = union("P3c:clean", "P3c",
                      judged_t=_p3_terminal_t(tap, backend, manifest, "clean"), fresh=True)
    clean3c = {"rows": list(clean3c_u["rows"].values())} if clean3c_u["ok"] else None
    if not (clean3c and pre3 and p2):
        missing("F2P-06", "missing_census")
    else:
        gen3 = _generation_rebuild(probe, manifest, "P3", "apply1", doc1)
        gen3b = _generation_rebuild(probe, manifest, "P3", "apply2", doc2)
        scene2_map = dict(gen3b["pairs"]) if gen3b["ok"] else {}
        # V-06/S-13: la generación propia son los pares con el documento, no los nacimientos de
        # clases del documento que no casan (botín de la CE).
        scene1_nets = set(gen3["pairs"].values()) if gen3["ok"] else set()
        alive_scene1 = {str(r.get("net_id")) for r in clean3c["rows"]} & scene1_nets
        stim_unbacked = _stimulus_unbacked(probe, manifest, "P3") or \
            _stimulus_unbacked(probe, manifest, "P3c")
        fails = []
        if not gen3b["ok"] or len(scene2_map) != len(doc2["entities"]):
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
        foreigners = _foreign_spawns(probe, "P3", manifest)
        # V-18: sin estímulos crudos de ajenos o de limpieza, F2P-06 es INCONCLUSO, no FALLA.
        stimuli_missing = not foreigners or len(foreigners) != 2
        if not stimuli_missing:
            for net, f in foreigners.items():
                if f["mode"] == "foreign_in_container":
                    if not f["obs_parent_net_id"]:
                        fails.append(f"{net}:obs_parent_missing")
                    elif f["obs_parent_net_id"] != f["target_net_id"]:
                        fails.append(f"{net}:obs_parent_mismatch")
        cleaned = _cleanup_ok(probe, manifest, "P3c")
        if cleaned is None:
            stimuli_missing = True
        elif foreigners and cleaned != len(foreigners):
            fails.append(f"cleaned_raw_n={cleaned}")
        if foreigners and not stimuli_missing:
            # v1.3.11 (F-07): lo declarado frente a lo observado. Cada ajeno que la limpieza dice
            # haber borrado falta en el censo válido de después.
            clean_nets = {str(r.get("net_id")) for r in clean3c["rows"]}
            for net in sorted(foreigners):
                if net in clean_nets:
                    fails.append(f"{net}:cleanup_still_alive")
        clean_ops = _tap_op(tap, "scene.reset", "P3c", manifest)
        clean_term = _terminal_state(backend, clean_ops[0]["op_id"],
                                     str(clean_ops[0]["session"])) if clean_ops else None
        clean_state_bad = ""
        if clean_term is None:
            clean_state_bad = "no_op_state"
        else:
            exp = _stage_terminal(manifest, "P3c", "clean")
            pair = (str(clean_term["data"].get("state") or ""),
                    str(clean_term["data"].get("reason") or ""))
            if exp is not None and pair != exp:
                clean_state_bad = f"state={pair[0]}/{pair[1]}"
        if stim_unbacked:
            reasons.append("unbacked_rows")
            missing("F2P-06", "unbacked_rows")
        elif clean_state_bad:
            fail("F2P-06", clean_state_bad)
        elif stimuli_missing:
            missing("F2P-06", "stimulus_missing")
        elif not gen3["ok"]:
            missing("F2P-06", "generation_unbacked")
        elif fails:
            fail("F2P-06", ";".join(fails[:5]))
        else:
            passing("F2P-06")

    # --- F2P-07 ---
    b4_u = union("P4b:post_restart", "P4b",
                 judged_t=_part_restart_t(backend, manifest, "P4b"), fresh=True)
    # v1.3.13 (Z-02): el censo `P4c:post_restart` también tiene que ser posterior al terminal del
    # reset de la escena 1 (la etapa de Y-08), no solo al restart del servidor.
    p4c_resets = _tap_op(tap, "scene.reset", "P4c", manifest)
    p4c_restart_t = _part_restart_t(backend, manifest, "P4c")
    _doc1_id = str(doc1.get("doc_id") or "")
    _doc2_id = str(doc2.get("doc_id") or "")
    p4c_stage = next((d for d in p4c_resets
                      if str((d.get("args") or {}).get("doc_id") or "") == _doc1_id and
                      (p4c_restart_t is None or float(d["t_ms"]) < p4c_restart_t)), None)
    p4c_stage_term = _terminal_state(backend, p4c_stage["op_id"],
                                     str(p4c_stage["session"])) if p4c_stage else None
    _c4_reset_t = float(p4c_stage_term["t_ms"]) if p4c_stage_term is not None else None
    _c4_judged = max([_t for _t in (p4c_restart_t, _c4_reset_t) if _t is not None],
                     default=None)
    c4_u = union("P4c:post_restart", "P4c", judged_t=_c4_judged, fresh=True)
    b4 = {"rows": list(b4_u["rows"].values())} if b4_u["ok"] else None
    c4 = {"rows": list(c4_u["rows"].values())} if c4_u["ok"] else None
    if not (b4 and c4):
        if not c4:
            # v1.3.13 (Z-02): si el censo no es fresco frente al reset, el motivo es el de frescura.
            _c4_job = _census(probe, "P4c:post_restart")
            _stale = (_c4_job is not None and _c4_judged is not None and
                      _finite(_c4_job.get("deliver_t")) and
                      float(_c4_job["deliver_t"]) <= float(_c4_judged))
            missing("F2P-07", "unbacked_rows" if _stale else "missing_census")
        else:
            missing("F2P-07", "missing_census")
    else:
        fails = []
        botin: list[str] = []
        control_ok = True
        creation = _control_creation(probe, manifest)
        restart_b = _part_restart_t(backend, manifest, "P4b")
        restart_c = _part_restart_t(backend, manifest, "P4c")
        epoch_b = _epoch_at(tap, restart_b - 1e-6) if restart_b else ""
        epoch_c = _epoch_at(tap, restart_c - 1e-6) if restart_c else ""
        last_b = _last_known_positions(probe, manifest, restart_b, doc1, doc2,
                                       epoch=epoch_b) if restart_b else {}
        last_c = _last_known_positions(probe, manifest, restart_c, doc1, doc2,
                                       epoch=epoch_c) if restart_c else {}
        # Enmienda de identidad (brief:1308): las últimas posiciones conocidas (R-09) salen de la vida
        # anterior a cada reinicio del servidor. Si esa vida no casa, sus censos no cuentan en
        # `_last_known_positions` y la reaparición no se puede juzgar entera. Un reinicio que falta
        # lo sigue juzgando `_server_restart_ok` (`restart_unbacked`), no esta regla.
        _lives_before_ok = all(
            _rt is None or bool((_life_at(probe, float(_rt) - 1e-6) or {}).get("ok"))
            for _rt in (restart_b, restart_c))
        # Lo que solo da FALLA porque la base de P1 no lo exime (criatura o clase de la CE) no se
        # puede decidir sin la base: con su vida sin casar va aparte y da INCONCLUSO.
        unbound_hits: list[str] = []
        # §6.1 punto 9 (S-13): las clases que la CE crea en la zona son las del censo de P1 fuera de
        # toda generación. El control persistente está fuera de la zona y no exime a nada dentro.
        ce_classes_in_zone = set(baseline_classes)
        creature_classes = {str(e["cls"]) for e in docs
                            if str(e.get("kind")) in ("infectado", "animal")}
        for j, last in ((b4, last_b), (c4, last_c)):
            for r in j["rows"]:
                cls = str(r.get("class_name"))
                ai = int(r.get("ai_agent_b", 0))
                # v1.3.12 (W-04): el criterio de F-09 para ai=1 se AÑADE a las reglas de pose; no
                # exime a las demás. Una criatura restaurada sin IA o muerta sigue las de pose.
                if cls in creature_classes and ai == 1:
                    if cls in ce_classes_in_zone:
                        botin.append(f"{r.get('net_id')}:{cls}:criatura")
                    elif baseline_bad:
                        unbound_hits.append(f"{r.get('net_id')}:{cls}:criatura")
                    else:
                        fails.append(f"{r.get('net_id')}:creature_reappeared")
                if _exact_reappearance(r, last):
                    fails.append(f"{r.get('net_id')}:reappeared")
                    continue
                if cls not in scene1_classes:
                    continue
                if _near_last_known(r, last):
                    if cls in ce_classes_in_zone:
                        botin.append(f"{r.get('net_id')}:{cls}")
                    elif baseline_bad:
                        unbound_hits.append(f"{r.get('net_id')}:{cls}")
                    else:
                        fails.append(f"{r.get('net_id')}:near_last_known")
        if creation is None:
            control_ok = False
        else:
            control_ok = _control_census_ok(probe, manifest, "P4b", creation, restart_b,
                                            tap=tap) and \
                _control_census_ok(probe, manifest, "P4c", creation, restart_c, tap=tap)
        # W-01: el reset de P4c es una etapa positiva y su terminal esperado es observado.
        # v1.3.13 (§5.2 línea 246): P4c resetea solo la escena 1; la escena 2 sigue aplicada en el
        # backend y no se resetea. v1.3.13 (Y-08, §6.1 punto 2 línea 493 y F2P-07 línea 378): la
        # etapa es el `scene.reset` con el `doc_id` de la escena 1 entregado ANTES del restart del
        # servidor de P4c; si no lo hay, FALLA. Los demás resets se juzgan por su terminal (X-03).
        p4c_state_bad = ""
        p4c_reset_fuera = False
        if not p4c_resets:
            p4c_state_bad = "no_op_state"
        elif p4c_stage is None:
            p4c_state_bad = "p4c_reset_escena1_ausente"
        else:
            exp = _stage_terminal(manifest, "P4c", "reset")
            for _idx, _d in enumerate(p4c_resets):
                # v1.3.13 (T2f-12, X-03; §5.2 linea 246): P4c resetea solo la escena 1. Un reset
                # de la escena 2 esta fuera de guion: INCONCLUSO propio, sin juzgar su terminal.
                if _doc2_id and str((_d.get("args") or {}).get("doc_id") or "") == _doc2_id:
                    p4c_reset_fuera = True
                    continue
                _term = _terminal_state(backend, _d["op_id"], str(_d["session"]))
                _label = "" if _idx == 0 else f"reset{_idx + 1}_"
                if _term is None:
                    p4c_state_bad = f"{_label}no_op_state"
                    break
                pair = (str(_term["data"].get("state") or ""),
                        str(_term["data"].get("reason") or ""))
                if exp is not None and pair != exp:
                    p4c_state_bad = f"{_label}state={pair[0]}/{pair[1]}"
                    break
        # W-05/W-06: la generación de P4b se juzga antes del INCONCLUSO de la CE; así un FALLA
        # independiente no queda tapado.
        gen4b = _generation_rebuild(probe, manifest, "P4b", "apply", doc1)
        gen4a2 = _generation_rebuild(probe, manifest, "P4a", "apply2", doc1)
        p4b_apply_ops = _tap_op(tap, "scene.apply", "P4b", manifest)
        p4b_term = _terminal_state(backend, p4b_apply_ops[0]["op_id"],
                                   str(p4b_apply_ops[0]["session"])) if p4b_apply_ops else None
        p4b_t = float(p4b_term["t_ms"]) if p4b_term is not None else None
        post4b_u = union("P4b:post_apply", "P4b", judged_t=p4b_t, fresh=True)
        post4b = {"rows": list(post4b_u["rows"].values())} if post4b_u["ok"] else None
        gen4_bad: list[str] = []
        if gen4b["ok"] and post4b is not None:
            by_net = {str(r.get("net_id")): r for r in post4b["rows"]}
            kinds = {str(e["id"]): str(e["kind"]) for e in doc1["entities"]}
            for lid, net in gen4b["pairs"].items():
                c = by_net.get(net)
                if c is None:
                    gen4_bad.append(f"{lid}:census_missing")
                    continue
                if str(c.get("parent_net_id") or "") != "":
                    gen4_bad.append(f"{lid}:not_root")
                    continue
                if kinds.get(lid) in ("infectado", "animal"):
                    if int(c.get("alive_b", 0)) != 1 or int(c.get("ai_agent_b", 0)) != 1:
                        gen4_bad.append(f"{lid}:alive_or_ai")
                    continue
                w = gen4b["births"][net]
                if math.hypot(float(c["pos_x_m"]) - float(w["pos_x_m"]),
                              float(c["pos_z_m"]) - float(w["pos_z_m"])) >= EPS_OBJ_M:
                    gen4_bad.append(f"{lid}:pose")
                elif not _finite(c.get("surface_y_m")) or \
                        abs(float(c["pos_y_m"]) - float(c["surface_y_m"])) > SUPPORT_TOL_OBJETO_M:
                    gen4_bad.append(f"{lid}:unsupported")
        if fails or gen4_bad:
            fail("F2P-07", ";".join((fails + gen4_bad)[:5]))
        elif p4c_state_bad:
            # M2 (ronda 2, brief:1319): el terminal acreditado de P4c no depende de la base ni de la
            # vida de la sonda; se juzga antes del guardián para que un FALLA independiente decida.
            fail("F2P-07", p4c_state_bad)
        elif botin:
            missing("F2P-07", "posible_botin_ce:" + ";".join(botin[:5]))
        elif unbound_hits or baseline_bad or not _lives_before_ok:
            # Enmienda de identidad (brief:1308) y ronda 2 (B3, brief:1319): F2P-07 usa la base de P1
            # y los censos de la vida anterior a cada reinicio; si la base no vale por la razón que
            # sea o esas vidas no casan, INCONCLUSO, nunca PASA. Va después de los FALLA que no
            # dependen de ellas (el terminal de P4c y el botín de la CE ya se han juzgado).
            _reason = "baseline_unbacked" if (unbound_hits or baseline_bad) else "server_life_unbound"
            missing("F2P-07", _reason +
                    (":" + ";".join(unbound_hits[:5]) if unbound_hits else ""))
        elif not _server_restart_ok(tap, backend, manifest, "P4b") or \
                not _server_restart_ok(tap, backend, manifest, "P4c"):
            missing("F2P-07", "restart_unbacked")
        elif not control_ok:
            missing("F2P-07", "persistent_control_missing")
        elif p4c_reset_fuera:
            missing("F2P-07", "p4c_reset_fuera_de_guion")
        else:
            if p4b_term is None:
                missing("F2P-07", "p4b_no_op_state")
            elif _stage_terminal(manifest, "P4b", "apply") is not None and \
                    (str(p4b_term["data"].get("state") or ""),
                     str(p4b_term["data"].get("reason") or "")) != _stage_terminal(manifest, "P4b", "apply"):
                fail("F2P-07", f"p4b_state={p4b_term['data'].get('state')}/{p4b_term['data'].get('reason')}")
            elif not gen4b["ok"]:
                missing("F2P-07", "p4b_generation_unbacked")
            elif gen4b["unmatched"]:
                fail("F2P-07", "p4b_unmatched:" + ",".join(gen4b["unmatched"][:5]))
            elif gen4b["extras"]:
                extra_classes = {str(r.get("class_name")) for r in gen4b["extras"]}
                if extra_classes and extra_classes <= baseline_classes:
                    missing("F2P-07", "posible_botin_ce")
                else:
                    fail("F2P-07", f"p4b_extras={len(gen4b['extras'])}")
            elif len(gen4b["pairs"]) != len(doc1["entities"]):
                fail("F2P-07", f"p4b_generation={len(gen4b['pairs'])}")
            elif post4b is None:
                missing("F2P-07", "p4b_post_census_unbacked")
            else:
                epoch4b = _generation_epoch(probe, "P4b", "apply")
                epoch4a2 = _generation_epoch(probe, "P4a", "apply2")
                if epoch4b == epoch4a2 and gen4a2["ok"] and \
                        set(gen4b["nets"]) & set(gen4a2["nets"]):
                    # v1.3.11 (F-11): la disjunción vale dentro del mismo epoch; un `net_id`
                    # repetido en otro epoch es otra entidad.
                    fail("F2P-07", "p4b_reuses_p4a_nets")
                else:
                    passing("F2P-07")

    # --- F2P-08 ---
    p4a_apply = _tap_op(tap, "scene.apply", "P4a", manifest)
    a1_term = _terminal_state(backend, p4a_apply[0]["op_id"],
                              str(p4a_apply[0]["session"])) if p4a_apply else None
    a1_t = float(a1_term["t_ms"]) if a1_term is not None else None
    reset_ops = _tap_op(tap, "scene.reset", "P4a", manifest)
    reset_term = _terminal_state(backend, reset_ops[0]["op_id"],
                                 str(reset_ops[0]["session"])) if reset_ops else None
    apply2_term = None
    if len(p4a_apply) > 1:
        apply2_term = _terminal_state(backend, p4a_apply[1]["op_id"],
                                      str(p4a_apply[1]["session"]))
    # v1.3.13 (Z-01): el censo `P4a:post_apply2` juzga el apply2 y el «sin restos» del reset;
    # su frescura va contra el máximo de sus dos terminales.
    _p4a_apply2_t = float(apply2_term["t_ms"]) if apply2_term is not None else None
    _p4a_reset_t = float(reset_term["t_ms"]) if reset_term is not None else None
    # Si falta uno de los dos terminales, el censo no se puede contrastar: INCONCLUSO.
    if _p4a_apply2_t is None or _p4a_reset_t is None:
        _p4a_judged = None
    else:
        _p4a_judged = max(_p4a_apply2_t, _p4a_reset_t)
    p4a_u = union("P4a:post_apply2", "P4a", judged_t=_p4a_judged, fresh=True)
    p4a_c = {"rows": list(p4a_u["rows"].values())} if p4a_u["ok"] else None
    rs = _part_restarts(tap, backend, manifest, "P4a")
    if not (p4a_c and p4a_apply and rs):
        if not p4a_c:
            # v1.3.13 (Z-01): si el censo no es fresco, el motivo es el de frescura.
            _p4a_job = _census(probe, "P4a:post_apply2")
            _stale = (_p4a_job is not None and _p4a_judged is not None and
                      _finite(_p4a_job.get("deliver_t")) and
                      float(_p4a_job["deliver_t"]) <= float(_p4a_judged))
            missing("F2P-08", "unbacked_rows" if _stale else "missing_restart_or_apply")
        else:
            missing("F2P-08", "missing_restart_or_apply")
    else:
        # v1.3.12 (W-02): tras CADA reinicio del backend de P4a, reconciliación en la sesión nueva
        # y antes de la primera entrega de escena (apply o reset) del tramo.
        session_at = _backend_sessions(tap, backend)
        recon_missing = False
        recon_bad: list[str] = []
        for rs_ in rs:
            rt = float(rs_["t_ms"])
            if not _backend_restart_accredited(tap, backend, rt):
                recon_missing = True
                continue
            new_sess = session_at(rt + 1e-6)
            first = [float(d["t_ms"]) for d in tap["deliveries"]
                     if d["verb"] in ("scene.apply", "scene.reset") and
                     str(d["session"]) == new_sess and float(d["t_ms"]) > rt]
            if not first:
                recon_bad.append(f"no_scene_delivery_after_restart:{rt}")
                continue
            if not _reconciliation_ok(tap, backend, manifest, "P4a", rt, min(first)):
                recon_bad.append(f"no_reconciliation_before_scene:{rt}")
        stage_bad: list[str] = []
        for label, term, exp in (("apply1", a1_term, _stage_terminal(manifest, "P4a", "apply1")),
                                 ("reset", reset_term, _stage_terminal(manifest, "P4a", "reset")),
                                 ("apply2", apply2_term, _stage_terminal(manifest, "P4a", "apply2"))):
            if exp is None:
                continue
            if term is None:
                stage_bad.append(f"{label}_no_op_state")
                continue
            pair = (str(term["data"].get("state") or ""),
                    str(term["data"].get("reason") or ""))
            if pair != exp:
                stage_bad.append(f"{label}_state={pair[0]}/{pair[1]}")
        if recon_missing:
            missing("F2P-08", "restart_unbacked")
        elif recon_bad:
            fail("F2P-08", ";".join(recon_bad[:5]))
        elif stage_bad:
            fail("F2P-08", ";".join(stage_bad[:5]))
        else:
            # R-08/R-12/S-04: la generación del apply nuevo de P4a se sigue por identidad, no por
            # pose. Los objetos comparan pose; las criaturas, identidad y vida. Sin restos del apply
            # anterior tras el reset.
            gen4 = _generation_rebuild(probe, manifest, "P4a", "apply2", doc1)
            gen4_prev = _generation_rebuild(probe, manifest, "P4a", "apply1", doc1)
            # v1.3.11 (F-06): la generación de P4a:apply1 también tiene que ser completa y estar
            # viva en el censo válido siguiente a ese apply.
            post1_u = union("P4a:post_apply1", "P4a", judged_t=a1_t, fresh=True)
            post1 = {"rows": list(post1_u["rows"].values())} if post1_u["ok"] else None
            if not gen4["ok"]:
                missing("F2P-08", "generation_missing")
            elif not gen4_prev["ok"]:
                missing("F2P-08", "generation_missing_apply1")
            elif gen4_prev["unmatched"]:
                fail("F2P-08", "apply1_unmatched:" + ",".join(gen4_prev["unmatched"][:5]))
            elif len(gen4_prev["pairs"]) != len(doc1["entities"]):
                fail("F2P-08", f"apply1_generation={len(gen4_prev['pairs'])}")
            elif post1 is None:
                missing("F2P-08", "apply1_census_unbacked")
            else:
                kinds = {str(e["id"]): str(e["kind"]) for e in doc1["entities"]}
                bad: list[str] = []
                by_net1 = {str(r.get("net_id")): r for r in post1["rows"]}
                for lid, net in gen4_prev["pairs"].items():
                    c = by_net1.get(net)
                    if c is None:
                        bad.append(f"{lid}:apply1_census_missing")
                        continue
                    # v1.3.12 (X-05, §6.1 punto 3 línea 502): también sin padre en el censo.
                    if str(c.get("parent_net_id") or "") != "":
                        bad.append(f"{lid}:apply1_not_root")
                        continue
                    if kinds.get(lid) in ("infectado", "animal"):
                        if int(c.get("alive_b", 0)) != 1:
                            bad.append(f"{lid}:apply1_not_alive")
                        continue
                    w = gen4_prev["births"][net]
                    # v1.3.13 (Y-01, F2P-08 línea 676 y §6.1 punto 3 línea 510): primero el apoyo
                    # de §6 (línea 630); después la misma pose 3D frente al nacimiento (< 0,5 m).
                    if not _finite(c.get("surface_y_m")) or \
                            abs(float(c["pos_y_m"]) - float(c["surface_y_m"])) > SUPPORT_TOL_OBJETO_M:
                        bad.append(f"{lid}:apply1_unsupported")
                    elif _dist(c, float(w["pos_x_m"]), float(w["pos_y_m"]),
                               float(w["pos_z_m"])) >= EPS_OBJ_M:
                        bad.append(f"{lid}:apply1_pose")
                by_net = {str(r.get("net_id")): r for r in p4a_c["rows"]}
                if gen4["unmatched"]:
                    bad.append("unmatched:" + ",".join(gen4["unmatched"][:5]))
                ce_extra = bool(gen4["extras"]) and \
                    all(str(r.get("class_name")) in baseline_classes for r in gen4["extras"])
                if gen4["extras"] and not ce_extra:
                    bad.append("extras:" + str(len(gen4["extras"])))
                if gen4_prev["ok"] and set(gen4_prev["nets"]) & set(by_net):
                    bad.append("leftovers:" + str(len(set(gen4_prev["nets"]) & set(by_net))))
                for lid, net in gen4["pairs"].items():
                    c = by_net.get(net)
                    if c is None:
                        bad.append(f"{lid}:census_missing")
                        continue
                    if str(c.get("parent_net_id") or "") != "":
                        bad.append(f"{lid}:not_root")
                        continue
                    if kinds.get(lid) in ("infectado", "animal"):
                        if int(c.get("alive_b", 0)) != 1 or int(c.get("ai_agent_b", 0)) != 1:
                            bad.append(f"{lid}:alive_or_ai")
                        continue
                    w = gen4["births"][net]
                    # v1.3.13 (Y-01): primero el apoyo de §6; después la pose 3D frente al nacimiento
                    # (< 0,5 m), como en 0536ae4. La horizontal sola no basta.
                    if not _finite(c.get("surface_y_m")) or \
                            abs(float(c["pos_y_m"]) - float(c["surface_y_m"])) > SUPPORT_TOL_OBJETO_M:
                        bad.append(f"{lid}:unsupported")
                    elif _dist(c, float(w["pos_x_m"]), float(w["pos_y_m"]),
                               float(w["pos_z_m"])) >= EPS_OBJ_M:
                        bad.append(f"{lid}:pose")
                if bad:
                    fail("F2P-08", ";".join(bad[:5]))
                elif ce_extra:
                    missing("F2P-08", "posible_botin_ce")
                else:
                    passing("F2P-08")

    # --- F2P-09 (R-11: corte acreditado por el runner, no por el reinicio) ---
    p5_applies = _tap_op(tap, "scene.apply", "P5", manifest)
    p5_cuts = [c for c in backend.get("cuts", []) if
               (_part_window(manifest, "P5") is not None and
                float(_part_window(manifest, "P5")["start_t_ms"]) <= c["t_ms"] <=
                float(_part_window(manifest, "P5")["end_t_ms"]))]
    # v1.3.13 (Z-07): el censo P5:post_apply se ata al mismo apply nuevo de Y-03 (sesión distinta
    # de la que muere, posterior al cut). Sin cut, o sin reinicio del backend, se conserva el
    # criterio anterior por índice.
    _p5_new = _p5_new_apply(tap, backend, manifest)
    if p5_cuts and _p5_new:
        _p5_judged = _terminal_t(tap, backend, _p5_new[0]["op_id"],
                                 str(_p5_new[0]["session"]))
    else:
        _p5_judged = _apply_terminal_t(tap, backend, manifest, "P5", 1)
    p5_u = union("P5:post_apply", "P5", judged_t=_p5_judged, fresh=True)
    p5c = {"rows": list(p5_u["rows"].values())} if p5_u["ok"] else None
    # B4 (ronda 2, brief:1320): la reutilización de `net_id` se mira dentro de una misma vida. El
    # motor recicla los `net_id` al reiniciar el servidor; entre vidas distintas un `net_id` igual no
    # dice nada. P5 está en otra vida que la base de P1 en la partida automática (vida 3 frente a 1).
    _p5_job = _census(probe, "P5:post_apply")
    _p5_life_idx = _life_index_at(probe, float(_p5_job["deliver_t"])) \
        if _p5_job is not None and _finite(_p5_job.get("deliver_t")) else None
    _same_life_base = _p1_life_idx is not None and _p5_life_idx is not None and \
        _p1_life_idx == _p5_life_idx
    wit5 = _witness(probe, "P5:cut")
    if wit5 is not None and _measurement(wit5, manifest=manifest, probe=probe, part="P5",
                                        tap=tap) != "":
        wit5 = None
    wit5b = _witness(probe, "P5:apply2")
    if wit5b is not None and _measurement(wit5b, manifest=manifest, probe=probe, part="P5",
                                          tap=tap) != "":
        wit5b = None
    if not (p5c and wit5 and wit5b and p5_applies and p5_cuts):
        # v1.3.13 (Z-07): con `cut`, un censo no fresco da el motivo de frescura del evaluador;
        # un censo ausente o no acreditado por otra causa conserva `missing_cut_evidence`.
        _p5_job = _census(probe, "P5:post_apply")
        _stale = (not p5c and p5_cuts and _p5_job is not None and _p5_judged is not None and
                  _finite(_p5_job.get("deliver_t")) and
                  float(_p5_job["deliver_t"]) <= float(_p5_judged))
        missing("F2P-09", "unbacked_rows" if _stale else "missing_cut_evidence")
    else:
        gen5 = _generation_rebuild(probe, manifest, "P5", "cut", doc1)
        gen5b = _generation_rebuild(probe, manifest, "P5", "apply2", doc1)
        cut_t = min(float(c["t_ms"]) for c in p5_cuts)
        k = _k_before_cut(probe, gen5, cut_t, str(wit5.get("inst") or ""))
        # v1.3.9: la op cortada es el último `scene.apply` entregado antes del `cut`, en la sesión
        # del backend que muere. No se infiere de un terminal ni se le exige terminal.
        dying_session = _backend_sessions(tap, backend)(cut_t)
        cut_candidates = [d for d in p5_applies if d["session"] == dying_session and
                          float(d["t_ms"]) <= cut_t]
        cut_d = max(cut_candidates, key=lambda x: x["t_ms"]) if cut_candidates else None
        cut_oid = str(cut_d["op_id"]) if cut_d is not None else ""
        cut_delivery = float(cut_d["t_ms"]) if cut_d is not None else 0.0
        # Una respuesta cuenta solo si su acuse fue aceptado; el reenvío rechazado al backend nuevo
        # no es una resolución (v1.3.9, punto 5).
        cut_res = [r for r in _results_for(tap, cut_oid, dying_session)
                   if r.get("ack_ok") is True and _is_int(r.get("ack_http")) and
                   200 <= int(r["ack_http"]) < 300] if cut_oid else []
        # v1.3.13 (W-11b, §6.1 punto 2 líneas 495-498 y punto 5 líneas 556-557): la op cortada de
        # P5 no tiene terminal. Si aparece uno suyo, solo se acepta con una causa probada en la
        # sesión que muere y anterior a su `t_ms`:
        #   a. un `/result` con `status: "error"` que ese backend aceptó (acuse 2xx y `ok: true`);
        #   b. un `op.state` exactamente `parcial/sin_resultado`, anterior o igual al terminal;
        #   c. un `/hello` del servidor aceptado en el tap, después de la entrega y antes del
        #      terminal, sin un resultado aceptado de la op entre medias.
        # Un reenvío rechazado (409/400) o un `restart` del servidor solo no son causa.
        cut_term_bad = ""
        if cut_oid:
            # v1.3.13 (A-02, §6.1 punto 2 línea 498): se juzgan TODOS los terminales de la op
            # cortada, no solo el último. El primero que no sea `observado/reconciliada` con una
            # causa da FALLA; más de un terminal también.
            _cut_terms = [st for st in backend.get("op_states") or []
                          if str(st["data"].get("op_id") or "") == cut_oid and
                          str(st.get("session") or "") == dying_session and
                          _is_terminal(str(st["data"].get("state") or ""),
                                       str(st["data"].get("reason") or ""))]
            _cut_terms.sort(key=lambda x: float(x["t_ms"]))
            if _cut_terms:
                for _t in _cut_terms:
                    _state = str(_t["data"].get("state") or "")
                    _reason = str(_t["data"].get("reason") or "")
                    _term_t = float(_t["t_ms"])
                    # v1.3.13 (A-01): ni el terminal ni sus causas pueden ser posteriores al cut.
                    if _term_t >= cut_t or (_state, _reason) != ("observado", "reconciliada") or \
                            not _cut_cause_ok(tap, backend, cut_d, cut_oid, cut_delivery,
                                              cut_t, dying_session, _term_t, cut_res):
                        cut_term_bad = f"cut_op_terminal={_state}/{_reason}"
                        break
                if not cut_term_bad and len(_cut_terms) > 1:
                    cut_term_bad = f"cut_op_terminals={len(_cut_terms)}"
        # v1.3.11 (F-03): el reinicio del backend tras el corte se acredita con su `restart` y un
        # `/hello` de sesión nueva. Si no se acredita, INCONCLUSO; si se acredita y falta la
        # lectura o va antes del reinicio o en la sesión vieja, FALLA.
        p5_restarts = [r for r in _part_backend_restarts(backend, manifest, "P5")
                       if float(r["t_ms"]) > cut_t]
        # v1.3.13 (Y-03/Z-07): con reinicio del backend, el apply nuevo es el mismo que usa el censo
        # y la ventana `P5:apply2`: un `scene.apply` de una sesión distinta de la que muere. Sin
        # reinicio se conserva el comportamiento anterior (la parte da INCONCLUSO de todos modos).
        if p5_restarts:
            new_apply = _p5_new
        else:
            new_apply = [d for d in p5_applies if float(d["t_ms"]) > cut_t]
        if not gen5["ok"] or not gen5b["ok"]:
            missing("F2P-09", "generation_unbacked")
        elif k == 0:
            # §6.1 F2P-09: si ningún nacimiento de la generación cortada es anterior al corte con
            # su ancla, el estímulo no ocurrió antes del corte.
            missing("F2P-09", "p5_sin_efecto")
        elif cut_d is None:
            fail("F2P-09", "no_cut_delivery")
        elif cut_res:
            fail("F2P-09", "cut_op_had_result")
        elif cut_term_bad:
            fail("F2P-09", cut_term_bad)
        elif cut_t <= cut_delivery:
            fail("F2P-09", "cut_before_delivery")
        elif not new_apply:
            missing("F2P-09", "no_new_apply")
        else:
            # v1.3.12 (W-02): tras CADA reinicio del backend posterior al corte, reconciliación en
            # la sesión nueva y antes de la primera entrega de escena (apply o reset) del tramo.
            session_at = _backend_sessions(tap, backend)
            recon_missing = not p5_restarts
            recon_bad: list[str] = []
            for rs_ in p5_restarts:
                rt = float(rs_["t_ms"])
                if not _backend_restart_accredited(tap, backend, rt):
                    recon_missing = True
                    continue
                new_sess = session_at(rt + 1e-6)
                first = [float(d["t_ms"]) for d in tap["deliveries"]
                         if d["verb"] in ("scene.apply", "scene.reset") and
                         str(d["session"]) == new_sess and float(d["t_ms"]) > rt]
                if not first:
                    recon_bad.append(f"no_scene_delivery_after_restart:{rt}")
                    continue
                if not _reconciliation_ok(tap, backend, manifest, "P5", rt, min(first)):
                    recon_bad.append(f"no_reconciliation_before_scene:{rt}")
            new_apply_d = new_apply[0]
            apply2_term = _terminal_state(backend, str(new_apply_d["op_id"]),
                                          str(new_apply_d["session"]))
            stage_bad = ""
            if apply2_term is None:
                stage_bad = "no_op_state"
            else:
                exp = _stage_terminal(manifest, "P5", "apply2")
                pair = (str(apply2_term["data"].get("state") or ""),
                        str(apply2_term["data"].get("reason") or ""))
                if exp is not None and pair != exp:
                    stage_bad = f"state={pair[0]}/{pair[1]}"
            if recon_missing:
                missing("F2P-09", "restart_unbacked")
            elif recon_bad:
                # §6.1 punto 6: reinicio acreditado y falta la lectura (o va antes o en la sesión
                # vieja) es FALLA.
                fail("F2P-09", ";".join(recon_bad[:5]))
            elif stage_bad:
                fail("F2P-09", stage_bad)
            else:
                # S-03/S-04/V-03: la generación nueva sale de su testigo, completa y disjunta;
                # las criaturas se siguen por identidad y vida, sin comparar pose.
                bad = []
                kinds = {str(e["id"]): str(e["kind"]) for e in doc1["entities"]}
                if gen5b["unmatched"]:
                    bad.append("unmatched:" + ",".join(gen5b["unmatched"][:5]))
                ce_extra = bool(gen5b["extras"]) and \
                    all(str(r.get("class_name")) in baseline_classes for r in gen5b["extras"])
                if gen5b["extras"] and not ce_extra:
                    bad.append(f"extras={len(gen5b['extras'])}")
                if len(gen5b["pairs"]) != len(doc1["entities"]):
                    bad.append(f"generation={len(gen5b['pairs'])}")
                new_nets = set(gen5b["pairs"].values())
                if gen5["ok"] and new_nets & set(gen5["nets"]):
                    bad.append("reuses_cut_nets")
                if _same_life_base and new_nets & base_nets:
                    bad.append("reuses_baseline_nets")
                p5_by_net = {str(r.get("net_id")): r for r in p5c["rows"]}
                live = 0
                for lid, net in gen5b["pairs"].items():
                    c = p5_by_net.get(net)
                    if c is None:
                        bad.append(f"{lid}:census_missing")
                        continue
                    if str(c.get("parent_net_id") or "") != "":
                        bad.append(f"{lid}:not_root")
                        continue
                    if int(c.get("alive_b", 0)) != 1:
                        bad.append(f"{lid}:not_alive")
                        continue
                    if kinds.get(lid) in ("infectado", "animal"):
                        if int(c.get("ai_agent_b", 0)) != 1:
                            bad.append(f"{lid}:no_ai")
                            continue
                    else:
                        # v1.3.11 (F-06): la generación viva de cada apply conserva la pose de §6 en
                        # los objetos; un objeto desplazado 10 m es FALLA.
                        w = gen5b["births"][net]
                        if math.hypot(float(c["pos_x_m"]) - float(w["pos_x_m"]),
                                      float(c["pos_z_m"]) - float(w["pos_z_m"])) >= EPS_OBJ_M:
                            bad.append(f"{lid}:pose")
                            continue
                        if not _finite(c.get("surface_y_m")) or \
                                abs(float(c["pos_y_m"]) - float(c["surface_y_m"])) > SUPPORT_TOL_OBJETO_M:
                            bad.append(f"{lid}:unsupported")
                            continue
                    live += 1
                cut_present = [net for net in (set(gen5["nets"]) if gen5["ok"] else set())
                               if net in p5_by_net and int(p5_by_net[net].get("alive_b", 0)) == 1]
                if cut_present:
                    bad.append("cut_leftovers:" + ",".join(sorted(cut_present)[:5]))
                # S-03: una raíz de más dentro de la cobertura es un extra de P5 (33 + K). Las clases
                # que la CE crea en la zona (las del censo de P1) no se distinguen del botín (§6.1.9).
                extra_at_pose = []
                for net, r in p5_by_net.items():
                    if (_same_life_base and net in base_nets) or net in new_nets or \
                            (gen5["ok"] and net in gen5["nets"]):
                        continue
                    cls = str(r.get("class_name"))
                    if cls not in scene1_classes or cls in baseline_classes:
                        continue
                    if str(r.get("parent_net_id") or "") != "":
                        continue
                    if int(r.get("alive_b", 0)) == 1:
                        extra_at_pose.append(net)
                if extra_at_pose:
                    bad.append("extras:" + ",".join(sorted(extra_at_pose)[:5]))
                if baseline_bad:
                    # Enmienda de identidad (brief:1308) y ronda 2 (B3, brief:1319): si la base de
                    # P1 no vale por la razón que sea, un extra no se distingue del botín de la CE
                    # ni de la base, y la reutilización de la base no se puede ver. Esos motivos no
                    # deciden; los demás FALLA, sí. El orden de ahora se conserva.
                    bad = [b for b in bad
                           if not str(b).startswith(("extras=", "extras:", "reuses_baseline_nets"))]
                if bad:
                    fail("F2P-09", ";".join(bad[:5]))
                elif baseline_bad:
                    missing("F2P-09", "baseline_unbacked")
                elif ce_extra:
                    missing("F2P-09", "posible_botin_ce")
                elif live != len(doc1["entities"]):
                    fail("F2P-09", f"total={live}")
                else:
                    passing("F2P-09")

    # --- F2P-10 ---
    if not del_rows:
        missing("F2P-10", "no_delete_lines")
    else:
        fails = []
        gaps = []
        max_confirm = _delete_confirm_separation(del_rows)
        census_jobs = [j for j in probe["jobs"].values() if j["kind"] == "census"]
        # v1.3.11 (F-02): el tipo sale de lo observado y de la fila del documento con la que casó
        # su nacimiento; nunca del prefijo de un `lid`.
        net_kind: dict[tuple[str, str], str] = {}
        for p, s, d in (("P2", "apply", doc1), ("P2n", "apply", doc1),
                        ("P3", "apply1", doc1), ("P3", "apply2", doc2),
                        ("P4a", "apply1", doc1), ("P4a", "apply2", doc1),
                        ("P4b", "apply", doc1), ("P5", "cut", doc1), ("P5", "apply2", doc1)):
            gen = _generation_rebuild(probe, manifest, p, s, d)
            if not gen["ok"]:
                continue
            # Enmienda de identidad (brief:1307): el epoch con que se juzga la generación es el del
            # producto en la vida de su testigo, el mismo con que se buscan los censos de abajo.
            ge = _job_epoch(probe, _witness(probe, f"{p}:{s}"))
            kinds = {str(e["id"]): str(e["kind"]) for e in d["entities"]}
            for lid, net in gen["pairs"].items():
                net_kind[(ge, net)] = kinds.get(lid, "")

        def creature_covered(u: dict[str, Any], pos: tuple[float, float],
                             last_tick: float | None, v_max: float) -> bool:
            """§6.1 punto 4 (F-02): un ÚNICO componente cubre el disco de incertidumbre con SU Δt."""
            if last_tick is None:
                return False
            for comp in u["components"]:
                st = comp.get("snap_tick_ms")
                if not _finite(st):
                    continue
                dt_s = (float(st) - float(last_tick)) / 1000.0
                if dt_s < 0:
                    continue
                required = v_max * dt_s + 2.0
                cx, cz = comp["center"]
                if math.hypot(pos[0] - cx, pos[1] - cz) + required <= comp["radius"] + 1e-9:
                    return True
            return False

        for line in del_rows:
            net = f"{int(line.get('net_high', 0))}:{int(line.get('net_low', 0))}"
            t = float(line.get("t_ms") or 0.0)
            part = _part_for_time(manifest, t)
            win = _part_window(manifest, part)
            if win is None:
                gaps.append(f"{net}:no_part")
                continue
            # S-10: el epoch es por evento, no el del manifest de la parte.
            epoch = _epoch_at(tap, t)
            if not _HEX32.match(epoch):
                gaps.append(f"{net}:no_epoch")
                continue
            # Última posición válida anterior al borrado (mismo epoch), validada por la UNIÓN.
            # Enmienda de identidad (brief:1307): el epoch de cada censo es el del producto en su
            # vida (`_job_epoch`), no el `server_epoch` de la sonda, que en el juego es otro UUID.
            prev_tags = sorted({str(j["tag"]) for j in census_jobs
                                if ":disk:" not in str(j["tag"]) and
                                _job_epoch(probe, j) == epoch and
                                j.get("part") == part and
                                j.get("deliver_t") is not None and float(j["deliver_t"]) < t},
                               key=lambda tag: max(float(j["deliver_t"]) for j in census_jobs
                                                   if str(j["tag"]) == tag), reverse=True)
            if not prev_tags:
                gaps.append(f"{net}:no_position")
                continue
            pu = _census_union(probe, manifest, part, prev_tags[0], tap=tap)
            if not pu["ok"]:
                gaps.append(f"{net}:unbacked_rows")
                continue
            last_row = pu["rows"].get(net)
            if last_row is None:
                # S-12: la posición del documento nunca hace de posición observada.
                gaps.append(f"{net}:no_position")
                continue
            pos = (float(last_row["pos_x_m"]), float(last_row["pos_z_m"]))
            last_tick = pu["row_tick"].get(net)
            # Siguiente censo válido posterior al borrado, del mismo epoch (el del producto en la
            # vida del censo; enmienda de identidad, brief:1307).
            next_tags = sorted({str(j["tag"]) for j in census_jobs
                                if ":disk:" not in str(j["tag"]) and
                                _job_epoch(probe, j) == epoch and
                                j.get("part") == part and
                                j.get("deliver_t") is not None and float(j["deliver_t"]) > t},
                               key=lambda tag: min(float(j["deliver_t"]) for j in census_jobs
                                                   if str(j["tag"]) == tag))
            if not next_tags:
                gaps.append(f"{net}:no_next_census")
                continue
            nu = _census_union(probe, manifest, part, next_tags[0], judged_t=t, fresh=True, tap=tap)
            if not nu["ok"]:
                gaps.append(f"{net}:unbacked_rows")
                continue
            present = net in nu["rows"]
            lid = str(line.get("lid") or "")
            doc_kind = net_kind.get((epoch, net), "")
            observed_creature = int(last_row.get("ai_agent_b", 0)) == 1
            if doc_kind in ("infectado", "animal"):
                if not observed_creature:
                    gaps.append(f"{net}:kind_mismatch")
                    continue
                is_creature = True
                v_max = V_MAX_INFECTADO if doc_kind == "infectado" else V_MAX_ANIMAL
            elif doc_kind == "objeto":
                if observed_creature:
                    gaps.append(f"{net}:kind_mismatch")
                    continue
                is_creature = False
                v_max = 0.0
            else:
                is_creature = observed_creature
                v_max = V_MAX_INFECTADO if lid.startswith("zmb-") else V_MAX_ANIMAL

            def covered() -> bool:
                if is_creature:
                    return creature_covered(nu, pos, last_tick, v_max)
                return _coverage_status(pos, nu["disks"]) == "deep"

            if int(line.get("deleted_confirmed_b", 0)) == 1:
                if present:
                    fails.append(f"{net}:confirmed_but_alive")
                elif not covered():
                    gaps.append(f"{net}:coverage_gap")
            if int(line.get("delete_failed_b", 0)) == 1:
                if not present:
                    if covered():
                        fails.append(f"{net}:failed_but_missing")
                    else:
                        gaps.append(f"{net}:coverage_gap")
        metrics["delete_confirm_max_ms"] = round(max_confirm, 3)
        if fails:
            fail("F2P-10", ";".join(fails[:5]))
        elif gaps:
            missing("F2P-10", ";".join(gaps[:5]))
        else:
            passing("F2P-10")

    # --- F2P-11 ---
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
                # S-14: el umbral es estricto, < 0,5 m, también en la búsqueda de los edificios.
                r = next((r for r in p1["rows"] if str(r.get("class_name")) == cls and
                          abs(float(r["pos_x_m"]) - x) < 0.5 and
                          abs(float(r["pos_z_m"]) - z) < 0.5), None)
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
            missing("F2P-11", "witness_unbacked")
        elif not wit2["rows"]:
            fail("F2P-11", "witness_empty")
        else:
            passing("F2P-11")

    # --- F2P-13 (punto 7 + criatura por el documento, H-4) ---
    ctl_wit = _witness(probe, "P1:control")
    if ctl_wit is not None and _measurement(ctl_wit, manifest=manifest, probe=probe,
                                            part="P1") != "":
        ctl_wit = None
    ctl_known = ctl_wit is not None
    ctl_creatures = 0
    if ctl_wit:
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
    windows = _witness_windows(probe, tap, backend, manifest)
    if not windows["ok"]:
        missing("F2P-13", "missing_witness_window:" + windows["reason"])
    else:
        wit_ops = []
        for p, s in (("P2", "apply"), ("P2n", "apply"), ("P3", "apply1"), ("P3", "apply2"),
                     ("P4a", "apply1"), ("P4a", "apply2"), ("P4b", "apply"), ("P5", "cut"),
                     ("P5", "apply2")):
            w = _witness(probe, f"{p}:{s}")
            if w is not None and _measurement(w, manifest=manifest, probe=probe, part=p,
                                              tap=tap) == "":
                wit_ops.append(w)
        if not wit_ops:
            missing("F2P-13", "no_witness_windows")
        else:
            extras_obj = []
            extras_obj_ce = []
            extras_cre = []
            kind_by_cls = {str(e["cls"]): str(e["kind"]) for e in docs}
            doc_for_tag = {("P2", "apply"): doc1, ("P2n", "apply"): doc1,
                           ("P3", "apply1"): doc1, ("P3", "apply2"): doc2,
                           ("P4a", "apply1"): doc1, ("P4a", "apply2"): doc1,
                           ("P4b", "apply"): doc1, ("P5", "cut"): doc1,
                           ("P5", "apply2"): doc1}
            for w in wit_ops:
                doc = doc_for_tag.get((w["part"], w["stage"]))
                if doc is None:
                    continue
                doc_entities = list(doc.get("entities") or [])
                used: set[int] = set()
                for r in w["rows"]:
                    if int(r.get("sample_idx", -1)) != 0:
                        continue
                    cls = str(r.get("class_name"))
                    is_child = str(r.get("parent_net_id") or "") != ""
                    if not is_child:
                        match = None
                        for i, e in enumerate(doc_entities):
                            if i in used or cls != str(e["cls"]):
                                continue
                            # S-14: estricto, < 0,5 m.
                            if math.hypot(float(r["pos_x_m"]) - float(e["x"]),
                                          float(r["pos_z_m"]) - float(e["z"])) < EPS_OBJ_M:
                                match = i
                                break
                        if match is not None:
                            used.add(match)
                            continue
                    if cls not in scene_classes:
                        continue
                    # R-08: un nacimiento de una clase de la escena que no consume una fila libre
                    # del documento de ese apply es un extra de su generación.
                    # v1.3.11 (F-10): en M1 el producto solo crea raíces; un nacimiento CON padre de
                    # una clase de las escenas tampoco se descarta: es un extra.
                    tag = (f"{w['tag']}:{'child:' if is_child else ''}{cls}@"
                           f"{float(r.get('pos_x_m')):.1f},{float(r.get('pos_z_m')):.1f}")
                    if kind_by_cls.get(cls) in ("infectado", "animal"):
                        extras_cre.append(tag)
                    elif cls in baseline_classes:
                        # S-13/V-17: un objeto de una clase que la CE crea en la zona (la del censo
                        # de P1) no se distingue del botín → INCONCLUSO `posible_botin_ce`.
                        extras_obj_ce.append(tag)
                    else:
                        extras_obj.append(tag)
            if extras_obj:
                fail("F2P-13", ";".join(extras_obj[:5]))
            elif extras_obj_ce:
                missing("F2P-13", "posible_botin_ce:" + ";".join(extras_obj_ce[:5]))
            elif extras_cre:
                if not ctl_known:
                    missing("F2P-13", "control_window_missing:" + ";".join(extras_cre[:5]))
                elif ctl_creatures == 0:
                    fail("F2P-13", ";".join(extras_cre[:5]))
                else:
                    missing("F2P-13", "control_had_creatures:" + ";".join(extras_cre[:5]))
            else:
                passing("F2P-13")

    # v1.3.13 (B-01, §6.1 punto 5): la traza no borra un FALLA propio. Si la comprobación ya está
    # en FALLA por su regla, se le añade el motivo; si no, queda como hoy.
    for violation in trace_bad:
        for cid in TRACE_PART_CHECKS.get(violation.get("part") or "", ()):
            cur = checks.get(cid)
            if cur is not None and cur.get("status") == "fail":
                if "tap_trace_mismatch" not in str(cur.get("detail") or ""):
                    cur["detail"] = f"{cur.get('detail') or ''};tap_trace_mismatch"
            else:
                fail(cid, "tap_trace_mismatch")

    # v1.3.13 (T2f-12, B-05; §6.1 punto 2 línea 498): el backend nunca da un segundo terminal a una
    # op ya resuelta. Si una op (sesion, op_id) tiene mas de un terminal, la comprobacion de su etapa
    # da FALLA con `segundo_terminal:<op_id>`; si no es de ninguna etapa, la de su parte. Si ya
    # estaba en FALLA, se ANADE el motivo. La op cortada de P5 ya lo tiene (`cut_op_terminals`).
    _cut_key = _p5_cut_key(tap, backend, manifest)
    _terms_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for _st in backend["op_states"]:
        _oid = str(_st["data"].get("op_id") or "")
        _sess = str(_st.get("session") or "")
        if not _oid or not _sess:
            continue
        if _is_terminal(str(_st["data"].get("state") or ""),
                        str(_st["data"].get("reason") or "")):
            _terms_by_key.setdefault((_sess, _oid), []).append(_st)
    for _key, _sts in _terms_by_key.items():
        if len(_sts) < 2 or _key == _cut_key:
            continue
        _cid = _second_terminal_check(tap, backend, manifest, _key[0], _key[1])
        if not _cid:
            continue
        _motive = f"segundo_terminal:{_key[1]}"
        _cur = checks.get(_cid)
        if _cur is not None and _cur.get("status") == "fail":
            if _motive not in str(_cur.get("detail") or ""):
                _cur["detail"] = f"{_cur.get('detail') or ''};{_motive}"
        else:
            fail(_cid, _motive)

    # v1.3.14 (§6.1 punto 5): un registro sin `req_id`, una respuesta sin peticion o una
    # duplicada dejan la traza sin juzgar: INCONCLUSO `tap_req_id_missing` en el check de su parte.
    # v1.3.15 (K-02): fuera de las partes con check de traza (P1, entre partes o despues de P5) el
    # problema da INCONCLUSO con el mismo motivo, como una violacion de traza fuera de parte; nunca
    # se descarta en silencio.
    for _prob in tap.get("req_id_problems") or []:
        _ppart = _part_for_time(manifest, float(_prob["t_ms"]))
        _pcids = TRACE_PART_CHECKS.get(_ppart, ())
        if not _pcids:
            if "tap_req_id_missing" not in reasons:
                reasons.append("tap_req_id_missing")
            continue
        for _pcid in _pcids:
            _pcur = checks.get(_pcid)
            if _pcur is None:
                continue
            # v1.3.14: sin req_id la traza no se puede juzgar: INCONCLUSO, aunque la comprobacion
            # hubiera fallado por una consecuencia de la respuesta sin emparejar.
            missing(_pcid, "tap_req_id_missing")

    # v1.3.16 (T2f-15l, :599): mas de cuatro eventos en el ms del cut (sin contar el cut) dejan la
    # traza sin juzgar: INCONCLUSO `tap_tie_group_too_large` en el check de P5.
    # v1.3.16 (T2f-15m, L-04): salvo que F2P-09 ya este en FALLA por una regla suya que no sea la
    # traza (B-01); entonces se queda en FALLA y solo se le anade el motivo.
    if _tie_too_large:
        _cur09 = checks.get("F2P-09")
        if _cur09 is not None and _cur09.get("status") == "fail":
            if "tap_tie_group_too_large" not in str(_cur09.get("detail") or ""):
                _cur09["detail"] = f"{_cur09.get('detail') or ''};tap_tie_group_too_large"
        else:
            if "tap_tie_group_too_large" not in reasons:
                reasons.append("tap_tie_group_too_large")
            checks["F2P-09"] = {"status": "missing", "detail": "tap_tie_group_too_large"}

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
    # L1 (ronda 2, brief:1325): una vida registrada dentro de la partida que no casa y que ninguna
    # comprobación usa no puede dejar el veredicto global en PASA. Un `restart` del servidor de más
    # tras el último trabajo de P5 abre una vida sin identidad; las 13 pasan y la partida daría PASA.
    # Solo se aplica cuando todas las comprobaciones pasan y no hay motivos (si algo ya da INCONCLUSO
    # o FALLA, no cambia nada) y solo cuenta una vida que solape alguna parte de la campaña: un
    # reinicio registrado fuera de la partida no crea una vida que haya que casar.
    _unbound_in_campaign = False
    for _life in probe["lives"].get("lives") or []:
        if _life.get("ok"):
            continue
        for _p in (manifest.get("f2p", {}).get("parts") or []):
            if _finite(_p.get("start_t_ms")) and _finite(_p.get("end_t_ms")) and \
                    float(_life["lo"]) < float(_p["end_t_ms"]) and \
                    float(_life["hi"]) > float(_p["start_t_ms"]):
                _unbound_in_campaign = True
                break
        if _unbound_in_campaign:
            break
    if _unbound_in_campaign:
        reasons.append("server_life_unbound")
        return gate_core.make_verdict(SPIKE_ID, 2, checks=checks_list, metrics=metrics,
                                      reasons=list(reasons))
    return gate_core.make_verdict(SPIKE_ID, 0, checks=checks_list, metrics=metrics, reasons=[])


# ---------------------------------------------------------------------------------------------------
# Auxiliares de tiempo de los efectos juzgados (todos con `t_ms`, R-03)
# ---------------------------------------------------------------------------------------------------

def _first_apply_op(tap: dict[str, Any], manifest: dict[str, Any], part: str,
                    index: int = 0) -> dict[str, Any] | None:
    ops = _tap_op(tap, "scene.apply", part, manifest)
    return ops[index] if len(ops) > index else None


def _terminal_t(tap: dict[str, Any], backend: dict[str, Any], op_id: str,
                session: str) -> float | None:
    st = _terminal_state(backend, op_id, session)
    return float(st["t_ms"]) if st is not None else None


def _p2_terminal_t(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any]) -> float | None:
    d = _first_apply_op(tap, manifest, "P2")
    if d is None:
        return None
    return _terminal_t(tap, backend, d["op_id"], str(d["session"]))


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
    return _terminal_t(tap, backend, d["op_id"], str(d["session"])) if d else None


def _p4a_terminal_t(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any]) -> float | None:
    ops = _tap_op(tap, "scene.apply", "P4a", manifest)
    if len(ops) < 2:
        return None
    return _terminal_t(tap, backend, ops[1]["op_id"], str(ops[1]["session"]))


def _apply_terminal_t(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                      part: str, index: int) -> float | None:
    ops = _tap_op(tap, "scene.apply", part, manifest)
    if len(ops) <= index:
        return None
    return _terminal_t(tap, backend, ops[index]["op_id"], str(ops[index]["session"]))


def _part_restart_t(backend: dict[str, Any], manifest: dict[str, Any],
                    part: str) -> float | None:
    win = _part_window(manifest, part)
    if win is None:
        return None
    ts = [r["t_ms"] for r in backend["restarts"]
          if str(r["data"].get("target") or "") == "server" and
          float(win["start_t_ms"]) <= r["t_ms"] <= float(win["end_t_ms"])]
    return min(ts) if ts else None


def _backend_restart_accredited(tap: dict[str, Any], backend: dict[str, Any],
                                restart_t: float) -> bool:
    """Reinicio del backend acreditado (§6.1 punto 6, F-03): evento `restart` + `/hello` de sesión
    nueva aceptado después. La sesión nueva tiene que ser distinta de la del tramo anterior."""
    session_at = _backend_sessions(tap, backend)
    old = session_at(float(restart_t) - 1e-6)
    new = session_at(float(restart_t) + 1e-6)
    if not old or not new or old == new:
        return False
    return any(str(h.get("session") or "") == new and str(h.get("peer") or "") == "server" and
               _hello_resp_time(h) is not None and
               float(_hello_resp_time(h)) > float(restart_t) for h in tap.get("hellos") or [])


def _part_backend_restarts(backend: dict[str, Any], manifest: dict[str, Any],
                           part: str) -> list[dict[str, Any]]:
    """Reinicios del backend de una parte (§6.1 punto 6, F-03)."""
    win = _part_window(manifest, part)
    if win is None:
        return []
    return [r for r in backend["restarts"]
            if str((r.get("data") or {}).get("target") or "") == "backend" and
            float(win["start_t_ms"]) <= r["t_ms"] <= float(win["end_t_ms"])]


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
        for r in _results_for(tap, d["op_id"], str(d["session"])):
            read = r.get("read") or {}
            obs = read.get("obs")
            if isinstance(obs, dict) and obs.get("at") == "checkpoint" and \
                    isinstance(obs.get("rows"), list):
                ck = {str(row[0]): row for row in obs["rows"]
                      if isinstance(row, list) and len(row) >= 7}
                break
        if ck is not None:
            break
    for e in doc1["entities"]:
        if e["kind"] not in ("infectado", "animal"):
            continue
        w = next((r for r in wit2["rows"] if int(r.get("sample_idx", -1)) == 0 and
                  str(r.get("class_name")) == str(e["cls"]) and
                  math.hypot(float(r["pos_x_m"]) - float(e["x"]),
                             float(r["pos_z_m"]) - float(e["z"])) < EPS_OBJ_M), None)
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
            cre_missing.append(f"{e['id']}:coverage_gap")
        elif int(c.get("alive_b", 0)) != 1 or int(c.get("ai_agent_b", 0)) != 1:
            cre_fail.append(f"{e['id']}:alive_or_ai")


def aggregate_parts(part_dirs: list[Path], *, repo_root: Path | None = None) -> dict[str, Any]:
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
