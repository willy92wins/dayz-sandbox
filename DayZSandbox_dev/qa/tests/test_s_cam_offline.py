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
# Enmienda 2026-11-18: 27 columnas + las 9 celdas crudas m00..m22 = 36.
PATH_COLS_36 = PATH_KEYS + tuple(f"m{r}{c}" for r in range(3) for c in range(3))
CLIENT_INST = "cd" * 16


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
    """Matriz de la fixture sintetica con la convencion medida por la
    sonda del 24-nov: la fila 2 es (cos p * sin y, sin p, cos p * cos y),
    sin efecto del roll. Las filas 0 y 1 son un completado ortonormal
    cualquiera: el motor aun no las ha medido (v5 de la sonda), y el
    oraculo solo puede juzgarlas cuando los dos lados las publican."""
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    cp = math.cos(pitch)
    fwd = [cp * math.sin(yaw), math.sin(pitch), cp * math.cos(yaw)]
    up = [0.0, 1.0, 0.0] if abs(fwd[1]) < 0.9 else [1.0, 0.0, 0.0]
    side = [
        up[1] * fwd[2] - up[2] * fwd[1],
        up[2] * fwd[0] - up[0] * fwd[2],
        up[0] * fwd[1] - up[1] * fwd[0],
    ]
    norma = math.hypot(side[0], side[1], side[2])
    side = [v / norma for v in side]
    upv = [
        fwd[1] * side[2] - fwd[2] * side[1],
        fwd[2] * side[0] - fwd[0] * side[2],
        fwd[0] * side[1] - fwd[1] * side[0],
    ]
    return [side, upv, fwd]


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


def _path_rows(fixture_name, pos_mode, orientation, euler_mode, duration_ms, count=PATH_COUNT):
    fixtures = _load_json(FIXTURES / "s_cam_paths.json")
    keys = _key_table(fixtures["paths"][fixture_name])
    dt = duration_ms / float(count - 1)
    staged = []
    for i in range(count):
        t = min(i * dt / 1000.0, keys[-1]["t_s"])
        rel = _ref_pos_rel(keys, t, pos_mode)
        pos = [rel[0], ANCHOR_Y + rel[1], rel[2]]
        if orientation == "slerp":
            m = quat_to_matrix(_ref_quat(keys, t))
            yaw, pitch, roll = _short_arc_euler(t) if euler_mode == "short_arc" else (0.0, 0.0, 0.0)
        else:
            yaw, pitch, roll = _linear_hud_euler(t)
            m = ypr_matrix(yaw, pitch, roll)
        staged.append((pos, m, yaw, pitch, roll))
    rows = []
    for i in range(count):
        t = min(i * dt / 1000.0, keys[-1]["t_s"])
        pos, m, yaw, pitch, roll = staged[i]
        # La vista publicada es la pose ordenada en el frame anterior
        # (sonda del 24-nov); el FOV, en cambio, se ve en el mismo frame.
        if i:
            prev_pos, prev_m = staged[i - 1][0], staged[i - 1][1]
        else:
            prev_pos, prev_m = pos, m
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
            prev_pos[0],
            prev_pos[1],
            prev_pos[2],
            prev_m[2][0],
            prev_m[2][1],
            prev_m[2][2],
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


def _dof_rows(fixture_name, count=PATH_COUNT):
    fixtures = _load_json(FIXTURES / "s_cam_paths.json")
    keys = _key_table(fixtures["paths"][fixture_name])
    dt = PATH_DURATION_MS / float(count - 1)
    anchor = fixtures["anchor_pose"]
    m = ypr_matrix(anchor["yaw_deg"], anchor["pitch_deg"], anchor["roll_deg"])
    rows = []
    for i in range(count):
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


def _write_path_jsonl(path, dict_rows):
    """Las filas del recorrido se escriben como listas de 36 columnas,
    como las empaqueta la sonda; nunca dicts con claves de mas."""
    _write_jsonl(path, [[row[c] for c in PATH_COLS_36] for row in dict_rows])


def _read_path_dicts(path):
    out = []
    for row in _read_jsonl(path):
        if isinstance(row, list):
            out.append(dict(zip(PATH_COLS_36, row)))
        else:
            out.append(dict(row))
    return out


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


def _hud_tree(phase, step, overlay=False):
    """Arbol de widgets crudo: identidad, padre y visibilidad por nodo."""
    nodes = [
        {"id": "ws", "parent": None, "visible": True, "hierarchy": True, "baseline": True},
        {"id": "hud_panel", "parent": "ws", "visible": True, "hierarchy": True, "baseline": True},
        {"id": "crosshair", "parent": "hud_panel", "visible": False, "hierarchy": False, "baseline": True},
        {"id": "stamina_bg", "parent": "hud_panel", "visible": False, "hierarchy": False, "baseline": True},
    ]
    if overlay:
        nodes.append({"id": "test_overlay_20", "parent": "hud_panel",
                      "visible": True, "hierarchy": True, "baseline": False})
    return {"ev": "hud_tree", "phase": phase, "step": step, "nodes": nodes,
            "baseline_ids": ["ws", "hud_panel", "crosshair", "stamina_bg"]}


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
    rows.append(_op("SCAM-S0", "fixture", "scam_fixture_setup", "done", nk={
        "frame": float(FRAME_BASE), "tick_ms": TICK_BASE, "active_b": 1.0,
        "anchor_x_m": 4500.0, "anchor_y_m": ANCHOR_Y, "anchor_z_m": 9800.0,
        "subj_present_b": 1.0, "subj_dist_m": 2.0, "bg_present_b": 1.0,
        "bg_dist_m": 50.0, "qb_items_n": 1.0, "player_in_veh_b": 0.0,
        "fov_rad": 0.70,
    }))
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
    # P0 del protocolo: KC_RIGHT+KC_UP simultaneos 300 ms a igual velocidad
    # dan 27/27 grados (simetrica); no una P0 inventada.
    s_0 = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 27.0, 27.0, 0.0, 0.70, speed=8.0, speed_steps=1.0, integrated=1.3, input_frames=90.0)
    moved = _pose_nk(4520.0, ANCHOR_Y, 9806.0, 60.0, 15.0, 0.0, 0.70, speed=8.0, speed_steps=1.0, integrated=1.6, input_frames=120.0)
    p_roll = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 35.0, -12.0, 18.0, 0.85)
    p0 = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 27.0, 27.0, 0.0, 0.70)
    rows.append(_state("SCAM-S1", "s_init", s_init))
    rows.append(_state("SCAM-S1", "s_a", s_a))
    rows.append(_state("SCAM-S1", "s_b", s_b))
    rows.append(_state("SCAM-S1", "s_0", s_0))
    rows.append(_state("SCAM-S1", "moved", moved))
    # Lecturas de scam_pose_save: la referencia de la reaplicacion (brief:105).
    rows.append(_op("SCAM-S1", "save_p0", "scam_pose_save", "done", nk=dict(s_0), sk={"name": "P0", "saved_names_csv": "P0,P_roll"}))
    rows.append(_op("SCAM-S1", "save_p_roll", "scam_pose_save", "done", nk=dict(p_roll), sk={"name": "P_roll", "saved_names_csv": "P0,P_roll"}))
    rows.append(_state("SCAM-S1", "p_roll_applied", p_roll))
    rows.append(_state("SCAM-S1", "p0_applied", p0))
    # N8: negativa sin cliente, provocada y con invariancia observada.
    nc_pre = _pose_nk(4500.0, ANCHOR_Y, 9806.0, 27.0, 27.0, 0.0, 0.70, saved_count=2.0)
    rows.append(_state("SCAM-S1", "pre_nc", nc_pre, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))
    for step, verb in (
        ("no_client_free", "scam_free_op"), ("no_client_pose", "scam_pose_apply"),
        ("no_client_hud", "scam_hud_op"), ("no_client_dof", "scam_dof_set"),
        ("no_client_path", "scam_path_start"), ("no_client_sample", "scam_sample_start"),
    ):
        rows.append(_op("SCAM-S1", step, verb, "rejected", "client_not_in_game"))
    rows.append(_state("SCAM-S1", "post_nc", nc_pre, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))

    for step in ("neg_1", "neg_2", "neg_3", "neg_4", "neg_5", "neg_6"):
        idx = step.split("_")[1]
        nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, saved_count=2.0)
        rows.append(_state("SCAM-S2", f"pre_{idx}", nk, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))
        rows.append(_op("SCAM-S2", step, "scam_path_start", "rejected", "bad_args"))
        rows.append(_state("SCAM-S2", f"post_{idx}", nk, {"saved_names_csv": "P0,P_roll", "cam_job_state": ""}))

    rows.append(_op("SCAM-S2", "path_1_start", "scam_path_start", "done", sk={"job": "job-1"}))
    busy_nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, cam_dtsum=900.0)
    rows.append(_state("SCAM-S2", "busy_pre", busy_nk, {"cam_job_id": "job-1", "cam_job_state": "running"}))
    rows.append(_op("SCAM-S2", "busy_attempt", "scam_path_start", "rejected", "busy"))
    rows.append(_state("SCAM-S2", "busy_post", busy_nk, {"cam_job_id": "job-1", "cam_job_state": "running"}))

    # Horquilla honesta: dos filas reales del recorrido a 4 frames.
    hud_rows = _path_rows("linear_hud_6s", "linear", "ypr", "linear_hud", PATH_DURATION_MS)
    def _nk_from_path(row):
        return _pose_nk(row["x_m"], row["y_m"], row["z_m"], row["yaw_deg"],
                        row["pitch_deg"], row["roll_deg"], row["fov_rad"],
                        cam_dtsum=row["dtsum_ms"], frame=int(row["frame"]),
                        tick=row["tick_ms"], aux=0.0)
    pre_cap = _nk_from_path(hud_rows[120])
    post_cap = _nk_from_path(hud_rows[124])
    cap_row = hud_rows[122]
    rows.append(_state("SCAM-S3", "hud_preset", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, flags=258.0, saved_flags=258.0, aux=34.0, saved_aux=34.0), {"cam_job_state": ""}))
    rows.append(_op("SCAM-S3", "path_hud_start", "scam_path_start", "done", sk={"job": "job-hud"}))
    rows.append(_state("SCAM-S3", "pre_cap", pre_cap, {"cam_job_state": "running", "cam_job_id": "job-hud"}))
    rows.append(_state("SCAM-S3", "post_cap", post_cap, {"cam_job_state": "running", "cam_job_id": "job-hud"}))
    cap_ev = _capture("SCAM-S3", "hud_during", "hud_during.bmp", "pre_cap", "post_cap")
    cap_ev["frame"] = float(cap_row["frame"])
    rows.append(cap_ev)
    clean_ref = _nk_from_path(cap_row)
    rows.append(_state("SCAM-S3", "clean_ref_state", clean_ref, {"cam_job_state": ""}))
    rows.append(_capture("SCAM-S3", "hud_clean_ref", "hud_clean_ref.bmp", "clean_ref_state", "clean_ref_state"))
    rows.append(_capture("SCAM-S3", "hud_clean_repeat", "hud_clean_ref_repeat.bmp", "clean_ref_state", "clean_ref_state"))
    rows.append(_capture("SCAM-S3", "hud_visible_ref", "hud_visible_ref.bmp", "clean_ref_state", "clean_ref_state"))
    rows.append(_hud_tree("SCAM-S3", "tree_pre_cap", overlay=False))
    rows.append(_hud_tree("SCAM-S3", "tree_control_ovl", overlay=True))
    post_path_hud = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, flags=258.0, saved_flags=258.0, aux=34.0, saved_aux=34.0)
    rows.append(_state("SCAM-S3", "post_path_hud", post_path_hud, {"cam_job_state": ""}))
    rows.append({"ev": "hud_control", "phase": "SCAM-S3", "step": "control_qb", "op_code": 4, "mode": 1, "read_nk": {"qb_vis_b": 1.0}})
    rows.append({"ev": "hud_control", "phase": "SCAM-S3", "step": "control_ovl", "op_code": 4, "mode": 2, "read_nk": {"ovl_vis_b": 1.0}})
    # Lecturas scam_hud_op(0) de los controles (brief:217-218): son las
    # que acredita el evaluador; las filas hud_control son solo resumen.
    rows.append(_op("SCAM-S3", "control_read_qb", "scam_hud_op", "done", nk={"frame": 1500.0, "tick_ms": 9000.0, "elem_vis_mask": 0.0, "flags_mask": 391.0, "saved_flags_mask": 258.0, "aux_vis_mask": 0.0, "saved_aux_vis_mask": 34.0, "qb_vis_b": 1.0, "qb_items_n": 1.0, "menu_open_b": 0.0, "ovl_vis_b": 0.0, "player_in_veh_b": 0.0}))
    rows.append(_op("SCAM-S3", "control_read_ovl", "scam_hud_op", "done", nk={"frame": 1501.0, "tick_ms": 9016.0, "elem_vis_mask": 0.0, "flags_mask": 391.0, "saved_flags_mask": 258.0, "aux_vis_mask": 0.0, "saved_aux_vis_mask": 34.0, "qb_vis_b": 0.0, "qb_items_n": 1.0, "menu_open_b": 0.0, "ovl_vis_b": 1.0, "player_in_veh_b": 0.0}))

    rows.append(_capture("SCAM-S4", "dof_before", "dof_before_reject.bmp", "pre_1", "pre_1"))
    for j in range(1, 5):
        nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, enable=1.0, sent_dist=3.5, sent_blur=0.6, calls=5.0)
        rows.append(_state("SCAM-S4", f"pre_{j}", nk))
        rows.append(_op("SCAM-S4", f"neg_{j}", "scam_dof_set", "rejected", "bad_args"))
        rows.append(_state("SCAM-S4", f"post_{j}", nk))
        rows.append(_capture("SCAM-S4", f"dof_after_{j}", f"dof_after_reject_{j}.bmp", f"post_{j}", f"post_{j}"))

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
    rows.append(_capture("SCAM-S4", "ctrl_noblur_repeat", "dof_ctrl_noblur_repeat.bmp", "ctrl_noblur_pre", "ctrl_noblur_post"))
    rows.append(_state("SCAM-S4", "post_reset", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70)))

    phases = {
        1: (0.0, 50.0),
        2: (1400.0, 1500.0),
        3: (2900.0, 3000.0),
        4: (5700.0, 5800.0),
    }
    for path in ("dof_var_6s", "dof_fixed_6s"):
        for k, (pre, post) in phases.items():
            for suffix, dtsum in (("pre", pre), ("post", post)):
                nk = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70,
                              cam_dtsum=dtsum, frame=FRAME_BASE + int(dtsum / 16.667))
                rows.append(_state("SCAM-S4", f"{path}_t{k}_{suffix}", nk,
                                   {"cam_job_state": "running",
                                    "cam_job_id": "job-var" if path == "dof_var_6s" else "job-fix"}))
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
            prefix = "var" if path == "dof_var_6s" else "fix"
            rows.append(_capture("SCAM-S4", f"{prefix}_t{k}", f"{prefix}_t{k}.bmp",
                                 f"{path}_t{k}_pre", f"{path}_t{k}_post"))
    rows.append(_state("SCAM-S4", "post_dof_var", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, frame=FRAME_BASE + 400), {"cam_job_state": ""}))
    rows.append(_state("SCAM-S4", "post_dof_fix", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, frame=FRAME_BASE + 401), {"cam_job_state": ""}))

    # La mascara inicial de S5 se observa antes de ocultar/parar, y el
    # job_stop real va como op enlazada antes de su resumen ev=stop.
    rows.append(_state("SCAM-S5", "hud_preset", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, flags=258.0, saved_flags=258.0, aux=34.0, saved_aux=34.0), {"cam_job_state": ""}))
    # S5 arranca sus dos trabajos antes de parar: cada arranque ancla
    # su trabajo con job == op_id (StartJob del brief:140).
    sample_start = _op("SCAM-S5", "sample_s5_start", "scam_sample_start", "done", sk={"job": "sample-job"})
    sample_start["op_id"] = "sample-job"
    rows.append(sample_start)
    path_start = _op("SCAM-S5", "path_s5_start", "scam_path_start", "done", sk={"job": "cam-job"})
    path_start["op_id"] = "cam-job"
    rows.append(path_start)
    rows.append(_op("SCAM-S5", "stop_op", "job_stop", "done", sk={"job": "cam-job", "state": "stopped", "reason": ""}))
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
    post_stop = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70, flags=258.0, saved_flags=258.0, aux=34.0, saved_aux=34.0, input_ack=14.0)
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
    """brief:127: durante el retardo de cam_slow_stop los pulsos se
    ignoran; llegan en la ventana y nunca producen giro."""
    rows = []
    tick = 1000.0
    frame = 5000.0
    while tick <= 2600.0:
        psi = 0.0
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
    # Cada BMP sale de su propia pose y evento: ningun contenido se
    # reutiliza; una marca de pocos pixeles distingue cada captura sin
    # mover las metricas (MAD entre pares emparejados sigue < 1).
    for idx, (name, img) in enumerate(sorted(files.items())):
        marked = bytearray(img)
        for j in range(8):
            marked[(idx * 131 + j * 977) % len(marked)] ^= 0x01
        _write_bmp(samples / name, marked)


def _link_scenario(scenario):
    """Cada observacion lleva op_id unico y la instancia del peer."""
    used = {str(r.get("op_id")) for r in scenario if r.get("op_id")}
    n = 0
    for row in scenario:
        if row.get("ev") in ("op", "state"):
            if not row.get("op_id"):
                n += 1
                while f"op-{n:04d}" in used:
                    n += 1
                row["op_id"] = f"op-{n:04d}"
                used.add(row["op_id"])
            row["peer_inst"] = CLIENT_INST
    return scenario


