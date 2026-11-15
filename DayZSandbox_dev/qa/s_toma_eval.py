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

- `act_observe` (`server`, de S3 `DSBX_QA_X_Actor`; contrato de S3:113, BLOQ 14): `args.nk` con `center_x_m`,
  `center_z_m` y `radius_m` (S-toma no inventa ningun `op`).
  - `read.sk`: `core_ver` (25 chars), `adapter_ver` (29 chars), `backend_class`.
  - `read.nk`: `backend_available_b` (1).
  - Tabla de filas de observación de actores y vestuario: `actor_id`, `real_class`,
    `slot_name`, `item_class`, `x_m`, `y_m`, `z_m` (y opcionalmente `net_id_low`,
    `net_id_high`, `alive_b`).

- Contratos de lectura cruda que este evaluador EXIGE y que el brief no tabula (BLOQ 3, 5, 9; el runner y la extension
  los producen, el evaluador los recalcula, nunca confia en una etiqueta):
  - `take_key_op(op="audit_candidates")` y `bind_key`/`restore_bindings` devuelven la tabla `scol = ["action_name",
    "key_name"]`, `ncol = ["alt_idx"]`: una fila por vinculacion observada de acciones de la build sobre las teclas
    candidatas y de la propia accion; el evaluador recalcula los conflictos y las candidatas libres en Python.
  - `take_srv_observe_start` emite ademas `key_rpc` (una por `TAKE_STOP_KEY` recibido; `subject_id` = `take_id` del par,
    `state_or_origin` = decision `accepted` | `rejected` | `repeat_terminal`, `v1` = epoch pedido, `v2` = `retry_seq`,
    `v3` = epoch actual) y `rpc_emit` (una por RPC servidor -> cliente que intenta emitir; `subject_id` = RPC,
    `state_or_origin` = `sent` | `blocked_lease`, `v1` = `lease_age_ms` crudo, `v2` = emitido 0/1).
  - La identidad de toma es `(gen, take_id)`: `gen` es la generacion del servidor observada en el puente (un
    `take_scene_prep(op="restart_epoch")` o un `hello` de servidor con otra instancia); el mismo `take_id` completo en una
    generacion nueva es otra toma.
  - Las calibraciones salen de ordenes reales `take_clock_ping` del puente: el intervalo es [deliver, result] en `t_ms` del
    arnes; cada `clock_pair` del escenario solo aporta su pertenencia (etapa, repeticion, fase) y se enlaza con la
    respuesta cruda por `(peer, peer_tick_ms, peer_frame)`.
  - Los cortes salen de `cut_start`/`cut_end` y de los polls/keepalives 200 del puente (`tick_s` del propio peer); el lease
    es `identity.params.lease_ms`.

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

import bisect
import hashlib
import importlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import xml.etree.ElementTree as ET

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
    """Reconstruye las operaciones entregadas, sus primeros resultados y las paginas de cada job (BLOQ 2, 13)."""
    order_meta_by_op = {}
    enq_t = {}
    deliver_t = {}
    polls_by_op = {}
    first_results = {}
    op_order = []
    hellos = []
    poll_events = []
    hello_boundaries = []
    last_srv_inst = None

    for idx, rec in enumerate(bridge_records):
        ev = rec.get("ev") or rec.get("event")
        if ev == "hello":
            if rec.get("http", 200) == 200 and rec.get("ok") is not False:
                hellos.append(rec)
                if rec.get("peer") == "server":
                    inst = rec.get("inst")
                    if last_srv_inst is not None and inst != last_srv_inst:
                        hello_boundaries.append(idx)
                    last_srv_inst = inst
        elif ev in ("enq", "deliver"):
            oid = rec.get("op_id")
            if isinstance(oid, str):
                order_meta_by_op[oid] = (idx, rec)
                if ev == "enq":
                    enq_t.setdefault(oid, rec.get("t_ms"))
                else:
                    deliver_t.setdefault(oid, rec.get("t_ms"))
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

        ops.append(
            {
                "op_id": op_id,
                "verb": verb,
                "peer": peer,
                "inst": inst,
                "poll_idx": p_idx,
                "res_idx": r_idx,
                "poll_rec": p_rec,
                "res_rec": r_rec,
                "t_enq": enq_t.get(op_id),
                "t_deliver": deliver_t.get(op_id),
                "t_result": r_rec.get("t_ms"),
                "status": norm_status,
                "raw_status": raw_status,
                "reason": str(res.get("reason") or ""),
                "dup": bool(res.get("dup", False)),
                "dup_raw": res.get("dup"),
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
        )

    boundaries = list(hello_boundaries)
    for op in ops:
        if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "restart_epoch" and op["status"] == "ok":
            boundaries.append(op["res_idx"])
    boundaries.sort()
    for op in ops:
        op["gen"] = 1 + bisect.bisect_right(boundaries, op["res_idx"])

    jobs = {}
    for op in ops:
        verb = op["verb"]
        if verb in ("take_arm", "take_cli_watch_start", "take_srv_observe_start") and op["status"] == "ok":
            job_id = op["read_s"].get("job") or op["op_id"]
            jobs[(op["inst"], job_id)] = {
                "job_id": job_id,
                "inst": op["inst"],
                "start_op": op,
                "verb": verb,
                "peer": op["peer"],
                "gen": op["gen"],
                "take_id": op["args_s"].get("take_id", ""),
                "mode": op["args_s"].get("mode", "rpc"),
                "stop_inject": op["args_s"].get("stop_inject", "none"),
                "args_s": op["args_s"],
                "args_n": op["args_n"],
                "state": op["read_s"].get("state", "running"),
                "reason": op["reason"] or str(op["read_s"].get("reason") or ""),
                "end_tick_ms": float(op["read_n"].get("end_tick_ms", 0.0) or 0.0),
                "onjobend_tick_ms": float(op["read_n"].get("onjobend_tick_ms", 0.0) or 0.0),
                "released_tick_ms": float(op["read_n"].get("released_tick_ms", 0.0) or 0.0),
                "pages": [],
                "rows": list(op["read_rows"]),
            }
        elif verb == "job_read" and op["status"] == "ok":
            job_id = op["args_s"].get("job") or op["read_s"].get("job") or ""
            j = jobs.get((op["inst"], job_id))
            if j is not None:
                j["pages"].append(op)
                j["rows"].extend(op["read_rows"])
                if op["read_s"].get("state"):
                    j["state"] = op["read_s"]["state"]
                if op["read_s"].get("reason"):
                    j["reason"] = op["read_s"]["reason"]
                for tk in ("end_tick_ms", "onjobend_tick_ms", "released_tick_ms"):
                    if tk in op["read_n"] and float(op["read_n"][tk]) > 0.0:
                        j[tk] = float(op["read_n"][tk])

    return ops, jobs, hellos, poll_events


def _verify_s_toma_integrity(part_dir, manifest, bridge_records, scenario_records, ops, jobs, hellos, repo_root=None, sources=None):
    """Integridad de la parte y propia de S-toma (§5, A3, R4-N13, R4-N14, T2, T12, BLOQ 12-14).

    Devuelve `(ok, reasons, ctx)`; `ctx` lleva la fixture consumida (exactamente los bytes cuyo hash se verifico)."""
    root = f03_common._resolve_repo_root(repo_root)
    src = sources if sources is not None else _GitSources(root)

    if not isinstance(manifest, dict):
        return False, ["params_unverified"], None

    build = manifest.get("build")
    both = bool(manifest.get("both", True))
    req_peers = ("server", "client") if both else ("server",)

    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        return False, ["params_unverified"], None

    if build in ("retail", "diag") and identity.get("git_dirty") is not False:
        return False, ["git_dirty"], None

    peer_builds = identity.get("peer_builds")
    if not isinstance(peer_builds, dict) or any(peer_builds.get(r) != build for r in req_peers):
        return False, ["build_mismatch"], None

    for role in req_peers:
        if not any(h.get("peer") == role for h in hellos):
            return False, ["build_mismatch"], None

    for h in hellos:
        proto, h_build, _pv = f03_common._hello_proto_and_build(h)
        if proto != "qa0" or h_build != build:
            return False, ["build_mismatch"], None

    git_head = identity.get("git_head") or manifest.get("git_head") or ""
    try:
        expected_stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=root)
    except f03_common.StampSourceUnavailableError:
        return False, ["stamp_source_unavailable"], None

    expected_pv = f"dsbx-qa1+{expected_stamp}"
    if identity.get("probe_stamp") != expected_stamp:
        return False, ["artifact_unverified"], None

    for h in hellos:
        _proto, _h_build, pv = f03_common._hello_proto_and_build(h)
        if not isinstance(pv, str) or pv == "dsbx-qa1+unstamped" or pv != expected_pv:
            return False, ["artifact_unverified"], None

    ok_params, param_reason = f03_common.verify_eval_params_at_commit(manifest, repo_root=root)
    if not ok_params:
        return False, [param_reason], None

    params = identity.get("params")
    if not isinstance(params, dict):
        return False, ["params_unverified"], None

    wire_cap = params.get("wire_cap")
    if not isinstance(wire_cap, int) or isinstance(wire_cap, bool) or wire_cap <= 0:
        return False, ["params_unverified"], None

    lease_ms = params.get("lease_ms")
    if isinstance(lease_ms, bool) or not isinstance(lease_ms, (int, float)) or lease_ms <= 0:
        return False, ["params_unverified"], None

    # BLOQ 12: el sello esperado del adaptador se RECALCULA desde las fuentes del git_head; lo guardado en la
    # identidad solo se contrasta con ese recalculo, nunca se toma como verdad.
    try:
        exp_stamp = src.exp_stamp(git_head)
    except f03_common.StampSourceUnavailableError:
        return False, ["stamp_source_unavailable"], None
    expected_adapter = "dsbx-qa-exp1+" + str(exp_stamp)
    if len(expected_adapter) != 29 or params.get("adapter_ver_expected") != expected_adapter:
        return False, ["params_unverified"], None

    fixture_sha = params.get("fixture_sha256")
    if not isinstance(fixture_sha, str) or len(fixture_sha) != 64:
        return False, ["params_unverified"], None

    # BLOQ 12: se consumen EXACTAMENTE los bytes cuyo hash se verifica (blob del commit; si git no lo da, el fichero).
    fix_bytes = src.fixture_bytes(git_head)
    if fix_bytes is None:
        fixture_path = _find_fixture_path(root)
        if fixture_path is None:
            return False, ["params_unverified"], None
        fix_bytes = fixture_path.read_bytes()
    if hashlib.sha256(fix_bytes).hexdigest() != fixture_sha:
        return False, ["params_unverified"], None
    try:
        fixture = json.loads(fix_bytes.decode("utf-8"))
    except Exception:
        return False, ["params_unverified"], None
    if not isinstance(fixture, dict):
        return False, ["params_unverified"], None

    for ev in bridge_records:
        kind = ev.get("ev") or ev.get("event")
        if kind == "wire_cap_exceeded":
            return False, ["wire_cap_exceeded"], None
        if kind in ("poll", "result", "keepalive") and int(ev.get("body_len", 0) or 0) > wire_cap:
            return False, ["wire_cap_exceeded"], None
        if kind == "lost":
            return False, ["result_lost"], None
        if kind == "expire":
            return False, ["result_timeout"], None

    for srec in scenario_records:
        if srec.get("ev") == "operator_timeout":
            return False, ["operator_timeout"], None

    # BLOQ 13: la primera entrega de toda orden cuyo resultado se consume debe ser EXPLICITAMENTE no duplicada.
    for op in ops:
        if op.get("dup_raw") is not False:
            return False, ["dup_first_delivery"], None

    # T2 y BLOQ 13: la capacidad del observador, tambien con el estado real del nucleo (`failed/rows_cap`).
    cap_reasons = ("observer_capacity", "rows_cap")
    for j in jobs.values():
        if j.get("reason") in cap_reasons or any(p["reason"] in cap_reasons or p["read_s"].get("reason") in cap_reasons for p in j["pages"]):
            return False, ["observer_capacity"], None
        for r in j.get("rows", []):
            if r.get("row_kind") in cap_reasons or r.get("detail") in cap_reasons:
                return False, ["observer_capacity"], None
    for op in ops:
        if op.get("reason") in cap_reasons or op["read_s"].get("reason") in cap_reasons:
            return False, ["observer_capacity"], None

    # El observador de S3 (T12): `take_scene_prep(op="verify")` y `act_observe` con el contrato de S3 (BLOQ 14: sin `op`).
    verify_ops = [
        op for op in ops
        if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "verify" and op["status"] == "ok"
    ]
    act_obs_ops = [op for op in ops if op["verb"] == "act_observe" and op["status"] == "ok"]
    if not verify_ops or not act_obs_ops:
        return False, ["artifact_unverified"], None
    for vop in verify_ops:
        if int(vop["read_n"].get("observer_ok_b", 0)) != 1:
            return False, ["artifact_unverified"], None
        if vop["read_s"].get("adapter_ver") != expected_adapter:
            return False, ["artifact_unverified"], None
        if vop["read_s"].get("observer_stamp") != expected_pv:
            return False, ["artifact_unverified"], None
    for aop in act_obs_ops:
        if int(aop["read_n"].get("backend_available_b", 0)) != 1:
            return False, ["artifact_unverified"], None
        if aop["read_s"].get("adapter_ver") != expected_adapter:
            return False, ["artifact_unverified"], None
        if aop["read_s"].get("core_ver") != expected_pv:
            return False, ["artifact_unverified"], None

    return True, [], {
        "fixture": fixture,
        "lease_ms": float(lease_ms),
        "git_head": git_head,
        "sources": src,
        "expected_adapter": expected_adapter,
    }


def _calibrate_peer_clock(bundle, peer, stage, rep, extent=None, gen=None):
    """Calibracion por intervalos [theta_lo, theta_hi] enlazada con respuestas CRUDAS de `take_clock_ping` (BLOQ 4).

    Cada `clock_pair` del escenario tiene que corresponder a una orden real del puente (mismo tick y frame crudos del
    peer, misma instancia) cuyo intervalo [deliver, result] en `t_ms` del arnes contiene lo declarado; el intervalo se
    calcula del puente, no de lo declarado. Los pings deben rodear las filas de la toma (frames y ticks del peer)."""
    pairs = [
        p for p in bundle["clock_pairs"]
        if p.get("peer") == peer and p.get("stage") == stage and int(p.get("rep", 0)) == int(rep)
    ]
    if len(pairs) < 2:
        return None, "insufficient_clock_pings"

    linked = []
    seen_ops = set()
    for pr in pairs:
        try:
            key = (peer, float(pr["peer_tick_ms"]), int(pr["peer_frame"]))
            h_send = float(pr["h_send_ms"])
            h_recv = float(pr["h_recv_ms"])
        except Exception:
            return None, "invalid_clock_ping_fields"
        pg = bundle["pings"].get(key)
        if pg is None:
            return None, "clock_pair_without_raw_ping"
        if pr.get("inst") and pr.get("inst") != pg["inst"]:
            return None, "clock_pair_inst_differs_from_raw_ping"
        if h_recv < h_send:
            return None, "negative_clock_ping_rtt"
        if h_send > pg["t_lo"] + 1.0 or pg["t_hi"] > h_recv + 1.0:
            return None, "clock_pair_outside_raw_ping_interval"
        if pg["op_id"] in seen_ops:
            return None, "clock_ping_duplicated"
        seen_ops.add(pg["op_id"])
        use = bundle["ping_use"].setdefault(pg["op_id"], (stage, int(rep), peer))
        if use != (stage, int(rep), peer):
            return None, "clock_ping_reused_across_calibrations"
        linked.append((pr, pg))

    insts = {pg["inst"] for _pr, pg in linked}
    gens = {pg["gen"] for _pr, pg in linked}
    epochs = {int(pr.get("epoch", 0)) for pr, _pg in linked if pr.get("epoch") is not None}
    if len(insts) > 1 or len(gens) > 1 or len(epochs) > 1:
        return None, "peer_epoch_or_inst_changed_in_calibration"
    if gen is not None and gens != {gen}:
        return None, "peer_epoch_or_inst_changed_in_calibration"

    if extent is not None:
        f_lo, f_hi, t_lo, t_hi = extent
        before = [pg for _pr, pg in linked if pg["peer_frame"] < f_lo and pg["peer_tick_ms"] < t_lo]
        after = [pg for _pr, pg in linked if pg["peer_frame"] > f_hi and pg["peer_tick_ms"] > t_hi]
        if len(before) + len(after) != len(linked):
            return None, "clock_ping_inside_or_misordered_vs_take_rows"
        if not before or not after:
            return None, "clock_pings_not_bracketing_take_rows"

    theta_lo = -math.inf
    theta_hi = math.inf
    for _pr, pg in linked:
        lo_i = pg["t_lo"] - pg["peer_tick_ms"]
        hi_i = pg["t_hi"] - pg["peer_tick_ms"]
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
        "gen": next(iter(gens), 1),
    }, None


