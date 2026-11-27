#!/usr/bin/env python3
"""Mutantes del evaluador de S-track (criterios 1 de S-track-1 y S-track-2).

Para cada mutante copia ``s_track_eval.py`` a un directorio temporal,
aplica la sustitucion de texto sobre la linea exacta de la constante
(CONTRACT.md SS4 y SS13) y corre la suite del evaluador con
``STRACK_EVAL_PATH`` apuntando a la copia mutada.

Si la linea de la constante no esta exactamente una vez, el mutante
queda en ERROR: un mutante no aplicado nunca cuenta como superviviente
en silencio.

Antes de los mutantes corre la suite sin mutar; si el baseline no
esta verde, para con error porque un baseline rojo invalida todo.
Tras el baseline corre un control sin mutar: copia el evaluador
SIN mutar con la misma disposicion que cada mutante (directorio
temporal aislado, solo ``s_track_eval.py``) y corre la suite; si
el control no esta verde exactamente igual que el baseline, todos
los mutantes quedan en ERROR y el runner sale con codigo != 0.

Uso:
    python run_mutants.py [--strack-dir DIR] [--python EXE]

Salida: tabla mutante -> MUERTO/SOBREVIVE/ERROR, con los tests que
matan a cada mutante (campo ``killed_by`` del informe y lineas tras
la tabla), y ``mutants_report.json`` junto a este fichero (o en
``<strack-dir>`` si la carpeta de mutantes no es escribible en ese
arbol).
Codigo de salida 0 solo si mueren todos los mutantes (minimos y
extras); la etiqueta ``minimal`` queda solo como informacion.

Solo stdlib.
"""

from __future__ import annotations

import argparse
import ast
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
    # S-track-2 (brief SS5.1, CONTRACT SS13): minimos, tienen que morir.
    Mutant(
        name="plantilla_en_proyeccion",
        replacements=(
            ('TEMPLATE_SOURCE = "marca"', 'TEMPLATE_SOURCE = "proyeccion"'),
        ),
        minimal=True,
        description="Plantilla en la proyeccion en lugar de la marca.",
    ),
    Mutant(
        name="mascara_ignorada",
        replacements=(
            ("USE_MASK = True", "USE_MASK = False"),
        ),
        minimal=True,
        description="Mascara ignorada en la correlacion.",
    ),
    Mutant(
        name="umbral_suave_5pc",
        replacements=(
            ("THRESH_SUAVE_FRAC = 0.02", "THRESH_SUAVE_FRAC = 0.05"),
        ),
        minimal=True,
        description="Umbral de T-suave al 5 % en lugar del 2 %.",
    ),
)

MINIMAL_NAMES = tuple(m.name for m in MUTANTS if m.minimal)


def _line_core(raw):
    """Linea sin su fin de linea (\\r\\n, \\n o \\r)."""
    if raw.endswith("\r\n"):
        return raw[:-2], "\r\n"
    if raw.endswith("\n") or raw.endswith("\r"):
        return raw[:-1], raw[-1]
    return raw, ""


def _assign_info(line, mutant_name):
    """(nombre, valor literal) de una linea ``NOMBRE = <literal>``."""
    try:
        tree = ast.parse(line)
    except SyntaxError as exc:
        raise MutationError(
            f"mutante {mutant_name}: linea no parseable {line!r}: {exc}"
        ) from exc
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign):
        raise MutationError(
            f"mutante {mutant_name}: {line!r} no es una asignacion"
        )
    node = tree.body[0]
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        raise MutationError(
            f"mutante {mutant_name}: {line!r} no asigna a un solo Name"
        )
    try:
        value = ast.literal_eval(node.value)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise MutationError(
            f"mutante {mutant_name}: valor no literal en {line!r}"
        ) from exc
    return node.targets[0].id, value


def _module_assigns(tree, const_name):
    """Assign de nivel de modulo con un solo destino Name ``const_name``."""
    return [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == const_name
    ]


