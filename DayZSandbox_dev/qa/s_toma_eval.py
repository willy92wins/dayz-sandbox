r"""Evaluador puro de S-toma (brief S-toma §5 y enmiendas vinculantes T1-T13 / E1-E9).

Esquema exacto de `samples/` consumido por `evaluate(part_dir)`
===============================================================

El evaluador es puro sobre una sola carpeta de evidencia (`part_dir`). Lee únicamente:
- `part_dir / "manifest.json"` (campos de identidad permitidos: `both`, `build`, `id`,
  `identity`, `kind`, `params`, `schema`).
- `part_dir / "samples" / "bridge.jsonl"` (traza cruda de eventos HTTP de `QABridge` entre el
  arnés y los dos peers `server` y `client`).
- `part_dir / "samples" / "scenario.jsonl"` (marcas temporales del arnés `h_ms`, pares de
  reloj, estímulos de parada/mirada y ventanas de corte de conexión).
- `qa/fixtures/s_toma_fixture.json` (fixture canónica de escena, actores, vestuario, cues,
  infectado y camino de cámara Catmull-Rom B6).

1. `samples/bridge.jsonl`
-------------------------
Secuencia JSONL producida por `bridge_qa.QABridge`:
- `ev == "hello"` (`http == 200`, `ok == True`): `peer` (`"server"` | `"client"`), `inst`,
  `args` con `proto` (`"qa0"`), `build` (`"offline"` | `"diag"` | `"retail"`), `probe_ver`
  (`"dsbx-qa1+<16hex>"` o `"dsbx-qa1+unstamped"`, 25 caracteres).
- `ev == "enq"` / `ev == "deliver"`: `op_id` opaco, `peer`, `inst`, `verb`, `args` (con el
  campo de inyección ya filtrado por el puente antes de volcar el registro).
- `ev == "poll"` (`http == 200`): `peer`, `inst`, `frame`, `tick_s`, `held_ms`, `n_ops`,
  `op_ids`, `now_ms`, `body_len`.
- `ev == "result"` (`http == 200`): `peer`, `op_id`, `body_len`, `result` con `op_id`,
  `status` (`"done"` | `"ok"` | `"error"` | `"rejected"`), `reason`, `dup` (`false` en la
  primera entrega consumida), `recv_ms`, `done_ms`, `frame_recv`, `frame_done` y `read`
  (payload empaquetado con `wire.pack_payload`).
- `ev == "keepalive"`, `ev == "cut_start"`, `ev == "cut_end"`, `ev == "wire_cap_exceeded"`,
  `ev == "lost"`, `ev == "expire"`.

2. Verbos y tablas en `samples/bridge.jsonl`
--------------------------------------------
- `take_clock_ping` (`server` o `client`, instantáneo):
  - `args.nk`: `ping_seq` (entero 0..7).
  - `read.nk`: `peer_frame` (int, contador `m_Frame`), `peer_tick_ms` (float, ms de
    `GetGame().GetTickTime() * 1000.0`), `dtsum_ms` (float, ms de suma de `timeslice`),
    `lease_ms` (float), `last_ok_poll_ms` (float).
  - `read.sk`: `peer_role` (`"server"` | `"client"`), `observer_stamp` (25 chars).

- `take_key_op` (`client`, instantáneo):
  - `args.sk`: `op` (`"audit_candidates"` | `"bind_key"` | `"restore_bindings"`),
    `action_name` (`"UADsbxQaTakeStop"`), `candidates`, `target_key`.
  - `read.nk`: `input_id` (int, `UAInputAPI.GetInputByName` / `RegisterInput` en
    `P:\scripts\3_game\inputapi\uainput.c:218,231`), `candidates_checked_n` (int),
    `free_candidates_n` (int), `conflict_count_def` (int), `conflict_count_alt` (int),
    `export_called_b` (0/1, `GetUApi().Export()` en `uainput.c:262`).
  - `read.sk`: `selected_def_key`, `selected_alt_key`, `bound_keys_csv`,
    `conflicting_actions_csv`, `build_version` (`GetGame().GetVersion` en
    `P:\scripts\3_game\global\game.c:942`).

- `take_scene_prep` (`server`, instantáneo):
  - `args.sk`: `op` (`"apply"` | `"reset"` | `"verify"` | `"set_director"` |
    `"restart_epoch"` | `"release_held_ack"` | `"perturb_fixture"` | `"status"`),
    `take_id`, `director_id`, `director_engine_uid`.
  - `args.nk`: `director_allow_dmg_pre_b` (0/1, `Object.SetAllowDamage` en
    `P:\scripts\3_game\entities\object.c:1196`), `actor_capable_b` (0/1),
    `director_present_b` (0/1), `spawn_infected_b` (0/1), `emote_initial_id` (13),
    `emote_pending_id` (1), `emote_future_id` (44).
  - `read.nk`: `scene_ok_b`, `observer_ok_b`, `actors_count_n`, `extra_entities_n`,
    `actor1_mark_err_m`, `actor2_mark_err_m`, `wardrobe_match_b`, `persona_match_b`,
    `director_allow_dmg_b` (`Object.GetAllowDamage()` en `object.c:1191`),
    `director_health` (`Object.GetHealth01("", "")`), `director_alive_b`
    (`Object.IsAlive()`), `director_in_block_b` (`DayZPlayerImplement` / `SetBlock(false)`
    en `P:\scripts\4_world\entities\manbase\playerbase.c:3809`), `pending_cues_n`,
    `exp_emote_req_id_n` (`eAIBase.DsbxGetPendingEmoteID()`), `future_cues_fired_n`,
    `srv_key_rpc_recv_n`, `srv_key_rpc_rejected_n`, `transitions_n`, `restorations_n`,
    `ack_sent_n`, `held_acks_n`, `srv_epoch`, `last_ok_poll_ms`, `lease_ms`,
    `term_frame`, `term_tick_ms`, `term_lease_age_ms`, `restore_frame`,
    `cleanup_end_frame`.
  - `read.sk`: `active_take_id`, `take_state`, `take_origin`, `director_id`,
    `director_engine_uid`, `reg_engine_uid`, `sender_engine_uid`
    (`Man.GetIdentity().GetId()` en `P:\scripts\3_game\gameplay.c:368`),
    `payload_sender_id`, `observer_stamp` (25 chars), `adapter_ver` (29 chars
    `"dsbx-qa-exp1+<16hex>"` o `"dsbx-qa-exp1+unstamped"` desde
    `DSBX_QA_ActorRegistry.GetAdapterStamp()`, o `""` si `observer_ok_b == 0`).

- `take_cam_prep` (`client`, instantáneo):
  - `args.sk`: `op` (`"load_path"` | `"clear_path"` | `"set_cache"` | `"set_ui_blocker"` |
    `"hold_next_go"` | `"release_held_go"` | `"deliver_stale_msg"` | `"reactivate_cam"` |
    `"set_sender_id"` | `"set_go_delay"` | `"status"`), `take_id`, `path_hash`,
    `path_spec`, `cached_take_id`, `spoof_sender_id`, `ui_blocker`
    (`"none"` | `"menu"` | `"chat"`).
  - `args.nk`: `cached_epoch`, `hold_go_b`, `go_delay_ms`.
  - `read.nk`: `cam_ready_b`, `sandbox_cam_active_b`, `hud_hidden_b`, `quickbar_hidden_b`,
    `menu_open_b` (`UIManager.IsMenuOpen(MENU_INGAME)` en
    `P:\scripts\3_game\tools\uimanager.c:154-157`), `chat_open_b`
    (`UIManager.IsMenuOpen(MENU_CHAT_INPUT)`), `pending_stop_b`, `late_go_ignored_n`,
    `stale_msg_ignored_n`, `cli_cached_epoch`, `last_ok_poll_ms`, `lease_ms`,
    `cam_yaw_deg`, `cam_pitch_deg`, `go_delay_ms`, `safety_exit_frame`,
    `safety_lease_age_ms`, `cli_state_seq` (T5/T6), `cli_state_recv_tick_ms` (T5).
  - `read.sk`: `loaded_path_hash`, `cli_cached_take_id`, `cli_cached_state`,
    `pending_stop_take_id`, `cli_cached_origin` (T5), `cli_cached_director_id` (T5).

- `take_arm` (`server`, trabajo `resource = "take"`, `page_size = 4`, `deadman = "stop"`):
  - `ncol` (15): `["srv_frame", "srv_tick_ms", "dtsum_ms", "take_dtsum_ms", "v1", "v2",
    "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11"]`.
  - `scol` (3): `["row_kind", "subject_id", "state_or_origin"]`.
  - Filas de control (`row_kind`):
    - `"arm_ready"`: `v1=allow_dmg_pre_b`, `v2=director_health`, `v3=pending_cues_n`,
      `v4=exp_emote_req_id_n`, `v5=sched_srv_tick_ms`, `v6=sched_cli_tick_ms`,
      `v7=future_cues_fired_n`.
    - `"go_sent"`: `v1=go_send_srv_frame`, `v2=go_send_tick_ms`, `v3=pending_cues_n`,
      `v4=exp_emote_req_id_n`, `v5=sched_srv_tick_ms`, `v6=sched_cli_tick_ms`,
      `v7=future_cues_fired_n`.
    - `"dispatch"`: `subject_id` en `{"actor_1", "actor_2"}`, `v1=dispatch_srv_frame`,
      `v2=order_tick_ms`.
    - `"stop_obs"` y `"post_stop_end"`: `v1=stop_srv_frame`, `v2=allow_dmg_during_b` (en
      `stop_obs`) o `allow_dmg_pre_b` (en `post_stop_end`), `v3=allow_dmg_post_b`,
      `v4=pending_cues_n`, `v5=exp_emote_req_id_n`, `v6=director_health`,
      `v7=director_alive_b`, `v8=transitions_n`, `v9=restorations_n`,
      `v10=future_cues_fired_n`, `v11=ack_sent_n`;
      `state_or_origin = "<take_state>:<take_origin>"`.

- `take_srv_observe_start` (`server`, trabajo `resource = "take_srv_watch"`,
  `page_size = 4`, `deadman = "continue"`):
  - Mismo `ncol` (15) y `scol` (3) que `take_arm`.
  - Filas crudas (`row_kind`):
    - `"act_sample"`: `subject_id` en `{"actor_1", "actor_2"}`, `v1..v3 = pos_x_m,
      pos_y_m, pos_z_m` (`Object.GetPosition()`), `v4 = move_speed`
      (`Human.GetCurrentMovementSpeed()` en `P:\scripts\3_game\human.c:468`),
      `v5 = cb_state_n` (`HumanCommandActionCallback.GetState()` en `human.c:383`,
      `STATE_NONE = 0`), `v6 = cb_cmd_id_n` (`CMD_GESTUREFB_CAMPFIRE = 1051`,
      `CMD_GESTUREMOD_GREETING = 1000`, `CMD_GESTUREFB_SALUTE = 1050` o `0`),
      `v7 = cb_emote_id_n` (`13`, `1`, `44` o `0` vía `DsbxGetCurrentGestureID()`),
      `v8 = cb_inst_n` (`m_DsbxCbInstId`), `v9 = exp_emote_req_id_n`
      (`DsbxGetPendingEmoteID()`), `v10 = pending_cues_n`, `v11 = future_cues_fired_n`.
    - `"director_sample"`: `subject_id = "director"`, `v1 = director_health`,
      `v2 = director_alive_b`, `v3 = allow_dmg_b` (`GetAllowDamage()`),
      `v4 = director_in_block_b`, `state_or_origin = take_state`.
    - `"melee_hit"`: `ZombieBase.FightLogic` (`P:\scripts\4_world\entities\creatures\infected\zombiebase.c:613`),
      `v1 = was_hit_b`, `v2 = target_is_director_b`, `v3 = alignable_b`,
      `v4 = zmb_dist_m`, `v5 = zmb_reach_m`, `v6 = allow_dmg_b`,
      `v7 = director_health`, `v8 = director_alive_b`, `v9 = director_in_block_b`,
      `v10 = dmg_ammo_b` (1 solo si `m_AmmoType` no es `""` ni `"Dummy_Light"` y sin
      bloqueo), `v11 = is_heavy_b`; `state_or_origin = m_AmmoType`.
    - `"take_terminal"` (R5-N5): `subject_id = take_id`, `state_or_origin =
      "<take_state>:<take_origin>"`, `v1 = term_frame`, `v2 = term_tick_ms`,
      `v3 = term_dtsum_ms`, `v4 = lease_age_ms`, `v5 = restore_frame`,
      `v6 = transitions_n`, `v7 = restorations_n`, `v8 = allow_dmg_post_b`,
      `v9 = pending_cues_n`, `v10 = exp_emote_req_id_n`, `v11 = future_cues_fired_n`.
    - `"cleanup_done"` (R5-N5): `subject_id = take_id`, `state_or_origin =
      "<take_state>:<take_origin>"`, `v1 = cleanup_end_frame`,
      `v2 = cleanup_end_tick_ms`, `v3 = allow_dmg_post_b`, `v4 = director_alive_b`.

- `take_cli_watch_start` (`client`, trabajo `resource = "take_cli_watch"`,
  `page_size = 4`, `deadman = "continue"`):
  - `ncol` (17): `["cli_frame", "cli_tick_ms", "dtsum_ms", "take_dtsum_ms",
    "sandbox_cam_active_b", "hud_hidden_b", "quickbar_hide_flag_b",
    "quickbar_widget_visible_b", "cam_x_m", "cam_y_m", "cam_z_m", "cam_yaw_deg",
    "cam_pitch_deg", "cam_fov_deg", "ack_req_epoch_n", "ack_cur_epoch_n", "aux_n"]`.
  - `scol` (9): `["row_kind", "detail", "ack_req_take_id", "ack_req_state",
    "ack_req_origin", "ack_resp_class", "ack_cur_take_id", "ack_cur_state",
    "ack_cur_origin"]`.
  - Filas (`row_kind`):
    - `"go_recv"`: llegada cruda en `OnRpc`, `aux_n = dispatch_srv_frame`,
      `ack_cur_epoch_n = state_seq` (o en `detail`).
    - `"go_deliver"`: entrega a la aplicación tras `go_delay_ms`, `aux_n =
      dispatch_srv_frame`.
    - `"frame_sample"`: cámara activa (`GetCurrentCameraPosition/Direction` en
      `P:\scripts\3_game\global\game.c:731-732`), HUD y barra (`QUICKBAR_HIDE = 256` en
      `P:\scripts\5_mission\gui\ingamehudvisibility.c:25` y `m_QuickbarWidget.IsVisible()`
      en `P:\scripts\1_core\proto\enwidgets.c:138`), `aux_n = press_edge_b + 2*hold_b +
      4*pending_stop_b`.
    - `"key_edge"`: `aux_n = key_act_count_n`, `detail` en `{"press_accepted",
      "ignored_no_take", "ignored_menu", "ignored_chat"}` (`LocalPress` / `LocalHold` en
      `P:\scripts\3_game\inputapi\uainput.c:60-62`).
    - `"rpc_stop_sent"`: `aux_n = retry_seq`, `detail = take_id`.
    - `"cli_safety_exit"` (R5-N5): `aux_n = safety_exit_frame`, `take_dtsum_ms =
      safety_lease_age_ms`, `detail` en `{"lease_expired", "take_terminal",
      "key_press"}`.
    - `"ack_recv"` (R5-N4, T6): `ack_req_epoch_n`, `ack_req_take_id`, `ack_req_state`,
      `ack_req_origin`, `ack_resp_class` (`"first_terminal"` | `"repeat_terminal"`),
      `ack_cur_epoch_n`, `ack_cur_take_id`, `ack_cur_state`, `ack_cur_origin`,
      `aux_n = cur_seq`.
    - `"take_state_recv"` (T5): `ack_cur_epoch_n = epoch`, `ack_cur_take_id = take_id`,
      `ack_cur_state = state`, `ack_cur_origin = origin`, `detail = director_id`,
      `aux_n = state_seq`.

- `take_stop` (`server`, instantáneo):
  - `args.sk`: `take_id`, `origin` (`"web"` | `"abort_test"`).
  - `read.nk`: `srv_frame`, `srv_tick_ms`, `dtsum_ms`, `take_dtsum_ms`, `transitions_n`,
    `restorations_n`, `allow_dmg_post_b`, `pending_cues_n`, `exp_emote_req_id_n`,
    `future_cues_fired_n`.
  - `read.sk`: `take_state`, `take_origin`.

- `act_observe` (`server`, de S3 `DSBX_QA_X_Actor`, invocado con `op = "snapshot"` por T12):
  - `read.sk`: `core_ver` (25 chars), `adapter_ver` (29 chars), `backend_class`.
  - `read.nk`: `backend_available_b` (1).
  - Tabla de filas de observación de actores y vestuario: `actor_id`, `real_class`,
    `slot_name`, `item_class`, `x_m`, `y_m`, `z_m` (y opcionalmente `net_id_low`,
    `net_id_high`, `alive_b`).

3. `samples/scenario.jsonl`
---------------------------
Registros JSONL emitidos por el runner con marcas `h_ms` del reloj monótono del arnés:
- `kind == "run_meta"`: `take_id_prefix` (`"<8hex>-"`), `calib_step_deg`, `calib_sign`
  (`1` o `-1`), `eps_look_deg`, `no_pulse_shift_deg`.
- `kind == "clock_pair"`: `peer` (`"server"` | `"client"`), `stage`, `rep`, `phase`
  (`"pre"` | `"post"`), `h_send_ms`, `h_recv_ms`, `peer_tick_ms`, `peer_frame`, `inst`,
  `epoch`.
- `kind == "take_meta"`: `stage` (`"S0a"` | `"S0b"` | `"S1"` | `"S1sel"` | `"S1c"` |
  `"S2"` | `"S3a"` | `"S3b"` | `"S3c"` | `"S3d"`), `rep` (int), `case_id` (str),
  `take_id` (str), `mode` (`"rpc"` | `"common_time"`), `contemp_yaw_ref_deg` (float),
  `allow_dmg_pre_b` (0/1), `go_delay_ms` (float), `h_start_ms` (float).
- `kind == "stimulus"`: `stim_type` (`"web_stop"` | `"key_press"` | `"key_hold"` |
  `"look_pulse"`), `stage`, `rep`, `case_id`, `take_id`, `h_ms`, `key`, `hold_ms`,
  `dx_px`, `sign`.
- `kind == "cut_window"`: `stage`, `case_id`, `take_id`, `peer`, `last_ok_poll_h_ms`,
  `last_ok_poll_tick_ms`, `reconnect_poll_h_ms`, `reconnect_poll_tick_ms`, `lease_ms`.
- `kind == "key_rejection"`: `stage`, `case_id`, `take_id`, `guard_take_id`,
  `reg_engine_uid`, `sender_engine_uid`, `payload_sender_id`, `h_ms`,
  `srv_tick_ms`, `cli_tick_ms`.
"""

