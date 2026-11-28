"""F3-foto (plans/2026-11-28-m1-f3-foto-tope-brief.md §4): la foto peor de actores cabe en el cable."""
import copy
import json
import unittest
from pathlib import Path

from app.backend import actor_wire
from app.backend import scene_plan as sp
from app.backend.bridge import WIRE_CAP

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
HASH = "a" * 64
T = 999999999999


def _load(name):
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


CAT = _load("catalog-m1.json")


def _world_catalog(cat):
    classes = []
    for kind in ("objeto", "infectado", "animal", "actor"):
        classes.extend(cat["classes"][kind])
    return {"classes": classes}


def _validate(doc, world_size=15360):
    return sp.validate_for_apply(
        doc, 1, HASH, CAT, world_catalog=_world_catalog(CAT), catalog_valid=True,
        world_size=world_size, op_id="op-1", conn=1, actor_engine="expansion",
    )


def _actor(n, gestures, wardrobe="partisano"):
    return {
        "id": "act-%02d" % n, "kind": "actor", "cls": "SurvivorM_Mirek", "name": "A%d" % n,
        "x": 6176.0 + n, "z": 7632.0, "yaw": 35, "wardrobe": wardrobe, "behaviour": "HOLD",
        "roam": 15, "marks": [],
        "gestures": [{"emote": "EmoteGreeting", "t": 0.5 * j} for j in range(gestures)],
    }


def _doc(actors):
    doc = _load("escena-basica-cine.json")
    doc["entities"] = [e for e in doc["entities"] if e.get("kind") != "actor"] + actors
    return doc


def _photo(actors, world_size=15360):
    """Foto peor escrita aquí, sin usar el código bajo prueba."""
    x = int(min(world_size * 1000, 99999000))
    rows, events = [], []
    for a in actors:
        items = CAT["wardrobe_items"].get(a["wardrobe"], [])
        rows.append([a["id"], a["cls"], x, -9999999, x, 359999, list(items), 63, "unreachable", T])
        for j in range(len(a["gestures"])):
            events.append([a["id"], j, "requested", T, None])
            events.append([a["id"], j, "playing", T, None])
            events.append([a["id"], j, "canceled", T, "x" * 24])
    read = {"actors": rows, "gestures": events}
    env = {"op_id": "rd-999999", "session": "0" * 16, "epoch": "0" * 32, "status": "done",
           "reason": None, "dup": False, "read": read}
    return len(json.dumps(env, separators=(",", ":"), ensure_ascii=False).encode("utf-8")), read


def _max_gestures():
    g = 0
    while _photo([_actor(1, g + 1)])[0] <= WIRE_CAP:
        g += 1
    return g


G = _max_gestures()


class TestActorPhotoCap(unittest.TestCase):
    def test_f1_fixture(self):
        res = _validate(_load("escena-basica-cine.json"))
        self.assertTrue(res["ok"], res)

    def test_f2_borde(self):
        self.assertGreater(G, 0)
        self.assertLess(G, 64)
        ok = _validate(_doc([_actor(1, G)]))
        self.assertTrue(ok["ok"], ok)
        size, _ = _photo([_actor(1, G + 1)])
        bad = _validate(_doc([_actor(1, G + 1)]))
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["code"], "actor_invalid")
        self.assertEqual([e["pointer"] for e in bad["errors"]], ["/entities"])
        self.assertIn("%d B" % size, bad["errors"][0]["msg"])

    def test_f3_suma_de_actores(self):
        half = G // 2 + 1
        self.assertLessEqual(_photo([_actor(1, half)])[0], WIRE_CAP)
        self.assertGreater(_photo([_actor(1, half), _actor(2, half)])[0], WIRE_CAP)
        self.assertTrue(_validate(_doc([_actor(1, half)]))["ok"])
        res = _validate(_doc([_actor(1, half), _actor(2, half)]))
        self.assertEqual(res["code"], "actor_invalid")
        self.assertEqual([e["pointer"] for e in res["errors"]], ["/entities"])

    def test_f4_error_propio_primero(self):
        doc = _doc([_actor(1, G + 5, wardrobe="nadie")])
        res = _validate(doc)
        self.assertEqual(res["code"], "actor_invalid")
        pointers = [e["pointer"] for e in res["errors"]]
        self.assertNotIn("/entities", pointers)
        self.assertTrue(any(p.endswith("/wardrobe") for p in pointers), pointers)

    def test_f5_foto_valida(self):
        _, read = _photo([_actor(1, G)])
        self.assertTrue(actor_wire.valid_actor_read(read))


if __name__ == "__main__":
    unittest.main()
