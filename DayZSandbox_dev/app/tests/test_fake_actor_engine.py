"""Pruebas del motor de actores falso y de los presets de vestuario (brief F3-offline-1 §8.3: T-F1..T-F3, T-W1)."""

import copy
import json
import unittest
from pathlib import Path

from app.backend.actor_judge import (
    judge_gesture,
    judge_hold,
    judge_identity,
    judge_mark,
    judge_roam,
)
from app.backend.actor_wire import valid_actor_read, valid_actor_row
from app.tests.fake_actor_engine import FakeActorEngine, FakeClock, collect

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CATALOG_PATH = _ROOT_DIR / "fixtures" / "catalog-m1.json"
_SCENE_PATH = _ROOT_DIR / "fixtures" / "escena-basica-cine.json"

EXPECTED_WARDROBE_ITEMS = {
    "partisano": [
        "GorkaEJacket_Flat",
        "GorkaPants_Flat",
        "MilitaryBoots_Black",
        "TacticalGloves_Black",
        "BalaclavaMask_Black",
    ],
    "civil": [
        "Hoodie_Grey",
        "Jeans_Blue",
        "AthleticShoes_Grey",
        "BaseballCap_Blue",
        "TaloonBag_Blue",
    ],
    "medica": [
        "ParamedicJacket_Green",
        "ParamedicPants_Green",
        "Sneakers_White",
        "SurgicalGloves_White",
        "SurgicalMask",
    ],
    "cazador": [
        "HuntingJacket_Brown",
        "HunterPants_Brown",
        "HikingBoots_Brown",
        "WorkingGloves_Brown",
        "BoonieHat_DPM",
    ],
}


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _valid_wardrobe_catalog(catalog: dict) -> bool:
    """Regla de §4 (T-W1): correspondencia exacta con wardrobes y 1..32 clases validas como cls de §2.1."""
    if not isinstance(catalog, dict):
        return False
    wardrobes = catalog.get("wardrobes")
    wardrobe_items = catalog.get("wardrobe_items")
    if not isinstance(wardrobes, list) or not isinstance(wardrobe_items, dict):
        return False
    if set(wardrobes) != set(wardrobe_items.keys()):
        return False
    for preset in wardrobes:
        items = wardrobe_items.get(preset)
        if not isinstance(items, list) or not (1 <= len(items) <= 32):
            return False
        for item_cls in items:
            if not valid_actor_row(["act-01", item_cls, 0, 0, 0, 0, [], -1, "idle", 0]):
                return False
    return True


