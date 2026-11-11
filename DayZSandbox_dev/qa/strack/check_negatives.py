#!/usr/bin/env python3
"""Comprobador de negativas de S-track-1 (criterio 4 del brief).

Lee un informe.json (CONTRACT.md SS3) y comprueba que las negativas
esperadas salieron FALLA:

- delay1 en mount0, por cada hook evaluado en mount0.
- delay1 en lookat, por cada hook evaluado en lookat.
- roll en mount0 con Ha.

"Hook evaluado" se deriva de ``results``: hooks con entradas de
``inject == "none"`` (o sin inject) para ese caso. Si ``results`` no
aporta hooks para un caso, se exige al menos Ha como minimo.

Uso:
    python check_negatives.py [informe.json]

Sin argumento busca ``informe.json`` en el directorio actual.

Codigos de salida:
    0  se cumple (todas las esperadas presentes y con got == "FALLA")
    1  alguna corrida esperada esta presente pero got != "FALLA"
       (PASA, INCONCLUSO u otro valor)
    2  falta alguna corrida esperada, el fichero no existe o el JSON
       no es valido / no tiene la estructura minima

Solo stdlib.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KNOWN_CASES = ("calib", "mount0", "mount03", "lookat", "follow")
KNOWN_HOOKS = ("Ha", "Hb", "Hc")


def parse_run(run):
    """Devuelve (caso, hook, inject) a partir de un nombre de corrida.

    Formato CONTRACT SS1: ``<caso>_<hook>`` o ``<caso>_<hook>_<inject>``.
    Devuelve (None, None, None) si no se puede interpretar.
    """
    if not run or not isinstance(run, str):
        return (None, None, None)
    parts = run.split("_")
    if len(parts) < 2:
        return (None, None, None)
    caso = parts[0]
    hook = parts[1]
    inject = parts[2] if len(parts) >= 3 else None
    return (caso, hook, inject)


def _evaluated_hooks(informe, caso):
    """Hooks evaluados para ``caso`` segun ``results`` (inject none)."""
    hooks = set()
    results = informe.get("results") or []
    if not isinstance(results, list):
        return hooks
    for entry in results:
        if not isinstance(entry, dict):
            continue
        inject = entry.get("inject", "none")
        if inject not in (None, "", "none"):
            continue
        entry_caso = entry.get("caso")
        entry_hook = entry.get("hook")
        if not entry_caso and entry.get("run"):
            parsed_caso, parsed_hook, _ = parse_run(entry.get("run"))
            entry_caso = entry_caso or parsed_caso
            entry_hook = entry_hook or parsed_hook
        if entry_caso == caso and entry_hook:
            hooks.add(entry_hook)
    return hooks


def expected_requirements(informe):
    """Lista ordenada de (caso, hook, inject) exigidos por el criterio 4."""
    mount0_hooks = _evaluated_hooks(informe, "mount0") or {"Ha"}
    lookat_hooks = _evaluated_hooks(informe, "lookat") or {"Ha"}
    requirements = []
    for hook in sorted(mount0_hooks):
        requirements.append(("mount0", hook, "delay1"))
    for hook in sorted(lookat_hooks):
        requirements.append(("lookat", hook, "delay1"))
    requirements.append(("mount0", "Ha", "roll"))
    # Deduplicar conservando el orden.
    seen = set()
    unique = []
    for req in requirements:
        if req not in seen:
            seen.add(req)
            unique.append(req)
    return unique


def _negatives_index(informe):
    """Indice (caso, hook, inject) -> lista de entradas de ``negativas``."""
    index = {}
    negativas = informe.get("negativas") or []
    if not isinstance(negativas, list):
        return index
    for entry in negativas:
        if not isinstance(entry, dict):
            continue
        caso, hook, inject = parse_run(entry.get("run"))
        # Los campos explicitos, si existen, mandan sobre el parseo.
        # ``negativas`` de CONTRACT no trae caso/hook, pero se tolera.
        if entry.get("caso"):
            caso = entry.get("caso")
        if entry.get("hook"):
            hook = entry.get("hook")
        if entry.get("inject"):
            inject = entry.get("inject")
        if caso is None or hook is None or inject is None:
            continue
        index.setdefault((caso, hook, inject), []).append(entry)
    return index


def check_informe(informe):
    """Comprueba el criterio 4 sobre un dict ya parseado.

    Devuelve (exit_code, rows) donde cada row es un dict con
    caso, hook, inject, run, got y status
    (``OK`` / ``MAL_VEREDICTO`` / ``FALTA``).
    """
    if not isinstance(informe, dict):
        return 2, []
    requirements = expected_requirements(informe)
    index = _negatives_index(informe)
    rows = []
    has_missing = False
    has_wrong = False
    for caso, hook, inject in requirements:
        run_name = f"{caso}_{hook}_{inject}"
        entries = index.get((caso, hook, inject), [])
        if not entries:
            has_missing = True
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": run_name, "got": "-", "status": "FALTA",
            })
            continue
        # Con varias entradas para la misma corrida, basta el peor
        # veredicto: si alguna no es FALLA, la negativa no sirve.
        gots = [str(e.get("got", "")) for e in entries]
        if all(g == "FALLA" for g in gots):
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": entries[0].get("run", run_name),
                "got": "FALLA", "status": "OK",
            })
        else:
            has_wrong = True
            bad = next(g for g in gots if g != "FALLA")
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": entries[0].get("run", run_name),
                "got": bad, "status": "MAL_VEREDICTO",
            })
    if has_missing:
        return 2, rows
    if has_wrong:
        return 1, rows
    return 0, rows


def format_table(rows):
    """Tabla de texto de los resultados por corrida esperada."""
    headers = ("corrida", "inject", "got", "estado")
    body = [
        (r["run"], r["inject"], r["got"], r["status"]) for r in rows
    ]
    widths = [len(h) for h in headers]
    for row in body:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(row):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [fmt(headers), fmt(tuple("-" * w for w in widths))]
    lines.extend(fmt(row) for row in body)
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) > 1 or (argv and argv[0] in ("-h", "--help")):
        print(__doc__.strip())
        return 2 if len(argv) > 1 else 0
    path = Path(argv[0]) if argv else Path("informe.json")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"ERROR: no se puede leer {path}: {exc}", file=sys.stderr)
        return 2
    try:
        informe = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"ERROR: JSON no valido en {path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(informe, dict) or "negativas" not in informe:
        print(
            f"ERROR: {path} no tiene la estructura de informe.json "
            "(falta la clave 'negativas')",
            file=sys.stderr,
        )
        return 2
    code, rows = check_informe(informe)
    print(format_table(rows))
    if code == 0:
        print("CRITERIO 4: OK (todas las negativas esperadas salieron FALLA)")
    elif code == 1:
        print("CRITERIO 4: NO CUMPLE (alguna negativa no salio FALLA)")
    else:
        print("CRITERIO 4: NO CUMPLE (falta alguna corrida esperada)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
