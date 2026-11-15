"""Runner de S-persist (brief F0.3-0 §5.1, §6). Offline ejecuta los peers falsos como
procesos reales del nucleo (PartContext) y simula el reinicio de mundo matando y
relanzando el peer servidor: la extension persiste en disco solo lo creado sin
ECE_NOPERSISTENCY_WORLD, como haria el storage del motor."""

import argparse
import hashlib
import json
import math
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


def _census(ctx, fixture, stage, area_id, include_dir, *, busy_probe=False, qa_fault=None, defer_free=False):
    area = fixture["areas"][area_id]
    tag = f"{stage}:{area_id}"
    cx = float(area["center_x_m"])
    cz = float(area["center_z_m"])
    rad = float(area["radius_m"])
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
        probe = f03_common.issue_one(ctx, "server", "per_census_start", probe_payload)
        ctx.record_scenario({
            "ev": "census_busy_probe",
            "area_id": area_id,
            "status": probe.status,
            "reason": probe.reason,
            "op_id": probe.op_id,
        })

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


def _restart_server(ctx, old_epoch):
    proc = ctx.procs.get("server")
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
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

        sim_storage = ctx.part_dir / "_sim_storage"
        sim_storage.mkdir(parents=True, exist_ok=True)
        (sim_storage / "objects.bin").write_bytes(b"DSBX_STORAGE_T0_CLEAN\n")
        storage_t0 = _snapshot_dir(sim_storage)
        backup_dir = ctx.part_dir / "_storage_backup"
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)
        shutil.copytree(sim_storage, backup_dir)
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
                rec = _census(ctx, fixture, "t0_baseline_census", area_id, include_dir, defer_free=True)
                _census(ctx, fixture, "contention_probe", area_id, 0)
                _job_free(ctx, rec["job_id"])
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

        for scene_id in cfg["active_scenes"]:
            _wire_rows, ledger_rows = _build_scene_rows(fixture, scene_id)
            _record_ledger(ctx, ledger_rows)
            _ground_queries(ctx, scene_id, ledger_rows)
            scene_op_id = ctx.peek_next_op_id()
            fault = cfg["apply_faults"].get(scene_id)
            app = _apply_scene(ctx, fixture, scene_id, scene_op_id, server_epoch_old, 1, "a", qa_fault=fault)
            ctx.record_scenario({
                "ev": "apply_scene_t1",
                "scene_id": scene_id,
                "scene_op_id": scene_op_id,
                "status": app.status,
                "reason": app.reason,
            })
            if app.status == "done" and app.payload:
                for row in app.payload.get("rows") or []:
                    ctx.record_scenario({
                        "ev": "ledger_spawn_recorded",
                        "kind": "scene",
                        "scene_id": scene_id,
                        "logical_id": row.get("logical_id"),
                        "class_name": row.get("class_name"),
                        "net_id_t1": row.get("net_id"),
                        "init_max_hp": row.get("max_hp"),
                        "init_health_hp": row.get("health_hp"),
                    })
            if scene_id == cfg["retained_scene"]:
                dup = _apply_scene(ctx, fixture, scene_id, scene_op_id, server_epoch_old, 1, "a", qa_fault=fault)
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
        ctx.record_scenario({"ev": "storage_snapshot_t1", "files": _snapshot_dir(sim_storage)})

        for area_id in cfg["creature_areas"]:
            _census(ctx, fixture, "t2_census_10min", area_id, 0)
        ctx.record_scenario({"ev": "storage_snapshot_t2", "files": _snapshot_dir(sim_storage)})

        t3_director_areas = {cfg["retained_area"], "area_a", "area_b"}
        for area_id in cfg["base_areas"]:
            _census(ctx, fixture, "t3_pre_reset_census", area_id, 1 if area_id in t3_director_areas else 0)

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
        ctx.record_scenario({
            "ev": "reset_scene_retained_t3",
            "scene_id": cfg["retained_scene"],
            "area_id": cfg["retained_area"],
            "status": rr.status,
            "reason": rr.reason,
        })

        for area_id in cfg["base_areas"]:
            _census(ctx, fixture, "t3_post_reset_census", area_id, 1 if area_id in t3_director_areas else 0)

        if drop_control_pre_restart:
            _census(ctx, fixture, "t3_post_reset_census", "area_c", 0, qa_fault="drop_ctrl_pre_restart")

        stop_status = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
        ctx.record_scenario({
            "ev": "t3_stop_status",
            "status": stop_status.status,
            "num": dict(stop_status.payload["num"]) if stop_status.payload else {},
        })

        server_epoch_new = _restart_server(ctx, server_epoch_old)
        st_t4 = f03_common.issue_one(ctx, "server", "per_status", wire.empty_payload())
        if st_t4.status == "done" and st_t4.payload:
            server_epoch_new = str(st_t4.payload["str"].get("server_epoch") or server_epoch_new)
        ctx.record_scenario({
            "ev": "t4_post_restart_status",
            "status": st_t4.status,
            "server_epoch_old": server_epoch_old,
            "server_epoch_new": server_epoch_new,
        })

        t5_director_areas = {cfg["retained_area"], "area_a", "area_b"}
        for area_id in cfg["base_areas"]:
            _census(ctx, fixture, "t5_post_restart_census", area_id, 1 if area_id in t5_director_areas else 0)

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

        restored_snapshot = _snapshot_dir(backup_dir)
        if sim_storage.exists():
            shutil.rmtree(sim_storage, ignore_errors=True)
        shutil.copytree(backup_dir, sim_storage)
        restored_snapshot = _snapshot_dir(sim_storage)
        restore_ok = 1 if restored_snapshot == storage_t0 else 0
        ctx.record_scenario({
            "ev": "storage_restore_result",
            "restore_ok_b": restore_ok,
            "files": restored_snapshot,
        })
        if restore_ok == 1:
            shutil.rmtree(backup_dir, ignore_errors=True)

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
