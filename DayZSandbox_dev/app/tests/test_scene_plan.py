"""Pruebas puras de scene_plan.py (F2-offline §3, §4.1 y §4.3).

Sin red ni Bridge: solo funciones puras y las fixtures del repositorio.
Contrato: plans/2026-11-14-m1-f2-offline-brief.md v1.2.1, §3.3, §3.6, §4.1, §4.3,
D11, D12 y §13 (A2, A3, A6).
"""
import copy
import hashlib
import json
import math
import unittest
from pathlib import Path

from app.backend import scene_plan as sp

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
HASH = "a" * 64
SESSION = "0123456789abcdef"
EPOCH = "0123456789abcdef0123456789abcdef"
DOC_ID = "d-7c19e2a4"

OBJ_CLS = "Land_Wreck_Volha_Police"
ZMB_CLS = "ZmbM_CitizenASkinny_Grey"
ANI_CLS = "Animal_GallusGallusDomesticus"


def _load(name):
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


def _catalog():
    return _load("catalog-m1.json")


def _doc_without_actors():
    doc = _load("escena-basica-cine.json")
    doc["entities"] = [e for e in doc["entities"] if e.get("kind") != "actor"]
    return doc


def _world_catalog(cat=None):
    cat = cat if cat is not None else _catalog()
    classes = []
    for kind in ("objeto", "infectado", "animal"):
        classes.extend(cat["classes"][kind])
    return {"classes": classes}


def _gen(session=SESSION, op_id="op-9", rev=1, hash_=HASH, plan_sha256="c" * 64):
    return {
        "session": session,
        "op_id": op_id,
        "rev": rev,
        "hash": hash_,
        "plan_sha256": plan_sha256,
    }


def _scene_read(doc_id=DOC_ID, epoch=EPOCH, generation=None, scene=None, obs=None):
    read = {
        "epoch": epoch,
        "generation": copy.deepcopy(generation),
        "registry_n": 0,
        "registry_sha256": "0" * 64,
        "scene": copy.deepcopy(scene) if scene is not None else {
            "doc_id": doc_id,
            "gen_n": 0,
            "n": 0,
            "retained_n": 0,
            "retained": [],
            "pending": None,
            "last": None,
        },
    }
    if obs is not None:
        read["obs"] = copy.deepcopy(obs)
    return read


def _last(order, verb, outcome):
    return {
        "session": order["session"],
        "op_id": order["op_id"],
        "verb": verb,
        "outcome": outcome,
    }


def _read_with_last(order, last, n=0, retained_n=0, retained=None,
                    generation=None, pending=None, doc_id=DOC_ID, epoch=EPOCH):
    scene = {
        "doc_id": doc_id,
        "gen_n": 0,
        "n": n,
        "retained_n": retained_n,
        "retained": retained if retained is not None else [],
        "pending": pending,
        "last": last,
    }
    return _scene_read(doc_id=doc_id, epoch=epoch, generation=generation, scene=scene)


def _apply_order(plan, expectation):
    return {
        "session": SESSION,
        "op_id": "op-1",
        "epoch": EPOCH,
        "args": copy.deepcopy(plan),
        "expectation": copy.deepcopy(expectation),
    }


def _checkpoint_rows(plan):
    return [
        [row[0], row[1], row[2], 100.0, row[3], row[4], 100.0]
        for row in plan["rows"]
    ]


def _apply_read(order, rows):
    plan = order["args"]
    exp_n = len(order["expectation"])
    gen = {
        "session": order["session"],
        "op_id": order["op_id"],
        "rev": plan["rev"],
        "hash": plan["hash"],
        "plan_sha256": plan["plan_sha256"],
    }
    scene = {
        "doc_id": plan["doc_id"],
        "gen_n": 1,
        "n": exp_n,
        "retained_n": 0,
        "retained": [],
        "pending": None,
        "last": _last(order, "scene.apply", "done"),
    }
    return _scene_read(
        doc_id=plan["doc_id"],
        epoch=order["epoch"],
        generation=gen,
        scene=scene,
        obs={"at": "checkpoint", "rows": rows},
    )


def _reset_order(doc_id=DOC_ID):
    return {
        "session": SESSION,
        "op_id": "op-1",
        "epoch": EPOCH,
        "args": {"doc_id": doc_id},
    }


