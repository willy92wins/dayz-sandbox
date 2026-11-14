"""Evaluador esqueleto de S-toma (brief F0.3-0 §5.1)."""

import gate_core

SPIKE_ID = "S-toma"


def evaluate(_part_dir):
    return gate_core.make_verdict(SPIKE_ID, 2, reasons=["not_implemented"])
