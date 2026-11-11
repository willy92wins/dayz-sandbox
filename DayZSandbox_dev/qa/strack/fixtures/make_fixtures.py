"""Generador determinista de fixtures sinteticas offline para S-track·1 (brief §3 y CONTRACT.md).

Genera:
- pasa: todo PASA, con desfase verdadero de calibracion k = 1 (no 0), y negativas delay1/roll en `negativas`.
- delay1: retraso de un frame en las corridas positivas -> FALLA (exit_code = 1).
- calib_pm1: asociacion de imagen desplazada +-1 frame en calibracion -> calibracion no pasa (INCONCLUSO).
- low_coverage: cobertura de deteccion < COVERAGE_MIN -> INCONCLUSO (exit_code = 2).
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

SEED = 20261110
IMAGE_W = 1920
IMAGE_H = 1080
FOV_RAD = 1.0471976  # 60 deg vertical
FOCAL_V = (0.5 * IMAGE_H) / math.tan(0.5 * FOV_RAD)

_BG_CACHE = None


def _get_panorama():
    """Construye un fondo panoramico determinista con textura horizontal rica para correlacion de bandas."""
    global _BG_CACHE
    if _BG_CACHE is not None:
        return _BG_CACHE
    rng = np.random.default_rng(SEED)
    pano_w = IMAGE_W + 1200
    xs = np.arange(pano_w, dtype=np.float32)[None, :]
    ys = np.arange(IMAGE_H, dtype=np.float32)[:, None]

    horiz = (
        28.0 * np.sin(2.0 * math.pi * xs / 137.0)
        + 22.0 * np.cos(2.0 * math.pi * xs / 61.0 + 0.7)
        + 16.0 * np.sin(2.0 * math.pi * xs / 29.0 + 1.4)
        + 12.0 * np.cos(2.0 * math.pi * xs / 311.0 - 0.5)
    )
    # Ruido horizontal suave (invariante por filas dentro de bandas, unico en X)
    noise_1d = rng.normal(0.0, 14.0, size=(1, pano_w)).astype(np.float32)
    kernel = np.array([0.1, 0.2, 0.4, 0.2, 0.1], dtype=np.float32)
    smooth_1d = np.convolve(noise_1d[0], kernel, mode="same")[None, :]
    vert_mod = 1.0 + 0.15 * np.sin(2.0 * math.pi * ys / 180.0)
    pano = np.clip(126.0 + (horiz + smooth_1d) * vert_mod, 25.0, 230.0).astype(np.float32)
    _BG_CACHE = pano
    return pano


def _slice_background(shift_left_px):
    """Extrae una vista 1920x1080 del panorama desplazada hacia la izquierda en shift_left_px (subpixel)."""
    pano = _get_panorama()
    base_x0 = 400.0 + float(shift_left_px)
    i0 = int(math.floor(base_x0))
    frac = float(base_x0 - i0)
    i0 = max(0, min(pano.shape[1] - IMAGE_W - 2, i0))
    if abs(frac) <= 1e-6:
        return pano[:, i0 : i0 + IMAGE_W].copy()
    return ((1.0 - frac) * pano[:, i0 : i0 + IMAGE_W] + frac * pano[:, i0 + 1 : i0 + 1 + IMAGE_W]).copy()


def _stamp_motif(img, u_center, v_center, kind="usti", radius=28):
    """Dibuja un motivo suave analitico de ~40 px con precision subpixel exacta alrededor de (u_center, v_center)."""
    h, w = img.shape
    cx = int(round(float(u_center)))
    cy = int(round(float(v_center)))
    x0 = max(0, cx - radius)
    x1 = min(w, cx + radius + 1)
    y0 = max(0, cy - radius)
    y1 = min(h, cy + radius + 1)
    if x1 <= x0 or y1 <= y0:
        return
    xs = np.arange(x0, x1, dtype=np.float32)[None, :] - float(u_center)
    ys = np.arange(y0, y1, dtype=np.float32)[:, None] - float(v_center)
    r2 = xs * xs + ys * ys
    r = np.sqrt(r2)
    env = np.exp(-r2 / (2.0 * 11.0 * 11.0))
    wx = np.clip(1.0 - (np.abs(xs) / float(radius)) ** 6, 0.0, 1.0)
    wy = np.clip(1.0 - (np.abs(ys) / float(radius)) ** 6, 0.0, 1.0)
    blend = wx * wy

    if kind == "usti":
        pattern = (
            128.0
            + 85.0 * np.cos(0.35 * r) * env
            + 30.0 * np.cos(0.28 * xs) * np.cos(0.28 * ys) * env
        )
    else:
        pattern = (
            128.0
            - 85.0 * np.cos(0.30 * r + 0.7) * env
            + 32.0 * np.sin(0.25 * xs) * np.sin(0.25 * ys) * env
        )
    patch = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = (1.0 - blend) * patch + blend * pattern


def _save_bmp(path, img_f32):
    arr = np.clip(np.rint(img_f32), 0, 255).astype(np.uint8)
    Image.fromarray(arr, mode="L").save(path, format="BMP")


def _normalize(v):
    n = float(np.linalg.norm(v))
    if n <= 1e-12:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return v / n


def _project(pt, cam, fov_rad=FOV_RAD):
    v = np.asarray(pt, dtype=np.float64) - np.asarray(cam["pos"], dtype=np.float64)
    xc = float(np.dot(v, cam["x"]))
    yc = float(np.dot(v, cam["y"]))
    zc = float(np.dot(v, cam["z"]))
    f = (0.5 * IMAGE_H) / math.tan(0.5 * float(fov_rad))
    return (0.5 * IMAGE_W + f * (xc / zc), 0.5 * IMAGE_H - f * (yc / zc))


def _apply_roll(cam, roll_deg):
    theta = math.radians(float(roll_deg))
    c = math.cos(theta)
    s = math.sin(theta)
    x = np.asarray(cam["x"], dtype=np.float64)
    y = np.asarray(cam["y"], dtype=np.float64)
    z = np.asarray(cam["z"], dtype=np.float64)
    return {
        "pos": list(cam["pos"]),
        "x": (c * x + s * y).tolist(),
        "y": (-s * x + c * y).tolist(),
        "z": z.tolist(),
    }


def _rot_to_quat(x, y, z):
    m = np.column_stack((x, y, z))
    tr = float(m[0, 0] + m[1, 1] + m[2, 2])
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        q = np.array([0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s])
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        q = np.array([(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s])
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        q = np.array([(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s])
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        q = np.array([(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s])
    return q / np.linalg.norm(q)


def _quat_to_axes(q):
    q = q / np.linalg.norm(q)
    w, x, y, z = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    m = np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )
    return m[:, 0], m[:, 1], m[:, 2]


def _slerp(q0, q1, alpha):
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        res = q0 + float(alpha) * (q1 - q0)
        return res / np.linalg.norm(res)
    theta_0 = math.acos(max(-1.0, min(1.0, dot)))
    sin_0 = math.sin(theta_0)
    theta = theta_0 * float(alpha)
    res = (math.cos(theta) - dot * math.sin(theta) / sin_0) * q0 + (math.sin(theta) / sin_0) * q1
    return res / np.linalg.norm(res)


def _write_calib_run(base_dir, hook, true_k=1, jitter_pm1=False):
    """Genera una corrida de calibracion (calib_Ha / calib_Hb) con desfase verdadero true_k."""
    run_name = f"calib_{hook}"
    run_dir = Path(base_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    n_shots = 20
    n_total = n_shots + 3
    dt = 1.0 / 60.0

    # Patron determinista de giros de 10 deg y 0 deg que distingue unicamente k entre (-2, -1, 0, 1, 2).
    def _yaw_for_frame(m):
        if m % 2 == 0 and (m % 7 != 0):
            return 10.0
        if m % 11 == 3:
            return 10.0
        return 0.0

    rows = []
    for m in range(n_total):
        yaw_deg = _yaw_for_frame(m)
        rad = math.radians(yaw_deg)
        cam_z = [math.sin(rad), 0.0, math.cos(rad)]
        cam_x = [math.cos(rad), 0.0, -math.sin(rad)]
        cam_y = [0.0, 1.0, 0.0]
        shot_name = f"f{m:06d}.bmp" if m < n_shots else ""
        usti = [0.15, 1.50, 3.0]
        konec = [-0.45, 1.56, 3.0]
        lect_map = {r: usti for r in ("a", "b", "c", "d", "e", "f")}
        lect_k_map = {r: konec for r in ("a", "b", "c", "d", "e", "f")}
        rows.append(
            {
                "frame": m,
                "t_ms": round(m * dt * 1000.0, 3),
                "dt": round(dt, 5),
                "hook": hook,
                "invocaciones_en_frame": 1,
                "caso": "calib",
                "inject": "none",
                "run": run_name,
                "lecturas": {"usti hlavne": lect_map, "konec hlavne": lect_k_map},
                "cam": {"pos": [0.0, 1.5, 0.0], "x": cam_x, "y": cam_y, "z": cam_z},
                "fov_rad": FOV_RAD,
                "calib_yaw_deg": yaw_deg,
                "shot": shot_name,
            }
        )

    shift_10_px = FOCAL_V * math.tan(math.radians(10.0))
    img_0 = _slice_background(0.0)
    img_10 = _slice_background(shift_10_px)

    for n in range(n_shots):
        eff_k = int(true_k)
        if jitter_pm1 and (n % 3 == 1):
            # En el 33% de los frames desplazamos el indice a un frame con yaw distinto para que match_frac ~ 0.69
            alt_m = max(0, n + eff_k - 1)
            if _yaw_for_frame(alt_m) == _yaw_for_frame(n + eff_k):
                alt_m = min(n_total - 1, n + eff_k + 1)
            rendered_m = alt_m
        else:
            rendered_m = max(0, min(n_total - 1, n + eff_k))
        rendered_yaw = _yaw_for_frame(rendered_m)
        bmp_arr = img_10 if rendered_yaw > 5.0 else img_0
        _save_bmp(run_dir / f"f{n:06d}.bmp", bmp_arr)

    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    (run_dir / "samples.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _turn_windows(turn_frames):
    """3 giros de turn_frames frames, con 3 frames quietos al principio y 40 rectos (0,67 s) entre giros,
    para que la segmentacion no los una (en partida hay ~3 s andando entre giros)."""
    wins = []
    start = 3
    for _ in range(3):
        wins.append((start, start + turn_frames))
        start = start + turn_frames + 40
    return tuple(wins), start - 34


def _build_trajectory(n_frames=None, turn_rate_deg=2.8, turn_step_m=0.035, turn_frames=36):
    """Genera la trayectoria del arma con 3 giros reales (> 90 deg en >= 0,5 s, orquestador 2026-11-11) y tramos rectos."""
    dt = 1.0 / 60.0
    turn_windows, auto_n = _turn_windows(turn_frames)
    if n_frames is None:
        n_frames = auto_n
    yaw_deg = 0.0
    pos_u = np.array([0.0, 1.50, 0.0], dtype=np.float64)
    states = []

    for m in range(n_frames):
        in_turn = any(a <= m < b for a, b in turn_windows)
        if in_turn:
            yaw_deg += float(turn_rate_deg)
            rad = math.radians(yaw_deg)
            # Desplazamiento transversal durante el giro para que tanto lookat como mount/follow tengan ~11-13 px/frame
            wx = np.array([math.cos(rad), 0.0, -math.sin(rad)], dtype=np.float64)
            pos_u = pos_u + float(turn_step_m) * wx
        elif m >= 3:
            # En los primeros 3 frames esta quieto para referencia inicial limpia; luego camina suave
            rad = math.radians(yaw_deg)
            wz = np.array([math.sin(rad), 0.0, math.cos(rad)], dtype=np.float64)
            pos_u = pos_u + 0.004 * wz

        rad = math.radians(yaw_deg)
        wz = np.array([math.sin(rad), 0.0, math.cos(rad)], dtype=np.float64)
        wx = np.array([math.cos(rad), 0.0, -math.sin(rad)], dtype=np.float64)
        wy = np.array([0.0, 1.0, 0.0], dtype=np.float64)

        # Separacion transversal de ~0.93 m entre usti hlavne y konec hlavne (~270-350 px en pantalla en todos los modos)
        p_usti = pos_u.copy()
        p_konec = pos_u - 0.90 * wx + 0.16 * wy + 0.15 * wz
        states.append(
            {
                "frame": m,
                "t_ms": round(m * dt * 1000.0, 3),
                "dt": round(dt, 5),
                "usti": p_usti,
                "konec": p_konec,
                "wx": wx,
                "wy": wy,
                "wz": wz,
            }
        )
    return states


def _mode_camera_for_state(st, caso, cam0_pos=None):
    us = st["usti"]
    ks = st["konec"]
    wx = _normalize(np.cross(np.array([0.0, 1.0, 0.0], dtype=np.float64), _normalize(ks - us)))
    wz = _normalize(ks - us)
    wy = _normalize(np.cross(wz, wx))
    basis = np.column_stack((wx, wy, wz))

    if caso == "lookat":
        pos = cam0_pos.copy() if cam0_pos is not None else np.array([0.0, 1.50, -3.0], dtype=np.float64)
        z = _normalize(us - pos)
        x = _normalize(np.cross(np.array([0.0, 1.0, 0.0], dtype=np.float64), z))
        y = _normalize(np.cross(z, x))
        return {"pos": pos, "x": x, "y": y, "z": z}

    if caso == "follow":
        local_off = np.array([-2.70, 0.14, 0.46], dtype=np.float64)
    else:
        # mount0 y mount03: camara montada lateralmente mirando al punto medio boca-recamara (> 320 px en pantalla)
        local_off = np.array([-2.50, 0.08, 0.46], dtype=np.float64)

    pos = us + basis @ local_off
    target_mid = 0.50 * us + 0.50 * ks
    z = _normalize(target_mid - pos)
    x = _normalize(np.cross(np.array([0.0, 1.0, 0.0], dtype=np.float64), z))
    y = _normalize(np.cross(z, x))
    return {"pos": pos, "x": x, "y": y, "z": z}


def _write_tracking_run(
    base_dir,
    caso,
    hook,
    inject="none",
    true_k=1,
    force_delay1=False,
    force_roll_deg=0.0,
    low_coverage=False,
    turn_rate_deg=2.8,
    turn_step_m=0.035,
    noisy_detector=False,
    turn_frames=36,
):
    suffix = f"_{inject}" if inject != "none" else ""
    run_name = f"{caso}_{hook}{suffix}"
    run_dir = Path(base_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    states = _build_trajectory(turn_rate_deg=turn_rate_deg, turn_step_m=turn_step_m, turn_frames=turn_frames)
    n_total = len(states)
    cam0_pos = np.array([0.0, 1.50, -3.0], dtype=np.float64)

    # Pose objetivo instantanea por frame
    raw_cams = [_mode_camera_for_state(st, caso, cam0_pos=cam0_pos) for st in states]

    # Aplicar retraso de entrada si inject == delay1 o force_delay1
    use_delay = (inject == "delay1") or bool(force_delay1)
    input_cams = []
    for m in range(n_total):
        src_idx = max(0, m - 1) if use_delay else m
        input_cams.append(raw_cams[src_idx])

    # Para mount03 integramos el filtro exponencial (smooth_s = 0.3)
    written_cams = []
    q_filt = None
    p_filt = None
    for m, ic in enumerate(input_cams):
        if caso == "mount03":
            qt = _rot_to_quat(ic["x"], ic["y"], ic["z"])
            pt = ic["pos"].copy()
            if m == 0 or q_filt is None or p_filt is None:
                p_filt = pt
                q_filt = qt
            else:
                dt = states[m]["dt"]
                alpha = 1.0 - math.exp(-dt / 0.3)
                p_filt = p_filt + alpha * (pt - p_filt)
                q_filt = _slerp(q_filt, qt, alpha)
            fx, fy, fz = _quat_to_axes(q_filt)
            cam_m = {"pos": p_filt.tolist(), "x": fx.tolist(), "y": fy.tolist(), "z": fz.tolist()}
        else:
            cam_m = {
                "pos": ic["pos"].tolist(),
                "x": ic["x"].tolist(),
                "y": ic["y"].tolist(),
                "z": ic["z"].tolist(),
            }

        roll_val = 1.0 if inject == "roll" else float(force_roll_deg)
        if abs(roll_val) > 1e-6:
            cam_m = _apply_roll(cam_m, roll_val)
        written_cams.append(cam_m)

    # Elegir frames con captura (incluyendo 3 capturas por ventana de giro y 7 en resto: 16 BMP por corrida)
    turn_windows, _ = _turn_windows(turn_frames)
    shot_frames = {0}
    step = max(4, turn_frames // 9)
    for turn_start, turn_end in turn_windows:
        shot_frames.add(turn_end + 4)
        for f_t in range(turn_start + 1, turn_end, step):
            shot_frames.add(f_t)
    shot_frames = sorted(f for f in shot_frames if f + int(true_k) < n_total)

    rows = []
    for m, st in enumerate(states):
        u_a = st["usti"]
        k_a = st["konec"]
        # Lectura 'a' es exacta; 'b'..'f' tienen un offset de ~0.025 m (~11 px en pantalla: > 2 px y < 20 px)
        lect_u = {"a": u_a.tolist()}
        lect_k = {"a": k_a.tolist()}
        offsets = {
            "b": np.array([0.024, 0.0, 0.0]),
            "c": np.array([-0.025, 0.005, 0.0]),
            "d": np.array([0.0, 0.024, 0.0]),
            "e": np.array([0.020, -0.015, 0.0]),
            "f": np.array([-0.022, -0.012, 0.0]),
        }
        for r, off in offsets.items():
            lect_u[r] = (u_a + off).tolist()
            lect_k[r] = (k_a + off).tolist()

        shot_name = f"f{m:06d}.bmp" if m in shot_frames else ""
        row = {
            "frame": m,
            "t_ms": st["t_ms"],
            "dt": st["dt"],
            "hook": hook,
            "invocaciones_en_frame": 2 if hook == "Hb" and m % 5 == 0 else 1,
            "caso": caso,
            "inject": inject,
            "run": run_name,
            "lecturas": {"usti hlavne": lect_u, "konec hlavne": lect_k},
            "cam": written_cams[m],
            "fov_rad": FOV_RAD,
            "calib_yaw_deg": 0.0,
            "shot": shot_name,
        }
        rows.append(row)
        # En Hb simulamos invocaciones duplicadas en el mismo frame (plan §4 / brief §1)
        if hook == "Hb" and m % 10 == 0:
            dup = dict(row)
            dup["shot"] = ""
            rows.append(dup)

    bg_base = _slice_background(0.0)
    rng = np.random.default_rng(SEED + 99)

    for idx_s, n in enumerate(shot_frames):
        rendered_m = n + int(true_k)
        st_m = states[rendered_m]
        cam_m = written_cams[rendered_m]
        pu = _project(st_m["usti"], cam_m, FOV_RAD)
        pk = _project(st_m["konec"], cam_m, FOV_RAD)
        img = bg_base.copy()
        # Si low_coverage=True, ocluimos el motivo en >33% de los BMP por ventana para que coverage < 0.95
        occluded = low_coverage and (idx_s > 0) and (idx_s % 3 != 0)
        if occluded:
            img.fill(128.0)
        else:
            if noisy_detector and idx_s == 0:
                # Plantilla casi plana para forzar fallo de calibracion del detector si se pide
                _stamp_motif(img, pu[0], pu[1], kind="usti", radius=4)
                _stamp_motif(img, pk[0], pk[1], kind="konec", radius=4)
                img += rng.normal(0.0, 35.0, size=img.shape).astype(np.float32)
            else:
                _stamp_motif(img, pu[0], pu[1], kind="usti")
                _stamp_motif(img, pk[0], pk[1], kind="konec")
        _save_bmp(run_dir / f"f{n:06d}.bmp", img)

    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    (run_dir / "samples.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_fixture(target_dir, kind="pasa"):
    """Genera una fixture completa del tipo solicitado ('pasa', 'delay1', 'calib_pm1', 'low_coverage', etc.)."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    if kind == "pasa":
        _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=False)
        _write_calib_run(target_dir, "Hb", true_k=1, jitter_pm1=False)
        for caso in ("mount0", "mount03", "lookat", "follow"):
            _write_tracking_run(target_dir, caso, "Ha", inject="none", true_k=1)
        _write_tracking_run(target_dir, "mount0", "Hb", inject="none", true_k=1)
        _write_tracking_run(target_dir, "mount0", "Hc", inject="none", true_k=1)
        # Negativas esperadas (van solo a `negativas` en informe.json)
        _write_tracking_run(target_dir, "mount0", "Ha", inject="delay1", true_k=1)
        _write_tracking_run(target_dir, "lookat", "Ha", inject="delay1", true_k=1)
        _write_tracking_run(target_dir, "mount0", "Ha", inject="roll", true_k=1)
    elif kind == "delay1":
        _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=False)
        _write_tracking_run(target_dir, "mount0", "Ha", inject="none", true_k=1, force_delay1=True)
        _write_tracking_run(target_dir, "lookat", "Ha", inject="none", true_k=1, force_delay1=True)
    elif kind == "calib_pm1":
        _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=True)
        _write_tracking_run(target_dir, "mount0", "Ha", inject="none", true_k=1)
    elif kind == "low_coverage":
        _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=False)
        _write_tracking_run(target_dir, "mount0", "Ha", inject="none", true_k=1, low_coverage=True)
    elif kind == "roll_defect":
        _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=False)
        _write_tracking_run(target_dir, "mount0", "Ha", inject="none", true_k=1, force_roll_deg=1.0)
    elif kind == "weak_stimulus":
        _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=False)
        # Giro lento y largo (0,65 deg/frame x 150 frames = 97,5 deg en 2,5 s: es giro) con paso corto,
        # para que el desplazamiento entre frames quede por debajo de 3*THRESH_PX
        _write_tracking_run(target_dir, "mount0", "Ha", inject="none", true_k=1, turn_rate_deg=0.65, turn_step_m=0.008, turn_frames=150)
    else:
        raise ValueError(f"Unknown fixture kind: {kind}")

    return target_dir


def generate_all_fixtures(root_dir):
    """Genera las cuatro fixtures principales dentro de subcarpetas de root_dir."""
    root_dir = Path(root_dir)
    out = {}
    for kind in ("pasa", "delay1", "calib_pm1", "low_coverage"):
        sub = root_dir / kind
        generate_fixture(sub, kind=kind)
        out[kind] = sub
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generador de fixtures sinteticas offline para S-track·1")
    parser.add_argument("out_dir", help="Carpeta destino donde escribir las fixtures")
    parser.add_argument(
        "--kind",
        default="all",
        choices=("all", "pasa", "delay1", "calib_pm1", "low_coverage", "roll_defect", "weak_stimulus"),
        help="Tipo de fixture a generar (por defecto 'all' genera las 4 carpetas)",
    )
    args = parser.parse_args(argv)
    if args.kind == "all":
        generate_all_fixtures(args.out_dir)
    else:
        generate_fixture(args.out_dir, kind=args.kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