class TestFakeActorEngine(unittest.TestCase):
    """Pruebas T-F1, T-F2, T-F3 y T-W1 del brief de F3-offline-1 (§8.3)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = _load_json(_CATALOG_PATH)
        cls.scene = _load_json(_SCENE_PATH)
        cls.actors_by_id = {
            ent["id"]: ent
            for ent in cls.scene["entities"]
            if ent.get("kind") == "actor"
        }

    def _build_scene_engine(self) -> FakeActorEngine:
        clock = FakeClock(0)
        engine = FakeActorEngine(self.catalog, clock)
        for lid in ("act-01", "act-02"):
            ent = self.actors_by_id[lid]
            engine.spawn(lid, ent["cls"], ent["x"], ent["z"], ent["yaw"], ent["wardrobe"])
            engine.set_marks(lid, ent["marks"], ent["behaviour"], ent["roam"])
            for gi, gest in enumerate(ent.get("gestures", [])):
                engine.request_gesture(lid, gi, gest["emote"])
        return engine

    def _evaluate_scene_judges(self, samples: dict, events: list) -> dict[str, dict]:
        act01 = self.actors_by_id["act-01"]
        act02 = self.actors_by_id["act-02"]
        exp01 = {"cls": act01["cls"], "items": self.catalog["wardrobe_items"][act01["wardrobe"]]}
        exp02 = {"cls": act02["cls"], "items": self.catalog["wardrobe_items"][act02["wardrobe"]]}
        return {
            "c1_act01": judge_identity(exp01, samples["act-01"][0]),
            "c1_act02": judge_identity(exp02, samples["act-02"][0]),
            "c2_mark0": judge_mark(samples["act-01"], 0, act01["marks"][0], settle_ms=0),
            "c2_mark1": judge_mark(samples["act-01"], 1, act01["marks"][1], settle_ms=10000),
            "c3_act01": judge_gesture(events, "act-01", 0),
            "c3_act02": judge_gesture(events, "act-02", 0),
            "hold_act02": judge_hold(samples["act-02"], window_ms=10000),
        }

    def test_t_f1_sano(self) -> None:
        # T-F1: escena-basica-cine.json cada 200 ms -> todas las fotos pasan valid_actor_read y los jueces dan PASA.
        engine = self._build_scene_engine()
        orig_read = engine.read
        snapshots = []

        def tracked_read():
            snap = orig_read()
            snapshots.append(snap)
            return snap

        engine.read = tracked_read
        samples, events = collect(engine, until_ms=22000, step_ms=200)
        self.assertGreater(len(snapshots), 0)
        for snap in snapshots:
            self.assertTrue(valid_actor_read(snap))

        verdicts = self._evaluate_scene_judges(samples, events)
        for name, res in verdicts.items():
            with self.subTest(judge=name):
                self.assertEqual(res["verdict"], "PASA", f"{name} dio {res}")
                self.assertIsNone(res["why"])

    def test_t_f2_fallos(self) -> None:
        # T-F2: cada fallo de la tabla de §5 tumba solo a su juez con el why exacto; los demas siguen en PASA.
        cases = [
            ("unreachable", lambda e: e.unreachable("act-01", 1), None, "c2_mark1", "FALLA", "inalcanzable"),
            ("unreachable_near", lambda e: e.unreachable_near("act-01", 1), None, "c2_mark1", "FALLA", "inalcanzable"),
            ("stop_short", lambda e: e.stop_short("act-01", 1), None, "c2_mark1", "FALLA", "no_llega"),
            ("jitter_mark", lambda e: e.jitter("act-01", 0.6), None, "c2_mark1", "FALLA", "no_quieto"),
            ("jitter_hold", lambda e: e.jitter("act-02", 0.6), None, "hold_act02", "FALLA", "se_mueve"),
            ("drop_mark", lambda e: None, ("act-01", 10000, 12000), "c2_mark1", "INCONCLUSO", "sin_cobertura"),
            ("drop_hold", lambda e: None, ("act-02", 2000, 4000), "hold_act02", "INCONCLUSO", "sin_cobertura"),
            ("wardrobe_drop", lambda e: e.wardrobe_drop("act-01", "GorkaEJacket_Flat"), None, "c1_act01", "FALLA", "vestuario"),
            ("wardrobe_add", lambda e: e.wardrobe_add("act-01", "Hoodie_Grey"), None, "c1_act01", "FALLA", "vestuario"),
            ("cls_swap", lambda e: e.cls_swap("act-01", "SurvivorM_Boris"), None, "c1_act01", "FALLA", "clase"),
            ("combat", lambda e: e.combat("act-01"), None, "c3_act01", "FALLA", "rechazado"),
            ("cancel_after_start", lambda e: e.cancel_after_start("act-01", 0), None, "c3_act01", "FALLA", "cancelado"),
            ("finish_without_start", lambda e: e.finish_without_start("act-01", 0), None, "c3_act01", "FALLA", "fin_sin_empezar"),
            ("never_starts", lambda e: e.never_starts("act-01", 0, 3000), None, "c3_act01", "FALLA", "agotado"),
            ("late_start", lambda e: e.late_start("act-01", 0, 3000), None, "c3_act01", "FALLA", "despues_del_fin"),
        ]
        for label, inject_fn, drop_arg, target_judge, exp_verdict, exp_why in cases:
            with self.subTest(fault=label):
                engine = self._build_scene_engine()
                inject_fn(engine)
                samples, events = collect(engine, until_ms=22000, step_ms=200, drop=drop_arg)
                verdicts = self._evaluate_scene_judges(samples, events)
                self.assertEqual(verdicts[target_judge]["verdict"], exp_verdict)
                self.assertEqual(verdicts[target_judge]["why"], exp_why)
                for other_name, res in verdicts.items():
                    if other_name == target_judge:
                        continue
                    self.assertEqual(
                        res["verdict"],
                        "PASA",
                        f"Con fallo {label}, {other_name} cambio a {res}",
                    )

    def test_t_f3_roam(self) -> None:
        # T-F3: ROAM con radio 15 durante 10 min simulados (600 000 ms) y los tres fallos de ROAM.
        p0 = {"x": 6176.0, "z": 7632.0}
        window_ms = 600000
        step_ms = 500
        exp01 = {"cls": "SurvivorM_Mirek", "items": self.catalog["wardrobe_items"]["partisano"]}
        exp02 = {"cls": "SurvivorF_Linda", "items": self.catalog["wardrobe_items"]["civil"]}

        def _make_roam_engine() -> FakeActorEngine:
            engine = FakeActorEngine(self.catalog, FakeClock(0))
            engine.spawn("act-01", "SurvivorM_Mirek", p0["x"], p0["z"], 35, "partisano")
            engine.set_marks("act-01", [], "ROAM", 15)
            engine.request_gesture("act-01", 0, "EmotePoint")
            engine.spawn("act-02", "SurvivorF_Linda", 6189.0, 7638.0, 250, "civil")
            engine.set_marks("act-02", [], "HOLD", 15)
            engine.request_gesture("act-02", 0, "EmoteGreeting")
            return engine

        # Positivo: 10 min simulados -> PASA y todas las fotos con mark_i = -1.
        engine_ok = _make_roam_engine()
        samples_ok, events_ok = collect(engine_ok, until_ms=window_ms, step_ms=step_ms)
        self.assertTrue(all(row[7] == -1 for row in samples_ok["act-01"]))
        res_ok = judge_roam(samples_ok["act-01"], p0, 15, window_ms, 40, 4)
        self.assertEqual(res_ok["verdict"], "PASA")
        self.assertIsNone(res_ok["why"])

        # Negativos de ROAM (tabla de §5 y §8.3 T-F3), comprobando tambien que los demas jueces no cambian.
        roam_faults = [
            ("roam_escape", lambda e: e.roam_escape("act-01", 2, 22), "fuera_radio"),
            ("roam_stand_still", lambda e: e.roam_stand_still("act-01"), "quieto"),
            ("roam_no_stops", lambda e: e.roam_no_stops("act-01"), "quieto"),
        ]
        for label, inject_fn, exp_why in roam_faults:
            with self.subTest(fault=label):
                engine = _make_roam_engine()
                inject_fn(engine)
                samples, events = collect(engine, until_ms=window_ms, step_ms=step_ms)
                self.assertTrue(all(row[7] == -1 for row in samples["act-01"]))
                res = judge_roam(samples["act-01"], p0, 15, window_ms, 40, 4)
                self.assertEqual(res["verdict"], "FALLA")
                self.assertEqual(res["why"], exp_why)
                # Los demas jueces del mismo actor y del otro actor siguen en PASA.
                self.assertEqual(judge_identity(exp01, samples["act-01"][0])["verdict"], "PASA")
                self.assertEqual(judge_gesture(events, "act-01", 0)["verdict"], "PASA")
                self.assertEqual(judge_identity(exp02, samples["act-02"][0])["verdict"], "PASA")
                self.assertEqual(judge_gesture(events, "act-02", 0)["verdict"], "PASA")
                self.assertEqual(judge_hold(samples["act-02"], window_ms=10000)["verdict"], "PASA")

    def test_t_w1_catalogo(self) -> None:
        # T-W1 (§4 y §8.3): positivo contra catalog-m1.json y negativos por desajuste con wardrobes.
        self.assertTrue(_valid_wardrobe_catalog(self.catalog))
        self.assertEqual(self.catalog["wardrobe_items"], EXPECTED_WARDROBE_ITEMS)

        # Negativo 1: un preset de wardrobes sin entrada en wardrobe_items.
        missing_entry = copy.deepcopy(self.catalog)
        del missing_entry["wardrobe_items"]["cazador"]
        self.assertFalse(_valid_wardrobe_catalog(missing_entry))
        engine = FakeActorEngine(missing_entry, FakeClock(0))
        with self.assertRaises(ValueError):
            engine.spawn("act-01", "SurvivorM_Mirek", 100.0, 100.0, 0, "cazador")

        # Negativo 2: una entrada en wardrobe_items sin preset en wardrobes.
        extra_entry = copy.deepcopy(self.catalog)
        extra_entry["wardrobe_items"]["buzo"] = ["Hoodie_Grey"]
        self.assertFalse(_valid_wardrobe_catalog(extra_entry))


if __name__ == "__main__":
    unittest.main()
