"""Pure blind evaluator for spike S-perf (F0.3 server scene budget and window sampling).

This module is the executable specification of the evidence contract for S-perf.
It inspects ONLY ``part_dir / "samples"`` and the canonical versioned modset
fixture ``qa/fixtures/s_perf_modset.json``. It never reads ``manifest.json``
fields bound to fault injection or any harness metadata outside ``samples/``.

===============================================================================
EXPECTED ``samples/`` SCHEMA AND ENFORCE API PROVENANCE
===============================================================================

1. ``samples/bridge.jsonl`` (required)
   One JSON object per bridge operation in chronological order. Each record has:
   - ``op_id`` (str): opaque unique identifier ``<nonce16>-<n>``. The evaluator
     joins enqueue/deliver with ack/result by ``op_id`` and is invariant to any
     bijective renaming of ``op_id``.
   - ``verb`` (str): one of the S-perf verbs (``perf_preflight``,
     ``perf_step_apply``, ``perf_window_start``, ``perf_snap``,
     ``perf_budget_check``), common job verbs (``job_read``, ``job_stop``,
     ``job_free``), or S3 actor adapter verbs (``act_*``).
   - ``peer`` / ``target_inst`` (str): ``"server"`` or ``"client"``.
   - ``issued_ms`` (int/float): harness monotonic timestamp (``h_ms``) when the
     command was written to the outbox.
   - ``ack_ms`` (int/float): harness monotonic timestamp when the ACK arrived.
   - ``read_ms`` (int/float): harness monotonic timestamp when the result was read.
   - ``ack`` (dict): ``{"status": "ok"|"rejected"|"error", "reason": str, ...}``.
   - ``read`` (dict): envelope with ``status`` (``"done"|"rejected"|"error"``),
     ``reason`` (str), ``has`` (``["payload"]`` on ``"done"``, ``[]`` on
     ``"rejected"`` or ``"error"``), and wire payload fields (``sk``, ``sv``,
     ``nk``, ``nv``, ``ncol``, ``ncell``, ``scol``, ``scell``, ``rows``) or
     unpacked ``payload`` (``{"str": {}, "num": {}, "rows": [...]}``).
   - ``args`` / ``payload_req`` (dict): wire or unpacked request arguments.
   - ``pages`` (optional list[dict]): for paged operations (``job_read`` drained
     via ``read_job_pages`` or multi-page ``perf_snap``), each page's unpacked
     or wire payload, or combined ``rows`` (list[dict]).

2. Verb Payloads and Enforce API Provenance

   A) ``perf_preflight`` (instant, ``target_inst="server"``)
      Request ``args``:
      - ``str``: ``expected_world`` (``"chernarusplus"``),
        ``required_classes_csv``, optional ``expected_modset_sig``,
        ``expected_addons_csv``.
      - ``num``: ``center_x_m`` (7500.0), ``center_z_m`` (7500.0),
        ``clear_radius_m`` (65.0), ``fix_weather_b`` (1).
      Result ``read`` on ``done`` (``has == ["payload"]``):
      - ``str``:
        * ``world_name``: ``g_Game.GetWorldName()`` [P:\\scripts\\3_game\\global\\game.c:934]
        * ``loaded_addons_csv``: sorted comma-separated non-``DZ_*`` patches from
          ``g_Game.ConfigGetChildrenCount("CfgPatches")`` /
          ``g_Game.ConfigGetChildName("CfgPatches", i)`` [game.c:594,611]
        * ``modset_sig``: ``"world=<w>;addons=<csv>;patches_n=<n>"``
      - ``num``:
        * ``is_server_b``: ``1`` if ``g_Game.IsDedicatedServer() || g_Game.IsServer()``
        * ``players_n``: count from ``g_Game.GetPlayers(players)``
        * ``cfg_patches_total_n``: required patches count (6)
        * ``center_y_m``: ``g_Game.SurfaceY(7500.0, 7500.0)``
        * ``director_x_m``, ``director_z_m``: ``director.GetPosition()`` (7500.0, 7495.0)
        * ``director_orig_allow_damage_b``: ``director.GetAllowDamage()`` [object.c:1191]
          captured at the start of the cycle before setting ``SetAllowDamage(false)``
        * ``director_allow_damage_b``: ``director.GetAllowDamage()`` after lock (0)
        * ``overcast``, ``rain``, ``fog``: ``GetGame().GetWeather().GetOvercast().GetActual()``
          etc. [weather.c:38-49] after freezing weather at 0.0 and setting date
          ``GetGame().GetWorld().SetDate(2026, 6, 15, 12, 0)``
        * ``census_dynamic_n``, ``census_foreign_n``: independent sphere query via
          ``g_Game.GetObjectsAtPosition3D("7500 300 7500", 65.0, objects, proxyCargos)``
          [game.c:930] excluding the director and the director's inventory
        * ``tick_ms``: ``g_Game.GetTickTime() * 1000.0`` [game.c:914]
        * ``frame``: server tick frame counter incremented in ``OnTick(float)``
        * ``avg_fps_now``: ``g_Game.GetAvgFPS(64)`` [game.c:880]

   B) ``perf_step_apply`` (instant, ``target_inst="server"``)
      Request ``args``:
      - ``str``: ``step_id`` (``"base"|"fixture"|"inc1"|"inc2"|"cleanup"``)
      - ``num``: ``objects_n``, ``infected_n``, ``animals_n``, ``actors_n``,
        ``wardrobe_per_actor_n`` (5), ``center_x_m`` (7500.0),
        ``center_z_m`` (7500.0), ``roam_radius_m`` (6.0).
      Result ``read`` on ``done`` (``has == ["payload"]``):
      - ``str``: ``step_id``, ``modset_sig``,
        ``cleanup_status`` (``"clean"`` or ``"partial_foreign_content"``)
      - ``num``:
        * ``objects_n``, ``infected_n``, ``animals_n``, ``actors_n``,
          ``wardrobe_per_actor_n`` (requested counts)
        * ``objects_alive_n``, ``infected_alive_n``, ``animals_alive_n``,
          ``actors_alive_n`` (verified live handles via ``EntityAI.Cast``,
          ``!IsDamageDestroyed()``, ``!IsSetForDeletion()``)
        * ``roots_alive_n``, ``children_alive_n``, ``entities_alive_n``
        * ``deleted_prev_roots_n``, ``deleted_prev_children_n``
        * ``skipped_foreign_containers_n``, ``preserved_ancestors_n``
        * ``spawn_flags_obj_n`` (``12583972``), ``spawn_flags_ai_n`` (``12586020``)
          passed to ``g_Game.CreateObjectEx(cls, pos, flags)`` [game.c:703]
        * ``director_orig_allow_damage_b``, ``director_allow_damage_b``
        * ``apply_cost_ms``, ``tick_ms``, ``frame``

   C) ``perf_window_start`` (job on resource ``"perf_sampler"``) & ``job_read``
      Request ``args``:
      - ``str``: ``step_id``, ``expected_modset_sig``
      - ``num``: ``warmup_ms`` (30000), ``duration_ms`` (60000),
        ``sample_step_ms`` (1000).
      Start ACK ``read`` on ``done``:
      - ``str``: ``job``, ``state`` (``"running"``), ``resource`` (``"perf_sampler"``),
        ``step_id``, ``modset_sig``
      - ``num``: ``start_tick_ms``, ``start_frame``, ``warmup_ms``,
        ``duration_ms``, ``sample_step_ms``, ``expected_rows_n`` (61).
      Terminal ``job_read`` scalars:
      - ``str``: ``job``, ``state`` (``"done"|"stopped"|"failed"|"expired"``),
        ``reason``
      - ``num``: ``rows_total_n``, ``pages_n``, ``page_n``, ``end_tick_ms``,
        ``onjobend_tick_ms``, ``released_tick_ms``.
      1 Hz table columns (``ncol``, 13 numeric columns, ``scol = []``):
      - ``seq_n``: sample index ``0..60``
      - ``frame``: server frame counter at sample emission
      - ``tick_ms``: ``g_Game.GetTickTime() * 1000.0`` (ms)
      - ``dtsum_ms``: cumulative ``timeslice * 1000.0`` sum in ``OnTick`` (ms)
      - ``avg_fps``: ``g_Game.GetAvgFPS(64)`` (fps)
      - ``alive_roots_n``: live root entities verified by handle iteration
      - ``alive_wardrobe_n``: live wardrobe attachments verified in actor inventories
        via ``actor.GetInventory().HasEntityInInventory(item)`` [inventory.c:118]
      - ``roam_disp_step_m``: mean/total horizontal displacement (m) of roam actors
        during that 1 s interval
      - ``roam_min_step_m``: minimum horizontal displacement (m) across all roam
        actors during that 1 s interval (must be >= ``ROAM_MIN_STEP_M = 0.05`` m
        for ``seq_n >= 1`` when roam actors are present)
      - ``emote_active_actors_n``: count of odd-indexed emote actors with
        ``GetEmoteManager().m_bEmoteIsPlaying == true`` [emotemanager.c:127]
      - ``emote_cb_cmd1101_actors_n``: count of emote actors whose
        ``m_Callback != null && m_Callback.m_callbackID == 1101 && m_Callback.GetState() > 0``
        [emotemanager.c:4,120; human.c:383]
      - ``creatures_moved_step_n``: count of creatures (infected + animals) that
        moved during that 1 s interval
      - ``creatures_min_step_m``: minimum horizontal displacement (m) across all
        creatures during that 1 s interval (must be >= ``CREATURES_MIN_STEP_M = 0.01`` m
        for ``seq_n >= 1`` when creatures are present)

   D) ``perf_snap`` (paged instant, 15 rows/page)
      Request ``args``:
      - ``str``: ``step_id``
      - ``num``: ``page_n`` (0..pages_n-1), ``inject_foreign_cargo_b`` (0, or 1 in N6).
      Result ``read`` on ``done``:
      - ``str``: ``step_id``, ``modset_sig``
      - ``num``: ``page_n``, ``pages_n``, ``objects_alive_n``, ``infected_alive_n``,
        ``animals_alive_n``, ``actors_alive_n``, ``roots_alive_n``,
        ``children_alive_n``, ``entities_alive_n``, ``census_dynamic_n``,
        ``census_foreign_n``, ``director_orig_allow_damage_b``,
        ``director_allow_damage_b``, ``foreign_injected_b``, ``tick_ms``,
        ``frame``, ``avg_fps_now``.
      Row columns (``ncol``, 18 numeric columns, ``scol = []``):
      - ``entity_idx_n``: deterministic index within the step
      - ``kind_code_n``: ``1`` = object (``SeaChest``), ``2`` = infected,
        ``3`` = animal, ``4`` = actor
      - ``role_code_n``: ``0`` = static object, ``1`` = roam actor,
        ``2`` = emote actor, ``3`` = creature sway
      - ``alive_b``: ``1`` if alive and valid
      - ``wardrobe_n``: count of live equipped garments on actor (``5`` in step,
        ``1`` on preserved actor after N6 partial cleanup)
      - ``ai_agent_b``: ``1`` if creature/actor AI agent is active
      - ``pos_x_m``, ``pos_y_m``, ``pos_z_m``: world coordinates from ``GetPosition()``
      - ``cum_disp_m``: cumulative horizontal displacement (m)
      - ``wp_legs_n``: completed patrol legs count for roam actors
      - ``emote_playing_b``: ``1`` if ``m_bEmoteIsPlaying``
      - ``emote_pending_b``: ``1`` if ``m_bEmoteIsRequestPending``
      - ``emote_cb_id_n``: ``m_Callback.m_callbackID`` (``1101`` when clap active)
      - ``emote_cb_state_n``: ``m_Callback.GetState()`` (``> 0`` when active)
      - ``emote_active_ticks_n``: cumulative ticks with active 1101 emote callback
      - ``emote_completions_n``: completed clap gesture cycles
      - ``foreign_content_b``: ``1`` if recursive inventory inspection finds any
        unregistered item inside this entity or its descendants

   E) ``perf_budget_check`` (instant A6 guard, 0 spawns)
      Request ``args``:
      - ``str``: ``expected_modset_sig``
      - ``num``: ``max_objects_n``, ``max_infected_n``, ``max_animals_n``,
        ``max_actors_n``, ``max_wardrobe_per_actor_n``, ``max_children_n``,
        ``max_combined_roots_n``, ``max_combined_entities_n``,
        ``cand_objects_n``, ``cand_infected_n``, ``cand_animals_n``,
        ``cand_actors_n``, ``cand_wardrobe_total_n``,
        ``cand_wardrobe_max_per_actor_n``, ``cand_extra_children_n``.
      Result ``read``:
      - On ``done`` (all 7 guards satisfied): ``has == ["payload"]``,
        ``str``: ``budget_status="accepted"``, ``violation_path=""``;
        ``num``: ``cand_roots_n``, ``cand_children_n``, ``cand_entities_n``,
        ``headroom_roots_n``, ``headroom_entities_n``, ``spawned_orders_n`` (0).
      - On ``rejected``: ``has == []`` and ``reason`` in
        ``{"modset_mismatch", "budget_exceeded:objects",
        "budget_exceeded:infected", "budget_exceeded:animals",
        "budget_exceeded:actors", "budget_exceeded:wardrobe_per_actor",
        "budget_exceeded:children_total", "budget_exceeded:combined_roots",
        "budget_exceeded:combined_entities"}``.

3. Optional supplementary files in ``samples/``
   - ``samples/step_<step>_polls.jsonl``: per-poll harness timestamps ``h_ms`` and
     terminal ``job_read`` marks (``end_tick_ms``, ``onjobend_tick_ms``,
     ``released_tick_ms``).
   - ``samples/final_snap.json``: unpacked final ``perf_snap`` after bench closure.
   - ``samples/technical.json``: technical blocker report written by the runner on
     transport ``timeout``/``lost``, non-``done`` job termination
     (``stopped``/``failed``/``expired``), ``cleanup_incomplete``, or
     ``actor_driver_unavailable``. Causes affected checks to stay ``"missing"``
     and the part verdict to exit ``2 INCONCLUSO``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import f03_common
import gate_core
import wire

SPIKE_ID = "S-perf"
CHECK_IDS = ("PRF-01", "PRF-02", "PRF-03", "PRF-04", "PRF-05", "PRF-06")

DEFAULT_MODSET_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "s_perf_modset.json"
)

# Geometry constants (S-perf brief §2.2.2)
CENTER_POS = (7500.0, 300.0, 7500.0)
DIRECTOR_POS = (7500.0, 300.0, 7495.0)
CLEAR_RADIUS_M = 65.0
MAX_DIRECTOR_DIST_M = 60.0
MIN_GROUP_SEP_M = 10.0
ROAM_SQUARE_RADIUS_M = 6.0
CREATURE_SWAY_RADIUS_M = 1.5
MIN_ACTOR_NEIGHBOR_SEP_M = 3.0

# Spawn flags (S-perf brief §2.1.2, #11)
SPAWN_FLAGS_OBJ = 12583972
SPAWN_FLAGS_AI = 12586020
FORBIDDEN_SPAWN_FLAG = 33554432

# Emote constants (S-perf brief §2.1.2)
EMOTE_CLAP_ID = 39
EMOTE_CB_CMD_CLAP = 1101

# Approved floor metric (#28, Q9) and window parameters (S-perf brief §2.1, §5)
FLOOR_FPS = 35.0
WARMUP_MIN_MS = 30000.0
WINDOW_MIN_MS = 60000.0
WINDOW_MAX_MS = 65000.0
EXPECTED_WINDOW_ROWS = 61
SAMPLE_STEP_MS = 1000.0
SAMPLE_DT_MIN_MS = 500.0
SAMPLE_DT_MAX_MS = 1500.0
FPS_REL_TOL = 0.10
DTSUM_DRIFT_TOL = 0.02
HARNESS_DRIFT_TOL = 0.05

# Continuous activity thresholds (S-perf brief §5, §11, Arbitraje N3 & N5)
ROAM_MIN_STEP_M = 0.05
CREATURES_MIN_STEP_M = 0.01
ROAM_QUARTER_MIN_M = 2.0
ROAM_TOTAL_MIN_M = 15.0
ROAM_SUBSTEP_MIN_M = 0.15
ROAM_MIN_WP_LEGS = 2
CREATURES_QUARTER_MIN_M = 0.25
CREATURES_TOTAL_MIN_M = 1.5
EMOTE_QUARTER_MIN_COMPLETIONS = 1
EMOTE_TOTAL_MIN_COMPLETIONS = 4
EXPECTED_SNAP_CHECKPOINTS = 13

STEP_ORDER = ("base", "fixture", "inc1", "inc2")
STEP_ALIASES = {
    "0x": "base",
    "base": "base",
    "1x": "fixture",
    "fixture": "fixture",
    "2x": "inc1",
    "inc1": "inc1",
    "3x": "inc2",
    "inc2": "inc2",
    "cleanup": "cleanup",
}

STEP_SPEC: dict[str, dict[str, int]] = {
    "base": {
        "k": 0,
        "objects_n": 0,
        "infected_n": 0,
        "animals_n": 0,
        "actors_n": 0,
        "wardrobe_per_actor_n": 0,
        "roots_n": 0,
        "children_n": 0,
        "entities_n": 0,
    },
    "fixture": {
        "k": 1,
        "objects_n": 20,
        "infected_n": 10,
        "animals_n": 3,
        "actors_n": 2,
        "wardrobe_per_actor_n": 5,
        "roots_n": 35,
        "children_n": 10,
        "entities_n": 45,
    },
    "inc1": {
        "k": 2,
        "objects_n": 30,
        "infected_n": 15,
        "animals_n": 5,
        "actors_n": 3,
        "wardrobe_per_actor_n": 5,
        "roots_n": 53,
        "children_n": 15,
        "entities_n": 68,
    },
    "inc2": {
        "k": 3,
        "objects_n": 40,
        "infected_n": 20,
        "animals_n": 6,
        "actors_n": 4,
        "wardrobe_per_actor_n": 5,
        "roots_n": 70,
        "children_n": 20,
        "entities_n": 90,
    },
}

WINDOW_NCOL = (
    "seq_n",
    "frame",
    "tick_ms",
    "dtsum_ms",
    "avg_fps",
    "alive_roots_n",
    "alive_wardrobe_n",
    "roam_disp_step_m",
    "roam_min_step_m",
    "emote_active_actors_n",
    "emote_cb_cmd1101_actors_n",
    "creatures_moved_step_n",
    "creatures_min_step_m",
)

SNAP_NCOL = (
    "entity_idx_n",
    "kind_code_n",
    "role_code_n",
    "alive_b",
    "wardrobe_n",
    "ai_agent_b",
    "pos_x_m",
    "pos_y_m",
    "pos_z_m",
    "cum_disp_m",
    "wp_legs_n",
    "emote_playing_b",
    "emote_pending_b",
    "emote_cb_id_n",
    "emote_cb_state_n",
    "emote_active_ticks_n",
    "emote_completions_n",
    "foreign_content_b",
)

PERF_VERBS = {
    "perf_preflight",
    "perf_step_apply",
    "perf_window_start",
    "perf_snap",
    "perf_budget_check",
}

COMMON_VERBS = {
    "job_read",
    "job_stop",
    "job_free",
    "poll_job",
    "stop_job",
    "hello",
    "noop",
    "ping",
}

N5_REQUIRED_REASONS = (
    "budget_exceeded:objects",
    "budget_exceeded:infected",
    "budget_exceeded:animals",
    "budget_exceeded:actors",
    "budget_exceeded:wardrobe_per_actor",
    "budget_exceeded:children_total",
    "budget_exceeded:combined_roots",
    "budget_exceeded:combined_entities",
)


# ---------------------------------------------------------------------------
# Geometry functions (S-perf brief §2.2.2)
# ---------------------------------------------------------------------------


def spawn_pos_object(idx: int, y: float = 300.0) -> tuple[float, float, float]:
    """Return (x, y, z) for SeaChest object ``idx`` (0..39)."""
    x = 7470.0 + (idx % 10) * 2.5
    z = 7525.0 + (idx // 10) * 2.5
    return (x, float(y), z)


def spawn_pos_infected(idx: int, y: float = 300.0) -> tuple[float, float, float]:
    """Return (x, y, z) base spawn for infected ``idx`` (0..19)."""
    x = 7520.0 + (idx % 5) * 4.0
    z = 7525.0 + (idx // 5) * 4.0
    return (x, float(y), z)


def spawn_pos_animal(idx: int, y: float = 300.0) -> tuple[float, float, float]:
    """Return (x, y, z) base spawn for animal ``idx`` (0..5)."""
    x = 7465.0 + (idx % 5) * 4.0
    z = 7460.0 + (idx // 5) * 4.0
    return (x, float(y), z)


def spawn_pos_actor(idx: int, y: float = 300.0) -> tuple[float, float, float]:
    """Return (x, y, z) base spawn for actor ``idx`` (0..3) on the 2x2 grid."""
    ax = 7508.0 + (idx % 2) * 15.0
    az = 7470.0 - (idx // 2) * 15.0
    return (ax, float(y), az)


def _dist_xz(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def _point_to_box_dist_xz(
    pt: tuple[float, float],
    box_min_x: float,
    box_max_x: float,
    box_min_z: float,
    box_max_z: float,
) -> float:
    dx = max(box_min_x - pt[0], 0.0, pt[0] - box_max_x)
    dz = max(box_min_z - pt[1], 0.0, pt[1] - box_max_z)
    return math.hypot(dx, dz)


def _box_to_box_dist_xz(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    dx = max(a[0] - b[1], 0.0, b[0] - a[1])
    dz = max(a[2] - b[3], 0.0, b[2] - a[3])
    return math.hypot(dx, dz)


def verify_geometry_spec(k: int = 3) -> dict[str, Any]:
    """Verify §2.2.2 geometry separations and director distance for step index ``k``."""
    step_name = {0: "base", 1: "fixture", 2: "inc1", 3: "inc2"}.get(k, "inc2")
    spec = STEP_SPEC[step_name]
    dir_xz = (DIRECTOR_POS[0], DIRECTOR_POS[2])
    cen_xz = (CENTER_POS[0], CENTER_POS[2])

    obj_boxes: list[tuple[float, float, float, float]] = []
    inf_boxes: list[tuple[float, float, float, float]] = []
    ani_boxes: list[tuple[float, float, float, float]] = []
    act_boxes: list[tuple[float, float, float, float]] = []
    all_Check_pts: list[tuple[float, float]] = []

    for i in range(spec["objects_n"]):
        x, _, z = spawn_pos_object(i)
        obj_boxes.append((x, x, z, z))
        all_Check_pts.append((x, z))

    for i in range(spec["infected_n"]):
        x, _, z = spawn_pos_infected(i)
        r = CREATURE_SWAY_RADIUS_M
        inf_boxes.append((x - r, x + r, z, z))
        all_Check_pts.extend([(x - r, z), (x + r, z)])

    for i in range(spec["animals_n"]):
        x, _, z = spawn_pos_animal(i)
        r = CREATURE_SWAY_RADIUS_M
        ani_boxes.append((x - r, x + r, z, z))
        all_Check_pts.extend([(x - r, z), (x + r, z)])

    for a in range(spec["actors_n"]):
        ax, _, az = spawn_pos_actor(a)
        r = ROAM_SQUARE_RADIUS_M if (a % 2 == 0) else 0.0
        act_boxes.append((ax - r, ax + r, az - r, az + r))
        for vx in (ax - r, ax + r):
            for vz in (az - r, az + r):
                all_Check_pts.append((vx, vz))

    max_director_dist = max(
        (_dist_xz(pt, dir_xz) for pt in all_Check_pts),
        default=0.0,
    )
    max_center_dist = max(
        (_dist_xz(pt, cen_xz) for pt in all_Check_pts),
        default=0.0,
    )

    groups = {
        "objects": obj_boxes,
        "infected": inf_boxes,
        "animals": ani_boxes,
        "actors": act_boxes,
    }
    group_names = ("objects", "infected", "animals", "actors")
    pair_dists: dict[str, float] = {}
    min_inter_group = float("inf")
    for idx_a, ga in enumerate(group_names):
        for gb in group_names[idx_a + 1 :]:
            boxes_a = groups[ga]
            boxes_b = groups[gb]
            if not boxes_a or not boxes_b:
                continue
            d = min(_box_to_box_dist_xz(ba, bb) for ba in boxes_a for bb in boxes_b)
            pair_dists[f"{ga}_{gb}"] = round(d, 4)
            if d < min_inter_group:
                min_inter_group = d

    if min_inter_group == float("inf"):
        min_inter_group = 0.0

    # Neighbor actor square distance across the full 2x2 grid assuming 6.0 m radius squares
    full_actor_squares = []
    for a in range(4):
        ax, _, az = spawn_pos_actor(a)
        r = ROAM_SQUARE_RADIUS_M
        full_actor_squares.append((ax - r, ax + r, az - r, az + r))
    min_actor_sep = min(
        _box_to_box_dist_xz(full_actor_squares[i], full_actor_squares[j])
        for i in range(len(full_actor_squares))
        for j in range(i + 1, len(full_actor_squares))
    )

    valid = (
        max_director_dist < MAX_DIRECTOR_DIST_M
        and max_center_dist <= CLEAR_RADIUS_M
        and (min_inter_group >= MIN_GROUP_SEP_M if all_Check_pts else True)
        and min_actor_sep >= MIN_ACTOR_NEIGHBOR_SEP_M
    )
    return {
        "valid": valid,
        "k": k,
        "step_id": step_name,
        "max_director_dist_m": round(max_director_dist, 4),
        "max_center_dist_m": round(max_center_dist, 4),
        "min_inter_group_dist_m": round(min_inter_group, 4),
        "min_actor_square_sep_m": round(min_actor_sep, 4),
        "group_pair_min_dist_m": pair_dists,
    }


# ---------------------------------------------------------------------------
# Payload and JSONL helpers
# ---------------------------------------------------------------------------


def _is_finite_number(val: Any) -> bool:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return False
    return math.isfinite(float(val))


def _unpack_any_payload(obj: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Unpack either a wire payload or an already-unpacked payload dict."""
    if not isinstance(obj, dict):
        return None, "payload_not_dict"
    if "str" in obj and "num" in obj and isinstance(obj["str"], dict) and isinstance(obj["num"], dict):
        for k, v in obj["str"].items():
            if not isinstance(k, str) or not isinstance(v, str):
                return None, "invalid_str_entry"
        for k, v in obj["num"].items():
            if not isinstance(k, str) or not _is_finite_number(v):
                return None, "non_finite_num_entry"
        rows = obj.get("rows", [])
        if isinstance(rows, int):
            rows = []
        if not isinstance(rows, list):
            return None, "invalid_rows_list"
        for r in rows:
            if not isinstance(r, dict):
                return None, "row_not_dict"
            for rk, rv in r.items():
                if isinstance(rv, str):
                    continue
                if not _is_finite_number(rv):
                    return None, f"non_finite_row_val:{rk}"
        return {
            "str": dict(obj["str"]),
            "num": dict(obj["num"]),
            "ncol": list(obj.get("ncol", [])),
            "scol": list(obj.get("scol", [])),
            "rows": list(rows),
        }, None

    if all(k in obj for k in wire.PAYLOAD_KEYS):
        try:
            unpacked = wire.unpack_payload(obj)
            return unpacked, None
        except Exception as exc:
            return None, f"wire_unpack_error:{exc}"

    return None, "unrecognized_payload_shape"


