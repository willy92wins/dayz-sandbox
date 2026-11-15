"""Mutant catalog for spike S-perf (F0.3 performance baseline and scaling).

Defines ``EXPECTED_MUTANTS`` consumed by ``f03_common.aggregate_spike`` and
checked by ``test_probe_static.check_12_blind_evaluators``.
Each entry specifies:
- ``expected_exit_code``: expected evaluator verdict exit code (1 = FALLA).
- ``must_fail_checks``: checks that MUST be in state ``"fail"``.
- ``allowed_non_pass``: ``{check_id: [states]}`` in the format that
  ``f03_common.aggregate_spike`` reads (``allowed_non_pass.get(cid)``): the non-pass
  states a check may show besides the ones in ``must_fail_checks``, as causal
  downstream consequences of the injected fault or of unexecuted steps in the partial
  mutant runs (keys disjoint from ``must_fail_checks``; S-perf brief §7).
"""

from __future__ import annotations

EXPECTED_MUTANTS = {
    "client_fps": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-01"],
        "allowed_non_pass": {
            "PRF-02": ["missing"],
            "PRF-03": ["missing"],
            "PRF-04": ["missing"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "idle_actor": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": {
            "PRF-03": ["missing"],
            "PRF-04": ["missing"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "pending_emote": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": {
            "PRF-03": ["missing"],
            "PRF-04": ["missing"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "early_burst_idle": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": {
            "PRF-03": ["missing"],
            "PRF-04": ["missing"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "burst_per_quarter": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": {
            "PRF-03": ["missing"],
            "PRF-04": ["missing"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "single_sample": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-03"],
        "allowed_non_pass": {
            "PRF-02": ["missing", "fail"],
            "PRF-04": ["missing", "fail"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "short_window": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-03"],
        "allowed_non_pass": {
            "PRF-02": ["missing", "fail"],
            "PRF-04": ["missing", "fail"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "clustered_samples": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-03"],
        "allowed_non_pass": {
            "PRF-02": ["missing", "fail"],
            "PRF-04": ["missing", "fail"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "desync_fps": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-04"],
        "allowed_non_pass": {
            "PRF-02": ["missing"],
            "PRF-03": ["missing"],
            "PRF-05": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "overload_floor": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-05"],
        "allowed_non_pass": {
            "PRF-02": ["missing"],
            "PRF-03": ["missing"],
            "PRF-04": ["missing"],
            "PRF-06": ["missing"],
        },
    },
    "accept_budget_exceeded": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-06"],
        "allowed_non_pass": {
            "PRF-02": ["missing"],
            "PRF-03": ["missing"],
            "PRF-04": ["missing"],
            "PRF-05": ["missing"],
        },
    },
}

EXPECTED_HARNESS_TESTS = {}

MUTANT_QA_FAULTS = {
    "client_fps": "allow_client_perf",
    "idle_actor": "idle_actor",
    "pending_emote": "pending_emote",
    "early_burst_idle": "early_burst_idle",
    "burst_per_quarter": "burst_per_quarter",
    "single_sample": "single_sample",
    "short_window": "short_window",
    "clustered_samples": "clustered_samples",
    "desync_fps": "desync_fps",
    "overload_floor": "overload_floor",
    "accept_budget_exceeded": "accept_budget_exceeded",
}
