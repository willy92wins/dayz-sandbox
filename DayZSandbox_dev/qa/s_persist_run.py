"""Runner de S-persist (brief F0.3-0 §5.1, §6). Offline ejecuta los peers falsos como
procesos reales del nucleo (PartContext) y simula el reinicio de mundo matando y
relanzando el peer servidor: la extension persiste en disco solo lo creado sin
ECE_NOPERSISTENCY_WORLD, como haria el storage del motor."""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import f03_common
import gate_core
import s_persist_eval
import s_persist_mutants
import wire

SPIKE_ID = "S-persist"
QA_DIR = Path(__file__).resolve().parent
REPO_ROOT = QA_DIR.parent.parent
FIXTURE_PATH = QA_DIR / "fixtures" / "s_persist_fixture.json"

IN_SCOL = ["logical_id", "parent_id", "cat", "class_name", "slot_name"]
IN_NCOL = ["req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"]
TERMINAL_STATES = ("done", "failed", "stopped", "expired")
# Holgura del primer disco t5: en partida la latencia del censo varia mucho
# mas que offline y cada reintento es otro censo grande (GetObjectsAtPosition3D),
# asi que el radio inicial cubre el alcance estimado con margen acotado.
SLACK_REL = 0.10
SLACK_ABS_M = 5.0


def _fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _part_config(part_name, fixture):
    if part_name == "mut-foreign_wiped":
        return {
            "retained_scene": "scene_a_mut",
            "retained_area": "area_a_mut",
            "pfx": "am",
            "base_areas": ["area_a", "area_a_mut", "area_b", "area_c"],
            "active_scenes": ["scene_a_mut", "scene_a_clean", "scene_b"],
            "raw_tags": ["am_foreign_ground", "am_foreign_in_chest", "am_foreign_in_child_kit", "b_foreign_in_chest", "c_persistent_control"],
            "creature_areas": ["area_a_mut", "area_b"],
            "apply_faults": {},
            "reset_fault": "reset_wipe_radius_25m",
            "cross_scene": "scene_a_mut",
            "cross_parent": "am_prop_2",
            "has_scene_d": False,
            "bypass_contention": False,
            "mutant": "foreign_wiped",
        }
    if part_name == "mut-unprotected_leak":
        return {
            "retained_scene": "scene_a",
            "retained_area": "area_a",
            "pfx": "a",
            "base_areas": ["area_a", "area_b", "area_c", "area_d"],
            "active_scenes": ["scene_a", "scene_a_clean", "scene_b", "scene_d"],
            "raw_tags": ["a_foreign_ground", "a_foreign_in_chest", "a_foreign_in_child_kit", "b_foreign_in_chest", "c_persistent_control"],
            "creature_areas": ["area_a", "area_b"],
            "apply_faults": {"scene_d": "omit_nopersistency_flag"},
            "reset_fault": "",
            "cross_scene": "scene_a",
            "cross_parent": "a_prop_2",
            "has_scene_d": True,
            "bypass_contention": False,
            "mutant": "unprotected_leak",
        }
    bypass = part_name == "mut-census_resource_bypass"
    return {
        "retained_scene": "scene_a",
        "retained_area": "area_a",
        "pfx": "a",
        "base_areas": ["area_a", "area_b", "area_c"],
        "active_scenes": ["scene_a", "scene_a_clean", "scene_b"],
        "raw_tags": ["a_foreign_ground", "a_foreign_in_chest", "a_foreign_in_child_kit", "b_foreign_in_chest", "c_persistent_control"],
        "creature_areas": ["area_a", "area_b"],
        "apply_faults": {},
        "reset_fault": "",
        "cross_scene": "scene_a",
        "cross_parent": "a_prop_2",
        "has_scene_d": False,
        "bypass_contention": bypass,
        "mutant": "census_resource_bypass" if bypass else "",
    }


def _build_scene_rows(fixture, scene_id):
    scene = fixture["scenes"][scene_id]
    wire_rows = []
    ledger_rows = []
    for ent in scene.get("entities", []):
        wire_rows.append({
            "logical_id": ent["logical_id"],
            "parent_id": ent["parent_id"],
            "cat": ent["cat"],
            "class_name": ent["class_name"],
            "slot_name": ent["slot_name"],
            "req_x_m": float(ent["req_x_m"]),
            "req_z_m": float(ent["req_z_m"]),
            "req_yaw_deg": float(ent["req_yaw_deg"]),
            "health_mark_ratio": float(ent.get("health_mark_ratio", 0.0)),
            "must_vanish_b": float(ent.get("must_vanish_on_restart_b", 1)),
        })
        ledger_rows.append({
            "role": ent.get("role", scene.get("role", "")),
            "scene_id": scene_id,
            "logical_id": ent["logical_id"],
            "parent_id": ent["parent_id"],
            "cat": ent["cat"],
            "class_name": ent["class_name"],
            "slot_name": ent["slot_name"],
            "req_x_m": float(ent["req_x_m"]),
            "req_z_m": float(ent["req_z_m"]),
            "req_yaw_deg": float(ent["req_yaw_deg"]),
            "health_mark_ratio": float(ent.get("health_mark_ratio", 0.0)),
            "must_vanish_on_restart_b": int(ent.get("must_vanish_on_restart_b", 1)),
        })
    return wire_rows, ledger_rows


def _snapshot_dir(root):
    root = Path(root)
    if not root.is_dir():
        return None
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rel = path.relative_to(root).as_posix()
            st = path.stat()
            out[rel] = {
                "sha256": f03_common.sha256_file_hex(path),
                "size_b": int(st.st_size),
                "mtime_ns": int(st.st_mtime_ns),
            }
    return out


def _storage_env():
    """Configuracion de storage del brief §2.3, sobreescribible por DSBX_S_PERSIST_STORAGE_CONFIG."""
    override = os.environ.get("DSBX_S_PERSIST_STORAGE_CONFIG")
    try:
        if override:
            data = json.loads(Path(override).read_text(encoding="utf-8"))
            if isinstance(data.get("storage_env"), dict):
                data = data["storage_env"]
        else:
            data = _fixture().get("storage_env")
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    required = ("server_root_dir", "mission_dir", "storage_dir", "storage_data_dir", "server_exe_names")
    if any(k not in data for k in required):
        return None
    names = data.get("server_exe_names")
    if not isinstance(names, list) or not names:
        return None
    return {
        "server_root_dir": str(data["server_root_dir"]),
        "mission_dir": str(data["mission_dir"]),
        "storage_dir": str(data["storage_dir"]),
        "storage_data_dir": str(data["storage_data_dir"]),
        "server_exe_names": [str(n) for n in names],
    }


_STORAGE_LEAF_RE = re.compile(r"^storage_\d+$")
_SERVER_EXE_NAMES = frozenset({"dayzserver_x64.exe", "dayzserver.exe", "dayzdiag_x64.exe"})


