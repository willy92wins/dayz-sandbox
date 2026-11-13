"""Pruebas del almacen (brief F1a §6: A5, T1-T8 y T10 de almacen)."""

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from app.backend.store import Store

HUMAN = {"role": "human", "id": "web"}
AI = {"role": "ai", "id": "mcp"}
CATALOG = {"classes": {}, "caps": {"objeto": 20, "infectado": 10, "animal": 3, "actor": 2}}


def validate(doc, catalog):
    """Doble minimo: rechaza x o z fuera de [0, 15360]. El catalogo llega como dict."""
    del catalog
    errors = []
    for i, ent in enumerate(doc.get("entities") or []):
        for axis in ("x", "z"):
            val = ent.get(axis)
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                continue
            if not (0 <= val <= 15360):
                errors.append(
                    {
                        "code": "out_of_map",
                        "pointer": "/entities/" + str(i) + "/" + axis,
                        "msg": "fuera del mapa",
                    }
                )
    return errors


def scene(entities=None, nxt=None):
    return {
        "schema": "dsbx.scene/1",
        "doc_id": "d-00000001",
        "name": "Amanecer en Stary Sobor",
        "map": "chernarusplus",
        "ambiente": {
            "fecha": "2026-09-14",
            "hora": "06:10",
            "nubes": 0.35,
            "niebla": 0.12,
            "lluvia": 0,
            "viento": 3,
        },
        "entities": entities
        if entities is not None
        else [
            {
                "id": "obj-01",
                "kind": "objeto",
                "cls": "Land_Wreck_Ikarus",
                "name": "Autobus",
                "x": 10.0,
                "z": 20.0,
                "yaw": 5,
            }
        ],
        "cameras": [],
        "next": nxt or {"act": 1, "obj": 2, "zmb": 1, "ani": 1, "cam": 1},
    }


