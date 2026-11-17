"""Generador determinista de fixtures sinteticas offline para S-track·1 (brief §3 y CONTRACT.md).

Genera:
- pasa: todo PASA, con desfase verdadero de calibracion k = 1 (no 0), y negativas delay1/roll en `negativas`.
- delay1: retraso de un frame en las corridas positivas -> FALLA (exit_code = 1).
- calib_pm1: asociacion de imagen desplazada +-1 frame en calibracion -> calibracion no pasa (INCONCLUSO).
- low_coverage: cobertura de deteccion < COVERAGE_MIN -> INCONCLUSO (exit_code = 2).
"""

import argparse
import hashlib
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


def _write_marcas_file(base_dir, run_dir, run_name, marks):
    if not marks:
        return
    marcas_dir = Path(base_dir) / "marcas"
    marcas_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for shot, puntos, momento in marks:
        path = Path(run_dir) / shot
        sha = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        entries.append({
            "shot": shot,
            "png": str(Path(shot).with_suffix(".png")),
            "sha256": sha,
            "momento": momento,
            "A": {k: [float(v[0]), float(v[1])] for k, v in puntos.items()},
            "B": {k: [float(v[0]), float(v[1])] for k, v in puntos.items()},
            "puntos": {k: [float(v[0]), float(v[1])] for k, v in puntos.items()},
            "diff_max_px": 0.0,
        })
    data = {"schema": 1, "run": run_name, "convencion": "fixture", "marcadores": {"A": "fixture", "B": "fixture"}, "marcas": entries}
    (marcas_dir / f"{run_name}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
    bias_reading=None,
    bias_px=0.0,
    giro_field=False,
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

    # Capturas pedidas: exactamente 20 en cada ventana (giro y resto agregada),
    # tambien en ventanas inferidas sin campo `giro` (vuelta 2, hallazgo 4).
    turn_windows, _ = _turn_windows(turn_frames)
    shot_frames = {0}
    in_turn = set()
    for turn_start, turn_end in turn_windows:
        frames = list(range(turn_start, turn_end))
        in_turn.update(frames)
        if giro_field and len(frames) >= 20:
            # Con campo `giro` la ventana es exacta: bastan 20 por giro (60 de giro dan la mascara).
            shot_frames.update(frames[int(i * (len(frames) - 1) / 19.0)] for i in range(20))
        else:
            # Ventana inferida: sus bordes se mueven unos frames, se captura todo el giro.
            shot_frames.update(frames)
    # Solo frames cuyo frame+k existe (los demas se descartan al elegir capturas).
    resto_frames = [f_t for f_t in range(n_total) if f_t not in in_turn and f_t + int(true_k) < n_total]
    if giro_field and len(resto_frames) >= 20:
        shot_frames.update(resto_frames[int(i * (len(resto_frames) - 1) / 19.0)] for i in range(20))
    elif giro_field:
        shot_frames.update(resto_frames)
    else:
        # Ventana inferida: la deteccion de giros se come frames de resto en los
        # bordes; se pide 1 de cada 3 para que resto conserve >= 20 capturas.
        shot_frames.update(f_t for f_t in resto_frames if f_t % 3 == 0)
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
        if bias_reading is not None and abs(float(bias_px)) > 1e-9:
            cam_b = written_cams[m]
            cam_pos_b = np.asarray(cam_b["pos"], dtype=np.float64)
            cam_x_b = np.asarray(cam_b["x"], dtype=np.float64)
            cam_z_b = np.asarray(cam_b["z"], dtype=np.float64)
            for lect_map, true_pt in ((lect_u, u_a), (lect_k, k_a)):
                zc = float(np.dot(np.asarray(true_pt, dtype=np.float64) - cam_pos_b, cam_z_b))
                delta = cam_x_b * (float(bias_px) * max(zc, 0.1) / FOCAL_V)
                lect_map[bias_reading] = (np.asarray(lect_map[bias_reading], dtype=np.float64) + delta).tolist()

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
        if giro_field:
            giro_n = 0
            for gi, (a_w, b_w) in enumerate(turn_windows):
                if a_w <= m < b_w:
                    giro_n = gi + 1
                    break
            row["giro"] = giro_n
            row["seg"] = giro_n
        rows.append(row)
        # En Hb simulamos invocaciones duplicadas en el mismo frame (plan §4 / brief §1)
        if hook == "Hb" and m % 10 == 0:
            dup = dict(row)
            dup["shot"] = ""
            rows.append(dup)

    rng = np.random.default_rng(SEED + 99)
    marks_collected = []

    for idx_s, n in enumerate(shot_frames):
        rendered_m = n + int(true_k)
        st_m = states[rendered_m]
        cam_m = written_cams[rendered_m]
        pu = _project(st_m["usti"], cam_m, FOV_RAD)
        pk = _project(st_m["konec"], cam_m, FOV_RAD)
        # Fondo distinto en cada captura (el fondo cambia al moverse la camara).
        img = _slice_background(float(rendered_m) * 2.0)
        # Si low_coverage=True, ocluimos ~10% de los BMP de cada ventana: coverage ~0,90 < 0,95
        # sin contaminar la mascara ni la calibracion del detector de la misma corrida.
        occluded = low_coverage and (idx_s % 10 == 9)
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
        if not occluded:
            momento = "estable" if n == 0 else "resto"
            for gi, (a_w, b_w) in enumerate(turn_windows):
                if a_w <= rendered_m < b_w:
                    momento = f"giro{gi + 1}"
                    break
            marks_collected.append((f"f{n:06d}.bmp", {"usti hlavne": pu, "konec hlavne": pk}, momento, rendered_m))

    # Vuelta 3 (hallazgo 14): cinco marcas por fase (brief §4): primera estable,
    # mitad de cada giro y mitad del resto, no las cinco primeras capturas.
    selected = []
    if marks_collected:
        by_momento = {}
        for cand in marks_collected:
            by_momento.setdefault(cand[2], []).append(cand)
        if "estable" in by_momento:
            selected.append(min(by_momento["estable"], key=lambda c: c[3]))
        for gi, (a_w, b_w) in enumerate(turn_windows):
            name = f"giro{gi + 1}"
            if name in by_momento:
                mid = 0.5 * (a_w + b_w - 1)
                selected.append(min(by_momento[name], key=lambda c: abs(c[3] - mid)))
        if "resto" in by_momento:
            if len(turn_windows) >= 2:
                mid_resto = 0.5 * (turn_windows[0][1] + turn_windows[1][0])
                selected.append(min(by_momento["resto"], key=lambda c: abs(c[3] - mid_resto)))
            else:
                selected.append(by_momento["resto"][0])
    marks_final = [(shot, puntos, momento) for shot, puntos, momento, _rm in selected]
    _write_marcas_file(base_dir, run_dir, run_name, marks_final)
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    (run_dir / "samples.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _yaw_axes(yaw_deg):
    rad = math.radians(float(yaw_deg))
    x = np.array([math.cos(rad), 0.0, -math.sin(rad)], dtype=np.float64)
    y = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    z = np.array([math.sin(rad), 0.0, math.cos(rad)], dtype=np.float64)
    return x, y, z


def _quat_xyzw_from_wxyz(q):
    return [float(q[1]), float(q[2]), float(q[3]), float(q[0])]


def _nlerp(q0, q1, alpha):
    # QuatLerp de arco corto: mismo arco que la slerp, velocidad angular no uniforme.
    if float(np.dot(q0, q1)) < 0.0:
        q1 = -q1
    res = (1.0 - float(alpha)) * q0 + float(alpha) * q1
    n = float(np.linalg.norm(res))
    return res / n if n > 1e-12 else q0.copy()


def _slerp_longarc(q0, q1, alpha):
    dot = float(np.dot(q0, q1))
    if dot > 0.9995:
        res = q0 + float(alpha) * (q1 - q0)
        return res / np.linalg.norm(res)
    theta_0 = math.acos(max(-1.0, min(1.0, dot)))
    sin_0 = math.sin(theta_0)
    if abs(sin_0) < 1e-9:
        return _nlerp(q0, q1, alpha)
    theta = theta_0 * float(alpha)
    res = (math.cos(theta) - dot * math.sin(theta) / sin_0) * q0 + (math.sin(theta) / sin_0) * q1
    return res / np.linalg.norm(res)


def _write_suave_run(base_dir, regime=60, mode="ok", inject="none", dt_pattern=None):
    caso = f"suave{int(regime)}"
    suffix = f"_{inject}" if inject != "none" else ""
    run_name = f"{caso}_Hb{suffix}"
    run_dir = Path(base_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    fps = float(regime)
    dt = 1.0 / fps
    smooth_by_tramo = {1: 0.0, 2: 0.3, 3: 0.8, 4: 0.3}
    rows = []
    frame = 0
    # Estado del filtro del generador: persiste entre tramos (vuelta 2, hallazgo 7).
    filt_pos = None
    filt_q = None
    prev_raw_pos = None
    t_acc = 0.0
    for tramo in (1, 2, 3, 4):
        smooth_written = smooth_by_tramo[tramo]
        smooth_used = smooth_written
        if mode == "smooth_changed" and tramo == 1:
            smooth_used = 0.3
        if tramo < 4:
            n_frames = int(3.0 * fps)
            for i in range(n_frames):
                dt_cur = float(dt_pattern[frame % len(dt_pattern)]) if dt_pattern else dt
                t_in = i * dt
                # Lata: salta +1 m a 1 s y -1 m a 2 s dentro del tramo.
                lata_x = 0.0
                if t_in >= 1.0:
                    lata_x = 1.0
                if t_in >= 2.0:
                    lata_x = 0.0
                if mode == "reset_en_tramo" and tramo == 2:
                    # Salto justo en el cambio de tramo y filtro reiniciado (defecto del hallazgo 7).
                    lata_x = 1.0 if t_in < 1.0 else 0.0
                lata = np.array([lata_x, 1.5, 3.0], dtype=np.float64)
                raw_pos = lata + np.array([0.0, 0.3, -1.2], dtype=np.float64)
                # cam_raw sigue a lata.a en el mismo frame, salvo en el modo desfasado (hallazgo 6).
                camraw_pos = raw_pos
                if mode == "entrada_desfasada" and prev_raw_pos is not None:
                    camraw_pos = prev_raw_pos.copy()
                prev_raw_pos = raw_pos.copy()
                x, y, z = _yaw_axes(0.0)
                raw_q = _rot_to_quat(x, y, z)
                if filt_pos is None or (mode == "reset_en_tramo" and i == 0 and tramo > 1):
                    filt_pos = camraw_pos.copy()
                    filt_q = raw_q.copy()
                else:
                    alpha = 1.0 if smooth_used == 0.0 else 1.0 - math.exp(-dt_cur / smooth_used)
                    filt_pos = filt_pos + alpha * (camraw_pos - filt_pos)
                    filt_q = _slerp(filt_q, raw_q, alpha)
                fx, fy, fz = _quat_to_axes(filt_q)
                written_pos = filt_pos.copy()
                if mode == "frac35" and tramo == 2:
                    # Error de respuesta del 3,5 % del salto: entre THRESH_SUAVE_FRAC y 0,05 (hallazgo 11).
                    written_pos = written_pos + np.array([0.035, 0.0, 0.0], dtype=np.float64)
                t_ms_cur = round((t_acc + dt_cur) * 1000.0, 3) if dt_pattern else round(frame * dt * 1000.0, 3)
                t_acc += dt_cur
                rows.append({
                    "frame": frame, "t_ms": t_ms_cur, "dt": round(dt_cur, 6),
                    "hook": "Hb", "caso": caso, "inject": inject, "run": run_name,
                    "lecturas": {}, "fov_rad": FOV_RAD, "calib_yaw_deg": 0.0, "shot": "",
                    "giro": 0, "seg": tramo, "tramo": tramo, "smooth_s": smooth_written, "fps_cap": int(regime),
                    "lata": {"a": lata.tolist()},
                    "cam_raw": {"pos": camraw_pos.tolist(), "x": x.tolist(), "y": y.tolist(), "z": z.tolist(), "q": _quat_xyzw_from_wxyz(raw_q)},
                    "cam": {"pos": written_pos.tolist(), "x": fx.tolist(), "y": fy.tolist(), "z": fz.tolist(), "q": _quat_xyzw_from_wxyz(filt_q)},
                })
                frame += 1
        else:
            # Tramo 4: 0,5 s quieto, giro +170 (2 s), giro -170 de vuelta (2 s).
            if mode == "giro20":
                segments = [(int(0.5 * fps), 0.0, 0), (int(2.0 * fps), 20.0, 1), (int(2.0 * fps), 0.0, 2)]
            elif mode == "giro160":
                segments = [(int(0.5 * fps), 0.0, 0), (int(2.0 * fps), 160.0, 1), (int(2.0 * fps), 0.0, 2)]
            else:
                segments = [(int(0.5 * fps), 0.0, 0), (int(2.0 * fps), 170.0, 1), (int(2.0 * fps), 0.0, 2)]
            lata = np.array([0.0, 1.5, 3.0], dtype=np.float64)
            for n_seg, yaw_target, giro_n in segments:
                for i in range(n_seg):
                    dt_cur = float(dt_pattern[frame % len(dt_pattern)]) if dt_pattern else dt
                    raw_pos = lata + np.array([0.0, 0.3, -1.2], dtype=np.float64)
                    x, y, z = _yaw_axes(yaw_target)
                    raw_q = _rot_to_quat(x, y, z)
                    if giro_n == 2:
                        # La misma orientación con el cuaternión negado: dot de inicio < 0.
                        raw_q = -raw_q
                    if filt_pos is None:
                        filt_pos = raw_pos.copy()
                        filt_q = _rot_to_quat(*_yaw_axes(0.0))
                    else:
                        alpha = 1.0 - math.exp(-dt_cur / smooth_used)
                        filt_pos = filt_pos + alpha * (raw_pos - filt_pos)
                        if mode == "quatlerp":
                            filt_q = _nlerp(filt_q, raw_q, alpha)
                        elif mode == "longarc":
                            filt_q = _slerp_longarc(filt_q, raw_q, alpha)
                        else:
                            filt_q = _slerp(filt_q, raw_q, alpha)
                    fx, fy, fz = _quat_to_axes(filt_q)
                    t_ms_cur = round((t_acc + dt_cur) * 1000.0, 3) if dt_pattern else round(frame * dt * 1000.0, 3)
                    t_acc += dt_cur
                    row = {
                        "frame": frame, "t_ms": t_ms_cur, "dt": round(dt_cur, 6),
                        "hook": "Hb", "caso": caso, "inject": inject, "run": run_name,
                        "lecturas": {}, "fov_rad": FOV_RAD, "calib_yaw_deg": 0.0, "shot": "",
                        "giro": giro_n, "seg": 4, "tramo": 4, "smooth_s": smooth_written, "fps_cap": int(regime),
                        "lata": {"a": lata.tolist()},
                        "cam_raw": {"pos": raw_pos.tolist(), "x": x.tolist(), "y": y.tolist(), "z": z.tolist(), "q": _quat_xyzw_from_wxyz(raw_q)},
                        "cam": {"pos": filt_pos.tolist(), "x": fx.tolist(), "y": fy.tolist(), "z": fz.tolist(), "q": _quat_xyzw_from_wxyz(filt_q)},
                    }
                    if i == 0 and giro_n in (1, 2):
                        # dot orientativo de inicio (informativo).
                        row["quat_dot_inicio"] = -0.5 if (mode == "longarc" and giro_n == 2) else 0.5
                    rows.append(row)
                    frame += 1
    (run_dir / "samples.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return run_dir


def _pose_dict(pos, yaw_deg):
    x, y, z = _yaw_axes(yaw_deg)
    return {"pos": np.asarray(pos, dtype=np.float64).tolist(), "x": x.tolist(), "y": y.tolist(), "z": z.tolist()}


def _write_ropa_run(base_dir, defect=False):
    run_name = "ropa_Hb"
    run_dir = Path(base_dir) / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    n_frames = 120
    dt = 1.0 / 60.0
    cam = {"pos": [0.0, 1.5, -1.3], "x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}
    # Fases exigidas: estable, mitad de cada giro (1..3) y resto (hallazgo 15).
    marked_frames = {0: "estable", 30: "giro1", 60: "giro2", 90: "giro3", 110: "resto"}
    def _giro_of(m):
        if 20 <= m < 40:
            return 1
        if 50 <= m < 70:
            return 2
        if 80 <= m < 100:
            return 3
        return 0
    for m in range(n_frames):
        yaw = m * 0.5
        x, y, z = _yaw_axes(yaw)
        basis = np.column_stack((x, y, z))
        spine_pos = np.array([0.0, 1.4, 0.0], dtype=np.float64)
        drift = 0.03 * (m / max(n_frames - 1, 1)) if defect else 0.0
        mochila_pos = spine_pos + basis @ np.array([0.0, 0.1, -0.25 + drift], dtype=np.float64)
        arma_pos = spine_pos + basis @ np.array([0.3, 0.0, 0.4], dtype=np.float64)
        mira_pos = arma_pos + basis @ np.array([0.0, 0.08, 0.1], dtype=np.float64)
        sil_pos = arma_pos + basis @ np.array([0.0, 0.0, 0.45], dtype=np.float64)
        def pose(pos):
            return {"pos": pos.tolist(), "x": x.tolist(), "y": y.tolist(), "z": z.tolist()}
        ropa = {
            "mochila": {"a": pose(mochila_pos), "f": pose(mochila_pos)},
            "mira": {"a": pose(mira_pos), "f": pose(mira_pos)},
            "silenciador": {"a": pose(sil_pos), "f": pose(sil_pos)},
            "spine3": {"a": pose(spine_pos), "f": pose(spine_pos)},
            "arma": {"a": pose(arma_pos), "f": pose(arma_pos)},
        }
        lect = {r: mira_pos.tolist() for r in ("a", "b", "c", "d", "e", "f")}
        usti = arma_pos.tolist()
        konec = (arma_pos + basis @ np.array([0.0, 0.02, 0.4], dtype=np.float64)).tolist()
        rows.append({
            "frame": m, "t_ms": round(m * dt * 1000.0, 3), "dt": round(dt, 6),
            "hook": "Hb", "caso": "ropa", "inject": "none", "run": run_name,
            "lecturas": {"usti hlavne": {r: usti for r in ("a", "b", "c", "d", "e", "f")},
                         "konec hlavne": {r: konec for r in ("a", "b", "c", "d", "e", "f")},
                         "mira": lect},
            "cam": cam, "fov_rad": FOV_RAD, "calib_yaw_deg": 0.0,
            "shot": f"f{m:06d}.bmp" if m in marked_frames else "", "giro": _giro_of(m), "seg": 0, "ropa": ropa,
        })
    (run_dir / "samples.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    # Detalles dibujados en sus posiciones de verdad (las del mundo generado,
    # independientes del evaluador) en cada fase marcada, con su marca.
    marks = []
    for m, momento in sorted(marked_frames.items()):
        row_m = rows[m]
        pu = _project(np.asarray(row_m["lecturas"]["usti hlavne"]["a"], dtype=np.float64), cam, FOV_RAD)
        pk = _project(np.asarray(row_m["lecturas"]["konec hlavne"]["a"], dtype=np.float64), cam, FOV_RAD)
        pm = _project(np.asarray(row_m["lecturas"]["mira"]["a"], dtype=np.float64), cam, FOV_RAD)
        img = _slice_background(float(m) * 2.0)
        _stamp_motif(img, pu[0], pu[1], kind="usti")
        _stamp_motif(img, pk[0], pk[1], kind="konec")
        _stamp_motif(img, pm[0], pm[1], kind="konec")
        _save_bmp(run_dir / f"f{m:06d}.bmp", img)
        marks.append((f"f{m:06d}.bmp", {"usti hlavne": pu, "konec hlavne": pk, "mira": pm}, momento))
    _write_marcas_file(base_dir, run_dir, run_name, marks)
    return run_dir


def _write_fondo_run(base_dir):
    out_dir = Path(base_dir) / "fondo_cambiante"
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED + 7)
    src = (120.0 + rng.normal(0.0, 6.0, size=(IMAGE_H, IMAGE_W))).astype(np.float32)
    tgt = (120.0 + rng.normal(0.0, 6.0, size=(IMAGE_H, IMAGE_W))).astype(np.float32)
    cx, cy = 960.0, 540.0
    tx, ty = 990.0, 520.0
    _stamp_motif(src, cx, cy, kind="usti")
    _stamp_motif(tgt, tx, ty, kind="usti")
    # Anillo exterior fuerte en la fuente, copiado en el objetivo desplazado +20 px en u.
    outer_src = rng.integers(0, 2, size=(48, 48)).astype(np.float32) * 220.0 + 10.0
    half = 24
    sx0, sy0 = int(cx) - half, int(cy) - half
    src_patch = src[sy0:sy0 + 48, sx0:sx0 + 48]
    yy, xx = np.mgrid[0:48, 0:48]
    ring = ((xx - 23.5) ** 2 + (yy - 23.5) ** 2) > (16.0 ** 2)
    src_patch[ring] = outer_src[ring]
    src[sy0:sy0 + 48, sx0:sx0 + 48] = src_patch
    ox, oy = int(tx) + 20 - half, int(ty) - half
    tgt_patch = tgt[oy:oy + 48, ox:ox + 48]
    tgt_patch[ring] = outer_src[ring]
    tgt[oy:oy + 48, ox:ox + 48] = tgt_patch
    # Los píxeles del arma (dentro de la máscara) son idénticos en el objetivo.
    tx0, ty0 = int(tx) - half, int(ty) - half
    disc = ~ring
    tgt_region = tgt[ty0:ty0 + 48, tx0:tx0 + 48]
    tgt_region[disc] = src_patch[disc]
    tgt[ty0:ty0 + 48, tx0:tx0 + 48] = tgt_region
    _save_bmp(out_dir / "source.bmp", src)
    _save_bmp(out_dir / "target.bmp", tgt)
    mask = np.zeros((48, 48), dtype=np.uint8)
    mask[((xx - 23.5) ** 2 + (yy - 23.5) ** 2) <= (16.0 ** 2)] = 255
    Image.fromarray(mask, mode="L").save(out_dir / "mascara.png")
    truth = {"source_center": [cx, cy], "target_center": [tx, ty], "decoy_center": [tx + 20.0, ty]}
    (out_dir / "truth.json").write_text(json.dumps(truth, indent=2) + "\n", encoding="utf-8")
    return out_dir


def _write_s2_completo(target_dir):
    """Positivo completo de imagen en formato S-track·2 (hallazgo 13): campo `giro`,
    todas las capturas pedidas con su BMP y >= 20 capturas por ventana."""
    _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=False)
    for caso in ("mount0", "mount03", "lookat", "follow"):
        _write_tracking_run(target_dir, caso, "Ha", inject="none", true_k=1, giro_field=True)
    return target_dir


def _trim_giro1_to_15(target_dir):
    run_dir = Path(target_dir) / "mount0_Ha"
    samples_path = run_dir / "samples.jsonl"
    rows = [json.loads(line) for line in samples_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kept = 0
    for r in rows:
        if int(r.get("giro") or 0) == 1 and r.get("shot"):
            kept += 1
            if kept > 15:
                r["shot"] = ""
    samples_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


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
    elif kind == "sesgo5":
        _write_calib_run(target_dir, "Ha", true_k=1, jitter_pm1=False)
        _write_calib_run(target_dir, "Hb", true_k=1, jitter_pm1=False)
        _write_tracking_run(target_dir, "mount0", "Ha", inject="none", true_k=1, bias_reading="a", bias_px=5.0)
    elif kind == "fondo_cambiante":
        _write_fondo_run(target_dir)
    elif kind == "suave_ok":
        _write_suave_run(target_dir, regime=60, mode="ok")
    elif kind == "suave_smooth":
        _write_suave_run(target_dir, regime=60, mode="smooth_changed")
    elif kind == "suave_quatlerp":
        _write_suave_run(target_dir, regime=60, mode="quatlerp")
    elif kind == "suave_longarc":
        _write_suave_run(target_dir, regime=60, mode="longarc")
    elif kind == "suave_frac35":
        _write_suave_run(target_dir, regime=60, mode="frac35")
    elif kind == "suave_entrada_desfasada":
        _write_suave_run(target_dir, regime=60, mode="entrada_desfasada")
    elif kind == "suave_reset_tramo":
        _write_suave_run(target_dir, regime=60, mode="reset_en_tramo")
    elif kind == "ropa_ok":
        _write_ropa_run(target_dir, defect=False)
        _write_calib_run(target_dir, "Hb", true_k=0, jitter_pm1=False)
    elif kind == "ropa_falla":
        _write_ropa_run(target_dir, defect=True)
        _write_calib_run(target_dir, "Hb", true_k=0, jitter_pm1=False)
    elif kind == "s2_completo":
        _write_s2_completo(target_dir)
    elif kind in ("pocas_capturas", "s2_pocas15"):
        # Negativa de 15 capturas derivada del positivo S-track·2 completo (hallazgo 13).
        _write_s2_completo(target_dir)
        _trim_giro1_to_15(target_dir)
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
        choices=("all", "pasa", "delay1", "calib_pm1", "low_coverage", "roll_defect", "weak_stimulus", "sesgo5", "fondo_cambiante", "suave_ok", "suave_smooth", "suave_quatlerp", "suave_longarc", "suave_frac35", "suave_entrada_desfasada", "suave_reset_tramo", "ropa_ok", "ropa_falla", "pocas_capturas", "s2_completo", "s2_pocas15"),
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