def _resolve_abs(raw):
    """Ruta absoluta resuelta, o None si es relativa, raiz de unidad o '.'."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text == ".":
        return None
    p = Path(text)
    if not p.is_absolute():
        return None
    try:
        resolved = p.resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if resolved == Path(resolved.anchor):
        return None
    return resolved


def _paths_overlap(a, b):
    try:
        a.relative_to(b)
        return True
    except ValueError:
        pass
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False


def _validate_storage_env(storage_env, backup_dir=None):
    """BLOQ 3: el destino de borrado es exactamente <mision>/storage_<n> de la corrida.

    Devuelve el dict con rutas resueltas, o None rechazando antes de operar:
    rutas relativas/raices/'.', storage que no cuelga de mission_dir con hoja
    storage_<n>, datos fuera del storage y solapamiento storage<->backup.
    """
    if not isinstance(storage_env, dict):
        return None
    server_root = _resolve_abs(storage_env.get("server_root_dir"))
    mission = _resolve_abs(storage_env.get("mission_dir"))
    storage = _resolve_abs(storage_env.get("storage_dir"))
    storage_data = _resolve_abs(storage_env.get("storage_data_dir"))
    if server_root is None or mission is None or storage is None or storage_data is None:
        return None
    if storage.parent != mission:
        return None
    if not _STORAGE_LEAF_RE.match(storage.name):
        return None
    try:
        mission.relative_to(server_root)
    except ValueError:
        return None
    if storage_data != storage and storage_data.parent == storage:
        pass
    elif storage_data != storage:
        try:
            storage_data.relative_to(storage)
        except ValueError:
            return None
    if backup_dir is not None:
        backup = Path(backup_dir)
        if not backup.is_absolute():
            return None
        try:
            backup = backup.resolve()
        except (OSError, RuntimeError, ValueError):
            return None
        if _paths_overlap(storage, backup):
            return None
    out = dict(storage_env)
    out["server_root_dir"] = str(server_root)
    out["mission_dir"] = str(mission)
    out["storage_dir"] = str(storage)
    out["storage_data_dir"] = str(storage_data)
    return out


def _server_query_error():
    return "unknown"


def _classify_server_processes(rows, storage_env, *, own_pid=None):
    """Clasifica filas (name,pid,cmdline): 'running'|'stopped'|'unknown'.

    Solo cuenta el servidor de la corrida: ejecutable de servidor (nunca un
    cliente DayZDiag_x64.exe) y, si hay linea de comandos, -mission/-profiles
    de esta mision; o el PID propio registrado al lanzarlo.
    """
    if rows is None:
        return _server_query_error()
    mission = str(storage_env.get("mission_dir") or "") if storage_env else ""
    found = False
    for row in rows or []:
        try:
            name = str(row.get("name") or "")
            pid = row.get("pid")
            cmd = str(row.get("command_line") or "")
        except AttributeError:
            continue
        if own_pid is not None and pid is not None and int(pid) == int(own_pid):
            found = True
            continue
        if name.lower() not in _SERVER_EXE_NAMES:
            continue
        if not cmd:
            continue
        low = cmd.lower()
        # Un cliente DayZDiag_x64.exe no es el servidor: el servidor Diag
        # acredita con -server en su linea de comandos.
        if name.lower() == "dayzdiag_x64.exe" and "-server" not in low:
            continue
        if mission and mission.lower() not in low:
            continue
        if "-mission" not in low and "-profiles" not in low and not mission:
            continue
        found = True
    return "running" if found else "stopped"


def _list_server_processes(storage_env):
    """Filas de procesos via tasklist/WMI; None si la consulta falla."""
    try:
        proc = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH", "/V"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    rows = []
    for line in proc.stdout.splitlines():
        try:
            row = next(csv.reader([line]), [])
        except (csv.Error, StopIteration):
            continue
        if not row:
            continue
        pid = None
        if len(row) > 1:
            try:
                pid = int(row[1])
            except ValueError:
                pid = None
        rows.append({"name": row[0], "pid": pid, "command_line": ""})
    try:
        proc2 = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process | Select-Object Name,ProcessId,CommandLine | ConvertTo-Csv -NoTypeInformation",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
    except OSError:
        return rows
    if proc2.returncode != 0:
        return rows
    by_pid = {}
    for line in proc2.stdout.splitlines():
        try:
            row = next(csv.reader([line]), [])
        except (csv.Error, StopIteration):
            continue
        if len(row) < 3 or row[0] == "Name":
            continue
        try:
            pid2 = int(row[1])
        except ValueError:
            continue
        by_pid[pid2] = {"name": row[0], "pid": pid2, "command_line": row[2]}
    if by_pid:
        merged = []
        seen = set()
        for r in rows:
            if r["pid"] in by_pid:
                merged.append(by_pid[r["pid"]])
                seen.add(r["pid"])
            else:
                merged.append(r)
        for pid2, r in by_pid.items():
            if pid2 not in seen:
                merged.append(r)
        return merged
    return rows


def _server_state(storage_env, *, own_pid=None, rows=None):
    """'running'|'stopped'|'unknown': un error de consulta nunca es 'stopped'."""
    if storage_env is None:
        return "unknown"
    if rows is None:
        rows = _list_server_processes(storage_env)
    return _classify_server_processes(rows, storage_env, own_pid=own_pid)


def _server_process_running(storage_env):
    # Compat: True solo con servidor de la corrida acreditado; unknown -> False
    # en booleanos, pero los llamadores criticos usan _require_server_stopped.
    return _server_state(storage_env) == "running"


def _require_server_stopped(storage_env, *, own_pid=None, rows=None):
    """Puerta previa a copiar/restaurar: (True,'') solo si parada comprobada."""
    state = _server_state(storage_env, own_pid=own_pid, rows=rows)
    if state == "stopped":
        return True, ""
    if state == "running":
        return False, "server_still_running"
    return False, "server_state_unknown"


def _unique_backup_path(backup_dir):
    """Slot de backup nuevo: nunca se reutiliza ni se borra uno previo."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return backup_dir
    for n in range(2, 1000):
        cand = backup_dir.with_name(f"{backup_dir.name}.bak{n}")
        if not cand.exists():
            return cand
    raise RuntimeError("storage_backup_slot_exhausted")


def _copy_tree_verified(src, dst, expected_snapshot=None):
    """Copia src->dst (dst no debe existir) y verifica por sha256+size."""
    src = Path(src)
    dst = Path(dst)
    if expected_snapshot is None:
        expected_snapshot = _snapshot_dir(src) or {}
    if src.is_dir():
        shutil.copytree(src, dst)
    else:
        dst.mkdir(parents=True, exist_ok=True)
    got = _snapshot_dir(dst) or {}
    if _sha_map(got) != _sha_map(expected_snapshot):
        raise RuntimeError("storage_copy_verify_failed")
    return got


def _backup_storage(storage_env, backup_dir, label):
    # BLOQ 2/3: parada comprobada y rutas delimitadas antes de copiar.
    checked = _validate_storage_env(storage_env, backup_dir)
    if checked is None:
        raise RuntimeError("storage_path_rejected")
    ok, err = _require_server_stopped(checked)
    if not ok:
        raise RuntimeError(err)
    src = Path(checked["storage_dir"])
    snapshot = _snapshot_dir(src)
    if snapshot is None:
        snapshot = {}
    # BLOQ 4: un backup previo es evidencia de recuperacion; no se borra.
    target = _unique_backup_path(backup_dir)
    _copy_tree_verified(src, target, snapshot)
    return snapshot


def _resolve_backup_dir(backup_dir):
    """El slot de backup vigente: el de mayor numero, sin borrar ninguno."""
    backup_dir = Path(backup_dir)
    best = None
    best_n = 0
    if backup_dir.is_dir():
        best, best_n = backup_dir, 1
    parent = backup_dir.parent
    if parent.is_dir():
        for cand in parent.glob(backup_dir.name + ".bak*"):
            suffix = cand.name[len(backup_dir.name) + 4:]
            if cand.is_dir() and suffix.isdigit() and int(suffix) > best_n:
                best, best_n = cand, int(suffix)
    return best


def _sha_map(snapshot):
    out = {}
    for rel, meta in (snapshot or {}).items():
        if isinstance(meta, dict):
            out[rel] = (str(meta.get("sha256") or ""), int(meta.get("size_b") or 0))
        else:
            out[rel] = (str(meta or ""), 0)
    return out


def _restore_storage(storage_env, backup_dir, storage_t0):
    """BLOQ 4: copia preparada y verificada antes de sustituir, con rollback.

    Devuelve (restore_ok_b, snapshot, error). Cualquier fallo deja el destino
    intacto o restaurado desde la copia de rollback y error != '' (el llamador
    lo publica como restauracion incompleta). El backup nunca se borra aqui.
    """
    checked = _validate_storage_env(storage_env, backup_dir)
    if checked is None:
        return 0, {}, "storage_path_rejected"
    ok, err = _require_server_stopped(checked)
    if not ok:
        return 0, _snapshot_dir(Path(checked["storage_dir"])) or {}, err
    dest = Path(checked["storage_dir"])
    actual_backup = _resolve_backup_dir(backup_dir)
    if actual_backup is None:
        return 0, _snapshot_dir(dest) or {}, "storage_backup_missing"
    expected = _snapshot_dir(actual_backup) or {}
    if storage_t0 is not None and _sha_map(expected) != _sha_map(storage_t0):
        return 0, _snapshot_dir(dest) or {}, "storage_backup_verify_failed"
    parent = dest.parent
    stamp = f"{os.getpid()}-{time.time_ns()}"
    staged = parent / f".{dest.name}.r7stage-{stamp}"
    rollback = parent / f".{dest.name}.r7rollback-{stamp}"
    try:
        # 1) Preparar y verificar la copia fuera del destino.
        _copy_tree_verified(actual_backup, staged, expected)
        # 2) Solo entonces sustituir: destino -> rollback, staged -> destino.
        moved_dest = False
        try:
            if dest.exists():
                os.rename(dest, rollback)
                moved_dest = True
            os.rename(staged, dest)
        except OSError:
            if moved_dest and not dest.exists() and rollback.exists():
                os.rename(rollback, dest)
            raise
        # 3) Verificar el destino ya sustituido; si no, rollback.
        restored = _snapshot_dir(dest) or {}
        if _sha_map(restored) != _sha_map(expected):
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=True)
            if rollback.exists():
                os.rename(rollback, dest)
            restored = _snapshot_dir(dest) or {}
            return 0, restored, "storage_restore_verify_failed"
        if rollback.exists():
            shutil.rmtree(rollback, ignore_errors=True)
        # Brief §10.2/N33: la restauracion en frio se acredita por sha256 (+size).
        return (1 if _sha_map(restored) == _sha_map(storage_t0) else 0), restored, ""
    except Exception as exc:  # fallo de copia/sustitucion: destino intacto o restaurado
        try:
            if staged.exists():
                shutil.rmtree(staged, ignore_errors=True)
            if not dest.exists() and rollback.exists():
                os.rename(rollback, dest)
        except OSError:
            pass
        return 0, _snapshot_dir(dest) or {}, f"storage_restore_incomplete:{type(exc).__name__}:{exc}"