import hashlib
import math
from pathlib import Path
import statistics
import subprocess

import f03_common
import gate_core
import wire

SPIKE_ID = "S-toma"
CHECK_IDS = (
    "TOM-01",
    "TOM-02",
    "TOM-03",
    "TOM-04",
    "TOM-05",
    "TOM-06",
    "TOM-07",
)

FIXTURE_REL_CANDIDATES = (
    "DayZSandbox_dev/qa/fixtures/s_toma_fixture.json",
    "qa/fixtures/s_toma_fixture.json",
)


def _chk(cid: str, status: str, reason: str = "", observed: dict | None = None) -> dict:
    det = str(reason or ("ok" if status == "pass" else ""))
    out = {
        "detail": det,
        "id": cid,
        "reason": str(reason or ""),
        "status": status,
    }
    if observed is not None:
        out["observed"] = observed
    return out


def _all_missing_checks(reason: str = ""):
    return [_chk(cid, "missing", reason=reason) for cid in CHECK_IDS]


def _make_inconcluso(reasons, checks=None):
    dedup = list(dict.fromkeys(str(r) for r in reasons if r))
    first_reason = dedup[0] if dedup else "inconclusive"
    if checks is None:
        checks = _all_missing_checks(reason=first_reason)
    return gate_core.make_verdict(
        SPIKE_ID,
        2,
        checks=checks,
        reasons=dedup or [first_reason],
    )


def _load_json_safe(path):
    try:
        return gate_core.read_json(Path(path))
    except Exception:
        return None


def _find_fixture_path(repo_root: Path) -> Path | None:
    for rel in FIXTURE_REL_CANDIDATES:
        cand = repo_root / rel
        if cand.is_file():
            return cand
    local_cand = Path(__file__).resolve().parent / "fixtures" / "s_toma_fixture.json"
    if local_cand.is_file():
        return local_cand
    return None


def _read_git_blob_bytes(repo_root: Path, git_head: str, rel_paths: tuple[str, ...]) -> bytes | None:
    if not isinstance(git_head, str) or not git_head.strip():
        return None
    toplevel = f03_common._git_toplevel(repo_root)
    if toplevel is None:
        return None
    for rel in rel_paths:
        try:
            proc = subprocess.run(
                ["git", "show", f"{git_head.strip()}:{rel}"],
                cwd=toplevel,
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                return proc.stdout
        except OSError:
            continue
    return None


def _unpack_payload_safe(obj):
    if not isinstance(obj, dict):
        return {}, {}, []
    if all(k in obj for k in wire.PAYLOAD_KEYS):
        try:
            unp = wire.unpack_payload(obj)
            return unp["str"], unp["num"], unp["rows"]
        except Exception:
            pass
    sk = obj.get("sk") or []
    sv = obj.get("sv") or []
    nk = obj.get("nk") or []
    nv = obj.get("nv") or []
    s_map = dict(zip(sk, sv)) if len(sk) == len(sv) else {}
    n_map = dict(zip(nk, nv)) if len(nk) == len(nv) else {}
    rows_out = []
    rows_n = int(obj.get("rows", 0) or 0)
    ncol = list(obj.get("ncol") or [])
    ncell = list(obj.get("ncell") or [])
    scol = list(obj.get("scol") or [])
    scell = list(obj.get("scell") or [])
    if rows_n > 0 and (ncol or scol):
        n_nc = len(ncol)
        n_sc = len(scol)
        if len(ncell) == rows_n * n_nc and len(scell) == rows_n * n_sc:
            for r_idx in range(rows_n):
                row = {}
                for c_idx, col in enumerate(ncol):
                    row[col] = ncell[r_idx * n_nc + c_idx]
                for c_idx, col in enumerate(scol):
                    row[col] = scell[r_idx * n_sc + c_idx]
                rows_out.append(row)
    return s_map, n_map, rows_out


def _catmull_rom_scalar(p0, p1, p2, p3, u):
    u2 = u * u
    u3 = u2 * u
    return 0.5 * (
        (2.0 * p1)
        + (-p0 + p2) * u
        + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * u2
        + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * u3
    )


def eval_catmull_rom_path(keyframes, t_ms):
    """Evalúa la curva analítica Catmull-Rom de los keyframes de la fixture en `t_ms`."""
    if not keyframes:
        return [0.0, 0.0, 0.0], 0.0, 0.0, 0.0
    kfs = sorted(keyframes, key=lambda k: float(k["t_ms"]))
    if t_ms <= float(kfs[0]["t_ms"]):
        kf = kfs[0]
        return list(kf["pos_m"]), float(kf["yaw_deg"]), float(kf["pitch_deg"]), float(kf["fov_deg"])
    if t_ms >= float(kfs[-1]["t_ms"]):
        kf = kfs[-1]
        return list(kf["pos_m"]), float(kf["yaw_deg"]), float(kf["pitch_deg"]), float(kf["fov_deg"])

    seg_idx = 0
    for idx in range(len(kfs) - 1):
        t0 = float(kfs[idx]["t_ms"])
        t1 = float(kfs[idx + 1]["t_ms"])
        if t0 <= t_ms <= t1:
            seg_idx = idx
            break

    k1 = kfs[seg_idx]
    k2 = kfs[seg_idx + 1]
    k0 = kfs[seg_idx - 1] if seg_idx > 0 else k1
    k3 = kfs[seg_idx + 2] if (seg_idx + 2) < len(kfs) else k2

    dt = float(k2["t_ms"]) - float(k1["t_ms"])
    u = (t_ms - float(k1["t_ms"])) / dt if dt > 0.0 else 0.0

    pos = [
        _catmull_rom_scalar(float(k0["pos_m"][c]), float(k1["pos_m"][c]), float(k2["pos_m"][c]), float(k3["pos_m"][c]), u)
        for c in range(3)
    ]
    yaw = _catmull_rom_scalar(float(k0["yaw_deg"]), float(k1["yaw_deg"]), float(k2["yaw_deg"]), float(k3["yaw_deg"]), u)
    pitch = _catmull_rom_scalar(float(k0["pitch_deg"]), float(k1["pitch_deg"]), float(k2["pitch_deg"]), float(k3["pitch_deg"]), u)
    fov = _catmull_rom_scalar(float(k0["fov_deg"]), float(k1["fov_deg"]), float(k2["fov_deg"]), float(k3["fov_deg"]), u)
    return pos, yaw, pitch, fov


def _dist3(a, b):
    return math.sqrt(
        (float(a[0]) - float(b[0])) ** 2
        + (float(a[1]) - float(b[1])) ** 2
        + (float(a[2]) - float(b[2])) ** 2
    )


def _reconstruct_ops_and_jobs(bridge_records):
    """Reconstruye las operaciones entregadas, sus primeros resultados y las páginas de cada job."""
    order_meta_by_op = {}
    polls_by_op = {}
    first_results = {}
    op_order = []
    hellos = []
    poll_events = []

    for idx, rec in enumerate(bridge_records):
        ev = rec.get("ev") or rec.get("event")
        if ev == "hello":
            if rec.get("http", 200) == 200 and rec.get("ok") is not False:
                hellos.append(rec)
        elif ev in ("enq", "deliver"):
            oid = rec.get("op_id")
            if isinstance(oid, str):
                order_meta_by_op[oid] = (idx, rec)
                if oid not in op_order:
                    op_order.append(oid)
        elif ev == "poll":
            poll_events.append(rec)
            for pid in rec.get("op_ids") or []:
                if isinstance(pid, str) and pid not in polls_by_op:
                    polls_by_op[pid] = (idx, rec)
                    if pid not in op_order:
                        op_order.append(pid)
            if isinstance(rec.get("op"), dict):
                op_obj = rec["op"]
                oid = op_obj.get("op_id")
                if isinstance(oid, str):
                    order_meta_by_op.setdefault(oid, (idx, op_obj))
                    polls_by_op.setdefault(oid, (idx, rec))
                    if oid not in op_order:
                        op_order.append(oid)
        elif ev == "result" and rec.get("http", 200) == 200:
            res_body = rec.get("result") if isinstance(rec.get("result"), dict) else rec.get("res")
            if isinstance(res_body, dict):
                oid = rec.get("op_id") or res_body.get("op_id")
                if isinstance(oid, str) and oid not in first_results:
                    first_results[oid] = (idx, rec, res_body)

    ops = []
    jobs = {}
    for op_id in op_order:
        if op_id not in first_results:
            continue
        r_idx, r_rec, res = first_results[op_id]
        p_idx, p_rec = polls_by_op.get(op_id, order_meta_by_op.get(op_id, (r_idx, r_rec)))
        _, m_rec = order_meta_by_op.get(op_id, (p_idx, p_rec))

        verb = m_rec.get("verb") or (p_rec.get("op", {}) if isinstance(p_rec.get("op"), dict) else {}).get("verb", "")
        peer = m_rec.get("peer") or p_rec.get("peer") or r_rec.get("peer") or ""
        inst = m_rec.get("inst") or p_rec.get("inst") or r_rec.get("inst") or ""
        raw_args = m_rec.get("args")
        if raw_args is None and isinstance(p_rec.get("op"), dict):
            raw_args = p_rec["op"].get("args")

        args_s, args_n, args_rows = _unpack_payload_safe(raw_args)
        read_s, read_n, read_rows = _unpack_payload_safe(res.get("read"))
        raw_status = str(res.get("status") or "")
        norm_status = "ok" if raw_status in ("done", "ok") else raw_status

        entry = {
            "op_id": op_id,
            "verb": verb,
            "peer": peer,
            "inst": inst,
            "poll_idx": p_idx,
            "res_idx": r_idx,
            "poll_rec": p_rec,
            "res_rec": r_rec,
            "status": norm_status,
            "raw_status": raw_status,
            "reason": str(res.get("reason") or ""),
            "dup": bool(res.get("dup", False)),
            "recv_ms": float(res.get("recv_ms", 0.0) or 0.0),
            "done_ms": float(res.get("done_ms", 0.0) or 0.0),
            "frame_recv": int(res.get("frame_recv", 0) or 0),
            "frame_done": int(res.get("frame_done", 0) or 0),
            "args_s": args_s,
            "args_n": args_n,
            "args_rows": args_rows,
            "read_s": read_s,
            "read_n": read_n,
            "read_rows": read_rows,
        }
        ops.append(entry)

        if verb in ("take_arm", "take_cli_watch_start", "take_srv_observe_start") and norm_status == "ok":
            job_id = read_s.get("job") or op_id
            jobs[job_id] = {
                "job_id": job_id,
                "start_op": entry,
                "verb": verb,
                "peer": peer,
                "take_id": args_s.get("take_id", ""),
                "mode": args_s.get("mode", "rpc"),
                "stop_inject": args_s.get("stop_inject", "none"),
                "args_s": args_s,
                "args_n": args_n,
                "state": read_s.get("state", "running"),
                "reason": str(res.get("reason") or read_s.get("reason") or ""),
                "end_tick_ms": float(read_n.get("end_tick_ms", 0.0) or 0.0),
                "onjobend_tick_ms": float(read_n.get("onjobend_tick_ms", 0.0) or 0.0),
                "released_tick_ms": float(read_n.get("released_tick_ms", 0.0) or 0.0),
                "pages": [],
                "rows": list(read_rows),
            }
        elif verb == "job_read" and norm_status == "ok":
            job_id = args_s.get("job") or read_s.get("job") or ""
            if job_id in jobs:
                j = jobs[job_id]
                j["pages"].append(entry)
                j["rows"].extend(read_rows)
                if read_s.get("state"):
                    j["state"] = read_s["state"]
                if read_s.get("reason"):
                    j["reason"] = read_s["reason"]
                for tk in ("end_tick_ms", "onjobend_tick_ms", "released_tick_ms"):
                    if tk in read_n and float(read_n[tk]) > 0.0:
                        j[tk] = float(read_n[tk])

    return ops, jobs, hellos, poll_events


def _verify_s_toma_integrity(part_dir, manifest, bridge_records, scenario_records, ops, jobs, hellos, repo_root=None):
    """Comprobaciones de integridad de la parte y propias de S-toma (§5, A3, R4-N13, R4-N14, T2, T12)."""
    root = f03_common._resolve_repo_root(repo_root)

    if not isinstance(manifest, dict):
        return False, ["params_unverified"]

    build = manifest.get("build")
    both = bool(manifest.get("both", True))
    req_peers = ("server", "client") if both else ("server",)

    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        return False, ["params_unverified"]

    if build in ("retail", "diag") and identity.get("git_dirty") is not False:
        return False, ["git_dirty"]

    peer_builds = identity.get("peer_builds")
    if not isinstance(peer_builds, dict) or any(peer_builds.get(r) != build for r in req_peers):
        return False, ["build_mismatch"]

    for role in req_peers:
        if not any(h.get("peer") == role for h in hellos):
            return False, ["build_mismatch"]

    for h in hellos:
        proto, h_build, _pv = f03_common._hello_proto_and_build(h)
        if proto != "qa0" or h_build != build:
            return False, ["build_mismatch"]

    git_head = identity.get("git_head") or manifest.get("git_head") or ""
    try:
        expected_stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=root)
    except f03_common.StampSourceUnavailableError:
        return False, ["stamp_source_unavailable"]

    expected_pv = f"dsbx-qa1+{expected_stamp}"
    if identity.get("probe_stamp") != expected_stamp:
        return False, ["artifact_unverified"]

    for h in hellos:
        _proto, _h_build, pv = f03_common._hello_proto_and_build(h)
        if not isinstance(pv, str) or pv == "dsbx-qa1+unstamped" or pv != expected_pv:
            return False, ["artifact_unverified"]

    ok_params, param_reason = f03_common.verify_eval_params_at_commit(manifest, repo_root=root)
    if not ok_params:
        return False, [param_reason]

    params = identity.get("params")
    if not isinstance(params, dict):
        return False, ["params_unverified"]

    wire_cap = params.get("wire_cap")
    if not isinstance(wire_cap, int) or isinstance(wire_cap, bool) or wire_cap <= 0:
        return False, ["params_unverified"]

    expected_adapter = params.get("adapter_ver_expected")
    if not isinstance(expected_adapter, str) or len(expected_adapter) != 29 or not expected_adapter.startswith("dsbx-qa-exp1+"):
        return False, ["params_unverified"]

    fixture_sha = params.get("fixture_sha256")
    if not isinstance(fixture_sha, str) or len(fixture_sha) != 64:
        return False, ["params_unverified"]

    fixture_path = _find_fixture_path(root)
    if fixture_path is None:
        return False, ["params_unverified"]
    blob = _read_git_blob_bytes(root, git_head, FIXTURE_REL_CANDIDATES)
    actual_fix_sha = hashlib.sha256(blob if blob is not None else fixture_path.read_bytes()).hexdigest()
    if fixture_sha != actual_fix_sha:
        return False, ["params_unverified"]

    for ev in bridge_records:
        kind = ev.get("ev") or ev.get("event")
        if kind == "wire_cap_exceeded":
            return False, ["wire_cap_exceeded"]
        if kind in ("poll", "result", "keepalive") and int(ev.get("body_len", 0) or 0) > wire_cap:
            return False, ["wire_cap_exceeded"]
        if kind == "lost":
            return False, ["result_lost"]
        if kind == "expire":
            return False, ["result_timeout"]

    for srec in scenario_records:
        if srec.get("ev") == "operator_timeout":
            return False, ["operator_timeout"]

    # T2: observer_capacity en cualquiera de los observadores -> INCONCLUSO
    for j in jobs.values():
        if j.get("reason") == "observer_capacity":
            return False, ["observer_capacity"]
        for r in j.get("rows", []):
            if r.get("row_kind") == "observer_capacity" or r.get("detail") == "observer_capacity":
                return False, ["observer_capacity"]
    for op in ops:
        if op.get("reason") == "observer_capacity" or op["read_s"].get("reason") == "observer_capacity":
            return False, ["observer_capacity"]

    # Verificar el observador de S3 (take_scene_prep(op="verify") y act_observe(op="snapshot"))
    verify_ops = [
        op for op in ops
        if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "verify" and op["status"] == "ok"
    ]
    act_obs_ops = [op for op in ops if op["verb"] == "act_observe" and op["status"] == "ok"]
    if not verify_ops or not act_obs_ops:
        return False, ["artifact_unverified"]
    for vop in verify_ops:
        if int(vop["read_n"].get("observer_ok_b", 0)) != 1:
            return False, ["artifact_unverified"]
        if vop["read_s"].get("adapter_ver") != expected_adapter:
            return False, ["artifact_unverified"]
        if vop["read_s"].get("observer_stamp") != expected_pv:
            return False, ["artifact_unverified"]
    for aop in act_obs_ops:
        # T12: act_observe debe invocarse con op = "snapshot"
        if aop["args_s"].get("op") != "snapshot":
            return False, ["act_observe_missing_snapshot_op"]
        if int(aop["read_n"].get("backend_available_b", 0)) != 1:
            return False, ["artifact_unverified"]
        if aop["read_s"].get("adapter_ver") != expected_adapter:
            return False, ["artifact_unverified"]
        if aop["read_s"].get("core_ver") != expected_pv:
            return False, ["artifact_unverified"]

    return True, []