def _project_interval(tick_lo, tick_hi, cal):
    return tick_lo + cal["theta_lo"], tick_hi + cal["theta_hi"]


def _collect_take_bundles(ops, jobs, scenario_records, timeline):
    """Agrupa operaciones, filas crudas, estimulos y metadatos por toma, identificada por `(gen, take_id)` (BLOQ 2).

    `gen` es la generacion del servidor observada en el puente (reinicio de epoch logico o nueva instancia de proceso);
    el mismo `take_id` completo en una generacion nueva es otra toma. Los registros del escenario se asignan por orden
    de fichero: un estimulo pertenece a la ultima `take_meta` anterior con su `take_id`."""
    run_meta = {}
    clock_pairs = []
    metas_list = []
    latest = {}
    stim_by_idx = {}
    orphan_stim = []
    cut_raw = []
    rej_raw = []

    for rec in scenario_records:
        k = rec.get("kind")
        if k == "run_meta":
            run_meta = dict(rec)
        elif k == "clock_pair":
            clock_pairs.append(rec)
        elif k == "take_meta":
            tid = rec.get("take_id", "")
            if tid:
                latest[tid] = len(metas_list)
                metas_list.append(dict(rec))
        elif k == "stimulus":
            tid = rec.get("take_id", "")
            if tid in latest:
                stim_by_idx.setdefault(latest[tid], []).append(rec)
            else:
                orphan_stim.append(rec)
        elif k == "cut_window":
            cut_raw.append((dict(rec), latest.get(rec.get("take_id", ""))))
        elif k == "key_rejection":
            rej_raw.append((dict(rec), latest.get(rec.get("take_id", ""))))

    first_meta_idx = {}
    for idx, m in enumerate(metas_list):
        first_meta_idx.setdefault(m.get("take_id", ""), idx)
    for rec in orphan_stim:
        idx = first_meta_idx.get(rec.get("take_id", ""))
        if idx is not None:
            stim_by_idx.setdefault(idx, []).append(rec)

    gens_by_tid = {}
    for j in jobs.values():
        if j["verb"] in ("take_arm", "take_srv_observe_start", "take_cli_watch_start") and j.get("take_id"):
            gens_by_tid.setdefault(j["take_id"], set()).add(j["gen"])

    take_metas = {}
    take_order = []
    stimuli_by_take = {}
    keys_by_idx = {}
    collisions = []
    seen_count = {}
    prev_gen = 1
    for idx, meta in enumerate(metas_list):
        tid = meta.get("take_id", "")
        gens = sorted(gens_by_tid.get(tid, ()))
        n_prev = seen_count.get(tid, 0)
        seen_count[tid] = n_prev + 1
        if n_prev < len(gens):
            gen = gens[n_prev]
        elif gens:
            gen = gens[-1]
        else:
            gen = prev_gen
        prev_gen = gen
        key = (gen, tid)
        keys_by_idx[idx] = key
        if key in take_metas:
            collisions.append(key)
            continue
        take_metas[key] = meta
        take_order.append(key)
        stimuli_by_take[key] = list(stim_by_idx.get(idx, []))

    cut_windows = []
    for rec, idx in cut_raw:
        rec["_key"] = keys_by_idx.get(idx)
        cut_windows.append(rec)
    key_rejections = []
    for rec, idx in rej_raw:
        rec["_key"] = keys_by_idx.get(idx)
        key_rejections.append(rec)

    arm_jobs_by_take = {}
    srv_obs_rows = []
    cli_watch_rows = []
    srv_obs_jobs = []
    cli_watch_jobs = []
    for j in jobs.values():
        v = j["verb"]
        if v == "take_arm":
            arm_jobs_by_take.setdefault((j["gen"], j.get("take_id", "")), []).append(j)
        elif v == "take_srv_observe_start":
            srv_obs_jobs.append(j)
            for r in j["rows"]:
                r_copy = dict(r)
                r_copy["_watch_take_id"] = j.get("take_id", "")
                r_copy["_gen"] = j["gen"]
                srv_obs_rows.append(r_copy)
        elif v == "take_cli_watch_start":
            cli_watch_jobs.append(j)
            for r in j["rows"]:
                r_copy = dict(r)
                r_copy["_watch_take_id"] = j.get("take_id", "")
                r_copy["_gen"] = j["gen"]
                cli_watch_rows.append(r_copy)

    return {
        "run_meta": run_meta,
        "clock_pairs": clock_pairs,
        "take_metas": take_metas,
        "take_order": take_order,
        "identity_collisions": collisions,
        "stimuli_by_take": stimuli_by_take,
        "cut_windows": cut_windows,
        "key_rejections": key_rejections,
        "arm_jobs_by_take": arm_jobs_by_take,
        "srv_obs_rows": srv_obs_rows,
        "cli_watch_rows": cli_watch_rows,
        "srv_obs_jobs": srv_obs_jobs,
        "cli_watch_jobs": cli_watch_jobs,
        "ops": ops,
        "timeline": timeline,
        "pings": _collect_pings(ops),
        "ping_use": {},
    }


def _get_take_slice(key, bundle, ops=None):
    """Extrae las filas de `take_arm`, `take_srv_observe_start` y `take_cli_watch_start` de una toma (gen, take_id)."""
    cache = bundle.setdefault("_slice_cache", {})
    if key in cache:
        return cache[key]
    gen, take_id = key
    meta = bundle["take_metas"].get(key, {})
    arm_list = bundle["arm_jobs_by_take"].get(key, [])
    arm_job = arm_list[0] if arm_list else None
    arm_rows = arm_job["rows"] if arm_job else []

    s_lo = meta.get("srv_frame_lo")
    s_hi = meta.get("srv_frame_hi")
    c_lo = meta.get("cli_frame_lo")
    c_hi = meta.get("cli_frame_hi")

    srv_rows = [
        r for r in bundle["srv_obs_rows"]
        if r["_gen"] == gen
        and (
            r.get("_watch_take_id") == take_id
            or (r.get("subject_id") == take_id and r.get("row_kind") in ("take_terminal", "cleanup_done"))
            or (s_lo is not None and s_hi is not None and s_lo <= int(r.get("srv_frame", 0)) <= s_hi)
        )
    ]
    cli_rows = [
        r for r in bundle["cli_watch_rows"]
        if r["_gen"] == gen
        and (
            r.get("_watch_take_id") == take_id
            or r.get("ack_req_take_id") == take_id
            or (c_lo is not None and c_hi is not None and c_lo <= int(r.get("cli_frame", 0)) <= c_hi)
        )
    ]
    out = {
        "key": key,
        "gen": gen,
        "take_id": take_id,
        "meta": meta,
        "arm_job": arm_job,
        "arm_rows": arm_rows,
        "srv_rows": srv_rows,
        "cli_rows": cli_rows,
        "stimuli": bundle["stimuli_by_take"].get(key, []),
    }
    cache[key] = out
    return out


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
    keys = _stage_keys(bundle, stage_name)
    if len(keys) < reps_expected:
        return None, "missing", f"{stage_name}_missing_repetitions"

    rep_metrics = []
    for idx, key in enumerate(keys[:reps_expected], start=1):
        tslice = _get_take_slice(key, bundle, ops)
        rep_no = int(tslice["meta"].get("rep", idx))
        t_state, _t_row = _take_terminal(tslice, bundle)
        if t_state == "duplicate":
            return None, "fail", f"{stage_name}_r{rep_no}_duplicate_take_terminal"
        srv_cal, cli_cal, err = _calibrate_take(bundle, tslice, stage_name, rep_no)
        if err is not None:
            return None, "missing", f"{stage_name}_r{rep_no}_{err}"
        if t_state == "missing":
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
    """TOM-01 — disparo conjunto, desfase por intervalos y seleccion del canal (§5 TOM-01, R4-N3..N5, R5-N6, R5-N10, T7, T9).

    Devuelve `(check, canal)`: el canal ("rpc" | "common_time") solo se fija si el check pasa, una sola vez, y es el que
    consumen TOM-02, TOM-04 y TOM-05 (BLOQ 6). Una serie `rpc` valida pasa por si sola; la reserva solo se consulta
    cuando `rpc` no cumple."""
    s1_res, s1_st, s1_reason = _evaluate_series_tom01("S1", 3, bundle, ops, fixture)
    if s1_st != "ok":
        return _chk("TOM-01", s1_st, reason=s1_reason), None

    if s1_res["var_hi"] <= 100.0:
        return _chk(
            "TOM-01",
            "pass",
            observed={"active_mode": "rpc", "rpc_var_hi_ms": round(s1_res["var_hi"], 2)},
        ), "rpc"

    if s1_res["res_lo"] > 100.0:
        return _chk(
            "TOM-01",
            "fail",
            observed={"var_lo_ms": round(s1_res["var_lo"], 2), "res_lo_ms": round(s1_res["res_lo"], 2)},
            reason="rpc_local_variation_gt_100ms",
        ), None

    delivs_s1 = [m["deliv_mid_ms"] for m in s1_res["reps"]]
    deliv_spread_s1 = max(delivs_s1) - min(delivs_s1) if delivs_s1 else 0.0

    if s1_res["var_lo"] > 100.0 and s1_res["res_hi"] <= 100.0 and deliv_spread_s1 > 50.0:
        # T9 / R4-N4: la reserva solo vale si S1sel acredito la condicion causal y la serie common_time cumple.
        s1sel_res, s1sel_st, s1sel_reason = _evaluate_series_tom01("S1sel", 3, bundle, ops, fixture)
        if s1sel_st != "ok":
            return _chk("TOM-01", s1sel_st, reason=f"s1sel_{s1sel_reason}"), None
        sel_delays = [m["go_deliver_tick_ms"] - m["go_recv_tick_ms"] for m in s1sel_res["reps"]]
        if not (sel_delays[0] <= 20.0 and sel_delays[1] >= 120.0 and sel_delays[2] <= 20.0):
            return _chk("TOM-01", "fail", reason="s1sel_go_deliver_delay_pattern_invalid"), None
        if not (s1sel_res["var_lo"] > 100.0 and s1sel_res["res_hi"] <= 100.0):
            return _chk("TOM-01", "fail", reason="s1sel_causal_condition_not_accredited"), None

        s1c_res, s1c_st, s1c_reason = _evaluate_series_tom01("S1c", 3, bundle, ops, fixture)
        if s1c_st != "ok":
            return _chk("TOM-01", s1c_st, reason=f"s1c_{s1c_reason}"), None
        if s1c_res["res_lo"] > 100.0 or s1c_res["var_lo"] > 100.0:
            return _chk(
                "TOM-01",
                "fail",
                observed={"s1c_var_lo_ms": round(s1c_res["var_lo"], 2), "s1c_res_lo_ms": round(s1c_res["res_lo"], 2)},
                reason="common_time_variation_gt_100ms",
            ), None
        if s1c_res["var_hi"] <= 100.0:
            return _chk(
                "TOM-01",
                "pass",
                observed={
                    "active_mode": "common_time",
                    "rpc_var_lo_ms": round(s1_res["var_lo"], 2),
                    "common_time_var_hi_ms": round(s1c_res["var_hi"], 2),
                },
            ), "common_time"
        return _chk("TOM-01", "missing", reason="common_time_fallback_uncertain"), None

    if s1_res["var_lo"] > 100.0:
        return _chk("TOM-01", "fail", reason="variation_lower_bound_gt_100ms"), None

    return _chk(
        "TOM-01",
        "missing",
        observed={"var_lo_ms": round(s1_res["var_lo"], 2), "var_hi_ms": round(s1_res["var_hi"], 2)},
        reason="threshold_inside_uncertainty_interval",
    ), None


