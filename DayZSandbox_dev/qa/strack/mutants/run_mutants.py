#!/usr/bin/env python3
"""Mutantes del evaluador de S-track-1 (criterio 1 del brief).

Para cada mutante copia ``s_track_eval.py`` a un directorio temporal,
aplica la sustitucion de texto sobre la linea exacta de la constante
(CONTRACT.md SS4) y corre la suite del evaluador con
``STRACK_EVAL_PATH`` apuntando a la copia mutada.

Si la linea de la constante no esta exactamente una vez, el mutante
queda en ERROR: un mutante no aplicado nunca cuenta como superviviente
en silencio.

Antes de los mutantes corre la suite sin mutar; si el baseline no
esta verde, para con error porque un baseline rojo invalida todo.

Uso:
    python run_mutants.py [--strack-dir DIR] [--python EXE]

Salida: tabla mutante -> MUERTO/SOBREVIVE/ERROR y
``mutants_report.json`` junto a este fichero (o en ``<strack-dir>``
si la carpeta de mutantes no es escribible en ese arbol).
Codigo de salida 0 solo si todos los mutantes minimos mueren.

Solo stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


class MutationError(Exception):
    """La linea de la constante no esta exactamente una vez."""


@dataclass(frozen=True)
class Mutant:
    name: str
    # Pares (linea exacta original, linea de reemplazo).
    replacements: tuple
    minimal: bool = True
    description: str = ""


# Lineas exactas de CONTRACT.md SS4. No reformatear: la sustitucion
# cuenta ocurrencias de la linea completa.
MUTANTS = (
    Mutant(
        name="umbral_relajado",
        replacements=(
            ("THRESH_PX = 2.0", "THRESH_PX = 20.0"),
            ("THRESH_ROLL_DEG = 0.5", "THRESH_ROLL_DEG = 5.0"),
        ),
        minimal=True,
        description="Umbrales de T-lect/T-hook x10: debe dejar pasar fallos.",
    ),
    Mutant(
        name="k_cero",
        replacements=(
            ("K_CANDIDATES = (-2, -1, 0, 1, 2)", "K_CANDIDATES = (0,)"),
        ),
        minimal=True,
        description="Calibracion fijada a k=0: debe romper la asociacion.",
    ),
    Mutant(
        name="cobertura_ignorada",
        replacements=(
            ("COVERAGE_MIN = 0.95", "COVERAGE_MIN = 0.0"),
        ),
        minimal=True,
        description="Sin minimo de cobertura: no debe salir INCONCLUSO.",
    ),
    Mutant(
        name="calib_match_cero",
        replacements=(
            ("CALIB_MATCH_MIN = 0.99", "CALIB_MATCH_MIN = 0.0"),
        ),
        minimal=False,
        description="extra: cualquier k vale en la calibracion.",
    ),
    Mutant(
        name="stimulus_cero",
        replacements=(
            ("STIMULUS_FACTOR = 3.0", "STIMULUS_FACTOR = 0.0"),
        ),
        minimal=False,
        description="extra: sin exigencia de estimulo en T-hook.",
    ),
    Mutant(
        name="detector_laxo",
        replacements=(
            ("DETECTOR_MAX_PX = 0.5", "DETECTOR_MAX_PX = 99.0"),
        ),
        minimal=False,
        description="extra: el detector nunca se declara malo.",
    ),
)

MINIMAL_NAMES = tuple(m.name for m in MUTANTS if m.minimal)


def apply_mutant(source_text, mutant):
    """Aplica las sustituciones de ``mutant`` sobre el texto fuente.

    Cada linea original debe aparecer exactamente una vez; en caso
    contrario levanta MutationError (mutante no aplicado = error).
    """
    text = source_text
    for old, new in mutant.replacements:
        count = text.count(old)
        if count != 1:
            raise MutationError(
                f"mutante {mutant.name}: la linea {old!r} aparece "
                f"{count} veces (se esperaba exactamente 1)"
            )
        text = text.replace(old, new)
    return text


def run_suite(python, strack_dir, eval_path):
    """Corre la suite del evaluador contra ``eval_path``.

    Devuelve (returncode, salida combinada). Lanza OSError si el
    interprete o la suite no se pueden lanzar.
    """
    strack_dir = Path(strack_dir)
    tests_dir = strack_dir / "tests"
    env = dict(os.environ)
    env["STRACK_EVAL_PATH"] = str(Path(eval_path).resolve())
    cmd = [
        str(python), "-m", "unittest", "discover",
        "-s", str(tests_dir), "-t", str(strack_dir),
    ]
    proc = subprocess.run(
        cmd, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, output


def run_one_mutant(python, strack_dir, source_text, mutant):
    """Copia mutada en tmpdir + suite. Devuelve el dict de resultado."""
    result = {
        "name": mutant.name,
        "minimal": mutant.minimal,
        "kind": "minimo" if mutant.minimal else "extra",
        "description": mutant.description,
        "replacements": [
            {"old": old, "new": new} for old, new in mutant.replacements
        ],
        "status": "ERROR",
        "returncode": None,
        "detail": "",
        "output_tail": "",
    }
    try:
        mutated = apply_mutant(source_text, mutant)
    except MutationError as exc:
        result["detail"] = str(exc)
        return result
    tmpdir = tempfile.mkdtemp(prefix=f"strack_mutant_{mutant.name}_")
    try:
        mutated_path = Path(tmpdir) / "s_track_eval.py"
        mutated_path.write_text(mutated, encoding="utf-8")
        try:
            returncode, output = run_suite(python, strack_dir, mutated_path)
        except OSError as exc:
            result["detail"] = f"no se pudo correr la suite: {exc}"
            return result
        result["returncode"] = returncode
        result["output_tail"] = output[-2000:]
        if returncode != 0:
            result["status"] = "MUERTO"
            result["detail"] = "la suite falla contra el mutante"
        else:
            result["status"] = "SOBREVIVE"
            result["detail"] = "la suite pasa contra el mutante"
        return result
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def run_all(strack_dir, python):
    """Baseline + todos los mutantes. Devuelve (exit_code, report)."""
    strack_dir = Path(strack_dir).resolve()
    eval_path = strack_dir / "s_track_eval.py"
    report = {
        "strack_dir": str(strack_dir),
        "eval_path": str(eval_path),
        "python": str(python),
        "baseline": {"ok": False, "returncode": None, "detail": ""},
        "mutants": [],
        "ok": False,
    }
    if not eval_path.is_file():
        report["baseline"]["detail"] = f"no existe el evaluador: {eval_path}"
        return 2, report
    if not (strack_dir / "tests").is_dir():
        report["baseline"]["detail"] = (
            f"no existe la suite: {strack_dir / 'tests'}"
        )
        return 2, report
    try:
        source_text = eval_path.read_text(encoding="utf-8")
    except OSError as exc:
        report["baseline"]["detail"] = f"no se puede leer el evaluador: {exc}"
        return 2, report

    # Baseline sin mutar: si no esta verde, todo lo demas no vale.
    try:
        baseline_rc, baseline_out = run_suite(python, strack_dir, eval_path)
    except OSError as exc:
        report["baseline"]["detail"] = f"no se pudo correr la suite: {exc}"
        return 2, report
    report["baseline"]["returncode"] = baseline_rc
    report["baseline"]["output_tail"] = baseline_out[-2000:]
    if baseline_rc != 0:
        report["baseline"]["detail"] = (
            "baseline rojo: la suite no pasa sin mutar; "
            "los mutantes no se evaluan"
        )
        return 2, report
    report["baseline"]["ok"] = True
    report["baseline"]["detail"] = "suite verde sin mutar"

    for mutant in MUTANTS:
        report["mutants"].append(
            run_one_mutant(python, strack_dir, source_text, mutant)
        )

    minimal_results = [m for m in report["mutants"] if m["minimal"]]
    report["ok"] = bool(minimal_results) and all(
        m["status"] == "MUERTO" for m in minimal_results
    )
    return (0 if report["ok"] else 1), report


def default_strack_dir():
    """Carpeta padre de ``mutants/`` segun la ubicacion de este fichero."""
    return Path(__file__).resolve().parent.parent


def report_path_for(strack_dir):
    """Donde va mutants_report.json para este ``strack_dir``."""
    candidate = Path(strack_dir) / "mutants" / "mutants_report.json"
    if candidate.parent.is_dir():
        return candidate
    return Path(strack_dir) / "mutants_report.json"


def format_table(report):
    headers = ("mutante", "tipo", "estado")
    rows = [
        (m["name"], m["kind"], m["status"]) for m in report.get("mutants", [])
    ]
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt(row):
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row))

    lines = [fmt(headers), fmt(tuple("-" * w for w in widths))]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Corre los mutantes del evaluador de S-track-1."
    )
    parser.add_argument(
        "--strack-dir", default=None,
        help="carpeta qa/strack (por defecto: la padre de mutants/)",
    )
    parser.add_argument(
        "--python", default=sys.executable,
        help="interprete para la suite (por defecto: sys.executable)",
    )
    args = parser.parse_args(argv)

    strack_dir = (
        Path(args.strack_dir).resolve()
        if args.strack_dir else default_strack_dir()
    )
    exit_code, report = run_all(strack_dir, args.python)

    out_path = report_path_for(strack_dir)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report_written = str(out_path)
    except OSError as exc:
        print(f"ERROR: no se pudo escribir {out_path}: {exc}", file=sys.stderr)
        report_written = None

    baseline = report["baseline"]
    if not baseline["ok"]:
        print(f"BASELINE: ERROR - {baseline['detail']}")
        tail = baseline.get("output_tail", "")
        if tail:
            print(tail.rstrip())
        print("Los mutantes no se evaluan: un baseline rojo invalida todo.")
    else:
        print("BASELINE: OK (suite verde sin mutar)")
        print(format_table(report))
        for m in report["mutants"]:
            if m["status"] != "MUERTO":
                print(f"  {m['name']}: {m['status']} - {m['detail']}")
    if report_written:
        print(f"Informe: {report_written}")
    if exit_code == 0:
        print("RESULTADO: OK (todos los mutantes minimos mueren)")
    elif exit_code == 2:
        print("RESULTADO: ERROR (baseline o entorno)")
    else:
        print("RESULTADO: FALLO (algun mutante minimo no muere)")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
