"""Evaluador puro y ciego del spike S3 (brief 2026-11-14-m1-f0.3-s3-brief.md §5).

Decide solo con ``<parte>/samples/`` y con los campos permitidos del manifiesto
(``schema``, ``id``, ``kind``, ``build``, ``both``, ``params``, ``identity``).
No abre otros ficheros de la parte ni mira su nombre de carpeta.

ESQUEMA DE LAS EVIDENCIAS QUE ESTE EVALUADOR ACEPTA
===================================================

Todas las filas son observaciones crudas del motor. Los identificadores de
orden (``*_op_id``) son los opacos que el puente registra; el evaluador los usa
solo para resolver el payload de ``samples/bridge.jsonl`` y no interpreta su
texto. Una fila de ``samples/scenario.jsonl`` sin las columnas crudas que exige
su comprobacion deja esa comprobacion en ``missing`` (nunca en ``pass``).

``samples/scenario.jsonl`` (una fila JSON por linea)
----------------------------------------------------

Campos comunes: ``check`` (``S3-00``..``S3-12``) y ``kind``.

* S3-00: ``kind="handshake"``, ``phase`` (``S0_handshake``|``S9_restore``),
  ``observe_op_id``. Se exige al menos una fila; cada una debe acreditar el
  adaptador cargado y registrado en orden.
* S3-01: ``kind="positive"`` con ``apply1_op_id``, ``observe1_op_id``,
  ``reset_op_id``, ``apply2_op_id`` y ``observe2_op_id``; ``kind="reject"``
  con ``case`` (``unknown_class``|``incompatible_slot``),
  ``baseline_observe_op_id``, ``apply_op_id`` y ``observe_op_id``;
  ``kind="partial"`` con ``apply_op_id``.
* S3-02: ``kind="once_reachable"`` con ``actor_id``, ``start_op_id`` y
  ``page_op_ids`` (todas las paginas de ``job_read`` del trabajo, en orden).
* S3-03: ``kind="hold"`` o ``kind="loop"`` con ``actor_id``, ``start_op_id``
  y ``page_op_ids``.
* S3-04: una fila por gesto, ``kind="emote"`` con ``emote_key``, ``actor_id``,
  ``start_op_id`` y ``page_op_ids``.
* S3-05: ``kind="roam_urban"`` y ``kind="roam_open"`` con ``actor_id``,
  ``start_op_id`` y ``page_op_ids``.
* S3-06: ``kind="unreachable"`` y ``kind="require_threat"`` con ``actor_id``,
  ``start_op_id`` y ``page_op_ids``.
* S3-07: ``kind="require_combat"`` con ``actor_id``, ``start_op_id`` y
  ``page_op_ids``.
* S3-08: ``kind="unknown_emote"`` con ``op_id``; y
  ``kind="cancel_before_start"``, ``"cancel_after_start"``,
  ``"interrupt_between_samples"``, ``"never_starts"`` o
  ``"stale_callback_isolation"`` con ``actor_id``, ``start_op_id``,
  ``page_op_ids``, ``stop_op_id``, ``post_watch_start_op_id`` y
  ``post_watch_page_op_ids`` (estos dos ultimos pueden faltar solo en
  ``interrupt_between_samples`` y ``stale_callback_isolation``).
* S3-09: repite ``kind="never_starts"``, ``"cancel_before_start"`` o
  ``"cancel_after_start"`` con los mismos op ids que S3-08 (la union se hace
  por ``req_seq_n``; las filas retenidas del trabajo detenido y las del
  trabajo de seguimiento posterior se concatenan y se ordenan por
  ``(tick_ms, req_seq_n, seq_n)``).
* S3-10: no necesita filas; se decide con las fixtures del oraculo.
* S3-11: ``kind="observe_no_expansion"`` con ``observe_op_id``; y
  ``kind="apply_props_only"`` con ``apply_op_id`` y ``observe_op_id``.
* S3-12: ``kind="capability_lost"`` y ``kind="no_expansion"`` con
  ``baseline_observe_op_id``, ``apply_op_id`` y ``post_observe_op_id``.

``samples/bridge.jsonl``
------------------------

Se usan los eventos ``enq`` (con ``op_id``, ``peer``, ``verb`` y ``args`` sin
la clave reservada del inyector), ``hello`` (200), ``result`` (200, con
``result.read`` que lleva ``has=["payload"]`` y el payload de 9 miembros) y
``lost``/``expire`` para separar fallos tecnicos de fallos de criterio.

Columnas crudas de ``act_behaviour_run`` (``job_read``; 27 numericas y 3 de
texto, ``page_size = 4``). Unidades y origen:
``seq_n``, ``frame``, ``tick_ms`` (``g_Game.GetTickTime()*1000.0``),
``dtsum_ms`` (``Σtimeslice`` del trabajo), ``x_m``/``y_m``/``z_m``
(posicion del actor), ``wp_x_m``/``wp_y_m``/``wp_z_m`` (marca vigente),
``dist_center_m``, ``max_dist_tick_m``, ``dist_mark_m``, ``settle_dtsum_ms``,
``settle_max_drift_m``, ``path_len_m``, ``dest_reached_n``,
``legs_completed_n``, ``buildings_near_n``, ``ticks_checked_n``,
``out_of_radius_ticks_n``, ``actor_fighting_b``, ``actor_raised_b``,
``actor_health``, ``inf_health``, ``inf_chase_disp_m``, ``combat_obs_tick_ms``;
texto: ``mark_state`` (``en_ruta``|``en_marca``|``no_alcanzada``|``agotado``),
``faction_class`` e ``infected_id``.

Columnas crudas de ``act_emote_run`` (``job_read``; 35 numericas y 6 de texto,
``page_size = 4``). Unidades y origen: ``seq_n``, ``periodic_seq_n``,
``frame``, ``tick_ms``, ``dtsum_ms``, ``req_seq_n``, ``cb_inst_id``
(instancia de ``EmoteCB``), ``max_cb_inst_at_req_n``, ``expected_emote_id``
(``ID_EMOTE_*`` de la fixture), ``observed_emote_id`` (el que llega en
``DsbxOnBound``), ``expected_cmd_id`` (``CMD_GESTUREMOD_*``), ``anim_cmd_id``,
``anim_state_n`` (``STATE_NONE``=0, ``STATE_LOOP_IN``=1, ``STATE_LOOP_LOOP``=2,
``STATE_NORMAL``=7), ``on_finish_called_b``, ``raw_p_canceled_b`` (literal de
``OnFinish(bool pCanceled)``; ``-1`` antes del callback),
``cancel_requested_b``, ``stance_idx``, ``hands_empty_b``,
``can_play_emote_b``, ``em_is_playing_b``, ``em_cb_present_b``,
``exp_pending_id`` (lectura directa del almacenamiento de ``eAIBase``),
``post_cleanup_cb_count_n``, ``foreign_cb_events_n``, ``req_tick_ms``,
``start_tick_ms``, ``cancel_req_tick_ms``, ``end_tick_ms``,
``cleanup_tick_ms``, ``actor_fighting_b``, ``actor_raised_b``,
``actor_health``, ``inf_health``, ``inf_chase_disp_m``,
``combat_obs_tick_ms``; texto: ``emote_key``, ``row_kind``
(``periodic``|``event``), ``emote_state`` (``pedido``|``en_curso``|
``terminado``|``cancelado``|``rechazado``|``agotado``),
``observed_end_cause`` (``cb_normal``|``cb_canceled``|``observer_missing``),
``infected_id`` y ``faction_class``.

Payloads instantaneos (``read`` de la orden)
--------------------------------------------

``act_observe``: ``sk`` = ``core_ver``, ``adapter_ver``, ``backend_class``,
``last_op_id``, ``last_op_status``, ``last_op_reason``; ``nk`` =
``core_loaded_b``, ``backend_available_b``, ``core_start_tick_ms``,
``adapter_reg_tick_ms``, ``weather_frozen_b``, ``world_props_n``,
``world_actors_n``, ``hour_n``, ``minute_n``, ``fog``, ``overcast``, ``rain``,
``last_op_validate_tick_ms``, ``last_op_cap_drop_tick_ms``,
``last_op_revalidate_tick_ms``, ``last_op_first_effect_tick_ms``,
``last_op_reject_tick_ms``, ``last_op_spawned_props_ever_n``,
``last_op_spawned_actors_ever_n``, ``last_op_deleted_objects_ever_n``,
``last_op_env_writes_ever_n``, ``total_mutations_seq_n``, ``tick_ms``,
``frame``; ``scol`` = ``actor_id``, ``real_class``, ``slot_name``,
``item_class``; ``ncol`` = ``x_m``, ``y_m``, ``z_m``, ``health_01`` (una fila
por prenda de cada actor vivo).

``act_scene_apply``: ``sk`` = ``apply_state``, ``failed_item``; ``nk`` =
``backend_available_b``, ``created_props_n``, ``created_actors_n``,
``pre_gear_seeded_n``, ``pre_sweep_total_n``, ``pre_gear_cleared_n``,
``tick_ms``, ``frame``.

``act_reset``: ``nk`` = ``deleted_actors_n``, ``deleted_props_n``,
``deleted_infected_n``, ``tick_ms``, ``frame``.

``act_combat_stage``: ``sk`` = ``infected_id``, ``faction_class``; ``nk`` =
``init_dist_m``, ``actor_health_init``, ``inf_health_init``, ``inf_x0_m``,
``inf_z0_m``, ``tick_ms``, ``frame``.

``act_env_freeze``: ``nk`` = ``weather_frozen_b``, ``hour_n``, ``minute_n``,
``fog``, ``overcast``, ``rain``, ``tick_ms``, ``frame``.

MANIFIESTO
----------

``identity.params`` debe traer ``wire_cap``, ``exp_probe_stamp`` (16 hex del
adaptador en ``git_head``) y ``exp_pbo_sha256`` (``None`` solo en ``offline``).
El sello del nucleo se recalcula desde ``git_head``; nunca se acepta el del
arbol de trabajo. Toda medida en ``[T - 1e-5, T + 1e-5]`` para
``T in {0.5, 1.5, 15.0}`` m se declara ``missing`` (incertidumbre de
serializacion de ``float``).
"""

