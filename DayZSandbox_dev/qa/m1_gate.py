"""CLI del arnes M1 (brief F0.1 §3). Sale 0 PASA, 1 FALLA, 2 INCONCLUSO."""

import argparse
import importlib
import sys
import traceback
from pathlib import Path

import gate_core
from s_puente_eval import evaluate


def build_parser():
    parser = argparse.ArgumentParser(prog="qa/m1_gate.py")
    sub = parser.add_subparsers(dest="cmd", required=True)

    spike = sub.add_parser("spike")
    spike.add_argument("id")
    _common(spike)
    spike.add_argument("--evaluate-only", action="store_true")
    spike.add_argument("--server-profile")
    spike.add_argument("--client-profile")
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


def validate(parser, args):
    if args.cmd == "spike" and args.id not in gate_core.SPIKES:
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
    if args.build in ("retail", "diag"):
        server = getattr(args, "server_profile", None)
        client = getattr(args, "client_profile", None)
        if not server or not client:
            parser.error("retail/diag require --server-profile and --client-profile")
        if not Path(server).is_dir() or not Path(client).is_dir():
            parser.error("profile folders must exist")
    if hasattr(args, "peer_timeout"):
        args.peer_timeout = gate_core.peer_timeout_s(args.build, args.peer_timeout)


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        validate(parser, args)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0

    evidence = Path(args.evidence)
    accepted = False
    try:
        if getattr(args, "evaluate_only", False):
            manifest = evidence / "manifest.json"
            samples = evidence / "samples"
            if not (evidence.is_dir() and manifest.is_file() and samples.is_dir()):
                return 2
        else:
            if evidence.exists():
                if not evidence.is_dir() or any(evidence.iterdir()):
                    return 2
            else:
                evidence.mkdir(parents=True)
        accepted = True
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
    if args.id not in gate_core.IMPLEMENTED_SPIKES:
        return _not_implemented(args, evidence, argv, "spike", args.id)
    if args.evaluate_only:
        verdict = evaluate(evidence)
        gate_core.write_json(evidence / "verdict.json", verdict)
        return int(verdict["exit_code"])
    run_s_puente = importlib.import_module("s_puente_run").run
    return int(run_s_puente(args, evidence, argv))


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
