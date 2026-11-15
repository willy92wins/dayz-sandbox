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
            out.append(dict(row))
        elif isinstance(row, list) and len(row) == len(cols):
            out.append({name: row[i] for i, name in enumerate(cols)})
        else:
            return []
    return out


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
    for name in PATH_DUMPS:
        samples["paths"][name] = _rows_as_dicts(
            f03_common.read_jsonl(sdir / f"{name}.jsonl"), PATH_COLS_27
        )
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


# CAM-01: rechazos de frontera de poses, cámara cerrada, caminos inválidos y
# camino ocupado, observados uno a uno con 0 efectos sobre las celdas crudas.
# PASS exige: rechazo de NaN/Inf en wire sin líneas nuevas en el bridge; la
# negativa con cámara cerrada da rejected/no_active_cam y pose_cells_equal;
# cada negativa de poses y de caminos da rejected con su reason y conserva
# pose_cells_equal, saved_count_n, saved_names_csv y cam_job_state vacío; y el
# segundo camino recibe rejected/busy conservando job1 running. FAIL si no.
def _check_cam_01(samples: dict) -> dict:
    scenario = samples.get("scenario") or []
    wire = _event(scenario, "wire_nan", "SCAM-S1", "wire")
    if wire is None:
        return _chk("CAM-01", "missing", "no_wire_probe")
    if not (wire.get("nan_rejected_b") is True and wire.get("inf_rejected_b") is True):
        return _chk("CAM-01", "fail", "wire_nan_not_rejected")
    if wire.get("bridge_lines_delta") != 0:
        return _chk("CAM-01", "fail", "wire_nan_added_bridge_lines")

    neg0 = _event(scenario, "op", "SCAM-S1", "neg_0")
    pre0 = _state(scenario, "SCAM-S1", "pre_0")
    post0 = _state(scenario, "SCAM-S1", "post_0")
    if neg0 is None or pre0 is None or post0 is None:
        return _chk("CAM-01", "missing", "no_closed_cam_negative")
    if neg0.get("status") != "rejected" or neg0.get("reason") != "no_active_cam":
        return _chk("CAM-01", "fail", "closed_cam_not_rejected")
    if _num(post0, "active_b") != 0.0:
        return _chk("CAM-01", "fail", "closed_cam_active")
    if not pose_cells_equal(_nk(pre0), _nk(post0)):
        return _chk("CAM-01", "fail", "closed_cam_effects")

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
                return _chk("CAM-01", "missing", f"no_{phase}_{step}")
            if op.get("status") != "rejected" or op.get("reason") != reason:
                return _chk("CAM-01", "fail", f"{phase}_{step}_not_rejected")
            if not pose_cells_equal(_nk(pre), _nk(post)):
                return _chk("CAM-01", "fail", f"{phase}_{step}_pose_effect")
            if _num(pre, "saved_count_n") != _num(post, "saved_count_n"):
                return _chk("CAM-01", "fail", f"{phase}_{step}_saved_count_changed")
            if _sk(pre).get("saved_names_csv") != _sk(post).get("saved_names_csv"):
                return _chk("CAM-01", "fail", f"{phase}_{step}_saved_names_changed")
            if _sk(post).get("cam_job_state") != "":
                return _chk("CAM-01", "fail", f"{phase}_{step}_cam_job_not_idle")

    busy_attempt = _event(scenario, "op", "SCAM-S2", "busy_attempt")
    busy_pre = _state(scenario, "SCAM-S2", "busy_pre")
    busy_post = _state(scenario, "SCAM-S2", "busy_post")
    if busy_attempt is None or busy_pre is None or busy_post is None:
        return _chk("CAM-01", "missing", "no_busy_probe")
    job1_id = _sk(busy_pre).get("cam_job_id")
    if not isinstance(job1_id, str) or not job1_id:
        return _chk("CAM-01", "fail", "busy_without_active_job")
    if busy_attempt.get("status") != "rejected" or busy_attempt.get("reason") != "busy":
        return _chk("CAM-01", "fail", "busy_not_rejected")
    if _sk(busy_post).get("cam_job_id") != job1_id:
        return _chk("CAM-01", "fail", "busy_replaced_job")
    if _sk(busy_post).get("cam_job_state") != "running":
        return _chk("CAM-01", "fail", "busy_job_not_running")
    return _chk("CAM-01", "pass", "ok")


# CAM-02: cámara libre por teclado local en 3 tramos con tiempos integrados
# publicados, e ida y vuelta de pose con alabeo sobre cámara activa. PASS exige
# coherencia cámara/motor, avance > 0.2 s y distancia 1.5..2.5 m en el tramo 1,
# 8.0 m/s y 3..5 m con ratio 1.7..2.3 en el tramo 2, giro 15..40 grados sin
# desplazarse en el tramo 3, y al reaplicar las poses active_b == 1.0 con
# < 0.05 m y < 0.5 grados. FAIL en caso contrario.
def _check_cam_02(samples: dict) -> dict:
    return _not_implemented("CAM-02")


# CAM-03: una muestra por frame en m_Probe.m_Frame, trayectoria a < 0.5 m de la
# referencia analítica independiente y ningún paso mayor que 3x la mediana.
# M < 180 filas o un salto de dtsum_ms > 100 ms dan missing (INCONCLUSO).
# PASS exige seq_n y frame consecutivos, dtsum_ms creciente, cámara y motor a
# < 0.01 m en todas las filas, error < 0.5 m en todas y paso <= 3x mediana.
# FAIL en caso contrario.
def _check_cam_03(samples: dict) -> dict:
    return _not_implemented("CAM-03")


