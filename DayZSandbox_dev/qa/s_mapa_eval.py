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
# Clase contractual de la plantilla (§4.3, D5).  No basta con que la respuesta
# repita la clase pedida: el pedido y la observacion tienen que ser esta clase.
CONTRACT_CLASS = "Barrel_Green"
HEX_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")
HEX_STAMP_RE = re.compile(r"^[0-9a-f]{16}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Fixture congelada del propio oraculo (acreditacion contra la fuente, no contra
# el hash que trae el paquete evaluado).  El evaluador la lee de su propio arbol;
# no abre ``qa/fixtures/`` de la parte, que sigue siendo solo ``samples/``.
FROZEN_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "s_mapa_puntos.json"

# Campos que el runner puede re-sellar al materializar la fixture en samples/:
# commit y sello de la captura certificadora, y los hashes derivados de ellos.
_FROZEN_MUTABLE_PATHS = frozenset(
    {
        ("accreditation", "certifying_capture_sha256"),
        ("accreditation", "certifying_probe_stamp"),
        ("certifying_capture", "certifying_git_head"),
        ("certifying_capture", "certifying_hello", "probe_ver"),
        ("certifying_capture", "certifying_probe_stamp"),
        ("certifying_capture", "certifying_wire_cap"),
    }
)

SAT_ARTIFACT_KEYS = (
    "pbo_source_sha256",
    "paa_tiles_sha256",
    "pal2pace_exe_sha256",
    "stitch_recipe_sha256",
)


def _is_finite_num(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def _exact_int(val: object) -> int | None:
    """Devuelve el entero exacto contenido en ``val`` o ``None`` si no lo es.

    N23/N26: los contadores (``_n``), booleanos (``_b``) y ``frame`` viajan como
    enteros exactos; un ``0.49`` no es valido aunque redondee a ``0``.
    """
    if not _is_finite_num(val):
        return None
    f = float(val)
    if f != math.floor(f):
        return None
    return int(f)


def _same_num(val: object, ref: float, tol: float) -> bool:
    return _is_finite_num(val) and abs(float(val) - float(ref)) <= tol


def _load_frozen_fixture() -> dict | None:
    try:
        data = json.loads(FROZEN_FIXTURE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _frozen_mismatches(got: object, exp: object, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Lista de rutas donde ``got`` no coincide con la fixture congelada.

    Se toleran solo los campos de ``_FROZEN_MUTABLE_PATHS`` (commit y sello de la
    captura certificadora, y los hashes que de ellos derivan).  Todo lo demas
    (puntos, ventanas, muestras, luminancias, superficies y banderas de
    acreditacion) queda congelado: el implementador no puede autoacreditar su
    copia en ``samples/``.
    """
    if path in _FROZEN_MUTABLE_PATHS:
        return []
    if isinstance(exp, dict):
        if not isinstance(got, dict):
            return [path]
        bad: list[tuple[str, ...]] = []
        for key in sorted(set(exp.keys()) | set(got.keys())):
            if key not in exp or key not in got:
                bad.append(path + (key,))
            else:
                bad.extend(_frozen_mismatches(got[key], exp[key], path + (key,)))
        return bad
    if isinstance(exp, list):
        if not isinstance(got, list) or len(got) != len(exp):
            return [path]
        bad = []
        for idx, (g_item, e_item) in enumerate(zip(got, exp)):
            bad.extend(_frozen_mismatches(g_item, e_item, path + (str(idx),)))
        return bad
    if isinstance(exp, bool) or isinstance(got, bool):
        return [] if got == exp else [path]
    if isinstance(exp, (int, float)) and isinstance(got, (int, float)):
        return [] if float(got) == float(exp) else [path]
    return [] if got == exp else [path]


def _roi_rect_overlap(a: object, b: object) -> bool:
    if not (isinstance(a, (list, tuple)) and len(a) == 4 and isinstance(b, (list, tuple)) and len(b) == 4):
        return True
    au0, av0, au1, av1 = (float(a[0]), float(a[1]), float(a[2]), float(a[3]))
    bu0, bv0, bu1, bv1 = (float(b[0]), float(b[1]), float(b[2]), float(b[3]))
    return not (au1 < bu0 or bu1 < au0 or av1 < bv0 or bv1 < av0)


def _verify_sat_source(
    provenance: dict,
    accred: dict,
    samples_dir: Path,
) -> str | None:
    """Acredita la Via A por ficheros y referencia, no por etiqueta.

    El manifiesto declara ``source_kind = "dayz_tools_sat"``; para que valga, cada
    hash declarado tiene que corresponder a un fichero realmente presente en
    ``samples/`` (via ``<clave>_relpath``) y la imagen de referencia tiene que ser
    un PNG con el SHA-256 declarado.  Si falta cualquier pieza, el resultado es
    ``unaccredited_sat_source``.
    """
    if accred.get("sat_accredited") is not True:
        return "unaccredited_sat_source"

    ref_sha = accred.get("sat_reference_image_sha256")
    ref_rel = accred.get("sat_reference_image_relpath")
    if not isinstance(ref_sha, str) or not HEX_SHA256_RE.match(ref_sha):
        return "unaccredited_sat_source"
    if not isinstance(ref_rel, str) or not ref_rel:
        return "unaccredited_sat_source"

    root = samples_dir.resolve()
    ref_path = (samples_dir / ref_rel).resolve()
    if not ref_path.is_file() or root not in ref_path.parents:
        return "unaccredited_sat_source"
    try:
        raw = ref_path.read_bytes()
    except OSError:
        return "unaccredited_sat_source"
    if raw[:8] != PNG_SIGNATURE:
        return "unaccredited_sat_source"
    if hashlib.sha256(raw).hexdigest() != ref_sha:
        return "unaccredited_sat_source"

    for key in SAT_ARTIFACT_KEYS:
        decl_sha = accred.get(key)
        decl_rel = accred.get(key.replace("_sha256", "_relpath"))
        if not isinstance(decl_sha, str) or not HEX_SHA256_RE.match(decl_sha):
            return "unaccredited_sat_source"
        if not isinstance(decl_rel, str) or not decl_rel:
            return "unaccredited_sat_source"
        art_path = (samples_dir / decl_rel).resolve()
        if not art_path.is_file() or root not in art_path.parents:
            return "unaccredited_sat_source"
        try:
            art = art_path.read_bytes()
        except OSError:
            return "unaccredited_sat_source"
        if hashlib.sha256(art).hexdigest() != decl_sha:
            return "unaccredited_sat_source"

    # La imagen declarada por procedencia tiene que ser la misma referencia.
    if provenance.get("sat_reference_image_sha256") not in (None, ref_sha):
        return "unaccredited_sat_source"
    return None


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
        if not dobj.eof:
            # MEN 10: un flujo zlib truncado puede dar la longitud esperada; se
            # exige que el flujo comprimido haya terminado de verdad.
            return (None, "idat_stream_not_terminated")
        if dobj.unused_data:
            return (None, "idat_trailing_garbage")
        if dobj.unconsumed_tail:
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


# BLOQ 4: una atribucion incompatible o un duplicado ambiguo es FALLA; solo una
# operacion que falta de verdad (sin enq/poll/result) queda como missing.
_ATTRIBUTION_ERROR_PREFIXES = (
    "op_not_from_server_instance:",
    "ambiguous_operation:",
    "poll_not_from_server_instance:",
    "result_not_from_server_instance:",
    "result_op_id_mismatch:",
    "missing_op_clock:",
    "missing_poll_clock:",
    "poll_before_enq:",
    "poll_after_result:",
    "result_before_enq:",
)


def _attribution_failure(reason: str, metrics: dict[str, object] | None = None) -> dict:
    checks = [{"id": cid, "status": "fail", "detail": reason} for cid in CHECK_IDS]
    return gate_core.make_verdict(
        SPIKE_ID,
        1,
        checks=checks,
        metrics=metrics or {},
        reasons=[reason],
    )


def _extract_complete_ops(
    bridge_rows: list[dict],
    expected_build: str,
    expected_stamp: str,
) -> tuple[dict[str, dict], str | None]:
    """Indexa operaciones ligadas a la instancia del servidor observada en el hello.

    Cada orden debe aparecer con su ``enq``, un ``poll`` que la incluya y un
    ``result``, los tres atribuidos al peer ``server`` y a una instancia que haya
    saludado como servidor.  Se exige orden temporal ``enq <= poll <= result``, que
    el ``result.op_id`` interior coincida con el exterior y que no haya duplicados
    ambiguos (mismo ``op_id`` con contenido distinto).

    BLOQ 4: las instancias admitidas salen solo de saludos aceptados y sellados
    (``ok == true``, ``proto == qa0``, build del manifiesto y sello historico), no
    de cualquier fila ``hello`` con HTTP 200.

    El nucleo emite ``poll`` de los dos peers.  El cliente tambien hace polls
    vacios legitimos: se admiten y solo se exige la atribucion al servidor en las
    operaciones y polls que transportan ordenes ``map_*``.
    """
    hello_stamp = f"dsbx-qa1+{expected_stamp}"
    server_insts = {
        r.get("inst")
        for r in bridge_rows
        if r.get("ev") == "hello"
        and r.get("peer") == "server"
        and r.get("http") == 200
        and r.get("ok") is True
        and isinstance(r.get("inst"), str)
        and r["inst"]
        and isinstance(r.get("args"), dict)
        and r["args"].get("proto") == "qa0"
        and r["args"].get("build") == expected_build
        and r["args"].get("probe_ver") == hello_stamp
    }
    if not server_insts:
        return ({}, "missing_server_hello")

    enqs: dict[str, dict] = {}
    polls_for_op: dict[str, list[dict]] = {}
    results: dict[str, dict] = {}

    def _attr_ok(row: dict, require_inst: bool) -> bool:
        if row.get("peer") != "server":
            return False
        inst = row.get("inst")
        if require_inst or inst is not None:
            return isinstance(inst, str) and inst in server_insts
        return True

    for row in bridge_rows:
        ev = row.get("ev")
        if ev == "enq":
            oid = row.get("op_id")
            if not isinstance(oid, str) or not oid:
                continue
            if not _attr_ok(row, require_inst=True):
                return ({}, f"op_not_from_server_instance:{oid}")
            prev = enqs.get(oid)
            if prev is not None and (
                prev.get("inst") != row.get("inst")
                or prev.get("peer") != row.get("peer")
                or prev.get("verb") != row.get("verb")
                or prev.get("args") != row.get("args")
            ):
                return ({}, f"ambiguous_operation:{oid}")
            enqs[oid] = row
        elif ev == "poll" and row.get("http") == 200:
            # Trafico legitimo del cliente (polls vacios): no transporta ordenes
            # map_* ni se le exige instancia de servidor.
            if row.get("peer") == "client":
                continue
            if not _attr_ok(row, require_inst=True):
                return ({}, f"poll_not_from_server_instance:{row.get('inst')}")
            for oid in row.get("op_ids") or []:
                if isinstance(oid, str) and oid:
                    polls_for_op.setdefault(oid, []).append(row)
        elif ev == "result" and row.get("http") == 200:
            oid = row.get("op_id")
            res = row.get("result")
            if not isinstance(oid, str) or not oid or not isinstance(res, dict):
                continue
            if not _attr_ok(row, require_inst=False):
                return ({}, f"result_not_from_server_instance:{oid}")
            if res.get("op_id") != oid:
                return ({}, f"result_op_id_mismatch:{oid}")
            prev = results.get(oid)
            if prev is not None and prev.get("result") != res:
                return ({}, f"ambiguous_operation:{oid}")
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

        # Orden temporal estricta en el reloj del puente.
        t_enq = enq_row.get("t_ms")
        t_res = res_row.get("t_ms")
        if not (_is_finite_num(t_enq) and _is_finite_num(t_res)):
            return ({}, f"missing_op_clock:{oid}")
        t_poll = None
        for poll_row in polls_for_op[oid]:
            t_p = poll_row.get("t_ms")
            if not _is_finite_num(t_p):
                return ({}, f"missing_poll_clock:{oid}")
            if t_p < float(t_enq):
                return ({}, f"poll_before_enq:{oid}")
            if t_p > float(t_res):
                return ({}, f"poll_after_result:{oid}")
            t_poll = t_p if t_poll is None else min(t_poll, t_p)
        if t_poll is None or float(t_res) < float(t_enq):
            return ({}, f"result_before_enq:{oid}")

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

    # La copia en ``samples/`` se acredita contra la fixture congelada del oraculo,
    # no contra el hash que el propio paquete aporta.  Solo pueden diferir los
    # campos que el runner re-sella al materializar la captura.
    frozen = _load_frozen_fixture()
    if frozen is None:
        return (None, "unaccredited_fixture")
    if _frozen_mismatches(fixture, frozen):
        return (None, "unaccredited_fixture")

    # BLOQ 7: el archivo certificador separado no es una isla.  Tiene que ser el
    # mismo bloque que la fixture congelada declara (con los sellos re-materializados
    # por el runner); si difiere en ordenes, ventanas o geometria, la captura no
    # acredita nada aunque sus propios hashes cuadren.
    fx_cert = fixture.get("certifying_capture")
    if not isinstance(fx_cert, dict):
        return (None, "unaccredited_fixture")
    if _frozen_mismatches({"certifying_capture": cert_cap}, {"certifying_capture": fx_cert}):
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

    # Una captura offline no puede pasar a diag/retail solo cambiando etiquetas: la
    # bandera de acreditacion en juego y el build certificador tienen que ser
    # coherentes entre si (y quedan congelados contra la fixture del oraculo).
    if cert_build == "offline":
        if accred.get("accredited_ingame") is not False:
            return (None, "unaccredited_fixture")
    elif cert_build in ("diag", "retail"):
        if accred.get("accredited_ingame") is not True:
            return (None, "unaccredited_fixture")
    else:
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

    # Separacion fisica real entre calibracion y verificacion: puntos certificados
    # distintos y ventanas disjuntas.  No basta con que los nombres C/V difieran:
    # V1..V3 no puede ser una copia fisica de C1..C3 con los nombres cambiados.
    for cid in CAL_IDS:
        for vid in VER_IDS:
            cpt = cal_pts[cid]
            vpt = ver_pts[vid]
            cx = cpt.get("certified_x_m")
            cz = cpt.get("certified_z_m")
            vx = vpt.get("certified_x_m")
            vz = vpt.get("certified_z_m")
            if not all(_is_finite_num(v) for v in (cx, cz, vx, vz)):
                return (None, "unaccredited_fixture")
            if math.hypot(float(cx) - float(vx), float(cz) - float(vz)) < 500.0:
                return (None, "unaccredited_fixture")
            if _roi_rect_overlap(cpt.get("roi_px"), vpt.get("roi_px")):
                return (None, "unaccredited_fixture")
            if _roi_rect_overlap(cpt.get("world_roi_m"), vpt.get("world_roi_m")):
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
    seen_cert_op_ids: set[str] = set()
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

        # N31: la captura certificadora debe conservar las 32 ordenes distintas
        # (16 filas x 2 mitades de 8 muestras) que cubren las 256 muestras.
        # Dos ordenes sueltas, o un mismo bloque repetido, no acreditan el parche.
        if (
            not isinstance(patch_row_ops, list)
            or len(patch_row_ops) != 32
            or not isinstance(locate_op, dict)
        ):
            return (None, "unaccredited_fixture")

        p_idx_num = PATCH_IDS.index(pid)
        covered_cells: set[tuple[int, int]] = set()
        for op_entry in patch_row_ops:
            if not isinstance(op_entry, dict):
                return (None, "unaccredited_fixture")
            ord_obj = op_entry.get("order")
            res_obj = op_entry.get("result")
            if not isinstance(ord_obj, dict) or not isinstance(res_obj, dict):
                return (None, "unaccredited_fixture")
            if ord_obj.get("verb") != "map_world_read" or res_obj.get("status") != "done":
                return (None, "unaccredited_fixture")
            op_id_val = ord_obj.get("op_id")
            if op_id_val != res_obj.get("op_id") or not isinstance(op_id_val, str) or not op_id_val:
                return (None, "unaccredited_fixture")
            if op_id_val in seen_cert_op_ids:
                return (None, "unaccredited_fixture")
            seen_cert_op_ids.add(op_id_val)
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
            if (r_local, c_base) in covered_cells:
                return (None, "unaccredited_fixture")
            covered_cells.add((r_local, c_base))
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

        if len(covered_cells) != 32:
            return (None, "unaccredited_fixture")

        # Verificar orden/resultado de map_feature_locate en certifying_capture
        loc_ord = locate_op.get("order")
        loc_res = locate_op.get("result")
        if not isinstance(loc_ord, dict) or not isinstance(loc_res, dict):
            return (None, "unaccredited_fixture")
        loc_op_id = loc_ord.get("op_id")
        if (
            loc_ord.get("verb") != "map_feature_locate"
            or loc_res.get("status") != "done"
            or loc_op_id != loc_res.get("op_id")
            or not isinstance(loc_op_id, str)
            or not loc_op_id
            or loc_op_id in seen_cert_op_ids
        ):
            return (None, "unaccredited_fixture")
        seen_cert_op_ids.add(loc_op_id)
        try:
            loc_args = wire.unpack_payload(loc_ord.get("args", {}))
            loc_read = wire.unpack_payload(loc_res.get("read", {}))
        except ValueError:
            return (None, "unaccredited_fixture")
        exp_loc_mode = "calibrate" if pid in CAL_IDS else "verify"
        if (
            loc_args["str"].get("point_id") != pid
            or loc_args["str"].get("feature_kind") != fkind
            or loc_args["str"].get("mode_id") != exp_loc_mode
            or loc_read["str"].get("point_id") != pid
            or loc_read["str"].get("mode_id") != exp_loc_mode
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
        s_op_id = s_ord.get("op_id")
        if (
            s_ord.get("verb") != "map_place_ground"
            or s_res.get("status") != "done"
            or s_op_id != s_res.get("op_id")
            or not isinstance(s_op_id, str)
            or not s_op_id
            or s_op_id in seen_cert_op_ids
        ):
            return (None, "unaccredited_fixture")
        seen_cert_op_ids.add(s_op_id)
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
    params_ok, params_err = f03_common.verify_eval_params_at_commit(manifest, repo_root=root)
    if not params_ok:
        return _inconclusive(params_err or "params_unverified")
    historical_wire_cap = int(identity["params"]["wire_cap"])

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
        sat_err = _verify_sat_source(provenance, accred, samples_dir)
        if sat_err is not None:
            return _inconclusive(sat_err)

    # N25 + N31: Verificar fixture y captura certificadora
    reconstructed_certified, cert_err = _verify_certifying_capture(
        fixture, cert_cap, provenance, fixture_path, cert_path, build, root
    )
    if cert_err is not None or reconstructed_certified is None:
        return _inconclusive(cert_err or "unaccredited_fixture")

    ops, ops_err = _extract_complete_ops(bridge_rows, build, expected_stamp)
    if ops_err is not None:
        if ops_err.startswith(_ATTRIBUTION_ERROR_PREFIXES):
            return _attribution_failure(ops_err)
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
        for req_nk in ("x0_m", "z0_m", "step_m", "row_n", "chunk_n"):
            if not _is_finite_num(u_args["num"].get(req_nk)):
                return _inconclusive("missing_world_read_args")
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
            _exact_int(u_args["num"].get("row_n")) != r_glob
            or _exact_int(u_args["num"].get("chunk_n")) != 8
            or not _same_num(u_args["num"].get("x0_m"), exp_x0, 1e-3)
            or not _same_num(u_args["num"].get("z0_m"), exp_z0, 1e-3)
            or not _same_num(u_args["num"].get("step_m"), 480.0, 1e-3)
            or len(u_read["rows"]) != 8
        ):
            return _inconclusive("grid_read_coordinates_mismatch")

        # La lectura observada tiene que repetir la geometria de la orden emitida,
        # no solo ser plausible: un origen puesto a cero en la respuesta se rechaza.
        for same_k in ("x0_m", "z0_m", "step_m", "row_n"):
            if not _same_num(u_read["num"].get(same_k), float(u_args["num"][same_k]), 1e-6):
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
        for req_nk in ("x0_m", "z0_m", "step_m", "row_n", "chunk_n"):
            if not _is_finite_num(u_args["num"].get(req_nk)):
                return _inconclusive("missing_world_read_args")
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
            _exact_int(u_args["num"].get("row_n")) != exp_row_n
            or _exact_int(u_args["num"].get("chunk_n")) != 8
            or not _same_num(u_args["num"].get("x0_m"), exp_x0, 1e-3)
            or not _same_num(u_args["num"].get("z0_m"), exp_z0, 1e-3)
            or not _same_num(u_args["num"].get("step_m"), 3.75, 1e-6)
            or len(u_read["rows"]) != 8
        ):
            return _inconclusive("patch_read_coordinates_mismatch")

        for same_k in ("x0_m", "z0_m", "step_m", "row_n"):
            if not _same_num(u_read["num"].get(same_k), float(u_args["num"][same_k]), 1e-6):
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
        map01_detail = "tiles_or_domains_present"
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
            l_args = loc_op["args"]
            if l_str.get("mode_id") != exp_mode or l_str.get("decision_id") != exp_dec or l_str.get("reject_reason_id") != "":
                map02_ok = False
                map02_detail = f"locate_decision_failed:{pid}:{l_str.get('decision_id')}:{l_str.get('reject_reason_id')}"
                break

            # La orden emitida y su respuesta tienen que hablar del mismo punto,
            # del mismo rasgo y del mismo modo: no se acepta un eco cambiado.
            if (
                l_args["str"].get("point_id") != pid
                or l_args["str"].get("feature_kind") != cert_info["feature_kind"]
                or l_args["str"].get("mode_id") != exp_mode
                or l_str.get("point_id") != pid
            ):
                map02_ok = False
                map02_detail = f"locate_order_mismatch:{pid}"
                break
            roi_x_min, roi_z_min, roi_x_max, roi_z_max = cert_info["world_roi_m"]
            if not (
                _same_num(l_args["num"].get("x_min_m"), roi_x_min, 1e-3)
                and _same_num(l_args["num"].get("z_min_m"), roi_z_min, 1e-3)
                and _same_num(l_args["num"].get("x_max_m"), roi_x_max, 1e-3)
                and _same_num(l_args["num"].get("z_max_m"), roi_z_max, 1e-3)
            ):
                map02_ok = False
                map02_detail = f"locate_roi_mismatch:{pid}"
                break

            if pid in CAL_IDS:
                if "req_x_m" in l_args["num"] or "req_z_m" in l_args["num"]:
                    map02_ok = False
                    map02_detail = f"calibrate_had_req_coords:{pid}"
                    break
                if not (_same_num(l_num.get("req_x_m"), 0.0, 1e-6) and _same_num(l_num.get("req_z_m"), 0.0, 1e-6)):
                    map02_ok = False
                    map02_detail = f"calibrate_req_not_zero:{pid}"
                    break
            else:
                arg_req_x = l_args["num"].get("req_x_m")
                arg_req_z = l_args["num"].get("req_z_m")
                if not (_is_finite_num(arg_req_x) and _is_finite_num(arg_req_z)):
                    map02_ok = False
                    map02_detail = f"verify_missing_req_args:{pid}"
                    break
                if not (
                    _same_num(l_num.get("req_x_m"), float(arg_req_x), 1e-6)
                    and _same_num(l_num.get("req_z_m"), float(arg_req_z), 1e-6)
                ):
                    map02_ok = False
                    map02_detail = f"verify_req_echo_mismatch:{pid}"
                    break

            w_rec = rebuilt_world_features[pid]

            # BLOQ 5: testigo independiente de la altura en las coordenadas del
            # rasgo.  Las muestras crudas de la corrida se contrastan con la
            # captura certificadora congelada antes de compararlas con lo que la
            # propia evidencia declara.  Desplazar a la vez las alturas del
            # parche, del localizador y de la colocacion no puede pasar.
            if abs(float(w_rec["srv_y_m"]) - float(cert_info["certified_y_m"])) > 0.02:
                map02_ok = False
                map02_detail = f"patch_vs_certified_height_mismatch:{pid}"
                break

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
                            v_args = v_op["args"]
                            # Coordenadas pedidas: de la orden, no del eco de la respuesta.
                            req_x = float(v_args["num"]["req_x_m"])
                            req_z = float(v_args["num"]["req_z_m"])
                            if not (
                                _same_num(v_num.get("req_x_m"), req_x, 1e-6)
                                and _same_num(v_num.get("req_z_m"), req_z, 1e-6)
                            ):
                                map02_ok = False
                                map02_detail = f"verify_req_echo_mismatch:{vid}"
                                break
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
    place_negative_ops = [("P_OUT", pout_op), ("P_BRIDGE", pbridge_op), ("P_ROOF", proof_op)]
    seq_posts: list[int] = []
    max_contact_err = 0.0

    # Testigo congelado de la caja de la plantilla: la colocacion certificada en
    # P_GROUND conserva su lectura de ClippingInfo.  La misma clase debe producir
    # la misma caja en todas las colocaciones (BLOQ 5: una caja que "compensa" la
    # altura cambia con el terreno y delata la fabricacion).
    pg_cert_read = wire.unpack_payload(
        cert_cap["surfaces"]["P_GROUND"]["place_ground_op"]["result"]["read"]
    )
    cert_box_min_y = float(pg_cert_read["num"]["bbox_min_y_m"])
    cert_box_max_y = float(pg_cert_read["num"]["bbox_max_y_m"])

    # N23: contadores exactos (no redondeados), no negativos y continuos durante
    # toda la sesion, incluidos los rechazos.  Se recorren en orden de emision.
    counters_ok = True
    counters_detail = "ok"
    prev_post: int | None = None
    for cpid, cop in sorted(
        place_positive_ops + place_negative_ops,
        key=lambda item: float(item[1]["enq_row"].get("t_ms", 0.0)),
    ):
        exact_vals: dict[str, int] = {}
        for ck in ("seq_pre_n", "seq_post_n", "ent_id_n", "pre_count_n", "post_count_n"):
            cval = _exact_int(cop["read"]["num"].get(ck))
            if cval is None or cval < 0:
                counters_ok = False
                counters_detail = f"non_exact_counter:{cpid}:{ck}"
                break
            exact_vals[ck] = cval
        if not counters_ok:
            break
        if exact_vals["pre_count_n"] != exact_vals["post_count_n"]:
            counters_ok = False
            counters_detail = f"cleanup_count_mismatch:{cpid}:{exact_vals['pre_count_n']}->{exact_vals['post_count_n']}"
            break
        if prev_post is not None and exact_vals["seq_pre_n"] != prev_post:
            counters_ok = False
            counters_detail = f"spawn_seq_not_continuous:{cpid}:{exact_vals['seq_pre_n']}!={prev_post}"
            break
        prev_post = exact_vals["seq_post_n"]

    if not counters_ok:
        map03_ok = False
        map03_detail = counters_detail

    for pid, pop in place_positive_ops if map03_ok else []:
        p_str = pop["read"]["str"]
        p_num = pop["read"]["num"]
        p_args = pop["args"]
        seq_pre = _exact_int(p_num.get("seq_pre_n"))
        seq_post = _exact_int(p_num.get("seq_post_n"))
        ent_id = _exact_int(p_num.get("ent_id_n"))
        pre_cnt = _exact_int(p_num.get("pre_count_n"))
        post_cnt = _exact_int(p_num.get("post_count_n"))

        # Coordenadas pedidas: de la orden emitida.  La respuesta solo puede
        # repetirlas; no se toma el eco de la respuesta como peticion.
        arg_req_x = p_args["num"].get("req_x_m")
        arg_req_z = p_args["num"].get("req_z_m")
        if not (_is_finite_num(arg_req_x) and _is_finite_num(arg_req_z)):
            map03_ok = False
            map03_detail = f"missing_req_args:{pid}"
            break
        req_x = float(arg_req_x)
        req_z = float(arg_req_z)
        if not (_same_num(p_num.get("req_x_m"), req_x, 1e-6) and _same_num(p_num.get("req_z_m"), req_z, 1e-6)):
            map03_ok = False
            map03_detail = f"place_req_echo_mismatch:{pid}"
            break
        arg_class = p_args["str"].get("class_id")
        if not isinstance(arg_class, str) or arg_class == "":
            map03_ok = False
            map03_detail = f"missing_class_args:{pid}"
            break
        if arg_class != CONTRACT_CLASS:
            map03_ok = False
            map03_detail = f"wrong_contract_class_args:{pid}:{arg_class}"
            break

        obs_x = float(p_num["obs_x_m"])
        obs_y = float(p_num["obs_y_m"])
        obs_z = float(p_num["obs_z_m"])
        bbox_min_y = float(p_num["bbox_min_y_m"])
        bbox_max_y = float(p_num["bbox_max_y_m"])
        obs_surf_y = float(p_num["obs_surf_y_m"])
        terrain_y = float(p_num["terrain_y_m"])

        if p_str.get("decision_id") != "placed" or p_str.get("reject_reason_id") != "":
            map03_ok = False
            map03_detail = f"not_placed:{pid}"
            break
        if seq_post != seq_pre + 1:
            map03_ok = False
            map03_detail = f"invalid_spawn_seq_delta:{pid}:{seq_pre}->{seq_post}"
            break
        if p_str.get("point_id") != pid or p_str.get("obs_class_id") != CONTRACT_CLASS:
            map03_ok = False
            map03_detail = f"wrong_obs_class:{pid}:{p_str.get('obs_class_id')}"
            break
        if not (bbox_max_y > bbox_min_y):
            map03_ok = False
            map03_detail = f"invalid_bbox:{pid}"
            break
        if not (_same_num(bbox_min_y, cert_box_min_y, 1e-6) and _same_num(bbox_max_y, cert_box_max_y, 1e-6)):
            map03_ok = False
            map03_detail = (
                f"box_witness_mismatch:{pid}:{bbox_min_y}/{bbox_max_y}"
                f"!={cert_box_min_y}/{cert_box_max_y}"
            )
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

        # Testigo independiente de la superficie en las coordenadas que tocan:
        # la superficie observada se acredita contra la captura certificadora
        # congelada (altura del rasgo) y, para P_GROUND, contra la superficie
        # certificada.  El contacto se calcula en la posicion observada, como
        # exige el brief, sin imponer igualdad vertical entre posiciones distintas
        # (un desplazamiento de 0,04 m puede cambiar 0,12 m la altura).
        if pid in VER_IDS:
            cert_y = float(reconstructed_certified[pid]["certified_y_m"])
            if abs(obs_surf_y - cert_y) > 1.5:
                map03_ok = False
                map03_detail = f"obs_surface_vs_certified_mismatch:{pid}:{obs_surf_y:.3f}!={cert_y:.3f}"
                break
            w_ref = rebuilt_world_features[pid]
            if abs(terrain_y - float(w_ref["srv_y_m"])) > 5.0:
                map03_ok = False
                map03_detail = f"terrain_witness_mismatch:{pid}:{terrain_y:.3f}"
                break
            srv_x = float(ver_locate_ops[pid]["read"]["num"]["srv_x_m"])
            srv_z = float(ver_locate_ops[pid]["read"]["num"]["srv_z_m"])
            cert_x = reconstructed_certified[pid]["certified_x_m"]
            cert_z = reconstructed_certified[pid]["certified_z_m"]
            if math.hypot(obs_x - srv_x, obs_z - srv_z) >= 10.0 or math.hypot(obs_x - cert_x, obs_z - cert_z) >= 10.0:
                map03_ok = False
                map03_detail = f"verify_placement_drift:{pid}"
                break
        else:
            cap_surf = cert_cap["surfaces"]["P_GROUND"]
            if not (
                _same_num(terrain_y, float(cap_surf["terrain_y_m"]), 0.05)
                # La superficie se acredita en la posicion observada, no en la
                # pedida: un desplazamiento de 0,04 m puede cambiar 0,12 m la
                # altura.  Se acota contra la superficie certificada en la pedida.
                and _same_num(obs_surf_y, float(cap_surf["terrain_y_m"]), 0.5)
                and _same_num(p_num.get("road_y_m"), float(cap_surf["road_y_m"]), 0.05)
                and _same_num(p_num.get("ray_hit_b"), float(cap_surf["ray_hit_b"]), 1e-6)
                and _same_num(p_num.get("hit_y_m"), float(cap_surf["hit_y_m"]), 0.05)
            ):
                map03_ok = False
                map03_detail = "pground_surface_witness_mismatch"
                break
            pground_fix = next(p for p in fixture["placement_points"] if p["point_id"] == "P_GROUND")
            if math.hypot(obs_x - float(pground_fix["req_x_m"]), obs_z - float(pground_fix["req_z_m"])) >= 10.0:
                map03_ok = False
                map03_detail = "pground_certified_drift"
                break

        # La posicion observada tiene que coincidir con la proyeccion independiente
        # del rasgo de imagen (no solo con la peticion, que podria ser un eco).
        if a_ok is not None and b_ok is not None:
            if pid in VER_IDS:
                u_proj, v_proj = detected_img_features[pid]
            else:
                pground_fix = next(p for p in fixture["placement_points"] if p["point_id"] == "P_GROUND")
                u_proj = float(pground_fix["u_px"])
                v_proj = float(pground_fix["v_px"])
            x_proj, z_proj = apply_affine_2d(a_ok, b_ok, u_proj, v_proj)
            if math.hypot(obs_x - x_proj, obs_z - z_proj) > 0.05:
                map03_ok = False
                map03_detail = f"observed_position_vs_projection:{pid}"
                break

        # El contacto se mide en la posicion observada, contra la superficie
        # observada alli (SurfaceY(obs_x, obs_z)), no contra la pedida.
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
                i_args = iop["args"]
                cert_info = reconstructed_certified[vid]
                arg_req_x = i_args["num"].get("req_x_m")
                arg_req_z = i_args["num"].get("req_z_m")
                if not (_is_finite_num(arg_req_x) and _is_finite_num(arg_req_z)):
                    map04_ok = False
                    map04_detail = f"inv_missing_req_args:{vid}"
                    break
                req_x = float(arg_req_x)
                req_z = float(arg_req_z)
                if not (
                    _same_num(i_num.get("req_x_m"), req_x, 1e-6)
                    and _same_num(i_num.get("req_z_m"), req_z, 1e-6)
                ):
                    map04_ok = False
                    map04_detail = f"inv_req_echo_mismatch:{vid}"
                    break
                if i_args["str"].get("mode_id") != "verify" or i_args["str"].get("point_id") != vid:
                    map04_ok = False
                    map04_detail = f"inv_order_mismatch:{vid}"
                    break
                # BLOQ 3: la orden negativa tambien tiene que hablar del rasgo y de
                # la ventana acreditados, no de un ``feature_kind`` inventado ni de
                # una ventana puesta a cero.
                if i_args["str"].get("feature_kind") != cert_info["feature_kind"]:
                    map04_ok = False
                    map04_detail = f"inv_feature_kind_mismatch:{vid}"
                    break
                inv_roi = cert_info["world_roi_m"]
                if not (
                    _same_num(i_args["num"].get("x_min_m"), inv_roi[0], 1e-3)
                    and _same_num(i_args["num"].get("z_min_m"), inv_roi[1], 1e-3)
                    and _same_num(i_args["num"].get("x_max_m"), inv_roi[2], 1e-3)
                    and _same_num(i_args["num"].get("z_max_m"), inv_roi[3], 1e-3)
                ):
                    map04_ok = False
                    map04_detail = f"inv_roi_mismatch:{vid}"
                    break
                srv_x = float(i_num["srv_x_m"])
                srv_y = float(i_num["srv_y_m"])
                srv_z = float(i_num["srv_z_m"])
                prom = float(i_num["prominence_m"])
                # Lectura independiente: el rasgo devuelto tiene que ser el que
                # reconstruye el evaluador desde las 256 muestras del parche.
                w_rec = rebuilt_world_features[vid]
                if (
                    abs(srv_x - float(w_rec["srv_x_m"])) > 0.02
                    or abs(srv_y - float(w_rec["srv_y_m"])) > 0.02
                    or abs(srv_z - float(w_rec["srv_z_m"])) > 0.02
                    or abs(prom - float(w_rec["prominence_m"])) > 0.02
                ):
                    map04_ok = False
                    map04_detail = f"inv_srv_vs_patch256_mismatch:{vid}"
                    break
                p_idx = PATCH_IDS.index(vid)
                patch_cells_set = [
                    (
                        inv_roi[0] + 3.75 * float(c),
                        inv_roi[3] - 3.75 * float(r),
                        patch_samples[(p_idx, r, c)][0],
                        patch_samples[(p_idx, r, c)][1],
                    )
                    for r in range(16)
                    for c in range(16)
                ]
                rows_in_patch = True
                for a_row in iop["read"]["rows"]:
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
                    map04_ok = False
                    map04_detail = f"inv_audit_rows_not_in_patch:{vid}"
                    break

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

    def _place_negative(
        neg_id: str,
        neg_op: dict,
        cap_surf: dict,
        expect_reason: str,
        require_elevated: bool,
    ) -> tuple[bool, str]:
        n_str = neg_op["read"]["str"]
        n_num = neg_op["read"]["num"]
        n_args = neg_op["args"]
        arg_req_x = n_args["num"].get("req_x_m")
        arg_req_z = n_args["num"].get("req_z_m")
        arg_class = n_args["str"].get("class_id")
        if not (_is_finite_num(arg_req_x) and _is_finite_num(arg_req_z)):
            return (False, f"missing_req_args:{neg_id}")
        req_x = float(arg_req_x)
        req_z = float(arg_req_z)
        if not (_same_num(n_num.get("req_x_m"), req_x, 1e-6) and _same_num(n_num.get("req_z_m"), req_z, 1e-6)):
            return (False, f"req_echo_mismatch:{neg_id}")
        if not isinstance(arg_class, str) or arg_class == "":
            return (False, f"missing_class_args:{neg_id}")
        if arg_class != CONTRACT_CLASS:
            return (False, f"wrong_contract_class_args:{neg_id}:{arg_class}")
        if n_str.get("point_id") != neg_id:
            return (False, f"point_mismatch:{neg_id}")

        # La superficie de la captura certificada es el testigo independiente:
        # las lecturas de la corrida tienen que coincidir con ella.
        if not (
            _same_num(req_x, float(cap_surf["req_x_m"]), 1e-3)
            and _same_num(req_z, float(cap_surf["req_z_m"]), 1e-3)
            and _same_num(n_num.get("terrain_y_m"), float(cap_surf["terrain_y_m"]), 0.05)
            and _same_num(n_num.get("road_y_m"), float(cap_surf["road_y_m"]), 0.05)
            and _same_num(n_num.get("ray_hit_b"), float(cap_surf["ray_hit_b"]), 1e-6)
            and _same_num(n_num.get("hit_y_m"), float(cap_surf["hit_y_m"]), 0.05)
        ):
            return (False, f"surface_witness_mismatch:{neg_id}")
        if n_str.get("hit_class_id", "") != cap_surf["hit_class_id"]:
            return (False, f"hit_class_witness_mismatch:{neg_id}")

        cap_t_y = float(cap_surf["terrain_y_m"])
        cap_r_y = float(cap_surf["road_y_m"])
        cap_ray = float(cap_surf["ray_hit_b"])
        cap_h_y = float(cap_surf["hit_y_m"])
        cap_elevated = (cap_r_y - cap_t_y > 0.25) or (cap_ray == 1.0 and cap_h_y - cap_t_y > 0.25)
        if require_elevated and not cap_elevated:
            return (False, f"fixture_surface_mismatch:{neg_id}")
        if not require_elevated:
            if not (req_x < 0.0 or req_x > 15360.0 or req_z < 0.0 or req_z > 15360.0):
                return (False, f"out_of_map_check_failed:{neg_id}")

        vals = {}
        for nk in ("seq_pre_n", "seq_post_n", "ent_id_n", "pre_count_n", "post_count_n"):
            iv = _exact_int(n_num.get(nk))
            if iv is None or iv < 0:
                return (False, f"non_exact_counter:{neg_id}:{nk}")
            vals[nk] = iv
        if not (
            vals["seq_post_n"] == vals["seq_pre_n"]
            and n_str.get("obs_class_id") == ""
            and vals["ent_id_n"] == 0
            and vals["post_count_n"] == vals["pre_count_n"]
        ):
            return (False, f"spawned_on_reject:{neg_id}")
        if n_str.get("decision_id") != "rejected" or n_str.get("reject_reason_id") != expect_reason:
            return (False, f"reason_failed:{neg_id}:{n_str.get('decision_id')}:{n_str.get('reject_reason_id')}")
        return (True, "ok")

    map05_ok, map05_detail = _place_negative("P_OUT", pout_op, cert_cap["surfaces"]["P_OUT"], "out_of_map", False)
    checks_out.append({"id": "MAP-05", "status": "pass" if map05_ok else "fail", "detail": map05_detail})

    map06_ok, map06_detail = _place_negative(
        "P_BRIDGE", pbridge_op, cert_cap["surfaces"]["P_BRIDGE"], "elevated_surface", True
    )
    checks_out.append({"id": "MAP-06", "status": "pass" if map06_ok else "fail", "detail": map06_detail})

    map07_ok, map07_detail = _place_negative(
        "P_ROOF", proof_op, cert_cap["surfaces"]["P_ROOF"], "elevated_surface", True
    )
    checks_out.append({"id": "MAP-07", "status": "pass" if map07_ok else "fail", "detail": map07_detail})

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