def _evaluate_stop_repetition(stage_name, rep_idx, tslice, bundle, expected_origin, fixture):
    """Evalúa una repetición de parada a los 3 s (web o tecla) para TOM-02."""
    run_meta = bundle["run_meta"]
    eps_look_deg = float(run_meta.get("eps_look_deg", 0.5))
    calib_step_deg = float(run_meta.get("calib_step_deg", 0.0))
    if calib_step_deg < 2.0 * eps_look_deg or eps_look_deg <= 0.0:
        return "missing", "look_stimulus_uncalibrated"

    arm_rows = tslice["arm_rows"]
    srv_rows = tslice["srv_rows"]
    cli_rows = tslice["cli_rows"]
    take_id = tslice["take_id"]
    pref = f"{stage_name}_r{rep_idx}"

    # La interrupcion inequivoca se decide ANTES de la calibracion: una calibracion perdida no la oculta (BLOQ 7).
    t_state, term_row = _take_terminal(tslice, bundle)
    if t_state == "duplicate":
        return "fail", f"{pref}_duplicate_take_terminal"
    if t_state == "missing":
        return "fail", f"{pref}_missing_terminal_or_interrupted"
    expected_so = f"parada:{expected_origin}"
    if term_row.get("state_or_origin") != expected_so:
        return "fail", f"{pref}_unexpected_terminal_{term_row.get('state_or_origin')}"
    if float(term_row.get("v3", 0.0)) < 2800.0:
        return "fail", f"{pref}_interrupted_before_3s"

    stop_obs_rows = [r for r in arm_rows if r.get("row_kind") == "stop_obs"]
    if not stop_obs_rows:
        return "fail", f"{pref}_missing_stop_obs"
    stop_obs = stop_obs_rows[0]
    if stop_obs.get("state_or_origin") != expected_so:
        return "fail", f"{pref}_stop_obs_mismatch"

    srv_cal, cli_cal, cal_err = _calibrate_take(bundle, tslice, stage_name, rep_idx)
    if cal_err is not None:
        return "missing", f"{pref}_{cal_err}"

    stim_kind = "web_stop" if expected_origin == "web" else ("key_press", "key_hold")
    stims = [
        s for s in tslice["stimuli"]
        if (s.get("stim_type") == stim_kind if isinstance(stim_kind, str) else s.get("stim_type") in stim_kind)
    ]
    if not stims:
        return "missing", f"{pref}_missing_stop_stimulus"
    t0_h = float(stims[0]["h_ms"])

    frame_samples = sorted(
        [r for r in cli_rows if r.get("row_kind") == "frame_sample"],
        key=lambda r: int(r.get("cli_frame", 0)),
    )
    if len(frame_samples) < 5:
        return "missing", f"{pref}_insufficient_frame_samples"

    # E9 anti-fabricacion: la serie de dt de frame ni es constante ni retrocede.
    tick_deltas = [
        round(float(frame_samples[i + 1]["cli_tick_ms"]) - float(frame_samples[i]["cli_tick_ms"]), 4)
        for i in range(len(frame_samples) - 1)
    ]
    if any(d <= 0.0 for d in tick_deltas):
        return "fail", f"{pref}_non_monotonic_frame_ticks"
    if len(tick_deltas) >= 10 and len(set(tick_deltas)) == 1:
        return "fail", f"{pref}_fabricated_constant_frame_dt"
    # ... ni los dt de Σtimeslice (que mide el motor) son constantes (E9, BLOQ 17).
    dt_deltas = [
        round(float(frame_samples[i + 1]["take_dtsum_ms"]) - float(frame_samples[i]["take_dtsum_ms"]), 4)
        for i in range(len(frame_samples) - 1)
        if int(frame_samples[i]["sandbox_cam_active_b"]) == 1 and int(frame_samples[i + 1]["sandbox_cam_active_b"]) == 1
    ]
    if len(dt_deltas) >= 10 and len(set(dt_deltas)) == 1:
        return "fail", f"{pref}_fabricated_constant_take_dtsum_step"

    pos_cam_idx = None
    for idx, r in enumerate(frame_samples):
        if int(r.get("sandbox_cam_active_b", 0)) == 1:
            pos_cam_idx = idx
            break
    if pos_cam_idx is None or pos_cam_idx == 0:
        return "missing", f"{pref}_missing_cam_start"

    go_deliv_rows = [r for r in cli_rows if r.get("row_kind") == "go_deliver"]
    if not go_deliv_rows:
        return "missing", f"{pref}_missing_go_deliver"
    go_deliv_frame = int(go_deliv_rows[0]["cli_frame"])
    pre_go_frames = [r for r in frame_samples if int(r["cli_frame"]) < go_deliv_frame]
    if not pre_go_frames:
        return "missing", f"{pref}_missing_pre_go_frames"
    for r in pre_go_frames[:pos_cam_idx]:
        if int(r.get("sandbox_cam_active_b", 0)) != 0:
            return "fail", f"{pref}_sandbox_cam_active_before_c_r"

    cli_tick_at_t0_lo = t0_h - cli_cal["theta_hi"]
    cli_tick_at_t0_hi = t0_h - cli_cal["theta_lo"]
    bracketing = [
        r for r in frame_samples
        if (cli_tick_at_t0_lo - 40.0) <= float(r["cli_tick_ms"]) <= (cli_tick_at_t0_hi + 40.0)
    ]
    if not bracketing:
        return "fail", f"{pref}_stimulus_outside_take_trace"
    dtsum_lo = min(float(r["take_dtsum_ms"]) for r in bracketing)
    dtsum_hi = max(float(r["take_dtsum_ms"]) for r in bracketing)
    if dtsum_hi < 2850.0 or dtsum_lo > 3150.0:
        return "fail", f"{pref}_stimulus_not_at_3000_pm_150ms"

    if expected_origin == "juego":
        win_samples = [
            r for r in frame_samples[pos_cam_idx:]
            if float(r["cli_tick_ms"]) <= cli_tick_at_t0_lo
        ]
        if not win_samples:
            return "missing", f"{pref}_empty_c_r_to_t0_window"
        for r in win_samples:
            for req_col in ("sandbox_cam_active_b", "hud_hidden_b", "quickbar_hide_flag_b", "quickbar_widget_visible_b"):
                if req_col not in r:
                    return "missing", f"{pref}_missing_col_{req_col}"
            if (
                int(r["sandbox_cam_active_b"]) != 1
                or int(r["hud_hidden_b"]) != 1
                or int(r["quickbar_hide_flag_b"]) != 1
                or int(r["quickbar_widget_visible_b"]) != 0
            ):
                return "fail", f"{pref}_hud_or_quickbar_not_hidden_in_window"
        st_ack, why_ack = _check_key_stop_ack(tslice, bundle, stage_name, rep_idx, stop_obs)
        if st_ack != "pass":
            return st_ack, why_ack

    stop_srv_frame = int(stop_obs.get("v1", stop_obs.get("srv_frame", 0)))
    stop_srv_tick = float(stop_obs.get("srv_tick_ms", 0.0))
    prior_srv_ticks = [
        float(r["srv_tick_ms"]) for r in (arm_rows + srv_rows)
        if int(r.get("srv_frame", 0)) < stop_srv_frame and float(r.get("srv_tick_ms", 0.0)) > 0.0
    ]
    srv_stop_prev_tick = max(prior_srv_ticks) if prior_srv_ticks else stop_srv_tick
    srv_stop_lo_h, srv_stop_hi_h = _project_interval(srv_stop_prev_tick, stop_srv_tick, srv_cal)
    st_lat, why_lat = _latency_verdict(f"{pref}_srv_stop_latency", srv_stop_lo_h - t0_h, srv_stop_hi_h - t0_h)
    if st_lat != "pass":
        return st_lat, why_lat

    rec, why_rec = _control_recovery_interval(tslice, cli_cal, run_meta, t0_h, frame_samples, pos_cam_idx)
    if why_rec is not None:
        return rec, f"{pref}_{why_rec}"
    st_lat, why_lat = _latency_verdict(f"{pref}_cli_control_recovery", rec[0], rec[1])
    if st_lat != "pass":
        return st_lat, why_lat

    # E9: movimiento continuo y parada real de actor_1
    mark_1 = fixture["actors"][0]["mark_pos_m"]
    act1_samples = sorted(
        [r for r in srv_rows if r.get("row_kind") == "act_sample" and r.get("subject_id") == "actor_1"],
        key=lambda r: int(r.get("srv_frame", 0)),
    )
    pre_stop_a1 = [r for r in act1_samples if int(r.get("srv_frame", 0)) <= stop_srv_frame]
    post_stop_a1 = [r for r in act1_samples if int(r.get("srv_frame", 0)) > stop_srv_frame]
    if not pre_stop_a1 or not post_stop_a1:
        return "fail", f"{pref}_missing_actor1_samples"
    max_disp_a1 = max(_dist3([r.get("v1", 0.0), r.get("v2", 0.0), r.get("v3", 0.0)], mark_1) for r in pre_stop_a1)
    if max_disp_a1 < 0.3:
        return "fail", f"{pref}_actor1_did_not_advance_before_stop"
    stop_pos_a1 = [post_stop_a1[0].get("v1", 0.0), post_stop_a1[0].get("v2", 0.0), post_stop_a1[0].get("v3", 0.0)]
    for r in post_stop_a1[1:]:
        if float(r.get("v4", 0.0)) > 0.05 or _dist3([r.get("v1", 0.0), r.get("v2", 0.0), r.get("v3", 0.0)], stop_pos_a1) > 0.1:
            return "fail", f"{pref}_actor1_continued_moving_after_stop"

    # Precondicion de gesto pendiente y vigilancia posterior hasta take_dtsum_ms >= 4800 (R4-N10, R5-N3, T10)
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
        return "missing", f"{pref}_pending_gesture_precondition_unobserved"

    post_stop_a2 = [r for r in act2_samples if int(r.get("srv_frame", 0)) >= stop_srv_frame]
    if not post_stop_a2:
        return "missing", f"{pref}_missing_post_stop_actor2_samples"

    final_4800_idx = None
    for idx, r in enumerate(post_stop_a2):
        if float(r.get("take_dtsum_ms", 0.0)) >= 4800.0:
            final_4800_idx = idx
            break
    if final_4800_idx is None:
        return "missing", f"{pref}_post_stop_coverage_lt_4800ms"

    watch_slice = post_stop_a2[: final_4800_idx + 1]
    for i in range(len(watch_slice) - 1):
        df = int(watch_slice[i + 1]["srv_frame"]) - int(watch_slice[i]["srv_frame"])
        if df != 1:
            return "fail", f"{pref}_post_stop_srv_frame_gap"
        dt_step = float(watch_slice[i + 1]["srv_tick_ms"]) - float(watch_slice[i]["srv_tick_ms"])
        if dt_step > 100.0:
            return "missing", f"{pref}_post_stop_low_freq_gap"

    for r in watch_slice:
        cb_cmd = int(r.get("v6", 0))
        cb_emote = int(r.get("v7", 0))
        exp_req = int(r.get("v9", 0))
        pend_cues = int(r.get("v10", 0))
        fut_fired = int(r.get("v11", 0))
        if exp_req != 0 or pend_cues != 0 or fut_fired != 0:
            return "fail", f"{pref}_pending_or_future_cues_not_cancelled"
        if cb_emote in (1, 44) or cb_cmd in (1000, 1050):
            return "fail", f"{pref}_cancelled_gesture_executed_after_stop"

    return "pass", None


def _eval_tom_02(bundle, ops, fixture, channel="rpc"):
    """TOM-02 — paradas a los 3 s (3 web, 3 tecla) del canal seleccionado, control en < 1 s y cues (§5 TOM-02, T9)."""
    if channel == "common_time":
        plan = (("S1c", "web"), ("S2c", "juego"))
    else:
        plan = (("S1", "web"), ("S2", "juego"))
    for stage_name, expected_origin in plan:
        keys = _stage_keys(bundle, stage_name)
        if len(keys) < 3:
            restart_ops = [
                op for op in ops
                if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "restart_epoch"
            ]
            for key in keys:
                ts = _get_take_slice(key, bundle, ops)
                t_state, t_row = _take_terminal(ts, bundle)
                if t_state != "ok" or float(t_row.get("v3", 0.0)) < 2800.0:
                    return _chk("TOM-02", "fail", reason=f"{stage_name}_interrupted_before_3s")
            if restart_ops and stage_name == "S1":
                return _chk("TOM-02", "fail", reason="peer_restarted_during_take")
            return _chk("TOM-02", "missing", reason=f"{stage_name}_missing_3_repetitions")

        for idx, key in enumerate(keys[:3], start=1):
            tslice = _get_take_slice(key, bundle, ops)
            rep_no = int(tslice["meta"].get("rep", idx))
            st, reason = _evaluate_stop_repetition(stage_name, rep_no, tslice, bundle, expected_origin, fixture)
            if st != "pass":
                return _chk("TOM-02", st, reason=reason)

    return _chk("TOM-02", "pass")


def _eval_tom_03(bundle, ops, hellos, fixture, ctx):
    """TOM-03 — tecla fijada sin conflicto, reasignacion tras recarga y pulsacion mantenida (§5 TOM-03, R5-N13, BLOQ 5).

    Los conflictos se recalculan en Python de las vinculaciones crudas exportadas; la tecla por defecto se contrasta con
    el `inputs.xml` del commit sellado; las activaciones salen de los bits crudos de `frame_sample.aux_n`
    (`press_edge_b + 2*hold_b + 4*pending_stop_b`), no de etiquetas."""
    expected_def = fixture.get("expected_default_key", "kF9")
    candidates = list(fixture.get("candidate_keys", ["kF9", "kF10", "kBackslash", "kRBracket"]))
    action_name = fixture.get("action_name", "UADsbxQaTakeStop")

    key_ops = [op for op in ops if op["verb"] == "take_key_op" and op["status"] == "ok"]
    audits = [op for op in key_ops if op["args_s"].get("op") == "audit_candidates"]
    binds = [op for op in key_ops if op["args_s"].get("op") == "bind_key"]
    restores = [op for op in key_ops if op["args_s"].get("op") == "restore_bindings"]

    if not audits or len(binds) < 2 or not restores:
        return _chk("TOM-03", "missing", reason="missing_key_op_sequence")

    audit = audits[0]
    if audit["args_s"].get("action_name") != action_name:
        return _chk("TOM-03", "fail", reason="wrong_action_name")
    if int(audit["read_n"].get("input_id", 0)) <= 0:
        return _chk("TOM-03", "fail", reason="input_id_not_registered")
    if not audit["read_s"].get("build_version"):
        return _chk("TOM-03", "fail", reason="missing_build_version")
    if int(audit["read_n"].get("candidates_checked_n", 0)) != len(candidates):
        return _chk("TOM-03", "missing", reason="audit_did_not_cover_all_candidates")

    # Conflictos recalculados de las vinculaciones observadas (no de contadores ni CSV de la sonda).
    conflicts = {}
    for act, key in _binding_rows(audit):
        if act != action_name and key in candidates:
            conflicts.setdefault(key, set()).add(act)
    free = [k for k in candidates if k not in conflicts]
    if expected_def in conflicts:
        return _chk("TOM-03", "fail", reason="default_key_conflict")
    if len(free) < 2:
        return _chk("TOM-03", "fail", reason="insufficient_free_candidate_keys")
    k_def, k_alt = free[0], free[1]
    if k_def != expected_def:
        return _chk("TOM-03", "fail", reason="default_key_conflict")
    if audit["read_s"].get("selected_def_key") != k_def or audit["read_s"].get("selected_alt_key") != k_alt:
        return _chk("TOM-03", "fail", reason="selected_keys_differ_from_observed_free_candidates")

    # La tecla por defecto de `inputs.xml` en el commit sellado es la de la fixture (R5-N13).
    src = ctx["sources"]
    xml_bytes = src.inputs_xml(ctx["git_head"])
    if xml_bytes is None:
        return _chk("TOM-03", "missing", reason="inputs_xml_unavailable_at_sealed_commit")
    xml_keys = _default_keys_from_inputs_xml(xml_bytes, action_name)
    if not xml_keys:
        return _chk("TOM-03", "fail", reason="inputs_xml_has_no_default_binding_for_action")
    if xml_keys[0] != expected_def:
        return _chk("TOM-03", "fail", reason="inputs_xml_default_key_differs_from_fixture")

    alt_binds = [b for b in binds if b["args_s"].get("target_key") == k_alt]
    if not alt_binds or int(alt_binds[0]["read_n"].get("export_called_b", 0)) != 1:
        return _chk("TOM-03", "fail", reason="alt_key_bind_did_not_export")
    if (action_name, k_alt) not in _binding_rows(alt_binds[0]) or (action_name, k_def) in _binding_rows(alt_binds[0]):
        return _chk("TOM-03", "fail", reason="alt_key_bind_not_in_raw_bindings")

    cli_insts = []
    for h in hellos:
        if h.get("peer") == "client" and h.get("inst") and h.get("inst") not in cli_insts:
            cli_insts.append(h.get("inst"))
    if len(cli_insts) < 2:
        return _chk("TOM-03", "fail", reason="client_not_reloaded_between_s0a_and_s0b")

    s0a_keys = _stage_keys(bundle, "S0a")
    s0b_keys = _stage_keys(bundle, "S0b")
    if not s0a_keys or not s0b_keys:
        return _chk("TOM-03", "missing", reason="missing_s0a_or_s0b_take")
    if not s0a_keys[0][1].endswith("keydef") or not s0b_keys[0][1].endswith("keyreb"):
        return _chk("TOM-03", "fail", reason="short_take_label_mismatch_s0")

    s0b = _get_take_slice(s0b_keys[0], bundle, ops)
    srv_cal, cli_cal, cal_err = _calibrate_take(bundle, s0b, "S0b", int(s0b["meta"].get("rep", 1)))
    if cal_err is not None:
        return _chk("TOM-03", "missing", reason=f"s0b_{cal_err}")
    stims = sorted(s0b["stimuli"], key=lambda s: float(s.get("h_ms", 0.0)))
    old_stims = [s for s in stims if s.get("key") == k_def]
    new_stims = [s for s in stims if s.get("key") == k_alt]
    if not old_stims or not new_stims:
        return _chk("TOM-03", "fail", reason="missing_old_or_new_key_stim_in_s0b")
    frames = sorted([r for r in s0b["cli_rows"] if r.get("row_kind") == "frame_sample"], key=lambda r: int(r["cli_frame"]))
    old_h = float(old_stims[0]["h_ms"])
    new_h = float(new_stims[0]["h_ms"])
    old_lo, old_hi = old_h - cli_cal["theta_hi"] - 40.0, old_h - cli_cal["theta_lo"] + 500.0
    new_lo, new_hi = new_h - cli_cal["theta_hi"] - 40.0, new_h - cli_cal["theta_lo"] + 500.0
    in_old = [r for r in frames if old_lo <= float(r["cli_tick_ms"]) <= old_hi]
    in_new = [r for r in frames if new_lo <= float(r["cli_tick_ms"]) <= new_hi]
    if not in_old or float(in_old[-1]["cli_tick_ms"]) - float(in_old[0]["cli_tick_ms"]) < 450.0:
        return _chk("TOM-03", "missing", reason="s0b_old_key_window_not_observed_500ms")
    if any(_frame_bits(r)[0] for r in in_old if float(r["cli_tick_ms"]) < new_lo):
        return _chk("TOM-03", "fail", reason="old_key_triggered_or_new_key_failed_in_s0b")
    if not any(_frame_bits(r)[0] for r in in_new):
        return _chk("TOM-03", "fail", reason="old_key_triggered_or_new_key_failed_in_s0b")
    edge_frames = [r for r in frames if _frame_bits(r)[0]]
    edges_s0b = [
        r for r in s0b["cli_rows"]
        if r.get("row_kind") == "key_edge" and r.get("detail") == "press_accepted"
    ]
    if len(edge_frames) != 1 or len(edges_s0b) != 1 or float(edges_s0b[0].get("take_dtsum_ms", 0.0)) < 1000.0:
        return _chk("TOM-03", "fail", reason="old_key_triggered_or_new_key_failed_in_s0b")
    t_state, t_row = _take_terminal(s0b, bundle)
    if t_state != "ok" or t_row.get("state_or_origin") != "parada:juego":
        return _chk("TOM-03", "fail", reason="s0b_not_stopped_by_new_key")

    s2_keys = _stage_keys(bundle, "S2")
    if len(s2_keys) < 2:
        return _chk("TOM-03", "missing", reason="missing_s2_r2_for_hold_check")
    s2 = _get_take_slice(s2_keys[1], bundle, ops)
    hold_stims = [
        s for s in s2["stimuli"]
        if s.get("stim_type") in ("key_hold", "key_press") and float(s.get("hold_ms", 0.0)) >= 600.0
    ]
    if not hold_stims:
        return _chk("TOM-03", "fail", reason="missing_600ms_hold_stimulus_in_s2_r2")
    s2_frames = sorted([r for r in s2["cli_rows"] if r.get("row_kind") == "frame_sample"], key=lambda r: int(r["cli_frame"]))
    edge_frames = [r for r in s2_frames if _frame_bits(r)[0]]
    hold_frames = [r for r in s2_frames if _frame_bits(r)[1]]
    edges_r2 = [
        r for r in s2["cli_rows"]
        if r.get("row_kind") == "key_edge" and r.get("detail") == "press_accepted"
    ]
    if len(edge_frames) != 1 or len(edges_r2) != 1 or int(edges_r2[0].get("aux_n", 0)) != 1:
        return _chk("TOM-03", "fail", reason="held_key_produced_multiple_activations")
    if len(hold_frames) < 2 or float(hold_frames[-1]["cli_tick_ms"]) - float(hold_frames[0]["cli_tick_ms"]) < 500.0:
        return _chk("TOM-03", "missing", reason="held_key_not_observed_as_held_for_600ms")
    hold_run_ok = all(
        int(b["cli_frame"]) - int(a["cli_frame"]) == 1 for a, b in zip(hold_frames, hold_frames[1:])
    )
    if not hold_run_ok:
        return _chk("TOM-03", "fail", reason="held_key_not_held_continuously_in_raw_frames")

    if (action_name, k_def) not in _binding_rows(restores[-1]):
        return _chk("TOM-03", "fail", reason="default_key_not_restored")

    return _chk("TOM-03", "pass")


