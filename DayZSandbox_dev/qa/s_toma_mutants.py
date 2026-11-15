"""Mutantes y tests de arnes de S-toma (brief S-toma §6)."""

EXPECTED_MUTANTS = {
    "despachar_desfasado": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-01"],
        "allowed_non_pass": {},
    },
    "jitter_gt_100ms": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-01"],
        "allowed_non_pass": {},
    },
    "fase_muestreo_desplazada": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-01"],
        "allowed_non_pass": {},
    },
    "peer_reiniciado_en_toma": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-02"],
        "allowed_non_pass": {
            "TOM-01": ["missing"],
            "TOM-05": ["missing", "fail"],
        },
    },
    "retraso_lectura_tecla_gt_1s": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-02"],
        "allowed_non_pass": {},
    },
    "gesto_pendiente_no_cancelado": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-02"],
        "allowed_non_pass": {},
    },
    "conflicto_tecla_ignorado": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-03"],
        "allowed_non_pass": {},
    },
    "proteccion_retenida_al_salir": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-04"],
        "allowed_non_pass": {},
    },
    "traza_cam_incompleta": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-05"],
        "allowed_non_pass": {},
    },
    "cam_desviada_b6": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-05"],
        "allowed_non_pass": {},
    },
    "go_tardio_reactiva_cam": {
        "expected_exit_code": 1,
        "must_fail_checks": ["TOM-07"],
        "allowed_non_pass": {},
    },
}

EXPECTED_HARNESS_TESTS = {}