def _calibrate_peer_clock(clock_pairs, peer, stage, rep):
    """Calibración por intervalos [theta_lo, theta_hi] para un peer y repetición (§5 TOM-01)."""
    pairs = [
        p for p in clock_pairs
        if p.get("peer") == peer and p.get("stage") == stage and int(p.get("rep", 0)) == int(rep)
    ]
    if len(pairs) < 2:
        return None, "insufficient_clock_pings"

    insts = {p.get("inst") for p in pairs if p.get("inst")}
    epochs = {int(p.get("epoch", 0)) for p in pairs if p.get("epoch") is not None}
    if len(insts) > 1 or len(epochs) > 1:
        return None, "peer_epoch_or_inst_changed_in_calibration"

    theta_lo = -math.inf
    theta_hi = math.inf
    for p in pairs:
        try:
            h_send = float(p["h_send_ms"])
            h_recv = float(p["h_recv_ms"])
            p_tick = float(p["peer_tick_ms"])
        except Exception:
            return None, "invalid_clock_ping_fields"
        if h_recv < h_send:
            return None, "negative_clock_ping_rtt"
        lo_i = h_send - p_tick
        hi_i = h_recv - p_tick
        if lo_i > theta_lo:
            theta_lo = lo_i
        if hi_i < theta_hi:
            theta_hi = hi_i

    if theta_lo > theta_hi:
        return None, "empty_clock_calibration_intersection"
    width = theta_hi - theta_lo
    if width > 40.0:
        return None, "clock_calibration_width_gt_40ms"

    return {
        "theta_lo": theta_lo,
        "theta_hi": theta_hi,
        "width": width,
        "inst": next(iter(insts), ""),
        "epoch": next(iter(epochs), 0),
    }, None


def _project_interval(tick_lo, tick_hi, cal):
    return tick_lo + cal["theta_lo"], tick_hi + cal["theta_hi"]


def _collect_take_bundles(ops, jobs, scenario_records):
    """Agrupa las operaciones, filas crudas, estímulos y metadatos por `take_id`."""
    run_meta = {}
    clock_pairs = []
    take_metas = {}
    take_order = []
    stimuli_by_take = {}
    cut_windows = []
    key_rejections = []

    for rec in scenario_records:
        k = rec.get("kind")
        if k == "run_meta":
            run_meta = dict(rec)
        elif k == "clock_pair":
            clock_pairs.append(rec)
        elif k == "take_meta":
            tid = rec.get("take_id", "")
            if tid:
                take_metas[tid] = dict(rec)
                if tid not in take_order:
                    take_order.append(tid)
        elif k == "stimulus":
            tid = rec.get("take_id", "")
            stimuli_by_take.setdefault(tid, []).append(rec)
        elif k == "cut_window":
            cut_windows.append(rec)
        elif k == "key_rejection":
            key_rejections.append(rec)

    arm_jobs_by_take = {}
    srv_obs_rows = []
    cli_watch_rows = []
    srv_obs_jobs = []
    cli_watch_jobs = []

    for j in jobs.values():
        v = j["verb"]
        if v == "take_arm":
            tid = j.get("take_id", "")
            arm_jobs_by_take.setdefault(tid, []).append(j)
        elif v == "take_srv_observe_start":
            srv_obs_jobs.append(j)
            for r in j["rows"]:
                r_copy = dict(r)
                r_copy["_watch_take_id"] = j.get("take_id", "")
                srv_obs_rows.append(r_copy)
        elif v == "take_cli_watch_start":
            cli_watch_jobs.append(j)
            for r in j["rows"]:
                r_copy = dict(r)
                r_copy["_watch_take_id"] = j.get("take_id", "")
                cli_watch_rows.append(r_copy)

    return {
        "run_meta": run_meta,
        "clock_pairs": clock_pairs,
        "take_metas": take_metas,
        "take_order": take_order,
        "stimuli_by_take": stimuli_by_take,
        "cut_windows": cut_windows,
        "key_rejections": key_rejections,
        "arm_jobs_by_take": arm_jobs_by_take,
        "srv_obs_rows": srv_obs_rows,
        "cli_watch_rows": cli_watch_rows,
        "srv_obs_jobs": srv_obs_jobs,
        "cli_watch_jobs": cli_watch_jobs,
    }


def _get_take_slice(take_id, bundle, ops):
    """Extrae las filas de `take_arm`, `take_srv_observe_start` y `take_cli_watch_start` de una toma."""
    meta = bundle["take_metas"].get(take_id, {})
    arm_list = bundle["arm_jobs_by_take"].get(take_id, [])
    arm_job = arm_list[0] if arm_list else None
    arm_rows = arm_job["rows"] if arm_job else []

    s_frame_lo = meta.get("srv_frame_lo")
    s_frame_hi = meta.get("srv_frame_hi")
    c_frame_lo = meta.get("cli_frame_lo")
    c_frame_hi = meta.get("cli_frame_hi")

    srv_rows = [
        r for r in bundle["srv_obs_rows"]
        if (
            r.get("_watch_take_id") == take_id
            or r.get("subject_id") == take_id
            or (s_frame_lo is not None and s_frame_hi is not None and s_frame_lo <= int(r.get("srv_frame", 0)) <= s_frame_hi)
        )
    ]
    cli_rows = [
        r for r in bundle["cli_watch_rows"]
        if (
            r.get("_watch_take_id") == take_id
            or r.get("ack_req_take_id") == take_id
            or (c_frame_lo is not None and c_frame_hi is not None and c_frame_lo <= int(r.get("cli_frame", 0)) <= c_frame_hi)
        )
    ]

    return {
        "take_id": take_id,
        "meta": meta,
        "arm_job": arm_job,
        "arm_rows": arm_rows,
        "srv_rows": srv_rows,
        "cli_rows": cli_rows,
        "stimuli": bundle["stimuli_by_take"].get(take_id, []),
    }


def _compute_rep_start_intervals(tslice, srv_cal, cli_cal, fixture):
    """Calcula los intervalos de comienzo C(r), A(actor_1, r) y A(actor_2, r) en h_ms (§5 TOM-01, R5-N10)."""
    arm_rows = tslice["arm_rows"]
    srv_rows = tslice["srv_rows"]
    cli_rows = tslice["cli_rows"]
    meta = tslice["meta"]
    mode = meta.get("mode") or (tslice["arm_job"]["mode"] if tslice["arm_job"] else "rpc")

    go_sent_rows = [r for r in arm_rows if r.get("row_kind") == "go_sent"]
    dispatch_rows = [r for r in arm_rows if r.get("row_kind") == "dispatch"]
    if not go_sent_rows:
        return None, "missing", "missing_go_sent"
    go_sent = go_sent_rows[0]
    go_send_frame = int(go_sent.get("v1", go_sent.get("srv_frame", 0)))
    go_send_tick = float(go_sent.get("v2", go_sent.get("srv_tick_ms", 0.0)))
    sched_srv_tick = float(go_sent.get("v5", 0.0))
    sched_cli_tick = float(go_sent.get("v6", 0.0))

    if go_send_frame <= 0 or go_send_tick <= 0.0:
        return None, "fail", "fabricated_take_without_raw_ticks"

    disp_by_actor = {r.get("subject_id"): r for r in dispatch_rows}
    if "actor_1" not in disp_by_actor or "actor_2" not in disp_by_actor:
        return None, "fail", "missing_actor_dispatch_rows"

    d1_frame = int(disp_by_actor["actor_1"].get("v1", disp_by_actor["actor_1"].get("srv_frame", 0)))
    d2_frame = int(disp_by_actor["actor_2"].get("v1", disp_by_actor["actor_2"].get("srv_frame", 0)))
    d1_tick = float(disp_by_actor["actor_1"].get("srv_tick_ms", 0.0))

    if mode == "rpc":
        if d1_frame != go_send_frame or d2_frame != go_send_frame:
            return None, "fail", "dispatch_frame_mismatch_in_rpc_mode"
    elif mode == "common_time":
        if d1_frame != d2_frame:
            return None, "fail", "dispatch_actors_not_same_frame_in_common_time"
        if d1_tick < sched_srv_tick:
            return None, "fail", "common_time_dispatch_before_scheduled_tick"
        if abs(float(disp_by_actor["actor_1"].get("take_dtsum_ms", 0.0))) > 1e-3:
            return None, "fail", "common_time_zero_not_at_dispatch"
        # R4-N3: comprobar que el frame anterior del servidor estaba por debajo de sched_srv_tick_ms
        prior_srv = [
            r for r in (arm_rows + srv_rows)
            if int(r.get("srv_frame", 0)) < d1_frame and float(r.get("srv_tick_ms", 0.0)) > 0.0
        ]
        if not prior_srv:
            return None, "missing", "common_time_missing_pre_dispatch_srv_sample"
        max_prior_tick = max(float(r.get("srv_tick_ms", 0.0)) for r in prior_srv)
        if max_prior_tick >= sched_srv_tick:
            return None, "fail", "common_time_not_first_frame_reaching_sched_tick"
    else:
        return None, "fail", "unknown_take_arm_mode"

    go_recv_rows = [r for r in cli_rows if r.get("row_kind") == "go_recv"]
    go_deliver_rows = [r for r in cli_rows if r.get("row_kind") == "go_deliver"]
    if not go_recv_rows or not go_deliver_rows:
        return None, "missing", "missing_go_recv_or_deliver"
    go_recv = go_recv_rows[0]
    go_deliver = go_deliver_rows[0]
    go_recv_tick = float(go_recv.get("cli_tick_ms", 0.0))
    go_deliver_tick = float(go_deliver.get("cli_tick_ms", 0.0))
    if go_recv_tick <= 0.0 or go_deliver_tick < go_recv_tick:
        return None, "fail", "invalid_go_recv_or_deliver_tick"

    if mode == "common_time":
        if go_deliver_tick > sched_cli_tick:
            return None, "fail", "common_time_go_delivered_after_scheduled_tick"
        if (sched_cli_tick - go_recv_tick) < 750.0:
            return None, "fail", "common_time_go_not_sent_ahead_of_schedule"

    # C(r): intervalo entre última frame_sample con sandbox_cam_active_b == 0 y primera con == 1
    # sin exigir que siga a go_recv (§5 TOM-01).
    frame_samples = sorted(
        [r for r in cli_rows if r.get("row_kind") == "frame_sample"],
        key=lambda r: int(r.get("cli_frame", 0)),
    )
    pos_cam_idx = None
    for idx, r in enumerate(frame_samples):
        if int(r.get("sandbox_cam_active_b", 0)) == 1:
            pos_cam_idx = idx
            break
    if pos_cam_idx is None:
        return None, "missing", "missing_cam_positive_sample"
    if pos_cam_idx == 0 or int(frame_samples[pos_cam_idx - 1].get("sandbox_cam_active_b", 1)) != 0:
        return None, "missing", "missing_cam_pre_start_negative_sample"

    cam_neg = frame_samples[pos_cam_idx - 1]
    cam_pos = frame_samples[pos_cam_idx]
    if mode == "common_time" and float(cam_pos.get("cli_tick_ms", 0.0)) < sched_cli_tick:
        return None, "fail", "common_time_cam_activated_before_scheduled_tick"

    c_lo_h, c_hi_h = _project_interval(
        float(cam_neg["cli_tick_ms"]),
        float(cam_pos["cli_tick_ms"]),
        cli_cal,
    )

    # A(actor_1, r): velocidad > 0 o desplazamiento >= 0.05 m respecto de su marca
    mark_1 = fixture["actors"][0]["mark_pos_m"]
    act1_samples = sorted(
        [r for r in srv_rows if r.get("row_kind") == "act_sample" and r.get("subject_id") == "actor_1"],
        key=lambda r: int(r.get("srv_frame", 0)),
    )
    pos_a1_idx = None
    for idx, r in enumerate(act1_samples):
        pos_r = [float(r.get("v1", 0.0)), float(r.get("v2", 0.0)), float(r.get("v3", 0.0))]
        disp_m = _dist3(pos_r, mark_1)
        speed = float(r.get("v4", 0.0))
        if speed > 0.01 or disp_m >= 0.05:
            pos_a1_idx = idx
            break
    if pos_a1_idx is None:
        return None, "missing", "missing_actor1_positive_sample"
    if pos_a1_idx == 0:
        return None, "missing", "missing_actor1_pre_start_negative_sample"
    a1_neg = act1_samples[pos_a1_idx - 1]
    a1_pos = act1_samples[pos_a1_idx]
    a1_lo_h, a1_hi_h = _project_interval(
        float(a1_neg["srv_tick_ms"]),
        float(a1_pos["srv_tick_ms"]),
        srv_cal,
    )

    # A(actor_2, r): instancia nueva respecto de referencia pre-GO, cb_emote_id_n == 13,
    # cb_cmd_id_n == 1051 y cb_state_n != STATE_NONE (0) (R4-N5).
    act2_samples = sorted(
        [r for r in srv_rows if r.get("row_kind") == "act_sample" and r.get("subject_id") == "actor_2"],
        key=lambda r: int(r.get("srv_frame", 0)),
    )
    pre_go_a2 = [r for r in act2_samples if int(r.get("srv_frame", 0)) < d2_frame]
    if not pre_go_a2:
        return None, "missing", "missing_actor2_pre_go_reference_sample"
    ref_inst_n = int(pre_go_a2[-1].get("v8", 0))

    pos_a2_idx = None
    for idx, r in enumerate(act2_samples):
        cb_state = int(r.get("v5", 0))
        cb_cmd = int(r.get("v6", 0))
        cb_emote = int(r.get("v7", 0))
        cb_inst = int(r.get("v8", 0))
        if cb_inst > ref_inst_n and cb_emote == 13 and cb_cmd == 1051 and cb_state != 0:
            pos_a2_idx = idx
            break
    if pos_a2_idx is None:
        return None, "missing", "missing_actor2_positive_sample"
    if pos_a2_idx == 0:
        return None, "missing", "missing_actor2_pre_start_negative_sample"
    a2_neg = act2_samples[pos_a2_idx - 1]
    a2_pos = act2_samples[pos_a2_idx]
    a2_lo_h, a2_hi_h = _project_interval(
        float(a2_neg["srv_tick_ms"]),
        float(a2_pos["srv_tick_ms"]),
        srv_cal,
    )

    # Desfase Δ_i(r) = A(actor_i, r) - C(r) en h_ms:
    # [delta_lo, delta_hi] = [a_lo_h - c_hi_h, a_hi_h - c_lo_h]
    d1_lo = a1_lo_h - c_hi_h
    d1_hi = a1_hi_h - c_lo_h
    d2_lo = a2_lo_h - c_hi_h
    d2_hi = a2_hi_h - c_lo_h

    # Entrega de la atribución causal: de la emisión del GO en servidor a go_deliver en cliente (R5-N6)
    go_send_lo_h, go_send_hi_h = _project_interval(go_send_tick, go_send_tick, srv_cal)
    go_deliv_lo_h, go_deliv_hi_h = _project_interval(go_deliver_tick, go_deliver_tick, cli_cal)
    deliv_lo = go_deliv_lo_h - go_send_hi_h
    deliv_hi = go_deliv_hi_h - go_send_lo_h
    deliv_mid = 0.5 * (deliv_lo + deliv_hi)

    # Desfase residual sin entrega: (A(actor_i, r) - go_send) - (C(r) - go_deliver)
    res1_lo = (float(a1_neg["srv_tick_ms"]) - go_send_tick) - (float(cam_pos["cli_tick_ms"]) - go_deliver_tick)
    res1_hi = (float(a1_pos["srv_tick_ms"]) - go_send_tick) - (float(cam_neg["cli_tick_ms"]) - go_deliver_tick)
    res2_lo = (float(a2_neg["srv_tick_ms"]) - go_send_tick) - (float(cam_pos["cli_tick_ms"]) - go_deliver_tick)
    res2_hi = (float(a2_pos["srv_tick_ms"]) - go_send_tick) - (float(cam_neg["cli_tick_ms"]) - go_deliver_tick)

    return {
        "c_interval_h": (c_lo_h, c_hi_h),
        "a1_interval_h": (a1_lo_h, a1_hi_h),
        "a2_interval_h": (a2_lo_h, a2_hi_h),
        "d1_interval_ms": (d1_lo, d1_hi),
        "d2_interval_ms": (d2_lo, d2_hi),
        "res1_interval_ms": (res1_lo, res1_hi),
        "res2_interval_ms": (res2_lo, res2_hi),
        "deliv_mid_ms": deliv_mid,
        "go_recv_tick_ms": go_recv_tick,
        "go_deliver_tick_ms": go_deliver_tick,
        "cam_neg": cam_neg,
        "cam_pos": cam_pos,
        "a1_neg": a1_neg,
        "a1_pos": a1_pos,
        "a2_neg": a2_neg,
        "a2_pos": a2_pos,
    }, "ok", None