def _eval_tom_04(bundle, ops, channel="rpc"):
    """TOM-04 — proteccion del director y restauracion exacta en la frontera terminal (§5 TOM-04, H20, R4-N11, R5-N1, T9-T11).

    El golpe protector se acredita SOLO dentro de la ventana protegida [comienzo efectivo, frontera) (BLOQ 10); el
    registro terminal es unico; el `director_sample` tiene continuidad por frame hasta la frontera; la restauracion se
    contrasta con lecturas posteriores."""
    stage = "S1c" if channel == "common_time" else "S1"
    keys = _stage_keys(bundle, stage)
    if len(keys) < 3:
        return _chk("TOM-04", "missing", reason="s1_missing_3_repetitions")

    expected_pre_by_rep = {1: 1, 2: 0, 3: 1}
    any_valid_melee = False

    for idx, key in enumerate(keys[:3], start=1):
        tslice = _get_take_slice(key, bundle, ops)
        rep_no = int(tslice["meta"].get("rep", idx))
        arm_rows = tslice["arm_rows"]
        srv_rows = tslice["srv_rows"]

        arm_ready_rows = [r for r in arm_rows if r.get("row_kind") == "arm_ready"]
        go_sent_rows = [r for r in arm_rows if r.get("row_kind") == "go_sent"]
        dispatch_rows = [r for r in arm_rows if r.get("row_kind") == "dispatch"]
        stop_obs_rows = [r for r in arm_rows if r.get("row_kind") == "stop_obs"]
        post_end_rows = [r for r in arm_rows if r.get("row_kind") == "post_stop_end"]
        t_state, term_row = _take_terminal(tslice, bundle)
        if t_state == "duplicate":
            return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_duplicate_take_terminal")

        if not arm_ready_rows or not go_sent_rows or t_state != "ok":
            return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_missing_control_or_terminal_rows")

        arm_ready = arm_ready_rows[0]
        go_sent = go_sent_rows[0]

        pre_dmg_b = int(arm_ready.get("v1", -1))
        health_pre = float(arm_ready.get("v2", 1.0))
        if pre_dmg_b != expected_pre_by_rep.get(rep_no, pre_dmg_b):
            return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_unexpected_allow_dmg_pre")

        if dispatch_rows:
            eff_start_frame = min(int(r.get("v1", r.get("srv_frame", 0))) for r in dispatch_rows)
        else:
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

        pre_samples = [ds for ds in dir_samples if int(ds.get("srv_frame", 0)) < frontier_frame]
        post_samples = [ds for ds in dir_samples if int(ds.get("srv_frame", 0)) >= frontier_frame]
        if (
            not pre_samples
            or int(pre_samples[0]["srv_frame"]) > eff_start_frame + 1
            or int(pre_samples[-1]["srv_frame"]) < frontier_frame - 1
            or any(int(b["srv_frame"]) - int(a["srv_frame"]) != 1 for a, b in zip(pre_samples, pre_samples[1:]))
        ):
            return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_director_samples_not_continuous_to_frontier")
        if not post_samples:
            return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_no_director_sample_after_frontier")

        rep_valid_hit = False
        for mh in melee_hits:
            mf = int(mh.get("srv_frame", 0))
            if mf >= frontier_frame:
                continue  # un golpe posterior a la frontera no acredita el melee protector
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

        for ds in pre_samples:
            if int(ds.get("v3", 1)) != 0:
                return _chk("TOM-04", "fail", reason=f"s1_r{rep_no}_allow_dmg_true_before_frontier")
            if int(ds.get("v2", 0)) != 1:
                return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_gk07_director_not_alive")
            if float(ds.get("v1", 0.0)) + 1e-5 < health_pre:
                return _chk("TOM-04", "missing", reason=f"s1_r{rep_no}_gk07_director_health_decreased")
        for ds in post_samples:
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


def _eval_tom_05(bundle, ops, fixture, channel="rpc"):
    """TOM-05 — tres tomas con reset crudo en Python y camino B6 (§5 TOM-05, R5-N9, T1, T8, T9, BLOQ 11).

    Cada toma exige su `take_scene_prep(op="reset")` y una observacion fresca (`act_observe`) posterior al reset y
    anterior al armado. La camara se evalua desde su primer frame activo hasta su SALIDA observada (primer frame con la
    camara del jugador): las tres tomas se comparan en su prefijo comun, con continuidad exigida hasta esa frontera."""
    stage = "S1c" if channel == "common_time" else "S1"
    keys = _stage_keys(bundle, stage)
    if len(keys) < 3:
        return _chk("TOM-05", "missing", reason="s1_missing_3_repetitions")

    resets = [op for op in ops if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "reset" and op["status"] == "ok"]
    observes = [op for op in ops if op["verb"] == "act_observe" and op["status"] == "ok"]
    perturbs = [
        op for op in ops
        if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "perturb_fixture" and op["status"] == "ok"
    ]

    keyframes = fixture["camera_path"]["keyframes"]
    path_dur = float(fixture["camera_path"]["duration_ms"])
    if path_dur < 4000.0:
        return _chk("TOM-05", "fail", reason="camera_path_duration_lt_4000ms")

    used_obs = set()
    prev_arm_idx = -1
    slices = []
    for idx, key in enumerate(keys[:3], start=1):
        tslice = _get_take_slice(key, bundle, ops)
        slices.append(tslice)
        if tslice["arm_job"] is None:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_missing_arm_job")
        arm_idx = tslice["arm_job"]["start_op"]["res_idx"]
        pre_resets = [op for op in resets if prev_arm_idx < op["res_idx"] < arm_idx]
        if not pre_resets:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_missing_reset_before_take")
        reset_op = pre_resets[-1]
        fresh = [op for op in observes if reset_op["res_idx"] < op["res_idx"] < arm_idx and op["op_id"] not in used_obs]
        if not fresh or fresh[-1]["frame_recv"] < reset_op["frame_done"]:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_missing_fresh_observation_after_reset")
        obs = fresh[-1]
        used_obs.add(obs["op_id"])
        st, reason = _correlate_and_verify_b6_reset_obs(obs["read_rows"], fixture)
        if st != "pass":
            return _chk("TOM-05", st, reason=f"s1_r{idx}_{reason}")
        if idx == 2:
            if not any(prev_arm_idx < p["res_idx"] < reset_op["res_idx"] for p in perturbs):
                return _chk("TOM-05", "fail", reason="missing_perturb_fixture_before_r2_reset")
        prev_arm_idx = arm_idx

    traces_by_rep = []
    all_sampled_t = set()

    for idx, tslice in enumerate(slices, start=1):
        frames = sorted(
            [r for r in tslice["cli_rows"] if r.get("row_kind") == "frame_sample"],
            key=lambda r: int(r.get("cli_frame", 0)),
        )
        first_active = next((i for i, r in enumerate(frames) if int(r.get("sandbox_cam_active_b", 0)) == 1), None)
        if first_active is None:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_empty_active_cam_trace")
        exit_idx = next(
            (i for i in range(first_active, len(frames)) if int(frames[i].get("sandbox_cam_active_b", 0)) == 0), None
        )
        if exit_idx is None:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_camera_exit_not_observed")
        active_samples = frames[first_active:exit_idx]
        if not active_samples:
            return _chk("TOM-05", "missing", reason=f"s1_r{idx}_empty_active_cam_trace")

        dts = []
        for i in range(len(active_samples) - 1):
            df = int(active_samples[i + 1]["cli_frame"]) - int(active_samples[i]["cli_frame"])
            if df != 1:
                return _chk("TOM-05", "fail", reason=f"s1_r{idx}_missing_rendered_frame_in_trace")
            dts.append(float(active_samples[i + 1]["take_dtsum_ms"]) - float(active_samples[i]["take_dtsum_ms"]))
        if int(frames[exit_idx]["cli_frame"]) - int(active_samples[-1]["cli_frame"]) != 1:
            return _chk("TOM-05", "fail", reason=f"s1_r{idx}_missing_rendered_frame_before_camera_exit")

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