def _max_doc(n_obj, n_zmb, n_ani, caps_animal):
    """Documento con lids de 10 caracteres (maximo normativo) y clases largas."""
    entities = []
    for i in range(n_obj):
        entities.append({
            "id": "obj-%06d" % (100000 + i),
            "kind": "objeto",
            "cls": OBJ_CLS,
            "x": 100.0 + i,
            "z": 200.0 + i,
            "yaw": 0.0,
        })
    for i in range(n_zmb):
        entities.append({
            "id": "zmb-%06d" % (100000 + i),
            "kind": "infectado",
            "cls": ZMB_CLS,
            "x": 300.0 + i,
            "z": 400.0 + i,
            "yaw": 0.0,
        })
    for i in range(n_ani):
        entities.append({
            "id": "ani-%06d" % (100000 + i),
            "kind": "animal",
            "cls": ANI_CLS,
            "x": 500.0 + i,
            "z": 600.0 + i,
            "yaw": 0.0,
        })
    doc = {"doc_id": DOC_ID, "entities": entities}
    cat = _catalog()
    cat = copy.deepcopy(cat)
    cat["caps"]["objeto"] = n_obj
    cat["caps"]["infectado"] = n_zmb
    cat["caps"]["animal"] = caps_animal
    return doc, cat


class TestPlan(unittest.TestCase):
    def test_plan_deterministic_bytes_and_hash(self):
        doc = _doc_without_actors()
        cat = _catalog()
        p1 = sp.build_plan(doc, 1, HASH, cat)
        p2 = sp.build_plan(copy.deepcopy(doc), 1, HASH, cat)
        self.assertEqual(sp.compact_json_bytes(p1), sp.compact_json_bytes(p2))
        self.assertEqual(p1["plan_sha256"], p2["plan_sha256"])
        self.assertEqual(
            p1["plan_sha256"],
            hashlib.sha256(sp.canonical_json_bytes({
                "doc_id": doc["doc_id"],
                "rev": 1,
                "hash": HASH,
                "classes": p1["classes"],
                "rows": p1["rows"],
            })).hexdigest(),
        )

    def test_plan_rows_order_classes_and_expectation(self):
        doc = _doc_without_actors()
        cat = _catalog()
        plan = sp.build_plan(doc, 1, HASH, cat)
        self.assertEqual(len(plan["rows"]), 33)
        self.assertEqual([r[0] for r in plan["rows"]], [e["id"] for e in doc["entities"]])
        self.assertEqual(plan["classes"], sorted({e["cls"] for e in doc["entities"]}))
        by_lid = {e["id"]: e["cls"] for e in doc["entities"]}
        for row in plan["rows"]:
            self.assertEqual(len(row), 5)
            lid, ci, x, z, yaw = row
            self.assertEqual(plan["classes"][ci], by_lid[lid])
            for val in (x, z, yaw):
                self.assertEqual(round(val, 3), val)
        exp = sp.extract_expectation(doc)
        self.assertEqual(len(exp), 33)
        self.assertTrue(sp.plan_matches_expectation(plan, exp))

    def test_plan_hash_changes_with_rev_coord_or_class(self):
        doc = _doc_without_actors()
        cat = _catalog()
        base = sp.build_plan(doc, 1, HASH, cat)
        other_rev = sp.build_plan(doc, 2, HASH, cat)
        self.assertNotEqual(base["plan_sha256"], other_rev["plan_sha256"])
        moved = copy.deepcopy(doc)
        moved["entities"][0]["x"] = moved["entities"][0]["x"] + 1.0
        self.assertNotEqual(base["plan_sha256"], sp.build_plan(moved, 1, HASH, cat)["plan_sha256"])
        reclassed = copy.deepcopy(doc)
        reclassed["entities"][0]["cls"] = "LargeTent"
        self.assertNotEqual(base["plan_sha256"], sp.build_plan(reclassed, 1, HASH, cat)["plan_sha256"])

    def test_plan_yaw_normalized_after_rounding(self):
        doc = _doc_without_actors()
        cat = _catalog()
        for raw, expected in ((359.9999, 0.0), (360.0, 0.0), (359.9994, 359.999), (-0.0001, 0.0)):
            moved = copy.deepcopy(doc)
            moved["entities"][0]["yaw"] = raw
            plan = sp.build_plan(moved, 1, HASH, cat)
            self.assertEqual(plan["rows"][0][4], expected, raw)

    def test_plan_rows_shifted_by_constructor_do_not_match_expectation(self):
        doc = _doc_without_actors()
        cat = _catalog()
        plan = sp.build_plan(doc, 1, HASH, cat)
        exp = sp.extract_expectation(doc)
        self.assertTrue(sp.plan_matches_expectation(plan, exp))
        shifted = copy.deepcopy(plan)
        for row in shifted["rows"]:
            row[2] = row[2] + 2.0
        self.assertFalse(sp.plan_matches_expectation(shifted, exp))

    def test_plan_with_repeated_row_does_not_match_expectation(self):
        doc = _doc_without_actors()
        cat = _catalog()
        plan = sp.build_plan(doc, 1, HASH, cat)
        exp = sp.extract_expectation(doc)
        plan["rows"][1] = copy.deepcopy(plan["rows"][0])
        self.assertFalse(sp.plan_matches_expectation(plan, exp))

    def test_plan_with_ci_of_another_class_does_not_match_expectation(self):
        doc = _doc_without_actors()
        cat = _catalog()
        plan = sp.build_plan(doc, 1, HASH, cat)
        exp = sp.extract_expectation(doc)
        lid = plan["rows"][0][0]
        other = next(i for i, cls in enumerate(plan["classes"]) if cls != exp[lid][0])
        plan["rows"][0][1] = other
        self.assertFalse(sp.plan_matches_expectation(plan, exp))

    def test_plan_negative_zero_yaw_becomes_positive_zero(self):
        doc = _doc_without_actors()
        doc["entities"][0]["yaw"] = -0.0
        plan = sp.build_plan(doc, 1, HASH, _catalog())
        yaw = plan["rows"][0][4]
        self.assertEqual(yaw, 0.0)
        self.assertEqual(math.copysign(1.0, yaw), 1.0)


