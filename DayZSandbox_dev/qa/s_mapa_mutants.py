"""Tabla de expectativas para los mutantes de S-mapa.

Este modulo lo importa ``f03_common.aggregate_spike`` y el arnes de tests,
NUNCA ``s_mapa_eval.py`` (que permanece ciego a nombres de mutantes y fallos).
"""

from __future__ import annotations


EXPECTED_MUTANTS: dict[str, dict[str, object]] = {
    "external_tiles": {
        "expected_exit_code": 1,
        "must_fail_checks": ["MAP-01"],
        "allowed_non_pass": {},
    },
    "flip_v_matrix": {
        "expected_exit_code": 1,
        "must_fail_checks": ["MAP-02"],
        "allowed_non_pass": {"MAP-03": ["fail"]},
    },
    "verify_drift_25m": {
        "expected_exit_code": 1,
        "must_fail_checks": ["MAP-02"],
        "allowed_non_pass": {"MAP-03": ["fail"]},
    },
    "elevated_not_rejected": {
        "expected_exit_code": 1,
        "must_fail_checks": ["MAP-06", "MAP-07"],
        "allowed_non_pass": {},
    },
}


EXPECTED_HARNESS_TESTS: dict[str, dict[str, object]] = {}
