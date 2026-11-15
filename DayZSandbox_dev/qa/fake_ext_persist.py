"""Extension de S-persist para fake_peer (prefijo per_, RPC 26102800..26102809).

Modela un mundo minimo del servidor: registro de propiedad en memoria, entidades
propias creadas con ECE_NOPERSISTENCY_WORLD, objetos ajenos y un control persistente,
reseteo por escena con retencion de descendientes ajenos o de otra escena, censos por
disco con trabajo protegido (resource per_census, deadman stop) y reinicio de mundo que
solo conserva lo creado sin ECE_NOPERSISTENCY_WORLD.

Extensiones para F2 (PR "sonda: extensiones para F2"), con la misma forma de cable que el .c:
  * per_census_start con nk select_all_entityai_b = 1: todo lo del disco (mundo S-persist mas los objetos del
    mapa simulado: edificios, contenedores con inventario anidado, una criatura), inventario recorrido en
    PREORDER, radio en (0, 120] y columna surface_y_m (la ultima, solo en este modo);
  * per_spawn_raw foreign_in_container con sk target_net_id "<high>:<low>" (rechazos target_not_found y
    no_cargo_space, sin efectos);
  * per_witness_start: testigo de creacion (resource per_witness) con muestras sample_idx 0 (EEInit) y 1..K.
"""

import json
import math
import re
import secrets
from pathlib import Path

import wire
from fake_peer import FakeExt

PREFIX = "per_"
RPC_BASE = 26102800

SERVER_VERBS = frozenset({
    "per_status",
    "per_apply_scene",
    "per_reset_scene",
    "per_child_transition",
    "per_spawn_raw",
    "per_census_start",
    "per_cleanup_qa",
    "per_witness_start",
})

AREA_CENTERS = {
    "area_a": (4500.0, 10200.0),
    "area_b": (4680.0, 10200.0),
    "area_c": (4860.0, 10200.0),
    "area_d": (5040.0, 10200.0),
    "area_a_mut": (4500.0, 10380.0),
}

SCENE_AREA = {
    "scene_a": "area_a",
    "scene_a_mut": "area_a_mut",
    "scene_a_clean": "area_a",
    "scene_b": "area_b",
    "scene_d": "area_d",
}

CENSUS_SCOL = [
    "class_name",
    "loc_kind",
    "parent_class",
    "parent_net_id",
    "slot_name",
    "owner_uid",
    "own_logical_id",
    "net_id",
    "pers_id",
]
CENSUS_NCOL = [
    "own_b",
    "in_radius_b",
    "alive_b",
    "ai_agent_b",
    "pos_x_m",
    "pos_y_m",
    "pos_z_m",
    "yaw_deg",
    "pitch_deg",
    "roll_deg",
    "max_hp",
    "health_hp",
    "inv_children_n",
    "spawn_tick_ms",
]

CENSUS_NCOL_ALL = CENSUS_NCOL + ["surface_y_m"]
CENSUS_ALL_RADIUS_MAX = 120.0

WITNESS_SCOL = ["class_name", "net_id", "parent_net_id"]
WITNESS_NCOL = [
    "sample_idx",
    "pos_x_m",
    "pos_y_m",
    "pos_z_m",
    "yaw_deg",
    "tick_ms",
    "frame",
    "ai_agent_b",
    "alive_b",
]
WITNESS_PAGE_SIZE = 5
WITNESS_MAX_ROWS = 4096
WITNESS_RADIUS_MAX = 120.0
WITNESS_WINDOW_MAX_MS = 600000.0
WITNESS_TAIL_MS = 5000.0
WITNESS_K_DEFAULT = 3
WITNESS_K_MAX = 5

# Dimensiones (ancho, alto) de cada clase segun su config vanilla (DZ/...): itemSize[] y itemsCargoSize[].
#   WoodenCrate  DZ/gear/camping/config.cpp:10074 (itemSize 10,5; cargo :10180 = 10,5)
#   SeaChest     DZ/gear/camping/config.cpp:9820  (itemSize 10,10; cargo :9846 = 10,10)
#   Barrel_*     DZ/gear/containers/config.cpp:19 Barrel_ColorBase (itemSize 10,15; cargo :95 = 10,15)
#   FirstAidKit  DZ/gear/containers/config.cpp:454 (itemSize 3,3; cargo 3,3)
#   Pot          DZ/gear/cooking/config.cpp:1106 (itemSize 4,3; cargo 4,3)
#   Rag          DZ/gear/consumables/config.cpp:494 (itemSize 1,3; sin cargo)
#   Apple        DZ/gear/food/config.cpp:4302 (itemSize 1,1; sin cargo: ni Edible_Base ni Inventory_Base, DZ/data/config.cpp:3332 y :3145, lo declaran)
#   OffroadHatchback DZ/vehicles/wheeled/config.cpp:1242 (cargo 10,30, :1495)
# Lo que no esta en CARGO_SIZE no tiene cargo; lo que no esta en ITEM_SIZE ocupa 1x1.
ITEM_SIZE = {
    "WoodenCrate": (10, 5),
    "SeaChest": (10, 10),
    "Barrel_Blue": (10, 15),
    "Barrel_Green": (10, 15),
    "Barrel_Red": (10, 15),
    "Barrel_Yellow": (10, 15),
    "FirstAidKit": (3, 3),
    "Pot": (4, 3),
    "Rag": (1, 3),
    "Apple": (1, 1),
}
CARGO_SIZE = {
    "WoodenCrate": (10, 5),
    "SeaChest": (10, 10),
    "Barrel_Blue": (10, 15),
    "Barrel_Green": (10, 15),
    "Barrel_Red": (10, 15),
    "Barrel_Yellow": (10, 15),
    "FirstAidKit": (3, 3),
    "Pot": (4, 3),
    "OffroadHatchback": (10, 30),
}

# Objetos del mapa simulado (no los crea S-persist ni los toca cleanup/reinicio): solo los ve el censo con
# select_all_entityai_b = 1. Los edificios tienen net_id real (medido en partida: parte alta negativa, p. ej.
# -2147225600:847447385), nunca 0:0.
# El slot "Cargo:idx:fila:col" coloca el hijo en la rejilla del padre (fila y columna de su esquina).
# (net_id, class_name, parent_net_id, slot_name, x, z, ai_agent)
BARRACKS_NET_ID = "-2147225600:847447385"
GARAGE_NET_ID = "-2147225344:847447400"
NO_DAMAGE_SYSTEM_CLASSES = frozenset({"Land_Wreck_Uaz"})
NO_HEALTH = -1.0  # centinela de max_hp y health_hp sin sistema de daño (el cable no admite NaN)
MAP_OBJECT_SPECS = (
    (BARRACKS_NET_ID, "Land_Mil_Barracks1", "", "", 6170.0, 7643.0, False),
    ("1:65", "Rag", BARRACKS_NET_ID, "Cargo:2:1:3", 6170.0, 7643.0, False),  # cargo proxy del edificio (PROXYCARGO)
    (GARAGE_NET_ID, "Land_Garage_Row", "", "", 6120.0, 7600.0, False),
    ("1:50", "Barrel_Blue", "", "", 6190.0, 7650.0, False),
    ("1:51", "Rag", "1:50", "Cargo:0:0:0", 6190.0, 7650.0, False),
    ("1:52", "WoodenCrate", "", "", 6150.0, 7620.0, False),
    ("1:53", "Pot", "1:52", "Cargo:0:0:0", 6150.0, 7620.0, False),
    ("1:54", "Apple", "1:53", "Cargo:0:0:0", 6150.0, 7620.0, False),
    ("1:55", "OffroadHatchback", "", "", 6200.0, 7700.0, False),
    ("1:56", "HatchbackWheel", "1:55", "Wheel_1_1", 6200.0, 7700.0, False),
    ("1:57", "Zmbf_PoliceCopBlue", "", "", 6140.0, 7680.0, True),
    ("1:58", "Barrel_Green", "", "", 6288.0, 7643.0, False),
    ("1:59", "Barrel_Red", "", "", 6500.0, 7643.0, False),
    # Resto de vehiculo del mapa, sin sistema de daño (Object.HasDamageSystem() = false): en el motor GetMaxHealth y
    # GetHealth tiran una excepcion de la VM ("No DamageSystemData"); la sonda lo lee como max_hp = health_hp = -1.
    ("1:68", "Land_Wreck_Uaz", "", "", 6200.0, 7650.0, False),
    # Pot lleno de verdad para un Rag (1x3): la manzana ocupa (0,0) y el botiquin 3x3 las columnas 1-3; el botiquin
    # tiene hueco libre, pero no es el objetivo (el padre de la ubicacion encontrada no seria el Pot).
    ("1:66", "Pot", "", "", 6160.0, 7640.0, False),
    ("1:67", "Apple", "1:66", "Cargo:0:0:0", 6160.0, 7640.0, False),
    ("1:60", "FirstAidKit", "1:66", "Cargo:0:0:1", 6160.0, 7640.0, False),
    # Botiquin 3x3 lleno con tres Rag 1x3 y sin subcontenedores.
    ("1:61", "FirstAidKit", "", "", 6165.0, 7635.0, False),
    ("1:62", "Rag", "1:61", "Cargo:0:0:0", 6165.0, 7635.0, False),
    ("1:63", "Rag", "1:61", "Cargo:0:0:1", 6165.0, 7635.0, False),
    ("1:64", "Rag", "1:61", "Cargo:0:0:2", 6165.0, 7635.0, False),
)

