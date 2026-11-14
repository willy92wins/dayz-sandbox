"""Declaracion de mutantes y pruebas del arnes de F0.3-0 (brief §5.2, §14 F02-H4)."""

EXPECTED_MUTANTS = {
    "ignore_stop": {
        "expected_exit_code": 1,
        "must_fail_checks": ["BASE-03"],
        "allowed_non_pass": {},
    },
    "freeze_on_wait": {
        "expected_exit_code": 1,
        "must_fail_checks": ["BASE-08"],
        "allowed_non_pass": {},
    },
    "defer_cleanup": {
        "expected_exit_code": 1,
        "must_fail_checks": ["BASE-08"],
        "allowed_non_pass": {},
    },
    "ignore_deadman": {
        "expected_exit_code": 1,
        "must_fail_checks": ["BASE-11"],
        "allowed_non_pass": {},
    },
    "skip_send": {
        "expected_exit_code": 1,
        "must_fail_checks": ["BASE-11"],
        "allowed_non_pass": {},
    },
}

EXPECTED_HARNESS_TESTS = {
    "probe-budget": {
        "expected_exit_code": 2,
        "expected_reason": "callback_budget_exhausted",
        "must_pass_checks": ["BASE-12"],
    },
}
