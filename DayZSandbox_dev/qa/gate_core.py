"""Registro de ids, mapa de fases, agregacion y E/S de evidencia (brief F0.1 §3-§4, F0.3-0 §5.1, §13 A1)."""

import json
import math
import os
import platform
import subprocess
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
}

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
