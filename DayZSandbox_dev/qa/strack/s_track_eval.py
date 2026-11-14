"""Evaluador de la sonda S-track·1 (brief 2026-11-10-s-track-1-brief.md §3 y CONTRACT.md).

Lee carpetas de corridas con samples.jsonl y capturas f######.bmp, ejecuta:
1. Calibracion de desfase de frame k por correlacion horizontal de bandas y convencion de FOV.
2. Calibracion del detector de plantilla (48x48 px, ventana +-80 px, subpixel) con transformaciones sinteticas.
3. Evaluacion por ventana (cada giro y resto) de T-lect y T-hook, comprobando estimulo y cobertura.
4. Escritura de informe.json e informe.md y codigo de salida 0 (PASA), 1 (FALLA) o 2 (INCONCLUSO).
"""

import argparse
import hashlib
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
TEMPLATE_PX = 48
CORR_MIN = 0.8
MIN_SHOTS_WINDOW = 20
MASK_STD_MAX = 8.0
MASK_MIN_SHOTS = 50
MARK_AGREE_PX = 1.5
TEMPLATE_SOURCE = "marca"
USE_MASK = True
ROPA_MAX_M = 0.01
ROPA_MAX_DEG = 0.5
JUMP_MIN_M = 0.5
THRESH_SUAVE_FRAC = 0.02
QUAT_NORM_TOL = 1e-4
SUAVE_FPS_AGREE_DEG = 0.5
FPS_REGIME_TOL = 0.10
# Vuelta 4 (hallazgo 4): tolerancia del estimulo de giro. El objetivo se
# escribe como una rotacion exacta de 170 deg; extraerlo con atan2/acos en
# doble precision introduce errores muy por debajo de 0.01 deg, asi que
# 1.0 deg deja dos ordenes de margen sobre el ruido numerico y sigue siendo
# diez veces menor que la desviacion de un objetivo de 160 deg.
GIRO_TARGET_TOL_DEG = 1.0

IMAGE_W = 1920
IMAGE_H = 1080
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


def _sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _resolve_marcas_dir(runs_dir, marcas_dir=None):
    if marcas_dir is not None:
        return Path(marcas_dir)
    runs_path = Path(runs_dir)
    if (runs_path / "marcas").is_dir():
        return runs_path / "marcas"
    return Path(__file__).resolve().parent / "marcas"


def load_marcas(marcas_dir, run_name, run_dir):
    """Carga y valida las marcas de una corrida (contrato §12). Devuelve (validas, descartadas)."""
    path = Path(marcas_dir) / f"{run_name}.json"
    if not path.is_file():
        return [], [{"shot": "", "cause": "missing_marcas_file"}]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], [{"shot": "", "cause": "invalid_marcas_json"}]
    valid = []
    discarded = []
    for entry in data.get("marcas") or []:
        shot = str(entry.get("shot") or "")
        try:
            diff = float(entry.get("diff_max_px"))
        except (TypeError, ValueError):
            diff = float("inf")
        if diff > MARK_AGREE_PX:
            discarded.append({"shot": shot, "cause": "diff_max_px_exceeded", "diff_max_px": diff})
            continue
        expected = str(entry.get("sha256") or "").lower()
        png_name = entry.get("png")
        png_path = Path(run_dir) / str(png_name) if png_name else None
        # Vuelta 4 (hallazgo 6): se resuelve primero la imagen que consume el
        # detector (_shot_path: BMP o PNG homonima) y se vincula siempre su
        # contenido con la PNG validada, tambien cuando solo hay PNG.
        consumed_path = _shot_path(run_dir, shot) if shot else None
        if png_path is not None and png_path.is_file():
            if not expected or _sha256_file(png_path).lower() != expected:
                discarded.append({"shot": shot, "cause": "sha256_mismatch"})
                continue
            if consumed_path is None or not consumed_path.is_file():
                discarded.append({"shot": shot, "cause": "imagen_ilegible"})
                continue
            if consumed_path.resolve() != png_path.resolve():
                try:
                    px_png = np.asarray(Image.open(png_path).convert("L"))
                    px_consumed = np.asarray(Image.open(consumed_path).convert("L"))
                except OSError:
                    discarded.append({"shot": shot, "cause": "imagen_ilegible"})
                    continue
                if px_png.shape != px_consumed.shape or not np.array_equal(px_png, px_consumed):
                    discarded.append({"shot": shot, "cause": "imagen_distinta_png_bmp"})
                    continue
        else:
            if consumed_path is None or not consumed_path.is_file() or not expected or _sha256_file(consumed_path).lower() != expected:
                discarded.append({"shot": shot, "cause": "sha256_mismatch"})
                continue
        puntos = {}
        for name, xy in (entry.get("puntos") or {}).items():
            if isinstance(xy, (list, tuple)) and len(xy) == 2:
                try:
                    puntos[str(name)] = (float(xy[0]), float(xy[1]))
                except (TypeError, ValueError):
                    pass
        valid.append({"shot": shot, "puntos": puntos, "momento": str(entry.get("momento") or ""), "diff_max_px": diff})
    return valid, discarded


def windows_from_giro(samples):
    """Ventanas por el campo `giro` (contrato §9): giro1..giroN y resto."""
    windows = {}
    resto = []
    for row in samples:
        frame = int(row["frame"])
        try:
            giro = int(row.get("giro") or 0)
        except (TypeError, ValueError):
            giro = 0
        if giro > 0:
            windows.setdefault(f"giro{giro}", []).append(frame)
        else:
            resto.append(frame)
    windows["resto"] = resto
    return windows


def _windows_for_run(run):
    samples = run["samples"]
    if any("giro" in row for row in samples):
        return windows_from_giro(samples), True
    return detect_windows(samples), False


EXPECTED_WINDOWS = ("giro1", "giro2", "giro3", "resto")


def _require_expected_windows(windows, has_giro):
    """Vuelta 3 (hallazgo 10): con campo giro, cada ventana prevista ausente
    queda presente como vacia para que se juzgue INCONCLUSO por repeticion."""
    if not has_giro:
        return windows
    out = dict(windows)
    for name in EXPECTED_WINDOWS:
        out.setdefault(name, [])
    return out


def _shift_mask(mask, du, dv):
    if mask is None:
        return None
    out = np.zeros_like(mask, dtype=bool)
    h, w = mask.shape
    dx = int(round(float(du)))
    dy = int(round(float(dv)))
    x0_src = max(0, -dx)
    x1_src = min(w, w - dx)
    y0_src = max(0, -dy)
    y1_src = min(h, h - dy)
    if x1_src <= x0_src or y1_src <= y0_src:
        return out
    out[y0_src + dy:y1_src + dy, x0_src + dx:x1_src + dx] = mask[y0_src:y1_src, x0_src:x1_src]
    return out