def _series_variation_bounds(rep_metrics, key):
    """Calcula las cotas [var_lo, var_hi] de la variación entre las repeticiones de una serie."""
    intervals = [m[key] for m in rep_metrics]
    var_hi = 0.0
    var_lo = 0.0
    for i in range(len(intervals)):
        for j in range(len(intervals)):
            if i == j:
                continue
            hi_diff = intervals[i][1] - intervals[j][0]
            lo_diff = max(0.0, intervals[i][0] - intervals[j][1])
            if hi_diff > var_hi:
                var_hi = hi_diff
            if lo_diff > var_lo:
                var_lo = lo_diff
    return var_lo, var_hi


def _evaluate_series_tom01(stage_name, reps_expected, bundle, ops, fixture):
    """Evalúa una tanda de 3 repeticiones (`S1`, `S1sel` o `S1c`) para TOM-01."""
    take_ids = [
        tid for tid in bundle["take_order"]
        if bundle["take_metas"].get(tid, {}).get("stage") == stage_name
    ]
    if len(take_ids) < reps_expected:
        return None, "missing", f"{stage_name}_missing_repetitions"

    rep_metrics = []
    for idx, tid in enumerate(take_ids[:reps_expected], start=1):
        tslice = _get_take_slice(tid, bundle, ops)
        rep_no = int(tslice["meta"].get("rep", idx))
        srv_cal, srv_err = _calibrate_peer_clock(bundle["clock_pairs"], "server", stage_name, rep_no)
        if srv_cal is None:
            return None, "missing", f"{stage_name}_r{rep_no}_srv_{srv_err}"
        cli_cal, cli_err = _calibrate_peer_clock(bundle["clock_pairs"], "client", stage_name, rep_no)
        if cli_cal is None:
            return None, "missing", f"{stage_name}_r{rep_no}_cli_{cli_err}"

        term_rows = [r for r in tslice["srv_rows"] if r.get("row_kind") == "take_terminal"]
        if not term_rows:
            return None, "missing", f"{stage_name}_r{rep_no}_missing_take_terminal"

        m, st, reason = _compute_rep_start_intervals(tslice, srv_cal, cli_cal, fixture)
        if st != "ok":
            return None, st, f"{stage_name}_r{rep_no}_{reason}"
        rep_metrics.append(m)

    v1_lo, v1_hi = _series_variation_bounds(rep_metrics, "d1_interval_ms")
    v2_lo, v2_hi = _series_variation_bounds(rep_metrics, "d2_interval_ms")
    r1_lo, r1_hi = _series_variation_bounds(rep_metrics, "res1_interval_ms")
    r2_lo, r2_hi = _series_variation_bounds(rep_metrics, "res2_interval_ms")

    return {
        "reps": rep_metrics,
        "var_lo": max(v1_lo, v2_lo),
        "var_hi": max(v1_hi, v2_hi),
        "res_lo": max(r1_lo, r2_lo),
        "res_hi": max(r1_hi, r2_hi),
    }, "ok", None


def _eval_tom_01(bundle, ops, fixture):
    """TOM-01 — disparo conjunto y desfase por intervalos (§5 TOM-01, R4-N3..N5, R5-N6, R5-N10, T7, T9)."""
    s1_res, s1_st, s1_reason = _evaluate_series_tom01("S1", 3, bundle, ops, fixture)
    if s1_st != "ok":
        return _chk("TOM-01", s1_st, reason=s1_reason)

    # T9 y §5 TOM-01: S1sel (0/160/0 ms en cola de entrega del cliente) y S1c (3 reps common_time)
    # existen siempre en una corrida positiva completa y deben quedar acreditadas.
    s1sel_res, s1sel_st, s1sel_reason = _evaluate_series_tom01("S1sel", 3, bundle, ops, fixture)
    if s1sel_st != "ok":
        return _chk("TOM-01", s1sel_st, reason=f"s1sel_{s1sel_reason}")

    sel_delays = [
        m["go_deliver_tick_ms"] - m["go_recv_tick_ms"]
        for m in s1sel_res["reps"]
    ]
    if not (sel_delays[0] <= 20.0 and sel_delays[1] >= 120.0 and sel_delays[2] <= 20.0):
        return _chk("TOM-01", "fail", reason="s1sel_go_deliver_delay_pattern_invalid")
    if not (s1sel_res["var_lo"] > 100.0 and s1sel_res["res_hi"] <= 100.0):
        return _chk("TOM-01", "fail", reason="s1sel_causal_condition_not_accredited")

    s1c_res, s1c_st, s1c_reason = _evaluate_series_tom01("S1c", 3, bundle, ops, fixture)
    if s1c_st != "ok":
        return _chk("TOM-01", s1c_st, reason=f"s1c_{s1c_reason}")

    if s1_res["res_lo"] > 100.0:
        return _chk(
            "TOM-01",
            "fail",
            observed={"var_lo_ms": round(s1_res["var_lo"], 2), "res_lo_ms": round(s1_res["res_lo"], 2)},
            reason="rpc_local_variation_gt_100ms",
        )
    if s1c_res["res_lo"] > 100.0 or s1c_res["var_lo"] > 100.0:
        return _chk(
            "TOM-01",
            "fail",
            observed={"s1c_var_lo_ms": round(s1c_res["var_lo"], 2), "s1c_res_lo_ms": round(s1c_res["res_lo"], 2)},
            reason="common_time_variation_gt_100ms",
        )

    delivs_s1 = [m["deliv_mid_ms"] for m in s1_res["reps"]]
    deliv_spread_s1 = max(delivs_s1) - min(delivs_s1) if delivs_s1 else 0.0

    if s1_res["var_hi"] <= 100.0 and s1c_res["var_hi"] <= 100.0:
        return _chk(
            "TOM-01",
            "pass",
            observed={
                "active_mode": "rpc",
                "rpc_var_hi_ms": round(s1_res["var_hi"], 2),
                "common_time_var_hi_ms": round(s1c_res["var_hi"], 2),
            },
        )

    if s1_res["var_lo"] > 100.0 and s1_res["res_hi"] <= 100.0 and deliv_spread_s1 > 50.0:
        if s1c_res["var_hi"] <= 100.0:
            return _chk(
                "TOM-01",
                "pass",
                observed={
                    "active_mode": "common_time",
                    "rpc_var_lo_ms": round(s1_res["var_lo"], 2),
                    "common_time_var_hi_ms": round(s1c_res["var_hi"], 2),
                },
            )
        if s1c_res["var_lo"] > 100.0:
            return _chk("TOM-01", "fail", reason="common_time_fallback_exceeded_100ms")
        return _chk("TOM-01", "missing", reason="common_time_fallback_uncertain")

    if s1_res["var_lo"] > 100.0:
        return _chk("TOM-01", "fail", reason="variation_lower_bound_gt_100ms")

    return _chk(
        "TOM-01",
        "missing",
        observed={"var_lo_ms": round(s1_res["var_lo"], 2), "var_hi_ms": round(s1_res["var_hi"], 2)},
        reason="threshold_inside_uncertainty_interval",
    )


