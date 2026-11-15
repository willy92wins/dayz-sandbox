"""Tests offline for spike S-perf evaluator (qa/s_perf_eval.py).

Covers:
- PRF-01..PRF-06 checks on synthetic evidence per s_perf_eval.py schema
- E9 anti-fabrication negatives (all must FAIL or INCONCLUSO, never PASS)
- 11 mutants from EXPECTED_MUTANTS with must_fail_checks in "fail", never "missing"
- §8.1 offline tests: k* derivation, N5 8 subcases, N6, geometry, modset equality
- test_e2e_* tests that fail now (skeleton implementation)

Run: python -m unittest discover -s qa/tests -t qa -p test_s_perf_offline.py
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import secrets
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import f03_common
import gate_core
import s_perf_eval
import s_perf_mutants
import wire

PASA, FALLA, INCONCLUSO = 0, 1, 2  # codigos de gate_core.verdict_name
from tests.synth import _write_jsonl


QA_DIR = Path(__file__).resolve().parents[1]
DEV_ROOT = QA_DIR.parent
FIXTURE_PATH = QA_DIR / "fixtures" / "s_perf_modset.json"

# --- Constants from evaluator and brief ---
STEP_SPEC = s_perf_eval.STEP_SPEC
STEP_ORDER = s_perf_eval.STEP_ORDER
WINDOW_NCOL = s_perf_eval.WINDOW_NCOL
SNAP_NCOL = s_perf_eval.SNAP_NCOL
PERF_VERBS = s_perf_eval.PERF_VERBS
EXPECTED_WINDOW_ROWS = s_perf_eval.EXPECTED_WINDOW_ROWS
WARMUP_MIN_MS = s_perf_eval.WARMUP_MIN_MS
WINDOW_MIN_MS = s_perf_eval.WINDOW_MIN_MS
WINDOW_MAX_MS = s_perf_eval.WINDOW_MAX_MS
SAMPLE_STEP_MS = s_perf_eval.SAMPLE_STEP_MS
SAMPLE_DT_MIN_MS = s_perf_eval.SAMPLE_DT_MIN_MS
SAMPLE_DT_MAX_MS = s_perf_eval.SAMPLE_DT_MAX_MS
FPS_REL_TOL = s_perf_eval.FPS_REL_TOL
DTSUM_DRIFT_TOL = s_perf_eval.DTSUM_DRIFT_TOL
HARNESS_DRIFT_TOL = s_perf_eval.HARNESS_DRIFT_TOL
FLOOR_FPS = s_perf_eval.FLOOR_FPS
ROAM_MIN_STEP_M = s_perf_eval.ROAM_MIN_STEP_M
CREATURES_MIN_STEP_M = s_perf_eval.CREATURES_MIN_STEP_M
ROAM_QUARTER_MIN_M = s_perf_eval.ROAM_QUARTER_MIN_M
ROAM_TOTAL_MIN_M = s_perf_eval.ROAM_TOTAL_MIN_M
ROAM_SUBSTEP_MIN_M = s_perf_eval.ROAM_SUBSTEP_MIN_M
ROAM_MIN_WP_LEGS = s_perf_eval.ROAM_MIN_WP_LEGS
CREATURES_QUARTER_MIN_M = s_perf_eval.CREATURES_QUARTER_MIN_M
CREATURES_TOTAL_MIN_M = s_perf_eval.CREATURES_TOTAL_MIN_M
EMOTE_QUARTER_MIN_COMPLETIONS = s_perf_eval.EMOTE_QUARTER_MIN_COMPLETIONS
EMOTE_TOTAL_MIN_COMPLETIONS = s_perf_eval.EMOTE_TOTAL_MIN_COMPLETIONS
EXPECTED_SNAP_CHECKPOINTS = s_perf_eval.EXPECTED_SNAP_CHECKPOINTS
N5_REQUIRED_REASONS = s_perf_eval.N5_REQUIRED_REASONS
SPAWN_FLAGS_OBJ = s_perf_eval.SPAWN_FLAGS_OBJ
SPAWN_FLAGS_AI = s_perf_eval.SPAWN_FLAGS_AI
FORBIDDEN_SPAWN_FLAG = s_perf_eval.FORBIDDEN_SPAWN_FLAG
EMOTE_CB_CMD_CLAP = s_perf_eval.EMOTE_CB_CMD_CLAP
CENTER_POS = s_perf_eval.CENTER_POS
DIRECTOR_POS = s_perf_eval.DIRECTOR_POS
CLEAR_RADIUS_M = s_perf_eval.CLEAR_RADIUS_M
MAX_DIRECTOR_DIST_M = s_perf_eval.MAX_DIRECTOR_DIST_M
MIN_GROUP_SEP_M = s_perf_eval.MIN_GROUP_SEP_M
CREATURE_SWAY_RADIUS_M = s_perf_eval.CREATURE_SWAY_RADIUS_M
ROAM_SQUARE_RADIUS_M = s_perf_eval.ROAM_SQUARE_RADIUS_M

# Load canonical fixture
with FIXTURE_PATH.open("r", encoding="utf-8") as f:
    CANONICAL_FIXTURE = json.load(f)

CANONICAL_WORLD = CANONICAL_FIXTURE["world"]
CANONICAL_ADDONS_CSV = CANONICAL_FIXTURE["loaded_addons_csv"]
CANONICAL_PATCHES_N = CANONICAL_FIXTURE["patches_n"]
CANONICAL_MODSET_SIG = CANONICAL_FIXTURE["modset_sig"]
REQUIRED_CLASSES = CANONICAL_FIXTURE["required_classes"]


# ==============================================================================
# Evidence Constructors (synthetic bridge.jsonl, samples, etc.)
# ==============================================================================

def _now() -> float:
    return 1000.0


def _op_id() -> str:
    return f"{secrets.token_hex(8)}-{secrets.randbits(16)}"


def _pack_payload(
    scalars_str: dict | None = None,
    scalars_num: dict | None = None,
    num_cols: list | None = None,
    str_cols: list | None = None,
    row_dicts: list | None = None,
) -> dict:
    return wire.pack_payload(
        scalars_str=scalars_str,
        scalars_num=scalars_num,
        num_cols=num_cols,
        str_cols=str_cols,
        row_dicts=row_dicts,
    )


def _unpacked_payload(
    str_vals: dict | None = None,
    num_vals: dict | None = None,
    rows: list | None = None,
    ncol: list | None = None,
    scol: list | None = None,
) -> dict:
    return {
        "str": str_vals or {},
        "num": num_vals or {},
        "ncol": ncol or [],
        "scol": scol or [],
        "rows": rows or [],
    }


def _bridge_record(
    verb: str,
    peer: str = "server",
    status: str = "done",
    reason: str = "",
    op_id: str | None = None,
    issued_ms: float | None = None,
    ack_ms: float | None = None,
    read_ms: float | None = None,
    req_payload: dict | None = None,
    res_payload: dict | None = None,
    ack_payload: dict | None = None,
    **extra,
) -> dict:
    oid = op_id or _op_id()
    now = _now()
    i_ms = issued_ms or now
    a_ms = ack_ms or now + 1.0
    r_ms = read_ms or now + 2.0
    ack = ack_payload or {"status": "ok" if status == "done" else "rejected", "reason": reason}
    read_env = {
        "status": status,
        "reason": reason,
        "has": ["payload"] if status == "done" else [],
    }
    if res_payload:
        read_env.update(res_payload)
    return {
        "op_id": oid,
        "verb": verb,
        "peer": peer,
        "target_inst": peer,
        "issued_ms": i_ms,
        "ack_ms": a_ms,
        "read_ms": r_ms,
        "ack": ack,
        "read": read_env,
        "args": req_payload or {},
        "payload_req": req_payload or {},
        "payload_res": res_payload or {},
        **extra,
    }


def _preflight_done(
    *,
    op_id: str | None = None,
    world_name: str = CANONICAL_WORLD,
    loaded_addons_csv: str = CANONICAL_ADDONS_CSV,
    modset_sig: str = CANONICAL_MODSET_SIG,
    is_server_b: int = 1,
    players_n: int = 1,
    cfg_patches_total_n: int = CANONICAL_PATCHES_N,
    center_y_m: float = 300.0,
    director_x_m: float = DIRECTOR_POS[0],
    director_z_m: float = DIRECTOR_POS[2],
    director_orig_allow_damage_b: int = 1,
    director_allow_damage_b: int = 0,
    overcast: float = 0.0,
    rain: float = 0.0,
    fog: float = 0.0,
    census_dynamic_n: int = 0,
    census_foreign_n: int = 0,
    tick_ms: float = 1000.0,
    frame: int = 100,
    avg_fps_now: float = 58.0,
    req_expected_world: str = CANONICAL_WORLD,
    req_expected_modset_sig: str = CANONICAL_MODSET_SIG,
    req_required_classes_csv: str = CANONICAL_FIXTURE["required_classes_csv"],
    req_center_x_m: float = CENTER_POS[0],
    req_center_z_m: float = CENTER_POS[2],
    req_clear_radius_m: float = CLEAR_RADIUS_M,
    req_fix_weather_b: int = 1,
    issued_ms: float | None = None,
    ack_ms: float | None = None,
    read_ms: float | None = None,
) -> dict:
    req = _pack_payload(
        scalars_str={
            "expected_world": req_expected_world,
            "required_classes_csv": req_required_classes_csv,
            "expected_modset_sig": req_expected_modset_sig,
        },
        scalars_num={
            "center_x_m": req_center_x_m,
            "center_z_m": req_center_z_m,
            "clear_radius_m": req_clear_radius_m,
            "fix_weather_b": req_fix_weather_b,
        },
    )
    res = _pack_payload(
        scalars_str={
            "world_name": world_name,
            "loaded_addons_csv": loaded_addons_csv,
            "modset_sig": modset_sig,
        },
        scalars_num={
            "is_server_b": is_server_b,
            "players_n": players_n,
            "cfg_patches_total_n": cfg_patches_total_n,
            "center_y_m": center_y_m,
            "director_x_m": director_x_m,
            "director_z_m": director_z_m,
            "director_orig_allow_damage_b": director_orig_allow_damage_b,
            "director_allow_damage_b": director_allow_damage_b,
            "overcast": overcast,
            "rain": rain,
            "fog": fog,
            "census_dynamic_n": census_dynamic_n,
            "census_foreign_n": census_foreign_n,
            "tick_ms": tick_ms,
            "frame": frame,
            "avg_fps_now": avg_fps_now,
        },
    )
    return _bridge_record(
        verb="perf_preflight",
        peer="server",
        status="done",
        reason="",
        op_id=op_id,
        req_payload=req,
        res_payload=res,
        issued_ms=issued_ms,
        ack_ms=ack_ms,
        read_ms=read_ms,
    )


def _preflight_rejected(
    *,
    op_id: str | None = None,
    reason: str = "modset_mismatch",
    req_expected_modset_sig: str = CANONICAL_MODSET_SIG,
) -> dict:
    req = _pack_payload(
        scalars_str={
            "expected_world": CANONICAL_WORLD,
            "required_classes_csv": CANONICAL_FIXTURE["required_classes_csv"],
            "expected_modset_sig": req_expected_modset_sig,
        },
        scalars_num={
            "center_x_m": CENTER_POS[0],
            "center_z_m": CENTER_POS[2],
            "clear_radius_m": CLEAR_RADIUS_M,
            "fix_weather_b": 1,
        },
    )
    res = _unpacked_payload()
    return _bridge_record(
        verb="perf_preflight",
        peer="server",
        status="rejected",
        reason=reason,
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _step_apply_done(
    step_id: str,
    *,
    op_id: str | None = None,
    modset_sig: str = CANONICAL_MODSET_SIG,
    cleanup_status: str = "clean",
    requested_counts: dict | None = None,
    alive_counts: dict | None = None,
    director_orig_allow_damage_b: int = 1,
    director_allow_damage_b: int = 0,
    apply_cost_ms: float = 5.0,
    tick_ms: float = 2000.0,
    frame: int = 200,
    skipped_foreign_containers_n: int = 0,
    preserved_ancestors_n: int = 0,
) -> dict:
    spec = STEP_SPEC.get(step_id, STEP_SPEC["fixture"])
    req_counts = requested_counts or {
        "objects_n": spec["objects_n"],
        "infected_n": spec["infected_n"],
        "animals_n": spec["animals_n"],
        "actors_n": spec["actors_n"],
        "wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
    }
    alive = alive_counts or {
        "objects_alive_n": spec["objects_n"],
        "infected_alive_n": spec["infected_n"],
        "animals_alive_n": spec["animals_n"],
        "actors_alive_n": spec["actors_n"],
        "roots_alive_n": spec["roots_n"],
        "children_alive_n": spec["children_n"],
        "entities_alive_n": spec["entities_n"],
    }
    req = _pack_payload(
        scalars_str={"step_id": step_id},
        scalars_num={
            **req_counts,
            "center_x_m": CENTER_POS[0],
            "center_z_m": CENTER_POS[2],
            "roam_radius_m": 6.0,
        },
    )
    res = _pack_payload(
        scalars_str={"step_id": step_id, "modset_sig": modset_sig, "cleanup_status": cleanup_status},
        scalars_num={
            **req_counts,
            **alive,
            "deleted_prev_roots_n": 0,
            "deleted_prev_children_n": 0,
            "skipped_foreign_containers_n": skipped_foreign_containers_n,
            "preserved_ancestors_n": preserved_ancestors_n,
            "spawn_flags_obj_n": SPAWN_FLAGS_OBJ,
            "spawn_flags_ai_n": SPAWN_FLAGS_AI,
            "director_orig_allow_damage_b": director_orig_allow_damage_b,
            "director_allow_damage_b": director_allow_damage_b,
            "apply_cost_ms": apply_cost_ms,
            "tick_ms": tick_ms,
            "frame": frame,
        },
    )
    return _bridge_record(
        verb="perf_step_apply",
        peer="server",
        status="done",
        reason="",
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _step_apply_rejected(
    step_id: str,
    *,
    op_id: str | None = None,
    reason: str = "bad_args:step_id",
    req_step_id: str = "bad_step",
) -> dict:
    req = _pack_payload(
        scalars_str={"step_id": req_step_id},
        scalars_num={
            "objects_n": 0,
            "infected_n": 0,
            "animals_n": 0,
            "actors_n": 0,
            "wardrobe_per_actor_n": 5,
            "center_x_m": CENTER_POS[0],
            "center_z_m": CENTER_POS[2],
            "roam_radius_m": 6.0,
        },
    )
    res = _unpacked_payload()
    return _bridge_record(
        verb="perf_step_apply",
        peer="server",
        status="rejected",
        reason=reason,
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _window_start_done(
    step_id: str,
    *,
    op_id: str | None = None,
    job_id: str | None = None,
    modset_sig: str = CANONICAL_MODSET_SIG,
    start_tick_ms: float = 10000.0,
    start_frame: int = 1000,
    warmup_ms: float = WARMUP_MIN_MS,
    duration_ms: float = WINDOW_MIN_MS,
    sample_step_ms: float = SAMPLE_STEP_MS,
    expected_rows_n: int = EXPECTED_WINDOW_ROWS,
    req_expected_modset_sig: str = CANONICAL_MODSET_SIG,
) -> dict:
    jid = job_id or f"job-{secrets.token_hex(8)}"
    req = _pack_payload(
        scalars_str={"step_id": step_id, "expected_modset_sig": req_expected_modset_sig},
        scalars_num={
            "warmup_ms": warmup_ms,
            "duration_ms": duration_ms,
            "sample_step_ms": sample_step_ms,
        },
    )
    res = _pack_payload(
        scalars_str={
            "job": jid,
            "state": "running",
            "resource": "perf_sampler",
            "step_id": step_id,
            "modset_sig": modset_sig,
        },
        scalars_num={
            "start_tick_ms": start_tick_ms,
            "start_frame": start_frame,
            "warmup_ms": warmup_ms,
            "duration_ms": duration_ms,
            "sample_step_ms": sample_step_ms,
            "expected_rows_n": expected_rows_n,
        },
    )
    return _bridge_record(
        verb="perf_window_start",
        peer="server",
        status="done",
        reason="",
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _window_start_rejected(
    step_id: str,
    *,
    op_id: str | None = None,
    reason: str = "modset_mismatch",
    req_expected_modset_sig: str = "wrong-sig",
) -> dict:
    req = _pack_payload(
        scalars_str={"step_id": step_id, "expected_modset_sig": req_expected_modset_sig},
        scalars_num={
            "warmup_ms": WARMUP_MIN_MS,
            "duration_ms": WINDOW_MIN_MS,
            "sample_step_ms": SAMPLE_STEP_MS,
        },
    )
    res = _unpacked_payload()
    return _bridge_record(
        verb="perf_window_start",
        peer="server",
        status="rejected",
        reason=reason,
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _job_read_done(
    job_id: str,
    *,
    op_id: str | None = None,
    state: str = "done",
    reason: str = "",
    rows_total_n: int = EXPECTED_WINDOW_ROWS,
    pages_n: int = 4,
    page_n: int = 0,
    end_tick_ms: float | None = None,
    onjobend_tick_ms: float | None = None,
    released_tick_ms: float | None = None,
    rows: list | None = None,
    bypass_wire_validation: bool = False,
) -> dict:
    req = _pack_payload(scalars_str={"job": job_id})
    if bypass_wire_validation and rows is not None:
        # Use unpacked payload directly to allow rows with missing columns (for anti-fabrication tests)
        res = _unpacked_payload(
            str_vals={"job": job_id, "state": state, "reason": reason},
            num_vals={
                "rows_total_n": rows_total_n,
                "pages_n": pages_n,
                "page_n": page_n,
                "end_tick_ms": end_tick_ms or 71000.0,
                "onjobend_tick_ms": onjobend_tick_ms or 71100.0,
                "released_tick_ms": released_tick_ms or 71200.0,
            },
            rows=rows,
            ncol=list(WINDOW_NCOL),
            scol=[],
        )
    else:
        res = _pack_payload(
            scalars_str={"job": job_id, "state": state, "reason": reason},
            scalars_num={
                "rows_total_n": rows_total_n,
                "pages_n": pages_n,
                "page_n": page_n,
                "end_tick_ms": end_tick_ms or 71000.0,
                "onjobend_tick_ms": onjobend_tick_ms or 71100.0,
                "released_tick_ms": released_tick_ms or 71200.0,
            },
            num_cols=list(WINDOW_NCOL),
            row_dicts=rows or [],
        )
    return _bridge_record(
        verb="job_read",
        peer="server",
        status="done",
        reason="",
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _job_free_done(job_id: str, *, op_id: str | None = None) -> dict:
    req = _pack_payload(scalars_str={"job": job_id})
    res = _unpacked_payload()
    return _bridge_record(
        verb="job_free",
        peer="server",
        status="done",
        reason="",
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _snap_done(
    step_id: str,
    *,
    op_id: str | None = None,
    page_n: int = 0,
    pages_n: int = 1,
    inject_foreign_cargo_b: int = 0,
    counts: dict | None = None,
    census_dynamic_n: int | None = None,
    census_foreign_n: int = 0,
    director_orig_allow_damage_b: int = 1,
    director_allow_damage_b: int = 0,
    foreign_injected_b: int = 0,
    tick_ms: float = 50000.0,
    frame: int = 5000,
    avg_fps_now: float = 51.0,
    rows: list | None = None,
    modset_sig: str = CANONICAL_MODSET_SIG,
    peer: str = "server",
) -> dict:
    spec = STEP_SPEC.get(step_id, STEP_SPEC["fixture"])
    cnt = counts or {
        "objects_alive_n": spec["objects_n"],
        "infected_alive_n": spec["infected_n"],
        "animals_alive_n": spec["animals_n"],
        "actors_alive_n": spec["actors_n"],
        "roots_alive_n": spec["roots_n"],
        "children_alive_n": spec["children_n"],
        "entities_alive_n": spec["entities_n"],
    }
    census_dyn = census_dynamic_n if census_dynamic_n is not None else spec["roots_n"]
    req = _pack_payload(
        scalars_str={"step_id": step_id},
        scalars_num={"page_n": page_n, "inject_foreign_cargo_b": inject_foreign_cargo_b},
    )
    res = _pack_payload(
        scalars_str={"step_id": step_id, "modset_sig": modset_sig},
        scalars_num={
            **cnt,
            "census_dynamic_n": census_dyn,
            "census_foreign_n": census_foreign_n,
            "director_orig_allow_damage_b": director_orig_allow_damage_b,
            "director_allow_damage_b": director_allow_damage_b,
            "foreign_injected_b": foreign_injected_b,
            "tick_ms": tick_ms,
            "frame": frame,
            "avg_fps_now": avg_fps_now,
        },
        num_cols=list(SNAP_NCOL),
        row_dicts=rows or [],
    )
    return _bridge_record(
        verb="perf_snap",
        peer=peer,
        status="done",
        reason="",
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _snap_rejected(
    step_id: str,
    *,
    op_id: str | None = None,
    reason: str = "wrong_role:client",
    peer: str = "client",
    req_page_n: int = 0,
) -> dict:
    req = _pack_payload(
        scalars_str={"step_id": step_id},
        scalars_num={"page_n": req_page_n, "inject_foreign_cargo_b": 0},
    )
    res = _unpacked_payload()
    return _bridge_record(
        verb="perf_snap",
        peer=peer,
        status="rejected",
        reason=reason,
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _budget_check_done(
    *,
    op_id: str | None = None,
    expected_modset_sig: str = CANONICAL_MODSET_SIG,
    max_vals: dict | None = None,
    cand_vals: dict | None = None,
    accepted: bool = True,
    violation_path: str = "",
    headroom_roots_n: int = 0,
    headroom_entities_n: int = 0,
    spawned_orders_n: int = 0,
) -> dict:
    req = _pack_payload(
        scalars_str={"expected_modset_sig": expected_modset_sig},
        scalars_num={
            "max_objects_n": max_vals.get("max_objects_n", 40) if max_vals else 40,
            "max_infected_n": max_vals.get("max_infected_n", 20) if max_vals else 20,
            "max_animals_n": max_vals.get("max_animals_n", 6) if max_vals else 6,
            "max_actors_n": max_vals.get("max_actors_n", 4) if max_vals else 4,
            "max_wardrobe_per_actor_n": max_vals.get("max_wardrobe_per_actor_n", 5) if max_vals else 5,
            "max_children_n": max_vals.get("max_children_n", 20) if max_vals else 20,
            "max_combined_roots_n": max_vals.get("max_combined_roots_n", 70) if max_vals else 70,
            "max_combined_entities_n": max_vals.get("max_combined_entities_n", 90) if max_vals else 90,
            "cand_objects_n": cand_vals.get("cand_objects_n", 40) if cand_vals else 40,
            "cand_infected_n": cand_vals.get("cand_infected_n", 20) if cand_vals else 20,
            "cand_animals_n": cand_vals.get("cand_animals_n", 6) if cand_vals else 6,
            "cand_actors_n": cand_vals.get("cand_actors_n", 4) if cand_vals else 4,
            "cand_wardrobe_total_n": cand_vals.get("cand_wardrobe_total_n", 20) if cand_vals else 20,
            "cand_wardrobe_max_per_actor_n": cand_vals.get("cand_wardrobe_max_per_actor_n", 5) if cand_vals else 5,
            "cand_extra_children_n": cand_vals.get("cand_extra_children_n", 0) if cand_vals else 0,
        },
    )
    if accepted:
        res = _pack_payload(
            scalars_str={"budget_status": "accepted", "violation_path": ""},
            scalars_num={
                "cand_roots_n": sum(cand_vals.get(k, 0) for k in ("cand_objects_n", "cand_infected_n", "cand_animals_n", "cand_actors_n")) if cand_vals else 70,
                "cand_children_n": (cand_vals.get("cand_wardrobe_total_n", 0) + cand_vals.get("cand_extra_children_n", 0)) if cand_vals else 20,
                "cand_entities_n": sum(cand_vals.get(k, 0) for k in ("cand_objects_n", "cand_infected_n", "cand_animals_n", "cand_actors_n", "cand_wardrobe_total_n", "cand_extra_children_n")) if cand_vals else 90,
                "headroom_roots_n": headroom_roots_n,
                "headroom_entities_n": headroom_entities_n,
                "spawned_orders_n": spawned_orders_n,
            },
        )
        status, reason = "done", ""
    else:
        res = _unpacked_payload()
        status, reason = "rejected", violation_path
    return _bridge_record(
        verb="perf_budget_check",
        peer="server",
        status=status,
        reason=reason,
        op_id=op_id,
        req_payload=req,
        res_payload=res,
    )


def _build_window_rows(
    step_id: str,
    *,
    n_rows: int = EXPECTED_WINDOW_ROWS,
    start_tick_ms: float = 40000.0,
    start_frame: int = 4000,
    fps_mean: float = 51.0,
    fps_counter: float = 51.0,
    roam_min_step: float = ROAM_MIN_STEP_M,
    creatures_min_step: float = CREATURES_MIN_STEP_M,
    emote_active: int | None = None,
    emote_cb1101: int | None = None,
    creatures_moved: int | None = None,
    with_dtsum: bool = True,
    with_harness_drift: bool = False,
) -> list:
    spec = STEP_SPEC.get(step_id, STEP_SPEC["fixture"])
    # Default emote_active and emote_cb1101 to number of emote actors (actors_n // 2)
    if emote_active is None:
        emote_active = spec["actors_n"] // 2
    if emote_cb1101 is None:
        emote_cb1101 = spec["actors_n"] // 2
    # Default creatures_moved to total creatures (infected + animals)
    if creatures_moved is None:
        creatures_moved = spec["infected_n"] + spec["animals_n"]
    rows = []
    tick = start_tick_ms
    frame = float(start_frame)
    dtsum = 0.0
    frame_increment = fps_counter * SAMPLE_STEP_MS / 1000.0
    for i in range(n_rows):
        dt = SAMPLE_STEP_MS
        tick += dt
        frame += frame_increment
        if with_dtsum:
            dtsum += dt
        row = {
            "seq_n": i,
            "frame": int(round(frame)),
            "tick_ms": round(tick, 1),
            "dtsum_ms": round(dtsum, 1) if with_dtsum else round(tick - start_tick_ms, 1),
            "avg_fps": round(fps_mean + (i % 5 - 2) * 0.5, 2),
            "alive_roots_n": spec["roots_n"],
            "alive_wardrobe_n": spec["children_n"],
            "roam_disp_step_m": round(roam_min_step + 0.02, 3),
            "roam_min_step_m": round(roam_min_step, 3) if i >= 1 else 0.0,
            "emote_active_actors_n": emote_active if spec["actors_n"] >= 2 else 0,
            "emote_cb_cmd1101_actors_n": emote_cb1101 if spec["actors_n"] >= 2 else 0,
            "creatures_moved_step_n": creatures_moved if (spec["infected_n"] + spec["animals_n"]) > 0 else 0,
            "creatures_min_step_m": round(creatures_min_step, 3) if i >= 1 else 0.0,
        }
        rows.append(row)
    return rows


def _build_snap_rows(
    step_id: str,
    *,
    foreign_content_b: int = 0,
    actor_foreign_idx: int | None = None,
    cp_index: int = 0,
    total_cps: int = EXPECTED_SNAP_CHECKPOINTS,
) -> list:
    spec = STEP_SPEC.get(step_id, STEP_SPEC["fixture"])
    rows = []
    e_idx = 0
    # Objects
    for i in range(spec["objects_n"]):
        x, _, z = s_perf_eval.spawn_pos_object(i)
        rows.append({
            "entity_idx_n": e_idx,
            "kind_code_n": 1,
            "role_code_n": 0,
            "alive_b": 1,
            "wardrobe_n": 0,
            "ai_agent_b": 0,
            "pos_x_m": float(x),
            "pos_y_m": 300.0,
            "pos_z_m": float(z),
            "cum_disp_m": 0.0,
            "wp_legs_n": 0,
            "emote_playing_b": 0,
            "emote_pending_b": 0,
            "emote_cb_id_n": 0,
            "emote_cb_state_n": 0,
            "emote_active_ticks_n": 0,
            "emote_completions_n": 0,
            "foreign_content_b": 1 if (foreign_content_b and e_idx == 0) else 0,
        })
        e_idx += 1
    # Infected
    for i in range(spec["infected_n"]):
        x, _, z = s_perf_eval.spawn_pos_infected(i)
        # Sway ±1.5m over 60s, 13 checkpoints (5s intervals)
        sway_amplitude = CREATURE_SWAY_RADIUS_M
        phase = (cp_index / total_cps) * 2 * math.pi
        sway_x = sway_amplitude * math.sin(phase)
        rows.append({
            "entity_idx_n": e_idx,
            "kind_code_n": 2,
            "role_code_n": 3,
            "alive_b": 1,
            "wardrobe_n": 0,
            "ai_agent_b": 1,
            "pos_x_m": float(x + sway_x),
            "pos_y_m": 300.0,
            "pos_z_m": float(z),
            "cum_disp_m": abs(sway_x) * 2 * cp_index,  # cumulative
            "wp_legs_n": 0,
            "emote_playing_b": 0,
            "emote_pending_b": 0,
            "emote_cb_id_n": 0,
            "emote_cb_state_n": 0,
            "emote_active_ticks_n": 0,
            "emote_completions_n": 0,
            "foreign_content_b": 0,
        })
        e_idx += 1
    # Animals
    for i in range(spec["animals_n"]):
        x, _, z = s_perf_eval.spawn_pos_animal(i)
        sway_amplitude = CREATURE_SWAY_RADIUS_M
        phase = (cp_index / total_cps) * 2 * math.pi
        sway_x = sway_amplitude * math.sin(phase)
        rows.append({
            "entity_idx_n": e_idx,
            "kind_code_n": 3,
            "role_code_n": 3,
            "alive_b": 1,
            "wardrobe_n": 0,
            "ai_agent_b": 1,
            "pos_x_m": float(x + sway_x),
            "pos_y_m": 300.0,
            "pos_z_m": float(z),
            "cum_disp_m": abs(sway_x) * 2 * cp_index,
            "wp_legs_n": 0,
            "emote_playing_b": 0,
            "emote_pending_b": 0,
            "emote_cb_id_n": 0,
            "emote_cb_state_n": 0,
            "emote_active_ticks_n": 0,
            "emote_completions_n": 0,
            "foreign_content_b": 0,
        })
        e_idx += 1
    # Actors
    for a in range(spec["actors_n"]):
        ax, _, az = s_perf_eval.spawn_pos_actor(a)
        role = 1 if (a % 2 == 0) else 2
        is_foreign_actor = (foreign_content_b and actor_foreign_idx is not None and e_idx == actor_foreign_idx)
        if role == 1:
            # Roam actor: patrol square of radius 6m over 60s (48m perimeter)
            # 13 checkpoints (0-12) at 5s intervals
            # Each side = 12m, 4 sides = 48m total. Speed = 48m/60s = 0.8 m/s
            # Per 5s checkpoint: 4m displacement
            # Complete 1 leg (12m) every 3 checkpoints
            perimeter = 48.0
            speed = perimeter / 60.0  # 0.8 m/s
            dist_per_cp = speed * 5.0  # 4.0 m per checkpoint
            total_dist = cp_index * dist_per_cp
            # wp_legs: increments every 3 checkpoints (12m per leg)
            wp_legs = cp_index // 3
            # Position along square path
            side_len = 12.0
            path_pos = (cp_index * dist_per_cp) % perimeter
            side = int(path_pos / side_len)
            side_progress = (path_pos % side_len) / side_len
            radius = ROAM_SQUARE_RADIUS_M
            # Square centered at (ax, az) with radius 6m
            # Start at right side center: (ax + radius, az)
            if side == 0:
                # Right side: moving +Z (up)
                pos_x = ax + radius
                pos_z = az - radius + side_progress * 2 * radius
            elif side == 1:
                # Top side: moving -X (left)
                pos_x = ax + radius - side_progress * 2 * radius
                pos_z = az + radius
            elif side == 2:
                # Left side: moving -Z (down)
                pos_x = ax - radius
                pos_z = az + radius - side_progress * 2 * radius
            else:
                # Bottom side: moving +X (right)
                pos_x = ax - radius + side_progress * 2 * radius
                pos_z = az - radius
        else:
            # Emote actor: stationary
            pos_x = ax
            pos_z = az
            wp_legs = 0
            total_dist = 0.0
        rows.append({
            "entity_idx_n": e_idx,
            "kind_code_n": 4,
            "role_code_n": role,
            "alive_b": 1,
            "wardrobe_n": spec["wardrobe_per_actor_n"],
            "ai_agent_b": 1 if role == 1 else 0,
            "pos_x_m": float(pos_x),
            "pos_y_m": 300.0,
            "pos_z_m": float(pos_z),
            "cum_disp_m": total_dist,
            "wp_legs_n": wp_legs,
            "emote_playing_b": 1 if role == 2 else 0,
            "emote_pending_b": 0,
            "emote_cb_id_n": EMOTE_CB_CMD_CLAP if role == 2 else 0,
            "emote_cb_state_n": 1 if role == 2 else 0,
            "emote_active_ticks_n": cp_index * 30 if role == 2 else 0,
            "emote_completions_n": cp_index // 3 if role == 2 else 0,
            "foreign_content_b": 1 if is_foreign_actor else 0,
        })
        e_idx += 1
    return rows


def _chk(verdict: dict, cid: str) -> str:
    """Status of one check in the core verdict format (list of {id, status, detail})."""
    return next(c["status"] for c in verdict["checks"] if c["id"] == cid)


def _chk_detail(verdict: dict, cid: str) -> str:
    return next(c["detail"] for c in verdict["checks"] if c["id"] == cid)


def _records_to_events(records: list[dict]) -> list[dict]:
    """Expand the test's one-record-per-op builders into the REAL core event log
    (enq -> deliver -> result), the only format the evaluator accepts."""
    events: list[dict] = []
    for rec in records:
        if "ev" in rec:
            events.append(rec)
            continue
        read_env = dict(rec["read"])
        status = read_env.pop("status")
        reason = read_env.pop("reason", "")
        peer = rec["peer"]
        events.append({
            "ev": "enq", "t_ms": rec["issued_ms"], "op_id": rec["op_id"], "peer": peer,
            "verb": rec["verb"], "inst": rec.get("target_inst", peer), "args": rec.get("args") or {},
        })
        events.append({
            "ev": "deliver", "t_ms": rec["ack_ms"], "op_id": rec["op_id"], "peer": peer,
            "verb": rec["verb"], "inst": rec.get("target_inst", peer), "args": rec.get("args") or {},
        })
        events.append({
            "ev": "result", "t_ms": rec["read_ms"], "http": 200, "op_id": rec["op_id"], "peer": peer,
            "result": {"op_id": rec["op_id"], "status": status, "reason": reason, "read": read_env,
                       "recv_ms": rec["ack_ms"], "done_ms": rec["read_ms"], "dup": False},
        })
    return events


def _write_part(
    part_dir: Path,
    bridge_records: list[dict],
    *,
    extra_samples: dict[str, Any] | None = None,
    manifest: dict | None = None,
) -> None:
    samples = part_dir / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    _write_jsonl(samples / "bridge.jsonl", _records_to_events(bridge_records))
    if extra_samples:
        for name, data in extra_samples.items():
            if name.endswith(".jsonl"):
                _write_jsonl(samples / name, data)
            else:
                (samples / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if manifest:
        gate_core.write_json(part_dir / "manifest.json", manifest)
    else:
        gate_core.write_json(part_dir / "manifest.json", {
            "argv": [], "both": True, "build": "offline", "ended_utc": "2026-01-01T00:00:00Z",
            "faults": [], "harness": {"git_dirty": False, "git_head": "test", "platform": "test", "python": "3.14"},
            "id": "S-perf", "kind": "spike", "params": {"hold_ms": 2000, "lease_ms": 3000, "port": 9, "retry_ms": 2000, "seed": 20261026, "ttl_ms": 5000},
            "schema": gate_core.SCHEMA_MANIFEST, "started_utc": "2026-01-01T00:00:00Z",
        })


DEFAULT_FPS = {"base": 58.0, "fixture": 51.0, "inc1": 44.0, "inc2": 38.5}
ZERO_COUNTS = {c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}
ZERO_ALIVE = {
    "objects_alive_n": 0, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 0,
    "roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0,
}


def _window_marks(rows: list) -> dict:
    last = rows[-1]["tick_ms"] if rows else 0.0
    return {"end_tick_ms": last + 100.0, "onjobend_tick_ms": last + 200.0, "released_tick_ms": last + 300.0}


def _step_segment(
    step: str,
    *,
    fps: float | None = None,
    rows: list | None = None,
    snap_rows=None,
    n_snaps: int = EXPECTED_SNAP_CHECKPOINTS,
    free: bool = True,
    job_id: str | None = None,
    ws_kwargs: dict | None = None,
    apply_rec: dict | None = None,
    read_kwargs: dict | None = None,
    census_dynamic_n: int | None = None,
) -> list[dict]:
    """apply -> window start -> n snapshots over the window -> terminal job_read -> job_free
    (the order of the brief §4.2 run sequence)."""
    fps = DEFAULT_FPS[step] if fps is None else fps
    jid = job_id or f"job-{step}"
    rows = _build_window_rows(step, fps_mean=fps, fps_counter=fps) if rows is None else rows
    t0 = rows[0]["tick_ms"] if rows else 41000.0
    seg = [apply_rec or _step_apply_done(step), _window_start_done(step, job_id=jid, **(ws_kwargs or {}))]
    for cp in range(n_snaps):
        sr = snap_rows(cp) if snap_rows else _build_snap_rows(step, cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)
        seg.append(_snap_done(step, tick_ms=t0 + cp * 5000.0, rows=sr, census_dynamic_n=census_dynamic_n))
    kw = {"rows": rows, "rows_total_n": len(rows), **_window_marks(rows)}
    kw.update(read_kwargs or {})
    seg.append(_job_read_done(jid, **kw))
    if free:
        seg.append(_job_free_done(jid))
    return seg


def _cap_vals(step: str) -> tuple[dict, dict]:
    spec = STEP_SPEC[step]
    mx = {
        "max_objects_n": spec["objects_n"], "max_infected_n": spec["infected_n"],
        "max_animals_n": spec["animals_n"], "max_actors_n": spec["actors_n"],
        "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"], "max_children_n": spec["children_n"],
        "max_combined_roots_n": spec["roots_n"], "max_combined_entities_n": spec["entities_n"],
    }
    cand = {
        "cand_objects_n": spec["objects_n"], "cand_infected_n": spec["infected_n"],
        "cand_animals_n": spec["animals_n"], "cand_actors_n": spec["actors_n"],
        "cand_wardrobe_total_n": spec["children_n"],
        "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"], "cand_extra_children_n": 0,
    }
    return mx, cand


def _budget_at_cap(step: str = "inc2") -> dict:
    mx, cand = _cap_vals(step)
    return _budget_check_done(accepted=True, max_vals=mx, cand_vals=cand)


def _n5_stimuli(step: str = "inc2") -> list[tuple[str, dict, dict]]:
    """The 8 isolated N5 calls of brief section 6 against the cap of `step`."""
    mx0, cap = _cap_vals(step)
    zero = {k: 0 for k in cap}
    out = []

    def add(reason, max_over=None, **cand_over):
        mx = dict(mx0)
        mx.update(max_over or {})
        cand = dict(zero)
        cand.update(cand_over)
        out.append((reason, mx, cand))

    add("budget_exceeded:objects", cand_objects_n=mx0["max_objects_n"] + 1)
    add("budget_exceeded:infected", cand_infected_n=mx0["max_infected_n"] + 1)
    add("budget_exceeded:animals", cand_animals_n=mx0["max_animals_n"] + 1)
    add("budget_exceeded:actors", cand_actors_n=mx0["max_actors_n"] + 1)
    add("budget_exceeded:wardrobe_per_actor", cand_actors_n=1, cand_wardrobe_total_n=6,
        cand_wardrobe_max_per_actor_n=6)
    add("budget_exceeded:children_total", cand_extra_children_n=mx0["max_children_n"] + 1)
    add("budget_exceeded:combined_roots", max_over={"max_combined_roots_n": mx0["max_combined_roots_n"] - 1}, **cap)
    add("budget_exceeded:combined_entities",
        max_over={"max_combined_entities_n": mx0["max_combined_entities_n"] - 1}, **cap)
    return out


def _n5_records(step: str = "inc2", *, accept_reason: str | None = None) -> list[dict]:
    recs = []
    for reason, mx, cand in _n5_stimuli(step):
        if reason == accept_reason:
            recs.append(_budget_check_done(accepted=True, max_vals=mx, cand_vals=cand))
        else:
            recs.append(_budget_check_done(accepted=False, violation_path=reason, max_vals=mx, cand_vals=cand))
    return recs


def _negatives_segment(step: str = "inc2", *, post_census_dynamic_n: int | None = None,
                       accept_reason: str | None = None, tick0: float = 110000.0) -> list[dict]:
    """Brief section 6: N5 x8, N2, N1a, N1b, N4, the post-N5 snapshot (closing N1-N5 BEFORE N6),
    then N6 + partial cleanup + bench closure."""
    spec = STEP_SPEC[step]
    seg = _n5_records(step, accept_reason=accept_reason)
    seg.append(_snap_rejected(step, peer="client"))
    seg.append(_window_start_done(step, job_id="job-n1a", expected_rows_n=1, warmup_ms=0, duration_ms=1000))
    seg.append(_job_read_done("job-n1a", rows_total_n=1, pages_n=1, rows=_build_window_rows(step, n_rows=1)))
    seg.append(_job_free_done("job-n1a"))
    seg.append(_window_start_rejected(step, req_expected_modset_sig="wrong"))
    seg.append(_preflight_rejected(reason="area_not_clear"))
    seg.append(_snap_done(step, tick_ms=tick0, census_dynamic_n=post_census_dynamic_n,
                          rows=_build_snap_rows(step, cp_index=13, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
    actor_idx = spec["objects_n"] + spec["infected_n"] + spec["animals_n"]
    seg.append(_snap_done(step, inject_foreign_cargo_b=1, foreign_injected_b=1, census_foreign_n=2,
                          tick_ms=tick0 + 2000.0, rows=_build_snap_rows(step, foreign_content_b=1, actor_foreign_idx=actor_idx)))
    seg.append(_step_apply_done(
        "cleanup", cleanup_status="partial_foreign_content", requested_counts=dict(ZERO_COUNTS),
        alive_counts={"objects_alive_n": 1, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 1,
                      "roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3},
        director_orig_allow_damage_b=1, director_allow_damage_b=1, skipped_foreign_containers_n=2,
        preserved_ancestors_n=1))
    surv = _build_snap_rows(step, foreign_content_b=1, actor_foreign_idx=actor_idx)
    for r in surv:
        if r["entity_idx_n"] == actor_idx:
            r["wardrobe_n"] = 1
    seg.append(_snap_done(
        step, tick_ms=tick0 + 4000.0, counts={"roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3},
        census_dynamic_n=2, census_foreign_n=2, director_allow_damage_b=1, director_orig_allow_damage_b=1,
        rows=[surv[0], surv[actor_idx]]))
    seg.append(_step_apply_done(
        "cleanup", cleanup_status="clean", requested_counts=dict(ZERO_COUNTS), alive_counts=dict(ZERO_ALIVE),
        director_orig_allow_damage_b=1, director_allow_damage_b=1))
    seg.append(_snap_done(
        step, tick_ms=tick0 + 6000.0, counts={"roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0},
        census_dynamic_n=0, census_foreign_n=0, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=[]))
    return seg


def _full_run(*, fps: dict | None = None, steps=STEP_ORDER, negatives: bool = True,
              budget_step: str | None = "inc2", segs: dict | None = None) -> list[dict]:
    """A complete honest run (brief section 4.2): preflight, 4 steps, budget at the certified cap,
    negative battery with its closure."""
    fps = dict(DEFAULT_FPS, **(fps or {}))
    bridge = [_preflight_done()]
    for s in steps:
        bridge.extend((segs or {}).get(s) or _step_segment(s, fps=fps[s]))
    if budget_step:
        bridge.append(_budget_at_cap(budget_step))
    if negatives:
        bridge.extend(_negatives_segment(budget_step or "inc2"))
    return bridge


def _eval_records(records: list[dict], td: str | Path, name: str = "part") -> dict:
    part = Path(td) / name
    _write_part(part, records)
    return s_perf_eval.evaluate(part)


def _statuses(verdict: dict) -> dict:
    return {c["id"]: c["status"] for c in verdict["checks"]}


class TestSPerfOffline(unittest.TestCase):
    """Offline tests for S-perf evaluator."""

    def setUp(self):
        self.maxDiff = None

    # ==========================================================================
    # PRF-01: server_preflight_and_modset_lock
    # ==========================================================================

    def test_prf01_healthy_preflight_passes(self):
        """Healthy preflight on server with canonical modset passes PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done()]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "pass")

    def test_prf01_client_perf_done_fails(self):
        """Any perf_* verb completing as 'done' on client fails PRF-01 (E5)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _snap_done("fixture", peer="client"),  # violation
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")
            self.assertTrue(any("client role" in r for r in verdict["reasons"]))

    def test_prf01_modset_sig_mismatch_fails(self):
        """modset_sig in preflight result != canonical fixture fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(modset_sig="world=x;addons=y;patches_n=1")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_world_mismatch_fails(self):
        """world_name != chernarusplus fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(world_name="livonia")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_addons_csv_mismatch_fails(self):
        """loaded_addons_csv != canonical fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(loaded_addons_csv="DayZExpansion_HeavyQA,DayZSandbox_QA")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_director_not_locked_fails(self):
        """director_allow_damage_b != 0 fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(director_allow_damage_b=1)]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_weather_not_fixed_fails(self):
        """Weather not frozen at 0.0 fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(overcast=0.5)]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_area_not_clean_fails(self):
        """Preflight with dynamic/foreign entities in radius fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(census_dynamic_n=1, census_foreign_n=1)]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_all_perf_done_carry_canonical_modset_sig(self):
        """Every server perf_* 'done' must carry modset_sig == canonical."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture", modset_sig="wrong-sig"),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_preflight_rejected_modset_mismatch_is_violation(self):
        """Preflight rejected with modset_mismatch (negative probe) counts as PRF-01 violation."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_rejected(reason="modset_mismatch")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_duplicate_op_id_fails(self):
        """Duplicate op_id in bridge.jsonl fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            oid = "aaaaaaaa-1"
            bridge = [
                _preflight_done(op_id=oid),
                _step_apply_done("fixture", op_id=oid),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_prf01_non_monotonic_timestamps_fails(self):
        """Non-monotonic issued/ack/read timestamps fail PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(op_id="a", issued_ms=100.0, ack_ms=50.0),  # ack < issued
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    # ==========================================================================
    # PRF-03: warmup_and_window_completeness
    # ==========================================================================

    def test_prf03_healthy_window_passes(self):
        """Complete 61-row window with correct warmup/span/deltas passes PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0),
                _job_free_done("job-1"),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "pass")

    def test_prf03_insufficient_rows_fails(self):
        """< 61 rows fails PRF-03 with insufficient_samples."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", expected_rows_n=61)
            rows = _build_window_rows("fixture", n_rows=10)
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows_total_n=10, rows=rows),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")
            self.assertTrue(any("insufficient_samples" in r for r in verdict["reasons"]))

    def test_prf03_warmup_too_short_fails(self):
        """Effective warmup < 30000 ms fails PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", start_tick_ms=40000.0, warmup_ms=30000.0)
            rows = _build_window_rows("fixture", start_tick_ms=45000.0)  # only 5000 ms warmup
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")
            self.assertTrue(any("effective warmup" in r for r in verdict["reasons"]))

    def test_prf03_span_too_short_fails(self):
        """Window span < 60000 ms fails PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", start_tick_ms=40000.0, warmup_ms=30000.0)
            # Build 61 rows with 800ms intervals -> span = 48000ms < 60000ms
            rows = []
            tick = 70000.0
            frame = 4000.0
            dtsum = 0.0
            frame_increment = 51.0 * 0.8  # fps_counter * dt/1000
            for i in range(EXPECTED_WINDOW_ROWS):
                dt = 800.0
                tick += dt
                frame += frame_increment
                dtsum += dt
                spec = STEP_SPEC["fixture"]
                rows.append({
                    "seq_n": i,
                    "frame": int(round(frame)),
                    "tick_ms": round(tick, 1),
                    "dtsum_ms": round(dtsum, 1),
                    "avg_fps": 51.0,
                    "alive_roots_n": spec["roots_n"],
                    "alive_wardrobe_n": spec["children_n"],
                    "roam_disp_step_m": 0.07,
                    "roam_min_step_m": 0.07 if i >= 1 else 0.0,
                    "emote_active_actors_n": 1,
                    "emote_cb_cmd1101_actors_n": 1,
                    "creatures_moved_step_n": 13,
                    "creatures_min_step_m": 0.02 if i >= 1 else 0.0,
                })
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")
            self.assertTrue(any("window span" in r for r in verdict["reasons"]))

    def test_prf03_non_increasing_frame_fails(self):
        """Non-increasing frame counter fails PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            rows[10]["frame"] = rows[9]["frame"]  # duplicate frame
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")

    def test_prf03_non_increasing_dtsum_fails(self):
        """Non-increasing dtsum_ms fails PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            rows[10]["dtsum_ms"] = rows[9]["dtsum_ms"]  # duplicate dtsum
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")

    def test_prf03_delta_t_out_of_bounds_fails(self):
        """Sample interval outside [500, 1500] ms fails PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", sample_step_ms=2000.0)
            rows = _build_window_rows("fixture")
            rows[1]["tick_ms"] = rows[0]["tick_ms"] + 2000.0  # 2s gap
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")

    def test_prf03_missing_columns_fails(self):
        """Missing required WINDOW_NCOL columns fails PRF-03 (anti-fabrication)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            del rows[0]["avg_fps"]  # missing column
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0, bypass_wire_validation=True),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")

    def test_prf03_job_lifecycle_order_fails(self):
        """Invalid job lifecycle marks (end > onjobend > released) fails PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101200.0, onjobend_tick_ms=101100.0, released_tick_ms=101000.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "fail")

    def test_prf03_non_done_terminal_is_technical_inconcluso(self):
        """Job ending in stopped/failed/expired -> INCONCLUSO (technical)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", state="failed", reason="crash", rows_total_n=0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-03"), "missing")  # technical -> missing
            self.assertEqual(verdict["exit_code"], INCONCLUSO)

    # ==========================================================================
    # PRF-04: dual_source_fps_agreement
    # ==========================================================================

    def test_prf04_healthy_agreement_passes(self):
        """FPS sources within ±10% and clock drifts within tolerance pass PRF-04."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", start_tick_ms=40000.0)
            rows = _build_window_rows("fixture", fps_mean=51.0, fps_counter=51.0, start_tick_ms=70000.0)
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-04"), "pass")

    def test_prf04_fps_disagreement_fails(self):
        """FPS sources > 10% apart fails PRF-04."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", fps_mean=51.0, fps_counter=38.0)  # > 25% diff
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-04"), "fail")
            self.assertTrue(any("FPS disagreement" in r for r in verdict["reasons"]))

    def test_prf04_dtsum_drift_fails(self):
        """dtsum drift > 2% fails PRF-04."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", start_tick_ms=40000.0)
            rows = _build_window_rows("fixture", start_tick_ms=70000.0)
            # Corrupt dtsum to create >2% drift
            for r in rows:
                r["dtsum_ms"] = r["tick_ms"] * 1.05  # 5% drift
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-04"), "fail")
            self.assertTrue(any("dtsum drift" in r for r in verdict["reasons"]))

    def test_prf04_harness_drift_fails(self):
        """Harness clock drift > 5% fails PRF-04."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", start_tick_ms=40000.0)
            rows = _build_window_rows("fixture", start_tick_ms=70000.0)
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            # Add polls.jsonl with large harness span
            extra = {
                "step_fixture_polls.jsonl": [
                    {"h_ms": 1000.0}, {"h_ms": 2000.0}, {"h_ms": 3000.0},
                    # Harness span ~72s vs tick span ~60s -> ~20% drift
                ]
            }
            _write_part(part, bridge, extra_samples=extra)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-04"), "fail")
            self.assertTrue(any("harness clock drift" in r for r in verdict["reasons"]))

    def test_prf04_less_than_two_rows_missing(self):
        """< 2 rows or zero span -> missing (no division), not fail (N13)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", n_rows=1)
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows_total_n=1, rows=rows),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-04"), "missing")

    # ==========================================================================
    # PRF-02: step_loads_and_continuous_activity
    # ==========================================================================

    def test_prf02_healthy_step_passes(self):
        """Complete step with correct counts, activity, and 13 checkpoints passes PRF-02."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                _job_free_done("job-1"),
            ]
            # 13 checkpoints (each is a separate checkpoint operation, not paginated)
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                snap_rows = _build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=snap_rows))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "pass")

    def test_prf02_counts_mismatch_fails(self):
        """Observed counts != requested counts fails PRF-02."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture", alive_counts={"objects_alive_n": 19}),  # mismatch
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_invalid_spawn_flags_fails(self):
        """Wrong spawn flags fails PRF-02 (#11)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            # Use a custom step_apply with wrong flags
            bridge = [
                _preflight_done(),
                _bridge_record(
                    verb="perf_step_apply",
                    status="done",
                    req_payload=_pack_payload(
                        scalars_str={"step_id": "fixture"},
                        scalars_num={"objects_n": 20, "infected_n": 10, "animals_n": 3, "actors_n": 2, "wardrobe_per_actor_n": 5, "center_x_m": 7500.0, "center_z_m": 7500.0, "roam_radius_m": 6.0},
                    ),
                    res_payload=_pack_payload(
                        scalars_str={"step_id": "fixture", "modset_sig": CANONICAL_MODSET_SIG, "cleanup_status": "clean"},
                        scalars_num={
                            "objects_n": 20, "infected_n": 10, "animals_n": 3, "actors_n": 2, "wardrobe_per_actor_n": 5,
                            "objects_alive_n": 20, "infected_alive_n": 10, "animals_alive_n": 3, "actors_alive_n": 2,
                            "roots_alive_n": 35, "children_alive_n": 10, "entities_alive_n": 45,
                            "spawn_flags_obj_n": 999999,  # wrong
                            "spawn_flags_ai_n": SPAWN_FLAGS_AI,
                            "director_orig_allow_damage_b": 1, "director_allow_damage_b": 0,
                            "apply_cost_ms": 5.0, "tick_ms": 2000.0, "frame": 200,
                        },
                    ),
                ),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_roam_min_step_below_threshold_fails(self):
        """roam_min_step_m < ROAM_MIN_STEP_M fails PRF-02 (Arbitraje N3)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", roam_min_step=0.01)  # below 0.05
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_emote_callback_inactive_fails(self):
        """emote actor without callback 1101 active fails PRF-02."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", emote_cb1101=0)  # no callback 1101
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_creature_min_step_below_threshold_fails(self):
        """creatures_min_step_m < CREATURES_MIN_STEP_M fails PRF-02."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", creatures_min_step=0.001)  # below 0.01
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_insufficient_checkpoints_fails(self):
        """< 13 perf_snap checkpoints fails PRF-02."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(5):  # only 5 checkpoints
                bridge.append(_snap_done("fixture", page_n=cp, pages_n=5, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture", cp_index=cp, total_cps=5)))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_quarter_trajectory_roam_fails(self):
        """Roam actor quarter displacement < 2.0 m fails PRF-02 (Arbitraje N7)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            # Build snapshots where roam actor barely moves
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                snap_rows = _build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)
                # Modify roam actor position to be nearly stationary
                for r in snap_rows:
                    if r["kind_code_n"] == 4 and r["role_code_n"] == 1:
                        r["pos_x_m"] = 7508.0
                        r["pos_z_m"] = 7470.0
                        r["cum_disp_m"] = 0.0
                        r["wp_legs_n"] = 0
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=snap_rows))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_quarter_trajectory_emote_fails(self):
        """Emote actor < 1 completion per quarter fails PRF-02 (Arbitraje N5)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                snap_rows = _build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)
                for r in snap_rows:
                    if r["kind_code_n"] == 4 and r["role_code_n"] == 2:
                        r["emote_completions_n"] = 0  # no completions
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=snap_rows))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    def test_prf02_census_mismatch_fails(self):
        """Independent census != registered alive fails PRF-02 (N8)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                snap_rows = _build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, census_dynamic_n=999, rows=snap_rows))  # mismatch
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-02"), "fail")

    # ==========================================================================
    # PRF-05: floor_and_combined_budget_derivation
    # ==========================================================================

    def test_prf05_fixture_below_floor_fails_immediately(self):
        """fixture step with fps_window_mean <= 35.0 fails PRF-05 immediately."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", fps_mean=30.0, fps_counter=30.0)
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-05"), "fail")
            self.assertTrue(any("below floor" in r for r in verdict["reasons"]))

    def test_prf05_base_below_floor_fails_immediately(self):
        """base step with fps_window_mean <= 35.0 fails PRF-05 immediately."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("base", job_id="job-1")
            rows = _build_window_rows("base", fps_mean=30.0, fps_counter=30.0)
            bridge = [
                _preflight_done(),
                _step_apply_done("base"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("base", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("base", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-05"), "fail")

    def test_prf05_k_star_derivation_certified_budget(self):
        """k* derivation exports certified_budget metrics when all 4 steps valid (k*=3)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done()]
            # All 4 steps with healthy windows (all > 35 FPS -> k*=3)
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0, fps_counter=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0)
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                    _job_free_done(f"job-{s}"),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s, cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # Budget check at inc2 cap (k*=3) - build proper max_vals/cand_vals
            spec = STEP_SPEC["inc2"]
            max_vals = {
                "max_objects_n": spec["objects_n"],
                "max_infected_n": spec["infected_n"],
                "max_animals_n": spec["animals_n"],
                "max_actors_n": spec["actors_n"],
                "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
                "max_children_n": spec["children_n"],
                "max_combined_roots_n": spec["roots_n"],
                "max_combined_entities_n": spec["entities_n"],
            }
            cand_vals = {
                "cand_objects_n": spec["objects_n"],
                "cand_infected_n": spec["infected_n"],
                "cand_animals_n": spec["animals_n"],
                "cand_actors_n": spec["actors_n"],
                "cand_wardrobe_total_n": spec["children_n"],
                "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"],
                "cand_extra_children_n": 0,
            }
            bridge.append(_budget_check_done(accepted=True, max_vals=max_vals, cand_vals=cand_vals))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-05"), "pass")
            self.assertIn("certified_budget", verdict["metrics"])
            cb = verdict["metrics"]["certified_budget"]
            self.assertEqual(cb["certified_step_id"], "inc2")
            self.assertEqual(cb["certified_step_index"], 3)
            self.assertEqual(cb["floor_fps"], 35.0)

    def test_prf05_k_star_2_when_inc1_above_floor(self):
        """k* = 2 when fixture and inc1 > 35.0 but inc2 <= 35.0."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done()]
            fps_map = {"base": 58.0, "fixture": 51.0, "inc1": 44.0, "inc2": 30.0}
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=fps_map[s], fps_counter=fps_map[s])
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                    _job_free_done(f"job-{s}"),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s, cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # Budget check at inc1 cap (k*=2) - build proper max_vals/cand_vals
            spec = STEP_SPEC["inc1"]
            max_vals = {
                "max_objects_n": spec["objects_n"],
                "max_infected_n": spec["infected_n"],
                "max_animals_n": spec["animals_n"],
                "max_actors_n": spec["actors_n"],
                "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
                "max_children_n": spec["children_n"],
                "max_combined_roots_n": spec["roots_n"],
                "max_combined_entities_n": spec["entities_n"],
            }
            cand_vals = {
                "cand_objects_n": spec["objects_n"],
                "cand_infected_n": spec["infected_n"],
                "cand_animals_n": spec["animals_n"],
                "cand_actors_n": spec["actors_n"],
                "cand_wardrobe_total_n": spec["children_n"],
                "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"],
                "cand_extra_children_n": 0,
            }
            bridge.append(_budget_check_done(accepted=True, max_vals=max_vals, cand_vals=cand_vals))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-05"), "pass")
            cb = verdict["metrics"]["certified_budget"]
            self.assertEqual(cb["certified_step_id"], "inc1")
            self.assertEqual(cb["certified_step_index"], 2)

    def test_prf05_missing_budget_check_at_cap_fails(self):
        """Missing accepted perf_budget_check at certified cap fails PRF-05."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done()]
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0, fps_counter=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0)
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                    _job_free_done(f"job-{s}"),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s, cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # NO budget check at cap
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-05"), "fail")
            self.assertTrue(any("missing accepted perf_budget_check" in r for r in verdict["reasons"]))

    # ==========================================================================
    # PRF-06: negative_guards_and_clean_teardown
    # ==========================================================================

    def test_prf06_n5_all_8_subcases_required(self):
        """All 8 N5 subcases must be present and rejected with exact reasons."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            # Only 7 of 8 budget checks
            for reason in list(N5_REQUIRED_REASONS)[:-1]:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")

    def test_prf06_n5_wrong_reason_fails(self):
        """Budget check with excess but wrong rejection reason fails PRF-06."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:objects"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:infected"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:animals"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:actors"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:wardrobe_per_actor"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:children_total"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:combined_roots"),
                _budget_check_done(accepted=False, violation_path="budget_exceeded:wrong_reason"),  # wrong
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")

    def test_prf06_n2_client_rejection_required(self):
        """N2: client perf_snap must be rejected with wrong_role:client."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            # Missing N2
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")

    def test_prf06_n1a_single_sample_rejected_and_freed(self):
        """N1a: 1-row window must be rejected as insufficient_samples and freed."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-n1a", expected_rows_n=1, warmup_ms=0, duration_ms=1000)
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-n1a", rows_total_n=1, rows=_build_window_rows("fixture", n_rows=1)),
                # Missing job_free
            ]
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")
            self.assertTrue(any("N1a" in r and "freed" in r for r in verdict["reasons"]))

    def test_prf06_n1b_modset_mismatch_rejection(self):
        """N1b: perf_window_start with wrong modset_sig must be rejected modset_mismatch."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            # Missing N1b
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")

    def test_prf06_n4_area_not_clear_rejection(self):
        """N4: preflight with foreign entity must reject area_not_clear."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            # Missing N4
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")

    def test_prf06_n6_foreign_cargo_partial_cleanup(self):
        """N6: foreign cargo in SeaChest + garment preserves actor ancestor."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            # N6 injection
            bridge.append(_snap_done("fixture", inject_foreign_cargo_b=1, foreign_injected_b=1, census_foreign_n=2, rows=_build_snap_rows("fixture", foreign_content_b=1, actor_foreign_idx=STEP_SPEC["fixture"]["objects_n"])))
            # Cleanup partial
            bridge.append(_step_apply_done("cleanup", cleanup_status="partial_foreign_content", requested_counts={c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}, alive_counts={"objects_alive_n": 1, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 1, "roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, director_orig_allow_damage_b=1, director_allow_damage_b=1, skipped_foreign_containers_n=2, preserved_ancestors_n=1))
            # Cleanup snap
            bridge.append(_snap_done("fixture", tick_ms=80000.0, counts={"roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, census_foreign_n=2, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=_build_snap_rows("fixture")[:2]))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            # N1a, N1b, N2, N4 and the post-N5 snapshot are absent: PRF-06 cannot pass
            self.assertNotEqual(_chk(verdict, "PRF-06"), "pass")
            self.assertNotEqual(verdict["exit_code"], PASA)

    def test_prf06_n1_n5_invariance_before_n6(self):
        """Census invariance must hold between N1-N5 battery and N6 (N10)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            # Pre-N5 snapshot (checkpoint)
            bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0, rows=_build_snap_rows("fixture", cp_index=0, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            # Add N2, N1a, N1b, N4
            bridge.append(_snap_rejected("fixture", peer="client"))
            ws_n1a = _window_start_done("fixture", job_id="job-n1a", expected_rows_n=1, warmup_ms=0, duration_ms=1000)
            bridge.append(ws_n1a)
            bridge.append(_job_read_done("job-n1a", rows_total_n=1, rows=_build_window_rows("fixture", n_rows=1)))
            bridge.append(_job_free_done("job-n1a"))
            bridge.append(_window_start_rejected("fixture", req_expected_modset_sig="wrong"))
            bridge.append(_preflight_rejected(reason="area_not_clear"))
            # Post-N5, pre-N6 snapshot (for census invariance check) - DIFFERENT census to test invariance check
            bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=75000.0, census_dynamic_n=999, rows=_build_snap_rows("fixture", cp_index=13, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # N6 injection with foreign cargo
            bridge.append(_snap_done("fixture", inject_foreign_cargo_b=1, foreign_injected_b=1, census_foreign_n=2, census_dynamic_n=999, rows=_build_snap_rows("fixture", foreign_content_b=1)))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")
            self.assertTrue(any("census invariance broken" in r for r in verdict["reasons"]))

    def test_prf06_full_negative_battery_passes(self):
        """Complete negative battery (N1a, N1b, N2, N4, N5x8, N6) with invariance passes PRF-06."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            # 13 checkpoints for the step (pre-N5 snapshots for census invariance)
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # N5 - all 8 with proper fixture max_vals/cand_vals
            spec = STEP_SPEC["fixture"]
            base_max_vals = {
                "max_objects_n": spec["objects_n"],
                "max_infected_n": spec["infected_n"],
                "max_animals_n": spec["animals_n"],
                "max_actors_n": spec["actors_n"],
                "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
                "max_children_n": spec["children_n"],
                "max_combined_roots_n": spec["roots_n"],
                "max_combined_entities_n": spec["entities_n"],
            }
            for reason in N5_REQUIRED_REASONS:
                cat = reason.split(":")[1]
                max_vals = dict(base_max_vals)
                # Base candidate at fixture limits (all categories at max)
                cand_vals = {
                    "cand_objects_n": spec["objects_n"],
                    "cand_infected_n": spec["infected_n"],
                    "cand_animals_n": spec["animals_n"],
                    "cand_actors_n": spec["actors_n"],
                    "cand_wardrobe_total_n": spec["children_n"],
                    "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"],
                    "cand_extra_children_n": 0,
                }
                if cat == "objects":
                    cand_vals["cand_objects_n"] = max_vals["max_objects_n"] + 1
                elif cat == "infected":
                    cand_vals["cand_infected_n"] = max_vals["max_infected_n"] + 1
                elif cat == "animals":
                    cand_vals["cand_animals_n"] = max_vals["max_animals_n"] + 1
                elif cat == "actors":
                    cand_vals["cand_actors_n"] = max_vals["max_actors_n"] + 1
                elif cat == "wardrobe_per_actor":
                    cand_vals["cand_wardrobe_max_per_actor_n"] = max_vals["max_wardrobe_per_actor_n"] + 1
                elif cat == "children_total":
                    cand_vals["cand_extra_children_n"] = max_vals["max_children_n"] + 1
                elif cat == "combined_roots":
                    # Candidate: all categories at max (roots=35), but max_combined_roots_n=34
                    max_vals["max_combined_roots_n"] = max_vals["max_combined_roots_n"] - 1
                elif cat == "combined_entities":
                    # Candidate: all categories at max (entities=45), but max_combined_entities_n=44
                    max_vals["max_combined_entities_n"] = max_vals["max_combined_entities_n"] - 1
                bridge.append(_budget_check_done(accepted=False, violation_path=reason, max_vals=max_vals, cand_vals=cand_vals))
            # N2
            bridge.append(_snap_rejected("fixture", peer="client"))
            # N1a
            ws_n1a = _window_start_done("fixture", job_id="job-n1a", expected_rows_n=1, warmup_ms=0, duration_ms=1000)
            bridge.append(ws_n1a)
            bridge.append(_job_read_done("job-n1a", rows_total_n=1, rows=_build_window_rows("fixture", n_rows=1)))
            bridge.append(_job_free_done("job-n1a"))
            # N1b
            bridge.append(_window_start_rejected("fixture", req_expected_modset_sig="wrong"))
            # N4
            bridge.append(_preflight_rejected(reason="area_not_clear"))
            # Post-N5, pre-N6 snapshot (for census invariance check)
            bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=75000.0, rows=_build_snap_rows("fixture", cp_index=13, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # N6 injection - mark both SeaChest (idx 0) and first actor (idx 33) with foreign_content_b=1
            fixture_spec = STEP_SPEC["fixture"]
            actor_foreign_idx = fixture_spec["objects_n"] + fixture_spec["infected_n"] + fixture_spec["animals_n"]  # 20+10+3=33
            bridge.append(_snap_done("fixture", inject_foreign_cargo_b=1, foreign_injected_b=1, census_foreign_n=2, rows=_build_snap_rows("fixture", foreign_content_b=1, actor_foreign_idx=actor_foreign_idx)))
            # Cleanup partial
            bridge.append(_step_apply_done("cleanup", cleanup_status="partial_foreign_content", requested_counts={c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}, alive_counts={"objects_alive_n": 1, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 1, "roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, director_orig_allow_damage_b=1, director_allow_damage_b=1, skipped_foreign_containers_n=2, preserved_ancestors_n=1))
            # Cleanup snap - must show both SeaChest (idx 0) and actor (idx 33) as survivors
            # Actor should have only 1 garment (the one with foreign cargo), so wardrobe_n=1
            cleanup_snap_rows = _build_snap_rows("fixture", foreign_content_b=1, actor_foreign_idx=actor_foreign_idx)
            # Modify actor's wardrobe_n to 1 (only the garment with foreign cargo)
            for r in cleanup_snap_rows:
                if r["entity_idx_n"] == actor_foreign_idx:
                    r["wardrobe_n"] = 1
                    break
            # Filter to only the two survivors: SeaChest (idx 0) and actor (idx 33)
            survivor_rows = [cleanup_snap_rows[0], cleanup_snap_rows[actor_foreign_idx]]
            bridge.append(_snap_done("fixture", tick_ms=80000.0, counts={"roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, census_foreign_n=2, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=survivor_rows))
            # Bench closure
            bridge.append(_step_apply_done("cleanup", cleanup_status="clean", requested_counts={c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}, alive_counts={"objects_alive_n": 0, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 0, "roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0}, director_orig_allow_damage_b=1, director_allow_damage_b=1))
            bridge.append(_snap_done("fixture", tick_ms=85000.0, counts={"roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0}, census_dynamic_n=0, census_foreign_n=0, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=[]))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "pass")


# ==============================================================================
# Honest full run and the format of the evidence (real core event log)
# ==============================================================================

class TestHonestRun(unittest.TestCase):
    def test_full_honest_run_is_pasa(self):
        with tempfile.TemporaryDirectory() as td:
            v = _eval_records(_full_run(), td)
            self.assertEqual(v["exit_code"], PASA, v["reasons"])
            self.assertEqual(set(_statuses(v).values()), {"pass"}, v["reasons"])
            cb = v["metrics"]["certified_budget"]
            self.assertEqual((cb["certified_step_id"], cb["certified_step_index"]), ("inc2", 3))

    def test_verdict_uses_the_core_check_list_format(self):
        with tempfile.TemporaryDirectory() as td:
            v = _eval_records(_full_run(), td)
            self.assertIsInstance(v["checks"], list)
            self.assertEqual([c["id"] for c in v["checks"]], list(s_perf_eval.CHECK_IDS))
            self.assertTrue(all(set(c) == {"detail", "id", "status"} for c in v["checks"]))

    def test_op_id_rename_is_invariant_on_a_full_run(self):
        with tempfile.TemporaryDirectory() as td:
            recs = _full_run()
            v1 = _eval_records(recs, td, "a")
            ren = {}
            recs2 = []
            for r in recs:
                r = dict(r)
                r["op_id"] = ren.setdefault(r["op_id"], f"{'%016x' % (len(ren) + 7)}-{len(ren) + 1}")
                recs2.append(r)
            v2 = _eval_records(recs2, td, "b")
            self.assertEqual(_statuses(v1), _statuses(v2))
            self.assertEqual(v1["exit_code"], v2["exit_code"])

    def test_fixture_only_floor_breaks_run_before_f1(self):
        with tempfile.TemporaryDirectory() as td:
            v = _eval_records(_full_run(fps={"fixture": 31.4}, budget_step=None, negatives=False), td)
            self.assertEqual(_chk(v, "PRF-05"), "fail")
            self.assertIn("below floor", _chk_detail(v, "PRF-05"))


class TestEvidenceFormat(unittest.TestCase):
    """The evaluator only reads what the core's bridge wrote (enq / deliver / result)."""

    def _events(self):
        return _records_to_events(_full_run(negatives=False, steps=("fixture",)))

    def _eval_events(self, td, events):
        part = Path(td) / "part"
        (part / "samples").mkdir(parents=True)
        _write_jsonl(part / "samples" / "bridge.jsonl", events)
        return s_perf_eval.evaluate(part)

    def test_premerged_records_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            v = self._eval_events(td, [r for r in _full_run(negatives=False, steps=("fixture",))])
            self.assertEqual(_chk(v, "PRF-01"), "fail")
            self.assertIn("not a bridge event", _chk_detail(v, "PRF-01"))

    def test_result_without_deliver_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ev = [e for e in self._events() if not (e["ev"] == "deliver" and e["verb"] == "perf_step_apply")]
            v = self._eval_events(td, ev)
            self.assertEqual(_chk(v, "PRF-01"), "fail")
            self.assertIn("result without deliver", " ".join(v["reasons"]))

    def test_result_without_enq_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ev = [e for e in self._events() if not (e["ev"] == "enq" and e["verb"] == "perf_preflight")]
            v = self._eval_events(td, ev)
            self.assertEqual(_chk(v, "PRF-01"), "fail")
            self.assertIn("without enq", " ".join(v["reasons"]))

    def test_duplicate_enq_op_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ev = self._events()
            ev.append(dict(ev[0]))
            v = self._eval_events(td, ev)
            self.assertEqual(_chk(v, "PRF-01"), "fail")
            self.assertIn("duplicate op_id", _chk_detail(v, "PRF-01") + " ".join(v["reasons"]))

    def test_lost_and_expired_ops_are_inconcluso_not_pass(self):
        with tempfile.TemporaryDirectory() as td:
            all_ev = self._events()
            lost_ops = {e["op_id"] for e in all_ev if e["ev"] == "enq" and e["verb"] == "perf_step_apply"}
            ev = [e for e in all_ev if not (e["ev"] == "result" and e["op_id"] in lost_ops)]
            ev += [{"ev": "lost", "t_ms": 5000.0, "op_id": o} for o in lost_ops]
            v = self._eval_events(td, ev)
            self.assertEqual(v["exit_code"], INCONCLUSO)

    def test_empty_traffic_cannot_pass(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            (part / "samples").mkdir(parents=True)
            _write_jsonl(part / "samples" / "bridge.jsonl", [{"ev": "hello", "t_ms": 1.0, "peer": "server", "http": 200}])
            v = s_perf_eval.evaluate(part)
            self.assertNotEqual(v["exit_code"], PASA)
            self.assertEqual(set(_statuses(v).values()), {"missing"})


# ==============================================================================
# E9 anti-fabrication negatives: each must give FALLA or INCONCLUSO FOR ITS REASON
# ==============================================================================

class TestE9AntiFabrication(unittest.TestCase):
    def _fixture_run(self, td, *, rows=None, apply_rec=None, snap_rows=None, census=None, ws_kwargs=None, fps=None):
        bridge = [_preflight_done()] + _step_segment(
            "fixture", rows=rows, apply_rec=apply_rec, snap_rows=snap_rows,
            census_dynamic_n=census, ws_kwargs=ws_kwargs, fps=fps)
        return _eval_records(bridge, td)

    def test_baseline_fixture_only_is_clean(self):
        with tempfile.TemporaryDirectory() as td:
            v = self._fixture_run(td)
            self.assertEqual({k: v for k, v in _statuses(v).items() if k in ("PRF-01", "PRF-02", "PRF-03", "PRF-04")},
                             {"PRF-01": "pass", "PRF-02": "pass", "PRF-03": "pass", "PRF-04": "pass"}, v["reasons"])

    def test_fixed_fps_disagrees_with_frame_counter(self):
        """avg_fps pinned to a round value while frame/tick_ms say 51 fps: PRF-04 recomputes from raw."""
        with tempfile.TemporaryDirectory() as td:
            rows = _build_window_rows("fixture", fps_mean=60.0, fps_counter=51.0)
            for r in rows:
                r["avg_fps"] = 60.0
            v = self._fixture_run(td, rows=rows)
            self.assertEqual(_chk(v, "PRF-04"), "fail")
            self.assertIn("FPS disagreement", _chk_detail(v, "PRF-04"))
            self.assertNotEqual(v["exit_code"], PASA)

    def test_fixed_fps_with_frozen_counters(self):
        """frame constant and dtsum 0 (a label, not a measurement): rejected as non-advancing."""
        with tempfile.TemporaryDirectory() as td:
            rows = _build_window_rows("fixture")
            for r in rows:
                r["avg_fps"], r["frame"], r["dtsum_ms"] = 60.0, 1000, 0.0
            v = self._fixture_run(td, rows=rows)
            self.assertEqual(_chk(v, "PRF-03"), "fail")
            self.assertIn("non-increasing frame or dtsum_ms", _chk_detail(v, "PRF-03"))
            self.assertEqual(_chk(v, "PRF-04"), "fail")

    def test_dtsum_that_does_not_follow_the_tick_clock(self):
        with tempfile.TemporaryDirectory() as td:
            rows = _build_window_rows("fixture")
            for i, r in enumerate(rows):
                r["dtsum_ms"] = round(i * 700.0, 1)
            v = self._fixture_run(td, rows=rows)
            self.assertEqual(_chk(v, "PRF-04"), "fail")
            self.assertIn("dtsum drift", _chk_detail(v, "PRF-04"))

    def test_observed_counts_missing_are_not_replaced_by_the_requested_echo(self):
        """The apply result only echoes the order (no *_alive_n): there is no observation."""
        with tempfile.TemporaryDirectory() as td:
            spec = STEP_SPEC["fixture"]
            rec = _step_apply_done("fixture")
            res = dict(rec["read"])
            nums = {k: v for k, v in wire.unpack_payload({k: res[k] for k in wire.PAYLOAD_KEYS})["num"].items()
                    if not k.endswith("_alive_n")}
            strs = wire.unpack_payload({k: res[k] for k in wire.PAYLOAD_KEYS})["str"]
            repacked = _pack_payload(scalars_str=strs, scalars_num=nums)
            rec["read"].update(repacked)
            v = self._fixture_run(td, apply_rec=rec)
            self.assertEqual(_chk(v, "PRF-02"), "fail")
            self.assertIn("count mismatch", _chk_detail(v, "PRF-02"))
            self.assertIn("alive=None", " ".join(v["reasons"]))

    def test_observed_counts_copied_from_the_order_but_world_has_fewer_entities(self):
        """apply says 45/45 alive (copied from the order); the raw per-entity rows list 34 roots."""
        with tempfile.TemporaryDirectory() as td:
            def snaps(cp):
                rows = _build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)
                return rows[:-1]
            v = self._fixture_run(td, snap_rows=snaps)
            self.assertEqual(_chk(v, "PRF-02"), "fail")
            self.assertIn("snap row count", _chk_detail(v, "PRF-02"))

    def test_census_sees_an_unregistered_entity(self):
        """Independent census = registered + 1 (an entity created without registering)."""
        with tempfile.TemporaryDirectory() as td:
            v = self._fixture_run(td, census=STEP_SPEC["fixture"]["roots_n"] + 1)
            self.assertEqual(_chk(v, "PRF-02"), "fail")
            self.assertIn("census_dynamic_n", _chk_detail(v, "PRF-02"))

    def test_census_misses_a_registered_entity(self):
        """Independent census = registered - 1 (a registered entity secretly destroyed)."""
        with tempfile.TemporaryDirectory() as td:
            v = self._fixture_run(td, census=STEP_SPEC["fixture"]["roots_n"] - 1)
            self.assertEqual(_chk(v, "PRF-02"), "fail")
            self.assertIn("census_dynamic_n", _chk_detail(v, "PRF-02"))

    def test_census_mirrors_a_registry_that_lost_entities(self):
        """Registry AND census both report 34 (census copied from the registry): the spec says 35."""
        with tempfile.TemporaryDirectory() as td:
            def snaps(cp):
                return _build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)[:-1]
            rec_snap = lambda cp: snaps(cp)
            bridge = [_preflight_done()] + _step_segment("fixture", snap_rows=rec_snap, census_dynamic_n=34)
            bridge = [b for b in bridge]
            for b in bridge:
                if b["verb"] == "perf_snap":
                    n = wire.unpack_payload({k: b["read"][k] for k in wire.PAYLOAD_KEYS})
                    n["num"]["roots_alive_n"] = 34
                    b["read"].update(_pack_payload(scalars_str=n["str"], scalars_num=n["num"], num_cols=list(SNAP_NCOL),
                                                    row_dicts=n["rows"]))
            v = _eval_records(bridge, td)
            self.assertEqual(_chk(v, "PRF-02"), "fail")
            self.assertIn("roots_alive_n=34", _chk_detail(v, "PRF-02"))

    def test_duplicate_window_row(self):
        with tempfile.TemporaryDirectory() as td:
            rows = _build_window_rows("fixture")
            rows[10] = dict(rows[9])
            v = self._fixture_run(td, rows=rows)
            self.assertEqual(_chk(v, "PRF-03"), "fail")
            self.assertIn("duplicate window row seq_n=9", _chk_detail(v, "PRF-03") + " ".join(v["reasons"]))

    def test_duplicate_snapshot_is_not_a_new_checkpoint(self):
        """The same snapshot (same tick_ms) pasted 13 times does not cover the window."""
        with tempfile.TemporaryDirectory() as td:
            bridge = [_preflight_done()] + _step_segment("fixture")
            snaps = [b for b in bridge if b["verb"] == "perf_snap"]
            first_tick = 41000.0
            for b in snaps:
                n = wire.unpack_payload({k: b["read"][k] for k in wire.PAYLOAD_KEYS})
                n["num"]["tick_ms"] = first_tick
                b["read"].update(_pack_payload(scalars_str=n["str"], scalars_num=n["num"], num_cols=list(SNAP_NCOL),
                                                row_dicts=n["rows"]))
            v = _eval_records(bridge, td)
            self.assertEqual(_chk(v, "PRF-02"), "fail")
            self.assertIn("checkpoint tick_ms spacing", _chk_detail(v, "PRF-02"))

    def test_snapshots_bunched_in_a_few_seconds_do_not_cover_the_window(self):
        with tempfile.TemporaryDirectory() as td:
            bridge = [_preflight_done()] + _step_segment("fixture")
            for i, b in enumerate([b for b in bridge if b["verb"] == "perf_snap"]):
                n = wire.unpack_payload({k: b["read"][k] for k in wire.PAYLOAD_KEYS})
                n["num"]["tick_ms"] = 41000.0 + i * 100.0
                b["read"].update(_pack_payload(scalars_str=n["str"], scalars_num=n["num"], num_cols=list(SNAP_NCOL),
                                                row_dicts=n["rows"]))
            v = _eval_records(bridge, td)
            self.assertEqual(_chk(v, "PRF-02"), "fail")
            self.assertIn("checkpoint tick_ms spacing", _chk_detail(v, "PRF-02"))

    def test_client_fps_is_not_server_fps(self):
        with tempfile.TemporaryDirectory() as td:
            ws_client = _window_start_done("fixture", job_id="job-client")
            ws_client["peer"] = ws_client["target_inst"] = "client"
            bridge = [_preflight_done(), _step_apply_done("fixture"), ws_client,
                      _snap_done("fixture", peer="client", avg_fps_now=60.0)]
            v = _eval_records(bridge, td)
            self.assertEqual(_chk(v, "PRF-01"), "fail")
            self.assertIn("on client role", " ".join(v["reasons"]))
            self.assertEqual(v["exit_code"], FALLA)

    def test_expected_seal_instead_of_observed(self):
        with tempfile.TemporaryDirectory() as td:
            rec = _step_apply_done("fixture", modset_sig=CANONICAL_MODSET_SIG)
            pre = _preflight_done(modset_sig=CANONICAL_MODSET_SIG, loaded_addons_csv="DayZExpansion_HeavyQA,DayZSandbox_QA")
            v = _eval_records([pre, rec], td)
            self.assertEqual(_chk(v, "PRF-01"), "fail")
            self.assertIn("loaded_addons_csv", " ".join(v["reasons"]))
            v2 = _eval_records([_preflight_done(), _step_apply_done("fixture", modset_sig="not-the-observed-seal")], td, "p2")
            self.assertEqual(_chk(v2, "PRF-01"), "fail")
            self.assertIn("modset_sig", _chk_detail(v2, "PRF-01"))

    def test_expected_seal_with_wrong_patch_count(self):
        with tempfile.TemporaryDirectory() as td:
            v = _eval_records([_preflight_done(cfg_patches_total_n=CANONICAL_PATCHES_N + 1)], td)
            self.assertEqual(_chk(v, "PRF-01"), "fail")
            self.assertIn("cfg_patches_total_n", " ".join(v["reasons"]))

    def test_two_perf_sampler_jobs_at_once(self):
        with tempfile.TemporaryDirectory() as td:
            rows = _build_window_rows("fixture")
            bridge = [_preflight_done(), _step_apply_done("fixture"),
                      _window_start_done("fixture", job_id="job-1"),
                      _window_start_done("fixture", job_id="job-2"),
                      _job_read_done("job-1", rows=rows, rows_total_n=61, **_window_marks(rows)),
                      _job_read_done("job-2", rows=rows, rows_total_n=61, **_window_marks(rows))]
            v = _eval_records(bridge, td)
            self.assertEqual(_chk(v, "PRF-03"), "fail")
            self.assertIn("concurrent perf_sampler job", _chk_detail(v, "PRF-03"))

    def test_sequential_sampler_jobs_are_fine(self):
        with tempfile.TemporaryDirectory() as td:
            v = _eval_records(_full_run(negatives=False, steps=("base", "fixture")), td)
            self.assertNotIn("concurrent", " ".join(v["reasons"]))

    def test_n1a_job_must_be_freed_with_job_free(self):
        with tempfile.TemporaryDirectory() as td:
            seg = [r for r in _negatives_segment() if not (r["verb"] == "job_free")]
            v = _eval_records(_full_run(negatives=False) + seg, td)
            self.assertEqual(_chk(v, "PRF-06"), "fail")
            self.assertIn("not freed with job_free", " ".join(v["reasons"]))

    def test_post_n5_snapshot_with_changed_census_breaks_invariance(self):
        """N1-N5 must leave the census untouched: the post-N5 snapshot (taken BEFORE N6) differs."""
        with tempfile.TemporaryDirectory() as td:
            seg = _negatives_segment(post_census_dynamic_n=999)
            v = _eval_records(_full_run(negatives=False) + seg, td)
            self.assertEqual(_chk(v, "PRF-06"), "fail")
            self.assertIn("census invariance broken on census_dynamic_n", " ".join(v["reasons"]))

    def test_n6_snapshot_census_cannot_stand_in_for_the_post_n5_one(self):
        """A 999 census only on the N6 injection snapshot does not matter (N6 closes separately),
        but dropping the post-N5 snapshot means N1-N5 invariance was never shown."""
        with tempfile.TemporaryDirectory() as td:
            seg = _negatives_segment()
            n5_end = max(i for i, r in enumerate(seg) if r["verb"] == "perf_preflight")
            post = next(i for i, r in enumerate(seg) if r["verb"] == "perf_snap" and r["peer"] == "server")
            del seg[post]
            v = _eval_records(_full_run(negatives=False) + seg, td)
            self.assertEqual(_chk(v, "PRF-06"), "fail")

    def test_evaluator_is_blind_to_mutant_names(self):
        from tests import test_probe_static
        self.assertEqual(test_probe_static.check_12_blind_evaluators(QA_DIR), [])


# ==============================================================================
# Technical failures (N12): INCONCLUSO, never PASA or FALLA by themselves
# ==============================================================================

class TestTechnical(unittest.TestCase):
    def _with_state(self, td, state, tech=None):
        rows = _build_window_rows("fixture")
        seg = _step_segment("fixture", read_kwargs={"state": state}, rows=rows)
        part = Path(td) / "part"
        _write_part(part, [_preflight_done()] + seg)
        if tech:
            (part / "samples" / "technical.json").write_text(json.dumps(tech), encoding="utf-8")
        return s_perf_eval.evaluate(part)

    def test_expired_job_is_technical_inconcluso(self):
        with tempfile.TemporaryDirectory() as td:
            v = self._with_state(td, "expired")
            self.assertEqual(v["exit_code"], INCONCLUSO)
            self.assertNotEqual(_chk(v, "PRF-03"), "pass")
            self.assertIn("technical", " ".join(v["reasons"]))

    def test_technical_json_blocks_a_pass(self):
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            _write_part(part, _full_run())
            (part / "samples" / "technical.json").write_text(json.dumps({"reason": "cleanup_incomplete"}), encoding="utf-8")
            v = s_perf_eval.evaluate(part)
            self.assertEqual(v["exit_code"], INCONCLUSO)
            self.assertIn("technical: cleanup_incomplete", v["reasons"])


# ==============================================================================
# Mutants (brief section 7): the literal injection, must_fail_checks == "fail"
# ==============================================================================

def _fixture_only(**seg_kw) -> list[dict]:
    return [_preflight_done()] + _step_segment("fixture", **seg_kw)


def _snap_rows_with(transform):
    def make(cp):
        rows = _build_snap_rows("fixture", cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)
        return transform(cp, rows)
    return make


def _roam(rows):
    return [r for r in rows if r["kind_code_n"] == 4 and r["role_code_n"] == 1]


def _mutant_records(name: str) -> list[dict]:
    if name == "client_fps":
        # perf_snap to the client with the injection; the client answers `done` with ITS fps
        return [_preflight_done(), _step_apply_done("fixture"), _snap_done("fixture", peer="client", avg_fps_now=60.0)]

    if name == "idle_actor":
        # fixture with roam speed 0: no displacement in any second, positions frozen, no patrol legs
        rows = _build_window_rows("fixture", roam_min_step=0.0)
        for r in rows:
            r["roam_disp_step_m"] = 0.0
        frozen = {}

        def tf(cp, snap):
            for r in _roam(snap):
                if cp == 0:
                    frozen[r["entity_idx_n"]] = (r["pos_x_m"], r["pos_z_m"])
                r["pos_x_m"], r["pos_z_m"] = frozen[r["entity_idx_n"]]
                r["wp_legs_n"], r["cum_disp_m"] = 0, 0.0
            return snap
        return _fixture_only(rows=rows, snap_rows=_snap_rows_with(tf))

    if name == "pending_emote":
        # emote requested but the callback 1101 never starts: pending, not playing, no callback id
        rows = _build_window_rows("fixture", emote_active=0, emote_cb1101=0)

        def tf(cp, snap):
            for r in snap:
                if r["kind_code_n"] == 4 and r["role_code_n"] == 2:
                    r.update(emote_playing_b=0, emote_pending_b=1, emote_cb_id_n=0, emote_cb_state_n=0,
                             emote_active_ticks_n=0, emote_completions_n=0)
            return snap
        return _fixture_only(rows=rows, snap_rows=_snap_rows_with(tf))

    if name == "early_burst_idle":
        # activity only during the first 10 s (cp 0..2); everything frozen afterwards
        rows = _build_window_rows("fixture")
        for i, r in enumerate(rows):
            if i > 10:
                r.update(roam_min_step_m=0.0, roam_disp_step_m=0.0, creatures_min_step_m=0.0, creatures_moved_step_n=0,
                         emote_active_actors_n=0, emote_cb_cmd1101_actors_n=0)
        ref: dict = {}

        def tf(cp, snap):
            for r in snap:
                if r["kind_code_n"] == 1:
                    continue
                key = r["entity_idx_n"]
                if cp <= 2:
                    ref[key] = dict(r)
                else:
                    frozen = ref[key]
                    for f in ("pos_x_m", "pos_z_m", "wp_legs_n", "cum_disp_m", "emote_active_ticks_n", "emote_completions_n"):
                        r[f] = frozen[f]
                    if r["role_code_n"] == 2:
                        r.update(emote_playing_b=0, emote_cb_state_n=0)
            return snap
        return _fixture_only(rows=rows, snap_rows=_snap_rows_with(tf))

    if name == "burst_per_quarter":
        # ~2 s of activity at the start of each 15 s quarter, stillness the rest (N7)
        rows = _build_window_rows("fixture")
        for i, r in enumerate(rows):
            if i % 15 >= 2:
                r.update(roam_min_step_m=0.0, roam_disp_step_m=0.0, creatures_min_step_m=0.0, creatures_moved_step_n=0,
                         emote_active_actors_n=0, emote_cb_cmd1101_actors_n=0)
        base = {}

        def tf(cp, snap):
            # positions only advance across the 5 s sub-steps that contain a burst (cp 0, 3, 6, 9)
            for r in snap:
                if r["kind_code_n"] == 1:
                    continue
                key = r["entity_idx_n"]
                if cp == 0:
                    base[key] = [dict(r), dict(r)]
                last = base[key][1]
                if cp % 3 == 1 and cp > 0:
                    base[key][1] = dict(r)
                    last = base[key][1]
                for f in ("pos_x_m", "pos_z_m", "wp_legs_n", "cum_disp_m", "emote_active_ticks_n", "emote_completions_n"):
                    r[f] = last[f]
                if r["kind_code_n"] == 4 and r["role_code_n"] == 2:
                    r.update(emote_playing_b=1 if cp % 3 == 0 else 0,
                             emote_cb_state_n=1 if cp % 3 == 0 else 0)
            return snap
        return _fixture_only(rows=rows, snap_rows=_snap_rows_with(tf))

    if name == "single_sample":
        # the job ends after 1 row (rows_total_n == 1) although the window asked for 61
        rows = _build_window_rows("fixture", n_rows=1)
        return _fixture_only(rows=rows, read_kwargs={"pages_n": 1})

    if name == "short_window":
        rows = _build_window_rows("fixture", n_rows=16, start_tick_ms=10000.0 + 5000.0)
        return _fixture_only(rows=rows, ws_kwargs={"warmup_ms": 5000.0, "duration_ms": 15000.0, "expected_rows_n": 16},
                             read_kwargs={"pages_n": 1})

    if name == "clustered_samples":
        # 61 rows, 60 s in total, but the gaps alternate 100 ms / 1900 ms (outside [500, 1500])
        rows = _build_window_rows("fixture")
        tick = rows[0]["tick_ms"]
        for i, r in enumerate(rows):
            if i:
                tick += 100.0 if i % 2 else 1900.0
            r["tick_ms"] = tick
            r["dtsum_ms"] = round(tick - rows[0]["tick_ms"], 1)
        return _fixture_only(rows=rows)

    if name == "desync_fps":
        rows = _build_window_rows("fixture", fps_mean=51.0 * 1.25, fps_counter=51.0)
        return _fixture_only(rows=rows)

    if name == "overload_floor":
        return [_preflight_done()] + _step_segment("base", fps=58.0) + _step_segment("fixture", fps=28.0)

    if name == "accept_budget_exceeded":
        return [_preflight_done()] + _n5_records("inc2", accept_reason="budget_exceeded:objects")

    raise KeyError(name)


class TestMutants(unittest.TestCase):
    def test_every_declared_mutant_has_an_injection_and_a_fault_code(self):
        self.assertEqual(set(s_perf_mutants.EXPECTED_MUTANTS), set(s_perf_mutants.MUTANT_QA_FAULTS))
        self.assertEqual(len(s_perf_mutants.EXPECTED_MUTANTS), 11)
        for name, spec in s_perf_mutants.EXPECTED_MUTANTS.items():
            self.assertEqual(spec["expected_exit_code"], 1)
            self.assertTrue(spec["must_fail_checks"])
            self.assertIsInstance(spec["allowed_non_pass"], dict)  # the shape aggregate_spike reads
            self.assertTrue(set(spec["allowed_non_pass"]).isdisjoint(spec["must_fail_checks"]))
            wire.format_qa_fault(s_perf_mutants.MUTANT_QA_FAULTS[name])  # fits the 24-char wire field

    def test_mutants_fail_their_check_with_fail_never_missing(self):
        for name, spec in s_perf_mutants.EXPECTED_MUTANTS.items():
            with self.subTest(mutant=name), tempfile.TemporaryDirectory() as td:
                v = _eval_records(_mutant_records(name), td)
                st = _statuses(v)
                for cid in spec["must_fail_checks"]:
                    self.assertEqual(st[cid], "fail", f"{name}: {cid} -> {st} {v['reasons'][:3]}")
                    self.assertTrue(_chk_detail(v, cid), f"{name}: {cid} fail without a detail")
                for cid, state in st.items():  # the exact rule of f03_common.aggregate_spike (rules 6 and 7)
                    if cid in spec["must_fail_checks"]:
                        continue
                    self.assertTrue(state == "pass" or state in spec["allowed_non_pass"].get(cid, []),
                                    f"{name}: {cid}={state} not allowed ({st}) {v['reasons'][:4]}")
                self.assertEqual(v["exit_code"], spec["expected_exit_code"])
                self.assertNotIn("technical", " ".join(v["reasons"]))

    def test_each_mutant_fails_for_its_injected_reason(self):
        expect = {
            "client_fps": ("PRF-01", "on client role"),
            "idle_actor": ("PRF-02", "roam_min_step_m"),
            "pending_emote": ("PRF-02", "emote callback 1101 inactive"),
            "early_burst_idle": ("PRF-02", "roam_min_step_m"),
            "burst_per_quarter": ("PRF-02", "roam_min_step_m"),
            "single_sample": ("PRF-03", "insufficient_samples"),
            "short_window": ("PRF-03", "insufficient_samples"),
            "clustered_samples": ("PRF-03", "sample interval"),
            "desync_fps": ("PRF-04", "FPS disagreement"),
            "overload_floor": ("PRF-05", "below floor"),
            "accept_budget_exceeded": ("PRF-06", "was not rejected"),
        }
        self.assertEqual(set(expect), set(s_perf_mutants.EXPECTED_MUTANTS))
        for name, (cid, needle) in expect.items():
            with self.subTest(mutant=name), tempfile.TemporaryDirectory() as td:
                v = _eval_records(_mutant_records(name), td)
                self.assertIn(needle, _chk_detail(v, cid) + " | " + " | ".join(v["reasons"]))

    def test_snapshot_only_mutants_are_caught_without_the_one_hz_rows(self):
        """burst/early-burst/idle injected only in the raw positions (snapshots) of an otherwise
        healthy 1 Hz series: the quarter reconstruction from raw positions still fails PRF-02."""
        for name in ("idle_actor", "early_burst_idle", "burst_per_quarter"):
            with self.subTest(mutant=name), tempfile.TemporaryDirectory() as td:
                recs = _mutant_records(name)
                healthy_rows = _build_window_rows("fixture")
                for r in recs:
                    if r["verb"] == "job_read":
                        n = wire.unpack_payload({k: r["read"][k] for k in wire.PAYLOAD_KEYS})
                        r["read"].update(_pack_payload(scalars_str=n["str"], scalars_num=n["num"],
                                                        num_cols=list(WINDOW_NCOL), row_dicts=healthy_rows))
                v = _eval_records(recs, td)
                self.assertEqual(_chk(v, "PRF-02"), "fail", name)
                self.assertTrue(any(w in " ".join(v["reasons"]) for w in ("stalled", "displacement", "inactive", "completions", "stationary")),
                                " | ".join(v["reasons"][:4]))


# ==============================================================================
# §8.1 Offline Tests: k* derivation, N5 8 subcases, geometry, modset equality
# ==============================================================================

class TestSection81Offline(unittest.TestCase):
    """Tests from §8.1 of the brief that can be tested with evaluator only."""

    def setUp(self):
        self.maxDiff = None

    def test_k_star_derivation_fixture_only(self):
        """k* = 1 when only fixture > 35.0 and inc1 <= 35.0."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done()]
            fps_map = {"base": 58.0, "fixture": 51.0, "inc1": 30.0, "inc2": 30.0}
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=fps_map[s], fps_counter=fps_map[s])
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                    _job_free_done(f"job-{s}"),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s, cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # Budget check at fixture cap (k*=1)
            spec = STEP_SPEC["fixture"]
            max_vals = {
                "max_objects_n": spec["objects_n"],
                "max_infected_n": spec["infected_n"],
                "max_animals_n": spec["animals_n"],
                "max_actors_n": spec["actors_n"],
                "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
                "max_children_n": spec["children_n"],
                "max_combined_roots_n": spec["roots_n"],
                "max_combined_entities_n": spec["entities_n"],
            }
            cand_vals = {
                "cand_objects_n": spec["objects_n"],
                "cand_infected_n": spec["infected_n"],
                "cand_animals_n": spec["animals_n"],
                "cand_actors_n": spec["actors_n"],
                "cand_wardrobe_total_n": spec["children_n"],
                "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"],
                "cand_extra_children_n": 0,
            }
            bridge.append(_budget_check_done(accepted=True, max_vals=max_vals, cand_vals=cand_vals))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-05"), "pass")
            cb = verdict["metrics"]["certified_budget"]
            self.assertEqual(cb["certified_step_id"], "fixture")
            self.assertEqual(cb["certified_step_index"], 1)

    def test_k_star_derivation_fixture_inc1(self):
        """k* = 2 when fixture and inc1 > 35.0, inc2 <= 35.0."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done()]
            fps_map = {"base": 58.0, "fixture": 51.0, "inc1": 44.0, "inc2": 30.0}
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=fps_map[s], fps_counter=fps_map[s])
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                    _job_free_done(f"job-{s}"),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s, cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # Budget check at inc1 cap (k*=2)
            spec = STEP_SPEC["inc1"]
            max_vals = {
                "max_objects_n": spec["objects_n"],
                "max_infected_n": spec["infected_n"],
                "max_animals_n": spec["animals_n"],
                "max_actors_n": spec["actors_n"],
                "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
                "max_children_n": spec["children_n"],
                "max_combined_roots_n": spec["roots_n"],
                "max_combined_entities_n": spec["entities_n"],
            }
            cand_vals = {
                "cand_objects_n": spec["objects_n"],
                "cand_infected_n": spec["infected_n"],
                "cand_animals_n": spec["animals_n"],
                "cand_actors_n": spec["actors_n"],
                "cand_wardrobe_total_n": spec["children_n"],
                "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"],
                "cand_extra_children_n": 0,
            }
            bridge.append(_budget_check_done(accepted=True, max_vals=max_vals, cand_vals=cand_vals))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            cb = verdict["metrics"]["certified_budget"]
            self.assertEqual(cb["certified_step_id"], "inc1")
            self.assertEqual(cb["certified_step_index"], 2)

    def test_k_star_derivation_all_three(self):
        """k* = 3 when all three load steps > 35.0."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done()]
            fps_map = {"base": 58.0, "fixture": 51.0, "inc1": 44.0, "inc2": 38.5}
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=fps_map[s], fps_counter=fps_map[s])
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                    _job_free_done(f"job-{s}"),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s, cp_index=cp, total_cps=EXPECTED_SNAP_CHECKPOINTS)))
            # Budget check at inc2 cap (k*=3)
            spec = STEP_SPEC["inc2"]
            max_vals = {
                "max_objects_n": spec["objects_n"],
                "max_infected_n": spec["infected_n"],
                "max_animals_n": spec["animals_n"],
                "max_actors_n": spec["actors_n"],
                "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
                "max_children_n": spec["children_n"],
                "max_combined_roots_n": spec["roots_n"],
                "max_combined_entities_n": spec["entities_n"],
            }
            cand_vals = {
                "cand_objects_n": spec["objects_n"],
                "cand_infected_n": spec["infected_n"],
                "cand_animals_n": spec["animals_n"],
                "cand_actors_n": spec["actors_n"],
                "cand_wardrobe_total_n": spec["children_n"],
                "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"],
                "cand_extra_children_n": 0,
            }
            bridge.append(_budget_check_done(accepted=True, max_vals=max_vals, cand_vals=cand_vals))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            cb = verdict["metrics"]["certified_budget"]
            self.assertEqual(cb["certified_step_id"], "inc2")
            self.assertEqual(cb["certified_step_index"], 3)

    def test_k_star_fixture_below_floor_blocks_f1(self):
        """fixture <= 35.0 -> PRF-05 fail (blocks F1 per brief)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", fps_mean=30.0, fps_counter=30.0)
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-05"), "fail")
            self.assertEqual(verdict["exit_code"], FALLA)

    def test_n5_8_subcases_individual(self):
        """Each of the 8 N5 subcases tested individually."""
        for reason in N5_REQUIRED_REASONS:
            with self.subTest(reason=reason):
                with tempfile.TemporaryDirectory() as td:
                    part = Path(td) / "part"
                    # Extract the violated limit from reason
                    # e.g., "budget_exceeded:objects" -> cand = max+1 for that category
                    bridge = [
                        _preflight_done(),
                        _step_apply_done("fixture"),
                    ]
                    # Build max_vals with budget check expected keys
                    spec = STEP_SPEC["fixture"]
                    max_vals = {
                        "max_objects_n": spec["objects_n"],
                        "max_infected_n": spec["infected_n"],
                        "max_animals_n": spec["animals_n"],
                        "max_actors_n": spec["actors_n"],
                        "max_wardrobe_per_actor_n": spec["wardrobe_per_actor_n"],
                        "max_children_n": spec["children_n"],
                        "max_combined_roots_n": spec["roots_n"],
                        "max_combined_entities_n": spec["entities_n"],
                    }
                    cand_vals = {
                        "cand_objects_n": spec["objects_n"],
                        "cand_infected_n": spec["infected_n"],
                        "cand_animals_n": spec["animals_n"],
                        "cand_actors_n": spec["actors_n"],
                        "cand_wardrobe_total_n": spec["children_n"],
                        "cand_wardrobe_max_per_actor_n": spec["wardrobe_per_actor_n"],
                        "cand_extra_children_n": 0,
                    }
                    cat = reason.split(":")[1]
                    if cat == "objects":
                        cand_vals["cand_objects_n"] = max_vals["max_objects_n"] + 1
                    elif cat == "infected":
                        cand_vals["cand_infected_n"] = max_vals["max_infected_n"] + 1
                    elif cat == "animals":
                        cand_vals["cand_animals_n"] = max_vals["max_animals_n"] + 1
                    elif cat == "actors":
                        cand_vals["cand_actors_n"] = max_vals["max_actors_n"] + 1
                    elif cat == "wardrobe_per_actor":
                        cand_vals["cand_wardrobe_max_per_actor_n"] = max_vals["max_wardrobe_per_actor_n"] + 1
                    elif cat == "children_total":
                        cand_vals["cand_extra_children_n"] = max_vals["max_children_n"] + 1
                    elif cat == "combined_roots":
                        cand_vals["cand_objects_n"] = max_vals["max_combined_roots_n"]
                        max_vals["max_combined_roots_n"] = max_vals["max_combined_roots_n"] - 1
                    elif cat == "combined_entities":
                        cand_vals["cand_objects_n"] = max_vals["max_combined_entities_n"]
                        max_vals["max_combined_entities_n"] = max_vals["max_combined_entities_n"] - 1
                    bridge.append(_budget_check_done(accepted=False, violation_path=reason, max_vals=max_vals, cand_vals=cand_vals))
                    _write_part(part, bridge)
                    verdict = s_perf_eval.evaluate(part)
                    self.assertEqual(_chk(verdict, "PRF-06"), "fail")

    def test_geometry_separation_and_director_distance(self):
        """Verify §2.2.2 geometry: min 10m between groups, all < 60m from director."""
        result = s_perf_eval.verify_geometry_spec(k=3)
        self.assertTrue(result["valid"], f"Geometry invalid: {result}")
        self.assertGreaterEqual(result["min_inter_group_dist_m"], MIN_GROUP_SEP_M)
        self.assertLess(result["max_director_dist_m"], MAX_DIRECTOR_DIST_M)
        self.assertLessEqual(result["max_center_dist_m"], CLEAR_RADIUS_M)
        self.assertGreaterEqual(result["min_actor_square_sep_m"], s_perf_eval.MIN_ACTOR_NEIGHBOR_SEP_M)

    def test_modset_exact_equality_canonical(self):
        """Modset must match canonical fixture exactly (N15)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            # Extra patch -> mismatch
            bridge = [_preflight_done(loaded_addons_csv=CANONICAL_ADDONS_CSV + ",DayZExpansion_HeavyQA")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_modset_missing_patch_rejected(self):
        """Missing required patch -> modset_mismatch."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            # Missing DayZSandbox_QA
            bridge = [_preflight_done(loaded_addons_csv="DayZExpansion_AI,DayZExpansion_AI_Scripts,DayZExpansion_Core_Scripts")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "fail")

    def test_op_id_rename_invariance(self):
        """Verdict invariant under bijective op_id renaming."""
        with tempfile.TemporaryDirectory() as td:
            part1 = Path(td) / "part1"
            part2 = Path(td) / "part2"
            bridge = [
                _preflight_done(op_id="aaaaaaaa-1"),
                _step_apply_done("fixture", op_id="bbbbbbbb-2"),
                _window_start_done("fixture", op_id="cccccccc-3", job_id="job-1"),
                _job_read_done("job-1", op_id="dddddddd-4", rows=_build_window_rows("fixture")),
            ]
            _write_part(part1, bridge)
            # Rename all op_ids
            bridge2 = []
            for i, rec in enumerate(bridge):
                new_rec = dict(rec)
                new_rec["op_id"] = f"new{i:08x}-{i+1}"
                if "payload" in new_rec and "str" in new_rec["payload"] and "job" in new_rec["payload"]["str"]:
                    new_rec["payload"]["str"]["job"] = f"job-new{i}"
                bridge2.append(new_rec)
            _write_part(part2, bridge2)
            v1 = s_perf_eval.evaluate(part1)
            v2 = s_perf_eval.evaluate(part2)
            self.assertEqual([(c["id"], c["status"]) for c in v1["checks"]], [(c["id"], c["status"]) for c in v2["checks"]])
            self.assertEqual(v1["exit_code"], v2["exit_code"])


# ==============================================================================
# Director cycle tests (N11): two cycles with original true/false
# ==============================================================================

class TestDirectorCycles(unittest.TestCase):
    """N11: Director AllowDamage capture per cycle, invalidated after cleanup."""

    def setUp(self):
        self.maxDiff = None

    def test_two_cycles_original_true_then_false(self):
        """Two consecutive cycles on same peer with original true then false."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            # Cycle 1: original true
            bridge = [
                _preflight_done(director_orig_allow_damage_b=1, director_allow_damage_b=0),
                _step_apply_done("fixture", director_orig_allow_damage_b=1, director_allow_damage_b=0),
                _step_apply_done("cleanup", cleanup_status="clean", director_orig_allow_damage_b=1, director_allow_damage_b=1),
            ]
            # Cycle 2: original false (different original)
            bridge.extend([
                _preflight_done(director_orig_allow_damage_b=0, director_allow_damage_b=0),
                _step_apply_done("fixture", director_orig_allow_damage_b=0, director_allow_damage_b=0),
                _step_apply_done("cleanup", cleanup_status="clean", director_orig_allow_damage_b=0, director_allow_damage_b=0),
            ])
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-01"), "pass")
            self.assertNotEqual(_chk(verdict, "PRF-06"), "fail")

    def test_new_preflight_before_cleanup_invalidates_cycle(self):
        """New preflight without cleanup of previous cycle -> PRF-06 violation."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(director_orig_allow_damage_b=1),
                _step_apply_done("fixture"),
                _preflight_done(director_orig_allow_damage_b=0),  # new cycle before cleanup
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(_chk(verdict, "PRF-06"), "fail")
            self.assertTrue(any("new perf_preflight before previous cycle cleanup" in r for r in verdict["reasons"]))


# ==============================================================================
# Independent register of the REAL traffic (wraps f03_common.PartContext)
# ==============================================================================

NONCE_OP_RE = re.compile(r"^[0-9a-f]{16}-\d+$")


class _Register:
    """Everything the bridge of each part really wrote and every order really enqueued,
    captured by wrapping PartContext (which owns bridge.jsonl and launches the peers).
    It does not read anything the runner writes."""

    def __init__(self):
        self.parts: dict[str, dict] = {}

    def part(self, name: str) -> dict:
        return self.parts.setdefault(name, {"events": [], "orders": []})


@contextlib.contextmanager
def _witnessed():
    reg = _Register()
    original = f03_common.PartContext

    class WitnessedPartContext(original):
        def open(self):
            slot = reg.part(self.part_name)
            real_writer = f03_common._JsonlWriter

            class Tee(real_writer):
                def write(inner, row):
                    if inner.path.name == "bridge.jsonl":
                        slot["events"].append(json.loads(json.dumps(row)))
                    super().write(row)

            f03_common._JsonlWriter = Tee
            try:
                super().open()
            finally:
                f03_common._JsonlWriter = real_writer
            if self.bridge is not None:
                real_enqueue = self.bridge.enqueue

                def enqueue(peer, verb, args, target_inst, ttl_ms, op_id=None, issued_ms=None):
                    slot["orders"].append({
                        "peer": peer, "verb": verb, "args": json.loads(json.dumps(args)),
                        "inst": target_inst, "ttl_ms": ttl_ms, "op_id": op_id, "issued_ms": issued_ms,
                        "registered_inst": self.bridge.registered(peer), "now_ms": self.bridge.now_ms(),
                        "nonce": self.op_nonce,
                    })
                    return real_enqueue(peer, verb, args, target_inst, ttl_ms, op_id=op_id, issued_ms=issued_ms)

                self.bridge.enqueue = enqueue

    patched = [(f03_common, "PartContext")]
    for mod in list(sys.modules.values()):
        if mod is not None and mod is not f03_common and getattr(mod, "PartContext", None) is original:
            patched.append((mod, "PartContext"))
    for mod, attr in patched:
        setattr(mod, attr, WitnessedPartContext)
    try:
        yield reg
    finally:
        for mod, attr in patched:
            setattr(mod, attr, original)


def _canon(rows: list[dict]) -> list[str]:
    return [json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows]


def _unpack_result(ev: dict) -> dict | None:
    body = ev.get("result") or {}
    rd = body.get("read") or {}
    if body.get("status") == "done" and rd.get("has") == ["payload"]:
        return wire.unpack_payload(rd)
    return None


def _register_violations(evidence: Path, reg: _Register) -> list[str]:
    """The runner's evidence must match the register: same bridge log line by line, and its own
    derived files (polls, final_snap) must correspond to traffic that really happened."""
    out: list[str] = []
    part_dirs = [d for d in sorted(Path(evidence).iterdir()) if d.is_dir() and (d / "samples").is_dir()]
    if not part_dirs:
        return ["no part directories with samples/"]
    for pdir in part_dirs:
        name = pdir.name
        on_disk = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl") if (pdir / "samples" / "bridge.jsonl").is_file() else []
        slot = reg.parts.get(name)
        if slot is None or not slot["events"]:
            if on_disk:
                out.append(f"{name}: registry empty but samples/bridge.jsonl has {len(on_disk)} lines (traffic never went through the bridge)")
            else:
                out.append(f"{name}: registry empty and no bridge traffic")
            continue
        if _canon(on_disk) != _canon(slot["events"]):
            out.append(f"{name}: samples/bridge.jsonl differs from the register ({len(on_disk)} vs {len(slot['events'])} lines)")
        events = slot["events"]
        enq_t = {e["op_id"]: e["t_ms"] for e in events if e.get("ev") == "enq"}
        res_t = {e["op_id"]: e["t_ms"] for e in events if e.get("ev") == "result"}
        jr = [(enq_t[o], res_t[o]) for o in enq_t if o in res_t
              and any(x.get("ev") == "enq" and x["op_id"] == o and x.get("verb") == "job_read" for x in events)]
        for pf in sorted((pdir / "samples").glob("step_*_polls.jsonl")):
            for p in f03_common.read_jsonl(pf):
                h = p.get("h_ms")
                if not any(a - 5.0 <= h <= b + 5.0 for a, b in jr):
                    out.append(f"{name}/{pf.name}: poll h_ms={h} matches no real job_read")
                    break
        fs = pdir / "samples" / "final_snap.json"
        if fs.is_file():
            snaps = [_unpack_result(e) for e in events if e.get("ev") == "result"
                     and any(x.get("ev") == "enq" and x["op_id"] == e["op_id"] and x.get("verb") == "perf_snap" for x in events)]
            snaps = [s for s in snaps if s]
            claimed = _unpack_any(json.loads(fs.read_text(encoding="utf-8")))
            if not snaps or claimed["num"] != snaps[-1]["num"]:
                out.append(f"{name}/final_snap.json does not equal the last real perf_snap result")
    return out


def _unpack_any(obj):
    return obj if "str" in obj else wire.unpack_payload(obj)


def _order_violations(reg: _Register) -> list[str]:
    """Every order the runner enqueued must be a valid order: instance, ttl, issued_ms, op_id, args, qa_fault."""
    out: list[str] = []
    for name, slot in reg.parts.items():
        for o in slot["orders"]:
            tag = f"{name}/{o['verb']}/{o['op_id']}"
            if not isinstance(o["inst"], str) or not o["inst"] or o["inst"] != o["registered_inst"]:
                out.append(f"{tag}: inst {o['inst']!r} != registered {o['registered_inst']!r}")
            if not isinstance(o["ttl_ms"], int) or isinstance(o["ttl_ms"], bool) or not (0 < o["ttl_ms"] <= 120000):
                out.append(f"{tag}: ttl_ms {o['ttl_ms']!r}")
            im = o["issued_ms"]
            if not isinstance(im, (int, float)) or isinstance(im, bool) or not math.isfinite(im) or im > o["now_ms"] + 1.0:
                out.append(f"{tag}: issued_ms {im!r}")
            if not isinstance(o["op_id"], str) or not NONCE_OP_RE.match(o["op_id"]) or not o["op_id"].startswith(o["nonce"] + "-"):
                out.append(f"{tag}: op_id is not <nonce16>-<n> of this part")
            try:
                wire.validate_payload(o["args"])
                wire.check_arg_strings(o["args"])
                qf = o["args"]["sv"][o["args"]["sk"].index("qa_fault")]
                if len(qf) != wire.QA_FAULT_LEN:
                    out.append(f"{tag}: qa_fault width {len(qf)}")
            except Exception as exc:
                out.append(f"{tag}: args not a valid wire order ({exc})")
    return out


GATE_ARGV = ["spike", "S-perf", "--both", "--build", "offline"]


def _run_gate(evidence: Path):
    import m1_gate
    with _witnessed() as reg:
        rc = m1_gate.main(GATE_ARGV + ["--evidence", str(evidence)])
    return rc, reg


class TestSyntheticRunnerIsDetected(unittest.TestCase):
    """A runner that never opens a PartContext (no peers, no bridge) and just writes traces."""

    def test_synthetic_runner_leaves_the_register_empty(self):
        import m1_gate
        fake = types.ModuleType("s_perf_run")

        def run(args, evidence, argv):
            part = Path(evidence) / "run"
            _write_part(part, _full_run())  # a perfectly clean-looking set of traces
            gate_core.write_json(part / "part.json", {"op_map": [], "op_nonce": "0123456789abcdef", "part": "run", "spike_id": "S-perf"})
            gate_core.write_json(part / "verdict.json", gate_core.make_verdict("S-perf", 0))
            return 0

        fake.run = run
        with tempfile.TemporaryDirectory() as td, mock.patch.dict(sys.modules, {"s_perf_run": fake}):
            evidence = Path(td) / "ev"
            with _witnessed() as reg:
                m1_gate.main(GATE_ARGV + ["--evidence", str(evidence)])
            # the evaluator alone is fooled by good-looking traces ...
            self.assertEqual(s_perf_eval.evaluate(evidence / "run")["exit_code"], PASA)
            # ... the independent register is not
            viol = _register_violations(evidence, reg)
            self.assertTrue(any("registry empty" in v for v in viol), viol)

    def test_register_flags_tampered_bridge_log(self):
        with tempfile.TemporaryDirectory() as td:
            evidence = Path(td) / "ev"
            part = evidence / "run"
            _write_part(part, _full_run(negatives=False, steps=("fixture",)))
            reg = _Register()
            reg.part("run")["events"] = f03_common.read_jsonl(part / "samples" / "bridge.jsonl")[:-3]
            viol = _register_violations(evidence, reg)
            self.assertTrue(any("differs from the register" in v for v in viol), viol)


# ==============================================================================
# End to end: the real gate with the fake peers, one shared run (these FAIL on the skeleton)
# ==============================================================================

class TestE2E(unittest.TestCase):
    """m1_gate spike S-perf --both --build offline, wrapped by the independent register."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        cls.evidence = Path(cls._td.name) / "ev"
        cls.rc, cls.reg = _run_gate(cls.evidence)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()

    def test_e2e_gate_exits_pasa(self):
        self.assertEqual(self.rc, 0, "the offline gate must give PASA (exit 0)")
        verdict = gate_core.read_json(self.evidence / "verdict.json")
        self.assertEqual(verdict["exit_code"], 0)
        self.assertEqual(verdict["verdict"], "PASA")

    def test_e2e_evidence_reevaluates_to_the_same_verdicts(self):
        """Not verdict.json: the evaluator is run again on the samples of every part."""
        run_v = s_perf_eval.evaluate(self.evidence / "run")
        self.assertEqual(run_v["exit_code"], PASA, run_v["reasons"])
        self.assertEqual(set(_statuses(run_v).values()), {"pass"})
        for name, spec in s_perf_mutants.EXPECTED_MUTANTS.items():
            pdir = self.evidence / f"mut-{name}"
            self.assertTrue(pdir.is_dir(), f"missing part mut-{name}")
            v = s_perf_eval.evaluate(pdir)
            for cid in spec["must_fail_checks"]:
                self.assertEqual(_statuses(v)[cid], "fail", f"{name}: {v['reasons'][:3]}")

    def test_e2e_register_matches_runner_evidence(self):
        self.assertEqual(_register_violations(self.evidence, self.reg), [])

    def test_e2e_run_sequence_really_went_through_the_bridge(self):
        self.assertIn("run", self.reg.parts, "no traffic registered for part run/")
        events = self.reg.parts["run"]["events"]
        verbs = [e["verb"] for e in events if e.get("ev") == "enq" and e.get("peer") == "server"]
        count = lambda v: verbs.count(v)
        self.assertGreaterEqual(count("perf_preflight"), 1)
        self.assertGreaterEqual(count("perf_step_apply"), 5)        # 4 steps + cleanup
        self.assertGreaterEqual(count("perf_window_start"), 4)
        self.assertGreaterEqual(count("perf_snap"), 4 * EXPECTED_SNAP_CHECKPOINTS)
        self.assertGreaterEqual(count("perf_budget_check"), 1 + 8)  # cap + N5
        self.assertGreaterEqual(count("job_read"), 4)
        self.assertGreaterEqual(count("job_free"), 4)
        self.assertTrue(any(e.get("verb") == "perf_snap" and e.get("peer") == "client" for e in events if e.get("ev") == "enq"),
                        "N2: a perf_snap to the client is part of the battery")
        delivered = {e["op_id"] for e in events if e.get("ev") == "deliver"}
        self.assertTrue(all(e["op_id"] in delivered for e in events if e.get("ev") == "result"))

    def test_e2e_orders_are_valid(self):
        self.assertTrue(self.reg.parts, "no orders were enqueued through the bridge")
        self.assertEqual(_order_violations(self.reg), [])

    def test_e2e_two_director_cycles_with_different_originals(self):
        """N11: consecutive cycles on the same server peer with originals true and false; each
        cleanup restores that cycle's original, never the previous one."""
        cycles = []
        for name in sorted(self.reg.parts):
            ev = self.reg.parts[name]["events"]
            by_id = {e["op_id"]: e for e in ev if e.get("ev") == "enq"}
            for e in ev:
                if e.get("ev") != "result" or by_id.get(e["op_id"], {}).get("peer") != "server":
                    continue
                u = _unpack_result(e)
                verb = by_id[e["op_id"]]["verb"]
                if u and verb == "perf_preflight":
                    cycles.append({"orig": u["num"]["director_orig_allow_damage_b"], "restored": None})
                elif u and verb == "perf_step_apply" and u["str"].get("step_id") == "cleanup" \
                        and u["str"].get("cleanup_status") == "clean" and cycles and cycles[-1]["restored"] is None:
                    cycles[-1]["restored"] = u["num"]["director_allow_damage_b"]
        self.assertGreaterEqual(len(cycles), 2)
        self.assertEqual({c["orig"] for c in cycles}, {0, 1})
        for c in cycles:
            self.assertEqual(c["restored"], c["orig"])


if __name__ == "__main__":
    unittest.main()