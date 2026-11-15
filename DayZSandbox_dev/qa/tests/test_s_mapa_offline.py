"""Suite de pruebas offline del oraculo de S-mapa (F0.3).

Los tests de unidad sobre evidencia sintetica, fixture, presupuesto de cable,
reevaluacion historica, ceguera/invariancia y negativas antifalsificacion
pasan sin necesidad de la implementacion del runner ni de la extension.
Los tests end-to-end tienen prefijo ``test_e2e_`` y fallan mientras
``s_mapa_run.py``, ``fake_ext_map.py`` y ``DSBX_QA_X_Map.c`` sean esqueletos.
"""

from __future__ import annotations

import binascii
import copy
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock
import zlib

QA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = QA_DIR.parents[1]
if str(QA_DIR) not in sys.path:
    sys.path.insert(0, str(QA_DIR))

import bridge_qa
import f03_common
import fake_peer
import gate_core
import m1_gate
import s_mapa_eval
import s_mapa_mutants
import wire


FIXTURE_PATH = QA_DIR / "fixtures" / "s_mapa_puntos.json"


def _encode_png_8bit_gray(rows_bytes: list[bytes]) -> bytes:
    """Codifica una matriz de filas en un PNG 8-bit escala de grises valido."""
    height = len(rows_bytes)
    width = len(rows_bytes[0]) if height else 0

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        crc = binascii.crc32(ctype + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw_scanlines = b"".join(b"\x00" + r for r in rows_bytes)
    idat = zlib.compress(raw_scanlines, level=1)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def _compute_stamped_fixture(
    raw_fixture: dict,
    *,
    cert_git_head: str,
    cert_probe_stamp: str,
    cert_wire_cap: int = 3500,
) -> dict:
    """Actualiza los sellos y hashes SHA-256 de una copia de s_mapa_puntos.json."""
    fx = copy.deepcopy(raw_fixture)
    cert = fx["certifying_capture"]
    cert["certifying_git_head"] = cert_git_head
    cert["certifying_probe_stamp"] = cert_probe_stamp
    cert["certifying_wire_cap"] = cert_wire_cap
    cert["certifying_hello"]["probe_ver"] = f"dsbx-qa1+{cert_probe_stamp}"

    y_min = float(cert["global_luma_range"]["y_min_m"])
    y_max = float(cert["global_luma_range"]["y_max_m"])
    for pid, p_obj in cert["patches"].items():
        lumas = [
            s_mapa_eval.quantize_luma(float(s[0]), float(s[1]), y_min, y_max)
            for s in p_obj["samples_256"]
        ]
        p_obj["patch_luma_256"] = lumas
        p_obj["patch_luma_sha256"] = hashlib.sha256(bytes(lumas)).hexdigest()

    cert_bytes = json.dumps(cert, indent=2, sort_keys=True).encode("utf-8")
    cert_sha = hashlib.sha256(cert_bytes).hexdigest()
    fx["accreditation"]["certifying_probe_stamp"] = cert_probe_stamp
    fx["accreditation"]["certifying_capture_sha256"] = cert_sha
    return fx


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows]
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _strip_enforce_comments(txt: str) -> str:
    """Quita comentarios de Enforce Script para no acreditar un .c solo-comentario."""
    out: list[str] = []
    i = 0
    n = len(txt)
    while i < n:
        if txt.startswith("//", i):
            j = txt.find("\n", i)
            i = n if j < 0 else j
        elif txt.startswith("/*", i):
            j = txt.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif txt[i] in ("'", '"'):
            quote = txt[i]
            out.append(txt[i])
            i += 1
            while i < n:
                out.append(txt[i])
                if txt[i] == "\\":
                    if i + 1 < n:
                        out.append(txt[i + 1])
                        i += 2
                        continue
                elif txt[i] == quote:
                    i += 1
                    break
                i += 1
        else:
            out.append(txt[i])
            i += 1
    return "".join(out)


def _probe_c_problems(txt: str) -> list[str]:
    """Comprueba la sonda Enforce por codigo real, no por menciones en comentarios."""
    code = _strip_enforce_comments(txt)
    problems: list[str] = []
    for token in (
        "class DSBX_QA_X_Map",
        "override bool Handles(",
        '"map_world_read"',
        '"map_feature_locate"',
        '"map_place_ground"',
        "SpawnTrackedObject",
        "ObjectDelete",
        "SurfaceY",
        "SurfaceRoadY",
        "SurfaceIsSea",
        "SurfaceGetSeaLevel",
        "RaycastRVProxy",
        "RayCastBullet",
    ):
        if token not in code:
            problems.append(f"missing_code_token:{token}")
    if '"not_implemented"' in code:
        problems.append("still_not_implemented")
    if code.count("CreateObjectEx(") != 1:
        problems.append(f"create_object_ex_count:{code.count('CreateObjectEx(')}")
    return problems


def _locate_payload_problems(u_read: dict) -> list[str]:
    """Rechaza una extension que solo devuelve decision_id='located'."""
    problems: list[str] = []
    for sk in ("point_id", "mode_id", "decision_id", "reject_reason_id"):
        if not isinstance(u_read.get("str", {}).get(sk), str):
            problems.append(f"missing_locate_str:{sk}")
    for nk in (
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
    ):
        val = u_read.get("num", {}).get(nk)
        if not isinstance(val, (int, float)) or isinstance(val, bool) or not math.isfinite(float(val)):
            problems.append(f"missing_locate_num:{nk}")
    rows = u_read.get("rows")
    if not isinstance(rows, list) or len(rows) != 2:
        problems.append("missing_locate_audit_rows")
    else:
        for row in rows:
            for col in ("sx_m", "sz_m", "y_m", "sea_b"):
                if not isinstance(row.get(col), (int, float)):
                    problems.append(f"missing_locate_row_col:{col}")
    return problems


class _TrafficRecord:
    def __init__(self) -> None:
        self.bridge: dict[str, list[dict]] = {}
        self.contexts: list[dict] = []


_RECORD = _TrafficRecord()


def _recording_writer_factory():
    base = f03_common._JsonlWriter

    class _RecordingWriter(base):  # type: ignore[misc, valid-type]
        def __init__(self, path):
            super().__init__(path)
            if Path(path).name == "bridge.jsonl":
                _RECORD.bridge.setdefault(str(Path(path)), [])

        def write(self, row):
            super().write(row)
            if Path(self.path).name == "bridge.jsonl":
                _RECORD.bridge[str(Path(self.path))].append(copy.deepcopy(row))

    return _RecordingWriter


def _recording_part_context_class():
    base = f03_common.PartContext

    class _RecordingPartContext(base):  # type: ignore[misc, valid-type]
        def open(self):
            super().open()
            _RECORD.contexts.append(
                {
                    "part_dir": str(self.part_dir),
                    "pids": dict(self.fake_peer_pids),
                    "spawned": sorted(self.procs.keys()),
                }
            )

    return _RecordingPartContext


def _verify_part_against_record(part_dir: Path, rec: _TrafficRecord) -> list[str]:
    """Comprueba que la evidencia de la parte viene del nucleo, no del runner."""
    problems: list[str] = []
    pdir = Path(part_dir)
    bridge_path = pdir / "samples" / "bridge.jsonl"
    if not bridge_path.is_file():
        return ["missing_bridge"]
    recorded = rec.bridge.get(str(bridge_path), [])
    written = f03_common.read_jsonl(bridge_path)
    if written != recorded:
        problems.append("bridge_not_from_core")
    if not recorded:
        problems.append("no_recorded_traffic")

    ctx = next((c for c in rec.contexts if c["part_dir"] == str(pdir)), None)
    if ctx is None:
        problems.append("missing_part_context")
        return problems
    pids = ctx["pids"]
    if not pids.get("server") or not pids.get("client"):
        problems.append("runner_without_peers")
    if ctx["spawned"] != ["client", "server"]:
        problems.append("peers_not_spawned")

    try:
        manifest = gate_core.read_json(pdir / "manifest.json")
    except Exception:
        problems.append("missing_manifest")
        return problems
    exec_ids = manifest.get("execution_identity") if isinstance(manifest, dict) else None
    if not isinstance(exec_ids, dict):
        problems.append("missing_execution_identity")
        return problems
    if exec_ids.get("fake_peer_pids") != pids:
        problems.append("manifest_pids_mismatch")

    hellos = [r for r in written if r.get("ev") == "hello" and r.get("http") == 200]
    for role in ("server", "client"):
        if not any(r.get("peer") == role for r in hellos):
            problems.append(f"missing_hello:{role}")
    if not any(r.get("ev") == "enq" for r in written):
        problems.append("no_enqueued_ops")
    if not any(r.get("ev") == "result" and r.get("http") == 200 for r in written):
        problems.append("no_results")
    return problems


