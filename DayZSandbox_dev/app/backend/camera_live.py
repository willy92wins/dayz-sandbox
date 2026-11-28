"""Camara viva en el backend (F4 parte 1 §5.2): CameraLive.

Estado solo bajo el lock del bridge: la orden en vuelo, el ultimo resultado
y la ultima lectura valida con su hora en el reloj del bridge.
"""
import copy

from app.backend.scene_plan import MAX_XZ_MM, MAX_Y_MM, m_to_mm, yaw_to_mdeg

CAM_MAX_KEYS = 32
CAM_VERBS = ("camera.play", "camera.stop", "camera.read")
_CAM_KEYS = ("active", "playing", "cam_id", "t_ms", "dur_ms", "pose")
_ARRAYS = ("c_t_ms", "c_x_mm", "c_y_mm", "c_z_mm", "c_yaw_mdeg",
           "c_pitch_mdeg", "c_fov_mdeg", "c_focus_mm")


def _is_int(val):
    return isinstance(val, int) and not isinstance(val, bool)


def valid_cam_read(read):
    """Forma de la lectura de camara (brief §3.3)."""
    if not isinstance(read, dict) or set(read) != {"cam"}:
        return False
    cam = read.get("cam")
    if not isinstance(cam, dict) or set(cam) != set(_CAM_KEYS):
        return False
    active, playing = cam.get("active"), cam.get("playing")
    if active not in (0, 1) or playing not in (0, 1):
        return False
    if playing == 1 and active != 1:
        return False
    cam_id = cam.get("cam_id")
    if not isinstance(cam_id, str) or len(cam_id.encode("utf-8")) > 40:
        return False
    t_ms, dur_ms = cam.get("t_ms"), cam.get("dur_ms")
    if not _is_int(t_ms) or not _is_int(dur_ms) or t_ms < 0 or dur_ms < 0 or t_ms > dur_ms:
        return False
    pose = cam.get("pose")
    if not isinstance(pose, list) or len(pose) != 6:
        return False
    if not all(_is_int(v) for v in pose):
        return False
    if active == 0:
        return cam_id == "" and t_ms == 0 and dur_ms == 0 and pose == [0, 0, 0, 0, 0, 0]
    x, y, z, yaw, pitch, fov = pose
    return (
        cam_id != ""
        and 0 <= yaw < 360000
        and -90000 <= pitch <= 90000
        and 0 < fov < 180000
        and abs(y) <= MAX_Y_MM
        and 0 <= x <= MAX_XZ_MM
        and 0 <= z <= MAX_XZ_MM
    )


def _fail(code, msg, pointer=""):
    return {"ok": False, "code": code, "pointer": pointer, "msg": msg}