class TestValidation(unittest.TestCase):
    def _validate(self, doc, store_catalog=None, world_catalog=None,
                  catalog_valid=True, world_size=15360, rev=1, hash_=HASH,
                  op_id=None, conn=None):
        if store_catalog is None:
            store_catalog = _catalog()
        if world_catalog is None:
            world_catalog = _world_catalog(store_catalog)
        return sp.validate_for_apply(
            doc, rev, hash_, store_catalog, world_catalog=world_catalog,
            catalog_valid=catalog_valid, world_size=world_size,
            op_id=op_id, conn=conn,
        )

    def test_valid_scene_ok(self):
        doc = _doc_without_actors()
        res = self._validate(doc, op_id="op-1", conn=1)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["expectation"]), 33)
        self.assertEqual(res["plan"]["rows"], sp.build_plan(doc, 1, HASH, _catalog())["rows"])
        self.assertLessEqual(res["envelope"]["max_bytes"], sp.WIRE_CAP)

    def test_expansion_unavailable(self):
        doc = _load("escena-basica-cine.json")
        res = self._validate(doc)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "expansion_unavailable")
        self.assertEqual(res["http"], 422)
        self.assertEqual(res["pointer"], "/entities/0")
        self.assertEqual(len(res["errors"]), 2)
        self.assertTrue(all(e["code"] == "expansion_unavailable" for e in res["errors"]))

    def test_catalog_pending_by_default(self):
        doc = _doc_without_actors()
        res = sp.validate_for_apply(doc, 1, HASH, _catalog(),
                                    world_catalog=_world_catalog())
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "catalog_pending")
        self.assertEqual(res["http"], 409)
        self.assertEqual(res["pointer"], "")

    def test_catalog_pending_without_world_catalog(self):
        doc = _doc_without_actors()
        res = sp.validate_for_apply(doc, 1, HASH, _catalog(),
                                    world_catalog=None, catalog_valid=True)
        self.assertEqual(res["code"], "catalog_pending")

    def test_unknown_class(self):
        doc = _doc_without_actors()
        doc["entities"][0]["cls"] = "NoSuchClass"
        res = self._validate(doc)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "unknown_class")
        self.assertEqual(res["http"], 422)
        self.assertEqual(res["pointer"], "/entities/0/cls")

    def test_out_of_map(self):
        doc = _doc_without_actors()
        res = self._validate(doc, world_size=100.0)
        self.assertEqual(res["code"], "out_of_map")
        self.assertEqual(res["http"], 422)
        self.assertEqual(res["pointer"], "/entities/0/x")
        doc["entities"][0]["x"] = 50.0
        doc["entities"][0]["z"] = 200.0
        res = self._validate(doc, world_size=100.0)
        self.assertEqual(res["pointer"], "/entities/0/z")

    def test_budget_exceeded_by_each_type_and_total(self):
        doc = _doc_without_actors()
        for key, cap in (("objeto", 19), ("infectado", 9), ("animal", 2)):
            cat = _catalog()
            cat["caps"][key] = cap
            res = self._validate(doc, store_catalog=cat)
            self.assertEqual(res["code"], "budget_exceeded", key)
            self.assertEqual(res["http"], 422)
            self.assertEqual(res["pointer"], "/entities")
        cat = _catalog()
        cat["caps"]["total"] = 30
        res = self._validate(doc, store_catalog=cat)
        self.assertEqual(res["code"], "budget_exceeded")
        self.assertIn("total", res["errors"][0]["msg"].lower())

    def test_budget_exceeded_without_valid_caps(self):
        doc = _doc_without_actors()
        for caps in (None, {"objeto": 20, "infectado": 10},
                     {"objeto": 20.0, "infectado": 10, "animal": 3},
                     {"objeto": True, "infectado": 10, "animal": 3},
                     {"objeto": 20, "infectado": 10, "animal": 3, "total": 33.0}):
            cat = _catalog()
            if caps is None:
                cat.pop("caps")
            else:
                cat["caps"] = caps
            res = self._validate(doc, store_catalog=cat)
            self.assertEqual(res["code"], "budget_exceeded", caps)
            self.assertEqual(res["pointer"], "/entities")

    def test_plan_too_large_lid_pointer(self):
        doc = _doc_without_actors()
        doc["entities"][0]["id"] = "obj-1234567"
        res = self._validate(doc)
        self.assertEqual(res["code"], "plan_too_large")
        self.assertEqual(res["http"], 422)
        self.assertEqual(res["pointer"], "/entities/0/id")

    def test_plan_too_large_class_1024_pointer(self):
        doc = _doc_without_actors()
        long_cls = "C" * 1024
        doc["entities"][0]["cls"] = long_cls
        cat = _catalog()
        cat["classes"]["objeto"] = cat["classes"]["objeto"] + [long_cls]
        world_catalog = _world_catalog(cat)
        res = self._validate(doc, store_catalog=cat, world_catalog=world_catalog,
                             op_id="op-1", conn=1)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "plan_too_large")
        self.assertEqual(res["http"], 422)
        self.assertEqual(res["pointer"], "/entities/0/cls")

    def test_plan_too_large_rev_and_op_id(self):
        doc = _doc_without_actors()
        res = self._validate(doc, rev=1234567890)
        self.assertEqual(res["code"], "plan_too_large")
        self.assertEqual(res["pointer"], "")
        res = self._validate(doc, op_id="op-1234567")
        self.assertEqual(res["code"], "plan_too_large")
        self.assertEqual(res["pointer"], "")

    def test_plan_too_large_envelope_35_roots(self):
        doc, cat = _max_doc(20, 10, 5, 5)
        res = self._validate(doc, store_catalog=cat)
        self.assertEqual(res["code"], "plan_too_large")
        self.assertEqual(res["pointer"], "")

    def test_validation_order_stops_at_first_code(self):
        full = _load("escena-basica-cine.json")
        res = self._validate(full, catalog_valid=False)
        self.assertEqual(res["code"], "expansion_unavailable")
        doc = _doc_without_actors()
        doc["entities"][0]["cls"] = "NoSuchClass"
        doc["entities"][0]["x"] = 99999.0
        res = self._validate(doc, world_size=100.0)
        self.assertEqual(res["code"], "unknown_class")
        doc = _doc_without_actors()
        cat = _catalog()
        cat["caps"]["objeto"] = 19
        res = self._validate(doc, store_catalog=cat, world_size=100.0)
        self.assertEqual(res["code"], "out_of_map")


