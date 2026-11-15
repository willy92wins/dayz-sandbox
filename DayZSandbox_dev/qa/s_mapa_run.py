"""Runner de S-mapa (brief S-mapa §6 y §8; contrato de F0.3-0 §5.2-§5.4).

Usa solo ``f03_common.PartContext`` e ``issue_one``: todo el trafico pasa por el puente del nucleo. Las lecturas del
motor (alturas, posiciones, contadores) las devuelven los verbos ``map_*``; el runner solo ensambla el raster, ajusta la
transformacion afin y decide las coordenadas que pide en cada paso. La acreditacion en partida de la fixture NO se toca.
"""

import copy
import hashlib
import json
import math
import struct
import binascii
import traceback
import zlib
from pathlib import Path

import f03_common
import gate_core
import s_mapa_eval
import s_mapa_mutants
import wire

SPIKE_ID = "S-mapa"
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "s_mapa_puntos.json"
WORLD_SIZE_M = 15360.0
IMG_W = 4096
IMG_H = 4096
STEP_PX_M = 3.75
PATCH_IDS = ("C1", "C2", "C3", "V1", "V2", "V3")
CAL_IDS = ("C1", "C2", "C3")
VER_IDS = ("V1", "V2", "V3")
CLASS_ID = "Barrel_Green"
TILE_URL = "https://tiles.izurvive.example/{z}/{x}/{y}.png"


def _planned_parts(part_arg):
    all_parts = ["run"] + [f"mut-{name}" for name in s_mapa_mutants.EXPECTED_MUTANTS]
    if part_arg == "all":
        return all_parts
    if part_arg not in all_parts:
        raise ValueError(f"unknown part {part_arg!r} for {SPIKE_ID}")
    return [part_arg]


# --- PNG ---------------------------------------------------------------------------------------------------------
def _chunk(ctype, data):
    crc = binascii.crc32(ctype + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)


def encode_png_gray8(rows):
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    ihdr = struct.pack(">IIBBBBB", IMG_W, IMG_H, 8, 0, 0, 0, 0)
    return (
        s_mapa_eval.PNG_SIGNATURE
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw, 6))
        + _chunk(b"IEND", b"")
    )