def _snapshot_stage(is_live, storage_env, sim_storage):
    if is_live and storage_env is not None:
        try:
            snap = _snapshot_dir(Path(storage_env["storage_dir"]))
        except OSError:
            snap = None
        return snap if snap is not None else {}
    return _snapshot_dir(sim_storage)


def _bridge_events(ctx):
    with ctx.bridge.cv:
        return list(ctx.bridge.events)


def _bridge_op_first_t(events, op_id):
    vals = []
    for ev in events:
        if str(ev.get("op_id") or "") != op_id:
            continue
        t = ev.get("t_ms")
        if isinstance(t, (int, float)) and math.isfinite(float(t)):
            vals.append(float(t))
    return min(vals) if vals else None


def _bridge_op_result_t(events, op_id):
    for ev in reversed(events):
        if ev.get("ev") != "result" or str(ev.get("op_id") or "") != op_id:
            continue
        t = ev.get("t_ms")
        if isinstance(t, (int, float)) and math.isfinite(float(t)):
            return float(t)
    return None


def _bridge_hello_t(events, inst):
    vals = []
    for ev in events:
        if ev.get("ev") != "hello" or ev.get("http") != 200 or ev.get("peer") != "server":
            continue
        if str(ev.get("inst") or "") != str(inst):
            continue
        t = ev.get("t_ms")
        if isinstance(t, (int, float)) and math.isfinite(float(t)):
            vals.append(float(t))
    return min(vals) if vals else None


def _bridge_old_max_tick_ms(events, hello_t_ms):
    """max_old_srv_tick_ms del oraculo (eval :2448): maximo de recv_ms/done_ms
    registrados en los resultados del bridge del peer servidor del epoch viejo
    (todos anteriores al hello nuevo), no el tick_ms de un solo payload."""
    best = 0.0
    for ev in events:
        if ev.get("ev") != "result" or ev.get("peer") != "server":
            continue
        t = ev.get("t_ms")
        if hello_t_ms is not None:
            if not isinstance(t, (int, float)) or not math.isfinite(float(t)) or float(t) >= float(hello_t_ms):
                continue
        res_list = []
        if isinstance(ev.get("result"), dict):
            res_list.append(ev["result"])
        if isinstance(ev.get("results"), list):
            res_list.extend(r for r in ev["results"] if isinstance(r, dict))
        for res in res_list:
            if bool(res.get("dup")):
                continue
            for key in ("recv_ms", "done_ms"):
                v = res.get(key)
                if isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) > best:
                    best = float(v)
    return best


def _probe_sources_at_commit(git_head):
    top = f03_common._git_toplevel(REPO_ROOT)
    cwd = str(top if top is not None else REPO_ROOT)
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", git_head, "--", "qa/probe/DayZSandbox_QA", "DayZSandbox_dev/qa/probe/DayZSandbox_QA"],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if proc.returncode != 0:
        return {}
    out = {}
    for raw in proc.stdout.splitlines():
        path = raw.strip()
        if not path:
            continue
        norm = path.replace("\\", "/").lstrip("/")
        if norm.startswith("DayZSandbox_dev/"):
            norm = norm[len("DayZSandbox_dev/"):]
        fname = Path(norm).name
        if norm.startswith("qa/probe/DayZSandbox_QA/scripts/") and fname.startswith("DSBX_QA_X_Persist") and fname.endswith(".c"):
            show = subprocess.run(
                ["git", "-c", "core.autocrlf=false", "show", f"{git_head}:{path}"],
                cwd=cwd, capture_output=True, check=False,
            )
            if show.returncode == 0:
                out[path] = show.stdout.decode("utf-8")
    return out


def _job_free(ctx, job_id):
    return f03_common.issue_one(
        ctx, "server", "job_free",
        wire.pack_payload(scalars_str={"job": job_id}),
    )


def _census_tag(stage, area_id, has_center_override=False):
    """Etiqueta explicita de etapa para el evaluador congelado.

    BLOQ 1: un disco de seguimiento o posterior a la limpieza nunca lleva la
    etiqueta desnuda t5_track_* (que el evaluador clasifica como t5): lleva
    '<etapa>:<disco>', p. ej. 't6_post_cleanup_census:t5_track_b_inf_1_p0_r0',
    y asi ninguna lectura posterior a la limpieza entra en N49/PER-08.
    """
    return f"{stage}:{area_id}"


def _census(ctx, fixture, stage, area_id, include_dir, *, busy_probe=False, busy_fault=None, qa_fault=None, defer_free=False, center_override=None, radius_override=None):
    if center_override is None:
        area = fixture["areas"][area_id]
        tag = _census_tag(stage, area_id)
        cx = float(area["center_x_m"])
        cz = float(area["center_z_m"])
        rad = float(area["radius_m"])
    else:
        tag = _census_tag(stage, area_id, has_center_override=True)
        cx = float(center_override[0])
        cz = float(center_override[1])
        rad = float(radius_override) if radius_override is not None else 60.0
    payload = wire.pack_payload(
        scalars_str={"area_tag": tag},
        scalars_num={
            "center_x_m": cx,
            "center_z_m": cz,
            "radius_m": rad,
            "include_director_b": float(include_dir),
        },
    )
    out = f03_common.issue_one(ctx, "server", "per_census_start", payload, qa_fault=qa_fault)
    rec = {
        "ev": "census_stage",
        "stage": stage,
        "area_id": area_id,
        "area_tag": tag,
        "include_director_b": int(include_dir),
        "status": out.status,
        "reason": out.reason,
        "op_id": out.op_id,
        "job_id": "",
        "rows": [],
        "job_complete": False,
    }
    if out.status != "done" or not out.payload:
        ctx.record_scenario(rec)
        return rec
    job_id = str(out.payload["str"].get("job") or out.op_id)
    rec["job_id"] = job_id
    rec["start_str"] = dict(out.payload["str"])
    rec["start_num"] = dict(out.payload["num"])
    rec["snap_tick_ms"] = float(out.payload["num"].get("snap_tick_ms", 0.0))
    rec["start_result_t_ms"] = _bridge_op_result_t(_bridge_events(ctx), out.op_id)
    rec["start_first_t_ms"] = _bridge_op_first_t(_bridge_events(ctx), out.op_id)
    rec["center_x_m"] = float(out.payload["num"].get("center_x_m", cx))
    rec["center_z_m"] = float(out.payload["num"].get("center_z_m", cz))
    rec["radius_m"] = float(out.payload["num"].get("radius_m", rad))

    if busy_probe:
        probe_payload = wire.pack_payload(
            scalars_str={"area_tag": f"contention_probe:{area_id}"},
            scalars_num={
                "center_x_m": cx,
                "center_z_m": cz,
                "radius_m": rad,
                "include_director_b": 0.0,
            },
        )
        probe = f03_common.issue_one(ctx, "server", "per_census_start", probe_payload, qa_fault=busy_fault)
        ctx.record_scenario({
            "ev": "census_busy_probe",
            "area_id": area_id,
            "status": probe.status,
            "reason": probe.reason,
            "op_id": probe.op_id,
        })
        # Mutante census_resource_bypass: el recurso no protege y el segundo censo se acepta.
        # Hay que consumirlo (paginas + job_free) para no dejar un trabajo vivo colgado.
        if probe.status == "done" and probe.payload:
            probe_jid = str(probe.payload["str"].get("job") or probe.op_id)
            probe_state = ""
            probe_deadline = time.monotonic() + 60.0
            while time.monotonic() < probe_deadline:
                probe_page = f03_common.issue_one(
                    ctx, "server", "job_read",
                    wire.pack_payload(scalars_str={"job": probe_jid}, scalars_num={"page_n": 0.0}),
                )
                if probe_page.status != "done" or not probe_page.payload:
                    break
                probe_state = str(probe_page.payload["str"].get("state") or "")
                if probe_state in TERMINAL_STATES:
                    break
                time.sleep(0.02)
            if probe_state == "done":
                try:
                    f03_common.read_job_pages(ctx, "server", probe_jid, timeout_ms=30000)
                except Exception:
                    pass
            _job_free(ctx, probe_jid)

    state = ""
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        probe_page = f03_common.issue_one(
            ctx, "server", "job_read",
            wire.pack_payload(scalars_str={"job": job_id}, scalars_num={"page_n": 0.0}),
        )
        if probe_page.status != "done" or not probe_page.payload:
            break
        state = str(probe_page.payload["str"].get("state") or "")
        if state in TERMINAL_STATES:
            break
        time.sleep(0.02)

    rows = []
    if state == "done":
        try:
            pages = f03_common.read_job_pages(ctx, "server", job_id, timeout_ms=30000)
            rows = list(pages.get("rows") or [])
            rec["job_complete"] = True
            rec["job_num"] = dict(pages.get("num") or {})
        except Exception as exc:
            rec["pages_error"] = str(exc)
    if defer_free:
        rec["free_status"] = "deferred"
    else:
        free = _job_free(ctx, job_id)
        rec["free_status"] = free.status
    rec["rows"] = rows
    rec["state"] = state
    ctx.record_scenario(rec)
    return rec


