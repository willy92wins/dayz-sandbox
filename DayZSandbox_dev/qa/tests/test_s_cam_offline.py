"""Corrida sana sintetica de S-cam y deteccion ciega de sus 10 mutantes.

La evidencia sale del brief S-cam (§3, §4, §5 y §7) y de las fixtures
``qa/fixtures/s_cam_paths.json`` / ``s_cam_rois.json``; el generador no lee
etiquetas del evaluador. Los mutantes se aplican como efectos sobre
``part_dir/samples`` (el evaluador es ciego a sus nombres).
"""

import argparse
import json
import math
import random
import shutil
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path

import f03_common
import fake_peer
import gate_core
import m1_gate
import s_cam_eval
import s_cam_mutants
import wire
from tests import e2e_witness

QA_DIR = Path(__file__).resolve().parents[1]
FIXTURES = QA_DIR / "fixtures"

W, H = 1280, 720
ANCHOR_Y = 300.0
FRAME_BASE = 1000
TICK_BASE = 5000.0
PATH_COUNT = 361
PATH_DURATION_MS = 6000.0

POSE_SCALARS = ("x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg", "fov_rad")
PATH_KEYS = (
    "seq_n", "frame", "tick_ms", "dtsum_ms",
    "x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg",
    "eng_x_m", "eng_y_m", "eng_z_m", "eng_dx", "eng_dy", "eng_dz",
    "fov_rad", "calc_focus_dist_m", "sent_focus_dist_m", "sent_focus_blur",
    "set_focus_calls_n", "active_b", "elem_vis_mask", "flags_mask",
    "qb_vis_b", "menu_open_b", "ovl_vis_b",
)


def _wrap180(angle):
    return ((float(angle) + 180.0) % 360.0) - 180.0


def _lerp(a, b, u):
    return float(a) + (float(b) - float(a)) * float(u)


