"""Corrida sana sintetica de S-cam y deteccion ciega de sus 10 mutantes.

La evidencia sale del brief S-cam (§3, §4, §5 y §7) y de las fixtures
``qa/fixtures/s_cam_paths.json`` / ``s_cam_rois.json``; el generador no lee
etiquetas del evaluador. Los mutantes se aplican como efectos sobre
``part_dir/samples`` (el evaluador es ciego a sus nombres).
"""

import json
import math
import random
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

import s_cam_eval
import s_cam_mutants

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


if __name__ == "__main__":
    unittest.main()