def apply_mutant(source_text, mutant):
    """Aplica las sustituciones de ``mutant`` sobre el texto fuente.

    Con ``ast``: la linea a sustituir debe ser exactamente el
    ``lineno`` de un ``ast.Assign`` de nivel de modulo con un solo
    destino ``Name`` igual a la constante, y esa linea debe ser
    exactamente la del contrato. 0 o >= 2 asignaciones a esa
    constante, o una linea distinta en ese ``lineno`` (p. ej. el
    texto esta dentro de una cadena multilinea y la asignacion
    real es ``USE_MASK = bool(1)``), levantan MutationError
    (mutante no aplicado = ERROR). Tras sustituir se vuelve a
    parsear y se comprueba que el valor literal es el nuevo.
    """
    try:
        ast.parse(source_text)
    except SyntaxError as exc:
        raise MutationError(
            f"mutante {mutant.name}: el fuente no es parseable: {exc}"
        ) from exc
    text = source_text
    for old, new in mutant.replacements:
        const_name, _old_value = _assign_info(old, mutant.name)
        new_name, new_value = _assign_info(new, mutant.name)
        if new_name != const_name:
            raise MutationError(
                f"mutante {mutant.name}: {new!r} no asigna a {const_name}"
            )
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            raise MutationError(
                f"mutante {mutant.name}: el fuente no es parseable: {exc}"
            ) from exc
        assigns = _module_assigns(tree, const_name)
        if len(assigns) != 1:
            raise MutationError(
                f"mutante {mutant.name}: la asignacion a {const_name} "
                f"a nivel de modulo aparece {len(assigns)} veces "
                "(se esperaba exactamente 1)"
            )
        node = assigns[0]
        if getattr(node, "end_lineno", node.lineno) != node.lineno:
            raise MutationError(
                f"mutante {mutant.name}: la asignacion a {const_name} "
                f"ocupa varias lineas (linea {node.lineno})"
            )
        lines = text.splitlines(True)
        if not (1 <= node.lineno <= len(lines)):
            raise MutationError(
                f"mutante {mutant.name}: lineno {node.lineno} fuera de rango"
            )
        core, ending = _line_core(lines[node.lineno - 1])
        if core != old:
            raise MutationError(
                f"mutante {mutant.name}: la linea {old!r} aparece "
                f"0 veces como asignacion activa; la linea "
                f"{node.lineno} de {const_name} es {core!r}"
            )
        lines[node.lineno - 1] = new + ending
        text = "".join(lines)
        # Re-parsear y comprobar el valor literal nuevo.
        try:
            new_tree = ast.parse(text)
        except SyntaxError as exc:
            raise MutationError(
                f"mutante {mutant.name}: tras sustituir no parsea: {exc}"
            ) from exc
        new_assigns = _module_assigns(new_tree, const_name)
        if len(new_assigns) != 1:
            raise MutationError(
                f"mutante {mutant.name}: tras sustituir, {const_name} "
                f"aparece {len(new_assigns)} veces"
            )
        try:
            actual = ast.literal_eval(new_assigns[0].value)
        except (ValueError, TypeError, SyntaxError) as exc:
            raise MutationError(
                f"mutante {mutant.name}: valor nuevo no literal "
                f"para {const_name}"
            ) from exc
        if actual != new_value or type(actual) is not type(new_value):
            raise MutationError(
                f"mutante {mutant.name}: tras sustituir, {const_name} "
                f"vale {actual!r} y se esperaba {new_value!r}"
            )
    return text