def _collect_creature_tracks(rec, lids, tracks, obs_req_t):
    for row in rec.get("rows") or []:
        lid = str(row.get("own_logical_id") or "")
        if lid not in lids:
            continue
        tracks.append({
            "logical_id": lid,
            "stage": rec.get("stage"),
            "area_id": rec.get("area_id"),
            "x_m": float(row.get("pos_x_m", 0.0)),
            "z_m": float(row.get("pos_z_m", 0.0)),
            "snap_tick_ms": float(rec.get("snap_tick_ms", 0.0)),
            "start_first_t_ms": rec.get("start_first_t_ms"),
            "obs_req_t": float(obs_req_t),
        })


def _restart_server_live(ctx, old_epoch, director_uid_t0):
    """t4 en diag/retail: el operador reinicia DayZServer y reconecta el mismo director."""
    instructions = (
        "Reinicia DayZServer (proceso real) y reconecta el cliente con el mismo personaje "
        f"(director_uid={director_uid_t0}). El epoch del servidor debe cambiar respecto a {old_epoch}."
    )

    def _new_server_hello(ev):
        if ev.get("ev") != "hello" or ev.get("http") != 200 or ev.get("peer") != "server":
            return False
        args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
        inst = str(ev.get("inst") or args.get("inst") or "")
        return inst != "" and inst != old_epoch

    res = f03_common.await_operator(
        ctx,
        step="t4_restart",
        action="restart_server_and_reconnect_director",
        instructions=instructions,
        predicate=_new_server_hello,
        timeout_s=600.0,
    )
    if not res.get("ok"):
        ctx.record_scenario({
            "ev": "live_restart_failed",
            "reason": str(res.get("reason") or "not_implemented_live_restart"),
        })
        return ""

    deadline = time.monotonic() + 120.0
    new_epoch = ""
    while time.monotonic() < deadline:
        st = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
        if st.status == "done" and st.payload:
            new_epoch = str(st.payload["str"].get("server_epoch") or "")
            n = st.payload["num"]
            uid = str(st.payload["str"].get("director_uid") or "")
            if (
                new_epoch
                and new_epoch != old_epoch
                and uid == director_uid_t0
                and int(round(float(n.get("director_present_b", 0.0)))) == 1
                and int(round(float(n.get("director_alive_b", 0.0)))) == 1
                and int(round(float(n.get("director_inv_readable_b", 0.0)))) == 1
            ):
                return new_epoch
        time.sleep(2.0)
    ctx.record_scenario({"ev": "live_restart_failed", "reason": "director_not_reconnected"})
    return ""


def _restart_server(ctx, old_epoch, director_uid_t0=""):
    if ctx.build in ("diag", "retail"):
        return _restart_server_live(ctx, old_epoch, director_uid_t0)
    return _restart_server_offline(ctx, old_epoch)


def _restart_server_offline(ctx, old_epoch):
    proc = ctx.procs.get("server")
    if proc is not None and proc.poll() is None:
        # N49: deja al peer viejo sondear una vez mas tras su ultima lectura (keepalive observable)
        # y deja que el bridge drene las peticiones en vuelo antes de matarlo, para que no quede
        # ninguna peticion del epoch viejo que el bridge procese despues del hello nuevo.
        time.sleep(0.25)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        # Deja que el handler del bridge termine su long-poll en vuelo del peer viejo
        # (hold_ms como maximo) y escriba su 200 antes de registrar el hello del epoch nuevo;
        # si no, el handler viejo ve el hello nuevo y emite un 409 tardio (N49: ningun evento
        # del epoch viejo despues del hello nuevo) contra un socket ya cerrado.
        drain_s = float(getattr(ctx.bridge, "hold_ms", 2000)) / 1000.0 + 0.2
        time.sleep(drain_s)
        # El 200 del ultimo long-poll del peer viejo se escribe contra un socket ya cerrado
        # (ConnectionResetError) y el bridge lo guarda como fallo; es esperado al matar el peer
        # y no debe tumbar las ordenes del epoch nuevo.
        fail = getattr(ctx.bridge, "failure", None)
        if isinstance(fail, (ConnectionResetError, ConnectionAbortedError)):
            ctx.bridge.failure = None
    cfg_path = ctx.profiles["server"] / "dsbx_qa.json"
    log_path = ctx.peer_logs["server"]
    log_fh = log_path.open("a", encoding="utf-8", newline="\n")
    ctx._log_handles.append(log_fh)
    cmd = [
        sys.executable,
        str(f03_common.FAKE_PEER),
        "--peer", "server",
        "--config", str(cfg_path),
        "--rpc-port", str(f03_common._free_udp_port()),
    ]
    if ctx.git_head:
        cmd.extend(["--git-head", ctx.git_head])
    elif ctx.expected_stamp:
        cmd.extend(["--probe-ver", f"dsbx-qa1+{ctx.expected_stamp}"])
    new_proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    ctx.procs["server"] = new_proc
    ctx.fake_peer_pids["server"] = new_proc.pid
    # El testigo comun (E9) solo aprende los PIDs en PartContext._spawn_peers; el reinicio de mundo
    # lanza un proceso nuevo fuera de esa ruta. Si el testigo esta activo, se le registra el PID real.
    try:
        from tests import e2e_witness as _witness
        _active = getattr(_witness, "_ACTIVE", None)
        if _active is not None:
            _rec = _active._rec_for(ctx)
            if _rec is not None:
                _rec.pids.setdefault("server", set()).add(new_proc.pid)
    except Exception:
        pass
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        reg = ctx.bridge.registered("server")
        if reg and reg != old_epoch:
            return str(reg)
        time.sleep(0.02)
    return str(ctx.bridge.registered("server") or "")


def _record_ledger(ctx, ledger_rows):
    for row in ledger_rows:
        ctx.record_scenario({"ev": "ledger_entry", **row})


def _ground_queries(ctx, scene_id, ledger_rows):
    ground_y_by_lid = {}
    for row in ledger_rows:
        if row["parent_id"] != "":
            continue
        gq = f03_common.issue_one(
            ctx, "server", "ground_query",
            {
                "pos": [row["req_x_m"], 0.0, row["req_z_m"]],
                "ypr": [0.0, 0.0, 0.0],
                "fog": 0.0,
                "count": 1,
                "x": row["req_x_m"],
                "z": row["req_z_m"],
            },
        )
        gy = 0.0
        if gq.status == "done" and isinstance(gq.read, dict) and isinstance(gq.read.get("y"), (int, float)):
            gy = float(gq.read["y"])
        ctx.record_scenario({
            "ev": "ground_query_t1",
            "scene_id": scene_id,
            "logical_id": row["logical_id"],
            "req_x_m": row["req_x_m"],
            "req_z_m": row["req_z_m"],
            "ground_y_m": gy,
            "status": gq.status,
        })
        ground_y_by_lid[row["logical_id"]] = gy
    return ground_y_by_lid


def _apply_scene(ctx, fixture, scene_id, scene_op_id, expect_epoch, gen_n, q9_pathway, qa_fault=None):
    wire_rows, ledger_rows = _build_scene_rows(fixture, scene_id)
    payload = wire.pack_payload(
        scalars_str={
            "scene_id": scene_id,
            "scene_op_id": scene_op_id,
            "expect_epoch": expect_epoch,
            "q9_pathway": q9_pathway,
        },
        scalars_num={"gen_n": float(gen_n)},
        num_cols=IN_NCOL,
        str_cols=IN_SCOL,
        row_dicts=wire_rows,
    )
    return f03_common.issue_one(ctx, "server", "per_apply_scene", payload, qa_fault=qa_fault)


def _spawn_raw(ctx, fixture, tag):
    cfg = fixture["raw_spawns"][tag]
    payload = wire.pack_payload(
        scalars_str={
            "tag": tag,
            "mode": str(cfg["mode"]),
            "class_name": str(cfg["class_name"]),
            "child_cargo_class": str(cfg.get("child_cargo_class") or ""),
            "target_scene_id": str(cfg.get("target_scene_id") or ""),
            "target_parent_id": str(cfg.get("target_parent_id") or ""),
        },
        scalars_num={
            "x_m": float(cfg["x_m"]),
            "z_m": float(cfg["z_m"]),
            "yaw_deg": float(cfg.get("yaw_deg", 0.0)),
            "health_mark_ratio": float(cfg.get("health_mark_ratio", 0.0)),
        },
    )
    return f03_common.issue_one(ctx, "server", "per_spawn_raw", payload)


def _transition(ctx, scene_id, logical_id, action, expect_epoch, target_scene="", target_parent=""):
    payload = wire.pack_payload(
        scalars_str={
            "scene_id": scene_id,
            "logical_id": logical_id,
            "action": action,
            "expect_epoch": expect_epoch,
            "target_scene_id": target_scene,
            "target_parent_id": target_parent,
        }
    )
    return f03_common.issue_one(ctx, "server", "per_child_transition", payload)


