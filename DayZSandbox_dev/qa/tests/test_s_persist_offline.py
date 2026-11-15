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

import bridge_qa
import f03_common
import fake_peer
import gate_core
import m1_gate
import s_persist_eval
import s_persist_mutants
import wire
from s_persist_eval import _unpack_any_payload


def _surface_y(x: float, z: float) -> float:
    return 100.0 + 10.0 * math.sin(float(x) / 100.0) * math.cos(float(z) / 100.0)


def _get_git_head_and_persist_sources() -> tuple[str, str, dict[str, str]]:
    """MEN-7: enumera TODOS los DSBX_QA_X_Persist*.c del commit con git ls-tree (como el evaluador)."""
    git_head = gate_core.git_harness(repo_root=REPO_ROOT)["git_head"]
    stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=REPO_ROOT)
    listing = subprocess.run(
        [
            "git", "-c", "core.autocrlf=false", "ls-tree", "-r", "--name-only", git_head, "--",
            "DayZSandbox_dev/qa/probe/DayZSandbox_QA/scripts",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    sources: dict[str, str] = {}
    for rel_path in listing.stdout.splitlines():
        rel_path = rel_path.strip()
        name = rel_path.rsplit("/", 1)[-1]
        if not (name.startswith("DSBX_QA_X_Persist") and name.endswith(".c")):
            continue
        proc = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "show", f"{git_head}:{rel_path}"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            timeout=15,
            check=True,
        )
        sources[rel_path] = proc.stdout.decode("utf-8")
    if not sources:
        raise AssertionError("no DSBX_QA_X_Persist*.c found at " + git_head)
    return git_head, stamp, sources


def _unpack(obj: dict[str, Any]) -> tuple[dict[str, str], dict[str, float], list[dict[str, Any]]]:
    u = wire.unpack_payload(obj)
    return u["str"], u["num"], u["rows"]


def _checks_by_id(verdict: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in verdict["checks"]}


def _shift_epoch_chronology_from_t5(
    events: list[dict[str, Any]],
    server_epoch_new: str,
    delta_ms: float,
) -> None:
    """
    Shift all time fields for all operations in server_epoch_new from the first
    t5_post_restart_census onwards by delta_ms. Modifies events in place.

    This ensures coherent chronology: when t5_post_restart_census is delayed,
    all subsequent censuses and operations in the same epoch shift together,
    preventing false resource overlap detections.
    """
    t5_started = False
    for ev in events:
        if ev.get("ev") == "result":
            inst = ev.get("inst")
            if inst != server_epoch_new:
                continue
            for res in ev.get("results") or []:
                verb = res.get("verb")
                if verb == "per_census_start":
                    try:
                        u_s, u_n, u_r = _unpack(res["read"])
                        area_tag = u_s.get("area_tag", "")
                        if area_tag.startswith("t5_post_restart_census:"):
                            t5_started = True
                    except (ValueError, KeyError):
                        pass
                if t5_started:
                    _shift_result_time_fields(res, delta_ms)
            if t5_started and "h_ms" in ev:
                ev["h_ms"] = float(ev["h_ms"]) + delta_ms
            if t5_started and "t_ms" in ev:
                ev["t_ms"] = float(ev["t_ms"]) + delta_ms
        elif ev.get("ev") in ("enq", "poll"):
            if ev.get("inst") == server_epoch_new and t5_started:
                if "h_ms" in ev:
                    ev["h_ms"] = float(ev["h_ms"]) + delta_ms
                if "t_ms" in ev:
                    ev["t_ms"] = float(ev["t_ms"]) + delta_ms


def _shift_result_time_fields(res: dict[str, Any], delta_ms: float) -> None:
    """Shift all *_tick_ms fields in a result's read payload by delta_ms."""
    verb = res.get("verb")
    if "read" not in res:
        return
    try:
        u_s, u_n, u_r = _unpack(res["read"])
    except (ValueError, KeyError):
        return
    shifted = False
    if verb == "per_census_start":
        if "snap_tick_ms" in u_n:
            u_n["snap_tick_ms"] = float(u_n["snap_tick_ms"]) + delta_ms
            shifted = True
        if "snap_frame" in u_n:
            pass
    elif verb == "job_read":
        for tk in ("start_tick_ms", "end_tick_ms", "onjobend_tick_ms", "released_tick_ms", "elapsed_dtsum_ms"):
            if tk in u_n:
                u_n[tk] = float(u_n[tk]) + delta_ms
                shifted = True
    elif verb == "job_free":
        pass
    elif verb == "per_status":
        if "tick_ms" in u_n:
            u_n["tick_ms"] = float(u_n["tick_ms"]) + delta_ms
            shifted = True
        if "frame" in u_n:
            pass
    elif verb == "per_cleanup_qa":
        if "tick_ms" in u_n:
            u_n["tick_ms"] = float(u_n["tick_ms"]) + delta_ms
            shifted = True
        if "frame" in u_n:
            pass
    elif verb == "per_apply_scene":
        if "q9_tick_ms" in u_n:
            u_n["q9_tick_ms"] = float(u_n["q9_tick_ms"]) + delta_ms
            shifted = True
        if "q9_frame" in u_n:
            pass
    elif verb == "per_reset_scene":
        if "tick_ms" in u_n:
            u_n["tick_ms"] = float(u_n["tick_ms"]) + delta_ms
            shifted = True
        if "frame" in u_n:
            pass
    elif verb == "per_child_transition":
        if "tick_ms" in u_n:
            u_n["tick_ms"] = float(u_n["tick_ms"]) + delta_ms
            shifted = True
        if "frame" in u_n:
            pass
    elif verb == "per_spawn_raw":
        if "tick_ms" in u_n:
            u_n["tick_ms"] = float(u_n["tick_ms"]) + delta_ms
            shifted = True
        if "frame" in u_n:
            pass
    if shifted:
        res["read"] = _repack_read(u_s, u_n, u_r, res["read"])


def _repack_read(
    strings: dict[str, str],
    numbers: dict[str, float],
    rows: list[dict[str, Any]],
    original_read: dict[str, Any],
) -> dict[str, Any]:
    """Repack a read payload preserving ncol/scol from original."""
    return wire.pack_payload(
        scalars_str=strings,
        scalars_num=numbers,
        num_cols=original_read.get("ncol"),
        str_cols=original_read.get("scol"),
        row_dicts=rows,
    )


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
        t2_hold_ms: float = 605000.0,
    ) -> None:
        self.t2_hold_ms = t2_hold_ms
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
        # Reloj del bridge (t_ms): lo escribe el nucleo, es monotono entre epochs; el tick_ms es del peer.
        self.h_ms = 5000.0
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
        self.h_ms += dt_ms
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
        t_recv = self.h_ms
        self._advance(20.0, 1)
        done_ms = self.tick_ms
        frame_done = self.frame
        t_done = self.h_ms

        self.bridge_events.append({
            "ev": "enq",
            "peer": peer,
            "op_id": oid,
            "verb": verb,
            "args": args,
            "h_ms": recv_ms,
            "t_ms": t_recv,
        })
        self.bridge_events.append({
            "ev": "poll",
            "peer": peer,
            "inst": inst,
            "ops": [{"op_id": oid, "verb": verb, "args": args}],
            "body_len": 512,
            "h_ms": recv_ms,
            "t_ms": t_recv,
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
            "t_ms": t_done,
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
        contention_probe: bool = False,
    ) -> str:
        area_tag = area_id if stage == "t5_post_restart_census" and area_id.startswith("t5_track_") else f"{stage}:{area_id}"
        if stage == "contention_probe":
            area_tag = f"contention_probe:{area_id}"
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

        if contention_probe:
            # MEN-6: con el censo vivo, un segundo per_census_start sobre el mismo recurso.
            # Honesto: rejected/busy. Mutante census_resource_bypass: se acepta y corre entero dentro
            # de la ventana del primero (el recurso no protege).
            probe_tag = f"contention_probe:{area_id}"
            if self.fault_code == "census_resource_bypass":
                self._emit_census(
                    inst, "contention_probe", area_id, center_x, center_z, [],
                    include_director_b=0, director_present_b=director_present_b,
                )
            else:
                probe_args = self._pack_ext_args(
                    strings={"area_tag": probe_tag},
                    numbers={
                        "center_x_m": center_x,
                        "center_z_m": center_z,
                        "radius_m": 60.0,
                        "include_director_b": 0.0,
                    },
                )
                self._emit_op("server", inst, "per_census_start", probe_args, self._pack_ext_read(), status="rejected", reason="busy")

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
        jf_read = self._pack_ext_read(strings={"job": job_id, "freed": "1", "resource": "per_census"})
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
            "t_ms": 100.0,
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
            "t_ms": 110.0,
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
                contention_probe=(aid == "area_a"),
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
        self._advance(self.t2_hold_ms, 18000)
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

        # t4: ultima lectura del epoch viejo (per_status del peer, posterior a t3_post_reset_census)
        self._advance(5000.0, 100)
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
                    "registered_total_n": 11.0,
                    "scenes_count_n": 1.0,
                    "director_present_b": 1.0,
                    "director_alive_b": 1.0,
                    "director_inv_readable_b": 1.0,
                    "director_inv_count_n": 2.0,
                },
                ncol=["gen_n", "own_alive_n"],
                scol=["scene_id", "last_op_id"],
                rows=[{"scene_id": ret_scene_id, "last_op_id": f"rst-{ret_scene_id}-1", "gen_n": 1.0, "own_alive_n": 11.0}],
            ),
        )
        # Parada y arranque: el proceso nuevo tiene su propio reloj (tick_ms pequeno); el bridge sigue.
        self.h_ms += 40000.0
        if self.server_epoch_new != self.server_epoch_old:
            self.tick_ms = 30000.0
            self.frame = 500
        self.bridge_events.append({
            "ev": "hello",
            "peer": "server",
            "inst": self.server_epoch_new,
            "proto": "qa0",
            "build": "offline",
            "probe_ver": probe_ver,
            "http": 200,
            "h_ms": self.tick_ms,
            "t_ms": self.h_ms,
        })
        self._advance(300.0, 5)

        # Primera orden del epoch nuevo: lectura per_status del peer
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
            "params": {
                "wire_cap": wire.WIRE_CAP,
                "probe_budget_log_poll_ms": f03_common.PROBE_BUDGET_LOG_POLL_MS,
                "probe_budget_retry_ms": f03_common.PROBE_BUDGET_RETRY_MS,
            },
            "identity": {
                "build": "offline",
                "git_dirty": False,
                "git_head": self.git_head,
                # D12 del núcleo final: la identidad trae los parámetros de probe-budget de git_head.
                "params": {
                    "wire_cap": wire.WIRE_CAP,
                    "probe_budget_log_poll_ms": f03_common.PROBE_BUDGET_LOG_POLL_MS,
                    "probe_budget_retry_ms": f03_common.PROBE_BUDGET_RETRY_MS,
                },
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


# ---------------------------------------------------------------------------------------------------------
# Helpers de los tests de la ronda 3 (BLOQ-3: fuente independiente del runner)
# ---------------------------------------------------------------------------------------------------------


def _read_events(part_dir: Path) -> list[dict[str, Any]]:
    path = Path(part_dir) / "samples" / "bridge.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_events(part_dir: Path, events: list[dict[str, Any]]) -> None:
    path = Path(part_dir) / "samples" / "bridge.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8", newline="\n")


