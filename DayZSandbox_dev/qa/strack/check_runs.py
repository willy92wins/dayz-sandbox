"""Comprobación mecánica de las corridas reales de S-track·2 (arbitraje del orquestador, 2026-11-13).

Sol, en su cuarta vuelta sobre el evaluador, dejó cuatro BLOQ que solo se dan con entradas que el banco real no
debería producir. No se tocó el evaluador: esta comprobación corre sobre las corridas ANTES de aceptar cualquier
veredicto suyo. Una corrida que no la pasa es INVÁLIDA y su veredicto no cuenta (se repite o queda INCONCLUSA).

  1. Termina: `done.json` con "ok": true (y `preflight.json` fuera de `calib`).
  2. Giros completos (BLOQ 1, giro truncado): cada giro 1..3 (1..2 en `suave*`) dura 4,0 ± 0,3 s más un frame,
     medido entre el primer y el último frame con ese `giro`; y están todos los que pide el caso.
  3. Entrada completa (BLOQ 2): en `suave*`, `cam_raw` (pos, x, y, z, q) y `lata.a` en todos los frames.
  4. Reloj coherente (BLOQ 3): entre frames consecutivos, `t_ms[n] - t_ms[n-1]` = `1000 * dt[n]` ± 1 ms.
  5. Calibración (BLOQ 4): cada negativa necesita la corrida `calib_<hook>` válida en la misma carpeta.
  6. Muestras: `samples.jsonl` no vacío y, si hay `SHA256SUMS`, que case.

Uso: python check_runs.py <carpeta strack con una subcarpeta por corrida> [--json salida.json]
Salida: una línea por corrida (VALIDA / INVALIDA y motivos) y código 0 si todas son válidas, 1 si no, 2 si no hay corridas.
Solo biblioteca estándar.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

GIRO_S = 4.0
GIRO_TOL_S = 0.3
DT_TOL_MS = 1.0
GIROS_POR_CASO = {"mount0": 3, "mount03": 3, "lookat": 3, "follow": 3, "ropa": 3,
                  "suave30": 2, "suave60": 2, "suave144": 2}
NEGATIVAS = {"delay1", "roll", "smooth03", "quatlerp", "longarc"}


def split_run(name):
    parts = name.split("_")
    caso, hook = parts[0], parts[1] if len(parts) > 1 else ""
    inject = parts[2] if len(parts) > 2 else "none"
    return caso, hook, inject


def load_samples(path):
    rows, bad = [], 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    return rows, bad


def check_sha(run_dir):
    sums = run_dir / "SHA256SUMS"
    if not sums.is_file():
        return None
    wrong = []
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, name = line.partition("  ")
        name = name.lstrip("*")
        f = run_dir / name
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != digest.strip().lower():
            wrong.append(name)
    return wrong


def check_run(run_dir):
    caso, hook, inject = split_run(run_dir.name)
    why = []
    done_p = run_dir / "done.json"
    if not done_p.is_file():
        return caso, hook, inject, ["sin done.json"]
    try:
        done = json.loads(done_p.read_text(encoding="utf-8"))
    except ValueError:
        return caso, hook, inject, ["done.json ilegible"]
    if done.get("ok") is not True:
        why.append(f"done.ok={done.get('ok')} causa={done.get('causa')}")
    if caso != "calib" and not (run_dir / "preflight.json").is_file():
        why.append("sin preflight.json")
    sp = run_dir / "samples.jsonl"
    if not sp.is_file():
        why.append("sin samples.jsonl")
        return caso, hook, inject, why
    rows, bad = load_samples(sp)
    if bad:
        why.append(f"{bad} lineas ilegibles en samples.jsonl")
    if not rows:
        why.append("samples.jsonl vacio")
        return caso, hook, inject, why
    rows.sort(key=lambda r: r.get("frame", -1))

    # 4. reloj coherente
    incoh, faltan_t = 0, 0
    for prev, cur in zip(rows, rows[1:]):
        if cur.get("frame") != prev.get("frame", -10) + 1:
            continue
        t0, t1, dt = prev.get("t_ms"), cur.get("t_ms"), cur.get("dt")
        if not all(isinstance(v, (int, float)) for v in (t0, t1, dt)):
            faltan_t += 1
            continue
        if abs((t1 - t0) - 1000.0 * dt) > DT_TOL_MS:
            incoh += 1
    if faltan_t:
        why.append(f"{faltan_t} frames sin t_ms/dt numericos")
    if incoh:
        why.append(f"{incoh} pares con t_ms incoherente con dt (> {DT_TOL_MS} ms)")

    # 2. giros completos
    need = GIROS_POR_CASO.get(caso, 0)
    if need:
        dts = [r.get("dt") for r in rows if isinstance(r.get("dt"), (int, float))]
        frame_s = sorted(dts)[len(dts) // 2] if dts else 0.0
        for n in range(1, need + 1):
            g = [r for r in rows if r.get("giro") == n and isinstance(r.get("t_ms"), (int, float))]
            if not g:
                why.append(f"falta el giro {n}")
                continue
            dur = (g[-1]["t_ms"] - g[0]["t_ms"]) / 1000.0
            if abs(dur - GIRO_S) > GIRO_TOL_S + frame_s:
                why.append(f"giro {n} dura {dur:.2f} s (pide {GIRO_S} +- {GIRO_TOL_S} s)")

    # 3. entrada completa en suave*
    if caso.startswith("suave"):
        sin = 0
        for r in rows:
            cr, lata = r.get("cam_raw") or {}, r.get("lata") or {}
            if any(cr.get(k) is None for k in ("pos", "x", "y", "z", "q")) or lata.get("a") is None:
                sin += 1
        if sin:
            why.append(f"{sin} frames sin cam_raw completo o sin lata.a")

    # 6. integridad
    wrong = check_sha(run_dir)
    if wrong:
        why.append(f"SHA256SUMS no casa en {len(wrong)} ficheros")
    return caso, hook, inject, why


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("runs")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    root = Path(a.runs)
    # una carpeta por corrida; fuera las .prev_ y .invalid_ que aparta el banco, y marcas/ del orquestador
    dirs = sorted(d for d in root.iterdir() if d.is_dir() and "." not in d.name and d.name != "marcas")
    if not dirs:
        print(f"sin corridas en {root}")
        return 2
    res = {}
    for d in dirs:
        caso, hook, inject, why = check_run(d)
        res[d.name] = {"caso": caso, "hook": hook, "inject": inject, "motivos": why}
    # 5. calibración para las negativas
    for name, r in res.items():
        if r["inject"] in NEGATIVAS and r["caso"] != "calib" and not r["caso"].startswith("suave"):
            c = res.get(f"calib_{r['hook']}")
            if c is None:
                r["motivos"].append(f"sin calib_{r['hook']}")
            elif c["motivos"]:
                r["motivos"].append(f"calib_{r['hook']} invalida")
    ok = True
    for name, r in res.items():
        r["valida"] = not r["motivos"]
        ok &= r["valida"]
        print(f"{name:32s} {'VALIDA' if r['valida'] else 'INVALIDA'}" + ("" if r["valida"] else "  " + "; ".join(r["motivos"])))
    print(f"RESULT {sum(r['valida'] for r in res.values())} validas, {sum(not r['valida'] for r in res.values())} invalidas")
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
