#!/usr/bin/env python3
"""Herramienta de marcas a mano de S-track·2 (brief §4, contrato §12).

No dibuja ninguna proyección de lectura: solo enseña la imagen, una rejilla de coordenadas y
recortes ampliados, para que el marcador ponga la boca y la recámara sin ver dónde caen las lecturas.

Subcomandos:
  elegir  <run_dir> [--marcas DIR]
      Elige las 5 capturas de la corrida (la primera estable, una en mitad de cada giro y una en mitad
      del resto) y crea o actualiza qa/strack/marcas/<run>.json con su sha256 (de la PNG) y su momento.
  vista   <run_dir> <png> --out FICHERO
      Vista entera reducida a la mitad (960x540) con rejilla cada 50 px en coordenadas de la PNG original.
  recorte <run_dir> <png> <u> <v> --out FICHERO [--medio 24] [--zoom 12]
      Recorte de (2*medio+1)^2 px centrado en (u, v), ampliado sin interpolar, con una línea cada píxel y
      etiquetas cada 4 px en coordenadas de la PNG original (centro del píxel = coordenada entera).
  poner   <run> <png> <marcador A|B> <punto> <u> <v> [--marcas DIR]
      Escribe la marca de un marcador. Punto: «usti hlavne», «konec hlavne» o «mira».
  poner-borde <run> <png> <A|B> u1 v1 u2 v2 u3 v3 u4 v4 u5 v5 [--marcas DIR]
      Guarda los 5 puntos del borde de la boca en `boca_anillo_borde` (contrato §17).
  poner-orejas <run> <png> <A|B> u1 v1 u2 v2 [--marcas DIR]
      Guarda las dos puntas del punto de mira en `punto_mira_orejas` y su media en `punto_mira`.
  cerrar  <run> [--marcas DIR]
      Ajusta una elipse a los 5 puntos de `boca_anillo_borde` de cada marcador, toma su centro,
      promedia las dos puntas de `punto_mira_orejas`, calcula `puntos` (media de A y B) y
      `diff_max_px` en cada captura con las dos marcas.

Convención de píxel (contrato §12): origen arriba-izquierda, el centro del píxel (0,0) en (0.0, 0.0).
Solo numpy, Pillow y stdlib.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

STRACK = Path(__file__).resolve().parent
PUNTOS = ("usti hlavne", "konec hlavne", "mira")
PUNTOS_SESGO = ("boca_anillo", "punto_mira")
ESTABLE_FRAME = 30  # ~0,5 s a 60 fps tras armar
CONVENCION = ("px de la PNG 1920x1080, origen arriba-izquierda, centro del pixel (0,0) en (0.0,0.0); "
              "mismo marco que la proyeccion de §2")


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rows(run_dir):
    out = []
    with open(Path(run_dir) / "samples.jsonl", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _shots(rows):
    """Una entrada por captura pedida (shot != ""), sin duplicar frames de H-b."""
    seen = set()
    shots = []
    for r in rows:
        name = r.get("shot") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        shots.append({"shot": name, "t": float(r.get("t_ms") or 0.0), "giro": int(r.get("giro") or 0),
                      "frame": int(r.get("frame") or 0)})
    return shots


def _nearest(cands, t_mid):
    return min(cands, key=lambda s: abs(s["t"] - t_mid)) if cands else None


def elegir_capturas(rows, run_dir):
    """Las 5 del brief §4: primera estable, mitad de cada giro y mitad del resto (solo PNG existentes)."""
    shots = [s for s in _shots(rows) if (Path(run_dir) / Path(s["shot"]).with_suffix(".png").name).is_file()]
    elegidas = []
    # «Estable»: fuera de giro y pasado el arranque. Con k = -1 la captura del frame n muestra la vista del
    # n-1, así que el frame 0 enseña todavía la cámara del jugador; se toma la primera desde ESTABLE_FRAME.
    estables = [s for s in shots if s["giro"] == 0 and s["frame"] >= ESTABLE_FRAME]
    if estables:
        elegidas.append((estables[0], "estable"))
    giros = sorted({s["giro"] for s in shots if s["giro"] > 0})
    for g in giros:
        cand = [s for s in shots if s["giro"] == g]
        t_mid = (cand[0]["t"] + cand[-1]["t"]) / 2.0
        elegidas.append((_nearest(cand, t_mid), f"giro{g}"))
    resto = [s for s in estables if s is not (estables[0] if estables else None)]
    if resto:
        t_mid = (resto[0]["t"] + resto[-1]["t"]) / 2.0
        elegidas.append((_nearest(resto, t_mid), "resto"))
    return elegidas


def _marcas_path(run, marcas_dir):
    return Path(marcas_dir or (STRACK / "marcas")) / f"{run}.json"


def _load(run, marcas_dir):
    p = _marcas_path(run, marcas_dir)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"schema": 1, "run": run, "convencion": CONVENCION,
            "marcadores": {"A": "claude-orquestador", "B": ""}, "marcas": []}


def _save(run, data, marcas_dir):
    p = _marcas_path(run, marcas_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def cmd_elegir(args):
    run_dir = Path(args.run_dir)
    run = run_dir.name
    data = _load(run, args.marcas)
    by_png = {m["png"]: m for m in data["marcas"]}
    for s, momento in elegir_capturas(_rows(run_dir), run_dir):
        png = Path(s["shot"]).with_suffix(".png").name
        sha = _sha256(run_dir / png)
        m = by_png.get(png)
        if m is None:
            m = {"shot": s["shot"], "png": png, "sha256": sha, "momento": momento, "A": {}, "B": {}}
            data["marcas"].append(m)
        elif m.get("sha256") != sha:
            raise SystemExit(f"{png}: el sha256 cambió desde que se eligió ({m.get('sha256')} != {sha})")
    # Contrato §18: en ropa (un solo hook) se marcan 10 capturas; --extra N añade N capturas de giro repartidas.
    extra = int(getattr(args, "extra", 0) or 0)
    if extra > 0:
        taken = {m["png"] for m in data["marcas"]}
        cands = [s for s in _shots(_rows(run_dir)) if s["giro"] > 0
                 and (run_dir / Path(s["shot"]).with_suffix(".png").name).is_file()
                 and Path(s["shot"]).with_suffix(".png").name not in taken]
        if cands:
            step = max(1, len(cands) // (extra + 1))
            for s in cands[step::step][:extra]:
                png = Path(s["shot"]).with_suffix(".png").name
                data["marcas"].append({"shot": s["shot"], "png": png, "sha256": _sha256(run_dir / png),
                                       "momento": f"extra_giro{s['giro']}", "A": {}, "B": {}})
    p = _save(run, data, args.marcas)
    for m in data["marcas"]:
        print(f"{m['momento']:8s} {m['png']}  {m['sha256'][:12]}")
    print(f"escrito {p}")


def _grid_font_draw(img):
    return ImageDraw.Draw(img)


def cmd_vista(args):
    im = Image.open(Path(args.run_dir) / args.png).convert("RGB")
    small = im.resize((im.width // 2, im.height // 2), Image.BILINEAR)
    d = ImageDraw.Draw(small)
    for x in range(0, im.width, 50):
        col = (255, 255, 0) if x % 100 == 0 else (90, 90, 0)
        d.line([(x // 2, 0), (x // 2, small.height)], fill=col, width=1)
        if x % 100 == 0:
            d.text((x // 2 + 2, 2), str(x), fill=(255, 255, 0))
    for y in range(0, im.height, 50):
        col = (0, 255, 255) if y % 100 == 0 else (0, 90, 90)
        d.line([(0, y // 2), (small.width, y // 2)], fill=col, width=1)
        if y % 100 == 0:
            d.text((2, y // 2 + 2), str(y), fill=(0, 255, 255))
    small.save(args.out)
    print(args.out)


def cmd_recorte(args):
    im = np.asarray(Image.open(Path(args.run_dir) / args.png).convert("RGB"))
    h, w = im.shape[:2]
    cu, cv, r, z = int(round(args.u)), int(round(args.v)), int(args.medio), int(args.zoom)
    x0, y0 = cu - r, cv - r
    n = 2 * r + 1
    crop = np.zeros((n, n, 3), dtype=np.uint8)
    xs0, ys0 = max(0, x0), max(0, y0)
    xs1, ys1 = min(w, x0 + n), min(h, y0 + n)
    crop[ys0 - y0:ys1 - y0, xs0 - x0:xs1 - x0] = im[ys0:ys1, xs0:xs1]
    big = Image.fromarray(np.repeat(np.repeat(crop, z, axis=0), z, axis=1))
    margin = 40
    canvas = Image.new("RGB", (big.width + margin, big.height + margin), (0, 0, 0))
    canvas.paste(big, (margin, margin))
    d = ImageDraw.Draw(canvas)
    for i in range(n + 1):
        col = (70, 70, 70)
        d.line([(margin + i * z, margin), (margin + i * z, margin + n * z)], fill=col)
        d.line([(margin, margin + i * z), (margin + n * z, margin + i * z)], fill=col)
    for i in range(n):
        px = x0 + i
        py = y0 + i
        if px % 4 == 0:
            d.text((margin + i * z + 1, 2), str(px), fill=(255, 255, 0))
            d.line([(margin + i * z + z // 2, margin - 8), (margin + i * z + z // 2, margin)], fill=(255, 255, 0))
        if py % 4 == 0:
            d.text((1, margin + i * z + 1), str(py), fill=(0, 255, 255))
            d.line([(margin - 8, margin + i * z + z // 2), (margin, margin + i * z + z // 2)], fill=(0, 255, 255))
    canvas.save(args.out)
    print(f"{args.out}  x {x0}..{x0 + n - 1}  y {y0}..{y0 + n - 1}  zoom {z}")


def fit_ellipse_center(points):
    """Centro de la elipse que pasa por 5 puntos (solución exacta de la cónica).

    Resuelve el núcleo del sistema 5x6 de la cónica general
    A x^2 + B xy + C y^2 + D x + E y + F = 0 y devuelve su centro.
    Lanza ValueError si los puntos no son 5, si la cónica no es una elipse
    (B^2 - 4AC >= 0, p. ej. puntos casi colineales) o si el centro no está definido.
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) != 5:
        raise ValueError("fit_ellipse_center: se necesitan exactamente 5 puntos")
    # Centrar y escalar antes de ajustar: en pixeles crudos (p. ej. centro
    # (960, 540), semiejes (12, 30)) las columnas x^2/y^2 dominan y el
    # determinante de la matriz del centro cae por debajo de 1e-12 en
    # elipses validas. Se deshace el cambio en el centro al final.
    cx0 = sum(p[0] for p in pts) / len(pts)
    cy0 = sum(p[1] for p in pts) / len(pts)
    scale = max(max(abs(p[0] - cx0), abs(p[1] - cy0)) for p in pts)
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("fit_ellipse_center: puntos degenerados (sin conica unica)")
    npts = [((x - cx0) / scale, (y - cy0) / scale) for x, y in pts]
    design = np.array(
        [[x * x, x * y, y * y, x, y, 1.0] for x, y in npts], dtype=np.float64
    )
    _u, _s, vt = np.linalg.svd(design)
    # Núcleo de dimensión > 1 (puntos colineales, repetidos o degenerados):
    # el 5.º valor singular (rango < 5) delata que no hay cónica única.
    if len(_s) >= 1 and float(_s[-1]) <= 1e-10 * max(float(_s[0]), 1e-12):
        raise ValueError("fit_ellipse_center: puntos degenerados (sin conica unica)")
    conic = vt[-1]
    a, b, c, d, e, _f = (float(v) for v in conic)
    if b * b - 4.0 * a * c >= 0.0:
        raise ValueError("fit_ellipse_center: la conica no es una elipse")
    mat = np.array([[2.0 * a, b], [b, 2.0 * c]], dtype=np.float64)
    if abs(float(np.linalg.det(mat))) <= 1e-12:
        raise ValueError("fit_ellipse_center: centro no definido")
    center = np.linalg.solve(mat, np.array([-d, -e], dtype=np.float64))
    if not np.all(np.isfinite(center)):
        raise ValueError("fit_ellipse_center: centro no finito")
    return (float(cx0 + scale * center[0]), float(cy0 + scale * center[1]))