def _reset_scene(ctx, scene_id, reset_op_id, expect_epoch, qa_fault=None):
    payload = wire.pack_payload(
        scalars_str={
            "scene_id": scene_id,
            "reset_op_id": reset_op_id,
            "expect_epoch": expect_epoch,
        }
    )
    return f03_common.issue_one(ctx, "server", "per_reset_scene", payload, qa_fault=qa_fault)


def _tracks_speed(obs_list):
    v_m_s = 6.0
    for i in range(1, len(obs_list)):
        dt_s = (float(obs_list[i]["snap_tick_ms"]) - float(obs_list[i - 1]["snap_tick_ms"])) / 1000.0
        if dt_s > 1e-3:
            dist_m = math.hypot(
                float(obs_list[i]["x_m"]) - float(obs_list[i - 1]["x_m"]),
                float(obs_list[i]["z_m"]) - float(obs_list[i - 1]["z_m"]),
            )
            v_m_s = max(v_m_s, dist_m / dt_s)
    return v_m_s


def _n49_covered(obs, t5_censuses, dt_pre_ms, v_bound_m_s, first_new_tick_ms=0.0):
    for c in t5_censuses:
        if not c.get("job_complete"):
            continue
        snap = float(c.get("snap_tick_ms", 0.0))
        if snap <= 0.0:
            continue
        # N49 (eval :2655): solo censos del epoch nuevo, desde su primer tick acreditado.
        if first_new_tick_ms > 0.0 and snap < first_new_tick_ms:
            continue
        res_t = c.get("start_result_t_ms")
        hello_t = c.get("hello_t_ms")
        if res_t is None or hello_t is None:
            continue
        dt_post_ms = max(snap, float(res_t) - float(hello_t), 0.0)
        reach = max(15.0, v_bound_m_s * (dt_pre_ms + dt_post_ms) / 1000.0)
        dist = math.hypot(float(obs["x_m"]) - float(c["center_x_m"]), float(obs["z_m"]) - float(c["center_z_m"]))
        if dist + reach <= float(c["radius_m"]) + 1e-6:
            return True
    return False


def _scene_creature_q9_failed(fixture, scene_id, app_payload, ground_y_by_lid):
    creatures = {
        e["logical_id"]
        for e in fixture["scenes"].get(scene_id, {}).get("entities", [])
        if e.get("cat") in ("infected", "animal")
    }
    if not creatures:
        return False
    fix = {e["logical_id"]: e for e in fixture["scenes"].get(scene_id, {}).get("entities", [])}
    for row in app_payload.get("rows") or []:
        lid = str(row.get("logical_id") or "")
        if lid not in creatures:
            continue
        ent = fix.get(lid)
        if ent is None:
            continue
        gy = float(ground_y_by_lid.get(lid, 0.0))
        exp = (float(ent["req_x_m"]), gy, float(ent["req_z_m"]))
        got = (
            float(row.get("q9_x_m", 0.0)),
            float(row.get("q9_y_m", 0.0)),
            float(row.get("q9_z_m", 0.0)),
        )
        err_abs = math.sqrt(sum((got[i] - exp[i]) ** 2 for i in range(3)))
        if err_abs >= 0.5 - 1e-5 or float(row.get("q9_err_3d_m", 0.0)) >= 0.5 - 1e-5:
            return True
    return False


