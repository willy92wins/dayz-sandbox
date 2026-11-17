"""Runner esqueleto de F2P (brief F0.3-0 §5.1)."""

from pathlib import Path
import gate_core

SPIKE_ID = "F2P"


def run(args, evidence, argv):
    started = gate_core.utc_now()
    ev_dir = Path(evidence)
    gate_core.write_json(
        ev_dir / "manifest.json",
        gate_core.make_manifest("spike", SPIKE_ID, args, argv, started, gate_core.utc_now()),
    )
    gate_core.write_json(
        ev_dir / "verdict.json",
        gate_core.make_verdict(SPIKE_ID, 2, reasons=["not_implemented"]),
    )
    return 2
