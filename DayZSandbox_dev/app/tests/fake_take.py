"""La toma del mod falso, servidor y cliente (brief F5 parte 1, §3.4 y §6).

Oráculo de Claude. Cumple el contrato del cable de la toma. El GO es una llamada directa
del servidor falso al cliente falso (el RPC real depende de S-toma), y la tecla del juego
y el hombre muerto se simulan con ganchos. Solo pruebas.
"""
import threading
import time

from app.tests.fake_camera import ARRAYS, check_play_args

CHECKS = ("scene", "marks", "wardrobe", "env", "director")
LIVE = ("armada", "rodando")


def _str(v):
    return isinstance(v, str) and v != ""


class FakeTake:
    def __init__(self, fake, clock=time.monotonic):
        self.fake = fake
        self.clock = clock
        self._lock = threading.Lock()
        self.take = None  # {take_id, state, origin, dur_ms, bad, t_ms, t0}
        self.loaded = None  # (take_id, cam_hash, args de camera.play) en el cliente
        self.pending_stop = set()  # take_id que el cliente tiene como parada pendiente
        self.events = []  # (tipo, take_id): go, terminada, parada
        # ganchos de prueba
        self.fail_checks = []
        self.deadman_ms = 5000
        self.hold_go = False
        self._held_go = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)

    # --- estado -----------------------------------------------------------
    def _read_locked(self):
        t = self.take
        if t is None:
            return {"take": {"take_id": "", "state": "ninguna", "origin": "", "t_ms": 0,
                             "dur_ms": 0, "bad": []}}
        t_ms = t["t_ms"]
        if t["state"] == "rodando":
            t_ms = min(max(int((self.clock() - t["t0"]) * 1000), 0), t["dur_ms"])
        return {"take": {"take_id": t["take_id"], "state": t["state"], "origin": t["origin"],
                         "t_ms": t_ms, "dur_ms": t["dur_ms"], "bad": list(t["bad"])}}

    def _end_locked(self, state, origin):
        t = self.take
        if t["state"] == "rodando":
            t["t_ms"] = min(max(int((self.clock() - t["t0"]) * 1000), 0), t["dur_ms"])
        if state == "terminada":
            t["t_ms"] = t["dur_ms"]
        t["state"] = state
        t["origin"] = origin
        self.events.append((state, t["take_id"]))
        # D2: cualquier final suelta la cámara del cliente
        self.fake.camera.execute("camera.stop", {"f2": 1})

    def _advance_locked(self):
        t = self.take
        if t is None:
            return
        if t["state"] == "rodando" and (self.clock() - t["t0"]) * 1000 >= t["dur_ms"]:
            self._end_locked("terminada", "")
            return
        if t["state"] in LIVE:
            age = self.fake.server.lease_age_ms()
            if age is not None and age > self.deadman_ms:
                self._end_locked("parada", "hombre_muerto")

    def _tick_loop(self):
        while not self._stop.wait(0.02):
            with self._lock:
                self._advance_locked()

    def state(self):
        with self._lock:
            self._advance_locked()
            return self._read_locked()["take"]

    # --- cliente ------------------------------------------------------------
    def _client_go_locked(self, take_id):
        if take_id in self.pending_stop:
            return
        t = self.take
        if self.loaded is None or self.loaded[0] != take_id or t is None \
                or t["take_id"] != take_id or t["state"] != "rodando":
            return
        self.fake.camera.execute("camera.play", dict(self.loaded[2], f2=1))

    def release_go(self):
        """Entrega el GO retenido con `hold_go`."""
        with self._lock:
            take_id, self._held_go = self._held_go, None
            if take_id is not None:
                self._client_go_locked(take_id)

    def press_stop_key(self, menu_open=False):
        """La tecla de parada del cliente (#33). Devuelve si tuvo efecto."""
        with self._lock:
            self._advance_locked()
            t = self.take
            if menu_open or t is None or t["state"] not in LIVE:
                return False
            if self.loaded is None or self.loaded[0] != t["take_id"]:
                return False
            self.pending_stop.add(t["take_id"])
            self.fake.camera.execute("camera.stop", {"f2": 1})
            # take_stop_key: en el falso el servidor lo recibe en el acto
            self._end_locked("parada", "juego")
            return True

    # --- órdenes ----------------------------------------------------------
    def execute(self, role, verb, args):
        """(status, reason, read) de una orden `take.*`."""
        if not isinstance(args, dict) or args.get("f2") != 1:
            return "rejected", "unknown_verb", {}
        with self._lock:
            self._advance_locked()
            if role == "client":
                if verb != "take.cam_load":
                    return "rejected", "unknown_verb", {}
                cam_args = {k: args.get(k) for k in ("cam_id",) + ARRAYS}
                if check_play_args(cam_args) or not _str(args.get("take_id")) \
                        or not _str(args.get("cam_hash")):
                    return "rejected", "bad_args", {}
                self.loaded = (args["take_id"], args["cam_hash"], cam_args)
                return "done", None, {"ready": {"take_id": args["take_id"],
                                                "cam_hash": args["cam_hash"]}}
            if verb == "take.read":
                return "done", None, self._read_locked()
            take_id = args.get("take_id")
            if verb == "take.prepare":
                if self.take is not None and self.take["state"] in LIVE:
                    return "rejected", "busy", {}
                dur = args.get("dur_ms")
                if not _str(take_id) or not isinstance(dur, int) or isinstance(dur, bool) or dur < 0:
                    return "rejected", "bad_args", {}
                self.take = {"take_id": take_id, "state": "preparada", "origin": "",
                             "dur_ms": dur, "t_ms": 0, "t0": None,
                             "bad": [c for c in CHECKS if c in self.fail_checks]}
                return "done", None, self._read_locked()
            cur = self.take if self.take is not None and self.take["take_id"] == take_id else None
            if verb == "take.arm":
                if cur is None or cur["state"] != "preparada" or cur["bad"]:
                    return "rejected", "bad_state", {}
                if self.loaded is None or self.loaded[0] != take_id \
                        or self.loaded[1] != args.get("cam_hash"):
                    return "rejected", "cam_not_ready", {}
                cur["state"] = "armada"
                return "done", None, self._read_locked()
            if verb == "take.go":
                if cur is None or cur["state"] != "armada":
                    return "rejected", "bad_state", {}
                cur["state"] = "rodando"
                cur["t0"] = self.clock()
                self.events.append(("go", take_id))
                if self.hold_go:
                    self._held_go = take_id
                else:
                    self._client_go_locked(take_id)
                return "done", None, self._read_locked()
            if verb == "take.stop":
                if cur is None:
                    return "rejected", "unknown_take", {}
                if cur["state"] in ("preparada",) + LIVE:
                    self._end_locked("parada", "web")
                return "done", None, self._read_locked()
            return "rejected", "unknown_verb", {}