def run_part(args, base_dir, argv, part_name, *, drop_control_pre_restart=False):
    base_dir = Path(base_dir)
    fixture = _fixture()
    cfg = _part_config(part_name, fixture)
    with f03_common.PartContext(
        base_dir=base_dir,
        part_name=part_name,
        spike_id=SPIKE_ID,
        args=args,
        argv=argv,
    ) as ctx:
        if ctx.startup_reason is not None:
            ctx.collect_probe_budget_logs()
            ctx.finalize_manifest()
            verdict = s_persist_eval.evaluate(ctx.part_dir, repo_root=REPO_ROOT)
            gate_core.write_json(ctx.part_dir / "verdict.json", verdict)
            return verdict

        git_head = ctx.git_head or ""
        expected_stamp = ctx.expected_stamp or ""
        ctx.record_scenario({
            "ev": "probe_sources_at_commit",
            "git_head": git_head,
            "probe_stamp": expected_stamp,
            "persist_files": _probe_sources_at_commit(git_head),
        })

        if cfg["mutant"]:
            if cfg["bypass_contention"]:
                effect = {"resource": "per_census", "bypass": True}
                target = "DSBX_QA_X_Persist::HandleCensusStart"
            else:
                effect = {
                    "scene_id": cfg["retained_scene"],
                    "qa_fault": cfg["reset_fault"] or list(cfg["apply_faults"].values())[0],
                }
                target = "DSBX_QA_X_Persist"
            ctx.write_injection(
                mutant=cfg["mutant"],
                kind="enforce_fault",
                target=target,
                observable_effect=effect,
            )

        is_live = ctx.build in ("diag", "retail")
        storage_env = _storage_env() if is_live else None
        if is_live and storage_env is not None:
            # BLOQ 3: rutas delimitadas antes de cualquier operacion.
            storage_env = _validate_storage_env(storage_env, backup_dir=None)
        if is_live and storage_env is None:
            ctx.record_scenario({"ev": "storage_config_invalid"})
        sim_storage = ctx.part_dir / "_sim_storage"
        backup_dir = ctx.part_dir / "_storage_backup"
        storage_t0 = None

        try:
            if is_live and storage_env is not None:
                if _server_state(storage_env) != "stopped":
                    f03_common.await_operator(
                        ctx,
                        step="t0_stop_server_for_cold_backup",
                        action="stop_server",
                        instructions="Para DayZServer para el backup en frio de $mission:storage_#.",
                        predicate=lambda _ev: _server_state(storage_env) == "stopped",
                        timeout_s=300.0,
                    )
                # BLOQ 2: parada comprobada inmediatamente antes de copiar;
                # si no se acredita, _backup_storage falla sin copiar.
                try:
                    storage_t0 = _backup_storage(storage_env, backup_dir, "t0")
                except Exception as exc:
                    ctx.record_scenario({
                        "ev": "storage_restore_result",
                        "restore_ok_b": 0,
                        "restore_incomplete_b": 1,
                        "error": f"storage_backup_incomplete:{exc}",
                        "files": {},
                    })
                    raise
                ctx.record_scenario({"ev": "storage_snapshot_t0", "files": storage_t0})
                start_threshold = ctx.bridge.now_ms()

                def _both_peers_hello_after(ev):
                    if ev.get("ev") != "hello" or ev.get("http") != 200:
                        return False
                    if ev.get("peer") not in ("server", "client"):
                        return False
                    t = ev.get("t_ms")
                    return isinstance(t, (int, float)) and float(t) >= start_threshold

                f03_common.await_operator(
                    ctx,
                    step="t0_start_peers",
                    action="start_server_and_client",
                    instructions="Arranca DayZServer y el cliente QA tras el backup en frio.",
                    predicate=_both_peers_hello_after,
                    timeout_s=600.0,
                )
                verify_reason = ctx._verify_hello_events()
                ctx.record_scenario({"ev": "t0_hello_verify", "reason": verify_reason or ""})
            elif not is_live:
                sim_storage.mkdir(parents=True, exist_ok=True)
                (sim_storage / "objects.bin").write_bytes(b"DSBX_STORAGE_T0_CLEAN\n")
                storage_t0 = _snapshot_dir(sim_storage)
                # BLOQ 4: slot nuevo; un backup previo nunca se borra.
                shutil.copytree(sim_storage, _unique_backup_path(backup_dir))
                ctx.record_scenario({"ev": "storage_snapshot_t0", "files": storage_t0})

            st_t0 = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
            server_epoch_old = ""
            director_uid_t0 = ""
            if st_t0.status == "done" and st_t0.payload:
                server_epoch_old = str(st_t0.payload["str"].get("server_epoch") or "")
                director_uid_t0 = str(st_t0.payload["str"].get("director_uid") or "")
            ctx.record_scenario({
                "ev": "t0_status",
                "status": st_t0.status,
                "server_epoch": server_epoch_old,
                "director_uid": director_uid_t0,
                "num": dict(st_t0.payload["num"]) if st_t0.payload else {},
            })

            baseline_director_rows = []
            for idx, area_id in enumerate(cfg["base_areas"]):
                include_dir = 1 if area_id == "area_a" else 0
                if idx == 0 and cfg["bypass_contention"]:
                    rec = _census(
                        ctx, fixture, "t0_baseline_census", area_id, include_dir,
                        busy_probe=True, busy_fault="census_resource_bypass",
                    )
                else:
                    rec = _census(ctx, fixture, "t0_baseline_census", area_id, include_dir, busy_probe=(idx == 0))
                if include_dir == 1:
                    for row in rec.get("rows") or []:
                        if row.get("owner_uid") == director_uid_t0 and row.get("class_name") not in fixture["sentinel_classes"]:
                            baseline_director_rows.append(row)
            ctx.record_scenario({
                "ev": "baseline_director_foreign",
                "director_uid": director_uid_t0,
                "rows": baseline_director_rows,
            })

            creature_lids = {f"{cfg['pfx']}_inf_1", f"{cfg['pfx']}_ani_1", "b_inf_1", "b_ani_1"}
            apply_spawn_ticks = {}
            for scene_id in cfg["active_scenes"]:
                _wire_rows, ledger_rows = _build_scene_rows(fixture, scene_id)
                _record_ledger(ctx, ledger_rows)
                ground_y_by_lid = _ground_queries(ctx, scene_id, ledger_rows)
                scene_op_id = ctx.peek_next_op_id()
                fault = cfg["apply_faults"].get(scene_id)
                final_gen = 1
                final_pathway = "a"
                app = _apply_scene(ctx, fixture, scene_id, scene_op_id, server_epoch_old, final_gen, final_pathway, qa_fault=fault)
                ctx.record_scenario({
                    "ev": "apply_scene_t1",
                    "scene_id": scene_id,
                    "scene_op_id": scene_op_id,
                    "status": app.status,
                    "reason": app.reason,
                })
                if app.status == "done" and app.payload and _scene_creature_q9_failed(fixture, scene_id, app.payload, ground_y_by_lid):
                    reset_op = ctx.peek_next_op_id()
                    reset_out = _reset_scene(ctx, scene_id, reset_op, server_epoch_old)
                    ctx.record_scenario({
                        "ev": "apply_scene_contingency_reset_t1",
                        "scene_id": scene_id,
                        "reset_op_id": reset_op,
                        "status": reset_out.status,
                        "reason": reset_out.reason,
                    })
                    final_gen = 2
                    final_pathway = "b"
                    scene_op_id = ctx.peek_next_op_id()
                    app = _apply_scene(ctx, fixture, scene_id, scene_op_id, server_epoch_old, final_gen, final_pathway, qa_fault=fault)
                    ctx.record_scenario({
                        "ev": "apply_scene_contingency_t1",
                        "scene_id": scene_id,
                        "scene_op_id": scene_op_id,
                        "gen_n": final_gen,
                        "q9_pathway": final_pathway,
                        "status": app.status,
                        "reason": app.reason,
                    })
                if app.status == "done" and app.payload:
                    for row in app.payload.get("rows") or []:
                        lid = row.get("logical_id")
                        if lid in creature_lids:
                            apply_spawn_ticks[lid] = float(row.get("spawn_tick_ms", 0.0))
                        ctx.record_scenario({
                            "ev": "ledger_spawn_recorded",
                            "kind": "scene",
                            "scene_id": scene_id,
                            "logical_id": lid,
                            "class_name": row.get("class_name"),
                            "net_id_t1": row.get("net_id"),
                            "init_max_hp": row.get("max_hp"),
                            "init_health_hp": row.get("health_hp"),
                            "spawn_tick_ms": row.get("spawn_tick_ms"),
                        })
                if scene_id == cfg["retained_scene"]:
                    dup = _apply_scene(ctx, fixture, scene_id, scene_op_id, server_epoch_old, final_gen, final_pathway, qa_fault=fault)
                    ctx.record_scenario({
                        "ev": "apply_scene_idempotent_t1",
                        "scene_id": scene_id,
                        "scene_op_id": scene_op_id,
                        "status": dup.status,
                        "reason": dup.reason,
                    })

            for tag in cfg["raw_tags"]:
                raw = _spawn_raw(ctx, fixture, tag)
                ctx.record_scenario({
                    "ev": "spawn_raw_t1",
                    "tag": tag,
                    "status": raw.status,
                    "reason": raw.reason,
                })
                if raw.status == "done" and raw.payload:
                    rs = raw.payload["str"]
                    rn = raw.payload["num"]
                    ctx.record_scenario({
                        "ev": "ledger_spawn_recorded",
                        "kind": "raw",
                        "tag": tag,
                        "mode": str(fixture["raw_spawns"][tag]["mode"]),
                        "class_name": str(rs.get("class_name") or ""),
                        "net_id_t1": str(rs.get("net_id") or ""),
                        "pers_id_t1": str(rs.get("pers_id") or ""),
                        "init_max_hp": float(rn.get("max_hp", 0.0)),
                        "init_health_hp": float(rn.get("health_hp", 0.0)),
                    })

            for area_id in cfg["base_areas"]:
                _census(ctx, fixture, "t1_pre_transition_census", area_id, 1 if area_id in ("area_a", "area_b") else 0)

            transitions = [
                ("scene_a_clean", "ac_act_1_armband_drop", "drop_to_ground", "", ""),
                ("scene_a_clean", "ac_act_1_gloves_dir", "move_to_director", "", ""),
                ("scene_b", "b_act_1_armband_drop", "drop_to_ground", "", ""),
                ("scene_b", "b_act_1_gloves_dir", "move_to_director", "", ""),
                ("scene_b", "b_cross_child", "move_to_container", cfg["cross_scene"], cfg["cross_parent"]),
            ]
            for t_scene, t_lid, t_action, t_sc, t_par in transitions:
                tr = _transition(ctx, t_scene, t_lid, t_action, server_epoch_old, t_sc, t_par)
                ctx.record_scenario({
                    "ev": "child_transition_t1",
                    "scene_id": t_scene,
                    "logical_id": t_lid,
                    "action": t_action,
                    "status": tr.status,
                    "reason": tr.reason,
                })

            for area_id in cfg["base_areas"]:
                _census(ctx, fixture, "t1_post_transition_census", area_id, 1 if area_id in ("area_a", "area_b") else 0)
            ctx.record_scenario({"ev": "storage_snapshot_t1", "files": _snapshot_stage(is_live, storage_env, sim_storage)})

            creature_tracks = []
            if is_live and apply_spawn_ticks:
                spawn_max = max(apply_spawn_ticks.values())
                wait_deadline = time.monotonic() + 900.0
                waited = 0.0
                while time.monotonic() < wait_deadline:
                    st_wait = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
                    tick_ms = 0.0
                    if st_wait.status == "done" and st_wait.payload:
                        tick_ms = float(st_wait.payload["num"].get("tick_ms", 0.0))
                    waited = tick_ms - spawn_max
                    if waited >= 600000.0:
                        break
                    time.sleep(30.0)
                ctx.record_scenario({
                    "ev": "t2_hold_wait",
                    "spawn_max_tick_ms": spawn_max,
                    "last_tick_ms": spawn_max + waited,
                    "elapsed_ms": waited,
                    "satisfied": 1 if waited >= 600000.0 else 0,
                })
            for area_id in cfg["creature_areas"]:
                obs_req_t = time.time()
                rec_t2 = _census(ctx, fixture, "t2_census_10min", area_id, 0)
                _collect_creature_tracks(rec_t2, creature_lids, creature_tracks, obs_req_t)
            ctx.record_scenario({"ev": "storage_snapshot_t2", "files": _snapshot_stage(is_live, storage_env, sim_storage)})

            t3_director_areas = {cfg["retained_area"], "area_a", "area_b"}
            for area_id in cfg["base_areas"]:
                obs_req_t = time.time()
                rec_t3p = _census(ctx, fixture, "t3_pre_reset_census", area_id, 1 if area_id in t3_director_areas else 0)
                _collect_creature_tracks(rec_t3p, creature_lids, creature_tracks, obs_req_t)

            for attempt in (1, 2):
                rc_op = ctx.peek_next_op_id()
                rc = _reset_scene(ctx, "scene_a_clean", rc_op, server_epoch_old)
                ctx.record_scenario({
                    "ev": f"reset_scene_clean_{attempt}_t3",
                    "scene_id": "scene_a_clean",
                    "attempt": attempt,
                    "status": rc.status,
                    "reason": rc.reason,
                })

            rr_op = ctx.peek_next_op_id()
            rr = _reset_scene(ctx, cfg["retained_scene"], rr_op, server_epoch_old, qa_fault=(cfg["reset_fault"] or None))
            rr_tick_ms = 0.0
            if rr.status == "done" and rr.payload:
                rr_tick_ms = float(rr.payload["num"].get("tick_ms", 0.0))
            ctx.record_scenario({
                "ev": "reset_scene_retained_t3",
                "scene_id": cfg["retained_scene"],
                "area_id": cfg["retained_area"],
                "status": rr.status,
                "reason": rr.reason,
                "tick_ms": rr_tick_ms,
            })

            t3_post_snap_by_area = {}
            for area_id in cfg["base_areas"]:
                obs_req_t = time.time()
                rec_t3q = _census(ctx, fixture, "t3_post_reset_census", area_id, 1 if area_id in t3_director_areas else 0)
                t3_post_snap_by_area[area_id] = float(rec_t3q.get("snap_tick_ms", 0.0))
                _collect_creature_tracks(rec_t3q, creature_lids, creature_tracks, obs_req_t)

            if drop_control_pre_restart:
                _census(ctx, fixture, "t3_post_reset_census", "area_c", 0, qa_fault="drop_ctrl_pre_restart")

            stop_status = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
            ctx.record_scenario({
                "ev": "t3_stop_status",
                "status": stop_status.status,
                "num": dict(stop_status.payload["num"]) if stop_status.payload else {},
            })

            server_epoch_new = _restart_server(ctx, server_epoch_old, director_uid_t0)
            st_t4 = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
            first_new_tick_ms = 0.0
            if st_t4.status == "done" and st_t4.payload:
                server_epoch_new = str(st_t4.payload["str"].get("server_epoch") or server_epoch_new)
                first_new_tick_ms = float(st_t4.payload["num"].get("tick_ms", 0.0))
            ctx.record_scenario({
                "ev": "t4_post_restart_status",
                "status": st_t4.status,
                "server_epoch_old": server_epoch_old,
                "server_epoch_new": server_epoch_new,
            })

            events_after_restart = _bridge_events(ctx)
            hello_t_ms = _bridge_hello_t(events_after_restart, server_epoch_new)
            stop_first_t_ms = _bridge_op_first_t(events_after_restart, stop_status.op_id) if stop_status else None
            stop_tick_ms = float(stop_status.payload["num"].get("tick_ms", 0.0)) if (stop_status and stop_status.payload) else 0.0
            stop_window_ms = 0.0
            if hello_t_ms is not None and stop_first_t_ms is not None and hello_t_ms >= stop_first_t_ms:
                stop_window_ms = float(hello_t_ms) - float(stop_first_t_ms)
            max_old_srv_tick_ms = max(
                [stop_tick_ms, rr_tick_ms, _bridge_old_max_tick_ms(events_after_restart, hello_t_ms)]
                + [float(v) for v in t3_post_snap_by_area.values()]
            )

            t5_director_areas = {cfg["retained_area"], "area_a", "area_b"}
            t5_censuses = []
            for area_id in cfg["base_areas"]:
                rec_t5 = _census(ctx, fixture, "t5_post_restart_census", area_id, 1 if area_id in t5_director_areas else 0)
                rec_t5["hello_t_ms"] = hello_t_ms
                t5_censuses.append(rec_t5)

            # Duracion bridge medida de un censo t5 (first->result): proyecta el dt_post
            # del censo aun no lanzado hasta su propio resultado, con la misma formula N49.
            t5_census_dur_ms = 0.0
            for c0 in t5_censuses:
                f0 = c0.get("start_first_t_ms")
                r0 = c0.get("start_result_t_ms")
                if f0 is not None and r0 is not None and float(r0) > float(f0):
                    t5_census_dur_ms = max(t5_census_dur_ms, float(r0) - float(f0))

            # Latencia de dimensionado registrada de verdad: cuanto crece el dt_post
            # real de un disco sobre la cota inferior medida al dimensionarlo
            # (tick del per_status y reloj del bridge de ese instante). Arranca con
            # la duracion first->result de los censos t5 base y se corrige con el
            # snap/resultado reales de cada disco lanzado.
            sizing_latency_ms = t5_census_dur_ms

            tracks_by_lid = {}
            for trk in creature_tracks:
                tracks_by_lid.setdefault(trk["logical_id"], []).append(trk)

            retained_creature_lids = {f"{cfg['pfx']}_inf_1", f"{cfg['pfx']}_ani_1"}
            for lid, obs_list in tracks_by_lid.items():
                obs_list = sorted(obs_list, key=lambda o: float(o["snap_tick_ms"]))
                if lid in retained_creature_lids:
                    stages = ("t2_census_10min", "t3_pre_reset_census")
                    reset_branch = True
                else:
                    stages = ("t2_census_10min", "t3_pre_reset_census", "t3_post_reset_census")
                    reset_branch = False
                relevant = [o for o in obs_list if o.get("stage") in stages and float(o.get("snap_tick_ms", 0.0)) > 0.0]
                if not relevant:
                    continue
                last_obs_tick = float(relevant[-1]["snap_tick_ms"])
                v_m_s = _tracks_speed(relevant)
                if reset_branch:
                    post_ret_snap = float(t3_post_snap_by_area.get(cfg["retained_area"], 0.0))
                    # N49 rama reset (eval :2629): misma formula, sin atajo optimista.
                    dt_pre_ms = (
                        max(0.0, rr_tick_ms - last_obs_tick)
                        + max(0.0, max_old_srv_tick_ms - post_ret_snap)
                        + stop_window_ms
                    )
                else:
                    dt_pre_ms = max(0.0, max_old_srv_tick_ms - last_obs_tick) + stop_window_ms
                    last_obs_first = relevant[-1].get("start_first_t_ms")
                    if hello_t_ms is not None and last_obs_first is not None:
                        dt_pre_ms = max(dt_pre_ms, float(hello_t_ms) - float(last_obs_first))

                for idx, trk in enumerate(relevant):
                    if _n49_covered(trk, t5_censuses, dt_pre_ms, v_m_s, first_new_tick_ms):
                        continue
                    prev_actual_dt_post_ms = None
                    prev_result_t_ms = None
                    prev_required_radius_m = 0.0
                    for attempt in range(5):
                        # Misma formula N49 (eval :2662) para dimensionar y para reintentar:
                        # dt_post = max(snap_del_proceso_nuevo, resultado_en_bridge - hello).
                        # Para el censo aun no lanzado, snap >= tick actual del proceso nuevo
                        # y resultado >= ahora en el bridge; ambos son cotas inferiores del
                        # mismo termino, y sobre ellas se suma la latencia registrada de
                        # verdad en los discos ya lanzados (su snap/resultado reales menos
                        # la cota medida al dimensionarlos), no una duracion ajena.
                        st_disc = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
                        tick_now = 0.0
                        if st_disc.status == "done" and st_disc.payload:
                            tick_now = float(st_disc.payload["num"].get("tick_ms", 0.0))
                        bridge_now_ms = float(ctx.bridge.now_ms())
                        bridge_dt_post = 0.0
                        if hello_t_ms is not None:
                            bridge_dt_post = max(0.0, bridge_now_ms - float(hello_t_ms))
                        lower_dt_post_ms = max(tick_now, bridge_dt_post, 0.0)
                        dt_post_est = lower_dt_post_ms + sizing_latency_ms
                        if prev_actual_dt_post_ms is not None and prev_result_t_ms is not None:
                            # El siguiente disco no puede tener un dt_post menor que el
                            # real del disco fallido mas el tiempo de bridge ya pasado
                            # desde su resultado registrado.
                            dt_post_est = max(
                                dt_post_est,
                                prev_actual_dt_post_ms + max(0.0, bridge_now_ms - float(prev_result_t_ms)),
                            )
                        reach_m = max(15.0, v_m_s * (dt_pre_ms + dt_post_est) / 1000.0)
                        radius_m = max(60.0, reach_m * (1 + SLACK_REL) + SLACK_ABS_M, prev_required_radius_m)
                        track_tag = f"t5_track_{lid}_p{idx}_r{attempt}"
                        rec_disc = _census(
                            ctx, fixture, "t5_post_restart_census", track_tag, 0,
                            center_override=(trk["x_m"], trk["z_m"]),
                            radius_override=radius_m,
                        )
                        rec_disc["hello_t_ms"] = hello_t_ms
                        t5_censuses.append(rec_disc)
                        ctx.record_scenario({
                            "ev": "t5_track_disc",
                            "area_tag": track_tag,
                            "logical_id": lid,
                            "stage": trk["stage"],
                            "center_x_m": trk["x_m"],
                            "center_z_m": trk["z_m"],
                            "radius_m": radius_m,
                            "reach_m": reach_m,
                            "v_m_s": v_m_s,
                            "dt_pre_ms": dt_pre_ms,
                            "dt_post_est_ms": dt_post_est,
                            "attempt": attempt,
                        })
                        d_first = rec_disc.get("start_first_t_ms")
                        d_res = rec_disc.get("start_result_t_ms")
                        if d_first is not None and d_res is not None and float(d_res) > float(d_first):
                            t5_census_dur_ms = max(t5_census_dur_ms, float(d_res) - float(d_first))
                        # Registra el dt_post real de este disco (formula del oraculo)
                        # para corregir la latencia de dimensionado del siguiente.
                        d_snap = float(rec_disc.get("snap_tick_ms", 0.0))
                        if rec_disc.get("job_complete") and d_snap > 0.0 and d_res is not None and hello_t_ms is not None:
                            actual_dt_post_ms = max(d_snap, float(d_res) - float(hello_t_ms), 0.0)
                            sizing_latency_ms = max(sizing_latency_ms, actual_dt_post_ms - lower_dt_post_ms)
                            prev_actual_dt_post_ms = actual_dt_post_ms
                            prev_result_t_ms = float(d_res)
                            dist_m = math.hypot(
                                float(trk["x_m"]) - float(rec_disc["center_x_m"]),
                                float(trk["z_m"]) - float(rec_disc["center_z_m"]),
                            )
                            prev_required_radius_m = dist_m + max(15.0, v_m_s * (dt_pre_ms + actual_dt_post_ms) / 1000.0)
                        if _n49_covered(trk, [rec_disc], dt_pre_ms, v_m_s, first_new_tick_ms):
                            break
                        # El siguiente intento recalcula arriba con la misma formula,
                        # la latencia registrada de este disco y los relojes avanzados.

            witness_rows, _ = _build_scene_rows(fixture, "scene_b")
            w_op_id = ctx.peek_next_op_id()
            w_app = _apply_scene(ctx, fixture, "scene_b", w_op_id, server_epoch_new, 1, "a")
            ctx.record_scenario({"ev": "t5_witness_apply", "status": w_app.status, "reason": w_app.reason})

            w_pre = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
            ctx.record_scenario({"ev": "t5_witness_pre_status", "status": w_pre.status, "num": dict(w_pre.payload["num"]) if w_pre.payload else {}})
            _census(ctx, fixture, "t5_witness_pre_census", "area_b", 1)

            stale_reset = _reset_scene(ctx, "scene_b", ctx.peek_next_op_id(), server_epoch_old)
            ctx.record_scenario({"ev": "t5_stale_epoch_reset", "status": stale_reset.status, "reason": stale_reset.reason})
            stale_apply = _apply_scene(ctx, fixture, "scene_b", ctx.peek_next_op_id(), server_epoch_old, 2, "a")
            ctx.record_scenario({"ev": "t5_stale_epoch_apply", "status": stale_apply.status, "reason": stale_apply.reason})

            w_post = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
            ctx.record_scenario({"ev": "t5_witness_post_status", "status": w_post.status, "num": dict(w_post.payload["num"]) if w_post.payload else {}})
            _census(ctx, fixture, "t5_witness_post_census", "area_b", 1)

            _reset_scene(ctx, "scene_b", ctx.peek_next_op_id(), server_epoch_new)

            cleanup_rows = [
                {
                    "area_tag": area_id,
                    "center_x_m": float(fixture["areas"][area_id]["center_x_m"]),
                    "center_z_m": float(fixture["areas"][area_id]["center_z_m"]),
                    "radius_m": float(fixture["areas"][area_id]["radius_m"]),
                }
                for area_id in cfg["base_areas"]
            ]
            track_discs = [
                {
                    "area_id": str(c.get("area_id") or ""),
                    "center_x_m": float(c.get("start_num", {}).get("center_x_m", 0.0)),
                    "center_z_m": float(c.get("start_num", {}).get("center_z_m", 0.0)),
                    "radius_m": float(c.get("start_num", {}).get("radius_m", 0.0)),
                }
                for c in t5_censuses
                if str(c.get("area_id") or "").startswith("t5_track_")
            ]
            for c in track_discs:
                cleanup_rows.append({
                    "area_tag": c["area_id"],
                    "center_x_m": c["center_x_m"],
                    "center_z_m": c["center_z_m"],
                    "radius_m": c["radius_m"],
                })
            cleanup = f03_common.issue_one(
                ctx, "server", "per_cleanup_qa",
                wire.pack_payload(
                    scalars_str={"cleanup_tag": "t6_cleanup"},
                    num_cols=["center_x_m", "center_z_m", "radius_m"],
                    str_cols=["area_tag"],
                    row_dicts=cleanup_rows,
                ),
            )
            ctx.record_scenario({"ev": "t6_cleanup_qa", "status": cleanup.status, "reason": cleanup.reason})

            for area_id in cfg["base_areas"]:
                _census(ctx, fixture, "t6_post_cleanup_census", area_id, 1 if area_id == "area_a" else 0)
            for c in track_discs:
                _census(
                    ctx, fixture, "t6_post_cleanup_census", str(c["area_id"]), 0,
                    center_override=(float(c["center_x_m"]), float(c["center_z_m"])),
                    radius_override=float(c["radius_m"]),
                )

        finally:
            if is_live and storage_env is not None and storage_t0 is not None:
                if _server_state(storage_env) != "stopped":
                    f03_common.await_operator(
                        ctx,
                        step="t6_stop_server_for_cold_restore",
                        action="stop_server",
                        instructions="Para DayZServer para restaurar en frio $mission:storage_#.",
                        predicate=lambda _ev: _server_state(storage_env) == "stopped",
                        timeout_s=300.0,
                    )
                # BLOQ 2/4: _restore_storage exige parada comprobada justo
                # antes de sustituir y nunca borra el backup; cualquier
                # fallo queda como restauracion incompleta en el recibo.
                try:
                    restore_ok, restored_snapshot, restore_err = _restore_storage(
                        storage_env, backup_dir, storage_t0
                    )
                except Exception as exc:
                    restore_ok, restored_snapshot = 0, _snapshot_stage(True, storage_env, sim_storage)
                    restore_err = f"storage_restore_incomplete:{type(exc).__name__}:{exc}"
                ctx.record_scenario({
                    "ev": "storage_restore_result",
                    "restore_ok_b": restore_ok,
                    "restore_incomplete_b": 0 if restore_ok == 1 else 1,
                    "error": restore_err,
                    "files": restored_snapshot,
                })
            elif not is_live and storage_t0 is not None and _resolve_backup_dir(backup_dir) is not None:
                if sim_storage.exists():
                    shutil.rmtree(sim_storage, ignore_errors=True)
                shutil.copytree(_resolve_backup_dir(backup_dir), sim_storage)
                restored_snapshot = _snapshot_dir(sim_storage)
                restore_ok = 1 if restored_snapshot == storage_t0 else 0
                ctx.record_scenario({
                    "ev": "storage_restore_result",
                    "restore_ok_b": restore_ok,
                    "restore_incomplete_b": 0 if restore_ok == 1 else 1,
                    "error": "" if restore_ok == 1 else "storage_restore_incomplete",
                    "files": restored_snapshot,
                })
                # BLOQ 4: el backup se conserva como evidencia de recuperacion.

        ctx.collect_probe_budget_logs()
        ctx.finalize_manifest()

    verdict = s_persist_eval.evaluate(ctx.part_dir, repo_root=REPO_ROOT)
    gate_core.write_json(ctx.part_dir / "verdict.json", verdict)
    return verdict


