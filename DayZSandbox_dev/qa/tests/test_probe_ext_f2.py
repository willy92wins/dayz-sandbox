"""Pruebas del PR «sonda: extensiones para F2»: modo de censo select_all_entityai_b, target_net_id en per_spawn_raw
y per_witness_start (testigo de creacion con trayectoria de K muestras).

Tres capas:
  * extremo a extremo offline por el nucleo (PartContext, f03_common.issue_one, read_job_pages, job_free) con
    peers falsos reales (procesos), como el runner de S-persist;
  * en proceso, con un peer de pega y reloj manual, para lo que el e2e no puede forzar de forma determinista
    (alive_b = 0, el tope exacto de filas, la identidad del modo 0 frente al fake anterior, el tamano de pagina);
  * estaticas sobre los .c, como qa/tests/test_probe_static.py.
"""

import argparse, os
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
WITNESS_C = QA_DIR / "probe" / "DayZSandbox_QA" / "scripts" / "4_World" / "DSBX_QA_W_Witness.c"  # bufer y ganchos
WITNESS_W_C = WITNESS_C
PROBE_SCRIPTS = QA_DIR / "probe" / "DayZSandbox_QA" / "scripts"
VANILLA_ROOTS = (Path("P:/scripts"), Path(os.environ.get("DSBX_VANILLA_SCRIPTS", "P:/scripts")))
# Implementacion de S-persist (rama claude/s-persist-impl-e9, PR #21) sobre la que va este PR: la cabeza que se fusiono
# en el (antes, 6a7bd7a).
BASELINE_COMMIT = "89c431e"

CENTER = (6170.0, 7643.0)
CENSUS_SCOL = ["class_name", "loc_kind", "parent_class", "parent_net_id", "slot_name", "owner_uid", "own_logical_id", "net_id", "pers_id"]
# Las 14 columnas numericas de S-persist tal y como estaban antes de este PR (modo 0), copiadas a mano.
CENSUS_NCOL_MODE0 = [
    "own_b", "in_radius_b", "alive_b", "ai_agent_b", "pos_x_m", "pos_y_m", "pos_z_m", "yaw_deg", "pitch_deg",
    "roll_deg", "max_hp", "health_hp", "inv_children_n", "spawn_tick_ms",
]
WITNESS_SCOL = ["class_name", "net_id", "parent_net_id"]
WITNESS_NCOL = ["sample_idx", "pos_x_m", "pos_y_m", "pos_z_m", "yaw_deg", "tick_ms", "frame", "ai_agent_b", "alive_b", "surface_y_m"]
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


