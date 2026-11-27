"""F3-web §2 y §5.1: GET /api/catalog lleva wardrobe_items (K1, K2)."""
import copy
import json
import os
import unittest

from backend.profile import Profile


ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG = os.path.join(ROOT, "fixtures", "catalog-m1.json")


class _FakeStore:
    def __init__(self, catalog):
        self.catalog = catalog


def _catalog_view(catalog):
    p = Profile.__new__(Profile)
    p.store = _FakeStore(catalog)
    return p.get_catalog()


class CatalogWardrobeItemsTest(unittest.TestCase):
    def setUp(self):
        with open(CATALOG, "r", encoding="utf-8") as f:
            self.cat = json.load(f)

    def test_k1_fixture(self):
        view = _catalog_view(self.cat)
        items = view["wardrobe_items"]
        self.assertEqual(sorted(items.keys()), sorted(view["wardrobes"]))
        for name in view["wardrobes"]:
            self.assertEqual(items[name], self.cat["wardrobe_items"][name], name)

    def test_k2_raros(self):
        cat = copy.deepcopy(self.cat)
        cat["wardrobes"] = ["sin", "nolista", "mezcla"]
        cat["wardrobe_items"] = {"nolista": "Hoodie_Grey", "mezcla": ["A", 3, "", "B"]}
        view = _catalog_view(cat)
        self.assertEqual(view["wardrobe_items"], {"sin": [], "nolista": [], "mezcla": ["A", "B"]})

    def test_k2_sin_clave_y_resto_igual(self):
        cat = copy.deepcopy(self.cat)
        del cat["wardrobe_items"]
        view = _catalog_view(cat)
        self.assertEqual(view["wardrobe_items"], {w: [] for w in view["wardrobes"]})
        base = _catalog_view(self.cat)
        for key in ("ok", "source", "classes", "caps", "wardrobes", "emotes"):
            self.assertEqual(view[key], base[key], key)
        self.assertEqual(
            sorted(base.keys()),
            sorted(["ok", "source", "classes", "caps", "wardrobes", "emotes", "wardrobe_items"]),
        )


if __name__ == "__main__":
    unittest.main()
