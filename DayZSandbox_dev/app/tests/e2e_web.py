"""Arnés de la prueba de navegador F1b-web (brief §6.1).

Solo biblioteca estándar. No empieza por `test`, así que `unittest discover`
no lo recoge. Sale 0 si pasa, 1 si falla y 2 si falta una precondición.
"""
import http.client
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # DayZSandbox_dev/
sys.path.insert(0, str(ROOT))

from app.backend.server import Backend, now_ms  # noqa: E402
from app.backend.store import Store  # noqa: E402


def _playwright_resolvable():
    node_path = os.environ.get("NODE_PATH", "")
    for entry in node_path.split(os.pathsep):
        if not entry:
            continue
        p = Path(entry)
        if (p / "playwright" / "package.json").is_file():
            return True
        if (p / "node_modules" / "playwright" / "package.json").is_file():
            return True
    return False


class EvilHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        cookie = self.headers.get("Cookie")
        if cookie:
            self.server.captured_cookies.append(cookie)
        if self.path.split("?")[0] != "/evil.html":
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        snap = self.server.get_snapshot()
        backend_url = self.server.backend_url
        doc_id = snap["doc_id"]
        rev = snap["rev"]
        hash_ = snap["hash"]
        name = json.dumps({"doc_id": doc_id, "rev": rev, "hash": hash_, "x": ""})
        # El nombre del único campo es el JSON hasta "x":" y su valor es "}
        field_name = name[:-2]  # quita el "" final: queda ...,"x":"
        # Reconstrucción exacta: name debe ser {"doc_id":...,"rev":...,"hash":...,"x":"
        field_name = '{"doc_id":%s,"rev":%s,"hash":%s,"x":"' % (
            json.dumps(doc_id), rev, json.dumps(hash_))
        body_obj = {"doc_id": doc_id, "rev": rev, "hash": hash_}
        html = """<!doctype html>
<html><head><meta charset="utf-8"><title>evil</title></head><body>
<script>
(function () {
  var backend = %s;
  var body = %s;
  var fieldName = %s;
  fetch(backend + "/api/apply", {method: "POST", credentials: "include",
    headers: {"Content-Type": "text/plain"}, body: body})
    .catch(function () {})
    .then(function () {
      var form = document.createElement("form");
      form.method = "POST";
      form.action = backend + "/api/apply";
      form.enctype = "text/plain";
      var input = document.createElement("input");
      input.type = "hidden";
      input.name = fieldName;
      input.value = '\\"}';
      form.appendChild(input);
      document.body.appendChild(form);
      document.title = "evil-sent";
      form.submit();
    });
})();
</script>
</body></html>
""" % (json.dumps(backend_url), json.dumps(json.dumps(body_obj)), json.dumps(field_name))
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    missing = []
    node = shutil.which("node")
    if not node:
        missing.append("node")
    if not _playwright_resolvable():
        missing.append("NODE_PATH que resuelva playwright")
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        missing.append("PLAYWRIGHT_BROWSERS_PATH")
    dist_index = ROOT / "app" / "web" / "dist" / "index.html"
    if not dist_index.is_file():
        missing.append("app/web/dist/index.html")
    if missing:
        print("INCONCLUSO: falta " + ", ".join(missing))
        return 2

    human_key = secrets.token_urlsafe(32)
    ai_key = secrets.token_urlsafe(32)
    while ai_key == human_key:
        ai_key = secrets.token_urlsafe(32)

    tmpdir = tempfile.mkdtemp(prefix="dsbx-e2e-")
    log_path = os.path.join(tmpdir, "backend.log")
    log_file = open(log_path, "w+", encoding="utf-8", buffering=1)
    secrets_seen = {human_key, ai_key}

    def collect_secrets(backend):
        try:
            with backend._sessions_lock:
                for sid, info in list(backend.sessions.items()):
                    secrets_seen.add(sid)
                    if isinstance(info, dict) and info.get("csrf"):
                        secrets_seen.add(info["csrf"])
        except Exception:
            pass

    backend_holder = {}
    threads = {}
    evil = None
    script_proc = None
    script_output = []
    try:
        with open(ROOT / "fixtures" / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)
        scene_path = os.path.join(tmpdir, "scene.json")
        store = Store(scene_path, catalog)

        def make_backend(port):
            b = Backend(store, human_key, ai_key, port=port,
                        web_root=str(ROOT / "app" / "web" / "dist"), log=log_file)
            b.httpd.handle_error = lambda *a: None
            t = threading.Thread(target=b.serve_forever, daemon=True)
            t.start()
            backend_holder["backend"] = b
            threads["backend"] = t
            return b

        backend = make_backend(0)
        port = backend.port

        evil = ThreadingHTTPServer(("127.0.0.1", 0), EvilHandler)
        evil.captured_cookies = []
        evil.backend_url = "http://127.0.0.1:%d" % port
        evil.get_snapshot = lambda: backend_holder["backend"].store.snapshot()
        evil_thread = threading.Thread(target=evil.serve_forever, daemon=True)
        evil_thread.start()
        evil_port = evil.server_address[1]

        def http_from_python(method, path, cookie_value, extra_headers, body_obj):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            headers = {"Host": "127.0.0.1:%d" % port}
            if cookie_value:
                headers["Cookie"] = "dsbx_session_%d=%s" % (port, cookie_value)
            headers.update(extra_headers or {})
            data = b""
            if body_obj is not None:
                data = json.dumps(body_obj).encode("utf-8")
                headers["Content-Type"] = "application/json"
                headers["Content-Length"] = str(len(data))
            conn.request(method, path, body=data if data else None, headers=headers)
            resp = conn.getresponse()
            text = resp.read().decode("utf-8", "replace")
            status = resp.status
            conn.close()
            try:
                parsed = json.loads(text) if text else {}
            except ValueError:
                parsed = {}
            return status, parsed

        def handle_cmd(obj):
            cmd = obj.get("cmd")
            b = backend_holder["backend"]
            if cmd == "op_state":
                op_id = obj.get("op_id")
                at = now_ms()
                with b.store.lock:
                    op = b.ops.get(op_id)
                    if op is None:
                        snap = b.store.snapshot()
                        op = {"op_id": op_id, "state": obj.get("state"),
                              "rev": snap["rev"], "hash": snap["hash"],
                              "at_ms": at, "origin": obj.get("origin")}
                        b.ops[op_id] = op
                    else:
                        op["state"] = obj.get("state")
                        op["origin"] = obj.get("origin")
                        op["at_ms"] = at
                    b.op_mono[op_id] = b.clock()
                    b._emit("op.state", dict(op))
                return {"ok": True, "at_ms": at}
            if cmd == "count_ops":
                with b.store.lock:
                    n = len(b.ops)
                return {"ok": True, "n": n}
            if cmd == "log_count":
                needle = obj.get("needle", "")
                try:
                    log_file.flush()
                except Exception:
                    pass
                try:
                    with open(log_path, encoding="utf-8", errors="replace") as f:
                        lines = f.read().splitlines()
                except OSError:
                    lines = []
                return {"ok": True, "n": sum(1 for ln in lines if needle in ln)}
            if cmd == "drop_sse":
                with b.store.lock:
                    for q in list(b.clients):
                        b._close_client(q)
                return {"ok": True}
            if cmd == "replay_stolen":
                name = "dsbx_session_%d=" % port
                captured_value = None
                for header in list(evil.captured_cookies):
                    for part in header.split(";"):
                        part = part.strip()
                        if part.startswith(name):
                            captured_value = part[len(name):].strip()
                            break
                    if captured_value:
                        break
                captured = captured_value is not None
                with b.store.lock:
                    before = len(b.ops)
                session_status = 0
                session_keys = []
                apply_status = 0
                apply_code = None
                if captured:
                    origin = "http://127.0.0.1:%d" % port
                    session_status, parsed = http_from_python(
                        "GET", "/api/session", captured_value, {"Origin": origin}, None)
                    if isinstance(parsed, dict):
                        session_keys = sorted(parsed.keys())
                    snap = b.store.snapshot()
                    body = {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]}
                    apply_status, parsed2 = http_from_python(
                        "POST", "/api/apply", captured_value,
                        {"Origin": origin, "X-CSRF-Token": "token-inventado"}, body)
                    if isinstance(parsed2, dict):
                        apply_code = parsed2.get("code")
                with b.store.lock:
                    after = len(b.ops)
                return {"ok": True, "captured": captured,
                        "session_status": session_status, "session_keys": session_keys,
                        "apply_status": apply_status, "apply_code": apply_code,
                        "ops_delta": after - before}
            if cmd == "restart":
                collect_secrets(b)
                b.shutdown()
                old_thread = threads.get("backend")
                if old_thread is not None:
                    old_thread.join(timeout=10)
                make_backend(port)
                return {"ok": True}
            return {"ok": False, "code": "unknown_cmd"}

        env = dict(os.environ)
        env["DSBX_URL"] = "http://127.0.0.1:%d" % port
        env["DSBX_HUMAN_KEY"] = human_key
        env["DSBX_EVIL_URL"] = "http://127.0.0.1:%d/evil.html" % evil_port

        script_proc = subprocess.Popen(
            [node, str(ROOT / "app" / "web" / "e2e" / "queue.e2e.cjs")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
            cwd=str(ROOT))

        timer = threading.Timer(300, lambda: script_proc and script_proc.kill())
        timer.daemon = True
        timer.start()
        try:
            assert script_proc.stdout is not None
            for line in script_proc.stdout:
                script_output.append(line)
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    obj = json.loads(stripped)
                except ValueError:
                    obj = None
                if not isinstance(obj, dict) or "cmd" not in obj:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    continue
                try:
                    resp = handle_cmd(obj)
                except Exception:
                    resp = {"ok": False}
                try:
                    script_proc.stdin.write(json.dumps(resp) + "\n")
                    script_proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
            code = script_proc.wait(timeout=10)
        finally:
            timer.cancel()

        collect_secrets(backend_holder["backend"])
        try:
            log_file.flush()
        except Exception:
            pass
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                log_text = f.read()
        except OSError:
            log_text = ""
        out_text = "".join(script_output)
        secret_hit = any(s and (s in log_text or s in out_text) for s in secrets_seen)
        if secret_hit:
            print("FALLA: secreto en el log o en la salida")
            return 1
        if code != 0:
            print("FALLA: el guion salio con %s" % code)
            return 1
        print("e2e_web: OK")
        return 0
    finally:
        if script_proc is not None and script_proc.poll() is None:
            try:
                script_proc.kill()
            except OSError:
                pass
        try:
            b = backend_holder.get("backend")
            if b is not None:
                collect_secrets(b)
                b.shutdown()
                t = threads.get("backend")
                if t is not None:
                    t.join(timeout=10)
        except Exception:
            pass
        if evil is not None:
            try:
                evil.shutdown()
                evil.server_close()
            except Exception:
                pass
        try:
            log_file.close()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
