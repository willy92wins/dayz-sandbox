"""Mundo falso en memoria para F2 sin juego (brief F2-offline §3 y §5).

Modela entidades vivas con inventario jerarquico, suelo determinista inyectable,
ticks simulados con deriva de criaturas tras soltar la IA, registro de propiedad
por epoch y escena, censo independiente que no lee el registro, e inyeccion de
fallos y reinicio de mision. Solo biblioteca estandar y sin red.

El gancho publico `seed_record(doc_id, lid, cls, x, z, session, op_id)` existe SOLO
para pruebas: siembra una entidad viva registrada en la escena con otra orden, para
comprobar que las compensaciones no borran lo que no es de su `(session, op_id)`.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
import re
import secrets
import threading
import time
from pathlib import Path

WIRE_CAP = 3500
SCENE_BATCH = 8
POS_TOL_M = 0.5

# Constantes de creacion verificadas en S-persist §3.1 y brief F2 §3.7
ECE_CREATEPHYSICS = 1024
ECE_INITAI = 2048
ECE_NOLIFETIME = 4194304
ECE_NOPERSISTENCY_WORLD = 8388608
ECE_NOPERSISTENCY_CHAR = 16777216
ECE_IN_INVENTORY = 787456
ECE_PLACE_ON_SURFACE = 1060
ECE_DYNAMIC_PERSISTENCY = 33554432  # PROHIBIDO (#11)
RF_DEFAULT = 512

FLAGS_STATIC = (
    ECE_PLACE_ON_SURFACE
    | ECE_NOLIFETIME
    | ECE_NOPERSISTENCY_WORLD
    | ECE_NOPERSISTENCY_CHAR
)  # 29361188
FLAGS_ROOT = FLAGS_STATIC
FLAGS_AI = FLAGS_STATIC | ECE_INITAI  # 29363236
FLAGS_CREATURE = FLAGS_AI
FLAGS_INV_OWN = (
    ECE_IN_INVENTORY
    | ECE_NOLIFETIME
    | ECE_NOPERSISTENCY_WORLD
    | ECE_NOPERSISTENCY_CHAR
)
FLAGS_CHILD = FLAGS_INV_OWN

_ROOT_DIR = Path(__file__).resolve().parents[2]
_CATALOG_M1_PATH = _ROOT_DIR / "fixtures" / "catalog-m1.json"

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_DOC_ID_RE = re.compile(r"^d-[0-9a-f]{8}$")
_LID_RE = re.compile(r"^(obj|zmb|ani)-(0[1-9]|[1-9][0-9]+)$")
_MAX_REV = 999999999  # 9 digitos (§3.6, M14)
_MAX_Y = 9999.999  # rango normativo de y y gy (§3.6)
_PREFIX_KIND = {
    "obj": "objeto",
    "zmb": "infectado",
    "ani": "animal",
}

# §5: Clases con inventario de M1 + contenedores pequenos habituales para hijos en pruebas
_INVENTORY_EXACT = frozenset({
    "LargeTent",
    "MediumTent",
    "CarTent",
    "WoodenCrate",
    "SeaChest",
    "Fireplace",
    "PowerGenerator",
    "FirstAidKit",
    "SmallProtectorCase",
    "AmmoBox",
    "TeddyBear",
    "Pot",
    "FryingPan",
    "CourierBag",
})
_INVENTORY_PREFIXES = (
    "Barrel_",
    "Bear_",
    "DryBag_",
    "WaterproofBag_",
    "TaloonBag_",
    "MountainBag_",
    "AliceBag_",
)


def _is_int(val: object) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _is_num(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _is_hex(val: object, length: int) -> bool:
    return isinstance(val, str) and len(val) == length and _HEX_RE.match(val) is not None


def _r3(val: float | int) -> float:
    out = round(float(val), 3)
    return 0.0 if out == 0.0 else out


def _r_yaw(val: float | int) -> float:
    """Redondea a 3 decimales y normaliza a [0, 360) (§3.3, F2-06)."""
    out = round(float(val), 3) % 360.0
    return 0.0 if out == 0.0 else out


def _has_3_decimals(val: float) -> bool:
    return abs(round(float(val), 3) - float(val)) <= 1e-9


def _is_ascii_text(val: object) -> bool:
    if not isinstance(val, str) or not val:
        return False
    try:
        val.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _valid_lid(val: object) -> bool:
    return (
        isinstance(val, str)
        and len(val) <= 10
        and _LID_RE.match(val) is not None
    )


def _canon_sha256(obj: object) -> str:
    raw = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hash_doc(doc: dict) -> str:
    """Hash canonico SHA-256 del documento, identico a Store._hash_doc."""
    return _canon_sha256(doc)


def compute_plan_sha256(
    doc_id: str, rev: int, doc_hash: str, classes: list[str], rows: list[list]
) -> str:
    """SHA-256 del JSON canonico de {doc_id, rev, hash, classes, rows} (§3.3)."""
    return _canon_sha256({
        "doc_id": doc_id,
        "rev": rev,
        "hash": doc_hash,
        "classes": classes,
        "rows": rows,
    })


def has_inventory(cls_name: str) -> bool:
    """Indica si una clase tiene inventario en el modelo del mundo falso (§5)."""
    if not isinstance(cls_name, str):
        return False
    if cls_name in _INVENTORY_EXACT:
        return True
    return any(cls_name.startswith(pref) for pref in _INVENTORY_PREFIXES)


def default_ground_y(x: float, z: float) -> float:
    """Suelo determinista y no plano por defecto (§5)."""
    fx = float(x)
    fz = float(z)
    return (
        120.0
        + 18.5 * math.sin(fx / 400.0)
        + 12.25 * math.cos(fz / 350.0)
        + 0.002 * (fx - fz)
    )


def _load_default_catalog() -> dict:
    with _CATALOG_M1_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _base_for_kind(kind: str, cls_name: str) -> str:
    if kind == "infectado":
        return "DayZInfected"
    if kind == "animal":
        return "DayZAnimal"
    if kind == "actor":
        return "SurvivorBase"
    if cls_name.startswith("Land_"):
        return "HouseNoDestruct"
    return "Inventory_Base"


def _normalize_catalog_classes(classes: object) -> list[list[str]]:
    if classes is None:
        cat = _load_default_catalog()
        classes = cat.get("classes", {})
    elif isinstance(classes, dict) and isinstance(classes.get("classes"), dict):
        classes = classes["classes"]

    pairs: list[list[str]] = []
    seen: set[str] = set()
    if isinstance(classes, dict):
        for kind in ("objeto", "infectado", "animal", "actor"):
            for item in classes.get(kind, ()):
                if isinstance(item, str) and item not in seen:
                    seen.add(item)
                    pairs.append([item, _base_for_kind(kind, item)])
        for kind, items in classes.items():
            if kind in ("objeto", "infectado", "animal", "actor"):
                continue
            if isinstance(items, (list, tuple)):
                for item in items:
                    if isinstance(item, str) and item not in seen:
                        seen.add(item)
                        pairs.append([item, _base_for_kind(kind, item)])
        return pairs

    if isinstance(classes, (list, tuple, set)):
        for item in classes:
            if isinstance(item, str):
                if item not in seen:
                    seen.add(item)
                    pairs.append([item, "EntityAI"])
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                cls_name = str(item[0])
                base_name = str(item[1])
                if cls_name not in seen:
                    seen.add(cls_name)
                    pairs.append([cls_name, base_name])
        return pairs

    raise ValueError("formato de classes no soportado")


def build_plan(
    doc: dict,
    *,
    rev: int = 1,
    hash: str | None = None,
    caps: dict | None = None,
    catalog: dict | None = None,
) -> dict:
    """Construye los args de scene.apply (§3.3) a partir de un documento."""
    doc_id = doc["doc_id"]
    doc_hash = hash if hash is not None else hash_doc(doc)

    if caps is None:
        cat = catalog if catalog is not None else _load_default_catalog()
        raw_caps = cat.get("caps", {})
        caps_out = {
            "objeto": int(raw_caps["objeto"]),
            "infectado": int(raw_caps["infectado"]),
            "animal": int(raw_caps["animal"]),
        }
        if "total" in raw_caps and raw_caps["total"] is not None:
            caps_out["total"] = int(raw_caps["total"])
    else:
        caps_out = copy.deepcopy(caps)

    non_actors = [
        ent for ent in doc.get("entities", [])
        if isinstance(ent, dict) and ent.get("kind") != "actor"
    ]
    classes = sorted({ent["cls"] for ent in non_actors})
    ci_by_cls = {cls_name: idx for idx, cls_name in enumerate(classes)}
    rows = [
        [
            ent["id"],
            ci_by_cls[ent["cls"]],
            _r3(ent["x"]),
            _r3(ent["z"]),
            _r_yaw(ent["yaw"]),
        ]
        for ent in non_actors
    ]
    plan_sha = compute_plan_sha256(doc_id, rev, doc_hash, classes, rows)
    return {
        "doc_id": doc_id,
        "rev": rev,
        "hash": doc_hash,
        "plan_sha256": plan_sha,
        "caps": caps_out,
        "classes": classes,
        "rows": rows,
    }


make_plan = build_plan


def _call_tick_fn(tick_fn, tick_s: float) -> None:
    try:
        sig = inspect.signature(tick_fn)
        req_pos = [
            p for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            and p.default is inspect.Parameter.empty
        ]
        if len(req_pos) == 1:
            tick_fn(tick_s)
            return
    except (TypeError, ValueError):
        pass
    tick_fn()


class _Entity:
    __slots__ = (
        "eid",
        "cls",
        "x",
        "y",
        "z",
        "yaw",
        "hp",
        "parent_eid",
        "slot",
        "flags",
        "alive",
        "origin",
        "scene",
        "is_creature",
        "ai_active",
        "children_eids",
    )

    def __init__(
        self,
        eid: str,
        cls: str,
        x: float,
        y: float,
        z: float,
        yaw: float,
        *,
        hp: float = 1.0,
        parent_eid: str | None = None,
        slot: str | None = None,
        flags: int = 0,
        origin: str = "sandbox",
        scene: str | None = None,
        is_creature: bool = False,
        ai_active: bool = False,
    ) -> None:
        self.eid = eid
        self.cls = cls
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.yaw = float(yaw)
        self.hp = float(hp)
        self.parent_eid = parent_eid
        self.slot = slot
        self.flags = int(flags)
        self.alive = True
        self.origin = origin
        self.scene = scene
        self.is_creature = bool(is_creature)
        self.ai_active = bool(ai_active)
        self.children_eids: list[str] = []


class _OpCtx:
    """Contador de efectos de una operacion, para lotes y barrera (M8, M10)."""

    __slots__ = ("effects", "in_batch")

    def __init__(self) -> None:
        self.effects = 0
        self.in_batch = 0


class _SceneState:
    __slots__ = (
        "doc_id",
        "gen_n",
        "generation",
        "retained_n",
        "retained",
        "pending_orders",
        "last",
        "checkpoint",
        "retained_rec_ids",
    )

    def __init__(self, doc_id: str) -> None:
        self.doc_id = doc_id
        self.gen_n = 0
        self.generation: dict | None = None
        self.retained_n = 0
        self.retained: list[str] = []
        # Ordenes de apply con registros sin retener en esta escena (M6, M11)
        self.pending_orders: list[tuple[str, str]] = []
        self.last: dict | None = None
        self.checkpoint: list[list] = []
        # ids de registros retenidos en la ultima operacion (para pending, M6)
        self.retained_rec_ids: set[int] = set()


class FakeWorld:
    """Mundo falso en memoria que cumple §3 y §5 del brief de F2-offline."""

    def __init__(
        self,
        classes=None,
        world_size: int | float = 15360,
        ground=None,
        tick_s: float = 0.0,
        creature_drift_m: float = 1.5,
        batch: int = SCENE_BATCH,
        epoch: str | None = None,
    ) -> None:
        if not _is_int(batch) or batch < 1:
            raise ValueError("batch debe ser un entero >= 1")
        if not _is_num(world_size) or float(world_size) < 0:
            raise ValueError("world_size debe ser >= 0")
        if epoch is not None and not _is_hex(epoch, 32):
            raise ValueError("epoch debe ser 32 hex")

        self._lock = threading.RLock()
        self._catalog_classes = _normalize_catalog_classes(classes)
        self._known_classes: set[str] = {pair[0] for pair in self._catalog_classes}
        self.world_size = world_size
        self._ground = ground
        self.tick_s = float(tick_s)
        self.creature_drift_m = float(creature_drift_m)
        self.batch = int(batch)
        self.epoch: str = epoch.lower() if isinstance(epoch, str) else secrets.token_hex(16)
        self.storage_ops: int = 0

        self._next_eid = 1
        self._seed_seq = 0
        self._tick_gen = 0
        self._entities: dict[str, _Entity] = {}
        self._registry: list[dict] = []
        self._scenes: dict[str, _SceneState] = {}
        self._effects: dict[tuple[str, str], dict[str, int]] = {}

        # Ganchos de fallo inyectable; la clave puede ser `lid` (todas las escenas)
        # o `(doc_id, lid)` para una escena concreta (M17).
        self._fail_create: set[object] = set()
        self._suppress_create: set[object] = set()
        self._displace_on_create: dict[object, object] = {}
        self._fail_delete: set[object] = set()

        # Barrera de prueba (M8): espera en el efecto n, fuera del cerrojo.
        self._barrier_n: int | None = None
        self._barrier_reached: threading.Event | None = None
        self._barrier_release: threading.Event | None = None

    # -- catalogo, suelo y storage -------------------------------------------

    def catalog_classes(self) -> list[list[str]]:
        with self._lock:
            return [list(pair) for pair in self._catalog_classes]

    def ground_y(self, x: float, z: float) -> float:
        fx = float(x)
        fz = float(z)
        g = self._ground
        if g is None:
            return default_ground_y(fx, fz)
        if callable(g):
            return float(g(fx, fz))
        if _is_num(g):
            return float(g)
        raise TypeError("ground debe ser invocable o numerico")

    def has_inventory(self, cls_name: str) -> bool:
        return has_inventory(cls_name)

    def touch_storage(self) -> int:
        with self._lock:
            self.storage_ops += 1
            return self.storage_ops

    storage_write = touch_storage
    storage_delete = touch_storage

    # -- ticks y deriva de IA ------------------------------------------------

    def _drift_creatures_locked(self) -> None:
        if self.tick_s <= 0.0 or self.creature_drift_m <= 0.0:
            return
        limit = float(self.world_size)
        for ent in self._entities.values():
            if not ent.alive or not ent.is_creature or not ent.ai_active:
                continue
            rad = math.radians(ent.yaw)
            nx = ent.x + self.creature_drift_m * math.cos(rad)
            nz = ent.z + self.creature_drift_m * math.sin(rad)
            if nx < 0.0 or nx > limit or nz < 0.0 or nz > limit:
                nx = max(0.0, min(limit, ent.x - self.creature_drift_m * math.cos(rad)))
                nz = max(0.0, min(limit, ent.z - self.creature_drift_m * math.sin(rad)))
            ent.x = nx
            ent.z = nz
            if ent.parent_eid is None:
                ent.y = self.ground_y(nx, nz)

    def tick(self) -> None:
        """Avanza un tick simulado: duerme tick_s y deriva criaturas con IA suelta."""
        if self.tick_s > 0.0:
            time.sleep(self.tick_s)
        with self._lock:
            self._tick_gen += 1
            self._drift_creatures_locked()

    def _do_tick(self, tick_fn) -> None:
        if tick_fn is None or tick_fn == self.tick:
            self.tick()
            return
        with self._lock:
            before_gen = self._tick_gen
        _call_tick_fn(tick_fn, self.tick_s)
        with self._lock:
            if self._tick_gen == before_gen:
                self._tick_gen += 1
                self._drift_creatures_locked()

    # -- utilidades internas de entidades y registro -------------------------

    def _scene_state_locked(self, doc_id: str, *, create: bool = False) -> _SceneState | None:
        st = self._scenes.get(doc_id)
        if st is None and create:
            st = _SceneState(doc_id)
            self._scenes[doc_id] = st
        return st

    def _record_effect_locked(self, session: str, op_id: str, kind: str) -> None:
        slot = self._effects.setdefault((session, op_id), {"created": 0, "deleted": 0})
        slot[kind] += 1

    def _alloc_eid_locked(self) -> str:
        eid = f"ent-{self._next_eid}"
        self._next_eid += 1
        return eid

    @staticmethod
    def _hook_hit(container, doc_id: str, lid: str) -> bool:
        return (doc_id, lid) in container or lid in container

    def _scene_records_locked(self, doc_id: str) -> list[dict]:
        return [
            r for r in self._registry
            if r["epoch"] == self.epoch and r["scene_id"] == doc_id
        ]

    def _op_records_locked(self, doc_id: str, session: str, op_id: str) -> list[dict]:
        return [
            r for r in self._registry
            if r["epoch"] == self.epoch
            and r["scene_id"] == doc_id
            and r["op"]["session"] == session
            and r["op"]["op_id"] == op_id
        ]

    def _prune_pending_locked(self, doc_id: str) -> None:
        """Quita del pending las ordenes sin registros o con solo registros retenidos (M6)."""
        st = self._scenes.get(doc_id)
        if st is None:
            return
        alive: list[tuple[str, str]] = []
        for sess, oid in st.pending_orders:
            recs = self._op_records_locked(doc_id, sess, oid)
            if not recs:
                continue
            if all(id(r) in st.retained_rec_ids for r in recs):
                continue
            alive.append((sess, oid))
        st.pending_orders = alive

    def _pending_report_locked(self, doc_id: str, st: _SceneState) -> dict | None:
        for sess, oid in st.pending_orders:
            recs = self._op_records_locked(doc_id, sess, oid)
            if recs:
                return {"session": sess, "op_id": oid, "n": len(recs)}
        return None

    def _set_retention_locked(
        self, st: _SceneState, retained_recs: list[dict]
    ) -> None:
        """Fija retained_n/retained y los ids retenidos de la ultima operacion (M11)."""
        lids = [r["lid"] for r in retained_recs]
        st.retained_n = len(lids)
        st.retained = lids[:8]
        st.retained_rec_ids = {id(r) for r in retained_recs}

    def _drift_one_locked(self, ent: _Entity) -> None:
        """Mueve una criatura al soltar su IA (§5): ya no esta en su pose de creacion."""
        if self.creature_drift_m <= 0.0 or not ent.is_creature or not ent.ai_active:
            return
        limit = float(self.world_size)
        rad = math.radians(ent.yaw)
        nx = ent.x + self.creature_drift_m * math.cos(rad)
        nz = ent.z + self.creature_drift_m * math.sin(rad)
        if nx < 0.0 or nx > limit or nz < 0.0 or nz > limit:
            nx = max(0.0, min(limit, ent.x - self.creature_drift_m * math.cos(rad)))
            nz = max(0.0, min(limit, ent.z - self.creature_drift_m * math.sin(rad)))
        ent.x = nx
        ent.z = nz
        if ent.parent_eid is None:
            ent.y = self.ground_y(nx, nz)

    def _cascade_delete_locked(self, ent: _Entity) -> None:
        """Borra la entidad y todo lo que contiene, como DayZ (M2)."""
        stack: list[_Entity] = [ent]
        killed: list[_Entity] = []
        seen: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur.eid in seen:
                continue
            seen.add(cur.eid)
            for cid in list(cur.children_eids):
                child = self._entities.get(cid)
                if child is not None and child.alive:
                    stack.append(child)
            if cur.alive:
                cur.alive = False
                cur.ai_active = False
                killed.append(cur)
        killed_ids = {k.eid for k in killed}
        for k in killed:
            parent = self._entities.get(k.parent_eid) if k.parent_eid else None
            if parent is not None and k.eid in parent.children_eids:
                parent.children_eids.remove(k.eid)
            k.parent_eid = None
            k.slot = None
        if killed_ids:
            self._registry = [r for r in self._registry if r["eid"] not in killed_ids]

    def _barrier_hit_locked(self, ctx: "_OpCtx") -> bool:
        return self._barrier_n is not None and ctx.effects == self._barrier_n

    def _barrier_wait(self) -> None:
        """Espera fuera del cerrojo a que la prueba libere la barrera (M8)."""
        with self._lock:
            reached = self._barrier_reached
            release = self._barrier_release
            self._barrier_n = None
        if reached is not None:
            reached.set()
        if release is not None:
            release.wait()

    def _resolve_live_entity_locked(self, ref: object) -> _Entity:
        if isinstance(ref, tuple) and len(ref) == 2:
            doc_id, lid = ref
            for rec in self._registry:
                if rec["epoch"] == self.epoch and rec["scene_id"] == doc_id and rec["lid"] == lid:
                    ent = self._entities.get(rec["eid"])
                    if ent is not None and ent.alive:
                        return ent
            raise ValueError(f"entidad viva no encontrada para {(doc_id, lid)!r}")

        if isinstance(ref, str):
            ent = self._entities.get(ref)
            if ent is not None and ent.alive:
                return ent
            matches: list[_Entity] = []
            for rec in self._registry:
                if rec["epoch"] == self.epoch and rec["lid"] == ref:
                    cand = self._entities.get(rec["eid"])
                    if cand is not None and cand.alive:
                        matches.append(cand)
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise ValueError(f"lid ambiguo entre varias escenas: {ref!r}")
        raise ValueError(f"entidad viva no encontrada: {ref!r}")

    def _detach_from_parent_locked(self, ent: _Entity) -> None:
        if ent.parent_eid is not None:
            parent = self._entities.get(ent.parent_eid)
            if parent is not None and ent.eid in parent.children_eids:
                parent.children_eids.remove(ent.eid)
            ent.parent_eid = None
            ent.slot = None

    def _attach_to_parent_locked(self, ent: _Entity, parent: _Entity, slot: str) -> None:
        if not parent.alive:
            raise ValueError("el contenedor padre no vive")
        if not has_inventory(parent.cls):
            raise ValueError(f"la clase {parent.cls!r} no tiene inventario")
        if slot != "cargo" and not (isinstance(slot, str) and slot.startswith("att:") and len(slot) > 4):
            raise ValueError(f"hueco invalido: {slot!r}")
        # Evitar ciclos en jerarquia
        cur: str | None = parent.eid
        visited: set[str] = set()
        while cur is not None:
            if cur == ent.eid or cur in visited:
                raise ValueError("ciclo en jerarquia de inventario")
            visited.add(cur)
            p = self._entities.get(cur)
            cur = p.parent_eid if p is not None and p.alive else None
        self._detach_from_parent_locked(ent)
        ent.parent_eid = parent.eid
        ent.slot = slot
        if ent.eid not in parent.children_eids:
            parent.children_eids.append(ent.eid)

    def _inventory_descendants_locked(self, root_eid: str) -> list[_Entity]:
        """Recorrido PREORDER de descendientes vivos dentro del inventario de root_eid."""
        root = self._entities.get(root_eid)
        if root is None or not root.alive or not has_inventory(root.cls):
            return []
        out: list[_Entity] = []
        visited: set[str] = {root_eid}
        stack: list[str] = list(reversed(root.children_eids))
        while stack:
            cid = stack.pop()
            if cid in visited:
                continue
            child = self._entities.get(cid)
            if child is None or not child.alive or child.parent_eid not in visited:
                continue
            visited.add(cid)
            out.append(child)
            if has_inventory(child.cls) and child.children_eids:
                for gcid in reversed(child.children_eids):
                    if gcid not in visited:
                        stack.append(gcid)
        return out

    def _hierarchy_depth_locked(self, eid: str) -> int:
        depth = 0
        visited: set[str] = set()
        cur = self._entities.get(eid)
        while cur is not None and cur.alive and cur.parent_eid is not None:
            if cur.parent_eid in visited:
                break
            visited.add(cur.parent_eid)
            parent = self._entities.get(cur.parent_eid)
            if parent is None or not parent.alive:
                break
            depth += 1
            cur = parent
        return depth

    def _has_foreign_descendant_locked(self, eid: str, deletable_eids: set[str]) -> bool:
        for desc in self._inventory_descendants_locked(eid):
            if desc.eid not in deletable_eids:
                return True
        return False

    def _mark_retained_with_ancestors_locked(
        self,
        ent: _Entity,
        rec: dict,
        deletable_by_eid: dict[str, dict],
        retained_ids: set[int],
    ) -> None:
        retained_ids.add(id(rec))
        visited: set[str] = {ent.eid}
        cur_eid = ent.parent_eid
        while cur_eid is not None and cur_eid not in visited:
            visited.add(cur_eid)
            anc_ent = self._entities.get(cur_eid)
            if anc_ent is None or not anc_ent.alive:
                break
            anc_rec = deletable_by_eid.get(cur_eid)
            if anc_rec is not None:
                retained_ids.add(id(anc_rec))
            cur_eid = anc_ent.parent_eid

    def _compute_retention_locked(self, deletable_records: list[dict]) -> set[int]:
        """Calcula los registros retenidos segun S-persist §3.3 punto 2 y D5."""
        deletable_eids: set[str] = set()
        deletable_by_eid: dict[str, dict] = {}
        for rec in deletable_records:
            ent = self._entities.get(rec["eid"])
            if ent is not None and ent.alive:
                deletable_eids.add(ent.eid)
                deletable_by_eid[ent.eid] = rec

        retained_ids: set[int] = set()
        for rec in deletable_records:
            ent = self._entities.get(rec["eid"])
            if ent is None or not ent.alive:
                continue
            if self._has_foreign_descendant_locked(ent.eid, deletable_eids):
                self._mark_retained_with_ancestors_locked(
                    ent, rec, deletable_by_eid, retained_ids
                )
        return retained_ids

    def _delete_deletable(
        self,
        *,
        session: str,
        op_id: str,
        doc_id: str,
        order_epoch: str,
        ctx: "_OpCtx",
        initial_retained_ids: set[int],
        stop_on_retention: bool,
        clear_gen_on_first_delete: bool,
        check,
        tick,
        op_scope: tuple[str, str] | None = None,
    ) -> tuple[bool, set[int], str | None]:
        """Borra lo borrable no retenido en dos pasadas (hijos y luego raices) por lotes.

        `op_scope` limita lo borrable a los registros de esa `(session, op_id)` (D8 y
        §3.4 paso 2): solo lo pasan las dos compensaciones. El paso 4 del apply y el
        reset normal pasan `None` y borran lo borrable de toda la escena.
        Revalida la retencion justo antes de cada borrado bajo self._lock (TOCTOU),
        confirma cada borrado (D5) y para con `delete_failed` si no se confirma.
        Con `stop_on_retention` (apply, §3.3 paso 4) para al encontrar retencion;
        sin el (reset y compensacion, §3.4) la salta y sigue.
        Devuelve (had_effect, retained_ids, parada) donde `parada` es
        None, "delete_failed", "retention_stop", "stale_epoch" o el motivo de `check`.
        """
        retained_ids = set(initial_retained_ids)
        had_effect = False
        parada: str | None = None

        # Relee el registro y reordena en cada pasada (M1): hijos de mas profundo
        # a menos profundo, empates en el orden del registro; luego raices en ese orden.
        with self._lock:
            if op_scope is None:
                deletable_records = self._scene_records_locked(doc_id)
            else:
                deletable_records = self._op_records_locked(
                    doc_id, op_scope[0], op_scope[1]
                )
            deletable_eids: set[str] = set()
            deletable_by_eid: dict[str, dict] = {}
            for r in deletable_records:
                ent = self._entities.get(r["eid"])
                if ent is not None and ent.alive:
                    deletable_eids.add(ent.eid)
                    deletable_by_eid[ent.eid] = r

            pass1 = [
                r for r in deletable_records
                if r["parent_lid"] is not None and id(r) not in retained_ids
            ]
            pass1.sort(key=lambda r: -self._hierarchy_depth_locked(r["eid"]))
            pass2 = [
                r for r in deletable_records
                if r["parent_lid"] is None and id(r) not in retained_ids
            ]
            queue = pass1 + pass2

        for rec in queue:
            with self._lock:
                # M3: con el cerrojo, antes de cualquier efecto, si el mundo reinicio
                # el verbo para sin escribir nada (tambien antes de saltar registros
                # que el reinicio ya se llevo, o `parada` quedaria en None).
                if self.epoch != order_epoch:
                    parada = "stale_epoch"
                    break
                if id(rec) in retained_ids or rec not in self._registry:
                    continue

            if check is not None:
                fail = check()
                if fail is not None:
                    parada = fail
                    break

            do_batch_tick = False
            hit_barrier = False
            with self._lock:
                # M3: antes de cada efecto, con el cerrojo, si el mundo reinicio
                if self.epoch != order_epoch:
                    parada = "stale_epoch"
                    break
                if id(rec) in retained_ids or rec not in self._registry:
                    continue
                ent = self._entities.get(rec["eid"])
                if ent is None or not ent.alive:
                    self._registry.remove(rec)
                    if clear_gen_on_first_delete:
                        st = self._scene_state_locked(doc_id, create=True)
                        st.generation = None
                        st.checkpoint = []
                    had_effect = True
                    continue

                # D5/TOCTOU: justo antes de borrar, en el mismo tick y con el cerrojo
                if self._has_foreign_descendant_locked(ent.eid, deletable_eids):
                    self._mark_retained_with_ancestors_locked(
                        ent, rec, deletable_by_eid, retained_ids
                    )
                    retained_ids.add(id(rec))
                    if stop_on_retention:
                        parada = "retention_stop"
                        break
                    continue

                # D5: se pide el borrado y se comprueba que la entidad ya no vive.
                if self._hook_hit(self._fail_delete, doc_id, rec["lid"]):
                    parada = "delete_failed"
                    break
                self._cascade_delete_locked(ent)
                if ent.alive:
                    parada = "delete_failed"
                    break

                deletable_eids.discard(ent.eid)
                self._record_effect_locked(session, op_id, "deleted")
                if clear_gen_on_first_delete:
                    st = self._scene_state_locked(doc_id, create=True)
                    st.generation = None
                    st.checkpoint = []
                had_effect = True
                ctx.effects += 1
                ctx.in_batch += 1
                if ctx.in_batch >= self.batch:
                    ctx.in_batch = 0
                    do_batch_tick = True
                hit_barrier = self._barrier_hit_locked(ctx)

            if hit_barrier:
                self._barrier_wait()
            if do_batch_tick:
                self._do_tick(tick)

        if parada is None and ctx.in_batch > 0 and had_effect:
            self._do_tick(tick)
            ctx.in_batch = 0

        return had_effect, retained_ids, parada

    # -- lecturas y verbos de §3 ---------------------------------------------

    def read(self, doc_id: str) -> dict:
        """Lectura de estado del mundo y de la escena (§3.2)."""
        with self._lock:
            reg_rows = sorted(
                [
                    [
                        r["scene_id"],
                        r["lid"],
                        r["parent_lid"],
                        r["cls"],
                        r["gen_n"],
                    ]
                    for r in self._registry
                    if r["epoch"] == self.epoch
                ],
                key=lambda item: (
                    item[0],
                    item[1],
                    "" if item[2] is None else item[2],
                    item[3],
                    item[4],
                ),
            )
            reg_canon = json.dumps(
                reg_rows, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            reg_sha = hashlib.sha256(reg_canon).hexdigest()

            st = self._scene_state_locked(doc_id, create=False)
            scene_records = [
                r for r in self._registry
                if r["epoch"] == self.epoch and r["scene_id"] == doc_id
            ]
            if st is None:
                generation = None
                scene_obj = {
                    "doc_id": doc_id,
                    "gen_n": 0,
                    "n": len(scene_records),
                    "retained_n": 0,
                    "retained": [],
                    "pending": None,
                    "last": None,
                }
            else:
                generation = copy.deepcopy(st.generation)
                pending = self._pending_report_locked(doc_id, st)
                scene_obj = {
                    "doc_id": doc_id,
                    "gen_n": st.gen_n,
                    "n": len(scene_records),
                    "retained_n": st.retained_n,
                    "retained": list(st.retained[:8]),
                    "pending": pending,
                    "last": copy.deepcopy(st.last),
                }

            return {
                "epoch": self.epoch,
                "generation": generation,
                "registry_n": len(reg_rows),
                "registry_sha256": reg_sha,
                "scene": scene_obj,
            }

    def _validate_plan_locked(self, args: object) -> tuple[str | None, str | None]:
        """Valida etapas 1 y 2 de §3.3 sin efecto. Devuelve (error_reason, doc_id_valido)."""
        if not isinstance(args, dict):
            return "bad_plan", None
        doc_id = args.get("doc_id")
        if not isinstance(doc_id, str) or _DOC_ID_RE.match(doc_id) is None:
            return "bad_plan", None

        rev = args.get("rev")
        doc_hash = args.get("hash")
        plan_sha = args.get("plan_sha256")
        caps = args.get("caps")
        classes = args.get("classes")
        rows = args.get("rows")

        if not _is_int(rev) or rev < 0 or rev > _MAX_REV:
            return "bad_plan", doc_id
        if not _is_hex(doc_hash, 64) or not _is_hex(plan_sha, 64):
            return "bad_plan", doc_id

        # A6: falla cerrado, sin caps validos no hay presupuesto que respetar
        if not isinstance(caps, dict):
            return "budget_exceeded", doc_id
        for k in ("objeto", "infectado", "animal"):
            if k not in caps or not _is_int(caps[k]) or caps[k] < 0:
                return "budget_exceeded", doc_id
        if "total" in caps and caps["total"] is not None:
            if not _is_int(caps["total"]) or caps["total"] < 0:
                return "budget_exceeded", doc_id

        if not isinstance(classes, list):
            return "bad_plan", doc_id
        if any(not _is_ascii_text(c) for c in classes):
            return "bad_plan", doc_id
        if len(classes) != len(set(classes)):
            return "bad_plan", doc_id
        if list(classes) != sorted(classes):
            return "bad_plan", doc_id

        if not isinstance(rows, list):
            return "bad_plan", doc_id

        seen_lids: set[str] = set()
        counts = {"objeto": 0, "infectado": 0, "animal": 0}
        coords: list[tuple[float, float]] = []
        referenced_cis: set[int] = set()

        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) != 5:
                return "bad_plan", doc_id
            lid, ci, x, z, yaw = row
            if not _valid_lid(lid) or lid in seen_lids:
                return "bad_plan", doc_id
            seen_lids.add(lid)
            if not _is_int(ci) or ci < 0 or ci >= len(classes):
                return "bad_plan", doc_id
            if not (_is_num(x) and _is_num(z) and _is_num(yaw)):
                return "bad_plan", doc_id
            fx, fz, fyaw = float(x), float(z), float(yaw)
            if not (math.isfinite(fx) and math.isfinite(fz) and math.isfinite(fyaw)):
                return "bad_plan", doc_id
            if fyaw < 0.0 or fyaw >= 360.0:
                return "bad_plan", doc_id
            if not (_has_3_decimals(fx) and _has_3_decimals(fz) and _has_3_decimals(fyaw)):
                return "bad_plan", doc_id

            prefix = lid.split("-", 1)[0]
            counts[_PREFIX_KIND[prefix]] += 1
            coords.append((fx, fz))
            referenced_cis.add(ci)

        # M14: todas las clases de `classes` tienen que usarse
        if rows and len(referenced_cis) != len(classes):
            return "bad_plan", doc_id

        # Etapa 1b: cada clase existe en el mundo
        for ci in referenced_cis:
            if classes[ci] not in self._known_classes:
                return "unknown_class", doc_id
        for cls_name in classes:
            if cls_name not in self._known_classes:
                return "unknown_class", doc_id

        # Etapa 1c: coordenadas en [0, world_size]
        limit = float(self.world_size)
        for fx, fz in coords:
            if fx < 0.0 or fx > limit or fz < 0.0 or fz > limit:
                return "out_of_map", doc_id

        # Etapa 2: reservar presupuesto
        for kind in ("objeto", "infectado", "animal"):
            if counts[kind] > caps[kind]:
                return "budget_exceeded", doc_id
        if "total" in caps and caps["total"] is not None:
            if len(rows) > caps["total"]:
                return "budget_exceeded", doc_id

        return None, doc_id

    def apply(self, order: dict, check=None, tick=None) -> tuple[str, str | None, dict]:
        """Verbo scene.apply (§3.3 y aclaraciones M1-M19)."""
        if not isinstance(order, dict):
            return "rejected", "bad_plan", {}
        session = order.get("session")
        op_id = order.get("op_id")
        verb = order.get("verb")
        if not isinstance(session, str) or not session or not isinstance(op_id, str) or not op_id:
            return "rejected", "bad_plan", {}
        if verb is not None and verb != "scene.apply":
            return "rejected", "unknown_verb", {}

        with self._lock:
            order_epoch = order.get("epoch")
            if order_epoch != self.epoch:
                return "rejected", "stale_epoch", {}

            args = order.get("args")
            err, doc_id = self._validate_plan_locked(args)
            if err is not None:
                return "rejected", err, (self.read(doc_id) if doc_id else {})
            assert doc_id is not None

            # Etapa 3: retencion previa sin efecto (D5, D7)
            deletable = self._scene_records_locked(doc_id)
            initial_retained = self._compute_retention_locked(deletable)
            if initial_retained:
                return "rejected", "foreign_content_retained", self.read(doc_id)

            rev = int(args["rev"])
            doc_hash = str(args["hash"])
            plan_sha = str(args["plan_sha256"])
            classes = list(args["classes"])
            rows = [list(r) for r in args["rows"]]

        ctx = _OpCtx()

        # Etapa 4: resetear lo borrable de la escena en dos pasadas. El apply para
        # en cuanto encuentra retencion (D7, §3.3 paso 4).
        had_effect, stage4_retained, parada = self._delete_deletable(
            session=session,
            op_id=op_id,
            doc_id=doc_id,
            order_epoch=str(order_epoch),
            ctx=ctx,
            initial_retained_ids=set(),
            stop_on_retention=True,
            clear_gen_on_first_delete=True,
            check=check,
            tick=tick,
        )

        with self._lock:
            # M3: antes de escribir estado (last, retained, pending), si el mundo
            # reinicio durante un tick, parar sin escribir nada en el mundo nuevo.
            if self.epoch != order_epoch:
                return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)
            scene_now = self._scene_records_locked(doc_id)
            retained_recs = [r for r in scene_now if id(r) in stage4_retained]
            if parada == "stale_epoch":
                return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)
            if parada == "delete_failed":
                if not had_effect:
                    return "rejected", "delete_failed", self.read(doc_id)
                st = self._scene_state_locked(doc_id, create=True)
                self._set_retention_locked(st, retained_recs)
                self._prune_pending_locked(doc_id)
                st.last = {
                    "session": session,
                    "op_id": op_id,
                    "verb": "scene.apply",
                    "outcome": "interrupted",
                }
                return "error", "delete_failed", self.read(doc_id)
            if parada is not None and parada != "retention_stop":
                if not had_effect:
                    return "rejected", parada, self.read(doc_id)
                st = self._scene_state_locked(doc_id, create=True)
                self._set_retention_locked(st, retained_recs)
                self._prune_pending_locked(doc_id)
                st.last = {
                    "session": session,
                    "op_id": op_id,
                    "verb": "scene.apply",
                    "outcome": "interrupted",
                }
                return "error", parada, self.read(doc_id)

            if parada == "retention_stop":
                if not had_effect:
                    return "rejected", "foreign_content_retained", self.read(doc_id)
                st = self._scene_state_locked(doc_id, create=True)
                self._set_retention_locked(st, retained_recs)
                self._prune_pending_locked(doc_id)
                st.last = {
                    "session": session,
                    "op_id": op_id,
                    "verb": "scene.apply",
                    "outcome": "retained",
                }
                return "error", "foreign_content_retained", self.read(doc_id)

            # M9: antes de crear se vuelve a leer lo borrable de la escena; si queda
            # algo (p. ej. un hijo propio anadido durante el reset), no se crea.
            leftovers = self._scene_records_locked(doc_id)
            if leftovers:
                if not had_effect:
                    return "rejected", "foreign_content_retained", self.read(doc_id)
                st = self._scene_state_locked(doc_id, create=True)
                self._set_retention_locked(st, leftovers)
                self._prune_pending_locked(doc_id)
                st.last = {
                    "session": session,
                    "op_id": op_id,
                    "verb": "scene.apply",
                    "outcome": "retained",
                }
                return "error", "foreign_content_retained", self.read(doc_id)

            st = self._scene_state_locked(doc_id, create=True)
            target_gen_n = st.gen_n + 1

        # Si el plan tiene 0 filas y no hubo borrados, comprobar lease/plazo antes de publicar
        if not rows and not had_effect and check is not None:
            fail = check()
            with self._lock:
                if self.epoch != order_epoch:
                    return "rejected", "stale_epoch", self.read(doc_id)
            if fail is not None:
                return "rejected", fail, self.read(doc_id)

        # Etapa 5: crear por lotes de batch por tick
        checkpoint_rows: list[list] = []

        for idx, (lid, ci, x, z, yaw) in enumerate(rows):
            if check is not None:
                fail = check()
                if fail is not None:
                    with self._lock:
                        # M3: antes de escribir `last`, si el mundo reinicio, parar.
                        if self.epoch != order_epoch:
                            return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)
                        if not had_effect:
                            return "rejected", fail, self.read(doc_id)
                        st = self._scene_state_locked(doc_id, create=True)
                        st.last = {
                            "session": session,
                            "op_id": op_id,
                            "verb": "scene.apply",
                            "outcome": "interrupted",
                        }
                        return "error", fail, self.read(doc_id)

            create_failed_now = False
            do_batch_tick = False
            hit_barrier = False
            with self._lock:
                # M3: antes de cada efecto, con el cerrojo, si el mundo reinicio
                if self.epoch != order_epoch:
                    return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)
                fx, fz, fyaw = float(x), float(z), float(yaw)
                gy = float(self.ground_y(fx, fz))
                if (
                    self._hook_hit(self._fail_create, doc_id, lid)
                    or not math.isfinite(gy)
                    or gy < -_MAX_Y
                    or gy > _MAX_Y
                ):
                    create_failed_now = True
                else:
                    st = self._scene_state_locked(doc_id, create=True)
                    if (session, op_id) not in st.pending_orders:
                        st.pending_orders.append((session, op_id))
                    cls_name = classes[ci]
                    prefix = lid.split("-", 1)[0]
                    is_creature = prefix in ("zmb", "ani")
                    flags = FLAGS_CREATURE if is_creature else FLAGS_ROOT

                    sx, sy, sz = fx, gy, fz
                    disp = self._displace_on_create.get((doc_id, lid))
                    if disp is None:
                        disp = self._displace_on_create.get(lid)
                    if disp is not None:
                        if isinstance(disp, (list, tuple)):
                            if len(disp) == 2:
                                sx += float(disp[0])
                                sz += float(disp[1])
                            elif len(disp) >= 3:
                                sx += float(disp[0])
                                sy += float(disp[1])
                                sz += float(disp[2])
                        elif _is_num(disp):
                            sx += float(disp)

                    eid = self._alloc_eid_locked()
                    ent = _Entity(
                        eid,
                        cls_name,
                        sx,
                        sy,
                        sz,
                        fyaw,
                        hp=1.0,
                        flags=flags,
                        origin="sandbox",
                        scene=doc_id,
                        is_creature=is_creature,
                        ai_active=False,
                    )
                    self._entities[eid] = ent
                    st.generation = None
                    st.checkpoint = []
                    self._registry.append({
                        "epoch": self.epoch,
                        "scene_id": doc_id,
                        "gen_n": target_gen_n,
                        "op": {"session": session, "op_id": op_id},
                        "lid": lid,
                        "parent_lid": None,
                        "cls": cls_name,
                        "gy": gy,
                        "eid": eid,
                    })
                    self._record_effect_locked(session, op_id, "created")
                    had_effect = True

                    if self._hook_hit(self._suppress_create, doc_id, lid):
                        ent.alive = False

                    # D9: checkpoint en el mismo tick de la creacion, antes de soltar la IA
                    if not ent.alive:
                        checkpoint_rows.append([lid, -1, None, None, None, None, _r3(gy)])
                    else:
                        ci_read = classes.index(ent.cls) if ent.cls in classes else -1
                        checkpoint_rows.append([
                            lid,
                            ci_read,
                            _r3(ent.x),
                            _r3(ent.y),
                            _r3(ent.z),
                            _r_yaw(ent.yaw),
                            _r3(gy),
                        ])
                        if is_creature:
                            ent.ai_active = True
                            # §5: al soltar la IA ya cambia de pose
                            self._drift_one_locked(ent)

                    ctx.effects += 1
                    ctx.in_batch += 1
                    if ctx.in_batch >= self.batch or idx == len(rows) - 1:
                        ctx.in_batch = 0
                        do_batch_tick = True
                    hit_barrier = self._barrier_hit_locked(ctx)

            if create_failed_now:
                return self._compensate_failed_apply(
                    session=session,
                    op_id=op_id,
                    doc_id=doc_id,
                    order_epoch=str(order_epoch),
                    had_effect=had_effect,
                    ctx=ctx,
                    check=check,
                    tick=tick,
                )

            if hit_barrier:
                self._barrier_wait()
            if do_batch_tick:
                self._do_tick(tick)

        # Etapa 6: publicar
        with self._lock:
            # M3: antes de publicar generation/last/pending/retained, si el mundo
            # reinicio en el ultimo tick, parar sin escribir nada.
            if self.epoch != order_epoch:
                return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)
            st = self._scene_state_locked(doc_id, create=True)
            st.gen_n = target_gen_n
            st.generation = {
                "session": session,
                "op_id": op_id,
                "rev": rev,
                "hash": doc_hash,
                "plan_sha256": plan_sha,
            }
            if (session, op_id) in st.pending_orders:
                st.pending_orders.remove((session, op_id))
            self._prune_pending_locked(doc_id)
            self._set_retention_locked(st, [])
            st.checkpoint = copy.deepcopy(checkpoint_rows)
            st.last = {
                "session": session,
                "op_id": op_id,
                "verb": "scene.apply",
                "outcome": "done",
            }
            read_out = self.read(doc_id)
            read_out["obs"] = {
                "at": "checkpoint",
                "rows": copy.deepcopy(checkpoint_rows),
            }
            return "done", None, read_out

    def _compensate_failed_apply(
        self,
        *,
        session: str,
        op_id: str,
        doc_id: str,
        order_epoch: str,
        had_effect: bool,
        ctx: "_OpCtx",
        check,
        tick,
    ) -> tuple[str, str, dict]:
        """Compensa en la misma orden los registros creados por ella (D8, §3.3, M7, M10)."""
        with self._lock:
            op_records = self._op_records_locked(doc_id, session, op_id)
            initial_retained = self._compute_retention_locked(op_records)

        # M12: una creacion que falla antes de ningun efecto -> rejected/create_failed
        if not op_records and not had_effect:
            return "rejected", "create_failed", self.read(doc_id)

        _had, comp_retained, parada = self._delete_deletable(
            session=session,
            op_id=op_id,
            doc_id=doc_id,
            order_epoch=order_epoch,
            ctx=ctx,
            initial_retained_ids=initial_retained,
            stop_on_retention=False,
            clear_gen_on_first_delete=False,
            check=check,
            tick=tick,
            # D8 y §3.4 paso 2: la compensacion borra solo los registros de su orden.
            op_scope=(session, op_id),
        )

        with self._lock:
            # M3: antes de escribir last/retention/pending, si el mundo reinicio
            # durante la compensacion, parar sin escribir nada en el mundo nuevo.
            if self.epoch != order_epoch:
                return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)
            st = self._scene_state_locked(doc_id, create=True)
            rem_op = self._op_records_locked(doc_id, session, op_id)
            retained_lids = [r["lid"] for r in rem_op if id(r) in comp_retained]
            self._set_retention_locked(
                st, [r for r in rem_op if id(r) in comp_retained]
            )
            self._prune_pending_locked(doc_id)

            if parada == "stale_epoch":
                return "error", "stale_epoch", self.read(doc_id)
            if parada is not None:
                st.last = {
                    "session": session,
                    "op_id": op_id,
                    "verb": "scene.apply",
                    "outcome": "interrupted",
                }
                # M7: la compensacion dentro de la orden mantiene create_failed
                return "error", "create_failed", self.read(doc_id)

            outcome = "retained" if retained_lids else "compensated"
            st.last = {
                "session": session,
                "op_id": op_id,
                "verb": "scene.apply",
                "outcome": outcome,
            }
            return "error", "create_failed", self.read(doc_id)

    def reset(self, order: dict, check=None, tick=None) -> tuple[str, str | None, dict]:
        """Verbo scene.reset (§3.4 y aclaraciones M1-M19)."""
        if not isinstance(order, dict):
            return "rejected", "bad_args", {}
        session = order.get("session")
        op_id = order.get("op_id")
        verb = order.get("verb")
        if not isinstance(session, str) or not session or not isinstance(op_id, str) or not op_id:
            return "rejected", "bad_args", {}
        if verb is not None and verb != "scene.reset":
            return "rejected", "unknown_verb", {}

        with self._lock:
            order_epoch = order.get("epoch")
            if order_epoch != self.epoch:
                return "rejected", "stale_epoch", {}

            args = order.get("args")
            if not isinstance(args, dict):
                return "rejected", "bad_args", {}
            doc_id = args.get("doc_id")
            if not isinstance(doc_id, str) or _DOC_ID_RE.match(doc_id) is None:
                return "rejected", "bad_args", {}

            has_if_pending = "if_pending" in args
            target_pending: tuple[str, str] | None = None
            if has_if_pending:
                # M13: si viene `if_pending` tiene que ser {session, op_id} valido
                ip = args["if_pending"]
                if (
                    not isinstance(ip, dict)
                    or not isinstance(ip.get("session"), str)
                    or not ip.get("session")
                    or not isinstance(ip.get("op_id"), str)
                    or not ip.get("op_id")
                ):
                    return "rejected", "bad_args", self.read(doc_id)
                target_pending = (ip["session"], ip["op_id"])

                # Paso 1 (§3.4): comprobar que scene.pending coincide
                st_cur = self._scene_state_locked(doc_id, create=False)
                cur_pending_n = len(
                    self._op_records_locked(doc_id, target_pending[0], target_pending[1])
                )
                if (
                    st_cur is None
                    or target_pending not in st_cur.pending_orders
                    or cur_pending_n == 0
                ):
                    return "rejected", "not_pending", self.read(doc_id)

                deletable = self._op_records_locked(
                    doc_id, target_pending[0], target_pending[1]
                )
            else:
                deletable = self._scene_records_locked(doc_id)

            initial_retained = self._compute_retention_locked(deletable)
            non_retained_any = any(id(r) not in initial_retained for r in deletable)

        if not non_retained_any and check is not None:
            fail = check()
            with self._lock:
                if self.epoch != order_epoch:
                    return "rejected", "stale_epoch", self.read(doc_id)
            if fail is not None:
                return "rejected", fail, self.read(doc_id)

        ctx = _OpCtx()
        had_effect, final_retained, parada = self._delete_deletable(
            session=session,
            op_id=op_id,
            doc_id=doc_id,
            order_epoch=str(order_epoch),
            ctx=ctx,
            initial_retained_ids=initial_retained,
            stop_on_retention=False,
            clear_gen_on_first_delete=(not has_if_pending),
            check=check,
            tick=tick,
            # §3.4 paso 2: con `if_pending` la compensacion borra solo los registros
            # de esa orden; el reset normal (`None`) borra toda la escena.
            op_scope=target_pending if has_if_pending else None,
        )

        with self._lock:
            # M3: antes de escribir estado, si el mundo reinicio durante un tick,
            # parar sin escribir nada en el mundo nuevo.
            if self.epoch != order_epoch:
                return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)
            scene_now = self._scene_records_locked(doc_id)
            retained_recs = [r for r in scene_now if id(r) in final_retained]
            retained_lids = [r["lid"] for r in retained_recs]

            if parada == "stale_epoch":
                return ("error" if had_effect else "rejected"), "stale_epoch", self.read(doc_id)

            if parada is not None:
                if not had_effect:
                    return "rejected", parada, self.read(doc_id)
                st = self._scene_state_locked(doc_id, create=True)
                self._set_retention_locked(st, retained_recs)
                self._prune_pending_locked(doc_id)
                if has_if_pending:
                    assert target_pending is not None
                    # M5: una compensacion if_pending interrumpida deja last del apply
                    st.last = {
                        "session": target_pending[0],
                        "op_id": target_pending[1],
                        "verb": "scene.apply",
                        "outcome": "interrupted",
                    }
                else:
                    st.last = {
                        "session": session,
                        "op_id": op_id,
                        "verb": "scene.reset",
                        "outcome": "interrupted",
                    }
                return "error", parada, self.read(doc_id)

            st = self._scene_state_locked(doc_id, create=True)
            self._set_retention_locked(st, retained_recs)

            if not has_if_pending:
                st.generation = None
                st.checkpoint = []
                st.pending_orders = []
                outcome = "retained" if retained_lids else "done"
                st.last = {
                    "session": session,
                    "op_id": op_id,
                    "verb": "scene.reset",
                    "outcome": outcome,
                }
            else:
                assert target_pending is not None
                self._prune_pending_locked(doc_id)
                outcome = "retained" if retained_lids else "compensated"
                st.last = {
                    "session": target_pending[0],
                    "op_id": target_pending[1],
                    "verb": "scene.apply",
                    "outcome": outcome,
                }

            return "done", None, self.read(doc_id)

    def observe(self, order: dict) -> tuple[str, str | None, dict]:
        """Verbo scene.observe (§3.5 y §3.6)."""
        if not isinstance(order, dict):
            return "rejected", "bad_args", {}
        session = order.get("session")
        op_id = order.get("op_id")
        verb = order.get("verb")
        if not isinstance(session, str) or not session or not isinstance(op_id, str) or not op_id:
            return "rejected", "bad_args", {}
        if verb is not None and verb != "scene.observe":
            return "rejected", "unknown_verb", {}

        with self._lock:
            if order.get("epoch") != self.epoch:
                return "rejected", "stale_epoch", {}

            args = order.get("args")
            if not isinstance(args, dict):
                return "rejected", "bad_args", {}
            doc_id = args.get("doc_id")
            at = args.get("at")
            if not isinstance(doc_id, str) or _DOC_ID_RE.match(doc_id) is None or at not in ("checkpoint", "now"):
                return "rejected", "bad_args", {}

            st = self._scene_state_locked(doc_id, create=False)
            if at == "checkpoint":
                if st is not None and st.generation is not None:
                    obs_rows = copy.deepcopy(st.checkpoint)
                else:
                    obs_rows = []
            else:
                scene_eids = {
                    r["eid"]
                    for r in self._registry
                    if r["epoch"] == self.epoch and r["scene_id"] == doc_id
                }
                obs_rows = []
                for rec in self._registry:
                    if (
                        rec["epoch"] != self.epoch
                        or rec["scene_id"] != doc_id
                        or rec["parent_lid"] is not None
                    ):
                        continue
                    ent = self._entities.get(rec["eid"])
                    if ent is None or not ent.alive:
                        # M15: raiz muerta -> nulos en x, y, z, yaw y hp; contadores a 0
                        obs_rows.append([rec["lid"], None, None, None, None, None, 0, 0])
                        continue
                    n_own = 0
                    n_foreign = 0
                    for desc in self._inventory_descendants_locked(ent.eid):
                        if desc.eid in scene_eids:
                            n_own += 1
                        else:
                            n_foreign += 1
                    hp = _r3(max(0.0, min(1.0, ent.hp)))
                    obs_rows.append([
                        rec["lid"],
                        _r3(ent.x),
                        _r3(ent.y),
                        _r3(ent.z),
                        _r_yaw(ent.yaw),
                        hp,
                        n_own,
                        n_foreign,
                    ])

            read_out = self.read(doc_id)
            read_out["obs"] = {"at": at, "rows": obs_rows}

            envelope = {
                "op_id": op_id,
                "session": session,
                "epoch": self.epoch,
                "status": "done",
                "reason": None,
                "dup": False,
                "read": read_out,
            }
            raw_ascii = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
            raw_utf8 = json.dumps(
                envelope, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            if len(raw_ascii) > WIRE_CAP or len(raw_utf8) > WIRE_CAP:
                return "rejected", "result_too_large", {}

            return "done", None, read_out

    # -- censo independiente y contadores de prueba --------------------------

    def census(self) -> list[dict]:
        """Devuelve todas las entidades vivas del mundo sin consultar el registro (§5)."""
        with self._lock:
            out: list[dict] = []
            for ent in self._entities.values():
                if not ent.alive:
                    continue
                out.append({
                    "eid": ent.eid,
                    "cls": ent.cls,
                    "pos": [ent.x, ent.y, ent.z],
                    "x": ent.x,
                    "y": ent.y,
                    "z": ent.z,
                    "yaw": ent.yaw,
                    "hp": ent.hp,
                    "parent": ent.parent_eid,
                    "slot": ent.slot,
                    "flags": ent.flags,
                    "origin": ent.origin,
                    "scene": ent.scene,
                })
            return out

    def effects(self, session: str, op_id: str) -> dict[str, int]:
        """Devuelve {"created": n, "deleted": n} para (session, op_id)."""
        with self._lock:
            counts = self._effects.get((session, op_id))
            if counts is None:
                return {"created": 0, "deleted": 0}
            return {"created": counts["created"], "deleted": counts["deleted"]}

    def registry_snapshot(self) -> list[dict]:
        """Registro entero sin filtrar por epoch, para las pruebas (M4)."""
        with self._lock:
            return copy.deepcopy(self._registry)

    # -- ganchos de prueba (§5) ----------------------------------------------

    def spawn_foreign(
        self,
        cls: str,
        x: float,
        z: float,
        yaw: float,
        inside=None,
        *,
        persistent: bool = False,
        slot: str = "cargo",
    ) -> str:
        """Crea una entidad ajena (o persistent) en el suelo o dentro de un contenedor."""
        with self._lock:
            fx, fz, fyaw = float(x), float(z), float(yaw)
            parent_ent: _Entity | None = None
            if inside is not None:
                parent_ent = self._resolve_live_entity_locked(inside)
                if not has_inventory(parent_ent.cls):
                    raise ValueError(f"la clase {parent_ent.cls!r} no tiene inventario")
                fy = parent_ent.y
            else:
                fy = float(self.ground_y(fx, fz))

            origin = "persistent" if persistent else "foreign"
            flags = 0 if persistent else ECE_NOPERSISTENCY_WORLD
            eid = self._alloc_eid_locked()
            ent = _Entity(
                eid,
                cls,
                fx,
                fy,
                fz,
                fyaw,
                hp=1.0,
                flags=flags,
                origin=origin,
                scene=None,
                is_creature=False,
                ai_active=False,
            )
            self._entities[eid] = ent
            if parent_ent is not None:
                self._attach_to_parent_locked(ent, parent_ent, slot)
            return eid

    def spawn_persistent(
        self,
        cls: str,
        x: float,
        z: float,
        yaw: float,
        inside=None,
        *,
        slot: str = "cargo",
    ) -> str:
        """Atajo para crear un objeto ajeno persistente que sobrevive a restart()."""
        return self.spawn_foreign(
            cls, x, z, yaw, inside=inside, persistent=True, slot=slot
        )

    def spawn_own_child(
        self,
        doc_id: str,
        parent_lid: str,
        cls: str,
        lid: str,
        *,
        slot: str = "cargo",
        inside=None,
    ) -> str:
        """Crea un hijo propio registrado en doc_id bajo parent_lid (como F3)."""
        with self._lock:
            parent_rec = None
            for rec in self._registry:
                if (
                    rec["epoch"] == self.epoch
                    and rec["scene_id"] == doc_id
                    and rec["lid"] == parent_lid
                ):
                    parent_rec = rec
                    break
            if parent_rec is None:
                raise ValueError(f"padre registrado no encontrado: {(doc_id, parent_lid)!r}")
            if any(
                r["epoch"] == self.epoch and r["scene_id"] == doc_id and r["lid"] == lid
                for r in self._registry
            ):
                raise ValueError(f"lid ya registrado en {doc_id!r}: {lid!r}")

            parent_ent = self._entities.get(parent_rec["eid"])
            if parent_ent is None or not parent_ent.alive:
                raise ValueError("la entidad padre no vive")

            container_ent = (
                self._resolve_live_entity_locked(inside)
                if inside is not None
                else parent_ent
            )
            if not has_inventory(container_ent.cls):
                raise ValueError(f"la clase {container_ent.cls!r} no tiene inventario")

            eid = self._alloc_eid_locked()
            ent = _Entity(
                eid,
                cls,
                container_ent.x,
                container_ent.y,
                container_ent.z,
                container_ent.yaw,
                hp=1.0,
                flags=FLAGS_CHILD,
                origin="sandbox",
                scene=doc_id,
                is_creature=False,
                ai_active=False,
            )
            self._entities[eid] = ent
            self._attach_to_parent_locked(ent, container_ent, slot)
            self._registry.append({
                "epoch": self.epoch,
                "scene_id": doc_id,
                "gen_n": parent_rec["gen_n"],
                "op": copy.deepcopy(parent_rec["op"]),
                "lid": lid,
                "parent_lid": parent_lid,
                "cls": cls,
                "gy": parent_rec["gy"],
                "eid": eid,
            })
            return eid

    def move_to_ground(self, eid_or_ref) -> None:
        """Suelta una entidad al suelo sin alterar su registro."""
        with self._lock:
            ent = self._resolve_live_entity_locked(eid_or_ref)
            self._detach_from_parent_locked(ent)
            ent.y = float(self.ground_y(ent.x, ent.z))

    def move_inside(self, eid_or_ref, inside, *, slot: str = "cargo") -> None:
        """Mueve una entidad dentro de otro contenedor sin alterar su registro."""
        with self._lock:
            ent = self._resolve_live_entity_locked(eid_or_ref)
            parent_ent = self._resolve_live_entity_locked(inside)
            self._attach_to_parent_locked(ent, parent_ent, slot)

    def move_entity(
        self,
        target,
        x: float | None = None,
        z: float | None = None,
        *,
        dx: float = 0.0,
        dz: float = 0.0,
        dy: float | None = None,
        yaw: float | None = None,
    ) -> None:
        """Desplaza o reorienta una entidad viva (p. ej. para F2-O)."""
        with self._lock:
            ent = self._resolve_live_entity_locked(target)
            ent.x = float(x) if x is not None else ent.x + float(dx)
            ent.z = float(z) if z is not None else ent.z + float(dz)
            if dy is not None:
                ent.y = ent.y + float(dy)
            elif ent.parent_eid is None:
                ent.y = float(self.ground_y(ent.x, ent.z))
            if yaw is not None:
                ent.yaw = float(yaw)

    def seed_scene(
        self,
        doc_id: str,
        rows,
        *,
        classes: list[str] | None = None,
    ) -> dict:
        """Registra y materializa otra escena con el mismo algoritmo de apply (§5)."""
        with self._lock:
            self._seed_seq += 1
            seed_op_id = f"seed-{self._seed_seq}"
            seed_session = "0" * 16

            if isinstance(rows, dict):
                if "entities" in rows:
                    doc_copy = copy.deepcopy(rows)
                    doc_copy["doc_id"] = doc_id
                    plan_args = build_plan(
                        doc_copy,
                        caps={"objeto": 10000, "infectado": 10000, "animal": 10000},
                    )
                elif "rows" in rows and "classes" in rows:
                    cls_list = list(rows["classes"])
                    row_list = [list(r) for r in rows["rows"]]
                    rev_val = int(rows.get("rev", 1))
                    h = rows.get("hash") or _canon_sha256({"seed": doc_id, "rows": row_list})
                    p_sha = rows.get("plan_sha256") or compute_plan_sha256(
                        doc_id, rev_val, h, cls_list, row_list
                    )
                    plan_args = {
                        "doc_id": doc_id,
                        "rev": rev_val,
                        "hash": h,
                        "plan_sha256": p_sha,
                        "caps": {"objeto": 10000, "infectado": 10000, "animal": 10000},
                        "classes": cls_list,
                        "rows": row_list,
                    }
                else:
                    raise ValueError("diccionario de seed_scene invalido")
            elif isinstance(rows, list):
                if not rows:
                    cls_list = list(classes) if classes is not None else []
                    row_list = []
                elif isinstance(rows[0], dict):
                    non_act = [e for e in rows if e.get("kind") != "actor"]
                    cls_list = sorted({e["cls"] for e in non_act})
                    ci_map = {c: i for i, c in enumerate(cls_list)}
                    row_list = [
                        [
                            e.get("id") or e["lid"],
                            ci_map[e["cls"]],
                            _r3(e["x"]),
                            _r3(e["z"]),
                            _r_yaw(e.get("yaw", 0.0)),
                        ]
                        for e in non_act
                    ]
                elif isinstance(rows[0], (list, tuple)) and len(rows[0]) in (4, 5):
                    if isinstance(rows[0][1], str):
                        cls_list = sorted({str(r[1]) for r in rows})
                        ci_map = {c: i for i, c in enumerate(cls_list)}
                        row_list = [
                            [
                                str(r[0]),
                                ci_map[str(r[1])],
                                _r3(r[2]),
                                _r3(r[3]),
                                _r_yaw(r[4] if len(r) == 5 else 0.0),
                            ]
                            for r in rows
                        ]
                    else:
                        cls_list = (
                            list(classes)
                            if classes is not None
                            else sorted(self._known_classes)
                        )
                        row_list = [
                            [
                                str(r[0]),
                                int(r[1]),
                                _r3(r[2]),
                                _r3(r[3]),
                                _r_yaw(r[4] if len(r) == 5 else 0.0),
                            ]
                            for r in rows
                        ]
                else:
                    raise ValueError("formato de filas de seed_scene invalido")

                h = _canon_sha256({"seed": doc_id, "rows": row_list})
                plan_args = {
                    "doc_id": doc_id,
                    "rev": 1,
                    "hash": h,
                    "plan_sha256": compute_plan_sha256(doc_id, 1, h, cls_list, row_list),
                    "caps": {"objeto": 10000, "infectado": 10000, "animal": 10000},
                    "classes": cls_list,
                    "rows": row_list,
                }
            else:
                raise ValueError("rows debe ser lista o diccionario")

            # M16: seed_scene nunca amplia el catalogo; una clase desconocida es error
            err, _ = self._validate_plan_locked(plan_args)
            if err is not None:
                raise ValueError(f"seed_scene invalido: {err}")

            deletable = [
                r for r in self._registry
                if r["epoch"] == self.epoch and r["scene_id"] == doc_id
            ]
            if self._compute_retention_locked(deletable):
                raise RuntimeError("seed_scene rechazado: foreign_content_retained")

            pass1 = [r for r in deletable if r["parent_lid"] is not None]
            pass1.sort(key=lambda r: -self._hierarchy_depth_locked(r["eid"]))
            pass2 = [r for r in deletable if r["parent_lid"] is None]
            for rec in pass1 + pass2:
                ent_old = self._entities.get(rec["eid"])
                if ent_old is not None and ent_old.alive:
                    self._detach_from_parent_locked(ent_old)
                    ent_old.alive = False
                    ent_old.ai_active = False
                if rec in self._registry:
                    self._registry.remove(rec)

            st = self._scene_state_locked(doc_id, create=True)
            target_gen_n = st.gen_n + 1
            cls_plan = list(plan_args["classes"])
            checkpoint_rows: list[list] = []

            for lid, ci, x, z, yaw in plan_args["rows"]:
                cls_name = cls_plan[ci]
                fx, fz, fyaw = float(x), float(z), float(yaw)
                gy = float(self.ground_y(fx, fz))
                prefix = lid.split("-", 1)[0]
                is_creature = prefix in ("zmb", "ani")
                flags = FLAGS_CREATURE if is_creature else FLAGS_ROOT

                eid = self._alloc_eid_locked()
                ent = _Entity(
                    eid,
                    cls_name,
                    fx,
                    gy,
                    fz,
                    fyaw,
                    hp=1.0,
                    flags=flags,
                    origin="sandbox",
                    scene=doc_id,
                    is_creature=is_creature,
                    ai_active=False,
                )
                self._entities[eid] = ent
                self._registry.append({
                    "epoch": self.epoch,
                    "scene_id": doc_id,
                    "gen_n": target_gen_n,
                    "op": {"session": seed_session, "op_id": seed_op_id},
                    "lid": lid,
                    "parent_lid": None,
                    "cls": cls_name,
                    "gy": gy,
                    "eid": eid,
                })
                checkpoint_rows.append([
                    lid,
                    ci,
                    _r3(ent.x),
                    _r3(ent.y),
                    _r3(ent.z),
                    _r_yaw(ent.yaw),
                    _r3(gy),
                ])
                if is_creature:
                    ent.ai_active = True

            st.gen_n = target_gen_n
            st.generation = {
                "session": seed_session,
                "op_id": seed_op_id,
                "rev": int(plan_args["rev"]),
                "hash": str(plan_args["hash"]),
                "plan_sha256": str(plan_args["plan_sha256"]),
            }
            st.pending_orders = []
            st.retained_n = 0
            st.retained = []
            st.retained_rec_ids = set()
            st.checkpoint = checkpoint_rows
            st.last = {
                "session": seed_session,
                "op_id": seed_op_id,
                "verb": "scene.apply",
                "outcome": "done",
            }
            read_out = self.read(doc_id)
            read_out["obs"] = {
                "at": "checkpoint",
                "rows": copy.deepcopy(checkpoint_rows),
            }
            return read_out

    @staticmethod
    def _hook_key(lid: str, doc_id: str | None):
        return (doc_id, lid) if doc_id is not None else lid

    def fail_create(self, lid: str, enabled: bool = True, *, doc_id: str | None = None) -> None:
        key = self._hook_key(lid, doc_id)
        with self._lock:
            if enabled:
                self._fail_create.add(key)
            else:
                self._fail_create.discard(key)

    def suppress_create(self, lid: str, enabled: bool = True, *, doc_id: str | None = None) -> None:
        key = self._hook_key(lid, doc_id)
        with self._lock:
            if enabled:
                self._suppress_create.add(key)
            else:
                self._suppress_create.discard(key)

    def displace_on_create(self, lid: str, d, *, doc_id: str | None = None) -> None:
        key = self._hook_key(lid, doc_id)
        with self._lock:
            if d is None or d == 0:
                self._displace_on_create.pop(key, None)
            else:
                self._displace_on_create[key] = d

    def fail_delete(self, lid: str, enabled: bool = True, *, doc_id: str | None = None) -> None:
        key = self._hook_key(lid, doc_id)
        with self._lock:
            if enabled:
                self._fail_delete.add(key)
            else:
                self._fail_delete.discard(key)

    def spawn_orphan_sandbox(
        self, cls: str, x: float, z: float, yaw: float = 0.0
    ) -> str:
        """Entidad de origen Sandbox que NO esta en el registro (M18).

        El mod decide lo propio por el registro, no por `origin`, asi que nunca la toca.
        """
        with self._lock:
            fx, fz, fyaw = float(x), float(z), float(yaw)
            fy = float(self.ground_y(fx, fz))
            eid = self._alloc_eid_locked()
            ent = _Entity(
                eid,
                cls,
                fx,
                fy,
                fz,
                fyaw,
                hp=1.0,
                flags=FLAGS_ROOT,
                origin="sandbox",
                scene=None,
                is_creature=False,
                ai_active=False,
            )
            self._entities[eid] = ent
            return eid

    def seed_record(
        self,
        doc_id: str,
        lid: str,
        cls: str,
        x: float,
        z: float,
        session: str,
        op_id: str,
    ) -> str:
        """Gancho SOLO para pruebas: registra una entidad viva con otra `(session, op_id)`.

        Siembra en `doc_id` un registro de una orden ajena para comprobar que las
        compensaciones (D8, §3.4 paso 2) no borran lo que no es de su orden.
        """
        with self._lock:
            if not isinstance(doc_id, str) or _DOC_ID_RE.match(doc_id) is None:
                raise ValueError("doc_id invalido")
            if not _valid_lid(lid):
                raise ValueError("lid invalido")
            if not isinstance(session, str) or not session:
                raise ValueError("session invalida")
            if not isinstance(op_id, str) or not op_id:
                raise ValueError("op_id invalido")
            fx, fz = float(x), float(z)
            gy = float(self.ground_y(fx, fz))
            eid = self._alloc_eid_locked()
            ent = _Entity(
                eid,
                cls,
                fx,
                gy,
                fz,
                0.0,
                hp=1.0,
                flags=FLAGS_ROOT,
                origin="sandbox",
                scene=doc_id,
                is_creature=False,
                ai_active=False,
            )
            self._entities[eid] = ent
            self._registry.append({
                "epoch": self.epoch,
                "scene_id": doc_id,
                "gen_n": 1,
                "op": {"session": session, "op_id": op_id},
                "lid": lid,
                "parent_lid": None,
                "cls": cls,
                "gy": gy,
                "eid": eid,
            })
            return eid

    def barrier_after(self, n: int) -> None:
        """Tras el efecto n.º `n` de la orden siguiente, espera fuera del cerrojo (M8)."""
        with self._lock:
            self._barrier_n = int(n)
            self._barrier_reached = threading.Event()
            self._barrier_release = threading.Event()

    def release_barrier(self) -> None:
        with self._lock:
            release = self._barrier_release
        if release is not None:
            release.set()

    def wait_barrier_reached(self, timeout: float = 5.0) -> bool:
        with self._lock:
            reached = self._barrier_reached
        if reached is None:
            return True
        return reached.wait(timeout)

    def clear_faults(self) -> None:
        with self._lock:
            self._fail_create.clear()
            self._suppress_create.clear()
            self._displace_on_create.clear()
            self._fail_delete.clear()

    def restart(self, epoch: str | None = None) -> str:
        """Reinicia la mision: nuevo epoch, registro vacio y desaparece ECE_NOPERSISTENCY_WORLD."""
        if epoch is not None and not _is_hex(epoch, 32):
            raise ValueError("epoch debe ser 32 hex")
        with self._lock:
            if epoch is not None:
                self.epoch = epoch.lower()
            else:
                old = self.epoch
                new_ep = secrets.token_hex(16)
                while new_ep == old:
                    new_ep = secrets.token_hex(16)
                self.epoch = new_ep

            self._registry.clear()
            self._scenes.clear()
            self.clear_faults()

            kept: dict[str, _Entity] = {}
            for eid, ent in self._entities.items():
                if not ent.alive:
                    continue
                if (ent.flags & ECE_NOPERSISTENCY_WORLD) != 0 and (
                    ent.flags & ECE_DYNAMIC_PERSISTENCY
                ) == 0:
                    continue
                if ent.origin == "persistent" or (ent.flags & ECE_DYNAMIC_PERSISTENCY) != 0:
                    kept[eid] = ent

            for ent in kept.values():
                ent.children_eids = [c for c in ent.children_eids if c in kept]
                if ent.parent_eid is not None and ent.parent_eid not in kept:
                    ent.parent_eid = None
                    ent.slot = None
                    ent.y = float(self.ground_y(ent.x, ent.z))

            self._entities = kept
            return self.epoch
