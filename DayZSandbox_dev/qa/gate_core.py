"""Registro de ids, mapa de fases, agregacion y E/S de evidencia (brief F0.1 §3-§4, F0.3-0 §5.1, §13 A1)."""

import json
import math
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_MANIFEST = "dsbx-qa-manifest/1"
SCHEMA_VERDICT = "dsbx-qa-verdict/1"

SPIKE_REGISTRY = {
    "S-puente": ("s_puente_run", "s_puente_eval", None),
    "F0.3-0": ("f03_base_run", "f03_base_eval", "f03_base_mutants"),
    "S-persist": ("s_persist_run", "s_persist_eval", "s_persist_mutants"),
    "S3": ("s3_run", "s3_eval", "s3_mutants"),
    "S-cam": ("s_cam_run", "s_cam_eval", "s_cam_mutants"),
    "S-cot": ("s_cot_run", "s_cot_eval", "s_cot_mutants"),
    "S-tiempo": ("s_tiempo_run", "s_tiempo_eval", "s_tiempo_mutants"),
    "S-toma": ("s_toma_run", "s_toma_eval", "s_toma_mutants"),
    "S-perf": ("s_perf_run", "s_perf_eval", "s_perf_mutants"),
    "S-mapa": ("s_mapa_run", "s_mapa_eval", "s_mapa_mutants"),
    "F2P": ("f2p_run", "f2p_eval", "f2p_mutants"),
}

# Spikes que ademas de la sonda (--pbo) exigen el PBO del producto (--product-pbo) en retail/diag.
PRODUCT_PBO_SPIKES = frozenset({"F2P"})

SPIKES = tuple(SPIKE_REGISTRY.keys())
# Informativo: m1_gate despacha cualquier spike registrado a sus modulos (brief F0.3-0 §5.1); los esqueletos
# responden not_implemented (exit 2). Activar un spike no exige tocar esta linea.
IMPLEMENTED_SPIKES = frozenset(SPIKE_REGISTRY)


def known_spikes():
    extra = os.environ.get("DSBX_QA_TEST_UNIMPL_SPIKE", "").strip()
    if extra and extra not in SPIKES:
        return SPIKES + (extra,)
    return SPIKES


CRITERIA = (
    [f"A{i}" for i in range(1, 7)]
    + [f"B{i}" for i in range(1, 8)]
    + [f"C{i}" for i in range(1, 6)]
    + [f"D{i}" for i in range(1, 6)]
    + [f"E{i}" for i in range(1, 6)]
)

PHASES = {
    "F1": ["A1", "A5", "A6", "C4", "C5", "D2", "E1", "E2", "E3"],
    "F2": ["A1", "A2", "A3", "A4"],
    "F3": ["A2", "A3", "A4", "C1", "C2", "C3", "C4", "C5"],
    "F4": ["B1", "B2", "B3", "B4"],
    "F5": ["B4", "B5", "B6", "B7"],
    "F6": ["A6", "D1", "D2", "D3", "D4", "D5", "E1", "E2", "E3", "E4", "E5"],
}

SUITE = list(CRITERIA)

DEFAULT_HOLD_MS = 2000
DEFAULT_LEASE_MS = 3000
DEFAULT_TTL_MS = 5000
DEFAULT_RETRY_MS = 2000
DEFAULT_SEED = 20261026
DEFAULT_PEER_TIMEOUT_S = {"offline": 20, "retail": 120, "diag": 120}


def peer_timeout_s(build, given):
    if given is not None:
        return given
    return DEFAULT_PEER_TIMEOUT_S[build]


def aggregate(codes):
    if any(c == 1 for c in codes):
        return 1
    if any(c != 0 for c in codes):
        return 2
    return 0


def verdict_name(code):
    return {0: "PASA", 1: "FALLA", 2: "INCONCLUSO"}[code]


def _sanitize(obj):
    if isinstance(obj, float):
        if math.isinf(obj):
            return "inf"
        if math.isnan(obj):
            raise ValueError("nan is not a finite metric")
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