def _census(ctx, tag, radius, select_all=None, include_dir=0, center=CENTER, free=True, director_uid=""):
    nums = {
        "center_x_m": float(center[0]),
        "center_z_m": float(center[1]),
        "radius_m": float(radius),
        "include_director_b": float(include_dir),
    }
    if select_all is not None:
        nums["select_all_entityai_b"] = float(select_all)
    strs = {"area_tag": tag}
    if director_uid:
        strs["director_uid"] = director_uid
    out = _issue(ctx, "per_census_start", strs, nums)
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
        self.assertEqual(by_class["Land_Mil_Barracks1"][0]["net_id"], fake_ext_persist.BARRACKS_NET_ID)
        self.assertNotEqual(by_class["Land_Mil_Barracks1"][0]["net_id"], "0:0")  # los edificios tienen net_id real
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
        by_net = {r["net_id"]: r for r in pages["rows"]}
        apple = by_net["1:54"]  # anidado: Apple dentro de Pot dentro de WoodenCrate
        self.assertEqual(apple["parent_net_id"], "1:53")
        self.assertEqual(apple["parent_class"], "Pot")
        self.assertEqual(by_net["1:53"]["parent_net_id"], "1:52")
        # inv_children_n cuenta TODOS los descendientes (EnumerateInventory PREORDER), no solo los directos.
        # Expectativa independiente, a mano: WoodenCrate -> Pot -> Apple = 2; Pot -> Apple = 1; Apple = 0; el Pot 1:66
        # lleva una manzana y un botiquin vacio = 2; el botiquin 1:61 lleva tres Rag = 3.
        self.assertEqual(by_net["1:52"]["inv_children_n"], 2.0)
        self.assertEqual(by_net["1:53"]["inv_children_n"], 1.0)
        self.assertEqual(by_net["1:54"]["inv_children_n"], 0.0)
        self.assertEqual(by_net["1:66"]["inv_children_n"], 2.0)
        self.assertEqual(by_net["1:61"]["inv_children_n"], 3.0)
        # Cargo proxy de un edificio (PROXYCARGO): cargo con su padre y sus coordenadas reales, no suelo.
        proxy = by_net["1:65"]
        self.assertEqual(
            (proxy["loc_kind"], proxy["parent_net_id"], proxy["parent_class"], proxy["slot_name"]),
            ("cargo", fake_ext_persist.BARRACKS_NET_ID, "Land_Mil_Barracks1", "Cargo:2:1:3"),
        )
        wheel = by_class["HatchbackWheel"][0]
        self.assertEqual(wheel["loc_kind"], "attachment")
        self.assertEqual(wheel["slot_name"], "Wheel_1_1")
        self.assertEqual(wheel["parent_net_id"], "1:55")
        # El barril a 118 m queda fuera de un disco de 115 m; el lejano tambien.
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
        # Un resto de vehiculo sin sistema de daño (Land_Wreck_Uaz) no rompe el censo: max_hp = health_hp = -1.
        uaz = by_class["Land_Wreck_Uaz"][0]
        self.assertEqual((uaz["max_hp"], uaz["health_hp"]), (-1.0, -1.0))
        self.assertEqual(uaz["parent_net_id"], "")
        self.assertEqual(by_class["Barrel_Blue"][0]["max_hp"], 100.0)
        # El director no entra (include_director_b = 0).
        self.assertEqual([r for r in pages["rows"] if r["owner_uid"]], [])

    def test_mode1_include_director_and_radius_120(self):
        _o, pages, state = _census(self.ctx, "dir", 120.0, select_all=1, include_dir=1,
                                   director_uid=fake_ext_persist.DIRECTOR_UID)
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
            "child_count_n", "tick_ms", "frame", "health_mark_b",
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
        for bad in ("1:9999", "0:0", "7:7", "-5:5"):
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
        # Destinos que de verdad no aceptan el Rag (1x3) en SU cargo, con la config vanilla como referencia:
        #  * Apple 1:54: sin cargo (DZ/gear/food/config.cpp:4302; ni Edible_Base ni Inventory_Base lo declaran);
        #  * FirstAidKit 1:61: 3x3 lleno con tres Rag 1x3 y sin subcontenedores;
        #  * Pot 1:66: 4x3 lleno para un Rag (manzana en (0,0) y botiquin 3x3 en las columnas 1-3), pero el
        #    botiquin tiene hueco: FindFirstFree podria devolver el cargo del botiquin y el padre no seria el Pot.
        for target in ("1:54", "1:61", "1:66"):
            kids_before, pages_before = self._children_of(target)
            res = _spawn(self.ctx, "nc" + target, "foreign_in_container", "Rag", target_net_id=target)
            self.assertEqual((res.status, res.reason), ("rejected", "no_cargo_space"), target)
            kids_after, pages_after = self._children_of(target)
            self.assertEqual(pages_before["rows_total_n"], pages_after["rows_total_n"], target)
            self.assertEqual(sorted(k["net_id"] for k in kids_before), sorted(k["net_id"] for k in kids_after), target)
        # El subcontenedor libre del Pot 1:66 sigue vacio (no se creo nada bajo otro padre).
        self.assertEqual(self._children_of("1:60")[0], [])
        # El Pot 1:53 (solo la manzana en (0,0)) si tiene hueco: columna 1.
        ok = _spawn(self.ctx, "fits", "foreign_in_container", "Rag", target_net_id="1:53")
        self.assertEqual(ok.status, "done", ok)
        self.assertEqual(ok.payload["str"]["obs_slot_name"], "Cargo:0:0:1")
        # El coche si tiene cargo en vanilla (10x30, DZ/vehicles/wheeled/config.cpp:1495).
        car = _spawn(self.ctx, "car", "foreign_in_container", "Rag", target_net_id="1:55")
        self.assertEqual(car.status, "done", car)

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
        # Una clase que no deriva de ninguna raiz enganchada (un jugador) nace dentro del radio y el testigo no la ve.
        uncovered = _spawn(self.ctx, "wu", "foreign_ground", "SurvivorM_Mirek", 6181.0, 7651.0)
        for r in (ground, boxed, outside, uncovered):
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
        self.assertNotIn(uncovered.payload["str"]["net_id"], by_net)
        for net_id, samples in by_net.items():
            self.assertEqual([r["sample_idx"] for r in samples], [0.0, 1.0, 2.0, 3.0], net_id)
            self.assertEqual({r["alive_b"] for r in samples}, {1.0})
            self.assertEqual({r["ai_agent_b"] for r in samples}, {0.0})
            ticks = [r["tick_ms"] for r in samples]
            frames = [r["frame"] for r in samples]
            self.assertEqual(ticks, sorted(ticks))
            self.assertEqual(frames, sorted(frames))
            # Frames consecutivos 0, 1, ..., K: sample_idx 1 es el frame siguiente al de EEInit.
            self.assertEqual(frames, [frames[0] + i for i in range(4)], net_id)
            self.assertEqual(len({r["pos_x_m"] for r in samples}), 1)
            # Las muestras 0..K comparten net_id (el de la fila 0 se lee en el primer tick, no en EEInit) y no es 0:0.
            self.assertEqual(len({r["net_id"] for r in samples}), 1, net_id)
            self.assertNotEqual(samples[0]["net_id"], "0:0")
            # surface_y_m: SurfaceY de la x y la z de cada fila (la muestra 0, las de EEInit; las demas, las de su tick).
            for r in samples:
                self.assertAlmostEqual(
                    r["surface_y_m"], fake_ext_persist._surface_y(r["pos_x_m"], r["pos_z_m"]), places=9, msg=net_id,
                )
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
    rows = list(rows or [])
    # Como llegan por el cable (wire.unpack_payload): con filas llegan tambien sus columnas, que el apply de S-persist
    # exige (s_persist_run.py las manda siempre).
    ncol = [k for k, v in rows[0].items() if not isinstance(v, str)] if rows else []
    scol = [k for k, v in rows[0].items() if isinstance(v, str)] if rows else []
    unpacked = {"str": dict(strs or {}), "num": dict(nums or {}), "rows": rows, "ncol": ncol, "scol": scol}
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
        _tick(self.peer, self.jobs, self.ext)  # sample 0 (EEInit) y sample 1 (este tick), vivo
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
        for r in rows:  # tambien con alive_b = 0: SurfaceY de la ultima posicion emitida
            self.assertAlmostEqual(r["surface_y_m"], fake_ext_persist._surface_y(r["pos_x_m"], r["pos_z_m"]), places=9)
        self.assertEqual({r["class_name"] for r in rows}, {"Barrel_Yellow"})
        self.assertEqual({(r["pos_x_m"], r["pos_z_m"]) for r in rows}, {(6180.0, 7650.0)})  # ultima posicion conocida
        self.assertEqual([r["frame"] for r in rows], [rows[0]["frame"] + i for i in range(4)])  # 0, 1, 2, 3 consecutivos
        self.assertIsNone(self.ext.witness)

    def test_sample0_carries_the_net_id_of_the_first_tick(self):
        job_id = self._start(window_ms=500.0, k=2)
        ent = self._new()
        self.assertEqual(self.ext.witness["buf"][0]["net_id"], "0:0")  # en EEInit el motor aun no lo asigno
        _tick(self.peer, self.jobs, self.ext)
        rows = _job_rows(self.jobs, job_id)
        self.assertEqual([r["sample_idx"] for r in rows], [0.0, 1.0])
        self.assertEqual({r["net_id"] for r in rows}, {ent["net_id"]})
        self.assertNotEqual(rows[0]["net_id"], "0:0")
        # Posicion y frame de EEInit en la fila 0; sample 1 sigue siendo el frame siguiente.
        self.assertEqual(rows[1]["frame"], rows[0]["frame"] + 1)

    def test_sample0_of_an_entity_gone_before_the_first_tick(self):
        job_id = self._start(window_ms=500.0, k=1)
        ent = self._new()
        self.ext._delete_entity(ent)
        _tick(self.peer, self.jobs, self.ext)
        rows = _job_rows(self.jobs, job_id)
        self.assertEqual([r["sample_idx"] for r in rows], [0.0, 1.0])
        self.assertEqual([(r["net_id"], r["alive_b"]) for r in rows], [("0:0", 0.0), ("0:0", 0.0)])
        self.assertEqual((rows[0]["pos_x_m"], rows[0]["pos_z_m"]), (6180.0, 7650.0))

    def test_class_without_hooked_root_is_not_seen(self):
        job_id = self._start(window_ms=200.0, k=1)
        self._new("SurvivorM_Mirek")  # jugador: ManBase no esta enganchado
        self._new("UnknownModdedThing")
        covered = self._new("Zmbf_PoliceCopBlue")  # ZombieBase
        self._new("Land_Mil_Barracks1", 6181.0, 7651.0)  # House > BuildingBase
        _tick(self.peer, self.jobs, self.ext)
        rows = _job_rows(self.jobs, job_id)
        self.assertEqual(sorted({r["class_name"] for r in rows}), ["Land_Mil_Barracks1", "Zmbf_PoliceCopBlue"])
        self.assertEqual(len(rows), 4)  # una sola fila por entidad y muestra: sin doble captura
        self.assertEqual(sum(1 for r in rows if r["sample_idx"] == 0.0), 2)
        self.assertEqual(fake_ext_persist.hook_root("Barrel_Yellow"), "ItemBase")
        self.assertIsNone(fake_ext_persist.hook_root("SurvivorM_Mirek"))
        self.assertIsNotNone(covered)

    def test_first_follow_sample_is_the_frame_after_eeinit(self):
        # Q-01: un desplazamiento del mod entre EEInit y el primer tick se ve en sample_idx 1, no un tick despues.
        job_id = self._start(window_ms=500.0, k=2)
        ent = self._new()
        f_create = self.peer.frame
        ent["pos"] = (6181.5, 100.0, 7651.5)  # el mod lo desplaza antes del primer tick de servidor
        _tick(self.peer, self.jobs, self.ext)
        rows = _job_rows(self.jobs, job_id)
        self.assertEqual([r["sample_idx"] for r in rows], [0.0, 1.0])
        self.assertEqual((rows[0]["pos_x_m"], rows[1]["pos_x_m"]), (6180.0, 6181.5))
        self.assertEqual((rows[0]["frame"], rows[1]["frame"]), (float(f_create), float(f_create + 1)))
        ent["pos"] = (6183.0, 100.0, 7651.5)
        _tick(self.peer, self.jobs, self.ext)
        rows = _job_rows(self.jobs, job_id)
        self.assertEqual([r["sample_idx"] for r in rows], [0.0, 1.0, 2.0])
        self.assertEqual(rows[2]["pos_x_m"], 6183.0)
        self.assertEqual(rows[2]["frame"], float(f_create + 2))

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
            # S-persist retiene el censo hasta CENSUS_HOLD_MAX_MS (750 ms) si nadie lo disputa: 30 ticks de 33 ms.
            _tick(peer, jobs, ext, n=30)
            job = jobs.jobs_by_id["cap"]
            self.assertEqual((job["state"], job["reason"], job["rows_total"]), (want_state, want_reason, 4096), extra)

    def test_mode1_rejections_leave_no_job(self):
        peer, jobs, ext = _make_ext()
        for radius in (0.0, 120.01, 500.0):
            self.assertEqual(self._census(ext, "r%s" % radius, radius=radius)[:2], ("rejected", "bad_args"))
        self.assertEqual(jobs.jobs_by_id, {})
        self.assertEqual(jobs.held_resources, {})


