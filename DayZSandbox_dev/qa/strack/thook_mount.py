#!/usr/bin/env python3
"""T-hook de `mount` por medida directa en imagen (árbitro del coordinador, 26-nov; contrato §34).

Con la cámara montada rígida sobre el arma, el arma solo se mueve en la imagen si la pose de la cámara y la que se
dibuja no casan: ese desplazamiento ES la deriva de T-hook, sin plantilla ni máscara.

Por captura de giro: desplazamiento por correlación de fase (subpíxel) de dos cultivos fijos sobre el arma respecto a la
captura de referencia (la primera estable): uno en la recámara (proyección de `konec hlavne`) y otro a lo largo del cañón,
a ≥ SEPARACION_PX de la recámara. Cada cultivo se normaliza (media 0, varianza 1), lo que no mueve píxeles y quita el
cambio de brillo del sol al girar. Deriva = p95 del mayor de los dos desplazamientos; roll = p95 del ángulo entre el
segmento de referencia y el desplazado. PASA si deriva ≤ THRESH_PX y roll ≤ THRESH_ROLL_DEG (umbrales del plan §4.2).

Uso: python thook_mount.py <run_dir> --k <k> --f <f_px> [--json salida.json]
Solo numpy, Pillow y stdlib.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

THRESH_PX = 2.0
THRESH_ROLL_DEG = 0.5
MIN_SHOTS_WINDOW = 20
CROP_PX = 48
SEPARACION_PX = 200.0
CALIDAD_MIN = 0.5  # pico de NCC
BUSQUEDA_PX = 120  # en mount0_Ha el arma se desplaza ~+80, +53 px (f000812 frente a f000030)
ESCALAS = (1.0, 0.8, 0.85, 0.9, 0.95, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3)  # en mount0_Ha el arma sale ~20 % mas grande
ESCALA_MEJORA_MIN = 0.05
RIGIDEZ_ESCALA_TOL = 0.05  # un paso de ESCALAS
ESTABLE_FRAME = 30
IMAGE_W, IMAGE_H = 1920, 1080
# Punto blanco fijo de la HUD en el centro exacto de la imagen (visto en mount0_Hb f000030 y f001382): un cultivo que lo
# contenga da desplazamiento ~0 aunque el arma se mueva, porque la correlacion de fase se engancha a ese borde fijo.
HUD_PUNTO = (IMAGE_W / 2.0, IMAGE_H / 2.0)
HUD_MARGEN_PX = 4.0


def _gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float64)


def _crop(img, cu, cv, size=None):
    size = size or CROP_PX
    h = size // 2
    x0, y0 = int(round(cu)) - h, int(round(cv)) - h
    if x0 < 0 or y0 < 0 or x0 + size > img.shape[1] or y0 + size > img.shape[0]:
        return None
    return img[y0:y0 + size, x0:x0 + size]


def _crop_pad(img, cu, cv, size):
    """Ventana de busqueda; lo que cae fuera de la imagen se rellena con una constante (varianza 0: NCC 0 ahi)."""
    h = size // 2
    x0, y0 = int(round(cu)) - h, int(round(cv)) - h
    out = np.full((size, size), float(img.mean()))
    ys, xs = max(0, y0), max(0, x0)
    ye, xe = min(img.shape[0], y0 + size), min(img.shape[1], x0 + size)
    if ye > ys and xe > xs:
        out[ys - y0:ye - y0, xs - x0:xe - x0] = img[ys:ye, xs:xe]
    return out


def _norm(c):
    if c is None:
        return None
    sd = float(c.std())
    if sd < 1e-6:
        return None
    return (c - float(c.mean())) / sd


def _subpixel(cc, y, x):
    def par(a, b, c):
        den = a - 2.0 * b + c
        return 0.0 if abs(den) < 1e-12 else 0.5 * (a - c) / den
    hh, ww = cc.shape
    dy = par(cc[(y - 1) % hh, x], cc[y, x], cc[(y + 1) % hh, x])
    dx = par(cc[y, (x - 1) % ww], cc[y, x], cc[y, (x + 1) % ww])
    return y + dy, x + dx


def phase_shift(ref, cur):
    """Desplazamiento (dx, dy) que lleva `ref` a `cur`, y la calidad del pico (0-1). Cultivos ya normalizados."""
    win = np.outer(np.hanning(ref.shape[0]), np.hanning(ref.shape[1]))
    f0 = np.fft.fft2(ref * win)
    f1 = np.fft.fft2(cur * win)
    r = np.conj(f0) * f1
    r /= np.abs(r) + 1e-12
    cc = np.real(np.fft.ifft2(r))
    y, x = np.unravel_index(int(cc.argmax()), cc.shape)
    q = float(cc[y, x])
    ys, xs = _subpixel(cc, y, x)
    hh, ww = cc.shape
    if ys > hh / 2:
        ys -= hh
    if xs > ww / 2:
        xs -= ww
    return float(xs), float(ys), q


def _p95(vals):
    if not vals:
        return float("inf")
    s = sorted(vals)
    return float(s[max(0, int(math.ceil(0.95 * len(s))) - 1)])


def _project(p, cam, f):
    pos, ax, ay, az = (np.asarray(cam[k], dtype=np.float64) for k in ("pos", "x", "y", "z"))
    v = np.asarray(p, dtype=np.float64) - pos
    zc = float(v @ az)
    if zc <= 1e-6:
        return None
    return (IMAGE_W / 2 + f * float(v @ ax) / zc, IMAGE_H / 2 - f * float(v @ ay) / zc)


def _rows(run_dir):
    rows, seen = [], set()
    for line in open(Path(run_dir) / "samples.jsonl", encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r["frame"] in seen:
            continue
        seen.add(r["frame"])
        rows.append(r)
    rows.sort(key=lambda r: r["frame"])
    return rows


def _png(run_dir, shot):
    p = Path(run_dir) / Path(shot).with_suffix(".png").name
    return p if p.exists() else (Path(run_dir) / shot)


def crop_centers(rows, k, f):
    """Recámara = proyección de konec (lectura a) en la captura de referencia; segundo punto a lo largo del cañón."""
    by = {r["frame"]: r for r in rows}
    ref = next((r for r in rows if r.get("shot") and int(r.get("giro") or 0) == 0 and r["frame"] >= ESTABLE_FRAME), None)
    if ref is None:
        return None, None
    tgt = by.get(ref["frame"] + k)
    if tgt is None:
        return None, None
    lect = tgt.get("lecturas") or {}
    pk = _project((lect.get("konec hlavne") or {}).get("a"), tgt["cam"], f)
    pu = _project((lect.get("usti hlavne") or {}).get("a"), tgt["cam"], f)
    if pk is None or pu is None:
        return ref, None
    d = math.hypot(pu[0] - pk[0], pu[1] - pk[1])
    if d < 1e-6:
        return ref, None
    # Sentido recamara -> receptor (opuesto a la boca): en mount el cañon hacia la boca es fino y casi todo fondo, que
    # se desplaza al girar; el receptor ocupa mas imagen. El cultivo 1 se aleja de la boca hasta no contener el punto
    # fijo de la HUD (centro exacto de la pantalla, que no se mueve con el arma).
    ux, uy = (pk[0] - pu[0]) / d, (pk[1] - pu[1]) / d
    c1 = pk
    step = 0
    while _toca_hud(c1) and step < 50:
        step += 1
        c1 = (pk[0] + ux * 4.0 * step, pk[1] + uy * 4.0 * step)
    p2 = (c1[0] + ux * SEPARACION_PX, c1[1] + uy * SEPARACION_PX)
    return ref, (c1, p2, SEPARACION_PX)


def _toca_hud(c, size=None):
    """True si el cultivo centrado en c contiene el punto fijo de la HUD (con margen)."""
    h = (size or CROP_PX) / 2.0 + HUD_MARGEN_PX
    return abs(c[0] - HUD_PUNTO[0]) <= h and abs(c[1] - HUD_PUNTO[1]) <= h


def _ncc_map(tpl, win):
    """Mapa de NCC del cultivo normalizado `tpl` (s x s, media 0, var 1) sobre `win` (posiciones validas), por FFT."""
    s = tpl.shape[0]
    H, W = win.shape
    n = float(s * s)
    F = np.fft.rfft2(win)
    T = np.fft.rfft2(tpl[::-1, ::-1], s=win.shape)
    full = np.fft.irfft2(F * T, s=win.shape)
    num = full[s - 1:H, s - 1:W]
    ii = np.pad(win, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    i2 = np.pad(win * win, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    sm = ii[s:, s:] - ii[:-s, s:] - ii[s:, :-s] + ii[:-s, :-s]
    sq = i2[s:, s:] - i2[:-s, s:] - i2[s:, :-s] + i2[:-s, :-s]
    var = np.maximum(sq / n - (sm / n) ** 2, 0.0)
    sd = np.sqrt(var)
    return num / (n * np.where(sd < 1e-6, np.inf, sd))


def ncc_search(tpl, img, cu, cv, radius=None, escalas=None):
    """Busca el cultivo `tpl` (normalizado) en ±radius px alrededor de (cu, cv) en `img` y en las escalas dadas (el arma
    puede salir mas cerca o mas lejos si la pose de la camara no casa con la dibujada). Devuelve (dx, dy, pico NCC,
    escala), con dx, dy en px de la imagen; None si la ventana sale de la imagen."""
    radius = BUSQUEDA_PX if radius is None else radius
    escalas = ESCALAS if escalas is None else escalas
    s = tpl.shape[0]
    wr = s + 2 * radius
    best = None
    for e in escalas:
        wo = int(round(wr * e))
        win = _crop_pad(img, cu, cv, wo)
        if wo != wr:
            win = np.asarray(Image.fromarray(win.astype(np.float32), mode="F").resize((wr, wr), Image.BILINEAR),
                             dtype=np.float64)
        m = _ncc_map(tpl, win)
        y, x = np.unravel_index(int(m.argmax()), m.shape)
        q = float(m[y, x])
        # la escala 1 se prefiere salvo mejora clara (evita escalas espurias en derivas pequeñas)
        cand = ((x - radius) * e, (y - radius) * e, q, e)
        if best is None or (q > best[2] + (ESCALA_MEJORA_MIN if best[3] == 1.0 else 0.0)):
            best = cand
    return best


def _medir_cultivo(ref_n, img, c):
    """Desplazamiento del cultivo: NCC coloca (entero, en ±BUSQUEDA_PX y en ESCALAS) y, si gana la escala 1, la
    correlacion de fase afina el subpixel en el sitio colocado. Calidad = pico de NCC. None si sale de la imagen."""
    s = ncc_search(ref_n, img, *c)
    if s is None:
        return None
    ix, iy, q, e = s
    if e != 1.0:
        return ix, iy, q, e
    cur = _norm(_crop(img, c[0] + ix, c[1] + iy))
    if cur is None:
        return None
    fx, fy, _ = phase_shift(ref_n, cur)
    if abs(fx) > 1.5 or abs(fy) > 1.5:  # la fase no casa con la colocacion: se queda la entera
        fx, fy = 0.0, 0.0
    return ix + fx, iy + fy, q, e


def es_rigido(c1, c2, m1, m2):
    """Los dos cultivos son del mismo arma rigida: misma escala elegida por los dos y la longitud del segmento desplazado
    casa con esa escala. Un emparejamiento espurio en uno solo de los cultivos (texturas repetidas) rompe esto."""
    e1, e2 = m1[3], m2[3]
    if abs(e1 - e2) > RIGIDEZ_ESCALA_TOL + 1e-9:
        return False
    l0 = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
    l1 = math.hypot((c2[0] + m2[0]) - (c1[0] + m1[0]), (c2[1] + m2[1]) - (c1[1] + m1[1]))
    return abs(l1 / l0 - (e1 + e2) / 2.0) <= RIGIDEZ_ESCALA_TOL + 1e-9


def measure_images(ref_img, imgs, c1, c2):
    """Deriva y roll por imagen respecto a la referencia. Devuelve lista de (deriva_px, roll_deg, calidad_min)."""
    r1, r2 = _norm(_crop(ref_img, *c1)), _norm(_crop(ref_img, *c2))
    if r1 is None or r2 is None:
        return None
    base = math.atan2(c2[1] - c1[1], c2[0] - c1[0])
    out = []
    for img in imgs:
        m1, m2 = _medir_cultivo(r1, img, c1), _medir_cultivo(r2, img, c2)
        if m1 is None or m2 is None:
            out.append(None)
            continue
        dx1, dy1, q1, _ = m1
        dx2, dy2, q2, _ = m2
        rigido = es_rigido(c1, c2, m1, m2)
        ang = math.atan2((c2[1] + dy2) - (c1[1] + dy1), (c2[0] + dx2) - (c1[0] + dx1))
        roll = abs((math.degrees(ang - base) + 180.0) % 360.0 - 180.0)
        out.append((max(math.hypot(dx1, dy1), math.hypot(dx2, dy2)), roll, min(q1, q2), rigido))
    return out


def verdict(meas):
    calidad = [m for m in meas if m is not None and m[2] >= CALIDAD_MIN]
    good = [m for m in calidad if m[3]]
    res = {"n_shots": len(meas), "n_validas": len(good), "n_no_rigidas": len(calidad) - len(good)}
    if len(good) < MIN_SHOTS_WINDOW:
        if len(meas) < MIN_SHOTS_WINDOW:
            causa = "insufficient_sampling"
        elif len(calidad) >= MIN_SHOTS_WINDOW:
            causa = "cultivos_no_rigidos"
        else:
            causa = "correlacion_debil"
        res.update(verdict="INCONCLUSO", cause=causa)
        return res
    res["coverage"] = round(len(good) / max(1, len(meas)), 4)
    res["p95_px"] = round(_p95([m[0] for m in good]), 4)
    res["roll_deg"] = round(_p95([m[1] for m in good]), 4)
    if res["p95_px"] > THRESH_PX:
        res.update(verdict="FALLA", cause="p95_px_exceeded")
    elif res["roll_deg"] > THRESH_ROLL_DEG:
        res.update(verdict="FALLA", cause="roll_exceeded")
    elif res["coverage"] < 0.95:
        res.update(verdict="INCONCLUSO", cause="low_coverage")
    else:
        res.update(verdict="PASA", cause="")
    return res


def evaluate_run(run_dir, k, f):
    rows = _rows(run_dir)
    ref, centers = crop_centers(rows, k, f)
    out = {"run": Path(run_dir).name, "measure": "T-hook-mount", "k": k, "f_px": f}
    if ref is None or centers is None:
        out.update(verdict="INCONCLUSO", cause="sin_referencia")
        return out
    c1, c2, sep = centers
    out.update(ref_shot=ref["shot"], recamara=[round(c1[0], 2), round(c1[1], 2)], segundo=[round(c2[0], 2), round(c2[1], 2)],
               separacion_px=round(min(sep, SEPARACION_PX) if sep >= SEPARACION_PX else sep, 1))
    if sep < SEPARACION_PX:
        out["aviso"] = f"boca y recamara a {sep:.0f} px (< {SEPARACION_PX:.0f}): segundo cultivo en la boca"
    ref_img = _gray(_png(run_dir, ref["shot"]))
    windows = {}
    for r in rows:
        g = int(r.get("giro") or 0)
        if g > 0 and r.get("shot"):
            windows.setdefault(f"giro{g}", []).append(r)
        elif g == 0 and r.get("shot") and r["frame"] > ref["frame"]:
            # tanda r6 (26-nov): temblor sin giro (quieto y andando). Con suavizado, en los giros entra ademas el
            # retraso del filtro; esta ventana separa el temblor, que es lo que el suavizado debe quitar.
            windows.setdefault("sin_giro", []).append(r)
    out["windows"] = {}
    for w, wrows in sorted(windows.items()):
        imgs = [_gray(_png(run_dir, r["shot"])) for r in wrows]
        meas = measure_images(ref_img, imgs, c1, c2)
        out["windows"][w] = verdict(meas) if meas is not None else {"verdict": "INCONCLUSO", "cause": "cultivo_fuera_o_sin_textura"}
    vs = [w["verdict"] for w in out["windows"].values()]
    out["verdict"] = "FALLA" if "FALLA" in vs else ("INCONCLUSO" if (not vs or "INCONCLUSO" in vs) else "PASA")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("--k", type=int, required=True)
    ap.add_argument("--f", type=float, required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    res = evaluate_run(a.run_dir, a.k, a.f)
    txt = json.dumps(res, indent=1, ensure_ascii=False)
    if a.json:
        Path(a.json).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