def _write_bridge(samples, scenario):
    """bridge.jsonl crudo: hello del peer y enq/result por observacion."""
    _link_scenario(scenario)
    rows = [
        {
            "ev": "hello", "peer": "client", "http": 200, "ok": True,
            "args": {"build": "offline", "inst": CLIENT_INST, "peer": "client",
                     "probe_ver": "fake-qa0", "proto": "qa0"},
        }
    ]
    stop_ev = next((r for r in scenario if r.get("ev") == "stop"), None)
    for row in scenario:
        if row.get("ev") not in ("op", "state"):
            continue
        op_id = row["op_id"]
        verb = row.get("verb") or "scam_state_read"
        enq = {"ev": "enq", "op_id": op_id, "verb": verb,
               "peer": "client", "args": {}}
        result = {
            "ev": "result", "op_id": op_id, "peer": "client",
            "result": {
                "status": row.get("status", "done"),
                "reason": row.get("reason", ""),
                "read": {"nk": row.get("read_nk") or {},
                         "sk": row.get("read_sk") or {}},
            },
        }
        if row.get("step") == "stop_op" and stop_ev is not None:
            # Tiempos del job_stop real en el bridge (arnes y peer).
            try:
                enq["t_ms"] = float(stop_ev["stop_send_h_ms"])
                result["t_ms"] = float(stop_ev["stop_ack_h_ms"])
                result["result"]["recv_ms"] = float(stop_ev["stop_recv_ms"])
                result["result"]["done_ms"] = float(stop_ev["stop_recv_ms"]) + 1.0
            except (KeyError, TypeError, ValueError):
                pass
        rows.append(enq)
        rows.append(result)
    _write_jsonl(Path(samples) / "bridge.jsonl", rows)


def write_healthy(part_dir):
    part_dir = Path(part_dir)
    samples = part_dir / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    scenario = _scenario()
    _link_scenario(scenario)
    _write_jsonl(samples / "scenario.jsonl", scenario)
    _write_bridge(samples, scenario)
    _write_path_jsonl(samples / "path_catmull_scripted.jsonl", _path_rows("short_arc_6s", "catmull_rom", "slerp", "short_arc", PATH_DURATION_MS))
    _write_path_jsonl(samples / "path_linear_hud.jsonl", _path_rows("linear_hud_6s", "linear", "ypr", "linear_hud", PATH_DURATION_MS))
    _write_path_jsonl(samples / "path_engine_interp.jsonl", _path_rows("short_arc_6s", "linear", "slerp", "short_arc", PATH_DURATION_MS))
    _write_path_jsonl(samples / "path_dof_var.jsonl", _dof_rows("dof_var_6s"))
    _write_path_jsonl(samples / "path_dof_fix.jsonl", _dof_rows("dof_fixed_6s"))
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
    if Path(path).name == "scenario.jsonl":
        # La evidencia mutada es coherente: el bridge refleja las
        # lecturas que el peer habria devuelto.
        _link_scenario(rows)
        _write_jsonl(path, rows)
        _write_bridge(Path(path).parent, rows)


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
        # N1: se inyecta al reaplicar P_roll, una pose que discrimina.
        def mutate(rows):
            for row in rows:
                if row.get("ev") == "state" and row.get("phase") == "SCAM-S1" and row.get("step") == "p_roll_applied":
                    nk = row["read_nk"]
                    nk["yaw_deg"], nk["pitch_deg"] = nk["pitch_deg"], nk["yaw_deg"]
                    m = ypr_matrix(nk["yaw_deg"], nk["pitch_deg"], nk["roll_deg"])
                    nk["eng_dx"], nk["eng_dy"], nk["eng_dz"] = m[2][0], m[2][1], m[2][2]
                    for r in range(3):
                        for c in range(3):
                            nk[f"m{r}{c}"] = m[r][c]
        _rewrite_jsonl(scenario_path, mutate)
        return

    if name == "long_arc":
        # Las tres lecturas coherentes con el yaw mutado (matriz y
        # direccion renderizada), para que CAM-05 caiga por el yaw del
        # arco largo y no por una incoherencia entre lecturas.
        def mutate(rows):
            for row in rows:
                t = row["dtsum_ms"] / 1000.0
                if t <= 3.0:
                    row["yaw_deg"] = _wrap180(179.0 - 358.0 * (t / 3.0))
                    m = ypr_matrix(row["yaw_deg"], row["pitch_deg"], row["roll_deg"])
                    row["eng_dx"], row["eng_dy"], row["eng_dz"] = m[2][0], m[2][1], m[2][2]
                    for r in range(3):
                        for c in range(3):
                            row[f"m{r}{c}"] = m[r][c]
        _mutate_path(part_dir, "path_catmull_scripted", mutate)
        return

    if name == "frozen_fov":
        def mutate(rows):
            for row in rows:
                row["fov_rad"] = 0.65
        _mutate_path(part_dir, "path_catmull_scripted", mutate)
        return

    if name == "path_jump":
        # brief:150: salto de un solo frame en t >= 3 s.
        def mutate(rows):
            done = False
            for row in rows:
                if not done and row["dtsum_ms"] >= 3000.0:
                    row["x_m"] += 2.0
                    row["eng_x_m"] += 2.0
                    done = True
        _mutate_path(part_dir, "path_catmull_scripted", mutate)
        return

    if name == "late_finish":
        path = samples / "path_catmull_scripted.jsonl"
        rows = _read_path_dicts(path)
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
        _write_path_jsonl(path, rows)
        return

    if name == "ignore_focus_keys":
        def mutate(rows):
            for row in rows:
                row["sent_focus_dist_m"] = 2.0
                row["sent_focus_blur"] = 1.0
        _mutate_path(part_dir, "path_dof_var", mutate)

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
        _mutate_path(part_dir, "path_linear_hud", mutate)
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
    path = _samples(part_dir) / f"{name}.jsonl"
    rows = _read_path_dicts(path)
    mutate(rows)
    _write_path_jsonl(path, rows)


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
    rows = _read_path_dicts(path)
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
    _write_path_jsonl(path, rows)


def _neg_fov_off_lerp(part_dir):
    def mutate(rows):
        rows[120]["fov_rad"] = 0.5

    _mutate_path(part_dir, "path_catmull_scripted", mutate)


def _neg_dof_reject_accepted(part_dir):
    _set_event(part_dir, "op", "SCAM-S4", "neg_1", status="done", reason="")
    # La respuesta cruda del bridge cuenta lo mismo que el resumen.
    bridge = _samples(part_dir) / "bridge.jsonl"
    rows = _read_jsonl(bridge)
    for row in rows:
        if row.get("ev") == "result" and row.get("op_id") == "SCAM-S4-neg_1":
            row["result"]["status"] = "done"
            row["result"]["reason"] = ""
    _write_jsonl(bridge, rows)


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
        bridge = part / "samples" / "bridge.jsonl"
        with bridge.open("a", encoding="utf-8") as fh:
            fh.write('{"ev": "poll", "peer": "client", "http": 200, "t_ms": 0.0}\n')
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


def _r1_scenario(part, fn):
    path = _scenario_path(part)
    rows = _read_jsonl(path)
    fn(rows)
    _link_scenario(rows)
    _write_jsonl(path, rows)
    _write_bridge(_samples(part), rows)


def _r1_state(part, phase, step, **nk_changes):
    def fn(rows):
        for row in rows:
            if row.get("ev") == "state" and row.get("phase") == phase and row.get("step") == step:
                row.setdefault("read_nk", {}).update(nk_changes)
    _r1_scenario(part, fn)


def _r1_op(part, phase, step, **changes):
    def fn(rows):
        for row in rows:
            if row.get("ev") == "op" and row.get("phase") == phase and row.get("step") == step:
                row.update(changes)
    _r1_scenario(part, fn)


def _r1_drop_events(part, pred):
    def fn(rows):
        rows[:] = [r for r in rows if not pred(r)]
    _r1_scenario(part, fn)