# El testigo del .c se engancha en EEInit de RAICES DE SCRIPT (EntityAI es del motor y no se puede modar): ItemBase,
# ZombieBase, AnimalBase, CarScript y BuildingBase (+ 4 clases vanilla que cortan la cadena por debajo de una raiz).
# El fake solo captura lo que en el .c derivaria de una de ellas; lo demas (jugadores, barcos, clases desconocidas)
# no se ve, como en el motor. Prefijos y clases tomados de la config vanilla (DZ/...) y de los scripts.
HOOK_ROOT_PREFIX = (
    ("Land_", "BuildingBase"),   # House > BuildingBase
    ("Zmb", "ZombieBase"),
    ("Animal_", "AnimalBase"),
    ("Offroad", "CarScript"),
    ("Barrel_", "ItemBase"),
)
HOOK_ROOT_CLASSES = {
    "WoodenCrate": "ItemBase", "SeaChest": "ItemBase", "FirstAidKit": "ItemBase", "Pot": "ItemBase",
    "Rag": "ItemBase", "Apple": "ItemBase", "HatchbackWheel": "ItemBase", "LargeTent": "ItemBase",
    "MediumTent": "ItemBase", "CarTent": "ItemBase", "CamoNet": "ItemBase", "Fireplace": "ItemBase",
    "Spotlight": "ItemBase", "PowerGenerator": "ItemBase", "Jeans_Blue": "ItemBase",
    "ChristmasTree": "ChristmasTree",  # vanilla corta la cadena: lo cubre su propio modded class
}


def hook_root(class_name):
    """Raiz enganchada que cubre esta clase en el .c, o None si el testigo no la ve."""
    root = HOOK_ROOT_CLASSES.get(class_name)
    if root is not None:
        return root
    low = class_name.lower()
    for prefix, root in HOOK_ROOT_PREFIX:
        if low.startswith(prefix.lower()):
            return root
    return None


CENSUS_PAGE_SIZE = 5
CENSUS_MAX_ROWS = 4096
CENSUS_MAX_MS = 900000.0
CENSUS_FINISH_DELAY_FRAMES = 10
STATE_FILE_NAME = "_dsbx_persist_world.json"
DEFAULT_MAX_HP = 100.0
DIRECTOR_UID = "dir-uid-778899"
DIRECTOR_ROOT_NET = "1:2"
DIRECTOR_JEANS_NET = "1:10"
DIRECTOR_APPLE_NET = "1:11"
PERSISTENT_CONTROL_PERS_ID = "11:22:33:44"
PERSISTENT_CHILD_PERS_ID = "55:66:77:88"
ZERO_PERS_ID = "0:0:0:0"
NET_ID_RE = re.compile(r"-?[0-9]{1,10}:-?[0-9]{1,10}")


def _surface_y(x, z):
    return 100.0 + 10.0 * math.sin(float(x) / 100.0) * math.cos(float(z) / 100.0)


def _dist2(x1, z1, x2, z2):
    return math.hypot(float(x1) - float(x2), float(z1) - float(z2))


