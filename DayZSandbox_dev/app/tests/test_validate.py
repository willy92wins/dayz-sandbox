from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from app.backend.validate import validate
except ModuleNotFoundError:
    from backend.validate import validate

try:
    from app.backend.store import Store
except ModuleNotFoundError:
    try:
        from backend.store import Store
    except ModuleNotFoundError:
        Store = None

ROOT_DIR = Path(__file__).resolve().parents[2]
SCENE_PATH = ROOT_DIR / "fixtures" / "escena-basica-cine.json"
CATALOG_PATH = ROOT_DIR / "fixtures" / "catalog-m1.json"
SCHEMA_PATH = ROOT_DIR / "schemas" / "scene.schema.json"


def _doc_hash(doc: dict) -> str:
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TestValidateA1(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_doc = json.loads(SCENE_PATH.read_text(encoding="utf-8"))
        cls.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    def _clone_doc(self) -> dict:
        return copy.deepcopy(self.base_doc)

    def _assert_single_error(self, doc: dict, expected_code: str, expected_pointer: str) -> None:
        before = copy.deepcopy(doc)
        errs = validate(doc, self.catalog)
        self.assertEqual(doc, before, "validate() no debe mutar el documento de entrada")
        self.assertTrue(len(errs) >= 1, f"Se esperaba error {expected_code} en {expected_pointer}, pero salió []")
        matching = [
            e for e in errs if e.get("code") == expected_code and e.get("pointer") == expected_pointer
        ]
        self.assertTrue(
            len(matching) == 1,
            f"Se esperaba ({expected_code!r}, {expected_pointer!r}) en {errs!r}",
        )
        self.assertIsInstance(matching[0].get("msg"), str)
        self.assertTrue(bool(matching[0]["msg"].strip()))

    def test_a1_positive_fixture_validates_without_errors(self) -> None:
        doc = self._clone_doc()
        errs = validate(doc, self.catalog)
        self.assertEqual(errs, [])

        self.assertEqual(doc["schema"], "dsbx.scene/1")
        self.assertEqual(doc["map"], "chernarusplus")
        self.assertEqual(doc["next"], {"act": 3, "obj": 21, "zmb": 11, "ani": 4, "cam": 4})

        counts = {"actor": 0, "objeto": 0, "infectado": 0, "animal": 0}
        for ent in doc["entities"]:
            counts[ent["kind"]] += 1
        self.assertEqual(counts, {"actor": 2, "objeto": 20, "infectado": 10, "animal": 3})
        self.assertEqual(len(doc["cameras"]), 3)

        h = _doc_hash(doc)
        self.assertEqual(len(h), 64)

    def test_schema_file_is_valid_2020_12(self) -> None:
        self.assertEqual(
            self.schema.get("$schema"),
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertIs(self.schema.get("additionalProperties"), False)

    def test_a1_negative_unsupported_version(self) -> None:
        doc = self._clone_doc()
        doc["schema"] = "dsbx.scene/2"
        self._assert_single_error(doc, "unsupported_version", "/schema")

    def test_a1_negative_unknown_class(self) -> None:
        doc = self._clone_doc()
        doc["entities"][2]["cls"] = "Land_Objeto_Inexistente"
        self._assert_single_error(doc, "unknown_class", "/entities/2/cls")

        doc2 = self._clone_doc()
        doc2["entities"][0]["cls"] = "Land_Wreck_Ikarus"
        self._assert_single_error(doc2, "unknown_class", "/entities/0/cls")

    def test_a1_negative_out_of_map(self) -> None:
        doc_x_low = self._clone_doc()
        doc_x_low["entities"][0]["x"] = -0.1
        self._assert_single_error(doc_x_low, "out_of_map", "/entities/0/x")

        doc_z_high = self._clone_doc()
        doc_z_high["entities"][2]["z"] = 15360.1
        self._assert_single_error(doc_z_high, "out_of_map", "/entities/2/z")

        doc_mark = self._clone_doc()
        doc_mark["entities"][0]["marks"][0]["x"] = 16000.0
        self._assert_single_error(doc_mark, "out_of_map", "/entities/0/marks/0/x")

        doc_cam = self._clone_doc()
        doc_cam["cameras"][0]["keys"][0]["z"] = -5.0
        self._assert_single_error(doc_cam, "out_of_map", "/cameras/0/keys/0/z")

    def test_a1_negative_budget_exceeded(self) -> None:
        doc_obj = self._clone_doc()
        doc_obj["entities"].append(
            {
                "id": "obj-21",
                "kind": "objeto",
                "cls": "Barrel_Red",
                "name": "Bidón extra",
                "x": 6180.0,
                "z": 7640.0,
                "yaw": 0,
            }
        )
        doc_obj["next"]["obj"] = 22
        self._assert_single_error(doc_obj, "budget_exceeded", "/entities")

        doc_act = self._clone_doc()
        doc_act["entities"].append(
            {
                "id": "act-03",
                "kind": "actor",
                "cls": "SurvivorM_Boris",
                "name": "Boris",
                "x": 6180.0,
                "z": 7640.0,
                "yaw": 0,
                "wardrobe": "cazador",
                "behaviour": "HOLD",
                "roam": 15,
                "marks": [],
                "gestures": [],
            }
        )
        doc_act["next"]["act"] = 4
        self._assert_single_error(doc_act, "budget_exceeded", "/entities")

    def test_a1_negative_unknown_field(self) -> None:
        doc_root = self._clone_doc()
        doc_root["extra"] = 123
        self._assert_single_error(doc_root, "unknown_field", "/extra")

        doc_ent = self._clone_doc()
        doc_ent["entities"][0]["extra_prop"] = "x"
        self._assert_single_error(doc_ent, "unknown_field", "/entities/0/extra_prop")

        doc_non_actor = self._clone_doc()
        doc_non_actor["entities"][2]["wardrobe"] = "civil"
        self._assert_single_error(doc_non_actor, "unknown_field", "/entities/2/wardrobe")

        doc_amb = self._clone_doc()
        doc_amb["ambiente"]["temperatura"] = 20
        self._assert_single_error(doc_amb, "unknown_field", "/ambiente/temperatura")

        doc_cam = self._clone_doc()
        doc_cam["cameras"][0]["fov"] = 50
        self._assert_single_error(doc_cam, "unknown_field", "/cameras/0/fov")

    def test_a1_negative_bad_ref_gesture_at_without_mark(self) -> None:
        doc_no_marks = self._clone_doc()
        doc_no_marks["entities"][1]["gestures"] = [{"emote": "EmoteGreeting", "at": 1}]
        self._assert_single_error(doc_no_marks, "bad_ref", "/entities/1/gestures/0/at")

        doc_exceed_marks = self._clone_doc()
        doc_exceed_marks["entities"][0]["gestures"] = [{"emote": "EmotePoint", "at": 3}]
        self._assert_single_error(doc_exceed_marks, "bad_ref", "/entities/0/gestures/0/at")

    def test_a1_negative_bad_order_camera_keys(self) -> None:
        doc_unsorted = self._clone_doc()
        doc_unsorted["cameras"][1]["keys"][2]["t"] = 2.0
        self._assert_single_error(doc_unsorted, "bad_order", "/cameras/1/keys/2/t")

        doc_dup_t = self._clone_doc()
        doc_dup_t["cameras"][1]["keys"][1]["t"] = 0
        self._assert_single_error(doc_dup_t, "bad_order", "/cameras/1/keys/1/t")

        doc_nonzero_start = self._clone_doc()
        doc_nonzero_start["cameras"][0]["keys"][0]["t"] = 1.0
        self._assert_single_error(doc_nonzero_start, "bad_order", "/cameras/0/keys/0/t")

    def test_a1_negative_bad_id(self) -> None:
        doc_bad_fmt = self._clone_doc()
        doc_bad_fmt["entities"][0]["id"] = "act-mirek"
        self._assert_single_error(doc_bad_fmt, "bad_id", "/entities/0/id")

        doc_one_digit = self._clone_doc()
        doc_one_digit["entities"][0]["id"] = "act-1"
        self._assert_single_error(doc_one_digit, "bad_id", "/entities/0/id")

        doc_wrong_prefix = self._clone_doc()
        doc_wrong_prefix["entities"][0]["id"] = "obj-99"
        self._assert_single_error(doc_wrong_prefix, "bad_id", "/entities/0/id")

        doc_dup = self._clone_doc()
        doc_dup["entities"][1]["id"] = "act-01"
        self._assert_single_error(doc_dup, "bad_id", "/entities/1/id")

        doc_cam = self._clone_doc()
        doc_cam["cameras"][0]["id"] = "cam-general"
        self._assert_single_error(doc_cam, "bad_id", "/cameras/0/id")

    def test_a1_negative_missing_type_and_value(self) -> None:
        doc_missing = self._clone_doc()
        del doc_missing["ambiente"]["hora"]
        self._assert_single_error(doc_missing, "missing_field", "/ambiente/hora")

        doc_bad_type = self._clone_doc()
        doc_bad_type["entities"][2]["yaw"] = True
        self._assert_single_error(doc_bad_type, "bad_type", "/entities/2/yaw")

        doc_bad_yaw = self._clone_doc()
        doc_bad_yaw["entities"][2]["yaw"] = 360
        self._assert_single_error(doc_bad_yaw, "bad_value", "/entities/2/yaw")

        doc_bad_amb = self._clone_doc()
        doc_bad_amb["ambiente"]["nubes"] = 1.5
        self._assert_single_error(doc_bad_amb, "bad_value", "/ambiente/nubes")

        doc_bad_emote = self._clone_doc()
        doc_bad_emote["entities"][0]["gestures"][0]["emote"] = "EmoteDance"
        self._assert_single_error(doc_bad_emote, "bad_value", "/entities/0/gestures/0/emote")

    def test_a1_negative_store_zero_changes_when_invalid(self) -> None:
        if Store is None:
            doc = self._clone_doc()
            before = copy.deepcopy(doc)
            doc["entities"][2]["x"] = 20000.0
            errs = validate(doc, self.catalog)
            self.assertEqual(errs[0]["code"], "out_of_map")
            self.assertEqual(errs[0]["pointer"], "/entities/2/x")
            self.assertNotEqual(doc, before)
            return

        with tempfile.TemporaryDirectory() as tmp:
            scene_file = os.path.join(tmp, "scene.json")
            store = Store(scene_file, self.catalog)
            snap_before = store.snapshot()
            disk_before = Path(scene_file).read_text(encoding="utf-8")
            author = {"role": "human", "id": "web"}

            invalid_batches = [
                [{"name": "entity.set", "target": "obj-01", "args": {"cls": "ClaseFalsa"}}],
                [{"name": "entity.move", "target": "obj-01", "args": {"x": 20000.0, "z": 7626.0}}],
                [
                    {
                        "name": "entity.add",
                        "args": {
                            "kind": "objeto",
                            "cls": "Barrel_Red",
                            "name": "Extra",
                            "x": 6180.0,
                            "z": 7640.0,
                            "yaw": 0,
                        },
                    }
                ],
                [
                    {
                        "name": "entity.gestures",
                        "target": "act-02",
                        "args": {"gestures": [{"emote": "EmoteGreeting", "at": 1}]},
                    }
                ],
                [
                    {
                        "name": "camera.set",
                        "target": "cam-02",
                        "args": {
                            "keys": [
                                {
                                    "t": 0,
                                    "x": 6154.0,
                                    "y": 2.1,
                                    "z": 7610.0,
                                    "yaw": 28,
                                    "pitch": -2,
                                    "fov": 42,
                                    "focus": 24,
                                },
                                {
                                    "t": 0,
                                    "x": 6168.0,
                                    "y": 2.4,
                                    "z": 7614.0,
                                    "yaw": 8,
                                    "pitch": -3,
                                    "fov": 36,
                                    "focus": 16,
                                },
                            ]
                        },
                    }
                ],
            ]

            for idx, ops in enumerate(invalid_batches):
                res = store.commit(
                    author,
                    f"req-neg-{idx}",
                    snap_before["doc_id"],
                    snap_before["rev"],
                    "negativa A1",
                    ops,
                )
                self.assertIs(res.get("ok"), False)
                self.assertEqual(res.get("code"), "invalid")
                self.assertEqual(store.snapshot(), snap_before)
                self.assertEqual(Path(scene_file).read_text(encoding="utf-8"), disk_before)


if __name__ == "__main__":
    unittest.main()
