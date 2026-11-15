"""Extension de S-mapa para fake_peer (prefijo map_, RPC 26102870..26102879).

Implementa los tres verbos ``map_world_read``, ``map_feature_locate`` y ``map_place_ground`` con el mismo algoritmo
que ``DSBX_QA_X_Map.c`` (brief S-mapa §4.1-§4.3 y §5.1) sobre un MUNDO SIMULADO:

- Terreno: dentro de las 6 ventanas ``world_roi_m`` de la fixture (``qa/fixtures/s_mapa_puntos.json``) la altura sale de
  la malla de 16x16 muestras de la captura certificadora offline (interpolacion bilineal; en los nodos es exacta). Fuera
  de ellas, una funcion analitica determinista (sin lectura de la imagen ni de las transformaciones del runner).
- Objetos: un puente (calzada a 6,75 m sobre un terreno de 1,25 m) y una casa (tejado a 15,25 m sobre 6,5 m), que solo
  se ven en ``SurfaceRoadY`` y en el raycast vertical, nunca en ``SurfaceY``.
- Creacion: ``spawn_tracked`` es la UNICA via que instancia un objeto; incrementa el contador monotono ``seq`` al crear
  y la identidad, clase, posicion y caja se LEEN del objeto creado (no se copia lo pedido).

Los fallos inyectados (``qa_fault``) son ``ignore_elevated_surface`` y ``spawn_then_reject`` en ``map_place_ground``;
cualquier otro valor, o un fallo en otro verbo, se rechaza con ``bad_args`` (falla cerrado).
"""

import json
import math
from pathlib import Path

import wire
from fake_peer import FakeExt

PREFIX = "map_"
RPC_BASE = 26102870

VERB_WORLD = "map_world_read"
VERB_LOCATE = "map_feature_locate"
VERB_PLACE = "map_place_ground"
_VERBS = frozenset({VERB_WORLD, VERB_LOCATE, VERB_PLACE})

WORLD_NAME = "chernarusplus"
WORLD_SIZE_M = 15360.0
SEA_LEVEL_M = 0.0
STEP_M = 3.75
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "s_mapa_puntos.json"

FAULT_IGNORE_ELEVATED = "ignore_elevated_surface"
FAULT_SPAWN_THEN_REJECT = "spawn_then_reject"
_KNOWN_FAULTS = frozenset({"", FAULT_IGNORE_ELEVATED, FAULT_SPAWN_THEN_REJECT})

_FEATURE_KINDS = frozenset({"relief_peak", "coast_ns", "coast_ew"})
_LOCATE_MODES = frozenset({"calibrate", "verify"})
_READ_MODES = frozenset({"grid_row", "patch_row"})

_ELEVATION_M = 0.25
_STR_MAX = 32

# Objetos del mundo simulado: (centro x, centro z, semiancho x, semiancho z, cota superior y, clase).
_BRIDGE = (13210.0, 4200.0, 14.0, 4.0, 6.75, "Land_Bridge_Concrete_25")
_HOUSE = (6680.0, 2628.0, 6.0, 5.0, 15.25, "Land_House_2W01")
_STATIC_OBJECTS = (_BRIDGE, _HOUSE)
# Terreno plano alrededor de los puntos de colocacion: (x, z, semiancho, y).
_FLAT_PATCHES = (
    (6720.0, 2660.0, 8.0, 12.5),
    (6680.0, 2628.0, 2.0, 6.5),
    (13210.0, 4200.0, 30.0, 1.25),
)
# Caja local de la clase de barril: (min y, max y).
_BARREL_BOX = (-0.5625, 0.5625)


def _q64(val):
    return round(float(val) * 64.0) / 64.0


def _is_num(val):
    return isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(float(val))


def _is_int(val):
    return _is_num(val) and float(val) == math.floor(float(val))


def _clip(text):
    return text if len(text) <= _STR_MAX else text[:_STR_MAX]


