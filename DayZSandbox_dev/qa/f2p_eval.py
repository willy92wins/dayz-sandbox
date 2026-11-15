"""Evaluador esqueleto de F2P (brief F0.3-0 §5.1)."""

import gate_core

SPIKE_ID = "F2P"


def evaluate(_part_dir):
    return gate_core.make_verdict(SPIKE_ID, 2, reasons=["not_implemented"])