def _eval_tom_06(bundle, ops, ctx):
    """TOM-06 — negativas de preparacion, conexion (`take-conn-drop` 2 ramas) y stops (§5 TOM-06, R4-N17, R5-N5, T13)."""
    lease_ms = ctx["lease_ms"]
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

    s3a = _case_keys(bundle, ("S3a",))
    for c_id in ("conn_drop_no_effects", "conn_drop_after_effects", "stop_before_go", "double_stop_at_go", "stop_at_600ms"):
        if c_id not in s3a:
            return _chk("TOM-06", "missing", reason=f"s3a_missing_case_{c_id}")

    cut_pairs = _pair_cuts(bundle)

    key_no = s3a["conn_drop_no_effects"]
    ts_no = _get_take_slice(key_no, bundle, ops)
    if any(r.get("row_kind") in ("go_sent", "dispatch") for r in ts_no["arm_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_no_effects_emitted_go_or_dispatch")
    if any(r.get("row_kind") == "frame_sample" and int(r.get("sandbox_cam_active_b", 0)) == 1 for r in ts_no["cli_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_no_effects_activated_camera")
    t_state, t_no = _take_terminal(ts_no, bundle)
    if t_state == "duplicate":
        return _chk("TOM-06", "fail", reason="conn_drop_no_effects_duplicate_take_terminal")
    if t_state != "ok" or "terminada" in t_no.get("state_or_origin", ""):
        return _chk("TOM-06", "fail", reason="conn_drop_no_effects_invalid_terminal")
    cuts_no = [p for p in cut_pairs if p[0].get("_key") == key_no]
    if not cuts_no:
        return _chk("TOM-06", "missing", reason="conn_drop_no_effects_missing_cut_window")
    for cw, bc in cuts_no:
        st_l, why_l = _verify_lease_discipline(cw, bc, ts_no, lease_ms)
        if st_l != "pass":
            return _chk("TOM-06", st_l, reason=why_l)

    key_af = s3a["conn_drop_after_effects"]
    ts_af = _get_take_slice(key_af, bundle, ops)
    arm_job_after = ts_af["arm_job"]
    if not arm_job_after:
        return _chk("TOM-06", "missing", reason="conn_drop_after_effects_missing_arm_job")
    if not any(r.get("row_kind") == "go_sent" for r in ts_af["arm_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_missing_go_sent")
    if not any(r.get("row_kind") == "dispatch" for r in ts_af["arm_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_missing_dispatch")
    if not any(r.get("row_kind") == "frame_sample" and int(r.get("sandbox_cam_active_b", 0)) == 1 for r in ts_af["cli_rows"]):
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_no_active_cam_frames")
    if any(r.get("row_kind") in ("take_terminal", "cleanup_done") for r in ts_af["arm_rows"]):
        return _chk("TOM-06", "fail", reason="terminal_row_illegally_appended_to_stopped_take_arm")

    t_state, tr = _take_terminal(ts_af, bundle)
    if t_state == "duplicate":
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_duplicate_take_terminal")
    cleanup_after = [r for r in ts_af["srv_rows"] if r.get("row_kind") == "cleanup_done" and r.get("subject_id") == ts_af["take_id"]]
    cli_exit_after = [r for r in ts_af["cli_rows"] if r.get("row_kind") == "cli_safety_exit"]
    if t_state != "ok" or not cleanup_after or not cli_exit_after:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_missing_r5_n5_terminal_evidence")
    if tr.get("state_or_origin") != "parada:hombre_muerto":
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_wrong_terminal_state_or_origin")
    if int(tr.get("v6", 0)) != 1 or int(tr.get("v7", 0)) != 1:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_transitions_or_restorations_not_1")
    if int(tr.get("v9", 1)) != 0 or int(tr.get("v10", 1)) != 0 or int(tr.get("v11", 1)) != 0:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_cues_or_pending_not_cancelled")
    expected_pre_dmg = int(ts_af["meta"].get("allow_dmg_pre_b", 1))
    if int(tr.get("v8", -1)) != expected_pre_dmg:
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_allow_dmg_not_restored")
    post_dir = [
        r for r in ts_af["srv_rows"]
        if r.get("row_kind") == "director_sample" and int(r.get("srv_frame", 0)) > int(tr.get("v5", 0))
    ]
    if not post_dir:
        return _chk("TOM-06", "missing", reason="conn_drop_after_effects_no_raw_director_reading_after_restoration")
    if any(int(r.get("v3", -1)) != expected_pre_dmg for r in post_dir):
        return _chk("TOM-06", "fail", reason="conn_drop_after_effects_allow_dmg_not_restored_in_later_readings")

    cuts_after = [p for p in cut_pairs if p[0].get("_key") == key_af]
    if not cuts_after:
        return _chk("TOM-06", "missing", reason="conn_drop_after_effects_missing_cut_window")
    for cw, bc in cuts_after:
        st_l, why_l = _verify_lease_discipline(cw, bc, ts_af, lease_ms)
        if st_l != "pass":
            return _chk("TOM-06", st_l, reason=why_l)
        if bc["peer"] == "server":
            reconn_tick = float(bc["reconnect_tick"])
            if float(tr.get("v4", 0.0)) <= lease_ms:
                return _chk("TOM-06", "fail", reason="conn_drop_srv_lease_age_not_gt_lease_ms")
            if arm_job_after["onjobend_tick_ms"] <= 0.0 or arm_job_after["onjobend_tick_ms"] >= reconn_tick:
                return _chk("TOM-06", "fail", reason="conn_drop_onjobend_not_before_reconnection")
            if arm_job_after["released_tick_ms"] <= 0.0 or arm_job_after["released_tick_ms"] >= reconn_tick:
                return _chk("TOM-06", "fail", reason="conn_drop_released_not_before_reconnection")

    for stop_case in ("stop_before_go", "double_stop_at_go", "stop_at_600ms"):
        ts_st = _get_take_slice(s3a[stop_case], bundle, ops)
        t_state, t_row = _take_terminal(ts_st, bundle)
        if t_state == "duplicate":
            return _chk("TOM-06", "fail", reason=f"{stop_case}_duplicate_take_terminal")
        if t_state != "ok":
            return _chk("TOM-06", "fail", reason=f"{stop_case}_missing_take_terminal")
        if not t_row.get("state_or_origin", "").startswith("parada:") or "terminad" in t_row.get("state_or_origin", ""):
            return _chk("TOM-06", "fail", reason=f"{stop_case}_invalid_terminal_state")
        if int(t_row.get("v6", 0)) != 1 or int(t_row.get("v7", 0)) != 1:
            return _chk("TOM-06", "fail", reason=f"{stop_case}_multiple_transitions_or_restorations")
        stop_ops = [
            op for op in ops
            if op["verb"] == "take_stop" and op["status"] == "ok" and op["args_s"].get("take_id") == ts_st["take_id"]
        ]
        need = 2 if stop_case == "double_stop_at_go" else 1
        if len(stop_ops) < need:
            return _chk("TOM-06", "missing", reason=f"{stop_case}_missing_raw_take_stop_orders")
        if any(int(op["read_n"].get("transitions_n", 0)) != 1 or int(op["read_n"].get("restorations_n", 0)) != 1 for op in stop_ops):
            return _chk("TOM-06", "fail", reason=f"{stop_case}_take_stop_repeated_effects")

    return _chk("TOM-06", "pass")


def _verify_look_response_after_local_exit(cli_rows, stimuli, contemp_yaw_ref, eps_look_deg, calib_sign, after_exit_frame):
    """T4: tras una salida local de camara hay respuesta de mirada atribuible a un pulso (guinada frente a la referencia)."""
    pulses = [s for s in stimuli if s.get("stim_type") == "look_pulse"]
    if not pulses:
        return False
    for r in cli_rows:
        if r.get("row_kind") != "frame_sample" or int(r.get("sandbox_cam_active_b", 1)) != 0:
            continue
        if int(r.get("cli_frame", 0)) <= after_exit_frame:
            continue
        dyaw = (float(r.get("cam_yaw_deg", 0.0)) - float(contemp_yaw_ref)) * calib_sign
        if dyaw >= eps_look_deg:
            return True
    return False


def _eval_tom_07(bundle, ops, ctx, hellos=None):
    """TOM-07 — negativas de tecla (S3b), reintentos/carreras/hombre muerto (S3c) y reinicio de proceso (S3d)."""
    if bundle["identity_collisions"]:
        return _chk("TOM-07", "missing", reason="take_identity_collision_same_epoch_and_take_id")

    res = _tom07_ui_negatives(bundle, ops)
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])

    s3b = _case_keys(bundle, ("S3b",))
    if "prior_terminal_same_epoch" not in s3b:
        return _chk("TOM-07", "missing", reason="s3b_missing_prior_terminal_take")
    prior_key = s3b["prior_terminal_same_epoch"]
    ts_prior = _get_take_slice(prior_key, bundle, ops)
    p_state, _p = _take_terminal(ts_prior, bundle)
    if ts_prior["arm_job"] is None or p_state != "ok":
        return _chk("TOM-07", "fail", reason="t3_prior_take_not_really_armed_and_terminated")

    rej_by_case = {}
    for r in bundle["key_rejections"]:
        rej_by_case.setdefault(r.get("case_id"), []).append(r)
    for req_rej in S3B_CASES:
        if req_rej not in rej_by_case:
            return _chk("TOM-07", "missing", reason=f"s3b_missing_rejection_{req_rej}")
        if len(rej_by_case[req_rej]) != 1:
            return _chk("TOM-07", "fail", reason=f"s3b_{req_rej}_not_exactly_one_rejection")
    guardians = [rej_by_case[c][0].get("_key") for c in S3B_CASES]
    if len(set(guardians)) != 4 or any(g is None for g in guardians):
        return _chk("TOM-07", "fail", reason="t10_guardian_not_unique_per_case")
    for case_id in S3B_CASES:
        res = _tom07_rejection_case(bundle, ops, rej_by_case[case_id][0], case_id, prior_key)
        if res is not None:
            return _chk("TOM-07", res[0], reason=res[1])

    c3 = _case_keys(bundle, ("S3c", "S3d"))
    required_s3c = (
        "drop_first_req", "drop_first_ack", "simul_key_and_web", "held_go_after_key",
        "stale_notify_take_a", "stale_notify_take_b", "ack2", "new", "epoch_dup_1", "epoch_dup_2",
        "cut_nokey", "cut_before", "cut_after", "procdup_1", "procdup_2",
    )
    for cname in required_s3c:
        if cname not in c3:
            return _chk("TOM-07", "missing", reason=f"s3c_missing_case_{cname}")

    res = _tom07_drop_first_req(bundle, ops, c3["drop_first_req"])
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])
    res = _tom07_drop_first_ack(bundle, ops, c3["drop_first_ack"])
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])

    ts_sim = _get_take_slice(c3["simul_key_and_web"], bundle, ops)
    t_state, term_sim = _take_terminal(ts_sim, bundle)
    if t_state != "ok" or int(term_sim.get("v6", 0)) != 1 or int(term_sim.get("v7", 0)) != 1:
        return _chk("TOM-07", "fail", reason="simultaneous_key_and_web_produced_multiple_stops")

    ts_hgo = _get_take_slice(c3["held_go_after_key"], bundle, ops)
    key_edges_hgo = [r for r in ts_hgo["cli_rows"] if r.get("row_kind") == "key_edge"]
    if not key_edges_hgo:
        return _chk("TOM-07", "missing", reason="held_go_missing_key_edge")
    key_frame_hgo = int(key_edges_hgo[0]["cli_frame"])
    go_deliver = [r for r in ts_hgo["cli_rows"] if r.get("row_kind") == "go_deliver"]
    after_frames = [
        r for r in ts_hgo["cli_rows"]
        if r.get("row_kind") == "frame_sample" and int(r.get("cli_frame", 0)) > key_frame_hgo
    ]
    if not go_deliver or not after_frames:
        return _chk("TOM-07", "missing", reason="held_go_not_observed_after_key_press")
    cam_prep_ops = [op for op in ops if op["verb"] == "take_cam_prep" and op["status"] == "ok"]
    release_go_ops = [op for op in cam_prep_ops if op["args_s"].get("op") == "release_held_go"]
    if (
        any(int(r.get("sandbox_cam_active_b", 0)) == 1 for r in after_frames)
        or not release_go_ops
        or int(release_go_ops[-1]["read_n"].get("late_go_ignored_n", 0)) < 1
    ):
        return _chk("TOM-07", "fail", reason="late_go_reactivated_camera_after_key_press")

    res = _tom07_stale_notify(bundle, ops, c3["stale_notify_take_a"], c3["stale_notify_take_b"])
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])

    if not c3["ack2"][1].endswith("ack2") or not c3["new"][1].endswith("new"):
        return _chk("TOM-07", "fail", reason="ack2_or_new_short_label_invalid")
    res = _tom07_late_ack_and_cache(bundle, ops, c3["ack2"], c3["new"])
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])

    res = _tom07_epoch_cases(bundle, ops, c3["epoch_dup_1"], c3["epoch_dup_2"], "epoch_dup", False)
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])

    res = _tom07_cut_cases(bundle, ops, ctx, c3)
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])

    srv_hellos = [h for h in (hellos or []) if h.get("peer") == "server"]
    if len(srv_hellos) >= 2:
        new_t = float(srv_hellos[-1].get("t_ms", 0.0))
        if _client_lease_exceeded_in_restart(bundle, new_t, ctx["lease_ms"]):
            return _chk("TOM-07", "missing", reason="s3d_server_restart_exceeded_client_lease")
    res = _tom07_epoch_cases(bundle, ops, c3["procdup_1"], c3["procdup_2"], "procdup", True)
    if res is not None:
        return _chk("TOM-07", res[0], reason=res[1])

    return _chk("TOM-07", "pass")


def evaluate(part_dir, *, repo_root=None, sources=None):
    """Evalúa una carpeta de parte de S-toma usando únicamente `samples/` y `manifest.json`.

    `sources` es la costura de lectura del commit sellado (fixture, sello de la expansion, `inputs.xml`); por defecto lee
    git. Los tests la sustituyen para entregar fuentes sinteticas, nunca para saltarse una comprobacion."""
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
    if not bridge_path.is_file() or not scenario_path.is_file():
        return _make_inconcluso(["artifact_unverified"])

    try:
        bridge_records = f03_common.read_jsonl(bridge_path)
        scenario_records = f03_common.read_jsonl(scenario_path)
    except Exception:
        return _make_inconcluso(["artifact_unverified"])

    ops, jobs, hellos, _ = _reconstruct_ops_and_jobs(bridge_records)
    ok_s_toma, st_reasons, ctx = _verify_s_toma_integrity(
        pdir, manifest, bridge_records, scenario_records, ops, jobs, hellos, repo_root=root, sources=sources
    )
    if not ok_s_toma:
        return _make_inconcluso(st_reasons)
    fixture = ctx["fixture"]

    timeline = _bridge_timeline(bridge_records)
    bundle = _collect_take_bundles(ops, jobs, scenario_records, timeline)
    reused = _frame_ranges_overlap(bundle)
    if reused is not None:
        return _make_inconcluso(["raw_rows_reused_across_takes"])

    tom01, channel = _eval_tom_01(bundle, ops, fixture)
    ch = channel or "rpc"
    checks = [
        tom01,
        _eval_tom_02(bundle, ops, fixture, channel=ch),
        _eval_tom_03(bundle, ops, hellos, fixture, ctx),
        _eval_tom_04(bundle, ops, channel=ch),
        _eval_tom_05(bundle, ops, fixture, channel=ch),
        _eval_tom_06(bundle, ops, ctx),
        _eval_tom_07(bundle, ops, ctx, hellos=hellos),
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
        metrics={"wire_cap": wire_cap, "channel": channel or "none"},
        reasons=list(dict.fromkeys(reasons)),
    )



class _GitSources:
    """Lectura de ficheros y de árboles de un commit del repositorio (A3/A5). Los tests pueden sustituirla."""

    def __init__(self, repo_root):
        self.root = Path(repo_root)
        self._top = None

    def _toplevel(self):
        if self._top is None:
            self._top = f03_common._git_toplevel(self.root)
        return self._top

    def show(self, git_head, rel_path):
        top = self._toplevel()
        if top is None or not isinstance(git_head, str) or not git_head.strip():
            return None
        try:
            proc = subprocess.run(
                ["git", "show", f"{git_head.strip()}:{rel_path}"],
                cwd=top,
                capture_output=True,
                check=False,
            )
        except OSError:
            return None
        return proc.stdout if proc.returncode == 0 else None

    def ls(self, git_head, prefix):
        top = self._toplevel()
        if top is None or not isinstance(git_head, str) or not git_head.strip():
            return []
        try:
            proc = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", git_head.strip(), "--", prefix],
                cwd=top,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
        except OSError:
            return []
        if proc.returncode != 0:
            return []
        return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]

    def fixture_bytes(self, git_head):
        for rel in FIXTURE_REL_CANDIDATES:
            blob = self.show(git_head, rel)
            if blob:
                return blob
        return None

    def exp_stamp(self, git_head):
        """Sello de la expansion recalculado desde las fuentes del commit (BLOQ 12). Usa la funcion de S3 si existe."""
        try:
            s3 = importlib.import_module("s3_eval")
        except Exception:
            s3 = None
        fn = getattr(s3, "compute_exp_stamp_at_commit", None)
        if callable(fn):
            try:
                return str(fn(git_head, repo_root=self.root))
            except f03_common.StampSourceUnavailableError:
                raise
            except Exception as exc:
                raise f03_common.StampSourceUnavailableError("stamp_source_unavailable") from exc
        for prefix in EXP_PROBE_PREFIXES:
            paths = self.ls(git_head, prefix)
            if not paths:
                continue
            pairs = []
            for path in sorted(paths):
                rel = path[len(prefix) + 1:] if path.startswith(prefix + "/") else path
                if rel == wire.STAMP_REL_PATH:
                    continue
                blob = self.show(git_head, path)
                if blob is None:
                    raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")
                pairs.append((rel, blob))
            if pairs:
                return wire.compute_probe_stamp_from_pairs(pairs)
        raise f03_common.StampSourceUnavailableError("stamp_source_unavailable")

    def inputs_xml(self, git_head):
        for prefix in INPUTS_XML_PREFIXES:
            for path in sorted(self.ls(git_head, prefix)):
                if path.endswith("/inputs.xml"):
                    blob = self.show(git_head, path)
                    if blob:
                        return blob
        return None


def _default_keys_from_inputs_xml(xml_bytes, action_name):
    """Teclas por defecto (en orden de documento) que `inputs.xml` vincula a `action_name`; None si no se puede leer."""
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return None
    keys = []
    for el in root.iter():
        if el.tag != "input" or el.attrib.get("name") != action_name:
            continue
        for sub in el.iter():
            if sub.tag == "btn" and sub.attrib.get("name"):
                keys.append(sub.attrib["name"])
    return keys


def _bridge_timeline(bridge_records):
    """Polls 200 y cortes del puente por peer, con su `t_ms` (reloj del arnes) y el tick crudo del peer (BLOQ 9)."""
    polls = {"server": [], "client": []}
    cuts = []
    open_cuts = {}
    for idx, rec in enumerate(bridge_records):
        ev = rec.get("ev") or rec.get("event")
        peer = rec.get("peer")
        if ev in ("poll", "keepalive") and rec.get("http", 200) == 200 and peer in polls:
            t_ms = rec.get("t_ms")
            tick_s = rec.get("tick_s")
            if isinstance(t_ms, (int, float)) and isinstance(tick_s, (int, float)):
                polls[peer].append((float(t_ms), float(tick_s) * 1000.0, idx))
        elif ev == "cut_start" and peer in polls:
            open_cuts[peer] = (rec.get("t_ms"), idx)
        elif ev == "cut_end" and peer in open_cuts:
            st_t, st_idx = open_cuts.pop(peer)
            cuts.append({"peer": peer, "start_t": st_t, "end_t": rec.get("t_ms"), "start_idx": st_idx, "end_idx": idx})
    for c in cuts:
        before = [p for p in polls[c["peer"]] if p[2] < c["start_idx"]]
        after = [p for p in polls[c["peer"]] if p[2] > c["end_idx"]]
        c["last_ok_t"] = before[-1][0] if before else None
        c["last_ok_tick"] = before[-1][1] if before else None
        c["reconnect_t"] = after[0][0] if after else None
        c["reconnect_tick"] = after[0][1] if after else None
    return {"polls": polls, "cuts": cuts}