# CAM-04: fin entre 6.0 y 6.3 s y pose y FOV finales iguales a la última clave.
# PASS exige 6000.0 <= dtsum_ms <= 6300.0, posición a < 0.05 m, orientación a
# < 0.5 grados y FOV a < 0.00873 rad de la última clave, en ambos recorridos
# (path_catmull_scripted y path_linear_hud). FAIL en caso contrario.
def _check_cam_04(samples: dict) -> dict:
    fixtures = (samples.get("fixtures_paths") or {}).get("paths") or {}
    for dump in ("path_catmull_scripted", "path_linear_hud"):
        rows = samples.get("paths", {}).get(dump) or []
        fpath = fixtures.get(PATH_FIXTURE[dump])
        if not rows or not isinstance(fpath, dict):
            return _chk("CAM-04", "missing", f"no_{dump}")
        keys = fpath.get("keys") or []
        if not keys:
            return _chk("CAM-04", "missing", f"no_{dump}_keys")
        last = rows[-1]
        first = rows[0]
        key_last = keys[-1]
        key_first = keys[0]
        try:
            dtsum = float(last["dtsum_ms"])
            dx = float(last["eng_x_m"]) - float(key_last["pos_x_m"])
            dz = float(last["eng_z_m"]) - float(key_last["pos_z_m"])
            dy = (
                float(last["eng_y_m"]) - float(first["eng_y_m"])
                - (float(key_last["pos_y_rel_m"]) - float(key_first["pos_y_rel_m"]))
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
def _check_cam_05(samples: dict) -> dict:
    return _not_implemented("CAM-05")


# CAM-06: rechazos individuales de foco con 0 efectos sobre pose e imagen, y
# acreditación de textura y estabilidad de escena. Falta de captura, resolución
# < 1280x720, var_lap < 25.0 o ruido basal >= 1.0 dan missing (INCONCLUSO).
# PASS exige rejected/bad_args en las 4 negativas, foco enviado y contador
# intactos, pose_cells_equal y mad < 1.0, y active_b == 1.0 con FOV 0.70 en los
# controles estáticos. FAIL en caso contrario.
def _check_cam_06(samples: dict) -> dict:
    return _not_implemented("CAM-06")


# CAM-07: efecto óptico de DOF estático a 2 m y clasificación de DOF apagado o
# no soportado para Q5. Sin configuración acreditada o con CAM-06 missing da
# missing. Con configuración y escena aptas, mad(bg, near2m, noblur) < 0.5 da
# fail con detail dof_not_supported_or_identical_frames. PASS exige fondo
# <= 0.70, sujeto >= 0.85, far50m con mad >= 0.5 y fondo > 0.70, y reset a 0.
def _check_cam_07(samples: dict) -> dict:
    return _not_implemented("CAM-07")


# CAM-08: foco cambiando entre claves de un camino 2 m -> 50 m -> 2 m, con
# expectativas emparejadas a la distancia real de cada fase. Sin configuración
# o con CAM-06 missing da missing; fases fuera de ventana o desemparejadas dan
# missing capture_phase_unaccredited. PASS exige foco enviado < 0.25 m y blur
# 1.0 +-0.02, set_focus_calls_n creciente de uno en uno, fondo <= 0.70 en t1 y
# t4, sujeto >= 0.85 en t1, fondo > 0.70 y mad >= 0.5 en t3, y reset al salir.
def _check_cam_08(samples: dict) -> dict:
    return _not_implemented("CAM-08")


# CAM-09: HUD, quickbar y auxiliares ocultos en todo el recorrido, comparación
# visual en la pose exacta de la captura, detector recursivo de overlays y
# restauración completa de flags y auxiliares. Captura fuera de ventana, pose
# inestable o referencia con ruido >= 1.0 dan missing (INCONCLUSO). PASS exige
# qb_items_n >= 1, todas las filas con elem_vis_mask 0, quickbar oculta, flags
# 391, sin inventario ni menu y ovl_vis_b 0, mad contra quickbar visible >= 4.0
# y contra referencia limpia < 2.0/< 1.5, restauración 258 y auxiliares, y los
# dos controles negativos observados. FAIL en caso contrario.
def _check_cam_09(samples: dict) -> dict:
    return _not_implemented("CAM-09")


# CAM-10: parar a mitad devuelve el control en < 1 s de reloj de pared. Exige
# u <= 100 ms y ráfagas A/B; si faltan, missing (INCONCLUSO). PASS exige una
# fila post-parada con mcam_active_b 0 y cámara del jugador, estabilidad
# pre-pulso < 0.5 grados, respuesta a A >= +3.0 grados antes de 1000 ms desde
# la parada, inversión a B <= -2.0 grados, y restauración de flags y auxiliares.
# FAIL en caso contrario.
def _check_cam_10(samples: dict) -> dict:
    return _not_implemented("CAM-10")


def evaluate(part_dir) -> dict:
    samples = _load_samples(part_dir)
    checks = [
        _check_cam_01(samples),
        _check_cam_02(samples),
        _check_cam_03(samples),
        _check_cam_04(samples),
        _check_cam_05(samples),
        _check_cam_06(samples),
        _check_cam_07(samples),
        _check_cam_08(samples),
        _check_cam_09(samples),
        _check_cam_10(samples),
    ]
    failed = [c["id"] for c in checks if c["status"] == "fail"]
    if failed:
        return gate_core.make_verdict(SPIKE_ID, 1, checks=checks, reasons=failed)
    missing = [c["id"] for c in checks if c["status"] != "pass"]
    if missing:
        return gate_core.make_verdict(SPIKE_ID, 2, checks=checks, reasons=missing)
    return gate_core.make_verdict(SPIKE_ID, 0, checks=checks, reasons=[])
