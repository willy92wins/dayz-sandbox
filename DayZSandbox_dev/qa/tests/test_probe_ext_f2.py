"""Pruebas del PR «sonda: extensiones para F2»: modo de censo select_all_entityai_b, target_net_id en per_spawn_raw
y per_witness_start (testigo de creacion con trayectoria de K muestras).

Tres capas:
  * extremo a extremo offline por el nucleo (PartContext, f03_common.issue_one, read_job_pages, job_free) con
    peers falsos reales (procesos), como el runner de S-persist;
  * en proceso, con un peer de pega y reloj manual, para lo que el e2e no puede forzar de forma determinista
    (alive_b = 0, el tope exacto de filas, la identidad del modo 0 frente al fake anterior, el tamano de pagina);
  * estaticas sobre los .c, como qa/tests/test_probe_static.py.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import types
import unittest
from pathlib import Path

import f03_common
import fake_ext_persist
import fake_peer
import gate_core
import wire

from . import test_probe_static as tps

QA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = QA_DIR.parent
PERSIST_C = QA_DIR / "probe" / "DayZSandbox_QA" / "scripts" / "5_Mission" / "DSBX_QA_X_Persist.c"
WITNESS_C = QA_DIR / "probe" / "DayZSandbox_QA" / "scripts" / "4_World" / "DSBX_QA_W_Witness.c"
BASELINE_COMMIT = "6a7bd7a"  # implementacion de S-persist (rama claude/s-persist-impl-e9), de donde sale este PR

CENTER = (6170.0, 7643.0)
CENSUS_SCOL = ["class_name", "loc_kind", "parent_class", "parent_net_id", "slot_name", "owner_uid", "own_logical_id", "net_id", "pers_id"]
# Las 14 columnas numericas de S-persist tal y como estaban antes de este PR (modo 0), copiadas a mano.
CENSUS_NCOL_MODE0 = [
    "own_b", "in_radius_b", "alive_b", "ai_agent_b", "pos_x_m", "pos_y_m", "pos_z_m", "yaw_deg", "pitch_deg",
    "roll_deg", "max_hp", "health_hp", "inv_children_n", "spawn_tick_ms",
]
WITNESS_SCOL = ["class_name", "net_id", "parent_net_id"]
WITNESS_NCOL = ["sample_idx", "pos_x_m", "pos_y_m", "pos_z_m", "yaw_deg", "tick_ms", "frame", "ai_agent_b", "alive_b"]
WITNESS_START_NK = {
    "start_tick_ms", "start_frame", "center_x_m", "center_z_m", "radius_m", "window_ms", "witness_follow_ticks",
}
IN_SCOL = ["logical_id", "parent_id", "cat", "class_name", "slot_name"]
IN_NCOL = ["req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"]
WIRE_CAP = 3500


# ---------------------------------------------------------------------------------------------------- helpers e2e
def _args():
    return argparse.Namespace(
        build="offline",
        both=False,
        evaluate_only=False,
        fault=None,
        pbo=None,
        peer_timeout=None,
        server_profile=None,
        client_profile=None,
        hold_ms=gate_core.DEFAULT_HOLD_MS,
        lease_ms=gate_core.DEFAULT_LEASE_MS,
        ttl_ms=gate_core.DEFAULT_TTL_MS,
        retry_ms=gate_core.DEFAULT_RETRY_MS,
        seed=gate_core.DEFAULT_SEED,
    )


def _issue(ctx, verb, strs=None, nums=None, **kw):
    payload = wire.pack_payload(scalars_str=strs or {}, scalars_num=nums or {})
    return f03_common.issue_one(ctx, "server", verb, payload, **kw)


def _status_epoch(ctx):
    out = _issue(ctx, "per_status")
    assert out.status == "done", out
    return str(out.payload["str"]["server_epoch"])


def _wait_terminal(ctx, job_id, timeout_s=90.0):
    deadline = time.monotonic() + timeout_s
    state = ""
    while time.monotonic() < deadline:
        out = _issue(ctx, "job_read", {"job": job_id}, {"page_n": 0.0})
        if out.status != "done":
            return out.status + "/" + out.reason
        state = str(out.payload["str"].get("state") or "")
        if state in f03_common.TERMINAL_JOB_STATES:
            return state
        time.sleep(0.02)
    return "timeout:" + state


def _free(ctx, job_id):
    out = _issue(ctx, "job_free", {"job": job_id})
    assert out.status == "done", out


def _read_all(ctx, job_id):
    return f03_common.read_job_pages(ctx, "server", job_id, timeout_ms=30000)


def _cols(pages):
    p0 = pages["outcomes"][0].payload
    return list(p0["ncol"]), list(p0["scol"])


def _census(ctx, tag, radius, select_all=None, include_dir=0, center=CENTER, free=True):
    nums = {
        "center_x_m": float(center[0]),
        "center_z_m": float(center[1]),
        "radius_m": float(radius),
        "include_director_b": float(include_dir),
    }
    if select_all is not None:
        nums["select_all_entityai_b"] = float(select_all)
    out = _issue(ctx, "per_census_start", {"area_tag": tag}, nums)
    if out.status != "done":
        return out, None, ""
    job_id = str(out.payload["str"]["job"])
    state = _wait_terminal(ctx, job_id)
    pages = _read_all(ctx, job_id) if state in f03_common.TERMINAL_JOB_STATES else None
    if free:
        _free(ctx, job_id)
    return out, pages, state


def _spawn(ctx, tag, mode, cname, x=6180.0, z=7650.0, target_net_id=None, target_scene="", target_parent=""):
    strs = {
        "tag": tag,
        "mode": mode,
        "class_name": cname,
        "child_cargo_class": "",
        "target_scene_id": target_scene,
        "target_parent_id": target_parent,
    }
    if target_net_id is not None:
        strs["target_net_id"] = target_net_id
    return _issue(ctx, "per_spawn_raw", strs, {"x_m": x, "z_m": z, "yaw_deg": 30.0, "health_mark_ratio": 0.5})


def _witness_nums(radius=115.0, window_ms=1500.0, k=None, center=CENTER):
    nums = {
        "center_x_m": float(center[0]),
        "center_z_m": float(center[1]),
        "radius_m": float(radius),
        "window_ms": float(window_ms),
    }
    if k is not None:
        nums["witness_follow_ticks"] = float(k)
    return nums


def _apply_scene(ctx, epoch, scene_id, n_rows):
    rows = []
    for i in range(n_rows):
        rows.append({
            "logical_id": "r%d" % i,
            "parent_id": "",
            "cat": "prop",
            "class_name": "Barrel_Yellow",
            "slot_name": "",
            "req_x_m": 6120.0 + float(i * 3),
            "req_z_m": 7600.0 + float(i * 2),
            "req_yaw_deg": 0.0,
            "health_mark_ratio": 0.5,
            "must_vanish_b": 1.0,
        })
    payload = wire.pack_payload(
        scalars_str={"scene_id": scene_id, "scene_op_id": scene_id + "-op", "expect_epoch": epoch, "q9_pathway": "a"},
        scalars_num={"gen_n": 1.0},
        num_cols=IN_NCOL,
        str_cols=IN_SCOL,
        row_dicts=rows,
    )
    return f03_common.issue_one(ctx, "server", "per_apply_scene", payload)


class _E2EBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = Path(tempfile.mkdtemp(prefix="dsbx-ext-f2-"))
        cls.ctx = f03_common.PartContext(
            base_dir=cls._tmp, part_name="run", spike_id="F2-ext", args=_args(), argv=[],
        )
        cls.ctx.open()
        if cls.ctx.startup_reason is not None:
            reason = cls.ctx.startup_reason
            cls.ctx.close()
            shutil.rmtree(cls._tmp, ignore_errors=True)
            raise unittest.SkipTest("peers falsos no arrancan: " + str(reason))

    @classmethod
    def tearDownClass(cls):
        try:
            cls.ctx.close()
        finally:
            shutil.rmtree(cls._tmp, ignore_errors=True)

    def setUp(self):
        out = _issue(self.ctx, "per_cleanup_qa")
        self.assertEqual(out.status, "done", out)


# ---------------------------------------------------------------------------------------- 1. censo select_all
class CensusSelectAllE2E(_E2EBase):
    def test_mode1_good_case_rows_columns_and_surface(self):
        foreign = _spawn(self.ctx, "f_ground", "foreign_ground", "Barrel_Yellow", 6180.0, 7650.0)
        self.assertEqual(foreign.status, "done", foreign)
        inbox = _spawn(self.ctx, "f_box", "foreign_in_container", "Rag", target_net_id="1:50")
        self.assertEqual(inbox.status, "done", inbox)

        start, pages, state = _census(self.ctx, "all", 115.0, select_all=1)
        self.assertEqual(start.status, "done", start)
        self.assertEqual(state, "done")
        ncol, scol = _cols(pages)
        # Columnas: las de siempre y surface_y_m, la ultima.
        self.assertEqual(ncol, CENSUS_NCOL_MODE0 + ["surface_y_m"])
        self.assertEqual(scol, CENSUS_SCOL)
        self.assertEqual(start.payload["str"]["resource"], "per_census")
        self.assertEqual(int(start.payload["num"]["rows_captured_n"]), pages["rows_total_n"])
        self.assertEqual(start.payload["num"]["radius_m"], 115.0)

        by_class = {}
        for row in pages["rows"]:
            by_class.setdefault(row["class_name"], []).append(row)
        # Edificios y objetos del mapa que S-persist no registra ni lista: ahora entran.
        self.assertIn("Land_Mil_Barracks1", by_class)
        self.assertIn("Land_Garage_Row", by_class)
        self.assertEqual(by_class["Land_Mil_Barracks1"][0]["net_id"], "0:0")
        self.assertEqual(by_class["Zmbf_PoliceCopBlue"][0]["ai_agent_b"], 1.0)
        self.assertEqual({r["own_b"] for r in pages["rows"]}, {0.0})  # S-persist no registra nada de esto
        # Raices: parent_net_id vacio y loc_kind ground. Inventario: padre inmediato real.
        for cname in ("Barrel_Blue", "WoodenCrate", "OffroadHatchback", "Barrel_Yellow"):
            root = by_class[cname][0]
            self.assertEqual(root["parent_net_id"], "", cname)
            self.assertEqual(root["loc_kind"], "ground", cname)
        rag_rows = {r["net_id"]: r for r in by_class["Rag"]}
        self.assertEqual(rag_rows["1:51"]["parent_net_id"], "1:50")
        self.assertEqual(rag_rows["1:51"]["parent_class"], "Barrel_Blue")
        self.assertEqual(rag_rows["1:51"]["loc_kind"], "cargo")
        self.assertEqual(rag_rows["1:51"]["slot_name"], "Cargo:0:0:0")
        new_rag = rag_rows[str(inbox.payload["str"]["net_id"])]
        self.assertEqual(new_rag["parent_net_id"], "1:50")
        self.assertEqual(new_rag["loc_kind"], "cargo")
        self.assertEqual(new_rag["own_b"], 0.0)
        apple = by_class["Apple"][0]  # anidado: Apple dentro de Pot dentro de WoodenCrate
        self.assertEqual(apple["parent_net_id"], "1:53")
        self.assertEqual(apple["parent_class"], "Pot")
        self.assertEqual(by_class["Pot"][0]["parent_net_id"], "1:52")
        wheel = by_class["HatchbackWheel"][0]
        self.assertEqual(wheel["loc_kind"], "attachment")
        self.assertEqual(wheel["slot_name"], "Wheel_1_1")
        self.assertEqual(wheel["parent_net_id"], "1:55")
        # El barril a 120 m queda fuera de un disco de 115 m; el lejano tambien.
        self.assertNotIn("Barrel_Green", by_class)
        self.assertNotIn("Barrel_Red", by_class)
        # surface_y_m es SurfaceY(pos_x_m, pos_z_m) en todas las filas y no es constante.
        ys = set()
        for row in pages["rows"]:
            self.assertAlmostEqual(
                row["surface_y_m"], fake_ext_persist._surface_y(row["pos_x_m"], row["pos_z_m"]), places=9,
            )
            ys.add(round(row["surface_y_m"], 6))
        self.assertGreater(len(ys), 3)
        # El director no entra (include_director_b = 0).
        self.assertEqual([r for r in pages["rows"] if r["owner_uid"]], [])

    def test_mode1_include_director_and_radius_120(self):
        _o, pages, state = _census(self.ctx, "dir", 120.0, select_all=1, include_dir=1)
        self.assertEqual(state, "done")
        owners = [r for r in pages["rows"] if r["owner_uid"] == fake_ext_persist.DIRECTOR_UID]
        self.assertEqual(sorted(r["class_name"] for r in owners), ["Apple", "Jeans_Blue"])
        # 120 m exactos es valido y el barril a 120 m entra.
        self.assertIn("Barrel_Green", [r["class_name"] for r in pages["rows"]])

    def test_mode0_columns_and_rows_unchanged(self):
        _spawn(self.ctx, "m0", "foreign_ground", "Barrel_Yellow", 6180.0, 7650.0)
        _o1, pages_default, st1 = _census(self.ctx, "d", 115.0)
        _o2, pages_zero, st2 = _census(self.ctx, "z", 115.0, select_all=0)
        self.assertEqual((st1, st2), ("done", "done"))
        for pages in (pages_default, pages_zero):
            ncol, scol = _cols(pages)
            self.assertEqual(ncol, CENSUS_NCOL_MODE0)
            self.assertEqual(scol, CENSUS_SCOL)
            self.assertNotIn("surface_y_m", pages["rows"][0])
        self.assertEqual(pages_default["rows"], pages_zero["rows"])
        # El mapa simulado no sale en el modo de S-persist.
        self.assertEqual([r["class_name"] for r in pages_zero["rows"]], ["Barrel_Yellow"])
        # Sin tope de radio con 0: S-persist usa discos grandes.
        _o3, pages_big, st3 = _census(self.ctx, "big", 5000.0, select_all=0)
        self.assertEqual(st3, "done")
        self.assertEqual(_cols(pages_big)[0], CENSUS_NCOL_MODE0)

    def test_mode1_rejections_have_no_effect(self):
        for radius in (0.0, -5.0, 120.5, 121.0, 5000.0):
            out, _p, _s = _census(self.ctx, "bad", radius, select_all=1)
            self.assertEqual((out.status, out.reason), ("rejected", "bad_args"), radius)
        out, _p, _s = _census(self.ctx, "bad", 115.0, select_all=2)
        self.assertEqual((out.status, out.reason), ("rejected", "bad_args"))
        out, _p, _s = _census(self.ctx, "bad", 115.0, select_all=0.5)
        self.assertEqual((out.status, out.reason), ("rejected", "bad_args"))
        # Sin efectos: no quedo ningun trabajo vivo (un censo valido no da busy) y el recurso esta libre.
        out, pages, state = _census(self.ctx, "ok", 115.0, select_all=1)
        self.assertEqual(out.status, "done", out)
        self.assertEqual(state, "done")
        self.assertGreater(pages["rows_total_n"], 5)


# --------------------------------------------------------------------------------------- 2. target_net_id
class SpawnTargetNetIdE2E(_E2EBase):
    def _children_of(self, parent_net_id):
        _o, pages, state = _census(self.ctx, "kids", 115.0, select_all=1)
        self.assertEqual(state, "done")
        return [r for r in pages["rows"] if r["parent_net_id"] == parent_net_id], pages

    def test_good_case_by_census_net_id(self):
        crate = _spawn(self.ctx, "crate", "foreign_ground", "WoodenCrate", 6160.0, 7660.0)
        self.assertEqual(crate.status, "done", crate)
        # El net_id del contenedor sale del censo, como hara F2.
        _o, pages, _s = _census(self.ctx, "find", 115.0, select_all=1)
        crate_rows = [r for r in pages["rows"] if r["class_name"] == "WoodenCrate" and r["own_b"] == 0.0 and r["net_id"] != "1:52"]
        self.assertEqual(len(crate_rows), 1)
        target = crate_rows[0]["net_id"]
        self.assertEqual(target, crate.payload["str"]["net_id"])

        res = _spawn(self.ctx, "foreign_item", "foreign_in_container", "Rag", target_net_id=target)
        self.assertEqual(res.status, "done", res)
        s = res.payload["str"]
        self.assertEqual(s["spawn_status"], "ok")
        self.assertEqual(s["obs_loc_kind"], "cargo")
        self.assertEqual(s["obs_parent_net_id"], target)
        self.assertEqual(s["obs_slot_name"], "Cargo:0:0:0")
        self.assertEqual(sorted(res.payload["num"]), sorted([
            "pos_x_m", "pos_y_m", "pos_z_m", "yaw_deg", "pitch_deg", "roll_deg", "max_hp", "health_hp",
            "child_count_n", "tick_ms", "frame",
        ]))
        kids, _pages = self._children_of(target)
        self.assertEqual([k["net_id"] for k in kids], [s["net_id"]])
        self.assertEqual(kids[0]["loc_kind"], "cargo")

    def test_good_case_into_map_container_second_slot(self):
        res = _spawn(self.ctx, "into_barrel", "foreign_in_container", "Rag", target_net_id="1:50")
        self.assertEqual((res.status, res.payload["str"]["obs_parent_net_id"]), ("done", "1:50"))
        self.assertEqual(res.payload["str"]["obs_slot_name"], "Cargo:0:0:1")

    def test_target_not_found_has_no_effect(self):
        before, pages_before = self._children_of("1:50")
        for bad in ("1:9999", "0:0", "7:7"):
            res = _spawn(self.ctx, "nf", "foreign_in_container", "Rag", target_net_id=bad)
            self.assertEqual((res.status, res.reason), ("rejected", "target_not_found"), bad)
        after, pages_after = self._children_of("1:50")
        self.assertEqual(pages_before["rows_total_n"], pages_after["rows_total_n"])
        self.assertEqual(len(before), len(after))
        # Un borrado previo tambien da target_not_found.
        crate = _spawn(self.ctx, "gone", "foreign_ground", "WoodenCrate", 6160.0, 7660.0)
        self.assertEqual(_issue(self.ctx, "per_cleanup_qa").status, "done")
        res = _spawn(self.ctx, "nf2", "foreign_in_container", "Rag", target_net_id=crate.payload["str"]["net_id"])
        self.assertEqual((res.status, res.reason), ("rejected", "target_not_found"))

    def test_malformed_target_is_bad_args(self):
        for bad in ("abc", "1:", ":2", "1:2:3", "1;2", "1:x", "99999999999:1"):
            res = _spawn(self.ctx, "ba", "foreign_in_container", "Rag", target_net_id=bad)
            self.assertEqual((res.status, res.reason), ("rejected", "bad_args"), bad)

    def test_no_cargo_space_has_no_effect(self):
        # Sin cargo (un coche) y con el cargo lleno (Pot: 2 huecos, ya lleva una manzana).
        res = _spawn(self.ctx, "nc1", "foreign_in_container", "Rag", target_net_id="1:55")
        self.assertEqual((res.status, res.reason), ("rejected", "no_cargo_space"))
        ok = _spawn(self.ctx, "fill", "foreign_in_container", "Rag", target_net_id="1:53")
        self.assertEqual(ok.status, "done", ok)
        kids_before, pages_before = self._children_of("1:53")
        res = _spawn(self.ctx, "nc2", "foreign_in_container", "Rag", target_net_id="1:53")
        self.assertEqual((res.status, res.reason), ("rejected", "no_cargo_space"))
        kids_after, pages_after = self._children_of("1:53")
        self.assertEqual(pages_before["rows_total_n"], pages_after["rows_total_n"])
        self.assertEqual(sorted(k["net_id"] for k in kids_before), sorted(k["net_id"] for k in kids_after))

    def test_old_path_by_scene_and_empty_target_unchanged(self):
        res = _spawn(self.ctx, "old", "foreign_in_container", "Rag", target_scene="nope", target_parent="nope")
        self.assertEqual((res.status, res.reason), ("rejected", "unknown_entity"))
        res = _spawn(self.ctx, "old2", "foreign_in_container", "Rag", target_net_id="", target_scene="nope", target_parent="nope")
        self.assertEqual((res.status, res.reason), ("rejected", "unknown_entity"))


# -------------------------------------------------------------------------------------------- 3. el testigo
class WitnessE2E(_E2EBase):
    def _start(self, nums, tag="w"):
        return _issue(self.ctx, "per_witness_start", {"witness_tag": tag}, nums)

    def _finish(self, start):
        job_id = str(start.payload["str"]["job"])
        state = _wait_terminal(self.ctx, job_id)
        pages = _read_all(self.ctx, job_id)
        _free(self.ctx, job_id)
        return state, pages

    def test_good_case_trajectory(self):
        start = self._start(_witness_nums(window_ms=1500.0), tag="w_good")
        self.assertEqual(start.status, "done", start)
        s = start.payload["str"]
        self.assertEqual(
            {k: s[k] for k in ("state", "resource", "witness_tag")},
            {"state": "running", "resource": "per_witness", "witness_tag": "w_good"},
        )
        self.assertEqual(set(s), {"job", "state", "resource", "witness_tag", "server_epoch"})
        self.assertEqual(s["server_epoch"], _status_epoch(self.ctx))
        n = start.payload["num"]
        self.assertEqual(set(n), WITNESS_START_NK)
        self.assertEqual((n["radius_m"], n["window_ms"], n["witness_follow_ticks"]), (115.0, 1500.0, 3.0))
        self.assertEqual((n["center_x_m"], n["center_z_m"]), CENTER)

        ground = _spawn(self.ctx, "wg", "foreign_ground", "Barrel_Yellow", 6180.0, 7650.0)
        boxed = _spawn(self.ctx, "wb", "foreign_in_container", "Rag", target_net_id="1:50")
        outside = _spawn(self.ctx, "wo", "foreign_ground", "Barrel_Blue", 6500.0, 7643.0)
        for r in (ground, boxed, outside):
            self.assertEqual(r.status, "done", r)

        state, pages = self._finish(start)
        self.assertEqual(state, "done")
        self.assertEqual(pages["reason"], "")
        ncol, scol = _cols(pages)
        self.assertEqual(ncol, WITNESS_NCOL)
        self.assertEqual(scol, WITNESS_SCOL)

        rows = pages["rows"]
        self.assertEqual(len(rows), 2 * (1 + 3))  # dos entidades dentro del radio, la de fuera no
        by_net = {}
        for row in rows:
            by_net.setdefault(row["net_id"], []).append(row)
        self.assertEqual(set(by_net), {ground.payload["str"]["net_id"], boxed.payload["str"]["net_id"]})
        for net_id, samples in by_net.items():
            self.assertEqual([r["sample_idx"] for r in samples], [0.0, 1.0, 2.0, 3.0], net_id)
            self.assertEqual({r["alive_b"] for r in samples}, {1.0})
            self.assertEqual({r["ai_agent_b"] for r in samples}, {0.0})
            ticks = [r["tick_ms"] for r in samples]
            frames = [r["frame"] for r in samples]
            self.assertEqual(ticks, sorted(ticks))
            self.assertEqual(frames, sorted(frames))
            self.assertEqual(len(set(frames[1:])), 3)  # cada muestra de seguimiento es un tick de servidor distinto
            self.assertLess(frames[0], frames[1])
            self.assertEqual(len({r["pos_x_m"] for r in samples}), 1)
        g = by_net[ground.payload["str"]["net_id"]]
        self.assertEqual(g[0]["class_name"], "Barrel_Yellow")
        self.assertEqual(g[0]["parent_net_id"], "")
        self.assertEqual((g[0]["pos_x_m"], g[0]["pos_z_m"]), (6180.0, 7650.0))
        self.assertAlmostEqual(g[0]["pos_y_m"], fake_ext_persist._surface_y(6180.0, 7650.0), places=9)
        self.assertEqual(g[0]["yaw_deg"], 30.0)
        b = by_net[boxed.payload["str"]["net_id"]]
        self.assertEqual(b[0]["class_name"], "Rag")
        self.assertEqual(b[0]["parent_net_id"], "1:50")
        # El trabajo dura al menos window_ms y no antes de tomar las K muestras de la ultima entidad.
        elapsed = pages["num"]["end_tick_ms"] - pages["num"]["start_tick_ms"]
        self.assertGreaterEqual(elapsed, 1500.0 - 1.0)

    def test_follow_ticks_custom_k(self):
        start = self._start(_witness_nums(window_ms=800.0, k=2), tag="w_k2")
        self.assertEqual(start.payload["num"]["witness_follow_ticks"], 2.0)
        one = _spawn(self.ctx, "k2", "foreign_ground", "Barrel_Yellow", 6180.0, 7650.0)
        state, pages = self._finish(start)
        self.assertEqual(state, "done")
        self.assertEqual([r["sample_idx"] for r in pages["rows"]], [0.0, 1.0, 2.0])
        self.assertEqual({r["net_id"] for r in pages["rows"]}, {one.payload["str"]["net_id"]})

    def test_off_by_default_and_after_end(self):
        before = _spawn(self.ctx, "pre", "foreign_ground", "Barrel_Yellow", 6180.0, 7650.0)
        start = self._start(_witness_nums(window_ms=300.0, k=1), tag="w_empty")
        state, pages = self._finish(start)
        self.assertEqual(state, "done")
        self.assertEqual(pages["rows"], [])  # lo creado antes (o con el testigo apagado) no sale
        after = _spawn(self.ctx, "post", "foreign_ground", "Barrel_Yellow", 6181.0, 7650.0)
        start2 = self._start(_witness_nums(window_ms=300.0, k=1), tag="w_empty2")
        state2, pages2 = self._finish(start2)
        self.assertEqual((state2, pages2["rows"]), ("done", []))
        self.assertEqual(before.status, "done")
        self.assertEqual(after.status, "done")

    def test_rejections_have_no_effect(self):
        good = _witness_nums()
        cases = {
            "radius 0": dict(good, radius_m=0.0),
            "radius neg": dict(good, radius_m=-1.0),
            "radius 120.5": dict(good, radius_m=120.5),
            "window 0": dict(good, window_ms=0.0),
            "window neg": dict(good, window_ms=-1.0),
            "window 600001": dict(good, window_ms=600001.0),
            "k 0": dict(good, witness_follow_ticks=0.0),
            "k 6": dict(good, witness_follow_ticks=6.0),
            "k 2.5": dict(good, witness_follow_ticks=2.5),
            "k -1": dict(good, witness_follow_ticks=-1.0),
        }
        for key in ("center_x_m", "center_z_m", "radius_m", "window_ms"):
            cases["sin " + key] = {k: v for k, v in good.items() if k != key}
        for label, nums in cases.items():
            out = self._start(nums, tag="bad")
            self.assertEqual((out.status, out.reason), ("rejected", "bad_args"), label)
        # Sin efectos: el recurso per_witness esta libre (no hay busy) y los extremos validos se aceptan.
        out = self._start(_witness_nums(radius=120.0, window_ms=200.0, k=5), tag="edge")
        self.assertEqual(out.status, "done")
        self.assertEqual(self._finish(out)[0], "done")
        out = self._start(_witness_nums(window_ms=600000.0, k=1), tag="edge2")  # el maximo se acepta; se para a mano
        self.assertEqual(out.status, "done")
        job_id = str(out.payload["str"]["job"])
        stop = _issue(self.ctx, "job_stop", {"job": job_id})
        self.assertEqual(stop.status, "done", stop)
        self.assertEqual(_wait_terminal(self.ctx, job_id), "stopped")
        _free(self.ctx, job_id)

    def test_exclusive_resource(self):
        first = self._start(_witness_nums(window_ms=1200.0, k=1), tag="w_first")
        self.assertEqual(first.status, "done", first)
        second = self._start(_witness_nums(window_ms=1200.0, k=1), tag="w_second")
        self.assertEqual((second.status, second.reason), ("rejected", "busy"))
        state, _pages = self._finish(first)
        self.assertEqual(state, "done")


# ----------------------------------------------------------------------------------------- 4. tope de filas
class RowsCapE2E(_E2EBase):
    """Cientos de operaciones: se llena el mundo simulado con per_apply_scene (12 raices por llamada, como el .c)."""

    def test_witness_then_census_rows_cap(self):
        epoch = _status_epoch(self.ctx)
        start = _issue(
            self.ctx, "per_witness_start", {"witness_tag": "cap"}, _witness_nums(window_ms=300000.0, k=1),
        )
        self.assertEqual(start.status, "done", start)
        job_id = str(start.payload["str"]["job"])
        created = 0
        scene_n = 0
        # 12 raices por llamada, 2 filas por entidad (muestra 0 y 1): el tope de 4096 filas salta a las 2048.
        while created <= 2100:
            out = _apply_scene(self.ctx, epoch, "cap%d" % scene_n, 12)
            self.assertEqual(out.status, "done", out)
            created += 12
            scene_n += 1
        state = _wait_terminal(self.ctx, job_id)
        self.assertEqual(state, "failed")
        pages = _read_all(self.ctx, job_id)
        self.assertEqual(pages["state"], "failed")
        self.assertEqual(pages["reason"], "rows_cap")
        self.assertEqual(pages["rows_total_n"], 4096)  # ni una mas, y el trabajo no aparenta haber acabado bien
        _free(self.ctx, job_id)
        # El gancho se apago solo: un testigo nuevo no hereda nada y el recurso esta libre.
        again = _issue(self.ctx, "per_witness_start", {"witness_tag": "again"}, _witness_nums(window_ms=200.0, k=1))
        self.assertEqual(again.status, "done", again)
        job2 = str(again.payload["str"]["job"])
        self.assertEqual(_wait_terminal(self.ctx, job2), "done")
        self.assertEqual(_read_all(self.ctx, job2)["rows"], [])
        _free(self.ctx, job2)

        # Censo select_all: con mas de 4096 filas en el disco acaba failed/rows_cap, sin truncar.
        while created < 4100:
            out = _apply_scene(self.ctx, epoch, "cap%d" % scene_n, 12)
            self.assertEqual(out.status, "done", out)
            created += 12
            scene_n += 1
        census, pages_c, state_c = _census(self.ctx, "cap", 115.0, select_all=1, free=False)
        self.assertEqual(census.status, "done", census)
        self.assertEqual(state_c, "failed")
        self.assertEqual(pages_c["reason"], "rows_cap")
        self.assertEqual(pages_c["rows_total_n"], 4096)
        _free(self.ctx, str(census.payload["str"]["job"]))


# ------------------------------------------------------------------------------------- en proceso (peer de pega)
class _StubPeer:
    def __init__(self):
        self.config = None
        self.inst = "epoch-stub"
        self.frame = 1
        self.now = 1000.0

    def local_ms(self):
        return self.now

    def lease_valid(self):
        return True

    def is_transport_connected(self):
        return True


def _make_ext(module=fake_ext_persist):
    peer = _StubPeer()
    jobs = fake_peer.JobMgr(peer)
    ext = module.PersistFakeExt()
    ext.init(peer, jobs)
    return peer, jobs, ext


def _call(ext, verb, strs=None, nums=None, rows=None, op_id="op-1"):
    op = {"op_id": op_id, "verb": verb, "qa_fault": ""}
    unpacked = {"str": dict(strs or {}), "num": dict(nums or {}), "rows": list(rows or [])}
    return ext.on_start_op(op, unpacked, None)


def _tick(peer, jobs, ext, dt_ms=33.0, n=1):
    for _ in range(n):
        peer.now += dt_ms
        peer.frame += 1
        jobs.tick_jobs(dt_ms / 1000.0, peer.now)
        ext.on_tick(dt_ms / 1000.0)


def _job_rows(jobs, job_id):
    job = jobs.jobs_by_id[job_id]
    n_nc, n_sc = len(job["ncol"]), len(job["scol"])
    out = []
    for i in range(job["rows_total"]):
        row = dict(zip(job["ncol"], job["ncell"][i * n_nc:(i + 1) * n_nc]))
        row.update(dict(zip(job["scol"], job["scell"][i * n_sc:(i + 1) * n_sc])))
        out.append(row)
    return out


class WitnessInProcess(unittest.TestCase):
    def setUp(self):
        self.peer, self.jobs, self.ext = _make_ext()

    def _start(self, window_ms=200.0, k=3, op_id="w1"):
        status, reason, _p = _call(
            self.ext, "per_witness_start", {"witness_tag": "t"},
            {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": 115.0, "window_ms": window_ms,
             "witness_follow_ticks": float(k)}, op_id=op_id,
        )
        self.assertEqual((status, reason), ("done", ""))
        return op_id

    def _new(self, cname="Barrel_Yellow", x=6180.0, z=7650.0):
        return self.ext._add_entity(
            net_id=self.ext._alloc_net_id(), class_name=cname, cat="raw", pos=(x, 100.0, z),
        )

    def test_entity_gone_gives_alive_zero_and_window_end_waits_for_k_samples(self):
        job_id = self._start(window_ms=200.0, k=3)
        t0 = self.peer.now
        ent = self._new()
        _tick(self.peer, self.jobs, self.ext)  # sample 0
        _tick(self.peer, self.jobs, self.ext)  # sample 1 (vivo)
        self.ext._delete_entity(ent)
        _tick(self.peer, self.jobs, self.ext)  # sample 2 (ya no existe)
        # La ventana vence, pero falta la muestra 3 de la ultima entidad capturada: sigue running.
        self.peer.now = t0 + 300.0
        self.assertEqual(self.jobs.get_state(job_id), "running")
        _tick(self.peer, self.jobs, self.ext, dt_ms=1.0)  # sample 3; ventana cerrada y sin seguimiento -> done
        self.assertEqual(self.jobs.get_state(job_id), "done")
        rows = _job_rows(self.jobs, job_id)
        self.assertEqual([r["sample_idx"] for r in rows], [0.0, 1.0, 2.0, 3.0])
        self.assertEqual([r["alive_b"] for r in rows], [1.0, 1.0, 0.0, 0.0])
        self.assertEqual({r["class_name"] for r in rows}, {"Barrel_Yellow"})
        self.assertEqual({(r["pos_x_m"], r["pos_z_m"]) for r in rows}, {(6180.0, 7650.0)})  # ultima posicion conocida
        self.assertIsNone(self.ext.witness)

    def test_follow_row_takes_position_of_that_tick(self):
        job_id = self._start(window_ms=500.0, k=2)
        ent = self._new()
        _tick(self.peer, self.jobs, self.ext)
        ent["pos"] = (6181.5, 100.0, 7651.5)  # el mod la desplaza antes del tick 1
        _tick(self.peer, self.jobs, self.ext)
        rows = _job_rows(self.jobs, job_id)
        self.assertEqual((rows[0]["pos_x_m"], rows[1]["pos_x_m"]), (6180.0, 6181.5))
        self.assertEqual((rows[0]["sample_idx"], rows[1]["sample_idx"]), (0.0, 1.0))

    def test_capture_after_window_end_and_outside_radius_are_ignored(self):
        job_id = self._start(window_ms=100.0, k=1)
        self._new("Barrel_Blue", 6500.0, 7643.0)  # fuera del radio
        self.peer.now += 101.0
        self._new("Barrel_Red", 6180.0, 7650.0)  # despues de vencer la ventana
        _tick(self.peer, self.jobs, self.ext)
        self.assertEqual(_job_rows(self.jobs, job_id), [])
        self.assertEqual(self.jobs.get_state(job_id), "done")

    def test_ending_by_any_cause_switches_the_hook_off(self):
        job_id = self._start(window_ms=60000.0, k=1)
        self.assertIsNotNone(self.ext.witness)
        self.jobs.end_job(job_id, "stopped", "")  # job_stop / shutdown / deadman acaban igual
        self.assertIsNone(self.ext.witness)
        self._new()
        self.assertEqual(self.jobs.jobs_by_id[job_id]["rows_total"], 0)

    def test_rows_cap_boundary_is_exact_and_never_silent(self):
        # K = 1: 2 filas por entidad. 2048 entidades -> 4096 filas justas (done); 2049 -> failed/rows_cap.
        for n, want_state, want_reason, want_rows in ((2048, "done", "", 4096), (2049, "failed", "rows_cap", 4096)):
            peer, jobs, ext = _make_ext()
            status, _r, _p = _call(
                ext, "per_witness_start", {"witness_tag": "cap"},
                {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": 115.0, "window_ms": 100.0,
                 "witness_follow_ticks": 1.0}, op_id="cap-%d" % n,
            )
            self.assertEqual(status, "done")
            for i in range(n):
                ext._add_entity(net_id="9:%d" % (1000 + i), class_name="Barrel_Yellow", cat="raw", pos=(6180.0, 100.0, 7650.0))
            _tick(peer, jobs, ext, dt_ms=33.0, n=5)
            job = jobs.jobs_by_id["cap-%d" % n]
            self.assertEqual((job["state"], job["reason"], job["rows_total"]), (want_state, want_reason, want_rows), n)
            self.assertIsNone(ext.witness)


class CensusCapInProcess(unittest.TestCase):
    def _census(self, ext, op_id, select_all=1, radius=115.0):
        nums = {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": radius, "include_director_b": 0.0,
                "select_all_entityai_b": float(select_all)}
        return _call(ext, "per_census_start", {"area_tag": "t"}, nums, op_id=op_id)

    def test_rows_cap_boundary(self):
        peer, jobs, ext = _make_ext()
        status, _r, _p = self._census(ext, "base")
        self.assertEqual(status, "done")
        base = jobs.jobs_by_id["base"]["rows_total"]
        self.assertGreaterEqual(base, 8)
        jobs.end_job("base", "done", "")
        jobs.dispatch_core_verb({"verb": "job_free"}, {"str": {"job": "base"}, "num": {}})
        for extra, want_state, want_reason in ((4096 - base, "done", ""), (4097 - base, "failed", "rows_cap")):
            peer, jobs, ext = _make_ext()
            for i in range(extra):
                ext._add_entity(net_id="9:%d" % (1000 + i), class_name="Barrel_Yellow", cat="raw", pos=(6180.0, 100.0, 7650.0))
            status, _r, _p = self._census(ext, "cap")
            self.assertEqual(status, "done")
            _tick(peer, jobs, ext, n=12)
            job = jobs.jobs_by_id["cap"]
            self.assertEqual((job["state"], job["reason"], job["rows_total"]), (want_state, want_reason, 4096), extra)

    def test_mode1_rejections_leave_no_job(self):
        peer, jobs, ext = _make_ext()
        for radius in (0.0, 120.01, 500.0):
            self.assertEqual(self._census(ext, "r%s" % radius, radius=radius)[:2], ("rejected", "bad_args"))
        self.assertEqual(jobs.jobs_by_id, {})
        self.assertEqual(jobs.held_resources, {})


class Mode0IdentityInProcess(unittest.TestCase):
    """Con select_all_entityai_b = 0 (o ausente), filas y columnas son identicas a las del fake anterior al PR."""

    GOLDEN_SHA256 = "86b5638988c528a689396e1590f7d2885bea6449899dca2b9f2a1ede3b5c5b58"

    @staticmethod
    def _scenario(module, explicit_zero):
        peer, jobs, ext = _make_ext(module)
        trace = []

        def run(verb, strs=None, nums=None, rows=None, op_id="x"):
            res = _call(ext, verb, strs, nums, rows, op_id=op_id)
            trace.append([verb, res[0], res[1], res[2]])
            return res

        rows = [
            {"logical_id": "p1", "parent_id": "", "cat": "prop", "class_name": "Barrel_Blue", "slot_name": "",
             "req_x_m": 4500.0, "req_z_m": 10200.0, "req_yaw_deg": 10.0, "health_mark_ratio": 0.5, "must_vanish_b": 1.0},
            {"logical_id": "c1", "parent_id": "p1", "cat": "prop", "class_name": "Rag", "slot_name": "Cargo",
             "req_x_m": 0.0, "req_z_m": 0.0, "req_yaw_deg": 0.0, "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
            {"logical_id": "z1", "parent_id": "", "cat": "infected", "class_name": "Zmbf_PoliceCopBlue", "slot_name": "",
             "req_x_m": 4520.0, "req_z_m": 10210.0, "req_yaw_deg": 0.0, "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
        ]
        run("per_apply_scene", {"scene_id": "scene_a", "scene_op_id": "o1", "expect_epoch": peer.inst, "q9_pathway": "a"},
            {"gen_n": 1.0}, rows, op_id="apply")
        run("per_spawn_raw", {"tag": "g", "mode": "foreign_ground", "class_name": "Barrel_Yellow"},
            {"x_m": 4510.0, "z_m": 10205.0, "yaw_deg": 5.0, "health_mark_ratio": 0.5}, op_id="sp1")
        run("per_spawn_raw", {"tag": "c", "mode": "foreign_in_container", "class_name": "Apple",
                              "target_scene_id": "scene_a", "target_parent_id": "p1"},
            {"health_mark_ratio": 0.25}, op_id="sp2")
        for i, (radius, inc) in enumerate(((60.0, 1.0), (5000.0, 0.0), (40.0, 0.0))):
            nums = {"center_x_m": 4500.0, "center_z_m": 10200.0, "radius_m": radius, "include_director_b": inc}
            if explicit_zero:
                nums["select_all_entityai_b"] = 0.0
            op_id = "census%d" % i
            status, reason, payload = run("per_census_start", {"area_tag": "area_a"}, nums, op_id=op_id)
            _tick(peer, jobs, ext, n=12)
            job = jobs.jobs_by_id[op_id]
            trace.append(["job", job["state"], job["reason"], job["ncol"], job["scol"], job["ncell"], job["scell"]])
            jobs.end_job(op_id, "done", "")
            jobs.dispatch_core_verb({"verb": "job_free"}, {"str": {"job": op_id}, "num": {}})
        return json.dumps(trace, sort_keys=True)

    def test_identical_regardless_of_explicit_zero(self):
        self.assertEqual(self._scenario(fake_ext_persist, False), self._scenario(fake_ext_persist, True))

    def test_columns_and_rows_match_pre_pr_golden(self):
        out = self._scenario(fake_ext_persist, False)
        self.assertNotIn("surface_y_m", out)
        self.assertNotIn("Land_Mil_Barracks1", out)  # el mapa simulado solo lo ve select_all_entityai_b = 1
        digest = hashlib.sha256(out.encode("utf-8")).hexdigest()
        self.assertEqual(digest, self.GOLDEN_SHA256)

    def test_identical_to_fake_at_baseline_commit(self):
        try:
            proc = subprocess.run(
                ["git", "-c", "core.autocrlf=false", "show", BASELINE_COMMIT + ":DayZSandbox_dev/qa/fake_ext_persist.py"],
                cwd=str(REPO_ROOT), capture_output=True, check=False,
            )
        except OSError as exc:
            self.skipTest("git no disponible: %s" % exc)
        if proc.returncode != 0:
            self.skipTest("commit base %s no disponible en este clon" % BASELINE_COMMIT)
        old = types.ModuleType("fake_ext_persist_baseline")
        exec(compile(proc.stdout.decode("utf-8"), "fake_ext_persist@" + BASELINE_COMMIT, "exec"), old.__dict__)
        self.assertEqual(self._scenario(old, False), self._scenario(fake_ext_persist, False))
        self.assertEqual(self._scenario(old, False), self._scenario(fake_ext_persist, True))


class WirePageSizeInProcess(unittest.TestCase):
    """Cada pagina (5 filas) con filas del peor caso realista cabe por debajo de 3500 B en el cable."""

    LONG = "Land_Construction_Building_Houseblock_A1"  # 41 caracteres
    NET = "2147483647:2147483647"  # net_id de 20 cifras (21 caracteres con el separador)

    def _page_bytes(self, ncol, scol, row_fn, float_fn):
        peer = _StubPeer()
        jobs = fake_peer.JobMgr(peer)
        ext = fake_ext_persist.PersistFakeExt()
        status = jobs.start_job(ext, "job-0123456789abcdef", "per_x", list(ncol), list(scol), 5, 4096, 900000.0, "stop")
        self.assertEqual(status, "")
        for i in range(5):
            nvals, svals = row_fn(i, float_fn)
            self.assertTrue(jobs.append_row("job-0123456789abcdef", nvals, svals))
        jobs.end_job("job-0123456789abcdef", "done", "")
        code, _r, payload = jobs.dispatch_core_verb(
            {"verb": "job_read"}, {"str": {"job": "job-0123456789abcdef"}, "num": {"page_n": 0.0}},
        )
        self.assertEqual(code, "done")
        body = {
            "done_ms": 99999999.999, "dup": False, "frame_done": 999999, "frame_recv": 999999,
            "op_id": "abcdef012345-99999", "read": fake_peer._new_payload_read(payload),
            "reason": "", "recv_ms": 99999999.999, "status": "done",
        }
        return len(wire.result_wire_bytes(body))

    @staticmethod
    def _float_enforce(v):
        return round(v, 5)  # el JsonSerializer de Enforce escribe como mucho unos 5 decimales

    @staticmethod
    def _float_repr_worst(v):
        return v + 1.0 / 3.0  # 16-17 cifras significativas, mas largo que lo que escribe Enforce

    def _census_row(self, i, ffn):
        svals = [self.LONG, "attachment", self.LONG, self.NET, "Cargo:12:34:56", "", "", self.NET, "2147483647:2147483647:2147483647:2147483647"]
        base = [0.0, 1.0, 1.0, 0.0, 6170.123456789 + i, 188.123456789, 7643.987654321, 359.123456, -12.345678, 179.987654,
                1234567.5, 1234567.25, 12.0, 123456789.123, 188.1234567]
        return [ffn(v) for v in base], svals

    def _witness_row(self, i, ffn):
        svals = [self.LONG, self.NET, self.NET]
        base = [3.0, 6170.123456789 + i, 188.123456789, 7643.987654321, 359.123456, 123456789.123456, 999999.0, 0.0, 1.0]
        return [ffn(v) for v in base], svals

    def test_census_mode1_page_under_cap(self):
        size = self._page_bytes(CENSUS_NCOL_MODE0 + ["surface_y_m"], CENSUS_SCOL, self._census_row, self._float_enforce)
        self.assertLess(size, WIRE_CAP, size)
        # Cota estricta con floats de Python de 17 cifras (mas largos que los de Enforce): solo se informa.
        strict = self._page_bytes(CENSUS_NCOL_MODE0 + ["surface_y_m"], CENSUS_SCOL, self._census_row, self._float_repr_worst)
        self.assertLess(strict, WIRE_CAP, strict)

    def test_witness_page_under_cap(self):
        size = self._page_bytes(WITNESS_NCOL, WITNESS_SCOL, self._witness_row, self._float_enforce)
        self.assertLess(size, WIRE_CAP, size)
        strict = self._page_bytes(WITNESS_NCOL, WITNESS_SCOL, self._witness_row, self._float_repr_worst)
        self.assertLess(strict, WIRE_CAP, strict)

    def test_start_reads_under_cap(self):
        peer, jobs, ext = _make_ext()
        for verb, strs, nums in (
            ("per_witness_start", {"witness_tag": "w" * 60},
             {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": 115.0, "window_ms": 600000.0, "witness_follow_ticks": 5.0}),
            ("per_census_start", {"area_tag": "a" * 60},
             {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": 115.0, "select_all_entityai_b": 1.0}),
        ):
            status, _r, payload = _call(ext, verb, strs, nums, op_id="s-" + verb)
            self.assertEqual(status, "done")
            body = {"done_ms": 99999999.999, "dup": False, "frame_done": 999999, "frame_recv": 999999,
                    "op_id": "abcdef012345-99999", "read": fake_peer._new_payload_read(payload),
                    "reason": "", "recv_ms": 99999999.999, "status": "done"}
            self.assertLess(len(wire.result_wire_bytes(body)), WIRE_CAP)


# ------------------------------------------------------------------------------------------- 5. estaticas (.c)
def _code(path):
    text = Path(path).read_bytes().decode("utf-8")
    return text, tps._strip_comments(text, blank_strings=False)


def _block_after(code, header_regex):
    """Cuerpo (entre llaves) del primer bloque cuyo encabezado casa con header_regex."""
    m = re.search(header_regex, code)
    if not m:
        return None
    start = code.index("{", m.end() - 1) if code[m.end() - 1] != "{" else m.end() - 1
    depth = 0
    for i in range(start, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[start + 1:i]
    return None


def _statements(body):
    """Primeras sentencias de un cuerpo: separa por ; a nivel 0 (un if sin llaves cuenta con su consecuente)."""
    out = []
    cur = []
    depth = 0
    for ch in body:
        cur.append(ch)
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ";" and depth == 0:
            out.append(re.sub(r"\s+", " ", "".join(cur)).strip())
            cur = []
    return out


def _inserted(code, member):
    return re.findall(r"\b" + re.escape(member) + r'\.Insert\("([^"]+)"\)', code)


class StaticWitnessHookTests(unittest.TestCase):
    def setUp(self):
        self.text, self.code = _code(WITNESS_C)

    def test_file_is_lf_utf8_without_bom(self):
        raw = WITNESS_C.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        raw.decode("utf-8")

    def test_modded_entityai_eeinit_super_first_then_bool_check(self):
        self.assertEqual(len(re.findall(r"\bmodded\s+class\s+EntityAI\b", self.code)), 1)
        body = _block_after(self.code, r"override\s+void\s+EEInit\s*\(\s*\)\s*\{")
        self.assertIsNotNone(body)
        stmts = _statements(body)
        self.assertEqual(stmts[0], "super.EEInit();")
        # Segunda sentencia: comprobar el bool estatico y salir si esta apagado.
        self.assertRegex(stmts[1], r"^if \(!DSBX_QA_Witness\.s_On\) return;$")
        self.assertEqual(stmts[2], "DSBX_QA_Witness.Capture(this);")
        self.assertEqual(len(stmts), 3)

    def test_switch_is_static_and_off_by_default(self):
        self.assertRegex(self.code, r"static\s+bool\s+s_On\s*=\s*false\s*;")

    def test_buffer_is_bounded_and_filtered_by_radius_and_window(self):
        self.assertRegex(self.code, r"BUFFER_MAX\s*=\s*4097")
        cap_body = _block_after(self.code, r"static\s+void\s+Capture\s*\(\s*EntityAI\s+ent\s*\)\s*\{")
        self.assertIn("s_Radius", cap_body)
        self.assertIn("s_EndTickMs", cap_body)
        self.assertIn("GetNetworkID", cap_body)
        self.assertIn("GetHierarchyParent", cap_body)

    def test_only_the_server_probe_can_switch_it_on(self):
        _t, persist = _code(PERSIST_C)
        calls = re.findall(r"DSBX_QA_Witness\.Enable\s*\(", persist)
        self.assertEqual(len(calls), 1)
        enable_owner = _block_after(persist, r"protected\s+void\s+HandleWitnessStart\s*\([^)]*\)\s*\{")
        self.assertIn("DSBX_QA_Witness.Enable(", enable_owner)
        self.assertEqual(len(re.findall(r"\bEnable\s*\(", self.code)), 1)  # solo la definicion en el fichero de 4_World


class StaticPersistExtensionTests(unittest.TestCase):
    def setUp(self):
        self.text, self.code = _code(PERSIST_C)

    def test_three_verbs_and_args_are_present(self):
        handles = _block_after(self.code, r"override\s+bool\s+Handles\s*\([^)]*\)\s*\{")
        self.assertIn('verb == "per_witness_start"', handles)
        start_op = _block_after(self.code, r"override\s+void\s+OnStartOp\s*\([^)]*\)\s*\{")
        self.assertIn("HandleWitnessStart(op, args, res)", start_op)
        for lit in (
            "select_all_entityai_b", "target_net_id", "witness_tag", "center_x_m", "center_z_m", "radius_m",
            "window_ms", "witness_follow_ticks", "per_witness", "target_not_found", "no_cargo_space", "bad_args",
            "server_epoch", "start_tick_ms", "start_frame",
        ):
            self.assertIn('"%s"' % lit, self.code, lit)

    def test_witness_job_is_exclusive_page5_max4096(self):
        self.assertRegex(
            self.code,
            r'StartJob\(this,\s*op\.op_id,\s*"per_witness",\s*m_WitnessNcol,\s*m_WitnessScol,\s*5,\s*4096,\s*[^,]+,\s*"stop"\)',
        )
        # El tope de filas lo pone el JobMgr (AppendRow): el .c no escribe a mano el motivo ni trunca.
        self.assertNotIn('"rows_cap"', self.code)
        witness_tick = _block_after(self.code, r"protected\s+void\s+TickWitness\s*\(\s*\)\s*\{")
        self.assertGreaterEqual(witness_tick.count("AppendWitnessRow("), 2)
        row = _block_after(self.code, r"protected\s+bool\s+AppendWitnessRow\s*\([^)]*\)\s*\{")
        self.assertIn("m_Jobs.AppendRow(", row)

    def test_witness_columns_and_ranges(self):
        self.assertEqual(_inserted(self.code, "m_WitnessScol"), WITNESS_SCOL)
        self.assertEqual(_inserted(self.code, "m_WitnessNcol"), WITNESS_NCOL)
        self.assertRegex(self.code, r"WITNESS_RADIUS_MAX\s*=\s*120\.0")
        self.assertRegex(self.code, r"WITNESS_WINDOW_MAX_MS\s*=\s*600000\.0")
        self.assertRegex(self.code, r"WITNESS_K_DEFAULT\s*=\s*3\b")
        self.assertRegex(self.code, r"WITNESS_K_MAX\s*=\s*5\b")
        body = _block_after(self.code, r"protected\s+void\s+HandleWitnessStart\s*\([^)]*\)\s*\{")
        self.assertLess(body.index("followK < 1"), body.index("StartJob("))  # los rechazos, antes de StartJob
        self.assertLess(body.index("StartJob("), body.index("DSBX_QA_Witness.Enable("))  # el gancho, despues
        for key in ("start_tick_ms", "start_frame", "center_x_m", "center_z_m", "radius_m", "window_ms", "witness_follow_ticks"):
            self.assertIn('PutNum(res.read, "%s"' % key, body)
        self.assertIn('PutStr(res.read, "witness_tag"', body)
        self.assertIn('PutStr(res.read, "server_epoch"', body)

    def test_window_end_waits_for_the_k_samples_and_off_on_any_job_end(self):
        tick = _block_after(self.code, r"protected\s+void\s+TickWitness\s*\(\s*\)\s*\{")
        self.assertIn("now >= m_WitnessEndMs", tick)
        self.assertRegex(tick, r"m_WitnessWindowClosed\s*&&\s*m_WitnessFollow\.Count\(\)\s*==\s*0")
        self.assertIn('EndJob(jid, "done", "")', tick)
        on_end = _block_after(self.code, r"override\s+void\s+OnJobEnd\s*\([^)]*\)\s*\{")
        self.assertIn("ResetWitness()", on_end)
        reset = _block_after(self.code, r"protected\s+void\s+ResetWitness\s*\(\s*\)\s*\{")
        self.assertIn("DSBX_QA_Witness.Disable()", reset)
        shutdown = _block_after(self.code, r"override\s+void\s+OnShutdown\s*\(\s*\)\s*\{")
        self.assertIn("ResetWitness()", shutdown)

    def test_census_mode0_columns_untouched_and_mode1_adds_surface_last(self):
        self.assertEqual(_inserted(self.code, "m_CensusNcol"), CENSUS_NCOL_MODE0)
        self.assertEqual(_inserted(self.code, "m_CensusScol"), CENSUS_SCOL)
        self.assertEqual(_inserted(self.code, "m_CensusNcolAll"), ["surface_y_m"])  # el resto se copia de m_CensusNcol
        cols = _block_after(self.code, r"protected\s+void\s+InitCensusColumns\s*\(\s*\)\s*\{")
        self.assertLess(cols.index("m_CensusNcolAll.Insert(m_CensusNcol.Get("), cols.index('m_CensusNcolAll.Insert("surface_y_m")'))
        start = _block_after(self.code, r"protected\s+void\s+HandleCensusStart\s*\([^)]*\)\s*\{")
        self.assertIn("censusNcol, m_CensusScol, 5, 4096, 900000.0", start)
        self.assertIn("m_CensusNcolAll", start)

    def test_census_mode1_guards_and_calls(self):
        start = _block_after(self.code, r"protected\s+void\s+HandleCensusStart\s*\([^)]*\)\s*\{")
        self.assertRegex(start, r'GetNumArg\(args,\s*"select_all_entityai_b",\s*0\.0\)')
        self.assertRegex(start, r"selectAllB\s*==\s*1\s*&&\s*\(\s*radiusM\s*<=\s*0\.0\s*\|\|\s*radiusM\s*>\s*CENSUS_ALL_RADIUS_MAX\s*\)")
        self.assertRegex(self.code, r"CENSUS_ALL_RADIUS_MAX\s*=\s*120\.0")
        self.assertLess(start.index("CENSUS_ALL_RADIUS_MAX"), start.index("StartJob("))  # sin efectos antes del rechazo
        self.assertIn("GetObjectsAtPosition3D(centerPos, radiusM, nearObjs, nearCargos)", start)
        self.assertIn("EnumerateInventory(InventoryTraversalType.PREORDER, subItems)", start)
        self.assertIn("EntityAI.Cast(obj) != null", start)
        row = _block_after(self.code, r"protected\s+void\s+AppendEntityCensusRow\s*\([^)]*\)\s*\{")
        self.assertRegex(row, r"if\s*\(withSurface\)\s*\{[^}]*g_Game\.SurfaceY\(pos\[0\],\s*pos\[2\]\)")
        self.assertIn("ReadRealLocation(obj,", row)  # parent_net_id, parent_class, slot_name y loc_kind reales

    def test_spawn_target_net_id(self):
        body = _block_after(self.code, r"protected\s+void\s+HandleSpawnRaw\s*\([^)]*\)\s*\{")
        self.assertIn('GetStrArg(args, "target_net_id", "")', body)
        self.assertIn("g_Game.GetObjectByNetworkId(tLow, tHigh)", body)
        self.assertIn("FindFirstFreeLocationForNewEntity(className, FindInventoryLocationType.CARGO, netLoc)", body)
        self.assertIn("GameInventory.LocationCreateEntity(netLoc, className, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT)", body)
        # Los rechazos nuevos van antes de crear nada.
        create = body.index("GameInventory.LocationCreateEntity(netLoc")
        self.assertLess(body.index('"target_not_found"'), create)
        self.assertLess(body.index('"no_cargo_space"'), create)
        # La rama anterior (por escena y padre) queda como estaba.
        self.assertIn("FindRecord(targetSceneId, targetParentId)", body)

    def test_fake_matches_the_c_columns_and_flags(self):
        self.assertEqual(_inserted(self.code, "m_WitnessNcol"), fake_ext_persist.WITNESS_NCOL)
        self.assertEqual(_inserted(self.code, "m_WitnessScol"), fake_ext_persist.WITNESS_SCOL)
        self.assertEqual(
            _inserted(self.code, "m_CensusNcol") + _inserted(self.code, "m_CensusNcolAll"), fake_ext_persist.CENSUS_NCOL_ALL,
        )
        self.assertEqual(fake_ext_persist.CENSUS_NCOL_ALL[-1], "surface_y_m")
        self.assertEqual("per_witness_start" in fake_ext_persist.SERVER_VERBS, True)

    def test_sources_are_lf(self):
        for path in (PERSIST_C, WITNESS_C, QA_DIR / "fake_ext_persist.py", Path(__file__)):
            self.assertNotIn(b"\r", path.read_bytes(), str(path))


if __name__ == "__main__":
    unittest.main()