def _build_synthetic_part(
    part_dir: Path,
    *,
    git_head: str,
    probe_stamp: str,
    wire_cap: int = 3500,
    build: str = "offline",
    git_dirty: bool = False,
    mutant: str | None = None,
    ent_id_for_valid_spawns: int = 0,
    contact_offset_y_m: float = 0.0,
    common_srv_bias_x_m: float = 0.0,
    constant_terrain_y: float | None = None,
    tamper_bg_without_tile_url: bool = False,
    spawn_then_reject_all_negatives: bool = False,
    custom_fixture: dict | None = None,
    nonce: str = "0123456789abcdef",
    exec_port: int = 53100,
    exec_pids: tuple[int, int] = (4101, 4102),
) -> dict:
    """Construye un directorio de parte sintetico completo para S-mapa."""
    pdir = Path(part_dir)
    samples = pdir / "samples"
    samples.mkdir(parents=True, exist_ok=True)

    base_fx = custom_fixture if custom_fixture is not None else gate_core.read_json(FIXTURE_PATH)
    fx = _compute_stamped_fixture(
        base_fx,
        cert_git_head=git_head,
        cert_probe_stamp=probe_stamp,
        cert_wire_cap=wire_cap,
    )
    cert_cap = fx["certifying_capture"]
    cert_bytes = json.dumps(cert_cap, indent=2, sort_keys=True).encode("utf-8")
    cert_path = samples / "s_mapa_certifying_capture.json"
    cert_path.write_bytes(cert_bytes)
    fix_path = samples / "s_mapa_puntos.json"
    gate_core.write_json(fix_path, fx)

    fix_sha = f03_common.sha256_file_hex(fix_path)
    cert_sha = f03_common.sha256_file_hex(cert_path)

    bridge_rows: list[dict] = [
        {
            "args": {
                "build": build,
                "inst": "srv-map-1",
                "peer": "server",
                "probe_ver": f"dsbx-qa1+{probe_stamp}",
                "proto": "qa0",
            },
            "ev": "hello",
            "http": 200,
            "inst": "srv-map-1",
            "ok": True,
            "peer": "server",
            "t_ms": 10.0,
        },
        {
            "args": {
                "build": build,
                "inst": "cli-map-1",
                "peer": "client",
                "probe_ver": f"dsbx-qa1+{probe_stamp}",
                "proto": "qa0",
            },
            "ev": "hello",
            "http": 200,
            "inst": "cli-map-1",
            "ok": True,
            "peer": "client",
            "t_ms": 11.0,
        },
    ]

    op_seq = [0]
    clock_ms = [20.0]
    frame_no = [100]

    def _next_op_id() -> str:
        op_seq[0] += 1
        return f"{nonce}-{op_seq[0]}"

    def _emit_op(verb: str, args_payload: dict, read_payload: dict | None, status: str = "done", reason: str = "") -> str:
        oid = _next_op_id()
        clock_ms[0] = round(clock_ms[0] + 1.0, 3)
        frame_no[0] += 1
        t_enq = clock_ms[0]
        bridge_rows.append(
            {
                "args": args_payload,
                "ev": "enq",
                "inst": "srv-map-1",
                "op_id": oid,
                "peer": "server",
                "t_ms": t_enq,
                "verb": verb,
            }
        )
        args_with_fault = copy.deepcopy(args_payload)
        args_with_fault["sk"] = list(args_with_fault.get("sk", [])) + ["qa_fault"]
        args_with_fault["sv"] = list(args_with_fault.get("sv", [])) + [wire.QA_FAULT_NONE]
        poll_order = {
            "args": bridge_qa.full_args(args_with_fault),
            "inst": "srv-map-1",
            "issued_ms": t_enq,
            "op_id": oid,
            "ttl_ms": 5000,
            "verb": verb,
        }
        p_len = len(wire.poll_wire_bytes(poll_order, now_ms=t_enq + 0.5))
        bridge_rows.append(
            {
                "body_len": p_len,
                "ev": "poll",
                "frame": frame_no[0],
                "held_ms": 0.5,
                "http": 200,
                "inst": "srv-map-1",
                "n_ops": 1,
                "now_ms": round(t_enq + 0.5, 3),
                "op_ids": [oid],
                "peer": "server",
                "t_ms": round(t_enq + 0.5, 3),
                "tick_s": round(t_enq / 1000.0, 3),
            }
        )
        read_full = dict(read_payload) if read_payload is not None else dict(wire.empty_payload())
        read_full["frame"] = frame_no[0]
        read_full["tick_s"] = round((t_enq + 1.0) / 1000.0, 3)
        read_full["pos"] = [0.0, 0.0, 0.0]
        read_full["ypr"] = [0.0, 0.0, 0.0]
        read_full["y"] = 0.0
        read_full["fog"] = 0.0
        read_full["rpc_log"] = []
        read_full["has"] = ["payload"] if status == "done" else []
        res_obj = {
            "done_ms": round(t_enq + 1.0, 3),
            "dup": False,
            "frame_done": frame_no[0] + 1,
            "frame_recv": frame_no[0],
            "op_id": oid,
            "read": read_full,
            "reason": reason,
            "recv_ms": round(t_enq + 0.5, 3),
            "status": status,
        }
        r_len = len(wire.result_wire_bytes(res_obj))
        bridge_rows.append(
            {
                "body_len": r_len,
                "ev": "result",
                "http": 200,
                "op_id": oid,
                "peer": "server",
                "result": res_obj,
                "t_ms": round(t_enq + 1.0, 3),
            }
        )
        return oid

    # Paso 1: 128 grid_row + 192 patch_row
    grid_op_ids: list[str] = []
    patch_op_ids: list[str] = []
    grid_samples: dict[tuple[int, int], tuple[float, float]] = {}
    patch_samples: dict[tuple[int, int, int], tuple[float, float]] = {}
    all_samples_flat: list[list[float]] = []

    for r_g in range(32):
        z0 = 15360.0 - 480.0 * float(r_g)
        for c_chunk in range(4):
            x0 = 480.0 * float(c_chunk * 8)
            row_dicts = []
            for k in range(8):
                c_g = c_chunk * 8 + k
                if constant_terrain_y is not None:
                    yv, sb = (constant_terrain_y, 0.0)
                elif r_g >= 28 or c_g >= 29:
                    yv, sb = (0.0, 1.0)
                else:
                    # Gradiente Norte-Sur fuerte para garantizar mean_abs_diff_flipped >= 15.0 y sigma_luma >= 5.0
                    yv = float((31 - r_g) * 7 + (c_g % 5) * 4)
                    sb = 0.0
                grid_samples[(r_g, c_g)] = (yv, sb)
                all_samples_flat.append([yv, sb])
                row_dicts.append({"y_m": yv, "sea_b": sb})
            a_pl = wire.pack_payload(
                scalars_str={"mode_id": "grid_row"},
                scalars_num={"x0_m": x0, "z0_m": z0, "step_m": 480.0, "row_n": float(r_g), "chunk_n": 8.0},
            )
            r_pl = wire.pack_payload(
                scalars_str={"world_name": "chernarusplus", "mode_id": "grid_row"},
                scalars_num={
                    "world_size_m": 15360.0,
                    "sea_level_m": 0.0,
                    "x0_m": x0,
                    "z0_m": z0,
                    "step_m": 480.0,
                    "row_n": float(r_g),
                    "tick_ms": clock_ms[0],
                    "frame": float(frame_no[0]),
                },
                num_cols=["y_m", "sea_b"],
                row_dicts=row_dicts,
            )
            grid_op_ids.append(_emit_op("map_world_read", a_pl, r_pl))

    for p_idx, pid in enumerate(s_mapa_eval.PATCH_IDS):
        p_cap = cert_cap["patches"][pid]
        u0, v0, _, _ = p_cap["roi_px"]
        s256 = p_cap["samples_256"]
        for r_l in range(16):
            z0 = 15360.0 - 3.75 * float(v0 + r_l)
            row_n_val = float(p_idx * 16 + r_l)
            for c_chunk in range(2):
                c_base = c_chunk * 8
                x0 = 3.75 * float(u0 + c_base)
                row_dicts = []
                for k in range(8):
                    c_l = c_base + k
                    yv, sb = float(s256[r_l * 16 + c_l][0]), float(s256[r_l * 16 + c_l][1])
                    if constant_terrain_y is not None:
                        yv, sb = (constant_terrain_y, 0.0)
                    patch_samples[(p_idx, r_l, c_l)] = (yv, sb)
                    all_samples_flat.append([yv, sb])
                    row_dicts.append({"y_m": yv, "sea_b": sb})
                a_pl = wire.pack_payload(
                    scalars_str={"mode_id": "patch_row"},
                    scalars_num={"x0_m": x0, "z0_m": z0, "step_m": 3.75, "row_n": row_n_val, "chunk_n": 8.0},
                )
                r_pl = wire.pack_payload(
                    scalars_str={"world_name": "chernarusplus", "mode_id": "patch_row"},
                    scalars_num={
                        "world_size_m": 15360.0,
                        "sea_level_m": 0.0,
                        "x0_m": x0,
                        "z0_m": z0,
                        "step_m": 3.75,
                        "row_n": row_n_val,
                        "tick_ms": clock_ms[0],
                        "frame": float(frame_no[0]),
                    },
                    num_cols=["y_m", "sea_b"],
                    row_dicts=row_dicts,
                )
                patch_op_ids.append(_emit_op("map_world_read", a_pl, r_pl))

    land_vals = [yv for yv, sb in all_samples_flat if sb == 0.0]
    y_min_m = min(land_vals) if land_vals else 0.0
    y_max_m = max(land_vals) if land_vals else 254.0

    # Construir raster 4096x4096
    bg_rows: list[bytes] = []
    for r_g in range(32):
        ba = bytearray(4096)
        for c_g in range(32):
            yv, sb = grid_samples[(r_g, c_g)]
            lv = s_mapa_eval.quantize_luma(yv, sb, y_min_m, y_max_m)
            ba[c_g * 128 : (c_g + 1) * 128] = bytes([lv]) * 128
        bg_rows.append(bytes(ba))

    raster_rows: list[bytearray] = [bytearray(bg_rows[v // 128]) for v in range(4096)]
    if mutant == "external_tiles" or tamper_bg_without_tile_url:
        for v in range(4096):
            tile_r = (v // 256) % 2
            line_ba = bytearray(4096)
            for t_c in range(16):
                lv = 40 if (tile_r + t_c) % 2 == 0 else 200
                line_ba[t_c * 256 : (t_c + 1) * 256] = bytes([lv]) * 256
            raster_rows[v] = line_ba

    for p_idx, pid in enumerate(s_mapa_eval.PATCH_IDS):
        u0, v0, _, _ = cert_cap["patches"][pid]["roi_px"]
        for r_l in range(16):
            for c_l in range(16):
                yv, sb = patch_samples[(p_idx, r_l, c_l)]
                raster_rows[v0 + r_l][u0 + c_l] = s_mapa_eval.quantize_luma(yv, sb, y_min_m, y_max_m)

    png_bytes = _encode_png_8bit_gray([bytes(r) for r in raster_rows])
    png_path = samples / "chernarus_local.png"
    png_path.write_bytes(png_bytes)
    png_sha = f03_common.sha256_file_hex(png_path)

    samples_sha = hashlib.sha256(json.dumps(all_samples_flat, separators=(",", ":")).encode("utf-8")).hexdigest()
    tile_urls = ["https://tiles.izurvive.example/{z}/{x}/{y}.png"] if mutant == "external_tiles" else []
    prov_obj = {
        "schema": "dsbx.map.provenance.v4",
        "world_name": "chernarusplus",
        "world_size_m": 15360.0,
        "sea_level_m": 0.0,
        "source_kind": "mod_relief_plan_b",
        "image_relpath": "samples/chernarus_local.png",
        "image_sha256": png_sha,
        "fixture_relpath": "samples/s_mapa_puntos.json",
        "fixture_sha256": fix_sha,
        "certifying_evidence_relpath": "samples/s_mapa_certifying_capture.json",
        "certifying_capture_sha256": cert_sha,
        "width_px": 4096,
        "height_px": 4096,
        "bit_depth": 8,
        "color_type": 0,
        "step_px_m": 3.75,
        "y_min_m": y_min_m,
        "y_max_m": y_max_m,
        "grid_op_ids": grid_op_ids,
        "patch_op_ids": patch_op_ids,
        "samples_sha256": samples_sha,
        "crs": "CRS.Simple",
        "tile_urls": tile_urls,
        "external_domains": [],
    }
    gate_core.write_json(samples / "map_provenance.json", prov_obj)

    # Paso 2: calibrate_C1_C3
    cal_op_ids: list[str] = []
    cal_px: list[tuple[float, float]] = []
    cal_world: list[tuple[float, float]] = []
    all_pts_by_id = {
        p["point_id"]: p for p in fx["calibration_points"] + fx["verification_points"]
    }

    def _audit_rows_for_patch(pid: str, w_det: dict, bias_x: float = 0.0) -> list[dict[str, float]]:
        p_info = all_pts_by_id[pid]
        x_min, z_min, x_max, z_max = p_info["world_roi_m"]
        if p_info["feature_kind"] == "relief_peak":
            return [
                {"sx_m": x_min + bias_x, "sz_m": z_max, "y_m": float(w_det["y_border_m"]), "sea_b": 0.0},
                {"sx_m": float(w_det["srv_x_m"]) + bias_x, "sz_m": float(w_det["srv_z_m"]), "y_m": float(w_det["srv_y_m"]), "sea_b": 0.0},
            ]
        ap0, ap1 = w_det["audit_pair"]
        return [
            {"sx_m": ap0[0] + bias_x, "sz_m": ap0[1], "y_m": ap0[2], "sea_b": ap0[3]},
            {"sx_m": ap1[0] + bias_x, "sz_m": ap1[1], "y_m": ap1[2], "sea_b": ap1[3]},
        ]

    for cid in s_mapa_eval.CAL_IDS:
        p_info = all_pts_by_id[cid]
        p_idx = s_mapa_eval.PATCH_IDS.index(cid)
        p256 = [patch_samples[(p_idx, r, c)] for r in range(16) for c in range(16)]
        w_det = s_mapa_eval.locate_world_feature_from_patch(
            p256, p_info["world_roi_m"], p_info["feature_kind"], 0.0
        )
        if w_det is None:
            w_det = {
                "srv_x_m": float(p_info["certified_x_m"]),
                "srv_y_m": float(p_info["certified_y_m"]),
                "srv_z_m": float(p_info["certified_z_m"]),
                "prominence_m": 10.0,
                "y_border_m": 0.0,
                "audit_pair": (
                    (float(p_info["certified_x_m"]), float(p_info["certified_z_m"]), 4.0, 0.0),
                    (float(p_info["certified_x_m"]), float(p_info["certified_z_m"]), 0.0, 1.0),
                ),
            }
        srv_x = float(w_det["srv_x_m"]) + common_srv_bias_x_m
        srv_y = float(w_det["srv_y_m"])
        srv_z = float(w_det["srv_z_m"])
        prom = float(w_det["prominence_m"])
        cal_px.append((float(p_info["certified_u_px"]), float(p_info["certified_v_px"])))
        cal_world.append((srv_x, srv_z))

        x_min, z_min, x_max, z_max = p_info["world_roi_m"]
        a_pl = wire.pack_payload(
            scalars_str={"point_id": cid, "feature_kind": p_info["feature_kind"], "mode_id": "calibrate"},
            scalars_num={"x_min_m": x_min, "z_min_m": z_min, "x_max_m": x_max, "z_max_m": z_max},
        )
        r_pl = wire.pack_payload(
            scalars_str={"point_id": cid, "mode_id": "calibrate", "decision_id": "located", "reject_reason_id": ""},
            scalars_num={
                "req_x_m": 0.0,
                "req_z_m": 0.0,
                "srv_feature_found_b": 1.0,
                "srv_x_m": srv_x,
                "srv_y_m": srv_y,
                "srv_z_m": srv_z,
                "prominence_m": prom,
                "err_xz_m": 0.0,
                "err_reflected_z_m": 0.0,
                "tick_ms": clock_ms[0],
                "frame": float(frame_no[0]),
            },
            num_cols=["sx_m", "sz_m", "y_m", "sea_b"],
            row_dicts=_audit_rows_for_patch(cid, w_det, common_srv_bias_x_m),
        )
        cal_op_ids.append(_emit_op("map_feature_locate", a_pl, r_pl))

    fit = s_mapa_eval.solve_affine_2d(cal_px, cal_world)
    assert fit is not None
    a_ok, b_ok = fit
    a_inv, b_inv = s_mapa_eval.invert_vertical_affine(a_ok, b_ok, 4096.0)

    # Paso 3: verify_and_place_V1_V3
    step3_op_ids: list[str] = []
    spawn_seq = [0]

    for vid in s_mapa_eval.VER_IDS:
        p_info = all_pts_by_id[vid]
        p_idx = s_mapa_eval.PATCH_IDS.index(vid)
        p256 = [patch_samples[(p_idx, r, c)] for r in range(16) for c in range(16)]
        w_det = s_mapa_eval.locate_world_feature_from_patch(
            p256, p_info["world_roi_m"], p_info["feature_kind"], 0.0
        )
        if w_det is None:
            w_det = {
                "srv_x_m": float(p_info["certified_x_m"]),
                "srv_y_m": float(p_info["certified_y_m"]),
                "srv_z_m": float(p_info["certified_z_m"]),
                "prominence_m": 10.0,
                "y_border_m": 0.0,
                "audit_pair": (
                    (float(p_info["certified_x_m"]), float(p_info["certified_z_m"]), 4.0, 0.0),
                    (float(p_info["certified_x_m"]), float(p_info["certified_z_m"]), 0.0, 1.0),
                ),
            }
        srv_x = float(w_det["srv_x_m"]) + common_srv_bias_x_m
        srv_y = float(w_det["srv_y_m"])
        srv_z = float(w_det["srv_z_m"])
        prom = float(w_det["prominence_m"])

        u_v, v_v = float(p_info["certified_u_px"]), float(p_info["certified_v_px"])
        if mutant == "flip_v_matrix":
            req_x, req_z = s_mapa_eval.apply_affine_2d(a_inv, b_inv, u_v, v_v)
        else:
            req_x, req_z = s_mapa_eval.apply_affine_2d(a_ok, b_ok, u_v, v_v)
            if mutant == "verify_drift_25m":
                req_x += 25.0

        err_xz = math.hypot(req_x - srv_x, req_z - srv_z)
        err_refl_z = abs((15360.0 - req_z) - srv_z)
        if err_xz >= 10.0 and err_refl_z < 50.0 and abs(req_x - srv_x) < 50.0:
            dec_id, rej_id = "rejected", "inverted_axis"
        elif err_xz >= 10.0:
            dec_id, rej_id = "rejected", "verification_error_exceeded"
        else:
            dec_id, rej_id = "verified", ""

        x_min, z_min, x_max, z_max = p_info["world_roi_m"]
        a_loc = wire.pack_payload(
            scalars_str={"point_id": vid, "feature_kind": p_info["feature_kind"], "mode_id": "verify"},
            scalars_num={
                "req_x_m": req_x,
                "req_z_m": req_z,
                "x_min_m": x_min,
                "z_min_m": z_min,
                "x_max_m": x_max,
                "z_max_m": z_max,
            },
        )
        r_loc = wire.pack_payload(
            scalars_str={"point_id": vid, "mode_id": "verify", "decision_id": dec_id, "reject_reason_id": rej_id},
            scalars_num={
                "req_x_m": req_x,
                "req_z_m": req_z,
                "srv_feature_found_b": 1.0,
                "srv_x_m": srv_x,
                "srv_y_m": srv_y,
                "srv_z_m": srv_z,
                "prominence_m": prom,
                "err_xz_m": err_xz,
                "err_reflected_z_m": err_refl_z,
                "tick_ms": clock_ms[0],
                "frame": float(frame_no[0]),
            },
            num_cols=["sx_m", "sz_m", "y_m", "sea_b"],
            row_dicts=_audit_rows_for_patch(vid, w_det, common_srv_bias_x_m),
        )
        step3_op_ids.append(_emit_op("map_feature_locate", a_loc, r_loc))

        # Colocacion en V1..V3
        seq_pre = spawn_seq[0]
        spawn_seq[0] += 1
        seq_post = spawn_seq[0]
        surf_y = srv_y
        bbox_min_y = -0.5625
        bbox_max_y = 0.5625
        # Posicion observada independiente de la pedida (no es un simple eco):
        # el motor coloca con un residuo deterministico dentro de la tolerancia.
        obs_x = req_x + 0.0125
        obs_z = req_z - 0.0125
        obs_y = surf_y - bbox_min_y + contact_offset_y_m
        a_pl = wire.pack_payload(
            scalars_str={"point_id": vid, "class_id": "Barrel_Green"},
            scalars_num={"req_x_m": req_x, "req_z_m": req_z},
        )
        r_pl = wire.pack_payload(
            scalars_str={
                "point_id": vid,
                "decision_id": "placed",
                "reject_reason_id": "",
                "hit_class_id": "",
                "obs_class_id": "Barrel_Green",
            },
            scalars_num={
                "req_x_m": req_x,
                "req_z_m": req_z,
                "terrain_y_m": surf_y,
                "road_y_m": surf_y,
                "ray_hit_b": 0.0,
                "hit_y_m": 0.0,
                "seq_pre_n": float(seq_pre),
                "seq_post_n": float(seq_post),
                "ent_id_n": float(ent_id_for_valid_spawns),
                "obs_x_m": obs_x,
                "obs_y_m": obs_y,
                "obs_z_m": obs_z,
                "bbox_min_y_m": bbox_min_y,
                "bbox_max_y_m": bbox_max_y,
                "obs_surf_y_m": surf_y,
                "pre_count_n": 0.0,
                "post_count_n": 0.0,
                "tick_ms": clock_ms[0],
                "frame": float(frame_no[0]),
            },
        )
        step3_op_ids.append(_emit_op("map_place_ground", a_pl, r_pl))

    # Paso 4: place_ground_P_GROUND
    pg_info = next(p for p in fx["placement_points"] if p["point_id"] == "P_GROUND")
    pg_x, pg_z = float(pg_info["req_x_m"]), float(pg_info["req_z_m"])
    seq_pre = spawn_seq[0]
    spawn_seq[0] += 1
    seq_post = spawn_seq[0]
    pg_surf_y = 12.5
    pg_bbox_min_y = -0.5625
    pg_bbox_max_y = 0.5625
    pg_obs_x = pg_x + 0.0125
    pg_obs_z = pg_z - 0.0125
    pg_obs_y = pg_surf_y - pg_bbox_min_y + contact_offset_y_m
    step4_op_id = _emit_op(
        "map_place_ground",
        wire.pack_payload(
            scalars_str={"point_id": "P_GROUND", "class_id": "Barrel_Green"},
            scalars_num={"req_x_m": pg_x, "req_z_m": pg_z},
        ),
        wire.pack_payload(
            scalars_str={
                "point_id": "P_GROUND",
                "decision_id": "placed",
                "reject_reason_id": "",
                "hit_class_id": "",
                "obs_class_id": "Barrel_Green",
            },
            scalars_num={
                "req_x_m": pg_x,
                "req_z_m": pg_z,
                "terrain_y_m": pg_surf_y,
                "road_y_m": pg_surf_y,
                "ray_hit_b": 0.0,
                "hit_y_m": 0.0,
                "seq_pre_n": float(seq_pre),
                "seq_post_n": float(seq_post),
                "ent_id_n": float(ent_id_for_valid_spawns),
                "obs_x_m": pg_x,
                "obs_y_m": pg_obs_y,
                "obs_z_m": pg_z,
                "bbox_min_y_m": pg_bbox_min_y,
                "bbox_max_y_m": pg_bbox_max_y,
                "obs_surf_y_m": pg_surf_y,
                "pre_count_n": 0.0,
                "post_count_n": 0.0,
                "tick_ms": clock_ms[0],
                "frame": float(frame_no[0]),
            },
        ),
    )

    # Paso 5: neg_inverted_axis
    step5_op_ids: list[str] = []
    for vid in s_mapa_eval.VER_IDS:
        p_info = all_pts_by_id[vid]
        p_idx = s_mapa_eval.PATCH_IDS.index(vid)
        p256 = [patch_samples[(p_idx, r, c)] for r in range(16) for c in range(16)]
        w_det = s_mapa_eval.locate_world_feature_from_patch(
            p256, p_info["world_roi_m"], p_info["feature_kind"], 0.0
        )
        if w_det is None:
            w_det = {
                "srv_x_m": float(p_info["certified_x_m"]),
                "srv_y_m": float(p_info["certified_y_m"]),
                "srv_z_m": float(p_info["certified_z_m"]),
                "prominence_m": 10.0,
                "y_border_m": 0.0,
                "audit_pair": (
                    (float(p_info["certified_x_m"]), float(p_info["certified_z_m"]), 4.0, 0.0),
                    (float(p_info["certified_x_m"]), float(p_info["certified_z_m"]), 0.0, 1.0),
                ),
            }
        srv_x = float(w_det["srv_x_m"]) + common_srv_bias_x_m
        srv_y = float(w_det["srv_y_m"])
        srv_z = float(w_det["srv_z_m"])
        prom = float(w_det["prominence_m"])
        u_v, v_v = float(p_info["certified_u_px"]), float(p_info["certified_v_px"])
        req_x, req_z = s_mapa_eval.apply_affine_2d(a_inv, b_inv, u_v, v_v)
        err_xz = math.hypot(req_x - srv_x, req_z - srv_z)
        err_refl_z = abs((15360.0 - req_z) - srv_z)
        x_min, z_min, x_max, z_max = p_info["world_roi_m"]
        step5_op_ids.append(
            _emit_op(
                "map_feature_locate",
                wire.pack_payload(
                    scalars_str={"point_id": vid, "feature_kind": p_info["feature_kind"], "mode_id": "verify"},
                    scalars_num={
                        "req_x_m": req_x,
                        "req_z_m": req_z,
                        "x_min_m": x_min,
                        "z_min_m": z_min,
                        "x_max_m": x_max,
                        "z_max_m": z_max,
                    },
                ),
                wire.pack_payload(
                    scalars_str={
                        "point_id": vid,
                        "mode_id": "verify",
                        "decision_id": "rejected",
                        "reject_reason_id": "inverted_axis",
                    },
                    scalars_num={
                        "req_x_m": req_x,
                        "req_z_m": req_z,
                        "srv_feature_found_b": 1.0,
                        "srv_x_m": srv_x,
                        "srv_y_m": srv_y,
                        "srv_z_m": srv_z,
                        "prominence_m": prom,
                        "err_xz_m": err_xz,
                        "err_reflected_z_m": err_refl_z,
                        "tick_ms": clock_ms[0],
                        "frame": float(frame_no[0]),
                    },
                    num_cols=["sx_m", "sz_m", "y_m", "sea_b"],
                    row_dicts=_audit_rows_for_patch(vid, w_det, common_srv_bias_x_m),
                ),
            )
        )

    # Paso 6: neg_out_of_map, neg_bridge, neg_roof
    seq_pre_out = spawn_seq[0]
    if spawn_then_reject_all_negatives:
        spawn_seq[0] += 1
    seq_post_out = spawn_seq[0]
    pout_op_id = _emit_op(
        "map_place_ground",
        wire.pack_payload(
            scalars_str={"point_id": "P_OUT", "class_id": "Barrel_Green"},
            scalars_num={"req_x_m": -240.0, "req_z_m": -390.0},
        ),
        wire.pack_payload(
            scalars_str={
                "point_id": "P_OUT",
                "decision_id": "rejected",
                "reject_reason_id": "out_of_map",
                "hit_class_id": "",
                "obs_class_id": "Barrel_Green" if spawn_then_reject_all_negatives else "",
            },
            scalars_num={
                "req_x_m": -240.0,
                "req_z_m": -390.0,
                "terrain_y_m": 0.0,
                "road_y_m": 0.0,
                "ray_hit_b": 0.0,
                "hit_y_m": 0.0,
                "seq_pre_n": float(seq_pre_out),
                "seq_post_n": float(seq_post_out),
                "ent_id_n": 0.0,
                "obs_x_m": 0.0,
                "obs_y_m": 0.0,
                "obs_z_m": 0.0,
                "bbox_min_y_m": 0.0,
                "bbox_max_y_m": 0.0,
                "obs_surf_y_m": 0.0,
                "pre_count_n": 0.0,
                "post_count_n": 0.0,
                "tick_ms": clock_ms[0],
                "frame": float(frame_no[0]),
            },
        ),
    )

    seq_pre_br = spawn_seq[0]
    if mutant == "elevated_not_rejected" or spawn_then_reject_all_negatives:
        spawn_seq[0] += 1
    seq_post_br = spawn_seq[0]
    br_dec = "placed" if mutant == "elevated_not_rejected" else "rejected"
    br_rej = "" if mutant == "elevated_not_rejected" else "elevated_surface"
    br_obs_cls = "Barrel_Green" if (mutant == "elevated_not_rejected" or spawn_then_reject_all_negatives) else ""
    pbridge_op_id = _emit_op(
        "map_place_ground",
        wire.pack_payload(
            scalars_str={"point_id": "P_BRIDGE", "class_id": "Barrel_Green"},
            scalars_num={"req_x_m": 13210.0, "req_z_m": 4200.0},
        ),
        wire.pack_payload(
            scalars_str={
                "point_id": "P_BRIDGE",
                "decision_id": br_dec,
                "reject_reason_id": br_rej,
                "hit_class_id": "Land_Bridge_Concrete_25",
                "obs_class_id": br_obs_cls,
            },
            scalars_num={
                "req_x_m": 13210.0,
                "req_z_m": 4200.0,
                "terrain_y_m": 1.25,
                "road_y_m": 6.75,
                "ray_hit_b": 1.0,
                "hit_y_m": 6.75,
                "seq_pre_n": float(seq_pre_br),
                "seq_post_n": float(seq_post_br),
                "ent_id_n": 0.0,
                "obs_x_m": 13210.0 if br_obs_cls else 0.0,
                "obs_y_m": 1.8125 if br_obs_cls else 0.0,
                "obs_z_m": 4200.0 if br_obs_cls else 0.0,
                "bbox_min_y_m": -0.5625 if br_obs_cls else 0.0,
                "bbox_max_y_m": 0.5625 if br_obs_cls else 0.0,
                "obs_surf_y_m": 1.25 if br_obs_cls else 0.0,
                "pre_count_n": 0.0,
                "post_count_n": 0.0,
                "tick_ms": clock_ms[0],
                "frame": float(frame_no[0]),
            },
        ),
    )

    seq_pre_rf = spawn_seq[0]
    if mutant == "elevated_not_rejected" or spawn_then_reject_all_negatives:
        spawn_seq[0] += 1
    seq_post_rf = spawn_seq[0]
    rf_obs_cls = "Barrel_Green" if (mutant == "elevated_not_rejected" or spawn_then_reject_all_negatives) else ""
    proof_op_id = _emit_op(
        "map_place_ground",
        wire.pack_payload(
            scalars_str={"point_id": "P_ROOF", "class_id": "Barrel_Green"},
            scalars_num={"req_x_m": 6680.0, "req_z_m": 2628.0},
        ),
        wire.pack_payload(
            scalars_str={
                "point_id": "P_ROOF",
                "decision_id": "rejected",
                "reject_reason_id": "elevated_surface",
                "hit_class_id": "Land_House_2W01",
                "obs_class_id": rf_obs_cls,
            },
            scalars_num={
                "req_x_m": 6680.0,
                "req_z_m": 2628.0,
                "terrain_y_m": 6.5,
                "road_y_m": 6.5,
                "ray_hit_b": 1.0,
                "hit_y_m": 15.25,
                "seq_pre_n": float(seq_pre_rf),
                "seq_post_n": float(seq_post_rf),
                "ent_id_n": 0.0,
                "obs_x_m": 6680.0 if rf_obs_cls else 0.0,
                "obs_y_m": 7.0625 if rf_obs_cls else 0.0,
                "obs_z_m": 2628.0 if rf_obs_cls else 0.0,
                "bbox_min_y_m": -0.5625 if rf_obs_cls else 0.0,
                "bbox_max_y_m": 0.5625 if rf_obs_cls else 0.0,
                "obs_surf_y_m": 6.5 if rf_obs_cls else 0.0,
                "pre_count_n": 0.0,
                "post_count_n": 0.0,
                "tick_ms": clock_ms[0],
                "frame": float(frame_no[0]),
            },
        ),
    )

    scenario_rows = [
        {
            "step": "world_and_relief_read",
            "op_ids": grid_op_ids + patch_op_ids,
            "t_start_h_ms": 1.0,
            "t_end_h_ms": 320.0,
            "elapsed_h_ms": 319.0,
        },
        {
            "step": "calibrate_C1_C3",
            "op_ids": cal_op_ids,
            "t_start_h_ms": 321.0,
            "t_end_h_ms": 325.0,
            "elapsed_h_ms": 4.0,
            "calibration_fit": {"A": a_ok, "b": b_ok},
        },
        {
            "step": "verify_and_place_V1_V3",
            "op_ids": step3_op_ids,
            "t_start_h_ms": 326.0,
            "t_end_h_ms": 334.0,
            "elapsed_h_ms": 8.0,
        },
        {
            "step": "place_ground_P_GROUND",
            "op_ids": [step4_op_id],
            "t_start_h_ms": 335.0,
            "t_end_h_ms": 337.0,
            "elapsed_h_ms": 2.0,
        },
        {
            "step": "neg_inverted_axis",
            "op_ids": step5_op_ids,
            "t_start_h_ms": 338.0,
            "t_end_h_ms": 342.0,
            "elapsed_h_ms": 4.0,
        },
        {
            "step": "neg_out_of_map",
            "op_ids": [pout_op_id],
            "t_start_h_ms": 343.0,
            "t_end_h_ms": 345.0,
            "elapsed_h_ms": 2.0,
        },
        {
            "step": "neg_bridge",
            "op_ids": [pbridge_op_id],
            "t_start_h_ms": 346.0,
            "t_end_h_ms": 348.0,
            "elapsed_h_ms": 2.0,
        },
        {
            "step": "neg_roof",
            "op_ids": [proof_op_id],
            "t_start_h_ms": 349.0,
            "t_end_h_ms": 351.0,
            "elapsed_h_ms": 2.0,
        },
    ]

    _write_jsonl(samples / "bridge.jsonl", bridge_rows)
    _write_jsonl(samples / "scenario.jsonl", scenario_rows)
    gate_core.write_json(
        pdir / "part.json",
        {"op_map": [], "op_nonce": nonce, "part": pdir.name, "spike_id": "S-mapa"},
    )
    manifest = {
        "argv": ["qa/m1_gate.py", "spike", "S-mapa"],
        "both": True,
        "build": build,
        "ended_utc": "2026-11-15T06:00:10Z",
        "execution_identity": {
            "fake_peer_pids": {"client": exec_pids[1], "server": exec_pids[0]},
            "key_sha256": {"client": "1111222233334444", "server": "aaaabbbbccccdddd"},
            "peer_insts": {"client": ["cli-map-1"], "server": ["srv-map-1"]},
            "port": exec_port,
        },
        "faults": [],
        "harness": {"git_dirty": git_dirty, "git_head": git_head, "platform": "win32", "python": "3.14"},
        "id": "S-mapa",
        "identity": {
            "build": build,
            "git_dirty": git_dirty,
            "git_head": git_head,
            "params": {
                "hold_ms": 2000,
                "lease_ms": 3000,
                "retry_ms": 2000,
                "seed": 20261026,
                "ttl_ms": 5000,
                "wire_cap": wire_cap,
            },
            "pbo_sha256": None,
            "peer_builds": {"client": build, "server": build},
            "probe_stamp": probe_stamp,
        },
        "kind": "spike",
        "params": {
            "hold_ms": 2000,
            "lease_ms": 3000,
            "port": exec_port,
            "retry_ms": 2000,
            "run_id": "abcd1234",
            "seed": 20261026,
            "ttl_ms": 5000,
        },
        "schema": gate_core.SCHEMA_MANIFEST,
        "started_utc": "2026-11-15T06:00:00Z",
    }
    gate_core.write_json(pdir / "manifest.json", manifest)
    return manifest


def _git_run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def _init_temp_git_repo(root: Path, *, wire_cap: int = 3500) -> str:
    """Inicializa un repo git temporal con las fuentes reales de la sonda y wire.py."""
    _git_run(root, "init")
    _git_run(root, "config", "user.email", "qa@example.local")
    _git_run(root, "config", "user.name", "QA")
    dst_probe = root / "DayZSandbox_dev" / "qa" / "probe" / "DayZSandbox_QA"
    shutil.copytree(wire.REAL_PROBE_DIR, dst_probe)
    dst_wire = root / "DayZSandbox_dev" / "qa" / "wire.py"
    dst_wire.parent.mkdir(parents=True, exist_ok=True)
    w_txt = (QA_DIR / "wire.py").read_text(encoding="utf-8")
    w_txt = w_txt.replace("WIRE_CAP = 3500", f"WIRE_CAP = {wire_cap}")
    dst_wire.write_bytes(w_txt.encode("utf-8"))
    _git_run(root, "add", ".")
    _git_run(root, "commit", "-m", "initial")
    return _git_run(root, "rev-parse", "HEAD").stdout.strip()


class SMapaOracleOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.real_git_head = gate_core.git_harness(repo_root=REPO_ROOT)["git_head"]
        cls.real_probe_stamp = f03_common.compute_probe_stamp_at_commit(cls.real_git_head, repo_root=REPO_ROOT)

    def test_fixture_geometry_and_accreditation_invariants(self) -> None:
        """Verifica las invariantes geometricas (§4.4, N11) y acreditacion de qa/fixtures/s_mapa_puntos.json."""
        self.assertTrue(FIXTURE_PATH.is_file(), "qa/fixtures/s_mapa_puntos.json no existe")
        fx = gate_core.read_json(FIXTURE_PATH)
        self.assertEqual(fx.get("schema"), "dsbx.map.fixture.v4")
        self.assertEqual(fx.get("world_name"), "chernarusplus")
        self.assertEqual(fx.get("world_size_m"), 15360.0)
        self.assertEqual(fx.get("width_px"), 4096)
        self.assertEqual(fx.get("height_px"), 4096)
        self.assertEqual(fx.get("step_px_m"), 3.75)

        cal = fx["calibration_points"]
        ver = fx["verification_points"]
        self.assertEqual([p["point_id"] for p in cal], ["C1", "C2", "C3"])
        self.assertEqual([p["point_id"] for p in ver], ["V1", "V2", "V3"])

        all_6 = cal + ver
        for p in all_6:
            u0, v0, u1, v1 = p["roi_px"]
            self.assertEqual(u1 - u0, 15, p["point_id"])
            self.assertEqual(v1 - v0, 15, p["point_id"])
            x0, z0, x1, z1 = p["world_roi_m"]
            self.assertAlmostEqual(x0, 3.75 * u0, places=5)
            self.assertAlmostEqual(x1, 3.75 * u1, places=5)
            self.assertAlmostEqual(z0, 15360.0 - 3.75 * v1, places=5)
            self.assertAlmostEqual(z1, 15360.0 - 3.75 * v0, places=5)

        # Condicionamiento amplio en C1..C3 y V1..V3 (>= 1e-3 * W * H)
        min_det = 1e-3 * 4096.0 * 4096.0
        det_c = abs(
            s_mapa_eval.det_2d(
                (cal[0]["certified_u_px"], cal[0]["certified_v_px"]),
                (cal[1]["certified_u_px"], cal[1]["certified_v_px"]),
                (cal[2]["certified_u_px"], cal[2]["certified_v_px"]),
            )
        )
        det_v = abs(
            s_mapa_eval.det_2d(
                (ver[0]["certified_u_px"], ver[0]["certified_v_px"]),
                (ver[1]["certified_u_px"], ver[1]["certified_v_px"]),
                (ver[2]["certified_u_px"], ver[2]["certified_v_px"]),
            )
        )
        self.assertGreaterEqual(det_c, min_det)
        self.assertGreaterEqual(det_v, min_det)

        # Separacion mutua >= 500 m y |z_j - S/2| >= 1500 m para todo V_j
        for i in range(len(all_6)):
            for j in range(i + 1, len(all_6)):
                dist = math.hypot(
                    all_6[i]["certified_x_m"] - all_6[j]["certified_x_m"],
                    all_6[i]["certified_z_m"] - all_6[j]["certified_z_m"],
                )
                self.assertGreaterEqual(dist, 500.0)
        for vp in ver:
            self.assertGreaterEqual(abs(vp["certified_z_m"] - 7680.0), 1500.0)

        # Comprobar que los hashes estaticos en qa/fixtures/s_mapa_puntos.json coinciden con el calculo real
        cert_git_head = fx["certifying_capture"]["certifying_git_head"]
        fixture_probe_stamp = f03_common.compute_probe_stamp_at_commit(cert_git_head, repo_root=REPO_ROOT)
        expected_fx = _compute_stamped_fixture(
            fx,
            cert_git_head=cert_git_head,
            cert_probe_stamp=fixture_probe_stamp,
        )
        expected_luma_shas = {
            pid: expected_fx["certifying_capture"]["patches"][pid]["patch_luma_sha256"]
            for pid in s_mapa_eval.PATCH_IDS
        }
        actual_luma_shas = {
            pid: fx["certifying_capture"]["patches"][pid]["patch_luma_sha256"]
            for pid in s_mapa_eval.PATCH_IDS
        }
        self.assertEqual(
            actual_luma_shas,
            expected_luma_shas,
            f"Actualizar patch_luma_sha256 en s_mapa_puntos.json a: {json.dumps(expected_luma_shas)} "
            f"y probe_stamp={fixture_probe_stamp} y certifying_capture_sha256={expected_fx['accreditation']['certifying_capture_sha256']}",
        )
        self.assertEqual(
            fx["accreditation"]["certifying_probe_stamp"],
            fixture_probe_stamp,
            f"probe_stamp esperado={fixture_probe_stamp}",
        )
        self.assertEqual(
            fx["accreditation"]["certifying_capture_sha256"],
            expected_fx["accreditation"]["certifying_capture_sha256"],
            f"certifying_capture_sha256 esperado={expected_fx['accreditation']['certifying_capture_sha256']}",
        )

    def test_run_and_all_four_mutants_and_aggregation(self) -> None:
        """Verifica run/ (con ent_id_n == 0 en colocaciones validas, N23), los 4 mutantes y aggregate_spike.

        Es sintetico a proposito: prueba evaluador y agregacion sin la
        implementacion. Los ``test_e2e_*`` son los que ejercitan el runner real.
        """
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "ev_s_mapa"
            _build_synthetic_part(
                base / "run",
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                ent_id_for_valid_spawns=0,
                exec_port=53100,
                exec_pids=(4101, 4102),
            )
            v_run = s_mapa_eval.evaluate(base / "run", repo_root=REPO_ROOT)
            self.assertEqual(v_run["exit_code"], 0, v_run)
            self.assertTrue(all(c["status"] == "pass" for c in v_run["checks"]))
            gate_core.write_json(base / "run" / "verdict.json", v_run)

            for idx, (m_name, spec) in enumerate(s_mapa_mutants.EXPECTED_MUTANTS.items(), start=1):
                mdir = base / f"mut-{m_name}"
                _build_synthetic_part(
                    mdir,
                    git_head=self.real_git_head,
                    probe_stamp=self.real_probe_stamp,
                    mutant=m_name,
                    nonce=f"{idx:016x}",
                    exec_port=53100 + idx,
                    exec_pids=(4100 + idx * 2, 4101 + idx * 2),
                )
                gate_core.write_json(
                    mdir / "injection.json",
                    {
                        "applied": True,
                        "kind": "qa_fault" if m_name == "elevated_not_rejected" else "scenario",
                        "mutant": m_name,
                        "observable_effect": {"mutant": m_name},
                        "target": "S-mapa",
                        "when_h_ms": 10.0,
                    },
                )
                v_mut = s_mapa_eval.evaluate(mdir, repo_root=REPO_ROOT)
                self.assertEqual(v_mut["exit_code"], 1, f"{m_name}: {v_mut}")
                by_id = {c["id"]: c["status"] for c in v_mut["checks"]}
                for must_c in spec["must_fail_checks"]:
                    self.assertEqual(by_id[must_c], "fail", f"{m_name} debia fallar {must_c}: {by_id}")
                gate_core.write_json(mdir / "verdict.json", v_mut)

            agg = f03_common.aggregate_spike(base, "S-mapa", repo_root=REPO_ROOT)
            self.assertEqual(agg["exit_code"], 0, agg)

    def test_antifabrication_negatives_never_pass(self) -> None:
        """Verifica todos los casos negativos de §3 ENCARGO.md, §9(1) y E9."""
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)

            # 1) Posiciones "leidas" que copian la fixture sin lectura del motor (o con sesgo / parche discordante)
            p_copy = tpath / "neg_copied_positions"
            _build_synthetic_part(p_copy, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            br_rows = f03_common.read_jsonl(p_copy / "samples" / "bridge.jsonl")
            # Eliminar las lecturas map_world_read o hacer que el parche tenga otro centro mientras srv_x_m copia la fixture
            for r in br_rows:
                if r.get("ev") == "result" and isinstance(r.get("result"), dict):
                    u_rd = wire.unpack_payload(r["result"]["read"])
                    if u_rd["str"].get("mode_id") == "patch_row" and abs(float(u_rd["num"].get("row_n", -1)) - 24.0) < 1e-3:
                        # Desplazar el pico de C2 en las muestras crudas mientras srv_x_m sigue copiando certified_x_m (13920.0)
                        r["result"]["read"]["ncell"][0] = 100.0
                        r["result"]["read"]["ncell"][4] = 125.0
            _write_jsonl(p_copy / "samples" / "bridge.jsonl", br_rows)
            v_copy = s_mapa_eval.evaluate(p_copy, repo_root=REPO_ROOT)
            self.assertNotEqual(v_copy["exit_code"], 0)
            self.assertEqual(v_copy["exit_code"], 1)
            self.assertEqual(next(c for c in v_copy["checks"] if c["id"] == "MAP-02")["status"], "fail")

            # 2) Alturas de terreno constantes -> 2 INCONCLUSO (degenerate_relief_range)
            p_const = tpath / "neg_constant_heights"
            _build_synthetic_part(
                p_const,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                constant_terrain_y=42.0,
            )
            v_const = s_mapa_eval.evaluate(p_const, repo_root=REPO_ROOT)
            self.assertEqual(v_const["exit_code"], 2)
            self.assertEqual(v_const["reasons"], ["degenerate_relief_range"])

            # 3) Sello o hash esperado en lugar del observado (probe_ver / image_sha256 falsos)
            p_bad_stamp = tpath / "neg_bad_stamp"
            _build_synthetic_part(p_bad_stamp, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            br_s = f03_common.read_jsonl(p_bad_stamp / "samples" / "bridge.jsonl")
            br_s[0]["args"]["probe_ver"] = "dsbx-qa1+deadbeefcafebabe"
            _write_jsonl(p_bad_stamp / "samples" / "bridge.jsonl", br_s)
            v_bad_stamp = s_mapa_eval.evaluate(p_bad_stamp, repo_root=REPO_ROOT)
            self.assertEqual(v_bad_stamp["exit_code"], 2)
            self.assertEqual(v_bad_stamp["reasons"], ["artifact_unverified"])

            p_bad_img_sha = tpath / "neg_bad_img_sha"
            _build_synthetic_part(p_bad_img_sha, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            prov = gate_core.read_json(p_bad_img_sha / "samples" / "map_provenance.json")
            prov["image_sha256"] = "ff" * 32
            gate_core.write_json(p_bad_img_sha / "samples" / "map_provenance.json", prov)
            v_bad_img = s_mapa_eval.evaluate(p_bad_img_sha, repo_root=REPO_ROOT)
            self.assertEqual(v_bad_img["exit_code"], 1)
            self.assertEqual(next(c for c in v_bad_img["checks"] if c["id"] == "MAP-01")["status"], "fail")

            # 4) Rechazo declarado sin la orden ni su respuesta, o fila que solo trae etiqueta (point_ok / decision_id sin lecturas crudas, E9)
            p_no_resp = tpath / "neg_declared_reject_without_order"
            _build_synthetic_part(p_no_resp, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            scen_nr = f03_common.read_jsonl(p_no_resp / "samples" / "scenario.jsonl")
            roof_oid = scen_nr[-1]["op_ids"][0]
            br_nr = [r for r in f03_common.read_jsonl(p_no_resp / "samples" / "bridge.jsonl") if r.get("op_id") != roof_oid]
            _write_jsonl(p_no_resp / "samples" / "bridge.jsonl", br_nr)
            v_no_resp = s_mapa_eval.evaluate(p_no_resp, repo_root=REPO_ROOT)
            self.assertEqual(v_no_resp["exit_code"], 2)

            p_label_only = tpath / "neg_label_only_without_raw_readings"
            _build_synthetic_part(p_label_only, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            br_lbl = f03_common.read_jsonl(p_label_only / "samples" / "bridge.jsonl")
            for r in br_lbl:
                if r.get("ev") == "result" and r.get("op_id") == roof_oid:
                    r["result"]["read"] = dict(
                        r["result"]["read"],
                        sk=["point_id", "decision_id", "reject_reason_id"],
                        sv=["P_ROOF", "rejected", "elevated_surface"],
                        nk=["point_ok", "on_ground"],
                        nv=[1.0, 0.0],
                    )
            _write_jsonl(p_label_only / "samples" / "bridge.jsonl", br_lbl)
            v_lbl = s_mapa_eval.evaluate(p_label_only, repo_root=REPO_ROOT)
            self.assertEqual(v_lbl["exit_code"], 2)

            # 5) Puntos colineales (C1, C2, C3 colineales en mundo -> MAP-02 falla)
            p_col = tpath / "neg_collinear"
            _build_synthetic_part(p_col, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            br_col = f03_common.read_jsonl(p_col / "samples" / "bridge.jsonl")
            # Forzar que solve_affine_2d reciba puntos colineales o verificar solve_affine_2d directamente
            self.assertIsNone(
                s_mapa_eval.solve_affine_2d(
                    [(100.0, 100.0), (200.0, 200.0), (300.0, 300.0)],
                    [(375.0, 14985.0), (750.0, 14610.0), (1125.0, 14235.0)],
                )
            )
            # En evidencia: alterar C3 srv_x_m/srv_z_m y su parche para que C1, C2, C3 sean colineales
            for r in br_col:
                if r.get("ev") == "result" and isinstance(r.get("result"), dict):
                    u_rd = wire.unpack_payload(r["result"]["read"])
                    if u_rd["str"].get("point_id") == "C3" and u_rd["str"].get("mode_id") == "calibrate":
                        # Poner srv_x_m, srv_z_m en el punto medio exacto de C1 y C2
                        c1_x, c1_z = 1860.0, 2236.875
                        c2_x, c2_z = 13920.0, 13680.0
                        mid_x, mid_z = 0.5 * (c1_x + c2_x), 0.5 * (c1_z + c2_z)
                        nk_list = r["result"]["read"]["nk"]
                        nv_list = r["result"]["read"]["nv"]
                        nv_list[nk_list.index("srv_x_m")] = mid_x
                        nv_list[nk_list.index("srv_z_m")] = mid_z
            _write_jsonl(p_col / "samples" / "bridge.jsonl", br_col)
            v_col = s_mapa_eval.evaluate(p_col, repo_root=REPO_ROOT)
            self.assertEqual(v_col["exit_code"], 1)
            self.assertEqual(next(c for c in v_col["checks"] if c["id"] == "MAP-02")["status"], "fail")

    def test_brief_specific_negatives_n15_n16_n19_n22_n24_n25_n29_n30_n31(self) -> None:
        """Verifica los casos negativos especificos de N15, N16, N19, N22, N24, N25, N29, N30 y N31."""
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp)

            # N16: Fondo del PNG alterado con tile_urls == [] -> MAP-01 falla por full_raster_mismatch_px > 0
            p_n16 = tpath / "neg_n16_bg_tampered"
            _build_synthetic_part(
                p_n16,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                tamper_bg_without_tile_url=True,
            )
            v_n16 = s_mapa_eval.evaluate(p_n16, repo_root=REPO_ROOT)
            self.assertEqual(v_n16["exit_code"], 1)
            c_m1 = next(c for c in v_n16["checks"] if c["id"] == "MAP-01")
            self.assertEqual(c_m1["status"], "fail")
            self.assertIn("full_raster_mismatch_px", c_m1["detail"])

            # N15: Sesgo comun +100 m en srv_x_m -> MAP-02 falla contra certified_x_m
            p_n15 = tpath / "neg_n15_common_bias"
            _build_synthetic_part(
                p_n15,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                common_srv_bias_x_m=100.0,
            )
            v_n15 = s_mapa_eval.evaluate(p_n15, repo_root=REPO_ROOT)
            self.assertEqual(v_n15["exit_code"], 1)
            self.assertEqual(next(c for c in v_n15["checks"] if c["id"] == "MAP-02")["status"], "fail")

            # N24: Parche de cima con 9 muestras en [y_max - 0.5, y_max] cuyo centroide de 9 muestras difiere > 10 m
            # de la muestra maxima; si srv_x_m/srv_z_m solo promedia las 2 filas de map_feature_locate, el evaluador lo rechaza.
            patch_9 = [[100.0, 0.0] for _ in range(256)]
            # 1 muestra en (1, 1) con 120.0 y 8 muestras en bloque (12..14, 12..14) con 119.6 (dentro de [119.5, 120.0])
            patch_9[1 * 16 + 1] = [120.0, 0.0]
            high_cluster = [(12, 12), (12, 13), (12, 14), (13, 12), (13, 13), (13, 14), (14, 12), (14, 13)]
            for r_c, c_c in high_cluster:
                patch_9[r_c * 16 + c_c] = [119.6, 0.0]
            roi_m = [13890.0, 13653.75, 13946.25, 13710.0]
            det_9 = s_mapa_eval.locate_world_feature_from_patch(patch_9, roi_m, "relief_peak", 0.0)
            self.assertIsNotNone(det_9)
            self.assertEqual(len(det_9["m_srv"]), 9)
            peak_1_x = 13890.0 + 3.75 * 1.0
            peak_1_z = 13710.0 - 3.75 * 1.0
            # Distancia entre el centroide de las 9 muestras y la muestra maxima (o el promedio de las 2 filas) > 10 m
            self.assertGreater(math.hypot(det_9["srv_x_m"] - peak_1_x, det_9["srv_z_m"] - peak_1_z), 10.0)

            # N30: Muestras a los dos lados de y_max - 0.5 sobre float sin cuantizar
            patch_n30 = [[100.0, 0.0] for _ in range(256)]
            y_max_n30 = 150.004  # No multiplo de 1/64
            patch_n30[8 * 16 + 8] = [y_max_n30, 0.0]
            # (8, 9) a y_max - 0.499 -> entra en M_srv; (8, 7) a y_max - 0.501 -> queda fuera de M_srv
            patch_n30[8 * 16 + 9] = [y_max_n30 - 0.499, 0.0]
            patch_n30[8 * 16 + 7] = [y_max_n30 - 0.501, 0.0]
            det_n30 = s_mapa_eval.locate_world_feature_from_patch(patch_n30, roi_m, "relief_peak", 0.0)
            self.assertIsNotNone(det_n30)
            self.assertEqual(det_n30["m_srv"], [(8, 8), (8, 9)])

            # N29: Los dos casos de frontera alrededor de 0.2 m de contacto vertical sobre floats sin cuantizar
            # 0.2001 m se redondearia a 13/64 = 0.203125, pero 0.197 m se redondearia a 13/64 = 0.203125 > 0.2 si se cuantizara!
            # Con floats sin cuantizar: 0.197 m (< 0.2 m) PASA y 0.201 m (>= 0.2 m) FALLA, y 0.1999 m PASA mientras 0.2001 m FALLA.
            p_n29_pass = tpath / "n29_pass_01999"
            _build_synthetic_part(
                p_n29_pass,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                contact_offset_y_m=0.1999,
            )
            v_n29_pass = s_mapa_eval.evaluate(p_n29_pass, repo_root=REPO_ROOT)
            self.assertEqual(v_n29_pass["exit_code"], 0, v_n29_pass)

            p_n29_fail = tpath / "n29_fail_02001"
            _build_synthetic_part(
                p_n29_fail,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                contact_offset_y_m=0.2001,
            )
            v_n29_fail = s_mapa_eval.evaluate(p_n29_fail, repo_root=REPO_ROOT)
            self.assertEqual(v_n29_fail["exit_code"], 1)
            self.assertEqual(next(c for c in v_n29_fail["checks"] if c["id"] == "MAP-03")["status"], "fail")

            # N19 + N23: spawn_then_reject en P_OUT, P_BRIDGE y P_ROOF con ent_id_n == 0 y post_count_n == pre_count_n
            p_n19 = tpath / "neg_n19_spawn_then_reject"
            _build_synthetic_part(
                p_n19,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                spawn_then_reject_all_negatives=True,
            )
            v_n19 = s_mapa_eval.evaluate(p_n19, repo_root=REPO_ROOT)
            self.assertEqual(v_n19["exit_code"], 1)
            by_id_19 = {c["id"]: c["status"] for c in v_n19["checks"]}
            self.assertEqual(by_id_19["MAP-05"], "fail")
            self.assertEqual(by_id_19["MAP-06"], "fail")
            self.assertEqual(by_id_19["MAP-07"], "fail")

            # N22: Costa de pendiente < 0.20 m -> 2 INCONCLUSO (missing_independent_correspondence)
            p_n22 = tpath / "neg_n22_shallow_coast"
            _build_synthetic_part(p_n22, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            br_22 = f03_common.read_jsonl(p_n22 / "samples" / "bridge.jsonl")
            for r in br_22:
                if r.get("ev") == "result" and isinstance(r.get("result"), dict):
                    u_rd = wire.unpack_payload(r["result"]["read"])
                    # En parche 0 (C1, coast_ns), filas 0..7 tienen row_n 0..7: rebajar altura de tierra a 0.15 m (< 0.20 m)
                    if u_rd["str"].get("mode_id") == "patch_row" and 0.0 <= float(u_rd["num"].get("row_n", -1)) <= 7.0:
                        for idx_c in range(0, len(r["result"]["read"]["ncell"]), 2):
                            r["result"]["read"]["ncell"][idx_c] = 0.15
            _write_jsonl(p_n22 / "samples" / "bridge.jsonl", br_22)
            v_n22 = s_mapa_eval.evaluate(p_n22, repo_root=REPO_ROOT)
            self.assertEqual(v_n22["exit_code"], 2)
            self.assertEqual(v_n22["reasons"], ["missing_independent_correspondence"])

            # N25 + N31: Captura certificadora ausente, con hash alterado, o con commit/sello inexistente -> unaccredited_fixture
            p_n25_miss = tpath / "neg_n25_missing_cert"
            _build_synthetic_part(p_n25_miss, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            (p_n25_miss / "samples" / "s_mapa_certifying_capture.json").unlink()
            self.assertEqual(s_mapa_eval.evaluate(p_n25_miss, repo_root=REPO_ROOT)["exit_code"], 2)

            p_n31_bad_commit = tpath / "neg_n31_bad_cert_commit"
            _build_synthetic_part(p_n31_bad_commit, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            fx_bad_c = gate_core.read_json(p_n31_bad_commit / "samples" / "s_mapa_puntos.json")
            fx_bad_c = _compute_stamped_fixture(
                fx_bad_c,
                cert_git_head="deadbeef" * 5,
                cert_probe_stamp=self.real_probe_stamp,
            )
            cert_bad_bytes = json.dumps(fx_bad_c["certifying_capture"], indent=2, sort_keys=True).encode("utf-8")
            (p_n31_bad_commit / "samples" / "s_mapa_certifying_capture.json").write_bytes(cert_bad_bytes)
            gate_core.write_json(p_n31_bad_commit / "samples" / "s_mapa_puntos.json", fx_bad_c)
            prov_bad_c = gate_core.read_json(p_n31_bad_commit / "samples" / "map_provenance.json")
            prov_bad_c["fixture_sha256"] = f03_common.sha256_file_hex(p_n31_bad_commit / "samples" / "s_mapa_puntos.json")
            prov_bad_c["certifying_capture_sha256"] = f03_common.sha256_file_hex(
                p_n31_bad_commit / "samples" / "s_mapa_certifying_capture.json"
            )
            gate_core.write_json(p_n31_bad_commit / "samples" / "map_provenance.json", prov_bad_c)
            v_n31_commit = s_mapa_eval.evaluate(p_n31_bad_commit, repo_root=REPO_ROOT)
            self.assertEqual(v_n31_commit["exit_code"], 2)
            self.assertEqual(v_n31_commit["reasons"], ["unaccredited_fixture"])

            p_n31_bad_stamp = tpath / "neg_n31_bad_cert_stamp"
            _build_synthetic_part(p_n31_bad_stamp, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            fx_bad_s = gate_core.read_json(p_n31_bad_stamp / "samples" / "s_mapa_puntos.json")
            fx_bad_s = _compute_stamped_fixture(
                fx_bad_s,
                cert_git_head=self.real_git_head,
                cert_probe_stamp="1234567890abcdef",
            )
            (p_n31_bad_stamp / "samples" / "s_mapa_certifying_capture.json").write_bytes(
                json.dumps(fx_bad_s["certifying_capture"], indent=2, sort_keys=True).encode("utf-8")
            )
            gate_core.write_json(p_n31_bad_stamp / "samples" / "s_mapa_puntos.json", fx_bad_s)
            prov_bad_s = gate_core.read_json(p_n31_bad_stamp / "samples" / "map_provenance.json")
            prov_bad_s["fixture_sha256"] = f03_common.sha256_file_hex(p_n31_bad_stamp / "samples" / "s_mapa_puntos.json")
            prov_bad_s["certifying_capture_sha256"] = f03_common.sha256_file_hex(
                p_n31_bad_stamp / "samples" / "s_mapa_certifying_capture.json"
            )
            gate_core.write_json(p_n31_bad_stamp / "samples" / "map_provenance.json", prov_bad_s)
            v_n31_stamp = s_mapa_eval.evaluate(p_n31_bad_stamp, repo_root=REPO_ROOT)
            self.assertEqual(v_n31_stamp["exit_code"], 2)
            self.assertEqual(v_n31_stamp["reasons"], ["unaccredited_fixture"])

            # N31: Captura certificadora sin las ordenes/resultados conservados -> unaccredited_fixture
            p_n31_no_ops = tpath / "neg_n31_missing_cert_ops"
            _build_synthetic_part(p_n31_no_ops, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            fx_no_ops = gate_core.read_json(p_n31_no_ops / "samples" / "s_mapa_puntos.json")
            del fx_no_ops["certifying_capture"]["patches"]["C1"]["feature_locate_op"]
            fx_no_ops = _compute_stamped_fixture(
                fx_no_ops,
                cert_git_head=self.real_git_head,
                cert_probe_stamp=self.real_probe_stamp,
            )
            (p_n31_no_ops / "samples" / "s_mapa_certifying_capture.json").write_bytes(
                json.dumps(fx_no_ops["certifying_capture"], indent=2, sort_keys=True).encode("utf-8")
            )
            gate_core.write_json(p_n31_no_ops / "samples" / "s_mapa_puntos.json", fx_no_ops)
            prov_no_ops = gate_core.read_json(p_n31_no_ops / "samples" / "map_provenance.json")
            prov_no_ops["fixture_sha256"] = f03_common.sha256_file_hex(p_n31_no_ops / "samples" / "s_mapa_puntos.json")
            prov_no_ops["certifying_capture_sha256"] = f03_common.sha256_file_hex(
                p_n31_no_ops / "samples" / "s_mapa_certifying_capture.json"
            )
            gate_core.write_json(p_n31_no_ops / "samples" / "map_provenance.json", prov_no_ops)
            v_n31_no_ops = s_mapa_eval.evaluate(p_n31_no_ops, repo_root=REPO_ROOT)
            self.assertEqual(v_n31_no_ops["exit_code"], 2)
            self.assertEqual(v_n31_no_ops["reasons"], ["unaccredited_fixture"])

    def test_exhaustive_wire_budget_under_1024_bytes_n26_n29(self) -> None:
        """Verifica que todos los /poll y /result de map_* caben en < 1024 B incluso con floats sin cuantizar (N26, N29)."""
        op_id = "0123456789abcdef-320"
        inst = "0123456789abcdef"
        now_ms = 99999999.999
        late_tick = 899999.984375
        late_frame = 999999.0

        def _make_full_res(payload: dict) -> dict:
            rd = dict(payload)
            rd["frame"] = 999999
            rd["tick_s"] = 899999.984
            rd["pos"] = [0.0, 0.0, 0.0]
            rd["ypr"] = [0.0, 0.0, 0.0]
            rd["y"] = 0.0
            rd["fog"] = 0.0
            rd["rpc_log"] = []
            rd["has"] = ["payload"]
            return {
                "done_ms": late_tick,
                "dup": False,
                "frame_done": 999999,
                "frame_recv": 999998,
                "op_id": op_id,
                "read": rd,
                "reason": "",
                "recv_ms": late_tick,
                "status": "done",
            }

        # 1) map_world_read con floats de longitud maxima sin cuantizar (N29)
        wr_args_healthy = wire.pack_payload(
            scalars_str={"mode_id": "patch_row", "qa_fault": wire.format_qa_fault(None)},
            scalars_num={"x0_m": 13920.12345678, "z0_m": 13680.87654321, "step_m": 3.75, "row_n": 95.0, "chunk_n": 8.0},
        )
        wr_args_fault = wire.pack_payload(
            scalars_str={"mode_id": "patch_row", "qa_fault": wire.format_qa_fault("ignore_elevated_surface")},
            scalars_num={"x0_m": 13920.12345678, "z0_m": 13680.87654321, "step_m": 3.75, "row_n": 95.0, "chunk_n": 8.0},
        )
        wr_poll_h = wire.poll_wire_bytes(
            {"args": bridge_qa.full_args(wr_args_healthy), "inst": inst, "issued_ms": late_tick, "op_id": op_id, "ttl_ms": 5000, "verb": "map_world_read"},
            now_ms=now_ms,
        )
        wr_poll_f = wire.poll_wire_bytes(
            {"args": bridge_qa.full_args(wr_args_fault), "inst": inst, "issued_ms": late_tick, "op_id": op_id, "ttl_ms": 5000, "verb": "map_world_read"},
            now_ms=now_ms,
        )
        self.assertEqual(len(wr_poll_h), len(wr_poll_f))
        self.assertLess(len(wr_poll_h), 1024)

        wr_res_pl = wire.pack_payload(
            scalars_str={"world_name": "chernarusplus", "mode_id": "patch_row"},
            scalars_num={
                "world_size_m": 15360.0,
                "sea_level_m": 0.0,
                "x0_m": 13920.125,
                "z0_m": 13680.875,
                "step_m": 3.75,
                "row_n": 95.0,
                "tick_ms": late_tick,
                "frame": late_frame,
            },
            num_cols=["y_m", "sea_b"],
            row_dicts=[{"y_m": 243.1234567890123 + i * 0.1111111111, "sea_b": 0.0} for i in range(8)],
        )
        wr_res_bytes = wire.result_wire_bytes(_make_full_res(wr_res_pl))
        self.assertLess(len(wr_res_bytes), 1024)

        # 2) map_feature_locate (verify rechazado con motivo largo y centroide fraccionario sin cuantizar)
        fl_args = wire.pack_payload(
            scalars_str={"point_id": "V3", "feature_kind": "relief_peak", "mode_id": "verify", "qa_fault": wire.format_qa_fault(None)},
            scalars_num={
                "req_x_m": 12515.625,
                "req_z_m": 10080.125,
                "x_min_m": 12487.5,
                "z_min_m": 10053.75,
                "x_max_m": 12543.75,
                "z_max_m": 10110.0,
            },
        )
        fl_poll = wire.poll_wire_bytes(
            {"args": bridge_qa.full_args(fl_args), "inst": inst, "issued_ms": late_tick, "op_id": op_id, "ttl_ms": 5000, "verb": "map_feature_locate"},
            now_ms=now_ms,
        )
        self.assertLess(len(fl_poll), 1024)

        fl_res_pl = wire.pack_payload(
            scalars_str={
                "point_id": "V3",
                "mode_id": "verify",
                "decision_id": "rejected",
                "reject_reason_id": "verification_error_exceeded",
            },
            scalars_num={
                "req_x_m": 12515.625,
                "req_z_m": 10080.125,
                "srv_feature_found_b": 1.0,
                "srv_x_m": 12540.333333333334,
                "srv_y_m": 254.1234567890123,
                "srv_z_m": 10095.666666666666,
                "prominence_m": 34.1234567890123,
                "err_xz_m": 29.1876543210987,
                "err_reflected_z_m": 4815.541666666666,
                "tick_ms": late_tick,
                "frame": late_frame,
            },
            num_cols=["sx_m", "sz_m", "y_m", "sea_b"],
            row_dicts=[
                {"sx_m": 12487.5, "sz_m": 10110.0, "y_m": 220.0000001234, "sea_b": 0.0},
                {"sx_m": 12540.0, "sz_m": 10095.0, "y_m": 254.123456789, "sea_b": 0.0},
            ],
        )
        fl_res_bytes = wire.result_wire_bytes(_make_full_res(fl_res_pl))
        self.assertLess(len(fl_res_bytes), 1024)

        # 3) map_place_ground con contact_height_error, clases de 32 caracteres y alturas sin cuantizar (N29)
        pg_args_h = wire.pack_payload(
            scalars_str={"point_id": "P_BRIDGE", "class_id": "Barrel_Green", "qa_fault": wire.format_qa_fault(None)},
            scalars_num={"req_x_m": 13210.125, "req_z_m": 4200.875},
        )
        pg_args_f = wire.pack_payload(
            scalars_str={"point_id": "P_BRIDGE", "class_id": "Barrel_Green", "qa_fault": wire.format_qa_fault("spawn_then_reject")},
            scalars_num={"req_x_m": 13210.125, "req_z_m": 4200.875},
        )
        pg_poll_h = wire.poll_wire_bytes(
            {"args": bridge_qa.full_args(pg_args_h), "inst": inst, "issued_ms": late_tick, "op_id": op_id, "ttl_ms": 5000, "verb": "map_place_ground"},
            now_ms=now_ms,
        )
        pg_poll_f = wire.poll_wire_bytes(
            {"args": bridge_qa.full_args(pg_args_f), "inst": inst, "issued_ms": late_tick, "op_id": op_id, "ttl_ms": 5000, "verb": "map_place_ground"},
            now_ms=now_ms,
        )
        self.assertEqual(len(pg_poll_h), len(pg_poll_f))
        self.assertLess(len(pg_poll_h), 1024)

        pg_res_pl = wire.pack_payload(
            scalars_str={
                "point_id": "P_BRIDGE",
                "decision_id": "rejected",
                "reject_reason_id": "contact_height_error",
                "hit_class_id": "Land_Bridge_Concrete_LongName_32",
                "obs_class_id": "Barrel_Green_Custom_LongClass_32",
            },
            scalars_num={
                "req_x_m": 13210.125,
                "req_z_m": 4200.875,
                "terrain_y_m": 124.1234567890123,
                "road_y_m": 129.8765432109876,
                "ray_hit_b": 1.0,
                "hit_y_m": 129.8765432109876,
                "seq_pre_n": 10.0,
                "seq_post_n": 11.0,
                "ent_id_n": 999999.0,
                "obs_x_m": 13210.12345678901,
                "obs_y_m": 124.6859567890123,
                "obs_z_m": 4200.87654321098,
                "bbox_min_y_m": -0.5625001234567,
                "bbox_max_y_m": 0.5625001234567,
                "obs_surf_y_m": 124.1234567890123,
                "pre_count_n": 12.0,
                "post_count_n": 12.0,
                "tick_ms": late_tick,
                "frame": late_frame,
            },
        )
        pg_res_bytes = wire.result_wire_bytes(_make_full_res(pg_res_pl))
        self.assertLess(len(pg_res_bytes), 1024)

    def test_historical_wire_cap_reevaluation_and_params_unverified_n27(self) -> None:
        """Verifica la reevaluacion historica frente a cambio de WIRE_CAP a 1100 (N27 y F0.3-0 §13 A3)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            head1 = _init_temp_git_repo(root, wire_cap=3500)
            stamp1 = f03_common.compute_probe_stamp_at_commit(head1, repo_root=root)

            pdir = Path(tmp) / "part_run"
            _build_synthetic_part(pdir, git_head=head1, probe_stamp=stamp1, wire_cap=3500)
            v1 = s_mapa_eval.evaluate(pdir, repo_root=root)
            self.assertEqual(v1["exit_code"], 0, v1)

            # Rebajar WIRE_CAP a 1100 en un nuevo commit y en memoria: reevaluar la parte en head1 sigue dando 0 PASA
            w_path = root / "DayZSandbox_dev" / "qa" / "wire.py"
            w_path.write_bytes(w_path.read_text(encoding="utf-8").replace("WIRE_CAP = 3500", "WIRE_CAP = 1100").encode("utf-8"))
            _git_run(root, "add", ".")
            _git_run(root, "commit", "-m", "lower-wire-cap-1100")
            with mock.patch.object(wire, "WIRE_CAP", 1100):
                v_after = s_mapa_eval.evaluate(pdir, repo_root=root)
                self.assertEqual(v_after, v1)

            # Si manifest.identity.params.wire_cap difiere del wire.py en git_head -> 2 INCONCLUSO (params_unverified)
            p_mismatch = Path(tmp) / "part_mismatch"
            _build_synthetic_part(p_mismatch, git_head=head1, probe_stamp=stamp1, wire_cap=2800)
            v_mis = s_mapa_eval.evaluate(p_mismatch, repo_root=root)
            self.assertEqual(v_mis["exit_code"], 2)
            self.assertEqual(v_mis["reasons"], ["params_unverified"])

    def test_blindness_and_invariance_of_evaluator(self) -> None:
        """Alterar injection.json, part.json, manifest['faults'], argv, carpeta y op_id no cambia el veredicto."""
        with tempfile.TemporaryDirectory() as tmp:
            p_orig = Path(tmp) / "run"
            _build_synthetic_part(
                p_orig,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                nonce="aaaa1111bbbb2222",
            )
            v_orig = s_mapa_eval.evaluate(p_orig, repo_root=REPO_ROOT)
            self.assertEqual(v_orig["exit_code"], 0)

            p_inv = Path(tmp) / "mut-flip_v_matrix"
            shutil.copytree(p_orig, p_inv)
            gate_core.write_json(
                p_inv / "injection.json",
                {"applied": True, "mutant": "flip_v_matrix", "observable_effect": {"a22_sign": 1}},
            )
            gate_core.write_json(
                p_inv / "part.json",
                {"op_map": ["x"], "op_nonce": "9999888877776666", "part": "mut-flip_v_matrix", "spike_id": "S-mapa"},
            )
            man = gate_core.read_json(p_inv / "manifest.json")
            man["faults"] = ["flip_v_matrix", "elevated_not_rejected"]
            man["argv"] = ["qa/m1_gate.py", "spike", "S-mapa", "--fault", "flip_v_matrix"]
            gate_core.write_json(p_inv / "manifest.json", man)

            # Renombrar coherentemente todos los op_id en bridge.jsonl, scenario.jsonl y map_provenance.json
            for rel in ("bridge.jsonl", "scenario.jsonl", "map_provenance.json"):
                fp = p_inv / "samples" / rel
                txt = fp.read_text(encoding="utf-8").replace("aaaa1111bbbb2222", "cccc3333dddd4444")
                fp.write_bytes(txt.encode("utf-8"))

            v_inv = s_mapa_eval.evaluate(p_inv, repo_root=REPO_ROOT)
            self.assertEqual(v_inv, v_orig)

    # =========================================================================
    # Negativas de la revision de Sol r1 (BLOQ 1..9, MEN 10). Cada una reproduce
    # una fabricacion concreta y debe dar FALLA o INCONCLUSO, nunca PASA.
    # =========================================================================
    def test_neg_sol01_sat_label_without_files_or_reference(self) -> None:
        """BLOQ 1: dayz_tools_sat no se acredita por etiqueta; sin ficheros ni referencia, INCONCLUSO."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "neg_sat_label"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            prov = gate_core.read_json(pdir / "samples" / "map_provenance.json")
            prov["source_kind"] = "dayz_tools_sat"
            prov["sat_reference_image_sha256"] = "00" * 32
            gate_core.write_json(pdir / "samples" / "map_provenance.json", prov)
            v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 2)
            self.assertEqual(v["reasons"], ["unaccredited_sat_source"])

    def test_neg_sol02_physical_copies_of_calibration_as_verification(self) -> None:
        """BLOQ 2: V1..V3 copiadas fisicamente de C1..C3 no acreditan la separacion."""
        with tempfile.TemporaryDirectory() as tmp:
            frozen = gate_core.read_json(FIXTURE_PATH)
            custom = copy.deepcopy(frozen)
            cal = custom["calibration_points"]
            custom["verification_points"] = []
            for idx, src in enumerate(cal):
                cp = copy.deepcopy(src)
                cp["point_id"] = s_mapa_eval.VER_IDS[idx]
                custom["verification_points"].append(cp)
            for idx, src in enumerate(cal):
                pid = s_mapa_eval.VER_IDS[idx]
                custom["certifying_capture"]["patches"][pid] = copy.deepcopy(
                    custom["certifying_capture"]["patches"][src["point_id"]]
                )
            pdir = Path(tmp) / "neg_v_copies_c"
            _build_synthetic_part(
                pdir,
                git_head=self.real_git_head,
                probe_stamp=self.real_probe_stamp,
                custom_fixture=custom,
            )
            with mock.patch.object(s_mapa_eval, "_load_frozen_fixture", return_value=copy.deepcopy(custom)):
                v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 2)
            self.assertEqual(v["reasons"], ["unaccredited_fixture"])

    def test_neg_sol03_orders_without_matching_coordinates(self) -> None:
        """BLOQ 3: MAP-02/MAP-03 contrastan la orden con su respuesta, no el eco de la respuesta."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "neg_zero_order_coords"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            for row in rows:
                if row.get("ev") != "enq" or row.get("verb") not in ("map_feature_locate", "map_place_ground"):
                    continue
                u = wire.unpack_payload(row["args"])
                if row["verb"] == "map_feature_locate" and u["str"].get("mode_id") == "calibrate":
                    for key in ("x_min_m", "z_min_m", "x_max_m", "z_max_m"):
                        u["num"][key] = 0.0
                else:
                    for key in ("req_x_m", "req_z_m"):
                        u["num"][key] = 0.0
                row["args"] = wire.pack_payload(scalars_str=u["str"], scalars_num=u["num"])
            _write_jsonl(pdir / "samples" / "bridge.jsonl", rows)
            v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 1, v)
            self.assertEqual(next(c for c in v["checks"] if c["id"] == "MAP-02")["status"], "fail")

            # Origenes observados a cero en la respuesta, con la orden correcta.
            pdir2 = Path(tmp) / "neg_zero_read_origins"
            _build_synthetic_part(pdir2, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows2 = f03_common.read_jsonl(pdir2 / "samples" / "bridge.jsonl")
            for row in rows2:
                if row.get("ev") == "result" and isinstance(row.get("result"), dict):
                    res = row["result"]
                    u = wire.unpack_payload(res["read"]) if res.get("status") == "done" else None
                    if u is not None and u["str"].get("mode_id") in ("grid_row", "patch_row"):
                        u["num"]["x0_m"] = 0.0
                        u["num"]["z0_m"] = 0.0
                        res["read"] = wire.pack_payload(
                            scalars_str=u["str"],
                            scalars_num=u["num"],
                            num_cols=u["ncol"],
                            row_dicts=u["rows"],
                        )
            _write_jsonl(pdir2 / "samples" / "bridge.jsonl", rows2)
            v2 = s_mapa_eval.evaluate(pdir2, repo_root=REPO_ROOT)
            self.assertEqual(v2["exit_code"], 2, v2)

    def test_neg_sol04_unbound_or_ambiguous_operations(self) -> None:
        """BLOQ 4: operaciones atribuidas a una instancia no registrada o duplicadas ambiguas."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "neg_client_attribution"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            target = None
            for row in rows:
                if row.get("ev") == "enq" and row.get("verb") == "map_place_ground":
                    target = row.get("op_id")
                    break
            self.assertIsNotNone(target)
            for row in rows:
                if row.get("op_id") == target:
                    row["peer"] = "client"
                    if "inst" in row:
                        row["inst"] = "cli-map-1"
                if row.get("ev") == "poll" and target in (row.get("op_ids") or []):
                    row["peer"] = "client"
                    row["inst"] = "cli-map-1"
            _write_jsonl(pdir / "samples" / "bridge.jsonl", rows)
            v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 2, v)

            # Duplicado ambiguo: mismo op_id con otra orden.
            pdir2 = Path(tmp) / "neg_ambiguous_dup"
            _build_synthetic_part(pdir2, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows2 = f03_common.read_jsonl(pdir2 / "samples" / "bridge.jsonl")
            enq = next(r for r in rows2 if r.get("ev") == "enq")
            dup = copy.deepcopy(enq)
            dup["verb"] = "map_world_read"
            rows2.append(dup)
            _write_jsonl(pdir2 / "samples" / "bridge.jsonl", rows2)
            v2 = s_mapa_eval.evaluate(pdir2, repo_root=REPO_ROOT)
            self.assertEqual(v2["exit_code"], 2, v2)

    def test_neg_sol05_fabricated_placement_heights_and_copied_request(self) -> None:
        """BLOQ 5: alturas y contacto se contrastan con las muestras del mundo y terrain_y_m."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "neg_constant_place_heights"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            for row in rows:
                if row.get("ev") != "result" or not isinstance(row.get("result"), dict):
                    continue
                res = row["result"]
                u = wire.unpack_payload(res["read"]) if res.get("status") == "done" else None
                if u is None or u["str"].get("decision_id") != "placed":
                    continue
                # obs_x/obs_z siguen copiados de req, pero la altura observada se fija
                # a 0.5625 y la superficie a 0, mientras terrain_y_m dice otra cosa.
                u["num"]["obs_y_m"] = 0.5625
                u["num"]["bbox_min_y_m"] = -0.5625
                u["num"]["bbox_max_y_m"] = 0.5625
                u["num"]["obs_surf_y_m"] = 0.0
                res["read"] = wire.pack_payload(
                    scalars_str=u["str"], scalars_num=u["num"], num_cols=u["ncol"], row_dicts=u["rows"]
                )
            _write_jsonl(pdir / "samples" / "bridge.jsonl", rows)
            v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 1, v)
            self.assertEqual(next(c for c in v["checks"] if c["id"] == "MAP-03")["status"], "fail")

    def test_neg_sol06_counters_reset_or_rounded(self) -> None:
        """BLOQ 6: los contadores de N23 son enteros exactos y continuos toda la sesion."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "neg_counter_reset_on_rejects"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            for row in rows:
                if row.get("ev") != "result" or not isinstance(row.get("result"), dict):
                    continue
                res = row["result"]
                u = wire.unpack_payload(res["read"]) if res.get("status") == "done" else None
                if u is None or u["str"].get("decision_id") != "rejected":
                    continue
                if u["str"].get("reject_reason_id") in ("out_of_map", "elevated_surface"):
                    u["num"]["seq_pre_n"] = 0.0
                    u["num"]["seq_post_n"] = 0.0
                    res["read"] = wire.pack_payload(
                        scalars_str=u["str"], scalars_num=u["num"], num_cols=u["ncol"], row_dicts=u["rows"]
                    )
            _write_jsonl(pdir / "samples" / "bridge.jsonl", rows)
            v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 1, v)
            self.assertEqual(next(c for c in v["checks"] if c["id"] == "MAP-03")["status"], "fail")

            # Censo redondeado: pre_count_n=0 y post_count_n=0.49 no es un entero exacto.
            pdir2 = Path(tmp) / "neg_rounded_census"
            _build_synthetic_part(pdir2, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows2 = f03_common.read_jsonl(pdir2 / "samples" / "bridge.jsonl")
            for row in rows2:
                if row.get("ev") != "result" or not isinstance(row.get("result"), dict):
                    continue
                res = row["result"]
                u = wire.unpack_payload(res["read"]) if res.get("status") == "done" else None
                if u is None or u["str"].get("decision_id") != "rejected":
                    continue
                if u["str"].get("reject_reason_id") == "out_of_map":
                    u["num"]["pre_count_n"] = 0.0
                    u["num"]["post_count_n"] = 0.49
                    res["read"] = wire.pack_payload(
                        scalars_str=u["str"], scalars_num=u["num"], num_cols=u["ncol"], row_dicts=u["rows"]
                    )
            _write_jsonl(pdir2 / "samples" / "bridge.jsonl", rows2)
            v2 = s_mapa_eval.evaluate(pdir2, repo_root=REPO_ROOT)
            self.assertEqual(v2["exit_code"], 1, v2)
            self.assertEqual(next(c for c in v2["checks"] if c["id"] == "MAP-03")["status"], "fail")

    def test_neg_sol07_capture_without_full_coverage_or_declared_promotion(self) -> None:
        """BLOQ 7: N31 exige 32 ordenes distintas y una captura offline no se promociona por declaracion."""
        with tempfile.TemporaryDirectory() as tmp:
            frozen = gate_core.read_json(FIXTURE_PATH)
            stub = copy.deepcopy(frozen)
            for pid in s_mapa_eval.PATCH_IDS:
                stub["certifying_capture"]["patches"][pid]["patch_row_ops"] = stub["certifying_capture"][
                    "patches"
                ][pid]["patch_row_ops"][:2]
            pdir = Path(tmp) / "neg_capture_two_orders"
            _build_synthetic_part(
                pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp, custom_fixture=stub
            )
            with mock.patch.object(s_mapa_eval, "_load_frozen_fixture", return_value=copy.deepcopy(stub)):
                v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 2)
            self.assertEqual(v["reasons"], ["unaccredited_fixture"])

            # Una captura offline relabelada como diag/ingame en samples/ no vale
            # si la fixture congelada sigue diciendo offline.
            pdir2 = Path(tmp) / "neg_offline_declared_diag"
            _build_synthetic_part(pdir2, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            fx = gate_core.read_json(pdir2 / "samples" / "s_mapa_puntos.json")
            fx["accreditation"]["accredited_ingame"] = True
            fx["certifying_capture"]["certifying_build"] = "diag"
            fx["certifying_capture"]["certifying_hello"]["build"] = "diag"
            fx = _compute_stamped_fixture(
                fx,
                cert_git_head=self.real_git_head,
                cert_probe_stamp=self.real_probe_stamp,
            )
            (pdir2 / "samples" / "s_mapa_certifying_capture.json").write_bytes(
                json.dumps(fx["certifying_capture"], indent=2, sort_keys=True).encode("utf-8")
            )
            gate_core.write_json(pdir2 / "samples" / "s_mapa_puntos.json", fx)
            prov = gate_core.read_json(pdir2 / "samples" / "map_provenance.json")
            prov["fixture_sha256"] = f03_common.sha256_file_hex(pdir2 / "samples" / "s_mapa_puntos.json")
            prov["certifying_capture_sha256"] = f03_common.sha256_file_hex(
                pdir2 / "samples" / "s_mapa_certifying_capture.json"
            )
            gate_core.write_json(pdir2 / "samples" / "map_provenance.json", prov)
            v2 = s_mapa_eval.evaluate(pdir2, repo_root=REPO_ROOT)
            self.assertEqual(v2["exit_code"], 2, v2)
            self.assertEqual(v2["reasons"], ["unaccredited_fixture"])

    def test_neg_sol08_e2e_reference_negatives_and_n24_locator(self) -> None:
        """BLOQ 8: runner sin peers, extension solo-located, .c comentario y localizador N24 completo."""
        with tempfile.TemporaryDirectory() as tmp:
            # 1) Runner que escribe paquetes sin arrancar peers.
            pdir = Path(tmp) / "neg_runner_without_peers"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            man = gate_core.read_json(pdir / "manifest.json")
            man["execution_identity"]["fake_peer_pids"] = {"client": None, "server": None}
            gate_core.write_json(pdir / "manifest.json", man)
            empty_record = _TrafficRecord()
            self.assertIn("runner_without_peers", _verify_part_against_record(pdir, empty_record))
            self.assertIn("no_recorded_traffic", _verify_part_against_record(pdir, empty_record))

            # 2) Extension que solo devuelve decision_id="located".
            minimal = {
                "str": {"point_id": "C1", "mode_id": "calibrate", "decision_id": "located", "reject_reason_id": ""},
                "num": {},
                "rows": [],
                "ncol": [],
                "scol": [],
            }
            self.assertIn("missing_locate_num:req_x_m", _locate_payload_problems(minimal))
            pdir2 = Path(tmp) / "neg_located_only"
            _build_synthetic_part(pdir2, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows2 = f03_common.read_jsonl(pdir2 / "samples" / "bridge.jsonl")
            for row in rows2:
                if row.get("ev") == "result" and isinstance(row.get("result"), dict):
                    res = row["result"]
                    u = wire.unpack_payload(res["read"]) if res.get("status") == "done" else None
                    if u is not None and u["str"].get("mode_id") == "calibrate":
                        res["read"] = wire.pack_payload(
                            scalars_str={
                                "point_id": u["str"]["point_id"],
                                "mode_id": "calibrate",
                                "decision_id": "located",
                                "reject_reason_id": "",
                            },
                            scalars_num={"req_x_m": 0.0, "req_z_m": 0.0},
                        )
            _write_jsonl(pdir2 / "samples" / "bridge.jsonl", rows2)
            v2 = s_mapa_eval.evaluate(pdir2, repo_root=REPO_ROOT)
            self.assertEqual(v2["exit_code"], 2, v2)

            # 3) DSBX_QA_X_Map.c compuesto solo por un comentario.
            comment_only = "// class DSBX_QA_X_Map SpawnTrackedObject CreateObjectEx( SurfaceY\n"
            self.assertIn("missing_code_token:override bool Handles(", _probe_c_problems(comment_only))

            # 4) N24: el localizador fraudulento completo (centroide de solo 2 filas)
            #    se entrega al evaluador; MAP-02 debe rechazarlo contra las 256 muestras.
            pdir3 = Path(tmp) / "neg_n24_two_row_locator"
            _build_synthetic_part(pdir3, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            rows3 = f03_common.read_jsonl(pdir3 / "samples" / "bridge.jsonl")
            for row in rows3:
                if row.get("ev") != "result" or not isinstance(row.get("result"), dict):
                    continue
                res = row["result"]
                u = wire.unpack_payload(res["read"]) if res.get("status") == "done" else None
                if u is None or u["str"].get("point_id") != "C2" or u["str"].get("mode_id") != "calibrate":
                    continue
                rows_loc = u["rows"]
                if len(rows_loc) != 2:
                    continue
                avg_x = 0.5 * (float(rows_loc[0]["sx_m"]) + float(rows_loc[1]["sx_m"]))
                avg_z = 0.5 * (float(rows_loc[0]["sz_m"]) + float(rows_loc[1]["sz_m"]))
                u["num"]["srv_x_m"] = avg_x
                u["num"]["srv_z_m"] = avg_z
                res["read"] = wire.pack_payload(
                    scalars_str=u["str"], scalars_num=u["num"], num_cols=u["ncol"], row_dicts=u["rows"]
                )
            _write_jsonl(pdir3 / "samples" / "bridge.jsonl", rows3)
            v3 = s_mapa_eval.evaluate(pdir3, repo_root=REPO_ROOT)
            self.assertEqual(v3["exit_code"], 1, v3)
            self.assertEqual(next(c for c in v3["checks"] if c["id"] == "MAP-02")["status"], "fail")

    def test_neg_sol09_implementer_cannot_self_accredit(self) -> None:
        """BLOQ 9: la acreditacion diag es del propietario; el implementador no puede autoacreditar samples/."""
        frozen = gate_core.read_json(FIXTURE_PATH)
        self.assertIs(frozen["accreditation"]["accredited_ingame"], False)
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "neg_self_accredited"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            fx = gate_core.read_json(pdir / "samples" / "s_mapa_puntos.json")
            fx["accreditation"]["accredited_ingame"] = True
            gate_core.write_json(pdir / "samples" / "s_mapa_puntos.json", fx)
            prov = gate_core.read_json(pdir / "samples" / "map_provenance.json")
            prov["fixture_sha256"] = f03_common.sha256_file_hex(pdir / "samples" / "s_mapa_puntos.json")
            gate_core.write_json(pdir / "samples" / "map_provenance.json", prov)
            v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 2)
            self.assertEqual(v["reasons"], ["unaccredited_fixture"])

    def test_neg_sol10_truncated_zlib_stream(self) -> None:
        """MEN 10: un PNG con flujo zlib truncado no puede pasar aunque descomprima al tamano esperado."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "neg_truncated_idat"
            _build_synthetic_part(pdir, git_head=self.real_git_head, probe_stamp=self.real_probe_stamp)
            png_path = pdir / "samples" / "chernarus_local.png"
            raw = png_path.read_bytes()
            pos = 8
            chunks: list[tuple[bytes, bytes]] = []
            while pos < len(raw):
                length = struct.unpack(">I", raw[pos : pos + 4])[0]
                ctype = raw[pos + 4 : pos + 8]
                cdata = raw[pos + 8 : pos + 8 + length]
                chunks.append((ctype, cdata))
                pos += 12 + length
            rebuilt = bytearray(b"\x89PNG\r\n\x1a\n")
            for ctype, cdata in chunks:
                if ctype == b"IDAT" and len(cdata) > 4:
                    cdata = cdata[:-4]  # quita el trailer adler32 del flujo zlib
                crc = binascii.crc32(ctype + cdata) & 0xFFFFFFFF
                rebuilt += struct.pack(">I", len(cdata)) + ctype + cdata + struct.pack(">I", crc)
            png_path.write_bytes(bytes(rebuilt))
            prov = gate_core.read_json(pdir / "samples" / "map_provenance.json")
            prov["image_sha256"] = f03_common.sha256_file_hex(png_path)
            gate_core.write_json(pdir / "samples" / "map_provenance.json", prov)
            v = s_mapa_eval.evaluate(pdir, repo_root=REPO_ROOT)
            self.assertEqual(v["exit_code"], 1, v)
            c_m1 = next(c for c in v["checks"] if c["id"] == "MAP-01")
            self.assertEqual(c_m1["status"], "fail")
            self.assertIn("idat_stream_not_terminated", c_m1["detail"])

    # =========================================================================
    # Tests end-to-end (prefijo test_e2e_): ejercitan la implementacion real
    # (s_mapa_run.py, fake_ext_map.py, DSBX_QA_X_Map.c, m1_gate.py).
    # Deben FALLAR ahora contra el esqueleto y PASAR cuando el implementador
    # complete el spike.
    # =========================================================================
    def test_e2e_m1_gate_spike_s_mapa_offline_full_and_evaluate_only(self) -> None:
        """Ejecuta la corrida completa offline de S-mapa y su reevaluacion (--evaluate-only).

        Envuelve ``f03_common.PartContext`` para registrar el trafico real del
        nucleo y los peers lanzados; cada parte tiene que casar con ese registro.
        """
        import s_mapa_run  # noqa: F401  (se importa antes de parchear)

        _RECORD.bridge.clear()
        _RECORD.contexts.clear()
        with tempfile.TemporaryDirectory() as tmp:
            ev_dir = Path(tmp) / "ev_offline"
            writer_cls = _recording_writer_factory()
            ctx_cls = _recording_part_context_class()
            with mock.patch.object(f03_common, "_JsonlWriter", writer_cls), mock.patch.object(
                f03_common, "PartContext", ctx_cls
            ), mock.patch.object(s_mapa_run, "PartContext", ctx_cls, create=True):
                rc = m1_gate.main(
                    [
                        "spike",
                        "S-mapa",
                        "--both",
                        "--build",
                        "offline",
                        "--evidence",
                        str(ev_dir),
                    ]
                )
            self.assertEqual(rc, 0, "m1_gate.py spike S-mapa offline debe devolver 0 PASA")
            verdict = gate_core.read_json(ev_dir / "verdict.json")
            self.assertEqual(verdict["exit_code"], 0, verdict)

            expected_parts = ["run"] + [f"mut-{name}" for name in s_mapa_mutants.EXPECTED_MUTANTS]
            for pname in expected_parts:
                problems = _verify_part_against_record(ev_dir / pname, _RECORD)
                self.assertEqual(problems, [], f"{pname}: {problems}")

            rc_eval = m1_gate.main(
                [
                    "spike",
                    "S-mapa",
                    "--both",
                    "--build",
                    "offline",
                    "--evaluate-only",
                    "--evidence",
                    str(ev_dir),
                ]
            )
            self.assertEqual(rc_eval, 0)

    def test_e2e_fake_ext_map_calibrate_rejects_req_x_and_handles_verbs(self) -> None:
        """Verifica en fake_ext_map.py los 3 verbos map_* y el rechazo bad_args si calibrate incluye req_x_m (N18)."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "dsbx_qa.json"
            cfg.write_bytes(b'{"key":"k","retry_ms":200,"url":"http://127.0.0.1:9/"}\n')
            srv = fake_peer.Peer(str(cfg), "server", 59999, 60.0, None)
            try:
                # 1) calibrate con req_x_m -> rejected / bad_args (N18)
                bucket_bad: list[dict] = []
                op_bad = {
                    "args": wire.pack_payload(
                        scalars_str={"point_id": "C1", "feature_kind": "coast_ns", "mode_id": "calibrate"},
                        scalars_num={
                            "req_x_m": 1860.0,
                            "x_min_m": 1830.0,
                            "z_min_m": 2208.75,
                            "x_max_m": 1886.25,
                            "z_max_m": 2265.0,
                        },
                    ),
                    "inst": srv.inst,
                    "issued_ms": 0.0,
                    "op_id": "op-cal-bad",
                    "ttl_ms": 5000,
                    "verb": "map_feature_locate",
                }
                srv._start_op(op_bad, 10.0, time.monotonic(), bucket_bad)
                self.assertEqual(len(bucket_bad), 1)
                self.assertEqual(bucket_bad[0]["status"], "rejected")
                self.assertEqual(bucket_bad[0]["reason"], "bad_args")

                # 2) calibrate sano en C1 -> done / located
                bucket_ok: list[dict] = []
                op_ok = {
                    "args": wire.pack_payload(
                        scalars_str={"point_id": "C1", "feature_kind": "coast_ns", "mode_id": "calibrate"},
                        scalars_num={
                            "x_min_m": 1830.0,
                            "z_min_m": 2208.75,
                            "x_max_m": 1886.25,
                            "z_max_m": 2265.0,
                        },
                    ),
                    "inst": srv.inst,
                    "issued_ms": 0.0,
                    "op_id": "op-cal-ok",
                    "ttl_ms": 5000,
                    "verb": "map_feature_locate",
                }
                srv._start_op(op_ok, 11.0, time.monotonic(), bucket_ok)
                self.assertEqual(len(bucket_ok), 1)
                self.assertEqual(bucket_ok[0]["status"], "done")
                u_read = wire.unpack_payload(bucket_ok[0]["read"])
                self.assertEqual(u_read["str"].get("decision_id"), "located")
            finally:
                srv.shutdown()

    def test_e2e_probe_map_c_single_create_object_ex_and_implemented(self) -> None:
        """Verifica que DSBX_QA_X_Map.c implementa los verbos y contiene una unica llamada a CreateObjectEx(."""
        c_path = wire.REAL_PROBE_DIR / "scripts" / "5_Mission" / "DSBX_QA_X_Map.c"
        txt = c_path.read_text(encoding="utf-8")
        problems = _probe_c_problems(txt)
        self.assertEqual(problems, [], f"DSBX_QA_X_Map.c: {problems}")
        self.assertEqual(_strip_enforce_comments(txt).count("CreateObjectEx("), 1)


if __name__ == "__main__":
    unittest.main()