def build_raster(grid_samples, patch_samples, rois, y_min, y_max):
    """Receta de §4.1(2): fondo de 32x32 celdas de 128 px y 6 bloques de 16x16 encima, sin interpolar."""
    lq = s_mapa_eval.quantize_luma
    bg = []
    for r in range(32):
        line = bytearray(IMG_W)
        for c in range(32):
            yv, sb = grid_samples[(r, c)]
            line[c * 128:(c + 1) * 128] = bytes([lq(yv, sb, y_min, y_max)]) * 128
        bg.append(bytes(line))
    rows = [bytearray(bg[v // 128]) for v in range(IMG_H)]
    for p_idx, roi in enumerate(rois):
        u0, v0 = roi[0], roi[1]
        for r in range(16):
            for c in range(16):
                yv, sb = patch_samples[(p_idx, r, c)]
                rows[v0 + r][u0 + c] = lq(yv, sb, y_min, y_max)
    return rows


# --- fixture y material certificador -------------------------------------------------------------------------------
def _materialize_fixture(ctx):
    """Escribe samples/s_mapa_certifying_capture.json y s_mapa_puntos.json (re-sellando solo commit y sello)."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    cap = copy.deepcopy(fixture["certifying_capture"])
    stamp = ctx.expected_stamp
    cap["certifying_git_head"] = ctx.git_head
    cap["certifying_probe_stamp"] = stamp
    cap["certifying_hello"]["probe_ver"] = "dsbx-qa1+" + stamp
    cap["certifying_wire_cap"] = int(wire.WIRE_CAP)
    cap_bytes = json.dumps(cap, indent=2, sort_keys=True).encode("utf-8")
    cap_sha = hashlib.sha256(cap_bytes).hexdigest()
    fixture["certifying_capture"] = cap
    fixture["accreditation"]["certifying_capture_sha256"] = cap_sha
    fixture["accreditation"]["certifying_probe_stamp"] = stamp
    cap_path = ctx.samples_dir / "s_mapa_certifying_capture.json"
    fix_path = ctx.samples_dir / "s_mapa_puntos.json"
    cap_path.write_bytes(cap_bytes)
    fix_path.write_bytes((json.dumps(fixture, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    return fixture, f03_common.sha256_file_hex(fix_path), cap_sha


# --- pasos ---------------------------------------------------------------------------------------------------------
class _Scenario:
    def __init__(self, ctx):
        self.ctx = ctx

    def step(self, name, fn, **extra):
        t0 = self.ctx.now_h_ms()
        op_ids = fn()
        t1 = self.ctx.now_h_ms()
        row = {"step": name, "op_ids": list(op_ids), "t_start_h_ms": t0, "t_end_h_ms": t1, "elapsed_h_ms": t1 - t0}
        row.update(extra)
        self.ctx.record_scenario(row)


def _locate_payload(pid, kind, mode, roi_m, req=None):
    nums = {}
    if req is not None:
        nums["req_x_m"] = float(req[0])
        nums["req_z_m"] = float(req[1])
    nums.update(
        {"x_min_m": roi_m[0], "z_min_m": roi_m[1], "x_max_m": roi_m[2], "z_max_m": roi_m[3]}
    )
    return wire.pack_payload(
        scalars_str={"point_id": pid, "feature_kind": kind, "mode_id": mode}, scalars_num=nums
    )


def _place_payload(pid, req):
    return wire.pack_payload(
        scalars_str={"point_id": pid, "class_id": CLASS_ID},
        scalars_num={"req_x_m": float(req[0]), "req_z_m": float(req[1])},
    )


def _run_scenario(ctx, part_name):
    issue = f03_common.issue_one
    mutant = part_name[4:] if part_name.startswith("mut-") else None
    scen = _Scenario(ctx)
    fixture, fix_sha, cap_sha = _materialize_fixture(ctx)
    feats = {p["point_id"]: p for p in fixture["calibration_points"] + fixture["verification_points"]}
    places = {p["point_id"]: p for p in fixture["placement_points"]}
    rois = [feats[pid]["roi_px"] for pid in PATCH_IDS]

    state = {"grid": {}, "patch": {}, "grid_ids": [], "patch_ids": []}

    def read_rows(out):
        return [(float(r["y_m"]), float(r["sea_b"])) for r in out.payload["rows"]]

    def step1():
        ids = []
        for idx in range(128):
            r, c0 = idx // 4, (idx % 4) * 8
            out = issue(
                ctx, "server", "map_world_read",
                wire.pack_payload(
                    scalars_str={"mode_id": "grid_row"},
                    scalars_num={"x0_m": 480.0 * c0, "z0_m": WORLD_SIZE_M - 480.0 * r, "step_m": 480.0,
                                 "row_n": float(r), "chunk_n": 8.0},
                ),
            )
            ids.append(out.op_id)
            state["grid_ids"].append(out.op_id)
            for k, cell in enumerate(read_rows(out)):
                state["grid"][(r, c0 + k)] = cell
        for p_idx, roi in enumerate(rois):
            for r in range(16):
                for half in (0, 1):
                    c0 = 8 * half
                    out = issue(
                        ctx, "server", "map_world_read",
                        wire.pack_payload(
                            scalars_str={"mode_id": "patch_row"},
                            scalars_num={"x0_m": STEP_PX_M * (roi[0] + c0),
                                         "z0_m": WORLD_SIZE_M - STEP_PX_M * (roi[1] + r),
                                         "step_m": STEP_PX_M, "row_n": float(p_idx * 16 + r), "chunk_n": 8.0},
                        ),
                    )
                    ids.append(out.op_id)
                    state["patch_ids"].append(out.op_id)
                    for k, cell in enumerate(read_rows(out)):
                        state["patch"][(p_idx, r, c0 + k)] = cell
        if len(state["grid"]) != 1024 or len(state["patch"]) != 1536:
            raise RuntimeError("incomplete_world_read")
        land = [y for (y, sb) in list(state["grid"].values()) + list(state["patch"].values()) if sb == 0.0]
        if not land or max(land) - min(land) < 1.0:
            raise RuntimeError("degenerate_relief_range")
        y_min, y_max = min(land), max(land)
        state["range"] = (y_min, y_max)
        raster = build_raster(state["grid"], state["patch"], rois, y_min, y_max)
        tiles = []
        effect = None
        if mutant == "external_tiles":
            tampered = 0
            for v in range(IMG_H):
                checker_v = ((v // 256) & 1)
                row = raster[v]
                spans = sorted(roi[0] for roi in rois if roi[1] <= v <= roi[1] + 15)
                pattern = bytearray(IMG_W)
                for u0 in range(0, IMG_W, 256):
                    pattern[u0:u0 + 256] = bytes([40 if (((u0 // 256) + checker_v) & 1) == 0 else 200]) * 256
                protected = bytearray(IMG_W)
                for u0 in spans:
                    protected[u0:u0 + 16] = b"\x01" * 16
                for u in range(IMG_W):
                    if not protected[u]:
                        row[u] = pattern[u]
                        tampered += 1
            tiles = [TILE_URL]
            effect = {"tampered_bg_pixels": tampered, "tile_urls_count": 1}
        png_path = ctx.samples_dir / "chernarus_local.png"
        png_path.write_bytes(encode_png_gray8(raster))
        gate_core.write_json(
            ctx.samples_dir / "map_provenance.json",
            {
                "schema": "dsbx.map.provenance.v4",
                "world_name": "chernarusplus",
                "world_size_m": WORLD_SIZE_M,
                "sea_level_m": 0.0,
                "source_kind": "mod_relief_plan_b",
                "image_relpath": "samples/chernarus_local.png",
                "image_sha256": f03_common.sha256_file_hex(png_path),
                "fixture_relpath": "samples/s_mapa_puntos.json",
                "fixture_sha256": fix_sha,
                "certifying_evidence_relpath": "samples/s_mapa_certifying_capture.json",
                "certifying_capture_sha256": cap_sha,
                "width_px": IMG_W,
                "height_px": IMG_H,
                "bit_depth": 8,
                "color_type": 0,
                "step_px_m": STEP_PX_M,
                "y_min_m": y_min,
                "y_max_m": y_max,
                "grid_op_ids": state["grid_ids"],
                "patch_op_ids": state["patch_ids"],
                "samples_sha256": hashlib.sha256(
                    json.dumps(
                        [sorted((list(k), list(v)) for k, v in state["grid"].items()),
                         sorted((list(k), list(v)) for k, v in state["patch"].items())]
                    ).encode("utf-8")
                ).hexdigest(),
                "crs": "CRS.Simple",
                "tile_urls": tiles,
                "external_domains": [],
            },
        )
        if effect is not None:
            ctx.write_injection(
                mutant="external_tiles", kind="scenario", target="samples/chernarus_local.png",
                observable_effect=effect,
            )
        return ids

    scen.step("world_and_relief_read", step1)

    # Paso 2: calibracion con C1..C3.
    png_rows, png_err = s_mapa_eval.decode_and_validate_png(ctx.samples_dir / "chernarus_local.png", IMG_W, IMG_H)
    if png_rows is None:
        raise RuntimeError("png_unreadable:" + png_err)
    img_pts = {}
    for pid in PATCH_IDS:
        det = s_mapa_eval.detect_image_feature(png_rows, feats[pid]["roi_px"], feats[pid]["feature_kind"])
        if det is None:
            raise RuntimeError("image_feature_not_found:" + pid)
        img_pts[pid] = det
    cal_world = {}

    def step2():
        ids = []
        for pid in CAL_IDS:
            out = issue(ctx, "server", "map_feature_locate",
                        _locate_payload(pid, feats[pid]["feature_kind"], "calibrate", feats[pid]["world_roi_m"]))
            ids.append(out.op_id)
            cal_world[pid] = (float(out.payload["num"]["srv_x_m"]), float(out.payload["num"]["srv_z_m"]))
        return ids

    scen.step("calibrate_C1_C3", step2)
    fit = s_mapa_eval.solve_affine_2d([img_pts[p] for p in CAL_IDS], [cal_world[p] for p in CAL_IDS])
    if fit is None:
        raise RuntimeError("singular_affine_fit")
    a_ok, b_ok = fit
    fit_row = {"calibration_fit": {"A": a_ok, "b": b_ok}}
    a_inv, b_inv = s_mapa_eval.invert_vertical_affine(a_ok, b_ok, float(IMG_H))

    # Paso 3: verificacion ciega y colocacion en V1..V3.
    flip = mutant == "flip_v_matrix"
    drift = mutant == "verify_drift_25m"
    a_use, b_use = (a_inv, b_inv) if flip else (a_ok, b_ok)
    proj = {}

    def step3():
        ids = []
        for pid in VER_IDS:
            x, z = s_mapa_eval.apply_affine_2d(a_use, b_use, *img_pts[pid])
            if drift:
                x += 25.0
            proj[pid] = (x, z)
            out = issue(ctx, "server", "map_feature_locate",
                        _locate_payload(pid, feats[pid]["feature_kind"], "verify", feats[pid]["world_roi_m"],
                                        req=(x, z)))
            ids.append(out.op_id)
            out = issue(ctx, "server", "map_place_ground", _place_payload(pid, (x, z)))
            ids.append(out.op_id)
        return ids

    scen.step("verify_and_place_V1_V3", step3, **fit_row)
    if flip:
        ctx.write_injection(
            mutant="flip_v_matrix", kind="scenario", target="verify_and_place_V1_V3",
            observable_effect={"a22_sign": 1 if a_use[1][1] > 0 else -1, "v1_projected_z_m": proj["V1"][1]},
        )
    if drift:
        ctx.write_injection(
            mutant="verify_drift_25m", kind="scenario", target="verify_and_place_V1_V3",
            observable_effect={"injected_dx_m": 25.0},
        )

    # Paso 4: P_GROUND.
    def step4():
        pg = places["P_GROUND"]
        x, z = s_mapa_eval.apply_affine_2d(a_ok, b_ok, float(pg["u_px"]), float(pg["v_px"]))
        return [issue(ctx, "server", "map_place_ground", _place_payload("P_GROUND", (x, z))).op_id]

    scen.step("place_ground_P_GROUND", step4, **fit_row)

    # Paso 5: eje vertical invertido sobre el ajuste sano.
    def step5():
        ids = []
        for pid in VER_IDS:
            x, z = s_mapa_eval.apply_affine_2d(a_inv, b_inv, *img_pts[pid])
            out = issue(ctx, "server", "map_feature_locate",
                        _locate_payload(pid, feats[pid]["feature_kind"], "verify", feats[pid]["world_roi_m"],
                                        req=(x, z)))
            ids.append(out.op_id)
        return ids

    scen.step("neg_inverted_axis", step5, **fit_row)

    # Paso 6: negativas de colocacion.
    results = {}

    def neg(pid, fault=None):
        def fn():
            pt = places[pid]
            out = issue(ctx, "server", "map_place_ground",
                        _place_payload(pid, (pt["req_x_m"], pt["req_z_m"])), qa_fault=fault)
            results[pid] = out
            return [out.op_id]
        return fn

    scen.step("neg_out_of_map", neg("P_OUT"))
    scen.step("neg_bridge", neg("P_BRIDGE", "ignore_elevated_surface" if mutant == "elevated_not_rejected" else None))
    scen.step("neg_roof", neg("P_ROOF", "spawn_then_reject" if mutant == "elevated_not_rejected" else None))
    if mutant == "elevated_not_rejected":
        b, r = results["P_BRIDGE"].payload, results["P_ROOF"].payload
        ctx.write_injection(
            mutant="elevated_not_rejected", kind="qa_fault", target="neg_bridge,neg_roof",
            observable_effect={
                "bridge_decision": b["str"].get("decision_id"),
                "roof_seq_delta": int(r["num"]["seq_post_n"] - r["num"]["seq_pre_n"]),
                "roof_obs_class": r["str"].get("obs_class_id"),
            },
        )


def run_part(args, base_dir, argv, part_name):
    with f03_common.PartContext(
        base_dir=base_dir, part_name=part_name, spike_id=SPIKE_ID, args=args, argv=argv
    ) as ctx:
        if ctx.startup_reason is None:
            try:
                _run_scenario(ctx, part_name)
            except Exception as exc:  # el evaluador clasificara la evidencia incompleta como INCONCLUSO
                ctx.record_scenario({"step": "runner_error", "error": f"{type(exc).__name__}: {exc}",
                                     "trace": traceback.format_exc()[-1500:]})
        ctx.finalize_manifest()
    part_dir = Path(base_dir) / part_name
    verdict = s_mapa_eval.evaluate(part_dir)
    gate_core.write_json(part_dir / "verdict.json", verdict)
    return verdict


def run(args, evidence, argv):
    base_dir = Path(evidence)
    parts = _planned_parts(getattr(args, "part", "all") or "all")
    started = gate_core.utc_now()
    for part_name in parts:
        run_part(args, base_dir, argv, part_name)
    if not (base_dir / "manifest.json").is_file():
        gate_core.write_json(
            base_dir / "manifest.json",
            gate_core.make_manifest("spike", SPIKE_ID, args, argv, started, gate_core.utc_now()),
        )
    agg = f03_common.aggregate_spike(base_dir, SPIKE_ID)
    return int(agg["exit_code"])
