"""Evaluador determinista y ciego de evidencia del spike S-mapa (F0.3).

Lee exclusivamente ``<part_dir>/manifest.json`` y ``<part_dir>/samples/``:

1. ``samples/bridge.jsonl`` — traza JSONL del puente HTTP local:
   - ``ev == "hello"`` (``peer == "server"``, ``http == 200``, ``ok == True``):
     ``args.proto == "qa0"``, ``args.build`` (debe coincidir con ``manifest.build``),
     ``args.probe_ver == "dsbx-qa1+<probe_stamp_16hex>"``.
   - ``ev == "enq"``, ``ev == "poll"``, ``ev == "result"``:
     Cada orden ejecutada debe tener su tripleta ``enq`` -> ``poll`` -> ``result``
     con ``body_len <= wire_cap`` (donde ``wire_cap`` proviene de
     ``manifest.identity.params.wire_cap``, verificado contra el ``wire.py``
     historico en ``manifest.identity.git_head``).
   - Verbos evaluados y lecturas crudas del motor en ``result.read``:
     * ``map_world_read``:
       - ``args``: ``sk=["mode_id"]`` (``"grid_row"`` o ``"patch_row"``),
         ``nk=["x0_m","z0_m","step_m","row_n","chunk_n"]`` (metros y conteos).
       - ``read.sk``: ``world_name`` (``g_Game.GetWorldName()``), ``mode_id``.
       - ``read.nk``: ``world_size_m`` (``g_Game.GetWorld().GetWorldSize()`` [m]),
         ``sea_level_m`` (``g_Game.SurfaceGetSeaLevel()`` [m]), ``x0_m`` [m],
         ``z0_m`` [m], ``step_m`` [m], ``row_n``, ``tick_ms`` (``g_Game.GetTime()`` [ms]),
         ``frame`` (contador de tick del servidor).
       - ``read.ncol``: ``["y_m", "sea_b"]`` con ``rows == chunk_n``:
         ``y_m`` es ``g_Game.SurfaceY(x, z)`` [m] en ``float`` canonico sin
         cuantizacion adicional (N29, N30); ``sea_b`` es ``1.0`` si
         ``g_Game.SurfaceIsSea(x, z) || y_m <= sea_level_m``, ``0.0`` en tierra.
     * ``map_feature_locate``:
       - ``args``: ``sk=["point_id","feature_kind","mode_id"]``,
         ``nk=["x_min_m","z_min_m","x_max_m","z_max_m"]`` en ``"calibrate"`` y
         ``["req_x_m","req_z_m","x_min_m","z_min_m","x_max_m","z_max_m"]`` en ``"verify"``.
       - ``read.sk``: ``point_id``, ``mode_id``, ``decision_id``
         (``"located"``/``"verified"``/``"rejected"``), ``reject_reason_id``.
       - ``read.nk``: ``req_x_m`` [m], ``req_z_m`` [m], ``srv_feature_found_b`` (0/1),
         ``srv_x_m`` [m], ``srv_y_m`` [m], ``srv_z_m`` [m], ``prominence_m`` [m],
         ``err_xz_m`` [m], ``err_reflected_z_m`` [m], ``tick_ms`` [ms], ``frame``.
         Proveniencia: malla 16x16 evaluada con ``SurfaceY`` y ``SurfaceIsSea`` en el
         servidor (centroide de ``M_srv`` con ``y >= y_max - 0.5`` en ``relief_peak`` o
         punto medio ``k* - 0.5`` en ``coast_ns``/``coast_ew``).
       - ``read.ncol``: ``["sx_m","sz_m","y_m","sea_b"]`` (``rows == 2`` muestras de
         auditoria que deben pertenecer a las 256 muestras crudas del parche).
     * ``map_place_ground``:
       - ``args``: ``sk=["point_id","class_id"]``, ``nk=["req_x_m","req_z_m"]`` [m].
       - ``read.sk``: ``point_id``, ``decision_id`` (``"placed"``/``"rejected"``),
         ``reject_reason_id``, ``hit_class_id`` (``g_Game.ObjectGetType(hitObj, ...)``),
         ``obs_class_id`` (``g_Game.ObjectGetType(obj, ...)``).
       - ``read.nk``: ``req_x_m`` [m], ``req_z_m`` [m],
         ``terrain_y_m`` (``g_Game.SurfaceY`` [m]),
         ``road_y_m`` (``g_Game.SurfaceRoadY`` [m]),
         ``ray_hit_b`` (0/1 de ``RaycastRVProxy`` / ``RayCastBullet``),
         ``hit_y_m`` [m], ``seq_pre_n`` y ``seq_post_n`` (contador monotonico
         ``m_SpawnSeqN`` de ``SpawnTrackedObject``), ``ent_id_n`` (``obj.GetID()``,
         admite ``0``), ``obs_x_m``/``obs_y_m``/``obs_z_m`` (``obj.GetPosition()`` [m]),
         ``bbox_min_y_m``/``bbox_max_y_m`` (``obj.ClippingInfo`` [m]),
         ``obs_surf_y_m`` (``g_Game.SurfaceY(obs_x_m, obs_z_m)`` [m]),
         ``pre_count_n``/``post_count_n`` (``g_Game.GetObjectsAtPosition``),
         ``tick_ms`` [ms], ``frame``.

2. ``samples/scenario.jsonl`` — pasos ejecutados por el runner:
   Cada fila contiene ``step`` (``"world_and_relief_read"``, ``"calibrate_C1_C3"``,
   ``"verify_and_place_V1_V3"``, ``"place_ground_P_GROUND"``, ``"neg_inverted_axis"``,
   ``"neg_out_of_map"``, ``"neg_bridge"``, ``"neg_roof"``), ``op_ids`` (lista de
   identificadores opacos enlazados a ``bridge.jsonl``), ``t_start_h_ms``,
   ``t_end_h_ms`` y ``elapsed_h_ms`` en el reloj monotonico del arnes (``h_ms``).

3. ``samples/chernarus_local.png`` — imagen PNG local en escala de grises de 8 bits
   (``width_px = 4096``, ``height_px = 4096``, ``bit_depth = 8``, ``color_type = 0``).

4. ``samples/map_provenance.json`` — manifiesto ``dsbx.map.provenance.v4`` con
   hashes SHA-256 de imagen, fixture y captura certificadora, ``source_kind``,
   ``crs == "CRS.Simple"``, ``tile_urls == []``, ``external_domains == []``,
   ``grid_op_ids`` y ``patch_op_ids``.

5. ``samples/s_mapa_puntos.json`` — copia local de la fixture ``dsbx.map.fixture.v4``
   con ``calibration_points`` (``C1..C3``), ``verification_points`` (``V1..V3``),
   ``placement_points`` (``P_GROUND``, ``P_OUT``, ``P_BRIDGE``, ``P_ROOF``) y
   ``accreditation``.

6. ``samples/s_mapa_certifying_capture.json`` — captura certificadora
   ``dsbx.map.certifying_capture.v4`` con ``certifying_git_head``,
   ``certifying_probe_stamp``, ``certifying_hello``, ``global_luma_range``,
   ``patches`` (256 muestras crudas y luminancias de ``C1..C3`` y ``V1..V3``),
   ``surfaces`` (mediciones de ``P_GROUND``, ``P_OUT``, ``P_BRIDGE``, ``P_ROOF``)
   y las ordenes y resultados certificadores conservados (N31).
"""

from __future__ import annotations

import binascii
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import zlib

import f03_common
import gate_core
import wire