def _extract_request_payload(rec: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    for key in ("args", "payload_req", "req_payload", "payload"):
        cand = rec.get(key)
        if isinstance(cand, dict):
            if all(k in cand for k in wire.PAYLOAD_KEYS):
                try:
                    wire.check_arg_strings(cand)
                except Exception as exc:
                    return {"str": {}, "num": {}, "rows": []}, f"arg_strings:{exc}"
            unpacked, err = _unpack_any_payload(cand)
            if err is not None:
                return {"str": {}, "num": {}, "rows": []}, err
            for sv in unpacked["str"].values():
                if len(sv) > wire.MAX_ARG_STR_CHARS:
                    return {"str": {}, "num": {}, "rows": []}, "arg_str_exceeds_max"
            return unpacked, None
    return {"str": {}, "num": {}, "rows": []}, None


def _extract_result_envelope(rec: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Validate and extract result status, reason, has, and unpacked payload."""
    read = rec.get("read")
    ack = rec.get("ack")
    if not isinstance(ack, dict) or not isinstance(ack.get("status"), str):
        return None, "missing_or_invalid_ack"
    if not isinstance(read, dict) or not isinstance(read.get("status"), str):
        return None, "missing_or_invalid_read"

    status = read["status"]
    reason = read.get("reason", "")
    if not isinstance(reason, str):
        return None, "reason_not_str"

    if status not in ("done", "rejected", "error", "timeout", "lost"):
        return None, f"invalid_read_status:{status}"

    has = read.get("has")
    if status == "done":
        if has is not None and has != ["payload"]:
            return None, f"done_invalid_has:{has}"
    elif status in ("rejected", "error"):
        if has is not None and has != []:
            return None, f"non_done_non_empty_has:{has}"

    # Extract payload for done results
    payload_src = None
    if "payload_res" in rec and isinstance(rec["payload_res"], dict):
        payload_src = rec["payload_res"]
    elif "payload" in read and isinstance(read["payload"], dict):
        payload_src = read["payload"]
    elif all(k in read for k in wire.PAYLOAD_KEYS):
        payload_src = {k: read[k] for k in wire.PAYLOAD_KEYS}
    elif "str" in read and "num" in read:
        payload_src = read

    if status == "done":
        if payload_src is None:
            return None, "done_missing_payload"
        unpacked, err = _unpack_any_payload(payload_src)
        if err is not None or unpacked is None:
            return None, f"done_bad_payload:{err}"
        # Merge multi-page rows if present on the record
        extra_rows: list[dict[str, Any]] = []
        if isinstance(rec.get("pages"), list) and rec["pages"]:
            for pg in rec["pages"]:
                pg_unpacked, pg_err = _unpack_any_payload(pg)
                if pg_err is not None or pg_unpacked is None:
                    return None, f"page_bad_payload:{pg_err}"
                extra_rows.extend(pg_unpacked["rows"])
        elif isinstance(rec.get("rows"), list):
            for r in rec["rows"]:
                if not isinstance(r, dict):
                    return None, "rec_row_not_dict"
                for rk, rv in r.items():
                    if not isinstance(rv, str) and not _is_finite_number(rv):
                        return None, f"rec_row_non_finite:{rk}"
                extra_rows.append(r)
        if extra_rows:
            unpacked = dict(unpacked)
            unpacked["rows"] = extra_rows
    else:
        # On rejected/error, wire payload if present must be empty
        if all(k in read for k in wire.PAYLOAD_KEYS):
            for k in ("sk", "sv", "nk", "nv", "ncol", "ncell", "scol", "scell"):
                if read.get(k) != []:
                    return None, f"rejected_non_empty_wire_field:{k}"
            if read.get("rows", 0) != 0:
                return None, "rejected_non_zero_rows"
        unpacked = {"str": {}, "num": {}, "ncol": [], "scol": [], "rows": []}

    return {
        "status": status,
        "reason": reason,
        "ack_status": ack["status"],
        "ack_reason": ack.get("reason", ""),
        "payload": unpacked,
    }, None


def _normalize_step_id(raw_step: str) -> str:
    return STEP_ALIASES.get(raw_step.strip(), raw_step.strip())


def _load_modset_fixture(fixture_path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    path = fixture_path or DEFAULT_MODSET_FIXTURE
    if not path.is_file():
        return None, f"modset_fixture_missing:{path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"modset_fixture_invalid_json:{exc}"
    if not isinstance(data, dict):
        return None, "modset_fixture_not_object"
    for req_key in ("world", "loaded_addons_csv", "patches_n", "modset_sig"):
        if req_key not in data:
            return None, f"modset_fixture_missing_key:{req_key}"
    return data, None


def _compute_roll5_min(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    vals = [float(r["avg_fps"]) for r in rows]
    if len(vals) < 5:
        return min(vals)
    return min(sum(vals[i : i + 5]) / 5.0 for i in range(len(vals) - 4))


def _check_budget_violation_path(req_num: dict[str, Any]) -> str | None:
    """Return the first A6 guard violated by a perf_budget_check request, or None."""
    max_obj = int(req_num.get("max_objects_n", 0))
    max_inf = int(req_num.get("max_infected_n", 0))
    max_ani = int(req_num.get("max_animals_n", 0))
    max_act = int(req_num.get("max_actors_n", 0))
    max_w_per_act = int(req_num.get("max_wardrobe_per_actor_n", 5))
    max_children = int(req_num.get("max_children_n", 0))
    max_roots = int(req_num.get("max_combined_roots_n", 0))
    max_entities = int(req_num.get("max_combined_entities_n", 0))

    cand_obj = int(req_num.get("cand_objects_n", 0))
    cand_inf = int(req_num.get("cand_infected_n", 0))
    cand_ani = int(req_num.get("cand_animals_n", 0))
    cand_act = int(req_num.get("cand_actors_n", 0))
    cand_w_tot = int(req_num.get("cand_wardrobe_total_n", 0))
    cand_w_max = int(req_num.get("cand_wardrobe_max_per_actor_n", 0))
    cand_extra_ch = int(req_num.get("cand_extra_children_n", 0))

    cand_roots = cand_obj + cand_inf + cand_ani + cand_act
    cand_children = cand_w_tot + cand_extra_ch
    cand_entities = cand_roots + cand_children

    if cand_obj > max_obj:
        return "budget_exceeded:objects"
    if cand_inf > max_inf:
        return "budget_exceeded:infected"
    if cand_ani > max_ani:
        return "budget_exceeded:animals"
    if cand_act > max_act:
        return "budget_exceeded:actors"
    if cand_w_max > max_w_per_act:
        return "budget_exceeded:wardrobe_per_actor"
    if cand_children > max_children:
        return "budget_exceeded:children_total"
    if cand_roots > max_roots:
        return "budget_exceeded:combined_roots"
    if cand_entities > max_entities:
        return "budget_exceeded:combined_entities"
    return None


# ---------------------------------------------------------------------------
# Main Evaluator Entry Point
# ---------------------------------------------------------------------------


def evaluate(
    part_dir: Path | str,
    *,
    repo_root: Path | str | None = None,
    modset_fixture_path: Path | str | None = None,
) -> dict[str, Any]:
    """Evaluate ``part_dir / "samples"`` for spike S-perf and return a verdict dict."""
    part_path = Path(part_dir)
    samples_dir = part_path / "samples"
    checks: dict[str, str] = {cid: "missing" for cid in CHECK_IDS}
    reasons: list[str] = []
    metrics: dict[str, Any] = {}

    fixture_path = Path(modset_fixture_path) if modset_fixture_path else DEFAULT_MODSET_FIXTURE
    modset_fixture, fixture_err = _load_modset_fixture(fixture_path)
    if fixture_err is not None or modset_fixture is None:
        reasons.append(fixture_err or "modset_fixture_unavailable")
        return gate_core.make_verdict(
            SPIKE_ID,
            gate_core.INCONCLUSO,
            checks=checks,
            metrics=metrics,
            reasons=reasons,
        )

    canonical_world = str(modset_fixture["world"])
    canonical_addons_csv = str(modset_fixture["loaded_addons_csv"])
    canonical_patches_n = int(modset_fixture["patches_n"])
    canonical_modset_sig = str(modset_fixture["modset_sig"])

    # Technical failure report (S-perf brief §4.2 N12, Arbitraje N2 & N4)
    tech_path = samples_dir / "technical.json"
    technical_data: dict[str, Any] | None = None
    if tech_path.is_file():
        try:
            raw_tech = json.loads(tech_path.read_text(encoding="utf-8"))
            if isinstance(raw_tech, dict):
                technical_data = raw_tech
        except Exception as exc:
            reasons.append(f"PRF-01: malformed technical.json ({exc})")
            checks["PRF-01"] = "fail"

    bridge_path = samples_dir / "bridge.jsonl"
    if not bridge_path.is_file():
        if technical_data is not None:
            reasons.append(f"technical:{technical_data.get('reason', 'blocker')}")
        else:
            reasons.append("samples/bridge.jsonl missing")
        return gate_core.make_verdict(
            SPIKE_ID,
            gate_core.INCONCLUSO,
            checks=checks,
            metrics=metrics,
            reasons=reasons,
        )

    try:
        raw_records = f03_common.read_jsonl(bridge_path)
    except Exception as exc:
        checks["PRF-01"] = "fail"
        reasons.append(f"PRF-01: invalid bridge.jsonl JSONL ({exc})")
        return gate_core.make_verdict(
            SPIKE_ID,
            gate_core.FALLA,
            checks=checks,
            metrics=metrics,
            reasons=reasons,
        )

    if not raw_records:
        if technical_data is not None:
            reasons.append(f"technical:{technical_data.get('reason', 'empty_bridge')}")
        else:
            reasons.append("samples/bridge.jsonl is empty")
        return gate_core.make_verdict(
            SPIKE_ID,
            gate_core.INCONCLUSO,
            checks=checks,
            metrics=metrics,
            reasons=reasons,
        )

    # Parse and anti-fabrication check on every bridge record (E9)
    seen_op_ids: set[str] = set()
    ops: list[dict[str, Any]] = []
    prf01_violations: list[str] = []
    prf02_violations: list[str] = []
    prf03_violations: list[str] = []
    prf04_violations: list[str] = []
    prf05_violations: list[str] = []
    prf06_violations: list[str] = []
    transport_failures: list[str] = []

    prev_server_issued_ms: float | None = None

    for idx, rec in enumerate(raw_records):
        if not isinstance(rec, dict):
            prf01_violations.append(f"record[{idx}] is not a JSON object")
            continue
        op_id = rec.get("op_id")
        if not isinstance(op_id, str) or not op_id.strip():
            prf01_violations.append(f"record[{idx}] missing valid op_id")
            continue
        if op_id in seen_op_ids:
            prf01_violations.append(f"duplicate op_id {op_id!r}")
            continue
        seen_op_ids.add(op_id)

        verb = rec.get("verb")
        if not isinstance(verb, str) or not verb:
            prf01_violations.append(f"op {op_id}: missing verb")
            continue
        is_act_verb = verb.startswith("act_")
        if verb not in PERF_VERBS and verb not in COMMON_VERBS and not is_act_verb:
            prf01_violations.append(f"op {op_id}: unknown verb {verb!r}")
            continue

        peer = str(rec.get("peer") or rec.get("target_inst") or "server")
        if peer not in ("server", "client"):
            prf01_violations.append(f"op {op_id}: invalid peer {peer!r}")
            continue

        issued_ms = rec.get("issued_ms")
        ack_ms = rec.get("ack_ms")
        read_ms = rec.get("read_ms")
        if (
            not _is_finite_number(issued_ms)
            or not _is_finite_number(ack_ms)
            or not _is_finite_number(read_ms)
        ):
            prf01_violations.append(f"op {op_id}: missing or non-finite timestamps")
            continue
        issued_f = float(issued_ms)
        ack_f = float(ack_ms)
        read_f = float(read_ms)
        if ack_f < issued_f or read_f < ack_f:
            prf01_violations.append(
                f"op {op_id}: non-monotonic timestamps (issued={issued_f}, ack={ack_f}, read={read_f})"
            )
            continue
        if peer == "server" and prev_server_issued_ms is not None and issued_f < prev_server_issued_ms:
            prf01_violations.append(
                f"op {op_id}: decreasing server issued_ms ({issued_f} < {prev_server_issued_ms})"
            )
        if peer == "server":
            prev_server_issued_ms = issued_f

        req_payload, req_err = _extract_request_payload(rec)
        if req_err is not None:
            prf01_violations.append(f"op {op_id}: invalid request payload ({req_err})")
            continue

        res_env, res_err = _extract_result_envelope(rec)
        if res_err is not None or res_env is None:
            prf01_violations.append(f"op {op_id}: invalid result envelope ({res_err})")
            continue

        if res_env["status"] in ("timeout", "lost"):
            transport_failures.append(f"op {op_id} ({verb}): {res_env['status']}")
            continue

        ops.append(
            {
                "idx": idx,
                "op_id": op_id,
                "verb": verb,
                "peer": peer,
                "issued_ms": issued_f,
                "ack_ms": ack_f,
                "read_ms": read_f,
                "req": req_payload,
                "status": res_env["status"],
                "reason": res_env["reason"],
                "ack_status": res_env["ack_status"],
                "payload": res_env["payload"],
                "raw": rec,
            }
        )

    # -----------------------------------------------------------------------
    # PRF-01: server_preflight_and_modset_lock
    # -----------------------------------------------------------------------
    preflight_done_ops: list[dict[str, Any]] = []
    preflight_rejected_ops: list[dict[str, Any]] = []

    for op in ops:
        verb = op["verb"]
        peer = op["peer"]
        status = op["status"]
        p_str = op["payload"]["str"]
        p_num = op["payload"]["num"]

        # Any perf_* operation completing as "done" on client is a hard PRF-01 violation (E5)
        if peer == "client" and verb in PERF_VERBS and status == "done":
            prf01_violations.append(
                f"op {op['op_id']}: {verb} completed as 'done' on client role"
            )

        if peer == "server" and verb == "perf_preflight":
            if status == "done":
                preflight_done_ops.append(op)
                world_name = p_str.get("world_name")
                addons_csv = p_str.get("loaded_addons_csv")
                modset_sig = p_str.get("modset_sig")
                patches_n = p_num.get("cfg_patches_total_n")
                is_srv = p_num.get("is_server_b")
                players_n = p_num.get("players_n")
                dir_allow = p_num.get("director_allow_damage_b")
                dir_orig = p_num.get("director_orig_allow_damage_b")
                census_dyn = p_num.get("census_dynamic_n")
                census_for = p_num.get("census_foreign_n", 0)
                overcast = p_num.get("overcast")
                rain = p_num.get("rain")
                fog = p_num.get("fog")

                # Check request args against canonical fixture if provided (Arbitraje N8)
                req_str = op["req"]["str"]
                if "expected_world" in req_str and req_str["expected_world"] != canonical_world:
                    prf01_violations.append(
                        f"op {op['op_id']}: preflight expected_world={req_str['expected_world']!r} != {canonical_world!r}"
                    )
                if (
                    "expected_modset_sig" in req_str
                    and req_str["expected_modset_sig"] != canonical_modset_sig
                ):
                    prf01_violations.append(
                        f"op {op['op_id']}: preflight expected_modset_sig={req_str['expected_modset_sig']!r} != canonical"
                    )
                if (
                    "expected_addons_csv" in req_str
                    and req_str["expected_addons_csv"] != canonical_addons_csv
                ):
                    prf01_violations.append(
                        f"op {op['op_id']}: preflight expected_addons_csv={req_str['expected_addons_csv']!r} != canonical"
                    )

                if is_srv != 1:
                    prf01_violations.append(f"op {op['op_id']}: is_server_b={is_srv} != 1")
                if world_name != canonical_world:
                    prf01_violations.append(
                        f"op {op['op_id']}: world_name={world_name!r} != {canonical_world!r}"
                    )
                if addons_csv != canonical_addons_csv:
                    prf01_violations.append(
                        f"op {op['op_id']}: loaded_addons_csv={addons_csv!r} != {canonical_addons_csv!r}"
                    )
                if patches_n != canonical_patches_n:
                    prf01_violations.append(
                        f"op {op['op_id']}: cfg_patches_total_n={patches_n} != {canonical_patches_n}"
                    )
                if modset_sig != canonical_modset_sig:
                    prf01_violations.append(
                        f"op {op['op_id']}: modset_sig={modset_sig!r} != {canonical_modset_sig!r}"
                    )
                if players_n is None or int(players_n) < 1:
                    prf01_violations.append(f"op {op['op_id']}: players_n={players_n} < 1")
                if dir_allow != 0:
                    prf01_violations.append(
                        f"op {op['op_id']}: director_allow_damage_b={dir_allow} != 0"
                    )
                if dir_orig not in (0, 1):
                    prf01_violations.append(
                        f"op {op['op_id']}: director_orig_allow_damage_b={dir_orig} not in (0, 1)"
                    )
                req_num_pf = op["req"]["num"]
                if (
                    "expected_orig_allow_damage_b" in req_num_pf
                    and int(req_num_pf["expected_orig_allow_damage_b"]) != dir_orig
                ):
                    prf01_violations.append(
                        f"op {op['op_id']}: director_orig_allow_damage_b={dir_orig} != expected {req_num_pf['expected_orig_allow_damage_b']}"
                    )
                if census_dyn != 0 or census_for != 0:
                    prf01_violations.append(
                        f"op {op['op_id']}: preflight area not clean (dynamic={census_dyn}, foreign={census_for})"
                    )
                if (
                    overcast is None
                    or rain is None
                    or fog is None
                    or abs(float(overcast)) > 1e-6
                    or abs(float(rain)) > 1e-6
                    or abs(float(fog)) > 1e-6
                ):
                    prf01_violations.append(
                        f"op {op['op_id']}: weather not fixed at 0.0 (overcast={overcast}, rain={rain}, fog={fog})"
                    )
            else:
                preflight_rejected_ops.append(op)

        # Every server perf_* 'done' result that carries modset_sig must match the canonical fixture
        if peer == "server" and verb in PERF_VERBS and status == "done":
            if "modset_sig" in p_str and p_str["modset_sig"] != canonical_modset_sig:
                prf01_violations.append(
                    f"op {op['op_id']} ({verb}): modset_sig={p_str['modset_sig']!r} != {canonical_modset_sig!r}"
                )

    # Check if the only preflight on server was a non-negative rejection (e.g., modset_mismatch against altered fixture)
    if not preflight_done_ops and preflight_rejected_ops:
        for rej_op in preflight_rejected_ops:
            if rej_op["reason"] in ("modset_mismatch", "world_mismatch") or rej_op["reason"].startswith("missing_class:"):
                prf01_violations.append(
                    f"op {rej_op['op_id']}: perf_preflight rejected with {rej_op['reason']!r}"
                )

    if prf01_violations:
        checks["PRF-01"] = "fail"
        reasons.extend(f"PRF-01: {v}" for v in prf01_violations)
    elif preflight_done_ops:
        checks["PRF-01"] = "pass"
    else:
        checks["PRF-01"] = "missing"

    # Check director protection cycle state tracking across multiple cycles (S-perf brief §2.2.3, N11)
    active_cycle_orig_allow: int | None = None
    for op in ops:
        if op["peer"] != "server" or op["status"] != "done":
            continue
        p_str = op["payload"]["str"]
        p_num = op["payload"]["num"]
        if op["verb"] == "perf_preflight":
            if active_cycle_orig_allow is not None:
                # Starting a new preflight without closing previous cycle via cleanup
                prf06_violations.append(
                    f"op {op['op_id']}: new perf_preflight before previous cycle cleanup invalidated director state"
                )
            orig_val = p_num.get("director_orig_allow_damage_b")
            if orig_val in (0, 1):
                active_cycle_orig_allow = int(orig_val)
        elif op["verb"] == "perf_step_apply":
            step_name = _normalize_step_id(p_str.get("step_id") or op["req"]["str"].get("step_id", ""))
            if step_name == "cleanup":
                cleanup_status = p_str.get("cleanup_status", "clean")
                if active_cycle_orig_allow is None:
                    prf06_violations.append(
                        f"op {op['op_id']}: cleanup executed without active cycle director state"
                    )
                else:
                    obs_orig = p_num.get("director_orig_allow_damage_b")
                    obs_allow = p_num.get("director_allow_damage_b")
                    if obs_orig != active_cycle_orig_allow or obs_allow != active_cycle_orig_allow:
                        prf06_violations.append(
                            f"op {op['op_id']}: cleanup did not restore director_allow_damage_b to cycle original {active_cycle_orig_allow} (got orig={obs_orig}, allow={obs_allow})"
                        )
                    # Only full clean cleanup invalidates the cycle state; partial foreign cleanup keeps cycle until final clean or ends cycle if no second cleanup follows
                    if cleanup_status == "clean":
                        active_cycle_orig_allow = None
            elif step_name in STEP_SPEC:
                if active_cycle_orig_allow is not None:
                    obs_orig = p_num.get("director_orig_allow_damage_b")
                    obs_allow = p_num.get("director_allow_damage_b")
                    if obs_orig != active_cycle_orig_allow:
                        prf02_violations.append(
                            f"op {op['op_id']} ({step_name}): director_orig_allow_damage_b={obs_orig} != cycle original {active_cycle_orig_allow}"
                        )
                    if obs_allow != 0:
                        prf02_violations.append(
                            f"op {op['op_id']} ({step_name}): director_allow_damage_b={obs_allow} != 0 during step"
                        )

    # -----------------------------------------------------------------------
    # Organize per-step operations (apply, window start + job_read, snaps)
    # -----------------------------------------------------------------------
    step_apply_ops: dict[str, dict[str, Any]] = {}
    step_window_starts: dict[str, list[dict[str, Any]]] = {}
    job_reads_by_id: dict[str, list[dict[str, Any]]] = {}
    job_frees_by_id: set[str] = set()
    step_snaps: dict[str, list[dict[str, Any]]] = {}
    all_snap_ops: list[dict[str, Any]] = []
    budget_check_ops: list[dict[str, Any]] = []
    cleanup_ops: list[dict[str, Any]] = []
    act_ops: list[dict[str, Any]] = []

    for op in ops:
        if op["peer"] != "server":
            continue
        verb = op["verb"]
        req_str = op["req"]["str"]
        req_num = op["req"]["num"]
        p_str = op["payload"]["str"]
        p_num = op["payload"]["num"]

        if verb.startswith("act_"):
            act_ops.append(op)
            if op["status"] != "done":
                prf02_violations.append(
                    f"op {op['op_id']} ({verb}): S3 actor command failed ({op['status']}/{op['reason']})"
                )

        elif verb == "perf_step_apply":
            raw_step = p_str.get("step_id") or req_str.get("step_id", "")
            step_id = _normalize_step_id(raw_step)
            if step_id == "cleanup":
                cleanup_ops.append(op)
            elif step_id in STEP_SPEC:
                step_apply_ops[step_id] = op
                step_snaps[step_id] = []
            elif op["status"] == "done":
                prf02_violations.append(f"op {op['op_id']}: unknown step_id {raw_step!r}")

        elif verb == "perf_window_start":
            raw_step = p_str.get("step_id") or req_str.get("step_id", "")
            step_id = _normalize_step_id(raw_step)
            step_window_starts.setdefault(step_id, []).append(op)

        elif verb in ("job_read", "poll_job"):
            job_id = p_str.get("job") or req_str.get("job", "")
            if job_id:
                job_reads_by_id.setdefault(job_id, []).append(op)

        elif verb == "job_free":
            job_id = p_str.get("job") or req_str.get("job", "")
            if job_id and op["status"] == "done":
                job_frees_by_id.add(job_id)

        elif verb == "perf_snap":
            all_snap_ops.append(op)
            raw_step = p_str.get("step_id") or req_str.get("step_id", "")
            step_id = _normalize_step_id(raw_step)
            # Group multi-page snaps or checkpoints for load steps (excluding N6 foreign injection)
            inj_b = int(req_num.get("inject_foreign_cargo_b", p_num.get("foreign_injected_b", 0)))
            if step_id in STEP_SPEC and inj_b == 0 and op["status"] == "done":
                step_snaps.setdefault(step_id, []).append(op)

        elif verb == "perf_budget_check":
            budget_check_ops.append(op)

    # Combine multi-page perf_snap calls that belong to the same checkpoint (page_n == 0 starts a checkpoint)
    step_checkpoints: dict[str, list[dict[str, Any]]] = {}
    for step_id, snap_list in step_snaps.items():
        merged_cps: list[dict[str, Any]] = []
        for sop in snap_list:
            p_num = sop["payload"]["num"]
            page_n = int(p_num.get("page_n", 0))
            pages_n = int(p_num.get("pages_n", 1))
            rows = list(sop["payload"]["rows"])
            if page_n == 0 or not merged_cps:
                merged_cps.append(
                    {
                        "op_id": sop["op_id"],
                        "tick_ms": float(p_num.get("tick_ms", 0.0)),
                        "frame": int(p_num.get("frame", 0)),
                        "pages_expected": pages_n,
                        "pages_seen": {page_n},
                        "num": dict(p_num),
                        "str": dict(sop["payload"]["str"]),
                        "rows": rows,
                    }
                )
            else:
                cur = merged_cps[-1]
                cur["pages_seen"].add(page_n)
                cur["rows"].extend(rows)
        step_checkpoints[step_id] = merged_cps

    # Assemble window datasets from perf_window_start + job_read (and step_<step>_polls.jsonl if present)
    step_windows: dict[str, dict[str, Any]] = {}
    n1a_short_windows: list[dict[str, Any]] = []
    n1b_modset_rejects: list[dict[str, Any]] = []
    technical_window_missing = False

    for step_id, start_ops in step_window_starts.items():
        for w_op in start_ops:
            req_str = w_op["req"]["str"]
            req_num = w_op["req"]["num"]
            if w_op["status"] == "rejected":
                if w_op["reason"] == "modset_mismatch":
                    n1b_modset_rejects.append(w_op)
                else:
                    prf03_violations.append(
                        f"op {w_op['op_id']} ({step_id}): perf_window_start rejected with {w_op['reason']!r}"
                    )
                continue
            if w_op["status"] != "done":
                prf03_violations.append(
                    f"op {w_op['op_id']} ({step_id}): perf_window_start status={w_op['status']!r}"
                )
                continue

            p_str = w_op["payload"]["str"]
            p_num = w_op["payload"]["num"]
            job_id = p_str.get("job", "")
            if not job_id:
                prf03_violations.append(f"op {w_op['op_id']} ({step_id}): missing job id")
                continue

            reads = job_reads_by_id.get(job_id, [])
            # Collect rows and terminal metadata across job_read operations
            merged_rows_by_seq: dict[int, dict[str, Any]] = {}
            raw_rows_list: list[dict[str, Any]] = []
            terminal_state = p_str.get("state", "running")
            terminal_num: dict[str, Any] = {}
            first_poll_h_ms = w_op["ack_ms"]
            last_poll_h_ms = w_op["read_ms"]

            # If rows were attached directly on w_op (e.g., synthetic compact fixture), read them too
            if w_op["payload"]["rows"]:
                for r in w_op["payload"]["rows"]:
                    raw_rows_list.append(r)

            for r_op in reads:
                if r_op["status"] != "done":
                    prf03_violations.append(
                        f"op {r_op['op_id']} (job_read {job_id}): status={r_op['status']!r}"
                    )
                    continue
                rp_str = r_op["payload"]["str"]
                rp_num = r_op["payload"]["num"]
                st = rp_str.get("state", "")
                if st in ("done", "stopped", "failed", "expired"):
                    terminal_state = st
                    terminal_num.update(rp_num)
                last_poll_h_ms = max(last_poll_h_ms, r_op["read_ms"])
                for row in r_op["payload"]["rows"]:
                    if "seq_n" in row and _is_finite_number(row["seq_n"]):
                        s_idx = int(row["seq_n"])
                        if s_idx not in merged_rows_by_seq:
                            merged_rows_by_seq[s_idx] = row
                            raw_rows_list.append(row)
                    else:
                        raw_rows_list.append(row)

            # Check optional step_<step>_polls.jsonl for harness clock span and terminal marks
            poll_file = samples_dir / f"step_{step_id}_polls.jsonl"
            poll_h_span_ms: float | None = None
            if poll_file.is_file():
                try:
                    polls = f03_common.read_jsonl(poll_file)
                    h_vals = [
                        float(p["h_ms"])
                        for p in polls
                        if isinstance(p, dict) and _is_finite_number(p.get("h_ms"))
                    ]
                    if len(h_vals) >= 2:
                        poll_h_span_ms = h_vals[-1] - h_vals[0]
                    for p in polls:
                        if isinstance(p, dict):
                            if p.get("state") in ("done", "stopped", "failed", "expired"):
                                terminal_state = str(p["state"])
                            for mk in ("end_tick_ms", "onjobend_tick_ms", "released_tick_ms", "rows_total_n"):
                                if _is_finite_number(p.get(mk)) and mk not in terminal_num:
                                    terminal_num[mk] = p[mk]
                except Exception as exc:
                    prf03_violations.append(f"malformed {poll_file.name}: {exc}")

            w_info = {
                "step_id": step_id,
                "job_id": job_id,
                "op_id": w_op["op_id"],
                "start_tick_ms": float(p_num.get("start_tick_ms", 0.0)),
                "start_frame": int(p_num.get("start_frame", 0)),
                "warmup_ms": float(p_num.get("warmup_ms", req_num.get("warmup_ms", 0.0))),
                "duration_ms": float(p_num.get("duration_ms", req_num.get("duration_ms", 0.0))),
                "sample_step_ms": float(
                    p_num.get("sample_step_ms", req_num.get("sample_step_ms", 0.0))
                ),
                "expected_rows_n": int(p_num.get("expected_rows_n", 61)),
                "terminal_state": terminal_state,
                "terminal_num": terminal_num,
                "rows": raw_rows_list,
                "freed": (job_id in job_frees_by_id)
                or (float(terminal_num.get("released_tick_ms", 0.0)) > 0.0),
                "h_span_ms": poll_h_span_ms
                if poll_h_span_ms is not None
                else max(0.0, last_poll_h_ms - first_poll_h_ms),
                "is_neg_probe": bool(
                    w_op["raw"].get("subcase") == "N1a"
                    or step_id not in STEP_SPEC
                    or (
                        step_id in step_windows
                        and len(raw_rows_list) == 1
                        and int(terminal_num.get("rows_total_n", len(raw_rows_list))) == 1
                    )
                ),
            }

            if w_info["is_neg_probe"]:
                n1a_short_windows.append(w_info)
            else:
                step_windows[step_id] = w_info

    # -----------------------------------------------------------------------
    # PRF-03: warmup_and_window_completeness
    # -----------------------------------------------------------------------
    valid_prf03_steps: set[str] = set()

    for step_id, w_info in step_windows.items():
        t_state = w_info["terminal_state"]
        rows = w_info["rows"]
        t_num = w_info["terminal_num"]
        rows_total_n = int(t_num.get("rows_total_n", len(rows)))

        # Non-done terminal states (stopped, failed, expired) are technical failures -> INCONCLUSO (Arbitraje N2, §4.2 N12)
        if t_state in ("stopped", "failed", "expired", "running"):
            technical_window_missing = True
            reasons.append(
                f"PRF-03 technical: step {step_id!r} job {w_info['job_id']!r} ended in state={t_state!r}"
            )
            continue

        # Terminal 'done' with < 61 samples is a completeness FAILURE (1 FALLA, insufficient_samples; Arbitraje N2)
        if rows_total_n < EXPECTED_WINDOW_ROWS or len(rows) < EXPECTED_WINDOW_ROWS:
            prf03_violations.append(
                f"step {step_id}: insufficient_samples (rows_total_n={rows_total_n}, rows={len(rows)} < {EXPECTED_WINDOW_ROWS})"
            )
            continue

        if w_info["warmup_ms"] < WARMUP_MIN_MS:
            prf03_violations.append(
                f"step {step_id}: warmup_ms={w_info['warmup_ms']} < {WARMUP_MIN_MS}"
            )
        if w_info["duration_ms"] < WINDOW_MIN_MS:
            prf03_violations.append(
                f"step {step_id}: duration_ms={w_info['duration_ms']} < {WINDOW_MIN_MS}"
            )
        if w_info["sample_step_ms"] != SAMPLE_STEP_MS:
            prf03_violations.append(
                f"step {step_id}: sample_step_ms={w_info['sample_step_ms']} != {SAMPLE_STEP_MS}"
            )

        # Verify all required columns exist in every row (anti-fabrication E9: reject probe-only labels)
        missing_col = False
        for r_idx, r in enumerate(rows):
            for col in WINDOW_NCOL:
                if col not in r or not _is_finite_number(r[col]):
                    prf03_violations.append(
                        f"step {step_id}: row[{r_idx}] missing or non-finite column {col!r}"
                    )
                    missing_col = True
                    break
            if missing_col:
                break
        if missing_col:
            continue

        # Check seq_n contiguous 0..N-1
        seqs = [int(r["seq_n"]) for r in rows]
        if seqs != list(range(len(rows))):
            prf03_violations.append(f"step {step_id}: seq_n not contiguous 0..{len(rows) - 1}")
            continue

        # Check warmup anchor from start_tick_ms to row[0].tick_ms (§4.1 N6, §5 PRF-03)
        first_tick = float(rows[0]["tick_ms"])
        last_tick = float(rows[-1]["tick_ms"])
        warmup_obs = first_tick - w_info["start_tick_ms"]
        if warmup_obs < WARMUP_MIN_MS:
            prf03_violations.append(
                f"step {step_id}: effective warmup {warmup_obs:.1f} ms < {WARMUP_MIN_MS} ms"
            )

        span_ms = last_tick - first_tick
        if span_ms < WINDOW_MIN_MS or span_ms > WINDOW_MAX_MS:
            prf03_violations.append(
                f"step {step_id}: window span {span_ms:.1f} ms outside [{WINDOW_MIN_MS}, {WINDOW_MAX_MS}] ms"
            )

        # Check per-step delta_t in [500, 1500] ms and strictly increasing frame and dtsum_ms
        step_dt_bad = False
        for i in range(1, len(rows)):
            dt = float(rows[i]["tick_ms"]) - float(rows[i - 1]["tick_ms"])
            df = int(rows[i]["frame"]) - int(rows[i - 1]["frame"])
            ddt = float(rows[i]["dtsum_ms"]) - float(rows[i - 1]["dtsum_ms"])
            if dt < SAMPLE_DT_MIN_MS or dt > SAMPLE_DT_MAX_MS:
                prf03_violations.append(
                    f"step {step_id}: sample interval dt[{i}]={dt:.1f} ms outside [{SAMPLE_DT_MIN_MS}, {SAMPLE_DT_MAX_MS}] ms"
                )
                step_dt_bad = True
                break
            if df <= 0 or ddt <= 0.0:
                prf03_violations.append(
                    f"step {step_id}: non-increasing frame or dtsum_ms at seq {i} (df={df}, ddt={ddt})"
                )
                step_dt_bad = True
                break
        if step_dt_bad:
            continue

        # Check job lifecycle marks: end_tick_ms <= onjobend_tick_ms <= released_tick_ms
        end_t = t_num.get("end_tick_ms")
        onjobend_t = t_num.get("onjobend_tick_ms")
        released_t = t_num.get("released_tick_ms")
        if (
            not _is_finite_number(end_t)
            or not _is_finite_number(onjobend_t)
            or not _is_finite_number(released_t)
        ):
            prf03_violations.append(
                f"step {step_id}: missing job lifecycle marks (end={end_t}, onjobend={onjobend_t}, released={released_t})"
            )
            continue
        if not (last_tick <= float(end_t) <= float(onjobend_t) <= float(released_t)):
            prf03_violations.append(
                f"step {step_id}: invalid job lifecycle order (last_tick={last_tick}, end={end_t}, onjobend={onjobend_t}, released={released_t})"
            )
            continue

        if step_id not in [v.split(":")[0].replace("step ", "") for v in prf03_violations]:
            valid_prf03_steps.add(step_id)

    if prf03_violations:
        checks["PRF-03"] = "fail"
        reasons.extend(f"PRF-03: {v}" for v in prf03_violations)
    elif valid_prf03_steps and not technical_window_missing:
        checks["PRF-03"] = "pass"
    else:
        checks["PRF-03"] = "missing"

    # -----------------------------------------------------------------------
    # PRF-04: dual_source_fps_agreement
    # -----------------------------------------------------------------------
    valid_prf04_steps: set[str] = set()
    step_fps_metrics: dict[str, dict[str, float]] = {}

    for step_id, w_info in step_windows.items():
        if w_info["terminal_state"] != "done":
            continue
        rows = w_info["rows"]
        # Guard against < 2 rows or zero span (S-perf brief §5 N13)
        if len(rows) < 2:
            continue
        if any(col not in r or not _is_finite_number(r[col]) for r in rows for col in ("tick_ms", "dtsum_ms", "frame", "avg_fps")):
            continue
        span_tick_ms = float(rows[-1]["tick_ms"]) - float(rows[0]["tick_ms"])
        if span_tick_ms <= 0.0:
            continue
        span_dtsum_ms = float(rows[-1]["dtsum_ms"]) - float(rows[0]["dtsum_ms"])
        delta_frames = float(int(rows[-1]["frame"]) - int(rows[0]["frame"]))
        if delta_frames <= 0.0:
            prf04_violations.append(f"step {step_id}: non-positive frame delta ({delta_frames})")
            continue

        fps_window_mean = sum(float(r["avg_fps"]) for r in rows) / float(len(rows))
        fps_frame_counter = delta_frames / (span_tick_ms / 1000.0)
        fps_roll5_min = _compute_roll5_min(rows)
        if fps_frame_counter <= 0.0 or fps_window_mean <= 0.0:
            prf04_violations.append(f"step {step_id}: non-positive FPS values")
            continue

        rel_diff_fps = abs(fps_window_mean - fps_frame_counter) / fps_frame_counter
        dtsum_drift = abs(span_dtsum_ms - span_tick_ms) / span_tick_ms

        h_span_ms = float(w_info.get("h_span_ms", span_tick_ms))
        h_drift = abs(h_span_ms - span_tick_ms) / span_tick_ms if h_span_ms > 0.0 else 0.0

        step_fps_metrics[step_id] = {
            "fps_window_mean": round(fps_window_mean, 4),
            "fps_frame_counter": round(fps_frame_counter, 4),
            "fps_roll5_min": round(fps_roll5_min, 4),
            "fps_rel_diff": round(rel_diff_fps, 6),
            "dtsum_drift": round(dtsum_drift, 6),
            "h_ms_drift": round(h_drift, 6),
        }

        step_failed_04 = False
        if rel_diff_fps > FPS_REL_TOL:
            prf04_violations.append(
                f"step {step_id}: FPS disagreement {rel_diff_fps:.4f} > {FPS_REL_TOL} (mean={fps_window_mean:.2f}, counter={fps_frame_counter:.2f})"
            )
            step_failed_04 = True
        if dtsum_drift > DTSUM_DRIFT_TOL:
            prf04_violations.append(
                f"step {step_id}: dtsum drift {dtsum_drift:.4f} > {DTSUM_DRIFT_TOL}"
            )
            step_failed_04 = True
        if h_drift > HARNESS_DRIFT_TOL:
            prf04_violations.append(
                f"step {step_id}: harness clock drift {h_drift:.4f} > {HARNESS_DRIFT_TOL}"
            )
            step_failed_04 = True

        if not step_failed_04:
            valid_prf04_steps.add(step_id)

    if step_fps_metrics:
        metrics["step_fps"] = step_fps_metrics

    if prf04_violations:
        checks["PRF-04"] = "fail"
        reasons.extend(f"PRF-04: {v}" for v in prf04_violations)
    elif valid_prf04_steps and not technical_window_missing:
        checks["PRF-04"] = "pass"
    else:
        checks["PRF-04"] = "missing"

    # -----------------------------------------------------------------------
    # PRF-02: step_loads_and_continuous_activity
    # -----------------------------------------------------------------------
    present_load_steps = (
        set(step_apply_ops.keys())
        | (set(step_windows.keys()) & set(STEP_SPEC.keys()))
        | set(step_checkpoints.keys())
    )
    valid_prf02_steps: set[str] = set()
    actor_driver_missing = bool(
        technical_data and technical_data.get("reason") == "actor_driver_unavailable"
    )

    for step_id in STEP_ORDER:
        if step_id not in present_load_steps:
            continue
        spec = STEP_SPEC[step_id]
        if spec["actors_n"] > 0 and actor_driver_missing:
            reasons.append(f"PRF-02 technical: actor_driver_unavailable on step {step_id!r}")
            continue

        step_bad = False
        apply_op = step_apply_ops.get(step_id)
        if apply_op is None:
            prf02_violations.append(f"step {step_id}: missing perf_step_apply")
            continue
        if apply_op["status"] != "done":
            if apply_op["reason"] == "expansion_unavailable":
                actor_driver_missing = True
                reasons.append(f"PRF-02 technical: expansion_unavailable on step {step_id!r}")
                continue
            prf02_violations.append(
                f"step {step_id}: perf_step_apply failed with {apply_op['status']}/{apply_op['reason']}"
            )
            continue

        ap_num = apply_op["payload"]["num"]
        req_num = apply_op["req"]["num"]

        # Verify requested and observed counts match STEP_SPEC[step_id]
        for cat in ("objects", "infected", "animals", "actors"):
            exp_val = spec[f"{cat}_n"]
            req_val = ap_num.get(f"{cat}_n", req_num.get(f"{cat}_n"))
            alive_val = ap_num.get(f"{cat}_alive_n", ap_num.get(f"{cat}_n"))
            if req_val != exp_val or alive_val != exp_val:
                prf02_violations.append(
                    f"step {step_id}: {cat} count mismatch (expected={exp_val}, req={req_val}, alive={alive_val})"
                )
                step_bad = True

        if ap_num.get("roots_alive_n") != spec["roots_n"]:
            prf02_violations.append(
                f"step {step_id}: roots_alive_n={ap_num.get('roots_alive_n')} != {spec['roots_n']}"
            )
            step_bad = True
        if ap_num.get("children_alive_n") != spec["children_n"]:
            prf02_violations.append(
                f"step {step_id}: children_alive_n={ap_num.get('children_alive_n')} != {spec['children_n']}"
            )
            step_bad = True
        if ap_num.get("entities_alive_n") != spec["entities_n"]:
            prf02_violations.append(
                f"step {step_id}: entities_alive_n={ap_num.get('entities_alive_n')} != {spec['entities_n']}"
            )
            step_bad = True
        if ap_num.get("director_allow_damage_b") != 0:
            prf02_violations.append(
                f"step {step_id}: director_allow_damage_b={ap_num.get('director_allow_damage_b')} != 0"
            )
            step_bad = True

        # Check spawn flags (#11)
        if spec["objects_n"] > 0:
            flags_obj = int(ap_num.get("spawn_flags_obj_n", 0))
            if flags_obj != SPAWN_FLAGS_OBJ or (flags_obj & FORBIDDEN_SPAWN_FLAG) != 0:
                prf02_violations.append(
                    f"step {step_id}: invalid spawn_flags_obj_n={flags_obj} (expected {SPAWN_FLAGS_OBJ})"
                )
                step_bad = True
        if (spec["infected_n"] + spec["animals_n"] + spec["actors_n"]) > 0:
            flags_ai = int(ap_num.get("spawn_flags_ai_n", 0))
            if flags_ai != SPAWN_FLAGS_AI or (flags_ai & FORBIDDEN_SPAWN_FLAG) != 0:
                prf02_violations.append(
                    f"step {step_id}: invalid spawn_flags_ai_n={flags_ai} (expected {SPAWN_FLAGS_AI})"
                )
                step_bad = True

        # Check 1 Hz window rows for continuous per-second activity (Arbitraje N3 & N5)
        w_info = step_windows.get(step_id)
        if w_info is not None and w_info["rows"]:
            rows = w_info["rows"]
            exp_roam_actors = (spec["actors_n"] + 1) // 2
            exp_emote_actors = spec["actors_n"] // 2
            exp_creatures = spec["infected_n"] + spec["animals_n"]

            for r_idx, r in enumerate(rows):
                if any(c not in r or not _is_finite_number(r[c]) for c in WINDOW_NCOL):
                    prf02_violations.append(f"step {step_id}: row[{r_idx}] missing activity columns")
                    step_bad = True
                    break
                if int(r["alive_roots_n"]) != spec["roots_n"]:
                    prf02_violations.append(
                        f"step {step_id}: row[{r_idx}] alive_roots_n={r['alive_roots_n']} != {spec['roots_n']}"
                    )
                    step_bad = True
                    break
                if int(r["alive_wardrobe_n"]) != spec["children_n"]:
                    prf02_violations.append(
                        f"step {step_id}: row[{r_idx}] alive_wardrobe_n={r['alive_wardrobe_n']} != {spec['children_n']}"
                    )
                    step_bad = True
                    break

                seq_n = int(r["seq_n"])
                if seq_n >= 1 and spec["k"] >= 1:
                    if exp_roam_actors > 0:
                        if (
                            float(r["roam_min_step_m"]) < ROAM_MIN_STEP_M
                            or float(r["roam_disp_step_m"]) < ROAM_MIN_STEP_M
                        ):
                            prf02_violations.append(
                                f"step {step_id}: seq={seq_n} roam_min_step_m={r['roam_min_step_m']} < {ROAM_MIN_STEP_M}"
                            )
                            step_bad = True
                            break
                    if exp_emote_actors > 0:
                        if (
                            int(r["emote_active_actors_n"]) != exp_emote_actors
                            or int(r["emote_cb_cmd1101_actors_n"]) != exp_emote_actors
                        ):
                            prf02_violations.append(
                                f"step {step_id}: seq={seq_n} emote callback 1101 inactive (active={r['emote_active_actors_n']}, cb1101={r['emote_cb_cmd1101_actors_n']}, expected={exp_emote_actors})"
                            )
                            step_bad = True
                            break
                    if exp_creatures > 0:
                        if (
                            int(r["creatures_moved_step_n"]) != exp_creatures
                            or float(r["creatures_min_step_m"]) < CREATURES_MIN_STEP_M
                        ):
                            prf02_violations.append(
                                f"step {step_id}: seq={seq_n} creature step movement below minimum (moved={r['creatures_moved_step_n']}/{exp_creatures}, min_step={r['creatures_min_step_m']} < {CREATURES_MIN_STEP_M})"
                            )
                            step_bad = True
                            break

        # Check 13 perf_snap checkpoints (cp = 0..12) and quarter trajectories Q1..Q4
        cps = step_checkpoints.get(step_id, [])
        if not cps:
            # If window completed with 61 rows, checkpoints are required for PRF-02 to pass
            if w_info is not None and len(w_info["rows"]) >= EXPECTED_WINDOW_ROWS and not step_bad:
                prf02_violations.append(f"step {step_id}: missing perf_snap checkpoints (0/{EXPECTED_SNAP_CHECKPOINTS})")
                step_bad = True
            continue

        if len(cps) < EXPECTED_SNAP_CHECKPOINTS:
            prf02_violations.append(
                f"step {step_id}: insufficient perf_snap checkpoints ({len(cps)} < {EXPECTED_SNAP_CHECKPOINTS})"
            )
            step_bad = True

        # Validate each checkpoint's census, counts, and entity rows
        entity_series: dict[int, list[dict[str, Any]]] = {}
        prev_cp_tick: float | None = None
        for cp_idx, cp in enumerate(cps):
            cp_num = cp["num"]
            cp_rows = cp["rows"]
            cp_tick = cp["tick_ms"]
            if prev_cp_tick is not None and cp_tick <= prev_cp_tick:
                prf02_violations.append(
                    f"step {step_id}: non-increasing checkpoint tick_ms at cp={cp_idx}"
                )
                step_bad = True
            prev_cp_tick = cp_tick

            if cp_num.get("director_allow_damage_b") != 0:
                prf02_violations.append(
                    f"step {step_id} cp={cp_idx}: director_allow_damage_b != 0"
                )
                step_bad = True
            if cp_num.get("roots_alive_n") != spec["roots_n"]:
                prf02_violations.append(
                    f"step {step_id} cp={cp_idx}: roots_alive_n={cp_num.get('roots_alive_n')} != {spec['roots_n']}"
                )
                step_bad = True
            if cp_num.get("children_alive_n") != spec["children_n"]:
                prf02_violations.append(
                    f"step {step_id} cp={cp_idx}: children_alive_n={cp_num.get('children_alive_n')} != {spec['children_n']}"
                )
                step_bad = True
            if cp_num.get("census_foreign_n", 0) != 0:
                prf02_violations.append(
                    f"step {step_id} cp={cp_idx}: unexpected foreign entity in census ({cp_num.get('census_foreign_n')})"
                )
                step_bad = True
            census_dyn = cp_num.get("census_dynamic_n")
            if census_dyn not in (spec["roots_n"], spec["entities_n"]):
                prf02_violations.append(
                    f"step {step_id} cp={cp_idx}: census_dynamic_n={census_dyn} does not match alive roots/entities ({spec['roots_n']}/{spec['entities_n']})"
                )
                step_bad = True

            if len(cp_rows) != spec["roots_n"]:
                prf02_violations.append(
                    f"step {step_id} cp={cp_idx}: snap row count {len(cp_rows)} != {spec['roots_n']}"
                )
                step_bad = True
                break

            for r in cp_rows:
                if any(c not in r or not _is_finite_number(r[c]) for c in SNAP_NCOL):
                    prf02_violations.append(
                        f"step {step_id} cp={cp_idx}: snap row missing required columns"
                    )
                    step_bad = True
                    break
                if int(r["alive_b"]) != 1 or int(r["foreign_content_b"]) != 0:
                    prf02_violations.append(
                        f"step {step_id} cp={cp_idx}: entity {r['entity_idx_n']} alive_b={r['alive_b']} foreign={r['foreign_content_b']}"
                    )
                    step_bad = True
                    break
                e_idx = int(r["entity_idx_n"])
                entity_series.setdefault(e_idx, []).append(r)
            if step_bad:
                break

        # Quarter trajectory & continuous activity reconstruction across cp = 0..12
        if not step_bad and spec["k"] >= 1 and len(cps) >= EXPECTED_SNAP_CHECKPOINTS:
            quarters = ((0, 3), (3, 6), (6, 9), (9, 12))
            roam_seen = 0
            emote_seen = 0
            creature_seen = 0

            for e_idx, series in sorted(entity_series.items()):
                if len(series) < EXPECTED_SNAP_CHECKPOINTS:
                    prf02_violations.append(
                        f"step {step_id}: entity {e_idx} missing checkpoints ({len(series)} < 13)"
                    )
                    step_bad = True
                    break
                kind = int(series[0]["kind_code_n"])
                role = int(series[0]["role_code_n"])

                # Actors (kind == 4) must wear 5 garments
                if kind == 4:
                    if any(int(s["wardrobe_n"]) != spec["wardrobe_per_actor_n"] for s in series):
                        prf02_violations.append(
                            f"step {step_id}: actor {e_idx} wardrobe_n != {spec['wardrobe_per_actor_n']}"
                        )
                        step_bad = True
                        break

                # Roam actor (kind == 4, role == 1)
                if kind == 4 and role == 1:
                    roam_seen += 1
                    substep_dists = [
                        math.hypot(
                            float(series[i + 1]["pos_x_m"]) - float(series[i]["pos_x_m"]),
                            float(series[i + 1]["pos_z_m"]) - float(series[i]["pos_z_m"]),
                        )
                        for i in range(12)
                    ]
                    if any(d < ROAM_SUBSTEP_MIN_M for d in substep_dists):
                        prf02_violations.append(
                            f"step {step_id}: roam actor {e_idx} stalled during 5 s sub-step (min={min(substep_dists):.3f} m < {ROAM_SUBSTEP_MIN_M} m)"
                        )
                        step_bad = True
                        break
                    for q_idx, (q_start, q_end) in enumerate(quarters, start=1):
                        q_dist = sum(substep_dists[q_start:q_end])
                        if q_dist < ROAM_QUARTER_MIN_M:
                            prf02_violations.append(
                                f"step {step_id}: roam actor {e_idx} Q{q_idx} displacement {q_dist:.2f} m < {ROAM_QUARTER_MIN_M} m"
                            )
                            step_bad = True
                            break
                    if step_bad:
                        break
                    total_dist = sum(substep_dists)
                    wp_legs = int(series[12]["wp_legs_n"]) - int(series[0]["wp_legs_n"])
                    if total_dist < ROAM_TOTAL_MIN_M or wp_legs < ROAM_MIN_WP_LEGS:
                        prf02_violations.append(
                            f"step {step_id}: roam actor {e_idx} 60 s total_dist={total_dist:.2f} m (< {ROAM_TOTAL_MIN_M}) or wp_legs={wp_legs} (< {ROAM_MIN_WP_LEGS})"
                        )
                        step_bad = True
                        break

                # Emote actor (kind == 4, role == 2)
                elif kind == 4 and role == 2:
                    emote_seen += 1
                    for cp_i, s in enumerate(series):
                        if (
                            int(s["emote_playing_b"]) != 1
                            or int(s["emote_cb_id_n"]) != EMOTE_CB_CMD_CLAP
                            or int(s["emote_cb_state_n"]) <= 0
                        ):
                            prf02_violations.append(
                                f"step {step_id}: emote actor {e_idx} inactive at cp={cp_i} (playing={s['emote_playing_b']}, cb_id={s['emote_cb_id_n']}, state={s['emote_cb_state_n']})"
                            )
                            step_bad = True
                            break
                        if cp_i > 0:
                            prev_ticks = int(series[cp_i - 1]["emote_active_ticks_n"])
                            cur_ticks = int(s["emote_active_ticks_n"])
                            # Require active ticks to advance substantially across every 5 s sub-step (Arbitraje N5)
                            if cur_ticks - prev_ticks < 3:
                                prf02_violations.append(
                                    f"step {step_id}: emote actor {e_idx} active_ticks stalled between cp={cp_i - 1} and cp={cp_i} ({prev_ticks} -> {cur_ticks})"
                                )
                                step_bad = True
                                break
                    if step_bad:
                        break
                    for q_idx, (q_start, q_end) in enumerate(quarters, start=1):
                        q_comp = int(series[q_end]["emote_completions_n"]) - int(
                            series[q_start]["emote_completions_n"]
                        )
                        if q_comp < EMOTE_QUARTER_MIN_COMPLETIONS:
                            prf02_violations.append(
                                f"step {step_id}: emote actor {e_idx} Q{q_idx} completions={q_comp} < {EMOTE_QUARTER_MIN_COMPLETIONS}"
                            )
                            step_bad = True
                            break
                    if step_bad:
                        break
                    tot_comp = int(series[12]["emote_completions_n"]) - int(
                        series[0]["emote_completions_n"]
                    )
                    if tot_comp < EMOTE_TOTAL_MIN_COMPLETIONS:
                        prf02_violations.append(
                            f"step {step_id}: emote actor {e_idx} total completions={tot_comp} < {EMOTE_TOTAL_MIN_COMPLETIONS}"
                        )
                        step_bad = True
                        break

                # Creatures: infected (kind == 2) and animals (kind == 3)
                elif kind in (2, 3):
                    creature_seen += 1
                    if any(int(s["ai_agent_b"]) != 1 for s in series):
                        prf02_violations.append(
                            f"step {step_id}: creature {e_idx} ai_agent_b != 1"
                        )
                        step_bad = True
                        break
                    substep_dists = [
                        math.hypot(
                            float(series[i + 1]["pos_x_m"]) - float(series[i]["pos_x_m"]),
                            float(series[i + 1]["pos_z_m"]) - float(series[i]["pos_z_m"]),
                        )
                        for i in range(12)
                    ]
                    if any(d <= 0.01 for d in substep_dists):
                        prf02_violations.append(
                            f"step {step_id}: creature {e_idx} stationary during 5 s sub-step (min={min(substep_dists):.4f} m)"
                        )
                        step_bad = True
                        break
                    for q_idx, (q_start, q_end) in enumerate(quarters, start=1):
                        q_dist = sum(substep_dists[q_start:q_end])
                        if q_dist < CREATURES_QUARTER_MIN_M:
                            prf02_violations.append(
                                f"step {step_id}: creature {e_idx} Q{q_idx} displacement {q_dist:.3f} m < {CREATURES_QUARTER_MIN_M} m"
                            )
                            step_bad = True
                            break
                    if step_bad:
                        break
                    tot_c_dist = sum(substep_dists)
                    if tot_c_dist < CREATURES_TOTAL_MIN_M:
                        prf02_violations.append(
                            f"step {step_id}: creature {e_idx} 60 s displacement {tot_c_dist:.3f} m < {CREATURES_TOTAL_MIN_M} m"
                        )
                        step_bad = True
                        break

            if not step_bad:
                exp_roam = (spec["actors_n"] + 1) // 2
                exp_emote = spec["actors_n"] // 2
                exp_creat = spec["infected_n"] + spec["animals_n"]
                if roam_seen != exp_roam or emote_seen != exp_emote or creature_seen != exp_creat:
                    prf02_violations.append(
                        f"step {step_id}: role counts in snap ({roam_seen} roam, {emote_seen} emote, {creature_seen} creatures) != expected ({exp_roam}, {exp_emote}, {exp_creat})"
                    )
                    step_bad = True

        if not step_bad and w_info is not None and len(w_info["rows"]) >= EXPECTED_WINDOW_ROWS:
            valid_prf02_steps.add(step_id)

    if prf02_violations:
        checks["PRF-02"] = "fail"
        reasons.extend(f"PRF-02: {v}" for v in prf02_violations)
    elif valid_prf02_steps and not actor_driver_missing and not technical_window_missing:
        checks["PRF-02"] = "pass"
    else:
        checks["PRF-02"] = "missing"

    # -----------------------------------------------------------------------
    # PRF-05: floor_and_combined_budget_derivation
    # -----------------------------------------------------------------------
    # Immediate floor failure rule (S-perf brief §5 PRF-05):
    # If 'base' or 'fixture' is present and has fps_window_mean <= 35.0 -> immediate 'fail'.
    for mandatory_step in ("base", "fixture"):
        if mandatory_step in step_fps_metrics:
            m_fps = step_fps_metrics[mandatory_step]["fps_window_mean"]
            c_fps = step_fps_metrics[mandatory_step]["fps_frame_counter"]
            if m_fps <= FLOOR_FPS or c_fps <= FLOOR_FPS:
                prf05_violations.append(
                    f"step {mandatory_step} below floor ({m_fps:.2f} / {c_fps:.2f} <= {FLOOR_FPS} FPS)"
                )

    certified_k: int | None = None
    certified_step_id: str | None = None

    all_four_present = all(
        s in valid_prf02_steps and s in valid_prf03_steps and s in valid_prf04_steps
        for s in STEP_ORDER
    )

    if not prf05_violations and all_four_present and checks["PRF-01"] == "pass":
        # Derive k* = max{k in {1,2,3} | for all j <= k, step j is admissible (fps_window_mean > 35.0)}
        k_star = 0
        for s_name in ("fixture", "inc1", "inc2"):
            s_k = STEP_SPEC[s_name]["k"]
            s_mean = step_fps_metrics[s_name]["fps_window_mean"]
            s_cnt = step_fps_metrics[s_name]["fps_frame_counter"]
            if s_mean > FLOOR_FPS and s_cnt > FLOOR_FPS:
                k_star = s_k
            else:
                break

        if k_star < 1:
            prf05_violations.append("no load step >= fixture met the > 35.0 FPS floor")
        else:
            certified_k = k_star
            certified_step_id = {1: "fixture", 2: "inc1", 3: "inc2"}[k_star]
            cap_spec = STEP_SPEC[certified_step_id]

            # Verify positive perf_budget_check at the certified cap (budget_at_cap)
            cap_accepted = False
            for bop in budget_check_ops:
                req_num = bop["req"]["num"]
                req_str = bop["req"]["str"]
                if req_str.get("expected_modset_sig", canonical_modset_sig) != canonical_modset_sig:
                    continue
                if (
                    int(req_num.get("cand_objects_n", -1)) == cap_spec["objects_n"]
                    and int(req_num.get("cand_infected_n", -1)) == cap_spec["infected_n"]
                    and int(req_num.get("cand_animals_n", -1)) == cap_spec["animals_n"]
                    and int(req_num.get("cand_actors_n", -1)) == cap_spec["actors_n"]
                    and int(req_num.get("cand_wardrobe_max_per_actor_n", -1))
                    == cap_spec["wardrobe_per_actor_n"]
                    and int(req_num.get("cand_wardrobe_total_n", -1)) == cap_spec["children_n"]
                    and int(req_num.get("cand_extra_children_n", -1)) == 0
                    and int(req_num.get("max_combined_roots_n", -1)) == cap_spec["roots_n"]
                    and int(req_num.get("max_combined_entities_n", -1)) == cap_spec["entities_n"]
                ):
                    if bop["status"] == "done":
                        bp_str = bop["payload"]["str"]
                        bp_num = bop["payload"]["num"]
                        if (
                            bp_str.get("budget_status") == "accepted"
                            and bp_str.get("violation_path", "") == ""
                            and int(bp_num.get("spawned_orders_n", -1)) == 0
                            and int(bp_num.get("headroom_roots_n", -1)) == 0
                            and int(bp_num.get("headroom_entities_n", -1)) == 0
                        ):
                            cap_accepted = True
                        else:
                            prf05_violations.append(
                                f"op {bop['op_id']}: budget_at_cap invalid done payload"
                            )
                    else:
                        prf05_violations.append(
                            f"op {bop['op_id']}: budget_at_cap rejected ({bop['reason']})"
                        )

            if not cap_accepted and not prf05_violations:
                prf05_violations.append(
                    f"missing accepted perf_budget_check at certified cap {certified_step_id!r} (k*={k_star})"
                )

            if not prf05_violations:
                c_fps_info = step_fps_metrics[certified_step_id]
                metrics["certified_budget"] = {
                    "certified_step_id": certified_step_id,
                    "certified_step_index": k_star,
                    "floor_fps": FLOOR_FPS,
                    "certified_window_mean_fps": c_fps_info["fps_window_mean"],
                    "certified_frame_counter_fps": c_fps_info["fps_frame_counter"],
                    "certified_roll5_min_fps": c_fps_info["fps_roll5_min"],
                    "max_objects_n": cap_spec["objects_n"],
                    "max_infected_n": cap_spec["infected_n"],
                    "max_animals_n": cap_spec["animals_n"],
                    "max_actors_n": cap_spec["actors_n"],
                    "max_wardrobe_per_actor_n": cap_spec["wardrobe_per_actor_n"],
                    "max_combined_roots_n": cap_spec["roots_n"],
                    "max_children_n": cap_spec["children_n"],
                    "max_combined_entities_n": cap_spec["entities_n"],
                    "modset_sig": canonical_modset_sig,
                    "measured_profile": {
                        "world": canonical_world,
                        "center_x_m": CENTER_POS[0],
                        "center_z_m": CENTER_POS[2],
                        "director_x_m": DIRECTOR_POS[0],
                        "director_z_m": DIRECTOR_POS[2],
                        "clear_radius_m": CLEAR_RADIUS_M,
                        "classes": modset_fixture.get("required_classes", {}),
                        "spawn_flags": {
                            "object_flags": SPAWN_FLAGS_OBJ,
                            "ai_flags": SPAWN_FLAGS_AI,
                        },
                        "ai_regime": "s3_adapter_roam_6m_emote_clap_1101_creature_sway_1p5m",
                    },
                }

    if prf05_violations:
        checks["PRF-05"] = "fail"
        reasons.extend(f"PRF-05: {v}" for v in prf05_violations)
    elif "certified_budget" in metrics:
        checks["PRF-05"] = "pass"
    else:
        checks["PRF-05"] = "missing"

    # -----------------------------------------------------------------------
    # PRF-06: negative_guards_and_clean_teardown
    # -----------------------------------------------------------------------
    # 1. Inspect every perf_budget_check operation for A6 guard violations
    seen_n5_reasons: set[str] = set()
    for bop in budget_check_ops:
        req_str = bop["req"]["str"]
        req_num = bop["req"]["num"]
        exp_sig = req_str.get("expected_modset_sig", canonical_modset_sig)
        if exp_sig != canonical_modset_sig:
            if bop["status"] == "rejected" and bop["reason"] == "modset_mismatch":
                n1b_modset_rejects.append(bop)
            else:
                prf06_violations.append(
                    f"op {bop['op_id']}: perf_budget_check with mismatched modset_sig did not reject with modset_mismatch"
                )
            continue

        expected_violation = _check_budget_violation_path(req_num)
        if expected_violation is not None:
            if bop["status"] != "rejected":
                prf06_violations.append(
                    f"op {bop['op_id']}: excess budget candidate ({expected_violation}) was not rejected (status={bop['status']!r})"
                )
            elif bop["reason"] != expected_violation:
                prf06_violations.append(
                    f"op {bop['op_id']}: expected reason {expected_violation!r}, got {bop['reason']!r}"
                )
            else:
                seen_n5_reasons.add(expected_violation)

    # 2. Check N2 (client role rejection on perf_snap or any perf_* verb)
    n2_client_rejects = [
        op
        for op in ops
        if op["peer"] == "client"
        and op["verb"] in PERF_VERBS
        and op["status"] == "rejected"
        and op["reason"] == "wrong_role:client"
    ]
    for op in ops:
        if op["peer"] == "client" and op["verb"] in PERF_VERBS:
            if op["status"] != "rejected" or op["reason"] != "wrong_role:client":
                # Note: status == "done" already fails PRF-01; any wrong rejection reason fails PRF-06
                if op["status"] != "done":
                    prf06_violations.append(
                        f"op {op['op_id']}: client {op['verb']} expected rejected/wrong_role:client, got {op['status']}/{op['reason']}"
                    )

    # 3. Check N1a (1-sample window probe rejected as insufficient_samples and freed)
    n1a_valid = False
    for nw in n1a_short_windows:
        t_num = nw["terminal_num"]
        r_tot = int(t_num.get("rows_total_n", len(nw["rows"])))
        if nw["terminal_state"] == "done" and r_tot == 1 and len(nw["rows"]) == 1:
            if not nw["freed"]:
                prf06_violations.append(
                    f"op {nw['op_id']}: N1a 1-row job {nw['job_id']!r} was not freed with job_free"
                )
            else:
                n1a_valid = True
        else:
            prf06_violations.append(
                f"op {nw['op_id']}: N1a expected done with 1 row, got state={nw['terminal_state']!r} rows={r_tot}"
            )

    # 4. Check N1b (modset_mismatch rejection)
    for op in preflight_rejected_ops:
        if op["reason"] == "modset_mismatch":
            n1b_modset_rejects.append(op)
    n1b_valid = len(n1b_modset_rejects) >= 1

    # 5. Check N4 (area_not_clear rejection on preflight when foreign entity present)
    n4_rejects = [
        op
        for op in preflight_rejected_ops
        if op["reason"] == "area_not_clear" or op["reason"].startswith("area_not_clear:")
    ]

    # 6. Check Pre/Post N1-N5 census invariance BEFORE N6 (S-perf brief §6 line 182, N10)
    foreign_inject_ops = [
        op
        for op in all_snap_ops
        if op["peer"] == "server"
        and int(
            op["req"]["num"].get(
                "inject_foreign_cargo_b",
                op["payload"]["num"].get("foreign_injected_b", 0),
            )
        )
        == 1
    ]

    neg_battery_ops = n1a_short_windows + n1b_modset_rejects + n2_client_rejects + [
        bop for bop in budget_check_ops if bop["status"] == "rejected"
    ]
    pre_post_n5_invariance_ok = False
    if neg_battery_ops:
        first_neg_idx = min(
            (x["idx"] if "idx" in x else 0)
            for x in (
                n1b_modset_rejects
                + n2_client_rejects
                + [bop for bop in budget_check_ops if bop["status"] == "rejected"]
            )
        ) if (n1b_modset_rejects or n2_client_rejects or budget_check_ops) else 0
        last_n5_idx = max(
            (bop["idx"] for bop in budget_check_ops if bop["status"] == "rejected"),
            default=first_neg_idx,
        )
        first_n6_idx = min((op["idx"] for op in foreign_inject_ops), default=len(raw_records) + 1)
        if last_n5_idx > first_n6_idx:
            prf06_violations.append(
                "N1-N5 negative battery did not finish before N6 foreign cargo injection"
            )
        snaps_before_n5 = [
            op
            for op in all_snap_ops
            if op["peer"] == "server"
            and op["status"] == "done"
            and op["idx"] < first_neg_idx
            and int(op["payload"]["num"].get("foreign_injected_b", 0)) == 0
        ]
        snaps_after_n5_before_n6 = [
            op
            for op in all_snap_ops
            if op["peer"] == "server"
            and op["status"] == "done"
            and last_n5_idx < op["idx"] < first_n6_idx
            and int(op["payload"]["num"].get("foreign_injected_b", 0)) == 0
        ]
        if snaps_before_n5 and snaps_after_n5_before_n6:
            pre_s = snaps_before_n5[-1]["payload"]["num"]
            post_s = snaps_after_n5_before_n6[0]["payload"]["num"]
            for k_cmp in (
                "objects_alive_n",
                "infected_alive_n",
                "animals_alive_n",
                "actors_alive_n",
                "roots_alive_n",
                "children_alive_n",
                "entities_alive_n",
                "census_dynamic_n",
                "census_foreign_n",
            ):
                if pre_s.get(k_cmp) != post_s.get(k_cmp):
                    prf06_violations.append(
                        f"N1-N5 census invariance broken on {k_cmp}: before={pre_s.get(k_cmp)} vs after={post_s.get(k_cmp)}"
                    )
            if not prf06_violations:
                pre_post_n5_invariance_ok = True

    # 7. Check N6 (foreign_cargo in SeaChest + equipped garment, preserving actor ancestor) & teardown
    n6_valid = False
    if foreign_inject_ops:
        inj_op = foreign_inject_ops[-1]
        if inj_op["status"] != "done":
            prf06_violations.append(
                f"op {inj_op['op_id']}: perf_snap(inject_foreign_cargo_b=1) failed"
            )
        else:
            inj_num = inj_op["payload"]["num"]
            inj_rows = inj_op["payload"]["rows"]
            if int(inj_num.get("foreign_injected_b", 0)) != 1 or int(inj_num.get("census_foreign_n", 0)) < 2:
                prf06_violations.append(
                    f"op {inj_op['op_id']}: N6 injection did not record foreign_injected_b=1 and census_foreign_n>=2 (got {inj_num.get('census_foreign_n')})"
                )
            # Record pre-cleanup positions of entities flagged with foreign_content_b == 1
            pre_foreign_entities: dict[int, tuple[ int, float, float, float ]] = {}
            for r in inj_rows:
                if int(r.get("foreign_content_b", 0)) == 1:
                    pre_foreign_entities[int(r["entity_idx_n"])] = (
                        int(r["kind_code_n"]),
                        float(r["pos_x_m"]),
                        float(r["pos_y_m"]),
                        float(r["pos_z_m"]),
                    )
            if len(pre_foreign_entities) < 2:
                prf06_violations.append(
                    f"op {inj_op['op_id']}: N6 injection snap must mark both SeaChest and actor with foreign_content_b=1"
                )

            # Find the cleanup operation immediately following inj_op
            post_inj_cleanups = [c for c in cleanup_ops if c["idx"] > inj_op["idx"]]
            if not post_inj_cleanups:
                prf06_violations.append("N6: missing cleanup after foreign cargo injection")
            else:
                c1 = post_inj_cleanups[0]
                c1_str = c1["payload"]["str"]
                c1_num = c1["payload"]["num"]
                if c1["status"] != "done":
                    prf06_violations.append(f"op {c1['op_id']}: N6 cleanup not done")
                else:
                    if c1_str.get("cleanup_status") != "partial_foreign_content":
                        prf06_violations.append(
                            f"op {c1['op_id']}: expected cleanup_status='partial_foreign_content', got {c1_str.get('cleanup_status')!r}"
                        )
                    if int(c1_num.get("skipped_foreign_containers_n", 0)) != 2:
                        prf06_violations.append(
                            f"op {c1['op_id']}: expected skipped_foreign_containers_n=2 (SeaChest + garment), got {c1_num.get('skipped_foreign_containers_n')}"
                        )
                    if int(c1_num.get("preserved_ancestors_n", 0)) != 1:
                        prf06_violations.append(
                            f"op {c1['op_id']}: expected preserved_ancestors_n=1 (actor), got {c1_num.get('preserved_ancestors_n')}"
                        )
                    if (
                        int(c1_num.get("objects_alive_n", -1)) != 1
                        or int(c1_num.get("actors_alive_n", -1)) != 1
                        or int(c1_num.get("infected_alive_n", -1)) != 0
                        or int(c1_num.get("animals_alive_n", -1)) != 0
                        or int(c1_num.get("roots_alive_n", -1)) != 2
                        or int(c1_num.get("children_alive_n", -1)) != 1
                        or int(c1_num.get("entities_alive_n", -1)) != 3
                    ):
                        prf06_violations.append(
                            f"op {c1['op_id']}: N6 partial cleanup survivor counts mismatch (expected 1 object, 1 actor, 1 garment -> 2 roots, 1 child, 3 entities)"
                        )

                    # Find the perf_snap immediately after c1 (cleanup_snap)
                    snaps_after_c1 = [
                        s
                        for s in all_snap_ops
                        if s["peer"] == "server" and s["status"] == "done" and s["idx"] > c1["idx"]
                    ]
                    if not snaps_after_c1:
                        prf06_violations.append("N6: missing cleanup_snap after partial cleanup")
                    else:
                        cs = snaps_after_c1[0]
                        cs_num = cs["payload"]["num"]
                        cs_rows = cs["payload"]["rows"]
                        if (
                            int(cs_num.get("roots_alive_n", -1)) != 2
                            or int(cs_num.get("children_alive_n", -1)) != 1
                            or int(cs_num.get("entities_alive_n", -1)) != 3
                            or int(cs_num.get("census_foreign_n", -1)) != 2
                        ):
                            prf06_violations.append(
                                f"op {cs['op_id']}: cleanup_snap counts mismatch (roots={cs_num.get('roots_alive_n')}, children={cs_num.get('children_alive_n')}, foreign={cs_num.get('census_foreign_n')})"
                            )
                        if cs_num.get("director_allow_damage_b") != cs_num.get(
                            "director_orig_allow_damage_b"
                        ):
                            prf06_violations.append(
                                f"op {cs['op_id']}: cleanup_snap director_allow_damage_b not restored to original"
                            )
                        if len(cs_rows) != 2:
                            prf06_violations.append(
                                f"op {cs['op_id']}: cleanup_snap expected 2 root rows (SeaChest + preserved actor), got {len(cs_rows)}"
                            )
                        else:
                            kinds_seen = set()
                            for r in cs_rows:
                                e_idx = int(r["entity_idx_n"])
                                kind = int(r["kind_code_n"])
                                kinds_seen.add(kind)
                                if int(r["alive_b"]) != 1 or int(r["foreign_content_b"]) != 1:
                                    prf06_violations.append(
                                        f"op {cs['op_id']}: survivor {e_idx} must have alive_b=1 and foreign_content_b=1"
                                    )
                                if kind == 4 and int(r["wardrobe_n"]) != 1:
                                    prf06_violations.append(
                                        f"op {cs['op_id']}: preserved actor {e_idx} must retain exactly the 1 garment with foreign cargo (got wardrobe_n={r['wardrobe_n']})"
                                    )
                                if e_idx in pre_foreign_entities:
                                    _, px, py, pz = pre_foreign_entities[e_idx]
                                    dist = math.sqrt(
                                        (float(r["pos_x_m"]) - px) ** 2
                                        + (float(r["pos_y_m"]) - py) ** 2
                                        + (float(r["pos_z_m"]) - pz) ** 2
                                    )
                                    if dist > 0.05:
                                        prf06_violations.append(
                                            f"op {cs['op_id']}: preserved entity {e_idx} moved during cleanup ({dist:.3f} m)"
                                        )
                            if kinds_seen != {1, 4}:
                                prf06_violations.append(
                                    f"op {cs['op_id']}: expected survivor kinds {{1 (SeaChest), 4 (Actor)}}, got {kinds_seen}"
                                )

                        # If bench closure (second cleanup after bench_reset_foreign) is present, verify 0 survivors
                        if len(post_inj_cleanups) >= 2:
                            c2 = post_inj_cleanups[-1]
                            c2_str = c2["payload"]["str"]
                            c2_num = c2["payload"]["num"]
                            if (
                                c2["status"] != "done"
                                or c2_str.get("cleanup_status") != "clean"
                                or int(c2_num.get("roots_alive_n", -1)) != 0
                                or int(c2_num.get("children_alive_n", -1)) != 0
                                or int(c2_num.get("entities_alive_n", -1)) != 0
                            ):
                                prf06_violations.append(
                                    f"op {c2['op_id']}: bench closure cleanup did not leave 0 entities"
                                )
                            snaps_after_c2 = [
                                s
                                for s in all_snap_ops
                                if s["peer"] == "server"
                                and s["status"] == "done"
                                and s["idx"] > c2["idx"]
                            ]
                            if snaps_after_c2:
                                fs = snaps_after_c2[-1]["payload"]
                                if (
                                    int(fs["num"].get("roots_alive_n", -1)) != 0
                                    or int(fs["num"].get("entities_alive_n", -1)) != 0
                                    or int(fs["num"].get("census_dynamic_n", -1)) != 0
                                    or int(fs["num"].get("census_foreign_n", -1)) != 0
                                    or len(fs["rows"]) != 0
                                ):
                                    prf06_violations.append(
                                        "final_snap after bench closure does not show 0 entities and 0 foreign cargo"
                                    )

                        if not prf06_violations:
                            n6_valid = True

    # Check optional samples/final_snap.json if present
    final_snap_path = samples_dir / "final_snap.json"
    if final_snap_path.is_file():
        try:
            raw_fs = json.loads(final_snap_path.read_text(encoding="utf-8"))
            fs_unpacked, fs_err = _unpack_any_payload(raw_fs)
            if fs_err is not None or fs_unpacked is None:
                prf06_violations.append(f"malformed final_snap.json ({fs_err})")
            else:
                fs_num = fs_unpacked["num"]
                if fs_num.get("director_allow_damage_b") != fs_num.get("director_orig_allow_damage_b"):
                    prf06_violations.append(
                        "final_snap.json: director_allow_damage_b != director_orig_allow_damage_b"
                    )
        except Exception as exc:
            prf06_violations.append(f"invalid final_snap.json ({exc})")

    # Determine if the complete §6 negative suite + teardown is present and valid
    all_n5_present = all(r in seen_n5_reasons for r in N5_REQUIRED_REASONS)
    full_prf06_ready = (
        n1a_valid
        and n1b_valid
        and len(n2_client_rejects) >= 1
        and all_n5_present
        and pre_post_n5_invariance_ok
        and n6_valid
    )

    if prf06_violations:
        checks["PRF-06"] = "fail"
        reasons.extend(f"PRF-06: {v}" for v in prf06_violations)
    elif full_prf06_ready:
        checks["PRF-06"] = "pass"
    else:
        checks["PRF-06"] = "missing"

    # -----------------------------------------------------------------------
    # Final Verdict Aggregation (S-perf brief §5: fail > missing > pass)
    # -----------------------------------------------------------------------
    if any(v == "fail" for v in checks.values()):
        code = gate_core.FALLA
    elif (
        transport_failures
        or technical_data is not None
        or technical_window_missing
        or actor_driver_missing
        or any(v != "pass" for v in checks.values())
    ):
        code = gate_core.INCONCLUSO
        if transport_failures:
            reasons.extend(f"transport: {t}" for t in transport_failures)
        if technical_data is not None:
            reasons.append(f"technical: {technical_data.get('reason', 'blocker')}")
    else:
        code = gate_core.PASA

    return gate_core.make_verdict(
        SPIKE_ID,
        code,
        checks=checks,
        metrics=metrics,
        reasons=reasons,
    )
