"""Toma viva en el backend (F5 parte 1 §3-§4): TakeLive.

Estado solo bajo el lock del bridge.
"""
import copy
import hashlib
import json

from app.backend.camera_live import play_args_from_keys

CHECKS = ("scene", "marks", "wardrobe", "env", "director")
TAKE_LIVE = ("preparando", "armada", "rodando")
TAKE_READ_MS = 250
_CAM_NINE = ("cam_id", "c_t_ms", "c_x_mm", "c_y_mm", "c_z_mm", "c_yaw_mdeg",
             "c_pitch_mdeg", "c_fov_mdeg", "c_focus_mm")
_TAKE_KEYS = ("take_id", "state", "origin", "t_ms", "dur_ms", "bad")
_READY_KEYS = ("take_id", "cam_hash")
_STATES = ("ninguna", "preparada", "armada", "rodando", "terminada", "parada")
_ORIGINS = ("", "web", "juego", "hombre_muerto")
_FAIL_VERBS = ("take.cam_load", "take.prepare", "take.arm", "take.go")


def _is_int(val):
    return isinstance(val, int) and not isinstance(val, bool)


def _fail(code, msg, pointer=""):
    return {"ok": False, "code": code, "pointer": pointer, "msg": msg}


def valid_take_read(read):
    """Forma de la lectura de toma (brief §3.2)."""
    if not isinstance(read, dict) or set(read) != {"take"}:
        return False
    take = read.get("take")
    if not isinstance(take, dict) or set(take) != set(_TAKE_KEYS):
        return False
    take_id = take.get("take_id")
    if not isinstance(take_id, str) or len(take_id.encode("utf-8")) > 64:
        return False
    state = take.get("state")
    if state not in _STATES:
        return False
    origin = take.get("origin")
    if origin not in _ORIGINS:
        return False
    if (origin != "") != (state == "parada"):
        return False
    t_ms, dur_ms = take.get("t_ms"), take.get("dur_ms")
    if not _is_int(t_ms) or not _is_int(dur_ms) or t_ms < 0 or t_ms > dur_ms:
        return False
    if state in ("ninguna", "preparada", "armada") and t_ms != 0:
        return False
    if state == "terminada" and t_ms != dur_ms:
        return False
    bad = take.get("bad")
    if not isinstance(bad, list):
        return False
    if len(bad) != len(set(bad)):
        return False
    if any(name not in CHECKS for name in bad):
        return False
    if bad and state != "preparada":
        return False
    if state == "ninguna":
        return take_id == "" and dur_ms == 0
    return take_id != ""


def valid_ready_read(read):
    """Forma de la lectura de take.cam_load (brief §3.3)."""
    if not isinstance(read, dict) or set(read) != {"ready"}:
        return False
    ready = read.get("ready")
    if not isinstance(ready, dict) or set(ready) != set(_READY_KEYS):
        return False
    tid, h = ready.get("take_id"), ready.get("cam_hash")
    return isinstance(tid, str) and tid != "" and isinstance(h, str) and h != ""