class TestEnvelope(unittest.TestCase):
    def test_envelope_33_roots_with_maxima_fits_wire_cap(self):
        doc, cat = _max_doc(20, 10, 3, 3)
        plan = sp.build_plan(doc, sp._MAX_REV, "0" * 64, cat)
        env = sp.compute_envelope(
            [row[0] for row in plan["rows"]],
            plan["classes"],
            caps=plan["caps"],
            doc_id=doc["doc_id"],
            rev=sp._MAX_REV,
            hash_="0" * 64,
            op_id="op-999999",
            conn=sp._MAX_COUNT,
        )
        self.assertLessEqual(env["max_bytes"], sp.WIRE_CAP)
        for key in ("poll_apply", "result_apply", "result_observe_now",
                    "result_reset_or_read"):
            self.assertLessEqual(env[key], sp.WIRE_CAP, key)
        res = sp.validate_for_apply(
            doc, 1, HASH, cat, world_catalog=_world_catalog(cat),
            catalog_valid=True, world_size=15360,
        )
        self.assertTrue(res["ok"])
        self.assertLessEqual(res["envelope"]["max_bytes"], sp.WIRE_CAP)

    def test_envelope_35_roots_exceeds_wire_cap(self):
        doc, cat = _max_doc(20, 10, 5, 5)
        env = sp.compute_envelope(
            [e["id"] for e in doc["entities"]],
            sorted({e["cls"] for e in doc["entities"]}),
            caps={"objeto": 20, "infectado": 10, "animal": 5},
            doc_id=doc["doc_id"],
            rev=sp._MAX_REV,
            hash_="0" * 64,
            op_id="op-999999",
            conn=sp._MAX_COUNT,
        )
        self.assertGreater(env["max_bytes"], sp.WIRE_CAP)


