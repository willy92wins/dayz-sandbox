"""Mutant catalog for spike S-perf (F0.3 performance baseline and scaling).

Defines ``EXPECTED_MUTANTS`` consumed by ``f03_common.aggregate_spike`` and
checked by ``test_probe_static.check_12_blind_evaluators``.
Each entry specifies:
- ``expected_exit_code``: expected evaluator verdict exit code (1 = FALLA).
- ``must_fail_checks``: checks that MUST be in state ``"fail"``.
- ``allowed_non_pass``: checks allowed to be non-``"pass"`` as causal downstream
  consequences of the injected fault or unexecuted steps in partial mutant runs
  (disjoint from ``must_fail_checks``; see S-perf brief §7).
"""

from __future__ import annotations

EXPECTED_MUTANTS = {
    "client_fps": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-01"],
        "allowed_non_pass": ["PRF-02", "PRF-03", "PRF-04", "PRF-05", "PRF-06"],
    },
    "idle_actor": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": ["PRF-03", "PRF-04", "PRF-05", "PRF-06"],
    },
    "pending_emote": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": ["PRF-03", "PRF-04", "PRF-05", "PRF-06"],
    },
    "early_burst_idle": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": ["PRF-03", "PRF-04", "PRF-05", "PRF-06"],
    },
    "burst_per_quarter": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-02"],
        "allowed_non_pass": ["PRF-03", "PRF-04", "PRF-05", "PRF-06"],
    },
    "single_sample": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-03"],
        "allowed_non_pass": ["PRF-02", "PRF-04", "PRF-05", "PRF-06"],
    },
    "short_window": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-03"],
        "allowed_non_pass": ["PRF-02", "PRF-04", "PRF-05", "PRF-06"],
    },
    "clustered_samples": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-03"],
        "allowed_non_pass": ["PRF-02", "PRF-04", "PRF-05", "PRF-06"],
    },
    "desync_fps": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-04"],
        "allowed_non_pass": ["PRF-02", "PRF-03", "PRF-05", "PRF-06"],
    },
    "overload_floor": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-05"],
        "allowed_non_pass": ["PRF-02", "PRF-03", "PRF-04", "PRF-06"],
    },
    "accept_budget_exceeded": {
        "expected_exit_code": 1,
        "must_fail_checks": ["PRF-06"],
        "allowed_non_pass": ["PRF-02", "PRF-03", "PRF-04", "PRF-05"],
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
