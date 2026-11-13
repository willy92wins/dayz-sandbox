#!/usr/bin/env python3
"""Comprobador de negativas de S-track (criterios 4/5 y CONTRACT SS3/SS14).

Lee un informe.json y comprueba que las negativas esperadas salieron
FALLA (``got == "FALLA"``):

- Schema 2 (CONTRACT SS14, S-track-2): las nueve corridas fijas
  ``mount0_Ha_delay1``, ``mount0_Hb_delay1``, ``mount0_Hc_delay1``,
  ``lookat_Ha_delay1``, ``lookat_Hb_delay1``, ``mount0_Hb_roll``,
  ``suave60_Hb_smooth03``, ``suave60_Hb_quatlerp`` y
  ``suave60_Hb_longarc``, todas con ``expected == "FALLA"``.
  Se identifican por el nombre completo de ``run``. Cualquier
  ``got`` distinto de FALLA (PASA, INCONCLUSO u otro), una
  negativa ausente, un ``expected`` ausente, ``null`` o distinto
  de ``"FALLA"``, un ``inject`` ausente, ``null``, ``""`` o que
  no casa con el sufijo de ``run``, o una corrida duplicada
  devuelve exit 1 con el motivo.
- Schema 1 (CONTRACT SS3, S-track-1): se sigue aceptando para no
  romper la evidencia de S-track-1, con su logica historica:
  delay1 en mount0/lookat por hook evaluado y roll en mount0 con Ha.
  "Hook evaluado" se deriva de ``results`` (``inject == "none"``);
  si no hay hooks para un caso se exige al menos Ha.

Uso:
    python check_negatives.py [informe.json]

Sin argumento busca ``informe.json`` en el directorio actual.

Codigos de salida:
    0  se cumple (todas las esperadas presentes y con got == "FALLA")
    1  alguna negativa no salio FALLA; en schema 2 tambien si falta
       alguna de las nueve
    2  falta alguna corrida esperada (solo schema 1), el fichero no
       existe, el JSON no es valido / no tiene la estructura minima
       o el schema no es 1 ni 2

Solo stdlib.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

KNOWN_CASES = ("calib", "mount0", "mount03", "lookat", "follow")
KNOWN_HOOKS = ("Ha", "Hb", "Hc")

# CONTRACT SS14: las nueve negativas de schema 2, en este orden.
SCHEMA2_NEGATIVE_RUNS = (
    "mount0_Ha_delay1",
    "mount0_Hb_delay1",
    "mount0_Hc_delay1",
    "lookat_Ha_delay1",
    "lookat_Hb_delay1",
    "mount0_Hb_roll",
    "suave60_Hb_smooth03",
    "suave60_Hb_quatlerp",
    "suave60_Hb_longarc",
)


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


def expected_requirements_schema2():
    """Las nueve (caso, hook, inject) de CONTRACT SS14, en orden."""
    return [parse_run(run) for run in SCHEMA2_NEGATIVE_RUNS]


def expected_requirements(informe):
    """Requisitos segun el schema del informe.

    Schema 2: las nueve fijas de SS14. Schema 1 (o sin schema, como
    la evidencia historica): la lista del criterio 4 de S-track-1.
    """
    if isinstance(informe, dict) and informe.get("schema") == 2:
        return expected_requirements_schema2()
    return _expected_requirements_schema1(informe)


def _expected_requirements_schema1(informe):
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


def _check_schema2(informe):
    """Schema 2: nueve por ``run`` completo (CONTRACT SS14).

    ``expected`` debe ser exactamente ``"FALLA"``, ``inject``
    debe casar con el sufijo de ``run`` y ninguna de las nueve
    puede venir duplicada; todos son exit 1 con motivo en la
    fila (``detail``).
    """
    negativas = informe.get("negativas") or []
    by_run = {}
    if isinstance(negativas, list):
        for entry in negativas:
            if not isinstance(entry, dict):
                continue
            run = entry.get("run")
            if not isinstance(run, str) or not run:
                continue
            by_run.setdefault(run, []).append(entry)
    rows = []
    has_error = False
    for run_name in SCHEMA2_NEGATIVE_RUNS:
        caso, hook, inject = parse_run(run_name)
        entries = by_run.get(run_name, [])
        if not entries:
            has_error = True
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": run_name, "got": "-", "status": "FALTA",
                "detail": f"falta la negativa {run_name} (esperada FALLA)",
            })
            continue
        if len(entries) > 1:
            has_error = True
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": run_name,
                "got": str(entries[0].get("got", "")),
                "status": "DUPLICADA",
                "detail": (
                    f"corrida duplicada {run_name}: "
                    f"{len(entries)} entradas"
                ),
            })
            continue
        entry = entries[0]
        got = str(entry.get("got", ""))
        # Vuelta 4: expected debe existir y ser exactamente "FALLA";
        # ausente, null o distinto -> EXPECTED_NO_CASA, exit 1.
        has_expected = "expected" in entry
        actual_expected = entry.get("expected")
        if not has_expected or actual_expected != "FALLA":
            has_error = True
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": run_name, "got": got, "status": "EXPECTED_NO_CASA",
                "detail": (
                    f"{run_name} tiene expected={actual_expected!r} "
                    f"y se esperaba 'FALLA'"
                ),
            })
            continue
        # Vuelta 3: inject debe existir y ser exactamente el sufijo
        # de run; ausente, null, "" u otro valor -> INJECT_NO_CASA.
        has_inject = "inject" in entry
        actual_inject = entry.get("inject")
        if not has_inject or actual_inject != inject:
            has_error = True
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": run_name, "got": got, "status": "INJECT_NO_CASA",
                "detail": (
                    f"{run_name} tiene inject={actual_inject!r} "
                    f"y el sufijo de run exige {inject!r}"
                ),
            })
        elif got != "FALLA":
            has_error = True
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": run_name, "got": got, "status": "MAL_VEREDICTO",
                "detail": f"{run_name} salio {got} y se esperaba FALLA",
            })
        else:
            rows.append({
                "caso": caso, "hook": hook, "inject": inject,
                "run": run_name, "got": "FALLA", "status": "OK",
                "detail": "",
            })
    return (1 if has_error else 0), rows


def check_informe(informe):
    """Comprueba las negativas sobre un dict ya parseado.

    Devuelve (exit_code, rows) donde cada row es un dict con
    caso, hook, inject, run, got y status
    (``OK`` / ``MAL_VEREDICTO`` / ``FALTA`` / ``DUPLICADA`` /
    ``INJECT_NO_CASA`` / ``EXPECTED_NO_CASA``).

    Schema 2: identificacion por ``run`` completo; cualquier
    PASA/INCONCLUSO u otro ``got``, una ausente, un ``expected``
    ausente, ``null`` o distinto de ``"FALLA"``, un ``inject``
    que no casa con el sufijo de ``run`` o una duplicada da
    exit 1. Schema 1: ausente da exit 2 y veredicto distinto de
    FALLA da exit 1 (comportamiento historico).
    Schema distinto de 1/2 da exit 2 sin filas.
    """
    if not isinstance(informe, dict):
        return 2, []
    schema = informe.get("schema", 1)
    if schema not in (1, 2):
        return 2, []
    if schema == 2:
        return _check_schema2(informe)
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
    schema = informe.get("schema", 1)
    if schema not in (1, 2):
        print(
            f"ERROR: schema no soportado en {path}: {schema!r} "
            "(se aceptan 1 y 2)",
            file=sys.stderr,
        )
        return 2
    label = "CRITERIO 5 (schema 2)" if schema == 2 else "CRITERIO 4 (schema 1)"
    code, rows = check_informe(informe)
    print(format_table(rows))
    for row in rows:
        if row["status"] == "FALTA":
            print(f"MOTIVO: falta la negativa {row['run']} (esperada FALLA)")
        elif row["status"] == "MAL_VEREDICTO":
            print(
                f"MOTIVO: {row['run']} salio {row['got']} "
                "y se esperaba FALLA"
            )
        elif row["status"] in (
            "DUPLICADA", "INJECT_NO_CASA", "EXPECTED_NO_CASA"
        ):
            print(f"MOTIVO: {row.get('detail') or row['status']}")
    if code == 0:
        print(f"{label}: OK (todas las negativas esperadas salieron FALLA)")
    elif code == 1:
        print(f"{label}: NO CUMPLE (alguna negativa no salio FALLA o falta)")
    else:
        print(f"{label}: NO CUMPLE (falta alguna corrida esperada)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
