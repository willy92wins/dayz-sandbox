"""Oráculo ciego de S-cam (brief S-cam §3, §5, §7; F0.3-0 §5.1, §5.2, §6.1(12)).

Decide solo con lecturas crudas de ``part_dir/samples/``, con las fixtures
``qa/fixtures/s_cam_paths.json`` y ``qa/fixtures/s_cam_rois.json``, y con los
campos permitidos de ``part_dir/manifest.json`` (``build``, ``both``, ``id``,
``kind``, ``params``, ``identity``, ``schema``). No usa etiquetas calculadas por
la sonda ni el nombre de la parte.

Esquema de evidencias
=====================

``manifest.json`` (campos permitidos)
-------------------------------------
``build``: ``"offline"|"retail"|"diag"``; ``both``: bool; ``id``: str;
``kind``: str; ``schema``: str; ``params``: dict con ``seed``, ``ttl_ms``,
``lease_ms``, ``hold_ms``, ``retry_ms``, ``port``; ``identity``: dict con
``git_head``, ``git_dirty``, ``peer_builds``, ``probe_stamp`` y ``params``
(``wire_cap``, ``lease_ms``).

``samples/scenario.jsonl``
--------------------------
Una fila JSON por evento del arnés. Campos comunes: ``ev`` (str),
``phase`` (``"SCAM-S0"``..``"SCAM-S5"``), ``step`` (str único dentro de la
fase), ``t_ms``/``h_ms`` (ms, reloj de pared del arnés, de
``f03_common.PartContext.record_scenario``). Las lecturas se copian de
``wire.unpack_payload(res.read)`` del ``RESULT`` del peer; no se fabrican.

- ``ev="wire_nan"``: ``nan_rejected_b`` (bool), ``inf_rejected_b`` (bool),
  ``bridge_lines_delta`` (int). Sale de ``wire.pack_payload`` con ``NaN``/``Inf``
  y del contador de líneas del bridge.
- ``ev="op"``: ``verb``, ``role`` (``"client"``), ``op_id``, ``status``,
  ``reason``, ``recv_ms``, ``done_ms``, ``frame_recv``, ``frame_done``
  (de ``f03_common.issue_one``/``OpOutcome``), ``read_nk`` (dict nombre→float)
  y ``read_sk`` (dict nombre→str) del verbo (columnas de §3.1 del brief).
- ``ev="state"``: ``read_nk`` con las 45 columnas numéricas y ``read_sk`` con
  las 5 cadenas de ``scam_state_read`` (§3.1, §3.7).
- ``ev="capture"``: ``file`` (nombre ``.bmp``), ``window_w``, ``window_h``
  (px), ``pre_step``/``post_step`` (etiquetas de ``ev="state"``),
  ``capture_tick_ms``, ``capture_h_ms``.
- ``ev="stop"``: ``job_id``, ``stop_send_h_ms``, ``stop_ack_h_ms``,
  ``stop_recv_ms``, ``stop_done_ms``, ``u_ms`` (``job_stop`` y respuesta).
- ``ev="pulse"``: ``burst`` (``"A"|"B"``), ``seq_n``, ``dx_px``,
  ``issued_h_ms``, ``kind`` (``"mouse_move"``).
- ``ev="phase"``: ``path`` (``"dof_var_6s"|"dof_fixed_6s"``),
  ``phase_k`` (1..4), ``pre_step``/``post_step``, ``pre_dtsum_ms``,
  ``post_dtsum_ms``.
- ``ev="dof_config"``: ``accredited_b`` (bool), ``mode``
  (``"offline"|"operator"|"optical"``), ``window_w``, ``window_h``,
  ``mad_bg_50m``.
- ``ev="hud_control"``: ``op_code`` (4), ``mode`` (0|1|2), ``read_nk``.
- ``ev="operator_done"``/``ev="operator_timeout"``: de
  ``f03_common.await_operator``.

``samples/scenario.jsonl``: ``read_nk`` de ``ev="state"`` (45 columnas)
-----------------------------------------------------------------------
``frame`` (contador, ``m_Probe.m_Frame``), ``tick_ms`` (ms,
``m_Probe.NowMs``), ``cam_dtsum_ms`` (ms, ``m_PathDtSumMs``), ``active_b``
(bool 0/1, ``m_Cam.IsActive()``), ``enable_b`` (bool, foco activo),
``sent_focus_dist_m``/``sent_focus_blur`` (m, 0..1, último ``SetFocus``),
``set_focus_calls_n`` (contador de ``ApplyCamFocus``), ``saved_count_n``,
``speed_mps``, ``speed_steps_n``, ``input_frames_n``, ``integrated_dt_s``,
``input_ack_seq_n`` (cámara libre), ``x_m,y_m,z_m`` (m,
``m_Cam.GetTransform``), ``yaw_deg,pitch_deg,roll_deg`` (deg,
``Math3D.MatrixToAngles``), ``fov_rad`` (rad, ``Camera.GetCurrentFOV``),
``m00..m22`` (9 celdas crudas de la matriz de ``m_Cam.GetTransform``),
``eng_x_m,eng_y_m,eng_z_m`` (m, ``GetCurrentCameraPosition``),
``eng_dx,eng_dy,eng_dz`` (unitario, ``GetCurrentCameraDirection``),
``elem_vis_mask`` (bits 0..7, ``IsElementVisible(EHudElement)``),
``flags_mask``/``saved_flags_mask`` (bits 0..11, ``IsContextFlagActive``),
``aux_vis_mask``/``saved_aux_vis_mask`` (bits 0..6, ``IsVisible`` de los 7
auxiliares), ``qb_vis_b`` (``IsElementVisible(EHudElement.QUICKBAR)``),
``qb_items_n`` (``GetQuickBarSize``/``GetQuickBarEntity``), ``menu_open_b``,
``ovl_vis_b`` (barrido DFS de ``GetWorkspace`` con ``IsVisibleHierarchy``).
``read_sk``: ``cam_job_id``, ``cam_job_state``, ``sample_job_id``,
``sample_job_state``, ``saved_names_csv``.

``SCAM-S1`` (CAM-02): pasos de ``ev="state"``
--------------------------------------------
``s_init``, ``s_a``, ``s_b`` y ``s_0`` (los tres tramos de teclado),
``moved`` (pose tras desplazarse ``>= 10 m`` y girar ``>= 30`` grados) y
``p_roll_applied``/``p0_applied`` (poses guardadas reaplicadas). Se aceptan
sinónimos en mayúsculas y variantes listadas en ``_find_state``.

``samples/path_catmull_scripted.jsonl``, ``path_linear_hud.jsonl``,
``path_engine_interp.jsonl``, ``path_dof_var.jsonl``, ``path_dof_fix.jsonl``
----------------------------------------------------------------------------
Páginas de ``job_read`` del trabajo ``"cam"`` concatenadas; una fila JSON por
frame, como lista de 27 floats en este orden (§3.1, §3.4): ``seq_n``,
``frame``, ``tick_ms`` (ms), ``dtsum_ms`` (ms), ``x_m,y_m,z_m`` (m, nodo),
``yaw_deg,pitch_deg,roll_deg`` (deg, nodo), ``eng_x_m,eng_y_m,eng_z_m`` (m,
vista renderizada), ``eng_dx,eng_dy,eng_dz`` (unitario), ``fov_rad`` (rad),
``calc_focus_dist_m`` (m, lerp de claves), ``sent_focus_dist_m`` (m),
``sent_focus_blur`` (0..1), ``set_focus_calls_n`` (contador), ``active_b``
(bool), ``elem_vis_mask``, ``flags_mask``, ``qb_vis_b``, ``menu_open_b``,
``ovl_vis_b``. Las 27 lecturas salen de las mismas API que ``scam_state_read``;
``calc_focus_*`` de ``Math.Lerp`` sobre las claves y ``sent_focus_*``/
``set_focus_calls_n`` de ``ApplyCamFocus``/``Camera.SetFocus``.

``samples/control_recovery.jsonl``
----------------------------------
Páginas de ``job_read`` del trabajo ``"cam_sample"``; lista de 18 floats:
``seq_n``, ``frame``, ``tick_ms`` (ms), ``dtsum_ms`` (ms),
``eng_x_m,eng_y_m,eng_z_m`` (m), ``eng_dx,eng_dy,eng_dz`` (unitario),
``fov_rad`` (rad), ``pl_cam_x_m,pl_cam_y_m,pl_cam_z_m`` (m),
``pl_cam_dx,pl_cam_dy,pl_cam_dz`` (unitario,
``DayZPlayer.GetCurrentCameraTransform``), ``mcam_active_b`` (bool).

``samples/*.bmp``
-----------------
Capturas de ventana ``>= 1280x720`` en BMP 24 bits BGR sin comprimir
(``BI_RGB``). Se usan: ``hud_during.bmp``, ``hud_clean_ref.bmp``,
``hud_clean_ref_repeat.bmp``, ``hud_visible_ref.bmp``,
``dof_before_reject.bmp``, ``dof_after_reject_1..4.bmp``,
``dof_ctrl_noblur.bmp``, ``dof_ctrl_noblur_repeat.bmp``,
``dof_ctrl_near2m.bmp``, ``dof_ctrl_far50m.bmp``, ``var_t1..t4.bmp`` y
``fix_t1..t4.bmp``. Luminancia ``Y = 0.114 B + 0.587 G + 0.299 R``; ROIs
normalizadas ``[x0,y0,x1,y1]`` desde la esquina superior izquierda; ``var_lap``
es la varianza del Laplaciano 3x3 y ``mad`` la diferencia absoluta media.

``samples/interp_comparison.json``
----------------------------------
Lo escribe este evaluador (§5.3): ``scripted_max_pos_err_m``,
``engine_max_pos_err_m``, ``scripted_max_over_median_step``,
``engine_max_over_median_step``, ``engine_passes_b2_b``,
``engine_supports_keyed_dof_b`` y ``selected_mode`` (``"scripted"`` o
``"engine_interp"``).

``qa/fixtures/s_cam_paths.json``
--------------------------------
``anchor_pose`` (``anchor_x_m``, ``anchor_z_m``, ``anchor_eye_h_m``, ``yaw_deg``,
``pitch_deg``, ``roll_deg``, ``fov_rad``); ``fixture_entities`` (``subject`` y
``background`` con ``classname``, ``dist_m``, ``pos_x_m``, ``pos_z_m``); ``paths``
con ``pos_mode`` y ``keys`` (``t_s``, ``pos_x_m``, ``pos_y_rel_m`` relativo a
``anchor_pose``, ``pos_z_m``, ``yaw_deg``, ``pitch_deg``, ``roll_deg``,
``fov_rad``, ``focus_dist_m``, ``focus_blur``).

``qa/fixtures/s_cam_rois.json``
-------------------------------
``min_window_w``/``min_window_h``, ``roi_bg_50m``, ``roi_subject_2m``,
``roi_quickbar``, ``full_screen``, ``phase_windows_ms`` (``t1``..``t4``),
``max_bracket_span_ms``, ``max_pair_skew_ms``.
"""

import math
import statistics
import struct
from pathlib import Path

import f03_common
import gate_core

SPIKE_ID = "S-cam"
CHECK_IDS = tuple(f"CAM-{i:02d}" for i in range(1, 11))

PATH_COLS_27 = (
    "seq_n", "frame", "tick_ms", "dtsum_ms",
    "x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg",
    "eng_x_m", "eng_y_m", "eng_z_m", "eng_dx", "eng_dy", "eng_dz",
    "fov_rad", "calc_focus_dist_m", "sent_focus_dist_m", "sent_focus_blur",
    "set_focus_calls_n", "active_b", "elem_vis_mask", "flags_mask",
    "qb_vis_b", "menu_open_b", "ovl_vis_b",
)
# Enmienda 2026-11-18: cada fila lleva ademas las 9 celdas crudas m00..m22.
PATH_COLS_36 = PATH_COLS_27 + tuple(
    f"m{r}{c}" for r in range(3) for c in range(3)
)
SAMPLE_COLS_18 = (
    "seq_n", "frame", "tick_ms", "dtsum_ms",
    "eng_x_m", "eng_y_m", "eng_z_m", "eng_dx", "eng_dy", "eng_dz",
    "fov_rad", "pl_cam_x_m", "pl_cam_y_m", "pl_cam_z_m",
    "pl_cam_dx", "pl_cam_dy", "pl_cam_dz", "mcam_active_b",
)
POSE_SCALARS = ("x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg", "fov_rad")
POSE_CELLS = tuple(f"m{r}{c}" for r in range(3) for c in range(3))
PATH_DUMPS = (
    "path_catmull_scripted",
    "path_linear_hud",
    "path_engine_interp",
    "path_dof_var",
    "path_dof_fix",
)
PATH_FIXTURE = {
    "path_catmull_scripted": "short_arc_6s",
    "path_linear_hud": "linear_hud_6s",
    "path_dof_var": "dof_var_6s",
    "path_dof_fix": "dof_fixed_6s",
}


def _chk(cid: str, status: str, detail: str) -> dict:
    return {"detail": detail, "id": cid, "reason": detail, "status": status}


def _not_implemented(cid: str) -> dict:
    return _chk(cid, "missing", "not_implemented")


def _rows_as_dicts(rows: list, cols: tuple) -> list[dict]:
    out = []
    for row in rows:
        if isinstance(row, dict):
            if set(row) != set(cols):
                return []
            out.append(dict(row))
        elif isinstance(row, list) and len(row) == len(cols):
            out.append({name: row[i] for i, name in enumerate(cols)})
        else:
            return []
    return out


def _path_rows_load(rows: list):
    """Filas del recorrido: exactamente las 36 columnas de la enmienda.

    Devuelve (filas, bad_columns). Una fila de 27 columnas, un dict con
    claves de mas o de menos, o una lista de otra longitud es bad_columns.
    """
    out = []
    for row in rows:
        if isinstance(row, dict):
            if set(row) != set(PATH_COLS_36):
                return [], True
            out.append(dict(row))
        elif isinstance(row, list) and len(row) == len(PATH_COLS_36):
            out.append({name: row[i] for i, name in enumerate(PATH_COLS_36)})
        else:
            return [], True
    return out, False


