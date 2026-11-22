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
    "per_purge_start",
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

PURGE_PAGE_SIZE = 8
PURGE_MAX_ROWS = 256
PURGE_MAX_MS = 600000.0
PURGE_SCOL = ["phase", "pers_id", "class_name", "parent_pers_id", "owner_uid",
              "result", "net_id", "parent_net_id"]
PURGE_NCOL = ["depth_n", "emit_tick_ms", "lease_age_ms", "lease_limit_ms",
              "max_hp", "health_hp", "confirm_tick_ms"]

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
    "surface_y_m",
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
ZERO_PERS_ID = "0:0:0:0"
NET_ID_RE = re.compile(r"-?[0-9]{1,10}:-?[0-9]{1,10}")


def _surface_y(x, z):
    return 100.0 + 10.0 * math.sin(float(x) / 100.0) * math.cos(float(z) / 100.0)


def _dist2(x1, z1, x2, z2):
    return math.hypot(float(x1) - float(x2), float(z1) - float(z2))


# Espejo de InitSentinelClasses de DSBX_QA_X_Persist.c (MEN-10).
SENTINEL_CLASSES = frozenset({
    "Barrel_Green", "Barrel_Blue", "Barrel_Red", "Barrel_Yellow",
    "WoodenCrate", "SeaChest", "FirstAidKit", "StoneKnife", "SewingKit",
    "OffroadHatchback", "HatchbackWheel", "HatchbackDoors_Driver",
    "SurvivorM_Mirek", "SurvivorF_Eva", "RadarCap_Black", "RadarCap_Brown",
    "Armband_Yellow", "Armband_Blue", "WorkingGloves_Beige",
    "WorkingGloves_Yellow", "WaterBottle", "Compass", "BandageDressing",
    "OrienteeringCompass", "Fireplace",
})
HEALTH_MARK_RATIOS = (0.7325, 0.6150, 0.8450)
ZERO_NET_ID = "0:0"
# Salida acotada de la ocupacion por contencion (BLOQ 6): A se retiene hasta
# acreditar el intento de B o hasta este tope desde su inicio.
CENSUS_HOLD_MAX_MS = 750.0
CENSUS_FINISH_AFTER_ATTEMPT_TICKS = 2
# Presupuesto de captura (espejo de CENSUS_CAPTURE_BUDGET_MS del .c): unico
# limite dentro del bucle de captura tras la instantanea del lease.
CENSUS_CAPTURE_BUDGET_MS = 120000.0


def _is_valid_identity(value, zero):
    text = str(value or "")
    return text != "" and text != zero


def _is_int_str(value):
    # Espejo de IsIntStr del .c: signo opcional y 1..10 cifras ASCII (11 con '-').
    s = str(value or "")
    if not s:
        return False
    if s[0] == "-":
        if len(s) < 2 or len(s) > 11:
            return False
        body = s[1:]
    else:
        if len(s) > 10:
            return False
        body = s
    return all("0" <= c <= "9" for c in body)


def _is_nonzero_pers_id(value):
    # MENOR 14: admite no canonicos como "01:0:0:0" (el .c los admite en la orden);
    # la comparacion sigue siendo textual, como FormatPersId.
    parts = str(value or "").split(":")
    if len(parts) != 4:
        return False
    if not all(_is_int_str(p) for p in parts):
        return False
    nums = [int(p) for p in parts]
    return any(n != 0 for n in nums)


def _identity_matches(net_id, pers_id, qa_net_ids, qa_pers_ids):
    """BLOQ 5: una identidad vacia o cero nunca es coincidencia."""
    if _is_valid_identity(net_id, ZERO_NET_ID) and net_id in qa_net_ids:
        return True
    if _is_valid_identity(pers_id, ZERO_PERS_ID) and pers_id in qa_pers_ids:
        return True
    return False


