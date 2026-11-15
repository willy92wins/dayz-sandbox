"""Declaracion de mutantes de S3 (brief 2026-11-14-m1-f0.3-s3-brief.md §6).

Cada mutante inyecta un defecto concreto en una parte ``mut-<nombre>`` y debe
poner en ``fail`` exactamente las comprobaciones de ``must_fail_checks``. Las
comprobaciones de pasos que esa parte no ejecuta quedan autorizadas en
``allowed_non_pass`` como ``missing``. ``S3-00`` (handshake) y ``S3-10``
(fixtures) se ejecutan en toda parte y deben salir en ``pass``.
"""

CHECK_IDS = tuple(f"S3-{i:02d}" for i in range(0, 13))
_ALWAYS_EXECUTED = frozenset({"S3-00", "S3-10"})


def _allowed(must_fail):
    must = set(must_fail)
    return {
        cid: ["missing"]
        for cid in CHECK_IDS
        if cid not in must and cid not in _ALWAYS_EXECUTED
    }


EXPECTED_MUTANTS = {
    "roam_out_of_radius": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-05"],
        "allowed_non_pass": _allowed(["S3-05"]),
    },
    "roam_stand_still": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-05"],
        "allowed_non_pass": _allowed(["S3-05"]),
    },
    "fsm_is_final_as_reached": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-06"],
        "allowed_non_pass": _allowed(["S3-06"]),
    },
    "wrong_emote_cmd": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-04"],
        "allowed_non_pass": _allowed(["S3-04"]),
    },
    "stale_callback_contamination": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-08"],
        "allowed_non_pass": _allowed(["S3-08"]),
    },
    "canceled_emote_as_done": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-08"],
        "allowed_non_pass": _allowed(["S3-08"]),
    },
    "late_emote_after_timeout": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-09"],
        "allowed_non_pass": _allowed(["S3-09"]),
    },
    "no_clear_on_stop_after_start": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-09"],
        "allowed_non_pass": _allowed(["S3-09"]),
    },
    "combat_emote_as_done": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-07"],
        "allowed_non_pass": _allowed(["S3-07"]),
    },
    "extra_default_gear": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-01"],
        "allowed_non_pass": _allowed(["S3-01"]),
    },
    "props_before_actor_check": {
        "expected_exit_code": 1,
        "must_fail_checks": ["S3-12"],
        "allowed_non_pass": _allowed(["S3-12"]),
    },
}

EXPECTED_HARNESS_TESTS = {}
