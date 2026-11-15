"""CLI del arnes M1 (brief F0.1 §3, F0.3-0 §5.1-§5.2). Sale 0 PASA, 1 FALLA, 2 INCONCLUSO."""

import argparse
import importlib
import subprocess
import sys
import traceback
from pathlib import Path

import gate_core


def build_parser():
    parser = argparse.ArgumentParser(prog="qa/m1_gate.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    spike = sub.add_parser("spike")
    spike.add_argument("id")
    _common(spike)
    spike.add_argument("--evaluate-only", action="store_true")
    spike.add_argument("--server-profile")
    spike.add_argument("--client-profile")
    spike.add_argument("--pbo", default=None)
    spike.add_argument("--product-pbo", default=None)
    spike.add_argument("--oracle-commit", default=None)
    spike.add_argument("--part", default="all")
    spike.add_argument("--peer-timeout", type=float, default=None)
    spike.add_argument("--hold-ms", type=int, default=gate_core.DEFAULT_HOLD_MS)
    spike.add_argument("--lease-ms", type=int, default=gate_core.DEFAULT_LEASE_MS)
    spike.add_argument("--ttl-ms", type=int, default=gate_core.DEFAULT_TTL_MS)
    spike.add_argument("--retry-ms", type=int, default=gate_core.DEFAULT_RETRY_MS)
    spike.add_argument("--seed", type=int, default=gate_core.DEFAULT_SEED)
    spike.add_argument("--fault", default=None)

    criterion = sub.add_parser("criterion")
    criterion.add_argument("id")
    _common(criterion)
    _profiles(criterion)

    phase = sub.add_parser("phase")
    phase.add_argument("id")
    _common(phase)
    _profiles(phase)

    suite = sub.add_parser("suite")
    _common(suite)
    _profiles(suite)
    return parser


def _common(parser):
    parser.add_argument("--build", required=True, choices=("offline", "retail", "diag"))
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--both", action="store_true")


def _profiles(parser):
    parser.add_argument("--server-profile")
    parser.add_argument("--client-profile")


def _valid_parts_for_spike(spike_id: str) -> set[str]:
    if spike_id not in gate_core.SPIKE_REGISTRY:
        return {"all"}
    _run_mod, _eval_mod, mut_mod_name = gate_core.SPIKE_REGISTRY[spike_id]
    if not mut_mod_name:
        return {"all"}
    mut_mod = importlib.import_module(mut_mod_name)
    parts = {"all", "run"}
    for mname in getattr(mut_mod, "EXPECTED_MUTANTS", {}):
        parts.add(f"mut-{mname}")
    for hname in getattr(mut_mod, "EXPECTED_HARNESS_TESTS", {}):
        parts.add(str(hname))
    return parts


def validate(parser, args):
    if args.cmd == "spike" and args.id not in gate_core.known_spikes():
        parser.error(f"unknown spike {args.id}")
    if args.cmd == "criterion" and args.id not in gate_core.CRITERIA:
        parser.error(f"unknown criterion {args.id}")
    if args.cmd == "phase" and args.id not in gate_core.PHASES:
        parser.error(f"unknown phase {args.id}")
    fault = getattr(args, "fault", None)
    if fault and args.build != "offline":
        parser.error("--fault requires --build offline")
    if hasattr(args, "hold_ms") and args.hold_ms >= args.lease_ms:
        parser.error("--hold-ms must be < --lease-ms")
    if args.cmd == "spike":
        part = getattr(args, "part", "all") or "all"
        if part != "all":
            if args.id == "S-puente":
                parser.error("--part is not supported for S-puente")
            if getattr(args, "oracle_commit", None) is None:  # con oraculo, main() valida --part tras comprobarlo
                valid_parts = _valid_parts_for_spike(args.id)
                if part not in valid_parts:
                    parser.error(f"unknown --part {part} for spike {args.id}")
    if args.cmd == "spike":
        if getattr(args, "oracle_commit", None) is not None:
            entry = gate_core.SPIKE_REGISTRY.get(args.id)
            if entry is None or not entry[2]:
                parser.error(f"--oracle-commit is not supported for spike {args.id}")
        product = getattr(args, "product_pbo", None)
        if product is not None:
            product_path = Path(product)
            if not product_path.is_file() or product_path.suffix.lower() != ".pbo":
                parser.error("--product-pbo must point to an existing .pbo file")
    if args.build in ("retail", "diag") and not getattr(args, "evaluate_only", False):
        server = getattr(args, "server_profile", None)
        client = getattr(args, "client_profile", None)
        if not server or not client:
            parser.error("retail/diag require --server-profile and --client-profile")
        if not Path(server).is_dir() or not Path(client).is_dir():
            parser.error("profile folders must exist")
        if args.cmd == "spike" and args.id != "S-puente":
            pbo = getattr(args, "pbo", None)
            if not pbo:
                parser.error("retail/diag F0.3 spikes require --pbo")
            pbo_path = Path(pbo)
            if not pbo_path.is_file() or pbo_path.suffix.lower() != ".pbo":
                parser.error("--pbo must point to an existing .pbo file")
            if args.id in gate_core.PRODUCT_PBO_SPIKES and not getattr(args, "product_pbo", None):
                parser.error(f"retail/diag {args.id} requires --product-pbo")
    if hasattr(args, "peer_timeout"):
        args.peer_timeout = gate_core.peer_timeout_s(args.build, args.peer_timeout)


def _oracle_context():
    """(raiz del repo git, carpeta qa) para la comprobacion del oraculo; las pruebas lo parchean con un repo temporal."""
    qa_dir = Path(__file__).resolve().parent
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(qa_dir), capture_output=True, text=True, check=False
        )
        root = top.stdout.strip() if top.returncode == 0 else ""
    except OSError:
        root = ""
    return (Path(root) if root else qa_dir.parent), qa_dir