def _connected_to_center(low):
    h, w = low.shape
    cy, cx = h // 2, w // 2
    if not low[cy, cx]:
        # Semilla: el píxel bajo más cercano al centro.
        ys, xs = np.nonzero(low)
        if len(ys) == 0:
            return np.zeros_like(low)
        idx = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
        cy, cx = int(ys[idx]), int(xs[idx])
    seen = np.zeros_like(low)
    stack = [(cy, cx)]
    seen[cy, cx] = True
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and low[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                stack.append((ny, nx))
    return seen


def _mask_valid(mask):
    return (
        mask is not None
        and isinstance(mask, np.ndarray)
        and mask.shape == (TEMPLATE_PX, TEMPLATE_PX)
        and int(np.asarray(mask, dtype=bool).sum()) >= 4
    )


def _mask_empty(mask):
    return not _mask_valid(mask)


def _masks_by_point(template_mask):
    """Normaliza: dict punto->mascara local, o mascara unica (solo vale como boca)."""
    if template_mask is None:
        return {}
    if isinstance(template_mask, dict):
        return {str(p): m for p, m in template_mask.items()}
    return {"usti hlavne": template_mask}


MASK_DETAIL_FILES = {"usti hlavne": "boca", "konec hlavne": "recamara", "mira": "mira"}


def _bilinear_sample_points(img, xs, ys):
    h, w = img.shape
    x = np.clip(np.asarray(xs, dtype=np.float64), 0.0, float(w - 1) - 1e-6)
    y = np.clip(np.asarray(ys, dtype=np.float64), 0.0, float(h - 1) - 1e-6)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1 = np.minimum(x0 + 1, w - 1)
    y1 = np.minimum(y0 + 1, h - 1)
    wx = x - x0
    wy = y - y0
    ia = img[y0, x0].astype(np.float64, copy=False)
    ib = img[y0, x1].astype(np.float64, copy=False)
    ic = img[y1, x0].astype(np.float64, copy=False)
    id_ = img[y1, x1].astype(np.float64, copy=False)
    return (1.0 - wy) * ((1.0 - wx) * ia + wx * ib) + wy * ((1.0 - wx) * ic + wx * id_)


def _paste_masked_patch_subpixel(synth, source_img, src_center, tgt_center, mask):
    """Pega el parche enmascarado con centro subpixel coherente con extract_template (offset -23.5)."""
    su, sv = float(src_center[0]), float(src_center[1])
    tu, tv = float(tgt_center[0]), float(tgt_center[1])
    half = TEMPLATE_PX // 2
    x_lo = max(0, int(math.floor(tu)) - half - 1)
    x_hi = min(synth.shape[1], int(math.ceil(tu)) + half + 2)
    y_lo = max(0, int(math.floor(tv)) - half - 1)
    y_hi = min(synth.shape[0], int(math.ceil(tv)) + half + 2)
    if x_hi <= x_lo or y_hi <= y_lo:
        return
    xs, ys = np.meshgrid(
        np.arange(x_lo, x_hi, dtype=np.float64), np.arange(y_lo, y_hi, dtype=np.float64)
    )
    m = _bilinear_sample_points(np.asarray(mask, dtype=np.float64), xs - tu + 0.5 * (TEMPLATE_PX - 1), ys - tv + 0.5 * (TEMPLATE_PX - 1))
    sampled = _bilinear_sample_points(source_img, xs - (tu - su), ys - (tv - sv))
    region = synth[y_lo:y_hi, x_lo:x_hi]
    take = m > 0.5
    region[take] = sampled[take]
    synth[y_lo:y_hi, x_lo:x_hi] = region


def build_masks_from_run(run, marcas, k, fov_conv):
    """Una mascara por detalle (boca, recamara y mira en ropa), en coordenadas locales de su plantilla.

    Por detalle: cultivos centrados en su marca, alineados por la proyeccion de su
    lectura (a) en cada captura de giro, con std temporal < MASK_STD_MAX sobre
    >= MASK_MIN_SHOTS capturas y componente conexa al centro.
    """
    masks = {}
    if not marcas:
        return masks
    by_frame = run["by_frame"]
    giro_frames = set()
    for row in run["samples"]:
        try:
            if int(row.get("giro") or 0) > 0:
                giro_frames.add(int(row["frame"]))
        except (TypeError, ValueError):
            pass
    if not giro_frames:
        wins, _has = _windows_for_run(run)
        for name, frames in wins.items():
            if name.startswith("giro"):
                giro_frames.update(frames)
    point_names = []
    for mark in marcas:
        for name in mark["puntos"]:
            if name not in point_names:
                point_names.append(name)
    half = TEMPLATE_PX // 2
    # Ancla por detalle: marca y desplazamiento marca-proyeccion en su captura.
    anchors = {}
    for point in point_names:
        first = None
        for mark in marcas:
            if point in mark["puntos"]:
                first = mark
                break
        if first is None:
            continue
        cu, cv = first["puntos"][point]
        anchors[point] = (cu, cv, (0.0, 0.0))
    # Una sola carga por captura para todos los detalles.
    # Vuelta 3 (hallazgo 12): en mount0 el montaje es rigido y el arma queda
    # quieta en imagen; los cultivos se anclan a la marca, nunca a la
    # proyeccion de una lectura candidata (p. ej. (a)), que es lo que se juzga.
    crops_by_point = {p: [] for p in anchors}
    for row in run["samples"]:
        if int(row["frame"]) not in giro_frames or not row.get("shot"):
            continue
        path = _shot_path(run["dir"], row["shot"])
        if not path.is_file():
            continue
        img = None
        for point, (cu, cv, anchor_delta) in anchors.items():
            center_u, center_v = cu, cv
            if img is None:
                img = _load_gray(path)
            x0 = int(round(center_u)) - half
            y0 = int(round(center_v)) - half
            if x0 < 0 or y0 < 0 or x0 + TEMPLATE_PX > img.shape[1] or y0 + TEMPLATE_PX > img.shape[0]:
                continue
            crop = img[y0:y0 + TEMPLATE_PX, x0:x0 + TEMPLATE_PX].astype(np.float64)
            # Un cultivo plano (oclusión, carga o fundido) no define el arma: fuera de la mascara.
            if float(crop.std()) < TEXTURE_MIN_STD:
                continue
            crops_by_point[point].append(crop)
    for point in point_names:
        crops = crops_by_point.get(point, [])
        if len(crops) < MASK_MIN_SHOTS:
            masks[point] = None
            continue
        stack = np.stack(crops, axis=0)
        std = stack.std(axis=0)
        low = std < MASK_STD_MAX
        masks[point] = _connected_to_center(low)
    return masks


def build_mask_from_run(run, marcas, k, fov_conv):
    """Compatibilidad: la mascara de la boca de build_masks_from_run."""
    return build_masks_from_run(run, marcas, k, fov_conv).get("usti hlavne")


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


def _crop_std(img, u, v_px, size=TEMPLATE_PX):
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


def extract_template(img, u, v_px, size=TEMPLATE_PX, mask=None):
    """Extrae una plantilla centrada en (u, v_px) con interpolacion bilineal exacta."""
    half = 0.5 * float(size - 1)
    xs = float(u) + (np.arange(size, dtype=np.float64) - half)
    ys = float(v_px) + (np.arange(size, dtype=np.float64) - half)
    patch = _bilinear_sample_grid(img, xs, ys)
    use_mask = mask if (USE_MASK and mask is not None) else None
    if use_mask is not None:
        m = np.asarray(use_mask, dtype=bool)
        # Hallazgo 1: mascara vacia o invalida nunca cae en silencio a "sin mascara":
        # plantilla sin norma (sin deteccion posible), marcada como vacia.
        if m.shape != patch.shape or int(m.sum()) < 4:
            return {"patch": patch, "zm": np.zeros_like(patch), "norm": 0.0, "size": size, "mask": None, "mask_empty": True}
        mean = float(patch[m].mean())
        zm = (patch - mean) * m
        norm = float(np.linalg.norm(zm))
        return {"patch": patch, "zm": zm, "norm": norm, "size": size, "mask": m}
    mean = float(patch.mean())
    zm = patch - mean
    norm = float(np.linalg.norm(zm))
    return {
        "patch": patch,
        "zm": zm,
        "norm": norm,
        "size": size,
        "mask": None,
    }


def _box_sum(arr, size):
    p = np.pad(arr, ((1, 0), (1, 0)), mode="constant", constant_values=0.0)
    cs = np.cumsum(np.cumsum(p, axis=0), axis=1)
    return cs[size:, size:] - cs[:-size, size:] - cs[size:, :-size] + cs[:-size, :-size]


def _ncc_at(crop_f64, tmpl, u_c, v_c, grid_idx):
    patch = _bilinear_sample_grid(crop_f64, u_c + grid_idx, v_c + grid_idx)
    mask = tmpl.get("mask") if USE_MASK else None
    if mask is not None:
        zm = (patch - float(patch[mask].mean())) * mask
    else:
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
    mask = tmpl.get("mask") if USE_MASK else None
    if mask is not None:
        mf = np.asarray(mask, dtype=np.float64)
        count = float(mf.sum())
        dots = np.fft.irfft2(
            np.fft.rfft2(crop, s=(fh, fw)) * np.conj(np.fft.rfft2(tmpl["zm"], s=(fh, fw))),
            s=(fh, fw),
        )[:out_h, :out_w]
        sum_m = np.fft.irfft2(
            np.fft.rfft2(crop, s=(fh, fw)) * np.conj(np.fft.rfft2(mf, s=(fh, fw))),
            s=(fh, fw),
        )[:out_h, :out_w]
        sum_m2 = np.fft.irfft2(
            np.fft.rfft2(crop * crop, s=(fh, fw)) * np.conj(np.fft.rfft2(mf, s=(fh, fw))),
            s=(fh, fw),
        )[:out_h, :out_w]
        w_var = sum_m2 - (sum_m * sum_m) / max(count, 1.0)
        w_norm = np.sqrt(np.maximum(w_var, 0.0))
    else:
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


def make_template_bank(img, u, v_px, size=None, mask=None):
    """Plantillas del entorno de (u, v_px) giradas BANK_ANGLES_DEG y escaladas BANK_SCALES alrededor del punto."""
    size = TEMPLATE_PX if size is None else size
    use_mask = mask if USE_MASK else None
    bank = []
    mask_img = None
    if use_mask is not None:
        mask_img = np.zeros(img.shape, dtype=np.float64)
        half = size // 2
        x0 = int(round(float(u))) - half
        y0 = int(round(float(v_px))) - half
        mh, mw = np.asarray(use_mask).shape
        xa, xb = max(0, x0), min(img.shape[1], x0 + mw)
        ya, yb = max(0, y0), min(img.shape[0], y0 + mh)
        if xb > xa and yb > ya:
            mask_img[ya:yb, xa:xb] = np.asarray(use_mask, dtype=np.float64)[ya - y0:yb - y0, xa - x0:xb - x0]
    for ang in BANK_ANGLES_DEG:
        for scl in BANK_SCALES:
            warped = img if (ang == 0.0 and scl == 1.0) else _warp_image_around(img, u, v_px, 0.0, 0.0, float(ang), float(scl))
            warped_mask = None
            if mask_img is not None:
                if ang == 0.0 and scl == 1.0:
                    warped_mask = np.asarray(use_mask, dtype=bool)
                else:
                    warped_m_img = _warp_image_around(mask_img, u, v_px, 0.0, 0.0, float(ang), float(scl))
                    warped_mask = extract_template(warped_m_img, u, v_px, size)["patch"] > 0.5
            tmpl = extract_template(warped, u, v_px, size, mask=warped_mask)
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


def _calibrate_detector_once(runs, k_by_hook, fov_by_hook, template_mask=None, background_images=None):
    """Calibra el detector sobre un BMP real con desplazamientos subpixel, giros +-2 deg y escalas +-5 %."""
    source_img = None
    p_usti = None
    p_konec = None

    # La mascara se construye desde mount0: la fuente de calibracion se busca
    # primero en mount0 (misma procedencia) y solo despues en los demas casos.
    source_runs = sorted(runs, key=lambda r: 0 if r["caso"] == "mount0" else 1)
    for run in source_runs:
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
        return {"p95_px": float("inf"), "p95_deg": float("inf"), "verdict": "INCONCLUSO", "cause": "sin_fuente_detector"}

    # Una mascara por detalle, en sus coordenadas locales (hallazgo 1): sin trasladar la de la boca.
    masks = _masks_by_point(template_mask)
    mask_u = masks.get("usti hlavne")
    mask_k = masks.get("konec hlavne")
    if USE_MASK and template_mask is not None and (_mask_empty(mask_u) or _mask_empty(mask_k)):
        return {"p95_px": 999.0, "p95_deg": 999.0, "verdict": "INCONCLUSO", "cause": "mascara_vacia"}
    tmpl_u = make_template_bank(source_img, p_usti[0], p_usti[1], mask=mask_u)
    tmpl_k = make_template_bank(source_img, p_konec[0], p_konec[1], mask=mask_k)
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

    # Fondo cambiante: pegar el arma enmascarada sobre fondos de otras capturas,
    # con coordenadas subpixel coherentes con la extraccion (hallazgo 2).
    # Vuelta 3 (hallazgo 13): se repite con los dos detalles y se comprueba
    # tambien el angulo del segmento boca-recamara.
    bg_px_errors = []
    bg_deg_errors = []
    bgs = list(background_images or [])
    if USE_MASK and _mask_valid(mask_u) and _mask_valid(mask_k):
        if not bgs:
            for run in runs:
                for row in run["samples"]:
                    if not row.get("shot"):
                        continue
                    bp = _shot_path(run["dir"], row["shot"])
                    if bp.is_file():
                        cand = _load_gray(bp)
                        if cand.shape == source_img.shape and float(np.abs(cand - source_img).mean()) > 1.0:
                            bgs.append(cand)
                    if len(bgs) >= 3:
                        break
                if len(bgs) >= 3:
                    break
        for bg in bgs[:3]:
            for du, dv in ((12.0, -7.0), (-9.0, 11.0)):
                synth = np.array(bg, dtype=np.float64, copy=True)
                tgt_u = (p_usti[0] + du, p_usti[1] + dv)
                tgt_k = (p_konec[0] + du, p_konec[1] + dv)
                _paste_masked_patch_subpixel(synth, source_img, p_usti, tgt_u, np.asarray(mask_u, dtype=bool))
                _paste_masked_patch_subpixel(synth, source_img, p_konec, tgt_k, np.asarray(mask_k, dtype=bool))
                synth32 = synth.astype(np.float32)
                det_u = detect_template_bank(synth32, tmpl_u, tgt_u[0], tgt_u[1], search_radius=24)
                det_k = detect_template_bank(synth32, tmpl_k, tgt_k[0], tgt_k[1], search_radius=24)
                if det_u is None or det_u[2] < CORR_MIN:
                    bg_px_errors.append(float("inf"))
                else:
                    bg_px_errors.append(math.hypot(det_u[0] - tgt_u[0], det_u[1] - tgt_u[1]))
                if det_k is None or det_k[2] < CORR_MIN:
                    bg_px_errors.append(float("inf"))
                else:
                    bg_px_errors.append(math.hypot(det_k[0] - tgt_k[0], det_k[1] - tgt_k[1]))
                if det_u is None or det_k is None:
                    bg_deg_errors.append(float("inf"))
                else:
                    true_ang = _segment_angle_deg(tgt_u, tgt_k)
                    meas_ang = _segment_angle_deg(det_u, det_k)
                    bg_deg_errors.append(_angle_diff_deg(meas_ang, true_ang))
    p95_bg_px = round(_p95(bg_px_errors), 4) if bg_px_errors and all(math.isfinite(x) for x in bg_px_errors) else (999.0 if bg_px_errors else None)
    p95_bg_deg = round(_p95(bg_deg_errors), 4) if bg_deg_errors and all(math.isfinite(x) for x in bg_deg_errors) else (999.0 if bg_deg_errors else None)

    p95_px = round(_p95(px_errors), 4) if all(math.isfinite(x) for x in px_errors) else float("inf")
    p95_deg = round(_p95(deg_errors), 4) if all(math.isfinite(x) for x in deg_errors) else float("inf")
    # Hallazgo 3: con USE_MASK, sin calibracion de fondo cambiante no hay PASA con la calibracion vieja.
    bg_missing = USE_MASK and not bg_px_errors
    ok = (
        math.isfinite(p95_px)
        and math.isfinite(p95_deg)
        and p95_px <= DETECTOR_MAX_PX
        and p95_deg <= DETECTOR_MAX_DEG
        and not bg_missing
        and (p95_bg_px is None or (math.isfinite(p95_bg_px) and p95_bg_px <= DETECTOR_MAX_PX))
        and (p95_bg_deg is None or (math.isfinite(p95_bg_deg) and p95_bg_deg <= DETECTOR_MAX_DEG))
    )
    if bg_missing:
        cause = "sin_calibracion_fondo"
    elif not ok:
        cause = "detector_fuera_de_umbral"
    else:
        cause = ""
    out = {
        "p95_px": p95_px if math.isfinite(p95_px) else 999.0,
        "p95_deg": p95_deg if math.isfinite(p95_deg) else 999.0,
        "verdict": "PASA" if ok else "INCONCLUSO",
        "cause": cause,
    }
    if p95_bg_px is not None:
        out["p95_bg_px"] = p95_bg_px
    if p95_bg_deg is not None:
        out["p95_bg_deg"] = p95_bg_deg
    return out


def calibrate_detector(runs, k_by_hook, fov_by_hook, template_mask=None, background_images=None, mask_by_hook=None):
    """Vuelta 4 (hallazgo 5): cada pareja de mascaras conserva su procedencia.

    Con mask_by_hook, cada pareja valida se calibra solo con capturas de su
    hook (su fuente y sus centros); si esa calibracion no pasa, se prueba la
    siguiente pareja valida. Sin mask_by_hook se conserva el camino previo.
    """
    if not mask_by_hook:
        return _calibrate_detector_once(runs, k_by_hook, fov_by_hook, template_mask=template_mask, background_images=background_images)
    ordered = [h for h in HOOKS_ORDER if h in mask_by_hook] + [h for h in mask_by_hook if h not in HOOKS_ORDER]
    first_failure = None
    any_valid = False
    for hook in ordered:
        masks = mask_by_hook[hook]
        by_point = _masks_by_point(masks)
        if USE_MASK and (_mask_empty(by_point.get("usti hlavne")) or _mask_empty(by_point.get("konec hlavne"))):
            continue
        any_valid = True
        scoped = [r for r in runs if r.get("hook") == hook]
        if not scoped:
            continue
        res = _calibrate_detector_once(scoped, k_by_hook, fov_by_hook, template_mask=masks, background_images=background_images)
        res = dict(res, mask_hook=hook)
        if res["verdict"] == "PASA":
            return res
        if first_failure is None:
            first_failure = res
    if first_failure is not None:
        return first_failure
    if not any_valid:
        return {"p95_px": 999.0, "p95_deg": 999.0, "verdict": "INCONCLUSO", "cause": "mascara_vacia"}
    return {"p95_px": float("inf"), "p95_deg": float("inf"), "verdict": "INCONCLUSO", "cause": "sin_fuente_detector"}


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
    # Ventanas sin etiqueta `giro` (H1): medida de reloj de pared, se queda
    # en t_ms; no fecha nada del filtro.
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
                # Filtro de mount03 (H1): aplicar alpha frame a frame con el
                # dt de cada frame es integrar sobre el eje Σdt; no usa t_ms.
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


def _detect_run_shots(run, k, fov_conv, ref_reading="a", marcas=None, mask=None):
    """Extrae la plantilla (en la marca si TEMPLATE_SOURCE='marca') y detecta los dos puntos."""
    by_frame = run["by_frame"]
    run_dir = run["dir"]
    shot_rows = [s for s in run["samples"] if s.get("shot")]
    if not shot_rows:
        return {}

    chosen_r = ref_reading
    pu0 = pk0 = None
    img0 = None
    if TEMPLATE_SOURCE == "marca":
        if not marcas:
            return {}
        for mark in marcas:
            if "usti hlavne" not in mark["puntos"] or "konec hlavne" not in mark["puntos"]:
                continue
            cand_path = _shot_path(run_dir, mark["shot"])
            if not cand_path.is_file():
                continue
            img0 = _load_gray(cand_path)
            pu0 = mark["puntos"]["usti hlavne"]
            pk0 = mark["puntos"]["konec hlavne"]
            break
        if img0 is None or pu0 is None or pk0 is None:
            return {}
    else:
        first_row = None
        target0 = None
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
                first_row, target0, img0 = cand, cand_target, c_img
                break
        if first_row is None or target0 is None:
            return {}
        lect0 = target0.get("lecturas") or {}
        cam0 = target0.get("cam") or {}
        fov0 = float(target0.get("fov_rad", 1.0471976))
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

    # Una mascara por detalle en sus coordenadas locales (hallazgo 1); una vacia
    # invalida la deteccion en vez de caer a "sin mascara".
    _masks = _masks_by_point(mask)
    _mask_u = _masks.get("usti hlavne") if _masks else None
    _mask_k = _masks.get("konec hlavne") if _masks else None
    if USE_MASK and _masks and (_mask_empty(_mask_u) or _mask_empty(_mask_k)):
        return {}
    tmpl_u = make_template_bank(img0, pu0[0], pu0[1], mask=_mask_u)
    tmpl_k = make_template_bank(img0, pk0[0], pk0[1], mask=_mask_k)

    detections = {}
    prev_det = None
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
        pu = project_point(uw, cam, fov, fov_conv) if uw is not None else None
        pk = project_point(kw, cam, fov, fov_conv) if kw is not None else None
        # Vuelta 4 (hallazgo 7): la proyeccion de "a" ya no descarta la
        # captura. Centros de busqueda, en orden: proyeccion de "a",
        # deteccion previa y marca (pu0/pk0). La textura se comprueba en
        # el candidato detectado, no en la proyeccion de "a".
        if float(img.mean()) >= SCENE_MAX_MEAN:
            detections[f_num] = None
            continue
        attempts = []
        for cand in ((pu, pk), prev_det, (pu0, pk0)):
            if cand is None or cand[0] is None or cand[1] is None:
                continue
            if any(math.hypot(cand[0][0] - a[0][0], cand[0][1] - a[0][1]) < 1.0 and math.hypot(cand[1][0] - a[1][0], cand[1][1] - a[1][1]) < 1.0 for a in attempts):
                continue
            attempts.append(cand)
        du = dk = None
        for cand_u, cand_k in attempts:
            du = detect_template_bank(img, tmpl_u, cand_u[0], cand_u[1], search_radius=SEARCH_RADIUS)
            dk = detect_template_bank(img, tmpl_k, cand_k[0], cand_k[1], search_radius=SEARCH_RADIUS)
            if du is not None and dk is not None:
                break
            du = dk = None
        if du is None or dk is None:
            detections[f_num] = None
            continue
        if _crop_std(img, du[0], du[1]) < TEXTURE_MIN_STD or _crop_std(img, dk[0], dk[1]) < TEXTURE_MIN_STD:
            detections[f_num] = None
            continue
        detections[f_num] = {"usti hlavne": (du[0], du[1]), "konec hlavne": (dk[0], dk[1]), "corr": min(float(du[2]), float(dk[2]))}
        prev_det = ((du[0], du[1]), (dk[0], dk[1]))
    return detections


def _eval_window_metrics(run, window_frames, detections, k, fov_conv, reading, cam_override=None, check_stim=False, base_PreCheck="", apply_min_shots=True):
    by_frame = run["by_frame"]
    shot_frames = [f for f in window_frames if by_frame.get(f, {}).get("shot")]
    n_shots = len(shot_frames)
    if not shot_frames:
        return 0.0, 0.0, 0.0, "INCONCLUSO", base_PreCheck or "no_shots_in_window", n_shots
    # Hallazgo 4: el minimo se aplica siempre, tambien a ventanas inferidas sin campo `giro`.
    if n_shots < MIN_SHOTS_WINDOW:
        return 999.0, 999.0, 0.0, "INCONCLUSO", "insufficient_sampling", n_shots

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
        if det is None or float(det.get("corr", 1.0)) < CORR_MIN:
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
        return p95_px, roll_deg, coverage, "INCONCLUSO", base_PreCheck, n_shots
    if run["has_gaps"]:
        return p95_px, roll_deg, coverage, "INCONCLUSO", "frame_gaps", n_shots
    if missing_reading and observed == 0:
        return p95_px, roll_deg, coverage, "INCONCLUSO", "reading_unavailable", n_shots
    if check_stim and not check_turn_stimulus(run, window_frames, reading, fov_conv):
        return p95_px, roll_deg, coverage, "INCONCLUSO", "insufficient_stimulus", n_shots
    if coverage < COVERAGE_MIN:
        return p95_px, roll_deg, coverage, "INCONCLUSO", "low_coverage", n_shots
    if base_PreCheck:
        return p95_px, roll_deg, coverage, "INCONCLUSO", base_PreCheck, n_shots
    if p95_px > THRESH_PX:
        return p95_px, roll_deg, coverage, "FALLA", "p95_px_exceeded", n_shots
    if roll_deg > THRESH_ROLL_DEG:
        return p95_px, roll_deg, coverage, "FALLA", "roll_deg_exceeded", n_shots
    return p95_px, roll_deg, coverage, "PASA", "", n_shots


def _eval_tmarca_rows(run, marcas, k, fov_conv):
    """Distancia proyección↔marca por lectura (medida T-marca, umbral THRESH_PX)."""
    rows = []
    by_frame = run["by_frame"]
    # Puntos habituales del arma y, en ropa, el punto mira.
    point_names = []
    for mark in marcas or []:
        for name in mark["puntos"]:
            if name not in point_names:
                point_names.append(name)
    readings = list(READINGS_ORDER)
    # Vuelta 3 (hallazgo 14): las marcas deben cubrir las fases del brief §4
    # (estable, mitad de cada giro y del resto); sin esa evidencia no hay PASA.
    required_momentos = {"estable", "giro1", "giro2", "giro3", "resto"}
    for reading in readings:
        dists = []
        roll_dists = []
        used = 0
        momentos_used = set()
        for mark in marcas or []:
            # Localizar el frame de la captura marcada.
            shot_frame = None
            for row in run["samples"]:
                if row.get("shot") == mark["shot"]:
                    shot_frame = int(row["frame"])
                    break
            if shot_frame is None:
                continue
            target = by_frame.get(shot_frame + int(k))
            if target is None:
                continue
            lect = target.get("lecturas") or {}
            cam = target.get("cam") or {}
            fov = float(target.get("fov_rad", 1.0471976))
            per_mark = []
            for pname in point_names:
                if pname not in mark["puntos"]:
                    continue
                world = (lect.get(pname) or {}).get(reading)
                if world is None:
                    continue
                proj = project_point(world, cam, fov, fov_conv)
                if proj is None:
                    continue
                per_mark.append((pname, math.hypot(proj[0] - mark["puntos"][pname][0], proj[1] - mark["puntos"][pname][1]), proj, mark["puntos"][pname]))
            if not per_mark:
                continue
            used += 1
            if mark.get("momento"):
                momentos_used.add(str(mark["momento"]))
            dists.extend(d for _n, d, _p, _m in per_mark)
            if len(per_mark) >= 2:
                proj_seg = _segment_angle_deg(per_mark[0][2], per_mark[1][2])
                mark_seg = _segment_angle_deg(per_mark[0][3], per_mark[1][3])
                roll_dists.append(_angle_diff_deg(proj_seg, mark_seg))
        if not marcas:
            verdict, cause = "INCONCLUSO", "sin_marcas"
            p95_px, roll_deg, cov = 999.0, 999.0, 0.0
        elif used == 0:
            verdict, cause = "INCONCLUSO", "sin_marcas"
            p95_px, roll_deg, cov = 999.0, 999.0, 0.0
        else:
            p95_px = round(_p95(dists), 4) if dists else 999.0
            roll_deg = round(_p95(roll_dists), 4) if roll_dists else 0.0
            cov = round(float(used) / float(len(marcas)), 4)
            if not required_momentos.issubset(momentos_used):
                verdict, cause = "INCONCLUSO", "marcas_fases_ausentes"
            elif p95_px > THRESH_PX:
                verdict, cause = "FALLA", "p95_px_exceeded"
            elif roll_deg > THRESH_ROLL_DEG:
                verdict, cause = "FALLA", "roll_deg_exceeded"
            else:
                verdict, cause = "PASA", ""
        rows.append({
            "run": run["run"], "caso": run["caso"], "hook": run["hook"], "inject": run["inject"],
            "measure": "T-marca", "reading": reading, "window": "marcas",
            "p95_px": p95_px, "roll_deg": roll_deg, "coverage": cov,
            "verdict": verdict, "cause": cause, "n_shots": used,
        })
    return rows


def _pose_arrays(pose):
    if not isinstance(pose, dict):
        return None
    pos = _vec3(pose.get("pos"))
    x = _vec3(pose.get("x"))
    y = _vec3(pose.get("y"))
    z = _vec3(pose.get("z"))
    if pos is None or x is None or y is None or z is None:
        return None
    return pos, np.column_stack((x, y, z))


def _mira_mark_distances(run, marcas, k, fov_conv, reading):
    dists = []
    by_frame = run["by_frame"]
    for mark in marcas or []:
        if "mira" not in mark["puntos"]:
            continue
        shot_frame = None
        for row in run["samples"]:
            if row.get("shot") == mark["shot"]:
                shot_frame = int(row["frame"])
                break
        if shot_frame is None:
            continue
        target = by_frame.get(shot_frame + int(k))
        if target is None:
            continue
        world = ((target.get("lecturas") or {}).get("mira") or {}).get(reading)
        if world is None:
            continue
        proj = project_point(world, target.get("cam") or {}, float(target.get("fov_rad", 1.0471976)), fov_conv)
        if proj is None:
            continue
        dists.append(math.hypot(proj[0] - mark["puntos"]["mira"][0], proj[1] - mark["puntos"]["mira"][1]))
    return dists


def evaluate_ropa_run(run, marcas, k, fov_conv, calib_ok=True):
    """T-ropa: variación de la pose relativa por categoría, con (a) y con (f).

    Sin calibracion valida (calib_ok=False) el contraste visual de la mira es
    INCONCLUSO y la parte numerica queda como informacion (hallazgos 9 y 10).
    """
    rows = []
    decisions = {}
    mapping = {"mochila": "spine3", "mira": "arma", "silenciador": "arma"}
    mira_ok_by_reading = {}
    mira_dists_by_reading = {}
    # Vuelta 4 (hallazgo 8): T-ropa exige cobertura manual completa de la
    # mira (las cinco fases), no una sola marca.
    mira_momentos = {str(m.get("momento") or "") for m in (marcas or []) if "mira" in m.get("puntos", {})}
    mira_marks_total = sum(1 for m in (marcas or []) if "mira" in m.get("puntos", {}))
    mira_coverage_ok = {"estable", "giro1", "giro2", "giro3", "resto"}.issubset(mira_momentos)
    for reading in ("a", "f"):
        if calib_ok:
            dists = _mira_mark_distances(run, marcas, k, fov_conv, reading)
        else:
            dists = []
        mira_dists_by_reading[reading] = dists
        mira_ok_by_reading[reading] = bool(
            dists and len(dists) >= mira_marks_total and mira_coverage_ok and _p95(dists) <= THRESH_PX
        )
    for category, ref_name in mapping.items():
        cat_verdicts = []
        for reading in ("a", "f"):
            rel_series = []
            total = 0
            valid_giro = 0
            valid_fuera = 0
            for row in run["samples"]:
                ropa = row.get("ropa") or {}
                cat_pose = _pose_arrays((ropa.get(category) or {}).get(reading) if isinstance(ropa.get(category), dict) else None)
                ref_pose = _pose_arrays((ropa.get(ref_name) or {}).get(reading) if isinstance(ropa.get(ref_name), dict) else None)
                total += 1
                if cat_pose is None or ref_pose is None:
                    continue
                rel_pos = ref_pose[1].T @ (cat_pose[0] - ref_pose[0])
                rel_rot = ref_pose[1].T @ cat_pose[1]
                rel_series.append((rel_pos, rel_rot))
                try:
                    en_giro = int(row.get("giro") or 0) > 0
                except (TypeError, ValueError):
                    en_giro = False
                if en_giro:
                    valid_giro += 1
                else:
                    valid_fuera += 1
            if not rel_series:
                p95_m, p95_deg, cov = 999.0, 999.0, 0.0
                verdict, cause = "INCONCLUSO", "categoria_ausente"
            else:
                ref_pos, ref_rot = rel_series[0]
                pos_devs = [float(np.linalg.norm(p - ref_pos)) for p, _r in rel_series]
                ang_devs = []
                for _p, rot in rel_series:
                    rel = rot @ ref_rot.T
                    tr = float(np.trace(rel))
                    ang = math.degrees(math.acos(max(-1.0, min(1.0, 0.5 * (tr - 1.0)))))
                    ang_devs.append(ang)
                p95_m = round(_p95(pos_devs), 6)
                p95_deg = round(_p95(ang_devs), 4)
                # Vuelta 3 (hallazgo 11): cobertura sobre el intervalo esperado
                # (span de frames), no sobre las filas presentes; los huecos cuentan.
                frames_present = [int(r.get("frame") or 0) for r in run["samples"]]
                expected_span = (max(frames_present) - min(frames_present) + 1) if frames_present else max(total, 1)
                cov = round(float(len(rel_series)) / float(max(expected_span, 1)), 4)
                # Hallazgo 9: cobertura >= COVERAGE_MIN y presencia en giro y fuera de giro.
                if run.get("has_gaps") or cov < COVERAGE_MIN or valid_giro == 0 or valid_fuera == 0:
                    verdict, cause = "INCONCLUSO", "ropa_cobertura_insuficiente"
                elif not calib_ok:
                    # Hallazgo 10: sin calibracion valida no se sustituye por k=0/focal vertical.
                    verdict, cause = "INCONCLUSO", "calib_inconcluso"
                elif not mira_ok_by_reading.get(reading, False):
                    if mira_dists_by_reading.get(reading) and _p95(mira_dists_by_reading[reading]) > THRESH_PX:
                        verdict, cause = "FALLA", "mira_marca_exceeded"
                    elif mira_dists_by_reading.get(reading):
                        verdict, cause = "INCONCLUSO", "mira_marca_incompleta"
                    else:
                        verdict, cause = "INCONCLUSO", "mira_sin_marca_valida"
                elif p95_m >= ROPA_MAX_M or p95_deg >= ROPA_MAX_DEG:
                    verdict, cause = "FALLA", "ropa_pose_exceeded"
                else:
                    verdict, cause = "PASA", ""
            cat_verdicts.append(verdict)
            rows.append({
                "run": run["run"], "caso": run["caso"], "hook": run["hook"], "inject": run["inject"],
                "measure": "T-ropa", "reading": reading, "window": "completa",
                "p95_px": 999.0, "roll_deg": p95_deg, "coverage": cov,
                "verdict": verdict, "cause": cause,
                "category": category, "p95_m": p95_m, "p95_deg": p95_deg,
            })
        if cat_verdicts and all(v == "PASA" for v in cat_verdicts):
            decisions[category] = "sigue"
        elif any(v == "FALLA" for v in cat_verdicts):
            decisions[category] = "no_sigue"
        else:
            decisions[category] = None
    return rows, decisions


def _quat_xyzw(v):
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        return None
    try:
        x, y, z, w = (float(v[0]), float(v[1]), float(v[2]), float(v[3]))
    except (TypeError, ValueError):
        return None
    q = np.array([w, x, y, z], dtype=np.float64)
    n = float(np.linalg.norm(q))
    if n <= 1e-12 or not np.all(np.isfinite(q)):
        return None
    return q


def _quat_raw_xyzw(v):
    if not isinstance(v, (list, tuple)) or len(v) != 4:
        return None
    try:
        return np.array([float(v[3]), float(v[0]), float(v[1]), float(v[2])], dtype=np.float64)
    except (TypeError, ValueError):
        return None


def _quat_angle_deg(q1, q2):
    if q1 is None or q2 is None:
        return 999.0
    n1 = float(np.linalg.norm(q1))
    n2 = float(np.linalg.norm(q2))
    if n1 <= 1e-12 or n2 <= 1e-12:
        return 999.0
    dot = abs(float(np.dot(q1 / n1, q2 / n2)))
    return math.degrees(2.0 * math.acos(max(-1.0, min(1.0, dot))))


def _cam_q_wxyz(cam):
    if not isinstance(cam, dict):
        return None
    if cam.get("q") is not None:
        return _quat_xyzw(cam.get("q"))
    x = _vec3(cam.get("x"))
    y = _vec3(cam.get("y"))
    z = _vec3(cam.get("z"))
    if x is None or y is None or z is None:
        return None
    return _rot_to_quat(x, y, z)


SUAVE_TRAMO_LABEL = {1: "s0", 2: "s03", 3: "s08"}
SUAVE_TRAMO_SMOOTH = {1: 0.0, 2: 0.3, 3: 0.8, 4: 0.3}


def _cum_dt_s(samples):
    """Eje Σdt (vuelta 5, H1): instante final de cada frame acumulado desde dt.

    El filtro del mod integra dt (CONTRACT §16), así que toda medida de lo
    que hace el filtro se fecha en este eje, no en t_ms (otro reloj).
    """
    cum = []
    acc = 0.0
    for s in samples:
        try:
            dt = float(s.get("dt") or 0.0)
        except (TypeError, ValueError):
            dt = 0.0
        if not math.isfinite(dt):
            dt = 0.0
        acc += dt
        cum.append(acc)
    return cum


def _indice_intervalo_carga(samples):
    """Índice de la fila cuyo dt es el intervalo de carga, o None (H2).

    El intervalo de carga es solo el 0→1: el mod pone m_Frame=-1, arma
    (TryArm, creación de cámara) en el mismo OnUpdate del frame 0 y el
    tirón de esa creación y de la primera captura cae en el intervalo que
    acaba en el frame 1. Que las dos primeras filas vistas sean la pareja
    de carga solo queda probado si sus frames son exactamente 0 y 1; una
    corrida que empieza en otro frame no tiene intervalo exento.
    """
    if len(samples) < 2:
        return None
    try:
        if int(samples[0].get("frame")) == 0 and int(samples[1].get("frame")) == 1:
            return 1
    except (TypeError, ValueError):
        return None
    return None


def evaluate_suave_run(run):
    """T-suave numérica sobre samples.jsonl. Devuelve (filas, info) con info para el acuerdo entre regímenes."""
    samples = run["samples"]
    caso = str(run.get("caso") or "")
    regime = "".join(ch for ch in caso if ch.isdigit()) or "60"
    rows = []
    orient_at = {}
    if not samples:
        return rows, {"regime": regime, "orient_at": orient_at, "fps_measured": 0.0}
    # Vuelta 5 (H2): el intervalo de carga (solo el 0→1, ver
    # _indice_intervalo_carga) queda fuera de N/Σdt, igual que en
    # check_runs queda fuera de la deriva. Los demás intervalos cuentan.
    carga_idx = _indice_intervalo_carga(samples)
    dts = [float(s.get("dt") or 0.0) for i, s in enumerate(samples)
           if i != carga_idx and float(s.get("dt") or 0.0) > 0]
    # Vuelta 3 (hallazgos 6 y 7): la cadencia se mide con frames y tiempo
    # transcurrido; la mediana de dt se informa aparte y no certifica el regimen.
    fps_median = round(1.0 / float(np.median(dts)), 3) if dts else 0.0
    # Cadencia = frames / tiempo transcurrido de sus intervalos dt.
    fps_measured = round(len(dts) / sum(dts), 3) if dts else fps_median
    cum_dt = _cum_dt_s(samples)
    fps_cap = None
    for s in samples:
        if s.get("fps_cap") is not None:
            try:
                fps_cap = float(s["fps_cap"])
            except (TypeError, ValueError):
                pass
            break
    try:
        regime_fps = float(regime)
    except ValueError:
        regime_fps = None
    if fps_cap is None:
        fps_cap = regime_fps
    # Coherencia caso/regimen/tope: fps_cap debe ser el regimen del caso y
    # los FPS se miden contra el regimen que se pretende certificar.
    fps_incoherent = (
        fps_cap is not None and regime_fps is not None and abs(fps_cap - regime_fps) > 1e-9
    )
    fps_bad = regime_fps is not None and regime_fps > 0 and abs(fps_measured - regime_fps) / regime_fps > FPS_REGIME_TOL
    continuity_bad = bool(run.get("has_gaps"))

    # Saltos de la lata por tramo: primer frame en que lata.a cambia > JUMP_MIN_M.
    jumps = []  # (indice, magnitud)
    prev_lata = None
    for idx, s in enumerate(samples):
        lata = _vec3(((s.get("lata") or {}).get("a")))
        if lata is not None and prev_lata is not None:
            mag = float(np.linalg.norm(lata - prev_lata))
            if mag > JUMP_MIN_M:
                jumps.append((idx, mag))
        if lata is not None:
            prev_lata = lata

    # Objetivo de posicion atado a lata.a (contrato §16): cam_raw debe seguirla
    # en el mismo frame con el desplazamiento constante de follow.
    follow_offset = None
    for s in samples:
        lata0 = _vec3(((s.get("lata") or {}).get("a")))
        raw0 = _vec3(((s.get("cam_raw") or {}).get("pos")))
        if lata0 is not None and raw0 is not None:
            follow_offset = raw0 - lata0
            break
    desfasada_idx = set()
    for idx, s in enumerate(samples):
        lata_i = _vec3(((s.get("lata") or {}).get("a")))
        raw_i = _vec3(((s.get("cam_raw") or {}).get("pos")))
        if lata_i is not None and raw_i is not None and follow_offset is not None:
            if float(np.linalg.norm(raw_i - (lata_i + follow_offset))) > 0.01:
                desfasada_idx.add(idx)

    # Simulación del filtro con el smooth_s del guion (no el escrito). El estado
    # se conserva entre tramos y el primer frame de cada tramo tambien se
    # comprueba (hallazgo 7); dt es el intervalo que acaba en ese frame (§16).
    sim_pos = {}
    sim_q = {}
    err_pos_frac = {}
    err_deg = {}
    state_pos = None
    state_q = None
    last_jump_mag = 1.0
    jump_idx_set = {i for i, _m in jumps}
    jump_mag_at = {i: m for i, m in jumps}
    for idx, s in enumerate(samples):
        try:
            tramo = int(s.get("tramo") or 1)
        except (TypeError, ValueError):
            tramo = 1
        if idx in jump_idx_set:
            last_jump_mag = jump_mag_at[idx]
        raw = s.get("cam_raw") or {}
        raw_pos = _vec3(raw.get("pos"))
        raw_q = _cam_q_wxyz(raw)
        lata = _vec3(((s.get("lata") or {}).get("a")))
        # Vuelta 4 (hallazgo 1): sin lata.a no se sustituye el objetivo por
        # cam_raw; ese frame no aporta objetivo de posicion (y el grupo que
        # lo juzga quedara INCONCLUSO por lata_ausente).
        target_pos = lata + follow_offset if (lata is not None and follow_offset is not None) else None
        cam = s.get("cam") or {}
        cam_pos = _vec3(cam.get("pos"))
        cam_q = _cam_q_wxyz(cam)
        dt = float(s.get("dt") or (1.0 / 60.0))
        smooth = SUAVE_TRAMO_SMOOTH.get(tramo, 0.3)
        # Con inject=smooth03 el guion escrito es 0,3 en todos los tramos: el esperado sigue siendo el del tramo.
        alpha = 1.0 if smooth == 0.0 else 1.0 - math.exp(-max(dt, 0.0) / smooth)
        if state_pos is None:
            if target_pos is not None:
                state_pos = target_pos.copy()
            if raw_q is not None:
                state_q = raw_q / np.linalg.norm(raw_q)
        elif target_pos is not None:
            state_pos = state_pos + alpha * (target_pos - state_pos)
            if raw_q is not None:
                if state_q is None:
                    state_q = raw_q / np.linalg.norm(raw_q)
                else:
                    state_q = _slerp(state_q, raw_q / np.linalg.norm(raw_q), alpha)
        sim_pos[idx] = None if state_pos is None else state_pos.copy()
        sim_q[idx] = None if state_q is None else state_q.copy()
        if cam_pos is not None and state_pos is not None:
            err_pos_frac[idx] = float(np.linalg.norm(cam_pos - state_pos)) / max(last_jump_mag, 1e-9)
        if cam_q is not None and state_q is not None:
            err_deg[idx] = _quat_angle_deg(cam_q, state_q)

    # Agrupar índices por etiqueta de tramo/giro.
    groups = {}
    for idx, s in enumerate(samples):
        try:
            tramo = int(s.get("tramo") or 1)
        except (TypeError, ValueError):
            tramo = 1
        try:
            giro = int(s.get("giro") or 0)
        except (TypeError, ValueError):
            giro = 0
        if tramo == 4 and giro == 1:
            label = "giro+170"
        elif tramo == 4 and giro == 2:
            label = "giro-170"
        elif tramo == 4:
            # Intervalo previo al primer giro (tramo=4, giro=0): no es un grupo
            # propio, pero su posicion se comprueba dentro de giro+170 (hall. 5).
            groups.setdefault("pre_giro", []).append(idx)
            continue
        else:
            label = SUAVE_TRAMO_LABEL.get(tramo, f"s{tramo}")
        groups.setdefault(label, []).append(idx)
    pre_giro_idxs = groups.pop("pre_giro", [])

    # Hallazgo 8: hacen falta estimulo y los cinco grupos; sin ellos INCONCLUSO, nunca PASA.
    required_labels = ("s0", "s03", "s08", "giro+170", "giro-170")
    ordered_labels = [l for l in required_labels if l in groups] + [l for l in groups if l not in required_labels]
    ordered_labels += [l for l in required_labels if l not in groups]
    for label in ordered_labels:
        idxs = groups.get(label, [])
        is_giro = label.startswith("giro")
        # Error máximo tras los saltos del grupo.
        fracs = [err_pos_frac[i] for i in idxs if i in err_pos_frac]
        degs = [err_deg[i] for i in idxs if i in err_deg]
        err_max_frac = round(max(fracs), 6) if fracs else 999.0
        # Vuelta 3 (hallazgo 1): cada frame evaluado exige cam.pos y el
        # cuaternion escrito cam.q; su ausencia es INCONCLUSO, nunca PASA.
        eval_idxs = list(idxs) + (list(pre_giro_idxs) if label == "giro+170" else [])
        missing_obs = any(
            _vec3((samples[i].get("cam") or {}).get("pos")) is None
            or _quat_raw_xyzw((samples[i].get("cam") or {}).get("q")) is None
            for i in eval_idxs
        ) if eval_idxs else False
        if not is_giro and idxs and len(fracs) != len(idxs):
            missing_obs = True
        if is_giro and idxs and (len(degs) != len(idxs) or any(i not in err_pos_frac for i in eval_idxs)):
            missing_obs = True
        pos_fracs_giro = [err_pos_frac[i] for i in eval_idxs if i in err_pos_frac]
        coverage = round(float(len(fracs if not is_giro else degs)) / float(len(idxs)), 4) if idxs else 0.0
        # Norma del cuaternión escrito.
        norm_dev = 0.0
        path_deg = 0.0
        prev_q = None
        prev_t = None
        orient_1_6 = None
        # Origen explicito del salto (vuelta 5, H1): instante Σdt del frame
        # previo al grupo. Antes se fechaba con t_ms y un tirón real hacía
        # discrepar 1,7° a dos cámaras correctas (falso acuerdo FPS).
        t_start = None
        if idxs:
            for j in range(idxs[0] - 1, -1, -1):
                t_start = cum_dt[j]
                prev_q = _cam_q_wxyz(samples[j].get("cam") or {})
                prev_t = t_start
                break
            if t_start is None:
                try:
                    dt0 = float(samples[idxs[0]].get("dt") or 0.0)
                except (TypeError, ValueError):
                    dt0 = 0.0
                t_start = cum_dt[idxs[0]] - dt0
        for i in idxs:
            s = samples[i]
            raw_q = _quat_raw_xyzw((s.get("cam") or {}).get("q"))
            if raw_q is not None:
                norm_dev = max(norm_dev, abs(float(np.linalg.norm(raw_q)) - 1.0))
            q = _cam_q_wxyz(s.get("cam") or {})
            if q is not None and prev_q is not None:
                path_deg += _quat_angle_deg(prev_q, q)
            t_now = cum_dt[i]
            t_eff = t_now
            if orient_1_6 is None and t_start is not None and t_eff >= (t_start + 1.0 / 6.0) and q is not None:
                if prev_q is not None and prev_t is not None and t_eff > prev_t:
                    # Vuelta 4 (hallazgo 3): interpolacion compatible con la
                    # respuesta exponencial y los dt reales. El angulo que
                    # falta hasta el objetivo (constante en el giro) decae
                    # como exp(-t/smooth_s): su logaritmo se interpola
                    # linealmente entre los dos frames que abrazan t=1/6 s.
                    t_target = t_start + 1.0 / 6.0
                    frac_t = max(0.0, min(1.0, (t_target - prev_t) / (t_eff - prev_t)))
                    target_q = _cam_q_wxyz(s.get("cam_raw") or {})
                    orient_1_6 = None
                    if target_q is not None:
                        tq = target_q / np.linalg.norm(target_q)
                        qp = prev_q / np.linalg.norm(prev_q)
                        qc = q / np.linalg.norm(q)
                        th_prev = _quat_angle_deg(qp, tq)
                        th_curr = _quat_angle_deg(qc, tq)
                        if th_prev > 1e-6 and 1e-9 < th_curr < th_prev:
                            th_star = math.exp(math.log(th_prev) + frac_t * (math.log(th_curr) - math.log(th_prev)))
                            alpha_star = max(0.0, min(1.0, (th_prev - th_star) / th_prev))
                            orient_1_6 = _slerp(qp, tq, alpha_star)
                    if orient_1_6 is None:
                        orient_1_6 = _slerp(prev_q, q / np.linalg.norm(q), frac_t)
                else:
                    orient_1_6 = q
            if q is not None:
                prev_q = q
                prev_t = t_eff
        if orient_1_6 is not None:
            orient_at[label] = orient_1_6
        # Arco: corto si va en el sentido del salto de ±170°; largo si va al contrario o supera 180°.
        signed_yaw = 0.0
        prev_yaw = None
        for i in idxs:
            zax = _vec3((samples[i].get("cam") or {}).get("z"))
            if zax is None:
                continue
            yaw = math.degrees(math.atan2(float(zax[0]), float(zax[2])))
            if prev_yaw is not None:
                signed_yaw += (yaw - prev_yaw + 180.0) % 360.0 - 180.0
            prev_yaw = yaw
        expected_sign = 1.0 if label == "giro+170" else (-1.0 if label == "giro-170" else 0.0)
        arc = "largo" if (path_deg > 180.0 or (expected_sign != 0.0 and signed_yaw * expected_sign < -10.0)) else "corto"
        orient_1_6_deg = None
        if idxs and orient_1_6 is not None:
            # Hallazgo 16: referencia = orientacion anterior al salto, no la primera ya filtrada.
            q0 = None
            for j in range(idxs[0] - 1, -1, -1):
                q0 = _cam_q_wxyz(samples[j].get("cam") or {})
                if q0 is not None:
                    break
            if q0 is None:
                q0 = _cam_q_wxyz(samples[idxs[0]].get("cam") or {})
            orient_1_6_deg = round(_quat_angle_deg(q0, orient_1_6), 4)
        # Estimulo de orientacion observable en el grupo (cam_raw).
        raw_qs = []
        for i in idxs:
            rq = _cam_q_wxyz(samples[i].get("cam_raw") or {})
            if rq is not None:
                raw_qs.append(rq)
        base_raw_q = None
        if idxs:
            for j in range(idxs[0] - 1, -1, -1):
                base_raw_q = _cam_q_wxyz(samples[j].get("cam_raw") or {})
                if base_raw_q is not None:
                    break
        ref_raw_q = base_raw_q if base_raw_q is not None else (raw_qs[0] if raw_qs else None)
        giro_stimulus = bool(raw_qs) and ref_raw_q is not None and max((_quat_angle_deg(ref_raw_q, q) for q in raw_qs), default=0.0) > 10.0
        # Vuelta 3 (hallazgo 4): el guion exige +-170 deg; amplitud, sentido y
        # objetivo se validan antes de juzgar (un giro de 20 deg no certifica).
        stim_amplitude = _quat_angle_deg(ref_raw_q, raw_qs[-1]) if (raw_qs and ref_raw_q is not None) else 0.0
        stim_signed = 0.0
        _prev_yaw = None
        _yaw_seq = []
        if ref_raw_q is not None:
            _yaw_seq.append(ref_raw_q)
        _yaw_seq.extend(raw_qs)
        for _q in _yaw_seq:
            _axes = _quat_to_axes(_q / np.linalg.norm(_q))
            _yaw = math.degrees(math.atan2(float(_axes[2][0]), float(_axes[2][2])))
            if _prev_yaw is not None:
                stim_signed += (_yaw - _prev_yaw + 180.0) % 360.0 - 180.0
            _prev_yaw = _yaw
        expected_sign_pre = 1.0 if label == "giro+170" else (-1.0 if label == "giro-170" else 0.0)
        # Vuelta 4 (hallazgo 4): el objetivo debe ser +-170 deg dentro de
        # GIRO_TARGET_TOL_DEG y constante durante todo el giro.
        target_const_deg = 0.0
        if raw_qs:
            target_const_deg = max(_quat_angle_deg(raw_qs[-1], q) for q in raw_qs)
        stimulus_ok = bool(
            giro_stimulus
            and expected_sign_pre != 0.0
            and abs(stim_amplitude - 170.0) <= GIRO_TARGET_TOL_DEG
            and abs(stim_signed * expected_sign_pre - 170.0) <= GIRO_TARGET_TOL_DEG
            and target_const_deg <= GIRO_TARGET_TOL_DEG
        )
        # Vuelta 4 (hallazgos 1 y 2): lata.a valida en los frames juzgados y,
        # en los giros, observacion/referencia a 1/6 s y guion terminado
        # (el grupo dura al menos 1 s: el contrato lo mantiene 4 s y la
        # fixture 2 s; 4 frames a 60 FPS son 0.07 s).
        lata_missing = any(_vec3(((samples[i].get("lata") or {}).get("a"))) is None for i in eval_idxs) if eval_idxs else False
        giro_incomplete = False
        if is_giro:
            # Duración del grupo sobre Σdt (H1): es tiempo del filtro, no de pared.
            t_last = cum_dt[idxs[-1]] if idxs else 0.0
            giro_incomplete = bool(
                orient_1_6 is None or orient_1_6_deg is None or t_start is None or (t_last - t_start) < 1.0
            )
        if fps_incoherent:
            verdict, cause = "INCONCLUSO", "fps_cap_incoherente"
        elif continuity_bad:
            verdict, cause = "INCONCLUSO", "continuidad_frames"
        elif fps_bad:
            verdict, cause = "INCONCLUSO", "fps_regime"
        elif not idxs:
            verdict, cause = "INCONCLUSO", "grupo_ausente"
        elif missing_obs:
            verdict, cause = "INCONCLUSO", "sin_observaciones_validas"
        elif lata_missing:
            verdict, cause = "INCONCLUSO", "lata_ausente"
        elif giro_incomplete:
            verdict, cause = "INCONCLUSO", "giro_incompleto"
        elif any(i in desfasada_idx for i in idxs):
            # Hallazgo 6 / §16: cam_raw no sigue a lata.a en el mismo frame.
            verdict, cause = "FALLA", "entrada_desfasada"
        elif is_giro:
            if not degs or not giro_stimulus:
                verdict, cause = "INCONCLUSO", "sin_observaciones_validas" if not degs else "sin_estimulo"
            elif not stimulus_ok:
                verdict, cause = "INCONCLUSO", "estimulo_giro_invalido"
            elif norm_dev > QUAT_NORM_TOL:
                verdict, cause = "FALLA", "quat_norm_exceeded"
            elif arc == "largo":
                verdict, cause = "FALLA", "long_arc"
            elif pos_fracs_giro and max(pos_fracs_giro) > THRESH_SUAVE_FRAC:
                # Hallazgo 5: tambien la posicion durante el giro (y su previo).
                verdict, cause = "FALLA", "suave_frac_exceeded"
            elif max(degs) / 170.0 > THRESH_SUAVE_FRAC:
                verdict, cause = "FALLA", "suave_orient_exceeded"
            else:
                verdict, cause = "PASA", ""
            err_max_frac = round(max([d / 170.0 for d in degs] + list(pos_fracs_giro), default=999.0), 6) if degs else 999.0
        else:
            tramo_jumps = [i for i, _m in jumps if i in idxs]
            if not tramo_jumps:
                # Sin salto observado en el tramo no se puede juzgar la respuesta.
                verdict, cause = "INCONCLUSO", "sin_salto"
            elif not fracs:
                verdict, cause = "INCONCLUSO", "sin_observaciones_validas"
            elif err_max_frac <= THRESH_SUAVE_FRAC:
                verdict, cause = "PASA", ""
            else:
                verdict, cause = "FALLA", "suave_frac_exceeded"
        rows.append({
            "run": run["run"], "caso": run["caso"], "hook": run["hook"], "inject": run["inject"],
            "measure": "T-suave", "reading": None, "window": label,
            "p95_px": 999.0, "roll_deg": 999.0, "coverage": coverage,
            "verdict": verdict, "cause": cause,
            "regime": regime, "tramo": label, "err_max_frac": err_max_frac,
            "quat_norm_dev": round(float(norm_dev), 8), "arc": arc,
            "fps_measured": fps_measured, "fps_median": fps_median, "orient_1_6_deg": orient_1_6_deg,
            "n_shots": len(idxs),
        })
    return rows, {"regime": regime, "orient_at": orient_at, "fps_measured": fps_measured, "fps_median": fps_median, "fps_bad": fps_bad or fps_incoherent or continuity_bad}


def _finite_report(obj):
    """Copia con todos los float finitos (hallazgo 15): Infinity/NaN -> 999.0."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else 999.0
    if isinstance(obj, dict):
        return {k: _finite_report(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite_report(v) for v in obj]
    return obj


def evaluate(runs_dir, out_dir=None, marcas_dir=None):
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

    marcas_path = _resolve_marcas_dir(runs_dir, marcas_dir)
    marcas_by_run = {}
    marcas_info = {}
    for run in runs:
        valid, discarded = load_marcas(marcas_path, run["run"], run["dir"])
        marcas_by_run[run["run"]] = valid
        marcas_info[run["run"]] = {"valid": len(valid), "discarded": discarded}

    # Mascaras desde mount0 por hook: una por detalle, en coordenadas locales (hallazgo 1).
    mask_by_hook = {}
    if USE_MASK:
        for run in runs:
            if run["caso"] != "mount0" or run["inject"] != "none":
                continue
            hook_m = run["hook"]
            if hook_m in mask_by_hook:
                continue
            k_m = k_by_hook.get(hook_m)
            masks = build_masks_from_run(run, marcas_by_run.get(run["run"], []), int(k_m) if k_m is not None else 0, fov_by_hook.get(hook_m, "vertical"))
            if masks:
                mask_by_hook[hook_m] = masks
                try:
                    marcas_path.mkdir(parents=True, exist_ok=True)
                    for point, mask in masks.items():
                        if not _mask_valid(mask):
                            continue
                        detail = MASK_DETAIL_FILES.get(point, str(point).replace(" ", "_"))
                        suffix = "" if point == "usti hlavne" else f"_{detail}"
                        Image.fromarray((np.asarray(mask, dtype=bool).astype(np.uint8) * 255), mode="L").save(marcas_path / f"mascara_{run['run']}{suffix}.png")
                except OSError:
                    pass
    # Vuelta 3 (hallazgo 8): la calibracion usa la primera pareja valida de
    # mascaras; un hook descartado (mascaras vacias) no bloquea a los demas.
    first_mask = next(
        (m for m in mask_by_hook.values() if not _mask_empty(m.get("usti hlavne")) and not _mask_empty(m.get("konec hlavne"))),
        next(iter(mask_by_hook.values()), None),
    )

    def _mask_cause(run):
        if not USE_MASK:
            return ""
        masks = mask_by_hook.get(run["hook"])
        if not masks:
            return "mascara_ausente"
        if _mask_empty(masks.get("usti hlavne")) or _mask_empty(masks.get("konec hlavne")):
            return "mascara_vacia"
        return ""

    detector_block = calibrate_detector(runs, k_by_hook, fov_by_hook, template_mask=first_mask, mask_by_hook=mask_by_hook if mask_by_hook else None)
    det_ok = detector_block["verdict"] == "PASA"

    positive_runs = [r for r in runs if r["caso"] != "calib" and r["inject"] == "none"]
    negative_runs = [r for r in runs if r["caso"] != "calib" and r["inject"] != "none"]
    image_positive = [r for r in positive_runs if r["caso"] not in ("ropa",) and not str(r["caso"]).startswith("suave")]
    ropa_positive = [r for r in positive_runs if r["caso"] == "ropa"]
    suave_positive = [r for r in positive_runs if str(r["caso"]).startswith("suave")]

    results = []
    detections_cache = {}

    # 1. Evaluar T-lect/T-marca sobre TODAS las corridas positivas de imagen (hallazgo 5).
    tlect_runs = image_positive
    reading_verdicts = {r: [] for r in READINGS_ORDER}
    tmarca_verdicts = {r: [] for r in READINGS_ORDER}
    tmarca_by_run = {}

    for run in tlect_runs:
        hook = run["hook"]
        calib_ok = (hook in calib_block and calib_block[hook]["verdict"] == "PASA") or (
            hook == "Hc" and calib_block.get("Ha", {}).get("verdict") == "PASA"
        )
        k_val = k_by_hook.get(hook)
        k_use = int(k_val) if k_val is not None else 0
        fov_conv = fov_by_hook.get(hook, "vertical")
        run_marcas = marcas_by_run.get(run["run"], [])
        mask_cause = _mask_cause(run)
        pre_cause = ""
        if TEMPLATE_SOURCE == "marca" and not run_marcas:
            pre_cause = "sin_marcas"
        elif mask_cause:
            pre_cause = mask_cause
        elif not calib_ok:
            pre_cause = "calib_inconcluso"
        elif not det_ok:
            pre_cause = "detector_inconcluso"

        detections = _detect_run_shots(run, k_use, fov_conv, ref_reading="a", marcas=run_marcas, mask=mask_by_hook.get(hook))
        detections_cache[run["run"]] = detections
        windows, has_giro = _windows_for_run(run)
        windows = _require_expected_windows(windows, has_giro)
        turn_names = [w for w in windows if w.startswith("giro")]
        no_turns_cause = "no_turn_windows" if not turn_names and not pre_cause else pre_cause

        for trow in _eval_tmarca_rows(run, run_marcas, k_use, fov_conv):
            # T-marca solo gatea si hay calibración/detector; sin ellos queda como medida informativa INCONCLUSA por esa causa.
            if pre_cause and pre_cause != "sin_marcas" and trow["verdict"] == "PASA":
                trow = dict(trow, verdict="INCONCLUSO", cause=pre_cause)
            results.append(trow)
            tmarca_verdicts[trow["reading"]].append(trow["verdict"])
            tmarca_by_run.setdefault(run["run"], []).append(trow)

        for r in READINGS_ORDER:
            for w_name, w_frames in windows.items():
                p95_px, roll_deg, cov, verdict, cause, n_shots = _eval_window_metrics(
                    run,
                    w_frames,
                    detections,
                    k_use,
                    fov_conv,
                    r,
                    cam_override=None,
                    check_stim=False,
                    base_PreCheck=no_turns_cause,
                    apply_min_shots=has_giro,
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
                        "n_shots": n_shots,
                    }
                )
                reading_verdicts[r].append((hook, verdict))

    winning_reading = None
    for r in READINGS_ORDER:
        by_h = {}
        for h, v in reading_verdicts[r]:
            by_h.setdefault(h, []).append(v)
        # Vuelta 4 (hallazgo 8): la lectura certificada exige T-marca PASA
        # (no basta con que no sea FALLA); un INCONCLUSO la bloquea y llega
        # al codigo de salida via winning_reading=None.
        _tm = tmarca_verdicts.get(r, [])
        marca_ok = bool(_tm) and all(v == "PASA" for v in _tm)
        if marca_ok and any(vs and all(v == "PASA" for v in vs) for vs in by_h.values()):
            winning_reading = r
            break

    eval_reading = winning_reading if winning_reading is not None else "a"

    # 2. Evaluar T-hook sobre todas las corridas positivas de imagen
    thook_by_mode_hook = {}
    for run in image_positive:
        hook = run["hook"]
        calib_ok = (hook in calib_block and calib_block[hook]["verdict"] == "PASA") or (
            hook == "Hc" and calib_block.get("Ha", {}).get("verdict") == "PASA"
        )
        k_val = k_by_hook.get(hook)
        k_use = int(k_val) if k_val is not None else 0
        fov_conv = fov_by_hook.get(hook, "vertical")
        run_marcas = marcas_by_run.get(run["run"], [])
        mask_cause = _mask_cause(run)
        pre_cause = ""
        if TEMPLATE_SOURCE == "marca" and not run_marcas:
            pre_cause = "sin_marcas"
        elif mask_cause:
            pre_cause = mask_cause
        elif not calib_ok:
            pre_cause = "calib_inconcluso"
        elif not det_ok:
            pre_cause = "detector_inconcluso"
        elif winning_reading is None:
            pre_cause = "t_lect_inconcluso"

        if run["run"] not in detections_cache:
            detections_cache[run["run"]] = _detect_run_shots(run, k_use, fov_conv, ref_reading=eval_reading, marcas=run_marcas, mask=mask_by_hook.get(hook))
        detections = detections_cache[run["run"]]

        windows, has_giro = _windows_for_run(run)
        windows = _require_expected_windows(windows, has_giro)
        turn_names = [w for w in windows if w.startswith("giro")]
        no_turns_cause = "no_turn_windows" if not turn_names and not pre_cause else pre_cause
        ideal_cams = build_ideal_mode_cameras(run["samples"], eval_reading)

        w_verdicts = []
        for w_name, w_frames in windows.items():
            p95_px, roll_deg, cov, verdict, cause, n_shots = _eval_window_metrics(
                run,
                w_frames,
                detections,
                k_use,
                fov_conv,
                eval_reading,
                cam_override=ideal_cams,
                check_stim=w_name.startswith("giro"),
                base_PreCheck=no_turns_cause,
                apply_min_shots=has_giro,
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
                    "n_shots": n_shots,
                }
            )
            w_verdicts.append(verdict)
        thook_by_mode_hook[(run["caso"], hook)] = w_verdicts

    hook_por_modo = {}
    for mode in MODES_ORDER:
        winner = None
        for h in HOOKS_ORDER:
            vs = thook_by_mode_hook.get((mode, h))
            if not (vs and all(v == "PASA" for v in vs)):
                continue
            # Hallazgo 5: el caso con marcas se comprueba contra sus marcas y eso
            # condiciona la decision de hook (T-marca de la lectura evaluada).
            run_name = next((r["run"] for r in image_positive if r["caso"] == mode and r["hook"] == h), None)
            marca_rows = [t for t in tmarca_by_run.get(run_name, []) if t["reading"] == eval_reading]
            if marca_rows and not all(t["verdict"] == "PASA" for t in marca_rows):
                continue
            winner = h
            break
        hook_por_modo[mode] = winner

    # 2b. T-ropa
    ropa_decisions = {"mochila": None, "mira": None, "silenciador": None}
    for run in ropa_positive:
        hook_r = run["hook"]
        # Hallazgo 10: sin calibracion valida no se sustituye por k=0 ni focal vertical.
        calib_r = calib_block.get(hook_r) or (calib_block.get("Ha") if hook_r == "Hc" else None)
        calib_ok_r = bool(calib_r and calib_r.get("verdict") == "PASA" and calib_r.get("k") is not None and calib_r.get("f_px"))
        k_val = k_by_hook.get(hook_r)
        k_use = int(k_val) if (calib_ok_r and k_val is not None) else 0
        fov_conv = fov_by_hook.get(hook_r, "vertical") if calib_ok_r else "vertical"
        rrows, rdec = evaluate_ropa_run(run, marcas_by_run.get(run["run"], []), k_use, fov_conv, calib_ok=calib_ok_r)
        results.extend(rrows)
        ropa_decisions.update(rdec)
        # La proyección del punto mira también va como T-marca de esa corrida.
        tmarca_ropa = _eval_tmarca_rows(run, marcas_by_run.get(run["run"], []), k_use, fov_conv)
        if not calib_ok_r:
            tmarca_ropa = [dict(t, verdict="INCONCLUSO", cause="calib_inconcluso") for t in tmarca_ropa]
        results.extend(tmarca_ropa)

    # 2c. T-suave positiva y acuerdo entre regímenes en t=1/6 s.
    # Hallazgo 15: regimen ausente -> "INCONCLUSO" con causa, nunca null fuera del enum.
    suave_decisions = {"30": "INCONCLUSO", "60": "INCONCLUSO", "144": "INCONCLUSO"}
    suave_causas = {"30": "regimen_ausente", "60": "regimen_ausente", "144": "regimen_ausente"}
    suave_infos = []
    suave_rows_by_run = {}
    for run in suave_positive:
        srows, sinfo = evaluate_suave_run(run)
        suave_rows_by_run[run["run"]] = srows
        suave_infos.append((run, sinfo))
    # Acuerdo entre regímenes: orientación en t=1/6 s por etiqueta de giro.
    # Hallazgo 14: solo regimenes validos (los INCONCLUSO por fps_regime no entran).
    by_label = {}
    for run, sinfo in suave_infos:
        srows = suave_rows_by_run[run["run"]]
        if sinfo.get("fps_bad") or any(r["cause"] == "fps_regime" for r in srows):
            continue
        # Vuelta 3 (hallazgo 3): al acuerdo solo entran giros con estimulo,
        # observaciones y referencia temporal validos (fila no INCONCLUSA).
        row_by_label = {r["tramo"]: r for r in srows}
        for label, q in sinfo["orient_at"].items():
            if not str(label).startswith("giro"):
                continue
            srow = row_by_label.get(label)
            if srow is None or srow["verdict"] == "INCONCLUSO" or srow.get("orient_1_6_deg") is None:
                continue
            by_label.setdefault(label, []).append((run, sinfo["regime"], q))
    disagree_runs = set()
    for label, entries in by_label.items():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if _quat_angle_deg(entries[i][2], entries[j][2]) > SUAVE_FPS_AGREE_DEG:
                    disagree_runs.add(entries[i][0]["run"])
                    disagree_runs.add(entries[j][0]["run"])
    # Vuelta 5b (B2): el acuerdo no puede quedar satisfecho porque falte
    # una comparación. Entre los regímenes cualificados para el acuerdo
    # (fps válido, hallazgo 14, y con estímulo de giro válido por
    # etiqueta, hallazgo 3), si la orientación a 1/6 s de alguno no entra
    # en by_label por otra causa (fila INCONCLUSA o ausente), el acuerdo
    # queda pendiente y ningún régimen que dependa de él se certifica
    # PASA: sus filas de giro PASA pasan a INCONCLUSO con esta causa. Un
    # régimen FALLA sigue aportando su orientación y no deja el acuerdo
    # pendiente por sí solo; un régimen descalificado por fps o por
    # estímulo no es una referencia que el acuerdo necesite.
    acuerdo_pendiente = False
    cualificados = []
    for _run, _sinfo in suave_infos:
        _srows = suave_rows_by_run[_run["run"]]
        if _sinfo.get("fps_bad") or any(r["cause"] == "fps_regime" for r in _srows):
            continue
        cualificados.append((_run, _sinfo, _srows))
    if len(cualificados) >= 2:
        for label in ("giro+170", "giro-170"):
            esperados = set()
            for _run, _sinfo, _srows in cualificados:
                _row = next((r for r in _srows if r.get("tramo") == label), None)
                if _row is not None and _row.get("cause") in ("sin_estimulo", "estimulo_giro_invalido"):
                    continue
                esperados.add(_sinfo["regime"])
            presentes = {regime for _run, regime, _q in by_label.get(label, [])}
            if esperados - presentes:
                acuerdo_pendiente = True
    # Vuelta 5c (N1): un desacuerdo ya demostrado entre dos regímenes
    # tiene prioridad sobre el estado pendiente: la falta de una tercera
    # comparación no borra ese FALLA. Solo los regímenes sin desacuerdo
    # demostrado pasan a INCONCLUSO por acuerdo pendiente; el régimen
    # incompleto conserva su propia causa INCONCLUSA.
    if acuerdo_pendiente:
        for run_name, srows in suave_rows_by_run.items():
            if run_name in disagree_runs:
                continue
            if srows and all(r["verdict"] == "PASA" for r in srows):
                for row in srows:
                    if str(row.get("tramo", "")).startswith("giro") and row["verdict"] == "PASA":
                        row["verdict"] = "INCONCLUSO"
                        row["cause"] = "suave_fps_agree_pendiente"
    for run, sinfo in suave_infos:
        srows = suave_rows_by_run[run["run"]]
        if run["run"] in disagree_runs:
            for row in srows:
                if str(row.get("tramo", "")).startswith("giro") and row["verdict"] == "PASA":
                    row["verdict"] = "FALLA"
                    row["cause"] = "suave_fps_agree_exceeded"
        results.extend(srows)
        verdicts = [r["verdict"] for r in srows]
        regime = sinfo["regime"]
        if verdicts and all(v == "PASA" for v in verdicts):
            suave_decisions[regime] = "PASA"
            suave_causas[regime] = ""
        elif any(v == "FALLA" for v in verdicts):
            suave_decisions[regime] = "FALLA"
            suave_causas[regime] = next((r["cause"] for r in srows if r["verdict"] == "FALLA"), "")
        elif verdicts:
            suave_decisions[regime] = "INCONCLUSO"
            suave_causas[regime] = next((r["cause"] for r in srows if r["verdict"] == "INCONCLUSO"), "inconcluso")

    # 3. Evaluar corridas negativas (inject != none): van solo a `negativas`
    negativas = []
    for run in negative_runs:
        hook = run["hook"]
        k_val = k_by_hook.get(hook)
        k_use = int(k_val) if k_val is not None else 0
        fov_conv = fov_by_hook.get(hook, "vertical")
        if str(run["caso"]).startswith("suave"):
            srows, _sinfo = evaluate_suave_run(run)
            neg_verdicts = [r["verdict"] for r in srows]
        else:
            detections = _detect_run_shots(run, k_use, fov_conv, ref_reading=eval_reading, marcas=marcas_by_run.get(run["run"], []), mask=mask_by_hook.get(hook))
            windows, has_giro = _windows_for_run(run)
            ideal_cams = build_ideal_mode_cameras(run["samples"], eval_reading)
            neg_verdicts = []
            for w_name, w_frames in windows.items():
                _, _, _, verdict, _, _n = _eval_window_metrics(
                    run,
                    w_frames,
                    detections,
                    k_use,
                    fov_conv,
                    eval_reading,
                    cam_override=ideal_cams,
                    check_stim=w_name.startswith("giro"),
                    base_PreCheck="",
                    apply_min_shots=has_giro,
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
    suave_rows_all = [r for r in results if r["measure"] == "T-suave"]
    ropa_rows_all = [r for r in results if r["measure"] == "T-ropa"]
    if any(r["verdict"] == "FALLA" for r in thook_rows + suave_rows_all + ropa_rows_all):
        exit_code = 1
    elif image_positive and (
        not calib_block
        or any(c["verdict"] != "PASA" for c in calib_block.values())
        or not det_ok
        or winning_reading is None
        or not thook_rows
        or any(r["verdict"] == "INCONCLUSO" for r in thook_rows)
    ):
        exit_code = 2
    elif any(r["verdict"] == "INCONCLUSO" for r in suave_rows_all + ropa_rows_all):
        exit_code = 2
    elif not results:
        exit_code = 2
    else:
        exit_code = 0

    report = {
        "schema": 2,
        "calib": calib_block,
        "detector": detector_block,
        "results": results,
        "decisions": {
            "lectura": winning_reading,
            "hook_por_modo": hook_por_modo,
            "k": {h: calib_block[h]["k"] for h in calib_block},
            "ropa": ropa_decisions,
            "suave": suave_decisions,
            "suave_causas": suave_causas,
        },
        "negativas": negativas,
        "marcas": marcas_info,
        "exit_code": exit_code,
    }
    # Hallazgo 15: valores finitos siempre; la serializacion no admite NaN/Infinity.
    report = _finite_report(report)

    if out_dir is not None:
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "informe.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        (out_path / "informe.md").write_text(_render_markdown(report), encoding="utf-8")

    return report


def _render_markdown(report):
    verdict_str = {0: "PASA", 1: "FALLA", 2: "INCONCLUSO"}.get(report["exit_code"], "INCONCLUSO")
    lines = [
        f"# Informe S-track·2 — {verdict_str} (exit_code={report['exit_code']})",
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
            f"- **T-ropa:** `{json.dumps(report['decisions'].get('ropa'))}`",
            f"- **T-suave:** `{json.dumps(report['decisions'].get('suave'))}`",
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
    parser = argparse.ArgumentParser(description="Evaluador de la sonda S-track·2")
    parser.add_argument("runs_dir", help="Carpeta con las subcarpetas de corridas")
    parser.add_argument("--out", required=True, help="Carpeta de salida para informe.json e informe.md")
    parser.add_argument("--marcas", default=None, help="Carpeta de marcas (por defecto, <carpeta del script>/marcas o <runs>/marcas)")
    args = parser.parse_args(argv)
    report = evaluate(args.runs_dir, args.out, marcas_dir=args.marcas)
    return int(report["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