def _r1_recovery(handoff_ms=0.0, response_ms=200.0):
    """Recuperacion con handoff en handoff_ms y respuesta tras el."""
    rows = []
    tick, frame = 1000.0, 5000.0
    while tick <= 2200.0:
        rel = tick - 1000.0
        psi = 0.0
        if rel >= handoff_ms + response_ms:
            psi = 5.0
        if rel >= handoff_ms + response_ms + 240.0:
            psi = -2.0
        mcam = 1.0 if rel < handoff_ms else 0.0
        dx, dz = math.sin(math.radians(psi)), math.cos(math.radians(psi))
        rows.append([float(len(rows)), frame, tick, rel, 4500.0, ANCHOR_Y, 9800.0,
                     dx, 0.0, dz, 0.70, 4500.0, ANCHOR_Y, 9800.0, dx, 0.0, dz, mcam])
        tick += 16.0
        frame += 1.0
    return rows


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
                details = {c["id"]: c["detail"] for c in verdict["checks"]}
                for check_id, detail in (spec.get("must_fail_detail") or {}).items():
                    self.assertEqual(details.get(check_id), detail, f"{name}: {check_id} {verdict}")
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
                "missing",
                "hud_visible_other_scene",
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
        self.assertEqual(checks["CAM-10"]["detail"], "no_burst_a_response", verdict)
        failed = [cid for cid, check in checks.items() if check["status"] != "pass"]
        self.assertEqual(failed, ["CAM-10"], verdict)

    def test_e2e_e1_real_peer_expired_lease_blocks_effects(self):
        """E1 contra el fake_ext_cam real (sin stand-in), con reloj
        controlado: ordenes scam_*, trabajos cam/cam_sample, entrada libre
        en on_tick y limpieza. Falla hoy porque el peer es un esqueleto."""
        import time

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

            # Entrada libre consumible durante on_tick (brief:124-127):
            # el canal offline es el fichero junto al perfil del peer, y
            # fake_ext_cam solo se mueve al consumir entradas recibidas.
            input_path = Path(config_path).with_name("scam_os_input.jsonl")
            input_path.write_text(
                json.dumps({"seq_n": 1, "kind": "key_hold", "keys": ["KC_W"],
                            "duration_ms": 500.0, "dx_px": 0.0, "issued_h_ms": 0.0}) + "\n",
                encoding="utf-8",
            )
            peer._step_extensions_and_jobs(0.5)
            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["num"]["input_ack_seq_n"], 1.0)
            self.assertGreater(state["num"]["input_frames_n"], 0.0)
            self.assertGreater(state["num"]["z_m"], 9800.0)

            # La mascara de auxiliares se compara con su basal: el
            # preset enciende los bits 1 y 5 (brief:176) y preserva los
            # demas bits observados, no exige que valgan 0.
            basal_aux = int(read(call("scam_state_read", wire.pack_payload()))["num"]["aux_vis_mask"])
            expected_aux = float(basal_aux | (1 << 1) | (1 << 5))
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
            # brief:176: scam_hud_op(5) asegura PermanentCrossHair (bit 1)
            # y StaminaBackground (bit 5) sobre la basal y guarda esa
            # mascara: basal | 34, sea cual sea la basal observada.
            self.assertEqual(state["num"]["aux_vis_mask"], expected_aux)
            self.assertEqual(state["num"]["saved_aux_vis_mask"], expected_aux)
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

            # Un cam_sample vivo al vencer el lease (E1): arranca con el
            # lease vigente y el deadman lo termina sin emitir mas.
            sample = call("scam_sample_start", wire.pack_payload(scalars_num={"duration_ms": 3500.0}))
            self.assertEqual(sample["status"], "done", sample)
            sample_job_id = read(sample)["str"]["job"]
            self.assertTrue(sample_job_id, sample)
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["str"]["sample_job_state"], "running")

            # filas antes del lease caducado
            peer._step_extensions_and_jobs(0.05)
            peer._step_extensions_and_jobs(0.05)
            rows_before = read(call("job_read", wire.pack_payload(scalars_str={"job": job_id}, scalars_num={"page_n": 0})))
            rows_before_n = rows_before["num"]["rows_total_n"]
            self.assertGreater(rows_before_n, 0.0)
            sample_rows_before = read(call("job_read", wire.pack_payload(scalars_str={"job": sample_job_id}, scalars_num={"page_n": 0})))
            sample_rows_before_n = sample_rows_before["num"]["rows_total_n"]
            self.assertGreater(sample_rows_before_n, 0.0)

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
            # Tras dos ticks de 50 ms el camino ya aplico el lerp de foco
            # (brief:147-152): 2,0 + (50-2,0) * 0,1/6 = 2,8, no 2,0.
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["num"]["sent_focus_dist_m"], 2.8)

            out = call("scam_pose_apply", wire.pack_payload(scalars_str={"name": "P0"}))
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            # El camino avanzo en esos dos ticks: x = 4500 + 6 * 0,1/6.
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["num"]["x_m"], 4500.1)

            out = call("scam_sample_start", wire.pack_payload(scalars_num={"duration_ms": 3500.0}))
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            # El arranque expirado no crea otro sample ni toca el vivo.
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["str"]["sample_job_id"], sample_job_id)
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["str"]["sample_job_state"], "running")

            # Una orden de camino bajo un lease vencido (E1): no emite,
            # no sustituye el trabajo en curso y no mueve la camara.
            out = call(
                "scam_path_start",
                wire.pack_payload(
                    scalars_str={"pos_mode": "linear", "interp_mode": "scripted", "hide_hud": "1"},
                    num_cols=[
                        "t_s", "x_m", "y_m", "z_m", "yaw_deg", "pitch_deg",
                        "roll_deg", "fov_rad", "focus_dist_m", "focus_blur",
                    ],
                    row_dicts=[
                        {
                            "t_s": 0.0, "x_m": 4600.0, "y_m": ANCHOR_Y, "z_m": 9900.0,
                            "yaw_deg": 45.0, "pitch_deg": 0.0, "roll_deg": 0.0,
                            "fov_rad": 0.70, "focus_dist_m": 2.0, "focus_blur": 1.0,
                        },
                        {
                            "t_s": 6.0, "x_m": 4606.0, "y_m": ANCHOR_Y, "z_m": 9904.0,
                            "yaw_deg": 45.0, "pitch_deg": 0.0, "roll_deg": 0.0,
                            "fov_rad": 0.70, "focus_dist_m": 2.0, "focus_blur": 1.0,
                        },
                    ],
                ),
            )
            self.assertEqual(out["status"], "error", out)
            self.assertEqual(out["reason"], "lease_expired", out)
            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["str"]["cam_job_id"], job_id)
            self.assertEqual(state["str"]["cam_job_state"], "running")
            self.assertEqual(state["num"]["x_m"], 4500.1)

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

            # El deadman tambien termina el cam_sample vivo, sin filas
            # nuevas, y su estado queda libre.
            sample_after = read(call("job_read", wire.pack_payload(scalars_str={"job": sample_job_id}, scalars_num={"page_n": 0})))
            self.assertEqual(sample_after["num"]["rows_total_n"], sample_rows_before_n)
            self.assertEqual(sample_after["str"]["state"], "failed")
            self.assertEqual(sample_after["str"]["reason"], "lease_expired")
            self.assertEqual(read(call("scam_state_read", wire.pack_payload()))["str"]["sample_job_state"], "")

            state = read(call("scam_state_read", wire.pack_payload()))
            self.assertEqual(state["str"]["cam_job_state"], "")
            self.assertEqual(state["num"]["active_b"], 0.0)
            self.assertEqual(state["num"]["flags_mask"], 258.0)
            # OnJobEnd restaura la mascara guardada al ocultar (la basal
            # con los dos bits del preset ya encendidos).
            self.assertEqual(state["num"]["aux_vis_mask"], expected_aux)
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
            # Con m_Cam destruida la pose ya no esta definida: no se
            # afirma x_m contra el valor de antes del camino.

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
            self.assertEqual(state["num"]["aux_vis_mask"], expected_aux)
        finally:
            Path(config_path).unlink()
            Path(config_path).with_name("scam_os_input.jsonl").unlink(missing_ok=True)

    # ---------------------------------------------------------------- ronda 1 (test_r1_*)
    def _r1(self, label, mutate):
        return self._verdict_with(f"r1_{label}", mutate)

    def test_r1_01_columnas_36_y_27_dan_bad_columns(self):
        """Claude 1/Sol 2 + enmienda: 36 columnas PASA; 27 dan missing."""
        v = self._r1("cols_ok", lambda p: None)
        self.assertEqual(v["exit_code"], 0, v)
        def to27(part):
            for name in ("path_catmull_scripted", "path_linear_hud", "path_engine_interp", "path_dof_var", "path_dof_fix"):
                path = _samples(part) / f"{name}.jsonl"
                rows = [r[:27] for r in _read_jsonl(path)]
                _write_jsonl(path, rows)
        v = self._r1("cols27", to27)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-03"]["status"], "missing", v)
        self.assertEqual(checks["CAM-03"]["detail"], "bad_columns", v)
        self.assertNotEqual(v["verdict"], "PASA", v)

    def test_r1_02_n1_swap_sobre_p_roll_cae(self):
        """Sol 3/Claude 9 (N1): swap_axes sobre P_roll cae por CAM-02."""
        v = self._verdict_with("r1_swap", lambda p: apply_mutant(p, "swap_axes"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "p_roll_theta_deg", v)
        non_pass = [c["id"] for c in v["checks"] if c["status"] != "pass"]
        self.assertEqual(non_pass, ["CAM-02"], v)

    def test_r1_03_n1_swap_sobre_p0_simetrica_no_cambia_nada(self):
        """Variante honesta N1: permutar la P0 27/27 no mueve la pose."""
        def swap_p0(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "p0_applied":
                        nk = row["read_nk"]
                        nk["yaw_deg"], nk["pitch_deg"] = nk["pitch_deg"], nk["yaw_deg"]
            _r1_scenario(part, fn)
        v = self._r1("swap_p0", swap_p0)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def _r1_n2(self, label, handoff_ms):
        """Estimulos identificables desde ~100 ms y durante toda la
        ventana de recuperacion; handoff tardio y respuesta < 1 s."""
        def mut(part):
            _write_jsonl(_samples(part) / "control_recovery.jsonl", _r1_recovery(handoff_ms, 200.0))
            def fn(rows):
                extra = []
                for row in list(rows):
                    if row.get("ev") == "pulse" and row.get("burst") == "A":
                        row["issued_h_ms"] = 650.0 + 40.0 * float(row["seq_n"])
                    if row.get("ev") == "pulse" and row.get("burst") == "B":
                        row["issued_h_ms"] = 1500.0 + 40.0 * (float(row["seq_n"]) - 10.0)
                for i in range(5, 18):
                    extra.append({"ev": "pulse", "phase": "SCAM-S5", "step": f"a{i}",
                                  "burst": "A", "seq_n": i, "dx_px": 40.0,
                                  "issued_h_ms": 650.0 + 40.0 * i, "kind": "mouse_move"})
                rows.extend(extra)
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "post_stop_state":
                        row["read_nk"]["input_ack_seq_n"] = 99.0
            _r1_scenario(part, fn)
        return self._r1(label, mut)

    def test_r1_04_n2_recuperacion_500ms_pasa(self):
        """Sol 4/Claude 2 (N2): handoff a 500 ms y respuesta < 1 s PASA."""
        v = self._r1_n2("n2_500", 500.0)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r1_05_n2_recuperacion_300ms_pasa(self):
        """Variante N2: handoff a 300 ms tambien PASA."""
        v = self._r1_n2("n2_300", 300.0)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r1_06_n3_horquilla_a_100m_nunca_pasa(self):
        """Claude 4 (N3): horquilla a 100 m del camino nunca PASA."""
        def mut(part):
            _r1_state(part, "SCAM-S3", "pre_cap", x_m=4600.0, eng_x_m=4600.0)
            _r1_state(part, "SCAM-S3", "post_cap", x_m=4600.0, eng_x_m=4600.0)
        v = self._r1("n3_100m", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertIn("not_anchored", checks["CAM-09"]["detail"], v)

    def test_r1_07_n3_horquilla_desplazada_361m_nunca_pasa(self):
        """Variante N3: horquilla a 3,61 m del camino tampoco PASA."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") in ("pre_cap", "post_cap"):
                        row["read_nk"]["x_m"] += 3.61
                        row["read_nk"]["eng_x_m"] += 3.61
            _r1_scenario(part, fn)
        v = self._r1("n3_361", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertIn("not_anchored", checks["CAM-09"]["detail"], v)

    def test_r1_08_n4_fixture_en_error_nunca_pasa(self):
        """Sol 6 (N4): fixture en error con camara/FOV/escena mal cae."""
        def mut(part):
            _r1_op(part, "SCAM-S0", "fixture", status="error", reason="fixture_failed")
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("verb") == "scam_fixture_setup":
                        row["read_nk"].update({"active_b": 0.0, "fov_rad": 2.8, "subj_present_b": 0.0, "bg_present_b": 0.0})
            _r1_scenario(part, fn)
        v = self._r1("n4_fixture", mut)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "fail", v)

    def test_r1_09_n4_lectura_tras_camino_vieja_nunca_pasa(self):
        """Sol 6 variante (N4): post_dof_var con trabajo aun running cae."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "post_dof_var":
                        row["read_sk"] = {"cam_job_state": "running", "cam_job_id": "otro"}
            _r1_scenario(part, fn)
        v = self._r1("n4_stale", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "missing", v)
        self.assertIn("reset", checks["CAM-08"]["detail"], v)

    def test_r1_10_n5_ratio_069_pasa_con_metrica(self):
        """Claude 5/Sol 7 (N5): ratio 0,69 con lo demas sano PASA."""
        def mut(part):
            src = _samples(part) / "dof_ctrl_far50m.bmp"
            img = s_cam_eval.read_bmp_gray(src)
            # fondo de far con contraste reducido: se reescribe desde noblur
            # difuminado una pasada mas que near no; se usa blur del propio test
            rois = _load_json(FIXTURES / "s_cam_rois.json")
            noise = _noise_image()
            far = _blur_region(noise, rois["roi_bg_50m"], passes=1)
            marked = bytearray(far)
            marked[12345] ^= 0x01
            _write_bmp(src, marked)
        v = self._r1("n5_069", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-07"]["status"], "pass", v)
        self.assertIn("far50m_bg_ratio", v.get("metrics") or {}, v)

    def test_r1_11_n6_capacidad_desconocida_y_modo_scripted(self):
        """Sol 8/Claude 6 (N6): sin ensayo nativo, capacidad null y scripted."""
        def mut(part):
            def m(rows):
                for row in rows:
                    row["eng_x_m"] += 0.001
            _mutate_path(part, "path_catmull_scripted", m)
        v = self._r1("n6", mut)
        self.assertEqual(_checks_by_id(v)["CAM-05"]["status"], "pass", v)
        comp = _load_json(_samples(self._root / "r1_n6") / "interp_comparison.json")
        self.assertIsNone(comp["engine_supports_keyed_dof_b"], comp)
        self.assertEqual(comp["selected_mode"], "scripted", comp)

    def test_r1_12_n6_etiqueta_de_foco_no_cambia_el_modo(self):
        """Variante N6: foco escalonado en engine tampoco acredita capacidad."""
        def mut(part):
            def m(rows):
                for row in rows:
                    row["sent_focus_dist_m"] = 2.0
            _mutate_path(part, "path_engine_interp", m)
        v = self._r1("n6_label", mut)
        comp = _load_json(_samples(self._root / "r1_n6_label") / "interp_comparison.json")
        self.assertIsNone(comp["engine_supports_keyed_dof_b"], comp)
        self.assertEqual(comp["selected_mode"], "scripted", comp)

    def test_r1_13_n7_aux_contra_inicial_no_contra_copia(self):
        """Sol 9/Claude 7 (N7): 34 iniciales, 2 guardados y 2 restaurados FALLA."""
        def mut(part):
            _r1_state(part, "SCAM-S3", "post_path_hud", aux_vis_mask=2.0, saved_aux_vis_mask=2.0)
        v = self._r1("n7", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "fail", v)
        self.assertEqual(checks["CAM-09"]["detail"], "aux_not_restored", v)

    def test_r1_14_n7_variante_en_s5_tambien_falla(self):
        """Variante N7 en SCAM-S5/CAM-10 con el mismo patron."""
        def mut(part):
            _r1_state(part, "SCAM-S5", "post_stop_state", aux_vis_mask=2.0, saved_aux_vis_mask=2.0)
        v = self._r1("n7_s5", mut)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "fail", v)

    def test_r1_15_n8_sin_caso_da_missing(self):
        """Claude 8 (N8): la sana sin el caso sin cliente da missing."""
        def mut(part):
            _r1_drop_events(part, lambda r: str(r.get("step") or "").startswith("no_client") or r.get("step") in ("pre_nc", "post_nc"))
        v = self._r1("n8_missing", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "no_client_case", v)

    def test_r1_16_n8_orden_aceptada_sin_cliente_falla(self):
        """Variante N8: una orden aceptada sin cliente que mueve la camara FALLA."""
        def mut(part):
            _r1_op(part, "SCAM-S1", "no_client_free", status="done", reason="")
            _r1_state(part, "SCAM-S1", "post_nc", x_m=4510.0, eng_x_m=4510.0)
        v = self._r1("n8_accepted", mut)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "fail", v)

    def test_r1_17_procedencia_ids_cero_nunca_pasa(self):
        """Sol 1: ids de operacion a 0 nunca acreditan PASA."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op":
                        row["op_id"] = "0"
            _r1_scenario(part, fn)
        v = self._r1("prov_zero", mut)
        checks = _checks_by_id(v)
        self.assertNotEqual(v["verdict"], "PASA", v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)

    def test_r1_18_procedencia_verbo_sustituido_nunca_pasa(self):
        """Variante Sol 1: verbos cambiados a qa_echo con rol server cae."""
        def mut(part):
            orig = {
                r["op_id"]: r.get("verb")
                for r in _read_jsonl(_scenario_path(part))
                if r.get("ev") == "op"
            }

            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op":
                        row["verb"] = "qa_echo"
                        row["role"] = "server"
            _r1_scenario(part, fn)
            # El bridge conserva los verbos scam_* reales: el resumen
            # sustituido no casa con su enq.
            bridge = _samples(part) / "bridge.jsonl"
            brows = _read_jsonl(bridge)
            for brow in brows:
                if brow.get("ev") == "enq" and brow.get("op_id") in orig:
                    brow["verb"] = orig[brow["op_id"]]
            _write_jsonl(bridge, brows)
        v = self._r1("prov_verb", mut)
        self.assertNotEqual(v["verdict"], "PASA", v)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "fail", v)

    def test_r1_19_procedencia_sin_bridge_nunca_pasa(self):
        """Variante Sol 1: observaciones fabricadas sin bridge no pasan."""
        def mut(part):
            (_samples(part) / "bridge.jsonl").unlink()
        v = self._r1("prov_nobridge", mut)
        self.assertNotEqual(v["verdict"], "PASA", v)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "missing", v)

    def test_r1_20_busy_id_cero_y_busy_distinto(self):
        """Claude 13: id 0 o trabajo ocupado distinto del de Pasada 1 cae."""
        def zero(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "path_1_start":
                        row["read_sk"] = {"job": "0"}
            _r1_scenario(part, fn)
        v = self._r1("busy_zero", zero)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "fail", v)
        def other(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") in ("busy_pre", "busy_post"):
                        row["read_sk"] = {"cam_job_id": "job-otro", "cam_job_state": "running"}
            _r1_scenario(part, fn)
        v = self._r1("busy_other", other)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "fail", v)

    def test_r1_21_captura_sin_evento_y_reutilizada(self):
        """Claude 12 cambiado en r2 (Sol 6): sin evento da missing; dos
        tomas independientes con contenido identico son el caso ideal
        de CAM-09 (3) y pasan: la identidad sale del evento y de la
        horquilla, nunca de que el contenido sea distinto."""
        def noev(part):
            _r1_drop_events(part, lambda r: r.get("ev") == "capture" and r.get("file") == "hud_during.bmp")
        v = self._r1("cap_noev", noev)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertIn("capture", checks["CAM-09"]["detail"], v)
        def reused(part):
            shutil.copyfile(_samples(part) / "hud_clean_ref.bmp", _samples(part) / "hud_during.bmp")
        v = self._r1("cap_reused", reused)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "pass", v)

    def test_r1_22_hud_visible_de_otra_escena_falla(self):
        """Variante Claude 12 cambiada en r2 (nuevo 10): una referencia
        de otra escena da missing, nunca fail con un umbral sin cita."""
        def mut(part):
            _write_bmp(_samples(part) / "hud_visible_ref.bmp", bytearray([255]) * (W * H))
        v = self._r1("cap_blank", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "hud_visible_other_scene", v)

    def test_r1_23_cam08_fases_desde_lecturas_crudas(self):
        """Claude 10/Sol 11: lecturas fuera de ventana con etiqueta sana cae."""
        def mut(part):
            for step, dt in (("dof_var_6s_t1_pre", 400.0), ("dof_var_6s_t1_post", 1300.0),
                             ("dof_fixed_6s_t1_pre", 400.0), ("dof_fixed_6s_t1_post", 1300.0)):
                _r1_state(part, "SCAM-S4", step, cam_dtsum_ms=dt)
        v = self._r1("cam08_raw", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "missing", v)
        self.assertEqual(checks["CAM-08"]["detail"], "capture_phase_unaccredited", v)

    def test_r1_24_cam08_sin_lecturas_de_fase_da_missing(self):
        """Variante Claude 10: sin las lecturas citadas, missing."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("ev") == "state" and "_t" in str(r.get("step") or "") and r.get("phase") == "SCAM-S4")
        v = self._r1("cam08_nostates", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "missing", v)
        self.assertEqual(checks["CAM-08"]["detail"], "capture_phase_unaccredited", v)

    def test_r1_25_cam08_control_fijo_se_juzga(self):
        """Claude 19: control vacio da missing; blur del control mal da fail."""
        def empty(part):
            _write_path_jsonl(_samples(part) / "path_dof_fix.jsonl", [])
        v = self._r1("fix_empty", empty)
        self.assertEqual(_checks_by_id(v)["CAM-08"]["status"], "missing", v)
        def blur(part):
            def m(rows):
                for row in rows:
                    row["sent_focus_blur"] = 1.0
            _mutate_path(part, "path_dof_fix", m)
        v = self._r1("fix_blur", blur)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "fail", v)
        self.assertIn("fix_blur", checks["CAM-08"]["detail"], v)

    def test_r1_26_cam08_capturas_de_fase_reutilizadas(self):
        """Sol 11 variante cambiada en r2 (Sol 6): var_t1 con el mismo
        estado optico que el par estatico puede dar los mismos bytes;
        pasa, porque la identidad sale de su evento y de su fase."""
        def mut(part):
            shutil.copyfile(_samples(part) / "dof_ctrl_near2m.bmp", _samples(part) / "var_t1.bmp")
        v = self._r1("cam08_reused", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "pass", v)

    def test_r1_27_reset_por_nombre_aproximado_no_vale(self):
        """Claude 11: sin post_reset exacto, aunque haya ctrl_* sanos, missing."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("step") == "post_reset")
            _r1_state(part, "SCAM-S4", "ctrl_noblur_pre", sent_focus_dist_m=50.0, sent_focus_blur=1.0)
        v = self._r1("reset_fuzzy", mut)
        self.assertEqual(_checks_by_id(v)["CAM-07"]["status"], "missing", v)

    def test_r1_28_hud_arbol_crudo_y_dof_retail(self):
        """Claude 22/Sol 12 cambiado en r2 (nuevo 2): ningun verbo
        produce el arbol, asi que sin el CAM-09 pasa por ovl_vis_b;
        dof_config incoherente con build retail da missing."""
        def notree(part):
            _r1_drop_events(part, lambda r: r.get("ev") == "hud_tree")
        v = self._r1("hud_notree", notree)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "pass", v)
        def ovl(part):
            # El overlay se observa en ovl_vis_b de la lectura, no en un
            # arbol que ningun verbo produce.
            _r1_state(part, "SCAM-S3", "pre_cap", ovl_vis_b=1.0)
        v = self._r1("hud_tree_ovl", ovl)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "fail", v)
        def retail(part):
            man = _load_json(Path(part) / "manifest.json")
            man["build"] = "retail"
            _write_json(Path(part) / "manifest.json", man)
        v = self._r1("dof_retail", retail)
        self.assertEqual(_checks_by_id(v)["CAM-07"]["status"], "missing", v)

    def test_r1_29_cam02_fov_y_direccion_renderizada(self):
        """Sol 13/Claude 18: FOV 2,0 o direccion (1,0,0) al reaplicar FALLA."""
        def fov(part):
            _r1_state(part, "SCAM-S1", "p_roll_applied", fov_rad=2.0)
            _r1_state(part, "SCAM-S1", "p0_applied", fov_rad=2.0)
        v = self._r1("cam02_fov", fov)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "p_roll_fov_err", v)
        def dirv(part):
            _r1_state(part, "SCAM-S1", "p_roll_applied", eng_dx=1.0, eng_dy=0.0, eng_dz=0.0)
        v = self._r1("cam02_dir", dirv)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "fail", v)

    def test_r1_30_cam02_pose_guardada_en_otra_posicion_pasa(self):
        """Variante honesta Claude 18: P_roll guardada y reaplicada en el
        ancla, comparada con su lectura de guardado, PASA."""
        def mut(part):
            _r1_state(part, "SCAM-S1", "p_roll_applied", x_m=4502.0, eng_x_m=4502.0)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "save_p_roll":
                        row["read_nk"]["x_m"] = 4502.0
                        row["read_nk"]["eng_x_m"] = 4502.0
            _r1_scenario(part, fn)
        v = self._r1("cam02_anchor", mut)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "pass", v)

    def test_r1_31_cam10_sin_dx_da_missing(self):
        """Sol 16: rafagas sin desplazamiento de raton nunca PASA."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "pulse":
                        row.pop("dx_px", None)
            _r1_scenario(part, fn)
        v = self._r1("cam10_nodx", mut)
        self.assertNotEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "missing", v)

    def test_r1_32_cam10_acuse_signo_y_relojes(self):
        """Claude 20/15/23 cambiado en r2 (nuevo 4): el acuse a 0 da
        missing, nunca fail; signo mixto falla; tick que no casa con
        dtsum da missing."""
        def ack0(part):
            _r1_state(part, "SCAM-S5", "post_stop_state", input_ack_seq_n=0.0)
        v = self._r1("cam10_ack0", ack0)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "missing", v)
        def mixed(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "pulse" and row.get("burst") == "A" and row.get("seq_n") == 4:
                        row["dx_px"] = -40.0
            _r1_scenario(part, fn)
        v = self._r1("cam10_mixed", mixed)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "burst_a_sign", v)
        def clocks(part):
            path = _samples(part) / "control_recovery.jsonl"
            rows = _read_jsonl(path)
            for row in rows:
                row[3] = 0.0
            _write_jsonl(path, rows)
        v = self._r1("cam10_clocks", clocks)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "missing", v)

    def test_r1_33_fail_antes_que_missing(self):
        """Sol 15: sin wire_nan y con neg_0 en done, CAM-01 FALLA."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("ev") == "wire_nan")
            _r1_op(part, "SCAM-S1", "neg_0", status="done", reason="")
        v = self._r1("fail_first", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "closed_cam_not_rejected", v)

    def test_r1_34_campo_ausente_da_missing_sin_excepcion(self):
        """Claude 16 cambiado en r2 (nuevo 6): la base temporal sale
        del job_stop del bridge, asi que el resumen sin stop_ack_h_ms
        ya no es la fuente y la sana pasa sin excepcion."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "stop":
                        row.pop("stop_ack_h_ms", None)
            _r1_scenario(part, fn)
            # El bridge real trae los tiempos del job_stop con
            # independencia del resumen: se sellan como en la sana.
            bridge = _samples(part) / "bridge.jsonl"
            brows = _read_jsonl(bridge)
            op_id = next(r["op_id"] for r in _read_jsonl(_scenario_path(part)) if r.get("step") == "stop_op")
            for brow in brows:
                if brow.get("op_id") != op_id:
                    continue
                if brow.get("ev") == "enq":
                    brow["t_ms"] = 500.0
                if brow.get("ev") == "result":
                    brow["t_ms"] = 550.0
                    brow["result"]["recv_ms"] = 1000.0
                    brow["result"]["done_ms"] = 1001.0
            _write_jsonl(bridge, brows)
        v = self._r1("no_ack_field", mut)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

    def test_r1_35_altura_desde_fixture_no_desde_primera_fila(self):
        """Claude 17: desfase constante +1 m en Y cae; con el datum de
        fixture movido a la par, la variante honesta PASA."""
        def shifted(part):
            for name in ("path_catmull_scripted", "path_linear_hud"):
                def m(rows):
                    for row in rows:
                        row["y_m"] += 1.0
                        row["eng_y_m"] += 1.0
                _mutate_path(part, name, m)
        v = self._r1("height_shift", shifted)
        self.assertEqual(_checks_by_id(v)["CAM-03"]["status"], "fail", v)
        def honest(part):
            shifted(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("verb") == "scam_fixture_setup":
                        row["read_nk"]["anchor_y_m"] = ANCHOR_Y + 1.0
            _r1_scenario(part, fn)
        v = self._r1("height_honest", honest)
        self.assertEqual(_checks_by_id(v)["CAM-03"]["status"], "pass", v)

    def test_r1_36_suite_casos_del_brief_314(self):
        """Claude 21: los 11 casos de brief:314 que faltaban."""
        # paginas con float32 dentro de WIRE_CAP y pose_cells a 27 grados
        import struct as _st
        def f32(v):
            return _st.unpack("f", _st.pack("f", float(v)))[0]
        payload = wire.pack_payload(
            scalars_num={"page_n": 0},
            num_cols=list(PATH_COLS_36),
            row_dicts=[{c: f32(1.5) for c in PATH_COLS_36} for _ in range(3)],
        )
        self.assertLessEqual(len(json.dumps(payload).encode()), wire.WIRE_CAP)
        a = _pose_nk(4500.0, ANCHOR_Y, 9800.0, 27.0, 27.0, 0.0, 0.70)
        self.assertTrue(s_cam_eval.pose_cells_equal(a, dict(a)))
        # omision de KC_PRIOR: la velocidad no sube a 8
        def no_prior(part):
            _r1_state(part, "SCAM-S1", "s_b", speed_mps=4.0)
        v = self._r1("suite_noprior", no_prior)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "fail", v)
        # giro autonomo sin pulsos: deriva en la ventana quieta
        def drift(part):
            rows = _read_jsonl(_samples(part) / "control_recovery.jsonl")
            for row in rows:
                if 1030.0 <= row[2] < 1100.0:
                    psi = math.radians(5.0)
                    row[7], row[9] = math.sin(psi), math.cos(psi)
                    row[14], row[16] = math.sin(psi), math.cos(psi)
            _write_jsonl(_samples(part) / "control_recovery.jsonl", rows)
        v = self._r1("suite_drift", drift)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "fail", v)
        # menos de 180 muestras
        def few(part):
            def m(rows):
                del rows[100:]
            _mutate_path(part, "path_catmull_scripted", m)
        v = self._r1("suite_few", few)
        self.assertEqual(_checks_by_id(v)["CAM-03"]["status"], "missing", v)
        # textura insuficiente var_lap < 25
        def flat(part):
            _write_bmp(_samples(part) / "dof_ctrl_noblur.bmp", bytearray([128]) * (W * H))
        v = self._r1("suite_flat", flat)
        self.assertEqual(_checks_by_id(v)["CAM-06"]["status"], "missing", v)
        # u > 100 ms
        def ubig(part):
            _r1_scenario(part, lambda rows: [r.update({"stop_ack_h_ms": 700.0}) for r in rows if r.get("ev") == "stop"])
        v = self._r1("suite_ubig", ubig)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "missing", v)
        self.assertEqual(self._r1("suite_healthy", lambda p: None)["exit_code"], 0)

    def test_r1_37_suite_lost_e_invariance(self):
        """Claude 21 (resto): evento lost e invariancia de ids."""
        def lost(part):
            path = _samples(part) / "bridge.jsonl"
            rows = [r for r in _read_jsonl(path) if not (r.get("ev") == "result" and r.get("op_id") == "SCAM-S1-neg_1")]
            _write_jsonl(path, rows)
        v = self._r1("suite_lost", lost)
        self.assertNotEqual(v["verdict"], "PASA", v)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "missing", v)
        def renamed(part):
            def fn(rows):
                for row in rows:
                    if row.get("op_id"):
                        row["op_id"] = "renamed-" + str(row["op_id"])
            _r1_scenario(part, fn)
            # _r1_scenario ya refleja los ids renombrados en el bridge;
            # aqui solo cambia el qa_fault de los enq.
            path = _samples(part) / "bridge.jsonl"
            brows = _read_jsonl(path)
            for row in brows:
                if row.get("ev") == "enq":
                    row["args"] = {"qa_fault": "x" * 24}
            _write_jsonl(path, brows)
        v = self._r1("suite_renamed", renamed)
        self.assertEqual(v["exit_code"], 0, v)

    # ---------------------------------------------------------------- ronda 2 (test_r2_*)
    def _r2(self, label, mutate):
        return self._verdict_with(f"r2_{label}", mutate)

    def _r2_scenario_direct(self, part, fn):
        """Edita scenario sin reflejarlo en el bridge (desajuste real)."""
        path = _scenario_path(part)
        rows = _read_jsonl(path)
        fn(rows)
        _write_jsonl(path, rows)

    def test_r2_01_fixture_con_los_12_campos_y_estado_pasa(self):
        """Sol 2: fixture sin fov_rad (brief:99) y estado posterior a 0,70."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "fixture":
                        row["read_nk"] = {k: v for k, v in row["read_nk"].items() if k != "fov_rad"}
                idx = next(i for i, r in enumerate(rows) if r.get("step") == "fixture")
                rows.insert(idx + 1, _state("SCAM-S0", "post_fixture", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 0.70), {"cam_job_state": ""}))
            _r1_scenario(part, fn)
        v = self._r2("fixture12", mut)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r2_02_fixture_sin_lectura_de_fov_da_missing(self):
        """Sol 2 variante: sin fov en el fixture ni en ningun estado S0."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "fixture":
                        row["read_nk"] = {k: v for k, v in row["read_nk"].items() if k != "fov_rad"}
            _r1_scenario(part, fn)
        v = self._r2("fixture_no_fov", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "no_fixture_fov_reading", v)

    def test_r2_03_fixture_fov_mal_en_estado_da_fail(self):
        """Control deshonesto Sol 2: el fixture trae 0,70 pero el estado
        posterior de la camara preparada dice 1,40."""
        def mut(part):
            def fn(rows):
                idx = next(i for i, r in enumerate(rows) if r.get("step") == "fixture")
                rows.insert(idx + 1, _state("SCAM-S0", "post_fixture", _pose_nk(4500.0, ANCHOR_Y, 9800.0, 0.0, 0.0, 0.0, 1.40), {"cam_job_state": ""}))
            _r1_scenario(part, fn)
        v = self._r2("fixture_fov_mal", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "fixture_fov", v)

    _SAVE10 = ("frame", "tick_ms", "saved_count_n", "x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg", "fov_rad")

    def _r2_save10(self, part):
        def fn(rows):
            for row in rows:
                if row.get("ev") == "op" and row.get("step") in ("save_p0", "save_p_roll"):
                    nk = dict(row["read_nk"])
                    nk["saved_count_n"] = 2.0
                    row["read_nk"] = {k: nk[k] for k in self._SAVE10}
        _r1_scenario(part, fn)

    def test_r2_04_guardado_con_los_10_campos_pasa(self):
        """Sol 3: scam_pose_save sin matriz (brief:105) y reaplicacion sana."""
        v = self._r2("save10", self._r2_save10)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r2_05_guardado_con_nombre_cambiado_da_fail(self):
        """Control deshonesto Sol 3: el guardado dice llamarse otro."""
        def mut(part):
            self._r2_save10(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "save_p_roll":
                        row["read_sk"] = {"name": "OTRA", "saved_names_csv": "P0,OTRA"}
            _r1_scenario(part, fn)
        v = self._r2("save_name", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "saved_pose_name_mismatch", v)

    def test_r2_06_guardado_no_completado_da_fail(self):
        """Control deshonesto Sol 3: save_p_roll no llego a done y la
        reaplicacion, sana en apariencia, no tiene guardado valido."""
        def mut(part):
            _r1_op(part, "SCAM-S1", "save_p_roll", status="error", reason="save_failed")
        v = self._r2("save_notdone", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "saved_pose_not_done", v)

    def _r2_recovery(self, turn_a_tick, turn_b_tick, handoff_tick=1000.0):
        rows = []
        tick, frame = 1000.0, 5000.0
        while tick <= 2000.0:
            psi = 0.0
            if tick >= turn_a_tick:
                psi = 5.0
            if tick >= turn_b_tick:
                psi = -2.0
            dx, dz = math.sin(math.radians(psi)), math.cos(math.radians(psi))
            if tick >= handoff_tick:
                eng = [4500.0, ANCHOR_Y, 9800.0, dx, 0.0, dz]
                mcam = 0.0
            else:
                eng = [4503.0, ANCHOR_Y + 0.4, 9802.0, math.sin(0.5), 0.0, math.cos(0.5)]
                mcam = 1.0
            rows.append([float(len(rows)), frame, tick, tick - 1000.0] + eng + [0.70, 4500.0, ANCHOR_Y, 9800.0, dx, 0.0, dz, mcam])
            tick += 16.0
            frame += 1.0
        return rows

    def _r2_cam10_gap(self, part, turn_a_tick, handoff_tick=1300.0, a_h=845.0):
        _write_jsonl(_samples(part) / "control_recovery.jsonl", self._r2_recovery(turn_a_tick, 1800.0, handoff_tick))
        def fn(rows):
            for row in rows:
                if row.get("ev") == "pulse" and row.get("burst") == "A":
                    row["issued_h_ms"] = a_h
                if row.get("ev") == "pulse" and row.get("burst") == "B":
                    row["issued_h_ms"] = 1245.0
                if row.get("ev") == "state" and row.get("step") == "post_stop_state":
                    row["read_nk"]["input_ack_seq_n"] = 64.0
        _r1_scenario(part, fn)

    def test_r2_07_cam10_pulso_en_el_hueco_de_reloj_pasa(self):
        """Sol 4: con el handoff en el tick 1300, el pulso de 845 cae en
        el hueco entre el handoff real y el estimado y su giro vale."""
        v = self._r2("cam10_gap", lambda p: self._r2_cam10_gap(p, 1312.0))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

    def test_cam10_r2_giro_antes_de_la_llegada_posible_da_fail(self):
        """Control deshonesto Sol 4: el pulso A se emite en 1000 (su
        llegada mas temprana al peer es 1450) y la camara gira en 1336,
        dentro de la ventana quieta posterior al handoff (1300)."""
        v = self._r2("cam10_early", lambda p: self._r2_cam10_gap(p, 1336.0, a_h=1000.0))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "pre_pulse_drift", v)

    def test_r2_09_cam10_desfase_tick_dtsum_de_3ms_pasa(self):
        """Sol 4/Claude 15: un incremento 16/13 ms entre relojes pasa."""
        def mut(part):
            path = _samples(part) / "control_recovery.jsonl"
            rows = _read_jsonl(path)
            for row in rows[6:]:
                row[3] -= 3.0
            _write_jsonl(path, rows)
        v = self._r2("cam10_3ms", mut)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

    def test_r2_10_cam10_deriva_de_reloj_grande_da_missing(self):
        """Control Sol 4: dtsum avanza 15 ms por frame frente a 16 de
        tick; la deriva acumulada entre relojes crece sin cota."""
        def mut(part):
            path = _samples(part) / "control_recovery.jsonl"
            rows = _read_jsonl(path)
            for i, row in enumerate(rows):
                row[3] = float(i) * 15.0
            _write_jsonl(path, rows)
        v = self._r2("cam10_drift", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "tick_dtsum_mismatch", v)

    def test_r2_11_hashes_durante_igual_a_limpia_pasa(self):
        """Sol 6: hud_during identica a hud_clean_ref es el caso ideal."""
        def mut(part):
            shutil.copyfile(_samples(part) / "hud_clean_ref.bmp", _samples(part) / "hud_during.bmp")
        v = self._r2("hash_ideal", mut)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "pass", v)

    def test_r2_12_hashes_fijas_identicas_pasan(self):
        """Sol 6 variante: fix_t1..t4 identicas (control fijo) pasan."""
        def mut(part):
            for k in (2, 3, 4):
                shutil.copyfile(_samples(part) / "fix_t1.bmp", _samples(part) / f"fix_t{k}.bmp")
        v = self._r2("hash_fix", mut)
        self.assertEqual(_checks_by_id(v)["CAM-08"]["status"], "pass", v)

    def test_r2_13_hashes_repetida_igual_a_la_limpia_pasa(self):
        """Sol 6 variante: hud_clean_ref_repeat identica a la limpia
        (MAD 0 entre repeticiones) tambien pasa."""
        def mut(part):
            shutil.copyfile(_samples(part) / "hud_clean_ref.bmp", _samples(part) / "hud_clean_ref_repeat.bmp")
        v = self._r2("hash_repeat", mut)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "pass", v)

    def test_r2_14_dof_offline_sin_ventana_ni_mad_pasa(self):
        """Nuevo 3: en offline basta el modo (brief:192)."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "dof_config":
                        row.pop("window_w", None)
                        row.pop("window_h", None)
                        row.pop("mad_bg_50m", None)
            _r1_scenario(part, fn)
        v = self._r2("dof_offline", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-07"]["status"], "pass", v)
        self.assertEqual(checks["CAM-08"]["status"], "pass", v)

    def test_r2_15_dof_retail_operador_correcto_pasa(self):
        """Sol 12: OPERATOR_DONE de SCAM-S0/confirm_dof_and_windowed."""
        def mut(part):
            man = _load_json(Path(part) / "manifest.json")
            man["build"] = "retail"
            _write_json(Path(part) / "manifest.json", man)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "dof_config":
                        row.update({"mode": "operator", "window_w": 1280, "window_h": 720})
                        row.pop("mad_bg_50m", None)
                rows.insert(0, {"ev": "operator_done", "phase": "SCAM-S0", "step": "SCAM-S0", "action": "confirm_dof_and_windowed"})
            _r1_scenario(part, fn)
        v = self._r2("dof_operator", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-07"]["status"], "pass", v)
        self.assertEqual(checks["CAM-08"]["status"], "pass", v)

    def test_r2_16_dof_retail_operador_de_otro_paso_da_missing(self):
        """Control deshonesto Sol 12: operator_done ajeno y mad 0."""
        def mut(part):
            man = _load_json(Path(part) / "manifest.json")
            man["build"] = "retail"
            _write_json(Path(part) / "manifest.json", man)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "dof_config":
                        row.update({"mode": "operator", "window_w": 1280, "window_h": 720, "mad_bg_50m": 0.0})
                rows.insert(0, {"ev": "operator_done", "phase": "SCAM-S5", "step": "SCAM-S5", "action": "otra_cosa"})
            _r1_scenario(part, fn)
        v = self._r2("dof_operator_bad", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-07"]["status"], "missing", v)
        self.assertEqual(checks["CAM-07"]["detail"], "dof_config_unaccredited", v)

    def test_e1_r2_los_asertos_salen_del_brief(self):
        """Nuevo 1, con la mascara del punto 7 de r3: el E1 compara los
        auxiliares con la basal observada mas los bits del preset, y
        afirma 2,8 y 4500,1 tras dos ticks, sin afirmar la pose con la
        camara destruida."""
        src = Path(__file__).read_text(encoding="utf-8")
        seg = src[src.index("def test_e2e_e1_real_peer"):src.index("# ---------------------------------------------------------------- ronda 1")]
        self.assertIn("basal_aux", seg)
        self.assertIn("expected_aux", seg)
        self.assertNotIn('["aux_vis_mask"], 34.0', seg)
        self.assertNotIn('["aux_vis_mask"], 1.0', seg)
        self.assertIn('["sent_focus_dist_m"], 2.8', seg)
        self.assertIn('["x_m"], 4500.1', seg)
        # Aritmetica del brief sobre la secuencia del propio test.
        self.assertEqual((1 << 1) | (1 << 5), 34)
        self.assertAlmostEqual(2.0 + (50.0 - 2.0) * (0.1 / 6.0), 2.8)
        self.assertAlmostEqual(4500.0 + 6.0 * (0.1 / 6.0), 4500.1)

    def test_r2_18_cam09_sin_arbol_de_widgets_pasa(self):
        """Nuevo 2: sin ev=hud_tree, ovl_vis_b acredita el overlay."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("ev") == "hud_tree")
        v = self._r2("cam09_notree", mut)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r2_19_cam09_frame_fuera_de_la_horquilla_da_missing(self):
        """Sol 5: capture.frame en otra fila, lejos de pre/post."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "capture" and row.get("file") == "hud_during.bmp":
                        row["frame"] = 1040.0
            _r1_scenario(part, fn)
        v = self._r2("cam09_frame_out", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "capture_frame_not_anchored", v)

    def test_r2_20_cam09_horquilla_de_un_segundo_da_missing(self):
        """Pasada c16: horquilla de 1 s / 1,8 m no acredita la captura."""
        def mut(part):
            hud = _read_path_dicts(_samples(part) / "path_linear_hud.jsonl")
            def from_row(r):
                return _pose_nk(r["x_m"], r["y_m"], r["z_m"], r["yaw_deg"], r["pitch_deg"], r["roll_deg"], r["fov_rad"], cam_dtsum=r["dtsum_ms"], frame=int(r["frame"]), tick=r["tick_ms"], aux=0.0)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "pre_cap":
                        row["read_nk"] = from_row(hud[90])
                    if row.get("ev") == "state" and row.get("step") == "post_cap":
                        row["read_nk"] = from_row(hud[150])
            _r1_scenario(part, fn)
        v = self._r2("cam09_span", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "capture_bracket_span", v)

    def test_r2_21_cam09_horquilla_de_otro_trabajo_da_missing(self):
        """Sol 5 variante: pre/post dicen ser de otro cam_job_id."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") in ("pre_cap", "post_cap"):
                        row["read_sk"] = {"cam_job_state": "running", "cam_job_id": "job-otro"}
            _r1_scenario(part, fn)
        v = self._r2("cam09_job", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "capture_job_mismatch", v)

    def test_r2_22_cam09_captura_solo_con_tick_pasa(self):
        """Sol 5 variante: sin frame, el capture_tick_ms localiza la fila."""
        def mut(part):
            hud = _read_path_dicts(_samples(part) / "path_linear_hud.jsonl")
            def fn(rows):
                bracket_frames = []
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") in ("pre_cap", "post_cap"):
                        bracket_frames.append(float(row["read_nk"]["frame"]))
                mid_frame = sum(bracket_frames) / len(bracket_frames)
                tick_by_frame = {float(r["frame"]): float(r["tick_ms"]) for r in hud}
                for row in rows:
                    if row.get("ev") == "capture" and row.get("file") == "hud_during.bmp":
                        row.pop("frame", None)
                        row["capture_tick_ms"] = tick_by_frame[mid_frame]
            _r1_scenario(part, fn)
        v = self._r2("cam09_tick", mut)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "pass", v)

    def test_r2_23_cam09_controles_reales_a_cero_da_fail(self):
        """Nuevo 6: las lecturas scam_hud_op del control dicen 0."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") in ("control_read_qb", "control_read_ovl"):
                        row["read_nk"]["qb_vis_b"] = 0.0
                        row["read_nk"]["ovl_vis_b"] = 0.0
            _r1_scenario(part, fn)
        v = self._r2("cam09_ctrl0", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "fail", v)
        self.assertEqual(checks["CAM-09"]["detail"], "control_qb_not_detected", v)

    def test_r2_24_cam09_solo_filas_hud_control_da_missing(self):
        """Nuevo 6 variante: quedan las filas hud_control a 1, pero
        ninguna lectura scam_hud_op enlazada."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("ev") == "op" and r.get("step") in ("control_read_qb", "control_read_ovl"))
        v = self._r2("cam09_ctrlrows", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "no_hud_control_ops", v)

    def test_r2_25_cam09_overlay_basal_visible_da_fail(self):
        """Sol 11: un auxiliar basal visible se ve en ovl_vis_b."""
        def mut(part):
            _r1_state(part, "SCAM-S3", "pre_cap", ovl_vis_b=1.0)
        v = self._r2("cam09_basal", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "fail", v)
        self.assertEqual(checks["CAM-09"]["detail"], "overlay_visible_pre_cap", v)

    def test_r2_26_cam10_en_retail_sin_acuse_pasa(self):
        """Nuevo 4: en retail el acuse no tiene productor ni se exige."""
        def mut(part):
            man = _load_json(Path(part) / "manifest.json")
            man["build"] = "retail"
            _write_json(Path(part) / "manifest.json", man)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "dof_config":
                        row.update({"mode": "optical", "window_w": 1280, "window_h": 720, "mad_bg_50m": 10.0})
            _r1_scenario(part, fn)
            _r1_state(part, "SCAM-S5", "post_stop_state", input_ack_seq_n=0.0)
        v = self._r2("cam10_retail", mut)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

    def test_r2_27_cam10_acuse_que_no_cubre_los_pulsos_da_missing(self):
        """Sol 10: pulsos con seq 100.. y acuse 14 en offline."""
        def mut(part):
            def fn(rows):
                pulses = [r for r in rows if r.get("ev") == "pulse"]
                for offset, row in enumerate(pulses):
                    row["seq_n"] = 500 + offset
            _r1_scenario(part, fn)
        v = self._r2("cam10_ackcover", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "input_ack_not_covering", v)

    def test_r2_28_estado_sin_op_id_da_missing_no_fail(self):
        """Nuevo 5: los ev=state sin op_id son ausencia, no FALLA."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state":
                        row.pop("op_id", None)
            self._r2_scenario_direct(part, fn)
        v = self._r2("state_no_opid", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_id_absent", v)

    def test_estado_con_op_id_cero_explicito_da_fail(self):
        """Control deshonesto nuevo 5: un id "0" explicito si es fail."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "pre_0":
                        row["op_id"] = "0"
            self._r2_scenario_direct(part, fn)
        v = self._r2("state_zero", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_id_zero", v)

    def test_r2_30_procedencia_resultados_qa_echo_en_bridge_da_fail(self):
        """Sol 1: los RESULT de estado se sustituyen por qa_echo."""
        def mut(part):
            bridge = _samples(part) / "bridge.jsonl"
            rows = _read_jsonl(bridge)
            state_ids = {r["op_id"] for r in _read_jsonl(_scenario_path(part)) if r.get("ev") == "state"}
            for row in rows:
                if row.get("op_id") in state_ids and row.get("ev") == "enq":
                    row["verb"] = "qa_echo"
                if row.get("op_id") in state_ids and row.get("ev") == "result":
                    row["result"] = {"status": "done", "reason": "", "read": {"has": [], "frame": 0}}
            _write_jsonl(bridge, rows)
        v = self._r2("prov_echo", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertIn("provenance", checks["CAM-01"]["detail"], v)

    def test_r2_31_procedencia_job_cambiado_solo_en_scenario_da_fail(self):
        """Sol 1 variante: el job de path_1_start y de busy cambia solo
        en el resumen; el bridge sigue diciendo job-1."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "path_1_start":
                        row["read_sk"] = {"job": "job-falso"}
                    if row.get("ev") == "state" and row.get("step") in ("busy_pre", "busy_post"):
                        row["read_sk"] = {"cam_job_id": "job-falso", "cam_job_state": "running"}
            self._r2_scenario_direct(part, fn)
        v = self._r2("prov_job", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_read_mismatch", v)

    def test_r2_32_procedencia_lectura_cruda_distinta_da_fail(self):
        """Sol 1 variante: una lectura de estado no casa con su RESULT."""
        def mut(part):
            bridge = _samples(part) / "bridge.jsonl"
            rows = _read_jsonl(bridge)
            target = next(r["op_id"] for r in _read_jsonl(_scenario_path(part)) if r.get("step") == "s_init")
            for row in rows:
                if row.get("ev") == "result" and row.get("op_id") == target:
                    row["result"]["read"]["nk"]["x_m"] = 9999.0
            _write_jsonl(bridge, rows)
        v = self._r2("prov_read", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_read_mismatch", v)

    def test_r2_33_misma_lectura_de_pre_y_post_da_missing(self):
        """Nuevo 7: post_1 es la misma lectura que pre_1 (mismo op_id)."""
        def mut(part):
            def fn(rows):
                pre = next(r for r in rows if r.get("step") == "pre_1" and r.get("phase") == "SCAM-S1")
                for row in rows:
                    if row.get("step") == "post_1" and row.get("phase") == "SCAM-S1":
                        row["read_nk"] = dict(pre["read_nk"])
                        row["read_sk"] = dict(pre["read_sk"])
                        row["op_id"] = pre["op_id"]
            self._r2_scenario_direct(part, fn)
        v = self._r2("prepost_same", mut)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "missing", v)

    def test_r2_34_post_antes_de_la_orden_da_missing(self):
        """Nuevo 7 variante: post_1 va delante de neg_1 en scenario."""
        def mut(part):
            def fn(rows):
                idx_pre = next(i for i, r in enumerate(rows) if r.get("step") == "pre_1" and r.get("phase") == "SCAM-S1")
                idx_post = next(i for i, r in enumerate(rows) if r.get("step") == "post_1" and r.get("phase") == "SCAM-S1")
                post = rows.pop(idx_post)
                rows.insert(idx_pre, post)
            _r1_scenario(part, fn)
        v = self._r2("post_before", mut)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "missing", v)

    def test_r2_35_paso_repetido_en_la_misma_fase_da_missing(self):
        """Nuevo 7 variante: dos lecturas llamadas igual en SCAM-S4."""
        def mut(part):
            def fn(rows):
                first = next(r for r in rows if r.get("step") == "dof_var_6s_t1_pre")
                closing = next(r for r in rows if r.get("step") == "dof_var_6s_t1_post")
                extra = dict(first)
                extra.pop("op_id", None)
                extra["read_nk"] = dict(first["read_nk"])
                extra["read_nk"]["cam_dtsum_ms"] = float(closing["read_nk"]["cam_dtsum_ms"]) + 25.0
                idx = next(i for i, r in enumerate(rows) if r.get("step") == "dof_var_6s_t1_post")
                rows.insert(idx + 1, extra)
            _r1_scenario(part, fn)
        v = self._r2("dup_step", mut)
        self.assertEqual(_checks_by_id(v)["CAM-08"]["status"], "missing", v)

    def test_r2_36_preset_tardio_no_acredita_la_mascara_inicial(self):
        """Nuevo 8: hud_preset tras restaurar (2) no vale de inicial."""
        def mut(part):
            def fn(rows):
                post_rows = [
                    r for r in rows
                    if r.get("ev") == "state" and r.get("step") in ("post_path_hud", "post_stop_state")
                ]
                for post_row in post_rows:
                    phase = post_row["phase"]
                    post_step = post_row["step"]
                    post_row["read_nk"]["aux_vis_mask"] = 2.0
                    post_row["read_nk"]["saved_aux_vis_mask"] = 2.0
                    idx = next(i for i, r in enumerate(rows) if r.get("phase") == phase and r.get("step") == "hud_preset")
                    preset = rows.pop(idx)
                    preset["read_nk"]["aux_vis_mask"] = 2.0
                    preset["read_nk"]["saved_aux_vis_mask"] = 2.0
                    idx_post = next(i for i, r in enumerate(rows) if r.get("phase") == phase and r.get("step") == post_step)
                    rows.insert(idx_post + 1, preset)
            _r1_scenario(part, fn)
        v = self._r2("preset_late", mut)
        checks = _checks_by_id(v)
        self.assertNotEqual(checks["CAM-09"]["status"], "pass", v)
        self.assertNotEqual(checks["CAM-10"]["status"], "pass", v)

    def test_r2_37_preset_en_la_op5_acredita_y_la_restauracion_mala_falla(self):
        """Nuevo 8 variante: la op5 enlazada (34) manda aunque la
        lectura hud_preset llegue tarde con 2."""
        def mut(part):
            def fn(rows):
                for phase, post_step, boundary in (("SCAM-S3", "post_path_hud", "path_hud_start"), ("SCAM-S5", "post_stop_state", "stop")):
                    for row in rows:
                        if row.get("ev") == "state" and row.get("phase") == phase and row.get("step") == post_step:
                            row["read_nk"]["aux_vis_mask"] = 2.0
                            row["read_nk"]["saved_aux_vis_mask"] = 2.0
                    op5 = _op(phase, "preset_op5", "scam_hud_op", "done", nk={"frame": 900.0, "tick_ms": 4000.0, "elem_vis_mask": 255.0, "flags_mask": 258.0, "saved_flags_mask": 258.0, "aux_vis_mask": 34.0, "saved_aux_vis_mask": 34.0, "qb_vis_b": 0.0, "qb_items_n": 1.0, "menu_open_b": 0.0, "ovl_vis_b": 0.0, "player_in_veh_b": 0.0})
                    idx_b = next(i for i, r in enumerate(rows) if r.get("phase") == phase and r.get("step") == boundary)
                    rows.insert(idx_b, op5)
                    idx = next(i for i, r in enumerate(rows) if r.get("phase") == phase and r.get("step") == "hud_preset")
                    preset = rows.pop(idx)
                    preset["read_nk"]["aux_vis_mask"] = 2.0
                    preset["read_nk"]["saved_aux_vis_mask"] = 2.0
                    idx_post = next(i for i, r in enumerate(rows) if r.get("phase") == phase and r.get("step") == post_step)
                    rows.insert(idx_post + 1, preset)
            _r1_scenario(part, fn)
        v = self._r2("preset_op5", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "fail", v)
        self.assertEqual(checks["CAM-09"]["detail"], "aux_not_restored", v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)

    def test_r2_38_stop_corrido_en_el_resumen_da_missing(self):
        """Nuevo 6: el resumen stop se corre 600 ms; el bridge no."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "stop":
                        row["stop_send_h_ms"] += 600.0
                        row["stop_ack_h_ms"] += 600.0
                        row["stop_recv_ms"] += 600.0
            self._r2_scenario_direct(part, fn)
        v = self._r2("stop_shift", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "stop_summary_mismatch", v)

    def test_r2_39_stop_sin_op_enlazada_da_missing(self):
        """Nuevo 6 variante: sin la op job_stop no hay base temporal."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("step") == "stop_op")
        v = self._r2("stop_no_op", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "no_stop_anchor", v)

    def test_r2_40_n8_seis_ordenes_con_un_solo_resultado_da_fail(self):
        """Sol 8: las seis sin cliente apuntan al mismo op_id y verbo."""
        def mut(part):
            def fn(rows):
                free = next(r for r in rows if r.get("step") == "no_client_free")
                for row in rows:
                    if row.get("step") in ("no_client_pose", "no_client_hud", "no_client_dof", "no_client_path", "no_client_sample"):
                        row["op_id"] = free["op_id"]
                        row["verb"] = free["verb"]
            self._r2_scenario_direct(part, fn)
        v = self._r2("n8_shared", mut)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "fail", v)

    def test_r2_41_n8_orden_aceptada_con_efectos_de_foco_da_fail(self):
        """Sol 8 variante: verbos distintos, pero post_nc cambia el foco."""
        def mut(part):
            _r1_state(part, "SCAM-S1", "post_nc", sent_focus_dist_m=10.0, enable_b=1.0)
        v = self._r2("n8_effects", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "no_client_effects", v)

    def test_r2_42_cam08_caminos_truncados_dan_missing(self):
        """Sol 7: 180 filas que no llegan a t3/t4 no acreditan fases."""
        def mut(part):
            for name in ("path_dof_var", "path_dof_fix"):
                path = _samples(part) / f"{name}.jsonl"
                _write_path_jsonl(path, _read_path_dicts(path)[:180])
        v = self._r2("cam08_trunc", mut)
        self.assertEqual(_checks_by_id(v)["CAM-08"]["status"], "missing", v)

    def test_r2_43_cam08_sin_bmp_de_t2_da_missing(self):
        """Sol 7 variante: falta var_t2.bmp aunque su evento exista."""
        def mut(part):
            (_samples(part) / "var_t2.bmp").unlink()
        v = self._r2("cam08_not2", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "missing", v)
        self.assertIn("var_t2", checks["CAM-08"]["detail"], v)

    def test_r2_44_cam08_reset_compartido_da_missing(self):
        """Sol 7 variante: post_dof_var copia el op_id de post_dof_fix."""
        def mut(part):
            def fn(rows):
                fix = next(r for r in rows if r.get("step") == "post_dof_fix")
                for row in rows:
                    if row.get("step") == "post_dof_var":
                        row["op_id"] = fix["op_id"]
                        row["read_nk"] = dict(fix["read_nk"])
            self._r2_scenario_direct(part, fn)
        v = self._r2("cam08_resetdup", mut)
        self.assertEqual(_checks_by_id(v)["CAM-08"]["status"], "missing", v)

    def test_r2_45_cam08_captura_con_lecturas_inexistentes_da_missing(self):
        """Sol 7 variante: los ev=capture de fase citan pasos que no hay."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "capture" and str(row.get("file", "")).startswith(("var_", "fix_")):
                        row["pre_step"] = "no_existe_pre"
                        row["post_step"] = "no_existe_post"
            _r1_scenario(part, fn)
        v = self._r2("cam08_capsteps", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "missing", v)
        self.assertIn("no_capture_bracket", checks["CAM-08"]["detail"], v)

    def test_r2_46_cam04_matriz_final_girada_da_fail(self):
        """Sol 15: matriz y direccion giradas 15 grados, Euler intactos."""
        def mut(part):
            def m(rows):
                last = rows[-1]
                mat = ypr_matrix(last["yaw_deg"] + 15.0, last["pitch_deg"], last["roll_deg"])
                for r in range(3):
                    for c in range(3):
                        last[f"m{r}{c}"] = mat[r][c]
                last["eng_dx"], last["eng_dy"], last["eng_dz"] = mat[2][0], mat[2][1], mat[2][2]
            _mutate_path(part, "path_linear_hud", m)
        v = self._r2("cam04_matrix", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-04"]["status"], "fail", v)
        self.assertIn("path_linear_hud_theta_deg", checks["CAM-04"]["detail"], v)

    def test_r2_47_cam04_euler_final_distinto_con_matriz_buena_pasa(self):
        """Sol 15 variante: CAM-04 juzga la matriz cruda, no el Euler."""
        def mut(part):
            def m(rows):
                rows[-1]["yaw_deg"] += 15.0
            _mutate_path(part, "path_linear_hud", m)
        v = self._r2("cam04_euler", mut)
        self.assertEqual(_checks_by_id(v)["CAM-04"]["status"], "pass", v)

    def test_docstring_r2_describe_lo_que_juzga_el_codigo(self):
        """Nuevo 9: 36 columnas, bridge, frame, peer_inst y pasos."""
        src = (QA_DIR / "s_cam_eval.py").read_text(encoding="utf-8")
        chunks = src.split('"""')
        doc = chunks[1] if len(chunks) > 2 else ""
        for token in ("36 floats", "bridge.jsonl", "peer_inst", "op_id", "frame",
                      "path_hud_start", "post_dof_var", "post_stop_state", "stop_op"):
            self.assertIn(token, doc)
        self.assertNotIn("lista de 27 floats", doc)
        self.assertNotIn("_STATIC_RESET_STEPS", src)
        self.assertNotIn("_avg_pose", src)

    def test_r2_49_cam06_sin_pre_exacta_da_missing(self):
        """Pasada c17: sin pre_1 no vale una lectura de otra fase."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("ev") == "state" and r.get("phase") == "SCAM-S4" and r.get("step") == "pre_1")
        v = self._r2("cam06_nopre", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-06"]["status"], "missing", v)
        self.assertEqual(checks["CAM-06"]["detail"], "no_state_neg_1", v)

    def test_r2_50_cam06_misma_lectura_pre_y_post_da_missing(self):
        """Nuevo 7 en CAM-06: post_2 con el op_id de pre_2."""
        def mut(part):
            def fn(rows):
                pre = next(r for r in rows if r.get("phase") == "SCAM-S4" and r.get("step") == "pre_2")
                for row in rows:
                    if row.get("phase") == "SCAM-S4" and row.get("step") == "post_2":
                        row["op_id"] = pre["op_id"]
            self._r2_scenario_direct(part, fn)
        v = self._r2("cam06_same", mut)
        self.assertEqual(_checks_by_id(v)["CAM-06"]["status"], "missing", v)

    def test_r2_51_cam01_negativa_perdida_da_missing(self):
        """Sol 13: neg_1 con lost contractual es ausencia de resultado."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "neg_1" and row.get("phase") == "SCAM-S1":
                        row["status"] = "lost"
                        row["reason"] = "result_lost"
            _r1_scenario(part, fn)
            bridge = _samples(part) / "bridge.jsonl"
            brows = [r for r in _read_jsonl(bridge) if not (r.get("ev") == "result" and r.get("op_id") == "SCAM-S1-neg_1")]
            brows.append({"ev": "lost", "op_id": "SCAM-S1-neg_1", "peer": "client", "reason": "result_lost", "verb": "scam_pose_apply"})
            _write_jsonl(bridge, brows)
        v = self._r2("cam01_lost", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertNotEqual(v["verdict"], "PASA", v)

    def test_r2_52_cam01_aceptada_sin_horquilla_da_fail(self):
        """Sol 13 variante: neg_0 en done sin pre_0 es fail, no missing."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "neg_0":
                        row["status"] = "done"
                        row["reason"] = ""
                rows[:] = [r for r in rows if not (r.get("ev") == "state" and r.get("step") == "pre_0")]
            _r1_scenario(part, fn)
        v = self._r2("cam01_accepted", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "closed_cam_not_rejected", v)

    def test_r2_53_cam10_sin_preset_en_s5_da_missing(self):
        """Sol 9: sin observacion inicial, aux=saved=2 no acredita nada."""
        def mut(part):
            _r1_drop_events(part, lambda r: r.get("phase") == "SCAM-S5" and r.get("step") == "hud_preset")
            _r1_state(part, "SCAM-S5", "post_stop_state", aux_vis_mask=2.0, saved_aux_vis_mask=2.0)
        v = self._r2("cam10_nopreset", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "no_initial_aux_observation", v)

    def test_r2_54_cam09_referencia_de_otra_escena_da_missing(self):
        """Nuevo 10 variante: visible en blanco frente a la limpia."""
        def mut(part):
            _write_bmp(_samples(part) / "hud_visible_ref.bmp", bytearray([255]) * (W * H))
        v = self._r2("cam09_otherscene", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "hud_visible_other_scene", v)

    # ---------------------------------------------------------------- ronda 3 (test_r3_*)
    def _r3(self, label, mutate):
        return self._verdict_with(f"r3_{label}", mutate)

    def _r3_expire(self, part, phase, step):
        """El transporte expira una orden: el resumen dice timeout (lo
        que devuelve issue_one) y el puente trae expire, no RESULT."""
        _r1_op(part, phase, step, status="timeout", reason="result_timeout")
        bridge = _samples(part) / "bridge.jsonl"
        rows = [r for r in _read_jsonl(bridge)
                if not (r.get("ev") == "result" and r.get("op_id") == f"{phase}-{step}")]
        rows.append({"ev": "expire", "op_id": f"{phase}-{step}", "peer": "client"})
        _write_jsonl(bridge, rows)

    def test_r3_01_n8_el_reloj_que_avanza_no_suspende(self):
        """Punto 1 (hallazgo 1): post_nc con frame+6 y tick+96, el resto
        igual, PASA: frame y tick prueban el orden, no son un efecto."""
        def mut(part):
            _r1_state(part, "SCAM-S1", "post_nc", frame=1006.0, tick_ms=5096.0)
        v = self._r3("n8_reloj", mut)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r3_02_n8_otro_avance_pasa_y_un_efecto_real_cae(self):
        """Punto 1, variante y control: frame+2/tick+33 PASA; el mismo
        avance con la pose movida sigue en FALLA no_client_effects."""
        def honesta(part):
            _r1_state(part, "SCAM-S1", "post_nc", frame=1002.0, tick_ms=5033.0)
        v = self._r3("n8_avance2", honesta)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "pass", v)

        def con_efecto(part):
            _r1_state(part, "SCAM-S1", "post_nc", frame=1006.0, tick_ms=5096.0, x_m=4501.0, eng_x_m=4501.0)
        v = self._r3("n8_efecto", con_efecto)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "no_client_effects", v)

    def test_r3_03_negativa_expirada_en_s1_da_missing(self):
        """Punto 2 (hallazgo 2): neg_1 con expire/timeout es ausencia
        de RESULT (INCONCLUSO), no una negativa incumplida."""
        v = self._r3("expire_s1", lambda p: self._r3_expire(p, "SCAM-S1", "neg_1"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "SCAM-S1_neg_1_timeout", v)
        self.assertNotEqual(v["verdict"], "PASA", v)

    def test_r3_04_expiradas_en_cam06_guardado_y_ocupado(self):
        """Punto 2, variantes: la misma regla de transporte manda en
        CAM-06, en el guardado de CAM-02 y en el camino ocupado. El
        control aceptado sigue en FALLA."""
        v = self._r3("expire_cam06", lambda p: self._r3_expire(p, "SCAM-S4", "neg_2"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-06"]["status"], "missing", v)
        self.assertEqual(checks["CAM-06"]["detail"], "neg_2_timeout", v)

        v = self._r3("expire_save", lambda p: self._r3_expire(p, "SCAM-S1", "save_p_roll"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "missing", v)
        self.assertEqual(checks["CAM-02"]["detail"], "saved_pose_timeout", v)

        v = self._r3("expire_busy", lambda p: self._r3_expire(p, "SCAM-S2", "busy_attempt"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "busy_timeout", v)

        def aceptada(part):
            _r1_op(part, "SCAM-S1", "neg_1", status="done", reason="")
        v = self._r3("neg_aceptada", aceptada)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "SCAM-S1_neg_1_not_rejected", v)

    _APPLY25 = ("frame", "tick_ms", "active_b", "x_m", "y_m", "z_m", "yaw_deg",
                "pitch_deg", "roll_deg", "fov_rad", "eng_x_m", "eng_y_m", "eng_z_m",
                "eng_dx", "eng_dy", "eng_dz")

    def _r3_as_apply_ops(self, part):
        cells = tuple(f"m{r}{c}" for r in range(3) for c in range(3))
        keep = self._APPLY25 + cells

        def fn(rows):
            for row in rows:
                if row.get("ev") != "state" or row.get("step") not in ("p_roll_applied", "p0_applied"):
                    continue
                name = "P_roll" if row["step"] == "p_roll_applied" else "P0"
                nk = {k: row["read_nk"][k] for k in keep}
                step = row["step"]
                row.clear()
                row.update({
                    "ev": "op", "phase": "SCAM-S1", "step": step,
                    "verb": "scam_pose_apply", "role": "client",
                    "op_id": f"apply-{name}", "status": "done", "reason": "",
                    "read_nk": nk, "read_sk": {"name": name},
                })
        _r1_scenario(part, fn)

    def test_r3_05_cam02_reaplicacion_como_result_del_verbo(self):
        """Punto 3 (hallazgo 3): p_roll_applied y p0_applied como el
        RESULT de scam_pose_apply (brief:106) acreditan CAM-02."""
        v = self._r3("apply_op", self._r3_as_apply_ops)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r3_06_cam02_result_wire_y_nombre_que_no_casa(self):
        """Punto 3, variante wire y control: el RESULT llega en formato
        wire en el puente y CAM-02 lo consume igual; un RESULT con otro
        nombre de pose cae."""
        def wire_variant(part):
            self._r3_as_apply_ops(part)
            bridge = _samples(part) / "bridge.jsonl"
            rows = _read_jsonl(bridge)
            for row in rows:
                if row.get("ev") == "result" and str(row.get("op_id", "")).startswith("apply-"):
                    read = row["result"]["read"]
                    packed = wire.pack_payload(scalars_num=read["nk"], scalars_str=read["sk"])
                    packed["has"] = ["payload"]
                    row["result"]["read"] = packed
            _write_jsonl(bridge, rows)
        v = self._r3("apply_wire", wire_variant)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "pass", v)

        def otro_nombre(part):
            self._r3_as_apply_ops(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "p_roll_applied":
                        row["read_sk"] = {"name": "OTRA"}
            _r1_scenario(part, fn)
        v = self._r3("apply_name", otro_nombre)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "p_roll_applied_apply_name_mismatch", v)

    def _r3_set_summary_ack(self, part, ack_ms):
        def fn(rows):
            for row in rows:
                if row.get("ev") == "stop":
                    row["stop_ack_h_ms"] = ack_ms
        self._r2_scenario_direct(part, fn)

    def test_r3_07_cam10_acuse_del_runner_posterior_al_del_puente(self):
        """Punto 4 (hallazgo 4): el RESULT llega al puente en h=550 y
        el runner sale de issue_one en h=554 (o mas tarde): son dos
        instantes validos y CAM-10 PASA. Un acuse del runner anterior
        al del puente sigue en INCONCLUSO."""
        v = self._r3("ack554", lambda p: self._r3_set_summary_ack(p, 554.0))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

        v = self._r3("ack587", lambda p: self._r3_set_summary_ack(p, 587.0))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

        v = self._r3("ack540", lambda p: self._r3_set_summary_ack(p, 540.0))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "stop_summary_mismatch", v)

    def _r3_recovery_rows(self, t0, handoff_rel, a_rel, b_rel, a_deg=4.8):
        rows = []
        tick, frame = t0, 5000.0
        while tick <= t0 + 640.0:
            rel = tick - t0
            psi = 0.0
            if rel >= a_rel:
                psi = a_deg
            if rel >= b_rel:
                psi = a_deg - 3.0
            mcam = 0.0 if rel >= handoff_rel else 1.0
            dx, dz = math.sin(math.radians(psi)), math.cos(math.radians(psi))
            rows.append([float(len(rows)), frame, tick, rel, 4500.0, ANCHOR_Y, 9800.0,
                         dx, 0.0, dz, 0.70, 4500.0, ANCHOR_Y, 9800.0, dx, 0.0, dz, mcam])
            tick += 16.0
            frame += 1.0
        return rows

    def _r3_burst_case(self, part, send, ack, t0, a_h, b_h, rows):
        _write_jsonl(_samples(part) / "control_recovery.jsonl", rows)

        def fn(scen):
            for row in scen:
                if row.get("ev") == "stop":
                    row["stop_send_h_ms"] = send
                    row["stop_ack_h_ms"] = ack
                    row["stop_recv_ms"] = t0
                if row.get("ev") == "pulse" and row.get("burst") == "A":
                    row["issued_h_ms"] = a_h + 40.0 * float(row["seq_n"])
                if row.get("ev") == "pulse" and row.get("burst") == "B":
                    row["issued_h_ms"] = b_h + 40.0 * (float(row["seq_n"]) - 10.0)
        _r1_scenario(part, fn)

    def test_r3_08_cam10_b_en_el_intervalo_no_prueba_inversion(self):
        """Punto 5 (hallazgo 5): B solo puede haber llegado en
        [t0+340, t0+435]; la respuesta de A en t0+368 no prueba que B
        llegara antes. La inversion tras el extremo tardio acredita."""
        rows = self._r3_recovery_rows(1570.0, 342.0, 358.0, 448.0)
        v = self._r3("b_intervalo", lambda p: self._r3_burst_case(p, 500.0, 595.0, 1570.0, 695.0, 935.0, rows))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r3_09_cam10_otra_ventana_pasa_y_b_seguro_antes_cae(self):
        """Punto 5, variante y control: otra ventana de 70 ms tambien
        PASA; si hasta la llegada mas tardia de B precede a la
        respuesta de A, CAM-10 cae por burst_b_before_a_response."""
        rows = self._r3_recovery_rows(2000.0, 300.0, 330.0, 430.0, a_deg=5.0)
        v = self._r3("b_ventana70", lambda p: self._r3_burst_case(p, 400.0, 470.0, 2000.0, 570.0, 780.0, rows))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

        v = self._r3("b_seguro", lambda p: self._r3_burst_case(p, 400.0, 470.0, 2000.0, 570.0, 500.0, rows))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "burst_b_before_a_response", v)

    def test_r3_10_cam10_desfase_de_reloj_de_un_frame_pasa(self):
        """Punto 5 (relojes): un desfase acumulado de 8 o de 12 ms
        entre tick y dtsum, dentro de un periodo de frame, PASA; un
        salto de 40 ms sigue en INCONCLUSO tick_dtsum_mismatch."""
        def desfase(ms):
            def mut(part):
                path = _samples(part) / "control_recovery.jsonl"
                rows = _read_jsonl(path)
                for row in rows[6:]:
                    row[3] -= ms
                _write_jsonl(path, rows)
            return mut
        v = self._r3("drift8", desfase(8.0))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        v = self._r3("drift12", desfase(12.0))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        v = self._r3("drift40", desfase(40.0))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "tick_dtsum_mismatch", v)

    def _r3_move_t1(self, part, paths):
        def fn(rows):
            for row in rows:
                if row.get("ev") == "state" and row.get("step") in (f"{p}_t1_pre" for p in paths):
                    row["read_nk"]["cam_dtsum_ms"] = 1400.0
                if row.get("ev") == "state" and row.get("step") in (f"{p}_t1_post" for p in paths):
                    row["read_nk"]["cam_dtsum_ms"] = 1450.0
                if row.get("ev") == "phase" and row.get("path") in paths and row.get("phase_k") == 1:
                    row["pre_dtsum_ms"] = 1400.0
                    row["post_dtsum_ms"] = 1450.0
        _r1_scenario(part, fn)
        shutil.copyfile(_samples(part) / "fix_t1.bmp", _samples(part) / "var_t1.bmp")

    def test_r3_11_cam08_fase_tarde_es_inconcluso_no_fallo_optico(self):
        """Punto 6 (hallazgo 6): var_t1 a 1400-1450 ms con ratio de
        fondo 1 da INCONCLUSO capture_phase_unaccredited, no FALLA."""
        v = self._r3("fase_tarde", lambda p: self._r3_move_t1(p, ("dof_var_6s",)))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "missing", v)
        self.assertEqual(checks["CAM-08"]["detail"], "capture_phase_unaccredited", v)

    def test_r3_12_cam08_ambas_fases_tarde_y_telemetria_que_si_cae(self):
        """Punto 6, variante y control: las dos fases tarde dan
        INCONCLUSO; con la fase tarde pero la telemetria del camino
        mal, el FALLA observado se conserva."""
        v = self._r3("fases_tarde", lambda p: self._r3_move_t1(p, ("dof_var_6s", "dof_fixed_6s")))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "missing", v)
        self.assertEqual(checks["CAM-08"]["detail"], "capture_phase_unaccredited", v)

        def telemetria(part):
            self._r3_move_t1(part, ("dof_var_6s",))
            def m(rows):
                rows[10]["sent_focus_dist_m"] += 5.0
            _mutate_path(part, "path_dof_var", m)
        v = self._r3("fase_telemetria", telemetria)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "fail", v)
        self.assertEqual(checks["CAM-08"]["detail"], "sent_dist_row_10", v)

    def test_r3_13_cam09_sin_ancla_de_captura_no_juzga_la_imagen(self):
        """Punto 6 en CAM-09: sin evento hud_during, o con el frame
        fuera de la horquilla, un BMP con quickbar da INCONCLUSO; la
        captura acreditada con quickbar sigue en FALLA."""
        def sin_evento(part):
            def es_la_captura_en_camino(fila):
                return fila.get("file") == "hud_during.bmp" and fila.get("ev") == "capture"
            _r1_drop_events(part, es_la_captura_en_camino)
            shutil.copyfile(_samples(part) / "hud_visible_ref.bmp", _samples(part) / "hud_during.bmp")
        v = self._r3("cam09_sin_evento", sin_evento)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "missing", v)

        def frame_fuera(part):
            def fn(rows):
                for row in rows:
                    if row.get("file") == "hud_during.bmp" and row.get("ev") == "capture":
                        row["frame"] = 1040.0
            _r1_scenario(part, fn)
            shutil.copyfile(_samples(part) / "hud_visible_ref.bmp", _samples(part) / "hud_during.bmp")
        v = self._r3("cam09_frame_fuera", frame_fuera)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "capture_frame_not_anchored", v)

        def acreditada_con_quickbar(part):
            shutil.copyfile(_samples(part) / "hud_visible_ref.bmp", _samples(part) / "hud_during.bmp")
        v = self._r3("cam09_quickbar", acreditada_con_quickbar)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "fail", v)
        self.assertEqual(checks["CAM-09"]["detail"], "quickbar_not_detected", v)

    def test_r3_14_e1_lleva_los_tres_escenarios_y_la_mascara_basal(self):
        """Punto 7 (cierre E1): el test E1 con el peer real contiene la
        orden de camino con el lease vencido, el cam_sample vivo al
        vencerlo y la entrada libre consumible en on_tick, y compara
        los auxiliares con su basal (basal | bits del preset)."""
        src = Path(__file__).read_text(encoding="utf-8")
        seg = src[src.index("def test_e2e_e1_real_peer"):src.index("# ---------------------------------------------------------------- ronda 1")]
        self.assertIn("scam_os_input.jsonl", seg)
        self.assertIn("input_ack_seq_n", seg)
        self.assertIn("sample_job_id", seg)
        self.assertIn("sample_rows_before_n", seg)
        self.assertGreaterEqual(seg.count("scam_path_start"), 2)
        self.assertIn("basal_aux", seg)
        self.assertIn("expected_aux", seg)
        self.assertNotIn('["aux_vis_mask"], 34.0', seg)

    def test_r3_15_mascara_de_auxiliares_contra_su_basal(self):
        """Punto 7, en el evaluador: con una basal de 35 (el bit 0 mas
        los dos del preset), la restauracion a 35 acredita CAM-09 y
        CAM-10; no se exige que los demas bits valgan 0."""
        def mut(part):
            for phase, step in (("SCAM-S3", "hud_preset"), ("SCAM-S3", "post_path_hud"),
                                ("SCAM-S5", "hud_preset"), ("SCAM-S5", "post_stop_state")):
                _r1_state(part, phase, step, aux_vis_mask=35.0, saved_aux_vis_mask=35.0)
        v = self._r3("aux_basal35", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "pass", v)
        self.assertEqual(checks["CAM-10"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r3_16_e9_las_cinco_construcciones_estan_reescritas(self):
        """Punto 8 (E9): las cinco construcciones compartidas con las
        pasadas de Claude estan rederivadas desde la regla; las cinco
        exentas (constantes del protocolo y forma de evidencia del
        brief) se conservan."""
        src = Path(__file__).read_text(encoding="utf-8")
        self.assertNotIn("hud" "[122]", src)
        self.assertNotIn("int(row[" '"seq_n"' "]) + 100", src)
        self.assertNotIn('"cam_dtsum_ms"]' ' = 900.0', src)
        self.assertNotIn("for phase, post_step" " in ((", src)
        self.assertNotIn("src[:" "src.index", src)
        # Las rederivadas: tick por el frame medio de la horquilla,
        # seq por enumeracion, dtsum desde la lectura de cierre, fases
        # desde las filas post presentes y docstring por particion.
        self.assertIn("tick_by_frame", src)
        self.assertIn("500 + offset", src)
        self.assertIn("closing[\"read_nk\"][\"cam_dtsum_ms\"]", src)
        self.assertIn("post_rows", src)
        self.assertIn("chunks = src.split", src)

    def _r3_seal_frames(self, part, sealed):
        scen = _read_jsonl(_scenario_path(part))
        ids = {}
        for row in scen:
            if row.get("phase") == "SCAM-S1" and row.get("step") in sealed:
                ids[row["step"]] = row.get("op_id")
        bridge = _samples(part) / "bridge.jsonl"
        rows = _read_jsonl(bridge)
        for row in rows:
            if row.get("ev") != "result":
                continue
            for step, op_id in ids.items():
                if row.get("op_id") == op_id:
                    recv, done = sealed[step]
                    row["result"]["frame_recv"] = recv
                    row["result"]["frame_done"] = done
        _write_jsonl(bridge, rows)

    def _r3_trio(self, part, post_frame):
        _r1_state(part, "SCAM-S1", "pre_1", frame=66.0)
        _r1_state(part, "SCAM-S1", "post_1", frame=float(post_frame))
        self._r3_seal_frames(part, {"pre_1": (65.0, 66.0), "neg_1": (66.0, 67.0),
                                    "post_1": (float(post_frame), float(post_frame))})

    def test_r3_17_result_nuevo_con_lectura_vieja_cae(self):
        """Punto 9 (hallazgo 7, identidad): post_1 con un RESULT nuevo
        (frame_recv=frame_done=68) cuyo payload es la lectura del
        frame 66 cae; el trio fresco (66, negativa hasta 67, post en
        68) PASA."""
        v = self._r3("trio_fresco", lambda p: self._r3_trio(p, 68.0))
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

        v = self._r3("trio_viejo", lambda p: self._r3_trio_viejo(p))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_stale_payload", v)

    def _r3_trio_viejo(self, part):
        _r1_state(part, "SCAM-S1", "pre_1", frame=66.0)
        _r1_state(part, "SCAM-S1", "post_1", frame=66.0)
        self._r3_seal_frames(part, {"pre_1": (65.0, 66.0), "neg_1": (66.0, 67.0),
                                    "post_1": (68.0, 68.0)})

    def test_r3_18_payload_fuera_del_intervalo_sellado_cae(self):
        """Punto 9, variante: un payload posterior al frame_done
        sellado tambien es una lectura que no es de esta operacion."""
        def futuro(part):
            _r1_state(part, "SCAM-S1", "pre_1", frame=66.0)
            _r1_state(part, "SCAM-S1", "post_1", frame=70.0)
            self._r3_seal_frames(part, {"pre_1": (65.0, 66.0), "neg_1": (66.0, 67.0),
                                        "post_1": (68.0, 68.0)})
        v = self._r3("trio_futuro", futuro)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_stale_payload", v)

        def en_el_borde(part):
            _r1_state(part, "SCAM-S1", "pre_1", frame=66.0)
            _r1_state(part, "SCAM-S1", "post_1", frame=67.0)
            self._r3_seal_frames(part, {"pre_1": (65.0, 66.0), "neg_1": (66.0, 67.0),
                                        "post_1": (67.0, 68.0)})
        v = self._r3("trio_borde", en_el_borde)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "pass", v)

    def test_r3_19_cam10_parar_el_trabajo_de_s3_cae(self):
        """Punto 10 (hallazgo 8, identidad): el arranque de S5 devuelve
        el trabajo retenido de S3 y el job_stop lo para con un RESULT
        ya terminal: CAM-10 cae. La sana de S5 PASA."""
        v = self._r3("s5_sana", lambda p: None)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

        def retenido(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "path_s5_start":
                        row["read_sk"] = {"job": "job-hud"}
                    if row.get("ev") == "op" and row.get("step") == "stop_op":
                        row["read_sk"] = {"job": "job-hud", "state": "done", "reason": ""}
                    if row.get("ev") == "stop":
                        row["job_id"] = "job-hud"
            _r1_scenario(part, fn)
        v = self._r3("s5_retenido", retenido)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertIn("job", checks["CAM-10"]["detail"], v)

    def test_r3_20_cam10_sin_transicion_a_stopped_y_argumento_ajeno(self):
        """Punto 10, variantes: un RESULT con el trabajo de S5 pero en
        estado done (sin transicion a stopped) cae, y un argumento de
        job_stop que nombra otro trabajo tambien."""
        def sin_transicion(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "stop_op":
                        row["read_sk"] = {"job": "cam-job", "state": "done", "reason": ""}
            _r1_scenario(part, fn)
        v = self._r3("s5_done", sin_transicion)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "stop_job_not_stopped", v)

        def argumento_ajeno(part):
            bridge = _samples(part) / "bridge.jsonl"
            rows = _read_jsonl(bridge)
            for row in rows:
                if row.get("ev") == "enq" and row.get("op_id") == "SCAM-S5-stop_op":
                    row["args"] = wire.pack_payload(scalars_str={"job": "job-hud"})
            _write_jsonl(bridge, rows)
        v = self._r3("s5_argumento", argumento_ajeno)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "stop_job_argument_mismatch", v)

    # ---------------------------------------------------------------- ronda 4 (test_r4_*)
    def _r4(self, label, mutate):
        return self._verdict_with(f"r4_{label}", mutate)

    def _r4_sin_result(self, part, phase, step, status, vaciar=False):
        """Una orden cuyo transporte termina sin RESULT: el resumen trae
        el estado terminal y el puente, un expire o un lost en su lugar."""
        def fn(rows):
            for row in rows:
                if row.get("ev") == "op" and row.get("phase") == phase and row.get("step") == step:
                    row["status"] = status
                    row["reason"] = "result_timeout" if status == "timeout" else ""
                    if vaciar:
                        row["read_nk"] = {}
                        row["read_sk"] = {}
        _r1_scenario(part, fn)
        bridge = _samples(part) / "bridge.jsonl"
        oid = f"{phase}-{step}"
        rows = [r for r in _read_jsonl(bridge)
                if not (r.get("ev") == "result" and r.get("op_id") == oid)]
        rows.append({"ev": "expire" if status == "timeout" else "lost",
                     "op_id": oid, "peer": "client"})
        _write_jsonl(bridge, rows)

    def test_r4_01_p0_expire_en_s4_no_pisa_cam01(self):
        """Punto 1 (P0): con expire en los lost del puente, la negativa
        expirada de S4 no deja la procedencia sin enlazar y CAM-01 PASA."""
        v = self._r4("p0_expire_s4", lambda p: self._r3_expire(p, "SCAM-S4", "neg_2"))
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "pass", v)

    def test_r4_02_p2_payload_previo_a_la_recepcion_sellada(self):
        """Punto 1 (P2): pre_1 trae el frame 64 con el RESULT sellado en
        (65, 66): el payload precede a la recepcion y CAM-01 cae."""
        def mut(part):
            _r1_state(part, "SCAM-S1", "pre_1", frame=64.0)
            self._r3_seal_frames(part, {"pre_1": (65.0, 66.0)})
        v = self._r4("p2_payload", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_stale_payload", v)

    def test_r4_03_p6_post_previo_al_fin_de_la_negativa(self):
        """Punto 1 (P6): neg_1 sellada (66, 68) y post_1 con payload 67
        sellado (67, 67): cada fila esta en su intervalo, pero el post
        precede al fin de la negativa y CAM-01 cae."""
        def mut(part):
            _r1_state(part, "SCAM-S1", "post_1", frame=67.0)
            self._r3_seal_frames(part, {"neg_1": (66.0, 68.0), "post_1": (67.0, 67.0)})
        v = self._r4("p6_post", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_stale_payload", v)

    def test_r4_04_p7_frames_sellados_en_la_fila_del_resumen(self):
        """Punto 1 (P7): sin sellar el puente, el resumen de post_1 copia
        frame_recv = frame_done = 68 y su payload es del frame 66."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("phase") == "SCAM-S1" and row.get("step") == "post_1":
                        row["read_nk"]["frame"] = 66.0
                        row["frame_recv"] = 68.0
                        row["frame_done"] = 68.0
            _r1_scenario(part, fn)
        v = self._r4("p7_resumen", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "provenance_stale_payload", v)

    def test_r4_05_c7_negativa_cerrada_expirada(self):
        """Punto 1 (C7): neg_0 expirada da INCONCLUSO closed_cam_timeout,
        no una negativa incumplida."""
        v = self._r4("c7_neg0", lambda p: self._r3_expire(p, "SCAM-S1", "neg_0"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "closed_cam_timeout", v)

    def test_r4_06_c9_orden_sin_cliente_expirada(self):
        """Punto 1 (C9): no_client_pose expirada da INCONCLUSO
        no_client_pose_timeout."""
        v = self._r4("c9_nc_pose", lambda p: self._r3_expire(p, "SCAM-S1", "no_client_pose"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "no_client_pose_timeout", v)

    def test_r4_07_a6_result_de_reaplicacion_expirado(self):
        """Punto 1 (A6): el RESULT de la reaplicacion de P_roll expira y
        CAM-02 queda en INCONCLUSO p_roll_applied_timeout."""
        def mut(part):
            self._r3_as_apply_ops(part)
            _r1_op(part, "SCAM-S1", "p_roll_applied", status="timeout", reason="result_timeout")
            bridge = _samples(part) / "bridge.jsonl"
            rows = [r for r in _read_jsonl(bridge)
                    if not (r.get("ev") == "result" and r.get("op_id") == "apply-P_roll")]
            rows.append({"ev": "expire", "op_id": "apply-P_roll", "peer": "client"})
            _write_jsonl(bridge, rows)
        v = self._r4("a6_apply_expire", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "missing", v)
        self.assertEqual(checks["CAM-02"]["detail"], "p_roll_applied_timeout", v)

    def test_r4_08_o1_lectura_previa_tras_la_primera_orden(self):
        """Punto 1 (O1): pre_nc registrada detras de no_client_free ya no
        precede a las seis ordenes y CAM-01 da no_client_order."""
        def mut(part):
            def fn(rows):
                idx_pre = next(i for i, r in enumerate(rows) if r.get("step") == "pre_nc")
                previa = rows.pop(idx_pre)
                idx_free = next(i for i, r in enumerate(rows) if r.get("step") == "no_client_free")
                rows.insert(idx_free + 1, previa)
            _r1_scenario(part, fn)
        v = self._r4("o1_orden", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "no_client_order", v)

    def test_r4_09_k2_post_nc_con_el_reloj_anterior_al_pre(self):
        """Punto 1 (K2): post_nc con frame 994 frente a pre_nc en 1000 da
        INCONCLUSO no_client_clock_order."""
        v = self._r4("k2_reloj", lambda p: _r1_state(p, "SCAM-S1", "post_nc", frame=994.0))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "no_client_clock_order", v)

    def test_r4_10_a2_result_de_reaplicacion_no_done(self):
        """Punto 1 (A2): el RESULT de reaplicar P_roll llega rechazado
        con la lectura intacta y CAM-02 cae por no completado."""
        def mut(part):
            self._r3_as_apply_ops(part)
            _r1_op(part, "SCAM-S1", "p_roll_applied", status="rejected", reason="rejected_by_peer")
        v = self._r4("a2_rejected", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "p_roll_applied_apply_not_done", v)

    def test_r4_11_a4_verbo_del_result_de_reaplicacion(self):
        """Punto 1 (A4): el RESULT de p_roll_applied trae otro verbo y
        CAM-02 no lo consume: INCONCLUSO no_p_roll_applied."""
        def mut(part):
            self._r3_as_apply_ops(part)
            _r1_op(part, "SCAM-S1", "p_roll_applied", verb="scam_pose_save")
        v = self._r4("a4_verbo", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "missing", v)
        self.assertEqual(checks["CAM-02"]["detail"], "no_p_roll_applied", v)

    def test_r4_12_a5_result_de_reaplicacion_sin_nombre(self):
        """Punto 1 (A5): el RESULT de reaplicar no trae nombre de pose y
        CAM-02 da INCONCLUSO no_p_roll_applied."""
        def mut(part):
            self._r3_as_apply_ops(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "p_roll_applied":
                        row["read_sk"] = {}
            _r1_scenario(part, fn)
        v = self._r4("a5_sin_nombre", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "missing", v)
        self.assertEqual(checks["CAM-02"]["detail"], "no_p_roll_applied", v)

    def test_r4_13_m08c_la_telemetria_del_fijo_manda_sobre_la_fase(self):
        """Punto 1 (M08c): con la fase t1 tarde, la telemetria mala del
        camino fijo se juzga antes que la optica y CAM-08 cae."""
        def mut(part):
            self._r3_move_t1(part, ("dof_var_6s",))
            def m(rows):
                rows[10]["sent_focus_dist_m"] += 5.0
            _mutate_path(part, "path_dof_fix", m)
        v = self._r4("m08c_telemetria", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-08"]["status"], "fail", v)
        self.assertEqual(checks["CAM-08"]["detail"], "fix_dist_row_10", v)

    def _r4_hud_during_visible(self, part):
        shutil.copyfile(_samples(part) / "hud_visible_ref.bmp", _samples(part) / "hud_during.bmp")

    def test_r4_14_m09p3_captura_sin_dtsum_da_missing(self):
        """Punto 1 (M09p3): con la quickbar en la captura y pre_cap sin
        cam_dtsum_ms, CAM-09 queda en INCONCLUSO bad_capture_dtsum."""
        def mut(part):
            self._r4_hud_during_visible(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "pre_cap":
                        row["read_nk"].pop("cam_dtsum_ms", None)
            _r1_scenario(part, fn)
        v = self._r4("m09p3_dtsum", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "bad_capture_dtsum", v)

    def test_r4_15_m09p4_referencia_limpia_movida_da_missing(self):
        """Punto 1 (M09p4): la referencia limpia se mueve 1 m de la pose
        de la captura y CAM-09 da clean_ref_pose_moved."""
        def mut(part):
            self._r4_hud_during_visible(part)
            _r1_state(part, "SCAM-S3", "clean_ref_state", x_m=4501.0, eng_x_m=4501.0)
        v = self._r4("m09p4_movida", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "clean_ref_pose_moved", v)

    def test_r4_16_m09p5_sin_referencia_limpia_da_missing(self):
        """Punto 1 (M09p5): sin lectura clean_ref_state, CAM-09 da
        INCONCLUSO no_clean_ref_state."""
        def mut(part):
            self._r4_hud_during_visible(part)
            _r1_drop_events(part, lambda r: r.get("ev") == "state" and r.get("step") == "clean_ref_state")
        v = self._r4("m09p5_sin_ref", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "no_clean_ref_state", v)

    def test_r4_17_m09p6_referencia_sin_fov_da_missing(self):
        """Punto 1 (M09p6): clean_ref_state sin fov_rad da INCONCLUSO
        bad_clean_ref_pose."""
        def mut(part):
            self._r4_hud_during_visible(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "clean_ref_state":
                        row["read_nk"].pop("fov_rad", None)
            _r1_scenario(part, fn)
        v = self._r4("m09p6_fov", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "bad_clean_ref_pose", v)

    def test_r4_18_m09p7_referencia_con_ruido_da_missing(self):
        """Punto 1 (M09p7): la repeticion de la referencia limpia trae
        otra imagen (MAD >= 1) y CAM-09 da noise:clean_ref."""
        def mut(part):
            self._r4_hud_during_visible(part)
            shutil.copyfile(_samples(part) / "dof_ctrl_noblur.bmp",
                            _samples(part) / "hud_clean_ref_repeat.bmp")
        v = self._r4("m09p7_ruido", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "noise:clean_ref", v)

    def test_r4_19_m09p8_ventana_de_la_captura_da_missing(self):
        """Punto 1 (M09p8): el evento de la captura trae una ventana de
        800 px y CAM-09 da window:hud_during."""
        def mut(part):
            self._r4_hud_during_visible(part)
            _set_event(part, "capture", "SCAM-S3", "hud_during", window_w=800)
        v = self._r4("m09p8_ventana", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-09"]["status"], "missing", v)
        self.assertEqual(checks["CAM-09"]["detail"], "window:hud_during", v)

    def test_r4_20_s2_acuse_a_medio_ms_del_puente(self):
        """Punto 1 (S2): el acuse del resumen a 549,5 ms con el del
        puente a 550 esta dentro del 1 ms de tolerancia y CAM-10 PASA."""
        v = self._r4("s2_ack549", lambda p: self._r3_set_summary_ack(p, 549.5))
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

    def test_r4_21_i1_arranque_s5_con_el_trabajo_retenido_de_s3(self):
        """Punto 1 (I1): el arranque de S5 devuelve el trabajo de S3 y el
        job_stop lo para ya parado: CAM-10 cae por el ancla de S5."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "path_s5_start":
                        row["read_sk"] = {"job": "job-hud"}
                    if row.get("ev") == "op" and row.get("step") == "stop_op":
                        row["read_sk"] = {"job": "job-hud", "state": "stopped", "reason": ""}
                    if row.get("ev") == "stop":
                        row["job_id"] = "job-hud"
            _r1_scenario(part, fn)
        v = self._r4("i1_retenido", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "s5_path_job_mismatch", v)

    def test_r4_22_i2_result_de_stop_con_otro_trabajo(self):
        """Punto 1 (I2): el RESULT del job_stop nombra otro trabajo y
        CAM-10 cae por stop_job_mismatch."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "stop_op":
                        row["read_sk"] = {"job": "otro", "state": "stopped", "reason": ""}
            _r1_scenario(part, fn)
        v = self._r4("i2_otro", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "stop_job_mismatch", v)

    def test_r4_23_i4_resumen_de_stop_con_otro_trabajo(self):
        """Punto 1 (I4): el resumen ev=stop trae otro job_id con el
        RESULT sano y CAM-10 cae por stop_job_mismatch."""
        v = self._r4("i4_resumen", lambda p: _set_event(p, "stop", "SCAM-S5", "stop", job_id="otro"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "stop_job_mismatch", v)

    def test_r4_24_i6_muestra_de_s5_con_un_trabajo_ajeno(self):
        """Punto 1 (I6): el cam_sample de S5 se ancla con el trabajo del
        camino, o con el retenido de S3, y CAM-10 cae en los dos casos."""
        def con_el_del_camino(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "sample_s5_start":
                        row["read_sk"] = {"job": "cam-job"}
            _r1_scenario(part, fn)
        v = self._r4("i6_sample_camino", con_el_del_camino)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "s5_sample_job_mismatch", v)

        def con_el_de_s3(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "sample_s5_start":
                        row["read_sk"] = {"job": "job-hud"}
            _r1_scenario(part, fn)
        v = self._r4("i6_sample_s3", con_el_de_s3)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "s5_sample_job_mismatch", v)

    def test_r4_25_i7_la_identidad_manda_sobre_las_ausencias(self):
        """Punto 1 (I7): sin pulsos B y con el RESULT en done, la
        identidad se juzga antes que las ausencias: stop_job_not_stopped."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "stop_op":
                        row["read_sk"] = {"job": "cam-job", "state": "done", "reason": ""}
            _r1_scenario(part, fn)
            _r1_drop_events(part, lambda r: r.get("ev") == "pulse" and r.get("burst") == "B")
        v = self._r4("i7_identidad", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "stop_job_not_stopped", v)

    def test_r4_26_i8_result_de_stop_sin_job(self):
        """Punto 1 (I8): el RESULT del job_stop no trae job y CAM-10 da
        INCONCLUSO no_stop_job."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "stop_op":
                        row["read_sk"] = {"state": "stopped", "reason": ""}
            _r1_scenario(part, fn)
        v = self._r4("i8_sin_job", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "no_stop_job", v)

    def test_r4_27_i9_result_de_stop_sin_estado(self):
        """Punto 1 (I9): el RESULT del job_stop no trae state y CAM-10
        da INCONCLUSO no_stop_job_state."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "stop_op":
                        row["read_sk"] = {"job": "cam-job", "reason": ""}
            _r1_scenario(part, fn)
        v = self._r4("i9_sin_estado", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "no_stop_job_state", v)

    def test_r4_28_i10_arranque_de_s5_sin_job(self):
        """Punto 1 (I10): el arranque de camino de S5 no trae job y
        CAM-10 da INCONCLUSO no_s5_path_anchor."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "path_s5_start":
                        row["read_sk"] = {}
            _r1_scenario(part, fn)
        v = self._r4("i10_sin_job", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "no_s5_path_anchor", v)

    def test_r4_29_i11_muestra_de_s5_sin_job(self):
        """Punto 1 (I11): el cam_sample de S5 no trae job y CAM-10 da
        INCONCLUSO no_s5_sample_anchor."""
        def mut(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "sample_s5_start":
                        row["read_sk"] = {}
            _r1_scenario(part, fn)
        v = self._r4("i11_sin_job", mut)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "missing", v)
        self.assertEqual(checks["CAM-10"]["detail"], "no_s5_sample_anchor", v)

    def test_r4_30_f2_el_periodo_es_el_frame_mas_largo(self):
        """Punto 1 (F2): un frame de 33 ms en el que dtsum avanza 13 deja
        un desfase de 20 ms, dentro del periodo maximo, y CAM-10 PASA."""
        def mut(part):
            path = _samples(part) / "control_recovery.jsonl"
            rows = _read_jsonl(path)
            for row in rows[31:]:
                row[2] += 17.0
                row[3] -= 3.0
            _write_jsonl(path, rows)
        v = self._r4("f2_periodo_max", mut)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

    def test_r4_31_f3_desfase_de_exactamente_un_periodo(self):
        """Punto 1 (F3): un desfase acumulado de 16 ms, exactamente un
        periodo de frame, no suspende CAM-10."""
        def mut(part):
            path = _samples(part) / "control_recovery.jsonl"
            rows = _read_jsonl(path)
            for row in rows[6:]:
                row[3] -= 16.0
            _write_jsonl(path, rows)
        v = self._r4("f3_un_periodo", mut)
        self.assertEqual(_checks_by_id(v)["CAM-10"]["status"], "pass", v)

    def test_r4_32_b3_inversion_transitoria_antes_del_extremo_tardio(self):
        """Punto 1 (B3): la vista cae 3 grados entre los rel 400 y 432 y
        vuelve al pico desde el 448, ya pasado el extremo tardio de B
        (rel 435): tras ese extremo no hay inversion y CAM-10 cae."""
        rows = []
        tick, frame = 1570.0, 5000.0
        while tick <= 1570.0 + 640.0:
            rel = tick - 1570.0
            psi = 0.0
            if rel >= 358.0:
                psi = 4.8
            if 400.0 <= rel <= 432.0:
                psi = 1.8
            dx, dz = math.sin(math.radians(psi)), math.cos(math.radians(psi))
            mcam = 0.0 if rel >= 342.0 else 1.0
            rows.append([float(len(rows)), frame, tick, rel, 4500.0, ANCHOR_Y, 9800.0,
                         dx, 0.0, dz, 0.70, 4500.0, ANCHOR_Y, 9800.0, dx, 0.0, dz, mcam])
            tick += 16.0
            frame += 1.0
        v = self._r4("b3_transitoria",
                     lambda p: self._r3_burst_case(p, 500.0, 595.0, 1570.0, 695.0, 935.0, rows))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "no_burst_b_inversion", v)

    def test_r4_33_b4_extremo_tardio_igual_a_la_respuesta_de_a(self):
        """Punto 1 (B4): si hasta la llegada mas tardia de B coincide con
        el tick de la respuesta de A, B precede con seguridad y CAM-10
        cae por burst_b_before_a_response."""
        rows = self._r3_recovery_rows(1570.0, 342.0, 358.0, 448.0)
        v = self._r4("b4_igual",
                     lambda p: self._r3_burst_case(p, 500.0, 595.0, 1570.0, 695.0, 868.0, rows))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-10"]["status"], "fail", v)
        self.assertEqual(checks["CAM-10"]["detail"], "burst_b_before_a_response", v)

    def test_r4_34_terminal_de_transporte_nunca_da_falla(self):
        """Punto 2 (y C6 de la mutacion): el fixture cuyo transporte
        termina sin RESULT es INCONCLUSO con o sin lectura, nunca FALLA;
        un fixture done con la camara inactiva sigue cayendo."""
        v = self._r4("term_sana", lambda p: None)
        self.assertEqual(_checks_by_id(v)["CAM-01"]["status"], "pass", v)

        v = self._r4("term_timeout_intacta",
                     lambda p: self._r4_sin_result(p, "SCAM-S0", "fixture", "timeout"))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "fixture_timeout", v)

        v = self._r4("term_timeout_vacia",
                     lambda p: self._r4_sin_result(p, "SCAM-S0", "fixture", "timeout", vaciar=True))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "fixture_timeout", v)

        v = self._r4("term_lost_vacia",
                     lambda p: self._r4_sin_result(p, "SCAM-S0", "fixture", "lost", vaciar=True))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "fixture_lost", v)

        def done_inactiva(part):
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "fixture":
                        row["read_nk"]["active_b"] = 0.0
            _r1_scenario(part, fn)
        v = self._r4("term_done_inactiva", done_inactiva)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "fail", v)
        self.assertEqual(checks["CAM-01"]["detail"], "fixture_cam_inactive", v)

    def test_r4_35_arranque_de_camino_expirado_es_inconcluso(self):
        """Punto 2: path_1_start expira sin RESULT y con la lectura
        vacia; sin trabajo que anclar, CAM-01 da INCONCLUSO, no FALLA."""
        v = self._r4("term_path1",
                     lambda p: self._r4_sin_result(p, "SCAM-S2", "path_1_start", "timeout", vaciar=True))
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-01"]["status"], "missing", v)
        self.assertEqual(checks["CAM-01"]["detail"], "path_1_start_timeout", v)

    def test_r4_36_los_tres_casos_medidos_de_mat2(self):
        """Punto 3: la direccion desde Euler reproduce el mat[2] medido
        en el log del 24-nov a 1e-6 en los tres casos."""
        self.assertTrue(hasattr(s_cam_eval, "_dir_from_euler"))
        casos = (
            (30.0, 15.0, (0.4829629, 0.2588190, 0.8365163)),
            (179.0, -4.0, (0.0174097, -0.0697565, -0.9974121)),
            (70.0, 15.0, (0.9076734, 0.2588190, 0.3303660)),
        )
        for yaw, pitch, medido in casos:
            with self.subTest(yaw=yaw, pitch=pitch):
                dado = s_cam_eval._dir_from_euler(yaw, pitch)
                for obtenido, esperado in zip(dado, medido):
                    self.assertAlmostEqual(obtenido, esperado, delta=1e-6)

    def test_r4_37_sana_con_la_convencion_medida_pasa(self):
        """Punto 3: la corrida sana regenerada con la convencion medida
        acredita CAM-02, CAM-04 y CAM-05 y cierra en PASA."""
        v = self._r4("sana_medida", lambda p: None)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "pass", v)
        self.assertEqual(checks["CAM-04"]["status"], "pass", v)
        self.assertEqual(checks["CAM-05"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r4_38_guardado_sin_celdas_se_juzga_por_la_direccion(self):
        """Punto 3: sin celdas en el guardado, la reaplicacion sana pasa
        por su direccion; una reaplicacion girada sigue cayendo."""
        v = self._r4("sin_celdas", self._r2_save10)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

        def girada(part):
            self._r2_save10(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "p_roll_applied":
                        nk = row["read_nk"]
                        nk["yaw_deg"] = 50.0
                        mat = ypr_matrix(nk["yaw_deg"], nk["pitch_deg"], nk["roll_deg"])
                        nk["eng_dx"], nk["eng_dy"], nk["eng_dz"] = mat[2][0], mat[2][1], mat[2][2]
                        for r in range(3):
                            for c in range(3):
                                nk[f"m{r}{c}"] = mat[r][c]
            _r1_scenario(part, fn)
        v = self._r4("sin_celdas_girada", girada)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "p_roll_theta_deg", v)

    def test_r4_39_vista_un_frame_por_detras_y_control_de_dos(self):
        """Punto 4a: la sana lleva la vista un frame por detras y PASA;
        con dos frames de retraso, CAM-03 cae por cam_eng_mismatch."""
        v = self._r4("lag_sana", lambda p: None)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-03"]["status"], "pass", v)
        self.assertEqual(checks["CAM-05"]["status"], "pass", v)

        def dos_frames(part):
            def m(rows):
                origen = [(r["x_m"], r["y_m"], r["z_m"], r["m20"], r["m21"], r["m22"]) for r in rows]
                for i, row in enumerate(rows):
                    src = origen[i - 2] if i >= 2 else origen[0]
                    row["eng_x_m"], row["eng_y_m"], row["eng_z_m"] = src[0], src[1], src[2]
                    row["eng_dx"], row["eng_dy"], row["eng_dz"] = src[3], src[4], src[5]
            _mutate_path(part, "path_catmull_scripted", m)
        v = self._r4("lag_dos", dos_frames)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-03"]["status"], "fail", v)
        self.assertEqual(checks["CAM-03"]["detail"], "path_catmull_scripted_cam_eng_mismatch", v)

    def test_r4_40_result_con_la_vista_del_frame_anterior_no_falla(self):
        """Punto 4a: el RESULT de reaplicar trae las eng_* de la pose
        anterior (a mas de 10 m) y CAM-02 no cae; si el nodo del RESULT
        es el que se desvia, CAM-02 cae por la posicion del nodo."""
        def vista_anterior(part):
            self._r3_as_apply_ops(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "p_roll_applied":
                        row["read_nk"]["eng_x_m"] = 4520.0
                        row["read_nk"]["eng_y_m"] = ANCHOR_Y
                        row["read_nk"]["eng_z_m"] = 9806.0
            _r1_scenario(part, fn)
        v = self._r4("result_vista_previa", vista_anterior)
        self.assertEqual(_checks_by_id(v)["CAM-02"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

        def nodo_desviado(part):
            self._r3_as_apply_ops(part)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "op" and row.get("step") == "p_roll_applied":
                        row["read_nk"]["x_m"] = 4520.0
                        row["read_nk"]["eng_x_m"] = 4520.0
            _r1_scenario(part, fn)
        v = self._r4("result_nodo_desviado", nodo_desviado)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-02"]["status"], "fail", v)
        self.assertEqual(checks["CAM-02"]["detail"], "p_roll_cam_pos_err", v)

    def test_r4_41_el_camino_del_motor_sale_del_origen(self):
        """Punto 4c: el camino del motor arranca en el origen y avanza
        por la recta sin llegar; CAM-05 no cambia, el modo elegido sigue
        scripted y la comparativa dice que sale del origen."""
        def desde_el_origen(part):
            def m(rows):
                n = len(rows)
                for i, row in enumerate(rows):
                    s = 0.95 * i / float(n - 1)
                    row["eng_x_m"] *= s
                    row["eng_y_m"] *= s
                    row["eng_z_m"] *= s
            _mutate_path(part, "path_engine_interp", m)
        v = self._r4("engine_origen", desde_el_origen)
        checks = _checks_by_id(v)
        self.assertEqual(checks["CAM-05"]["status"], "pass", v)
        comp = (v.get("metrics") or {}).get("interp_comparison") or {}
        self.assertEqual(comp.get("selected_mode"), "scripted", v)
        self.assertEqual(comp.get("engine_starts_from_origin"), True, v)
        self.assertEqual(comp.get("engine_passes_b2_b"), False, v)

    def test_r4_42_recorrido_honesto_a_40ms_y_un_frame_de_73(self):
        """Punto 4d: un recorrido de 6 s a 40 ms por frame (151 filas)
        acredita CAM-03 sin minimo de filas, y un hueco de 73 ms en el
        dtsum no lo suspende."""
        def a_40ms(part):
            _write_path_jsonl(_samples(part) / "path_catmull_scripted.jsonl",
                              _path_rows("short_arc_6s", "catmull_rom", "slerp", "short_arc", PATH_DURATION_MS, 151))
            _write_path_jsonl(_samples(part) / "path_linear_hud.jsonl",
                              _path_rows("linear_hud_6s", "linear", "ypr", "linear_hud", PATH_DURATION_MS, 151))
        v = self._r4("cam03_40ms", a_40ms)
        self.assertEqual(_checks_by_id(v)["CAM-03"]["status"], "pass", v)

        def con_73ms(part):
            a_40ms(part)
            def m(rows):
                for row in rows[75:]:
                    row["tick_ms"] += 33.0
                    row["dtsum_ms"] += 33.0
            _mutate_path(part, "path_catmull_scripted", m)
        v = self._r4("cam03_73ms", con_73ms)
        self.assertEqual(_checks_by_id(v)["CAM-03"]["status"], "pass", v)

    def test_r4_43_camino_de_foco_a_40ms_acredita_cam08(self):
        """Punto 4d en CAM-08: los dos caminos de foco a 40 ms por frame
        (151 filas) cubren las fases a ese periodo y CAM-08 PASA."""
        def a_40ms(part):
            _write_path_jsonl(_samples(part) / "path_dof_var.jsonl", _dof_rows("dof_var_6s", 151))
            _write_path_jsonl(_samples(part) / "path_dof_fix.jsonl", _dof_rows("dof_fixed_6s", 151))
        v = self._r4("cam08_40ms", a_40ms)
        self.assertEqual(_checks_by_id(v)["CAM-08"]["status"], "pass", v)
        self.assertEqual(v["exit_code"], 0, v)

    def test_r4_44_tick_de_captura_a_un_periodo_de_su_fila(self):
        """Punto 4d en CAM-09: a 40 ms por frame, un capture_tick_ms a
        20 ms de su fila ancla la pose dentro de un periodo medido."""
        def mut(part):
            hud = _path_rows("linear_hud_6s", "linear", "ypr", "linear_hud", PATH_DURATION_MS, 151)
            _write_path_jsonl(_samples(part) / "path_linear_hud.jsonl", hud)
            def nk_of(r):
                return _pose_nk(r["x_m"], r["y_m"], r["z_m"], r["yaw_deg"], r["pitch_deg"],
                                r["roll_deg"], r["fov_rad"], cam_dtsum=r["dtsum_ms"],
                                frame=int(r["frame"]), tick=r["tick_ms"], aux=0.0)
            def fn(rows):
                for row in rows:
                    if row.get("ev") == "state" and row.get("step") == "pre_cap":
                        row["read_nk"] = nk_of(hud[49])
                    if row.get("ev") == "state" and row.get("step") == "post_cap":
                        row["read_nk"] = nk_of(hud[52])
                    if row.get("ev") == "state" and row.get("step") == "clean_ref_state":
                        row["read_nk"] = nk_of(hud[50])
                    if row.get("ev") == "capture" and row.get("file") == "hud_during.bmp":
                        row.pop("frame", None)
                        row["capture_tick_ms"] = hud[50]["tick_ms"] + 20.0
            _r1_scenario(part, fn)
        v = self._r4("cam09_tick40", mut)
        self.assertEqual(_checks_by_id(v)["CAM-09"]["status"], "pass", v)

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