import math
import subprocess
from pathlib import Path

import f03_common
import gate_core
import wire

SPIKE_ID = "S3"
CHECK_IDS = tuple(f"S3-{i:02d}" for i in range(0, 13))
EXP_PROBE_REL = "DayZSandbox_dev/qa/probe/DayZSandbox_QA_Expansion"
EXP_STAMP_REL = "scripts/5_Mission/DSBX_QA_Exp_Stamp.c"
BOUNDARY_M = (0.5, 1.5, 15.0)
BOUNDARY_EPS_M = 1e-5
DRAIN_MAX_MS = 1000.0
QUIET_MIN_MS = 3000.0
COMBAT_RECENT_MS = 1000.0
CHASE_ADVANCE_M = 0.25
APPROVED_EMOTES = {
    "nod": (58, 1109),
    "shake": (59, 1110),
    "shrug": (60, 1111),
    "clap": (39, 1101),
    "move": (52, 1103),
    "down": (53, 1104),
    "come": (54, 1105),
    "tauntthink": (51, 1108),
}
ALLOWED_MODES = frozenset({"HOLD", "ONCE", "LOOP", "ROAM"})
EXPANSION_MARKERS = ("eAI_", "eAIWaypointBehavior", "eAIWaypointBehavior.ROAMING", "ROAMING_LOCAL")


def _chk(cid: str, status: str, detail: str = "") -> dict:
    return {"detail": detail, "id": cid, "status": status}


def _pass(cid: str) -> dict:
    return _chk(cid, "pass", "ok")


def _miss(cid: str, detail: str) -> dict:
    return _chk(cid, "missing", detail)


def _fail(cid: str, detail: str) -> dict:
    return _chk(cid, "fail", detail)


def _num(obj, key):
    if not isinstance(obj, dict):
        return None
    val = obj.get(key)
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return None
    val = float(val)
    if not math.isfinite(val):
        return None
    return val


def _text(obj, key):
    if not isinstance(obj, dict):
        return None
    val = obj.get(key)
    return val if isinstance(val, str) else None


def _boundary(value) -> bool:
    if value is None:
        return False
    return any(abs(value - t) <= BOUNDARY_EPS_M for t in BOUNDARY_M)


def _dist(x1, z1, x2, z2):
    return math.hypot(x2 - x1, z2 - z1)


def _index_bridge(bridge_rows):
    enq_by_op = {}
    results_by_op = {}
    terminal_err_by_op = {}
    for ev in bridge_rows:
        kind = ev.get("ev")
        oid = ev.get("op_id")
        if kind == "enq" and isinstance(oid, str) and oid not in enq_by_op:
            enq_by_op[oid] = ev
        elif kind == "result" and ev.get("http") == 200 and isinstance(oid, str):
            results_by_op.setdefault(oid, []).append(ev)
        elif kind == "lost" and isinstance(oid, str):
            terminal_err_by_op.setdefault(oid, "result_lost")
        elif kind == "expire" and isinstance(oid, str):
            terminal_err_by_op.setdefault(oid, "result_timeout")
    return {"enq": enq_by_op, "results": results_by_op, "terminal": terminal_err_by_op}


def _resolve(idx, op_id):
    if not isinstance(op_id, str):
        return None, "bad_op_id"
    lst = idx["results"].get(op_id) or []
    if lst:
        return lst[0], ""
    err = idx["terminal"].get(op_id)
    if err:
        return None, err
    return None, "result_timeout"


def _unpack_read(body):
    read = body.get("read") if isinstance(body, dict) else None
    if not isinstance(read, dict) or read.get("has") != ["payload"]:
        return None
    try:
        return wire.unpack_payload(read)
    except ValueError:
        return None


def _result(idx, op_id):
    ev, tech = _resolve(idx, op_id)
    if ev is None:
        return None, None, tech
    return (ev.get("result") or {}), ev, ""


def _done_payload(idx, op_id):
    body, _ev, tech = _result(idx, op_id)
    if body is None:
        return None, tech
    if body.get("status") != "done":
        return None, "status:" + str(body.get("status"))
    payload = _unpack_read(body)
    if payload is None:
        return None, "no_payload"
    return payload, ""


def _is_rejected(idx, op_id, reason):
    body, _ev, tech = _result(idx, op_id)
    if body is None:
        return None, tech
    if body.get("status") != "rejected":
        return False, "status:" + str(body.get("status"))
    if body.get("reason") != reason:
        return False, "reason:" + str(body.get("reason"))
    return True, ""


def _arg_num(args, key):
    if not isinstance(args, dict):
        return None
    nk = args.get("nk") or []
    nv = args.get("nv") or []
    for pos, name in enumerate(nk):
        if name == key and pos < len(nv):
            return _num({"v": nv[pos]}, "v")
    return None


def _arg_str(args, key):
    if not isinstance(args, dict):
        return None
    sk = args.get("sk") or []
    sv = args.get("sv") or []
    for pos, name in enumerate(sk):
        if name == key and pos < len(sv):
            val = sv[pos]
            return val if isinstance(val, str) else None
    return None


def _arg_rows(args):
    if not isinstance(args, dict):
        return None
    rows = args.get("rows")
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 0:
        return None
    return rows


def _collect_pages(idx, page_ids):
    if not isinstance(page_ids, list) or not page_ids:
        return None, [], "no_pages"
    first = None
    rows = []
    for pos, pid in enumerate(page_ids):
        payload, err = _done_payload(idx, pid)
        if payload is None:
            return None, [], err
        if pos == 0:
            first = payload
        else:
            assert first is not None
            if payload["str"].get("state") != first["str"].get("state"):
                return None, [], "state_changed"
            if int(payload["num"].get("rows_total_n", -1)) != int(first["num"].get("rows_total_n", -2)):
                return None, [], "rows_total_changed"
        rows.extend(payload["rows"])
    return first, rows, ""


def _job(idx, start_id, page_ids):
    if not isinstance(start_id, str):
        return None, "bad_start_op"
    start_payload, err = _done_payload(idx, start_id)
    if start_payload is None:
        return None, err
    meta, rows, perr = _collect_pages(idx, page_ids)
    if meta is None:
        return None, perr
    enq = idx["enq"].get(start_id) or {}
    return {
        "args": enq.get("args") or {},
        "meta": meta,
        "resource": start_payload["str"].get("resource", ""),
        "rows": rows,
        "start": start_payload["str"],
    }, ""


def _rows_strictly_increasing(rows, key):
    last = None
    for row in rows:
        val = _num(row, key)
        if val is None:
            return None
        if last is not None and val <= last:
            return False
        last = val
    return True


def _started_b(row):
    cb = _num(row, "cb_inst_id")
    mx = _num(row, "max_cb_inst_at_req_n")
    obs = _num(row, "observed_emote_id")
    exp = _num(row, "expected_emote_id")
    acmd = _num(row, "anim_cmd_id")
    ecmd = _num(row, "expected_cmd_id")
    start = _num(row, "start_tick_ms")
    req = _num(row, "req_tick_ms")
    anim = _num(row, "anim_state_n")
    ofc = _num(row, "on_finish_called_b")
    state = _text(row, "emote_state")
    if None in (cb, mx, obs, exp, acmd, ecmd, start, req, anim, ofc) or state is None:
        return None
    return (
        cb > mx
        and obs == exp
        and acmd == ecmd
        and ecmd != 0.0
        and start >= req
        and req > 0.0
        and (anim != 0.0 or state == "en_curso" or ofc == 1.0)
    )


def _active_combat_b(rows, k):
    row = rows[k]
    inf_id = _text(row, "infected_id")
    inf_h = _num(row, "inf_health")
    act_h = _num(row, "actor_health")
    faction = _text(row, "faction_class")
    tick = _num(row, "tick_ms")
    fight = _num(row, "actor_fighting_b")
    raised = _num(row, "actor_raised_b")
    disp = _num(row, "inf_chase_disp_m")
    if None in (inf_id, inf_h, act_h, faction, tick, fight, raised, disp):
        return None
    if inf_id == "" or inf_h <= 0.0 or act_h <= 0.0:
        return False
    if faction in ("", "eAIFactionPassive", "eAIFactionCivilian"):
        return False
    if fight == 1.0:
        return True
    if raised != 1.0:
        return False
    for j in range(k - 1, -1, -1):
        prev_tick = _num(rows[j], "tick_ms")
        prev_act = _num(rows[j], "actor_health")
        prev_inf = _num(rows[j], "inf_health")
        prev_disp = _num(rows[j], "inf_chase_disp_m")
        if None in (prev_tick, prev_act, prev_inf, prev_disp):
            continue
        dt = tick - prev_tick
        if dt <= 0.0:
            continue
        if dt > COMBAT_RECENT_MS:
            break
        if (prev_act - act_h) > 0.0 or (prev_inf - inf_h) > 0.0 or (disp - prev_disp) >= CHASE_ADVANCE_M:
            return True
    return False


def _wardrobe(payload):
    if payload is None:
        return None
    out = {}
    for row in payload["rows"]:
        aid = _text(row, "actor_id")
        real = _text(row, "real_class")
        slot = _text(row, "slot_name")
        item = _text(row, "item_class")
        if None in (aid, real, slot, item):
            return None
        out.setdefault(aid, {"real_class": real, "items": []})
        out[aid]["items"].append((slot, item))
    return out


def _load_json(path: Path):
    try:
        return gate_core.read_json(path)
    except (OSError, ValueError):
        return None


def _load_fixtures(fixtures_dir: Path) -> dict:
    return {
        "actors": _load_json(fixtures_dir / "s3_actors_preset.json"),
        "marks": _load_json(fixtures_dir / "s3_marks.json"),
        "emotes": _load_json(fixtures_dir / "s3_emotes.json"),
        "combat": _load_json(fixtures_dir / "s3_combat_qa.json"),
    }


def _fixture_wardrobe(actors_fx):
    expected = {}
    for actor in actors_fx.get("actors") or []:
        aid = actor.get("actor_id")
        char = actor.get("character")
        wardrobe = actor.get("wardrobe") or []
        if not isinstance(aid, str) or not isinstance(char, str):
            return None
        items = []
        for item in wardrobe:
            slot = item.get("slot")
            cls = item.get("item")
            if not isinstance(slot, str) or not isinstance(cls, str):
                return None
            items.append((slot, cls))
        expected[aid] = {"real_class": "eAI_" + char, "items": items}
    return expected


