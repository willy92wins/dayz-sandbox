"""Mutantes de S-cam (brief S-cam §6, F0.3-0 §5.2).

Cada entrada declara ``expected_exit_code``, ``must_fail_checks``,
``allowed_non_pass`` y el codigo ``qa_fault`` de ancho fijo 24 que el runner
inyecta con ``f03_common.issue_one`` (``wire.format_qa_fault``).
"""

import wire

EXPECTED_MUTANTS = {
    "inactive_cam": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-02"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_no_activate"),
    },
    "swap_axes": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-02"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_swap_axes"),
    },
    "long_arc": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-05"],
        "allowed_non_pass": {"CAM-04": ["fail"]},
        "qa_fault": wire.format_qa_fault("cam_long_arc"),
    },
    "frozen_fov": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-04", "CAM-05"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_frozen_fov"),
    },
    "path_jump": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-03"],
        "allowed_non_pass": {"CAM-04": ["fail"]},
        "qa_fault": wire.format_qa_fault("cam_path_jump"),
    },
    "late_finish": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-04"],
        "allowed_non_pass": {"CAM-03": ["fail"]},
        "qa_fault": wire.format_qa_fault("cam_late_finish"),
    },
    "ignore_focus_keys": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-08"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_ignore_focus_keys"),
    },
    "dof_off": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-07"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_dof_off"),
    },
    "hud_leak": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-09"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_force_quickbar"),
    },
    "hud_restore_corrupt": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-09"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_restore_showhud"),
    },
}

EXPECTED_HARNESS_TESTS = {}
