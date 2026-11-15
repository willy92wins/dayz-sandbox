"""Mod falso dsbx1 (F1b-bridge §6): los dos peers en Python, solo stdlib.

Cumple §2.4 entero: validacion de todo 200, una orden en curso con polls de
mantenimiento, plazo local anclado al envio del poll y retencion anclada a la
recepcion + margen, deduplicacion por (session, op_id) antes que cualquier
otra comprobacion, comprobaciones de orden nueva en orden, lease y plazo
antes de cada efecto, y resultados con reintentos.

CLI: python app/tests/fake_mod.py --config backend.json
"""
import argparse
import copy
import hashlib
import http.client
import json
import os
import queue
import re
import secrets
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import quote

try:
    from app.tests.fake_world import FakeWorld
except ImportError:  # CLI: python app/tests/fake_mod.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from app.tests.fake_world import FakeWorld

WIRE_CAP = 3500
REG_SHA = "0" * 64
MAX_STRING_CHARS = 1023  # A15/M20: el motor corta cada cadena de un JSON a 1023
_HEX = re.compile(r"[0-9a-fA-F]+")


def _truncate_strings(obj, limit=MAX_STRING_CHARS):
    """Copia profunda de `obj` con cada cadena cortada a `limit` (M20)."""
    if isinstance(obj, str):
        return obj[:limit]
    if isinstance(obj, list):
        return [_truncate_strings(x, limit) for x in obj]
    if isinstance(obj, dict):
        return {k: _truncate_strings(v, limit) for k, v in obj.items()}
    return obj


def _is_hex(value, n):
    return isinstance(value, str) and len(value) == n and _HEX.fullmatch(value) is not None


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def valid_hello_response(obj):
    # §2.4.1, mas `conn`: sin ella el peer se quedaria con session y sin conexion, y sus polls
    # darian 400 para siempre en vez del 409 que lo hace presentarse otra vez
    return (isinstance(obj, dict) and obj.get("ok") is True
            and _is_hex(obj.get("session"), 16)
            and _is_int(obj.get("conn")) and obj.get("conn") >= 1
            and _is_int(obj.get("lease_ms")) and obj.get("lease_ms") > 0
            and _is_int(obj.get("hold_ms")) and obj.get("hold_ms") > 0
            and _is_int(obj.get("wire_cap")) and obj.get("wire_cap") >= 1024)


def valid_order(order):
    return (isinstance(order, dict)
            and isinstance(order.get("op_id"), str) and bool(order.get("op_id"))
            and _is_hex(order.get("session"), 16)
            and _is_int(order.get("conn"))
            and _is_hex(order.get("epoch"), 32)
            and _is_hex(order.get("inst"), 32)
            and isinstance(order.get("verb"), str) and bool(order.get("verb"))
            and isinstance(order.get("args"), dict)
            and _is_int(order.get("issued_ms"))
            and _is_int(order.get("ttl_ms")) and order.get("ttl_ms") > 0)


def valid_poll_response(obj):
    if not (isinstance(obj, dict) and obj.get("ok") is True):
        return False
    now = obj.get("now_ms")
    if not _is_int(now):
        return False
    ops = obj.get("ops")
    if not isinstance(ops, list) or len(ops) > 1:
        return False
    return all(valid_order(o) for o in ops)


def valid_ack_response(obj):
    return isinstance(obj, dict) and obj.get("ok") is True


class _Entry:
    __slots__ = ("key", "order", "state", "result", "steps_done", "plazo_local",
                 "retention_until", "attempts", "next_attempt", "pending", "send_dup")

    def __init__(self, key, order, plazo_local, retention_until):
        self.key = key
        self.order = order
        self.state = "en_curso"
        self.result = None
        self.steps_done = 0
        self.plazo_local = plazo_local
        self.retention_until = retention_until
        self.attempts = 0
        self.next_attempt = 0.0
        self.pending = False
        self.send_dup = False


