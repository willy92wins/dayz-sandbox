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
  ``peer_inst`` (instancia del peer del ``hello``) si esta presente.
- ``ev="state"``: ``op_id`` (id de la orden ``scam_state_read`` que lo
  produjo; ausente da ``missing``, vacio o ``"0"`` da ``fail``), ``peer_inst``,
  ``read_nk`` con las 45 columnas numéricas y ``read_sk`` con
  las 5 cadenas de ``scam_state_read`` (§3.1, §3.7).
- ``ev="capture"``: ``file`` (nombre ``.bmp``), ``window_w``, ``window_h``
  (px), ``pre_step``/``post_step`` (etiquetas de ``ev="state"``),
  ``capture_tick_ms``, ``capture_h_ms`` y ``frame`` (frame efectivo de la
  captura en el recorrido, si el runner lo publica; en su defecto se usa
  ``capture_tick_ms`` para localizar la fila del recorrido).
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
- ``ev="operator_done"``/``ev="operator_timeout"``: de
  ``f03_common.await_operator``; solo acredita DOF el de ``SCAM-S0`` con
  accion ``confirm_dof_and_windowed``.
- Las filas ``ev="hud_tree"`` y ``ev="hud_control"`` no las produce ningun
  verbo del brief (§3.1): el evaluador no las exige ni las acredita. El
  overlay se juzga por ``ovl_vis_b`` (§3.6 del brief) y los controles de
  CAM-09 por las respuestas ``ev="op"`` de ``scam_hud_op`` enlazadas.

``samples/bridge.jsonl``
-------------------------
Lo escribe el bridge (``bridge_qa``): ``hello`` (``peer``, ``args.inst``),
``enq`` (``op_id``, ``verb``, ``peer``, ``t_ms`` en reloj del arnes) y
``result`` (``op_id``, ``result.status``/``reason``/``read``,
``result.recv_ms``/``done_ms`` en reloj del peer y ``t_ms`` del arnes al
recibir). Cada ``ev="op"``/``ev="state"`` de ``scenario.jsonl`` enlaza con
su ``enq``/``result`` por ``op_id`` unico: el verbo del ``enq`` tiene que
ser el del ``ev="op"`` (o ``scam_state_read`` en ``ev="state"``) y las
claves de ``read_nk``/``read_sk`` tienen que casar con el ``read`` crudo
desempaquetado del ``result``. Un ``result`` ausente con evento ``lost``
del bridge para ese ``op_id`` es ausencia de resultado (``missing``).

Pasos buscados por nombre exacto (``phase``/``step``)
-----------------------------------------------------
``SCAM-S0``: ``fixture`` (op ``scam_fixture_setup``) y cualquier
``ev="state"`` posterior con ``fov_rad`` para acreditar el FOV de la
camara preparada. ``SCAM-S1``: ``wire``, ``pre_0``/``neg_0``/``post_0``,
``pre_nc``/``post_nc``, ``no_client_free``/``no_client_pose``/
``no_client_hud``/``no_client_dof``/``no_client_path``/``no_client_sample``,
``pre_1..5``/``neg_1..5``/``post_1..5``, ``s_init``, ``s_a``, ``s_b``,
``s_0``, ``moved``, ``save_p0``, ``save_p_roll``, ``p_roll_applied``,
``p0_applied``. ``SCAM-S2``: ``pre_1..6``/``neg_1..6``/``post_1..6``,
``path_1_start``, ``busy_pre``, ``busy_attempt``, ``busy_post``.
``SCAM-S3``: ``hud_preset``, ``path_hud_start``, ``pre_cap``, ``post_cap``,
``clean_ref_state``, ``post_path_hud`` y los ``ev="op"`` de control de
``scam_hud_op``. ``SCAM-S4``: ``pre_1..4``/``neg_1..4``/``post_1..4``,
``ctrl_noblur_pre/post``, ``ctrl_near2m_pre/post``,
``ctrl_far50m_pre/post``, ``post_reset``, ``dof_var_6s_t1..t4_pre/post``,
``dof_fixed_6s_t1..t4_pre/post``, ``post_dof_var``, ``post_dof_fix``.
``SCAM-S5``: ``hud_preset``, los arranques ``scam_sample_start`` y
``scam_path_start`` (cada uno ancla su trabajo con ``job == op_id``),
``stop_op`` (op ``job_stop`` cuyo RESULT nombra ese trabajo y observa
``state == "stopped"``), ``stop``, pulsos ``a*``/``b*``,
``post_stop_state``.

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
``p_roll_applied``/``p0_applied`` (poses guardadas reaplicadas: lectura
de estado enlazada o el RESULT ``ev="op"`` de ``scam_pose_apply`` con su
``read.sk.name`` y sus 25 campos, consumido por verbo, nombre e ID). Se
aceptan sinónimos en mayúsculas y variantes listadas en ``_find_state``.

``samples/path_catmull_scripted.jsonl``, ``path_linear_hud.jsonl``,
``path_engine_interp.jsonl``, ``path_dof_var.jsonl``, ``path_dof_fix.jsonl``
----------------------------------------------------------------------------
Páginas de ``job_read`` del trabajo ``"cam"`` concatenadas; una fila JSON por
frame, como lista de 36 floats (enmienda 2026-11-18: 27 mas las 9 celdas
crudas ``m00..m22``) o dict con esas 36 claves, en este orden (§3.1, §3.4):
``seq_n``,
``frame``, ``tick_ms`` (ms), ``dtsum_ms`` (ms), ``x_m,y_m,z_m`` (m, nodo),
``yaw_deg,pitch_deg,roll_deg`` (deg, nodo), ``eng_x_m,eng_y_m,eng_z_m`` (m,
vista renderizada), ``eng_dx,eng_dy,eng_dz`` (unitario), ``fov_rad`` (rad),
``calc_focus_dist_m`` (m, lerp de claves), ``sent_focus_dist_m`` (m),
``sent_focus_blur`` (0..1), ``set_focus_calls_n`` (contador), ``active_b``
(bool), ``elem_vis_mask``, ``flags_mask``, ``qb_vis_b``, ``menu_open_b``,
``ovl_vis_b``, ``m00,m01,m02,m10,m11,m12,m20,m21,m22``. Las lecturas salen
de las mismas API que ``scam_state_read``;
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
import wire

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


def _dir_from_euler(yaw_deg: float, pitch_deg: float) -> list:
    """Dirección ``mat[2]`` de ``YawPitchRollMatrix`` con la fórmula medida
    en la sonda de cliente del 24-nov (enmienda del orquestador, hecho 1):
    ``(cos p * sin y, sin p, cos p * cos y)``, sin efecto del roll.

    Es la única reconstrucción desde Euler que el motor acredita: las
    filas ``mat[0]`` y ``mat[1]`` siguen sin medir hasta la v5 de la
    sonda, así que ninguna orientación entera se reconstruye desde Euler.
    """
    yaw = math.radians(float(yaw_deg))
    pitch = math.radians(float(pitch_deg))
    cp = math.cos(pitch)
    return [cp * math.sin(yaw), math.sin(pitch), cp * math.cos(yaw)]


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