class PersistFakeExt(FakeExt):
    def __init__(self):
        super().__init__()
        self.peer = None
        self.jobs = None
        self.epoch = ""
        self.records = []
        self.scene_gen = {}
        self.scene_last_op = {}
        self.scene_applied = {}
        self.scene_center = {}
        self.world = {}
        self.next_net_low = 100
        self.raw_net_ids = set()
        self.qa_net_ids = set()
        self.pending_finish = {}
        self.director_items = []
        self.director_uid = DIRECTOR_UID
        self.map_objects = []
        self.witness = None

    def _state_file(self):
        cfg = getattr(self.peer, "config", None)
        if cfg is None:
            return None
        try:
            return Path(cfg).parent / STATE_FILE_NAME
        except (TypeError, OSError):
            return None

    def _save_state(self):
        sf = self._state_file()
        if sf is None:
            return
        entities = []
        for ent in self.world.values():
            if ent.get("owner_uid") == self.director_uid:
                continue
            entities.append({
                "net_id": ent["net_id"],
                "pers_id": ent["pers_id"],
                "class_name": ent["class_name"],
                "cat": ent["cat"],
                "loc_kind": ent["loc_kind"],
                "parent_net_id": ent["parent_net_id"],
                "parent_class": ent["parent_class"],
                "slot_name": ent["slot_name"],
                "owner_uid": ent["owner_uid"],
                "pos": [float(ent["pos"][0]), float(ent["pos"][1]), float(ent["pos"][2])],
                "ori": [float(ent["ori"][0]), float(ent["ori"][1]), float(ent["ori"][2])],
                "max_hp": float(ent["max_hp"]),
                "health_hp": float(ent["health_hp"]),
                "spawn_tick_ms": float(ent["spawn_tick_ms"]),
                "alive": bool(ent["alive"]),
                "ai_agent": bool(ent["ai_agent"]),
                "persistent": bool(ent["persistent"]),
                "own_logical_id": ent["own_logical_id"],
                "own_b": int(ent["own_b"]),
                "scene_id": ent["scene_id"],
                "area_id": ent["area_id"],
            })
        data = {
            "director_uid": self.director_uid,
            "next_net_low": self.next_net_low,
            "entities": entities,
        }
        try:
            sf.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        except OSError:
            pass

    def _load_state(self):
        sf = self._state_file()
        if sf is None or not sf.is_file():
            return False
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        try:
            self.next_net_low = max(int(data.get("next_net_low", 100)), 100)
        except (TypeError, ValueError):
            self.next_net_low = 100
        loaded = data.get("entities")
        if not isinstance(loaded, list):
            return False
        for raw in loaded:
            if not isinstance(raw, dict) or not raw.get("persistent"):
                continue
            ent = self._add_entity(
                net_id=str(raw.get("net_id") or ""),
                pers_id=str(raw.get("pers_id") or ZERO_PERS_ID),
                class_name=str(raw.get("class_name") or ""),
                cat=str(raw.get("cat") or "raw"),
                loc_kind=str(raw.get("loc_kind") or "ground"),
                parent_net_id=str(raw.get("parent_net_id") or ""),
                parent_class=str(raw.get("parent_class") or ""),
                slot_name=str(raw.get("slot_name") or ""),
                owner_uid=str(raw.get("owner_uid") or ""),
                pos=tuple(raw.get("pos") or (0.0, 0.0, 0.0)),
                ori=tuple(raw.get("ori") or (0.0, 0.0, 0.0)),
                max_hp=float(raw.get("max_hp", DEFAULT_MAX_HP)),
                health_hp=float(raw.get("health_hp", DEFAULT_MAX_HP)),
                spawn_tick_ms=float(raw.get("spawn_tick_ms", 0.0)),
                persistent=True,
                own_logical_id="",
                own_b=0,
                area_id=str(raw.get("area_id") or ""),
            )
            ent["alive"] = bool(raw.get("alive", True))
            ent["ai_agent"] = bool(raw.get("ai_agent", False))
            if ent["owner_uid"] != self.director_uid:
                self.raw_net_ids.add(ent["net_id"])
        return True

    def init(self, peer, jobs):
        self.peer = peer
        self.jobs = jobs
        self.epoch = peer.inst
        self._build_director()
        self._build_map()
        if self._load_state():
            self.records = []
            self.scene_gen = {}
            self.scene_last_op = {}
            self.scene_applied = {}
            self.scene_center = {}
            self.pending_finish.clear()
            self.qa_net_ids.clear()

    def handles(self, verb, role):
        return role == "server" and verb in SERVER_VERBS

    def _build_director(self):
        jeans = self._add_entity(
            net_id=DIRECTOR_JEANS_NET,
            pers_id=ZERO_PERS_ID,
            class_name="Jeans_Blue",
            cat="director",
            loc_kind="attachment",
            parent_net_id=DIRECTOR_ROOT_NET,
            parent_class="SurvivorM_Mirek",
            slot_name="Legs",
            owner_uid=self.director_uid,
            pos=(4500.0, _surface_y(4500.0, 10200.0), 10200.0),
            ori=(0.0, 0.0, 0.0),
            max_hp=DEFAULT_MAX_HP,
            health_hp=DEFAULT_MAX_HP,
            spawn_tick_ms=500.0,
            persistent=True,
        )
        apple = self._add_entity(
            net_id=DIRECTOR_APPLE_NET,
            pers_id=ZERO_PERS_ID,
            class_name="Apple",
            cat="director",
            loc_kind="cargo",
            parent_net_id=DIRECTOR_JEANS_NET,
            parent_class="Jeans_Blue",
            slot_name="Cargo:0:0:0",
            owner_uid=self.director_uid,
            pos=(4500.0, _surface_y(4500.0, 10200.0), 10200.0),
            ori=(0.0, 0.0, 0.0),
            max_hp=50.0,
            health_hp=50.0,
            spawn_tick_ms=500.0,
            persistent=True,
        )
        self.director_items = [jeans["net_id"], apple["net_id"]]

    def _alloc_net_id(self):
        self.next_net_low += 1
        return "1:%d" % self.next_net_low

    def _make_entity(self, **kw):
        ent = {
            "net_id": kw["net_id"],
            "pers_id": kw.get("pers_id", ZERO_PERS_ID),
            "class_name": kw["class_name"],
            "cat": kw.get("cat", "prop"),
            "loc_kind": kw.get("loc_kind", "ground"),
            "parent_net_id": kw.get("parent_net_id", ""),
            "parent_class": kw.get("parent_class", ""),
            "slot_name": kw.get("slot_name", ""),
            "owner_uid": kw.get("owner_uid", ""),
            "pos": tuple(kw.get("pos", (0.0, 0.0, 0.0))),
            "ori": tuple(kw.get("ori", (0.0, 0.0, 0.0))),
            "max_hp": float(kw.get("max_hp", DEFAULT_MAX_HP)),
            "health_hp": float(kw.get("health_hp", DEFAULT_MAX_HP)),
            "spawn_tick_ms": float(kw.get("spawn_tick_ms", 0.0)),
            "alive": True,
            "ai_agent": bool(kw.get("ai_agent", False)),
            "persistent": bool(kw.get("persistent", False)),
            "own_logical_id": kw.get("own_logical_id", ""),
            "own_b": int(kw.get("own_b", 0)),
            "scene_id": kw.get("scene_id", ""),
            "area_id": kw.get("area_id", ""),
        }
        return ent

    def _add_entity(self, **kw):
        ent = self._make_entity(**kw)
        self.world[ent["net_id"]] = ent
        self._witness_capture(ent)
        return ent

    def _build_map(self):
        self.map_objects = []
        for net_id, cname, parent_net, slot, x, z, ai in MAP_OBJECT_SPECS:
            parent_class = ""
            if parent_net:
                for prev in self.map_objects:
                    if prev["net_id"] == parent_net:
                        parent_class = prev["class_name"]
            self.map_objects.append(self._make_entity(
                net_id=net_id,
                pers_id=ZERO_PERS_ID,
                class_name=cname,
                cat="map",
                loc_kind="cargo" if (parent_net and slot.startswith("Cargo")) else ("attachment" if parent_net else "ground"),
                parent_net_id=parent_net,
                parent_class=parent_class,
                slot_name=slot,
                owner_uid="",
                pos=(x, _surface_y(x, z), z),
                ori=(0.0, 0.0, 0.0),
                max_hp=NO_HEALTH if cname in NO_DAMAGE_SYSTEM_CLASSES else DEFAULT_MAX_HP,
                health_hp=NO_HEALTH if cname in NO_DAMAGE_SYSTEM_CLASSES else DEFAULT_MAX_HP,
                spawn_tick_ms=0.0,
                persistent=False,
                ai_agent=ai,
            ))

    def _find_by_net_id(self, net_id):
        # GetObjectByNetworkId: 0:0 es "sin id de red asignado", no resuelve nada.
        if net_id == "0:0":
            return None
        ent = self.world.get(net_id)
        if ent is not None and ent["alive"]:
            return ent
        for obj in self.map_objects:
            if obj["net_id"] == net_id and obj["alive"]:
                return obj
        return None

    def _cargo_children(self, net_id):
        out = []
        for ent in list(self.world.values()) + self.map_objects:
            if ent["alive"] and ent["parent_net_id"] == net_id and ent["loc_kind"] == "cargo":
                out.append(ent)
        return out

    @staticmethod
    def _slot_rc(slot_name):
        parts = str(slot_name).split(":")
        if len(parts) == 4 and parts[0] == "Cargo":
            try:
                return int(parts[2]), int(parts[3])
            except ValueError:
                return None
        return None

    def _first_fit(self, parent, item_class):
        """Primer hueco (fila y columna de la esquina) en la rejilla de cargo de parent, o None."""
        dims = CARGO_SIZE.get(parent["class_name"])
        if dims is None:
            return None
        cols, rows = dims
        iw, ih = ITEM_SIZE.get(item_class, (1, 1))
        used = set()
        for child in self._cargo_children(parent["net_id"]):
            rc = self._slot_rc(child["slot_name"])
            if rc is None:
                continue
            cw, ch = ITEM_SIZE.get(child["class_name"], (1, 1))
            for r in range(rc[0], rc[0] + ch):
                for c in range(rc[1], rc[1] + cw):
                    used.add((r, c))
        for r in range(0, rows - ih + 1):
            for c in range(0, cols - iw + 1):
                if all((rr, cc) not in used for rr in range(r, r + ih) for cc in range(c, c + iw)):
                    return r, c
        return None

    def _find_free_location(self, target, item_class):
        """FindFirstFreeLocationForNewEntity(CARGO): primero el cargo del objetivo y despues el de sus descendientes
        en PREORDER (vanilla puede devolver el hueco de un subcontenedor, inventory.c:879). Devuelve (padre, slot)."""
        for cand in [target] + self._preorder_children(target["net_id"]):
            fit = self._first_fit(cand, item_class)
            if fit is not None:
                return cand, "Cargo:0:%d:%d" % fit
        return None

    def _preorder_children(self, net_id):
        # Hijos de net_id en PREORDER (mundo y mapa), como EnumerateInventory(PREORDER) menos la raiz.
        out = []
        for ent in list(self.world.values()) + self.map_objects:
            if ent["alive"] and ent["parent_net_id"] == net_id and net_id != "":
                out.append(ent)
                out.extend(self._preorder_children(ent["net_id"]))
        return out

    def _record_by(self, scene_id, logical_id):
        for rec in self.records:
            if rec["scene_id"] == scene_id and rec["logical_id"] == logical_id:
                return rec
        return None

    def _children_count(self, net_id):
        n = 0
        for ent in list(self.world.values()) + self.map_objects:
            if ent["alive"] and ent["parent_net_id"] == net_id:
                n += 1
        return n

    def _descendants(self, net_id):
        out = []
        frontier = [net_id]
        seen = {net_id}
        while frontier:
            cur = frontier.pop()
            for ent in self.world.values():
                if ent["net_id"] in seen:
                    continue
                if ent["parent_net_id"] == cur:
                    seen.add(ent["net_id"])
                    out.append(ent)
                    frontier.append(ent["net_id"])
        return out

    def _delete_entity(self, ent):
        self.world.pop(ent["net_id"], None)
        self.raw_net_ids.discard(ent["net_id"])
        self.qa_net_ids.discard(ent["net_id"])

    def _drop_records(self, recs):
        for rec in recs:
            ent = rec.get("ent")
            if ent is not None:
                self._delete_entity(ent)
            if rec in self.records:
                self.records.remove(rec)

    def _census_row(self, ent, in_radius, deep=False):
        return {
            "class_name": ent["class_name"],
            "loc_kind": ent["loc_kind"],
            "parent_class": ent["parent_class"],
            "parent_net_id": ent["parent_net_id"],
            "slot_name": ent["slot_name"],
            "owner_uid": ent["owner_uid"],
            "own_logical_id": ent["own_logical_id"],
            "net_id": ent["net_id"],
            "pers_id": ent["pers_id"],
            "own_b": float(ent["own_b"]),
            "in_radius_b": float(in_radius),
            "alive_b": 1.0 if ent["alive"] else 0.0,
            "ai_agent_b": 1.0 if ent["ai_agent"] else 0.0,
            "pos_x_m": float(ent["pos"][0]),
            "pos_y_m": float(ent["pos"][1]),
            "pos_z_m": float(ent["pos"][2]),
            "yaw_deg": float(ent["ori"][0]),
            "pitch_deg": float(ent["ori"][1]),
            "roll_deg": float(ent["ori"][2]),
            "max_hp": float(ent["max_hp"]),
            "health_hp": float(ent["health_hp"]),
            # El .c cuenta con EnumerateInventory(PREORDER): todos los descendientes. El modo 0 del fake sigue
            # contando hijos directos (S-persist); el modo 1 cuenta como el .c.
            "inv_children_n": float(len(self._preorder_children(ent["net_id"])) if deep else self._children_count(ent["net_id"])),
            "spawn_tick_ms": float(ent["spawn_tick_ms"]),
            "surface_y_m": float(_surface_y(ent["pos"][0], ent["pos"][2])),
        }

    # ------------------------------------------------------------------ verbs
    def on_start_op(self, op, args_unpacked, raw_args):
        verb = op["verb"]
        fault = op.get("qa_fault", "")
        if verb == "per_status":
            return self._op_status(args_unpacked)
        if verb == "per_cleanup_qa":
            return self._op_cleanup(args_unpacked)
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        if verb == "per_apply_scene":
            return self._op_apply(op, args_unpacked, fault)
        if verb == "per_reset_scene":
            return self._op_reset(args_unpacked, fault)
        if verb == "per_child_transition":
            return self._op_transition(args_unpacked)
        if verb == "per_spawn_raw":
            return self._op_spawn_raw(args_unpacked)
        if verb == "per_census_start":
            return self._op_census_start(op, args_unpacked, fault)
        if verb == "per_witness_start":
            return self._op_witness_start(op, args_unpacked)
        return ("rejected", "unknown_verb", wire.empty_payload())

    def _op_status(self, args_unpacked):
        strs = args_unpacked.get("str") or {}
        lifecycle = strs.get("lifecycle", "")
        rows = []
        for scene_id, gen in self.scene_gen.items():
            alive_n = sum(
                1 for rec in self.records
                if rec["scene_id"] == scene_id and rec["ent"]["alive"]
            )
            rows.append({
                "scene_id": scene_id,
                "last_op_id": self.scene_last_op.get(scene_id, ""),
                "gen_n": float(gen),
                "own_alive_n": float(alive_n),
            })
        s = {
            "server_epoch": self.epoch,
            "director_uid": self.director_uid,
        }
        if lifecycle == "shutdown":
            s["shutdown_marker"] = "1"
        elif lifecycle == "startup":
            s["startup_marker"] = "1"
        n = {
            "tick_ms": float(self.peer.local_ms()),
            "frame": float(self.peer.frame),
            "registered_total_n": float(len(self.records)),
            "scenes_count_n": float(len(self.scene_gen)),
            "director_present_b": 1.0,
            "director_alive_b": 1.0,
            "director_inv_readable_b": 1.0,
            "director_inv_count_n": float(len(self.director_items)),
        }
        payload = wire.pack_payload(
            scalars_str=s,
            scalars_num=n,
            num_cols=["gen_n", "own_alive_n"],
            str_cols=["scene_id", "last_op_id"],
            row_dicts=rows,
        )
        return ("done", "", payload)

    def _op_apply(self, op, args_unpacked, fault):
        strs = args_unpacked.get("str") or {}
        nums = args_unpacked.get("num") or {}
        scene_id = strs.get("scene_id", "")
        scene_op_id = strs.get("scene_op_id", "")
        expect_epoch = strs.get("expect_epoch", "")
        pathway = strs.get("q9_pathway", "")
        gen_n = int(round(float(nums.get("gen_n", 0.0))))
        rows_in = args_unpacked.get("rows") or []
        if not scene_id or not scene_op_id or gen_n < 1:
            return ("rejected", "bad_args", wire.empty_payload())
        if expect_epoch != self.epoch:
            return ("rejected", "stale_epoch", wire.empty_payload())
        if pathway not in ("a", "b"):
            return ("rejected", "bad_args", wire.empty_payload())
        cached = self.scene_applied.get(scene_id)
        if cached is not None and cached["scene_op_id"] == scene_op_id:
            s = dict(cached["s"])
            n = dict(cached["n"])
            n["idempotent_hit_b"] = 1.0
            payload = wire.pack_payload(
                scalars_str=s,
                scalars_num=n,
                num_cols=list(cached["ncol"]),
                str_cols=list(cached["scol"]),
                row_dicts=[dict(r) for r in cached["rows"]],
            )
            return ("done", "", payload)

        persistent = fault == "omit_nopersistency_flag"
        area_id = SCENE_AREA.get(scene_id, "area_a")
        now_ms = float(self.peer.local_ms())
        frame = int(self.peer.frame)
        created_roots = 0
        created_children = 0
        out_rows = []
        local = {}
        root_positions = []
        for row in rows_in:
            lid = str(row.get("logical_id", ""))
            pid = str(row.get("parent_id", ""))
            cat = str(row.get("cat", ""))
            cname = str(row.get("class_name", ""))
            sname = str(row.get("slot_name", ""))
            rx = float(row.get("req_x_m", 0.0))
            rz = float(row.get("req_z_m", 0.0))
            ryaw = float(row.get("req_yaw_deg", 0.0))
            ratio = float(row.get("health_mark_ratio", 0.0))
            max_hp = DEFAULT_MAX_HP
            hp = max_hp * ratio if ratio > 0.0 else max_hp
            ai_b = cat in ("infected", "animal")
            if pid == "":
                gy = _surface_y(rx, rz)
                pos = (rx, gy, rz)
                ori = (ryaw, 0.0, 0.0)
                loc_kind = "ground"
                parent_net = ""
                parent_class = ""
                slot_name = ""
                created_roots += 1
                root_positions.append((rx, rz))
                q9 = (rx, gy, rz)
                dx = dy = dz = 0.0
                err = 0.0
                q9_yaw, q9_pitch, q9_roll = ryaw, 0.0, 0.0
            else:
                parent = local.get(pid)
                if parent is None:
                    return ("rejected", "bad_args", wire.empty_payload())
                pos = parent["pos"]
                ori = parent["ori"]
                if sname == "Cargo":
                    idx = self._children_count(parent["net_id"])
                    loc_kind = "cargo"
                    slot_name = "Cargo:0:0:%d" % idx
                else:
                    loc_kind = "attachment"
                    slot_name = sname
                parent_net = parent["net_id"]
                parent_class = parent["class_name"]
                created_children += 1
                q9 = pos
                dx = dy = dz = 0.0
                err = 0.0
                q9_yaw, q9_pitch, q9_roll = ori
            net_id = self._alloc_net_id()
            ent = self._add_entity(
                net_id=net_id,
                pers_id=ZERO_PERS_ID,
                class_name=cname,
                cat=cat,
                loc_kind=loc_kind,
                parent_net_id=parent_net,
                parent_class=parent_class,
                slot_name=slot_name,
                owner_uid="",
                pos=pos,
                ori=ori,
                max_hp=max_hp,
                health_hp=hp,
                spawn_tick_ms=now_ms,
                persistent=persistent,
                own_logical_id=lid,
                own_b=1,
                scene_id=scene_id,
                area_id=area_id,
                ai_agent=ai_b,
            )
            self.records.append({
                "server_epoch": self.epoch,
                "scene_id": scene_id,
                "gen_n": gen_n,
                "logical_id": lid,
                "parent_id": pid,
                "cat": cat,
                "class_name": cname,
                "slot_name": sname,
                "ent": ent,
                "net_id": net_id,
                "spawn_tick_ms": now_ms,
                "max_hp": max_hp,
                "health_hp": hp,
            })
            if persistent:
                self.qa_net_ids.add(net_id)
            local[lid] = ent
            out_rows.append({
                "logical_id": lid,
                "class_name": cname,
                "net_id": net_id,
                "obs_loc_kind": loc_kind,
                "obs_parent_net_id": parent_net,
                "obs_slot_name": slot_name,
                "ok_b": 1.0,
                "alive_b": 1.0,
                "ai_agent_b": 1.0 if ai_b else 0.0,
                "req_y_m": float(pos[1]),
                "q9_x_m": float(q9[0]),
                "q9_y_m": float(q9[1]),
                "q9_z_m": float(q9[2]),
                "q9_dx_m": float(dx),
                "q9_dy_m": float(dy),
                "q9_dz_m": float(dz),
                "q9_err_3d_m": float(err),
                "q9_yaw_deg": float(q9_yaw),
                "q9_pitch_deg": float(q9_pitch),
                "q9_roll_deg": float(q9_roll),
                "max_hp": max_hp,
                "health_hp": hp,
                "spawn_tick_ms": now_ms,
            })
        if root_positions:
            cx = sum(p[0] for p in root_positions) / float(len(root_positions))
            cz = sum(p[1] for p in root_positions) / float(len(root_positions))
            self.scene_center[scene_id] = (cx, cz)
        s = {
            "apply_status": "ok",
            "reason": "",
            "server_epoch": self.epoch,
            "scene_id": scene_id,
            "scene_op_id": scene_op_id,
            "q9_pathway": pathway,
        }
        n = {
            "gen_n": float(gen_n),
            "created_roots_n": float(created_roots),
            "created_children_n": float(created_children),
            "idempotent_hit_b": 0.0,
            "q9_tick_ms": now_ms,
            "q9_frame": float(frame),
        }
        ncol = [
            "ok_b", "alive_b", "ai_agent_b", "req_y_m", "q9_x_m", "q9_y_m",
            "q9_z_m", "q9_dx_m", "q9_dy_m", "q9_dz_m", "q9_err_3d_m",
            "q9_yaw_deg", "q9_pitch_deg", "q9_roll_deg", "max_hp",
            "health_hp", "spawn_tick_ms",
        ]
        scol = [
            "logical_id", "class_name", "net_id", "obs_loc_kind",
            "obs_parent_net_id", "obs_slot_name",
        ]
        self.scene_gen[scene_id] = gen_n
        self.scene_last_op[scene_id] = scene_op_id
        self.scene_applied[scene_id] = {
            "scene_op_id": scene_op_id,
            "s": dict(s),
            "n": dict(n),
            "ncol": list(ncol),
            "scol": list(scol),
            "rows": [dict(r) for r in out_rows],
        }
        payload = wire.pack_payload(
            scalars_str=s,
            scalars_num=n,
            num_cols=ncol,
            str_cols=scol,
            row_dicts=out_rows,
        )
        self._save_state()
        return ("done", "", payload)

    def _op_reset(self, args_unpacked, fault):
        strs = args_unpacked.get("str") or {}
        scene_id = strs.get("scene_id", "")
        reset_op_id = strs.get("reset_op_id", "")
        expect_epoch = strs.get("expect_epoch", "")
        if not scene_id or not reset_op_id:
            return ("rejected", "bad_args", wire.empty_payload())
        if expect_epoch != self.epoch:
            return ("rejected", "stale_epoch", wire.empty_payload())
        scene_recs = [
            rec for rec in self.records
            if rec["scene_id"] == scene_id
            and rec["server_epoch"] == self.epoch
            and rec["gen_n"] == self.scene_gen.get(scene_id, 1)
        ]
        now_ms = float(self.peer.local_ms())
        frame = int(self.peer.frame)
        retained_rows = []
        if fault == "reset_wipe_radius_25m":
            center = self.scene_center.get(scene_id) or AREA_CENTERS.get(
                SCENE_AREA.get(scene_id, "area_a"), (0.0, 0.0)
            )
            for ent in list(self.world.values()):
                if ent["owner_uid"] == self.director_uid:
                    continue
                if _dist2(ent["pos"][0], ent["pos"][2], center[0], center[1]) <= 25.0:
                    self._delete_entity(ent)
            deleted_n = len(scene_recs)
            self._drop_records(scene_recs)
            s = {
                "reset_status": "ok",
                "reason": "clean",
                "server_epoch": self.epoch,
                "scene_id": scene_id,
                "reset_op_id": reset_op_id,
            }
            n = {
                "deleted_n": float(deleted_n),
                "retained_n": 0.0,
                "tick_ms": now_ms,
                "frame": float(frame),
            }
            payload = wire.pack_payload(
                scalars_str=s,
                scalars_num=n,
                num_cols=["foreign_descendants_n"],
                str_cols=["logical_id", "class_name", "net_id"],
                row_dicts=[],
            )
            self._save_state()
            return ("done", "", payload)

        deletable = {rec["ent"]["net_id"]: rec for rec in scene_recs}
        retain = {}
        for rec in scene_recs:
            ent = rec["ent"]
            foreign = False
            for desc in self._descendants(ent["net_id"]):
                if desc["net_id"] not in deletable:
                    foreign = True
                    break
            if foreign:
                retain[ent["net_id"]] = True
                parent_nid = ent["parent_net_id"]
                while parent_nid in deletable:
                    retain[parent_nid] = True
                    parent_nid = deletable[parent_nid]["ent"]["parent_net_id"]

        deleted = 0
        for rec in list(scene_recs):
            ent = rec["ent"]
            if rec["parent_id"] != "" and not retain.get(ent["net_id"]):
                self._drop_records([rec])
                deleted += 1
        for rec in list(scene_recs):
            ent = rec["ent"]
            if rec["parent_id"] == "" and not retain.get(ent["net_id"]):
                self._drop_records([rec])
                deleted += 1

        retained_recs = [
            rec for rec in scene_recs
            if retain.get(rec["ent"]["net_id"])
        ]
        for rec in retained_recs:
            ent = rec["ent"]
            survivors = 0
            for desc in self._descendants(ent["net_id"]):
                dnid = desc["net_id"]
                if dnid not in deletable:
                    survivors += 1
            retained_rows.append({
                "logical_id": rec["logical_id"],
                "class_name": ent["class_name"],
                "net_id": ent["net_id"],
                "foreign_descendants_n": float(survivors),
            })
        retained_n = len(retained_rows)
        s = {
            "reset_status": "partial" if retained_n > 0 else "ok",
            "reason": "foreign_content_retained" if retained_n > 0 else "clean",
            "server_epoch": self.epoch,
            "scene_id": scene_id,
            "reset_op_id": reset_op_id,
        }
        n = {
            "deleted_n": float(deleted),
            "retained_n": float(retained_n),
            "tick_ms": now_ms,
            "frame": float(frame),
        }
        payload = wire.pack_payload(
            scalars_str=s,
            scalars_num=n,
            num_cols=["foreign_descendants_n"],
            str_cols=["logical_id", "class_name", "net_id"],
            row_dicts=retained_rows,
        )
        self._save_state()
        return ("done", "", payload)

    def _op_transition(self, args_unpacked):
        strs = args_unpacked.get("str") or {}
        scene_id = strs.get("scene_id", "")
        logical_id = strs.get("logical_id", "")
        action = strs.get("action", "")
        expect_epoch = strs.get("expect_epoch", "")
        target_scene = strs.get("target_scene_id", "")
        target_parent = strs.get("target_parent_id", "")
        if expect_epoch != self.epoch:
            return ("rejected", "stale_epoch", wire.empty_payload())
        rec = self._record_by(scene_id, logical_id)
        if rec is None:
            return ("rejected", "unknown_entity", wire.empty_payload())
        ent = rec["ent"]
        pre = {
            "pre_loc_kind": ent["loc_kind"],
            "pre_parent_net_id": ent["parent_net_id"],
            "pre_slot_name": ent["slot_name"],
            "pre_owner_uid": ent["owner_uid"],
        }
        if action == "drop_to_ground":
            ent["loc_kind"] = "ground"
            ent["parent_net_id"] = ""
            ent["parent_class"] = ""
            ent["slot_name"] = ""
            ent["owner_uid"] = ""
        elif action == "move_to_director":
            ent["loc_kind"] = "cargo"
            ent["parent_net_id"] = DIRECTOR_JEANS_NET
            ent["parent_class"] = "Jeans_Blue"
            ent["slot_name"] = "Cargo:0:1:0"
            ent["owner_uid"] = self.director_uid
        elif action == "move_to_container":
            tgt = self._record_by(target_scene, target_parent)
            if tgt is None:
                return ("rejected", "unknown_entity", wire.empty_payload())
            tgt_ent = tgt["ent"]
            ent["loc_kind"] = "cargo"
            ent["parent_net_id"] = tgt_ent["net_id"]
            ent["parent_class"] = tgt_ent["class_name"]
            ent["slot_name"] = "Cargo:0:0:%d" % self._children_count(tgt_ent["net_id"])
            ent["owner_uid"] = ""
            ent["pos"] = tgt_ent["pos"]
            ent["ori"] = tgt_ent["ori"]
            ent["area_id"] = tgt_ent["area_id"]
        else:
            return ("rejected", "bad_args", wire.empty_payload())
        s = {
            "transition_status": "ok",
            "net_id": ent["net_id"],
            "post_loc_kind": ent["loc_kind"],
            "post_parent_net_id": ent["parent_net_id"],
            "post_slot_name": ent["slot_name"],
            "post_owner_uid": ent["owner_uid"],
        }
        s.update(pre)
        n = {
            "pos_x_m": float(ent["pos"][0]),
            "pos_y_m": float(ent["pos"][1]),
            "pos_z_m": float(ent["pos"][2]),
            "yaw_deg": float(ent["ori"][0]),
            "pitch_deg": float(ent["ori"][1]),
            "roll_deg": float(ent["ori"][2]),
            "tick_ms": float(self.peer.local_ms()),
            "frame": float(self.peer.frame),
        }
        payload = wire.pack_payload(scalars_str=s, scalars_num=n)
        self._save_state()
        return ("done", "", payload)

    def _op_spawn_raw(self, args_unpacked):
        strs = args_unpacked.get("str") or {}
        nums = args_unpacked.get("num") or {}
        tag = strs.get("tag", "")
        mode = strs.get("mode", "")
        cname = strs.get("class_name", "")
        child_class = strs.get("child_cargo_class", "")
        target_scene = strs.get("target_scene_id", "")
        target_parent = strs.get("target_parent_id", "")
        target_net = strs.get("target_net_id", "")
        x_m = float(nums.get("x_m", 0.0))
        z_m = float(nums.get("z_m", 0.0))
        yaw = float(nums.get("yaw_deg", 0.0))
        ratio = float(nums.get("health_mark_ratio", 0.0))
        if not tag or not cname:
            return ("rejected", "bad_args", wire.empty_payload())
        max_hp = DEFAULT_MAX_HP
        hp = max_hp * ratio if ratio > 0.0 else max_hp
        now_ms = float(self.peer.local_ms())
        persistent = mode == "persistent_control"
        pers_id = ZERO_PERS_ID
        loc_kind = "ground"
        parent_net = ""
        parent_class = ""
        slot_name = ""
        pos = (x_m, _surface_y(x_m, z_m), z_m)
        ori = (yaw, 0.0, 0.0)
        area_id = ""
        for aid, (cx, cz) in AREA_CENTERS.items():
            if _dist2(x_m, z_m, cx, cz) <= 60.0:
                area_id = aid
                break
        if mode == "foreign_in_container" and target_net != "":
            # Padre por net_id (GetObjectByNetworkId). Los rechazos salen antes de crear nada: sin efectos.
            if not NET_ID_RE.fullmatch(target_net):
                return ("rejected", "bad_args", wire.empty_payload())
            tgt_ent = self._find_by_net_id(target_net)
            if tgt_ent is None:
                return ("rejected", "target_not_found", wire.empty_payload())
            # El hueco tiene que ser CARGO y su padre exactamente el objetivo (como el .c con GetParent()); si el
            # unico hueco esta en un subcontenedor, rechazo sin efectos.
            found = self._find_free_location(tgt_ent, cname)
            if found is None or found[0] is not tgt_ent:
                return ("rejected", "no_cargo_space", wire.empty_payload())
            loc_kind = "cargo"
            parent_net = tgt_ent["net_id"]
            parent_class = tgt_ent["class_name"]
            slot_name = found[1]
            pos = tgt_ent["pos"]
            ori = tgt_ent["ori"]
            area_id = tgt_ent["area_id"]
        elif mode == "foreign_in_container":
            tgt = self._record_by(target_scene, target_parent)
            if tgt is None:
                return ("rejected", "unknown_entity", wire.empty_payload())
            tgt_ent = tgt["ent"]
            loc_kind = "cargo"
            parent_net = tgt_ent["net_id"]
            parent_class = tgt_ent["class_name"]
            slot_name = "Cargo:0:1:0"
            pos = tgt_ent["pos"]
            ori = tgt_ent["ori"]
            area_id = tgt_ent["area_id"]
        elif mode == "persistent_control":
            pers_id = PERSISTENT_CONTROL_PERS_ID
        net_id = self._alloc_net_id()
        ent = self._add_entity(
            net_id=net_id,
            pers_id=pers_id,
            class_name=cname,
            cat="raw",
            loc_kind=loc_kind,
            parent_net_id=parent_net,
            parent_class=parent_class,
            slot_name=slot_name,
            owner_uid="",
            pos=pos,
            ori=ori,
            max_hp=max_hp,
            health_hp=hp,
            spawn_tick_ms=now_ms,
            persistent=persistent,
            own_logical_id="",
            own_b=0,
            area_id=area_id,
        )
        self.raw_net_ids.add(net_id)
        child_count = 0
        if mode == "persistent_control" and child_class:
            child_net = self._alloc_net_id()
            self._add_entity(
                net_id=child_net,
                pers_id=PERSISTENT_CHILD_PERS_ID,
                class_name=child_class,
                cat="raw_child",
                loc_kind="cargo",
                parent_net_id=net_id,
                parent_class=cname,
                slot_name="Cargo:0:0:0",
                owner_uid="",
                pos=pos,
                ori=ori,
                max_hp=DEFAULT_MAX_HP,
                health_hp=DEFAULT_MAX_HP,
                spawn_tick_ms=now_ms,
                persistent=True,
                own_logical_id="",
                own_b=0,
                area_id=area_id,
            )
            self.raw_net_ids.add(child_net)
            child_count = 1
        s = {
            "spawn_status": "ok",
            "tag": tag,
            "class_name": cname,
            "net_id": net_id,
            "pers_id": pers_id,
            "obs_loc_kind": ent["loc_kind"],
            "obs_parent_net_id": ent["parent_net_id"],
            "obs_slot_name": ent["slot_name"],
        }
        n = {
            "pos_x_m": float(ent["pos"][0]),
            "pos_y_m": float(ent["pos"][1]),
            "pos_z_m": float(ent["pos"][2]),
            "yaw_deg": float(ent["ori"][0]),
            "pitch_deg": float(ent["ori"][1]),
            "roll_deg": float(ent["ori"][2]),
            "max_hp": float(ent["max_hp"]),
            "health_hp": float(ent["health_hp"]),
            "child_count_n": float(child_count),
            "tick_ms": now_ms,
            "frame": float(self.peer.frame),
        }
        payload = wire.pack_payload(scalars_str=s, scalars_num=n)
        self._save_state()
        return ("done", "", payload)



    def _op_census_start(self, op, args_unpacked, fault):
        strs = args_unpacked.get("str") or {}
        nums = args_unpacked.get("num") or {}
        area_tag = strs.get("area_tag", "")
        center_x = float(nums.get("center_x_m", 0.0))
        center_z = float(nums.get("center_z_m", 0.0))
        radius = float(nums.get("radius_m", 60.0))
        include_dir = int(round(float(nums.get("include_director_b", 0.0))))
        select_all_raw = float(nums.get("select_all_entityai_b", 0.0))
        if not area_tag:
            return ("rejected", "bad_args", wire.empty_payload())
        # Modo opt-in select_all_entityai_b: con 0 nada cambia (ni filas, ni columnas, ni tope de radio);
        # con 1 el radio va en (0, 120]. Los rechazos salen antes de cualquier efecto.
        if select_all_raw not in (0.0, 1.0):
            return ("rejected", "bad_args", wire.empty_payload())
        select_all = int(select_all_raw)
        if select_all == 1 and not (0.0 < radius <= CENSUS_ALL_RADIUS_MAX):
            return ("rejected", "bad_args", wire.empty_payload())
        if fault == "drop_ctrl_pre_restart":
            for net_id in list(self.world.keys()):
                ent = self.world[net_id]
                if ent["class_name"] == "Barrel_Yellow" and ent["area_id"] == "area_c":
                    self._delete_entity(ent)
        job_id = op["op_id"]
        # Mutante census_resource_bypass: el recurso per_census no protege; el segundo censo se
        # acepta aunque el primero siga activo. El runner pasa este qa_fault solo en esa parte.
        if fault == "census_resource_bypass":
            self.jobs.held_resources.pop("per_census", None)
        err = self.jobs.start_job(
            self,
            job_id,
            "per_census",
            list(CENSUS_NCOL_ALL if select_all == 1 else CENSUS_NCOL),
            list(CENSUS_SCOL),
            CENSUS_PAGE_SIZE,
            CENSUS_MAX_ROWS,
            CENSUS_MAX_MS,
            "stop",
        )
        if err != "":
            return ("rejected", err, wire.empty_payload())
        area_id = area_tag
        if ":" in area_tag:
            area_id = area_tag.split(":", 1)[1]
        snap_ms = float(self.peer.local_ms())
        snap_frame = int(self.peer.frame)
        rows = []
        if select_all == 1:
            # Todo lo del disco (mundo S-persist y mapa simulado): cada raiz seguida de su inventario en PREORDER.
            # El director no es raiz del censo; su inventario solo entra con include_director_b = 1.
            # Seleccion como el .c: esfera de GetObjectsAtPosition3D centrada en (cx, SurfaceY(cx, cz), cz), sin filtro
            # horizontal (HandleCensusStart: centerPos). Una raiz 116 m por encima del centro queda fuera con r = 115.
            center_y = _surface_y(center_x, center_z)
            for ent in list(self.world.values()) + self.map_objects:
                if not ent["alive"] or ent["parent_net_id"] != "" or ent["owner_uid"] == self.director_uid:
                    continue
                d3 = math.sqrt(
                    (float(ent["pos"][0]) - center_x) ** 2
                    + (float(ent["pos"][1]) - center_y) ** 2
                    + (float(ent["pos"][2]) - center_z) ** 2
                )
                if d3 > radius:
                    continue
                rows.append(self._census_row(ent, 1, deep=True))
                for sub in self._preorder_children(ent["net_id"]):
                    rows.append(self._census_row(sub, 1, deep=True))
            if include_dir == 1:
                for ent in self.world.values():
                    if ent["alive"] and ent["owner_uid"] == self.director_uid:
                        rows.append(self._census_row(ent, 1, deep=True))
        else:
            for ent in self.world.values():
                if not ent["alive"]:
                    continue
                if ent["owner_uid"] == self.director_uid:
                    if include_dir == 1:
                        rows.append(self._census_row(ent, 1))
                    continue
                if _dist2(ent["pos"][0], ent["pos"][2], center_x, center_z) <= radius:
                    rows.append(self._census_row(ent, 1))
                    continue
                if ent["own_b"] == 1 and ent["cat"] in ("infected", "animal"):
                    if ent["area_id"] == area_id:
                        rows.append(self._census_row(ent, 0))
        census_ncol = CENSUS_NCOL_ALL if select_all == 1 else CENSUS_NCOL
        for row in rows:
            nvals = [row[c] for c in census_ncol]
            svals = [row[c] for c in CENSUS_SCOL]
            if not self.jobs.append_row(job_id, nvals, svals):
                if select_all == 1 and self.jobs.get_state(job_id) == "failed":
                    # Tope de filas: el JobMgr ya dejo el trabajo en failed/rows_cap; no se sigue ni se trunca en
                    # silencio. Igual que el .c, el arranque responde done y el estado se lee con job_read.
                    break
                return ("rejected", "bad_args", wire.empty_payload())
        s = {
            "job": job_id,
            "state": "running",
            "resource": "per_census",
            "area_tag": area_tag,
            "server_epoch": self.epoch,
            "director_uid": self.director_uid,
        }
        n = {
            "snap_tick_ms": snap_ms,
            "snap_frame": float(snap_frame),
            "rows_captured_n": float(len(rows)),
            "center_x_m": center_x,
            "center_z_m": center_z,
            "radius_m": radius,
            "director_present_b": 1.0,
            "director_alive_b": 1.0,
            "director_inv_readable_b": 1.0,
            "director_inv_count_n": float(len(self.director_items)),
        }
        payload = wire.pack_payload(scalars_str=s, scalars_num=n)
        self.pending_finish[job_id] = CENSUS_FINISH_DELAY_FRAMES
        return ("done", "", payload)

    # --------------------------------------------------------- testigo de creacion
    def _witness_capture(self, ent):
        # Equivale al gancho EEInit del .c: apagado cuesta un chequeo; encendido filtra por radio y ventana.
        wit = self.witness
        if wit is None or wit["closed"]:
            return
        now_ms = float(self.peer.local_ms())
        if now_ms > wit["end_ms"]:
            return
        if hook_root(ent["class_name"]) is None:
            return  # no deriva de ninguna raiz enganchada: el .c no la ve
        if len(wit["buf"]) >= WITNESS_MAX_ROWS + 1:
            return
        if _dist2(ent["pos"][0], ent["pos"][2], wit["cx"], wit["cz"]) > wit["radius"]:
            return
        # En EEInit el motor aun no ha asignado el net_id (0:0): se lee en el primer tick de servidor.
        wit["buf"].append({
            "ent": ent,
            "class_name": ent["class_name"],
            "net_id": "0:0",
            "parent_net_id": "",
            "pos": tuple(ent["pos"]),
            "yaw": float(ent["ori"][0]),
            "tick_ms": now_ms,
            "frame": int(wit["frame"]),
            "ai": 1.0 if ent["ai_agent"] else 0.0,
        })

    def _witness_alive(self, ent):
        return ent["alive"] and self.world.get(ent["net_id"]) is ent

    def _witness_row(self, sample_idx, cls, net_id, parent_net_id, pos, yaw, tick_ms, frame, ai, alive):
        return {
            "class_name": cls,
            "net_id": net_id,
            "parent_net_id": parent_net_id,
            "sample_idx": float(sample_idx),
            "pos_x_m": float(pos[0]),
            "pos_y_m": float(pos[1]),
            "pos_z_m": float(pos[2]),
            "yaw_deg": float(yaw),
            "tick_ms": float(tick_ms),
            "frame": float(frame),
            "ai_agent_b": float(ai),
            "alive_b": 1.0 if alive else 0.0,
        }

    def _witness_append(self, job_id, row):
        nvals = [row[c] for c in WITNESS_NCOL]
        svals = [row[c] for c in WITNESS_SCOL]
        return self.jobs.append_row(job_id, nvals, svals)

    def _op_witness_start(self, op, args_unpacked):
        strs = args_unpacked.get("str") or {}
        nums = args_unpacked.get("num") or {}
        witness_tag = strs.get("witness_tag", "")
        for key in ("center_x_m", "center_z_m", "radius_m", "window_ms"):
            if key not in nums:
                return ("rejected", "bad_args", wire.empty_payload())
        center_x = float(nums["center_x_m"])
        center_z = float(nums["center_z_m"])
        radius = float(nums["radius_m"])
        window_ms = float(nums["window_ms"])
        k_raw = float(nums.get("witness_follow_ticks", float(WITNESS_K_DEFAULT)))
        # Los rechazos salen antes de start_job y de encender el gancho: sin efectos.
        if not (0.0 < radius <= WITNESS_RADIUS_MAX) or not (0.0 < window_ms <= WITNESS_WINDOW_MAX_MS):
            return ("rejected", "bad_args", wire.empty_payload())
        if not k_raw.is_integer() or not (1 <= int(k_raw) <= WITNESS_K_MAX):
            return ("rejected", "bad_args", wire.empty_payload())
        follow_k = int(k_raw)
        job_id = op["op_id"]
        err = self.jobs.start_job(
            self,
            job_id,
            "per_witness",
            list(WITNESS_NCOL),
            list(WITNESS_SCOL),
            WITNESS_PAGE_SIZE,
            WITNESS_MAX_ROWS,
            window_ms + WITNESS_TAIL_MS,
            "stop",
        )
        if err != "":
            return ("rejected", err, wire.empty_payload())
        start_ms = float(self.peer.local_ms())
        self.witness = {
            "job_id": job_id,
            "end_ms": start_ms + window_ms,
            "k": follow_k,
            "cx": center_x,
            "cz": center_z,
            "radius": radius,
            "closed": False,
            "frame": int(self.peer.frame),
            "buf": [],
            "follow": [],
        }
        s = {
            "job": job_id,
            "state": "running",
            "resource": "per_witness",
            "witness_tag": witness_tag,
            "server_epoch": self.epoch,
        }
        n = {
            "start_tick_ms": start_ms,
            "start_frame": float(self.peer.frame),
            "center_x_m": center_x,
            "center_z_m": center_z,
            "radius_m": radius,
            "window_ms": window_ms,
            "witness_follow_ticks": float(follow_k),
        }
        payload = wire.pack_payload(scalars_str=s, scalars_num=n)
        return ("done", "", payload)

    def _tick_witness(self):
        wit = self.witness
        if wit is None:
            return
        jid = wit["job_id"]
        now_ms = float(self.peer.local_ms())
        frame = int(self.peer.frame)
        wit["frame"] = frame
        # 1) capturas de EEInit acumuladas desde el tick anterior; van ANTES del seguimiento: su sample_idx 1 sale en este
        #    mismo tick, el frame siguiente (frames consecutivos 0, 1, ..., K). La fila sample_idx 0 sale en este primer tick
        #    con la posicion, el tick_ms y el frame de EEInit pero con el net_id y el parent_net_id leidos ahora.
        fresh = []
        for cap in wit["buf"]:
            fol = {
                "ent": cap["ent"],
                "class_name": cap["class_name"],
                "net_id": cap["net_id"],
                "parent_net_id": cap["parent_net_id"],
                "pos": cap["pos"],
                "yaw": cap["yaw"],
                "ai": cap["ai"],
                "tick_ms": cap["tick_ms"],
                "frame": cap["frame"],
                "next": 1,
            }
            wit["follow"].append(fol)
            fresh.append(fol)
        wit["buf"] = []
        for fol in fresh:
            ent = fol["ent"]
            alive = self._witness_alive(ent)
            if alive:
                fol["net_id"] = ent["net_id"]
                fol["parent_net_id"] = ent["parent_net_id"]
            else:
                fol["net_id"] = "0:0"
                fol["parent_net_id"] = ""
            row = self._witness_row(
                0, fol["class_name"], fol["net_id"], fol["parent_net_id"],
                fol["pos"], fol["yaw"], fol["tick_ms"], fol["frame"], fol["ai"], alive,
            )
            if not self._witness_append(jid, row):
                return
        # 2) muestras de seguimiento (sample_idx 1..K), incluidas las recien capturadas
        keep = []
        for fol in list(wit["follow"]):
            ent = fol["ent"]
            alive = self._witness_alive(ent)
            if alive:
                fol["pos"] = tuple(ent["pos"])
                fol["yaw"] = float(ent["ori"][0])
                fol["net_id"] = ent["net_id"]
                fol["parent_net_id"] = ent["parent_net_id"]
                fol["ai"] = 1.0 if ent["ai_agent"] else 0.0
            row = self._witness_row(
                fol["next"], fol["class_name"], fol["net_id"], fol["parent_net_id"],
                fol["pos"], fol["yaw"], now_ms, frame, fol["ai"], alive,
            )
            if not self._witness_append(jid, row):
                return
            fol["next"] += 1
            if fol["next"] <= wit["k"]:
                keep.append(fol)
        wit["follow"] = keep
        # 3) vencida la ventana se deja de capturar; acaba cuando no queda seguimiento pendiente
        if not wit["closed"] and now_ms >= wit["end_ms"]:
            wit["closed"] = True
        if wit["closed"] and not wit["follow"]:
            self.jobs.end_job(jid, "done", "")

    def on_job_end(self, job_id, state, reason):
        if self.witness is not None and self.witness["job_id"] == job_id:
            self.witness = None

    def _op_cleanup(self, args_unpacked):
        cleaned_own = len(self.records)
        self._drop_records(list(self.records))
        cleaned_raw = 0
        for net_id in list(self.world.keys()):
            ent = self.world[net_id]
            if ent["owner_uid"] == self.director_uid:
                continue
            cleaned_raw += 1
            self._delete_entity(ent)
        self.records = []
        self.scene_gen = {}
        self.scene_last_op = {}
        self.scene_applied = {}
        self.scene_center = {}
        self.pending_finish.clear()
        payload = wire.pack_payload(
            scalars_num={
                "cleaned_own_n": float(cleaned_own),
                "cleaned_raw_n": float(cleaned_raw),
                "tick_ms": float(self.peer.local_ms()),
                "frame": float(self.peer.frame),
            }
        )
        self._save_state()
        return ("done", "", payload)

    def simulate_world_restart(self):
        self.peer.inst = secrets.token_hex(16)
        self.epoch = self.peer.inst
        keep = {}
        for net_id, ent in self.world.items():
            if ent["owner_uid"] == self.director_uid or ent["persistent"]:
                keep[net_id] = ent
        self.world = keep
        for ent in self.world.values():
            if ent["owner_uid"] != self.director_uid:
                ent["own_b"] = 0
                ent["own_logical_id"] = ""
        self.records = []
        self.scene_gen = {}
        self.scene_last_op = {}
        self.scene_applied = {}
        self.scene_center = {}
        self.pending_finish.clear()
        self._save_state()

    def on_tick(self, timeslice_s):
        self._tick_witness()
        for job_id in list(self.pending_finish):
            left = int(self.pending_finish.get(job_id, 0)) - 1
            if left > 0:
                self.pending_finish[job_id] = left
                continue
            if self.jobs.get_state(job_id) == "running":
                self.jobs.end_job(job_id, "done", "")
            self.pending_finish.pop(job_id, None)

    def on_shutdown(self):
        self.pending_finish.clear()
        self.witness = None


def create_ext(peer, jobs):
    return PersistFakeExt()