def _load_samples(part_dir) -> dict:
    pdir = Path(part_dir)
    sdir = pdir / "samples"
    fdir = Path(__file__).resolve().parent / "fixtures"
    samples = {
        "captures": {},
        "control_recovery": [],
        "fixtures_paths": {},
        "fixtures_rois": {},
        "manifest": {},
        "part_dir": pdir,
        "paths": {},
        "scenario": [],
    }
    mpath = pdir / "manifest.json"
    if mpath.is_file():
        samples["manifest"] = gate_core.read_json(mpath)
    samples["scenario"] = f03_common.read_jsonl(sdir / "scenario.jsonl")
    samples["bridge"] = f03_common.read_jsonl(sdir / "bridge.jsonl")
    samples["path_bad_columns"] = {}
    for name in PATH_DUMPS:
        rows, bad = _path_rows_load(
            f03_common.read_jsonl(sdir / f"{name}.jsonl")
        )
        samples["paths"][name] = rows
        samples["path_bad_columns"][name] = bad
    samples["control_recovery"] = _rows_as_dicts(
        f03_common.read_jsonl(sdir / "control_recovery.jsonl"), SAMPLE_COLS_18
    )
    if sdir.is_dir():
        samples["captures"] = {p.name: p for p in sorted(sdir.glob("*.bmp"))}
    fp = fdir / "s_cam_paths.json"
    if fp.is_file():
        samples["fixtures_paths"] = gate_core.read_json(fp)
    fr = fdir / "s_cam_rois.json"
    if fr.is_file():
        samples["fixtures_rois"] = gate_core.read_json(fr)
    return samples


def _event(scenario: list, ev: str, phase: str, step: str) -> dict | None:
    for row in scenario:
        if row.get("ev") == ev and row.get("phase") == phase and row.get("step") == step:
            return row
    return None


def _state(scenario: list, phase: str, step: str) -> dict | None:
    return _event(scenario, "state", phase, step)


def _nk(row: dict | None) -> dict:
    if isinstance(row, dict) and isinstance(row.get("read_nk"), dict):
        return row["read_nk"]
    return {}


def _sk(row: dict | None) -> dict:
    if isinstance(row, dict) and isinstance(row.get("read_sk"), dict):
        return row["read_sk"]
    return {}


def _num(row: dict | None, key: str) -> float | None:
    value = _nk(row).get(key)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def pose_cells_equal(pre: dict, post: dict) -> bool:
    """Igualdad exacta de pose y de las 9 celdas crudas (§5.1, R3-N6)."""
    if not isinstance(pre, dict) or not isinstance(post, dict):
        return False
    for key in POSE_SCALARS + POSE_CELLS:
        if key not in pre or key not in post:
            return False
        if pre[key] != post[key]:
            return False
    return True


def _wrap180(angle_deg: float) -> float:
    return ((float(angle_deg) + 180.0) % 360.0) - 180.0


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _angle_between(d1, d2) -> float:
    dot = sum(float(a) * float(b) for a, b in zip(d1, d2))
    return math.degrees(math.acos(_clip(dot, -1.0, 1.0)))


def _dist(p, q) -> float:
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(p, q)))


def _rot_x(angle: float) -> list:
    c, s = math.cos(angle), math.sin(angle)
    return [[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]]


def _rot_y(angle: float) -> list:
    c, s = math.cos(angle), math.sin(angle)
    return [[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]]


def _rot_z(angle: float) -> list:
    c, s = math.cos(angle), math.sin(angle)
    return [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]


def _mul3(a: list, b: list) -> list:
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def _ypr_matrix(yaw_deg: float, pitch_deg: float, roll_deg: float) -> list:
    """Matriz 3x3 con la convención verificada de ``YawPitchRollMatrix``.

    El ejemplo del prototipo (``enmath3d.c:127-130``) casa con
    ``transpose(Rz(pitch) * Ry(yaw) * Rx(roll))``; se usa la misma convención
    para reconstruir la orientación de las filas que solo publican Euler.
    """
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    roll = math.radians(float(roll_deg))
    m = _mul3(_mul3(_rot_z(pitch), _rot_y(yaw)), _rot_x(roll))
    return [[m[j][i] for j in range(3)] for i in range(3)]


def _matrix_to_quat(m: list) -> list:
    trace = m[0][0] + m[1][1] + m[2][2]
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2][1] - m[1][2]) / s
        y = (m[0][2] - m[2][0]) / s
        z = (m[1][0] - m[0][1]) / s
    elif m[0][0] > m[1][1] and m[0][0] > m[2][2]:
        s = math.sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0
        w = (m[2][1] - m[1][2]) / s
        x = 0.25 * s
        y = (m[0][1] + m[1][0]) / s
        z = (m[0][2] + m[2][0]) / s
    elif m[1][1] > m[2][2]:
        s = math.sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0
        w = (m[0][2] - m[2][0]) / s
        x = (m[0][1] + m[1][0]) / s
        y = 0.25 * s
        z = (m[1][2] + m[2][1]) / s
    else:
        s = math.sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0
        w = (m[1][0] - m[0][1]) / s
        x = (m[0][2] + m[2][0]) / s
        y = (m[1][2] + m[2][1]) / s
        z = 0.25 * s
    return [x, y, z, w]


def _theta3d(q1: list, q2: list) -> float:
    n1 = math.sqrt(sum(float(v) ** 2 for v in q1))
    n2 = math.sqrt(sum(float(v) ** 2 for v in q2))
    if n1 <= 0.0 or n2 <= 0.0:
        return 180.0
    dot = abs(sum(float(a) * float(b) for a, b in zip(q1, q2)) / (n1 * n2))
    return 2.0 * math.degrees(math.acos(_clip(dot, 0.0, 1.0)))


def _theta3d_cells(obs: dict, ref: dict) -> float:
    try:
        m_obs = [[float(obs[f"m{i}{j}"]) for j in range(3)] for i in range(3)]
        m_ref = [[float(ref[f"m{i}{j}"]) for j in range(3)] for i in range(3)]
    except (KeyError, TypeError, ValueError):
        return 180.0
    return _theta3d(_matrix_to_quat(m_obs), _matrix_to_quat(m_ref))


def _theta3d_euler(obs: dict, ref: dict) -> float:
    try:
        q_obs = _matrix_to_quat(
            _ypr_matrix(obs["yaw_deg"], obs["pitch_deg"], obs["roll_deg"])
        )
        q_ref = _matrix_to_quat(
            _ypr_matrix(ref["yaw_deg"], ref["pitch_deg"], ref["roll_deg"])
        )
    except (KeyError, TypeError, ValueError):
        return 180.0
    return _theta3d(q_obs, q_ref)


def _find_state(scenario: list, phase: str, *names: str) -> dict | None:
    for name in names:
        row = _state(scenario, phase, name)
        if row is not None:
            return row
    return None


def _col(row: dict, key: str) -> float | None:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return None


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def _lerp(a: float, b: float, u: float) -> float:
    return float(a) + (float(b) - float(a)) * float(u)


def _row_pos(row: dict, prefix: str = "") -> list[float]:
    return [
        float(row[f"{prefix}x_m"]),
        float(row[f"{prefix}y_m"]),
        float(row[f"{prefix}z_m"]),
    ]


def _row_dir(row: dict, prefix: str = "") -> list[float]:
    return [
        float(row[f"{prefix}dx"]),
        float(row[f"{prefix}dy"]),
        float(row[f"{prefix}dz"]),
    ]


def _mat_forward(row: dict) -> list[float]:
    return [float(row["m20"]), float(row["m21"]), float(row["m22"])]


def _matrix_dict(m: list) -> dict:
    return {f"m{i}{j}": m[i][j] for i in range(3) for j in range(3)}


def _q_from_row(row: dict) -> list:
    m = [[float(row[f"m{i}{j}"]) for j in range(3)] for i in range(3)]
    return _matrix_to_quat(m)


def _key_table(fixture_path: dict) -> list[dict]:
    keys = []
    for raw in fixture_path.get("keys") or []:
        keys.append(
            {
                "t_s": float(raw["t_s"]),
                "pos": [
                    float(raw["pos_x_m"]),
                    float(raw["pos_y_rel_m"]),
                    float(raw["pos_z_m"]),
                ],
                "yaw_deg": float(raw["yaw_deg"]),
                "pitch_deg": float(raw["pitch_deg"]),
                "roll_deg": float(raw["roll_deg"]),
                "fov_rad": float(raw["fov_rad"]),
                "focus_dist_m": float(raw["focus_dist_m"]),
                "focus_blur": float(raw["focus_blur"]),
            }
        )
    return keys


def _ref_pos_rel(keys: list[dict], t_s: float, pos_mode: str) -> list[float]:
    end = keys[-1]["t_s"]
    t = _clip(float(t_s), 0.0, end)
    if pos_mode == "linear":
        for i in range(len(keys) - 1):
            t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
            if t0 <= t <= t1:
                u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
                return [_lerp(keys[i]["pos"][a], keys[i + 1]["pos"][a], u) for a in range(3)]
        return list(keys[-1]["pos"])
    s = 0.0 if end <= 0.0 else t / end
    segs = len(keys) - 1
    seg = min(int(s * segs), segs - 1)
    u = s * segs - seg
    p0 = keys[max(seg - 1, 0)]["pos"]
    p1 = keys[seg]["pos"]
    p2 = keys[seg + 1]["pos"]
    p3 = keys[min(seg + 2, len(keys) - 1)]["pos"]
    out = []
    for a in range(3):
        out.append(
            0.5
            * (
                2.0 * p1[a]
                + (-p0[a] + p2[a]) * u
                + (2.0 * p0[a] - 5.0 * p1[a] + 4.0 * p2[a] - p3[a]) * u * u
                + (-p0[a] + 3.0 * p1[a] - 3.0 * p2[a] + p3[a]) * u * u * u
            )
        )
    return out


def _normalize_quat(q: list) -> list:
    n = math.sqrt(sum(float(v) ** 2 for v in q))
    if n <= 0.0:
        return [0.0, 0.0, 0.0, 1.0]
    return [float(v) / n for v in q]


def _key_quat(key: dict) -> list:
    return _matrix_to_quat(
        _ypr_matrix(key["yaw_deg"], key["pitch_deg"], key["roll_deg"])
    )


def _slerp(qa: list, qb: list, u: float) -> list:
    qa = _normalize_quat(qa)
    qb = _normalize_quat(qb)
    dot = sum(float(a) * float(b) for a, b in zip(qa, qb))
    if dot < 0.0:
        qb = [-v for v in qb]
        dot = -dot
    dot = _clip(dot, -1.0, 1.0)
    if dot > 0.9995:
        return _normalize_quat([_lerp(qa[i], qb[i], u) for i in range(4)])
    omega = math.acos(dot)
    sin_omega = math.sin(omega)
    w1 = math.sin((1.0 - u) * omega) / sin_omega
    w2 = math.sin(u * omega) / sin_omega
    return _normalize_quat([w1 * qa[i] + w2 * qb[i] for i in range(4)])


def _ref_quat(keys: list[dict], t_s: float) -> list:
    end = keys[-1]["t_s"]
    t = _clip(float(t_s), 0.0, end)
    for i in range(len(keys) - 1):
        t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
        if t0 <= t <= t1:
            u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return _slerp(_key_quat(keys[i]), _key_quat(keys[i + 1]), u)
    return _key_quat(keys[-1])


def _ref_fov(keys: list[dict], t_s: float) -> float:
    end = keys[-1]["t_s"]
    t = _clip(float(t_s), 0.0, end)
    for i in range(len(keys) - 1):
        t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
        if t0 <= t <= t1:
            u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return _lerp(keys[i]["fov_rad"], keys[i + 1]["fov_rad"], u)
    return keys[-1]["fov_rad"]


def _ref_focus(keys: list[dict], t_s: float) -> tuple[float, float]:
    end = keys[-1]["t_s"]
    t = _clip(float(t_s), 0.0, end)
    for i in range(len(keys) - 1):
        t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
        if t0 <= t <= t1:
            u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            return (
                _lerp(keys[i]["focus_dist_m"], keys[i + 1]["focus_dist_m"], u),
                _lerp(keys[i]["focus_blur"], keys[i + 1]["focus_blur"], u),
            )
    return keys[-1]["focus_dist_m"], keys[-1]["focus_blur"]


def _row_time(row: dict, t_end: float) -> float | None:
    try:
        return min(float(row["dtsum_ms"]) / 1000.0, float(t_end))
    except (KeyError, TypeError, ValueError):
        return None


def _closest_row(rows: list, t_target: float, t_end: float) -> tuple[dict | None, float]:
    best = None
    best_dt = float("inf")
    best_t = 0.0
    for row in rows:
        t = _row_time(row, t_end)
        if t is None:
            continue
        dt = abs(t - t_target)
        if dt < best_dt:
            best_dt = dt
            best = row
            best_t = t
    return best, best_t


def _path_status(
    rows: list, keys: list[dict], pos_mode: str, t_end: float, y_datum: float
) -> tuple[str, str]:
    count = len(rows)
    if count == 0:
        return "missing", "no_rows"
    if count < 180:
        return "missing", f"rows={count}"
    dtsums = []
    for row in rows:
        try:
            dtsums.append(float(row["dtsum_ms"]))
        except (KeyError, TypeError, ValueError):
            return "missing", "bad_columns"
    for i in range(1, count):
        if dtsums[i] - dtsums[i - 1] > 100.0:
            return "missing", f"gap_ms={dtsums[i] - dtsums[i - 1]:.1f}"
    for i, row in enumerate(rows):
        try:
            seq = float(row["seq_n"])
            frame = float(row["frame"])
        except (KeyError, TypeError, ValueError):
            return "missing", "bad_columns"
        if i == 0:
            if dtsums[0] != 0.0:
                return "fail", "first_dtsum_not_zero"
        else:
            if dtsums[i] <= dtsums[i - 1]:
                return "fail", "dtsum_not_increasing"
            if abs(frame - float(rows[i - 1]["frame"]) - 1.0) > 1e-6:
                return "fail", "frame_not_contiguous"
        if abs(seq - i) > 1e-6:
            return "fail", "seq_n_not_contiguous"
    for row in rows:
        try:
            if float(row["active_b"]) != 1.0:
                return "fail", "cam_inactive"
            if _dist(_row_pos(row, "eng_"), _row_pos(row)) >= 0.01:
                return "fail", "cam_eng_mismatch"
        except (KeyError, TypeError, ValueError):
            return "missing", "bad_columns"
    for row in rows:
        t = _row_time(row, t_end)
        if t is None:
            return "missing", "bad_dtsum"
        ref_rel = _ref_pos_rel(keys, t, pos_mode)
        ref = [ref_rel[0], y_datum + ref_rel[1], ref_rel[2]]
        err = _dist(_row_pos(row, "eng_"), ref)
        if err >= 0.5:
            return "fail", f"ref_err_m={err:.3f}"
    steps = [
        _dist(_row_pos(rows[i], "eng_"), _row_pos(rows[i - 1], "eng_"))
        for i in range(1, count)
    ]
    med = _median(steps)
    if med <= 0.0:
        return "fail", "median_step_zero"
    if max(steps) > 3.0 * med:
        return "fail", f"step_over_median={max(steps) / med:.2f}"
    return "pass", "ok"