class MergeInteractionsInProcess(unittest.TestCase):
    """Interacciones de la fusion con S-persist que git no marco (Sol sobre fb2dcb8)."""

    def test_inv_children_direct_in_mode0_and_all_descendants_in_mode1_on_the_same_tree(self):
        # S-persist (modo 0) cuenta hijos directos; el censo select_all_entityai_b = 1 (contrato de F2), todos los
        # descendientes. El mismo arbol anidado discrimina los dos conteos: WoodenCrate -> Pot -> Apple.
        peer, jobs, ext = _make_ext()
        pos = (CENTER[0] + 5.0, fake_ext_persist._surface_y(CENTER[0] + 5.0, CENTER[1]), CENTER[1])
        ext._add_entity(net_id="9:1", class_name="WoodenCrate", cat="raw", pos=pos)
        ext._add_entity(net_id="9:2", class_name="Pot", cat="raw", parent_net_id="9:1", parent_class="WoodenCrate",
                        loc_kind="cargo", slot_name="Cargo:0:0:0", pos=pos)
        ext._add_entity(net_id="9:3", class_name="Apple", cat="raw", parent_net_id="9:2", parent_class="Pot",
                        loc_kind="cargo", slot_name="Cargo:0:0:0", pos=pos)
        got = {}
        for mode in (0, 1):
            nums = {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": 60.0, "include_director_b": 0.0,
                    "select_all_entityai_b": float(mode)}
            status, reason, _p = _call(ext, "per_census_start", {"area_tag": "t"}, nums, op_id="m%d" % mode)
            self.assertEqual((status, reason), ("done", ""), mode)
            rows = {r["net_id"]: r for r in _job_rows(jobs, "m%d" % mode)}
            got[mode] = tuple(rows[n]["inv_children_n"] for n in ("9:1", "9:2", "9:3"))
            _tick(peer, jobs, ext, n=30)  # la retencion de S-persist cierra el censo (750 ms) antes del siguiente
        self.assertEqual(got[0], (1.0, 1.0, 0.0))
        self.assertEqual(got[1], (2.0, 1.0, 0.0))

    def test_rejected_target_net_spawns_leave_identity_counters_untouched(self):
        peer, jobs, ext = _make_ext()

        def identity():
            return sorted(ext.world), ext.next_net_low, ext.next_pers_seq

        before = identity()
        for target, want in (("abc", "bad_args"), ("1:9999", "target_not_found"), ("1:61", "no_cargo_space")):
            status, reason, _p = _call(
                ext, "per_spawn_raw",
                {"tag": "r", "mode": "foreign_in_container", "class_name": "Rag", "target_net_id": target},
                {"health_mark_ratio": 0.0}, op_id="r-" + target,
            )
            self.assertEqual((status, reason), ("rejected", want), target)
        self.assertEqual(identity(), before)
        # y la siguiente creacion recibe el mismo pers_id que sin los rechazos
        _peer2, _jobs2, twin = _make_ext()
        args = ({"tag": "g", "mode": "foreign_ground", "class_name": "Barrel_Yellow"},
                {"x_m": 6180.0, "z_m": 7650.0, "yaw_deg": 0.0, "health_mark_ratio": 0.0})
        a = wire.unpack_payload(_call(ext, "per_spawn_raw", *args, op_id="g1")[2])
        b = wire.unpack_payload(_call(twin, "per_spawn_raw", *args, op_id="g1")[2])
        self.assertEqual((a["str"]["pers_id"], a["str"]["net_id"]), (b["str"]["pers_id"], b["str"]["net_id"]))