class TestApplyPredicate(unittest.TestCase):
    def setUp(self):
        self.doc = _doc_without_actors()
        self.cat = _catalog()
        self.plan = sp.build_plan(self.doc, 1, HASH, self.cat)
        self.exp = sp.extract_expectation(self.doc)
        self.order = _apply_order(self.plan, self.exp)
        self.rows = _checkpoint_rows(self.plan)

    def test_good_apply(self):
        read = _apply_read(self.order, self.rows)
        self.assertTrue(sp.check_apply_predicate(self.order, read))

    def test_omitted_row(self):
        read = _apply_read(self.order, self.rows[:-1])
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_extra_row(self):
        rows = self.rows + [["obj-99", 0, 0.0, 0.0, 0.0, 0.0, 0.0]]
        read = _apply_read(self.order, rows)
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_repeated_row(self):
        rows = copy.deepcopy(self.rows)
        rows[1][0] = rows[0][0]
        read = _apply_read(self.order, rows)
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_repeated_row_exact_same_lid_and_count(self):
        rows = copy.deepcopy(self.rows)
        rows[1] = copy.deepcopy(rows[0])
        read = _apply_read(self.order, rows)
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_ci_minus_one(self):
        rows = copy.deepcopy(self.rows)
        rows[0][1] = -1
        read = _apply_read(self.order, rows)
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_ci_of_another_class(self):
        rows = copy.deepcopy(self.rows)
        lid = rows[0][0]
        exp_cls = self.exp[lid][0]
        other = next(i for i, cls in enumerate(self.plan["classes"]) if cls != exp_cls)
        rows[0][1] = other
        read = _apply_read(self.order, rows)
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_x_null(self):
        rows = copy.deepcopy(self.rows)
        rows[0][2] = None
        read = _apply_read(self.order, rows)
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_position_error_06m(self):
        rows = copy.deepcopy(self.rows)
        rows[0][2] = rows[0][2] + 0.6
        read = _apply_read(self.order, rows)
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_real_error_05004m_rounded_to_04999(self):
        doc = {
            "doc_id": DOC_ID,
            "entities": [{
                "id": "obj-01", "kind": "objeto", "cls": "Land_Wreck_Ikarus",
                "x": 0.0, "z": 0.0, "yaw": 0.0,
            }],
        }
        plan = sp.build_plan(doc, 1, HASH, self.cat)
        exp = sp.extract_expectation(doc)
        order = _apply_order(plan, exp)
        # Posicion real (0.0704, 0, 0.4954): el redondeo a mm da (0.07, 0, 0.495).
        rows = [["obj-01", 0, 0.07, 0.0, 0.495, 0.0, 0.0]]
        dist = sp.dist3((0.07, 0.0, 0.495), (0.0, 0.0, 0.0))
        self.assertGreaterEqual(dist, sp.POS_TOL_M - sp.EPS_Q)
        self.assertLess(dist, sp.POS_TOL_M)
        read = _apply_read(order, rows)
        self.assertFalse(sp.check_apply_predicate(order, read))

    def test_generation_other_plan_sha256(self):
        read = _apply_read(self.order, self.rows)
        read["generation"]["plan_sha256"] = "b" * 64
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_generation_other_rev(self):
        read = _apply_read(self.order, self.rows)
        read["generation"]["rev"] = 2
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_generation_other_hash(self):
        read = _apply_read(self.order, self.rows)
        read["generation"]["hash"] = "b" * 64
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_pending_not_null(self):
        read = _apply_read(self.order, self.rows)
        read["scene"]["pending"] = {"session": SESSION, "op_id": "op-2", "n": 1}
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_scene_n_mismatch(self):
        read = _apply_read(self.order, self.rows)
        read["scene"]["n"] = len(self.exp) + 1
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_retained_n_positive(self):
        read = _apply_read(self.order, self.rows)
        read["scene"]["retained_n"] = 1
        read["scene"]["retained"] = ["obj-01"]
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_expectation_shifted_two_meters(self):
        read = _apply_read(self.order, self.rows)
        shifted = {lid: (cls, x + 2.0, z) for lid, (cls, x, z) in self.exp.items()}
        self.assertFalse(sp.check_apply_predicate(self.order, read, shifted))

    def test_epoch_mismatch(self):
        read = _apply_read(self.order, self.rows)
        read["epoch"] = "f" * 32
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_generation_null(self):
        read = _apply_read(self.order, self.rows)
        read["generation"] = None
        self.assertFalse(sp.check_apply_predicate(self.order, read))

    def test_read_without_scene(self):
        read = _apply_read(self.order, self.rows)
        del read["scene"]
        self.assertFalse(sp.check_apply_predicate(self.order, read))


