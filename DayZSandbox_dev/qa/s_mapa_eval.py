"""Evaluador esqueleto de S-mapa (brief F0.3-0 §5.1)."""

import gate_core

SPIKE_ID = "S-mapa"


def evaluate(_part_dir):
    return gate_core.make_verdict(SPIKE_ID, 2, reasons=["not_implemented"])
