"""Backend local de Sandbox (F1a): API HTTP y SSE sobre el almacén.

Uso, desde DayZSandbox_dev/:  python app/backend/server.py --config backend.json [--port N]
Solo biblioteca estándar. Brief: plans/2026-11-11-m1-f1a-brief.md §5.
"""
import argparse
import hmac
import json
import os
import queue
import re
import secrets
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.backend.store import Store  # noqa: E402
from app.backend.lease import Leases  # noqa: E402
from app.backend.profile import Profile  # noqa: E402
from app.backend.bridge import Bridge  # noqa: E402
from app.backend.scene_live import SceneLive  # noqa: E402

MAX_BODY = 1024 * 1024
CLIENT_QUEUE = 1000
PING_S = 15
TAKE_LOCKED = ("armada", "rodando")
WAIT_MAX = 30
DRAIN_S = 2.0  # tope total para descartar el cuerpo de un POST rechazado (C-02)
HUMAN = {"role": "human", "id": "web"}
AI = {"role": "ai", "id": "mcp"}

STATUS = {
    "conflict": 409, "stale_base": 409, "stale_apply": 409, "doc_changed": 409,
    "request_conflict": 409, "take_locked": 409, "ai_paused": 409,
    "already_reverted": 409, "nothing_to_undo": 409, "nothing_to_redo": 409,
    "entity_gone": 409, "busy_human": 409, "lease_expired": 409,
    "bad_op": 422, "invalid": 422, "bad_base": 422,
    "unauthorized": 401, "forbidden": 403, "author_mismatch": 403, "csrf_failed": 403,
    "bad_request": 400, "not_found": 404, "internal": 500,
    "queue_full": 409, "wire_cap_exceeded": 500,
    "expansion_unavailable": 422, "catalog_pending": 409,
    "unknown_class": 422, "out_of_map": 422, "budget_exceeded": 422,
    "plan_too_large": 422, "scene_unsupported": 409,
}


def now_ms():
    return int(time.time() * 1000)


def fail(code, msg, pointer=""):
    return {"ok": False, "code": code, "pointer": pointer, "msg": msg}


