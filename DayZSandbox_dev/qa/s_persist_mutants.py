"""Expected mutant and negative-control catalog for S-persist."""

from __future__ import annotations

EXPECTED_MUTANTS = {
    "unprotected_leak": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PER-08"],
        "allowed_non_pass": {},
    },
    "foreign_wiped": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PER-04", "PER-05"],
        "allowed_non_pass": {},
    },
}

EXPECTED_HARNESS_TESTS = {}