# Runner propio: descubre y corre la suite con TestLoader/TestResult
# y escribe en JSON testsRun y failures/errors con id() y kind.
# kind == "test" solo para un metodo de test individual cuyo fallo
# sale del cuerpo del test; setUp/tearDown (de instancia, clase o
# modulo) e importacion se distinguen por el traceback y nunca
# matan a un mutante.
_RUNNER_SCRIPT = '''\
import json
import sys
import unittest


def _kind(test, tid, tb=""):
    type_name = type(test).__name__
    label = str(test)
    if "setUpClass" in label or tid.startswith("setUpClass"):
        return "setup_class"
    if "setUpModule" in label or tid.startswith("setUpModule"):
        return "setup_module"
    if "tearDownClass" in label or "tearDownModule" in label:
        return "setup_class"
    if type_name == "_FailedTest" or tid.startswith(
        "unittest.loader._FailedTest"
    ):
        return "import"
    if type_name == "_ErrorHolder":
        return "setup_module" if "Module" in label else "setup_class"
    tb_text = tb if isinstance(tb, str) else ""
    if ", in tearDown" in tb_text:
        return "teardown"
    if ", in setUp" in tb_text:
        return "setup"
    if getattr(test, "_testMethodName", None):
        return "test"
    return "other"


# Arbitro (orquestador, tras 4 vueltas): la fase se registra de forma
# estructural envolviendo el cuerpo de cada metodo de test. Solo es
# muerte un failure (AssertionError) que sale del CUERPO del test (o de
# un subTest dentro del cuerpo). setUp, tearDown y addCleanup, aunque
# fallen con AssertionError, nunca son muerte.
BODY = {}


def _wrap_bodies(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            _wrap_bodies(item)
            continue
        name = getattr(item, "_testMethodName", None)
        if not name or not hasattr(item, name):
            continue
        tid = item.id()
        original = getattr(item, name)
        fexc = getattr(item, "failureException", AssertionError)

        def body(_orig=original, _tid=tid, _fexc=fexc):
            BODY[_tid] = "started"
            try:
                out = _orig()
            except _fexc:
                BODY[_tid] = "assert_fail"
                raise
            except unittest.SkipTest:
                BODY[_tid] = "skipped"
                raise
            except BaseException:
                BODY[_tid] = "error"
                raise
            BODY[_tid] = "ok"
            return out
        setattr(item, name, body)


def _body_kill(test, from_failures):
    if not from_failures:
        return False
    parent = getattr(test, "test_case", None)
    if parent is not None:
        # _SubTest: el fallo sale de un subTest dentro del cuerpo.
        return BODY.get(parent.id()) in ("ok", "assert_fail", "error")
    try:
        tid = test.id()
    except Exception:
        return False
    return BODY.get(tid) == "assert_fail"


def _entries(pairs, from_failures=False):
    out = []
    for test, _tb in pairs:
        try:
            tid = test.id()
        except Exception:
            tid = str(test)
        tb_text = _tb if isinstance(_tb, str) else str(_tb)
        kind = _kind(test, tid, tb_text)
        kill = _body_kill(test, from_failures)
        if kind == "test" and not kill:
            kind = "no_body"
        out.append({
            "id": tid, "kind": kind,
            "body_kill": bool(kill),
            "is_setup_error": not kill,
            "traceback": tb_text[-4000:],
        })
    return out


def main():
    strack_dir, tests_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    loader = unittest.TestLoader()
    try:
        suite = loader.discover(
            start_dir=tests_dir, pattern="test*.py",
            top_level_dir=strack_dir,
        )
    except Exception as exc:
        data = {
            "testsRun": 0, "failures": [],
            "errors": [{
                "id": "unittest.loader._FailedTest.discover",
                "kind": "import", "is_setup_error": True,
                "detail": f"{type(exc).__name__}: {exc}",
            }],
            "wasSuccessful": False,
        }
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        return 1
    result = unittest.TestResult()
    _wrap_bodies(suite)
    suite.run(result)
    # Solo diagnostico humano en stderr; la clasificacion usa el JSON.
    for _test, _tb in list(result.failures) + list(result.errors):
        print(f"{_test.id()}\\n{_tb}", file=sys.stderr)
    data = {
        "testsRun": result.testsRun,
        "failures": _entries(result.failures, from_failures=True),
        "errors": _entries(result.errors, from_failures=False),
        "wasSuccessful": bool(result.wasSuccessful()),
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _is_setup_entry(entry):
    """True si la entrada es de preparacion, no del cuerpo del test."""
    if not isinstance(entry, dict):
        return False
    # Arbitro: solo cuenta como muerte un failure del cuerpo del test.
    if entry.get("body_kill") is not True:
        return True
    if entry.get("kind") != "test" or entry.get("is_setup_error"):
        return True
    tb = entry.get("traceback") or entry.get("detail") or entry.get("tb") or ""
    if not isinstance(tb, str):
        tb = str(tb)
    return ", in setUp" in tb or ", in tearDown" in tb


def _individual_ids(structured):
    """id() de tests individuales fallidos, sin duplicados."""
    seen = []
    if not isinstance(structured, dict):
        return seen
    for key in ("failures", "errors"):
        entries = structured.get(key) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if _is_setup_entry(entry):
                continue
            tid = entry.get("id")
            if isinstance(tid, str) and tid and tid not in seen:
                seen.append(tid)
    return seen


def _setup_error_ids(structured):
    """id() de errores que no son de un test individual."""
    seen = []
    if not isinstance(structured, dict):
        return seen
    for key in ("failures", "errors"):
        entries = structured.get(key) or []
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if not _is_setup_entry(entry):
                continue
            tid = entry.get("id")
            if isinstance(tid, str) and tid and tid not in seen:
                seen.append(tid)
    return seen


def _structured_tests_run(structured):
    """testsRun como int, o None si no hay resultado estructurado."""
    if not isinstance(structured, dict):
        return None
    value = structured.get("testsRun")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def run_suite(python, strack_dir, eval_path):
    """Corre la suite contra ``eval_path`` con el runner propio.

    Devuelve (returncode, salida combinada, structured) donde
    structured es el dict JSON del runner (con ``testsRun`` None
    si el runner no produjo JSON valido). Lanza OSError si el
    interprete no se puede lanzar.
    """
    strack_dir = Path(strack_dir)
    tests_dir = strack_dir / "tests"
    env = dict(os.environ)
    env["STRACK_EVAL_PATH"] = str(Path(eval_path).resolve())
    tmpdir = tempfile.mkdtemp(prefix="strack_runner_")
    try:
        runner_path = Path(tmpdir) / "_strack_runner.py"
        runner_path.write_text(_RUNNER_SCRIPT, encoding="utf-8")
        json_path = Path(tmpdir) / "result.json"
        cmd = [
            str(python), str(runner_path),
            str(strack_dir), str(tests_dir), str(json_path),
        ]
        proc = subprocess.run(
            cmd, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        structured = {"testsRun": None, "failures": [], "errors": []}
        try:
            parsed = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                structured = parsed
        except (OSError, ValueError):
            pass
        return proc.returncode, output, structured
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _unpack_suite(raw):
    """(rc, output, structured) desde run_suite (3- o 2-tupla)."""
    if isinstance(raw, tuple) and len(raw) == 3:
        return raw[0], raw[1], raw[2]
    if isinstance(raw, tuple) and len(raw) == 2:
        return raw[0], raw[1], {"testsRun": None, "failures": [],
                                "errors": []}
    return 2, "", {"testsRun": None, "failures": [], "errors": []}


def _error_result(mutant, detail, returncode=None, tests_run=None):
    """Resultado ERROR de un mutante (p. ej. control sin mutar rojo)."""
    return {
        "name": mutant.name,
        "minimal": mutant.minimal,
        "kind": "minimo" if mutant.minimal else "extra",
        "description": mutant.description,
        "replacements": [
            {"old": old, "new": new} for old, new in mutant.replacements
        ],
        "status": "ERROR",
        "returncode": returncode,
        "tests_run": tests_run,
        "detail": detail,
        "output_tail": "",
        "killed_by": [],
    }


def _run_control(python, strack_dir, source_text):
    """Copia SIN mutar con la disposicion de un mutante y corre la suite.

    Mismo directorio temporal aislado y mismos ficheros alrededor
    (solo ``s_track_eval.py``) que usa ``run_one_mutant``.
    """
    tmpdir = tempfile.mkdtemp(prefix="strack_control_")
    try:
        control_path = Path(tmpdir) / "s_track_eval.py"
        control_path.write_text(source_text, encoding="utf-8")
        return _unpack_suite(run_suite(python, strack_dir, control_path))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def run_one_mutant(python, strack_dir, source_text, mutant,
                   baseline_killed_by=()):
    """Copia mutada en tmpdir + suite. Devuelve el dict de resultado.

    MUERTO solo si el runner estructurado dice ``testsRun >= 1``
    y hay >= 1 fallo o error de un test individual (``id()`` de
    un metodo de test, kind == "test") que no este en el baseline.
    ``testsRun`` None, 0 tests, o errores de setUp/tearDown (de
    instancia, clase o modulo) o de importacion dan ERROR, nunca
    MUERTO: un mutante que solo produce errores de preparacion es
    ERROR. Los fallos no se sacan del texto libre del log.
    """
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
        "tests_run": None,
        "detail": "",
        "output_tail": "",
        "killed_by": [],
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
            raw = run_suite(python, strack_dir, mutated_path)
        except OSError as exc:
            result["detail"] = f"no se pudo correr la suite: {exc}"
            result["tests_run"] = None
            return result
        returncode, output, structured = _unpack_suite(raw)
        result["returncode"] = returncode
        result["output_tail"] = (output or "")[-2000:]
        tests_run = _structured_tests_run(structured)
        result["tests_run"] = tests_run
        killed = _individual_ids(structured)
        setup_errors = _setup_error_ids(structured)
        baseline_set = set(baseline_killed_by or ())
        new_kills = [name for name in killed if name not in baseline_set]
        if tests_run is None:
            result["status"] = "ERROR"
            result["killed_by"] = []
            result["detail"] = (
                "sin resultado estructurado del runner "
                "(testsRun=None); no es MUERTO"
            )
        elif tests_run < 1:
            result["status"] = "ERROR"
            result["killed_by"] = []
            result["detail"] = (
                "la suite no ejecuto ningun test identificable "
                f"(testsRun={tests_run}); sin muerte atribuible"
            )
        elif setup_errors:
            result["status"] = "ERROR"
            result["killed_by"] = []
            result["detail"] = (
                "error de setUp/tearDown/setUpClass/setUpModule/"
                "importacion, no del cuerpo de un test: "
                + ", ".join(setup_errors)
            )
        elif returncode == 0:
            result["status"] = "SOBREVIVE"
            result["detail"] = "la suite pasa contra el mutante"
        elif not killed:
            result["status"] = "ERROR"
            result["killed_by"] = []
            result["detail"] = (
                "la suite falla sin test individual identificado "
                "por su id() (p. ej. setUpClass); no es MUERTO"
            )
        elif not new_kills:
            result["status"] = "ERROR"
            result["killed_by"] = []
            result["detail"] = (
                "los tests que fallan ya fallaban en el baseline: "
                + ", ".join(killed)
            )
        else:
            result["status"] = "MUERTO"
            result["killed_by"] = new_kills
            result["detail"] = (
                "la suite falla contra el mutante; tests que lo matan: "
                + ", ".join(new_kills)
            )
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
        "control": {"ok": False, "returncode": None, "detail": "",
                    "tests_run": None},
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
        baseline_rc, baseline_out, baseline_structured = _unpack_suite(
            run_suite(python, strack_dir, eval_path)
        )
    except OSError as exc:
        report["baseline"]["detail"] = f"no se pudo correr la suite: {exc}"
        return 2, report
    report["baseline"]["returncode"] = baseline_rc
    report["baseline"]["output_tail"] = (baseline_out or "")[-2000:]
    report["baseline"]["tests_run"] = _structured_tests_run(
        baseline_structured
    )
    if baseline_rc != 0:
        report["baseline"]["detail"] = (
            "baseline rojo: la suite no pasa sin mutar; "
            "los mutantes no se evaluan"
        )
        return 2, report
    if _structured_tests_run(baseline_structured) is None:
        report["baseline"]["detail"] = (
            "baseline sin resultado estructurado (testsRun=None); "
            "los mutantes no se evaluan"
        )
        return 2, report
    if _structured_tests_run(baseline_structured) < 1:
        report["baseline"]["detail"] = (
            "baseline sin tests: la suite no ejecuto ningun test; "
            "los mutantes no se evaluan"
        )
        return 2, report
    report["baseline"]["ok"] = True
    report["baseline"]["detail"] = "suite verde sin mutar"
    baseline_killed = _individual_ids(baseline_structured)
    baseline_tests = _structured_tests_run(baseline_structured)

    # Control sin mutar con la disposicion de los mutantes: si no
    # esta verde exactamente igual que el baseline, todos ERROR.
    try:
        control_rc, control_out, control_structured = _run_control(
            python, strack_dir, source_text
        )
    except OSError as exc:
        detail = f"control sin mutar no se pudo correr: {exc}"
        report["control"]["detail"] = detail
        report["mutants"] = [
            _error_result(m, detail) for m in MUTANTS
        ]
        return 2, report
    control_tests = _structured_tests_run(control_structured)
    report["control"]["returncode"] = control_rc
    report["control"]["output_tail"] = (control_out or "")[-2000:]
    report["control"]["tests_run"] = control_tests
    control_green = (
        control_rc == 0
        and control_tests is not None
        and control_tests == baseline_tests
        and not _individual_ids(control_structured)
        and not _setup_error_ids(control_structured)
    )
    if not control_green:
        detail = (
            "control sin mutar no verde igual que el baseline "
            f"(returncode={control_rc}, testsRun={control_tests} "
            f"frente a baseline testsRun={baseline_tests}); "
            "todos los mutantes son ERROR"
        )
        report["control"]["detail"] = detail
        report["mutants"] = [
            _error_result(
                m, detail, returncode=control_rc,
                tests_run=control_tests,
            )
            for m in MUTANTS
        ]
        return 2, report
    report["control"]["ok"] = True
    report["control"]["detail"] = (
        "suite verde sin mutar con la disposicion de los mutantes"
    )

    for mutant in MUTANTS:
        report["mutants"].append(
            run_one_mutant(
                python, strack_dir, source_text, mutant,
                baseline_killed_by=baseline_killed,
            )
        )

    # BLOQ4: tienen que morir todos; `minimal` solo es informacion.
    report["ok"] = bool(report["mutants"]) and all(
        m["status"] == "MUERTO" for m in report["mutants"]
    )
    if report["ok"]:
        return 0, report
    # Arbitro: un mutante en ERROR (p. ej. solo errores de preparacion o
    # limpieza) es un fallo de entorno/arnes, no un superviviente: exit 2.
    if any(m["status"] == "ERROR" for m in report["mutants"]):
        return 2, report
    return 1, report


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
    headers = ("mutante", "tipo", "estado", "tests que lo matan")
    rows = []
    for m in report.get("mutants", []):
        killed = ", ".join(m.get("killed_by") or []) or "-"
        rows.append((m["name"], m["kind"], m["status"], killed))
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
        description="Corre los mutantes del evaluador de S-track."
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
    report_written = None
    write_failed = False
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report_written = str(out_path)
    except OSError as exc:
        print(f"ERROR: no se pudo escribir {out_path}: {exc}", file=sys.stderr)
        write_failed = True

    baseline = report["baseline"]
    if not baseline["ok"]:
        print(f"BASELINE: ERROR - {baseline['detail']}")
        tail = baseline.get("output_tail", "")
        if tail:
            print(tail.rstrip())
        print("Los mutantes no se evaluan: un baseline rojo invalida todo.")
    else:
        print("BASELINE: OK (suite verde sin mutar)")
        control = report.get("control") or {}
        if control:
            if control.get("ok"):
                print("CONTROL: OK (suite verde sin mutar, disposicion de mutante)")
            else:
                print(f"CONTROL: ERROR - {control.get('detail', '')}")
                tail = control.get("output_tail", "")
                if tail:
                    print(tail.rstrip())
        print(format_table(report))
        for m in report["mutants"]:
            killed = ", ".join(m.get("killed_by") or [])
            if m["status"] == "MUERTO" and killed:
                print(f"  {m['name']}: MUERTO por {killed}")
            elif m["status"] != "MUERTO":
                print(f"  {m['name']}: {m['status']} - {m['detail']}")
    if report_written:
        print(f"Informe: {report_written}")
    if write_failed:
        # Sin informe guardado no hay OK: exit != 0 siempre.
        print("RESULTADO: ERROR (no se pudo escribir el informe)")
        return exit_code if exit_code != 0 else 2
    if exit_code == 0:
        print("RESULTADO: OK (todos los mutantes mueren)")
    elif exit_code == 2:
        print("RESULTADO: ERROR (baseline o entorno)")
    else:
        print("RESULTADO: FALLO (algun mutante no muere)")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