def _rot_x(angle):
    c, s = math.cos(angle), math.sin(angle)
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def _rot_y(angle):
    c, s = math.cos(angle), math.sin(angle)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def _rot_z(angle):
    c, s = math.cos(angle), math.sin(angle)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def _mul3(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def ypr_matrix(yaw_deg, pitch_deg, roll_deg):
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    roll = math.radians(float(roll_deg))
    m = _mul3(_mul3(_rot_z(pitch), _rot_y(yaw)), _rot_x(roll))
    return [[m[j][i] for j in range(3)] for i in range(3)]


def matrix_to_quat(m):
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2][1] - m[1][2]) / s
        y = (m[0][2] - m[2][0]) / s
        z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        w = (m[2][1] - m[1][2]) / s
        x = 0.25 * s
        y = (m[0][1] + m[1][0]) / s
        z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        w = (m[0][2] - m[2][0]) / s
        x = (m[0][1] + m[1][0]) / s
        y = 0.25 * s
        z = (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        w = (m[1][0] - m[0][1]) / s
        x = (m[0][2] + m[2][0]) / s
        y = (m[1][2] + m[2][1]) / s
        z = 0.25 * s
    return [x, y, z, w]


def quat_to_matrix(q):
    x, y, z, w = [float(v) for v in q]
    return [
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
        [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
        [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
    ]


def _normalize_quat(q):
    n = math.sqrt(sum(float(v) ** 2 for v in q))
    if n <= 0.0:
        return [0.0, 0.0, 0.0, 1.0]
    return [float(v) / n for v in q]


def _slerp(qa, qb, u):
    qa = _normalize_quat(qa)
    qb = _normalize_quat(qb)
    dot = sum(float(a) * float(b) for a, b in zip(qa, qb))
    if dot < 0.0:
        qb = [-v for v in qb]
        dot = -dot
    dot = max(-1.0, min(1.0, dot))
    if dot > 0.9995:
        return _normalize_quat([_lerp(qa[i], qb[i], u) for i in range(4)])
    omega = math.acos(dot)
    sin_omega = math.sin(omega)
    w1 = math.sin((1.0 - u) * omega) / sin_omega
    w2 = math.sin(u * omega) / sin_omega
    return _normalize_quat([w1 * qa[i] + w2 * qb[i] for i in range(4)])


def _key_table(fixture_path):
    keys = []
    for raw in fixture_path.get("keys") or []:
        keys.append(
            {
                "t_s": float(raw["t_s"]),
                "pos": [
                    float(raw["pos_x_m"]),
                    float(raw["pos_y_rel_m"]),
                    float(raw["pos_z_m"]),
                ],
                "yaw_deg": float(raw["yaw_deg"]),
                "pitch_deg": float(raw["pitch_deg"]),
                "roll_deg": float(raw["roll_deg"]),
                "fov_rad": float(raw["fov_rad"]),
                "focus_dist_m": float(raw["focus_dist_m"]),
                "focus_blur": float(raw["focus_blur"]),
            }
        )
    return keys


def _ref_pos_rel(keys, t_s, pos_mode):
    end = keys[-1]["t_s"]
    t = max(0.0, min(float(t_s), end))
    if pos_mode == "linear":
        for i in range(len(keys) - 1):
            t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
            if t0 <= t <= t1:
                u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
                return [_lerp(keys[i]["pos"][a], keys[i + 1]["pos"][a], u) for a in range(3)]
        return list(keys[-1]["pos"])
    s = 0.0 if end <= 0.0 else t / end
    segs = len(keys) - 1
    seg = min(int(s * segs), segs - 1)
    u = s * segs - seg
    p0 = keys[max(seg - 1, 0)]["pos"]
    p1 = keys[seg]["pos"]
    p2 = keys[seg + 1]["pos"]
    p3 = keys[min(seg + 2, len(keys) - 1)]["pos"]
    out = []
    for a in range(3):
        out.append(
            0.5
            * (
                2.0 * p1[a]
                + (-p0[a] + p2[a]) * u
                + (2.0 * p0[a] - 5.0 * p1[a] + 4.0 * p2[a] - p3[a]) * u * u
                + (-p0[a] + 3.0 * p1[a] - 3.0 * p2[a] + p3[a]) * u * u * u
            )
        )
    return out


def _key_quat(key):
    return matrix_to_quat(
        ypr_matrix(key["yaw_deg"], key["pitch_deg"], key["roll_deg"])
    )


def _ref_quat(keys, t_s):
    end = keys[-1]["t_s"]
    t = max(0.0, min(float(t_s), end))
    for i in range(len(keys) - 1):
        t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
        if t0 <= t <= t1:
            u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return _slerp(_key_quat(keys[i]), _key_quat(keys[i + 1]), u)
    return _key_quat(keys[-1])


def _ref_fov(keys, t_s):
    end = keys[-1]["t_s"]
    t = max(0.0, min(float(t_s), end))
    for i in range(len(keys) - 1):
        t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
        if t0 <= t <= t1:
            u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return _lerp(keys[i]["fov_rad"], keys[i + 1]["fov_rad"], u)
    return keys[-1]["fov_rad"]


def _ref_focus(keys, t_s):
    end = keys[-1]["t_s"]
    t = max(0.0, min(float(t_s), end))
    for i in range(len(keys) - 1):
        t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
        if t0 <= t <= t1:
            u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return (
                _lerp(keys[i]["focus_dist_m"], keys[i + 1]["focus_dist_m"], u),
                _lerp(keys[i]["focus_blur"], keys[i + 1]["focus_blur"], u),
            )
    return keys[-1]["focus_dist_m"], keys[-1]["focus_blur"]


def _short_arc_euler(t_s):
    if t_s <= 3.0:
        u = t_s / 3.0
        return (
            _wrap180(179.0 + 2.0 * u),
            _lerp(-4.0, 0.0, u),
            _lerp(0.0, 6.0, u),
        )
    u = (t_s - 3.0) / 3.0
    return (-179.0 + 160.0 * u, _lerp(0.0, 3.0, u), _lerp(6.0, 0.0, u))


def _linear_hud_euler(t_s):
    if t_s <= 3.0:
        u = t_s / 3.0
        return (_lerp(0.0, 15.0, u), _lerp(0.0, -2.0, u), 0.0)
    u = (t_s - 3.0) / 3.0
    return (_lerp(15.0, 30.0, u), _lerp(-2.0, 0.0, u), 0.0)


def _path_rows(fixture_name, pos_mode, orientation, euler_mode, duration_ms):
    fixtures = _load_json(FIXTURES / "s_cam_paths.json")
    keys = _key_table(fixtures["paths"][fixture_name])
    dt = duration_ms / float(PATH_COUNT - 1)
    rows = []
    for i in range(PATH_COUNT):
        t = min(i * dt / 1000.0, keys[-1]["t_s"])
        rel = _ref_pos_rel(keys, t, pos_mode)
        pos = [rel[0], ANCHOR_Y + rel[1], rel[2]]
        if orientation == "slerp":
            m = quat_to_matrix(_ref_quat(keys, t))
            yaw, pitch, roll = _short_arc_euler(t) if euler_mode == "short_arc" else (0.0, 0.0, 0.0)
        else:
            yaw, pitch, roll = _linear_hud_euler(t)
            m = ypr_matrix(yaw, pitch, roll)
        fd, fb = _ref_focus(keys, t)
        fov = _ref_fov(keys, t)
        values = [
            float(i),
            float(FRAME_BASE + i),
            float(TICK_BASE + i * dt),
            float(i * dt),
            pos[0],
            pos[1],
            pos[2],
            yaw,
            pitch,
            roll,
            pos[0],
            pos[1],
            pos[2],
            m[2][0],
            m[2][1],
            m[2][2],
            fov,
            fd,
            fd,
            fb,
            float(i),
            1.0,
            0.0,
            391.0,
            0.0,
            0.0,
            0.0,
        ]
        row = dict(zip(PATH_KEYS, values))
        for r in range(3):
            for c in range(3):
                row[f"m{r}{c}"] = m[r][c]
        rows.append(row)
    return rows


def _dof_rows(fixture_name):
    fixtures = _load_json(FIXTURES / "s_cam_paths.json")
    keys = _key_table(fixtures["paths"][fixture_name])
    dt = PATH_DURATION_MS / float(PATH_COUNT - 1)
    anchor = fixtures["anchor_pose"]
    m = ypr_matrix(anchor["yaw_deg"], anchor["pitch_deg"], anchor["roll_deg"])
    rows = []
    for i in range(PATH_COUNT):
        t = min(i * dt / 1000.0, keys[-1]["t_s"])
        fd, fb = _ref_focus(keys, t)
        values = [
            float(i),
            float(FRAME_BASE + i),
            float(TICK_BASE + i * dt),
            float(i * dt),
            float(anchor["anchor_x_m"]),
            ANCHOR_Y,
            float(anchor["anchor_z_m"]),
            float(anchor["yaw_deg"]),
            float(anchor["pitch_deg"]),
            float(anchor["roll_deg"]),
            float(anchor["anchor_x_m"]),
            ANCHOR_Y,
            float(anchor["anchor_z_m"]),
            m[2][0],
            m[2][1],
            m[2][2],
            float(anchor["fov_rad"]),
            fd,
            fd,
            fb,
            float(i),
            1.0,
            0.0,
            391.0,
            0.0,
            0.0,
            0.0,
        ]
        row = dict(zip(PATH_KEYS, values))
        for r in range(3):
            for c in range(3):
                row[f"m{r}{c}"] = m[r][c]
        rows.append(row)
    return rows


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")


def _read_jsonl(path):
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pose_nk(
    x,
    y,
    z,
    yaw,
    pitch,
    roll,
    fov,
    *,
    active=1.0,
    enable=0.0,
    sent_dist=0.0,
    sent_blur=0.0,
    calls=0.0,
    saved_count=0.0,
    speed=0.0,
    speed_steps=0.0,
    input_frames=0.0,
    integrated=0.0,
    input_ack=0.0,
    cam_dtsum=0.0,
    frame=FRAME_BASE,
    tick=TICK_BASE,
    elem=0.0,
    flags=0.0,
    saved_flags=0.0,
    aux=0.0,
    saved_aux=0.0,
    qb=0.0,
    qb_items=1.0,
    menu=0.0,
    ovl=0.0,
):
    m = ypr_matrix(yaw, pitch, roll)
    nk = {
        "frame": float(frame),
        "tick_ms": float(tick),
        "cam_dtsum_ms": float(cam_dtsum),
        "active_b": float(active),
        "enable_b": float(enable),
        "sent_focus_dist_m": float(sent_dist),
        "sent_focus_blur": float(sent_blur),
        "set_focus_calls_n": float(calls),
        "saved_count_n": float(saved_count),
        "speed_mps": float(speed),
        "speed_steps_n": float(speed_steps),
        "input_frames_n": float(input_frames),
        "integrated_dt_s": float(integrated),
        "input_ack_seq_n": float(input_ack),
        "x_m": float(x),
        "y_m": float(y),
        "z_m": float(z),
        "yaw_deg": float(yaw),
        "pitch_deg": float(pitch),
        "roll_deg": float(roll),
        "fov_rad": float(fov),
        "eng_x_m": float(x),
        "eng_y_m": float(y),
        "eng_z_m": float(z),
        "eng_dx": m[2][0],
        "eng_dy": m[2][1],
        "eng_dz": m[2][2],
        "elem_vis_mask": float(elem),
        "flags_mask": float(flags),
        "saved_flags_mask": float(saved_flags),
        "aux_vis_mask": float(aux),
        "saved_aux_vis_mask": float(saved_aux),
        "qb_vis_b": float(qb),
        "qb_items_n": float(qb_items),
        "menu_open_b": float(menu),
        "ovl_vis_b": float(ovl),
    }
    for r in range(3):
        for c in range(3):
            nk[f"m{r}{c}"] = m[r][c]
    return nk


def _state(phase, step, nk, sk=None):
    return {
        "ev": "state",
        "phase": phase,
        "step": step,
        "t_ms": 0.0,
        "h_ms": 0.0,
        "read_nk": nk,
        "read_sk": dict(sk or {}),
    }


def _op(phase, step, verb, status, reason="", nk=None, sk=None):
    return {
        "ev": "op",
        "phase": phase,
        "step": step,
        "verb": verb,
        "role": "client",
        "op_id": f"{phase}-{step}",
        "status": status,
        "reason": reason,
        "recv_ms": 0.0,
        "done_ms": 0.0,
        "read_nk": dict(nk or {}),
        "read_sk": dict(sk or {}),
    }


def _capture(phase, step, file_name, pre_step, post_step):
    return {
        "ev": "capture",
        "phase": phase,
        "step": step,
        "file": file_name,
        "window_w": W,
        "window_h": H,
        "pre_step": pre_step,
        "post_step": post_step,
        "capture_tick_ms": 0.0,
        "capture_h_ms": 0.0,
    }


def _scenario():
    rows = []

    rows.append(
        {
            "ev": "wire_nan",
            "phase": "SCAM-S1",
            "step": "wire",
            "nan_rejected_b": True,
            "inf_rejected_b": True,
            "bridge_lines_delta": 0,
        }
    )
    rows.append(_op("SCAM-S0", "fixture", "scam_fixture_setup", "done", nk={"player_in_veh_b": 0.0, "qb_items_n": 1.0}))
    rows.append(
        {
            "ev": "dof_config",
            "phase": "SCAM-S0",
            "step": "dof_config",
            "accredited_b": True,
            "mode": "offline",
            "window_w": W,
            "window_h": H,
            "mad_bg_50m": 10.0,
        }
    )

    anchor = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70)

    closed = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, active=0.0)
    rows.append(_state("SCAM-S1", "pre_0", closed))
    rows.append(_op("SCAM-S1", "neg_0", "scam_pose_apply", "rejected", "no_active_cam"))
    rows.append(_state("SCAM-S1", "post_0", closed))

    neg_reasons = {
        "neg_1": "empty_name",
        "neg_2": "duplicate_name",
        "neg_3": "unknown_pose",
        "neg_4": "bad_args",
        "neg_5": "bad_args",
    }
    for step, reason in neg_reasons.items():
        idx = step.split("_")[1]
        nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, saved_count=2.0)
        rows.append(_state("SCAM-S1", f"pre_{idx}", nk, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))
        rows.append(_op("SCAM-S1", step, "scam_pose_apply", "rejected", reason))
        rows.append(_state("SCAM-S1", f"post_{idx}", nk, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))

    s_init = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, speed=4.0)
    s_a = _pose_nk(4500.0, ANCHOR_Y, 9802.0, 0.0, 0.0, 0.0, 0.70, speed=4.0, integrated=0.5, input_frames=30.0)
    s_b = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 0.0, 0.0, 0.0, 0.70, speed=8.0, speed_steps=1.0, integrated=1.0, input_frames=60.0)
    s_0 = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 25.0, 15.0, 0.0, 0.70, speed=8.0, speed_steps=1.0, integrated=1.3, input_frames=90.0)
    moved = _pose_nk(4520.0, ANCHOR_Y, 9806.0, 60.0, 15.0, 0.0, 0.70, speed=8.0, speed_steps=1.0, integrated=1.6, input_frames=120.0)
    p_roll = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 35.0, -12.0, 18.0, 0.85)
    p0 = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 25.0, 15.0, 0.0, 0.70)
    rows.append(_state("SCAM-S1", "s_init", s_init))
    rows.append(_state("SCAM-S1", "s_a", s_a))
    rows.append(_state("SCAM-S1", "s_b", s_b))
    rows.append(_state("SCAM-S1", "s_0", s_0))
    rows.append(_state("SCAM-S1", "moved", moved))
    rows.append(_state("SCAM-S1", "p_roll_applied", p_roll))
    rows.append(_state("SCAM-S1", "p0_applied", p0))

    for step in ("neg_1", "neg_2", "neg_3", "neg_4", "neg_5", "neg_6"):
        idx = step.split("_")[1]
        nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, saved_count=2.0)
        rows.append(_state("SCAM-S2", f"pre_{idx}", nk, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))
        rows.append(_op("SCAM-S2", step, "scam_path_start", "rejected", "bad_args"))
        rows.append(_state("SCAM-S2", f"post_{idx}", nk, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))

    busy_nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, cam_dtsum=900.0)
    rows.append(_state("SCAM-S2", "busy_pre", busy_nk, {"cam_job_id": "job-1", "cam_job_state": "running"}))
    rows.append(_op("SCAM-S2", "busy_attempt", "scam_path_start", "rejected", "busy"))
    rows.append(_state("SCAM-S2", "busy_post", busy_nk, {"cam_job_id": "job-1", "cam_job_state": "running"}))

    pre_cap = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, cam_dtsum=2000.0, aux=0.0)
    post_cap = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, cam_dtsum=2010.0, aux=0.0)
    rows.append(_state("SCAM-S3", "pre_cap", pre_cap, {"cam_job_state": "running"}))
    rows.append(_state("SCAM-S3", "post_cap", post_cap, {"cam_job_state": "running"}))
    rows.append(_capture("SCAM-S3", "hud_during", "hud_during.bmp", "pre_cap", "post_cap"))
    clean_ref = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, cam_dtsum=2010.0, aux=0.0)
    rows.append(_state("SCAM-S3", "clean_ref_state", clean_ref, {"cam_job_state": ""}))
    post_path_hud = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, flags=258.0, saved_flags=258.0, aux=1.0, saved_aux=1.0)
    rows.append(_state("SCAM-S3", "post_path_hud", post_path_hud, {"cam_job_state": ""}))
    rows.append({"ev": "hud_control", "phase": "SCAM-S3", "step": "control_qb", "op_code": 4, "mode": 1, "read_nk": {"qb_vis_b": 1.0}})
    rows.append({"ev": "hud_control", "phase": "SCAM-S3", "step": "control_ovl", "op_code": 4, "mode": 2, "read_nk": {"ovl_vis_b": 1.0}})

    for j in range(1, 5):
        nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, enable=1.0, sent_dist=3.5, sent_blur=0.6, calls=5.0)
        rows.append(_state("SCAM-S4", f"pre_{j}", nk))
        rows.append(_op("SCAM-S4", f"neg_{j}", "scam_dof_set", "rejected", "bad_args"))
        rows.append(_state("SCAM-S4", f"post_{j}", nk))

    for name in ("noblur", "near2m", "far50m"):
        nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70)
        rows.append(_state("SCAM-S4", f"ctrl_{name}_pre", nk))
        rows.append(_state("SCAM-S4", f"ctrl_{name}_post", nk))
        rows.append(
            _capture(
                "SCAM-S4",
                f"ctrl_{name}",
                f"dof_ctrl_{name}.bmp",
                f"ctrl_{name}_pre",
                f"ctrl_{name}_post",
            )
        )
    rows.append(_state("SCAM-S4", "post_reset", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70)))

    phases = {
        1: (0.0, 50.0),
        2: (1400.0, 1500.0),
        3: (2900.0, 3000.0),
        4: (5700.0, 5800.0),
    }
    for path in ("dof_var_6s", "dof_fixed_6s"):
        for k, (pre, post) in phases.items():
            rows.append(
                {
                    "ev": "phase",
                    "phase": "SCAM-S4",
                    "step": f"{path}_t{k}",
                    "path": path,
                    "phase_k": k,
                    "pre_step": f"{path}_t{k}_pre",
                    "post_step": f"{path}_t{k}_post",
                    "pre_dtsum_ms": pre,
                    "post_dtsum_ms": post,
                }
            )
    rows.append(_state("SCAM-S4", "post_dof_var", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70)))

    rows.append(
        {
            "ev": "stop",
            "phase": "SCAM-S5",
            "step": "stop",
            "job_id": "cam-job",
            "stop_send_h_ms": 500.0,
            "stop_ack_h_ms": 550.0,
            "stop_recv_ms": 1000.0,
            "stop_done_ms": 560.0,
            "u_ms": 50.0,
        }
    )
    for i in range(5):
        rows.append({"ev": "pulse", "phase": "SCAM-S5", "step": f"a{i}", "burst": "A", "seq_n": i, "dx_px": 40.0, "issued_h_ms": 650.0 + 40.0 * i, "kind": "mouse_move"})
    for i in range(5):
        rows.append({"ev": "pulse", "phase": "SCAM-S5", "step": f"b{i}", "burst": "B", "seq_n": 10 + i, "dx_px": -40.0, "issued_h_ms": 890.0 + 40.0 * i, "kind": "mouse_move"})
    post_stop = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, flags=258.0, saved_flags=258.0, aux=1.0, saved_aux=1.0)
    rows.append(_state("SCAM-S5", "post_stop_state", post_stop))

    return rows


