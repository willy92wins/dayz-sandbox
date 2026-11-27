"""F3-offline-2 §2.1 y §3: validación con motor y órdenes `actor.apply` (T-V1..T-V5)."""
import copy
import json
import unittest
from pathlib import Path

from app.backend import actor_wire
from app.backend import scene_plan as sp

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"
HASH = "a" * 64


def _load(name):
    with open(FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


def _catalog():
    return _load("catalog-m1.json")


def _basic():
    return _load("escena-basica-cine.json")


def _without_actors(doc):
    doc = copy.deepcopy(doc)
    doc["entities"] = [e for e in doc["entities"] if e.get("kind") != "actor"]
    return doc


def _world_catalog(cat):
    classes = []
    for kind in ("objeto", "infectado", "animal", "actor"):
        classes.extend(cat["classes"][kind])
    return {"classes": classes}


def _validate(doc, engine="expansion", catalog_valid=True, cat=None, world_size=15360, rev=1):
    cat = cat if cat is not None else _catalog()
    return sp.validate_for_apply(
        doc, rev, HASH, cat, world_catalog=_world_catalog(cat),
        catalog_valid=catalog_valid, world_size=world_size,
        op_id="op-1", conn=1, actor_engine=engine,
    )


# §2.1, escrito a mano a partir de la fixture y del preset `partisano`.
ACT01 = {
    "f2": 1, "doc_id": None, "rev": 1, "hash": HASH,
    "a_lid": "act-01", "a_cls": "SurvivorM_Mirek",
    "a_x_mm": 6176000, "a_z_mm": 7632000, "a_yaw_mdeg": 35000,
    "a_items": ["GorkaEJacket_Flat", "GorkaPants_Flat", "MilitaryBoots_Black",
                "TacticalGloves_Black", "BalaclavaMask_Black"],
    "a_behaviour": "ONCE", "a_roam_mm": 15000,
    "mk_x_mm": [6181000, 6185000], "mk_z_mm": [7635000, 7639000],
    "g_emote": ["EmotePoint"], "g_at": [1], "g_t_ms": [-1],
}


class TestValidationEngine(unittest.TestCase):
    def test_v1_sin_motor_igual_que_hoy(self):
        res = _validate(_basic(), engine="none")
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "expansion_unavailable")
        self.assertEqual([e["pointer"] for e in res["errors"]], ["/entities/0", "/entities/1"])

    def test_v2_con_motor_ordenes_y_plan_iguales(self):
        doc = _basic()
        res = _validate(doc)
        self.assertTrue(res["ok"], res)
        self.assertEqual(len(res["actor_orders"]), 2)
        expected = dict(ACT01, doc_id=doc["doc_id"])
        self.assertEqual(res["actor_orders"][0], expected)
        self.assertEqual(res["actor_orders"][1]["a_lid"], "act-02")
        self.assertEqual(res["actor_orders"][1]["a_items"],
                         _catalog()["wardrobe_items"]["civil"])
        bare = _validate(_without_actors(doc))
        self.assertTrue(bare["ok"])
        self.assertEqual(bare["actor_orders"], [])
        for key in ("plan", "expectation", "envelope"):
            self.assertEqual(res[key], bare[key], key)

    def test_v2_sin_motor_sin_actores_no_lleva_ordenes(self):
        res = _validate(_without_actors(_basic()), engine="none")
        self.assertTrue(res["ok"])
        self.assertEqual(res["actor_orders"], [])

    def test_v2b_paso6_salta_actores(self):
        res = _validate(_basic())
        self.assertNotEqual(res.get("code"), "plan_too_large")
        self.assertTrue(res["ok"])

    def test_v4_precedencia_1b_antes_de_catalogo(self):
        doc = _basic()
        doc["entities"][0]["wardrobe"] = "nadie"
        res = _validate(doc, catalog_valid=False)
        self.assertEqual(res["code"], "actor_invalid")
        res = _validate(doc, engine="none", catalog_valid=False)
        self.assertEqual(res["code"], "expansion_unavailable")

    def test_v5_gestos_por_tiempo_y_por_marca(self):
        res = _validate(_basic())
        act02 = res["actor_orders"][1]
        self.assertEqual(act02["g_t_ms"], [1500])
        self.assertEqual(act02["g_at"], [-1])
        act01 = res["actor_orders"][0]
        self.assertEqual(act01["g_at"], [1])
        self.assertEqual(act01["g_t_ms"], [-1])

    def test_max_actors_igual_que_actor_wire(self):
        self.assertEqual(sp.MAX_ACTORS, actor_wire._MAX_ACTORS)