def _evaluate_stop_repetition(stage_name, rep_idx, tslice, bundle, expected_origin, fixture):
    """Evalúa una repetición de parada a los 3 s (S1 web o S2 tecla) para TOM-02."""
    run_meta = bundle["run_meta"]
    eps_look_deg = float(run_meta.get("eps_look_deg", 0.5))
    calib_step_deg = float(run_meta.get("calib_step_deg", 0.0))
    calib_sign = 1.0 if float(run_meta.get("calib_sign", 1.0)) >= 0.0 else -1.0
    if calib_step_deg < 2.0 * eps_look_deg or eps_look_deg <= 0.0:
        return "missing", "look_stimulus_uncalibrated"

    srv_cal, srv_err = _calibrate_peer_clock(bundle["clock_pairs"], "server", stage_name, rep_idx)
    if srv_cal is None:
        return "missing", f"{stage_name}_r{rep_idx}_srv_{srv_err}"
    cli_cal, cli_err = _calibrate_peer_clock(bundle["clock_pairs"], "client", stage_name, rep_idx)
    if cli_cal is None:
        return "missing", f"{stage_name}_r{rep_idx}_cli_{cli_err}"

    arm_rows = tslice["arm_rows"]
    srv_rows = tslice["srv_rows"]
    cli_rows = tslice["cli_rows"]
    meta = tslice["meta"]
    take_id = tslice["take_id"]

    term_rows = [r for r in srv_rows if r.get("row_kind") == "take_terminal" and r.get("subject_id") == take_id]
    if not term_rows:
        term_rows = [r for r in srv_rows if r.get("row_kind") == "take_terminal"]
    if not term_rows:
        return "fail", f"{stage_name}_r{rep_idx}_missing_terminal_or_interrupted"
    term_row = term_rows[0]
    expected_so = f"parada:{expected_origin}"
    if term_row.get("state_or_origin") != expected_so:
        return "fail", f"{stage_name}_r{rep_idx}_unexpected_terminal_{term_row.get('state_or_origin')}"

    stop_obs_rows = [r for r in arm_rows if r.get("row_kind") == "stop_obs"]
    if not stop_obs_rows:
        return "fail", f"{stage_name}_r{rep_idx}_missing_stop_obs"
    stop_obs = stop_obs_rows[0]
    if stop_obs.get("state_or_origin") != expected_so:
        return "fail", f"{stage_name}_r{rep_idx}_stop_obs_mismatch"

    stim_kind = "web_stop" if expected_origin == "web" else ("key_press", "key_hold")
    stims = [
        s for s in tslice["stimuli"]
        if (s.get("stim_type") == stim_kind if isinstance(stim_kind, str) else s.get("stim_type") in stim_kind)
    ]
    if not stims:
        return "missing", f"{stage_name}_r{rep_idx}_missing_stop_stimulus"
    t0_h = float(stims[0]["h_ms"])

    frame_samples = sorted(
        [r for r in cli_rows if r.get("row_kind") == "frame_sample"],
        key=lambda r: int(r.get("cli_frame", 0)),
    )
    if len(frame_samples) < 5:
        return "missing", f"{stage_name}_r{rep_idx}_insufficient_frame_samples"

    # E9 anti-fabricación: los deltas de cli_tick_ms no pueden ser todos idénticos/cero
    tick_deltas = [
        round(float(frame_samples[i + 1]["cli_tick_ms"]) - float(frame_samples[i]["cli_tick_ms"]), 4)
        for i in range(len(frame_samples) - 1)
    ]
    if any(d <= 0.0 for d in tick_deltas):
        return "fail", f"{stage_name}_r{rep_idx}_non_monotonic_frame_ticks"
    if len(tick_deltas) >= 10 and len(set(tick_deltas)) == 1:
        return "fail", f"{stage_name}_r{rep_idx}_fabricated_constant_frame_dt"

    pos_cam_idx = None
    for idx, r in enumerate(frame_samples):
        if int(r.get("sandbox_cam_active_b", 0)) == 1:
            pos_cam_idx = idx
            break
    if pos_cam_idx is None or pos_cam_idx == 0:
        return "missing", f"{stage_name}_r{rep_idx}_missing_cam_start"

    go_deliv_rows = [r for r in cli_rows if r.get("row_kind") == "go_deliver"]
    if not go_deliv_rows:
        return "missing", f"{stage_name}_r{rep_idx}_missing_go_deliver"
    go_deliv_frame = int(go_deliv_rows[0]["cli_frame"])
    pre_go_frames = [r for r in frame_samples if int(r["cli_frame"]) < go_deliv_frame]
    if not pre_go_frames:
        return "missing", f"{stage_name}_r{rep_idx}_missing_pre_go_frames"
    for r in pre_go_frames[:pos_cam_idx]:
        if int(r.get("sandbox_cam_active_b", 0)) != 0:
            return "fail", f"{stage_name}_r{rep_idx}_sandbox_cam_active_before_c_r"

    cli_tick_at_t0_lo = t0_h - cli_cal["theta_hi"]
    cli_tick_at_t0_hi = t0_h - cli_cal["theta_lo"]
    bracketing = [
        r for r in frame_samples
        if (cli_tick_at_t0_lo - 40.0) <= float(r["cli_tick_ms"]) <= (cli_tick_at_t0_hi + 40.0)
    ]
    if not bracketing:
        return "fail", f"{stage_name}_r{rep_idx}_stimulus_outside_take_trace"
    dtsum_lo = min(float(r["take_dtsum_ms"]) for r in bracketing)
    dtsum_hi = max(float(r["take_dtsum_ms"]) for r in bracketing)
    if dtsum_hi < 2850.0 or dtsum_lo > 3150.0:
        return "fail", f"{stage_name}_r{rep_idx}_stimulus_not_at_3000_pm_150ms"

    if expected_origin == "juego":
        win_samples = [
            r for r in frame_samples[pos_cam_idx:]
            if float(r["cli_tick_ms"]) <= cli_tick_at_t0_lo
        ]
        if not win_samples:
            return "missing", f"{stage_name}_r{rep_idx}_empty_c_r_to_t0_window"
        for r in win_samples:
            for req_col in ("sandbox_cam_active_b", "hud_hidden_b", "quickbar_hide_flag_b", "quickbar_widget_visible_b"):
                if req_col not in r:
                    return "missing", f"{stage_name}_r{rep_idx}_missing_col_{req_col}"
            if (
                int(r["sandbox_cam_active_b"]) != 1
                or int(r["hud_hidden_b"]) != 1
                or int(r["quickbar_hide_flag_b"]) != 1
                or int(r["quickbar_widget_visible_b"]) != 0
            ):
                return "fail", f"{stage_name}_r{rep_idx}_hud_or_quickbar_not_hidden_in_window"

        key_edges = [r for r in cli_rows if r.get("row_kind") == "key_edge" and r.get("detail") == "press_accepted"]
        if not key_edges:
            return "missing", f"{stage_name}_r{rep_idx}_key_dead_with_sandbox_cam"
        rpc_stops = [r for r in cli_rows if r.get("row_kind") == "rpc_stop_sent"]
        ack_recvs = [
            r for r in cli_rows
            if r.get("row_kind") == "ack_recv" and r.get("ack_req_take_id") == take_id
        ]
        if not rpc_stops or not ack_recvs:
            return "fail", f"{stage_name}_r{rep_idx}_missing_correlated_ack_recv"
        ack = ack_recvs[0]
        expected_epoch = int(meta.get("srv_epoch", srv_cal["epoch"]))
        if (
            int(ack.get("ack_req_epoch_n", 0)) != expected_epoch
            or ack.get("ack_req_take_id") != take_id
            or ack.get("ack_req_state") != "parada"
            or ack.get("ack_req_origin") != "juego"
            or ack.get("ack_resp_class") not in ("first_terminal", "repeat_terminal")
            or ack.get("ack_cur_state") != "parada"
            or ack.get("ack_cur_origin") != "juego"
        ):
            return "fail", f"{stage_name}_r{rep_idx}_ack_recv_columns_mismatch"
        if float(ack.get("cli_tick_ms", 0.0)) < float(rpc_stops[0].get("cli_tick_ms", 0.0)):
            return "fail", f"{stage_name}_r{rep_idx}_ack_before_rpc_stop_sent"
        if int(stop_obs.get("v11", 0)) < 1:
            return "fail", f"{stage_name}_r{rep_idx}_server_did_not_record_ack_sent"

    stop_srv_frame = int(stop_obs.get("v1", stop_obs.get("srv_frame", 0)))
    stop_srv_tick = float(stop_obs.get("srv_tick_ms", 0.0))
    prior_srv_ticks = [
        float(r["srv_tick_ms"]) for r in srv_rows
        if int(r.get("srv_frame", 0)) < stop_srv_frame and float(r.get("srv_tick_ms", 0.0)) > 0.0
    ]
    srv_stop_prev_tick = max(prior_srv_ticks) if prior_srv_ticks else stop_srv_tick
    srv_stop_lo_h, srv_stop_hi_h = _project_interval(srv_stop_prev_tick, stop_srv_tick, srv_cal)
    lat_srv_lo = srv_stop_lo_h - t0_h
    lat_srv_hi = srv_stop_hi_h - t0_h
    if lat_srv_lo <= 0.0:
        return "fail", f"{stage_name}_r{rep_idx}_fabricated_zero_or_negative_srv_stop_latency"
    if lat_srv_lo >= 1000.0:
        return "fail", f"{stage_name}_r{rep_idx}_srv_stop_latency_ge_1000ms"
    if lat_srv_hi >= 1000.0:
        return "missing", f"{stage_name}_r{rep_idx}_srv_stop_latency_uncertain"

    contemp_yaw_ref = meta.get("contemp_yaw_ref_deg")
    if contemp_yaw_ref is None:
        return "missing", f"{stage_name}_r{rep_idx}_missing_contemp_yaw_ref"
    contemp_yaw_ref = float(contemp_yaw_ref)

    f_rel_idx = None
    for idx in range(pos_cam_idx, len(frame_samples)):
        if int(frame_samples[idx].get("sandbox_cam_active_b", 1)) == 0:
            f_rel_idx = idx
            break
    if f_rel_idx is None:
        return "fail", f"{stage_name}_r{rep_idx}_camera_never_released"

    look_pulses = sorted(
        [s for s in tslice["stimuli"] if s.get("stim_type") == "look_pulse" and float(s.get("h_ms", 0.0)) >= t0_h],
        key=lambda s: float(s["h_ms"]),
    )
    if not look_pulses:
        return "missing", f"{stage_name}_r{rep_idx}_missing_look_pulses_after_t0"
    first_pulse_h = float(look_pulses[0]["h_ms"])

    t1_idx = None
    for idx in range(f_rel_idx, len(frame_samples)):
        r = frame_samples[idx]
        if int(r.get("sandbox_cam_active_b", 1)) != 0:
            continue
        r_lo_h, r_hi_h = _project_interval(float(r["cli_tick_ms"]), float(r["cli_tick_ms"]), cli_cal)
        dyaw = (float(r.get("cam_yaw_deg", 0.0)) - contemp_yaw_ref) * calib_sign
        if r_hi_h < first_pulse_h:
            if dyaw >= eps_look_deg:
                return "fail", f"{stage_name}_r{rep_idx}_yaw_shifted_before_look_pulse"
            continue
        if r_lo_h < first_pulse_h:
            continue
        if dyaw >= eps_look_deg:
            t1_idx = idx
            break
    if t1_idx is None:
        return "fail", f"{stage_name}_r{rep_idx}_no_attributed_look_response"

    t1_pos = frame_samples[t1_idx]
    t1_neg = frame_samples[t1_idx - 1] if t1_idx > 0 else t1_pos
    t1_lo_h, t1_hi_h = _project_interval(float(t1_neg["cli_tick_ms"]), float(t1_pos["cli_tick_ms"]), cli_cal)
    lat_cli_lo = t1_lo_h - t0_h
    lat_cli_hi = t1_hi_h - t0_h
    if lat_cli_lo <= 0.0:
        return "fail", f"{stage_name}_r{rep_idx}_fabricated_zero_or_negative_cli_stop_latency"
    if lat_cli_lo >= 1000.0:
        return "fail", f"{stage_name}_r{rep_idx}_cli_control_recovery_ge_1000ms"
    if lat_cli_hi >= 1000.0:
        return "missing", f"{stage_name}_r{rep_idx}_cli_control_recovery_uncertain"

    # E9: comprobar movimiento continuo y parada real de actor_1
    mark_1 = fixture["actors"][0]["mark_pos_m"]
    act1_samples = sorted(
        [r for r in srv_rows if r.get("row_kind") == "act_sample" and r.get("subject_id") == "actor_1"],
        key=lambda r: int(r.get("srv_frame", 0)),
    )
    pre_stop_a1 = [r for r in act1_samples if int(r.get("srv_frame", 0)) <= stop_srv_frame]
    post_stop_a1 = [r for r in act1_samples if int(r.get("srv_frame", 0)) > stop_srv_frame]
    if not pre_stop_a1 or not post_stop_a1:
        return "fail", f"{stage_name}_r{rep_idx}_missing_actor1_samples"
    max_disp_a1 = max(_dist3([r.get("v1", 0.0), r.get("v2", 0.0), r.get("v3", 0.0)], mark_1) for r in pre_stop_a1)
    if max_disp_a1 < 0.3:
        return "fail", f"{stage_name}_r{rep_idx}_actor1_did_not_advance_before_stop"
    stop_pos_a1 = [post_stop_a1[0].get("v1", 0.0), post_stop_a1[0].get("v2", 0.0), post_stop_a1[0].get("v3", 0.0)]
    for r in post_stop_a1[1:]:
        if float(r.get("v4", 0.0)) > 0.05 or _dist3([r.get("v1", 0.0), r.get("v2", 0.0), r.get("v3", 0.0)], stop_pos_a1) > 0.1:
            return "fail", f"{stage_name}_r{rep_idx}_actor1_continued_moving_after_stop"

    # Precondición de gesto pendiente antes del stop y vigilancia posterior hasta take_dtsum_ms >= 4800 ms (R4-N10, R5-N3, T10)
    act2_samples = sorted(
        [r for r in srv_rows if r.get("row_kind") == "act_sample" and r.get("subject_id") == "actor_2"],
        key=lambda r: int(r.get("srv_frame", 0)),
    )
    pre_stop_a2 = [r for r in act2_samples if int(r.get("srv_frame", 0)) < stop_srv_frame]
    pending_observed = any(
        int(r.get("v9", 0)) == 1 and int(r.get("v7", 0)) == 13 and int(r.get("v10", 0)) >= 1
        for r in pre_stop_a2
    )
    if not pending_observed:
        return "missing", f"{stage_name}_r{rep_idx}_pending_gesture_precondition_unobserved"

    post_stop_a2 = [r for r in act2_samples if int(r.get("srv_frame", 0)) >= stop_srv_frame]
    if not post_stop_a2:
        return "missing", f"{stage_name}_r{rep_idx}_missing_post_stop_actor2_samples"

    final_4800_idx = None
    for idx, r in enumerate(post_stop_a2):
        if float(r.get("take_dtsum_ms", 0.0)) >= 4800.0:
            final_4800_idx = idx
            break
    if final_4800_idx is None:
        return "missing", f"{stage_name}_r{rep_idx}_post_stop_coverage_lt_4800ms"

    watch_slice = post_stop_a2[: final_4800_idx + 1]
    for i in range(len(watch_slice) - 1):
        df = int(watch_slice[i + 1]["srv_frame"]) - int(watch_slice[i]["srv_frame"])
        if df != 1:
            return "fail", f"{stage_name}_r{rep_idx}_post_stop_srv_frame_gap"
        dt_step = float(watch_slice[i + 1]["srv_tick_ms"]) - float(watch_slice[i]["srv_tick_ms"])
        if dt_step > 100.0:
            return "missing", f"{stage_name}_r{rep_idx}_post_stop_low_freq_gap"

    for r in watch_slice:
        cb_cmd = int(r.get("v6", 0))
        cb_emote = int(r.get("v7", 0))
        exp_req = int(r.get("v9", 0))
        pend_cues = int(r.get("v10", 0))
        fut_fired = int(r.get("v11", 0))
        if exp_req != 0 or pend_cues != 0 or fut_fired != 0:
            return "fail", f"{stage_name}_r{rep_idx}_pending_or_future_cues_not_cancelled"
        if cb_emote in (1, 44) or cb_cmd in (1000, 1050):
            return "fail", f"{stage_name}_r{rep_idx}_cancelled_gesture_executed_after_stop"

    return "pass", None


def _eval_tom_02(bundle, ops, fixture):
    """TOM-02 — paradas a los 3 s (3 web en S1, 3 tecla en S2), control en < 1 s y cues (§5 TOM-02)."""
    for stage_name, expected_origin in (("S1", "web"), ("S2", "juego")):
        take_ids = [
            tid for tid in bundle["take_order"]
            if bundle["take_metas"].get(tid, {}).get("stage") == stage_name
        ]
        if len(take_ids) < 3:
            restart_ops = [
                op for op in ops
                if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "restart_epoch"
            ]
            for tid in take_ids:
                ts = _get_take_slice(tid, bundle, ops)
                term_rows = [r for r in ts["srv_rows"] if r.get("row_kind") == "take_terminal"]
                if not term_rows or float(term_rows[0].get("v3", 0.0)) < 2800.0:
                    return _chk("TOM-02", "fail", reason=f"{stage_name}_interrupted_before_3s")
            if restart_ops and stage_name == "S1":
                return _chk("TOM-02", "fail", reason="peer_restarted_during_take")
            return _chk("TOM-02", "missing", reason=f"{stage_name}_missing_3_repetitions")

        for idx, tid in enumerate(take_ids[:3], start=1):
            tslice = _get_take_slice(tid, bundle, ops)
            rep_no = int(tslice["meta"].get("rep", idx))
            st, reason = _evaluate_stop_repetition(stage_name, rep_no, tslice, bundle, expected_origin, fixture)
            if st != "pass":
                return _chk("TOM-02", st, reason=reason)

    return _chk("TOM-02", "pass")