class TestResetPredicate(unittest.TestCase):
    def setUp(self):
        self.order = _reset_order()

    def test_done_clean(self):
        read = _read_with_last(self.order, _last(self.order, "scene.reset", "done"))
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read), ("observado", None))

    def test_retained(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "retained"),
            n=2, retained_n=2, retained=["obj-01", "obj-02"],
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("parcial", "contenido_ajeno"))

    def test_interrupted(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "interrupted"), n=3,
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("parcial", "interrumpida"))

    def test_done_with_rests(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "done"), n=1,
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_done_with_retained_n(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "done"),
            n=1, retained_n=1, retained=["obj-01"],
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_without_retained_list(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "retained"),
            n=0, retained_n=0, retained=[],
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_with_n_different_from_retained_n(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "retained"),
            n=3, retained_n=2, retained=["obj-01", "obj-02"],
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_with_generation(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "retained"),
            n=2, retained_n=2, retained=["obj-01", "obj-02"], generation=_gen(),
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_with_pending(self):
        read = _read_with_last(
            self.order, _last(self.order, "scene.reset", "retained"),
            n=2, retained_n=2, retained=["obj-01", "obj-02"],
            pending={"session": SESSION, "op_id": "op-2", "n": 1},
        )
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_last_with_other_verb(self):
        read = _read_with_last(self.order, _last(self.order, "scene.apply", "done"))
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_last_with_other_op(self):
        last = _last(self.order, "scene.reset", "done")
        last["op_id"] = "op-2"
        read = _read_with_last(self.order, last)
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_last_null(self):
        read = _read_with_last(self.order, None)
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_epoch_mismatch(self):
        read = _read_with_last(self.order, _last(self.order, "scene.reset", "done"),
                               epoch="f" * 32)
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_doc_id_mismatch(self):
        read = _read_with_last(self.order, _last(self.order, "scene.reset", "done"),
                               doc_id="d-00000000")
        self.assertEqual(sp.evaluate_reset_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))