class CensusSpatialInProcess(unittest.TestCase):
    """Modo 1: la seleccion es la esfera de GetObjectsAtPosition3D centrada en (cx, SurfaceY(cx, cz), cz)."""

    def _classes(self, ext, jobs, op_id, radius):
        nums = {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": radius, "select_all_entityai_b": 1.0}
        status, reason, _p = _call(ext, "per_census_start", {"area_tag": "t"}, nums, op_id=op_id)
        self.assertEqual((status, reason), ("done", ""))
        return {r["class_name"] for r in _job_rows(jobs, op_id)}

    def test_elevated_roots_use_3d_distance(self):
        cy = fake_ext_persist._surface_y(*CENTER)
        for r, expect_in in ((115.0, False), (120.0, True)):
            peer, jobs, ext = _make_ext()
            ext._add_entity(net_id="9:1", class_name="High116", cat="raw", pos=(CENTER[0], cy + 116.0, CENTER[1]))
            ext._add_entity(net_id="9:2", class_name="Flat100", cat="raw", pos=(CENTER[0] + 100.0, cy, CENTER[1]))
            # 100 m en horizontal y 60 m de altura: 116,6 m en 3D (fuera con 115, dentro con 120)
            ext._add_entity(net_id="9:3", class_name="Raised100", cat="raw", pos=(CENTER[0] + 100.0, cy + 60.0, CENTER[1]))
            # 100 m en horizontal y 40 m de altura: 107,7 m en 3D (dentro con los dos radios)
            ext._add_entity(net_id="9:4", class_name="Raised40", cat="raw", pos=(CENTER[0] + 100.0, cy + 40.0, CENTER[1]))
            got = self._classes(ext, jobs, "e%d" % int(r), r)
            self.assertEqual("High116" in got, expect_in, r)
            self.assertEqual("Raised100" in got, expect_in, r)
            self.assertIn("Flat100", got)
            self.assertIn("Raised40", got)

    def test_mode0_keeps_its_horizontal_disc(self):
        # El modo de S-persist no cambia: distancia horizontal, sin altura.
        peer, jobs, ext = _make_ext()
        cy = fake_ext_persist._surface_y(*CENTER)
        ext._add_entity(net_id="9:1", class_name="High116", cat="raw", pos=(CENTER[0], cy + 116.0, CENTER[1]))
        nums = {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": 115.0}
        _call(ext, "per_census_start", {"area_tag": "t"}, nums, op_id="m0")
        self.assertIn("High116", {r["class_name"] for r in _job_rows(jobs, "m0")})


def _without_health_mark(payload):
    """El payload sin lo que anade la marca de salud verificada (columna health_mark_b del apply y escalar
    health_mark_b de per_spawn_raw, los dos AL FINAL): lo demas tiene que seguir siendo identico al fake previo."""
    out = dict(payload)
    keep = [i for i, k in enumerate(out["nk"]) if k != "health_mark_b"]
    out["nk"] = [out["nk"][i] for i in keep]
    out["nv"] = [out["nv"][i] for i in keep]
    if "health_mark_b" in out["ncol"]:
        width = len(out["ncol"])
        drop = out["ncol"].index("health_mark_b")
        out["ncell"] = [v for i, v in enumerate(out["ncell"]) if i % width != drop]
        out["ncol"] = [c for c in out["ncol"] if c != "health_mark_b"]
    return out


class Mode0IdentityInProcess(unittest.TestCase):
    """Con select_all_entityai_b = 0 (o ausente), filas y columnas son identicas a las del fake anterior al PR."""

    # Huella del escenario con el fake de BASELINE_COMMIT (89c431e), sin lo que anade la marca de salud.
    GOLDEN_SHA256 = "7befe73ed99917ebcee2b56fbef533f96a4bd19bcf94ce6072631f5a0c945a39"

    @staticmethod
    def _scenario(module, explicit_zero):
        peer, jobs, ext = _make_ext(module)
        trace = []

        def run(verb, strs=None, nums=None, rows=None, op_id="x"):
            res = _call(ext, verb, strs, nums, rows, op_id=op_id)
            trace.append([verb, res[0], res[1], _without_health_mark(res[2])])
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
            # Contrato de S-persist: el censo lleva siempre director_uid (como en a80e65b y en el
            # runner de F2P); sin el, include_director_b = 1 se rechaza y los escalares del director salen a 0.
            census_strs = {"area_tag": "area_a", "director_uid": fake_ext_persist.DIRECTOR_UID}
            status, reason, payload = run("per_census_start", census_strs, nums, op_id=op_id)
            # S-persist retiene el censo hasta CENSUS_HOLD_MAX_MS (750 ms) si nadie lo disputa: 30 ticks de 33 ms.
            _tick(peer, jobs, ext, n=30)
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
        base = [3.0, 6170.123456789 + i, 188.123456789, 7643.987654321, 359.123456, 123456789.123456, 999999.0, 0.0, 1.0, 188.1234567]
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

    def test_every_modded_class_calls_super_first_then_checks_the_bool(self):
        names = re.findall(r"\bmodded\s+class\s+(\w+)", self.code)
        self.assertEqual(sorted(names), sorted(HOOK_ROOTS + HOOK_EXTRAS))  # lista cerrada: la que se valida en partida
        for cls in names:
            body = _block_after(self.code, r"modded\s+class\s+%s\s*\{" % cls)
            eeinit = _block_after(body, r"override\s+void\s+EEInit\s*\(\s*\)\s*\{")
            stmts = _statements(eeinit)
            self.assertEqual(stmts[0], "super.EEInit();", cls)
            self.assertRegex(stmts[1], r"^if \(!DSBX_QA_Witness\.s_On\) return;$", cls)
            self.assertEqual(stmts[2], "DSBX_QA_Witness.Capture(this);", cls)
            self.assertEqual(len(stmts), 3, cls)

    def test_no_engine_class_is_modded(self):
        # EntityAI y compania son clases del motor ("Engine class 'EntityAI' cannot be modded"): solo raices de script.
        names = set(re.findall(r"\bmodded\s+class\s+(\w+)", self.code))
        self.assertEqual(names & ENGINE_CLASSES, set())
        for _t, code in (_code(p) for p in sorted(PROBE_SCRIPTS.rglob("*.c"))):
            self.assertEqual(set(re.findall(r"\bmodded\s+class\s+(\w+)", code)) & ENGINE_CLASSES, set())
        # y la prueba no es vacua: detecta un modded class de EntityAI.
        self.assertEqual({"EntityAI"} & ENGINE_CLASSES, {"EntityAI"})

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


def _eeinit_without_super(root):
    """(fichero, clase) de cada override void EEInit() de root cuyo cuerpo no llama a super.EEInit()."""
    out = []
    for path in sorted(Path(root).rglob("*.c")):
        text = path.read_bytes().decode("utf-8", "replace")
        for m in re.finditer(r"\boverride\s+void\s+EEInit\s*\(\s*\)\s*\{", text):
            depth, j = 1, m.end()
            while j < len(text) and depth:
                depth += {"{": 1, "}": -1}.get(text[j], 0)
                j += 1
            body = re.sub(r"//[^\n]*", "", text[m.end():j])
            if "super.EEInit" in body:
                continue
            cls = None
            for cm in re.finditer(r"\bclass\s+(\w+)\s*(?:extends|:)\s*\w+", text[:m.start()]):
                cls = cm.group(1)
            out.append((path.name, cls))
    return out


def _vanilla_class_index(root):
    """{modulo: {clase}} con cada `class X` (no modded) de scripts/3_game, 4_world y 5_mission de root."""
    index = {}
    for mod in ("3_game", "4_world", "5_mission"):
        names = set()
        for path in (Path(root) / mod).rglob("*.c"):
            text = path.read_bytes().decode("utf-8", "replace")
            names.update(re.findall(r"^[ \t]*class[ \t]+(\w+)", text, re.M))
        index[mod] = names
    return index


def _modded_module_violations(scripts_dir, index):
    """Cada `modded class X` de scripts/<N>_<Modulo>/ tiene que estar definida en el mismo modulo vanilla."""
    out = []
    for path in sorted(Path(scripts_dir).rglob("*.c")):
        mod = path.parent.name.lower()
        code = tps._strip_comments(path.read_bytes().decode("utf-8"), blank_strings=False)
        for m in re.finditer(r"\bmodded\s+class\s+(\w+)", code):
            if m.group(1) not in index.get(mod, set()):
                out.append("%s: modded class %s no esta definida en %s" % (path.name, m.group(1), mod))
    return out


class StaticModdedClassModuleTests(unittest.TestCase):
    """Un modded class tiene que estar en el MISMO modulo de scripts que la clase original (EntityAI es de 3_Game)."""

    @classmethod
    def setUpClass(cls):
        roots = [r for r in VANILLA_ROOTS if (r / "3_game").is_dir() and (r / "4_world").is_dir()]
        if not roots:
            raise unittest.SkipTest("no hay scripts vanilla (P:\\scripts ni DSBX_VANILLA_SCRIPTS)")
        cls.index = _vanilla_class_index(roots[0])

    def test_probe_modded_classes_live_in_their_vanilla_module(self):
        self.assertEqual(_modded_module_violations(PROBE_SCRIPTS, self.index), [])
        self.assertIn("EntityAI", self.index["3_game"])  # el indice ve de verdad el vanilla

    def test_control_modded_entityai_in_4_world_fails(self):
        tmp = Path(tempfile.mkdtemp(prefix="dsbx-modmod-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "4_World").mkdir()
        (tmp / "3_Game").mkdir()
        (tmp / "4_World" / "bad.c").write_bytes(b"modded class EntityAI\n{\n}\n")
        (tmp / "3_Game" / "ok.c").write_bytes(b"modded class EntityAI\n{\n}\n")
        got = _modded_module_violations(tmp, self.index)
        self.assertEqual(len(got), 1, got)
        self.assertIn("bad.c", got[0])

    def test_hook_file_is_in_4_world_and_there_is_no_3_game(self):
        self.assertEqual(WITNESS_C.parent.name, "4_World")
        self.assertFalse((PROBE_SCRIPTS / "3_Game").exists())
        cfg = (QA_DIR / "probe" / "DayZSandbox_QA" / "config.cpp").read_bytes().decode("utf-8")
        self.assertNotIn("gameScriptModule", cfg)
        self.assertRegex(cfg, r'dependencies\[\]\s*=\s*\{"World",\s*"Mission"\};')


# Raices de script moddables (todas de 4_world) en las que se engancha el testigo, y las 4 clases vanilla que cortan
# la cadena de EEInit por debajo de una raiz. Es la lista que se valida en partida.
HOOK_ROOTS = ("ItemBase", "ZombieBase", "AnimalBase", "CarScript", "BuildingBase")
HOOK_EXTRAS = ("ContaminatedArea_Local", "ChristmasTree", "Animal_CapraHircus_Spooky", "ZmbM_Mummy")
# Clases del motor (o de 3_game con metodos proto) citadas: no se pueden modar. entityai.c:115 (proto native
# GetHierarchyParent :885), object.c, entity.c:1, inventoryitem.c:1, building.c:17, man.c:13, transport.c:68,
# dayzanimal.c:24/:191/:655, dayzinfected.c:104, pawn.c:191, gameplay.c:1531.
ENGINE_CLASSES = frozenset({
    "EntityAI", "Object", "Entity", "ObjectTyped", "InventoryItem", "Building", "Transport", "Car", "Boat",
    "Helicopter", "Motorbike", "Man", "Person", "Human", "DayZPlayer", "DayZCreature", "DayZCreatureAI",
    "DayZAnimal", "DayZInfected", "Pawn", "Static", "ScriptedEntity", "EffecterBase",
})
# Cobertura de la escena de F2 (fixtures/escena-sin-actores.json, 33 raices): clase de script que crea el producto
# (la primera de la cadena de la clase de config que existe en scripts) -> raiz enganchada que la cubre.
F2_COVERAGE = {
    "House": "BuildingBase",  # Land_Wreck_Ikarus, _Volha_Police, _V3S, _Volha_Blue, Land_Container_1Bo, _1Aoh (HouseNoDestruct > House)
    "LargeTent": "ItemBase", "MediumTent": "ItemBase", "CarTent": "ItemBase", "CamoNet": "ItemBase",
    "Fireplace": "ItemBase", "Barrel_Red": "ItemBase", "Barrel_Blue": "ItemBase", "Barrel_Green": "ItemBase",
    "Barrel_Yellow": "ItemBase", "WoodenCrate": "ItemBase", "SeaChest": "ItemBase", "Spotlight": "ItemBase",
    "PowerGenerator": "ItemBase",
    "ZmbM_FarmerFat_Base": "ZombieBase", "ZmbM_HermitSkinny_Base": "ZombieBase", "ZmbF_CitizenANormal_Base": "ZombieBase",
    "ZmbM_CitizenASkinny_Base": "ZombieBase", "ZmbM_PatrolNormal_Base": "ZombieBase", "ZmbF_VillagerOld_Base": "ZombieBase",
    "ZmbM_Jacket_Base": "ZombieBase", "ZmbF_Runner_Base": "ZombieBase", "ZmbM_HunterOld_Base": "ZombieBase",
    "ZmbM_MotobikerFat_Base": "ZombieBase",
    "Animal_CervusElaphus": "AnimalBase", "Animal_CapreolusCapreolus": "AnimalBase",
    "Animal_GallusGallusDomesticus": "AnimalBase",
}


def _script_parents(root):
    parents = {}
    modules = {}
    for mod in ("3_game", "4_world", "5_mission"):
        for path in (Path(root) / mod).rglob("*.c"):
            text = path.read_bytes().decode("utf-8", "replace")
            for m in re.finditer(r"^[ \t]*class[ \t]+(\w+)[ \t]*(?:extends|:)[ \t]*(\w+)", text, re.M):
                parents.setdefault(m.group(1), m.group(2))
                modules.setdefault(m.group(1), mod)
    return parents, modules


def _chain(parents, name):
    out, seen = [], set()
    while name in parents and name not in seen:
        seen.add(name)
        out.append(name)
        name = parents[name]
    out.append(name)
    return out


class StaticHookRootsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        roots = [r for r in VANILLA_ROOTS if (r / "3_game").is_dir() and (r / "4_world").is_dir()]
        if not roots:
            raise unittest.SkipTest("no hay scripts vanilla (P:\\scripts ni DSBX_VANILLA_SCRIPTS)")
        cls.root = roots[0]
        cls.parents, cls.modules = _script_parents(cls.root)

    def test_roots_are_script_classes_of_4_world_and_derive_from_entityai(self):
        for cls in HOOK_ROOTS + HOOK_EXTRAS:
            self.assertEqual(self.modules.get(cls), "4_world", cls)
            self.assertIn("EntityAI", _chain(self.parents, cls), cls)
            self.assertNotIn(cls, ENGINE_CLASSES)

    def test_no_double_capture(self):
        # Ninguna raiz es ascendiente de otra: una entidad pasa por un solo gancho de raiz.
        for a in HOOK_ROOTS:
            chain = _chain(self.parents, a)[1:]
            self.assertEqual([b for b in HOOK_ROOTS if b in chain], [], a)
        cut = {c for _f, c in _eeinit_without_super(self.root)}
        for extra in HOOK_EXTRAS:
            chain = _chain(self.parents, extra)[1:]
            # Deriva de exactamente una raiz enganchada (si no, el modded class sobra) ...
            self.assertEqual(len([b for b in HOOK_ROOTS if b in chain]), 1, extra)
            # ... y su EEInit vanilla corta la cadena (si llamara a super habria raiz mas extra = dos filas).
            self.assertIn(extra, cut, extra)
        # Toda clase vanilla que corta la cadena por debajo de una raiz esta cubierta; ninguna otra se mada.
        for cls in cut:
            chain = _chain(self.parents, cls)
            if any(b in chain for b in HOOK_ROOTS):
                self.assertIn(cls, HOOK_EXTRAS, cls)
        # Un extra no es ascendiente de otro extra.
        for a in HOOK_EXTRAS:
            for b in HOOK_EXTRAS:
                if a != b:
                    self.assertNotIn(a, _chain(self.parents, b)[1:])

    def test_f2_scene_classes_are_covered_by_exactly_one_hooked_root(self):
        for cls, root in F2_COVERAGE.items():
            chain = _chain(self.parents, cls)
            self.assertIn(cls, self.parents, cls)  # la clase de script existe en vanilla
            hit = [b for b in HOOK_ROOTS if b in chain]
            self.assertEqual(hit, [root], cls)
            self.assertFalse(set(chain) & set(HOOK_EXTRAS), cls)  # ninguna cae en una clase que corta la cadena
        self.assertEqual(len(F2_COVERAGE), 27)  # 1 House (6 edificios) + 13 items + 10 infectados + 3 animales: 33 raices


class StaticEEInitCoverageTests(unittest.TestCase):
    VANILLA_ROOTS = (Path("P:/scripts"), Path(os.environ.get("DSBX_VANILLA_SCRIPTS", "P:/scripts")))

    def test_scanner_detects_a_class_that_cuts_the_chain(self):
        tmp = Path(tempfile.mkdtemp(prefix="dsbx-eeinit-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "a.c").write_bytes(
            b"class Cut extends House\n{\n\toverride void EEInit()\n\t{\n\t\tFoo();\n\t}\n}\n"
            b"class Ok extends House\n{\n\toverride void EEInit()\n\t{\n\t\tsuper.EEInit();\n\t}\n}\n"
        )
        self.assertEqual(_eeinit_without_super(tmp), [("a.c", "Cut")])

    def test_every_vanilla_class_that_cuts_the_chain_is_covered(self):
        roots = [r for r in self.VANILLA_ROOTS if r.is_dir()]
        if not roots:
            self.skipTest("no hay scripts vanilla (P:\\scripts) en esta maquina")
        witness = WITNESS_C.read_bytes().decode("utf-8") + WITNESS_W_C.read_bytes().decode("utf-8")
        for root in roots:
            found = _eeinit_without_super(root)
            self.assertGreater(len(found), 0)  # el escaner ve al menos los cuatro conocidos
            for fname, cls in found:
                self.assertRegex(
                    witness, r"modded\s+class\s+%s\b" % re.escape(cls),
                    "%s (%s) corta la cadena de EEInit y no esta cubierta en DSBX_QA_W_Witness.c" % (cls, fname),
                )

    def test_covered_classes_repeat_the_guard_and_limitation_is_written(self):
        _t, code_g = _code(WITNESS_C)
        _t, code_w = _code(WITNESS_W_C)
        code = code_g + code_w
        raw = WITNESS_W_C.read_bytes().decode("utf-8")
        for cm in re.finditer(r"modded\s+class\s+(\w+)", code):
            cls = cm.group(1)
            body = _block_after(code, r"modded\s+class\s+%s\s*\{" % cls)
            stmts = _statements(_block_after(body, r"override\s+void\s+EEInit\s*\(\s*\)\s*\{"))
            self.assertEqual(stmts[0], "super.EEInit();", cls)
            self.assertRegex(stmts[1], r"^if \(!DSBX_QA_Witness\.s_On\) return;$", cls)
            self.assertEqual(stmts[2], "DSBX_QA_Witness.Capture(this);", cls)
        self.assertIn("LIMITACION CONOCIDA", raw)
        self.assertIn("mods de terceros", raw)


class HealthMarkInProcess(unittest.TestCase):
    """Marca de salud reconciliada con S-persist (16-nov): lo que crea el QA la lleva puesta al crear, directa y
    verificada (SetHealth y relectura; health_mark_b = 1 si la relectura la confirma). health_mark_pending no existe y
    -1/-1 queda para los objetos del mundo sin sistema de daño (HasDamageSystem() dice «inicializado», object.c:976)."""

    def setUp(self):
        self.peer, self.jobs, self.ext = _make_ext()

    def _row(self, lid, cname, ratio, parent=""):
        return {"logical_id": lid, "parent_id": parent, "cat": "prop", "class_name": cname,
                "slot_name": "Cargo" if parent else "", "req_x_m": 6120.0, "req_z_m": 7600.0, "req_yaw_deg": 0.0,
                "health_mark_ratio": ratio, "must_vanish_b": 1.0}

    def _apply(self, rows, op="o1"):
        status, reason, payload = _call(
            self.ext, "per_apply_scene",
            {"scene_id": "sc", "scene_op_id": op, "expect_epoch": self.peer.inst, "q9_pathway": "a"},
            {"gen_n": 1.0}, rows, op_id="apply-" + op,
        )
        self.assertEqual((status, reason), ("done", ""))
        return wire.unpack_payload(payload)

    def _spawn(self, ratio, cname="WoodenCrate", op="sp"):
        status, reason, payload = _call(
            self.ext, "per_spawn_raw", {"tag": "t", "mode": "foreign_ground", "class_name": cname},
            {"x_m": 6180.0, "z_m": 7650.0, "yaw_deg": 0.0, "health_mark_ratio": ratio}, op_id=op,
        )
        return status, reason, wire.unpack_payload(payload)

    def test_qa_creation_carries_the_verified_mark_at_once(self):
        out = self._apply([self._row("a", "WoodenCrate", 0.5), self._row("b", "Barrel_Yellow", 0.0)])
        self.assertEqual((out["str"]["apply_status"], out["str"]["reason"]), ("ok", ""))
        self.assertNotIn("health_mark_pending_n", out["num"])
        a, b = out["rows"]
        self.assertEqual((a["max_hp"], a["health_hp"], a["health_mark_b"]), (100.0, 50.0, 1.0))
        self.assertEqual((b["max_hp"], b["health_hp"], b["health_mark_b"]), (100.0, 100.0, 1.0))  # sin marca pedida
        status, reason, raw = self._spawn(0.25)
        self.assertEqual((status, reason, raw["str"]["spawn_status"]), ("done", "", "ok"))
        self.assertEqual((raw["num"]["max_hp"], raw["num"]["health_hp"], raw["num"]["health_mark_b"]), (100.0, 25.0, 1.0))

    def test_health_mark_b_is_the_last_column_and_the_old_ones_keep_their_order(self):
        out = self._apply([self._row("a", "WoodenCrate", 0.5)])
        old = ["ok_b", "alive_b", "ai_agent_b", "req_y_m", "q9_x_m", "q9_y_m", "q9_z_m", "q9_dx_m", "q9_dy_m", "q9_dz_m",
               "q9_err_3d_m", "q9_yaw_deg", "q9_pitch_deg", "q9_roll_deg", "max_hp", "health_hp", "spawn_tick_ms"]
        self.assertEqual(out["ncol"], old + ["health_mark_b"])

    def test_failed_creation_confirms_no_mark(self):
        # Hijo de un padre que no existe: fila fallida sin salud observada y sin marca confirmada (MEN de Sol sobre
        # dcde8f3: la creacion fallida salia con health_mark_b = 1).
        out = self._apply([self._row("a", "WoodenCrate", 0.5), self._row("c", "Rag", 0.5, parent="nope")])
        self.assertEqual((out["str"]["apply_status"], out["str"]["reason"]), ("partial", "creation_failed"))
        a, c = out["rows"]
        self.assertEqual((a["ok_b"], a["health_mark_b"]), (1.0, 1.0))
        self.assertEqual((c["ok_b"], c["max_hp"], c["health_hp"], c["health_mark_b"]), (0.0, 0.0, 0.0, 0.0))

    def test_object_without_damage_system_gives_no_health_and_no_mark(self):
        # Clase sin sistema de daño creada por el QA (en el motor no esta soportado: GetMaxHealth tira la excepcion):
        # el fake no inventa la salud y la marca pedida sale sin confirmar en el recibo, sin estados nuevos.
        out = self._apply([self._row("w", "Land_Wreck_Uaz", 0.5), self._row("z", "Land_Wreck_Uaz", 0.0)])
        self.assertEqual(out["str"]["apply_status"], "ok")
        w, z = out["rows"]
        self.assertEqual((w["max_hp"], w["health_hp"], w["health_mark_b"]), (-1.0, -1.0, 0.0))
        self.assertEqual((z["max_hp"], z["health_hp"], z["health_mark_b"]), (-1.0, -1.0, 1.0))
        status, reason, raw = self._spawn(0.5, cname="Land_Wreck_Uaz", op="spw")
        self.assertEqual((status, reason, raw["str"]["spawn_status"]), ("done", "", "ok"))
        self.assertEqual((raw["num"]["max_hp"], raw["num"]["health_hp"], raw["num"]["health_mark_b"]), (-1.0, -1.0, 0.0))

    def test_census_gives_qa_health_and_minus_one_only_for_world_objects_without_damage_system(self):
        out = self._apply([self._row("a", "WoodenCrate", 0.5)])
        crate_net = out["rows"][0]["net_id"]
        nums = {"center_x_m": CENTER[0], "center_z_m": CENTER[1], "radius_m": 115.0, "select_all_entityai_b": 1.0}
        status, reason, _p = _call(self.ext, "per_census_start", {"area_tag": "t"}, nums, op_id="c1")
        self.assertEqual((status, reason), ("done", ""))
        rows = {r["net_id"]: r for r in _job_rows(self.jobs, "c1")}
        self.assertEqual((rows[crate_net]["max_hp"], rows[crate_net]["health_hp"]), (100.0, 50.0))
        wreck = [r for r in rows.values() if r["class_name"] == "Land_Wreck_Uaz"]
        self.assertEqual([(r["max_hp"], r["health_hp"]) for r in wreck], [(-1.0, -1.0)])
        others = [r for r in rows.values() if r["class_name"] != "Land_Wreck_Uaz"]
        self.assertTrue(others)
        self.assertTrue(all(r["max_hp"] > 0.0 and r["health_hp"] > 0.0 for r in others))

    def test_no_pending_state_anywhere(self):
        self.assertFalse(hasattr(fake_ext_persist, "HEALTH_PENDING_MAX_MS"))
        self.assertNotIn("health_mark_pending", Path(fake_ext_persist.__file__).read_text(encoding="utf-8"))
        self.assertNotIn("health_mark_pending", PERSIST_C.read_text(encoding="utf-8"))


class StaticHealthMarkTests(unittest.TestCase):
    """La marca en lo que crea el QA es directa y verificada; la guarda HasDamageSystem queda para leer el mundo."""

    def setUp(self):
        self.text, self.code = _code(PERSIST_C)

    def test_apply_qa_health_mark_is_direct_and_verified(self):
        body = _block_after(self.code, r"protected\s+int\s+ApplyQaHealthMark\s*\([^)]*\)\s*\{")
        self.assertIsNotNone(body)
        self.assertNotIn("HasDamageSystem", body)  # directa: al crear, HasDamageSystem() aun da false (object.c:976)
        self.assertRegex(body, r"if\s*\(\s*ratio\s*<=\s*0\.0\s*\)\s*return\s+1;")
        self.assertRegex(body, r"if\s*\(\s*!obj\s*\|\|\s*maxHp\s*<=\s*0\.0\s*\)\s*return\s+0;")
        set_at = body.index("SetHealth(")
        self.assertLess(body.index("ReadQaHealth(obj, maxHp, healthHp)"), set_at)
        after = body[set_at:]
        self.assertIn("ReadQaHealth(obj, maxHp, healthHp)", after)  # relee tras aplicar
        self.assertRegex(after, r"if\s*\(\s*Math\.AbsFloat\(diff\)\s*<=\s*0\.01\s*\)\s*return\s+1;")
        self.assertIn("return 0;", after)

    def test_creation_paths_use_the_verified_mark_without_new_states(self):
        raw = _block_after(self.code, r"protected\s+void\s+HandleSpawnRaw\s*\([^)]*\)\s*\{")
        self.assertIsNotNone(raw)
        self.assertRegex(raw, r"healthMarkB\s*=\s*ApplyQaHealthMark\(cEnt,\s*hRatio,\s*maxHp,\s*healthHp\);")
        self.assertRegex(raw, r"ApplyQaHealthMark\(childEnt,\s*hRatio,")  # el hijo del control, por el mismo camino
        self.assertIn('PutStr(res.read, "spawn_status", "ok");', raw)
        self.assertRegex(raw, r'PutNum\(res\.read,\s*"health_mark_b",\s*healthMarkB\);')
        scene = _block_after(self.code, r"protected\s+void\s+HandleApplyScene\s*\([^)]*\)\s*\{")
        self.assertRegex(scene, r"rec\.m_HealthMarkB\s*=\s*ApplyQaHealthMark\(ent,\s*hRatio,\s*maxHp,\s*healthNow\);")
        # Creacion fallida: sin lectura de salud ni marca confirmada.
        self.assertRegex(scene, r"rec\.m_MaxHp\s*=\s*0\.0;\s*rec\.m_HealthHp\s*=\s*0\.0;\s*rec\.m_HealthMarkB\s*=\s*0;")
        for gone in ("health_mark_pending", "HealthPending", "QueueHealthMark", "SettleHealthMark", "ApplyHealthRatio",
                     "HEALTH_PENDING_MAX_MS"):
            self.assertNotIn(gone, self.code, gone)

    def test_health_mark_b_is_appended_after_the_old_apply_columns(self):
        emit = _block_after(self.code, r"protected\s+void\s+EmitApplyResponse\s*\([^)]*\)\s*\{")
        cols = _inserted(emit, "read.ncol")
        self.assertEqual(cols[-1], "health_mark_b")
        self.assertEqual(cols[-2], "spawn_tick_ms")
        self.assertEqual(cols[:-1], fake_ext_persist_apply_ncol()[:-1])
        self.assertEqual(cols, fake_ext_persist_apply_ncol())

    def test_on_tick_has_no_pending_retry(self):
        tick = _block_after(self.code, r"override\s+void\s+OnTick\s*\([^)]*\)\s*\{")
        self.assertTrue(tick.lstrip().startswith("TickWitness();"))
        self.assertNotIn("Health", tick)


def fake_ext_persist_apply_ncol():
    """Las columnas numericas de per_apply_scene que emite el fake (en orden): el .c las tiene que repetir."""
    peer, jobs, ext = _make_ext()
    status, _reason, payload = _call(
        ext, "per_apply_scene", {"scene_id": "s", "scene_op_id": "o", "expect_epoch": peer.inst, "q9_pathway": "a"},
        {"gen_n": 1.0},
        [{"logical_id": "a", "parent_id": "", "cat": "prop", "class_name": "Barrel_Yellow", "slot_name": "",
          "req_x_m": 6120.0, "req_z_m": 7600.0, "req_yaw_deg": 0.0, "health_mark_ratio": 0.5, "must_vanish_b": 1.0}],
    )
    return wire.unpack_payload(payload)["ncol"]


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
        # El tope de filas del testigo lo pone el JobMgr (AppendRow): ni HandleWitnessStart, ni
        # TickWitness, ni AppendWitnessRow escriben a mano el motivo ni truncan.
        witness_code = "".join(
            _block_after(self.code, header) or ""
            for header in (
                r"protected\s+void\s+HandleWitnessStart\s*\([^)]*\)\s*\{",
                r"protected\s+void\s+TickWitness\s*\(\s*\)\s*\{",
                r"protected\s+bool\s+AppendWitnessRow\s*\([^)]*\)\s*\{",
            )
        )
        self.assertNotIn('"rows_cap"', witness_code)
        # La unica aparicion en todo el .c es la purga de S-persist, que cierra su propio trabajo.
        self.assertEqual(self.code.count('"rows_cap"'), 1)
        purge_start = _block_after(self.code, r"protected\s+void\s+HandlePurgeStart\s*\([^)]*\)\s*\{")
        self.assertIn('m_Jobs.EndJob(m_PurgeJobId, "failed", "rows_cap");', purge_start)
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
        self.assertEqual(start.count("seen, selectAllB == 1))"), 4)  # las cuatro llamadas, con corte (S-persist)
        row = _block_after(self.code, r"protected\s+bool\s+AppendEntityCensusRow\s*\([^)]*\)\s*\{")
        self.assertRegex(row, r"if\s*\(withSurface\)\s*\{[^}]*g_Game\.SurfaceY\(pos\[0\],\s*pos\[2\]\)")
        self.assertIn("ReadRealLocation(obj,", row)  # parent_net_id, parent_class, slot_name y loc_kind reales

    def test_inv_children_counts_direct_children_except_in_select_all(self):
        # Sol sobre fb2dcb8: S-persist paso a contar hijos directos (su oraculo) y git lo aplico tambien al modo 1, que
        # el fake y F2 cuentan con todos los descendientes. El conteo depende ahora del modo.
        self.assertRegex(
            self.code,
            r"protected\s+void\s+ReadRealLocation\s*\([^)]*bool\s+proxyAsCargo\s*=\s*false,\s*bool\s+allDescendants\s*=\s*false\)",
        )
        loc = _block_after(self.code, r"protected\s+void\s+ReadRealLocation\s*\([^)]*\)\s*\{")
        self.assertRegex(
            loc,
            r"if\s*\(\s*chEnt\s*&&\s*chEnt\s*!=\s*ent\s*&&\s*\(\s*allDescendants\s*\|\|\s*chEnt\.GetHierarchyParent\(\)\s*==\s*ent\s*\)\s*\)",
        )
        row = _block_after(self.code, r"protected\s+bool\s+AppendEntityCensusRow\s*\([^)]*\)\s*\{")
        self.assertIn("invChildrenN, withSurface, withSurface);", row)
        calls = re.findall(r"ReadRealLocation\(([^;]*)\);", self.code)
        self.assertGreaterEqual(len(calls), 4)
        # solo el censo pasa el modo; las demas llamadas (apply, spawn raw, transiciones) cuentan hijos directos
        self.assertEqual([c for c in calls if "withSurface" in c], [c for c in calls if c.rstrip().endswith("withSurface, withSurface")])
        self.assertEqual(sum(1 for c in calls if "withSurface" in c), 1)

    def test_health_api_only_in_the_helpers_and_the_guard_for_the_world(self):
        # Object.GetMaxHealth/GetHealth/SetHealth: solo en ReadHealth (objetos del mundo, detras de HasDamageSystem: tiran
        # una excepcion de la VM sin sistema de daño, p. ej. Land_Wreck_Uaz), ReadQaHealth (lo que crea el QA, directa)
        # y ApplyQaHealthMark (SetHealth y relectura).
        code = self.code
        helpers = {}
        for ret, name in (("void", "ReadHealth"), ("void", "ReadQaHealth"), ("int", "ApplyQaHealthMark")):
            body = _block_after(code, r"protected\s+%s\s+%s\s*\([^)]*\)\s*\{" % (ret, name))
            self.assertIsNotNone(body, name)
            helpers[name] = body
        for call in ("GetMaxHealth(", "GetHealth(", "SetHealth("):
            total = code.count(call)
            inside = sum(b.count(call) for b in helpers.values())
            self.assertGreater(total, 0, call)
            self.assertEqual(total, inside, call + " fuera de los ayudantes")
        guarded = helpers["ReadHealth"]
        self.assertIn("!obj.HasDamageSystem()", guarded)
        self.assertLess(guarded.index("HasDamageSystem()"), guarded.index("GetMaxHealth("))
        self.assertIn("maxHp = -1.0;", guarded)
        self.assertIn("healthHp = -1.0;", guarded)
        self.assertNotIn("SetHealth(", helpers["ReadQaHealth"] + guarded)
        # La lectura directa, solo para lo que crea el QA: al crear, en el censo detras de IsQaCreated y en la marca de
        # t6 (sus dos llamadas exigen antes la clase centinela).
        row = _block_after(code, r"protected\s+bool\s+AppendEntityCensusRow\s*\([^)]*\)\s*\{")
        self.assertRegex(
            row,
            r"if\s*\(\s*IsQaCreated\(obj\)\s*\)\s*ReadQaHealth\(obj,\s*maxHp,\s*healthHp\);\s*else\s*ReadHealth\(obj,\s*maxHp,\s*healthHp\);",
        )
        qa = _block_after(code, r"protected\s+bool\s+IsQaCreated\s*\(\s*Object\s+obj\s*\)\s*\{")
        for needle in ("FindRecordByObject(obj) != null", "FindRawRecordByObject(obj) != null", "IsSentinelClass(obj.GetType())"):
            self.assertIn(needle, qa)
        # Definicion, 2 en ApplyQaHealthMark, censo, IsQaHealthMark y los 2 de la purga de S-persist
        # (AppendPurgeTreeRow y la emision de TickPurge), ambos tras el mismo IsQaCreated.
        purge_row = _block_after(code, r"protected\s+void\s+AppendPurgeTreeRow\s*\([^)]*\)\s*\{")
        self.assertRegex(
            purge_row,
            r"if\s*\(\s*IsQaCreated\(ent\)\s*\)\s*ReadQaHealth\(ent,\s*maxHp,\s*healthHp\);\s*else\s*ReadHealth\(ent,\s*maxHp,\s*healthHp\);",
        )
        purge_tick = _block_after(code, r"protected\s+void\s+TickPurge\s*\(\s*\)\s*\{")
        self.assertRegex(
            purge_tick,
            r"if\s*\(\s*IsQaCreated\(se\)\s*\)\s*ReadQaHealth\(se,\s*rowMaxHp,\s*rowHealthHp\);\s*else\s*ReadHealth\(se,\s*rowMaxHp,\s*rowHealthHp\);",
        )
        self.assertEqual(code.count("ReadQaHealth("), 7)
        self.assertEqual(len(re.findall(r"IsSentinelClass\([^;]*\)\s*&&\s*IsQaHealthMark\(", code)), 2)
        # y el testigo no lee salud.
        self.assertNotRegex(_code(WITNESS_C)[1], r"Get(Max)?Health\(")

    def test_surface_y_is_last_column_and_computed_when_the_row_is_emitted(self):
        self.assertEqual(WITNESS_NCOL[-1], "surface_y_m")
        self.assertEqual(_inserted(self.code, "m_WitnessNcol")[-1], "surface_y_m")
        row = _block_after(self.code, r"protected\s+bool\s+AppendWitnessRow\s*\([^)]*\)\s*\{")
        self.assertIn("nvals.Insert(g_Game.SurfaceY(x, z));", row)
        self.assertLess(row.index("nvals.Insert(aliveB)"), row.index("SurfaceY(x, z)"))  # ultima de ncol
        # La muestra 0 no lo calcula en Capture ni en EEInit: el gancho de 4_World no llama a SurfaceY.
        self.assertNotIn("SurfaceY", _code(WITNESS_C)[1])
        tick = _block_after(self.code, r"protected\s+void\s+TickWitness\s*\(\s*\)\s*\{")
        self.assertNotIn("SurfaceY", tick)  # solo AppendWitnessRow la consulta, al emitir cada fila

    def test_sample0_row_uses_ids_read_at_the_first_tick(self):
        tick = _block_after(self.code, r"protected\s+void\s+TickWitness\s*\(\s*\)\s*\{")
        self.assertIn("s0Net = FormatNetId(s0.m_Ent)", tick)
        self.assertRegex(tick, r"AppendWitnessRow\(jid,\s*0,\s*s0\.m_ClassName,\s*s0Net,\s*s0Parent,")
        self.assertNotRegex(tick, r"AppendWitnessRow\(jid,\s*0,[^;]*cap\.m_NetId")
        self.assertLess(tick.index("s0Net = FormatNetId"), tick.index("for (int f = 0"))  # las filas 0 van antes que el seguimiento
        raw = WITNESS_C.read_bytes().decode("utf-8")
        self.assertIn("ECE_INITAI", raw)  # limitacion de ai_agent_b documentada

    def test_follow_after_capture_order_in_tick(self):
        tick = _block_after(self.code, r"protected\s+void\s+TickWitness\s*\(\s*\)\s*\{")
        self.assertLess(tick.index("for (int c = 0"), tick.index("for (int f = 0"))  # capturas antes que seguimiento
        self.assertLess(tick.index("m_WitnessFollow.Insert(nf)"), tick.index("int fCount = m_WitnessFollow.Count()"))

    def test_proxycargo_only_in_mode1(self):
        sig = re.search(r"protected\s+void\s+ReadRealLocation\s*\([^)]*\)", self.code).group(0)
        self.assertIn("bool proxyAsCargo = false", sig)  # por defecto apagado: los demas llamadores no cambian
        body = _block_after(self.code, r"protected\s+void\s+ReadRealLocation\s*\([^)]*\)\s*\{")
        self.assertRegex(body, r"proxyAsCargo\s*&&\s*locType\s*==\s*InventoryLocationType\.PROXYCARGO\s*&&\s*parObj")
        calls = re.findall(r"ReadRealLocation\(([^;]*)\);", self.code)
        flagged = [c for c in calls if c.rstrip().endswith("withSurface")]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(len(calls), 5)  # 4 llamadores previos sin tocar y el del censo

    def test_spawn_parent_of_location_must_be_the_target(self):
        body = _block_after(self.code, r"protected\s+void\s+HandleSpawnRaw\s*\([^)]*\)\s*\{")
        self.assertRegex(body, r"netLoc\.GetType\(\)\s*!=\s*InventoryLocationType\.CARGO\s*\|\|\s*netLoc\.GetParent\(\)\s*!=\s*netParEnt")
        self.assertLess(body.index("netLoc.GetParent() != netParEnt"), body.index("GameInventory.LocationCreateEntity(netLoc"))

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
        for path in (PERSIST_C, WITNESS_C, WITNESS_W_C, QA_DIR / "fake_ext_persist.py", Path(__file__)):
            self.assertNotIn(b"\r", path.read_bytes(), str(path))


if __name__ == "__main__":
    unittest.main()
