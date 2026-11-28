"""Bridge dsbx1 (F1b-bridge, lado backend): listener propio en 127.0.0.1.

Protocolo entre el backend y los dos peers del mod. Solo biblioteca estandar.
Contrato: plans/2026-11-14-m1-f1b-bridge-brief.md §2-§5.
El Bridge comparte el candado del almacen (store.lock) con el Backend para
que set_op_state, apply y las entregas no se crucen con candados invertidos.
"""
import copy
import hashlib
import hmac
import json
import re
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

WIRE_CAP = 3500
# Tope de cada cadena de una orden. El motor corta a 1023 lo que un peer lee con JsonSerializer
# (partida diag de F0.3-0, BASE-01; su brief, §15, D10). La regla del proyecto es 1000, con
# margen, y aqui se cuenta sobre la forma escapada del cable, que nunca es menor que la decodificada.
STR_CAP = 1000
DRAIN_S = 2.0  # tope total para descartar el cuerpo de una peticion rechazada (como C-02 de F1b-web)
BODY_S = 2.0  # tope total para leer el cuerpo de una peticion aceptada
MAX_DRAIN = 1024 * 1024  # por encima no se descarta: se responde y se cierra
_HEX = re.compile(r"[0-9a-fA-F]+")
_KEY_IN_PATH = re.compile(r"([?&]key=)[^&\s\"']*")


def _is_hex(value, n):
    return isinstance(value, str) and len(value) == n and _HEX.fullmatch(value) is not None


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _max_str_bytes(obj):
    """Bytes de la cadena mas larga dentro de obj (claves y valores, en profundidad), contados
    como salen en el cable: escapada y en UTF-8, sin las comillas."""
    if isinstance(obj, str):
        return len(json.dumps(obj, ensure_ascii=False).encode("utf-8")) - 2
    if isinstance(obj, dict):
        return max([0] + [max(_max_str_bytes(k), _max_str_bytes(v)) for k, v in obj.items()])
    if isinstance(obj, (list, tuple)):
        return max([0] + [_max_str_bytes(v) for v in obj])
    return 0


def valid_world_read(read):
    """Forma del estado del mundo (§4): epoch/generation/registry_n/registry_sha256."""
    if not isinstance(read, dict):
        return False
    if not _is_hex(read.get("epoch"), 32):
        return False
    if "generation" not in read:
        return False
    gen = read.get("generation")
    if gen is not None:
        if not isinstance(gen, dict):
            return False
        if not _is_hex(gen.get("session"), 16):
            return False
        if not isinstance(gen.get("op_id"), str) or not gen.get("op_id"):
            return False
        if not _is_int(gen.get("rev")):
            return False
        if not _is_hex(gen.get("hash"), 64):
            return False
    if not _is_int(read.get("registry_n")) or read.get("registry_n") < 0:
        return False
    if not _is_hex(read.get("registry_sha256"), 64):
        return False
    return True


def _err(status, error):
    return status, {"ok": False, "error": error}