class _Roi:
    def __init__(self, world_roi_m, samples_256):
        self.x_min = float(world_roi_m[0])
        self.z_min = float(world_roi_m[1])
        self.x_max = float(world_roi_m[2])
        self.z_max = float(world_roi_m[3])
        self.y = [[float(samples_256[r * 16 + c][0]) for c in range(16)] for r in range(16)]

    def contains(self, x, z):
        return self.x_min <= x <= self.x_max and self.z_min <= z <= self.z_max

    def height(self, x, z):
        fc = (x - self.x_min) / STEP_M
        fr = (self.z_max - z) / STEP_M
        c0 = min(14, max(0, int(math.floor(fc))))
        r0 = min(14, max(0, int(math.floor(fr))))
        tc = min(1.0, max(0.0, fc - c0))
        tr = min(1.0, max(0.0, fr - r0))
        top = self.y[r0][c0] * (1.0 - tc) + self.y[r0][c0 + 1] * tc
        bottom = self.y[r0 + 1][c0] * (1.0 - tc) + self.y[r0 + 1][c0 + 1] * tc
        return top * (1.0 - tr) + bottom * tr


class _World:
    """Motor simulado: terreno, calzada, raycast, censo de objetos y creacion rastreada."""

    def __init__(self, rois):
        self.rois = rois
        self.seq = 0
        self._next_id = 4000000
        self.live = []

    @staticmethod
    def _global_raw(x, z):
        t = z / WORLD_SIZE_M
        return (
            -32.0
            + 270.0 * (t ** 1.15)
            + 14.0 * math.sin(x / 1700.0) * math.cos(z / 1300.0)
            + 8.0 * math.sin((x + z) / 900.0)
        )

    def surface_y(self, x, z):
        for roi in self.rois:
            if roi.contains(x, z):
                return _q64(roi.height(x, z))
        for cx, cz, half, y in _FLAT_PATCHES:
            if abs(x - cx) <= half and abs(z - cz) <= half:
                return y
        return _q64(self._global_raw(x, z))

    def surface_is_sea(self, x, z):
        return self.surface_y(x, z) <= SEA_LEVEL_M

    def surface_road_y(self, x, z):
        terrain = self.surface_y(x, z)
        cx, cz, hx, hz, top, _cls = _BRIDGE
        if abs(x - cx) <= hx and abs(z - cz) <= hz:
            return max(terrain, top)
        return terrain

    def sea_b(self, x, z, y):
        if self.surface_is_sea(x, z) or y <= SEA_LEVEL_M:
            return 1.0
        return 0.0

    @staticmethod
    def raycast_down(x, z, y_from, y_to):
        """Raycast vertical descendente: (impacto, y, clase) del objeto mas alto entre y_from e y_to."""
        best = None
        for cx, cz, hx, hz, top, cls in _STATIC_OBJECTS:
            if abs(x - cx) <= hx and abs(z - cz) <= hz and y_to <= top <= y_from:
                if best is None or top > best[0]:
                    best = (top, cls)
        if best is None:
            return (False, 0.0, "")
        return (True, best[0], best[1])

    def objects_at(self, x, z, radius):
        n = 0
        for cx, cz, _hx, _hz, _top, _cls in _STATIC_OBJECTS:
            if math.hypot(x - cx, z - cz) <= radius:
                n += 1
        for obj in self.live:
            if math.hypot(x - obj["pos"][0], z - obj["pos"][2]) <= radius:
                n += 1
        return n

    def spawn_tracked(self, class_name, x, y, z):
        """Unica via de instanciacion: None si la clase no existe; si no, cuenta y devuelve el objeto creado."""
        if not class_name.startswith("Barrel_"):
            return None
        self.seq += 1
        self._next_id += 1
        obj = {"id": self._next_id, "class": class_name, "pos": [x, y, z], "box": _BARREL_BOX}
        self.live.append(obj)
        return obj

    def delete(self, obj):
        if obj in self.live:
            self.live.remove(obj)


def _load_world():
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    patches = data["certifying_capture"]["patches"]
    rois = []
    for pid in ("C1", "C2", "C3", "V1", "V2", "V3"):
        p = patches[pid]
        rois.append(_Roi(p["world_roi_m"], p["samples_256"]))
    return _World(rois)


def _bad_args():
    return ("rejected", "bad_args", wire.empty_payload())


