"""Offline unit and anti-fabrication tests for the S-persist oracle (s_persist_eval)."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from collections.abc import Iterable
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
from tests import e2e_witness


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
        restart_gap_ms: float = 800.0,
        new_epoch_tick0_ms: float = 200.0,
        old_keepalive_after_stop: bool = True,
        t5_radius_m: float = 60.0,
        baseline_sentinel_glove: bool = False,
        purge_returning: tuple[str, ...] | None = None,
        purge_hook: Any = None,
        t0_players_n: tuple[int, ...] = (1,),
    ) -> None:
        # O2 (brief, secciones finales): un guante basal de clase centinela en el director desde t0 (arbitraje 6), las
        # prendas QA que vuelven con el personaje tras el reinicio (por defecto los dos guantes), un gancho que puede
        # cambiar el plan de la purga antes de emitirla y la secuencia de `players_n` de los `per_status` de t0.
        self.baseline_sentinel_glove = baseline_sentinel_glove
        self.purge_returning = purge_returning
        self.purge_hook = purge_hook
        self.t0_players_n = t0_players_n
        self.purge_plan: dict[str, Any] = {}
        self.t2_hold_ms = t2_hold_ms
        # N49: hueco del bridge entre el keepalive viejo y el hello nuevo, tick_ms del peer nuevo en su hello
        # (tiempo desde el arranque del proceso) y keepalive del peer viejo tras su ultima lectura.
        self.restart_gap_ms = restart_gap_ms
        self.new_epoch_tick0_ms = new_epoch_tick0_ms
        self.old_keepalive_after_stop = old_keepalive_after_stop
        # radio de los discos del censo t5 (Sol delta r2 MEN: el alcance de la cobertura N49 depende de el)
        self.t5_radius_m = t5_radius_m
        # discos de seguimiento t5 emitidos (etiqueta, x, z): cada uno lleva su censo de limpieza en t6, como el runner
        self.t5_track_discs: list[tuple[str, float, float]] = []
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
        self.next_pers_k = 0

        self.bridge_events: list[dict[str, Any]] = []
        self.scenario_events: list[dict[str, Any]] = []
        self.entities_by_lid: dict[str, dict[str, Any]] = {}

    def _next_op_id(self) -> str:
        self.op_seq += 1
        return f"{self.nonce}-{self.op_seq}"

    def _alloc_net_id(self) -> str:
        self.next_net_low += 1
        return f"1:{self.next_net_low}"

    def _alloc_pers_id(self) -> str:
        # Oraculo v2: como en DayZDiag, GetPersistentID da 4 enteros con signo, unicos y distintos de cero
        # desde la creacion (tambien con ECE_NOPERSISTENCY_WORLD).
        self.next_pers_k += 1
        k = self.next_pers_k
        return f"{1594376013 - 7919 * k}:{-1137025392 + 104729 * k}:{470150303 + 130363 * k}:{-806843468 - 154763 * k}"

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
        enq_inst: str | None = None,
    ) -> str:
        oid = op_id or self._next_op_id()
        recv_ms = self.tick_ms
        frame_recv = self.frame
        t_recv = self.h_ms
        self._advance(20.0, 1)
        done_ms = self.tick_ms
        frame_done = self.frame
        t_done = self.h_ms

        enq_ev: dict[str, Any] = {
            "ev": "enq",
            "peer": peer,
            "op_id": oid,
            "verb": verb,
            "args": args,
            "h_ms": recv_ms,
            "t_ms": t_recv,
        }
        if enq_inst is not None:
            # como el puente real (bridge_qa.enqueue): el `enq` lleva el `inst` destino (`target_inst`)
            enq_ev["inst"] = enq_inst
        self.bridge_events.append(enq_ev)
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
        radius_m = self.t5_radius_m if stage == "t5_post_restart_census" or area_id.startswith("t5_track_") else 60.0
        census_strings = {"area_tag": area_tag}
        if include_director_b == 1:
            # brief, ronda 2 (`:533`): el censo con el director lleva su uid explicito
            census_strings["director_uid"] = self.director_uid
        in_args = self._pack_ext_args(
            strings=census_strings,
            numbers={
                "center_x_m": center_x,
                "center_z_m": center_z,
                "radius_m": radius_m,
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
                "radius_m": radius_m,
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

    # Columnas de las filas del trabajo `per_purge_start` (brief, ronda 2 `:568` y arbitraje 4: `net_id` y
    # `parent_net_id` del epoch nuevo; aclaracion, punto 2: `confirm_tick_ms` al final de `ncol`).
    PURGE_SCOL = ["phase", "pers_id", "class_name", "parent_pers_id", "owner_uid", "result", "net_id", "parent_net_id"]
    PURGE_NCOL = ["depth_n", "emit_tick_ms", "lease_age_ms", "lease_limit_ms", "max_hp", "health_hp", "confirm_tick_ms"]
    PURGE_PAGE_SIZE = 8

    def purge_row(
        self,
        phase: str,
        ent: dict[str, Any],
        *,
        result: str = "",
        emit_tick_ms: float = 0.0,
        lease_age_ms: float = 0.0,
        lease_limit_ms: float = 0.0,
        confirm_tick_ms: float = 0.0,
    ) -> dict[str, Any]:
        """Una fila del trabajo de purga para la entidad ``ent`` del arbol del director (claves de ``plan["tree"]``)."""
        return {
            "phase": phase,
            "pers_id": ent["pers_id"],
            "class_name": ent["class_name"],
            "parent_pers_id": ent.get("parent_pers_id", ""),
            "owner_uid": ent.get("owner_uid", self.director_uid),
            "result": result,
            "net_id": ent.get("net_id", ""),
            "parent_net_id": ent.get("parent_net_id", ""),
            "depth_n": float(ent.get("depth_n", 0.0)),
            "emit_tick_ms": float(emit_tick_ms),
            "lease_age_ms": float(lease_age_ms),
            "lease_limit_ms": float(lease_limit_ms),
            "max_hp": float(ent.get("max_hp", 100.0)),
            "health_hp": float(ent.get("health_hp", 100.0)),
            "confirm_tick_ms": float(confirm_tick_ms),
        }

    def honest_purge_rows(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Filas honestas: el arbol previo (`pre`) y, por cada autorizado en orden, su baja (`emit`, con la guarda E1
        del momento) y su `result` en un tick posterior; `absent` si no esta, `ambiguous` si esta mas de una vez,
        `retained_foreign` si su arbol tiene algo no autorizado. O3 (aclaracion, punto 2): el `deleted` lleva en
        `confirm_tick_ms` el tick en que se confirmo, posterior a su `emit_tick_ms`; las demas filas, `0`."""
        tree = plan["tree"]
        rows = [self.purge_row("pre", ent) for ent in tree]
        authorized = {r["pers_id"] for r in plan["order_rows"]}
        tick = plan["start_tick_ms"]
        for orow in plan["order_rows"]:
            matches = [ent for ent in tree if ent["pers_id"] == orow["pers_id"]]
            if not matches:
                rows.append(self.purge_row("result", {"pers_id": orow["pers_id"], "class_name": orow["class_name"]}, result="absent"))
                continue
            if len(matches) > 1:
                rows.append(self.purge_row("result", matches[0], result="ambiguous"))
                continue
            ent = matches[0]
            subtree = [e for e in tree if e.get("parent_net_id") == ent["net_id"]]
            if any(e["pers_id"] not in authorized for e in subtree):
                rows.append(self.purge_row("result", ent, result="retained_foreign"))
                continue
            tick += 50.0
            rows.append(self.purge_row(
                "emit", ent, emit_tick_ms=tick, lease_age_ms=plan["lease_age_ms"], lease_limit_ms=plan["lease_limit_ms"],
            ))
            tick += 50.0
            rows.append(self.purge_row("result", ent, result="deleted", confirm_tick_ms=tick))
        return rows

    def _purge_job_read(self, job_id: str, state: str, reason: str, rows: list[dict[str, Any]], page: int,
                        start_tick: float, end_tick: float, enq_inst: str | None) -> None:
        ps = self.PURGE_PAGE_SIZE
        pages_n = (len(rows) + ps - 1) // ps if rows else 0
        chunk = rows[page * ps:(page + 1) * ps]
        self._emit_op(
            "server",
            self.server_epoch_new,
            "job_read",
            self._pack_ext_args(strings={"job": job_id}, numbers={"page_n": float(page)}),
            self._pack_ext_read(
                strings={"job": job_id, "state": state, "reason": reason, "resource": "per_purge"},
                numbers={
                    "page_n": float(page),
                    "pages_n": float(pages_n),
                    "rows_total_n": float(len(rows)),
                    "start_tick_ms": start_tick,
                    "end_tick_ms": end_tick,
                    "onjobend_tick_ms": end_tick,
                    "released_tick_ms": end_tick,
                    "elapsed_dtsum_ms": max(0.0, end_tick - start_tick),
                },
                ncol=self.PURGE_NCOL,
                scol=self.PURGE_SCOL,
                rows=chunk,
            ),
            enq_inst=enq_inst,
        )

    def _emit_runner_purge(self) -> None:
        """t4 del runner (brief, ronda 2 `:570-574`, arbitraje 1, 4, 5 y 7): orden con las acreditadas, acuse con
        `pre_n`, sondeo de `job_read` (pagina 0) hasta un estado terminal, todas las paginas una a una con
        `target_inst` = epoch nuevo, y `job_free`. Las prendas QA que vuelven con el personaje (mismo `pers_id`,
        `net_id` nuevo) aparecen en `pre` y se borran; despues faltan en t5."""
        epoch = self.server_epoch_new
        acc_lids = ["ac_act_1_gloves_dir", "b_act_1_gloves_dir"]
        jeans = self.baseline_dir_rows[0]
        tree: list[dict[str, Any]] = []
        for row in self.baseline_dir_rows:
            tree.append({
                "pers_id": row["pers_id"],
                "class_name": row["class_name"],
                "net_id": row["net_id"],
                "parent_net_id": row["parent_net_id"],
                "parent_pers_id": jeans["pers_id"] if row["parent_net_id"] == jeans["net_id"] else "",
                "depth_n": 1.0 if row["parent_net_id"] == jeans["net_id"] else 0.0,
                "owner_uid": self.director_uid,
            })
        returning = acc_lids if self.purge_returning is None else list(self.purge_returning)
        for lid in returning:
            ent = self.entities_by_lid[lid]
            tree.append({
                "pers_id": ent["pers_id"],
                "class_name": ent["class_name"],
                "net_id": self._alloc_net_id(),
                "parent_net_id": jeans["net_id"],
                "parent_pers_id": jeans["pers_id"],
                "depth_n": 1.0,
                "owner_uid": self.director_uid,
                "logical_id": lid,
            })
        self._advance(100.0, 3)
        plan: dict[str, Any] = {
            "send_order": True,
            "order_strings": {"director_uid": self.director_uid, "expect_epoch": epoch},
            "order_rows": [
                {"pers_id": self.entities_by_lid[lid]["pers_id"], "class_name": self.entities_by_lid[lid]["class_name"]}
                for lid in acc_lids
            ],
            "order_status": "done",
            "order_reason": "",
            "tree": tree,
            "rows": None,
            "state": "done",
            "reason": "ok",
            "pre_n": None,
            "lease_age_ms": 400.0,
            "lease_limit_ms": 3000.0,
            "enq_inst": epoch,
            "start_tick_ms": self.tick_ms,
            "end_tick_ms": None,
            "running_poll": True,
            "read_pages": True,
            "job_free": True,
            "authorized_rows": None,
        }
        if self.purge_hook is not None:
            self.purge_hook(self, plan)
        self.purge_plan = plan
        rows = plan["rows"] if plan["rows"] is not None else self.honest_purge_rows(plan)
        plan["final_rows"] = rows
        self.scenario_events.append({
            "ev": "purge_authorized",
            "director_uid": self.director_uid,
            "rows": plan["authorized_rows"] if plan["authorized_rows"] is not None else [
                {
                    "pers_id": orow["pers_id"],
                    "logical_id": lid,
                    "net_id": self.entities_by_lid[lid]["net_id"],
                    "censuses": ["t1_post_transition_census", "t3_pre_reset_census"]
                    + (["t3_post_reset_census"] if lid.startswith("b_") else []),
                }
                for lid, orow in zip(acc_lids, plan["order_rows"])
            ],
        })
        if not plan["send_order"]:
            return
        job_id = self._next_op_id()
        pre_rows = [r for r in rows if r["phase"] == "pre"]
        start_tick = self.tick_ms
        self._emit_op(
            "server",
            epoch,
            "per_purge_start",
            self._pack_ext_args(strings=plan["order_strings"], ncol=[], scol=["pers_id", "class_name"], rows=plan["order_rows"]),
            self._pack_ext_read(
                strings={"job": job_id, "state": "running", "resource": "per_purge"},
                numbers={"pre_n": float(len(pre_rows) if plan["pre_n"] is None else plan["pre_n"])},
            ),
            status=plan["order_status"],
            reason=plan["order_reason"],
            op_id=job_id,
            enq_inst=plan["enq_inst"],
        )
        if plan["order_status"] != "done":
            return
        if plan["running_poll"]:
            self._purge_job_read(job_id, "running", "", pre_rows, 0, start_tick, 0.0, plan["enq_inst"])
        steps = sum(1 for r in rows if r["phase"] in ("emit", "result"))
        self._advance(50.0 * (steps + 1), 3)
        end_tick = self.tick_ms if plan["end_tick_ms"] is None else float(plan["end_tick_ms"])
        state = plan["state"]
        if state not in ("done", "failed", "stopped", "expired"):
            # el trabajo sigue vivo al vencer la espera: el sondeo solo ve la pagina 0 en `running`
            self._purge_job_read(job_id, state, "", rows, 0, start_tick, 0.0, plan["enq_inst"])
            return
        self._purge_job_read(job_id, state, plan["reason"], rows, 0, start_tick, end_tick, plan["enq_inst"])
        if plan["read_pages"]:
            pages_n = (len(rows) + self.PURGE_PAGE_SIZE - 1) // self.PURGE_PAGE_SIZE if rows else 1
            for page in range(pages_n):
                self._purge_job_read(job_id, state, plan["reason"], rows, page, start_tick, end_tick, plan["enq_inst"])
        if plan["job_free"]:
            self._emit_op(
                "server",
                epoch,
                "job_free",
                self._pack_ext_args(strings={"job": job_id}),
                self._pack_ext_read(strings={"job": job_id, "freed": "1", "resource": "per_purge"}),
                enq_inst=plan["enq_inst"],
            )

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

        # Initial per_status (brief, ronda 2 `:531` y arbitraje 8): en t0 va sin `director_uid` y la salida trae
        # `players_n`; solo con un jugador listo trae su uid y su estado. Con cero se sigue esperando.
        for t0_pn in self.t0_players_n:
            one = t0_pn == 1
            self._emit_op(
                "server",
                self.server_epoch_old,
                "per_status",
                self._pack_ext_args(strings={"director_uid": ""}),
                self._pack_ext_read(
                    strings={"server_epoch": self.server_epoch_old, "director_uid": self.director_uid if one else ""},
                    numbers={
                        "tick_ms": self.tick_ms,
                        "frame": float(self.frame),
                        "registered_total_n": 0.0,
                        "scenes_count_n": 0.0,
                        "players_n": float(t0_pn),
                        "director_present_b": 1.0 if one else 0.0,
                        "director_alive_b": 1.0 if one else 0.0,
                        "director_inv_readable_b": 1.0 if one else 0.0,
                        "director_inv_count_n": (3.0 if self.baseline_sentinel_glove else 2.0) if one else 0.0,
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
            "pers_id": self._alloc_pers_id(),
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
            "pers_id": self._alloc_pers_id(),
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
        if self.baseline_sentinel_glove:
            # arbitraje 6: unos guantes vanilla de la misma clase que los de scene_a_clean, puestos desde t0
            baseline_dir_rows.append({
                **copy.deepcopy(dir_jeans_row),
                "class_name": "WorkingGloves_Beige",
                "slot_name": "Gloves",
                "net_id": "1:12",
                "pers_id": self._alloc_pers_id(),
                "max_hp": 100.0,
                "health_hp": 100.0,
                "inv_children_n": 0.0,
            })
        self.baseline_dir_rows = baseline_dir_rows

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
        sentinel_set = set(self.fixture["sentinel_classes"])
        self.scenario_events.append({
            "ev": "baseline_director_foreign",
            "director_uid": self.director_uid,
            "rows": copy.deepcopy([r for r in baseline_dir_rows if r["class_name"] not in sentinel_set]),
        })
        # brief, ronda 2 (`:537`): el basal es completo; las filas de clase centinela del director van aparte
        self.scenario_events.append({
            "ev": "baseline_director_sentinel",
            "director_uid": self.director_uid,
            "rows": copy.deepcopy([r for r in baseline_dir_rows if r["class_name"] in sentinel_set]),
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
                pers = self._alloc_pers_id()
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
                        "pers_id": pers,
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
                    "pers_id_t1": self.entities_by_lid[r["logical_id"]]["pers_id"],
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
            pers_id = "11:22:33:44" if mode == "persistent_control" else self._alloc_pers_id()

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

            t_strings = {
                "scene_id": sc_id,
                "logical_id": lid,
                "action": act,
                "expect_epoch": self.server_epoch_old,
                "target_scene_id": tgt_sc,
                "target_parent_id": tgt_pid,
            }
            if act == "move_to_director":
                t_strings["director_uid"] = self.director_uid
            t_args = self._pack_ext_args(strings=t_strings)
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
        self._advance(1000.0, 30)
        self._emit_op(
            "server",
            self.server_epoch_old,
            "per_status",
            self._pack_ext_args(strings={"director_uid": self.director_uid}),
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
        # Keepalive del peer viejo despues de su ultima lectura (formato del nucleo: poll con deliver=0, con su
        # tick): su silencio posterior es observable (N49, Sol delta BLOQ 3).
        if self.old_keepalive_after_stop:
            self._advance(200.0, 6)
            self.bridge_events.append({
                "ev": "keepalive",
                "peer": "server",
                "inst": self.server_epoch_old,
                "http": 200,
                "n_ops": 0,
                "body_len": 24,
                "frame": self.frame,
                "tick_s": self.tick_ms / 1000.0,
                "now_ms": self.h_ms,
                "t_ms": self.h_ms,
            })
        # Parada y arranque: el proceso nuevo tiene su propio reloj (tick_ms desde su arranque); el bridge sigue.
        self.h_ms += self.restart_gap_ms
        if self.server_epoch_new != self.server_epoch_old:
            self.tick_ms = self.new_epoch_tick0_ms
            self.frame = 12
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

        # Primera orden del epoch nuevo: el per_status de la espera, que valida al director (por su uid y con
        # `target_inst` = epoch nuevo, arbitraje 7)
        self._emit_op(
            "server",
            self.server_epoch_new,
            "per_status",
            self._pack_ext_args(strings={"director_uid": self.director_uid}),
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
                    "director_inv_count_n": float(len(self.baseline_dir_rows)),
                },
                ncol=["gen_n", "own_alive_n"],
                scol=["scene_id", "last_op_id"],
                rows=[],
            ),
            enq_inst=self.server_epoch_new,
        )

        # Purga ordenada por el runner (brief, secciones finales): con el director validado y antes del primer censo
        # t5, la orden con las acreditadas, su trabajo `per_purge_start`, su sondeo, sus paginas y su `job_free`.
        self._emit_runner_purge()

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
            self.t5_track_discs.append(("t5_track_b_inf_1_t2", b_inf_x, b_inf_z))
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
                "pers_id": self._alloc_pers_id(),
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
                self._pack_ext_args(strings={"director_uid": self.director_uid}),
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
        for disc, disc_x, disc_z in self.t5_track_discs:
            self._emit_census(
                self.server_epoch_new, "t6_post_cleanup_census", disc, disc_x, disc_z, [], include_director_b=0
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


def _is_finite_t(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


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
            # Sol delta BLOQ 1: los resultados reales del nucleo (fake_peer.py `_done`) NO llevan `verb`: el verbo
            # se resuelve por el op_id con el `enq` que registro el propio bridge (bridge_qa.py `enqueue`).
            verb_by_op: dict[str, str] = {}
            for r in registered:
                if r.get("ev") == "enq" and r.get("op_id") and r.get("verb"):
                    verb_by_op.setdefault(str(r["op_id"]), str(r["verb"]))
            applied = [
                1
                for r in registered
                if r.get("ev") == "result"
                for res in (r.get("results") or ([r["result"]] if isinstance(r.get("result"), dict) else []))
                if res.get("status") == "done"
                and (res.get("verb") or verb_by_op.get(str(res.get("op_id") or r.get("op_id") or ""))) == "per_apply_scene"
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
        # Case A: pers_id all "0:0:0:0" in every census (t1, witness and after restart). Oraculo v2: el motor da
        # pers_id != 0 desde la creacion, asi que en t1 y en el testigo es FALLA (PER-01, PER-09); tras el
        # reinicio la identidad del control sigue sin poder verificarse (PER-06 missing).
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
            self.assertEqual(verdict["exit_code"], 1)
            c_map = _checks_by_id(verdict)
            self.assertEqual(c_map["PER-01"]["status"], "fail")
            self.assertIn("census_zero_or_invalid_pers_id", c_map["PER-01"]["detail"])
            self.assertEqual(c_map["PER-09"]["status"], "fail")
            self.assertIn("witness_census_row_invalid", c_map["PER-09"]["detail"])
            self.assertEqual(c_map["PER-06"]["status"], "missing")
            self.assertEqual(c_map["PER-06"]["detail"], "identity_unverifiable")

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

    # Oraculo v2 (partida real del 2026-11-16): pers_id != "0:0:0:0" desde la creacion, en t1 y en el testigo.

    def _set_census_pers_id(
        self, part_dir: Path, builder: "_SyntheticPartBuilder", area_tag: str, lid: str, pers_id: str
    ) -> None:
        """Pone ``pers_id`` en la fila ``own_logical_id == lid`` del censo ``area_tag`` (solo en ese censo)."""
        events = _read_events(part_dir)
        jobs: set[str] = set()
        hits = 0
        for ev in events:
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("verb") == "per_census_start":
                    u_s, _u_n, _u_r = _unpack(res["read"])
                    if u_s.get("area_tag") == area_tag:
                        jobs.add(u_s["job"])
                elif res.get("verb") == "job_read":
                    u_s, u_n, u_r = _unpack(res["read"])
                    if u_s.get("job") not in jobs:
                        continue
                    for row in u_r:
                        if row.get("own_logical_id") == lid:
                            row["pers_id"] = pers_id
                            hits += 1
                    res["read"] = builder._pack_ext_read(
                        strings=u_s, numbers=u_n, ncol=res["read"]["ncol"], scol=res["read"]["scol"], rows=u_r
                    )
        self.assertEqual(hits, 1, msg=f"{area_tag}:{lid}")
        _write_events(part_dir, events)

    def _add_apply_pers_column(
        self, part_dir: Path, builder: "_SyntheticPartBuilder", override: dict[tuple[str, str], str]
    ) -> int:
        """Anade a las filas de ``per_apply_scene`` la columna opcional ``pers_id`` con el valor del censo de esa
        entidad en su epoch (``override[(inst, logical_id)]`` lo sustituye). Devuelve cuantas filas la llevan."""
        events = _read_events(part_dir)
        census_pers: dict[tuple[str, str], str] = {}
        for ev in events:
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("verb") == "job_read":
                    _u_s, _u_n, u_r = _unpack(res["read"])
                    for row in u_r:
                        if row.get("own_logical_id"):
                            census_pers.setdefault((ev["inst"], row["own_logical_id"]), row["pers_id"])
        n = 0
        for ev in events:
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("verb") != "per_apply_scene" or res.get("status") != "done":
                    continue
                u_s, u_n, u_r = _unpack(res["read"])
                for row in u_r:
                    key = (ev["inst"], row["logical_id"])
                    row["pers_id"] = override.get(key, census_pers[key])
                    n += 1
                res["read"] = builder._pack_ext_read(
                    strings=u_s,
                    numbers=u_n,
                    ncol=res["read"]["ncol"],
                    scol=list(res["read"]["scol"]) + ["pers_id"],
                    rows=u_r,
                )
        _write_events(part_dir, events)
        return n

    def test_v2_t1_scene_row_with_zero_or_malformed_pers_id_not_pasa(self) -> None:
        """Oraculo v2/v2.1: una fila de t1 de una entidad de escena con pers_id cero o imposible -> FALLA/PER-01.

        v2.1 (Sol r1 BLOQ 2): "-0", fuera de int32, ceros a la izquierda, no numerico y "\\n" final no son ids.
        """
        for bad in ("0:0:0:0", "1:2:3", "-0:0:0:0", "2147483648:0:0:0", "01:2:3:4", "1:2:3:x", "1:2:3:4\n"):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / "t1_bad_pers")
                self._set_census_pers_id(part_dir, builder, "t1_pre_transition_census:area_a", "a_prop_1", bad)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 1, msg=repr(bad))
                self.assertEqual(_only_non_pass(verdict), {"PER-01": "fail"}, msg=repr(bad))
                self.assertIn("a_prop_1:census_zero_or_invalid_pers_id", _checks_by_id(verdict)["PER-01"]["detail"])

    def test_v2_witness_row_with_zero_pers_id_not_pasa(self) -> None:
        """Oraculo v2/v2.1: una fila del testigo con pers_id "0:0:0:0" o "-0:0:0:0" -> FALLA/PER-09."""
        for bad in ("0:0:0:0", "-0:0:0:0"):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / "witness_zero_pers")
                self._set_census_pers_id(part_dir, builder, "t5_witness_pre_census:area_b", "b_prop_1", bad)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 1, msg=bad)
                self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"}, msg=bad)
                self.assertIn("witness_census_row_invalid:b_prop_1", _checks_by_id(verdict)["PER-09"]["detail"])

    def test_v2_pers_id_reported_by_spawn_must_match_census(self) -> None:
        """Oraculo v2: si ``per_apply_scene`` reporta ``pers_id`` (columna opcional), el censo trae el mismo.

        Columna igual al censo -> PASA; distinta en t1 -> FALLA/PER-01; distinta en el testigo -> FALLA/PER-09;
        ``"0:0:0:0"`` en el recibo no es un id real y no se compara (como ``pers_id_t3`` en PER-06) -> PASA.
        """
        cases = (
            ("matching", {}, {}),
            ("t1_mismatch", {("old", "a_prop_1"): "7:7:7:7"}, {"PER-01": "fail"}),
            ("witness_mismatch", {("new", "b_prop_1"): "7:7:7:7"}, {"PER-09": "fail"}),
            ("spawn_reports_zero", {("old", "a_prop_1"): "0:0:0:0"}, {}),
        )
        for name, ovr, expected in cases:
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / name)
                epoch = {"old": builder.server_epoch_old, "new": builder.server_epoch_new}
                n = self._add_apply_pers_column(part_dir, builder, {(epoch[e], lid): p for (e, lid), p in ovr.items()})
                self.assertGreater(n, 0, msg=name)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(_only_non_pass(verdict), expected, msg=name)
                self.assertEqual(verdict["exit_code"], 1 if expected else 0, msg=name)
                if name == "t1_mismatch":
                    self.assertIn(
                        "a_prop_1:census_pers_id_differs_from_spawn", _checks_by_id(verdict)["PER-01"]["detail"]
                    )
                if name == "witness_mismatch":
                    self.assertIn("witness_census_row_invalid:b_prop_1", _checks_by_id(verdict)["PER-09"]["detail"])

    # Oraculo v2.1 (Sol r1 sobre v2): ids canonicos int32, unicos por etapa y epoch, y estables en el testigo.

    def _census_pers_id(self, part_dir: Path, area_tag: str, lid: str) -> str:
        """``pers_id`` de la fila ``own_logical_id == lid`` del censo ``area_tag``."""
        jobs: set[str] = set()
        found: list[str] = []
        for ev in _read_events(part_dir):
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("verb") == "per_census_start":
                    u_s, _u_n, _u_r = _unpack(res["read"])
                    if u_s.get("area_tag") == area_tag:
                        jobs.add(u_s["job"])
                elif res.get("verb") == "job_read":
                    u_s, _u_n, u_r = _unpack(res["read"])
                    if u_s.get("job") in jobs:
                        found += [r["pers_id"] for r in u_r if r.get("own_logical_id") == lid]
        self.assertEqual(len(found), 1, msg=f"{area_tag}:{lid}")
        return found[0]

    def _set_all_own_census_pers_id(self, part_dir: Path, builder: "_SyntheticPartBuilder", pers_id: str) -> int:
        """Pone ``pers_id`` en todas las filas QA propias (``own_logical_id``) de todos los censos; devuelve cuantas."""
        events = _read_events(part_dir)
        n = 0
        for ev in events:
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("verb") != "job_read":
                    continue
                u_s, u_n, u_r = _unpack(res["read"])
                for row in u_r:
                    if row.get("own_logical_id"):
                        row["pers_id"] = pers_id
                        n += 1
                res["read"] = builder._pack_ext_read(
                    strings=u_s, numbers=u_n, ncol=res["read"]["ncol"], scol=res["read"]["scol"], rows=u_r
                )
        _write_events(part_dir, events)
        return n

    def test_v2_1_pers_id_validator_canonical_int32(self) -> None:
        """Oraculo v2.1 (Sol r1 BLOQ 2): 4 enteros int32 en forma canonica; el cero se mide por valor."""
        for ok in ("1:-2:3:4", "0:0:0:1", "-2147483648:2147483647:0:5", "1594376013:1497516033:-1137025392:470150303"):
            self.assertTrue(s_persist_eval._is_nonzero_pers_id(ok), msg=ok)
            self.assertEqual(s_persist_eval._pers_id_issue(ok), "", msg=ok)
        self.assertTrue(s_persist_eval._valid_pers_id("0:0:0:0"))
        self.assertFalse(s_persist_eval._is_nonzero_pers_id("0:0:0:0"))
        for bad in (
            "-0:0:0:0", "00:0:0:0", "01:2:3:4", "+1:2:3:4", "2147483648:0:0:0", "-2147483649:0:0:0", "1:2:3",
            "1:2:3:4:5", "1:2:3:4\n", " 1:2:3:4", "a:b:c:d", "1:2:3:x", "١:2:3:4", "", None, 1234,
        ):
            self.assertFalse(s_persist_eval._valid_pers_id(bad), msg=repr(bad))
            self.assertEqual(s_persist_eval._pers_id_issue(bad), "zero_or_invalid_pers_id", msg=repr(bad))

    def test_v2_1_constant_or_copied_pers_id_not_pasa(self) -> None:
        """Oraculo v2.1 (Sol r1 BLOQ 1): el mismo pers_id en entidades distintas de una etapa no da PASA.

        (a) todas las filas QA con el id copiado del control (``area_c`` intacta), sin recibos, y (b) con recibos
        de ``per_apply_scene`` que coinciden: FALLA en PER-01 y PER-09. (c) dos entidades distintas de t1 con el
        mismo id: solo PER-01. (d) dos entidades distintas del testigo con el mismo id antes y despues: solo PER-09.
        """
        for with_receipts in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / "copied_control_pers")
                ctrl_pid = builder.entities_by_lid["c_persistent_control"]["pers_id"]
                self.assertGreaterEqual(self._set_all_own_census_pers_id(part_dir, builder, ctrl_pid), 100)
                if with_receipts:
                    self.assertGreater(self._add_apply_pers_column(part_dir, builder, {}), 0)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                c_map = _checks_by_id(verdict)
                self.assertEqual(verdict["exit_code"], 1, msg=f"receipts={with_receipts}")
                # O2 (contrato de la purga, `:542` y arbitraje 3): con el `pers_id` copiado del control los guantes no
                # se pueden acreditar -> PER-08 `missing` (falta de evidencia), ademas de los dos `fail` de siempre.
                self.assertEqual(
                    _only_non_pass(verdict), {"PER-01": "fail", "PER-08": "missing", "PER-09": "fail"}, msg=f"receipts={with_receipts}"
                )
                self.assertIn("purge_accredited_unidentified:b_act_1_gloves_dir:pers_id_shared", c_map["PER-08"]["detail"])
                self.assertIn(f"t1_pers_id_shared_by_distinct_entities:{ctrl_pid}", c_map["PER-01"]["detail"])
                self.assertIn(f"witness_pers_id_shared_by_distinct_entities:{ctrl_pid}", c_map["PER-09"]["detail"])
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "t1_two_entities_same_pers")
            pid = builder.entities_by_lid["a_prop_1"]["pers_id"]
            self._set_census_pers_id(part_dir, builder, "t1_pre_transition_census:area_a", "a_prop_2", pid)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_only_non_pass(verdict), {"PER-01": "fail"})
            self.assertIn(f"t1_pers_id_shared_by_distinct_entities:{pid}", _checks_by_id(verdict)["PER-01"]["detail"])
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "witness_two_entities_same_pers")
            pid = self._census_pers_id(part_dir, "t5_witness_pre_census:area_b", "b_prop_1")
            for tag in ("t5_witness_pre_census:area_b", "t5_witness_post_census:area_b"):
                self._set_census_pers_id(part_dir, builder, tag, "b_chest_own", pid)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"})
            self.assertIn(f"witness_pers_id_shared_by_distinct_entities:{pid}", _checks_by_id(verdict)["PER-09"]["detail"])

    def test_v2_1_witness_post_census_pers_id_changed_not_pasa(self) -> None:
        """Oraculo v2.1 (Sol r1 MEN): si el pers_id de una entidad del testigo cambia del censo previo al
        posterior (a cero o a otro id) -> FALLA/PER-09."""
        for new_pid in ("0:0:0:0", "7:7:7:7"):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / "witness_post_pers_changed")
                self._set_census_pers_id(part_dir, builder, "t5_witness_post_census:area_b", "b_prop_1", new_pid)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(verdict["exit_code"], 1, msg=new_pid)
                self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"}, msg=new_pid)
                self.assertIn("witness_entity_changed:", _checks_by_id(verdict)["PER-09"]["detail"])

    # Oraculo v2.1 (autorizado por Guillermo): en t6 solo cuenta como superviviente lo que es del test.

    @staticmethod
    def _t6_row(**over: Any) -> dict[str, Any]:
        """Fila completa de censo para inyectar en t6 (por defecto, un infectado del CE en area_c)."""
        row: dict[str, Any] = {
            "class_name": "ZmbM_PatrolNormal_Autumn", "loc_kind": "ground", "parent_class": "", "parent_net_id": "",
            "slot_name": "", "owner_uid": "", "own_logical_id": "", "net_id": "1:8001",
            "pers_id": "-1203338211:774601125:-98765431:1357913579", "own_b": 0.0, "in_radius_b": 1.0, "alive_b": 1.0,
            "ai_agent_b": 1.0, "pos_x_m": 4862.0, "pos_y_m": _surface_y(4862.0, 10202.0), "pos_z_m": 10202.0,
            "yaw_deg": 33.0, "pitch_deg": 0.0, "roll_deg": 0.0, "max_hp": 100.0, "health_hp": 41.0,
            "inv_children_n": 0.0, "spawn_tick_ms": 0.0,
        }
        row.update(over)
        return row

    def _add_t6_rows(
        self, part_dir: Path, builder: "_SyntheticPartBuilder", area_id: str, extra: list[dict[str, Any]]
    ) -> None:
        """Anade ``extra`` al censo t6 de ``area_id`` (area base, con el director si lo lleva, o disco ``t5_track_*``)
        en su ultima pagina, con sus contadores coherentes."""
        events = _read_events(part_dir)
        tag = f"t6_post_cleanup_census:{area_id}"
        jobs: set[str] = set()
        appended = 0
        for ev in events:
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("verb") == "per_census_start":
                    u_s, u_n, u_r = _unpack(res["read"])
                    if u_s.get("area_tag") == tag:
                        jobs.add(u_s["job"])
                        u_n["rows_captured_n"] = float(u_n["rows_captured_n"]) + len(extra)
                        res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
                elif res.get("verb") == "job_read":
                    u_s, u_n, u_r = _unpack(res["read"])
                    if u_s.get("job") in jobs:
                        pages_n = max(1, int(round(u_n["pages_n"])))
                        u_n["pages_n"] = float(pages_n)
                        u_n["rows_total_n"] = float(u_n["rows_total_n"]) + len(extra)
                        if int(round(u_n["page_n"])) == pages_n - 1:
                            u_r.extend(copy.deepcopy(extra))
                            appended += 1
                        res["read"] = builder._pack_ext_read(
                            strings=u_s, numbers=u_n, ncol=res["read"]["ncol"], scol=res["read"]["scol"], rows=u_r
                        )
        self.assertEqual(appended, 1, msg=tag)
        _write_events(part_dir, events)

    def _census_row(self, part_dir: Path, area_tag: str, lid: str) -> dict[str, Any]:
        """Fila ``own_logical_id == lid`` del censo ``area_tag``."""
        jobs: set[str] = set()
        found: list[dict[str, Any]] = []
        for ev in _read_events(part_dir):
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("verb") == "per_census_start":
                    u_s, _u_n, _u_r = _unpack(res["read"])
                    if u_s.get("area_tag") == area_tag:
                        jobs.add(u_s["job"])
                elif res.get("verb") == "job_read":
                    u_s, _u_n, u_r = _unpack(res["read"])
                    if u_s.get("job") in jobs:
                        found += [r for r in u_r if r.get("own_logical_id") == lid]
        self.assertEqual(len(found), 1, msg=f"{area_tag}:{lid}")
        return found[0]

    def test_v2_1_t6_only_test_entities_count_as_survivors(self) -> None:
        """Oraculo v2.1 (brief :284, :189): tras ``per_cleanup_qa`` solo tumba PER-09 lo que es del test.

        Un infectado del CE con su gorra en el area -> PASA. Un superviviente del QA ajeno por diseno
        (``per_spawn_raw``, ``own_b=0``), por su ``pers_id`` o su marca de vida -> FALLA/PER-09. Una fila del CE que
        se hace pasar por el QA (``pers_id`` o ``net_id`` de una entidad del test, o clase centinela con la marca
        de vida del QA) -> FALLA/PER-09. Sol r2: el ``Fireplace`` hijo del control (sin recibo propio) que en t6
        esta suelto o dentro de un ``WoodenCrate`` ajeno sigue siendo del test -> FALLA/PER-09.
        """
        cap = {
            "class_name": "PilotkaCap", "loc_kind": "attachment", "parent_class": "ZmbM_PatrolNormal_Autumn",
            "parent_net_id": "1:8001", "slot_name": "Headgear", "net_id": "1:8002", "ai_agent_b": 0.0,
            "pers_id": "1471113377:-246813579:1029384756:-1122334455", "health_hp": 100.0,
        }
        crate = {
            "class_name": "WoodenCrate", "net_id": "1:8010", "pers_id": "-1987654321:123456789:-24680:97531",
            "ai_agent_b": 0.0, "max_hp": 400.0, "health_hp": 400.0, "inv_children_n": 1.0,
        }
        for name in ("ce_infected_with_cap", "qa_control_raw", "qa_foreign_raw_by_pers_id", "ce_with_qa_pers_id",
                     "ce_with_qa_net_id", "ce_sentinel_with_qa_mark", "qa_raw_child_loose",
                     "qa_raw_child_in_foreign_crate"):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run")
                part_dir = builder.build_into(Path(tmp) / name)
                wit = self._census_row(part_dir, "t5_witness_pre_census:area_b", "b_prop_1")
                raw_wb = builder.entities_by_lid["a_foreign_ground"]
                fp = dict(builder.entities_by_lid["c_persistent_control_child"], alive_b=1.0)
                rows = {
                    "ce_infected_with_cap": [self._t6_row(), self._t6_row(**cap)],
                    "qa_control_raw": [dict(builder.entities_by_lid["c_persistent_control"], alive_b=1.0)],
                    "qa_foreign_raw_by_pers_id": [
                        self._t6_row(class_name="WaterBottle", net_id="1:8003", pers_id=raw_wb["pers_id"],
                                     ai_agent_b=0.0, health_hp=100.0)
                    ],
                    "ce_with_qa_pers_id": [self._t6_row(pers_id=wit["pers_id"]), self._t6_row(**cap)],
                    "ce_with_qa_net_id": [self._t6_row(net_id=wit["net_id"])],
                    "ce_sentinel_with_qa_mark": [
                        self._t6_row(class_name="Barrel_Yellow", ai_agent_b=0.0, max_hp=1300.0, health_hp=1300.0 * 0.845)
                    ],
                    "qa_raw_child_loose": [
                        dict(fp, loc_kind="ground", parent_class="", parent_net_id="", slot_name="")
                    ],
                    "qa_raw_child_in_foreign_crate": [
                        dict(fp, loc_kind="cargo", parent_class="WoodenCrate", parent_net_id="1:8010",
                             slot_name="Cargo:0:0:0"),
                        self._t6_row(**crate),
                    ],
                }[name]
                self._add_t6_rows(part_dir, builder, "area_c", rows)
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                if name == "ce_infected_with_cap":
                    self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(_only_non_pass(verdict)))
                    continue
                self.assertEqual(verdict["exit_code"], 1, msg=name)
                self.assertEqual(_only_non_pass(verdict), {"PER-09": "fail"}, msg=name)
                detail = _checks_by_id(verdict)["PER-09"]["detail"]
                self.assertTrue(detail.startswith("t6_cleanup_survivors:"), msg=f"{name}: {detail}")
                self.assertIn(f"{rows[0]['class_name']}:{rows[0]['net_id']}", detail, msg=name)
                if name == "ce_with_qa_pers_id":
                    self.assertIn("PilotkaCap:1:8002", detail, msg=name)
                if name == "qa_raw_child_in_foreign_crate":
                    self.assertNotIn("WoodenCrate", detail, msg=name)

    def _t6_census_op_ids(self, events: list[dict[str, Any]], area_tag: str) -> set[str]:
        """``op_id`` del censo ``area_tag`` (``per_census_start``) y de sus ``job_read`` / ``job_free``."""
        starts: set[str] = set()
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("verb") == "per_census_start" and _unpack(res["read"])[0].get("area_tag") == area_tag:
                    starts.add(res["op_id"])
        ids = set(starts)
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("verb") in ("job_read", "job_free") and _unpack(res["read"])[0].get("job") in starts:
                    ids.add(res["op_id"])
        return ids

    def _shift_census_center(
        self, part_dir: Path, builder: "_SyntheticPartBuilder", area_tag: str, dx_m: float
    ) -> None:
        """Desplaza ``dx_m`` en x el centro que publica el censo ``area_tag``."""
        events = _read_events(part_dir)
        moved = 0
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("verb") == "per_census_start":
                    u_s, u_n, u_r = _unpack(res["read"])
                    if u_s.get("area_tag") == area_tag:
                        u_n["center_x_m"] = float(u_n["center_x_m"]) + dx_m
                        res["read"] = builder._pack_ext_read(strings=u_s, numbers=u_n, rows=u_r)
                        moved += 1
        self.assertEqual(moved, 1, msg=area_tag)
        _write_events(part_dir, events)

    def test_v2_1_t6_director_and_track_discs(self) -> None:
        """Oraculo v2.1 (Sol, confirmacion de t6): la limpieza se verifica tambien en el director y en los discos
        ``t5_track_*``.

        a) Una prenda QA (``own_b=1``) dentro del director tras la limpieza -> FALLA/PER-09; una prenda de inicio del
        director sin identidad QA (``BandageDressing`` centinela, vida completa) no es superviviente de la limpieza
        (PER-09 pasa). b) Con el disco t5 ``t5_track_b_inf_1_t2``: el ``Fireplace`` del control superviviente en su
        censo t6 -> FALLA/PER-09; un ``Barrel_Yellow`` del mundo ahi -> PASA; sin su censo t6, o con el censo t6 en otro
        centro -> INCONCLUSO/PER-09.
        O3 (aclaracion del brief, punto 4: lo observado tras la purga se juzga en cualquier censo posterior, t6 incluido):
        en a), el guante QA es ademas un remanente por identidad -> PER-08 `fail` (`purge_remnant`); y la venda, de clase
        centinela y con un `pers_id` que no es del basal ni de una prenda acreditada, es una centinela sin atribuir ->
        PER-08 `missing` (`:588`), aunque PER-09 siga pasando.
        """
        disc = "t5_track_b_inf_1_t2"
        for name in ("qa_garment_in_director", "director_start_item", "qa_survivor_in_track_disc",
                     "ce_barrel_in_track_disc", "track_disc_without_t6", "track_disc_t6_elsewhere"):
            with tempfile.TemporaryDirectory() as tmp:
                builder = _SyntheticPartBuilder("run", creature_far_move_m=75.0, include_t5_track_disks=True)
                part_dir = builder.build_into(Path(tmp) / name)
                needle = ""
                per08_needle = ""
                if name == "qa_garment_in_director":
                    gloves = dict(builder.entities_by_lid["b_act_1_gloves_dir"], alive_b=1.0)
                    self.assertEqual(gloves["owner_uid"], builder.director_uid)
                    self._add_t6_rows(part_dir, builder, "area_a", [gloves])
                    expected = {"PER-08": "fail", "PER-09": "fail"}
                    needle = f"t6_cleanup_survivors:WorkingGloves_Yellow:{gloves['net_id']}"
                    per08_needle = "purge_remnant:b_act_1_gloves_dir"
                elif name == "director_start_item":
                    self._add_t6_rows(part_dir, builder, "area_a", [self._t6_row(
                        class_name="BandageDressing", loc_kind="cargo", parent_class="Jeans_Blue", parent_net_id="1:10",
                        slot_name="Cargo:0:2:0", owner_uid=builder.director_uid, net_id="1:8020", ai_agent_b=0.0,
                        pers_id="1357924680:-1357924680:24681357:-97531", max_hp=50.0, health_hp=50.0,
                    )])
                    expected = {"PER-08": "missing"}
                    per08_needle = "director_sentinel_unattributable:BandageDressing"
                elif name == "qa_survivor_in_track_disc":
                    fp = dict(builder.entities_by_lid["c_persistent_control_child"], alive_b=1.0, loc_kind="ground",
                              parent_class="", parent_net_id="", slot_name="")
                    self._add_t6_rows(part_dir, builder, disc, [fp])
                    expected = {"PER-09": "fail"}
                    needle = f"t6_cleanup_survivors:Fireplace:{fp['net_id']}"
                elif name == "ce_barrel_in_track_disc":
                    self._add_t6_rows(part_dir, builder, disc, [self._t6_row(
                        class_name="Barrel_Yellow", net_id="1:8030", ai_agent_b=0.0, max_hp=1300.0, health_hp=384.9,
                        pers_id="1780910942:-1857628348:2126480516:1419094472",
                    )])
                    expected = {}
                elif name == "track_disc_without_t6":
                    events = _read_events(part_dir)
                    ops = self._t6_census_op_ids(events, f"t6_post_cleanup_census:{disc}")
                    self.assertEqual(len(ops), 3, msg=name)
                    _write_events(part_dir, _drop_ops(events, ops))
                    expected = {"PER-09": "missing"}
                    needle = f"t6_cleanup_census_absent:{disc}"
                else:
                    self._shift_census_center(part_dir, builder, f"t6_post_cleanup_census:{disc}", 5.0)
                    expected = {"PER-09": "missing"}
                    needle = f"t6_cleanup_census_absent:{disc}"
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertEqual(_only_non_pass(verdict), expected, msg=name)
                statuses = set(expected.values())
                self.assertEqual(verdict["exit_code"], 1 if "fail" in statuses else (2 if statuses else 0), msg=name)
                if needle:
                    self.assertIn(needle, _checks_by_id(verdict)["PER-09"]["detail"], msg=name)
                if per08_needle:
                    self.assertIn(per08_needle, _checks_by_id(verdict)["PER-08"]["detail"], msg=name)

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
            with _CoreTap() as tap, e2e_witness.Witness() as witness:
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
            # Testigo comun del nucleo (E9, PR #17): cada fila de bridge.jsonl la emitio el bridge desde un origen
            # real, toda orden entregada/resuelta paso por un socket y esta en la traza de un proceso peer lanzado
            # por PartContext, con los mismos digests; y el runner no se conecto al bridge.
            self.assertEqual(witness.verify(ev_dir), [])
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
                                        "pers_id": "-1311752381:996137005:-224557291:1468313449",
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
            "pers_id": builder.entities_by_lid["b_prop_1"]["pers_id"],
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
        with tempfile.TemporaryDirectory() as tmp, _CoreTap() as tap, e2e_witness.Witness() as witness:
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
            # El testigo comun no ve nada fabricado en el trafico honesto.
            self.assertEqual(witness.verify(base), [])
            # Un runner que reescribe bridge.jsonl despues de cerrar el contexto queda al descubierto.
            events = _read_events(base / "run")
            events.append({"ev": "result", "peer": "server", "inst": "x", "results": [{"op_id": "forged", "verb": "per_apply_scene", "status": "done", "read": {}}]})
            _write_events(base / "run", events)
            self.assertIn("run:disk_rows_differ_from_core_registry", tap.problems(base, ["run"]))
            self.assertIn("unwitnessed_row", {p.code for p in witness.verify(base)})

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
                with _CoreTap() as tap, e2e_witness.Witness() as witness:
                    rc = m1_gate.main(["spike", "S-persist", "--both", "--build", "offline", "--evidence", str(ev_dir)])
                # La evidencia fabricada pasa el oraculo: eso solo no acredita la procedencia...
                self.assertEqual(rc, 0)
                # ...pero el nucleo no abrio ninguna parte, ni lanzo peers, ni registro trafico.
                self.assertEqual(
                    sorted(tap.problems(ev_dir, expected_parts)),
                    sorted(f"{p}:no_part_context_opened" for p in expected_parts),
                )
                # El testigo comun lo ve igual: ninguna fila la emitio el bridge y no hay peers reales.
                codes = {p.code for p in witness.verify(ev_dir)}
                self.assertIn("no_peer_process", codes)
                self.assertIn("unwitnessed_row", codes)
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
        """MEN-4 / Sol r2 Nuevo 2: hueco silencioso de 60 s (parada o carga) -> INCONCLUSO; hueco corto -> PASA.

        Sol delta BLOQ 3: la ventana sin observacion se cuenta entera con el reloj del bridge, de modo que el hueco
        entre la ultima lectura/keepalive del peer viejo y el hello nuevo es el de la parada, y el de la carga
        arranca en el hello nuevo; el hueco corto (2 s) sigue pasando.
        """
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run", restart_gap_ms=2000.0)
            part_dir = builder.build_into(Path(tmp) / "short_gap")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
        # 60 s entre el keepalive del peer viejo y el hello del nuevo (el mundo pudo seguir)
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run", restart_gap_ms=60000.0)
            part_dir = builder.build_into(Path(tmp) / "gap_before_restart")
            self._n49_expect_unaccredited_or_unreachable(part_dir, "gap_before_restart")
        # 60 s entre el hello del epoch nuevo y su primera lectura (el mundo ya corria): los relojes del
        # epoch nuevo, y los del bridge desde alli, van 60 s por delante del peer viejo
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "gap_after_load")
            events = _read_events(part_dir)
            for ev in events[self._new_hello_index(events, builder):]:
                if _is_finite_t(ev.get("t_ms")):
                    ev["t_ms"] = float(ev["t_ms"]) + 60000.0
            _write_events(part_dir, events)
            self._n49_expect_unaccredited_or_unreachable(part_dir, "gap_after_load")

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
            # Sol delta r2 BLOQ 2: el rechazo `busy` posterior a la liberacion de A no lo explica ningun censo
            # activo: ese motivo (mas especifico) tiene precedencia sobre el de la readquisicion.
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "census_busy_without_active_holder")
        # (g) tras liberar, el siguiente censo aceptado no queda integro (sin sus job_read): no se acredita la
        # readquisicion
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "third_not_intact")
            events = _read_events(part_dir)
            b_start = self._census_start_results(events, "t0_baseline_census:area_b")[0]
            jr_ids = {
                res["op_id"]
                for ev in events
                if ev.get("ev") == "result"
                for res in ev.get("results") or []
                if res.get("verb") == "job_read" and _unpack(res["read"])[0].get("job") == b_start["op_id"]
            }
            self.assertTrue(jr_ids)
            _write_events(part_dir, _drop_ops(events, jr_ids))
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 2, msg=json.dumps(verdict["checks"]))
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

    # =========================================================================
    # Ronda 4 (Sol sobre el delta): BLOQ 1..3, regresiones test_sol3_NN_*
    # =========================================================================

    @staticmethod
    def _new_hello_index(events: list[dict[str, Any]], builder: "_SyntheticPartBuilder") -> int:
        return next(
            i for i, ev in enumerate(events)
            if ev.get("ev") == "hello" and ev.get("peer") == "server" and ev.get("inst") == builder.server_epoch_new
        )

    def _n49_expect_unaccredited_or_unreachable(self, part_dir: Path, tag: str) -> None:
        """Ninguna variante da PASA: INCONCLUSO (exit 2) y solo PER-07/08 `missing` (sin `fail`)."""
        verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
        self.assertEqual(verdict["exit_code"], 2, msg=f"{tag}:{json.dumps(verdict['checks'])}")
        c_map = _checks_by_id(verdict)
        for cid in ("PER-07", "PER-08"):
            self.assertEqual(c_map[cid]["status"], "missing", msg=f"{tag}:{cid}")
            self.assertTrue(
                c_map[cid]["detail"].startswith("post_restart_creature_coverage_missing"),
                msg=f"{tag}:{cid}:{c_map[cid]['detail']}",
            )
        self.assertEqual(_only_non_pass(verdict), {"PER-07": "missing", "PER-08": "missing"}, msg=tag)

    @staticmethod
    def _to_real_core_result_rows(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Formato REAL del nucleo (bridge_qa.py `result`): un evento por resultado, bajo `result`, sin `verb`
        (fake_peer.py `_done`/`_rejected` no lo llevan)."""
        out: list[dict[str, Any]] = []
        for ev in events:
            if ev.get("ev") == "result" and isinstance(ev.get("results"), list):
                for res in ev["results"]:
                    body = {k: v for k, v in res.items() if k != "verb"}
                    out.append({
                        "ev": "result", "http": 200, "peer": ev.get("peer"), "inst": ev.get("inst"),
                        "op_id": res.get("op_id"), "result": body, "t_ms": ev.get("t_ms"), "body_len": 0,
                    })
            else:
                out.append(ev)
        return out

    def test_sol3_01_core_tap_resolves_verb_from_enq_with_real_core_result_format(self) -> None:
        """Sol delta BLOQ 1 (HONESTA): resultados reales del nucleo (sin `verb`) -> el tap resuelve el verbo por el
        `op_id` y su `enq` registrado: no da `no_real_per_apply_scene_done` y el evaluador da PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "run")
            rows = self._to_real_core_result_rows(_read_events(part_dir))
            self.assertTrue(all("verb" not in (r.get("result") or {}) for r in rows if r.get("ev") == "result"))
            _write_events(part_dir, rows)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
            tap = _CoreTap()
            tap.parts.append({"part_dir": part_dir, "bridge_id": 1, "pids": {"server": 4242, "client": 4343}})
            tap.rows_by_bridge[1] = copy.deepcopy(_read_events(part_dir))
            self.assertEqual(tap.problems(Path(tmp), ["run"]), [])
            # no es vacuo: si el registro no trae el `enq` del per_apply_scene, el verbo no se resuelve
            apply_ids = {r["op_id"] for r in rows if r.get("ev") == "enq" and r.get("verb") == "per_apply_scene"}
            self.assertTrue(apply_ids)
            tap.rows_by_bridge[1] = [
                copy.deepcopy(r) for r in _read_events(part_dir)
                if not (r.get("ev") == "enq" and r.get("op_id") in apply_ids)
            ]
            _write_events(part_dir, tap.rows_by_bridge[1])
            self.assertIn("run:no_real_per_apply_scene_done", tap.problems(Path(tmp), ["run"]))

    def _first_census_by_tag(self, events: list[dict[str, Any]], tag: str) -> dict[str, Any]:
        return self._census_start_results(events, tag)[0]

    def test_sol3_02_census_new_start_while_first_retained_after_release_is_valid(self) -> None:
        """Sol delta BLOQ 2 (HONESTA): A termina y libera el recurso; B arranca antes del `job_free` de A (el trabajo
        sigue retenido). El nucleo libera al terminar (fake_peer.py:316): no es solape ni FALLA en PER-09."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "retained")
            events = _read_events(part_dir)
            a_start = self._first_census_by_tag(events, "t0_baseline_census:area_a")
            b_start = self._first_census_by_tag(events, "t0_baseline_census:area_b")
            a_free_ids = {
                ev["op_id"] for ev in events
                if ev.get("ev") == "enq" and ev.get("verb") == "job_free"
                and _unpack(ev["args"])[0].get("job") == a_start["op_id"]
            }
            self.assertEqual(len(a_free_ids), 1)
            moved = [
                ev for ev in events
                if (ev.get("ev") == "enq" and ev.get("op_id") in a_free_ids)
                or (ev.get("ev") == "poll" and any(o.get("op_id") in a_free_ids for o in ev.get("ops") or []))
                or (ev.get("ev") == "result" and any(r.get("op_id") in a_free_ids for r in ev.get("results") or []))
            ]
            rest = [ev for ev in events if not any(ev is m for m in moved)]
            # el `job_free` de A pasa a ir DESPUES del arranque de B (sus tres eventos juntos)
            b_pos = max(
                i for i, ev in enumerate(rest)
                if ev.get("ev") == "result" and any(r.get("op_id") == b_start["op_id"] for r in ev.get("results") or [])
            )
            events2 = rest[: b_pos + 1] + moved + rest[b_pos + 1:]
            # cambia el orden de los eventos; el reloj del bridge debe seguir siendo monotono
            last_t = 0.0
            for ev in events2:
                if _is_finite_t(ev.get("t_ms")):
                    last_t = max(last_t, float(ev["t_ms"]))
                    ev["t_ms"] = last_t
            _write_events(part_dir, events2)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "pass")

    def test_sol3_03_census_busy_after_declared_release_is_not_contention_proof(self) -> None:
        """Sol delta BLOQ 2 (FABRICACION): A declara la liberacion a 1030 ms y el supuesto `busy` llega a 1040 ms: el
        recurso ya estaba libre, el `busy` no lo explica ningun censo activo -> no PASA (PER-09 `missing`)."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "late_busy")
            events = _read_events(part_dir)
            a_start = self._first_census_by_tag(events, "t0_baseline_census:area_a")
            u_s, u_n, u_r = _unpack(a_start["read"])
            released = float(u_n["snap_tick_ms"]) + 10.0
            for ev in events:
                for res in ev.get("results") or []:
                    if res.get("verb") != "job_read":
                        continue
                    j_s, j_n, j_r = _unpack(res["read"])
                    if j_s.get("job") == a_start["op_id"]:
                        for k in ("end_tick_ms", "onjobend_tick_ms", "released_tick_ms"):
                            j_n[k] = released
                        res["read"] = _repack_read(j_s, j_n, j_r, res["read"])
            busy = next(
                res
                for ev in events
                if ev.get("ev") == "result"
                for res in ev.get("results") or []
                if res.get("verb") == "per_census_start" and res.get("status") == "rejected"
            )
            busy["recv_ms"] = released + 5.0
            busy["done_ms"] = released + 10.0  # despues de la liberacion declarada
            _write_events(part_dir, events)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertNotEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
            self.assertNotEqual(_checks_by_id(verdict)["PER-09"]["status"], "pass")
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["detail"], "census_busy_without_active_holder")

    def test_sol3_02b_census_reacquired_after_release_while_first_job_still_retained_pasa(self) -> None:
        """Sol delta r2 BLOQ 1 (HONESTA): el `job_free` del primer censo se retrasa hasta justo antes del ultimo
        `per_status` viejo; los censos siguientes arrancan tras `released_tick_ms` con A aun retenido. La
        readquisicion se acredita por `released_tick_ms`, no por `job_free`: PER-09 pasa."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "long_retention")
            events = _read_events(part_dir)
            a_start = self._first_census_by_tag(events, "t0_baseline_census:area_a")
            a_free_ids = {
                ev["op_id"] for ev in events
                if ev.get("ev") == "enq" and ev.get("verb") == "job_free"
                and _unpack(ev["args"])[0].get("job") == a_start["op_id"]
            }
            self.assertEqual(len(a_free_ids), 1)
            moved = [
                ev for ev in events
                if (ev.get("ev") == "enq" and ev.get("op_id") in a_free_ids)
                or (ev.get("ev") == "poll" and any(o.get("op_id") in a_free_ids for o in ev.get("ops") or []))
                or (ev.get("ev") == "result" and any(r.get("op_id") in a_free_ids for r in ev.get("results") or []))
            ]
            self.assertEqual(len(moved), 3)
            rest = [ev for ev in events if not any(ev is m for m in moved)]
            old_status_ids = _status_op_ids(events, builder.server_epoch_old)
            last_old_status = old_status_ids[-1]
            pos = next(
                i for i, ev in enumerate(rest)
                if ev.get("ev") == "enq" and ev.get("op_id") == last_old_status
            )
            prev_res = next(ev for ev in reversed(rest[:pos]) if ev.get("ev") == "result")
            base_t = float(prev_res["t_ms"]) + 100.0
            base_h = float(prev_res["results"][0]["done_ms"]) + 100.0
            enq_ev, poll_ev, res_ev = moved
            for ev, dt in ((enq_ev, 0.0), (poll_ev, 0.0), (res_ev, 20.0)):
                ev["t_ms"] = base_t + dt
                ev["h_ms"] = base_h + dt
            res_ev["results"][0]["recv_ms"] = base_h
            res_ev["results"][0]["done_ms"] = base_h + 20.0
            events2 = rest[:pos] + moved + rest[pos:]
            _write_events(part_dir, events2)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
            self.assertEqual(_checks_by_id(verdict)["PER-09"]["status"], "pass")

    def test_sol3_03b_valid_busy_does_not_cover_impossible_busy(self) -> None:
        """Sol delta r2 BLOQ 2 (FABRICACION): ademas del `busy` valido, un segundo `per_census_start -> rejected/busy`
        con todos los censos t0 ya completados y liberados (antes del primer apply, recv=done=1540) no lo explica
        ningun censo activo: otra prueba valida no lo tapa -> PER-09 no pasa, con el motivo concreto."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "second_busy")
            events = _read_events(part_dir)
            busy_enq = next(
                ev for ev in events if ev.get("ev") == "enq" and ev.get("verb") == "per_census_start"
                and _unpack(ev["args"])[0].get("area_tag", "").startswith("contention_probe")
            )
            busy_poll = next(
                ev for ev in events if ev.get("ev") == "poll"
                and any(o.get("op_id") == busy_enq["op_id"] for o in ev.get("ops") or [])
            )
            busy_res = next(
                ev for ev in events if ev.get("ev") == "result"
                and any(r.get("op_id") == busy_enq["op_id"] for r in ev.get("results") or [])
            )
            new_id = f"{builder.nonce}-900"
            first_apply = next(i for i, ev in enumerate(events) if ev.get("ev") == "enq" and ev.get("verb") == "per_apply_scene")
            t0 = float(events[first_apply - 1]["t_ms"])
            clones = []
            for ev, dt in ((busy_enq, 0.0), (busy_poll, 0.0), (busy_res, 20.0)):
                c = copy.deepcopy(ev)
                c["t_ms"] = t0 + dt
                if "h_ms" in c:
                    c["h_ms"] = 1540.0 + dt
                if c.get("ev") == "enq":
                    c["op_id"] = new_id
                elif c.get("ev") == "poll":
                    for o in c["ops"]:
                        o["op_id"] = new_id
                else:
                    r = c["results"][0]
                    r["op_id"] = new_id
                    r["recv_ms"] = 1540.0
                    r["done_ms"] = 1540.0
                clones.append(c)
            events2 = events[:first_apply] + clones + events[first_apply:]
            _write_events(part_dir, events2)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            c_map = _checks_by_id(verdict)
            self.assertNotEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))
            self.assertIn(c_map["PER-09"]["status"], ("missing", "fail"))
            self.assertEqual(c_map["PER-09"]["detail"], "census_busy_without_active_holder")

    def test_sol3_04_n49_clocks_of_new_epoch_and_bridge_shifted_60s_not_pasa(self) -> None:
        """Sol delta BLOQ 3: relojes del epoch nuevo y del bridge desplazados 60 s (primera lectura a ~90300 ms): se
        cuenta toda la ventana sin observacion, no solo `hello -> primera lectura` -> INCONCLUSO, nunca PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "shift60")
            events = _read_events(part_dir)
            for ev in events[self._new_hello_index(events, builder):]:
                if _is_finite_t(ev.get("t_ms")):
                    ev["t_ms"] = float(ev["t_ms"]) + 60000.0
            # Sol delta r2 MEN: tambien los ticks del peer nuevo (su reloj desde el arranque del proceso)
            self._shift_new_epoch_peer_ticks(events, builder.server_epoch_new, 60000.0)
            _write_events(part_dir, events)
            self._n49_expect_unaccredited_or_unreachable(part_dir, "shift60")

    @staticmethod
    def _shift_new_epoch_peer_ticks(events: list[dict[str, Any]], inst: str, delta_ms: float) -> None:
        """Desplaza los ticks del peer del epoch nuevo (h_ms de hello/poll/result, recv/done de cada resultado y los
        `*_tick_ms` de sus lecturas); no toca el reloj del bridge (`t_ms`)."""
        for ev in events:
            if ev.get("inst") != inst:
                continue
            if "h_ms" in ev:
                ev["h_ms"] = float(ev["h_ms"]) + delta_ms
            for res in ev.get("results") or []:
                for k in ("recv_ms", "done_ms"):
                    if k in res:
                        res[k] = float(res[k]) + delta_ms
                _shift_result_time_fields(res, delta_ms)

    def test_sol3_04b_n49_restart_60s_initial_age_59s_discs_600m_not_pasa_1000m_pasa(self) -> None:
        """Sol delta r2 MEN: reinicio de 60 s y edad inicial de 59 s del proceso nuevo. La ventana sin observacion
        posterior cuenta desde el ARRANQUE del proceso (tick_ms 0), no desde su primera lectura: con discos t5 de
        600 m no se cubre a la criatura -> INCONCLUSO; con discos de 1000 m si -> PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder(
                "run", restart_gap_ms=60000.0, new_epoch_tick0_ms=59000.0, t5_radius_m=600.0,
            )
            part_dir = builder.build_into(Path(tmp) / "r600")
            self._n49_expect_unaccredited_or_unreachable(part_dir, "sol3_04b_600")
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder(
                "run", restart_gap_ms=60000.0, new_epoch_tick0_ms=59000.0, t5_radius_m=1000.0,
            )
            part_dir = builder.build_into(Path(tmp) / "r1000")
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(verdict["exit_code"], 0, msg=json.dumps(verdict["checks"]))

    def test_sol3_05_n49_complete_silence_before_restart_not_pasa(self) -> None:
        """Sol delta BLOQ 3: silencio completo del peer viejo tras su ultima lectura (ni un keepalive) -> la parada
        no se acredita -> `N49_extremes_unaccredited`, nunca PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run", old_keepalive_after_stop=False)
            part_dir = builder.build_into(Path(tmp) / "silence")
            self._n49_expect_unaccredited(part_dir, "sol3_05")

    def test_sol3_06_n49_event_of_new_epoch_before_its_hello_not_pasa(self) -> None:
        """Sol delta BLOQ 3 (negativa anterior al `hello`): un evento del epoch nuevo con reloj anterior a su hello
        -> la carga no se acredita -> INCONCLUSO."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "pre_hello")
            events = _read_events(part_dir)
            i = self._new_hello_index(events, builder)
            hello_t = float(events[i]["t_ms"])
            events.insert(i, {
                "ev": "keepalive", "peer": "server", "inst": builder.server_epoch_new, "http": 200, "n_ops": 0,
                "body_len": 24, "t_ms": hello_t - 5.0,
            })
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "sol3_06")
        # variante: el resultado del primer per_status nuevo lleva un reloj anterior al hello
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "first_read_before_hello")
            events = _read_events(part_dir)
            first_new = _status_op_ids(events, builder.server_epoch_new)[0]
            hello_t = float(events[self._new_hello_index(events, builder)]["t_ms"])
            for ev in events:
                if ev.get("ev") == "result" and any(r.get("op_id") == first_new for r in ev.get("results") or []):
                    ev["t_ms"] = hello_t - 1.0
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "sol3_06b")

    def test_sol3_07_n49_old_peer_without_keepalive_after_last_reading_not_pasa(self) -> None:
        """Sol delta BLOQ 3 (negativa sin `keepalive`): el peer viejo solo deja eventos que no son un keepalive/poll 200
        tras su ultima lectura (aqui un keepalive caido, http 503) -> no se acredita su vida -> INCONCLUSO."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "no_keepalive")
            events = _read_events(part_dir)
            n = 0
            for ev in events:
                if ev.get("ev") == "keepalive" and ev.get("inst") == builder.server_epoch_old:
                    ev["http"] = 503
                    n += 1
            self.assertEqual(n, 1)
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "sol3_07")

    def test_sol3_08_n49_old_peer_alive_after_new_hello_not_pasa(self) -> None:
        """Sol delta BLOQ 3: un evento del peer viejo en o despues del hello nuevo (dos mundos a la vez) -> INCONCLUSO."""
        with tempfile.TemporaryDirectory() as tmp:
            builder = _SyntheticPartBuilder("run")
            part_dir = builder.build_into(Path(tmp) / "two_worlds")
            events = _read_events(part_dir)
            i = self._new_hello_index(events, builder)
            hello_t = float(events[i]["t_ms"])
            events.insert(i + 1, {
                "ev": "keepalive", "peer": "server", "inst": builder.server_epoch_old, "http": 200, "n_ops": 0,
                "body_len": 24, "t_ms": hello_t + 10.0,
            })
            _write_events(part_dir, events)
            self._n49_expect_unaccredited(part_dir, "sol3_08")

    # =========================================================================
    # E9: enmienda del oraculo. (A) PER-09 sin FALLA falso por causa tecnica del director o de un censo t5;
    # (B) PER-07/PER-08 exigen el mismo PERSONAJE del director (y un ancla de identidad); (C) purga de arranque
    # acreditada con `per_purge_read` en PER-08 (brief, enmienda del 2026-11-17).
    # =========================================================================

    _E9_MUT_FAULTS = {"run": "", "mut-foreign_wiped": "reset_wipe_radius_25m", "mut-unprotected_leak": "omit_nopersistency_flag"}

    def _e9_build(self, tmp: str, part: str = "run", name: str = "p", **kw: Any) -> tuple["_SyntheticPartBuilder", Path]:
        builder = _SyntheticPartBuilder(part, fault_code=self._E9_MUT_FAULTS[part], **kw)
        return builder, builder.build_into(Path(tmp) / name)

    @staticmethod
    def _e9_results(events: list[dict[str, Any]], verb: str, status: str | None = "done") -> Iterable[dict[str, Any]]:
        """Resultados de bridge del verbo ``verb`` (con ese estado; ``None`` = cualquiera), en orden de evidencia."""
        for ev in events:
            if ev.get("ev") == "result":
                yield from (r for r in ev.get("results") or [] if r.get("verb") == verb and status in (None, r.get("status")))

    @staticmethod
    def _e9_page(res: dict[str, Any]) -> types.SimpleNamespace:
        """La lectura empaquetada de ``res`` como un objeto editable: ``.strs``, ``.nums`` y ``.rows``."""
        strs, nums, rows = _unpack(res["read"])
        return types.SimpleNamespace(strs=strs, nums=nums, rows=rows)

    @staticmethod
    def _e9_store(res: dict[str, Any], page: types.SimpleNamespace) -> None:
        res["read"] = _repack_read(page.strs, page.nums, page.rows, res["read"])

    @staticmethod
    def _e9_director_rows(page: types.SimpleNamespace, builder: "_SyntheticPartBuilder") -> list[dict[str, Any]]:
        return [row for row in page.rows if row["owner_uid"] == builder.director_uid]

    def _e9_jobs_of(self, events: list[dict[str, Any]], tags: set[str]) -> dict[str, str]:
        """``{job_id: area_tag}`` de los censos aceptados cuya etiqueta esta en ``tags``."""
        pages = (self._e9_page(res) for res in self._e9_results(events, "per_census_start"))
        return {pg.strs["job"]: pg.strs["area_tag"] for pg in pages if pg.strs.get("area_tag", "") in tags}

    def _e9_edit_start_reads(self, part_dir: Path, tags: set[str], edit: Any) -> None:
        events = _read_events(part_dir)
        done = 0
        for res in self._e9_results(events, "per_census_start"):
            page = self._e9_page(res)
            if page.strs.get("area_tag", "") not in tags:
                continue
            edit(page)
            self._e9_store(res, page)
            done += 1
        self.assertEqual(done, len(tags), msg=f"census starts edited: {tags}")
        _write_events(part_dir, events)

    def _e9_edit_pages(self, part_dir: Path, tags: set[str], edit: Any) -> None:
        events = _read_events(part_dir)
        jobs = self._e9_jobs_of(events, tags)
        self.assertEqual(len(jobs), len(tags), msg=f"census jobs found: {tags}")
        done = 0
        for res in self._e9_results(events, "job_read"):
            page = self._e9_page(res)
            if page.strs.get("job", "") not in jobs:
                continue
            edit(page)
            self._e9_store(res, page)
            done += 1
        self.assertTrue(done, msg=f"no census page edited: {tags}")
        _write_events(part_dir, events)

    def _e9_director_gone(self, part_dir: Path, areas: tuple[str, ...], *, present: int, readable: int) -> None:
        def edit(page: types.SimpleNamespace) -> None:
            page.nums.update(director_present_b=float(present), director_alive_b=float(present),
                             director_inv_readable_b=float(readable))
            if not present:
                page.strs["director_uid"] = ""

        self._e9_edit_start_reads(part_dir, {f"t5_post_restart_census:{a}" for a in areas}, edit)

    def _e9_census_down(self, part_dir: Path, tag: str, how: str) -> None:
        """Cae el censo ``tag`` por causa tecnica: ``failed`` / ``expired`` / ``stopped`` (estado de sus paginas) o
        ``absent`` (todas sus ordenes desaparecen)."""
        if how == "absent":
            events = _read_events(part_dir)
            ops = self._t6_census_op_ids(events, tag)
            self.assertGreaterEqual(len(ops), 3, msg=tag)
            _write_events(part_dir, _drop_ops(events, ops))
            return

        def edit(page: types.SimpleNamespace) -> None:
            page.strs.update(state=how, reason="lease_expired" if how == "expired" else "")

        self._e9_edit_pages(part_dir, {tag}, edit)

    def _e9_director_row(self, builder: "_SyntheticPartBuilder", cls: str, net_id: str, pers_id: str, slot: str) -> dict[str, Any]:
        return self._t6_row(
            class_name=cls, loc_kind="attachment", parent_class="SurvivorM_Mirek", parent_net_id="1:2", slot_name=slot,
            owner_uid=builder.director_uid, net_id=net_id, pers_id=pers_id, ai_agent_b=0.0, max_hp=100.0,
            health_hp=100.0, inv_children_n=0.0,
        )

    def _e9_add_rows_to_census(self, part_dir: Path, tag: str, extra: list[dict[str, Any]]) -> None:
        """Anade filas a la ultima pagina del censo ``tag`` y ajusta sus contadores."""
        events = _read_events(part_dir)
        jobs = self._e9_jobs_of(events, {tag})
        self.assertEqual(list(jobs.values()), [tag])
        done_pages = 0
        for ev in events:
            if ev.get("ev") != "result":
                continue
            for res in ev.get("results") or []:
                if res.get("status") != "done" or res.get("verb") not in ("per_census_start", "job_read"):
                    continue
                u_s, u_n, u_r = _unpack(res["read"])
                if res.get("verb") == "per_census_start" and u_s.get("job") in jobs:
                    u_n["rows_captured_n"] += len(extra)
                    u_n["director_inv_count_n"] += len(extra)
                    res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
                elif res.get("verb") == "job_read" and u_s.get("job") in jobs:
                    u_n["rows_total_n"] += len(extra)
                    if int(round(u_n["page_n"])) == int(round(u_n["pages_n"])) - 1:
                        u_r.extend(copy.deepcopy(extra))
                        done_pages += 1
                    res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
        self.assertEqual(done_pages, 1, msg=tag)
        _write_events(part_dir, events)

    def _e9_swap_director_pers_ids(self, part_dir: Path, builder: "_SyntheticPartBuilder", areas: tuple[str, ...],
                                   only_class: str = "") -> None:
        """Deja al director de t5 de las ``areas`` con ``pers_id`` nuevos (personaje nuevo del mismo jugador)."""
        serial = iter(range(1, 10_000))

        def edit(page: types.SimpleNamespace) -> None:
            for row in self._e9_director_rows(page, builder):
                if only_class in ("", row["class_name"]):
                    k = next(serial)
                    row["pers_id"] = f"{1900000 + k}:{-2900000 - k}:{3900000 + k}:{-1100000 - k}"

        self._e9_edit_pages(part_dir, {f"t5_post_restart_census:{a}" for a in areas}, edit)

    # O2: la purga la ordena el runner (`per_purge_start`); estos ayudantes sustituyen a los de `per_purge_read`.
    def _e9_purge_reads(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resultados `job_read` del trabajo de purga, en orden de evidencia."""
        jobs = {res["op_id"] for res in self._e9_results(events, "per_purge_start", None)}
        return [res for res in self._e9_results(events, "job_read") if self._e9_page(res).strs.get("job") in jobs]

    def _e9_edit_purge_reads(self, part_dir: Path, edit: Any, *, terminal_only: bool = True) -> None:
        events = _read_events(part_dir)
        n = 0
        for res in self._e9_purge_reads(events):
            page = self._e9_page(res)
            if terminal_only and page.strs.get("state") == "running":
                continue
            edit(page)
            self._e9_store(res, page)
            n += 1
        self.assertTrue(n, msg="no purge job_read edited")
        _write_events(part_dir, events)

    @staticmethod
    def _e9_purge_rows(part_dir: Path) -> list[dict[str, Any]]:
        """Filas del trabajo de purga leidas de las paginas terminales (para afirmar sobre la evidencia)."""
        events = _read_events(part_dir)
        jobs = {r["op_id"] for ev in events if ev.get("ev") == "result" for r in ev["results"] if r["verb"] == "per_purge_start"}
        pages: dict[int, list[dict[str, Any]]] = {}
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("verb") == "job_read" and res.get("status") == "done":
                    u_s, u_n, u_r = _unpack(res["read"])
                    if u_s.get("job") in jobs and u_s.get("state") != "running":
                        pages[int(round(u_n["page_n"]))] = u_r
        return [row for p in sorted(pages) for row in pages[p]]

    @staticmethod
    def _e9_first_t5_start_tick(part_dir: Path) -> float:
        ticks = []
        for ev in _read_events(part_dir):
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("verb") == "per_census_start" and res.get("status") == "done":
                    u_s, u_n, _ = _unpack(res["read"])
                    if u_s.get("area_tag", "").startswith("t5_post_restart_census:"):
                        ticks.append(float(u_n["snap_tick_ms"]))
        return min(ticks)

    def _e9_expect(self, verdict: dict[str, Any], expected: dict[str, str], msg: str, **details: str) -> None:
        self.assertEqual(_only_non_pass(verdict), expected, msg=msg)
        statuses = set(expected.values())
        self.assertEqual(verdict["exit_code"], 1 if "fail" in statuses else (2 if statuses else 0), msg=msg)
        c_map = _checks_by_id(verdict)
        for cid, needle in details.items():
            self.assertIn(needle, c_map[cid.replace("_", "-")]["detail"], msg=f"{msg}: {cid}={c_map[cid.replace('_', '-')]['detail']}")

    # ---- (A) PER-09 -------------------------------------------------------

    def test_e9_a_director_gone_in_t5_is_missing_not_fail(self) -> None:
        """Hallazgo A, brief :309 (la fila de PER-09 no exige nada del director) y :295 (missing -> exit 2):
        director ausente o inventario ilegible en t5 -> PER-09 `missing`, nunca `fail`."""
        variants = (
            ("absent_both_areas", "run", ("area_a", "area_b"), 0, 0,
             {"PER-07": "missing", "PER-08": "missing", "PER-09": "missing"}),
            ("inventory_unreadable_area_b", "run", ("area_b",), 1, 0, {"PER-08": "missing", "PER-09": "missing"}),
            ("absent_area_a_only", "run", ("area_a",), 0, 0, {"PER-07": "missing", "PER-09": "missing"}),
        )
        for name, part, areas, present, readable, expected in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, part, name)
                    self._e9_director_gone(part_dir, areas, present=present, readable=readable)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, expected, name)
                    detail = _checks_by_id(verdict)["PER-09"]["detail"]
                    for a in areas:
                        self.assertIn(f"t5_director_unreadable:{a}", detail, msg=name)

    def test_e9_a_director_gone_in_t5_of_a_mutant_part_is_missing_not_fail(self) -> None:
        """Hallazgo A en las partes mutantes: el `missing` de PER-09 no tapa el `fail` propio de la mutacion, y no se
        crea ningun `fail` nuevo."""
        # (con el director ausente la puerta de PER-08 da `missing` antes que el `fail` propio del mutante `leak`)
        mutants = (
            ("mut-foreign_wiped", {"PER-04": "fail", "PER-05": "fail"}),
            ("mut-unprotected_leak", set()),
        )
        for part, own in mutants:
            with self.subTest(part):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, part, part)
                    self._e9_director_gone(part_dir, ("area_a", "area_b"), present=0, readable=0)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-09"]["status"], "missing", msg=part)
                    self.assertIn("t5_director_unreadable:area_a", c_map["PER-09"]["detail"], msg=part)
                    fails = {cid for cid, c in c_map.items() if c["status"] == "fail"}
                    self.assertEqual(fails, set(own), msg=part)

    def test_e9_a_t5_census_down_by_technical_cause_is_missing_not_fail(self) -> None:
        """Hallazgo A: censo t5 de un area obligatoria `failed` / `expired` / `stopped` o ausente -> PER-09 `missing`."""
        variants = (
            ("area_b_failed", "area_b", "failed"),
            ("area_b_expired", "area_b", "expired"),
            ("area_a_stopped", "area_a", "stopped"),
            ("area_b_absent", "area_b", "absent"),
        )
        for name, area, how in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)
                    self._e9_census_down(part_dir, f"t5_post_restart_census:{area}", how)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-09"]["status"], "missing", msg=name)
                    self.assertIn(f"t5_missing_census:{area}", c_map["PER-09"]["detail"], msg=name)
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=json.dumps(_only_non_pass(verdict)))
                    self.assertEqual(verdict["exit_code"], 2, msg=name)

    def test_e9_a_director_not_included_where_matrix_requires_it_still_fails(self) -> None:
        """Hallazgo A (negativa de la regla): `include_director_b = 0` donde :234 lo exige sigue en `fail`, tambien
        cuando ademas el director no esta."""
        variants = (
            ("area_b_include0", ("area_b",), 1, 1),
            ("area_a_include0_and_director_absent", ("area_a",), 0, 0),
            ("both_areas_include0", ("area_a", "area_b"), 1, 1),
        )
        for name, areas, present, readable in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)

                    def edit(page: types.SimpleNamespace) -> None:
                        page.nums.update(include_director_b=0.0, director_present_b=float(present),
                                         director_inv_readable_b=float(readable))

                    self._e9_edit_start_reads(part_dir, {f"t5_post_restart_census:{a}" for a in areas}, edit)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-09"]["status"], "fail", msg=name)
                    for a in areas:
                        self.assertIn(f"t5_director_not_included:{a}", c_map["PER-09"]["detail"], msg=name)
                    self.assertEqual(verdict["exit_code"], 1, msg=name)

    def test_e9_a_real_per09_fail_overrides_the_t5_missing(self) -> None:
        """Hallazgo A (regla 4): con el director ausente en t5, un `fail` real de PER-09 manda y su parte se sigue
        evaluando: testigo cambiado, `stale_epoch` no rechazado, supervivientes en t6."""
        for name in ("witness_changed", "stale_reset_not_rejected", "t6_survivor", "census_down_and_survivor"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    self._e9_director_gone(part_dir, ("area_b",), present=0, readable=0)
                    if name == "witness_changed":
                        self._set_census_pers_id(part_dir, builder, "t5_witness_post_census:area_b", "b_prop_1", "7:7:7:7")
                        needle = "witness_entity_changed:"
                    elif name == "stale_reset_not_rejected":
                        events = _read_events(part_dir)
                        n = 0
                        for ev in events:
                            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                                if (
                                    ev.get("inst") == builder.server_epoch_new
                                    and res.get("verb") == "per_reset_scene"
                                    and res.get("status") == "rejected"
                                ):
                                    res["reason"] = "busy"
                                    n += 1
                        self.assertEqual(n, 1)
                        _write_events(part_dir, events)
                        needle = "stale_reset_not_rejected"
                    else:
                        if name == "census_down_and_survivor":
                            self._e9_census_down(part_dir, "t5_post_restart_census:area_a", "failed")
                        self._add_t6_rows(part_dir, builder, "area_c", [self._t6_row(
                            class_name="Barrel_Yellow", ai_agent_b=0.0, max_hp=1300.0, health_hp=1300.0 * 0.845)])
                        needle = "t6_cleanup_survivors:Barrel_Yellow:1:8001"
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-09"]["status"], "fail", msg=name)
                    self.assertIn(needle, c_map["PER-09"]["detail"], msg=name)
                    self.assertNotIn("t5_director_unreadable", c_map["PER-09"]["detail"], msg=name)
                    self.assertEqual(verdict["exit_code"], 1, msg=name)

    def test_e9_a_equivalent_of_the_real_run_director_unreadable_and_t6_discs_absent(self) -> None:
        """Hallazgo A, positiva: equivalente sintetico de `run_20261117T194421Z` (director ilegible en t5 y censos t6
        de los discos ausentes o caidos) -> PER-09 `missing` (con `t6_cleanup_census_absent`), exit 2."""
        disc = "t5_track_b_inf_1_t2"
        for name in ("disc_t6_absent", "disc_t6_failed", "disc_t6_absent_and_base_t6_absent"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, creature_far_move_m=75.0, include_t5_track_disks=True)
                    self._e9_director_gone(part_dir, ("area_a", "area_b"), present=0, readable=0)
                    self._e9_census_down(part_dir, f"t6_post_cleanup_census:{disc}", "absent" if "absent" in name else "failed")
                    if name.endswith("base_t6_absent"):
                        self._e9_census_down(part_dir, "t6_post_cleanup_census:area_c", "absent")
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-09"]["status"], "missing", msg=name)
                    self.assertTrue(c_map["PER-09"]["detail"].startswith("t6_cleanup_census_absent:"), msg=name)
                    self.assertIn(disc, c_map["PER-09"]["detail"], msg=name)
                    self.assertIn("t5_director_unreadable:area_a", c_map["PER-09"]["detail"], msg=name)
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)
                    self.assertEqual(verdict["exit_code"], 2, msg=name)
                    self.assertEqual(verdict["verdict"], "INCONCLUSO", msg=name)

    # ---- (B) PER-07 / PER-08: mismo personaje del director -------------------

    def test_e9_b_director_replaced_by_a_new_character_is_missing_not_pass(self) -> None:
        """Hallazgo B, brief :307, :308, :28 y :276: mismo `director_uid` pero ningun `pers_id` de la linea base de t0
        en el director de t5 -> PER-07 / PER-08 `missing` (`director_character_replaced`).

        O2 (Sol 2 sobre 433d535): se quita la variante `one_baseline_item_gone_in_unreset_branch` (la Apple con otro
        `pers_id` y los Jeans con el suyo). Exigia que sobreviviera todo el basal: es el INCONCLUSO falso de Sol 2. El
        caso pasa ahora a `test_pos_o2_sol2_consumed_or_swapped_baseline_item_keeps_the_same_character` (PASA)."""
        variants = (
            ("both_branches", ("area_a", "area_b"), "", {"PER-07": "missing", "PER-08": "missing"}),
            ("reset_branch_only", ("area_a",), "", {"PER-07": "missing"}),
            ("unreset_branch_only", ("area_b",), "", {"PER-08": "missing"}),
        )
        for name, areas, only_class, expected in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    self._e9_swap_director_pers_ids(part_dir, builder, areas, only_class)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self._e9_expect(verdict, expected, name)
                    for cid in expected:
                        self.assertEqual(c_map[cid]["detail"], "director_character_replaced", msg=f"{name}:{cid}")

    def test_e9_b_replaced_character_in_the_mutant_part_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            builder, part_dir = self._e9_build(tmp, "mut-unprotected_leak", "leak")
            self._e9_swap_director_pers_ids(part_dir, builder, ("area_a", "area_b"))
            c_map = _checks_by_id(s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT))
            for cid in ("PER-07", "PER-08"):
                self.assertEqual((c_map[cid]["status"], c_map[cid]["detail"]), ("missing", "director_character_replaced"), msg=cid)

    def test_e9_b_reloaded_character_keeps_passing_and_reappeared_gloves_keep_failing(self) -> None:
        """Hallazgo B, controles: personaje recargado (los mismos `pers_id`, `net_id` nuevos como al reiniciar) ->
        PASA; guantes que reaparecen en el director recargado -> `fail` como antes.

        O2 (brief, secciones finales, `:582` y arbitraje 6): el remanente se juzga por identidad, no por clase. Los
        guantes que reaparecen llevan ahora el `pers_id` acreditado (el de la prenda QA): antes llevaban uno inventado,
        que con el contrato nuevo es una centinela sin atribuir (`missing`, lo cubre
        `test_e9_c_sentinel_garment_still_in_the_director_after_the_purge_fails`)."""
        def reload_net_ids(builder: "_SyntheticPartBuilder", part_dir: Path) -> None:
            def edit(page: types.SimpleNamespace) -> None:
                for row in self._e9_director_rows(page, builder):
                    row["net_id"] = f"2:{row['net_id'].split(':')[1]}0"
                    if row.get("parent_net_id") == "1:10":
                        row["parent_net_id"] = "2:100"

            self._e9_edit_pages(part_dir, {"t5_post_restart_census:area_a", "t5_post_restart_census:area_b"}, edit)

        cases = (
            ("reloaded_only", None, {}),
            ("yellow_gloves_back_in_unreset_branch", ("area_b", "b_act_1_gloves_dir", "Gloves"),
             {"PER-08": "fail"}),
            ("beige_gloves_back_in_reset_branch", ("area_a", "ac_act_1_gloves_dir", "Gloves"),
             {"PER-07": "fail", "PER-08": "fail"}),
        )
        for name, extra, expected in cases:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    reload_net_ids(builder, part_dir)
                    if extra:
                        area, lid, slot = extra
                        glove = builder.entities_by_lid[lid]
                        self._e9_add_rows_to_census(
                            part_dir, f"t5_post_restart_census:{area}",
                            [self._e9_director_row(builder, glove["class_name"], "2:9001", glove["pers_id"], slot)],
                        )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, expected, name)
                    c_map = _checks_by_id(verdict)
                    if name == "yellow_gloves_back_in_unreset_branch":
                        self.assertIn("purge_remnant:b_act_1_gloves_dir", c_map["PER-08"]["detail"])
                    if name == "beige_gloves_back_in_reset_branch":
                        self.assertIn("reappeared_director_gloves:WorkingGloves_Beige", c_map["PER-07"]["detail"])
                        self.assertIn("purge_remnant:ac_act_1_gloves_dir", c_map["PER-08"]["detail"])

    def test_e9_b_unanchored_identity_is_missing_not_pass(self) -> None:
        """Hallazgo B (ancla): si la linea base de `pers_id` del director en t0 queda vacia (ninguno valido, o todos
        `0:0:0:0`) PER-07 y PER-08 no pueden saltarse la comprobacion: `missing` (`director_identity_unanchored`)."""
        for name, bad in (("all_zero", "0:0:0:0"), ("not_a_pers_id", "garbage"), ("empty", "")):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)

                    def edit(page: types.SimpleNamespace) -> None:
                        for row in self._e9_director_rows(page, builder):
                            row["pers_id"] = bad

                    # el director sin pers_id utilizable en t0 (y, como el motor lo haria, en todas las etapas)
                    tags = {f"{stage}:area_a" for stage in (
                        "t0_baseline_census", "t1_pre_transition_census", "t1_post_transition_census",
                        "t3_pre_reset_census", "t3_post_reset_census", "t5_post_restart_census")}
                    tags |= {"t0_baseline_census:area_a", "t5_post_restart_census:area_b", "t3_post_reset_census:area_b",
                             "t3_pre_reset_census:area_b", "t1_pre_transition_census:area_b", "t1_post_transition_census:area_b"}
                    self._e9_edit_pages(part_dir, tags, edit)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    for cid in ("PER-07", "PER-08"):
                        self.assertEqual(
                            (c_map[cid]["status"], c_map[cid]["detail"]), ("missing", "director_identity_unanchored"),
                            msg=f"{name}:{cid}:{_only_non_pass(verdict)}")
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)
                    self.assertEqual(verdict["exit_code"], 2, msg=name)

    def test_e9_b_one_valid_anchor_is_enough_to_anchor(self) -> None:
        """Control del ancla: con UN `pers_id` valido en la linea base (y el otro a cero) el director queda anclado y
        sigue en PASA si ese `pers_id` persiste."""
        with tempfile.TemporaryDirectory() as tmp:
            builder, part_dir = self._e9_build(tmp, "run", "one_anchor")

            def edit(page: types.SimpleNamespace) -> None:
                for row in self._e9_director_rows(page, builder):
                    if row["class_name"] == "Apple":
                        row["pers_id"] = "0:0:0:0"

            tags = {f"{stage}:{a}" for stage in (
                "t0_baseline_census", "t1_pre_transition_census", "t1_post_transition_census", "t3_pre_reset_census",
                "t3_post_reset_census", "t5_post_restart_census") for a in ("area_a",)}
            tags |= {"t5_post_restart_census:area_b", "t3_post_reset_census:area_b", "t3_pre_reset_census:area_b",
                     "t1_pre_transition_census:area_b", "t1_post_transition_census:area_b"}
            self._e9_edit_pages(part_dir, tags, edit)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            c_map = _checks_by_id(verdict)
            self.assertEqual((c_map["PER-07"]["status"], c_map["PER-08"]["status"]), ("pass", "pass"), msg=json.dumps(_only_non_pass(verdict)))

    # ---- (C) la purga que ordena el runner (PER-08, brief, secciones finales del 2026-11-22) ------
    # O2: estos seis tests juzgaban `per_purge_read` (enmienda del 2026-11-17, `:503-514`), que el contrato nuevo
    # quita. Se reescriben con el trabajo `per_purge_start`, conservando lo que cada uno protegia.

    def test_e9_c_honest_purge_record_passes(self) -> None:
        """La evidencia sana lleva la purga honesta: orden igual a las acreditadas (los dos guantes, tambien el que
        borro el reset de t3), acuse con `pre_n`, `done` antes del primer censo t5, las bajas de los guantes que volvieron
        con el personaje (fila `pre`) y una fila `result` por autorizado. Sigue en PASA tambien si vuelve un solo guante
        o ninguno (`result = absent`)."""
        for name, returning, results in (
            ("two_gloves", None, ["deleted", "deleted"]),
            ("one_glove", ("b_act_1_gloves_dir",), ["absent", "deleted"]),
            ("nothing_returns", (), ["absent", "absent"]),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_returning=returning)
                    order = list(self._e9_results(_read_events(part_dir), "per_purge_start"))
                    self.assertEqual(len(order), 1)
                    o_s, o_n, _o_rows = _unpack(order[0]["read"])
                    self.assertEqual((o_s["state"], o_s["resource"]), ("running", "per_purge"))
                    self.assertEqual(o_n["pre_n"], float(sum(1 for r in self._e9_purge_rows(part_dir) if r["phase"] == "pre")))
                    rows = self._e9_purge_rows(part_dir)
                    self.assertEqual([r["result"] for r in rows if r["phase"] == "result"], results)
                    pre_pids = {r["pers_id"] for r in rows if r["phase"] == "pre"}
                    for lid in (returning if returning is not None else ("ac_act_1_gloves_dir", "b_act_1_gloves_dir")):
                        # el guante vuelve con el mismo pers_id antes de purgar (MEN 10)
                        self.assertIn(builder.entities_by_lid[lid]["pers_id"], pre_pids)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=name)
                    self.assertEqual(verdict["verdict"], "PASA", msg=name)
                    self.assertEqual(
                        verdict["metrics"]["runner_purge"]["accredited"], ["ac_act_1_gloves_dir", "b_act_1_gloves_dir"]
                    )

    def test_e9_c_no_purge_record_of_the_new_epoch_is_missing(self) -> None:
        """Sin orden `per_purge_start` aceptada del epoch nuevo -> PER-08 `missing`: sin orden, con la orden dirigida
        al epoch viejo o con la orden rechazada."""
        def no_order(_b: Any, plan: dict[str, Any]) -> None:
            plan["send_order"] = False

        def other_instance(_b: Any, plan: dict[str, Any]) -> None:
            # otra instancia que no es la del epoch nuevo (con la vieja, un `enq` tras el hello nuevo cuenta ademas
            # como actividad del mundo viejo y N49 tapa el detalle de la purga)
            plan["enq_inst"] = "srv-epoch-9999"
            plan["order_strings"]["expect_epoch"] = "srv-epoch-9999"

        def rejected(_b: Any, plan: dict[str, Any]) -> None:
            plan["order_status"], plan["order_reason"] = "rejected", "busy"

        for name, hook, needle in (
            ("no_order", no_order, "purge_not_done:no_order"),
            ("order_to_another_instance", other_instance, "purge_order_not_after_restart"),
            ("order_rejected", rejected, "purge_not_done:order_rejected"),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08=needle)

    def test_e9_c_purge_not_done_or_counts_inconsistent_is_missing(self) -> None:
        """Un trabajo que no acaba en `done`, o un recibo incompleto o incoherente -> PER-08 `missing` (`:584`): estado
        `failed` / `expired` / `stopped` o la espera vencida sin estado terminal; una pagina sin leer; `rows_total_n`
        distinto de las filas leidas; `pre_n` distinto de las filas `pre`; un autorizado sin su fila `result`; dos
        bajas del mismo `pers_id`."""
        def state(st: str, reason: str) -> Any:
            def hook(_b: Any, plan: dict[str, Any]) -> None:
                plan["state"], plan["reason"] = st, reason
            return hook

        def unread_page(_b: Any, plan: dict[str, Any]) -> None:
            plan["read_pages"] = False

        def pre_n(_b: Any, plan: dict[str, Any]) -> None:
            plan["pre_n"] = 3

        def no_result_for_yellow(b: Any, plan: dict[str, Any]) -> None:
            yellow = b.entities_by_lid["b_act_1_gloves_dir"]["pers_id"]
            plan["rows"] = [
                r for r in b.honest_purge_rows(plan) if not (r["phase"] == "result" and r["pers_id"] == yellow)
            ]

        def double_baja(b: Any, plan: dict[str, Any]) -> None:
            rows = b.honest_purge_rows(plan)
            emit = next(r for r in rows if r["phase"] == "emit")
            rows.insert(rows.index(emit) + 1, {**emit, "emit_tick_ms": emit["emit_tick_ms"] + 1.0})
            plan["rows"] = rows

        variants = (
            ("failed_lease_expired", state("failed", "lease_expired"), {}, "purge_not_done:failed"),
            ("expired", state("expired", "job_timeout"), {}, "purge_not_done:expired"),
            ("stopped", state("stopped", ""), {}, "purge_not_done:stopped"),
            ("wait_expired_still_running", state("running", ""), {}, "purge_not_done:wait_expired"),
            ("second_page_unread", unread_page, {"baseline_sentinel_glove": True}, "purge_pages_incomplete"),
            ("rows_total_over_rows_read", None, {}, "purge_pages_incomplete"),
            ("pre_n_differs", pre_n, {}, "purge_pre_n_mismatch"),
            ("authorized_without_result_row", no_result_for_yellow, {}, "purge_result_missing_or_repeated"),
            ("two_bajas_same_pers_id", double_baja, {}, "purge_duplicate_baja"),
        )
        for name, hook, kw, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook, **kw)
                    if name == "rows_total_over_rows_read":
                        self._e9_edit_purge_reads(part_dir, lambda pg: pg.nums.update(rows_total_n=pg.nums["rows_total_n"] + 1))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=f"{name}:{_only_non_pass(verdict)}")
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-08"]["status"], "missing", msg=name)
                    self.assertIn(needle, c_map["PER-08"]["detail"], msg=f"{name}:{c_map['PER-08']['detail']}")
                    self.assertEqual(verdict["exit_code"], 2, msg=name)

    def test_e9_c_purge_after_the_first_t5_census_fails(self) -> None:
        """El fin de la purga (`end_tick_ms` del trabajo) mayor o igual que el inicio del primer censo t5 aceptado ->
        PER-08 `fail` (`:581`, `>=` como en `:512`); un fin justo anterior sigue en PASA."""
        timings = (
            ("same_tick_as_first_census", 0.0, False),
            ("after_first_census_before_the_next", 5.0, False),
            ("long_after_all_t5", 1.0e6, False),
            ("one_ms_before_first_census", -1.0, True),
        )
        for name, delta, ok in timings:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)
                    first = self._e9_first_t5_start_tick(part_dir)
                    self._e9_edit_purge_reads(
                        part_dir,
                        lambda pg, end=first + delta: pg.nums.update(end_tick_ms=end, onjobend_tick_ms=end, released_tick_ms=end),
                    )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    if ok:
                        self.assertEqual(_only_non_pass(verdict), {}, msg=name)
                    else:
                        self._e9_expect(verdict, {"PER-08": "fail"}, name, PER_08="purge_not_before_t5_census")

    def test_e9_c_purge_row_of_a_non_sentinel_class_fails(self) -> None:
        """Una baja que la orden no autoriza -> PER-08 `fail` (`:577-578`). Antes se juzgaba por clase no centinela;
        ahora por identidad: un objeto ajeno del director (la camiseta que cogio despues de t0), los Jeans basales o
        la Apple basal."""
        def deleting(cls: str, extra: bool) -> Any:
            def hook(b: Any, plan: dict[str, Any]) -> None:
                if extra:
                    plan["tree"].append({
                        "pers_id": "1600101:-1600102:1600103:-1600104", "class_name": cls, "net_id": "1:9601",
                        "parent_net_id": "1:2", "parent_pers_id": "", "depth_n": 0.0, "owner_uid": b.director_uid,
                    })
                rows = b.honest_purge_rows(plan)
                victim = next(e for e in plan["tree"] if e["class_name"] == cls)
                rows.insert(len(rows) - 1, b.purge_row(
                    "emit", victim, emit_tick_ms=plan["start_tick_ms"] + 400.0, lease_age_ms=500.0, lease_limit_ms=3000.0,
                ))
                plan["rows"] = rows
            return hook

        variants = (
            ("tshirt_added", deleting("TShirt_Green", True), "purge_deleted_unordered:TShirt_Green"),
            ("baseline_jeans_deleted", deleting("Jeans_Blue", False), "purge_deleted_baseline:Jeans_Blue"),
            ("only_apple_deleted", deleting("Apple", False), "purge_deleted_baseline:Apple"),
        )
        for name, hook, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "fail"}, name, PER_08=needle)

    def test_e9_c_sentinel_garment_still_in_the_director_after_the_purge_fails(self) -> None:
        """Tras una purga `done`, una prenda con un `pers_id` acreditado en el director de un censo posterior -> `fail`
        por identidad (`:582`): el guante amarillo en t5 de area_b (PER-08) o el beige en t5 de area_a (PER-07 y
        PER-08). Una centinela que no se puede atribuir (`pers_id` que no es del basal ni de una prenda prevista) ->
        `missing` (`:588`), ya no `fail` por clase."""
        variants = (
            ("yellow_gloves_area_b", "area_b", "b_act_1_gloves_dir", "Gloves", {"PER-08": "fail"},
             {"PER-08": "purge_remnant:b_act_1_gloves_dir"}),
            ("beige_gloves_area_a", "area_a", "ac_act_1_gloves_dir", "Gloves", {"PER-07": "fail", "PER-08": "fail"},
             {"PER-07": "reappeared_director_gloves:WorkingGloves_Beige", "PER-08": "purge_remnant:ac_act_1_gloves_dir"}),
            ("radar_cap_unattributable_area_b", "area_b", "RadarCap_Black", "Headgear", {"PER-08": "missing"},
             {"PER-08": "director_sentinel_unattributable:RadarCap_Black"}),
            ("armband_unattributable_area_a", "area_a", "Armband_Blue", "Armband", {"PER-07": "missing", "PER-08": "missing"},
             {"PER-07": "director_sentinel_unattributable:Armband_Blue", "PER-08": "director_sentinel_unattributable:Armband_Blue"}),
        )
        for name, area, what, slot, expected, needles in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    if what in builder.entities_by_lid:
                        cls, pid = builder.entities_by_lid[what]["class_name"], builder.entities_by_lid[what]["pers_id"]
                    else:
                        cls, pid = what, "1500201:-1500202:1500203:-1500204"
                    self._e9_add_rows_to_census(
                        part_dir, f"t5_post_restart_census:{area}", [self._e9_director_row(builder, cls, "1:9101", pid, slot)],
                    )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, expected, name, **{k.replace("-", "_"): v for k, v in needles.items()})

    def test_e9_c_start_garment_in_the_director_is_not_a_sentinel_remnant(self) -> None:
        """Control: una prenda de inicio (clase no centinela) en el director tras la purga no es un resto."""
        with tempfile.TemporaryDirectory() as tmp:
            builder, part_dir = self._e9_build(tmp, "run", "start_garment")
            self._e9_add_rows_to_census(
                part_dir, "t5_post_restart_census:area_b",
                [self._e9_director_row(builder, "TShirt_Green", "1:9201", "1500301:-1500302:1500303:-1500304", "Body")],
            )
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(_only_non_pass(verdict), {})


    # =========================================================================
    # O2 (ronda acotada del oraculo, 22-nov): los seis hallazgos de Sol sobre 433d535, el arbitraje 6 y la purga que
    # ordena el runner (brief, secciones finales `:517-601` y `:603-648`). `test_neg_o2_*` dan `fail` o `missing`
    # donde corresponde; `test_pos_o2_*` son evidencia honesta que debe pasar.
    # =========================================================================

    _O2_X_PID = "1600101:-1600102:1600103:-1600104"

    def _o2_edit_census_args(self, part_dir: Path, tag: str, edit: Any) -> None:
        """Edita los `args` de la orden de censo ``tag`` en su `enq` y en su `poll` (de ahi sale `include_director_b`)."""
        events = _read_events(part_dir)
        (job,) = list(self._e9_jobs_of(events, {tag}))
        n = 0
        for ev in events:
            holders = [ev] if ev.get("ev") == "enq" else (list(ev.get("ops") or []) if ev.get("ev") == "poll" else [])
            for h in holders:
                if h.get("op_id") == job:
                    u_s, u_n, u_r = _unpack(h["args"])
                    page = types.SimpleNamespace(strs=u_s, nums=u_n, rows=u_r)
                    edit(page)
                    h["args"] = _repack_read(page.strs, page.nums, page.rows, h["args"])
                    n += 1
        self.assertEqual(n, 2, msg=tag)
        _write_events(part_dir, events)

    def _o2_map_new_epoch_director_rows(self, part_dir: Path, builder: "_SyntheticPartBuilder", fn: Any) -> None:
        """Aplica ``fn(fila) -> fila | None`` a las filas del director de todos los censos del epoch nuevo (t5, testigo y
        t6) y ajusta `rows_total_n`, `rows_captured_n` y `director_inv_count_n` sin mover paginas."""
        events = _read_events(part_dir)
        dropped: dict[str, int] = {}
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" and ev.get("inst") == builder.server_epoch_new else []:
                if res.get("verb") == "per_census_start" and res.get("status") == "done":
                    dropped[_unpack(res["read"])[0]["job"]] = 0
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("verb") != "job_read" or res.get("status") != "done":
                    continue
                u_s, u_n, u_r = _unpack(res["read"])
                if u_s.get("job") not in dropped:
                    continue
                kept = []
                for row in u_r:
                    if row.get("owner_uid") != builder.director_uid:
                        kept.append(row)
                        continue
                    out = fn(dict(row))
                    if out is None:
                        dropped[u_s["job"]] += 1
                    else:
                        kept.append(out)
                res["read"] = _repack_read(u_s, u_n, kept, res["read"])
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("status") != "done" or res.get("verb") not in ("job_read", "per_census_start"):
                    continue
                u_s, u_n, u_r = _unpack(res["read"])
                d = dropped.get(u_s.get("job", ""), 0)
                if not d:
                    continue
                if res["verb"] == "job_read":
                    u_n["rows_total_n"] -= d
                else:
                    u_n["rows_captured_n"] -= d
                    u_n["director_inv_count_n"] -= d
                res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
        _write_events(part_dir, events)

    @staticmethod
    def _o2_op_events(events: list[dict[str, Any]], op_id: str) -> list[int]:
        """Indices de los eventos (`enq`, `poll`/`deliver`, `result`) de la orden ``op_id``."""
        out = []
        for i, ev in enumerate(events):
            if ev.get("op_id") == op_id and ev.get("ev") in ("enq", "deliver"):
                out.append(i)
            elif ev.get("ev") == "poll" and any(o.get("op_id") == op_id for o in ev.get("ops") or []):
                out.append(i)
            elif ev.get("ev") == "result" and any(r.get("op_id") == op_id for r in ev.get("results") or []):
                out.append(i)
        return out

    def _o2_purge_op_ids(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        """``order``, ``reads`` (todas las `job_read` del trabajo, en orden) y ``free`` de la purga."""
        (order,) = [r["op_id"] for r in self._e9_results(events, "per_purge_start", None)]
        reads = [r["op_id"] for r in self._e9_results(events, "job_read") if self._e9_page(r).strs.get("job") == order]
        frees = [r["op_id"] for r in self._e9_results(events, "job_free") if self._e9_page(r).strs.get("job") == order]
        return {"order": order, "reads": reads, "free": frees[0] if frees else ""}

    @staticmethod
    def _o2_insert_op(events: list[dict[str, Any]], at: int, *, op_id: str, verb: str, inst: str, args: dict[str, Any],
                      read: dict[str, Any], t_ms: float, status: str = "done", reason: str = "",
                      tick_ms: float = 1.0) -> None:
        evs = [
            {"ev": "enq", "peer": "server", "op_id": op_id, "verb": verb, "args": args, "inst": inst, "t_ms": t_ms},
            {"ev": "poll", "peer": "server", "inst": inst, "ops": [{"op_id": op_id, "verb": verb, "args": args}], "t_ms": t_ms},
            {"ev": "result", "peer": "server", "inst": inst, "t_ms": t_ms + 1.0, "results": [{
                "op_id": op_id, "verb": verb, "status": status, "reason": reason, "dup": 0, "recv_ms": tick_ms,
                "done_ms": tick_ms + 1.0, "frame_recv": 1, "frame_done": 2, "read": read,
            }]},
        ]
        events[at:at] = evs

    def _o2_glove_row(self, builder: "_SyntheticPartBuilder", lid: str, net_id: str) -> dict[str, Any]:
        glove = builder.entities_by_lid[lid]
        return self._e9_director_row(builder, glove["class_name"], net_id, glove["pers_id"], "Gloves")

    # ---- 1. FALLA e INCONCLUSO falsos --------------------------------------------------------------------------

    def test_neg_o2_sol1_explicit_include_director_0_is_judged_before_the_technical_failure(self) -> None:
        """Sol 1 sobre 433d535 (BLOQ A; brief :309 y :234): un `include_director_b = 0` explicito en la orden aceptada
        del censo t5 de un area que lo exige da `fail` en PER-09 aunque su trabajo acabe en `failed`, `expired` o
        `stopped`: el pedido demostrable se juzga antes de clasificar la caida tecnica."""
        for name, area, how in (
            ("area_b_failed", "area_b", "failed"),
            ("area_b_expired", "area_b", "expired"),
            ("area_a_stopped", "area_a", "stopped"),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)
                    tag = f"t5_post_restart_census:{area}"
                    self._o2_edit_census_args(part_dir, tag, lambda pg: pg.nums.update(include_director_b=0.0))
                    self._e9_census_down(part_dir, tag, how)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-09"]["status"], "fail", msg=f"{name}:{_only_non_pass(verdict)}")
                    self.assertIn(f"t5_director_not_included:{area}", c_map["PER-09"]["detail"], msg=name)
                    self.assertEqual({cid for cid, c in c_map.items() if c["status"] == "fail"}, {"PER-09"}, msg=name)
                    self.assertEqual(verdict["exit_code"], 1, msg=name)

    def test_pos_o2_sol1_census_down_without_an_explicit_zero_stays_missing(self) -> None:
        """Control de Sol 1: con `include_director_b = 1`, o sin la clave en la orden, un censo t5 caido por causa tecnica
        sigue dando `missing` en PER-09, nunca `fail` (brief :309)."""
        for name, area, how, drop_key in (
            ("area_b_failed_with_include_1", "area_b", "failed", False),
            ("area_a_expired_without_the_key", "area_a", "expired", True),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)
                    tag = f"t5_post_restart_census:{area}"
                    if drop_key:
                        self._o2_edit_census_args(part_dir, tag, lambda pg: pg.nums.pop("include_director_b"))
                    self._e9_census_down(part_dir, tag, how)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-09"]["status"], "missing", msg=f"{name}:{_only_non_pass(verdict)}")
                    self.assertIn(f"t5_missing_census:{area}", c_map["PER-09"]["detail"], msg=name)
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)
                    self.assertEqual(verdict["exit_code"], 2, msg=name)

    def test_pos_o2_sol2_consumed_or_swapped_baseline_item_keeps_the_same_character(self) -> None:
        """Sol 2 sobre 433d535 (BLOQ B): el mismo personaje no se da por sustituido por gastar un objeto basal. La Apple
        basal se come despues de t3 (falta en t5, en el testigo, en t6 y en las filas `pre`, con recuentos coherentes) o
        se sustituye por otra Apple con otro `pers_id`; los Jeans conservan el suyo (el ancla) y la purga es correcta ->
        PASA. La continuidad del inventario corrobora; no se exige que sobreviva todo."""
        def eat_apple(row: dict[str, Any]) -> dict[str, Any] | None:
            if row["class_name"] == "Apple":
                return None
            if row["class_name"] == "Jeans_Blue":
                row["inv_children_n"] = 0.0
            return row

        def swap_apple(row: dict[str, Any]) -> dict[str, Any]:
            if row["class_name"] == "Apple":
                row["pers_id"] = "1700201:-1700202:1700203:-1700204"
            return row

        def hook_eat(_b: Any, plan: dict[str, Any]) -> None:
            plan["tree"] = [e for e in plan["tree"] if e["class_name"] != "Apple"]

        def hook_swap(_b: Any, plan: dict[str, Any]) -> None:
            for e in plan["tree"]:
                if e["class_name"] == "Apple":
                    e["pers_id"] = "1700201:-1700202:1700203:-1700204"

        for name, fn, hook in (("apple_eaten_after_t3", eat_apple, hook_eat), ("apple_swapped_for_another", swap_apple, hook_swap)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    self._o2_map_new_epoch_director_rows(part_dir, builder, fn)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")
                    self.assertEqual(verdict["verdict"], "PASA", msg=name)

    def test_neg_o2_sol2_no_baseline_item_left_in_the_director_is_missing(self) -> None:
        """Control de Sol 2 (el ancla no se afloja): sin ningun `pers_id` del basal en el director de t5 (los objetos
        basales desaparecen, o todos traen `pers_id` nuevos) -> PER-07 y PER-08 `missing`
        (`director_character_replaced`)."""
        def all_gone(_row: dict[str, Any]) -> None:
            return None

        def all_new(row: dict[str, Any]) -> dict[str, Any]:
            row["pers_id"] = f"18{row['net_id'].split(':')[1]}01:-1800002:1800003:-1800004"
            return row

        for name, fn in (("all_baseline_items_gone", all_gone), ("all_baseline_items_with_new_pers_ids", all_new)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    self._o2_map_new_epoch_director_rows(part_dir, builder, fn)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    for cid in ("PER-07", "PER-08"):
                        self.assertEqual(
                            (c_map[cid]["status"], c_map[cid]["detail"]), ("missing", "director_character_replaced"),
                            msg=f"{name}:{cid}:{_only_non_pass(verdict)}",
                        )
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)

    def test_neg_o2_sol4_foreign_deletion_in_the_purge_fails_even_without_the_anchor(self) -> None:
        """Sol 4 sobre 433d535 (BLOQ C) y brief `:589`: un borrado ajeno acreditado en las filas del trabajo
        `per_purge_start` da `fail` en PER-08 aunque falte el ancla del personaje (en t5 o en las filas `pre`) o el
        director no este legible en t5: el `fail` con evidencia del epoch correcto manda sobre el `missing`."""
        def delete_baseline(cls: str, *, unanchored_pre: bool = False, tshirt: bool = False) -> Any:
            def hook(b: Any, plan: dict[str, Any]) -> None:
                if unanchored_pre:
                    plan["tree"] = [e for e in plan["tree"] if e.get("logical_id")]
                if tshirt:
                    plan["tree"].append({
                        "pers_id": self._O2_X_PID, "class_name": "TShirt_Green", "net_id": "1:9601",
                        "parent_net_id": "1:2", "parent_pers_id": "", "depth_n": 0.0, "owner_uid": b.director_uid,
                    })
                rows = b.honest_purge_rows(plan)
                victim = next(e for e in plan["tree"] if e["class_name"] == cls)
                rows.insert(len(rows) - 1, b.purge_row(
                    "emit", victim, emit_tick_ms=plan["start_tick_ms"] + 400.0, lease_age_ms=500.0, lease_limit_ms=3000.0,
                ))
                plan["rows"] = rows
            return hook

        variants = (
            ("baseline_apple_deleted_character_replaced_in_t5", delete_baseline("Apple"), "swap",
             {"PER-07": "missing", "PER-08": "fail"}, "purge_deleted_baseline:Apple"),
            ("unordered_deletion_pre_rows_without_anchor", delete_baseline("TShirt_Green", unanchored_pre=True, tshirt=True), "",
             {"PER-08": "fail"}, "purge_deleted_unordered:TShirt_Green"),
            ("baseline_jeans_deleted_director_unreadable_in_t5", delete_baseline("Jeans_Blue"), "gone",
             {"PER-08": "fail", "PER-09": "missing"}, "purge_deleted_baseline:Jeans_Blue"),
        )
        for name, hook, t5_edit, expected, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    if t5_edit == "swap":
                        self._e9_swap_director_pers_ids(part_dir, builder, ("area_a", "area_b"))
                    elif t5_edit == "gone":
                        self._e9_director_gone(part_dir, ("area_b",), present=0, readable=0)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, expected, name, PER_08=needle)

    def test_pos_o2_arb6_baseline_glove_of_the_same_class_beside_the_qa_glove_passes(self) -> None:
        """Arbitraje 6 (BLOQ 6 de Sol r2): unos guantes `WorkingGloves_Beige` del basal de t0, junto al guante QA de la
        misma clase que vuelve tras el reset de t3 con otro `net_id` y el mismo `pers_id`. Solo se autoriza el QA; el
        basal se conserva y no tumba PER-07 ni PER-08, ni aborta t0 (`:537`). Tambien en la parte `mut-foreign_wiped`
        (solo sus fallos propios) y si solo vuelve el guante beige. Con 9 filas, el recibo ocupa dos paginas."""
        for name, part, returning, expected in (
            ("run", "run", None, {}),
            ("run_only_the_beige_glove_returns", "run", ("ac_act_1_gloves_dir",), {}),
            ("mut_foreign_wiped", "mut-foreign_wiped", None, {"PER-04": "fail", "PER-05": "fail"}),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, part, name, baseline_sentinel_glove=True, purge_returning=returning)
                    base_glove = next(r for r in builder.baseline_dir_rows if r["class_name"] == "WorkingGloves_Beige")
                    qa_glove = builder.entities_by_lid["ac_act_1_gloves_dir"]
                    self.assertNotIn(base_glove["pers_id"], {r["pers_id"] for r in builder.purge_plan["order_rows"]})
                    beige_pre = {r["pers_id"] for r in self._e9_purge_rows(part_dir) if r["phase"] == "pre" and r["class_name"] == "WorkingGloves_Beige"}
                    self.assertEqual(beige_pre, {base_glove["pers_id"], qa_glove["pers_id"]})
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), expected, msg=f"{name}:{json.dumps(verdict['checks'])}")
                    self.assertNotIn("dirty_initial_area", verdict["reasons"], msg=name)

    def test_neg_o2_arb6_qa_glove_remnant_or_deleted_baseline_glove_fails(self) -> None:
        """Arbitraje 6, negativas: con el guante basal presente, (1) el guante QA beige (`pers_id` acreditado) se queda
        en t5 a su lado -> PER-07 y PER-08 `fail`; (2) la purga borra el guante basal -> PER-08 `fail`; (3) la orden
        autoriza el guante basal -> PER-08 `fail`."""
        def delete_base_glove(b: Any, plan: dict[str, Any]) -> None:
            rows = b.honest_purge_rows(plan)
            base = next(e for e in plan["tree"] if e["class_name"] == "WorkingGloves_Beige" and not e.get("logical_id"))
            rows.insert(len(rows) - 1, b.purge_row("emit", base, emit_tick_ms=plan["start_tick_ms"] + 400.0, lease_age_ms=500.0, lease_limit_ms=3000.0))
            plan["rows"] = rows

        def authorize_base_glove(b: Any, plan: dict[str, Any]) -> None:
            base = next(r for r in b.baseline_dir_rows if r["class_name"] == "WorkingGloves_Beige")
            plan["order_rows"].append({"pers_id": base["pers_id"], "class_name": base["class_name"]})

        variants = (
            ("qa_glove_stays_beside_the_baseline_one", None, {"PER-07": "fail", "PER-08": "fail"},
             {"PER_07": "reappeared_director_gloves:WorkingGloves_Beige", "PER_08": "purge_remnant:ac_act_1_gloves_dir"}),
            ("purge_deletes_the_baseline_glove", delete_base_glove, {"PER-08": "fail"},
             {"PER_08": "purge_deleted_baseline:WorkingGloves_Beige"}),
            ("order_authorizes_the_baseline_glove", authorize_base_glove, {"PER-08": "fail"},
             {"PER_08": "purge_order_differs_from_accredited"}),
        )
        for name, hook, expected, needles in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, baseline_sentinel_glove=True, purge_hook=hook)
                    if hook is None:
                        for area in ("area_a", "area_b"):
                            self._e9_add_rows_to_census(
                                part_dir, f"t5_post_restart_census:{area}", [self._o2_glove_row(builder, "ac_act_1_gloves_dir", "1:9301")]
                            )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, expected, name, **needles)

    # ---- 2. PASA falsos de identidad ---------------------------------------------------------------------------

    def test_neg_o2_sol3_per07_anchor_is_checked_in_every_director_census(self) -> None:
        """Sol 3 sobre 433d535 (BLOQ B): PER-07 verifica el ancla en cada censo del director que usa. En
        `mut-foreign_wiped`, un censo t5 (area_a o area_a_mut) con el mismo uid y todos los `pers_id` nuevos no se
        acredita con los del otro censo -> PER-07 `missing`; el mutante sigue fallando solo por PER-04 y PER-05."""
        for name, area in (("area_a_replaced", "area_a"), ("area_a_mut_replaced", "area_a_mut")):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "mut-foreign_wiped", name)
                    self._e9_swap_director_pers_ids(part_dir, builder, (area,))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(
                        verdict, {"PER-04": "fail", "PER-05": "fail", "PER-07": "missing"}, name,
                        PER_07="director_character_replaced",
                    )

    def test_pos_o2_sol3_reloaded_character_in_every_census_passes(self) -> None:
        """Control de Sol 3: el personaje recargado (mismos `pers_id`, `net_id` nuevos) en todos los censos t5 -> PASA en
        `run` y, en `mut-foreign_wiped`, solo los fallos propios del mutante."""
        def reload(row: dict[str, Any]) -> dict[str, Any]:
            row["net_id"] = f"2:{row['net_id'].split(':')[1]}0"
            if row.get("parent_net_id") == "1:10":
                row["parent_net_id"] = "2:100"
            return row

        for name, part, expected in (("run", "run", {}), ("mut_foreign_wiped", "mut-foreign_wiped", {"PER-04": "fail", "PER-05": "fail"})):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, part, name)
                    areas = ("area_a", "area_b") + (("area_a_mut",) if part == "mut-foreign_wiped" else ())
                    self._e9_edit_pages(
                        part_dir, {f"t5_post_restart_census:{a}" for a in areas},
                        lambda pg: [reload(r) for r in self._e9_director_rows(pg, builder)],
                    )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), expected, msg=f"{name}:{json.dumps(verdict['checks'])}")

    def _o2_edit_area_c(self, part_dir: Path, stage: str, edit_row: Any) -> None:
        def edit(pg: types.SimpleNamespace) -> None:
            for row in pg.rows:
                edit_row(row)

        self._e9_edit_pages(part_dir, {f"{stage}:area_c"}, edit)

    def test_neg_o2_sol6_control_child_with_another_pers_id_not_pasa(self) -> None:
        """Sol 6 sobre 433d535 (fuera del delta; brief :306): el hijo `Fireplace` del control persistente de area_c se
        compara entre t3 y t5 tambien por su `pers_id`. Otro de la misma clase en el mismo barril -> PER-06 `fail`; sin
        un `pers_id` utilizable en t3 o en t5 la identidad del hijo no se puede verificar -> `missing`. PER-07 y PER-08
        quedan en `missing` porque dependen de PER-06."""
        def set_fireplace_pid(pid: str) -> Any:
            def edit_row(row: dict[str, Any]) -> None:
                if row["class_name"] == "Fireplace":
                    row["pers_id"] = pid
            return edit_row

        variants = (
            ("fireplace_swapped_same_class_same_barrel", "t5_post_restart_census", "1700001:-1700002:1700003:-1700004",
             "fail", "control_child_pers_id_mismatch"),
            ("t3_child_with_zero_pers_id", "t3_post_reset_census", "0:0:0:0", "missing", "control_child_identity_unverifiable"),
            ("t5_child_with_malformed_pers_id", "t5_post_restart_census", "55:66:77", "missing", "control_child_identity_unverifiable"),
        )
        for name, stage, pid, status, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)
                    self._o2_edit_area_c(part_dir, stage, set_fireplace_pid(pid))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(
                        verdict, {"PER-06": status, "PER-07": "missing", "PER-08": "missing"}, name, PER_06=needle,
                    )

    def test_pos_o2_sol6_control_child_keeps_its_pers_id_with_new_net_ids_passes(self) -> None:
        """Control de Sol 6: tras el reinicio el barril y su `Fireplace` traen `net_id` nuevos y los mismos `pers_id`
        -> PASA."""
        def renumber(row: dict[str, Any]) -> None:
            if row["class_name"] == "Barrel_Yellow":
                row["net_id"] = "3:801"
            elif row["class_name"] == "Fireplace":
                row["net_id"], row["parent_net_id"] = "3:802", "3:801"

        with tempfile.TemporaryDirectory() as tmp:
            _builder, part_dir = self._e9_build(tmp, "run", "renumbered")
            self._o2_edit_area_c(part_dir, "t5_post_restart_census", renumber)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(_only_non_pass(verdict), {}, msg=json.dumps(verdict["checks"]))

    # ---- 3. La purga ordenada por el runner -------------------------------------------------------------------

    def test_neg_o2_purge_order_differs_from_the_accredited_fails(self) -> None:
        """Brief, arbitraje 3: el oraculo recalcula las acreditadas (alta, `move_to_director` y censos del epoch viejo
        con el director) y las compara por igualdad con la orden cruda del puente, aunque no haya bajas. Una orden que
        omite el guante amarillo, que anade los Jeans basales, que cambia la clase de un guante o que anade un
        `pers_id` desconocido sin que vuelva nada -> PER-08 `fail`."""
        def omit_yellow(_b: Any, plan: dict[str, Any]) -> None:
            plan["order_rows"] = plan["order_rows"][:1]

        def add_jeans(b: Any, plan: dict[str, Any]) -> None:
            jeans = b.baseline_dir_rows[0]
            plan["order_rows"].append({"pers_id": jeans["pers_id"], "class_name": jeans["class_name"]})

        def wrong_class(_b: Any, plan: dict[str, Any]) -> None:
            plan["order_rows"][1] = {**plan["order_rows"][1], "class_name": "WorkingGloves_Beige"}

        def unknown_and_nothing_returns(_b: Any, plan: dict[str, Any]) -> None:
            plan["order_rows"].append({"pers_id": self._O2_X_PID, "class_name": "WorkingGloves_Yellow"})

        for name, hook, returning in (
            ("order_omits_the_yellow_glove", omit_yellow, None),
            ("order_adds_the_baseline_jeans", add_jeans, None),
            ("order_with_a_wrong_class", wrong_class, None),
            ("order_adds_an_unknown_pers_id_zero_bajas", unknown_and_nothing_returns, ()),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook, purge_returning=returning)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "fail"}, name, PER_08="purge_order_differs_from_accredited")

    def test_pos_o2_purge_accredited_are_recomputed_without_trusting_the_runner(self) -> None:
        """Las acreditadas salen de la evidencia, nunca de `purge_authorized` (`:575`): un evento del runner que miente
        (lista los Jeans basales, o nada) no cambia el veredicto de una orden correcta. Y el guante que borro el reset
        de t3 sigue acreditado con sus lecturas de t1_post y t3_pre (arbitraje 3)."""
        def lying_event(rows: Any) -> Any:
            def hook(b: Any, plan: dict[str, Any]) -> None:
                plan["authorized_rows"] = rows(b)
            return hook

        for name, hook in (
            ("event_lists_the_baseline_jeans", lying_event(lambda b: [{"pers_id": b.baseline_dir_rows[0]["pers_id"], "logical_id": "", "net_id": "1:10", "censuses": []}])),
            ("event_lists_nothing", lying_event(lambda _b: [])),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")
                    self.assertIn("ac_act_1_gloves_dir", verdict["metrics"]["runner_purge"]["accredited"])

    def test_neg_o2_purge_accredited_unidentifiable_is_missing(self) -> None:
        """Brief, arbitraje 3 (`:626`): si falta evidencia para identificar una prenda prevista, `missing` (ni `fail` ni
        PASA): el guante amarillo leido con otro `pers_id` en t1_post que en t3, su `move_to_director` con un `net_id`
        que no es el de su alta, o sin el director como dueno tras la transicion."""
        def edit_t1_post_yellow(builder: "_SyntheticPartBuilder", part_dir: Path) -> None:
            yellow_nid = builder.entities_by_lid["b_act_1_gloves_dir"]["net_id"]

            def edit(pg: types.SimpleNamespace) -> None:
                for row in pg.rows:
                    if row["net_id"] == yellow_nid:
                        row["pers_id"] = self._O2_X_PID

            self._e9_edit_pages(part_dir, {"t1_post_transition_census:area_a", "t1_post_transition_census:area_b"}, edit)

        def edit_transition_net_id(builder: "_SyntheticPartBuilder", part_dir: Path) -> None:
            events = _read_events(part_dir)
            n = 0
            for res in self._e9_results(events, "per_child_transition"):
                page = self._e9_page(res)
                if page.strs.get("net_id") == builder.entities_by_lid["b_act_1_gloves_dir"]["net_id"]:
                    page.strs["net_id"] = "1:9999"
                    self._e9_store(res, page)
                    n += 1
            self.assertEqual(n, 1)
            _write_events(part_dir, events)

        def edit_transition_owner(builder: "_SyntheticPartBuilder", part_dir: Path) -> None:
            # la transicion `ok` no acredita que el destino sea el director: prenda prevista sin identificar, no una
            # autorizacion indebida (sin FALLA falso)
            events = _read_events(part_dir)
            n = 0
            for res in self._e9_results(events, "per_child_transition"):
                page = self._e9_page(res)
                if page.strs.get("net_id") == builder.entities_by_lid["b_act_1_gloves_dir"]["net_id"]:
                    page.strs["post_owner_uid"] = ""
                    self._e9_store(res, page)
                    n += 1
            self.assertEqual(n, 1)
            _write_events(part_dir, events)

        for name, edit, needle in (
            ("yellow_glove_read_with_two_pers_ids", edit_t1_post_yellow, "purge_accredited_unidentified:b_act_1_gloves_dir:inconsistent_readings"),
            ("transition_net_id_is_not_the_apply_one", edit_transition_net_id, "purge_accredited_unidentified:b_act_1_gloves_dir:apply_transition_mismatch"),
            ("transition_without_the_director_as_owner", edit_transition_owner, "purge_accredited_unidentified:b_act_1_gloves_dir:transition_not_to_director"),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    edit(builder, part_dir)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08=needle)

    def test_neg_o2_purge_pages_must_be_unique_and_complete(self) -> None:
        """Brief, arbitraje 4: paginas unicas y completas del mismo trabajo. Con el recibo en dos paginas, una pagina 1
        que repite una fila `pre` de la pagina 0 (el total cuadra), una lectura cuya `page_n` no es la pedida, o la
        pagina 1 marcada como de otro trabajo -> PER-08 `missing`."""
        def page1_repeats(pg: types.SimpleNamespace) -> None:
            if int(round(pg.nums["page_n"])) == 1:
                pg.rows = [dict(pg_rows0[0])]

        def wrong_page_n(pg: types.SimpleNamespace) -> None:
            if int(round(pg.nums["page_n"])) == 1:
                pg.nums["page_n"] = 0.0

        def other_job(pg: types.SimpleNamespace) -> None:
            if int(round(pg.nums["page_n"])) == 1:
                pg.strs["job"] = "otro-trabajo-1"

        for name, edit, needle in (
            ("page_1_repeats_a_pre_row_of_page_0", page1_repeats, "purge_pre_rows_duplicated_or_unidentified"),
            ("read_with_a_page_n_that_was_not_asked", wrong_page_n, "purge_read_inconsistent"),
            ("page_1_of_another_job", other_job, "purge_pages_incomplete"),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, baseline_sentinel_glove=True)
                    pg_rows0 = [r for r in self._e9_purge_rows(part_dir) if r["phase"] == "pre"]
                    self.assertEqual(len(self._e9_purge_rows(part_dir)), 9)
                    self._e9_edit_purge_reads(part_dir, edit)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=f"{name}:{_only_non_pass(verdict)}")
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-08"]["status"], "missing", msg=name)
                    self.assertIn(needle, c_map["PER-08"]["detail"], msg=f"{name}:{c_map['PER-08']['detail']}")

    def test_neg_o2_purge_bad_baja_is_judged_in_any_terminal_state(self) -> None:
        """Brief, arbitraje 5: el runner lee las paginas de cualquier estado terminal y el oraculo juzga sus bajas. La
        baja de los Jeans basales da `fail` en un trabajo `failed` (lease), `expired` o `stopped`, y tambien con la
        espera vencida (pagina 0 en `running`): manda sobre el `missing` de `purge_not_done`."""
        def hook_for(st: str, reason: str) -> Any:
            def hook(b: Any, plan: dict[str, Any]) -> None:
                plan["state"], plan["reason"] = st, reason
                rows = b.honest_purge_rows(plan)
                jeans = next(e for e in plan["tree"] if e["class_name"] == "Jeans_Blue")
                rows.insert(len(rows) - 1, b.purge_row("emit", jeans, emit_tick_ms=plan["start_tick_ms"] + 400.0, lease_age_ms=500.0, lease_limit_ms=3000.0))
                plan["rows"] = rows
            return hook

        for st, reason in (("failed", "lease_expired"), ("expired", "job_timeout"), ("stopped", ""), ("running", "")):
            with self.subTest(st):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", st, purge_hook=hook_for(st, reason))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "fail"}, st, PER_08="purge_deleted_baseline:Jeans_Blue")

    def test_neg_o2_purge_baja_identity_owner_class_and_lease(self) -> None:
        """Brief, ronda 2 `:577-579` y arbitraje 2: una baja autorizada sin estar acreditada, fuera del arbol del director,
        con otra clase que la autorizada o con `lease_age_ms > lease_limit_ms` -> PER-08 `fail`. Una baja con
        `lease_limit_ms = 0` no acredita E1 -> `missing`. (La igualdad, en el control positivo de abajo.)"""
        def authorize_unaccredited(b: Any, plan: dict[str, Any]) -> None:
            plan["tree"].append({
                "pers_id": self._O2_X_PID, "class_name": "TShirt_Green", "net_id": "1:9601",
                "parent_net_id": "1:2", "parent_pers_id": "", "depth_n": 0.0, "owner_uid": b.director_uid,
            })
            plan["order_rows"].append({"pers_id": self._O2_X_PID, "class_name": "TShirt_Green"})

        def edit_yellow_baja(**changes: Any) -> Any:
            def hook(b: Any, plan: dict[str, Any]) -> None:
                yellow = b.entities_by_lid["b_act_1_gloves_dir"]["pers_id"]
                rows = b.honest_purge_rows(plan)
                for r in rows:
                    if r["phase"] == "emit" and r["pers_id"] == yellow:
                        r.update(changes)
                plan["rows"] = rows
            return hook

        variants = (
            ("authorized_but_unaccredited", authorize_unaccredited, "fail", "purge_deleted_unaccredited:TShirt_Green"),
            ("baja_outside_the_director", edit_yellow_baja(owner_uid="otro-uid-1"), "fail", "purge_deleted_outside_director:WorkingGloves_Yellow"),
            ("baja_with_another_class", edit_yellow_baja(class_name="WorkingGloves_Beige"), "fail", "purge_deleted_class_mismatch:WorkingGloves_Beige"),
            ("lease_age_over_the_limit", edit_yellow_baja(lease_age_ms=3001.0), "fail", "purge_emit_lease_expired:WorkingGloves_Yellow"),
            ("lease_limit_zero", edit_yellow_baja(lease_limit_ms=0.0), "missing", "purge_emit_lease_unaccredited"),
        )
        for name, hook, status, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": status}, name, PER_08=needle)

    def test_pos_o2_purge_lease_age_equal_to_the_limit_passes(self) -> None:
        """Control: `LeaseOk()` admite la igualdad (`DSBX_QA_Probe.c:447-454`), asi que una baja con
        `lease_age_ms == lease_limit_ms` sigue en PASA."""
        def equal(b: Any, plan: dict[str, Any]) -> None:
            plan["lease_age_ms"] = plan["lease_limit_ms"]

        with tempfile.TemporaryDirectory() as tmp:
            _builder, part_dir = self._e9_build(tmp, "run", "equal", purge_hook=equal)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(_only_non_pass(verdict), {}, msg=json.dumps(verdict["checks"]))

    def _o2_rag_hook(self, *, only_in_emit: bool) -> Any:
        """Una implementacion defectuosa: borra el guante amarillo con un trapo ajeno dentro (en `pre`, o que entro
        despues y solo se ve en las filas `emit` del tick de la baja)."""
        def hook(b: Any, plan: dict[str, Any]) -> None:
            yellow = b.entities_by_lid["b_act_1_gloves_dir"]["pers_id"]
            y_ent = next(e for e in plan["tree"] if e["pers_id"] == yellow)
            rag = {
                "pers_id": "1900001:-1900002:1900003:-1900004", "class_name": "Rag", "net_id": "1:9701",
                "parent_net_id": y_ent["net_id"], "parent_pers_id": yellow, "depth_n": 2.0, "owner_uid": b.director_uid,
            }
            rows = b.honest_purge_rows(plan)
            if only_in_emit:
                at = next(i for i, r in enumerate(rows) if r["phase"] == "emit" and r["pers_id"] == yellow)
                rows.insert(at, b.purge_row("emit", rag))
            else:
                at = max(i for i, r in enumerate(rows) if r["phase"] == "pre") + 1
                rows.insert(at, b.purge_row("pre", rag))
            plan["rows"] = rows
        return hook

    def test_neg_o2_purge_foreign_descendant_lost_with_its_parent_fails(self) -> None:
        """Brief, ronda 2 `:580` y arbitraje 2 y 4: una entidad sin autorizar que cuelga de una baja en la captura de su
        tick (que entro despues de `pre`, o que ya estaba en `pre`) y falta en t5: se borro algo ajeno con el padre ->
        `fail`. Con el director ilegible en t5 la ausencia queda fuera de cobertura -> `missing`, no `fail`.
        O3 (H2 de Sol sobre O2): el arrastre se atribuye con la captura del tick de la baja, no con `pre`. El trapo que
        solo consta en `pre` y que la captura del tick ya no pone bajo el guante (`rag_in_pre`) no se le atribuye: su
        ausencia en t5 no se explica -> `missing` (`purge_foreign_unaccounted:Rag`), ya no `fail`. La variante
        `rag_in_pre_and_in_the_tick_capture` conserva el `fail` cuando la captura si lo pone bajo el guante."""
        variants = (
            ("rag_in_pre", self._o2_rag_hook(only_in_emit=False), False, "missing", "purge_foreign_unaccounted:Rag"),
            ("rag_in_pre_and_in_the_tick_capture", self._o3_rag_hook(in_pre=True, in_capture="under_glove"), False,
             "fail", "purge_foreign_lost_with_parent:Rag"),
            ("rag_entered_after_pre", self._o2_rag_hook(only_in_emit=True), False, "fail", "purge_foreign_lost_with_parent:Rag"),
            ("rag_in_pre_director_unreadable_in_t5", self._o2_rag_hook(only_in_emit=False), True, "missing", ""),
        )
        for name, hook, unreadable, status, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    if unreadable:
                        self._e9_director_gone(part_dir, ("area_a", "area_b"), present=1, readable=0)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-08"]["status"], status, msg=f"{name}:{_only_non_pass(verdict)}")
                    if needle:
                        self.assertIn(needle, c_map["PER-08"]["detail"], msg=f"{name}:{c_map['PER-08']['detail']}")
                    if status == "fail":
                        self.assertEqual(_only_non_pass(verdict), {"PER-08": "fail"}, msg=name)
                    else:
                        self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)

    def test_pos_o2_purge_foreign_content_still_in_t5_is_not_a_loss(self) -> None:
        """Control: si el trapo ajeno sigue en el director en t5 (no se perdio con el guante), no hay `fail` por perdida."""
        with tempfile.TemporaryDirectory() as tmp:
            builder, part_dir = self._e9_build(tmp, "run", "rag_kept", purge_hook=self._o2_rag_hook(only_in_emit=False))
            for area in ("area_a", "area_b"):
                self._e9_add_rows_to_census(part_dir, f"t5_post_restart_census:{area}", [self._e9_director_row(
                    builder, "Rag", "1:9702", "1900001:-1900002:1900003:-1900004", "Cargo:0:2:0")])
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(_only_non_pass(verdict), {}, msg=json.dumps(verdict["checks"]))

    def test_neg_o2_purge_remnant_by_identity_after_done_fails(self) -> None:
        """Brief, ronda 2 `:582`: tras un `done`, un `pers_id` acreditado en el director de un censo posterior es un
        remanente -> `fail`: con `retained_foreign` (el guante tiene algo ajeno dentro y se queda), con un guante
        `absent` en la purga que aparece despues en t5, o en el censo testigo."""
        def retained(b: Any, plan: dict[str, Any]) -> None:
            yellow = b.entities_by_lid["b_act_1_gloves_dir"]["pers_id"]
            y_ent = next(e for e in plan["tree"] if e["pers_id"] == yellow)
            plan["tree"].append({
                "pers_id": "1900001:-1900002:1900003:-1900004", "class_name": "Rag", "net_id": "1:9701",
                "parent_net_id": y_ent["net_id"], "parent_pers_id": yellow, "depth_n": 2.0, "owner_uid": b.director_uid,
            })

        variants = (
            ("retained_foreign_glove_stays", retained, None, ("t5_post_restart_census:area_a", "t5_post_restart_census:area_b"), "b_act_1_gloves_dir"),
            ("absent_in_the_purge_present_in_t5", None, ("ac_act_1_gloves_dir",), ("t5_post_restart_census:area_b",), "b_act_1_gloves_dir"),
            ("remnant_in_the_witness_census", None, None, ("t5_witness_pre_census:area_b", "t5_witness_post_census:area_b"), "ac_act_1_gloves_dir"),
        )
        for name, hook, returning, tags, lid in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook, purge_returning=returning)
                    if hook is retained:
                        self.assertIn("retained_foreign", [r["result"] for r in self._e9_purge_rows(part_dir)])
                    for tag in tags:
                        self._e9_add_rows_to_census(part_dir, tag, [self._o2_glove_row(builder, lid, "1:9801")])
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-08"]["status"], "fail", msg=f"{name}:{_only_non_pass(verdict)}")
                    self.assertIn(f"purge_remnant:{lid}", c_map["PER-08"]["detail"], msg=name)
                    self.assertEqual(verdict["exit_code"], 1, msg=name)

    def test_neg_o2_purge_epoch_link_is_required(self) -> None:
        """Brief, ronda 2 `:574`, `:585` y arbitraje 7: el `per_status` que valida al director, la orden, las `job_read` y
        el `job_free` van al epoch nuevo; cada resultado se casa con su `enq` y su entrega por `op_id`, y su epoch es el
        del ultimo `hello` aceptado del servidor. Sin ese vinculo, o con la orden a otro epoch, PER-08 `missing`."""
        def stale(b: Any, plan: dict[str, Any]) -> None:
            plan["order_strings"]["expect_epoch"] = b.server_epoch_old

        def edit_events(kind: str) -> Any:
            def edit(builder: "_SyntheticPartBuilder", events: list[dict[str, Any]]) -> list[dict[str, Any]]:
                ids = self._o2_purge_op_ids(events)
                last_read = ids["reads"][-1]
                if kind == "read_enq_other":
                    for ev in events:
                        if ev.get("ev") == "enq" and ev.get("op_id") == last_read:
                            ev["inst"] = "srv-epoch-9999"
                elif kind == "read_without_delivery":
                    events = [ev for ev in events if not (ev.get("ev") == "poll" and any(o.get("op_id") == last_read for o in ev.get("ops") or []))]
                elif kind == "order_enq_without_inst":
                    for ev in events:
                        if ev.get("ev") == "enq" and ev.get("op_id") == ids["order"]:
                            ev.pop("inst")
                elif kind == "order_result_of_another_epoch":
                    for ev in events:
                        if ev.get("ev") == "result" and any(r.get("op_id") == ids["order"] for r in ev.get("results") or []):
                            ev["inst"] = "srv-epoch-9999"
                elif kind == "director_not_validated":
                    first_new = _status_op_ids(events, builder.server_epoch_new)[0]
                    for ev in events:
                        for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                            if res.get("op_id") == first_new:
                                u_s, u_n, u_r = _unpack(res["read"])
                                u_n["director_present_b"] = 0.0
                                res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
                return events
            return edit

        variants = (
            ("order_expects_the_old_epoch", stale, None, "purge_order_stale_epoch"),
            ("read_enqueued_to_another_instance", None, edit_events("read_enq_other"), "purge_epoch_unlinked:job_read:enq_inst"),
            ("read_without_delivery", None, edit_events("read_without_delivery"), "purge_epoch_unlinked:job_read:no_delivery"),
            ("order_enq_without_inst", None, edit_events("order_enq_without_inst"), "purge_epoch_unlinked:per_purge_start:enq_inst"),
            ("order_result_of_another_epoch", None, edit_events("order_result_of_another_epoch"), "purge_epoch_unlinked:per_purge_start:result_epoch"),
            ("director_not_validated_before_the_order", None, edit_events("director_not_validated"), "purge_director_not_validated"),
        )
        for name, hook, edit, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    if edit is not None:
                        _write_events(part_dir, edit(builder, _read_events(part_dir)))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08=needle)

    def test_pos_o2_purge_epoch_linked_in_the_real_bridge_format(self) -> None:
        """Control del vinculo: el trafico de t4 (el `per_status` de la espera y la purga) con el formato del puente real
        (`enq` con `inst`, `poll` con `op_ids` y un `deliver` por orden, `result` sin `inst`) sigue en PASA."""
        with tempfile.TemporaryDirectory() as tmp:
            builder, part_dir = self._e9_build(tmp, "run", "real_format")
            events = _read_events(part_dir)
            ids = self._o2_purge_op_ids(events)
            first_new = _status_op_ids(events, builder.server_epoch_new)[0]
            targets = {first_new, ids["order"], ids["free"], *ids["reads"]}
            out: list[dict[str, Any]] = []
            for ev in events:
                if ev.get("ev") == "poll" and any(o.get("op_id") in targets for o in ev.get("ops") or []):
                    out.append({k: v for k, v in ev.items() if k != "ops"} | {"op_ids": [o["op_id"] for o in ev["ops"]], "http": 200})
                    for o in ev["ops"]:
                        out.append({"ev": "deliver", "peer": "server", "inst": ev["inst"], "op_id": o["op_id"],
                                    "verb": o["verb"], "args": o["args"], "t_ms": ev.get("t_ms")})
                elif ev.get("ev") == "result" and any(r.get("op_id") in targets for r in ev.get("results") or []):
                    out.append({k: v for k, v in ev.items() if k != "inst"})
                else:
                    out.append(ev)
            _write_events(part_dir, out)
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(_only_non_pass(verdict), {}, msg=json.dumps(verdict["checks"]))

    def test_neg_o2_sol5_purge_end_between_the_census_job_start_and_its_snapshot_fails(self) -> None:
        """Sol 5 sobre 433d535 (BLOQ C): el primer trabajo t5 empieza en S-10 (su `job_read`) y su instantanea es S; un
        fin de purga en S-5 queda despues del inicio del trabajo -> `fail` (`:581`, `>=`), aunque sea anterior a la
        instantanea. Con el fin en S-11, antes del inicio del trabajo, sigue en PASA."""
        for name, end_delta, ok in (("end_after_the_job_start", -5.0, False), ("end_before_the_job_start", -11.0, True)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)
                    snap = self._e9_first_t5_start_tick(part_dir)
                    self._e9_edit_pages(part_dir, {"t5_post_restart_census:area_a"}, lambda pg: pg.nums.update(start_tick_ms=snap - 10.0))
                    self._e9_edit_purge_reads(
                        part_dir,
                        lambda pg, end=snap + end_delta: pg.nums.update(end_tick_ms=end, onjobend_tick_ms=end, released_tick_ms=end),
                    )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    if ok:
                        self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")
                    else:
                        self._e9_expect(verdict, {"PER-08": "fail"}, name, PER_08="purge_not_before_t5_census")

    def test_neg_o2_sol5_last_purge_read_after_the_first_t5_send_is_missing(self) -> None:
        """Sol 5 / brief `:586`: la ultima lectura del trabajo de purga tiene que preceder, en la traza del puente, al
        envio del primer censo t5. Si una lectura (la ultima pagina, o todas las terminales) llega despues -> `missing`
        (el fin del trabajo sigue siendo anterior: no hay `fail`)."""
        for name, how_many in (("last_page_read_after", 1), ("all_terminal_reads_after", 2)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name)
                    events = _read_events(part_dir)
                    ids = self._o2_purge_op_ids(events)
                    moved_ids = ids["reads"][-how_many:]
                    idxs = sorted(i for oid in moved_ids for i in self._o2_op_events(events, oid))
                    moved = [events[i] for i in idxs]
                    rest = [ev for i, ev in enumerate(events) if i not in set(idxs)]
                    (first_t5_job,) = list(self._e9_jobs_of(rest, {"t5_post_restart_census:area_a"}))
                    at = next(i for i, ev in enumerate(rest) if ev.get("ev") == "enq" and ev.get("op_id") == first_t5_job) + 1
                    _write_events(part_dir, rest[:at] + moved + rest[at:])
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08="purge_read_not_before_t5")

    def test_neg_o2_purge_pre_rows_without_the_character_anchor_is_missing(self) -> None:
        """Brief, arbitraje 8: antes de la primera baja tiene que constar el mismo personaje (las filas `pre` contienen el
        ancla de PER-07). Sin ella (solo los guantes, o los objetos basales con `pers_id` nuevos) -> `missing`; las bajas
        honestas no dan `fail`."""
        def only_gloves(_b: Any, plan: dict[str, Any]) -> None:
            plan["tree"] = [e for e in plan["tree"] if e.get("logical_id")]

        def new_pids(_b: Any, plan: dict[str, Any]) -> None:
            for k, e in enumerate(plan["tree"]):
                if not e.get("logical_id"):
                    e["pers_id"] = f"170{k}301:-1700302:1700303:-1700304"

        for name, hook in (("pre_rows_only_the_gloves", only_gloves), ("baseline_items_with_new_pers_ids", new_pids)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08="purge_character_unanchored")

    def test_neg_o2_t0_director_ambiguous_only_with_two_or_more_players(self) -> None:
        """Brief, ronda 2 `:531` y arbitraje 8: con dos o mas jugadores en el `per_status` de t0 -> `2 INCONCLUSO`
        (`director_ambiguous`), tambien si antes hubo una espera con cero."""
        for name, seq in (("two_players", (2,)), ("three_players", (3,)), ("zero_then_two", (0, 2))):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, t0_players_n=seq)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertIn("director_ambiguous", verdict["reasons"], msg=name)
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)
                    self.assertEqual(verdict["exit_code"], 2, msg=name)

    def test_pos_o2_t0_zero_players_keeps_waiting_and_one_player_fixes_the_uid(self) -> None:
        """Control: con cero jugadores se sigue esperando y el uid se fija con exactamente uno -> PASA, sin
        `director_ambiguous`."""
        for name, seq in (("zero_then_one", (0, 1)), ("zero_zero_then_one", (0, 0, 1))):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, t0_players_n=seq)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{verdict['reasons']}")
                    self.assertNotIn("director_ambiguous", verdict["reasons"], msg=name)

    def test_neg_o2_t0_entity_outside_the_director_tree_still_aborts(self) -> None:
        """Brief `:248` (ronda 2): una centinela dentro del arbol del director ya no aborta, pero cualquier entidad de las
        areas de suelo en t0 (una centinela o un objeto cualquiera, `owner_uid` vacio) sigue abortando con
        `dirty_initial_area`."""
        for name, area, cls in (("sentinel_on_the_ground_area_b", "area_b", "RadarCap_Black"), ("bottle_on_the_ground_area_c", "area_c", "WaterBottle")):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    row = self._t6_row(class_name=cls, ai_agent_b=0.0, max_hp=100.0, health_hp=100.0, net_id="1:9901",
                                       pers_id="1500901:-1500902:1500903:-1500904")
                    events = _read_events(part_dir)
                    (job,) = list(self._e9_jobs_of(events, {f"t0_baseline_census:{area}"}))
                    for ev in events:
                        for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                            if res.get("status") == "done" and res.get("verb") in ("per_census_start", "job_read"):
                                u_s, u_n, u_r = _unpack(res["read"])
                                if u_s.get("job") != job:
                                    continue
                                if res["verb"] == "per_census_start":
                                    u_n["rows_captured_n"] += 1
                                else:
                                    u_n.update(rows_total_n=1.0, pages_n=1.0)
                                    u_r = [row]
                                res["read"] = _repack_read(u_s, u_n, u_r, res["read"])
                    _write_events(part_dir, events)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertIn("dirty_initial_area", verdict["reasons"], msg=name)
                    self.assertEqual(verdict["exit_code"], 2, msg=name)

    def test_neg_o2_per_purge_read_no_longer_accredits_the_purge(self) -> None:
        """Brief, ronda 2 `:526`: `per_purge_read` desaparece. Un registro honesto de `per_purge_read` (formato de la
        enmienda del 2026-11-17) sin orden `per_purge_start`, con prendas acreditadas -> PER-08 `missing`."""
        def no_order(_b: Any, plan: dict[str, Any]) -> None:
            plan["send_order"] = False

        for name in ("record_with_both_gloves", "record_with_nothing"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=no_order)
                    events = _read_events(part_dir)
                    first_new = _status_op_ids(events, builder.server_epoch_new)[0]
                    at = max(self._o2_op_events(events, first_new)) + 1
                    rows = [] if name == "record_with_nothing" else [
                        {"class_name": builder.entities_by_lid[lid]["class_name"], "pers_id": builder.entities_by_lid[lid]["pers_id"],
                         "owner_uid": builder.director_uid}
                        for lid in ("ac_act_1_gloves_dir", "b_act_1_gloves_dir")
                    ]
                    self._o2_insert_op(
                        events, at, op_id="old-purge-read-1", verb="per_purge_read", inst=builder.server_epoch_new,
                        args=builder._pack_ext_args(), t_ms=float(events[at - 1]["t_ms"]) + 1.0, tick_ms=700.0,
                        read=builder._pack_ext_read(
                            strings={"server_epoch": builder.server_epoch_new, "purge_state": "done"},
                            numbers={"purge_tick_ms": 700.0, "purge_frame": 20.0, "purged_n": float(len(rows))},
                            scol=["class_name", "pers_id", "owner_uid"], rows=rows,
                        ),
                    )
                    _write_events(part_dir, events)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08="purge_not_done:no_order")

    def test_neg_o2_purge_second_order_in_the_run_is_missing(self) -> None:
        """Brief `:538` y `:587`: la unica orden de purga de la corrida es la de t4. Otra en el epoch viejo (aunque se
        rechace) o una segunda en el nuevo -> PER-08 `missing`."""
        for name in ("rejected_order_in_the_old_epoch", "second_order_in_the_new_epoch"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    events = _read_events(part_dir)
                    ids = self._o2_purge_op_ids(events)
                    order_enq = next(ev for ev in events if ev.get("ev") == "enq" and ev.get("op_id") == ids["order"])
                    if name == "rejected_order_in_the_old_epoch":
                        at = self._new_hello_index(events, builder)
                        inst, status, reason, t_ms = builder.server_epoch_old, "rejected", "director_not_ready", float(events[at - 1]["t_ms"]) - 1.0
                    else:
                        at = max(self._o2_op_events(events, ids["free"])) + 1
                        inst, status, reason, t_ms = builder.server_epoch_new, "done", "", float(events[at - 1]["t_ms"]) + 1.0
                    self._o2_insert_op(
                        events, at, op_id="extra-purge-1", verb="per_purge_start", inst=inst, args=order_enq["args"],
                        t_ms=t_ms, status=status, reason=reason,
                        read=builder._pack_ext_read(strings={"job": "extra-purge-1", "state": "running", "resource": "per_purge"}, numbers={"pre_n": 4.0}) if status == "done" else {},
                    )
                    _write_events(part_dir, events)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08="purge_extra_order")

    # =========================================================================
    # O3 (ultima ronda del tope, 22-nov): los diez hallazgos de Sol sobre O2 (`a6a68f6`), el cierre parcial de Sol 5 y
    # la aclaracion de la interfaz de la purga (brief `:650-670`). `test_neg_o3_*` dan `fail` o `missing` donde
    # corresponde; `test_pos_o3_*` son evidencia honesta que debe pasar. Los reproductores de Sol son datos: estos
    # tests se escriben desde cero.
    # =========================================================================

    _O3_RAG_PID = "1900011:-1900012:1900013:-1900014"
    _O3_FOREIGN_PID = "1600301:-1600302:1600303:-1600304"

    @staticmethod
    def _o3_tree_ent(b: Any, plan: dict[str, Any], lid: str) -> dict[str, Any]:
        pid = b.entities_by_lid[lid]["pers_id"]
        return next(e for e in plan["tree"] if e["pers_id"] == pid)

    @staticmethod
    def _o3_insert_after_pre(rows: list[dict[str, Any]], extra: list[dict[str, Any]]) -> None:
        at = max(i for i, r in enumerate(rows) if r["phase"] == "pre") + 1
        rows[at:at] = extra

    def _o3_rows_gloves_left_after_pre(self, b: Any, plan: dict[str, Any], lids: tuple[str, ...]) -> list[dict[str, Any]]:
        """Los guantes ``lids`` constan en `pre` (la captura inicial) y salen del arbol antes de que se resuelva su
        candidato: sin `emit` y con `result = absent` (P2c resuelve `absent` sobre el arbol del tick de resolucion)."""
        gone = [self._o3_tree_ent(b, plan, lid) for lid in lids]
        rows = b.honest_purge_rows({**plan, "tree": [e for e in plan["tree"] if all(e is not g for g in gone)]})
        self._o3_insert_after_pre(rows, [b.purge_row("pre", g) for g in gone])
        return rows

    def _o3_rag_hook(self, *, in_pre: bool, in_capture: str) -> Any:
        """Un trapo ajeno en el guante amarillo: en `pre` (captura inicial) y/o en la captura del tick de su baja
        (``in_capture``: ``"under_glove"`` cuelga del guante, ``"elsewhere"`` cuelga de los Jeans, ``""`` no sale)."""
        def hook(b: Any, plan: dict[str, Any]) -> None:
            y_ent = self._o3_tree_ent(b, plan, "b_act_1_gloves_dir")
            rag = {
                "pers_id": self._O3_RAG_PID, "class_name": "Rag", "net_id": "1:9711", "parent_net_id": y_ent["net_id"],
                "parent_pers_id": y_ent["pers_id"], "depth_n": 2.0, "owner_uid": b.director_uid,
            }
            rows = b.honest_purge_rows(plan)  # el trapo no esta en el arbol del plan: el guante resulta elegible
            if in_pre:
                self._o3_insert_after_pre(rows, [b.purge_row("pre", rag)])
            if in_capture:
                if in_capture == "elsewhere":
                    jeans = next(e for e in plan["tree"] if e["class_name"] == "Jeans_Blue")
                    rag = {**rag, "parent_net_id": jeans["net_id"], "parent_pers_id": jeans["pers_id"], "depth_n": 1.0}
                at = next(i for i, r in enumerate(rows) if r["phase"] == "emit" and r["pers_id"] == y_ent["pers_id"])
                rows.insert(at, b.purge_row("emit", rag))
            plan["rows"] = rows
        return hook

    def _o3_rag_seen_in(self, part_dir: Path, builder: "_SyntheticPartBuilder", tags: tuple[str, ...]) -> None:
        for tag in tags:
            self._e9_add_rows_to_census(
                part_dir, tag, [self._e9_director_row(builder, "Rag", "1:9711", self._O3_RAG_PID, "Cargo:0:2:0")]
            )

    def _o3_edit_result(self, part_dir: Path, op_id: str, edit: Any) -> None:
        events = _read_events(part_dir)
        n = 0
        for ev in events:
            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                if res.get("op_id") == op_id:
                    page = self._e9_page(res)
                    edit(page)
                    self._e9_store(res, page)
                    n += 1
        self.assertEqual(n, 1, msg=op_id)
        _write_events(part_dir, events)

    @staticmethod
    def _o3_drop_deliveries(events: list[dict[str, Any]], op_ids: set[str]) -> list[dict[str, Any]]:
        """Quita las entregas (el `poll` que lleva la orden, o su `deliver`) y conserva `enq` y resultado."""
        return [
            ev for ev in events
            if not (ev.get("ev") == "poll" and any(o.get("op_id") in op_ids for o in ev.get("ops") or []))
            and not (ev.get("ev") == "deliver" and ev.get("op_id") in op_ids)
        ]

    def _o3_transition_op_ids(self, events: list[dict[str, Any]], builder: "_SyntheticPartBuilder", lids: tuple[str, ...]) -> set[str]:
        nids = {builder.entities_by_lid[lid]["net_id"] for lid in lids}
        ids = {res["op_id"] for res in self._e9_results(events, "per_child_transition") if self._e9_page(res).strs.get("net_id") in nids}
        self.assertEqual(len(ids), len(lids))
        return ids

    # ---- H1: un `absent` legitimo no da INCONCLUSO ----------------------------------------------------------

    def test_pos_o3_h1_absent_of_a_glove_that_was_in_pre_passes(self) -> None:
        """H1 (Sol sobre O2): `pre` es la captura inicial. Un guante que consta en `pre` y sale del arbol antes de que se
        resuelva su candidato, sin `emit`, con `result = absent` y ausente en t5 con el director cubierto -> PASA, no
        INCONCLUSO (P2c resuelve `absent` sobre el arbol del tick de resolucion, `DSBX_QA_X_Persist.c:1570-1574`)."""
        for name, lids, results in (
            ("yellow_glove_left_the_tree_after_pre", ("b_act_1_gloves_dir",), ["deleted", "absent"]),
            ("both_gloves_left_the_tree_after_pre", ("ac_act_1_gloves_dir", "b_act_1_gloves_dir"), ["absent", "absent"]),
        ):
            def hook(b: Any, plan: dict[str, Any], lids: tuple[str, ...] = lids) -> None:
                plan["rows"] = self._o3_rows_gloves_left_after_pre(b, plan, lids)

            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    rows = self._e9_purge_rows(part_dir)
                    self.assertEqual([r["result"] for r in rows if r["phase"] == "result"], results)
                    for lid in lids:
                        pid = builder.entities_by_lid[lid]["pers_id"]
                        self.assertIn(pid, {r["pers_id"] for r in rows if r["phase"] == "pre"})
                        self.assertNotIn(pid, {r["pers_id"] for r in rows if r["phase"] == "emit"})
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")
                    self.assertEqual(verdict["verdict"], "PASA", msg=name)

    def test_neg_o3_h1_absent_after_pre_is_contrasted_with_emissions_and_later_coverage(self) -> None:
        """H1, negativas: el `absent` de un guante de `pre` se contrasta con las emisiones y con lo observado despues. Con
        una baja suya en el recibo -> `missing` (`purge_result_contradicts_baja`); si aparece despues en el director (t5)
        -> `fail` (`purge_remnant`); con el director ilegible en t5 la ausencia no se acredita -> `missing`, sin `fail`."""
        def yellow_absent(b: Any, plan: dict[str, Any]) -> None:
            plan["rows"] = self._o3_rows_gloves_left_after_pre(b, plan, ("b_act_1_gloves_dir",))

        def absent_with_its_baja(b: Any, plan: dict[str, Any]) -> None:
            rows = self._o3_rows_gloves_left_after_pre(b, plan, ("b_act_1_gloves_dir",))
            y_ent = self._o3_tree_ent(b, plan, "b_act_1_gloves_dir")
            at = next(i for i, r in enumerate(rows) if r["phase"] == "result" and r["pers_id"] == y_ent["pers_id"])
            rows.insert(at, b.purge_row(
                "emit", y_ent, emit_tick_ms=plan["start_tick_ms"] + 160.0, lease_age_ms=400.0, lease_limit_ms=3000.0,
            ))
            plan["rows"] = rows

        variants = (
            ("absent_with_its_own_baja", absent_with_its_baja, "", {"PER-08": "missing"}, "purge_result_contradicts_baja"),
            ("absent_but_in_the_director_in_t5", yellow_absent, "remnant", {"PER-08": "fail"}, "purge_remnant:b_act_1_gloves_dir"),
            ("absent_with_the_director_unreadable_in_t5", yellow_absent, "unreadable", None, ""),
        )
        for name, hook, t5_edit, expected, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    if t5_edit == "remnant":
                        self._e9_add_rows_to_census(
                            part_dir, "t5_post_restart_census:area_b", [self._o2_glove_row(builder, "b_act_1_gloves_dir", "1:9801")]
                        )
                    elif t5_edit == "unreadable":
                        self._e9_director_gone(part_dir, ("area_a", "area_b"), present=1, readable=0)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    if expected is None:
                        self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=f"{name}:{_only_non_pass(verdict)}")
                        self.assertEqual(_checks_by_id(verdict)["PER-08"]["status"], "missing", msg=name)
                        self.assertEqual(verdict["exit_code"], 2, msg=name)
                    else:
                        self._e9_expect(verdict, expected, name, PER_08=needle)

    # ---- H2: un objeto conservado no da FALLA por perdida ----------------------------------------------------

    def test_pos_o3_h2_object_out_of_the_tick_capture_and_seen_after_is_not_a_loss(self) -> None:
        """H2 (Sol sobre O2): un trapo cuelga del guante amarillo en `pre`; en la captura del tick de su baja ya no cuelga
        de el (no sale, o sale bajo los Jeans), y los dos censos del testigo t5 lo muestran despues con el mismo `net_id`
        y `pers_id` -> PASA: el arrastre se atribuye con la captura del tick y la supervivencia, con lo observado en t5."""
        for name, in_capture in (("rag_out_of_the_capture", ""), ("rag_under_the_jeans_in_the_capture", "elsewhere")):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=self._o3_rag_hook(in_pre=True, in_capture=in_capture))
                    self._o3_rag_seen_in(part_dir, builder, ("t5_witness_pre_census:area_b", "t5_witness_post_census:area_b"))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")

    def test_neg_o3_h2_dragged_or_unaccounted_object(self) -> None:
        """H2, negativas: el trapo cuelga del guante en la captura del tick de su baja y no se ve despues -> `fail`
        (borrado con el padre); solo en `pre`, fuera de la captura y sin verse despues -> `missing`
        (`purge_foreign_unaccounted:Rag`), nunca `fail`; y con el director ilegible en t5 -> `missing`."""
        variants = (
            ("rag_in_the_tick_capture_lost", "under_glove", False, "fail", "purge_foreign_lost_with_parent:Rag"),
            ("rag_only_in_pre_never_seen_after", "", False, "missing", "purge_foreign_unaccounted:Rag"),
            ("rag_only_in_pre_director_unreadable_in_t5", "", True, "missing", ""),
        )
        for name, in_capture, unreadable, status, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=self._o3_rag_hook(in_pre=True, in_capture=in_capture))
                    if unreadable:
                        self._e9_director_gone(part_dir, ("area_a", "area_b"), present=1, readable=0)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-08"]["status"], status, msg=f"{name}:{_only_non_pass(verdict)}")
                    if needle:
                        self.assertIn(needle, c_map["PER-08"]["detail"], msg=f"{name}:{c_map['PER-08']['detail']}")
                    if status == "missing":
                        self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)
                    else:
                        self.assertEqual(_only_non_pass(verdict), {"PER-08": "fail"}, msg=name)

    # ---- H3: un `pers_id` ambiguo no es un remanente acreditado ----------------------------------------------

    def test_neg_o3_h3_ambiguous_pers_id_is_not_an_accredited_remnant(self) -> None:
        """H3 (Sol sobre O2): la unicidad se resuelve antes de declarar el remanente. Dos guantes con el `pers_id` del
        amarillo y `net_id` distintos en `pre` y en t5 (la purga registra `ambiguous` y no borra) -> `missing`, no `fail`;
        igual si en t5 solo queda uno de los dos de `pre`, o si tras la baja del beige aparecen dos con su `pers_id` en
        t5 de area_a (PER-07 y PER-08). Control: un remanente unico sigue en `fail`."""
        def second_yellow(b: Any, plan: dict[str, Any]) -> None:
            y_ent = self._o3_tree_ent(b, plan, "b_act_1_gloves_dir")
            plan["tree"].append({**y_ent, "net_id": "1:9721"})

        variants = (
            ("two_yellow_gloves_in_pre_and_t5", second_yellow, "area_b", ("b_act_1_gloves_dir",), ("1:YELLOW", "1:9721"),
             {"PER-08": "missing"}, "purge_remnant_ambiguous:b_act_1_gloves_dir"),
            ("two_in_pre_one_left_in_t5", second_yellow, "area_b", ("b_act_1_gloves_dir",), ("1:9721",),
             {"PER-08": "missing"}, "purge_remnant_ambiguous:b_act_1_gloves_dir"),
            ("beige_deleted_then_two_copies_in_t5", None, "area_a", ("ac_act_1_gloves_dir",), ("1:9731", "1:9732"),
             {"PER-07": "missing", "PER-08": "missing"}, "purge_remnant_ambiguous:ac_act_1_gloves_dir"),
            ("control_unique_remnant_still_fails", None, "area_b", ("b_act_1_gloves_dir",), ("1:9741",),
             {"PER-08": "fail"}, "purge_remnant:b_act_1_gloves_dir"),
        )
        for name, hook, area, (lid,), nids, expected, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    rows = self._e9_purge_rows(part_dir)
                    if hook is second_yellow:
                        self.assertIn("ambiguous", [r["result"] for r in rows if r["phase"] == "result"])
                    pid = builder.entities_by_lid[lid]["pers_id"]
                    pre_nid = next((r["net_id"] for r in rows if r["phase"] == "pre" and r["pers_id"] == pid), "")
                    extra = [self._o2_glove_row(builder, lid, pre_nid if nid == "1:YELLOW" else nid) for nid in nids]
                    self._e9_add_rows_to_census(part_dir, f"t5_post_restart_census:{area}", extra)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, expected, name, PER_08=needle)

    def test_pos_o3_h3_one_entity_seen_in_several_windows_is_not_ambiguous(self) -> None:
        """Control de H3: la misma entidad vista en varias ventanas (`pre`, censos t5 del reinicio y del testigo y t6, con
        el mismo `net_id`) no es un `pers_id` repetido. El guante beige basal junto al QA de su clase, con los dos guantes
        de vuelta o solo el beige -> PASA."""
        for name, returning in (("both_gloves_return", None), ("only_the_beige_glove_returns", ("ac_act_1_gloves_dir",))):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, baseline_sentinel_glove=True, purge_returning=returning)
                    base = next(r for r in builder.baseline_dir_rows if r["class_name"] == "WorkingGloves_Beige")
                    self.assertIn(base["net_id"], {r["net_id"] for r in self._e9_purge_rows(part_dir) if r["phase"] == "pre"})
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")

    # ---- H4: la identidad de cada baja ------------------------------------------------------------------------

    def test_neg_o3_h4_baja_identity_is_crossed_with_pre_capture_and_result(self) -> None:
        """H4 (Sol sobre O2): cada baja se cruza por la identidad del epoch nuevo con `pre`, con la captura de su tick y
        con su `result`. Sin `net_id` en la baja y en su `deleted` -> `missing`; su `net_id` apunta a la Apple basal con
        el `pers_id` del guante -> `missing`; un `net_id` que no esta en `pre` -> `missing`; un `deleted` con otro
        `net_id` que su baja -> `missing`. Un trapo que aun cuelga del guante en la captura del tick, aunque sobreviva
        en t5 -> `fail` (un padre solo se borra fisicamente vacio, arbitraje 2)."""
        def edit_yellow(fn: Any, phases: tuple[str, ...] = ("emit", "result")) -> Any:
            def hook(b: Any, plan: dict[str, Any]) -> None:
                pid = b.entities_by_lid["b_act_1_gloves_dir"]["pers_id"]
                rows = b.honest_purge_rows(plan)
                apple = next(e for e in plan["tree"] if e["class_name"] == "Apple")
                for r in rows:
                    if r["pers_id"] == pid and r["phase"] in phases:
                        fn(r, apple)
                plan["rows"] = rows
            return hook

        def blank(r: dict[str, Any], _apple: dict[str, Any]) -> None:
            r["net_id"] = r["parent_net_id"] = ""

        def to_apple(r: dict[str, Any], apple: dict[str, Any]) -> None:
            r["net_id"], r["parent_net_id"] = apple["net_id"], apple["parent_net_id"]

        def unknown(r: dict[str, Any], _apple: dict[str, Any]) -> None:
            r["net_id"] = "1:9990"

        def other_result(r: dict[str, Any], _apple: dict[str, Any]) -> None:
            r["net_id"] = "1:9991"

        variants = (
            ("emit_and_deleted_without_net_id", edit_yellow(blank), "", "missing", "purge_baja_unidentified"),
            ("emit_net_id_points_to_the_baseline_apple", edit_yellow(to_apple), "", "missing", "purge_baja_identity_mismatch"),
            ("emit_net_id_not_in_pre", edit_yellow(unknown), "", "missing", "purge_baja_not_in_pre"),
            ("deleted_with_another_net_id", edit_yellow(other_result, ("result",)), "", "missing", "purge_result_identity_mismatch"),
            ("rag_hanging_in_the_capture_and_kept", self._o3_rag_hook(in_pre=False, in_capture="under_glove"), "rag_kept",
             "fail", "purge_baja_with_descendant:Rag"),
        )
        for name, hook, t5_edit, status, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    if t5_edit == "rag_kept":
                        self._o3_rag_seen_in(part_dir, builder, ("t5_post_restart_census:area_a", "t5_post_restart_census:area_b"))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": status}, name, PER_08=needle)

    def test_pos_o3_h4_bajas_identified_in_their_tick_captures_pass(self) -> None:
        """Control de H4: las dos bajas en ticks seguidos sin un `result` entre ellas (los `deleted` llegan despues), o la
        confirmacion del primer guante en el mismo tick que la emision del segundo (P2c confirma y emite en el mismo
        `TickPurge`) -> PASA."""
        def consecutive(b: Any, plan: dict[str, Any]) -> None:
            rows = b.honest_purge_rows(plan)
            t = plan["start_tick_ms"]
            pre = [r for r in rows if r["phase"] == "pre"]
            emits = [r for r in rows if r["phase"] == "emit"]
            results = [r for r in rows if r["phase"] == "result"]
            for k, (e, r) in enumerate(zip(emits, results)):
                e["emit_tick_ms"], r["confirm_tick_ms"] = t + 50.0 * (k + 1), t + 150.0 + 50.0 * k
            plan["rows"] = pre + emits + results

        def confirm_and_emit_in_one_tick(b: Any, plan: dict[str, Any]) -> None:
            rows = b.honest_purge_rows(plan)
            emits = [r for r in rows if r["phase"] == "emit"]
            results = [r for r in rows if r["phase"] == "result"]
            emits[1]["emit_tick_ms"] = results[0]["confirm_tick_ms"]
            results[1]["confirm_tick_ms"] = emits[1]["emit_tick_ms"] + 50.0
            plan["rows"] = rows

        for name, hook in (("consecutive_emissions_results_later", consecutive), ("confirm_and_next_emission_in_one_tick", confirm_and_emit_in_one_tick)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")

    # ---- H5: la seleccion de t0 en el contrato nuevo ------------------------------------------------------------

    def test_neg_o3_h5_t0_selection_not_ready_before_the_baseline_is_inconclusive(self) -> None:
        """H5 (Sol sobre O2): en el contrato nuevo (`players_n` en t0 y purga del runner) el uid del director solo vale si
        una seleccion lista (`players_n == 1`, uid no vacio, presente, vivo y legible) precede al primer censo basal.
        La unica respuesta de t0 sin jugador listo (`players_n = 0`, uid vacio, 0/0/0), la seleccion lista despues del
        primer censo basal, o un jugador con el inventario ilegible -> INCONCLUSO (`director_not_selected`), sin `fail`:
        el uid de un censo o de otro `per_status` ya no la suple."""
        def not_ready(page: types.SimpleNamespace) -> None:
            page.strs["director_uid"] = ""
            page.nums.update(players_n=0.0, director_present_b=0.0, director_alive_b=0.0, director_inv_readable_b=0.0)

        def unreadable(page: types.SimpleNamespace) -> None:
            page.nums.update(director_inv_readable_b=0.0)

        for name, how in (("only_t0_status_not_ready", not_ready), ("ready_after_the_first_baseline_census", "move"),
                          ("one_player_inventory_unreadable", unreadable)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    events = _read_events(part_dir)
                    t0_status = _status_op_ids(events, builder.server_epoch_old)[0]
                    if how == "move":
                        idxs = self._o2_op_events(events, t0_status)
                        moved = [events[i] for i in idxs]
                        rest = [ev for i, ev in enumerate(events) if i not in set(idxs)]
                        (job,) = list(self._e9_jobs_of(rest, {"t0_baseline_census:area_a"}))
                        enq_at = next(i for i, ev in enumerate(rest) if ev.get("ev") == "enq" and ev.get("op_id") == job)
                        for ev in moved:
                            ev["t_ms"] = float(rest[enq_at]["t_ms"])
                        _write_events(part_dir, rest[:enq_at + 3] + moved + rest[enq_at + 3:])
                    else:
                        self._o3_edit_result(part_dir, t0_status, how)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertIn("director_not_selected", verdict["reasons"], msg=f"{name}:{verdict['reasons']}")
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=name)
                    self.assertEqual(verdict["exit_code"], 2, msg=name)

    def test_pos_o3_h5_ready_selection_before_the_baseline_passes(self) -> None:
        """Control de H5: con cero jugadores se sigue esperando y la seleccion lista llega antes del basal -> PASA. Y una
        traza antigua (sin `players_n` ni purga del runner) conserva el respaldo historico del uid: no da
        `director_not_selected` (su PER-08 sigue en `missing` por la purga que no hubo)."""
        for name, seq in (("zero_then_one", (0, 1)), ("zero_zero_then_one", (0, 0, 1))):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, t0_players_n=seq)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{verdict['reasons']}")
                    self.assertEqual(verdict["verdict"], "PASA", msg=name)
        with self.subTest("historical_trace_without_players_n"):
            with tempfile.TemporaryDirectory() as tmp:
                builder, part_dir = self._e9_build(
                    tmp, "run", "historical", purge_hook=lambda _b, plan: plan.update(send_order=False),
                )
                t0_status = _status_op_ids(_read_events(part_dir), builder.server_epoch_old)[0]
                self._o3_edit_result(part_dir, t0_status, lambda page: page.nums.pop("players_n"))
                verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                self.assertNotIn("director_not_selected", verdict["reasons"])
                self._e9_expect(verdict, {"PER-08": "missing"}, "historical", PER_08="purge_not_done:no_order")

    # ---- H6: la procedencia vieja, eslabon a eslabon ------------------------------------------------------------

    def test_neg_o3_h6_old_provenance_link_missing_leaves_the_glove_unidentified(self) -> None:
        """H6 (Sol sobre O2): antes de autorizar por identidad se exige el enlace al epoch viejo del alta, la transicion
        (con su entrega) y los censos que dan la lectura. Sin las entregas de los dos `move_to_director` (con sus `enq`,
        resultados y censos), sin la del alta de scene_b o sin la de una pagina de t1_post de area_a -> la prenda queda
        sin identificar y PER-08 `missing`."""
        def drop(kind: str) -> Any:
            def edit(builder: "_SyntheticPartBuilder", events: list[dict[str, Any]]) -> list[dict[str, Any]]:
                if kind == "transitions":
                    ids = self._o3_transition_op_ids(events, builder, ("ac_act_1_gloves_dir", "b_act_1_gloves_dir"))
                elif kind == "apply_b":
                    ids = {next(
                        res["op_id"] for res in self._e9_results(events, "per_apply_scene")
                        if self._e9_page(res).strs.get("scene_id") == "scene_b"
                    )}
                else:
                    (job,) = list(self._e9_jobs_of(events, {"t1_post_transition_census:area_a"}))
                    ids = {next(res["op_id"] for res in self._e9_results(events, "job_read") if self._e9_page(res).strs.get("job") == job)}
                return self._o3_drop_deliveries(events, ids)
            return edit

        for name, kind, needle in (
            ("both_move_to_director_without_delivery", "transitions", "purge_accredited_unidentified:ac_act_1_gloves_dir:old_link:per_child_transition:no_delivery"),
            ("apply_of_scene_b_without_delivery", "apply_b", "purge_accredited_unidentified:b_act_1_gloves_dir:old_link:per_apply_scene:no_delivery"),
            ("t1_post_page_without_delivery", "page", "old_link:job_read:no_delivery"),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    _write_events(part_dir, drop(kind)(builder, _read_events(part_dir)))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08=needle)

    def test_pos_o3_h6_old_provenance_linked_in_the_real_bridge_format_passes(self) -> None:
        """Control de H6: la procedencia vieja con el formato del puente real (`enq` con `inst` nulo, `poll` con `op_ids`
        y un `deliver` por orden con el `inst` destino nulo, `result` sin `inst`; `qa/bridge_qa.py:371-378`, `:737-761`,
        `:859-867`), o con las transiciones dirigidas al epoch viejo (`enq` con su `inst`) -> PASA."""
        def real_format(builder: "_SyntheticPartBuilder", events: list[dict[str, Any]]) -> list[dict[str, Any]]:
            upto = self._new_hello_index(events, builder)
            out: list[dict[str, Any]] = []
            for i, ev in enumerate(events):
                if i >= upto or ev.get("peer") != "server":
                    out.append(ev)
                elif ev.get("ev") == "enq":
                    out.append({**ev, "inst": ev.get("inst")})
                elif ev.get("ev") == "poll" and ev.get("ops") is not None:
                    out.append({k: v for k, v in ev.items() if k != "ops"} | {"op_ids": [o["op_id"] for o in ev["ops"]], "http": 200})
                    out.extend(
                        {"ev": "deliver", "peer": "server", "inst": None, "op_id": o["op_id"], "verb": o["verb"],
                         "args": o["args"], "t_ms": ev.get("t_ms")}
                        for o in ev["ops"]
                    )
                elif ev.get("ev") == "result":
                    out.append({k: v for k, v in ev.items() if k != "inst"})
                else:
                    out.append(ev)
            return out

        def targeted_transitions(builder: "_SyntheticPartBuilder", events: list[dict[str, Any]]) -> list[dict[str, Any]]:
            ids = self._o3_transition_op_ids(events, builder, ("ac_act_1_gloves_dir", "b_act_1_gloves_dir"))
            for ev in events:
                if ev.get("ev") == "enq" and ev.get("op_id") in ids:
                    ev["inst"] = builder.server_epoch_old
            return events

        for name, edit in (("old_epoch_in_the_real_bridge_format", real_format), ("transitions_targeted_to_the_old_epoch", targeted_transitions)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    _write_events(part_dir, edit(builder, _read_events(part_dir)))
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")

    # ---- H7: la cronologia de la purga -----------------------------------------------------------------------

    def test_neg_o3_h7_purge_chronology_is_verified(self) -> None:
        """H7 (Sol sobre O2) y aclaracion, punto 2: como mucho una baja por tick, cada emision dentro de la ventana del
        trabajo, `deleted` despues de su `emit` y con `confirm_tick_ms` posterior a su `emit_tick_ms`. Dos bajas en el
        mismo tick, una baja despues del fin del trabajo, un `deleted` antes de su `emit`, una confirmacion en el tick de
        la emision o sin `confirm_tick_ms` -> `missing`. Y el cierre parcial de Sol 5: un primer ENVIO de censo t5
        rechazado (`purge_pending`) antes de la ultima lectura de la purga -> `missing`, aunque el primer trabajo
        aceptado sea posterior."""
        def edit_rows(fn: Any, **plan_kw: Any) -> Any:
            def hook(b: Any, plan: dict[str, Any]) -> None:
                plan.update(plan_kw)
                rows = b.honest_purge_rows(plan)
                fn(rows, plan)
                plan["rows"] = rows
            return hook

        def same_tick(rows: list[dict[str, Any]], _plan: dict[str, Any]) -> None:
            emits = [r for r in rows if r["phase"] == "emit"]
            emits[1]["emit_tick_ms"] = emits[0]["emit_tick_ms"]

        def after_end(rows: list[dict[str, Any]], plan: dict[str, Any]) -> None:
            plan["end_tick_ms"] = plan["start_tick_ms"] + 120.0

        def deleted_first(rows: list[dict[str, Any]], _plan: dict[str, Any]) -> None:
            e = next(i for i, r in enumerate(rows) if r["phase"] == "emit")
            rows[e], rows[e + 1] = rows[e + 1], rows[e]

        def confirm_same_tick(rows: list[dict[str, Any]], _plan: dict[str, Any]) -> None:
            e = next(i for i, r in enumerate(rows) if r["phase"] == "emit")
            rows[e + 1]["confirm_tick_ms"] = rows[e]["emit_tick_ms"]

        def confirm_missing(rows: list[dict[str, Any]], _plan: dict[str, Any]) -> None:
            for r in rows:
                if r["result"] == "deleted":
                    r["confirm_tick_ms"] = 0.0

        variants = (
            ("two_bajas_in_one_tick", edit_rows(same_tick), "purge_two_bajas_in_one_tick"),
            ("baja_after_the_end_of_the_job", edit_rows(after_end), "purge_emit_outside_the_job_window"),
            ("deleted_before_its_emit", edit_rows(deleted_first), "purge_deleted_before_its_emit"),
            ("confirmed_in_the_emission_tick", edit_rows(confirm_same_tick), "purge_confirm_not_after_emit"),
            ("deleted_without_confirm_tick", edit_rows(confirm_missing), "purge_confirm_not_after_emit"),
            ("first_t5_send_rejected_before_the_last_read", None, "purge_read_not_before_t5"),
        )
        for name, hook, needle in variants:
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    if hook is None:
                        events = _read_events(part_dir)
                        ids = self._o2_purge_op_ids(events)
                        (first_t5_job,) = list(self._e9_jobs_of(events, {"t5_post_restart_census:area_a"}))
                        t5_enq = next(ev for ev in events if ev.get("ev") == "enq" and ev.get("op_id") == first_t5_job)
                        at = min(self._o2_op_events(events, ids["reads"][-1]))
                        self._o2_insert_op(
                            events, at, op_id="o3-early-t5-send", verb="per_census_start", inst=builder.server_epoch_new,
                            args=t5_enq["args"], read={}, t_ms=float(events[at - 1]["t_ms"]), status="rejected",
                            reason="purge_pending",
                        )
                        _write_events(part_dir, events)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08=needle)

    def test_pos_o3_h7_purge_chronology_at_its_bounds_passes(self) -> None:
        """Control de H7: la ventana del trabajo incluye sus extremos. La confirmacion del ultimo guante en el tick del fin
        (P2c confirma, ve todo resuelto y cierra el trabajo en el mismo `TickPurge`) y la primera emision en el tick de
        inicio del trabajo -> PASA."""
        def confirm_at_end(b: Any, plan: dict[str, Any]) -> None:
            rows = b.honest_purge_rows(plan)
            plan["end_tick_ms"] = max(r["confirm_tick_ms"] for r in rows)
            plan["rows"] = rows

        def emit_at_start(b: Any, plan: dict[str, Any]) -> None:
            rows = b.honest_purge_rows(plan)
            next(r for r in rows if r["phase"] == "emit")["emit_tick_ms"] = plan["start_tick_ms"]
            plan["rows"] = rows

        for name, hook in (("last_confirm_at_the_end_tick", confirm_at_end), ("first_emission_at_the_start_tick", emit_at_start)):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    _builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=hook)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")

    # ---- H8: el trabajo de la orden y la rodaja contractual ---------------------------------------------------

    def test_neg_o3_h8_job_of_the_order_and_contractual_slice(self) -> None:
        """H8 (Sol sobre O2) y aclaracion, puntos 1 y 3: el `job` del acuse y de todas las lecturas es el `op_id` de la
        orden, y cada pagina es la rodaja contractual de 8 filas. Un alias en el acuse y en todas las lecturas, paginas
        de 4 filas, o 9 filas repartidas 7 + 2 -> `missing`."""
        for name in ("job_alias_in_the_ack_and_every_read", "pages_of_four_rows", "nine_rows_split_seven_and_two"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder = _SyntheticPartBuilder("run", baseline_sentinel_glove=True)
                    if name == "pages_of_four_rows":
                        builder.PURGE_PAGE_SIZE = 4
                    part_dir = builder.build_into(Path(tmp) / name)
                    events = _read_events(part_dir)
                    ids = self._o2_purge_op_ids(events)
                    if name == "job_alias_in_the_ack_and_every_read":
                        alias = "o3-purge-alias-1"
                        for ev in events:
                            holders = [ev] if ev.get("ev") == "enq" else (list(ev.get("ops") or []) if ev.get("ev") == "poll" else [])
                            for h in holders:
                                if h.get("op_id") in {*ids["reads"], ids["free"]}:
                                    u_s, u_n, u_r = _unpack(h["args"])
                                    u_s["job"] = alias
                                    h["args"] = _repack_read(u_s, u_n, u_r, h["args"])
                            for res in (ev.get("results") or []) if ev.get("ev") == "result" else []:
                                if res.get("op_id") in {ids["order"], *ids["reads"], ids["free"]}:
                                    page = self._e9_page(res)
                                    page.strs["job"] = alias
                                    self._e9_store(res, page)
                        needle = "purge_job_is_not_the_order_op_id"
                    elif name == "pages_of_four_rows":
                        needle = "purge_pages_incomplete"
                    else:
                        all_rows = self._e9_purge_rows(part_dir)
                        self.assertEqual(len(all_rows), 9)
                        for res in self._e9_purge_reads(events):
                            page = self._e9_page(res)
                            if page.strs.get("state") != "running":
                                page.rows = copy.deepcopy(all_rows[:7] if int(round(page.nums["page_n"])) == 0 else all_rows[7:])
                                self._e9_store(res, page)
                        needle = "purge_pages_incomplete"
                    _write_events(part_dir, events)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertNotIn("fail", {c["status"] for c in verdict["checks"]}, msg=f"{name}:{_only_non_pass(verdict)}")
                    c_map = _checks_by_id(verdict)
                    self.assertEqual(c_map["PER-08"]["status"], "missing", msg=name)
                    self.assertIn(needle, c_map["PER-08"]["detail"], msg=f"{name}:{c_map['PER-08']['detail']}")

    def test_pos_o3_h8_identical_rereads_and_full_pages_pass(self) -> None:
        """Control de H8: una relectura identica de una pagina es valida y no cuenta dos veces (las dos paginas de 9 filas
        releidas), y 16 filas en dos paginas llenas de 8 -> PASA."""
        def sixteen_rows(b: Any, plan: dict[str, Any]) -> None:
            for k in range(8):
                plan["tree"].append({
                    "pers_id": f"{1650001 + k}:-1650002:1650003:-1650004", "class_name": "Rag", "net_id": f"1:96{k:02d}",
                    "parent_net_id": "1:2", "parent_pers_id": "", "depth_n": 0.0, "owner_uid": b.director_uid,
                })

        for name in ("identical_rereads_of_both_pages", "sixteen_rows_in_two_full_pages"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    if name == "identical_rereads_of_both_pages":
                        builder, part_dir = self._e9_build(tmp, "run", name, baseline_sentinel_glove=True)
                        events = _read_events(part_dir)
                        for k, res in enumerate([r for r in self._e9_purge_reads(events) if self._e9_page(r).strs.get("state") != "running"]):
                            idxs = self._o2_op_events(events, res["op_id"])
                            copies = copy.deepcopy([events[i] for i in idxs])
                            new_id = f"o3-reread-{k}"
                            for ev in copies:
                                if "op_id" in ev:
                                    ev["op_id"] = new_id
                                for o in ev.get("ops") or []:
                                    o["op_id"] = new_id
                                for r in ev.get("results") or []:
                                    r["op_id"] = new_id
                            at = max(self._o2_op_events(events, res["op_id"])) + 1
                            events[at:at] = copies
                        _write_events(part_dir, events)
                    else:
                        builder, part_dir = self._e9_build(tmp, "run", name, purge_hook=sixteen_rows)
                        self.assertEqual(len(self._e9_purge_rows(part_dir)), 16)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")

    # ---- H9: toda la espera de `per_status` ligada al epoch nuevo ---------------------------------------------

    def _o3_insert_wait_status(self, builder: "_SyntheticPartBuilder", events: list[dict[str, Any]], op_id: str,
                               *, server_epoch: str | None = None) -> None:
        """Inserta antes de la validacion un `per_status` de la espera con «director aun no listo» (0/0/0), dirigido al
        epoch nuevo y con el mismo `tick_ms` que la primera lectura (N49)."""
        first_new = _status_op_ids(events, builder.server_epoch_new)[0]
        res = next(r for ev in events if ev.get("ev") == "result" for r in ev.get("results") or [] if r.get("op_id") == first_new)
        page = self._e9_page(res)
        page.nums.update(director_present_b=0.0, director_alive_b=0.0, director_inv_readable_b=0.0)
        if server_epoch is not None:
            page.strs["server_epoch"] = server_epoch
        enq = next(ev for ev in events if ev.get("ev") == "enq" and ev.get("op_id") == first_new)
        at = min(self._o2_op_events(events, first_new))
        self._o2_insert_op(
            events, at, op_id=op_id, verb="per_status", inst=builder.server_epoch_new, args=enq["args"],
            read=_repack_read(page.strs, page.nums, page.rows, res["read"]), t_ms=float(events[at - 1]["t_ms"]) + 0.5,
            tick_ms=float(page.nums["tick_ms"]),
        )

    def test_neg_o3_h9_every_per_status_of_the_wait_is_linked(self) -> None:
        """H9 (Sol sobre O2) y aclaracion, punto 5: toda la espera de `per_status` entre el `hello` nuevo y la orden se
        liga al epoch nuevo, no solo la respuesta que valida. Un `per_status` «aun no listo» antes de la validacion sin su
        entrega, encolado sin `target_inst`, o cuya respuesta trae otro `server_epoch` -> PER-08 `missing`."""
        for name, needle in (
            ("not_ready_status_without_delivery", "purge_epoch_unlinked:per_status_wait:no_delivery"),
            ("not_ready_status_enqueued_without_target", "purge_epoch_unlinked:per_status_wait:enq_inst"),
            ("not_ready_status_of_another_epoch", "purge_epoch_unlinked:per_status_wait:server_epoch"),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    events = _read_events(part_dir)
                    self._o3_insert_wait_status(
                        builder, events, "o3-wait-1",
                        server_epoch="srv-epoch-9999" if name == "not_ready_status_of_another_epoch" else None,
                    )
                    if name == "not_ready_status_without_delivery":
                        events = self._o3_drop_deliveries(events, {"o3-wait-1"})
                    elif name == "not_ready_status_enqueued_without_target":
                        next(ev for ev in events if ev.get("ev") == "enq" and ev.get("op_id") == "o3-wait-1").pop("inst")
                    _write_events(part_dir, events)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, {"PER-08": "missing"}, name, PER_08=needle)

    def test_pos_o3_h9_wait_with_several_linked_per_status_passes(self) -> None:
        """Control de H9: dos `per_status` «aun no listo» antes del que valida, todos ligados al epoch nuevo, con el
        formato del constructor o con el del puente real (`poll` con `op_ids`, `deliver` y `result` sin `inst`) -> PASA."""
        for name in ("two_not_ready_status_then_ready", "two_not_ready_status_in_the_real_bridge_format"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    events = _read_events(part_dir)
                    self._o3_insert_wait_status(builder, events, "o3-wait-2")
                    self._o3_insert_wait_status(builder, events, "o3-wait-1")
                    if name.endswith("real_bridge_format"):
                        targets = {"o3-wait-1", "o3-wait-2", _status_op_ids(events, builder.server_epoch_new)[2]}
                        out: list[dict[str, Any]] = []
                        for ev in events:
                            if ev.get("ev") == "poll" and any(o.get("op_id") in targets for o in ev.get("ops") or []):
                                out.append({k: v for k, v in ev.items() if k != "ops"} | {"op_ids": [o["op_id"] for o in ev["ops"]], "http": 200})
                                out.extend(
                                    {"ev": "deliver", "peer": "server", "inst": ev["inst"], "op_id": o["op_id"], "verb": o["verb"],
                                     "args": o["args"], "t_ms": ev.get("t_ms")}
                                    for o in ev["ops"]
                                )
                            elif ev.get("ev") == "result" and any(r.get("op_id") in targets for r in ev.get("results") or []):
                                out.append({k: v for k, v in ev.items() if k != "inst"})
                            else:
                                out.append(ev)
                        events = out
                    _write_events(part_dir, events)
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")

    # ---- H10: lo observado despues de la purga, tambien en t6 ---------------------------------------------------

    def test_neg_o3_h10_post_purge_observations_include_t6(self) -> None:
        """H10 (Sol sobre O2) y aclaracion, punto 4: un remanente o una centinela sin atribuir se juzgan en cualquier censo
        posterior a la purga, tambien t6. Solo en t6 de area_a: un guante amarillo en el director con un `pers_id` ajeno
        al basal y a las acreditadas -> `missing`; una centinela con `pers_id` nulo -> `missing`; el guante amarillo
        acreditado -> `fail` (PER-08 por identidad y PER-09 como superviviente de la limpieza)."""
        for name, cls, pid_of, slot, expected, needle in (
            ("foreign_yellow_glove_only_in_t6", "WorkingGloves_Yellow", "foreign", "Gloves", {"PER-08": "missing"},
             "director_sentinel_unattributable:WorkingGloves_Yellow"),
            ("sentinel_with_a_null_pers_id_only_in_t6", "RadarCap_Black", "null", "Headgear", {"PER-08": "missing"},
             "director_sentinel_unattributable:RadarCap_Black"),
            ("accredited_yellow_glove_only_in_t6", "WorkingGloves_Yellow", "accredited", "Gloves",
             {"PER-08": "fail", "PER-09": "fail"}, "purge_remnant:b_act_1_gloves_dir"),
        ):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    builder, part_dir = self._e9_build(tmp, "run", name)
                    pid = {"foreign": self._O3_FOREIGN_PID, "null": "0:0:0:0",
                           "accredited": builder.entities_by_lid["b_act_1_gloves_dir"]["pers_id"]}[pid_of]
                    self._e9_add_rows_to_census(
                        part_dir, "t6_post_cleanup_census:area_a", [self._e9_director_row(builder, cls, "1:9811", pid, slot)]
                    )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self._e9_expect(verdict, expected, name, PER_08=needle)

    def test_pos_o3_h10_attributable_items_in_t6_pass(self) -> None:
        """Control de H10: en t6, el guante beige basal (centinela del basal que se conserva) o una prenda de inicio de
        clase no centinela con un `pers_id` ajeno -> PASA."""
        for name in ("baseline_sentinel_glove_in_t6", "start_garment_in_t6"):
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as tmp:
                    if name == "baseline_sentinel_glove_in_t6":
                        builder, part_dir = self._e9_build(tmp, "run", name, baseline_sentinel_glove=True)
                        base = next(r for r in builder.baseline_dir_rows if r["class_name"] == "WorkingGloves_Beige")
                        t6_rows = [r for res in self._e9_results(_read_events(part_dir), "job_read")
                                   for r in self._e9_page(res).rows if r.get("net_id") == base["net_id"]]
                        self.assertTrue(t6_rows)
                    else:
                        builder, part_dir = self._e9_build(tmp, "run", name)
                        self._e9_add_rows_to_census(
                            part_dir, "t6_post_cleanup_census:area_a",
                            [self._e9_director_row(builder, "TShirt_Green", "1:9821", self._O3_FOREIGN_PID, "Body")],
                        )
                    verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
                    self.assertEqual(_only_non_pass(verdict), {}, msg=f"{name}:{json.dumps(verdict['checks'])}")


if __name__ == "__main__":
    unittest.main()