class Backend:
    """Une el almacén con HTTP: credenciales, gate (pausa y toma), cola de órdenes y SSE."""

    def __init__(self, store, human_key, ai_key, port=0, horizon=1000, log=None, clock=time.monotonic,
                 web_root=None, bridge_port=None, peer_key=None, bridge_kwargs=None,
                 profile_path=None, schema_path=None):
        if not human_key or not ai_key or human_key == ai_key:
            raise ValueError("human_key y ai_key deben ser distintas y no vacías")
        if peer_key is not None and (not peer_key or peer_key == human_key or peer_key == ai_key):
            raise ValueError("human_key, ai_key y peer_key deben ser distintas y no vacías")
        if bridge_port is not None and not peer_key:
            raise ValueError("human_key, ai_key y peer_key deben ser distintas y no vacías")
        self.profile = Profile(store, profile_path=profile_path, schema_path=schema_path)
        self.store = store
        self.clock = clock
        self.web_root = web_root
        self.sessions = {}
        self._sessions_lock = threading.Lock()
        self.op_mono = {}
        self.drain_s = DRAIN_S
        self._keys = ((human_key, HUMAN), (ai_key, AI))
        self.horizon = horizon
        self.log = log if log is not None else sys.stderr
        self.paused = False
        self.take_state = "libre"
        self.seq = 0
        self.ring = deque(maxlen=horizon)  # (seq, tipo, data_json)
        self.clients = set()
        self.ops = {}  # op_id -> {op_id, state, rev, hash, at_ms}
        self._op_n = 0
        store.gate = self._gate
        store.on_commit = self._on_commit
        self.leases = Leases(clock=clock)
        self.changed = threading.Condition(store.lock)  # despierta a /api/scene/changes
        store.busy = self._busy
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.httpd.block_on_close = False
        self.httpd.backend = self
        self.bridge = None
        self.scene_live = None
        self.observation = None
        if bridge_port is not None:
            self.bridge = Bridge(self, peer_key, port=bridge_port, clock=self.clock,
                                 log=self.log, **(bridge_kwargs or {}))
            self.scene_live = SceneLive(self.bridge)

    @property
    def port(self):
        return self.httpd.server_address[1]

    def serve_forever(self):
        self.httpd.serve_forever(poll_interval=0.1)

    def shutdown(self):
        if self.bridge is not None:
            self.bridge.shutdown()
        self.httpd.shutdown()
        with self.store.lock:
            for q in list(self.clients):
                self._close_client(q)
        self.httpd.server_close()

    # --- dentro del candado del almacén -------------------------------
    def _gate(self, author):
        if self.take_state in TAKE_LOCKED:
            return "take_locked"
        if author["role"] == "ai" and self.paused:
            return "ai_paused"
        return None

    def _on_commit(self, record):
        self._emit("scene.commit", record)
        self.changed.notify_all()

    def _busy(self, author, fp):
        self.expire_leases()
        if author["role"] == "ai" and self.leases.busy(fp):
            return "busy_human"
        return None

    def expire_leases(self):
        with self.store.lock:
            for l in self.leases.expire():
                self._emit("lease.state", {"lease_id": l["lease_id"], "target": l["target"],
                                           "field": l["field"], "state": "caducada"})

    def lease_take(self, target, field):
        with self.store.lock:
            doc = self.store.snapshot()["doc"]
            ids = {e["id"] for e in doc["entities"]} | {c["id"] for c in doc["cameras"]} | {"ambiente"}
            if target not in ids:
                return fail("entity_gone", "No existe " + target, "/target")
            self.expire_leases()
            l = self.leases.take(target, field)
            self._emit("lease.state", {"lease_id": l["lease_id"], "target": target, "field": field, "state": "viva"})
            return {"ok": True, "lease_id": l["lease_id"], "expires_in": self.leases.ttl}

    def lease_renew(self, lease_id):
        with self.store.lock:
            self.expire_leases()
            if self.leases.renew(lease_id) is None:
                return fail("lease_expired", "El préstamo caducó o no existe")
            return {"ok": True, "expires_in": self.leases.ttl}

    def lease_release(self, lease_id):
        with self.store.lock:
            self.expire_leases()
            l = self.leases.release(lease_id)
            if l is not None:
                self._emit("lease.state", {"lease_id": lease_id, "target": l["target"],
                                           "field": l["field"], "state": "soltada"})
            return {"ok": True}

    def changes(self, since_rev, timeout_s):
        with self.store.lock:
            rev = self.store.snapshot()["rev"]
            if since_rev > rev:
                return fail("bad_base", "since_rev futura", "/since_rev")
            recs = self.store.records_since(since_rev)
            if recs is None:
                r = fail("stale_base", "since_rev fuera del horizonte", "/since_rev")
                r["current"] = self.store.snapshot()
                return r
            if not recs and timeout_s > 0:
                self.changed.wait_for(lambda: self.store.records_since(since_rev) != [], timeout_s)
                recs = self.store.records_since(since_rev) or []
            snap = self.store.snapshot()
            return {"ok": True, "rev": snap["rev"], "hash": snap["hash"], "batches": recs}

    def apply_request(self, author, doc_id, rev, hash_):
        with self.store.lock:
            frozen = self.store.freeze(doc_id, rev, hash_)
            if not frozen.get("ok"):
                return frozen
            self._emit("apply.request", {"rev": rev, "hash": hash_, "author": author, "at_ms": now_ms()})
            return {"ok": True}

    def _emit(self, kind, data):
        self.seq += 1
        ev = (self.seq, kind, json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        self.ring.append(ev)
        for q in list(self.clients):
            try:
                q.put_nowait(ev)
            except queue.Full:
                self._close_client(q)

    def _close_client(self, q):
        self.clients.discard(q)
        while True:  # deja sitio para el aviso de cierre
            try:
                q.get_nowait()
            except queue.Empty:
                break
        q.put_nowait(None)

    def subscribe(self, last_event_id):
        """Devuelve la cola del cliente, ya con la repetición o la instantánea."""
        q = queue.Queue(maxsize=CLIENT_QUEUE)
        with self.store.lock:
            first = self.ring[0][0] if self.ring else self.seq + 1
            if last_event_id is not None and first - 1 <= last_event_id <= self.seq \
                    and self.seq - last_event_id <= CLIENT_QUEUE:
                for ev in self.ring:
                    if ev[0] > last_event_id:
                        q.put_nowait(ev)
            else:
                snap = self.store.snapshot()
                now = self.clock()
                ops = []
                for op in self.ops.values():
                    item = dict(op)
                    item["age_ms"] = int((now - self.op_mono.get(op["op_id"], now)) * 1000)
                    ops.append(item)
                data = {"rev": snap["rev"], "hash": snap["hash"], "doc_id": snap["doc_id"],
                        "doc": snap["doc"], "ops": ops}
                q.put_nowait((self.seq, "snapshot", json.dumps(data, ensure_ascii=False, separators=(",", ":"))))
            self.clients.add(q)
        return q

    def unsubscribe(self, q):
        with self.store.lock:
            self.clients.discard(q)

    def set_paused(self, paused):
        with self.store.lock:
            self.paused = paused
            self._emit("ai.state", {"paused": paused})
        return {"ok": True, "paused": paused}

    def set_op_state(self, op_id, state, origin, reason=None):
        with self.store.lock:
            op = self.ops[op_id]
            op["state"] = state
            op["origin"] = origin
            op["reason"] = reason
            op["at_ms"] = now_ms()
            self.op_mono[op_id] = self.clock()
            self._emit("op.state", dict(op))
            return dict(op)

    def apply(self, doc_id, rev, hash_):
        with self.store.lock:
            frozen = self.store.freeze(doc_id, rev, hash_)
            if not frozen.get("ok"):
                return frozen
            if self.bridge is not None and self.scene_live is not None \
                    and self.scene_live.server_has_scene_locked():
                # D1/A10: con un peer con escena, apply es una orden F2. SceneLive
                # valida (§4.1), crea la fila de la API y la encola; Backend no
                # crea otra fila.
                res = self.scene_live.prepare_apply_locked(
                    frozen["doc"], frozen["rev"], frozen["hash"])
                if not res.get("ok"):
                    return res
                if self.scene_live._scene_queue_len_locked() >= self.bridge.queue_max:
                    return fail("queue_full", "Cola del bridge llena")
                ok, order = self.scene_live.enqueue_apply_locked(
                    None, res["plan"], res["expectation"])
                if not ok:
                    return order
                return {"ok": True, "op_id": order["op_id"]}
            if self.bridge is not None and self.bridge.live_scene_count() >= self.bridge.queue_max:
                return fail("queue_full", "Cola del bridge llena")
            self._op_n += 1
            op = {"op_id": "op-%d" % self._op_n, "state": "pendiente",
                  "rev": frozen["rev"], "hash": frozen["hash"], "at_ms": now_ms(),
                  "origin": "backend", "reason": None}
            if self.bridge is not None:
                ok, info = self.bridge.enqueue_scene_apply(op["op_id"], doc_id,
                                                           frozen["rev"], frozen["hash"])
                if not ok:
                    self._op_n -= 1
                    return fail(info, "La orden no cabe en el cable")
            self.ops[op["op_id"]] = op
            self.op_mono[op["op_id"]] = self.clock()
            self._emit("op.state", dict(op))
            return {"ok": True, "op_id": op["op_id"]}

    def reset(self, doc_id):
        """POST /api/reset (§4.2/A11): delega en SceneLive; sin bridge, 409."""
        with self.store.lock:
            if self.bridge is None or self.scene_live is None:
                return fail("scene_unsupported", "El servidor no soporta escena F2")
            ok, info = self.scene_live.enqueue_reset_locked(None, doc_id)
            if not ok:
                return info
            return {"ok": True, "op_id": info["op_id"]}

    def request_observe(self, doc_id):
        """POST /api/observe (§4.2): lectura `now` interna a traves de SceneLive."""
        with self.store.lock:
            if self.bridge is None or self.scene_live is None:
                return fail("scene_unsupported", "El servidor no soporta escena F2")
            return self.scene_live.request_observe_locked(doc_id)

    def get_observation(self):
        """GET /api/observation (§4.2): ultima lectura `now` y su antiguedad.

        SceneLive guarda el objeto en el campo `Backend.observation` (§4.2); el
        metodo no puede llamarse igual que el campo o lo sombrearia en la instancia.
        """
        with self.store.lock:
            if self.scene_live is None:
                return {"ok": True, "observation": None, "age_ms": None}
            return self.scene_live.observation_locked()

    def author_for(self, header):
        token = header[7:] if header and header.startswith("Bearer ") else None
        found = None
        for key, author in self._keys:
            if token is not None and hmac.compare_digest(token.encode(), key.encode()):
                found = author
        return found

    def create_session(self):
        sid = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self._sessions_lock:
            self.sessions[sid] = {"csrf": csrf}
        return sid, csrf

    def session_for(self, cookie_header, port):
        if not cookie_header:
            return None
        name = "dsbx_session_%d" % port
        for part in cookie_header.split(";"):
            key, sep, value = part.strip().partition("=")
            if not sep or key.strip() != name:
                continue
            sid = value.strip()
            with self._sessions_lock:
                session = self.sessions.get(sid)
                if session is not None:
                    return {"csrf": session["csrf"]}
        return None

    def human_key_matches(self, key):
        if not isinstance(key, str):
            return False
        try:
            raw = key.encode("utf-8")
        except UnicodeEncodeError:  # un sustituto aislado ("\ud800") no es la clave: 401, no excepción (C-03)
            return False
        return hmac.compare_digest(raw, self._keys[0][0].encode())


class Handler(BaseHTTPRequestHandler):
    server_version = "DsbxBackend/1"
    sys_version = ""

    def log_message(self, fmt, *args):
        b = self.server.backend
        b.log.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    @property
    def backend(self):
        return self.server.backend

    def send_json(self, status, obj, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in headers or ():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, status, body, content_type, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        for name, value in extra or ():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_result(self, result):
        status = 200 if result.get("ok") else STATUS.get(result.get("code"), 409)
        self.send_json(status, result)

    def _allowed_hosts(self):
        port = self.backend.port
        return ("127.0.0.1:%d" % port, "localhost:%d" % port)

    def discard_body(self):
        """Descarta sin parsear el cuerpo de un POST rechazado antes de leerlo.

        Con un plazo total (`drain_s`): un cliente que anuncia un cuerpo y no lo manda no
        retiene el hilo; se responde igual y se cierra la conexión (C-02).
        """
        if self.command != "POST" or getattr(self, "_body_gone", False):
            return
        self._body_gone = True
        self.close_connection = True
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if length <= 0 or length > MAX_BODY:
            return
        deadline = time.monotonic() + self.backend.drain_s
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
        except (OSError, ValueError):  # TimeoutError es OSError: plazo agotado o conexión rota
            return
        finally:
            self.connection.settimeout(None)

    def check_host(self):
        if self.headers.get("Host") not in self._allowed_hosts():
            self.discard_body()
            self.send_json(403, fail("forbidden", "Host u Origin no permitido"))
            return False
        return True

    def check_host_origin(self):
        """Host y Origin como hasta F1-co. Devuelve True si la petición puede seguir."""
        if not self.check_host():
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in ["http://" + h for h in self._allowed_hosts()]:
            self.discard_body()
            self.send_json(403, fail("forbidden", "Host u Origin no permitido"))
            return False
        return True

    def authenticate(self):
        """Bearer si trae Authorization; si no, cookie. (autor, vía, sesión) o None."""
        if self.headers.get("Authorization") is not None:
            author = self.backend.author_for(self.headers.get("Authorization"))
            if author is None:
                self.discard_body()
                self.send_json(401, fail("unauthorized", "Credencial no válida"))
                return None
            return author, "bearer", None
        session = self.backend.session_for(self.headers.get("Cookie"), self.backend.port)
        if session is None:
            self.discard_body()
            self.send_json(401, fail("unauthorized", "Credencial no válida"))
            return None
        return HUMAN, "cookie", session

    def check_csrf(self, session):
        origin = self.headers.get("Origin")
        token = self.headers.get("X-CSRF-Token")
        allowed = ["http://" + h for h in self._allowed_hosts()]
        if origin not in allowed or token is None or session is None or \
                not hmac.compare_digest(token.encode(), session["csrf"].encode()):
            self.discard_body()
            self.send_json(403, fail("csrf_failed", "CSRF no válido"))
            return False
        return True

    def serve_static(self, path):
        web_root = self.backend.web_root
        if path == "/":
            index = os.path.join(web_root, "index.html") if web_root else None
            if not index or not os.path.isfile(index):
                body = "Web sin construir: en app/web, npm ci --ignore-scripts y después npm run build".encode("utf-8")
                self.send_static(503, body, "text/plain; charset=utf-8")
                return
            with open(index, "rb") as f:
                body = f.read()
            self.send_static(200, body, "text/html; charset=utf-8",
                             extra=(("Content-Security-Policy",
                                     "default-src 'self'; frame-ancestors 'none'"),))
            return
        name = path[len("/assets/"):]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.(js|css)", name) or not web_root:
            self.send_json(404, fail("not_found", "Ruta desconocida"))
            return
        target = os.path.join(web_root, "assets", name)
        if not os.path.isfile(target):
            self.send_json(404, fail("not_found", "Ruta desconocida"))
            return
        with open(target, "rb") as f:
            body = f.read()
        ctype = "text/javascript; charset=utf-8" if name.endswith(".js") else "text/css; charset=utf-8"
        self.send_static(200, body, ctype)

    def read_body(self, author):
        """Cuerpo JSON como dict, o None si ya respondió."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.send_json(400, fail("bad_request", "Cuerpo ausente o mayor de 1 MiB"))
            return None
        try:
            raw = self.rfile.read(length) if length else b""
            self._body_gone = True
            body = json.loads(raw.decode("utf-8")) if length else {}
        except (UnicodeDecodeError, ValueError):
            self.send_json(400, fail("bad_request", "JSON ilegible"))
            return None
        if not isinstance(body, dict):
            self.send_json(400, fail("bad_request", "El cuerpo tiene que ser un objeto JSON"))
            return None
        if author is not None and "author" in body:
            given = body.pop("author")
            if not (isinstance(given, dict) and given.get("role") == author["role"]
                    and given.get("id", author["id"]) == author["id"]):
                self.send_json(403, fail("author_mismatch", "El autor no casa con la credencial", "/author"))
                return None
        return body

    def fields(self, body, spec):
        """Comprueba tipos del sobre; devuelve la lista de valores o None si ya respondió."""
        values = []
        for name, types in spec:
            v = body.get(name)
            if not isinstance(v, types) or isinstance(v, bool) and bool not in types:
                self.send_json(400, fail("bad_request", "Falta o tiene mal tipo: " + name, "/" + name))
                return None
            values.append(v)
        return values

    def do_GET(self):
        if not self.check_host_origin():
            return
        url = urlsplit(self.path)
        if url.path == "/" or url.path.startswith("/assets/"):
            self.serve_static(url.path)
            return
        if not url.path.startswith("/api/"):
            self.send_json(404, fail("not_found", "Ruta desconocida"))
            return
        auth = self.authenticate()
        if auth is None:
            return
        author = auth[0]
        if url.path == "/api/session":
            self.send_json(200, {"ok": True})
            return
        if self.path == "/api/scene":
            self.send_json(200, self.backend.store.snapshot())
        elif self.path == "/api/schema":
            self.send_json(*self.backend.profile.get_schema())
        elif self.path == "/api/catalog":
            self.send_json(200, self.backend.profile.get_catalog())
        elif self.path == "/api/profile":
            if author["role"] != "human":
                self.send_json(403, fail("forbidden", "Solo la persona lee el perfil"))
            else:
                self.send_json(200, self.backend.profile.get_profile())
        elif url.path == "/api/scene/changes":
            q = parse_qs(url.query)
            try:
                since = int(q["since_rev"][0])
                wait = min(max(float(q.get("timeout_s", ["0"])[0]), 0.0), WAIT_MAX)
            except (KeyError, ValueError):
                self.send_json(400, fail("bad_request", "since_rev o timeout_s no válidos"))
                return
            self.send_result(self.backend.changes(since, wait))
        elif self.path == "/api/events":
            self.stream_events()
        elif url.path == "/api/observation":
            self.send_json(200, self.backend.get_observation())
        else:
            self.send_json(404, fail("not_found", "Ruta desconocida"))

    def do_POST(self):
        if not self.check_host():
            return
        path = urlsplit(self.path).path
        if path == "/api/session":
            if not self.check_host_origin():
                return
            body = self.read_body(None)
            if body is None:
                return
            if not self.backend.human_key_matches(body.get("key")):
                self.send_json(401, fail("unauthorized", "Credencial no válida"))
                return
            sid, csrf = self.backend.create_session()
            cookie = "dsbx_session_%d=%s; HttpOnly; SameSite=Strict; Path=/" % (self.backend.port, sid)
            self.send_json(200, {"ok": True, "csrf": csrf}, headers=(("Set-Cookie", cookie),))
            return
        if not path.startswith("/api/"):
            if not self.check_host_origin():
                return
            self.send_json(404, fail("not_found", "Ruta desconocida"))
            return
        # Con cookie, el CSRF se exige antes de leer el cuerpo y manda su código;
        # con Bearer o sin credencial manda el Origin genérico de F1a.
        if self.headers.get("Authorization") is None:
            session = self.backend.session_for(self.headers.get("Cookie"), self.backend.port)
            if session is not None:
                if not self.check_csrf(session):
                    return
                author = HUMAN
                body = self.read_body(author)
                if body is None:
                    return
                try:
                    self.route_post(author, body)
                except Exception:  # nunca filtra detalles (ni claves) al cliente
                    self.send_json(500, fail("internal", "Error interno"))
                    raise
                return
        if not self.check_host_origin():
            return
        auth = self.authenticate()
        if auth is None:
            return
        author = auth[0]
        body = self.read_body(author)
        if body is None:
            return
        try:
            self.route_post(author, body)
        except Exception:  # nunca filtra detalles (ni claves) al cliente
            self.send_json(500, fail("internal", "Error interno"))
            raise

    def route_post(self, author, body):
        store, path = self.backend.store, self.path
        human = author["role"] == "human"
        if path == "/api/scene/ops":
            v = self.fields(body, [("doc_id", (str,)), ("request_id", (str,)), ("base_rev", (int,)),
                                   ("label", (str, type(None))), ("ops", (list,))])
            if v is not None:
                doc_id, request_id, base_rev, label, ops = v
                self.send_result(store.commit(author, request_id, doc_id, base_rev, label, ops))
        elif path in ("/api/scene/undo", "/api/scene/redo"):
            v = self.fields(body, [("doc_id", (str,)), ("request_id", (str,))])
            if v is not None:
                fn = store.undo if path.endswith("undo") else store.redo
                self.send_result(fn(author, v[1], v[0]))
        elif path.startswith("/api/scene/batches/") and path.endswith("/revert"):
            batch_id = path[len("/api/scene/batches/"):-len("/revert")]
            if not human:
                self.send_json(403, fail("forbidden", "Solo la persona revierte tandas"))
                return
            v = self.fields(body, [("doc_id", (str,)), ("request_id", (str,))])
            if v is not None:
                self.send_result(store.revert_batch(author, v[1], v[0], batch_id))
        elif path == "/api/ai/pause":
            if not human:
                self.send_json(403, fail("forbidden", "Solo la persona pausa a la IA"))
                return
            v = self.fields(body, [("paused", (bool,))])
            if v is not None:
                self.send_json(200, self.backend.set_paused(v[0]))
        elif path == "/api/scene/validate":
            v = self.fields(body, [("doc_id", (str,)), ("base_rev", (int,)), ("ops", (list,))])
            if v is not None:
                self.send_result(store.check(author, *v))
        elif path == "/api/apply/request":
            v = self.fields(body, [("doc_id", (str,)), ("rev", (int,)), ("hash", (str,))])
            if v is not None:
                self.send_result(self.backend.apply_request(author, *v))
        elif path == "/api/lease" or path.startswith("/api/lease/"):
            if not human:
                self.send_json(403, fail("forbidden", "Solo la persona pide préstamos"))
                return
            parts = path.split("/")  # ['', 'api', 'lease', <id>, <acción>]
            if path == "/api/lease":
                target, field = body.get("target"), body.get("field")
                if not isinstance(target, str) or not isinstance(field, (str, type(None))):
                    self.send_json(400, fail("bad_request", "target o field no válidos", "/target"))
                    return
                self.send_result(self.backend.lease_take(target, field))
            elif len(parts) == 5 and parts[4] == "renew":
                self.send_result(self.backend.lease_renew(parts[3]))
            elif len(parts) == 5 and parts[4] == "release":
                self.send_result(self.backend.lease_release(parts[3]))
            else:
                self.send_json(404, fail("not_found", "Ruta desconocida"))
        elif path == "/api/apply":
            if not human:
                self.send_json(403, fail("forbidden", "Solo la persona aplica"))
                return
            v = self.fields(body, [("doc_id", (str,)), ("rev", (int,)), ("hash", (str,))])
            if v is not None:
                self.send_result(self.backend.apply(*v))
        elif path == "/api/profile":
            if not human:
                self.send_json(403, fail("forbidden", "Solo la persona guarda el perfil"))
                return
            length = int(self.headers.get("Content-Length") or 0)
            self.send_json(*self.backend.profile.save_profile(body, length))
        elif path == "/api/reset":
            if not human:
                self.send_json(403, fail("forbidden", "Solo la persona quita del juego"))
                return
            v = self.fields(body, [("doc_id", (str,))])
            if v is not None:
                self.send_result(self.backend.reset(v[0]))
        elif path == "/api/observe":
            v = self.fields(body, [("doc_id", (str,))])
            if v is not None:
                self.send_result(self.backend.request_observe(v[0]))
        else:
            self.send_json(404, fail("not_found", "Ruta desconocida"))

    def stream_events(self):
        raw = self.headers.get("Last-Event-ID")
        try:
            last = int(raw) if raw is not None else None
        except ValueError:
            last = None
        q = self.backend.subscribe(last)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=PING_S)
                except queue.Empty:
                    self.backend.expire_leases()
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                if ev is None:  # cola llena o apagado: el cliente vuelve con snapshot
                    break
                seq, kind, data = ev
                self.wfile.write(("id: %d\nevent: %s\ndata: %s\n\n" % (seq, kind, data)).encode("utf-8"))
                self.wfile.flush()
        except OSError:
            pass
        finally:
            self.backend.unsubscribe(q)
            self.close_connection = True


def load_config(path, persist_peer_key=False):
    """Lee backend.json y completa lo que falte.

    Un fichero nuevo se escribe con todas sus claves. Uno ya existente solo se reescribe si le falta
    `human_key` o `ai_key`, o si le falta `peer_key` y `persist_peer_key` es verdadero, que es lo
    que pide `main`: así `peer_key` queda guardada desde el primer arranque del backend con bridge
    (brief F1b-bridge §2.1) y la puede leer el mod falso con `--config`.
    """
    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    defaults = {"port": 8765, "bridge_port": 8766, "scene": "data/scene.json", "catalog": "fixtures/catalog-m1.json",
                "web": "app/web/dist"}
    changed = not os.path.exists(path)
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    for k in ("human_key", "ai_key"):
        if not cfg.get(k):
            cfg[k] = secrets.token_urlsafe(32)
            changed = True
    if not cfg.get("peer_key"):
        cfg["peer_key"] = secrets.token_urlsafe(32)
        while cfg["peer_key"] in (cfg.get("human_key"), cfg.get("ai_key")):
            cfg["peer_key"] = secrets.token_urlsafe(32)
        if persist_peer_key:
            changed = True
    if changed:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backend local de Sandbox (F1a)")
    ap.add_argument("--config", required=True)
    ap.add_argument("--port", type=int)
    ap.add_argument("--bridge-port", type=int,
                    help="puerto del bridge dsbx1; con --port 0 y sin este, también efímero")
    args = ap.parse_args(argv)
    cfg = load_config(args.config, persist_peer_key=True)
    if args.bridge_port is not None:
        bridge_port = args.bridge_port
    elif args.port == 0:
        bridge_port = 0  # puertos efímeros: no choca con un backend que ya esté escuchando
    else:
        bridge_port = cfg.get("bridge_port")
    try:
        with open(cfg["catalog"], encoding="utf-8") as f:
            catalog = json.load(f)
        scene_dir = os.path.dirname(os.path.abspath(cfg["scene"]))
        os.makedirs(scene_dir, exist_ok=True)
        store = Store(cfg["scene"], catalog)
    except Exception as e:  # escena o catálogo ilegible o inválido: no se sobrescribe nada
        print("No se puede abrir la escena o el catálogo: %s" % e, file=sys.stderr)
        return 2
    try:
        backend = Backend(store, cfg["human_key"], cfg["ai_key"],
                          port=args.port if args.port is not None else cfg["port"],
                          web_root=cfg.get("web"), bridge_port=bridge_port,
                          peer_key=cfg.get("peer_key"))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print("Escuchando en http://127.0.0.1:%d" % backend.port, flush=True)
    if backend.bridge is not None:
        print("Bridge dsbx1 en 127.0.0.1:%d" % backend.bridge.port, flush=True)
    try:
        backend.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
