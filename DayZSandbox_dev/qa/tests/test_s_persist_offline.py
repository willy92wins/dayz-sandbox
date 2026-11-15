"""Offline unit and anti-fabrication tests for the S-persist oracle (s_persist_eval)."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

QA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = QA_DIR.parent.parent
if str(QA_DIR) not in sys.path:
    sys.path.insert(0, str(QA_DIR))

import f03_common
import fake_peer
import gate_core
import m1_gate
import s_persist_eval
import s_persist_mutants
import wire


def _surface_y(x: float, z: float) -> float:
    return 100.0 + 10.0 * math.sin(float(x) / 100.0) * math.cos(float(z) / 100.0)


def _get_git_head_and_persist_sources() -> tuple[str, str, dict[str, str]]:
    git_head = gate_core.git_harness(repo_root=REPO_ROOT)["git_head"]
    stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=REPO_ROOT)
    rel_path = "DayZSandbox_dev/qa/probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_X_Persist.c"
    proc = subprocess.run(
        ["git", "show", f"{git_head}:{rel_path}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        timeout=15,
        check=True,
    )
    return git_head, stamp, {rel_path: proc.stdout.decode("utf-8")}


def _unpack(obj: dict[str, Any]) -> tuple[dict[str, str], dict[str, float], list[dict[str, Any]]]:
    u = wire.unpack_payload(obj)
    return u["str"], u["num"], u["rows"]


def _checks_by_id(verdict: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in verdict["checks"]}


class _SyntheticPartBuilder:
    """Builds realistic raw bridge.jsonl and scenario.jsonl samples for S-persist."""

    def __init__(
        self,
        part_name: str = "run",
        *,
        nonce: str = "a1b2c3d4e5f60718",
        fault_code: str = "",
        q9_use_pathway_b: bool = False,
        creature_far_move_m: float = 0.0,
        include_t5_track_disks: bool = True,
        drop_control_post_restart: bool = False,
    ) -> None:
        self.part_name = part_name
        self.nonce = nonce
        self.fault_code = fault_code
        self.q9_use_pathway_b = q9_use_pathway_b
        self.creature_far_move_m = creature_far_move_m
        self.include_t5_track_disks = include_t5_track_disks
        self.drop_control_post_restart = drop_control_post_restart

        self.fixture = json.loads(
            (QA_DIR / "fixtures" / "s_persist_fixture.json").read_text(encoding="utf-8")
        )
        self.git_head, self.probe_stamp, self.persist_files = _get_git_head_and_persist_sources()
        self.server_epoch_old = "srv-epoch-1001"
        self.server_epoch_new = "srv-epoch-2002"
        self.client_inst = "cli-epoch-3003"
        self.director_uid = "dir-uid-778899"

        self.op_seq = 0
        self.tick_ms = 1000.0
        self.frame = 100
        self.next_net_low = 100

        self.bridge_events: list[dict[str, Any]] = []
        self.scenario_events: list[dict[str, Any]] = []
        self.entities_by_lid: dict[str, dict[str, Any]] = {}

    def _next_op_id(self) -> str:
        self.op_seq += 1
        return f"{self.nonce}-{self.op_seq}"

    def _alloc_net_id(self) -> str:
        self.next_net_low += 1
        return f"1:{self.next_net_low}"

    def _advance(self, dt_ms: float = 50.0, dframe: int = 3) -> None:
        self.tick_ms += dt_ms
        self.frame += dframe

    def _emit_op(
        self,
        peer: str,
        inst: str,
        verb: str,
        args: dict[str, Any],
        read: dict[str, Any],
        *,
        status: str = "done",
        reason: str = "",
        op_id: str | None = None,
    ) -> str:
        oid = op_id or self._next_op_id()
        recv_ms = self.tick_ms
        frame_recv = self.frame
        self._advance(20.0, 1)
        done_ms = self.tick_ms
        frame_done = self.frame

        self.bridge_events.append({
            "ev": "enq",
            "peer": peer,
            "op_id": oid,
            "verb": verb,
            "args": args,
            "h_ms": recv_ms,
        })
        self.bridge_events.append({
            "ev": "poll",
            "peer": peer,
            "inst": inst,
            "ops": [{"op_id": oid, "verb": verb, "args": args}],
            "body_len": 512,
            "h_ms": recv_ms,
        })
        self.bridge_events.append({
            "ev": "result",
            "peer": peer,
            "inst": inst,
            "results": [{
                "op_id": oid,
                "verb": verb,
                "status": status,
                "reason": reason,
                "dup": 0,
                "recv_ms": recv_ms,
                "done_ms": done_ms,
                "frame_recv": frame_recv,
                "frame_done": frame_done,
                "read": read,
            }],
            "h_ms": done_ms,
        })
        return oid

    def _pack_ext_args(
        self,
        strings: dict[str, str] | None = None,
        numbers: dict[str, float] | None = None,
        ncol: list[str] | None = None,
        scol: list[str] | None = None,
        rows: list[dict[str, Any]] | None = None,
        fault: str | None = None,
    ) -> dict[str, Any]:
        s = dict(strings or {})
        s["qa_fault"] = wire.format_qa_fault(self.fault_code if fault is None else fault)
        nc = list(ncol or [])
        sc = list(scol or [])
        allowed = set(nc) | set(sc)
        filtered_rows = [{k: r[k] for k in allowed} for r in (rows or [])]
        packed = wire.pack_payload(
            scalars_str=s,
            scalars_num=numbers or {},
            num_cols=nc,
            str_cols=sc,
            row_dicts=filtered_rows,
        )
        packed["pos"] = [0.0, 0.0, 0.0]
        packed["ypr"] = [0.0, 0.0, 0.0]
        packed["fog"] = 0.0
        packed["count"] = 0
        packed["duration_ms"] = 0
        return packed

    def _pack_ext_read(
        self,
        strings: dict[str, str] | None = None,
        numbers: dict[str, float] | None = None,
        ncol: list[str] | None = None,
        scol: list[str] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        nc = list(ncol or [])
        sc = list(scol or [])
        allowed = set(nc) | set(sc)
        filtered_rows = [{k: r[k] for k in allowed} for r in (rows or [])]
        packed = wire.pack_payload(
            scalars_str=strings or {},
            scalars_num=numbers or {},
            num_cols=nc,
            str_cols=sc,
            row_dicts=filtered_rows,
        )
        packed["has"] = ["payload"]
        return packed

    def _emit_census(
        self,
        inst: str,
        stage: str,
        area_id: str,
        center_x: float,
        center_z: float,
        rows: list[dict[str, Any]],
        *,
        include_director_b: int = 0,
        director_present_b: int = 1,
        director_inv_readable_b: int = 1,
    ) -> str:
        area_tag = area_id if stage == "t5_post_restart_census" and area_id.startswith("t5_track_") else f"{stage}:{area_id}"
        in_args = self._pack_ext_args(
            strings={"area_tag": area_tag},
            numbers={
                "center_x_m": center_x,
                "center_z_m": center_z,
                "radius_m": 60.0,
                "include_director_b": float(include_director_b),
            },
        )
        start_tick = self.tick_ms
        start_frame = self.frame
        job_id = self._next_op_id()
        start_read = self._pack_ext_read(
            strings={
                "job": job_id,
                "state": "running",
                "resource": "per_census",
                "area_tag": area_tag,
                "server_epoch": inst,
                "director_uid": self.director_uid if director_present_b else "",
            },
            numbers={
                "snap_tick_ms": start_tick,
                "snap_frame": float(start_frame),
                "rows_captured_n": float(len(rows)),
                "center_x_m": center_x,
                "center_z_m": center_z,
                "radius_m": 60.0,
                "director_present_b": float(director_present_b),
                "director_alive_b": float(director_present_b),
                "director_inv_readable_b": float(director_inv_readable_b),
                "director_inv_count_n": float(sum(1 for r in rows if r.get("owner_uid") == self.director_uid)),
            },
        )
        self._emit_op("server", inst, "per_census_start", in_args, start_read, op_id=job_id)

        scol = [
            "class_name",
            "loc_kind",
            "parent_class",
            "parent_net_id",
            "slot_name",
            "owner_uid",
            "own_logical_id",
            "net_id",
            "pers_id",
        ]
        ncol = [
            "own_b",
            "in_radius_b",
            "alive_b",
            "ai_agent_b",
            "pos_x_m",
            "pos_y_m",
            "pos_z_m",
            "yaw_deg",
            "pitch_deg",
            "roll_deg",
            "max_hp",
            "health_hp",
            "inv_children_n",
            "spawn_tick_ms",
        ]
        page_size = 5
        pages_n = (len(rows) + page_size - 1) // page_size if rows else 0
        end_tick = self.tick_ms

        if pages_n == 0:
            jr_args = self._pack_ext_args(strings={"job": job_id}, numbers={"page_n": 0.0})
            jr_read = self._pack_ext_read(
                strings={"job": job_id, "state": "done", "reason": "", "resource": "per_census"},
                numbers={
                    "page_n": 0.0,
                    "pages_n": 0.0,
                    "rows_total_n": 0.0,
                    "start_tick_ms": start_tick,
                    "end_tick_ms": end_tick,
                    "onjobend_tick_ms": end_tick,
                    "released_tick_ms": end_tick,
                    "elapsed_dtsum_ms": 10.0,
                },
                ncol=ncol,
                scol=scol,
                rows=[],
            )
            self._emit_op("server", inst, "job_read", jr_args, jr_read)
        else:
            for p in range(pages_n):
                chunk = rows[p * page_size : (p + 1) * page_size]
                jr_args = self._pack_ext_args(strings={"job": job_id}, numbers={"page_n": float(p)})
                jr_read = self._pack_ext_read(
                    strings={"job": job_id, "state": "done", "reason": "", "resource": "per_census"},
                    numbers={
                        "page_n": float(p),
                        "pages_n": float(pages_n),
                        "rows_total_n": float(len(rows)),
                        "start_tick_ms": start_tick,
                        "end_tick_ms": end_tick,
                        "onjobend_tick_ms": end_tick,
                        "released_tick_ms": end_tick,
                        "elapsed_dtsum_ms": 10.0,
                    },
                    ncol=ncol,
                    scol=scol,
                    rows=chunk,
                )
                self._emit_op("server", inst, "job_read", jr_args, jr_read)

        jf_args = self._pack_ext_args(strings={"job": job_id})
        jf_read = self._pack_ext_read(strings={"job": job_id, "freed": "1"})
        self._emit_op("server", inst, "job_free", jf_args, jf_read)
        return job_id

    def build_into(self, part_dir: Path) -> Path:
        part_dir.mkdir(parents=True, exist_ok=True)
        samples_dir = part_dir / "samples"
        samples_dir.mkdir(parents=True, exist_ok=True)

        uses_mut_area = self.part_name == "mut-foreign_wiped"
        has_scene_d = self.part_name == "mut-unprotected_leak"
        ret_scene_id = "scene_a_mut" if uses_mut_area else "scene_a"
        ret_area_id = "area_a_mut" if uses_mut_area else "area_a"
        ret_pfx = "am" if uses_mut_area else "a"

        base_areas = ["area_a", "area_b", "area_c"]
        if uses_mut_area:
            base_areas.append("area_a_mut")
        if has_scene_d:
            base_areas.append("area_d")

        # t0: probe_sources_at_commit and cold storage snapshot
        self.scenario_events.append({
            "ev": "probe_sources_at_commit",
            "git_head": self.git_head,
            "probe_stamp": self.probe_stamp,
            "persist_files": self.persist_files,
        })
        storage_files_t0 = {
            "players.db": {
                "sha256": hashlib.sha256(b"players-db-baseline").hexdigest(),
                "size_b": 19,
                "mtime_ns": 1700000000000000000,
            },
            "data/types.bin": {
                "sha256": hashlib.sha256(b"types-bin-baseline").hexdigest(),
                "size_b": 18,
                "mtime_ns": 1700000000000000000,
            },
        }
        self.scenario_events.append({
            "ev": "storage_snapshot_t0",
            "files": copy.deepcopy(storage_files_t0),
        })
        self.scenario_events.append({
            "ev": "storage_backup_t0",
            "backup_ok_b": 1,
            "files": copy.deepcopy(storage_files_t0),
        })

        probe_ver = f"dsbx-qa1+{self.probe_stamp}"
        self.bridge_events.append({
            "ev": "hello",
            "peer": "server",
            "inst": self.server_epoch_old,
            "proto": "qa0",
            "build": "offline",
            "probe_ver": probe_ver,
            "http": 200,
            "h_ms": 100.0,
        })
        self.bridge_events.append({
            "ev": "hello",
            "peer": "client",
            "inst": self.client_inst,
            "proto": "qa0",
            "build": "offline",
            "probe_ver": probe_ver,
            "http": 200,
            "h_ms": 110.0,
        })

        # Initial per_status
        self._emit_op(
            "server",
            self.server_epoch_old,
            "per_status",
            self._pack_ext_args(),
            self._pack_ext_read(
                strings={"server_epoch": self.server_epoch_old, "director_uid": self.director_uid},
                numbers={
                    "tick_ms": self.tick_ms,
                    "frame": float(self.frame),
                    "registered_total_n": 0.0,
                    "scenes_count_n": 0.0,
                    "director_present_b": 1.0,
                    "director_alive_b": 1.0,
                    "director_inv_readable_b": 1.0,
                    "director_inv_count_n": 2.0,
                },
                ncol=["gen_n", "own_alive_n"],
                scol=["scene_id", "last_op_id"],
                rows=[],
            ),
        )

        # Baseline director foreign items (non-sentinel)
        dir_jeans_row = {
            "class_name": "Jeans_Blue",
            "loc_kind": "attachment",
            "parent_class": "SurvivorM_Mirek",
            "parent_net_id": "1:2",
            "slot_name": "Legs",
            "owner_uid": self.director_uid,
            "own_logical_id": "",
            "net_id": "1:10",
            "pers_id": "0:0:0:0",
            "own_b": 0.0,
            "in_radius_b": 1.0,
            "alive_b": 1.0,
            "ai_agent_b": 0.0,
            "pos_x_m": 4500.0,
            "pos_y_m": _surface_y(4500.0, 10200.0),
            "pos_z_m": 10200.0,
            "yaw_deg": 0.0,
            "pitch_deg": 0.0,
            "roll_deg": 0.0,
            "max_hp": 100.0,
            "health_hp": 100.0,
            "inv_children_n": 1.0,
            "spawn_tick_ms": 500.0,
        }
        dir_apple_row = {
            "class_name": "Apple",
            "loc_kind": "cargo",
            "parent_class": "Jeans_Blue",
            "parent_net_id": "1:10",
            "slot_name": "Cargo:0:0:0",
            "owner_uid": self.director_uid,
            "own_logical_id": "",
            "net_id": "1:11",
            "pers_id": "0:0:0:0",
            "own_b": 0.0,
            "in_radius_b": 1.0,
            "alive_b": 1.0,
            "ai_agent_b": 0.0,
            "pos_x_m": 4500.0,
            "pos_y_m": _surface_y(4500.0, 10200.0),
            "pos_z_m": 10200.0,
            "yaw_deg": 0.0,
            "pitch_deg": 0.0,
            "roll_deg": 0.0,
            "max_hp": 50.0,
            "health_hp": 50.0,
            "inv_children_n": 0.0,
            "spawn_tick_ms": 500.0,
        }
        baseline_dir_rows = [dir_jeans_row, dir_apple_row]

        for aid in base_areas:
            ainfo = self.fixture["areas"][aid]
            inc_d = 1 if aid == "area_a" else 0
            self._emit_census(
                self.server_epoch_old,
                "t0_baseline_census",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                copy.deepcopy(baseline_dir_rows) if inc_d else [],
                include_director_b=inc_d,
            )
        self.scenario_events.append({
            "ev": "baseline_director_foreign",
            "director_uid": self.director_uid,
            "rows": copy.deepcopy(baseline_dir_rows),
        })

        # t1: ledger_entry, ground_query, per_apply_scene, per_spawn_raw
        active_scenes = [ret_scene_id, "scene_a_clean", "scene_b"]
        if has_scene_d:
            active_scenes.append("scene_d")

        for sc_id in active_scenes:
            sc_def = self.fixture["scenes"][sc_id]
            for ent in sc_def["entities"]:
                le = copy.deepcopy(ent)
                le["ev"] = "ledger_entry"
                le["role"] = sc_def["role"]
                le["scene_id"] = sc_id
                self.scenario_events.append(le)
                if ent["parent_id"] == "":
                    rx = float(ent["req_x_m"])
                    rz = float(ent["req_z_m"])
                    gy = _surface_y(rx, rz)
                    self._emit_op(
                        "server",
                        self.server_epoch_old,
                        "ground_query",
                        {
                            "x": rx,
                            "z": rz,
                            "pos": [rx, 0.0, rz],
                            "ypr": [0.0, 0.0, 0.0],
                            "fog": 0.0,
                            "count": 1,
                            "duration_ms": 0,
                        },
                        {"has": ["y"], "y": gy},
                    )

        # Apply each active scene
        in_scol = ["logical_id", "parent_id", "cat", "class_name", "slot_name"]
        in_ncol = ["req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"]
        out_scol = ["logical_id", "class_name", "net_id", "obs_loc_kind", "obs_parent_net_id", "obs_slot_name"]
        out_ncol = [
            "ok_b",
            "alive_b",
            "ai_agent_b",
            "req_y_m",
            "q9_x_m",
            "q9_y_m",
            "q9_z_m",
            "q9_dx_m",
            "q9_dy_m",
            "q9_dz_m",
            "q9_err_3d_m",
            "q9_yaw_deg",
            "q9_pitch_deg",
            "q9_roll_deg",
            "max_hp",
            "health_hp",
            "spawn_tick_ms",
        ]

        def _apply_one_scene(sc_id: str, gen_n: int, pathway: str, creature_drift: float = 0.0) -> tuple[str, list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
            sc_def = self.fixture["scenes"][sc_id]
            in_rows: list[dict[str, Any]] = []
            out_rows: list[dict[str, Any]] = []
            local_nids: dict[str, str] = {}
            local_pos: dict[str, tuple[float, float, float, float]] = {}
            roots_n = 0
            children_n = 0

            for ent in sc_def["entities"]:
                lid = ent["logical_id"]
                pid = ent["parent_id"]
                cat = ent["cat"]
                cname = ent["class_name"]
                sname = ent["slot_name"]
                rx = float(ent["req_x_m"])
                rz = float(ent["req_z_m"])
                ryaw = float(ent["req_yaw_deg"])
                ratio = float(ent["health_mark_ratio"])
                mv = float(ent["must_vanish_on_restart_b"])

                in_rows.append({
                    "logical_id": lid,
                    "parent_id": pid,
                    "cat": cat,
                    "class_name": cname,
                    "slot_name": sname,
                    "req_x_m": rx,
                    "req_z_m": rz,
                    "req_yaw_deg": ryaw,
                    "health_mark_ratio": ratio,
                    "must_vanish_b": mv,
                })

                nid = self._alloc_net_id()
                local_nids[lid] = nid
                max_hp = 100.0
                hp = max_hp * ratio if ratio > 0.0 else max_hp
                ai_b = 1.0 if cat in ("infected", "animal") else 0.0

                if pid == "":
                    roots_n += 1
                    gy = _surface_y(rx, rz)
                    dx = creature_drift if cat in ("infected", "animal") else 0.02
                    dy = 0.0
                    dz = 0.01
                    qx = rx + dx
                    qy = gy + dy
                    qz = rz + dz
                    err3d = math.sqrt(dx * dx + dy * dy + dz * dz)
                    obs_loc = "ground"
                    obs_pnid = ""
                    obs_slot = ""
                    local_pos[lid] = (qx, qy, qz, ryaw)
                else:
                    children_n += 1
                    obs_pnid = local_nids[pid]
                    px, py, pz, pyaw = local_pos[pid]
                    gy = py
                    qx, qy, qz = px, py, pz
                    dx = dy = dz = err3d = 0.0
                    obs_loc = "cargo" if sname == "Cargo" else "attachment"
                    obs_slot = f"Cargo:0:0:{children_n}" if sname == "Cargo" else sname
                    local_pos[lid] = (qx, qy, qz, pyaw)

                orow = {
                    "logical_id": lid,
                    "class_name": cname,
                    "net_id": nid,
                    "obs_loc_kind": obs_loc,
                    "obs_parent_net_id": obs_pnid,
                    "obs_slot_name": obs_slot,
                    "ok_b": 1.0,
                    "alive_b": 1.0,
                    "ai_agent_b": ai_b,
                    "req_y_m": gy,
                    "q9_x_m": qx,
                    "q9_y_m": qy,
                    "q9_z_m": qz,
                    "q9_dx_m": dx,
                    "q9_dy_m": dy,
                    "q9_dz_m": dz,
                    "q9_err_3d_m": err3d,
                    "q9_yaw_deg": ryaw,
                    "q9_pitch_deg": 0.0,
                    "q9_roll_deg": 0.0,
                    "max_hp": max_hp,
                    "health_hp": hp,
                    "spawn_tick_ms": self.tick_ms,
                }
                out_rows.append(orow)

                if creature_drift < 0.5:
                    parent_ent = next((e for e in sc_def["entities"] if e["logical_id"] == pid), None)
                    self.entities_by_lid[lid] = {
                        "logical_id": lid,
                        "scene_id": sc_id,
                        "area_id": sc_def["area_id"],
                        "role": sc_def["role"],
                        "cat": cat,
                        "class_name": cname,
                        "loc_kind": obs_loc,
                        "parent_class": parent_ent["class_name"] if parent_ent else "",
                        "parent_net_id": obs_pnid,
                        "slot_name": obs_slot,
                        "owner_uid": "",
                        "own_logical_id": lid,
                        "net_id": nid,
                        "pers_id": "0:0:0:0",
                        "own_b": 1.0,
                        "in_radius_b": 1.0,
                        "alive_b": 1.0,
                        "ai_agent_b": ai_b,
                        "pos_x_m": qx,
                        "pos_y_m": qy,
                        "pos_z_m": qz,
                        "yaw_deg": ryaw,
                        "pitch_deg": 0.0,
                        "roll_deg": 0.0,
                        "max_hp": max_hp,
                        "health_hp": hp,
                        "inv_children_n": 0.0,
                        "spawn_tick_ms": self.tick_ms,
                        "must_vanish_on_restart_b": int(mv),
                    }

            scene_op_id = f"scop-{sc_id}-{gen_n}"
            fault = "omit_nopersistency_flag" if (sc_id == "scene_d" and has_scene_d) else ""
            a_args = self._pack_ext_args(
                strings={
                    "scene_id": sc_id,
                    "scene_op_id": scene_op_id,
                    "expect_epoch": self.server_epoch_old,
                    "q9_pathway": pathway,
                },
                numbers={"gen_n": float(gen_n)},
                ncol=in_ncol,
                scol=in_scol,
                rows=in_rows,
                fault=fault,
            )
            a_read = self._pack_ext_read(
                strings={
                    "apply_status": "ok",
                    "reason": "",
                    "server_epoch": self.server_epoch_old,
                    "scene_id": sc_id,
                    "scene_op_id": scene_op_id,
                    "q9_pathway": pathway,
                },
                numbers={
                    "gen_n": float(gen_n),
                    "created_roots_n": float(roots_n),
                    "created_children_n": float(children_n),
                    "idempotent_hit_b": 0.0,
                    "q9_tick_ms": self.tick_ms,
                    "q9_frame": float(self.frame),
                },
                ncol=out_ncol,
                scol=out_scol,
                rows=out_rows,
            )
            self._emit_op("server", self.server_epoch_old, "per_apply_scene", a_args, a_read)
            return scene_op_id, out_rows, a_args, a_read

        for sc_id in active_scenes:
            if self.q9_use_pathway_b and sc_id == "scene_b":
                _apply_one_scene(sc_id, 1, "a", creature_drift=0.65)
                # Reset before pathway b (Q9 contingency for scene_b)
                r_args = self._pack_ext_args(
                    strings={
                        "scene_id": sc_id,
                        "reset_op_id": f"rst-q9b-{sc_id}",
                        "expect_epoch": self.server_epoch_old,
                    }
                )
                r_read = self._pack_ext_read(
                    strings={
                        "reset_status": "ok",
                        "reason": "clean",
                        "server_epoch": self.server_epoch_old,
                        "scene_id": sc_id,
                        "reset_op_id": f"rst-q9b-{sc_id}",
                    },
                    numbers={
                        "deleted_n": float(len(self.fixture["scenes"][sc_id]["entities"])),
                        "retained_n": 0.0,
                        "tick_ms": self.tick_ms,
                        "frame": float(self.frame),
                    },
                    ncol=["foreign_descendants_n"],
                    scol=["logical_id", "class_name", "net_id"],
                    rows=[],
                )
                self._emit_op("server", self.server_epoch_old, "per_reset_scene", r_args, r_read)
                scop_id, out_rows, a_args, a_read = _apply_one_scene(sc_id, 2, "b", creature_drift=0.02)
            elif self.q9_use_pathway_b and sc_id == ret_scene_id:
                # For retained scene, apply directly with pathway b (contingency is internal)
                scop_id, out_rows, a_args, a_read = _apply_one_scene(sc_id, 1, "b", creature_drift=0.02)
            else:
                scop_id, out_rows, a_args, a_read = _apply_one_scene(sc_id, 1, "a", creature_drift=0.02)

            if sc_id == ret_scene_id:
                # Idempotent repeat of scene_op_id
                idem_read = copy.deepcopy(a_read)
                u_s, u_n, u_r = _unpack(idem_read)
                u_n["idempotent_hit_b"] = 1.0
                idem_packed = self._pack_ext_read(
                    strings=u_s,
                    numbers=u_n,
                    ncol=out_ncol,
                    scol=out_scol,
                    rows=u_r,
                )
                self._emit_op("server", self.server_epoch_old, "per_apply_scene", a_args, idem_packed)

            for r in out_rows:
                self.scenario_events.append({
                    "ev": "ledger_spawn_recorded",
                    "logical_id": r["logical_id"],
                    "net_id_t1": r["net_id"],
                    "pers_id_t1": "0:0:0:0",
                    "init_max_hp": r["max_hp"],
                    "init_health_hp": r["health_hp"],
                })

        # Spawn raw foreign and persistent_control entities
        raw_tags = [
            f"{ret_pfx}_foreign_ground",
            f"{ret_pfx}_foreign_in_chest",
            f"{ret_pfx}_foreign_in_child_kit",
            "b_foreign_in_chest",
            "c_persistent_control",
        ]
        for rtag in raw_tags:
            rdef = self.fixture["raw_spawns"][rtag]
            nid = self._alloc_net_id()
            mode = rdef["mode"]
            cname = rdef["class_name"]
            ratio = float(rdef["health_mark_ratio"])
            max_hp = 100.0
            hp = max_hp * ratio
            pers_id = "11:22:33:44" if mode == "persistent_control" else "0:0:0:0"

            if mode == "foreign_ground" or mode == "persistent_control":
                px = float(rdef["x_m"])
                pz = float(rdef["z_m"])
                py = _surface_y(px, pz)
                yaw = float(rdef["yaw_deg"])
                loc_k = "ground"
                pclass = ""
                pnid = ""
                slot_n = ""
                child_cnt = 1.0 if mode == "persistent_control" else 0.0
            else:
                p_ent = self.entities_by_lid[rdef["target_parent_id"]]
                px, py, pz, yaw = p_ent["pos_x_m"], p_ent["pos_y_m"], p_ent["pos_z_m"], 0.0
                loc_k = "cargo"
                pclass = p_ent["class_name"]
                pnid = p_ent["net_id"]
                slot_n = "Cargo:0:1:0"
                child_cnt = 0.0

            s_args = self._pack_ext_args(
                strings={
                    "tag": rtag,
                    "mode": mode,
                    "class_name": cname,
                    "child_cargo_class": rdef["child_cargo_class"],
                    "target_scene_id": rdef["target_scene_id"],
                    "target_parent_id": rdef["target_parent_id"],
                },
                numbers={
                    "x_m": float(rdef["x_m"]),
                    "z_m": float(rdef["z_m"]),
                    "yaw_deg": float(rdef["yaw_deg"]),
                    "health_mark_ratio": ratio,
                },
            )
            s_read = self._pack_ext_read(
                strings={
                    "spawn_status": "ok",
                    "tag": rtag,
                    "class_name": cname,
                    "net_id": nid,
                    "pers_id": pers_id,
                    "obs_loc_kind": loc_k,
                    "obs_parent_net_id": pnid,
                    "obs_slot_name": slot_n,
                },
                numbers={
                    "pos_x_m": px,
                    "pos_y_m": py,
                    "pos_z_m": pz,
                    "yaw_deg": yaw,
                    "pitch_deg": 0.0,
                    "roll_deg": 0.0,
                    "max_hp": max_hp,
                    "health_hp": hp,
                    "child_count_n": child_cnt,
                    "tick_ms": self.tick_ms,
                    "frame": float(self.frame),
                },
            )
            self._emit_op("server", self.server_epoch_old, "per_spawn_raw", s_args, s_read)

            self.entities_by_lid[rtag] = {
                "logical_id": rtag,
                "scene_id": "",
                "area_id": rdef["area_id"],
                "role": rdef["role"],
                "cat": "raw",
                "class_name": cname,
                "loc_kind": loc_k,
                "parent_class": pclass,
                "parent_net_id": pnid,
                "slot_name": slot_n,
                "owner_uid": "",
                "own_logical_id": "",
                "net_id": nid,
                "pers_id": pers_id,
                "own_b": 0.0,
                "in_radius_b": 1.0,
                "alive_b": 1.0,
                "ai_agent_b": 0.0,
                "pos_x_m": px,
                "pos_y_m": py,
                "pos_z_m": pz,
                "yaw_deg": yaw,
                "pitch_deg": 0.0,
                "roll_deg": 0.0,
                "max_hp": max_hp,
                "health_hp": hp,
                "inv_children_n": child_cnt,
                "spawn_tick_ms": self.tick_ms,
                "must_vanish_on_restart_b": 0,
            }
            if mode == "persistent_control":
                fp_nid = self._alloc_net_id()
                self.entities_by_lid["c_persistent_control_child"] = {
                    "logical_id": "c_persistent_control_child",
                    "scene_id": "",
                    "area_id": "area_c",
                    "role": "persistent_control",
                    "cat": "raw_child",
                    "class_name": "Fireplace",
                    "loc_kind": "cargo",
                    "parent_class": "Barrel_Yellow",
                    "parent_net_id": nid,
                    "slot_name": "Cargo:0:0:0",
                    "owner_uid": "",
                    "own_logical_id": "",
                    "net_id": fp_nid,
                    "pers_id": "55:66:77:88",
                    "own_b": 0.0,
                    "in_radius_b": 1.0,
                    "alive_b": 1.0,
                    "ai_agent_b": 0.0,
                    "pos_x_m": px,
                    "pos_y_m": py,
                    "pos_z_m": pz,
                    "yaw_deg": 0.0,
                    "pitch_deg": 0.0,
                    "roll_deg": 0.0,
                    "max_hp": 100.0,
                    "health_hp": 100.0,
                    "inv_children_n": 0.0,
                    "spawn_tick_ms": self.tick_ms,
                    "must_vanish_on_restart_b": 0,
                }

            self.scenario_events.append({
                "ev": "ledger_spawn_recorded",
                "logical_id": rtag,
                "net_id_t1": nid,
                "pers_id_t1": pers_id,
                "init_max_hp": max_hp,
                "init_health_hp": hp,
            })

        def _recompute_inv_children() -> None:
            counts: dict[str, int] = {}
            for e in self.entities_by_lid.values():
                if e["alive_b"] == 1.0 and e["parent_net_id"]:
                    counts[e["parent_net_id"]] = counts.get(e["parent_net_id"], 0) + 1
            for e in self.entities_by_lid.values():
                e["inv_children_n"] = float(counts.get(e["net_id"], 0))

        def _census_rows_for_area(aid: str, include_dir: bool) -> list[dict[str, Any]]:
            _recompute_inv_children()
            rows: list[dict[str, Any]] = []
            for e in self.entities_by_lid.values():
                if e["alive_b"] != 1.0:
                    continue
                if e["owner_uid"] == self.director_uid:
                    if include_dir:
                        rows.append(copy.deepcopy(e))
                elif e["area_id"] == aid:
                    rows.append(copy.deepcopy(e))
            if include_dir:
                rows.extend(copy.deepcopy(baseline_dir_rows))
            return rows

        # t1_pre_transition_census
        for aid in base_areas:
            ainfo = self.fixture["areas"][aid]
            inc_d = 1 if aid in ("area_a", "area_b") else 0
            self._emit_census(
                self.server_epoch_old,
                "t1_pre_transition_census",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                _census_rows_for_area(aid, bool(inc_d)),
                include_director_b=inc_d,
            )

        # Execute transitions in t1
        transitions = [
            ("scene_a_clean", "ac_act_1_armband_drop", "drop_to_ground", "", ""),
            ("scene_a_clean", "ac_act_1_gloves_dir", "move_to_director", "", ""),
            ("scene_b", "b_act_1_armband_drop", "drop_to_ground", "", ""),
            ("scene_b", "b_act_1_gloves_dir", "move_to_director", "", ""),
            ("scene_b", "b_cross_child", "move_to_container", ret_scene_id, f"{ret_pfx}_prop_2"),
        ]
        for sc_id, lid, act, tgt_sc, tgt_pid in transitions:
            ent = self.entities_by_lid[lid]
            pre_loc = ent["loc_kind"]
            pre_pnid = ent["parent_net_id"]
            pre_slot = ent["slot_name"]
            pre_ouid = ent["owner_uid"]
            if act == "drop_to_ground":
                ent["loc_kind"] = "ground"
                ent["parent_class"] = ""
                ent["parent_net_id"] = ""
                ent["slot_name"] = ""
                ent["owner_uid"] = ""
            elif act == "move_to_director":
                ent["loc_kind"] = "cargo"
                ent["parent_class"] = "Jeans_Blue"
                ent["parent_net_id"] = "1:10"
                ent["slot_name"] = "Cargo:0:1:0"
                ent["owner_uid"] = self.director_uid
            elif act == "move_to_container":
                tgt_ent = self.entities_by_lid[tgt_pid]
                ent["area_id"] = tgt_ent["area_id"]
                ent["loc_kind"] = "cargo"
                ent["parent_class"] = tgt_ent["class_name"]
                ent["parent_net_id"] = tgt_ent["net_id"]
                ent["slot_name"] = "Cargo:0:0:0"
                ent["owner_uid"] = ""

            t_args = self._pack_ext_args(
                strings={
                    "scene_id": sc_id,
                    "logical_id": lid,
                    "action": act,
                    "expect_epoch": self.server_epoch_old,
                    "target_scene_id": tgt_sc,
                    "target_parent_id": tgt_pid,
                }
            )
            t_read = self._pack_ext_read(
                strings={
                    "transition_status": "ok",
                    "net_id": ent["net_id"],
                    "pre_loc_kind": pre_loc,
                    "pre_parent_net_id": pre_pnid,
                    "pre_slot_name": pre_slot,
                    "pre_owner_uid": pre_ouid,
                    "post_loc_kind": ent["loc_kind"],
                    "post_parent_net_id": ent["parent_net_id"],
                    "post_slot_name": ent["slot_name"],
                    "post_owner_uid": ent["owner_uid"],
                },
                numbers={
                    "pos_x_m": ent["pos_x_m"],
                    "pos_y_m": ent["pos_y_m"],
                    "pos_z_m": ent["pos_z_m"],
                    "yaw_deg": ent["yaw_deg"],
                    "pitch_deg": 0.0,
                    "roll_deg": 0.0,
                    "tick_ms": self.tick_ms,
                    "frame": float(self.frame),
                },
            )
            self._emit_op("server", self.server_epoch_old, "per_child_transition", t_args, t_read)

        # t1_post_transition_census
        for aid in base_areas:
            ainfo = self.fixture["areas"][aid]
            inc_d = 1 if aid in ("area_a", "area_b") else 0
            self._emit_census(
                self.server_epoch_old,
                "t1_post_transition_census",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                _census_rows_for_area(aid, bool(inc_d)),
                include_director_b=inc_d,
            )

        # Advance 10 min for t2_census_10min
        self._advance(605000.0, 18000)
        if self.creature_far_move_m != 0.0:
            self.entities_by_lid["b_inf_1"]["pos_x_m"] += self.creature_far_move_m
            if abs(self.creature_far_move_m) > 60.0:
                self.entities_by_lid["b_inf_1"]["in_radius_b"] = 0.0

        for aid in (ret_area_id, "area_b"):
            ainfo = self.fixture["areas"][aid]
            self._emit_census(
                self.server_epoch_old,
                "t2_census_10min",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                _census_rows_for_area(aid, False),
                include_director_b=0,
            )

        # t3_pre_reset_census
        for aid in base_areas:
            ainfo = self.fixture["areas"][aid]
            inc_d = 1 if aid in ("area_a", ret_area_id, "area_b") else 0
            self._emit_census(
                self.server_epoch_old,
                "t3_pre_reset_census",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                _census_rows_for_area(aid, bool(inc_d)),
                include_director_b=inc_d,
            )

        # t3: Reset scene_a_clean twice (idempotency check)
        for lid, ent in list(self.entities_by_lid.items()):
            if ent["scene_id"] == "scene_a_clean":
                ent["alive_b"] = 0.0

        for idx, del_n in ((1, 6.0), (2, 0.0)):
            rc_op_id = f"rst-clean-{idx}"
            rc_args = self._pack_ext_args(
                strings={
                    "scene_id": "scene_a_clean",
                    "reset_op_id": rc_op_id,
                    "expect_epoch": self.server_epoch_old,
                }
            )
            rc_read = self._pack_ext_read(
                strings={
                    "reset_status": "ok",
                    "reason": "clean",
                    "server_epoch": self.server_epoch_old,
                    "scene_id": "scene_a_clean",
                    "reset_op_id": rc_op_id,
                },
                numbers={
                    "deleted_n": del_n,
                    "retained_n": 0.0,
                    "tick_ms": self.tick_ms,
                    "frame": float(self.frame),
                },
                ncol=["foreign_descendants_n"],
                scol=["logical_id", "class_name", "net_id"],
                rows=[],
            )
            self._emit_op("server", self.server_epoch_old, "per_reset_scene", rc_args, rc_read)

        # t3: Reset retained scene (scene_a or scene_a_mut)
        retained_set = {f"{ret_pfx}_prop_2", f"{ret_pfx}_cont_1", f"{ret_pfx}_cont_1_child"}
        if uses_mut_area:
            # mut-foreign_wiped wipes everything in ret_area_id including foreign & cross_child
            for ent in self.entities_by_lid.values():
                if ent["area_id"] == ret_area_id:
                    ent["alive_b"] = 0.0
            rr_args = self._pack_ext_args(
                strings={
                    "scene_id": ret_scene_id,
                    "reset_op_id": "rst-ret-mut",
                    "expect_epoch": self.server_epoch_old,
                },
                fault="reset_wipe_radius_25m",
            )
            rr_read = self._pack_ext_read(
                strings={
                    "reset_status": "ok",
                    "reason": "clean",
                    "server_epoch": self.server_epoch_old,
                    "scene_id": ret_scene_id,
                    "reset_op_id": "rst-ret-mut",
                },
                numbers={
                    "deleted_n": 12.0,
                    "retained_n": 0.0,
                    "tick_ms": self.tick_ms,
                    "frame": float(self.frame),
                },
                ncol=["foreign_descendants_n"],
                scol=["logical_id", "class_name", "net_id"],
                rows=[],
            )
            self._emit_op("server", self.server_epoch_old, "per_reset_scene", rr_args, rr_read)
        else:
            for lid, ent in self.entities_by_lid.items():
                if ent["scene_id"] == ret_scene_id and lid not in retained_set:
                    ent["alive_b"] = 0.0
            ret_rows = [
                {
                    "logical_id": f"{ret_pfx}_prop_2",
                    "class_name": "WoodenCrate",
                    "net_id": self.entities_by_lid[f"{ret_pfx}_prop_2"]["net_id"],
                    "foreign_descendants_n": 1.0,
                },
                {
                    "logical_id": f"{ret_pfx}_cont_1",
                    "class_name": "SeaChest",
                    "net_id": self.entities_by_lid[f"{ret_pfx}_cont_1"]["net_id"],
                    "foreign_descendants_n": 2.0,
                },
                {
                    "logical_id": f"{ret_pfx}_cont_1_child",
                    "class_name": "FirstAidKit",
                    "net_id": self.entities_by_lid[f"{ret_pfx}_cont_1_child"]["net_id"],
                    "foreign_descendants_n": 1.0,
                },
            ]
            rr_args = self._pack_ext_args(
                strings={
                    "scene_id": ret_scene_id,
                    "reset_op_id": "rst-ret-1",
                    "expect_epoch": self.server_epoch_old,
                }
            )
            rr_read = self._pack_ext_read(
                strings={
                    "reset_status": "partial",
                    "reason": "foreign_content_retained",
                    "server_epoch": self.server_epoch_old,
                    "scene_id": ret_scene_id,
                    "reset_op_id": "rst-ret-1",
                },
                numbers={
                    "deleted_n": 9.0,
                    "retained_n": 3.0,
                    "tick_ms": self.tick_ms,
                    "frame": float(self.frame),
                },
                ncol=["foreign_descendants_n"],
                scol=["logical_id", "class_name", "net_id"],
                rows=ret_rows,
            )
            self._emit_op("server", self.server_epoch_old, "per_reset_scene", rr_args, rr_read)

        # t3_post_reset_census
        for aid in base_areas:
            ainfo = self.fixture["areas"][aid]
            inc_d = 1 if aid in ("area_a", ret_area_id, "area_b") else 0
            self._emit_census(
                self.server_epoch_old,
                "t3_post_reset_census",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                _census_rows_for_area(aid, bool(inc_d)),
                include_director_b=inc_d,
            )

        # t4: Server restart -> hello with new server_epoch_new
        self._advance(5000.0, 100)
        self.bridge_events.append({
            "ev": "hello",
            "peer": "server",
            "inst": self.server_epoch_new,
            "proto": "qa0",
            "build": "offline",
            "probe_ver": probe_ver,
            "http": 200,
            "h_ms": self.tick_ms,
        })

        # Simulate world restart: only c_persistent_control (+ child) and d_prop_leak (if mut-unprotected_leak) survive
        for lid, ent in self.entities_by_lid.items():
            if lid in ("c_persistent_control", "c_persistent_control_child"):
                ent["alive_b"] = 0.0 if self.drop_control_post_restart else 1.0
                ent["own_b"] = 0.0
                ent["own_logical_id"] = ""
            elif has_scene_d and lid == "d_prop_leak":
                ent["alive_b"] = 1.0
                ent["own_b"] = 0.0
                ent["own_logical_id"] = ""
            else:
                ent["alive_b"] = 0.0

        # t5_post_restart_census
        for aid in base_areas:
            ainfo = self.fixture["areas"][aid]
            inc_d = 1 if aid in ("area_a", ret_area_id, "area_b") else 0
            self._emit_census(
                self.server_epoch_new,
                "t5_post_restart_census",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                _census_rows_for_area(aid, bool(inc_d)),
                include_director_b=inc_d,
            )

        if self.creature_far_move_m != 0.0 and self.include_t5_track_disks:
            b_inf_x = 4688.0 + self.creature_far_move_m
            b_inf_z = 10202.0
            self._emit_census(
                self.server_epoch_new,
                "t5_post_restart_census",
                "t5_track_b_inf_1_t2",
                b_inf_x,
                b_inf_z,
                [],
                include_director_b=0,
            )

        # t5 witness scene_b in server_epoch_new
        wit_rows: list[dict[str, Any]] = []
        wit_in_rows: list[dict[str, Any]] = []
        wit_out_rows: list[dict[str, Any]] = []
        wit_nids: dict[str, str] = {}
        for ent in self.fixture["scenes"]["scene_b"]["entities"]:
            lid = ent["logical_id"]
            pid = ent["parent_id"]
            cname = ent["class_name"]
            cat = ent["cat"]
            sname = ent["slot_name"]
            rx = float(ent["req_x_m"]) if pid == "" else 4686.0
            rz = float(ent["req_z_m"]) if pid == "" else 10202.0
            gy = _surface_y(rx, rz)
            nid = self._alloc_net_id()
            wit_nids[lid] = nid
            pnid = wit_nids[pid] if pid else ""
            loc_k = "ground" if pid == "" else ("cargo" if sname == "Cargo" else "attachment")
            slot_str = "" if pid == "" else ("Cargo:0:0:0" if sname == "Cargo" else sname)
            p_ent = next((e for e in self.fixture["scenes"]["scene_b"]["entities"] if e["logical_id"] == pid), None)
            wit_in_rows.append({
                "logical_id": lid,
                "parent_id": pid,
                "cat": cat,
                "class_name": cname,
                "slot_name": sname,
                "req_x_m": float(ent["req_x_m"]),
                "req_z_m": float(ent["req_z_m"]),
                "req_yaw_deg": float(ent["req_yaw_deg"]),
                "health_mark_ratio": float(ent["health_mark_ratio"]),
                "must_vanish_b": 1.0,
            })
            wit_out_rows.append({
                "logical_id": lid,
                "class_name": cname,
                "net_id": nid,
                "obs_loc_kind": loc_k,
                "obs_parent_net_id": pnid,
                "obs_slot_name": slot_str,
                "ok_b": 1.0,
                "alive_b": 1.0,
                "ai_agent_b": 1.0 if cat in ("infected", "animal") else 0.0,
                "req_y_m": gy,
                "q9_x_m": rx,
                "q9_y_m": gy,
                "q9_z_m": rz,
                "q9_dx_m": 0.0,
                "q9_dy_m": 0.0,
                "q9_dz_m": 0.0,
                "q9_err_3d_m": 0.0,
                "q9_yaw_deg": float(ent["req_yaw_deg"]),
                "q9_pitch_deg": 0.0,
                "q9_roll_deg": 0.0,
                "max_hp": 100.0,
                "health_hp": 100.0 * float(ent["health_mark_ratio"]) if float(ent["health_mark_ratio"]) > 0.0 else 100.0,
                "spawn_tick_ms": self.tick_ms,
            })
            wit_rows.append({
                "class_name": cname,
                "loc_kind": loc_k,
                "parent_class": p_ent["class_name"] if p_ent else "",
                "parent_net_id": pnid,
                "slot_name": slot_str,
                "owner_uid": "",
                "own_logical_id": lid,
                "net_id": nid,
                "pers_id": "0:0:0:0",
                "own_b": 1.0,
                "in_radius_b": 1.0,
                "alive_b": 1.0,
                "ai_agent_b": 1.0 if cat in ("infected", "animal") else 0.0,
                "pos_x_m": rx,
                "pos_y_m": gy,
                "pos_z_m": rz,
                "yaw_deg": float(ent["req_yaw_deg"]),
                "pitch_deg": 0.0,
                "roll_deg": 0.0,
                "max_hp": 100.0,
                "health_hp": 100.0 * float(ent["health_mark_ratio"]) if float(ent["health_mark_ratio"]) > 0.0 else 100.0,
                "inv_children_n": 2.0 if lid == "b_chest_own" else (3.0 if lid == "b_act_1" else 0.0),
                "spawn_tick_ms": self.tick_ms,
            })

        wit_op_id = "wit-scene-b-1"
        self._emit_op(
            "server",
            self.server_epoch_new,
            "per_apply_scene",
            self._pack_ext_args(
                strings={
                    "scene_id": "scene_b",
                    "scene_op_id": wit_op_id,
                    "expect_epoch": self.server_epoch_new,
                    "q9_pathway": "a",
                },
                numbers={"gen_n": 1.0},
                ncol=in_ncol,
                scol=in_scol,
                rows=wit_in_rows,
            ),
            self._pack_ext_read(
                strings={
                    "apply_status": "ok",
                    "reason": "",
                    "server_epoch": self.server_epoch_new,
                    "scene_id": "scene_b",
                    "scene_op_id": wit_op_id,
                    "q9_pathway": "a",
                },
                numbers={
                    "gen_n": 1.0,
                    "created_roots_n": 6.0,
                    "created_children_n": 5.0,
                    "idempotent_hit_b": 0.0,
                    "q9_tick_ms": self.tick_ms,
                    "q9_frame": float(self.frame),
                },
                ncol=out_ncol,
                scol=out_scol,
                rows=wit_out_rows,
            ),
        )

        def _emit_witness_status() -> None:
            self._emit_op(
                "server",
                self.server_epoch_new,
                "per_status",
                self._pack_ext_args(),
                self._pack_ext_read(
                    strings={"server_epoch": self.server_epoch_new, "director_uid": self.director_uid},
                    numbers={
                        "tick_ms": self.tick_ms,
                        "frame": float(self.frame),
                        "registered_total_n": 11.0,
                        "scenes_count_n": 1.0,
                        "director_present_b": 1.0,
                        "director_alive_b": 1.0,
                        "director_inv_readable_b": 1.0,
                        "director_inv_count_n": 2.0,
                    },
                    ncol=["gen_n", "own_alive_n"],
                    scol=["scene_id", "last_op_id"],
                    rows=[{"scene_id": "scene_b", "last_op_id": wit_op_id, "gen_n": 1.0, "own_alive_n": 11.0}],
                ),
            )

        _emit_witness_status()
        self._emit_census(
            self.server_epoch_new,
            "t5_witness_pre_census",
            "area_b",
            4680.0,
            10200.0,
            copy.deepcopy(wit_rows) + copy.deepcopy(baseline_dir_rows),
            include_director_b=1,
        )

        # Stale epoch reset & apply rejected
        self._emit_op(
            "server",
            self.server_epoch_new,
            "per_reset_scene",
            self._pack_ext_args(
                strings={
                    "scene_id": "scene_b",
                    "reset_op_id": "stale-rst-1",
                    "expect_epoch": self.server_epoch_old,
                }
            ),
            {},
            status="rejected",
            reason="stale_epoch",
        )
        self._emit_op(
            "server",
            self.server_epoch_new,
            "per_apply_scene",
            self._pack_ext_args(
                strings={
                    "scene_id": "scene_b",
                    "scene_op_id": "stale-app-2",
                    "expect_epoch": self.server_epoch_old,
                    "q9_pathway": "a",
                },
                numbers={"gen_n": 2.0},
                ncol=in_ncol,
                scol=in_scol,
                rows=wit_in_rows,
            ),
            {},
            status="rejected",
            reason="stale_epoch",
        )

        _emit_witness_status()
        self._emit_census(
            self.server_epoch_new,
            "t5_witness_post_census",
            "area_b",
            4680.0,
            10200.0,
            copy.deepcopy(wit_rows) + copy.deepcopy(baseline_dir_rows),
            include_director_b=1,
        )

        # Cleanup witness and QA
        self._emit_op(
            "server",
            self.server_epoch_new,
            "per_cleanup_qa",
            self._pack_ext_args(strings={"cleanup_tag": "t6_cleanup"}),
            self._pack_ext_read(
                numbers={
                    "cleaned_own_n": 11.0,
                    "cleaned_raw_n": 2.0,
                    "tick_ms": self.tick_ms,
                    "frame": float(self.frame),
                }
            ),
        )
        for aid in base_areas:
            ainfo = self.fixture["areas"][aid]
            inc_d = 1 if aid == "area_a" else 0
            self._emit_census(
                self.server_epoch_new,
                "t6_post_cleanup_census",
                aid,
                float(ainfo["center_x_m"]),
                float(ainfo["center_z_m"]),
                copy.deepcopy(baseline_dir_rows) if inc_d else [],
                include_director_b=inc_d,
            )

        self.scenario_events.append({
            "ev": "storage_restore_result",
            "restore_ok_b": 1,
            "files": copy.deepcopy(storage_files_t0),
        })

        manifest = {
            "schema": "m1-manifest-v1",
            "id": "S-persist",
            "kind": "spike",
            "build": "offline",
            "both": True,
            "params": {"wire_cap": wire.WIRE_CAP},
            "identity": {
                "build": "offline",
                "git_dirty": False,
                "git_head": self.git_head,
                "params": {"wire_cap": wire.WIRE_CAP},
                "pbo_sha256": None,
                "peer_builds": {"server": "offline", "client": "offline"},
                "probe_stamp": self.probe_stamp,
            },
            "execution_identity": {
                "peer_insts": {
                    "server": [self.server_epoch_old, self.server_epoch_new],
                    "client": [self.client_inst],
                },
                "port": 18999,
            },
        }
        (part_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (part_dir / "part.json").write_text(
            json.dumps(
                {
                    "op_nonce": self.nonce,
                    "part": self.part_name,
                    "spike_id": "S-persist",
                    "op_map": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if self.part_name.startswith("mut-"):
            mname = self.part_name[len("mut-") :]
            (part_dir / "injection.json").write_text(
                json.dumps(
                    {
                        "applied": True,
                        "mutant": mname,
                        "fault_code": self.fault_code,
                        "observable_effect": {"part": self.part_name},
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        with (samples_dir / "bridge.jsonl").open("w", encoding="utf-8", newline="\n") as bf:
            for ev in self.bridge_events:
                bf.write(json.dumps(ev, sort_keys=True) + "\n")
        with (samples_dir / "scenario.jsonl").open("w", encoding="utf-8", newline="\n") as sf:
            for ev in self.scenario_events:
                sf.write(json.dumps(ev, sort_keys=True) + "\n")

        return part_dir


class TestSPersistOracleOffline(unittest.TestCase):
    """Offline unit and anti-fabrication tests for the S-persist oracle."""

    def test_positive_run_part_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "run")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict, indent=2))
            self.assertEqual(verdict["verdict"], "PASA")
            c_map = _checks_by_id(verdict)
            for cid in s_persist_eval.CHECK_IDS:
                self.assertEqual(c_map[cid]["status"], "pass", msg=cid)
            self.assertEqual(verdict["metrics"]["q9_selected_pathway"], "a")
            self.assertEqual(
                verdict["metrics"]["grill_foreign_in_unreset_own_container"]["readings_available_b"],
                1,
            )

    def test_q9_pathway_b_contingency_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run", q9_use_pathway_b=True).build_into(
                Path(tmp) / "run"
            )
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict, indent=2))
            self.assertEqual(verdict["metrics"]["q9_selected_pathway"], "b")

    def test_mutant_unprotected_leak_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder(
                "mut-unprotected_leak", fault_code="omit_nopersistency_flag"
            ).build_into(Path(tmp) / "mut-unprotected_leak")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(verdict["verdict"], "FALLA")
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-08"]["status"], "fail")
            for cid in s_persist_eval.CHECK_IDS:
                if cid != "PER-08":
                    self.assertEqual(c_map[cid]["status"], "pass", msg=cid)

    def test_mutant_foreign_wiped_detected_and_per08_passes_n50(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder(
                "mut-foreign_wiped", fault_code="reset_wipe_radius_25m"
            ).build_into(Path(tmp) / "mut-foreign_wiped")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(verdict["verdict"], "FALLA")
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-04"]["status"], "fail")
            self.assertEqual(c_map["PER-05"]["status"], "fail")
            for cid in s_persist_eval.CHECK_IDS:
                if cid not in ("PER-04", "PER-05"):
                    self.assertEqual(c_map[cid]["status"], "pass", msg=cid)

    def test_aggregate_spike_with_expected_mutants_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for pname, fcode, nonce in (
                ("run", "", "a1b2c3d4e5f60718"),
                ("mut-unprotected_leak", "omit_nopersistency_flag", "b2c3d4e5f6071829"),
                ("mut-foreign_wiped", "reset_wipe_radius_25m", "c3d4e5f60718293a"),
            ):
                pdir = _SyntheticPartBuilder(pname, nonce=nonce, fault_code=fcode).build_into(base / pname)
                v = s_persist_eval.evaluate(pdir, repo_root=REPO_ROOT)
                gate_core.write_json(pdir / "verdict.json", v)
            agg = f03_common.aggregate_spike(base, "S-persist", repo_root=REPO_ROOT)
            self.assertEqual(agg["exit_code"], 0, msg=json.dumps(agg, indent=2))
            self.assertEqual(agg["verdict"], "PASA")

    def test_control_lost_returns_inconcluso_n37(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder(
                "run", drop_control_post_restart=True
            ).build_into(Path(tmp) / "control_lost")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(verdict["verdict"], "INCONCLUSO")
            c_map = _checks_by_id(verdict)
            for cid in ("PER-06", "PER-07", "PER-08"):
                self.assertEqual(c_map[cid]["status"], "missing", msg=cid)
            for cid in ("PER-01", "PER-02", "PER-03", "PER-04", "PER-05", "PER-09", "PER-10"):
                self.assertEqual(c_map[cid]["status"], "pass", msg=cid)

    # =========================================================================
    # Anti-fabrication negative tests (ENCARGO.md §3.1 & §3.3)
    # =========================================================================

    def test_neg_census_copies_request_without_independent_job_read(self) -> None:
        # 1) Drop job_read events so census has no independent rows
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "no_job_read")
            bpath = part_dir / "samples" / "bridge.jsonl"
            lines = [
                json.loads(line)
                for line in bpath.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            filtered = [
                ev
                for ev in lines
                if not (ev.get("ev") == "enq" and ev.get("verb") == "job_read")
                and not (
                    ev.get("ev") == "result"
                    and any(r.get("verb") == "job_read" for r in (ev.get("results") or []))
                )
            ]
            bpath.write_text(
                "\n".join(json.dumps(e) for e in filtered) + "\n", encoding="utf-8"
            )
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(verdict["verdict"], "PASA")

        # 2) Census copies offset_m (pos_y_m = 0.0) instead of terrain SurfaceY
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "zero_y_census")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            for row in u_r:
                                if row.get("own_logical_id") == "a_prop_1":
                                    row["pos_y_m"] = 0.0
                            res["read"] = builder._pack_ext_read(
                                strings=u_s,
                                numbers=u_n,
                                ncol=res["read"]["ncol"],
                                scol=res["read"]["scol"],
                                rows=u_r,
                            )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-01"]["status"], "fail")

    def test_neg_persistent_id_all_zero_or_constant(self) -> None:
        # Case A: pers_id all "0:0:0:0" after restart
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "pers_zero")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            for row in u_r:
                                row["pers_id"] = "0:0:0:0"
                            res["read"] = builder._pack_ext_read(
                                strings=u_s,
                                numbers=u_n,
                                ncol=res["read"]["ncol"],
                                scol=res["read"]["scol"],
                                rows=u_r,
                            )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(_checks_by_id(verdict)["PER-06"]["status"], "pass")

        # Case B: constant non-zero pers_id across distinct entities in area_c
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "pers_const")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            for row in u_r:
                                if row.get("class_name") in ("Barrel_Yellow", "Fireplace"):
                                    row["pers_id"] = "11:22:33:44"
                            res["read"] = builder._pack_ext_read(
                                strings=u_s,
                                numbers=u_n,
                                ncol=res["read"]["ncol"],
                                scol=res["read"]["scol"],
                                rows=u_r,
                            )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-06"]["status"], "fail")

    def test_neg_foreign_pose_without_before_and_after_or_altered_pose(self) -> None:
        # Case A: missing t3_pre_reset_census
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "no_t3_pre")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            filtered = []
            for ev in events:
                if ev.get("ev") == "enq" and ev.get("verb") == "per_census_start":
                    u_s, _, _ = _unpack(ev["args"])
                    if "t3_pre_reset_census" in u_s.get("area_tag", ""):
                        continue
                if ev.get("ev") == "result":
                    res_list = ev.get("results") or []
                    if res_list and res_list[0].get("verb") == "per_census_start":
                        u_s, _, _ = _unpack(res_list[0]["read"])
                        if "t3_pre_reset_census" in u_s.get("area_tag", ""):
                            continue
                filtered.append(ev)
            bpath.write_text("\n".join(json.dumps(e) for e in filtered) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertEqual(_checks_by_id(verdict)["PER-05"]["status"], "missing")

        # Case B: foreign ground item changes yaw_deg in t3_post_reset_census
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "foreign_yaw_changed")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            t3_post_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if "t3_post_reset_census" in u_s.get("area_tag", ""):
                                t3_post_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t3_post_jobs:
                                for row in u_r:
                                    if row.get("class_name") == "WaterBottle":
                                        row["yaw_deg"] = float(row["yaw_deg"]) + 5.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-05"]["status"], "fail")

    def test_neg_storage_intact_without_before_and_after_hashes(self) -> None:
        # Case A: storage_restore_result has only restore_ok_b = 1 without post-restore file hashes
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "no_post_hashes")
            spath = part_dir / "samples" / "scenario.jsonl"
            events = [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "storage_restore_result":
                    ev.pop("files", None)
            spath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-10"]["status"], "missing")

        # Case B: post-restore sha256 does not match t0 sha256
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "tampered_post_hash")
            spath = part_dir / "samples" / "scenario.jsonl"
            events = [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "storage_restore_result":
                    ev["files"]["players.db"]["sha256"] = "0" * 64
            spath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-10"]["status"], "missing")

    def test_neg_reset_idempotent_without_second_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "single_clean_reset")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            rst_clean_2_op_id = None
            for ev in events:
                if ev.get("ev") == "enq" and ev.get("verb") == "per_reset_scene":
                    u_s, _, _ = _unpack(ev["args"])
                    if u_s.get("reset_op_id") == "rst-clean-2":
                        rst_clean_2_op_id = ev.get("op_id")
                        break
            filtered = []
            for ev in events:
                if ev.get("ev") == "result":
                    res_list = ev.get("results") or []
                    for res in res_list:
                        if res.get("verb") == "per_reset_scene" and res.get("op_id") == rst_clean_2_op_id:
                            break
                    else:
                        filtered.append(ev)
                        continue
                    continue
                filtered.append(ev)
            bpath.write_text("\n".join(json.dumps(e) for e in filtered) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(_checks_by_id(verdict)["PER-03"]["status"], "pass")

    def test_neg_post_restart_without_new_execution_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            builder.server_epoch_new = builder.server_epoch_old
            part_dir = builder.build_into(Path(tmp) / "same_epoch")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-09"]["status"], "fail")
            self.assertNotEqual(c_map["PER-06"]["status"], "pass")

    def test_neg_ground_query_reads_zero_zero_n48(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "ground_query_0_0")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") in ("enq", "poll"):
                    if ev.get("verb") == "ground_query":
                        ev["args"].pop("x", None)
                        ev["args"].pop("z", None)
                    for op in ev.get("ops") or []:
                        if op.get("verb") == "ground_query":
                            op["args"].pop("x", None)
                            op["args"].pop("z", None)
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-01"]["status"], "missing")

    def test_creature_far_movement_with_and_without_t5_track_disk_n39_n49(self) -> None:
        # With t5_track_* disk -> PASS
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder(
                "run", creature_far_move_m=75.0, include_t5_track_disks=True
            ).build_into(Path(tmp) / "far_covered")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict, indent=2))

        # Without t5_track_* disk -> MISSING (post_restart_creature_coverage_missing)
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder(
                "run", creature_far_move_m=75.0, include_t5_track_disks=False
            ).build_into(Path(tmp) / "far_uncovered")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-08"]["status"], "missing")
            self.assertIn("post_restart_creature_coverage_missing", c_map["PER-08"]["detail"])

    def test_neg_lease_expired_rejected_by_evaluator_e1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "lease_expired")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            events.append({
                "ev": "result",
                "peer": "server",
                "inst": "srv-epoch-1001",
                "results": [{
                    "op_id": "exp-op-1",
                    "verb": "per_apply_scene",
                    "status": "error",
                    "reason": "lease_expired",
                    "dup": 0,
                    "recv_ms": 1000.0,
                    "done_ms": 1001.0,
                    "frame_recv": 10,
                    "frame_done": 10,
                    "read": {},
                }],
            })
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertIn("lease_expired", verdict["reasons"])

    # =========================================================================
    # Static scanner, historical invariance (N44), op_id/qa_fault invariance, check_12
    # =========================================================================

    def test_static_scanner_clean_and_negative_injections(self) -> None:
        _git_head, _stamp, persist_files = _get_git_head_and_persist_sources()
        self.assertEqual(s_persist_eval.scan_persist_enforcescript_sources(persist_files), [])

        base_rel, base_src = next(iter(persist_files.items()))
        # Comments with forbidden tokens are ignored
        commented = base_src + "\n// GetCEApi() OpenFile(\"$mission:storage_1\") arr.Remove(0);\n/* ECE_DYNAMIC_PERSISTENCY */\n"
        self.assertEqual(
            s_persist_eval.scan_persist_enforcescript_sources({base_rel: commented}), []
        )

        # Every forbidden token and substring outside comments triggers a violation
        for tok in ("GetCEApi", "CEApi", "ECE_DYNAMIC_PERSISTENCY", "OpenFile", "FileSerializer", "JsonFileLoader"):
            injected = base_src + f"\nvoid Bad() {{ {tok} x; }}\n"
            v = s_persist_eval.scan_persist_enforcescript_sources({base_rel: injected})
            self.assertTrue(v, msg=f"Failed to detect {tok}")

        for sub in ("$mission:", "$saves:", "$profile:"):
            injected = base_src + f'\nstring p = "{sub}storage_1";\n'
            v = s_persist_eval.scan_persist_enforcescript_sources({base_rel: injected})
            self.assertTrue(v, msg=f"Failed to detect {sub}")

        # E3: unordered .Remove( is forbidden
        injected_remove = base_src + "\nvoid BadRemove() { m_Records.Remove(0); }\n"
        self.assertTrue(
            s_persist_eval.scan_persist_enforcescript_sources({base_rel: injected_remove})
        )

    def test_historical_evaluation_invariant_and_tamper_detected_n44(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "hist")
            v1 = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(v1["exit_code"], 0)

            # Tampering with probe_sources_at_commit so it differs from git show <git_head> yields PER-10 == "missing"
            spath = part_dir / "samples" / "scenario.jsonl"
            events = [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "probe_sources_at_commit":
                    for k in list(ev["persist_files"].keys()):
                        ev["persist_files"][k] += "\n// tampered working tree\n"
            spath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            v2 = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(v2["exit_code"], 2)
            c_map = _checks_by_id(v2)
            self.assertEqual(c_map["PER-10"]["status"], "missing")
            self.assertEqual(c_map["PER-10"]["detail"], "artifact_unverified")

    def test_verdict_invariant_under_op_id_renaming_and_qa_fault_padding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p1 = _SyntheticPartBuilder("run", nonce="1111222233334444", fault_code="").build_into(
                Path(tmp) / "p1"
            )
            p2 = _SyntheticPartBuilder(
                "run", nonce="9999aaaabbbbcccc", fault_code="synthetic_noop_fault"
            ).build_into(Path(tmp) / "p2")
            v1 = s_persist_eval.evaluate(p1, repo_root=REPO_ROOT)
            v2 = s_persist_eval.evaluate(p2, repo_root=REPO_ROOT)
            self.assertEqual(v1["exit_code"], 0)
            self.assertEqual(v2["exit_code"], 0)
            self.assertEqual(v1["checks"], v2["checks"])

    # =========================================================================
    # End-to-End tests requiring runner & extension implementation (ENCARGO.md §4.1)
    # =========================================================================

    def _verify_gate_evidence_with_frozen_oracle(self, ev_dir: Path) -> dict[str, Any]:
        expected_parts = ["run"] + [f"mut-{m}" for m in s_persist_mutants.EXPECTED_MUTANTS]
        for pname in expected_parts:
            pdir = ev_dir / pname
            if not (
                pdir.is_dir()
                and (pdir / "manifest.json").is_file()
                and (pdir / "part.json").is_file()
                and (pdir / "samples" / "bridge.jsonl").is_file()
                and (pdir / "samples" / "scenario.jsonl").is_file()
            ):
                return {"verdict": "INCONCLUSO", "exit_code": 2, "reason": f"missing_part_files:{pname}"}
            if pname.startswith("mut-") and not (pdir / "injection.json").is_file():
                return {"verdict": "INCONCLUSO", "exit_code": 2, "reason": f"missing_injection:{pname}"}
            v = s_persist_eval.evaluate(pdir, repo_root=REPO_ROOT)
            gate_core.write_json(pdir / "verdict.json", v)
            c_map = _checks_by_id(v)
            if pname == "run":
                if v["exit_code"] != 0 or v["verdict"] != "PASA":
                    return {"verdict": v["verdict"], "exit_code": v["exit_code"], "reason": "run_not_pasa"}
                if any(c_map[cid]["status"] != "pass" for cid in s_persist_eval.CHECK_IDS):
                    return {"verdict": "FALLA", "exit_code": 1, "reason": "run_check_not_pass"}
            else:
                mname = pname[len("mut-") :]
                mspec = s_persist_mutants.EXPECTED_MUTANTS[mname]
                must_fail = set(mspec["must_fail_checks"])
                if v["exit_code"] != 1 or v["verdict"] != "FALLA":
                    return {"verdict": "INCONCLUSO", "exit_code": 2, "reason": f"mutant_not_falla:{pname}"}
                for cid in s_persist_eval.CHECK_IDS:
                    exp_st = "fail" if cid in must_fail else "pass"
                    if c_map[cid]["status"] != exp_st:
                        return {"verdict": "INCONCLUSO", "exit_code": 2, "reason": f"mutant_check_mismatch:{pname}:{cid}"}
        agg = f03_common.aggregate_spike(
            ev_dir,
            "S-persist",
            repo_root=REPO_ROOT,
            expected_mutants=s_persist_mutants.EXPECTED_MUTANTS,
            expected_harness_tests=s_persist_mutants.EXPECTED_HARNESS_TESTS,
        )
        return agg

    def test_e2e_m1_gate_spike_s_persist_offline_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp) / "e2e_offline"
            rc = m1_gate.main([
                "spike",
                "S-persist",
                "--both",
                "--build",
                "offline",
                "--evidence",
                str(ev_dir),
            ])
            self.assertEqual(rc, 0)
            root_verdict = json.loads((ev_dir / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(root_verdict["verdict"], "PASA")
            self.assertEqual(root_verdict["exit_code"], 0)
            # BLOQ 1: Re-evaluate every part and re-aggregate with the frozen oracle
            verified_agg = self._verify_gate_evidence_with_frozen_oracle(ev_dir)
            self.assertEqual(verified_agg["exit_code"], 0, msg=json.dumps(verified_agg, indent=2))
            self.assertEqual(verified_agg["verdict"], "PASA")

    def test_e2e_lease_expired_blocks_effects_and_allows_cleanup_e1(self) -> None:
        import os
        import time

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump(
                {
                    "url": "http://127.0.0.1:18999/",
                    "key": "test-key",
                    "retry_ms": 2000,
                    "callback_budget": 2000,
                },
                tf,
            )
            config_path = tf.name
        try:
            now_box = [1000.0]
            peer = fake_peer.Peer(
                config_path,
                "server",
                0,
                30.0,
                "",
                clock_ms_fn=lambda: now_box[0],
            )
            peer.hello_ok = True
            peer.last_ok_ms = 1000.0
            self.assertTrue(peer.lease_valid())

            def _make_valid_op(
                op_id: str,
                verb: str,
                payload: dict[str, Any],
                issued_ms: float,
                ttl_ms: int = 10000,
            ) -> dict[str, Any]:
                norm_args = f03_common._normalize_new_verb_args(payload, "")
                return {
                    "op_id": op_id,
                    "verb": verb,
                    "args": norm_args,
                    "inst": peer.inst,
                    "ttl_ms": ttl_ms,
                    "issued_ms": float(issued_ms),
                }

            # 1) While lease is valid, prepare state on peer (apply scene_a_clean + spawn raw a_foreign_ground + start census job)
            fixture = json.loads(
                (QA_DIR / "fixtures" / "s_persist_fixture.json").read_text(encoding="utf-8")
            )
            in_scol = ["logical_id", "parent_id", "cat", "class_name", "slot_name"]
            in_ncol = ["req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"]
            clean_in_rows = [
                {
                    "logical_id": e["logical_id"],
                    "parent_id": e["parent_id"],
                    "cat": e["cat"],
                    "class_name": e["class_name"],
                    "slot_name": e["slot_name"],
                    "req_x_m": float(e["req_x_m"]),
                    "req_z_m": float(e["req_z_m"]),
                    "req_yaw_deg": float(e["req_yaw_deg"]),
                    "health_mark_ratio": float(e["health_mark_ratio"]),
                    "must_vanish_b": float(e["must_vanish_on_restart_b"]),
                }
                for e in fixture["scenes"]["scene_a_clean"]["entities"]
            ]
            prep_results: list[dict[str, Any]] = []
            prep_apply_op = _make_valid_op(
                "op-prep-apply",
                "per_apply_scene",
                wire.pack_payload(
                    scalars_str={
                        "scene_id": "scene_a_clean",
                        "scene_op_id": "prep-scop-1",
                        "expect_epoch": peer.inst,
                        "q9_pathway": "a",
                    },
                    scalars_num={"gen_n": 1.0},
                    num_cols=in_ncol,
                    str_cols=in_scol,
                    row_dicts=clean_in_rows,
                ),
                now_box[0],
            )
            peer._start_op(prep_apply_op, now_box[0], time.monotonic(), prep_results)

            prep_raw_op = _make_valid_op(
                "op-prep-raw",
                "per_spawn_raw",
                wire.pack_payload(
                    scalars_str={
                        "tag": "a_foreign_ground",
                        "mode": "foreign_ground",
                        "class_name": "WaterBottle",
                        "child_cargo_class": "",
                        "target_scene_id": "",
                        "target_parent_id": "",
                    },
                    scalars_num={
                        "x_m": 4504.0,
                        "z_m": 10202.0,
                        "yaw_deg": 25.0,
                        "health_mark_ratio": 0.615,
                    },
                ),
                now_box[0],
            )
            peer._start_op(prep_raw_op, now_box[0], time.monotonic(), prep_results)

            prep_status_op = _make_valid_op(
                "op-prep-status", "per_status", wire.pack_payload(), now_box[0]
            )
            peer._start_op(prep_status_op, now_box[0], time.monotonic(), prep_results)

            prep_census_op = _make_valid_op(
                "op-prep-census",
                "per_census_start",
                wire.pack_payload(
                    scalars_str={"area_tag": "t1_pre_transition_census:area_a"},
                    scalars_num={
                        "center_x_m": 4500.0,
                        "center_z_m": 10200.0,
                        "radius_m": 60.0,
                        "include_director_b": 1.0,
                    },
                ),
                now_box[0],
            )
            peer._start_op(prep_census_op, now_box[0], time.monotonic(), prep_results)

            prep_by_id = {r["op_id"]: r for r in prep_results}
            self.assertEqual(prep_by_id["op-prep-apply"]["status"], "done")
            self.assertEqual(prep_by_id["op-prep-raw"]["status"], "done")
            self.assertEqual(prep_by_id["op-prep-status"]["status"], "done")
            self.assertEqual(prep_by_id["op-prep-census"]["status"], "done")
            _, prep_st_n, _ = _unpack(prep_by_id["op-prep-status"]["read"])
            self.assertEqual(prep_st_n["registered_total_n"], 6.0)
            self.assertEqual(prep_st_n["scenes_count_n"], 1.0)

            # 2) Advance virtual clock past PEER_LEASE_TIMEOUT_MS (5000 ms) without polling so lease expires
            now_box[0] = 7500.0
            self.assertFalse(peer.lease_valid())

            # Stepping jobs after lease expiry must fail the running per_census job with lease_expired
            peer._step_extensions_and_jobs(0.05)

            results: list[dict[str, Any]] = []
            jr_op = _make_valid_op(
                "op-jr-expired",
                "job_read",
                wire.pack_payload(scalars_str={"job": "op-prep-census"}, scalars_num={"page_n": 0.0}),
                now_box[0],
            )
            peer._start_op(jr_op, now_box[0], time.monotonic(), results)

            for idx, verb in enumerate(
                ("per_apply_scene", "per_reset_scene", "per_child_transition", "per_spawn_raw", "per_census_start")
            ):
                op = _make_valid_op(f"op-exp-{idx}", verb, wire.pack_payload(), now_box[0])
                peer._start_op(op, now_box[0], time.monotonic(), results)

            # Check per_status before cleanup: prepared state must still be intact (6 own entities, 1 scene)
            mid_status_op = _make_valid_op(
                "op-mid-status", "per_status", wire.pack_payload(), now_box[0]
            )
            peer._start_op(mid_status_op, now_box[0], time.monotonic(), results)

            # 3) per_cleanup_qa is allowed even with expired lease and cleans up the prepared state
            clean_op = _make_valid_op(
                "op-clean",
                "per_cleanup_qa",
                wire.pack_payload(scalars_str={"cleanup_tag": "t6"}),
                now_box[0],
            )
            peer._start_op(clean_op, now_box[0], time.monotonic(), results)

            post_status_op = _make_valid_op(
                "op-post-status", "per_status", wire.pack_payload(), now_box[0]
            )
            peer._start_op(post_status_op, now_box[0], time.monotonic(), results)

            by_id = {r["op_id"]: r for r in results}
            jr_s, _, _ = _unpack(by_id["op-jr-expired"]["read"])
            self.assertEqual(jr_s["state"], "failed")
            self.assertEqual(jr_s["reason"], "lease_expired")

            for idx in range(5):
                r = by_id.get(f"op-exp-{idx}")
                self.assertIsNotNone(r)
                self.assertEqual(r["status"], "error")
                self.assertEqual(r["reason"], "lease_expired")

            _, mid_st_n, _ = _unpack(by_id["op-mid-status"]["read"])
            self.assertEqual(mid_st_n["registered_total_n"], 6.0)
            self.assertEqual(mid_st_n["scenes_count_n"], 1.0)

            r_clean = by_id.get("op-clean")
            self.assertIsNotNone(r_clean)
            self.assertEqual(r_clean["status"], "done")
            _, clean_n, _ = _unpack(r_clean["read"])
            self.assertEqual(clean_n["cleaned_own_n"], 6.0)
            self.assertGreaterEqual(clean_n["cleaned_raw_n"], 1.0)

            _, post_st_n, _ = _unpack(by_id["op-post-status"]["read"])
            self.assertEqual(post_st_n["registered_total_n"], 0.0)
            self.assertEqual(post_st_n["scenes_count_n"], 0.0)
        finally:
            os.unlink(config_path)

    # =========================================================================
    # Negative tests for Sol's 12 BLOQs (ARREGLOS_r3_sol.md §3)
    # =========================================================================

    def test_neg_bloq01_fabricator_runner_rejected_by_frozen_oracle(self) -> None:
        """BLOQ 1: A runner that writes verdict.json=PASA without valid samples/parts is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp) / "fabricated_gate"
            ev_dir.mkdir(parents=True, exist_ok=True)
            gate_core.write_json(
                ev_dir / "verdict.json",
                {"schema": "m1-verdict-v1", "id": "S-persist", "verdict": "PASA", "exit_code": 0, "checks": [], "metrics": {}, "reasons": []},
            )
            for pname in ("run", "mut-unprotected_leak", "mut-foreign_wiped"):
                pdir = ev_dir / pname
                (pdir / "samples").mkdir(parents=True, exist_ok=True)
                gate_core.write_json(
                    pdir / "verdict.json",
                    {"schema": "m1-verdict-v1", "id": "S-persist", "verdict": "PASA", "exit_code": 0, "checks": [], "metrics": {}, "reasons": []},
                )
            verified = self._verify_gate_evidence_with_frozen_oracle(ev_dir)
            self.assertIn(verified["exit_code"], (1, 2))
            self.assertNotEqual(verified["verdict"], "PASA")

    def test_neg_bloq02_orders_missing_inst_or_ttl_rejected_before_ext(self) -> None:
        """BLOQ 2: Orders missing inst or ttl_ms/issued_ms are rejected by Peer._start_op and fail evaluation."""
        import os
        import time

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump({"url": "http://127.0.0.1:18999/", "key": "k"}, tf)
            config_path = tf.name
        try:
            now_box = [1000.0]
            peer = fake_peer.Peer(config_path, "server", 0, 30.0, "", clock_ms_fn=lambda: now_box[0])
            peer.hello_ok = True
            peer.last_ok_ms = 1000.0
            res_bucket: list[dict[str, Any]] = []
            # Missing inst -> rejected/stale_instance
            peer._start_op({"op_id": "no-inst", "verb": "per_cleanup_qa", "args": wire.pack_payload()}, now_box[0], time.monotonic(), res_bucket)
            # Missing ttl_ms/issued_ms -> rejected/expired
            peer._start_op({"op_id": "no-ttl", "verb": "per_cleanup_qa", "inst": peer.inst, "args": wire.pack_payload()}, now_box[0], time.monotonic(), res_bucket)
            by_id = {r["op_id"]: r for r in res_bucket}
            self.assertEqual(by_id["no-inst"]["status"], "rejected")
            self.assertEqual(by_id["no-inst"]["reason"], "stale_instance")
            self.assertEqual(by_id["no-ttl"]["status"], "rejected")
            self.assertEqual(by_id["no-ttl"]["reason"], "expired")
        finally:
            os.unlink(config_path)

        # In evaluator: if per_cleanup_qa or census is rejected with stale_instance/expired, verdict is not PASA
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "stale_inst_trace")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            res["status"] = "rejected"
                            res["reason"] = "stale_instance"
                            break
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(verdict["verdict"], "PASA")

    def test_neg_bloq03_post_restart_census_reuses_old_job_pages(self) -> None:
        """BLOQ 3: Reusing t0 job_id in t5_post_restart_census without t5 job_read/job_free is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "reuse_job_t5")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]

            t0_jobs_by_area: dict[str, str] = {}
            t5_jobs_to_strip: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, u_n, u_r = _unpack(res["read"])
                            atag = u_s.get("area_tag", "")
                            if atag.startswith("t0_baseline_census:"):
                                aid = atag.split(":", 1)[1]
                                t0_jobs_by_area[aid] = u_s["job"]
                            elif atag in ("t5_post_restart_census:area_a", "t5_post_restart_census:area_b"):
                                aid = atag.split(":", 1)[1]
                                old_jid = t0_jobs_by_area[aid]
                                t5_jobs_to_strip.add(u_s["job"])
                                u_s["job"] = old_jid
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)

            filtered: list[dict[str, Any]] = []
            for ev in events:
                if ev.get("ev") in ("enq", "poll"):
                    args = ev.get("args") or ((ev.get("ops") or [{}])[0].get("args") if ev.get("ops") else None)
                    verb = ev.get("verb") or ((ev.get("ops") or [{}])[0].get("verb") if ev.get("ops") else "")
                    if verb in ("job_read", "job_free") and isinstance(args, dict):
                        u_s, _, _ = _unpack(args)
                        if u_s.get("job") in t5_jobs_to_strip:
                            continue
                elif ev.get("ev") == "result":
                    res_list = ev.get("results") or []
                    if res_list and res_list[0].get("verb") in ("job_read", "job_free"):
                        u_s, _, _ = _unpack(res_list[0]["read"])
                        if u_s.get("job") in t5_jobs_to_strip:
                            continue
                filtered.append(ev)

            bpath.write_text("\n".join(json.dumps(e) for e in filtered) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(verdict["verdict"], "PASA")
            self.assertIn("reused_census_job_id", verdict["reasons"])

    def test_neg_bloq04_per01_census_zero_health_or_unlabeled_duplicate(self) -> None:
        """BLOQ 4: PER-01 rejects alive_b=max_hp=health_hp=0 in census OR an extra unlabeled Barrel_Green."""
        # Subcase A: alive_b = max_hp = health_hp = 0 in t1_pre_transition_census
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "zero_hp_census")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            t1_pre_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if "t1_pre_transition_census" in u_s.get("area_tag", ""):
                                t1_pre_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t1_pre_jobs:
                                for row in u_r:
                                    if row.get("own_logical_id") == "a_prop_1":
                                        row["alive_b"] = 0.0
                                        row["max_hp"] = 0.0
                                        row["health_hp"] = 0.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-01"]["status"], "fail")

        # Subcase B: Duplicate Barrel_Green labeled as foreign (own_b=0, own_logical_id="") in t1_pre and t3_post
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "unlabeled_dup_barrel")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            target_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("area_tag") in (
                                "t1_pre_transition_census:area_a",
                                "t3_post_reset_census:area_a",
                            ):
                                target_jobs.add(u_s["job"])
                                u_n["rows_captured_n"] = float(u_n["rows_captured_n"]) + 1.0
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in target_jobs:
                                u_n["rows_total_n"] = float(u_n["rows_total_n"]) + 1.0
                                if int(round(u_n["page_n"])) == int(round(u_n["pages_n"])) - 1:
                                    u_r.append({
                                        "class_name": "Barrel_Green",
                                        "loc_kind": "ground",
                                        "parent_class": "",
                                        "parent_net_id": "",
                                        "slot_name": "",
                                        "owner_uid": "",
                                        "own_logical_id": "",
                                        "net_id": "1:9999",
                                        "pers_id": "0:0:0:0",
                                        "own_b": 0.0,
                                        "in_radius_b": 1.0,
                                        "alive_b": 1.0,
                                        "ai_agent_b": 0.0,
                                        "pos_x_m": 4502.0,
                                        "pos_y_m": _surface_y(4502.0, 10202.0),
                                        "pos_z_m": 10202.0,
                                        "yaw_deg": 15.0,
                                        "pitch_deg": 0.0,
                                        "roll_deg": 0.0,
                                        "max_hp": 100.0,
                                        "health_hp": 100.0,
                                        "inv_children_n": 0.0,
                                        "spawn_tick_ms": 1500.0,
                                    })
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-01"]["status"], "fail")
            self.assertEqual(c_map["PER-03"]["status"], "fail")
            self.assertEqual(c_map["PER-04"]["status"], "fail")

    def test_neg_bloq05_retained_containers_and_foreign_cargo_displaced_n52(self) -> None:
        """BLOQ 5: Moving retained containers and their foreign/cross cargo by 10 m after reset fails PER-05."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "moved_retained_n52")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            t3_post_a_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if u_s.get("area_tag") == "t3_post_reset_census:area_a":
                                t3_post_a_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t3_post_a_jobs:
                                for row in u_r:
                                    if row.get("class_name") in (
                                        "WoodenCrate",
                                        "SeaChest",
                                        "FirstAidKit",
                                        "SewingKit",
                                        "Compass",
                                        "BandageDressing",
                                    ):
                                        row["pos_x_m"] = float(row["pos_x_m"]) + 10.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-05"]["status"], "fail")

    def test_neg_bloq06_foreign_items_in_wrong_parent_container(self) -> None:
        """BLOQ 6: Placing a_foreign_in_chest and a_foreign_in_child_kit in another container fails PER-01/04/05."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "wrong_foreign_parent")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            wrong_parent_nid = builder.entities_by_lid["b_chest_foreign"]["net_id"]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            for row in u_r:
                                if row.get("class_name") in ("Compass", "BandageDressing"):
                                    row["parent_net_id"] = wrong_parent_nid
                                    row["parent_class"] = "SeaChest"
                            res["read"] = builder._pack_ext_read(
                                strings=u_s,
                                numbers=u_n,
                                ncol=res["read"]["ncol"],
                                scol=res["read"]["scol"],
                                rows=u_r,
                            )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-01"]["status"], "fail")
            self.assertEqual(c_map["PER-04"]["status"], "fail")
            self.assertEqual(c_map["PER-05"]["status"], "fail")

    def test_neg_bloq07_unaccredited_reachable_volume_before_or_after_restart_n49(self) -> None:
        """BLOQ 7: Unaccredited time gap between last pre-restart census and t5 census returns INCONCLUSO."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "unaccredited_gap_n49")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Advance ALL t5_post_restart_census snap_tick_ms by 12000 ms (12 s * 6 m/s = 72 m > 60 m disk)
            # to maintain E9 resource non-overlap chronological order across areas
            t5_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("area_tag", "").startswith("t5_post_restart_census:"):
                                t5_jobs.add(u_s["job"])
                                u_n["snap_tick_ms"] = float(u_n["snap_tick_ms"]) + 12000.0
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t5_jobs:
                                for tk in ("start_tick_ms", "end_tick_ms", "onjobend_tick_ms", "released_tick_ms"):
                                    u_n[tk] = float(u_n[tk]) + 12000.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
                        elif res.get("verb") == "job_free":
                            u_s, _, _ = _unpack(res["read"])
                            if u_s.get("job") in t5_jobs:
                                # job_free has minimal read payload, just advance by recreating
                                u_s["freed"] = "1"
                                # Advance timestamps in the read payload if present
                                u_n = {}
                                for tk in ("start_tick_ms", "end_tick_ms", "onjobend_tick_ms", "released_tick_ms"):
                                    u_n[tk] = 12000.0  # This is a hack; job_free read doesn't have these
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=[])
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-08"]["status"], "missing")
            self.assertIn("post_restart_creature_coverage_missing", c_map["PER-08"]["detail"])

    def test_neg_bloq08_per10_source_omission_and_substitution(self) -> None:
        """BLOQ 8: Substituting DSBX_QA_X_Persist.c with DSBX_QA_Stamp.c in persist_files is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "subst_stamp_c")
            stamp_rel = "DayZSandbox_dev/qa/probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_Stamp.c"
            proc = subprocess.run(
                ["git", "show", f"{builder.git_head}:{stamp_rel}"],
                cwd=str(REPO_ROOT),
                capture_output=True,
                timeout=15,
                check=True,
            )
            stamp_text = proc.stdout.decode("utf-8")
            spath = part_dir / "samples" / "scenario.jsonl"
            events = [json.loads(l) for l in spath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "probe_sources_at_commit":
                    ev["persist_files"] = {stamp_rel: stamp_text}
            spath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-10"]["status"], "missing")
            self.assertEqual(c_map["PER-10"]["detail"], "artifact_unverified")

    def test_neg_bloq09_per02_fixed_zero_spawn_tick_or_short_hold(self) -> None:
        """BLOQ 9: Setting crow['spawn_tick_ms']=0 with snap_tick_ms=600000 when created at 1520 fails PER-02."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "zero_spawn_tick")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            t2_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if "t2_census_10min" in u_s.get("area_tag", ""):
                                t2_jobs.add(u_s["job"])
                                u_n["snap_tick_ms"] = 600000.0
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t2_jobs:
                                for tk in ("start_tick_ms", "end_tick_ms", "onjobend_tick_ms", "released_tick_ms"):
                                    u_n[tk] = 600000.0
                                for row in u_r:
                                    if row.get("own_logical_id") == "a_inf_1":
                                        row["spawn_tick_ms"] = 0.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-02"]["status"], "fail")

    def test_neg_bloq10_per09_invented_apple_witness_scene_rejected(self) -> None:
        """BLOQ 10: Replacing the 11 witness entities of scene_b with Apple fails PER-09."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "apple_witness")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            wit_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if u_s.get("area_tag") in (
                                "t5_witness_pre_census:area_b",
                                "t5_witness_post_census:area_b",
                            ):
                                wit_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in wit_jobs:
                                for row in u_r:
                                    if int(round(float(row.get("own_b", 0.0)))) == 1:
                                        row["class_name"] = "Apple"
                                        row["loc_kind"] = "ground"
                                        row["parent_class"] = ""
                                        row["parent_net_id"] = ""
                                        row["slot_name"] = ""
                                        row["inv_children_n"] = 0.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "fail")

    def test_neg_bloq11_per09_interleaved_polls_and_wrong_semantic_order(self) -> None:
        """BLOQ 11: Interleaved polls/ops between witness status and census pass; wrong semantic order fails."""
        # 1) Honest trace with 10 interleaved operations between wit_pre_status and wit_pre_census -> PASA
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "interleaved_wit")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            new_events: list[dict[str, Any]] = []
            for ev in events:
                if ev.get("ev") == "enq" and ev.get("verb") == "per_census_start":
                    u_s, _, _ = _unpack(ev["args"])
                    if u_s.get("area_tag") == "t5_witness_pre_census:area_b":
                        for k in range(10):
                            noop_id = f"interleaved-noop-{k}"
                            new_events.append({"ev": "enq", "peer": "client", "op_id": noop_id, "verb": "cli_Ping", "args": {}, "h_ms": 620000.0 + k})
                            new_events.append({
                                "ev": "result",
                                "peer": "client",
                                "inst": builder.client_inst,
                                "results": [{"op_id": noop_id, "verb": "cli_Ping", "status": "done", "reason": "", "dup": 0, "recv_ms": 620000.0 + k, "done_ms": 620000.5 + k, "frame_recv": 100, "frame_done": 100, "read": {}}],
                            })
                new_events.append(ev)
            bpath.write_text("\n".join(json.dumps(e) for e in new_events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict, indent=2))
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "pass")

        # 2) Dishonest trace where post-stale witness status is omitted -> INCONCLUSO (exit_code == 2)
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "missing_post_wit_status")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            seen_stale_apply = False
            filtered: list[dict[str, Any]] = []
            for ev in events:
                if ev.get("ev") == "result":
                    res_list = ev.get("results") or []
                    if res_list and res_list[0].get("verb") == "per_apply_scene" and res_list[0].get("reason") == "stale_epoch":
                        seen_stale_apply = True
                    elif seen_stale_apply and res_list and res_list[0].get("verb") == "per_status":
                        continue
                filtered.append(ev)
            bpath.write_text("\n".join(json.dumps(e) for e in filtered) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(_checks_by_id(verdict)["PER-09"]["status"], "pass")

    def test_neg_bloq12_resource_arbitrary_no_lock_and_concurrent_contention(self) -> None:
        """BLOQ 12: Changing census resource to 'arbitrary_no_lock' or overlapping census jobs is rejected."""
        # Subcase A: resource changed to "arbitrary_no_lock" in job_read
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "arbitrary_no_lock")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") in ("per_census_start", "job_read"):
                            u_s, u_n, u_r = _unpack(res["read"])
                            if "resource" in u_s:
                                u_s["resource"] = "arbitrary_no_lock"
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"].get("ncol"),
                                    scol=res["read"].get("scol"),
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(verdict["verdict"], "PASA")
            self.assertIn("invalid_census_resource", verdict["reasons"])

        # Subcase B: Two per_census_start jobs overlap in time on the server (unprotected concurrent contention)
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "overlapping_census")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Make t0_baseline_census:area_b start before t0_baseline_census:area_a released its lock
            t0_a_job = None
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("area_tag") == "t0_baseline_census:area_a":
                                t0_a_job = u_s["job"]
                        elif res.get("verb") == "job_read" and t0_a_job:
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") == t0_a_job:
                                u_n["end_tick_ms"] = float(u_n["start_tick_ms"]) + 5000.0
                                u_n["onjobend_tick_ms"] = float(u_n["start_tick_ms"]) + 5000.0
                                u_n["released_tick_ms"] = float(u_n["start_tick_ms"]) + 5000.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertIn(verdict["exit_code"], (1, 2))
            self.assertNotEqual(verdict["verdict"], "PASA")
            self.assertIn("unprotected_census_resource_overlap", verdict["reasons"])


if __name__ == "__main__":
    unittest.main()