def cam_hash_of(cam_args):
    blob = json.dumps(cam_args, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


class TakeLive:
    """Coordinador de toma (F5) acoplado a un Bridge y su Backend."""

    def __init__(self, bridge):
        self.bridge = bridge
        self.backend = bridge.backend
        self._n = 0
        self._take = None

    def _live(self):
        t = self._take
        return t is not None and t["state"] in TAKE_LIVE

    def _sync_locked(self):
        t = self._take
        self.backend.take_state = "libre" if t is None else t["state"]

    def snapshot_locked(self):
        if self._take is None:
            return {"ok": True, "take": None}
        t = self._take
        origin = t["origin"] if t["state"] == "parada" else None
        reason = t["reason"] if t["state"] == "fallida" else None
        return {"ok": True, "take": {
            "take_id": t["take_id"], "doc_id": t["doc_id"], "rev": t["rev"],
            "cam_id": t["cam_id"], "state": t["state"], "origin": origin,
            "reason": reason, "bad": list(t["bad"]), "t_ms": t["t_ms"],
            "dur_ms": t["dur_ms"],
        }}

    def _order_live_locked(self, verb):
        for o in self.bridge.orders.values():
            if o.get("verb") == verb and o.get("bstate") in ("pendiente", "ejecutando"):
                return o
        return None

    def _finish_locked(self, state, origin=None, reason=None):
        if not self._live():
            return
        t = self._take
        t["state"] = state
        t["origin"] = origin if state == "parada" else None
        t["reason"] = reason if state == "fallida" else None
        self._sync_locked()

    def _maybe_arm_locked(self):
        t = self._take
        if t is None or t["state"] != "preparando" or t.get("stop_requested"):
            return
        if not t.get("prepare_ok") or not t.get("cam_ready"):
            return
        snap = self.backend.store.snapshot()
        if snap["rev"] != t["rev"] or snap["hash"] != t["hash"]:
            self._finish_locked("fallida", reason="doc_changed")
            return
        args = {"f2": 1, "take_id": t["take_id"], "cam_hash": t["cam_hash"]}
        self.bridge.enqueue_order("take.arm", args, internal=True, role="server")

    def on_dropped_locked(self, order, reason):
        if not isinstance(order, dict) or order.get("verb") not in _FAIL_VERBS:
            return
        if not self._live():
            return
        tid = (order.get("args") or {}).get("take_id")
        if tid != self._take["take_id"]:
            return
        self._finish_locked("fallida", reason=reason)

    def on_server_hello_locked(self, peer_record):
        if not self._live():
            return
        epoch = peer_record.get("epoch") if isinstance(peer_record, dict) else None
        if epoch is not None and epoch != self._take.get("epoch"):
            self._finish_locked("fallida", reason="mundo_reiniciado")

    def on_result_locked(self, order, status, reason, read):
        if not isinstance(order, dict):
            return
        verb = order.get("verb")
        if not isinstance(verb, str) or not verb.startswith("take."):
            return
        t = self._take
        if t is None:
            return
        args = order.get("args") or {}
        if verb == "take.cam_load":
            oid = args.get("take_id")
        elif verb == "take.read":
            oid = None if not isinstance(read, dict) else (read.get("take") or {}).get("take_id")
        else:
            oid = args.get("take_id")
        if verb != "take.read" and oid != t["take_id"]:
            return
        if verb == "take.read" and status == "done":
            rec = read.get("take") if isinstance(read, dict) else None
            if not isinstance(rec, dict) or rec.get("take_id") != t["take_id"]:
                return
        if t["state"] not in TAKE_LIVE:
            return
        if verb in ("take.read", "take.stop") and status in ("rejected", "error"):
            if verb == "take.stop" and status == "rejected" and reason == "unknown_take" \
                    and t["state"] == "preparando":
                self._finish_locked("parada", origin="web")
            return
        if status in ("rejected", "error"):
            if verb in _FAIL_VERBS:
                self._finish_locked("fallida", reason=reason)
            return
        if status != "done":
            return
        rec = (read or {}).get("take") if verb != "take.cam_load" else None
        if verb == "take.cam_load":
            ready = (read or {}).get("ready") or {}
            if ready.get("take_id") != t["take_id"] or ready.get("cam_hash") != t["cam_hash"]:
                self._finish_locked("fallida", reason="cam_not_ready")
                return
            t["cam_ready"] = True
            self._maybe_arm_locked()
            return
        if isinstance(rec, dict) and rec.get("state") in ("terminada", "parada"):
            t["t_ms"] = rec.get("t_ms", t["t_ms"])
            t["dur_ms"] = rec.get("dur_ms", t["dur_ms"])
            origin = rec.get("origin") or None
            if rec["state"] == "parada":
                self._finish_locked("parada", origin=origin)
            else:
                self._finish_locked("terminada")
            return
        if verb == "take.prepare":
            bad = list(rec.get("bad") or []) if isinstance(rec, dict) else []
            t["bad"] = bad
            if bad:
                self._finish_locked("fallida", reason="checks")
                return
            t["prepare_ok"] = True
            self._maybe_arm_locked()
            return
        if verb == "take.arm" and isinstance(rec, dict) and rec.get("state") == "armada":
            t["state"] = "armada"
            self._sync_locked()
            return
        if verb == "take.go" and isinstance(rec, dict) and rec.get("state") == "rodando":
            t["state"] = "rodando"
            self._sync_locked()
            return
        if verb == "take.read" and isinstance(rec, dict) and rec.get("state") == "rodando":
            t["t_ms"] = rec.get("t_ms", t["t_ms"])
            t["dur_ms"] = rec.get("dur_ms", t["dur_ms"])

    def tick_locked(self):
        if not self._live():
            return
        srv = self.bridge.peers.get("server") or {}
        if not srv or srv.get("lost"):
            return
        t = self._take
        now = self.bridge._now()
        if t.get("stop_requested") and self._order_live_locked("take.stop") is None:
            self.bridge.enqueue_order(
                "take.stop", {"f2": 1, "take_id": t["take_id"]},
                internal=True, role="server")
        if t["state"] in ("armada", "rodando"):
            if self._order_live_locked("take.read") is None:
                last = t.get("last_read_mono")
                if last is None or (now - last) * 1000.0 >= TAKE_READ_MS:
                    ok, _order = self.bridge.enqueue_order(
                        "take.read", {"f2": 1}, internal=True, role="server")
                    if ok:
                        t["last_read_mono"] = now

    def request_prepare_locked(self, doc_id, cam_id):
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
            return _fail("no_director", "El cliente no esta en el mundo")
        if self._live():
            return _fail("take_busy", "Hay una toma en curso")
        ops = list(self.backend.ops.values())
        last = ops[-1] if ops else None
        verb = last.get("verb") if last else None
        if last is None or verb not in (None, "scene.apply") \
                or last.get("state") != "observado" \
                or last.get("rev") != snap["rev"] or last.get("hash") != snap["hash"]:
            return _fail("scene_not_observed", "Aplica la escena antes de preparar")
        all_keys = cam.get("keys") if isinstance(cam.get("keys"), list) else []
        if len(all_keys) < 2:
            return _fail("invalid", "Una camara con una sola clave no sirve",
                         "/cameras/%d/keys" % idx)
        built = play_args_from_keys(self.bridge, cam_id, idx, all_keys,
                                    list(range(len(all_keys))), collapse_t=False)
        if not built.get("ok"):
            return built
        play_args = built["args"]
        cam_args = {k: copy.deepcopy(play_args[k]) for k in _CAM_NINE}
        cam_hash = cam_hash_of(cam_args)
        dur_ms = play_args["c_t_ms"][-1]
        self._n += 1
        take_id = "tk-%s-%d" % (self.bridge.session, self._n)
        load_args = dict(cam_args, f2=1, take_id=take_id, cam_hash=cam_hash)
        prep_args = {"f2": 1, "take_id": take_id, "cam_id": cam_id,
                     "rev": snap["rev"], "hash": snap["hash"], "dur_ms": dur_ms}
        ok1, o1 = self.bridge.enqueue_order("take.cam_load", load_args, role="client")
        if not ok1:
            self._n -= 1
            return _fail("plan_too_large", "La orden no cabe en el cable")
        ok2, _o2 = self.bridge.enqueue_order(
            "take.prepare", prep_args, internal=True, role="server")
        if not ok2:
            self.bridge.orders.pop((self.bridge.session, o1["op_id"]), None)
            self._n -= 1
            return _fail("plan_too_large", "La orden no cabe en el cable")
        srv = self.bridge.peers.get("server") or {}
        self._take = {
            "take_id": take_id, "doc_id": snap["doc_id"], "rev": snap["rev"],
            "hash": snap["hash"], "cam_id": cam_id, "cam_hash": cam_hash,
            "state": "preparando", "origin": None, "reason": None, "bad": [],
            "t_ms": 0, "dur_ms": dur_ms, "cam_ready": False, "prepare_ok": False,
            "stop_requested": False, "last_read_mono": None,
            "epoch": srv.get("epoch"),
        }
        self._sync_locked()
        return {"ok": True, "take_id": take_id}

    def request_go_locked(self, take_id):
        t = self._take
        if t is None or t["take_id"] != take_id:
            return _fail("not_found", "No existe esa toma", "/take_id")
        if t["state"] != "armada" or t.get("stop_requested"):
            return _fail("take_state", "La toma no esta armada")
        ok, _order = self.bridge.enqueue_order(
            "take.go", {"f2": 1, "take_id": take_id}, internal=True, role="server")
        if not ok:
            return _fail("plan_too_large", "La orden no cabe en el cable")
        return {"ok": True}

    def request_stop_locked(self, take_id):
        t = self._take
        if t is None or t["take_id"] != take_id:
            return _fail("not_found", "No existe esa toma", "/take_id")
        if t["state"] not in TAKE_LIVE:
            return _fail("take_state", "La toma no esta viva")
        t["stop_requested"] = True
        if self._order_live_locked("take.stop") is None:
            self.bridge.enqueue_order(
                "take.stop", {"f2": 1, "take_id": take_id},
                internal=True, role="server")
        return {"ok": True}