def _read_scenario(part_dir: Path) -> list[dict[str, Any]]:
    path = Path(part_dir) / "samples" / "scenario.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_scenario(part_dir: Path, events: list[dict[str, Any]]) -> None:
    path = Path(part_dir) / "samples" / "scenario.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8", newline="\n")


def _drop_ops(events: list[dict[str, Any]], op_ids: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in events:
        if ev.get("ev") == "enq" and ev.get("op_id") in op_ids:
            continue
        if ev.get("ev") == "poll" and any(o.get("op_id") in op_ids for o in ev.get("ops") or []):
            continue
        if ev.get("ev") == "result" and any(r.get("op_id") in op_ids for r in ev.get("results") or []):
            continue
        out.append(ev)
    return out


def _status_op_ids(events: list[dict[str, Any]], inst: str) -> list[str]:
    ids: list[str] = []
    for ev in events:
        if ev.get("ev") == "result" and ev.get("inst") == inst:
            for res in ev.get("results") or []:
                if res.get("verb") == "per_status":
                    ids.append(res["op_id"])
    return ids


def _result_t_ms(events: list[dict[str, Any]], op_id: str) -> float:
    for ev in events:
        if ev.get("ev") == "result" and any(r.get("op_id") == op_id for r in ev.get("results") or []):
            return float(ev["t_ms"])
    raise AssertionError(f"no result for {op_id}")


def _append_old_epoch_op(
    builder: "_SyntheticPartBuilder",
    events: list[dict[str, Any]],
    verb: str,
    args: dict[str, Any],
    read: dict[str, Any],
    *,
    op_id: str,
    t_ms: float,
    peer_tick_ms: float,
) -> None:
    inst = builder.server_epoch_old
    events.append({"ev": "enq", "peer": "server", "op_id": op_id, "verb": verb, "args": args, "t_ms": t_ms})
    events.append({"ev": "poll", "peer": "server", "inst": inst, "ops": [{"op_id": op_id, "verb": verb, "args": args}], "t_ms": t_ms})
    events.append({
        "ev": "result", "peer": "server", "inst": inst, "t_ms": t_ms + 20.0,
        "results": [{
            "op_id": op_id, "verb": verb, "status": "done", "reason": "", "dup": 0,
            "recv_ms": peer_tick_ms, "done_ms": peer_tick_ms + 20.0, "frame_recv": 1, "frame_done": 2, "read": read,
        }],
    })


def _result_done_ms(events: list[dict[str, Any]], op_id: str) -> float:
    for ev in events:
        if ev.get("ev") == "result":
            for res in ev.get("results") or []:
                if res.get("op_id") == op_id:
                    return float(res["done_ms"])
    raise AssertionError(f"no result for {op_id}")


def _only_non_pass(verdict: dict[str, Any]) -> dict[str, str]:
    return {c["id"]: c["status"] for c in verdict["checks"] if c["status"] != "pass"}


def _convert_part_to_build(part_dir: Path, build: str) -> None:
    mpath = Path(part_dir) / "manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    manifest["build"] = build
    manifest["identity"]["build"] = build
    manifest["identity"]["peer_builds"] = {"server": build, "client": build}
    mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    events = _read_events(part_dir)
    for ev in events:
        if ev.get("ev") == "hello":
            ev["build"] = build
    _write_events(part_dir, events)


class _CoreTap:
    """BLOQ-3: fuente INDEPENDIENTE del runner.

    Envuelve el nucleo, no al runner: ``QABridge._emit`` (todo el trafico real entre el bridge y los peers),
    ``PartContext.open`` (que parte y que bridge) y ``PartContext._spawn_peers`` (los PID de los peers
    falsos). El registro es del test, en memoria; el ``samples/bridge.jsonl`` de cada parte tiene que casar
    con el.
    """

    def __init__(self) -> None:
        self.rows_by_bridge: dict[int, list[dict[str, Any]]] = {}
        self.parts: list[dict[str, Any]] = []
        self._orig: dict[str, Any] = {}

    def __enter__(self) -> "_CoreTap":
        tap = self
        orig_emit = bridge_qa.QABridge._emit
        orig_open = f03_common.PartContext.open
        orig_spawn = f03_common.PartContext._spawn_peers
        self._orig = {"emit": orig_emit, "open": orig_open, "spawn": orig_spawn}

        def emit(bridge_self: Any, fields: dict[str, Any]) -> Any:
            before = len(bridge_self.events)
            result = orig_emit(bridge_self, fields)
            if len(bridge_self.events) > before:
                tap.rows_by_bridge.setdefault(id(bridge_self), []).append(copy.deepcopy(bridge_self.events[-1]))
            return result

        def open_(ctx: Any) -> Any:
            result = orig_open(ctx)
            tap.parts.append({
                "part_dir": Path(ctx.part_dir),
                "bridge_id": id(ctx.bridge),
                "pids": dict(getattr(ctx, "_tap_pids", {})),
            })
            return result

        def spawn(ctx: Any) -> Any:
            result = orig_spawn(ctx)
            ctx._tap_pids = {role: pid for role, pid in ctx.fake_peer_pids.items() if pid}
            return result

        bridge_qa.QABridge._emit = emit
        f03_common.PartContext._spawn_peers = spawn
        f03_common.PartContext.open = open_
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        bridge_qa.QABridge._emit = self._orig["emit"]
        f03_common.PartContext.open = self._orig["open"]
        f03_common.PartContext._spawn_peers = self._orig["spawn"]
        return False

    def problems(self, ev_dir: Path, expected_parts: list[str], *, require_roles: tuple[str, ...] = ("server", "client")) -> list[str]:
        """Compara el disco con lo que el nucleo registro. Lista vacia = el trafico es real."""
        found: list[str] = []
        by_dir = {rec["part_dir"].resolve(): rec for rec in self.parts}
        for pname in expected_parts:
            pdir = (Path(ev_dir) / pname).resolve()
            rec = by_dir.get(pdir)
            if rec is None:
                found.append(f"{pname}:no_part_context_opened")
                continue
            registered = self.rows_by_bridge.get(rec["bridge_id"], [])
            for role in require_roles:
                if not isinstance(rec["pids"].get(role), int) or rec["pids"][role] <= 0:
                    found.append(f"{pname}:no_fake_peer_pid:{role}")
            disk = _read_events(pdir)
            if not registered:
                found.append(f"{pname}:empty_core_registry")
                continue
            if disk != registered:
                found.append(f"{pname}:disk_rows_differ_from_core_registry")

            def proj(rows: list[dict[str, Any]]) -> list[Any]:
                out = []
                for r in rows:
                    if r.get("ev") == "result":
                        results = r.get("results") or ([r["result"]] if isinstance(r.get("result"), dict) else [])
                        for res in results:
                            out.append((r.get("op_id") or res.get("op_id"), r.get("inst"), json.dumps(res, sort_keys=True)))
                return out

            if proj(disk) != proj(registered):
                found.append(f"{pname}:op_id_inst_result_differ")
            hello_roles = {r.get("peer") for r in registered if r.get("ev") == "hello" and r.get("http") == 200}
            for role in require_roles:
                if role not in hello_roles:
                    found.append(f"{pname}:no_registered_hello:{role}")
            applied = [
                1
                for r in registered
                if r.get("ev") == "result"
                for res in (r.get("results") or ([r["result"]] if isinstance(r.get("result"), dict) else []))
                if res.get("verb") == "per_apply_scene" and res.get("status") == "done"
            ]
            if not applied:
                found.append(f"{pname}:no_real_per_apply_scene_done")
        return found


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
                ("mut-census_resource_bypass", "census_resource_bypass", "d4e5f60718293a4b"),
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
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-01"]["status"], "missing")
            self.assertEqual(_checks_by_id(verdict)["PER-01"]["detail"], "missing_apply_or_t1_pre_census")

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
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-06"]["status"], "missing")
            self.assertEqual(_checks_by_id(verdict)["PER-06"]["detail"], "identity_unverifiable")

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
            self.assertEqual(verdict["exit_code"], 2)
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
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-03"]["status"], "missing")
            self.assertEqual(_checks_by_id(verdict)["PER-03"]["detail"], "second_reset_observation_missing")

    def test_neg_post_restart_without_new_execution_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            builder.server_epoch_new = builder.server_epoch_old
            part_dir = builder.build_into(Path(tmp) / "same_epoch")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-09"]["status"], "fail")
            self.assertEqual(c_map["PER-09"]["detail"], "server_epoch_not_rotated")
            self.assertEqual(c_map["PER-06"]["status"], "missing")

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
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-07"]["status"], "missing")
            self.assertEqual(c_map["PER-07"]["detail"], "post_t3_mutating_old_ops")
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

        # BLOQ-2 (brief F0.3-0 :476): `.Remove(` solo se prohibe sobre los 4 arrays cuyo orden importa.
        for member in ("m_CacheOrder", "m_RpcLog", "m_PingLog", "m_EmitLog"):
            injected_remove = base_src + f"\nvoid BadRemove() {{ {member}.Remove(0); }}\n"
            self.assertEqual(
                s_persist_eval.scan_persist_enforcescript_sources({base_rel: injected_remove}),
                [f"{base_rel}:forbidden_unordered_remove:{member}.Remove("],
                msg=member,
            )
        # Un `map.Remove(k)` (un mapa, sin orden) NO es violacion.
        map_remove = base_src + "\nclass Reg { ref map<string, int> m_Records; void Drop(string k) { m_Records.Remove(k); } }\n"
        self.assertEqual(s_persist_eval.scan_persist_enforcescript_sources({base_rel: map_remove}), [])
        # Un literal "a.Remove(b)" (o de un miembro prohibido) dentro de una cadena tampoco cuenta.
        literal = base_src + '\nvoid Lit() { string s = "a.Remove(b)"; string u = "m_CacheOrder.Remove(0)"; }\n'
        self.assertEqual(s_persist_eval.scan_persist_enforcescript_sources({base_rel: literal}), [])
        # Los tokens de CE siguen prohibidos aunque ya no haya regla general de Remove.
        self.assertTrue(
            s_persist_eval.scan_persist_enforcescript_sources({base_rel: base_src + "\nvoid Bad() { GetCEApi(); }\n"})
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
        expected_parts = ["run"] + [f"mut-{m}" for m in s_persist_mutants.EXPECTED_MUTANTS]
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp) / "e2e_offline"
            with _CoreTap() as tap:
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
            # BLOQ-3: el trafico de cada parte es el que registro el nucleo (bridge de la parte y PID de los
            # peers falsos lanzados por PartContext), no lo que el runner dejo escrito en disco.
            self.assertEqual(tap.problems(ev_dir, expected_parts), [])
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
            # BLOQ-3: el efecto no son contadores. El resultado del apply lista las 6 entidades de la fixture,
            # con clase, net_id valido y distinto, vivas y colocadas (una extension de solo contadores no las tiene).
            _, _ap_n, ap_rows = _unpack(prep_by_id["op-prep-apply"]["read"])
            fix_clean = {e["logical_id"]: e for e in fixture["scenes"]["scene_a_clean"]["entities"]}
            self.assertEqual({r["logical_id"] for r in ap_rows}, set(fix_clean))
            self.assertEqual(len({r["net_id"] for r in ap_rows}), len(fix_clean))
            for r in ap_rows:
                self.assertEqual(r["class_name"], fix_clean[r["logical_id"]]["class_name"])
                self.assertTrue(s_persist_eval._valid_net_id(r["net_id"], r["logical_id"]), msg=str(r))
                self.assertEqual(r["ok_b"], 1.0)
                self.assertEqual(r["alive_b"], 1.0)
                self.assertGreater(r["max_hp"], 0.0)
            _, raw_n, _ = _unpack(prep_by_id["op-prep-raw"]["read"])
            raw_s, _, _ = _unpack(prep_by_id["op-prep-raw"]["read"])
            self.assertEqual(raw_s["spawn_status"], "ok")
            self.assertTrue(s_persist_eval._valid_net_id(raw_s["net_id"]))
            self.assertGreater(raw_n["max_hp"], 0.0)

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
            self.assertEqual(verified["exit_code"], 2)
            self.assertEqual(verified["verdict"], "INCONCLUSO")
            self.assertEqual(verified["reason"], "missing_part_files:run")

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
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-01"]["status"], "missing")

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
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "fail")
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "unprotected_census_resource_overlap")
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
            # MENOR 13: Select foreign items by their observed net_id, not class_name
            a_foreign_in_chest_nid = builder.entities_by_lid["a_foreign_in_chest"]["net_id"]
            a_foreign_in_child_kit_nid = builder.entities_by_lid["a_foreign_in_child_kit"]["net_id"]
            wrong_parent_nid = builder.entities_by_lid["b_chest_foreign"]["net_id"]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            for row in u_r:
                                if row.get("net_id") in (a_foreign_in_chest_nid, a_foreign_in_child_kit_nid):
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
            # MEN 11: Use contractual job_free and shift chronology coherently by 12s
            # Shift entire epoch chronology from first t5_post_restart_census to avoid false resource overlaps
            _shift_epoch_chronology_from_t5(events, builder.server_epoch_new, 12000.0)
            # Ensure contractual job_free responses for t5 jobs
            t5_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if u_s.get("area_tag", "").startswith("t5_post_restart_census:"):
                                t5_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_free":
                            u_s, _, _ = _unpack(res["read"])
                            if u_s.get("job") in t5_jobs:
                                # Contractual job_free response
                                u_s["freed"] = "1"
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers={}, rows=[])
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-08"]["status"], "missing")
            self.assertIn("post_restart_creature_coverage_missing", c_map["PER-08"]["detail"])
            # No other check should fail
            for cid, check in c_map.items():
                if cid not in ("PER-07", "PER-08"):
                    self.assertNotEqual(check["status"], "fail", msg=f"{cid} failed: {check['detail']}")

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
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "missing")
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "missing_witness_status")

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
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-01"]["status"], "missing")
            self.assertIn("invalid_census_resource", verdict["reasons"])

        # Subcase B: el recurso no protege (mutante census_resource_bypass): un segundo per_census_start se
        # acepta mientras el primero sigue vivo -> FALLA en PER-09 (la contencion real se prueba en
        # test_men6_census_resource_contention_in_run).
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder(
                "mut-census_resource_bypass", fault_code="census_resource_bypass"
            ).build_into(Path(tmp) / "overlapping_census")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"})
            self.assertIn("unprotected_census_resource_overlap", verdict["reasons"])

    # =========================================================================
    # test_sol2_* regression tests for Sol r2 findings (ENCARGO.md §3.2)
    # =========================================================================

    def test_sol2_01_fabricator_runner_rejected(self) -> None:
        """Sol r2 Nuevo 1: Fabricator runner generating synthetic traces without peers -> FALLA/INCONCLUSO."""
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "fabricator_runner")
            # Remove all bridge events except hello - simulates runner that only writes verdict
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            filtered = [ev for ev in events if ev.get("ev") == "hello"]
            bpath.write_text("\n".join(json.dumps(e) for e in filtered) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-01"]["status"], "missing")
            self.assertEqual(c_map["PER-01"]["detail"], "missing_apply_or_t1_pre_census")

    def test_sol2_02_counter_only_extension_rejected(self) -> None:
        """Sol r2 Nuevo 1: Extension maintaining only counters 6/1, no entities -> FALLA/INCONCLUSO."""
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / "counter_only_ext")
            # Simulate extension that only returns counters by removing per_apply_scene and per_spawn_raw results
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            filtered = []
            for ev in events:
                if ev.get("ev") == "result":
                    res_list = ev.get("results") or []
                    filtered_res = [r for r in res_list if r.get("verb") not in ("per_apply_scene", "per_spawn_raw", "per_reset_scene", "per_child_transition")]
                    if filtered_res:
                        ev = dict(ev)
                        ev["results"] = filtered_res
                        filtered.append(ev)
                else:
                    filtered.append(ev)
            bpath.write_text("\n".join(json.dumps(e) for e in filtered) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-01"]["status"], "missing")
            self.assertEqual(c_map["PER-01"]["detail"], "missing_apply_or_t1_pre_census")
            self.assertEqual(c_map["PER-03"]["status"], "fail")

    def test_sol2_03_n49_temporal_extremes_unaccredited_inconcluso(self) -> None:
        """Sol r2 Nuevo 2: sin acreditar los extremos temporales (parada y carga) -> PER-07/08 `missing`, sin `fail`.

        La parada se acredita con un per_status del epoch viejo posterior a t3_post_reset_census, y la carga con
        un per_status inicial del epoch nuevo (tick_ms del peer pequeno); aqui falta la de parada. El detalle
        exacto es `post_restart_creature_coverage_missing:N49_extremes_unaccredited` y ningun otro check se mueve.
        """
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "n49_no_stop_status")
            events = _read_events(part_dir)
            old_ids = _status_op_ids(events, builder.server_epoch_old)
            _write_events(part_dir, _drop_ops(events, {old_ids[-1]}))
            self._n49_expect_unaccredited(part_dir, "sol2_03")

    def test_sol2_04_ids_reused_across_epochs_passes(self) -> None:
        """Sol r2 Nuevo 4: IDs reused across epochs (honest variant) -> PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "ids_reused_epochs")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Reassign witness net_ids in new epoch to values used in old epoch
            old_nids: dict[str, str] = {}
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_apply_scene":
                            u = _unpack_any_payload(res["read"])
                            if u:
                                u_s, _, u_r = u
                                if u_s.get("scene_id") == "scene_b" and u_s.get("server_epoch") == builder.server_epoch_old:
                                    for row in u_r:
                                        lid = str(row.get("logical_id") or "")
                                        nid = str(row.get("net_id") or "")
                                        if lid and nid:
                                            old_nids[lid] = nid
            # Capture new epoch witness net_ids from the new epoch apply BEFORE reuse
            new_epoch_witness_nids: dict[str, str] = {}
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_apply_scene":
                            u = _unpack_any_payload(res["read"])
                            if u:
                                u_s, _, u_r = u
                                if u_s.get("scene_id") == "scene_b" and u_s.get("server_epoch") == builder.server_epoch_new:
                                    for row in u_r:
                                        lid = str(row.get("logical_id") or "")
                                        nid = str(row.get("net_id") or "")
                                        if lid and nid:
                                            new_epoch_witness_nids[lid] = nid
            # Build mapping from new epoch net_id -> reused (old epoch) net_id
            nid_reuse_map: dict[str, str] = {}
            for lid, new_nid in new_epoch_witness_nids.items():
                if lid in old_nids:
                    nid_reuse_map[new_nid] = old_nids[lid]
            # Apply old nids to witness apply in new epoch
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_apply_scene":
                            u = _unpack_any_payload(res["read"])
                            if u:
                                u_s, u_n, u_r = u
                                if u_s.get("scene_id") == "scene_b" and u_s.get("server_epoch") == builder.server_epoch_new:
                                    for row in u_r:
                                        lid = str(row.get("logical_id") or "")
                                        if lid in old_nids:
                                            row["net_id"] = old_nids[lid]
                                    orig_read = res["read"]
                                    ncol = orig_read.get("ncol", [])
                                    scol = orig_read.get("scol", [])
                                    res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, ncol=ncol, scol=scol, rows=u_r)
            # Also update census job_read results for t5_witness_pre_census and t5_witness_post_census
            # to use the same reused net_ids so the census matches the apply scene
            witness_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if u_s.get("area_tag") in (
                                "t5_witness_pre_census:area_b",
                                "t5_witness_post_census:area_b",
                            ):
                                witness_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in witness_jobs:
                                for row in u_r:
                                    lid = str(row.get("own_logical_id") or "")
                                    if lid in old_nids:
                                        row["net_id"] = old_nids[lid]
                                    # Update parent_net_id to match reused parent net_id
                                    pnid = str(row.get("parent_net_id") or "")
                                    if pnid and pnid in nid_reuse_map:
                                        row["parent_net_id"] = nid_reuse_map[pnid]
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict, indent=2))
            self.assertEqual(verdict["verdict"], "PASA")

    def test_sol2_05_creature_moves_after_q9_passes(self) -> None:
        """Sol r2 Nuevo 5: Creature displaced 1m after Q9 (honest variant) -> PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            # Use creature_far_move_m=1.0 with include_t5_track_disks=True
            part_dir = _SyntheticPartBuilder(
                "run", creature_far_move_m=1.0, include_t5_track_disks=True
            ).build_into(Path(tmp) / "creature_moves_after_q9")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict, indent=2))
            self.assertEqual(verdict["verdict"], "PASA")
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-08"]["status"], "pass")

    def test_sol2_06_include_director_b0_leaked_garment_not_pasa(self) -> None:
        """Sol r2 Nuevo 6: include_director_b=0 with leaked WorkingGloves_Yellow -> not PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "director_not_included")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Set include_director_b=0 in all t5_post_restart_census
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("area_tag", "").startswith("t5_post_restart_census:"):
                                u_n["include_director_b"] = 0.0
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
            bpath.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-09"]["status"], "fail")
            self.assertIn("t5_director_not_included", c_map["PER-09"]["detail"])

    def test_sol2_07_inv_children_n_false_counts_not_pasa(self) -> None:
        """Sol r2 Nuevo 7: inv_children_n=0 and 999 for retained container -> not PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "inv_children_false")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Set inv_children_n=0 for a_cont_1 in t3_pre and t3_post
            # First, collect job_ids for t3_pre_reset_census and t3_post_reset_census for retained area
            t3_reset_jobs: set[str] = set()
            retained_area = "area_a_mut" if builder.part_name == "mut-foreign_wiped" else "area_a"
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            atag = u_s.get("area_tag", "")
                            # Extract area_id from area_tag (format: "stage:area_id")
                            census_area_id = atag.split(":", 1)[1] if ":" in atag else ""
                            if ("t3_pre_reset_census" in atag or "t3_post_reset_census" in atag) and census_area_id == retained_area:
                                t3_reset_jobs.add(u_s["job"])
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t3_reset_jobs:
                                for row in u_r:
                                    if row.get("own_logical_id") in ("a_cont_1", "am_cont_1"):
                                        row["inv_children_n"] = 0.0
                                res["read"] = builder._pack_ext_read(
                                    strings=u_s,
                                    numbers=u_n,
                                    ncol=res["read"]["ncol"],
                                    scol=res["read"]["scol"],
                                    rows=u_r,
                                )
            # Also test with 999
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t3_reset_jobs:
                                for row in u_r:
                                    if row.get("own_logical_id") in ("a_cont_1", "am_cont_1"):
                                        row["inv_children_n"] = 999.0
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
            self.assertEqual(c_map["PER-04"]["status"], "fail")
            self.assertIn("inv_children_n_mismatch", c_map["PER-04"]["detail"])

    def test_sol2_08_apples_in_t2_not_pasa(self) -> None:
        """Sol r2 Nuevo 8: Apple class substituted for creatures in t2 -> not PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "apples_in_t2")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Change class_name to Apple for b_inf_1 and b_ani_1 in t2_census_10min
            t2_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if "t2_census_10min" in u_s.get("area_tag", ""):
                                t2_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in t2_jobs:
                                for row in u_r:
                                    if row.get("own_logical_id") in ("b_inf_1", "b_ani_1"):
                                        row["class_name"] = "Apple"
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
            self.assertEqual(c_map["PER-02"]["status"], "fail")
            self.assertIn("t2_class_mismatch", c_map["PER-02"]["detail"])

    def test_sol2_09_dead_witness_after_old_orders_not_pasa(self) -> None:
        """Sol r2 Nuevo 9: Dead witness (alive_b=health_hp=ai_agent_b=0) in post census -> not PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "dead_witness")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Set alive_b=health_hp=ai_agent_b=0 for all own entities in t5_witness_post_census
            wit_post_jobs: set[str] = set()
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u_s, _, _ = _unpack(res["read"])
                            if "t5_witness_post_census" in u_s.get("area_tag", ""):
                                wit_post_jobs.add(u_s["job"])
                        elif res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            if u_s.get("job") in wit_post_jobs:
                                for row in u_r:
                                    if int(round(float(row.get("own_b", 0.0)))) == 1:
                                        row["alive_b"] = 0.0
                                        row["health_hp"] = 0.0
                                        row["ai_agent_b"] = 0.0
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
            self.assertEqual(c_map["PER-09"]["status"], "fail")
            self.assertIn("witness_post_census_alive_mismatch", c_map["PER-09"]["detail"])

    def _cleanup_10_of_11(self, part_dir: Path, builder: "_SyntheticPartBuilder", *, census_consistent: bool) -> None:
        events = _read_events(part_dir)
        for ev in events:
            if ev.get("ev") == "result":
                for res in ev.get("results") or []:
                    if res.get("verb") == "per_cleanup_qa":
                        u_s, u_n, u_r = _unpack(res["read"])
                        u_n["cleaned_own_n"] = 10.0
                        res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
        t6_b_jobs: set[str] = set()
        b_prop_1_nid = builder.entities_by_lid["b_prop_1"]["net_id"]
        survivor = {
            "class_name": "Barrel_Red",
            "loc_kind": "ground",
            "parent_class": "",
            "parent_net_id": "",
            "slot_name": "",
            "owner_uid": "",
            "own_logical_id": "b_prop_1",
            "net_id": b_prop_1_nid,
            "pers_id": "0:0:0:0",
            "own_b": 1.0,
            "in_radius_b": 1.0,
            "alive_b": 1.0,
            "ai_agent_b": 0.0,
            "pos_x_m": 4682.0,
            "pos_y_m": _surface_y(4682.0, 10202.0),
            "pos_z_m": 10202.0,
            "yaw_deg": 0.0,
            "pitch_deg": 0.0,
            "roll_deg": 0.0,
            "max_hp": 100.0,
            "health_hp": 100.0,
            "inv_children_n": 0.0,
            "spawn_tick_ms": 1500.0,
        }
        for ev in events:
            if ev.get("ev") == "result":
                for res in ev.get("results") or []:
                    if res.get("verb") == "per_census_start":
                        u_s, u_n, u_r = _unpack(res["read"])
                        if u_s.get("area_tag") == "t6_post_cleanup_census:area_b":
                            t6_b_jobs.add(u_s["job"])
                            if census_consistent:
                                u_n["rows_captured_n"] = 1.0
                                res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
                    elif res.get("verb") == "job_read":
                        u_s, u_n, u_r = _unpack(res["read"])
                        if u_s.get("job") in t6_b_jobs:
                            u_n["pages_n"] = 1.0
                            u_n["rows_total_n"] = 1.0
                            u_r.append(dict(survivor))
                            res["read"] = builder._pack_ext_read(
                                strings=u_s,
                                numbers=u_n,
                                ncol=res["read"]["ncol"],
                                scol=res["read"]["scol"],
                                rows=u_r,
                            )
        _write_events(part_dir, events)

    def test_sol2_10_cleanup_10_of_11_not_pasa(self) -> None:
        """Sol r2 Nuevo 10: limpieza de 10 de 11 con b_prop_1 vivo en t6.

        Censo t6 completo con el superviviente QA -> FALLA/PER-09 (`t6_cleanup_survivors`). Censo t6 de area_b
        incompleto (no acredita la limpieza) -> INCONCLUSO/PER-09 (`t6_cleanup_census_absent`).
        """
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "cleanup_10_of_11_survivor")
            self._cleanup_10_of_11(part_dir, builder, census_consistent=True)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-09"]["status"], "fail")
            self.assertIn("t6_cleanup_survivors", c_map["PER-09"]["detail"])
            self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"})
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "cleanup_10_of_11_census_absent")
            self._cleanup_10_of_11(part_dir, builder, census_consistent=False)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "missing")
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "t6_cleanup_census_absent:area_b")

    def test_sol2_11_neg_bloq07_contractual_job_free_shifted_chronology(self) -> None:
        """Sol r2 MEN 11: sin la lectura inicial del epoch nuevo y con la cronologia desplazada 12 s con coherencia
        (los job_free contractuales no cambian), solo falla N49: PER-07/08 `missing` y el resto `pass`."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "bloq07_job_free")
            events = _read_events(part_dir)
            new_ids = _status_op_ids(events, builder.server_epoch_new)
            events = _drop_ops(events, {new_ids[0]})
            # Shift entire epoch chronology from first t5_post_restart_census to avoid false resource overlaps
            _shift_epoch_chronology_from_t5(events, builder.server_epoch_new, 12000.0)
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "sol2_11")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            c_map = _checks_by_id(verdict)
            for cid in ("PER-01", "PER-02", "PER-03", "PER-04", "PER-05", "PER-06", "PER-09", "PER-10"):
                self.assertEqual(c_map[cid]["status"], "pass", msg=f"{cid}: {c_map[cid]['detail']}")

    def test_e2e_12_e2e_orders_complete_valid_lease_then_block(self) -> None:
        """Sol r2 MEN 12: E2E orders complete/valid - effect with valid lease, then block on expiry. Requires implementation."""
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

            # 1) While lease is valid, orders have complete args and produce effects
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
            results: list[dict[str, Any]] = []

            # Valid per_apply_scene with all required args
            apply_op = _make_valid_op(
                "op-apply-valid",
                "per_apply_scene",
                wire.pack_payload(
                    scalars_str={
                        "scene_id": "scene_a_clean",
                        "scene_op_id": "scop-1",
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
            peer._start_op(apply_op, now_box[0], time.monotonic(), results)
            apply_res = next(r for r in results if r["op_id"] == "op-apply-valid")
            self.assertEqual(apply_res["status"], "done")

            # 2) Advance clock past lease expiry
            now_box[0] = 7500.0
            self.assertFalse(peer.lease_valid())

            # 3) Orders after expiry are rejected with lease_expired
            expired_op = _make_valid_op(
                "op-expired",
                "per_apply_scene",
                wire.pack_payload(
                    scalars_str={
                        "scene_id": "scene_a_clean",
                        "scene_op_id": "scop-2",
                        "expect_epoch": peer.inst,
                        "q9_pathway": "a",
                    },
                    scalars_num={"gen_n": 2.0},
                    num_cols=in_ncol,
                    str_cols=in_scol,
                    row_dicts=clean_in_rows,
                ),
                now_box[0],
            )
            peer._start_op(expired_op, now_box[0], time.monotonic(), results)
            expired_res = next(r for r in results if r["op_id"] == "op-expired")
            self.assertEqual(expired_res["status"], "error")
            self.assertEqual(expired_res["reason"], "lease_expired")

            # 4) per_cleanup_qa still works with expired lease
            clean_op = _make_valid_op(
                "op-clean-valid",
                "per_cleanup_qa",
                wire.pack_payload(scalars_str={"cleanup_tag": "t6"}),
                now_box[0],
            )
            peer._start_op(clean_op, now_box[0], time.monotonic(), results)
            clean_res = next(r for r in results if r["op_id"] == "op-clean-valid")
            self.assertEqual(clean_res["status"], "done")
        finally:
            os.unlink(config_path)

    def test_sol2_13_neg_bloq06_select_foreign_by_observed_id(self) -> None:
        """Sol r2 MENOR 13: test_neg_bloq06 selects foreign items by observed net_id, not class_name."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "foreign_by_observed_id")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            # Get the observed net_ids for the two foreign items
            a_foreign_in_chest_nid = builder.entities_by_lid["a_foreign_in_chest"]["net_id"]
            a_foreign_in_child_kit_nid = builder.entities_by_lid["a_foreign_in_child_kit"]["net_id"]
            wrong_parent_nid = builder.entities_by_lid["b_chest_foreign"]["net_id"]

            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "job_read":
                            u_s, u_n, u_r = _unpack(res["read"])
                            for row in u_r:
                                # Select by observed net_id, not class_name
                                if row.get("net_id") in (a_foreign_in_chest_nid, a_foreign_in_child_kit_nid):
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

    # =========================================================================
    # Ronda 3 (oraculo reabierto): BLOQ-1..3 y MEN-4..8
    # =========================================================================

    def test_tap_registers_real_peer_traffic_and_detects_rewritten_bridge(self) -> None:
        """BLOQ-3 (el propio registro): un PartContext real con peers falsos queda registrado y el disco casa."""
        import argparse

        args = argparse.Namespace(
            build="offline",
            both=True,
            ttl_ms=gate_core.DEFAULT_TTL_MS,
            retry_ms=gate_core.DEFAULT_RETRY_MS,
            lease_ms=gate_core.DEFAULT_LEASE_MS,
            hold_ms=gate_core.DEFAULT_HOLD_MS,
            seed=gate_core.DEFAULT_SEED,
            peer_timeout=None,
            pbo=None,
            fault=None,
        )
        with tempfile.TemporaryDirectory() as tmp, _CoreTap() as tap:
            base = Path(tmp)
            with f03_common.PartContext(
                base_dir=base, part_name="run", spike_id="S-persist", args=args, argv=[]
            ) as ctx:
                self.assertIsNone(ctx.startup_reason)
                out = f03_common.issue_one(
                    ctx, "server", "qa_echo", wire.pack_payload(scalars_str={"k": "v"})
                )
                self.assertEqual(out.status, "done")
            # Trafico real: hellos de ambos peers, PID de ambos y disco == registro. Aqui no se aplico ninguna
            # escena, y es lo unico que falta.
            self.assertEqual(tap.problems(base, ["run"]), ["run:no_real_per_apply_scene_done"])
            # Un runner que reescribe bridge.jsonl despues de cerrar el contexto queda al descubierto.
            events = _read_events(base / "run")
            events.append({"ev": "result", "peer": "server", "inst": "x", "results": [{"op_id": "forged", "verb": "per_apply_scene", "status": "done", "read": {}}]})
            _write_events(base / "run", events)
            self.assertIn("run:disk_rows_differ_from_core_registry", tap.problems(base, ["run"]))

    def test_neg_bloq3_fabricator_runner_without_peers_detected_by_empty_core_registry(self) -> None:
        """BLOQ-3: runner que escribe en cada parte la evidencia sintetica sana, sin peers.

        Pasa el oraculo (que es ciego a la procedencia) y por eso el e2e exige ademas el registro del nucleo:
        el registro esta vacio y se detecta por ahi.
        """
        import types

        specs = (
            ("run", "", "a1b2c3d4e5f60718"),
            ("mut-unprotected_leak", "omit_nopersistency_flag", "b2c3d4e5f6071829"),
            ("mut-foreign_wiped", "reset_wipe_radius_25m", "c3d4e5f60718293a"),
            ("mut-census_resource_bypass", "census_resource_bypass", "d4e5f60718293a4b"),
        )
        expected_parts = [s[0] for s in specs]
        self.assertEqual(expected_parts, ["run"] + [f"mut-{m}" for m in s_persist_mutants.EXPECTED_MUTANTS])

        def fabricator_run(args: Any, evidence: Any, argv: Any) -> int:
            ev = Path(evidence)
            for pname, fcode, nonce in specs:
                pdir = _SyntheticPartBuilder(pname, nonce=nonce, fault_code=fcode).build_into(ev / pname)
                gate_core.write_json(pdir / "verdict.json", s_persist_eval.evaluate(pdir, repo_root=REPO_ROOT))
            agg = f03_common.aggregate_spike(
                ev,
                "S-persist",
                repo_root=REPO_ROOT,
                expected_mutants=s_persist_mutants.EXPECTED_MUTANTS,
                expected_harness_tests=s_persist_mutants.EXPECTED_HARNESS_TESTS,
            )
            started = gate_core.utc_now()
            gate_core.write_json(
                ev / "manifest.json",
                gate_core.make_manifest("spike", "S-persist", args, argv, started, gate_core.utc_now()),
            )
            gate_core.write_json(ev / "verdict.json", agg)
            return int(agg["exit_code"])

        fake_mod = types.ModuleType("s_persist_run")
        fake_mod.run = fabricator_run  # type: ignore[attr-defined]
        saved = sys.modules.get("s_persist_run")
        sys.modules["s_persist_run"] = fake_mod
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ev_dir = Path(tmp) / "fabricated"
                with _CoreTap() as tap:
                    rc = m1_gate.main(["spike", "S-persist", "--both", "--build", "offline", "--evidence", str(ev_dir)])
                # La evidencia fabricada pasa el oraculo: eso solo no acredita la procedencia...
                self.assertEqual(rc, 0)
                # ...pero el nucleo no abrio ninguna parte, ni lanzo peers, ni registro trafico.
                self.assertEqual(
                    sorted(tap.problems(ev_dir, expected_parts)),
                    sorted(f"{p}:no_part_context_opened" for p in expected_parts),
                )
        finally:
            if saved is None:
                sys.modules.pop("s_persist_run", None)
            else:
                sys.modules["s_persist_run"] = saved

    def _displace_a_prop_1(self, part_dir: Path, builder: "_SyntheticPartBuilder", dx: float, *, also_args: bool) -> None:
        fix = json.loads((QA_DIR / "fixtures" / "s_persist_fixture.json").read_text(encoding="utf-8"))
        ent = next(e for e in fix["scenes"]["scene_a"]["entities"] if e["logical_id"] == "a_prop_1")
        rx, rz = float(ent["req_x_m"]), float(ent["req_z_m"])
        nid = builder.entities_by_lid["a_prop_1"]["net_id"]
        scen = _read_scenario(part_dir)
        for e in scen:
            if e.get("ev") == "ledger_entry" and e.get("logical_id") == "a_prop_1":
                e["req_x_m"] = float(e["req_x_m"]) + dx
        _write_scenario(part_dir, scen)
        events = _read_events(part_dir)

        def walk(o: Any) -> None:
            if isinstance(o, dict):
                a = o.get("args")
                if (
                    o.get("verb") == "ground_query"
                    and isinstance(a, dict)
                    and abs(float(a.get("x", 0.0)) - rx) < 1e-6
                    and abs(float(a.get("z", 0.0)) - rz) < 1e-6
                ):
                    a["x"] = rx + dx
                    a["pos"][0] = rx + dx
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(events)
        for ev in events:
            if also_args and ev.get("ev") in ("enq", "poll"):
                ops = [ev] if ev.get("ev") == "enq" else list(ev.get("ops") or [])
                for op in ops:
                    if op.get("verb") == "per_apply_scene":
                        u_s, u_n, u_r = _unpack(op["args"])
                        hit = False
                        for row in u_r:
                            if row.get("logical_id") == "a_prop_1":
                                row["req_x_m"] = float(row["req_x_m"]) + dx
                                hit = True
                        if hit:
                            op["args"] = _repack_read(u_s, u_n, u_r, op["args"])
            if ev.get("ev") == "result":
                for res in ev.get("results") or []:
                    if res.get("verb") == "per_apply_scene" and res.get("status") == "done":
                        u_s, u_n, u_r = _unpack(res["read"])
                        hit = False
                        for row in u_r:
                            if row.get("logical_id") == "a_prop_1":
                                row["q9_x_m"] = float(row["q9_x_m"]) + dx
                                hit = True
                        if hit:
                            res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
                    elif res.get("verb") == "job_read" and res.get("status") == "done":
                        u_s, u_n, u_r = _unpack(res["read"])
                        hit = False
                        for row in u_r:
                            if row.get("net_id") == nid:
                                row["pos_x_m"] = float(row["pos_x_m"]) + dx
                                hit = True
                        if hit:
                            res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
        _write_events(part_dir, events)

    def test_bloq1_prop_displaced_30m_coherently_in_ledger_not_pasa(self) -> None:
        """BLOQ-1: a_prop_1 desplazado 30 m de forma coherente en ledger, ground_query, q9 y censo -> FALLA/PER-01.

        La posicion esperada sale de la fixture congelada; el ledger del runner solo se contrasta con ella.
        """
        for also_args in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / "displaced")
                self._displace_a_prop_1(part_dir, builder, 30.0, also_args=also_args)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 1, msg=json.dumps(verdict["checks"]))
                c_map = _checks_by_id(verdict)
                self.assertEqual(c_map["PER-01"]["status"], "fail", msg=str(also_args))
                self.assertIn("a_prop_1:ledger_req_x_m_differs_from_fixture", c_map["PER-01"]["detail"])
                self.assertEqual(_only_non_pass(verdict), {"PER-01": "fail"}, msg=str(also_args))

    def test_men5_offline_without_storage_events_and_short_hold_passes_diag_does_not(self) -> None:
        """MEN-5: en offline no se exigen storage_* ni los 600 s de PER-02; en diag/retail si."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run", t2_hold_ms=100000.0)
            part_dir = builder.build_into(Path(tmp) / "offline_light")
            scen = [e for e in _read_scenario(part_dir) if not str(e.get("ev", "")).startswith("storage_")]
            _write_scenario(part_dir, scen)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
            self.assertEqual(_only_non_pass(verdict), {})
        for build in ("diag", "retail"):
            # diag/retail sin los eventos de storage: PER-10 missing (y solo ese)
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / f"{build}_nostorage")
                _convert_part_to_build(part_dir, build)
                _write_scenario(part_dir, [e for e in _read_scenario(part_dir) if not str(e.get("ev", "")).startswith("storage_")])
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 2)
                self.assertEqual(_only_non_pass(verdict), {"PER-10": "missing"})
                self.assertEqual(_checks_by_id(verdict)["PER-10"]["detail"], "storage_restore_incomplete")
            # diag/retail con el nacimiento a 100 s del censo t2: PER-02 missing hold_under_600s
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run", t2_hold_ms=100000.0)
                part_dir = builder.build_into(Path(tmp) / f"{build}_shorthold")
                _convert_part_to_build(part_dir, build)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 2)
                self.assertEqual(_only_non_pass(verdict), {"PER-02": "missing"})
                self.assertIn("hold_under_600s", _checks_by_id(verdict)["PER-02"]["detail"])
            # diag/retail completo: PASA
            with tempfile.TemporaryDirectory() as tmp:
                part_dir = _SyntheticPartBuilder("run").build_into(Path(tmp) / f"{build}_full")
                _convert_part_to_build(part_dir, build)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))

    def _n49_expect_unaccredited(self, part_dir: Path, tag: str) -> None:
        verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
        self.assertEqual(verdict["exit_code"], 2, msg=tag)
        c_map = _checks_by_id(verdict)
        for cid in ("PER-07", "PER-08"):
            self.assertEqual(c_map[cid]["status"], "missing", msg=f"{tag}:{cid}")
            self.assertEqual(
                c_map[cid]["detail"],
                "post_restart_creature_coverage_missing:N49_extremes_unaccredited",
                msg=f"{tag}:{cid}",
            )
        self.assertEqual(_only_non_pass(verdict), {"PER-07": "missing", "PER-08": "missing"}, msg=tag)

    def test_men4_stop_extreme_needs_peer_status_after_t3_not_a_marker(self) -> None:
        """MEN-4: sin per_status del epoch viejo posterior a t3_post, N49 no se acredita; un marcador no lo arregla."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "no_stop_status")
            events = _read_events(part_dir)
            old_ids = _status_op_ids(events, builder.server_epoch_old)
            events = _drop_ops(events, {old_ids[-1]})
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "stop_status_dropped")
            # Marcadores del runner (ya no existen en el contrato): ni siquiera se miran.
            for ev in events:
                if ev.get("ev") == "result" and ev.get("inst") == builder.server_epoch_old:
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_status":
                            u_s, u_n, u_r = _unpack(res["read"])
                            u_s["shutdown_marker"] = "1"
                            res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "stop_status_dropped_with_marker")

    def test_men4_start_extreme_needs_small_first_peer_tick_after_hello(self) -> None:
        """MEN-4: la primera orden del epoch nuevo tiene que ser un per_status con tick_ms pequeno del peer."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "no_start_status")
            events = _read_events(part_dir)
            new_ids = _status_op_ids(events, builder.server_epoch_new)
            _write_events(part_dir, _drop_ops(events, {new_ids[0]}))
            self._n49_expect_unaccredited(part_dir, "start_status_dropped")
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "start_tick_huge")
            events = _read_events(part_dir)
            first_new = _status_op_ids(events, builder.server_epoch_new)[0]
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("op_id") == first_new:
                            u_s, u_n, u_r = _unpack(res["read"])
                            u_n["tick_ms"] = 900000.0
                            res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "start_tick_huge")

    def test_men4_silent_gap_before_restart_or_after_load_not_pasa_short_gap_passes(self) -> None:
        """MEN-4 / Sol r2 Nuevo 2: el hueco silencioso de 60 s (peer vivo sin lecturas) -> INCONCLUSO; 2 s -> PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "short_gap")
            events = _read_events(part_dir)
            final_old = _status_op_ids(events, builder.server_epoch_old)[-1]
            t_final = _result_t_ms(events, final_old)
            events.append({"ev": "keepalive", "peer": "server", "inst": builder.server_epoch_old, "http": 200, "t_ms": t_final + 2000.0})
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
        # 60 s en los que el peer viejo sigue vivo (keepalive) despues de su ultima lectura
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "gap_before_restart")
            events = _read_events(part_dir)
            final_old = _status_op_ids(events, builder.server_epoch_old)[-1]
            t_final = _result_t_ms(events, final_old)
            events.append({"ev": "keepalive", "peer": "server", "inst": builder.server_epoch_old, "http": 200, "t_ms": t_final + 60000.0})
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            for cid in ("PER-07", "PER-08"):
                self.assertEqual(c_map[cid]["status"], "missing", msg=cid)
                self.assertEqual(c_map[cid]["detail"], "post_restart_creature_coverage_missing", msg=cid)
            self.assertEqual(_only_non_pass(verdict), {"PER-07": "missing", "PER-08": "missing"})
        # 60 s entre el hello del epoch nuevo y su primera lectura (el mundo ya corria)
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "gap_after_load")
            events = _read_events(part_dir)
            for ev in events:
                if ev.get("ev") == "hello" and ev.get("inst") == builder.server_epoch_new:
                    ev["t_ms"] = float(ev["t_ms"]) - 60000.0
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            for cid in ("PER-07", "PER-08"):
                self.assertEqual(c_map[cid]["status"], "missing", msg=cid)
                self.assertEqual(c_map[cid]["detail"], "post_restart_creature_coverage_missing", msg=cid)
            self.assertEqual(_only_non_pass(verdict), {"PER-07": "missing", "PER-08": "missing"})

    def test_men_post_t3_pure_reads_are_not_mutating_but_writes_are(self) -> None:
        """MENOR: una lectura pura del epoch viejo tras t3 no cuenta como mutadora; una escritura si."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "pure_read")
            events = _read_events(part_dir)
            final_old = _status_op_ids(events, builder.server_epoch_old)[-1]
            t_final = _result_t_ms(events, final_old)
            gq_args = builder._pack_ext_args()
            gq_args.update({"x": 4502.0, "z": 10202.0})
            _append_old_epoch_op(builder, events, "ground_query", gq_args, {"has": ["y"], "y": 100.0}, op_id="late-gq-1", t_ms=t_final + 100.0, peer_tick_ms=_result_done_ms(events, final_old) + 100.0)
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "late_write")
            events = _read_events(part_dir)
            final_old = _status_op_ids(events, builder.server_epoch_old)[-1]
            t_final = _result_t_ms(events, final_old)
            _append_old_epoch_op(
                builder, events, "per_cleanup_qa", builder._pack_ext_args(strings={"cleanup_tag": "late"}),
                builder._pack_ext_read(numbers={"cleaned_own_n": 0.0, "cleaned_raw_n": 0.0, "tick_ms": 9.0e5, "frame": 1.0}),
                op_id="late-clean-1", t_ms=t_final + 100.0, peer_tick_ms=_result_done_ms(events, final_old) + 100.0,
            )
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            c_map = _checks_by_id(verdict)
            for cid in ("PER-07", "PER-08"):
                self.assertEqual(c_map[cid]["status"], "missing", msg=cid)
                self.assertEqual(c_map[cid]["detail"], "post_t3_mutating_old_ops", msg=cid)

    def _census_start_results(self, events: list[dict[str, Any]], tag: str) -> list[dict[str, Any]]:
        out = []
        for ev in events:
            if ev.get("ev") == "result":
                for res in ev.get("results") or []:
                    if res.get("verb") == "per_census_start" and res.get("status") in ("done", "rejected"):
                        u_s, _, _ = _unpack(res["read"])
                        if u_s.get("area_tag") == tag:
                            out.append(res)
        return out

    def test_men6_census_resource_contention_in_run(self) -> None:
        """MEN-6: segundo censo concurrente -> rejected/busy; primero integro; tercero aceptado tras liberar."""
        # (a) la corrida honesta lleva la prueba y pasa
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "honest")
            events = _read_events(part_dir)
            rejected = [
                res
                for ev in events
                if ev.get("ev") == "result"
                for res in ev.get("results") or []
                if res.get("verb") == "per_census_start" and res.get("status") == "rejected"
            ]
            self.assertEqual([(r["status"], r["reason"]) for r in rejected], [("rejected", "busy")])
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
        # (b) mutante census_resource_bypass: el segundo se acepta mientras el primero esta vivo
        with tempfile.TemporaryDirectory() as tmp:
            part_dir = _SyntheticPartBuilder("mut-census_resource_bypass", fault_code="census_resource_bypass").build_into(Path(tmp) / "bypass")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"})
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "unprotected_census_resource_overlap")
        # (c) sin la prueba de contencion: PER-09 missing
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "no_probe")
            events = _read_events(part_dir)
            rej_ids = {
                res["op_id"]
                for ev in events
                if ev.get("ev") == "result"
                for res in ev.get("results") or []
                if res.get("verb") == "per_census_start" and res.get("status") == "rejected"
            }
            _write_events(part_dir, _drop_ops(events, rej_ids))
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_only_non_pass(verdict), {"PER-09": "missing"})
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "census_busy_contention_unobserved")
        # (d) rechazo con otro motivo (no es contencion): FALLA
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "wrong_reason")
            events = _read_events(part_dir)
            for ev in events:
                if ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start" and res.get("status") == "rejected":
                            res["reason"] = "too_many_jobs"
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"})
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "census_contention_wrong_reason")
        # (e) el primer censo no queda integro tras el busy
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "first_not_intact")
            events = _read_events(part_dir)
            a_start = self._census_start_results(events, "t0_baseline_census:area_a")[0]
            u_s, u_n, u_r = _unpack(a_start["read"])
            u_n["rows_captured_n"] = float(u_n["rows_captured_n"]) + 3.0
            a_start["read"] = _repack_read(u_s, u_n, u_r, a_start["read"])
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "missing")
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "census_first_job_not_intact_after_busy")
        # (f) tras liberar, el siguiente censo se rechaza: no se acepta el tercero
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "third_rejected")
            events = _read_events(part_dir)
            b_start = self._census_start_results(events, "t0_baseline_census:area_b")[0]
            b_start["status"] = "rejected"
            b_start["reason"] = "busy"
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2)
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "missing")
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "census_not_accepted_after_release")

    def test_men8_t0_director_inventory_comes_from_t0_census_not_runner_fallback(self) -> None:
        """MEN-8: t0 de area_a exige include_director_b == 1 y director_inv_readable_b == 1; sin respaldo del runner."""
        for variant in ("include_zero", "unreadable"):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / variant)
                events = _read_events(part_dir)
                a_start = self._census_start_results(events, "t0_baseline_census:area_a")[0]
                if variant == "include_zero":
                    # tambien en los args del enq/poll (de donde sale include_director_b)
                    for ev in events:
                        ops = [ev] if ev.get("ev") == "enq" else (list(ev.get("ops") or []) if ev.get("ev") == "poll" else [])
                        for op in ops:
                            if op.get("op_id") == a_start["op_id"]:
                                u_s, u_n, u_r = _unpack(op["args"])
                                u_n["include_director_b"] = 0.0
                                op["args"] = _repack_read(u_s, u_n, u_r, op["args"])
                else:
                    u_s, u_n, u_r = _unpack(a_start["read"])
                    u_n["director_inv_readable_b"] = 0.0
                    a_start["read"] = _repack_read(u_s, u_n, u_r, a_start["read"])
                _write_events(part_dir, events)
                # el runner SI declara el director basal en scenario.jsonl: ya no se le hace caso
                self.assertTrue(any(e.get("ev") == "baseline_director_foreign" for e in _read_scenario(part_dir)))
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 2, msg=variant)
                self.assertIn("t0_director_inventory_not_censused", verdict["reasons"], msg=variant)


if __name__ == "__main__":
    unittest.main()
