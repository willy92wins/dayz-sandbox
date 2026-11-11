"""Backend local de Sandbox (F1a): API HTTP y SSE sobre el almacén.

Uso, desde DayZSandbox_dev/:  python app/backend/server.py --config backend.json [--port N]
Solo biblioteca estándar. Brief: plans/2026-11-11-m1-f1a-brief.md §5.
"""
import argparse
import hmac
import json
import os
import queue
import secrets
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.backend.store import Store  # noqa: E402

MAX_BODY = 1024 * 1024
CLIENT_QUEUE = 1000
PING_S = 15
TAKE_LOCKED = ("armada", "rodando")
HUMAN = {"role": "human", "id": "web"}
AI = {"role": "ai", "id": "mcp"}

STATUS = {
    "conflict": 409, "stale_base": 409, "stale_apply": 409, "doc_changed": 409,
    "request_conflict": 409, "take_locked": 409, "ai_paused": 409,
    "already_reverted": 409, "nothing_to_undo": 409, "nothing_to_redo": 409,
    "entity_gone": 409,
    "bad_op": 422, "invalid": 422, "bad_base": 422,
    "unauthorized": 401, "forbidden": 403, "author_mismatch": 403,
    "bad_request": 400, "not_found": 404, "internal": 500,
}


def now_ms():
    return int(time.time() * 1000)


def fail(code, msg, pointer=""):
    return {"ok": False, "code": code, "pointer": pointer, "msg": msg}


class Backend:
    """Une el almacén con HTTP: credenciales, gate (pausa y toma), cola de órdenes y SSE."""

    def __init__(self, store, human_key, ai_key, port=0, horizon=1000, log=None):
        self.store = store
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
        store.on_commit = lambda record: self._emit("scene.commit", record)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.httpd.block_on_close = False
        self.httpd.backend = self

    @property
    def port(self):
        return self.httpd.server_address[1]

    def serve_forever(self):
        self.httpd.serve_forever(poll_interval=0.1)

    def shutdown(self):
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
                data = {"rev": snap["rev"], "hash": snap["hash"], "doc_id": snap["doc_id"],
                        "doc": snap["doc"], "ops": list(self.ops.values())}
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

    def apply(self, doc_id, rev, hash_):
        with self.store.lock:
            frozen = self.store.freeze(doc_id, rev, hash_)
            if not frozen.get("ok"):
                return frozen
            self._op_n += 1
            op = {"op_id": "op-%d" % self._op_n, "state": "pendiente",
                  "rev": frozen["rev"], "hash": frozen["hash"], "at_ms": now_ms()}
            self.ops[op["op_id"]] = op
            self._emit("op.state", dict(op))
            return {"ok": True, "op_id": op["op_id"]}

    def author_for(self, header):
        token = header[7:] if header and header.startswith("Bearer ") else None
        found = None
        for key, author in self._keys:
            if token is not None and hmac.compare_digest(token.encode(), key.encode()):
                found = author
        return found


class Handler(BaseHTTPRequestHandler):
    server_version = "DsbxBackend/1"
    sys_version = ""

    def log_message(self, fmt, *args):
        b = self.server.backend
        b.log.write("%s %s\n" % (self.log_date_time_string(), fmt % args))

    @property
    def backend(self):
        return self.server.backend

    def send_json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_result(self, result):
        status = 200 if result.get("ok") else STATUS.get(result.get("code"), 409)
        self.send_json(status, result)

    def check_request(self):
        """Host, Origin y credencial. Devuelve el autor o None si ya respondió."""
        port = self.backend.port
        allowed = ("127.0.0.1:%d" % port, "localhost:%d" % port)
        origin = self.headers.get("Origin")
        if self.headers.get("Host") not in allowed or \
                (origin is not None and origin not in ["http://" + h for h in allowed]):
            self.send_json(403, fail("forbidden", "Host u Origin no permitido"))
            return None
        author = self.backend.author_for(self.headers.get("Authorization"))
        if author is None:
            self.send_json(401, fail("unauthorized", "Credencial no válida"))
            return None
        return author

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
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except (UnicodeDecodeError, ValueError):
            self.send_json(400, fail("bad_request", "JSON ilegible"))
            return None
        if not isinstance(body, dict):
            self.send_json(400, fail("bad_request", "El cuerpo tiene que ser un objeto JSON"))
            return None
        if "author" in body:
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
        author = self.check_request()
        if author is None:
            return
        if self.path == "/api/scene":
            self.send_json(200, self.backend.store.snapshot())
        elif self.path == "/api/events":
            self.stream_events()
        else:
            self.send_json(404, fail("not_found", "Ruta desconocida"))

    def do_POST(self):
        author = self.check_request()
        if author is None:
            return
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
        elif path == "/api/apply":
            if not human:
                self.send_json(403, fail("forbidden", "Solo la persona aplica"))
                return
            v = self.fields(body, [("doc_id", (str,)), ("rev", (int,)), ("hash", (str,))])
            if v is not None:
                self.send_result(self.backend.apply(*v))
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


def load_config(path):
    cfg = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    defaults = {"port": 8765, "scene": "data/scene.json", "catalog": "fixtures/catalog-m1.json"}
    changed = not os.path.exists(path)
    for k, v in defaults.items():
        cfg.setdefault(k, v)
    for k in ("human_key", "ai_key"):
        if not cfg.get(k):
            cfg[k] = secrets.token_urlsafe(32)
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
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    try:
        with open(cfg["catalog"], encoding="utf-8") as f:
            catalog = json.load(f)
        scene_dir = os.path.dirname(os.path.abspath(cfg["scene"]))
        os.makedirs(scene_dir, exist_ok=True)
        store = Store(cfg["scene"], catalog)
    except Exception as e:  # escena o catálogo ilegible o inválido: no se sobrescribe nada
        print("No se puede abrir la escena o el catálogo: %s" % e, file=sys.stderr)
        return 2
    backend = Backend(store, cfg["human_key"], cfg["ai_key"],
                      port=args.port if args.port is not None else cfg["port"])
    print("Escuchando en http://127.0.0.1:%d" % backend.port, flush=True)
    try:
        backend.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backend.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
