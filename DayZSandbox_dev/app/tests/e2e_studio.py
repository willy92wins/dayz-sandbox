"""Arnés de la prueba de navegador F6-web parte 1: DayZ Studio (brief §8.2).

Solo biblioteca estándar. No empieza por `test`, así que `unittest discover`
no lo recoge. Sale 0 si pasa, 1 si falla y 2 si falta una precondición.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # DayZSandbox_dev/
sys.path.insert(0, str(ROOT))

from app.backend.server import AI, HUMAN, Backend, now_ms  # noqa: E402
from app.backend.store import Store  # noqa: E402

# F6-web parte 2 §8.2: DSBX_GUION=coedit corre coedit.e2e.cjs con sus filas C1-C10.
GUION = os.environ.get("DSBX_GUION") or "studio"
if GUION == "coedit":
    ALL_ROWS = ["C%d" % i for i in range(1, 11)]
    SCRIPT = "coedit.e2e.cjs"
elif GUION == "actores":
    # F3-web §5.2: DSBX_GUION=actores corre actores.e2e.cjs con sus filas AC1-AC8.
    ALL_ROWS = ["AC%d" % i for i in range(1, 9)]
    SCRIPT = "actores.e2e.cjs"
elif GUION == "camaras":
    # F4-web §4: DSBX_GUION=camaras corre camaras.e2e.cjs con sus filas CM1-CM8.
    ALL_ROWS = ["CM%d" % i for i in range(1, 9)]
    SCRIPT = "camaras.e2e.cjs"
else:
    ALL_ROWS = ["S%d" % i for i in range(1, 13)]
    SCRIPT = "studio.e2e.cjs"


def _playwright_resolvable(node):
    """Lo decide Node con el NODE_PATH de la corrida y desde la carpeta del guion, como hará el guion (C-05)."""
    if not node or not os.environ.get("NODE_PATH"):
        return False
    try:
        p = subprocess.run(
            [node, "-e", "require.resolve('playwright')"],
            env=dict(os.environ),
            cwd=str(ROOT / "app" / "web" / "e2e"),
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return p.returncode == 0


def _write_empty_scene(scene_path):
    """Escribe la fixture con entities y cameras vacíos y next a 1 en formato de almacén."""
    fixture_path = ROOT / "fixtures" / "escena-basica-cine.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        doc = json.load(f)
    doc["entities"] = []
    doc["cameras"] = []
    doc["next"] = {"act": 1, "obj": 1, "zmb": 1, "ani": 1, "cam": 1}
    with open(scene_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(
            {"rev": 1, "doc": doc},
            f,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        f.write("\n")


def main():
    missing = []
    node = shutil.which("node")
    if not node:
        missing.append("node")
    if not _playwright_resolvable(node):
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

    tmpdir = tempfile.mkdtemp(prefix="dsbx-e2e-studio-")
    log_path = os.path.join(tmpdir, "backend.log")
    log_file = open(log_path, "w+", encoding="utf-8", newline="\n", buffering=1)
    profile_path = os.path.join(tmpdir, "profile.json")
    secrets_seen = {human_key, ai_key}

    def collect_secrets(backend):
        if backend is None:
            return
        try:
            with backend._sessions_lock:
                for sid, info in list(backend.sessions.items()):
                    secrets_seen.add(sid)
                    if isinstance(info, dict) and info.get("csrf"):
                        secrets_seen.add(info["csrf"])
        except Exception:
            pass

    backend_holder = {"backend": None}
    threads = {"backend": None}
    script_proc = None
    script_output = []
    cmd_seq = 0
    try:
        with open(ROOT / "fixtures" / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)
        scene_path = os.path.join(tmpdir, "scene.json")
        _write_empty_scene(scene_path)
        store = Store(scene_path, catalog)

        def make_backend(target_port):
            last_err = None
            attempts = 40 if target_port != 0 else 1
            b = None
            for i in range(attempts):
                try:
                    b = Backend(
                        store,
                        human_key,
                        ai_key,
                        port=target_port,
                        web_root=str(ROOT / "app" / "web" / "dist"),
                        log=log_file,
                        profile_path=profile_path,
                    )
                    break
                except OSError as exc:
                    last_err = exc
                    if i + 1 < attempts:
                        time.sleep(0.05)
            if b is None:
                raise last_err
            b.httpd.handle_error = lambda *a: None
            t = threading.Thread(target=b.serve_forever, daemon=True)
            t.start()
            backend_holder["backend"] = b
            threads["backend"] = t
            return b

        backend = make_backend(0)
        port = backend.port

        def handle_cmd(obj):
            nonlocal cmd_seq
            cmd_seq += 1
            cmd = obj.get("cmd")
            b = backend_holder.get("backend")

            if cmd == "snapshot":
                snap = store.snapshot()
                return {
                    "ok": True,
                    "doc_id": snap["doc_id"],
                    "rev": snap["rev"],
                    "hash": snap["hash"],
                    "doc": snap["doc"],
                }

            if cmd in ("ai_ops", "human_ops"):
                author = AI if cmd == "ai_ops" else HUMAN
                snap = store.snapshot()
                base_rev = obj.get("base_rev", snap["rev"])
                req_id = "cmd-%d-%s" % (cmd_seq, secrets.token_hex(6))
                label = obj.get("label")
                ops = obj.get("ops", [])
                return store.commit(author, req_id, snap["doc_id"], base_rev, label, ops)

            if cmd in ("ai_call", "ai_apply_request", "human_apply_request"):
                if b is None:
                    return {"ok": False, "code": "no_backend"}
                key = human_key if cmd == "human_apply_request" else ai_key
                if cmd == "ai_call":
                    method, path, body = "GET", "/api/scene", None
                else:
                    method, path = "POST", "/api/apply/request"
                    snap = store.snapshot()
                    body = {"doc_id": snap["doc_id"], "rev": obj.get("rev", snap["rev"]),
                            "hash": obj.get("hash", snap["hash"])}
                data = json.dumps(body).encode("utf-8") if body is not None else None
                req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data, method=method)
                req.add_header("Authorization", "Bearer " + key)
                if data is not None:
                    req.add_header("Content-Type", "application/json")
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return {"ok": True, "status": resp.status, "body": json.loads(resp.read().decode("utf-8"))}
                except urllib.error.HTTPError as e:
                    return {"ok": True, "status": e.code, "body": json.loads(e.read().decode("utf-8") or "null")}

            if cmd == "human_revert":
                snap = store.snapshot()
                req_id = "cmd-%d-%s" % (cmd_seq, secrets.token_hex(6))
                return store.revert_batch(HUMAN, req_id, snap["doc_id"], obj.get("batch"))

            if cmd == "last_commit":
                with store.lock:
                    if store._hist:
                        rec = store._hist[-1]
                        return {
                            "ok": True,
                            "label": rec.get("label"),
                            "author": rec.get("author"),
                            "rev": rec.get("rev"),
                            "batch": rec.get("batch"),
                        }
                    return {"ok": True, "label": None, "author": None, "rev": None, "batch": None}

            if cmd == "op_state":
                if b is None:
                    return {"ok": False, "code": "no_backend"}
                op_id = obj.get("op_id")
                at = now_ms()
                with b.store.lock:
                    m = re.match(r"^op-(\d+)$", str(op_id or ""))
                    if m:
                        n_id = int(m.group(1))
                        if n_id > b._op_n:
                            b._op_n = n_id
                    op = b.ops.get(op_id)
                    if op is None:
                        snap = b.store.snapshot()
                        op = {
                            "op_id": op_id,
                            "state": obj.get("state"),
                            "rev": snap["rev"],
                            "hash": snap["hash"],
                            "at_ms": at,
                            "origin": obj.get("origin"),
                        }
                        b.ops[op_id] = op
                    else:
                        op["state"] = obj.get("state")
                        op["origin"] = obj.get("origin")
                        op["at_ms"] = at
                    if "reason" in obj and obj.get("reason") is not None:
                        op["reason"] = obj.get("reason")
                    else:
                        op.pop("reason", None)
                    if "verb" in obj and obj.get("verb") is not None:
                        op["verb"] = obj.get("verb")
                    else:
                        op.pop("verb", None)
                    b.op_mono[op_id] = b.clock()
                    b._emit("op.state", dict(op))
                return {"ok": True, "at_ms": at}

            if cmd == "count_ops":
                if b is None:
                    return {"ok": False, "code": "no_backend"}
                with b.store.lock:
                    n = len(b.ops)
                return {"ok": True, "n": n}

            if cmd == "profile_read":
                if not os.path.exists(profile_path):
                    return {"ok": True, "text": None}
                with open(profile_path, "r", encoding="utf-8", errors="replace") as f:
                    return {"ok": True, "text": f.read()}

            if cmd == "profile_write":
                text = obj.get("text")
                if text is None:
                    if os.path.exists(profile_path):
                        os.remove(profile_path)
                elif isinstance(text, str):
                    with open(profile_path, "w", encoding="utf-8", newline="") as f:
                        f.write(text)
                else:
                    return {"ok": False, "code": "bad_text"}
                return {"ok": True}

            if cmd == "leases":
                if b is None:
                    return {"ok": True, "leases": []}
                with b.store.lock:
                    b.expire_leases()
                    live = b.leases.live()
                return {
                    "ok": True,
                    "leases": [
                        {
                            "lease_id": l["lease_id"],
                            "target": l["target"],
                            "field": l["field"],
                        }
                        for l in live
                    ],
                }

            if cmd == "stop_backend":
                if b is not None:
                    collect_secrets(b)
                    b.shutdown()
                    old_thread = threads.get("backend")
                    if old_thread is not None:
                        old_thread.join(timeout=10)
                    backend_holder["backend"] = None
                    threads["backend"] = None
                return {"ok": True}

            if cmd == "start_backend":
                if b is None:
                    make_backend(port)
                return {"ok": True}

            return {"ok": False, "code": "unknown_cmd"}

        env = dict(os.environ)
        env["DSBX_URL"] = "http://127.0.0.1:%d" % port
        env["DSBX_HUMAN_KEY"] = human_key

        script_proc = subprocess.Popen(
            [node, str(ROOT / "app" / "web" / "e2e" / SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            cwd=str(ROOT),
        )

        timer = threading.Timer(600, lambda: script_proc and script_proc.kill())
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
                except Exception as exc:
                    resp = {"ok": False, "error": type(exc).__name__}
                try:
                    assert script_proc.stdin is not None
                    script_proc.stdin.write(json.dumps(resp, ensure_ascii=False) + "\n")
                    script_proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    break
            code = script_proc.wait(timeout=10)
        finally:
            timer.cancel()

        collect_secrets(backend_holder.get("backend"))
        try:
            log_file.flush()
        except Exception:
            pass
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                log_text = f.read()
        except OSError:
            log_text = ""
        profile_text = ""
        if os.path.exists(profile_path):
            try:
                with open(profile_path, encoding="utf-8", errors="replace") as f:
                    profile_text = f.read()
            except OSError:
                profile_text = ""
        out_text = "".join(script_output)
        secret_hit = any(
            s and (s in log_text or s in out_text or s in profile_text)
            for s in secrets_seen
        )
        if secret_hit:
            print("FALLA: secreto en el log, en el perfil o en la salida")
            return 1
        ok_lines = {ln.strip() for ln in script_output}
        raw_only = os.environ.get("DSBX_ONLY")
        if raw_only is not None and raw_only.strip():
            requested_rows = [p.strip().upper() for p in raw_only.split(",") if p.strip()]
            unknown_rows = [r for r in requested_rows if r not in ALL_ROWS]
            if not requested_rows or unknown_rows:
                print("FALLA: DSBX_ONLY no valido: " + raw_only)
                return 1
            missing_rows = [r for r in requested_rows if ("%s OK" % r) not in ok_lines]
            if code != 0:
                extra = (" (faltan: %s)" % ", ".join(missing_rows)) if missing_rows else ""
                print("FALLA: el guion salio con %s%s" % (code, extra))
                return 1
            if missing_rows:
                print("FALLA: faltan filas: " + ", ".join(missing_rows))
                return 1
            print("PARCIAL: " + ",".join(requested_rows))
            return 0
        missing_rows = [r for r in ALL_ROWS if ("%s OK" % r) not in ok_lines]
        if code != 0:
            extra = (" (faltan: %s)" % ", ".join(missing_rows)) if missing_rows else ""
            print("FALLA: el guion salio con %s%s" % (code, extra))
            return 1
        if missing_rows:
            print("FALLA: faltan filas: " + ", ".join(missing_rows))
            return 1
        print("e2e_studio: OK")
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
        try:
            log_file.close()
        except Exception:
            pass
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
