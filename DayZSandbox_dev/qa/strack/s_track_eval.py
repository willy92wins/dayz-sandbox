"""Evaluador de la sonda S-track·1 (brief 2026-11-10-s-track-1-brief.md §3 y CONTRACT.md).

Lee carpetas de corridas con samples.jsonl y capturas f######.bmp, ejecuta:
1. Calibracion de desfase de frame k por correlacion horizontal de bandas y convencion de FOV.
2. Calibracion del detector de plantilla (48x48 px, ventana +-80 px, subpixel) con transformaciones sinteticas.
3. Evaluacion por ventana (cada giro y resto) de T-lect y T-hook, comprobando estimulo y cobertura.
4. Escritura de informe.json e informe.md y codigo de salida 0 (PASA), 1 (FALLA) o 2 (INCONCLUSO).
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

THRESH_PX = 2.0
THRESH_ROLL_DEG = 0.5
COVERAGE_MIN = 0.95
CALIB_MATCH_MIN = 0.99
K_CANDIDATES = (-2, -1, 0, 1, 2)
STIMULUS_FACTOR = 3.0
DETECTOR_MAX_PX = 0.5
DETECTOR_MAX_DEG = 0.1

IMAGE_W = 1920
IMAGE_H = 1080
# Orquestador 2026-11-11: 32 px (el brief decia 48). Con el banco de giro/escala, 32 px dio p95 0,29-0,37 px
# y 0,063-0,074 deg sobre capturas reales con textura (mount0_Hc, mount0_Hb); 48 px quedaba mas justo en angulo.
TEMPLATE_SIZE = 32
# Banco de plantillas giradas y escaladas: el detector busca la mejor de todas (NCC) y da su posicion.
# 15 plantillas: con 77 (paso 0,5 deg y 0,02) la precision era la misma y el tiempo 4 veces mayor.
BANK_ANGLES_DEG = (-2.0, -1.0, 0.0, 1.0, 2.0)
BANK_SCALES = (0.95, 1.0, 1.05)
SEARCH_RADIUS = 80
# Orquestador 2026-11-11: un recorte de plantilla con desviacion tipica menor que esto (niveles de gris
# 0-255) no tiene textura (arma sin cargar, cielo, suelo liso): la captura cuenta como no observada.
TEXTURE_MIN_STD = 15.0
# Una captura con luminancia media >= esto es de carga o fundido.
SCENE_MAX_MEAN = 200.0
READINGS_ORDER = ("a", "b", "c", "d", "e", "f")
HOOKS_ORDER = ("Ha", "Hb", "Hc")
MODES_ORDER = ("mount0", "mount03", "lookat", "follow")
POINTS = ("usti hlavne", "konec hlavne")


def _vec3(v):
    if not isinstance(v, (list, tuple)) or len(v) != 3:
        return None
    try:
        arr = np.array([float(v[0]), float(v[1]), float(v[2])], dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(arr)):
        return None
    return arr


def _normalize(v):
    n = float(np.linalg.norm(v))
    if n <= 1e-12:
        return np.array([0.0, 0.0, 1.0], dtype=np.float64)
    return v / n


def _focal_length(fov_rad, convention="vertical", width=IMAGE_W, height=IMAGE_H):
    # Brief v1.1 C: la focal medida en calib (float, px) manda sobre cualquier convenio de FOV.
    if isinstance(convention, (int, float)) and not isinstance(convention, bool):
        return float(convention)
    half = 0.5 * float(fov_rad)
    tan_half = math.tan(half)
    if abs(tan_half) <= 1e-9:
        tan_half = 1e-9
    if convention == "horizontal":
        return (0.5 * float(width)) / tan_half
    return (0.5 * float(height)) / tan_half


def project_point(point_world, cam, fov_rad, convention="vertical", width=IMAGE_W, height=IMAGE_H):
    """Proyecta un punto 3D del mundo a coordenadas de pantalla (u, v_px) segun CONTRACT §2."""
    p = _vec3(point_world) if not isinstance(point_world, np.ndarray) else point_world
    if p is None:
        return None
    pos = _vec3(cam.get("pos")) if not isinstance(cam.get("pos"), np.ndarray) else cam["pos"]
    ax = _vec3(cam.get("x")) if not isinstance(cam.get("x"), np.ndarray) else cam["x"]
    ay = _vec3(cam.get("y")) if not isinstance(cam.get("y"), np.ndarray) else cam["y"]
    az = _vec3(cam.get("z")) if not isinstance(cam.get("z"), np.ndarray) else cam["z"]
    if pos is None or ax is None or ay is None or az is None:
        return None
    v = p - pos
    xc = float(np.dot(v, ax))
    yc = float(np.dot(v, ay))
    zc = float(np.dot(v, az))
    if zc <= 1e-6:
        return None
    f = _focal_length(fov_rad, convention=convention, width=width, height=height)
    u = 0.5 * float(width) + f * (xc / zc)
    v_px = 0.5 * float(height) - f * (yc / zc)
    if not (math.isfinite(u) and math.isfinite(v_px)):
        return None
    return (u, v_px)


def _p95(values):
    if not values:
        return float("inf")
    ordered = sorted(float(x) for x in values)
    idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return float(ordered[idx])


def _angle_diff_deg(a_deg, b_deg):
    return abs((float(a_deg) - float(b_deg) + 180.0) % 360.0 - 180.0)


def _segment_angle_deg(p_usti, p_konec):
    du = float(p_konec[0]) - float(p_usti[0])
    dv = float(p_konec[1]) - float(p_usti[1])
    return math.degrees(math.atan2(dv, du))


def _shot_path(run_dir, name):
    """BMP del juego, o su PNG sin pérdida si el orquestador ya lo convirtió (mismos píxeles)."""
    path = Path(run_dir) / name
    if not path.is_file() and path.suffix.lower() == ".bmp":
        png = path.with_suffix(".png")
        if png.is_file():
            return png
    return path


def _load_gray(bmp_path):
    with Image.open(bmp_path) as img:
        gray = img.convert("L")
        return np.asarray(gray, dtype=np.float32)


def _read_run(run_dir):
    samples_path = run_dir / "samples.jsonl"
    if not samples_path.is_file():
        return None
    raw_rows = []
    text = samples_path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        raw_rows.append(json.loads(line))
    if not raw_rows:
        return None

    # Resolver duplicados por frame (ej. EOnPostFrame en Hb) conservando shot no vacio si existe.
    by_frame = {}
    for row in raw_rows:
        frame = int(row["frame"])
        if frame not in by_frame:
            by_frame[frame] = dict(row)
        else:
            prev = by_frame[frame]
            if not prev.get("shot") and row.get("shot"):
                by_frame[frame] = dict(row)
            else:
                merged = dict(row)
                if prev.get("shot") and not merged.get("shot"):
                    merged["shot"] = prev["shot"]
                by_frame[frame] = merged

    frames_sorted = sorted(by_frame.keys())
    has_gaps = False
    if len(frames_sorted) >= 2:
        expected_len = frames_sorted[-1] - frames_sorted[0] + 1
        if expected_len != len(frames_sorted):
            has_gaps = True

    samples = [by_frame[f] for f in frames_sorted]
    first = samples[0]
    return {
        "dir": run_dir,
        "run": str(first.get("run") or run_dir.name),
        "caso": str(first.get("caso") or ""),
        "hook": str(first.get("hook") or ""),
        "inject": str(first.get("inject") or "none"),
        "samples": samples,
        "by_frame": by_frame,
        "has_gaps": has_gaps,
    }


def _discover_runs(runs_dir):
    runs_dir = Path(runs_dir)
    if (runs_dir / "samples.jsonl").is_file():
        r = _read_run(runs_dir)
        return [r] if r is not None else []
    runs = []
    for sub in sorted(runs_dir.iterdir()):
        if sub.is_dir() and (sub / "samples.jsonl").is_file():
            r = _read_run(sub)
            if r is not None:
                runs.append(r)
    return runs


def _phase_shift_x(ref_img, cur_img, top_frac=0.65):
    """Desplazamiento horizontal (px, subpixel) por correlacion de fase 2D, sin la franja inferior del HUD.

    Brief v1.1 (orquestador): en las capturas reales la correlacion de una banda daba -81..-163 px para el
    mismo giro de 10 deg; la correlacion de fase 2D da dos grupos limpios (0 y 120-121 px). Mismo signo que
    _band_shift_px: negativo cuando la vista gira a la derecha.
    """
    h = ref_img.shape[0]
    rows = max(8, int(h * top_frac))
    a = ref_img[:rows] - ref_img[:rows].mean()
    b = cur_img[:rows] - cur_img[:rows].mean()
    fa = np.fft.fft2(a)
    fb = np.fft.fft2(b)
    r = fa * np.conj(fb)
    r /= np.abs(r) + 1e-9
    corr = np.fft.ifft2(r).real
    y, x = np.unravel_index(int(np.argmax(corr)), corr.shape)
    w = corr.shape[1]
    c0 = corr[y, x]
    cm = corr[y, (x - 1) % w]
    cp = corr[y, (x + 1) % w]
    den = cm - 2.0 * c0 + cp
    sub = 0.0 if abs(den) < 1e-12 else 0.5 * (cm - cp) / den
    dx = float(x) + sub
    if dx > w / 2.0:
        dx -= w
    return -dx


def _band_shift_px(ref_img, cur_img, max_lag=360):
    """Mide el desplazamiento horizontal cur_img respecto a ref_img por correlacion de bandas."""
    h, w = ref_img.shape
    band_defs = (
        (int(0.08 * h), int(0.22 * h)),
        (int(0.24 * h), int(0.38 * h)),
        (int(0.62 * h), int(0.76 * h)),
        (int(0.78 * h), int(0.92 * h)),
    )
    lags = []
    for y0, y1 in band_defs:
        r_prof = ref_img[y0:y1, :].mean(axis=0).astype(np.float64)
        c_prof = cur_img[y0:y1, :].mean(axis=0).astype(np.float64)
        r_prof -= r_prof.mean()
        c_prof -= c_prof.mean()
        r_std = float(np.linalg.norm(r_prof))
        c_std = float(np.linalg.norm(c_prof))
        if r_std <= 1e-6 or c_std <= 1e-6:
            continue
        # Buscamos dx tal que cur_img[x + dx] ~ ref_img[x]
        margin = max_lag + 8
        if w <= 2 * margin + 16:
            margin = max(1, w // 4)
            max_l = margin - 1
        else:
            max_l = max_lag
        template = r_prof[margin : w - margin]
        t_norm = float(np.linalg.norm(template))
        if t_norm <= 1e-6:
            continue
        best_lag = 0
        best_val = -1e18
        scores = np.empty(2 * max_l + 1, dtype=np.float64)
        t_len = len(template)
        for idx, dx in enumerate(range(-max_l, max_l + 1)):
            seg = c_prof[margin + dx : margin + dx + t_len]
            val = float(np.dot(template, seg)) / (t_norm * (float(np.linalg.norm(seg)) + 1e-12))
            scores[idx] = val
            if val > best_val:
                best_val = val
                best_lag = dx
        peak_i = best_lag + max_l
        sub = 0.0
        if 0 < peak_i < len(scores) - 1:
            denom = scores[peak_i - 1] - 2.0 * scores[peak_i] + scores[peak_i + 1]
            if abs(denom) > 1e-12:
                sub = 0.5 * (scores[peak_i - 1] - scores[peak_i + 1]) / denom
                sub = max(-0.5, min(0.5, sub))
        lags.append(float(best_lag) + sub)
    if not lags:
        return 0.0
    return float(np.median(lags))


def evaluate_calib_run(run):
    """Evalua una corrida de caso='calib' y devuelve el bloque de calibracion para su hook."""
    by_frame = run["by_frame"]
    run_dir = run["dir"]
    shot_rows = [s for s in run["samples"] if s.get("shot")]
    if len(shot_rows) < 2:
        return {
            "k": None,
            "match_frac": 0.0,
            "verdict": "INCONCLUSO",
            "cause": "insufficient_calib_shots",
            "fov_convention": "vertical",
        }

    # Brief v1.1 B: referencia = primera captura con la escena estable (se saltan carga y fundido):
    # luminancia media < 200 y variacion <= 2 % en 10 capturas seguidas.
    lum = []
    for row in shot_rows:
        pth = _shot_path(run_dir, row["shot"])
        lum.append(float(_load_gray(pth).mean()) if pth.is_file() else None)
    ref_idx = None
    for i in range(len(shot_rows) - 9):
        win = lum[i:i + 10]
        if any(v is None for v in win):
            continue
        if max(win) < 200.0 and (max(win) - min(win)) <= 0.02 * max(win):
            ref_idx = i
            break
    if ref_idx is None:
        return {
            "k": None,
            "match_frac": 0.0,
            "verdict": "INCONCLUSO",
            "cause": "no_stable_reference",
            "fov_convention": "medida",
            "f_px": None,
        }
    shot_rows = shot_rows[ref_idx:]
    first_path = _shot_path(run_dir, shot_rows[0]["shot"])
    if not first_path.is_file():
        return {
            "k": None,
            "match_frac": 0.0,
            "verdict": "INCONCLUSO",
            "cause": "missing_calib_bmp",
            "fov_convention": "vertical",
        }

    ref_img = _load_gray(first_path)
    h, w = ref_img.shape
    fov_rad = float(shot_rows[0].get("fov_rad", 1.0471976))

    raw_shifts = {}
    for row in shot_rows:
        bmp_path = _shot_path(run_dir, row["shot"])
        if not bmp_path.is_file():
            continue
        cur_img = _load_gray(bmp_path)
        raw_shifts[int(row["frame"])] = _phase_shift_x(ref_img, cur_img)

    if len(raw_shifts) < len(shot_rows):
        return {
            "k": None,
            "match_frac": 0.0,
            "verdict": "INCONCLUSO",
            "cause": "missing_calib_bmp",
            "fov_convention": "vertical",
        }

    vals = np.array(list(raw_shifts.values()), dtype=np.float64)
    max_dx = float(np.max(vals))
    min_dx = float(np.min(vals))
    span_px = max_dx - min_dx

    # Con giro de +10 grados a la derecha, el fondo se desplaza a la izquierda (-f * tan(10 deg)).
    # Brief v1.1 C: focal medida = desplazamiento en px / tan(giro escrito de 10 deg), solo del giro de la camara.
    fov_convention = "medida"
    mid = 0.5 * (max_dx + min_dx)
    hi = [dx for dx in vals if dx >= mid]
    lo = [dx for dx in vals if dx < mid]
    t10 = math.tan(math.radians(10.0))
    f_samples = []
    if hi and lo:
        hi_c = float(np.median(hi))
        f_samples = [(hi_c - dx) / t10 for dx in lo]
    f_used = float(np.median(f_samples)) if f_samples else None
    f_stats = {
        "f_px": round(f_used, 2) if f_used else None,
        "f_std_px": round(float(np.std(f_samples)), 3) if f_samples else None,
        "f_p05_px": round(float(np.percentile(f_samples, 5)), 2) if f_samples else None,
        "f_p95_px": round(float(np.percentile(f_samples, 95)), 2) if f_samples else None,
        "f_n": len(f_samples),
        "ref_shot": shot_rows[0]["shot"],
    }

    if span_px < 20.0 or not f_used:
        return dict({
            "k": None,
            "match_frac": 0.0,
            "verdict": "INCONCLUSO",
            "cause": "no_calib_shift_detected",
            "fov_convention": fov_convention,
        }, **f_stats)

    # max_dx corresponde a yaw 0 deg; max_dx - raw_shift es el desplazamiento positivo hacia la izquierda.
    measured_yaw = {}
    for frame, dx in raw_shifts.items():
        shift_left = max_dx - dx
        yaw_deg = math.degrees(math.atan2(shift_left, f_used))
        measured_yaw[frame] = yaw_deg

    total_shots = len(shot_rows)
    match_by_k = {}
    for k in K_CANDIDATES:
        matches = 0
        for row in shot_rows:
            n = int(row["frame"])
            target = by_frame.get(n + int(k))
            if target is None:
                continue
            written_yaw = float(target.get("calib_yaw_deg", 0.0))
            if abs(measured_yaw[n] - written_yaw) <= 2.5:
                matches += 1
        match_by_k[int(k)] = float(matches) / float(total_shots)

    passing = [k for k in K_CANDIDATES if match_by_k[int(k)] >= CALIB_MATCH_MIN and CALIB_MATCH_MIN > 0.0]
    best_k = max(K_CANDIDATES, key=lambda c: match_by_k[int(c)])
    best_frac = round(float(match_by_k[int(best_k)]), 4)

    if len(passing) == 1:
        win_k = int(passing[0])
        return dict({
            "k": win_k,
            "match_frac": round(float(match_by_k[win_k]), 4),
            "verdict": "PASA",
            "cause": "",
            "fov_convention": fov_convention,
            "match_by_k": {str(kk): round(v, 4) for kk, v in match_by_k.items()},
        }, **f_stats)

    cause = "ambiguous_k" if len(passing) > 1 else "below_calib_match_min"
    return dict({
        "k": None,
        "match_frac": best_frac,
        "verdict": "INCONCLUSO",
        "cause": cause,
        "fov_convention": fov_convention,
        "match_by_k": {str(kk): round(v, 4) for kk, v in match_by_k.items()},
    }, **f_stats)


def _bilinear_sample_grid(img, x_coords, y_coords):
    """Muestreo bilineal de img en una rejilla 2D dada por vectores 1D x_coords, y_coords."""
    h, w = img.shape
    x = np.clip(x_coords, 0.0, float(w - 1) - 1e-6)
    y = np.clip(y_coords, 0.0, float(h - 1) - 1e-6)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    wx = (x - x0)[None, :]
    wy = (y - y0)[:, None]
    ia = img[np.ix_(y0, x0)].astype(np.float64, copy=False)
    ib = img[np.ix_(y0, x1)].astype(np.float64, copy=False)
    ic = img[np.ix_(y1, x0)].astype(np.float64, copy=False)
    id_ = img[np.ix_(y1, x1)].astype(np.float64, copy=False)
    return (1.0 - wy) * ((1.0 - wx) * ia + wx * ib) + wy * ((1.0 - wx) * ic + wx * id_)


def _crop_std(img, u, v_px, size=TEMPLATE_SIZE):
    """Desviacion tipica del recorte size x size centrado en (u, v_px); 0 si cae fuera de la imagen."""
    h, w = img.shape
    half = size // 2
    x0 = int(round(float(u))) - half
    y0 = int(round(float(v_px))) - half
    if x0 < 0 or y0 < 0 or x0 + size > w or y0 + size > h:
        return 0.0
    return float(img[y0:y0 + size, x0:x0 + size].std())


def _textured(img, points):
    """Escena estable y recorte con textura alrededor de cada punto proyectado."""
    if float(img.mean()) >= SCENE_MAX_MEAN:
        return False
    return all(p is not None and _crop_std(img, p[0], p[1]) >= TEXTURE_MIN_STD for p in points)


def extract_template(img, u, v_px, size=TEMPLATE_SIZE):
    """Extrae una plantilla centrada en (u, v_px) con interpolacion bilineal exacta."""
    half = 0.5 * float(size - 1)
    xs = float(u) + (np.arange(size, dtype=np.float64) - half)
    ys = float(v_px) + (np.arange(size, dtype=np.float64) - half)
    patch = _bilinear_sample_grid(img, xs, ys)
    mean = float(patch.mean())
    zm = patch - mean
    norm = float(np.linalg.norm(zm))
    return {
        "patch": patch,
        "zm": zm,
        "norm": norm,
        "size": size,
    }


def _box_sum(arr, size):
    p = np.pad(arr, ((1, 0), (1, 0)), mode="constant", constant_values=0.0)
    cs = np.cumsum(np.cumsum(p, axis=0), axis=1)
    return cs[size:, size:] - cs[:-size, size:] - cs[size:, :-size] + cs[:-size, :-size]


def _ncc_at(crop_f64, tmpl, u_c, v_c, grid_idx):
    patch = _bilinear_sample_grid(crop_f64, u_c + grid_idx, v_c + grid_idx)
    zm = patch - float(patch.mean())
    n = float(np.linalg.norm(zm))
    if n <= 1e-6:
        return -1.0
    return float(np.sum(zm * tmpl["zm"])) / (n * tmpl["norm"])


def detect_template(img, tmpl, u_pred, v_pred, search_radius=SEARCH_RADIUS):
    """Busca la plantilla en una ventana +-search_radius con ajuste parabolico subpixel del pico de NCC."""
    if tmpl is None or tmpl["norm"] <= 1e-5:
        return None
    h, w = img.shape
    size = int(tmpl["size"])
    half_int = size // 2
    cx = int(round(float(u_pred)))
    cy = int(round(float(v_pred)))

    x_min = max(0, cx - search_radius - half_int)
    y_min = max(0, cy - search_radius - half_int)
    x_max = min(w, cx + search_radius + (size - half_int))
    y_max = min(h, cy + search_radius + (size - half_int))
    ch = y_max - y_min
    cw = x_max - x_min
    if cw < size or ch < size:
        return None

    crop = img[y_min:y_max, x_min:x_max].astype(np.float64)
    crop0 = crop - float(crop.mean())
    out_h = ch - size + 1
    out_w = cw - size + 1

    fh = 1 << (ch - 1).bit_length()
    fw = 1 << (cw - 1).bit_length()
    dots = np.fft.irfft2(
        np.fft.rfft2(crop0, s=(fh, fw)) * np.conj(np.fft.rfft2(tmpl["zm"], s=(fh, fw))),
        s=(fh, fw),
    )[:out_h, :out_w]

    box_s = _box_sum(crop0, size)
    box_sq = _box_sum(crop0 * crop0, size)
    w_var = box_sq - (box_s * box_s) / float(size * size)
    w_norm = np.sqrt(np.maximum(w_var, 0.0))

    denom = w_norm * tmpl["norm"]
    valid = denom > 1e-4
    if not np.any(valid):
        return None
    scores = np.where(valid, dots / np.maximum(denom, 1e-12), -1.0)
    iy, ix = np.unravel_index(int(np.argmax(scores)), scores.shape)
    peak_score = float(scores[iy, ix])
    if peak_score < 0.55:
        return None

    sub_x = 0.0
    sub_y = 0.0
    sh, sw = scores.shape
    if 0 < ix < sw - 1:
        d = scores[iy, ix - 1] - 2.0 * scores[iy, ix] + scores[iy, ix + 1]
        if abs(d) > 1e-12 and d < 0.0:
            sub_x = max(-0.6, min(0.6, 0.5 * (scores[iy, ix - 1] - scores[iy, ix + 1]) / d))
    if 0 < iy < sh - 1:
        d = scores[iy - 1, ix] - 2.0 * scores[iy, ix] + scores[iy + 1, ix]
        if abs(d) > 1e-12 and d < 0.0:
            sub_y = max(-0.6, min(0.6, 0.5 * (scores[iy - 1, ix] - scores[iy + 1, ix]) / d))

    half_f = 0.5 * float(size - 1)
    u_crop = float(ix) + half_f + sub_x
    v_crop = float(iy) + half_f + sub_y

    grid_idx = np.arange(size, dtype=np.float64) - half_f
    for step in (0.25, 0.08):
        c0 = _ncc_at(crop, tmpl, u_crop, v_crop, grid_idx)
        cx_m = _ncc_at(crop, tmpl, u_crop - step, v_crop, grid_idx)
        cx_p = _ncc_at(crop, tmpl, u_crop + step, v_crop, grid_idx)
        cy_m = _ncc_at(crop, tmpl, u_crop, v_crop - step, grid_idx)
        cy_p = _ncc_at(crop, tmpl, u_crop, v_crop + step, grid_idx)
        dx = 0.0
        dy = 0.0
        if c0 >= cx_m and c0 >= cx_p:
            denom_x = cx_m - 2.0 * c0 + cx_p
            if abs(denom_x) > 1e-12:
                dx = step * max(-0.5, min(0.5, 0.5 * (cx_m - cx_p) / denom_x))
        if c0 >= cy_m and c0 >= cy_p:
            denom_y = cy_m - 2.0 * c0 + cy_p
            if abs(denom_y) > 1e-12:
                dy = step * max(-0.5, min(0.5, 0.5 * (cy_m - cy_p) / denom_y))
        u_crop += dx
        v_crop += dy

    u_est = float(x_min) + u_crop
    v_est = float(y_min) + v_crop
    return (float(u_est), float(v_est), peak_score)


def make_template_bank(img, u, v_px, size=None):
    """Plantillas del entorno de (u, v_px) giradas BANK_ANGLES_DEG y escaladas BANK_SCALES alrededor del punto."""
    size = TEMPLATE_SIZE if size is None else size
    bank = []
    for ang in BANK_ANGLES_DEG:
        for scl in BANK_SCALES:
            warped = img if (ang == 0.0 and scl == 1.0) else _warp_image_around(img, u, v_px, 0.0, 0.0, float(ang), float(scl))
            tmpl = extract_template(warped, u, v_px, size)
            if tmpl is not None and tmpl["norm"] > 1e-5:
                bank.append(tmpl)
    return bank


def detect_template_bank(img, bank, u_pred, v_pred, search_radius=SEARCH_RADIUS):
    """La deteccion de mayor NCC entre todas las plantillas del banco."""
    best = None
    for tmpl in bank or ():
        det = detect_template(img, tmpl, u_pred, v_pred, search_radius=search_radius)
        if det is not None and (best is None or det[2] > best[2]):
            best = det
    return best


def _warp_image_around(img, center_u, center_v, shift_u, shift_v, angle_deg, scale):
    """Genera una imagen sintetica desplazada, girada y escalada a partir de un BMP real."""
    h, w = img.shape
    theta = math.radians(float(angle_deg))
    inv_scale = 1.0 / float(scale)
    cos_t = math.cos(theta) * inv_scale
    sin_t = math.sin(theta) * inv_scale
    cu = float(center_u)
    cv = float(center_v)
    su = float(shift_u)
    sv = float(shift_v)

    out = img.copy()
    x_lo = max(0, int(cu - 650))
    x_hi = min(w, int(cu + 650))
    y_lo = max(0, int(cv - 420))
    y_hi = min(h, int(cv + 420))
    if x_hi <= x_lo or y_hi <= y_lo:
        x_lo, x_hi, y_lo, y_hi = 0, w, 0, h

    dx = (np.arange(x_lo, x_hi, dtype=np.float64) - (cu + su))[None, :]
    dy = (np.arange(y_lo, y_hi, dtype=np.float64) - (cv + sv))[:, None]
    u_in = cu + cos_t * dx + sin_t * dy
    v_in = cv - sin_t * dx + cos_t * dy

    x = np.clip(u_in, 0.0, float(w - 1) - 1e-6)
    y = np.clip(v_in, 0.0, float(h - 1) - 1e-6)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    wx = x - x0
    wy = y - y0
    roi = (
        (1.0 - wy) * ((1.0 - wx) * img[y0, x0] + wx * img[y0, x1])
        + wy * ((1.0 - wx) * img[y1, x0] + wx * img[y1, x1])
    )
    out[y_lo:y_hi, x_lo:x_hi] = roi.astype(np.float32)
    return out


def calibrate_detector(runs, k_by_hook, fov_by_hook):
    """Calibra el detector sobre un BMP real con desplazamientos subpixel, giros +-2 deg y escalas +-5 %."""
    source_img = None
    p_usti = None
    p_konec = None

    for run in runs:
        if run["caso"] == "calib" or run["inject"] != "none":
            continue
        k = k_by_hook.get(run["hook"], 0)
        if k is None:
            k = 0
        fov_conv = fov_by_hook.get(run["hook"], "vertical")
        for row in run["samples"]:
            if not row.get("shot"):
                continue
            bmp_path = _shot_path(run["dir"], row["shot"])
            target = run["by_frame"].get(int(row["frame"]) + int(k))
            if not bmp_path.is_file() or target is None:
                continue
            lect = target.get("lecturas") or {}
            cam = target.get("cam") or {}
            fov_rad = float(target.get("fov_rad", 1.0471976))
            for r in READINGS_ORDER:
                u_w = (lect.get("usti hlavne") or {}).get(r)
                k_w = (lect.get("konec hlavne") or {}).get(r)
                if u_w is None or k_w is None:
                    continue
                pu = project_point(u_w, cam, fov_rad, fov_conv)
                pk = project_point(k_w, cam, fov_rad, fov_conv)
                if pu is not None and pk is not None:
                    # Fuente: escena estable, textura en los dos recortes y >= 200 px entre ellos (brief §0).
                    if math.hypot(pu[0] - pk[0], pu[1] - pk[1]) < 200.0:
                        break
                    cand_img = _load_gray(bmp_path)
                    if not _textured(cand_img, (pu, pk)):
                        break
                    source_img = cand_img
                    p_usti = pu
                    p_konec = pk
                    break
            if source_img is not None:
                break
        if source_img is not None:
            break

    if source_img is None or p_usti is None or p_konec is None:
        return {"p95_px": float("inf"), "p95_deg": float("inf"), "verdict": "INCONCLUSO"}

    tmpl_u = make_template_bank(source_img, p_usti[0], p_usti[1])
    tmpl_k = make_template_bank(source_img, p_konec[0], p_konec[1])
    mid_u = 0.5 * (p_usti[0] + p_konec[0])
    mid_v = 0.5 * (p_usti[1] + p_konec[1])

    cases = (
        (-12.35, 8.40, -2.0, 0.95),
        (14.20, -9.65, 2.0, 1.05),
        (-7.80, -11.25, 1.5, 0.97),
        (9.45, 13.10, -1.5, 1.03),
        (5.25, -4.75, 2.0, 0.95),
        (-6.40, 7.15, -2.0, 1.05),
        (18.60, 0.35, 0.0, 1.00),
        (-15.10, -12.80, 1.0, 1.02),
    )

    px_errors = []
    deg_errors = []
    base_angle = _segment_angle_deg(p_usti, p_konec)

    for du, dv, ang_deg, scale in cases:
        warped = _warp_image_around(source_img, mid_u, mid_v, du, dv, ang_deg, scale)
        theta = math.radians(ang_deg)
        cos_t = math.cos(theta) * scale
        sin_t = math.sin(theta) * scale

        def _transform_pt(pt):
            rx = pt[0] - mid_u
            ry = pt[1] - mid_v
            return (
                mid_u + du + cos_t * rx - sin_t * ry,
                mid_v + dv + sin_t * rx + cos_t * ry,
            )

        tu = _transform_pt(p_usti)
        tk = _transform_pt(p_konec)
        det_u = detect_template_bank(warped, tmpl_u, tu[0], tu[1], search_radius=24)
        det_k = detect_template_bank(warped, tmpl_k, tk[0], tk[1], search_radius=24)
        if det_u is None or det_k is None:
            px_errors.extend([float("inf"), float("inf")])
            deg_errors.append(float("inf"))
            continue
        err_u = math.hypot(det_u[0] - tu[0], det_u[1] - tu[1])
        err_k = math.hypot(det_k[0] - tk[0], det_k[1] - tk[1])
        px_errors.extend([err_u, err_k])
        true_ang = base_angle + ang_deg
        meas_ang = _segment_angle_deg(det_u, det_k)
        deg_errors.append(_angle_diff_deg(meas_ang, true_ang))

    p95_px = round(_p95(px_errors), 4) if all(math.isfinite(x) for x in px_errors) else float("inf")
    p95_deg = round(_p95(deg_errors), 4) if all(math.isfinite(x) for x in deg_errors) else float("inf")
    ok = (
        math.isfinite(p95_px)
        and math.isfinite(p95_deg)
        and p95_px <= DETECTOR_MAX_PX
        and p95_deg <= DETECTOR_MAX_DEG
    )
    return {
        "p95_px": p95_px if math.isfinite(p95_px) else 999.0,
        "p95_deg": p95_deg if math.isfinite(p95_deg) else 999.0,
        "verdict": "PASA" if ok else "INCONCLUSO",
    }


# Orquestador 2026-11-11: un giro es un tramo continuo en que el rumbo cambia mas de TURN_MIN_DEG de forma
# monotona y dura al menos TURN_MIN_S. Rumbo suavizado (mediana movil) y pausas de hasta TURN_GAP_S unidas.
TURN_MIN_DEG = 90.0
TURN_MIN_S = 0.5
TURN_RATE_MIN_DEG_S = 20.0
TURN_GAP_S = 0.15
TURN_SMOOTH_S = 0.10


def _sample_yaw_deg(row):
    lect = row.get("lecturas") or {}
    for r in READINGS_ORDER:
        u_cand = _vec3((lect.get("usti hlavne") or {}).get(r))
        k_cand = _vec3((lect.get("konec hlavne") or {}).get(r))
        if u_cand is not None and k_cand is not None:
            d = k_cand - u_cand
            return math.degrees(math.atan2(float(d[0]), float(d[2])))
    cam_z = _vec3((row.get("cam") or {}).get("z"))
    if cam_z is not None:
        return math.degrees(math.atan2(float(cam_z[0]), float(cam_z[2])))
    return None


def detect_windows(samples):
    """Separa los frames de cada giro (giro1, giro2, ...) y el resto a partir de las muestras."""
    n = len(samples)
    if n == 0:
        return {}
    times = []
    t_acc = 0.0
    for i, row in enumerate(samples):
        t_ms = row.get("t_ms")
        if t_ms is not None:
            times.append(float(t_ms) / 1000.0)
        else:
            t_acc += float(row.get("dt") or 0.0) if i > 0 else 0.0
            times.append(t_acc)
    raw = [_sample_yaw_deg(r) for r in samples]
    last = 0.0
    for i in range(n):
        if raw[i] is None:
            raw[i] = last
        last = raw[i]
    # Desenrollar
    unwrapped = [raw[0]]
    for i in range(1, n):
        d = (raw[i] - raw[i - 1] + 180.0) % 360.0 - 180.0
        unwrapped.append(unwrapped[-1] + d)
    # Mediana movil por tiempo
    yaw = []
    for i in range(n):
        lo = i
        while lo > 0 and times[i] - times[lo - 1] <= TURN_SMOOTH_S / 2.0:
            lo -= 1
        hi = i
        while hi < n - 1 and times[hi + 1] - times[i] <= TURN_SMOOTH_S / 2.0:
            hi += 1
        yaw.append(float(np.median(unwrapped[lo:hi + 1])))
    # Signo de giro por paso (0 = quieto)
    # Velocidad sobre una base de ~TURN_SMOOTH_S (menos ruido que frame a frame)
    sign = [0] * n
    for i in range(1, n):
        j0 = i - 1
        while j0 > 0 and times[i] - times[j0] < TURN_SMOOTH_S:
            j0 -= 1
        dt = max(times[i] - times[j0], 1e-6)
        rate = (yaw[i] - yaw[j0]) / dt
        if abs(rate) >= TURN_RATE_MIN_DEG_S:
            sign[i] = 1 if rate > 0 else -1
    # Tramos de mismo signo, uniendo pausas cortas (sin cambio de signo)
    segments = []
    i = 1
    while i < n:
        if sign[i] == 0:
            i += 1
            continue
        sgn = sign[i]
        a = i - 1
        b = i
        j = i + 1
        while j < n:
            if sign[j] == sgn:
                b = j
                j += 1
                continue
            if sign[j] == 0:
                k2 = j
                while k2 < n and sign[k2] == 0 and times[k2] - times[b] <= TURN_GAP_S:
                    k2 += 1
                if k2 < n and sign[k2] == sgn and times[k2] - times[b] <= TURN_GAP_S:
                    j = k2
                    continue
            break
        segments.append((a, b))
        i = b + 1
    windows = {}
    in_turn = set()
    turn_idx = 0
    for a, b in segments:
        total = yaw[b] - yaw[a]
        if abs(total) <= TURN_MIN_DEG:
            continue
        # Duracion robusta a los bordes: del 10 % al 90 % del cambio, escalada por 1/0,8
        # (exacta para un giro a velocidad constante).
        t10 = t90 = None
        for m in range(a, b + 1):
            frac = (yaw[m] - yaw[a]) / total
            if t10 is None and frac >= 0.1:
                t10 = times[m]
            if t90 is None and frac >= 0.9:
                t90 = times[m]
        if t10 is None or t90 is None or (t90 - t10) / 0.8 < TURN_MIN_S:
            continue
        turn_idx += 1
        w_frames = [int(samples[m]["frame"]) for m in range(a, b + 1)]
        windows[f"giro{turn_idx}"] = w_frames
        in_turn.update(w_frames)
    windows["resto"] = [int(s["frame"]) for s in samples if int(s["frame"]) not in in_turn]
    return windows


def _anchor_basis(p_usti, p_konec, right_sign=1.0):
    wz = _normalize(p_konec - p_usti)
    up_world = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    wx = np.cross(up_world, wz) * float(right_sign)
    if np.linalg.norm(wx) <= 1e-6:
        wx = np.array([1.0, 0.0, 0.0], dtype=np.float64)
    else:
        wx = _normalize(wx)
    wy = _normalize(np.cross(wz, wx) * float(right_sign))
    return wx, wy, wz


def _deroll_axes(cam_x, cam_y, cam_z, cam_right_sign=None):
    """Elimina cualquier giro sobre el eje optico z respecto al vector arriba del mundo [0,1,0]."""
    z = _normalize(cam_z)
    up = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    cx = np.cross(up, z)
    if np.linalg.norm(cx) <= 1e-6:
        return _normalize(cam_x), _normalize(cam_y), z
    if cam_right_sign is not None:
        cx = cx * float(cam_right_sign)
    elif float(np.dot(cx, cam_x)) < 0.0:
        cx = -cx
    x = _normalize(cx)
    cy = np.cross(z, x)
    if float(np.dot(cy, up)) < 0.0:
        cy = -cy
    y = _normalize(cy)
    return x, y, z


def _rot_to_quat(x, y, z):
    m = np.column_stack((x, y, z))
    tr = float(m[0, 0] + m[1, 1] + m[2, 2])
    if tr > 0.0:
        s = math.sqrt(tr + 1.0) * 2.0
        w = 0.25 * s
        qx = (m[2, 1] - m[1, 2]) / s
        qy = (m[0, 2] - m[2, 0]) / s
        qz = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        qx = 0.25 * s
        qy = (m[0, 1] + m[1, 0]) / s
        qz = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        qx = (m[0, 1] + m[1, 0]) / s
        qy = 0.25 * s
        qz = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        qx = (m[0, 2] + m[2, 0]) / s
        qy = (m[1, 2] + m[2, 1]) / s
        qz = 0.25 * s
    q = np.array([w, qx, qy, qz], dtype=np.float64)
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
    s0 = math.cos(theta) - dot * math.sin(theta) / sin_0
    s1 = math.sin(theta) / sin_0
    res = s0 * q0 + s1 * q1
    return res / np.linalg.norm(res)


def build_ideal_mode_cameras(samples, reading):
    """Construye la pose de camara nominal del modo en cada frame m a partir de la lectura elegida."""
    if not samples:
        return {}
    first = samples[0]
    caso = str(first.get("caso") or "mount0")
    lect0 = first.get("lecturas") or {}
    u0 = _vec3((lect0.get("usti hlavne") or {}).get(reading))
    k0 = _vec3((lect0.get("konec hlavne") or {}).get(reading))
    cam0 = first.get("cam") or {}
    c_pos0 = _vec3(cam0.get("pos"))
    c_x0 = _vec3(cam0.get("x"))
    c_y0 = _vec3(cam0.get("y"))
    c_z0 = _vec3(cam0.get("z"))
    if u0 is None or k0 is None or c_pos0 is None or c_x0 is None or c_y0 is None or c_z0 is None:
        return {}

    wz0 = _normalize(k0 - u0)
    up_w = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    test_cx = np.cross(up_w, wz0)
    right_sign = 1.0 if float(np.dot(test_cx, c_x0)) >= 0.0 else -1.0
    cam_right_sign = 1.0 if float(np.dot(np.cross(up_w, c_z0), c_x0)) >= 0.0 else -1.0

    wx0, wy0, wz0 = _anchor_basis(u0, k0, right_sign=right_sign)
    basis0 = np.column_stack((wx0, wy0, wz0))
    x0_u, y0_u, z0_u = _deroll_axes(c_x0, c_y0, c_z0, cam_right_sign=cam_right_sign)
    local_offset = basis0.T @ (c_pos0 - u0)
    local_x = basis0.T @ x0_u
    local_y = basis0.T @ y0_u
    local_z = basis0.T @ z0_u

    ideal_by_frame = {}
    q_filt = None
    pos_filt = None

    for idx, s in enumerate(samples):
        frame = int(s["frame"])
        lect = s.get("lecturas") or {}
        us = _vec3((lect.get("usti hlavne") or {}).get(reading))
        ks = _vec3((lect.get("konec hlavne") or {}).get(reading))
        if us is None or ks is None:
            continue
        wx, wy, wz = _anchor_basis(us, ks, right_sign=right_sign)
        basis = np.column_stack((wx, wy, wz))

        if caso == "lookat":
            pos_t = c_pos0.copy()
            z_t = _normalize(us - pos_t)
            x_t, y_t, z_t = _deroll_axes(x0_u, y0_u, z_t, cam_right_sign=cam_right_sign)
        else:
            pos_t = us + basis @ local_offset
            x_t = _normalize(basis @ local_x)
            y_t = _normalize(basis @ local_y)
            z_t = _normalize(basis @ local_z)
            x_t, y_t, z_t = _deroll_axes(x_t, y_t, z_t, cam_right_sign=cam_right_sign)

        if caso == "mount03":
            q_t = _rot_to_quat(x_t, y_t, z_t)
            if idx == 0 or q_filt is None or pos_filt is None:
                pos_filt = pos_t.copy()
                q_filt = q_t.copy()
            else:
                dt = max(1e-4, float(s.get("dt", 1.0 / 60.0)))
                alpha = 1.0 - math.exp(-dt / 0.3)
                pos_filt = pos_filt + alpha * (pos_t - pos_filt)
                q_filt = _slerp(q_filt, q_t, alpha)
            fx, fy, fz = _quat_to_axes(q_filt)
            fx, fy, fz = _deroll_axes(fx, fy, fz, cam_right_sign=cam_right_sign)
            ideal_by_frame[frame] = {"pos": pos_filt.copy(), "x": fx, "y": fy, "z": fz}
        else:
            ideal_by_frame[frame] = {"pos": pos_t, "x": x_t, "y": y_t, "z": z_t}

    return ideal_by_frame


def check_turn_stimulus(run, window_frames, reading, fov_conv):
    """Comprueba que durante la ventana de giro el desplazamiento entre frames supera STIMULUS_FACTOR * THRESH_PX."""
    by_frame = run["by_frame"]
    steps_px = []
    for f in window_frames:
        cur = by_frame.get(int(f))
        prev = by_frame.get(int(f) - 1)
        if cur is None or prev is None:
            continue
        cam = cur.get("cam") or {}
        fov_rad = float(cur.get("fov_rad", 1.0471976))
        u_cur = ((cur.get("lecturas") or {}).get("usti hlavne") or {}).get(reading)
        u_prev = ((prev.get("lecturas") or {}).get("usti hlavne") or {}).get(reading)
        if u_cur is None or u_prev is None:
            continue
        p_cur = project_point(u_cur, cam, fov_rad, fov_conv)
        p_prev = project_point(u_prev, cam, fov_rad, fov_conv)
        if p_cur is not None and p_prev is not None:
            steps_px.append(math.hypot(p_cur[0] - p_prev[0], p_cur[1] - p_prev[1]))
    if not steps_px:
        return False
    return _p95(steps_px) > (STIMULUS_FACTOR * THRESH_PX)


def _detect_run_shots(run, k, fov_conv, ref_reading="a"):
    """Extrae la plantilla del primer BMP del caso y detecta los dos puntos en todos los BMP de la corrida."""
    by_frame = run["by_frame"]
    run_dir = run["dir"]
    shot_rows = [s for s in run["samples"] if s.get("shot")]
    if not shot_rows:
        return {}

    # Plantilla de la primera captura con fichero y con frame objetivo n+k existente
    # (con k=-1 la captura del frame 0 no tiene objetivo).
    # y con escena estable y textura en los dos recortes (orquestador 2026-11-11).
    first_row = None
    first_bmp = None
    target0 = None
    img0 = None
    for cand in shot_rows:
        cand_path = _shot_path(run_dir, cand["shot"])
        cand_target = by_frame.get(int(cand["frame"]) + int(k))
        if not cand_path.is_file() or cand_target is None:
            continue
        c_lect = cand_target.get("lecturas") or {}
        c_cam = cand_target.get("cam") or {}
        c_fov = float(cand_target.get("fov_rad", 1.0471976))
        cu = (c_lect.get("usti hlavne") or {}).get(ref_reading)
        ck = (c_lect.get("konec hlavne") or {}).get(ref_reading)
        if cu is None or ck is None:
            continue
        c_img = _load_gray(cand_path)
        if _textured(c_img, (project_point(cu, c_cam, c_fov, fov_conv), project_point(ck, c_cam, c_fov, fov_conv))):
            first_row, first_bmp, target0, img0 = cand, cand_path, cand_target, c_img
            break
    if first_row is None:
        return {}

    lect0 = target0.get("lecturas") or {}
    cam0 = target0.get("cam") or {}
    fov0 = float(target0.get("fov_rad", 1.0471976))

    chosen_r = ref_reading
    u0_w = (lect0.get("usti hlavne") or {}).get(chosen_r)
    k0_w = (lect0.get("konec hlavne") or {}).get(chosen_r)
    if u0_w is None or k0_w is None:
        for r in READINGS_ORDER:
            u0_w = (lect0.get("usti hlavne") or {}).get(r)
            k0_w = (lect0.get("konec hlavne") or {}).get(r)
            if u0_w is not None and k0_w is not None:
                chosen_r = r
                break
    if u0_w is None or k0_w is None:
        return {}

    pu0 = project_point(u0_w, cam0, fov0, fov_conv)
    pk0 = project_point(k0_w, cam0, fov0, fov_conv)
    if pu0 is None or pk0 is None:
        return {}

    tmpl_u = make_template_bank(img0, pu0[0], pu0[1])
    tmpl_k = make_template_bank(img0, pk0[0], pk0[1])

    detections = {}
    for row in shot_rows:
        f_num = int(row["frame"])
        bmp_path = _shot_path(run_dir, row["shot"])
        target = by_frame.get(f_num + int(k))
        if not bmp_path.is_file() or target is None:
            detections[f_num] = None
            continue
        img = _load_gray(bmp_path)
        lect = target.get("lecturas") or {}
        cam = target.get("cam") or {}
        fov = float(target.get("fov_rad", 1.0471976))
        uw = (lect.get("usti hlavne") or {}).get(chosen_r)
        kw = (lect.get("konec hlavne") or {}).get(chosen_r)
        pu = project_point(uw, cam, fov, fov_conv) if uw is not None else pu0
        pk = project_point(kw, cam, fov, fov_conv) if kw is not None else pk0
        if pu is None or pk is None or not _textured(img, (pu, pk)):
            detections[f_num] = None
            continue
        du = detect_template_bank(img, tmpl_u, pu[0], pu[1], search_radius=SEARCH_RADIUS)
        dk = detect_template_bank(img, tmpl_k, pk[0], pk[1], search_radius=SEARCH_RADIUS)
        if du is None or dk is None:
            detections[f_num] = None
        else:
            detections[f_num] = {"usti hlavne": (du[0], du[1]), "konec hlavne": (dk[0], dk[1])}
    return detections


def _eval_window_metrics(run, window_frames, detections, k, fov_conv, reading, cam_override=None, check_stim=False, base_PreCheck=""):
    by_frame = run["by_frame"]
    shot_frames = [f for f in window_frames if by_frame.get(f, {}).get("shot")]
    if not shot_frames:
        return 0.0, 0.0, 0.0, "INCONCLUSO", base_PreCheck or "no_shots_in_window"

    observed = 0
    px_errs = []
    roll_errs = []
    missing_reading = False

    for f_num in shot_frames:
        det = detections.get(f_num)
        target_f = f_num + int(k)
        target = by_frame.get(target_f)
        if target is None:
            continue
        lect = target.get("lecturas") or {}
        uw = (lect.get("usti hlavne") or {}).get(reading)
        kw = (lect.get("konec hlavne") or {}).get(reading)
        if uw is None or kw is None:
            missing_reading = True
            continue
        if det is None:
            continue
        cam = cam_override.get(target_f) if cam_override is not None else target.get("cam")
        if cam is None:
            continue
        fov = float(target.get("fov_rad", 1.0471976))
        pu = project_point(uw, cam, fov, fov_conv)
        pk = project_point(kw, cam, fov, fov_conv)
        if pu is None or pk is None:
            continue
        observed += 1
        du = det["usti hlavne"]
        dk = det["konec hlavne"]
        err_u = math.hypot(du[0] - pu[0], du[1] - pu[1])
        err_k = math.hypot(dk[0] - pk[0], dk[1] - pk[1])
        px_errs.append(max(err_u, err_k))
        ang_proj = _segment_angle_deg(pu, pk)
        ang_det = _segment_angle_deg(du, dk)
        roll_errs.append(_angle_diff_deg(ang_det, ang_proj))

    coverage = round(float(observed) / float(len(shot_frames)), 4)
    p95_px = round(_p95(px_errs), 4) if px_errs else 999.0
    roll_deg = round(_p95(roll_errs), 4) if roll_errs else 999.0

    if base_PreCheck and base_PreCheck != "t_lect_inconcluso":
        return p95_px, roll_deg, coverage, "INCONCLUSO", base_PreCheck
    if run["has_gaps"]:
        return p95_px, roll_deg, coverage, "INCONCLUSO", "frame_gaps"
    if missing_reading and observed == 0:
        return p95_px, roll_deg, coverage, "INCONCLUSO", "reading_unavailable"
    if check_stim and not check_turn_stimulus(run, window_frames, reading, fov_conv):
        return p95_px, roll_deg, coverage, "INCONCLUSO", "insufficient_stimulus"
    if coverage < COVERAGE_MIN:
        return p95_px, roll_deg, coverage, "INCONCLUSO", "low_coverage"
    if base_PreCheck:
        return p95_px, roll_deg, coverage, "INCONCLUSO", base_PreCheck
    if p95_px > THRESH_PX:
        return p95_px, roll_deg, coverage, "FALLA", "p95_px_exceeded"
    if roll_deg > THRESH_ROLL_DEG:
        return p95_px, roll_deg, coverage, "FALLA", "roll_deg_exceeded"
    return p95_px, roll_deg, coverage, "PASA", ""


def evaluate(runs_dir, out_dir=None):
    """Evalua todas las corridas en runs_dir y opcionalmente escribe informe.json e informe.md en out_dir."""
    runs = _discover_runs(runs_dir)
    calib_block = {}
    k_by_hook = {}
    fov_by_hook = {}

    for run in runs:
        if run["caso"] == "calib" and run["inject"] == "none":
            c_res = evaluate_calib_run(run)
            calib_block[run["hook"]] = c_res
            k_by_hook[run["hook"]] = c_res["k"]
            fov_by_hook[run["hook"]] = c_res.get("f_px") or "vertical"

    # Hc usa la jerarquia del motor y comparte el pipeline de captura de Ha
    if "Hc" not in k_by_hook and "Ha" in k_by_hook:
        k_by_hook["Hc"] = k_by_hook["Ha"]
        fov_by_hook["Hc"] = fov_by_hook.get("Ha", "vertical")

    detector_block = calibrate_detector(runs, k_by_hook, fov_by_hook)
    det_ok = detector_block["verdict"] == "PASA"

    positive_runs = [r for r in runs if r["caso"] != "calib" and r["inject"] == "none"]
    negative_runs = [r for r in runs if r["caso"] != "calib" and r["inject"] != "none"]

    results = []
    detections_cache = {}

    # 1. Evaluar T-lect sobre las corridas positivas
    tlect_runs = [r for r in positive_runs if r["caso"] == "mount0"] or positive_runs
    reading_verdicts = {r: [] for r in READINGS_ORDER}

    for run in tlect_runs:
        hook = run["hook"]
        calib_ok = (hook in calib_block and calib_block[hook]["verdict"] == "PASA") or (
            hook == "Hc" and calib_block.get("Ha", {}).get("verdict") == "PASA"
        )
        k_val = k_by_hook.get(hook)
        k_use = int(k_val) if k_val is not None else 0
        fov_conv = fov_by_hook.get(hook, "vertical")
        pre_cause = ""
        if not calib_ok:
            pre_cause = "calib_inconcluso"
        elif not det_ok:
            pre_cause = "detector_inconcluso"

        detections = _detect_run_shots(run, k_use, fov_conv, ref_reading="a")
        detections_cache[run["run"]] = detections
        windows = detect_windows(run["samples"])
        turn_names = [w for w in windows if w.startswith("giro")]
        no_turns_cause = "no_turn_windows" if not turn_names and not pre_cause else pre_cause

        for r in READINGS_ORDER:
            for w_name, w_frames in windows.items():
                p95_px, roll_deg, cov, verdict, cause = _eval_window_metrics(
                    run,
                    w_frames,
                    detections,
                    k_use,
                    fov_conv,
                    r,
                    cam_override=None,
                    check_stim=False,
                    base_PreCheck=no_turns_cause,
                )
                results.append(
                    {
                        "run": run["run"],
                        "caso": run["caso"],
                        "hook": hook,
                        "inject": run["inject"],
                        "measure": "T-lect",
                        "reading": r,
                        "window": w_name,
                        "p95_px": p95_px,
                        "roll_deg": roll_deg,
                        "coverage": cov,
                        "verdict": verdict,
                        "cause": cause,
                    }
                )
                reading_verdicts[r].append((hook, verdict))

    winning_reading = None
    for r in READINGS_ORDER:
        by_h = {}
        for h, v in reading_verdicts[r]:
            by_h.setdefault(h, []).append(v)
        if any(vs and all(v == "PASA" for v in vs) for vs in by_h.values()):
            winning_reading = r
            break

    eval_reading = winning_reading if winning_reading is not None else "a"

    # 2. Evaluar T-hook sobre todas las corridas positivas
    thook_by_mode_hook = {}
    for run in positive_runs:
        hook = run["hook"]
        calib_ok = (hook in calib_block and calib_block[hook]["verdict"] == "PASA") or (
            hook == "Hc" and calib_block.get("Ha", {}).get("verdict") == "PASA"
        )
        k_val = k_by_hook.get(hook)
        k_use = int(k_val) if k_val is not None else 0
        fov_conv = fov_by_hook.get(hook, "vertical")
        pre_cause = ""
        if not calib_ok:
            pre_cause = "calib_inconcluso"
        elif not det_ok:
            pre_cause = "detector_inconcluso"
        elif winning_reading is None:
            pre_cause = "t_lect_inconcluso"

        if run["run"] not in detections_cache:
            detections_cache[run["run"]] = _detect_run_shots(run, k_use, fov_conv, ref_reading=eval_reading)
        detections = detections_cache[run["run"]]

        windows = detect_windows(run["samples"])
        turn_names = [w for w in windows if w.startswith("giro")]
        no_turns_cause = "no_turn_windows" if not turn_names and not pre_cause else pre_cause
        ideal_cams = build_ideal_mode_cameras(run["samples"], eval_reading)

        w_verdicts = []
        for w_name, w_frames in windows.items():
            p95_px, roll_deg, cov, verdict, cause = _eval_window_metrics(
                run,
                w_frames,
                detections,
                k_use,
                fov_conv,
                eval_reading,
                cam_override=ideal_cams,
                check_stim=w_name.startswith("giro"),
                base_PreCheck=no_turns_cause,
            )
            results.append(
                {
                    "run": run["run"],
                    "caso": run["caso"],
                    "hook": hook,
                    "inject": run["inject"],
                    "measure": "T-hook",
                    "reading": None,
                    "window": w_name,
                    "p95_px": p95_px,
                    "roll_deg": roll_deg,
                    "coverage": cov,
                    "verdict": verdict,
                    "cause": cause,
                }
            )
            w_verdicts.append(verdict)
        thook_by_mode_hook[(run["caso"], hook)] = w_verdicts

    hook_por_modo = {}
    for mode in MODES_ORDER:
        winner = None
        for h in HOOKS_ORDER:
            vs = thook_by_mode_hook.get((mode, h))
            if vs and all(v == "PASA" for v in vs):
                winner = h
                break
        hook_por_modo[mode] = winner

    # 3. Evaluar corridas negativas (inject != none): van solo a `negativas`
    negativas = []
    for run in negative_runs:
        hook = run["hook"]
        k_val = k_by_hook.get(hook)
        k_use = int(k_val) if k_val is not None else 0
        fov_conv = fov_by_hook.get(hook, "vertical")
        detections = _detect_run_shots(run, k_use, fov_conv, ref_reading=eval_reading)
        windows = detect_windows(run["samples"])
        ideal_cams = build_ideal_mode_cameras(run["samples"], eval_reading)
        neg_verdicts = []
        for w_name, w_frames in windows.items():
            _, _, _, verdict, _ = _eval_window_metrics(
                run,
                w_frames,
                detections,
                k_use,
                fov_conv,
                eval_reading,
                cam_override=ideal_cams,
                check_stim=w_name.startswith("giro"),
                base_PreCheck="",
            )
            neg_verdicts.append(verdict)
        if "FALLA" in neg_verdicts:
            got = "FALLA"
        elif "INCONCLUSO" in neg_verdicts or not neg_verdicts:
            got = "INCONCLUSO"
        else:
            got = "PASA"
        negativas.append(
            {
                "run": run["run"],
                "inject": run["inject"],
                "expected": "FALLA",
                "got": got,
                "ok": got == "FALLA",
            }
        )

    # 4. Codigo de salida (solo cuentan las corridas con inject == none)
    thook_rows = [r for r in results if r["measure"] == "T-hook"]
    if any(r["verdict"] == "FALLA" for r in thook_rows):
        exit_code = 1
    elif (
        not calib_block
        or any(c["verdict"] != "PASA" for c in calib_block.values())
        or not det_ok
        or winning_reading is None
        or not thook_rows
        or any(r["verdict"] == "INCONCLUSO" for r in thook_rows)
    ):
        exit_code = 2
    else:
        exit_code = 0

    report = {
        "schema": 1,
        "calib": calib_block,
        "detector": detector_block,
        "results": results,
        "decisions": {
            "lectura": winning_reading,
            "hook_por_modo": hook_por_modo,
            "k": {h: calib_block[h]["k"] for h in calib_block},
        },
        "negativas": negativas,
        "exit_code": exit_code,
    }

    if out_dir is not None:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "informe.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (out_path / "informe.md").write_text(_render_markdown(report), encoding="utf-8")

    return report


def _render_markdown(report):
    verdict_str = {0: "PASA", 1: "FALLA", 2: "INCONCLUSO"}.get(report["exit_code"], "INCONCLUSO")
    lines = [
        f"# Informe S-track·1 — {verdict_str} (exit_code={report['exit_code']})",
        "",
        "## 1. Calibración de imagen (`calib`)",
        "",
        "| Hook | k | match_frac | f medida px (p05-p95, std, n) | referencia | Veredicto | Causa |",
        "|---|---|---|---|---|---|---|",
    ]
    for h, c in sorted(report["calib"].items()):
        lines.append(
            f"| {h} | {c['k']} | {c['match_frac']:.4f} | {c.get('f_px')} ({c.get('f_p05_px')}-{c.get('f_p95_px')}, {c.get('f_std_px')}, {c.get('f_n')}) | {c.get('ref_shot')} | {c['verdict']} | {c['cause']} |"
        )
    det = report["detector"]
    lines.extend(
        [
            "",
            "## 2. Calibración del detector",
            "",
            f"- `p95_px`: {det['p95_px']} px (máx {DETECTOR_MAX_PX} px)",
            f"- `p95_deg`: {det['p95_deg']}° (máx {DETECTOR_MAX_DEG}°)",
            f"- Veredicto: **{det['verdict']}**",
            "",
            "## 3. Decisiones",
            "",
            f"- **Lectura ganadora (T-lect):** `{report['decisions']['lectura']}`",
            f"- **Desfase k por hook:** `{json.dumps(report['decisions']['k'])}`",
            f"- **Hook por modo (T-hook):** `{json.dumps(report['decisions']['hook_por_modo'])}`",
            "",
            "## 4. Resultados por ventana",
            "",
            "| Run | Caso | Hook | Medida | Lectura | Ventana | p95_px | roll_deg | Cobertura | Veredicto | Causa |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for r in report["results"]:
        lines.append(
            f"| {r['run']} | {r['caso']} | {r['hook']} | {r['measure']} | {r['reading']} | "
            f"{r['window']} | {r['p95_px']} | {r['roll_deg']} | {r['coverage']} | {r['verdict']} | {r['cause']} |"
        )
    if report["negativas"]:
        lines.extend(
            [
                "",
                "## 5. Negativas",
                "",
                "| Run | Inyección | Esperado | Obtenido | OK |",
                "|---|---|---|---|---|",
            ]
        )
        for neg in report["negativas"]:
            lines.append(
                f"| {neg['run']} | {neg['inject']} | {neg['expected']} | {neg['got']} | {neg['ok']} |"
            )
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluador de la sonda S-track·1")
    parser.add_argument("runs_dir", help="Carpeta con las subcarpetas de corridas")
    parser.add_argument("--out", required=True, help="Carpeta de salida para informe.json e informe.md")
    args = parser.parse_args(argv)
    report = evaluate(args.runs_dir, args.out)
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