class CameraLive:
    """Coordinador de camara (F4) acoplado a un Bridge y su Backend."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.backend = bridge.backend
        self._in_flight = None
        self._last = None
        self._cam = None
        self._cam_mono = None

    def _in_flight_order_locked(self):
        if self._in_flight is None:
            return None
        order = self.bridge.orders.get((self.bridge.session, self._in_flight))
        if order is not None and order.get("bstate") in ("pendiente", "ejecutando"):
            return order
        self._in_flight = None
        return None

    def snapshot_locked(self):
        """GET /api/camera: ultima lectura, last e in_flight."""
        age_ms = None
        cam = None
        if self._cam is not None and self._cam_mono is not None:
            cam = copy.deepcopy(self._cam)
            age_ms = int((self.bridge._now() - self._cam_mono) * 1000)
        inflight = self._in_flight_order_locked()
        last = copy.deepcopy(self._last) if self._last is not None else None
        return {
            "ok": True,
            "cam": cam,
            "age_ms": age_ms,
            "last": last,
            "in_flight": inflight["op_id"] if inflight is not None else None,
        }

    def on_dropped_locked(self, order, reason):
        if not isinstance(order, dict) or order.get("verb") not in CAM_VERBS:
            return
        if self._in_flight == order.get("op_id"):
            self._in_flight = None
        self._last = {
            "op_id": order["op_id"], "verb": order["verb"],
            "status": "dropped", "reason": reason,
        }

    def on_result_locked(self, order, status, reason, read):
        if not isinstance(order, dict) or order.get("verb") not in CAM_VERBS:
            return
        if self._in_flight == order.get("op_id"):
            self._in_flight = None
        if status == "done":
            cam = copy.deepcopy(read.get("cam"))
            self._cam = cam
            self._cam_mono = self.bridge._now()
            self._last = {
                "op_id": order["op_id"], "verb": order["verb"],
                "status": "done", "reason": None,
            }
            return
        self._last = {
            "op_id": order["op_id"], "verb": order["verb"],
            "status": status, "reason": reason,
        }

    def _busy_locked(self):
        return self._in_flight_order_locked() is not None

    def _enqueue_locked(self, verb, args):
        if not self.bridge.client_in_world():
            return _fail("client_not_in_game", "El cliente no esta en el mundo")
        if self._busy_locked():
            return _fail("camera_busy", "Hay una orden de camara en vuelo")
        ok, order = self.bridge.enqueue_order(verb, args, role="client")
        if not ok:
            return _fail("plan_too_large", "La orden no cabe en el cable")
        self._in_flight = order["op_id"]
        return {"ok": True, "op_id": order["op_id"]}

    def request_stop_locked(self):
        return self._enqueue_locked("camera.stop", {"f2": 1})

    def request_read_locked(self):
        return self._enqueue_locked("camera.read", {"f2": 1})

    def request_play_locked(self, doc_id, cam_id):
        snap = self.backend.store.snapshot()
        if doc_id != snap["doc_id"]:
            return _fail("doc_changed", "documento distinto", "/doc_id")
        cameras = snap["doc"].get("cameras") or []
        idx = None
        cam = None
        for i, c in enumerate(cameras):
            if isinstance(c, dict) and c.get("id") == cam_id:
                idx = i
                cam = c
                break
        if cam is None:
            return _fail("not_found", "No existe esa camara", "/cam_id")
        if not self.bridge.client_in_world():
            return _fail("client_not_in_game", "El cliente no esta en el mundo")
        if self._busy_locked():
            return _fail("camera_busy", "Hay una orden de camara en vuelo")
        keys = cam.get("keys") if isinstance(cam.get("keys"), list) else []
        n = len(keys)
        base = "/cameras/%d/keys" % idx
        if n > CAM_MAX_KEYS:
            return _fail("invalid", "Mas de %d claves" % CAM_MAX_KEYS, base)
        t_ms = []
        for k, key in enumerate(keys):
            t = key.get("t") if isinstance(key, dict) else None
            t_ms.append(round(float(t) * 1000) if t is not None else None)
        for k in range(1, n):
            if t_ms[k] is not None and t_ms[k - 1] is not None and t_ms[k] == t_ms[k - 1]:
                return _fail("invalid", "Dos claves en el mismo milisegundo",
                             "%s/%d/t" % (base, k))
        srv = self.bridge.peers.get("server") or {}
        wsize = srv.get("world_size")
        wsize = float(wsize) if isinstance(wsize, (int, float)) and not isinstance(wsize, bool) else 0.0
        for k, key in enumerate(keys):
            if not isinstance(key, dict):
                continue
            for axis in ("x", "z"):
                val = key.get(axis)
                if not isinstance(val, (int, float)) or isinstance(val, bool) \
                        or float(val) < 0.0 or float(val) > wsize:
                    return _fail("out_of_map", "Fuera del mapa", "%s/%d/%s" % (base, k, axis))
        args = {
            "f2": 1,
            "cam_id": cam_id,
            "c_t_ms": [round(float(key["t"]) * 1000) for key in keys],
            "c_x_mm": [m_to_mm(key["x"]) for key in keys],
            "c_y_mm": [m_to_mm(key["y"]) for key in keys],
            "c_z_mm": [m_to_mm(key["z"]) for key in keys],
            "c_yaw_mdeg": [yaw_to_mdeg(key["yaw"]) for key in keys],
            "c_pitch_mdeg": [round(float(key["pitch"]) * 1000) for key in keys],
            "c_fov_mdeg": [round(float(key["fov"]) * 1000) for key in keys],
            "c_focus_mm": [m_to_mm(key["focus"]) for key in keys],
        }
        ok, order = self.bridge.enqueue_order("camera.play", args, role="client")
        if not ok:
            return _fail("plan_too_large", "La orden no cabe en el cable")
        self._in_flight = order["op_id"]
        return {"ok": True, "op_id": order["op_id"]}
