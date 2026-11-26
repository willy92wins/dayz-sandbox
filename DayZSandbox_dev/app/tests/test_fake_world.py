"""Pruebas unitarias sin red del mundo falso de F2 (`app/tests/fake_world.py`).

Cubre el contrato de los verbos de §3 (`read`, `apply`, `reset`, `observe`),
el modelo de §5, las enmiendas 1 (TOCTOU) y 2 (borrado propio este donde este),
y la fixture `fixtures/escena-sin-actores.json` contra el censo independiente.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
import unittest
from collections import Counter
from pathlib import Path

from app.backend.validate import validate
from app.tests.fake_world import (
    ECE_DYNAMIC_PERSISTENCY,
    ECE_INITAI,
    ECE_IN_INVENTORY,
    ECE_NOLIFETIME,
    ECE_NOPERSISTENCY_CHAR,
    ECE_NOPERSISTENCY_WORLD,
    ECE_PLACE_ON_SURFACE,
    FLAGS_AI,
    FLAGS_CHILD,
    FLAGS_CREATURE,
    FLAGS_INV_OWN,
    FLAGS_ROOT,
    FLAGS_STATIC,
    POS_TOL_M,
    SCENE_BATCH,
    WIRE_CAP,
    FakeWorld,
    build_plan,
    compute_plan_sha256,
    hash_doc,
    plan_from_rows,
    plan_sha256_of,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
SESS_A = "a1b2c3d4e5f60718"
SESS_B = "1122334455667788"
PLAN_COLUMNS = ("lid", "ci", "x_mm", "z_mm", "yaw_mdeg")


def _m(val):
    """mm (o milesimas) del cable v1.3 -> metros (o unidades); `None` se queda."""
    return None if val is None else val / 1000.0


def _plan_rows(plan: dict) -> list[list]:
    """Filas `[lid, ci, x_mm, z_mm, yaw_mdeg]` de las columnas v1.3."""
    return [list(r) for r in zip(*(plan[k] for k in PLAN_COLUMNS))]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _dist3(a: tuple[float, float, float] | list[float], b: tuple[float, float, float] | list[float]) -> float:
    return math.sqrt(
        (float(a[0]) - float(b[0])) ** 2
        + (float(a[1]) - float(b[1])) ** 2
        + (float(a[2]) - float(b[2])) ** 2
    )


def _canon_bytes(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _custom_ground(x: float, z: float) -> float:
    return 210.25 + 0.015 * float(x) - 0.008 * float(z)


def _make_order(
    world: FakeWorld,
    verb: str,
    args: dict,
    *,
    op_id: str = "op-01",
    session: str = SESS_A,
    epoch: str | None = None,
) -> dict:
    return {
        "op_id": op_id,
        "session": session,
        "epoch": world.epoch if epoch is None else epoch,
        "verb": verb,
        "args": args,
    }


def _foreign_snapshot(census_rows: list[dict]) -> dict[str, dict]:
    """Foto de todo lo no propio (`foreign` y `persistent`) para verificar invariante de pose/padre."""
    return {
        row["eid"]: copy.deepcopy(row)
        for row in census_rows
        if row["origin"] in ("foreign", "persistent")
    }


class TestFixtureEscenaSinActores(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = _load_json(FIXTURES / "catalog-m1.json")
        cls.basica = _load_json(FIXTURES / "escena-basica-cine.json")
        cls.sin_actores = _load_json(FIXTURES / "escena-sin-actores.json")

    def test_fixture_valida_con_cero_errores_y_contenido_exacto(self) -> None:
        errors = validate(self.sin_actores, self.catalog)
        self.assertEqual(errors, [])
        self.assertEqual(self.sin_actores["doc_id"], "d-7c19e2a5")
        self.assertEqual(
            self.sin_actores["name"], "Amanecer en Stary Sobor (sin actores)"
        )
        self.assertEqual(self.sin_actores["schema"], self.basica["schema"])
        self.assertEqual(self.sin_actores["map"], self.basica["map"])
        self.assertEqual(self.sin_actores["ambiente"], self.basica["ambiente"])
        self.assertEqual(self.sin_actores["cameras"], self.basica["cameras"])
        self.assertEqual(self.sin_actores["next"], self.basica["next"])

        expected_entities = [
            e for e in self.basica["entities"] if e["kind"] != "actor"
        ]
        self.assertEqual(self.sin_actores["entities"], expected_entities)
        counts = Counter(e["kind"] for e in self.sin_actores["entities"])
        self.assertEqual(counts["actor"], 0)
        self.assertEqual(counts["objeto"], 20)
        self.assertEqual(counts["infectado"], 10)
        self.assertEqual(counts["animal"], 3)
        self.assertEqual(len(self.sin_actores["entities"]), 33)


class TestFakeWorldBaseMixin:
    catalog: dict
    doc: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = _load_json(FIXTURES / "catalog-m1.json")
        cls.doc = _load_json(FIXTURES / "escena-sin-actores.json")

    def assertForeignUntouched(self, before: dict[str, dict], after_census: list[dict]) -> None:
        after = _foreign_snapshot(after_census)
        self.assertEqual(set(before.keys()), set(after.keys()))
        alive_eids = {row["eid"] for row in after_census}
        for eid, prev in before.items():
            cur = after[eid]
            self.assertEqual(cur["cls"], prev["cls"])
            self.assertEqual(cur["pos"], prev["pos"])
            self.assertEqual(cur["x"], prev["x"])
            self.assertEqual(cur["y"], prev["y"])
            self.assertEqual(cur["z"], prev["z"])
            self.assertEqual(cur["yaw"], prev["yaw"])
            self.assertEqual(cur["hp"], prev["hp"])
            self.assertEqual(cur["parent"], prev["parent"])
            self.assertEqual(cur["slot"], prev["slot"])
            self.assertEqual(cur["origin"], prev["origin"])
            # M2: su padre sigue vivo y es el mismo
            if prev["parent"] is not None:
                self.assertIn(prev["parent"], alive_eids)


class TestCase1Apply(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 1: Apply (§3.3) de la escena sin actores, flags (§3.7), lotes y deriva Q9."""

    def test_apply_positivo_33_entidades_suelo_inyectado_clases_flags_y_checkpoint(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=3, catalog=self.catalog)
        plan2 = build_plan(self.doc, rev=3, catalog=self.catalog)
        self.assertEqual(_canon_bytes(plan), _canon_bytes(plan2))

        ticks = 0

        def count_tick() -> None:
            nonlocal ticks
            ticks += 1

        order = _make_order(world, "scene.apply", plan, op_id="op-apply-1", session=SESS_A)
        status, reason, read = world.apply(order, check=lambda: None, tick=count_tick)

        self.assertEqual(status, "done")
        self.assertIsNone(reason)
        self.assertEqual(ticks, math.ceil(33 / SCENE_BATCH))  # 5 ticks para 33 filas con batch=8
        self.assertEqual(world.effects(SESS_A, "op-apply-1"), {"created": 33, "deleted": 0})
        self.assertEqual(world.storage_ops, 0)

        # Generacion y estado de la escena (§3.2, §3.3 etapa 6)
        self.assertEqual(read["epoch"], world.epoch)
        self.assertEqual(
            read["generation"],
            {
                "session": SESS_A,
                "op_id": "op-apply-1",
                "rev": 3,
                "hash": hash_doc(self.doc),
                "plan_sha256": plan["plan_sha256"],
            },
        )
        self.assertEqual(read["registry_n"], 33)
        self.assertEqual(len(read["registry_sha256"]), 64)
        self.assertEqual(
            read["scene"],
            {
                "doc_id": self.doc["doc_id"],
                "gen_n": 1,
                "n": 33,
                "retained_n": 0,
                "retained": [],
                "pending": None,
                "last": {
                    "session": SESS_A,
                    "op_id": "op-apply-1",
                    "verb": "scene.apply",
                    "outcome": "done",
                },
            },
        )

        # Censo independiente: 33 entidades en (x, gy, z) con sus clases y flags (§3.7)
        census = world.census()
        self.assertEqual(len(census), 33)
        self.assertEqual(
            Counter(c["cls"] for c in census),
            Counter(e["cls"] for e in self.doc["entities"]),
        )

        self.assertEqual(
            FLAGS_STATIC,
            ECE_PLACE_ON_SURFACE | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD | ECE_NOPERSISTENCY_CHAR,
        )
        self.assertEqual(FLAGS_STATIC, 29361188)
        self.assertEqual(FLAGS_CREATURE, FLAGS_STATIC | ECE_INITAI)
        self.assertEqual(FLAGS_CREATURE, 29363236)
        self.assertEqual(
            FLAGS_CHILD,
            ECE_IN_INVENTORY | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD | ECE_NOPERSISTENCY_CHAR,
        )
        self.assertEqual(ECE_DYNAMIC_PERSISTENCY, 33554432)

        for c in census:
            self.assertEqual(c["origin"], "sandbox")
            self.assertEqual(c["scene"], self.doc["doc_id"])
            self.assertIsNone(c["parent"])
            self.assertIsNone(c["slot"])
            self.assertEqual(c["flags"] & ECE_DYNAMIC_PERSISTENCY, 0)
            if c["cls"].startswith(("Zmb", "Animal_")):
                self.assertEqual(c["flags"], FLAGS_CREATURE)
            else:
                self.assertEqual(c["flags"], FLAGS_ROOT)

        # Cada entidad del documento tiene correspondencia exacta en (x, gy, z) en el censo
        # (solo los objetos: las criaturas ya se han movido al soltar su IA, §5) y en el
        # checkpoint. X4-i lo mata la prueba de deriva con creature_drift_m > 0, no esta.
        obs = read["obs"]
        self.assertEqual(obs["at"], "checkpoint")
        self.assertEqual(len(obs["rows"]), 33)

        classes = plan["classes"]
        for idx, ent_doc in enumerate(self.doc["entities"]):
            lid = ent_doc["id"]
            ex = float(ent_doc["x"])
            ez = float(ent_doc["z"])
            eyaw = float(ent_doc["yaw"])
            egy = _custom_ground(ex, ez)

            cp_row = obs["rows"][idx]
            self.assertEqual(cp_row[0], lid)
            self.assertEqual(cp_row[1], classes.index(ent_doc["cls"]))
            # v1.3 §3.6: la fila del cable va en enteros (mm y milesimas de grado)
            self.assertTrue(all(type(v) is int for v in cp_row[1:]), cp_row)
            self.assertLess(
                _dist3((_m(cp_row[2]), _m(cp_row[3]), _m(cp_row[4])), (ex, egy, ez)),
                0.002,
            )
            self.assertEqual(cp_row[5], round(eyaw * 1000) % 360000)
            self.assertEqual(cp_row[6], round(egy * 1000))

            if ent_doc["cls"].startswith(("Zmb", "Animal_")):
                continue

            matches = [
                c for c in census
                if c["cls"] == ent_doc["cls"]
                and _dist3(c["pos"], (ex, egy, ez)) < 1e-6
                and abs(c["yaw"] - eyaw) < 1e-6
            ]
            self.assertEqual(len(matches), 1, f"no hallada en censo {lid}")

    def test_reapply_resetea_generacion_anterior_incluso_de_otra_sesion_y_lotes_custom(self) -> None:
        world = FakeWorld(ground=_custom_ground, batch=5)
        plan1 = build_plan(self.doc, rev=1, catalog=self.catalog)
        ticks_1 = 0

        def tick_counter_1() -> None:
            nonlocal ticks_1
            ticks_1 += 1

        st1, _, _ = world.apply(
            _make_order(world, "scene.apply", plan1, op_id="op-1", session=SESS_A),
            check=lambda: None,
            tick=tick_counter_1,
        )
        self.assertEqual(st1, "done")
        self.assertEqual(ticks_1, math.ceil(33 / 5))  # 7 ticks de creacion
        first_eids = {c["eid"] for c in world.census()}
        self.assertEqual(len(first_eids), 33)

        # Re-apply desde OTRA sesion del backend (mata X4-g y X4-h)
        plan2 = build_plan(self.doc, rev=2, catalog=self.catalog)
        ticks_2 = 0

        def tick_counter_2() -> None:
            nonlocal ticks_2
            ticks_2 += 1

        st2, rsn2, rd2 = world.apply(
            _make_order(world, "scene.apply", plan2, op_id="op-2", session=SESS_B),
            check=lambda: None,
            tick=tick_counter_2,
        )
        self.assertEqual(st2, "done")
        self.assertIsNone(rsn2)
        # 7 ticks para borrar 33 + 7 ticks para crear 33 = 14 ticks
        self.assertEqual(ticks_2, 14)
        self.assertEqual(world.effects(SESS_B, "op-2"), {"created": 33, "deleted": 33})
        self.assertEqual(rd2["scene"]["gen_n"], 2)
        self.assertEqual(rd2["scene"]["n"], 33)
        self.assertEqual(rd2["registry_n"], 33)

        second_census = world.census()
        self.assertEqual(len(second_census), 33)
        second_eids = {c["eid"] for c in second_census}
        self.assertTrue(first_eids.isdisjoint(second_eids))

    def test_deriva_criaturas_q9_checkpoint_antes_de_ia_y_now_despues(self) -> None:
        world = FakeWorld(ground=_custom_ground, tick_s=0.001, creature_drift_m=1.5)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, _, rd = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-drift"),
            check=lambda: None,
            tick=world.tick,
        )
        self.assertEqual(st, "done")

        by_lid_doc = {e["id"]: e for e in self.doc["entities"]}
        for row in rd["obs"]["rows"]:
            lid, _ci, x, y, z, _yaw, gy = row
            edoc = by_lid_doc[lid]
            target = (float(edoc["x"]), _custom_ground(edoc["x"], edoc["z"]), float(edoc["z"]))
            # Checkpoint tomado antes de soltar la IA: < 0,5 m incluso en zmb y ani (mata X4-i)
            self.assertLess(_dist3((_m(x), _m(y), _m(z)), target), POS_TOL_M)
            self.assertEqual(gy, round(target[1] * 1000))

        # Un par de ticks adicionales tras el apply
        world.tick()
        world.tick()

        st_now, _, rd_now = world.observe(
            _make_order(
                world,
                "scene.observe",
                {"doc_id": self.doc["doc_id"], "at": "now"},
                op_id="obs-now",
            )
        )
        self.assertEqual(st_now, "done")
        now_by_lid = {r[0]: r for r in rd_now["obs"]["rows"]}
        self.assertEqual(len(now_by_lid), 33)

        for lid, edoc in by_lid_doc.items():
            r = now_by_lid[lid]
            target = (float(edoc["x"]), _custom_ground(edoc["x"], edoc["z"]), float(edoc["z"]))
            dist = _dist3((_m(r[1]), _m(r[2]), _m(r[3])), target)
            if lid.startswith(("zmb-", "ani-")):
                self.assertGreaterEqual(dist, POS_TOL_M, f"{lid} no derivo tras soltar IA")
            else:
                self.assertLess(dist, 0.002, f"objeto estatico {lid} se movio")

        # Ademas verificamos contra el censo independiente que las 13 criaturas se desplazaron
        census = world.census()
        creatures_census = [c for c in census if c["cls"].startswith(("Zmb", "Animal_"))]
        self.assertEqual(len(creatures_census), 13)
        for c in creatures_census:
            # Ninguna coincide ya con las coordenadas originales de su clase
            orig_candidates = [
                e for e in self.doc["entities"] if e["cls"] == c["cls"]
            ]
            min_d = min(
                _dist3(c["pos"], (e["x"], _custom_ground(e["x"], e["z"]), e["z"]))
                for e in orig_candidates
            )
            self.assertGreaterEqual(min_d, POS_TOL_M)

    def test_apply_negativos_suppress_create_y_displace_on_create(self) -> None:
        # 1) suppress_create: entidad creada y desaparecida en el mismo tick -> 32 vivas en censo, fila ci=-1
        world = FakeWorld(ground=_custom_ground)
        world.suppress_create("obj-05")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-sup"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        self.assertEqual(len(world.census()), 32)
        cp_by_lid = {r[0]: r for r in rd["obs"]["rows"]}
        gy_05 = round(_custom_ground(6224.0, 7668.0) * 1000)
        self.assertEqual(cp_by_lid["obj-05"], ["obj-05", -1, None, None, None, None, gy_05])

        # 2) displace_on_create: desplazada 0,6 m (> POS_TOL_M = 0,5 m y < 0,7 m)
        world2 = FakeWorld(ground=_custom_ground)
        world2.displace_on_create("obj-05", 0.6)
        st2, _, rd2 = world2.apply(
            _make_order(world2, "scene.apply", plan, op_id="op-disp"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st2, "done")
        cp2 = {r[0]: r for r in rd2["obs"]["rows"]}["obj-05"]
        target_05 = (6224.0, _custom_ground(6224.0, 7668.0), 7668.0)
        d3 = _dist3((_m(cp2[2]), _m(cp2[3]), _m(cp2[4])), target_05)
        self.assertAlmostEqual(d3, 0.6, places=3)
        self.assertGreater(d3, POS_TOL_M)
        self.assertLess(d3, 0.7)

        c_obj05 = [c for c in world2.census() if c["cls"] == "Land_Container_1Bo"]
        self.assertEqual(len(c_obj05), 1)
        self.assertAlmostEqual(_dist3(c_obj05[0]["pos"], target_05), 0.6, places=6)


class TestCase2EtapasSinEfecto(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 2: bad_plan, unknown_class, out_of_map, budget_exceeded y foreign_content_retained."""

    def _prepare_world_with_scene_and_bystanders(self) -> FakeWorld:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, _, _ = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-base"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st, "done")
        world.spawn_foreign("Barrel_Red", 6141.0, 7676.0, 45.0)
        world.seed_scene("d-22223333", [["obj-01", "WoodenCrate", 6100.0, 7600.0, 15.0]])
        return world

    def _assert_rejected_no_effect(
        self,
        world: FakeWorld,
        plan_args: dict,
        expected_reason: str,
        op_id: str,
    ) -> dict:
        before_census_bytes = _canon_bytes(world.census())
        before_read_bytes = _canon_bytes(world.read(self.doc["doc_id"]))
        ticks = 0

        def tick_cb() -> None:
            nonlocal ticks
            ticks += 1

        st, reason, rd = world.apply(
            _make_order(world, "scene.apply", plan_args, op_id=op_id),
            check=lambda: None,
            tick=tick_cb,
        )
        self.assertEqual(st, "rejected")
        self.assertEqual(reason, expected_reason)
        self.assertEqual(ticks, 0)
        self.assertEqual(world.effects(SESS_A, op_id), {"created": 0, "deleted": 0})
        self.assertEqual(_canon_bytes(world.census()), before_census_bytes)
        self.assertEqual(_canon_bytes(world.read(self.doc["doc_id"])), before_read_bytes)
        return rd

    def test_bad_plan_variantes_sin_efecto(self) -> None:
        world = self._prepare_world_with_scene_and_bystanders()
        base = build_plan(self.doc, rev=2, catalog=self.catalog)

        # lid duplicado
        dup = copy.deepcopy(base)
        dup["lid"][1] = dup["lid"][0]
        self._assert_rejected_no_effect(world, dup, "bad_plan", "op-bad-dup")

        # patron lid invalido (actor o numeracion 00)
        act_plan = copy.deepcopy(base)
        act_plan["lid"][0] = "act-01"
        self._assert_rejected_no_effect(world, act_plan, "bad_plan", "op-bad-act")

        zero_id = copy.deepcopy(base)
        zero_id["lid"][0] = "obj-00"
        self._assert_rejected_no_effect(world, zero_id, "bad_plan", "op-bad-zero")

        # ci fuera de rango
        bad_ci = copy.deepcopy(base)
        bad_ci["ci"][0] = len(bad_ci["classes"])
        self._assert_rejected_no_effect(world, bad_ci, "bad_plan", "op-bad-ci")

        # v1.3: solo enteros (un NaN, un Inf, un float o un bool no valen)
        nan_plan = copy.deepcopy(base)
        nan_plan["x_mm"][0] = float("nan")
        self._assert_rejected_no_effect(world, nan_plan, "bad_plan", "op-bad-nan")

        inf_plan = copy.deepcopy(base)
        inf_plan["z_mm"][0] = float("inf")
        self._assert_rejected_no_effect(world, inf_plan, "bad_plan", "op-bad-inf")

        float_plan = copy.deepcopy(base)
        float_plan["x_mm"][0] = float(float_plan["x_mm"][0])
        self._assert_rejected_no_effect(world, float_plan, "bad_plan", "op-bad-float")

        bool_plan = copy.deepcopy(base)
        bool_plan["ci"][0] = False
        self._assert_rejected_no_effect(world, bool_plan, "bad_plan", "op-bad-bool")

        # yaw_mdeg fuera de [0, 360000)
        yaw_neg = copy.deepcopy(base)
        yaw_neg["yaw_mdeg"][0] = -100
        self._assert_rejected_no_effect(world, yaw_neg, "bad_plan", "op-bad-yaw1")

        yaw_360 = copy.deepcopy(base)
        yaw_360["yaw_mdeg"][0] = 360000
        self._assert_rejected_no_effect(world, yaw_360, "bad_plan", "op-bad-yaw2")

        # plan_sha256 malformado
        bad_sha = copy.deepcopy(base)
        bad_sha["plan_sha256"] = "z" * 64
        self._assert_rejected_no_effect(world, bad_sha, "bad_plan", "op-bad-sha")

    def test_unknown_class_out_of_map_y_budget_exceeded_por_tipo_y_total(self) -> None:
        world = self._prepare_world_with_scene_and_bystanders()
        base = build_plan(self.doc, rev=2, catalog=self.catalog)

        # unknown_class (mata X4-l)
        unk_classes = ["ItemInexistenteMod_X"]
        unk_rows = [["obj-01", 0, 6188000, 7626000, 0]]
        unk = plan_from_rows(
            self.doc["doc_id"], 2, base["hash"], unk_classes, unk_rows, base["caps"]
        )
        self.assertEqual(
            unk["plan_sha256"],
            compute_plan_sha256(
                self.doc["doc_id"], 2, base["hash"], unk_classes,
                ["obj-01"], [0], [6188000], [7626000], [0],
            ),
        )
        self._assert_rejected_no_effect(world, unk, "unknown_class", "op-unk")

        # out_of_map: x < 0 y z > world_size (en mm)
        oom_low = copy.deepcopy(base)
        oom_low["x_mm"][0] = -1
        self._assert_rejected_no_effect(world, oom_low, "out_of_map", "op-oom-1")

        oom_high = copy.deepcopy(base)
        oom_high["z_mm"][0] = 15360001
        self._assert_rejected_no_effect(world, oom_high, "out_of_map", "op-oom-2")

        # budget_exceeded por cada tipo (20/10/3) y por caps.total (mata X4-m)
        cap_obj = copy.deepcopy(base)
        cap_obj["caps"]["objeto"] = 19
        self._assert_rejected_no_effect(world, cap_obj, "budget_exceeded", "op-cap-obj")

        cap_zmb = copy.deepcopy(base)
        cap_zmb["caps"]["infectado"] = 9
        self._assert_rejected_no_effect(world, cap_zmb, "budget_exceeded", "op-cap-zmb")

        cap_ani = copy.deepcopy(base)
        cap_ani["caps"]["animal"] = 2
        self._assert_rejected_no_effect(world, cap_ani, "budget_exceeded", "op-cap-ani")

        cap_tot = copy.deepcopy(base)
        cap_tot["caps"] = {"objeto": 20, "infectado": 10, "animal": 3, "total": 32}
        self._assert_rejected_no_effect(world, cap_tot, "budget_exceeded", "op-cap-tot")

    def test_d_plan_v122_con_rows_y_columnas_desalineadas_bad_plan(self) -> None:
        # §3.9 (d) del brief de F2-partida: v1.2.2 se rechaza con bad_plan, sin efecto
        world = self._prepare_world_with_scene_and_bystanders()
        base = build_plan(self.doc, rev=2, catalog=self.catalog)
        legacy = {
            "doc_id": base["doc_id"],
            "rev": base["rev"],
            "hash": base["hash"],
            "plan_sha256": base["plan_sha256"],
            "caps": {"objeto": 20, "infectado": 10, "animal": 3},
            "classes": base["classes"],
            "rows": [[lid, ci, _m(x), _m(z), _m(yaw)] for lid, ci, x, z, yaw in _plan_rows(base)],
        }
        self._assert_rejected_no_effect(world, legacy, "bad_plan", "op-v122")
        # aun con f2 y caps v1.3: sin columnas no hay plan
        legacy_f2 = dict(legacy, f2=1, caps=copy.deepcopy(base["caps"]))
        self._assert_rejected_no_effect(world, legacy_f2, "bad_plan", "op-v122-f2")
        # columnas de longitudes distintas
        for key in PLAN_COLUMNS:
            short = copy.deepcopy(base)
            short[key] = short[key][:-1]
            self._assert_rejected_no_effect(world, short, "bad_plan", "op-short-%s" % key)
        # una columna que no es lista
        not_list = copy.deepcopy(base)
        not_list["x_mm"] = {"0": 1}
        self._assert_rejected_no_effect(world, not_list, "bad_plan", "op-not-list")
        # positivo: el mismo plan en columnas se aplica
        st, rsn, _ = world.apply(
            _make_order(world, "scene.apply", base, op_id="op-v13-ok"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual((st, rsn), ("done", None))

    def test_caps_total_menos_uno_sin_total_y_ausente_falla_cerrado(self) -> None:
        world = self._prepare_world_with_scene_and_bystanders()
        base = build_plan(self.doc, rev=2, catalog=self.catalog)
        self.assertEqual(base["caps"]["total"], -1)
        # total ausente: el mod real lo leeria como 0 (DP-2) -> budget_exceeded sin efecto
        no_total = copy.deepcopy(base)
        del no_total["caps"]["total"]
        self._assert_rejected_no_effect(world, no_total, "budget_exceeded", "op-no-total")
        zero_total = copy.deepcopy(base)
        zero_total["caps"]["total"] = 0
        self._assert_rejected_no_effect(world, zero_total, "budget_exceeded", "op-zero-total")
        bad_total = copy.deepcopy(base)
        bad_total["caps"]["total"] = -2
        self._assert_rejected_no_effect(world, bad_total, "budget_exceeded", "op-bad-total")
        # total = -1: sin tope total, el plan se aplica
        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", base, op_id="op-total-none"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual((st, rsn), ("done", None))
        self.assertEqual(rd["scene"]["n"], 33)
        exact = copy.deepcopy(base)
        exact["caps"]["total"] = 33
        st, rsn, _ = world.apply(
            _make_order(world, "scene.apply", exact, op_id="op-total-33"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual((st, rsn), ("done", None))

    def test_foreign_content_retained_previo_y_toctou_en_etapa4(self) -> None:
        # 1) Etapa 3 previa: algo ajeno ya dentro de obj-17 -> rejected/foreign_content_retained sin efecto (mata X4-s)
        world = self._prepare_world_with_scene_and_bystanders()
        foreign_eid = world.spawn_foreign("Barrel_Blue", 6140.0, 7676.0, 0.0, inside="obj-17")
        plan2 = build_plan(self.doc, rev=2, catalog=self.catalog)
        self._assert_rejected_no_effect(
            world, plan2, "foreign_content_retained", "op-ret-pre"
        )

        # Si se retira el objeto ajeno al suelo, el apply ahora pasa en verde
        world.move_to_ground(foreign_eid)
        st_ok, rsn_ok, _ = world.apply(
            _make_order(world, "scene.apply", plan2, op_id="op-ret-cleared"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_ok, "done")
        self.assertIsNone(rsn_ok)

        # 2) Enmienda 1 (TOCTOU durante el reset previo de un apply):
        # Entre el primer y segundo lote de borrado entra un objeto ajeno en obj-17 ->
        # para sin crear nada, last.outcome = "retained" y error/foreign_content_retained.
        plan3 = build_plan(self.doc, rev=3, catalog=self.catalog)
        tick_n = 0

        def inject_on_first_tick() -> None:
            nonlocal tick_n
            tick_n += 1
            if tick_n == 1:
                world.spawn_foreign("WoodenCrate", 6140.0, 7676.0, 10.0, inside="obj-17")

        before_foreign = _foreign_snapshot(world.census())
        st_toc, rsn_toc, rd_toc = world.apply(
            _make_order(world, "scene.apply", plan3, op_id="op-ret-toctou"),
            check=lambda: None,
            tick=inject_on_first_tick,
        )
        self.assertEqual(st_toc, "error")
        self.assertEqual(rsn_toc, "foreign_content_retained")
        # D7/§3.3 paso 4: el apply para al encontrar la retencion; no procesa el resto
        self.assertEqual(
            world.effects(SESS_A, "op-ret-toctou"),
            {"created": 0, "deleted": 16},
        )
        self.assertIsNone(rd_toc["generation"])
        self.assertIsNone(rd_toc["scene"]["pending"])
        self.assertEqual(rd_toc["scene"]["n"], 17)
        self.assertEqual(rd_toc["scene"]["retained_n"], 1)
        self.assertEqual(rd_toc["scene"]["retained"], ["obj-17"])
        self.assertGreater(rd_toc["scene"]["n"], rd_toc["scene"]["retained_n"])
        self.assertEqual(
            rd_toc["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-ret-toctou",
                "verb": "scene.apply",
                "outcome": "retained",
            },
        )
        # En el censo de la escena principal quedan obj-17 y los restos sin procesar
        main_live = [c for c in world.census() if c["scene"] == self.doc["doc_id"]]
        self.assertEqual(len(main_live), 17)
        self.assertIn("SeaChest", [c["cls"] for c in main_live])
        # El ajeno previo en el suelo sigue intacto
        after_foreign = _foreign_snapshot(world.census())
        for eid, snap in before_foreign.items():
            self.assertEqual(after_foreign[eid], snap)


class TestCase3LeaseYPlazo(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 3: Comprobacion de lease y plazo antes de cada efecto (mata X4-q)."""

    def test_check_falla_antes_del_primer_efecto_en_apply_y_reset(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)

        for motivo in ("lease_expired", "expired"):
            op_id = f"op-pre-{motivo}"
            before_bytes = _canon_bytes(world.census())
            st, rsn, _ = world.apply(
                _make_order(world, "scene.apply", plan, op_id=op_id),
                check=lambda m=motivo: m,
                tick=lambda: None,
            )
            self.assertEqual(st, "rejected")
            self.assertEqual(rsn, motivo)
            self.assertEqual(world.effects(SESS_A, op_id), {"created": 0, "deleted": 0})
            self.assertEqual(_canon_bytes(world.census()), before_bytes)

        # Aplicar escena en verde y probar fallo previo en reset y en re-apply
        st_ok, _, _ = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-ok"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_ok, "done")

        for motivo in ("lease_expired", "expired"):
            before_bytes = _canon_bytes(world.census())
            before_rd = _canon_bytes(world.read(self.doc["doc_id"]))
            st_r, rsn_r, _ = world.reset(
                _make_order(
                    world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id=f"rst-pre-{motivo}"
                ),
                check=lambda m=motivo: m,
                tick=lambda: None,
            )
            self.assertEqual(st_r, "rejected")
            self.assertEqual(rsn_r, motivo)
            self.assertEqual(
                world.effects(SESS_A, f"rst-pre-{motivo}"),
                {"created": 0, "deleted": 0},
            )
            self.assertEqual(_canon_bytes(world.census()), before_bytes)
            self.assertEqual(_canon_bytes(world.read(self.doc["doc_id"])), before_rd)

    def test_check_falla_tras_5_creaciones_deja_pending_5_y_para(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        checks = 0

        def check_5() -> str | None:
            nonlocal checks
            checks += 1
            return "lease_expired" if checks > 5 else None

        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-cut-5"),
            check=check_5,
            tick=lambda: None,
        )
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "lease_expired")
        self.assertEqual(checks, 6)  # ninguna llamada adicional tras fallar en la 6.a
        self.assertEqual(world.effects(SESS_A, "op-cut-5"), {"created": 5, "deleted": 0})
        self.assertEqual(len(world.census()), 5)
        self.assertIsNone(rd["generation"])
        self.assertEqual(
            rd["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-cut-5", "n": 5},
        )
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-cut-5",
                "verb": "scene.apply",
                "outcome": "interrupted",
            },
        )

    def test_check_falla_durante_reset_de_generacion_anterior_y_en_scene_reset(self) -> None:
        # 1) Durante etapa 4 (reset de la generacion anterior en apply)
        world = FakeWorld(ground=_custom_ground)
        plan1 = build_plan(self.doc, rev=1, catalog=self.catalog)
        world.apply(
            _make_order(world, "scene.apply", plan1, op_id="op-gen1"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(len(world.census()), 33)

        plan2 = build_plan(self.doc, rev=2, catalog=self.catalog)
        checks = 0

        def check_del_5() -> str | None:
            nonlocal checks
            checks += 1
            return "expired" if checks > 5 else None

        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", plan2, op_id="op-del-cut"),
            check=check_del_5,
            tick=lambda: None,
        )
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "expired")
        self.assertEqual(checks, 6)
        self.assertEqual(world.effects(SESS_A, "op-del-cut"), {"created": 0, "deleted": 5})
        self.assertEqual(len(world.census()), 28)
        self.assertIsNone(rd["generation"])  # al primer borrado generation pasa a null
        self.assertIsNone(rd["scene"]["pending"])
        self.assertEqual(rd["scene"]["n"], 28)
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-del-cut",
                "verb": "scene.apply",
                "outcome": "interrupted",
            },
        )

        # 2) Durante un scene.reset directo sobre las 28 restantes: corta tras 5 mas
        checks_r = 0

        def check_rst_5() -> str | None:
            nonlocal checks_r
            checks_r += 1
            return "lease_expired" if checks_r > 5 else None

        st_r, rsn_r, rd_r = world.reset(
            _make_order(
                world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="op-rst-cut"
            ),
            check=check_rst_5,
            tick=lambda: None,
        )
        self.assertEqual(st_r, "error")
        self.assertEqual(rsn_r, "lease_expired")
        self.assertEqual(checks_r, 6)
        self.assertEqual(world.effects(SESS_A, "op-rst-cut"), {"created": 0, "deleted": 5})
        self.assertEqual(len(world.census()), 23)
        self.assertEqual(
            rd_r["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-rst-cut",
                "verb": "scene.reset",
                "outcome": "interrupted",
            },
        )


