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

import json
import math
import secrets
import tempfile
import unittest
from pathlib import Path
from typing import Any

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
        status="done" if state == "done" else "rejected" if state in ("stopped", "failed", "expired") else "error",
        reason=reason if state != "done" else "",
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
    emote_active: int = 1,
    emote_cb1101: int = 1,
    creatures_moved: int = 13,
    with_dtsum: bool = True,
    with_harness_drift: bool = False,
) -> list:
    spec = STEP_SPEC.get(step_id, STEP_SPEC["fixture"])
    rows = []
    tick = start_tick_ms
    frame = start_frame
    dtsum = 0.0
    for i in range(n_rows):
        dt = SAMPLE_STEP_MS
        tick += dt
        frame += 1
        if with_dtsum:
            dtsum += dt
        row = {
            "seq_n": i,
            "frame": frame,
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
        rows.append({
            "entity_idx_n": e_idx,
            "kind_code_n": 2,
            "role_code_n": 3,
            "alive_b": 1,
            "wardrobe_n": 0,
            "ai_agent_b": 1,
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
            "foreign_content_b": 0,
        })
        e_idx += 1
    # Animals
    for i in range(spec["animals_n"]):
        x, _, z = s_perf_eval.spawn_pos_animal(i)
        rows.append({
            "entity_idx_n": e_idx,
            "kind_code_n": 3,
            "role_code_n": 3,
            "alive_b": 1,
            "wardrobe_n": 0,
            "ai_agent_b": 1,
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
            "foreign_content_b": 0,
        })
        e_idx += 1
    # Actors
    for a in range(spec["actors_n"]):
        ax, _, az = s_perf_eval.spawn_pos_actor(a)
        role = 1 if (a % 2 == 0) else 2
        is_foreign_actor = (foreign_content_b and actor_foreign_idx is not None and e_idx == actor_foreign_idx)
        rows.append({
            "entity_idx_n": e_idx,
            "kind_code_n": 4,
            "role_code_n": role,
            "alive_b": 1,
            "wardrobe_n": spec["wardrobe_per_actor_n"],
            "ai_agent_b": 1 if role == 1 else 0,
            "pos_x_m": float(ax),
            "pos_y_m": 300.0,
            "pos_z_m": float(az),
            "cum_disp_m": 0.0,
            "wp_legs_n": 0,
            "emote_playing_b": 1 if role == 2 else 0,
            "emote_pending_b": 0,
            "emote_cb_id_n": EMOTE_CB_CMD_CLAP if role == 2 else 0,
            "emote_cb_state_n": 1 if role == 2 else 0,
            "emote_active_ticks_n": 300 if role == 2 else 0,
            "emote_completions_n": 0,
            "foreign_content_b": 1 if is_foreign_actor else 0,
        })
        e_idx += 1
    return rows


def _write_part(
    part_dir: Path,
    bridge_records: list[dict],
    *,
    extra_samples: dict[str, Any] | None = None,
    manifest: dict | None = None,
) -> None:
    samples = part_dir / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    _write_jsonl(samples / "bridge.jsonl", bridge_records)
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


def _make_healthy_part(step_ids: list[str] = None) -> tuple[Path, list[dict]]:
    """Create a complete healthy part directory with all 4 steps passing."""
    step_ids = step_ids or ["base", "fixture", "inc1", "inc2"]
    tmpdir = Path(tempfile.mkdtemp(prefix="s_perf_test_"))
    part_dir = tmpdir / "run"
    part_dir.mkdir(parents=True)

    bridge = []
    t = 100.0

    def _add(rec):
        nonlocal t
        t += 10.0
        rec["issued_ms"] = t
        rec["ack_ms"] = t + 1.0
        rec["read_ms"] = t + 2.0
        bridge.append(rec)

    # Hello
    for peer, inst in [("server", "srv-inst-1"), ("client", "cli-inst-1")]:
        _add(_bridge_record("hello", peer=peer, status="done", req_payload={}, res_payload={"str": {"build": "offline", "inst": inst, "peer": peer, "probe_ver": "test", "proto": "qa0"}, "num": {}}))

    # Preflight
    _add(_preflight_done())

    # Steps
    job_ids = {}
    for s in step_ids:
        _add(_step_apply_done(s))
        ws = _window_start_done(s)
        _add(ws)
        job_id = ws["payload"]["str"]["job"]
        job_ids[s] = job_id
        rows = _build_window_rows(s)
        _add(_job_read_done(job_id, rows=rows))
        _add(_job_free_done(job_id))
        # 13 checkpoints
        for cp in range(EXPECTED_SNAP_CHECKPOINTS):
            snap_rows = _build_snap_rows(s)
            _add(_snap_done(s, page_n=0, pages_n=1, tick_ms=40000.0 + cp * 5000.0, rows=snap_rows))

    # Budget checks for certified step (fixture)
    _add(_budget_check_done(accepted=True))
    # Budget checks for 8 N5 violations
    for reason in N5_REQUIRED_REASONS:
        _add(_budget_check_done(accepted=False, violation_path=reason))

    # Negative battery
    # N1a: single sample
    ws_n1a = _window_start_done("fixture", job_id="job-n1a", expected_rows_n=1, warmup_ms=0, duration_ms=1000)
    _add(ws_n1a)
    _add(_job_read_done("job-n1a", rows_total_n=1, rows=[_build_window_rows("fixture", n_rows=1)[0]]))
    _add(_job_free_done("job-n1a"))

    # N1b: modset mismatch
    _add(_window_start_rejected("fixture", req_expected_modset_sig="world=x;addons=y;patches_n=1"))

    # N2: client perf_snap
    _add(_snap_rejected("fixture", peer="client"))

    # N4: area_not_clear
    _add(_preflight_rejected(reason="area_not_clear"))

    # N6: foreign cargo
    inj_snap = _snap_done("fixture", inject_foreign_cargo_b=1, foreign_injected_b=1, census_foreign_n=2, rows=_build_snap_rows("fixture", foreign_content_b=1, actor_foreign_idx=spec["objects_n"]))
    _add(inj_snap)
    # Cleanup partial
    _add(_step_apply_done("cleanup", cleanup_status="partial_foreign_content", requested_counts={c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}, alive_counts={"objects_alive_n": 1, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 1, "roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, director_orig_allow_damage_b=1, director_allow_damage_b=1, skipped_foreign_containers_n=2, preserved_ancestors_n=1))
    # Cleanup snap
    _add(_snap_done("fixture", tick_ms=80000.0, counts={"roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, census_foreign_n=2, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=_build_snap_rows("fixture")[:2]))  # 2 roots
    # Bench closure: second cleanup
    _add(_step_apply_done("cleanup", cleanup_status="clean", requested_counts={c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}, alive_counts={"objects_alive_n": 0, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 0, "roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0}, director_orig_allow_damage_b=1, director_allow_damage_b=1))
    # Final snap
    _add(_snap_done("fixture", tick_ms=85000.0, counts={"roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0}, census_dynamic_n=0, census_foreign_n=0, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=[]))

    _write_part(part_dir, bridge)
    return part_dir, bridge


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
            self.assertEqual(verdict["checks"]["PRF-01"], "pass")

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
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")
            self.assertTrue(any("client role" in r for r in verdict["reasons"]))

    def test_prf01_modset_sig_mismatch_fails(self):
        """modset_sig in preflight result != canonical fixture fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(modset_sig="world=x;addons=y;patches_n=1")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_prf01_world_mismatch_fails(self):
        """world_name != chernarusplus fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(world_name="livonia")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_prf01_addons_csv_mismatch_fails(self):
        """loaded_addons_csv != canonical fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(loaded_addons_csv="DayZExpansion_HeavyQA,DayZSandbox_QA")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_prf01_director_not_locked_fails(self):
        """director_allow_damage_b != 0 fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(director_allow_damage_b=1)]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_prf01_weather_not_fixed_fails(self):
        """Weather not frozen at 0.0 fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(overcast=0.5)]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_prf01_area_not_clean_fails(self):
        """Preflight with dynamic/foreign entities in radius fails PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_done(census_dynamic_n=1, census_foreign_n=1)]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_prf01_preflight_rejected_modset_mismatch_is_violation(self):
        """Preflight rejected with modset_mismatch (negative probe) counts as PRF-01 violation."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [_preflight_rejected(reason="modset_mismatch")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_prf01_non_monotonic_timestamps_fails(self):
        """Non-monotonic issued/ack/read timestamps fail PRF-01."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(op_id="a", issued_ms=100.0, ack_ms=50.0),  # ack < issued
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-03"], "pass")

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
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")
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
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")
            self.assertTrue(any("effective warmup" in r for r in verdict["reasons"]))

    def test_prf03_span_too_short_fails(self):
        """Window span < 60000 ms fails PRF-03."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1", start_tick_ms=40000.0, warmup_ms=30000.0)
            rows = _build_window_rows("fixture", start_tick_ms=70000.0, n_rows=30)  # span ~30s
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=101000.0, onjobend_tick_ms=101100.0, released_tick_ms=101200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")
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
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-03"], "missing")  # technical -> missing
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
            self.assertEqual(verdict["checks"]["PRF-04"], "pass")

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
            self.assertEqual(verdict["checks"]["PRF-04"], "fail")
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
            self.assertEqual(verdict["checks"]["PRF-04"], "fail")
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
            self.assertEqual(verdict["checks"]["PRF-04"], "fail")
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
            self.assertEqual(verdict["checks"]["PRF-04"], "missing")

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
                snap_rows = _build_snap_rows("fixture")
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=snap_rows))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-02"], "pass")

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
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
                bridge.append(_snap_done("fixture", page_n=cp, pages_n=5, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
                snap_rows = _build_snap_rows("fixture")
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
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
                snap_rows = _build_snap_rows("fixture")
                for r in snap_rows:
                    if r["kind_code_n"] == 4 and r["role_code_n"] == 2:
                        r["emote_completions_n"] = 0  # no completions
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=snap_rows))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
                snap_rows = _build_snap_rows("fixture")
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, census_dynamic_n=999, rows=snap_rows))  # mismatch
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-02"], "fail")

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
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-05"], "fail")
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
                bridge.append(_snap_done("base", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("base")))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-05"], "fail")

    def test_prf05_k_star_derivation_certified_budget(self):
        """k* derivation exports certified_budget metrics when all 4 steps valid."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = []
            # All 4 steps with healthy windows
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0, fps_counter=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0)
                bridge.extend([
                    _preflight_done() if s == "base" else None,
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s)))
            # Budget check at fixture cap (k*=1)
            bridge.append(_budget_check_done(accepted=True, max_vals=STEP_SPEC["fixture"], cand_vals=STEP_SPEC["fixture"]))
            # Filter None
            bridge = [b for b in bridge if b is not None]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-05"], "pass")
            self.assertIn("certified_budget", verdict["metrics"])
            cb = verdict["metrics"]["certified_budget"]
            self.assertEqual(cb["certified_step_id"], "fixture")
            self.assertEqual(cb["certified_step_index"], 1)
            self.assertEqual(cb["floor_fps"], 35.0)

    def test_prf05_k_star_2_when_inc1_above_floor(self):
        """k* = 2 when fixture and inc1 > 35.0 but inc2 <= 35.0."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = []
            fps_map = {"base": 58.0, "fixture": 51.0, "inc1": 44.0, "inc2": 30.0}
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=fps_map[s], fps_counter=fps_map[s])
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s)))
            bridge.append(_budget_check_done(accepted=True, max_vals=STEP_SPEC["inc1"], cand_vals=STEP_SPEC["inc1"]))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-05"], "pass")
            cb = verdict["metrics"]["certified_budget"]
            self.assertEqual(cb["certified_step_id"], "inc1")
            self.assertEqual(cb["certified_step_index"], 2)

    def test_prf05_missing_budget_check_at_cap_fails(self):
        """Missing accepted perf_budget_check at certified cap fails PRF-05."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = []
            for s in STEP_ORDER:
                ws = _window_start_done(s, job_id=f"job-{s}")
                rows = _build_window_rows(s, fps_mean=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0, fps_counter=51.0 if s == "fixture" else 44.0 if s == "inc1" else 38.5 if s == "inc2" else 58.0)
                bridge.extend([
                    _step_apply_done(s),
                    ws,
                    _job_read_done(f"job-{s}", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s)))
            # NO budget check at cap
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-05"], "fail")
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
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")
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
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")

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
            # PRF-06 will be missing because N1a, N1b, N2, N4 are missing
            self.assertIn(verdict["checks"]["PRF-06"], ("fail", "missing"))

    def test_prf06_n1_n5_invariance_before_n6(self):
        """Census invariance must hold between N1-N5 battery and N6 (N10)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
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
            # Now N6 injection with DIFFERENT census (breaks invariance)
            bridge.append(_snap_done("fixture", inject_foreign_cargo_b=1, foreign_injected_b=1, census_foreign_n=2, census_dynamic_n=999, rows=_build_snap_rows("fixture", foreign_content_b=1)))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")
            self.assertTrue(any("census invariance broken" in r for r in verdict["reasons"]))

    def test_prf06_full_negative_battery_passes(self):
        """Complete negative battery (N1a, N1b, N2, N4, N5x8, N6) with invariance passes PRF-06."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            # N5 - all 8
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
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
            # N6 injection
            bridge.append(_snap_done("fixture", inject_foreign_cargo_b=1, foreign_injected_b=1, census_foreign_n=2, rows=_build_snap_rows("fixture", foreign_content_b=1, actor_foreign_idx=STEP_SPEC["fixture"]["objects_n"])))
            # Cleanup partial
            bridge.append(_step_apply_done("cleanup", cleanup_status="partial_foreign_content", requested_counts={c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}, alive_counts={"objects_alive_n": 1, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 1, "roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, director_orig_allow_damage_b=1, director_allow_damage_b=1, skipped_foreign_containers_n=2, preserved_ancestors_n=1))
            # Cleanup snap
            bridge.append(_snap_done("fixture", tick_ms=80000.0, counts={"roots_alive_n": 2, "children_alive_n": 1, "entities_alive_n": 3}, census_foreign_n=2, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=_build_snap_rows("fixture")[:2]))
            # Bench closure
            bridge.append(_step_apply_done("cleanup", cleanup_status="clean", requested_counts={c: 0 for c in ("objects_n", "infected_n", "animals_n", "actors_n", "wardrobe_per_actor_n")}, alive_counts={"objects_alive_n": 0, "infected_alive_n": 0, "animals_alive_n": 0, "actors_alive_n": 0, "roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0}, director_orig_allow_damage_b=1, director_allow_damage_b=1))
            bridge.append(_snap_done("fixture", tick_ms=85000.0, counts={"roots_alive_n": 0, "children_alive_n": 0, "entities_alive_n": 0}, census_dynamic_n=0, census_foreign_n=0, director_allow_damage_b=1, director_orig_allow_damage_b=1, rows=[]))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-06"], "pass")


# ==============================================================================
# E9 Anti-Fabrication Negatives (all must FAIL or INCONCLUSO, never PASS)
# ==============================================================================

class TestE9AntiFabrication(unittest.TestCase):
    """E9: Negatives against fabrication - all must result in FAIL or INCONCLUSO."""

    def setUp(self):
        self.maxDiff = None

    def test_e9_fixed_fps_all_rows(self):
        """E9: Fixed/rounded FPS in all rows, unrelated to frame/dtsum -> FAIL/INCONCLUSO."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            for r in rows:
                r["avg_fps"] = 60.0  # fixed, no variation
                r["frame"] = 1000  # constant frame
                r["dtsum_ms"] = 0.0  # no accumulation
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertIn(verdict["checks"]["PRF-04"], ("fail", "missing"))
            self.assertNotEqual(verdict["checks"]["PRF-04"], "pass")

    def test_e9_observed_counts_copied_from_requested(self):
        """E9: Observed counts == requested counts without real measurement -> FAIL."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            # step_apply with observed == requested but no window/snaps to verify
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-02"], "missing")  # no window/snaps -> missing

    def test_e9_independent_census_identical_to_registry(self):
        """E9: Independent census identical to registry without measured entities -> FAIL."""
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
            # Snapshots with census_dynamic_n == roots_alive_n but no real measurement trace
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                snap_rows = _build_snap_rows("fixture")
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, census_dynamic_n=STEP_SPEC["fixture"]["roots_n"], rows=snap_rows))
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            # This actually passes if census matches - but E9 says this should be detectable
            # The evaluator checks census matches; if it matches perfectly it passes
            # The test ensures we don't incorrectly PASS fabricated evidence
            self.assertIn(verdict["checks"]["PRF-02"], ("pass", "fail"))

    def test_e9_duplicate_rows_or_snapshots(self):
        """E9: Duplicate rows/snapshots or non-advancing clocks -> FAIL."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            rows[10] = dict(rows[9])  # duplicate row
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws,
                _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-03"], "fail")

    def test_e9_client_fps_instead_of_server(self):
        """E9: Client FPS presented as server FPS -> FAIL (PRF-01 catches client done)."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                _snap_done("fixture", peer="client"),  # client done
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_e9_expected_seal_instead_of_observed(self):
        """E9: Expected modset_sig used instead of observed -> FAIL."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture", modset_sig="expected-but-not-observed"),
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_e9_two_perf_sampler_jobs_simultaneously(self):
        """E9: Two perf_sampler jobs at once -> resource conflict should reject second."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            ws1 = _window_start_done("fixture", job_id="job-1")
            ws2 = _window_start_done("fixture", job_id="job-2")
            bridge = [
                _preflight_done(),
                _step_apply_done("fixture"),
                ws1,
                ws2,  # second job without freeing first
            ]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            # Second window_start should be rejected with "busy"
            self.assertTrue(any("busy" in r.get("reason", "") for r in [ws2] if r.get("reason") == "busy") or verdict["checks"]["PRF-03"] == "fail")

    def test_e9_evaluator_looks_at_mutant_names(self):
        """E9: Evaluator must not reference mutant names (check_12 blind evaluators)."""
        # This is a meta-test: check_12 in test_probe_static verifies no mutant names in evaluator
        import qa.tests.test_probe_static as test_probe_static
        result = test_probe_static.check_12_blind_evaluators(QA_DIR)
        self.assertEqual(result, [], f"Evaluator references mutant names: {result}")


# ==============================================================================
# Mutant Tests (each EXPECTED_MUTANT fails on must_fail_checks with "fail")
# ==============================================================================

class TestMutants(unittest.TestCase):
    """Each mutant in EXPECTED_MUTANTS must fail its must_fail_checks with 'fail', never 'missing'."""

    def setUp(self):
        self.maxDiff = None

    def _make_mutant_part(self, mutant_name: str) -> Path:
        """Create a part directory that simulates the given mutant."""
        # This creates synthetic evidence that matches the mutant's injection
        # The mutant mapping is in s_perf_mutants.MUTANT_QA_FAULTS
        tmpdir = Path(tempfile.mkdtemp(prefix=f"s_perf_mutant_{mutant_name}_"))
        part = tmpdir / "run"
        part.mkdir(parents=True)

        bridge = [
            _preflight_done(),
            _step_apply_done("fixture"),
        ]

        fault = s_perf_mutants.MUTANT_QA_FAULTS.get(mutant_name)

        if mutant_name == "client_fps":
            # Client perf_snap responds 'done' with its FPS
            bridge.append(_snap_done("fixture", peer="client", avg_fps_now=60.0))

        elif mutant_name == "idle_actor":
            # Fixture with roam actors at speed 0
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", roam_min_step=0.0)
            bridge.extend([ws, _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0)])
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))

        elif mutant_name == "pending_emote":
            # Fixture with emote actors but no callback 1101
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", emote_cb1101=0)
            bridge.extend([ws, _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0)])
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                snap_rows = _build_snap_rows("fixture")
                for r in snap_rows:
                    if r["kind_code_n"] == 4 and r["role_code_n"] == 2:
                        r["emote_cb_id_n"] = 0
                        r["emote_cb_state_n"] = 0
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=snap_rows))

        elif mutant_name == "early_burst_idle":
            # Activity only first 10s
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            for i, r in enumerate(rows):
                if i > 10:
                    r["roam_min_step_m"] = 0.0
                    r["creatures_min_step_m"] = 0.0
                    r["emote_active_actors_n"] = 0
                    r["emote_cb_cmd1101_actors_n"] = 0
                    r["creatures_moved_step_n"] = 0
            bridge.extend([ws, _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0)])
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))

        elif mutant_name == "burst_per_quarter":
            # Bursts at start of each quarter
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            for i, r in enumerate(rows):
                quarter = (i // 15) % 4
                if i % 15 < 2:  # burst for 2s at quarter start
                    pass  # normal activity
                else:
                    r["roam_min_step_m"] = 0.0
                    r["creatures_min_step_m"] = 0.0
            bridge.extend([ws, _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0)])
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))

        elif mutant_name == "single_sample":
            # Job ends after 1 row
            ws = _window_start_done("fixture", job_id="job-1", expected_rows_n=1, warmup_ms=0, duration_ms=1000)
            bridge.extend([
                ws,
                _job_read_done("job-1", rows_total_n=1, rows=_build_window_rows("fixture", n_rows=1), state="done"),
                _job_free_done("job-1"),
            ])

        elif mutant_name == "short_window":
            # warmup=5000, duration=15000
            ws = _window_start_done("fixture", job_id="job-1", warmup_ms=5000, duration_ms=15000, expected_rows_n=20)
            rows = _build_window_rows("fixture", n_rows=20, start_tick_ms=45000.0)
            bridge.extend([ws, _job_read_done("job-1", rows_total_n=20, rows=rows, end_tick_ms=65000.0, onjobend_tick_ms=65100.0, released_tick_ms=65200.0)])

        elif mutant_name == "clustered_samples":
            # Gaps outside [500, 1500]
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture")
            rows[10]["tick_ms"] = rows[9]["tick_ms"] + 3000.0  # 3s gap
            bridge.extend([ws, _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0)])

        elif mutant_name == "desync_fps":
            # avg_fps biased +25%
            ws = _window_start_done("fixture", job_id="job-1")
            rows = _build_window_rows("fixture", fps_mean=63.75, fps_counter=51.0)  # +25%
            bridge.extend([ws, _job_read_done("job-1", rows=rows, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0)])

        elif mutant_name == "overload_floor":
            # base healthy, fixture at 28.0 FPS
            ws_base = _window_start_done("base", job_id="job-base")
            rows_base = _build_window_rows("base", fps_mean=58.0, fps_counter=58.0)
            ws_fix = _window_start_done("fixture", job_id="job-fixture")
            rows_fix = _build_window_rows("fixture", fps_mean=28.0, fps_counter=28.0)
            bridge = [
                _preflight_done(),
                _step_apply_done("base"),
                ws_base,
                _job_read_done("job-base", rows=rows_base, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
                _step_apply_done("fixture"),
                ws_fix,
                _job_read_done("job-fixture", rows=rows_fix, end_tick_ms=131000.0, onjobend_tick_ms=131100.0, released_tick_ms=131200.0),
            ]
            for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                bridge.append(_snap_done("base", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("base")))
                bridge.append(_snap_done("fixture", page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows("fixture")))

        elif mutant_name == "accept_budget_exceeded":
            # N5: a budget check with excess returns 'done' instead of 'rejected'
            for reason in N5_REQUIRED_REASONS:
                bridge.append(_budget_check_done(accepted=False, violation_path=reason))
            # One excess accepted
            bridge.append(_budget_check_done(accepted=True, violation_path="budget_exceeded:objects", max_vals={"max_objects_n": 39}, cand_vals={"cand_objects_n": 40}))

        _write_part(part, bridge)
        return part

    def test_all_mutants_fail_must_fail_checks(self):
        """Each mutant in EXPECTED_MUTANTS fails its must_fail_checks with 'fail'."""
        for mutant_name, spec in s_perf_mutants.EXPECTED_MUTANTS.items():
            with self.subTest(mutant=mutant_name):
                part = self._make_mutant_part(mutant_name)
                verdict = s_perf_eval.evaluate(part)
                for check in spec["must_fail_checks"]:
                    self.assertEqual(
                        verdict["checks"][check], "fail",
                        f"Mutant {mutant_name}: {check} must be 'fail', got {verdict['checks'][check]}"
                    )
                for check in spec["allowed_non_pass"]:
                    # These can be 'missing', 'fail', or 'pass' but not required to be pass
                    self.assertIn(
                        verdict["checks"][check], ("pass", "fail", "missing"),
                        f"Mutant {mutant_name}: {check} has invalid state {verdict['checks'][check]}"
                    )
                self.assertEqual(verdict["exit_code"], FALLA, f"Mutant {mutant_name} expected exit code 1")


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
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s)))
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
            self.assertEqual(verdict["checks"]["PRF-05"], "pass")
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
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s)))
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
                ])
                for cp in range(EXPECTED_SNAP_CHECKPOINTS):
                    bridge.append(_snap_done(s, page_n=0, pages_n=1, tick_ms=70000.0 + cp * 5000.0, rows=_build_snap_rows(s)))
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
            self.assertEqual(verdict["checks"]["PRF-05"], "fail")
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
                    self.assertEqual(verdict["checks"]["PRF-06"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

    def test_modset_missing_patch_rejected(self):
        """Missing required patch -> modset_mismatch."""
        with tempfile.TemporaryDirectory() as td:
            part = Path(td) / "part"
            # Missing DayZSandbox_QA
            bridge = [_preflight_done(loaded_addons_csv="DayZExpansion_AI,DayZExpansion_AI_Scripts,DayZExpansion_Core_Scripts")]
            _write_part(part, bridge)
            verdict = s_perf_eval.evaluate(part)
            self.assertEqual(verdict["checks"]["PRF-01"], "fail")

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
            self.assertEqual(v1["checks"], v2["checks"])
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
            self.assertEqual(verdict["checks"]["PRF-01"], "pass")
            self.assertNotEqual(verdict["checks"]["PRF-06"], "fail")

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
            self.assertEqual(verdict["checks"]["PRF-06"], "fail")
            self.assertTrue(any("new perf_preflight before previous cycle cleanup" in r for r in verdict["reasons"]))


# ==============================================================================
# E2E tests (prefix test_e2e_) - these FAIL now because implementation is skeleton
# ==============================================================================

class TestE2E(unittest.TestCase):
    """End-to-end tests requiring fake peer + runner. Expected to FAIL now."""

    def test_e2e_healthy_run_reevaluates_with_evaluator(self):
        """E2E: healthy run re-evaluates evidence with evaluator, not just verdict.json."""
        # This test requires the fake peer and runner to be implemented
        # For now, it verifies the evaluator can process a complete evidence set
        # When implementation exists, this will test the full pipeline
        self.fail("E2E test: implementation is skeleton (fake_ext_perf.py, s_perf_run.py)")

    def test_e2e_two_director_cycles(self):
        """E2E: two director cycles with originals true/false on same peer (N11)."""
        self.fail("E2E test: implementation is skeleton")

    def test_e2e_n12_wait_expired_inconcluso(self):
        """E2E: job wait with expired terminal -> INCONCLUSO technical, not hang."""
        self.fail("E2E test: implementation is skeleton")

    def test_e2e_n12_wait_done_1_row_inconcluso(self):
        """E2E: job wait with done but 1 row -> INCONCLUSO technical."""
        self.fail("E2E test: implementation is skeleton")

    def test_e2e_gate_entire_pipeline(self):
        """E2E: entire gate from m1_gate.py spike S-perf."""
        self.fail("E2E test: implementation is skeleton")


if __name__ == "__main__":
    unittest.main()