def read_bmp_gray(path) -> list[list[float]]:
    """Lee un BMP 24 bits BGR sin comprimir y devuelve luminancia por píxel."""
    data = Path(path).read_bytes()
    if len(data) < 54 or data[:2] != b"BM":
        raise ValueError("not a BMP file")
    offset = struct.unpack_from("<I", data, 10)[0]
    width = struct.unpack_from("<i", data, 18)[0]
    height = struct.unpack_from("<i", data, 22)[0]
    bpp = struct.unpack_from("<H", data, 28)[0]
    compression = struct.unpack_from("<I", data, 30)[0]
    if bpp != 24 or compression != 0 or width <= 0 or height == 0:
        raise ValueError("unsupported BMP format")
    top_down = height < 0
    rows = abs(height)
    stride = ((width * 3 + 3) // 4) * 4
    if offset + stride * rows > len(data):
        raise ValueError("truncated BMP pixel data")
    gray = []
    for y in range(rows):
        src_y = y if top_down else rows - 1 - y
        base = offset + src_y * stride
        line = []
        for x in range(width):
            b = data[base + 3 * x]
            g = data[base + 3 * x + 1]
            r = data[base + 3 * x + 2]
            line.append(0.114 * b + 0.587 * g + 0.299 * r)
        gray.append(line)
    return gray


def _roi_pixels(gray: list[list[float]], roi: list) -> list[float]:
    rows = len(gray)
    cols = len(gray[0]) if rows else 0
    x0 = int(round(float(roi[0]) * cols))
    y0 = int(round(float(roi[1]) * rows))
    x1 = int(round(float(roi[2]) * cols))
    y1 = int(round(float(roi[3]) * rows))
    x0, x1 = max(0, min(x0, cols)), max(0, min(x1, cols))
    y0, y1 = max(0, min(y0, rows)), max(0, min(y1, rows))
    if x1 <= x0 or y1 <= y0:
        return []
    out = []
    for y in range(y0, y1):
        out.extend(gray[y][x0:x1])
    return out


def var_lap(gray: list[list[float]], roi: list) -> float:
    """Varianza del Laplaciano 3x3 sobre el interior de la ROI."""
    rows = len(gray)
    cols = len(gray[0]) if rows else 0
    x0 = max(1, int(round(float(roi[0]) * cols)))
    y0 = max(1, int(round(float(roi[1]) * rows)))
    x1 = min(cols - 1, int(round(float(roi[2]) * cols)))
    y1 = min(rows - 1, int(round(float(roi[3]) * rows)))
    values = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            lap = (
                4.0 * gray[y][x]
                - gray[y - 1][x] - gray[y + 1][x]
                - gray[y][x - 1] - gray[y][x + 1]
            )
            values.append(lap)
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def mad(gray_a: list[list[float]], gray_b: list[list[float]], roi: list) -> float:
    """Diferencia absoluta media entre dos capturas sobre la ROI."""
    pa = _roi_pixels(gray_a, roi)
    pb = _roi_pixels(gray_b, roi)
    if not pa or len(pa) != len(pb):
        return float("inf")
    return sum(abs(a - b) for a, b in zip(pa, pb)) / len(pa)


def _capture_event(samples: dict, name: str) -> dict | None:
    for row in samples.get("scenario") or []:
        if row.get("ev") == "capture" and row.get("file") == name:
            return row
    return None


def _capture_gray(samples: dict, name: str):
    cache = samples.setdefault("_gray_cache", {})
    if name in cache:
        return cache[name]
    path = (samples.get("captures") or {}).get(name)
    gray = None
    if path is not None:
        try:
            gray = read_bmp_gray(path)
        except (OSError, ValueError, struct.error):
            gray = None
    cache[name] = gray
    return gray


def _window_ok(gray, rois: dict) -> bool:
    if not gray or not gray[0]:
        return False
    min_w = int(rois.get("min_window_w", 1280))
    min_h = int(rois.get("min_window_h", 720))
    return len(gray[0]) >= min_w and len(gray) >= min_h


def _capture_window_ok(event: dict | None, rois: dict) -> bool:
    if event is None:
        return True
    try:
        return (
            float(event.get("window_w")) >= float(rois.get("min_window_w", 1280))
            and float(event.get("window_h")) >= float(rois.get("min_window_h", 720))
        )
    except (TypeError, ValueError):
        return True


def _state_indexed(scenario: list, phase: str, prefix: str, idx: int) -> dict | None:
    for name in (
        f"{prefix}_{idx}",
        f"{prefix}{idx}",
        f"dof_{prefix}_{idx}",
        f"{idx}_{prefix}",
        f"{idx}{prefix}",
    ):
        row = _state(scenario, phase, name)
        if row is not None:
            return row
    patterns = (
        f"{prefix}_{idx}",
        f"{prefix}{idx}",
        f"_{idx}_{prefix}",
        f"_{idx}{prefix}",
        f"{idx}_{prefix}",
        f"{idx}{prefix}",
    )
    for cand in scenario:
        if cand.get("ev") != "state" or cand.get("phase") != phase:
            continue
        step = str(cand.get("step") or "").lower()
        if any(pattern in step for pattern in patterns):
            return cand
    return None


_STATIC_RESET_STEPS = (
    "post_reset",
    "reset",
    "dof_reset",
    "post_dof_reset",
    "post_static",
    "post_static_reset",
    "post_ctrl",
)
_STATIC_RESET_HINTS = ("reset", "static", "ctrl")
_PATH_RESET_STEPS = (
    "post_dof_var",
    "post_var",
    "after_dof_var",
    "dof_var_end",
    "post_path_var",
    "post_var_path",
    "post_job_var",
    "post_dof",
    "post_path",
    "after_path",
    "job_end",
    "post_job",
)
_PATH_RESET_HINTS = (
    "post_dof_var",
    "post_var",
    "after_dof_var",
    "dof_var_end",
    "post_path",
    "after_path",
    "post_dof",
    "job_end",
    "post_job",
)


def _scenario_index(scenario: list, row) -> int:
    for i, cand in enumerate(scenario):
        if cand is row:
            return i
    return -1


def _static_reset_fields(samples: dict, phase: str):
    """Reset estatico por identidad y orden: state exacto post_reset en
    SCAM-S4, posterior a la captura dof_ctrl_far50m."""
    scenario = samples.get("scenario") or []
    row = _state(scenario, phase, "post_reset")
    if row is None:
        return None
    cap = _capture_event(samples, "dof_ctrl_far50m.bmp")
    if cap is not None and _scenario_index(scenario, row) < _scenario_index(
        scenario, cap
    ):
        return None
    dist = _num(row, "sent_focus_dist_m")
    blur = _num(row, "sent_focus_blur")
    if dist is None or blur is None:
        return None
    return dist, blur


def _path_reset_fields(samples: dict, phase: str, which: str = "var"):
    """Lectura tras la terminacion real de un camino de foco: step exacto
    post_dof_var/post_dof_fix, cam_job_state vacio y frame posterior a la
    ultima fila de ese camino."""
    step = "post_dof_var" if which == "var" else "post_dof_fix"
    dump = "path_dof_var" if which == "var" else "path_dof_fix"
    scenario = samples.get("scenario") or []
    row = _state(scenario, phase, step)
    if row is None:
        return None
    if _sk(row).get("cam_job_state") != "":
        return None
    rows = samples.get("paths", {}).get(dump) or []
    if rows:
        try:
            last_frame = float(rows[-1]["frame"])
            if float(_nk(row)["frame"]) <= last_frame:
                return None
        except (KeyError, TypeError, ValueError):
            return None
    dist = _num(row, "sent_focus_dist_m")
    blur = _num(row, "sent_focus_blur")
    if dist is None or blur is None:
        return None
    return dist, blur


def _dof_config_accredited(samples: dict):
    """Acreditacion DOF desde evidencia (brief:192), no desde la etiqueta.

    Exige ventana >= 1280x720 y, ademas, mad >= 0,5 o un operator_done,
    con el modo coherente con la build del manifiesto.
    """
    rows = [
        row
        for row in samples.get("scenario") or []
        if row.get("ev") == "dof_config" and str(row.get("phase")) == "SCAM-S0"
    ]
    if not rows:
        return None
    build = str((samples.get("manifest") or {}).get("build") or "")
    operator_done = any(
        row.get("ev") == "operator_done"
        for row in samples.get("scenario") or []
    )
    for row in rows:
        mode = str(row.get("mode") or "")
        if build == "offline" and mode != "offline":
            continue
        if build in ("retail", "diag") and mode == "offline":
            continue
        try:
            ok_window = float(row.get("window_w")) >= 1280.0 and float(
                row.get("window_h")
            ) >= 720.0
            mad_v = float(row.get("mad_bg_50m"))
        except (TypeError, ValueError):
            continue
        if ok_window and (mad_v >= 0.5 or operator_done):
            return True
    return False


def _fixture_reading(samples: dict):
    for row in samples.get("scenario") or []:
        if (
            row.get("ev") == "op"
            and row.get("phase") == "SCAM-S0"
            and row.get("verb") == "scam_fixture_setup"
        ):
            return row
    return None


def _anchor_y(samples: dict):
    """Datum vertical: anchor_y_m de scam_fixture_setup (brief:99)."""
    row = _fixture_reading(samples)
    if row is None:
        return None
    value = _nk(row).get("anchor_y_m")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _y_datum(samples: dict, keys: list):
    anchor_y = _anchor_y(samples)
    if anchor_y is None or not keys:
        return None
    return anchor_y - float(keys[0]["pos"][1])


def _bridge_index(samples: dict):
    enq, result, inst = {}, {}, {}
    for row in samples.get("bridge") or []:
        ev = row.get("ev")
        if ev == "hello":
            args = row.get("args") or {}
            if isinstance(args, dict) and args.get("inst"):
                inst[str(row.get("peer") or "")] = str(args["inst"])
        elif ev == "enq" and row.get("op_id"):
            enq[str(row["op_id"])] = row
        elif ev == "result" and row.get("op_id"):
            result[str(row["op_id"])] = row
    return enq, result, inst


def _provenance_problem(samples: dict):
    """Procedencia (punto 2): cada op/state enlaza con bridge.jsonl.

    Devuelve (status, detail) o None si todo enlaza. Id "0", verbo o rol
    que no casa con el enq, instancia distinta de la del hello, o una
    observacion sin respuesta cruda nunca acreditan un PASA.
    """
    scenario = samples.get("scenario") or []
    bridge = samples.get("bridge") or []
    watched = [
        r for r in scenario if r.get("ev") in ("op", "state")
    ]
    if watched and not bridge:
        return "missing", "no_bridge_provenance"
    enq, result, inst = _bridge_index(samples)
    client_inst = inst.get("client")
    if watched and not client_inst:
        return "missing", "no_peer_instance"
    for row in watched:
        op_id = row.get("op_id")
        if op_id is None or str(op_id) in ("", "0"):
            return "fail", "provenance_id_zero"
        key = str(op_id)
        if key not in enq or key not in result:
            return "missing", f"provenance_unlinked:{key}"
        e = enq[key]
        if row.get("ev") == "op":
            if e.get("verb") != row.get("verb"):
                return "fail", "provenance_verb_mismatch"
            if str(e.get("peer") or "client") != "client":
                return "fail", "provenance_peer_mismatch"
            res = result[key].get("result") or {}
            if isinstance(res, dict):
                if res.get("status") != row.get("status"):
                    return "fail", "provenance_status_mismatch"
                if str(res.get("reason") or "") != str(row.get("reason") or ""):
                    return "fail", "provenance_reason_mismatch"
        peer_inst = row.get("peer_inst")
        if peer_inst is not None and str(peer_inst) != client_inst:
            return "fail", "provenance_instance_mismatch"
    return None


def _capture_ready(samples: dict, name: str, rois: dict, missing: list):
    gray = _capture_gray(samples, name)
    if gray is None:
        missing.append(f"no_bmp:{name}")
        return None
    if not _window_ok(gray, rois):
        missing.append(f"window:{name}")
        return None
    return gray


# CAM-01: rechazos de frontera de poses, cámara cerrada, caminos inválidos y
# camino ocupado, observados uno a uno con 0 efectos sobre las celdas crudas.
# PASS exige: rechazo de NaN/Inf en wire sin líneas nuevas en el bridge; la
# negativa con cámara cerrada da rejected/no_active_cam y pose_cells_equal;
# cada negativa de poses y de caminos da rejected con su reason y conserva
# pose_cells_equal, saved_count_n, saved_names_csv y cam_job_state vacío; y el
# segundo camino recibe rejected/busy conservando job1 running. FAIL si no.
def _check_cam_01(samples: dict) -> dict:
    # fail antes que missing: se recogen primero los incumplimientos de
    # lo presente y despues se clasifican las ausencias.
    scenario = samples.get("scenario") or []
    fails: list[str] = []
    missing: list[str] = []

    def verdict() -> dict:
        if fails:
            return _chk("CAM-01", "fail", fails[0])
        if missing:
            return _chk("CAM-01", "missing", missing[0])
        return _chk("CAM-01", "pass", "ok")

    # N4: precondiciones observadas de S0.
    fixture = _fixture_reading(samples)
    if fixture is None:
        missing.append("no_fixture_setup")
    else:
        if fixture.get("status") != "done":
            fails.append("fixture_not_done")
        fnk = _nk(fixture)
        if _num(fixture, "active_b") != 1.0:
            fails.append("fixture_cam_inactive")
        if _num(fixture, "fov_rad") is None or abs(_num(fixture, "fov_rad") - 0.70) >= 0.001:
            fails.append("fixture_fov")
        if _num(fixture, "subj_present_b") != 1.0 or _num(fixture, "bg_present_b") != 1.0:
            fails.append("fixture_scene_missing")
        if fnk.get("anchor_y_m") is None:
            missing.append("no_anchor_y")

    wire = _event(scenario, "wire_nan", "SCAM-S1", "wire")
    if wire is None:
        missing.append("no_wire_probe")
    else:
        if not (wire.get("nan_rejected_b") is True and wire.get("inf_rejected_b") is True):
            fails.append("wire_nan_not_rejected")
        if wire.get("bridge_lines_delta") != 0:
            fails.append("wire_nan_added_bridge_lines")

    neg0 = _event(scenario, "op", "SCAM-S1", "neg_0")
    pre0 = _state(scenario, "SCAM-S1", "pre_0")
    post0 = _state(scenario, "SCAM-S1", "post_0")
    if neg0 is None or pre0 is None or post0 is None:
        missing.append("no_closed_cam_negative")
    else:
        if neg0.get("status") != "rejected" or neg0.get("reason") != "no_active_cam":
            fails.append("closed_cam_not_rejected")
        if _num(post0, "active_b") != 0.0:
            fails.append("closed_cam_active")
        if not pose_cells_equal(_nk(pre0), _nk(post0)):
            fails.append("closed_cam_effects")

    # N8: negativa sin cliente ejecutable.
    nc_steps = ("no_client_free", "no_client_pose", "no_client_hud",
                "no_client_dof", "no_client_path", "no_client_sample")
    pre_nc = _state(scenario, "SCAM-S1", "pre_nc")
    post_nc = _state(scenario, "SCAM-S1", "post_nc")
    if pre_nc is None or post_nc is None or any(
        _event(scenario, "op", "SCAM-S1", s) is None for s in nc_steps
    ):
        missing.append("no_client_case")
    else:
        for step in nc_steps:
            op = _event(scenario, "op", "SCAM-S1", step)
            if op.get("status") != "rejected" or op.get("reason") != "client_not_in_game":
                fails.append(f"{step}_not_rejected")
        if not pose_cells_equal(_nk(pre_nc), _nk(post_nc)):
            fails.append("no_client_effects")

    pose_negatives = {
        "neg_1": "empty_name",
        "neg_2": "duplicate_name",
        "neg_3": "unknown_pose",
        "neg_4": "bad_args",
        "neg_5": "bad_args",
    }
    path_negatives = {
        "neg_1": "bad_args",
        "neg_2": "bad_args",
        "neg_3": "bad_args",
        "neg_4": "bad_args",
        "neg_5": "bad_args",
        "neg_6": "bad_args",
    }
    for phase, expected in (("SCAM-S1", pose_negatives), ("SCAM-S2", path_negatives)):
        for step, reason in expected.items():
            op = _event(scenario, "op", phase, step)
            pre = _state(scenario, phase, f"pre_{step.split('_')[1]}")
            post = _state(scenario, phase, f"post_{step.split('_')[1]}")
            if op is None or pre is None or post is None:
                missing.append(f"no_{phase}_{step}")
                continue
            if op.get("status") != "rejected" or op.get("reason") != reason:
                fails.append(f"{phase}_{step}_not_rejected")
                continue
            if not pose_cells_equal(_nk(pre), _nk(post)):
                fails.append(f"{phase}_{step}_pose_effect")
            if _num(pre, "saved_count_n") != _num(post, "saved_count_n"):
                fails.append(f"{phase}_{step}_saved_count_changed")
            if _sk(pre).get("saved_names_csv") != _sk(post).get("saved_names_csv"):
                fails.append(f"{phase}_{step}_saved_names_changed")
            if _sk(post).get("cam_job_state") != "":
                fails.append(f"{phase}_{step}_cam_job_not_idle")

    busy_attempt = _event(scenario, "op", "SCAM-S2", "busy_attempt")
    busy_pre = _state(scenario, "SCAM-S2", "busy_pre")
    busy_post = _state(scenario, "SCAM-S2", "busy_post")
    start_op = _event(scenario, "op", "SCAM-S2", "path_1_start")
    if busy_attempt is None or busy_pre is None or busy_post is None or start_op is None:
        missing.append("no_busy_probe")
    else:
        # El trabajo ocupado se ata al que devolvio la Pasada 1.
        job1_id = _sk(start_op).get("job")
        if not isinstance(job1_id, str) or not job1_id or job1_id == "0":
            fails.append("busy_job_id_unanchored")
        else:
            if _sk(busy_pre).get("cam_job_id") != job1_id:
                fails.append("busy_pre_job_mismatch")
            if busy_attempt.get("status") != "rejected" or busy_attempt.get("reason") != "busy":
                fails.append("busy_not_rejected")
            if _sk(busy_post).get("cam_job_id") != job1_id:
                fails.append("busy_replaced_job")
            if _sk(busy_post).get("cam_job_state") != "running":
                fails.append("busy_job_not_running")
    return verdict()


# CAM-02: cámara libre por teclado local en 3 tramos con tiempos integrados
# publicados, e ida y vuelta de pose con alabeo sobre cámara activa. PASS exige
# coherencia cámara/motor, avance > 0.2 s y distancia 1.5..2.5 m en el tramo 1,
# 8.0 m/s y 3..5 m con ratio 1.7..2.3 en el tramo 2, giro 15..40 grados sin
# desplazarse en el tramo 3, y al reaplicar las poses active_b == 1.0 con
# < 0.05 m y < 0.5 grados. FAIL en caso contrario.
def _check_cam_02(samples: dict) -> dict:
    scenario = samples.get("scenario") or []
    phase = "SCAM-S1"
    s_init = _find_state(scenario, phase, "s_init", "S_init")
    s_a = _find_state(scenario, phase, "s_a", "S_a")
    s_b = _find_state(scenario, phase, "s_b", "S_b")
    s_0 = _find_state(scenario, phase, "s_0", "S_0")
    moved = _find_state(
        scenario, phase, "moved", "after_move", "moved_state", "s_moved"
    )
    p_roll = _find_state(
        scenario, phase, "p_roll_applied", "apply_p_roll", "p_roll_restored", "post_p_roll"
    )
    p0 = _find_state(
        scenario, phase, "p0_applied", "apply_p0", "p0_restored", "post_p0"
    )
    for name, row in (
        ("s_init", s_init),
        ("s_a", s_a),
        ("s_b", s_b),
        ("s_0", s_0),
        ("moved", moved),
        ("p_roll", p_roll),
        ("p0", p0),
    ):
        if row is None:
            return _chk("CAM-02", "missing", f"no_{name}")
    try:
        if _num(s_init, "active_b") != 1.0:
            return _chk("CAM-02", "fail", "s_init_inactive")
        if _dist(_row_pos(_nk(s_init)), _row_pos(_nk(s_init), "eng_")) >= 0.01:
            return _chk("CAM-02", "fail", "s_init_cam_eng_mismatch")
        if _angle_between(_mat_forward(_nk(s_init)), _row_dir(_nk(s_init), "eng_")) >= 0.05:
            return _chk("CAM-02", "fail", "s_init_direction_mismatch")

        dt1 = _num(s_a, "integrated_dt_s") - _num(s_init, "integrated_dt_s")
        dt2 = _num(s_b, "integrated_dt_s") - _num(s_a, "integrated_dt_s")
        if dt1 <= 0.2:
            return _chk("CAM-02", "fail", f"dt1_int_s={dt1:.3f}")
        if dt2 <= 0.2:
            return _chk("CAM-02", "fail", f"dt2_int_s={dt2:.3f}")
        f_init = _num(s_init, "input_frames_n")
        f_a = _num(s_a, "input_frames_n")
        f_b = _num(s_b, "input_frames_n")
        f_0 = _num(s_0, "input_frames_n")
        if not (f_a > f_init and f_b > f_a and f_0 > f_b):
            return _chk("CAM-02", "fail", "input_frames_not_increasing")

        p_init = _row_pos(_nk(s_init))
        p_a = _row_pos(_nk(s_a))
        p_b = _row_pos(_nk(s_b))
        p_0 = _row_pos(_nk(s_0))
        d1 = _dist(p_a, p_init)
        d2 = _dist(p_b, p_a)
        if not (1.5 <= d1 <= 2.5):
            return _chk("CAM-02", "fail", f"d1_m={d1:.3f}")
        if _theta3d_cells(_nk(s_a), _nk(s_init)) >= 0.5:
            return _chk("CAM-02", "fail", "tramo1_rotation")
        if _num(s_b, "speed_mps") != 8.0:
            return _chk("CAM-02", "fail", f"speed_mps={_num(s_b, 'speed_mps')}")
        if _num(s_b, "speed_steps_n") < 1.0:
            return _chk("CAM-02", "fail", "speed_steps_n=0")
        if not (3.0 <= d2 <= 5.0):
            return _chk("CAM-02", "fail", f"d2_m={d2:.3f}")
        ratio = (d2 / dt2) / (d1 / dt1)
        if not (1.7 <= ratio <= 2.3):
            return _chk("CAM-02", "fail", f"speed_ratio={ratio:.2f}")
        if _dist(p_0, p_b) >= 0.05:
            return _chk("CAM-02", "fail", "tramo3_moved")
        dyaw = abs(_wrap180(_num(s_0, "yaw_deg") - _num(s_b, "yaw_deg")))
        dpitch = abs(_num(s_0, "pitch_deg") - _num(s_b, "pitch_deg"))
        if not (15.0 <= dyaw <= 40.0):
            return _chk("CAM-02", "fail", f"tramo3_dyaw_deg={dyaw:.2f}")
        if not (15.0 <= dpitch <= 40.0):
            return _chk("CAM-02", "fail", f"tramo3_dpitch_deg={dpitch:.2f}")

        saved_pos = _row_pos(_nk(s_0))
        moved_pos = _row_pos(_nk(moved))
        if _dist(moved_pos, saved_pos) < 10.0:
            return _chk("CAM-02", "fail", "moved_less_than_10m")
        if _theta3d_cells(_nk(moved), _nk(s_0)) < 30.0:
            return _chk("CAM-02", "fail", "moved_less_than_30deg")

        # La referencia es la lectura de scam_pose_save (brief:105), no
        # los angulos pedidos ni la posicion de S_0.
        save_roll = _event(scenario, "op", phase, "save_p_roll")
        save_p0 = _event(scenario, "op", phase, "save_p0")
        if save_roll is None or save_p0 is None:
            return _chk("CAM-02", "missing", "no_saved_pose_reading")
        roll_saved_pos = _row_pos(_nk(save_roll))
        p0_saved_pos = _row_pos(_nk(save_p0))
        if _num(p_roll, "active_b") != 1.0:
            return _chk("CAM-02", "fail", "p_roll_inactive")
        if _dist(_row_pos(_nk(p_roll), "eng_"), roll_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p_roll_eng_pos_err")
        if _dist(_row_pos(_nk(p_roll)), roll_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p_roll_cam_pos_err")
        if _theta3d_cells(_nk(p_roll), _nk(save_roll)) >= 0.5:
            return _chk("CAM-02", "fail", "p_roll_theta_deg")
        if abs(_num(p_roll, "fov_rad") - _num(save_roll, "fov_rad")) >= 0.00873:
            return _chk("CAM-02", "fail", "p_roll_fov_err")
        if _angle_between(_row_dir(_nk(p_roll), "eng_"), _mat_forward(_nk(p_roll))) >= 0.05:
            return _chk("CAM-02", "fail", "p_roll_direction_err")
        if _dist(_row_pos(_nk(p_roll), "eng_"), _row_pos(_nk(p_roll))) >= 0.01:
            return _chk("CAM-02", "fail", "p_roll_cam_identity")

        if _num(p0, "active_b") != 1.0:
            return _chk("CAM-02", "fail", "p0_inactive")
        if _dist(_row_pos(_nk(p0), "eng_"), p0_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p0_eng_pos_err")
        if _dist(_row_pos(_nk(p0)), p0_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p0_cam_pos_err")
        if _theta3d_cells(_nk(p0), _nk(save_p0)) >= 0.5:
            return _chk("CAM-02", "fail", "p0_theta_deg")
        if abs(_num(p0, "fov_rad") - _num(save_p0, "fov_rad")) >= 0.00873:
            return _chk("CAM-02", "fail", "p0_fov_err")
        if _angle_between(_row_dir(_nk(p0), "eng_"), _mat_forward(_nk(p0))) >= 0.05:
            return _chk("CAM-02", "fail", "p0_direction_err")
    except (KeyError, TypeError, ValueError):
        return _chk("CAM-02", "missing", "bad_columns")
    return _chk("CAM-02", "pass", "ok")


# CAM-03: una muestra por frame en m_Probe.m_Frame, trayectoria a < 0.5 m de la
# referencia analítica independiente (claves de la fixture; solo el origen
# vertical se ancla a la primera fila, como en CAM-04) y ningún paso mayor que
# 3x la mediana. M < 180 filas o un salto de dtsum_ms > 100 ms dan missing
# (INCONCLUSO). PASS exige seq_n y frame consecutivos, dtsum_ms creciente,
# cámara y motor a < 0.01 m en todas las filas, error < 0.5 m en todas y paso
# <= 3x mediana. FAIL en caso contrario.
def _check_cam_03(samples: dict) -> dict:
    fixtures = (samples.get("fixtures_paths") or {}).get("paths") or {}
    for dump in ("path_catmull_scripted", "path_linear_hud"):
        if (samples.get("path_bad_columns") or {}).get(dump):
            return _chk("CAM-03", "missing", "bad_columns")
        rows = samples.get("paths", {}).get(dump) or []
        fpath = fixtures.get(PATH_FIXTURE[dump])
        if not rows or not isinstance(fpath, dict):
            return _chk("CAM-03", "missing", f"no_{dump}")
        try:
            keys = _key_table(fpath)
        except (KeyError, TypeError, ValueError):
            return _chk("CAM-03", "missing", f"bad_{dump}_fixture")
        if not keys:
            return _chk("CAM-03", "missing", f"no_{dump}_keys")
        pos_mode = fpath.get("pos_mode", "linear")
        y_datum = _y_datum(samples, keys)
        if y_datum is None:
            return _chk("CAM-03", "missing", "no_anchor_y")
        status, detail = _path_status(
            rows, keys, pos_mode, keys[-1]["t_s"], y_datum
        )
        if status != "pass":
            return _chk("CAM-03", status, f"{dump}_{detail}")
    return _chk("CAM-03", "pass", "ok")


# CAM-04: fin entre 6.0 y 6.3 s y pose y FOV finales iguales a la última clave.
# PASS exige 6000.0 <= dtsum_ms <= 6300.0, posición a < 0.05 m, orientación a
# < 0.5 grados y FOV a < 0.00873 rad de la última clave, en ambos recorridos
# (path_catmull_scripted y path_linear_hud). FAIL en caso contrario.
def _check_cam_04(samples: dict) -> dict:
    fixtures = (samples.get("fixtures_paths") or {}).get("paths") or {}
    for dump in ("path_catmull_scripted", "path_linear_hud"):
        if (samples.get("path_bad_columns") or {}).get(dump):
            return _chk("CAM-04", "missing", "bad_columns")
        rows = samples.get("paths", {}).get(dump) or []
        fpath = fixtures.get(PATH_FIXTURE[dump])
        if not rows or not isinstance(fpath, dict):
            return _chk("CAM-04", "missing", f"no_{dump}")
        keys = fpath.get("keys") or []
        if not keys:
            return _chk("CAM-04", "missing", f"no_{dump}_keys")
        last = rows[-1]
        key_last = keys[-1]
        anchor_y = _anchor_y(samples)
        if anchor_y is None:
            return _chk("CAM-04", "missing", "no_anchor_y")
        try:
            dtsum = float(last["dtsum_ms"])
            dx = float(last["eng_x_m"]) - float(key_last["pos_x_m"])
            dz = float(last["eng_z_m"]) - float(key_last["pos_z_m"])
            dy = float(last["eng_y_m"]) - (
                anchor_y + float(key_last["pos_y_rel_m"]) - float(keys[0]["pos_y_rel_m"])
            )
            fov = float(last["fov_rad"])
            fov_key = float(key_last["fov_rad"])
        except (KeyError, TypeError, ValueError):
            return _chk("CAM-04", "missing", f"bad_{dump}_columns")
        if not (6000.0 <= dtsum <= 6300.0):
            return _chk("CAM-04", "fail", f"{dump}_finish_ms={dtsum:.1f}")
        pos_err = math.sqrt(dx * dx + dy * dy + dz * dz)
        if pos_err >= 0.05:
            return _chk("CAM-04", "fail", f"{dump}_pos_err_m={pos_err:.4f}")
        theta = _theta3d_euler(last, key_last)
        if theta >= 0.5:
            return _chk("CAM-04", "fail", f"{dump}_theta_deg={theta:.3f}")
        if abs(fov - fov_key) >= 0.00873:
            return _chk("CAM-04", "fail", f"{dump}_fov_diff_rad={abs(fov - fov_key):.5f}")
    return _chk("CAM-04", "pass", "ok")


# CAM-05: giro corto 179 -> -179 y tramo amplio -179 -> -19 con slerp real, FOV
# efectivo leído y comparativa empírica con InterpolateTo. PASS exige dirección
# del motor igual a la matriz en todas las filas, seguimiento de referencia
# < 2.0 grados, yaw cerca de 180/-179/-99 en los instantes fijados, excursión de
# FOV >= 0.25 rad y error de lerp < 0.02 rad, y interp_comparison.json con
# selected_mode calculado por la regla empírica de §5.3. FAIL en otro caso.
def _path_stats(rows: list, keys: list[dict], pos_mode: str) -> dict | None:
    if not rows:
        return None
    t_end = keys[-1]["t_s"]
    try:
        y_datum = float(rows[0]["eng_y_m"]) - keys[0]["pos"][1]
    except (KeyError, TypeError, ValueError):
        return None
    errors = []
    steps = []
    for i, row in enumerate(rows):
        t = _row_time(row, t_end)
        if t is None:
            return None
        ref_rel = _ref_pos_rel(keys, t, pos_mode)
        ref = [ref_rel[0], y_datum + ref_rel[1], ref_rel[2]]
        try:
            errors.append(_dist(_row_pos(row, "eng_"), ref))
            if i:
                steps.append(
                    _dist(_row_pos(row, "eng_"), _row_pos(rows[i - 1], "eng_"))
                )
        except (KeyError, TypeError, ValueError):
            return None
    med = _median(steps)
    return {
        "max_over_median_step": (max(steps) / med) if med > 0.0 else float("inf"),
        "max_pos_err_m": max(errors) if errors else float("inf"),
    }


def _engine_b2_b(rows: list, keys: list[dict]) -> bool:
    if not rows:
        return False
    t_end = keys[-1]["t_s"]
    try:
        y_datum = float(rows[0]["eng_y_m"]) - keys[0]["pos"][1]
    except (KeyError, TypeError, ValueError):
        return False
    status, _ = _path_status(rows, keys, "linear", t_end, y_datum)
    if status != "pass":
        return False
    times = [_row_time(row, t_end) for row in rows]
    if any(t is None for t in times):
        return False
    if not (any(t < 3.0 for t in times) and any(t >= 3.0 for t in times)):
        return False
    row3, t3 = _closest_row(rows, 3.0, t_end)
    if row3 is None or abs(t3 - 3.0) > 0.1:
        return False
    try:
        for row, t in zip(rows, times):
            if _angle_between(_row_dir(row, "eng_"), _mat_forward(row)) >= 0.05:
                return False
            if _theta3d(_q_from_row(row), _ref_quat(keys, t)) >= 2.0:
                return False
            if abs(float(row["fov_rad"]) - _ref_fov(keys, t)) >= 0.02:
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _engine_keyed_dof(rows: list, keys: list[dict]) -> bool:
    if not rows:
        return False
    t_end = keys[-1]["t_s"]
    try:
        for row in rows:
            t = _row_time(row, t_end)
            if t is None:
                return False
            ref_dist, ref_blur = _ref_focus(keys, t)
            sent_dist = float(row["sent_focus_dist_m"])
            sent_blur = float(row["sent_focus_blur"])
            if abs(sent_dist - ref_dist) >= 0.25:
                return False
            if abs(sent_blur - ref_blur) >= 0.02:
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _check_cam_05(samples: dict) -> dict:
    if (samples.get("path_bad_columns") or {}).get("path_catmull_scripted"):
        return _chk("CAM-05", "missing", "bad_columns")
    rows = samples.get("paths", {}).get("path_catmull_scripted") or []
    fixtures = (samples.get("fixtures_paths") or {}).get("paths") or {}
    fpath = fixtures.get("short_arc_6s")
    if not rows or not isinstance(fpath, dict):
        return _chk("CAM-05", "missing", "no_path_catmull_scripted")
    try:
        keys = _key_table(fpath)
    except (KeyError, TypeError, ValueError):
        return _chk("CAM-05", "missing", "bad_short_arc_fixture")
    if not keys:
        return _chk("CAM-05", "missing", "no_short_arc_keys")
    t_end = keys[-1]["t_s"]
    try:
        for row in rows:
            t = _row_time(row, t_end)
            if t is None:
                return _chk("CAM-05", "missing", "bad_dtsum")
            if _angle_between(_row_dir(row, "eng_"), _mat_forward(row)) >= 0.05:
                return _chk("CAM-05", "fail", "engine_direction_vs_matrix")
            if _theta3d(_q_from_row(row), _ref_quat(keys, t)) >= 2.0:
                return _chk("CAM-05", "fail", "orientation_vs_slerp")
        for row in rows:
            t = _row_time(row, t_end)
            if t <= 3.0 + 1e-9:
                yaw = _col(row, "yaw_deg")
                if yaw is None or abs(yaw) < 178.5:
                    return _chk("CAM-05", "fail", "short_arc_yaw_deg")
        for target, expected, tol, label in (
            (1.5, 180.0, 1.0, "mid_1_5s"),
            (3.0, -179.0, 1.0, "end_3_0s"),
            (4.5, -99.0, 2.0, "mid_4_5s"),
        ):
            row, t = _closest_row(rows, target, t_end)
            if row is None or abs(t - target) > 0.1:
                return _chk("CAM-05", "fail", f"no_sample_{label}")
            yaw = _col(row, "yaw_deg")
            if yaw is None or abs(_wrap180(yaw - expected)) >= tol:
                return _chk("CAM-05", "fail", f"{label}_yaw_deg")
        fovs = [_col(row, "fov_rad") for row in rows]
        if any(v is None for v in fovs):
            return _chk("CAM-05", "missing", "bad_fov")
        if max(fovs) - min(fovs) < 0.25:
            return _chk("CAM-05", "fail", "fov_excursion_rad")
        for row in rows:
            t = _row_time(row, t_end)
            if abs(float(row["fov_rad"]) - _ref_fov(keys, t)) >= 0.02:
                return _chk("CAM-05", "fail", "fov_vs_lerp_rad")
    except (KeyError, TypeError, ValueError):
        return _chk("CAM-05", "missing", "bad_columns")

    # N6: sin un ensayo optico nativo independiente, la capacidad queda
    # desconocida (null) y el modo sigue en scripted. La comparativa es un
    # informe: se escribe si se puede, pero CAM-05 no se comprueba a si
    # mismo releyendo el fichero que acaba de escribir.
    engine_rows = samples.get("paths", {}).get("path_engine_interp") or []
    scripted_stats = _path_stats(rows, keys, fpath.get("pos_mode", "linear"))
    engine_stats = _path_stats(engine_rows, keys, "linear")
    if scripted_stats is None:
        return _chk("CAM-05", "missing", "bad_scripted_metrics")
    if engine_stats is None:
        return _chk("CAM-05", "missing", "no_path_engine_interp")
    engine_ok = _engine_b2_b(engine_rows, keys)
    comparison = {
        "engine_max_over_median_step": engine_stats["max_over_median_step"],
        "engine_max_pos_err_m": engine_stats["max_pos_err_m"],
        "engine_passes_b2_b": bool(engine_ok),
        "engine_supports_keyed_dof_b": None,
        "scripted_max_over_median_step": scripted_stats["max_over_median_step"],
        "scripted_max_pos_err_m": scripted_stats["max_pos_err_m"],
        "selected_mode": "scripted",
    }
    samples["_interp_comparison"] = comparison
    try:
        out = Path(samples["part_dir"]) / "samples" / "interp_comparison.json"
        gate_core.write_json(out, comparison)
    except (OSError, ValueError):
        pass
    return _chk("CAM-05", "pass", "ok")


# CAM-06: rechazos individuales de foco con 0 efectos sobre pose e imagen, y
# acreditación de textura y estabilidad de escena. Falta de captura, resolución
# < 1280x720, var_lap < 25.0 o ruido basal >= 1.0 dan missing (INCONCLUSO).
# PASS exige rejected/bad_args en las 4 negativas, foco enviado y contador
# intactos, pose_cells_equal y mad < 1.0, y active_b == 1.0 con FOV 0.70 en los
# controles estáticos. FAIL en caso contrario.
def _check_cam_06(samples: dict) -> dict:
    scenario = samples.get("scenario") or []
    rois = samples.get("fixtures_rois") or {}
    phase = "SCAM-S4"
    roi_bg = rois.get("roi_bg_50m")
    roi_subj = rois.get("roi_subject_2m")
    missing = []
    if roi_bg is None or roi_subj is None:
        return _chk("CAM-06", "missing", "no_rois")

    for j in range(1, 5):
        op = _event(scenario, "op", phase, f"neg_{j}")
        if op is None:
            missing.append(f"no_neg_{j}")
            continue
        if op.get("status") != "rejected" or op.get("reason") != "bad_args":
            return _chk("CAM-06", "fail", f"neg_{j}_not_rejected")
        pre = _state_indexed(scenario, phase, "pre", j)
        post = _state_indexed(scenario, phase, "post", j)
        if pre is None or post is None:
            missing.append(f"no_state_neg_{j}")
            continue
        try:
            pre_nk = _nk(pre)
            post_nk = _nk(post)
            pre_tuple = (
                float(pre_nk["enable_b"]),
                float(pre_nk["sent_focus_dist_m"]),
                float(pre_nk["sent_focus_blur"]),
            )
            post_tuple = (
                float(post_nk["enable_b"]),
                float(post_nk["sent_focus_dist_m"]),
                float(post_nk["sent_focus_blur"]),
            )
            pre_calls = float(pre_nk["set_focus_calls_n"])
            post_calls = float(post_nk["set_focus_calls_n"])
        except (KeyError, TypeError, ValueError):
            missing.append(f"bad_state_neg_{j}")
            continue
        expected = (1.0, 3.5, 0.6)
        if any(abs(a - b) > 1e-6 for a, b in zip(pre_tuple, expected)):
            return _chk("CAM-06", "fail", f"neg_{j}_pre_focus")
        if any(abs(a - b) > 1e-6 for a, b in zip(post_tuple, expected)):
            return _chk("CAM-06", "fail", f"neg_{j}_focus_changed")
        if pre_calls != post_calls:
            return _chk("CAM-06", "fail", f"neg_{j}_calls_changed")
        if not pose_cells_equal(pre_nk, post_nk):
            return _chk("CAM-06", "fail", f"neg_{j}_pose_effect")
        if _capture_event(samples, "dof_before_reject.bmp") is None:
            missing.append("no_capture_event:dof_before_reject.bmp")
        if _capture_event(samples, f"dof_after_reject_{j}.bmp") is None:
            missing.append(f"no_capture_event:dof_after_reject_{j}.bmp")
        gray_before = _capture_ready(samples, "dof_before_reject.bmp", rois, missing)
        gray_after = _capture_ready(samples, f"dof_after_reject_{j}.bmp", rois, missing)
        if gray_before is not None and gray_after is not None:
            if mad(gray_before, gray_after, roi_bg) >= 1.0:
                return _chk("CAM-06", "fail", f"neg_{j}_image_changed")

    anchor = (samples.get("fixtures_paths") or {}).get("anchor_pose") or {}
    controls = ("dof_ctrl_noblur.bmp", "dof_ctrl_near2m.bmp", "dof_ctrl_far50m.bmp")
    for name in controls:
        event = _capture_event(samples, name)
        if event is None:
            missing.append(f"no_capture:{name}")
            continue
        if not _capture_window_ok(event, rois):
            missing.append(f"window:{name}")
        states = []
        for key in ("pre_step", "post_step"):
            step = event.get(key)
            if isinstance(step, str) and step:
                row = _state(scenario, phase, step)
                if row is not None:
                    states.append(row)
        if not states:
            missing.append(f"no_state:{name}")
            continue
        for row in states:
            try:
                active = float(_nk(row)["active_b"])
                fov = float(_nk(row)["fov_rad"])
                pos = _row_pos(_nk(row))
                yaw = float(_nk(row)["yaw_deg"])
                pitch = float(_nk(row)["pitch_deg"])
                roll = float(_nk(row)["roll_deg"])
            except (KeyError, TypeError, ValueError):
                missing.append(f"bad_state:{name}")
                continue
            if active != 1.0:
                return _chk("CAM-06", "fail", f"{name}_inactive")
            if abs(fov - 0.70) >= 0.001:
                return _chk("CAM-06", "fail", f"{name}_fov")
            if anchor:
                if (
                    abs(pos[0] - float(anchor["anchor_x_m"])) >= 0.05
                    or abs(pos[2] - float(anchor["anchor_z_m"])) >= 0.05
                ):
                    return _chk("CAM-06", "fail", f"{name}_pose")
                ref = {
                    "yaw_deg": float(anchor["yaw_deg"]),
                    "pitch_deg": float(anchor["pitch_deg"]),
                    "roll_deg": float(anchor["roll_deg"]),
                }
                if _theta3d_euler(_nk(row), ref) >= 0.5:
                    return _chk("CAM-06", "fail", f"{name}_orientation")

    gray_noblur = _capture_ready(samples, "dof_ctrl_noblur.bmp", rois, missing)
    gray_repeat = _capture_ready(samples, "dof_ctrl_noblur_repeat.bmp", rois, missing)
    for j in range(1, 5):
        _capture_ready(samples, f"dof_after_reject_{j}.bmp", rois, missing)
    if gray_noblur is not None:
        if var_lap(gray_noblur, roi_bg) < 25.0 or var_lap(gray_noblur, roi_subj) < 25.0:
            missing.append("texture:noblur")
        if gray_repeat is not None and mad(gray_noblur, gray_repeat, roi_bg) >= 1.0:
            missing.append("noise:noblur")

    if missing:
        return _chk("CAM-06", "missing", missing[0])
    return _chk("CAM-06", "pass", "ok")


# CAM-07: efecto óptico de DOF estático a 2 m y clasificación de DOF apagado o
# no soportado para Q5. Sin configuración acreditada o con CAM-06 missing da
# missing. Con configuración y escena aptas, mad(bg, near2m, noblur) < 0.5 da
# fail con detail dof_not_supported_or_identical_frames. PASS exige fondo
# <= 0.70, sujeto >= 0.85, far50m con mad >= 0.5 y fondo > 0.70, y reset a 0.
def _check_cam_07(samples: dict) -> dict:
    rois = samples.get("fixtures_rois") or {}
    roi_bg = rois.get("roi_bg_50m")
    roi_subj = rois.get("roi_subject_2m")
    if roi_bg is None or roi_subj is None:
        return _chk("CAM-07", "missing", "no_rois")

    cam06 = _check_cam_06(samples)
    if cam06["status"] == "missing":
        return _chk("CAM-07", "missing", "cam06_missing")
    accredited = _dof_config_accredited(samples)
    if accredited is None:
        return _chk("CAM-07", "missing", "no_dof_config")
    if not accredited:
        return _chk("CAM-07", "missing", "dof_config_unaccredited")

    missing = []
    gray_noblur = _capture_ready(samples, "dof_ctrl_noblur.bmp", rois, missing)
    gray_near = _capture_ready(samples, "dof_ctrl_near2m.bmp", rois, missing)
    gray_far = _capture_ready(samples, "dof_ctrl_far50m.bmp", rois, missing)

    vn = var_lap(gray_noblur, roi_bg) if gray_noblur is not None else None
    vs = var_lap(gray_noblur, roi_subj) if gray_noblur is not None else None
    if vn is not None and vn <= 0.0:
        missing.append("texture:noblur_bg")
        vn = None
    if vs is not None and vs <= 0.0:
        missing.append("texture:noblur_subject")
        vs = None

    if gray_noblur is not None and gray_near is not None:
        if mad(gray_noblur, gray_near, roi_bg) < 0.5:
            return _chk("CAM-07", "fail", "dof_not_supported_or_identical_frames")
        if vn is not None:
            if var_lap(gray_near, roi_bg) / vn > 0.70:
                return _chk("CAM-07", "fail", "bg_not_blurred_near2m")
        if vs is not None:
            if var_lap(gray_near, roi_subj) / vs < 0.85:
                return _chk("CAM-07", "fail", "subject_not_sharp_near2m")

    if gray_near is not None and gray_far is not None:
        if mad(gray_near, gray_far, roi_bg) < 0.5:
            return _chk("CAM-07", "fail", "far50m_no_optical_change")
    # N5/D2: el ratio del fondo a 50 m es solo una metrica informativa.

    reset = _static_reset_fields(samples, "SCAM-S4")
    if reset is None:
        missing.append("no_reset_state")
    elif reset[0] != 0.0 or reset[1] != 0.0:
        return _chk("CAM-07", "fail", "reset_focus_not_zero")

    if missing:
        return _chk("CAM-07", "missing", missing[0])
    return _chk("CAM-07", "pass", "ok")


# CAM-08: foco cambiando entre claves de un camino 2 m -> 50 m -> 2 m, con
# expectativas emparejadas a la distancia real de cada fase. Sin configuración
# o con CAM-06 missing da missing; fases fuera de ventana o desemparejadas dan
# missing capture_phase_unaccredited. PASS exige foco enviado < 0.25 m y blur
# 1.0 +-0.02, set_focus_calls_n creciente de uno en uno, fondo <= 0.70 en t1 y
# t4, sujeto >= 0.85 en t1, fondo > 0.70 y mad >= 0.5 en t3, y reset al salir.
def _phase_event_map(samples: dict, path: str) -> dict:
    out = {}
    for row in samples.get("scenario") or []:
        if (
            row.get("ev") != "phase"
            or row.get("phase") != "SCAM-S4"
            or row.get("path") != path
        ):
            continue
        try:
            k = int(row.get("phase_k"))
        except (TypeError, ValueError):
            continue
        if 1 <= k <= 4:
            out[k] = row
    return out


def _phase_mid(samples: dict, event: dict):
    """La fase sale de las lecturas de estado crudas nombradas en
    pre_step/post_step (cam_dtsum_ms), no de las etiquetas del runner."""
    scenario = samples.get("scenario") or []
    pre_row = _state(scenario, "SCAM-S4", str(event.get("pre_step") or ""))
    post_row = _state(scenario, "SCAM-S4", str(event.get("post_step") or ""))
    if pre_row is None or post_row is None:
        return None
    pre = _num(pre_row, "cam_dtsum_ms")
    post = _num(post_row, "cam_dtsum_ms")
    if pre is None or post is None:
        return None
    # Una etiqueta que discrepa de su lectura da missing, no credito.
    for key, raw in (("pre_dtsum_ms", pre), ("post_dtsum_ms", post)):
        if event.get(key) is not None:
            try:
                if abs(float(event[key]) - raw) > 1.0:
                    return None
            except (TypeError, ValueError):
                return None
    return pre, post, (pre + post) / 2.0


def _capture_hashes(samples: dict) -> dict:
    import hashlib

    out = {}
    for name, path in (samples.get("captures") or {}).items():
        try:
            out[name] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except OSError:
            continue
    return out


def _check_cam_08(samples: dict) -> dict:
    rois = samples.get("fixtures_rois") or {}
    roi_bg = rois.get("roi_bg_50m")
    roi_subj = rois.get("roi_subject_2m")
    if roi_bg is None or roi_subj is None:
        return _chk("CAM-08", "missing", "no_rois")

    cam06 = _check_cam_06(samples)
    if cam06["status"] == "missing":
        return _chk("CAM-08", "missing", "cam06_missing")
    accredited = _dof_config_accredited(samples)
    if accredited is None:
        return _chk("CAM-08", "missing", "no_dof_config")
    if not accredited:
        return _chk("CAM-08", "missing", "dof_config_unaccredited")

    fixtures = (samples.get("fixtures_paths") or {}).get("paths") or {}
    fpath = fixtures.get("dof_var_6s")
    rows = samples.get("paths", {}).get("path_dof_var") or []
    missing = []

    keys = None
    if not rows:
        missing.append("no_path_dof_var")
    elif not isinstance(fpath, dict):
        missing.append("no_dof_var_fixture")
    else:
        try:
            keys = _key_table(fpath)
        except (KeyError, TypeError, ValueError):
            missing.append("bad_dof_var_fixture")
        if keys is not None and not keys:
            missing.append("no_dof_var_keys")
            keys = None

    if keys is not None:
        t_end = keys[-1]["t_s"]
        prev_calls = None
        for i, row in enumerate(rows):
            t = _row_time(row, t_end)
            if t is None:
                missing.append("bad_dtsum")
                break
            try:
                sent_dist = float(row["sent_focus_dist_m"])
                sent_blur = float(row["sent_focus_blur"])
                calls = float(row["set_focus_calls_n"])
            except (KeyError, TypeError, ValueError):
                missing.append("bad_columns")
                break
            ref_dist, _ = _ref_focus(keys, t)
            if abs(sent_dist - ref_dist) >= 0.25:
                return _chk("CAM-08", "fail", f"sent_dist_row_{i}")
            if abs(sent_blur - 1.0) >= 0.02:
                return _chk("CAM-08", "fail", f"sent_blur_row_{i}")
            if prev_calls is not None and abs(calls - prev_calls - 1.0) > 1e-6:
                return _chk("CAM-08", "fail", f"focus_calls_row_{i}")
            prev_calls = calls

    gray = {}
    for k in (1, 3, 4):
        gray[f"var_t{k}"] = _capture_ready(samples, f"var_t{k}.bmp", rois, missing)
        gray[f"fix_t{k}"] = _capture_ready(samples, f"fix_t{k}.bmp", rois, missing)

    def ratio(name_a: str, name_b: str, roi: list):
        ga = gray.get(name_a)
        gb = gray.get(name_b)
        if ga is None or gb is None:
            return None
        denom = var_lap(gb, roi)
        if denom <= 0.0:
            return None
        return var_lap(ga, roi) / denom

    if gray["var_t1"] is not None and gray["fix_t1"] is not None:
        bg_ratio = ratio("var_t1", "fix_t1", roi_bg)
        subj_ratio = ratio("var_t1", "fix_t1", roi_subj)
        if bg_ratio is None or subj_ratio is None:
            missing.append("texture:t1")
        else:
            if bg_ratio > 0.70:
                return _chk("CAM-08", "fail", "bg_not_blurred_t1")
            if subj_ratio < 0.85:
                return _chk("CAM-08", "fail", "subject_not_sharp_t1")

    if gray["var_t3"] is not None and gray["fix_t3"] is not None:
        bg_ratio = ratio("var_t3", "fix_t3", roi_bg)
        if bg_ratio is None:
            missing.append("texture:t3")
        # N5/D2: sin umbral > 0,70 en el gate; queda como metrica.
    if gray["var_t3"] is not None and gray["var_t1"] is not None:
        if mad(gray["var_t3"], gray["var_t1"], roi_bg) < 0.5:
            return _chk("CAM-08", "fail", "t3_no_optical_change")

    if gray["var_t4"] is not None and gray["fix_t4"] is not None:
        bg_ratio = ratio("var_t4", "fix_t4", roi_bg)
        if bg_ratio is None:
            missing.append("texture:t4")
        elif bg_ratio > 0.70:
            return _chk("CAM-08", "fail", "bg_not_blurred_t4")

    reset = _path_reset_fields(samples, "SCAM-S4")
    if reset is None:
        missing.append("no_reset_state")
    elif reset[0] != 0.0 or reset[1] != 0.0:
        return _chk("CAM-08", "fail", "reset_focus_not_zero")

    # Cobertura y continuidad de los dos trabajos, variable y control.
    fix_rows = samples.get("paths", {}).get("path_dof_fix") or []
    if (samples.get("path_bad_columns") or {}).get("path_dof_fix"):
        missing.append("bad_columns_fix")
    if len(fix_rows) < 180:
        missing.append("no_path_dof_fix_coverage")
    else:
        for i, row in enumerate(fix_rows):
            try:
                if abs(float(row["seq_n"]) - i) > 1e-6:
                    return _chk("CAM-08", "fail", "fix_seq")
                if i and abs(float(row["frame"]) - float(fix_rows[i - 1]["frame"]) - 1.0) > 1e-6:
                    return _chk("CAM-08", "fail", "fix_frame")
                if abs(float(row["sent_focus_dist_m"]) - 50.0) >= 0.25:
                    return _chk("CAM-08", "fail", f"fix_dist_row_{i}")
                if abs(float(row["sent_focus_blur"]) - 0.0) >= 0.02:
                    return _chk("CAM-08", "fail", f"fix_blur_row_{i}")
            except (KeyError, TypeError, ValueError):
                missing.append("bad_columns_fix")
                break
    if rows and len(rows) < 180:
        missing.append("no_path_dof_var_coverage")
    # Cada captura de fase se enlaza con su evento y su horquilla.
    hashes = _capture_hashes(samples)
    phase_files = [f"{p}_t{k}.bmp" for p in ("var", "fix") for k in (1, 2, 3, 4)]
    for name in phase_files:
        if _capture_event(samples, name) is None:
            missing.append(f"no_capture_event:{name}")
    seen_hash = {}
    for name in phase_files:
        h = hashes.get(name)
        if h is None:
            continue
        if h in seen_hash:
            missing.append(f"capture_reused:{name}")
        seen_hash[h] = name
    if hashes.get("var_t1.bmp") in (hashes.get("dof_ctrl_near2m.bmp"),) and hashes.get("var_t1.bmp"):
        missing.append("capture_reused:var_t1.bmp")
    if hashes.get("var_t3.bmp") in (hashes.get("dof_ctrl_far50m.bmp"),) and hashes.get("var_t3.bmp"):
        missing.append("capture_reused:var_t3.bmp")
    fix_reset = _path_reset_fields(samples, "SCAM-S4", "fix")
    if fix_reset is None:
        missing.append("no_fix_reset_state")
    elif fix_reset[0] != 0.0 or fix_reset[1] != 0.0:
        return _chk("CAM-08", "fail", "fix_reset_focus_not_zero")

    windows = rois.get("phase_windows_ms") or {}
    span_max = float(rois.get("max_bracket_span_ms", 150.0))
    skew_max = float(rois.get("max_pair_skew_ms", 150.0))
    var_phases = _phase_event_map(samples, "dof_var_6s")
    fix_phases = _phase_event_map(samples, "dof_fixed_6s")
    for k in (1, 2, 3, 4):
        var_event = var_phases.get(k)
        fix_event = fix_phases.get(k)
        if var_event is None or fix_event is None:
            missing.append("capture_phase_unaccredited")
            continue
        var_mid = _phase_mid(samples, var_event)
        fix_mid = _phase_mid(samples, fix_event)
        if var_mid is None or fix_mid is None:
            missing.append("capture_phase_unaccredited")
            continue
        window = windows.get(f"t{k}")
        if not isinstance(window, (list, tuple)) or len(window) != 2:
            missing.append("capture_phase_unaccredited")
            continue
        for pre, post, mid in (var_mid, fix_mid):
            if post < pre or post - pre > span_max:
                missing.append("capture_phase_unaccredited")
                break
            if mid < float(window[0]) or mid > float(window[1]):
                missing.append("capture_phase_unaccredited")
                break
        if abs(var_mid[2] - fix_mid[2]) > skew_max:
            missing.append("capture_phase_unaccredited")

    if missing:
        return _chk("CAM-08", "missing", missing[0])
    return _chk("CAM-08", "pass", "ok")


def _first_event(scenario: list, ev: str, phase: str) -> dict | None:
    for row in scenario:
        if row.get("ev") == ev and row.get("phase") == phase:
            return row
    return None


def _num_any(scenario: list, key: str, phases: tuple) -> float | None:
    for phase in phases:
        for row in scenario:
            if row.get("phase") != phase:
                continue
            nk = _nk(row)
            if key in nk:
                try:
                    return float(nk[key])
                except (TypeError, ValueError):
                    continue
    return None


def _avg_pose(a: dict, b: dict):
    out = {}
    for key in POSE_SCALARS:
        va = _num(a, key)
        vb = _num(b, key)
        if va is None or vb is None:
            return None
        out[key] = (va + vb) / 2.0
    return out


def _path_row_hidden(row: dict):
    try:
        elem = float(row["elem_vis_mask"])
        qb = float(row["qb_vis_b"])
        flags = int(float(row["flags_mask"]))
        menu = float(row["menu_open_b"])
        ovl = float(row["ovl_vis_b"])
    except (KeyError, TypeError, ValueError):
        return None
    return elem, qb, flags, menu, ovl


def _recovery_row(row: dict):
    try:
        return {
            "tick_ms": float(row["tick_ms"]),
            "mcam": float(row["mcam_active_b"]),
            "eng_pos": _row_pos(row, "eng_"),
            "eng_dir": _row_dir(row, "eng_"),
            "pl_pos": _row_pos(row, "pl_cam_"),
            "pl_dir": _row_dir(row, "pl_cam_"),
        }
    except (KeyError, TypeError, ValueError):
        return None


# CAM-09: HUD, quickbar y auxiliares ocultos en todo el recorrido, comparación
# visual en la pose exacta de la captura, detector recursivo de overlays y
# restauración completa de flags y auxiliares. Captura fuera de ventana, pose
# inestable o referencia con ruido >= 1.0 dan missing (INCONCLUSO). PASS exige
# qb_items_n >= 1, todas las filas con elem_vis_mask 0, quickbar oculta, flags
# 391, sin inventario ni menu y ovl_vis_b 0, mad contra quickbar visible >= 4.0
# y contra referencia limpia < 2.0/< 1.5, restauración 258 y auxiliares, y los
# dos controles negativos observados. FAIL en caso contrario.
def _check_cam_09(samples: dict) -> dict:
    scenario = samples.get("scenario") or []
    phase = "SCAM-S3"
    rois = samples.get("fixtures_rois") or {}
    roi_qb = rois.get("roi_quickbar")
    roi_full = rois.get("full_screen")
    if roi_qb is None or roi_full is None:
        return _chk("CAM-09", "missing", "no_rois")

    rows = samples.get("paths", {}).get("path_linear_hud") or []
    missing = []
    if not rows:
        missing.append("no_path_linear_hud")

    cap_event = _capture_event(samples, "hud_during.bmp")
    pre_cap = post_cap = None
    if cap_event is not None:
        for key in ("pre_step", "post_step"):
            step = cap_event.get(key)
            if isinstance(step, str) and step:
                row = _state(scenario, phase, step)
                if row is not None:
                    if key == "pre_step":
                        pre_cap = row
                    else:
                        post_cap = row
    if pre_cap is None:
        pre_cap = _find_state(scenario, phase, "pre_cap", "precap", "pre_capture")
    if post_cap is None:
        post_cap = _find_state(scenario, phase, "post_cap", "postcap", "post_capture")
    if cap_event is not None and not _capture_window_ok(cap_event, rois):
        missing.append("window:hud_during")

    # N3: la pose efectiva es la fila del recorrido del frame de la
    # captura (mecanismo explicito), no un promedio. Se admite la
    # latencia normal: la horquilla puede separarse 4 frames. La
    # horquilla se coteja con el recorrido (ancla); si no casa, missing.
    p_cap = None
    if pre_cap is None or post_cap is None or cap_event is None:
        missing.append("no_capture_bracket")
    else:
        if (
            _sk(pre_cap).get("cam_job_state") != "running"
            or _sk(post_cap).get("cam_job_state") != "running"
        ):
            missing.append("capture_job_not_running")
        pre_dt = _num(pre_cap, "cam_dtsum_ms")
        post_dt = _num(post_cap, "cam_dtsum_ms")
        if pre_dt is None or post_dt is None:
            missing.append("bad_capture_dtsum")
        else:
            mid_dt = (pre_dt + post_dt) / 2.0
            if mid_dt < 1850.0 or mid_dt > 2150.0:
                missing.append("capture_window")
        cap_frame = cap_event.get("frame")
        eff_row = None
        by_frame = {}
        for row in rows:
            try:
                by_frame[float(row["frame"])] = row
            except (KeyError, TypeError, ValueError):
                continue
        for state_row, label in ((pre_cap, "pre"), (post_cap, "post")):
            frame_v = _num(state_row, "frame")
            path_row = by_frame.get(frame_v) if frame_v is not None else None
            if path_row is None:
                missing.append(f"capture_{label}_not_anchored")
                continue
            try:
                if _dist(_row_pos(_nk(state_row)), _row_pos(path_row)) > 0.05:
                    missing.append(f"capture_{label}_not_anchored")
                if _theta3d_cells(_nk(state_row), path_row) > 0.5:
                    missing.append(f"capture_{label}_not_anchored")
            except (KeyError, TypeError, ValueError):
                missing.append(f"capture_{label}_not_anchored")
        if cap_frame is not None:
            try:
                eff_row = by_frame.get(float(cap_frame))
            except (TypeError, ValueError):
                eff_row = None
        if eff_row is None:
            missing.append("capture_frame_not_anchored")
        else:
            p_cap = {k: float(eff_row[k]) for k in POSE_SCALARS}
        # Capturas sin evento o reutilizadas entre pasos: nunca PASA.
        for name in ("hud_during.bmp", "hud_clean_ref.bmp",
                     "hud_clean_ref_repeat.bmp", "hud_visible_ref.bmp"):
            if _capture_event(samples, name) is None:
                missing.append(f"no_capture_event:{name}")
        hashes = _capture_hashes(samples)
        seen_h = {}
        for name in ("hud_during.bmp", "hud_clean_ref.bmp",
                     "hud_clean_ref_repeat.bmp", "hud_visible_ref.bmp"):
            h = hashes.get(name)
            if h is not None:
                if h in seen_h:
                    missing.append(f"capture_reused:{name}")
                seen_h[h] = name

    clean_ref = _find_state(
        scenario, phase, "clean_ref_state", "clean_ref", "ref_state", "post_clean_ref"
    )
    if clean_ref is None:
        ref_event = _capture_event(samples, "hud_clean_ref.bmp")
        if ref_event is not None:
            step = ref_event.get("pre_step")
            if isinstance(step, str) and step:
                clean_ref = _state(scenario, phase, step)
    if clean_ref is None:
        missing.append("no_clean_ref_state")
    elif p_cap is not None:
        try:
            if _dist(_row_pos(_nk(clean_ref)), [p_cap["x_m"], p_cap["y_m"], p_cap["z_m"]]) > 0.01:
                missing.append("clean_ref_pose_moved")
            if _theta3d_euler(_nk(clean_ref), p_cap) > 0.05:
                missing.append("clean_ref_pose_rotated")
            if abs(_num(clean_ref, "fov_rad") - p_cap["fov_rad"]) > 0.001:
                missing.append("clean_ref_fov")
        except (KeyError, TypeError, ValueError):
            missing.append("bad_clean_ref_pose")

    gray_during = _capture_ready(samples, "hud_during.bmp", rois, missing)
    gray_clean = _capture_ready(samples, "hud_clean_ref.bmp", rois, missing)
    gray_repeat = _capture_ready(samples, "hud_clean_ref_repeat.bmp", rois, missing)
    gray_visible = _capture_ready(samples, "hud_visible_ref.bmp", rois, missing)
    if gray_clean is not None and gray_repeat is not None:
        if mad(gray_clean, gray_repeat, roi_full) >= 1.0:
            missing.append("noise:clean_ref")

    qb_items = _num(pre_cap, "qb_items_n") if pre_cap is not None else None
    if qb_items is None:
        qb_items = _num_any(scenario, "qb_items_n", (phase, "SCAM-S0"))
    if qb_items is None:
        missing.append("no_qb_items")
    elif qb_items < 1.0:
        return _chk("CAM-09", "fail", "qb_items_n=0")
    in_veh = _num_any(scenario, "player_in_veh_b", (phase, "SCAM-S0"))
    if in_veh is None:
        missing.append("no_player_in_veh")
    elif in_veh != 0.0:
        return _chk("CAM-09", "fail", "player_in_vehicle")

    for i, row in enumerate(rows):
        fields = _path_row_hidden(row)
        if fields is None:
            missing.append(f"bad_path_row_{i}")
            continue
        elem, qb, flags, menu, ovl = fields
        if elem != 0.0:
            return _chk("CAM-09", "fail", f"elem_vis_row_{i}")
        if qb != 0.0:
            return _chk("CAM-09", "fail", f"qb_vis_row_{i}")
        if (flags & 391) != 391:
            return _chk("CAM-09", "fail", f"flags_mask_row_{i}")
        if (flags & 1024) != 0:
            return _chk("CAM-09", "fail", f"inventory_open_row_{i}")
        if menu != 0.0:
            return _chk("CAM-09", "fail", f"menu_open_row_{i}")
        if ovl != 0.0:
            return _chk("CAM-09", "fail", f"ovl_vis_row_{i}")

    if pre_cap is not None:
        aux_cap = _num(pre_cap, "aux_vis_mask")
        if aux_cap is None:
            missing.append("no_aux_vis_pre_cap")
        elif aux_cap != 0.0:
            return _chk("CAM-09", "fail", "aux_visible_pre_cap")

    if (
        gray_during is not None
        and gray_visible is not None
        and gray_clean is not None
    ):
        if mad(gray_visible, gray_clean, roi_full) >= 10.0:
            return _chk("CAM-09", "fail", "hud_visible_other_scene")
        if mad(gray_during, gray_visible, roi_qb) < 4.0:
            return _chk("CAM-09", "fail", "quickbar_not_detected")
        if mad(gray_during, gray_clean, roi_full) >= 2.0:
            return _chk("CAM-09", "fail", "hud_visible_full_screen")
        if mad(gray_during, gray_clean, roi_qb) >= 1.5:
            return _chk("CAM-09", "fail", "quickbar_visible")

    post_hud = _find_state(
        scenario, phase, "post_path_hud", "post_path", "post_hud", "post_job_hud"
    )
    # N7: la restauracion se compara con la observacion inicial
    # congelada antes de ocultar; saved_aux solo es adicional.
    preset = _state(scenario, phase, "hud_preset")
    initial_aux = _num(preset, "aux_vis_mask") if preset is not None else None
    if preset is None:
        missing.append("no_initial_aux_observation")
    if post_hud is None:
        missing.append("no_post_path_hud")
    else:
        fm = _num(post_hud, "flags_mask")
        sfm = _num(post_hud, "saved_flags_mask")
        av = _num(post_hud, "aux_vis_mask")
        sav = _num(post_hud, "saved_aux_vis_mask")
        if None in (fm, sfm, av, sav):
            missing.append("bad_post_path_hud")
        else:
            if fm != 258.0 or sfm != 258.0:
                return _chk("CAM-09", "fail", "flags_not_restored")
            if initial_aux is not None and av != initial_aux:
                return _chk("CAM-09", "fail", "aux_not_restored")
            if av != sav:
                return _chk("CAM-09", "fail", "aux_saved_mismatch")

    # Deteccion de overlays calculada sobre el arbol crudo (brief:169):
    # identidad de cada nodo, relaciones y visibilidad; no ovl_vis_b.
    def tree_overlay(step_name: str):
        tree = None
        for row in scenario:
            if row.get("ev") == "hud_tree" and row.get("step") == step_name:
                tree = row
                break
        if tree is None:
            return None
        baseline = {str(v) for v in tree.get("baseline_ids") or []}
        nodes = tree.get("nodes") or []
        by_id = {str(n.get("id")): n for n in nodes if isinstance(n, dict)}
        for node in nodes:
            if not isinstance(node, dict) or not node.get("hierarchy"):
                continue
            nid = str(node.get("id"))
            parent = node.get("parent")
            if parent is not None and str(parent) not in by_id:
                return None
            if nid not in baseline:
                return 1.0
            if node.get("baseline") and not node.get("visible"):
                pass
            elif node.get("baseline") and node.get("visible") and nid in (
                "crosshair", "stamina_bg",
            ):
                return 1.0
        return 0.0

    if tree_overlay("tree_pre_cap") is None:
        missing.append("no_widget_tree")
    elif tree_overlay("tree_pre_cap") != 0.0:
        return _chk("CAM-09", "fail", "overlay_in_tree_pre_cap")
    if tree_overlay("tree_control_ovl") is None:
        missing.append("no_widget_tree_control")
    elif tree_overlay("tree_control_ovl") != 1.0:
        return _chk("CAM-09", "fail", "control_ovl_not_detected")

    controls = {}
    for row in scenario:
        if row.get("ev") != "hud_control" or row.get("phase") != phase:
            continue
        try:
            mode = int(float(row.get("mode")))
        except (TypeError, ValueError):
            continue
        if mode in (1, 2) and mode not in controls:
            controls[mode] = row
    for mode, key, label in ((1, "qb_vis_b", "qb"), (2, "ovl_vis_b", "ovl")):
        row = controls.get(mode)
        if row is None:
            missing.append(f"no_hud_control_mode_{mode}")
            continue
        value = _num(row, key)
        if value is None:
            missing.append(f"bad_hud_control_mode_{mode}")
            continue
        if value != 1.0:
            return _chk("CAM-09", "fail", f"control_{label}_not_detected")

    if missing:
        return _chk("CAM-09", "missing", missing[0])
    return _chk("CAM-09", "pass", "ok")


# CAM-10: parar a mitad devuelve el control en < 1 s de reloj de pared. Exige
# u <= 100 ms y ráfagas A/B; si faltan, missing (INCONCLUSO). PASS exige una
# fila post-parada con mcam_active_b 0 y cámara del jugador, estabilidad
# pre-pulso < 0.5 grados, respuesta a A >= +3.0 grados antes de 1000 ms desde
# la parada, inversión a B <= -2.0 grados, y restauración de flags y auxiliares.
# FAIL en caso contrario.
def _check_cam_10(samples: dict) -> dict:
    scenario = samples.get("scenario") or []
    phase = "SCAM-S5"
    rows = samples.get("control_recovery") or []
    missing = []
    if not rows:
        return _chk("CAM-10", "missing", "no_control_recovery")

    stop = _first_event(scenario, "stop", phase)
    if stop is None:
        missing.append("no_stop_event")
    u = None
    t0 = None
    if stop is not None:
        try:
            send = float(stop["stop_send_h_ms"])
            ack = float(stop["stop_ack_h_ms"])
            u = ack - send
        except (KeyError, TypeError, ValueError):
            try:
                u = float(stop["u_ms"])
            except (KeyError, TypeError, ValueError):
                u = None
        try:
            t0 = float(stop["stop_recv_ms"])
        except (KeyError, TypeError, ValueError):
            t0 = None
    if u is None:
        missing.append("no_stop_u")
    elif u > 100.0:
        missing.append("u_over_100ms")
    if t0 is None:
        missing.append("no_stop_recv")

    pulses = {"A": [], "B": []}
    for row in scenario:
        if row.get("ev") != "pulse" or row.get("phase") != phase:
            continue
        burst = row.get("burst")
        if burst not in pulses:
            continue
        try:
            issued = float(row["issued_h_ms"])
        except (KeyError, TypeError, ValueError):
            continue
        pulses[burst].append((issued, row))
    for burst in ("A", "B"):
        if not pulses[burst]:
            missing.append(f"no_burst_{burst}")

    if missing:
        return _chk("CAM-10", "missing", missing[0])

    # Rafagas completas: cada pulso con dx_px y seq; el signo se exige
    # en todos los pulsos, y el acuse del peer cubre cada seq usado.
    for burst, sign in (("A", 1.0), ("B", -1.0)):
        for _issued, row in pulses[burst]:
            if row.get("kind") != "mouse_move" or row.get("dx_px") is None or row.get("seq_n") is None:
                return _chk("CAM-10", "missing", f"burst_{burst.lower()}_incomplete")
            try:
                if float(row["dx_px"]) * sign <= 0.0:
                    return _chk("CAM-10", "fail", f"burst_{burst.lower()}_sign")
            except (TypeError, ValueError):
                return _chk("CAM-10", "missing", f"burst_{burst.lower()}_incomplete")
    post_stop_ack = _find_state(scenario, phase, "post_stop_state")
    ack_seq = _num(post_stop_ack, "input_ack_seq_n") if post_stop_ack is not None else None
    if ack_seq is None:
        missing.append("no_input_ack")
    elif ack_seq <= 0.0:
        # Sin consumo acreditado por el peer, los giros no se atribuyen.
        return _chk("CAM-10", "fail", "input_not_acked")
    if missing:
        return _chk("CAM-10", "missing", missing[0])
    pulse_a_h = min((issued for issued, _ in pulses["A"]), default=None)
    pulse_b_h = min((issued for issued, _ in pulses["B"]), default=None)

    rec = []
    for i, row in enumerate(rows):
        parsed = _recovery_row(row)
        if parsed is None:
            return _chk("CAM-10", "missing", f"bad_control_row_{i}")
        rec.append(parsed)
    for i in range(1, len(rec)):
        try:
            prev = float(rows[i - 1]["frame"])
            cur = float(rows[i]["frame"])
            dtick = float(rows[i]["tick_ms"]) - float(rows[i - 1]["tick_ms"])
            ddtsum = float(rows[i]["dtsum_ms"]) - float(rows[i - 1]["dtsum_ms"])
        except (KeyError, TypeError, ValueError):
            return _chk("CAM-10", "missing", "bad_frame_column")
        if abs(cur - prev - 1.0) > 1e-6:
            return _chk("CAM-10", "fail", f"frame_not_contiguous_{i}")
        if dtick <= 0.0:
            return _chk("CAM-10", "missing", "tick_not_increasing")
        if abs(dtick - ddtsum) > 2.0:
            return _chk("CAM-10", "missing", "tick_dtsum_mismatch")

    if t0 is None or pulse_a_h is None or pulse_b_h is None or u is None:
        return _chk("CAM-10", "missing", "no_stop_timing")
    try:
        ack = float(stop.get("stop_ack_h_ms"))
    except (TypeError, ValueError):
        return _chk("CAM-10", "missing", "no_stop_ack")
    pulse_b_min = t0 + (pulse_b_h - ack)

    def handoff(item):
        return (
            item["mcam"] == 0.0
            and _dist(item["eng_pos"], item["pl_pos"]) < 0.02
            and _angle_between(item["eng_dir"], item["pl_dir"]) < 0.2
        )

    # N2: el handoff puede caer en cualquier instante antes de la cota
    # de 1 s; no se exige antes del primer pulso.
    r0 = None
    for idx, item in enumerate(rec):
        if item["tick_ms"] >= t0 and handoff(item):
            r0 = idx
            break
    if r0 is None:
        return _chk("CAM-10", "fail", "no_handoff_row")
    handoff_h = ack + (rec[r0]["tick_ms"] - t0)
    # Estimulos identificables durante la ventana de recuperacion: al
    # menos un pulso A emitido tras el handoff observado.
    a_after = [issued for issued, _ in pulses["A"] if issued >= handoff_h]
    if not a_after:
        return _chk("CAM-10", "missing", "no_stimulus_after_handoff")
    pulse_a_min = t0 + (min(a_after) - ack)
    pre_a = [idx for idx, item in enumerate(rec) if r0 <= idx and item["tick_ms"] < pulse_a_min]
    if not pre_a:
        pre_a = [r0]
    psi0 = math.degrees(
        math.atan2(rec[r0]["pl_dir"][0], rec[r0]["pl_dir"][2])
    )
    for idx in pre_a:
        item = rec[idx]
        if item["mcam"] != 0.0 or not (
            _dist(item["eng_pos"], item["pl_pos"]) < 0.02
            and _angle_between(item["eng_dir"], item["pl_dir"]) < 0.2
        ):
            return _chk("CAM-10", "fail", "handoff_not_player_cam")
        psi = math.degrees(math.atan2(item["pl_dir"][0], item["pl_dir"][2]))
        if abs(_wrap180(psi - psi0)) >= 0.5:
            return _chk("CAM-10", "fail", "pre_pulse_drift")
    r_pre_a = pre_a[-1]
    psi_pre = math.degrees(
        math.atan2(rec[r_pre_a]["pl_dir"][0], rec[r_pre_a]["pl_dir"][2])
    )

    r1 = None
    for idx, item in enumerate(rec):
        if item["tick_ms"] < pulse_a_min or not handoff(item):
            continue
        psi = math.degrees(math.atan2(item["pl_dir"][0], item["pl_dir"][2]))
        if _wrap180(psi - psi_pre) >= 3.0:
            r1 = idx
            break
    if r1 is None:
        return _chk("CAM-10", "fail", "no_burst_a_response")
    if (rec[r1]["tick_ms"] - t0) + u >= 1000.0:
        return _chk("CAM-10", "fail", "recovery_over_1s")

    peak_delta = -180.0
    for item in rec:
        if pulse_a_min <= item["tick_ms"] < pulse_b_min:
            psi = math.degrees(math.atan2(item["pl_dir"][0], item["pl_dir"][2]))
            peak_delta = max(peak_delta, _wrap180(psi - psi_pre))
    psi_peak = _wrap180(psi_pre + peak_delta) if peak_delta > -180.0 else psi_pre

    if pulse_b_min <= rec[r1]["tick_ms"]:
        return _chk("CAM-10", "fail", "burst_b_before_a_response")
    r2 = None
    for idx, item in enumerate(rec):
        if item["tick_ms"] < pulse_b_min or idx <= r1 or not handoff(item):
            continue
        psi = math.degrees(math.atan2(item["pl_dir"][0], item["pl_dir"][2]))
        if _wrap180(psi - psi_peak) <= -2.0:
            r2 = idx
            break
    if r2 is None:
        return _chk("CAM-10", "fail", "no_burst_b_inversion")

    post_stop = _find_state(
        scenario, phase, "post_stop_state", "post_stop", "post_stop_hud", "after_stop"
    )
    if post_stop is None:
        missing.append("no_post_stop_state")
    else:
        fm = _num(post_stop, "flags_mask")
        sfm = _num(post_stop, "saved_flags_mask")
        av = _num(post_stop, "aux_vis_mask")
        sav = _num(post_stop, "saved_aux_vis_mask")
        if None in (fm, sfm, av, sav):
            missing.append("bad_post_stop_state")
        else:
            if fm != 258.0 or sfm != 258.0:
                return _chk("CAM-10", "fail", "flags_not_restored")
            preset5 = _state(scenario, phase, "hud_preset")
            initial_aux = _num(preset5, "aux_vis_mask") if preset5 is not None else None
            if initial_aux is not None and av != initial_aux:
                return _chk("CAM-10", "fail", "aux_not_restored")
            if av != sav:
                return _chk("CAM-10", "fail", "aux_saved_mismatch")

    if missing:
        return _chk("CAM-10", "missing", missing[0])
    return _chk("CAM-10", "pass", "ok")


def _informative_metrics(samples: dict) -> dict:
    """Metricas informativas fuera del gate (D2): ratios a 50 m y por fase."""
    rois = samples.get("fixtures_rois") or {}
    roi_bg = rois.get("roi_bg_50m")
    metrics = {}
    if roi_bg is None:
        return metrics
    noblur = _capture_gray(samples, "dof_ctrl_noblur.bmp")
    far = _capture_gray(samples, "dof_ctrl_far50m.bmp")
    if noblur is not None and far is not None:
        denom = var_lap(noblur, roi_bg)
        if denom > 0.0:
            metrics["far50m_bg_ratio"] = var_lap(far, roi_bg) / denom
    for k in (1, 2, 3, 4):
        var_g = _capture_gray(samples, f"var_t{k}.bmp")
        fix_g = _capture_gray(samples, f"fix_t{k}.bmp")
        if var_g is not None and fix_g is not None:
            denom = var_lap(fix_g, roi_bg)
            if denom > 0.0:
                metrics[f"phase_t{k}_bg_ratio"] = var_lap(var_g, roi_bg) / denom
    comp = samples.get("_interp_comparison")
    if isinstance(comp, dict):
        metrics["interp_comparison"] = comp
    return metrics


def evaluate(part_dir) -> dict:
    samples = _load_samples(part_dir)
    fns = (
        _check_cam_01, _check_cam_02, _check_cam_03, _check_cam_04,
        _check_cam_05, _check_cam_06, _check_cam_07, _check_cam_08,
        _check_cam_09, _check_cam_10,
    )
    checks = []
    for i, fn in enumerate(fns, start=1):
        cid = f"CAM-{i:02d}"
        try:
            checks.append(fn(samples))
        except Exception as exc:  # un campo ausente nunca es excepcion
            checks.append(_chk(cid, "missing", f"internal:{type(exc).__name__}"))
    prov = _provenance_problem(samples)
    if prov is not None:
        status, detail = prov
        c01 = checks[0]
        if c01["status"] == "pass":
            checks[0] = _chk("CAM-01", status, detail)
        elif c01["status"] == "missing" and status == "fail":
            checks[0] = _chk("CAM-01", "fail", detail)
    metrics = _informative_metrics(samples)
    failed = [c["id"] for c in checks if c["status"] == "fail"]
    if failed:
        return gate_core.make_verdict(
            SPIKE_ID, 1, checks=checks, metrics=metrics, reasons=failed
        )
    missing = [c["id"] for c in checks if c["status"] != "pass"]
    if missing:
        return gate_core.make_verdict(
            SPIKE_ID, 2, checks=checks, metrics=metrics, reasons=missing
        )
    return gate_core.make_verdict(
        SPIKE_ID, 0, checks=checks, metrics=metrics, reasons=[]
    )