def _marker_feature_points(marker):
    """Punto único por rasgo §17 de un marcador: centro de elipse y media de orejas."""
    out = {}
    borde = marker.get("boca_anillo_borde")
    if borde is not None:
        try:
            out["boca_anillo"] = fit_ellipse_center(borde)
        except (ValueError, TypeError, IndexError):
            out["boca_anillo"] = None
    orejas = marker.get("punto_mira_orejas")
    if orejas is not None:
        try:
            (u1, v1), (u2, v2) = orejas
            out["punto_mira"] = ((float(u1) + float(u2)) / 2.0, (float(v1) + float(v2)) / 2.0)
        except (ValueError, TypeError, IndexError):
            out["punto_mira"] = None
    elif marker.get("punto_mira") is not None:
        try:
            u, v = marker["punto_mira"]
            out["punto_mira"] = (float(u), float(v))
        except (ValueError, TypeError, IndexError):
            out["punto_mira"] = None
    return out


def _find_png_en_corrida(args, run, png):
    """Localiza la PNG de una captura en la carpeta de la corrida, si existe."""
    cands = []
    run_dir = getattr(args, "run_dir", None)
    if run_dir:
        cands.append(Path(run_dir) / png)
    if getattr(args, "marcas", None):
        md = Path(args.marcas)
        cands.extend([md / run / png, md.parent / run / png, md / png])
    cands.extend([Path(run) / png, STRACK / run / png, Path.cwd() / run / png, Path.cwd() / png])
    for c in cands:
        if c.is_file():
            return c
    return None


