"""Tests offline del oráculo de S-toma (brief S-toma §5, §6, §9 y T1-T13 / E1-E9)."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

QA_DIR = Path(__file__).resolve().parents[1]
if str(QA_DIR) not in sys.path:
    sys.path.insert(0, str(QA_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import f03_common
import gate_core
import m1_gate
import s_toma_eval
import s_toma_mutants
import wire
from tests import test_probe_static

SRV_NCOL = [
    "srv_frame",
    "srv_tick_ms",
    "dtsum_ms",
    "take_dtsum_ms",
    "v1",
    "v2",
    "v3",
    "v4",
    "v5",
    "v6",
    "v7",
    "v8",
    "v9",
    "v10",
    "v11",
]
SRV_SCOL = ["row_kind", "subject_id", "state_or_origin"]

CLI_NCOL = [
    "cli_frame",
    "cli_tick_ms",
    "dtsum_ms",
    "take_dtsum_ms",
    "sandbox_cam_active_b",
    "hud_hidden_b",
    "quickbar_hide_flag_b",
    "quickbar_widget_visible_b",
    "cam_x_m",
    "cam_y_m",
    "cam_z_m",
    "cam_yaw_deg",
    "cam_pitch_deg",
    "cam_fov_deg",
    "ack_req_epoch_n",
    "ack_cur_epoch_n",
    "aux_n",
]
CLI_SCOL = [
    "row_kind",
    "detail",
    "ack_req_take_id",
    "ack_req_state",
    "ack_req_origin",
    "ack_resp_class",
    "ack_cur_take_id",
    "ack_cur_state",
    "ack_cur_origin",
]

ACT_OBS_NCOL = ["x_m", "y_m", "z_m", "net_id_low", "net_id_high", "alive_b"]
ACT_OBS_SCOL = ["actor_id", "real_class", "slot_name", "item_class"]

ADAPTER_VER = "dsbx-qa-exp1+0123456789abcdef"


def _make_srv_row(
    srv_frame,
    srv_tick_ms,
    dtsum_ms,
    take_dtsum_ms,
    row_kind,
    subject_id="",
    state_or_origin="",
    v1=0.0,
    v2=0.0,
    v3=0.0,
    v4=0.0,
    v5=0.0,
    v6=0.0,
    v7=0.0,
    v8=0.0,
    v9=0.0,
    v10=0.0,
    v11=0.0,
):
    return {
        "srv_frame": int(srv_frame),
        "srv_tick_ms": float(srv_tick_ms),
        "dtsum_ms": float(dtsum_ms),
        "take_dtsum_ms": float(take_dtsum_ms),
        "v1": float(v1),
        "v2": float(v2),
        "v3": float(v3),
        "v4": float(v4),
        "v5": float(v5),
        "v6": float(v6),
        "v7": float(v7),
        "v8": float(v8),
        "v9": float(v9),
        "v10": float(v10),
        "v11": float(v11),
        "row_kind": str(row_kind),
        "subject_id": str(subject_id),
        "state_or_origin": str(state_or_origin),
    }


def _make_cli_row(
    cli_frame,
    cli_tick_ms,
    dtsum_ms,
    take_dtsum_ms,
    row_kind,
    detail="",
    sandbox_cam_active_b=0,
    hud_hidden_b=0,
    quickbar_hide_flag_b=0,
    quickbar_widget_visible_b=1,
    cam_x_m=7500.0,
    cam_y_m=17.4,
    cam_z_m=7500.0,
    cam_yaw_deg=0.0,
    cam_pitch_deg=-6.0,
    cam_fov_deg=0.75,
    ack_req_epoch_n=1,
    ack_cur_epoch_n=1,
    aux_n=0,
    ack_req_take_id="",
    ack_req_state="",
    ack_req_origin="",
    ack_resp_class="",
    ack_cur_take_id="",
    ack_cur_state="",
    ack_cur_origin="",
):
    return {
        "cli_frame": int(cli_frame),
        "cli_tick_ms": float(cli_tick_ms),
        "dtsum_ms": float(dtsum_ms),
        "take_dtsum_ms": float(take_dtsum_ms),
        "sandbox_cam_active_b": int(sandbox_cam_active_b),
        "hud_hidden_b": int(hud_hidden_b),
        "quickbar_hide_flag_b": int(quickbar_hide_flag_b),
        "quickbar_widget_visible_b": int(quickbar_widget_visible_b),
        "cam_x_m": round(float(cam_x_m), 4),
        "cam_y_m": round(float(cam_y_m), 4),
        "cam_z_m": round(float(cam_z_m), 4),
        "cam_yaw_deg": round(float(cam_yaw_deg), 4),
        "cam_pitch_deg": round(float(cam_pitch_deg), 4),
        "cam_fov_deg": round(float(cam_fov_deg), 4),
        "ack_req_epoch_n": int(ack_req_epoch_n),
        "ack_cur_epoch_n": int(ack_cur_epoch_n),
        "aux_n": int(aux_n),
        "row_kind": str(row_kind),
        "detail": str(detail),
        "ack_req_take_id": str(ack_req_take_id),
        "ack_req_state": str(ack_req_state),
        "ack_req_origin": str(ack_req_origin),
        "ack_resp_class": str(ack_resp_class),
        "ack_cur_take_id": str(ack_cur_take_id),
        "ack_cur_state": str(ack_cur_state),
        "ack_cur_origin": str(ack_cur_origin),
    }


class _SyntheticTraceBuilder:
    """Construye una carpeta de parte sintética completa y válida para S-toma."""

    def __init__(self, fixture: dict, git_head: str, probe_stamp: str, op_nonce: str = "a1b2c3d4e5f60718"):
        self.fixture = fixture
        self.git_head = git_head
        self.probe_stamp = probe_stamp
        self.probe_ver = f"dsbx-qa1+{probe_stamp}"
        self.op_nonce = op_nonce
        self._op_seq = 0
        self.bridge_rows: list[dict] = []
        self.scenario_rows: list[dict] = []
        self.op_map: list[dict] = []
        self.srv_inst = "srv-inst-1"
        self.cli_inst = "cli-inst-1"
        self.t_ms = 100.0

    def next_op_id(self) -> str:
        self._op_seq += 1
        return f"{self.op_nonce}-{self._op_seq}"

    def emit_hello(self, peer: str, inst: str, build: str = "offline", probe_ver: str | None = None):
        pv = self.probe_ver if probe_ver is None else probe_ver
        if peer == "server":
            self.srv_inst = inst
        else:
            self.cli_inst = inst
        self.t_ms += 5.0
        self.bridge_rows.append(
            {
                "args": {
                    "build": build,
                    "inst": inst,
                    "peer": peer,
                    "probe_ver": pv,
                    "proto": "qa0",
                },
                "ev": "hello",
                "http": 200,
                "inst": inst,
                "ok": True,
                "peer": peer,
                "t_ms": round(self.t_ms, 3),
            }
        )

    def emit_op(
        self,
        peer: str,
        verb: str,
        args_str: dict | None = None,
        args_num: dict | None = None,
        read_str: dict | None = None,
        read_num: dict | None = None,
        ncol: list[str] | None = None,
        scol: list[str] | None = None,
        rows: list[dict] | None = None,
        status: str = "done",
        reason: str = "",
        qa_fault: str | None = None,
        frame: int = 100,
        tick_s: float = 1.0,
    ) -> str:
        op_id = self.next_op_id()
        inst = self.srv_inst if peer == "server" else self.cli_inst

        packed_args_clean = wire.pack_payload(scalars_str=args_str, scalars_num=args_num)
        astr_wire = dict(args_str or {})
        astr_wire["qa_fault"] = wire.format_qa_fault(qa_fault)
        packed_args_wire = wire.pack_payload(scalars_str=astr_wire, scalars_num=args_num)

        self.t_ms += 2.0
        issued_ms = round(self.t_ms, 3)
        wire_order = {
            "args": packed_args_wire,
            "inst": inst,
            "issued_ms": issued_ms,
            "op_id": op_id,
            "ttl_ms": 5000,
            "verb": verb,
        }
        poll_bytes = wire.poll_wire_bytes(wire_order, now_ms=issued_ms + 1.0)

        packed_read = wire.pack_payload(
            scalars_str=read_str,
            scalars_num=read_num,
            num_cols=ncol,
            str_cols=scol,
            row_dicts=rows,
        )
        read_with_has = dict(packed_read)
        read_with_has["has"] = ["payload"]

        res_body = {
            "done_ms": round(tick_s * 1000.0 + 1.0, 3),
            "dup": False,
            "frame_done": int(frame + 1),
            "frame_recv": int(frame),
            "op_id": op_id,
            "read": read_with_has,
            "reason": reason,
            "recv_ms": round(tick_s * 1000.0, 3),
            "status": status,
        }
        res_bytes = wire.result_wire_bytes(res_body)

        self.bridge_rows.append(
            {
                "args": packed_args_clean,
                "ev": "enq",
                "inst": inst,
                "op_id": op_id,
                "peer": peer,
                "t_ms": issued_ms,
                "verb": verb,
            }
        )
        self.t_ms += 1.0
        self.bridge_rows.append(
            {
                "body_len": len(poll_bytes),
                "ev": "poll",
                "frame": int(frame),
                "held_ms": 1.0,
                "http": 200,
                "inst": inst,
                "n_ops": 1,
                "now_ms": round(self.t_ms, 3),
                "op_ids": [op_id],
                "peer": peer,
                "t_ms": round(self.t_ms, 3),
                "tick_s": round(float(tick_s), 4),
            }
        )
        self.bridge_rows.append(
            {
                "args": packed_args_clean,
                "ev": "deliver",
                "inst": inst,
                "op_id": op_id,
                "peer": peer,
                "t_ms": round(self.t_ms, 3),
                "verb": verb,
            }
        )
        self.t_ms += 1.0
        self.bridge_rows.append(
            {
                "body_len": len(res_bytes),
                "ev": "result",
                "http": 200,
                "op_id": op_id,
                "peer": peer,
                "result": res_body,
                "t_ms": round(self.t_ms, 3),
            }
        )
        self.op_map.append(
            {
                "n": len(self.op_map) + 1,
                "op_id": op_id,
                "peer": peer,
                "verb": verb,
            }
        )
        return op_id

    def emit_job_with_pages(
        self,
        peer: str,
        verb: str,
        take_id: str,
        ncol: list[str],
        scol: list[str],
        all_rows: list[dict],
        *,
        mode: str = "rpc",
        state: str = "done",
        reason: str = "",
        end_tick_ms: float = 5000.0,
        onjobend_tick_ms: float = 5005.0,
        released_tick_ms: float = 5008.0,
        page_size: int = 4,
    ) -> str:
        job_id = f"job-{verb}-{take_id}-{self._op_seq + 1}"
        self.emit_op(
            peer,
            verb,
            args_str={"mode": mode, "take_id": take_id},
            read_str={"job": job_id, "state": "running"},
            read_num={"page_size": page_size},
        )
        pages = [all_rows[i : i + page_size] for i in range(0, len(all_rows), page_size)] or [[]]
        pages_n = len(pages)
        rows_total_n = len(all_rows)
        for p_idx, page_rows in enumerate(pages):
            self.emit_op(
                peer,
                "job_read",
                args_str={"job": job_id},
                args_num={"page_n": p_idx},
                read_str={"job": job_id, "reason": reason, "state": state},
                read_num={
                    "end_tick_ms": end_tick_ms,
                    "onjobend_tick_ms": onjobend_tick_ms,
                    "page_n": p_idx,
                    "pages_n": pages_n,
                    "released_tick_ms": released_tick_ms,
                    "rows_total_n": rows_total_n,
                },
                ncol=ncol,
                scol=scol,
                rows=page_rows,
            )
        return job_id

    def emit_clock_calibration(self, stage: str, rep: int, base_h_ms: float, epoch: int = 1, width_ms: float = 2.0):
        for peer, inst in (("server", self.srv_inst), ("client", self.cli_inst)):
            for phase_idx, phase in enumerate(("pre", "post")):
                p_tick = base_h_ms + phase_idx * 5000.0
                self.scenario_rows.append(
                    {
                        "epoch": epoch,
                        "h_recv_ms": p_tick + width_ms,
                        "h_send_ms": p_tick,
                        "inst": inst,
                        "kind": "clock_pair",
                        "peer": peer,
                        "peer_frame": int(100 + phase_idx * 300),
                        "peer_tick_ms": p_tick,
                        "phase": phase,
                        "rep": rep,
                        "stage": stage,
                    }
                )


def _build_positive_take_rows(
    fixture: dict,
    take_id: str,
    stage: str,
    rep: int,
    base_tick_ms: float,
    *,
    mode: str = "rpc",
    origin: str = "web",
    allow_dmg_pre_b: int = 1,
    go_delay_ms: float = 0.0,
    actor2_lag_ms: float = 0.0,
    cam_drift_m: float = 0.0,
    director_mortal: bool = False,
    cues_keep_firing: bool = False,
    no_control_restore: bool = False,
    hold_ms: float = 0.0,
    epoch: int = 1,
):
    keyframes = fixture["camera_path"]["keyframes"]
    mark1 = fixture["actors"][0]["mark_pos_m"]
    mark2 = fixture["actors"][1]["mark_pos_m"]
    target1 = fixture["actors"][0]["dest_pos_m"]

    go_send_frame = 200 + rep * 100
    go_send_tick = base_tick_ms + 100.0
    if mode == "common_time":
        sched_srv_tick = base_tick_ms + 1000.0
        sched_cli_tick = base_tick_ms + 1000.0
        disp_frame = go_send_frame + 50
        disp_tick = sched_srv_tick + 5.0
    else:
        sched_srv_tick = 0.0
        sched_cli_tick = 0.0
        disp_frame = go_send_frame
        disp_tick = go_send_tick

    stop_srv_frame = disp_frame + 60
    stop_srv_tick = disp_tick + 3020.0
    allow_dmg_during = 1 if director_mortal else 0
    allow_dmg_post = allow_dmg_pre_b

    arm_rows = [
        _make_srv_row(
            go_send_frame - 2,
            go_send_tick - 32.0,
            16.0,
            0.0,
            "arm_ready",
            take_id,
            "armada",
            v1=allow_dmg_pre_b,
            v2=1.0,
            v3=2,
            v4=1,
            v5=sched_srv_tick,
            v6=sched_cli_tick,
            v7=0,
        ),
        _make_srv_row(
            go_send_frame,
            go_send_tick,
            32.0,
            0.0,
            "go_sent",
            take_id,
            "rodando",
            v1=go_send_frame,
            v2=go_send_tick,
            v3=2,
            v4=1,
            v5=sched_srv_tick,
            v6=sched_cli_tick,
            v7=0,
        ),
        _make_srv_row(
            disp_frame,
            disp_tick,
            48.0,
            0.0,
            "dispatch",
            "actor_1",
            mode,
            v1=disp_frame,
            v2=disp_tick,
        ),
        _make_srv_row(
            disp_frame,
            disp_tick,
            48.0,
            0.0,
            "dispatch",
            "actor_2",
            mode,
            v1=disp_frame,
            v2=disp_tick,
        ),
        _make_srv_row(
            stop_srv_frame,
            stop_srv_tick,
            3068.0,
            3020.0,
            "stop_obs",
            take_id,
            f"parada:{origin}",
            v1=stop_srv_frame,
            v2=allow_dmg_during,
            v3=allow_dmg_post,
            v4=1 if cues_keep_firing else 0,
            v5=1 if cues_keep_firing else 0,
            v6=0.75 if director_mortal else 1.0,
            v7=1,
            v8=1,
            v9=1,
            v10=1 if cues_keep_firing else 0,
            v11=1 if origin == "juego" else 0,
        ),
        _make_srv_row(
            stop_srv_frame + 40,
            stop_srv_tick + 1850.0,
            4918.0,
            4870.0,
            "post_stop_end",
            take_id,
            f"parada:{origin}",
            v1=stop_srv_frame,
            v2=allow_dmg_pre_b,
            v3=allow_dmg_post,
            v4=1 if cues_keep_firing else 0,
            v5=1 if cues_keep_firing else 0,
            v6=0.75 if director_mortal else 1.0,
            v7=1,
            v8=1,
            v9=1,
            v10=1 if cues_keep_firing else 0,
            v11=1 if origin == "juego" else 0,
        ),
    ]

    srv_rows = [
        _make_srv_row(
            disp_frame - 1,
            disp_tick - 4.0,
            32.0,
            0.0,
            "act_sample",
            "actor_1",
            "pre_go",
            v1=mark1[0],
            v2=mark1[1],
            v3=mark1[2],
            v4=0.0,
        ),
        _make_srv_row(
            disp_frame + 1,
            disp_tick + 4.0,
            64.0,
            4.0,
            "act_sample",
            "actor_1",
            "rodando",
            v1=mark1[0] + 0.25,
            v2=mark1[1],
            v3=mark1[2],
            v4=1.5,
        ),
        _make_srv_row(
            disp_frame + 30,
            disp_tick + 1500.0,
            1548.0,
            1500.0,
            "act_sample",
            "actor_1",
            "rodando",
            v1=target1[0] - 1.0,
            v2=target1[1],
            v3=target1[2],
            v4=1.5,
        ),
        _make_srv_row(
            stop_srv_frame + 1,
            stop_srv_tick + 16.0,
            3084.0,
            3036.0,
            "act_sample",
            "actor_1",
            f"parada:{origin}",
            v1=mark1[0] + 3.0,
            v2=mark1[1],
            v3=mark1[2],
            v4=0.0,
        ),
        _make_srv_row(
            stop_srv_frame + 2,
            stop_srv_tick + 32.0,
            3100.0,
            3052.0,
            "act_sample",
            "actor_1",
            f"parada:{origin}",
            v1=mark1[0] + 3.0,
            v2=mark1[1],
            v3=mark1[2],
            v4=0.0,
        ),
        _make_srv_row(
            disp_frame - 1,
            disp_tick - 4.0,
            32.0,
            0.0,
            "act_sample",
            "actor_2",
            "pre_go",
            v1=mark2[0],
            v2=mark2[1],
            v3=mark2[2],
            v5=0,
            v6=0,
            v7=0,
            v8=10,
            v9=0,
            v10=2,
            v11=0,
        ),
    ]
    if actor2_lag_ms > 0.0:
        srv_rows.append(
            _make_srv_row(
                disp_frame + 1,
                disp_tick + actor2_lag_ms - 4.0,
                32.0 + actor2_lag_ms,
                actor2_lag_ms - 4.0,
                "act_sample",
                "actor_2",
                "rodando",
                v1=mark2[0],
                v2=mark2[1],
                v3=mark2[2],
                v5=0,
                v6=0,
                v7=0,
                v8=10,
                v9=1,
                v10=2,
                v11=0,
            )
        )
    srv_rows.append(
        _make_srv_row(
            disp_frame + (2 if actor2_lag_ms > 0.0 else 1),
            disp_tick + 4.0 + actor2_lag_ms,
            64.0 + actor2_lag_ms,
            4.0 + actor2_lag_ms,
            "act_sample",
            "actor_2",
            "rodando",
            v1=mark2[0],
            v2=mark2[1],
            v3=mark2[2],
            v5=1,
            v6=1051,
            v7=13,
            v8=11,
            v9=1,
            v10=1,
            v11=0,
        )
    )

    for step_idx in range(38):
        f_no = stop_srv_frame + step_idx
        t_step = stop_srv_tick + step_idx * 50.0
        td_step = 3020.0 + step_idx * 50.0
        srv_rows.append(
            _make_srv_row(
                f_no,
                t_step,
                td_step + 48.0,
                td_step,
                "act_sample",
                "actor_2",
                f"parada:{origin}",
                v1=mark2[0],
                v2=mark2[1],
                v3=mark2[2],
                v5=1,
                v6=1050 if (cues_keep_firing and td_step >= 4500.0) else 1051,
                v7=44 if (cues_keep_firing and td_step >= 4500.0) else 13,
                v8=11,
                v9=1 if cues_keep_firing else 0,
                v10=1 if cues_keep_firing else 0,
                v11=1 if (cues_keep_firing and td_step >= 4500.0) else 0,
            )
        )

    srv_rows.extend(
        [
            _make_srv_row(
                disp_frame + 10,
                disp_tick + 500.0,
                548.0,
                500.0,
                "director_sample",
                "director",
                "rodando",
                v1=0.80 if director_mortal else 1.0,
                v2=1,
                v3=allow_dmg_during,
                v4=0,
            ),
            _make_srv_row(
                disp_frame + 20,
                disp_tick + 1000.0,
                1048.0,
                1000.0,
                "melee_hit",
                "infected_1",
                "MeleeZombie",
                v1=1,
                v2=1,
                v3=1,
                v4=1.1,
                v5=1.8,
                v6=allow_dmg_during,
                v7=0.75 if director_mortal else 1.0,
                v8=1,
                v9=0,
                v10=1,
                v11=0,
            ),
            _make_srv_row(
                stop_srv_frame + 1,
                stop_srv_tick + 16.0,
                3084.0,
                3036.0,
                "director_sample",
                "director",
                f"parada:{origin}",
                v1=0.75 if director_mortal else 1.0,
                v2=1,
                v3=allow_dmg_post,
                v4=0,
            ),
            _make_srv_row(
                stop_srv_frame,
                stop_srv_tick,
                3068.0,
                3020.0,
                "take_terminal",
                take_id,
                f"parada:{origin}",
                v1=stop_srv_frame,
                v2=stop_srv_tick,
                v3=3020.0,
                v4=120.0,
                v5=stop_srv_frame,
                v6=1,
                v7=1,
                v8=allow_dmg_post,
                v9=1 if cues_keep_firing else 0,
                v10=1 if cues_keep_firing else 0,
                v11=1 if cues_keep_firing else 0,
            ),
            _make_srv_row(
                stop_srv_frame + 1,
                stop_srv_tick + 16.0,
                3084.0,
                3036.0,
                "cleanup_done",
                take_id,
                f"parada:{origin}",
                v1=stop_srv_frame + 1,
                v2=stop_srv_tick + 16.0,
                v3=allow_dmg_post,
                v4=1,
            ),
        ]
    )

    cli_base_frame = 500 + rep * 150
    go_recv_tick = go_send_tick + 5.0
    go_deliv_tick = disp_tick if mode == "common_time" else (go_recv_tick + go_delay_ms)

    cli_rows = [
        _make_cli_row(
            cli_base_frame - 2,
            go_recv_tick - 20.0,
            10.0,
            -20.0,
            "frame_sample",
            "pre_go",
            sandbox_cam_active_b=0,
            hud_hidden_b=0,
            quickbar_hide_flag_b=0,
            quickbar_widget_visible_b=1,
            cam_yaw_deg=10.0,
        ),
        _make_cli_row(
            cli_base_frame - 1,
            go_recv_tick,
            30.0,
            0.0,
            "go_recv",
            "rpc_go",
            aux_n=disp_frame,
        ),
        _make_cli_row(
            cli_base_frame,
            go_deliv_tick - 4.0,
            38.0,
            0.0,
            "frame_sample",
            "pre_cam",
            sandbox_cam_active_b=0,
            hud_hidden_b=0,
            quickbar_hide_flag_b=0,
            quickbar_widget_visible_b=1,
            cam_yaw_deg=10.0,
        ),
        _make_cli_row(
            cli_base_frame,
            go_deliv_tick,
            46.0,
            0.0,
            "go_deliver",
            "delivered",
            aux_n=disp_frame,
        ),
    ]

    # 35 muestras continuas de cámara activa en [0, 3000] ms con dt ligeramente variable (anti-E9)
    t_cur = 0.0
    for s_idx in range(35):
        f_cur = cli_base_frame + 1 + s_idx
        pos_c, yaw_c, pitch_c, fov_c = s_toma_eval.eval_catmull_rom_path(keyframes, t_cur)
        drift_x = cam_drift_m if (cam_drift_m and t_cur >= 1000.0) else 0.0
        cli_rows.append(
            _make_cli_row(
                f_cur,
                go_deliv_tick + 4.0 + t_cur,
                54.0 + t_cur,
                t_cur,
                "frame_sample",
                "active",
                sandbox_cam_active_b=1,
                hud_hidden_b=1,
                quickbar_hide_flag_b=1,
                quickbar_widget_visible_b=0,
                cam_x_m=pos_c[0] + drift_x,
                cam_y_m=pos_c[1],
                cam_z_m=pos_c[2],
                cam_yaw_deg=yaw_c,
                cam_pitch_deg=pitch_c,
                cam_fov_deg=fov_c,
            )
        )
        step_dt = 88.0 if (s_idx % 2 == 0) else 89.5
        t_cur = min(3000.0, t_cur + step_dt)

    stim_h_ms = disp_tick + 3000.0
    if origin == "juego":
        cli_rows.extend(
            [
                _make_cli_row(
                    cli_base_frame + 36,
                    stim_h_ms + 5.0,
                    3060.0,
                    3005.0,
                    "key_edge",
                    "press_accepted",
                    aux_n=1,
                ),
                _make_cli_row(
                    cli_base_frame + 36,
                    stim_h_ms + 6.0,
                    3061.0,
                    3006.0,
                    "rpc_stop_sent",
                    take_id,
                    aux_n=0,
                ),
                _make_cli_row(
                    cli_base_frame + 37,
                    stim_h_ms + 25.0,
                    3080.0,
                    3025.0,
                    "ack_recv",
                    "stop_ack",
                    ack_req_epoch_n=epoch,
                    ack_req_take_id=take_id,
                    ack_req_state="parada",
                    ack_req_origin="juego",
                    ack_resp_class="first_terminal",
                    ack_cur_epoch_n=epoch,
                    ack_cur_take_id=take_id,
                    ack_cur_state="parada",
                    ack_cur_origin="juego",
                    aux_n=2,
                ),
            ]
        )

    cam_after_stop = 1 if no_control_restore else 0
    yaw_after_pulse = 10.0 if no_control_restore else 14.5
    cli_rows.extend(
        [
            _make_cli_row(
                cli_base_frame + 38,
                stim_h_ms + 40.0,
                3095.0,
                3040.0,
                "frame_sample",
                "released",
                sandbox_cam_active_b=cam_after_stop,
                hud_hidden_b=0,
                quickbar_hide_flag_b=0,
                quickbar_widget_visible_b=1,
                cam_yaw_deg=10.0,
            ),
            _make_cli_row(
                cli_base_frame + 39,
                stim_h_ms + 120.0,
                3175.0,
                3120.0,
                "frame_sample",
                "post_pulse",
                sandbox_cam_active_b=cam_after_stop,
                hud_hidden_b=0,
                quickbar_hide_flag_b=0,
                quickbar_widget_visible_b=1,
                cam_yaw_deg=yaw_after_pulse,
            ),
        ]
    )

    stimuli = [
        {
            "case_id": take_id,
            "h_ms": stim_h_ms,
            "hold_ms": hold_ms,
            "key": "kF9" if origin == "juego" else "",
            "kind": "stimulus",
            "rep": rep,
            "stage": stage,
            "stim_type": "web_stop" if origin == "web" else ("key_hold" if hold_ms > 0 else "key_press"),
            "take_id": take_id,
        },
        {
            "case_id": take_id,
            "dx_px": 40,
            "h_ms": stim_h_ms + 70.0,
            "kind": "stimulus",
            "rep": rep,
            "sign": 1,
            "stage": stage,
            "stim_type": "look_pulse",
            "take_id": take_id,
        },
    ]

    meta = {
        "allow_dmg_pre_b": allow_dmg_pre_b,
        "case_id": f"{stage}_r{rep}",
        "contemp_yaw_ref_deg": 10.0,
        "go_delay_ms": go_delay_ms,
        "h_start_ms": base_tick_ms,
        "kind": "take_meta",
        "mode": mode,
        "rep": rep,
        "srv_epoch": epoch,
        "stage": stage,
        "take_id": take_id,
    }
    return arm_rows, srv_rows, cli_rows, stimuli, meta


def _make_b6_obs_rows(fixture: dict, *, skip_reset_r2: bool = False) -> list[dict]:
    rows = []
    for idx, act in enumerate(fixture["actors"], start=1):
        pos = list(act["mark_pos_m"])
        if skip_reset_r2 and idx == 1:
            pos[0] += 4.0
        for w in act["wardrobe"]:
            rows.append(
                {
                    "actor_id": act["actor_id"],
                    "alive_b": 1,
                    "item_class": "TShirt_Red" if (skip_reset_r2 and idx == 1 and w["slot_name"] == "Body") else w["item_class"],
                    "net_id_high": 0,
                    "net_id_low": 100 + idx,
                    "real_class": act["real_class"],
                    "slot_name": w["slot_name"],
                    "x_m": float(pos[0]),
                    "y_m": float(pos[1]),
                    "z_m": float(pos[2]),
                }
            )
    return rows


def build_healthy_part(
    part_dir: Path,
    *,
    mutant: str | None = None,
    post_mutate=None,
    op_nonce: str = "a1b2c3d4e5f60718",
) -> Path:
    """Construye una carpeta de parte sintética completa (o mutada para cada uno de los 11 mutantes)."""
    pdir = Path(part_dir)
    samples_dir = pdir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    root = f03_common.REPO_ROOT
    harness = gate_core.git_harness(repo_root=root)
    git_head = harness["git_head"]
    probe_stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=root)
    fixture_path = QA_DIR / "fixtures" / "s_toma_fixture.json"
    fixture = gate_core.read_json(fixture_path)
    fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()

    b = _SyntheticTraceBuilder(fixture, git_head, probe_stamp, op_nonce=op_nonce)
    b.emit_hello("server", "srv-inst-1")
    b.emit_hello("client", "cli-inst-1")

    prefix = "1a2b3c4d-"
    b.scenario_rows.append(
        {
            "calib_sign": 1,
            "calib_step_deg": 4.5,
            "eps_look_deg": 0.5,
            "kind": "run_meta",
            "no_pulse_shift_deg": 0.05,
            "take_id_prefix": prefix,
        }
    )

    # Verificación del observador S3
    b.emit_op(
        "server",
        "take_scene_prep",
        args_str={"op": "verify"},
        read_str={"adapter_ver": ADAPTER_VER, "observer_stamp": b.probe_ver},
        read_num={"observer_ok_b": 1, "scene_ok_b": 1},
    )

    # S0a / S0b: auditoría de tecla, recarga de cliente y restauración
    conflict_ignored = mutant == "take_key_conflict_ignored"
    b.emit_op(
        "client",
        "take_key_op",
        args_str={"action_name": "UADsbxQaTakeStop", "op": "audit_candidates"},
        read_str={
            "bound_keys_csv": "kF9",
            "build_version": "1.30.164200",
            "conflicting_actions_csv": "UAGear" if conflict_ignored else "",
            "selected_alt_key": "kF10",
            "selected_def_key": "kF9",
        },
        read_num={
            "candidates_checked_n": 4,
            "conflict_count_alt": 0,
            "conflict_count_def": 1 if conflict_ignored else 0,
            "export_called_b": 1,
            "free_candidates_n": 3,
            "input_id": 77,
        },
    )
    s0a_tid = f"{prefix}keydef"
    b.scenario_rows.append({"case_id": "keydef", "kind": "take_meta", "rep": 1, "stage": "S0a", "take_id": s0a_tid})

    b.emit_op(
        "client",
        "take_key_op",
        args_str={"action_name": "UADsbxQaTakeStop", "op": "bind_key", "target_key": "kF10"},
        read_str={"bound_keys_csv": "kF10", "selected_alt_key": "kF10"},
        read_num={"conflict_count_alt": 0, "export_called_b": 1, "input_id": 77},
    )
    # Recarga real del cliente en S0b (nuevo inst)
    b.emit_hello("client", "cli-inst-2")
    s0b_tid = f"{prefix}keyreb"
    b.scenario_rows.append({"case_id": "keyreb", "kind": "take_meta", "rep": 1, "stage": "S0b", "take_id": s0b_tid})
    b.scenario_rows.extend(
        [
            {"h_ms": 1100.0, "key": "kF9", "kind": "stimulus", "stage": "S0b", "stim_type": "key_press", "take_id": s0b_tid},
            {"h_ms": 1600.0, "key": "kF10", "kind": "stimulus", "stage": "S0b", "stim_type": "key_press", "take_id": s0b_tid},
        ]
    )
    b.emit_job_with_pages(
        "server",
        "take_arm",
        s0b_tid,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(110, 1000.0, 16.0, 0.0, "go_sent", s0b_tid, "rodando", v1=110, v2=1000.0)],
    )
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        s0b_tid,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(140, 1620.0, 620.0, 620.0, "take_terminal", s0b_tid, "parada:juego", v1=140, v2=1620.0, v3=620.0, v6=1, v7=1)],
    )
    b.emit_job_with_pages(
        "client",
        "take_cli_watch_start",
        s0b_tid,
        CLI_NCOL,
        CLI_SCOL,
        [_make_cli_row(210, 1610.0, 610.0, 1500.0, "key_edge", "press_accepted", aux_n=1)],
    )
    b.emit_op(
        "client",
        "take_key_op",
        args_str={"action_name": "UADsbxQaTakeStop", "op": "bind_key", "target_key": "kF9"},
        read_str={"bound_keys_csv": "kF9", "selected_def_key": "kF9"},
        read_num={"conflict_count_def": 0, "export_called_b": 1, "input_id": 77},
    )
    b.emit_op(
        "client",
        "take_key_op",
        args_str={"action_name": "UADsbxQaTakeStop", "op": "restore_bindings"},
        read_str={"bound_keys_csv": "kF9"},
        read_num={"export_called_b": 1, "input_id": 77},
    )

    # S1: 3 repeticiones con reset B6, perturbación antes de r=2 y parada web a los 3 s
    for rep in (1, 2, 3):
        if rep == 2:
            b.emit_op("server", "take_scene_prep", args_str={"op": "perturb_fixture"}, read_num={"scene_ok_b": 1})
        b.emit_op(
            "server",
            "act_observe",
            args_str={"op": "snapshot"},
            read_str={"adapter_ver": ADAPTER_VER, "backend_class": "DSBX_QA_ActorAdapterExp", "core_ver": b.probe_ver},
            read_num={"backend_available_b": 1},
            ncol=ACT_OBS_NCOL,
            scol=ACT_OBS_SCOL,
            rows=_make_b6_obs_rows(fixture, skip_reset_r2=(mutant == "take_no_reset_between_reps" and rep == 2)),
        )
        tid = f"{prefix}s1-r{rep}"
        base_t = 10000.0 * rep
        b.emit_clock_calibration("S1", rep, base_t)
        lag_a2 = 250.0 if (mutant == "take_actor2_lag_250ms" and rep == 2) else 0.0
        drift_m = 0.85 if (mutant == "take_cam_path_drift" and rep == 2) else 0.0
        arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
            fixture,
            tid,
            "S1",
            rep,
            base_t,
            mode="rpc",
            origin="web",
            allow_dmg_pre_b=1 if rep in (1, 3) else 0,
            actor2_lag_ms=lag_a2,
            cam_drift_m=drift_m,
            director_mortal=(mutant == "take_director_mortal"),
            cues_keep_firing=(mutant == "take_cues_keep_firing"),
            no_control_restore=(mutant == "take_no_control_restore"),
        )
        b.scenario_rows.append(meta_r)
        b.scenario_rows.extend(stim_r)
        b.emit_job_with_pages("server", "take_arm", tid, SRV_NCOL, SRV_SCOL, arm_r, mode="rpc")
        b.emit_job_with_pages("server", "take_srv_observe_start", tid, SRV_NCOL, SRV_SCOL, srv_r, mode="rpc")
        b.emit_job_with_pages("client", "take_cli_watch_start", tid, CLI_NCOL, CLI_SCOL, cli_r, mode="rpc")

    # S1sel: 3 repeticiones con retardo controlado 0 / 160 / 0 ms en la cola de entrega del cliente (T9)
    for rep, delay_ms in ((1, 0.0), (2, 160.0), (3, 0.0)):
        tid = f"{prefix}s1sel-r{rep}"
        base_t = 50000.0 + 10000.0 * rep
        b.emit_clock_calibration("S1sel", rep, base_t)
        arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
            fixture, tid, "S1sel", rep, base_t, mode="rpc", origin="web", go_delay_ms=delay_ms
        )
        b.scenario_rows.append(meta_r)
        b.scenario_rows.extend(stim_r)
        b.emit_job_with_pages("server", "take_arm", tid, SRV_NCOL, SRV_SCOL, arm_r, mode="rpc")
        b.emit_job_with_pages("server", "take_srv_observe_start", tid, SRV_NCOL, SRV_SCOL, srv_r, mode="rpc")
        b.emit_job_with_pages("client", "take_cli_watch_start", tid, CLI_NCOL, CLI_SCOL, cli_r, mode="rpc")

    # S1c: 3 repeticiones en modo common_time (T9)
    for rep in (1, 2, 3):
        tid = f"{prefix}s1c-r{rep}"
        base_t = 90000.0 + 10000.0 * rep
        b.emit_clock_calibration("S1c", rep, base_t)
        lag_a2 = 250.0 if (mutant == "take_actor2_lag_250ms" and rep == 2) else 0.0
        arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
            fixture, tid, "S1c", rep, base_t, mode="common_time", origin="web", actor2_lag_ms=lag_a2
        )
        b.scenario_rows.append(meta_r)
        b.scenario_rows.extend(stim_r)
        b.emit_job_with_pages("server", "take_arm", tid, SRV_NCOL, SRV_SCOL, arm_r, mode="common_time")
        b.emit_job_with_pages("server", "take_srv_observe_start", tid, SRV_NCOL, SRV_SCOL, srv_r, mode="common_time")
        b.emit_job_with_pages("client", "take_cli_watch_start", tid, CLI_NCOL, CLI_SCOL, cli_r, mode="common_time")

    # S2: 3 repeticiones con parada desde el juego (tecla, con hold >= 600 ms en r=2)
    for rep in (1, 2, 3):
        tid = f"{prefix}s2-r{rep}"
        base_t = 130000.0 + 10000.0 * rep
        b.emit_clock_calibration("S2", rep, base_t)
        arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
            fixture,
            tid,
            "S2",
            rep,
            base_t,
            mode="rpc",
            origin="juego",
            hold_ms=650.0 if rep == 2 else 0.0,
            cues_keep_firing=(mutant == "take_cues_keep_firing"),
            no_control_restore=(mutant == "take_no_control_restore"),
        )
        b.scenario_rows.append(meta_r)
        b.scenario_rows.extend(stim_r)
        b.emit_job_with_pages("server", "take_arm", tid, SRV_NCOL, SRV_SCOL, arm_r, mode="rpc")
        b.emit_job_with_pages("server", "take_srv_observe_start", tid, SRV_NCOL, SRV_SCOL, srv_r, mode="rpc")
        b.emit_job_with_pages("client", "take_cli_watch_start", tid, CLI_NCOL, CLI_SCOL, cli_r, mode="rpc")

    # S3a: 3 errores síncronos de preparación y 5 casos negativos de conexión y stop
    arm_broken_ignored = mutant == "take_arm_ignores_broken_prep"
    for err_reason in ("cam_not_ready", "actor_incapable", "no_director"):
        b.emit_op(
            "server",
            "take_arm",
            args_str={"mode": "rpc", "take_id": f"{prefix}err-{err_reason}"},
            status="done" if arm_broken_ignored else "error",
            reason="" if arm_broken_ignored else err_reason,
            read_str={"err": "" if arm_broken_ignored else err_reason},
        )

    conn_completes = mutant == "take_conn_drop_completes"
    # Rama 1 de conn_drop: sin efectos (common_time antes del GO)
    tid_c1 = f"{prefix}cdrop1"
    b.scenario_rows.append({"case_id": "conn_drop_no_effects", "kind": "take_meta", "stage": "S3a", "take_id": tid_c1})
    b.scenario_rows.append(
        {
            "case_id": "conn_drop_no_effects",
            "kind": "cut_window",
            "last_ok_poll_h_ms": 170000.0,
            "last_ok_poll_tick_ms": 170000.0,
            "lease_ms": 2000.0,
            "peer": "server",
            "reconnect_poll_h_ms": 173500.0,
            "reconnect_poll_tick_ms": 173500.0,
            "stage": "S3a",
            "take_id": tid_c1,
        }
    )
    b.emit_job_with_pages(
        "server",
        "take_arm",
        tid_c1,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(900, 170000.0, 16.0, 0.0, "arm_ready", tid_c1, "armada")],
        mode="common_time",
        state="stopped",
        reason="lease_expired",
    )
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_c1,
        SRV_NCOL,
        SRV_SCOL,
        [
            _make_srv_row(
                940,
                172100.0,
                2100.0,
                0.0,
                "take_terminal",
                tid_c1,
                "terminada:normal" if conn_completes else "parada:hombre_muerto",
                v1=940,
                v2=172100.0,
                v4=2100.0,
                v6=1,
                v7=1,
            )
        ],
    )
    b.emit_job_with_pages("client", "take_cli_watch_start", tid_c1, CLI_NCOL, CLI_SCOL, [])

    # Rama 2 de conn_drop: tras haber disparado cámara y actores (R5-N5)
    tid_c2 = f"{prefix}cdrop2"
    b.scenario_rows.append(
        {
            "allow_dmg_pre_b": 1,
            "case_id": "conn_drop_after_effects",
            "kind": "take_meta",
            "stage": "S3a",
            "take_id": tid_c2,
        }
    )
    b.scenario_rows.append(
        {
            "case_id": "conn_drop_after_effects",
            "kind": "cut_window",
            "last_ok_poll_h_ms": 175500.0,
            "last_ok_poll_tick_ms": 175500.0,
            "lease_ms": 2000.0,
            "peer": "server",
            "reconnect_poll_h_ms": 179000.0,
            "reconnect_poll_tick_ms": 179000.0,
            "stage": "S3a",
            "take_id": tid_c2,
        }
    )
    b.emit_job_with_pages(
        "server",
        "take_arm",
        tid_c2,
        SRV_NCOL,
        SRV_SCOL,
        [
            _make_srv_row(950, 175000.0, 16.0, 0.0, "go_sent", tid_c2, "rodando", v1=950, v2=175000.0),
            _make_srv_row(950, 175000.0, 16.0, 0.0, "dispatch", "actor_1", "rpc", v1=950, v2=175000.0),
            _make_srv_row(950, 175000.0, 16.0, 0.0, "dispatch", "actor_2", "rpc", v1=950, v2=175000.0),
        ],
        state="stopped",
        reason="lease_expired",
        end_tick_ms=177600.0,
        onjobend_tick_ms=177610.0,
        released_tick_ms=177620.0,
    )
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_c2,
        SRV_NCOL,
        SRV_SCOL,
        [
            _make_srv_row(
                990,
                177600.0,
                2600.0,
                2600.0,
                "take_terminal",
                tid_c2,
                "terminada:normal" if conn_completes else "parada:hombre_muerto",
                v1=990,
                v2=177600.0,
                v3=2600.0,
                v4=2100.0,
                v5=990,
                v6=1,
                v7=1,
                v8=1,
                v9=0,
                v10=0,
                v11=0,
            ),
            _make_srv_row(
                991,
                177616.0,
                2616.0,
                2616.0,
                "cleanup_done",
                tid_c2,
                "parada:hombre_muerto",
                v1=991,
                v2=177616.0,
                v3=1,
                v4=1,
            ),
        ],
    )
    b.emit_job_with_pages(
        "client",
        "take_cli_watch_start",
        tid_c2,
        CLI_NCOL,
        CLI_SCOL,
        [
            _make_cli_row(1200, 175100.0, 100.0, 100.0, "frame_sample", "active", sandbox_cam_active_b=1),
            _make_cli_row(1240, 177600.0, 2600.0, 2100.0, "cli_safety_exit", "lease_expired", aux_n=1240),
        ],
    )

    for sc_idx, stop_case in enumerate(("stop_before_go", "double_stop_at_go", "stop_at_600ms"), start=1):
        tid_sc = f"{prefix}s3a-{sc_idx}"
        b.scenario_rows.append({"case_id": stop_case, "kind": "take_meta", "stage": "S3a", "take_id": tid_sc})
        b.emit_job_with_pages("server", "take_arm", tid_sc, SRV_NCOL, SRV_SCOL, [])
        b.emit_job_with_pages(
            "server",
            "take_srv_observe_start",
            tid_sc,
            SRV_NCOL,
            SRV_SCOL,
            [
                _make_srv_row(
                    1000 + sc_idx,
                    180000.0 + sc_idx * 500.0,
                    600.0,
                    600.0,
                    "take_terminal",
                    tid_sc,
                    "parada:web",
                    v1=1000 + sc_idx,
                    v2=180000.0 + sc_idx * 500.0,
                    v6=1,
                    v7=1,
                )
            ],
        )

    # S3b: negativas de tecla (sin toma, menú, chat, 4 rechazos con T3/T4/T5)
    for blocker in ("menu", "chat", "none"):
        b.emit_op(
            "client",
            "take_cam_prep",
            args_str={"op": "set_ui_blocker", "ui_blocker": blocker},
            read_num={
                "chat_open_b": 1 if blocker == "chat" else 0,
                "menu_open_b": 1 if blocker == "menu" else 0,
            },
        )

    prior_tid = f"{prefix}prior"
    guard_tid = f"{prefix}guard"
    b.scenario_rows.extend(
        [
            {"case_id": "prior_terminal_same_epoch", "kind": "take_meta", "stage": "S3b", "take_id": prior_tid},
            {"case_id": "guard", "contemp_yaw_ref_deg": 10.0, "kind": "take_meta", "stage": "S3b", "take_id": guard_tid},
        ]
    )
    b.emit_job_with_pages(
        "server",
        "take_arm",
        prior_tid,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1100, 190000.0, 16.0, 0.0, "go_sent", prior_tid, "rodando", v1=1100, v2=190000.0)],
    )
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        prior_tid,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1110, 190500.0, 500.0, 500.0, "take_terminal", prior_tid, "parada:web", v1=1110, v2=190500.0, v6=1, v7=1)],
    )

    b.emit_job_with_pages(
        "server",
        "take_arm",
        guard_tid,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1120, 191000.0, 16.0, 0.0, "go_sent", guard_tid, "rodando", v1=1120, v2=191000.0)],
    )
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        guard_tid,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1180, 195000.0, 4000.0, 4000.0, "take_terminal", guard_tid, "parada:web", v1=1180, v2=195000.0, v6=1, v7=1)],
    )

    rej_cases = [
        ("old_take_same_epoch", "qa-uid-dir-main", "qa-uid-dir-main", "dir_main", 191200.0),
        ("other_epoch", "qa-uid-dir-main", "qa-uid-dir-main", "dir_main", 191600.0),
        ("other_director_c1", "qa-uid-dir-other", "qa-uid-dir-main", "dir_main", 192000.0),
        ("other_director_c2", "qa-uid-dir-other", "qa-uid-dir-main", "dir_other", 192400.0),
    ]
    guard_cli_rows = [
        _make_cli_row(
            1300,
            189500.0,
            10.0,
            0.0,
            "key_edge",
            "press_accepted" if mutant == "take_key_stops_without_take" else "ignored_no_take",
            aux_n=0,
        ),
        _make_cli_row(1301, 189600.0, 20.0, 0.0, "key_edge", "ignored_menu", aux_n=0),
        _make_cli_row(1302, 189700.0, 30.0, 0.0, "key_edge", "ignored_chat", aux_n=0),
        _make_cli_row(
            1310,
            191220.0,
            220.0,
            220.0,
            "ack_recv",
            "repeat_for_prior",
            ack_req_epoch_n=1,
            ack_req_take_id=prior_tid,
            ack_req_state="parada",
            ack_req_origin="web",
            ack_resp_class="repeat_terminal",
            ack_cur_epoch_n=1,
            ack_cur_take_id=guard_tid,
            ack_cur_state="rodando",
            ack_cur_origin="rpc",
            aux_n=3,
        ),
    ]
    for r_idx, (rcase, reg_uid, snd_uid, pay_id, r_tick) in enumerate(rej_cases, start=1):
        b.scenario_rows.append(
            {
                "case_id": rcase,
                "cli_tick_ms": r_tick,
                "guard_take_id": guard_tid,
                "h_ms": r_tick,
                "kind": "key_rejection",
                "payload_sender_id": pay_id,
                "reg_engine_uid": reg_uid,
                "sender_engine_uid": snd_uid,
                "srv_tick_ms": r_tick + 10.0,
                "stage": "S3b",
                "take_id": guard_tid,
            }
        )
        b.scenario_rows.append(
            {
                "case_id": rcase,
                "dx_px": 40,
                "h_ms": r_tick + 50.0,
                "kind": "stimulus",
                "sign": 1,
                "stage": "S3b",
                "stim_type": "look_pulse",
                "take_id": guard_tid,
            }
        )
        guard_cli_rows.append(
            _make_cli_row(
                1320 + r_idx * 2,
                r_tick + 30.0,
                300.0 + r_idx * 50.0,
                300.0 + r_idx * 50.0,
                "take_state_recv",
                "dir_main",
                ack_cur_epoch_n=1,
                ack_cur_take_id=guard_tid,
                ack_cur_state="rodando",
                ack_cur_origin="rpc",
                aux_n=10 + r_idx,
            )
        )
        guard_cli_rows.append(
            _make_cli_row(
                1321 + r_idx * 2,
                r_tick + 90.0,
                360.0 + r_idx * 50.0,
                360.0 + r_idx * 50.0,
                "frame_sample",
                "after_local_exit",
                sandbox_cam_active_b=0,
                cam_yaw_deg=15.0,
            )
        )
    b.emit_job_with_pages("client", "take_cli_watch_start", guard_tid, CLI_NCOL, CLI_SCOL, guard_cli_rows)

    # S3c y S3d: reintentos, carreras, hombre muerto y reinicio de proceso
    unretried = mutant == "take_key_rpc_drop_unretried"
    tid_dreq = f"{prefix}dreq"
    b.scenario_rows.append(
        {
            "case_id": "drop_first_req",
            "kind": "take_meta",
            "retry_cli_recov_hi_ms": 420.0,
            "retry_srv_stop_hi_ms": 380.0,
            "stage": "S3c",
            "take_id": tid_dreq,
        }
    )
    b.emit_job_with_pages("server", "take_arm", tid_dreq, SRV_NCOL, SRV_SCOL, [])
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_dreq,
        SRV_NCOL,
        SRV_SCOL,
        []
        if unretried
        else [_make_srv_row(1400, 200350.0, 350.0, 350.0, "take_terminal", tid_dreq, "parada:juego", v1=1400, v2=200350.0, v6=1, v7=1)],
    )
    b.emit_job_with_pages(
        "client",
        "take_cli_watch_start",
        tid_dreq,
        CLI_NCOL,
        CLI_SCOL,
        [_make_cli_row(1400, 200000.0, 100.0, 100.0, "rpc_stop_sent", tid_dreq, aux_n=0)]
        + ([] if unretried else [_make_cli_row(1415, 200260.0, 360.0, 360.0, "rpc_stop_sent", tid_dreq, aux_n=1)]),
    )

    tid_dack = f"{prefix}dack"
    b.scenario_rows.append({"case_id": "drop_first_ack", "kind": "take_meta", "stage": "S3c", "take_id": tid_dack})
    b.emit_job_with_pages("server", "take_arm", tid_dack, SRV_NCOL, SRV_SCOL, [])
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_dack,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1420, 201000.0, 300.0, 300.0, "take_terminal", tid_dack, "parada:juego", v1=1420, v2=201000.0, v6=1, v7=1)],
    )
    b.emit_job_with_pages(
        "client",
        "take_cli_watch_start",
        tid_dack,
        CLI_NCOL,
        CLI_SCOL,
        [
            _make_cli_row(1420, 201000.0, 100.0, 100.0, "rpc_stop_sent", tid_dack, aux_n=0),
            _make_cli_row(1435, 201260.0, 360.0, 360.0, "rpc_stop_sent", tid_dack, aux_n=1),
            _make_cli_row(
                1436,
                201280.0,
                380.0,
                380.0,
                "ack_recv",
                "retry_ack",
                ack_req_epoch_n=1,
                ack_req_take_id=tid_dack,
                ack_req_state="parada",
                ack_req_origin="juego",
                ack_resp_class="repeat_terminal",
                ack_cur_epoch_n=1,
                ack_cur_take_id=tid_dack,
                ack_cur_state="parada",
                ack_cur_origin="juego",
                aux_n=20,
            ),
        ],
    )

    tid_sim = f"{prefix}sim"
    b.scenario_rows.append({"case_id": "simul_key_and_web", "kind": "take_meta", "stage": "S3c", "take_id": tid_sim})
    b.emit_job_with_pages("server", "take_arm", tid_sim, SRV_NCOL, SRV_SCOL, [])
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_sim,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1450, 202000.0, 500.0, 500.0, "take_terminal", tid_sim, "parada:juego", v1=1450, v2=202000.0, v6=1, v7=1)],
    )

    tid_hgo = f"{prefix}hgo"
    b.scenario_rows.append({"case_id": "held_go_after_key", "kind": "take_meta", "stage": "S3c", "take_id": tid_hgo})
    b.emit_job_with_pages("server", "take_arm", tid_hgo, SRV_NCOL, SRV_SCOL, [])
    b.emit_job_with_pages(
        "client",
        "take_cli_watch_start",
        tid_hgo,
        CLI_NCOL,
        CLI_SCOL,
        [
            _make_cli_row(1460, 203000.0, 100.0, 100.0, "key_edge", "press_accepted", aux_n=1),
            _make_cli_row(1465, 203100.0, 200.0, 200.0, "frame_sample", "after_held_go", sandbox_cam_active_b=0),
        ],
    )
    b.emit_op("client", "take_cam_prep", args_str={"op": "release_held_go"}, read_num={"late_go_ignored_n": 1})

    tid_sta = f"{prefix}sta"
    tid_stb = f"{prefix}stb"
    b.scenario_rows.extend(
        [
            {"case_id": "stale_notify_take_a", "kind": "take_meta", "stage": "S3c", "take_id": tid_sta},
            {"case_id": "stale_notify_take_b", "kind": "take_meta", "stage": "S3c", "take_id": tid_stb},
        ]
    )
    b.emit_job_with_pages("client", "take_cli_watch_start", tid_stb, CLI_NCOL, CLI_SCOL, [])
    b.emit_op(
        "client",
        "take_cam_prep",
        args_str={"op": "deliver_stale_msg", "take_id": tid_sta},
        read_num={"sandbox_cam_active_b": 1, "stale_msg_ignored_n": 1},
    )

    tid_ack2 = f"{prefix}ack2"
    tid_new = f"{prefix}new"
    b.scenario_rows.extend(
        [
            {"case_id": "ack2", "kind": "take_meta", "stage": "S3c", "take_id": tid_ack2},
            {"case_id": "new", "kind": "take_meta", "stage": "S3c", "take_id": tid_new},
        ]
    )
    b.emit_job_with_pages(
        "client",
        "take_cli_watch_start",
        tid_new,
        CLI_NCOL,
        CLI_SCOL,
        [
            _make_cli_row(
                1480,
                204000.0,
                200.0,
                200.0,
                "ack_recv",
                "late_ack_from_ack2",
                ack_req_epoch_n=1,
                ack_req_take_id=tid_ack2,
                ack_req_state="parada",
                ack_req_origin="juego",
                ack_resp_class="first_terminal",
                ack_cur_epoch_n=1,
                ack_cur_take_id=tid_new,
                ack_cur_state="rodando",
                ack_cur_origin="rpc",
                aux_n=30,
            )
        ],
    )
    b.emit_op(
        "client",
        "take_cam_prep",
        args_str={"op": "status", "take_id": tid_new},
        read_str={"cli_cached_origin": "rpc", "cli_cached_state": "rodando", "cli_cached_take_id": tid_new},
        read_num={"cli_cached_epoch": 1, "cli_state_seq": 30},
    )

    for ed_idx in (1, 2):
        tid_ed = f"{prefix}edup{ed_idx}"
        b.scenario_rows.append({"case_id": f"epoch_dup_{ed_idx}", "kind": "take_meta", "stage": "S3c", "take_id": tid_ed})

    tid_nk = f"{prefix}cutnk"
    b.scenario_rows.append({"case_id": "cut_nokey", "kind": "take_meta", "lease_ms": 2000.0, "stage": "S3c", "take_id": tid_nk})
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_nk,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1500, 206500.0, 2500.0, 2500.0, "take_terminal", tid_nk, "parada:hombre_muerto", v1=1500, v2=206500.0, v4=2100.0, v6=1, v7=1)],
    )

    tid_cbef = f"{prefix}cutbef"
    b.scenario_rows.append({"case_id": "cut_before", "kind": "take_meta", "stage": "S3c", "take_id": tid_cbef})
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_cbef,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1510, 207500.0, 1500.0, 1500.0, "take_terminal", tid_cbef, "parada:juego", v1=1510, v2=207500.0, v6=1, v7=1)],
    )

    tid_caft = f"{prefix}cutaft"
    b.scenario_rows.append({"case_id": "cut_after", "kind": "take_meta", "stage": "S3c", "take_id": tid_caft})
    b.scenario_rows.append(
        {
            "case_id": "cut_after",
            "kind": "cut_window",
            "last_ok_poll_h_ms": 208000.0,
            "last_ok_poll_tick_ms": 208000.0,
            "lease_ms": 2000.0,
            "peer": "client",
            "reconnect_poll_h_ms": 211500.0,
            "reconnect_poll_tick_ms": 211500.0,
            "stage": "S3c",
            "take_id": tid_caft,
        }
    )
    b.emit_job_with_pages(
        "server",
        "take_srv_observe_start",
        tid_caft,
        SRV_NCOL,
        SRV_SCOL,
        [_make_srv_row(1520, 210200.0, 2200.0, 2200.0, "take_terminal", tid_caft, "parada:hombre_muerto", v1=1520, v2=210200.0, v4=2100.0, v6=1, v7=1)],
    )
    b.emit_job_with_pages(
        "client",
        "take_cli_watch_start",
        tid_caft,
        CLI_NCOL,
        CLI_SCOL,
        [_make_cli_row(1520, 210100.0, 2100.0, 2100.0, "frame_sample", "after_lease", sandbox_cam_active_b=0)],
    )

    for pd_idx in (1, 2):
        tid_pd = f"{prefix}pdup{pd_idx}"
        b.scenario_rows.append(
            {
                "case_id": f"procdup_{pd_idx}",
                "contaminated_by_old_retry_b": 0,
                "kind": "take_meta",
                "restart_exceeded_lease_b": 0,
                "stage": "S3d",
                "take_id": tid_pd,
            }
        )

    manifest = {
        "argv": ["m1_gate.py", "spike", "S-toma", "--both", "--build", "offline"],
        "both": True,
        "build": "offline",
        "ended_utc": "2026-11-15T08:00:10Z",
        "faults": [mutant] if mutant else [],
        "harness": harness,
        "id": "S-toma",
        "identity": {
            "build": "offline",
            "git_dirty": harness.get("git_dirty"),
            "git_head": git_head,
            "params": {
                "adapter_ver_expected": ADAPTER_VER,
                "fixture_sha256": fixture_sha,
                "hold_ms": gate_core.DEFAULT_HOLD_MS,
                "lease_ms": gate_core.DEFAULT_LEASE_MS,
                "probe_budget_log_poll_ms": f03_common.PROBE_BUDGET_LOG_POLL_MS,
                "probe_budget_retry_ms": f03_common.PROBE_BUDGET_RETRY_MS,
                "retry_ms": gate_core.DEFAULT_RETRY_MS,
                "seed": gate_core.DEFAULT_SEED,
                "ttl_ms": gate_core.DEFAULT_TTL_MS,
                "wire_cap": int(wire.WIRE_CAP),
            },
            "pbo_sha256": None,
            "peer_builds": {"client": "offline", "server": "offline"},
            "probe_stamp": probe_stamp,
        },
        "kind": "spike",
        "params": {
            "hold_ms": gate_core.DEFAULT_HOLD_MS,
            "lease_ms": gate_core.DEFAULT_LEASE_MS,
            "port": 51234,
            "retry_ms": gate_core.DEFAULT_RETRY_MS,
            "run_id": "1a2b3c4d",
            "seed": gate_core.DEFAULT_SEED,
            "ttl_ms": gate_core.DEFAULT_TTL_MS,
        },
        "schema": gate_core.SCHEMA_MANIFEST,
        "started_utc": "2026-11-15T08:00:00Z",
    }

    if callable(post_mutate):
        post_mutate(manifest, b.bridge_rows, b.scenario_rows)

    gate_core.write_json(pdir / "manifest.json", manifest)
    gate_core.write_json(
        pdir / "part.json",
        {
            "op_map": b.op_map,
            "op_nonce": op_nonce,
            "part": pdir.name,
            "spike_id": "S-toma",
        },
    )
    if mutant:
        gate_core.write_json(
            pdir / "injection.json",
            {
                "applied": True,
                "kind": "synthetic_fault",
                "mutant": mutant,
                "observable_effect": {"fault_injected": mutant},
                "target": "both",
                "when_h_ms": 100.0,
            },
        )

    with (samples_dir / "bridge.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in b.bridge_rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")

    with (samples_dir / "scenario.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in b.scenario_rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")

    return pdir


class TestSTomaOracleOffline(unittest.TestCase):
    """Suite de pruebas offline del oráculo de S-toma."""

    def test_check_12_blind_evaluators_on_s_toma_eval(self):
        self.assertEqual(test_probe_static.check_12_blind_evaluators(QA_DIR), [])

    def test_healthy_part_passes_all_7_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            verdict = s_toma_eval.evaluate(pdir)
            self.assertEqual(verdict["exit_code"], 0, verdict)
            self.assertEqual(verdict["verdict"], "PASA")
            checks_by_id = {c["id"]: c["status"] for c in verdict["checks"]}
            for cid in s_toma_eval.CHECK_IDS:
                self.assertEqual(checks_by_id.get(cid), "pass", f"{cid} no dio pass: {verdict}")

    def test_tom_01_fallback_to_common_time_when_rpc_delivery_jitter_gt_100ms(self):
        def _inject_rpc_delivery_jitter(_man, bridge_rows, _scen_rows):
            for ev in bridge_rows:
                if ev.get("ev") != "result":
                    continue
                res = ev.get("result") or {}
                read = res.get("read") or {}
                if not all(k in read for k in wire.PAYLOAD_KEYS):
                    continue
                unp = wire.unpack_payload(read)
                if unp["str"].get("job", "").startswith("job-take_cli_watch_start-1a2b3c4d-s1-r2"):
                    new_rows = []
                    for row in unp["rows"]:
                        r_copy = dict(row)
                        if r_copy["row_kind"] in ("go_deliver", "frame_sample") and float(r_copy["take_dtsum_ms"]) >= 0.0:
                            r_copy["cli_tick_ms"] = float(r_copy["cli_tick_ms"]) + 130.0
                        new_rows.append(r_copy)
                    repacked = wire.pack_payload(
                        scalars_str=unp["str"],
                        scalars_num=unp["num"],
                        num_cols=unp["ncol"],
                        str_cols=unp["scol"],
                        row_dicts=new_rows,
                    )
                    repacked["has"] = ["payload"]
                    res["read"] = repacked

        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run", post_mutate=_inject_rpc_delivery_jitter)
            verdict = s_toma_eval.evaluate(pdir)
            self.assertEqual(verdict["exit_code"], 0, verdict)
            tom01 = next(c for c in verdict["checks"] if c["id"] == "TOM-01")
            self.assertEqual(tom01["status"], "pass")
            self.assertEqual(tom01.get("observed", {}).get("active_mode"), "common_time")

    def test_invariance_under_coherent_op_id_renaming_without_part_or_injection_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            v_orig = s_toma_eval.evaluate(pdir)
            (pdir / "part.json").unlink(missing_ok=True)
            (pdir / "injection.json").unlink(missing_ok=True)

            b_path = pdir / "samples" / "bridge.jsonl"
            rows = f03_common.read_jsonl(b_path)
            rename_map = {}
            for ev in rows:
                oid = ev.get("op_id")
                if isinstance(oid, str) and oid not in rename_map:
                    rename_map[oid] = f"renamed-opaque-{len(rename_map) + 1:04d}"

            for ev in rows:
                if isinstance(ev.get("op_id"), str):
                    ev["op_id"] = rename_map[ev["op_id"]]
                if isinstance(ev.get("op_ids"), list):
                    ev["op_ids"] = [rename_map.get(x, x) for x in ev["op_ids"]]
                if isinstance(ev.get("result"), dict) and isinstance(ev["result"].get("op_id"), str):
                    ev["result"]["op_id"] = rename_map[ev["result"]["op_id"]]

            with b_path.open("w", encoding="utf-8", newline="\n") as fh:
                for r in rows:
                    fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")

            v_renamed = s_toma_eval.evaluate(pdir)
            self.assertEqual(v_orig["exit_code"], v_renamed["exit_code"])
            self.assertEqual(v_orig["checks"], v_renamed["checks"])

    def test_invariance_under_24_char_qa_fault_in_poll_body_len(self):
        order_healthy = {
            "args": wire.pack_payload(scalars_str={"op": "verify", "qa_fault": wire.format_qa_fault(None)}),
            "inst": "srv-1",
            "issued_ms": 100.0,
            "op_id": "op-1",
            "ttl_ms": 5000,
            "verb": "take_scene_prep",
        }
        order_mutant = {
            "args": wire.pack_payload(scalars_str={"op": "verify", "qa_fault": wire.format_qa_fault("take_director_mortal")}),
            "inst": "srv-1",
            "issued_ms": 100.0,
            "op_id": "op-1",
            "ttl_ms": 5000,
            "verb": "take_scene_prep",
        }
        self.assertEqual(len(wire.poll_wire_bytes(order_healthy)), len(wire.poll_wire_bytes(order_mutant)))

    def test_invariance_when_wire_cap_changed_in_memory_uses_manifest_identity_params(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            orig_cap = wire.WIRE_CAP
            try:
                wire.WIRE_CAP = 500
                verdict = s_toma_eval.evaluate(pdir)
                self.assertEqual(verdict["exit_code"], 0, verdict)
                self.assertEqual(verdict["metrics"]["wire_cap"], orig_cap)
            finally:
                wire.WIRE_CAP = orig_cap

    def test_worst_case_job_read_page_wire_bytes_under_wire_cap(self):
        worst_rows = [
            _make_cli_row(
                999999,
                999999.999,
                999999.999,
                999999.999,
                "ack_recv",
                "repeat_terminal_detail_str",
                sandbox_cam_active_b=1,
                hud_hidden_b=1,
                quickbar_hide_flag_b=1,
                quickbar_widget_visible_b=0,
                cam_x_m=15360.1234,
                cam_y_m=512.5678,
                cam_z_m=15360.9876,
                cam_yaw_deg=-179.9876,
                cam_pitch_deg=-89.1234,
                cam_fov_deg=1.2345,
                ack_req_epoch_n=99,
                ack_cur_epoch_n=99,
                aux_n=99999,
                ack_req_take_id="1a2b3c4d-worst-case-01",
                ack_req_state="parada",
                ack_req_origin="hombre_muerto",
                ack_resp_class="repeat_terminal",
                ack_cur_take_id="1a2b3c4d-worst-case-02",
                ack_cur_state="rodando",
                ack_cur_origin="common_time",
            )
            for _ in range(4)
        ]
        packed = wire.pack_payload(
            scalars_str={"adapter_ver": ADAPTER_VER, "job": "job-take_cli_watch-9999", "reason": "", "state": "done"},
            scalars_num={
                "end_tick_ms": 999999.999,
                "onjobend_tick_ms": 999999.999,
                "page_n": 99,
                "pages_n": 100,
                "released_tick_ms": 999999.999,
                "rows_total_n": 400,
            },
            num_cols=CLI_NCOL,
            str_cols=CLI_SCOL,
            row_dicts=worst_rows,
        )
        packed["has"] = ["payload"]
        res_obj = {
            "done_ms": 999999.999,
            "dup": False,
            "frame_done": 999999,
            "frame_recv": 999998,
            "op_id": "a1b2c3d4e5f60718-9999",
            "read": packed,
            "reason": "",
            "recv_ms": 999999.0,
            "status": "done",
        }
        raw_bytes = wire.result_wire_bytes(res_obj)
        self.assertLess(len(raw_bytes), wire.WIRE_CAP)

    def test_t6_late_ack_of_ack2_recorded_without_overwriting_new_take_cache(self):
        def _overwrite_cache_with_old_ack(_man, bridge_rows, _scen_rows):
            for ev in bridge_rows:
                if ev.get("ev") != "result":
                    continue
                res = ev.get("result") or {}
                read = res.get("read") or {}
                if not all(k in read for k in wire.PAYLOAD_KEYS):
                    continue
                unp = wire.unpack_payload(read)
                if unp["str"].get("cli_cached_take_id") == "1a2b3c4d-new":
                    unp["str"]["cli_cached_take_id"] = "1a2b3c4d-ack2"
                    unp["str"]["cli_cached_state"] = "parada"
                    repacked = wire.pack_payload(scalars_str=unp["str"], scalars_num=unp["num"])
                    repacked["has"] = ["payload"]
                    res["read"] = repacked

        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run", post_mutate=_overwrite_cache_with_old_ack)
            verdict = s_toma_eval.evaluate(pdir)
            self.assertEqual(verdict["exit_code"], 1)
            tom07 = next(c for c in verdict["checks"] if c["id"] == "TOM-07")
            self.assertEqual(tom07["status"], "fail")
            self.assertIn("t6_old_ack_overwrote_newer_client_cache", tom07["reason"])

    def _assert_mutant_vector(self, mname: str, spec: dict):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / f"mut-{mname}", mutant=mname)
            verdict = s_toma_eval.evaluate(pdir)
            self.assertEqual(verdict["exit_code"], 1, f"{mname}: {verdict}")
            self.assertEqual(verdict["verdict"], "FALLA")
            checks_by_id = {c["id"]: c["status"] for c in verdict["checks"]}
            must_fail = set(spec["must_fail_checks"])
            allowed_non_pass = spec.get("allowed_non_pass") or {}
            for cid in s_toma_eval.CHECK_IDS:
                st = checks_by_id[cid]
                if cid in must_fail:
                    self.assertEqual(st, "fail", f"{mname} debía fallar {cid}: {verdict}")
                elif cid in allowed_non_pass:
                    self.assertIn(st, ["pass"] + list(allowed_non_pass[cid]), f"{mname} {cid}: {verdict}")
                else:
                    self.assertEqual(st, "pass", f"{mname} contaminó {cid}={st}: {verdict}")

    def test_all_11_mutants_and_aggregate_spike(self):
        self.assertEqual(len(s_toma_mutants.EXPECTED_MUTANTS), 11)
        for mname, spec in s_toma_mutants.EXPECTED_MUTANTS.items():
            with self.subTest(mutant=mname):
                self._assert_mutant_vector(mname, spec)

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p_run = build_healthy_part(base / "run", op_nonce="0000000000000001")
            gate_core.write_json(p_run / "verdict.json", s_toma_eval.evaluate(p_run))
            for idx, mname in enumerate(s_toma_mutants.EXPECTED_MUTANTS, start=2):
                p_mut = build_healthy_part(
                    base / f"mut-{mname}",
                    mutant=mname,
                    op_nonce=f"{idx:016x}",
                )
                gate_core.write_json(p_mut / "verdict.json", s_toma_eval.evaluate(p_mut))

            agg = f03_common.aggregate_spike(base, "S-toma")
            self.assertEqual(agg["exit_code"], 0, agg)
            self.assertEqual(agg["verdict"], "PASA")

    def test_inconcluso_cases(self):
        # 1. Calibración de reloj con anchura > 40 ms
        def _wide_clock(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "clock_pair" and r.get("stage") == "S1" and r.get("rep") == 1:
                    r["h_recv_ms"] = float(r["h_send_ms"]) + 65.0

        # 2. Comienzo sin muestra negativa previa (R5-N10)
        def _no_pre_neg_a1(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_srv_observe_start-1a2b3c4d-s1-r1"):
                            rows = [
                                r
                                for r in unp["rows"]
                                if not (r["row_kind"] == "act_sample" and r["subject_id"] == "actor_1" and float(r["v4"]) == 0.0 and float(r["take_dtsum_ms"]) == 0.0)
                            ]
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], rows)
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 3. telemetria_retrasada (R5-N11, T7): hueco de 180 ms tras el comienzo real de actor_2
        def _telemetria_retrasada(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_srv_observe_start-1a2b3c4d-s1-r2"):
                            for r in unp["rows"]:
                                if r["row_kind"] == "act_sample" and r["subject_id"] == "actor_2" and int(r["v7"]) == 13 and int(r["srv_frame"]) < 450:
                                    r["srv_tick_ms"] = float(r["srv_tick_ms"]) + 180.0
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 4. Tecla muerta con cámara Sandbox activa
        def _dead_key(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_cli_watch_start-1a2b3c4d-s2-r1"):
                            rows = [r for r in unp["rows"] if r["row_kind"] != "key_edge"]
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], rows)
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 5. Estímulo de mirada no calibrado (calib_step_deg < 2 * eps_look_deg)
        def _uncalibrated_look(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "run_meta":
                    r["calib_step_deg"] = 0.5
                    r["eps_look_deg"] = 0.5

        # 6. Precondición de gesto pendiente no observada antes del stop
        def _unobserved_pending_gesture(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_srv_observe_start-1a2b3c4d-s1-r1"):
                            for r in unp["rows"]:
                                if r["row_kind"] == "act_sample" and r["subject_id"] == "actor_2":
                                    r["v9"] = 0.0
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 7. Director dañado con allow_damage == 0 (GK-07)
        def _gk07_damage_with_allow_dmg_0(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_srv_observe_start-1a2b3c4d-s1-r1"):
                            for r in unp["rows"]:
                                if r["row_kind"] == "melee_hit":
                                    r["v6"] = 0.0
                                    r["v7"] = 0.5
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 8. Melee solo en bloqueo o Dummy_Light
        def _melee_dummy_light(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_srv_observe_start-1a2b3c4d-s1-r1"):
                            for r in unp["rows"]:
                                if r["row_kind"] == "melee_hit":
                                    r["state_or_origin"] = "Dummy_Light"
                                    r["v10"] = 0.0
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 9. Traza de cámara con FPS insuficientes (< 30 muestras continuas)
        def _low_fps_cam_trace(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_cli_watch_start-1a2b3c4d-s1-r1"):
                            active = [r for r in unp["rows"] if r["row_kind"] == "frame_sample" and int(r["sandbox_cam_active_b"]) == 1]
                            others = [r for r in unp["rows"] if not (r["row_kind"] == "frame_sample" and int(r["sandbox_cam_active_b"]) == 1)]
                            kept = active[:10]
                            if kept:
                                kept[-1]["take_dtsum_ms"] = 2900.0
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], others + kept)
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 10. Vigilancia posterior al stop < 4800 ms
        def _short_post_stop_watch(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_srv_observe_start-1a2b3c4d-s1-r1"):
                            rows = [r for r in unp["rows"] if not (r["row_kind"] == "act_sample" and r["subject_id"] == "actor_2" and float(r["take_dtsum_ms"]) >= 4500.0)]
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], rows)
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # 11. observer_capacity (T2)
        def _observer_capacity(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    res = ev.get("result") or {}
                    res["reason"] = "observer_capacity"
                    break

        # 12. hello con build distinto del de manifest.json
        def _hello_build_mismatch(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "hello":
                    ev["args"]["build"] = "retail"
                    break

        # 13. act_observe sin op="snapshot" (T12)
        def _act_observe_no_snapshot(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") in ("enq", "deliver") and ev.get("verb") == "act_observe":
                    ev["args"] = wire.pack_payload(scalars_str={"op": "other"})

        cases = [
            ("wide_clock", _wide_clock, "TOM-01"),
            ("no_pre_neg_a1", _no_pre_neg_a1, "TOM-01"),
            ("telemetria_retrasada", _telemetria_retrasada, "TOM-01"),
            ("dead_key", _dead_key, "TOM-02"),
            ("uncalibrated_look", _uncalibrated_look, "TOM-02"),
            ("unobserved_pending_gesture", _unobserved_pending_gesture, "TOM-02"),
            ("gk07_damage_with_allow_dmg_0", _gk07_damage_with_allow_dmg_0, "TOM-04"),
            ("melee_dummy_light", _melee_dummy_light, "TOM-04"),
            ("low_fps_cam_trace", _low_fps_cam_trace, "TOM-05"),
            ("short_post_stop_watch", _short_post_stop_watch, "TOM-02"),
            ("observer_capacity", _observer_capacity, "TOM-01"),
            ("hello_build_mismatch", _hello_build_mismatch, "TOM-01"),
            ("act_observe_no_snapshot", _act_observe_no_snapshot, "TOM-01"),
        ]
        for name, mut_fn, expected_missing_cid in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                pdir = build_healthy_part(Path(tmp) / "run", post_mutate=mut_fn)
                verdict = s_toma_eval.evaluate(pdir)
                self.assertEqual(verdict["exit_code"], 2, f"{name}: {verdict}")
                self.assertEqual(verdict["verdict"], "INCONCLUSO")
                checks_by_id = {c["id"]: c["status"] for c in verdict["checks"]}
                self.assertEqual(checks_by_id[expected_missing_cid], "missing", f"{name}: {verdict}")

    def test_anti_fabrication_and_t13_expired_lease_failures(self):
        # E9: dt constante fabricado en todos los frames de cámara
        def _constant_dt(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_cli_watch_start-1a2b3c4d-s1-r1"):
                            t0 = 10000.0
                            for idx, r in enumerate(unp["rows"]):
                                if r["row_kind"] == "frame_sample":
                                    r["cli_tick_ms"] = t0 + idx * 50.0
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # E9: net_id_low/high cero en act_observe
        def _zero_net_id(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("backend_class") == "DSBX_QA_ActorAdapterExp" and unp["rows"]:
                            for r in unp["rows"]:
                                r["net_id_low"] = 0
                                r["net_id_high"] = 0
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep
                            break

        # T13: servidor emite dispatch con lease vencido durante conn_drop_no_effects
        def _srv_expired_lease_op(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_cli_watch_start-1a2b3c4d-cdrop1"):
                            unp["rows"].append(
                                _make_cli_row(945, 172500.0, 2500.0, 0.0, "take_state_recv", "dir_main")
                            )
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        # T13: cliente emite rpc_stop_sent con lease vencido durante cut_after
        def _cli_expired_lease_op(_m, bridge_rows, _s):
            for ev in bridge_rows:
                if ev.get("ev") == "result":
                    read = (ev.get("result") or {}).get("read") or {}
                    if all(k in read for k in wire.PAYLOAD_KEYS):
                        unp = wire.unpack_payload(read)
                        if unp["str"].get("job", "").startswith("job-take_cli_watch_start-1a2b3c4d-cutaft"):
                            unp["rows"].append(
                                _make_cli_row(1525, 210500.0, 2500.0, 2500.0, "rpc_stop_sent", "1a2b3c4d-cutaft")
                            )
                            rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
                            rep["has"] = ["payload"]
                            ev["result"]["read"] = rep

        for name, mut_fn, expected_fail_cid in (
            ("constant_dt", _constant_dt, "TOM-02"),
            ("zero_net_id", _zero_net_id, "TOM-05"),
            ("srv_expired_lease_op", _srv_expired_lease_op, "TOM-06"),
            ("cli_expired_lease_op", _cli_expired_lease_op, "TOM-07"),
        ):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                pdir = build_healthy_part(Path(tmp) / "run", post_mutate=mut_fn)
                verdict = s_toma_eval.evaluate(pdir)
                self.assertEqual(verdict["exit_code"], 1, f"{name}: {verdict}")
                checks_by_id = {c["id"]: c["status"] for c in verdict["checks"]}
                self.assertEqual(checks_by_id[expected_fail_cid], "fail", f"{name}: {verdict}")

    def test_e2e_m1_gate_spike_s_toma_offline(self):
        """Test de punta a punta contra m1_gate.py spike S-toma --both --build offline --part all (en rojo hasta implementar el runner)."""
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "s_toma_e2e"
            rc = m1_gate.main(
                [
                    "spike",
                    "S-toma",
                    "--both",
                    "--build",
                    "offline",
                    "--part",
                    "all",
                    "--out",
                    str(out_dir),
                ]
            )
            self.assertEqual(rc, 0, "m1_gate spike S-toma offline debe terminar en PASA (exit 0)")
            verdict = gate_core.read_json(out_dir / "verdict.json")
            self.assertEqual(verdict["verdict"], "PASA")
            self.assertEqual(verdict["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
