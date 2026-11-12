"""Fachada MCP de la escena para la IA (F1-co §3): stdio JSON-RPC sobre la API local.

Uso, desde DayZSandbox_dev/:  python app/mcp/facade.py --config backend.json
Solo biblioteca estándar. Usa la clave de la IA; nunca la de la persona.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid

PROTOCOLS = ("2025-06-18", "2025-03-26")
WAIT_MAX = 30
RECENT = 20

NOT_APPLY = " La IA no aplica nada al juego: aplicar lo aprueba la persona en la web."
TOOLS = [
    {"name": "scene_get",
     "description": "Lee la escena actual con su revisión, su hash y las últimas tandas con su autor." + NOT_APPLY,
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "scene_ops",
     "description": "Manda una tanda atómica de operaciones sobre la escena (todo o nada); puede volver conflict, busy_human, take_locked, ai_paused, stale_base o doc_changed." + NOT_APPLY,
     "inputSchema": {"type": "object", "required": ["base_rev", "ops"], "additionalProperties": False,
                     "properties": {"base_rev": {"type": "integer"}, "label": {"type": ["string", "null"]},
                                    "ops": {"type": "array", "items": {"type": "object"}}}}},
    {"name": "scene_validate",
     "description": "Valida una tanda sin aplicarla y dice qué rechazo daría." + NOT_APPLY,
     "inputSchema": {"type": "object", "required": ["base_rev", "ops"], "additionalProperties": False,
                     "properties": {"base_rev": {"type": "integer"},
                                    "ops": {"type": "array", "items": {"type": "object"}}}}},
    {"name": "scene_wait_changes",
     "description": "Espera hasta timeout_s segundos (máx. 30) a que la escena cambie después de since_rev." + NOT_APPLY,
     "inputSchema": {"type": "object", "required": ["since_rev"], "additionalProperties": False,
                     "properties": {"since_rev": {"type": "integer"},
                                    "timeout_s": {"type": "number", "minimum": 0, "maximum": WAIT_MAX}}}},
    {"name": "apply_request",
     "description": "No aplica: pide a la persona, con una tarjeta en la web, que apruebe aplicar esta revisión al juego.",
     "inputSchema": {"type": "object", "required": ["rev", "hash"], "additionalProperties": False,
                     "properties": {"rev": {"type": "integer"}, "hash": {"type": "string"}}}},
]


class Backend:
    def __init__(self, port, key):
        self.base = "http://127.0.0.1:%d" % port
        self._key = key

    def call(self, method, path, body=None, timeout=10):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Authorization", "Bearer " + self._key)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:  # 4xx/5xx con cuerpo JSON del backend
            try:
                return json.loads(e.read().decode("utf-8"))
            except ValueError:
                return {"ok": False, "code": "http_%d" % e.code, "pointer": "", "msg": "respuesta ilegible"}


class Facade:
    def __init__(self, backend):
        self.b = backend
        self.seen_rev = None
        self.doc_id = None

    def _changes(self):
        """Tandas de la persona desde la última respuesta; luego sube seen_rev."""
        if self.seen_rev is None:
            return []
        r = self.b.call("GET", "/api/scene/changes?since_rev=%d&timeout_s=0" % self.seen_rev)
        if not r.get("ok", True) or "batches" not in r:
            return {"reload": True}
        human = [x for x in r["batches"] if x.get("author", {}).get("role") == "human"]
        self.seen_rev = max([self.seen_rev] + [x["rev"] for x in r["batches"]])
        return human

    def _ensure_doc(self):
        if self.doc_id is None:
            snap = self.b.call("GET", "/api/scene")
            self.doc_id = snap.get("doc_id")
            if self.seen_rev is None:
                self.seen_rev = snap.get("rev")

    def tool(self, name, args):
        if name == "scene_get":
            snap = self.b.call("GET", "/api/scene")
            self.doc_id = snap.get("doc_id")
            since = max(0, snap.get("rev", 0) - RECENT)
            ch = self.b.call("GET", "/api/scene/changes?since_rev=%d&timeout_s=0" % since)
            recent = ch.get("batches", []) if ch.get("ok", True) else []
            changes = self._changes()
            self.seen_rev = max(self.seen_rev or 0, snap.get("rev", 0))
            return {"rev": snap.get("rev"), "hash": snap.get("hash"), "doc_id": snap.get("doc_id"),
                    "doc": snap.get("doc"), "recent": recent[-RECENT:]}, changes
        self._ensure_doc()
        if name == "scene_ops":
            body = {"doc_id": self.doc_id, "request_id": str(uuid.uuid4()), "base_rev": args.get("base_rev"),
                    "label": args.get("label"), "ops": args.get("ops")}
            try:
                res = self.b.call("POST", "/api/scene/ops", body)
            except (urllib.error.URLError, OSError):  # un reintento con el mismo request_id
                res = self.b.call("POST", "/api/scene/ops", body)
        elif name == "scene_validate":
            res = self.b.call("POST", "/api/scene/validate",
                              {"doc_id": self.doc_id, "base_rev": args.get("base_rev"), "ops": args.get("ops")})
        elif name == "scene_wait_changes":
            t = min(max(float(args.get("timeout_s", WAIT_MAX)), 0), WAIT_MAX)
            res = self.b.call("GET", "/api/scene/changes?since_rev=%d&timeout_s=%g" % (int(args.get("since_rev")), t),
                              timeout=t + 10)
        elif name == "apply_request":
            res = self.b.call("POST", "/api/apply/request",
                              {"doc_id": self.doc_id, "rev": args.get("rev"), "hash": args.get("hash")})
        else:
            raise KeyError(name)
        return res, self._changes()

    def handle(self, msg):
        """Una petición JSON-RPC → su respuesta (o None si es una notificación)."""
        mid, method = msg.get("id"), msg.get("method")
        if mid is None:
            return None
        params = msg.get("params") or {}
        if method == "initialize":
            asked = params.get("protocolVersion")
            result = {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "dsbx-scene", "version": "1"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            if name not in {t["name"] for t in TOOLS}:
                return error(mid, -32602, "tool desconocida")
            try:
                res, changes = self.tool(name, params.get("arguments") or {})
            except (urllib.error.URLError, OSError):
                res, changes = {"ok": False, "code": "backend_unreachable", "pointer": "",
                                "msg": "No se puede hablar con el backend local"}, []
            except (TypeError, ValueError):
                return error(mid, -32602, "argumentos no válidos")
            payload = {"result": res, "changes_since_last_call": changes}
            is_error = isinstance(res, dict) and res.get("ok") is False
            result = {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
                      "isError": is_error}
        else:
            return error(mid, -32601, "método desconocido")
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def error(mid, code, msg):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}}


def serve(facade, stdin, stdout):
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if not isinstance(msg, dict):
                raise ValueError
        except ValueError:
            reply = error(None, -32700, "JSON ilegible")
        else:
            reply = facade.handle(msg)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            stdout.flush()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fachada MCP de la escena (F1-co)")
    ap.add_argument("--config", required=True)
    args = ap.parse_args(argv)
    try:
        with open(args.config, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        print("No se puede leer la configuración", file=sys.stderr)
        return 2
    key = cfg.get("ai_key")
    if not key:
        print("backend.json no tiene ai_key: la fachada no usa otra clave", file=sys.stderr)
        return 2
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    serve(Facade(Backend(int(cfg.get("port", 8765)), key)), sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
