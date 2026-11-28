"""Cámara del cliente falso (brief F4 parte 1, §4.2 y §6).

Cumple el contrato del mod salvo la interpolación: la pose es la de la clave 0 mientras
suena el camino y la de la última clave cuando acaba. El tiempo es el reloj de pared
desde el `play`. Solo pruebas.
"""
import threading
import time

CAM_MAX_KEYS = 32
ARRAYS = ("c_t_ms", "c_x_mm", "c_y_mm", "c_z_mm", "c_yaw_mdeg", "c_pitch_mdeg",
          "c_fov_mdeg", "c_focus_mm")
INACTIVE = {"active": 0, "playing": 0, "cam_id": "", "t_ms": 0, "dur_ms": 0,
            "pose": [0, 0, 0, 0, 0, 0]}


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def check_play_args(args):
    """'' si los args de `camera.play` valen, o 'bad_args' (§4.2)."""
    if not isinstance(args, dict) or not isinstance(args.get("cam_id"), str) or not args["cam_id"]:
        return "bad_args"
    arrays = [args.get(k) for k in ARRAYS]
    if not all(isinstance(a, list) and all(_int(v) for v in a) for a in arrays):
        return "bad_args"
    n = len(arrays[0])
    if n < 1 or n > CAM_MAX_KEYS or any(len(a) != n for a in arrays):
        return "bad_args"
    t, _x, _y, _z, yaw, pitch, fov, focus = arrays
    if t[0] != 0 or any(t[i] <= t[i - 1] for i in range(1, n)):
        return "bad_args"
    for i in range(n):
        if not (0 <= yaw[i] < 360000 and -90000 <= pitch[i] <= 90000
                and 0 < fov[i] < 180000 and focus[i] > 0):
            return "bad_args"
    return ""


class FakeCamera:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        # (cam_id, claves (t, x, y, z, yaw, pitch, fov, focus), t0); la pose son x..fov
        self._path = None
        # solo pruebas: la siguiente lectura `done` sale rota (K14)
        self.break_next_read = False

    def _state_locked(self):
        if self._path is None:
            return dict(INACTIVE, pose=list(INACTIVE["pose"]))
        cam_id, keys, t0 = self._path
        dur = keys[-1][0]
        t = int((self.clock() - t0) * 1000)
        if t >= dur:
            return {"active": 1, "playing": 0, "cam_id": cam_id, "t_ms": dur, "dur_ms": dur,
                    "pose": list(keys[-1][1:7])}
        return {"active": 1, "playing": 1, "cam_id": cam_id, "t_ms": max(t, 0), "dur_ms": dur,
                "pose": list(keys[0][1:7])}

    def _read_locked(self):
        read = {"cam": self._state_locked()}
        if self.break_next_read:
            self.break_next_read = False
            read["cam"]["playing"] = 2
        return read

    def execute(self, verb, args):
        """(status, reason, read) de una orden del cliente."""
        if not isinstance(args, dict) or args.get("f2") != 1 \
                or verb not in ("camera.play", "camera.stop", "camera.read"):
            return "rejected", "unknown_verb", {}
        with self._lock:
            if verb == "camera.play":
                bad = check_play_args(args)
                if bad:
                    return "rejected", bad, {}
                if self._state_locked()["playing"] == 1:
                    return "rejected", "busy", {}
                cols = [args[k] for k in ARRAYS]
                keys = [tuple(c[i] for c in cols) for i in range(len(cols[0]))]
                self._path = (args["cam_id"], keys, self.clock())
            elif verb == "camera.stop":
                self._path = None
            return "done", None, self._read_locked()

    def state(self):
        with self._lock:
            return self._state_locked()