def digest(doc):
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "scene.json")
        self.doc = scene()
        self._write(1, self.doc)
        self.events = []

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, rev, doc):
        text = json.dumps({"rev": rev, "doc": doc}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with open(self.path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.write("\n")

    def _bytes(self):
        with open(self.path, "rb") as fh:
            return fh.read()

    def store(self, horizon=1000, doc=None):
        if doc is not None:
            self._write(1, doc)
        store = Store(self.path, CATALOG, horizon, validator=validate)
        store.on_commit = self.events.append
        return store

    def move(self, target="obj-01", x=11.0, z=21.0):
        return {"name": "entity.move", "target": target, "args": {"x": x, "z": z}}

    def test_a5_undo_redo_restores_hash(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        base = 1
        snaps = []
        for i, op in enumerate(
            (
                {"name": "entity.set", "target": "obj-01", "args": {"name": "Uno"}},
                {"name": "entity.set", "target": "obj-01", "args": {"yaw": 15}},
                {"name": "ambient.set", "args": {"hora": "07:00"}},
            )
        ):
            res = store.commit(HUMAN, "a5-" + str(i), doc_id, base, "tanda-" + str(i), [op])
            self.assertTrue(res["ok"], res)
            base = res["rev"]
            snaps.append(store.snapshot())
        self.assertTrue(store.undo(HUMAN, "a5-u1", doc_id)["ok"])
        self.assertTrue(store.undo(HUMAN, "a5-u2", doc_id)["ok"])
        mid = store.snapshot()
        self.assertEqual(mid["doc"], snaps[0]["doc"])
        self.assertEqual(mid["hash"], snaps[0]["hash"])
        self.assertEqual(mid["hash"], digest(snaps[0]["doc"]))
        self.assertTrue(store.redo(HUMAN, "a5-r1", doc_id)["ok"])
        back = store.snapshot()
        self.assertEqual(back["doc"], snaps[1]["doc"])
        self.assertEqual(back["hash"], snaps[1]["hash"])
        self.assertEqual(back["hash"], digest(snaps[1]["doc"]))

    def test_a5_replace_failure_keeps_previous_file(self):
        store = self.store()
        before = self._bytes()
        rev = store.snapshot()["rev"]
        with mock.patch("app.backend.store.os.replace", side_effect=OSError("disco")):
            with self.assertRaises(OSError):
                store.commit(HUMAN, "a5-fail", self.doc["doc_id"], rev, "x", [self.move()])
        self.assertEqual(self._bytes(), before)
        self.assertEqual(store.snapshot()["rev"], rev)
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 10.0)
        self.assertEqual(self.events, [])

    def test_t1_two_ops_one_rev(self):
        store = self.store()
        ops = [
            {
                "name": "entity.add",
                "args": {
                    "kind": "objeto",
                    "cls": "Barrel_Yellow",
                    "name": "Bidon",
                    "x": 3,
                    "z": 4,
                    "yaw": 0,
                },
            },
            {"name": "entity.move", "target": "$0", "args": {"x": 6, "z": 7}},
        ]
        res = store.commit(HUMAN, "t1", self.doc["doc_id"], 1, "alta", ops)
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["rev"], 2)
        self.assertEqual(res["batch"], "b-2")
        self.assertEqual(res["created"], ["obj-02"])
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["rev"], 2)
        ent = [e for e in store.snapshot()["doc"]["entities"] if e["id"] == "obj-02"][0]
        self.assertEqual(ent["x"], 6)
        self.assertEqual(ent["z"], 7)

    def test_t1_second_op_invalid_changes_nothing(self):
        store = self.store()
        before = self._bytes()
        ops = [
            self.move(x=12, z=22),
            self.move(x=-1, z=22),
        ]
        res = store.commit(HUMAN, "t1-bad", self.doc["doc_id"], 1, "rota", ops)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "invalid")
        self.assertEqual(res["pointer"], "/entities/0/x")
        self.assertTrue(res["errors"])
        self.assertEqual(self._bytes(), before)
        self.assertEqual(store.snapshot()["rev"], 1)
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 10.0)
        self.assertEqual(self.events, [])

    def test_t1_extra_arg_is_bad_op(self):
        store = self.store()
        before = self._bytes()
        op = self.move()
        op["args"]["yaw"] = 1
        res = store.commit(HUMAN, "t1-extra", self.doc["doc_id"], 1, None, [op])
        self.assertEqual(res["code"], "bad_op")
        self.assertEqual(res["pointer"], "/ops/0/args/yaw")
        self.assertEqual(self._bytes(), before)
        self.assertEqual(store.snapshot()["rev"], 1)

    def test_t2_ai_accepts_untouched_field(self):
        store = self.store()
        res = store.commit(AI, "t2-ok", self.doc["doc_id"], 1, "ia", [self.move(x=30, z=20)])
        self.assertTrue(res["ok"], res)
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 30)

    def test_t2_ai_conflict_on_human_field_and_delete(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        human = store.commit(HUMAN, "t2-h", doc_id, 1, "persona", [self.move(x=40, z=20)])
        self.assertTrue(human["ok"], human)
        before = self._bytes()
        events = len(self.events)
        clash = store.commit(AI, "t2-c", doc_id, 1, "ia", [self.move(x=99, z=20)])
        self.assertEqual(clash["code"], "conflict")
        self.assertEqual(clash["pointer"], "/ops/0")
        self.assertEqual(clash["current"]["obj-01"]["x"], 40)
        self.assertEqual(self._bytes(), before)
        self.assertEqual(len(self.events), events)
        gone = store.commit(
            AI, "t2-del", doc_id, 1, "borra", [{"name": "entity.delete", "target": "obj-01"}]
        )
        self.assertEqual(gone["code"], "conflict")
        self.assertEqual(gone["current"]["obj-01"]["*"]["x"], 40)
        self.assertEqual(store.snapshot()["rev"], human["rev"])
        self.assertEqual(self._bytes(), before)

    def test_t3_human_wins_on_stale_field(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        ai = store.commit(AI, "t3-ai", doc_id, 1, "ia", [self.move(x=50, z=20)])
        self.assertTrue(ai["ok"], ai)
        human = store.commit(HUMAN, "t3-h", doc_id, 1, "persona", [self.move(x=60, z=20)])
        self.assertTrue(human["ok"], human)
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 60)

    def test_t3_human_move_of_deleted_is_entity_gone(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        deleted = store.commit(AI, "t3-del", doc_id, 1, "borra", [{"name": "entity.delete", "target": "obj-01"}])
        self.assertTrue(deleted["ok"], deleted)
        before = self._bytes()
        res = store.commit(HUMAN, "t3-move", doc_id, 1, "tarde", [self.move()])
        self.assertEqual(res["code"], "entity_gone")
        self.assertEqual(res["pointer"], "/ops/0/target")
        self.assertEqual(self._bytes(), before)
        self.assertEqual(store.snapshot()["rev"], deleted["rev"])
        self.assertEqual(store.snapshot()["doc"]["entities"], [])

    def test_t4_base_inside_horizon_is_checked_and_accepted(self):
        store = self.store(horizon=5)
        doc_id = self.doc["doc_id"]
        base = 1
        for i in range(5):
            res = store.commit(
                HUMAN,
                "t4p-" + str(i),
                doc_id,
                base,
                "n",
                [{"name": "entity.set", "target": "obj-01", "args": {"name": "n" + str(i)}}],
            )
            self.assertTrue(res["ok"], res)
            base = res["rev"]
        self.assertEqual(base, 6)
        # Alguien toco el nombre; esta tanda toca yaw y su base queda 5 revisiones atras.
        ok = store.commit(
            HUMAN, "t4-edge", doc_id, 1, "borde", [{"name": "entity.set", "target": "obj-01", "args": {"yaw": 9}}]
        )
        self.assertTrue(ok["ok"], ok)
        self.assertEqual(ok["rev"], 7)
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["yaw"], 9)

    def test_t4_base_past_horizon_is_stale_even_without_overlap(self):
        store = self.store(horizon=5)
        doc_id = self.doc["doc_id"]
        base = 1
        for i in range(6):
            res = store.commit(
                HUMAN,
                "t4n-" + str(i),
                doc_id,
                base,
                "n",
                [{"name": "entity.set", "target": "obj-01", "args": {"name": "m" + str(i)}}],
            )
            self.assertTrue(res["ok"], res)
            base = res["rev"]
        self.assertEqual(base - 1, 6)
        before = self._bytes()
        stale = store.commit(
            AI,
            "t4-stale",
            doc_id,
            1,
            "vieja",
            [
                {
                    "name": "entity.add",
                    "args": {"kind": "objeto", "cls": "Barrel_Red", "name": "Nuevo", "x": 1, "z": 1, "yaw": 0},
                }
            ],
        )
        self.assertEqual(stale["code"], "stale_base")
        self.assertEqual(stale["current"]["rev"], base)
        self.assertEqual(self._bytes(), before)
        self.assertEqual(len(store.snapshot()["doc"]["entities"]), 1)

    def test_t5_undo_only_own_batch(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        human = store.commit(
            HUMAN, "t5-h", doc_id, 1, "giro", [{"name": "entity.set", "target": "obj-01", "args": {"yaw": 12}}]
        )
        ai = store.commit(
            AI, "t5-ai", doc_id, human["rev"], "nombre", [{"name": "entity.set", "target": "obj-01", "args": {"name": "IA"}}]
        )
        undone = store.undo(HUMAN, "t5-u", doc_id)
        self.assertTrue(undone["ok"], undone)
        self.assertEqual(undone["partial"], [])
        ent = store.snapshot()["doc"]["entities"][0]
        self.assertEqual(ent["yaw"], 5)
        self.assertEqual(ent["name"], "IA")
        self.assertIn("Deshacer:", self.events[-1]["label"])

    def test_t5_later_edit_is_kept(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        human = store.commit(HUMAN, "t5b-h", doc_id, 1, "mueve", [self.move(x=15, z=20)])
        store.commit(AI, "t5b-ai", doc_id, human["rev"], "pisa", [self.move(x=18, z=20)])
        undone = store.undo(HUMAN, "t5b-u", doc_id)
        self.assertTrue(undone["ok"], undone)
        self.assertTrue(any(p["why"] == "changed_later" and p["target"] == "obj-01" for p in undone["partial"]))
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 18)

    def test_t5_undo_add_keeps_retouched_entity(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        added = store.commit(
            HUMAN,
            "t5c-add",
            doc_id,
            1,
            "alta",
            [
                {
                    "name": "entity.add",
                    "args": {"kind": "objeto", "cls": "Barrel_Yellow", "name": "Bidon", "x": 8, "z": 8, "yaw": 0},
                }
            ],
        )
        self.assertEqual(added["created"], ["obj-02"])
        store.commit(AI, "t5c-mv", doc_id, added["rev"], "mueve", [self.move("obj-02", x=9, z=8)])
        undone = store.undo(HUMAN, "t5c-u", doc_id)
        self.assertTrue(undone["ok"], undone)
        self.assertTrue(any(p["why"] == "changed_later" and p["field"] == "*" for p in undone["partial"]))
        ids = [e["id"] for e in store.snapshot()["doc"]["entities"]]
        self.assertIn("obj-02", ids)

    def test_t5_undo_delete_recreates_same_id(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        deleted = store.commit(
            HUMAN, "t5d", doc_id, 1, "baja", [{"name": "entity.delete", "target": "obj-01"}]
        )
        self.assertTrue(deleted["ok"])
        undone = store.undo(HUMAN, "t5d-u", doc_id)
        self.assertTrue(undone["ok"], undone)
        self.assertEqual(undone["created"], ["obj-01"])
        ent = store.snapshot()["doc"]["entities"][0]
        self.assertEqual(ent["id"], "obj-01")
        self.assertEqual(ent["x"], 10.0)
        again = store.commit(
            HUMAN,
            "t5d-new",
            doc_id,
            undone["rev"],
            "otra",
            [
                {
                    "name": "entity.add",
                    "args": {"kind": "objeto", "cls": "Barrel_Red", "name": "Otro", "x": 2, "z": 2, "yaw": 0},
                }
            ],
        )
        self.assertEqual(again["created"], ["obj-02"])

    def test_t6_human_reverts_ai_batch(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        ai = store.commit(
            AI, "t6-ai", doc_id, 1, "nombre", [{"name": "entity.set", "target": "obj-01", "args": {"name": "IA"}}]
        )
        self.assertTrue(ai["ok"])
        forbidden = store.revert_batch(AI, "t6-no", doc_id, ai["batch"])
        self.assertEqual(forbidden["code"], "forbidden")
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["name"], "IA")
        back = store.revert_batch(HUMAN, "t6-yes", doc_id, ai["batch"])
        self.assertTrue(back["ok"], back)
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["name"], "Autobus")
        again = store.revert_batch(HUMAN, "t6-again", doc_id, ai["batch"])
        self.assertEqual(again["code"], "already_reverted")
        self.assertEqual(store.snapshot()["rev"], back["rev"])

    def test_t7_delete_then_add_uses_next_id(self):
        doc = scene(
            entities=[
                {
                    "id": "obj-20",
                    "kind": "objeto",
                    "cls": "Barrel_Yellow",
                    "name": "Bidon",
                    "x": 13,
                    "z": 2,
                    "yaw": 0,
                }
            ],
            nxt={"act": 1, "obj": 21, "zmb": 1, "ani": 1, "cam": 1},
        )
        store = self.store(doc=doc)
        res = store.commit(
            HUMAN,
            "t7",
            doc["doc_id"],
            1,
            "reemplazo",
            [
                {"name": "entity.delete", "target": "obj-20"},
                {
                    "name": "entity.add",
                    "args": {"kind": "objeto", "cls": "Barrel_Red", "name": "Nuevo", "x": 1, "z": 1, "yaw": 0},
                },
            ],
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["created"], ["obj-21"])
        ids = [e["id"] for e in store.snapshot()["doc"]["entities"]]
        self.assertEqual(ids, ["obj-21"])

    def test_t7_fifty_add_delete_never_reuses_id(self):
        doc = scene(entities=[], nxt={"act": 1, "obj": 1, "zmb": 1, "ani": 1, "cam": 1})
        store = self.store(doc=doc)
        doc_id = doc["doc_id"]
        base = 1
        created = []
        for i in range(50):
            added = store.commit(
                HUMAN,
                "t7a-" + str(i),
                doc_id,
                base,
                "alta",
                [
                    {
                        "name": "entity.add",
                        "args": {"kind": "objeto", "cls": "Barrel_Red", "name": "N", "x": 1, "z": 1, "yaw": 0},
                    }
                ],
            )
            self.assertTrue(added["ok"], added)
            created.extend(added["created"])
            base = added["rev"]
            deleted = store.commit(
                HUMAN,
                "t7d-" + str(i),
                doc_id,
                base,
                "baja",
                [{"name": "entity.delete", "target": added["created"][0]}],
            )
            self.assertTrue(deleted["ok"], deleted)
            base = deleted["rev"]
        self.assertEqual(created, ["obj-" + f"{n:02d}" for n in range(1, 51)])
        self.assertEqual(len(set(created)), 50)

    def test_t8_same_request_returns_same_result(self):
        store = self.store()
        ops = [self.move(x=4, z=5)]
        first = store.commit(HUMAN, "same", self.doc["doc_id"], 1, "una", ops)
        second = store.commit(HUMAN, "same", self.doc["doc_id"], 1, "una", ops)
        self.assertEqual(first, second)
        self.assertEqual(store.snapshot()["rev"], first["rev"])
        self.assertEqual(len(self.events), 1)

    def test_t8_same_request_other_ops_conflicts(self):
        store = self.store()
        doc_id = self.doc["doc_id"]
        first = store.commit(HUMAN, "dup", doc_id, 1, "una", [self.move(x=4, z=5)])
        self.assertTrue(first["ok"])
        before = self._bytes()
        other = store.commit(HUMAN, "dup", doc_id, 1, "una", [self.move(x=8, z=5)])
        self.assertEqual(other["code"], "request_conflict")
        self.assertEqual(store.snapshot()["rev"], first["rev"])
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 4)
        self.assertEqual(self._bytes(), before)

    def test_t10_ai_commits_when_gate_is_open(self):
        store = self.store()
        store.gate = lambda author: None
        res = store.commit(AI, "t10-ok", self.doc["doc_id"], 1, "ia", [self.move(x=3, z=3)])
        self.assertTrue(res["ok"], res)
        self.assertEqual(self.events[-1]["author"]["role"], "ai")

    def test_t10_pause_rejects_inflight_ai_batch(self):
        store = self.store()
        entered = threading.Event()
        release = threading.Event()
        state = {"paused": False}

        def gate(author):
            entered.set()
            self.assertTrue(release.wait(2))
            if state["paused"] and author["role"] == "ai":
                return "ai_paused"
            return None

        store.gate = gate
        box = {}

        def run():
            box["res"] = store.commit(AI, "t10-hold", self.doc["doc_id"], 1, "ia", [self.move(x=7, z=7)])

        thread = threading.Thread(target=run)
        thread.start()
        self.assertTrue(entered.wait(2))
        state["paused"] = True
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(box["res"]["code"], "ai_paused")
        self.assertEqual(store.snapshot()["rev"], 1)
        self.assertEqual(self.events, [])
        later = store.commit(AI, "t10-after", self.doc["doc_id"], 1, "ia", [self.move(x=8, z=8)])
        self.assertEqual(later["code"], "ai_paused")
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 10.0)

    def test_t10_take_locked_blocks_both(self):
        store = self.store()
        store.gate = lambda author: "take_locked"
        before = self._bytes()
        for author, req in ((HUMAN, "t10-h"), (AI, "t10-ai")):
            res = store.commit(author, req, self.doc["doc_id"], 1, "toma", [self.move()])
            self.assertEqual(res["code"], "take_locked")
        self.assertEqual(self._bytes(), before)
        self.assertEqual(store.snapshot()["rev"], 1)

    def test_freeze_current_and_stale(self):
        store = self.store()
        snap = store.snapshot()
        frozen = store.freeze(snap["doc_id"], snap["rev"], snap["hash"])
        self.assertTrue(frozen["ok"])
        frozen["doc"]["entities"][0]["x"] = 12345
        self.assertEqual(store.snapshot()["doc"]["entities"][0]["x"], 10.0)
        moved = store.commit(AI, "fr", snap["doc_id"], 1, "ia", [self.move(x=2, z=2)])
        stale = store.freeze(snap["doc_id"], snap["rev"], snap["hash"])
        self.assertEqual(stale["code"], "stale_apply")
        self.assertEqual(stale["current"][0]["rev"], moved["rev"])

    def test_illegible_file_is_not_overwritten(self):
        with open(self.path, "wb") as fh:
            fh.write(b"\xff no-json")
        before = self._bytes()
        with self.assertRaises(RuntimeError):
            Store(self.path, CATALOG, validator=validate)
        self.assertEqual(self._bytes(), before)

    def test_nothing_to_undo(self):
        store = self.store()
        res = store.undo(HUMAN, "vacio", self.doc["doc_id"])
        self.assertEqual(res["code"], "nothing_to_undo")


if __name__ == "__main__":
    unittest.main()