def _control_recovery():
    rows = []
    tick = 1000.0
    frame = 5000.0
    while tick <= 1600.0:
        if tick < 1100.0:
            psi = 0.0
        elif tick < 1200.0:
            psi = 5.0
        elif tick < 1340.0:
            psi = 8.0
        else:
            psi = -2.0
        dx = math.sin(math.radians(psi))
        dz = math.cos(math.radians(psi))
        rows.append(
            [
                float(len(rows)),
                frame,
                tick,
                tick - 1000.0,
                4500.0,
                ANCHOR_Y,
                9800.0,
                dx,
                0.0,
                dz,
                0.70,
                4500.0,
                ANCHOR_Y,
                9800.0,
                dx,
                0.0,
                dz,
                0.0,
            ]
        )
        tick += 16.0
        frame += 1.0
    return rows


def _slow_stop_recovery():
    """Control recuperado 1500 ms tarde (qa_fault cam_slow_stop): los pulsos A/B llegan
    durante el bloqueo y solo se aplican tras PlayerControlEnable(true)."""
    rows = []
    tick = 1000.0
    frame = 5000.0
    while tick <= 2600.0:
        if tick < 2450.0:
            psi = 0.0
        elif tick < 2550.0:
            psi = 5.0
        else:
            psi = -2.0
        dx = math.sin(math.radians(psi))
        dz = math.cos(math.radians(psi))
        rows.append(
            [
                float(len(rows)),
                frame,
                tick,
                tick - 1000.0,
                4500.0,
                ANCHOR_Y,
                9800.0,
                dx,
                0.0,
                dz,
                0.70,
                4500.0,
                ANCHOR_Y,
                9800.0,
                dx,
                0.0,
                dz,
                0.0,
            ]
        )
        tick += 16.0
        frame += 1.0
    return rows


def _write_bmp(path, img):
    stride = W * 3
    header = bytearray()
    header += b"BM"
    header += struct.pack("<IHHI", 54 + stride * H, 0, 0, 54)
    header += struct.pack("<IiiHHIIiiII", 40, W, H, 1, 24, 0, stride * H, 2835, 2835, 0, 0)
    out = bytearray(header)
    for y in range(H - 1, -1, -1):
        src = img[y * W : (y + 1) * W]
        row = bytearray(stride)
        row[0::3] = src
        row[1::3] = src
        row[2::3] = src
        out.extend(row)
    Path(path).write_bytes(bytes(out))


def _noise_image(seed=1234):
    return bytearray(random.Random(seed).randbytes(W * H))


def _blur_region(img, roi, passes=2):
    out = bytearray(img)
    x0 = max(1, int(round(float(roi[0]) * W)) - 6)
    y0 = max(1, int(round(float(roi[1]) * H)) - 6)
    x1 = min(W - 1, int(round(float(roi[2]) * W)) + 6)
    y1 = min(H - 1, int(round(float(roi[3]) * H)) + 6)
    for _ in range(passes):
        src = bytearray(out)
        for y in range(y0, y1):
            base = y * W
            for x in range(x0, x1):
                total = 0
                for dy in (-1, 0, 1):
                    row = (y + dy) * W
                    for dx in (-1, 0, 1):
                        total += src[row + x + dx]
                out[base + x] = total // 9
    return out


def _paint_region(img, roi, value):
    out = bytearray(img)
    x0 = int(round(float(roi[0]) * W))
    y0 = int(round(float(roi[1]) * H))
    x1 = int(round(float(roi[2]) * W))
    y1 = int(round(float(roi[3]) * H))
    for y in range(y0, y1):
        out[y * W + x0 : y * W + x1] = bytes([value]) * (x1 - x0)
    return out


def _write_images(samples):
    rois = _load_json(FIXTURES / "s_cam_rois.json")
    roi_bg = rois["roi_bg_50m"]
    roi_qb = rois["roi_quickbar"]
    noise = _noise_image()
    blurred = _blur_region(noise, roi_bg)
    hud = _noise_image(4321)
    hud_visible = _paint_region(hud, roi_qb, 200)

    files = {
        "dof_before_reject.bmp": noise,
        "dof_after_reject_1.bmp": noise,
        "dof_after_reject_2.bmp": noise,
        "dof_after_reject_3.bmp": noise,
        "dof_after_reject_4.bmp": noise,
        "dof_ctrl_noblur.bmp": noise,
        "dof_ctrl_noblur_repeat.bmp": noise,
        "dof_ctrl_near2m.bmp": blurred,
        "dof_ctrl_far50m.bmp": noise,
        "var_t1.bmp": blurred,
        "fix_t1.bmp": noise,
        "var_t2.bmp": blurred,
        "fix_t2.bmp": noise,
        "var_t3.bmp": noise,
        "fix_t3.bmp": noise,
        "var_t4.bmp": blurred,
        "fix_t4.bmp": noise,
        "hud_during.bmp": hud,
        "hud_clean_ref.bmp": hud,
        "hud_clean_ref_repeat.bmp": hud,
        "hud_visible_ref.bmp": hud_visible,
    }
    for name, img in files.items():
        _write_bmp(samples / name, img)


def write_healthy(part_dir):
    part_dir = Path(part_dir)
    samples = part_dir / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    _write_jsonl(samples / "scenario.jsonl", _scenario())
    _write_jsonl(samples / "path_catmull_scripted.jsonl", _path_rows("short_arc_6s", "catmull_rom", "slerp", "short_arc", PATH_DURATION_MS))
    _write_jsonl(samples / "path_linear_hud.jsonl", _path_rows("linear_hud_6s", "linear", "ypr", "linear_hud", PATH_DURATION_MS))
    _write_jsonl(samples / "path_engine_interp.jsonl", _path_rows("short_arc_6s", "linear", "slerp", "short_arc", PATH_DURATION_MS))
    _write_jsonl(samples / "path_dof_var.jsonl", _dof_rows("dof_var_6s"))
    _write_jsonl(samples / "path_dof_fix.jsonl", _dof_rows("dof_fixed_6s"))
    _write_jsonl(samples / "control_recovery.jsonl", _control_recovery())
    _write_images(samples)
    _write_json(
        part_dir / "manifest.json",
        {
            "build": "offline",
            "both": True,
            "id": "S-cam",
            "kind": "run",
            "schema": "dsbx-qa-manifest/1",
            "params": {
                "seed": 1,
                "ttl_ms": 5000,
                "lease_ms": 2000,
                "hold_ms": 100,
                "retry_ms": 100,
                "port": 0,
            },
            "identity": {
                "git_head": "0" * 40,
                "git_dirty": False,
                "peer_builds": {"client": "offline"},
                "probe_stamp": "0" * 16,
                "params": {"wire_cap": 3500, "lease_ms": 2000},
            },
        },
    )
    return part_dir


def _rewrite_jsonl(path, mutate):
    rows = _read_jsonl(path)
    mutate(rows)
    _write_jsonl(path, rows)