def _frame_extent(rows, frame_key, tick_key):
    frames = [int(r[frame_key]) for r in rows if frame_key in r]
    ticks = [float(r[tick_key]) for r in rows if tick_key in r]
    if not frames or not ticks:
        return None
    return min(frames), max(frames), min(ticks), max(ticks)


def _collect_pings(ops):
    pings = {}
    for op in ops:
        if op["verb"] != "take_clock_ping" or op["status"] != "ok":
            continue
        n = op["read_n"]
        if "peer_tick_ms" not in n or "peer_frame" not in n:
            continue
        t_lo = op.get("t_deliver") if isinstance(op.get("t_deliver"), (int, float)) else op.get("t_enq")
        t_hi = op.get("t_result")
        if not isinstance(t_lo, (int, float)) or not isinstance(t_hi, (int, float)):
            continue
        key = (op["peer"], float(n["peer_tick_ms"]), int(n["peer_frame"]))
        pings[key] = {
            "op_id": op["op_id"],
            "peer": op["peer"],
            "inst": op["inst"],
            "gen": op["gen"],
            "peer_tick_ms": float(n["peer_tick_ms"]),
            "peer_frame": int(n["peer_frame"]),
            "t_lo": float(t_lo),
            "t_hi": float(t_hi),
        }
    return pings


def _stage_keys(bundle, stage):
    keys = [k for k in bundle["take_order"] if bundle["take_metas"].get(k, {}).get("stage") == stage]
    return sorted(keys, key=lambda k: int(bundle["take_metas"][k].get("rep", 0) or 0))


def _case_keys(bundle, stages):
    out = {}
    for k in bundle["take_order"]:
        m = bundle["take_metas"].get(k, {})
        if m.get("stage") in stages:
            out[m.get("case_id", k[1])] = k
    return out


def _slice_srv_extent(tslice):
    return _frame_extent(tslice["arm_rows"] + tslice["srv_rows"], "srv_frame", "srv_tick_ms")


def _slice_cli_extent(tslice):
    return _frame_extent(tslice["cli_rows"], "cli_frame", "cli_tick_ms")


def _calibrate_take(bundle, tslice, stage, rep):
    """Calibra los dos peers para una toma: (srv_cal, cli_cal, error)."""
    srv_cal, err = _calibrate_peer_clock(bundle, "server", stage, rep, extent=_slice_srv_extent(tslice), gen=tslice["gen"])
    if srv_cal is None:
        return None, None, f"srv_{err}"
    cli_cal, err = _calibrate_peer_clock(bundle, "client", stage, rep, extent=_slice_cli_extent(tslice), gen=tslice["gen"])
    if cli_cal is None:
        return None, None, f"cli_{err}"
    return srv_cal, cli_cal, None


def _take_terminal(tslice, bundle):
    """Registro terminal UNICO de la toma (BLOQ 10): ("ok", fila) | ("missing", None) | ("duplicate", None)."""
    gen, tid = tslice["key"]
    rows = [
        r for r in bundle["srv_obs_rows"]
        if r["_gen"] == gen and r.get("row_kind") == "take_terminal" and r.get("subject_id") == tid
    ]
    if not rows:
        return "missing", None
    if len(rows) > 1:
        return "duplicate", None
    return "ok", rows[0]


def _frame_ranges_overlap(bundle):
    """Anti-reutilizacion (BLOQ 4): los frames crudos de un mismo peer e instancia no se solapan entre tomas."""
    by_peer = {"server": [], "client": []}
    for key in bundle["take_order"]:
        ts = _get_take_slice(key, bundle)
        ext_s = _slice_srv_extent(ts)
        ext_c = _slice_cli_extent(ts)
        if ext_s is not None and ts["arm_job"] is not None:
            by_peer["server"].append((key, ts["gen"], ext_s[0], ext_s[1]))
        if ext_c is not None and any(r.get("row_kind") == "frame_sample" for r in ts["cli_rows"]):
            frames = [int(r["cli_frame"]) for r in ts["cli_rows"] if r.get("row_kind") == "frame_sample"]
            by_peer["client"].append((key, ts["gen"], min(frames), max(frames)))
    for peer, ranges in by_peer.items():
        for i in range(len(ranges)):
            for j in range(i + 1, len(ranges)):
                a = ranges[i]
                b = ranges[j]
                if a[1] != b[1] and peer == "server":
                    continue
                if a[2] <= b[3] and b[2] <= a[3]:
                    return peer, a[0], b[0]
    return None


def _latency_verdict(prefix, lo, hi):
    """Criterio del brief sobre la COTA SUPERIOR (BLOQ 15): una cota inferior que incluye cero no es fabricacion."""
    if hi < 0.0:
        return "fail", f"{prefix}_response_precedes_stimulus"
    if lo >= 1000.0:
        return "fail", f"{prefix}_ge_1000ms"
    if hi >= 1000.0:
        return "missing", f"{prefix}_uncertain"
    return "pass", None


def _control_recovery_interval(tslice, cli_cal, run_meta, t0_h, frame_samples, pos_cam_idx):
    """`t1`: primer frame desde `f_rel` con camara del jugador cuya guinada difiere de la referencia contemporanea en
    >= eps en el sentido del pulso y con un pulso ya emitido desde `t0` (R4-N6). Devuelve (lo, hi) o (status, motivo)."""
    eps_look_deg = float(run_meta.get("eps_look_deg", 0.5))
    calib_sign = 1.0 if float(run_meta.get("calib_sign", 1.0)) >= 0.0 else -1.0
    contemp_yaw_ref = tslice["meta"].get("contemp_yaw_ref_deg")
    if contemp_yaw_ref is None:
        return "missing", "missing_contemp_yaw_ref"
    contemp_yaw_ref = float(contemp_yaw_ref)

    f_rel_idx = None
    for idx in range(pos_cam_idx, len(frame_samples)):
        if int(frame_samples[idx].get("sandbox_cam_active_b", 1)) == 0:
            f_rel_idx = idx
            break
    if f_rel_idx is None:
        return "fail", "camera_never_released"

    look_pulses = sorted(
        [s for s in tslice["stimuli"] if s.get("stim_type") == "look_pulse" and float(s.get("h_ms", 0.0)) >= t0_h],
        key=lambda s: float(s["h_ms"]),
    )
    if not look_pulses:
        return "missing", "missing_look_pulses_after_t0"
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
                return "fail", "yaw_shifted_before_look_pulse"
            continue
        if r_lo_h < first_pulse_h:
            continue
        if dyaw >= eps_look_deg:
            t1_idx = idx
            break
    if t1_idx is None:
        return "fail", "no_attributed_look_response"

    t1_pos = frame_samples[t1_idx]
    t1_neg = frame_samples[t1_idx - 1] if t1_idx > 0 else t1_pos
    t1_lo_h, t1_hi_h = _project_interval(float(t1_neg["cli_tick_ms"]), float(t1_pos["cli_tick_ms"]), cli_cal)
    return (t1_lo_h - t0_h, t1_hi_h - t0_h), None


def _check_key_stop_ack(tslice, bundle, stage_name, rep_idx, stop_obs):
    """TOM-02 (tecla): `ack_recv` con los DOS pares completos, la instantanea actual y la recepcion cruda del servidor (BLOQ 3)."""
    take_id = tslice["take_id"]
    cli_rows = tslice["cli_rows"]
    pref = f"{stage_name}_r{rep_idx}"

    key_edges = [r for r in cli_rows if r.get("row_kind") == "key_edge" and r.get("detail") == "press_accepted"]
    if not key_edges:
        return "missing", f"{pref}_key_dead_with_sandbox_cam"
    rpc_stops = [r for r in cli_rows if r.get("row_kind") == "rpc_stop_sent" and r.get("detail") == take_id]
    ack_recvs = [r for r in cli_rows if r.get("row_kind") == "ack_recv" and r.get("ack_req_take_id") == take_id]
    if not rpc_stops or not ack_recvs:
        return "fail", f"{pref}_missing_correlated_ack_recv"
    ack = ack_recvs[0]
    epoch = int(ack.get("ack_req_epoch_n", 0))
    if (
        epoch <= 0
        or int(ack.get("ack_cur_epoch_n", 0)) != epoch
        or ack.get("ack_req_take_id") != take_id
        or ack.get("ack_req_state") != "parada"
        or ack.get("ack_req_origin") != "juego"
        or ack.get("ack_resp_class") not in ("first_terminal", "repeat_terminal")
        or ack.get("ack_cur_take_id") != take_id
        or ack.get("ack_cur_state") != "parada"
        or ack.get("ack_cur_origin") != "juego"
    ):
        return "fail", f"{pref}_ack_recv_columns_mismatch"
    if float(ack.get("cli_tick_ms", 0.0)) < float(rpc_stops[0].get("cli_tick_ms", 0.0)):
        return "fail", f"{pref}_ack_before_rpc_stop_sent"

    # El epoch y la secuencia de la instantanea se contrastan con los TAKE_STATE crudos que el cliente recibio (T5/T6).
    state_recvs = [r for r in cli_rows if r.get("row_kind") == "take_state_recv" and r.get("ack_cur_take_id") == take_id]
    if not state_recvs:
        return "missing", f"{pref}_no_take_state_recv_to_cross_check_ack_snapshot"
    if any(int(r.get("ack_cur_epoch_n", 0)) != epoch for r in state_recvs):
        return "fail", f"{pref}_ack_epoch_differs_from_take_state_epoch"
    term_states = [r for r in state_recvs if r.get("ack_cur_state") == "parada"]
    if not term_states or int(ack.get("aux_n", 0)) != int(term_states[-1].get("aux_n", -1)) or int(ack.get("aux_n", 0)) <= 0:
        return "fail", f"{pref}_ack_cur_seq_differs_from_terminal_take_state_seq"

    gen, _tid = tslice["key"]
    key_rpcs = [
        r for r in bundle["srv_obs_rows"]
        if r["_gen"] == gen and r.get("row_kind") == "key_rpc" and r.get("subject_id") == take_id
    ]
    if not key_rpcs:
        return "missing", f"{pref}_no_raw_server_key_rpc_record"
    sent_seqs = {int(r.get("aux_n", 0)) for r in rpc_stops}
    if any(int(r.get("v2", -1)) not in sent_seqs for r in key_rpcs):
        return "fail", f"{pref}_server_received_key_rpc_never_sent_by_client"
    if not any(r.get("state_or_origin") == "accepted" and int(r.get("v1", 0)) == epoch for r in key_rpcs):
        return "fail", f"{pref}_server_did_not_accept_key_rpc_of_this_pair"
    if int(stop_obs.get("v11", 0)) < 1:
        return "fail", f"{pref}_server_did_not_record_ack_sent"
    return "pass", None


def _binding_rows(op):
    """Vinculaciones crudas exportadas por `take_key_op` (tabla `action_name`, `key_name`; BLOQ 5)."""
    return [
        (str(r.get("action_name", "")), str(r.get("key_name", "")))
        for r in op["read_rows"]
        if "action_name" in r and "key_name" in r
    ]


def _frame_bits(row):
    aux = int(row.get("aux_n", 0))
    return aux & 1, (aux >> 1) & 1, (aux >> 2) & 1


def _pair_cuts(bundle):
    """Cada `cut_window` del escenario con SU corte real del puente (k-esimo del mismo peer), BLOQ 9."""
    by_peer = {"server": [], "client": []}
    for c in bundle["timeline"]["cuts"]:
        by_peer.setdefault(c["peer"], []).append(c)
    used = {}
    pairs = []
    for cw in bundle["cut_windows"]:
        peer = cw.get("peer")
        i = used.get(peer, 0)
        used[peer] = i + 1
        lst = by_peer.get(peer, [])
        pairs.append((cw, lst[i] if i < len(lst) else None))
    return pairs


def _verify_lease_discipline(cw, bc, tslice, lease_ms):
    """T13/E1.7: con el lease vencido no sale GO, orden de actor, RPC ni movimiento de camara, y la limpieza corre una vez.

    El ultimo poll/keepalive 200 y la reconexion salen del PUENTE (reloj `tick_s` del propio peer); el lease es el de la
    identidad (no el declarado por el runner); la emision de cada peer se mide en SU reloj: las recepciones del otro
    peer no prueban una emision (BLOQ 9). Devuelve (status, motivo)."""
    if bc is None or bc.get("last_ok_tick") is None or bc.get("reconnect_tick") is None:
        return "missing", "cut_window_without_raw_bridge_cut"
    try:
        if abs(float(cw.get("lease_ms", -1.0)) - float(lease_ms)) > 1e-6:
            return "missing", "cut_window_lease_ms_differs_from_identity"
        if (
            abs(float(cw.get("last_ok_poll_h_ms", -1e12)) - float(bc["last_ok_t"])) > 2.0
            or abs(float(cw.get("last_ok_poll_tick_ms", -1e12)) - float(bc["last_ok_tick"])) > 2.0
        ):
            return "missing", "cut_window_declaration_differs_from_raw_bridge"
    except (TypeError, ValueError):
        return "missing", "cut_window_invalid_fields"
    expire = float(bc["last_ok_tick"]) + float(lease_ms)
    reconn = float(bc["reconnect_tick"])
    peer = bc["peer"]
    gen_rows_srv = tslice["srv_rows"]
    if peer == "server":
        for r in tslice["arm_rows"]:
            if r.get("row_kind") in ("go_sent", "dispatch") and expire < float(r.get("srv_tick_ms", 0.0)) < reconn:
                return "fail", "server_emitted_go_or_dispatch_with_expired_lease"
        for r in gen_rows_srv:
            if r.get("row_kind") == "rpc_emit" and int(r.get("v2", 0)) == 1:
                if float(r.get("v1", 0.0)) > float(lease_ms) or expire < float(r.get("srv_tick_ms", 0.0)) < reconn:
                    return "fail", "server_emitted_rpc_with_expired_lease"
        cleanups = [r for r in gen_rows_srv if r.get("row_kind") == "cleanup_done" and r.get("subject_id") == tslice["take_id"]]
        if len(cleanups) != 1:
            return "fail", "server_safety_cleanup_not_run_exactly_once"
        if not any(
            r.get("row_kind") in ("act_sample", "director_sample") and expire < float(r.get("srv_tick_ms", 0.0)) < reconn
            for r in gen_rows_srv
        ):
            return "missing", "server_observer_did_not_continue_during_cut"
    else:
        for r in tslice["cli_rows"]:
            rtick = float(r.get("cli_tick_ms", 0.0))
            if r.get("row_kind") == "rpc_stop_sent" and expire < rtick < reconn:
                return "fail", "client_emitted_stop_rpc_with_expired_lease"
            if r.get("row_kind") == "frame_sample" and (expire + 50.0) < rtick < reconn and int(r.get("sandbox_cam_active_b", 0)) == 1:
                return "fail", "client_kept_sandbox_cam_active_with_expired_lease"
        exits = [r for r in tslice["cli_rows"] if r.get("row_kind") == "cli_safety_exit"]
        if len(exits) != 1:
            return "fail", "client_safety_exit_not_run_exactly_once"
        if not any(
            r.get("row_kind") == "frame_sample" and expire < float(r.get("cli_tick_ms", 0.0)) < reconn
            for r in tslice["cli_rows"]
        ):
            return "missing", "client_observer_did_not_continue_during_cut"
    return "pass", None


def _status_ops(ops, verb, t_min=None, **fields):
    out = []
    for op in ops:
        if op["verb"] != verb or op["args_s"].get("op") != "status" or op["status"] != "ok":
            continue
        if t_min is not None and (op.get("t_result") is None or float(op["t_result"]) < t_min):
            continue
        if all(op["read_s"].get(k) == v for k, v in fields.items()):
            out.append(op)
    return sorted(out, key=lambda o: o["res_idx"])