def _ensure_marca(args, data, run, png):
    """Devuelve la marca de `png`; si no esta elegida, la da de alta como extra.

    Solo da de alta si la PNG existe en la carpeta de la corrida: guarda su
    sha256 y `momento: "extra"` (contrato §12 ampliado, vuelta 3).
    """
    m = _find_marca(data, png)
    if m is not None:
        return m
    png_path = _find_png_en_corrida(args, run, png)
    if png_path is None:
        raise SystemExit(f"{png} no está entre las capturas elegidas de {run} ni existe en su carpeta")
    m = {"shot": Path(png).with_suffix(".bmp").name, "png": png,
         "sha256": _sha256(png_path), "momento": "extra", "A": {}, "B": {}}
    data["marcas"].append(m)
    return m


def cmd_poner(args):
    if args.punto not in PUNTOS + ("punto_mira",):
        raise SystemExit(f"punto no válido: {args.punto}")
    if args.marcador not in ("A", "B"):
        raise SystemExit("marcador: A o B")
    data = _load(args.run, args.marcas)
    m = _ensure_marca(args, data, args.run, args.png)
    marker = m.setdefault(args.marcador, {})
    marker[args.punto] = [float(args.u), float(args.v)]
    if args.punto == "punto_mira":
        marker.pop("punto_mira_orejas", None)
    _save(args.run, data, args.marcas)
    print(f"{args.run} {args.png} {args.marcador} {args.punto} = ({args.u}, {args.v})")


