#!/usr/bin/env python3
"""Extrae del p3d vanilla del M4A1 los rasgos visibles del contrato §17 y escribe m4a1_rasgos.json.

Uso: python extract_rasgos_m4a1.py <odol_reader_dir> <m4a1.p3d> <salida.json>
  <odol_reader_dir>: carpeta scripts/ de la skill dayz-p3d-debinarizer (odol_reader.py).
Escribe, en el espacio del modelo: usti/konec (LOD de memoria), el centro del anillo exterior de la cara frontal
del apagallamas (LOD 0) y el vértice de la punta del punto de mira delantero (LOD 0), con los datos de comprobación.
"""
import hashlib
import importlib
import json
import math
import sys
from pathlib import Path


def main(reader_dir, p3d, out):
    sys.path.insert(0, reader_dir)
    # Dependencia externa al repo, solo para extraer: se carga por importlib
    # para no romper qa/tests/test_stdlib_only.py (no es un import estatico).
    ODOL = importlib.import_module("odol_reader").ODOL

    odol = ODOL.from_file(p3d)
    mem = next(l for l in odol.lods if l is not None and any(s.name == "usti hlavne" for s in l.named_selections))
    sel = {s.name: s for s in mem.named_selections}

    def mp(name):
        v = mem.vertices[list(sel[name].selected_vertices)[0]]
        return [v.x, v.y, v.z]

    usti, konec = mp("usti hlavne"), mp("konec hlavne")
    ay, az = usti[1], usti[2]
    lod0 = odol.lods[0]
    V = [(v.x, v.y, v.z) for v in lod0.vertices]
    # cara frontal del apagallamas: los vertices mas adelantados (x minima) a menos de 15 mm del eje, sin
    # puntos sueltos (triangulos de proxy): se toma la x minima con >= 8 vertices en +-0,2 mm.
    near = [p for p in V if math.hypot(p[1] - ay, p[2] - az) < 0.015 and p[0] < usti[0]]
    xs = sorted({round(p[0], 4) for p in near})
    face_x = next(x for x in xs if sum(1 for p in near if abs(p[0] - x) <= 0.0002) >= 8)
    face = [p for p in near if abs(p[0] - face_x) <= 0.0004]
    rr = [math.hypot(p[1] - ay, p[2] - az) for p in face]
    r_cut = (max(rr) + min(rr)) / 2.0
    outer = sorted({(round(p[0], 6), round(p[1], 6), round(p[2], 6)) for p, r in zip(face, rr) if r > r_cut})
    cx = sum(p[0] for p in outer) / len(outer)
    cy = sum(p[1] for p in outer) / len(outer)
    cz = sum(p[2] for p in outer) / len(outer)
    off = math.hypot(cy - ay, cz - az)
    # punto de mira delantero: el vertice mas alto (y maxima) entre la boca y la mitad del cañón, por encima del eje
    # y a menos de 10 mm del plano medio (z).
    x_lo, x_hi = usti[0], (usti[0] + konec[0]) / 2.0
    # Se descartan los triangulos de proxy (vertices sueltos a > 15 cm del eje: optica, linterna).
    cand = [p for p in V if x_lo < p[0] < x_hi and abs(p[2] - az) < 0.010 and ay < p[1] < ay + 0.15]
    y_top = max(p[1] for p in cand)
    top = [p for p in cand if p[1] >= y_top - 1e-4]
    # Las dos «orejas» del punto de mira: los vertices de la cara superior con |z| maxima a cada lado.
    zr = max(p[2] - az for p in top)
    zl = min(p[2] - az for p in top)
    ears = [p for p in top if abs((p[2] - az) - zr) < 1e-4 or abs((p[2] - az) - zl) < 1e-4]
    xe = max(p[0] for p in ears)  # canto delantero de la cara superior
    ears = [p for p in ears if abs(p[0] - xe) < 1e-4]
    tip = (sum(p[0] for p in ears) / len(ears), sum(p[1] for p in ears) / len(ears), sum(p[2] for p in ears) / len(ears))
    data = {
        "schema": 1,
        "fuente": {"p3d": str(p3d).replace("\\", "/"), "sha256": hashlib.sha256(Path(p3d).read_bytes()).hexdigest(),
                   "odol_version": odol.version},
        "usti_hlavne": usti, "konec_hlavne": konec,
        "boca_anillo": {"pos_modelo": [cx, cy, cz], "n_vertices": len(outer),
                        "radio_m": sum(math.hypot(p[1] - cy, p[2] - cz) for p in outer) / len(outer),
                        "desvio_eje_m": off,
                        "t_eje": (cx - usti[0]) / (konec[0] - usti[0])},
        "punto_mira": {"pos_modelo": list(tip), "orejas": [list(p) for p in ears], "x_rango": [x_lo, x_hi],
                       "nota": "media de las dos orejas del punto de mira (canto delantero de la cara superior); se marcan las dos puntas y se usa la media"},
    }
    Path(out).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