def apply_mutant(part_dir, name):
    part_dir = Path(part_dir)
    samples = part_dir / "samples"
    scenario_path = samples / "scenario.jsonl"

    if name == "inactive_cam":
        def mutate(rows):
            for row in rows:
                if row.get("ev") == "state" and row.get("phase") == "SCAM-S1" and row.get("step") == "p0_applied":
                    row["read_nk"]["active_b"] = 0.0
        _rewrite_jsonl(scenario_path, mutate)
        return

    if name == "swap_axes":
        def mutate(rows):
            for row in rows:
                if row.get("ev") == "state" and row.get("phase") == "SCAM-S1" and row.get("step") == "p0_applied":
                    nk = row["read_nk"]
                    nk["yaw_deg"], nk["pitch_deg"] = nk["pitch_deg"], nk["yaw_deg"]
                    m = ypr_matrix(nk["yaw_deg"], nk["pitch_deg"], nk["roll_deg"])
                    for r in range(3):
                        for c in range(3):
                            nk[f"m{r}{c}"] = m[r][c]
        _rewrite_jsonl(scenario_path, mutate)
        return

    if name == "long_arc":
        def mutate(rows):
            for row in rows:
                t = row["dtsum_ms"] / 1000.0
                if t <= 3.0:
                    row["yaw_deg"] = _wrap180(179.0 - 358.0 * (t / 3.0))
        _rewrite_jsonl(samples / "path_catmull_scripted.jsonl", mutate)
        return

    if name == "frozen_fov":
        def mutate(rows):
            for row in rows:
                row["fov_rad"] = 0.65
        _rewrite_jsonl(samples / "path_catmull_scripted.jsonl", mutate)
        return

    if name == "path_jump":
        def mutate(rows):
            for row in rows:
                if row["dtsum_ms"] >= 3000.0:
                    row["x_m"] += 2.0
                    row["eng_x_m"] += 2.0
        _rewrite_jsonl(samples / "path_catmull_scripted.jsonl", mutate)
        return

    if name == "late_finish":
        rows = _read_jsonl(samples / "path_catmull_scripted.jsonl")
        last = dict(rows[-1])
        dt = last["dtsum_ms"] / max(1.0, last["seq_n"])
        seq = last["seq_n"]
        frame = last["frame"]
        tick = last["tick_ms"]
        dtsum = last["dtsum_ms"]
        while dtsum < 7000.0:
            seq += 1.0
            frame += 1.0
            tick += dt
            dtsum = min(7000.0, dtsum + dt)
            row = dict(last)
            row["seq_n"] = seq
            row["frame"] = frame
            row["tick_ms"] = tick
            row["dtsum_ms"] = dtsum
            rows.append(row)
        _write_jsonl(samples / "path_catmull_scripted.jsonl", rows)
        return

    if name == "ignore_focus_keys":
        def mutate(rows):
            for row in rows:
                row["sent_focus_dist_m"] = 2.0
                row["sent_focus_blur"] = 1.0
        _rewrite_jsonl(samples / "path_dof_var.jsonl", mutate)

        def mutate_states(rows):
            for row in rows:
                if row.get("ev") == "state" and row.get("phase") == "SCAM-S4" and row.get("step") == "post_dof_var":
                    row["read_nk"]["sent_focus_dist_m"] = 2.0
                    row["read_nk"]["sent_focus_blur"] = 1.0
        _rewrite_jsonl(scenario_path, mutate_states)
        return

    if name == "dof_off":
        src = samples / "dof_ctrl_noblur.bmp"
        shutil.copyfile(src, samples / "dof_ctrl_near2m.bmp")

        def mutate(rows):
            for row in rows:
                if row.get("ev") == "state" and row.get("phase") == "SCAM-S4" and str(row.get("step", "")).startswith("ctrl_near2m"):
                    row["read_nk"]["sent_focus_blur"] = 0.0
        _rewrite_jsonl(scenario_path, mutate)
        return

    if name == "hud_leak":
        def mutate(rows):
            for row in rows:
                if row["dtsum_ms"] >= 1800.0:
                    row["qb_vis_b"] = 1.0
                    row["ovl_vis_b"] = 1.0
        _rewrite_jsonl(samples / "path_linear_hud.jsonl", mutate)
        return

    if name == "hud_restore_corrupt":
        def mutate(rows):
            for row in rows:
                if row.get("ev") == "state" and row.get("phase") == "SCAM-S3" and row.get("step") == "post_path_hud":
                    row["read_nk"]["flags_mask"] = 0.0
        _rewrite_jsonl(scenario_path, mutate)
        return

    raise KeyError(f"unknown mutant: {name}")


def _samples(part_dir):
    return Path(part_dir) / "samples"


def _scenario_path(part_dir):
    return _samples(part_dir) / "scenario.jsonl"


def _set_event(part_dir, ev, phase, step, **changes):
    def mutate(rows):
        for row in rows:
            if row.get("ev") == ev and row.get("phase") == phase and row.get("step") == step:
                row.update(changes)

    _rewrite_jsonl(_scenario_path(part_dir), mutate)


def _set_state_nk(part_dir, phase, step, **changes):
    def mutate(rows):
        for row in rows:
            if row.get("ev") == "state" and row.get("phase") == phase and row.get("step") == step:
                row.setdefault("read_nk", {}).update(changes)

    _rewrite_jsonl(_scenario_path(part_dir), mutate)


def _mutate_path(part_dir, name, mutate):
    _rewrite_jsonl(_samples(part_dir) / f"{name}.jsonl", mutate)


def _checks_by_id(verdict):
    return {check["id"]: check for check in verdict["checks"]}


def _neg_wire_nan(part_dir):
    _set_event(part_dir, "wire_nan", "SCAM-S1", "wire", nan_rejected_b=False)


def _neg_p_roll_inactive(part_dir):
    _set_state_nk(part_dir, "SCAM-S1", "p_roll_applied", active_b=0.0)


def _neg_path_inactive(part_dir):
    def mutate(rows):
        rows[50]["active_b"] = 0.0

    _mutate_path(part_dir, "path_catmull_scripted", mutate)


def _neg_finish_late(part_dir):
    """Extiende el recorrido hasta 6301 ms con filas identicas a la ultima clave, sin
    cambiar la trayectoria: solo CAM-04 cae por el fin fuera de [6000, 6300]."""
    path = _samples(part_dir) / "path_catmull_scripted.jsonl"
    rows = _read_jsonl(path)
    last = dict(rows[-1])
    dt = last["dtsum_ms"] / max(1.0, last["seq_n"])
    seq = last["seq_n"]
    frame = last["frame"]
    tick = last["tick_ms"]
    dtsum = last["dtsum_ms"]
    while dtsum < 6301.0:
        seq += 1.0
        frame += 1.0
        tick += dt
        dtsum = min(6301.0, dtsum + dt)
        row = dict(last)
        row["seq_n"] = seq
        row["frame"] = frame
        row["tick_ms"] = tick
        row["dtsum_ms"] = dtsum
        rows.append(row)
    _write_jsonl(path, rows)


def _neg_fov_off_lerp(part_dir):
    def mutate(rows):
        rows[120]["fov_rad"] = 0.5

    _mutate_path(part_dir, "path_catmull_scripted", mutate)


def _neg_dof_reject_accepted(part_dir):
    _set_event(part_dir, "op", "SCAM-S4", "neg_1", status="done", reason="")


def _neg_dof_identical_frames(part_dir):
    samples = _samples(part_dir)
    shutil.copyfile(samples / "dof_ctrl_noblur.bmp", samples / "dof_ctrl_near2m.bmp")


def _neg_focus_blur_wrong(part_dir):
    def mutate(rows):
        rows[10]["sent_focus_blur"] = 0.0

    _mutate_path(part_dir, "path_dof_var", mutate)


def _neg_elem_visible(part_dir):
    def mutate(rows):
        rows[5]["elem_vis_mask"] = 1.0

    _mutate_path(part_dir, "path_linear_hud", mutate)


def _neg_burst_a_wrong_sign(part_dir):
    def mutate(rows):
        for row in rows:
            if row.get("ev") == "pulse" and row.get("phase") == "SCAM-S5" and row.get("burst") == "A":
                row["dx_px"] = -40.0

    _rewrite_jsonl(_scenario_path(part_dir), mutate)


# E9 (regla 4 de ENCARGO_original.md §3): negativas contra la fabricacion.
# Cada una tiene que dar FALLA o INCONCLUSO, nunca PASA.
def _fab_echo_requested_pose(part_dir):
    """La pose leida copia la pedida (P_roll) pero el motor sigue en la pose anterior."""
    _set_state_nk(part_dir, "SCAM-S1", "p_roll_applied", eng_x_m=4520.0, eng_y_m=ANCHOR_Y, eng_z_m=9806.0)


def _fab_echo_requested_path(part_dir):
    """El motor publica la trayectoria pedida, pero el nodo de camara no se movio del ancla."""
    def mutate(rows):
        for row in rows:
            row["x_m"] = 4500.0
            row["y_m"] = ANCHOR_Y
            row["z_m"] = 9800.0

    _mutate_path(part_dir, "path_catmull_scripted", mutate)


def _fab_identical_capture(part_dir):
    """Capturas identicas: el control sin blur se copia como si fuera el de 2 m."""
    samples = _samples(part_dir)
    shutil.copyfile(samples / "dof_ctrl_noblur.bmp", samples / "dof_ctrl_near2m.bmp")


def _fab_expected_metrics_instead_of_calculated(part_dir):
    """El runner publica un hash y una MAD esperados; el BMP calculado dice otra cosa."""
    samples = _samples(part_dir)
    shutil.copyfile(samples / "dof_ctrl_noblur.bmp", samples / "hud_clean_ref.bmp")
    shutil.copyfile(samples / "dof_ctrl_noblur.bmp", samples / "hud_clean_ref_repeat.bmp")

    def mutate(rows):
        for row in rows:
            if row.get("ev") == "capture" and row.get("file") == "hud_clean_ref.bmp":
                row["sha256"] = "0" * 64
                row["mad_full_screen"] = 0.0

    _rewrite_jsonl(_scenario_path(part_dir), mutate)


def _fab_hud_restored_without_widget_tree(part_dir):
    """El HUD se da por restaurado copiando saved_flags_mask, pero los auxiliares no vuelven."""
    _set_state_nk(part_dir, "SCAM-S3", "post_path_hud", aux_vis_mask=0.0, saved_aux_vis_mask=1.0)


CAM_STANDIN_VERBS = frozenset(
    {
        "scam_fixture_setup",
        "scam_state_read",
        "scam_free_op",
        "scam_pose_save",
        "scam_pose_apply",
        "scam_path_start",
        "scam_dof_set",
        "scam_hud_op",
        "scam_sample_start",
    }
)
CAM_STANDIN_COLS = ("seq_n", "dtsum_ms", "active_b")