def _tom07_ui_negatives(bundle, ops):
    cam_prep_ops = [op for op in ops if op["verb"] == "take_cam_prep" and op["status"] == "ok"]
    blocker_ops = [op for op in cam_prep_ops if op["args_s"].get("op") == "set_ui_blocker"]
    ignored_details = {r.get("detail") for r in bundle["cli_watch_rows"] if r.get("row_kind") == "key_edge"}
    for req_ign in ("ignored_no_take", "ignored_menu", "ignored_chat"):
        if req_ign not in ignored_details:
            return "missing", f"s3b_missing_{req_ign}"
    for r in bundle["cli_watch_rows"]:
        if r.get("row_kind") == "key_edge" and str(r.get("detail", "")).startswith("ignored_") and int(r.get("aux_n", 0)) != 0:
            return "fail", "s3b_ignored_key_counted_as_activation"
    no_take = _case_keys(bundle, ("S3b",)).get("no_take_keys")
    if no_take is not None:
        ts_nt = _get_take_slice(no_take, bundle, ops)
        if any(r.get("row_kind") == "key_edge" and r.get("detail") == "press_accepted" for r in ts_nt["cli_rows"]):
            return "fail", "s3b_key_accepted_without_active_take"
        if any(r.get("row_kind") == "rpc_stop_sent" for r in ts_nt["cli_rows"]):
            return "fail", "s3b_key_without_take_sent_stop_rpc"
    if not any(op["args_s"].get("ui_blocker") == "menu" and int(op["read_n"].get("menu_open_b", 0)) == 1 for op in blocker_ops):
        return "fail", "s3b_menu_blocker_not_observed_open"
    if not any(op["args_s"].get("ui_blocker") == "chat" and int(op["read_n"].get("chat_open_b", 0)) == 1 for op in blocker_ops):
        return "fail", "s3b_chat_blocker_not_observed_open"
    none_blockers = [op for op in blocker_ops if op["args_s"].get("ui_blocker") == "none"]
    if not none_blockers or any(
        int(op["read_n"].get("menu_open_b", 1)) != 0 or int(op["read_n"].get("chat_open_b", 1)) != 0 for op in none_blockers
    ):
        return "fail", "s3b_menu_or_chat_not_closed_with_close_menu"
    return None


S3B_CASES = ("old_take_same_epoch", "other_epoch", "other_director_c1", "other_director_c2")


def _tom07_rejection_case(bundle, ops, rej, case_id, prior_key):
    """Un caso de S3b con SU guardiana (T10): rechazo por RPC crudo, instantanea, cache y reconciliacion (T3-T6, BLOQ 3)."""
    run_meta = bundle["run_meta"]
    eps_look_deg = float(run_meta.get("eps_look_deg", 0.5))
    calib_sign = 1.0 if float(run_meta.get("calib_sign", 1.0)) >= 0.0 else -1.0
    gkey = rej.get("_key")
    if gkey is None or gkey not in bundle["take_metas"]:
        return "missing", f"s3b_{case_id}_rejection_without_guardian_take"
    ts = _get_take_slice(gkey, bundle, ops)
    gen, gtid = gkey
    pref = f"s3b_{case_id}"

    t_state, term = _take_terminal(ts, bundle)
    if t_state == "duplicate":
        return "fail", f"{pref}_duplicate_guardian_terminal"
    if t_state != "ok":
        return "missing", f"{pref}_guardian_without_terminal"
    if term.get("state_or_origin") != "parada:web":
        return "fail", f"{pref}_guardian_not_closed_by_web"
    if int(term.get("v6", 0)) != 1 or int(term.get("v7", 0)) != 1:
        return "fail", f"{pref}_guardian_effects_not_single"

    srv_cal, cli_cal, cal_err = _calibrate_take(bundle, ts, "S3b", int(ts["meta"].get("rep", 0)))
    if cal_err is not None:
        return "missing", f"{pref}_{cal_err}"

    srv_state_rows = [r for r in ts["srv_rows"] if r.get("row_kind") == "key_rpc"]
    pair_tid = prior_key[1] if case_id == "old_take_same_epoch" else gtid
    pair_rows = [r for r in srv_state_rows if r.get("subject_id") == pair_tid]
    sent = [r for r in ts["cli_rows"] if r.get("row_kind") == "rpc_stop_sent" and r.get("detail") == pair_tid]
    if not pair_rows or not sent:
        return "fail", f"{pref}_missing_raw_rpc_records"
    sent_seqs = {int(r.get("aux_n", 0)) for r in sent}
    if any(int(r.get("v2", -1)) not in sent_seqs for r in pair_rows):
        return "fail", f"{pref}_server_rpc_not_matching_client_retry_seq"
    other_rows = [r for r in srv_state_rows if r.get("subject_id") != pair_tid]
    if other_rows:
        return "fail", f"{pref}_unexpected_key_rpc_for_other_pair"

    state_recvs = sorted(
        [r for r in ts["cli_rows"] if r.get("row_kind") == "take_state_recv" and r.get("ack_cur_take_id") == gtid],
        key=lambda r: int(r.get("cli_frame", 0)),
    )
    if not state_recvs:
        return "fail", f"{pref}_no_take_state_recv"
    epoch = int(state_recvs[0].get("ack_cur_epoch_n", 0))
    if epoch <= 0 or any(int(r.get("ack_cur_epoch_n", 0)) != epoch for r in state_recvs):
        return "fail", f"{pref}_inconsistent_take_state_epoch"

    acks = [r for r in ts["cli_rows"] if r.get("row_kind") == "ack_recv" and r.get("ack_req_take_id") == pair_tid]
    if case_id == "old_take_same_epoch":
        if any(r.get("state_or_origin") != "repeat_terminal" for r in pair_rows):
            return "fail", f"{pref}_server_did_not_answer_repeat_terminal"
        prior_ts = _get_take_slice(prior_key, bundle, ops)
        p_state, p_term = _take_terminal(prior_ts, bundle)
        if p_state != "ok":
            return "fail", f"{pref}_prior_take_not_terminal"
        p_st, _, p_or = str(p_term.get("state_or_origin", "")).partition(":")
        if not acks:
            return "fail", f"{pref}_missing_repeat_terminal_ack"
        ack = acks[0]
        if (
            int(ack.get("ack_req_epoch_n", 0)) != epoch
            or int(ack.get("ack_cur_epoch_n", 0)) != epoch
            or ack.get("ack_resp_class") != "repeat_terminal"
            or ack.get("ack_req_state") != p_st
            or ack.get("ack_req_origin") != p_or
            or ack.get("ack_cur_take_id") != gtid
            or ack.get("ack_cur_state") != "rodando"
            or int(ack.get("aux_n", 0)) != int(state_recvs[0].get("aux_n", -1))
        ):
            return "fail", f"{pref}_ack_pair_or_snapshot_mismatch"
    else:
        if acks:
            return "fail", f"{pref}_rejected_pair_received_an_ack"
        if any(r.get("state_or_origin") != "rejected" for r in pair_rows):
            return "fail", f"{pref}_server_accepted_or_answered_a_rejected_pair"
        req_epochs = {int(r.get("v1", 0)) for r in pair_rows}
        if case_id == "other_epoch" and epoch in req_epochs:
            return "fail", f"{pref}_pair_epoch_equals_current_epoch"
        if case_id != "other_epoch" and req_epochs != {epoch}:
            return "fail", f"{pref}_pair_epoch_differs_from_current_epoch"

    # Marca cruda del rechazo en el servidor, proyectada a h_ms por intervalos (T5).
    rej_tick = min(float(r.get("srv_tick_ms", 0.0)) for r in pair_rows)
    rej_lo_h, _rej_hi_h = _project_interval(rej_tick, rej_tick, srv_cal)

    st_srv = [
        op for op in _status_ops(ops, "take_scene_prep", t_min=rej_lo_h, active_take_id=gtid)
        if op["gen"] == gen
    ]
    if not st_srv:
        return "missing", f"{pref}_no_server_snapshot_after_rejection"
    snap = st_srv[0]
    if int(snap["read_n"].get("transitions_n", 0)) != 0 or snap["read_s"].get("take_state") != "rodando":
        return "fail", f"{pref}_guardian_not_intact_in_server_snapshot"
    if case_id in ("other_director_c1", "other_director_c2"):
        want_payload = "dir_main" if case_id == "other_director_c1" else "dir_other"
        rs = snap["read_s"]
        if (
            rs.get("reg_engine_uid") != "qa-uid-dir-other"
            or not rs.get("sender_engine_uid")
            or rs.get("sender_engine_uid") == "qa-uid-dir-other"
            or rs.get("payload_sender_id") != want_payload
        ):
            return "fail", f"{pref}_engine_uid_or_payload_precondition_invalid"
        if int(snap["read_n"].get("srv_key_rpc_rejected_n", 0)) < len(pair_rows):
            return "fail", f"{pref}_server_rejected_counter_below_raw_record_count"

    # Reconciliacion de la cache del cliente con la instantanea del servidor: 5 campos y plazo <= 1000 ms (T5).
    want = (
        int(snap["read_n"].get("srv_epoch", 0)),
        snap["read_s"].get("active_take_id"),
        snap["read_s"].get("take_state"),
        snap["read_s"].get("take_origin"),
        snap["read_s"].get("director_id"),
    )
    reconciled = None
    for sr in state_recvs:
        app_lo_h, app_hi_h = _project_interval(float(sr["cli_tick_ms"]), float(sr["cli_tick_ms"]), cli_cal)
        if app_hi_h < rej_lo_h:
            continue
        got = (
            int(sr.get("ack_cur_epoch_n", 0)),
            sr.get("ack_cur_take_id"),
            sr.get("ack_cur_state"),
            sr.get("ack_cur_origin"),
            sr.get("detail"),
        )
        if got == want:
            reconciled = (sr, app_hi_h - rej_lo_h)
            break
    if reconciled is None:
        return "fail", f"{pref}_t5_cache_not_reconciled_with_server_snapshot"
    if reconciled[1] > 1000.0:
        return "fail", f"{pref}_t5_reconcile_after_1000ms"
    sr_row = reconciled[0]
    cache = _status_ops(ops, "take_cam_prep", t_min=rej_lo_h, cli_cached_take_id=gtid)
    if not cache:
        return "missing", f"{pref}_no_client_cache_status"
    c = cache[0]
    got_cache = (
        int(c["read_n"].get("cli_cached_epoch", 0)),
        c["read_s"].get("cli_cached_take_id"),
        c["read_s"].get("cli_cached_state"),
        c["read_s"].get("cli_cached_origin"),
        c["read_s"].get("cli_cached_director_id"),
    )
    if got_cache != want or int(c["read_n"].get("cli_state_seq", -1)) != int(sr_row.get("aux_n", -2)):
        return "fail", f"{pref}_t5_client_cache_status_differs_from_server_snapshot"

    # Control recuperado con respuesta de mirada atribuible al pulso (R4-N6): tras la salida local de camara.
    frames = sorted([r for r in ts["cli_rows"] if r.get("row_kind") == "frame_sample"], key=lambda r: int(r["cli_frame"]))
    first_active = next((i for i, r in enumerate(frames) if int(r.get("sandbox_cam_active_b", 0)) == 1), None)
    exit_frame = None
    if first_active is not None:
        for r in frames[first_active:]:
            if int(r.get("sandbox_cam_active_b", 1)) == 0:
                exit_frame = int(r["cli_frame"])
                break
    if exit_frame is None:
        return "fail", f"{pref}_t4_camera_not_released_locally"
    ref = float(ts["meta"].get("contemp_yaw_ref_deg", 0.0))
    if not _verify_look_response_after_local_exit(ts["cli_rows"], ts["stimuli"], ref, eps_look_deg, calib_sign, exit_frame):
        return "fail", f"{pref}_t4_missing_look_response_after_rejection"
    return None


def _key_rpc_rows(bundle, key):
    gen, tid = key
    return [
        r for r in bundle["srv_obs_rows"]
        if r["_gen"] == gen and r.get("row_kind") == "key_rpc" and r.get("subject_id") == tid
    ]


def _sent_rows(ts):
    return sorted(
        [r for r in ts["cli_rows"] if r.get("row_kind") == "rpc_stop_sent" and r.get("detail") == ts["take_id"]],
        key=lambda r: (int(r.get("aux_n", 0)), int(r.get("cli_frame", 0))),
    )


def _tom07_drop_first_req(bundle, ops, key):
    ts = _get_take_slice(key, bundle, ops)
    if ts["arm_job"] is None:
        return "missing", "drop_first_req_missing_arm_job"
    if ts["arm_job"]["stop_inject"] != "drop_first_req":
        return "fail", "drop_first_req_inject_not_in_raw_arm_order"
    seqs = [int(r.get("aux_n", 0)) for r in _sent_rows(ts)]
    krpc = _key_rpc_rows(bundle, key)
    if 0 not in seqs or 1 not in seqs:
        return "fail", "drop_first_req_not_stopped_by_retry"
    if {int(r.get("v2", -1)) for r in krpc} != {1} or any(r.get("state_or_origin") != "accepted" for r in krpc):
        return "fail", "drop_first_req_first_request_not_dropped_or_retry_not_accepted"
    t_state, term = _take_terminal(ts, bundle)
    if t_state == "duplicate":
        return "fail", "drop_first_req_duplicate_take_terminal"
    if t_state != "ok" or term.get("state_or_origin") != "parada:juego":
        return "fail", "drop_first_req_not_stopped_by_retry"
    if int(term.get("v6", 0)) != 1 or int(term.get("v7", 0)) != 1:
        return "fail", "drop_first_req_multiple_transitions_or_restorations"
    # R4-N9: cota superior < 1000 ms desde SU propio t0, de lecturas crudas calibradas (BLOQ 1), no de resumenes.
    srv_cal, cli_cal, err = _calibrate_take(bundle, ts, "S3c", int(ts["meta"].get("rep", 0)))
    if err is not None:
        return "missing", f"drop_first_req_{err}"
    stims = [s for s in ts["stimuli"] if s.get("stim_type") in ("key_press", "key_hold")]
    if not stims:
        return "missing", "drop_first_req_missing_key_stimulus"
    t0_h = float(stims[0]["h_ms"])
    term_frame = int(term.get("v1", 0))
    term_tick = float(term.get("v2", 0.0))
    prior = [
        float(r["srv_tick_ms"]) for r in (ts["arm_rows"] + ts["srv_rows"])
        if int(r.get("srv_frame", 0)) < term_frame and float(r.get("srv_tick_ms", 0.0)) > 0.0
    ]
    lo_h, hi_h = _project_interval(max(prior) if prior else term_tick, term_tick, srv_cal)
    st_l, why = _latency_verdict("drop_first_req_retry_srv_stop_latency", lo_h - t0_h, hi_h - t0_h)
    if st_l != "pass":
        return st_l, why
    frames = sorted([r for r in ts["cli_rows"] if r.get("row_kind") == "frame_sample"], key=lambda r: int(r["cli_frame"]))
    pos_cam_idx = next((i for i, r in enumerate(frames) if int(r.get("sandbox_cam_active_b", 0)) == 1), None)
    if pos_cam_idx is None:
        return "missing", "drop_first_req_missing_cam_start"
    rec, why_rec = _control_recovery_interval(ts, cli_cal, bundle["run_meta"], t0_h, frames, pos_cam_idx)
    if why_rec is not None:
        return rec, f"drop_first_req_{why_rec}"
    st_l, why = _latency_verdict("drop_first_req_retry_cli_control_recovery", rec[0], rec[1])
    if st_l != "pass":
        return st_l, why
    return None


