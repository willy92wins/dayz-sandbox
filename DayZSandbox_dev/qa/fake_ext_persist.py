"""Extension de S-persist para fake_peer (prefijo per_, RPC 26102800..26102809).

Modela un mundo minimo del servidor: registro de propiedad en memoria, entidades
propias creadas con ECE_NOPERSISTENCY_WORLD, objetos ajenos y un control persistente,
reseteo por escena con retencion de descendientes ajenos o de otra escena, censos por
disco con trabajo protegido (resource per_census, deadman stop) y reinicio de mundo que
solo conserva lo creado sin ECE_NOPERSISTENCY_WORLD.
"""

import json
import math
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


def _is_valid_identity(value, zero):
    text = str(value or "")
    return text != "" and text != zero


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

    def _add_entity(self, **kw):
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
        self.world[ent["net_id"]] = ent
        return ent

    def _record_by(self, scene_id, logical_id):
        for rec in self.records:
            if rec["scene_id"] == scene_id and rec["logical_id"] == logical_id:
                return rec
        return None

    def _children_count(self, net_id):
        n = 0
        for ent in self.world.values():
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

    def _census_row(self, ent, in_radius):
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
            "inv_children_n": float(self._children_count(ent["net_id"])),
            "spawn_tick_ms": float(ent["spawn_tick_ms"]),
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
                })
                continue
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
                    # MEN-13 (espejo del .c): fila fallida sin creacion, sin salud observada.
                    out_rows.append({
                        "logical_id": lid, "class_name": cname, "net_id": "",
                        "obs_loc_kind": "", "obs_parent_net_id": "", "obs_slot_name": "",
                        "ok_b": 0.0, "alive_b": 0.0, "ai_agent_b": 0.0,
                        "req_y_m": 0.0, "q9_x_m": 0.0, "q9_y_m": 0.0, "q9_z_m": 0.0,
                        "q9_dx_m": 0.0, "q9_dy_m": 0.0, "q9_dz_m": 0.0, "q9_err_3d_m": 0.0,
                        "q9_yaw_deg": 0.0, "q9_pitch_deg": 0.0, "q9_roll_deg": 0.0,
                        "max_hp": 0.0, "health_hp": 0.0, "spawn_tick_ms": now_ms,
                    })
                    continue
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
        if expect_epoch != self.epoch:
            return ("rejected", "stale_epoch", wire.empty_payload())
        rec = self._record_by(scene_id, logical_id)
        if rec is None:
            return ("rejected", "unknown_entity", wire.empty_payload())
        ent = rec["ent"]
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
        x_m = float(nums.get("x_m", 0.0))
        z_m = float(nums.get("z_m", 0.0))
        yaw = float(nums.get("yaw_deg", 0.0))
        ratio = float(nums.get("health_mark_ratio", 0.0))
        if not tag or not cname:
            return ("rejected", "bad_args", wire.empty_payload())
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
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
        if mode == "foreign_in_container":
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
        if not area_tag:
            return ("rejected", "bad_args", wire.empty_payload())
        if fault == "drop_ctrl_pre_restart":
            for net_id in list(self.world.keys()):
                ent = self.world[net_id]
                if ent["class_name"] == "Barrel_Yellow" and ent["area_id"] == "area_c":
                    self._delete_entity(ent)
        job_id = op["op_id"]
        # BLOQ 6: acreditar el intento de B sobre el censo A que retiene el
        # recurso (aceptado por bypass o rechazado busy): A no se libera
        # hasta este intento o hasta la salida acotada CENSUS_HOLD_MAX_MS.
        held_jid = self.jobs.held_resources.get("per_census")
        if held_jid and held_jid != job_id:
            self.contention_seen_for[held_jid] = float(self.peer.local_ms())
        # Mutante census_resource_bypass: el recurso per_census no protege; el segundo censo se
        # acepta aunque el primero siga activo. El runner pasa este qa_fault solo en esa parte.
        if fault == "census_resource_bypass":
            self.jobs.held_resources.pop("per_census", None)
        err = self.jobs.start_job(
            self,
            job_id,
            "per_census",
            list(CENSUS_NCOL),
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
        captured = 0
        capture_failed = ""
        for row in rows:
            # MEN 8/9 (espejo de AppendEntityCensusRow): guarda por fila.
            if not self.peer.lease_valid():
                capture_failed = "lease_expired"
                break
            nvals = [row[c] for c in CENSUS_NCOL]
            svals = [row[c] for c in CENSUS_SCOL]
            if not self.jobs.append_row(job_id, nvals, svals):
                capture_failed = "capture_truncated"
                break
            captured += 1
        if not capture_failed and captured < len(rows):
            capture_failed = "capture_truncated"
        if capture_failed:
            # MEN 9: una captura truncada termina como trabajo fallido.
            self.census_failed[job_id] = capture_failed
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
            "rows_captured_n": float(captured),
            "center_x_m": center_x,
            "center_z_m": center_z,
            "radius_m": radius,
            "director_present_b": 1.0,
            "director_alive_b": 1.0,
            "director_inv_readable_b": 1.0,
            "director_inv_count_n": float(len(self.director_items)),
        }
        payload = wire.pack_payload(scalars_str=s, scalars_num=n)
        self.pending_finish[job_id] = CENSUS_FINISH_AFTER_ATTEMPT_TICKS
        self.census_start_tick[job_id] = snap_ms
        return ("done", "", payload)

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
            if ent is not None and retain.get(ent["net_id"]):
                kept_records.append(rec)
                continue
            if ent is not None:
                cleaned_own += 1
            self._drop_records([rec])

        cleaned_raw = 0
        for net_id in list(self.world.keys()):
            ent = self.world.get(net_id)
            if ent is None or ent["owner_uid"] == self.director_uid:
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
                    d["net_id"] not in qa_net_ids and d["net_id"] not in rec_net_ids
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

    def on_tick(self, timeslice_s):
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
        self.census_start_tick.clear()
        self.contention_seen_for.clear()
        self.census_failed.clear()


def create_ext(peer, jobs):
    return PersistFakeExt()
