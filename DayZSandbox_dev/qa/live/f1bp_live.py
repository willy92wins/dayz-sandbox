#!/usr/bin/env python3
"""Orquestador del arnes de F1b-peers en partida (nucleo, G1, G2, G3 y G9).

CLI:
    python qa/live/f1bp_live.py run --build diag|retail --evidence <dir>
           --server-profile <S> --client-profile <C> --pids-file <p>
           --scenarios G1,G2,G3,G9 [--pbo <ruta>] [--fake]

Escribe la evidencia de EVIDENCIA.md. El backend real corre en este proceso,
igual que el proxy de fallos y (con --fake) el mod falso. Ninguna clave sale
en ningun fichero de la evidencia: solo su sha256 en manifest.json.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import http.client
import importlib.util
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.server import Backend  # noqa: E402
from app.backend.store import Store  # noqa: E402
from app.tests.fake_mod import FakeMod  # noqa: E402
from app.tools import peer_config  # noqa: E402


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_FAULT_PROXY = _load_module(
    "f1bp_fault_proxy", os.path.join(os.path.dirname(os.path.abspath(__file__)), "fault_proxy.py")
)
FaultProxy = _FAULT_PROXY.FaultProxy

LEASE_MS = 3000
HOLD_MS = 2000
TTL_MS = 10000
PEERS_TIMEOUT_S = 300
RULES_TIMEOUT_S = 5
LOGS_READY_TIMEOUT_S = 15 * 60
PIDS_TIMEOUT_S = 180
G9_OPS = 100
G9_WAIT_S = 5.0
OBSERVED_WAIT_S = 60.0
RECOVERY_WINDOW_S = 60.0  # R20
RECOVERY_STABLE_WAIT_S = 30.0  # R20
G4A_HELLO_401_WAIT_S = 30.0  # R25
G6_POLL_ALIGN_S = 5.0  # H-14

LAST_SECRETS = ()


def _now_ms():
    return time.monotonic() * 1000.0


def _wall_now():
    """Hora de pared local "HH:MM:SS.mmm", como la que encabeza cada linea del log del motor.

    Con (t_ms, wall) tomados en el mismo instante, el evaluador situa las lineas del log en el
    reloj del arnes (brief v1.4, sec. 10, H-04).
    """
    now = time.time()
    return time.strftime("%H:%M:%S", time.localtime(now)) + ".%03d" % (int(now * 1000) % 1000)


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _redact(text, secrets_used):
    out = str(text)
    for secret in secrets_used:
        if secret:
            out = out.replace(secret, "***")
    return out


def _atomic_write_json(path, obj):
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = "%s.tmp.%d.%d" % (path, os.getpid(), threading.get_ident())
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    last_error = None
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.01)
    if last_error is not None:
        raise last_error


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _read_jsonl(path):
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _parse_scenarios(value):
    if value is None:
        return []
    out = []
    for item in str(value).split(","):
        item = item.strip().upper()
        if item:
            out.append(item)
    return out


def _rule_fields(rule_ids):
    """Campos de inyeccion de un `case` (R9): `rule_id` si hay una, `rule_ids` si hay varias."""
    ids = [r for r in (rule_ids or []) if r]
    if len(ids) == 1:
        return {"rule_id": ids[0]}
    if ids:
        return {"rule_ids": ids}
    return {}


def _git_provenance(root, runner=subprocess.run):
    """(git_head, git_dirty) de la raiz del worktree `root` (R1).

    git_head es el SHA completo de HEAD; git_dirty es true si `git status --porcelain` fuera de
    DayZSandbox_dev/evidence da algo. Sin git, fuera de un repo, o si el repo que ve git no tiene
    `root` como raiz: (None, True). Solo lectura: GIT_OPTIONAL_LOCKS=0 evita que status toque el indice.
    """
    env = dict(os.environ)
    env["GIT_OPTIONAL_LOCKS"] = "0"

    def run_git(args):
        try:
            done = runner(
                ["git", "-C", str(root)] + list(args),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                env=env,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode != 0:
            return None
        return done.stdout

    top = run_git(["rev-parse", "--show-toplevel"])
    head = run_git(["rev-parse", "HEAD"])
    status = run_git(["status", "--porcelain", "--", ".", ":(exclude)DayZSandbox_dev/evidence"])
    if top is None or head is None or status is None:
        return None, True
    top = top.strip()
    try:
        same = os.path.samefile(top, str(root))
    except OSError:
        same = os.path.normcase(os.path.realpath(top)) == os.path.normcase(os.path.realpath(str(root)))
    head = head.strip().lower()
    if not same or len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
        return None, True
    return head, bool(status.strip())


def _count_in_file(path, needles, chunk=4 * 1024 * 1024):
    """Apariciones literales de cada `needle` (bytes) en el fichero, por trozos. None si no se lee."""
    needles = [n for n in needles if n]
    keep = max((len(n) for n in needles), default=1) - 1
    total = 0
    tail = b""
    try:
        with open(path, "rb") as fh:
            while True:
                data = fh.read(chunk)
                if not data:
                    break
                buf = tail + data
                for needle in needles:
                    total += buf.count(needle)
                # La cola (menos que una clave entera) no puede contener una aparicion completa:
                # no se cuenta dos veces.
                tail = buf[-keep:] if keep > 0 else b""
    except OSError:
        return None
    return total


class EvidenceWriter:
    """Escribe samples/<G>.jsonl con una linea por evento, UTF-8 y LF, ordenadas por t_ms.

    R27: un evento puede llevar un t_ms anterior al de su escritura (apply.t_ms es el de antes del
    POST, op_state.t_ms el del suceso del backend). Se guardan todos los eventos del escenario y
    `end()` los escribe ordenados por (t_ms, orden de emision); no hay ventana de retencion. El
    evaluador exige que t_ms no retroceda en el fichero.
    """

    def __init__(self, samples_dir):
        self.samples_dir = samples_dir
        self._lock = threading.RLock()
        self._fh = None
        self._pending = []
        self._seq = 0
        self.scenario = None

    def begin(self, scenario):
        with self._lock:
            self.end()
            self.scenario = scenario
            path = os.path.join(self.samples_dir, scenario + ".jsonl")
            self._fh = open(path, "w", encoding="utf-8", newline="\n")
            self._pending = []

    def emit(self, ev, t_ms=None, **fields):
        with self._lock:
            if self._fh is None:
                return
            obj = {"t_ms": float(t_ms) if t_ms is not None else _now_ms(), "ev": ev}
            obj.update(fields)
            line = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            self._seq += 1
            self._pending.append((obj["t_ms"], self._seq, line))

    def end(self):
        with self._lock:
            if self._fh is not None:
                try:
                    for _t, _n, line in sorted(self._pending, key=lambda p: (p[0], p[1])):
                        self._fh.write(line + "\n")
                    self._fh.flush()
                finally:
                    self._fh.close()
                self._fh = None
            self._pending = []
            self.scenario = None

    def append(self, scenario, ev, **fields):
        path = os.path.join(self.samples_dir, scenario + ".jsonl")
        obj = {"t_ms": _now_ms(), "ev": ev}
        obj.update(fields)
        line = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")


class RingPoller(threading.Thread):
    """Lee backend.ring cada 50 ms y escribe cada transicion nueva de una op."""

    def __init__(self, backend, writer, stop_event):
        super().__init__(daemon=True, name="f1bp-ring-poller")
        self.backend = backend
        self.writer = writer
        self.stop_event = stop_event
        with backend.store.lock:
            self.baseline = backend.seq
        # R5: la sesion del bridge a la que pertenece cada op de este backend.
        self.session = getattr(getattr(backend, "bridge", None), "session", None)
        self.seen = set()
        self._lock = threading.Lock()

    def _drain_locked(self):
        entries = []
        try:
            with self.backend.store.lock:
                entries = list(self.backend.ring)
        except Exception:
            entries = []
        for seq, kind, data in entries:
            if seq <= self.baseline or seq in self.seen:
                continue
            self.seen.add(seq)
            if kind != "op.state":
                continue
            try:
                item = json.loads(data)
            except (TypeError, ValueError):
                continue
            if not isinstance(item, dict):
                continue
            # R6: el instante del suceso es el `at_ms` (hora de pared, ms) que el backend pone al
            # evento, llevado al reloj del arnes con el desfase de este instante; sin `at_ms`, el de
            # lectura, con t_src "lectura".
            at_ms = item.get("at_ms")
            extra = {}
            if isinstance(at_ms, (int, float)) and not isinstance(at_ms, bool):
                t_ms = float(at_ms) + (_now_ms() - time.time() * 1000.0)
            else:
                t_ms = _now_ms()
                extra["t_src"] = "lectura"
            self.writer.emit(
                "op_state",
                t_ms=t_ms,
                op_id=item.get("op_id"),
                state=item.get("state"),
                reason=item.get("reason"),
                session=self.session,
                **extra
            )

    def drain(self):
        with self._lock:
            self._drain_locked()

    def run(self):
        while not self.stop_event.is_set():
            with self._lock:
                self._drain_locked()
            self.stop_event.wait(0.05)


class WebClient:
    """API web como la web: POST /api/session y POST /api/apply por HTTP."""

    def __init__(self, backend, human_key):
        self.backend = backend
        self.human_key = human_key
        self.cookie = None
        self.csrf = None
        # R5/R6: sesion del bridge y instantes (reloj del arnes) del ultimo apply.
        self.last_session = None
        self.last_t_ms = None
        self.last_t_end_ms = None

    def _post(self, path, body, headers=None):
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        base = {
            "Host": "127.0.0.1:%d" % self.backend.port,
            "Content-Type": "application/json",
            "Content-Length": str(len(data)),
        }
        if headers:
            base.update(headers)
        conn = http.client.HTTPConnection("127.0.0.1", self.backend.port, timeout=15)
        try:
            conn.request("POST", path, body=data, headers=base)
            resp = conn.getresponse()
            raw = resp.read()
            status = resp.status
            set_cookie = resp.getheader("Set-Cookie")
        finally:
            conn.close()
        try:
            obj = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            obj = {}
        return status, obj, set_cookie

    def open_session(self):
        status, obj, set_cookie = self._post("/api/session", {"key": self.human_key})
        if status != 200 or not isinstance(obj, dict) or obj.get("ok") is not True:
            raise RuntimeError("no se pudo abrir la sesion humana (http %s)" % status)
        csrf = obj.get("csrf")
        if not isinstance(csrf, str) or not csrf:
            raise RuntimeError("la sesion humana no devolvio csrf")
        if not set_cookie:
            raise RuntimeError("la sesion humana no devolvio cookie")
        self.cookie = set_cookie.split(";")[0].strip()
        self.csrf = csrf

    def apply(self):
        snap = self.backend.store.snapshot()
        body = {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]}
        headers = {
            "Cookie": self.cookie,
            "Origin": "http://127.0.0.1:%d" % self.backend.port,
            "X-CSRF-Token": self.csrf,
        }
        self.last_session = getattr(getattr(self.backend, "bridge", None), "session", None)
        self.last_t_ms = _now_ms()
        try:
            status, obj, _cookie = self._post("/api/apply", body, headers)
        finally:
            self.last_t_end_ms = _now_ms()
        op_id = None
        if status == 200 and isinstance(obj, dict) and obj.get("ok") is True:
            op_id = obj.get("op_id")
        return status, op_id


class LiveRun:
    def __init__(self, args):
        self.args = args
        self.fake_mode = bool(getattr(args, "fake", False))
        self.build = getattr(args, "build", "diag")
        self.evidence = os.path.abspath(getattr(args, "evidence"))
        self.scenarios = _parse_scenarios(getattr(args, "scenarios", ""))
        self.t0_wall = _wall_now()
        self.t0_ms = _now_ms()
        self.aborted = False
        self.setup_ok = True
        self.backend = None
        self.bridge = None
        self.store = None
        self.backend_thread = None
        self.proxy = None
        self.fake = None
        self.tempdir = None
        self.writer = None
        self.secrets = ()
        self.rules_version = 0
        self.pending_setup_events = []
        self.first_scenario_done = False
        self.effects_log = []
        self.logs_final = True
        self.samples_dir = os.path.join(self.evidence, "samples")
        self.logs_dir = os.path.join(self.evidence, "logs")
        self.proxy_log = os.path.join(self.samples_dir, "proxy.jsonl")
        self.rules_path = os.path.join(self.evidence, "rules.json")
        self.active_path = os.path.join(self.evidence, "rules_active.json")

    # --- preparacion ---------------------------------------------------------
    def prepare(self):
        if os.path.exists(self.evidence):
            if not os.path.isdir(self.evidence) or os.listdir(self.evidence):
                print("f1bp_live: la carpeta de evidencia ya existe y no esta vacia", file=sys.stderr)
                return False
        os.makedirs(self.evidence, exist_ok=True)
        os.makedirs(self.samples_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)

        try:
            with open(ROOT / "fixtures" / "catalog-m1.json", "r", encoding="utf-8") as fh:
                catalog = json.load(fh)
        except (OSError, ValueError) as exc:
            print("f1bp_live: no se puede leer el catalogo: %s" % exc, file=sys.stderr)
            return False

        self.tempdir = tempfile.mkdtemp(prefix="dsbx-f1bp-live-")
        self.store = Store(os.path.join(self.tempdir, "scene.json"), catalog)

        peer_key = secrets.token_urlsafe(32)
        human_key = secrets.token_urlsafe(32)
        ai_key = secrets.token_urlsafe(32)
        while human_key == peer_key:
            human_key = secrets.token_urlsafe(32)
        while ai_key in (peer_key, human_key):
            ai_key = secrets.token_urlsafe(32)
        self.secrets = (peer_key, human_key, ai_key)
        global LAST_SECRETS
        LAST_SECRETS = self.secrets

        self.writer = EvidenceWriter(self.samples_dir)
        return True

    def start_backend(self):
        try:
            self.backend = Backend(
                self.store,
                self.secrets[1],
                self.secrets[2],
                port=0,
                log=io.StringIO(),
                clock=time.monotonic,
                bridge_port=0,
                peer_key=self.secrets[0],
                bridge_kwargs={"lease_ms": LEASE_MS, "hold_ms": HOLD_MS, "ttl_ms": TTL_MS},
            )
            self.backend.httpd.handle_error = lambda *a: None
            self.bridge = self.backend.bridge
            self.backend_thread = threading.Thread(
                target=self.backend.serve_forever, daemon=True, name="f1bp-backend"
            )
            self.backend_thread.start()
            return True
        except Exception as exc:
            print("f1bp_live: no arranca el backend: %s" % _redact(exc, self.secrets), file=sys.stderr)
            return False

    def start_proxy(self):
        try:
            _atomic_write_json(self.rules_path, {"version": 0, "rules": []})
            self.proxy = FaultProxy(
                self.bridge.port,
                self.rules_path,
                self.active_path,
                self.proxy_log,
            )
            self.proxy.start()
            deadline = time.monotonic() + 5.0
            while self.proxy.port is None and time.monotonic() < deadline:
                time.sleep(0.01)
            if self.proxy.port is None:
                print("f1bp_live: el proxy no arranca", file=sys.stderr)
                return False
            return True
        except Exception as exc:
            print("f1bp_live: no arranca el proxy: %s" % _redact(exc, self.secrets), file=sys.stderr)
            return False

    def write_manifest(self):
        pbo_sha = None
        pbo = getattr(self.args, "pbo", None)
        if pbo and os.path.isfile(pbo):
            h = hashlib.sha256()
            with open(pbo, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    h.update(chunk)
            pbo_sha = h.hexdigest()
        # R1: procedencia real, desde la raiz del worktree (el padre de DayZSandbox_dev).
        git_head, git_dirty = _git_provenance(ROOT.parent)
        manifest = {
            "build": "fake" if self.fake_mode else self.build,
            "fake": self.fake_mode,
            "git_head": git_head,
            "git_dirty": git_dirty,
            "pbo_sha256": pbo_sha,
            "dayz_version": None,
            "ports": {
                "web": int(self.backend.port),
                "bridge": int(self.bridge.port),
                "proxy": int(self.proxy.port),
            },
            "key_sha256": [_sha256(secret) for secret in self.secrets],
            "lease_ms": LEASE_MS,
            "hold_ms": HOLD_MS,
            "scenarios": list(self.scenarios),
            "t0_ms": float(self.t0_ms),
            "t0_wall": self.t0_wall,
        }
        _atomic_write_json(os.path.join(self.evidence, "manifest.json"), manifest)

    def start_fake(self):
        try:
            # R15: el hello lleva el peer en el cuerpo, como con el mod real; el proxy lo saca de ahi.
            self.fake = FakeMod(
                "http://127.0.0.1:%d" % self.proxy.port,
                self.secrets[0],
                r_retry_unknown=True,
                maintenance_ms=20,
                result_retry_ms=(30, 60, 90),
            )
            original_record = self.fake._record_effect

            def record(order, step):
                try:
                    self.effects_log.append(
                        {
                            "step": step,
                            "session": order.get("session"),
                            "op": order.get("op_id"),
                            "tick_ms": int(round(_now_ms())),
                        }
                    )
                except Exception:
                    pass
                return original_record(order, step)

            self.fake._record_effect = record
            return True
        except Exception as exc:
            print("f1bp_live: no arranca el mod falso: %s" % _redact(exc, self.secrets), file=sys.stderr)
            return False

    def write_peer_configs(self):
        cfg_path = os.path.join(self.tempdir, "backend.json")
        _atomic_write_json(cfg_path, {"peer_key": self.secrets[0], "bridge_port": int(self.proxy.port)})
        for role, profile in (
            ("server", getattr(self.args, "server_profile")),
            ("client", getattr(self.args, "client_profile")),
        ):
            if not profile:
                print("f1bp_live: falta el perfil %s" % role, file=sys.stderr)
                return False
            rc = peer_config.main(["--config", cfg_path, "--profile", profile])
            if rc != 0:
                print("f1bp_live: peer_config fallo para %s" % role, file=sys.stderr)
                return False
            self.pending_setup_events.append(
                (
                    "config",
                    {
                        "peer": role,
                        "qa_step_gap_ms": 0,
                        "key_sha256": _sha256(self.secrets[0]),
                    },
                )
            )
        return True

    def write_ready(self):
        ready = {
            "build": "fake" if self.fake_mode else self.build,
            "web_port": int(self.backend.port),
            "bridge_port": int(self.proxy.port),
            "scenarios": list(self.scenarios),
        }
        _atomic_write_json(os.path.join(self.evidence, "ready.json"), ready)

    def wait_pids(self):
        path = getattr(self.args, "pids_file", None)
        if not path:
            return False
        deadline = time.monotonic() + PIDS_TIMEOUT_S
        while time.monotonic() < deadline:
            if os.path.isfile(path):
                data = _read_json(path)
                if isinstance(data, dict):
                    processes = data.get("processes")
                    if isinstance(processes, (dict, list)) and processes:
                        return True
                elif isinstance(data, list) and data:
                    return True
            time.sleep(0.2)
        print("f1bp_live: no llego pids.json en %d s" % PIDS_TIMEOUT_S, file=sys.stderr)
        return False

    def wait_peers(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with self.bridge.cond:
                    server = self.bridge.peers.get("server")
                    client = self.bridge.peers.get("client")
                    reconciled = self.bridge.reconciled
            except Exception:
                server = client = None
                reconciled = False
            if server and client and reconciled:
                return True
            time.sleep(0.1)
        print("f1bp_live: los dos peers no se presentaron en %d s" % timeout, file=sys.stderr)
        return False

    # --- eventos -------------------------------------------------------------
    def flush_setup_events(self):
        if self.first_scenario_done:
            return
        for ev, fields in self.pending_setup_events:
            self.writer.emit(ev, **fields)
        self.pending_setup_events = []
        self.first_scenario_done = True

    def bridge_photo(self):
        with self.bridge.cond:
            server = self.bridge.peers.get("server")
            client = self.bridge.peers.get("client")
            session = self.bridge.session
            catalog = self.bridge.catalog

        def peer_photo(rec):
            if not rec:
                return None
            return {
                "conn": int(rec.get("conn", 0)),
                "inst": rec.get("inst"),
                "epoch": rec.get("epoch"),
                "lost": bool(rec.get("lost")),
            }

        cat = None
        if catalog is not None:
            cat = {
                "complete": True,
                "n_classes": int(catalog.get("n_classes", 0)),
                "catalog_id": catalog.get("catalog_id"),
            }
        return {
            "session": session,
            "server": peer_photo(server),
            "client": peer_photo(client),
            "catalog": cat,
        }

    def first_hello(self, peer):
        for line in _read_jsonl(self.proxy_log):
            if (
                line.get("route") == "hello"
                and line.get("peer") == peer
                and line.get("upstream_status") == 200
            ):
                return line
        return None

    def wait_op(self, op_id, states, timeout):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            with self.store.lock:
                op = self.backend.ops.get(op_id)
                if op is not None:
                    last = (op.get("state"), op.get("reason"))
            if last is not None and last[0] in states:
                return last
            time.sleep(0.02)
        return last

    def apply_emit(self, web, ttl_ms=None):
        """POST /api/apply y su evento `apply` (R5, R6): sesion del bridge, t_ms justo antes del
        POST y t_end_ms al volver. Devuelve (status, op_id)."""
        status, op_id = web.apply()
        self.writer.emit(
            "apply",
            t_ms=web.last_t_ms,
            t_end_ms=web.last_t_end_ms,
            op_id=op_id,
            http_status=int(status),
            ttl_ms=int(self.bridge.ttl_ms if ttl_ms is None else ttl_ms),
            session=web.last_session,
        )
        return status, op_id

    def apply_case(self, web, name, rule_ids=None):
        status, op_id = self.apply_emit(web)
        self.writer.emit(
            "case", name=name, op_id=op_id, session=web.last_session, **_rule_fields(rule_ids)
        )
        return op_id

    def _server_conn(self):
        """`conn` del servidor si esta presentado y no `lost`; None si no."""
        try:
            with self.bridge.cond:
                rec = self.bridge.peers.get("server")
                if not rec or rec.get("lost"):
                    return None
                return rec.get("conn")
        except Exception:
            return None

    def wait_server_stable(self, timeout, stable_s=1.0):
        """R20: espera a que el servidor este en bridge.peers, no `lost` y con `conn` sin cambiar
        durante `stable_s`. True si lo logra dentro de `timeout`."""
        deadline = time.monotonic() + max(0.0, timeout)
        since = None
        last = None
        while True:
            conn = self._server_conn()
            now = time.monotonic()
            if conn is None:
                since, last = None, None
            elif since is None or conn != last:
                since, last = now, conn
            elif now - since >= stable_s:
                return True
            if now >= deadline:
                return False
            time.sleep(0.05)

    def recovery(self, web):
        """R20: encola la orden de recuperacion con el servidor presentado y estable (hasta 30 s); si
        acaba en fallido/conexion_perdida, reintenta con otra `recovery`. Todo dentro de 60 s."""
        t_end = time.monotonic() + RECOVERY_WINDOW_S
        op_id = None
        while True:
            self.wait_server_stable(min(RECOVERY_STABLE_WAIT_S, max(0.0, t_end - time.monotonic())))
            status, op_id = self.apply_emit(web)
            self.writer.emit("recovery", op_id=op_id, session=web.last_session)
            if not op_id:
                return op_id
            left = t_end - time.monotonic()
            final = self.wait_op(op_id, {"observado", "fallido", "parcial"}, max(0.0, left))
            if final is None or final[0] == "observado":
                return op_id
            if final == ("fallido", "conexion_perdida") and t_end - time.monotonic() > 0:
                continue
            return op_id

    def next_rules_version(self):
        self.rules_version += 1
        return self.rules_version

    def wait_rules_active(self, version, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            doc = _read_json(self.active_path)
            if isinstance(doc, dict) and doc.get("version") == version:
                return True
            time.sleep(0.02)
        return False

    def set_rules(self, version, rules, rule_ids):
        _atomic_write_json(self.rules_path, {"version": version, "rules": rules})
        self.writer.emit("rules", version=version, rule_ids=list(rule_ids))
        if self.wait_rules_active(version, RULES_TIMEOUT_S):
            self.writer.emit("rules_active", version=version)
            return True
        return False

    # --- escenarios ----------------------------------------------------------
    def run_scenario(self, name):
        # Cada escenario es un metodo run_<g>_body; los que faltan se registran como abortados.
        body = getattr(self, "run_%s_body" % name.lower(), None)
        if body is None:
            self.writer.begin(name)
            self.writer.emit("start", scenario=name, wall=_wall_now())
            self.writer.emit("end", status="aborted", reason="no implementado")
            self.writer.end()
            self.aborted = True
            return

        if not self.setup_ok:
            self.writer.begin(name)
            self.writer.emit("start", scenario=name, wall=_wall_now())
            self.writer.emit("end", status="aborted", reason="peers_not_presented")
            self.writer.end()
            self.aborted = True
            return

        self.writer.begin(name)
        # wall y t_ms del start son el ancla del reloj de las lineas del log (brief v1.4, H-04).
        self.writer.emit("start", scenario=name, wall=_wall_now())
        self.flush_setup_events()
        local_aborted = False
        reason = None
        stop_event = threading.Event()
        poller = RingPoller(self.backend, self.writer, stop_event)
        poller.start()
        try:
            # result_seen es un evento comun (EVIDENCIA): el envoltorio de handle_result va en todo
            # escenario, no solo en G4/G8. Es idempotente por bridge y restart_backend lo reengancha.
            self._l2b2_hook(self.bridge)
            local_aborted, reason = body()
        except Exception as exc:
            local_aborted = True
            reason = "exception: " + _redact(exc, self.secrets)
        finally:
            poller.drain()
            stop_event.set()
            poller.join(timeout=1.0)
        self.writer.emit("end", status="aborted" if local_aborted else "ok", reason=reason)
        self.writer.end()
        if local_aborted:
            self.aborted = True

    def run_g1_body(self):
        start = time.monotonic()
        deadline = start + PEERS_TIMEOUT_S
        found = set()
        while time.monotonic() < deadline and len(found) < 2:
            for peer in ("server", "client"):
                if peer in found:
                    continue
                if self.first_hello(peer) is not None:
                    self.writer.emit("connected", peer=peer)
                    found.add(peer)
            if len(found) < 2:
                time.sleep(0.2)
        if len(found) < 2:
            with self.bridge.cond:
                peers = dict(self.bridge.peers)
            for peer in ("server", "client"):
                if peer not in found and peers.get(peer) is not None:
                    self.writer.emit("connected", peer=peer)
                    found.add(peer)

        if self.build == "retail":
            target = start + 120.0
            while time.monotonic() < target:
                time.sleep(min(0.5, max(0.0, target - time.monotonic())))
            connected = False
            try:
                connected = bool(self.bridge.client_in_world())
            except Exception:
                connected = False
            self.writer.emit("client_alive", at_ms=_now_ms(), connected=connected)
        return False, None

    def run_g2_body(self):
        photo = self.bridge_photo()
        self.writer.emit("bridge", **photo)
        if not (photo.get("catalog") and photo["catalog"].get("complete")):
            deadline = time.monotonic() + 120.0
            while time.monotonic() < deadline:
                time.sleep(1.0)
                photo = self.bridge_photo()
                if photo.get("catalog") and photo["catalog"].get("complete"):
                    break
            self.writer.emit("bridge", **photo)
        return False, None

    def run_g3_body(self):
        web = WebClient(self.backend, self.secrets[1])
        web.open_session()

        op_a = self.apply_case(web, "a")
        if op_a:
            self.wait_op(op_a, {"observado"}, OBSERVED_WAIT_S)

        op_b = self.apply_case(web, "b")
        if op_b:
            self.wait_op(op_b, {"observado"}, OBSERVED_WAIT_S)

        rev = int(self.store.snapshot()["rev"])
        new_rev = rev + 7
        version = self.next_rules_version()
        rule = {
            "id": "g3c-rewrite",
            # El peer omite deliver=1 en el poll entregador: el proxy lo deja en
            # null. No se filtra por deliver; resp_has_op ya exige una orden.
            "match": {
                "route": "poll",
                "peer": "server",
                "resp_has_op": True,
                "resp_op_prefix": "op-",  # R19
                "nth": 1,
                "count": 1,
            },
            "action": {"type": "rewrite", "set": {"ops.0.args.rev": new_rev}},
        }
        if not self.set_rules(version, [rule], ["g3c-rewrite"]):
            return True, "rules_not_active"

        op_c = self.apply_case(web, "c", ["g3c-rewrite"])
        if op_c:
            self.wait_op(op_c, {"fallido", "observado", "parcial"}, OBSERVED_WAIT_S)

        # R10: la inyeccion acaba con un `rules` vacio y su `rules_active`; la recuperacion va despues.
        if not self.set_rules(self.next_rules_version(), [], []):
            return True, "rules_not_active"
        self.recovery(web)
        return False, None

    # === L2b2: G4 y G8 ===
    def _l2b2_state(self):
        # Estado propio de este bloque, creado a demanda: __init__ queda fuera de mi write-set.
        if not hasattr(self, "_l2b2_results"):
            self._l2b2_results = []
            self._l2b2_results_lock = threading.Lock()
            self._l2b2_pollers = []
            self._l2b2_restarts = 0

    def _l2b2_hook(self, bridge):
        """Envuelve bridge.handle_result para escribir result_seen y guardarlo en memoria.

        Idempotente por bridge. Se escribe todo cuerpo con op_id, tambien si el bridge lo
        rechaza (un resultado `rejected/stale_session` llega con un 400, y es evidencia).
        """
        self._l2b2_state()
        if getattr(bridge, "_l2b2_hooked", False):
            return
        original = bridge.handle_result

        def wrapped(query, body):
            t_ms = _now_ms()
            try:
                return original(query, body)
            finally:
                try:
                    if isinstance(body, dict) and isinstance(body.get("op_id"), str):
                        item = {
                            "t_ms": t_ms,
                            "op_id": body.get("op_id"),
                            "status": body.get("status"),
                            "reason": body.get("reason"),
                            "dup": body.get("dup") is True,
                        }
                        with self._l2b2_results_lock:
                            self._l2b2_results.append(item)
                        self.writer.emit(
                            "result_seen",
                            t_ms=t_ms,
                            op_id=item["op_id"],
                            status=item["status"],
                            reason=item["reason"],
                            dup=item["dup"],
                        )
                except Exception:
                    pass

        bridge.handle_result = wrapped
        bridge._l2b2_hooked = True

    def _l2b2_results_for(self, op_id, since_ms):
        self._l2b2_state()
        with self._l2b2_results_lock:
            return [r for r in self._l2b2_results if r["op_id"] == op_id and r["t_ms"] >= since_ms]

    def _l2b2_stop_pollers(self):
        self._l2b2_state()
        pollers, self._l2b2_pollers = self._l2b2_pollers, []
        for poller, stop_event in pollers:
            try:
                poller.drain()
            except Exception:
                pass
            stop_event.set()
            try:
                poller.join(timeout=1.0)
            except Exception:
                pass

    def _l2b2_new_web(self):
        web = WebClient(self.backend, self.secrets[1])
        web.open_session()
        return web

    def _l2b2_bump_ops(self, n=100):
        """Adelanta el contador de ops del backend: el op_id de una orden que no debe tener
        `effect` no se reutiliza despues con efecto en otra sesion (el evaluador cuenta por op)."""
        with self.store.lock:
            self.backend._op_n += int(n)

    def _l2b2_clear_rules(self):
        return self.set_rules(self.next_rules_version(), [], [])

    def _l2b2_sleep_until(self, t_ms):
        while True:
            left = t_ms - _now_ms()
            if left <= 0:
                return
            time.sleep(min(0.25, left / 1000.0))

    def _l2b2_apply_ttl(self, web, name, ttl_ms, emit_case=True, rule_ids=None):
        """apply con un TTL propio: se cambia bajo bridge.cond justo antes y se restaura justo
        despues. El evento apply (apply_case) lleva ese ttl_ms."""
        bridge = self.bridge
        with bridge.cond:
            previous = bridge.ttl_ms
            bridge.ttl_ms = int(ttl_ms)
        try:
            if emit_case:
                return self.apply_case(web, name, rule_ids)
            status, op_id = self.apply_emit(web)
            return op_id
        finally:
            with bridge.cond:
                bridge.ttl_ms = previous

    def restart_backend(self, bump_ops=True, before_hello=None):
        """Cierra el backend y crea otro en los mismos puertos (como BR7H1).

        bump_ops: adelanta el contador de ops de la sesion nueva (G8 c lo pone a False: su
        op-1 tiene que ser el primero de la sesion). before_hello: funcion sin argumentos que
        corre con el backend nuevo ya arriba y antes de esperar el hello; devuelve bool.
        Devuelve True si el servidor se presento en la sesion nueva.
        """
        self._l2b2_state()
        old = self.backend
        old_bridge = self.bridge
        old_session = old_bridge.session
        web_port = int(old.port)
        bridge_port = int(old_bridge.port)
        old_ops = int(getattr(old, "_op_n", 0))
        t_start = _now_ms()
        try:
            old.shutdown()
        except Exception:
            pass
        if self.backend_thread is not None:
            try:
                self.backend_thread.join(timeout=10)
            except Exception:
                pass
        with open(ROOT / "fixtures" / "catalog-m1.json", "r", encoding="utf-8") as fh:
            catalog = json.load(fh)
        self._l2b2_restarts += 1
        store = Store(os.path.join(self.tempdir, "scene-r%d.json" % self._l2b2_restarts), catalog)
        backend = None
        deadline = time.monotonic() + 10.0
        while backend is None:
            try:
                backend = Backend(
                    store,
                    self.secrets[1],
                    self.secrets[2],
                    port=web_port,
                    log=io.StringIO(),
                    clock=time.monotonic,
                    bridge_port=bridge_port,
                    peer_key=self.secrets[0],
                    bridge_kwargs={"lease_ms": LEASE_MS, "hold_ms": HOLD_MS, "ttl_ms": TTL_MS},
                )
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        backend.httpd.handle_error = lambda *a: None
        if bump_ops:
            backend._op_n = old_ops + 100
        self.backend = backend
        self.bridge = backend.bridge
        self.store = store
        self.backend_thread = threading.Thread(
            target=backend.serve_forever, daemon=True, name="f1bp-backend"
        )
        self.backend_thread.start()
        self._l2b2_hook(self.bridge)
        stop_event = threading.Event()
        poller = RingPoller(backend, self.writer, stop_event)
        poller.start()
        self._l2b2_pollers.append((poller, stop_event))

        if before_hello is not None and not before_hello():
            return False

        new_session = self.bridge.session
        deadline = time.monotonic() + OBSERVED_WAIT_S
        found = False
        while time.monotonic() < deadline and not found:
            for line in _read_jsonl(self.proxy_log):
                if (
                    line.get("route") == "hello"
                    and line.get("peer") == "server"
                    and line.get("upstream_status") == 200
                    and isinstance(line.get("t_ms"), (int, float))
                    and line["t_ms"] >= t_start
                ):
                    found = True
                    break
            if not found:
                time.sleep(0.1)
        if not found:
            return False
        self.writer.emit("backend_restart", old_session=old_session, new_session=new_session)
        return True

    def _l2b2_write_peer_key(self, profile, key):
        """Escribe dsbx_peer.json del servidor con `key` (peer_config.main) y anota el config."""
        cfg_path = os.path.join(self.tempdir, "backend_l2b2.json")
        _atomic_write_json(cfg_path, {"peer_key": key, "bridge_port": int(self.proxy.port)})
        try:
            rc = peer_config.main(["--config", cfg_path, "--profile", profile])
        finally:
            try:
                os.remove(cfg_path)
            except OSError:
                pass
        if rc != 0:
            return False
        self.writer.emit("config", peer="server", qa_step_gap_ms=0, key_sha256=_sha256(key))
        return True

    def _l2b2_add_manifest_key(self, key):
        path = os.path.join(self.evidence, "manifest.json")
        manifest = _read_json(path)
        if not isinstance(manifest, dict):
            return
        hashes = list(manifest.get("key_sha256") or [])
        digest = _sha256(key)
        if digest not in hashes:
            hashes.append(digest)
        manifest["key_sha256"] = hashes
        _atomic_write_json(path, manifest)

    # --- G4 ---
    def _g4_case_a(self):
        global LAST_SECRETS
        profile = getattr(self.args, "server_profile", None)
        if not profile:
            return "falta el perfil del servidor"
        bad = secrets.token_urlsafe(32)
        self.secrets = self.secrets + (bad,)
        LAST_SECRETS = self.secrets
        self._l2b2_add_manifest_key(bad)
        web = self._l2b2_new_web()
        restored = False
        try:
            if not self._l2b2_write_peer_key(profile, bad):
                return "peer_config fallo con la clave mala"
            # Brief v1.7, H-13: un 4xx llega al mod con el estado 5, y el mod lo mira con
            # DSBX_Const.REST_STATE_4XX y vuelve al hello (con H-07 hacia falta un 500). Un 409 es lo que
            # da el backend a un poll de una sesion que ya no vale (hello_required). El hello relee la
            # clave del dsbx_peer.json.
            # R25: el 409 va con un corte de los polls del servidor en vuelo (abort_inflight), para que
            # el hello ya lleve la clave mala; se espera ver ese hello rechazado (401) antes de abrir
            # la ventana y encolar la orden.
            rule = {
                "id": "g4a_409",
                "abort_inflight": True,
                "match": {"route": "poll", "peer": "server", "count": 1},
                "action": {"type": "status", "code": 409, "error": "forced_hello"},
            }
            t_rules = _now_ms()
            if not self.set_rules(self.next_rules_version(), [rule], ["g4a_409"]):
                return "rules_not_active"
            if not self._g4a_wait_hello_401(t_rules, G4A_HELLO_401_WAIT_S):
                return "g4a: sin hello 401 del servidor con la clave mala"
            t_start = _now_ms()
            op_a = self._l2b2_apply_ttl(web, "a", 2000, emit_case=False)
            session_a = web.last_session
            self._l2b2_sleep_until(t_start + 60000.0)
            t_end = _now_ms()
            self.writer.emit("bad_key_window", t_start_ms=t_start, t_end_ms=t_end)
            # El case va al cierre de la ventana: el evaluador mide la recuperacion desde el
            # evento case y la ventana ya dura 60 s.
            self.writer.emit(
                "case", name="a", op_id=op_a, session=session_a, **_rule_fields(["g4a_409"])
            )
            if not self._l2b2_clear_rules():
                return "rules_not_active"
            if not self._l2b2_write_peer_key(profile, self.secrets[0]):
                return "peer_config fallo al restaurar la clave"
            restored = True
            self.recovery(web)
            return None
        finally:
            if not restored:
                try:
                    self._l2b2_write_peer_key(profile, self.secrets[0])
                except Exception:
                    pass

    def _g4a_wait_hello_401(self, since_ms, timeout):
        """R25: espera, hasta `timeout` s, a una linea de proxy.jsonl con un hello del servidor y
        upstream_status 401 servida desde `since_ms` (reloj del arnes)."""
        deadline = time.monotonic() + timeout
        while True:
            for line in _read_jsonl(self.proxy_log):
                if (
                    line.get("route") == "hello"
                    and line.get("peer") == "server"
                    and line.get("upstream_status") == 401
                ):
                    t = line.get("t_done_ms", line.get("t_ms"))
                    if not isinstance(t, (int, float)) or t >= since_ms:
                        return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def _g4_case_b(self):
        # La orden de la sesion vieja no puede tener `effect` ni en la sesion vieja ni despues:
        # se contiene (los polls se rechazan mientras se encola y se reinicia) y su op_id se
        # aparta del rango que reutilizaran las sesiones siguientes.
        web = self._l2b2_new_web()
        self._l2b2_bump_ops(100)
        hold = {
            "id": "g4b_hold",
            "abort_inflight": True,
            "match": {"route": "poll", "peer": "server"},
            "action": {"type": "refuse"},
        }
        if not self.set_rules(self.next_rules_version(), [hold], ["g4b_hold"]):
            return "rules_not_active"
        op_b = self.apply_case(web, "b", ["g4b_hold", "g4b_stale"])
        if not op_b:
            self._l2b2_clear_rules()
            return "apply fallo en el caso b"
        with self.bridge.cond:
            old_session = self.bridge.session
            order = self.bridge.orders.get((old_session, op_b))
            stale = self.bridge._public_order(order, self.bridge._now_ms()) if order else None
        if stale is None:
            self._l2b2_clear_rules()
            return "la orden del caso b no esta en el bridge"

        def release():
            return self._l2b2_clear_rules()

        if not self.restart_backend(bump_ops=True, before_hello=release):
            return "restart_failed"
        web = self._l2b2_new_web()
        self.recovery(web)

        stale_rule = {
            "id": "g4b_stale",
            # Sin "deliver": el poll que entrega no lleva el parametro y el proxy lo deja en
            # null, asi que deliver=1 no casa nunca; un poll de mantenimiento ignora las ops.
            "match": {"route": "poll", "peer": "server", "count": 1},
            "action": {"type": "rewrite", "set": {"ops": [stale]}},
        }
        t_arm = _now_ms()
        if not self.set_rules(self.next_rules_version(), [stale_rule], ["g4b_stale"]):
            return "rules_not_active"
        self.writer.emit("stale_order", op_id=op_b, old_session=old_session)
        deadline = time.monotonic() + 30.0
        next_rearm = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if self._l2b2_results_for(op_b, t_arm):
                break
            if time.monotonic() >= next_rearm:
                # Un poll de mantenimiento pudo gastar la regla: se rearma (version nueva).
                self.set_rules(self.next_rules_version(), [stale_rule], ["g4b_stale"])
                next_rearm = time.monotonic() + 8.0
            time.sleep(0.05)
        if not self._l2b2_clear_rules():
            return "rules_not_active"
        self.recovery(web)
        return None

    def _g4_case_c(self):
        web = self._l2b2_new_web()
        cut = {
            "id": "g4c_cut",
            "abort_inflight": True,
            "match": {"route": "poll", "peer": "server"},
            "action": {"type": "refuse"},
        }
        if not self.set_rules(self.next_rules_version(), [cut], ["g4c_cut"]):
            return "rules_not_active"
        t_active = _now_ms()
        op_c = self._l2b2_apply_ttl(web, "c", 30000, rule_ids=["g4c_cut"])
        self._l2b2_sleep_until(t_active + 4500.0)
        if not self._l2b2_clear_rules():
            return "rules_not_active"
        if op_c:
            self.wait_op(op_c, {"fallido"}, 30.0)
        self.recovery(web)
        return None

    def run_g4_body(self):
        self._l2b2_state()
        self._l2b2_hook(self.bridge)
        try:
            if self.fake_mode:
                reason = self._g4_case_b()
                if reason:
                    return True, reason
                return True, "fake: G4 (a) y (c) necesitan el motor"
            for case in (self._g4_case_a, self._g4_case_b, self._g4_case_c):
                reason = case()
                if reason:
                    return True, reason
            return False, None
        finally:
            self._l2b2_stop_pollers()

    # --- G8 ---
    def _g8_wait_second_result(self, op_id, since_ms, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self._l2b2_results_for(op_id, since_ms)) >= 2:
                return True
            time.sleep(0.05)
        return False

    def run_g8_body(self):
        self._l2b2_state()
        self._l2b2_hook(self.bridge)
        try:
            web = self._l2b2_new_web()

            # a: drop_resp al primer resultado; el peer lo repite y no cambia nada
            rule = {
                "id": "g8a_drop",
                "match": {"route": "result", "peer": "server", "count": 1},
                "action": {"type": "drop_resp"},
            }
            if not self.set_rules(self.next_rules_version(), [rule], ["g8a_drop"]):
                return True, "rules_not_active"
            t0 = _now_ms()
            op_a = self.apply_case(web, "a", ["g8a_drop"])
            if op_a:
                self.wait_op(op_a, {"observado"}, OBSERVED_WAIT_S)
                if not self._g8_wait_second_result(op_a, t0, 10.0):
                    # R23: sin repeticion del resultado no hay caso; se cierra la inyeccion y se aborta.
                    self._l2b2_clear_rules()
                    return True, "g8a: no se vio la repeticion del resultado"
            if not self._l2b2_clear_rules():
                return True, "rules_not_active"
            self.recovery(web)

            # b: cuatro 503 al resultado; el peer abandona y el backend reentrega (dup:true)
            rule = {
                "id": "g8b_503",
                "match": {"route": "result", "peer": "server", "count": 4},
                "action": {"type": "status", "code": 503, "error": "unavailable"},
            }
            if not self.set_rules(self.next_rules_version(), [rule], ["g8b_503"]):
                return True, "rules_not_active"
            t0 = _now_ms()
            op_b = self.apply_case(web, "b", ["g8b_503"])
            if op_b:
                deadline = time.monotonic() + OBSERVED_WAIT_S
                while time.monotonic() < deadline:
                    if any(r["dup"] for r in self._l2b2_results_for(op_b, t0)):
                        break
                    time.sleep(0.05)
                self.wait_op(op_b, {"observado"}, OBSERVED_WAIT_S)
            if not self._l2b2_clear_rules():
                return True, "rules_not_active"
            self.recovery(web)

            # c: backend reiniciado; el op-1 de la sesion nueva (sin adelantar el contador)
            if not self.restart_backend(bump_ops=False):
                return True, "restart_failed"
            web = self._l2b2_new_web()
            op_c = self.apply_case(web, "c")
            if op_c:
                self.wait_op(op_c, {"observado"}, OBSERVED_WAIT_S)
            self.recovery(web)
            return False, None
        finally:
            self._l2b2_stop_pollers()
    # === fin L2b2 ===

    def confirm_gap_zero(self, profile):
        if not profile:
            return False
        # Solo cuenta la ULTIMA linea `config qa_step_gap_ms=` del script_*.log mas reciente.
        return self._g56_last_gap(profile) == 0

    def run_g9_body(self):
        web = WebClient(self.backend, self.secrets[1])
        web.open_session()

        if self.rules_version > 0:
            version = self.next_rules_version()
            self.set_rules(version, [], [])

        if self.fake_mode:
            confirmed = True
        else:
            confirmed = self.confirm_gap_zero(getattr(self.args, "server_profile", None))
        self.writer.emit("gap_reset", confirmed=bool(confirmed))

        for _ in range(G9_OPS):
            status, op_id = self.apply_emit(web)
            self.writer.emit("mix_op", op_id=op_id, session=web.last_session)
            if op_id:
                self.wait_op(op_id, {"observado"}, G9_WAIT_S)
        return False, None

    # --- cierre --------------------------------------------------------------
    # === L2b3: G5, G6 y G7 ===
    # --- L2b3a: G5 y G6 (ayudantes _g56_*) ---
    @staticmethod
    def _g56_last_gap(profile):
        """Ultimo `config qa_step_gap_ms=<n>` del script_*.log mas reciente del perfil, o None."""
        import re

        if not profile:
            return None
        try:
            logs = [p for p in glob.glob(os.path.join(profile, "script_*.log")) if os.path.isfile(p)]
        except OSError:
            return None
        if not logs:
            return None
        try:
            newest = max(logs, key=lambda p: os.path.getmtime(p))
        except OSError:
            return None
        pattern = re.compile(r"\bconfig qa_step_gap_ms=(\d+)")
        last = None
        try:
            with open(newest, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    found = pattern.search(line)
                    if found:
                        last = int(found.group(1))
        except OSError:
            return None
        return last

    def _g56_mark(self):
        try:
            return os.path.getsize(self.proxy_log)
        except OSError:
            return 0

    def _g56_wait_fire(self, rule_id, mark, timeout_s):
        """Linea de proxy.jsonl con ese rule_id (a partir de `mark`), sondeando cada 5 ms.

        Devuelve la de menor t_ms entre las vistas en una gracia de 40 ms (la del disparo
        empieza antes que cualquiera de su ventana), o None si no aparece.
        """
        deadline = time.monotonic() + timeout_s
        offset = int(mark)
        buf = b""
        found = []
        grace_until = None
        while time.monotonic() < deadline:
            try:
                with open(self.proxy_log, "rb") as fh:
                    fh.seek(offset)
                    chunk = fh.read()
            except OSError:
                chunk = b""
            if chunk:
                buf += chunk
                offset += len(chunk)
                cut = buf.rfind(b"\n")
                if cut >= 0:
                    complete, buf = buf[: cut + 1], buf[cut + 1:]
                    for raw in complete.split(b"\n"):
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            obj = json.loads(raw.decode("utf-8", errors="replace"))
                        except ValueError:
                            continue
                        if isinstance(obj, dict) and obj.get("rule_id") == rule_id:
                            found.append(obj)
            if found and grace_until is None:
                grace_until = time.monotonic() + 0.04
            if grace_until is not None and time.monotonic() >= grace_until:
                break
            time.sleep(0.005)
        if not found:
            return None
        found = [f for f in found if isinstance(f.get("t_done_ms"), (int, float))] or found
        return min(found, key=lambda f: f.get("t_ms") if isinstance(f.get("t_ms"), (int, float)) else 0)

    def _g6_wait_server_poll(self, mark, timeout_s):
        """H-14: espera a que termine un poll del servidor (linea de proxy.jsonl a partir de `mark`).

        El peer manda el siguiente poll en cuanto recibe la respuesta, asi que una orden encolada justo
        despues llega en un poll recien salido. Devuelve el t_done_ms de ese poll, o None si no aparece.
        """
        deadline = time.monotonic() + timeout_s
        offset = int(mark or 0)
        buf = b""
        while time.monotonic() < deadline:
            try:
                with open(self.proxy_log, "rb") as fh:
                    fh.seek(offset)
                    chunk = fh.read()
            except OSError:
                chunk = b""
            if chunk:
                buf += chunk
                offset += len(chunk)
                cut = buf.rfind(b"\n")
                if cut >= 0:
                    complete, buf = buf[: cut + 1], buf[cut + 1:]
                    for raw in complete.split(b"\n"):
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            obj = json.loads(raw.decode("utf-8", errors="replace"))
                        except ValueError:
                            continue
                        if (
                            isinstance(obj, dict)
                            and obj.get("peer") == "server"
                            and obj.get("route") == "poll"
                            and isinstance(obj.get("t_done_ms"), (int, float))
                        ):
                            return obj["t_done_ms"]
            time.sleep(0.005)
        return None

    def _g56_sleep_until(self, t_ms):
        while True:
            left = t_ms - _now_ms()
            if left <= 0:
                return
            time.sleep(min(0.25, left / 1000.0))

    def _g56_clear_rules(self):
        if not self.set_rules(self.next_rules_version(), [], []):
            raise RuntimeError("rules_not_cleared")

    def _g56_apply_case(self, web, name, peer, rule_ids=None):
        status, op_id = self.apply_emit(web)
        self.writer.emit(
            "case", name=name, peer=peer, op_id=op_id, session=web.last_session, **_rule_fields(rule_ids)
        )
        return op_id

    def _g56_set_gap(self, gap):
        """Pone qa_step_gap_ms en dsbx_peer.json del servidor y espera a que el log lo diga."""
        profile = getattr(self.args, "server_profile", None)
        if not profile:
            return False
        path = os.path.join(profile, "dsbx_peer.json")
        with open(path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        if not isinstance(cfg, dict) or not isinstance(cfg.get("key"), str):
            raise RuntimeError("dsbx_peer.json del servidor no es valido")
        cfg["qa_step_gap_ms"] = int(gap)
        data = json.dumps(cfg).encode("utf-8")
        tmp = "%s.tmp.%d" % (path, os.getpid())
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        last_error = None
        for _ in range(50):
            try:
                os.replace(tmp, path)
                last_error = None
                break
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.02)
        if last_error is not None:
            raise RuntimeError("no se pudo reescribir dsbx_peer.json del servidor")
        self.writer.emit(
            "config", peer="server", qa_step_gap_ms=int(gap), key_sha256=_sha256(cfg["key"])
        )
        # Un hello fuerza que el peer relea la configuracion. Brief v1.7, H-13: un 409 llega al mod
        # con el estado 5 (DSBX_Const.REST_STATE_4XX) y lo devuelve al hello. Con H-07 hacia falta
        # un 500, porque el mod miraba EREST_ERROR_CLIENTERROR, que vale 6.
        rule_id = "g56_gap_%d_%d" % (int(gap), self.rules_version + 1)
        rule = {
            "id": rule_id,
            "match": {"route": "poll", "peer": "server", "count": 1},
            "action": {"type": "status", "code": 409, "error": "forced_hello"},
        }
        mark = self._g56_mark()
        if not self.set_rules(self.next_rules_version(), [rule], [rule_id]):
            raise RuntimeError("rules_not_active")
        fired = self._g56_wait_fire(rule_id, mark, 30.0)
        self._g56_clear_rules()
        if fired is None:
            return False
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if self._g56_last_gap(profile) == int(gap):
                return True
            time.sleep(0.2)
        return False

    def _g56_case_a(self, web, peer, ms):
        name = "a%d" % ms
        rule_id = "g5a_%s_%d" % (peer, ms)
        rule = {
            "id": rule_id,
            "match": {"route": "poll", "peer": peer, "count": 1},
            "action": {"type": "then_hold_ms", "ms": ms, "routes": ["hello", "poll"]},
        }
        problem = None
        mark = self._g56_mark()
        try:
            if not self.set_rules(self.next_rules_version(), [rule], [rule_id]):
                raise RuntimeError("rules_not_active")
            self._g56_apply_case(web, name, peer, [rule_id])
            fired = self._g56_wait_fire(rule_id, mark, 30.0)
            if fired is None:
                problem = "%s_%s: regla sin disparar" % (name, peer)
            else:
                t_start = float(fired["t_done_ms"])
                # rule_id: el evaluador empareja ventana y caso por la regla (v1.6, H-12).
                self.writer.emit("window", t_start_ms=t_start, t_end_ms=t_start + ms, rule_id=rule_id)
                self._g56_sleep_until(t_start + ms + 3000.0)
        finally:
            self._g56_clear_rules()
        self.recovery(web)
        return problem

    def _g56_case_b(self, web, gap):
        name = "b%d" % gap
        rule_id = "g5b_cut_%d" % gap
        rule = {
            "id": rule_id,
            "match": {
                "route": "poll", "peer": "server", "resp_has_op": True, "resp_op_prefix": "op-",
                "count": 1,
            },  # R19
            "action": {"type": "then_cut_ms", "ms": 6000, "routes": ["hello", "poll"]},
        }
        if not self._g56_set_gap(gap):
            return "%s: qa_step_gap_ms=%d sin confirmar en el log" % (name, gap)
        problem = None
        mark = self._g56_mark()
        try:
            if not self.set_rules(self.next_rules_version(), [rule], [rule_id]):
                raise RuntimeError("rules_not_active")
            op_id = self._g56_apply_case(web, name, "server", [rule_id])
            fired = self._g56_wait_fire(rule_id, mark, 30.0)
            if fired is None:
                problem = "%s: regla sin disparar" % name
            else:
                t_start = float(fired["t_done_ms"])
                self.writer.emit("window", t_start_ms=t_start, t_end_ms=t_start + 6000.0, rule_id=rule_id)
                if op_id:
                    states = {"observado", "fallido"} if gap == 2500 else {"parcial", "fallido", "observado"}
                    self.wait_op(op_id, states, 60.0)
                self._g56_sleep_until(t_start + 6000.0)
        finally:
            self._g56_clear_rules()
        self.recovery(web)
        return problem

    def run_g5_body(self):
        if self.fake_mode:
            return True, "fake: G5 necesita el motor"
        web = WebClient(self.backend, self.secrets[1])
        web.open_session()
        problems = []
        try:
            for peer in ("server", "client"):
                for ms in (2500, 4500):
                    problem = self._g56_case_a(web, peer, ms)
                    if problem:
                        problems.append(problem)
            for gap in (2500, 4000):
                problem = self._g56_case_b(web, gap)
                if problem:
                    problems.append(problem)
        except RuntimeError as exc:
            problems.append(_redact(exc, self.secrets))
        finally:
            confirmed = False
            try:
                if not self._g56_set_gap(0):
                    problems.append("qa_step_gap_ms=0 sin confirmar al reponerlo")
                confirmed = self.confirm_gap_zero(getattr(self.args, "server_profile", None))
            except Exception as exc:
                problems.append("gap_reset: " + _redact(exc, self.secrets))
            self.writer.emit("gap_reset", confirmed=bool(confirmed))
        return (bool(problems), "; ".join(problems) if problems else None)

    # -- G6: suspension del servidor (solo el PID propio, identidad comprobada) --
    @staticmethod
    def _g56_parse_iso_utc(text):
        """'2026-11-15T10:00:00.1234567Z' (formato 'o' de PowerShell) -> datetime con tz, o None."""
        import datetime
        import re

        if not isinstance(text, str):
            return None
        found = re.fullmatch(
            r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})?",
            text.strip(),
        )
        if not found:
            return None
        year, month, day, hour, minute, second = (int(found.group(i)) for i in range(1, 7))
        frac = (found.group(7) or "0")[:6].ljust(6, "0")
        zone = found.group(8)
        tz = datetime.timezone.utc
        if zone and zone != "Z":
            sign = 1 if zone[0] == "+" else -1
            tz = datetime.timezone(sign * datetime.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6])))
        try:
            return datetime.datetime(year, month, day, hour, minute, second, int(frac), tzinfo=tz)
        except ValueError:
            return None

    @staticmethod
    def _g56_win():
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.CloseHandle.restype = wintypes.BOOL
        k32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        ]
        k32.GetProcessTimes.restype = wintypes.BOOL
        ntdll = ctypes.WinDLL("ntdll")
        ntdll.NtSuspendProcess.argtypes = [wintypes.HANDLE]
        ntdll.NtSuspendProcess.restype = ctypes.c_long
        ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
        ntdll.NtResumeProcess.restype = ctypes.c_long
        return ctypes, wintypes, k32, ntdll

    @staticmethod
    def _g56_creation_time(handle):
        """Instante de creacion (datetime UTC) del proceso de ese handle, o None."""
        import datetime
        from ctypes import byref

        _ctypes, wintypes, k32, _ntdll = LiveRun._g56_win()
        created = wintypes.FILETIME()
        other = [wintypes.FILETIME() for _ in range(3)]
        if not k32.GetProcessTimes(handle, byref(created), byref(other[0]), byref(other[1]), byref(other[2])):
            return None
        ticks = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        epoch = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)
        return epoch + datetime.timedelta(microseconds=ticks // 10)

    @staticmethod
    def _g56_open_if_own(pid, start_time, access, tol_s=2.0):
        """Abre `pid` con `access` y devuelve el handle solo si su creacion casa con `start_time`.

        Si no casa (otro proceso reutilizo el PID), o falta start_time, cierra y devuelve None.
        """
        expected = LiveRun._g56_parse_iso_utc(start_time)
        if expected is None or not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            return None
        _ctypes, _wintypes, k32, _ntdll = LiveRun._g56_win()
        handle = k32.OpenProcess(access, False, pid)
        if not handle:
            return None
        actual = LiveRun._g56_creation_time(handle)
        if actual is not None and abs((actual - expected).total_seconds()) <= tol_s:
            return handle
        k32.CloseHandle(handle)
        return None

    def _g56_server_entry(self):
        path = getattr(self.args, "pids_file", None)
        data = _read_json(path) if path else None
        procs = data.get("processes") if isinstance(data, dict) else data
        if isinstance(procs, dict):
            if "pid" in procs:
                procs = [procs]
            else:
                items = []
                for key, val in procs.items():
                    if isinstance(val, dict):
                        items.append(dict(val, role=val.get("role", key)))
                    elif isinstance(val, int):
                        items.append({"role": key, "pid": val})
                procs = items
        if not isinstance(procs, list):
            return None
        for item in procs:
            if isinstance(item, dict) and item.get("role") == "server":
                return item
        return None

    def _g56_suspend_server(self, hold_ms):
        """Suspende el servidor hold_ms. Devuelve (T_s_ms, T_e_ms, aviso) o (None, None, motivo)."""
        entry = self._g56_server_entry()
        if entry is None:
            return None, None, "sin rol server en pids.json"
        pid = entry.get("pid")
        if pid == os.getpid():
            return None, None, "el PID del servidor es el del arnes"
        access = 0x0800 | 0x1000  # PROCESS_SUSPEND_RESUME | PROCESS_QUERY_LIMITED_INFORMATION
        handle = self._g56_open_if_own(pid, entry.get("start_time"), access)
        if handle is None:
            return None, None, "identidad del servidor no comprobada (PID o start_time no casan)"
        _ctypes, _wintypes, k32, ntdll = self._g56_win()
        t_s = None
        t_e = None
        suspended = False
        problem = None
        try:
            rc = ntdll.NtSuspendProcess(handle)
            if rc != 0:
                return None, None, "NtSuspendProcess devolvio 0x%08x" % (rc & 0xFFFFFFFF)
            suspended = True
            t_s = _now_ms()
            time.sleep(hold_ms / 1000.0)
        finally:
            if suspended:
                for _ in range(5):
                    if ntdll.NtResumeProcess(handle) == 0:
                        break
                    time.sleep(0.05)
                else:
                    problem = "NtResumeProcess fallo"
                t_e = _now_ms()
            k32.CloseHandle(handle)
        return t_s, t_e, problem

    def run_g6_body(self):
        if self.fake_mode:
            return True, "fake: G6 necesita el motor"
        web = WebClient(self.backend, self.secrets[1])
        web.open_session()
        clock_s = float(getattr(self.args, "g6_clock_s", 600.0))
        t_start = _now_ms()
        time.sleep(max(0.0, clock_s))
        self.writer.emit("clock_run", t_start_ms=t_start, t_end_ms=_now_ms())

        rule_id = "g6_deliver"
        # Una regla de respuesta `pass` deja su rule_id en proxy.jsonl (fault_proxy.py, _forward_and_serve).
        rule = {
            "id": rule_id,
            "match": {
                "route": "poll", "peer": "server", "resp_has_op": True, "resp_op_prefix": "op-",
                "count": 1,
            },  # R19
            "action": {"type": "pass"},
        }
        problems = []
        original_ttl = self.bridge.ttl_ms
        # result_seen lo escribe el envoltorio comun (_l2b2_hook), que run_scenario instala en todo
        # escenario; un segundo envoltorio aqui duplicaria los eventos (integracion de L2b2 y L2b3a).
        self._l2b2_hook(self.bridge)
        op_id = None
        try:
            mark = self._g56_mark()
            if not self.set_rules(self.next_rules_version(), [rule], [rule_id]):
                raise RuntimeError("rules_not_active")
            # H-14: el plazo local del peer cuenta desde que envio el poll (P-02). Si el long-poll del
            # servidor lleva retenido mas de ~1,4 s, una orden de 1500 ms llega ya vencida (rejected/expired)
            # y G6 no prueba la pausa. Se encola justo al terminar un poll del servidor.
            self._g6_wait_server_poll(self._g56_mark(), G6_POLL_ALIGN_S)
            with self.bridge.cond:
                self.bridge.ttl_ms = 1500
            try:
                t_apply = _now_ms()
                status, op_id = self.apply_emit(web, ttl_ms=1500)
                t_after = _now_ms()
            finally:
                with self.bridge.cond:
                    self.bridge.ttl_ms = original_ttl
            self.writer.emit(
                "case", name="pause", peer="server", op_id=op_id, session=web.last_session,
                **_rule_fields([rule_id])
            )
            fired = self._g56_wait_fire(rule_id, mark, 20.0)
            if fired is None or not op_id:
                problems.append("g6: orden sin entregar (regla sin disparar)")
            else:
                t_d = float(fired["t_done_ms"])
                t_s, t_e, why = self._g56_suspend_server(2000)
                if t_s is None:
                    problems.append("g6: sin suspension: %s" % why)
                else:
                    if why:
                        problems.append("g6: " + why)
                    deadline_ms = self._g56_deadline(op_id, t_apply, t_after, 1500)
                    self.writer.emit(
                        "pause_order",
                        op_id=op_id,
                        T_d_ms=t_d,
                        T_s_ms=float(t_s),
                        T_e_ms=float(t_e),
                        D_ms=float(deadline_ms),
                        rule_id=rule_id,
                        session=web.last_session,
                    )
                    self.wait_op(op_id, {"observado", "fallido", "parcial"}, 30.0)
                    self._g56_wait_result_seen(op_id, 30.0)
        finally:
            with self.bridge.cond:
                self.bridge.ttl_ms = original_ttl
            try:
                self._g56_clear_rules()
            except RuntimeError as exc:
                problems.append(str(exc))
        self.recovery(web)
        return (bool(problems), "; ".join(problems) if problems else None)

    def _g56_deadline(self, op_id, t_apply, t_after, ttl_ms):
        """D = emision + TTL en el reloj del arnes (time.monotonic()*1000).

        Se usa issued_ms del bridge solo si su reloj es time.monotonic (el mismo del arnes) y la
        emision cae entre el inicio y el fin del apply; si no, el instante del apply mas el TTL.
        """
        try:
            with self.bridge.cond:
                order = self.bridge.orders.get((self.bridge.session, op_id))
                issued = order.get("issued_ms") if order else None
                order_ttl = order.get("ttl_ms") if order else None
                t0 = float(self.bridge._t0)
                same_clock = self.bridge.clock is time.monotonic
            if same_clock and isinstance(issued, int) and order_ttl == ttl_ms:
                emitted = t0 * 1000.0 + issued
                if t_apply - 2.0 <= emitted <= t_after + 2.0:
                    return emitted + ttl_ms
        except Exception:
            pass
        return t_apply + ttl_ms

    def _g56_wait_result_seen(self, op_id, timeout_s):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            with self.bridge.cond:
                order = self.bridge.orders.get((self.bridge.session, op_id))
                seen = bool(order and order.get("result_seen"))
            if seen:
                return True
            time.sleep(0.05)
        return False
    # === fin L2b3 ===

    # === L2b3b: G7 ===
    def _g7_scale(self, seconds):
        # Con el mod falso solo importa la estructura: las esperas se acortan.
        return min(seconds, 0.2) if self.fake_mode else seconds

    def _g7_rule(self, rule_id, route, action, peer="server", count=1, **extra):
        match = {"route": route, "peer": peer}
        if count is not None:
            match["count"] = count
        match.update(extra)
        return {"id": rule_id, "match": match, "action": action}

    def _g7_wait_fired(self, rule_id, timeout):
        # Disparo = linea de proxy.jsonl con ese rule_id; se sondea cada 5 ms.
        deadline = time.monotonic() + timeout
        while True:
            for line in _read_jsonl(self.proxy_log):
                if line.get("rule_id") == rule_id:
                    return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)

    def _g7_apply(self, web):
        status, op_id = self.apply_emit(web)
        return op_id

    def _g7_case(self, web, name, rule, after_fire=3.0, apply=False, op_states=None, hold_s=None):
        # Devuelve False si las reglas no se confirmaron (el escenario acaba aborted).
        rule_id = rule["id"]
        if not self.set_rules(self.next_rules_version(), [rule], [rule_id]):
            return False
        self.writer.emit("case", name=name, rule_id=rule_id)
        fire_timeout = self._g7_scale(30.0)
        op_id = self._g7_apply(web) if apply else None
        if hold_s is not None:
            # Caso de duracion fija (invalid_all_P): sin esperar disparo.
            time.sleep(self._g7_scale(hold_s))
        elif op_states is not None:
            if op_id:
                self.wait_op(op_id, op_states, self._g7_scale(OBSERVED_WAIT_S))
        else:
            self._g7_wait_fired(rule_id, fire_timeout)
            time.sleep(self._g7_scale(after_fire))
        # R10: fin de la inyeccion (rules vacio + rules_active) antes de la recuperacion.
        if not self.set_rules(self.next_rules_version(), [], []):
            return False
        self.recovery(web)
        return True

    def run_g7_body(self):
        web = WebClient(self.backend, self.secrets[1])
        web.open_session()
        final_states = {"observado", "fallido", "parcial"}

        for code in (400, 401, 409, 413, 500):
            act = {"type": "status", "code": code, "error": "fault"}
            rule = self._g7_rule("g7-status%d-P" % code, "poll", act)
            if not self._g7_case(web, "status%d_P" % code, rule):
                return True, "rules_not_active"
        for code in (400, 401, 409, 413, 500):
            act = {"type": "status", "code": code, "error": "fault"}
            rule = self._g7_rule("g7-status%d-R" % code, "result", act)
            if not self._g7_case(
                web, "status%d_R" % code, rule, apply=True, op_states=final_states
            ):
                return True, "rules_not_active"

        rule = self._g7_rule("g7-timeout-P", "poll", {"type": "hold_resp_ms", "ms": 5000})
        if not self._g7_case(web, "timeout_P", rule, after_fire=8.0):
            return True, "rules_not_active"

        rule = self._g7_rule("g7-r-held", "result", {"type": "hold_resp_ms", "ms": 4000})
        if not self._g7_case(
            web, "r_held", rule, apply=True, op_states={"observado"}
        ):
            return True, "rules_not_active"

        # Brief v1.5, H-08: una orden sin args no es una respuesta no valida. El poll sigue siendo
        # valido y el verbo la rechaza (rejected/bad_args, sin effect); por eso es una medida.
        invalid = (
            ("invalid_no_ok_P", {"ok": {"$delete": True}}, {}, False),
            ("invalid_ok_false_P", {"ok": False}, {}, False),
            ("invalid_now_decimal_P", {"now_ms": 1234.5}, {}, False),
            ("invalid_now_text_P", {"now_ms": "1234"}, {}, False),
            (
                "measure_no_args_P",
                {"ops.0.args": {"$delete": True}},
                {"resp_has_op": True, "resp_op_prefix": "op-"},  # R19
                True,
            ),
        )
        for name, setv, extra, apply in invalid:
            rule = self._g7_rule(
                "g7-" + name.replace("_", "-"),
                "poll",
                {"type": "rewrite", "set": setv},
                **extra,
            )
            if apply:
                ok = self._g7_case_apply_p(web, name, rule)
            else:
                ok = self._g7_case(web, name, rule, after_fire=3.0)
            if not ok:
                return True, "rules_not_active"

        # Todas las respuestas de P no validas durante mas que lease_ms (peer: lease lost).
        rule = self._g7_rule(
            "g7-invalid-all-P",
            "poll",
            {"type": "rewrite", "set": {"ok": False}},
            count=None,
        )
        if not self._g7_case(web, "invalid_all_P", rule, hold_s=4.5):
            return True, "rules_not_active"

        rule = self._g7_rule("g7-measure-ok1-P", "poll", {"type": "rewrite", "set": {"ok": 1}})
        if not self._g7_case(web, "measure_ok1_P", rule):
            return True, "rules_not_active"
        rule = self._g7_rule(
            "g7-measure-args-empty-P",
            "poll",
            {"type": "rewrite", "set": {"ops.0.args": {}}},
            resp_has_op=True,
            resp_op_prefix="op-",  # R19
        )
        if not self._g7_case_apply_p(web, "measure_args_empty_P", rule):
            return True, "rules_not_active"

        rule = self._g7_rule("g7-late-cb", "poll", {"type": "hold_resp_ms", "ms": 8000})
        if not self._g7_case(web, "late_cb", rule, after_fire=12.0):
            return True, "rules_not_active"
        return False, None

    def _g7_case_apply_p(self, web, name, rule):
        # Regla sobre un poll con orden (resp_has_op): hace falta un apply; se espera el disparo
        # y 3 s mas.
        rule_id = rule["id"]
        if not self.set_rules(self.next_rules_version(), [rule], [rule_id]):
            return False
        self.writer.emit("case", name=name, rule_id=rule_id)
        self._g7_apply(web)
        self._g7_wait_fired(rule_id, self._g7_scale(30.0))
        time.sleep(self._g7_scale(3.0))
        if not self.set_rules(self.next_rules_version(), [], []):
            return False
        self.recovery(web)
        return True
    # === fin L2b3b ===

    def write_scenarios_done(self):
        obj = {
            "scenarios": list(self.scenarios),
            "status": "aborted" if self.aborted else "ok",
            "t_ms": _now_ms(),
        }
        _atomic_write_json(os.path.join(self.evidence, "scenarios_done.json"), obj)

    def wait_logs_ready(self, timeout):
        path = os.path.join(self.evidence, "logs_ready.json")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if os.path.isfile(path):
                doc = _read_json(path)
                if doc is not None:
                    return doc
            time.sleep(0.5)
        print("f1bp_live: no llego logs_ready.json en %d s" % timeout, file=sys.stderr)
        return None

    def stop_fake(self):
        if self.fake is not None:
            try:
                self.fake.close()
            except Exception:
                pass
            self.fake = None

    def write_fake_logs(self):
        os.makedirs(self.logs_dir, exist_ok=True)
        lines = []
        for eff in self.effects_log:
            lines.append(
                "[DSBX] effect step=%s session=%s op=%s tick_ms=%d"
                % (eff["step"], eff["session"], eff["op"], int(eff["tick_ms"]))
            )
        server_log = os.path.join(self.logs_dir, "server_script.log")
        with open(server_log, "w", encoding="utf-8", newline="\n") as fh:
            if lines:
                fh.write("\n".join(lines) + "\n")
        client_log = os.path.join(self.logs_dir, "client_script.log")
        with open(client_log, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("")
        # R3: con --fake el orquestador escribe el inventario; el "perfil" es la propia carpeta logs/.
        inventory = {
            "server": {"dir": os.path.abspath(self.logs_dir), "files": ["server_script.log"]},
            "client": {"dir": os.path.abspath(self.logs_dir), "files": ["client_script.log"]},
            "copies": [
                {"peer": "server", "src": "server_script.log", "dest": "server_script.log"},
                {"peer": "client", "src": "client_script.log", "dest": "client_script.log"},
            ],
        }
        _atomic_write_json(os.path.join(self.logs_dir, "inventory.json"), inventory)

    def _inventory_paths(self):
        """Rutas absolutas de cada fichero del inventario de R3 (`dir` + nombre)."""
        inv = _read_json(os.path.join(self.logs_dir, "inventory.json"))
        paths = []
        if not isinstance(inv, dict):
            return paths
        for role, fallback in (
            ("server", getattr(self.args, "server_profile", None)),
            ("client", getattr(self.args, "client_profile", None)),
        ):
            entry = inv.get(role)
            if isinstance(entry, dict):
                base, names = entry.get("dir"), entry.get("files")
            else:
                # Formato antiguo (lista de nombres): el perfil de los argumentos.
                base, names = fallback, entry
            if not isinstance(base, str) or not isinstance(names, list):
                continue
            for name in names:
                if isinstance(name, str) and name:
                    paths.append(os.path.abspath(os.path.join(base, name)))
        return paths

    def key_scan(self):
        """Busca todas las claves en cada fichero del inventario y en las copias de logs/ (R4).

        Devuelve el numero de apariciones. `files` son los ficheros leidos (rutas absolutas); los que
        no se pudieron leer van aparte en `unreadable` y NO cuentan como cubiertos.
        """
        if not self.scenarios:
            return 0
        candidates = self._inventory_paths()
        try:
            names = sorted(os.listdir(self.logs_dir))
        except OSError:
            names = []
        for name in names:
            path = os.path.join(self.logs_dir, name)
            if os.path.isfile(path):
                candidates.append(os.path.abspath(path))
        needles = [secret.encode("utf-8") for secret in self.secrets if secret]
        files = []
        unreadable = []
        seen = set()
        hits = 0
        for path in candidates:
            key = os.path.normcase(path)
            if key in seen:
                continue
            seen.add(key)
            count = _count_in_file(path, needles)
            if count is None:
                unreadable.append(path)
                continue
            files.append(path)
            hits += count
        target = "G4" if "G4" in self.scenarios else self.scenarios[-1]
        self.writer.append(target, "key_scan", files=files, hits=hits, unreadable=unreadable)
        if hits:
            print("f1bp_live: %d apariciones de clave en los logs: clave en los logs" % hits, file=sys.stderr)
        if unreadable:
            print("f1bp_live: AVISO: %d ficheros sin poder leer en key_scan" % len(unreadable), file=sys.stderr)
        return hits

    def final_code(self, hits):
        """Codigo de salida: claves en los logs -> 1 (R4); escenarios abortados o logs no finales -> 2 (R2)."""
        if hits:
            return 1
        if self.aborted or not self.logs_final:
            return 2
        return 0

    def cleanup(self):
        self.stop_fake()
        if self.proxy is not None:
            try:
                self.proxy.stop()
            except Exception:
                pass
            self.proxy = None
        if self.backend is not None:
            try:
                self.backend.shutdown()
            except Exception:
                pass
            if self.backend_thread is not None:
                try:
                    self.backend_thread.join(timeout=10)
                except Exception:
                    pass
            self.backend = None
        if self.tempdir:
            shutil.rmtree(self.tempdir, ignore_errors=True)
            self.tempdir = None
        if self.writer is not None:
            self.writer.end()

    def execute(self):
        try:
            if not self.prepare():
                return 2
            if not self.start_backend():
                return 2
            if not self.start_proxy():
                return 2
            self.write_manifest()

            if self.fake_mode:
                if not self.start_fake():
                    self.setup_ok = False
            else:
                if not self.write_peer_configs():
                    self.setup_ok = False
                else:
                    self.write_ready()
                self.wait_pids()

            if not self.wait_peers(PEERS_TIMEOUT_S):
                self.setup_ok = False

            for name in self.scenarios:
                self.run_scenario(name)

            self.write_scenarios_done()

            if self.fake_mode:
                self.stop_fake()
                self.write_fake_logs()
            else:
                # R2: sin logs_ready.json con all_closed true, los logs no son finales: se sigue
                # escribiendo lo demas, pero el orquestador sale con 2.
                doc = self.wait_logs_ready(LOGS_READY_TIMEOUT_S)
                self.logs_final = isinstance(doc, dict) and doc.get("all_closed") is True
                if not self.logs_final:
                    print("f1bp_live: logs no finales (all_closed no es true)", file=sys.stderr)

            hits = self.key_scan()
            return self.final_code(hits)
        finally:
            self.cleanup()


def run(args):
    live = LiveRun(args)
    try:
        return live.execute()
    except Exception as exc:
        print("f1bp_live: error: %s" % _redact(exc, live.secrets), file=sys.stderr)
        try:
            live.cleanup()
        except Exception:
            pass
        return 2


def build_parser():
    parser = argparse.ArgumentParser(description="Orquestador del arnes F1b-peers en partida.")
    sub = parser.add_subparsers(dest="cmd")
    run_parser = sub.add_parser("run", help="corre los escenarios de la partida")
    run_parser.add_argument("--build", choices=("diag", "retail"), required=True)
    run_parser.add_argument("--evidence", required=True)
    run_parser.add_argument("--server-profile", required=True)
    run_parser.add_argument("--client-profile", required=True)
    run_parser.add_argument("--pids-file", required=True)
    run_parser.add_argument("--scenarios", required=True)
    run_parser.add_argument("--pbo", default=None)
    run_parser.add_argument("--fake", action="store_true")
    run_parser.add_argument("--g6-clock-s", type=float, default=600.0)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return run(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