def _tom07_drop_first_ack(bundle, ops, key):
    ts = _get_take_slice(key, bundle, ops)
    if ts["arm_job"] is None:
        return "missing", "drop_first_ack_missing_arm_job"
    if ts["arm_job"]["stop_inject"] != "drop_first_ack":
        return "fail", "drop_first_ack_inject_not_in_raw_arm_order"
    t_state, term = _take_terminal(ts, bundle)
    if t_state != "ok" or int(term.get("v6", 0)) != 1 or int(term.get("v7", 0)) != 1:
        return "fail", "drop_first_ack_failed_idempotent_retry_ack"
    sent = _sent_rows(ts)
    seqs = [int(r.get("aux_n", 0)) for r in sent]
    krpc = sorted(_key_rpc_rows(bundle, key), key=lambda r: int(r.get("v2", 0)))
    decisions = [(int(r.get("v2", -1)), r.get("state_or_origin")) for r in krpc]
    if 0 not in seqs or 1 not in seqs or decisions[:2] != [(0, "accepted"), (1, "repeat_terminal")]:
        return "fail", "drop_first_ack_failed_idempotent_retry_ack"
    acks = [r for r in ts["cli_rows"] if r.get("row_kind") == "ack_recv" and r.get("ack_req_take_id") == ts["take_id"]]
    if len(acks) != 1:
        return "fail", "drop_first_ack_failed_idempotent_retry_ack"
    ack = acks[0]
    epoch = int(ack.get("ack_req_epoch_n", 0))
    if (
        epoch <= 0
        or int(ack.get("ack_cur_epoch_n", 0)) != epoch
        or ack.get("ack_resp_class") != "repeat_terminal"
        or ack.get("ack_req_state") != "parada"
        or ack.get("ack_req_origin") != "juego"
        or ack.get("ack_cur_take_id") != ts["take_id"]
        or ack.get("ack_cur_state") != "parada"
        or ack.get("ack_cur_origin") != "juego"
        or float(ack.get("cli_tick_ms", 0.0)) < float(sent[-1].get("cli_tick_ms", 0.0))
    ):
        return "fail", "drop_first_ack_failed_idempotent_retry_ack"
    # El NOTIFY no cerro el pendiente: bit `pending_stop_b` de los frames crudos hasta el acuse del reintento, y ya no despues.
    frames = [r for r in ts["cli_rows"] if r.get("row_kind") == "frame_sample"]
    ack_tick = float(ack.get("cli_tick_ms", 0.0))
    if not any(_frame_bits(r)[2] for r in frames if float(r["cli_tick_ms"]) < ack_tick):
        return "fail", "drop_first_ack_pending_not_open_before_retry_ack"
    if any(_frame_bits(r)[2] for r in frames if float(r["cli_tick_ms"]) > ack_tick):
        return "fail", "drop_first_ack_pending_not_closed_by_retry_ack"
    return None


def _tom07_late_ack_and_cache(bundle, ops, ack2_key, new_key):
    ts_new = _get_take_slice(new_key, bundle, ops)
    ts_ack2 = _get_take_slice(ack2_key, bundle, ops)
    if ts_ack2["arm_job"] is None or ts_ack2["arm_job"]["stop_inject"] != "hold_all_ack":
        return "fail", "ack2_not_armed_with_hold_all_ack"
    if int(ts_ack2["arm_job"]["args_n"].get("post_stop_watch_ms", -1)) != 0:
        return "fail", "ack2_post_stop_watch_not_0"
    if ts_new["arm_job"] is None:
        return "fail", "new_take_not_armed_without_busy"
    rel = [
        op for op in ops
        if op["verb"] == "take_scene_prep" and op["args_s"].get("op") == "release_held_ack"
        and op["args_s"].get("take_id") == ack2_key[1] and op["status"] == "ok"
    ]
    if not rel:
        return "fail", "missing_release_held_ack_order"
    acks = [r for r in ts_new["cli_rows"] if r.get("row_kind") == "ack_recv" and r.get("ack_req_take_id") == ack2_key[1]]
    if not acks:
        return "fail", "missing_late_ack_of_ack2_while_new_running"
    ack = acks[0]
    state_recvs = sorted(
        [
            r for r in ts_new["cli_rows"]
            if r.get("row_kind") == "take_state_recv" and r.get("ack_cur_take_id") == new_key[1]
            and r.get("ack_cur_state") == "rodando"
        ],
        key=lambda r: int(r.get("cli_frame", 0)),
    )
    if not state_recvs:
        return "fail", "new_take_without_take_state_recv"
    epoch = int(state_recvs[0].get("ack_cur_epoch_n", 0))
    last_seq = int(state_recvs[-1].get("aux_n", 0))
    if (
        epoch <= 0
        or int(ack.get("ack_req_epoch_n", 0)) != epoch
        or int(ack.get("ack_cur_epoch_n", 0)) != epoch
        or ack.get("ack_req_state") != "parada"
        or ack.get("ack_req_origin") != "juego"
        or ack.get("ack_resp_class") not in ("first_terminal", "repeat_terminal")
        or ack.get("ack_cur_take_id") != new_key[1]
        or ack.get("ack_cur_state") != "rodando"
        or int(ack.get("aux_n", 0)) != last_seq
    ):
        return "fail", "ack2_late_ack_pair_or_current_snapshot_invalid"
    status_after = _status_ops(ops, "take_cam_prep", cli_cached_take_id=new_key[1])
    if not status_after:
        return "fail", "t6_old_ack_overwrote_newer_client_cache"
    st = status_after[-1]
    if (
        st["read_s"].get("cli_cached_state") != "rodando"
        or int(st["read_n"].get("cli_cached_epoch", 0)) != epoch
        or int(st["read_n"].get("cli_state_seq", -1)) != last_seq
    ):
        return "fail", "t6_old_ack_overwrote_newer_client_cache"
    return None


def _tom07_stale_notify(bundle, ops, key_a, key_b):
    ts_b = _get_take_slice(key_b, bundle, ops)
    stale_ops = [
        op for op in ops
        if op["verb"] == "take_cam_prep" and op["args_s"].get("op") == "deliver_stale_msg" and op["status"] == "ok"
    ]
    if not stale_ops or int(stale_ops[-1]["read_n"].get("stale_msg_ignored_n", 0)) < 4:
        return "fail", "stale_notify_not_delivered_or_not_ignored"
    if int(stale_ops[-1]["read_n"].get("sandbox_cam_active_b", 0)) != 1:
        return "fail", "stale_notify_released_active_camera_of_take_b"
    if any(r.get("row_kind") == "cli_safety_exit" for r in ts_b["cli_rows"]):
        return "fail", "stale_notify_triggered_safety_exit_on_take_b"
    state_recvs = sorted(
        [
            r for r in ts_b["cli_rows"]
            if r.get("row_kind") == "take_state_recv" and r.get("ack_cur_take_id") == key_b[1]
            and r.get("ack_cur_state") == "rodando"
        ],
        key=lambda r: int(r.get("cli_frame", 0)),
    )
    if not state_recvs:
        return "fail", "stale_take_b_without_take_state_recv"
    st = _status_ops(ops, "take_cam_prep", t_min=stale_ops[-1].get("t_result"), cli_cached_take_id=key_b[1])
    if not st:
        return "fail", "stale_notify_overwrote_cache_of_take_b"
    s = st[0]
    if (
        s["read_s"].get("cli_cached_state") != "rodando"
        or int(s["read_n"].get("cli_state_seq", -1)) != int(state_recvs[-1].get("aux_n", -2))
        or int(s["read_n"].get("sandbox_cam_active_b", 1)) != 1
    ):
        return "fail", "stale_notify_overwrote_cache_or_state_of_take_b"
    return None


def _tom07_epoch_cases(bundle, ops, k1, k2, label, restarted_by_process):
    t1 = _get_take_slice(k1, bundle, ops)
    t2 = _get_take_slice(k2, bundle, ops)
    if k1[1] != k2[1] or k1[0] == k2[0]:
        return "missing", f"{label}_same_full_take_id_in_new_epoch_not_observed"
    if t1["arm_job"] is None or t2["arm_job"] is None:
        return "missing", f"{label}_missing_arm_job_in_one_epoch"
    if not _sent_rows(t1):
        return "missing", f"{label}_no_retry_in_flight_in_old_epoch"
    # La toma nueva (mismo take_id completo, epoch nuevo) queda intacta: ni terminal, ni acuse viejo, ni reintento viejo.
    t_state, _row = _take_terminal(t2, bundle)
    if t_state != "missing":
        return "fail", f"{label}_new_epoch_take_stopped_by_old_retry"
    if any(r.get("row_kind") in ("ack_recv", "rpc_stop_sent") for r in t2["cli_rows"]):
        return "fail", f"{label}_new_epoch_take_contaminated_by_old_retry"
    if any(r["_gen"] == k2[0] and r.get("row_kind") == "key_rpc" and r.get("subject_id") == k2[1] and r.get("state_or_origin") == "accepted"
           for r in bundle["srv_obs_rows"]):
        return "fail", f"{label}_new_epoch_take_contaminated_by_old_retry"
    snaps = [op for op in _status_ops(ops, "take_scene_prep", active_take_id=k2[1]) if op["gen"] == k2[0]]
    if not snaps:
        return "missing", f"{label}_no_server_status_of_new_epoch_take"
    s = snaps[-1]
    if s["read_s"].get("take_state") not in ("armada", "rodando") or int(s["read_n"].get("transitions_n", 0)) != 0:
        return "fail", f"{label}_new_epoch_take_not_intact_in_server_status"
    return None


def _client_lease_exceeded_in_restart(bundle, hellos_srv_new_t, lease_ms):
    polls = bundle["timeline"]["polls"]["client"]
    last_srv = [p[0] for p in bundle["timeline"]["polls"]["server"] if p[0] < hellos_srv_new_t]
    window_lo = last_srv[-1] if last_srv else hellos_srv_new_t
    ts = [p[0] for p in polls]
    for a, b in zip(ts, ts[1:]):
        if b - a > lease_ms and a < hellos_srv_new_t and b > window_lo:
            return True
    return False


def _tom07_cut_cases(bundle, ops, ctx, c3):
    lease_ms = ctx["lease_ms"]
    pairs = _pair_cuts(bundle)
    run_meta = bundle["run_meta"]
    eps_look_deg = float(run_meta.get("eps_look_deg", 0.5))
    calib_sign = 1.0 if float(run_meta.get("calib_sign", 1.0)) >= 0.0 else -1.0
    for case in ("cut_nokey", "cut_before", "cut_after"):
        key = c3[case]
        ts = _get_take_slice(key, bundle, ops)
        t_state, term = _take_terminal(ts, bundle)
        if t_state == "duplicate":
            return "fail", f"{case}_duplicate_take_terminal"
        mine = [p for p in pairs if p[0].get("_key") == key]
        if len(mine) < 2 or {p[0].get("peer") for p in mine} != {"server", "client"}:
            return "missing", f"{case}_missing_cut_windows_for_both_peers"
        for cw, bc in mine:
            st_l, why_l = _verify_lease_discipline(cw, bc, ts, lease_ms)
            if st_l != "pass":
                return st_l, f"{case}_{why_l}" if not why_l.startswith("client_") and not why_l.startswith("server_") else why_l
        srv_bc = next(bc for cw, bc in mine if cw.get("peer") == "server")
        cli_bc = next(bc for cw, bc in mine if cw.get("peer") == "client")
        key_stims = [s for s in ts["stimuli"] if s.get("stim_type") in ("key_press", "key_hold")]
        if case == "cut_nokey":
            if t_state != "ok" or term.get("state_or_origin") != "parada:hombre_muerto":
                return "fail", "cut_nokey_did_not_transition_to_hombre_muerto"
            if float(term.get("v4", 0.0)) <= lease_ms:
                return "fail", "cut_nokey_lease_age_not_gt_lease_ms"
            if key_stims:
                return "fail", "cut_nokey_has_a_key_press"
        elif case == "cut_before":
            if not key_stims:
                return "missing", "cut_before_missing_key_stimulus"
            dt = float(key_stims[0]["h_ms"]) - float(cli_bc["last_ok_t"])
            if not (1350.0 <= dt <= 1650.0):
                return "missing", "cut_before_key_not_at_1500ms_from_last_poll"
            if (
                t_state != "ok"
                or term.get("state_or_origin") != "parada:juego"
                or int(term.get("v6", 0)) != 1
                or int(term.get("v7", 0)) != 1
            ):
                return "fail", "t8_cut_before_did_not_stop_with_juego_and_single_transition"
            if not any(r.get("row_kind") == "key_rpc" and r.get("state_or_origin") == "accepted" for r in _key_rpc_rows(bundle, key)):
                return "fail", "t8_cut_before_server_did_not_accept_the_key_rpc"
        else:
            if (
                t_state != "ok"
                or term.get("state_or_origin") != "parada:hombre_muerto"
                or int(term.get("v6", 0)) != 1
                or int(term.get("v7", 0)) != 1
                or int(term.get("v9", 1)) != 0
                or int(term.get("v10", 1)) != 0
                or int(term.get("v11", 1)) != 0
            ):
                return "fail", "t8_cut_after_invalid_terminal_or_new_effects"
            if float(term.get("v4", 0.0)) <= lease_ms:
                return "fail", "cut_after_lease_age_not_gt_lease_ms"
            if not key_stims:
                return "missing", "cut_after_missing_late_key_stimulus"
            dt = float(key_stims[0]["h_ms"]) - float(cli_bc["last_ok_t"])
            if not (3250.0 <= dt <= 3550.0):
                return "missing", "cut_after_late_key_not_at_3400ms_from_last_poll"
            late_acc = [
                r for r in _key_rpc_rows(bundle, key)
                if r.get("state_or_origin") == "accepted"
            ]
            if late_acc or int(term.get("v6", 0)) != 1:
                return "fail", "cut_after_late_key_had_effects_in_server"
        if case != "cut_before":
            frames = [r for r in ts["cli_rows"] if r.get("row_kind") == "frame_sample"]
            exits = [r for r in ts["cli_rows"] if r.get("row_kind") == "cli_safety_exit"]
            if not exits:
                return "fail", f"{case}_missing_client_safety_exit"
            ref = float(ts["meta"].get("contemp_yaw_ref_deg", 0.0))
            if not _verify_look_response_after_local_exit(ts["cli_rows"], ts["stimuli"], ref, eps_look_deg, calib_sign, int(exits[0].get("aux_n", 0))):
                return "fail", f"{case}_missing_look_response_after_lease"
            if not frames:
                return "missing", f"{case}_no_client_frames"
            # El cliente se pone al dia tras reconectar leyendo el estado crudo (D4).
            rec_t = float(srv_bc["reconnect_t"])
            st_srv = _status_ops(ops, "take_scene_prep", t_min=rec_t, active_take_id=key[1])
            if not st_srv:
                return "missing", f"{case}_no_status_after_reconnect"
            s = st_srv[0]
            if (
                s["read_s"].get("take_state") != "parada"
                or s["read_s"].get("take_origin") != "hombre_muerto"
                or int(s["read_n"].get("term_frame", -1)) != int(term.get("v1", -2))
                or abs(float(s["read_n"].get("term_lease_age_ms", -1.0)) - float(term.get("v4", -2.0))) > 1e-6
            ):
                return "fail", f"{case}_status_after_reconnect_differs_from_raw_terminal"
            cache = _status_ops(ops, "take_cam_prep", t_min=rec_t, cli_cached_take_id=key[1])
            if not cache or cache[0]["read_s"].get("cli_cached_state") != "parada":
                return "missing", f"{case}_client_cache_not_updated_after_reconnect"
    return None


EXP_PROBE_PREFIXES = (
    "DayZSandbox_dev/qa/probe/DayZSandbox_QA_Expansion",
    "qa/probe/DayZSandbox_QA_Expansion",
)


INPUTS_XML_PREFIXES = (
    "DayZSandbox_dev/qa/probe",
    "qa/probe",
)