def _find_marca(data, png):
    for m in data["marcas"]:
        if m["png"] == png:
            return m
    return None


def cmd_poner_borde(args):
    if args.marcador not in ("A", "B"):
        raise SystemExit("marcador: A o B")
    coords = [float(x) for x in args.coords]
    if len(coords) != 10:
        raise SystemExit("poner-borde: se necesitan exactamente 5 puntos (10 coordenadas)")
    borde = [[coords[i], coords[i + 1]] for i in range(0, 10, 2)]
    data = _load(args.run, args.marcas)
    m = _ensure_marca(args, data, args.run, args.png)
    m.setdefault(args.marcador, {})["boca_anillo_borde"] = borde
    _save(args.run, data, args.marcas)
    print(f"{args.run} {args.png} {args.marcador} boca_anillo_borde = {borde}")


def cmd_poner_orejas(args):
    if args.marcador not in ("A", "B"):
        raise SystemExit("marcador: A o B")
    coords = [float(x) for x in args.coords]
    if len(coords) != 4:
        raise SystemExit("poner-orejas: se necesitan exactamente 2 puntas (4 coordenadas)")
    orejas = [[coords[0], coords[1]], [coords[2], coords[3]]]
    media = [round((coords[0] + coords[2]) / 2.0, 3), round((coords[1] + coords[3]) / 2.0, 3)]
    data = _load(args.run, args.marcas)
    m = _ensure_marca(args, data, args.run, args.png)
    marker = m.setdefault(args.marcador, {})
    marker["punto_mira_orejas"] = orejas
    marker["punto_mira"] = media
    _save(args.run, data, args.marcas)
    print(f"{args.run} {args.png} {args.marcador} punto_mira_orejas = {orejas} media={media}")