class TestActorInvalid(unittest.TestCase):
    """T-V3: una negativa por fila de §3, con su pointer exacto y nada más."""

    def _one(self, mutate, pointer, world_size=15360):
        doc = _basic()
        mutate(doc)
        res = _validate(doc, world_size=world_size)
        self.assertFalse(res["ok"], res)
        self.assertEqual(res["code"], "actor_invalid")
        self.assertEqual(res["http"], 422)
        self.assertEqual([e["pointer"] for e in res["errors"]], [pointer])

    def test_diecisiete_actores(self):
        def m(doc):
            base = doc["entities"][1]
            for k in range(15):
                extra = copy.deepcopy(base)
                extra["id"] = "act-%02d" % (k + 3)
                doc["entities"].append(extra)
        doc = _basic()
        m(doc)
        idx = [i for i, e in enumerate(doc["entities"]) if e["kind"] == "actor"][16]
        self._one(m, "/entities/%d" % idx)

    def test_id(self):
        self._one(lambda d: d["entities"][0].update(id="act-1"), "/entities/0/id")

    def test_id_largo(self):
        self._one(lambda d: d["entities"][0].update(id="act-1234567"), "/entities/0/id")

    def test_clase(self):
        self._one(lambda d: d["entities"][0].update(cls="SurvivorM_Nadie"), "/entities/0/cls")

    def test_vestuario(self):
        self._one(lambda d: d["entities"][0].update(wardrobe="nadie"), "/entities/0/wardrobe")

    def test_behaviour(self):
        self._one(lambda d: d["entities"][1].update(behaviour="WANDER"), "/entities/1/behaviour")

    def test_roam(self):
        self._one(lambda d: d["entities"][1].update(roam=0), "/entities/1/roam")

    def test_emote(self):
        self._one(lambda d: d["entities"][0]["gestures"][0].update(emote="EmoteNadie"),
                  "/entities/0/gestures/0/emote")

    def test_demasiadas_marcas(self):
        def m(d):
            d["entities"][0]["marks"] = [{"x": 6181.0, "z": 7635.0}] * 65
        self._one(m, "/entities/0/marks")

    def test_demasiados_gestos(self):
        def m(d):
            d["entities"][1]["gestures"] = [{"emote": "EmoteGreeting", "t": 1.0}] * 65
        self._one(m, "/entities/1/gestures")

    def test_once_sin_marcas(self):
        def m(d):
            d["entities"][0]["marks"] = []
            d["entities"][0]["gestures"] = []
        self._one(m, "/entities/0/marks")

    def test_gesto_sin_at_ni_t(self):
        self._one(lambda d: d["entities"][0]["gestures"][0].pop("at"), "/entities/0/gestures/0")

    def test_gesto_con_at_y_t(self):
        self._one(lambda d: d["entities"][0]["gestures"][0].update(t=1.0), "/entities/0/gestures/0")

    def test_at_cero(self):
        self._one(lambda d: d["entities"][0]["gestures"][0].update(at=0),
                  "/entities/0/gestures/0/at")

    def test_at_mayor_que_marcas(self):
        self._one(lambda d: d["entities"][0]["gestures"][0].update(at=3),
                  "/entities/0/gestures/0/at")

    def test_at_en_hold(self):
        def m(d):
            d["entities"][1]["gestures"] = [{"emote": "EmoteGreeting", "at": 1}]
        self._one(m, "/entities/1/gestures/0/at")

    def test_t_negativo(self):
        self._one(lambda d: d["entities"][1]["gestures"][0].update(t=-0.5),
                  "/entities/1/gestures/0/t")

    def test_marca_fuera(self):
        self._one(lambda d: d["entities"][0]["marks"][1].update(x=15360.5),
                  "/entities/0/marks/1")

    def test_marca_en_el_borde_vale(self):
        doc = _basic()
        doc["entities"][0]["marks"][1]["x"] = 15360.0
        self.assertTrue(_validate(doc)["ok"])

    def test_orden_que_no_cabe(self):
        cat = _catalog()
        cat["wardrobe_items"]["partisano"] = ["X" * 60] * 64
        doc = _basic()
        res = _validate(doc, cat=cat)
        self.assertEqual(res["code"], "actor_invalid")
        self.assertEqual([e["pointer"] for e in res["errors"]], ["/entities/0"])

    def test_cadena_larga_no_cabe(self):
        cat = _catalog()
        cat["wardrobe_items"]["partisano"] = ["X" * 1001]
        res = _validate(_basic(), cat=cat)
        self.assertEqual([e["pointer"] for e in res["errors"]], ["/entities/0"])

    def test_actor_ya_invalido_no_se_mide(self):
        cat = _catalog()
        cat["wardrobe_items"]["partisano"] = ["X" * 60] * 64
        doc = _basic()
        doc["entities"][1]["wardrobe"] = "nadie"
        doc["entities"][0]["wardrobe"] = "nadie"
        res = _validate(doc, cat=cat)
        self.assertEqual([e["pointer"] for e in res["errors"]],
                         ["/entities/0/wardrobe", "/entities/1/wardrobe"])


if __name__ == "__main__":
    unittest.main()