def _eval_tom_03(bundle, ops, hellos, fixture):
    """TOM-03 — tecla fijada sin conflicto, reasignación tras recarga y pulsación mantenida (§5 TOM-03, R5-N13)."""
    expected_def = fixture.get("expected_default_key", "kF9")
    candidates = fixture.get("candidate_keys", ["kF9", "kF10", "kBackslash", "kRBracket"])

    key_ops = [op for op in ops if op["verb"] == "take_key_op" and op["status"] == "ok"]
    audits = [op for op in key_ops if op["args_s"].get("op") == "audit_candidates"]
    binds = [op for op in key_ops if op["args_s"].get("op") == "bind_key"]
    restores = [op for op in key_ops if op["args_s"].get("op") == "restore_bindings"]

    if not audits or len(binds) < 2 or not restores:
        return _chk("TOM-03", "missing", reason="missing_key_op_sequence")

    audit = audits[0]
    if audit["args_s"].get("action_name") != fixture.get("action_name", "UADsbxQaTakeStop"):
        return _chk("TOM-03", "fail", reason="wrong_action_name")
    if int(audit["read_n"].get("input_id", 0)) <= 0:
        return _chk("TOM-03", "fail", reason="input_id_not_registered")
    if not audit["read_s"].get("build_version"):
        return _chk("TOM-03", "fail", reason="missing_build_version")

    sel_def = audit["read_s"].get("selected_def_key", "")
    sel_alt = audit["read_s"].get("selected_alt_key", "")
    if sel_def != expected_def:
        return _chk("TOM-03", "fail", reason="default_key_conflict")
    if int(audit["read_n"].get("conflict_count_def", 0)) != 0 or int(audit["read_n"].get("conflict_count_alt", 0)) != 0:
        return _chk("TOM-03", "fail", reason="default_key_conflict")
    if audit["read_s"].get("conflicting_actions_csv", "") != "":
        return _chk("TOM-03", "fail", reason="default_key_conflict")
    if sel_alt == sel_def or sel_alt not in candidates or int(audit["read_n"].get("free_candidates_n", 0)) < 2:
        return _chk("TOM-03", "fail", reason="insufficient_free_candidate_keys")

    alt_binds = [b for b in binds if b["args_s"].get("target_key") == sel_alt]
    if not alt_binds or int(alt_binds[0]["read_n"].get("export_called_b", 0)) != 1:
        return _chk("TOM-03", "fail", reason="alt_key_bind_did_not_export")
    if int(alt_binds[0]["read_n"].get("conflict_count_alt", 0)) != 0:
        return _chk("TOM-03", "fail", reason="conflicting_candidate_bound")

    cli_hellos = [h for h in hellos if h.get("peer") == "client"]
    cli_insts = [h.get("inst") for h in cli_hellos if h.get("inst")]
    if len(set(cli_insts)) < 2:
        return _chk("TOM-03", "fail", reason="client_not_reloaded_between_s0a_and_s0b")

    s0a_takes = [tid for tid in bundle["take_order"] if bundle["take_metas"].get(tid, {}).get("stage") == "S0a"]
    s0b_takes = [tid for tid in bundle["take_order"] if bundle["take_metas"].get(tid, {}).get("stage") == "S0b"]
    if not s0a_takes or not s0b_takes:
        return _chk("TOM-03", "missing", reason="missing_s0a_or_s0b_take")

    keydef_tid = s0a_takes[0]
    keyreb_tid = s0b_takes[0]
    if not keydef_tid.endswith("keydef") or not keyreb_tid.endswith("keyreb"):
        return _chk("TOM-03", "fail", reason="short_take_label_mismatch_s0")

    s0b_slice = _get_take_slice(keyreb_tid, bundle, ops)
    if s0b_slice["arm_job"] and s0b_slice["cli_rows"]:
        s0b_stims = sorted(s0b_slice["stimuli"], key=lambda s: float(s.get("h_ms", 0.0)))
        old_key_stims = [s for s in s0b_stims if s.get("key") == sel_def]
        new_key_stims = [s for s in s0b_stims if s.get("key") == sel_alt]
        if not old_key_stims or not new_key_stims:
            return _chk("TOM-03", "fail", reason="missing_old_or_new_key_stim_in_s0b")
        edges_s0b = [
            r for r in s0b_slice["cli_rows"]
            if r.get("row_kind") == "key_edge" and r.get("detail") == "press_accepted"
        ]
        if len(edges_s0b) != 1 or float(edges_s0b[0].get("take_dtsum_ms", 0.0)) < 1000.0:
            return _chk("TOM-03", "fail", reason="old_key_triggered_or_new_key_failed_in_s0b")
        term_s0b = [r for r in s0b_slice["srv_rows"] if r.get("row_kind") == "take_terminal"]
        if not term_s0b or term_s0b[0].get("state_or_origin") != "parada:juego":
            return _chk("TOM-03", "fail", reason="s0b_not_stopped_by_new_key")

    s2_takes = [tid for tid in bundle["take_order"] if bundle["take_metas"].get(tid, {}).get("stage") == "S2"]
    if len(s2_takes) < 2:
        return _chk("TOM-03", "missing", reason="missing_s2_r2_for_hold_check")
    s2_r2_slice = _get_take_slice(s2_takes[1], bundle, ops)
    hold_stims = [
        s for s in s2_r2_slice["stimuli"]
        if s.get("stim_type") in ("key_hold", "key_press") and float(s.get("hold_ms", 0.0)) >= 600.0
    ]
    if not hold_stims:
        return _chk("TOM-03", "fail", reason="missing_600ms_hold_stimulus_in_s2_r2")
    edges_r2 = [
        r for r in s2_r2_slice["cli_rows"]
        if r.get("row_kind") == "key_edge" and r.get("detail") == "press_accepted"
    ]
    if len(edges_r2) != 1 or int(edges_r2[0].get("aux_n", 0)) != 1:
        return _chk("TOM-03", "fail", reason="held_key_produced_multiple_activations")

    if sel_def not in restores[-1]["read_s"].get("bound_keys_csv", ""):
        return _chk("TOM-03", "fail", reason="default_key_not_restored")

    return _chk("TOM-03", "pass")


def _eval_tom_04(bundle, ops):
    """TOM-04 — protección del director y restauración exacta en la frontera terminal (§5 TOM-04, H20, R4-N11, R5-N1, T11)."""
    s1_takes = [
        tid for tid in bundle["take_order"]
        if bundle["take_metas"].get(tid, {}).get("stage") == "S1"
    ]
    if len(s1_takes) < 3:
        return _chk("TOM-04", "missing", reason="s1_missing_3_repetitions")

    expected_pre_by_rep = {1: 1, 2: 0, 3: 1}
    any_valid_melee = False

    for idx, tid in enumerate(s1_takes[:3], start=1):
        tslice = _get_take_slice(tid, bundle, ops)
        rep_no = int(tslice["meta"].get("rep", idx))
        arm_rows = tslice["arm_rows"]
        srv_rows = tslice["srv_rows"]

        arm_ready_rows = [r for r in arm_rows if r.get("row_kind") == "arm_ready"]
        go_sent_rows = [r for r in arm_rows if r.get("row_kind") == "go_sent"]
        stop_obs_rows = [r for r in arm_rows if r.get("row_kind") == "stop_obs"]
        post_end_rows = [r for r in arm_rows if r.get("row_kind") == "post_stop_end"]
        term_rows = [r for r in srv_rows if r.get("row_kind") == "take_terminal" and r.get("subject_id") == tid]
        if not term_rows:
            term_rows = [r for r in srv_rows if r.get("row_kind") == "take_terminal"]

        if not arm_ready_rows or not go_sent_rows or not term_rows:
            return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_missing_control_or_terminal_rows")

        arm_ready = arm_ready_rows[0]
        go_sent = go_sent_rows[0]
        term_row = term_rows[0]

        pre_dmg_b = int(arm_ready.get("v1", -1))
        health_pre = float(arm_ready.get("v2", 1.0))
        if pre_dmg_b != expected_pre_by_rep.get(rep_no, pre_dmg_b):
            return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_unexpected_allow_dmg_pre")

        eff_start_frame = int(go_sent.get("v1", go_sent.get("srv_frame", 0)))
        term_frame = int(term_row.get("v1", term_row.get("srv_frame", 0)))
        restore_frame = int(term_row.get("v5", term_frame))
        frontier_frame = max(term_frame, restore_frame)

        dir_samples = sorted(
            [
                r for r in srv_rows
                if r.get("row_kind") == "director_sample" and int(r.get("srv_frame", 0)) >= eff_start_frame
            ],
            key=lambda r: int(r.get("srv_frame", 0)),
        )
        melee_hits = sorted(
            [
                r for r in srv_rows
                if r.get("row_kind") == "melee_hit" and int(r.get("srv_frame", 0)) >= eff_start_frame
            ],
            key=lambda r: int(r.get("srv_frame", 0)),
        )
        if not dir_samples or not melee_hits:
            return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_missing_dir_or_melee_samples")

        rep_valid_hit = False
        for mh in melee_hits:
            mf = int(mh.get("srv_frame", 0))
            if mf < frontier_frame:
                if int(mh.get("v6", 1)) != 0:
                    return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_allow_dmg_true_on_melee_hit")
                if int(mh.get("v8", 0)) != 1:
                    return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_gk07_director_died")
                if float(mh.get("v7", 0.0)) + 1e-5 < health_pre:
                    return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_gk07_health_dropped_with_allow_dmg_0")
            if (
                int(mh.get("v1", 0)) == 1
                and int(mh.get("v2", 0)) == 1
                and int(mh.get("v3", 0)) == 1
                and float(mh.get("v4", 99.0)) <= float(mh.get("v5", 0.0))
                and int(mh.get("v9", 1)) == 0
                and int(mh.get("v10", 0)) == 1
                and mh.get("state_or_origin", "") not in ("", "Dummy_Light")
            ):
                rep_valid_hit = True
                any_valid_melee = True

        if not rep_valid_hit:
            return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_melee_only_blocked_or_dummy_light")

        for ds in dir_samples:
            sf = int(ds.get("srv_frame", 0))
            if sf < frontier_frame:
                if int(ds.get("v3", 1)) != 0:
                    return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_allow_dmg_true_before_frontier")
                if int(ds.get("v2", 0)) != 1:
                    return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_gk07_director_not_alive")
                if float(ds.get("v1", 0.0)) + 1e-5 < health_pre:
                    return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_gk07_director_health_decreased")
            else:
                if int(ds.get("v3", -1)) != pre_dmg_b:
                    return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_allow_dmg_not_restored_after_frontier")

        if stop_obs_rows:
            so = stop_obs_rows[0]
            if int(so.get("v2", 1)) != 0:
                return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_stop_obs_allow_dmg_during_not_0")
            if int(so.get("v3", -1)) != pre_dmg_b:
                return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_stop_obs_allow_dmg_post_mismatch")

        if post_end_rows:
            pe = post_end_rows[0]
            if int(pe.get("v3", -1)) != pre_dmg_b:
                return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_post_stop_end_allow_dmg_mismatch")

        if int(term_row.get("v8", -1)) != pre_dmg_b:
            return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_terminal_allow_dmg_post_mismatch")

    if not any_valid_melee:
        return _chk("TOM-04", "missing", reason="no_accredited_harmful_melee_hit")

    return _chk("TOM-04", "pass")


def _correlate_and_verify_b6_reset_obs(obs_rows, fixture):
    """Compara en Python la observación cruda tras cada reset contra la fixture (§3.2, §5 TOM-05, R5-N9, E9)."""
    if not obs_rows:
        return "missing", "missing_b6_reset_observation_rows"

    by_actor = {}
    for r in obs_rows:
        aid = r.get("actor_id", "")
        by_actor.setdefault(aid, []).append(r)

    expected_actors = fixture.get("actors", [])
    matched_keys = set()

    for exp_a in expected_actors:
        exp_id = exp_a["actor_id"]
        exp_cls = exp_a["real_class"]
        exp_mark = exp_a["mark_pos_m"]
        exp_wardrobe = {w["slot_name"]: w["item_class"] for w in exp_a.get("wardrobe", [])}

        chosen_key = None
        if exp_id in by_actor:
            chosen_key = exp_id
        else:
            candidates = []
            for k, rows_k in by_actor.items():
                if not rows_k or rows_k[0].get("real_class") != exp_cls:
                    continue
                pos_k = [
                    float(rows_k[0].get("x_m", 0.0)),
                    float(rows_k[0].get("y_m", 0.0)),
                    float(rows_k[0].get("z_m", 0.0)),
                ]
                candidates.append((_dist3(pos_k, exp_mark), k))
            candidates.sort(key=lambda x: x[0])
            if candidates and candidates[0][0] < 1.5 and candidates[0][1] not in matched_keys:
                chosen_key = candidates[0][1]

        if chosen_key is None:
            return "fail", f"b6_reset_actor_not_found_{exp_id}"
        matched_keys.add(chosen_key)

        rows_a = by_actor[chosen_key]
        if rows_a[0].get("real_class") != exp_cls:
            return "fail", f"b6_reset_persona_mismatch_{exp_id}"
        pos_a = [
            float(rows_a[0].get("x_m", 0.0)),
            float(rows_a[0].get("y_m", 0.0)),
            float(rows_a[0].get("z_m", 0.0)),
        ]
        if _dist3(pos_a, exp_mark) >= 1.5:
            return "fail", f"b6_reset_mark_distance_ge_1_5m_{exp_id}"

        if "net_id_low" in rows_a[0] or "net_id_high" in rows_a[0]:
            if int(rows_a[0].get("net_id_low", 0)) == 0 and int(rows_a[0].get("net_id_high", 0)) == 0:
                return "fail", f"b6_reset_zero_entity_net_id_{exp_id}"

        obs_wardrobe = {
            r.get("slot_name", ""): r.get("item_class", "")
            for r in rows_a
            if r.get("slot_name")
        }
        if obs_wardrobe != exp_wardrobe:
            return "fail", f"b6_reset_wardrobe_mismatch_{exp_id}"

    if len(by_actor) != len(expected_actors):
        return "fail", "b6_reset_actor_count_mismatch"

    return "pass", None


def _interp_pos_at_t(samples, t_ms):
    if not samples:
        return [0.0, 0.0, 0.0]
    if t_ms <= float(samples[0]["take_dtsum_ms"]):
        s = samples[0]
        return [float(s["cam_x_m"]), float(s["cam_y_m"]), float(s["cam_z_m"])]
    if t_ms >= float(samples[-1]["take_dtsum_ms"]):
        s = samples[-1]
        return [float(s["cam_x_m"]), float(s["cam_y_m"]), float(s["cam_z_m"])]
    for i in range(len(samples) - 1):
        t0 = float(samples[i]["take_dtsum_ms"])
        t1 = float(samples[i + 1]["take_dtsum_ms"])
        if t0 <= t_ms <= t1:
            u = (t_ms - t0) / (t1 - t0) if t1 > t0 else 0.0
            return [
                float(samples[i]["cam_x_m"]) + u * (float(samples[i + 1]["cam_x_m"]) - float(samples[i]["cam_x_m"])),
                float(samples[i]["cam_y_m"]) + u * (float(samples[i + 1]["cam_y_m"]) - float(samples[i]["cam_y_m"])),
                float(samples[i]["cam_z_m"]) + u * (float(samples[i + 1]["cam_z_m"]) - float(samples[i]["cam_z_m"])),
            ]
    s = samples[-1]
    return [float(s["cam_x_m"]), float(s["cam_y_m"]), float(s["cam_z_m"])]