def dump_text(obj):
    return json.dumps(_sanitize(obj), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump_text(obj).encode("utf-8"))


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_bytes(repo_root, *git_args):
    """(returncode, stdout bytes) de `git -c core.autocrlf=false ...` en repo_root; (127, b"") si git no corre."""
    try:
        proc = subprocess.run(
            ["git", "-c", "core.autocrlf=false", *git_args],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
    except OSError:
        return 127, b""
    return proc.returncode, proc.stdout


def oracle_base(spike_id):
    """Nombre base del oraculo: modulo de evaluacion del registro sin `_eval` (s_persist_eval -> s_persist)."""
    eval_mod = SPIKE_REGISTRY[spike_id][1]
    return eval_mod[: -len("_eval")] if eval_mod.endswith("_eval") else eval_mod


_HEX_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def check_oracle_files(spike_id, commit, *, repo_root, qa_dir=None, collect=None):
    """Compara byte a byte los ficheros del oraculo del spike con `commit` (sin normalizar finales de linea).

    Devuelve {"ok", "commit", "files": [{"path", "blob_sha", "status"}], "problems": [...]}. Estados:
    ok / modified / deleted / added / missing_at_commit / head_differs; ademas `commit_unavailable`,
    `enumeration_failed:*`, `shadow_package:*`, `shadow_bytecode:*` y `check_error:<Tipo>`. Cualquier error da
    ok=False, nunca una excepcion. `commit` debe ser un id hexadecimal de objeto (7-40) y unívoco. No importa
    ningun modulo del spike. Si `collect` es un dict, se llena con {ruta_relativa_a_qa: bytes verificados} de los
    ficheros `.py` del oraculo (los que luego se cargan).
    """
    result = {"ok": False, "commit": commit, "files": [], "problems": []}
    try:
        _check_oracle_files(spike_id, commit, repo_root, qa_dir, collect, result)
    except Exception as exc:  # noqa: BLE001 - el guard falla cerrado, nunca con traza
        result["problems"].append(f"check_error:{type(exc).__name__}")
    result["ok"] = not result["problems"]
    return result


def _check_oracle_files(spike_id, commit, repo_root, qa_dir, collect, result):
    import fnmatch

    repo_root = Path(os.path.realpath(repo_root))
    qa_dir = Path(os.path.realpath(qa_dir if qa_dir is not None else Path(__file__).resolve().parent))
    prefix = qa_dir.relative_to(repo_root).as_posix()
    prefix = "" if prefix == "." else prefix + "/"
    base = oracle_base(spike_id)
    problems = result["problems"]

    commit_str = commit if isinstance(commit, str) else ""
    resolved = ""
    if _HEX_COMMIT_RE.match(commit_str):
        rc, out = _git_bytes(repo_root, "rev-parse", "--verify", "--quiet", commit_str + "^{commit}")
        resolved = out.decode("ascii", "replace").strip().lower()
        # una rama o un tag con nombre hexadecimal no vale: el id resuelto debe empezar por lo dado
        if rc != 0 or not resolved or not resolved.startswith(commit_str.lower()):
            resolved = ""
    if not resolved:
        problems.append("commit_unavailable")
        return
    result["commit"] = resolved
    # Un modulo del oraculo (o el runner) ya importado no esta verificado: falla cerrado.
    for mod_name in (f"{base}_eval", f"{base}_mutants", SPIKE_REGISTRY[spike_id][0]):
        if mod_name in sys.modules:
            problems.append(f"preloaded_module:{mod_name}")

    def blob_at(rev, path):
        code, data = _git_bytes(repo_root, "rev-parse", "--verify", "--quiet", f"{rev}:{path}")
        sha = data.decode("ascii", "replace").strip()
        return sha if code == 0 and sha else None

    required = [f"{prefix}{base}_eval.py", f"{prefix}{base}_mutants.py", f"{prefix}tests/test_{base}_offline.py"]
    fixtures_dir = f"{prefix}fixtures"
    pattern = f"{base}_*.json".lower()

    def census(rev, label):
        # -z: nombres delimitados por NUL y sin entrecomillar/escapar (un nombre con ñ no desaparece del censo)
        code, data = _git_bytes(repo_root, "ls-tree", "-z", "--name-only", rev, f"{fixtures_dir}/")
        if code != 0:
            problems.append(f"enumeration_failed:{label}")
            return set()
        found = set()
        for raw in data.split(b"\0"):
            name = raw.decode("utf-8", "surrogateescape").rsplit("/", 1)[-1]
            if name and fnmatch.fnmatchcase(name.lower(), pattern):
                found.add(f"{fixtures_dir}/{name}")
        return found

    in_commit = census(resolved, "commit")
    in_head = census("HEAD", "head")
    on_disk = set()
    disk_dir = qa_dir / "fixtures"
    if disk_dir.is_dir():
        for child in disk_dir.iterdir():
            if child.is_file() and fnmatch.fnmatchcase(child.name.lower(), pattern):
                on_disk.add(f"{fixtures_dir}/{child.name}")

    for name in (f"{base}_eval", f"{base}_mutants"):
        if (qa_dir / name).is_dir():
            problems.append(f"shadow_package:{prefix}{name}")
        for ext in (".pyc", ".pyd"):
            if (qa_dir / f"{name}{ext}").exists():
                problems.append(f"shadow_bytecode:{prefix}{name}{ext}")

    paths = list(required) + sorted((in_commit | in_head | on_disk) - set(required))
    for path in paths:
        entry = {"path": path, "blob_sha": blob_at(resolved, path), "status": "ok"}
        disk_file = repo_root / path
        if entry["blob_sha"] is None:
            if path in required:
                entry["status"] = "missing_at_commit"
            elif path in on_disk:
                entry["status"] = "added"  # fixture del patron en disco y no en el commit
            else:
                entry["status"] = "head_differs"  # solo en HEAD
        elif not disk_file.is_file():
            entry["status"] = "deleted"
        else:
            code, blob = _git_bytes(repo_root, "cat-file", "blob", entry["blob_sha"])
            disk_bytes = disk_file.read_bytes()
            if code != 0 or blob != disk_bytes:
                entry["status"] = "modified"
            elif blob_at("HEAD", path) != entry["blob_sha"]:
                entry["status"] = "head_differs"
            elif collect is not None and path in required[:2]:
                collect[path[len(prefix):]] = disk_bytes
        if entry["status"] != "ok":
            problems.append(f"{entry['status']}:{path}")
        result["files"].append(entry)


def load_verified_oracle(spike_id, collect, *, qa_dir):
    """Carga `<base>_eval` y `<base>_mutants` desde los bytes verificados (sin .pyc, sin paquetes) en sys.modules.

    Registra los dos modulos nuevos (vacios) antes de ejecutar ninguno y ejecuta mutants y luego eval, para que un
    import cruzado resuelva siempre al verificado.
    """
    import types

    qa_dir = Path(os.path.realpath(qa_dir if qa_dir is not None else Path(__file__).resolve().parent))
    base = oracle_base(spike_id)
    order = (f"{base}_mutants", f"{base}_eval")
    staged = []
    for name in order:
        path = str(qa_dir / f"{name}.py")
        module = types.ModuleType(name)
        module.__file__ = path
        staged.append((name, module, compile(collect[f"{name}.py"], path, "exec")))
    for name, module, _code in staged:
        sys.modules[name] = module
    try:
        for _name, module, code in staged:
            exec(code, module.__dict__)  # noqa: S102 - bytes ya verificados contra el commit congelado
    except BaseException:
        for name, _module, _code in staged:
            sys.modules.pop(name, None)
        raise


def git_harness(repo_root=None):
    harness = {
        "git_dirty": None,
        "git_head": None,
        "platform": platform.platform(),
        "python": platform.python_version(),
    }
    cwd = Path(repo_root) if repo_root is not None else None
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if top.returncode != 0 or not top.stdout.strip():
            return harness
        toplevel = Path(top.stdout.strip())
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=toplevel,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if head.returncode != 0:
            return harness
        dirty = subprocess.run(
            [
                "git",
                "status",
                "--porcelain",
                "--",
                ".",
                ":(exclude)DayZSandbox_dev/evidence",
            ],
            cwd=toplevel,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if dirty.returncode != 0:
            return harness
    except OSError:
        return harness
    harness["git_head"] = head.stdout.strip() or None
    harness["git_dirty"] = bool(dirty.stdout.strip())
    return harness


def make_manifest(kind, ident, args, argv, started, ended, port=None, run_id=None):
    fault = getattr(args, "fault", None)
    params = {
        "hold_ms": getattr(args, "hold_ms", DEFAULT_HOLD_MS),
        "lease_ms": getattr(args, "lease_ms", DEFAULT_LEASE_MS),
        "port": port,
        "retry_ms": getattr(args, "retry_ms", DEFAULT_RETRY_MS),
        "seed": getattr(args, "seed", DEFAULT_SEED),
        "ttl_ms": getattr(args, "ttl_ms", DEFAULT_TTL_MS),
    }
    if run_id is not None:
        params["run_id"] = run_id
    return {
        "argv": list(argv),
        "both": bool(getattr(args, "both", False)),
        "build": args.build,
        "ended_utc": ended,
        "faults": [fault] if fault else [],
        "harness": git_harness(),
        "id": ident,
        "kind": kind,
        "params": params,
        "schema": SCHEMA_MANIFEST,
        "started_utc": started,
    }


def make_verdict(ident, code, checks=None, metrics=None, reasons=None, error=None, members=None):
    body = {
        "checks": [] if checks is None else checks,
        "error": error,
        "exit_code": code,
        "id": ident,
        "metrics": {} if metrics is None else metrics,
        "reasons": [] if reasons is None else reasons,
        "schema": SCHEMA_VERDICT,
        "verdict": verdict_name(code),
    }
    if members is not None:
        body["members"] = members
    return body


def error_obj(exc):
    import traceback

    return {
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(exc)),
        "type": type(exc).__name__,
    }
