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
        ``frame``, ``avg_fps_now``, and (N6, Sol r1 BLOQ 11) ``foreign_sig_n``: a numeric
        signature of the engine identities of the foreign items. It is > 0 on the injection
        snapshot, identical on the snapshot after the partial cleanup iff the SAME two Rag
        survived (destruction or substitution change it) and 0 once they are retired.
        Checkpoint rows are bound to the window by SERVER time (``tick_ms``), their identities
        (``entity_idx_n``) are unique per snapshot and stable across snapshots, and the
        per-category counts of the headers must equal the reconstruction from the rows.
        The 4 quarters are the temporal quarters of ``[rows[0].tick_ms, rows[-1].tick_ms]``.
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

3. Optional supplementary files in ``samples/`` (NEVER a source of state, marks or clocks:
   Sol r1 BLOQ 1/2; job state and marks come only from the raw ``job_read`` results of the
   core's bridge log, and the harness clock only from the bridge's deliver/result instants)
   - ``samples/step_<step>_polls.jsonl``: written by the runner (N12 wait record); ignored here.
   - ``samples/final_snap.json``: may only ADD violations; the closure needs a RAW snapshot.
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

PASA, FALLA, INCONCLUSO = 0, 1, 2  # codigos de gate_core.verdict_name
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


def _checks_out(checks: dict[str, str], reasons: list[str]) -> list[dict[str, str]]:
    """Core verdict format: list of {id, status, detail} (f03_common.aggregate_spike reads it)."""
    out: list[dict[str, str]] = []
    for cid in CHECK_IDS:
        detail = ""
        prefix = f"{cid}:"
        for r in reasons:
            if r.startswith(prefix):
                detail = r[len(prefix):].strip()[:300]
                break
        out.append({"detail": detail, "id": cid, "status": checks.get(cid, "missing")})
    return out


_CORE_EVENT_KINDS = ("enq", "deliver", "result", "expire", "lost")