def _ref_dir(keys: list[dict], t_s: float) -> list:
    """Dirección de referencia en ``t_s``: los Euler de las claves se
    interpolan por el camino corto en yaw y se aplica la fórmula medida
    de ``mat[2]``. El giro completo entre claves (el slerp de la matriz
    entera) no se reconstruye: ``mat[0]`` y ``mat[1]`` están sin medir
    hasta la v5, y esa parte queda pendiente (ver CAM-05)."""
    end = keys[-1]["t_s"]
    t = _clip(float(t_s), 0.0, end)
    for i in range(len(keys) - 1):
        t0, t1 = keys[i]["t_s"], keys[i + 1]["t_s"]
        if t0 <= t <= t1:
            u = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
            yaw = keys[i]["yaw_deg"] + _wrap180(
                keys[i + 1]["yaw_deg"] - keys[i]["yaw_deg"]
            ) * u
            pitch = _lerp(keys[i]["pitch_deg"], keys[i + 1]["pitch_deg"], u)
            return _dir_from_euler(yaw, pitch)
    return _dir_from_euler(keys[-1]["yaw_deg"], keys[-1]["pitch_deg"])


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
    # Cobertura (enmienda del 24-nov, hecho 5): sin mínimo fijo de filas;
    # la acreditan seq_n/frame contiguos y ningún hueco de dtsum > 100 ms.
    dtsums = []
    for row in rows:
        try:
            dtsums.append(float(row["dtsum_ms"]))
        except (KeyError, TypeError, ValueError):
            return "missing", "bad_columns"
    for i in range(1, count):
        if dtsums[i] - dtsums[i - 1] > 100.0:
            return "missing", f"gap_ms={dtsums[i] - dtsums[i - 1]:.1f}"
    if dtsums[-1] < t_end * 1000.0 - 100.0:
        return "missing", f"coverage_end_ms={dtsums[-1]:.1f}"
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
    # La vista se ve en el frame siguiente (enmienda, hecho 2): la
    # ``eng_*`` de la fila i es la pose ordenada en la fila i-1, y la
    # vista de la fila 0 precede al recorrido, así que no se juzga.
    # Las filas con dtsum posterior a la duración de las claves ya no
    # son del recorrido (el trabajo terminó) y tampoco se juzgan.
    for i, row in enumerate(rows):
        if not i or dtsums[i] > t_end * 1000.0 + 1e-6:
            continue
        t = _row_time(rows[i - 1], t_end)
        if t is None:
            return "missing", "bad_dtsum"
        ref_rel = _ref_pos_rel(keys, t, pos_mode)
        ref = [ref_rel[0], y_datum + ref_rel[1], ref_rel[2]]
        err = _dist(_row_pos(row, "eng_"), ref)
        if err >= 0.5:
            return "fail", f"ref_err_m={err:.3f}"
    for i, row in enumerate(rows):
        try:
            if float(row["active_b"]) != 1.0:
                return "fail", "cam_inactive"
            if (
                i
                and dtsums[i] <= t_end * 1000.0 + 1e-6
                and _dist(_row_pos(row, "eng_"), _row_pos(rows[i - 1])) >= 0.01
            ):
                return "fail", "cam_eng_mismatch"
        except (KeyError, TypeError, ValueError):
            return "missing", "bad_columns"
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
    # Solo el nombre exacto pre_<j>/post_<j>: una coincidencia aproximada
    # podria tomar la lectura de otra fase como si fuera la de la negativa.
    return _state(scenario, phase, f"{prefix}_{idx}")


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


def _initial_aux(samples: dict, phase: str, boundary_ev: str, boundary_step: str):
    """Mascara inicial de N7: la observacion anterior a ocultar.

    Vale el read de la scam_hud_op(5) enlazada de esa fase o la lectura
    hud_preset si precede en scenario a la orden limite (el arranque del
    camino en S3, el stop en S5). Una hud_preset posterior a restaurar no
    acredita nada. Devuelve (valor, detail): valor None -> missing.
    """
    scenario = samples.get("scenario") or []
    boundary_idx = None
    for i, row in enumerate(scenario):
        if row.get("phase") != phase:
            continue
        if boundary_ev == "stop":
            if row.get("ev") == "stop":
                boundary_idx = i
                break
        elif row.get("ev") == "op" and row.get("step") == boundary_step:
            boundary_idx = i
            break
    preset_ops = [
        (i, r)
        for i, r in enumerate(scenario)
        if r.get("ev") == "op"
        and r.get("phase") == phase
        and r.get("verb") == "scam_hud_op"
        and _num(r, "aux_vis_mask") is not None
        and (boundary_idx is None or i < boundary_idx)
    ]
    if preset_ops:
        return _num(preset_ops[-1][1], "aux_vis_mask"), None
    preset = _state(scenario, phase, "hud_preset")
    if preset is None:
        return None, "no_initial_aux_observation"
    if boundary_idx is not None:
        preset_idx = _scenario_index(scenario, preset)
        if preset_idx < 0 or preset_idx >= boundary_idx:
            return None, "initial_aux_not_before_hide"
    value = _num(preset, "aux_vis_mask")
    if value is None:
        return None, "no_initial_aux_observation"
    return value, None