def _default_stub_args(evidence_dir):
    return argparse.Namespace(
        id=SPIKE_ID,
        build="offline",
        evidence=str(evidence_dir),
        both=True,
        part="all",
        server_profile=None,
        client_profile=None,
        pbo=None,
        peer_timeout=None,
        hold_ms=gate_core.DEFAULT_HOLD_MS,
        lease_ms=gate_core.DEFAULT_LEASE_MS,
        ttl_ms=gate_core.DEFAULT_TTL_MS,
        retry_ms=gate_core.DEFAULT_RETRY_MS,
        seed=gate_core.DEFAULT_SEED,
        fault=None,
    )


def run_control_lost_probe(evidence_dir, base_args=None):
    base_dir = Path(evidence_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    if base_args is None:
        args = _default_stub_args(base_dir)
    else:
        args = argparse.Namespace(**vars(base_args))
        args.evidence = str(base_dir)
    return run_part(args, base_dir, [], "control_lost", drop_control_pre_restart=True)


def run(args, evidence, argv):
    base_dir = Path(evidence)
    part_arg = getattr(args, "part", "all") or "all"
    all_parts = ["run"] + [f"mut-{name}" for name in s_persist_mutants.EXPECTED_MUTANTS]
    parts = all_parts if part_arg == "all" else [part_arg]
    started_utc = gate_core.utc_now()
    last_verdict = None
    for part_name in parts:
        last_verdict = run_part(args, base_dir, argv, part_name)
    if not (base_dir / "manifest.json").is_file():
        gate_core.write_json(
            base_dir / "manifest.json",
            gate_core.make_manifest("spike", SPIKE_ID, args, argv, started_utc, gate_core.utc_now()),
        )
    agg = f03_common.aggregate_spike(base_dir, SPIKE_ID, repo_root=REPO_ROOT)
    if part_arg != "all" and not all((base_dir / p / "verdict.json").is_file() for p in all_parts):
        return int(last_verdict.get("exit_code", 2)) if last_verdict else 2
    return int(agg["exit_code"])


def _build_argparser():
    parser = argparse.ArgumentParser(prog="s_persist_run.py")
    parser.add_argument("--build", default="offline", choices=("offline", "retail", "diag"))
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--both", action="store_true", default=True)
    parser.add_argument("--part", default="all")
    parser.add_argument("--server-profile", default=None)
    parser.add_argument("--client-profile", default=None)
    parser.add_argument("--pbo", default=None)
    parser.add_argument("--peer-timeout", type=float, default=None)
    parser.add_argument("--hold-ms", type=int, default=gate_core.DEFAULT_HOLD_MS)
    parser.add_argument("--lease-ms", type=int, default=gate_core.DEFAULT_LEASE_MS)
    parser.add_argument("--ttl-ms", type=int, default=gate_core.DEFAULT_TTL_MS)
    parser.add_argument("--retry-ms", type=int, default=gate_core.DEFAULT_RETRY_MS)
    parser.add_argument("--seed", type=int, default=gate_core.DEFAULT_SEED)
    parser.add_argument("--fault", default=None)
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = _build_argparser()
    args = parser.parse_args(argv)
    return run(args, Path(args.evidence), argv)


if __name__ == "__main__":
    raise SystemExit(main())
