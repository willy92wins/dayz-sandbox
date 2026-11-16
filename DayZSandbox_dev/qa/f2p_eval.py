"""Oráculo E9 de la partida de F2 (F2P-01..F2P-13).

Decide solo con lecturas independientes: las respuestas crudas de la sonda (censo y testigo), la
traza del proxy del producto, los eventos del backend, las líneas DSBX_SCENE_DEL del mod y los
campos permitidos del manifest. El contrato está en `qa/f2p_evidence_contract.md`.

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


def _valid_net(val: Any) -> bool:
    return isinstance(val, str) and bool(_NET_ID.match(val)) and val != "0:0"


def _load_doc1(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / "fixtures" / "escena-sin-actores.json").read_text(encoding="utf-8"))


def _load_doc2(repo_root: Path) -> dict[str, Any]:
    return json.loads((repo_root / "qa" / "fixtures" / "f2p_scene2.json").read_text(encoding="utf-8"))


def _surface_of(doc_entity: dict[str, Any], census_rows: list[dict[str, Any]]) -> float | None:
    for r in census_rows:
        if str(r.get("class_name")) == str(doc_entity["cls"]):
            if abs(float(r["pos_x_m"]) - float(doc_entity["x"])) <= EPS_OBJ_M and \
                    abs(float(r["pos_z_m"]) - float(doc_entity["z"])) <= EPS_OBJ_M:
                return float(r.get("surface_y_m"))
    return None


def _checks_as_list(checks: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    return [{"id": cid, "status": checks[cid]["status"], "detail": checks[cid]["detail"]}
            for cid in CHECK_IDS]


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
                            "t_result": None}
        elif kind == "result" and ev.get("http") == 200:
            res = ev.get("result") if isinstance(ev.get("result"), dict) else {}
            oid = str(res.get("op_id") or ev.get("op_id") or "")
            if not oid:
                continue
            op = ops.setdefault(oid, {"op_id": oid, "verb": str(res.get("verb") or ""),
                                      "args": None, "peer": str(ev.get("peer") or ""),
                                      "inst": str(ev.get("inst") or ""), "t_enq": float(t),
                                      "status": None, "reason": "", "read": {}, "t_result": None})
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
            # El arranque del trabajo lo sirvió la misma instancia de sonda que lo encoló. Si no, el
            # trabajo se crea igualmente pero queda no válido (así el motivo es `unbacked_rows`).
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
                "pages": {}, "rows": [], "pages_n": None, "rows_total": None, "valid": False,
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
        # El trabajo que pide la lectura y el que devuelve la respuesta tienen que casar. Antes se
        # aceptaba cualquiera de los dos (`or`), así que una respuesta con otro `job` se colaba.
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
        # La página pedida y la devuelta tienen que casar, y el sello de instancia también.
        a_pn = a_n.get("page_n")
        r_pn = r_n.get("page_n")
        if not _finite(a_pn) or not _finite(r_pn) or int(a_pn) != int(r_pn):
            bad_jobs.add(jid)
            continue
        if op.get("inst_result") and op.get("inst") and op["inst_result"] != op["inst"]:
            bad_jobs.add(jid)
            continue
        page_n = int(a_pn)
        job["pages"][page_n] = {"t_ms": op["t_result"], "rows": list(r_rows),
                                "resource": str(r_s.get("resource") or ""),
                                "state": str(r_s.get("state") or ""),
                                "pages_n": r_n.get("pages_n"), "rows_total_n": r_n.get("rows_total_n")}
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
        # `read_job_pages` de la sonda lee siempre la página 0 y, después, hasta `pages_n - 1`
        # (`f03_common.py:1130-1149`). El oráculo tiene que exigir lo mismo: con `pages_n = 0` la
        # única página válida es la 0, no «ninguna». Y 0 es un valor legítimo de `pages_n`/`rows_total_n`.
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
    """Resuelve los testigos con `witness_tag` vacío por ventana de parte y orden canónico de etapas.

    `witness_tag` es opcional en la interfaz real de F0.3. Un testigo con el tag vacío no se rechaza: se
    identifica por su `start_t` dentro de la ventana de su parte. Si la parte tiene varias ventanas
    (P3), se asignan en orden de arranque a las etapas canónicas que no estén ya ocupadas por un tag.
    """
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
                           "session": ""})
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
            results.append({"t_ms": t, "op_id": str(b.get("op_id") or ""),
                            "session": str(b.get("session") or ""), "epoch": str(b.get("epoch") or ""),
                            "status": str(b.get("status") or ""), "reason": str(b.get("reason") or ""),
                            "dup": bool(b.get("dup")), "read": b.get("read") if isinstance(b.get("read"), dict) else {}})
    return {"hellos": hellos, "deliveries": deliveries, "results": results}


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


def _part_window(manifest: dict[str, Any], part: str) -> dict[str, Any] | None:
    f2p = manifest.get("f2p") if isinstance(manifest.get("f2p"), dict) else {}
    for p in f2p.get("parts") or []:
        if isinstance(p, dict) and p.get("name") == part:
            return p
    return None


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
    if not _HEX40.match(str(f2p.get("oracle_commit") or "")):
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
    # sellos observados
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
        # Nombre canónico de la sonda en la evidencia: `pbo_sha256` (no `probe_pbo_sha256`).
        if str(ev.get("pbo_sha256") or "") != str(ident.get("pbo_sha256") or "") or \
                str(ev.get("product_pbo_sha256") or "") != str(ident.get("product_pbo_sha256") or ""):
            reasons.append("pbo_mismatch")
    else:
        reasons.append("manifest_incomplete")
    # hello de la sonda: proto, build y sello
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


def _job_provenance(job: dict[str, Any], manifest: dict[str, Any], probe: dict[str, Any],
                    tap: dict[str, Any], backend: dict[str, Any], part: str) -> str:
    """'' si es válido; 'unbacked' o 'stale'."""
    if not job["valid"]:
        return "unbacked"
    win = _part_window(manifest, part)
    if win is None:
        return "unbacked"
    if job["part"] != part:
        return "unbacked"
    if job["epoch"] != str(win.get("server_epoch") or ""):
        return "unbacked"
    if not (float(win["start_t_ms"]) <= job["start_t"] <= float(win["end_t_ms"])):
        return "unbacked"
    ident = manifest.get("identity") or {}
    # El sello se contrasta con el hello de la instancia que sirvió el trabajo, no con el epoch.
    if not _hello_stamp_ok(probe, job.get("inst") or "", "dsbx-qa1+" + str(ident.get("probe_stamp") or "")):
        return "unbacked"
    # frescura: el trabajo se abre después del último efecto de la parte anterior a su arranque.
    # Se exigen las dos cosas: el arranque del trabajo y la primera página, posteriores al efecto.
    effects = []
    for r in tap["results"]:
        if float(win["start_t_ms"]) <= r["t_ms"] < job["start_t"]:
            effects.append(r["t_ms"])
    for rs in backend["restarts"]:
        if float(win["start_t_ms"]) <= rs["t_ms"] < job["start_t"]:
            effects.append(rs["t_ms"])
    if effects and (job["start_t"] <= max(effects) or job.get("min_page_t", job["start_t"]) <= max(effects)):
        return "stale"
    if job.get("min_page_t", job["start_t"]) < float(win["start_t_ms"]) or \
            job.get("max_page_t", job["start_t"]) > float(win["end_t_ms"]):
        return "unbacked"
    # Una página no puede ser anterior al arranque del trabajo que la sirve. Si además es anterior al
    # efecto, la rama de frescura de arriba ya la ha clasificado como `stale`.
    if job.get("min_page_t", job["start_t"]) < job["start_t"]:
        return "unbacked"
    return ""


def _part_restarts(tap: dict[str, Any], backend: dict[str, Any], manifest: dict[str, Any],
                   part: str) -> list[dict[str, Any]]:
    win = _part_window(manifest, part)
    if win is None:
        return []
    out = []
    for rs in backend["restarts"]:
        if float(win["start_t_ms"]) <= rs["t_ms"] <= float(win["end_t_ms"]):
            out.append(rs)
    return out


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


def _op_state(backend: dict[str, Any], op_id: str) -> dict[str, Any] | None:
    for st in backend["op_states"]:
        if str(st["data"].get("op_id") or "") == op_id:
            return st
    return None


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
    """Mapa id_doc → net_id de la escena 2, identificada por clase y pose (no por orden de net_id)."""
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


def _baseline_ok(census_rows: list[dict[str, Any]], buildings: list[tuple[str, float, float, float]]) -> bool:
    for cls, x, z, yaw in buildings:
        found = False
        for r in census_rows:
            if str(r.get("class_name")) != cls:
                continue
            if abs(float(r["pos_x_m"]) - x) <= 0.5 and abs(float(r["pos_z_m"]) - z) <= 0.5 and \
                    abs((float(r["yaw_deg"]) - yaw + 180.0) % 360.0 - 180.0) <= 1.0:
                found = True
                break
        if not found:
            return False
    return True


BUILDINGS = [
    ("Land_Barn_Metal", 6120.0, 7630.0, 0.0),
    ("Land_Church_02", 6230.0, 7690.0, 90.0),
    ("Land_House_1W01", 6140.0, 7600.0, 45.0),
    ("Land_Shed_Wooden", 6225.0, 7600.0, 180.0),
]


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

    # `witness_tag` es opcional: resolver los testigos con tag vacío por ventana y orden canónico.
    _assign_witness_tags(probe, manifest)

    doc1 = _load_doc1(repo_root)
    doc2 = _load_doc2(repo_root)
    docs = _doc_poses(doc1) + _doc_poses(doc2)
    scene_classes = {str(e["cls"]) for e in docs}

    def fail(cid: str, detail: str) -> None:
        checks[cid] = {"status": "fail", "detail": detail}

    def missing(cid: str, detail: str) -> None:
        checks[cid] = {"status": "missing", "detail": detail}

    def passing(cid: str, detail: str = "ok") -> None:
        checks[cid] = {"status": "pass", "detail": detail}

    fab = {"trace": False, "opstate": False, "stale": False}

    def job_or_none(tag: str, kind: str) -> dict[str, Any] | None:
        j = _census(probe, tag) if kind == "census" else _witness(probe, tag)
        if j is None:
            return None
        part = tag.split(":")[0]
        prov = _job_provenance(j, manifest, probe, tap, backend, part)
        if prov == "unbacked":
            reasons.append("unbacked_rows")
            return None
        if prov == "stale":
            reasons.append("stale_rows")
            fab["stale"] = True
            return None
        return j

    # --- traza del producto: integridad (negativa contra la fabricación) ---
    delivery_ids = {d["op_id"] for d in tap["deliveries"]}
    for r in tap["results"]:
        if r["op_id"] not in delivery_ids:
            fab["trace"] = True
            reasons.append("tap_trace_mismatch")
            break
    for st in backend["op_states"]:
        oid = str(st["data"].get("op_id") or "")
        if oid and oid not in delivery_ids:
            fab["opstate"] = True
            reasons.append("op_state_without_event")
            break

    # --- P1 / P2 base ---
    p1 = job_or_none("P1:base", "census")
    p2 = job_or_none("P2:post", "census")
    wit2 = job_or_none("P2:apply", "witness")
    base_nets = {str(r.get("net_id")) for r in (p1["rows"] if p1 else [])}

    # P2 creations by witness (EEInit)
    wit_ee = []
    if wit2:
        wit_ee = [r for r in wit2["rows"] if int(r.get("sample_idx", -1)) == 0 and
                  str(r.get("parent_net_id") or "") == ""]
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

    # --- F2P-01 ---
    if not (p1 and p2 and wit2 and wit_ee):
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
                post_nets = {str(r.get("net_id")) for r in p2["rows"]}
                diff = [r for r in p2["rows"] if str(r.get("net_id")) not in base_nets]
                if len(diff) != 33:
                    fail("F2P-01", f"census_diff={len(diff)}")
                elif any(n not in post_nets for n in nets):
                    fail("F2P-01", "witness_net_missing_in_census")
                elif any(str(r.get("net_id")) not in set(nets) for r in diff):
                    fail("F2P-01", "extra_creation_in_census")
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
            surf = float(w.get("surface_y_m", float(w["pos_y_m"])))
            if _dist(w, float(e["x"]), surf, float(e["z"])) > EPS_OBJ_M:
                fails.append(f"{e['id']}:witness_far")
        if fails:
            fail("F2P-02", ";".join(fails[:5]))
        else:
            # objetos: censo posterior a < 0.5 m del documento
            obj_fail = []
            for e in doc1["entities"]:
                if e["kind"] != "objeto":
                    continue
                c = next((r for r in p2["rows"] if str(r.get("class_name")) == str(e["cls"]) and
                          abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and
                          abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M), None)
                if c is None:
                    obj_fail.append(f"{e['id']}:census_missing")
                elif _dist(c, float(e["x"]),
                           float(c["surface_y_m"]) if _finite(c.get("surface_y_m")) else float(c["pos_y_m"]),
                           float(e["z"])) > EPS_OBJ_M:
                    obj_fail.append(f"{e['id']}:census_far")
            if obj_fail:
                fail("F2P-02", ";".join(obj_fail[:5]))
            elif not witness_reliable:
                missing("F2P-02", "witness_not_final")
            else:
                # criaturas: trayectoria Q-01 y checkpoint del mod
                ticks = int((manifest.get("f2p") or {}).get("witness_follow_ticks") or 3)
                ck = None
                # El checkpoint de Q-01 es el del apply de P2, no el de un apply posterior.
                for d in _tap_op(tap, "scene.apply", "P2", manifest):
                    for r in _results_for(tap, d["op_id"]):
                        read = r.get("read") or {}
                        if isinstance(read.get("checkpoint"), list):
                            ck = {str(row[0]): row for row in read["checkpoint"]
                                  if isinstance(row, list) and len(row) >= 7}
                            break
                    if ck is not None:
                        break
                cre_fail = []
                cre_missing = []
                for e in doc1["entities"]:
                    if e["kind"] not in ("infectado", "animal"):
                        continue
                    w = next((r for r in wit_ee if str(r.get("class_name")) == str(e["cls"]) and
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
                    # Q-05: censo posterior con alive y IA
                    c = next((r for r in p2["rows"] if str(r.get("net_id")) == net), None)
                    if c is None:
                        d = math.hypot(float(w["pos_x_m"]) - float(p2["center_x"]),
                                       float(w["pos_z_m"]) - float(p2["center_z"]))
                        if d > float(p2["radius"]) - 15.0:
                            cre_missing.append(f"{e['id']}:coverage_gap")
                        else:
                            cre_fail.append(f"{e['id']}:census_missing")
                    elif int(c.get("alive_b", 0)) != 1 or int(c.get("ai_agent_b", 0)) != 1:
                        cre_fail.append(f"{e['id']}:alive_or_ai")
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
    p2n_census = job_or_none("P2n:clean", "census")
    if not p2n_apply:
        missing("F2P-03", "stimulus_not_observed")
    else:
        oid = p2n_apply[0]["op_id"]
        res = _results_for(tap, oid)
        st = _op_state(backend, oid)
        if not res:
            missing("F2P-03", "no_result")
        elif st is None:
            missing("F2P-03", "no_op_state")
        elif str(st["data"].get("state")) != expected[0] or str(st["data"].get("reason") or "") != expected[1]:
            fail("F2P-03", f"state={st['data'].get('state')}/{st['data'].get('reason')}")
        elif p2n_census is None:
            missing("F2P-03", "census_missing")
        else:
            scene1_nets = {str(r.get("net_id")) for r in p2["rows"]} - base_nets if p2 else set()
            if any(str(r.get("net_id")) in scene1_nets for r in p2n_census["rows"]):
                fail("F2P-03", "census_still_has_scene1")
            else:
                passing("F2P-03")

    # --- F2P-04 ---
    p2_apply = _tap_op(tap, "scene.apply", "P2", manifest)
    if not p2_apply or not p2:
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
            diff = [r for r in p2["rows"] if str(r.get("net_id")) not in base_nets]
            if len(diff) != 33:
                fail("F2P-04", f"duplicate_extra:{len(diff)}")
            else:
                passing("F2P-04")

    # --- F2P-05 ---
    pre3 = job_or_none("P3:pre_reset", "census")
    post31 = job_or_none("P3:post_reset1", "census")
    post32 = job_or_none("P3:post_reset2", "census")
    wit3 = job_or_none("P3:apply2", "witness")
    if not (pre3 and post31 and post32 and p2):
        missing("F2P-05", "missing_p3_census")
    else:
        scene1_nets = {str(r.get("net_id")) for r in p2["rows"]} - base_nets
        scene2_map = _doc2_nets_in(pre3["rows"], doc2)
        if len(scene2_map) != len(doc2["entities"]):
            scene2_map = _doc2_nets_in(wit3["rows"] if wit3 else [], doc2)
        scene2_nets = set(scene2_map.values())
        retained = {str(r.get("net_id")) for r in post31["rows"]} & scene1_nets
        expected_retained = {str(r.get("parent_net_id")) for r in post31["rows"]
                             if str(r.get("loc_kind")) == "cargo" and
                             str(r.get("parent_net_id")) in scene1_nets}
        fails = []
        if len(scene2_map) != len(doc2["entities"]):
            fails.append("scene2_not_found")
        if retained != expected_retained or len(retained) != 1:
            fails.append("retained_set")
        # ajenos intactos
        for net in (str(r.get("net_id")) for r in pre3["rows"] if str(r.get("net_id")) not in scene1_nets | scene2_nets | base_nets):
            before = next((r for r in pre3["rows"] if str(r.get("net_id")) == net), None)
            after = next((r for r in post31["rows"] if str(r.get("net_id")) == net), None)
            if after is None:
                fails.append(f"{net}:foreign_missing")
            elif str(before.get("class_name")) != str(after.get("class_name")) or \
                    _dist2(before, after) > 0.01 or \
                    str(before.get("parent_net_id") or "") != str(after.get("parent_net_id") or ""):
                fails.append(f"{net}:foreign_changed")
        # escena 2 intacta antes y después (identidad, clase, pose e inventario)
        for e in doc2["entities"]:
            net = scene2_map.get(str(e["id"]))
            if not net:
                continue
            b = next((r for r in pre3["rows"] if str(r.get("net_id")) == net), None)
            a = next((r for r in post31["rows"] if str(r.get("net_id")) == net), None)
            if b is None or a is None or str(b.get("class_name")) != str(a.get("class_name")) or \
                    _dist2(b, a) > 0.01 or int(b.get("inv_children_n", 0)) != int(a.get("inv_children_n", 0)):
                fails.append(f"{net}:scene2_changed")
        # op parcial/contenido_ajeno dos veces
        resets = [d for d in _tap_op(tap, "scene.reset", "P3", manifest)]
        states = [_op_state(backend, d["op_id"]) for d in resets]
        if len(resets) < 2 or any(s is None for s in states[:2]) or \
                any(str(s["data"].get("state")) != "parcial" or str(s["data"].get("reason") or "") != "contenido_ajeno"
                    for s in states[:2]):
            fails.append("reset_state")
        # segundo reset igual
        if {str(r.get("net_id")) for r in post32["rows"]} != {str(r.get("net_id")) for r in post31["rows"]}:
            fails.append("second_reset_diff")
        if fails:
            fail("F2P-05", ";".join(fails[:5]))
        else:
            passing("F2P-05")

    # --- F2P-06 ---
    clean3c = job_or_none("P3c:clean", "census")
    if not (clean3c and pre3 and p2 and wit3):
        missing("F2P-06", "missing_census")
    else:
        scene1_nets = {str(r.get("net_id")) for r in p2["rows"]} - base_nets
        scene2_map = _doc2_nets_in(pre3["rows"], doc2)
        if len(scene2_map) != len(doc2["entities"]):
            scene2_map = _doc2_nets_in(wit3["rows"], doc2)
        alive_scene1 = {str(r.get("net_id")) for r in clean3c["rows"]} & scene1_nets
        fails = []
        if len(scene2_map) != len(doc2["entities"]):
            fails.append("scene2_not_found")
        for e in doc2["entities"]:
            net = scene2_map.get(str(e["id"]))
            if not net:
                continue
            b = next((r for r in pre3["rows"] if str(r.get("net_id")) == net), None)
            a = next((r for r in clean3c["rows"] if str(r.get("net_id")) == net), None)
            if b is None or a is None or str(b.get("class_name")) != str(a.get("class_name")) or \
                    abs(float(a["pos_x_m"]) - float(e["x"])) > 0.5 or \
                    abs(float(a["pos_z_m"]) - float(e["z"])) > 0.5 or \
                    int(b.get("inv_children_n", 0)) != int(a.get("inv_children_n", 0)):
                fails.append(f"{net}:scene2_changed")
        if alive_scene1:
            fails.append(f"scene1_alive={len(alive_scene1)}")
        if fails:
            fail("F2P-06", ";".join(fails[:5]))
        else:
            passing("F2P-06")

    # --- F2P-07 ---
    b4 = job_or_none("P4b:post_restart", "census")
    c4 = job_or_none("P4c:post_restart", "census")
    if not (b4 and c4):
        missing("F2P-07", "missing_census")
    else:
        fails = []
        control_ok = True
        for j in (b4, c4):
            for r in j["rows"]:
                m = _find_doc_match(r, docs)
                if m is not None:
                    fails.append(f"{j['tag']}:reappeared:{m['id']}")
            ctrl = [r for r in j["rows"] if str(r.get("class_name")) == CONTROL_CLASS and
                    abs(float(r["pos_x_m"]) - CONTROL_POS[0]) <= 0.5 and
                    abs(float(r["pos_z_m"]) - CONTROL_POS[1]) <= 0.5 and
                    abs(float(r.get("health_hp", 0.0)) - CONTROL_HP) <= 1.0]
            if not ctrl:
                control_ok = False
            elif not any(int(c.get("inv_children_n", 0)) > 0 or
                         any(str(ch.get("parent_net_id") or "") == str(c.get("net_id"))
                             for ch in j["rows"] if ch is not c)
                         for c in ctrl):
                # El control persistente se creó con un hijo en el cargo: tiene que reaparecer con él.
                control_ok = False
        if fails:
            fail("F2P-07", ";".join(fails[:5]))
        elif not control_ok:
            missing("F2P-07", "persistent_control_missing")
        else:
            passing("F2P-07")

    # --- F2P-08 ---
    p4a_c = job_or_none("P4a:post_apply2", "census")
    p4a_apply = _tap_op(tap, "scene.apply", "P4a", manifest)
    rs = _part_restarts(tap, backend, manifest, "P4a")
    recon = _tap_op(tap, "state.read", "P4a", manifest)
    if not (p4a_c and p4a_apply and rs):
        missing("F2P-08", "missing_restart_or_apply")
    else:
        restart_t = min(r["t_ms"] for r in rs)
        rec = [d for d in recon if d["t_ms"] > restart_t]
        first_apply_t = min(d["t_ms"] for d in p4a_apply)
        rec = [d for d in rec if d["t_ms"] < first_apply_t]
        if not rec:
            missing("F2P-08", "no_reconciliation_before_apply")
        else:
            bad_docs = []
            doc_matches = []
            for e in doc1["entities"]:
                ms = [r for r in p4a_c["rows"]
                      if str(r.get("class_name")) == str(e["cls"]) and
                      abs(float(r["pos_x_m"]) - float(e["x"])) <= EPS_OBJ_M and
                      abs(float(r["pos_z_m"]) - float(e["z"])) <= EPS_OBJ_M]
                if len(ms) != 1:
                    bad_docs.append(f"{e['id']}:{len(ms)}")
                doc_matches.extend(ms)
            extras = [r for r in p4a_c["rows"]
                      if str(r.get("net_id")) not in base_nets and
                      _find_doc_match(r, doc1["entities"]) is None and
                      _find_doc_match(r, doc2["entities"]) is None]
            if bad_docs or len(doc_matches) != 33 or extras:
                fail("F2P-08", f"census={len(doc_matches)}/bad={';'.join(bad_docs[:5])}/extras={len(extras)}")
            elif not any(str(s["data"].get("reason") or "") == "reconciliada" for s in backend["op_states"]):
                missing("F2P-08", "no_reconciled_state")
            else:
                passing("F2P-08")

    # --- F2P-09 ---
    p5c = job_or_none("P5:post_apply", "census")
    wit5 = job_or_none("P5:cut", "witness")
    p5_applies = _tap_op(tap, "scene.apply", "P5", manifest)
    if not (p5c and wit5 and p5_applies):
        missing("F2P-09", "missing_cut_evidence")
    else:
        k = len([r for r in wit5["rows"] if int(r.get("sample_idx", -1)) == 0])
        cut_oid = p5_applies[0]["op_id"]
        cut_res = _results_for(tap, cut_oid)
        new_apply = [d for d in p5_applies if d["op_id"] != cut_oid]
        recon5 = [d for d in _tap_op(tap, "state.read", "P5", manifest)
                  if d["t_ms"] > (wit5["start_t"])]
        scene1_nets = {str(r.get("net_id")) for r in p5c["rows"]} - base_nets
        total = len([r for r in p5c["rows"] if _find_doc_match(r, doc1["entities"]) is not None])
        if k == 0:
            fail("F2P-09", "no_effect_before_cut")
        elif cut_res:
            fail("F2P-09", "cut_op_had_result")
        elif not new_apply or not recon5 or recon5[0]["t_ms"] >= new_apply[0]["t_ms"]:
            missing("F2P-09", "no_reconciliation_before_new_apply")
        elif total != 33:
            fail("F2P-09", f"total={total}")
        else:
            passing("F2P-09")

    # --- F2P-10 ---
    if not del_rows:
        missing("F2P-10", "no_delete_lines")
    else:
        census_jobs = sorted([j for j in probe["jobs"].values() if j["kind"] == "census" and j["valid"]],
                             key=lambda j: j["start_t"])
        doc_pos = {str(e["id"]): (float(e["x"]), float(e["z"])) for e in doc1["entities"]}
        fails = []
        gaps = []
        max_confirm = 0.0
        for line in del_rows:
            net = f"{int(line.get('net_high', 0))}:{int(line.get('net_low', 0))}"
            t = float(line.get("t_ms") or 0.0)
            nxt = next((j for j in census_jobs if j["start_t"] > t), None)
            if nxt is None:
                gaps.append(f"{net}:no_next_census")
                continue
            # Posición: el último censo anterior que tenga la entidad; si no, el documento por `lid`.
            pos = None
            for j in reversed(census_jobs):
                if j["start_t"] >= t:
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
            covered = math.hypot(pos[0] - float(nxt["center_x"]), pos[1] - float(nxt["center_z"])) <= \
                float(nxt["radius"])
            if not covered:
                gaps.append(f"{net}:not_covered")
                continue
            present = any(str(r.get("net_id")) == net for r in nxt["rows"])
            if int(line.get("deleted_confirmed_b", 0)) == 1:
                max_confirm = max(max_confirm, float(line.get("confirm_tick_ms") or 0.0) - t)
                if present:
                    fails.append(f"{net}:confirmed_but_alive")
            if int(line.get("delete_failed_b", 0)) == 1 and not present:
                fails.append(f"{net}:failed_but_missing")
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
        if not (wit2 and wit2["rows"]):
            fails.append("witness_empty")
        if fails:
            fail("F2P-11", ";".join(fails))
        else:
            passing("F2P-11")

    # --- F2P-13 ---
    ctl_wit = job_or_none("P1:control", "witness")
    ctl_known = ctl_wit is not None
    ctl_creatures = 0
    if ctl_wit:
        ctl_creatures = len([r for r in ctl_wit["rows"]
                             if int(r.get("sample_idx", -1)) == 0 and
                             str(r.get("parent_net_id") or "") == "" and
                             int(r.get("ai_agent_b", 0)) == 1])
    wit_ops = [w for w in (job_or_none(f"{p}:{s}", "witness") for p, s in
                           (("P2", "apply"), ("P2n", "apply"), ("P3", "apply1"), ("P3", "apply2"),
                            ("P4a", "apply1"), ("P4b", "apply"), ("P5", "cut"))) if w]
    if not wit_ops:
        missing("F2P-13", "no_witness_windows")
    else:
        extras_obj = []
        extras_cre = []
        for w in wit_ops:
            for r in w["rows"]:
                # Solo creaciones raíz (EEInit, sample_idx 0); las trayectorias y los hijos de cargo no son extras.
                if int(r.get("sample_idx", -1)) != 0:
                    continue
                if str(r.get("parent_net_id") or "") != "":
                    continue
                if str(r.get("class_name")) not in scene_classes:
                    continue
                if _find_doc_match(r, docs) is not None:
                    continue
                tag = f"{w['tag']}:{r.get('class_name')}@{float(r.get('pos_x_m')):.1f},{float(r.get('pos_z_m')):.1f}"
                if int(r.get("ai_agent_b", 0)) == 1:
                    extras_cre.append(tag)
                else:
                    extras_obj.append(tag)
        if extras_obj:
            fail("F2P-13", ";".join(extras_obj[:5]))
        elif extras_cre:
            if not ctl_known:
                # Sin ventana de control válida no se puede afirmar que no hubiera criaturas: INCONCLUSO.
                missing("F2P-13", "control_window_missing:" + ";".join(extras_cre[:5]))
            elif ctl_creatures == 0:
                fail("F2P-13", ";".join(extras_cre[:5]))
            else:
                missing("F2P-13", ";".join(extras_cre[:5]))
        else:
            passing("F2P-13")

    if fab["trace"]:
        fail("F2P-01", "tap_trace_mismatch")
    if fab["opstate"]:
        fail("F2P-01", "op_state_without_event")
    if fab["stale"]:
        fail("F2P-01", "stale_rows")

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