class _Peer:
    """Un peer (server o client). Hilo de poll + hilo trabajador."""

    def __init__(self, fake, role, epoch, inst=None):
        self.fake = fake
        self.role = role
        self.epoch = epoch
        self.inst = inst or secrets.token_hex(16)
        self.session = None
        self.conn = None
        self.lease_ms = 3000
        self.hold_ms = 2000
        self.wire_cap = WIRE_CAP
        self.last_valid_poll_mono = None
        self.cache = OrderedDict()
        self._lock = threading.Lock()
        self._work_q = queue.Queue()
        self._pending = []
        self._stop = threading.Event()
        self._executing = 0
        # inyeccion de fallos y configuracion de trabajo
        self.work_before_ms = int(fake._peer_kwargs.get("work_before_ms", 0))
        self.work_between_ms = int(fake._peer_kwargs.get("work_between_ms", 0))
        self.maintain_polls_during_work = True
        self.poll_response_delay_ms = 0
        self.ack_delay_ms = 0
        self.annotate_rev_delta = 0
        self.state_read_mode = "ok"
        self.drop_all_results = False
        self._drop_next_result = False
        self._lose_next_ack = False
        self._cut_until = 0.0
        self._overrides = {"hello": [], "poll": [], "ack": [], "catalog": []}
        # estadisticas observables por las pruebas (sin secretos)
        self.delivering_polls = 0
        self.maintenance_polls = 0
        self.hello_attempts = 0
        self.result_attempts = 0
        self.sent_results = []
        self.received_orders = []
        self.state_read_done = 0
        self._threads = []
        self._started = False

    # -- validacion (superficie tambien para BR10) ---------------------
    validate_hello = staticmethod(valid_hello_response)
    validate_poll = staticmethod(valid_poll_response)
    validate_ack = staticmethod(valid_ack_response)

    # -- arranque/parada -------------------------------------------------
    def start(self):
        if self._started:
            return
        self._started = True
        t1 = threading.Thread(target=self._poll_loop, daemon=True)
        t2 = threading.Thread(target=self._work_loop, daemon=True)
        t3 = threading.Thread(target=self._result_loop, daemon=True)
        self._threads = [t1, t2, t3]
        for t in self._threads:
            t.start()

    def stop(self):
        self._stop.set()
        try:
            self._work_q.put_nowait(None)
        except Exception:
            pass
        for t in self._threads:
            t.join(timeout=6)

    # -- utilidades --------------------------------------------------------
    def _sleep(self, seconds):
        self._stop.wait(timeout=max(0.0, seconds))

    def lease_age_ms(self):
        if self.last_valid_poll_mono is None:
            return None
        return (time.monotonic() - self.last_valid_poll_mono) * 1000.0

    def lease_ok(self):
        age = self.lease_age_ms()
        return age is not None and age <= self.lease_ms

    def cut_polls(self, ms):
        self._cut_until = time.monotonic() + ms / 1000.0

    def clear_poll_cut(self):
        self._cut_until = 0.0

    def lose_next_result(self):
        self._drop_next_result = True

    def lose_next_ack(self):
        self._lose_next_ack = True

    def simulate_next_response(self, route, obj):
        self._overrides[route].append(obj)

    def cache_keys(self):
        with self._lock:
            return list(self.cache.keys())

    # -- HTTP ---------------------------------------------------------------
    def _http(self, method, path, body=None, route=None):
        url = self.fake.bridge_url.rstrip("/")
        sep = "&" if "?" in path else "?"
        full = "%s%s%skey=%s" % (url, path, sep, quote(self.fake.peer_key, safe=""))
        parts = full.split("://", 1)[1]
        hostport, _, rest = parts.partition("/")
        host, _, port = hostport.partition(":")
        conn = http.client.HTTPConnection(host, int(port), timeout=15)
        data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if data is not None:
            headers["Content-Length"] = str(len(data))
        t_send = time.monotonic()
        try:
            conn.request(method, "/" + rest, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            status = resp.status
        finally:
            conn.close()
        t_recv = time.monotonic()
        try:
            obj = json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError:
            obj = {}
        if route is not None and self._overrides.get(route):
            obj = self._overrides[route].pop(0)
            status = 200
        return status, obj, t_send, t_recv

    def _qs(self, extra=""):
        return "peer=%s&inst=%s&session=%s" % (self.role, self.inst, self.session or "")

    # -- hello / catalogo ---------------------------------------------------
    def _do_hello(self):
        self.hello_attempts += 1
        body = {"proto": "dsbx1", "peer": self.role, "inst": self.inst,
                "epoch": self.epoch, "mod_ver": self.fake.mod_ver, "build": "retail"}
        if self.role == "server":
            world_size = 15360
            scene = None
            if self.fake.world is not None:
                world_size = self.fake.world.world_size
                scene = 1
            body.update({"map": "chernarus", "world_size": world_size,
                         "modset": ["DayZSandbox"], "actor_engine": "none"})
            if scene is not None:
                body["scene"] = scene
        try:
            status, obj, _ts, _tr = self._http("POST", "/hello", body, route="hello")
        except (OSError, ValueError):
            return False
        if status != 200 or not valid_hello_response(obj):
            return False
        self.session = obj["session"]
        self.conn = obj["conn"]
        self.lease_ms = obj["lease_ms"]
        self.hold_ms = obj["hold_ms"]
        self.wire_cap = obj["wire_cap"]
        self.last_valid_poll_mono = time.monotonic()
        if self.role == "server":
            self._upload_catalog()
        return True

    def _upload_catalog(self):
        classes = self.fake.catalog_classes
        size = max(1, self.fake.catalog_page_size)
        pages = max(1, (len(classes) + size - 1) // size)
        catalog_id = secrets.token_hex(8)
        modset_hash = hashlib.sha256(b"fake-modset").hexdigest()
        for i in range(pages):
            chunk = classes[i * size:(i + 1) * size]
            body = {"catalog_id": catalog_id, "page": i + 1, "pages": pages,
                    "build": "fake-1", "modset_hash": modset_hash, "classes": chunk}
            try:
                status, obj, _a, _b = self._http(
                    "POST", "/catalog?" + self._qs(), body, route="catalog")
            except (OSError, ValueError):
                return
            if status != 200 or not valid_ack_response(obj):
                return

    # -- cache ---------------------------------------------------------------
    def _evict_one_expired_locked(self, now):
        # FIFO: la caducada mas antigua en orden de llegada; nunca una viva.
        for key in list(self.cache.keys()):
            if self.cache[key].retention_until <= now:
                del self.cache[key]
                return True
        return False

    def _make_room_locked(self, now):
        while len(self.cache) >= self.fake.cache_capacity:
            if not self._evict_one_expired_locked(now):
                break

    def _cache_full_live_locked(self, now):
        return (len(self.cache) >= self.fake.cache_capacity
                and all(e.retention_until > now for e in self.cache.values()))

    def remember_completed(self, order, result, retention_until):
        """Guarda un resultado en la cache (misma via que handle_order)."""
        key = (order["session"], order["op_id"])
        now = time.monotonic()
        with self._lock:
            if key not in self.cache:
                self._make_room_locked(now)
            entry = _Entry(key, copy.deepcopy(order), now, retention_until)
            entry.state = "terminada"
            entry.result = copy.deepcopy(result)
            self.cache[key] = entry
            return entry

    # -- recepcion de ordenes --------------------------------------------------
    def handle_order(self, order, t_send=None, t_recv=None, now_ms=None):
        now = time.monotonic()
        if t_send is None:
            t_send = now
        if t_recv is None:
            t_recv = now
        if now_ms is None:
            now_ms = order.get("issued_ms", 0)
        remaining_ms = order["ttl_ms"] - (now_ms - order["issued_ms"])
        plazo_local = t_send + remaining_ms / 1000.0 - self.fake.deadline_margin_ms / 1000.0
        retention_until = t_recv + remaining_ms / 1000.0 + self.fake.retention_extra_ms / 1000.0
        key = (order.get("session"), order.get("op_id"))
        with self._lock:
            self.received_orders.append(copy.deepcopy(order))
            # 1) deduplicacion, antes que cualquier otra comprobacion (§2.4.4);
            # una entrada cuya retencion ya vencio ya no esta en la cache.
            existing = self.cache.get(key)
            if existing is not None and existing.retention_until <= now:
                del self.cache[key]
                existing = None
            if existing is not None:
                if existing.state == "en_curso":
                    return "en_curso"
                if existing.state == "terminada":
                    existing.send_dup = True
                    existing.attempts = 0
                    existing.next_attempt = 0.0
                    if not existing.pending:
                        existing.pending = True
                        self._pending.append(existing)
                    return "dup"
            # contrapresion: cache llena de entradas vivas
            self._make_room_locked(now)
            if len(self.cache) >= self.fake.cache_capacity:
                return "cache_llena"
            entry = _Entry(key, copy.deepcopy(order), plazo_local, retention_until)
            self.cache[key] = entry
            # 2) comprobaciones de orden nueva, en este orden (§2.4.5)
            reason = None
            if order.get("session") != self.session:
                reason = "stale_session"
            elif order.get("inst") != self.inst:
                reason = "stale_inst"
            elif order.get("conn") != self.conn:
                reason = "stale_conn"
            elif order.get("epoch") != self.epoch:
                reason = "stale_epoch"
            elif now > plazo_local:
                reason = "expired"
            if reason is not None:
                entry.state = "terminada"
                entry.result = {"status": "rejected", "reason": reason, "read": {}}
                entry.pending = True
                self._pending.append(entry)
                return "rejected"
            self._executing += 1
        self._work_q.put(entry)
        return "aceptada"

    def force_double_delivery(self, order, t_send=None, t_recv=None, now_ms=None):
        first = self.handle_order(order, t_send, t_recv, now_ms)
        second = self.handle_order(order, t_send, t_recv, now_ms)
        return first, second

    def resend_cached_result(self, op_id, session=None):
        with self._lock:
            for entry in self.cache.values():
                if entry.order["op_id"] == op_id and (session is None or entry.key[0] == session):
                    if entry.state != "terminada":
                        return False
                    entry.send_dup = True
                    entry.attempts = 0
                    entry.next_attempt = 0.0
                    if not entry.pending:
                        entry.pending = True
                        self._pending.append(entry)
                    return True
        return False

    # -- ejecucion ---------------------------------------------------------------
    def _check_before_effect(self, entry):
        age = self.lease_age_ms()
        if age is None or age > self.lease_ms:
            return "lease_expired"
        if time.monotonic() > entry.plazo_local:
            return "expired"
        return None

    def _work_loop(self):
        while not self._stop.is_set():
            try:
                entry = self._work_q.get(timeout=0.1)
            except queue.Empty:
                continue
            if entry is None:
                break
            try:
                self._execute(entry)
            except Exception:
                self._finish(entry, "error", "internal", {})
            finally:
                with self._lock:
                    self._executing = max(0, self._executing - 1)

    def _finish(self, entry, status, reason, read):
        with self._lock:
            if self._stop.is_set():
                return
            entry.state = "terminada"
            entry.result = {"status": status, "reason": reason, "read": read}
            entry.attempts = 0
            entry.next_attempt = 0.0
            entry.send_dup = False
            if not entry.pending:
                entry.pending = True
                self._pending.append(entry)

    def _execute(self, entry):
        order = entry.order
        verb = order["verb"]
        if self.fake.world is not None and verb in (
                "state.read", "scene.apply", "scene.reset", "scene.observe"):
            self._execute_world(entry, verb)
            return
        if verb == "state.read":
            if self.state_read_mode == "error":
                self._finish(entry, "error", "state_read_error", {})
                return
            if self.state_read_mode == "stale_epoch":
                read = self.fake.world_read()
                read = dict(read, epoch="e" * 32)
                self._finish(entry, "done", None, read)
                return
            if self.state_read_mode == "incompleto":
                self._finish(entry, "done", None, {"epoch": order["epoch"]})
                return
            self._finish(entry, "done", None, self.fake.world_read())
            return
        if verb != "scene.apply":
            self._finish(entry, "rejected", "unknown_verb", {})
            return
        # scene.apply: dos pasos con efecto (§3.2)
        if self.work_before_ms:
            self._sleep(self.work_before_ms / 1000.0)
            if self._stop.is_set():
                return
        fail = self._check_before_effect(entry)
        if fail is not None:
            self._finish(entry, "rejected", fail, {})
            return
        entry.steps_done = 1
        self.fake._record_effect(order, "retirar")
        self.fake._set_generation(None)
        if self.work_between_ms:
            self._sleep(self.work_between_ms / 1000.0)
            if self._stop.is_set():
                return
        fail = self._check_before_effect(entry)
        if fail is not None:
            self._finish(entry, "error", fail, {})
            return
        entry.steps_done = 2
        gen = {"session": order["session"], "op_id": order["op_id"],
               "rev": order["args"].get("rev", 0) + self.annotate_rev_delta,
               "hash": order["args"].get("hash")}
        self.fake._record_effect(order, "anotar")
        self.fake._set_generation(gen)
        self._finish(entry, "done", None, self.fake.world_read())

    def _tick(self):
        """Tick del peer durante un verbo del mundo: poll de mantenimiento (M8).

        Si los polls estan cortados, no se manda nada y el lease del peer caduca.
        """
        if time.monotonic() < self._cut_until:
            self._sleep(0.005)
            return
        self._poll_once(deliver=False)

    def _execute_world(self, entry, verb):
        order = entry.order
        args = _truncate_strings(order.get("args"))
        order2 = dict(order)
        order2["args"] = args
        check = lambda: self._check_before_effect(entry)
        tick = lambda: self._tick()
        if verb == "state.read":
            doc_id = args.get("doc_id") if isinstance(args, dict) else None
            if isinstance(doc_id, str) and doc_id:
                read = self.fake.world.read(doc_id)
            else:
                read = self.fake.world_read()
            self._finish(entry, "done", None, read)
            return
        if verb == "scene.apply":
            status, reason, read = self.fake.world.apply(order2, check=check, tick=tick)
        elif verb == "scene.reset":
            status, reason, read = self.fake.world.reset(order2, check=check, tick=tick)
        else:
            status, reason, read = self.fake.world.observe(order2)
        self._finish(entry, status, reason, read)

    # -- resultados ----------------------------------------------------------------
    def _attempt_result(self, entry):
        """Un intento. Devuelve 'ok', 'unknown' o 'fail'."""
        self.result_attempts += 1
        result = entry.result or {"status": "error", "reason": "internal", "read": {}}
        body = {"op_id": entry.order["op_id"], "session": entry.order["session"],
                "epoch": entry.order["epoch"], "status": result["status"],
                "reason": result.get("reason"), "dup": bool(entry.send_dup),
                "read": result.get("read") or {}}
        raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
        if len(raw) > WIRE_CAP:
            body = {"op_id": entry.order["op_id"], "session": entry.order["session"],
                    "epoch": entry.order["epoch"], "status": "error",
                    "reason": "result_too_large", "dup": bool(entry.send_dup), "read": {}}
        if self.drop_all_results:
            return "fail"
        if self._drop_next_result:
            self._drop_next_result = False
            return "fail"
        lose_ack = self._lose_next_ack
        if lose_ack:
            self._lose_next_ack = False
        try:
            status, obj, _a, _b = self._http(
                "POST", "/result?" + self._qs(), body, route="ack")
        except (OSError, ValueError):
            return "fail"
        if self.ack_delay_ms:
            delay = self.ack_delay_ms
            self.ack_delay_ms = 0
            self._sleep(delay / 1000.0)
        self.sent_results.append(copy.deepcopy(body))
        if entry.order["verb"] == "state.read" and body["status"] == "done":
            self.state_read_done += 1
        if lose_ack:
            return "fail"
        if status == 409 and isinstance(obj, dict) and obj.get("error") == "unknown_op":
            return "unknown"
        if status == 200 and valid_ack_response(obj):
            return "ok"
        return "fail"

    def _service_pending(self):
        now = time.monotonic()
        with self._lock:
            due = None
            for e in self._pending:
                if now >= e.next_attempt:
                    due = e
                    break
        if due is None:
            return False
        outcome = self._attempt_result(due)
        with self._lock:
            if outcome in ("ok", "unknown"):
                due.pending = False
                if due in self._pending:
                    self._pending.remove(due)
            else:
                due.attempts += 1
                delays = self.fake.result_retry_ms
                if due.attempts >= 4:
                    due.pending = False
                    if due in self._pending:
                        self._pending.remove(due)
                else:
                    idx = min(due.attempts - 1, len(delays) - 1)
                    due.next_attempt = time.monotonic() + delays[idx] / 1000.0
        return True

    def _result_loop(self):
        while not self._stop.is_set():
            try:
                if self.session is None:
                    self._sleep(0.02)
                    continue
                if not self._service_pending():
                    now = time.monotonic()
                    with self._lock:
                        if self._pending:
                            wait_s = min(0.02, max(0.0, min(e.next_attempt for e in self._pending) - now))
                        else:
                            wait_s = 0.02
                    self._sleep(wait_s)
            except Exception:
                self._sleep(0.02)

    # -- poll ------------------------------------------------------------------------
    def _poll_once(self, deliver):
        q = self._qs() + "&conn=%s" % self.conn
        if not deliver:
            q += "&deliver=0"
        try:
            status, obj, t_send, t_recv = self._http("GET", "/poll?" + q, route="poll")
        except (OSError, ValueError):
            return
        if self.poll_response_delay_ms:
            self._sleep(self.poll_response_delay_ms / 1000.0)
            t_recv = time.monotonic()
        if status == 409:
            self.session = None
            self.conn = None
            return
        if status != 200 or not valid_poll_response(obj):
            return
        self.last_valid_poll_mono = time.monotonic()
        if deliver:
            self.delivering_polls += 1
        else:
            self.maintenance_polls += 1
        if deliver and obj["ops"]:
            order = obj["ops"][0]
            self.handle_order(order, t_send=t_send, t_recv=t_recv, now_ms=obj["now_ms"])

    def _poll_loop(self):
        while not self._stop.is_set():
            try:
                self._loop_step()
            except Exception:
                self._sleep(0.02)

    def _loop_step(self):
        now = time.monotonic()
        if now < self._cut_until:
            self._sleep(0.01)
            return
        if self.session is None:
            if not self._do_hello():
                self._sleep(0.05)
            return
        with self._lock:
            cache_full = self._cache_full_live_locked(now)
            busy = self._executing > 0 or bool(self._pending)
        if busy and not self.maintain_polls_during_work and self._executing > 0:
            self._sleep(0.01)
            return
        if busy or cache_full:
            self._poll_once(deliver=False)
            self._sleep(self.fake.maintenance_ms / 1000.0)
            return
        self._poll_once(deliver=True)


class FakeMod:
    """Los dos peers contra el bridge en `bridge_url` (§6)."""

    # validacion expuesta para las pruebas H5/BR10
    validate_hello = staticmethod(valid_hello_response)
    validate_poll = staticmethod(valid_poll_response)
    validate_ack = staticmethod(valid_ack_response)

    def __init__(self, bridge_url, peer_key, *, cache_capacity=1024,
                 maintenance_ms=500, result_retry_ms=(250, 500, 1000),
                 deadline_margin_ms=100, retention_extra_ms=1000,
                 work_before_ms=0, work_between_ms=0,
                 catalog_classes=None, catalog_page_size=1,
                 mod_ver="fake-1", epoch=None, world=None):
        self.bridge_url = bridge_url
        self.peer_key = peer_key
        self.cache_capacity = int(cache_capacity)
        self.maintenance_ms = int(maintenance_ms)
        if isinstance(result_retry_ms, (int, float)):
            result_retry_ms = (int(result_retry_ms),)
        self.result_retry_ms = tuple(int(x) for x in result_retry_ms) or (250,)
        self.deadline_margin_ms = int(deadline_margin_ms)
        self.retention_extra_ms = int(retention_extra_ms)
        self.mod_ver = mod_ver
        self.world = world
        if catalog_classes is None and world is not None:
            catalog_classes = world.catalog_classes()
        self.catalog_classes = catalog_classes or [["FakeClaseA", "BaseA"],
                                                   ["FakeClaseB", "BaseB"]]
        self.catalog_page_size = int(catalog_page_size)
        self._peer_kwargs = {"work_before_ms": work_before_ms,
                             "work_between_ms": work_between_ms}
        # Con mundo, el epoch de los peers es el del mundo: las ordenes llevan ese
        # epoch y el mundo las acepta.
        self.epoch = world.epoch if world is not None else (epoch or secrets.token_hex(16))
        self._world_lock = threading.Lock()
        self._generation = None
        self._effects = {}
        self._mission_effects = {"retirar": 0, "anotar": 0}
        self.peers = {"server": _Peer(self, "server", self.epoch),
                      "client": _Peer(self, "client", self.epoch)}
        for p in self.peers.values():
            p.start()

    # alias comodos
    @property
    def server(self):
        return self.peers["server"]

    @property
    def client(self):
        return self.peers["client"]

    server_peer = server
    client_peer = client

    # -- mundo y efectos -------------------------------------------------------
    def _set_generation(self, gen):
        with self._world_lock:
            self._generation = copy.deepcopy(gen)

    @property
    def generation(self):
        with self._world_lock:
            return copy.deepcopy(self._generation)

    def world_read(self):
        with self._world_lock:
            gen = copy.deepcopy(self._generation)
        return {"epoch": self.epoch, "generation": gen,
                "registry_n": 0, "registry_sha256": REG_SHA}

    def _record_effect(self, order, step):
        key = (order["session"], order["op_id"])
        with self._world_lock:
            counts = self._effects.setdefault(key, {"retirar": 0, "anotar": 0})
            counts[step] += 1
            self._mission_effects[step] += 1

    def effect_count(self, op_id, step=None, session=None):
        with self._world_lock:
            if session is not None:
                counts = self._effects.get((session, op_id), {"retirar": 0, "anotar": 0})
                return counts[step] if step else sum(counts.values())
            total = 0
            for (sess, oid), counts in self._effects.items():
                if oid == op_id:
                    total += counts[step] if step else sum(counts.values())
            return total

    def effects_for(self, op_id, session=None):
        with self._world_lock:
            if session is not None:
                return dict(self._effects.get((session, op_id), {"retirar": 0, "anotar": 0}))
            out = {"retirar": 0, "anotar": 0}
            for (sess, oid), counts in self._effects.items():
                if oid == op_id:
                    out["retirar"] += counts["retirar"]
                    out["anotar"] += counts["anotar"]
            return out

    @property
    def mission_effects(self):
        with self._world_lock:
            return dict(self._mission_effects)

    # -- inyeccion (delegacion) ---------------------------------------------------
    def lose_next_result(self, role="server"):
        self.peers[role].lose_next_result()

    def lose_next_ack(self, role="server"):
        self.peers[role].lose_next_ack()

    def cut_polls(self, role, ms):
        self.peers[role].cut_polls(ms)

    def set_state_read_mode(self, mode):
        self.peers["server"].state_read_mode = mode

    def force_double_delivery(self, order, role="server", **kw):
        return self.peers[role].force_double_delivery(order, **kw)

    def resend_cached_result(self, op_id, role="server", session=None):
        return self.peers[role].resend_cached_result(op_id, session=session)

    def simulate_next_response(self, role, route, obj):
        self.peers[role].simulate_next_response(route, obj)

    def _make_peer(self, role, epoch):
        peer = _Peer(self, role, epoch)
        old = self.peers.get(role)
        if old is not None:
            # conserva la configuracion de trabajo e inyeccion basica
            peer.work_before_ms = old.work_before_ms
            peer.work_between_ms = old.work_between_ms
            peer.maintain_polls_during_work = old.maintain_polls_during_work
            peer.poll_response_delay_ms = old.poll_response_delay_ms
            peer.annotate_rev_delta = old.annotate_rev_delta
            peer.state_read_mode = old.state_read_mode
        return peer

    def restart_peer(self, role, epoch=None):
        old = self.peers[role]
        old.stop()
        if role == "server":
            new_epoch = epoch if epoch is not None else self.epoch
            if epoch is not None:
                # el servidor declara ese epoch; el mundo (generacion) se conserva
                pass
        else:
            new_epoch = epoch if epoch is not None else self.epoch
        peer = self._make_peer(role, new_epoch)
        self.peers[role] = peer
        peer.start()
        return peer

    def restart_mission(self):
        for p in list(self.peers.values()):
            p.stop()
        if self.world is not None:
            self.epoch = self.world.restart()
        else:
            self.epoch = secrets.token_hex(16)
        with self._world_lock:
            self._generation = None
            self._mission_effects = {"retirar": 0, "anotar": 0}
        for role in ("server", "client"):
            peer = self._make_peer(role, self.epoch)
            self.peers[role] = peer
        for p in self.peers.values():
            p.start()

    def reconnect(self, bridge_url=None):
        if bridge_url is not None:
            self.bridge_url = bridge_url
        for p in self.peers.values():
            p.session = None
            p.conn = None

    def wait_ready(self, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            srv, cli = self.peers["server"], self.peers["client"]
            if srv.session and cli.session and srv.state_read_done > 0:
                return True
            time.sleep(0.02)
        return False

    def close(self):
        for p in list(self.peers.values()):
            p.stop()

    stop = close

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mod falso dsbx1")
    ap.add_argument("--config", required=True)
    ap.add_argument("--world", action="store_true",
                    help="peer servidor con mundo falso (escena sin actores de F2)")
    args = ap.parse_args(argv)
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    peer_key = cfg.get("peer_key")
    bridge_port = cfg.get("bridge_port", 8766)
    if not peer_key:
        print("Falta peer_key en la configuracion", file=sys.stderr)
        return 2
    world = None
    if args.world:
        fixture = Path(__file__).resolve().parents[2] / "fixtures" / "escena-sin-actores.json"
        with fixture.open("r", encoding="utf-8") as f:
            json.load(f)  # la escena la aplica el backend; aqui solo se comprueba
        world = FakeWorld()
    fake = FakeMod("http://127.0.0.1:%d" % int(bridge_port), peer_key, world=world)
    print("Mod falso dsbx1 conectado al bridge local", flush=True)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        fake.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