class TestCompensationPredicate(unittest.TestCase):
    def setUp(self):
        self.order = _reset_order()

    def _read(self, outcome, **kwargs):
        return _read_with_last(
            self.order, _last(self.order, "scene.apply", outcome), **kwargs
        )

    def test_compensated(self):
        read = self._read("compensated", n=0)
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("parcial", "compensada"))

    def test_compensated_with_other_pending(self):
        read = self._read("compensated", n=0,
                          pending={"session": SESSION, "op_id": "op-2", "n": 1})
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("parcial", "compensada"))

    def test_compensated_with_n_positive(self):
        read = self._read("compensated", n=1)
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_compensated_with_generation(self):
        read = self._read("compensated", n=0, generation=_gen())
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_with_rests(self):
        read = self._read("retained", n=3, retained_n=2,
                          retained=["obj-01", "obj-02"])
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("parcial", "contenido_ajeno"))

    def test_retained_equal_counts(self):
        read = self._read("retained", n=2, retained_n=2,
                          retained=["obj-01", "obj-02"])
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("parcial", "contenido_ajeno"))

    def test_retained_empty(self):
        read = self._read("retained", n=0, retained_n=0, retained=[])
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_n_one_with_empty_retained_list(self):
        read = self._read("retained", n=1, retained_n=1, retained=[])
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_n_below(self):
        read = self._read("retained", n=1, retained_n=2,
                          retained=["obj-01", "obj-02"])
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_retained_with_generation(self):
        read = self._read("retained", n=2, retained_n=2,
                          retained=["obj-01", "obj-02"], generation=_gen())
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_interrupted(self):
        read = self._read("interrupted", n=3)
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("parcial", "interrumpida"))

    def test_interrupted_with_generation(self):
        read = self._read("interrupted", n=3, generation=_gen())
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_pending_is_the_order(self):
        read = self._read("compensated", n=0,
                          pending={"session": SESSION, "op_id": self.order["op_id"], "n": 1})
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("unresolved", None))

    def test_pending_is_the_order_even_if_interrupted(self):
        read = self._read("interrupted", n=1,
                          pending={"session": SESSION, "op_id": self.order["op_id"], "n": 1})
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("unresolved", None))

    def test_last_with_other_verb(self):
        read = _read_with_last(self.order, _last(self.order, "scene.reset", "compensated"), n=0)
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_done_outcome(self):
        read = self._read("done", n=0)
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))

    def test_epoch_mismatch(self):
        read = self._read("compensated", n=0)
        read["epoch"] = "f" * 32
        self.assertEqual(sp.evaluate_compensation_predicate(self.order, read),
                         ("fallido", "lectura_no_cumple"))