def _eval_s3_00(scen_rows, idx, core_pv, exp_pv):
    rows = [r for r in scen_rows if r.get("check") == "S3-00" and r.get("kind") == "handshake"]
    if not rows:
        return _miss("S3-00", "no_scenario")
    for row in rows:
        payload, err = _done_payload(idx, row.get("observe_op_id"))
        if payload is None:
            return _miss("S3-00", err)
        sk = payload["str"]
        nk = payload["num"]
        if _num(nk, "core_loaded_b") != 1.0:
            return _fail("S3-00", "core_not_loaded")
        if _num(nk, "backend_available_b") != 1.0:
            return _fail("S3-00", "backend_unavailable")
        if sk.get("backend_class") != "DSBX_QA_ExpansionBackend":
            return _fail("S3-00", "backend_class")
        if sk.get("core_ver") != core_pv:
            return _fail("S3-00", "core_ver")
        if sk.get("adapter_ver") != exp_pv:
            return _fail("S3-00", "adapter_ver")
        core_start = _num(nk, "core_start_tick_ms")
        adapter_reg = _num(nk, "adapter_reg_tick_ms")
        tick = _num(nk, "tick_ms")
        if None in (core_start, adapter_reg, tick):
            return _miss("S3-00", "missing_columns")
        if not (0.0 < core_start <= adapter_reg <= tick):
            return _fail("S3-00", "registration_order")
    return _pass("S3-00")


def _eval_s3_01(scen_rows, idx, fixtures):
    rows = [r for r in scen_rows if r.get("check") == "S3-01"]
    if not rows:
        return _miss("S3-01", "no_scenario")
    actors_fx = fixtures.get("actors") or {}
    expected_wardrobe = _fixture_wardrobe(actors_fx)
    if not expected_wardrobe:
        return _miss("S3-01", "fixture_unavailable")

    pos = [r for r in rows if r.get("kind") == "positive"]
    if len(pos) != 1:
        return _miss("S3-01", "no_positive")
    row = pos[0]
    for key in ("apply1_op_id", "observe1_op_id", "reset_op_id", "apply2_op_id", "observe2_op_id"):
        if not isinstance(row.get(key), str):
            return _miss("S3-01", "bad_op_id")

    apply1, err = _done_payload(idx, row["apply1_op_id"])
    if apply1 is None:
        return _fail("S3-01", "apply1:" + err)
    if apply1["str"].get("apply_state") != "observado" or apply1["str"].get("failed_item") != "":
        return _fail("S3-01", "apply1_state")
    seeded = _num(apply1["num"], "pre_gear_seeded_n")
    total = _num(apply1["num"], "pre_sweep_total_n")
    cleared = _num(apply1["num"], "pre_gear_cleared_n")
    if None in (seeded, total, cleared):
        return _miss("S3-01", "pre_gear_columns")
    if seeded != 2.0 or total < seeded or cleared != total:
        return _fail("S3-01", "pre_gear_sweep")
    if _num(apply1["num"], "created_props_n") != 2.0 or _num(apply1["num"], "created_actors_n") != 2.0:
        return _fail("S3-01", "apply1_counts")
    enq1 = idx["enq"].get(row["apply1_op_id"]) or {}
    if _arg_num(enq1.get("args") or {}, "seed_pre_gear_b") != 1.0:
        return _fail("S3-01", "seed_flag_missing")

    obs1, err = _done_payload(idx, row["observe1_op_id"])
    if obs1 is None:
        return _miss("S3-01", err)
    if _num(obs1["num"], "world_props_n") != 2.0 or _num(obs1["num"], "world_actors_n") != 2.0:
        return _fail("S3-01", "world_counts_before_reset")
    ward1 = _wardrobe(obs1)
    if ward1 is None or ward1 != expected_wardrobe:
        return _fail("S3-01", "wardrobe_before_reset")

    reset, err = _done_payload(idx, row["reset_op_id"])
    if reset is None:
        return _miss("S3-01", err)
    if _num(reset["num"], "deleted_actors_n") != 2.0 or _num(reset["num"], "deleted_props_n") != 2.0:
        return _fail("S3-01", "reset_counts")

    apply2, err = _done_payload(idx, row["apply2_op_id"])
    if apply2 is None:
        return _fail("S3-01", "apply2:" + err)
    seeded2 = _num(apply2["num"], "pre_gear_seeded_n")
    total2 = _num(apply2["num"], "pre_sweep_total_n")
    cleared2 = _num(apply2["num"], "pre_gear_cleared_n")
    if None in (seeded2, total2, cleared2) or seeded2 != 2.0 or total2 < seeded2 or cleared2 != total2:
        return _fail("S3-01", "pre_gear_sweep_after_reset")

    obs2, err = _done_payload(idx, row["observe2_op_id"])
    if obs2 is None:
        return _miss("S3-01", err)
    if _num(obs2["num"], "world_props_n") != 2.0 or _num(obs2["num"], "world_actors_n") != 2.0:
        return _fail("S3-01", "world_counts_after_reset")
    ward2 = _wardrobe(obs2)
    if ward2 is None or ward2 != expected_wardrobe or ward2 != ward1:
        return _fail("S3-01", "wardrobe_after_reset")

    reject_rows = [r for r in rows if r.get("kind") == "reject"]
    if len(reject_rows) != 2:
        return _miss("S3-01", "missing_rejects")
    for rrow in reject_rows:
        case = rrow.get("case")
        expected_reason = {"unknown_class": "unknown_class", "incompatible_slot": "incompatible_slot"}.get(case)
        if expected_reason is None:
            return _miss("S3-01", "bad_reject_case")
        base, err = _done_payload(idx, rrow.get("baseline_observe_op_id"))
        if base is None:
            return _miss("S3-01", err)
        if _num(base["num"], "weather_frozen_b") != 1.0:
            return _miss("S3-01", "weather_not_frozen")
        ok, derr = _is_rejected(idx, rrow.get("apply_op_id"), expected_reason)
        if ok is None:
            return _miss("S3-01", derr)
        if not ok:
            return _fail("S3-01", f"{case}:{derr}")
        post, err = _done_payload(idx, rrow.get("observe_op_id"))
        if post is None:
            return _miss("S3-01", err)
        if _num(post["num"], "world_props_n") != 0.0 or _num(post["num"], "world_actors_n") != 0.0:
            return _fail("S3-01", f"{case}:effects_before_reject")
        for key in ("last_op_spawned_props_ever_n", "last_op_spawned_actors_ever_n",
                    "last_op_deleted_objects_ever_n", "last_op_env_writes_ever_n"):
            if _num(post["num"], key) != 0.0:
                return _fail("S3-01", f"{case}:counter_{key}")
        for key in ("hour_n", "minute_n", "fog", "overcast", "rain"):
            b = _num(base["num"], key)
            p = _num(post["num"], key)
            if b is None or p is None or abs(b - p) > 1e-4:
                return _fail("S3-01", f"{case}:ambient_changed_{key}")

    partial_rows = [r for r in rows if r.get("kind") == "partial"]
    if len(partial_rows) != 1:
        return _miss("S3-01", "no_partial")
    part, err = _done_payload(idx, partial_rows[0].get("apply_op_id"))
    if part is None:
        return _fail("S3-01", "partial:" + err)
    if part["str"].get("apply_state") != "parcial":
        return _fail("S3-01", "partial_state")
    if part["str"].get("failed_item") != "actor_1:Feet:AthleticShoes_Black":
        return _fail("S3-01", "partial_failed_item")
    return _pass("S3-01")