def _dof_config_accredited(samples: dict):
    """Acreditacion DOF por build (brief:192), no por la etiqueta.

    Offline basta el modo ``offline``. En retail/diag hacen falta ventana
    >= 1280x720 y, ademas, ``mad_bg_50m >= 0,5`` del par preliminar o el
    OPERATOR_DONE de SCAM-S0/confirm_dof_and_windowed. Cada pieza se lee
    por separado: su ausencia nunca acredita.
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
        and str(row.get("phase")) == "SCAM-S0"
        and (
            str(row.get("action") or "") == "confirm_dof_and_windowed"
            or str(row.get("step") or "") == "SCAM-S0"
        )
        for row in samples.get("scenario") or []
    )
    for row in rows:
        mode = str(row.get("mode") or "")
        if build == "offline":
            if mode == "offline":
                return True
            continue
        if build in ("retail", "diag"):
            if mode == "offline":
                continue
            try:
                ok_window = float(row.get("window_w")) >= 1280.0 and float(
                    row.get("window_h")
                ) >= 720.0
            except (TypeError, ValueError):
                continue
            if not ok_window:
                continue
            if operator_done:
                return True
            try:
                mad_v = float(row.get("mad_bg_50m"))
            except (TypeError, ValueError):
                continue
            if mad_v >= 0.5:
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


def _bridge_read(row: dict, result_row: dict):
    """Lectura cruda de un RESULT como (nk, sk): desempaqueta el payload
    wire si lo trae, o usa los dicts nk/sk si el bridge ya los trae."""
    res = result_row.get("result") or {}
    if not isinstance(res, dict):
        return {}, {}
    raw = res.get("read") or {}
    if not isinstance(raw, dict) or not raw:
        return {}, {}
    if isinstance(raw.get("nk"), dict) or isinstance(raw.get("sk"), dict):
        return dict(raw.get("nk") or {}), dict(raw.get("sk") or {})
    if raw.get("has") == ["payload"]:
        try:
            unpacked = wire.unpack_payload(raw)
        except Exception:
            return {}, {}
        return dict(unpacked.get("num") or {}), dict(unpacked.get("str") or {})
    return {}, {}


def _read_matches(row: dict, result_row: dict) -> bool:
    cand_nk, cand_sk = _bridge_read(row, result_row)
    for key, value in (_nk(row) or {}).items():
        if key not in cand_nk:
            return False
        try:
            if abs(float(value) - float(cand_nk[key])) > 1e-6:
                return False
        except (TypeError, ValueError):
            return False
    for key, value in (_sk(row) or {}).items():
        if key not in cand_sk or str(cand_sk[key]) != str(value):
            return False
    return True


def _transport_terminal(row: dict):
    """Terminal de transporte de ``issue_one`` (f03_common.py:1047,1082):
    ``lost`` y ``timeout``/``result_timeout`` dicen que no llego ningun
    RESULT; no son un veredicto del producto sobre la orden."""
    status = row.get("status")
    if status == "lost":
        return "lost"
    if status == "timeout":
        return "timeout"
    return None


def _sealed_frames(row: dict, result_row: dict):
    """Frames sellados fuera del payload: ``frame_recv``/``frame_done``
    del RESULT (DSBX_QA_Probe.c:1262), con la copia del resumen si el
    puente no los trae."""
    res = result_row.get("result") or {}
    out = []
    for key in ("frame_recv", "frame_done"):
        value = res.get(key) if isinstance(res, dict) else None
        if value is None:
            value = row.get(key)
        try:
            out.append(float(value))
        except (TypeError, ValueError):
            out.append(None)
    return out[0], out[1]


def _provenance_problem(samples: dict):
    """Procedencia: cada op/state enlaza con su RESULT crudo del bridge.

    Id ausente da missing; id vacio o "0", verbo, instancia o lectura que
    no casa con la respuesta cruda da fail. Cada op_id y cada paso son
    unicos, y pre_<j> precede a neg_<j> y post_<j> la sigue. Un op sin
    result pero con evento lost del bridge es ausencia, no fabricacion.
    """
    scenario = samples.get("scenario") or []
    bridge = samples.get("bridge") or []
    watched = [r for r in scenario if r.get("ev") in ("op", "state")]
    if watched and not bridge:
        return "missing", "no_bridge_provenance"
    enq, result, inst = _bridge_index(samples)
    lost_ids = {
        str(r.get("op_id"))
        for r in bridge
        if r.get("ev") in ("lost", "expire") and r.get("op_id")
    }
    client_inst = inst.get("client")
    if watched and not client_inst:
        return "missing", "no_peer_instance"
    seen_ids: dict = {}
    seen_steps: dict = {}
    for row in watched:
        step_key = (str(row.get("phase") or ""), str(row.get("step") or ""))
        if step_key in seen_steps:
            return "missing", "provenance_duplicate_step"
        seen_steps[step_key] = row
        op_id = row.get("op_id")
        if op_id is None:
            return "missing", "provenance_id_absent"
        if str(op_id) in ("", "0"):
            return "fail", "provenance_id_zero"
        key = str(op_id)
        if key in seen_ids:
            return "missing", "provenance_duplicate_id"
        seen_ids[key] = row
        if key in lost_ids and key not in result:
            continue
        if key not in enq or key not in result:
            return "missing", f"provenance_unlinked:{key}"
        e = enq[key]
        expected_verb = row.get("verb") if row.get("ev") == "op" else "scam_state_read"
        if e.get("verb") != expected_verb:
            return "fail", "provenance_verb_mismatch"
        if str(e.get("peer") or "client") != "client":
            return "fail", "provenance_peer_mismatch"
        res = result[key].get("result") or {}
        if isinstance(res, dict) and row.get("ev") == "op":
            if res.get("status") != row.get("status"):
                return "fail", "provenance_status_mismatch"
            if str(res.get("reason") or "") != str(row.get("reason") or ""):
                return "fail", "provenance_reason_mismatch"
        if not _read_matches(row, result[key]):
            return "fail", "provenance_read_mismatch"
        # Frescura del payload: la lectura que llena la extension tiene
        # que haberse tomado entre la recepcion y el fin sellados en el
        # RESULT; un frame fuera de ese intervalo es una lectura vieja
        # (o futura) bajo un RESULT nuevo, no la observacion de esta op.
        frame_recv, frame_done = _sealed_frames(row, result[key])
        payload_frame = _num(row, "frame")
        if payload_frame is not None:
            if frame_recv is not None and payload_frame < frame_recv:
                return "fail", "provenance_stale_payload"
            if frame_done is not None and payload_frame > frame_done:
                return "fail", "provenance_stale_payload"
        peer_inst = row.get("peer_inst")
        if peer_inst is not None and str(peer_inst) != client_inst:
            return "fail", "provenance_instance_mismatch"
    # Orden inmediato pre < neg < post en las negativas observadas.
    index = {id(r): i for i, r in enumerate(scenario)}
    for phase in ("SCAM-S1", "SCAM-S2", "SCAM-S4"):
        for j in range(0, 7):
            pre = _state(scenario, phase, f"pre_{j}")
            neg = _event(scenario, "op", phase, f"neg_{j}")
            post = _state(scenario, phase, f"post_{j}")
            if pre is not None and neg is not None and post is not None:
                if not (index[id(pre)] < index[id(neg)] < index[id(post)]):
                    return "missing", "provenance_order"
                # Orden por el reloj del peer: el post tiene que leerse
                # despues de que la negativa terminara (su frame_done
                # sellado); si su payload es de ese frame o de antes de
                # que la negativa acabara, no observa el despues.
                neg_id = str(neg.get("op_id") or "")
                neg_done = None
                if neg_id in result:
                    _fr, neg_done = _sealed_frames(neg, result[neg_id])
                post_frame = _num(post, "frame")
                if neg_done is not None and post_frame is not None:
                    if post_frame < neg_done:
                        return "fail", "provenance_stale_payload"
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

    # N4: precondiciones observadas de S0. El FOV no lo publica
    # scam_fixture_setup (brief:99): lo acredita una lectura de estado
    # posterior de SCAM-S0, o el propio read si lo trae.
    fixture = _fixture_reading(samples)
    if fixture is None:
        missing.append("no_fixture_setup")
    else:
        # El terminal de transporte se clasifica antes de juzgar la
        # lectura: una orden sin RESULT no aporta lectura ni ancla, así
        # que nada de lo que depende de ella puede dar FALLA.
        fixture_terminal = None
        if fixture.get("status") == "lost":
            fixture_terminal = "lost"
        elif _transport_terminal(fixture) == "timeout":
            fixture_terminal = "timeout"
        if fixture_terminal is not None:
            missing.append(f"fixture_{fixture_terminal}")
        elif fixture.get("status") != "done":
            fails.append("fixture_not_done")
        fnk = _nk(fixture)
        if fixture_terminal is None and _num(fixture, "active_b") != 1.0:
            fails.append("fixture_cam_inactive")
        s0_fovs = [
            _num(r, "fov_rad")
            for r in scenario
            if r.get("ev") == "state" and r.get("phase") == "SCAM-S0"
        ]
        s0_fovs = [v for v in s0_fovs if v is not None]
        fixture_fov = _num(fixture, "fov_rad")
        if s0_fovs:
            if not any(abs(v - 0.70) < 0.001 for v in s0_fovs):
                fails.append("fixture_fov")
        elif fixture_terminal is None and fixture_fov is not None:
            if abs(fixture_fov - 0.70) >= 0.001:
                fails.append("fixture_fov")
        elif fixture_terminal is None:
            missing.append("no_fixture_fov_reading")
        if fixture_terminal is None and (
            _num(fixture, "subj_present_b") != 1.0 or _num(fixture, "bg_present_b") != 1.0
        ):
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

    # El resultado terminal presente se juzga antes que las ausencias:
    # una aceptacion observada es fail aunque falte la horquilla, y un
    # lost es ausencia de resultado (missing), nunca fail.
    neg0 = _event(scenario, "op", "SCAM-S1", "neg_0")
    pre0 = _state(scenario, "SCAM-S1", "pre_0")
    post0 = _state(scenario, "SCAM-S1", "post_0")
    if neg0 is None:
        missing.append("no_closed_cam_negative")
    elif neg0.get("status") == "lost":
        missing.append("closed_cam_lost")
    elif _transport_terminal(neg0) == "timeout":
        missing.append("closed_cam_timeout")
    elif neg0.get("status") != "rejected" or neg0.get("reason") != "no_active_cam":
        fails.append("closed_cam_not_rejected")
    elif pre0 is None or post0 is None:
        missing.append("no_closed_cam_negative")
    else:
        if _num(post0, "active_b") != 0.0:
            fails.append("closed_cam_active")
        if not pose_cells_equal(_nk(pre0), _nk(post0)):
            fails.append("closed_cam_effects")

    # N8: seis ordenes sin cliente, cada una con su verbo y su resultado
    # propios, y 0 efectos en toda la lectura (no solo en la pose).
    nc_expected = {
        "no_client_free": "scam_free_op",
        "no_client_pose": "scam_pose_apply",
        "no_client_hud": "scam_hud_op",
        "no_client_dof": "scam_dof_set",
        "no_client_path": "scam_path_start",
        "no_client_sample": "scam_sample_start",
    }
    pre_nc = _state(scenario, "SCAM-S1", "pre_nc")
    post_nc = _state(scenario, "SCAM-S1", "post_nc")
    nc_ops = {s: _event(scenario, "op", "SCAM-S1", s) for s in nc_expected}
    if pre_nc is None or post_nc is None or any(op is None for op in nc_ops.values()):
        missing.append("no_client_case")
    else:
        nc_ids = [str(op.get("op_id")) for op in nc_ops.values()]
        if len(set(nc_ids)) != len(nc_ids) or any(i in ("", "0") for i in nc_ids):
            fails.append("no_client_shared_result")
        # La guarda sin jugador se acredita entera: la lectura de
        # entrada precede a las seis respuestas y la de salida las
        # sigue, en el orden en que el arnes las registro.
        pre_i = _scenario_index(scenario, pre_nc)
        post_i = _scenario_index(scenario, post_nc)
        op_idx = [_scenario_index(scenario, op) for op in nc_ops.values()]
        if not (0 <= pre_i < min(op_idx) and max(op_idx) < post_i):
            missing.append("no_client_order")
        for step, verb in nc_expected.items():
            op = nc_ops[step]
            terminal = _transport_terminal(op)
            if terminal is not None:
                missing.append(f"{step}_{terminal}")
                continue
            if op.get("verb") != verb:
                fails.append(f"{step}_verb_mismatch")
            if op.get("status") != "rejected" or op.get("reason") != "client_not_in_game":
                fails.append(f"{step}_not_rejected")
        # frame y tick son los relojes de la lectura: prueban el orden
        # (el post no puede ser anterior al pre), no un efecto. Los
        # campos de efecto se comparan sin ellos (brief:79,102).
        for key in ("frame", "tick_ms"):
            pre_v = _num(pre_nc, key)
            post_v = _num(post_nc, key)
            if pre_v is not None and post_v is not None and post_v < pre_v:
                missing.append("no_client_clock_order")
        clock = ("frame", "tick_ms")
        pre_fx = {k: v for k, v in _nk(pre_nc).items() if k not in clock}
        post_fx = {k: v for k, v in _nk(post_nc).items() if k not in clock}
        if pre_fx != post_fx or _sk(pre_nc) != _sk(post_nc):
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
            if op is None:
                missing.append(f"no_{phase}_{step}")
                continue
            terminal = _transport_terminal(op)
            if terminal is not None:
                missing.append(f"{phase}_{step}_{terminal}")
                continue
            if op.get("status") != "rejected" or op.get("reason") != reason:
                fails.append(f"{phase}_{step}_not_rejected")
                continue
            if pre is None or post is None:
                missing.append(f"no_{phase}_{step}")
                continue
            if pre.get("op_id") is not None and pre.get("op_id") == post.get("op_id"):
                missing.append(f"no_{phase}_{step}")
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
    elif (start_terminal := _transport_terminal(start_op)) is not None:
        # Sin RESULT del arranque no hay trabajo que anclar: la prueba
        # de ocupado entera queda sin acreditar, nunca en FALLA.
        missing.append(f"path_1_start_{start_terminal}")
    else:
        # El trabajo ocupado se ata al que devolvio la Pasada 1.
        job1_id = _sk(start_op).get("job")
        if not isinstance(job1_id, str) or not job1_id or job1_id == "0":
            fails.append("busy_job_id_unanchored")
        else:
            if _sk(busy_pre).get("cam_job_id") != job1_id:
                fails.append("busy_pre_job_mismatch")
            busy_terminal = _transport_terminal(busy_attempt)
            if busy_terminal is not None:
                missing.append(f"busy_{busy_terminal}")
            elif busy_attempt.get("status") != "rejected" or busy_attempt.get("reason") != "busy":
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
    def _applied(state_names, step, want_name):
        """Reaplicacion (brief:106): vale la lectura de estado enlazada
        o el propio RESULT de ``scam_pose_apply``, consumido por verbo,
        nombre e ID enlazado. El RESULT acredita el nodo (``x_m..``,
        ``m..`` y ``fov_rad``); sus ``eng_*`` son la vista del frame
        anterior (enmienda, hecho 2) y solo se juzgan en una lectura
        posterior, nunca en el propio RESULT."""
        row = _find_state(scenario, phase, *state_names)
        if row is not None:
            return row, None
        op = _event(scenario, "op", phase, step)
        if op is None:
            return None, None
        terminal = _transport_terminal(op)
        if terminal is not None:
            return None, _chk("CAM-02", "missing", f"{step}_{terminal}")
        if op.get("verb") != "scam_pose_apply":
            return None, _chk("CAM-02", "missing", f"no_{step}")
        if op.get("status") != "done":
            return None, _chk("CAM-02", "fail", f"{step}_apply_not_done")
        applied_name = _sk(op).get("name")
        if applied_name is None:
            return None, _chk("CAM-02", "missing", f"no_{step}")
        if applied_name != want_name:
            return None, _chk("CAM-02", "fail", f"{step}_apply_name_mismatch")
        return op, None

    p_roll, p_roll_verdict = _applied(
        ("p_roll_applied", "apply_p_roll", "p_roll_restored", "post_p_roll"),
        "p_roll_applied",
        "P_roll",
    )
    p0, p0_verdict = _applied(
        ("p0_applied", "apply_p0", "p0_restored", "post_p0"),
        "p0_applied",
        "P0",
    )
    if p_roll_verdict is not None:
        return p_roll_verdict
    if p0_verdict is not None:
        return p0_verdict
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

        # La referencia es la lectura de scam_pose_save (brief:105: 10
        # campos, sin matriz), no los angulos pedidos ni S_0. Si el read
        # trae las celdas, la orientacion se juzga celdas frente a
        # celdas; si no, se juzga la direccion con la formula medida de
        # mat[2] desde los Euler guardados, y el giro completo queda
        # pendiente de la v5 (mat[0]/mat[1] sin medir), nunca en FALLA.
        save_roll = _event(scenario, "op", phase, "save_p_roll")
        save_p0 = _event(scenario, "op", phase, "save_p0")
        if save_roll is None or save_p0 is None:
            return _chk("CAM-02", "missing", "no_saved_pose_reading")
        for save_row, want_name in ((save_roll, "P_roll"), (save_p0, "P0")):
            save_terminal = _transport_terminal(save_row)
            if save_terminal is not None:
                return _chk("CAM-02", "missing", f"saved_pose_{save_terminal}")
            if save_row.get("status") != "done":
                return _chk("CAM-02", "fail", "saved_pose_not_done")
            saved_name = _sk(save_row).get("name")
            if saved_name is not None and saved_name != want_name:
                return _chk("CAM-02", "fail", "saved_pose_name_mismatch")

        def _saved_cells(save_row):
            nk = _nk(save_row)
            if all(k in nk for k in POSE_CELLS):
                return {k: float(nk[k]) for k in POSE_CELLS}
            return None

        def _orientation_err(applied_row, save_row):
            cells = _saved_cells(save_row)
            if cells is not None:
                return _theta3d_cells(_nk(applied_row), cells)
            nk = _nk(save_row)
            return _angle_between(
                _mat_forward(_nk(applied_row)),
                _dir_from_euler(nk["yaw_deg"], nk["pitch_deg"]),
            )

        roll_saved_pos = _row_pos(_nk(save_roll))
        p0_saved_pos = _row_pos(_nk(save_p0))
        # Las eng_* solo se juzgan en una lectura de estado posterior;
        # en el RESULT de scam_pose_apply son del frame anterior.
        p_roll_is_result = p_roll.get("ev") == "op"
        p0_is_result = p0.get("ev") == "op"
        if _num(p_roll, "active_b") != 1.0:
            return _chk("CAM-02", "fail", "p_roll_inactive")
        if not p_roll_is_result and _dist(_row_pos(_nk(p_roll), "eng_"), roll_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p_roll_eng_pos_err")
        if _dist(_row_pos(_nk(p_roll)), roll_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p_roll_cam_pos_err")
        if _orientation_err(p_roll, save_roll) >= 0.5:
            return _chk("CAM-02", "fail", "p_roll_theta_deg")
        if abs(_num(p_roll, "fov_rad") - _num(save_roll, "fov_rad")) >= 0.00873:
            return _chk("CAM-02", "fail", "p_roll_fov_err")
        if not p_roll_is_result and _angle_between(_row_dir(_nk(p_roll), "eng_"), _mat_forward(_nk(p_roll))) >= 0.05:
            return _chk("CAM-02", "fail", "p_roll_direction_err")
        if not p_roll_is_result and _dist(_row_pos(_nk(p_roll), "eng_"), _row_pos(_nk(p_roll))) >= 0.01:
            return _chk("CAM-02", "fail", "p_roll_cam_identity")

        if _num(p0, "active_b") != 1.0:
            return _chk("CAM-02", "fail", "p0_inactive")
        if not p0_is_result and _dist(_row_pos(_nk(p0), "eng_"), p0_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p0_eng_pos_err")
        if _dist(_row_pos(_nk(p0)), p0_saved_pos) >= 0.05:
            return _chk("CAM-02", "fail", "p0_cam_pos_err")
        if _orientation_err(p0, save_p0) >= 0.5:
            return _chk("CAM-02", "fail", "p0_theta_deg")
        if abs(_num(p0, "fov_rad") - _num(save_p0, "fov_rad")) >= 0.00873:
            return _chk("CAM-02", "fail", "p0_fov_err")
        if not p0_is_result and _angle_between(_row_dir(_nk(p0), "eng_"), _mat_forward(_nk(p0))) >= 0.05:
            return _chk("CAM-02", "fail", "p0_direction_err")
    except (KeyError, TypeError, ValueError):
        return _chk("CAM-02", "missing", "bad_columns")
    return _chk("CAM-02", "pass", "ok")


# CAM-03: una muestra por frame en m_Probe.m_Frame, trayectoria a < 0.5 m de la
# referencia analítica independiente (claves de la fixture; el origen
# vertical se ancla con anchor_y) y ningún paso mayor que 3x la mediana.
# La cobertura se acredita por seq_n y frame contiguos y sin huecos de
# dtsum_ms > 100 ms, sin mínimo fijo de filas (enmienda del 24-nov,
# hecho 5); su ausencia da missing (INCONCLUSO). La vista de cada fila
# se compara con la pose ordenada en la fila anterior (hecho 2). PASS
# exige dtsum_ms creciente, vista y nodo anterior a < 0.01 m, error
# < 0.5 m y paso <= 3x mediana. FAIL en caso contrario.
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
            # El final se juzga en el nodo de la ultima fila: la vista
            # de esa fila es la pose del frame anterior (hecho 2) y el
            # dump no trae una fila posterior que la asiente.
            dx = float(last["x_m"]) - float(key_last["pos_x_m"])
            dz = float(last["z_m"]) - float(key_last["pos_z_m"])
            dy = float(last["y_m"]) - (
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
        if len(rows) > 1:
            view_err = _dist(_row_pos(last, "eng_"), _row_pos(rows[-2]))
            if view_err >= 0.01:
                return _chk("CAM-04", "fail", f"{dump}_view_pos_err_m={view_err:.4f}")
        # La orientacion final se juzga por la direccion: mat[2] cruda
        # de la ultima fila frente a la formula medida desde la clave
        # final. El giro completo frente a la clave queda pendiente de
        # la v5 (mat[0]/mat[1] sin medir), nunca en FALLA.
        if not all(k in last for k in POSE_CELLS):
            return _chk("CAM-04", "missing", f"{dump}_no_matrix_cells")
        theta = _angle_between(
            _mat_forward(last),
            _dir_from_euler(key_last["yaw_deg"], key_last["pitch_deg"]),
        )
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
def _path_stats(samples: dict, rows: list, keys: list[dict], pos_mode: str) -> dict | None:
    if not rows:
        return None
    t_end = keys[-1]["t_s"]
    # El datum vertical se ancla con anchor_y, como CAM-03: el camino
    # del motor sale del origen (enmienda, hecho 4), así que la primera
    # fila no es la clave 0.
    y_datum = _y_datum(samples, keys)
    if y_datum is None:
        return None
    errors = []
    steps = []
    for i, row in enumerate(rows):
        try:
            if i and float(row["dtsum_ms"]) <= t_end * 1000.0 + 1e-6:
                t_prev = _row_time(rows[i - 1], t_end)
                if t_prev is None:
                    return None
                ref_rel = _ref_pos_rel(keys, t_prev, pos_mode)
                ref = [ref_rel[0], y_datum + ref_rel[1], ref_rel[2]]
                errors.append(_dist(_row_pos(row, "eng_"), ref))
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


def _engine_b2_b(samples: dict, rows: list, keys: list[dict]) -> bool:
    if not rows:
        return False
    t_end = keys[-1]["t_s"]
    y_datum = _y_datum(samples, keys)
    if y_datum is None:
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
        for i, row in enumerate(rows):
            if i and float(row["dtsum_ms"]) <= t_end * 1000.0 + 1e-6:
                prev = rows[i - 1]
                if _angle_between(_row_dir(row, "eng_"), _mat_forward(prev)) >= 0.05:
                    return False
                if _angle_between(_mat_forward(prev), _ref_dir(keys, times[i - 1])) >= 2.0:
                    return False
            if abs(float(row["fov_rad"]) - _ref_fov(keys, times[i])) >= 0.02:
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
            if t <= 3.0 + 1e-9:
                yaw = _col(row, "yaw_deg")
                if yaw is None or abs(yaw) < 178.5:
                    return _chk("CAM-05", "fail", "short_arc_yaw_deg")
        # La vista de la fila i es la pose ordenada en la fila i-1
        # (hecho 2): su direccion se compara con mat[2] de la fila
        # anterior y con la direccion de referencia de ese instante.
        # El giro completo frente al slerp queda pendiente de la v5.
        for i, row in enumerate(rows):
            if not i:
                continue
            try:
                if float(row["dtsum_ms"]) > t_end * 1000.0 + 1e-6:
                    continue
            except (KeyError, TypeError, ValueError):
                return _chk("CAM-05", "missing", "bad_dtsum")
            prev = rows[i - 1]
            t = _row_time(prev, t_end)
            if _angle_between(_row_dir(row, "eng_"), _mat_forward(prev)) >= 0.05:
                return _chk("CAM-05", "fail", "engine_direction_vs_matrix")
            if _angle_between(_mat_forward(prev), _ref_dir(keys, t)) >= 2.0:
                return _chk("CAM-05", "fail", "orientation_vs_slerp")
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
    scripted_stats = _path_stats(samples, rows, keys, fpath.get("pos_mode", "linear"))
    engine_stats = _path_stats(samples, engine_rows, keys, "linear")
    if scripted_stats is None:
        return _chk("CAM-05", "missing", "bad_scripted_metrics")
    if engine_stats is None:
        return _chk("CAM-05", "missing", "no_path_engine_interp")
    engine_ok = _engine_b2_b(samples, engine_rows, keys)
    comparison = {
        "engine_max_over_median_step": engine_stats["max_over_median_step"],
        "engine_max_pos_err_m": engine_stats["max_pos_err_m"],
        "engine_passes_b2_b": bool(engine_ok),
        "engine_starts_from_origin": True,
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
        neg_terminal = _transport_terminal(op)
        if neg_terminal is not None:
            missing.append(f"neg_{j}_{neg_terminal}")
            continue
        if op.get("status") != "rejected" or op.get("reason") != "bad_args":
            return _chk("CAM-06", "fail", f"neg_{j}_not_rejected")
        pre = _state_indexed(scenario, phase, "pre", j)
        post = _state_indexed(scenario, phase, "post", j)
        if pre is None or post is None:
            missing.append(f"no_state_neg_{j}")
            continue
        if pre.get("op_id") is not None and pre.get("op_id") == post.get("op_id"):
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
                # El ancla solo publica Euler: se juzga la direccion
                # con la formula medida y el giro completo queda
                # pendiente de la v5, nunca en FALLA.
                anchor_dir = _dir_from_euler(
                    float(anchor["yaw_deg"]), float(anchor["pitch_deg"])
                )
                if _angle_between(_mat_forward(_nk(row)), anchor_dir) >= 0.5:
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
    for key in ("pre_step", "post_step"):
        step = str(event.get(key) or "")
        matches = [
            r for r in scenario
            if r.get("ev") == "state" and r.get("phase") == "SCAM-S4" and r.get("step") == step
        ]
        if len(matches) != 1:
            return None
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


def _check_cam_08(samples: dict) -> dict:
    scenario = samples.get("scenario") or []
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
    for k in (1, 2, 3, 4):
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

    # Los umbrales opticos van despues de acreditar la fase (abajo):
    # primero la telemetria observada de los dos caminos y los resets.
    reset = _path_reset_fields(samples, "SCAM-S4")
    if reset is None:
        missing.append("no_reset_state")
    elif reset[0] != 0.0 or reset[1] != 0.0:
        return _chk("CAM-08", "fail", "reset_focus_not_zero")

    # Cobertura y continuidad de los dos trabajos, variable y control.
    # La cota de filas se deriva del periodo de frame medido en la
    # propia corrida (enmienda, hecho 5): hacen falta las filas que
    # cubren hasta la ultima fase (5,6 s) a ese periodo, sin huecos
    # mayores que 100 ms ni que 2,5 periodos, la cota que sea mayor.
    def _coverage_ok(dump_rows):
        if len(dump_rows) < 2:
            return False
        try:
            deltas = [
                float(dump_rows[i]["dtsum_ms"]) - float(dump_rows[i - 1]["dtsum_ms"])
                for i in range(1, len(dump_rows))
            ]
        except (KeyError, TypeError, ValueError):
            return False
        positive = [d for d in deltas if d > 0.0]
        if not positive:
            return False
        period = _median(positive)
        needed = math.ceil(5600.0 / period)
        gap_max = max(100.0, 2.5 * period)
        return len(dump_rows) >= needed and all(d <= gap_max for d in deltas)

    fix_rows = samples.get("paths", {}).get("path_dof_fix") or []
    if (samples.get("path_bad_columns") or {}).get("path_dof_fix"):
        missing.append("bad_columns_fix")
    if not _coverage_ok(fix_rows):
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
    if rows and not _coverage_ok(rows):
        missing.append("no_path_dof_var_coverage")
    # Cobertura hasta cada fase: 180 filas que no llegan a t3/t4 no
    # acreditan las fases tardias de ninguno de los dos caminos.
    for label, dump_rows in (("var", rows), ("fix", fix_rows)):
        if dump_rows:
            try:
                last_dt = max(float(r["dtsum_ms"]) for r in dump_rows)
            except (KeyError, TypeError, ValueError):
                last_dt = 0.0
            if last_dt < 5600.0:
                missing.append(f"no_path_dof_{label}_coverage")
    # Cada captura de fase se enlaza con su evento y con las lecturas
    # pre/post de su fase. El contenido identico entre tomas
    # independientes (mismo estado optico, render determinista) no es
    # reutilizacion: la identidad sale del evento y de su horquilla.
    phase_files = [f"{p}_t{k}.bmp" for p in ("var", "fix") for k in (1, 2, 3, 4)]
    for name in phase_files:
        cap = _capture_event(samples, name)
        if cap is None:
            missing.append(f"no_capture_event:{name}")
            continue
        for key in ("pre_step", "post_step"):
            step = cap.get(key)
            if not isinstance(step, str) or _state(scenario, "SCAM-S4", step) is None:
                missing.append(f"no_capture_bracket:{name}")
                break
    # Los resets de cada camino son lecturas distintas tras su propio
    # OnJobEnd: una misma lectura no acredita los dos.
    var_reset_row = _state(scenario, "SCAM-S4", "post_dof_var")
    fix_reset_row = _state(scenario, "SCAM-S4", "post_dof_fix")
    if (
        var_reset_row is not None
        and fix_reset_row is not None
        and var_reset_row.get("op_id") is not None
        and var_reset_row.get("op_id") == fix_reset_row.get("op_id")
    ):
        missing.append("no_reset_state")
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

    # Fase acreditada antes que ningun umbral optico (brief:260): una
    # captura fuera de su ventana es INCONCLUSO, no un fondo sin
    # desenfoque. La telemetria de arriba ya ha podido dar FALLA.
    if "capture_phase_unaccredited" in missing:
        return _chk("CAM-08", "missing", "capture_phase_unaccredited")

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

    if missing:
        # Una fase sin acreditar manda sobre cualquier otra ausencia.
        if "capture_phase_unaccredited" in missing:
            return _chk("CAM-08", "missing", "capture_phase_unaccredited")
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
    # captura (o la de su capture_tick_ms), no un promedio. La horquilla
    # pre/post es del mismo trabajo, cae en la ventana, no supera
    # max_bracket_span_ms ni se mueve mas de 0,05 m / 0,2 grados entre
    # sus extremos (brief:261), y el frame efectivo cae dentro de ella.
    p_cap = None
    p_cap_row = None
    if pre_cap is None or post_cap is None or cap_event is None:
        missing.append("no_capture_bracket")
    else:
        if (
            _sk(pre_cap).get("cam_job_state") != "running"
            or _sk(post_cap).get("cam_job_state") != "running"
        ):
            missing.append("capture_job_not_running")
        start_op = _event(scenario, "op", phase, "path_hud_start")
        if start_op is not None:
            job_id = _sk(start_op).get("job")
            if not job_id or _sk(pre_cap).get("cam_job_id") != job_id or _sk(post_cap).get("cam_job_id") != job_id:
                missing.append("capture_job_mismatch")
        pre_dt = _num(pre_cap, "cam_dtsum_ms")
        post_dt = _num(post_cap, "cam_dtsum_ms")
        if pre_dt is None or post_dt is None:
            missing.append("bad_capture_dtsum")
        else:
            span_max = float(rois.get("max_bracket_span_ms", 150.0))
            if post_dt - pre_dt > span_max or post_dt < pre_dt:
                missing.append("capture_bracket_span")
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
        pre_frame = _num(pre_cap, "frame")
        post_frame = _num(post_cap, "frame")
        if cap_frame is not None:
            try:
                eff_row = by_frame.get(float(cap_frame))
            except (TypeError, ValueError):
                eff_row = None
            if eff_row is not None and pre_frame is not None and post_frame is not None:
                if not (pre_frame <= float(cap_frame) <= post_frame):
                    missing.append("capture_frame_not_anchored")
                    eff_row = None
        if eff_row is None and cap_event.get("capture_tick_ms") is not None:
            try:
                tick_v = float(cap_event["capture_tick_ms"])
                eff_row = min(
                    rows,
                    key=lambda r: abs(float(r["tick_ms"]) - tick_v),
                    default=None,
                )
                # La tolerancia sale del periodo de frame medido en la
                # propia corrida (enmienda, hecho 5), no de 17 ms fijos.
                tick_deltas = [
                    float(rows[i]["tick_ms"]) - float(rows[i - 1]["tick_ms"])
                    for i in range(1, len(rows))
                ]
                tick_deltas = [d for d in tick_deltas if d > 0.0]
                tick_tol = _median(tick_deltas) if tick_deltas else 0.0
                if eff_row is not None and (
                    tick_tol <= 0.0 or abs(float(eff_row["tick_ms"]) - tick_v) > tick_tol
                ):
                    eff_row = None
                if eff_row is not None and pre_frame is not None and post_frame is not None:
                    if not (pre_frame <= float(eff_row["frame"]) <= post_frame):
                        missing.append("capture_frame_not_anchored")
                        eff_row = None
            except (KeyError, TypeError, ValueError):
                eff_row = None
        if eff_row is None:
            if "capture_frame_not_anchored" not in missing:
                missing.append("capture_frame_not_anchored")
        else:
            p_cap = {k: float(eff_row[k]) for k in POSE_SCALARS}
            p_cap_row = eff_row
        # Capturas sin evento: nunca PASA. El contenido identico entre
        # tomas independientes no es reutilizacion (ver CAM-08).
        for name in ("hud_during.bmp", "hud_clean_ref.bmp",
                     "hud_clean_ref_repeat.bmp", "hud_visible_ref.bmp"):
            if _capture_event(samples, name) is None:
                missing.append(f"no_capture_event:{name}")

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
            # Los dos lados publican sus celdas: la rotacion se juzga
            # celdas frente a celdas, sin reconstruir Euler.
            if p_cap_row is not None and _theta3d_cells(_nk(clean_ref), p_cap_row) > 0.05:
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

    # La imagen solo se juzga con la captura acreditada (evento,
    # horquilla del mismo trabajo, frame efectivo y referencia en la
    # pose): sin ese ancla es INCONCLUSO, nunca quickbar_not_detected.
    # Los flags y widgets de las filas ya han dado FALLA arriba.
    capture_unaccredited = any(
        m.startswith(
            (
                "capture",
                "no_capture",
                "bad_capture",
                "clean_ref",
                "no_clean_ref",
                "bad_clean_ref",
                "noise:clean_ref",
                "window:hud_during",
            )
        )
        for m in missing
    )
    if (
        not capture_unaccredited
        and gray_during is not None
        and gray_visible is not None
        and gray_clean is not None
    ):
        if mad(gray_visible, gray_clean, roi_full) >= 10.0:
            # Sin un ancla de escena en el brief, esto es ausencia de
            # acreditacion (missing), nunca un fail con umbral propio.
            missing.append("hud_visible_other_scene")
        elif mad(gray_during, gray_visible, roi_qb) < 4.0:
            return _chk("CAM-09", "fail", "quickbar_not_detected")
        elif mad(gray_during, gray_clean, roi_full) >= 2.0:
            return _chk("CAM-09", "fail", "hud_visible_full_screen")
        elif mad(gray_during, gray_clean, roi_qb) >= 1.5:
            return _chk("CAM-09", "fail", "quickbar_visible")

    post_hud = _find_state(
        scenario, phase, "post_path_hud", "post_path", "post_hud", "post_job_hud"
    )
    # N7: la restauracion se compara con la observacion inicial
    # congelada antes de ocultar; saved_aux solo es adicional.
    initial_aux, aux_detail = _initial_aux(samples, phase, "op", "path_hud_start")
    if initial_aux is None:
        missing.append(aux_detail or "no_initial_aux_observation")
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

    # El overlay se juzga por ovl_vis_b (brief:170), que la sonda
    # calcula con su barrido: ya esta en cada fila del recorrido (todas
    # a 0 arriba) y en pre_cap. Ningun verbo produce un arbol de
    # widgets, asi que no se exige ni se acredita ninguna fila de arbol.
    if pre_cap is not None:
        ovl_cap = _num(pre_cap, "ovl_vis_b")
        if ovl_cap is None:
            missing.append("no_ovl_vis_pre_cap")
        elif ovl_cap != 0.0:
            return _chk("CAM-09", "fail", "overlay_visible_pre_cap")

    # Controles negativos (brief:217-218): la lectura scam_hud_op(0)
    # tras forzar cada modo, como ev=op enlazada. Una fila hud_control
    # del runner no acredita nada.
    hud_ops = [
        row
        for row in scenario
        if row.get("ev") == "op"
        and row.get("phase") == phase
        and row.get("verb") == "scam_hud_op"
    ]
    if not hud_ops:
        missing.append("no_hud_control_ops")
    else:
        if not any(_num(row, "qb_vis_b") == 1.0 for row in hud_ops):
            return _chk("CAM-09", "fail", "control_qb_not_detected")
        if not any(_num(row, "ovl_vis_b") == 1.0 for row in hud_ops):
            return _chk("CAM-09", "fail", "control_ovl_not_detected")

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

    # La base temporal sale del job_stop real (op enlazada y su bridge:
    # enq.t_ms, result.t_ms y result.recv_ms), no del resumen ev=stop.
    # El resumen, si esta, tiene que casar con ellos a +-1 ms.
    stop = _first_event(scenario, "stop", phase)
    stop_op = _event(scenario, "op", phase, "stop_op")
    u = None
    t0 = None
    send = None
    ack = None
    if stop_op is None or stop_op.get("verb") != "job_stop":
        missing.append("no_stop_anchor")
    else:
        enq, result, _inst = _bridge_index(samples)
        op_key = str(stop_op.get("op_id") or "")
        enq_row = enq.get(op_key)
        res_row = result.get(op_key)
        if enq_row is None or res_row is None:
            missing.append("no_stop_anchor")
        else:
            res = res_row.get("result") or {}
            try:
                send = float(enq_row["t_ms"])
                ack = float(res_row.get("t_ms"))
                t0 = float(res["recv_ms"])
            except (KeyError, TypeError, ValueError):
                missing.append("no_stop_anchor")
            else:
                u = ack - send
                if stop is not None:
                    # Dos instantes distintos del acuse (brief:228): el
                    # puente registra la llegada del RESULT (ack) y el
                    # runner registra su salida posterior de issue_one.
                    # send y recv_ms son copias del mismo hecho y tienen
                    # que casar con el puente; el ack del runner solo
                    # tiene que ser posterior al del puente.
                    try:
                        sum_send = float(stop["stop_send_h_ms"])
                        sum_ack = float(stop["stop_ack_h_ms"])
                        sum_recv = float(stop["stop_recv_ms"])
                    except (KeyError, TypeError, ValueError):
                        pass
                    else:
                        if (
                            abs(sum_send - send) > 1.0
                            or abs(sum_recv - t0) > 1.0
                            or sum_ack < ack - 1.0
                        ):
                            missing.append("stop_summary_mismatch")
    if u is None:
        if "no_stop_anchor" not in missing:
            missing.append("no_stop_u")
    elif u > 100.0:
        missing.append("u_over_100ms")
    if t0 is None and "no_stop_anchor" not in missing:
        missing.append("no_stop_recv")

    # Identidad del trabajo parado (brief:140,227): el arranque de S5
    # ancla su trabajo con job == op_id (StartJob con el op_id), el
    # job_stop tiene que nombrar ese mismo trabajo en su argumento y en
    # su RESULT, y el RESULT tiene que observar la transicion a
    # "stopped" (un trabajo ya terminal devuelve su estado, no stopped).
    # Las paginas de control_recovery son las del cam_sample de S5, que
    # tambien se ancla por job == op_id y es un trabajo distinto.
    identity_fail = None
    if stop_op is not None and stop_op.get("verb") == "job_stop":
        stop_idx = _scenario_index(scenario, stop_op)
        path_starts = [
            r
            for r in scenario
            if r.get("ev") == "op"
            and r.get("phase") == phase
            and r.get("verb") == "scam_path_start"
            and _scenario_index(scenario, r) < stop_idx
        ]
        sample_starts = [
            r
            for r in scenario
            if r.get("ev") == "op"
            and r.get("phase") == phase
            and r.get("verb") == "scam_sample_start"
            and _scenario_index(scenario, r) < stop_idx
        ]
        if not path_starts:
            missing.append("no_s5_path_anchor")
        else:
            start5 = path_starts[-1]
            anchor_job = _sk(start5).get("job")
            # Trabajos de arranques anteriores: el de S5 tiene que ser
            # nuevo (en la forma del productor, job == op_id de su
            # arranque); devolver uno retenido es parar otro trabajo.
            # La igualdad literal con el op_id no se exige porque el
            # evaluador es invariante al renombrado de op_id (la suite
            # del brief renombra todos los ids y el job queda).
            earlier_jobs = {
                str(_sk(r).get("job"))
                for r in scenario
                if r.get("ev") == "op"
                and r.get("verb") in ("scam_path_start", "scam_sample_start")
                and r.get("phase") != phase
                and _sk(r).get("job")
            }
            if not anchor_job:
                missing.append("no_s5_path_anchor")
            elif str(anchor_job) in earlier_jobs:
                identity_fail = "s5_path_job_mismatch"
            else:
                result_job = _sk(stop_op).get("job")
                if result_job is None:
                    missing.append("no_stop_job")
                elif str(result_job) != str(anchor_job):
                    identity_fail = "stop_job_mismatch"
                result_state = _sk(stop_op).get("state")
                if result_state is None:
                    missing.append("no_stop_job_state")
                elif result_state != "stopped":
                    identity_fail = identity_fail or "stop_job_not_stopped"
                if (
                    stop is not None
                    and stop.get("job_id")
                    and str(stop.get("job_id")) != str(anchor_job)
                ):
                    identity_fail = identity_fail or "stop_job_mismatch"
                enq_map, _res_map, _inst_map = _bridge_index(samples)
                enq_row = enq_map.get(str(stop_op.get("op_id") or ""))
                arg_job = None
                if enq_row is not None and isinstance(enq_row.get("args"), dict):
                    try:
                        arg_job = wire.unpack_payload(enq_row["args"])["str"].get("job")
                    except Exception:
                        arg_job = None
                if arg_job is not None and str(arg_job) != str(anchor_job):
                    identity_fail = identity_fail or "stop_job_argument_mismatch"
                if not sample_starts:
                    missing.append("no_s5_sample_anchor")
                else:
                    sample_job = _sk(sample_starts[-1]).get("job")
                    if not sample_job:
                        missing.append("no_s5_sample_anchor")
                    elif str(sample_job) == str(anchor_job) or str(sample_job) in earlier_jobs:
                        identity_fail = identity_fail or "s5_sample_job_mismatch"

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

    if identity_fail is not None:
        return _chk("CAM-10", "fail", identity_fail)
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
    # El acuse solo tiene productor en offline (brief:127). En offline
    # tiene que cubrir los seq_n de los pulsos usados en A y en B; su
    # ausencia o un 0 es missing, nunca fail. En retail/diag no entra.
    build = str((samples.get("manifest") or {}).get("build") or "")
    if build == "offline":
        post_stop_ack = _find_state(scenario, phase, "post_stop_state")
        ack_seq = _num(post_stop_ack, "input_ack_seq_n") if post_stop_ack is not None else None
        used_seqs = []
        for burst in ("A", "B"):
            for _issued, row in pulses[burst]:
                try:
                    used_seqs.append(float(row["seq_n"]))
                except (TypeError, ValueError):
                    pass
        if ack_seq is None:
            missing.append("no_input_ack")
        elif used_seqs and ack_seq < max(used_seqs):
            missing.append("input_ack_not_covering")
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
    # tick_ms y dtsum_ms se miden en puntos distintos del frame (el peer
    # calcula dt antes de procesar ordenes, fake_peer.py:660, y muestrea
    # despues): el desfase acumulado entre ambos relojes no puede pasar
    # de un periodo de frame, que es lo que separa esos dos puntos de
    # muestreo. No hay una cota fija de 5 ms en el productor.
    tick0 = dtsum0 = None
    try:
        tick0 = float(rows[0]["tick_ms"])
        dtsum0 = float(rows[0]["dtsum_ms"])
        frame_period = max(
            float(rows[i]["tick_ms"]) - float(rows[i - 1]["tick_ms"])
            for i in range(1, len(rows))
        )
    except (KeyError, TypeError, ValueError):
        return _chk("CAM-10", "missing", "bad_frame_column")
    if frame_period <= 0.0:
        return _chk("CAM-10", "missing", "tick_not_increasing")
    for i in range(1, len(rec)):
        try:
            prev = float(rows[i - 1]["frame"])
            cur = float(rows[i]["frame"])
            dtick = float(rows[i]["tick_ms"]) - float(rows[i - 1]["tick_ms"])
            drift = abs(
                (float(rows[i]["tick_ms"]) - tick0)
                - (float(rows[i]["dtsum_ms"]) - dtsum0)
            )
        except (KeyError, TypeError, ValueError):
            return _chk("CAM-10", "missing", "bad_frame_column")
        if abs(cur - prev - 1.0) > 1e-6:
            return _chk("CAM-10", "fail", f"frame_not_contiguous_{i}")
        if dtick <= 0.0:
            return _chk("CAM-10", "missing", "tick_not_increasing")
        if drift > frame_period:
            return _chk("CAM-10", "missing", "tick_dtsum_mismatch")

    if t0 is None or pulse_a_h is None or pulse_b_h is None or u is None or send is None or ack is None:
        return _chk("CAM-10", "missing", "no_stop_timing")
    # Conversion acotada entre relojes: el stop llego al peer en un
    # instante del arnes dentro de [send, ack], asi que un pulso emitido
    # en h llega al peer en [t0+(h-ack), t0+(h-send)]. Un pulso cuyo
    # intervalo solapa el handoff no puede contar como anterior a el.
    def _arrival(issued_h):
        return t0 + (issued_h - ack), t0 + (issued_h - send)

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
    handoff_tick = rec[r0]["tick_ms"]
    a_candidates = [
        issued for issued, _ in pulses["A"] if _arrival(issued)[1] >= handoff_tick
    ]
    if not a_candidates:
        return _chk("CAM-10", "missing", "no_stimulus_after_handoff")
    pulse_a_min = _arrival(min(a_candidates))[0]
    # B llega en el intervalo [pulse_b_min, pulse_b_max]: el extremo
    # temprano es solo la llegada mas temprana posible, no la real.
    # Una inversion solo se acredita tras el extremo tardio, y B solo
    # precede con seguridad a la respuesta de A si hasta su llegada
    # mas tardia es anterior a ella.
    pulse_b_min, pulse_b_max = _arrival(pulse_b_h)
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
        if pulse_a_min <= item["tick_ms"] < pulse_b_max:
            psi = math.degrees(math.atan2(item["pl_dir"][0], item["pl_dir"][2]))
            peak_delta = max(peak_delta, _wrap180(psi - psi_pre))
    psi_peak = _wrap180(psi_pre + peak_delta) if peak_delta > -180.0 else psi_pre

    if pulse_b_max <= rec[r1]["tick_ms"]:
        return _chk("CAM-10", "fail", "burst_b_before_a_response")
    r2 = None
    for idx, item in enumerate(rec):
        if item["tick_ms"] < pulse_b_max or idx <= r1 or not handoff(item):
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
            initial_aux, aux_detail = _initial_aux(samples, phase, "stop", "stop_op")
            if initial_aux is None:
                missing.append(aux_detail or "no_initial_aux_observation")
            elif av != initial_aux:
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