class Bridge:
    """Listener dsbx1. Arranca su hilo servidor y (si se pide) el barrido al crearse."""

    def __init__(self, backend, peer_key, port=0, lease_ms=3000, hold_ms=2000,
                 retry_ms=2000, ttl_ms=10000, queue_max=32,
                 read_retry_ms=(1000, 2000, 4000, 8000), sweep_ms=250,
                 clock=None, log=None, enable_sweeper=True):
        if not peer_key or not isinstance(peer_key, str):
            raise ValueError("peer_key debe ser no vacia")
        self.backend = backend
        self._peer_key = peer_key
        self.clock = clock if clock is not None else backend.clock
        # Origen de los ms publicos (now_ms, issued_ms): el arranque del bridge. Asi son enteros
        # pequenos que un peer de Enforce lee en int de 32 bits sin perder las diferencias
        # (brief de F1b-peers, P-02); la logica interna de TTL sigue en segundos absolutos.
        self._t0 = float(self.clock())
        self.log = log if log is not None else getattr(backend, "log", sys.stderr)
        self.lease_ms = int(lease_ms)
        self.hold_ms = int(hold_ms)
        self.retry_ms = int(retry_ms)
        self.ttl_ms = int(ttl_ms)
        self.queue_max = int(queue_max)
        if isinstance(read_retry_ms, (int, float)):
            read_retry_ms = (int(read_retry_ms),)
        self.read_retry_ms = tuple(int(x) for x in read_retry_ms) or (8000,)
        self.sweep_ms = int(sweep_ms)
        self.drain_s = DRAIN_S
        self.body_s = BODY_S
        self.session = secrets.token_hex(8)
        self.lock = backend.store.lock
        self.cond = threading.Condition(self.lock)
        self._conns = set()
        self._conns_lock = threading.Lock()
        self.peers = {}  # rol -> dict de peer vigente
        self.orders = {}  # (session, op_id) -> orden interna
        self._seq = 0
        self._rd_n = 0
        self.reconciled = False
        self.world = None
        self.catalog = None
        self._catalog_attempts = {}
        self.events = []
        self._read_next_at = None
        self._read_backoff = 0
        self._closed = False
        self._stop = threading.Event()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", int(port)), _BridgeHandler)
        self.httpd.daemon_threads = True
        self.httpd.block_on_close = False
        self.httpd.bridge = self
        self._thread = threading.Thread(target=self.httpd.serve_forever,
                                        kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        self._sweeper = None
        if enable_sweeper:
            self._sweeper = threading.Thread(target=self._sweep_loop, daemon=True)
            self._sweeper.start()

    @property
    def port(self):
        return self.httpd.server_address[1]

    def shutdown(self):
        # `_closed` cambia bajo el mismo candado que el registro de conexiones: una conexion
        # aceptada que se registre despues ya ve el cierre y se corta sola (setup), y una que
        # se registro antes esta en la copia (H4, ronda 2 de Sol).
        with self._conns_lock:
            if self._closed:
                return
            self._closed = True
            conns = list(self._conns)
        self._stop.set()
        with self.cond:
            self.cond.notify_all()
        for conn in conns:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        try:
            self.httpd.shutdown()
        finally:
            self.httpd.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=5)
        if self._sweeper is not None and self._sweeper.is_alive():
            self._sweeper.join(timeout=5)

    # --- utilidades internas (candado ya tomado) -----------------------
    def _now(self):
        return float(self.clock())

    def _now_ms(self):
        return self._ms(self._now())

    def _ms(self, t):
        """ms enteros desde el arranque del bridge para un instante t del reloj (segundos)."""
        return int((t - self._t0) * 1000)

    def _log_line(self, line):
        try:
            self.log.write(line + "\n")
            flush = getattr(self.log, "flush", None)
            if flush is not None:
                flush()
        except Exception:
            pass

    def _register_event(self, kind, data):
        self.events.append({"event": kind, "data": data})
        self._log_line("bridge event %s" % kind)

    def peer(self, role):
        with self.lock:
            p = self.peers.get(role)
            return dict(p) if p is not None else None

    def client_in_world(self):
        with self.lock:
            srv = self.peers.get("server")
            cli = self.peers.get("client")
            return bool(self.reconciled and srv and cli and not cli.get("lost")
                        and cli.get("epoch") == srv.get("epoch"))

    def live_scene_count(self):
        with self.lock:
            return sum(1 for o in self.orders.values()
                       if o["verb"] in ("scene.apply", "scene.reset")
                       and o["bstate"] in ("pendiente", "ejecutando"))

    # --- cola -----------------------------------------------------------
    def _wire_poll_len(self, order_public, now_ms):
        body = json.dumps({"ok": True, "now_ms": now_ms, "ops": [order_public]},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return len(body)

    def _public_order(self, order, now_ms):
        peer = self.peers.get(order.get("role") or "server") or {}
        return {
            "op_id": order["op_id"], "session": self.session,
            "conn": order["conn"],
            "epoch": order["epoch"] if order["epoch"] is not None else peer.get("epoch", "0" * 32),
            "inst": order["inst"] if order["inst"] is not None else peer.get("inst", "0" * 32),
            "verb": order["verb"], "args": copy.deepcopy(order["args"]),
            "issued_ms": order["issued_ms"], "ttl_ms": order["ttl_ms"],
        }

    def enqueue_order(self, verb, args, op_id=None, ttl_ms=None, internal=False, role="server"):
        """Encola una orden. Devuelve (True, orden) o (False, 'wire_cap_exceeded')."""
        with self.cond:
            if op_id is None:
                self._rd_n += 1
                op_id = "rd-%d" % self._rd_n
            now = self._now()
            rec = self.peers.get(role) or {}
            order = {
                "op_id": op_id, "verb": verb, "args": copy.deepcopy(args),
                "role": role, "internal": bool(internal),
                "conn": int(rec.get("conn", 0)),
                "epoch": rec.get("epoch"), "inst": rec.get("inst"),
                "session": self.session, "issued_ms": self._ms(now),
                "enqueued_mono": now, "ttl_ms": int(ttl_ms if ttl_ms is not None else self.ttl_ms),
                "bstate": "pendiente", "delivered_inst": None, "last_delivery": None,
                "result_seen": False, "priority": 0 if internal else 1,
            }
            order["_seq"] = self._seq
            self._seq += 1
            if verb == "state.read":
                order["priority"] = 0
            public = self._public_order(order, self._ms(now))
            if self._wire_poll_len(public, self._ms(now)) > WIRE_CAP:
                return False, "wire_cap_exceeded"
            if _max_str_bytes(public) > STR_CAP:
                # el peer la leeria cortada: tampoco cabe en el cable (brief de F1b-peers §3.5)
                return False, "wire_cap_exceeded"
            self.orders[(self.session, op_id)] = order
            self.cond.notify_all()
            return True, order

    def enqueue_scene_apply(self, op_id, doc_id, rev, hash_):
        return self.enqueue_order("scene.apply", {"doc_id": doc_id, "rev": rev, "hash": hash_},
                                  op_id=op_id, internal=False)

    def _active_read_locked(self):
        for o in self.orders.values():
            if o["verb"] == "state.read" and o["bstate"] in ("pendiente", "ejecutando"):
                srv = self.peers.get("server")
                if srv and o["conn"] == srv.get("conn"):
                    return o
        return None

    def _trigger_state_read_locked(self):
        srv = self.peers.get("server")
        if not srv or srv.get("lost"):
            return None
        if self._active_read_locked() is not None:
            return None
        self._read_next_at = None
        sl = getattr(self.backend, "scene_live", None)
        args = sl.state_read_args_locked() if sl is not None else {}
        ok, order = self.enqueue_order("state.read", args, internal=True)
        return order if ok else None

    def _schedule_read_retry_locked(self):
        if not self.read_retry_ms:
            return
        idx = min(self._read_backoff, len(self.read_retry_ms) - 1)
        self._read_next_at = self._now() + self.read_retry_ms[idx] / 1000.0
        self._read_backoff = min(self._read_backoff + 1, len(self.read_retry_ms) - 1)

    def _internal_dropped_locked(self, order, reason):
        """F3-offline-2 §4.4: avisa a SceneLive de una orden interna descartada."""
        sl = getattr(self.backend, "scene_live", None)
        if sl is not None:
            sl.on_internal_dropped_locked(order, reason)

    def _transition_conn_orders_locked(self, new_conn, new_epoch):
        for order in list(self.orders.values()):
            if order.get("role", "server") != "server":
                continue
            if order["conn"] == new_conn:
                continue
            if order["internal"]:
                if order["bstate"] in ("pendiente", "ejecutando"):
                    order["bstate"] = "descartada"
                    self._internal_dropped_locked(
                        order, "mundo_reiniciado" if (order["epoch"] and new_epoch
                                                      and order["epoch"] != new_epoch)
                        else "conexion_perdida")
                continue
            if order["bstate"] not in ("pendiente", "ejecutando", "parcial"):
                continue
            reason = "mundo_reiniciado" if (order["epoch"] and new_epoch
                                            and order["epoch"] != new_epoch) else "conexion_perdida"
            if order["bstate"] == "parcial":
                # §4.4 (solo F2): un `parcial` de otro `epoch` se queda
                # `parcial/mundo_reiniciado` y no se reconcilia ni se compensa. Con el
                # mismo epoch, la lectura del mismo mundo puede reconciliarlo. Las
                # ordenes F1 siguen como en F1b-bridge.
                sl = getattr(self.backend, "scene_live", None)
                if reason == "mundo_reiniciado" and sl is not None and sl.is_f2_order(order) \
                        and order["op_id"] in self.backend.ops:
                    self.backend.set_op_state(order["op_id"], "parcial", "backend", reason)
                continue
            if order["bstate"] == "pendiente":
                order["bstate"] = "terminal"
                if order["verb"] in ("scene.apply", "scene.reset") and order["op_id"] in self.backend.ops:
                    self.backend.set_op_state(order["op_id"], "fallido", "backend", reason)
            else:
                order["bstate"] = "parcial"
                if order["verb"] in ("scene.apply", "scene.reset") and order["op_id"] in self.backend.ops:
                    self.backend.set_op_state(order["op_id"], "parcial", "backend", reason)

    # --- barrido --------------------------------------------------------
    def _sweep_loop(self):
        interval = max(self.sweep_ms, 10) / 1000.0
        while not self._stop.wait(interval):
            try:
                self.sweep()
            except Exception:
                pass

    def _check_server_loss_locked(self, t):
        srv = self.peers.get("server")
        if srv and not srv.get("lost") and srv.get("inflight", 0) == 0 \
                and srv.get("last_poll_mono") is not None \
                and (t - srv["last_poll_mono"]) * 1000.0 > self.lease_ms:
            old_conn = int(srv["conn"])
            new_conn = old_conn + 1
            for order in list(self.orders.values()):
                if order.get("role", "server") != "server":
                    continue
                if order["conn"] != old_conn:
                    continue
                if order["internal"]:
                    if order["bstate"] in ("pendiente", "ejecutando"):
                        order["bstate"] = "descartada"
                        self._internal_dropped_locked(order, "conexion_perdida")
                    continue
                if order["bstate"] == "pendiente":
                    order["bstate"] = "terminal"
                    if order["op_id"] in self.backend.ops:
                        self.backend.set_op_state(order["op_id"], "fallido", "backend", "conexion_perdida")
                elif order["bstate"] == "ejecutando":
                    order["bstate"] = "parcial"
                    if order["op_id"] in self.backend.ops:
                        self.backend.set_op_state(order["op_id"], "parcial", "backend", "conexion_perdida")
            srv["conn"] = new_conn
            srv["lost"] = True
            self.reconciled = False
            self._read_next_at = None
            return True
        return False

    def sweep(self, now=None):
        with self.cond:
            t = float(now) if now is not None else self._now()
            self._check_server_loss_locked(t)
            parcial_trigger = False
            for order in list(self.orders.values()):
                if order["bstate"] not in ("pendiente", "ejecutando"):
                    continue
                if (t - order["enqueued_mono"]) * 1000.0 <= order["ttl_ms"]:
                    continue
                if order["internal"]:
                    order["bstate"] = "descartada"
                    self._internal_dropped_locked(order, "sin_resultado")
                    if not self.reconciled or self._has_live_parcial_locked():
                        self._schedule_read_retry_locked()
                    continue
                if order.get("role") == "client":
                    order["bstate"] = "descartada"
                    cl = getattr(self.backend, "camera_live", None)
                    if cl is not None:
                        cl.on_dropped_locked(order, "sin_resultado")
                    continue
                if order["bstate"] == "pendiente":
                    order["bstate"] = "terminal"
                    if order["op_id"] in self.backend.ops:
                        self.backend.set_op_state(order["op_id"], "fallido", "backend", "no_entregada")
                else:
                    order["bstate"] = "parcial"
                    if order["op_id"] in self.backend.ops:
                        self.backend.set_op_state(order["op_id"], "parcial", "backend", "sin_resultado")
                    parcial_trigger = True
            if parcial_trigger:
                srv2 = self.peers.get("server")
                if srv2 and not srv2.get("lost"):
                    for order in self.orders.values():
                        if order["verb"] in ("scene.apply", "scene.reset") \
                                and order["bstate"] == "parcial" \
                                and order["conn"] == srv2.get("conn"):
                            self._trigger_state_read_locked()
                            break
            srv3 = self.peers.get("server")
            if srv3 and not srv3.get("lost") and self._read_next_at is not None \
                    and t >= self._read_next_at and self._active_read_locked() is None:
                if not self.reconciled or self._has_live_parcial_locked():
                    self._trigger_state_read_locked()
            self.cond.notify_all()

    def _has_live_parcial_locked(self):
        srv = self.peers.get("server")
        if not srv:
            return False
        sl = getattr(self.backend, "scene_live", None)
        if sl is not None and sl.has_unresolved_locked():
            return True
        return any(o["verb"] in ("scene.apply", "scene.reset") and o["bstate"] == "parcial"
                   and o["conn"] == srv.get("conn") for o in self.orders.values())

    # --- hello ------------------------------------------------------------
    def handle_hello(self, body):
        if not isinstance(body, dict):
            return _err(400, "bad_request")
        proto = body.get("proto")
        if not isinstance(proto, str):
            return _err(400, "bad_request")
        if proto != "dsbx1":
            return _err(409, "proto_mismatch")
        peer = body.get("peer")
        if peer not in ("server", "client"):
            return _err(400, "bad_request")
        inst, epoch = body.get("inst"), body.get("epoch")
        if not _is_hex(inst, 32) or not _is_hex(epoch, 32):
            return _err(400, "bad_request")
        if not isinstance(body.get("mod_ver"), str) or not body.get("mod_ver"):
            return _err(400, "bad_request")
        if body.get("build") not in ("retail", "diag"):
            return _err(400, "bad_request")
        if peer == "server":
            if not isinstance(body.get("map"), str):
                return _err(400, "bad_request")
            if not _is_int(body.get("world_size")) or body.get("world_size") < 0:
                return _err(400, "bad_request")
            modset = body.get("modset")
            if not isinstance(modset, list) or not all(isinstance(x, str) for x in modset):
                return _err(400, "bad_request")
            if body.get("actor_engine") not in ("expansion", "none"):
                return _err(400, "bad_request")
        with self.cond:
            old = self.peers.get(peer)
            new_conn = int(old["conn"]) + 1 if old else 1
            if peer == "server":
                self._transition_conn_orders_locked(new_conn, epoch)
            elif peer == "client":
                cl = getattr(self.backend, "camera_live", None)
                for order in list(self.orders.values()):
                    if order.get("role") != "client":
                        continue
                    if order.get("bstate") not in ("pendiente", "ejecutando"):
                        continue
                    order["bstate"] = "descartada"
                    if cl is not None:
                        cl.on_dropped_locked(order, "conexion_perdida")
            self.peers[peer] = {
                "peer": peer, "inst": inst, "epoch": epoch, "conn": new_conn,
                "mod_ver": body.get("mod_ver"), "build": body.get("build"),
                "map": body.get("map"), "world_size": body.get("world_size"),
                "modset": copy.deepcopy(body.get("modset")) if peer == "server" else None,
                "actor_engine": body.get("actor_engine"),
                "scene": body.get("scene") if peer == "server" else None,
                "last_poll_mono": self._now(), "inflight": 0, "lost": False,
            }
            if peer == "server":
                # C-03: un hello nuevo invalida los intentos de catalogo a medias.
                # Las paginas tienen que llegar dentro de la presentacion vigente;
                # el catalogo completo anterior lo invalida SceneLive (D4).
                self._catalog_attempts = {}
                self.reconciled = False
                self.world = None
                self._read_backoff = 0
                self._read_next_at = None
                sl = getattr(self.backend, "scene_live", None)
                if sl is not None:
                    sl.on_server_hello_locked(self.peers[peer])
                self._trigger_state_read_locked()
            self.cond.notify_all()
            return 200, {"ok": True, "session": self.session, "conn": new_conn,
                         "lease_ms": self.lease_ms, "hold_ms": self.hold_ms, "wire_cap": WIRE_CAP}

    # --- poll -------------------------------------------------------------
    def _check_peer_guard_locked(self, query):
        peer = query.get("peer")
        if peer not in ("server", "client"):
            return _err(400, "bad_request")
        inst = query.get("inst")
        session = query.get("session")
        conn_s = query.get("conn")
        if not isinstance(inst, str) or not inst or not isinstance(session, str) or not session \
                or conn_s is None:
            return _err(400, "bad_request")
        try:
            conn = int(conn_s)
        except (TypeError, ValueError):
            return _err(400, "bad_request")
        if str(conn) != str(conn_s).strip() and not (isinstance(conn_s, str) and conn_s.lstrip("-").isdigit()):
            return _err(400, "bad_request")
        if session != self.session:
            return _err(409, "hello_required")
        record = self.peers.get(peer)
        if record is None or record.get("lost"):
            return _err(409, "hello_required")
        if inst != record["inst"] or conn != int(record["conn"]):
            return _err(409, "hello_required")
        return None

    def handle_poll(self, query):
        deliver = query.get("deliver")
        if deliver is not None and deliver not in ("0", "1"):
            return _err(400, "bad_request")
        with self.cond:
            if query.get("peer") == "server":
                self._check_server_loss_locked(self._now())
            guard = self._check_peer_guard_locked(query)
            if guard is not None:
                return guard
            peer = query["peer"]
            record = self.peers[peer]
            record["last_poll_mono"] = self._now()
            if deliver == "0":
                return 200, {"ok": True, "now_ms": self._now_ms(), "ops": []}
            record["inflight"] = record.get("inflight", 0) + 1
            try:
                deadline = time.monotonic() + self.hold_ms / 1000.0
                while True:
                    if self._closed:
                        return 200, {"ok": True, "now_ms": self._now_ms(), "ops": []}
                    if self.peers.get(peer) is not record or record.get("lost"):
                        # el peer se presentó otra vez mientras este poll esperaba: es de una
                        # conexión anterior y recibe lo mismo que un poll nuevo de esa conexión
                        return _err(409, "hello_required")
                    candidate = self._pick_order_locked(peer, record)
                    if candidate is not None:
                        now_ms = self._now_ms()
                        public = self._public_order(candidate, now_ms)
                        payload = {"ok": True, "now_ms": now_ms, "ops": [public]}
                        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                        if len(raw) > WIRE_CAP:
                            self._register_event("wire_cap_exceeded", {"op_id": candidate["op_id"]})
                            return _err(500, "wire_cap_exceeded")
                        now = self._now()
                        if candidate["bstate"] == "pendiente":
                            candidate["bstate"] = "ejecutando"
                            candidate["delivered_inst"] = record["inst"]
                            candidate["inst"] = record["inst"]
                            candidate["epoch"] = record["epoch"] if peer == "server" else candidate["epoch"]
                            if peer == "server":
                                candidate["epoch"] = record["epoch"]
                            candidate["last_delivery"] = now
                            if candidate["verb"] in ("scene.apply", "scene.reset") \
                                    and candidate["op_id"] in self.backend.ops:
                                self.backend.set_op_state(candidate["op_id"], "ejecutando", "backend", "entregada")
                        else:
                            candidate["last_delivery"] = now
                        record["last_poll_mono"] = now
                        return 200, payload
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        record["last_poll_mono"] = self._now()
                        return 200, {"ok": True, "now_ms": self._now_ms(), "ops": []}
                    self.cond.wait(timeout=min(remaining, 0.05))
            finally:
                record["inflight"] = max(0, record.get("inflight", 1) - 1)

    def _pick_order_locked(self, peer, record):
        now = self._now()
        orders = sorted(self.orders.values(), key=lambda o: (o["priority"], o["_seq"]))
        for o in orders:
            if o.get("role", "server") != peer:
                continue
            if o["bstate"] == "ejecutando" and o["conn"] == record["conn"] \
                    and o["delivered_inst"] == record["inst"] and not o["result_seen"]:
                if (now - o["enqueued_mono"]) * 1000.0 > o["ttl_ms"]:
                    continue
                if o["last_delivery"] is not None and (now - o["last_delivery"]) * 1000.0 >= self.retry_ms:
                    return o
        for o in orders:
            if o.get("role", "server") != peer:
                continue
            if o["bstate"] == "ejecutando" and o["conn"] == record["conn"] and not o["result_seen"]:
                return None
        for o in orders:
            if o.get("role", "server") != peer:
                continue
            if o["bstate"] != "pendiente":
                continue
            if o["conn"] != int(record["conn"]):
                continue
            if (now - o["enqueued_mono"]) * 1000.0 > o["ttl_ms"]:
                continue
            if peer == "server" and o["verb"] in ("scene.apply", "scene.reset") and not self.reconciled:
                continue
            return o
        return None

    # --- result -----------------------------------------------------------
    def handle_result(self, query, body):
        peer = query.get("peer")
        if peer not in ("server", "client"):
            return _err(400, "bad_request")
        q_inst, q_session = query.get("inst"), query.get("session")
        if not isinstance(q_inst, str) or not q_inst or not isinstance(q_session, str) or not q_session:
            return _err(400, "bad_request")
        if q_session != self.session:
            return _err(409, "hello_required")
        if not isinstance(body, dict):
            return _err(400, "bad_request")
        op_id = body.get("op_id")
        b_session = body.get("session")
        epoch = body.get("epoch")
        status = body.get("status")
        reason = body.get("reason")
        dup = body.get("dup")
        read = body.get("read")
        if not isinstance(op_id, str) or not op_id or not isinstance(b_session, str) \
                or not _is_hex(epoch, 32) or status not in ("done", "rejected", "error") \
                or not isinstance(dup, bool) or not isinstance(read, dict) \
                or not (reason is None or isinstance(reason, str)):
            return _err(400, "bad_request")
        if status in ("rejected", "error") and not isinstance(reason, str):
            return _err(400, "bad_request")
        if b_session != self.session:  # §2.7: un resultado vale solo con la session actual
            return _err(400, "bad_request")
        with self.cond:
            order = self.orders.get((b_session, op_id))
            if order is None or order["role"] != peer:
                return _err(409, "unknown_op")
            if order["delivered_inst"] is None or q_inst != order["delivered_inst"]:
                return _err(409, "unknown_op")
            if epoch != order["epoch"]:
                return _err(400, "bad_request")
            sl = getattr(self.backend, "scene_live", None)
            cl = getattr(self.backend, "camera_live", None)
            is_cam = order.get("verb", "").startswith("camera.")
            is_f2 = sl is not None and sl.is_f2_order(order)
            if is_cam:
                from app.backend.camera_live import valid_cam_read
                if status == "done" and not valid_cam_read(read):
                    return _err(400, "bad_request")
            elif is_f2:
                # D1/A10: una orden F2 se valida con §3.2 y la juzga SceneLive.
                if status == "done" and not sl.valid_read(order, read):
                    return _err(400, "bad_request")
            elif status == "done" and order["verb"] in ("scene.apply", "state.read"):
                if not valid_world_read(read):
                    return _err(400, "bad_request")
            if order["result_seen"]:
                return 200, {"ok": True}
            if order["bstate"] in ("descartada", "terminal"):
                # entregada y ya cerrada por otra via (lectura del mundo o lectura descartada):
                # el resultado tardio se acusa y no cambia nada (§2.5.4)
                order["result_seen"] = True
                return 200, {"ok": True}
            if order["bstate"] not in ("ejecutando", "parcial"):
                return _err(409, "unknown_op")
            if not is_f2 and order["verb"] == "scene.apply":
                op = self.backend.ops.get(op_id)
                if op is None:
                    return _err(409, "unknown_op")
                if op["state"] in ("observado", "fallido", "aplicado"):
                    order["result_seen"] = True
                    order["bstate"] = "terminal"
                    return 200, {"ok": True}
            if is_cam:
                if cl is not None:
                    cl.on_result_locked(order, status, reason, read)
                order["result_seen"] = True
                order["bstate"] = "terminal"
                self.cond.notify_all()
                return 200, {"ok": True}
            if is_f2:
                # A10: SceneLive antes de marcar result_seen; el no lo marca.
                sl.on_result_locked(order, status, reason, read)
                order["result_seen"] = True
                self.cond.notify_all()
                return 200, {"ok": True}
            order["result_seen"] = True
            order["bstate"] = "terminal"
            if order["verb"] == "state.read":
                self._handle_read_result_locked(order, status, read)
                self.cond.notify_all()
                return 200, {"ok": True}
            if status == "done":
                self.backend.set_op_state(op_id, "aplicado", "servidor", None)
                if self._predicate_ok_locked(order, read):
                    self.backend.set_op_state(op_id, "observado", "servidor", None)
                else:
                    self.backend.set_op_state(op_id, "fallido", "servidor", "lectura_no_cumple")
            elif status == "rejected":
                self.backend.set_op_state(op_id, "fallido", "servidor", reason)
            else:
                self.backend.set_op_state(op_id, "parcial", "servidor", reason)
                order["bstate"] = "parcial"
                srv = self.peers.get("server")
                if srv and not srv.get("lost") and order["conn"] == srv.get("conn"):
                    self._trigger_state_read_locked()
            self.cond.notify_all()
            return 200, {"ok": True}

    def _predicate_ok_locked(self, order, read):
        if not valid_world_read(read):
            return False
        if read.get("epoch") != order["epoch"]:
            return False
        gen = read.get("generation")
        if not isinstance(gen, dict):
            return False
        args = order["args"] or {}
        return (gen.get("session") == self.session and gen.get("op_id") == order["op_id"]
                and gen.get("rev") == args.get("rev") and gen.get("hash") == args.get("hash"))

    def _handle_read_result_locked(self, order, status, read):
        srv = self.peers.get("server")
        sl_check = getattr(self.backend, "scene_live", None)
        reconciles = False
        if status == "done" and srv and not srv.get("lost") \
                and order["conn"] == int(srv["conn"]) and order["delivered_inst"] == srv["inst"] \
                and valid_world_read(read) and read.get("epoch") == srv["epoch"] \
                and (sl_check is None or sl_check.valid_state_read_locked(order, read)):
            # T-01 (contrato v1.3): un state.read con `f2` reconcilia solo con su `scene` valido.
            reconciles = True
        if reconciles:
            self.world = copy.deepcopy(read)
            self.reconciled = True
            self._read_next_at = None
            sl = getattr(self.backend, "scene_live", None)
            if sl is not None:
                # §4.6: la reconciliacion de F1b-bridge solo toca ordenes F1;
                # SceneLive juzga las F2 (§4.5).
                sl.on_world_read_locked(read)
            self._process_world_read_locked(read)
            if self._has_live_parcial_locked():
                # sigue el calendario 1, 2, 4, 8 s y despues cada 8 s (§4); no vuelve a 1 s
                self._schedule_read_retry_locked()
            else:
                self._read_backoff = 0
        else:
            if srv and not srv.get("lost"):
                if not self.reconciled or self._has_live_parcial_locked():
                    self._schedule_read_retry_locked()

    def _process_world_read_locked(self, read):
        gen = read.get("generation")
        if not isinstance(gen, dict):
            return
        if gen.get("session") != self.session:
            return
        target = self.orders.get((self.session, gen.get("op_id")))
        if target is None or target["verb"] != "scene.apply" or target["bstate"] != "parcial":
            return
        sl = getattr(self.backend, "scene_live", None)
        if sl is not None and sl.is_f2_order(target):
            return  # las F2 las juzga SceneLive.on_world_read_locked
        if target["epoch"] != read.get("epoch"):
            return
        op = self.backend.ops.get(target["op_id"])
        if op is None or op["state"] != "parcial":
            return
        if self._predicate_ok_locked(target, read):
            self.backend.set_op_state(target["op_id"], "observado", "servidor", "reconciliada")
        else:
            self.backend.set_op_state(target["op_id"], "fallido", "servidor", "lectura_no_cumple")
        target["bstate"] = "terminal"

    # --- catalog ------------------------------------------------------------
    def handle_catalog(self, query, body):
        if query.get("peer") != "server":
            return _err(400, "bad_request")
        q_inst, q_session = query.get("inst"), query.get("session")
        if not isinstance(q_inst, str) or not q_inst or not isinstance(q_session, str) or not q_session:
            return _err(400, "bad_request")
        if q_session != self.session:
            return _err(409, "hello_required")
        if not isinstance(body, dict):
            return _err(400, "bad_request")
        catalog_id = body.get("catalog_id")
        page, pages = body.get("page"), body.get("pages")
        build, modset_hash, classes = body.get("build"), body.get("modset_hash"), body.get("classes")
        if not _is_hex(catalog_id, 16) or not _is_int(page) or not _is_int(pages) \
                or page < 1 or pages < 1 or page > pages or not isinstance(build, str) or not build \
                or not _is_hex(modset_hash, 64) or not isinstance(classes, list):
            return _err(400, "bad_request")
        for item in classes:
            if not isinstance(item, (list, tuple)) or len(item) != 2 \
                    or not isinstance(item[0], str) or not isinstance(item[1], str):
                return _err(400, "bad_request")
        norm_classes = [[item[0], item[1]] for item in classes]
        with self.cond:
            srv = self.peers.get("server")
            if srv is None or srv.get("lost") or q_inst != srv["inst"]:
                return _err(409, "hello_required")
            attempt = self._catalog_attempts.get(catalog_id)
            if attempt is None:
                attempt = {"pages": pages, "build": build, "modset_hash": modset_hash, "pages_map": {}}
                self._catalog_attempts[catalog_id] = attempt
            elif attempt["pages"] != pages or attempt["build"] != build \
                    or attempt["modset_hash"] != modset_hash:
                del self._catalog_attempts[catalog_id]
                return _err(409, "bad_catalog")
            if page in attempt["pages_map"]:
                if attempt["pages_map"][page] != norm_classes:
                    del self._catalog_attempts[catalog_id]
                    return _err(409, "bad_catalog")
            else:
                attempt["pages_map"][page] = norm_classes
            have = len(attempt["pages_map"])
            if have < pages:
                return 200, {"ok": True, "have": have, "pages": pages}
            all_classes = []
            for p in range(1, pages + 1):
                all_classes.extend(attempt["pages_map"][p])
            names = [c[0] for c in all_classes]
            if len(names) != len(set(names)):
                del self._catalog_attempts[catalog_id]
                return _err(409, "bad_catalog")
            sorted_classes = sorted(all_classes, key=lambda c: (c[0], c[1]))
            canon = json.dumps(sorted_classes, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            sha = hashlib.sha256(canon).hexdigest()
            self.catalog = {"catalog_id": catalog_id, "build": build, "modset_hash": modset_hash,
                            "n_classes": len(sorted_classes), "sha256": sha, "classes": sorted_classes}
            sl = getattr(self.backend, "scene_live", None)
            if sl is not None:
                sl.on_catalog_complete_locked(q_inst, build)
            return 200, {"ok": True, "have": have, "pages": pages, "complete": True, "sha256": sha}


class _BridgeHandler(BaseHTTPRequestHandler):
    server_version = "DsbxBridge/1"
    sys_version = ""

    @property
    def bridge(self):
        return self.server.bridge

    def setup(self):
        super().setup()
        with self.bridge._conns_lock:
            tarde = self.bridge._closed
            if not tarde:
                self.bridge._conns.add(self.connection)
        if tarde:  # aceptada antes del cierre y registrada despues: se corta aqui
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def finish(self):
        with self.bridge._conns_lock:
            self.bridge._conns.discard(self.connection)
        super().finish()

    def log_message(self, fmt, *args):
        try:
            msg = fmt % args if args else str(fmt)
        except Exception:
            msg = str(fmt)
        msg = _KEY_IN_PATH.sub(r"\1***", msg)
        if self.bridge._peer_key:
            msg = msg.replace(self.bridge._peer_key, "***")
        self.bridge._log_line("%s %s" % (self.log_date_time_string(), msg))

    def _send(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > WIRE_CAP:
            self.bridge._register_event("wire_cap_exceeded", {"bytes": len(body)})
            status = 500
            body = json.dumps({"ok": False, "error": "wire_cap_exceeded"},
                              separators=(",", ":")).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            self.close_connection = True

    def _check_key(self, query):
        key = query.get("key")
        if key is None:
            return False
        try:
            return hmac.compare_digest(key.encode("utf-8"), self.bridge._peer_key.encode("utf-8"))
        except Exception:
            return False

    def _content_length(self):
        try:
            return int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return -1

    def _discard_body(self, length):
        """Descarta sin parsear el cuerpo anunciado de una peticion que se rechaza sin leerlo.

        Si se responde y se cierra con el cuerpo sin vaciar, Windows cierra con RST y el peer no
        llega a leer el 401, el 413 o el 404 (medido al integrar F1b-bridge: WinError 10053 en
        1 de 300 respuestas 401 y en 3 de 300 respuestas 413). Como `discard_body` de F1b-web
        (C-02), tiene un plazo total y un tope: un cuerpo que no llega no retiene el hilo.
        """
        self.close_connection = True
        if length <= 0 or length > MAX_DRAIN:
            return
        deadline = time.monotonic() + self.bridge.drain_s
        remaining = length
        try:
            while remaining > 0:
                left = deadline - time.monotonic()
                if left <= 0:
                    return
                self.connection.settimeout(left)
                chunk = self.rfile.read1(min(65536, remaining))
                if not chunk:
                    return
                remaining -= len(chunk)
        except (OSError, ValueError):  # plazo agotado o conexion rota
            return
        finally:
            try:
                self.connection.settimeout(None)
            except OSError:
                pass

    def _read_json_body(self):
        length = self._content_length()
        if length < 0:
            self.close_connection = True
            self._send(400, {"ok": False, "error": "bad_request"})
            return None
        if length > WIRE_CAP:
            self.close_connection = True
            self._send(413, {"ok": False, "error": "too_large"})
            return None
        if length == 0:
            return {}
        deadline = time.monotonic() + self.bridge.body_s
        chunks = []
        remaining = length
        try:
            while remaining > 0:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                self.connection.settimeout(left)
                chunk = self.rfile.read1(min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.connection.settimeout(None)
            except OSError:
                pass
        if remaining > 0:
            self.close_connection = True
            self._send(400, {"ok": False, "error": "bad_request"})
            return None
        raw = b"".join(chunks)
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._send(400, {"ok": False, "error": "bad_request"})
            return None
        if not isinstance(body, dict):
            self._send(400, {"ok": False, "error": "bad_request"})
            return None
        return body

    def _dispatch(self, method):
        url = urlsplit(self.path)
        qs = parse_qs(url.query)
        query = {k: v[0] for k, v in qs.items()}
        length = self._content_length()
        if not self._check_key(query):
            self._discard_body(length)
            self._send(401, {"ok": False, "error": "bad_key"})
            return
        if length > WIRE_CAP:
            self._discard_body(length)  # sin parsearlo: solo se vacia para que el 413 llegue
            self._send(413, {"ok": False, "error": "too_large"})
            return
        if length < 0:
            self.close_connection = True
            self._send(400, {"ok": False, "error": "bad_request"})
            return
        bridge = self.bridge
        if method == "POST" and url.path == "/hello":
            body = self._read_json_body()
            if body is None:
                return
            status, obj = bridge.handle_hello(body)
            self._send(status, obj)
        elif method == "GET" and url.path == "/poll":
            self._discard_body(length)  # un poll no lleva cuerpo; si lo trae, no se procesa
            status, obj = bridge.handle_poll(query)
            self._send(status, obj)
        elif method == "POST" and url.path == "/result":
            body = self._read_json_body()
            if body is None:
                return
            status, obj = bridge.handle_result(query, body)
            self._send(status, obj)
        elif method == "POST" and url.path == "/catalog":
            body = self._read_json_body()
            if body is None:
                return
            status, obj = bridge.handle_catalog(query, body)
            self._send(status, obj)
        else:
            self._discard_body(length)
            self._send(404, {"ok": False, "error": "bad_request"})

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")