def _is_health_mark(ent):
    max_hp = float(ent.get("max_hp", 0.0))
    if max_hp <= 0.0:
        return False
    hp = float(ent.get("health_hp", 0.0))
    return any(abs(hp - max_hp * r) <= 1e-2 for r in HEALTH_MARK_RATIOS)


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
        self.census_start_tick = {}
        self.contention_seen_for = {}
        self.census_failed = {}
        self.director_items = []
        self.director_uid = DIRECTOR_UID
        self.director_present = True
        self.director_alive = True
        self.director_inv_readable = True
        self.players_n_override = None
        self.map_objects = []
        self.witness = None
        self.next_pers_seq = 1
        # Duracion simulada de la captura del censo (la fijan los tests); se
        # refleja en capture_wall_ms. Por defecto 0, como hasta ahora.
        self.capture_delay_ms = 0.0
        # P2c: la purga la ordena el runner (trabajo per_purge, deadman stop).
        self.purge_job_id = ""
        self.purge_director_uid = ""
        self.purge_auth_pers = []
        self.purge_auth_class = []
        self.purge_resolved = []
        self.purge_confirm = None
        self.purge_confirm_ent = None
        self.purge_emit_tick = 0.0
        self.purge_pre_n = 0

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
            director_owned = ent.get("owner_uid") == self.director_uid
            if director_owned and ent["net_id"] in (DIRECTOR_JEANS_NET, DIRECTOR_APPLE_NET):
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
                "director_owned": bool(director_owned),
                "born_in_inventory": bool(ent.get("born_in_inventory", False)),
                "own_logical_id": ent["own_logical_id"],
                "own_b": int(ent["own_b"]),
                "scene_id": ent["scene_id"],
                "area_id": ent["area_id"],
            })
        qa_provenance = set(self.qa_net_ids) | set(self.raw_net_ids)
        for rec in self.records:
            ent = rec.get("ent")
            if ent is not None and ent.get("net_id"):
                qa_provenance.add(ent["net_id"])
        data = {
            "director_uid": self.director_uid,
            "next_net_low": self.next_net_low,
            "next_pers_seq": self.next_pers_seq,
            "qa_net_ids": sorted(qa_provenance),
            "raw_net_ids": sorted(self.raw_net_ids),
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
        try:
            self.next_pers_seq = max(int(data.get("next_pers_seq", 1)), 1)
        except (TypeError, ValueError):
            self.next_pers_seq = 1
        saved_qa = data.get("qa_net_ids")
        saved_raw = data.get("raw_net_ids")
        qa_provenance = set()
        raw_provenance = set()
        if isinstance(saved_qa, list):
            qa_provenance = {str(v) for v in saved_qa if str(v or "")}
        if isinstance(saved_raw, list):
            raw_provenance = {str(v) for v in saved_raw if str(v or "")}
        qa_provenance |= raw_provenance
        loaded = data.get("entities")
        if not isinstance(loaded, list):
            return False
        for raw in loaded:
            if not isinstance(raw, dict):
                continue
            director_owned = bool(raw.get("director_owned"))
            if not raw.get("persistent") and not director_owned:
                continue
            saved_net = str(raw.get("net_id") or "")
            if saved_net in self.world:
                continue
            saved_pers = str(raw.get("pers_id") or "")
            used_pers = {e.get("pers_id") for e in self.world.values()}
            if not _is_nonzero_pers_id(saved_pers) or saved_pers in used_pers:
                saved_pers = self._alloc_pers_id()
            ent = self._add_entity(
                net_id=saved_net,
                pers_id=saved_pers,
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
                persistent=bool(raw.get("persistent", False)),
                born_in_inventory=bool(raw.get("born_in_inventory", False)),
                own_logical_id="",
                own_b=0,
                scene_id=str(raw.get("scene_id") or ""),
                area_id=str(raw.get("area_id") or ""),
            )
            ent["alive"] = bool(raw.get("alive", True))
            ent["ai_agent"] = bool(raw.get("ai_agent", False))
            if ent["net_id"] in raw_provenance:
                self.raw_net_ids.add(ent["net_id"])
            if ent["net_id"] in qa_provenance:
                self.qa_net_ids.add(ent["net_id"])
        return True

    def init(self, peer, jobs):
        self.peer = peer
        self.jobs = jobs
        self.epoch = peer.inst
        self._build_director()
        self._build_map()
        self.raw_net_ids.clear()
        self.qa_net_ids.clear()
        if self._load_state():
            self.records = []
            self.scene_gen = {}
            self.scene_last_op = {}
            self.scene_applied = {}
            self.scene_center = {}
            self.pending_finish.clear()
            self.census_start_tick.clear()
            self.contention_seen_for.clear()
            self.census_failed.clear()
        self.director_items = [
            net_id for net_id, ent in self.world.items()
            if ent.get("owner_uid") == self.director_uid and ent.get("alive")
        ]

    def handles(self, verb, role):
        return role == "server" and verb in SERVER_VERBS

    def _build_director(self):
        jeans = self._add_entity(
            net_id=DIRECTOR_JEANS_NET,
            pers_id=self._alloc_pers_id(),
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
            pers_id=self._alloc_pers_id(),
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

    def _alloc_pers_id(self):
        used = {ent.get("pers_id") for ent in self.world.values()}
        seq = int(getattr(self, "next_pers_seq", 1) or 1)
        if seq < 1:
            seq = 1
        while ("%d:0:0:0" % seq) in used:
            seq += 1
        self.next_pers_seq = seq + 1
        return "%d:0:0:0" % seq

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
            "born_in_inventory": bool(kw.get("born_in_inventory", False)),
            "own_logical_id": kw.get("own_logical_id", ""),
            "own_b": int(kw.get("own_b", 0)),
            "scene_id": kw.get("scene_id", ""),
            "area_id": kw.get("area_id", ""),
        }
        return ent

    def _health_at_creation(self, cname, ratio):
        """(max_hp, health_hp, mark_b) de lo que crea el QA, como lo lee la sonda justo despues de crearlo y marcarlo
        (ApplyQaHealthMark del .c: SetHealth directo y relectura). mark_b = no se pidio marca o la relectura la
        confirma. Una clase sin sistema de daño (NO_DAMAGE_SYSTEM_CLASSES) no tiene salud que leer: -1/-1 y, con marca
        pedida, mark_b = False; en el motor crearla con el QA no esta soportado (GetMaxHealth tira la excepcion)."""
        if cname in NO_DAMAGE_SYSTEM_CLASSES:
            return NO_HEALTH, NO_HEALTH, ratio <= 0.0
        hp = DEFAULT_MAX_HP * ratio if ratio > 0.0 else DEFAULT_MAX_HP
        return DEFAULT_MAX_HP, hp, True

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

    def _children_index(self):
        """parent_net_id -> hijos vivos, en el orden de recorrido de siempre (mundo y despues mapa)."""
        index = {}
        for ent in list(self.world.values()) + self.map_objects:
            if ent["alive"] and ent["parent_net_id"] != "":
                index.setdefault(ent["parent_net_id"], []).append(ent)
        return index

    def _preorder_children(self, net_id, index=None):
        # Hijos de net_id en PREORDER (mundo y mapa), como EnumerateInventory(PREORDER) menos la raiz. El censo del
        # modo 1 pasa un indice construido una vez: recorrer el mundo entero en cada nivel y en cada fila lo hacia
        # cuadratico con miles de raices, y con la guarda de lease por fila de S-persist el reloj real del fake lo
        # hacia caducar a mitad de la captura (en el motor la captura va en un frame, con GetTickTime constante).
        if net_id == "":
            return []
        if index is None:
            index = self._children_index()
        out = []
        for ent in index.get(net_id, []):
            out.append(ent)
            out.extend(self._preorder_children(ent["net_id"], index))
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

    def _retained_net_ids(self, recs):
        """Contenedores con descendientes ajenos/desconocidos + sus ancestros."""
        deletable = {rec["ent"]["net_id"]: rec for rec in recs}
        retain = {}
        for rec in recs:
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
        return retain

    def _reapply_reset_with_retention(self, scene_id):
        """MEN 7/8: guarda de lease en cada borrado; False si caduca a mitad."""
        old_recs = [
            rec for rec in self.records
            if rec["scene_id"] == scene_id and rec["server_epoch"] == self.epoch
        ]
        if not old_recs:
            return True
        retain = self._retained_net_ids(old_recs)
        for rec in list(old_recs):
            ent = rec["ent"]
            if rec["parent_id"] != "" and not retain.get(ent["net_id"]):
                if not self.peer.lease_valid():
                    return False
                self._drop_records([rec])
        for rec in list(old_recs):
            ent = rec["ent"]
            if rec["parent_id"] == "" and not retain.get(ent["net_id"]):
                if not self.peer.lease_valid():
                    return False
                self._drop_records([rec])
        return True

    def _census_row(self, ent, in_radius, deep=False, index=None):
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
            "inv_children_n": float(len(self._preorder_children(ent["net_id"], index)) if deep else self._children_count(ent["net_id"])),
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
        # MEN 1: como el .c, per_purge_start es un verbo con efecto y mira el lease
        # antes de aceptar la orden (no despacha antes de la guarda E1).
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        if verb == "per_purge_start":
            return self._op_purge_start(op, args_unpacked)
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
        wanted_uid = strs.get("director_uid", "")
        players_n = int(self.players_n_override) if self.players_n_override is not None else 1
        director_uid = ""
        present = 0
        alive = 0
        readable = 0
        if wanted_uid == "":
            if players_n == 1:
                director_uid = self.director_uid
                present = 1 if self.director_present else 0
                alive = 1 if (self.director_present and self.director_alive) else 0
                readable = 1 if (self.director_present and self.director_inv_readable) else 0
        else:
            director_uid = wanted_uid
            if wanted_uid == self.director_uid and self.director_present:
                present = 1
                alive = 1 if self.director_alive else 0
                readable = 1 if self.director_inv_readable else 0
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
            "director_uid": director_uid,
        }
        if lifecycle == "shutdown":
            s["shutdown_marker"] = "1"
        elif lifecycle == "startup":
            s["startup_marker"] = "1"
        n = {
            "players_n": float(players_n),
            "tick_ms": float(self.peer.local_ms()),
            "frame": float(self.peer.frame),
            "registered_total_n": float(len(self.records)),
            "scenes_count_n": float(len(self.scene_gen)),
            "director_present_b": float(present),
            "director_alive_b": float(alive),
            "director_inv_readable_b": float(readable),
            "director_inv_count_n": float(len(self._director_tree_entities())) if present else 0.0,
        }
        payload = wire.pack_payload(
            scalars_str=s,
            scalars_num=n,
            num_cols=["gen_n", "own_alive_n"],
            str_cols=["scene_id", "last_op_id"],
            row_dicts=rows,
        )
        return ("done", "", payload)

    def _director_tree_entities(self):
        roots = [
            ent for ent in self.world.values()
            if ent.get("alive") and ent.get("owner_uid") == self.director_uid
        ]
        index = self._children_index()
        out = []
        seen = set()
        for root in roots:
            if root["net_id"] in seen:
                continue
            seen.add(root["net_id"])
            out.append(root)
            for desc in self._preorder_children(root["net_id"], index):
                if desc["net_id"] not in seen:
                    seen.add(desc["net_id"])
                    out.append(desc)
        return out

    def _root_owner_uid(self, ent):
        cur = ent
        seen = set()
        while cur is not None:
            nid = cur.get("net_id")
            if nid in seen:
                break
            seen.add(nid)
            if cur.get("owner_uid"):
                return cur["owner_uid"]
            parent_nid = cur.get("parent_net_id") or ""
            if not parent_nid:
                break
            cur = self.world.get(parent_nid)
        return ""

    def _subtree_born_in_inventory(self, ent):
        # MENOR 15: espejo del .c; todo registro del subarbol que se mueve a un
        # jugador debe haber nacido en inventario.
        if not ent.get("born_in_inventory"):
            return False
        for desc in self._preorder_children(ent["net_id"], self._children_index()):
            if not desc.get("born_in_inventory"):
                return False
        return True

    def _root_entity(self, ent):
        cur = ent
        seen = set()
        while cur is not None:
            nid = cur.get("net_id")
            if nid in seen:
                break
            seen.add(nid)
            parent_nid = cur.get("parent_net_id") or ""
            if not parent_nid:
                return cur
            nxt = self.world.get(parent_nid)
            if nxt is None:
                return cur
            cur = nxt
        return cur

    def _purge_depth(self, ent):
        # MENOR 14: como PurgeDepthOf del .c, el director cuenta como padre virtual
        # (sus hijos directos dan 1, los nietos 2), no 0.
        depth = 1
        cur = ent
        seen = set()
        while cur is not None:
            nid = cur.get("net_id")
            if nid in seen:
                break
            seen.add(nid)
            parent_nid = cur.get("parent_net_id") or ""
            if not parent_nid:
                break
            parent = self.world.get(parent_nid)
            if parent is None:
                break
            depth += 1
            cur = parent
        return depth

    def _purge_parent_pers(self, ent):
        parent_nid = ent.get("parent_net_id") or ""
        parent = self.world.get(parent_nid)
        return parent["pers_id"] if parent is not None else ZERO_PERS_ID

    def _purge_parent_net(self, ent):
        return ent.get("parent_net_id") or ""

    def _purge_append(self, phase, ent, result, emit_tick=0.0, lease_age=0.0, lease_limit=0.0, confirm_tick=0.0):
        # MENOR 13: owner_uid medido por la raiz del arbol, no una constante de la orden.
        owner_uid = self.director_uid if self._root_owner_uid(ent) == self.director_uid else ""
        row = {
            "phase": phase,
            "pers_id": ent.get("pers_id", ZERO_PERS_ID),
            "class_name": ent.get("class_name", ""),
            "parent_pers_id": self._purge_parent_pers(ent),
            "owner_uid": owner_uid,
            "result": result,
            "net_id": ent.get("net_id", ""),
            "parent_net_id": self._purge_parent_net(ent),
            "depth_n": float(self._purge_depth(ent)),
            "emit_tick_ms": float(emit_tick),
            "lease_age_ms": float(lease_age),
            "lease_limit_ms": float(lease_limit),
            "max_hp": float(ent.get("max_hp", 0.0)),
            "health_hp": float(ent.get("health_hp", 0.0)),
            "confirm_tick_ms": float(confirm_tick),
        }
        numeric = [row[name] for name in PURGE_NCOL]
        textual = [row[name] for name in PURGE_SCOL]
        return self.jobs.append_row(self.purge_job_id, numeric, textual)

    def _purge_authorized_index(self, pers_id):
        for idx, pid in enumerate(self.purge_auth_pers):
            if pid == pers_id:
                return idx
        return -1

    def _purge_count(self, tree, pers_id):
        return sum(1 for ent in tree if ent.get("pers_id") == pers_id)

    def _purge_subtree(self, cand):
        out = [cand]
        index = self._children_index()
        out.extend(self._preorder_children(cand["net_id"], index))
        return out

    def _purge_tree_eligible(self, cand, tree):
        if self._root_owner_uid(cand) != self.director_uid:
            return False
        pers = cand.get("pers_id", "")
        if not _is_nonzero_pers_id(pers):
            return False
        idx = self._purge_authorized_index(pers)
        if idx < 0 or self.purge_auth_class[idx] != cand.get("class_name"):
            return False
        if self._purge_count(tree, pers) != 1:
            return False
        for desc in self._purge_subtree(cand):
            dp = desc.get("pers_id", "")
            if not _is_nonzero_pers_id(dp):
                return False
            di = self._purge_authorized_index(dp)
            if di < 0 or self.purge_auth_class[di] != desc.get("class_name"):
                return False
            if self._purge_count(tree, dp) != 1:
                return False
            if self._root_owner_uid(desc) != self.director_uid:
                return False
        return True

    def _purge_pick_leaf(self, cand, tree):
        best = None
        best_depth = -1
        for desc in self._purge_subtree(cand):
            has_child = any(
                other is not desc and other.get("parent_net_id") == desc["net_id"]
                for other in tree
            )
            if has_child:
                continue
            depth = self._purge_depth(desc)
            if depth > best_depth:
                best_depth = depth
                best = desc
        return best

    def _op_purge_start(self, op, args_unpacked):
        strs = args_unpacked.get("str") or {}
        expect_epoch = strs.get("expect_epoch", "")
        director_uid = strs.get("director_uid", "")
        rows = args_unpacked.get("rows") or []
        scol_in = list(args_unpacked.get("scol") or [])
        ncol_in = list(args_unpacked.get("ncol") or [])
        if expect_epoch != self.epoch:
            return ("rejected", "stale_epoch", wire.empty_payload())
        if len(rows) < 1 or len(rows) > 16:
            return ("rejected", "bad_args", wire.empty_payload())
        if "pers_id" not in scol_in or "class_name" not in scol_in:
            return ("rejected", "bad_args", wire.empty_payload())
        if ncol_in:
            return ("rejected", "bad_args", wire.empty_payload())
        auth_pers = []
        auth_class = []
        for row in rows:
            pid = str(row.get("pers_id") or "")
            cls = str(row.get("class_name") or "")
            if not _is_nonzero_pers_id(pid) or not cls or pid in auth_pers:
                return ("rejected", "bad_args", wire.empty_payload())
            auth_pers.append(pid)
            auth_class.append(cls)
        if not director_uid or director_uid != self.director_uid:
            return ("rejected", "director_not_ready", wire.empty_payload())
        if not (self.director_present and self.director_alive and self.director_inv_readable):
            return ("rejected", "director_not_ready", wire.empty_payload())
        job_name = str(op.get("op_id") or "")
        err = self.jobs.start_job(self, job_name, "per_purge", list(PURGE_NCOL), list(PURGE_SCOL), PURGE_PAGE_SIZE, PURGE_MAX_ROWS, PURGE_MAX_MS, "stop")
        if err != "":
            return ("rejected", err, wire.empty_payload())
        self.purge_job_id = job_name
        self.purge_director_uid = director_uid
        self.purge_auth_pers = auth_pers
        self.purge_auth_class = auth_class
        self.purge_resolved = [0 for _ in auth_pers]
        self.purge_confirm = None
        tree = self._director_tree_entities()
        self.purge_pre_n = len(tree)
        if self.purge_pre_n + len(auth_pers) > PURGE_MAX_ROWS:
            self.jobs.end_job(self.purge_job_id, "failed", "rows_cap")
        else:
            for ent in tree:
                if not self._purge_append("pre", ent, ""):
                    break
        payload = wire.pack_payload(
            scalars_str={
                "job": job_name,
                "state": self.jobs.get_state(job_name),
                "resource": "per_purge",
            },
            scalars_num={"pre_n": float(self.purge_pre_n)},
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

        ncol_in = list(args_unpacked.get("ncol") or [])
        scol_in = list(args_unpacked.get("scol") or [])
        required_s = {"logical_id", "parent_id", "cat", "class_name", "slot_name"}
        required_n = {"req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"}
        if not required_s.issubset(set(scol_in)) or not required_n.issubset(set(ncol_in)):
            return ("rejected", "bad_args", wire.empty_payload())
        if len(rows_in) < 1 or len(rows_in) > 12:
            return ("rejected", "bad_args", wire.empty_payload())

        if not self._reapply_reset_with_retention(scene_id):
            return ("error", "lease_expired", wire.empty_payload())
        # MEN 7: lo retenido de la generacion anterior no se duplica: sus
        # filas se saltan con resultado parcial explicito y los padres se
        # resuelven contra la entidad retenida de su generacion.
        retained_by_lid = {
            rec["logical_id"]: rec["ent"]
            for rec in self.records
            if rec["scene_id"] == scene_id and rec["server_epoch"] == self.epoch
        }
        retained_skipped = 0
        persistent = fault == "omit_nopersistency_flag"
        area_id = SCENE_AREA.get(scene_id, "area_a")
        now_ms = float(self.peer.local_ms())
        frame = int(self.peer.frame)
        created_roots = 0
        created_children = 0
        out_rows = []
        local = dict(retained_by_lid)
        root_positions = []
        for row in rows_in:
            if not self.peer.lease_valid():
                return ("error", "lease_expired", wire.empty_payload())
            lid = str(row.get("logical_id", ""))
            if lid in retained_by_lid:
                # Fila retenida: no se crea duplicado ni registro nuevo.
                retained_skipped += 1
                rent = retained_by_lid[lid]
                out_rows.append({
                    "logical_id": lid, "class_name": rent["class_name"], "net_id": rent["net_id"],
                    "obs_loc_kind": rent["loc_kind"], "obs_parent_net_id": rent["parent_net_id"], "obs_slot_name": rent["slot_name"],
                    "ok_b": 0.0, "alive_b": 1.0 if rent["alive"] else 0.0, "ai_agent_b": 1.0 if rent["ai_agent"] else 0.0,
                    "req_y_m": float(rent["pos"][1]), "q9_x_m": float(rent["pos"][0]), "q9_y_m": float(rent["pos"][1]), "q9_z_m": float(rent["pos"][2]),
                    "q9_dx_m": 0.0, "q9_dy_m": 0.0, "q9_dz_m": 0.0, "q9_err_3d_m": 0.0,
                    "q9_yaw_deg": float(rent["ori"][0]), "q9_pitch_deg": float(rent["ori"][1]), "q9_roll_deg": float(rent["ori"][2]),
                    "max_hp": float(rent["max_hp"]), "health_hp": float(rent["health_hp"]), "spawn_tick_ms": float(rent["spawn_tick_ms"]),
                    "health_mark_b": 0.0,
                })
                continue
            pid = str(row.get("parent_id", ""))
            cat = str(row.get("cat", ""))
            cname = str(row.get("class_name", ""))
            sname = str(row.get("slot_name", ""))
            born_in_inventory = False
            rx = float(row.get("req_x_m", 0.0))
            rz = float(row.get("req_z_m", 0.0))
            ryaw = float(row.get("req_yaw_deg", 0.0))
            ratio = float(row.get("health_mark_ratio", 0.0))
            max_hp, hp, mark_b = self._health_at_creation(cname, ratio)
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
                    # MEN-13 (espejo del .c): fila fallida sin creacion, sin salud observada.
                    out_rows.append({
                        "logical_id": lid, "class_name": cname, "net_id": "",
                        "obs_loc_kind": "", "obs_parent_net_id": "", "obs_slot_name": "",
                        "ok_b": 0.0, "alive_b": 0.0, "ai_agent_b": 0.0,
                        "req_y_m": 0.0, "q9_x_m": 0.0, "q9_y_m": 0.0, "q9_z_m": 0.0,
                        "q9_dx_m": 0.0, "q9_dy_m": 0.0, "q9_dz_m": 0.0, "q9_err_3d_m": 0.0,
                        "q9_yaw_deg": 0.0, "q9_pitch_deg": 0.0, "q9_roll_deg": 0.0,
                        "max_hp": 0.0, "health_hp": 0.0, "spawn_tick_ms": now_ms,
                        "health_mark_b": 0.0,
                    })
                    continue
                born_in_inventory = bool(
                    cat == "child_attach" and sname == "Gloves" and parent.get("cat") == "actor"
                )
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
                pers_id=self._alloc_pers_id(),
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
                born_in_inventory=born_in_inventory,
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
                "mark_b": 1.0 if mark_b else 0.0,
                "born_in_inventory": born_in_inventory,
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
                "health_mark_b": 1.0 if mark_b else 0.0,
            })
        if root_positions:
            cx = sum(p[0] for p in root_positions) / float(len(root_positions))
            cz = sum(p[1] for p in root_positions) / float(len(root_positions))
            self.scene_center[scene_id] = (cx, cz)
        ok_n = sum(1 for r in out_rows if float(r.get("ok_b", 0.0)) == 1.0)
        if retained_skipped and ok_n < len(out_rows):
            # MEN 7: parcial explicito por retencion, no fallo de creacion.
            apply_status = "partial" if ok_n > 0 else "failed"
            apply_reason = "retained_prior_generation"
        elif ok_n == 0:
            apply_status, apply_reason = "failed", "creation_failed"
        elif ok_n < len(out_rows):
            apply_status, apply_reason = "partial", "creation_failed"
        else:
            apply_status, apply_reason = "ok", ""
        s = {
            "apply_status": apply_status,
            "reason": apply_reason,
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
            "health_hp", "spawn_tick_ms", "health_mark_b",
        ]
        scol = [
            "logical_id", "class_name", "net_id", "obs_loc_kind",
            "obs_parent_net_id", "obs_slot_name",
        ]
        self.scene_gen[scene_id] = gen_n
        self.scene_last_op[scene_id] = scene_op_id
        self.has_applied = True
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
                    if not self.peer.lease_valid():
                        return ("error", "lease_expired", wire.empty_payload())
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

        retain = self._retained_net_ids(scene_recs)

        # MEN 8: guarda en cada efecto; la caducidad se propaga como error,
        # nunca como done/ok con las filas pendientes sin procesar.
        deleted = 0
        for rec in list(scene_recs):
            ent = rec["ent"]
            if rec["parent_id"] != "" and not retain.get(ent["net_id"]):
                if not self.peer.lease_valid():
                    return ("error", "lease_expired", wire.empty_payload())
                self._drop_records([rec])
                deleted += 1
        for rec in list(scene_recs):
            ent = rec["ent"]
            if rec["parent_id"] == "" and not retain.get(ent["net_id"]):
                if not self.peer.lease_valid():
                    return ("error", "lease_expired", wire.empty_payload())
                self._drop_records([rec])
                deleted += 1

        retained_recs = [
            rec for rec in scene_recs
            if retain.get(rec["ent"]["net_id"])
        ]
        deletable_ids = {rec["ent"]["net_id"] for rec in scene_recs}
        for rec in retained_recs:
            ent = rec["ent"]
            survivors = 0
            for desc in self._descendants(ent["net_id"]):
                dnid = desc["net_id"]
                if dnid not in deletable_ids:
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
        wanted_uid = strs.get("director_uid", "")
        if expect_epoch != self.epoch:
            return ("rejected", "stale_epoch", wire.empty_payload())
        rec = self._record_by(scene_id, logical_id)
        if rec is None:
            return ("rejected", "unknown_entity", wire.empty_payload())
        ent = rec["ent"]
        if action == "move_to_director":
            if not wanted_uid:
                return ("rejected", "bad_args", wire.empty_payload())
            if wanted_uid != self.director_uid:
                return ("rejected", "director_not_ready", wire.empty_payload())
            if not (self.director_present and self.director_alive and self.director_inv_readable):
                return ("rejected", "director_not_ready", wire.empty_payload())
            if not self._subtree_born_in_inventory(ent):
                return ("rejected", "bad_args", wire.empty_payload())
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
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
            # MENOR 14: como el .c, cualquier contenedor de un jugador (cualquier
            # Man), no solo el director.
            tgt_root = self._root_entity(tgt_ent)
            is_player_root = bool(
                tgt_root is not None
                and (tgt_root.get("cat") == "actor" or tgt_root.get("owner_uid"))
            )
            if is_player_root and not self._subtree_born_in_inventory(ent):
                return ("rejected", "bad_args", wire.empty_payload())
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

    def _spawn_raw_area_for(self, x_value, z_value):
        found = ""
        for area_name, centre in AREA_CENTERS.items():
            if _dist2(x_value, z_value, centre[0], centre[1]) <= 60.0:
                found = area_name
                break
        return found

    def _spawn_raw_plan(self, mode, target_net, target_scene, target_parent, class_name, ground_pos, ground_ori, area_name):
        plan = {
            "loc_kind": "ground",
            "parent_net_id": "",
            "parent_class": "",
            "slot_name": "",
            "pos": ground_pos,
            "ori": ground_ori,
            "area_id": area_name,
        }
        if mode != "foreign_in_container":
            return plan, None
        if target_net:
            if not NET_ID_RE.fullmatch(target_net):
                return None, ("rejected", "bad_args", wire.empty_payload())
            holder = self._find_by_net_id(target_net)
            if holder is None:
                return None, ("rejected", "target_not_found", wire.empty_payload())
            located = self._find_free_location(holder, class_name)
            if located is None or located[0] is not holder:
                return None, ("rejected", "no_cargo_space", wire.empty_payload())
            plan.update({
                "loc_kind": "cargo",
                "parent_net_id": holder["net_id"],
                "parent_class": holder["class_name"],
                "slot_name": located[1],
                "pos": holder["pos"],
                "ori": holder["ori"],
                "area_id": holder["area_id"],
            })
            return plan, None
        record = self._record_by(target_scene, target_parent)
        if record is None:
            return None, ("rejected", "unknown_entity", wire.empty_payload())
        holder = record["ent"]
        plan.update({
            "loc_kind": "cargo",
            "parent_net_id": holder["net_id"],
            "parent_class": holder["class_name"],
            "slot_name": "Cargo:0:1:0",
            "pos": holder["pos"],
            "ori": holder["ori"],
            "area_id": holder["area_id"],
        })
        return plan, None

    def _op_spawn_raw(self, args_unpacked):
        text_args = args_unpacked.get("str") or {}
        num_args = args_unpacked.get("num") or {}
        label = text_args.get("tag", "")
        mode = text_args.get("mode", "")
        class_name = text_args.get("class_name", "")
        child_class = text_args.get("child_cargo_class", "")
        if not label or not class_name:
            return self._bad_args_reply()
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        ratio = float(num_args.get("health_mark_ratio", 0.0))
        health = self._health_at_creation(class_name, ratio)
        stamp = float(self.peer.local_ms())
        x_value = float(num_args.get("x_m", 0.0))
        z_value = float(num_args.get("z_m", 0.0))
        yaw_value = float(num_args.get("yaw_deg", 0.0))
        ground_pos = (x_value, _surface_y(x_value, z_value), z_value)
        ground_ori = (yaw_value, 0.0, 0.0)
        plan, refusal = self._spawn_raw_plan(mode, text_args.get("target_net_id", ""), text_args.get("target_scene_id", ""), text_args.get("target_parent_id", ""), class_name, ground_pos, ground_ori, self._spawn_raw_area_for(x_value, z_value))
        if refusal is not None:
            return refusal
        entity_data = {
            "net_id": self._alloc_net_id(),
            "pers_id": self._alloc_pers_id(),
            "class_name": class_name,
            "cat": "raw",
            "loc_kind": plan["loc_kind"],
            "parent_net_id": plan["parent_net_id"],
            "parent_class": plan["parent_class"],
            "slot_name": plan["slot_name"],
            "owner_uid": "",
            "pos": plan["pos"],
            "ori": plan["ori"],
            "max_hp": health[0],
            "health_hp": health[1],
            "spawn_tick_ms": stamp,
            "persistent": mode == "persistent_control",
            "own_logical_id": "",
            "own_b": 0,
            "area_id": plan["area_id"],
        }
        ent = self._add_entity(**entity_data)
        self.raw_net_ids.add(ent["net_id"])
        made_children = 0
        if mode == "persistent_control" and child_class:
            child_hp = DEFAULT_MAX_HP * ratio if ratio > 0.0 else DEFAULT_MAX_HP
            child_data = {
                "net_id": self._alloc_net_id(),
                "pers_id": self._alloc_pers_id(),
                "class_name": child_class,
                "cat": "raw_child",
                "loc_kind": "cargo",
                "parent_net_id": ent["net_id"],
                "parent_class": class_name,
                "slot_name": "Cargo:0:0:0",
                "owner_uid": "",
                "pos": plan["pos"],
                "ori": plan["ori"],
                "max_hp": DEFAULT_MAX_HP,
                "health_hp": child_hp,
                "spawn_tick_ms": stamp,
                "persistent": True,
                "own_logical_id": "",
                "own_b": 0,
                "area_id": plan["area_id"],
            }
            child_ent = self._add_entity(**child_data)
            self.raw_net_ids.add(child_ent["net_id"])
            made_children = 1
        text_out = {
            "spawn_status": "ok",
            "tag": label,
            "class_name": class_name,
            "net_id": ent["net_id"],
            "pers_id": ent["pers_id"],
            "obs_loc_kind": ent["loc_kind"],
            "obs_parent_net_id": ent["parent_net_id"],
            "obs_slot_name": ent["slot_name"],
        }
        num_out = {
            "pos_x_m": float(ent["pos"][0]),
            "pos_y_m": float(ent["pos"][1]),
            "pos_z_m": float(ent["pos"][2]),
            "yaw_deg": float(ent["ori"][0]),
            "pitch_deg": float(ent["ori"][1]),
            "roll_deg": float(ent["ori"][2]),
            "max_hp": float(ent["max_hp"]),
            "health_hp": float(ent["health_hp"]),
            "child_count_n": float(made_children),
            "tick_ms": stamp,
            "frame": float(self.peer.frame),
            "health_mark_b": 1.0 if health[2] else 0.0,
        }
        result_payload = wire.pack_payload(scalars_str=text_out, scalars_num=num_out)
        self._save_state()
        return ("done", "", result_payload)


    def _bad_args_reply(self):
        word = "rejected"
        return (word, "bad_args", wire.empty_payload())

    def _census_all_rows(self, mid_x, mid_z, radius, want_director):
        centre = (mid_x, _surface_y(mid_x, mid_z), mid_z)
        children = self._children_index()
        collected = []
        candidates = list(self.world.values()) + self.map_objects
        for entity in candidates:
            is_root = entity["parent_net_id"] == ""
            if not entity["alive"] or not is_root or entity["owner_uid"] == self.director_uid:
                continue
            d3 = math.sqrt(
                (float(entity["pos"][0]) - centre[0]) ** 2
                + (float(entity["pos"][1]) - centre[1]) ** 2
                + (float(entity["pos"][2]) - centre[2]) ** 2
            )
            if d3 > radius:
                continue
            collected.append(self._census_row(entity, 1, deep=True, index=children))
            for descendant in self._preorder_children(entity["net_id"], children):
                collected.append(self._census_row(descendant, 1, deep=True, index=children))
        if want_director == 1:
            for entity in self._director_tree_entities():
                collected.append(self._census_row(entity, 1, deep=True, index=children))
        return collected

    def _census_plain_rows(self, mid_x, mid_z, radius, want_director, area_name):
        collected = []
        if want_director == 1:
            for entity in self._director_tree_entities():
                collected.append(self._census_row(entity, 1))
        for entity in self.world.values():
            if not entity["alive"]:
                continue
            if self._root_owner_uid(entity) == self.director_uid:
                continue
            inside = _dist2(entity["pos"][0], entity["pos"][2], mid_x, mid_z) <= radius
            if inside:
                collected.append(self._census_row(entity, 1))
                continue
            own_creature = entity["own_b"] == 1 and entity["cat"] in ("infected", "animal")
            if own_creature and entity["area_id"] == area_name:
                collected.append(self._census_row(entity, 0))
        return collected

    def _census_capture_rows(self, job_name, rows_to_write, column_names):
        delay = float(getattr(self, "capture_delay_ms", 0.0) or 0.0)
        if hasattr(self.peer, "lease_age_ms"):
            age_at_start = float(self.peer.lease_age_ms())
        else:
            age_at_start = 0.0 if self.peer.lease_valid() else 1.0e9
        limit = float(getattr(self.peer, "lease_ms", 3000) or 3000)
        if age_at_start > limit:
            return 0, "lease_expired", delay
        written = 0
        total = len(rows_to_write)
        problem = ""
        for position, row_data in enumerate(rows_to_write, start=1):
            elapsed = delay * float(position) / float(total) if total else delay
            if elapsed > CENSUS_CAPTURE_BUDGET_MS:
                problem = "capture_budget_exceeded"
                break
            numeric = [row_data[name] for name in column_names]
            textual = [row_data[name] for name in CENSUS_SCOL]
            if not self.jobs.append_row(job_name, numeric, textual):
                problem = "capture_truncated"
                break
            written = position
        if not problem and written < total:
            problem = "capture_truncated"
        return written, problem, delay

    def _op_census_start(self, op, args_unpacked, fault):
        text_args = args_unpacked.get("str") or {}
        num_args = args_unpacked.get("num") or {}
        area_label = text_args.get("area_tag", "")
        if not area_label:
            return self._bad_args_reply()
        all_value = float(num_args.get("select_all_entityai_b", 0.0))
        radius_value = float(num_args.get("radius_m", 60.0))
        if all_value not in (0.0, 1.0):
            return self._bad_args_reply()
        all_mode = int(all_value)
        if all_mode == 1 and not 0.0 < radius_value <= CENSUS_ALL_RADIUS_MAX:
            return self._bad_args_reply()
        mid_x = float(num_args.get("center_x_m", 0.0))
        mid_z = float(num_args.get("center_z_m", 0.0))
        want_director = int(round(float(num_args.get("include_director_b", 0.0))))
        wanted_uid = text_args.get("director_uid", "")
        if want_director == 1 and not wanted_uid:
            return self._bad_args_reply()
        if self.purge_job_id and self.jobs.get_state(self.purge_job_id) == "running":
            return ("rejected", "purge_pending", wire.empty_payload())
        # MENOR 14: como el .c, con include_director_b=1 se censa al director
        # presente e inventario legible aunque este muerto (alive_b queda 0).
        director_ok = bool(
            wanted_uid
            and wanted_uid == self.director_uid
            and self.director_present
            and self.director_inv_readable
        )
        if fault == "drop_ctrl_pre_restart":
            for entity in list(self.world.values()):
                if entity["class_name"] == "Barrel_Yellow" and entity["area_id"] == "area_c":
                    self._delete_entity(entity)
        job_name = op["op_id"]
        holder = self.jobs.held_resources.get("per_census")
        if holder and holder != job_name:
            self.contention_seen_for[holder] = float(self.peer.local_ms())
        if fault == "census_resource_bypass":
            self.jobs.held_resources.pop("per_census", None)
        chosen_columns = CENSUS_NCOL_ALL if all_mode == 1 else CENSUS_NCOL
        start_error = self.jobs.start_job(self, job_name, "per_census", list(chosen_columns), list(CENSUS_SCOL), CENSUS_PAGE_SIZE, CENSUS_MAX_ROWS, CENSUS_MAX_MS, "stop")
        if start_error != "":
            return ("rejected", start_error, wire.empty_payload())
        area_name = area_label.split(":", 1)[1] if ":" in area_label else area_label
        snap_stamp = float(self.peer.local_ms())
        snap_frame_value = int(self.peer.frame)
        want_director_rows = want_director if director_ok else 0
        if all_mode == 1:
            rows_found = self._census_all_rows(mid_x, mid_z, radius_value, want_director_rows)
        else:
            rows_found = self._census_plain_rows(mid_x, mid_z, radius_value, want_director_rows, area_name)
        written, problem, delay = self._census_capture_rows(job_name, rows_found, chosen_columns)
        if problem:
            self.census_failed[job_name] = problem
        if delay and hasattr(self.peer, "now"):
            self.peer.now = float(self.peer.now) + delay
        text_out = {
            "job": job_name,
            "state": "running",
            "resource": "per_census",
            "area_tag": area_label,
            "server_epoch": self.epoch,
            "director_uid": wanted_uid,
        }
        num_out = {
            "snap_tick_ms": snap_stamp,
            "capture_wall_ms": float(delay),
            "snap_frame": float(snap_frame_value),
            "rows_captured_n": float(written),
            "center_x_m": mid_x,
            "center_z_m": mid_z,
            "radius_m": radius_value,
            "director_present_b": 1.0 if director_ok else 0.0,
            "director_alive_b": 1.0 if (director_ok and self.director_alive) else 0.0,
            "director_inv_readable_b": 1.0 if director_ok else 0.0,
            "director_inv_count_n": float(len(self._director_tree_entities())) if director_ok else 0.0,
        }
        result_payload = wire.pack_payload(scalars_str=text_out, scalars_num=num_out)
        self.pending_finish[job_name] = CENSUS_FINISH_AFTER_ATTEMPT_TICKS
        self.census_start_tick[job_name] = snap_stamp
        return ("done", "", result_payload)


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
            # SurfaceY de la x y la z de esta fila (la ultima posicion conocida si la entidad ya no existe)
            "surface_y_m": float(_surface_y(pos[0], pos[2])),
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
        if self.purge_job_id == job_id:
            self.purge_job_id = ""
            self.purge_confirm = None
            self.purge_confirm_ent = None
            self.purge_emit_tick = 0.0

    def _finish_pending_job(self, jid):
        if self.jobs.get_state(jid) == "running":
            reason = self.census_failed.get(jid, "")
            if reason:
                self.jobs.end_job(jid, "failed", reason)
            elif self.jobs.is_deadman_tripped(jid):
                self.jobs.end_job(jid, "failed", "lease_expired")
            else:
                self.jobs.end_job(jid, "done", "")
        self.pending_finish.pop(jid, None)
        self.census_start_tick.pop(jid, None)
        self.contention_seen_for.pop(jid, None)
        self.census_failed.pop(jid, None)

    def _op_cleanup(self, args_unpacked):
        for jid in list(self.pending_finish):
            self._finish_pending_job(jid)
        self.pending_finish.clear()
        self.census_start_tick.clear()
        self.contention_seen_for.clear()
        self.census_failed.clear()

        # BLOQ 5 + MEN 10 (espejo de CleanupAllEntities): identidad valida
        # (vacia/cero nunca coincide) o clase centinela + marca, solo dentro
        # de discos validos; sin disco valido no hay barrido por marca.
        qa_net_ids = set()
        qa_pers_ids = set()
        for rec in self.records:
            ent = rec.get("ent")
            if ent is not None:
                if _is_valid_identity(ent["net_id"], ZERO_NET_ID):
                    qa_net_ids.add(ent["net_id"])
                if _is_valid_identity(ent["pers_id"], ZERO_PERS_ID):
                    qa_pers_ids.add(ent["pers_id"])
        for nid in list(self.raw_net_ids) + list(self.qa_net_ids):
            if _is_valid_identity(nid, ZERO_NET_ID):
                qa_net_ids.add(nid)
        for ent in self.world.values():
            if ent["net_id"] in qa_net_ids and _is_valid_identity(ent["pers_id"], ZERO_PERS_ID):
                qa_pers_ids.add(ent["pers_id"])

        discs = []
        for row in args_unpacked.get("rows") or []:
            try:
                cx = float(row.get("center_x_m", 0.0))
                cz = float(row.get("center_z_m", 0.0))
                rad = float(row.get("radius_m", 0.0))
            except (TypeError, ValueError):
                continue
            if rad > 0.0 and math.isfinite(cx) and math.isfinite(cz):
                discs.append((cx, cz, rad))

        # Contenedores registrados con descendientes ajenos/desconocidos se
        # protegen (y sus ancestros registrados), como al reaplicar.
        retain = self._retained_net_ids(list(self.records))
        cleaned_own = 0
        kept_records = []
        for rec in list(self.records):
            ent = rec.get("ent")
            if ent is not None and self._root_owner_uid(ent) == self.director_uid:
                kept_records.append(rec)
                continue
            if ent is not None and retain.get(ent["net_id"]):
                kept_records.append(rec)
                continue
            if ent is not None:
                cleaned_own += 1
            self._drop_records([rec])

        cleaned_raw = 0
        for net_id in list(self.world.keys()):
            ent = self.world.get(net_id)
            if ent is None or self._root_owner_uid(ent) == self.director_uid:
                continue
            if retain.get(net_id):
                continue
            # Lo que cuelga de un contenedor protegido tampoco se borra.
            ancestor_nid = ent["parent_net_id"]
            protected_descendant = False
            while ancestor_nid:
                if retain.get(ancestor_nid):
                    protected_descendant = True
                    break
                parent_ent = self.world.get(ancestor_nid)
                ancestor_nid = parent_ent["parent_net_id"] if parent_ent else ""
            if protected_descendant:
                continue
            by_identity = _identity_matches(ent["net_id"], ent["pers_id"], qa_net_ids, qa_pers_ids)
            by_mark = (
                bool(discs)
                and ent["class_name"] in SENTINEL_CLASSES
                and _is_health_mark(ent)
                and any(_dist2(ent["pos"][0], ent["pos"][2], cx, cz) <= rad for cx, cz, rad in discs)
            )
            if by_identity or by_mark:
                # Un contenedor con descendientes ajenos tampoco se borra
                # por identidad/marca: se protege entero.
                rec_net_ids = {r["ent"]["net_id"] for r in kept_records}
                has_foreign_desc = any(
                    d["net_id"] not in qa_net_ids and d["net_id"] not in rec_net_ids and not (d["class_name"] in SENTINEL_CLASSES and _is_health_mark(d))
                    for d in self._descendants(net_id)
                )
                if has_foreign_desc:
                    continue
                cleaned_raw += 1
                self._delete_entity(ent)
        self.records = kept_records
        self.scene_gen = {}
        self.scene_last_op = {}
        self.scene_applied = {}
        self.scene_center = {}
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
        self.purge_job_id = ""
        self.purge_confirm = None
        self.purge_confirm_ent = None
        self.purge_emit_tick = 0.0
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
        # MEN-12 tambien al reiniciar: ningun trabajo queda running reteniendo per_census.
        for jid in list(self.pending_finish):
            self._finish_pending_job(jid)
        self.pending_finish.clear()
        self.census_start_tick.clear()
        self.contention_seen_for.clear()
        self.census_failed.clear()
        self._save_state()

    def _tick_purge(self):
        if not self.purge_job_id:
            return
        if self.jobs.get_state(self.purge_job_id) != "running":
            return
        if not (self.director_present and self.director_alive and self.director_inv_readable):
            self.jobs.end_job(self.purge_job_id, "failed", "director_lost")
            return
        tree = self._director_tree_entities()
        if self.purge_confirm is not None:
            if self._purge_count(tree, self.purge_confirm) > 0:
                return
            idx = self._purge_authorized_index(self.purge_confirm)
            if idx >= 0 and not self.purge_resolved[idx]:
                ent = self.purge_confirm_ent
                # Aclaracion 2: tick en que se confirma la ausencia, posterior al emit.
                confirm_tick = float(self.peer.local_ms())
                if confirm_tick <= self.purge_emit_tick:
                    confirm_tick = self.purge_emit_tick + 1.0
                if self._purge_append("result", ent, "deleted", confirm_tick=confirm_tick):
                    self.purge_resolved[idx] = 1
            self.purge_confirm = None
            if self.jobs.get_state(self.purge_job_id) != "running":
                return
        if all(self.purge_resolved):
            self.jobs.end_job(self.purge_job_id, "done", "ok")
            return
        for idx, pers in enumerate(self.purge_auth_pers):
            if self.jobs.get_state(self.purge_job_id) != "running":
                return
            if self.purge_resolved[idx]:
                continue
            cls = self.purge_auth_class[idx]
            count = self._purge_count(tree, pers)
            if count == 0:
                if self._purge_append("result", {"pers_id": pers, "class_name": cls,
                                                 "net_id": "", "parent_net_id": "",
                                                 "max_hp": 0.0, "health_hp": 0.0}, "absent"):
                    self.purge_resolved[idx] = 1
                continue
            if count > 1:
                first = next((e for e in tree if e.get("pers_id") == pers), None)
                if self._purge_append("result", first, "ambiguous"):
                    self.purge_resolved[idx] = 1
                continue
            cand = next((e for e in tree if e.get("pers_id") == pers), None)
            if cand is None or cand.get("class_name") != cls or not self._purge_tree_eligible(cand, tree):
                if self._purge_append("result", cand or {"pers_id": pers, "class_name": cls,
                                                         "net_id": "", "parent_net_id": "",
                                                         "max_hp": 0.0, "health_hp": 0.0}, "retained_foreign"):
                    self.purge_resolved[idx] = 1
                continue
            leaf = self._purge_pick_leaf(cand, tree)
            if leaf is None:
                if self._purge_append("result", cand, "retained_foreign"):
                    self.purge_resolved[idx] = 1
                continue
            # MENOR 6: una sola lectura de la edad; se decide y se registra la misma muestra.
            if hasattr(self.peer, "lease_age_ms"):
                age = float(self.peer.lease_age_ms())
                limit = float(getattr(self.peer, "lease_ms", 3000) or 3000)
                if age > limit:
                    return
            else:
                if not self.peer.lease_valid():
                    return
                age = 0.0
                limit = 0.0
            emit_tick = float(self.peer.local_ms())
            for sub in self._purge_subtree(leaf):
                if not self._purge_append("emit", sub, "", emit_tick, age, limit):
                    return
            self.purge_emit_tick = emit_tick
            self.purge_confirm = leaf.get("pers_id", "")
            self.purge_confirm_ent = dict(leaf)
            self._delete_entity(leaf)
            return
        if all(self.purge_resolved):
            self.jobs.end_job(self.purge_job_id, "done", "ok")

    def on_tick(self, timeslice_s):
        self._tick_purge()
        self._tick_witness()
        # BLOQ 6: A mantiene la ocupacion hasta acreditar el intento de B
        # (entonces termina en pocos ticks, con released_tick posterior al
        # snap de B) o hasta la salida acotada CENSUS_HOLD_MAX_MS.
        for job_id in list(self.pending_finish):
            if self.jobs.get_state(job_id) != "running":
                self.pending_finish.pop(job_id, None)
                self.census_start_tick.pop(job_id, None)
                self.contention_seen_for.pop(job_id, None)
                self.census_failed.pop(job_id, None)
                continue
            seen = job_id in self.contention_seen_for
            start_tick = float(self.census_start_tick.get(job_id, 0.0))
            bounded_exit = (
                start_tick > 0.0
                and float(self.peer.local_ms()) - start_tick >= CENSUS_HOLD_MAX_MS
            )
            if not seen and not bounded_exit:
                continue
            left = int(self.pending_finish.get(job_id, 0)) - 1
            if left > 0:
                self.pending_finish[job_id] = left
                continue
            self._finish_pending_job(job_id)

    def on_shutdown(self):
        for jid in list(self.pending_finish):
            self._finish_pending_job(jid)
        self.pending_finish.clear()
        self.witness = None
        self.census_start_tick.clear()
        self.contention_seen_for.clear()
        self.census_failed.clear()


def create_ext(peer, jobs):
    return PersistFakeExt()