def _cam_standin_module():
    """Homologo minimo de fake_ext_cam para la negativa E1 del peer falso.

    Modela la guarda del lease antes de cada efecto, el trabajo "cam" con
    deadman="stop", el bloqueo de efectos fuera de trabajo y la limpieza que
    corre siempre (soltar la camara y restaurar el HUD). El esqueleto real de
    S-cam aun no entiende los verbos scam_*; el e2e de E1 usa el de verdad.
    """

    class CamStandIn(fake_peer.FakeExt):
        def __init__(self):
            super().__init__()
            self.peer = None
            self.jobs = None
            self.active = 0.0
            self.pose = {
                "x_m": 4500.0,
                "y_m": ANCHOR_Y,
                "z_m": 9800.0,
                "yaw_deg": 0.0,
                "pitch_deg": 0.0,
                "roll_deg": 0.0,
                "fov_rad": 0.70,
            }
            self.saved = {}
            self.saved_names = []
            self.flags = 0.0
            self.saved_flags = 0.0
            self.aux = 0.0
            self.saved_aux = 0.0
            self.focus_dist = 0.0
            self.focus_blur = 0.0
            self.focus_calls = 0.0
            self.cam_job_id = ""
            self.sample_job_id = ""
            self.dtsum = 0.0
            self.duration_ms = 0.0
            self.seq = 0.0

        def init(self, peer, jobs):
            self.peer = peer
            self.jobs = jobs

        def handles(self, verb, role):
            return role == "client" and verb in CAM_STANDIN_VERBS

        def _read(self):
            nk = dict(self.pose)
            nk.update(
                {
                    "active_b": self.active,
                    "enable_b": 1.0 if self.focus_dist > 0.0 else 0.0,
                    "flags_mask": self.flags,
                    "saved_flags_mask": self.saved_flags,
                    "aux_vis_mask": self.aux,
                    "saved_aux_vis_mask": self.saved_aux,
                    "sent_focus_dist_m": self.focus_dist,
                    "sent_focus_blur": self.focus_blur,
                    "set_focus_calls_n": self.focus_calls,
                    "cam_dtsum_ms": self.dtsum,
                    "speed_mps": 4.0,
                }
            )
            sk = {
                "cam_job_id": self.cam_job_id,
                "cam_job_state": self.jobs.get_state(self.cam_job_id) if self.cam_job_id else "",
                "sample_job_id": self.sample_job_id,
                "sample_job_state": self.jobs.get_state(self.sample_job_id) if self.sample_job_id else "",
                "saved_names_csv": ",".join(self.saved_names),
            }
            return wire.pack_payload(
                scalars_str=sk,
                scalars_num={key: float(value) for key, value in nk.items()},
            )

        def _cleanup(self):
            self.active = 0.0
            self.flags = self.saved_flags
            self.aux = self.saved_aux
            self.focus_dist = 0.0
            self.focus_blur = 0.0

        def _hide(self):
            self.saved_flags = self.flags
            self.saved_aux = self.aux
            self.flags = 391.0
            self.aux = 0.0

        def _pose_from(self, nums):
            for key in ("x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg", "fov_rad"):
                if key in nums:
                    self.pose[key] = float(nums[key])

        def on_start_op(self, op, args_unpacked, raw_args):
            verb = op["verb"]
            strs = args_unpacked.get("str") or {}
            nums = args_unpacked.get("num") or {}
            rows = args_unpacked.get("rows") or []
            if verb == "scam_state_read":
                return ("done", "", self._read())
            if verb == "scam_hud_op" and int(nums.get("op_code", -1)) == 0:
                return ("done", "", self._read())
            if verb == "scam_hud_op" and int(nums.get("op_code", -1)) == 2:
                self.flags = self.saved_flags
                self.aux = self.saved_aux
                return ("done", "", self._read())
            if verb == "scam_free_op" and int(nums.get("op_code", -1)) == 3:
                self._cleanup()
                return ("done", "", self._read())
            if not self.peer.lease_valid():
                return ("error", "lease_expired", wire.empty_payload())

            if verb == "scam_fixture_setup":
                self.active = 1.0
                self.pose = {
                    "x_m": float(nums.get("anchor_x_m", 4500.0)),
                    "y_m": ANCHOR_Y,
                    "z_m": float(nums.get("anchor_z_m", 9800.0)),
                    "yaw_deg": float(nums.get("anchor_yaw_deg", 0.0)),
                    "pitch_deg": float(nums.get("anchor_pitch_deg", 0.0)),
                    "roll_deg": float(nums.get("anchor_roll_deg", 0.0)),
                    "fov_rad": float(nums.get("anchor_fov_rad", 0.70)),
                }
                self.focus_dist = 0.0
                self.focus_blur = 0.0
                return ("done", "", self._read())
            if verb == "scam_free_op":
                if int(nums.get("op_code", -1)) != 1:
                    return ("rejected", "bad_args", wire.empty_payload())
                if self.cam_job_id and self.jobs.get_state(self.cam_job_id) == "running":
                    return ("rejected", "busy", wire.empty_payload())
                self._pose_from(nums)
                self.active = 1.0
                self.focus_dist = 0.0
                self.focus_blur = 0.0
                return ("done", "", self._read())
            if verb == "scam_pose_save":
                name = str(strs.get("name", ""))
                if name == "":
                    return ("rejected", "empty_name", wire.empty_payload())
                if name in self.saved and str(strs.get("overwrite", "0")) != "1":
                    return ("rejected", "duplicate_name", wire.empty_payload())
                self.saved[name] = dict(self.pose)
                if name not in self.saved_names:
                    self.saved_names.append(name)
                return ("done", "", self._read())
            if verb == "scam_pose_apply":
                name = str(strs.get("name", ""))
                if name:
                    if name not in self.saved:
                        return ("rejected", "unknown_pose", wire.empty_payload())
                    self.pose = dict(self.saved[name])
                else:
                    self._pose_from(nums)
                if self.active != 1.0:
                    return ("rejected", "no_active_cam", wire.empty_payload())
                return ("done", "", self._read())
            if verb == "scam_hud_op":
                code = int(nums.get("op_code", -1))
                if code == 1:
                    self._hide()
                elif code == 5:
                    preset = float(nums.get("preset_mask", 0.0))
                    self.flags = preset
                    self.aux = 1.0
                    self.saved_flags = preset
                    self.saved_aux = 1.0
                elif code == 4:
                    if int(nums.get("mode", 0)) == 1:
                        self.flags = self.flags & ~(128.0 | 256.0 | 512.0)
                    else:
                        self.flags = self.flags | 256.0
                else:
                    return ("rejected", "bad_args", wire.empty_payload())
                return ("done", "", self._read())
            if verb == "scam_dof_set":
                if float(nums.get("enable_b", 0.0)) == 1.0:
                    self.focus_dist = float(nums.get("focus_dist_m", 0.0))
                    self.focus_blur = float(nums.get("focus_blur", 0.0))
                else:
                    self.focus_dist = 0.0
                    self.focus_blur = 0.0
                self.focus_calls += 1.0
                return ("done", "", self._read())
            if verb == "scam_path_start":
                if len(rows) < 2:
                    return ("rejected", "bad_args", wire.empty_payload())
                err = self.jobs.start_job(
                    self,
                    op["op_id"],
                    "cam",
                    list(CAM_STANDIN_COLS),
                    [],
                    4,
                    4096,
                    900000.0,
                    "stop",
                )
                if err:
                    return ("rejected", err, wire.empty_payload())
                self.cam_job_id = op["op_id"]
                self.seq = 0.0
                self.dtsum = 0.0
                self.duration_ms = float(rows[-1]["t_s"]) * 1000.0
                first = rows[0]
                self._pose_from(first)
                self.active = 1.0
                if str(strs.get("hide_hud", "0")) == "1":
                    self._hide()
                self.jobs.append_row(self.cam_job_id, [0.0, 0.0, 1.0], [])
                return ("done", "", self.jobs.fill_start_read(self.cam_job_id, "cam"))
            if verb == "scam_sample_start":
                err = self.jobs.start_job(
                    self,
                    op["op_id"],
                    "cam_sample",
                    list(CAM_STANDIN_COLS),
                    [],
                    5,
                    4096,
                    900000.0,
                    "stop",
                )
                if err:
                    return ("rejected", err, wire.empty_payload())
                self.sample_job_id = op["op_id"]
                self.jobs.append_row(self.sample_job_id, [0.0, 0.0, self.active], [])
                return ("done", "", self.jobs.fill_start_read(self.sample_job_id, "cam_sample"))
            return ("rejected", "unknown_verb", wire.empty_payload())

        def on_tick(self, timeslice_s):
            if not self.cam_job_id:
                return
            if self.jobs.get_state(self.cam_job_id) != "running":
                self.cam_job_id = ""
                return
            if not self.peer.lease_valid():
                return
            self.seq += 1.0
            self.dtsum += float(timeslice_s) * 1000.0
            self.jobs.append_row(self.cam_job_id, [self.seq, self.dtsum, self.active], [])
            if self.dtsum >= self.duration_ms:
                self.jobs.end_job(self.cam_job_id, "done", "")

        def on_job_end(self, job_id, state, reason):
            if job_id == self.cam_job_id:
                self.cam_job_id = ""
                self._cleanup()
            if job_id == self.sample_job_id:
                self.sample_job_id = ""

        def on_shutdown(self):
            self._cleanup()

    module = types.ModuleType("fake_ext_cam")
    module.CamStandIn = CamStandIn
    module.PREFIX = "scam_"
    module.RPC_BASE = 26102820
    module.create_ext = lambda peer, jobs: CamStandIn()
    return module


def _tee_bridge_class(registry):
    """Subclase de QABridge que copia cada fila emitida (registro Tee del modelo de S-toma).

    Se define antes de instalar el testigo: el testigo parchea la clase base real
    (``bridge_qa.QABridge``), de la que esta hereda, y asi cada ``_emit`` pasa por
    ambos sin que el Tee tape la anotacion del testigo.
    """

    class Tee(f03_common.QABridge):
        def _emit(self, row):
            registry.append(dict(row))
            return super()._emit(row)

    return Tee


