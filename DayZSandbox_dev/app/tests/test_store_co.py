"""F1-co en el almacén: el gancho busy, check (VAL) y records_since."""
import unittest

from . import test_store
from .test_store import AI, HUMAN

StoreCase = test_store.StoreCase  # solo para los ayudantes; se borra abajo para no repetir sus pruebas


class StoreCo(unittest.TestCase):
    # los ayudantes de StoreCase, sin heredar (y repetir) sus pruebas
    setUp, tearDown, _write, _bytes, store, move = (StoreCase.setUp, StoreCase.tearDown, StoreCase._write,
                                                    StoreCase._bytes, StoreCase.store, StoreCase.move)

    def test_check_valida_sin_publicar(self):
        store = self.store()
        before, disk = store.snapshot(), self._bytes()
        res = store.check(AI, self.doc["doc_id"], 1, [self.move(x=30, z=20)])
        self.assertEqual((res["ok"], res["rev_if_applied"]), (True, 2))
        self.assertEqual(store.snapshot(), before)
        self.assertEqual(self._bytes(), disk)
        self.assertEqual(self.events, [])
        real = store.commit(AI, "c1", self.doc["doc_id"], 1, None, [self.move(x=30, z=20)])
        self.assertEqual(real["hash"], res["hash_if_applied"])

    def test_check_da_el_mismo_rechazo_que_commit(self):
        store = self.store()
        bad = [self.move(x=12, z=22), self.move(x=-1, z=22)]
        chk = store.check(HUMAN, self.doc["doc_id"], 1, bad)
        com = store.commit(HUMAN, "c2", self.doc["doc_id"], 1, None, bad)
        self.assertEqual((chk["code"], chk["pointer"]), (com["code"], com["pointer"]))
        self.assertEqual(chk["code"], "invalid")
        store.commit(HUMAN, "c3", self.doc["doc_id"], 1, None, [self.move(x=40, z=20)])
        clash = store.check(AI, self.doc["doc_id"], 1, [self.move(x=99, z=20)])
        self.assertEqual(clash["code"], "conflict")
        self.assertEqual(store.snapshot()["rev"], 2)

    def test_records_since(self):
        store = self.store(horizon=3)
        for i in range(5):
            store.commit(HUMAN, "r%d" % i, self.doc["doc_id"], store.snapshot()["rev"], None, [self.move(x=10 + i, z=20)])
        self.assertEqual([r["rev"] for r in store.records_since(4)], [5, 6])
        self.assertEqual(store.records_since(6), [])
        self.assertIsNone(store.records_since(2))  # anterior al horizonte de 3
        self.assertIsNone(store.records_since(7))  # futura

    def test_busy_rechaza_con_pointer_y_current(self):
        store = self.store()
        seen = []

        def busy(author, fp):
            seen.append(fp)
            return "busy_human" if author["role"] == "ai" and ["obj-01", "x"] in fp else None

        store.busy = busy
        ops = [{"name": "ambient.set", "args": {"niebla": 0.3}}, self.move(x=50, z=20)]
        res = store.commit(AI, "b1", self.doc["doc_id"], 1, None, ops)
        self.assertEqual((res["code"], res["pointer"]), ("busy_human", "/ops/1"))
        self.assertEqual(res["current"]["obj-01"]["x"], 10.0)
        self.assertEqual(store.snapshot()["rev"], 1)
        self.assertEqual(self.events, [])
        self.assertTrue(store.commit(HUMAN, "b2", self.doc["doc_id"], 1, None, ops)["ok"])
        self.assertIn([["ambiente", "niebla"]], seen)

    def test_busy_no_se_llama_al_deshacer(self):
        store = self.store()
        store.commit(AI, "u1", self.doc["doc_id"], 1, None, [self.move(x=50, z=20)])
        store.busy = lambda author, fp: "busy_human"
        self.assertTrue(store.undo(AI, "u2", self.doc["doc_id"])["ok"])


del StoreCase

if __name__ == "__main__":
    unittest.main()