def _eval_s3_02(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-02" and r.get("kind") == "once_reachable"]
    if len(rows) != 1:
        return _miss("S3-02", "no_scenario")
    job, err = _job(idx, rows[0].get("start_op_id"), rows[0].get("page_op_ids"))
    if job is None:
        return _miss("S3-02", err)
    args = job["args"]
    if _arg_str(args, "mode") != "ONCE":
        return _fail("S3-02", "mode")
    if _arg_str(args, "threat_case") != "none":
        return _fail("S3-02", "threat_case")
    if _arg_num(args, "reach_timeout_ms") != 30000.0:
        return _fail("S3-02", "reach_timeout")
    if _arg_num(args, "settle_window_ms") != 10000.0:
        return _fail("S3-02", "settle_window")
    jrows = job["rows"]
    if len(jrows) < 2:
        return _fail("S3-02", "too_few_rows")
    inc = _rows_strictly_increasing(jrows, "dtsum_ms")
    if inc is None:
        return _miss("S3-02", "missing_dtsum")
    if not inc:
        return _fail("S3-02", "dtsum_not_growing")
    x0 = _num(jrows[0], "x_m")
    z0 = _num(jrows[0], "z_m")
    wx = _num(jrows[0], "wp_x_m")
    wz = _num(jrows[0], "wp_z_m")
    if None in (x0, z0, wx, wz):
        return _miss("S3-02", "missing_initial_position")
    d0 = _dist(x0, z0, wx, wz)
    if not (19.9 <= d0 <= 20.1):
        return _fail("S3-02", f"initial_distance:{d0:.6f}")
    start_meta = _num(job["meta"]["num"], "start_tick_ms")
    reach = None
    for pos, row in enumerate(jrows):
        dm = _num(row, "dist_mark_m")
        if dm is None:
            return _miss("S3-02", "missing_dist_mark")
        if dm < 1.5:
            if _boundary(dm):
                return _miss("S3-02", "quantization_boundary")
            if _text(row, "mark_state") != "en_marca":
                return _fail("S3-02", "not_en_marca")
            reach = pos
            break
    if reach is None:
        return _fail("S3-02", "never_reached")
    tick = _num(jrows[reach], "tick_ms")
    if tick is None or start_meta is None:
        return _miss("S3-02", "missing_tick")
    if tick - start_meta > 30000.0:
        return _fail("S3-02", "reach_too_late")
    px = _num(jrows[reach], "x_m")
    pz = _num(jrows[reach], "z_m")
    if px is None or pz is None:
        return _miss("S3-02", "missing_settle_position")
    settle_last = None
    observed_drift = 0.0
    for row in jrows[reach:]:
        x = _num(row, "x_m")
        z = _num(row, "z_m")
        if x is None or z is None:
            return _miss("S3-02", "missing_position")
        drift = _dist(px, pz, x, z)
        if _boundary(drift):
            return _miss("S3-02", "quantization_boundary")
        if drift >= 0.5:
            return _fail("S3-02", f"settle_drift:{drift:.6f}")
        observed_drift = max(observed_drift, drift)
        reported = _num(row, "settle_max_drift_m")
        if reported is None:
            return _miss("S3-02", "missing_settle_drift")
        if _boundary(reported):
            return _miss("S3-02", "quantization_boundary")
        if reported >= 0.5:
            return _fail("S3-02", "settle_max_drift")
        if reported + 1e-6 < observed_drift:
            return _fail("S3-02", "settle_max_drift_below_observed")
        sd = _num(row, "settle_dtsum_ms")
        if sd is None:
            return _miss("S3-02", "missing_settle_dtsum")
        settle_last = sd
    if settle_last is None or settle_last < 10000.0:
        return _fail("S3-02", "settle_window_short")
    return _pass("S3-02")


def _eval_s3_03(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-03"]
    hold_rows = [r for r in rows if r.get("kind") == "hold"]
    loop_rows = [r for r in rows if r.get("kind") == "loop"]
    if len(hold_rows) != 1 or len(loop_rows) != 1:
        return _miss("S3-03", "no_scenario")

    hold, err = _job(idx, hold_rows[0].get("start_op_id"), hold_rows[0].get("page_op_ids"))
    if hold is None:
        return _miss("S3-03", err)
    hargs = hold["args"]
    if _arg_str(hargs, "mode") != "HOLD":
        return _fail("S3-03", "hold_mode")
    if _arg_num(hargs, "duration_ms") != 10000.0:
        return _fail("S3-03", "hold_duration")
    if _arg_num(hargs, "sample_step_ms") != 500.0:
        return _fail("S3-03", "hold_sample_step")
    hrows = hold["rows"]
    if len(hrows) < 2:
        return _fail("S3-03", "hold_too_few_rows")
    inc = _rows_strictly_increasing(hrows, "dtsum_ms")
    if inc is None:
        return _miss("S3-03", "missing_dtsum")
    if not inc:
        return _fail("S3-03", "hold_dtsum_not_growing")
    last_dtsum = _num(hrows[-1], "dtsum_ms")
    if last_dtsum is None or last_dtsum < 10000.0:
        return _fail("S3-03", "hold_window_short")
    p0x = _num(hrows[0], "x_m")
    p0z = _num(hrows[0], "z_m")
    if p0x is None or p0z is None:
        return _miss("S3-03", "missing_position")
    observed_max = 0.0
    for row in hrows:
        x = _num(row, "x_m")
        z = _num(row, "z_m")
        if x is None or z is None:
            return _miss("S3-03", "missing_position")
        d = _dist(p0x, p0z, x, z)
        if _boundary(d):
            return _miss("S3-03", "quantization_boundary")
        if d >= 0.5:
            return _fail("S3-03", "hold_moved")
        observed_max = max(observed_max, d)
    reported_max = _num(hrows[-1], "max_dist_tick_m")
    if reported_max is None:
        return _miss("S3-03", "missing_max_dist")
    if _boundary(reported_max):
        return _miss("S3-03", "quantization_boundary")
    if reported_max >= 0.5:
        return _fail("S3-03", "hold_max_dist")
    if reported_max + 1e-6 < observed_max:
        return _fail("S3-03", "hold_max_dist_below_observed")

    loop, err = _job(idx, loop_rows[0].get("start_op_id"), loop_rows[0].get("page_op_ids"))
    if loop is None:
        return _miss("S3-03", err)
    largs = loop["args"]
    if _arg_str(largs, "mode") != "LOOP":
        return _fail("S3-03", "loop_mode")
    if _arg_num(largs, "duration_ms") != 60000.0:
        return _fail("S3-03", "loop_duration")
    if _arg_num(largs, "sample_step_ms") != 500.0:
        return _fail("S3-03", "loop_sample_step")
    lrows = loop["rows"]
    if len(lrows) < 2:
        return _fail("S3-03", "loop_too_few_rows")
    inc = _rows_strictly_increasing(lrows, "dtsum_ms")
    if inc is None:
        return _miss("S3-03", "missing_dtsum")
    if not inc:
        return _fail("S3-03", "loop_dtsum_not_growing")
    last_dtsum = _num(lrows[-1], "dtsum_ms")
    if last_dtsum is None or last_dtsum < 60000.0:
        return _fail("S3-03", "loop_window_short")
    prev_legs = None
    legs_grew = False
    prev_path = None
    path_grew = False
    for row in lrows:
        legs = _num(row, "legs_completed_n")
        path = _num(row, "path_len_m")
        if legs is None or path is None:
            return _miss("S3-03", "missing_loop_columns")
        if prev_legs is not None and legs < prev_legs:
            return _fail("S3-03", "legs_decreased")
        if prev_legs is not None and legs > prev_legs:
            legs_grew = True
        if prev_path is not None and path < prev_path:
            return _fail("S3-03", "path_decreased")
        if prev_path is not None and path > prev_path:
            path_grew = True
        prev_legs = legs
        prev_path = path
    legs_final = _num(lrows[-1], "legs_completed_n")
    path_final = _num(lrows[-1], "path_len_m")
    if legs_final is None or legs_final < 3.0:
        return _fail("S3-03", "legs_below_three")
    if path_final is None or path_final < 30.0:
        return _fail("S3-03", "path_below_thirty")
    if not legs_grew:
        return _fail("S3-03", "legs_constant")
    if not path_grew:
        return _fail("S3-03", "path_constant")
    return _pass("S3-03")


def _eval_s3_04(scen_rows, idx, fixtures):
    emotes_fx = fixtures.get("emotes") or {}
    catalog = {}
    for entry in emotes_fx.get("catalog") or []:
        key = entry.get("emote_key")
        eid = entry.get("emote_id")
        cid = entry.get("cmd_id")
        if isinstance(key, str) and isinstance(eid, int) and isinstance(cid, int):
            catalog[key] = (eid, cid)
    if not catalog:
        return _miss("S3-04", "fixture_unavailable")

    rows = [r for r in scen_rows if r.get("check") == "S3-04" and r.get("kind") == "emote"]
    if not rows:
        return _miss("S3-04", "no_scenario")
    by_key = {}
    for row in rows:
        key = row.get("emote_key")
        if not isinstance(key, str):
            return _miss("S3-04", "bad_emote_key")
        by_key.setdefault(key, []).append(row)

    for key in catalog:
        if key not in by_key:
            return _fail("S3-04", f"missing_emote:{key}")
    for key in by_key:
        if key not in catalog:
            return _fail("S3-04", f"unknown_emote:{key}")

    for key, (eid, cid) in catalog.items():
        if len(by_key[key]) != 1:
            return _fail("S3-04", f"duplicate_emote:{key}")
        job, err = _job(idx, by_key[key][0].get("start_op_id"), by_key[key][0].get("page_op_ids"))
        if job is None:
            return _miss("S3-04", err)
        args = job["args"]
        if _arg_str(args, "emote_key") != key:
            return _fail("S3-04", f"{key}:arg_key")
        if _arg_str(args, "test_case") != "normal":
            return _fail("S3-04", f"{key}:test_case")
        if _arg_num(args, "start_timeout_ms") != 5000.0:
            return _fail("S3-04", f"{key}:start_timeout")
        if _arg_num(args, "finish_timeout_ms") != 15000.0:
            return _fail("S3-04", f"{key}:finish_timeout")
        if _arg_num(args, "sample_step_ms") != 250.0:
            return _fail("S3-04", f"{key}:sample_step")

        jrows = job["rows"]
        if not jrows:
            return _fail("S3-04", f"{key}:empty")
        for row in jrows:
            stance = _num(row, "stance_idx")
            hands = _num(row, "hands_empty_b")
            foreign = _num(row, "foreign_cb_events_n")
            if None in (stance, hands, foreign):
                return _miss("S3-04", f"{key}:missing_columns")
            if stance != 0.0 or hands != 1.0:
                return _miss("S3-04", f"{key}:precondition")
            if foreign != 0.0:
                return _fail("S3-04", f"{key}:foreign_callback")
            if _text(row, "observed_end_cause") == "observer_missing":
                return _miss("S3-04", f"{key}:observer_missing")

        req_pos = None
        for pos, row in enumerate(jrows):
            rt = _num(row, "req_tick_ms")
            sb = _started_b(row)
            ofc = _num(row, "on_finish_called_b")
            if sb is None or ofc is None:
                return _miss("S3-04", f"{key}:missing_columns")
            if rt is not None and rt > 0.0 and sb is False and ofc == 0.0:
                req_pos = pos
                break
        if req_pos is None:
            return _miss("S3-04", f"{key}:no_request_row")
        req_row = jrows[req_pos]
        if _num(req_row, "expected_emote_id") != float(eid) or _num(req_row, "expected_cmd_id") != float(cid):
            return _fail("S3-04", f"{key}:expected_ids")
        req_tick = _num(req_row, "req_tick_ms")

        start_pos = None
        for pos, row in enumerate(jrows):
            sb = _started_b(row)
            if sb is None:
                return _miss("S3-04", f"{key}:missing_columns")
            if sb:
                start_pos = pos
                break
        if start_pos is None:
            return _fail("S3-04", f"{key}:never_started")
        start_tick = _num(jrows[start_pos], "start_tick_ms")

        finish_pos = None
        for pos, row in enumerate(jrows):
            ofc = _num(row, "on_finish_called_b")
            raw = _num(row, "raw_p_canceled_b")
            pend = _num(row, "exp_pending_id")
            cause = _text(row, "observed_end_cause")
            if None in (ofc, raw, pend, cause):
                return _miss("S3-04", f"{key}:missing_columns")
            if ofc == 1.0 and raw == 0.0 and cause == "cb_normal" and pend == 0.0 and _text(row, "emote_state") == "terminado":
                finish_pos = pos
                break
        if finish_pos is None:
            return _fail("S3-04", f"{key}:never_finished")
        end_tick = _num(jrows[finish_pos], "end_tick_ms")
        if None in (req_tick, start_tick, end_tick):
            return _miss("S3-04", f"{key}:missing_ticks")
        if not (req_tick <= start_tick < end_tick):
            return _fail("S3-04", f"{key}:order")
        if start_tick - req_tick > 5000.0:
            return _fail("S3-04", f"{key}:start_too_late")
        if end_tick - start_tick > 15000.0:
            return _fail("S3-04", f"{key}:finish_too_late")
        if any(_text(row, "emote_state") == "terminado" and _num(row, "raw_p_canceled_b") != 0.0 for row in jrows):
            return _fail("S3-04", f"{key}:terminated_but_canceled")
    return _pass("S3-04")


def _roam_aggregate(job):
    rows = job["rows"]
    if len(rows) < 2:
        return None, "too_few_rows"
    inc = _rows_strictly_increasing(rows, "dtsum_ms")
    if inc is None:
        return None, "missing_dtsum"
    if not inc:
        return None, "dtsum_not_growing"
    last_dtsum = _num(rows[-1], "dtsum_ms")
    if last_dtsum is None or last_dtsum < 600000.0:
        return None, "window_short"
    x0 = _num(rows[0], "x_m")
    z0 = _num(rows[0], "z_m")
    if x0 is None or z0 is None:
        return None, "missing_position"
    observed_max = 0.0
    for row in rows:
        x = _num(row, "x_m")
        z = _num(row, "z_m")
        dc = _num(row, "dist_center_m")
        if None in (x, z, dc):
            return None, "missing_position"
        if _boundary(dc):
            return None, "quantization_boundary"
        if dc > 15.0:
            return None, "outside_radius"
        real = _dist(x0, z0, x, z)
        if abs(real - dc) > 1e-3:
            return None, "dist_center_inconsistent"
        observed_max = max(observed_max, dc)
    max_dist = _num(rows[-1], "max_dist_tick_m")
    if max_dist is None:
        return None, "missing_max_dist"
    if _boundary(max_dist):
        return None, "quantization_boundary"
    if max_dist > 15.0:
        return None, "max_dist_outside_radius"
    if max_dist + 1e-6 < observed_max:
        return None, "max_dist_below_observed"
    out_ticks = _num(rows[-1], "out_of_radius_ticks_n")
    ticks_checked = _num(rows[-1], "ticks_checked_n")
    if out_ticks is None or ticks_checked is None:
        return None, "missing_counters"
    if ticks_checked <= 0.0:
        return None, "no_ticks"
    if out_ticks != 0.0:
        return None, "out_of_radius"
    prev_path = None
    path_grew = False
    prev_dest = None
    dest_grew = False
    for row in rows:
        path = _num(row, "path_len_m")
        dest = _num(row, "dest_reached_n")
        if path is None or dest is None:
            return None, "missing_path_columns"
        if prev_path is not None and path < prev_path:
            return None, "path_decreased"
        if prev_path is not None and path > prev_path:
            path_grew = True
        if prev_dest is not None and dest < prev_dest:
            return None, "dest_decreased"
        if prev_dest is not None and dest > prev_dest:
            dest_grew = True
        prev_path = path
        prev_dest = dest
    path_final = _num(rows[-1], "path_len_m")
    dest_final = _num(rows[-1], "dest_reached_n")
    if path_final is None or path_final < 40.0:
        return None, "path_below_forty"
    if dest_final is None or dest_final < 4.0:
        return None, "dest_below_four"
    if not path_grew:
        return None, "path_constant"
    if not dest_grew:
        return None, "dest_constant"
    return {
        "max_dist_tick_m": max_dist,
        "path_len_m": path_final,
        "dest_reached_n": dest_final,
        "buildings_near_n": _num(rows[-1], "buildings_near_n"),
    }, ""


def _eval_s3_05(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-05"]
    urban_rows = [r for r in rows if r.get("kind") == "roam_urban"]
    open_rows = [r for r in rows if r.get("kind") == "roam_open"]
    if len(urban_rows) != 1 or len(open_rows) != 1:
        return _miss("S3-05", "no_scenario")

    aggs = {}
    for name, srow in (("urban", urban_rows[0]), ("open", open_rows[0])):
        job, err = _job(idx, srow.get("start_op_id"), srow.get("page_op_ids"))
        if job is None:
            return _miss("S3-05", err)
        args = job["args"]
        if _arg_str(args, "mode") != "ROAM":
            return _fail("S3-05", f"{name}:mode")
        if _arg_num(args, "radius_m") != 15.0:
            return _fail("S3-05", f"{name}:radius")
        duration = _arg_num(args, "duration_ms")
        if duration is None or duration < 600000.0:
            return _fail("S3-05", f"{name}:duration")
        if _arg_num(args, "sample_step_ms") != 5000.0:
            return _fail("S3-05", f"{name}:sample_step")
        agg, aerr = _roam_aggregate(job)
        if agg is None:
            if aerr == "quantization_boundary":
                return _miss("S3-05", f"{name}:quantization_boundary")
            return _fail("S3-05", f"{name}:{aerr}")
        aggs[name] = agg

    buildings = aggs["open"].get("buildings_near_n")
    if buildings is None:
        return _miss("S3-05", "open:missing_buildings")
    if buildings >= 3.0:
        return _miss("S3-05", "open:too_many_buildings")

    u = aggs["urban"]
    o = aggs["open"]
    if (u["max_dist_tick_m"] == o["max_dist_tick_m"]
            and u["path_len_m"] == o["path_len_m"]
            and u["dest_reached_n"] == o["dest_reached_n"]):
        return _fail("S3-05", "identical_aggregates_between_environments")
    return _pass("S3-05")


def _eval_s3_06(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-06"]
    un_rows = [r for r in rows if r.get("kind") == "unreachable"]
    th_rows = [r for r in rows if r.get("kind") == "require_threat"]
    if len(un_rows) != 1 or len(th_rows) != 1:
        return _miss("S3-06", "no_scenario")

    for name, srow, threat in (("unreachable", un_rows[0], False), ("require_threat", th_rows[0], True)):
        job, err = _job(idx, srow.get("start_op_id"), srow.get("page_op_ids"))
        if job is None:
            return _miss("S3-06", err)
        args = job["args"]
        if _arg_str(args, "mode") != "ONCE":
            return _fail("S3-06", f"{name}:mode")
        if _arg_str(args, "threat_case") != ("require_threat" if threat else "none"):
            return _fail("S3-06", f"{name}:threat_case")
        if _arg_num(args, "reach_timeout_ms") != 15000.0:
            return _fail("S3-06", f"{name}:reach_timeout")
        jrows = job["rows"]
        if not jrows:
            return _fail("S3-06", f"{name}:empty")
        inc = _rows_strictly_increasing(jrows, "dtsum_ms")
        if inc is None:
            return _miss("S3-06", "missing_dtsum")
        if not inc:
            return _fail("S3-06", f"{name}:dtsum_not_growing")
        for row in jrows:
            if _text(row, "mark_state") == "en_marca":
                return _fail("S3-06", f"{name}:en_marca")
        last = jrows[-1]
        final_state = _text(last, "mark_state")
        if final_state not in ("no_alcanzada", "agotado"):
            return _fail("S3-06", f"{name}:final_state:{final_state}")
        final_dist = _num(last, "dist_mark_m")
        if final_dist is None:
            return _miss("S3-06", f"{name}:missing_dist_mark")
        if _boundary(final_dist):
            return _miss("S3-06", f"{name}:quantization_boundary")
        if final_dist < 1.5:
            return _fail("S3-06", f"{name}:final_dist_below_1_5")
        start_meta = _num(job["meta"]["num"], "start_tick_ms")
        last_tick = _num(last, "tick_ms")
        if start_meta is None or last_tick is None:
            return _miss("S3-06", f"{name}:missing_ticks")
        if last_tick - start_meta > 15000.0:
            return _fail("S3-06", f"{name}:timeout_exceeded")
        if threat:
            seen = False
            for pos, row in enumerate(jrows):
                dm = _num(row, "dist_mark_m")
                tick = _num(row, "tick_ms")
                if dm is None or tick is None:
                    return _miss("S3-06", "missing_columns")
                if dm < 1.5:
                    continue
                if _boundary(dm):
                    return _miss("S3-06", "quantization_boundary")
                active = _active_combat_b(jrows, pos)
                if active is None:
                    return _miss("S3-06", "missing_combat_columns")
                if active:
                    seen = True
                    break
            if not seen:
                return _miss("S3-06", "require_threat:no_active_combat")
    return _pass("S3-06")


def _eval_s3_07(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-07" and r.get("kind") == "require_combat"]
    if len(rows) != 1:
        return _miss("S3-07", "no_scenario")
    job, err = _job(idx, rows[0].get("start_op_id"), rows[0].get("page_op_ids"))
    if job is None:
        return _miss("S3-07", err)
    args = job["args"]
    if _arg_str(args, "test_case") != "require_combat":
        return _fail("S3-07", "test_case")
    if _arg_num(args, "combat_wait_ms") != 5000.0:
        return _fail("S3-07", "combat_wait")
    if _arg_num(args, "start_timeout_ms") != 5000.0:
        return _fail("S3-07", "start_timeout")
    step = _arg_num(args, "sample_step_ms")
    if step is None:
        step = 250.0
    jrows = job["rows"]
    if not jrows:
        return _fail("S3-07", "empty")
    req_pos = None
    for pos, row in enumerate(jrows):
        req_tick = _num(row, "req_tick_ms")
        tick = _num(row, "tick_ms")
        obs_tick = _num(row, "combat_obs_tick_ms")
        if None in (req_tick, tick, obs_tick):
            return _miss("S3-07", "missing_columns")
        if req_tick > 0.0 and obs_tick == tick and 0.0 <= req_tick - tick <= step:
            req_pos = pos
            break
    if req_pos is None:
        return _miss("S3-07", "no_request_row")
    active = _active_combat_b(jrows, req_pos)
    if active is None:
        return _miss("S3-07", "missing_combat_columns")
    if not active:
        return _miss("S3-07", "combat_not_active_at_request")
    if any(_text(row, "emote_state") == "terminado" for row in jrows):
        return _fail("S3-07", "terminated_under_combat")
    accepted = [row for row in jrows if _text(row, "emote_state") in ("rechazado", "agotado", "cancelado")]
    if not accepted:
        return _fail("S3-07", "no_rejected_or_exhausted_state")
    if _num(accepted[-1], "raw_p_canceled_b") == 0.0:
        return _fail("S3-07", "raw_p_canceled_zero")
    return _pass("S3-07")


def _merge_case(idx, srow):
    job, err = _job(idx, srow.get("start_op_id"), srow.get("page_op_ids"))
    if job is None:
        return None, err
    post = None
    if srow.get("post_watch_page_op_ids"):
        post, perr = _job(idx, srow.get("post_watch_start_op_id"), srow.get("post_watch_page_op_ids"))
        if post is None:
            return None, perr
    rows = list(job["rows"]) + (list(post["rows"]) if post else [])
    reqs = set()
    for row in rows:
        rq = _num(row, "req_seq_n")
        if rq is None:
            return None, "missing_req_seq"
        if rq > 0.0:
            reqs.add(rq)
    if len(reqs) != 1:
        return None, "req_seq_mismatch"
    req = next(iter(reqs))
    rows = [row for row in rows if _num(row, "req_seq_n") == req]
    rows.sort(key=lambda r: (_num(r, "tick_ms") or 0.0, _num(r, "seq_n") or 0.0))
    return {"job": job, "post": post, "req": req, "rows": rows}, ""


def _first_pos(rows, key, positive=True):
    for pos, row in enumerate(rows):
        val = _num(row, key)
        if val is None:
            return None
        if (val > 0.0) if positive else (val > 0.0):
            return pos
    return None


def _cancel_positions(rows):
    cancel_pos = None
    cleanup_pos = None
    for pos, row in enumerate(rows):
        cr = _num(row, "cancel_req_tick_ms")
        cl = _num(row, "cleanup_tick_ms")
        if cr is None or cl is None:
            return None, None, "missing_cancel_columns"
        if cancel_pos is None and cr > 0.0:
            cancel_pos = pos
        if cleanup_pos is None and cl > 0.0:
            cleanup_pos = pos
    return cancel_pos, cleanup_pos, ""


def _eval_s3_08(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-08"]
    if not rows:
        return _miss("S3-08", "no_scenario")

    unknown = [r for r in rows if r.get("kind") == "unknown_emote"]
    if len(unknown) != 1:
        return _miss("S3-08", "no_unknown_emote")
    ok, derr = _is_rejected(idx, unknown[0].get("op_id"), "unknown_emote")
    if ok is None:
        return _miss("S3-08", derr)
    if not ok:
        return _fail("S3-08", "unknown_emote:" + derr)

    kinds = ("cancel_before_start", "cancel_after_start", "interrupt_between_samples",
             "never_starts", "stale_callback_isolation")
    for kind in kinds:
        case_rows = [r for r in rows if r.get("kind") == kind]
        if len(case_rows) != 1:
            return _miss("S3-08", f"no_{kind}")
        case, err = _merge_case(idx, case_rows[0])
        if case is None:
            return _miss("S3-08", f"{kind}:{err}")
        jrows = case["rows"]
        if not jrows:
            return _fail("S3-08", f"{kind}:empty")
        cancel_pos, _cleanup_pos, cerr = _cancel_positions(jrows)
        if cerr:
            return _miss("S3-08", f"{kind}:{cerr}")
        if cancel_pos is None:
            return _miss("S3-08", f"{kind}:no_cancel_row")
        cancel_tick = _num(jrows[cancel_pos], "cancel_req_tick_ms")
        req_pos = _first_pos(jrows, "req_tick_ms")
        if req_pos is None:
            return _miss("S3-08", f"{kind}:no_request")
        req_tick = _num(jrows[req_pos], "req_tick_ms")
        if None in (cancel_tick, req_tick):
            return _miss("S3-08", f"{kind}:missing_ticks")

        if kind == "cancel_before_start":
            for row in jrows[:cancel_pos]:
                cp = _num(row, "can_play_emote_b")
                sb = _started_b(row)
                if cp is None or sb is None:
                    return _miss("S3-08", f"{kind}:missing_columns")
                if cp != 0.0:
                    return _miss("S3-08", f"{kind}:hands_not_blocked")
                if sb:
                    return _miss("S3-08", f"{kind}:started_before_cancel")
            if cancel_tick < req_tick:
                return _fail("S3-08", f"{kind}:cancel_before_request")
            if any(_num(row, "on_finish_called_b") == 1.0 for row in jrows):
                return _fail("S3-08", f"{kind}:on_finish_before_start")
            if any(_text(row, "emote_state") == "terminado" for row in jrows):
                return _fail("S3-08", f"{kind}:terminated")
            if not any(_text(row, "emote_state") == "cancelado" for row in jrows[cancel_pos:]):
                return _fail("S3-08", f"{kind}:not_canceled")

        elif kind == "cancel_after_start":
            pre = False
            for row in jrows[:cancel_pos]:
                sb = _started_b(row)
                st = _num(row, "start_tick_ms")
                if sb is None or st is None:
                    return _miss("S3-08", f"{kind}:missing_columns")
                if sb and st < cancel_tick:
                    pre = True
            if not pre:
                return _miss("S3-08", f"{kind}:not_started_before_cancel")
            end_ticks = [v for v in (_num(row, "end_tick_ms") for row in jrows) if v is not None and v > 0.0]
            if not end_ticks or max(end_ticks) <= cancel_tick:
                return _miss("S3-08", f"{kind}:no_end_after_cancel")
            good = False
            for row in jrows[cancel_pos:]:
                ofc = _num(row, "on_finish_called_b")
                raw = _num(row, "raw_p_canceled_b")
                cause = _text(row, "observed_end_cause")
                if None in (ofc, raw, cause):
                    return _miss("S3-08", f"{kind}:missing_columns")
                if ofc == 1.0 and raw == 1.0 and cause == "cb_canceled" and _text(row, "emote_state") == "cancelado":
                    good = True
                    break
            if not good:
                return _fail("S3-08", f"{kind}:callback_not_canceled")
            if any(_text(row, "emote_state") == "terminado" for row in jrows):
                return _fail("S3-08", f"{kind}:terminated")

        elif kind == "interrupt_between_samples":
            start_ticks = [v for v in (_num(row, "start_tick_ms") for row in jrows) if v is not None and v > 0.0]
            end_ticks = [v for v in (_num(row, "end_tick_ms") for row in jrows) if v is not None and v > 0.0]
            if not start_ticks or not end_ticks:
                return _miss("S3-08", f"{kind}:missing_ticks")
            start_tick = min(start_ticks)
            end_tick = max(end_ticks)
            periodic = []
            for row in jrows:
                if _text(row, "row_kind") != "periodic":
                    continue
                pseq = _num(row, "periodic_seq_n")
                tick = _num(row, "tick_ms")
                sb = _started_b(row)
                if pseq is None or tick is None or sb is None:
                    return _miss("S3-08", f"{kind}:missing_columns")
                periodic.append((pseq, tick, sb))
            found = False
            for i in range(len(periodic) - 1):
                p1, t1, s1 = periodic[i]
                p2, t2, s2 = periodic[i + 1]
                if p2 != p1 + 1.0:
                    continue
                if s1 is False and t1 < start_tick < cancel_tick <= end_tick < t2:
                    found = True
                    break
            if not found:
                return _miss("S3-08", f"{kind}:interruption_not_between_samples")
            good = False
            for row in jrows:
                ofc = _num(row, "on_finish_called_b")
                raw = _num(row, "raw_p_canceled_b")
                if None in (ofc, raw):
                    return _miss("S3-08", f"{kind}:missing_columns")
                if ofc == 1.0 and raw == 1.0 and _text(row, "emote_state") == "cancelado":
                    good = True
                    break
            if not good:
                return _fail("S3-08", f"{kind}:not_canceled")

        elif kind == "never_starts":
            for row in jrows[:cancel_pos]:
                cp = _num(row, "can_play_emote_b")
                sb = _started_b(row)
                if cp is None or sb is None:
                    return _miss("S3-08", f"{kind}:missing_columns")
                if cp != 0.0:
                    return _miss("S3-08", f"{kind}:hands_not_blocked")
                if sb:
                    return _miss("S3-08", f"{kind}:started")
            if cancel_tick - req_tick < 5000.0:
                return _fail("S3-08", f"{kind}:timeout_too_short")
            if not any(_text(row, "emote_state") == "agotado" for row in jrows[cancel_pos:]):
                return _fail("S3-08", f"{kind}:not_exhausted")

        else:  # stale_callback_isolation
            if not any((_num(row, "foreign_cb_events_n") or 0.0) >= 1.0 for row in jrows):
                return _miss("S3-08", f"{kind}:no_foreign_callback")
            for row in jrows:
                sb = _started_b(row)
                if sb is None:
                    return _miss("S3-08", f"{kind}:missing_columns")
                if sb:
                    return _fail("S3-08", f"{kind}:stale_callback_attributed")
            if any(_text(row, "emote_state") == "terminado" for row in jrows):
                return _fail("S3-08", f"{kind}:terminated")
    return _pass("S3-08")


def _eval_s3_09(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-09"]
    if not rows:
        return _miss("S3-09", "no_scenario")
    kinds = ("never_starts", "cancel_before_start", "cancel_after_start")
    seen = set()
    for row in rows:
        kind = row.get("kind")
        if kind not in kinds:
            return _miss("S3-09", f"bad_kind:{kind}")
        seen.add(kind)
    if seen != set(kinds):
        return _miss("S3-09", "missing_case")

    for kind in kinds:
        case_rows = [r for r in rows if r.get("kind") == kind]
        if len(case_rows) != 1:
            return _miss("S3-09", f"duplicate_{kind}")
        case, err = _merge_case(idx, case_rows[0])
        if case is None:
            return _miss("S3-09", f"{kind}:{err}")
        jrows = case["rows"]
        if not jrows:
            return _fail("S3-09", f"{kind}:empty")
        cancel_pos, cleanup_pos, cerr = _cancel_positions(jrows)
        if cerr:
            return _miss("S3-09", f"{kind}:{cerr}")
        if cancel_pos is None or cleanup_pos is None:
            return _miss("S3-09", f"{kind}:no_cancel_or_cleanup")
        if cleanup_pos < cancel_pos:
            return _fail("S3-09", f"{kind}:cleanup_before_cancel")
        cancel_tick = _num(jrows[cancel_pos], "cancel_req_tick_ms")
        cleanup_tick = _num(jrows[cleanup_pos], "cleanup_tick_ms")
        if None in (cancel_tick, cleanup_tick):
            return _miss("S3-09", f"{kind}:missing_ticks")
        if cleanup_tick < cancel_tick:
            return _fail("S3-09", f"{kind}:cleanup_before_cancel_tick")
        if cleanup_tick - cancel_tick > DRAIN_MAX_MS:
            return _fail("S3-09", f"{kind}:drain_too_long")
        for row in jrows[cancel_pos:]:
            pcc = _num(row, "post_cleanup_cb_count_n")
            if pcc is None:
                return _miss("S3-09", f"{kind}:missing_columns")
            if pcc != 0.0:
                return _fail("S3-09", f"{kind}:new_callback_after_cancel")
        for row in jrows[cleanup_pos:]:
            cp = _num(row, "can_play_emote_b")
            playing = _num(row, "em_is_playing_b")
            present = _num(row, "em_cb_present_b")
            pcc = _num(row, "post_cleanup_cb_count_n")
            pend = _num(row, "exp_pending_id")
            if None in (cp, playing, present, pcc, pend):
                return _miss("S3-09", f"{kind}:missing_columns")
            if cp != 1.0:
                return _miss("S3-09", f"{kind}:hands_still_blocked")
            if playing != 0.0:
                return _fail("S3-09", f"{kind}:emote_still_playing")
            if present != 0.0:
                return _fail("S3-09", f"{kind}:callback_still_present")
            if pcc != 0.0:
                return _fail("S3-09", f"{kind}:new_callback_in_quiet_window")
            if pend != 0.0:
                return _fail("S3-09", f"{kind}:pending_request_not_cleared")
        last_tick = _num(jrows[-1], "tick_ms")
        if last_tick is None:
            return _miss("S3-09", f"{kind}:missing_last_tick")
        if last_tick - cleanup_tick < QUIET_MIN_MS:
            return _fail("S3-09", f"{kind}:quiet_window_short")
    return _pass("S3-09")


def _fixture_text(fixtures_dir: Path, name: str):
    path = fixtures_dir / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _eval_s3_10(fixtures, fixtures_dir):
    actors = fixtures.get("actors")
    marks = fixtures.get("marks")
    emotes = fixtures.get("emotes")
    combat = fixtures.get("combat")
    if not all(isinstance(x, dict) for x in (actors, marks, emotes, combat)):
        return _miss("S3-10", "fixture_unavailable")

    for name in ("s3_actors_preset.json", "s3_marks.json", "s3_emotes.json"):
        text = _fixture_text(fixtures_dir, name)
        if text is None:
            return _miss("S3-10", f"missing_{name}")
        for marker in EXPANSION_MARKERS:
            if marker in text:
                return _fail("S3-10", f"{name}:expansion_marker:{marker}")

    catalog = emotes.get("catalog") or []
    got = {}
    for entry in catalog:
        key = entry.get("emote_key")
        eid = entry.get("emote_id")
        cid = entry.get("cmd_id")
        kind = entry.get("kind")
        if not isinstance(key, str) or not isinstance(eid, int) or not isinstance(cid, int) or kind != "onetime":
            return _fail("S3-10", "emote_entry_shape")
        got[key] = (eid, cid)
    if got != APPROVED_EMOTES:
        return _fail("S3-10", "emote_catalog_mismatch")

    props = actors.get("props") or []
    actor_list = actors.get("actors") or []
    if len(props) != 2 or len(actor_list) != 2:
        return _fail("S3-10", "actors_preset_counts")
    if {p.get("class") for p in props} != {"Land_Chair_1", "Barrel_Green"}:
        return _fail("S3-10", "props_classes")
    chars = [a.get("character") for a in actor_list]
    if set(chars) != {"SurvivorM_Mirek", "SurvivorF_Eva"}:
        return _fail("S3-10", "actor_characters")
    expected_wardrobe = _fixture_wardrobe(actors)
    if expected_wardrobe is None:
        return _fail("S3-10", "actor_wardrobe_shape")
    for aid, entry in expected_wardrobe.items():
        slots = sorted(slot for slot, _item in entry["items"])
        if slots != sorted(["Headgear", "Body", "Legs", "Feet", "Back"]):
            return _fail("S3-10", f"actor_slots:{aid}")
        if len(entry["items"]) != 5:
            return _fail("S3-10", f"actor_item_count:{aid}")
    if expected_wardrobe.get("actor_1", {}).get("items") is not None:
        feet = [item for slot, item in expected_wardrobe["actor_1"]["items"] if slot == "Feet"]
        if feet != ["AthleticShoes_Black"]:
            return _fail("S3-10", "actor_1_feet")

    points = marks.get("points") or {}
    required = ("once_origin", "once_reachable", "once_unreachable_origin", "once_unreachable",
                "threat_origin", "threat_mark", "threat_infected", "loop_m0", "loop_m1",
                "roam_urban_center", "roam_open_center", "hold_origin")
    for name in required:
        if name not in points:
            return _fail("S3-10", f"mark_missing:{name}")
    for name, point in points.items():
        mode = point.get("mode")
        if mode not in ALLOWED_MODES:
            return _fail("S3-10", f"mark_mode:{name}")
        if not isinstance(point.get("x_m"), (int, float)) or not isinstance(point.get("z_m"), (int, float)):
            return _fail("S3-10", f"mark_coords:{name}")
    if marks["points"]["roam_open_center"].get("buildings_near_max", 2) >= 3:
        return _fail("S3-10", "roam_open_buildings")

    if combat.get("faction_key") != "qa_hostile":
        return _fail("S3-10", "combat_faction")
    if combat.get("infected_class") != "ZmbM_PatrolNormal_Autumn":
        return _fail("S3-10", "combat_infected")
    return _pass("S3-10")


def _eval_s3_11(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-11"]
    obs_rows = [r for r in rows if r.get("kind") == "observe_no_expansion"]
    apply_rows = [r for r in rows if r.get("kind") == "apply_props_only"]
    if len(obs_rows) != 1 or len(apply_rows) != 1:
        return _miss("S3-11", "no_scenario")
    obs, err = _done_payload(idx, obs_rows[0].get("observe_op_id"))
    if obs is None:
        return _miss("S3-11", err)
    if _num(obs["num"], "core_loaded_b") != 1.0:
        return _fail("S3-11", "core_not_loaded")
    if _num(obs["num"], "backend_available_b") != 0.0:
        return _fail("S3-11", "backend_still_available")
    if obs["str"].get("adapter_ver") != "":
        return _fail("S3-11", "adapter_ver_not_empty")

    enq = idx["enq"].get(apply_rows[0].get("apply_op_id")) or {}
    args = enq.get("args") or {}
    if _arg_rows(args) != 0:
        return _fail("S3-11", "scene_has_actors")
    if _arg_num(args, "props_n") != 2.0:
        return _fail("S3-11", "props_arg")
    applied, err = _done_payload(idx, apply_rows[0].get("apply_op_id"))
    if applied is None:
        return _fail("S3-11", "apply:" + err)
    if _num(applied["num"], "created_props_n") != 2.0:
        return _fail("S3-11", "created_props")
    post, err = _done_payload(idx, apply_rows[0].get("observe_op_id"))
    if post is None:
        return _miss("S3-11", err)
    if _num(post["num"], "world_props_n") != 2.0:
        return _fail("S3-11", "world_props")
    return _pass("S3-11")


def _eval_s3_12(scen_rows, idx):
    rows = [r for r in scen_rows if r.get("check") == "S3-12"]
    lost_rows = [r for r in rows if r.get("kind") == "capability_lost"]
    noexp_rows = [r for r in rows if r.get("kind") == "no_expansion"]
    if len(lost_rows) != 1 or len(noexp_rows) != 1:
        return _miss("S3-12", "no_scenario")
    for kind, srow in (("capability_lost", lost_rows[0]), ("no_expansion", noexp_rows[0])):
        base, err = _done_payload(idx, srow.get("baseline_observe_op_id"))
        if base is None:
            return _miss("S3-12", err)
        if _num(base["num"], "weather_frozen_b") != 1.0:
            return _miss("S3-12", f"{kind}:weather_not_frozen")
        enq = idx["enq"].get(srow.get("apply_op_id")) or {}
        args = enq.get("args") or {}
        if _arg_rows(args) is None or _arg_rows(args) < 1:
            return _fail("S3-12", f"{kind}:scene_without_actors")
        if _arg_num(args, "props_n") != 2.0:
            return _fail("S3-12", f"{kind}:props_arg")
        if kind == "capability_lost" and _arg_str(args, "cap_mode") != "drop_after_validate":
            return _fail("S3-12", "capability_lost:cap_mode")
        ok, derr = _is_rejected(idx, srow.get("apply_op_id"), "expansion_unavailable")
        if ok is None:
            return _miss("S3-12", derr)
        if not ok:
            return _fail("S3-12", f"{kind}:{derr}")
        post, err = _done_payload(idx, srow.get("post_observe_op_id"))
        if post is None:
            return _miss("S3-12", err)
        if _num(post["num"], "world_props_n") != 0.0 or _num(post["num"], "world_actors_n") != 0.0:
            return _fail("S3-12", f"{kind}:effects_after_reject")
        for key in ("last_op_spawned_props_ever_n", "last_op_spawned_actors_ever_n",
                    "last_op_deleted_objects_ever_n", "last_op_env_writes_ever_n"):
            if _num(post["num"], key) != 0.0:
                return _fail("S3-12", f"{kind}:counter_{key}")
        first_effect = _num(post["num"], "last_op_first_effect_tick_ms")
        if first_effect is None:
            return _miss("S3-12", f"{kind}:missing_first_effect")
        if first_effect != -1.0:
            return _fail("S3-12", f"{kind}:first_effect_before_reject")
        base_mut = _num(base["num"], "total_mutations_seq_n")
        post_mut = _num(post["num"], "total_mutations_seq_n")
        if base_mut is None or post_mut is None:
            return _miss("S3-12", f"{kind}:missing_mutations")
        if post_mut > base_mut:
            return _fail("S3-12", f"{kind}:mutations_incremented")
        for key in ("hour_n", "minute_n", "fog", "overcast", "rain"):
            b = _num(base["num"], key)
            p = _num(post["num"], key)
            if b is None or p is None or abs(b - p) > 1e-4:
                return _fail("S3-12", f"{kind}:ambient_changed_{key}")
        if kind == "capability_lost":
            seq = [_num(post["num"], key) for key in ("last_op_validate_tick_ms", "last_op_cap_drop_tick_ms",
                                                      "last_op_revalidate_tick_ms", "last_op_reject_tick_ms")]
            if any(v is None for v in seq):
                return _miss("S3-12", "missing_stage_ticks")
            if not (0.0 < seq[0] <= seq[1] <= seq[2] <= seq[3]):
                return _fail("S3-12", "stage_order")
    return _pass("S3-12")


def _actor_overlap(scen_rows, idx):
    seen = set()
    intervals = []
    for row in scen_rows:
        for sid_key, page_key in (("start_op_id", "page_op_ids"),
                                  ("post_watch_start_op_id", "post_watch_page_op_ids")):
            sid = row.get(sid_key)
            pids = row.get(page_key)
            if not isinstance(sid, str) or not pids or sid in seen:
                continue
            seen.add(sid)
            job, err = _job(idx, sid, pids)
            if job is None:
                continue
            res = job["resource"]
            start = _num(job["meta"]["num"], "start_tick_ms")
            end = _num(job["meta"]["num"], "end_tick_ms")
            if not isinstance(res, str) or not res.startswith("actor:") or start is None or end is None or end <= 0.0:
                continue
            intervals.append((res, start, end))
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            r1, s1, e1 = intervals[i]
            r2, s2, e2 = intervals[j]
            if r1 == r2 and s1 < e2 and s2 < e1:
                return True
    return False


def compute_exp_stamp_at_commit(git_head: str, repo_root: Path | None = None) -> str:
    """Sello de 16 hex del adaptador leyendo sus fuentes en ``git_head`` (nunca del arbol)."""
    if not isinstance(git_head, str) or not git_head.strip():
        raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")
    head = git_head.strip()
    root = Path(repo_root) if repo_root is not None else f03_common._resolve_repo_root(None)
    toplevel = f03_common._git_toplevel(root)
    if toplevel is None:
        raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{head}^{{commit}}"],
        cwd=toplevel,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if verify.returncode != 0:
        raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")
    ls = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", head, "--", EXP_PROBE_REL],
        cwd=toplevel,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if ls.returncode != 0 or not ls.stdout.strip():
        raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")
    prefix = EXP_PROBE_REL + "/"
    pairs = []
    for tree_path in sorted(line.strip() for line in ls.stdout.splitlines() if line.strip()):
        if not tree_path.startswith(prefix):
            continue
        rel = tree_path[len(prefix):]
        if rel == EXP_STAMP_REL:
            continue
        show = subprocess.run(
            ["git", "show", f"{head}:{tree_path}"],
            cwd=toplevel,
            capture_output=True,
            check=False,
        )
        if show.returncode != 0:
            raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")
        pairs.append((rel, show.stdout))
    if not pairs:
        raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")
    return wire.compute_probe_stamp_from_pairs(pairs)


def evaluate(part_dir, *, repo_root: Path | None = None, fixtures_dir: Path | None = None) -> dict:
    pdir = Path(part_dir)
    raw_manifest = gate_core.read_json(pdir / "manifest.json")
    manifest = {
        "both": bool(raw_manifest.get("both", True)),
        "build": raw_manifest.get("build"),
        "id": raw_manifest.get("id", SPIKE_ID),
        "identity": raw_manifest.get("identity"),
        "kind": raw_manifest.get("kind", "spike"),
        "params": raw_manifest.get("params") if isinstance(raw_manifest.get("params"), dict) else {},
        "schema": raw_manifest.get("schema"),
    }
    spike_id = str(manifest["id"] or SPIKE_ID)
    build = manifest["build"]
    req_peers = ("server", "client") if manifest["both"] else ("server",)
    samples_dir = pdir / "samples"
    bridge_rows = f03_common.read_jsonl(samples_dir / "bridge.jsonl")
    scen_rows = f03_common.read_jsonl(samples_dir / "scenario.jsonl")
    fixtures_path = Path(fixtures_dir) if fixtures_dir is not None else Path(__file__).resolve().parent / "fixtures"
    fixtures = _load_fixtures(fixtures_path)

    def _early(reason: str) -> dict:
        checks = [_chk(cid, "missing", reason) for cid in CHECK_IDS]
        verdict = gate_core.make_verdict(spike_id, 2, checks=checks, metrics={}, reasons=[reason])
        verdict.update({"c4_m1": "INCONCLUSO", "c4_m2": "pendiente", "c4_status": "m1=INCONCLUSO; m2=pendiente"})
        return verdict

    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        return _early("params_unverified")
    if build in ("retail", "diag") and identity.get("git_dirty") is not False:
        return _early("git_dirty")

    peer_builds = identity.get("peer_builds")
    if not isinstance(peer_builds, dict) or any(peer_builds.get(role) != build for role in req_peers):
        return _early("build_mismatch")

    good_hellos = [
        ev for ev in bridge_rows
        if ev.get("ev") == "hello" and ev.get("http") == 200 and ev.get("ok") is not False
    ]
    for role in req_peers:
        if not any(ev.get("peer") == role for ev in good_hellos):
            return _early("build_mismatch")
    for ev in good_hellos:
        args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
        proto = args.get("proto") if "proto" in args else ev.get("proto")
        h_build = args.get("build") if "build" in args else ev.get("build")
        if proto != "qa0" or h_build != build:
            return _early("build_mismatch")

    git_head = identity.get("git_head")
    try:
        core_stamp = f03_common.compute_probe_stamp_at_commit(git_head or "", repo_root=repo_root)
    except f03_common.StampSourceUnavailableError:
        return _early("stamp_source_unavailable")
    core_pv = f"dsbx-qa1+{core_stamp}"
    if identity.get("probe_stamp") != core_stamp:
        return _early("artifact_unverified")
    for ev in good_hellos:
        args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
        pv = args.get("probe_ver") if "probe_ver" in args else ev.get("probe_ver")
        if not isinstance(pv, str) or pv == "dsbx-qa1+unstamped" or pv != core_pv:
            return _early("artifact_unverified")

    try:
        exp_stamp = compute_exp_stamp_at_commit(git_head or "", repo_root=repo_root)
    except f03_common.StampSourceUnavailableError:
        return _early("stamp_source_unavailable")
    exp_pv = f"dsbx-qa-exp1+{exp_stamp}"
    id_params = identity.get("params") if isinstance(identity.get("params"), dict) else {}
    if id_params.get("exp_probe_stamp") != exp_stamp:
        return _early("params_unverified")
    if build in ("retail", "diag") and not id_params.get("exp_pbo_sha256"):
        return _early("artifact_unverified")

    ok_params, param_reason = f03_common.verify_eval_params_at_commit(manifest, repo_root=repo_root)
    if not ok_params:
        return _early(param_reason)

    if any(ev.get("ev") == "wire_cap_exceeded" for ev in bridge_rows):
        return _early("wire_cap_exceeded")
    if any(r.get("ev") == "operator_timeout" for r in scen_rows):
        return _early("operator_timeout")

    idx = _index_bridge(bridge_rows)
    if _actor_overlap(scen_rows, idx):
        return _early("actor_resource_overlap")

    checks = [
        _eval_s3_00(scen_rows, idx, core_pv, exp_pv),
        _eval_s3_01(scen_rows, idx, fixtures),
        _eval_s3_02(scen_rows, idx),
        _eval_s3_03(scen_rows, idx),
        _eval_s3_04(scen_rows, idx, fixtures),
        _eval_s3_05(scen_rows, idx),
        _eval_s3_06(scen_rows, idx),
        _eval_s3_07(scen_rows, idx),
        _eval_s3_08(scen_rows, idx),
        _eval_s3_09(scen_rows, idx),
        _eval_s3_10(fixtures, fixtures_path),
        _eval_s3_11(scen_rows, idx),
        _eval_s3_12(scen_rows, idx),
    ]
    metrics = {"core_stamp": core_stamp, "exp_stamp": exp_stamp, "wire_cap": int(wire.WIRE_CAP)}

    c4_ids = [f"S3-{i:02d}" for i in range(1, 11)]
    c4_checks = [c for c in checks if c["id"] in c4_ids]
    if all(c["status"] == "pass" for c in c4_checks):
        c4_m1 = "PASA"
    elif any(c["status"] == "fail" for c in c4_checks):
        c4_m1 = "FALLA"
    else:
        c4_m1 = "INCONCLUSO"
    c4 = {"c4_m1": c4_m1, "c4_m2": "pendiente", "c4_status": f"m1={c4_m1}; m2=pendiente"}

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    if failed:
        verdict = gate_core.make_verdict(spike_id, 1, checks=checks, metrics=metrics, reasons=failed)
        verdict.update(c4)
        return verdict

    tech_reasons = []
    for c in checks:
        if c["status"] != "pass" and c["detail"] in ("result_lost", "result_timeout", "operator_timeout"):
            if c["detail"] not in tech_reasons:
                tech_reasons.append(c["detail"])
    if tech_reasons:
        verdict = gate_core.make_verdict(spike_id, 2, checks=checks, metrics=metrics, reasons=tech_reasons)
        verdict.update(c4)
        return verdict

    if any(c["status"] != "pass" for c in checks):
        missing_ids = [c["id"] for c in checks if c["status"] != "pass"]
        verdict = gate_core.make_verdict(spike_id, 2, checks=checks, metrics=metrics, reasons=missing_ids)
        verdict.update(c4)
        return verdict

    verdict = gate_core.make_verdict(spike_id, 0, checks=checks, metrics=metrics, reasons=[])
    verdict.update(c4)
    return verdict