def _e2e_args(**overrides):
    args = argparse.Namespace(
        build="offline",
        both=True,
        ttl_ms=gate_core.DEFAULT_TTL_MS,
        retry_ms=gate_core.DEFAULT_RETRY_MS,
        lease_ms=gate_core.DEFAULT_LEASE_MS,
        hold_ms=gate_core.DEFAULT_HOLD_MS,
        seed=gate_core.DEFAULT_SEED,
        peer_timeout=20.0,
        pbo=None,
        fault=None,
        oracle_commit=None,
        server_profile=None,
        client_profile=None,
        product_pbo=None,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def _fabricated_evidence(ev_dir):
    """Evidencia sana escrita a mano (run + los 10 mutantes) sin PartContext ni peers."""
    ev = Path(ev_dir)
    parts = ["run"] + [f"mut-{name}" for name in s_cam_mutants.EXPECTED_MUTANTS]
    for name in parts:
        part = write_healthy(ev / name)
        if name.startswith("mut-"):
            apply_mutant(part, name[len("mut-") :])
        (part / "samples" / "bridge.jsonl").write_text(
            '{"ev": "poll", "peer": "client", "http": 200, "t_ms": 0.0}\n',
            encoding="utf-8",
        )
        gate_core.write_json(
            part / "verdict.json",
            {
                "schema": "m1-verdict-v1",
                "id": "S-cam",
                "verdict": "PASA",
                "exit_code": 0,
                "checks": [],
                "metrics": {},
                "reasons": [],
            },
        )
    gate_core.write_json(
        ev / "verdict.json",
        {
            "schema": "m1-verdict-v1",
            "id": "S-cam",
            "verdict": "PASA",
            "exit_code": 0,
            "checks": [],
            "metrics": {},
            "reasons": [],
        },
    )
    return ev


class SCamOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._root = Path(tempfile.mkdtemp(prefix="s_cam_offline_"))
        cls._healthy = write_healthy(cls._root / "healthy")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._root, ignore_errors=True)

    def _part(self, name):
        part = self._root / name
        shutil.copytree(self._healthy, part)
        return part

    def _verdict(self, name=None):
        part = self._part("part" if name is None else f"mut_{name}")
        if name is not None:
            apply_mutant(part, name)
        return s_cam_eval.evaluate(part)

    def test_healthy_run(self):
        verdict = self._verdict()
        self.assertEqual(verdict["exit_code"], 0, verdict)
        self.assertEqual(verdict["verdict"], "PASA")
        self.assertTrue(all(check["status"] == "pass" for check in verdict["checks"]), verdict)

    def test_mutants(self):
        for name, spec in s_cam_mutants.EXPECTED_MUTANTS.items():
            with self.subTest(mutant=name):
                verdict = self._verdict(name)
                self.assertEqual(verdict["exit_code"], spec["expected_exit_code"], verdict)
                statuses = {check["id"]: check["status"] for check in verdict["checks"]}
                for check_id in spec["must_fail_checks"]:
                    self.assertEqual(statuses.get(check_id), "fail", f"{name}: {check_id} {verdict}")
                for check_id, status in statuses.items():
                    if check_id in spec["must_fail_checks"]:
                        continue
                    allowed = spec["allowed_non_pass"].get(check_id, [])
                    self.assertTrue(
                        status == "pass" or status in allowed,
                        f"{name}: {check_id}={status} not allowed (allowed={allowed})",
                    )

    def test_expected_mutants_schema(self):
        mutants = s_cam_mutants.EXPECTED_MUTANTS
        self.assertEqual(len(mutants), 10)
        valid_ids = {f"CAM-{i:02d}" for i in range(1, 11)}
        for name, spec in mutants.items():
            self.assertIn(spec["expected_exit_code"], (1,), name)
            self.assertTrue(spec["must_fail_checks"], name)
            self.assertTrue(set(spec["must_fail_checks"]).issubset(valid_ids), name)
            self.assertTrue(set(spec["allowed_non_pass"]).isdisjoint(spec["must_fail_checks"]), name)
            fault = spec["qa_fault"]
            self.assertIsInstance(fault, str, name)
            self.assertEqual(len(fault), 24, name)
            self.assertTrue(fault.isascii(), name)
            self.assertFalse(fault.endswith("_") and fault.strip("_") == "", name)
            self.assertEqual(fault.rstrip("_"), fault.rstrip("_").strip(), name)
            self.assertRegex(fault.rstrip("_"), r"^[a-z0-9_]*[a-z0-9]$", name)

    # ---------------------------------------------------------------- negativas E9 y por check
    def _verdict_with(self, label, mutate):
        part = self._part(label)
        mutate(part)
        return s_cam_eval.evaluate(part)

    def test_neg_e9_fabrication_is_never_pass(self):
        """E9: poses que copian la pedida, capturas identicas, metricas esperadas y HUD
        restaurado sin leer el arbol de widgets nunca dan PASA; se comprueba el check y el
        detail exacto de cada deteccion."""
        cases = (
            (
                "fab_echo_requested_pose",
                _fab_echo_requested_pose,
                "CAM-02",
                "fail",
                "p_roll_eng_pos_err",
            ),
            (
                "fab_echo_requested_path",
                _fab_echo_requested_path,
                "CAM-03",
                "fail",
                "path_catmull_scripted_cam_eng_mismatch",
            ),
            (
                "fab_identical_capture",
                _fab_identical_capture,
                "CAM-07",
                "fail",
                "dof_not_supported_or_identical_frames",
            ),
            (
                "fab_expected_metrics_instead_of_calculated",
                _fab_expected_metrics_instead_of_calculated,
                "CAM-09",
                "fail",
                "hud_visible_full_screen",
            ),
            (
                "fab_hud_restored_without_widget_tree",
                _fab_hud_restored_without_widget_tree,
                "CAM-09",
                "fail",
                "aux_not_restored",
            ),
        )
        for label, mutate, check_id, status, detail in cases:
            with self.subTest(fabrication=label):
                verdict = self._verdict_with(label, mutate)
                self.assertNotEqual(verdict["verdict"], "PASA", verdict)
                checks = _checks_by_id(verdict)
                self.assertEqual(checks[check_id]["status"], status, verdict)
                self.assertEqual(checks[check_id]["detail"], detail, verdict)

    def test_neg_one_per_check_cam_01_to_cam_10(self):
        """Una negativa minima por cada check CAM-01..CAM-10: cae solo por su regla y su
        detail exacto; el resto de checks sigue en pass."""
        cases = (
            ("cam01", _neg_wire_nan, "CAM-01", "fail", "wire_nan_not_rejected"),
            ("cam02", _neg_p_roll_inactive, "CAM-02", "fail", "p_roll_inactive"),
            ("cam03", _neg_path_inactive, "CAM-03", "fail", "path_catmull_scripted_cam_inactive"),
            ("cam04", _neg_finish_late, "CAM-04", "fail", "path_catmull_scripted_finish_ms=6301.0"),
            ("cam05", _neg_fov_off_lerp, "CAM-05", "fail", "fov_vs_lerp_rad"),
            ("cam06", _neg_dof_reject_accepted, "CAM-06", "fail", "neg_1_not_rejected"),
            (
                "cam07",
                _neg_dof_identical_frames,
                "CAM-07",
                "fail",
                "dof_not_supported_or_identical_frames",
            ),
            ("cam08", _neg_focus_blur_wrong, "CAM-08", "fail", "sent_blur_row_10"),
            ("cam09", _neg_elem_visible, "CAM-09", "fail", "elem_vis_row_5"),
            ("cam10", _neg_burst_a_wrong_sign, "CAM-10", "fail", "burst_a_sign"),
        )
        for label, mutate, check_id, status, detail in cases:
            with self.subTest(check=check_id):
                verdict = self._verdict_with(label, mutate)
                self.assertEqual(verdict["exit_code"], 1, verdict)
                checks = _checks_by_id(verdict)
                self.assertEqual(checks[check_id]["status"], status, verdict)
                self.assertEqual(checks[check_id]["detail"], detail, verdict)
                failed = [cid for cid, check in checks.items() if check["status"] != "pass"]
                self.assertEqual(failed, [check_id], verdict)

    def test_slow_stop_qa_fault_delays_control_and_fails_cam_10(self):
        """La nota al pie del brief §6: cam_slow_stop retrasa 1500 ms PlayerControlEnable(true)
        y CAM-10 cae por recuperacion fuera de 1 s (exit 1, FALLA)."""
        part = self._part("slow_stop")
        _write_jsonl(_samples(part) / "control_recovery.jsonl", _slow_stop_recovery())
        verdict = s_cam_eval.evaluate(part)
        self.assertEqual(verdict["exit_code"], 1, verdict)
        checks = _checks_by_id(verdict)
        self.assertEqual(checks["CAM-10"]["status"], "fail", verdict)
        self.assertEqual(checks["CAM-10"]["detail"], "recovery_over_1s", verdict)
        failed = [cid for cid, check in checks.items() if check["status"] != "pass"]
        self.assertEqual(failed, ["CAM-10"], verdict)

    def test_neg_e1_expired_lease_blocks_scam_effects_and_allows_cleanup(self):
        """E1 (spikes-comun :47): con el lease caducado en el peer falso se bloquean los
        efectos de S-cam (ordenes, trabajo y efectos fuera de trabajo) y corre la limpieza
        (soltar la camara y restaurar el HUD). Modelo de S-persist
        test_s_persist_offline.py:2918/:3102; el homologo de fake_ext_cam es un stand-in
        porque el esqueleto aun no entiende scam_*."""
        import time
        from unittest import mock

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
            standin = _cam_standin_module()
            with mock.patch.dict(sys.modules, {"fake_ext_cam": standin}):
                peer = fake_peer.Peer(
                    config_path,
                    "client",
                    0,
                    30.0,
                    "",
                    clock_ms_fn=lambda: now_box[0],
                )
            peer.hello_ok = True
            peer.last_ok_ms = 1000.0
            self.assertTrue(peer.lease_valid())

            results = []

            def call(verb, payload):
                op = {
                    "op_id": f"op-{len(results)}",
                    "verb": verb,
                    "args": f03_common._normalize_new_verb_args(payload, ""),
                    "inst": peer.inst,
                    "ttl_ms": 10000,
                    "issued_ms": now_box[0],
                }
                peer._start_op(op, now_box[0], time.monotonic(), results)
                return results[-1]

            def read(out):
                return wire.unpack_payload(out["read"])

            # --- lease vigente: preparar camara libre, poses, HUD y DOF
            out = call(
                "scam_fixture_setup",
                wire.pack_payload(
                    scalars_num={
                        "anchor_x_m": 4500.0,
                        "anchor_z_m": 9800.0,
                        "anchor_eye_h_m": 1.6,
                        "anchor_yaw_deg": 0.0,
                        "anchor_pitch_deg": 0.0,
                        "anchor_roll_deg": 0.0,
                        "anchor_fov_rad": 0.70,
                        "subj_dist_m": 2.0,
                        "bg_dist_m": 50.0,
                    }
                ),
            )
            self.assertEqual(out["status"], "done", out)

            out = call(
                "scam_free_op",
                wire.pack_payload(
                    scalars_num={
                        "op_code": 1.0,
                        "x_m": 4500.0,
                        "y_m": ANCHOR_Y,
                        "z_m": 9800.0,
                        "yaw_deg": 0.0,
                        "pitch_deg": 0.0,
                        "roll_deg": 0.0,
                        "fov_rad": 0.70,
                        "speed_mps": 4.0,
                        "ang_speed_degps": 90.0,
                    }
                ),
            )
            self.assertEqual(out["status"], "done", out)
            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["num"]["active_b"], 1.0)
            self.assertEqual(state["num"]["x_m"], 4500.0)

            self.assertEqual(
                call("scam_pose_save", wire.pack_payload(scalars_str={"name": "P0", "overwrite": "0"}))["status"],
                "done",
            )
            self.assertEqual(
                call("scam_hud_op", wire.pack_payload(scalars_num={"op_code": 5.0, "preset_mask": 258.0}))["status"],
                "done",
            )
            self.assertEqual(
                call(
                    "scam_dof_set",
                    wire.pack_payload(scalars_num={"enable_b": 1.0, "focus_dist_m": 2.0, "focus_blur": 1.0}),
                )["status"],
                "done",
            )
            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["num"]["flags_mask"], 258.0)
            self.assertEqual(state["num"]["saved_flags_mask"], 258.0)
            self.assertEqual(state["num"]["aux_vis_mask"], 1.0)
            self.assertEqual(state["num"]["saved_aux_vis_mask"], 1.0)
            self.assertEqual(state["num"]["sent_focus_dist_m"], 2.0)
            self.assertEqual(state["num"]["sent_focus_blur"], 1.0)

            # --- trabajo "cam" con deadman stop, en curso y con HUD oculto
            path = call(
                "scam_path_start",
                wire.pack_payload(
                    scalars_str={"pos_mode": "linear", "interp_mode": "scripted", "hide_hud": "1"},
                    num_cols=[
                        "t_s",
                        "x_m",
                        "y_m",
                        "z_m",
                        "yaw_deg",
                        "pitch_deg",
                        "roll_deg",
                        "fov_rad",
                        "focus_dist_m",
                        "focus_blur",
                    ],
                    row_dicts=[
                        {
                            "t_s": 0.0,
                            "x_m": 4500.0,
                            "y_m": ANCHOR_Y,
                            "z_m": 9800.0,
                            "yaw_deg": 0.0,
                            "pitch_deg": 0.0,
                            "roll_deg": 0.0,
                            "fov_rad": 0.70,
                            "focus_dist_m": 2.0,
                            "focus_blur": 1.0,
                        },
                        {
                            "t_s": 6.0,
                            "x_m": 4506.0,
                            "y_m": ANCHOR_Y + 0.8,
                            "z_m": 9804.0,
                            "yaw_deg": 30.0,
                            "pitch_deg": 2.0,
                            "roll_deg": 0.0,
                            "fov_rad": 0.90,
                            "focus_dist_m": 50.0,
                            "focus_blur": 1.0,
                        },
                    ],
                ),
            )
            self.assertEqual(path["status"], "done", path)
            job_id = read(path)["str"]["job"]
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["str"]["cam_job_state"], "running")

            # filas antes del lease caducado
            peer._step_extensions_and_jobs(0.05)
            peer._step_extensions_and_jobs(0.05)
            rows_before = read(call("job_read", wire.pack_payload(scalars_str={"job": job_id}, scalars_num={"page_n": 0})))
            rows_before_n = rows_before["num"]["rows_total_n"]
            self.assertGreater(rows_before_n, 0.0)

            # --- lease caducado: efectos bloqueados, sin efectos nuevos
            now_box[0] = 5000.0
            self.assertFalse(peer.lease_valid())
            out = call(
                "scam_hud_op",
                wire.pack_payload(scalars_num={"op_code": 1.0}),
            )
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["num"]["flags_mask"], 391.0)  # no re-guardo ni cambio nada

            out = call(
                "scam_dof_set",
                wire.pack_payload(scalars_num={"enable_b": 1.0, "focus_dist_m": 50.0, "focus_blur": 1.0}),
            )
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["num"]["sent_focus_dist_m"], 2.0)

            out = call("scam_pose_apply", wire.pack_payload(scalars_str={"name": "P0"}))
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["num"]["x_m"], 4500.0)

            out = call("scam_sample_start", wire.pack_payload(scalars_num={"duration_ms": 3500.0}))
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["str"]["sample_job_id"], "")

            out = call(
                "scam_free_op",
                wire.pack_payload(
                    scalars_num={
                        "op_code": 1.0,
                        "x_m": 4600.0,
                        "y_m": ANCHOR_Y,
                        "z_m": 9900.0,
                        "yaw_deg": 45.0,
                        "pitch_deg": 0.0,
                        "roll_deg": 0.0,
                        "fov_rad": 0.70,
                        "speed_mps": 4.0,
                        "ang_speed_degps": 90.0,
                    }
                ),
            )
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)

            # el deadman del trabajo lo termina en failed/lease_expired y corre la limpieza
            peer._step_extensions_and_jobs(0.05)
            rows_after = read(call("job_read", wire.pack_payload(scalars_str={"job": job_id}, scalars_num={"page_n": 0})))
            self.assertEqual(rows_after["num"]["rows_total_n"], rows_before_n)
            self.assertEqual(rows_after["str"]["state"], "failed")
            self.assertEqual(rows_after["str"]["reason"], "lease_expired")

            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["str"]["cam_job_state"], "")
            self.assertEqual(state["num"]["active_b"], 0.0)
            self.assertEqual(state["num"]["flags_mask"], 258.0)
            self.assertEqual(state["num"]["aux_vis_mask"], 1.0)
            self.assertEqual(state["num"]["sent_focus_dist_m"], 0.0)
            self.assertEqual(state["num"]["sent_focus_blur"], 0.0)

            # efectos fuera de trabajo bloqueados con el lease caducado
            out = call(
                "scam_free_op",
                wire.pack_payload(
                    scalars_num={
                        "op_code": 1.0,
                        "x_m": 4600.0,
                        "y_m": ANCHOR_Y,
                        "z_m": 9900.0,
                        "yaw_deg": 45.0,
                        "pitch_deg": 0.0,
                        "roll_deg": 0.0,
                        "fov_rad": 0.70,
                        "speed_mps": 4.0,
                        "ang_speed_degps": 90.0,
                    }
                ),
            )
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["num"]["active_b"], 0.0)
            self.assertEqual(state["num"]["x_m"], 4500.0)

            out = call("scam_hud_op", wire.pack_payload(scalars_num={"op_code": 1.0}))
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["num"]["flags_mask"], 258.0)

            out = call(
                "scam_dof_set",
                wire.pack_payload(scalars_num={"enable_b": 1.0, "focus_dist_m": 50.0, "focus_blur": 1.0}),
            )
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["num"]["sent_focus_dist_m"], 0.0)

            # la limpieza corre siempre, tambien con el lease caducado
            self.assertEqual(
                call("scam_hud_op", wire.pack_payload(scalars_num={"op_code": 2.0}))["status"], "done"
            )
            self.assertEqual(
                call("scam_free_op", wire.pack_payload(scalars_num={"op_code": 3.0}))["status"], "done"
            )
            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["num"]["active_b"], 0.0)
            self.assertEqual(state["num"]["flags_mask"], 258.0)
            self.assertEqual(state["num"]["aux_vis_mask"], 1.0)
        finally:
            Path(config_path).unlink()

    # ---------------------------------------------------------------- testigo comun (E9)
    def _reevaluate_parts(self, ev_dir):
        for pdir in sorted(Path(ev_dir).iterdir()):
            if not pdir.is_dir():
                continue
            verdict = s_cam_eval.evaluate(pdir)
            if pdir.name == "run":
                self.assertEqual(verdict["exit_code"], 0, verdict)
                continue
            name = pdir.name[len("mut-") :]
            spec = s_cam_mutants.EXPECTED_MUTANTS[name]
            self.assertEqual(verdict["exit_code"], spec["expected_exit_code"], verdict)
            statuses = {check["id"]: check["status"] for check in verdict["checks"]}
            for check_id in spec["must_fail_checks"]:
                self.assertEqual(statuses[check_id], "fail", f"{name}: {check_id} {verdict}")

    def _gate_with_stand_in_runner(self, runner, out_dir, registry):
        """``m1_gate.main`` envuelto como el e2e (testigo comun y registro Tee) con
        ``s_cam_run`` sustituido en ``sys.modules`` por ``runner``. Solo se toca esa
        clave, que se restaura al salir. Devuelve (rc, testigo)."""
        from unittest import mock

        stand_in = types.ModuleType("s_cam_run")
        stand_in.SPIKE_ID = "S-cam"
        stand_in.run = runner
        tee = _tee_bridge_class(registry)
        prev = sys.modules.get("s_cam_run")
        sys.modules["s_cam_run"] = stand_in
        try:
            with e2e_witness.Witness() as witness, mock.patch.object(f03_common, "QABridge", tee):
                rc = m1_gate.main(
                    ["spike", "S-cam", "--both", "--build", "offline", "--evidence", str(out_dir)]
                )
        finally:
            if prev is None:
                sys.modules.pop("s_cam_run", None)
            else:
                sys.modules["s_cam_run"] = prev
        return rc, witness

    def test_neg_witness_fabricating_runner_without_peers_is_caught_through_m1_gate(self):
        """Fabricante sin peers: ``s_cam_run`` sustituido en ``sys.modules`` por un runner
        que escribe a mano la evidencia sana (la parte sana y los 10 mutantes, con
        ``verdict.json`` PASA) sin ``PartContext`` ni peers. Por ``m1_gate.main`` aparenta
        exito y su arbol supera la reevaluacion del oraculo (fuentes sinteticas), pero el
        testigo comun, instalado durante la corrida como en el e2e, no ve ningun peer real
        (``no_peer_process``) ni fila emitida por el bridge (``unwitnessed_row``)."""

        def fabricated(args, evidence, argv):
            _fabricated_evidence(evidence)
            return 0

        registry: list = []
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "s_cam_fabricated"
            rc, witness = self._gate_with_stand_in_runner(fabricated, out_dir, registry)
            self.assertEqual(rc, 0, "el fabricador aparenta exito")
            self.assertEqual(gate_core.read_json(out_dir / "verdict.json")["verdict"], "PASA")
            self._reevaluate_parts(out_dir)
            self.assertEqual(registry, [], "el fabricador no abre ningun bridge")
            problems = witness.verify(out_dir)
            self.assertTrue(problems, "el testigo comun deberia detectar al fabricador")
            codes = {p.code for p in problems}
            self.assertIn("no_peer_process", codes, problems[:5])
            self.assertIn("unwitnessed_row", codes, problems[:5])

    def test_witness_control_honest_stand_in_runner_passes_the_e2e_wrapping(self):
        """Control del testigo comun: con el testigo y el registro Tee instalados como en
        el e2e, un runner de prueba honesto que abre un ``PartContext`` real, manda
        ``qa_echo`` a los dos peers y corta el enlace del server deja una evidencia que el
        testigo acepta entera. Prueba que lo que el e2e exige al testigo se puede cumplir
        a traves de este envoltorio; con el esqueleto, el e2e falla antes de llegar al
        testigo."""
        seen: dict = {"startup": "sin_contexto", "cut_end": False, "statuses": []}

        def honest(args, evidence, argv):
            with f03_common.PartContext(
                base_dir=Path(evidence), part_name="run", spike_id="S-cam", args=args, argv=argv
            ) as ctx:
                seen["startup"] = ctx.startup_reason
                for peer in ctx.required_peers():
                    seen["statuses"].append(f03_common.issue_one(ctx, peer, "qa_echo").status)
                ctx.bridge.cut("server", 600)
                ev = ctx.bridge.wait_event(
                    lambda e: e.get("ev") == "cut_end" and e.get("peer") == "server", 8000
                )
                seen["cut_end"] = ev is not None
                seen["statuses"].append(f03_common.issue_one(ctx, "server", "qa_echo").status)
            return 2

        registry: list = []
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "s_cam_witness_control"
            _rc, witness = self._gate_with_stand_in_runner(honest, out_dir, registry)
            self.assertIsNone(seen["startup"], seen)
            self.assertTrue(seen["cut_end"], seen)
            self.assertEqual(seen["statuses"], ["done", "done", "done"], seen)
            self.assertTrue(registry, "el registro Tee deberia ver el trafico del bridge")
            problems = witness.verify(out_dir, min_resolved_ops=3)
            self.assertEqual(problems, [], f"testigo comun sobre trafico honesto: {problems[:5]!r}")

    # ---------------------------------------------------------------- e2e (deben fallar con el esqueleto)
    def test_e2e_m1_gate_spike_s_cam_offline(self):
        """Punta a punta contra ``m1_gate.py spike S-cam --both --build offline``; el
        testigo comun (``tests/e2e_witness.py``, instalado antes que el registro Tee y
        durante toda la corrida) exige que cada fila de ``bridge.jsonl`` de cada parte
        salga de ordenes encoladas de verdad, de HTTP servido por socket y de la traza de
        los procesos peer. Con el esqueleto falla antes, en rc == 2."""
        from unittest import mock

        registry: list = []
        tee = _tee_bridge_class(registry)
        with tempfile.TemporaryDirectory() as tmp, e2e_witness.Witness() as witness, mock.patch.object(
            f03_common, "QABridge", tee
        ):
            out_dir = Path(tmp) / "s_cam_e2e"
            rc = m1_gate.main(
                ["spike", "S-cam", "--both", "--build", "offline", "--evidence", str(out_dir)]
            )
            self.assertEqual(rc, 0, "m1_gate spike S-cam offline debe terminar en PASA (exit 0)")
            self.assertEqual(gate_core.read_json(out_dir / "verdict.json")["verdict"], "PASA")
            problems = witness.verify(out_dir)
            self.assertEqual(problems, [], f"testigo comun de los e2e ({len(problems)}): {problems[:5]!r}")

    def test_e2e_m1_gate_spike_s_cam_offline_reevaluation(self):
        """La evidencia del gate offline se reevalua con ``--evaluate-only`` (todas las
        partes y ``--part run``) bajo el mismo testigo comun; cada fila de ``bridge.jsonl``
        sigue respaldada por el trafico real del nucleo y los peers."""
        from unittest import mock

        registry: list = []
        tee = _tee_bridge_class(registry)
        with tempfile.TemporaryDirectory() as tmp, e2e_witness.Witness() as witness, mock.patch.object(
            f03_common, "QABridge", tee
        ):
            out_dir = Path(tmp) / "s_cam_e2e_reval"
            rc = m1_gate.main(
                ["spike", "S-cam", "--both", "--build", "offline", "--evidence", str(out_dir)]
            )
            self.assertEqual(rc, 0, "la corrida del gate debe terminar en PASA antes de reevaluar")
            rc_all = m1_gate.main(
                [
                    "spike",
                    "S-cam",
                    "--both",
                    "--build",
                    "offline",
                    "--evaluate-only",
                    "--evidence",
                    str(out_dir),
                ]
            )
            self.assertEqual(rc_all, 0, "la reevaluacion de todas las partes debe salir 0")
            rc_run = m1_gate.main(
                [
                    "spike",
                    "S-cam",
                    "--both",
                    "--build",
                    "offline",
                    "--evaluate-only",
                    "--evidence",
                    str(out_dir),
                    "--part",
                    "run",
                ]
            )
            self.assertEqual(rc_run, 0, "la reevaluacion de run debe salir 0")
            problems = witness.verify(out_dir)
            self.assertEqual(problems, [], f"testigo comun de los e2e ({len(problems)}): {problems[:5]!r}")

    def test_e2e_lease_expired_blocks_scam_effects_and_runs_cleanup_e1(self):
        """E1 en partida falsa: con el lease caducado en el peer falso (``cut`` mas largo
        que ``lease_ms``), el trabajo ``cam`` con ``deadman=stop`` termina en
        ``failed/lease_expired`` sin emitir filas nuevas, y la limpieza corre: la camara se
        suelta y el HUD vuelve a ``saved_flags_mask``. El testigo comun, con el contexto ya
        cerrado, respalda cada fila de ``bridge.jsonl``. Falla mientras ``fake_ext_cam.py``
        sea un esqueleto (no entiende los verbos ``scam_*``)."""
        import time

        lease_ms = 300.0
        args = _e2e_args(lease_ms=int(lease_ms))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "ev"
            with e2e_witness.Witness() as witness, f03_common.PartContext(
                base_dir=base, part_name="run", spike_id="S-cam", args=args, argv=[]
            ) as ctx:
                self.assertIsNone(ctx.startup_reason)

                setup = f03_common.issue_one(
                    ctx,
                    "client",
                    "scam_fixture_setup",
                    wire.pack_payload(
                        scalars_num={
                            "anchor_x_m": 4500.0,
                            "anchor_z_m": 9800.0,
                            "anchor_eye_h_m": 1.6,
                            "anchor_yaw_deg": 0.0,
                            "anchor_pitch_deg": 0.0,
                            "anchor_roll_deg": 0.0,
                            "anchor_fov_rad": 0.70,
                            "subj_dist_m": 2.0,
                            "bg_dist_m": 50.0,
                        }
                    ),
                )
                self.assertEqual(setup.status, "done", setup)

                hud = f03_common.issue_one(
                    ctx,
                    "client",
                    "scam_hud_op",
                    wire.pack_payload(scalars_num={"op_code": 5.0, "preset_mask": 258.0}),
                )
                self.assertEqual(hud.status, "done", hud)
                dof = f03_common.issue_one(
                    ctx,
                    "client",
                    "scam_dof_set",
                    wire.pack_payload(
                        scalars_num={"enable_b": 1.0, "focus_dist_m": 2.0, "focus_blur": 1.0}
                    ),
                )
                self.assertEqual(dof.status, "done", dof)

                path = f03_common.issue_one(
                    ctx,
                    "client",
                    "scam_path_start",
                    wire.pack_payload(
                        scalars_str={"pos_mode": "linear", "interp_mode": "scripted", "hide_hud": "1"},
                        num_cols=[
                            "t_s",
                            "x_m",
                            "y_m",
                            "z_m",
                            "yaw_deg",
                            "pitch_deg",
                            "roll_deg",
                            "fov_rad",
                            "focus_dist_m",
                            "focus_blur",
                        ],
                        row_dicts=[
                            {
                                "t_s": 0.0,
                                "x_m": 4500.0,
                                "y_m": ANCHOR_Y,
                                "z_m": 9800.0,
                                "yaw_deg": 0.0,
                                "pitch_deg": 0.0,
                                "roll_deg": 0.0,
                                "fov_rad": 0.70,
                                "focus_dist_m": 2.0,
                                "focus_blur": 1.0,
                            },
                            {
                                "t_s": 6.0,
                                "x_m": 4506.0,
                                "y_m": ANCHOR_Y + 0.8,
                                "z_m": 9804.0,
                                "yaw_deg": 30.0,
                                "pitch_deg": 2.0,
                                "roll_deg": 0.0,
                                "fov_rad": 0.90,
                                "focus_dist_m": 50.0,
                                "focus_blur": 1.0,
                            },
                        ],
                    ),
                )
                self.assertEqual(path.status, "done", path)
                job_id = path.payload["str"].get("job", "")
                self.assertTrue(job_id, path)

                deadline = time.monotonic() + 5.0
                state = None
                while time.monotonic() < deadline:
                    state = f03_common.issue_one(ctx, "client", "scam_state_read", wire.pack_payload())
                    if state.status == "done" and state.payload["str"].get("cam_job_state") == "running":
                        break
                    time.sleep(0.05)
                self.assertIsNotNone(state, "sin lectura de estado")
                self.assertEqual(state.status, "done", state)
                self.assertEqual(state.payload["str"].get("cam_job_state"), "running", state)

                before = f03_common.issue_one(
                    ctx,
                    "client",
                    "job_read",
                    wire.pack_payload(scalars_str={"job": job_id}, scalars_num={"page_n": 0.0}),
                )
                self.assertEqual(before.status, "done", before)
                elapsed_before = float(before.payload["num"]["elapsed_dtsum_ms"])

                ctx.bridge.cut("client", 900)
                cut_end = ctx.bridge.wait_event(
                    lambda e: e.get("ev") == "cut_end" and e.get("peer") == "client", 8000
                )
                self.assertIsNotNone(cut_end, "el cut del client debe terminar")

                after = f03_common.issue_one(
                    ctx,
                    "client",
                    "job_read",
                    wire.pack_payload(scalars_str={"job": job_id}, scalars_num={"page_n": 0.0}),
                )
                self.assertEqual(after.status, "done", after)
                self.assertEqual(after.payload["str"].get("state"), "failed", after)
                self.assertEqual(after.payload["str"].get("reason"), "lease_expired", after)
                elapsed_after = float(after.payload["num"]["elapsed_dtsum_ms"])
                self.assertLessEqual(
                    elapsed_after - elapsed_before,
                    lease_ms + 200.0,
                    "el trabajo no debe seguir emitiendo despues de vencer el lease",
                )

                cleanup = f03_common.issue_one(ctx, "client", "scam_state_read", wire.pack_payload())
                self.assertEqual(cleanup.status, "done", cleanup)
                self.assertEqual(cleanup.payload["str"].get("cam_job_state"), "", cleanup)
                self.assertEqual(cleanup.payload["num"]["active_b"], 0.0, cleanup)
                self.assertEqual(cleanup.payload["num"]["flags_mask"], 258.0, cleanup)
                self.assertEqual(cleanup.payload["num"]["saved_flags_mask"], 258.0, cleanup)
                self.assertEqual(
                    cleanup.payload["num"]["aux_vis_mask"],
                    cleanup.payload["num"]["saved_aux_vis_mask"],
                    cleanup,
                )
                self.assertEqual(cleanup.payload["num"]["sent_focus_dist_m"], 0.0, cleanup)
                self.assertEqual(cleanup.payload["num"]["sent_focus_blur"], 0.0, cleanup)
            problems = witness.verify(base)
            self.assertEqual(problems, [], f"testigo comun de los e2e ({len(problems)}): {problems[:5]!r}")


if __name__ == "__main__":
    unittest.main()