class TestCase4Compensacion(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 4: Compensacion en la misma orden y por if_pending (D8, mata X4-o y X4-p)."""

    def test_fail_create_en_fila_12_compensa_las_11_creadas_sin_tocar_resto(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        # Testigos que no pertenecen a la orden: ajeno en suelo y segunda escena
        world.spawn_foreign("SeaChest", 6194.2, 7638.2, 15.0)
        world.seed_scene(
            "d-0a0e0001",
            [
                ["obj-01", "WoodenCrate", 6150.0, 7650.0, 0.0],
                ["obj-02", "Barrel_Red", 6152.0, 7650.0, 0.0],
            ],
        )
        before_foreign = _foreign_snapshot(world.census())

        # Fila 12 (indice 11) es obj-12
        self.assertEqual(self.doc["entities"][11]["id"], "obj-12")
        world.fail_create("obj-12")

        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-fail-12"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "create_failed")
        self.assertEqual(
            world.effects(SESS_A, "op-fail-12"),
            {"created": 11, "deleted": 11},
        )
        self.assertIsNone(rd["generation"])
        self.assertIsNone(rd["scene"]["pending"])
        self.assertEqual(rd["scene"]["n"], 0)
        self.assertEqual(rd["scene"]["retained_n"], 0)
        self.assertEqual(rd["scene"]["retained"], [])
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-fail-12",
                "verb": "scene.apply",
                "outcome": "compensated",
            },
        )

        census = world.census()
        self.assertEqual([c for c in census if c["scene"] == self.doc["doc_id"]], [])
        self.assertEqual(len([c for c in census if c["scene"] == "d-0a0e0001"]), 2)
        self.assertForeignUntouched(before_foreign, census)

    def test_fail_create_en_fila_12_con_ajeno_en_una_de_las_11_retiene_esa(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        world.fail_create("obj-12")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)

        # Al terminar el lote 1 (filas 1..8, que incluye obj-07 LargeTent), metemos algo ajeno en obj-07
        tick_n = 0
        injected_eid: str | None = None

        def inject_after_first_batch() -> None:
            nonlocal tick_n, injected_eid
            tick_n += 1
            if tick_n == 1:
                injected_eid = world.spawn_foreign(
                    "WoodenCrate", 6144.0, 7670.0, 200.0, inside="obj-07"
                )

        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-fail-ret"),
            check=lambda: None,
            tick=inject_after_first_batch,
        )
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "create_failed")
        self.assertIsNotNone(injected_eid)
        self.assertEqual(
            world.effects(SESS_A, "op-fail-ret"),
            {"created": 11, "deleted": 10},
        )
        self.assertEqual(rd["scene"]["n"], 1)
        self.assertEqual(rd["scene"]["retained_n"], 1)
        self.assertEqual(rd["scene"]["retained"], ["obj-07"])
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-fail-ret",
                "verb": "scene.apply",
                "outcome": "retained",
            },
        )

        # En el censo quedan exactamente obj-07 y el objeto ajeno dentro de obj-07
        census = world.census()
        self.assertEqual(len(census), 2)
        obj07 = [c for c in census if c["origin"] == "sandbox"][0]
        foreign_c = [c for c in census if c["origin"] == "foreign"][0]
        self.assertEqual(obj07["cls"], "LargeTent")
        self.assertEqual(foreign_c["eid"], injected_eid)
        self.assertEqual(foreign_c["parent"], obj07["eid"])
        self.assertEqual(foreign_c["slot"], "cargo")

    def test_reset_if_pending_compensa_solo_esa_orden_y_rechaza_not_pending(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        world.spawn_foreign("Barrel_Yellow", 6188.0, 7626.0, 0.0)
        world.seed_scene("d-0a0e0002", [["obj-01", "SeaChest", 6120.0, 7620.0, 90.0]])
        before_foreign = _foreign_snapshot(world.census())

        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        checks = 0

        def cut_after_5() -> str | None:
            nonlocal checks
            checks += 1
            return "lease_expired" if checks > 5 else None

        st_a, _, rd_a = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-pend-1", session=SESS_A),
            check=cut_after_5,
            tick=lambda: None,
        )
        self.assertEqual(st_a, "error")
        self.assertEqual(
            rd_a["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-pend-1", "n": 5},
        )

        # Negativo 1: otro op_id en if_pending -> rejected/not_pending sin efecto
        before_c = _canon_bytes(world.census())
        st_bad1, rsn_bad1, _ = world.reset(
            _make_order(
                world,
                "scene.reset",
                {
                    "doc_id": self.doc["doc_id"],
                    "if_pending": {"session": SESS_A, "op_id": "op-otro"},
                },
                op_id="rst-wrong-1",
                session=SESS_B,
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_bad1, "rejected")
        self.assertEqual(rsn_bad1, "not_pending")
        self.assertEqual(world.effects(SESS_B, "rst-wrong-1"), {"created": 0, "deleted": 0})
        self.assertEqual(_canon_bytes(world.census()), before_c)

        # Negativo 2: otra session en if_pending -> rejected/not_pending sin efecto
        st_bad2, rsn_bad2, _ = world.reset(
            _make_order(
                world,
                "scene.reset",
                {
                    "doc_id": self.doc["doc_id"],
                    "if_pending": {"session": SESS_B, "op_id": "op-pend-1"},
                },
                op_id="rst-wrong-2",
                session=SESS_B,
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_bad2, "rejected")
        self.assertEqual(rsn_bad2, "not_pending")
        self.assertEqual(_canon_bytes(world.census()), before_c)

        # Positivo: if_pending coincidente -> borra solo los 5 registros de op-pend-1
        st_ok, rsn_ok, rd_ok = world.reset(
            _make_order(
                world,
                "scene.reset",
                {
                    "doc_id": self.doc["doc_id"],
                    "if_pending": {"session": SESS_A, "op_id": "op-pend-1"},
                },
                op_id="rst-comp-ok",
                session=SESS_B,
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_ok, "done")
        self.assertIsNone(rsn_ok)
        self.assertEqual(world.effects(SESS_B, "rst-comp-ok"), {"created": 0, "deleted": 5})
        self.assertIsNone(rd_ok["scene"]["pending"])
        self.assertEqual(rd_ok["scene"]["n"], 0)
        self.assertEqual(
            rd_ok["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-pend-1",
                "verb": "scene.apply",
                "outcome": "compensated",
            },
        )
        census_after = world.census()
        self.assertEqual([c for c in census_after if c["scene"] == self.doc["doc_id"]], [])
        self.assertEqual(len([c for c in census_after if c["scene"] == "d-0a0e0002"]), 1)
        self.assertForeignUntouched(before_foreign, census_after)

        # Negativo 3: una vez compensada (o con generacion viva y pending=null), if_pending da not_pending
        world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-live", session=SESS_B),
            check=lambda: None,
            tick=lambda: None,
        )
        before_live = _canon_bytes(world.census())
        st_bad3, rsn_bad3, _ = world.reset(
            _make_order(
                world,
                "scene.reset",
                {
                    "doc_id": self.doc["doc_id"],
                    "if_pending": {"session": SESS_B, "op_id": "op-live"},
                },
                op_id="rst-wrong-3",
                session=SESS_B,
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_bad3, "rejected")
        self.assertEqual(rsn_bad3, "not_pending")
        self.assertEqual(_canon_bytes(world.census()), before_live)


class TestCase5ResetNegativosA3(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 5: Reset (§3.4, D5, Enmienda 2 y todos los negativos de F2-A3)."""

    def _apply_main(self, world: FakeWorld) -> None:
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, _, _ = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-init"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st, "done")

    def test_hijos_propios_en_cargo_suelo_y_contenedor_ajeno_borrados_y_segundo_reset_idempotente(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)

        # Contenedor ajeno en el suelo (pegado a obj-17 para cazar X4-a) con un objeto ajeno dentro
        foreign_chest = world.spawn_foreign("SeaChest", 6140.2, 7676.2, 110.0)
        foreign_inside = world.spawn_foreign(
            "FirstAidKit", 6140.2, 7676.2, 110.0, inside=foreign_chest
        )
        # Otro ajeno en el suelo de la misma clase que obj-15 y pegado a el (mata X4-a)
        world.spawn_foreign("WoodenCrate", 6163.1, 7663.1, 30.0)

        # Segunda escena registrada (mata X4-e)
        world.seed_scene(
            "d-5ec00001",
            [
                ["obj-01", "WoodenCrate", 6163.5, 7663.5, 45.0],
                ["zmb-01", "ZmbM_FarmerFat_Brown", 6242.5, 7610.5, 180.0],
            ],
        )

        # Hijo propio 1 en el cargo de obj-17
        c1 = world.spawn_own_child(self.doc["doc_id"], "obj-17", "FirstAidKit", "obj-91")
        self.assertEqual(
            [c for c in world.census() if c["eid"] == c1][0]["flags"], FLAGS_CHILD
        )
        # Hijo propio 2 soltado en el suelo
        c2 = world.spawn_own_child(self.doc["doc_id"], "obj-17", "AmmoBox", "obj-92")
        world.move_to_ground(c2)
        # Hijo propio 3 metido dentro del contenedor AJENO (Enmienda 2)
        c3 = world.spawn_own_child(self.doc["doc_id"], "obj-15", "Pot", "obj-93")
        world.move_inside(c3, foreign_chest)

        before_foreign = _foreign_snapshot(world.census())
        before_sec = [
            copy.deepcopy(c) for c in world.census() if c["scene"] == "d-5ec00001"
        ]

        st, rsn, rd = world.reset(
            _make_order(world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-1"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        # 33 raices + 3 hijos propios = 36 borrados
        self.assertEqual(world.effects(SESS_A, "rst-1"), {"created": 0, "deleted": 36})
        self.assertIsNone(rd["generation"])
        self.assertEqual(rd["scene"]["n"], 0)
        self.assertEqual(rd["scene"]["retained_n"], 0)
        self.assertEqual(rd["scene"]["retained"], [])
        self.assertEqual(rd["scene"]["last"]["outcome"], "done")
        self.assertEqual(world.storage_ops, 0)

        after_census = world.census()
        self.assertEqual([c for c in after_census if c["scene"] == self.doc["doc_id"]], [])
        self.assertEqual(
            [c for c in after_census if c["scene"] == "d-5ec00001"], before_sec
        )
        self.assertForeignUntouched(before_foreign, after_census)
        # El objeto ajeno dentro de foreign_chest sigue dentro de foreign_chest
        fi_after = [c for c in after_census if c["eid"] == foreign_inside][0]
        self.assertEqual(fi_after["parent"], foreign_chest)

        # Segundo reset sobre la escena ya vacia -> done sin efectos ni ticks
        ticks_2 = 0

        def count_t2() -> None:
            nonlocal ticks_2
            ticks_2 += 1

        st2, rsn2, rd2 = world.reset(
            _make_order(world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-2"),
            check=lambda: None,
            tick=count_t2,
        )
        self.assertEqual(st2, "done")
        self.assertIsNone(rsn2)
        self.assertEqual(ticks_2, 0)
        self.assertEqual(world.effects(SESS_A, "rst-2"), {"created": 0, "deleted": 0})
        self.assertEqual(rd2["scene"]["n"], 0)
        self.assertEqual(world.storage_ops, 0)

        # Prueba antitautologia del contador storage_ops (mata X4-w si fuera constante)
        self.assertEqual(world.touch_storage(), 1)
        self.assertEqual(world.storage_ops, 1)

    def test_ajeno_dentro_de_obj_17_retiene_obj_17_en_su_pose_sin_mover_ajeno(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)

        obj17_before = [
            copy.deepcopy(c)
            for c in world.census()
            if c["scene"] == self.doc["doc_id"] and c["cls"] == "SeaChest"
        ][0]
        f_eid = world.spawn_foreign("FirstAidKit", 6140.0, 7676.0, 200.0, inside="obj-17")
        before_foreign = _foreign_snapshot(world.census())

        st, rsn, rd = world.reset(
            _make_order(
                world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-obj17"
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        # El mod devuelve done y su lectura ensena lo retenido (D6, mata X4-b y X4-c)
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        self.assertEqual(world.effects(SESS_A, "rst-obj17"), {"created": 0, "deleted": 32})
        self.assertIsNone(rd["generation"])
        self.assertEqual(rd["scene"]["n"], 1)
        self.assertEqual(rd["scene"]["retained_n"], 1)
        self.assertEqual(rd["scene"]["retained"], ["obj-17"])
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "rst-obj17",
                "verb": "scene.reset",
                "outcome": "retained",
            },
        )
        self.assertEqual(world.storage_ops, 0)

        after_census = world.census()
        own_after = [c for c in after_census if c["scene"] == self.doc["doc_id"]]
        self.assertEqual(len(own_after), 1)
        self.assertEqual(own_after[0], obj17_before)
        self.assertForeignUntouched(before_foreign, after_census)
        f_after = [c for c in after_census if c["eid"] == f_eid][0]
        self.assertEqual(f_after["parent"], obj17_before["eid"])
        self.assertEqual(f_after["slot"], "cargo")

    def test_ajeno_en_hijo_contenedor_dentro_de_obj_15_retiene_cadena_entera(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)

        # Hijo contenedor nivel 1 dentro de obj-15 y nieto contenedor nivel 2 dentro de hijo 1
        child1_eid = world.spawn_own_child(
            self.doc["doc_id"], "obj-15", "CourierBag", "obj-81"
        )
        child2_eid = world.spawn_own_child(
            self.doc["doc_id"], "obj-81", "FirstAidKit", "obj-82"
        )
        # Hijo hermano sin contenido ajeno dentro de obj-15 -> debe borrarse
        sibling_eid = world.spawn_own_child(
            self.doc["doc_id"], "obj-15", "Pot", "obj-83"
        )
        # Objeto ajeno dentro del nieto: X4-d exige retener la cadena entera, no solo el nieto
        f_eid = world.spawn_foreign("AmmoBox", 6163.0, 7663.0, 30.0, inside=child2_eid)
        before_foreign = _foreign_snapshot(world.census())

        st, rsn, rd = world.reset(
            _make_order(
                world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-chain"
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        # 33 raices + 3 hijos = 36 propios; se quedan 3 (obj-15, obj-81, obj-82) y se borran 33
        self.assertEqual(world.effects(SESS_A, "rst-chain"), {"created": 0, "deleted": 33})
        self.assertEqual(rd["scene"]["n"], 3)
        self.assertEqual(rd["scene"]["retained_n"], 3)
        self.assertEqual(set(rd["scene"]["retained"]), {"obj-15", "obj-81", "obj-82"})
        self.assertEqual(rd["scene"]["last"]["outcome"], "retained")
        self.assertEqual(world.storage_ops, 0)

        after_census = world.census()
        by_eid = {c["eid"]: c for c in after_census}
        self.assertNotIn(sibling_eid, by_eid)
        self.assertIn(child1_eid, by_eid)
        self.assertIn(child2_eid, by_eid)
        self.assertIn(f_eid, by_eid)

        obj15_eid = by_eid[child1_eid]["parent"]
        self.assertIsNotNone(obj15_eid)
        self.assertIn(obj15_eid, by_eid)
        self.assertEqual(by_eid[obj15_eid]["cls"], "WoodenCrate")
        self.assertIsNone(by_eid[obj15_eid]["parent"])
        self.assertEqual(by_eid[child2_eid]["parent"], child1_eid)
        self.assertEqual(by_eid[f_eid]["parent"], child2_eid)
        self.assertForeignUntouched(before_foreign, after_census)

    def test_hijo_de_segunda_escena_dentro_de_obj_16_retiene_obj_16(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)

        world.seed_scene("d-5ec00002", [["obj-01", "WoodenCrate", 6100.0, 7600.0, 0.0]])
        sec_child = world.spawn_own_child(
            "d-5ec00002", "obj-01", "FirstAidKit", "obj-51"
        )
        world.move_inside(sec_child, (self.doc["doc_id"], "obj-16"))
        sec_before = {
            c["eid"]: copy.deepcopy(c)
            for c in world.census()
            if c["scene"] == "d-5ec00002"
        }

        st, rsn, rd = world.reset(
            _make_order(
                world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-cross"
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        # Mata X4-f: el hijo de otra escena NO es borrable en esta escena, retiene obj-16
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        self.assertEqual(world.effects(SESS_A, "rst-cross"), {"created": 0, "deleted": 32})
        self.assertEqual(rd["scene"]["retained_n"], 1)
        self.assertEqual(rd["scene"]["retained"], ["obj-16"])
        self.assertEqual(rd["scene"]["last"]["outcome"], "retained")

        after = world.census()
        own_main = [c for c in after if c["scene"] == self.doc["doc_id"]]
        self.assertEqual(len(own_main), 1)
        self.assertEqual(own_main[0]["cls"], "WoodenCrate")

        sec_after = {c["eid"]: c for c in after if c["scene"] == "d-5ec00002"}
        self.assertEqual(sec_after, sec_before)
        self.assertEqual(sec_after[sec_child]["parent"], own_main[0]["eid"])

    def test_toctou_durante_scene_reset_y_fail_delete_y_stale_epoch(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)

        # TOCTOU en reset: entra algo ajeno en obj-17 tras el primer lote de borrado
        tick_n = 0

        def inject_mid_reset() -> None:
            nonlocal tick_n
            tick_n += 1
            if tick_n == 1:
                world.spawn_foreign("AmmoBox", 6140.0, 7676.0, 0.0, inside="obj-17")

        st, rsn, rd = world.reset(
            _make_order(
                world, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-toctou"
            ),
            check=lambda: None,
            tick=inject_mid_reset,
        )
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        self.assertEqual(rd["scene"]["retained"], ["obj-17"])
        self.assertEqual(rd["scene"]["last"]["outcome"], "retained")
        self.assertEqual(len([c for c in world.census() if c["scene"] == self.doc["doc_id"]]), 1)

        # D5: un borrado no confirmado para la operacion con interrupted/delete_failed.
        # obj-10 es el decimo borrado (tras obj-01..obj-09), asi que ya hubo efectos.
        world2 = FakeWorld(ground=_custom_ground)
        self._apply_main(world2)
        last_before = copy.deepcopy(world2.read(self.doc["doc_id"])["scene"]["last"])
        world2.fail_delete("obj-10", doc_id=self.doc["doc_id"])
        st_fd, rsn_fd, rd_fd = world2.reset(
            _make_order(
                world2, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-fd"
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_fd, "error")
        self.assertEqual(rsn_fd, "delete_failed")
        self.assertEqual(world2.effects(SESS_A, "rst-fd"), {"created": 0, "deleted": 9})
        self.assertEqual(rd_fd["scene"]["n"], 24)
        self.assertEqual(rd_fd["scene"]["retained_n"], 0)
        self.assertIsNone(rd_fd["generation"])
        self.assertEqual(
            rd_fd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "rst-fd",
                "verb": "scene.reset",
                "outcome": "interrupted",
            },
        )
        self.assertEqual(len(world2.census()), 24)
        self.assertEqual(len(world2.registry_snapshot()), 24)
        self.assertIn("obj-10", [r["lid"] for r in world2.registry_snapshot()])
        self.assertNotEqual(last_before, rd_fd["scene"]["last"])

        # D5: si el primer borrado no se confirma -> rejected/delete_failed y sin cambios (A14)
        world3 = FakeWorld(ground=_custom_ground)
        self._apply_main(world3)
        world3.fail_delete("obj-01", doc_id=self.doc["doc_id"])
        before_c3 = _canon_bytes(world3.census())
        before_r3 = _canon_bytes(world3.read(self.doc["doc_id"]))
        st_fd1, rsn_fd1, rd_fd1 = world3.reset(
            _make_order(
                world3, "scene.reset", {"doc_id": self.doc["doc_id"]}, op_id="rst-fd1"
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_fd1, "rejected")
        self.assertEqual(rsn_fd1, "delete_failed")
        self.assertEqual(world3.effects(SESS_A, "rst-fd1"), {"created": 0, "deleted": 0})
        self.assertEqual(_canon_bytes(world3.census()), before_c3)
        self.assertEqual(_canon_bytes(world3.read(self.doc["doc_id"])), before_r3)
        self.assertIsNotNone(rd_fd1["generation"])

        # Orden de reset con epoch viejo -> rejected/stale_epoch sin tocar nada
        old_epoch = "0123456789abcdef0123456789abcdef"
        if old_epoch == world2.epoch:
            old_epoch = "fedcba9876543210fedcba9876543210"
        before_c = _canon_bytes(world2.census())
        st_se, rsn_se, rd_se = world2.reset(
            _make_order(
                world2,
                "scene.reset",
                {"doc_id": self.doc["doc_id"]},
                op_id="rst-stale",
                epoch=old_epoch,
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_se, "rejected")
        self.assertEqual(rsn_se, "stale_epoch")
        self.assertEqual(rd_se, {})
        self.assertEqual(_canon_bytes(world2.census()), before_c)


class TestCase6Observe(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 6: Observe (§3.5 y §3.6) en checkpoint y now, y rechazo result_too_large."""

    def test_observe_checkpoint_y_now_formas_y_movimiento(self) -> None:
        world = FakeWorld(ground=_custom_ground)

        # Sin generacion viva -> checkpoint devuelve []
        st0, rsn0, rd0 = world.observe(
            _make_order(
                world,
                "scene.observe",
                {"doc_id": self.doc["doc_id"], "at": "checkpoint"},
                op_id="obs-empty",
            )
        )
        self.assertEqual(st0, "done")
        self.assertIsNone(rsn0)
        self.assertEqual(rd0["obs"], {"at": "checkpoint", "rows": []})

        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-obs"),
            check=lambda: None,
            tick=lambda: None,
        )

        # Hijo propio y objeto ajeno dentro de obj-17, y mover obj-01 2 m en X
        world.spawn_own_child(self.doc["doc_id"], "obj-17", "FirstAidKit", "obj-91")
        world.spawn_foreign("AmmoBox", 6140.0, 7676.0, 200.0, inside="obj-17")
        world.move_entity((self.doc["doc_id"], "obj-01"), dx=2.0)

        # Observe checkpoint: 7 elementos [lid, ci, x, y, z, yaw, gy], inmutable frente al movimiento posterior
        st_cp, _, rd_cp = world.observe(
            _make_order(
                world,
                "scene.observe",
                {"doc_id": self.doc["doc_id"], "at": "checkpoint"},
                op_id="obs-cp",
            )
        )
        self.assertEqual(st_cp, "done")
        self.assertEqual(rd_cp["obs"]["at"], "checkpoint")
        self.assertEqual(len(rd_cp["obs"]["rows"]), 33)
        cp_obj01 = {r[0]: r for r in rd_cp["obs"]["rows"]}["obj-01"]
        self.assertEqual(len(cp_obj01), 7)
        self.assertEqual(cp_obj01[2], 6188000)

        # Observe now: 8 elementos [lid, x, y, z, yaw, hp, n_own, n_foreign], solo raices (33)
        st_nw, _, rd_nw = world.observe(
            _make_order(
                world,
                "scene.observe",
                {"doc_id": self.doc["doc_id"], "at": "now"},
                op_id="obs-nw",
            )
        )
        self.assertEqual(st_nw, "done")
        self.assertEqual(rd_nw["obs"]["at"], "now")
        self.assertEqual(len(rd_nw["obs"]["rows"]), 33)
        nw_by_lid = {r[0]: r for r in rd_nw["obs"]["rows"]}

        nw_obj01 = nw_by_lid["obj-01"]
        self.assertEqual(len(nw_obj01), 8)
        # v1.3 §3.6: [lid, x_mm, y_mm, z_mm, yaw_mdeg, hp_milli, n_own, n_foreign], enteros
        self.assertTrue(all(type(v) is int for v in nw_obj01[1:]), nw_obj01)
        self.assertEqual(nw_obj01[1], 6190000)  # 6188 + 2 m
        self.assertAlmostEqual(
            nw_obj01[2], round(_custom_ground(6190.0, 7626.0) * 1000), delta=1
        )
        self.assertEqual(nw_obj01[5], 1000)
        self.assertEqual(nw_obj01[6], 0)
        self.assertEqual(nw_obj01[7], 0)

        nw_obj17 = nw_by_lid["obj-17"]
        self.assertEqual(nw_obj17[6], 1)  # n_own
        self.assertEqual(nw_obj17[7], 1)  # n_foreign

    def test_observe_supera_wire_cap_devuelve_rejected_result_too_large(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        # 65 raices superan comodamente los 3500 B tanto en now como en checkpoint
        rows = [
            [f"obj-{i:02d}", 0, 6000123 + 1000 * i, 7000456 + 1000 * i, 123456]
            for i in range(1, 66)
        ]
        classes = ["Land_Wreck_Volha_Police"]
        h = "a" * 64
        plan_big = plan_from_rows(
            "d-7c19e2a5", 1, h, classes, rows,
            {"objeto": 100, "infectado": 0, "animal": 0, "total": -1},
        )
        st_ap, _, _ = world.apply(
            _make_order(world, "scene.apply", plan_big, op_id="op-big"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_ap, "done")

        for mode in ("now", "checkpoint"):
            st_ob, rsn_ob, rd_ob = world.observe(
                _make_order(
                    world,
                    "scene.observe",
                    {"doc_id": "d-7c19e2a5", "at": mode},
                    op_id=f"obs-big-{mode}",
                )
            )
            self.assertEqual(st_ob, "rejected")
            self.assertEqual(rsn_ob, "result_too_large")
            self.assertEqual(rd_ob, {})


class TestCase7Restart(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 7: restart(epoch) limpia registro y ECE_NOPERSISTENCY_WORLD, conserva persistent (mata X4-t)."""

    def test_restart_vacia_registro_cambia_epoch_borra_sandbox_y_conserva_persistent(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        old_epoch = world.epoch

        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-pre-rst"),
            check=lambda: None,
            tick=lambda: None,
        )
        world.spawn_own_child(self.doc["doc_id"], "obj-17", "FirstAidKit", "obj-91")
        world.seed_scene("d-0a0e0999", [["obj-01", "WoodenCrate", 6100.0, 7600.0, 0.0]])
        world.spawn_foreign("Barrel_Red", 6120.0, 7620.0, 0.0, persistent=False)
        pers_eid = world.spawn_foreign(
            "SeaChest", 6130.0, 7630.0, 75.0, persistent=True
        )
        pers_before = [c for c in world.census() if c["eid"] == pers_eid][0]

        new_epoch = world.restart()
        self.assertEqual(len(new_epoch), 32)
        self.assertNotEqual(new_epoch, old_epoch)
        self.assertEqual(world.epoch, new_epoch)

        rd = world.read(self.doc["doc_id"])
        self.assertEqual(rd["epoch"], new_epoch)
        self.assertIsNone(rd["generation"])
        self.assertEqual(rd["registry_n"], 0)
        empty_sha = hashlib.sha256(b"[]").hexdigest()
        self.assertEqual(rd["registry_sha256"], empty_sha)
        self.assertEqual(
            rd["scene"],
            {
                "doc_id": self.doc["doc_id"],
                "gen_n": 0,
                "n": 0,
                "retained_n": 0,
                "retained": [],
                "pending": None,
                "last": None,
            },
        )

        census = world.census()
        self.assertEqual([c for c in census if c["origin"] == "sandbox"], [])
        self.assertEqual([c for c in census if c["origin"] == "foreign"], [])
        self.assertEqual(census, [pers_before])

        # Cualquier verbo con el epoch anterior se rechaza con stale_epoch
        st_old, rsn_old, _ = world.apply(
            _make_order(
                world, "scene.apply", plan, op_id="op-stale", epoch=old_epoch
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_old, "rejected")
        self.assertEqual(rsn_old, "stale_epoch")
        self.assertEqual(census, world.census())

        # Reinicio con epoch explicito
        explicit = "abcdef0123456789abcdef0123456789"
        self.assertEqual(world.restart(explicit), explicit)
        self.assertEqual(world.epoch, explicit)
        self.assertEqual(world.census(), [pers_before])


class TestCase8TamanosWireCap(TestFakeWorldBaseMixin, unittest.TestCase):
    """Caso 8: Tamanos en el cable (§3.6) por debajo de WIRE_CAP = 3500 B."""

    def test_resultado_apply_observe_y_reset_de_escena_sin_actores_caben_en_3500_bytes(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        order = _make_order(
            world, "scene.apply", plan, op_id="op-000001", session=SESS_A
        )

        poll_envelope = {
            "ok": True,
            "session": SESS_A,
            "conn": "c" * 16,
            "now_ms": 1700000000000,
            "order": {
                **order,
                "inst": "i" * 16,
                "conn": "c" * 16,
                "issued_ms": 1700000000000,
                "ttl_ms": 30000,
            },
        }
        poll_bytes = json.dumps(poll_envelope, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(poll_bytes), WIRE_CAP)

        st_ap, rsn_ap, rd_ap = world.apply(order, check=lambda: None, tick=lambda: None)
        self.assertEqual(st_ap, "done")
        apply_result_body = {
            "op_id": order["op_id"],
            "session": order["session"],
            "epoch": order["epoch"],
            "status": st_ap,
            "reason": rsn_ap,
            "dup": False,
            "read": rd_ap,
        }
        apply_bytes = json.dumps(apply_result_body, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(apply_bytes), WIRE_CAP)

        st_nw, rsn_nw, rd_nw = world.observe(
            _make_order(
                world,
                "scene.observe",
                {"doc_id": self.doc["doc_id"], "at": "now"},
                op_id="op-000002",
            )
        )
        self.assertEqual(st_nw, "done")
        obs_result_body = {
            "op_id": "op-000002",
            "session": SESS_A,
            "epoch": world.epoch,
            "status": st_nw,
            "reason": rsn_nw,
            "dup": False,
            "read": rd_nw,
        }
        obs_bytes = json.dumps(obs_result_body, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(obs_bytes), WIRE_CAP)

        st_rs, rsn_rs, rd_rs = world.reset(
            _make_order(
                world,
                "scene.reset",
                {"doc_id": self.doc["doc_id"]},
                op_id="op-000003",
            ),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual(st_rs, "done")
        rst_result_body = {
            "op_id": "op-000003",
            "session": SESS_A,
            "epoch": world.epoch,
            "status": st_rs,
            "reason": rsn_rs,
            "dup": False,
            "read": rd_rs,
        }
        rst_bytes = json.dumps(rst_result_body, separators=(",", ":")).encode("utf-8")
        self.assertLess(len(rst_bytes), WIRE_CAP)


class TestCase9AclaracionesM1M19(TestFakeWorldBaseMixin, unittest.TestCase):
    """Vuelta 3: una prueba por cada aclaracion M1-M19 de §13 y el cambio 5 de la v1.2."""

    def _reg(self, world: FakeWorld, doc_id: str, lid: str) -> dict | None:
        for rec in world.registry_snapshot():
            if rec["scene_id"] == doc_id and rec["lid"] == lid:
                return rec
        return None

    def _reg_eid(self, world: FakeWorld, doc_id: str, lid: str) -> str:
        rec = self._reg(world, doc_id, lid)
        self.assertIsNotNone(rec, f"registro no encontrado para {(doc_id, lid)!r}")
        return rec["eid"]

    def _apply(
        self,
        world: FakeWorld,
        plan: dict,
        op_id: str,
        *,
        session: str = SESS_A,
        check=None,
        tick=None,
        epoch: str | None = None,
    ):
        return world.apply(
            _make_order(world, "scene.apply", plan, op_id=op_id, session=session, epoch=epoch),
            check=check if check is not None else (lambda: None),
            tick=tick if tick is not None else (lambda: None),
        )

    def _reset(
        self,
        world: FakeWorld,
        op_id: str,
        *,
        args: dict | None = None,
        session: str = SESS_A,
        check=None,
        tick=None,
    ):
        if args is None:
            args = {"doc_id": self.doc["doc_id"]}
        return world.reset(
            _make_order(world, "scene.reset", args, op_id=op_id, session=session),
            check=check if check is not None else (lambda: None),
            tick=tick if tick is not None else (lambda: None),
        )

    def _apply_main(self, world: FakeWorld, *, rev: int = 1, op_id: str = "op-v3-base") -> dict:
        plan = build_plan(self.doc, rev=rev, catalog=self.catalog)
        st, rsn, _ = self._apply(world, plan, op_id)
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        return plan

    def test_m1_delete_failed_en_segundo_borrado_interrumpe_y_conserva_obj02(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        eid_01 = self._reg_eid(world, self.doc["doc_id"], "obj-01")
        eid_02 = self._reg_eid(world, self.doc["doc_id"], "obj-02")
        world.fail_delete("obj-02", doc_id=self.doc["doc_id"])

        st, rsn, rd = self._reset(world, "rst-m1b")
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "delete_failed")
        self.assertEqual(world.effects(SESS_A, "rst-m1b"), {"created": 0, "deleted": 1})
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "rst-m1b",
                "verb": "scene.reset",
                "outcome": "interrupted",
            },
        )
        reg_lids = [
            r["lid"] for r in world.registry_snapshot()
            if r["scene_id"] == self.doc["doc_id"]
        ]
        self.assertNotIn("obj-01", reg_lids)
        self.assertIn("obj-02", reg_lids)
        census_eids = {c["eid"] for c in world.census()}
        self.assertNotIn(eid_01, census_eids)
        self.assertIn(eid_02, census_eids)

    def test_m1_primer_borrado_no_confirmado_rechaza_sin_efecto_ni_cambio_de_last(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        world.fail_delete("obj-01", doc_id=self.doc["doc_id"])
        before_census = _canon_bytes(world.census())
        before_read = _canon_bytes(world.read(self.doc["doc_id"]))

        st, rsn, _ = self._reset(world, "rst-m1a")
        self.assertEqual(st, "rejected")
        self.assertEqual(rsn, "delete_failed")
        self.assertEqual(world.effects(SESS_A, "rst-m1a"), {"created": 0, "deleted": 0})
        self.assertEqual(_canon_bytes(world.census()), before_census)
        self.assertEqual(_canon_bytes(world.read(self.doc["doc_id"])), before_read)

    def test_m1_apply_que_falla_al_borrar_generacion_previa_no_crea_nada(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world, rev=1, op_id="op-gen1")
        world.fail_delete("obj-02", doc_id=self.doc["doc_id"])
        plan2 = build_plan(self.doc, rev=2, catalog=self.catalog)

        st, rsn, rd = self._apply(world, plan2, "op-gen2")
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "delete_failed")
        self.assertEqual(world.effects(SESS_A, "op-gen2"), {"created": 0, "deleted": 1})
        self.assertEqual(len(world.census()), 32)
        self.assertLess(len(world.census()), 34)
        self.assertIsNone(rd["generation"])
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-gen2",
                "verb": "scene.apply",
                "outcome": "interrupted",
            },
        )

    def test_m2_borrar_contenedor_propio_borra_su_hijo_y_ajeno_conserva_padre(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        obj17_eid = self._reg_eid(world, self.doc["doc_id"], "obj-17")
        obj07_eid = self._reg_eid(world, self.doc["doc_id"], "obj-07")
        child_eid = world.spawn_own_child(
            self.doc["doc_id"], "obj-07", "FirstAidKit", "obj-91"
        )
        f_eid = world.spawn_foreign("AmmoBox", 6140.0, 7676.0, 0.0, inside="obj-17")

        st, rsn, rd = self._reset(world, "rst-m2")
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        self.assertEqual(rd["scene"]["retained"], ["obj-17"])

        census = {c["eid"]: c for c in world.census()}
        self.assertNotIn(child_eid, census)
        self.assertNotIn(obj07_eid, census)
        self.assertIn(obj17_eid, census)
        self.assertIn(f_eid, census)
        self.assertEqual(census[f_eid]["parent"], obj17_eid)
        self.assertEqual(census[f_eid]["slot"], "cargo")

        rec17 = self._reg(world, self.doc["doc_id"], "obj-17")
        self.assertIsNotNone(rec17)
        self.assertEqual(rec17["eid"], obj17_eid)
        self.assertEqual(census[obj17_eid]["cls"], "SeaChest")

    def test_m3_restart_a_mitad_de_apply_para_con_stale_epoch_y_no_deja_rastro(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        ticks = 0

        def tick_restart() -> None:
            nonlocal ticks
            ticks += 1
            if ticks == 1:
                world.restart()

        st, rsn, rd = self._apply(world, plan, "op-m3", tick=tick_restart)
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "stale_epoch")
        self.assertEqual(world.registry_snapshot(), [])
        self.assertEqual(world.census(), [])
        self.assertEqual(rd["epoch"], world.epoch)
        self.assertIsNone(rd["generation"])
        self.assertEqual(rd["registry_n"], 0)

    def test_m4_registry_snapshot_vacio_justo_tras_restart(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        self.assertEqual(len(world.registry_snapshot()), 33)
        world.restart()
        self.assertEqual(world.registry_snapshot(), [])

    def test_m5_compensacion_if_pending_interrumpida_deja_last_del_apply_y_pending(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        checks = 0

        def cut_after_5() -> str | None:
            nonlocal checks
            checks += 1
            return "lease_expired" if checks > 5 else None

        st_a, _, rd_a = self._apply(world, plan, "op-pend-m5", check=cut_after_5)
        self.assertEqual(st_a, "error")
        self.assertEqual(
            rd_a["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-pend-m5", "n": 5},
        )

        checks_r = 0

        def cut_after_2() -> str | None:
            nonlocal checks_r
            checks_r += 1
            return "expired" if checks_r > 2 else None

        st, rsn, rd = self._reset(
            world,
            "rst-m5",
            args={
                "doc_id": self.doc["doc_id"],
                "if_pending": {"session": SESS_A, "op_id": "op-pend-m5"},
            },
            session=SESS_B,
            check=cut_after_2,
        )
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "expired")
        self.assertEqual(world.effects(SESS_B, "rst-m5"), {"created": 0, "deleted": 2})
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-pend-m5",
                "verb": "scene.apply",
                "outcome": "interrupted",
            },
        )
        self.assertEqual(
            rd["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-pend-m5", "n": 3},
        )

    def test_m6_apply_que_para_por_retencion_no_anula_pending_ajeno(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan_b = build_plan(self.doc, rev=1, catalog=self.catalog)
        checks = 0

        def cut_after_10() -> str | None:
            nonlocal checks
            checks += 1
            return "lease_expired" if checks > 10 else None

        st_b, _, rd_b = self._apply(world, plan_b, "op-pend-b", check=cut_after_10)
        self.assertEqual(st_b, "error")
        self.assertEqual(
            rd_b["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-pend-b", "n": 10},
        )

        injected = {"eid": None}
        ticks = 0

        def inject_in_obj09() -> None:
            nonlocal ticks
            ticks += 1
            if ticks == 1:
                injected["eid"] = world.spawn_foreign(
                    "AmmoBox", 6134.0, 7654.0, 0.0, inside="obj-09"
                )

        plan_a = build_plan(self.doc, rev=2, catalog=self.catalog)
        st_a, rsn_a, rd_a = self._apply(world, plan_a, "op-apply-a", tick=inject_in_obj09)
        self.assertEqual(st_a, "error")
        self.assertEqual(rsn_a, "foreign_content_retained")
        self.assertIsNotNone(injected["eid"])
        self.assertEqual(world.effects(SESS_A, "op-apply-a"), {"created": 0, "deleted": 8})
        self.assertEqual(
            rd_a["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-pend-b", "n": 2},
        )
        self.assertEqual(rd_a["scene"]["retained"], ["obj-09"])
        self.assertEqual(rd_a["scene"]["last"]["outcome"], "retained")

    def test_m8_barrera_permite_ajeno_desde_otro_hilo_sin_bloqueo_y_retiene_obj17(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        world.barrier_after(8)
        reached = world._barrier_reached
        release = world._barrier_release
        self.assertIsNotNone(reached)
        self.assertIsNotNone(release)
        result: dict = {}

        def run() -> None:
            result["r"] = self._reset(world, "rst-m8")

        th = threading.Thread(target=run, daemon=True)
        th.start()
        self.assertTrue(reached.wait(5.0), "la barrera no se alcanzo en 5 s")
        got_lock = world._lock.acquire(timeout=1.0)
        if got_lock:
            world._lock.release()
        self.assertTrue(got_lock, "el verbo retuvo el cerrojo durante la barrera")
        f_eid = world.spawn_foreign("AmmoBox", 6140.0, 7676.0, 0.0, inside="obj-17")
        release.set()
        th.join(10.0)
        self.assertFalse(th.is_alive(), "el verbo no termino tras liberar la barrera")

        st, rsn, rd = result["r"]
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        self.assertEqual(rd["scene"]["retained"], ["obj-17"])
        self.assertEqual(rd["scene"]["last"]["outcome"], "retained")
        census = {c["eid"]: c for c in world.census()}
        self.assertIn(f_eid, census)
        self.assertEqual(
            census[f_eid]["parent"], self._reg_eid(world, self.doc["doc_id"], "obj-17")
        )

    def test_m9_hijo_propio_registrado_durante_el_reset_impide_crear(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world, rev=1, op_id="op-m9-gen1")
        world.barrier_after(1)
        plan2 = build_plan(self.doc, rev=2, catalog=self.catalog)
        reached = world._barrier_reached
        release = world._barrier_release
        self.assertIsNotNone(reached)
        self.assertIsNotNone(release)
        result: dict = {}

        def run() -> None:
            result["r"] = self._apply(world, plan2, "op-m9")

        th = threading.Thread(target=run, daemon=True)
        th.start()
        self.assertTrue(reached.wait(5.0), "la barrera no se alcanzo en 5 s")
        got_lock = world._lock.acquire(timeout=1.0)
        if got_lock:
            world._lock.release()
        self.assertTrue(got_lock, "el verbo retuvo el cerrojo durante la barrera")
        child_eid = world.spawn_own_child(
            self.doc["doc_id"], "obj-07", "FirstAidKit", "obj-91"
        )
        release.set()
        th.join(10.0)
        self.assertFalse(th.is_alive(), "el verbo no termino tras liberar la barrera")

        st, rsn, rd = result["r"]
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "foreign_content_retained")
        self.assertEqual(world.effects(SESS_A, "op-m9"), {"created": 0, "deleted": 6})
        self.assertEqual(rd["scene"]["retained"], ["obj-07"])
        self.assertEqual(rd["scene"]["last"]["outcome"], "retained")
        census = {c["eid"]: c for c in world.census()}
        self.assertIn(child_eid, census)
        self.assertEqual(
            census[child_eid]["parent"], self._reg_eid(world, self.doc["doc_id"], "obj-07")
        )

    def test_m10_compensacion_respeta_scene_batch_en_cada_tick(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        world.fail_create("obj-12")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        snaps: list[dict] = []

        def record_tick() -> None:
            snaps.append(world.effects(SESS_A, "op-m10"))

        st, rsn, rd = self._apply(world, plan, "op-m10", tick=record_tick)
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "create_failed")
        self.assertEqual(world.effects(SESS_A, "op-m10"), {"created": 11, "deleted": 11})
        self.assertEqual(rd["scene"]["last"]["outcome"], "compensated")

        totals = [s["created"] + s["deleted"] for s in snaps]
        self.assertGreaterEqual(len(totals), 2)
        prev = 0
        for total in totals:
            self.assertLessEqual(total - prev, SCENE_BATCH)
            prev = total

    def test_m11_reset_que_ya_no_retiene_nada_pone_retention_a_cero(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        f_eid = world.spawn_foreign("AmmoBox", 6140.0, 7676.0, 0.0, inside="obj-17")

        st1, _, rd1 = self._reset(world, "rst-m11-1")
        self.assertEqual(st1, "done")
        self.assertEqual(rd1["scene"]["retained_n"], 1)
        self.assertEqual(rd1["scene"]["retained"], ["obj-17"])

        world.move_to_ground(f_eid)
        st2, rsn2, rd2 = self._reset(world, "rst-m11-2")
        self.assertEqual(st2, "done")
        self.assertIsNone(rsn2)
        self.assertEqual(rd2["scene"]["retained_n"], 0)
        self.assertEqual(rd2["scene"]["retained"], [])
        self.assertEqual(rd2["scene"]["n"], 0)

    def test_m12_escena_vacia_con_fail_create_rechaza_sin_tocar_last(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        world.fail_create("obj-01")
        before_last = copy.deepcopy(world.read(self.doc["doc_id"])["scene"]["last"])
        self.assertIsNone(before_last)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)

        st, rsn, rd = self._apply(world, plan, "op-m12")
        self.assertEqual(st, "rejected")
        self.assertEqual(rsn, "create_failed")
        self.assertEqual(world.effects(SESS_A, "op-m12"), {"created": 0, "deleted": 0})
        self.assertEqual(rd["scene"]["last"], before_last)
        self.assertEqual(world.census(), [])

    def test_m13_reset_if_pending_null_y_doc_id_invalido_rechazan_sin_efecto(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        before_census = _canon_bytes(world.census())
        before_read = _canon_bytes(world.read(self.doc["doc_id"]))

        st1, rsn1, _ = self._reset(
            world,
            "rst-m13-null",
            args={"doc_id": self.doc["doc_id"], "if_pending": None},
        )
        self.assertEqual(st1, "rejected")
        self.assertEqual(rsn1, "bad_args")
        self.assertEqual(world.effects(SESS_A, "rst-m13-null"), {"created": 0, "deleted": 0})

        st2, rsn2, _ = self._reset(world, "rst-m13-doc", args={"doc_id": "d-1234567"})
        self.assertEqual(st2, "rejected")
        self.assertEqual(rsn2, "bad_args")
        self.assertEqual(world.effects(SESS_A, "rst-m13-doc"), {"created": 0, "deleted": 0})

        # v1.3 §3.3: if_pending medio vacio (o con otros tipos) tampoco vale
        for idx, ip in enumerate(({"session": SESS_A, "op_id": ""},
                                  {"session": "", "op_id": "op-v3-base"},
                                  {"session": None, "op_id": None},
                                  {"session": ""})):
            st3, rsn3, _ = self._reset(
                world, f"rst-m13-half-{idx}",
                args={"f2": 1, "doc_id": self.doc["doc_id"], "if_pending": ip},
            )
            self.assertEqual((st3, rsn3), ("rejected", "bad_args"), ip)

        self.assertEqual(_canon_bytes(world.census()), before_census)
        self.assertEqual(_canon_bytes(world.read(self.doc["doc_id"])), before_read)

    def test_reset_con_if_pending_vacio_es_un_reset_normal(self) -> None:
        # v1.3 §3.3 (DP-2): `if_pending` va siempre; vacio = reset normal (borra toda la escena)
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        st, rsn, rd = self._reset(
            world,
            "rst-v13-normal",
            args={"f2": 1, "doc_id": self.doc["doc_id"],
                  "if_pending": {"session": "", "op_id": ""}},
        )
        self.assertEqual((st, rsn), ("done", None))
        self.assertEqual(world.effects(SESS_A, "rst-v13-normal"), {"created": 0, "deleted": 33})
        self.assertEqual(rd["scene"]["n"], 0)
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "rst-v13-normal",
                "verb": "scene.reset",
                "outcome": "done",
            },
        )
        self.assertIsNone(rd["generation"])
        self.assertEqual([c for c in world.census() if c["scene"] == self.doc["doc_id"]], [])

    def test_m14_apply_bad_plan_rev10_doc_id_classes_desordenadas_y_clase_sin_uso(self) -> None:
        cat2 = copy.deepcopy(self.catalog)
        cat2["classes"]["objeto"] = list(cat2["classes"]["objeto"]) + ["AmmoBox"]
        world = FakeWorld(ground=_custom_ground, classes=cat2)
        base = build_plan(self.doc, rev=2, catalog=cat2)
        before_census = _canon_bytes(world.census())

        def reject(plan: dict, op_id: str) -> None:
            st, rsn, _ = self._apply(world, plan, op_id)
            self.assertEqual(st, "rejected")
            self.assertEqual(rsn, "bad_plan")
            self.assertEqual(world.effects(SESS_A, op_id), {"created": 0, "deleted": 0})

        rev10 = copy.deepcopy(base)
        rev10["rev"] = 1234567890
        reject(rev10, "op-m14-rev")

        bad_doc = copy.deepcopy(base)
        bad_doc["doc_id"] = "d-1234567"
        reject(bad_doc, "op-m14-doc")

        unordered = copy.deepcopy(base)
        unordered["classes"] = list(reversed(unordered["classes"]))
        reject(unordered, "op-m14-unordered")

        extra_classes = sorted(set(base["classes"]) | {"AmmoBox"})
        ci_map = {c: i for i, c in enumerate(extra_classes)}
        unused = copy.deepcopy(base)
        unused["classes"] = extra_classes
        unused["ci"] = [ci_map[base["classes"][ci]] for ci in base["ci"]]
        unused["plan_sha256"] = plan_sha256_of(unused)
        reject(unused, "op-m14-unused")

        self.assertEqual(_canon_bytes(world.census()), before_census)

    def test_m15_now_normaliza_yaw_y_raiz_muerta_da_nulos_y_contadores_cero(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        world.suppress_create("obj-05")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, _, _ = self._apply(world, plan, "op-m15")
        self.assertEqual(st, "done")
        world.move_entity((self.doc["doc_id"], "obj-01"), yaw=359.9996)

        st_o, rsn_o, rd = world.observe(
            _make_order(
                world,
                "scene.observe",
                {"doc_id": self.doc["doc_id"], "at": "now"},
                op_id="obs-m15",
            )
        )
        self.assertEqual(st_o, "done")
        self.assertIsNone(rsn_o)
        rows = {r[0]: r for r in rd["obs"]["rows"]}
        self.assertEqual(len(rows["obj-01"]), 8)
        # §3.9 (b) en el mundo: 359,9996 grados -> 360000 al redondear -> 0 al normalizar
        self.assertEqual(rows["obj-01"][4], 0)
        self.assertEqual(rows["obj-05"], ["obj-05", None, None, None, None, None, 0, 0])
        # negativa: 359,9994 no se normaliza a 0
        world.move_entity((self.doc["doc_id"], "obj-01"), yaw=359.9994)
        _st, _rsn, rd2 = world.observe(
            _make_order(
                world,
                "scene.observe",
                {"doc_id": self.doc["doc_id"], "at": "now"},
                op_id="obs-m15-b",
            )
        )
        self.assertEqual({r[0]: r for r in rd2["obs"]["rows"]}["obj-01"][4], 359999)

    def test_m16_seed_scene_clase_desconocida_error_y_catalogo_intacto(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        n_before = len(world.catalog_classes())
        with self.assertRaises(ValueError):
            world.seed_scene(
                "d-0a0e0016", [["obj-01", "ItemInexistenteMod_X", 100.0, 100.0, 0.0]]
            )
        self.assertEqual(len(world.catalog_classes()), n_before)
        self.assertEqual(world.registry_snapshot(), [])
        self.assertEqual(world.census(), [])

    def test_m17_fail_delete_por_doc_id_no_afecta_a_la_otra_escena(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        other = "d-0a0e0017"
        world.seed_scene(other, [["obj-01", "WoodenCrate", 6100.0, 7600.0, 0.0]])
        world.fail_delete("obj-01", doc_id=self.doc["doc_id"])

        st_b, rsn_b, _ = self._reset(world, "rst-m17-other", args={"doc_id": other})
        self.assertEqual(st_b, "done")
        self.assertIsNone(rsn_b)
        self.assertEqual(world.effects(SESS_A, "rst-m17-other"), {"created": 0, "deleted": 1})
        self.assertEqual([c for c in world.census() if c["scene"] == other], [])

        st_a, rsn_a, _ = self._reset(world, "rst-m17-main")
        self.assertEqual(st_a, "rejected")
        self.assertEqual(rsn_a, "delete_failed")
        self.assertEqual(world.effects(SESS_A, "rst-m17-main"), {"created": 0, "deleted": 0})
        self.assertEqual(
            len([c for c in world.census() if c["scene"] == self.doc["doc_id"]]), 33
        )

    def test_m18_huerfana_sandbox_fuera_del_registro_sobrevive_al_reset(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        orphan_eid = world.spawn_orphan_sandbox("Barrel_Green", 6150.0, 7650.0, 0.0)

        st, rsn, _ = self._reset(world, "rst-m18")
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        census = {c["eid"]: c for c in world.census()}
        self.assertIn(orphan_eid, census)
        self.assertEqual(census[orphan_eid]["origin"], "sandbox")
        self.assertIsNone(census[orphan_eid]["scene"])
        self.assertNotIn(orphan_eid, [r["eid"] for r in world.registry_snapshot()])
        self.assertEqual(
            [c for c in world.census() if c["scene"] == self.doc["doc_id"]], []
        )

    def test_m19_x4d_ajeno_que_entra_y_sale_retiene_contenedor_y_ancestro(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        for i in range(1, 9):
            world.spawn_own_child(
                self.doc["doc_id"], "obj-07", "FirstAidKit", f"obj-9{i}"
            )
        inner_eid = world.spawn_own_child(
            self.doc["doc_id"], "obj-15", "CourierBag", "obj-81"
        )
        world.barrier_after(8)
        reached = world._barrier_reached
        release = world._barrier_release
        self.assertIsNotNone(reached)
        self.assertIsNotNone(release)
        state: dict = {"foreign": None, "ticks": 0}

        def tick_m19() -> None:
            state["ticks"] += 1
            if state["ticks"] == 2 and state["foreign"] is not None:
                world.move_to_ground(state["foreign"])

        result: dict = {}

        def run() -> None:
            result["r"] = self._reset(world, "rst-m19", tick=tick_m19)

        th = threading.Thread(target=run, daemon=True)
        th.start()
        self.assertTrue(reached.wait(5.0), "la barrera no se alcanzo en 5 s")
        got_lock = world._lock.acquire(timeout=1.0)
        if got_lock:
            world._lock.release()
        self.assertTrue(got_lock, "el verbo retuvo el cerrojo durante la barrera")
        state["foreign"] = world.spawn_foreign(
            "AmmoBox", 6163.0, 7663.0, 0.0, inside=inner_eid
        )
        release.set()
        th.join(10.0)
        self.assertFalse(th.is_alive(), "el verbo no termino tras liberar la barrera")

        st, rsn, rd = result["r"]
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        self.assertEqual(set(rd["scene"]["retained"]), {"obj-15", "obj-81"})
        self.assertEqual(rd["scene"]["retained_n"], 2)
        self.assertEqual(rd["scene"]["last"]["outcome"], "retained")

        census = {c["eid"]: c for c in world.census()}
        obj15_eid = self._reg_eid(world, self.doc["doc_id"], "obj-15")
        self.assertIn(obj15_eid, census)
        self.assertIn(inner_eid, census)
        self.assertEqual(census[inner_eid]["parent"], obj15_eid)
        self.assertIn(state["foreign"], census)
        self.assertGreaterEqual(state["ticks"], 2)
        self.assertIsNone(census[state["foreign"]]["parent"])

    def test_cambio5_ia_al_soltar_cambia_pose_en_el_mismo_tick_del_checkpoint(self) -> None:
        world = FakeWorld(ground=_custom_ground, tick_s=0.0, creature_drift_m=1.5)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, rsn, rd = self._apply(world, plan, "op-drift-mismo-tick")
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)

        cp_by_lid = {r[0]: r for r in rd["obs"]["rows"]}
        reg = {
            r["lid"]: r for r in world.registry_snapshot()
            if r["scene_id"] == self.doc["doc_id"]
        }
        census = {c["eid"]: c for c in world.census()}
        creatures = [lid for lid in cp_by_lid if lid.startswith(("zmb-", "ani-"))]
        self.assertEqual(len(creatures), 13)
        for lid in creatures:
            cp = cp_by_lid[lid]
            ent = census[reg[lid]["eid"]]
            dist = _dist3(ent["pos"], (_m(cp[2]), _m(cp[3]), _m(cp[4])))
            self.assertGreater(
                dist, POS_TOL_M, f"{lid} no cambio de pose al soltar la IA en el mismo tick"
            )

    def test_plan_normaliza_yaw_359_9999_y_359_9996_a_cero(self) -> None:
        doc2 = copy.deepcopy(self.doc)
        doc2["entities"] = [
            {
                "id": "obj-01",
                "kind": "objeto",
                "cls": "WoodenCrate",
                "x": 6100.0,
                "z": 7600.0,
                "yaw": 359.9999,
            },
            {
                "id": "obj-02",
                "kind": "objeto",
                "cls": "WoodenCrate",
                "x": 6102.0,
                "z": 7602.0,
                "yaw": 359.9996,
            },
        ]
        plan = build_plan(doc2, rev=1, catalog=self.catalog)
        self.assertEqual(plan["yaw_mdeg"][0], 0)
        self.assertEqual(plan["yaw_mdeg"][1], 0)

    def test_segundo_reset_con_solo_contenedor_retenido_que_guarda_ajeno_vuelve_a_retener(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        f_eid = world.spawn_foreign("AmmoBox", 6140.0, 7676.0, 0.0, inside="obj-17")

        st1, _, rd1 = self._reset(world, "rst-m22-1")
        self.assertEqual(st1, "done")
        self.assertEqual(rd1["scene"]["retained"], ["obj-17"])

        st2, rsn2, rd2 = self._reset(world, "rst-m22-2")
        self.assertEqual(st2, "done")
        self.assertIsNone(rsn2)
        self.assertEqual(rd2["scene"]["retained_n"], 1)
        self.assertEqual(rd2["scene"]["retained"], ["obj-17"])
        self.assertEqual(rd2["scene"]["last"]["outcome"], "retained")
        self.assertEqual(world.effects(SESS_A, "rst-m22-2"), {"created": 0, "deleted": 0})
        self.assertIn(f_eid, {c["eid"] for c in world.census()})

    def test_compensacion_if_pending_con_fail_delete_deja_pending_y_error_delete_failed(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        checks = 0

        def cut_after_5() -> str | None:
            nonlocal checks
            checks += 1
            return "lease_expired" if checks > 5 else None

        st_a, _, rd_a = self._apply(world, plan, "op-pend-m23", check=cut_after_5)
        self.assertEqual(st_a, "error")
        self.assertEqual(
            rd_a["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-pend-m23", "n": 5},
        )

        world.fail_delete("obj-03", doc_id=self.doc["doc_id"])
        st, rsn, rd = self._reset(
            world,
            "rst-m23",
            args={
                "doc_id": self.doc["doc_id"],
                "if_pending": {"session": SESS_A, "op_id": "op-pend-m23"},
            },
            session=SESS_B,
        )
        self.assertEqual(st, "error")
        self.assertEqual(rsn, "delete_failed")
        self.assertEqual(world.effects(SESS_B, "rst-m23"), {"created": 0, "deleted": 2})
        self.assertEqual(
            rd["scene"]["pending"],
            {"session": SESS_A, "op_id": "op-pend-m23", "n": 3},
        )
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-pend-m23",
                "verb": "scene.apply",
                "outcome": "interrupted",
            },
        )


class TestCase10Vuelta4(TestFakeWorldBaseMixin, unittest.TestCase):
    """Vuelta 4: compensaciones limitadas a su orden (D8, §3.4) y M3 de verdad."""

    def _reg(self, world: FakeWorld, doc_id: str, lid: str) -> dict | None:
        for rec in world.registry_snapshot():
            if rec["scene_id"] == doc_id and rec["lid"] == lid:
                return rec
        return None

    def _reg_eid(self, world: FakeWorld, doc_id: str, lid: str) -> str:
        rec = self._reg(world, doc_id, lid)
        self.assertIsNotNone(rec, f"registro no encontrado para {(doc_id, lid)!r}")
        return rec["eid"]

    def _apply(self, world, plan, op_id, *, session=SESS_A, check=None, tick=None):
        return world.apply(
            _make_order(world, "scene.apply", plan, op_id=op_id, session=session),
            check=check if check is not None else (lambda: None),
            tick=tick if tick is not None else (lambda: None),
        )

    def _reset(self, world, op_id, *, args=None, session=SESS_A, check=None, tick=None):
        if args is None:
            args = {"doc_id": self.doc["doc_id"]}
        return world.reset(
            _make_order(world, "scene.reset", args, op_id=op_id, session=session),
            check=check if check is not None else (lambda: None),
            tick=tick if tick is not None else (lambda: None),
        )

    def _apply_main(self, world, *, rev=1, op_id="op-v4-base"):
        plan = build_plan(self.doc, rev=rev, catalog=self.catalog)
        st, rsn, _ = self._apply(world, plan, op_id)
        self.assertEqual(st, "done")
        self.assertIsNone(rsn)
        return plan

    def test_q3a_compensacion_en_la_orden_cortada_por_el_plazo_no_borra_nada(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        world.fail_create("obj-12")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        calls = 0

        def check():
            nonlocal calls
            calls += 1
            return "expired" if calls > 12 else None

        st, rsn, rd = self._apply(world, plan, "op-q3", check=check)
        self.assertEqual((st, rsn), ("error", "create_failed"))
        self.assertEqual(world.effects(SESS_A, "op-q3"), {"created": 11, "deleted": 0})
        self.assertEqual(rd["scene"]["last"]["outcome"], "interrupted")
        self.assertEqual(
            rd["scene"]["pending"], {"session": SESS_A, "op_id": "op-q3", "n": 11}
        )

    def test_m2_reset_cortado_tras_borrar_obj17_no_deja_hijos_con_padre_muerto(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        doc_id = self.doc["doc_id"]
        roots = [
            r["lid"] for r in world.registry_snapshot() if r["parent_lid"] is None
        ]
        k17 = roots.index("obj-17") + 1
        e17 = self._reg_eid(world, doc_id, "obj-17")
        e18 = self._reg_eid(world, doc_id, "obj-18")
        world.move_inside((doc_id, "obj-18"), (doc_id, "obj-17"))
        calls = 0

        def check():
            nonlocal calls
            calls += 1
            return "expired" if calls > k17 else None

        st, rsn, _ = self._reset(world, "rst-m2", check=check)
        self.assertEqual((st, rsn), ("error", "expired"))
        census = {c["eid"]: c for c in world.census()}
        self.assertNotIn(e17, census)
        self.assertNotIn(e18, census)
        dead_parent = [
            c["eid"]
            for c in census.values()
            if c["parent"] is not None and c["parent"] not in census
        ]
        self.assertEqual(dead_parent, [])

    def test_m3b_restart_en_el_primer_tick_de_un_reset_no_escribe_last(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        doc_id = self.doc["doc_id"]
        ticks = 0

        def tick():
            nonlocal ticks
            ticks += 1
            if ticks == 1:
                world.restart()

        st, rsn, rd = self._reset(world, "rst-m3", tick=tick)
        self.assertEqual((st, rsn), ("error", "stale_epoch"))
        self.assertEqual(world.effects(SESS_A, "rst-m3"), {"created": 0, "deleted": 8})
        self.assertIsNone(rd["scene"]["last"])
        self.assertIsNone(world.read(doc_id)["scene"]["last"])

    def test_m3_restart_tras_la_ultima_creacion_no_publica_generation(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        doc_id = self.doc["doc_id"]
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        ticks = 0

        def tick():
            nonlocal ticks
            ticks += 1
            if ticks == 5:
                world.restart()

        st, rsn, rd = self._apply(world, plan, "op-pub", tick=tick)
        self.assertEqual((st, rsn), ("error", "stale_epoch"))
        self.assertEqual(world.effects(SESS_A, "op-pub"), {"created": 33, "deleted": 0})
        self.assertIsNone(rd["generation"])
        self.assertIsNone(world.read(doc_id)["generation"])

    def test_m3_restart_antes_del_primer_borrado_de_la_compensacion_no_escribe_last(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        doc_id = self.doc["doc_id"]
        world.fail_create("obj-12")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        calls = 0

        def check():
            nonlocal calls
            calls += 1
            if calls == 13:
                world.restart()
            return None

        st, rsn, rd = self._apply(world, plan, "op-comp", check=check)
        self.assertEqual((st, rsn), ("error", "stale_epoch"))
        self.assertEqual(world.effects(SESS_A, "op-comp"), {"created": 11, "deleted": 0})
        self.assertIsNone(rd["scene"]["last"])
        self.assertIsNone(world.read(doc_id)["scene"]["last"])

    def test_oah_if_pending_compensacion_solo_borra_su_orden_y_conserva_registro_ajeno(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        doc_id = self.doc["doc_id"]
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        calls = 0

        def cut5():
            nonlocal calls
            calls += 1
            return "lease_expired" if calls > 5 else None

        st_a, _, rd_a = self._apply(world, plan, "op-a", check=cut5)
        self.assertEqual(st_a, "error")
        self.assertEqual(
            rd_a["scene"]["pending"], {"session": SESS_A, "op_id": "op-a", "n": 5}
        )
        e30 = world.seed_record(
            doc_id, "obj-30", "WoodenCrate", 6100.0, 7600.0, SESS_B, "op-otra"
        )
        st, rsn, _ = self._reset(
            world,
            "rst-comp",
            args={
                "doc_id": doc_id,
                "if_pending": {"session": SESS_A, "op_id": "op-a"},
            },
            session=SESS_B,
        )
        self.assertEqual((st, rsn), ("done", None))
        self.assertEqual(world.effects(SESS_B, "rst-comp"), {"created": 0, "deleted": 5})
        self.assertIn(e30, {c["eid"] for c in world.census()})
        self.assertIsNotNone(self._reg(world, doc_id, "obj-30"))

    def test_oah_en_orden_compensacion_no_borra_registro_ajeno_sembrado_tras_el_primer_lote(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        doc_id = self.doc["doc_id"]
        world.fail_create("obj-12")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        box = {"eid": None}
        ticks = 0

        def tick():
            nonlocal ticks
            ticks += 1
            if ticks == 1:
                box["eid"] = world.seed_record(
                    doc_id, "obj-30", "WoodenCrate", 6100.0, 7600.0, SESS_B, "op-otra"
                )

        st, rsn, _ = self._apply(world, plan, "op-a12", tick=tick)
        self.assertEqual((st, rsn), ("error", "create_failed"))
        self.assertEqual(world.effects(SESS_A, "op-a12"), {"created": 11, "deleted": 11})
        self.assertIsNotNone(box["eid"])
        self.assertIn(box["eid"], {c["eid"] for c in world.census()})
        self.assertIsNotNone(self._reg(world, doc_id, "obj-30"))

    def test_o1_r1_if_pending_con_registro_de_otra_orden_queda_compensada(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        doc_id = self.doc["doc_id"]
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        calls = 0

        def cut5():
            nonlocal calls
            calls += 1
            return "lease_expired" if calls > 5 else None

        st_a, _, _ = self._apply(world, plan, "op-a", check=cut5)
        self.assertEqual(st_a, "error")
        e30 = world.seed_record(
            doc_id, "obj-30", "WoodenCrate", 6100.0, 7600.0, SESS_B, "op-otra"
        )
        world.spawn_foreign(
            "AmmoBox", 6100.0, 7600.0, 0.0, inside=(doc_id, "obj-30")
        )
        st, rsn, rd = self._reset(
            world,
            "rst-comp",
            args={
                "doc_id": doc_id,
                "if_pending": {"session": SESS_A, "op_id": "op-a"},
            },
            session=SESS_B,
        )
        self.assertEqual((st, rsn), ("done", None))
        self.assertEqual(world.effects(SESS_B, "rst-comp"), {"created": 0, "deleted": 5})
        self.assertEqual(rd["scene"]["last"]["outcome"], "compensated")
        self.assertEqual(rd["scene"]["retained"], [])
        self.assertEqual(rd["scene"]["retained_n"], 0)
        self.assertIn(e30, {c["eid"] for c in world.census()})

    def test_o2_r1_registro_de_otra_orden_en_el_primer_check_rechaza_sin_last(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        doc_id = self.doc["doc_id"]
        world.fail_create("obj-01")
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        box = {"n": 0, "eid": None}

        def check():
            box["n"] += 1
            if box["n"] == 1:
                box["eid"] = world.seed_record(
                    doc_id, "obj-30", "WoodenCrate", 6100.0, 7600.0, SESS_B, "op-otra"
                )
            return None

        st, rsn, rd = self._apply(world, plan, "op-m12", check=check)
        self.assertEqual((st, rsn), ("rejected", "create_failed"))
        self.assertEqual(world.effects(SESS_A, "op-m12"), {"created": 0, "deleted": 0})
        self.assertIsNone(rd["scene"]["last"])
        self.assertIn(box["eid"], {c["eid"] for c in world.census()})

    def test_m3b2_restart_en_el_ultimo_tick_de_un_reset_no_escribe_last(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        doc_id = self.doc["doc_id"]
        self._apply_main(world)
        ticks = 0

        def tick():
            nonlocal ticks
            ticks += 1
            if ticks == 5:
                world.restart()

        st, rsn, rd = self._reset(world, "rst-ult", tick=tick)
        self.assertEqual((st, rsn), ("error", "stale_epoch"))
        self.assertEqual(world.effects(SESS_A, "rst-ult"), {"created": 0, "deleted": 33})
        self.assertIsNone(rd["scene"]["last"])
        self.assertIsNone(world.read(doc_id)["scene"]["last"])

    def test_m8_barrera_falla_rapido_si_el_verbo_retiene_el_cerrojo(self) -> None:
        world = FakeWorld(ground=_custom_ground)
        self._apply_main(world)
        world.barrier_after(8)
        reached = world._barrier_reached
        release = world._barrier_release
        self.assertIsNotNone(reached)
        self.assertIsNotNone(release)
        result: dict = {}

        def run() -> None:
            result["r"] = self._reset(world, "rst-m8")

        th = threading.Thread(target=run, daemon=True)
        th.start()
        self.assertTrue(reached.wait(5.0), "la barrera no se alcanzo en 5 s")
        got_lock = world._lock.acquire(timeout=1.0)
        if got_lock:
            world._lock.release()
        self.assertTrue(got_lock, "el verbo retuvo el cerrojo durante la barrera")
        release.set()
        th.join(10.0)
        self.assertFalse(th.is_alive(), "el verbo no termino tras liberar la barrera")
        st, rsn, _ = result["r"]
        self.assertEqual((st, rsn), ("done", None))


class TestCase11SolR1C05(TestFakeWorldBaseMixin, unittest.TestCase):
    """C-05 (§3.3 y §3.6): suelo fuera de rango o no finito cuenta como creacion fallida."""

    def test_suelo_fuera_de_rango_en_todas_partes_rechaza_en_la_primera_creacion(self) -> None:
        world = FakeWorld(ground=10000)
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-gy-10000"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual((st, rsn), ("rejected", "create_failed"))
        self.assertEqual(
            world.effects(SESS_A, "op-gy-10000"),
            {"created": 0, "deleted": 0},
        )
        self.assertEqual([c for c in world.census() if c["scene"] == self.doc["doc_id"]], [])
        self.assertEqual(world.census(), [])
        self.assertEqual(world.registry_snapshot(), [])
        self.assertIsNone(rd["generation"])
        self.assertIsNone(rd["scene"]["pending"])
        self.assertIsNone(rd["scene"]["last"])
        self.assertEqual(rd["scene"]["n"], 0)
        self.assertEqual(world._scenes[self.doc["doc_id"]].pending_orders, [])

    def test_suelo_fuera_de_rango_en_fila_12_compensa_las_11_creadas_sin_tocar_resto(self) -> None:
        ent12 = self.doc["entities"][11]
        self.assertEqual(ent12["id"], "obj-12")
        x12, z12 = float(ent12["x"]), float(ent12["z"])

        def ground_fail_row12(x: float, z: float) -> float:
            if (float(x), float(z)) == (x12, z12):
                return 10000.0
            return _custom_ground(x, z)

        world = FakeWorld(ground=ground_fail_row12)
        world.spawn_foreign("SeaChest", 6194.2, 7638.2, 15.0)
        world.seed_scene(
            "d-0a0e0001",
            [
                ["obj-01", "WoodenCrate", 6150.0, 7650.0, 0.0],
                ["obj-02", "Barrel_Red", 6152.0, 7650.0, 0.0],
            ],
        )
        before_foreign = _foreign_snapshot(world.census())

        plan = build_plan(self.doc, rev=1, catalog=self.catalog)
        st, rsn, rd = world.apply(
            _make_order(world, "scene.apply", plan, op_id="op-gy-12"),
            check=lambda: None,
            tick=lambda: None,
        )
        self.assertEqual((st, rsn), ("error", "create_failed"))
        self.assertEqual(
            world.effects(SESS_A, "op-gy-12"),
            {"created": 11, "deleted": 11},
        )
        self.assertIsNone(rd["generation"])
        self.assertIsNone(rd["scene"]["pending"])
        self.assertEqual(rd["scene"]["n"], 0)
        self.assertEqual(rd["scene"]["retained_n"], 0)
        self.assertEqual(rd["scene"]["retained"], [])
        self.assertEqual(
            rd["scene"]["last"],
            {
                "session": SESS_A,
                "op_id": "op-gy-12",
                "verb": "scene.apply",
                "outcome": "compensated",
            },
        )

        census = world.census()
        self.assertEqual([c for c in census if c["scene"] == self.doc["doc_id"]], [])
        self.assertEqual(len([c for c in census if c["scene"] == "d-0a0e0001"]), 2)
        self.assertForeignUntouched(before_foreign, census)

    def test_limites_exactos_de_gy_crean_y_nan_e_inf_fallan(self) -> None:
        plan = build_plan(self.doc, rev=1, catalog=self.catalog)

        for idx, bound in enumerate((-9999.999, 9999.999)):
            world = FakeWorld(ground=bound)
            st, rsn, rd = world.apply(
                _make_order(world, "scene.apply", plan, op_id=f"op-gy-ok-{idx}"),
                check=lambda: None,
                tick=lambda: None,
            )
            self.assertEqual((st, rsn), ("done", None))
            self.assertIsNotNone(rd["generation"])
            self.assertEqual(rd["scene"]["n"], 33)
            self.assertEqual(len(world.census()), 33)
            for row in rd["obs"]["rows"]:
                self.assertEqual(row[3], round(bound * 1000))
                self.assertEqual(row[6], round(bound * 1000))
                self.assertIn(abs(row[3]), (9999999,))

        for idx, bad_gy in enumerate(
            (float("nan"), float("inf"), float("-inf"), -10000.0, -9999.9991, 9999.9991)
        ):
            world = FakeWorld(ground=bad_gy)
            st, rsn, rd = world.apply(
                _make_order(world, "scene.apply", plan, op_id=f"op-gy-bad-{idx}"),
                check=lambda: None,
                tick=lambda: None,
            )
            self.assertEqual((st, rsn), ("rejected", "create_failed"))
            self.assertEqual(
                world.effects(SESS_A, f"op-gy-bad-{idx}"),
                {"created": 0, "deleted": 0},
            )
            self.assertEqual(world.census(), [])
            self.assertIsNone(rd["generation"])
            self.assertIsNone(rd["scene"]["pending"])
            self.assertIsNone(rd["scene"]["last"])


if __name__ == "__main__":
    unittest.main()