def _merge_core_events(raw: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Join the REAL bridge event log (enq -> deliver -> result, written by the harness core
    from the HTTP traffic) into one record per op. Anything not written by the core
    (no ``ev``) is a violation: the evaluator never accepts pre-merged records."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    viol: list[str] = []
    for idx, ev in enumerate(raw):
        if not isinstance(ev, dict) or not isinstance(ev.get("ev"), str):
            viol.append(f"record[{idx}] is not a bridge event (no 'ev')")
            continue
        kind = ev["ev"]
        if kind not in _CORE_EVENT_KINDS:
            continue  # hello, poll, keepalive, test_mode, ... are not operations
        op_id = ev.get("op_id")
        if not isinstance(op_id, str) or not op_id.strip():
            viol.append(f"record[{idx}] missing valid op_id")
            continue
        t_ms = ev.get("t_ms")
        if kind == "enq":
            if op_id in merged:
                viol.append(f"duplicate op_id {op_id!r}")
                continue
            merged[op_id] = {
                "op_id": op_id,
                "verb": ev.get("verb"),
                "peer": ev.get("peer"),
                "args": ev.get("args") if isinstance(ev.get("args"), dict) else {},
                "issued_ms": t_ms,
                "deliver_ms": None,
                "result": None,
                "result_ms": None,
                "terminal": None,
                "terminal_ms": None,
            }
            order.append(op_id)
            continue
        rec = merged.get(op_id)
        if rec is None:
            viol.append(f"{kind} for op {op_id!r} without enq")
            continue
        if kind == "deliver":
            if rec["deliver_ms"] is None:
                rec["deliver_ms"] = t_ms
                if ev.get("peer") not in (None, rec["peer"]):
                    viol.append(f"op {op_id}: delivered to {ev.get('peer')!r}, enqueued for {rec['peer']!r}")
        elif kind == "result":
            if rec["result"] is None and isinstance(ev.get("result"), dict):
                rec["result"] = ev["result"]
                rec["result_ms"] = t_ms
        elif rec["terminal"] is None:  # expire / lost
            rec["terminal"] = kind
            rec["terminal_ms"] = t_ms
    out: list[dict[str, Any]] = []
    for op_id in order:
        rec = merged[op_id]
        issued = rec["issued_ms"]
        if rec["result"] is not None:
            if rec["deliver_ms"] is None:
                viol.append(f"op {op_id}: result without deliver")
                continue
            body = rec["result"]
            read = dict(body.get("read") or {}) if isinstance(body.get("read"), dict) else {}
            read["status"] = body.get("status")
            read["reason"] = body.get("reason", "")
            out.append(
                {
                    "op_id": op_id,
                    "verb": rec["verb"],
                    "peer": rec["peer"],
                    "args": rec["args"],
                    "issued_ms": issued,
                    "ack_ms": rec["deliver_ms"],
                    "read_ms": rec["result_ms"],
                    "ack": {"status": "ok", "reason": ""},
                    "read": read,
                }
            )
        else:
            status = "lost" if rec["terminal"] == "lost" else "timeout"
            t_end = rec["terminal_ms"] if rec["terminal_ms"] is not None else issued
            out.append(
                {
                    "op_id": op_id,
                    "verb": rec["verb"],
                    "peer": rec["peer"],
                    "args": rec["args"],
                    "issued_ms": issued,
                    "ack_ms": rec["deliver_ms"] if rec["deliver_ms"] is not None else issued,
                    "read_ms": t_end,
                    "ack": {"status": "ok", "reason": ""},
                    "read": {"status": status, "reason": status, "has": []},
                }
            )
    return out, viol



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
# Helpers for the Sol-r1 hardening (BLOQ 4, 5, 10, 11): per-category identity counts,
# time-anchored checkpoints, temporal quarters and the isolated N5 stimuli
# ---------------------------------------------------------------------------

CP_ANCHOR_TOL_MS = 2500.0
CP_GAP_MIN_MS = 2500.0
CP_GAP_MAX_MS = 10000.0
ROLE_OF_KIND = {1: (0,), 2: (3,), 3: (3,), 4: (1, 2)}
KIND_COUNT_KEY = {1: "objects_n", 2: "infected_n", 3: "animals_n", 4: "actors_n"}
KIND_ALIVE_KEY = {1: "objects_alive_n", 2: "infected_alive_n", 3: "animals_alive_n", 4: "actors_alive_n"}
TERMINAL_STATES = ("done", "stopped", "failed", "expired")
N6_RETIRED_CENSUS = 0


def _start_is_neg_probe(op: dict[str, Any], step_id: str) -> bool:
    """A `perf_window_start` that is the N1a probe (1 expected row, no warmup, <= 1 s) or has no step."""
    p_num = op["payload"]["num"]
    r_num = op["req"]["num"]
    return bool(
        op["raw"].get("subcase") == "N1a"
        or step_id not in STEP_SPEC
        or (
            int(p_num.get("expected_rows_n", 61)) == 1
            and float(p_num.get("warmup_ms", r_num.get("warmup_ms", 0.0))) == 0
            and float(p_num.get("duration_ms", r_num.get("duration_ms", 0.0))) <= 1000
        )
    )


def _mid_h_ms(op: dict[str, Any]) -> float:
    """Harness-clock instant at which the peer executed the order: midpoint of the core's
    deliver and result events (both written by the bridge, never by the runner)."""
    return (float(op["ack_ms"]) + float(op["read_ms"])) / 2.0


def _interp(points: list[tuple[float, float]], t: float) -> float:
    """Piecewise-linear value at server time `t` of a (tick, value) series sorted by tick."""
    if t <= points[0][0]:
        return points[0][1]
    if t >= points[-1][0]:
        return points[-1][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            return v1 if t1 == t0 else v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return points[-1][1]


def _path_len(pts: list[tuple[float, float, float]], a: float, b: float) -> float:
    """Horizontal path length of an entity between server times `a` and `b`, with the
    positions at the boundaries interpolated from the surrounding checkpoints."""
    xs = [(t, x) for t, x, _ in pts]
    zs = [(t, z) for t, _, z in pts]
    poly = [(_interp(xs, a), _interp(zs, a))]
    poly += [(x, z) for t, x, z in pts if a < t < b]
    poly.append((_interp(xs, b), _interp(zs, b)))
    return sum(math.hypot(q[0] - p[0], q[1] - p[1]) for p, q in zip(poly, poly[1:]))


def _cp_time_violations(cps: list[dict[str, Any]], t0: float, t_end: float) -> list[str]:
    """Checkpoints must be ordered in server time, spread every ~5 s and anchored to the
    measured window [t0, t_end] (rows[0].tick_ms .. rows[-1].tick_ms), not just to each other."""
    out: list[str] = []
    ticks = [c["tick_ms"] for c in cps]
    for i in range(1, len(ticks)):
        if ticks[i] <= ticks[i - 1]:
            out.append(f"non-increasing checkpoint tick_ms at cp={i}")
    gaps = [b - a for a, b in zip(ticks, ticks[1:])]
    if gaps and any(g < CP_GAP_MIN_MS or g > CP_GAP_MAX_MS for g in gaps):
        out.append(
            f"checkpoint tick_ms spacing outside [{CP_GAP_MIN_MS:.0f}, {CP_GAP_MAX_MS:.0f}] ms "
            f"(min={min(gaps):.0f}, max={max(gaps):.0f})"
        )
    elif ticks and ticks[-1] - ticks[0] < 50000.0:
        out.append(f"checkpoints span only {ticks[-1] - ticks[0]:.0f} ms (< 50000)")
    if ticks:
        outside = [t for t in ticks if t < t0 - CP_ANCHOR_TOL_MS or t > t_end + CP_ANCHOR_TOL_MS]
        if outside:
            out.append(
                f"{len(outside)} checkpoint(s) outside the measured window [{t0:.0f}, {t_end:.0f}] ms "
                f"(first at {outside[0]:.0f}); activity belongs to another window"
            )
        if ticks[0] > t0 + CP_ANCHOR_TOL_MS or ticks[-1] < t_end - CP_ANCHOR_TOL_MS:
            out.append(
                f"checkpoints [{ticks[0]:.0f}, {ticks[-1]:.0f}] ms do not cover the measured window [{t0:.0f}, {t_end:.0f}] ms"
            )
    return out


def _cp_rows_violations(spec: dict[str, int], cp_idx: int, cp: dict[str, Any]) -> list[str]:
    """Per-checkpoint identity and category reconstruction from the raw rows (BLOQ 4)."""
    out: list[str] = []
    rows = cp["rows"]
    num = cp["num"]
    tag = f"cp={cp_idx}"
    if len(rows) != spec["roots_n"]:
        return [f"{tag}: snap row count {len(rows)} != {spec['roots_n']}"]
    for r in rows:
        if any(c not in r or not _is_finite_number(r[c]) for c in SNAP_NCOL):
            return [f"{tag}: snap row missing required columns"]
    for r in rows:
        if int(r["alive_b"]) != 1 or int(r["foreign_content_b"]) != 0:
            return [f"{tag}: entity {r['entity_idx_n']} alive_b={r['alive_b']} foreign={r['foreign_content_b']}"]
    ids = [int(r["entity_idx_n"]) for r in rows]
    if len(set(ids)) != len(ids):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        out.append(f"{tag}: duplicate entity_idx_n {dup[:5]} (identities must be unique per checkpoint)")
    kind_n: dict[int, int] = {}
    for r in rows:
        kind_n[int(r["kind_code_n"])] = kind_n.get(int(r["kind_code_n"]), 0) + 1
    for kind, key in KIND_COUNT_KEY.items():
        if kind_n.get(kind, 0) != spec[key]:
            out.append(f"{tag}: kind {kind} rows={kind_n.get(kind, 0)} != {spec[key]} ({key})")
        header = num.get(KIND_ALIVE_KEY[kind])
        if header != kind_n.get(kind, 0):
            out.append(
                f"{tag}: header {KIND_ALIVE_KEY[kind]}={header} != {kind_n.get(kind, 0)} rows of kind {kind}"
            )
    if set(kind_n) - set(KIND_COUNT_KEY):
        out.append(f"{tag}: unknown kind_code_n {sorted(set(kind_n) - set(KIND_COUNT_KEY))}")
    roam = emote = 0
    for r in rows:
        kind, role = int(r["kind_code_n"]), int(r["role_code_n"])
        if kind in ROLE_OF_KIND and role not in ROLE_OF_KIND[kind]:
            out.append(f"{tag}: entity {r['entity_idx_n']} kind {kind} has role_code_n={role}")
            break
        if kind == 4:
            roam += role == 1
            emote += role == 2
    if roam != (spec["actors_n"] + 1) // 2 or emote != spec["actors_n"] // 2:
        out.append(f"{tag}: actor roles ({roam} roam, {emote} emote) != ({(spec['actors_n'] + 1) // 2}, {spec['actors_n'] // 2})")
    wardrobe = sum(int(r["wardrobe_n"]) for r in rows if int(r["kind_code_n"]) == 4)
    if wardrobe != spec["children_n"]:
        out.append(f"{tag}: garments on actor rows {wardrobe} != children_n {spec['children_n']}")
    if any(int(r["wardrobe_n"]) != 0 for r in rows if int(r["kind_code_n"]) != 4):
        out.append(f"{tag}: non-actor rows carry garments")
    census = num.get("census_dynamic_n")
    if census not in (spec["roots_n"], spec["entities_n"]):
        out.append(f"{tag}: census_dynamic_n={census} does not match alive roots/entities ({spec['roots_n']}/{spec['entities_n']})")
    return out


def _cp_activity_violations(
    step_id: str, spec: dict[str, int], cps: list[dict[str, Any]], t0: float, t_end: float
) -> list[str]:
    """Continuity per temporal quarter, reconstructed from raw positions at the real server
    times of the checkpoints (BLOQ 5): the four quarters are [t0 + j*span/4, t0 + (j+1)*span/4]."""
    out: list[str] = []
    span = t_end - t0
    bounds = [(t0 + span * j / 4.0, t0 + span * (j + 1) / 4.0) for j in range(4)]
    series: dict[int, list[tuple[float, dict[str, Any]]]] = {}
    id_sets = []
    for cp in cps:
        id_sets.append({int(r["entity_idx_n"]) for r in cp["rows"]})
        for r in cp["rows"]:
            series.setdefault(int(r["entity_idx_n"]), []).append((cp["tick_ms"], r))
    if any(s != id_sets[0] for s in id_sets):
        return [f"step {step_id}: the set of entity identities changes between checkpoints"]
    roam_seen = emote_seen = creature_seen = 0
    for e_idx, pts in sorted(series.items()):
        kind = int(pts[0][1]["kind_code_n"])
        role = int(pts[0][1]["role_code_n"])
        if any(int(r["kind_code_n"]) != kind or int(r["role_code_n"]) != role for _, r in pts):
            return [f"step {step_id}: entity {e_idx} changes kind/role between checkpoints"]
        xz = [(t, float(r["pos_x_m"]), float(r["pos_z_m"])) for t, r in pts]
        subs = [math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(xz, xz[1:])]
        if kind == 4 and any(int(r["wardrobe_n"]) != spec["wardrobe_per_actor_n"] for _, r in pts):
            out.append(f"step {step_id}: actor {e_idx} wardrobe_n != {spec['wardrobe_per_actor_n']}")
            break
        if kind == 4 and role == 1:
            roam_seen += 1
            if any(d < ROAM_SUBSTEP_MIN_M for d in subs):
                out.append(
                    f"step {step_id}: roam actor {e_idx} stalled during 5 s sub-step (min={min(subs):.3f} m < {ROAM_SUBSTEP_MIN_M} m)"
                )
                break
            for q, (a, b) in enumerate(bounds, start=1):
                q_dist = _path_len(xz, a, b)
                if q_dist < ROAM_QUARTER_MIN_M:
                    out.append(f"step {step_id}: roam actor {e_idx} Q{q} displacement {q_dist:.2f} m < {ROAM_QUARTER_MIN_M} m")
                    break
            if out:
                break
            total = _path_len(xz, t0, t_end)
            legs = _interp([(t, float(r["wp_legs_n"])) for t, r in pts], t_end) - _interp(
                [(t, float(r["wp_legs_n"])) for t, r in pts], t0
            )
            if total < ROAM_TOTAL_MIN_M or legs < ROAM_MIN_WP_LEGS - 1e-9:
                out.append(
                    f"step {step_id}: roam actor {e_idx} 60 s total_dist={total:.2f} m (< {ROAM_TOTAL_MIN_M}) or wp_legs={legs:.1f} (< {ROAM_MIN_WP_LEGS})"
                )
                break
        elif kind == 4 and role == 2:
            emote_seen += 1
            for i, (_, s) in enumerate(pts):
                if (
                    int(s["emote_playing_b"]) != 1
                    or int(s["emote_cb_id_n"]) != EMOTE_CB_CMD_CLAP
                    or int(s["emote_cb_state_n"]) <= 0
                ):
                    out.append(
                        f"step {step_id}: emote actor {e_idx} inactive at cp={i} (playing={s['emote_playing_b']}, cb_id={s['emote_cb_id_n']}, state={s['emote_cb_state_n']})"
                    )
                    break
                if i > 0:
                    prev_t, cur_t = int(pts[i - 1][1]["emote_active_ticks_n"]), int(s["emote_active_ticks_n"])
                    if cur_t - prev_t < 3:
                        out.append(
                            f"step {step_id}: emote actor {e_idx} active_ticks stalled between cp={i - 1} and cp={i} ({prev_t} -> {cur_t})"
                        )
                        break
            if out:
                break
            comp = [(t, float(r["emote_completions_n"])) for t, r in pts]
            for q, (a, b) in enumerate(bounds, start=1):
                q_comp = _interp(comp, b) - _interp(comp, a)
                if q_comp < EMOTE_QUARTER_MIN_COMPLETIONS - 1e-9:
                    out.append(f"step {step_id}: emote actor {e_idx} Q{q} completions={q_comp:.1f} < {EMOTE_QUARTER_MIN_COMPLETIONS}")
                    break
            if out:
                break
            tot_comp = _interp(comp, t_end) - _interp(comp, t0)
            if tot_comp < EMOTE_TOTAL_MIN_COMPLETIONS - 1e-9:
                out.append(f"step {step_id}: emote actor {e_idx} total completions={tot_comp:.1f} < {EMOTE_TOTAL_MIN_COMPLETIONS}")
                break
        elif kind in (2, 3):
            creature_seen += 1
            if any(int(r["ai_agent_b"]) != 1 for _, r in pts):
                out.append(f"step {step_id}: creature {e_idx} ai_agent_b != 1")
                break
            if any(d <= 0.01 for d in subs):
                out.append(f"step {step_id}: creature {e_idx} stationary during 5 s sub-step (min={min(subs):.4f} m)")
                break
            for q, (a, b) in enumerate(bounds, start=1):
                q_dist = _path_len(xz, a, b)
                if q_dist < CREATURES_QUARTER_MIN_M:
                    out.append(f"step {step_id}: creature {e_idx} Q{q} displacement {q_dist:.3f} m < {CREATURES_QUARTER_MIN_M} m")
                    break
            if out:
                break
            tot = _path_len(xz, t0, t_end)
            if tot < CREATURES_TOTAL_MIN_M:
                out.append(f"step {step_id}: creature {e_idx} 60 s displacement {tot:.3f} m < {CREATURES_TOTAL_MIN_M} m")
                break
    if not out:
        exp = ((spec["actors_n"] + 1) // 2, spec["actors_n"] // 2, spec["infected_n"] + spec["animals_n"])
        if (roam_seen, emote_seen, creature_seen) != exp:
            out.append(f"step {step_id}: role counts in snap ({roam_seen} roam, {emote_seen} emote, {creature_seen} creatures) != expected {exp}")
    return out


def _budget_guard_excess(req_num: dict[str, Any]) -> dict[str, int]:
    """For every A6 guard, how far the candidate is over its limit (<= 0 means within it)."""
    g = lambda k: int(req_num.get(k, 0))  # noqa: E731
    roots = g("cand_objects_n") + g("cand_infected_n") + g("cand_animals_n") + g("cand_actors_n")
    children = g("cand_wardrobe_total_n") + g("cand_extra_children_n")
    return {
        "budget_exceeded:objects": g("cand_objects_n") - g("max_objects_n"),
        "budget_exceeded:infected": g("cand_infected_n") - g("max_infected_n"),
        "budget_exceeded:animals": g("cand_animals_n") - g("max_animals_n"),
        "budget_exceeded:actors": g("cand_actors_n") - g("max_actors_n"),
        "budget_exceeded:wardrobe_per_actor": g("cand_wardrobe_max_per_actor_n") - g("max_wardrobe_per_actor_n"),
        "budget_exceeded:children_total": children - g("max_children_n"),
        "budget_exceeded:combined_roots": roots - g("max_combined_roots_n"),
        "budget_exceeded:combined_entities": roots + children - g("max_combined_entities_n"),
    }


N5_MAX_KEYS = (
    "max_objects_n",
    "max_infected_n",
    "max_animals_n",
    "max_actors_n",
    "max_wardrobe_per_actor_n",
    "max_children_n",
    "max_combined_roots_n",
    "max_combined_entities_n",
)


def n5_stimulus_matches(reason: str, req_num: dict[str, Any], cap: dict[str, int]) -> str | None:
    """Does `req_num` isolate exactly the guard `reason` against the certified cap `cap` (a STEP_SPEC
    entry), by exactly one unit? Returns None when it does, else why not (BLOQ 10)."""
    cap_max = {
        "max_objects_n": cap["objects_n"],
        "max_infected_n": cap["infected_n"],
        "max_animals_n": cap["animals_n"],
        "max_actors_n": cap["actors_n"],
        "max_wardrobe_per_actor_n": cap["wardrobe_per_actor_n"],
        "max_children_n": cap["children_n"],
        "max_combined_roots_n": cap["roots_n"],
        "max_combined_entities_n": cap["entities_n"],
    }
    expect = dict(cap_max)
    if reason == "budget_exceeded:combined_roots":
        expect["max_combined_roots_n"] = cap["roots_n"] - 1
    if reason == "budget_exceeded:combined_entities":
        expect["max_combined_entities_n"] = cap["entities_n"] - 1
    for k in N5_MAX_KEYS:
        if k not in req_num or int(req_num[k]) != expect[k]:
            return f"{k}={req_num.get(k)} != {expect[k]} (cap of the certified step)"
    excess = _budget_guard_excess(req_num)
    over = sorted(r for r, v in excess.items() if v > 0)
    if over != [reason]:
        return f"stimulus violates {over or 'no guard'} instead of only {reason}"
    if excess[reason] != 1:
        return f"stimulus exceeds {reason} by {excess[reason]} (must be exactly +1)"
    if reason == "budget_exceeded:wardrobe_per_actor":
        if int(req_num.get("cand_actors_n", 0)) < 1:
            return "wardrobe_per_actor stimulus needs at least 1 actor"
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
            INCONCLUSO,
            checks=_checks_out(checks, reasons),
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
            INCONCLUSO,
            checks=_checks_out(checks, reasons),
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
            FALLA,
            checks=_checks_out(checks, reasons),
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
            INCONCLUSO,
            checks=_checks_out(checks, reasons),
            metrics=metrics,
            reasons=reasons,
        )

    # Parse and anti-fabrication check on every bridge record (E9)
    raw_records, merge_violations = _merge_core_events(raw_records)
    seen_op_ids: set[str] = set()
    ops: list[dict[str, Any]] = []
    prf01_violations: list[str] = []
    prf02_violations: list[str] = []
    prf03_violations: list[str] = []
    prf04_violations: list[str] = []
    prf05_violations: list[str] = []
    prf06_violations: list[str] = []
    transport_failures: list[str] = []
    transport_failed_verbs: set[str] = set()

    prf01_violations.extend(merge_violations)
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
            transport_failed_verbs.add(verb)
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
    # Organize the server operations into INSTANCES (Sol r1 BLOQ 7): every non-cleanup
    # perf_step_apply opens one, with its own windows, checkpoints and actor orders. Nothing is
    # replaced by a later apply of the same step: every present instance is evaluated.
    # -----------------------------------------------------------------------
    instances: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    job_reads_by_id: dict[str, list[dict[str, Any]]] = {}
    job_frees_by_id: set[str] = set()
    job_free_idx: dict[str, int] = {}
    job_inst: dict[str, dict[str, Any]] = {}
    all_snap_ops: list[dict[str, Any]] = []
    budget_check_ops: list[dict[str, Any]] = []
    cleanup_ops: list[dict[str, Any]] = []
    act_ops: list[dict[str, Any]] = []
    start_records: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

    def _new_instance(step: str, apply_op: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "step": step,
            "apply": apply_op,
            "windows": [],
            "snaps": [],
            "cps": [],
            "acts": [],
            "window_open": False,
            "closed": False,
            "ok02": False,
        }

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
            if cur is not None and not cur["closed"]:
                cur["acts"].append(op)
            if op["status"] != "done":
                prf02_violations.append(
                    f"op {op['op_id']} ({verb}): S3 actor command failed ({op['status']}/{op['reason']})"
                )

        elif verb == "perf_step_apply":
            raw_step = req_str.get("step_id") or p_str.get("step_id", "")
            step_id = _normalize_step_id(raw_step)
            if step_id == "cleanup":
                cleanup_ops.append(op)
                cur = None
            elif step_id in STEP_SPEC:
                cur = _new_instance(step_id, op)
                instances.append(cur)
            elif op["status"] == "done":
                prf02_violations.append(f"op {op['op_id']}: unknown step_id {raw_step!r}")

        elif verb == "perf_window_start":
            raw_step = p_str.get("step_id") or req_str.get("step_id", "")
            step_id = _normalize_step_id(raw_step)
            start_records.append((op, cur))
            if (
                op["status"] == "done"
                and not _start_is_neg_probe(op, step_id)
                and cur is not None
                and cur["step"] == step_id
            ):
                cur["window_open"] = True
                if p_str.get("job"):
                    job_inst[p_str["job"]] = cur

        elif verb in ("job_read", "poll_job"):
            job_id = req_str.get("job") or p_str.get("job", "")
            if job_id:
                job_reads_by_id.setdefault(job_id, []).append(op)
                if (
                    op["status"] == "done"
                    and p_str.get("state") in TERMINAL_STATES
                    and job_id in job_inst
                ):
                    job_inst[job_id]["closed"] = True

        elif verb == "job_free":
            job_id = req_str.get("job") or p_str.get("job", "")
            if job_id and op["status"] == "done":
                job_frees_by_id.add(job_id)
                job_free_idx.setdefault(job_id, op["idx"])
                if job_id in job_inst:
                    job_inst[job_id]["closed"] = True

        elif verb == "perf_snap":
            all_snap_ops.append(op)
            raw_step = req_str.get("step_id") or p_str.get("step_id", "")
            step_id = _normalize_step_id(raw_step)
            # A snapshot is a checkpoint of an instance only while its measured window is open
            # (after the window start, before its terminal read); the label alone is a probe
            # string. Snapshots outside any window (post-N5, N6, closure) are not checkpoints.
            inj_b = int(req_num.get("inject_foreign_cargo_b", p_num.get("foreign_injected_b", 0)))
            if (
                inj_b == 0
                and op["status"] == "done"
                and cur is not None
                and cur["window_open"]
                and not cur["closed"]
            ):
                if step_id != cur["step"]:
                    prf02_violations.append(
                        f"op {op['op_id']}: perf_snap labelled {step_id!r} taken while step {cur['step']!r} is applied"
                    )
                else:
                    cur["snaps"].append(op)

        elif verb == "perf_budget_check":
            budget_check_ops.append(op)

    # Combine multi-page perf_snap calls that belong to the same checkpoint (page_n == 0 starts a checkpoint)
    for inst in instances:
        merged_cps: list[dict[str, Any]] = []
        for sop in inst["snaps"]:
            p_num = sop["payload"]["num"]
            page_n = int(p_num.get("page_n", 0))
            pages_n = int(p_num.get("pages_n", 1))
            rows = list(sop["payload"]["rows"])
            if page_n == 0 or not merged_cps:
                merged_cps.append(
                    {
                        "op_id": sop["op_id"],
                        "idx": sop["idx"],
                        "tick_ms": float(p_num.get("tick_ms", 0.0)),
                        "h_ms": _mid_h_ms(sop),
                        "frame": int(p_num.get("frame", 0)),
                        "pages_expected": pages_n,
                        "pages_seen": {page_n},
                        "num": dict(p_num),
                        "str": dict(sop["payload"]["str"]),
                        "rows": rows,
                    }
                )
            else:
                cur_cp = merged_cps[-1]
                cur_cp["pages_seen"].add(page_n)
                cur_cp["rows"].extend(rows)
        inst["cps"] = merged_cps

    # Assemble window datasets from perf_window_start + job_read. State and marks come ONLY from
    # the raw job_read results of the core's bridge log (Sol r1 BLOQ 1): no auxiliary file
    # (step_<step>_polls.jsonl, technical.json) can substitute them.
    all_windows: list[dict[str, Any]] = []
    n1a_brief_windows: list[dict[str, Any]] = []
    n1b_modset_rejects: list[dict[str, Any]] = []
    technical_window_missing = False
    dup_row_violations: list[str] = []

    for w_op, w_cur in start_records:
        req_str = w_op["req"]["str"]
        req_num = w_op["req"]["num"]
        step_id = _normalize_step_id(w_op["payload"]["str"].get("step_id") or req_str.get("step_id", ""))
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
        merged_rows_by_seq: dict[int, dict[str, Any]] = {}
        raw_rows_list: list[dict[str, Any]] = []
        terminal_state = p_str.get("state", "running")
        terminal_num: dict[str, Any] = {}

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
            if st in TERMINAL_STATES:
                terminal_state = st
                terminal_num.update(rp_num)
            seen_in_read: set[int] = set()
            for row in r_op["payload"]["rows"]:
                if "seq_n" in row and _is_finite_number(row["seq_n"]):
                    s_idx = int(row["seq_n"])
                    if s_idx in seen_in_read:
                        dup_row_violations.append(
                            f"step {step_id}: duplicate window row seq_n={s_idx} inside one job_read (op {r_op['op_id']})"
                        )
                    seen_in_read.add(s_idx)
                    if s_idx not in merged_rows_by_seq:
                        merged_rows_by_seq[s_idx] = row
                        raw_rows_list.append(row)
                    elif merged_rows_by_seq[s_idx] != row:
                        dup_row_violations.append(
                            f"step {step_id}: window row seq_n={s_idx} differs between two reads of the job"
                        )
                else:
                    raw_rows_list.append(row)

        w_info = {
            "step_id": step_id,
            "job_id": job_id,
            "op_id": w_op["op_id"],
            "idx": w_op["idx"],
            "start_tick_ms": float(p_num.get("start_tick_ms", 0.0)),
            "start_frame": int(p_num.get("start_frame", 0)),
            "warmup_ms": float(p_num.get("warmup_ms", req_num.get("warmup_ms", 0.0))),
            "duration_ms": float(p_num.get("duration_ms", req_num.get("duration_ms", 0.0))),
            "sample_step_ms": float(p_num.get("sample_step_ms", req_num.get("sample_step_ms", 0.0))),
            "expected_rows_n": int(p_num.get("expected_rows_n", 61)),
            "terminal_state": terminal_state,
            "terminal_num": terminal_num,
            "rows": raw_rows_list,
            "freed": job_id in job_frees_by_id,
            "ok03": False,
            "ok04": False,
            "inst": None,
        }

        if _start_is_neg_probe(w_op, step_id):
            n1a_brief_windows.append(w_info)
        else:
            inst = w_cur if (w_cur is not None and w_cur["step"] == step_id) else None
            if inst is None:
                inst = _new_instance(step_id, None)
                instances.append(inst)
            inst["windows"].append(w_info)
            w_info["inst"] = inst
            all_windows.append(w_info)

    # -----------------------------------------------------------------------
    # PRF-03: warmup_and_window_completeness
    # -----------------------------------------------------------------------
    prf03_technical = False

    # Every successful perf_window_start must carry the contractual resource (Sol r1 BLOQ 6):
    # the concurrency guard cannot depend on a label the probe may omit. And two jobs of the verb
    # alive at once are only legitimate after the previous one was read terminal or freed.
    sampler_starts = sorted(
        (w_op for w_op, _ in start_records if w_op["status"] == "done"),
        key=lambda o: o["idx"],
    )
    for pos, w_op in enumerate(sampler_starts):
        resource = w_op["payload"]["str"].get("resource")
        if resource != "perf_sampler":
            prf03_violations.append(
                f"op {w_op['op_id']} ({w_op['payload']['str'].get('step_id', '?')}): perf_window_start answered "
                f"done with resource={resource!r}, not the contractual 'perf_sampler'"
            )
        if pos == 0:
            continue
        prev = sampler_starts[pos - 1]
        prev_job = prev["payload"]["str"].get("job", "")
        closed = any(
            r["status"] == "done"
            and r["payload"]["str"].get("state") in TERMINAL_STATES
            and prev["idx"] < r["idx"] < w_op["idx"]
            for r in job_reads_by_id.get(prev_job, [])
        ) or (prev_job in job_free_idx and prev["idx"] < job_free_idx[prev_job] < w_op["idx"])
        if not closed:
            prf03_violations.append(
                f"op {w_op['op_id']} ({w_op['payload']['str'].get('step_id', '?')}): concurrent perf_sampler job "
                f"started while previous job {prev_job!r} was not terminal or freed"
            )

    def _check_window_prf03(w_info: dict[str, Any]) -> bool:
        """All PRF-03 predicates of one window; appends its violations and returns True if clean."""
        nonlocal prf03_technical
        step_id = w_info["step_id"]
        t_state = w_info["terminal_state"]
        rows = w_info["rows"]
        t_num = w_info["terminal_num"]
        rows_total_n = int(t_num.get("rows_total_n", len(rows)))
        before = len(prf03_violations)

        # Non-done terminal states (stopped, failed, expired) are technical failures -> INCONCLUSO
        if t_state in ("stopped", "failed", "expired", "running"):
            prf03_technical = True
            reasons.append(
                f"PRF-03 technical: step {step_id!r} job {w_info['job_id']!r} ended in state={t_state!r}"
            )
            return False

        # Terminal 'done' with < 61 samples is a completeness FAILURE (insufficient_samples)
        if rows_total_n < EXPECTED_WINDOW_ROWS or len(rows) < EXPECTED_WINDOW_ROWS:
            prf03_violations.append(
                f"step {step_id}: insufficient_samples (rows_total_n={rows_total_n}, rows={len(rows)} < {EXPECTED_WINDOW_ROWS})"
            )
            return False

        if w_info["warmup_ms"] < WARMUP_MIN_MS:
            prf03_violations.append(f"step {step_id}: warmup_ms={w_info['warmup_ms']} < {WARMUP_MIN_MS}")
        if w_info["duration_ms"] < WINDOW_MIN_MS:
            prf03_violations.append(f"step {step_id}: duration_ms={w_info['duration_ms']} < {WINDOW_MIN_MS}")
        if w_info["sample_step_ms"] != SAMPLE_STEP_MS:
            prf03_violations.append(
                f"step {step_id}: sample_step_ms={w_info['sample_step_ms']} != {SAMPLE_STEP_MS}"
            )

        for r_idx, r in enumerate(rows):
            for col in WINDOW_NCOL:
                if col not in r or not _is_finite_number(r[col]):
                    prf03_violations.append(f"step {step_id}: row[{r_idx}] missing or non-finite column {col!r}")
                    return False

        seqs = [int(r["seq_n"]) for r in rows]
        if seqs != list(range(len(rows))):
            prf03_violations.append(f"step {step_id}: seq_n not contiguous 0..{len(rows) - 1}")
            return False

        first_tick = float(rows[0]["tick_ms"])
        last_tick = float(rows[-1]["tick_ms"])
        warmup_obs = first_tick - w_info["start_tick_ms"]
        if warmup_obs < WARMUP_MIN_MS:
            prf03_violations.append(f"step {step_id}: effective warmup {warmup_obs:.1f} ms < {WARMUP_MIN_MS} ms")

        span_ms = last_tick - first_tick
        if span_ms < WINDOW_MIN_MS or span_ms > WINDOW_MAX_MS:
            prf03_violations.append(
                f"step {step_id}: window span {span_ms:.1f} ms outside [{WINDOW_MIN_MS}, {WINDOW_MAX_MS}] ms"
            )

        for i in range(1, len(rows)):
            dt = float(rows[i]["tick_ms"]) - float(rows[i - 1]["tick_ms"])
            df = int(rows[i]["frame"]) - int(rows[i - 1]["frame"])
            ddt = float(rows[i]["dtsum_ms"]) - float(rows[i - 1]["dtsum_ms"])
            if dt < SAMPLE_DT_MIN_MS or dt > SAMPLE_DT_MAX_MS:
                prf03_violations.append(
                    f"step {step_id}: sample interval dt[{i}]={dt:.1f} ms outside [{SAMPLE_DT_MIN_MS}, {SAMPLE_DT_MAX_MS}] ms"
                )
                return False
            if df <= 0 or ddt <= 0.0:
                prf03_violations.append(
                    f"step {step_id}: non-increasing frame or dtsum_ms at seq {i} (df={df}, ddt={ddt})"
                )
                return False

        end_t = t_num.get("end_tick_ms")
        onjobend_t = t_num.get("onjobend_tick_ms")
        released_t = t_num.get("released_tick_ms")
        if not (_is_finite_number(end_t) and _is_finite_number(onjobend_t) and _is_finite_number(released_t)):
            prf03_violations.append(
                f"step {step_id}: missing job lifecycle marks (end={end_t}, onjobend={onjobend_t}, released={released_t})"
            )
            return False
        if not (last_tick <= float(end_t) <= float(onjobend_t) <= float(released_t)):
            prf03_violations.append(
                f"step {step_id}: invalid job lifecycle order (last_tick={last_tick}, end={end_t}, onjobend={onjobend_t}, released={released_t})"
            )
            return False
        return len(prf03_violations) == before

    for w_info in all_windows:
        w_info["ok03"] = _check_window_prf03(w_info)

    # N1a (1-sample probe window) is a negative of the product audited by PRF-06 (brief section 6), not a PRF-03 window.

    prf03_violations.extend(dup_row_violations)
    steps_windows: dict[str, list[dict[str, Any]]] = {}
    for w_info in all_windows:
        steps_windows.setdefault(w_info["step_id"], []).append(w_info)
    valid_prf03_steps: set[str] = {s for s, ws in steps_windows.items() if all(w["ok03"] for w in ws)}
    if prf03_violations:
        checks["PRF-03"] = "fail"
        reasons.extend(f"PRF-03: {v}" for v in prf03_violations)
    elif valid_prf03_steps and not prf03_technical:
        checks["PRF-03"] = "pass"
    else:
        checks["PRF-03"] = "missing"

    # -----------------------------------------------------------------------
    # PRF-04: dual_source_fps_agreement
    # -----------------------------------------------------------------------
    step_fps_all: dict[str, list[dict[str, float]]] = {}

    for w_info in all_windows:
        step_id = w_info["step_id"]
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

        # Harness clock (Sol r1 BLOQ 2): the interval is the one the core credited, anchored to the
        # measured window: first and last checkpoint of THIS window, with the harness instants
        # taken from the bridge's deliver/result events and the server ticks from the snapshots.
        # No checkpoints covering the window means no evidence -> not pass (missing), never skipped.
        h_drift = None
        cps = w_info["inst"]["cps"] if w_info["inst"] is not None else []
        if len(cps) >= 2:
            t0, t_end = float(rows[0]["tick_ms"]), float(rows[-1]["tick_ms"])
            c0, c1 = cps[0], cps[-1]
            if (
                c0["tick_ms"] <= t0 + CP_ANCHOR_TOL_MS
                and c1["tick_ms"] >= t_end - CP_ANCHOR_TOL_MS
                and c1["tick_ms"] > c0["tick_ms"]
            ):
                tick_span = c1["tick_ms"] - c0["tick_ms"]
                h_drift = abs((c1["h_ms"] - c0["h_ms"]) - tick_span) / tick_span

        info = {
            "fps_window_mean_raw": fps_window_mean,
            "fps_frame_counter_raw": fps_frame_counter,
            "fps_window_mean": round(fps_window_mean, 4),
            "fps_frame_counter": round(fps_frame_counter, 4),
            "fps_roll5_min": round(fps_roll5_min, 4),
            "fps_rel_diff": round(rel_diff_fps, 6),
            "dtsum_drift": round(dtsum_drift, 6),
            "h_ms_drift": None if h_drift is None else round(h_drift, 6),
        }
        w_info["fps"] = info
        step_fps_all.setdefault(step_id, []).append(info)

        step_failed_04 = False
        if rel_diff_fps > FPS_REL_TOL:
            prf04_violations.append(
                f"step {step_id}: FPS disagreement {rel_diff_fps:.4f} > {FPS_REL_TOL} (mean={fps_window_mean:.2f}, counter={fps_frame_counter:.2f})"
            )
            step_failed_04 = True
        if dtsum_drift > DTSUM_DRIFT_TOL:
            prf04_violations.append(f"step {step_id}: dtsum drift {dtsum_drift:.4f} > {DTSUM_DRIFT_TOL}")
            step_failed_04 = True
        if h_drift is not None and h_drift > HARNESS_DRIFT_TOL:
            prf04_violations.append(f"step {step_id}: harness clock drift {h_drift:.4f} > {HARNESS_DRIFT_TOL}")
            step_failed_04 = True

        if not step_failed_04 and h_drift is not None:
            w_info["ok04"] = True

    # Per step, the most conservative window (lowest mean) feeds the certified numbers.
    step_fps_metrics: dict[str, dict[str, float]] = {
        s: min(infos, key=lambda i: i["fps_window_mean_raw"]) for s, infos in step_fps_all.items()
    }
    if step_fps_metrics:
        metrics["step_fps"] = {
            s: {k: v for k, v in m.items() if not k.endswith("_raw")} for s, m in step_fps_metrics.items()
        }

    valid_prf04_steps: set[str] = {s for s, ws in steps_windows.items() if all(w["ok04"] for w in ws)}
    if prf04_violations:
        checks["PRF-04"] = "fail"
        reasons.extend(f"PRF-04: {v}" for v in prf04_violations)
    elif valid_prf04_steps and not prf03_technical:
        checks["PRF-04"] = "pass"
    else:
        checks["PRF-04"] = "missing"

    # -----------------------------------------------------------------------
    # PRF-02: step_loads_and_continuous_activity (one verdict per instance)
    # -----------------------------------------------------------------------
    actor_driver_missing = bool(
        technical_data and technical_data.get("reason") == "actor_driver_unavailable"
    )

    for inst in sorted(instances, key=lambda i: STEP_ORDER.index(i["step"])):
        step_id = inst["step"]
        spec = STEP_SPEC[step_id]
        iv: list[str] = []  # this instance's violations
        if spec["actors_n"] > 0 and actor_driver_missing:
            reasons.append(f"PRF-02 technical: actor_driver_unavailable on step {step_id!r}")
            continue

        apply_op = inst["apply"]
        if apply_op is None:
            if "perf_step_apply" in transport_failed_verbs:
                reasons.append(f"PRF-02 technical: perf_step_apply for step {step_id!r} lost or timed out")
            else:
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

        for cat in ("objects", "infected", "animals", "actors"):
            exp_val = spec[f"{cat}_n"]
            # The order comes from the core's enq record, the observation from the peer's
            # *_alive_n reading; a missing observation is NOT replaced by the requested echo.
            req_val = req_num.get(f"{cat}_n")
            alive_val = ap_num.get(f"{cat}_alive_n")
            if req_val != exp_val or alive_val != exp_val:
                iv.append(f"step {step_id}: {cat} count mismatch (expected={exp_val}, req={req_val}, alive={alive_val})")
        for key, exp in (("roots_alive_n", spec["roots_n"]), ("children_alive_n", spec["children_n"]), ("entities_alive_n", spec["entities_n"])):
            if ap_num.get(key) != exp:
                iv.append(f"step {step_id}: {key}={ap_num.get(key)} != {exp}")
        if ap_num.get("director_allow_damage_b") != 0:
            iv.append(f"step {step_id}: director_allow_damage_b={ap_num.get('director_allow_damage_b')} != 0")

        # Check spawn flags (#11)
        if spec["objects_n"] > 0:
            flags_obj = int(ap_num.get("spawn_flags_obj_n", 0))
            if flags_obj != SPAWN_FLAGS_OBJ or (flags_obj & FORBIDDEN_SPAWN_FLAG) != 0:
                iv.append(f"step {step_id}: invalid spawn_flags_obj_n={flags_obj} (expected {SPAWN_FLAGS_OBJ})")
        if (spec["infected_n"] + spec["animals_n"] + spec["actors_n"]) > 0:
            flags_ai = int(ap_num.get("spawn_flags_ai_n", 0))
            if flags_ai != SPAWN_FLAGS_AI or (flags_ai & FORBIDDEN_SPAWN_FLAG) != 0:
                iv.append(f"step {step_id}: invalid spawn_flags_ai_n={flags_ai} (expected {SPAWN_FLAGS_AI})")

        # 1 Hz window rows: continuous per-second activity (Arbitraje N3 & N5), every window of the instance
        exp_roam_actors = (spec["actors_n"] + 1) // 2
        exp_emote_actors = spec["actors_n"] // 2
        exp_creatures = spec["infected_n"] + spec["animals_n"]
        for w_info in inst["windows"]:
            rows = w_info["rows"]
            for r_idx, r in enumerate(rows):
                if any(c not in r or not _is_finite_number(r[c]) for c in WINDOW_NCOL):
                    iv.append(f"step {step_id}: row[{r_idx}] missing activity columns")
                    break
                if int(r["alive_roots_n"]) != spec["roots_n"]:
                    iv.append(f"step {step_id}: row[{r_idx}] alive_roots_n={r['alive_roots_n']} != {spec['roots_n']}")
                    break
                if int(r["alive_wardrobe_n"]) != spec["children_n"]:
                    iv.append(f"step {step_id}: row[{r_idx}] alive_wardrobe_n={r['alive_wardrobe_n']} != {spec['children_n']}")
                    break
                seq_n = int(r["seq_n"])
                if seq_n >= 1 and spec["k"] >= 1:
                    if exp_roam_actors > 0 and (
                        float(r["roam_min_step_m"]) < ROAM_MIN_STEP_M or float(r["roam_disp_step_m"]) < ROAM_MIN_STEP_M
                    ):
                        iv.append(f"step {step_id}: seq={seq_n} roam_min_step_m={r['roam_min_step_m']} < {ROAM_MIN_STEP_M}")
                        break
                    if exp_emote_actors > 0 and (
                        int(r["emote_active_actors_n"]) != exp_emote_actors
                        or int(r["emote_cb_cmd1101_actors_n"]) != exp_emote_actors
                    ):
                        iv.append(
                            f"step {step_id}: seq={seq_n} emote callback 1101 inactive (active={r['emote_active_actors_n']}, cb1101={r['emote_cb_cmd1101_actors_n']}, expected={exp_emote_actors})"
                        )
                        break
                    if exp_creatures > 0 and (
                        int(r["creatures_moved_step_n"]) != exp_creatures
                        or float(r["creatures_min_step_m"]) < CREATURES_MIN_STEP_M
                    ):
                        iv.append(
                            f"step {step_id}: seq={seq_n} creature step movement below minimum (moved={r['creatures_moved_step_n']}/{exp_creatures}, min_step={r['creatures_min_step_m']} < {CREATURES_MIN_STEP_M})"
                        )
                        break

        # Checkpoints (cp = 0..12): counts, identities and activity, bound to the window by server time
        w_last = inst["windows"][-1] if inst["windows"] else None
        full_window = w_last is not None and len(w_last["rows"]) >= EXPECTED_WINDOW_ROWS
        cps = inst["cps"]
        anchored = False
        t0 = t_end = 0.0
        if (
            w_last is not None
            and len(w_last["rows"]) >= 2
            and all(_is_finite_number(r.get("tick_ms")) for r in (w_last["rows"][0], w_last["rows"][-1]))
        ):
            t0, t_end = float(w_last["rows"][0]["tick_ms"]), float(w_last["rows"][-1]["tick_ms"])
            anchored = t_end > t0
        if not cps:
            if full_window and not iv:
                iv.append(f"step {step_id}: missing perf_snap checkpoints (0/{EXPECTED_SNAP_CHECKPOINTS})")
        else:
            if len(cps) < EXPECTED_SNAP_CHECKPOINTS:
                iv.append(f"step {step_id}: insufficient perf_snap checkpoints ({len(cps)} < {EXPECTED_SNAP_CHECKPOINTS})")
            if anchored:
                iv.extend(f"step {step_id}: {v}" for v in _cp_time_violations(cps, t0, t_end))
            else:
                iv.append(f"step {step_id}: checkpoints cannot be anchored to a measured window (no usable window rows)")
            cp_bad = False
            for cp_idx, cp in enumerate(cps):
                cp_num = cp["num"]
                if cp_num.get("director_allow_damage_b") != 0:
                    iv.append(f"step {step_id} cp={cp_idx}: director_allow_damage_b != 0")
                    cp_bad = True
                if cp_num.get("roots_alive_n") != spec["roots_n"]:
                    iv.append(f"step {step_id} cp={cp_idx}: roots_alive_n={cp_num.get('roots_alive_n')} != {spec['roots_n']}")
                    cp_bad = True
                if cp_num.get("children_alive_n") != spec["children_n"]:
                    iv.append(f"step {step_id} cp={cp_idx}: children_alive_n={cp_num.get('children_alive_n')} != {spec['children_n']}")
                    cp_bad = True
                if cp_num.get("census_foreign_n", 0) != 0:
                    iv.append(f"step {step_id} cp={cp_idx}: unexpected foreign entity in census ({cp_num.get('census_foreign_n')})")
                    cp_bad = True
                row_viol = _cp_rows_violations(spec, cp_idx, cp)
                if row_viol:
                    iv.extend(f"step {step_id} {v}" for v in row_viol)
                    cp_bad = True
                if cp_bad:
                    break
            if (
                not cp_bad
                and not iv
                and spec["k"] >= 1
                and len(cps) >= EXPECTED_SNAP_CHECKPOINTS
                and anchored
            ):
                iv.extend(_cp_activity_violations(step_id, spec, cps, t0, t_end))

        # Actor driving must be evidenced through the certified S3 adapter (Sol r1 BLOQ 13): the
        # profile exports the S3 regime, so a step with actors needs act_* orders that reached them.
        acts_ok = True
        if spec["actors_n"] > 0 and not iv and full_window:
            if not any(a["status"] == "done" for a in inst["acts"]):
                acts_ok = False
                reasons.append(
                    f"PRF-02 technical: actor_driver_unavailable: no act_* order of the S3 adapter drove the actors of step {step_id!r}"
                )

        prf02_violations.extend(iv)
        inst["ok02"] = not iv and full_window and acts_ok

    steps_instances: dict[str, list[dict[str, Any]]] = {}
    for inst in instances:
        steps_instances.setdefault(inst["step"], []).append(inst)
    valid_prf02_steps: set[str] = {
        s for s, ins in steps_instances.items() if all(i["ok02"] for i in ins)
    }
    acts_missing_somewhere = any(
        r.startswith("PRF-02 technical: actor_driver_unavailable") for r in reasons
    )
    if prf02_violations:
        checks["PRF-02"] = "fail"
        reasons.extend(f"PRF-02: {v}" for v in prf02_violations)
    elif valid_prf02_steps and not actor_driver_missing and not technical_window_missing and not acts_missing_somewhere:
        checks["PRF-02"] = "pass"
    else:
        checks["PRF-02"] = "missing"

    # -----------------------------------------------------------------------
    # PRF-05: floor_and_combined_budget_derivation
    # -----------------------------------------------------------------------
    cap_spec: dict[str, int] | None = None
    certified_step_id: str | None = None
    if prf03_technical:
        checks["PRF-05"] = "missing"
    else:
        # The approved floor (#28, Q9) applies to fps_window_mean ONLY, unrounded, and only once the
        # dual-source agreement of that step was validated (Sol r1 BLOQ 8): the independent counter
        # is not a second floor.
        for mandatory_step in ("base", "fixture"):
            if mandatory_step in step_fps_metrics and mandatory_step in valid_prf04_steps:
                m_fps = step_fps_metrics[mandatory_step]["fps_window_mean_raw"]
                if m_fps <= FLOOR_FPS:
                    prf05_violations.append(
                        f"step {mandatory_step} below floor (fps_window_mean {m_fps:.4f} <= {FLOOR_FPS} FPS)"
                    )

        steps_up_to_k_valid = {}
        for s_name in ("fixture", "inc1", "inc2"):
            steps_up_to_k_valid[s_name] = (
                s_name in valid_prf02_steps
                and s_name in valid_prf03_steps
                and s_name in valid_prf04_steps
                and s_name in step_fps_metrics
                and step_fps_metrics[s_name]["fps_window_mean_raw"] > FLOOR_FPS
            )

        # Brief §5 PRF-05: k* is derived "con los 4 escalones validos en PRF-01..PRF-04"
        all_four_valid = all(
            s_name in valid_prf02_steps
            and s_name in valid_prf03_steps
            and s_name in valid_prf04_steps
            and s_name in step_fps_metrics
            for s_name in STEP_ORDER
        )

        if not prf05_violations and checks["PRF-01"] == "pass" and all_four_valid:
            k_star = 0
            for s_name in ("fixture", "inc1", "inc2"):
                if steps_up_to_k_valid.get(s_name, False):
                    k_star = STEP_SPEC[s_name]["k"]
                else:
                    break

            if k_star < 1:
                prf05_violations.append("no load step >= fixture met the > 35.0 FPS floor")
            else:
                certified_step_id = {1: "fixture", 2: "inc1", 3: "inc2"}[k_star]
                cap_spec = STEP_SPEC[certified_step_id]

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
                        and int(req_num.get("cand_wardrobe_max_per_actor_n", -1)) == cap_spec["wardrobe_per_actor_n"]
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
                                prf05_violations.append(f"op {bop['op_id']}: budget_at_cap invalid done payload")
                        else:
                            prf05_violations.append(f"op {bop['op_id']}: budget_at_cap rejected ({bop['reason']})")

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
                            # Exported only because the S3 adapter orders were evidenced (PRF-02, BLOQ 13)
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
    # 1. Every perf_budget_check: the verdict must follow the request itself ...
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

    # ... and each of the 8 N5 stimuli must be isolated AGAINST THE CERTIFIED BUDGET (BLOQ 10):
    # a rejection obtained with the limits of another step does not credit the guard.
    anchored_n5: set[str] = set()
    if cap_spec is not None:
        for reason in N5_REQUIRED_REASONS:
            why_not = []
            for bop in budget_check_ops:
                if bop["req"]["str"].get("expected_modset_sig", canonical_modset_sig) != canonical_modset_sig:
                    continue
                if bop["status"] != "rejected" or bop["reason"] != reason:
                    continue
                miss = n5_stimulus_matches(reason, bop["req"]["num"], cap_spec)
                if miss is None:
                    anchored_n5.add(reason)
                    break
                why_not.append(miss)
            if reason not in anchored_n5 and why_not:
                reasons.append(
                    f"PRF-06: N5 {reason} not anchored to the certified budget {certified_step_id!r}: {why_not[0]}"
                )
    all_n5_present = all(r in anchored_n5 for r in N5_REQUIRED_REASONS)

    # 2. N2 (client role rejection on perf_snap or any perf_* verb)
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
                # status == "done" already fails PRF-01; any wrong rejection reason fails PRF-06
                if op["status"] != "done":
                    prf06_violations.append(
                        f"op {op['op_id']}: client {op['verb']} expected rejected/wrong_role:client, got {op['status']}/{op['reason']}"
                    )

    # 3. N1a (1-sample window probe rejected as insufficient_samples and freed)
    n1a_valid = False
    for nw in n1a_brief_windows:
        t_num = nw["terminal_num"]
        r_tot = int(t_num.get("rows_total_n", len(nw["rows"])))
        if nw["terminal_state"] == "done" and r_tot == 1 and len(nw["rows"]) == 1:
            if not nw["freed"]:
                prf06_violations.append(f"op {nw['op_id']}: N1a 1-row job {nw['job_id']!r} was not freed with job_free")
            else:
                n1a_valid = True
        else:
            prf06_violations.append(
                f"op {nw['op_id']}: N1a expected done with 1 row, got state={nw['terminal_state']!r} rows={r_tot}"
            )

    # 4. N1b (modset_mismatch rejection)
    for op in preflight_rejected_ops:
        if op["reason"] == "modset_mismatch":
            n1b_modset_rejects.append(op)
    n1b_valid = len(n1b_modset_rejects) >= 1

    # 5. N4 (area_not_clear): mandatory (Sol r1 BLOQ 9). Stimulus = a canonical preflight (same
    # world, seal, centre and radius as the honest one) so the rejection is about the area and not
    # about the request; the rejection is exact; zero effects is evidenced by the N1-N5 census
    # invariance below, which this rejection must sit inside.
    n4_rejects = [
        op
        for op in preflight_rejected_ops
        if op["reason"] == "area_not_clear" or op["reason"].startswith("area_not_clear:")
    ]
    n4_canonical: list[dict[str, Any]] = []
    for op in n4_rejects:
        rs, rn = op["req"]["str"], op["req"]["num"]
        if (
            rs.get("expected_world") == canonical_world
            and rs.get("expected_modset_sig") == canonical_modset_sig
            and _is_finite_number(rn.get("center_x_m"))
            and _is_finite_number(rn.get("center_z_m"))
            and abs(float(rn["center_x_m"]) - CENTER_POS[0]) < 1e-6
            and abs(float(rn["center_z_m"]) - CENTER_POS[2]) < 1e-6
            and float(rn.get("clear_radius_m", 0.0)) >= CLEAR_RADIUS_M
        ):
            n4_canonical.append(op)
        else:
            prf06_violations.append(
                f"op {op['op_id']}: N4 area_not_clear stimulus is not the canonical preflight request (world/seal/centre/radius)"
            )

    # 6. Pre/Post N1-N5 census invariance BEFORE N6 (S-perf brief §6, N10)
    foreign_inject_ops = [
        op
        for op in all_snap_ops
        if op["peer"] == "server"
        and int(op["req"]["num"].get("inject_foreign_cargo_b", op["payload"]["num"].get("foreign_injected_b", 0))) == 1
    ]
    battery = (
        [x["idx"] for x in n1b_modset_rejects]
        + [x["idx"] for x in n2_client_rejects]
        + [b["idx"] for b in budget_check_ops if b["status"] == "rejected"]
        + [x["idx"] for x in n4_rejects]
        + [w["idx"] for w in n1a_brief_windows]
    )
    pre_post_n5_invariance_ok = False
    pre_idx = post_idx = None
    if battery:
        first_neg_idx, last_neg_idx = min(battery), max(battery)
        first_n6_idx = min((op["idx"] for op in foreign_inject_ops), default=len(raw_records) + 1)
        if last_neg_idx > first_n6_idx:
            prf06_violations.append("N1-N5 negative battery did not finish before N6 foreign cargo injection")
        clean_snaps = [
            op
            for op in all_snap_ops
            if op["peer"] == "server"
            and op["status"] == "done"
            and int(op["payload"]["num"].get("foreign_injected_b", 0)) == 0
        ]
        snaps_before = [op for op in clean_snaps if op["idx"] < first_neg_idx]
        snaps_after = [op for op in clean_snaps if last_neg_idx < op["idx"] < first_n6_idx]
        if snaps_before and snaps_after:
            pre_idx, post_idx = snaps_before[-1]["idx"], snaps_after[0]["idx"]
            pre_s = snaps_before[-1]["payload"]["num"]
            post_s = snaps_after[0]["payload"]["num"]
            inv_ok = True
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
                    inv_ok = False
            pre_post_n5_invariance_ok = inv_ok
        elif n1b_modset_rejects or n2_client_rejects or any(b["status"] == "rejected" for b in budget_check_ops):
            prf06_violations.append(
                "N1-N5 census invariance not shown: needs a server snapshot before the first and another after the last negative (and before N6)"
            )
    n4_valid = bool(n4_canonical) and pre_idx is not None and any(
        pre_idx < op["idx"] < post_idx for op in n4_canonical
    )
    if n4_canonical and pre_idx is not None and not n4_valid:
        prf06_violations.append("N4 area_not_clear rejection lies outside the pre/post census invariance window")

    # 7. N6 (foreign cargo in SeaChest + equipped garment, preserving the actor ancestor), identities and closure
    n6_valid = False
    if foreign_inject_ops:
        n6_before = len(prf06_violations)
        inj_op = foreign_inject_ops[-1]
        if inj_op["status"] != "done":
            prf06_violations.append(f"op {inj_op['op_id']}: perf_snap(inject_foreign_cargo_b=1) failed")
        else:
            inj_num = inj_op["payload"]["num"]
            inj_rows = inj_op["payload"]["rows"]
            inj_sig = inj_num.get("foreign_sig_n")
            if int(inj_num.get("foreign_injected_b", 0)) != 1 or int(inj_num.get("census_foreign_n", 0)) != 2:
                prf06_violations.append(
                    f"op {inj_op['op_id']}: N6 injection did not record foreign_injected_b=1 and census_foreign_n=2 (the two Rag) (got {inj_num.get('census_foreign_n')})"
                )
            if not _is_finite_number(inj_sig) or float(inj_sig) <= 0:
                prf06_violations.append(
                    f"op {inj_op['op_id']}: N6 injection snapshot carries no foreign_sig_n identity of the two Rag"
                )
            # Observed identities of the containers holding the foreign content, before cleanup
            pre_foreign: dict[int, tuple[int, float, float, float]] = {}
            for r in inj_rows:
                if int(r.get("foreign_content_b", 0)) == 1:
                    pre_foreign[int(r["entity_idx_n"])] = (
                        int(r["kind_code_n"]),
                        float(r["pos_x_m"]),
                        float(r["pos_y_m"]),
                        float(r["pos_z_m"]),
                    )
            if len(pre_foreign) != 2 or {k for k, _, _, _ in pre_foreign.values()} != {1, 4}:
                prf06_violations.append(
                    f"op {inj_op['op_id']}: N6 injection snap must mark exactly the SeaChest and the actor with foreign_content_b=1"
                )

            def _same_survivors(snap_op: dict[str, Any], label: str, *, foreign_flag: int) -> None:
                rows_s = snap_op["payload"]["rows"]
                ids_s = {int(r["entity_idx_n"]) for r in rows_s}
                if len(rows_s) != 2 or ids_s != set(pre_foreign):
                    prf06_violations.append(
                        f"op {snap_op['op_id']}: {label}: survivors {sorted(ids_s)} are not the observed identities {sorted(pre_foreign)}"
                    )
                    return
                for r in rows_s:
                    e_idx = int(r["entity_idx_n"])
                    kind0, px, py, pz = pre_foreign[e_idx]
                    dist = math.sqrt(
                        (float(r["pos_x_m"]) - px) ** 2 + (float(r["pos_y_m"]) - py) ** 2 + (float(r["pos_z_m"]) - pz) ** 2
                    )
                    if int(r["kind_code_n"]) != kind0 or dist > 0.05:
                        prf06_violations.append(
                            f"op {snap_op['op_id']}: {label}: entity {e_idx} is not the same object as before cleanup (kind {r['kind_code_n']} vs {kind0}, moved {dist:.3f} m)"
                        )
                    if int(r["alive_b"]) != 1 or int(r["foreign_content_b"]) != foreign_flag:
                        prf06_violations.append(
                            f"op {snap_op['op_id']}: {label}: survivor {e_idx} must have alive_b=1 and foreign_content_b={foreign_flag}"
                        )
                    if int(r["kind_code_n"]) == 4 and int(r["wardrobe_n"]) != 1:
                        prf06_violations.append(
                            f"op {snap_op['op_id']}: {label}: preserved actor {e_idx} must retain exactly the 1 garment with foreign cargo (got wardrobe_n={r['wardrobe_n']})"
                        )

            post_inj_cleanups = [c for c in cleanup_ops if c["idx"] > inj_op["idx"]]
            if not post_inj_cleanups:
                prf06_violations.append("N6: missing cleanup after foreign cargo injection")
            else:
                c1 = post_inj_cleanups[0]
                c1_str = c1["payload"]["str"]
                c1_num = c1["payload"]["num"]
                c2 = post_inj_cleanups[1] if len(post_inj_cleanups) >= 2 else None
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

                    mid_snaps = [
                        s
                        for s in all_snap_ops
                        if s["peer"] == "server"
                        and s["status"] == "done"
                        and s["idx"] > c1["idx"]
                        and (c2 is None or s["idx"] < c2["idx"])
                    ]
                    if not mid_snaps:
                        prf06_violations.append("N6: missing cleanup_snap after partial cleanup")
                    else:
                        cs = mid_snaps[0]
                        cs_num = cs["payload"]["num"]
                        if (
                            int(cs_num.get("roots_alive_n", -1)) != 2
                            or int(cs_num.get("children_alive_n", -1)) != 1
                            or int(cs_num.get("entities_alive_n", -1)) != 3
                            or int(cs_num.get("census_foreign_n", -1)) != int(inj_num.get("census_foreign_n", 2))
                        ):
                            prf06_violations.append(
                                f"op {cs['op_id']}: cleanup_snap counts mismatch (roots={cs_num.get('roots_alive_n')}, children={cs_num.get('children_alive_n')}, foreign={cs_num.get('census_foreign_n')}; the two Rag must survive)"
                            )
                        if _is_finite_number(inj_sig) and cs_num.get("foreign_sig_n") != inj_sig:
                            prf06_violations.append(
                                f"op {cs['op_id']}: the foreign content was destroyed or substituted by cleanup (foreign_sig_n {cs_num.get('foreign_sig_n')} != {inj_sig})"
                            )
                        if cs_num.get("director_allow_damage_b") != cs_num.get("director_orig_allow_damage_b"):
                            prf06_violations.append(
                                f"op {cs['op_id']}: cleanup_snap director_allow_damage_b not restored to original"
                            )
                        _same_survivors(cs, "cleanup_snap", foreign_flag=1)

                    # Bench closure (N10): retirement of BOTH foreign items confirmed, closing
                    # cleanup, and a raw final snapshot with 0 entities. All of it is required.
                    if c2 is None:
                        prf06_violations.append(
                            "N6 closure: missing the cleanup that follows the retirement of the foreign content (bench_reset_foreign)"
                        )
                    else:
                        if len(mid_snaps) < 2:
                            prf06_violations.append(
                                "N6 closure: no snapshot confirms the retirement of both foreign items before the closing cleanup"
                            )
                        else:
                            conf = mid_snaps[-1]
                            cf_num = conf["payload"]["num"]
                            if (
                                int(cf_num.get("census_foreign_n", -1)) != N6_RETIRED_CENSUS
                                or float(cf_num.get("foreign_sig_n", 0) or 0) != 0
                            ):
                                prf06_violations.append(
                                    f"op {conf['op_id']}: retirement not confirmed: census_foreign_n={cf_num.get('census_foreign_n')}, foreign_sig_n={cf_num.get('foreign_sig_n')}"
                                )
                            _same_survivors(conf, "retirement confirmation", foreign_flag=0)
                        c2_str = c2["payload"]["str"]
                        c2_num = c2["payload"]["num"]
                        if (
                            c2["status"] != "done"
                            or c2_str.get("cleanup_status") != "clean"
                            or int(c2_num.get("roots_alive_n", -1)) != 0
                            or int(c2_num.get("children_alive_n", -1)) != 0
                            or int(c2_num.get("entities_alive_n", -1)) != 0
                        ):
                            prf06_violations.append(f"op {c2['op_id']}: bench closure cleanup did not leave 0 entities")
                        snaps_after_c2 = [
                            s
                            for s in all_snap_ops
                            if s["peer"] == "server" and s["status"] == "done" and s["idx"] > c2["idx"]
                        ]
                        if not snaps_after_c2:
                            prf06_violations.append("N6 closure: missing the raw final snapshot with 0 entities after the closing cleanup")
                        else:
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
                            if fs["num"].get("director_allow_damage_b") != fs["num"].get("director_orig_allow_damage_b"):
                                prf06_violations.append("final snapshot: director_allow_damage_b not restored to the cycle original")
        n6_valid = len(prf06_violations) == n6_before

    # Optional samples/final_snap.json can only ADD violations; it never substitutes a raw snapshot
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
                    prf06_violations.append("final_snap.json: director_allow_damage_b != director_orig_allow_damage_b")
        except Exception as exc:
            prf06_violations.append(f"invalid final_snap.json ({exc})")

    # Determine if the complete §6 negative suite + teardown is present and valid
    full_prf06_ready = (
        n1a_valid
        and n1b_valid
        and len(n2_client_rejects) >= 1
        and all_n5_present
        and n4_valid
        and pre_post_n5_invariance_ok
        and n6_valid
    )

    negative_battery_incomplete = False
    has_negative_battery_elements = (
        n1a_brief_windows
        or n1b_modset_rejects
        or n2_client_rejects
        or any(bop["status"] == "rejected" for bop in budget_check_ops)
        or foreign_inject_ops
    )
    if has_negative_battery_elements:
        if n1a_brief_windows and not n1a_valid:
            negative_battery_incomplete = True
        if n1b_modset_rejects and not n1b_valid:
            negative_battery_incomplete = True
        if not n2_client_rejects:
            client_perf_ops = [op for op in ops if op["peer"] == "client" and op["verb"] in PERF_VERBS]
            if client_perf_ops:
                for op in client_perf_ops:
                    if op["status"] != "rejected" or op["reason"] != "wrong_role:client":
                        negative_battery_incomplete = True
                        break
        if not all_n5_present:
            negative_battery_incomplete = True
        if not pre_post_n5_invariance_ok and (
            n1b_modset_rejects or n2_client_rejects or any(bop["status"] == "rejected" for bop in budget_check_ops)
        ):
            negative_battery_incomplete = True
        if foreign_inject_ops and not n6_valid:
            negative_battery_incomplete = True

    if prf06_violations or negative_battery_incomplete:
        checks["PRF-06"] = "fail"
        reasons.extend(f"PRF-06: {v}" for v in prf06_violations)
        if negative_battery_incomplete and not prf06_violations:
            reasons.append("PRF-06: incomplete or invalid negative battery (N1a, N1b, N2, N4, N5 anchored to the certified budget, N6 with closure)")
    elif full_prf06_ready:
        checks["PRF-06"] = "pass"
    else:
        checks["PRF-06"] = "missing"
        if has_negative_battery_elements and not n4_valid:
            reasons.append("PRF-06: missing N4 evidence (perf_preflight rejected area_not_clear inside the N1-N5 invariance window)")

    # -----------------------------------------------------------------------
    # Final Verdict Aggregation (S-perf brief §5: fail > missing > pass)
    # -----------------------------------------------------------------------
    if any(v == "fail" for v in checks.values()):
        code = FALLA
    elif (
        transport_failures
        or technical_data is not None
        or prf03_technical
        or actor_driver_missing
        or any(v != "pass" for v in checks.values())
    ):
        code = INCONCLUSO
        if transport_failures:
            reasons.extend(f"transport: {t}" for t in transport_failures)
        if technical_data is not None:
            reasons.append(f"technical: {technical_data.get('reason', 'blocker')}")
        if prf03_technical:
            reasons.append("technical: PRF-03 technical failure")
    else:
        code = PASA

    return gate_core.make_verdict(
        SPIKE_ID,
        code,
        checks=_checks_out(checks, reasons),
        metrics=metrics,
        reasons=reasons,
    )