def cerrar(data):
    """Media de A y B y diff_max_px por captura (solo los puntos con las dos marcas).

    Conserva el formato de §12 y añade los rasgos de §17: el centro de la
    elipse ajustada a `boca_anillo_borde` y la media de `punto_mira_orejas`
    entran en `puntos` como `boca_anillo` y `punto_mira`, y su distancia
    entre marcadores entra en `diff_max_px`. Una elipse rechazada o un
    rasgo presente en un solo marcador invalida la marca (diff 999.0).
    """
    for m in data["marcas"]:
        a, b = m.get("A") or {}, m.get("B") or {}
        puntos, diffs = {}, []
        for p in PUNTOS:
            if p in a and p in b:
                (ua, va), (ub, vb) = a[p], b[p]
                puntos[p] = [round((ua + ub) / 2.0, 3), round((va + vb) / 2.0, 3)]
                diffs.append(math.hypot(ua - ub, va - vb))
            elif p in a or p in b:
                diffs.append(float("inf"))  # un solo marcador: la marca no vale
        feat_a = _marker_feature_points(a)
        feat_b = _marker_feature_points(b)
        for p in PUNTOS_SESGO:
            pa, pb = feat_a.get(p), feat_b.get(p)
            present_a = p in feat_a or (p == "boca_anillo" and "boca_anillo_borde" in a) or (p == "punto_mira" and ("punto_mira_orejas" in a or "punto_mira" in a))
            present_b = p in feat_b or (p == "boca_anillo" and "boca_anillo_borde" in b) or (p == "punto_mira" and ("punto_mira_orejas" in b or "punto_mira" in b))
            if pa is not None and pb is not None:
                puntos[p] = [round((pa[0] + pb[0]) / 2.0, 3), round((pa[1] + pb[1]) / 2.0, 3)]
                diffs.append(math.hypot(pa[0] - pb[0], pa[1] - pb[1]))
            elif present_a or present_b:
                diffs.append(float("inf"))
        m["puntos"] = puntos
        m["diff_max_px"] = round(max(diffs), 3) if diffs and all(math.isfinite(x) for x in diffs) else 999.0
    return data


def cmd_cerrar(args):
    data = cerrar(_load(args.run, args.marcas))
    _save(args.run, data, args.marcas)
    for m in data["marcas"]:
        print(f"{m['momento']:8s} {m['png']} diff_max_px={m['diff_max_px']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("elegir"); s.add_argument("run_dir"); s.add_argument("--marcas"); s.add_argument("--extra", type=int, default=0); s.set_defaults(f=cmd_elegir)
    s = sub.add_parser("vista"); s.add_argument("run_dir"); s.add_argument("png"); s.add_argument("--out", required=True); s.set_defaults(f=cmd_vista)
    s = sub.add_parser("recorte"); s.add_argument("run_dir"); s.add_argument("png"); s.add_argument("u", type=float); s.add_argument("v", type=float)
    s.add_argument("--out", required=True); s.add_argument("--medio", type=int, default=24); s.add_argument("--zoom", type=int, default=12); s.set_defaults(f=cmd_recorte)
    s = sub.add_parser("poner"); s.add_argument("run"); s.add_argument("png"); s.add_argument("marcador"); s.add_argument("punto")
    s.add_argument("u", type=float); s.add_argument("v", type=float); s.add_argument("--marcas"); s.add_argument("--run-dir", dest="run_dir"); s.set_defaults(f=cmd_poner)
    s = sub.add_parser("poner-borde"); s.add_argument("run"); s.add_argument("png"); s.add_argument("marcador")
    s.add_argument("coords", nargs=10, type=float, metavar="U_V"); s.add_argument("--marcas"); s.add_argument("--run-dir", dest="run_dir"); s.set_defaults(f=cmd_poner_borde)
    s = sub.add_parser("poner-orejas"); s.add_argument("run"); s.add_argument("png"); s.add_argument("marcador")
    s.add_argument("coords", nargs=4, type=float, metavar="U_V"); s.add_argument("--marcas"); s.add_argument("--run-dir", dest="run_dir"); s.set_defaults(f=cmd_poner_orejas)
    s = sub.add_parser("cerrar"); s.add_argument("run"); s.add_argument("--marcas"); s.set_defaults(f=cmd_cerrar)
    args = ap.parse_args(argv)
    args.f(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