class MapFakeExt(FakeExt):
    def __init__(self):
        super().__init__()
        self.peer = None
        self._world = None
        self._world_failed = False

    def init(self, peer, jobs):
        self.peer = peer

    def handles(self, verb, role):
        return role == "server" and verb in _VERBS

    def _get_world(self):
        if self._world is None and not self._world_failed:
            try:
                self._world = _load_world()
            except (OSError, ValueError, KeyError, IndexError):
                self._world_failed = True
        return self._world

    def _clock(self):
        if self.peer is None:
            return 0.0, 0.0
        return round(float(self.peer.local_ms()), 3), float(self.peer.frame)

    def on_start_op(self, op, args_unpacked, raw_args):
        verb = op.get("verb")
        fault = str(op.get("qa_fault") or "")
        if fault not in _KNOWN_FAULTS or (fault != "" and verb != VERB_PLACE):
            return _bad_args()
        if args_unpacked.get("rows") or args_unpacked.get("ncol") or args_unpacked.get("scol"):
            return _bad_args()
        strs = args_unpacked.get("str", {})
        nums = args_unpacked.get("num", {})
        world = self._get_world()
        if verb == VERB_WORLD:
            return self._world_read(world, strs, nums)
        if verb == VERB_LOCATE:
            return self._feature_locate(world, strs, nums)
        if verb == VERB_PLACE:
            return self._place_ground(world, strs, nums, fault)
        return ("rejected", "unknown_verb", wire.empty_payload())

    # --- map_world_read -------------------------------------------------------------------------------------
    def _world_read(self, world, strs, nums):
        mode = strs.get("mode_id")
        if mode not in _READ_MODES:
            return _bad_args()
        for key in ("x0_m", "z0_m", "step_m", "row_n", "chunk_n"):
            if not _is_num(nums.get(key)):
                return _bad_args()
        if not (_is_int(nums["row_n"]) and _is_int(nums["chunk_n"])):
            return _bad_args()
        x0, z0, step = float(nums["x0_m"]), float(nums["z0_m"]), float(nums["step_m"])
        row_n, chunk_n = int(nums["row_n"]), int(nums["chunk_n"])
        if chunk_n < 1 or chunk_n > 8 or step <= 0.0 or row_n < 0:
            return _bad_args()
        if world is None:
            return ("error", "world_unavailable", wire.empty_payload())
        rows = []
        for c in range(chunk_n):
            x = x0 + float(c) * step
            y = world.surface_y(x, z0)
            rows.append({"y_m": y, "sea_b": world.sea_b(x, z0, y)})
        tick, frame = self._clock()
        payload = wire.pack_payload(
            scalars_str={"world_name": WORLD_NAME, "mode_id": mode},
            scalars_num={
                "world_size_m": WORLD_SIZE_M,
                "sea_level_m": SEA_LEVEL_M,
                "x0_m": x0,
                "z0_m": z0,
                "step_m": step,
                "row_n": float(row_n),
                "tick_ms": tick,
                "frame": frame,
            },
            num_cols=["y_m", "sea_b"],
            row_dicts=rows,
        )
        return ("done", "", payload)

    # --- map_feature_locate ---------------------------------------------------------------------------------
    @staticmethod
    def _grid(world, x_min, z_max):
        grid = []
        for r in range(16):
            line = []
            for c in range(16):
                x = x_min + STEP_M * float(c)
                z = z_max - STEP_M * float(r)
                y = world.surface_y(x, z)
                line.append((x, z, y, world.sea_b(x, z, y)))
            grid.append(line)
        return grid

    @staticmethod
    def _find_peak(grid):
        if any(grid[r][c][3] != 0.0 for r in range(16) for c in range(16)):
            return None
        y_max = max(grid[r][c][2] for r in range(16) for c in range(16))
        border = [(r, c) for r in range(16) for c in range(16) if r in (0, 15) or c in (0, 15)]
        y_border = max(grid[r][c][2] for r, c in border)
        prominence = y_max - y_border
        if prominence < 5.0:
            return None
        m_srv = [(r, c) for r in range(1, 15) for c in range(1, 15) if grid[r][c][2] >= y_max - 0.5]
        if not (1 <= len(m_srv) <= 9):
            return None
        srv_x = sum(grid[r][c][0] for r, c in m_srv) / float(len(m_srv))
        srv_z = sum(grid[r][c][1] for r, c in m_srv) / float(len(m_srv))
        row0 = next(grid[r][c] for r, c in border if grid[r][c][2] == y_border)
        row1 = next(grid[r][c] for r in range(1, 15) for c in range(1, 15) if grid[r][c][2] == y_max)
        return {"x": srv_x, "z": srv_z, "y": y_max, "prom": prominence, "rows": (row0, row1)}

    @staticmethod
    def _find_coast(grid, kind):
        if kind == "coast_ns":
            line = [grid[k][8] for k in range(16)]
        else:
            line = [grid[8][k] for k in range(16)]
        found = [
            k
            for k in range(3, 14)
            if all(line[i][3] == 0.0 for i in range(0, k)) and all(line[i][3] == 1.0 for i in range(k, 16))
        ]
        if len(found) != 1:
            return None
        k = found[0]
        y_land = line[k - 1][2]
        shore_step = y_land - SEA_LEVEL_M
        if shore_step < 0.20:
            return None
        if kind == "coast_ns":
            srv_x = line[0][0]
            srv_z = line[0][1] - (float(k) - 0.5) * STEP_M
        else:
            srv_x = line[0][0] + (float(k) - 0.5) * STEP_M
            srv_z = line[0][1]
        return {"x": srv_x, "z": srv_z, "y": y_land, "prom": shore_step, "rows": (line[k - 1], line[k])}

    def _feature_locate(self, world, strs, nums):
        point_id = strs.get("point_id")
        kind = strs.get("feature_kind")
        mode = strs.get("mode_id")
        if not isinstance(point_id, str) or point_id == "" or kind not in _FEATURE_KINDS or mode not in _LOCATE_MODES:
            return _bad_args()
        for key in ("x_min_m", "z_min_m", "x_max_m", "z_max_m"):
            if not _is_num(nums.get(key)):
                return _bad_args()
        x_min, z_min = float(nums["x_min_m"]), float(nums["z_min_m"])
        x_max, z_max = float(nums["x_max_m"]), float(nums["z_max_m"])
        if x_max <= x_min or z_max <= z_min:
            return _bad_args()
        if mode == "calibrate":
            if "req_x_m" in nums or "req_z_m" in nums:
                return _bad_args()
            req_x = req_z = 0.0
        else:
            if not (_is_num(nums.get("req_x_m")) and _is_num(nums.get("req_z_m"))):
                return _bad_args()
            req_x, req_z = float(nums["req_x_m"]), float(nums["req_z_m"])
        if world is None:
            return ("error", "world_unavailable", wire.empty_payload())

        decision, reason = "located", ""
        found = None
        audit = [(0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0)]
        err_xz = err_refl = 0.0
        if mode == "verify" and (req_x < 0.0 or req_x > WORLD_SIZE_M or req_z < 0.0 or req_z > WORLD_SIZE_M):
            decision, reason = "rejected", "out_of_map"
        else:
            grid = self._grid(world, x_min, z_max)
            found = self._find_peak(grid) if kind == "relief_peak" else self._find_coast(grid, kind)
            if found is not None:
                audit = [(c[0], c[1], c[2], c[3]) for c in found["rows"]]
            if found is None:
                decision, reason = "rejected", "feature_not_found"
            elif mode == "verify":
                err_xz = math.hypot(req_x - found["x"], req_z - found["z"])
                err_refl = abs((WORLD_SIZE_M - req_z) - found["z"])
                if err_xz >= 10.0 and err_refl < 50.0 and abs(req_x - found["x"]) < 50.0:
                    decision, reason = "rejected", "inverted_axis"
                elif err_xz >= 10.0:
                    decision, reason = "rejected", "verification_error_exceeded"
                else:
                    decision, reason = "verified", ""
        tick, frame = self._clock()
        payload = wire.pack_payload(
            scalars_str={
                "point_id": _clip(point_id),
                "mode_id": mode,
                "decision_id": decision,
                "reject_reason_id": reason,
            },
            scalars_num={
                "req_x_m": req_x,
                "req_z_m": req_z,
                "srv_feature_found_b": 1.0 if found is not None else 0.0,
                "srv_x_m": found["x"] if found is not None else 0.0,
                "srv_y_m": found["y"] if found is not None else 0.0,
                "srv_z_m": found["z"] if found is not None else 0.0,
                "prominence_m": found["prom"] if found is not None else 0.0,
                "err_xz_m": err_xz,
                "err_reflected_z_m": err_refl,
                "tick_ms": tick,
                "frame": frame,
            },
            num_cols=["sx_m", "sz_m", "y_m", "sea_b"],
            row_dicts=[{"sx_m": a[0], "sz_m": a[1], "y_m": a[2], "sea_b": a[3]} for a in audit],
        )
        return ("done", "", payload)

    # --- map_place_ground -----------------------------------------------------------------------------------
    def _place_ground(self, world, strs, nums, fault):
        point_id = strs.get("point_id")
        class_id = strs.get("class_id")
        if (
            not isinstance(point_id, str)
            or point_id == ""
            or not isinstance(class_id, str)
            or class_id == ""
            or not (_is_num(nums.get("req_x_m")) and _is_num(nums.get("req_z_m")))
        ):
            return _bad_args()
        if world is None:
            return ("error", "world_unavailable", wire.empty_payload())
        req_x, req_z = float(nums["req_x_m"]), float(nums["req_z_m"])

        seq_pre = world.seq
        rd = {
            "terrain_y": 0.0, "road_y": 0.0, "ray_hit": 0.0, "hit_y": 0.0, "hit_class": "",
            "obs_class": "", "ent_id": 0.0, "obs": (0.0, 0.0, 0.0), "bbox_min": 0.0, "bbox_max": 0.0,
            "obs_surf": 0.0, "pre_count": 0.0, "post_count": 0.0,
        }
        decision, reason = "placed", ""

        def observe(obj):
            rd["ent_id"] = float(obj["id"])
            rd["obs_class"] = _clip(obj["class"])
            rd["obs"] = (obj["pos"][0], obj["pos"][1], obj["pos"][2])
            rd["bbox_min"], rd["bbox_max"] = obj["box"]
            rd["obs_surf"] = world.surface_y(obj["pos"][0], obj["pos"][2])

        if req_x < 0.0 or req_x > WORLD_SIZE_M or req_z < 0.0 or req_z > WORLD_SIZE_M:
            decision, reason = "rejected", "out_of_map"
            if fault == FAULT_SPAWN_THEN_REJECT:
                obj = world.spawn_tracked(class_id, req_x, 0.0, req_z)
                if obj is not None:
                    observe(obj)
                    world.delete(obj)
        else:
            terrain = world.surface_y(req_x, req_z)
            road = world.surface_road_y(req_x, req_z)
            hit, hit_y, hit_class = world.raycast_down(req_x, req_z, terrain + 100.0, terrain + _ELEVATION_M)
            rd["terrain_y"], rd["road_y"] = terrain, road
            rd["ray_hit"], rd["hit_y"], rd["hit_class"] = (1.0 if hit else 0.0), hit_y, _clip(hit_class)
            rd["pre_count"] = float(world.objects_at(req_x, req_z, 2.0))
            elevated = (road - terrain > _ELEVATION_M) or (hit and hit_y > terrain + _ELEVATION_M)
            if elevated and fault != FAULT_IGNORE_ELEVATED:
                decision, reason = "rejected", "elevated_surface"
                if fault == FAULT_SPAWN_THEN_REJECT:
                    obj = world.spawn_tracked(class_id, req_x, terrain, req_z)
                    if obj is not None:
                        observe(obj)
                        world.delete(obj)
            else:
                obj = world.spawn_tracked(class_id, req_x, terrain, req_z)
                if obj is None:
                    decision, reason = "rejected", "spawn_failed"
                else:
                    obj["pos"][1] = terrain - obj["box"][0]
                    observe(obj)
                    world.delete(obj)
                    if abs(rd["obs"][1] + rd["bbox_min"] - rd["obs_surf"]) >= 0.2:
                        decision, reason = "rejected", "contact_height_error"
            rd["post_count"] = float(world.objects_at(req_x, req_z, 2.0))
        seq_post = world.seq
        tick, frame = self._clock()
        payload = wire.pack_payload(
            scalars_str={
                "point_id": _clip(point_id),
                "decision_id": decision,
                "reject_reason_id": reason,
                "hit_class_id": rd["hit_class"],
                "obs_class_id": rd["obs_class"],
            },
            scalars_num={
                "req_x_m": req_x,
                "req_z_m": req_z,
                "terrain_y_m": rd["terrain_y"],
                "road_y_m": rd["road_y"],
                "ray_hit_b": rd["ray_hit"],
                "hit_y_m": rd["hit_y"],
                "seq_pre_n": float(seq_pre),
                "seq_post_n": float(seq_post),
                "ent_id_n": rd["ent_id"],
                "obs_x_m": rd["obs"][0],
                "obs_y_m": rd["obs"][1],
                "obs_z_m": rd["obs"][2],
                "bbox_min_y_m": rd["bbox_min"],
                "bbox_max_y_m": rd["bbox_max"],
                "obs_surf_y_m": rd["obs_surf"],
                "pre_count_n": rd["pre_count"],
                "post_count_n": rd["post_count"],
                "tick_ms": tick,
                "frame": frame,
            },
        )
        return ("done", "", payload)


def create_ext(peer, jobs):
    ext = MapFakeExt()
    ext.peer = peer
    return ext
