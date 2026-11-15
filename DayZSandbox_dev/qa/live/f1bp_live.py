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
from app.tests import fake_mod as fake_mod_module  # noqa: E402
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


class EvidenceWriter:
    """Escribe samples/<G>.jsonl con una linea por evento, UTF-8 y LF."""

    def __init__(self, samples_dir):
        self.samples_dir = samples_dir
        self._lock = threading.RLock()
        self._fh = None
        self.scenario = None

    def begin(self, scenario):
        with self._lock:
            self.end()
            self.scenario = scenario
            path = os.path.join(self.samples_dir, scenario + ".jsonl")
            self._fh = open(path, "w", encoding="utf-8", newline="\n")

    def emit(self, ev, t_ms=None, **fields):
        with self._lock:
            if self._fh is None:
                return
            obj = {"t_ms": float(t_ms) if t_ms is not None else _now_ms(), "ev": ev}
            obj.update(fields)
            line = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            self._fh.write(line + "\n")
            self._fh.flush()

    def end(self):
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.flush()
                finally:
                    self._fh.close()
                self._fh = None
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
            self.writer.emit(
                "op_state",
                op_id=item.get("op_id"),
                state=item.get("state"),
                reason=item.get("reason"),
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
        status, obj, _cookie = self._post("/api/apply", body, headers)
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
        self._peer_http_patched = False
        self._original_peer_http = None
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
        manifest = {
            "build": "fake" if self.fake_mode else self.build,
            "fake": self.fake_mode,
            "git_head": None,
            "git_dirty": False,
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
            # El hello lleva el peer en el cuerpo, no en la query; el proxy solo
            # puede registrar el peer si va en la query. El parche va en la clase
            # antes de construir el falso, porque sus peers saludan al arrancar.
            if not self._peer_http_patched:
                self._original_peer_http = fake_mod_module._Peer._http

                def http_with_peer(peer_self, method, path, body=None, route=None):
                    if route == "hello":
                        sep = "&" if "?" in path else "?"
                        path = path + sep + "peer=" + peer_self.role
                    return self._original_peer_http(peer_self, method, path, body, route=route)

                fake_mod_module._Peer._http = http_with_peer
                self._peer_http_patched = True

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

    def apply_case(self, web, name):
        status, op_id = web.apply()
        self.writer.emit(
            "apply",
            op_id=op_id,
            http_status=int(status),
            ttl_ms=int(self.bridge.ttl_ms),
        )
        self.writer.emit("case", name=name, op_id=op_id)
        return op_id

    def recovery(self, web):
        status, op_id = web.apply()
        self.writer.emit(
            "apply",
            op_id=op_id,
            http_status=int(status),
            ttl_ms=int(self.bridge.ttl_ms),
        )
        self.writer.emit("recovery", op_id=op_id)
        if op_id:
            self.wait_op(op_id, {"observado"}, OBSERVED_WAIT_S)
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
                "nth": 1,
                "count": 1,
            },
            "action": {"type": "rewrite", "set": {"ops.0.args.rev": new_rev}},
        }
        if not self.set_rules(version, [rule], ["g3c-rewrite"]):
            return True, "rules_not_active"

        op_c = self.apply_case(web, "c")
        if op_c:
            self.wait_op(op_c, {"fallido", "observado", "parcial"}, OBSERVED_WAIT_S)

        self.recovery(web)
        return False, None

    # === L2b2: G4 y G8 ===
    # === fin L2b2 ===

    def confirm_gap_zero(self, profile):
        if not profile:
            return False
        logs = glob.glob(os.path.join(profile, "script_*.log"))
        for path in logs:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if "config qa_step_gap_ms=0" in line:
                            return True
            except OSError:
                continue
        return False

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
            status, op_id = web.apply()
            self.writer.emit(
                "apply",
                op_id=op_id,
                http_status=int(status),
                ttl_ms=int(self.bridge.ttl_ms),
            )
            self.writer.emit("mix_op", op_id=op_id)
            if op_id:
                self.wait_op(op_id, {"observado"}, G9_WAIT_S)
        return False, None

    # --- cierre --------------------------------------------------------------
    # === L2b3: G5, G6 y G7 ===
    # === fin L2b3 ===

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
                return True
            time.sleep(0.5)
        print("f1bp_live: no llego logs_ready.json en %d s" % timeout, file=sys.stderr)
        return False

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
        inventory = {
            "server": ["server_script.log"],
            "client": ["client_script.log"],
        }
        _atomic_write_json(os.path.join(self.logs_dir, "inventory.json"), inventory)

    def key_scan(self):
        if not self.scenarios:
            return 0
        files = []
        hits = 0
        try:
            names = sorted(os.listdir(self.logs_dir))
        except OSError:
            names = []
        for name in names:
            path = os.path.join(self.logs_dir, name)
            if not os.path.isfile(path):
                continue
            files.append(path)
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            for secret in self.secrets:
                hits += data.count(secret.encode("utf-8"))
        self.writer.append(self.scenarios[-1], "key_scan", files=files, hits=hits)
        if hits:
            print("f1bp_live: AVISO: %d apariciones de clave en los logs copiados" % hits, file=sys.stderr)
        return hits

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
        if self._peer_http_patched:
            fake_mod_module._Peer._http = self._original_peer_http
            self._peer_http_patched = False

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
                self.wait_logs_ready(LOGS_READY_TIMEOUT_S)

            self.key_scan()
            return 2 if self.aborted else 0
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