class TestReadShape(unittest.TestCase):
    def test_base_read_valid(self):
        self.assertTrue(sp.valid_scene_read(_scene_read()))

    def test_generation_rev_up_to_nine_digits(self):
        read = _scene_read(generation=_gen(rev=1234567))
        self.assertTrue(sp.valid_scene_read(read))
        read["generation"]["rev"] = 999999999
        self.assertTrue(sp.valid_scene_read(read))

    def test_generation_rev_ten_digits_invalid(self):
        read = _scene_read(generation=_gen(rev=1000000000))
        self.assertFalse(sp.valid_scene_read(read))

    def test_generation_rev_negative_or_float(self):
        for rev in (-1, 1.0, True):
            read = _scene_read(generation=_gen(rev=rev))
            self.assertFalse(sp.valid_scene_read(read), rev)

    def test_generation_key_missing(self):
        read = _scene_read()
        del read["generation"]
        self.assertFalse(sp.valid_scene_read(read))

    def test_scene_missing(self):
        read = _scene_read()
        del read["scene"]
        self.assertFalse(sp.valid_scene_read(read))

    def test_counters_out_of_range(self):
        for field, value in (("n", 1000000), ("gen_n", -1), ("retained_n", 1000000)):
            read = _scene_read()
            read["scene"][field] = value
            self.assertFalse(sp.valid_scene_read(read), field)

    def test_retained_too_many_or_over_retained_n(self):
        read = _scene_read()
        read["scene"]["retained_n"] = 9
        read["scene"]["retained"] = ["obj-01"] * 9
        self.assertFalse(sp.valid_scene_read(read))
        read = _scene_read()
        read["scene"]["retained_n"] = 0
        read["scene"]["retained"] = ["obj-01"]
        self.assertFalse(sp.valid_scene_read(read))

    def test_pending_n_out_of_range(self):
        read = _scene_read()
        read["scene"]["pending"] = {"session": SESSION, "op_id": "op-1", "n": -1}
        self.assertFalse(sp.valid_scene_read(read))

    def test_world_size_out_of_range(self):
        self.assertFalse(sp.valid_scene_read(_scene_read(), world_size=100000))

    def test_obs_checkpoint_row_valid(self):
        read = _scene_read()
        read["obs"] = {"at": "checkpoint",
                       "rows": [["obj-01", 0, 1.0, 2.0, 3.0, 359.999, 2.0]]}
        self.assertTrue(sp.valid_scene_read(read, require_obs="checkpoint"))

    def test_obs_checkpoint_dead_entity_valid(self):
        read = _scene_read()
        read["obs"] = {"at": "checkpoint",
                       "rows": [["obj-01", -1, None, None, None, None, None]]}
        self.assertTrue(sp.valid_scene_read(read, require_obs="checkpoint"))

    def test_obs_checkpoint_row_out_of_range(self):
        cases = [
            ("x", 100000.0),
            ("z", 100000.0),
            ("y", -10000.0),
            ("gy", 10000.0),
            ("yaw", 360.0),
            ("ci", 1000000),
            ("x", 1.2345),
        ]
        for field, value in cases:
            read = _scene_read()
            row = ["obj-01", 0, 1.0, 2.0, 3.0, 359.999, 2.0]
            idx = {"lid": 0, "ci": 1, "x": 2, "y": 3, "z": 4, "yaw": 5, "gy": 6}[field]
            row[idx] = value
            read["obs"] = {"at": "checkpoint", "rows": [row]}
            self.assertFalse(sp.valid_scene_read(read, require_obs="checkpoint"), field)

    def test_obs_now_row_valid_and_invalid(self):
        read = _scene_read()
        read["obs"] = {"at": "now",
                       "rows": [["obj-01", 1.0, 2.0, 3.0, 359.999, 0.999, 5, 0]]}
        self.assertTrue(sp.valid_scene_read(read, require_obs="now"))
        for field, value in (("hp", 1.001), ("n_own", 1000000), ("yaw", 360.0)):
            read = _scene_read()
            row = ["obj-01", 1.0, 2.0, 3.0, 359.999, 0.999, 5, 0]
            idx = {"hp": 5, "n_own": 6, "yaw": 4}[field]
            row[idx] = value
            read["obs"] = {"at": "now", "rows": [row]}
            self.assertFalse(sp.valid_scene_read(read, require_obs="now"), field)

    def test_lid_ascii_digits_and_length(self):
        self.assertTrue(sp.valid_lid("obj-01"))
        self.assertTrue(sp.valid_lid("obj-123456"))
        self.assertTrue(sp.valid_lid("obj-999999"))
        self.assertFalse(sp.valid_lid("obj-1234567"))
        self.assertFalse(sp.valid_lid("obj-\u0661\u0662"))
        self.assertFalse(sp.valid_lid("obj-01\n"))
        self.assertFalse(sp.valid_lid("obj-0"))
        self.assertFalse(sp.valid_lid("obj-00"))
        self.assertFalse(sp.valid_lid("act-01"))
        self.assertFalse(sp.valid_lid(None))

    def test_doc_id_pattern(self):
        self.assertTrue(sp.valid_doc_id("d-7c19e2a4"))
        self.assertFalse(sp.valid_doc_id("d-7C19E2A4"))
        self.assertFalse(sp.valid_doc_id("d-7c19e2a4\n"))
        self.assertFalse(sp.valid_doc_id("d-7c19e2a"))

    def test_op_id_number_at_most_six_digits(self):
        self.assertTrue(sp.valid_op_id("op-999999"))
        self.assertTrue(sp.valid_op_id("rd-1"))
        self.assertFalse(sp.valid_op_id("op-1000000"))
        self.assertFalse(sp.valid_op_id("op-"))
        self.assertFalse(sp.valid_op_id("x-1"))


if __name__ == "__main__":
    unittest.main()
