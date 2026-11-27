#!/usr/bin/env python3
"""T-lect de lookat/follow por medida directa de la boca en imagen (árbitro el coordinador, 26-nov 15:39Z; contrato §35).

En lookat/follow la cámara mira a la boca: el arma gira en la imagen y el fondo se desplaza, así que una máscara por
varianza temporal no sirve. Aquí, por cada captura de giro:
- La lectura (a) SOLO fija el ángulo y la escala de la plantilla: el ángulo 2D de boca a recámara proyectadas y la escala
  f/z de la boca. La captura se gira y escala alrededor de la proyección de (a) para llevarla a la geometría de la
  plantilla.
- La posición se busca por NCC enmascarada en una ventana de ±BUSQUEDA_PX, sin ninguna preferencia por el centro.
  La máscara es una franja sobre el cañón (radio del apagallamas a la escala de la plantilla), así que el fondo no cuenta.
- La plantilla sale de la primera captura estable, recortada en la proyección de (a): ese es el hueco del sesgo ya
  declarado (T-sesgo, §17).
- El punto fijo de la HUD (centro exacto de la pantalla) se borra de cada imagen antes de medir (relleno con la mediana
  de un anillo): la boca cae justo ahí y el punto no se mueve con el arma.
- Deriva de cada lectura = posición detectada − proyección de esa lectura. Veredicto por ventana y lectura con los
  umbrales del evaluador (p95 ≤ THRESH_PX, cobertura ≥ COVERAGE_MIN, ≥ MIN_SHOTS_WINDOW capturas).

Uso: python tlect_direct.py <run_dir> --k <k> --f <f_px> [--json salida.json]
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
COVERAGE_MIN = 0.95
MIN_SHOTS_WINDOW = 20
ESTABLE_FRAME = 30
IMAGE_W, IMAGE_H = 1920, 1080
TPL_PX = 64
BUSQUEDA_PX = 40
CALIDAD_MIN = 0.5
RADIO_BOCA_M = 0.012     # radio exterior del apagallamas (M4A1 p3d ~11 mm) + margen
LARGO_FRANJA_M = 0.12    # tramo de cañon desde la boca que entra en la mascara
FRENTE_M = 0.012         # tramo por delante de la punta
ANG_BUSQUEDA_DEG = (0, -1, 1, -2, 2, -3, 3, -4, 4)
VISTA_MAX_DEG = 10.0     # plantilla del banco solo si su vista 3D del cañon esta a <= 10 grados de la juzgada
BANCO_PASO = 3           # una plantilla cada 3 capturas de giro
AMBIG_RADIO_PX = 4       # segundo pico fuera de este radio (px de plantilla)
AMBIG_MIN = 0.03         # margen minimo de NCC entre el primer y el segundo pico (sinteticas: peor caso bueno 0,044;
                         # dos cañones identicos 0,021)
HUD_PUNTO = (IMAGE_W / 2.0, IMAGE_H / 2.0)
HUD_RADIO = 4            # el punto ocupa ~3x3 px; se borra un disco de este radio
PUNTOS = ("usti hlavne", "konec hlavne")


# ---------- geometria ----------

def project(p, cam, f):
    pos, ax, ay, az = (np.asarray(cam[k], dtype=np.float64) for k in ("pos", "x", "y", "z"))
    v = np.asarray(p, dtype=np.float64) - pos
    zc = float(v @ az)
    if zc <= 1e-6:
        return None
    return (IMAGE_W / 2 + f * float(v @ ax) / zc, IMAGE_H / 2 - f * float(v @ ay) / zc, zc)


def geometria(row, f, lectura="a"):
    """(pu, angulo_rad, px_por_m) de la boca segun una lectura; None si falta."""
    lect = row.get("lecturas") or {}
    u = (lect.get("usti hlavne") or {}).get(lectura)
    k = (lect.get("konec hlavne") or {}).get(lectura)
    if u is None or k is None or not row.get("cam"):
        return None
    pu, pk = project(u, row["cam"], f), project(k, row["cam"], f)
    if pu is None or pk is None:
        return None
    ang = math.atan2(pk[1] - pu[1], pk[0] - pu[0])
    return (pu[0], pu[1]), ang, f / pu[2]


# ---------- imagen ----------

def borrar_hud(img, centro=HUD_PUNTO, r=HUD_RADIO):
    """Rellena el disco del punto fijo de la HUD con la mediana de un anillo alrededor."""
    out = img.copy()
    cx, cy = int(round(centro[0])), int(round(centro[1]))
    y0, y1, x0, x1 = cy - 3 * r, cy + 3 * r + 1, cx - 3 * r, cx + 3 * r + 1
    if y0 < 0 or x0 < 0 or y1 > img.shape[0] or x1 > img.shape[1]:
        return out
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.hypot(yy - cy, xx - cx)
    anillo = img[y0:y1, x0:x1][(d > 2 * r) & (d <= 3 * r)]
    sub = out[y0:y1, x0:x1]
    sub[d <= r] = float(np.median(anillo))
    return out


def _gray(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float64)


def ventana_warp(img, centro, ang, escala, size):
    """Ventana `size`x`size` en coordenadas de la plantilla: punto (u, v) de la ventana -> imagen en
    centro + escala * R(ang) * ((u, v) - c). Bilineal; fuera de la imagen, la media."""
    c = (size - 1) / 2.0
    ca, sa = math.cos(ang) * escala, math.sin(ang) * escala
    a, b, d, e = ca, -sa, sa, ca
    # PIL pone el centro del pixel i en i + 0,5 (en entrada y en salida); aqui el centro del pixel i es i
    cc = centro[0] + 0.5 - (a * (c + 0.5) + b * (c + 0.5))
    ff = centro[1] + 0.5 - (d * (c + 0.5) + e * (c + 0.5))
    pil = Image.fromarray(img.astype(np.float32), mode="F")
    w = pil.transform((size, size), Image.AFFINE, (a, b, cc, d, e, ff), resample=Image.BILINEAR, fillcolor=float(img.mean()))
    return np.asarray(w, dtype=np.float64)


def mascara_franja(size, pxm, ang=0.0):
    """Franja sobre el cañon en coordenadas de la plantilla: disco en la boca (centro) y tramo hacia la recamara en la
    direccion `ang` (la plantilla se guarda girada a ang = 0: el cañon va hacia +x)."""
    c = (size - 1) / 2.0
    hw = max(2.0, RADIO_BOCA_M * pxm)
    largo = min(LARGO_FRANJA_M * pxm, size / 2.0 - 1)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float64)
    x, y = xx - c, yy - c
    ux, uy = math.cos(ang), math.sin(ang)
    # por delante de la punta entra un tramo de fondo: el borde arma/fondo de la boca es el unico rasgo no periodico
    # a lo largo del eje (anillos y ranuras se repiten y dejan saltos de un periodo)
    t = np.clip(x * ux + y * uy, -FRENTE_M * pxm, largo)
    dist = np.hypot(x - t * ux, y - t * uy)
    return (dist <= hw).astype(np.float64)


def _corr_valid(win, ker):
    """Correlacion cruzada 'valid' por FFT: out[i, j] = sum(win[i:i+s, j:j+s] * ker)."""
    s = ker.shape[0]
    H, W = win.shape
    F = np.fft.rfft2(win)
    K = np.fft.rfft2(ker[::-1, ::-1], s=win.shape)
    full = np.fft.irfft2(F * K, s=win.shape)
    return full[s - 1:H, s - 1:W]


def ncc_mascara(tpl, mask, win):
    """NCC enmascarada de la plantilla sobre la ventana (posiciones validas)."""
    n = float(mask.sum())
    if n < 10:
        return None
    m = mask
    tm = (tpl * m).sum() / n
    t = (tpl - tm) * m
    ts = math.sqrt(float((t * t).sum()))
    if ts < 1e-6:
        return None
    t = t / ts
    num = _corr_valid(win, t)
    s1 = _corr_valid(win, m)
    s2 = _corr_valid(win * win, m)
    var = np.maximum(s2 - s1 * s1 / n, 0.0)
    return num / np.sqrt(np.where(var < 1e-6, np.inf, var))


def _subpix(m, y, x):
    def par(a, b, c):
        den = a - 2 * b + c
        return 0.0 if abs(den) < 1e-12 else 0.5 * (a - c) / den
    dy = par(m[y - 1, x], m[y, x], m[y + 1, x]) if 0 < y < m.shape[0] - 1 else 0.0
    dx = par(m[y, x - 1], m[y, x], m[y, x + 1]) if 0 < x < m.shape[1] - 1 else 0.0
    return y + dy, x + dx


# ---------- medida ----------

class Plantilla:
    def __init__(self, img, pu, ang, pxm):
        # se guarda girada a ang = 0 y a su propia escala (1 px de plantilla = 1 px de la captura de referencia)
        self.pxm = pxm
        self.tpl = ventana_warp(img, pu, ang, 1.0, TPL_PX)
        self.mask = mascara_franja(TPL_PX, pxm)


def detectar(plantilla, img, pu, ang, pxm):
    """Posicion de la boca en `img` (px) buscando en ±BUSQUEDA_PX alrededor de `pu`, con la plantilla girada a `ang` y
    escalada a `pxm`. La lectura solo pone ang y escala: la busqueda no prefiere ninguna posicion. Devuelve
    (u, v, calidad) o None."""
    k = pxm / plantilla.pxm                   # px de captura por px de plantilla
    size = TPL_PX + 2 * BUSQUEDA_PX
    best = None
    # el angulo predicho se afina en ±ANG_BUSQUEDA_DEG: con 3 grados de error la franja deja de casar al final del cañon
    # y un anillo desplazado un periodo puntua igual (salto de ~8 px en la sintetica). Afinar el angulo no mete la
    # lectura en la posicion: la ventana gira alrededor de pu y la posicion se sigue buscando sin preferencia.
    for dd in ANG_BUSQUEDA_DEG:
        a = ang + math.radians(dd)
        win = ventana_warp(img, pu, a, k, size)
        m = ncc_mascara(plantilla.tpl, plantilla.mask, win)
        if m is None:
            continue
        y, x = np.unravel_index(int(m.argmax()), m.shape)
        q = float(m[y, x])
        if best is None or q > best[0]:
            best = (q, a, m, y, x)
    if best is None:
        return None
    q, a, m, y, x = best
    # unicidad: si otro pico a mas de AMBIG_RADIO_PX puntua casi igual, la deteccion es ambigua (rasgos periodicos,
    # fondo parecido) y no se da por medida. No mira la continuidad en el tiempo: eso esconderia temblor real.
    # el segundo pico es un maximo LOCAL distinto (el lobulo del primero es ancho y no cuenta)
    p = np.pad(m, 1, constant_values=-np.inf)
    vecinos = np.max(np.stack([p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx]
                               for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]), axis=0)
    locales = m > vecinos
    yy, xx = np.ogrid[0:m.shape[0], 0:m.shape[1]]
    fuera = locales & ((yy - y) ** 2 + (xx - x) ** 2 > AMBIG_RADIO_PX ** 2)
    q2 = float(m[fuera].max()) if fuera.any() else -1.0
    ys, xs = _subpix(m, y, x)
    du, dv = xs - BUSQUEDA_PX, ys - BUSQUEDA_PX   # desplazamiento en px de plantilla
    ca, sa = math.cos(a) * k, math.sin(a) * k
    return pu[0] + ca * du - sa * dv, pu[1] + sa * du + ca * dv, q, q - q2


def aceptada(det):
    """Deteccion medible: calidad suficiente y pico unico (margen frente al segundo maximo local)."""
    return det is not None and det[2] >= CALIDAD_MIN and det[3] >= AMBIG_MIN


def vista(row, f):
    """Direccion 3D unitaria boca->recamara en ejes de la camara (lectura a). Elige la plantilla del banco de vista mas
    parecida: no entra en la posicion."""
    lect = row.get("lecturas") or {}
    u = (lect.get("usti hlavne") or {}).get("a")
    k = (lect.get("konec hlavne") or {}).get("a")
    cam = row.get("cam")
    if u is None or k is None or not cam:
        return None
    d = np.asarray(k, dtype=np.float64) - np.asarray(u, dtype=np.float64)
    v = np.array([d @ np.asarray(cam[a], dtype=np.float64) for a in ("x", "y", "z")])
    nv = float(np.linalg.norm(v))
    return v / nv if nv > 1e-9 else None


def elegir_plantilla(banco, v, giro):
    """La plantilla del banco con la vista mas parecida, de OTRO giro, dentro de VISTA_MAX_DEG. None si no hay."""
    best, best_ang = None, VISTA_MAX_DEG
    for b in banco:
        if b["giro"] == giro:
            continue
        ang = math.degrees(math.acos(max(-1.0, min(1.0, float(b["vista"] @ v)))))
        if ang <= best_ang:
            best, best_ang = b, ang
    return best


def _p95(v):
    s = sorted(v)
    return float(s[max(0, int(math.ceil(0.95 * len(s))) - 1)]) if s else float("inf")


def veredicto(derivas, n_capturas):
    res = {"n_shots": n_capturas, "n_validas": len(derivas)}
    if n_capturas < MIN_SHOTS_WINDOW:
        res.update(verdict="INCONCLUSO", cause="insufficient_sampling")
        return res
    res["coverage"] = round(len(derivas) / max(1, n_capturas), 4)
    if len(derivas) < MIN_SHOTS_WINDOW:
        res.update(verdict="INCONCLUSO", cause="correlacion_debil")
        return res
    res["p95_px"] = round(_p95(derivas), 4)
    res["p50_px"] = round(float(np.median(derivas)), 4)
    res["frac_sobre_umbral"] = round(float(np.mean(np.asarray(derivas) > THRESH_PX)), 4)
    if res["p95_px"] > THRESH_PX:
        res.update(verdict="FALLA", cause="p95_px_exceeded")
    elif res["coverage"] < COVERAGE_MIN:
        res.update(verdict="INCONCLUSO", cause="low_coverage")
    else:
        res.update(verdict="PASA", cause="")
    return res


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


def lecturas_de(row):
    return sorted(((row.get("lecturas") or {}).get("usti hlavne") or {}).keys())


def evaluar(run_dir, k, f):
    rows = _rows(run_dir)
    by = {r["frame"]: r for r in rows}
    out = {"run": Path(run_dir).name, "measure": "T-lect-directa", "k": k, "f_px": f}
    ref = None
    for r in rows:
        if r.get("shot") and r["frame"] >= ESTABLE_FRAME and by.get(r["frame"] + k):
            g = geometria(by[r["frame"] + k], f)
            if g is not None:
                ref = (r, g)
                break
    if ref is None:
        out.update(verdict="INCONCLUSO", cause="sin_referencia")
        return out
    (rref, (pu0, ang0, pxm0)) = ref
    plantilla = Plantilla(borrar_hud(_gray(_png(run_dir, rref["shot"]))), pu0, ang0, pxm0)
    out.update(ref_shot=rref["shot"], ref_boca=[round(pu0[0], 2), round(pu0[1], 2)], ref_px_por_m=round(pxm0, 1),
               mascara_px=int(plantilla.mask.sum()))
    ventanas = {}
    for r in rows:
        g = int(r.get("giro") or 0)
        if g > 0 and r.get("shot"):
            ventanas.setdefault(f"giro{g}", []).append(r)
    # Banco de plantillas (orquestador, 26-nov): con el giro el cañon cambia de vista en 3D (escorzo) y una sola
    # plantilla deja de casar (NCC 0,45-0,6 y detecciones espurias). La plantilla de la primera captura estable vale
    # para su vista; para el resto se usan capturas de OTROS giros con la vista 3D mas parecida, cada una recortada en
    # la proyeccion de (a) de su propia captura (el mismo hueco del sesgo declarado).
    v0 = vista(by[rref["frame"] + k], f)
    banco = [{"giro": 0, "vista": v0, "pl": plantilla, "shot": rref["shot"]}] if v0 is not None else []
    for w, wrows in ventanas.items():
        g = int(w[4:])
        for r in wrows[::BANCO_PASO]:
            tgt = by.get(r["frame"] + k)
            if tgt is None:
                continue
            gb, vb = geometria(tgt, f), vista(tgt, f)
            if gb is None or vb is None:
                continue
            banco.append({"giro": g, "vista": vb, "shot": r["shot"],
                          "pl": Plantilla(borrar_hud(_gray(_png(run_dir, r["shot"]))), gb[0], gb[1], gb[2])})
    out["banco"] = len(banco)
    out["ventanas"] = {}
    for w, wrows in sorted(ventanas.items()):
        g = int(w[4:])
        derivas = {}
        n = 0
        sin_plantilla = 0
        for r in wrows:
            tgt = by.get(r["frame"] + k)
            if tgt is None:
                continue
            ga = geometria(tgt, f)
            va = vista(tgt, f)
            if ga is None or va is None:
                continue
            n += 1
            b = elegir_plantilla(banco, va, g)
            if b is None:
                sin_plantilla += 1
                continue
            img = borrar_hud(_gray(_png(run_dir, r["shot"])))
            det = detectar(b["pl"], img, ga[0], ga[1], ga[2])
            if not aceptada(det):
                continue
            for lec in lecturas_de(tgt):
                gl = geometria(tgt, f, lec)
                if gl is None:
                    continue
                derivas.setdefault(lec, []).append(math.hypot(det[0] - gl[0][0], det[1] - gl[0][1]))
        out["ventanas"][w] = {lec: veredicto(d, n) for lec, d in sorted(derivas.items())} or {"a": veredicto([], n)}
        for v in out["ventanas"][w].values():
            v["sin_plantilla"] = sin_plantilla
    por_lectura = {}
    for w in out["ventanas"].values():
        for lec, v in w.items():
            por_lectura.setdefault(lec, []).append(v["verdict"])
    out["por_lectura"] = {lec: ("FALLA" if "FALLA" in vs else ("INCONCLUSO" if "INCONCLUSO" in vs else "PASA"))
                          for lec, vs in sorted(por_lectura.items())}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_dir")
    ap.add_argument("--k", type=int, required=True)
    ap.add_argument("--f", type=float, required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    res = evaluar(a.run_dir, a.k, a.f)
    txt = json.dumps(res, indent=1, ensure_ascii=False)
    if a.json:
        Path(a.json).write_text(txt + "\n", encoding="utf-8")
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