def _eval_tom_05(bundle, ops, fixture):
    """TOM-05 — 3 tomas con reset crudo en Python y camino Catmull-Rom B6 (§5 TOM-05, R5-N9, T1)."""
    s1_takes = [
        tid for tid in bundle["take_order"]
        if bundle["take_metas"].get(tid, {}).get("stage") == "S1"
    ]
    if len(s1_takes) < 3:
        return _chk("TOM-05", "missing", reason="s1_missing_3_repetitions")

    act_obs_ops = [op for op in ops if op["verb"] == "act_observe" and op["status"] == "ok"]
    if len(act_obs_ops) < 3:
        return _chk("TOM-05", "missing", reason="missing_act_observe_per_s1_reset")
    for idx, aop in enumerate(act_obs_ops[:3], start=1):
        st, reason = _correlate_and_verify_b6_reset_obs(aop["read_rows"], fixture)
        if st != "pass":
            return _chk("TOM-05", st, reason=f"s1_r{idx}_{reason}")

    perturb_ops = [
        op for op in ops
        if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "perturb_fixture" and op["status"] == "ok"
    ]
    if not perturb_ops:
        return _chk("TOM-05", "fail", reason="missing_perturb_fixture_before_r2_reset")

    keyframes = fixture["camera_path"]["keyframes"]
    path_dur = float(fixture["camera_path"]["duration_ms"])
    if path_dur < 4000.0:
        return _chk("TOM-05", "fail", reason="camera_path_duration_lt_4000ms")

    traces_by_rep = []
    all_sampled_t = set()

    for idx, tid in enumerate(s1_takes[:3], start=1):
        tslice = _get_take_slice(tid, bundle, ops)
        active_samples = sorted(
            [
                r for r in tslice["cli_rows"]
                if r.get("row_kind") == "frame_sample"
                and int(r.get("sandbox_cam_active_b", 0)) == 1
                and 0.0 <= float(r.get("take_dtsum_ms", -1.0)) <= 3000.0
            ],
            key=lambda r: int(r.get("cli_frame", 0)),
        )
        if not active_samples:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_empty_active_cam_trace")

        dts = []
        for i in range(len(active_samples) - 1):
            df = int(active_samples[i + 1]["cli_frame"]) - int(active_samples[i]["cli_frame"])
            if df != 1:
                return _chk("TOM-05", "fail", reason=f"s1_r{idx}_missing_rendered_frame_in_trace")
            dt = float(active_samples[i + 1]["take_dtsum_ms"]) - float(active_samples[i]["take_dtsum_ms"])
            dts.append(dt)

        max_t = float(active_samples[-1]["take_dtsum_ms"])
        min_t = float(active_samples[0]["take_dtsum_ms"])
        if max_t < 2800.0:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_trace_truncated_before_2800ms")

        if len(active_samples) < 30 or not dts or max(dts) > 100.0:
            return _chk("TOM-05", "missing", reason="insufficient_frame_rate")
        med_dt = statistics.median(dts)
        if min_t > 2.0 * med_dt or dts[0] > 2.0 * med_dt or dts[-1] > 2.0 * med_dt:
            return _chk("TOM-05", "missing", reason="insufficient_frame_rate")

        for s in active_samples:
            t_s = float(s["take_dtsum_ms"])
            all_sampled_t.add(t_s)
            ana_pos, _, _, _ = eval_catmull_rom_path(keyframes, t_s)
            obs_pos = [float(s["cam_x_m"]), float(s["cam_y_m"]), float(s["cam_z_m"])]
            if _dist3(obs_pos, ana_pos) >= 0.5:
                return _chk(
                    "TOM-05",
                    "fail",
                    observed={"rep": idx, "t_ms": round(t_s, 2), "err_m": round(_dist3(obs_pos, ana_pos), 3)},
                    reason=f"s1_r{idx}_cam_deviation_vs_analytic_ge_0_5m",
                )

        traces_by_rep.append(active_samples)

    t_common_max = min(float(tr[-1]["take_dtsum_ms"]) for tr in traces_by_rep)
    grid_100 = [float(k * 100) for k in range(int(t_common_max // 100.0) + 1)]
    eval_instants = sorted(t for t in all_sampled_t.union(grid_100) if 0.0 <= t <= t_common_max)

    for t_ms in eval_instants:
        pos_r = [_interp_pos_at_t(tr, t_ms) for tr in traces_by_rep]
        ana_pos, _, _, _ = eval_catmull_rom_path(keyframes, t_ms)
        for r_idx in range(3):
            if _dist3(pos_r[r_idx], ana_pos) >= 0.5:
                return _chk("TOM-05", "fail", reason="b6_grid_deviation_vs_analytic_ge_0_5m")
        for i in range(3):
            for j in range(i + 1, 3):
                if _dist3(pos_r[i], pos_r[j]) >= 0.5:
                    return _chk("TOM-05", "fail", reason="b6_inter_take_deviation_ge_0_5m")

    return _chk("TOM-05", "pass")


def _verify_no_ops_emitted_with_expired_lease(cut_win, srv_rows, cli_rows, arm_rows):
    """T13: comprueba que ningún peer emite RPC ni órdenes ni mueve cámara con su lease vencido."""
    peer = cut_win.get("peer", "")
    last_ok_tick = float(cut_win.get("last_ok_poll_tick_ms", 0.0))
    reconn_tick = float(cut_win.get("reconnect_poll_tick_ms", math.inf))
    lease_ms = float(cut_win.get("lease_ms", 2000.0))
    expire_tick = last_ok_tick + lease_ms

    if peer == "server":
        for r in arm_rows:
            rk = r.get("row_kind")
            rtick = float(r.get("srv_tick_ms", 0.0))
            if rk in ("go_sent", "dispatch") and expire_tick < rtick < reconn_tick:
                return False, "server_emitted_go_or_dispatch_with_expired_lease"
        for r in cli_rows:
            rk = r.get("row_kind")
            rtick = float(r.get("cli_tick_ms", 0.0))
            if rk in ("take_state_recv", "ack_recv") and expire_tick < rtick < reconn_tick:
                return False, "server_emitted_rpc_with_expired_lease"
    elif peer == "client":
        for r in cli_rows:
            rk = r.get("row_kind")
            rtick = float(r.get("cli_tick_ms", 0.0))
            if rk == "rpc_stop_sent" and expire_tick < rtick < reconn_tick:
                return False, "client_emitted_stop_rpc_with_expired_lease"
            if rk == "frame_sample" and (expire_tick + 50.0) < rtick < reconn_tick:
                if int(r.get("sandbox_cam_active_b", 0)) == 1:
                    return False, "client_kept_sandbox_cam_active_with_expired_lease"
    return True, None


def _eval_tom_06(bundle, ops):
    """TOM-06 — negativas de preparación, conexión (`take-conn-drop` 2 ramas) y stops (§5 TOM-06, R4-N17, R5-N5, T13)."""
    broken_prep_ops = [
        op for op in ops
        if op["verb"] == "take_arm"
        and (
            op["args_s"].get("expect_err") in ("cam_not_ready", "actor_incapable", "no_director")
            or any(tag in op["args_s"].get("take_id", "") for tag in ("cam_not_ready", "actor_incapable", "no_director"))
        )
    ]
    if broken_prep_ops and any(op["status"] == "ok" for op in broken_prep_ops):
        return _chk("TOM-06", "fail", reason="take_arm_accepted_broken_prep")

    arm_errors = {
        op["reason"] or op["read_s"].get("err", "")
        for op in ops
        if op["verb"] == "take_arm" and op["status"] in ("error", "rejected")
    }
    for req_err in ("cam_not_ready", "actor_incapable", "no_director"):
        if req_err not in arm_errors:
            return _chk("TOM-06", "missing", reason=f"missing_sync_arm_error_{req_err}")

    s3a_takes = {
        bundle["take_metas"][tid].get("case_id", tid): tid
        for tid in bundle["take_order"]
        if bundle["take_metas"].get(tid, {}).get("stage") == "S3a"
    }
    required_cases = (
        "conn_drop_no_effects",
        "conn_drop_after_effects",
        "stop_before_go",
        "double_stop_at_go",
        "stop_at_600ms",
    )
    for c_id in required_cases:
        if c_id not in s3a_takes:
            return _chk("TOM-06", "missing", reason=f"s3a_missing_case_{c_id}")

    tid_no_eff = s3a_takes["conn_drop_no_effects"]
    ts_no_eff = _get_take_slice(tid_no_eff, bundle, ops)
    if any(r.get("row_kind") in ("go_sent", "dispatch") for r in ts_no_eff["arm_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_no_effects_emitted_go_or_dispatch")
    if any(r.get("row_kind") == "frame_sample" and int(r.get("sandbox_cam_active_b", 0)) == 1 for r in ts_no_eff["cli_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_no_effects_activated_camera")
    term_no_eff = [r for r in ts_no_eff["srv_rows"] if r.get("row_kind") == "take_terminal"]
    if not term_no_eff or "terminada" in term_no_eff[0].get("state_or_origin", ""):
        return _chk("TOM-06", "fail", reason="conn_drop_no_effects_invalid_terminal")

    cuts_no_eff = [
        c for c in bundle["cut_windows"]
        if c.get("take_id") == tid_no_eff or c.get("case_id") == "conn_drop_no_effects"
    ]
    for cw in cuts_no_eff:
        ok_lease, l_reason = _verify_no_ops_emitted_with_expired_lease(
            cw, ts_no_eff["srv_rows"], ts_no_eff["cli_rows"], ts_no_eff["arm_rows"]
        )
        if not ok_lease:
            return _chk("TOM-06", "fail", reason=l_reason)

    tid_after = s3a_takes["conn_drop_after_effects"]
    ts_after = _get_take_slice(tid_after, bundle, ops)
    arm_job_after = ts_after["arm_job"]
    if not arm_job_after:
        return _chk("TOM-06", "missing", reason="conn_drop_after_effects_missing_arm_job")
    if not any(r.get("row_kind") == "go_sent" for r in ts_after["arm_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_missing_go_sent")
    if not any(r.get("row_kind") == "dispatch" for r in ts_after["arm_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_missing_dispatch")
    if not any(r.get("row_kind") == "frame_sample" and int(r.get("sandbox_cam_active_b", 0)) == 1 for r in ts_after["cli_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_no_active_cam_frames")

    if any(r.get("row_kind") in ("take_terminal", "cleanup_done") for r in ts_after["arm_rows"]):
        return _chk("TOM-06", "fail", reason="terminal_row_illegally_appended_to_stopped_take_arm")

    term_after = [r for r in ts_after["srv_rows"] if r.get("row_kind") == "take_terminal" and r.get("subject_id") == tid_after]
    cleanup_after = [r for r in ts_after["srv_rows"] if r.get("row_kind") == "cleanup_done" and r.get("subject_id") == tid_after]
    cli_exit_after = [r for r in ts_after["cli_rows"] if r.get("row_kind") == "cli_safety_exit"]
    if not term_after or not cleanup_after or not cli_exit_after:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_missing_r5_n5_terminal_evidence")

    tr = term_after[0]
    if tr.get("state_or_origin") != "parada:hombre_muerto":
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_wrong_terminal_state_or_origin")
    if int(tr.get("v6", 0)) != 1 or int(tr.get("v7", 0)) != 1:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_transitions_or_restorations_not_1")
    if int(tr.get("v9", 1)) != 0 or int(tr.get("v10", 1)) != 0 or int(tr.get("v11", 1)) != 0:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_cues_or_pending_not_cancelled")
    expected_pre_dmg = int(ts_after["meta"].get("allow_dmg_pre_b", 1))
    if int(tr.get("v8", -1)) != expected_pre_dmg:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_allow_dmg_not_restored")

    cuts_after = [
        c for c in bundle["cut_windows"]
        if c.get("take_id") == tid_after or c.get("case_id") == "conn_drop_after_effects"
    ]
    if not cuts_after:
        return _chk("TOM-06", "missing", reason="conn_drop_after_effects_missing_cut_window")
    for cw in cuts_after:
        ok_lease, l_reason = _verify_no_ops_emitted_with_expired_lease(
            cw, ts_after["srv_rows"], ts_after["cli_rows"], ts_after["arm_rows"]
        )
        if not ok_lease:
            return _chk("TOM-06", "fail", reason=l_reason)
        if cw.get("peer") == "server":
            lease_ms = float(cw.get("lease_ms", 2000.0))
            reconn_tick = float(cw.get("reconnect_poll_tick_ms", 0.0))
            if float(tr.get("v4", 0.0)) <= lease_ms:
                return _chk("TOM-06", "fail", reason="conn_drop_srv_lease_age_not_gt_lease_ms")
            if arm_job_after["onjobend_tick_ms"] <= 0.0 or arm_job_after["onjobend_tick_ms"] >= reconn_tick:
                return _chk("TOM-06", "fail", reason="conn_drop_onjobend_not_before_reconnection")
            if arm_job_after["released_tick_ms"] <= 0.0 or arm_job_after["released_tick_ms"] >= reconn_tick:
                return _chk("TOM-06", "fail", reason="conn_drop_released_not_before_reconnection")

    for stop_case in ("stop_before_go", "double_stop_at_go", "stop_at_600ms"):
        ts_st = _get_take_slice(s3a_takes[stop_case], bundle, ops)
        term_st = [r for r in ts_st["srv_rows"] if r.get("row_kind") == "take_terminal"]
        if not term_st:
            return _chk("TOM-06", "fail", reason=f"{stop_case}_missing_take_terminal")
        t_row = term_st[0]
        if not t_row.get("state_or_origin", "").startswith("parada:") or "terminad" in t_row.get("state_or_origin", ""):
            return _chk("TOM-06", "fail", reason=f"{stop_case}_invalid_terminal_state")
        if int(t_row.get("v6", 0)) != 1 or int(t_row.get("v7", 0)) != 1:
            return _chk("TOM-06", "fail", reason=f"{stop_case}_multiple_transitions_or_restorations")

    return _chk("TOM-06", "pass")


def _verify_look_response_after_local_exit(cli_rows, stimuli, contemp_yaw_ref, eps_look_deg, calib_sign, after_h_ms):
    """T4: comprueba que tras una salida local de cámara hay respuesta de mirada atribuible al pulso."""
    pulses = [
        s for s in stimuli
        if s.get("stim_type") == "look_pulse" and float(s.get("h_ms", 0.0)) >= after_h_ms
    ]
    if not pulses:
        return False
    frame_samples = [
        r for r in cli_rows
        if r.get("row_kind") == "frame_sample" and int(r.get("sandbox_cam_active_b", 1)) == 0
    ]
    for r in frame_samples:
        dyaw = (float(r.get("cam_yaw_deg", 0.0)) - float(contemp_yaw_ref)) * calib_sign
        if dyaw >= eps_look_deg:
            return True
    return False


def _eval_tom_07(bundle, ops):
    """TOM-07 — negativas de tecla (S3b), reintentos/carreras/hombre muerto (S3c) y reinicio de proceso (S3d)."""
    run_meta = bundle["run_meta"]
    eps_look_deg = float(run_meta.get("eps_look_deg", 0.5))
    calib_sign = 1.0 if float(run_meta.get("calib_sign", 1.0)) >= 0.0 else -1.0

    s3b_takes = {
        bundle["take_metas"][tid].get("case_id", tid): tid
        for tid in bundle["take_order"]
        if bundle["take_metas"].get(tid, {}).get("stage") == "S3b"
    }
    if "guard" not in s3b_takes or "prior_terminal_same_epoch" not in s3b_takes:
        return _chk("TOM-07", "missing", reason="s3b_missing_guard_or_prior_terminal_take")

    prior_tid = s3b_takes["prior_terminal_same_epoch"]
    guard_tid = s3b_takes["guard"]
    if not guard_tid.endswith("guard"):
        return _chk("TOM-07", "fail", reason="s3b_guard_short_label_invalid")

    ts_guard = _get_take_slice(guard_tid, bundle, ops)
    for r in ts_guard["cli_rows"]:
        if r.get("row_kind") == "key_edge" and r.get("detail") in ("press_accepted", "stopped_without_take"):
            if float(r.get("take_dtsum_ms", 0.0)) <= 0.0:
                return _chk("TOM-07", "fail", reason="s3b_key_accepted_without_active_take")

    ignored_details = {
        r.get("detail")
        for r in bundle["cli_watch_rows"]
        if r.get("row_kind") == "key_edge"
    }
    for req_ign in ("ignored_no_take", "ignored_menu", "ignored_chat"):
        if req_ign not in ignored_details:
            return _chk("TOM-07", "missing", reason=f"s3b_missing_{req_ign}")

    cam_prep_ops = [op for op in ops if op["verb"] == "take_cam_prep" and op["status"] == "ok"]
    blocker_ops = [op for op in cam_prep_ops if op["args_s"].get("op") == "set_ui_blocker"]
    if not any(op["args_s"].get("ui_blocker") == "menu" and int(op["read_n"].get("menu_open_b", 0)) == 1 for op in blocker_ops):
        return _chk("TOM-07", "fail", reason="s3b_menu_blocker_not_observed_open")
    if not any(op["args_s"].get("ui_blocker") == "chat" and int(op["read_n"].get("chat_open_b", 0)) == 1 for op in blocker_ops):
        return _chk("TOM-07", "fail", reason="s3b_chat_blocker_not_observed_open")
    none_blockers = [op for op in blocker_ops if op["args_s"].get("ui_blocker") == "none"]
    if not none_blockers or any(
        int(op["read_n"].get("menu_open_b", 1)) != 0 or int(op["read_n"].get("chat_open_b", 1)) != 0
        for op in none_blockers
    ):
        return _chk("TOM-07", "fail", reason="s3b_menu_or_chat_not_closed_with_close_menu")

    ts_prior = _get_take_slice(prior_tid, bundle, ops)
    if not ts_prior["arm_job"] or not any(r.get("row_kind") == "take_terminal" for r in ts_prior["srv_rows"]):
        return _chk("TOM-07", "fail", reason="t3_prior_take_not_really_armed_and_terminated")

    guard_yaw_ref = float(ts_guard["meta"].get("contemp_yaw_ref_deg", 0.0))
    rej_by_case = {r.get("case_id"): r for r in bundle["key_rejections"]}
    for req_rej in ("old_take_same_epoch", "other_epoch", "other_director_c1", "other_director_c2"):
        if req_rej not in rej_by_case:
            return _chk("TOM-07", "missing", reason=f"s3b_missing_rejection_{req_rej}")

    c1 = rej_by_case["other_director_c1"]
    c2 = rej_by_case["other_director_c2"]
    if (
        c1.get("reg_engine_uid") != "qa-uid-dir-other"
        or c1.get("sender_engine_uid") == "qa-uid-dir-other"
        or not c1.get("sender_engine_uid")
        or c1.get("payload_sender_id") != "dir_main"
    ):
        return _chk("TOM-07", "fail", reason="s3b_c1_engine_uid_or_payload_invalid")
    if (
        c2.get("reg_engine_uid") != "qa-uid-dir-other"
        or c2.get("sender_engine_uid") == "qa-uid-dir-other"
        or not c2.get("sender_engine_uid")
        or c2.get("payload_sender_id") != "dir_other"
    ):
        return _chk("TOM-07", "fail", reason="s3b_c2_engine_uid_spoof_invalid")

    repeat_acks = [
        r for r in ts_guard["cli_rows"]
        if r.get("row_kind") == "ack_recv"
        and r.get("ack_req_take_id") == prior_tid
        and r.get("ack_resp_class") == "repeat_terminal"
        and r.get("ack_cur_take_id") == guard_tid
        and r.get("ack_cur_state") == "rodando"
    ]
    if not repeat_acks:
        return _chk("TOM-07", "fail", reason="t3_missing_repeat_terminal_ack_for_prior_take")

    state_recvs = [
        r for r in ts_guard["cli_rows"]
        if r.get("row_kind") == "take_state_recv"
        and r.get("ack_cur_take_id") == guard_tid
        and r.get("ack_cur_state") == "rodando"
    ]
    if len(state_recvs) < 4:
        return _chk("TOM-07", "fail", reason="t5_missing_take_state_recv_for_all_4_rejections")

    for req_rej, rinfo in rej_by_case.items():
        rej_cli_tick = float(rinfo.get("cli_tick_ms", 0.0))
        rej_h_ms = float(rinfo.get("h_ms", 0.0))
        matching_sr = [
            sr for sr in state_recvs
            if 0.0 <= (float(sr.get("cli_tick_ms", 0.0)) - rej_cli_tick) <= 1000.0
            and int(sr.get("aux_n", 0)) > 0
        ]
        if not matching_sr:
            return _chk("TOM-07", "fail", reason=f"t5_no_reconcile_within_1000ms_{req_rej}")
        if not _verify_look_response_after_local_exit(
            ts_guard["cli_rows"], ts_guard["stimuli"], guard_yaw_ref, eps_look_deg, calib_sign, rej_h_ms
        ):
            return _chk("TOM-07", "fail", reason=f"t4_missing_look_response_after_{req_rej}")

    s3c_takes = {
        bundle["take_metas"][tid].get("case_id", tid): tid
        for tid in bundle["take_order"]
        if bundle["take_metas"].get(tid, {}).get("stage") in ("S3c", "S3d")
    }
    required_s3c = (
        "drop_first_req",
        "drop_first_ack",
        "simul_key_and_web",
        "held_go_after_key",
        "stale_notify_take_a",
        "stale_notify_take_b",
        "ack2",
        "new",
        "epoch_dup_1",
        "epoch_dup_2",
        "cut_nokey",
        "cut_before",
        "cut_after",
        "procdup_1",
        "procdup_2",
    )
    for cname in required_s3c:
        if cname not in s3c_takes:
            return _chk("TOM-07", "missing", reason=f"s3c_missing_case_{cname}")

    ts_hgo = _get_take_slice(s3c_takes["held_go_after_key"], bundle, ops)
    key_edges_hgo = [r for r in ts_hgo["cli_rows"] if r.get("row_kind") == "key_edge"]
    if not key_edges_hgo:
        return _chk("TOM-07", "missing", reason="held_go_missing_key_edge")
    key_frame_hgo = int(key_edges_hgo[0]["cli_frame"])
    post_key_cam_on = [
        r for r in ts_hgo["cli_rows"]
        if r.get("row_kind") == "frame_sample"
        and int(r.get("cli_frame", 0)) > key_frame_hgo
        and int(r.get("sandbox_cam_active_b", 0)) == 1
    ]
    release_go_ops = [op for op in cam_prep_ops if op["args_s"].get("op") == "release_held_go"]
    if post_key_cam_on or not release_go_ops or int(release_go_ops[-1]["read_n"].get("late_go_ignored_n", 0)) < 1:
        return _chk("TOM-07", "fail", reason="late_go_reactivated_camera_after_key_press")

    ts_dreq = _get_take_slice(s3c_takes["drop_first_req"], bundle, ops)
    retries_dreq = [
        r for r in ts_dreq["cli_rows"]
        if r.get("row_kind") == "rpc_stop_sent" and int(r.get("aux_n", 0)) == 1
    ]
    term_dreq = [r for r in ts_dreq["srv_rows"] if r.get("row_kind") == "take_terminal"]
    if not retries_dreq or not term_dreq or term_dreq[0].get("state_or_origin") != "parada:juego":
        return _chk("TOM-07", "fail", reason="drop_first_req_not_stopped_by_retry")
    if float(ts_dreq["meta"].get("retry_srv_stop_hi_ms", 0.0)) >= 1000.0 or float(ts_dreq["meta"].get("retry_cli_recov_hi_ms", 0.0)) >= 1000.0:
        return _chk("TOM-07", "fail", reason="drop_first_req_retry_latency_ge_1000ms")

    ts_dack = _get_take_slice(s3c_takes["drop_first_ack"], bundle, ops)
    term_dack = [r for r in ts_dack["srv_rows"] if r.get("row_kind") == "take_terminal"]
    acks_dack = [r for r in ts_dack["cli_rows"] if r.get("row_kind") == "ack_recv"]
    retries_dack = [r for r in ts_dack["cli_rows"] if r.get("row_kind") == "rpc_stop_sent" and int(r.get("aux_n", 0)) >= 1]
    if (
        not term_dack
        or int(term_dack[0].get("v6", 0)) != 1
        or int(term_dack[0].get("v7", 0)) != 1
        or not retries_dack
        or not acks_dack
        or acks_dack[-1].get("ack_resp_class") != "repeat_terminal"
    ):
        return _chk("TOM-07", "fail", reason="drop_first_ack_failed_idempotent_retry_ack")

    ts_sim = _get_take_slice(s3c_takes["simul_key_and_web"], bundle, ops)
    term_sim = [r for r in ts_sim["srv_rows"] if r.get("row_kind") == "take_terminal"]
    if not term_sim or int(term_sim[0].get("v6", 0)) != 1 or int(term_sim[0].get("v7", 0)) != 1:
        return _chk("TOM-07", "fail", reason="simultaneous_key_and_web_produced_multiple_stops")

    ts_stb = _get_take_slice(s3c_takes["stale_notify_take_b"], bundle, ops)
    stale_ops = [op for op in cam_prep_ops if op["args_s"].get("op") == "deliver_stale_msg"]
    if not stale_ops or int(stale_ops[-1]["read_n"].get("stale_msg_ignored_n", 0)) < 1:
        return _chk("TOM-07", "fail", reason="stale_notify_not_delivered_or_not_ignored")
    if int(stale_ops[-1]["read_n"].get("sandbox_cam_active_b", 0)) != 1:
        return _chk("TOM-07", "fail", reason="stale_notify_released_active_camera_of_take_b")
    if any(r.get("row_kind") == "cli_safety_exit" and r.get("detail") == "stale_notify" for r in ts_stb["cli_rows"]):
        return _chk("TOM-07", "fail", reason="stale_notify_triggered_safety_exit_on_take_b")

    ack2_tid = s3c_takes["ack2"]
    new_tid = s3c_takes["new"]
    if not ack2_tid.endswith("ack2") or not new_tid.endswith("new"):
        return _chk("TOM-07", "fail", reason="ack2_or_new_short_label_invalid")
    ts_new = _get_take_slice(new_tid, bundle, ops)
    ack2_in_new = [
        r for r in ts_new["cli_rows"]
        if r.get("row_kind") == "ack_recv" and r.get("ack_req_take_id") == ack2_tid
    ]
    if not ack2_in_new:
        return _chk("TOM-07", "fail", reason="missing_late_ack_of_ack2_while_new_running")
    ack2_row = ack2_in_new[0]
    if ack2_row.get("ack_req_state") != "parada" or ack2_row.get("ack_req_origin") != "juego":
        return _chk("TOM-07", "fail", reason="ack2_late_ack_req_fields_invalid")
    status_after_ack2 = [
        op for op in cam_prep_ops
        if op["args_s"].get("op") == "status" and op["args_s"].get("take_id") == new_tid
    ]
    if not status_after_ack2 or status_after_ack2[-1]["read_s"].get("cli_cached_take_id") != new_tid or status_after_ack2[-1]["read_s"].get("cli_cached_state") != "rodando":
        return _chk("TOM-07", "fail", reason="t6_old_ack_overwrote_newer_client_cache")

    ts_nokey = _get_take_slice(s3c_takes["cut_nokey"], bundle, ops)
    term_nokey = [r for r in ts_nokey["srv_rows"] if r.get("row_kind") == "take_terminal"]
    if not term_nokey or term_nokey[0].get("state_or_origin") != "parada:hombre_muerto":
        return _chk("TOM-07", "fail", reason="cut_nokey_did_not_transition_to_hombre_muerto")
    if float(term_nokey[0].get("v4", 0.0)) <= float(ts_nokey["meta"].get("lease_ms", 2000.0)):
        return _chk("TOM-07", "fail", reason="cut_nokey_lease_age_not_gt_lease_ms")

    ts_cbef = _get_take_slice(s3c_takes["cut_before"], bundle, ops)
    term_cbef = [r for r in ts_cbef["srv_rows"] if r.get("row_kind") == "take_terminal"]
    if (
        not term_cbef
        or term_cbef[0].get("state_or_origin") != "parada:juego"
        or int(term_cbef[0].get("v6", 0)) != 1
        or int(term_cbef[0].get("v7", 0)) != 1
    ):
        return _chk("TOM-07", "fail", reason="t8_cut_before_did_not_stop_with_juego_and_single_transition")

    tid_caft = s3c_takes["cut_after"]
    ts_caft = _get_take_slice(tid_caft, bundle, ops)
    term_caft = [r for r in ts_caft["srv_rows"] if r.get("row_kind") == "take_terminal"]
    if (
        not term_caft
        or term_caft[0].get("state_or_origin") != "parada:hombre_muerto"
        or int(term_caft[0].get("v6", 0)) != 1
        or int(term_caft[0].get("v7", 0)) != 1
        or int(term_caft[0].get("v9", 1)) != 0
        or int(term_caft[0].get("v10", 1)) != 0
        or int(term_caft[0].get("v11", 1)) != 0
    ):
        return _chk("TOM-07", "fail", reason="t8_cut_after_invalid_terminal_or_new_effects")

    cuts_caft = [
        c for c in bundle["cut_windows"]
        if c.get("take_id") == tid_caft or c.get("case_id") == "cut_after"
    ]
    if not cuts_caft:
        return _chk("TOM-07", "missing", reason="t8_cut_after_missing_cut_window")
    for cw in cuts_caft:
        ok_l, l_reason = _verify_no_ops_emitted_with_expired_lease(
            cw, ts_caft["srv_rows"], ts_caft["cli_rows"], ts_caft["arm_rows"]
        )
        if not ok_l:
            return _chk("TOM-07", "fail", reason=l_reason)

    ts_p2 = _get_take_slice(s3c_takes["procdup_2"], bundle, ops)
    if ts_p2["meta"].get("restart_exceeded_lease_b") == 1:
        return _chk("TOM-07", "missing", reason="s3d_server_restart_exceeded_client_lease")
    if int(ts_p2["meta"].get("contaminated_by_old_retry_b", 0)) != 0:
        return _chk("TOM-07", "fail", reason="s3d_new_epoch_take_contaminated_by_old_retry")

    return _chk("TOM-07", "pass")


def evaluate(part_dir, *, repo_root=None):
    """Evalúa una carpeta de parte de S-toma usando únicamente `samples/` y `manifest.json`."""
    pdir = Path(part_dir)
    root = f03_common._resolve_repo_root(repo_root)

    raw_manifest = _load_json_safe(pdir / "manifest.json")
    if not isinstance(raw_manifest, dict):
        return _make_inconcluso(["params_unverified"])

    manifest = {
        "both": bool(raw_manifest.get("both", True)),
        "build": raw_manifest.get("build"),
        "id": raw_manifest.get("id", SPIKE_ID),
        "identity": raw_manifest.get("identity"),
        "kind": raw_manifest.get("kind", "spike"),
        "params": raw_manifest.get("params") if isinstance(raw_manifest.get("params"), dict) else {},
        "schema": raw_manifest.get("schema"),
    }

    bridge_path = pdir / "samples" / "bridge.jsonl"
    scenario_path = pdir / "samples" / "scenario.jsonl"
    fixture_path = _find_fixture_path(root)
    if not bridge_path.is_file() or not scenario_path.is_file() or fixture_path is None:
        return _make_inconcluso(["artifact_unverified"])

    try:
        bridge_records = f03_common.read_jsonl(bridge_path)
        scenario_records = f03_common.read_jsonl(scenario_path)
    except Exception:
        return _make_inconcluso(["artifact_unverified"])

    fixture = _load_json_safe(fixture_path)
    if not isinstance(fixture, dict):
        return _make_inconcluso(["params_unverified"])

    ops, jobs, hellos, _ = _reconstruct_ops_and_jobs(bridge_records)
    ok_s_toma, st_reasons = _verify_s_toma_integrity(
        pdir, manifest, bridge_records, scenario_records, ops, jobs, hellos, repo_root=root
    )
    if not ok_s_toma:
        return _make_inconcluso(st_reasons)

    bundle = _collect_take_bundles(ops, jobs, scenario_records)

    checks = [
        _eval_tom_01(bundle, ops, fixture),
        _eval_tom_02(bundle, ops, fixture),
        _eval_tom_03(bundle, ops, hellos, fixture),
        _eval_tom_04(bundle, ops),
        _eval_tom_05(bundle, ops, fixture),
        _eval_tom_06(bundle, ops),
        _eval_tom_07(bundle, ops),
    ]

    statuses = [c["status"] for c in checks]
    reasons = [c["reason"] for c in checks if c["status"] != "pass" and c.get("reason")]

    if "fail" in statuses:
        exit_code = 1
    elif "missing" in statuses:
        exit_code = 2
    else:
        exit_code = 0

    wire_cap = int(manifest["identity"]["params"]["wire_cap"])
    return gate_core.make_verdict(
        SPIKE_ID,
        exit_code,
        checks=checks,
        metrics={"wire_cap": wire_cap},
        reasons=list(dict.fromkeys(reasons)),
    )
