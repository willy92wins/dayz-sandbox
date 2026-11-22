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
        "must_fail_detail": {"CAM-02": "p0_inactive"},
    },
    "swap_axes": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-02"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_swap_axes"),
        # N1: se inyecta al reaplicar P_roll; efecto >> tolerancia 0,5.
        "inject_on": "scam_pose_apply:P_roll",
        "must_fail_detail": {"CAM-02": "p_roll_theta_deg"},
    },
    "long_arc": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-05"],
        "allowed_non_pass": {"CAM-04": ["fail"]},
        "qa_fault": wire.format_qa_fault("cam_long_arc"),
        "must_fail_detail": {"CAM-05": "short_arc_yaw_deg"},
    },
    "frozen_fov": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-04", "CAM-05"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_frozen_fov"),
        "must_fail_detail": {"CAM-05": "fov_excursion_rad"},
    },
    "path_jump": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-03"],
        "allowed_non_pass": {"CAM-04": ["fail"]},
        "qa_fault": wire.format_qa_fault("cam_path_jump"),
        "must_fail_detail": {"CAM-03": "path_catmull_scripted_ref_err_m=2.000"},
    },
    "late_finish": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-04"],
        "allowed_non_pass": {"CAM-03": ["fail"]},
        "qa_fault": wire.format_qa_fault("cam_late_finish"),
        "must_fail_detail": {"CAM-04": "path_catmull_scripted_finish_ms=7000.0"},
    },
    "ignore_focus_keys": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-08"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_ignore_focus_keys"),
        "must_fail_detail": {"CAM-08": "sent_dist_row_1"},
    },
    "dof_off": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-07"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_dof_off"),
        "must_fail_detail": {"CAM-07": "dof_not_supported_or_identical_frames"},
    },
    "hud_leak": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-09"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_force_quickbar"),
        "must_fail_detail": {"CAM-09": "qb_vis_row_108"},
    },
    "hud_restore_corrupt": {
        "expected_exit_code": 1,
        "must_fail_checks": ["CAM-09"],
        "allowed_non_pass": {},
        "qa_fault": wire.format_qa_fault("cam_restore_showhud"),
        "must_fail_detail": {"CAM-09": "flags_not_restored"},
    },
}

EXPECTED_HARNESS_TESTS = {}
