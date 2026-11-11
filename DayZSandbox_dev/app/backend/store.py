"""Almacen local del documento de escena (brief F1a §3)."""

import copy
import hashlib
import json
import os
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

_PREFIX = {
    "actor": "act",
    "objeto": "obj",
    "infectado": "zmb",
    "animal": "ani",
}
_ACTOR_EXTRA = ("wardrobe", "behaviour", "roam", "marks", "gestures")
_SET_FIELDS = ("cls", "name", "yaw", "wardrobe", "behaviour", "roam")
_AMB_FIELDS = ("fecha", "hora", "nubes", "niebla", "lluvia", "viento")
_FIXTURE = "fixtures/escena-basica-cine.json"


def _hash_doc(doc):
    raw = json.dumps(
        doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _fail(code, pointer, msg, current=None, **extra):
    out = {"ok": False, "code": code, "pointer": pointer, "msg": msg, "current": current}
    out.update(extra)
    return out


def _author_key(author):
    if not isinstance(author, dict):
        return ("", "")
    return (author.get("role"), author.get("id"))


class Store:
    def __init__(self, path: str, catalog: dict, horizon: int = 1000, *, validator=None):
        if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
            raise ValueError("horizon debe ser un entero >= 1")
        self.path = path
        self.catalog = catalog
        self.horizon = horizon
        self.lock = threading.RLock()
        self.on_commit = None
        self.gate = None
        if validator is None:
            from app.backend.validate import validate as validator
        self._validate = validator
        self._hist = deque(maxlen=horizon)
        self._seen = deque(maxlen=horizon)
        self._seen_index = {}
        self._inv = {}
        self._undo = {}
        self._redo = {}
        self._load()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "doc_id": self._doc["doc_id"],
                "rev": self._rev,
                "hash": _hash_doc(self._doc),
                "doc": copy.deepcopy(self._doc),
            }

    def commit(self, author, request_id, doc_id, base_rev, label, ops) -> dict:
        with self.lock:
            return self._commit_locked(author, request_id, doc_id, base_rev, label, ops)

    def undo(self, author, request_id, doc_id) -> dict:
        with self.lock:
            return self._undo_redo_locked(author, request_id, doc_id, redo=False)

    def redo(self, author, request_id, doc_id) -> dict:
        with self.lock:
            return self._undo_redo_locked(author, request_id, doc_id, redo=True)

    def revert_batch(self, author, request_id, doc_id, batch_id) -> dict:
        with self.lock:
            canon = self._canon("revert", author, doc_id, None, batch_id, [batch_id])
            hit = self._dedup(request_id, canon)
            if hit is not None:
                return hit
            err = self._doc_gate(author, doc_id)
            if err:
                return self._remember(request_id, canon, err)
            if not isinstance(author, dict) or author.get("role") != "human":
                return self._remember(
                    request_id, canon, _fail("forbidden", "/author", "solo la persona puede revertir")
                )
            info = self._inv.get(batch_id)
            if info is None:
                return self._remember(
                    request_id, canon, _fail("not_found", "/batch_id", "tanda desconocida")
                )
            if info.get("reverted"):
                return self._remember(
                    request_id, canon, _fail("already_reverted", "/batch_id", "tanda ya revertida")
                )
            label = "Revertir: " + (info.get("label") or batch_id)
            return self._apply_inverse(
                author, request_id, canon, info, label, revert_of=batch_id, direction=-1
            )

    def freeze(self, doc_id, rev, hash) -> dict:
        with self.lock:
            if doc_id != self._doc.get("doc_id"):
                return _fail("doc_changed", "/doc_id", "documento distinto")
            digest = _hash_doc(self._doc)
            if rev == self._rev and hash == digest:
                return {
                    "ok": True,
                    "rev": self._rev,
                    "hash": digest,
                    "doc": copy.deepcopy(self._doc),
                }
            changed = [copy.deepcopy(rec) for rec in self._hist if rec["rev"] > rev]
            return _fail("stale_apply", "/rev", "revision distinta", current=changed)

    def _load(self):
        dest = self.path
        if not os.path.exists(dest):
            doc = self._read_fixture()
            errors = self._validate(doc, self.catalog)
            if errors:
                raise RuntimeError(
                    "fixture invalida: " + errors[0].get("code", "invalid")
                )
            self._ensure_next(doc)
            self._doc = doc
            self._rev = 1
            self._write(1, doc)
            return
        try:
            with open(dest, "r", encoding="utf-8") as fh:
                data = json.loads(fh.read())
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("almacen ilegible: " + dest) from exc
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("rev"), int)
            or isinstance(data.get("rev"), bool)
            or not isinstance(data.get("doc"), dict)
        ):
            raise RuntimeError("almacen invalido: " + dest)
        doc = data["doc"]
        errors = self._validate(doc, self.catalog)
        if errors:
            raise RuntimeError(
                "almacen invalido: " + dest + ": " + str(errors[0].get("code", "invalid"))
            )
        if "doc_id" not in doc:
            raise RuntimeError("almacen invalido: " + dest + ": sin doc_id")
        self._ensure_next(doc)
        self._doc = doc
        self._rev = data["rev"]

    def _read_fixture(self):
        candidates = [
            Path(_FIXTURE),
            Path(__file__).resolve().parents[2] / "fixtures" / "escena-basica-cine.json",
        ]
        for cand in candidates:
            if cand.is_file():
                try:
                    with cand.open("r", encoding="utf-8") as fh:
                        doc = json.loads(fh.read())
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise RuntimeError("fixture ilegible: " + str(cand)) from exc
                if not isinstance(doc, dict):
                    raise RuntimeError("fixture invalida: " + str(cand))
                return doc
        raise RuntimeError("no existe el almacen ni " + _FIXTURE)

    def _ensure_next(self, doc):
        nxt = doc.get("next")
        if not isinstance(nxt, dict):
            nxt = {}
            doc["next"] = nxt
        for key in ("act", "obj", "zmb", "ani", "cam"):
            if key not in nxt:
                nxt[key] = 1
        doc.setdefault("entities", [])
        doc.setdefault("cameras", [])
        doc.setdefault("ambiente", {})

    def _write(self, rev, doc):
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="scene-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(
                    {"rev": rev, "doc": doc},
                    fh,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
            tmp = None
        finally:
            if tmp is not None and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    def _canon(self, kind, author, doc_id, base_rev, label, ops):
        return json.dumps(
            {
                "kind": kind,
                "author": author,
                "doc_id": doc_id,
                "base_rev": base_rev,
                "label": label,
                "ops": ops,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )

    def _dedup(self, request_id, canon):
        if not isinstance(request_id, str) or request_id == "":
            return _fail("bad_op", "/request_id", "request_id vacio")
        prev = self._seen_index.get(request_id)
        if prev is None:
            return None
        if prev[0] == canon:
            return copy.deepcopy(prev[1])
        return _fail("request_conflict", "/request_id", "request_id con otro contenido")

    def _remember(self, request_id, canon, result):
        stored = copy.deepcopy(result)
        if request_id in self._seen_index:
            return stored
        if len(self._seen) == self._seen.maxlen:
            old_id, _old_canon = self._seen.popleft()
            self._seen_index.pop(old_id, None)
        self._seen.append((request_id, canon))
        self._seen_index[request_id] = (canon, stored)
        return copy.deepcopy(stored)

    def _doc_gate(self, author, doc_id):
        if doc_id != self._doc.get("doc_id"):
            return _fail("doc_changed", "/doc_id", "documento distinto")
        gate = self.gate
        if gate is not None:
            code = gate(author)
            if code:
                return _fail(code, "", str(code))
        return None

    def _check_base(self, base_rev):
        if not isinstance(base_rev, int) or isinstance(base_rev, bool) or base_rev < 0:
            return _fail("bad_base", "/base_rev", "base_rev invalido")
        if base_rev > self._rev:
            return _fail("bad_base", "/base_rev", "base_rev futura")
        if self._rev - base_rev > self.horizon:
            return _fail(
                "stale_base",
                "/base_rev",
                "base fuera del horizonte",
                current=self.snapshot(),
            )
        return None

    def _commit_locked(self, author, request_id, doc_id, base_rev, label, ops):
        canon = self._canon("commit", author, doc_id, base_rev, label, ops)
        hit = self._dedup(request_id, canon)
        if hit is not None:
            return hit
        err = self._doc_gate(author, doc_id)
        if err:
            return self._remember(request_id, canon, err)
        err = self._check_base(base_rev)
        if err:
            return self._remember(request_id, canon, err)
        before = copy.deepcopy(self._doc)
        draft = copy.deepcopy(before)
        err, fp, created = _apply(draft, ops)
        if err:
            return self._remember(request_id, canon, err)
        crossed = self._conflict(fp, base_rev)
        if crossed is not None and isinstance(author, dict) and author.get("role") == "ai":
            pointer, current = crossed
            return self._remember(
                request_id,
                canon,
                _fail("conflict", pointer, "conflicto con una tanda posterior", current=current),
            )
        errors = self._validate(draft, self.catalog) or []
        if errors:
            first = errors[0]
            return self._remember(
                request_id,
                canon,
                _fail(
                    "invalid",
                    first.get("pointer", ""),
                    first.get("msg", "invalido"),
                    errors=errors,
                ),
            )
        changes = _changes_for(before, draft, fp)
        public_fp = [[target, field] for _i, target, field in _collapse(fp)]
        key = _author_key(author)

        def on_stored(bid):
            self._redo[key] = []
            self._undo.setdefault(key, []).append(bid)

        result = self._publish(
            draft, author, label, ops, created, [], public_fp, changes, on_stored
        )
        return self._remember(request_id, canon, result)

    def _conflict(self, fp, base_rev):
        later = [rec for rec in self._hist if rec["rev"] > base_rev]

        def crosses(target, field, rec):
            for ot, of in rec["fp"]:
                if target == ot and (field == of or field == "*" or of == "*"):
                    return True
            return False

        for op_i, target, field in fp:
            hit_rec = None
            for rec in later:
                if crosses(target, field, rec):
                    hit_rec = rec
                    break
            if hit_rec is None:
                continue
            current = {}
            for _i2, t2, f2 in fp:
                if not any(crosses(t2, f2, rec) for rec in later):
                    continue
                slot = current.setdefault(t2, {})
                slot[f2] = _value(self._doc, t2, f2)
            return "/ops/" + str(op_i), current
        return None

    def _publish(self, doc, author, label, ops, created, partial, fp, changes, on_stored):
        new_rev = self._rev + 1
        digest = _hash_doc(doc)
        self._write(new_rev, doc)
        self._doc = doc
        self._rev = new_rev
        bid = "b-" + str(new_rev)
        rec = {
            "batch": bid,
            "rev": new_rev,
            "hash": digest,
            "author": copy.deepcopy(author) if isinstance(author, dict) else author,
            "label": label,
            "ops": copy.deepcopy(ops),
            "created": list(created),
            "partial": copy.deepcopy(partial),
            "fp": [list(pair) for pair in fp],
            "at_ms": int(time.time() * 1000),
        }
        self._hist.append(rec)
        self._inv[bid] = {
            "changes": copy.deepcopy(changes),
            "reverted": False,
            "label": label if isinstance(label, str) else label,
        }
        if on_stored is not None:
            on_stored(bid)
        if self.on_commit is not None:
            self.on_commit(copy.deepcopy(rec))
        return {
            "ok": True,
            "rev": new_rev,
            "hash": digest,
            "batch": bid,
            "created": list(created),
            "partial": copy.deepcopy(partial),
        }

    def _undo_redo_locked(self, author, request_id, doc_id, redo):
        kind = "redo" if redo else "undo"
        canon = self._canon(kind, author, doc_id, None, None, [])
        hit = self._dedup(request_id, canon)
        if hit is not None:
            return hit
        err = self._doc_gate(author, doc_id)
        if err:
            return self._remember(request_id, canon, err)
        key = _author_key(author)
        stack = self._redo if redo else self._undo
        pile = stack.get(key) or []
        if not pile:
            code = "nothing_to_redo" if redo else "nothing_to_undo"
            return self._remember(request_id, canon, _fail(code, "", code))
        bid = pile[-1]
        info = self._inv.get(bid)
        if info is None or bool(info.get("reverted")) != redo:  # deshacer pide viva; rehacer, deshecha
            pile.pop()
            code = "nothing_to_redo" if redo else "nothing_to_undo"
            return self._remember(request_id, canon, _fail(code, "", code))
        prefix = "Rehacer: " if redo else "Deshacer: "
        label = prefix + (info.get("label") or bid)
        direction = 1 if redo else -1
        return self._apply_inverse(
            author, request_id, canon, info, label, revert_of=bid, direction=direction, stack_op=kind
        )

    def _apply_inverse(self, author, request_id, canon, info, label, revert_of, direction, stack_op=None):
        draft = copy.deepcopy(self._doc)
        partial = []
        fp = []
        created = []
        changes = []
        for ch in info["changes"]:
            target, field = ch["target"], ch["field"]
            src = ch["after"] if direction < 0 else ch["before"]
            dst = ch["before"] if direction < 0 else ch["after"]
            cur = _value(draft, target, field)
            if _same(cur, src):
                _set_value(draft, target, field, dst)
                fp.append([target, field])
                changes.append(
                    {
                        "target": target,
                        "field": field,
                        "before": copy.deepcopy(cur),
                        "after": copy.deepcopy(dst),
                    }
                )
                if field == "*" and dst is not None and isinstance(dst, dict) and "id" in dst:
                    if cur is None:
                        created.append(dst["id"])
            else:
                partial.append({"target": target, "field": field, "why": "changed_later"})
        errors = self._validate(draft, self.catalog) or []
        if errors:
            first = errors[0]
            return self._remember(
                request_id,
                canon,
                _fail("invalid", first.get("pointer", ""), first.get("msg", "invalido"), errors=errors),
            )
        ops = [{"name": stack_op or "revert", "target": revert_of, "args": {}}]

        def on_stored(_bid):
            key = _author_key(author)
            if stack_op == "undo":
                self._undo[key].pop()
                self._inv[revert_of]["reverted"] = True
                self._redo.setdefault(key, []).append(revert_of)
            elif stack_op == "redo":
                self._redo[key].pop()
                self._inv[revert_of]["reverted"] = False
                self._undo.setdefault(key, []).append(revert_of)
            else:
                info["reverted"] = True
                for piles in (self._undo, self._redo):
                    for k in list(piles):
                        piles[k] = [b for b in piles[k] if b != revert_of]
                self._redo[key] = []

        result = self._publish(draft, author, label, ops, created, partial, fp, changes, on_stored)
        return self._remember(request_id, canon, result)


def _collapse(fp):
    """Si la huella trae (id, *), los campos sueltos de ese id sobran para la inversa."""
    stars = {target for _i, target, field in fp if field == "*"}
    seen = set()
    out = []
    for op_i, target, field in fp:
        if target in stars and field != "*":
            continue
        key = (target, field)
        if key in seen:
            continue
        seen.add(key)
        out.append((op_i, target, field))
    return out


def _changes_for(before, after, fp):
    changes = []
    for _op_i, target, field in _collapse(fp):
        changes.append(
            {
                "target": target,
                "field": field,
                "before": _value(before, target, field),
                "after": _value(after, target, field),
            }
        )
    return changes


def _find_list(doc, target):
    for key in ("entities", "cameras"):
        for ent in doc.get(key, []):
            if ent.get("id") == target:
                return key, ent
    return None, None


def _value(doc, target, field):
    if target == "ambiente":
        amb = doc.get("ambiente") or {}
        if field == "*":
            return copy.deepcopy(amb)
        return copy.deepcopy(amb.get(field))
    _list, ent = _find_list(doc, target)
    if ent is None:
        return None
    if field == "*":
        return copy.deepcopy(ent)
    return copy.deepcopy(ent.get(field))


def _set_value(doc, target, field, value):
    if target == "ambiente":
        if field == "*":
            doc["ambiente"] = copy.deepcopy(value) if value is not None else {}
        else:
            if value is None:
                doc.setdefault("ambiente", {}).pop(field, None)
            else:
                doc.setdefault("ambiente", {})[field] = copy.deepcopy(value)
        return
    if field == "*":
        _remove(doc, target)
        if value is not None:
            ent = copy.deepcopy(value)
            bucket = "cameras" if "keys" in ent and "kind" not in ent else "entities"
            doc.setdefault(bucket, []).append(ent)
        return
    list_name, ent = _find_list(doc, target)
    if ent is None:
        return
    if value is None:
        ent.pop(field, None)
    else:
        ent[field] = copy.deepcopy(value)


def _remove(doc, target):
    for key in ("entities", "cameras"):
        doc[key] = [e for e in doc.get(key, []) if e.get("id") != target]


def _apply(doc, ops):
    if not isinstance(ops, list):
        return _fail("bad_op", "/ops", "ops debe ser una lista"), [], []
    created_by = {}
    created = []
    fp = []
    for i, op in enumerate(ops):
        err = _apply_one(doc, ops, i, op, created_by, created, fp)
        if err:
            return err, [], []
    return None, fp, created


def _apply_one(doc, ops, i, op, created_by, created, fp):
    if not isinstance(op, dict) or not isinstance(op.get("name"), str):
        return _fail("bad_op", "/ops/" + str(i) + "/name", "operacion invalida")
    name = op["name"]
    if "args" in op and not isinstance(op["args"], dict):
        return _fail("bad_op", "/ops/" + str(i) + "/args", "args invalido")
    args = op.get("args") or {}
    known = {
        "entity.add",
        "entity.delete",
        "entity.move",
        "entity.set",
        "entity.marks",
        "entity.gestures",
        "ambient.set",
        "camera.add",
        "camera.delete",
        "camera.set",
    }
    if name not in known:
        return _fail("bad_op", "/ops/" + str(i) + "/name", "operacion desconocida")
    needs_target = name not in ("entity.add", "ambient.set", "camera.add")
    if needs_target:
        if "target" not in op:
            return _fail("bad_op", "/ops/" + str(i) + "/target", "falta target")
        tid, err = _resolve_target(op.get("target"), i, created_by)
        if err:
            err["pointer"] = "/ops/" + str(i) + "/target"
            return err
    else:
        tid = None
        if "target" in op:
            return _fail("bad_op", "/ops/" + str(i) + "/target", "target no aplica")
    if name == "entity.add":
        return _add_entity(doc, i, args, created_by, created, fp)
    if name == "camera.add":
        return _add_camera(doc, i, args, created_by, created, fp)
    if name == "entity.delete":
        return _delete_from(doc, i, tid, "entities", fp, args)
    if name == "camera.delete":
        return _delete_from(doc, i, tid, "cameras", fp, args)
    if name == "entity.move":
        return _move(doc, i, tid, args, fp)
    if name == "entity.set":
        return _set_fields(doc, i, tid, args, fp)
    if name == "entity.marks":
        return _replace_actor_list(doc, i, tid, args, "marks", fp)
    if name == "entity.gestures":
        return _replace_actor_list(doc, i, tid, args, "gestures", fp)
    if name == "ambient.set":
        return _ambient(doc, i, args, fp)
    if name == "camera.set":
        return _camera_set(doc, i, tid, args, fp)
    return _fail("bad_op", "/ops/" + str(i) + "/name", "operacion desconocida")


def _resolve_target(target, i, created_by):
    if not isinstance(target, str) or target == "":
        return None, _fail("bad_op", "", "target invalido")
    if target.startswith("$"):
        rest = target[1:]
        if not rest.isdigit():
            return None, _fail("bad_op", "", "target $n invalido")
        n = int(rest)
        if n >= i or n not in created_by:
            return None, _fail("bad_op", "", "target $n no creado")
        return created_by[n], None
    return target, None


def _extra(args, allowed, i):
    for key in args:
        if key not in allowed:
            return _fail("bad_op", "/ops/" + str(i) + "/args/" + key, "argumento de mas")
    return None


def _need(args, keys, i):
    for key in keys:
        if key not in args:
            return _fail("bad_op", "/ops/" + str(i) + "/args/" + key, "falta " + key)
    return None


def _num(args, key, i):
    val = args[key]
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return _fail("bad_op", "/ops/" + str(i) + "/args/" + key, "numero invalido")
    return None


def _add_entity(doc, i, args, created_by, created, fp):
    err = _need(args, ("kind", "cls", "name", "x", "z", "yaw"), i)
    if err:
        return err
    kind = args["kind"]
    if kind not in _PREFIX:
        return _fail("bad_op", "/ops/" + str(i) + "/args/kind", "kind invalido")
    allowed = ["kind", "cls", "name", "x", "z", "yaw"]
    if kind == "actor":
        allowed.extend(_ACTOR_EXTRA)
    err = _extra(args, allowed, i)
    if err:
        return err
    for key in ("x", "z", "yaw"):
        err = _num(args, key, i)
        if err:
            return err
    if not isinstance(args["cls"], str) or not isinstance(args["name"], str):
        return _fail("bad_op", "/ops/" + str(i) + "/args/cls", "tipo invalido")
    prefix = _PREFIX[kind]
    n = int(doc["next"][prefix])
    eid = prefix + "-" + f"{n:02d}"
    doc["next"][prefix] = n + 1
    ent = {
        "id": eid,
        "kind": kind,
        "cls": args["cls"],
        "name": args["name"],
        "x": args["x"],
        "z": args["z"],
        "yaw": args["yaw"],
    }
    if kind == "actor":
        for key in _ACTOR_EXTRA:
            if key in args:
                ent[key] = copy.deepcopy(args[key])
    doc["entities"].append(ent)
    created_by[i] = eid
    created.append(eid)
    fp.append((i, eid, "*"))
    return None


def _add_camera(doc, i, args, created_by, created, fp):
    err = _need(args, ("name", "keys"), i)
    if err:
        return err
    err = _extra(args, ("name", "keys"), i)
    if err:
        return err
    if not isinstance(args["name"], str) or not isinstance(args["keys"], list):
        return _fail("bad_op", "/ops/" + str(i) + "/args/keys", "keys invalido")
    n = int(doc["next"]["cam"])
    cid = "cam-" + f"{n:02d}"
    doc["next"]["cam"] = n + 1
    cam = {"id": cid, "name": args["name"], "keys": copy.deepcopy(args["keys"])}
    doc["cameras"].append(cam)
    created_by[i] = cid
    created.append(cid)
    fp.append((i, cid, "*"))
    return None


def _delete_from(doc, i, tid, bucket, fp, args):
    err = _extra(args, (), i)
    if err:
        return err
    found = False
    kept = []
    for ent in doc[bucket]:
        if ent.get("id") == tid:
            found = True
        else:
            kept.append(ent)
    if not found:
        return _fail("entity_gone", "/ops/" + str(i) + "/target", "no existe " + tid)
    doc[bucket] = kept
    fp.append((i, tid, "*"))
    return None


def _live_entity(doc, tid, i):
    for ent in doc["entities"]:
        if ent.get("id") == tid:
            return ent, None
    return None, _fail("entity_gone", "/ops/" + str(i) + "/target", "no existe " + tid)


def _move(doc, i, tid, args, fp):
    err = _need(args, ("x", "z"), i)
    if err:
        return err
    err = _extra(args, ("x", "z"), i)
    if err:
        return err
    for key in ("x", "z"):
        err = _num(args, key, i)
        if err:
            return err
    ent, err = _live_entity(doc, tid, i)
    if err:
        return err
    ent["x"] = args["x"]
    ent["z"] = args["z"]
    fp.append((i, tid, "x"))
    fp.append((i, tid, "z"))
    return None


def _set_fields(doc, i, tid, args, fp):
    if not args:
        return _fail("bad_op", "/ops/" + str(i) + "/args", "sin campos")
    err = _extra(args, _SET_FIELDS, i)
    if err:
        return err
    if "yaw" in args:
        err = _num(args, "yaw", i)
        if err:
            return err
    ent, err = _live_entity(doc, tid, i)
    if err:
        return err
    for key in _SET_FIELDS:
        if key in args:
            ent[key] = copy.deepcopy(args[key])
            fp.append((i, tid, key))
    return None


def _replace_actor_list(doc, i, tid, args, field, fp):
    err = _need(args, (field,), i)
    if err:
        return err
    err = _extra(args, (field,), i)
    if err:
        return err
    if not isinstance(args[field], list):
        return _fail("bad_op", "/ops/" + str(i) + "/args/" + field, "lista invalida")
    ent, err = _live_entity(doc, tid, i)
    if err:
        return err
    if ent.get("kind") != "actor":
        return _fail("bad_op", "/ops/" + str(i) + "/target", "no es un actor")
    ent[field] = copy.deepcopy(args[field])
    if field == "marks":
        fp.append((i, tid, "marks"))
        fp.append((i, tid, "gestures"))
    else:
        fp.append((i, tid, "gestures"))
    return None


def _ambient(doc, i, args, fp):
    if not args:
        return _fail("bad_op", "/ops/" + str(i) + "/args", "sin campos")
    err = _extra(args, _AMB_FIELDS, i)
    if err:
        return err
    amb = doc.setdefault("ambiente", {})
    for key in _AMB_FIELDS:
        if key in args:
            amb[key] = copy.deepcopy(args[key])
            fp.append((i, "ambiente", key))
    return None


def _camera_set(doc, i, tid, args, fp):
    if not args:
        return _fail("bad_op", "/ops/" + str(i) + "/args", "sin campos")
    err = _extra(args, ("name", "keys"), i)
    if err:
        return err
    if "name" in args and not isinstance(args["name"], str):
        return _fail("bad_op", "/ops/" + str(i) + "/args/name", "name invalido")
    if "keys" in args and not isinstance(args["keys"], list):
        return _fail("bad_op", "/ops/" + str(i) + "/args/keys", "keys invalido")
    cam = None
    for item in doc["cameras"]:
        if item.get("id") == tid:
            cam = item
            break
    if cam is None:
        return _fail("entity_gone", "/ops/" + str(i) + "/target", "no existe " + tid)
    for key in ("name", "keys"):
        if key in args:
            cam[key] = copy.deepcopy(args[key])
            fp.append((i, tid, key))
    return None
