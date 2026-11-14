"""Comprobación mecánica de las corridas reales de S-track·2 (arbitraje del orquestador, 2026-11-13).

Sol, en su cuarta vuelta sobre el evaluador, dejó cuatro BLOQ que solo se dan con entradas que el banco real no
debería producir. No se tocó el evaluador: esta comprobación corre sobre las corridas ANTES de aceptar cualquier
veredicto suyo. Una corrida que no la pasa es INVÁLIDA y su veredicto no cuenta (se repite o queda INCONCLUSA).

  1. Termina: `done.json` con "ok": true (y `preflight.json` fuera de `calib`).
  2. Giros completos (BLOQ 1, giro truncado): cada giro 1..3 (1..2 en `suave*`) dura 4,0 ± 0,3 s más un frame,
     medido entre el primer y el último frame con ese `giro`; y están todos los que pide el caso.
  3. Entrada completa (BLOQ 2): en `suave*`, `cam_raw` (pos, x, y, z, q) y `lata.a` en todos los frames.
  4. Reloj coherente (BLOQ 3, vuelta 5; vuelta 5b, M2): cada fila tiene `t_ms` y `dt` finitos y `dt > 0`
     (también se rechazan NaN/Infinity en el JSON); dos filas del mismo frame con `t_ms` o
     `dt` distintos invalidan, y sobre las filas canónicas que consume el evaluador (la
     última de cada frame) `t_ms` crece estrictamente y la
     deriva ACUMULADA entre `t_ms` y `1000 * sum(dt)` no pasa de DERIVA_MAX_MS. Sin techo
     por intervalo: no hay base contractual para uno (vuelta 5b, M2). El único
     intervalo exento de deriva es el de carga 0→1 (ver _es_carga); tampoco él queda
     exento de la finitud. Tras la vuelta 5 el evaluador solo usa `t_ms`
     como reloj de pared (duración de giro y ventanas sin etiqueta), y de ahí sale el
     límite de deriva (ver la constante).
  5. Calibración (BLOQ 4): cada negativa necesita la corrida `calib_<hook>` válida en la misma carpeta; las de Hc,
     la `calib_Ha` (Hc no tiene calib propia y el evaluador usa la de Ha).
  6. Muestras: `samples.jsonl` no vacío y, si hay `SHA256SUMS`, que case.

Uso: python check_runs.py <carpeta strack con una subcarpeta por corrida> [--json salida.json]
Salida: una línea por corrida (VALIDA / INVALIDA y motivos) y código 0 si todas son válidas, 1 si no, 2 si no hay corridas.
Solo biblioteca estándar.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

GIRO_S = 4.0
GIRO_TOL_S = 0.3
# Límite de deriva fijado desde los consumidores de reloj de pared que quedan
# tras la vuelta 5 (H5), no desde los datos: la duración de giro admite
# 4,0 ± 0,3 s (CONTRACT §9) y las ventanas sin etiqueta `giro` unen pausas
# de 0,15 s (TURN_GAP_S del evaluador). La deriva dentro de una ventana
# puede oscilar como mucho 2·DERIVA_MAX_MS (de +límite a −límite); con
# 50 ms esa oscilación es 100 ms: un tercio de la tolerancia del giro y
# menos que la pausa mínima que une ventanas. Deja 200 ms de margen para
# la desviación real de duración y la cuantización de frame. Las dos
# calibraciones reales quedan muy por debajo (27,0 y 8,0 ms), pero eso es
# comprobación, no la razón del número. Vuelta 5b: ya no hay guarda de
# frontera de salto que este límite tuviera que proteger; y la
# corrección del filtro no depende de `t_ms` en absoluto: el filtro
# integra el `dt` registrado (CONTRACT §16) y todas sus medidas van
# sobre el eje Σdt del evaluador. `t_ms` solo alimenta las medidas de
# reloj de pared citadas arriba, y solo para ellas vale este límite.
DERIVA_MAX_MS = 50.0
GIROS_POR_CASO = {"mount0": 3, "mount03": 3, "lookat": 3, "follow": 3, "ropa": 3,
                  "suave30": 2, "suave60": 2, "suave144": 2}
NEGATIVAS = {"delay1", "roll", "smooth03", "quatlerp", "longarc"}
CALIB_DE = {"Hc": "Ha"}


def split_run(name):
    parts = name.split("_")
    caso, hook = parts[0], parts[1] if len(parts) > 1 else ""
    inject = parts[2] if len(parts) > 2 else "none"
    return caso, hook, inject


def _float_finito(texto):
    valor = float(texto)
    if not math.isfinite(valor):
        raise ValueError(f"numero no finito: {texto}")
    return valor


def _constante_no_finita(texto):
    # NaN / Infinity / -Infinity literales en el JSON (H4).
    raise ValueError(f"constante no finita en JSON: {texto}")


def load_samples(path):
    rows, bad = [], 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line, parse_float=_float_finito,
                                       parse_constant=_constante_no_finita))
            except ValueError:
                bad += 1
    return rows, bad


def _es_numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _frame_de(row):
    try:
        return int(row.get("frame"))
    except (TypeError, ValueError, AttributeError):
        return None


def _es_carga(prev, cur):
    """Intervalo de carga: solo el par de frames 0→1 (H2).

    El mod pone m_Frame=-1 (STRACK_Session.c, inicialización) y lo sube a
    0 antes de la primera Capture, con el armado (TryArm y creación de la
    cámara) en ese mismo OnUpdate: el tirón de la creación cae en el
    intervalo que acaba en el frame 1. El primer par visto solo es el de
    carga si sus frames son exactamente 0 y 1; si la corrida empieza en
    otro frame no hay intervalo exento.
    """
    return _frame_de(prev) == 0 and _frame_de(cur) == 1


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
    # H4: finitud y dt>0 en CADA fila cruda, antes de acumular, deduplicar
    # o excluir nada (un NaN envenenaba la deriva de todo lo posterior).
    no_finitas, dt_no_positivo, sin_frame = 0, 0, 0
    for r in rows:
        if not isinstance(r, dict) or _frame_de(r) is None:
            sin_frame += 1
            continue
        t_v, dt_v = r.get("t_ms"), r.get("dt")
        if not _es_numero(t_v) or not _es_numero(dt_v) or not math.isfinite(float(t_v)) or not math.isfinite(float(dt_v)):
            no_finitas += 1
            continue
        if float(dt_v) <= 0.0:
            dt_no_positivo += 1
    if sin_frame:
        why.append(f"{sin_frame} filas sin frame entero")
    if no_finitas:
        why.append(f"{no_finitas} filas con t_ms/dt no finitos o no numericos")
    if dt_no_positivo:
        why.append(f"{dt_no_positivo} filas sin dt positivo (dt>0)")

    # H3: se validan exactamente las filas canónicas que consume el
    # evaluador (s_track_eval.py, _read_run: la última fila de cada frame,
    # con el shot rescatado de la anterior, irrelevante aquí). Dos filas
    # del mismo frame que difieren en t_ms o dt invalidan la corrida.
    por_frame, duplicados_distintos = {}, 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        f = _frame_de(r)
        if f is None:
            continue
        if f in por_frame:
            prev = por_frame[f]
            if prev.get("t_ms") != r.get("t_ms") or prev.get("dt") != r.get("dt"):
                duplicados_distintos += 1
        por_frame[f] = r  # la canónica es la última, como en el evaluador
    if duplicados_distintos:
        why.append(f"{duplicados_distintos} frames duplicados con t_ms o dt distintos")
    rows = [por_frame[f] for f in sorted(por_frame)]

    # 4. reloj coherente sobre las filas canónicas
    no_crece, deriva, max_deriva = 0, 0.0, 0.0
    for prev, cur in zip(rows, rows[1:]):
        if _frame_de(cur) != _frame_de(prev) + 1:
            continue
        t0, t1, dt = prev.get("t_ms"), cur.get("t_ms"), cur.get("dt")
        if not all(_es_numero(v) and math.isfinite(float(v)) for v in (t0, t1, dt)):
            continue  # ya contado arriba como no finito
        delta_ms = float(t1) - float(t0)
        if delta_ms <= 0.0:
            no_crece += 1
            continue
        if _es_carga(prev, cur):  # único exento de deriva
            continue
        deriva += delta_ms - 1000.0 * float(dt)
        max_deriva = max(max_deriva, abs(deriva))
    if no_crece:
        why.append(f"{no_crece} pares con t_ms que no crece")
    if max_deriva > DERIVA_MAX_MS:
        why.append(f"t_ms incoherente con dt: deriva acumulada de {max_deriva:.1f} ms (> {DERIVA_MAX_MS:.0f} ms)")

    # 2. giros completos
    need = GIROS_POR_CASO.get(caso, 0)
    if need:
        # La mediana de dt excluye el intervalo de carga (H2), como la deriva y los FPS.
        carga_i = 1 if len(rows) >= 2 and _es_carga(rows[0], rows[1]) else None
        dts = [float(r.get("dt")) for i, r in enumerate(rows)
               if i != carga_i and _es_numero(r.get("dt")) and math.isfinite(float(r.get("dt")))]
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
            # Hc no tiene calib propia (el mod la rechaza; brief §3: calib con H-a y H-b): el evaluador usa la de Ha
            # (s_track_eval.py, k_by_hook["Hc"] = k_by_hook["Ha"]), así que aquí se exige la misma.
            ch = CALIB_DE.get(r["hook"], r["hook"])
            c = res.get(f"calib_{ch}")
            if c is None:
                r["motivos"].append(f"sin calib_{ch}")
            elif c["motivos"]:
                r["motivos"].append(f"calib_{ch} invalida")
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