SPIKE_ID = "S-mapa"
CHECK_IDS = (
    "MAP-01",
    "MAP-02",
    "MAP-03",
    "MAP-04",
    "MAP-05",
    "MAP-06",
    "MAP-07",
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
CAL_IDS = ("C1", "C2", "C3")
VER_IDS = ("V1", "V2", "V3")
PATCH_IDS = ("C1", "C2", "C3", "V1", "V2", "V3")
SURFACE_IDS = ("P_GROUND", "P_OUT", "P_BRIDGE", "P_ROOF")
HEX_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
HEX_STAMP_RE = re.compile(r"^[0-9a-f]{16}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_finite_num(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def quantize_luma(y_m: float, sea_b: float, y_min_m: float, y_max_m: float) -> int:
    """Convierte (y_m, sea_b) en luminancia 0..255 segun §4.1(2)."""
    if sea_b == 1.0:
        return 0
    span = y_max_m - y_min_m
    if span <= 0.0:
        return 1
    scaled = 1.0 + 254.0 * (y_m - y_min_m) / span
    val = int(math.floor(scaled + 0.5))
    return min(255, max(1, val))


def detect_image_feature(
    img_or_patch: list[list[int]] | list[int] | bytes,
    roi_px: list[int] | tuple[int, int, int, int],
    feature_kind: str,
) -> tuple[float, float] | None:
    """Detector de rasgo sobre submatriz 16x16 de luminancia (§4.2(1))."""
    if not isinstance(roi_px, (list, tuple)) or len(roi_px) != 4:
        return None
    u0, v0, u1, v1 = (int(roi_px[0]), int(roi_px[1]), int(roi_px[2]), int(roi_px[3]))
    if u1 - u0 != 15 or v1 - v0 != 15 or u0 < 0 or v0 < 0:
        return None

    patch: list[list[int]] = []
    if isinstance(img_or_patch, (bytes, bytearray)):
        if len(img_or_patch) != 256:
            return None
        for r in range(16):
            patch.append([int(img_or_patch[r * 16 + c]) for c in range(16)])
    elif isinstance(img_or_patch, list) and len(img_or_patch) == 256 and all(isinstance(x, int) for x in img_or_patch):
        for r in range(16):
            patch.append([int(img_or_patch[r * 16 + c]) for c in range(16)])
    elif isinstance(img_or_patch, list) and len(img_or_patch) == 16 and all(
        isinstance(row, (list, bytes, bytearray)) and len(row) == 16 for row in img_or_patch
    ):
        for r in range(16):
            patch.append([int(img_or_patch[r][c]) for c in range(16)])
    elif isinstance(img_or_patch, list) and len(img_or_patch) > v1:
        for r in range(16):
            row_src = img_or_patch[v0 + r]
            if not isinstance(row_src, (list, bytes, bytearray)) or len(row_src) <= u1:
                return None
            patch.append([int(row_src[u0 + c]) for c in range(16)])
    else:
        return None

    if feature_kind == "relief_peak":
        min_p = min(patch[r][c] for r in range(16) for c in range(16))
        if min_p < 1:
            return None
        i_max = max(patch[r][c] for r in range(16) for c in range(16))
        i_border = max(
            patch[r][c]
            for r in range(16)
            for c in range(16)
            if r in (0, 15) or c in (0, 15)
        )
        if i_max - i_border < 4:
            return None
        m_px = [
            (r, c)
            for r in range(1, 15)
            for c in range(1, 15)
            if patch[r][c] >= i_max - 1
        ]
        if not (1 <= len(m_px) <= 9):
            return None
        c_bar = sum(c for _, c in m_px) / float(len(m_px))
        r_bar = sum(r for r, _ in m_px) / float(len(m_px))
        return (float(u0) + c_bar, float(v0) + r_bar)

    if feature_kind in ("coast_ns", "coast_ew"):
        if feature_kind == "coast_ns":
            seq = [patch[k][8] for k in range(16)]
        else:
            seq = [patch[8][k] for k in range(16)]
        candidates = [
            k_star
            for k_star in range(3, 14)
            if all(seq[k] >= 1 for k in range(0, k_star))
            and all(seq[k] == 0 for k in range(k_star, 16))
        ]
        if len(candidates) != 1:
            return None
        k_star = candidates[0]
        if feature_kind == "coast_ns":
            return (float(u0) + 8.0, float(v0) + float(k_star) - 0.5)
        return (float(u0) + float(k_star) - 0.5, float(v0) + 8.0)

    return None


def locate_world_feature_from_patch(
    samples_256: list[tuple[float, float]] | list[list[float]],
    world_roi_m: list[float] | tuple[float, float, float, float],
    feature_kind: str,
    sea_level_m: float = 0.0,
) -> dict[str, object] | None:
    """Reconstruye el rasgo fisico en coordenadas del mundo desde las 256 muestras (§4.2(1), N30)."""
    if not isinstance(samples_256, list) or len(samples_256) != 256:
        return None
    if not isinstance(world_roi_m, (list, tuple)) or len(world_roi_m) != 4:
        return None
    x_min, z_min, x_max, z_max = (
        float(world_roi_m[0]),
        float(world_roi_m[1]),
        float(world_roi_m[2]),
        float(world_roi_m[3]),
    )
    if abs((x_max - x_min) - 56.25) > 1e-3 or abs((z_max - z_min) - 56.25) > 1e-3:
        return None

    grid: list[list[tuple[float, float]]] = []
    for r in range(16):
        row_items: list[tuple[float, float]] = []
        for c in range(16):
            cell = samples_256[r * 16 + c]
            if not isinstance(cell, (list, tuple)) or len(cell) != 2:
                return None
            y_val, sea_val = cell[0], cell[1]
            if not (_is_finite_num(y_val) and _is_finite_num(sea_val)):
                return None
            y_f = float(y_val)
            sea_f = float(sea_val)
            if sea_f not in (0.0, 1.0):
                return None
            if y_f <= sea_level_m and sea_f != 1.0:
                return None
            row_items.append((y_f, sea_f))
        grid.append(row_items)

    if feature_kind == "relief_peak":
        if any(grid[r][c][1] != 0.0 for r in range(16) for c in range(16)):
            return None
        y_max = max(grid[r][c][0] for r in range(16) for c in range(16))
        border_cells = [
            (r, c, grid[r][c][0])
            for r in range(16)
            for c in range(16)
            if r in (0, 15) or c in (0, 15)
        ]
        y_border = max(val for _, _, val in border_cells)
        prominence_m = y_max - y_border
        if prominence_m < 5.0:
            return None
        m_srv = [
            (r, c)
            for r in range(1, 15)
            for c in range(1, 15)
            if grid[r][c][0] >= y_max - 0.5
        ]
        if not (1 <= len(m_srv) <= 9):
            return None
        srv_x_m = sum(x_min + 3.75 * float(c) for _, c in m_srv) / float(len(m_srv))
        srv_z_m = sum(z_max - 3.75 * float(r) for r, _ in m_srv) / float(len(m_srv))
        return {
            "srv_feature_found_b": 1.0,
            "srv_x_m": srv_x_m,
            "srv_y_m": y_max,
            "srv_z_m": srv_z_m,
            "prominence_m": prominence_m,
            "y_border_m": y_border,
            "m_srv": m_srv,
        }

    if feature_kind in ("coast_ns", "coast_ew"):
        if feature_kind == "coast_ns":
            line = [grid[k][8] for k in range(16)]
        else:
            line = [grid[8][k] for k in range(16)]
        candidates = [
            k_star
            for k_star in range(3, 14)
            if all(line[k][1] == 0.0 for k in range(0, k_star))
            and all(line[k][1] == 1.0 for k in range(k_star, 16))
        ]
        if len(candidates) != 1:
            return None
        k_star = candidates[0]
        y_land = line[k_star - 1][0]
        step_shore = y_land - sea_level_m
        if step_shore < 0.20:
            return None
        if feature_kind == "coast_ns":
            srv_x_m = x_min + 30.0
            srv_z_m = z_max - (float(k_star) - 0.5) * 3.75
            audit_0 = (srv_x_m, z_max - float(k_star - 1) * 3.75, y_land, 0.0)
            audit_1 = (srv_x_m, z_max - float(k_star) * 3.75, line[k_star][0], 1.0)
        else:
            srv_x_m = x_min + (float(k_star) - 0.5) * 3.75
            srv_z_m = z_max - 30.0
            audit_0 = (x_min + float(k_star - 1) * 3.75, srv_z_m, y_land, 0.0)
            audit_1 = (x_min + float(k_star) * 3.75, srv_z_m, line[k_star][0], 1.0)
        return {
            "srv_feature_found_b": 1.0,
            "srv_x_m": srv_x_m,
            "srv_y_m": y_land,
            "srv_z_m": srv_z_m,
            "prominence_m": step_shore,
            "k_star": k_star,
            "audit_pair": (audit_0, audit_1),
        }

    return None


def det_2d(
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> float:
    """Determinante 2D (doble del area signada) de tres puntos."""
    return (p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1])


def solve_affine_2d(
    px_pts: list[tuple[float, float]],
    world_pts: list[tuple[float, float]],
) -> tuple[list[list[float]], list[float]] | None:
    """Resuelve [x, z]^T = A [u, v]^T + b sobre 3 puntos no colineales."""
    if len(px_pts) != 3 or len(world_pts) != 3:
        return None
    (u1, v1), (u2, v2), (u3, v3) = px_pts
    (x1, z1), (x2, z2), (x3, z3) = world_pts
    delta = det_2d((u1, v1), (u2, v2), (u3, v3))
    if abs(delta) < 1e-6:
        return None
    du2, dv2 = u2 - u1, v2 - v1
    du3, dv3 = u3 - u1, v3 - v1
    dx2, dz2 = x2 - x1, z2 - z1
    dx3, dz3 = x3 - x1, z3 - z1

    a11 = (dx2 * dv3 - dx3 * dv2) / delta
    a12 = (du2 * dx3 - du3 * dx2) / delta
    b_x = x1 - a11 * u1 - a12 * v1

    a21 = (dz2 * dv3 - dz3 * dv2) / delta
    a22 = (du2 * dz3 - du3 * dz2) / delta
    b_z = z1 - a21 * u1 - a22 * v1
    return ([[a11, a12], [a21, a22]], [b_x, b_z])


def apply_affine_2d(
    a_mat: list[list[float]],
    b_vec: list[float],
    u_px: float,
    v_px: float,
) -> tuple[float, float]:
    return (
        a_mat[0][0] * u_px + a_mat[0][1] * v_px + b_vec[0],
        a_mat[1][0] * u_px + a_mat[1][1] * v_px + b_vec[1],
    )


def invert_vertical_affine(
    a_mat: list[list[float]],
    b_vec: list[float],
    height_px: float = 4096.0,
) -> tuple[list[list[float]], list[float]]:
    """Construye T_inv(u, v) = T_ok(u, H - v) segun §4.2(3)."""
    a11, a12 = a_mat[0][0], a_mat[0][1]
    a21, a22 = a_mat[1][0], a_mat[1][1]
    bx, bz = b_vec[0], b_vec[1]
    return (
        [[a11, -a12], [a21, -a22]],
        [bx + a12 * height_px, bz + a22 * height_px],
    )


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def decode_and_validate_png(
    png_path: Path,
    expected_w: int = 4096,
    expected_h: int = 4096,
) -> tuple[list[bytes] | None, str]:
    """Valida todos los chunks PNG, CRC32, IHDR, IDAT e IEND y desfiltra el raster 8-bit gris."""
    try:
        raw = png_path.read_bytes()
    except OSError:
        return (None, "png_unreadable")
    if len(raw) < 33 or raw[:8] != PNG_SIGNATURE:
        return (None, "invalid_png_signature")

    pos = 8
    seen_ihdr = False
    seen_iend = False
    idat_parts: list[bytes] = []
    width = 0
    height = 0

    while pos < len(raw):
        if pos + 8 > len(raw):
            return (None, "truncated_chunk_header")
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        pos += 8
        if pos + length + 4 > len(raw):
            return (None, "truncated_chunk_body")
        cdata = raw[pos : pos + length]
        crc_expected = struct.unpack(">I", raw[pos + length : pos + length + 4])[0]
        crc_actual = binascii.crc32(ctype + cdata) & 0xFFFFFFFF
        if crc_actual != crc_expected:
            return (None, "invalid_chunk_crc")
        pos += length + 4

        if not seen_ihdr:
            if ctype != b"IHDR" or length != 13:
                return (None, "missing_or_invalid_ihdr")
            width, height, bit_depth, color_type, comp_m, filt_m, interlace_m = struct.unpack(
                ">IIBBBBB", cdata
            )
            if (
                width != expected_w
                or height != expected_h
                or bit_depth != 8
                or color_type != 0
                or comp_m != 0
                or filt_m != 0
                or interlace_m != 0
            ):
                return (None, "ihdr_mismatch")
            seen_ihdr = True
        elif ctype == b"IHDR":
            return (None, "duplicate_ihdr")
        elif ctype == b"IDAT":
            if seen_iend:
                return (None, "chunk_after_iend")
            idat_parts.append(cdata)
        elif ctype == b"IEND":
            if length != 0 or pos != len(raw):
                return (None, "invalid_iend")
            seen_iend = True
        else:
            if seen_iend:
                return (None, "chunk_after_iend")

    if not seen_ihdr or not seen_iend or not idat_parts:
        return (None, "incomplete_png_stream")

    try:
        dobj = zlib.decompressobj()
        decompressed = dobj.decompress(b"".join(idat_parts)) + dobj.flush()
        if dobj.unused_data:
            return (None, "idat_trailing_garbage")
    except zlib.error:
        return (None, "idat_decompress_failed")

    stride = width + 1
    if len(decompressed) != height * stride:
        return (None, "idat_size_mismatch")

    rows_out: list[bytes] = []
    prev_row = bytearray(width)
    for r in range(height):
        row_start = r * stride
        ftype = decompressed[row_start]
        scan = decompressed[row_start + 1 : row_start + stride]
        if ftype == 0:
            cur = bytearray(scan)
        elif ftype == 1:
            cur = bytearray(width)
            left = 0
            for c in range(width):
                left = (scan[c] + left) & 0xFF
                cur[c] = left
        elif ftype == 2:
            cur = bytearray((scan[c] + prev_row[c]) & 0xFF for c in range(width))
        elif ftype == 3:
            cur = bytearray(width)
            left = 0
            for c in range(width):
                left = (scan[c] + ((left + prev_row[c]) >> 1)) & 0xFF
                cur[c] = left
        elif ftype == 4:
            cur = bytearray(width)
            left = 0
            up_left = 0
            for c in range(width):
                up = prev_row[c]
                pred = _paeth_predictor(left, up, up_left)
                val = (scan[c] + pred) & 0xFF
                cur[c] = val
                left = val
                up_left = up
        else:
            return (None, f"unsupported_png_filter:{ftype}")
        rows_out.append(bytes(cur))
        prev_row = cur

    return (rows_out, "ok")


def _inconclusive(reason: str, metrics: dict[str, object] | None = None) -> dict:
    checks = [{"id": cid, "status": "missing", "detail": reason} for cid in CHECK_IDS]
    return gate_core.make_verdict(
        SPIKE_ID,
        2,
        checks=checks,
        metrics=metrics or {},
        reasons=[reason],
    )


def _extract_complete_ops(
    bridge_rows: list[dict],
) -> tuple[dict[str, dict], str | None]:
    """Indexa operaciones verificando la presencia de enq, poll y result para cada op_id."""
    enqs: dict[str, dict] = {}
    polls_for_op: set[str] = set()
    results: dict[str, dict] = {}

    for row in bridge_rows:
        ev = row.get("ev")
        if ev == "enq":
            oid = row.get("op_id")
            if isinstance(oid, str) and oid:
                enqs[oid] = row
        elif ev == "poll" and row.get("http") == 200:
            for oid in row.get("op_ids") or []:
                if isinstance(oid, str) and oid:
                    polls_for_op.add(oid)
        elif ev == "result" and row.get("http") == 200:
            oid = row.get("op_id")
            res = row.get("result")
            if isinstance(oid, str) and oid and isinstance(res, dict):
                results[oid] = row

    ops: dict[str, dict] = {}
    for oid, res_row in results.items():
        if oid not in enqs or oid not in polls_for_op:
            continue
        enq_row = enqs[oid]
        res_obj = res_row["result"]
        read_obj = res_obj.get("read")
        if not isinstance(read_obj, dict):
            continue
        status = res_obj.get("status")
        reason = res_obj.get("reason", "")
        has_list = read_obj.get("has")
        if not isinstance(has_list, list):
            continue
        unpacked_args: dict | None = None
        raw_args = enq_row.get("args")
        if isinstance(raw_args, dict):
            try:
                unpacked_args = wire.unpack_payload(raw_args)
            except ValueError:
                unpacked_args = None

        unpacked_read: dict | None = None
        if status == "done":
            if "payload" not in has_list:
                continue
            try:
                unpacked_read = wire.unpack_payload(read_obj)
            except ValueError:
                unpacked_read = None
        else:
            unpacked_read = {"str": {}, "num": {}, "rows": [], "ncol": [], "scol": []}

        if unpacked_args is None or unpacked_read is None:
            continue

        ops[oid] = {
            "op_id": oid,
            "verb": enq_row.get("verb"),
            "peer": enq_row.get("peer"),
            "status": status,
            "reason": reason,
            "args": unpacked_args,
            "read": unpacked_read,
            "enq_row": enq_row,
            "result_row": res_row,
        }
    return (ops, None)


def _verify_certifying_capture(
    fixture: dict,
    cert_cap: dict,
    provenance: dict,
    fixture_path: Path,
    cert_path: Path,
    manifest_build: str,
    repo_root: Path,
) -> tuple[dict[str, dict] | None, str | None]:
    """Verifica hashes, el commit/sello historico (N31), ordenes/resultados y coordenadas certificadas (§4.4(4))."""
    if fixture.get("schema") != "dsbx.map.fixture.v4":
        return (None, "unaccredited_fixture")
    if cert_cap.get("schema") != "dsbx.map.certifying_capture.v4":
        return (None, "unaccredited_fixture")

    fix_sha = f03_common.sha256_file_hex(fixture_path)
    cert_sha = f03_common.sha256_file_hex(cert_path)
    accred = fixture.get("accreditation")
    if not isinstance(accred, dict):
        return (None, "unaccredited_fixture")

    if provenance.get("fixture_sha256") != fix_sha:
        return (None, "unaccredited_fixture")
    if provenance.get("certifying_capture_sha256") != cert_sha:
        return (None, "unaccredited_fixture")
    if accred.get("certifying_capture_sha256") != cert_sha:
        return (None, "unaccredited_fixture")

    # Verificar que s_mapa_certifying_capture.json coincide con la serializacion canonica
    canonical_bytes = json.dumps(cert_cap, indent=2, sort_keys=True).encode("utf-8")
    canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()
    canonical_nl_sha = hashlib.sha256(canonical_bytes + b"\n").hexdigest()
    if cert_sha not in (canonical_sha, canonical_nl_sha):
        return (None, "unaccredited_fixture")

    # N31: Comprobacion historica de fuentes y sello sobre certifying_git_head
    cert_git_head = cert_cap.get("certifying_git_head")
    cert_stamp = cert_cap.get("certifying_probe_stamp")
    if (
        not isinstance(cert_git_head, str)
        or not HEX_COMMIT_RE.match(cert_git_head)
        or not isinstance(cert_stamp, str)
        or not HEX_STAMP_RE.match(cert_stamp)
        or cert_stamp == "unstamped"
    ):
        return (None, "unaccredited_fixture")
    if accred.get("certifying_probe_stamp") != cert_stamp:
        return (None, "unaccredited_fixture")

    try:
        hist_stamp = f03_common.compute_probe_stamp_at_commit(cert_git_head, repo_root=repo_root)
        hist_wire_cap = f03_common.read_wire_cap_at_commit(cert_git_head, repo_root=repo_root)
    except f03_common.StampSourceUnavailableError:
        return (None, "unaccredited_fixture")

    if hist_stamp != cert_stamp:
        return (None, "unaccredited_fixture")
    if "certifying_wire_cap" in cert_cap and cert_cap.get("certifying_wire_cap") != hist_wire_cap:
        return (None, "unaccredited_fixture")

    cert_build = cert_cap.get("certifying_build")
    cert_hello = cert_cap.get("certifying_hello")
    if not isinstance(cert_hello, dict):
        return (None, "unaccredited_fixture")
    if (
        cert_hello.get("ev") != "hello"
        or cert_hello.get("peer") != "server"
        or cert_hello.get("proto") != "qa0"
        or cert_hello.get("build") != cert_build
        or cert_hello.get("probe_ver") != f"dsbx-qa1+{cert_stamp}"
    ):
        return (None, "unaccredited_fixture")

    if manifest_build in ("retail", "diag"):
        if accred.get("accredited_ingame") is not True or cert_build not in ("diag", "retail"):
            return (None, "unaccredited_fixture")
    else:
        if accred.get("accredited_offline") is not True:
            return (None, "unaccredited_fixture")

    # Vinculacion con el mundo e imagen
    for key, exp_val in (
        ("world_name", "chernarusplus"),
        ("world_size_m", 15360.0),
        ("sea_level_m", 0.0),
        ("width_px", 4096),
        ("height_px", 4096),
        ("step_px_m", 3.75),
    ):
        if (
            fixture.get(key) != exp_val
            or accred.get(key) != exp_val
            or cert_cap.get(key) != exp_val
            or provenance.get(key) != exp_val
        ):
            return (None, "unaccredited_fixture")

    luma_range = cert_cap.get("global_luma_range")
    if not isinstance(luma_range, dict):
        return (None, "unaccredited_fixture")
    cy_min = luma_range.get("y_min_m")
    cy_max = luma_range.get("y_max_m")
    if not (_is_finite_num(cy_min) and _is_finite_num(cy_max)) or float(cy_max) - float(cy_min) < 1.0:
        return (None, "unaccredited_fixture")
    cy_min_f = float(cy_min)
    cy_max_f = float(cy_max)

    cal_pts = {p["point_id"]: p for p in (fixture.get("calibration_points") or []) if isinstance(p, dict) and "point_id" in p}
    ver_pts = {p["point_id"]: p for p in (fixture.get("verification_points") or []) if isinstance(p, dict) and "point_id" in p}
    place_pts = {p["point_id"]: p for p in (fixture.get("placement_points") or []) if isinstance(p, dict) and "point_id" in p}
    if set(cal_pts.keys()) != set(CAL_IDS) or set(ver_pts.keys()) != set(VER_IDS) or set(place_pts.keys()) != set(SURFACE_IDS):
        return (None, "unaccredited_fixture")

    all_feature_pts = {**cal_pts, **ver_pts}
    patches = cert_cap.get("patches")
    if not isinstance(patches, dict) or set(patches.keys()) != set(PATCH_IDS):
        return (None, "unaccredited_fixture")

    # N31: Verificar ordenes y resultados conservados en certifying_capture
    top_ops = cert_cap.get("certifying_ops")
    top_ops_by_id: dict[str, dict] = {}
    if isinstance(top_ops, list):
        for item in top_ops:
            if isinstance(item, dict) and isinstance(item.get("op_id"), str):
                top_ops_by_id[item["op_id"]] = item

    reconstructed_certified: dict[str, dict] = {}
    for pid in PATCH_IDS:
        fpt = all_feature_pts[pid]
        p_cap = patches.get(pid)
        if not isinstance(p_cap, dict):
            return (None, "unaccredited_fixture")
        roi_px = fpt.get("roi_px")
        world_roi_m = fpt.get("world_roi_m")
        fkind = fpt.get("feature_kind")
        if p_cap.get("roi_px") != roi_px or p_cap.get("world_roi_m") != world_roi_m or p_cap.get("feature_kind") != fkind:
            return (None, "unaccredited_fixture")

        samples_256 = p_cap.get("samples_256")
        patch_luma_256 = p_cap.get("patch_luma_256")
        patch_luma_sha = p_cap.get("patch_luma_sha256")
        if (
            not isinstance(samples_256, list)
            or len(samples_256) != 256
            or not isinstance(patch_luma_256, list)
            or len(patch_luma_256) != 256
            or not isinstance(patch_luma_sha, str)
            or not HEX_SHA256_RE.match(patch_luma_sha)
        ):
            return (None, "unaccredited_fixture")

        # N31: exigir ordenes/resultados conservados que respalden samples_256 y la localizacion
        patch_row_ops = p_cap.get("patch_row_ops")
        if not isinstance(patch_row_ops, list):
            patch_row_ops = p_cap.get("world_read_ops")
        if not isinstance(patch_row_ops, list) and isinstance(p_cap.get("patch_op_ids"), list):
            patch_row_ops = [top_ops_by_id.get(oid) for oid in p_cap["patch_op_ids"]]
        locate_op = p_cap.get("feature_locate_op")
        if not isinstance(locate_op, dict) and isinstance(p_cap.get("locate_op_id"), str):
            locate_op = top_ops_by_id.get(p_cap["locate_op_id"])

        if (
            not isinstance(patch_row_ops, list)
            or len(patch_row_ops) not in (2, 32)
            or not isinstance(locate_op, dict)
        ):
            return (None, "unaccredited_fixture")

        p_idx_num = PATCH_IDS.index(pid)
        for idx_chunk, op_entry in enumerate(patch_row_ops):
            if not isinstance(op_entry, dict):
                return (None, "unaccredited_fixture")
            ord_obj = op_entry.get("order")
            res_obj = op_entry.get("result")
            if not isinstance(ord_obj, dict) or not isinstance(res_obj, dict):
                return (None, "unaccredited_fixture")
            if ord_obj.get("verb") != "map_world_read" or res_obj.get("status") != "done":
                return (None, "unaccredited_fixture")
            if ord_obj.get("op_id") != res_obj.get("op_id") or not isinstance(ord_obj.get("op_id"), str):
                return (None, "unaccredited_fixture")
            try:
                u_args = wire.unpack_payload(ord_obj.get("args", {}))
                u_read = wire.unpack_payload(res_obj.get("read", {}))
            except ValueError:
                return (None, "unaccredited_fixture")
            if u_args["str"].get("mode_id") != "patch_row" or u_read["str"].get("mode_id") != "patch_row":
                return (None, "unaccredited_fixture")
            if len(u_read["rows"]) != 8:
                return (None, "unaccredited_fixture")
            row_n_val = int(round(float(u_args["num"].get("row_n", -1))))
            r_local = row_n_val - p_idx_num * 16
            if not (0 <= r_local < 16):
                return (None, "unaccredited_fixture")
            x0_val = float(u_args["num"].get("x0_m", -1e9))
            c_base = int(round((x0_val / 3.75) - float(roi_px[0])))
            if c_base not in (0, 8):
                return (None, "unaccredited_fixture")
            exp_x0 = 3.75 * float(roi_px[0] + c_base)
            exp_z0 = 15360.0 - 3.75 * float(roi_px[1] + r_local)
            if (
                abs(x0_val - exp_x0) > 1e-3
                or abs(float(u_args["num"].get("z0_m", -1e9)) - exp_z0) > 1e-3
                or abs(float(u_args["num"].get("step_m", 0.0)) - 3.75) > 1e-6
            ):
                return (None, "unaccredited_fixture")
            for k_col, row_cell in enumerate(u_read["rows"]):
                if "y_m" not in row_cell or "sea_b" not in row_cell:
                    return (None, "unaccredited_fixture")
                s_cap = samples_256[r_local * 16 + c_base + k_col]
                if (
                    not isinstance(s_cap, (list, tuple))
                    or len(s_cap) != 2
                    or abs(float(s_cap[0]) - float(row_cell["y_m"])) > 1e-6
                    or float(s_cap[1]) != float(row_cell["sea_b"])
                ):
                    return (None, "unaccredited_fixture")

        # Verificar orden/resultado de map_feature_locate en certifying_capture
        loc_ord = locate_op.get("order")
        loc_res = locate_op.get("result")
        if not isinstance(loc_ord, dict) or not isinstance(loc_res, dict):
            return (None, "unaccredited_fixture")
        if (
            loc_ord.get("verb") != "map_feature_locate"
            or loc_res.get("status") != "done"
            or loc_ord.get("op_id") != loc_res.get("op_id")
        ):
            return (None, "unaccredited_fixture")
        try:
            loc_args = wire.unpack_payload(loc_ord.get("args", {}))
            loc_read = wire.unpack_payload(loc_res.get("read", {}))
        except ValueError:
            return (None, "unaccredited_fixture")
        if (
            loc_args["str"].get("point_id") != pid
            or loc_args["str"].get("feature_kind") != fkind
            or loc_read["str"].get("point_id") != pid
            or float(loc_read["num"].get("srv_feature_found_b", 0.0)) != 1.0
        ):
            return (None, "unaccredited_fixture")

        recalc_luma: list[int] = []
        for item in samples_256:
            recalc_luma.append(quantize_luma(float(item[0]), float(item[1]), cy_min_f, cy_max_f))
        if recalc_luma != [int(x) for x in patch_luma_256]:
            return (None, "unaccredited_fixture")
        if hashlib.sha256(bytes(recalc_luma)).hexdigest() != patch_luma_sha:
            return (None, "unaccredited_fixture")

        img_det = detect_image_feature(recalc_luma, roi_px, str(fkind))
        if img_det is None:
            return (None, "unaccredited_fixture")
        cert_u = float(fpt.get("certified_u_px", -1e9))
        cert_v = float(fpt.get("certified_v_px", -1e9))
        if abs(img_det[0] - cert_u) > 1e-4 or abs(img_det[1] - cert_v) > 1e-4:
            return (None, "unaccredited_fixture")

        world_det = locate_world_feature_from_patch(samples_256, world_roi_m, str(fkind), 0.0)
        if world_det is None:
            return (None, "unaccredited_fixture")
        cert_x = float(fpt.get("certified_x_m", -1e9))
        cert_y = float(fpt.get("certified_y_m", -1e9))
        cert_z = float(fpt.get("certified_z_m", -1e9))
        if (
            abs(float(world_det["srv_x_m"]) - cert_x) > 0.02
            or abs(float(world_det["srv_y_m"]) - cert_y) > 0.02
            or abs(float(world_det["srv_z_m"]) - cert_z) > 0.02
        ):
            return (None, "unaccredited_fixture")
        if (
            abs(float(loc_read["num"].get("srv_x_m", -1e9)) - float(world_det["srv_x_m"])) > 0.02
            or abs(float(loc_read["num"].get("srv_y_m", -1e9)) - float(world_det["srv_y_m"])) > 0.02
            or abs(float(loc_read["num"].get("srv_z_m", -1e9)) - float(world_det["srv_z_m"])) > 0.02
        ):
            return (None, "unaccredited_fixture")

        reconstructed_certified[pid] = {
            "point_id": pid,
            "feature_kind": str(fkind),
            "roi_px": [int(x) for x in roi_px],
            "world_roi_m": [float(x) for x in world_roi_m],
            "certified_u_px": img_det[0],
            "certified_v_px": img_det[1],
            "certified_x_m": float(world_det["srv_x_m"]),
            "certified_y_m": float(world_det["srv_y_m"]),
            "certified_z_m": float(world_det["srv_z_m"]),
        }

    # Verificar surfaces en certifying_capture
    surfaces = cert_cap.get("surfaces")
    if not isinstance(surfaces, dict) or set(surfaces.keys()) != set(SURFACE_IDS):
        return (None, "unaccredited_fixture")

    for sid in SURFACE_IDS:
        spt = place_pts[sid]
        s_cap = surfaces.get(sid)
        if not isinstance(s_cap, dict):
            return (None, "unaccredited_fixture")
        for req_k in ("req_x_m", "req_z_m", "terrain_y_m", "road_y_m", "ray_hit_b", "hit_y_m"):
            if not _is_finite_num(s_cap.get(req_k)):
                return (None, "unaccredited_fixture")
        if not isinstance(s_cap.get("hit_class_id"), str):
            return (None, "unaccredited_fixture")
        if (
            abs(float(s_cap["req_x_m"]) - float(spt.get("req_x_m", -1e9))) > 1e-3
            or abs(float(s_cap["req_z_m"]) - float(spt.get("req_z_m", -1e9))) > 1e-3
        ):
            return (None, "unaccredited_fixture")

        # N31: verificar orden y resultado conservados para cada superficie
        surf_op = s_cap.get("place_ground_op")
        if not isinstance(surf_op, dict) and isinstance(s_cap.get("place_op_id"), str):
            surf_op = top_ops_by_id.get(s_cap["place_op_id"])
        if not isinstance(surf_op, dict):
            return (None, "unaccredited_fixture")
        s_ord = surf_op.get("order")
        s_res = surf_op.get("result")
        if not isinstance(s_ord, dict) or not isinstance(s_res, dict):
            return (None, "unaccredited_fixture")
        if (
            s_ord.get("verb") != "map_place_ground"
            or s_res.get("status") != "done"
            or s_ord.get("op_id") != s_res.get("op_id")
        ):
            return (None, "unaccredited_fixture")
        try:
            s_args = wire.unpack_payload(s_ord.get("args", {}))
            s_read = wire.unpack_payload(s_res.get("read", {}))
        except ValueError:
            return (None, "unaccredited_fixture")
        if s_args["str"].get("point_id") != sid or s_read["str"].get("point_id") != sid:
            return (None, "unaccredited_fixture")
        for num_k in ("req_x_m", "req_z_m", "terrain_y_m", "road_y_m", "ray_hit_b", "hit_y_m"):
            if abs(float(s_read["num"].get(num_k, -1e9)) - float(s_cap[num_k])) > 1e-5:
                return (None, "unaccredited_fixture")
        if s_read["str"].get("hit_class_id", "") != s_cap["hit_class_id"]:
            return (None, "unaccredited_fixture")

        if sid in ("P_BRIDGE", "P_ROOF"):
            t_y = float(s_cap["terrain_y_m"])
            r_y = float(s_cap["road_y_m"])
            ray_b = float(s_cap["ray_hit_b"])
            h_y = float(s_cap["hit_y_m"])
            h_cls = s_cap["hit_class_id"]
            exp_prefix = str(spt.get("expected_hit_class_prefix", ""))
            elevated_ok = (r_y - t_y > 0.25) or (ray_b == 1.0 and h_y - t_y > 0.25)
            if not elevated_ok or not exp_prefix or not h_cls.startswith(exp_prefix):
                return (None, "unaccredited_fixture")

    return (reconstructed_certified, None)


def evaluate(part_dir: Path | str, *, repo_root: Path | None = None) -> dict:
    """Evalua una sola carpeta de parte de S-mapa y devuelve su verdict.json."""
    pdir = Path(part_dir)
    root = repo_root if repo_root is not None else f03_common.REPO_ROOT

    manifest_path = pdir / "manifest.json"
    samples_dir = pdir / "samples"
    bridge_path = samples_dir / "bridge.jsonl"
    scenario_path = samples_dir / "scenario.jsonl"
    png_path = samples_dir / "chernarus_local.png"
    prov_path = samples_dir / "map_provenance.json"
    fixture_path = samples_dir / "s_mapa_puntos.json"
    cert_path = samples_dir / "s_mapa_certifying_capture.json"

    for req_file in (manifest_path, bridge_path, scenario_path, png_path, prov_path, fixture_path, cert_path):
        if not req_file.is_file():
            return _inconclusive("missing_evidence_file")

    try:
        manifest = gate_core.read_json(manifest_path)
        provenance = gate_core.read_json(prov_path)
        fixture = gate_core.read_json(fixture_path)
        cert_cap = gate_core.read_json(cert_path)
        bridge_rows = f03_common.read_jsonl(bridge_path)
        scenario_rows = f03_common.read_jsonl(scenario_path)
    except Exception:
        return _inconclusive("corrupt_evidence_json")

    if not isinstance(manifest, dict) or not isinstance(provenance, dict) or not isinstance(fixture, dict) or not isinstance(cert_cap, dict):
        return _inconclusive("corrupt_evidence_json")

    build = manifest.get("build")
    identity = manifest.get("identity")
    if not isinstance(build, str) or not isinstance(identity, dict):
        return _inconclusive("invalid_manifest")

    if build in ("retail", "diag") and identity.get("git_dirty") is not False:
        return _inconclusive("git_dirty")

    git_head = identity.get("git_head")
    if not isinstance(git_head, str) or not git_head.strip():
        return _inconclusive("stamp_source_unavailable")

    try:
        expected_stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=root)
    except f03_common.StampSourceUnavailableError:
        return _inconclusive("stamp_source_unavailable")

    # Verificar hello 200 del servidor en bridge.jsonl
    server_hellos = [
        r
        for r in bridge_rows
        if r.get("ev") == "hello"
        and r.get("peer") == "server"
        and r.get("http") == 200
        and r.get("ok") is True
        and isinstance(r.get("args"), dict)
    ]
    if not server_hellos:
        return _inconclusive("missing_server_hello")

    for h_ev in server_hellos:
        h_args = h_ev["args"]
        if h_args.get("proto") != "qa0" or h_args.get("build") != build:
            return _inconclusive("build_mismatch")
        p_ver = h_args.get("probe_ver")
        if p_ver == "dsbx-qa1+unstamped" or p_ver != f"dsbx-qa1+{expected_stamp}":
            return _inconclusive("artifact_unverified")

    if identity.get("probe_stamp") == "unstamped" or identity.get("probe_stamp") != expected_stamp:
        return _inconclusive("artifact_unverified")

    # N27 + F0.3-0 §13 A3: Verificar wire_cap historico en identity.params contra git_head
    verified_params, params_err = f03_common.verify_eval_params_at_commit(manifest, repo_root=root)
    if params_err is not None or verified_params is None:
        return _inconclusive(params_err or "params_unverified")
    historical_wire_cap = int(verified_params["wire_cap"])

    # Verificar excesos de cable y errores tecnicos de transporte en bridge.jsonl
    for row in bridge_rows:
        ev = row.get("ev")
        if ev == "wire_cap_exceeded":
            return _inconclusive("wire_cap_exceeded")
        if ev in ("poll", "result") and row.get("http") == 200:
            blen = row.get("body_len")
            if not isinstance(blen, int) or blen <= 0 or blen > historical_wire_cap:
                return _inconclusive("wire_cap_exceeded")
        if ev == "lost":
            return _inconclusive("result_lost")
        if ev == "expire":
            return _inconclusive("result_timeout")
        if ev == "result" and isinstance(row.get("result"), dict):
            res_obj = row["result"]
            st = res_obj.get("status")
            rsn = res_obj.get("reason", "")
            if st in ("error", "timeout", "lost"):
                return _inconclusive(f"transport_error:{rsn or st}")
            if st == "rejected" and rsn == "bad_args":
                return _inconclusive("bad_args")

    source_kind = provenance.get("source_kind")
    if source_kind == "dayz_tools_sat":
        accred = fixture.get("accreditation") if isinstance(fixture.get("accreditation"), dict) else {}
        sat_ok = accred.get("sat_accredited") is True and isinstance(accred.get("sat_reference_image_sha256"), str)
        for req_h in ("pbo_source_sha256", "paa_tiles_sha256", "pal2pace_exe_sha256", "stitch_recipe_sha256"):
            val = provenance.get(req_h)
            if not isinstance(val, str) or not HEX_SHA256_RE.match(val):
                sat_ok = False
        if not sat_ok:
            return _inconclusive("unaccredited_sat_source")

    # N25 + N31: Verificar fixture y captura certificadora
    reconstructed_certified, cert_err = _verify_certifying_capture(
        fixture, cert_cap, provenance, fixture_path, cert_path, build, root
    )
    if cert_err is not None or reconstructed_certified is None:
        return _inconclusive(cert_err or "unaccredited_fixture")

    ops, ops_err = _extract_complete_ops(bridge_rows)
    if ops_err is not None:
        return _inconclusive(ops_err)

    # Indexar pasos de scenario.jsonl
    steps_by_name: dict[str, dict] = {}
    for srow in scenario_rows:
        sname = srow.get("step")
        if isinstance(sname, str) and sname:
            if (
                not _is_finite_num(srow.get("t_start_h_ms"))
                or not _is_finite_num(srow.get("t_end_h_ms"))
                or not _is_finite_num(srow.get("elapsed_h_ms"))
                or not isinstance(srow.get("op_ids"), list)
            ):
                return _inconclusive("invalid_scenario_step")
            steps_by_name[sname] = srow

    required_steps = (
        "world_and_relief_read",
        "calibrate_C1_C3",
        "verify_and_place_V1_V3",
        "place_ground_P_GROUND",
        "neg_inverted_axis",
        "neg_out_of_map",
        "neg_bridge",
        "neg_roof",
    )
    for req_s in required_steps:
        if req_s not in steps_by_name:
            return _inconclusive(f"missing_step:{req_s}")
        for oid in steps_by_name[req_s]["op_ids"]:
            if not isinstance(oid, str) or oid not in ops:
                return _inconclusive(f"missing_op_in_bridge:{req_s}")

    # Reconstruir las 128 ordenes grid_row y 192 ordenes patch_row del Paso 1
    step1_op_ids = steps_by_name["world_and_relief_read"]["op_ids"]
    grid_op_ids = provenance.get("grid_op_ids")
    patch_op_ids = provenance.get("patch_op_ids")
    if (
        not isinstance(grid_op_ids, list)
        or len(grid_op_ids) != 128
        or not isinstance(patch_op_ids, list)
        or len(patch_op_ids) != 192
    ):
        return _inconclusive("invalid_world_read_op_lists")
    if set(grid_op_ids + patch_op_ids) != set(step1_op_ids) or len(step1_op_ids) != 320:
        return _inconclusive("step1_op_ids_mismatch")

    grid_samples: dict[tuple[int, int], tuple[float, float]] = {}
    patch_samples: dict[tuple[int, int, int], tuple[float, float]] = {}
    land_heights: list[float] = []

    for idx_g, oid in enumerate(grid_op_ids):
        op = ops.get(oid)
        if op is None or op["verb"] != "map_world_read" or op["status"] != "done":
            return _inconclusive("missing_grid_read_op")
        u_args = op["args"]
        u_read = op["read"]
        if u_args["str"].get("mode_id") != "grid_row" or u_read["str"].get("mode_id") != "grid_row":
            return _inconclusive("invalid_grid_read_mode")
        if u_read["str"].get("world_name") != "chernarusplus":
            return _inconclusive("world_name_mismatch")
        for req_nk in ("world_size_m", "sea_level_m", "x0_m", "z0_m", "step_m", "row_n", "tick_ms", "frame"):
            if not _is_finite_num(u_read["num"].get(req_nk)):
                return _inconclusive("missing_world_read_scalars")
        if abs(float(u_read["num"]["world_size_m"]) - 15360.0) > 1e-3 or abs(float(u_read["num"]["sea_level_m"]) - 0.0) > 1e-3:
            return _inconclusive("world_geometry_mismatch")

        r_glob = idx_g // 4
        c_chunk = (idx_g % 4) * 8
        exp_x0 = 480.0 * float(c_chunk)
        exp_z0 = 15360.0 - 480.0 * float(r_glob)
        if (
            int(round(float(u_args["num"].get("row_n", -1)))) != r_glob
            or int(round(float(u_args["num"].get("chunk_n", -1)))) != 8
            or abs(float(u_args["num"].get("x0_m", -1e9)) - exp_x0) > 1e-3
            or abs(float(u_args["num"].get("z0_m", -1e9)) - exp_z0) > 1e-3
            or abs(float(u_args["num"].get("step_m", 0.0)) - 480.0) > 1e-3
            or len(u_read["rows"]) != 8
        ):
            return _inconclusive("grid_read_coordinates_mismatch")

        for k_col, rdict in enumerate(u_read["rows"]):
            if not (_is_finite_num(rdict.get("y_m")) and _is_finite_num(rdict.get("sea_b"))):
                return _inconclusive("missing_grid_cell_values")
            yv = float(rdict["y_m"])
            sb = float(rdict["sea_b"])
            if sb not in (0.0, 1.0) or (yv <= 0.0 and sb != 1.0):
                return _inconclusive("invalid_sea_classification")
            grid_samples[(r_glob, c_chunk + k_col)] = (yv, sb)
            if sb == 0.0:
                land_heights.append(yv)

    for idx_p, oid in enumerate(patch_op_ids):
        op = ops.get(oid)
        if op is None or op["verb"] != "map_world_read" or op["status"] != "done":
            return _inconclusive("missing_patch_read_op")
        u_args = op["args"]
        u_read = op["read"]
        if u_args["str"].get("mode_id") != "patch_row" or u_read["str"].get("mode_id") != "patch_row":
            return _inconclusive("invalid_patch_read_mode")
        if u_read["str"].get("world_name") != "chernarusplus":
            return _inconclusive("world_name_mismatch")
        for req_nk in ("world_size_m", "sea_level_m", "x0_m", "z0_m", "step_m", "row_n", "tick_ms", "frame"):
            if not _is_finite_num(u_read["num"].get(req_nk)):
                return _inconclusive("missing_world_read_scalars")

        p_idx = idx_p // 32
        rem = idx_p % 32
        r_loc = rem // 2
        c_chunk = (rem % 2) * 8
        pid = PATCH_IDS[p_idx]
        roi_px = reconstructed_certified[pid]["roi_px"]
        exp_row_n = p_idx * 16 + r_loc
        exp_x0 = 3.75 * float(roi_px[0] + c_chunk)
        exp_z0 = 15360.0 - 3.75 * float(roi_px[1] + r_loc)
        if (
            int(round(float(u_args["num"].get("row_n", -1)))) != exp_row_n
            or int(round(float(u_args["num"].get("chunk_n", -1)))) != 8
            or abs(float(u_args["num"].get("x0_m", -1e9)) - exp_x0) > 1e-3
            or abs(float(u_args["num"].get("z0_m", -1e9)) - exp_z0) > 1e-3
            or abs(float(u_args["num"].get("step_m", 0.0)) - 3.75) > 1e-6
            or len(u_read["rows"]) != 8
        ):
            return _inconclusive("patch_read_coordinates_mismatch")

        for k_col, rdict in enumerate(u_read["rows"]):
            if not (_is_finite_num(rdict.get("y_m")) and _is_finite_num(rdict.get("sea_b"))):
                return _inconclusive("missing_patch_cell_values")
            yv = float(rdict["y_m"])
            sb = float(rdict["sea_b"])
            if sb not in (0.0, 1.0) or (yv <= 0.0 and sb != 1.0):
                return _inconclusive("invalid_sea_classification")
            patch_samples[(p_idx, r_loc, c_chunk + k_col)] = (yv, sb)
            if sb == 0.0:
                land_heights.append(yv)

    if len(grid_samples) != 1024 or len(patch_samples) != 1536:
        return _inconclusive("incomplete_world_read_samples")

    if not land_heights:
        return _inconclusive("degenerate_relief_range")
    y_min_obs = min(land_heights)
    y_max_obs = max(land_heights)
    if y_max_obs - y_min_obs < 1.0:
        return _inconclusive("degenerate_relief_range")

    # Decodificar y validar PNG
    png_rows, png_err = decode_and_validate_png(png_path, 4096, 4096)
    png_sha_actual = f03_common.sha256_file_hex(png_path)

    # Reconstruir rasgos en imagen y mundo para los 6 puntos desde las 256 muestras de map_world_read
    rebuilt_world_features: dict[str, dict] = {}
    detected_img_features: dict[str, tuple[float, float]] = {}
    for p_idx, pid in enumerate(PATCH_IDS):
        cert_info = reconstructed_certified[pid]
        p_256 = [patch_samples[(p_idx, r, c)] for r in range(16) for c in range(16)]
        w_feat = locate_world_feature_from_patch(
            p_256, cert_info["world_roi_m"], cert_info["feature_kind"], 0.0
        )
        if w_feat is None:
            return _inconclusive("missing_independent_correspondence")
        rebuilt_world_features[pid] = w_feat
        if png_rows is not None:
            i_feat = detect_image_feature(png_rows, cert_info["roi_px"], cert_info["feature_kind"])
            if i_feat is None:
                return _inconclusive("missing_independent_correspondence")
            detected_img_features[pid] = i_feat

    # Extraer y validar existencia de las ordenes de los pasos 2..6
    cal_ops: dict[str, dict] = {}
    for oid in steps_by_name["calibrate_C1_C3"]["op_ids"]:
        op = ops[oid]
        if op["verb"] == "map_feature_locate":
            pid = op["args"]["str"].get("point_id", "")
            cal_ops[pid] = op
    if set(cal_ops.keys()) != set(CAL_IDS):
        return _inconclusive("missing_calibration_ops")

    ver_locate_ops: dict[str, dict] = {}
    ver_place_ops: dict[str, dict] = {}
    for oid in steps_by_name["verify_and_place_V1_V3"]["op_ids"]:
        op = ops[oid]
        pid = op["args"]["str"].get("point_id", "")
        if op["verb"] == "map_feature_locate":
            ver_locate_ops[pid] = op
        elif op["verb"] == "map_place_ground":
            ver_place_ops[pid] = op
    if set(ver_locate_ops.keys()) != set(VER_IDS) or set(ver_place_ops.keys()) != set(VER_IDS):
        return _inconclusive("missing_verification_ops")

    pground_ops = [ops[oid] for oid in steps_by_name["place_ground_P_GROUND"]["op_ids"] if ops[oid]["verb"] == "map_place_ground"]
    if len(pground_ops) != 1 or pground_ops[0]["args"]["str"].get("point_id") != "P_GROUND":
        return _inconclusive("missing_p_ground_op")
    pground_op = pground_ops[0]

    inv_ops: dict[str, dict] = {}
    for oid in steps_by_name["neg_inverted_axis"]["op_ids"]:
        op = ops[oid]
        if op["verb"] == "map_feature_locate":
            pid = op["args"]["str"].get("point_id", "")
            inv_ops[pid] = op
    if set(inv_ops.keys()) != set(VER_IDS):
        return _inconclusive("missing_neg_inverted_axis_ops")

    pout_ops = [ops[oid] for oid in steps_by_name["neg_out_of_map"]["op_ids"] if ops[oid]["verb"] == "map_place_ground"]
    pbridge_ops = [ops[oid] for oid in steps_by_name["neg_bridge"]["op_ids"] if ops[oid]["verb"] == "map_place_ground"]
    proof_ops = [ops[oid] for oid in steps_by_name["neg_roof"]["op_ids"] if ops[oid]["verb"] == "map_place_ground"]
    if (
        len(pout_ops) != 1
        or pout_ops[0]["args"]["str"].get("point_id") != "P_OUT"
        or len(pbridge_ops) != 1
        or pbridge_ops[0]["args"]["str"].get("point_id") != "P_BRIDGE"
        or len(proof_ops) != 1
        or proof_ops[0]["args"]["str"].get("point_id") != "P_ROOF"
    ):
        return _inconclusive("missing_negative_placement_ops")
    pout_op = pout_ops[0]
    pbridge_op = pbridge_ops[0]
    proof_op = proof_ops[0]

    # Verificar que todas las ordenes map_feature_locate y map_place_ground tienen sus escalares crudos completos (E9)
    req_locate_nk = (
        "req_x_m",
        "req_z_m",
        "srv_feature_found_b",
        "srv_x_m",
        "srv_y_m",
        "srv_z_m",
        "prominence_m",
        "err_xz_m",
        "err_reflected_z_m",
        "tick_ms",
        "frame",
    )
    req_locate_sk = ("point_id", "mode_id", "decision_id", "reject_reason_id")
    for loc_op in list(cal_ops.values()) + list(ver_locate_ops.values()) + list(inv_ops.values()):
        if loc_op["status"] != "done":
            return _inconclusive("locate_op_not_done")
        for sk_k in req_locate_sk:
            if not isinstance(loc_op["read"]["str"].get(sk_k), str):
                return _inconclusive(f"missing_locate_str:{sk_k}")
        for nk_k in req_locate_nk:
            if not _is_finite_num(loc_op["read"]["num"].get(nk_k)):
                return _inconclusive(f"missing_locate_num:{nk_k}")
        if float(loc_op["read"]["num"]["srv_feature_found_b"]) != 1.0:
            return _inconclusive("missing_independent_correspondence")
        if len(loc_op["read"]["rows"]) != 2:
            return _inconclusive("missing_locate_audit_rows")
        for rdict in loc_op["read"]["rows"]:
            for col_k in ("sx_m", "sz_m", "y_m", "sea_b"):
                if not _is_finite_num(rdict.get(col_k)):
                    return _inconclusive(f"missing_locate_row_col:{col_k}")

    req_place_nk = (
        "req_x_m",
        "req_z_m",
        "terrain_y_m",
        "road_y_m",
        "ray_hit_b",
        "hit_y_m",
        "seq_pre_n",
        "seq_post_n",
        "ent_id_n",
        "obs_x_m",
        "obs_y_m",
        "obs_z_m",
        "bbox_min_y_m",
        "bbox_max_y_m",
        "obs_surf_y_m",
        "pre_count_n",
        "post_count_n",
        "tick_ms",
        "frame",
    )
    req_place_sk = ("point_id", "decision_id", "reject_reason_id", "hit_class_id", "obs_class_id")
    for pl_op in list(ver_place_ops.values()) + [pground_op, pout_op, pbridge_op, proof_op]:
        if pl_op["status"] != "done":
            return _inconclusive("place_op_not_done")
        for sk_k in req_place_sk:
            if not isinstance(pl_op["read"]["str"].get(sk_k), str):
                return _inconclusive(f"missing_place_str:{sk_k}")
        for nk_k in req_place_nk:
            if not _is_finite_num(pl_op["read"]["num"].get(nk_k)):
                return _inconclusive(f"missing_place_num:{nk_k}")

    # Verificar que en P_BRIDGE y P_ROOF el mundo realmente presenta geometria elevada (> 0.25 m); si no -> 2 INCONCLUSO (fixture_surface_mismatch)
    b_num = pbridge_op["read"]["num"]
    b_elevated = (float(b_num["road_y_m"]) - float(b_num["terrain_y_m"]) > 0.25) or (
        float(b_num["ray_hit_b"]) == 1.0 and float(b_num["hit_y_m"]) - float(b_num["terrain_y_m"]) > 0.25
    )
    r_num = proof_op["read"]["num"]
    r_hit_cls = proof_op["read"]["str"]["hit_class_id"]
    r_elevated = (
        float(r_num["ray_hit_b"]) == 1.0
        and float(r_num["hit_y_m"]) - float(r_num["terrain_y_m"]) > 0.25
        and r_hit_cls != ""
    )
    if not b_elevated or not r_elevated:
        return _inconclusive("fixture_surface_mismatch")

    checks_out: list[dict[str, str]] = []
    metrics_out: dict[str, object] = {
        "y_min_m": y_min_obs,
        "y_max_m": y_max_obs,
        "historical_wire_cap": historical_wire_cap,
    }

    # =========================================================================
    # MAP-01: Imagen local integra, reconstruccion 4096x4096 y sin teselas externas
    # =========================================================================
    map01_ok = True
    map01_detail = "ok"
    if png_rows is None:
        map01_ok = False
        map01_detail = png_err
    elif provenance.get("schema") != "dsbx.map.provenance.v4":
        map01_ok = False
        map01_detail = "invalid_provenance_schema"
    elif provenance.get("image_sha256") != png_sha_actual:
        map01_ok = False
        map01_detail = "image_sha256_mismatch"
    elif provenance.get("crs") != "CRS.Simple":
        map01_ok = False
        map01_detail = "invalid_crs"
    elif provenance.get("tile_urls") != [] or provenance.get("external_domains") != []:
        map01_ok = False
        map01_detail = "external_tiles_or_domains_present"
    elif source_kind not in ("mod_relief_plan_b", "dayz_tools_sat"):
        map01_ok = False
        map01_detail = "invalid_source_kind"
    else:
        # Calcular sigma_luma y reconstruccion completa 4096x4096 en Plan B
        total_px = 4096 * 4096
        sum_luma = 0
        sum_sq_luma = 0
        for row_b in png_rows:
            s_r = sum(row_b)
            sum_luma += s_r
            sum_sq_luma += sum(x * x for x in row_b)
        mean_luma = sum_luma / float(total_px)
        var_luma = max(0.0, (sum_sq_luma / float(total_px)) - mean_luma * mean_luma)
        sigma_luma = math.sqrt(var_luma)
        metrics_out["sigma_luma"] = round(sigma_luma, 4)

        if sigma_luma < 5.0:
            map01_ok = False
            map01_detail = f"low_sigma_luma:{sigma_luma:.3f}"
        elif source_kind == "mod_relief_plan_b":
            # Construir tabla de luminancia de fondo 32x32 y bloques de 16x16
            bg_rows_bytes: list[bytes] = []
            for r_g in range(32):
                line_ba = bytearray(4096)
                for c_g in range(32):
                    yv, sb = grid_samples[(r_g, c_g)]
                    l_val = quantize_luma(yv, sb, y_min_obs, y_max_obs)
                    c_start = c_g * 128
                    line_ba[c_start : c_start + 128] = bytes([l_val]) * 128
                bg_rows_bytes.append(bytes(line_ba))

            rec_rows: list[bytearray] = [bytearray(bg_rows_bytes[v // 128]) for v in range(4096)]
            for p_idx, pid in enumerate(PATCH_IDS):
                u0, v0, _, _ = reconstructed_certified[pid]["roi_px"]
                for r_l in range(16):
                    row_target = rec_rows[v0 + r_l]
                    for c_l in range(16):
                        yv, sb = patch_samples[(p_idx, r_l, c_l)]
                        row_target[u0 + c_l] = quantize_luma(yv, sb, y_min_obs, y_max_obs)

            mismatch_px = 0
            max_abs_err = 0
            for v in range(4096):
                p_row = png_rows[v]
                r_row = rec_rows[v]
                if p_row != r_row:
                    for u in range(4096):
                        diff = abs(p_row[u] - r_row[u])
                        if diff > 0:
                            mismatch_px += 1
                            if diff > max_abs_err:
                                max_abs_err = diff

            diff_flipped_sum = 0
            for v in range(4096):
                p_row = png_rows[v]
                f_row = png_rows[4095 - v]
                if p_row != f_row:
                    diff_flipped_sum += sum(abs(a - b) for a, b in zip(p_row, f_row))
            mean_abs_diff_flipped = diff_flipped_sum / float(total_px)

            metrics_out["full_raster_mismatch_px"] = mismatch_px
            metrics_out["max_raster_abs_err"] = max_abs_err
            metrics_out["mean_abs_diff_flipped"] = round(mean_abs_diff_flipped, 4)

            if mismatch_px != 0 or max_abs_err != 0:
                map01_ok = False
                map01_detail = f"full_raster_mismatch_px:{mismatch_px}"
            elif mean_abs_diff_flipped < 15.0:
                map01_ok = False
                map01_detail = f"low_mean_abs_diff_flipped:{mean_abs_diff_flipped:.3f}"

    checks_out.append({"id": "MAP-01", "status": "pass" if map01_ok else "fail", "detail": map01_detail})

    # =========================================================================
    # MAP-02: Calibracion afin C1..C3, recalculo 256 muestras y verificacion V1..V3 < 10 m
    # =========================================================================
    map02_ok = True
    map02_detail = "ok"
    a_ok: list[list[float]] | None = None
    b_ok: list[float] | None = None

    if set(CAL_IDS) & set(VER_IDS):
        map02_ok = False
        map02_detail = "calibration_verification_overlap"
    elif len(detected_img_features) != 6:
        map02_ok = False
        map02_detail = "image_features_unavailable"
    else:
        # Verificar correspondencia en imagen (<= 1.5 px de certified) y recálculo de 256 muestras en los 6 puntos
        for p_idx, pid in enumerate(PATCH_IDS):
            cert_info = reconstructed_certified[pid]
            u_img, v_img = detected_img_features[pid]
            img_err_px = math.hypot(u_img - cert_info["certified_u_px"], v_img - cert_info["certified_v_px"])
            if img_err_px > 1.5:
                map02_ok = False
                map02_detail = f"img_feature_drift:{pid}:{img_err_px:.3f}"
                break

            loc_op = cal_ops[pid] if pid in CAL_IDS else ver_locate_ops[pid]
            exp_mode = "calibrate" if pid in CAL_IDS else "verify"
            exp_dec = "located" if pid in CAL_IDS else "verified"
            l_str = loc_op["read"]["str"]
            l_num = loc_op["read"]["num"]
            if l_str.get("mode_id") != exp_mode or l_str.get("decision_id") != exp_dec or l_str.get("reject_reason_id") != "":
                map02_ok = False
                map02_detail = f"locate_decision_failed:{pid}:{l_str.get('decision_id')}:{l_str.get('reject_reason_id')}"
                break

            if pid in CAL_IDS:
                if "req_x_m" in loc_op["args"]["num"] or "req_z_m" in loc_op["args"]["num"]:
                    map02_ok = False
                    map02_detail = f"calibrate_had_req_coords:{pid}"
                    break

            w_rec = rebuilt_world_features[pid]
            srv_x = float(l_num["srv_x_m"])
            srv_y = float(l_num["srv_y_m"])
            srv_z = float(l_num["srv_z_m"])
            prom = float(l_num["prominence_m"])
            if (
                abs(srv_x - float(w_rec["srv_x_m"])) > 0.02
                or abs(srv_y - float(w_rec["srv_y_m"])) > 0.02
                or abs(srv_z - float(w_rec["srv_z_m"])) > 0.02
                or abs(prom - float(w_rec["prominence_m"])) > 0.02
            ):
                map02_ok = False
                map02_detail = f"srv_vs_patch256_mismatch:{pid}"
                break

            # Comprobar que las 2 filas de auditoria pertenecen a las 256 muestras del parche
            x_min, z_min, x_max, z_max = cert_info["world_roi_m"]
            patch_cells_set = [
                (
                    x_min + 3.75 * float(c),
                    z_max - 3.75 * float(r),
                    patch_samples[(p_idx, r, c)][0],
                    patch_samples[(p_idx, r, c)][1],
                )
                for r in range(16)
                for c in range(16)
            ]
            rows_in_patch = True
            for a_row in loc_op["read"]["rows"]:
                sx = float(a_row["sx_m"])
                sz = float(a_row["sz_m"])
                sy = float(a_row["y_m"])
                sb = float(a_row["sea_b"])
                if not any(
                    abs(sx - px) <= 0.02 and abs(sz - pz) <= 0.02 and abs(sy - py) <= 1e-4 and sb == psb
                    for px, pz, py, psb in patch_cells_set
                ):
                    rows_in_patch = False
                    break
            if not rows_in_patch:
                map02_ok = False
                map02_detail = f"audit_rows_not_in_patch:{pid}"
                break

            # Verificar especifica correspondencia de las 2 filas de auditoria (borde/interior o k*-1/k*)
            row0, row1 = loc_op["read"]["rows"][0], loc_op["read"]["rows"][1]
            if cert_info["feature_kind"] == "relief_peak":
                if (
                    abs(float(row0["y_m"]) - float(w_rec["y_border_m"])) > 1e-4
                    or abs(float(row1["y_m"]) - float(w_rec["srv_y_m"])) > 1e-4
                ):
                    map02_ok = False
                    map02_detail = f"peak_audit_rows_mismatch:{pid}"
                    break
            else:
                ap0, ap1 = w_rec["audit_pair"]
                if (
                    abs(float(row0["sx_m"]) - ap0[0]) > 0.02
                    or abs(float(row0["sz_m"]) - ap0[1]) > 0.02
                    or float(row0["sea_b"]) != 0.0
                    or abs(float(row1["sx_m"]) - ap1[0]) > 0.02
                    or abs(float(row1["sz_m"]) - ap1[1]) > 0.02
                    or float(row1["sea_b"]) != 1.0
                ):
                    map02_ok = False
                    map02_detail = f"coast_audit_rows_mismatch:{pid}"
                    break

            dist_cert = math.hypot(srv_x - cert_info["certified_x_m"], srv_z - cert_info["certified_z_m"])
            if dist_cert > 3.75:
                map02_ok = False
                map02_detail = f"srv_vs_certified_drift:{pid}:{dist_cert:.3f}"
                break

        if map02_ok:
            c_px = [detected_img_features[cid] for cid in CAL_IDS]
            c_world = [
                (float(cal_ops[cid]["read"]["num"]["srv_x_m"]), float(cal_ops[cid]["read"]["num"]["srv_z_m"]))
                for cid in CAL_IDS
            ]
            delta_px = abs(det_2d(c_px[0], c_px[1], c_px[2]))
            delta_m = abs(det_2d(c_world[0], c_world[1], c_world[2]))
            metrics_out["cal_delta_px2"] = round(delta_px, 4)
            metrics_out["cal_delta_m2"] = round(delta_m, 4)
            if delta_px < 1e-6 or delta_m < 1e-6:
                map02_ok = False
                map02_detail = "collinear_calibration_points"
            else:
                fit = solve_affine_2d(c_px, c_world)
                if fit is None:
                    map02_ok = False
                    map02_detail = "singular_affine_fit"
                else:
                    a_ok, b_ok = fit
                    det_a = a_ok[0][0] * a_ok[1][1] - a_ok[0][1] * a_ok[1][0]
                    if not (a_ok[0][0] > 0.0 and a_ok[1][1] < 0.0 and det_a < 0.0):
                        map02_ok = False
                        map02_detail = "invalid_affine_orientation"
                    else:
                        max_verify_err = 0.0
                        for vid in VER_IDS:
                            u_v, v_v = detected_img_features[vid]
                            x_hat, z_hat = apply_affine_2d(a_ok, b_ok, u_v, v_v)
                            v_op = ver_locate_ops[vid]
                            v_num = v_op["read"]["num"]
                            req_x = float(v_num["req_x_m"])
                            req_z = float(v_num["req_z_m"])
                            srv_x = float(v_num["srv_x_m"])
                            srv_z = float(v_num["srv_z_m"])
                            cert_x = reconstructed_certified[vid]["certified_x_m"]
                            cert_z = reconstructed_certified[vid]["certified_z_m"]

                            # La orden enviada en verify debe corresponder a la proyeccion evaluada y caer a < 10 m
                            err_req_vs_hat = math.hypot(req_x - x_hat, req_z - z_hat)
                            err_hat_srv = math.hypot(x_hat - srv_x, z_hat - srv_z)
                            err_hat_cert = math.hypot(x_hat - cert_x, z_hat - cert_z)
                            err_req_srv = math.hypot(req_x - srv_x, req_z - srv_z)
                            err_req_cert = math.hypot(req_x - cert_x, req_z - cert_z)
                            max_verify_err = max(max_verify_err, err_hat_srv, err_hat_cert, err_req_srv, err_req_cert)
                            if (
                                err_req_vs_hat > 0.05
                                or err_hat_srv >= 10.0
                                or err_hat_cert >= 10.0
                                or err_req_srv >= 10.0
                                or err_req_cert >= 10.0
                            ):
                                map02_ok = False
                                map02_detail = f"verify_error_exceeded:{vid}:{max(err_req_srv, err_hat_srv):.3f}"
                                break
                        metrics_out["max_verify_err_xz_m"] = round(max_verify_err, 4)

    # Incluso si MAP-02 fallo en V1..V3, resolver (A, b) sano sobre C1..C3 si es posible para evaluar MAP-04
    if a_ok is None and len(detected_img_features) == 6:
        c_px_try = [detected_img_features[cid] for cid in CAL_IDS]
        c_world_try = [
            (float(cal_ops[cid]["read"]["num"]["srv_x_m"]), float(cal_ops[cid]["read"]["num"]["srv_z_m"]))
            for cid in CAL_IDS
        ]
        if abs(det_2d(c_px_try[0], c_px_try[1], c_px_try[2])) >= 1e-6 and abs(det_2d(c_world_try[0], c_world_try[1], c_world_try[2])) >= 1e-6:
            fit_try = solve_affine_2d(c_px_try, c_world_try)
            if fit_try is not None:
                a_ok, b_ok = fit_try

    checks_out.append({"id": "MAP-02", "status": "pass" if map02_ok else "fail", "detail": map02_detail})

    # =========================================================================
    # MAP-03: Colocacion de plantilla en suelo en V1..V3 y P_GROUND (< 0.2 m, N29)
    # =========================================================================
    map03_ok = True
    map03_detail = "ok"
    place_positive_ops = [(vid, ver_place_ops[vid]) for vid in VER_IDS] + [("P_GROUND", pground_op)]
    seq_posts: list[int] = []
    max_contact_err = 0.0

    for pid, pop in place_positive_ops:
        p_str = pop["read"]["str"]
        p_num = pop["read"]["num"]
        seq_pre = int(round(float(p_num["seq_pre_n"])))
        seq_post = int(round(float(p_num["seq_post_n"])))
        ent_id = int(round(float(p_num["ent_id_n"])))
        pre_cnt = int(round(float(p_num["pre_count_n"])))
        post_cnt = int(round(float(p_num["post_count_n"])))
        req_x = float(p_num["req_x_m"])
        req_z = float(p_num["req_z_m"])
        obs_x = float(p_num["obs_x_m"])
        obs_y = float(p_num["obs_y_m"])
        obs_z = float(p_num["obs_z_m"])
        bbox_min_y = float(p_num["bbox_min_y_m"])
        bbox_max_y = float(p_num["bbox_max_y_m"])
        obs_surf_y = float(p_num["obs_surf_y_m"])

        if p_str.get("decision_id") != "placed" or p_str.get("reject_reason_id") != "":
            map03_ok = False
            map03_detail = f"not_placed:{pid}"
            break
        if seq_post != seq_pre + 1:
            map03_ok = False
            map03_detail = f"invalid_spawn_seq_delta:{pid}:{seq_pre}->{seq_post}"
            break
        if p_str.get("obs_class_id") != "Barrel_Green":
            map03_ok = False
            map03_detail = f"wrong_obs_class:{pid}:{p_str.get('obs_class_id')}"
            break
        if not (bbox_max_y > bbox_min_y):
            map03_ok = False
            map03_detail = f"invalid_bbox:{pid}"
            break
        if ent_id < 0:
            map03_ok = False
            map03_detail = f"negative_ent_id:{pid}"
            break
        if post_cnt != pre_cnt:
            map03_ok = False
            map03_detail = f"cleanup_count_mismatch:{pid}:{pre_cnt}->{post_cnt}"
            break

        horiz_req_err = math.hypot(obs_x - req_x, obs_z - req_z)
        if horiz_req_err > 0.05:
            map03_ok = False
            map03_detail = f"horizontal_req_drift:{pid}:{horiz_req_err:.4f}"
            break

        if pid in VER_IDS:
            srv_x = float(ver_locate_ops[pid]["read"]["num"]["srv_x_m"])
            srv_z = float(ver_locate_ops[pid]["read"]["num"]["srv_z_m"])
            cert_x = reconstructed_certified[pid]["certified_x_m"]
            cert_z = reconstructed_certified[pid]["certified_z_m"]
            if math.hypot(obs_x - srv_x, obs_z - srv_z) >= 10.0 or math.hypot(obs_x - cert_x, obs_z - cert_z) >= 10.0:
                map03_ok = False
                map03_detail = f"verify_placement_drift:{pid}"
                break
        else:
            pground_fix = next(p for p in fixture["placement_points"] if p["point_id"] == "P_GROUND")
            if a_ok is not None and b_ok is not None:
                gx_hat, gz_hat = apply_affine_2d(a_ok, b_ok, float(pground_fix["u_px"]), float(pground_fix["v_px"]))
                if math.hypot(obs_x - gx_hat, obs_z - gz_hat) >= 10.0:
                    map03_ok = False
                    map03_detail = "pground_projected_drift"
                    break
            if math.hypot(obs_x - float(pground_fix["req_x_m"]), obs_z - float(pground_fix["req_z_m"])) >= 10.0:
                map03_ok = False
                map03_detail = "pground_certified_drift"
                break

        # N29: Contacto vertical sobre floats crudos sin cuantizar (< 0.2 m)
        contact_err = abs(obs_y + bbox_min_y - obs_surf_y)
        max_contact_err = max(max_contact_err, contact_err)
        if not (contact_err < 0.2):
            map03_ok = False
            map03_detail = f"contact_height_error:{pid}:{contact_err:.6f}"
            break

        seq_posts.append(seq_post)

    if map03_ok:
        if len(seq_posts) != 4 or any(seq_posts[i] >= seq_posts[i + 1] for i in range(3)):
            map03_ok = False
            map03_detail = "non_increasing_seq_post_n"

    metrics_out["max_contact_err_y_m"] = round(max_contact_err, 6)
    checks_out.append({"id": "MAP-03", "status": "pass" if map03_ok else "fail", "detail": map03_detail})

    # =========================================================================
    # MAP-04: Rechazo explicito de eje vertical invertido (neg_inverted_axis)
    # =========================================================================
    map04_ok = True
    map04_detail = "ok"
    if a_ok is None or b_ok is None:
        map04_ok = False
        map04_detail = "missing_affine_for_inverted_axis"
    else:
        a_inv, b_inv = invert_vertical_affine(a_ok, b_ok, 4096.0)
        det_inv = a_inv[0][0] * a_inv[1][1] - a_inv[0][1] * a_inv[1][0]
        if not (a_inv[1][1] > 0.0 and det_inv > 0.0):
            map04_ok = False
            map04_detail = "invalid_inverted_matrix_signs"
        else:
            for vid in VER_IDS:
                u_v, v_v = detected_img_features[vid]
                x_inv_hat, z_inv_hat = apply_affine_2d(a_inv, b_inv, u_v, v_v)
                iop = inv_ops[vid]
                i_str = iop["read"]["str"]
                i_num = iop["read"]["num"]
                req_x = float(i_num["req_x_m"])
                req_z = float(i_num["req_z_m"])
                srv_x = float(i_num["srv_x_m"])
                srv_z = float(i_num["srv_z_m"])

                if math.hypot(req_x - x_inv_hat, req_z - z_inv_hat) > 0.05:
                    map04_ok = False
                    map04_detail = f"inv_projection_mismatch:{vid}"
                    break
                err_xz = math.hypot(req_x - srv_x, req_z - srv_z)
                err_refl_z = abs((15360.0 - req_z) - srv_z)
                if not (err_xz >= 10.0 and err_refl_z < 50.0 and abs(req_x - srv_x) < 50.0):
                    map04_ok = False
                    map04_detail = f"inv_geometry_outside_capture:{vid}"
                    break
                if i_str.get("mode_id") != "verify" or i_str.get("decision_id") != "rejected" or i_str.get("reject_reason_id") != "inverted_axis":
                    map04_ok = False
                    map04_detail = f"inv_not_rejected:{vid}:{i_str.get('decision_id')}:{i_str.get('reject_reason_id')}"
                    break

    checks_out.append({"id": "MAP-04", "status": "pass" if map04_ok else "fail", "detail": map04_detail})

    # =========================================================================
    # MAP-05: Rechazo explicito de coordenadas fuera del mapa (P_OUT) sin instanciar
    # =========================================================================
    o_str = pout_op["read"]["str"]
    o_num = pout_op["read"]["num"]
    o_req_x = float(o_num["req_x_m"])
    o_req_z = float(o_num["req_z_m"])
    o_out_bounds = o_req_x < 0.0 or o_req_x > 15360.0 or o_req_z < 0.0 or o_req_z > 15360.0
    o_no_spawn = (
        int(round(float(o_num["seq_post_n"]))) == int(round(float(o_num["seq_pre_n"])))
        and o_str.get("obs_class_id") == ""
        and int(round(float(o_num["ent_id_n"]))) == 0
        and int(round(float(o_num["post_count_n"]))) == int(round(float(o_num["pre_count_n"])))
    )
    map05_ok = (
        o_out_bounds
        and o_no_spawn
        and o_str.get("decision_id") == "rejected"
        and o_str.get("reject_reason_id") == "out_of_map"
    )
    checks_out.append({
        "id": "MAP-05",
        "status": "pass" if map05_ok else "fail",
        "detail": "ok" if map05_ok else f"out_of_map_check_failed:{o_str.get('decision_id')}:{o_str.get('reject_reason_id')}",
    })

    # =========================================================================
    # MAP-06: Rechazo explicito de colocacion sobre puente (P_BRIDGE) sin instanciar
    # =========================================================================
    b_str = pbridge_op["read"]["str"]
    b_no_spawn = (
        int(round(float(b_num["seq_post_n"]))) == int(round(float(b_num["seq_pre_n"])))
        and b_str.get("obs_class_id") == ""
        and int(round(float(b_num["ent_id_n"]))) == 0
        and int(round(float(b_num["post_count_n"]))) == int(round(float(b_num["pre_count_n"])))
    )
    map06_ok = (
        b_elevated
        and b_no_spawn
        and b_str.get("decision_id") == "rejected"
        and b_str.get("reject_reason_id") == "elevated_surface"
    )
    checks_out.append({
        "id": "MAP-06",
        "status": "pass" if map06_ok else "fail",
        "detail": "ok" if map06_ok else f"bridge_check_failed:{b_str.get('decision_id')}:{b_str.get('reject_reason_id')}",
    })

    # =========================================================================
    # MAP-07: Rechazo explicito de colocacion sobre tejado (P_ROOF) sin instanciar
    # =========================================================================
    r_str = proof_op["read"]["str"]
    r_no_spawn = (
        int(round(float(r_num["seq_post_n"]))) == int(round(float(r_num["seq_pre_n"])))
        and r_str.get("obs_class_id") == ""
        and int(round(float(r_num["ent_id_n"]))) == 0
        and int(round(float(r_num["post_count_n"]))) == int(round(float(r_num["pre_count_n"])))
    )
    map07_ok = (
        r_elevated
        and r_no_spawn
        and r_str.get("decision_id") == "rejected"
        and r_str.get("reject_reason_id") == "elevated_surface"
    )
    checks_out.append({
        "id": "MAP-07",
        "status": "pass" if map07_ok else "fail",
        "detail": "ok" if map07_ok else f"roof_check_failed:{r_str.get('decision_id')}:{r_str.get('reject_reason_id')}",
    })

    failed_ids = [c["id"] for c in checks_out if c["status"] != "pass"]
    exit_code = 0 if not failed_ids else 1
    reasons = [f"check_failed:{cid}" for cid in failed_ids]
    return gate_core.make_verdict(
        SPIKE_ID,
        exit_code,
        checks=checks_out,
        metrics=metrics_out,
        reasons=reasons,
    )