def _has_valid_f03_parts(evidence: Path, part: str) -> bool:
    if not evidence.is_dir():
        return False
    if part != "all":
        pdir = evidence / part
        return pdir.is_dir() and (pdir / "manifest.json").is_file() and (pdir / "samples").is_dir()
    for child in evidence.iterdir():
        if child.is_dir() and (child / "manifest.json").is_file() and (child / "samples").is_dir():
            return True
    return False


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        oracle_check = None
        if args.cmd == "spike" and args.oracle_commit is not None:
            entry = gate_core.SPIKE_REGISTRY.get(args.id)
            if entry is not None and entry[2]:
                # Antes de validate() y de importar nada del spike: un modulo modificado no puede alterar la comprobacion.
                repo_root, qa_dir = _oracle_context()
                oracle_check = gate_core.check_oracle_files(args.id, args.oracle_commit, repo_root=repo_root, qa_dir=qa_dir)
        validate(parser, args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0

    evidence = Path(args.evidence)
    part = getattr(args, "part", "all") or "all"
    is_f03_spike = args.cmd == "spike" and args.id != "S-puente"
    accepted = False
    try:
        if getattr(args, "evaluate_only", False):
            if is_f03_spike:
                if not _has_valid_f03_parts(evidence, part):
                    return 2
            else:
                manifest = evidence / "manifest.json"
                samples = evidence / "samples"
                if not (evidence.is_dir() and manifest.is_file() and samples.is_dir()):
                    return 2
        else:
            if is_f03_spike and part != "all":
                part_dir = evidence / part
                if part_dir.exists():
                    if not part_dir.is_dir() or any(part_dir.iterdir()):
                        return 2
                else:
                    evidence.mkdir(parents=True, exist_ok=True)
            else:
                if evidence.exists():
                    if not evidence.is_dir() or any(evidence.iterdir()):
                        return 2
                else:
                    evidence.mkdir(parents=True)
        accepted = True
        if args.cmd == "spike" and getattr(args, "oracle_commit", None) is not None:
            # Antes de importar o correr nada del spike: el oraculo debe ser byte a byte el del commit congelado.
            check = oracle_check
            gate_core.write_json(evidence / "oracle_check.json", check)
            if not check["ok"]:
                gate_core.write_json(
                    evidence / "verdict.json",
                    gate_core.make_verdict(args.id, 2, reasons=["oracle_modified"]),
                )
                return 2
            args.oracle_commit = check["commit"]
            if part != "all" and part not in _valid_parts_for_spike(args.id):
                return 2
        return execute(args, evidence, argv)
    except Exception as exc:
        if accepted and evidence.is_dir():
            try:
                gate_core.write_json(
                    evidence / "verdict.json",
                    gate_core.make_verdict(
                        getattr(args, "id", args.cmd),
                        2,
                        reasons=[],
                        error=gate_core.error_obj(exc),
                    ),
                )
            except Exception:
                traceback.print_exc()
            return 2
        traceback.print_exc()
        return 2


def execute(args, evidence, argv):
    if args.cmd == "spike":
        return _spike(args, evidence, argv)
    if args.cmd == "criterion":
        return _not_implemented(args, evidence, argv, "criterion", args.id)
    if args.cmd == "phase":
        return _group(args, evidence, argv, args.id, gate_core.PHASES[args.id])
    return _group(args, evidence, argv, "suite", gate_core.SUITE)


def _spike(args, evidence, argv):
    if args.id == "S-puente" and not args.both:
        _write_run(evidence, "spike", args.id, args, argv, 2, ["requires_both"])
        return 2
    if args.id == "F0.3-0" and not args.both and not args.evaluate_only:
        _write_run(evidence, "spike", args.id, args, argv, 2, ["requires_both"])
        return 2
    # Brief F0.3-0 §5.1: todo spike de SPIKE_REGISTRY se despacha a SU run y, con --evaluate-only, a SU evaluate y a
    # su EXPECTED_MUTANTS. Los esqueletos responden ellos mismos not_implemented (exit 2), asi que un spike se activa
    # desde su propio write-set sin tocar el nucleo. Solo un id fuera del registro cae aqui en not_implemented.
    if args.id not in gate_core.SPIKE_REGISTRY:
        return _not_implemented(args, evidence, argv, "spike", args.id)

    run_mod_name, eval_mod_name, _mut_mod_name = gate_core.SPIKE_REGISTRY[args.id]
    if args.id == "S-puente":
        if args.evaluate_only:
            eval_fn = importlib.import_module(eval_mod_name).evaluate
            verdict = eval_fn(evidence)
            gate_core.write_json(evidence / "verdict.json", verdict)
            return int(verdict["exit_code"])
        run_fn = importlib.import_module(run_mod_name).run
        return int(run_fn(args, evidence, argv))

    if args.evaluate_only:
        eval_fn = importlib.import_module(eval_mod_name).evaluate
        f03_common = importlib.import_module("f03_common")
        part = getattr(args, "part", "all") or "all"
        if part != "all":
            pdir = evidence / part
            pv = eval_fn(pdir)
            gate_core.write_json(pdir / "verdict.json", pv)
        else:
            for child in sorted(evidence.iterdir()):
                if child.is_dir() and (child / "manifest.json").is_file() and (child / "samples").is_dir():
                    pv = eval_fn(child)
                    gate_core.write_json(child / "verdict.json", pv)
        agg = f03_common.aggregate_spike(evidence, args.id)
        return int(agg["exit_code"])

    run_fn = importlib.import_module(run_mod_name).run
    return int(run_fn(args, evidence, argv))


def _not_implemented(args, evidence, argv, kind, ident):
    _write_run(evidence, kind, ident, args, argv, 2, ["not_implemented"])
    return 2


def _write_run(directory, kind, ident, args, argv, code, reasons):
    started = gate_core.utc_now()
    gate_core.write_json(
        Path(directory) / "manifest.json",
        gate_core.make_manifest(kind, ident, args, argv, started, gate_core.utc_now()),
    )
    gate_core.write_json(
        Path(directory) / "verdict.json",
        gate_core.make_verdict(ident, code, reasons=reasons),
    )


def _group(args, evidence, argv, ident, members):
    started = gate_core.utc_now()
    rows = []
    codes = []
    for cid in members:
        sub = evidence / cid
        sub.mkdir(parents=True, exist_ok=True)
        code = _not_implemented(args, sub, argv, "criterion", cid)
        codes.append(code)
        rows.append({"exit_code": code, "id": cid, "verdict": gate_core.verdict_name(code)})
    agg = gate_core.aggregate(codes)
    gate_core.write_json(
        evidence / "manifest.json",
        gate_core.make_manifest(args.cmd, ident, args, argv, started, gate_core.utc_now()),
    )
    reasons = ["not_implemented"] if agg != 0 else []
    gate_core.write_json(
        evidence / "verdict.json",
        gate_core.make_verdict(ident, agg, reasons=reasons, members=rows),
    )
    return agg


if __name__ == "__main__":
    sys.exit(main())
