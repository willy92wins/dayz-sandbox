#!/usr/bin/env python3
"""Orquestador de la partida F2P (P1..P5) y de sus modos seco/humo/almacen.

El veredicto lo da solo el gate (R-02):
  m1_gate.py spike F2P --build <b> --evidence <BASE> --evaluate-only
      --oracle-commit 75ecb097eb28467367ba1e20014eb09c3c491950
Este runner nunca escribe oracle_check.json ni importa el oraculo (R-01).
El backend corre como subproceso con su CLI (Q5/R-64); el tap va en este
proceso (R-15). Sin DayZ en el modo seco (R-63): backend real, tap, mod
falso como subproceso y sonda con los peers falsos de PartContext.
P2n: sin estimulo comprobado no se manda su apply (Q3/R-39) y F2P-03
queda INCONCLUSO stimulus_not_observed. P2: el tap puede contestar el
primer acuse (Q2/R-38), visible como upstream_status nulo.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import importlib.util
import json
import math
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent.parent
DEV_ROOT = QA_DIR.parent
REPO_ROOT = DEV_ROOT.parent
if str(QA_DIR) not in sys.path:
    sys.path.insert(0, str(QA_DIR))

import gate_core  # noqa: E402
import wire  # noqa: E402
import f03_common  # noqa: E402


def _load_tap_module():
    path = Path(__file__).resolve().with_name("f2p_tap.py")
    spec = importlib.util.spec_from_file_location("f2p_tap_live", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_TAP = _load_tap_module()
Tap = _TAP.Tap

ORACLE_COMMIT = "75ecb097eb28467367ba1e20014eb09c3c491950"
ORACLE_SHA256 = {
    "f2p_eval.py": "8c6edb105de18c33916fb5aee93139ab4c9a7cd4b9a4c8bf4e6846fa21699128",
    "f2p_mutants.py": "c6e202f0c26d629be93d1980b69b420c270a824779ca571d0422419e62adf106",
}
PART_ORDER = ("P1", "P2", "P2n", "P3", "P3c", "P4a", "P4b", "P4c", "P5")
CENTER = (6170.0, 7643.0)
MAIN_RADIUS = 115.0
WITNESS_RADIUS = 120.0
CONTROL_POS = (4860.0, 10200.0)
DOC1_ID = "d-7c19e2a5"
DOC2_ID = "d-2f2a5c01"
FORBIDDEN_REASONS = (
    "corrupt_manifest", "empty_or_corrupt_samples", "manifest_incomplete",
    "oracle_modified", "oracle_unverified", "pbo_mismatch", "build_mismatch",
    "wire_cap_exceeded", "tap_trace_mismatch", "tap_req_id_missing",
)

_SCENE_DEL_RE = re.compile(
    r"\[DSBX\]\s+DSBX_SCENE_DEL\s+(?:tick_ms=-?[0-9.]+\s+)?"
    r"frame=(?P<frame>-?\d+)\s+lid=(?P<lid>\S+)\s+"
    r"(?:net_low=(?P<net_low>-?\d+)\s+net_high=(?P<net_high>-?\d+)"
    r"|net=(?P<net_high2>-?\d+):(?P<net_low2>-?\d+))\s+"
    r"signal_ref(?:_b)?=(?P<signal_ref_b>[01])\s+"
    r"signal_pending(?:_b)?=(?P<signal_pending_b>[01])\s+"
    r"signal_by_netid(?:_b)?=(?P<signal_by_netid_b>[01])\s+"
    r"deleted_confirmed(?:_b)?=(?P<deleted_confirmed_b>[01])\s+"
    r"delete_failed(?:_b)?=(?P<delete_failed_b>[01])\s+"
    r"confirm_tick_ms=(?P<confirm_tick_ms>-?[0-9.]+)"
)
_WALL_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\b")


def wall_to_seconds(text):
    m = _WALL_RE.match(str(text).strip())
    if not m:
        return None
    h, mi, s, ms = (int(m.group(i)) for i in range(1, 5))
    return h * 3600.0 + mi * 60.0 + s + ms / 1000.0


def parse_scene_del_lines(lines, anchor_t_ms, anchor_wall_s):
    """Lineas DSBX_SCENE_DEL -> filas scene_del con t_ms en el reloj comun (R-12).

    El ancla (t_ms, pared) se toma en el mismo instante; el cruce de
    medianoche se resuelve sumando un dia si la linea queda muy por detras.
    """
    rows = []
    for line in lines:
        m = _SCENE_DEL_RE.search(line)
        if not m:
            continue
        wall = wall_to_seconds(line)
        if wall is None:
            continue
        delta_s = wall - float(anchor_wall_s)
        if delta_s < -43200.0:
            delta_s += 86400.0
        elif delta_s > 43200.0:
            delta_s -= 86400.0
        rows.append({
            "t_ms": float(anchor_t_ms) + delta_s * 1000.0,
            "frame": int(m.group("frame")),
            "lid": m.group("lid"),
            "net_low": int(m.group("net_low") or m.group("net_low2")),
            "net_high": int(m.group("net_high") or m.group("net_high2")),
            "signal_ref_b": int(m.group("signal_ref_b")),
            "signal_pending_b": int(m.group("signal_pending_b")),
            "signal_by_netid_b": int(m.group("signal_by_netid_b")),
            "deleted_confirmed_b": int(m.group("deleted_confirmed_b")),
            "delete_failed_b": int(m.group("delete_failed_b")),
            "confirm_tick_ms": float(m.group("confirm_tick_ms")),
        })
    rows.sort(key=lambda r: r["t_ms"])
    return rows


def _local_wall_seconds(t=None):
    """Segundos desde la medianoche LOCAL del instante `t` (por defecto, ahora).

    Las lineas del script log de DayZ llevan la hora local; con `time.time() % 86400` (UTC) el ancla de R-12
    desplazaba scene_del una hora en el portatil (6.a partida de T4: todas las filas fuera de las partes).
    """
    if t is None:
        t = time.time()
    lt = time.localtime(t)
    return lt.tm_hour * 3600.0 + lt.tm_min * 60.0 + lt.tm_sec + (float(t) % 1.0)


def collect_scene_del(log_paths, anchor_t_ms, anchor_wall_s):
    rows = []
    for path in log_paths:
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rows.extend(parse_scene_del_lines(text.splitlines(), anchor_t_ms, anchor_wall_s))
    rows.sort(key=lambda r: r["t_ms"])
    return rows


def scene_del_log_paths(server_profile):
    """script_*.log del perfil del servidor, ordenados (cada reinicio
    escribe un log nuevo en el mismo perfil)."""
    if not server_profile:
        return []
    try:
        return sorted(Path(server_profile).glob("script_*.log"))
    except OSError:
        return []


def collect_scene_del_from_profile(server_profile, anchor_t_ms, anchor_wall_s):
    """Modo real (diag/retail): DSBX_SCENE_DEL de los script_*.log del
    perfil del servidor, con el ancla de R-12 (t_ms y hora de pared
    tomadas en el mismo instante por quien llama)."""
    return collect_scene_del(scene_del_log_paths(server_profile),
                             anchor_t_ms, anchor_wall_s)


def build_f2p_block(*, oracle_commit, oracle_files, storage_path, storage_id,
                    parts, witness_follow_ticks=3, p2n_variant="create_failed_after"):
    """Bloque f2p del manifest (R-07). parts: lista de (name, start, end)."""
    if oracle_commit != ORACLE_COMMIT:
        raise ValueError("oracle_commit distinto del congelado")
    part_rows = []
    prev_end = None
    names = [p[0] for p in parts]
    if names != list(PART_ORDER):
        raise ValueError("las partes no estan en el orden normativo")
    for name, start, end in parts:
        start = float(start); end = float(end)
        if not (math.isfinite(start) and math.isfinite(end) and start < end):
            raise ValueError("ventana de parte invalida")
        if prev_end is not None and start < prev_end:
            raise ValueError("ventanas de parte solapadas")
        prev_end = end
        part_rows.append({"name": name, "start_t_ms": start, "end_t_ms": end,
                          "storage_id": str(storage_id)})
    return {
        "oracle_commit": oracle_commit,
        "oracle_files": dict(oracle_files),
        "storage": {"path": str(storage_path), "id": str(storage_id)},
        "witness_follow_ticks": int(witness_follow_ticks),
        "p2n_variant": p2n_variant,
        "parts": part_rows,
    }


class OrderLog:
    """backend.jsonl en memoria: seq propio y t_ms al recibir (R-11)."""

    def __init__(self, clock):
        self.clock = clock
        self.rows = []
        self._seq = 0
        self._lock = threading.Lock()

    def add(self, kind, data, t_ms=None):
        with self._lock:
            t = float(self.clock()) if t_ms is None else float(t_ms)
            if not math.isfinite(t):
                raise ValueError("t_ms no finito")
            row = {"seq": self._seq, "t_ms": t, "kind": kind, "data": dict(data)}
            self._seq += 1
            self.rows.append(row)
            return row

    def add_cut(self, epoch=""):
        return self.add("cut", {"target": "backend", "epoch": epoch})

    def add_restart_backend(self, epoch):
        return self.add("restart", {"target": "backend", "epoch": epoch})

    def add_restart_server(self, epoch, t_ms):
        return self.add("restart", {"target": "server", "epoch": epoch}, t_ms=t_ms)

    def kinds(self):
        return [r["kind"] for r in self.rows]


class JsonlWriter:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("w", encoding="utf-8", newline="\n")
        self._lock = threading.Lock()

    def write(self, row):
        line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        with self._lock:
            self._fh.write(line)
            self._fh.flush()

    def close(self):
        with self._lock:
            try:
                self._fh.close()
            except OSError:
                pass


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def oracle_files_sha(qa_dir=QA_DIR):
    return {name: sha256_file(Path(qa_dir) / name) for name in ("f2p_eval.py", "f2p_mutants.py")}


def check_oracle(repo_root=REPO_ROOT):
    return gate_core.check_oracle_files("F2P", ORACLE_COMMIT, repo_root=Path(repo_root), qa_dir=QA_DIR)


class BackendProc:
    """Backend real como subproceso (Q5): server.py --config --port --bridge-port."""

    def __init__(self, work_dir, scene_doc, clock, order_log, *, catalog_doc=None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.order_log = order_log
        self.web_port = free_port()
        self.bridge_port = free_port()
        self.proc = None
        self.config_path = self.work_dir / "backend.json"
        self.scene_path = self.work_dir / "scene.json"
        self._sse_thread = None
        self._stop = threading.Event()
        self.op_states = []
        self.human_key = secrets.token_urlsafe(32)
        self.ai_key = secrets.token_urlsafe(32)
        self.peer_key = secrets.token_urlsafe(32)
        self._write_scene(scene_doc)
        catalog = catalog_doc
        if catalog is None:
            catalog = json.loads((DEV_ROOT / "fixtures" / "catalog-m1.json").read_text(encoding="utf-8"))
        (self.work_dir / "catalog.json").write_text(
            json.dumps(catalog, ensure_ascii=False), encoding="utf-8", newline="\n")
        cfg = {
            "port": self.web_port, "bridge_port": self.bridge_port,
            "scene": str(self.scene_path), "catalog": str(self.work_dir / "catalog.json"),
            "web": str(DEV_ROOT / "app" / "web" / "dist"),
            "human_key": self.human_key, "ai_key": self.ai_key, "peer_key": self.peer_key,
        }
        self.config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8", newline="\n")

    def _write_scene(self, doc):
        self.scene_path.write_text(
            json.dumps({"rev": 1, "doc": doc}, ensure_ascii=False, sort_keys=True),
            encoding="utf-8", newline="\n")

    def load_scene_doc(self, doc):
        self._write_scene(doc)

    def start(self):
        self._stop.clear()
        cmd = [sys.executable, "-B", str(DEV_ROOT / "app" / "backend" / "server.py"),
               "--config", str(self.config_path),
               "--port", str(self.web_port), "--bridge-port", str(self.bridge_port)]
        self._log_fh = (self.work_dir / "backend.log").open(
            "w", encoding="utf-8", newline="\n")
        self.proc = subprocess.Popen(cmd, cwd=str(DEV_ROOT),
                                     stdout=self._log_fh, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", errors="replace")
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("el backend murio al arrancar: %s" % self.proc.returncode)
            try:
                status, _ = self.api_get("/api/session", key=self.human_key, timeout=1.0)
                if status in (200, 401, 403):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("el backend no respondio a tiempo")
        self._sse_thread = threading.Thread(target=self._sse_loop, daemon=True)
        self._sse_thread.start()
        return self

    def _sse_loop(self):
        while not self._stop.is_set():
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.web_port, timeout=5.0)
                conn.request("GET", "/api/events",
                             headers={"Authorization": "Bearer " + self.human_key})
                resp = conn.getresponse()
                if resp.status != 200:
                    time.sleep(0.1)
                    continue
                buf = b""
                while not self._stop.is_set():
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n\n"):
                        text = buf.decode("utf-8", "replace")
                        buf = b""
                        for line in text.splitlines():
                            if line.startswith("data: "):
                                try:
                                    payload = json.loads(line[6:])
                                except ValueError:
                                    continue
                                if isinstance(payload, dict) and payload.get("op_id"):
                                    row = dict(payload)
                                    self.op_states.append(row)
                                    self.order_log.add("op.state", row)
            except OSError:
                time.sleep(0.1)

    def stop(self):
        self._stop.set()
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        self.proc = None
        fh = getattr(self, "_log_fh", None)
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass
            self._log_fh = None

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def api_get(self, path, key=None, timeout=5.0):
        conn = http.client.HTTPConnection("127.0.0.1", self.web_port, timeout=timeout)
        headers = {}
        if key:
            headers["Authorization"] = "Bearer " + key
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except ValueError:
                body = raw.decode("utf-8", "replace")
            return int(resp.status), body
        finally:
            conn.close()

    def api_post(self, path, body, key=None, timeout=10.0):
        conn = http.client.HTTPConnection("127.0.0.1", self.web_port, timeout=timeout)
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        try:
            conn.request("POST", path, body=json.dumps(body).encode("utf-8"), headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            try:
                parsed = json.loads(raw.decode("utf-8")) if raw else None
            except ValueError:
                parsed = raw.decode("utf-8", "replace")
            return int(resp.status), parsed
        finally:
            conn.close()

    def snapshot(self):
        status, body = self.api_get("/api/scene", key=self.human_key)
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError("snapshot del backend no disponible: %s" % status)
        return body

    def apply(self, doc_id):
        snap = self.snapshot()
        return self.api_post("/api/apply",
                             {"doc_id": doc_id, "rev": snap["rev"], "hash": snap["hash"]},
                             key=self.human_key)

    def reset(self, doc_id):
        return self.api_post("/api/reset", {"doc_id": doc_id}, key=self.human_key)

    def observation(self):
        status, body = self.api_get("/api/observation", key=self.human_key)
        if status == 200 and isinstance(body, dict):
            self.order_log.add("api.observation", body)
        return status, body


def _is_catalog_pending(status, body):
    """409 catalog_pending del backend (brief :1258): el /catalog aun no acabo."""
    if int(status or 0) != 409 or not isinstance(body, dict):
        return False
    if body.get("code") == "catalog_pending":
        return True
    return any(isinstance(e, dict) and e.get("code") == "catalog_pending"
               for e in (body.get("errors") or []))


def wait_terminal(backend, op_id, timeout_s=60.0):
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        for row in reversed(backend.op_states):
            if row.get("op_id") == op_id:
                last = row
                if row.get("state") in ("observado", "parcial", "fallido"):
                    return row
                break
        time.sleep(0.02)
    return last


def wait_catalog_complete(tap, since_req_id=-1, timeout_s=30.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for rec in tap.records:
            if rec.get("dir") == "resp" and rec.get("path") == "/catalog" \
                    and int(rec.get("req_id", -1)) > since_req_id \
                    and rec.get("http") == 200 and isinstance(rec.get("body"), dict) \
                    and rec["body"].get("complete") is True:
                return rec
        time.sleep(0.02)
    return None


# ---------------------------------------------------------------------------
# Sonda (PartContext) helpers
# ---------------------------------------------------------------------------

def _payload_str_num(strs=None, nums=None):
    return wire.pack_payload(scalars_str=strs or {}, scalars_num=nums or {})


class ProbeJobError(RuntimeError):
    """Un censo/testigo no se pudo completar: la parte se corta INCONCLUSO."""


BUSY_ATTEMPTS = 40
BUSY_SLEEP_S = 0.25
JOB_POLL_SLEEP_S = 0.25


def _is_busy(out):
    return getattr(out, "status", None) == "rejected" \
        and getattr(out, "reason", None) == "busy"


def _issue_busy_retry(ctx, verb, payload, timeout_ms, *,
                      attempts=BUSY_ATTEMPTS, sleep_s=BUSY_SLEEP_S):
    """Arranca una orden reintentando ante rejected/busy con un tope."""
    last = None
    for _ in range(int(attempts)):
        out = f03_common.issue_one(ctx, "server", verb, payload,
                                   timeout_ms=timeout_ms)
        if not _is_busy(out):
            return out
        last = out
        time.sleep(float(sleep_s))
    raise ProbeJobError("%s: rejected/busy tras %s intentos"
                        % (verb, attempts))


def wait_job_terminal(ctx, job, timeout_ms=30000):
    """Espera a que el trabajo llegue a un estado terminal (sondea job_read)."""
    deadline = time.monotonic() + float(timeout_ms) / 1000.0
    while True:
        out = f03_common.issue_one(
            ctx, "server", "job_read",
            wire.pack_payload({"job": str(job)}, {"page_n": 0}),
            timeout_ms=5000)
        if out.status == "done" and out.payload:
            state = str(out.payload["str"].get("state") or "")
            if state in f03_common.TERMINAL_JOB_STATES:
                return out
            if state not in ("running", ""):
                raise ProbeJobError("job_read %s: estado %r" % (job, state))
        elif not _is_busy(out):
            raise ProbeJobError("job_read %s: %s/%s"
                                % (job, out.status, out.reason))
        if time.monotonic() >= deadline:
            raise ProbeJobError("job %s no llego a terminal en %s ms"
                                % (job, timeout_ms))
        time.sleep(JOB_POLL_SLEEP_S)


def free_job(ctx, job, timeout_ms=10000):
    """job_free esperando a que acabe; busy se reintenta con tope."""
    out = _issue_busy_retry(ctx, "job_free",
                            _payload_str_num({"job": str(job)}),
                            timeout_ms=timeout_ms)
    if out.status != "done":
        raise ProbeJobError("job_free %s: %s/%s" % (job, out.status, out.reason))
    return out


def _job_of(out, verb):
    job = ""
    if out.payload:
        job = str(out.payload["str"].get("job") or "")
    if out.status != "done" or not job:
        raise ProbeJobError("%s: %s/%s sin trabajo"
                            % (verb, out.status, out.reason))
    return job


def _read_and_free(ctx, job, timeout_ms):
    """Ciclo entero: esperar fin, leer todas las paginas, liberar."""
    wait_job_terminal(ctx, job, timeout_ms=timeout_ms)
    pages = f03_common.read_job_pages(ctx, "server", job,
                                      timeout_ms=timeout_ms)
    rows = list(pages.get("rows") or [])
    free_job(ctx, job)
    return rows


def probe_census(ctx, tag, *, center=CENTER, radius=MAIN_RADIUS, timeout_ms=30000,
                 director_uid=""):
    strs = {"area_tag": tag}
    if director_uid:
        strs["director_uid"] = str(director_uid)
    out = _issue_busy_retry(
        ctx, "per_census_start",
        _payload_str_num(strs,
                         {"center_x_m": float(center[0]), "center_z_m": float(center[1]),
                          "radius_m": float(radius), "select_all_entityai_b": 1.0,
                          "include_director_b": 1.0}),
        timeout_ms=timeout_ms)
    job = _job_of(out, "per_census_start")
    rows = _read_and_free(ctx, job, timeout_ms)
    return out, rows


def probe_witness(ctx, tag, *, window_ms=30000, follow_ticks=3):
    out = _issue_busy_retry(
        ctx, "per_witness_start",
        _payload_str_num({"witness_tag": tag},
                         {"center_x_m": CENTER[0], "center_z_m": CENTER[1],
                          "radius_m": WITNESS_RADIUS, "window_ms": float(window_ms),
                          "follow_ticks": float(follow_ticks)}),
        timeout_ms=int(window_ms) + 15000)
    _job_of(out, "per_witness_start")
    return out


def witness_pages(ctx, out, timeout_ms=90000):
    job = _job_of(out, "per_witness_start")
    return _read_and_free(ctx, job, timeout_ms)


def probe_status(ctx, director_uid=""):
    if director_uid:
        payload = _payload_str_num({"director_uid": str(director_uid)}, {})
    else:
        payload = wire.empty_payload()
    return f03_common.issue_one(ctx, "server", "per_status", payload,
                                timeout_ms=15000)


def probe_director_uid(ctx, *, timeout_ms=30000):
    deadline = time.monotonic() + float(timeout_ms) / 1000.0
    last_n = None
    while True:
        left_ms = int((deadline - time.monotonic()) * 1000.0)
        if left_ms <= 0:
            raise RuntimeError(
                "director_uid: players_n distinto de 1 hasta el tope "
                "(ultimo players_n=%r, timeout_ms=%r)" % (last_n, timeout_ms))
        out = f03_common.issue_one(
            ctx, "server", "per_status",
            _payload_str_num({"director_uid": ""}, {}),
            timeout_ms=max(1, min(int(timeout_ms), left_ms)))
        payload = getattr(out, "payload", None) or {}
        if not isinstance(payload, dict):
            return ""
        strs = payload.get("str") or {}
        nums = payload.get("num") or {}
        rows = payload.get("rows") or []
        if "players_n" not in nums and "players_n" not in strs:
            return ""
        try:
            last_n = int(float(nums.get("players_n", strs.get("players_n"))))
        except (TypeError, ValueError):
            return ""
        if last_n == 1:
            for key in ("director_uid", "player_uid", "uid", "owner_uid"):
                val = strs.get(key)
                if isinstance(val, str) and val:
                    return val
            for key, val in strs.items():
                if "uid" in str(key) and isinstance(val, str) and val:
                    return val
            for row in rows:
                if isinstance(row, dict):
                    for key in ("director_uid", "player_uid", "uid", "owner_uid"):
                        val = row.get(key)
                        if isinstance(val, str) and val:
                            return val
                    for key, val in row.items():
                        if "uid" in str(key) and isinstance(val, str) and val:
                            return val
            raise RuntimeError("director_uid: players_n=1 sin UID en per_status")
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "director_uid: players_n distinto de 1 hasta el tope "
                "(ultimo players_n=%r, timeout_ms=%r)" % (last_n, timeout_ms))
        time.sleep(0.05)


def probe_cleanup(ctx, tag="cleanup"):
    return f03_common.issue_one(
        ctx, "server", "per_cleanup_qa",
        wire.pack_payload(scalars_str={"cleanup_tag": tag}, scalars_num={},
                          num_cols=[], str_cols=[], row_dicts=[]),
        timeout_ms=30000)


def probe_spawn(ctx, mode, class_name, *, tag, pos=None, target_net_id="",
                child_cargo_class="", health_mark_ratio=None):
    nums = {}
    if pos is not None:
        # La sonda lee x_m y z_m (DSBX_QA_X_Persist.c, HandleSpawnRaw). Con pos_x_m/pos_z_m el ajeno y el control
        # nacian en el origen del mapa (6.a partida de T4, 917bc73: Barrel_Blue en (0, -51.6, 0)).
        nums.update({"x_m": float(pos[0]), "z_m": float(pos[1])})
    if health_mark_ratio is not None:
        nums["health_mark_ratio"] = float(health_mark_ratio)
    return f03_common.issue_one(
        ctx, "server", "per_spawn_raw",
        _payload_str_num({"mode": mode, "tag": tag, "class_name": class_name,
                          "target_net_id": target_net_id,
                          "child_cargo_class": child_cargo_class}, nums),
        timeout_ms=30000)


def load_doc(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def scene1_doc():
    return load_doc(DEV_ROOT / "fixtures" / "escena-sin-actores.json")


def find_scene_container_net(rows, doc, lid="obj-17", tol_m=0.5):
    """net_id del contenedor `lid` de la escena en un censo (brief :250 y :311): la única raíz viva de su clase
    a menos de `tol_m` de su pose (x, z). Devuelve "" si no hay exactamente una."""
    ent = next((e for e in (doc or {}).get("entities") or [] if e.get("id") == lid), None)
    if ent is None:
        return ""
    cls = str(ent.get("cls") or "")
    x, z = float(ent.get("x")), float(ent.get("z"))
    cands = []
    for r in rows or []:
        if str(r.get("class_name") or "") != cls or str(r.get("parent_net_id") or "") != "":
            continue
        try:
            d = math.hypot(float(r.get("pos_x_m")) - x, float(r.get("pos_z_m")) - z)
        except (TypeError, ValueError):
            continue
        if d < float(tol_m):
            cands.append(str(r.get("net_id") or ""))
    return cands[0] if len(cands) == 1 and cands[0] else ""


CREATURE_DISK_RADIUS_M = {"infectado": 60.0, "animal": 120.0}


def scene_creatures(doc):
    """Criaturas de la escena (kind infectado/animal) con su clase."""
    out = []
    for ent in (doc or {}).get("entities") or []:
        kind = str(ent.get("kind") or "")
        if kind in CREATURE_DISK_RADIUS_M and ent.get("id") and ent.get("cls"):
            out.append({"lid": str(ent["id"]), "kind": kind,
                        "cls": str(ent["cls"]),
                        "doc_pos": (float(ent.get("x") or 0.0),
                                    float(ent.get("z") or 0.0))})
    return out


def note_creature_positions(store, rows, creatures):
    """Ultima posicion observada por criatura, casada por clase (censo/testigo).

    La posicion del documento solo elige entre candidatas de la misma clase;
    la que se guarda es siempre la observada en la fila.
    """
    for c in creatures or []:
        cands = []
        for r in rows or []:
            if str(r.get("class_name") or "") != c["cls"]:
                continue
            try:
                pos = (float(r.get("pos_x_m")), float(r.get("pos_z_m")))
            except (TypeError, ValueError):
                continue
            cands.append(pos)
        if not cands:
            continue
        ref = store.get(c["lid"], (c["doc_pos"], None))[0]
        best = min(cands, key=lambda p: math.hypot(p[0] - ref[0], p[1] - ref[1]))
        store[c["lid"]] = (best, c["kind"])
    return store


def scene2_doc():
    p = DEV_ROOT / "fixtures" / "escena-f2p-2.json"
    if p.is_file():
        return load_doc(p)
    return load_doc(QA_DIR / "fixtures" / "f2p_scene2.json")


class ServerHelloTimeout(RuntimeError):
    pass


def tap_product_hellos(records):
    reqs = {}
    for rec in records or []:
        if rec.get("dir") == "req" and rec.get("path") == "/hello" \
                and isinstance(rec.get("body"), dict):
            reqs[rec.get("req_id")] = rec
    out = []
    for rec in records or []:
        if rec.get("dir") != "resp" or rec.get("path") != "/hello":
            continue
        req = reqs.get(rec.get("req_id"))
        if req is None:
            continue
        body = rec.get("body") if isinstance(rec.get("body"), dict) else {}
        accepted = rec.get("http") == 200 and body.get("ok") is True \
            and bool(str(body.get("session") or ""))
        if not accepted:
            continue
        rbody = req.get("body") or {}
        if str(rbody.get("peer") or "") != "server":
            continue
        out.append({"t_ms": float(rec.get("t_ms")),
                    "inst": str(rbody.get("inst") or ""),
                    "epoch": str(rbody.get("epoch") or "")})
    out.sort(key=lambda h: h["t_ms"])
    return out


def probe_server_hellos(ctx):
    bridge = getattr(ctx, "bridge", None)
    events = []
    if bridge is not None:
        try:
            with bridge.cv:
                events = list(bridge.events)
        except Exception:
            events = list(getattr(bridge, "events", []) or [])
    out = []
    for ev in events:
        if ev.get("ev") == "hello" and ev.get("http") == 200 \
                and ev.get("ok") is not False and str(ev.get("peer") or "") == "server":
            try:
                t_ms = float(ev.get("t_ms"))
            except (TypeError, ValueError):
                continue
            out.append({"t_ms": t_ms, "inst": str(ev.get("inst") or "")})
    out.sort(key=lambda h: h["t_ms"])
    return out


def probe_client_hellos(ctx):
    """hello del peer cliente en el bridge de la sonda (F4)."""
    bridge = getattr(ctx, "bridge", None)
    events = []
    if bridge is not None:
        try:
            with bridge.cv:
                events = list(bridge.events)
        except Exception:
            events = list(getattr(bridge, "events", []) or [])
    out = []
    for ev in events:
        if ev.get("ev") == "hello" and ev.get("http") == 200 \
                and ev.get("ok") is not False and str(ev.get("peer") or "") == "client":
            try:
                t_ms = float(ev.get("t_ms"))
            except (TypeError, ValueError):
                continue
            out.append({"t_ms": t_ms, "inst": str(ev.get("inst") or "")})
    out.sort(key=lambda h: h["t_ms"])
    return out


def wait_client_hello(ctx, since_t_ms, timeout_s=60.0):
    deadline = time.monotonic() + float(timeout_s)
    since = float("-inf") if since_t_ms is None else float(since_t_ms)
    while True:
        hits = [h for h in probe_client_hellos(ctx) if h["t_ms"] > since]
        if hits:
            return hits[0]
        if time.monotonic() >= deadline:
            raise ServerHelloTimeout(
                "el cliente no volvio tras el reinicio: sin hello del peer "
                "cliente tras t_restart=%r" % (since_t_ms,))
        time.sleep(0.05)


def tap_unmatched_req_ids(records):
    req_ids = {r.get("req_id") for r in records or [] if r.get("dir") == "req"}
    resp_ids = {r.get("req_id") for r in records or [] if r.get("dir") == "resp"}
    return req_ids - resp_ids


def wait_tap_drained(tap, quiet_s=2.0, timeout_s=30.0):
    deadline = time.monotonic() + float(timeout_s)
    last_count = -1
    last_change = time.monotonic()
    while time.monotonic() < deadline:
        records = list(getattr(tap, "records", []) or [])
        if len(records) != last_count:
            last_count = len(records)
            last_change = time.monotonic()
        if not tap_unmatched_req_ids(records) \
                and (time.monotonic() - last_change) >= float(quiet_s):
            return True
        time.sleep(0.05)
    return not tap_unmatched_req_ids(list(getattr(tap, "records", []) or []))


def wait_backend_reconciled(tap, since_t_ms, timeout_s=25.0):
    """True si tras since hay un /hello 200 del producto y un /poll 200
    posterior: el backend nuevo ya entrego en la sesion nueva."""
    deadline = time.monotonic() + float(timeout_s)
    since = float("-inf") if since_t_ms is None else float(since_t_ms)
    while True:
        records = list(getattr(tap, "records", []) or [])
        hello_t = None
        for r in records:
            if r.get("dir") == "resp" and r.get("path") == "/hello" \
                    and r.get("http") == 200 and float(r.get("t_ms", 0)) > since:
                hello_t = float(r["t_ms"])
                break
        if hello_t is not None and any(
                r.get("dir") == "resp" and r.get("path") == "/poll"
                and r.get("http") == 200 and float(r.get("t_ms", 0)) > hello_t
                for r in records):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def wait_life_hellos(tap, ctx, since_t_ms, timeout_s=60.0):
    deadline = time.monotonic() + float(timeout_s)
    since = float("-inf") if since_t_ms is None else float(since_t_ms)
    while True:
        prod = [h for h in tap_product_hellos(getattr(tap, "records", []))
                if h["t_ms"] > since and h["epoch"]]
        probe = [h for h in probe_server_hellos(ctx) if h["t_ms"] > since]
        if prod and probe:
            return prod[0]
        if time.monotonic() >= deadline:
            raise ServerHelloTimeout(
                "saludo no llego a tiempo: producto=%s sonda=%s tras t_restart=%r"
                % (bool(prod), bool(probe), since_t_ms))
        time.sleep(0.05)


class Campaign:
    """Guion P1..P5 (R-37..R-45). En seco los dos mundos no casan (Q1):
    las mediciones quedan missing/unbacked, sin motivos estructurales."""

    def __init__(self, ctx, backend_holder, tap, order_log, mode="seco",
                 *, hello_timeout_s=60.0, restart_hook=None,
                 director_uid="", on_part=None, director_timeout_ms=30000,
                 cliente="lanzar", esperar_cliente=False):
        self.ctx = ctx
        self.holder = backend_holder  # dict con 'backend' vigente
        self.tap = tap
        self.log = order_log
        self.mode = mode
        self.parts = []
        self.notes = []
        self.current_epoch = ""
        self.hello_timeout_s = float(hello_timeout_s)
        self.restart_hook = restart_hook
        self.director_uid = str(director_uid or "")
        self.director_timeout_ms = int(director_timeout_ms)
        self.inconcluso = ""
        self.on_part = on_part
        self.cliente = str(cliente or "lanzar")
        self._cur_part = None
        self._cur_start = None
        self._creature_pos = {}
        try:
            self._creatures = scene_creatures(scene1_doc())
        except Exception:
            self._creatures = []
        # F4: en modo real el cliente para y vuelve con el servidor
        # (StopBoth); con 'operador' rigen el aviso y el mismo tope.
        self.esperar_cliente = bool(esperar_cliente)

    def _census(self, tag, **kw):
        return probe_census(self.ctx, tag, director_uid=self.director_uid, **kw)

    def _note_rows(self, rows):
        if rows:
            note_creature_positions(self._creature_pos, rows, self._creatures)

    def _census_tracked(self, tag, **kw):
        kw.pop("director_uid", None)
        out, rows = probe_census(self.ctx, tag,
                                 director_uid=self.director_uid, **kw)
        self._note_rows(rows)
        return out, rows

    def _witness_tracked(self, out):
        rows = witness_pages(self.ctx, out)
        self._note_rows(rows)
        return rows

    def _reset_and_census(self, doc_id, post_tag):
        """Reset y censo posterior con un disco por criatura (brief :257, :547).

        El disco va centrado en la ultima posicion observada antes del reset,
        60 m para infectados y 120 m para animales, con la etiqueta de la
        etapa (<post_tag>:disk:<lid>) y en serie tras el censo principal.
        """
        before = dict(self._creature_pos)
        self._reset(doc_id)
        result = self._census_tracked(post_tag)
        for lid in sorted(before):
            pos, kind = before[lid]
            radius = CREATURE_DISK_RADIUS_M.get(kind)
            if radius is None:
                continue
            self._census_tracked("%s:disk:%s" % (post_tag, lid),
                                 center=pos, radius=radius)
        return result

    def _discs_for_missing(self, tag, rows):
        """Un disco por criatura de la escena que no sale en el censo principal `tag`.

        Partida de 9debe9b: el ciervo y el corzo se alejan ~30-40 m tras cada apply y salen del disco
        principal (115 m), y F2P-01, F2P-07 y F2P-09 los dan por census_missing. El oraculo une los discos
        por etiqueta (<tag>:disk:<lid>, f2p_eval.py:1637), asi que el censo que juzga presencia lleva un
        disco por criatura ausente, centrado en su ultima posicion conocida: 60 m infectado, 120 m animal.
        Las clases de la escena 1 son unicas y la CE de la mision va a cero, asi que la clase identifica.
        """
        seen = {str(r.get("class_name") or "") for r in rows or []}
        for c in self._creatures:
            if c["cls"] in seen:
                continue
            known = self._creature_pos.get(c["lid"])
            if not known:
                continue
            pos, kind = known
            radius = CREATURE_DISK_RADIUS_M.get(kind)
            if radius is None:
                continue
            self._census_tracked("%s:disk:%s" % (tag, c["lid"]), center=pos, radius=radius)

    def _census_presence(self, tag):
        """Censo principal de un instante en que el oraculo juzga presencia, mas los discos que falten."""
        out = self._census_tracked(tag, director_uid=self.director_uid)
        rows = out[1] if isinstance(out, tuple) and len(out) > 1 else []
        self._discs_for_missing(tag, rows)
        return out

    def _track_animals(self, tag):
        """Seguimiento de los animales de la escena: un disco de 120 m en la ultima posicion conocida de cada uno.

        6.a partida de T4 (917bc73): entre el apply1 de P3 y P3:pre_reset pasan unos 2 minutos (dos reinicios del
        backend y el testigo del apply2) y el ciervo y el corzo se alejaban mas de 120 m de donde nacieron, asi
        que F2P-05 los daba por census_missing. Con discos intermedios la ultima posicion conocida es reciente.
        La etiqueta `<tag>:disk:<lid>` nunca es la de un censo principal: el oraculo no la une, F2P-10 la salta
        (f2p_eval.py:4469 y :4492) y la busqueda de la ultima posicion valida si la usa (:1576).
        """
        for c in self._creatures:
            if c["kind"] != "animal":
                continue
            known = self._creature_pos.get(c["lid"])
            if not known:
                continue
            pos, kind = known
            self._census_tracked("%s:disk:%s" % (tag, c["lid"]), center=pos,
                                 radius=CREATURE_DISK_RADIUS_M[kind])

    def _status(self):
        return probe_status(self.ctx, director_uid=self.director_uid)

    def _pad_remaining(self, done_names):
        now = float(self.ctx.now_h_ms())
        last = max([p[2] for p in self.parts], default=now)
        if last < now:
            last = now
        for name in PART_ORDER:
            if name in done_names:
                continue
            start = last + 1.0
            end = start + 999.0
            self.parts.append((name, float(start), float(end)))
            last = end
        self.parts.sort(key=lambda p: PART_ORDER.index(p[0]))

    def _wait_first_life(self):
        hello = wait_life_hellos(self.tap, self.ctx, None,
                                 timeout_s=self.hello_timeout_s)
        self.current_epoch = str(hello["epoch"])
        return hello

    def _restart_server(self):
        # Orden R2-02/F4: censo de antes (en run), StopBoth cliente+servidor,
        # drenar, t_restart, arrancar servidor y cliente, saludos, restart.
        if self.restart_hook is None:
            raise ServerHelloTimeout("sin restart_hook: no hay reinicio del servidor")
        try:
            self.restart_hook("stop")
        except ServerHelloTimeout:
            raise
        except Exception as exc:
            raise ServerHelloTimeout(
                "la parada del servidor fallo (StopBoth): %s" % exc) from exc
        wait_tap_drained(self.tap, quiet_s=2.0,
                         timeout_s=max(30.0, self.hello_timeout_s))
        t_restart = float(self.ctx.now_h_ms())
        try:
            self.restart_hook("start")
        except ServerHelloTimeout:
            raise
        except Exception as exc:
            raise ServerHelloTimeout(
                "el arranque tras el reinicio fallo: %s" % exc) from exc
        hello = wait_life_hellos(self.tap, self.ctx, t_restart,
                                 timeout_s=self.hello_timeout_s)
        if self.esperar_cliente:
            # El cliente vuelve con el mismo perfil y el mismo UID; con
            # -Cliente operador rigen el aviso previo y este mismo tope.
            wait_client_hello(self.ctx, t_restart,
                              timeout_s=self.hello_timeout_s)
        # La parada propia del peer viejo puede dejar un ConnectionReset
        # guardado en el bridge; con el saludo nuevo verificado, no es un
        # fallo de la vida nueva.
        bridge = getattr(self.ctx, "bridge", None)
        if bridge is not None and getattr(bridge, "failure", None) is not None:
            try:
                with bridge.cv:
                    bridge.failure = None
            except Exception:
                bridge.failure = None
            self.notes.append("bridge.failure de la parada propia limpiado tras el saludo")
        if self.director_uid:
            try:
                uid = probe_director_uid(
                    self.ctx, timeout_ms=self.director_timeout_ms)
            except Exception as exc:
                raise ServerHelloTimeout(
                    "el cliente no volvio tras el reinicio: %s" % exc) from exc
            if uid and uid != self.director_uid:
                raise ServerHelloTimeout(
                    "el cliente volvio con otro UID tras el reinicio")
        epoch = str(hello["epoch"])
        self.log.add_restart_server(epoch, t_ms=t_restart)
        self.current_epoch = epoch
        return epoch

    @property
    def backend(self):
        return self.holder["backend"]

    def _begin(self, name):
        self._cur_part = name
        self._cur_start = self.ctx.now_h_ms()
        self._t0 = self._cur_start
        if self.on_part is not None:
            try:
                self.on_part("en_curso", name)
            except Exception:
                pass
        return self._t0

    def _end(self, name, start):
        end = self.ctx.now_h_ms()
        if end <= start:
            end = start + 1.0
        self.parts.append((name, float(start), float(end)))
        if self.on_part is not None:
            try:
                self.on_part("cerrada", name)
            except Exception:
                pass

    def _backend_op(self, verb, doc_id):
        """POST al backend mirando codigo y cuerpo (brief :1258).

        Ante 409 catalog_pending se reintenta hasta un tope; con cualquier
        otra respuesta sin op_id la parte se corta INCONCLUSO (ProbeJobError,
        que run() recoge en el informe).
        """
        attempts = int(getattr(self, "catalog_attempts", 60))
        sleep_s = float(getattr(self, "catalog_sleep_s", 0.5))
        fn = getattr(self.backend, verb)
        for i in range(max(1, attempts)):
            status, body = fn(doc_id)
            op_id = body.get("op_id") if isinstance(body, dict) else None
            if op_id:
                wait_terminal(self.backend, op_id, timeout_s=45.0)
                return body
            if _is_catalog_pending(status, body) and i + 1 < max(1, attempts):
                time.sleep(sleep_s)
                continue
            raise ProbeJobError(
                "%s %s: HTTP %s sin op_id: %s" % (verb, doc_id, status, body))
        raise ProbeJobError("%s %s: catalog_pending tras %s intentos"
                            % (verb, doc_id, attempts))

    def _apply(self, doc_id):
        return self._backend_op("apply", doc_id)

    def _reset(self, doc_id):
        return self._backend_op("reset", doc_id)

    def _restart_backend(self, doc):
        old = self.backend
        if old is not None:
            old.stop()
            while old.alive():
                time.sleep(0.02)
        # R-27 paso 4: restart tras la muerte y sin intercambios en vuelo.
        self.log.add_restart_backend(self.current_epoch)
        nb = BackendProc(old.work_dir, doc, self.ctx.now_h_ms, self.log)
        # El nuevo backend comparte puertos logicos del tap: se re-apunta.
        nb.bridge_port = old.bridge_port
        nb.web_port = old.web_port
        # Reescribe config con los puertos del tap/viejo antes de arrancar.
        cfg = json.loads(nb.config_path.read_text(encoding="utf-8"))
        cfg["bridge_port"] = nb.bridge_port
        cfg["port"] = nb.web_port
        cfg["peer_key"] = old.peer_key
        cfg["human_key"] = old.human_key
        cfg["ai_key"] = old.ai_key
        nb.human_key, nb.ai_key, nb.peer_key = old.human_key, old.ai_key, old.peer_key
        nb.config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
        t_restart = float(self.ctx.now_h_ms())
        nb.start()
        self.holder["backend"] = nb
        if not wait_backend_reconciled(self.tap, t_restart, timeout_s=25.0):
            raise ServerHelloTimeout(
                "backend nuevo sin hello+poll del producto tras el reinicio: "
                "no se entrega ninguna orden hasta reconciliar")
        return nb

    def run(self):
        try:
            return self._run_inner()
        except (ProbeJobError, ServerHelloTimeout) as exc:
            if not self.inconcluso:
                self.inconcluso = "INCONCLUSO: %s" % exc
            self.notes.append(self.inconcluso)
            done = {p[0] for p in self.parts}
            cur = getattr(self, "_cur_part", None)
            if cur and cur not in done:
                self._end(cur, getattr(self, "_cur_start", None)
                          or float(self.ctx.now_h_ms()))
                done.add(cur)
            self._pad_remaining(done)
            return self.parts

    def _run_inner(self):
        ctx = self.ctx
        # P1: saludos de la primera vida antes del primer trabajo (R2-02)
        try:
            self._wait_first_life()
        except ServerHelloTimeout as exc:
            self.inconcluso = "INCONCLUSO: %s" % exc
            self.notes.append(self.inconcluso)
            self._pad_remaining(set())
            return self.parts
        if not self.director_uid:
            try:
                self.director_uid = probe_director_uid(
                    ctx, timeout_ms=self.director_timeout_ms)
                if not self.director_uid:
                    self.notes.append(
                        "per_status sin players_n (sonda sin UID del director): "
                        "censo sin director_uid")
            except Exception as exc:
                self.inconcluso = "INCONCLUSO: %s" % exc
                self.notes.append(self.inconcluso)
                self._pad_remaining(set())
                return self.parts
        t = self._begin("P1")
        try:
            probe_status(ctx, director_uid=self.director_uid)
        except Exception as exc:
            self.notes.append("P1 per_status: %s" % exc)
        self._census_tracked("P1:base", director_uid=self.director_uid)
        w = probe_witness(ctx, "P1:control", window_ms=5000)
        self._witness_tracked(w)
        self._end("P1", t)
        # P2 (Q2: el tap contesta el primer acuse)
        t = self._begin("P2")
        self.tap.intercept_first_result()
        w = probe_witness(ctx, "P2:apply", window_ms=30000)
        self._apply(DOC1_ID)
        self._witness_tracked(w)
        self._census_presence("P2:post")
        self._end("P2", t)
        # P2n (Q3: sin estimulo, no se manda el apply)
        t = self._begin("P2n")
        self.notes.append("P2n sin apply: stimulus_not_observed (Q3)")
        self._census_tracked("P2n:pre_reset", director_uid=self.director_uid)
        self._reset_and_census(DOC1_ID, "P2n:clean")
        self._end("P2n", t)
        # P3
        t = self._begin("P3")
        w = probe_witness(ctx, "P3:apply1", window_ms=30000)
        self._apply(DOC1_ID)
        self._witness_tracked(w)
        self._track_animals("P3:sigue1")
        self._restart_backend(scene2_doc())
        self._track_animals("P3:sigue2")
        w = probe_witness(ctx, "P3:apply2", window_ms=30000)
        self._apply(DOC2_ID)
        self._witness_tracked(w)
        self._track_animals("P3:sigue3")
        self._restart_backend(scene1_doc())
        _pre = self._census_presence("P3:pre_spawn")
        _pre_rows = _pre[1] if isinstance(_pre, tuple) and len(_pre) > 1 else []
        # Brief :250 y :311: el ajeno va dentro de obj-17, con el net_id del contenedor sacado del censo.
        _obj17 = find_scene_container_net(_pre_rows, scene1_doc(), "obj-17")
        # En seco la sonda falsa censa su propio mundo (Q1), sin obj-17: se anota y sigue, para que el seco
        # siga sirviendo de regresión. En diag y retail, sin obj-17 la parte se corta.
        _real = self.mode != "seco"
        if not _obj17:
            if _real:
                raise ProbeJobError("P3: obj-17 (SeaChest) no sale una sola vez en el censo P3:pre_spawn; "
                                    "sin él no hay ajeno en el contenedor (A3)")
            self.notes.append("P3 seco: obj-17 no está en el mundo falso de la sonda; ajeno sin contenedor")
        try:
            for _mode, _cls, _tag, _kw in (
                    ("foreign_ground", "Barrel_Blue", "fg",
                     {"pos": (6180.0, 7650.0)}),
                    ("foreign_in_container", "Apple", "fc",
                     {"target_net_id": _obj17})):
                _out = probe_spawn(ctx, _mode, _cls, tag=_tag, **_kw)
                if getattr(_out, "status", None) != "done":
                    # Sin los ajenos no hay A3: el reset no saldría parcial/contenido_ajeno y el oráculo juzgaría
                    # una partida que no es la del guion. Se corta con INCONCLUSO, como un censo imposible.
                    _msg = "P3 spawn %s/%s: %s/%s" % (_mode, _cls, getattr(_out, "status", None),
                                                      getattr(_out, "reason", None))
                    if _real:
                        raise ProbeJobError(_msg)
                    self.notes.append(_msg + " (seco)")
        except ProbeJobError:
            raise
        except Exception as exc:
            raise ProbeJobError("P3 ajenos: %s" % exc) from exc
        self._census_presence("P3:pre_reset")
        self._reset_and_census(DOC1_ID, "P3:post_reset1")
        self._census_tracked("P3:pre_reset2", director_uid=self.director_uid)
        self._reset_and_census(DOC1_ID, "P3:post_reset2")
        self._end("P3", t)
        # P3c
        t = self._begin("P3c")
        try:
            probe_cleanup(ctx, "P3c")
        except Exception as exc:
            self.notes.append("P3c cleanup: %s" % exc)
        self._census_tracked("P3c:pre_reset", director_uid=self.director_uid)
        self._reset_and_census(DOC1_ID, "P3c:clean")
        self._end("P3c", t)
        # P4a
        t = self._begin("P4a")
        self._restart_backend(scene1_doc())
        try:
            _out = probe_spawn(ctx, "persistent_control", "Barrel_Yellow",
                               tag="control", pos=CONTROL_POS,
                               child_cargo_class="Fireplace",
                               health_mark_ratio=0.845)
            if getattr(_out, "status", None) != "done":
                self.notes.append("P4a spawn control: %s/%s"
                                  % (_out.status, _out.reason))
        except Exception as exc:
            self.notes.append("P4a control: %s" % exc)
        w = probe_witness(ctx, "P4a:apply1", window_ms=30000)
        self._apply(DOC1_ID)
        self._witness_tracked(w)
        self._census_presence("P4a:post_apply1")
        self._census_tracked("P4a:pre_reset", director_uid=self.director_uid)
        self._reset_and_census(DOC1_ID, "P4a:post_reset")
        w = probe_witness(ctx, "P4a:apply2", window_ms=30000)
        self._apply(DOC1_ID)
        self._witness_tracked(w)
        self._census_presence("P4a:post_apply2")
        self._end("P4a", t)
        # P4b (reinicio del servidor, R2-02)
        t = self._begin("P4b")
        self._census_tracked("P4b:pre_restart", director_uid=self.director_uid)
        try:
            self._restart_server()
        except ServerHelloTimeout as exc:
            self.inconcluso = "INCONCLUSO: %s" % exc
            self.notes.append(self.inconcluso)
            self._end("P4b", t)
            self._pad_remaining({"P1", "P2", "P2n", "P3", "P3c", "P4a", "P4b"})
            return self.parts
        self._census_tracked("P4b:post_restart", director_uid=self.director_uid)
        self._census_tracked("P4b:control", center=CONTROL_POS, radius=30.0, director_uid=self.director_uid)
        w = probe_witness(ctx, "P4b:apply", window_ms=30000)
        self._apply(DOC1_ID)
        self._witness_tracked(w)
        self._census_presence("P4b:post_apply")
        self._end("P4b", t)
        # P4c
        t = self._begin("P4c")
        self._census_tracked("P4c:pre_reset", director_uid=self.director_uid)
        self._reset_and_census(DOC1_ID, "P4c:post_reset")
        try:
            self._restart_server()
        except ServerHelloTimeout as exc:
            self.inconcluso = "INCONCLUSO: %s" % exc
            self.notes.append(self.inconcluso)
            self._end("P4c", t)
            self._pad_remaining({"P1", "P2", "P2n", "P3", "P3c", "P4a", "P4b", "P4c"})
            return self.parts
        self._census_tracked("P4c:post_restart", director_uid=self.director_uid)
        self._census_tracked("P4c:control", center=CONTROL_POS, radius=30.0, director_uid=self.director_uid)
        try:
            probe_cleanup(ctx, "P4c")
        except Exception as exc:
            self.notes.append("P4c cleanup: %s" % exc)
        self._end("P4c", t)
        # P5 (R-45: retencion en el tap, cut antes de parar, restart despues)
        t = self._begin("P5")
        self._census_tracked("P5:pre", director_uid=self.director_uid)
        w = probe_witness(ctx, "P5:cut", window_ms=30000)
        self.tap.hold_from_first_result()
        status, body = self.backend.apply(DOC1_ID)
        # Espera breve a que la retencion se arme; si no, se corta igual.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and self.tap.held_count() == 0:
            time.sleep(0.02)
        try:
            probe_status(ctx); probe_status(ctx)
        except Exception:
            pass
        self.log.add_cut(self.current_epoch)  # R-28.1: antes de parar
        old = self.backend
        if old is not None:
            old.stop()
        self.tap.release_held()  # lo retenido recibe el 502 del tap
        self._restart_backend_after_cut(scene1_doc())
        # Reconciliacion (R-29): esperar hello nuevo y un poll 200 posterior
        # antes de la primera entrega de escena del tramo nuevo.
        t_restart = self.ctx.now_h_ms()
        wait_backend_reconciled(self.tap, t_restart, timeout_s=25.0)
        self._witness_tracked(w)
        self._census_tracked("P5:post_cut", director_uid=self.director_uid)
        w = probe_witness(ctx, "P5:apply2", window_ms=30000)
        self._apply(DOC1_ID)
        self._witness_tracked(w)
        self._census_presence("P5:post_apply")
        self._end("P5", t)
        return self.parts

    def _restart_backend_after_cut(self, doc):
        old = self.holder["backend"]
        self.log.add_restart_backend(self.current_epoch)
        nb = BackendProc(old.work_dir, doc, self.ctx.now_h_ms, self.log)
        cfg = json.loads(nb.config_path.read_text(encoding="utf-8"))
        cfg.update({"bridge_port": old.bridge_port, "port": old.web_port,
                    "peer_key": old.peer_key, "human_key": old.human_key,
                    "ai_key": old.ai_key})
        nb.bridge_port, nb.web_port = old.bridge_port, old.web_port
        nb.human_key, nb.ai_key, nb.peer_key = old.human_key, old.ai_key, old.peer_key
        nb.config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8", newline="\n")
        nb.start()
        self.holder["backend"] = nb
        return nb


def _load_fases_module():
    path = Path(__file__).resolve().with_name("f2p_fases.py")
    spec = importlib.util.spec_from_file_location("f2p_fases_live", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_FASES = _load_fases_module()
FaseStore = _FASES.FaseStore


def _free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def spawn_probe_server_peer(ctx):
    """Peer falso del servidor nuevo, misma orden que PartContext._spawn_peers."""
    fake_peer = Path(f03_common.__file__).resolve().with_name("fake_peer.py")
    cfg_path = ctx.profiles["server"] / "dsbx_qa.json"
    log_path = ctx.peer_logs["server"]
    log_fh = log_path.open("a", encoding="utf-8", newline="\n")
    ctx._log_handles.append(log_fh)
    cmd = [sys.executable, str(fake_peer), "--peer", "server",
           "--config", str(cfg_path), "--rpc-port", str(_free_udp_port())]
    if getattr(ctx, "git_head", None):
        cmd.extend(["--git-head", str(ctx.git_head)])
    elif getattr(ctx, "expected_stamp", None):
        cmd.extend(["--probe-ver", "dsbx-qa1+%s" % ctx.expected_stamp])
    fault = getattr(ctx.args, "fault", None)
    if fault:
        cmd.extend(["--fault", str(fault)])
    clock_offset = float(getattr(ctx.args, "clock_offset_ms", 0.0) or 0.0)
    if clock_offset:
        cmd.extend(["--clock-offset-ms", str(clock_offset)])
    proc = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT)
    ctx.procs["server"] = proc
    ctx.fake_peer_pids["server"] = proc.pid
    return proc


def _stop_proc(proc, timeout_s=5.0):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout_s)


def make_seco_restart_hook(ctx, seco_state):
    def hook(action):
        if action == "stop":
            _stop_proc(seco_state.get("fake"))
            _stop_proc(ctx.procs.get("server"))
        elif action == "start":
            seco_state["fake"] = subprocess.Popen(
                [sys.executable, "-B",
                 str(DEV_ROOT / "app" / "tests" / "fake_mod.py"),
                 "--config", str(seco_state["cfg_path"]), "--world"],
                cwd=str(DEV_ROOT), stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT)
            spawn_probe_server_peer(ctx)
        else:
            raise ValueError("accion de reinicio desconocida: %s" % action)
    return hook


def make_real_restart_hook(server_ctl, *, powershell="powershell",
                           server_exe="", server_args="", working_dir="",
                           profile_dir="", state=None,
                           client_exe="", client_args="",
                           client_working_dir="", client_state=None,
                           cliente="lanzar", build="diag",
                           client_profile_dir=""):
    """Reinicio real: el ayudante PS para (StopBoth cliente+servidor) y
    arranca servidor y cliente por WMI con la misma linea de ordenes.

    state/client_state: dicts mutables con pid/start_time vigentes; el
    ayudante devuelve los PID y las horas nuevos en JSON. Con cliente
    'operador' no se arranca cliente: lo abre la Sesion de pruebas.
    """
    st = state if state is not None else {"pid": 0, "start_time": ""}
    cst = client_state if client_state is not None else {"pid": 0, "start_time": ""}

    def hook(action):
        if action not in ("stop", "start"):
            raise ValueError("accion de reinicio desconocida: %s" % action)
        cmd = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", str(server_ctl), "-Action", action,
               "-ServerExe", str(server_exe), "-ServerArgs", str(server_args),
               "-WorkingDir", str(working_dir), "-ProfileDir", str(profile_dir),
               "-ServerPid", str(st.get("pid") or 0),
               "-ServerStart", str(st.get("start_time") or ""),
               "-ClientPid", str(cst.get("pid") or 0),
               "-ClientStart", str(cst.get("start_time") or "")]
        if cliente == "lanzar":
            cmd += ["-ClientExe", str(client_exe), "-ClientArgs", str(client_args),
                    "-ClientWorkingDir", str(client_working_dir),
                    "-Build", str(build or "diag"),
                    "-ClientProfileDir", str(client_profile_dir or "")]
            m_mod = re.search(r'-mod=([^"]+)', str(client_args or ""))
            if m_mod:
                cmd += ["-ClientMods", m_mod.group(1)]
        out = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=300)
        if out.returncode != 0:
            raise RuntimeError("f2p_server_ctl fallo (rc=%s): %s"
                               % (out.returncode, out.stderr or out.stdout))
        if action == "stop":
            return
        found = False
        for line in (out.stdout or "").splitlines():
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict) or "pid" not in data:
                continue
            if data.get("role") == "client":
                cst["pid"] = int(data.get("pid") or 0)
                cst["start_time"] = str(data.get("start_time") or "")
            else:
                st["pid"] = int(data.get("pid") or 0)
                st["start_time"] = str(data.get("start_time") or "")
                found = True
        if not found:
            raise RuntimeError("f2p_server_ctl no devolvio PID/hora")

    return hook


def mods_line(work_root):
    """<mods> con los dos mods y rutas completas (F2 ronda 2b)."""
    root = str(work_root or "").replace("/", "\\").rstrip("\\")
    return "%s\\pbo\\@DayZSandbox;%s\\pbo\\@DayZSandbox_QA" % (root, root)


def client_launch(build, dayz_dir="", mods="", client_profile=""):
    """(exe, prefijo) del cliente segun build (R2c-1): en diag el mismo
    DayZDiag_x64 sin -server; en retail DayZ_BE con 0 1 1 -exe DayZ_x64
    y adopcion del DayZ_x64 por procedencia (F1b R14/R16)."""
    d = str(dayz_dir or "").replace("/", "\\").rstrip("\\")
    if str(build) == "retail":
        exe = ("%s\\DayZ_BE.exe" % d) if d else "DayZ_BE.exe"
        args = ("0 1 1 -exe DayZ_x64.exe \"-mod=%s\" -connect=127.0.0.1 "
                "-port=2302 \"-profiles=%s\" -name=DSBXQA -window "
                "-x=1280 -y=720 -noPause" % (mods, client_profile))
        return exe, args, True
    exe = ("%s\\DayZDiag_x64.exe" % d) if d else "DayZDiag_x64.exe"
    args = ("\"-mod=%s\" -connect=127.0.0.1 -port=2302 "
            "\"-profiles=%s\" -name=DSBXQA -window -x=1280 -y=720 -noPause"
            % (mods, client_profile))
    return exe, args, False


def check_package_manifest(package_dir):
    """Problemas del paquete contra su manifest.json (R2c-3/4): cada
    fichero listado tiene que existir y casar por sha256. Sin repo git."""
    root = Path(package_dir)
    problems = []
    mpath = root / "manifest.json"
    if not mpath.is_file():
        return ["falta manifest.json en %s" % root]
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["manifest.json ilegible: %s" % exc]
    for row in manifest.get("files") or []:
        name = str(row.get("file") or "")
        expected = row.get("sha256")
        target = root / name.replace("/", "\\")
        if row.get("missing") or not expected:
            problems.append("sin sha256 en manifest: %s" % name)
        elif not target.is_file():
            problems.append("falta el fichero del paquete: %s" % name)
        elif sha256_file(target) != str(expected).lower():
            problems.append("sha256 no casa: %s" % name)
    for pbo_name in ("pbo/@DayZSandbox/addons/DayZSandbox.pbo",
                     "pbo/@DayZSandbox_QA/addons/DayZSandbox_QA.pbo"):
        if not (root / pbo_name.replace("/", "\\")).is_file():
            problems.append("falta el PBO del paquete: %s" % pbo_name)
    return problems


def dry_run_orders(*, maquina="willy", cliente="lanzar", dayz_dir="",
                   dayz_server_dir="", python_exe="python", work_root="",
                   results_dir="", server_exe="", client_exe="", mission_b1="",
                   build="diag", package_dir="", humo=False):
    wr = str(work_root or "").replace("/", "\\").rstrip("\\")
    if str(build) == "retail":
        srv = server_exe or ((str(dayz_server_dir).replace("/", "\\").rstrip("\\") + "\\DayZServer_x64.exe") if dayz_server_dir else "DayZServer_x64.exe")
    else:
        srv = server_exe or ((str(dayz_dir).replace("/", "\\").rstrip("\\") + "\\DayZDiag_x64.exe") if dayz_dir else "DayZDiag_x64.exe")
    pbo_root = str(package_dir or "").replace("/", "\\").rstrip("\\") if (maquina == "portatil" and package_dir) else wr
    mods = mods_line(pbo_root)
    cli_exe, cli_args, adopt = client_launch(build, dayz_dir=dayz_dir, mods=mods,
                                             client_profile="%s\\profile-client" % wr)
    if client_exe:
        cli_exe = client_exe
    mission_dir = "%s\\mission" % wr
    server_cfg = "%s\\server\\serverDZ.cfg" % mission_dir
    mission = "%s\\mpmissions\\dayzOffline.chernarusplus" % mission_dir
    orders = []
    if maquina == "portatil":
        pkg = str(package_dir or "<paquete>").replace("/", "\\").rstrip("\\")
        orders.append("comprobacion del paquete: sha256 de cada fichero contra %s\\manifest.json; si no casa, no se lanza" % pkg)
        orders.append("DayZ ajenos: cualquier DayZ* vivo (DayZDiag_x64, DayZ_x64, DayZServer_x64, DayZ_BE) para el lanzamiento y se dice en el log")
        orders.append("PBO del paquete: %s\\pbo\\@DayZSandbox\\addons\\DayZSandbox.pbo y %s\\pbo\\@DayZSandbox_QA\\addons\\DayZSandbox_QA.pbo comprobados por manifest; no se construye nada" % (pkg, pkg))
    orders += [
        "mision desechable: copia nueva de la b1 en %s en cada intento; -mission y -config salen de la copia" % mission_dir,
        "WMI servidor: Invoke-CimMethod Win32_Process Create \"%s -server \\\"-config=%s\\\" \\\"-profiles=%s\\profile-server\\\" \\\"-mission=%s\\\" \\\"-mod=%s\\\" -port=2302 -dologs -adminlog -freezecheck\""
        % (srv, server_cfg, wr, mission, mods),
        "WMI cliente: Invoke-CimMethod Win32_Process Create \"%s %s\""
        % (cli_exe, cli_args),
        "reinicio: f2p_server_ctl.ps1 -Action restart -Build %s -ServerPid <pid> -ServerStart <iso> -ClientPid <pid> -ClientStart <iso> (StopBoth: WM_CLOSE, .mdmp, CrashReporter, puertos)" % build,
        "scp paquete: scp -r %s/paquete/* usuario@portatil:C:/dsbx-m1/" % work_root,
        "ssh orden: ssh usuario@portatil \"powershell -NoProfile -ExecutionPolicy Bypass -File C:/dsbx-m1/run_f2p_partida.ps1 -Maquina portatil\"",
        "scp vuelta: scp -r usuario@portatil:C:/dsbx-m1/resultados/* %s/" % (results_dir or work_root),
    ]
    if adopt:
        orders.append("cliente retail: el PID propio es el del DayZ_x64 adoptado por procedencia (cadena BattlEye o RPT del perfil propio), con su hora de arranque")
    if humo:
        orders.append("humo: comprobacion del paquete y de los ajenos, arranque con la mision copiada, hello del producto, hello de la sonda, hello del peer cliente y UID por per_status")
        orders.append("humo: ciclo de reinicio como el de F4 (parar los dos, drenar, arrancar los dos, mismos saludos, mismo UID) y cierre por WM_CLOSE de los PID propios")
        orders.append("humo: escribe resultados/humo.json con cada paso y copia los logs a resultados/; sin oraculo ni partida")
    if maquina == "portatil":
        orders.append("evidencia: por defecto bajo -ResultsDir (resultados/run/manifest.json), no bajo el repo")
    if maquina == "portatil" and cliente == "operador":
        orders.append("cliente operador: aviso en resultados/ESPERA_OPERADOR.txt; esperar hello del peer cliente con tope")
    return orders


LAST_SECRETS = ()


def write_product_peer_configs(work, peer_key, bridge_port, profiles):
    """dsbx_peer.json del mod de producto en cada perfil, con `app/tools/peer_config.py` por subproceso.

    El fichero de entrada (peer_key y bridge_port del tap) queda en la carpeta de trabajo, fuera de la evidencia.
    Lanza RuntimeError si falta un perfil o si la herramienta falla: sin la config, el producto no saluda.
    """
    cfg_path = Path(work) / "peer_config_in.json"
    cfg_path.write_text(json.dumps({"peer_key": peer_key, "bridge_port": int(bridge_port)}),
                        encoding="utf-8", newline="\n")
    tool = DEV_ROOT / "app" / "tools" / "peer_config.py"
    for profile in profiles:
        if not profile:
            raise RuntimeError("falta el perfil para dsbx_peer.json")
        Path(profile).mkdir(parents=True, exist_ok=True)
        out = subprocess.run([sys.executable, "-B", str(tool), "--config", str(cfg_path),
                              "--profile", str(profile)], cwd=str(DEV_ROOT),
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
        if out.returncode != 0 or not (Path(profile) / "dsbx_peer.json").is_file():
            raise RuntimeError("peer_config fallo para %s (rc=%s)" % (profile, out.returncode))


_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def globals_a_cero(text):
    """True si globals.xml deja a 0 ZombieMaxCount y AnimalMaxCount, con `type` u otros atributos en medio
    (<var name="ZombieMaxCount" type="0" value="0"/>)."""
    def cero(name):
        m = re.search(r'name="%s"[^>]*?value="(\d+)"' % name, text)
        return m is not None and m.group(1) == "0"
    return cero("ZombieMaxCount") and cero("AnimalMaxCount")


def _udp_port_in_netstat(text, port):
    """True si alguna fila UDP de `netstat -ano -p UDP` tiene `port` como puerto local."""
    suffix = ":%d" % int(port)
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].upper() == "UDP" and parts[1].endswith(suffix):
            return True
    return False


def _udp_port_free(port):
    """True si ningún socket UDP local tiene `port`, leído de la tabla de netstat sin atar nada.

    Antes ataba un socket UDP en 0.0.0.0:port, y atar en todas las interfaces hace saltar la alerta del Firewall
    de Windows para el python del runner (portátil, 24-nov). Si netstat falla, da False: la comprobación falla
    cerrada.
    """
    try:
        r = subprocess.run(["netstat", "-ano", "-p", "UDP"], capture_output=True, encoding="utf-8",
                           errors="replace", timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    if r.returncode != 0:
        return False
    return not _udp_port_in_netstat(r.stdout, port)


def run_comprobacion(*, work_root, results_dir, server_profile, client_profile, probe_pbo,
                     product_pbo, server_exe="", client_exe="", mission_dir="", package_dir="",
                     ports=(2302, 2304)):
    """Comprobación previa del portátil (24-nov): el camino real hasta justo antes de abrir DayZ.

    No arranca DayZ. Arranca el backend y el tap, escribe `dsbx_peer.json` en los dos perfiles, lo valida y
    lo retira, y para el backend y el tap. Escribe `<results_dir>/comprobacion.json` y devuelve (ok, checks).
    """
    checks = []

    def add(cid, ok, detalle=""):
        checks.append({"id": cid, "ok": bool(ok), "detalle": str(detalle)[:400]})
        return bool(ok)

    chk = check_oracle()
    add("oraculo", chk.get("ok"), chk.get("problems") or ORACLE_COMMIT)
    head, dirty = "", None
    try:
        head = subprocess.run(["git", "-c", "core.autocrlf=false", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                              capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-c", "core.autocrlf=false", "status", "--porcelain"], cwd=str(REPO_ROOT),
                               capture_output=True, text=True, check=True).stdout.strip()
        add("git_limpio", dirty == "", "HEAD %s%s" % (head, "" if dirty == "" else "; sucio: " + dirty[:200]))
    except Exception as exc:
        add("git_limpio", False, exc)
    pbos = {"sonda": probe_pbo, "producto": product_pbo}
    for nombre, path in pbos.items():
        p = Path(path) if path else None
        add("pbo_" + nombre, p is not None and p.is_file() and p.stat().st_size > 0,
            "%s sha256=%s" % (path, sha256_file(p) if p is not None and p.is_file() else "-"))
    pkg_json = Path(package_dir) / "json" if package_dir else None
    for nombre, fich, path in (("sonda", "build_pbo.json", probe_pbo), ("producto", "build_core_pbo.json", product_pbo)):
        if pkg_json is None or not (pkg_json / fich).is_file():
            add("procedencia_" + nombre, False, "sin %s en el paquete" % fich)
            continue
        meta = json.loads((pkg_json / fich).read_text(encoding="utf-8"))
        real = sha256_file(path) if path and Path(path).is_file() else ""
        add("procedencia_" + nombre, meta.get("pbo_sha256") == real and meta.get("ok") is not False,
            "build %s pbo_sha256=%s, el del paquete=%s" % (meta.get("git_head"), meta.get("pbo_sha256"), real))
        if nombre == "sonda":
            try:
                esperado = f03_common.compute_probe_stamp_at_commit(head, repo_root=REPO_ROOT)
            except Exception as exc:
                esperado = "error: %s" % exc
            add("sello_sonda", meta.get("stamp") == esperado,
                "PBO %s, esperado en HEAD %s" % (meta.get("stamp"), esperado))
    for nombre, path in (("servidor", server_exe), ("cliente", client_exe)):
        add("exe_" + nombre, bool(path) and Path(path).is_file(), path)
    if mission_dir:
        md = Path(mission_dir)
        cfg_ok = (md / "server" / "serverDZ.cfg").is_file()
        mis_ok = (md / "mpmissions" / "dayzOffline.chernarusplus").is_dir()
        glob = list(md.rglob("globals.xml"))
        ceros = bool(glob) and all(globals_a_cero(g.read_text(encoding="utf-8-sig", errors="replace"))
                                   for g in glob[:1])
        add("mision", cfg_ok and mis_ok and ceros,
            "serverDZ.cfg=%s mision=%s globals_a_cero=%s" % (cfg_ok, mis_ok, ceros))
    for port in ports:
        add("puerto_udp_%d" % port, _udp_port_free(port), "libre" if _udp_port_free(port) else "ocupado")
    work = Path(work_root)
    work.mkdir(parents=True, exist_ok=True)
    backend = tap = None
    try:
        backend = BackendProc(work / "backend_comprobacion", scene1_doc(), lambda: 0.0, OrderLog(lambda: 0.0))
        backend.start()
        tap = Tap(backend.bridge_port, clock=lambda: 0.0).start()
        add("backend_y_tap", True, "bridge %s, tap %s" % (backend.bridge_port, tap.port))
        profiles = (server_profile, client_profile)
        write_product_peer_configs(work, backend.peer_key, tap.port, profiles)
        for prof in profiles:
            f = Path(prof) / "dsbx_peer.json"
            cfg = json.loads(f.read_text(encoding="utf-8"))
            ok = cfg.get("url") == "http://127.0.0.1:%d/" % tap.port and cfg.get("key") == backend.peer_key \
                and bool(_KEY_RE.match(str(cfg.get("key") or "")))
            add("dsbx_peer_" + Path(prof).name, ok, "%s url=%s" % (f, cfg.get("url")))
            f.unlink()  # la escribe de nuevo la partida, con su backend y su tap
    except Exception as exc:
        add("backend_y_tap", False, exc)
    finally:
        if tap is not None:
            try:
                tap.stop()
            except Exception:
                pass
        if backend is not None:
            try:
                backend.stop()
            except Exception:
                pass
    todo_ok = all(c["ok"] for c in checks)
    out = Path(results_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "comprobacion.json").write_text(
        json.dumps({"ok": todo_ok, "head": head, "checks": checks}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    return todo_ok, checks


def run_campaign(*, build="offline", evidence_base=None, mode="seco",
                 server_profile=None, client_profile=None,
                 witness_follow_ticks=3, storage_id=None, work_root=None,
                 hello_timeout_s=60.0, restart_hook=None, director_uid="",
                 director_timeout_ms=30000, cliente="lanzar",
                 server_ctl="", server_state=None, client_state=None,
                 server_exe="", server_args="", working_dir="",
                 client_exe="", client_args="", client_working_dir="",
                 probe_pbo="", product_pbo=""):
    global LAST_SECRETS
    chk = check_oracle()
    if not chk.get("ok"):
        raise RuntimeError("oraculo no verificado: %s" % (chk.get("problems"),))
    utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if evidence_base is None:
        evidence_base = DEV_ROOT / "evidence" / "m1" / "F2P" / ("%s-%s" % (build, utc))
    base = Path(evidence_base)
    run_dir = base / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "samples").mkdir(parents=True, exist_ok=True)
    work = Path(work_root) if work_root else base.parent / (base.name + "-work")
    work.mkdir(parents=True, exist_ok=True)
    if build == "offline":
        pbo_path = work / "probe.pbo"
        prod_path = work / "product.pbo"
        if not pbo_path.is_file():
            pbo_path.write_bytes(b"PBO-RELLENO-SONDA\n")
        if not prod_path.is_file():
            prod_path.write_bytes(b"PBO-RELLENO-PRODUCTO\n")
    else:
        # Modo real (portátil, 24-nov): los PBO del paquete o los construidos, por --pbo y --product-pbo.
        # Sin ellos no se arranca nada (antes se buscaba <work>\probe.pbo, que no existe, tras abrir la parte).
        pbo_path = Path(probe_pbo) if probe_pbo else None
        prod_path = Path(product_pbo) if product_pbo else None
        if pbo_path is None or not pbo_path.is_file():
            raise RuntimeError("falta el PBO de la sonda (--pbo): %s" % (probe_pbo or "<vacio>",))
        if prod_path is None or not prod_path.is_file():
            raise RuntimeError("falta el PBO del producto (--product-pbo): %s" % (product_pbo or "<vacio>",))
    args = argparse.Namespace(
        build=build, both=True, ttl_ms=gate_core.DEFAULT_TTL_MS,
        retry_ms=gate_core.DEFAULT_RETRY_MS, lease_ms=gate_core.DEFAULT_LEASE_MS,
        hold_ms=gate_core.DEFAULT_HOLD_MS, seed=gate_core.DEFAULT_SEED,
        peer_timeout=None, pbo=str(pbo_path), product_pbo=str(prod_path),
        oracle_commit=ORACLE_COMMIT, fault=None,
        server_profile=str(server_profile) if server_profile else None,
        client_profile=str(client_profile) if client_profile else None,
    )
    ctx = f03_common.PartContext(base_dir=base, part_name="run", spike_id="F2P",
                                 args=args, argv=[], repo_root=REPO_ROOT,
                                 spawn_offline_peers=(build == "offline"))
    ctx.open()
    notes = []
    if ctx.startup_reason is not None:
        notes.append("startup_reason=%s" % ctx.startup_reason)
    clock = ctx.now_h_ms
    order_log = OrderLog(clock)
    files = oracle_files_sha()
    order_log.add("oracle.frozen", {"commit": ORACLE_COMMIT, "files": files})
    order_log.add("pbo.stamp", {"pbo_sha256": ctx.pbo_sha256 or sha256_file(pbo_path),
                                "product_pbo_sha256": ctx.product_pbo_sha256 or sha256_file(prod_path)})
    tap_writer = JsonlWriter(run_dir / "samples" / "bridge_tap.jsonl")
    backend_writer = JsonlWriter(run_dir / "samples" / "backend.jsonl")
    holder = {}
    tap = None
    fake_mod_proc = None
    seco_state = {"fake": None, "cfg_path": None}
    fase_store = FaseStore(work)
    entradas_partida = {"oracle_commit": ORACLE_COMMIT,
                        "oracle_files": files,
                        "storage_id": storage_id or ""}
    fase_store.mark("partida", "en_curso", entradas=entradas_partida)
    campaign_ref = {}
    parts = []
    storage_path = str(work / "storage_1")
    sid = storage_id or ("storage_1-%s" % utc)
    try:
        backend = BackendProc(work / "backend", scene1_doc(), clock, order_log)
        holder["backend"] = backend
        backend.start()
        tap = Tap(backend.bridge_port, clock=clock, sink=tap_writer.write).start()
        LAST_SECRETS = (backend.human_key, backend.ai_key, backend.peer_key)
        if build == "offline":
            cfg_path = work / "fake_mod.json"
            cfg_path.write_text(json.dumps({"peer_key": backend.peer_key,
                                            "bridge_port": tap.port}),
                                encoding="utf-8", newline="\n")
            fake_mod_proc = subprocess.Popen(
                [sys.executable, "-B", str(DEV_ROOT / "app" / "tests" / "fake_mod.py"),
                 "--config", str(cfg_path), "--world"],
                cwd=str(DEV_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            seco_state["fake"] = fake_mod_proc
            seco_state["cfg_path"] = cfg_path
            time.sleep(1.0)
        else:
            # Modo real (24-nov, segundo intento del portátil): el mod de producto lee
            # `$profile:dsbx_peer.json` (DSBX_Peer.c:512-516) y, sin él, no saluda nunca. Se escribe aquí,
            # apuntando al tap, con la herramienta del producto por subproceso (R-64, como f1bp_live.py:596-606);
            # el mod reintenta la lectura (DSBX_Peer.c:1460-1490), así que vale aunque DayZ ya esté arrancado.
            write_product_peer_configs(work, backend.peer_key, tap.port,
                                       (server_profile, client_profile))
        eff_restart_hook = restart_hook
        if eff_restart_hook is None and build == "offline":
            eff_restart_hook = make_seco_restart_hook(ctx, seco_state)
        if eff_restart_hook is None and mode in ("diag", "retail") and server_ctl:
            eff_restart_hook = make_real_restart_hook(
                server_ctl, server_exe=server_exe, server_args=server_args,
                working_dir=working_dir, profile_dir=str(server_profile or ""),
                state=server_state, client_exe=client_exe,
                client_args=client_args, client_working_dir=client_working_dir,
                client_state=client_state, cliente=cliente,
                build=(build if build in ("diag", "retail") else mode),
                client_profile_dir=str(client_profile or ""))
        campaign = Campaign(ctx, holder, tap, order_log, mode=mode,
                            hello_timeout_s=hello_timeout_s,
                            restart_hook=eff_restart_hook,
                            director_uid=director_uid,
                            director_timeout_ms=director_timeout_ms,
                            on_part=fase_store.mark_part,
                            cliente=cliente,
                            esperar_cliente=(mode in ("diag", "retail")))
        campaign_ref["campaign"] = campaign
        parts = campaign.run()
        notes.extend(campaign.notes)
        if campaign.inconcluso:
            fase_store.mark("partida", "fallida", entradas=entradas_partida)
        else:
            fase_store.mark("partida", "ok", entradas=entradas_partida,
                            salidas={"evidence": str(base)})
    finally:
        # F3: en seco sigue vacio; en diag/retail, DSBX_SCENE_DEL de los
        # script_*.log del perfil del servidor de cada vida, con el ancla
        # de R-12 tomada en un mismo instante.
        if mode in ("diag", "retail"):
            prof = server_profile
            if not prof:
                try:
                    prof = ctx.profiles.get("server")
                except Exception:
                    prof = None
            anchor_t_ms = clock()
            anchor_wall_s = _local_wall_seconds()
            scene_rows = collect_scene_del_from_profile(
                prof, anchor_t_ms, anchor_wall_s)
        else:
            scene_rows = collect_scene_del([], clock(), _local_wall_seconds())
        with (run_dir / "samples" / "scene_del.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
            for row in scene_rows:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        for _proc in {id(p): p for p in (fake_mod_proc, seco_state.get("fake")) if p is not None}.values():
            if _proc.poll() is None:
                _proc.terminate()
                try:
                    _proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    _proc.kill()
        if tap is not None:
            tap.stop()
        if holder.get("backend") is not None:
            try:
                holder["backend"].stop()
            except Exception:
                pass
        for row in order_log.rows:
            backend_writer.write(row)
        backend_writer.close()
        tap_writer.close()
        ctx.close()
        try:
            (work / "f2p_pids_final.json").write_text(
                json.dumps({"server": dict(server_state or {}),
                            "client": dict(client_state or {})},
                           ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        except OSError:
            pass
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not parts:
            now = clock()
            step = 1000.0
            parts = [(name, now + i * step, now + (i + 1) * step - 1.0)
                     for i, name in enumerate(PART_ORDER)]
        manifest["f2p"] = build_f2p_block(
            oracle_commit=ORACLE_COMMIT, oracle_files=files,
            storage_path=storage_path, storage_id=sid, parts=parts,
            witness_follow_ticks=witness_follow_ticks)
        manifest_path.write_bytes(
            (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
        _camp = campaign_ref.get("campaign")
        report = {"mode": mode, "build": build, "notes": notes,
                  "inconcluso": getattr(_camp, "inconcluso", "") if _camp else "",
                  "director_uid_presente": bool(getattr(_camp, "director_uid", "")) if _camp else False,
                  "current_epoch": getattr(_camp, "current_epoch", "") if _camp else "",
                  "mdmp": [], "reconciliation": "ver tap: state.read tras reinicios",
                  "a3_hijos_propios": "N/A en M1",
                  "metrics": {"delete_confirm_max_ms": None}}
        (run_dir / "informe.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
    return base, {"parts": parts, "notes": notes, "storage_id": sid}


def _utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_humo_real_steps(campaign, steps=None):
    """Pasos 3-4 del humo real (R2c-7): saludos de la primera vida, UID
    por per_status y un ciclo de reinicio como el de F4 con el mismo
    UID. Devuelve la lista de pasos; lanza si alguno falla ya anotado.
    `steps` es la lista donde se anotan, para que quien llama conserve el
    paso que falla aunque salte la excepcion (montaje retail, t4-e3d0978)."""
    steps = [] if steps is None else steps

    def paso(nombre, fn):
        t0 = time.monotonic()
        row = {"paso": nombre, "estado": "fallo", "inicio": _utc_iso(),
               "fin": "", "duracion_s": 0.0, "motivo": ""}
        try:
            out = fn()
            row["estado"] = "ok"
            row["motivo"] = str(out or "")
        except Exception as exc:
            row["motivo"] = str(exc)
            steps.append(row)
            raise
        finally:
            row["fin"] = _utc_iso()
            row["duracion_s"] = round(time.monotonic() - t0, 3)
            if row not in steps:
                steps.append(row)
        return row

    paso("hello_producto_y_sonda_primera_vida",
         lambda: "epoch=%s" % campaign._wait_first_life().get("epoch", ""))
    paso("hello_peer_cliente_primera_vida",
         lambda: "t_ms=%s" % wait_client_hello(
             campaign.ctx, None, timeout_s=campaign.hello_timeout_s)["t_ms"])
    uid_box = {}

    def _uid():
        uid = probe_director_uid(campaign.ctx,
                                 timeout_ms=campaign.director_timeout_ms)
        if not uid:
            # Como la partida (_run_inner): esta sonda no da players_n ni el UID del director, y el censo va sin
            # director_uid. Antes el humo lo daba por fallo con un mensaje que no era (montaje retail, t4-d38c552).
            return "per_status sin players_n (sonda sin UID del director): censo sin director_uid"
        campaign.director_uid = uid
        uid_box["uid"] = uid
        return "uid obtenido por per_status"

    paso("uid_por_per_status", _uid)

    def _restart():
        before = uid_box.get("uid", "")
        epoch = campaign._restart_server()
        if before and campaign.director_uid != before:
            raise ServerHelloTimeout("el cliente volvio con otro UID tras el reinicio")
        return "epoch=%s uid=mismo" % epoch

    paso("reinicio_f4_saludos_y_mismo_uid", _restart)
    return steps


def write_humo_pasos(path, steps):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps({"pasos": list(steps),
                    "ok": all(s.get("estado") == "ok" for s in steps)},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n")


def run_humo_real(*, evidence_base, work_root=None, build="diag",
                  server_profile=None, client_profile=None,
                  hello_timeout_s=120.0, director_timeout_ms=30000,
                  server_ctl="", server_state=None, client_state=None,
                  server_exe="", server_args="", working_dir="",
                  client_exe="", client_args="", client_working_dir=""):
    """Humo real sin oraculo ni partida (R2c-7): backend+tap+sonda con
    los saludos y el reinicio de F4. Escribe humo_pasos.json bajo la
    base (ResultsDir) y f2p_pids_final.json en el work para el cierre
    por WM_CLOSE del lanzador. Devuelve (base, pasos)."""
    base = Path(evidence_base)
    base.mkdir(parents=True, exist_ok=True)
    work = Path(work_root) if work_root else base / "humo-work"
    work.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(
        build=build, both=True, ttl_ms=gate_core.DEFAULT_TTL_MS,
        retry_ms=gate_core.DEFAULT_RETRY_MS, lease_ms=gate_core.DEFAULT_LEASE_MS,
        hold_ms=gate_core.DEFAULT_HOLD_MS, seed=gate_core.DEFAULT_SEED,
        peer_timeout=None, pbo=None, product_pbo=None,
        oracle_commit=None, fault=None,
        server_profile=str(server_profile) if server_profile else None,
        client_profile=str(client_profile) if client_profile else None)
    ctx = f03_common.PartContext(base_dir=work / "humo_ctx", part_name="run",
                                 spike_id="F2P", args=args, argv=[],
                                 repo_root=REPO_ROOT, spawn_offline_peers=False)
    steps = []
    backend = None
    tap = None
    try:
        ctx.open()
        clock = ctx.now_h_ms
        order_log = OrderLog(clock)
        holder = {}
        backend = BackendProc(work / "backend", scene1_doc(), clock, order_log)
        holder["backend"] = backend
        backend.start()
        tap = Tap(backend.bridge_port, clock=clock).start()
        write_product_peer_configs(work, backend.peer_key, tap.port, (server_profile, client_profile))
        hook = make_real_restart_hook(
            server_ctl, server_exe=server_exe, server_args=server_args,
            working_dir=working_dir, profile_dir=str(server_profile or ""),
            state=server_state, client_exe=client_exe,
            client_args=client_args, client_working_dir=client_working_dir,
            client_state=client_state, cliente="lanzar",
            build=build, client_profile_dir=str(client_profile or ""))
        campaign = Campaign(ctx, holder, tap, order_log, mode=build,
                            hello_timeout_s=hello_timeout_s,
                            restart_hook=hook, director_timeout_ms=director_timeout_ms,
                            cliente="lanzar", esperar_cliente=True)
        run_humo_real_steps(campaign, steps)
    finally:
        write_humo_pasos(base / "humo_pasos.json", steps)
        try:
            (work / "f2p_pids_final.json").write_text(
                json.dumps({"server": dict(server_state or {}),
                            "client": dict(client_state or {})},
                           ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8", newline="\n")
        except OSError:
            pass
        if tap is not None:
            tap.stop()
        if backend is not None:
            try:
                backend.stop()
            except Exception:
                pass
        try:
            ctx.close()
        except Exception:
            pass
    return base, steps


LEASE_PROBE_AFTER_PAGES = 20
LEASE_PROBE_DELAY_MS = 6000.0
LEASE_PROBE_CATALOG_TIMEOUT_S = 60.0


def _is_server_hello_body(body):
    return isinstance(body, dict) and (body.get("peer") == "server" or "modset" in body)


def lease_probe_verdict(records, injections):
    """Veredicto de la sonda de lease sobre los registros del tap (T4 917bc73: catalogo tras perder el lease).

    PASA si, despues del retraso inyectado, el servidor vuelve a saludar y el backend contesta `complete: true`
    a una pagina de catalogo posterior a su ultimo saludo; FALLA si vuelve a saludar y el catalogo no se completa;
    INCONCLUSO si no hubo retraso o no hubo saludo nuevo (no se perdio el lease).
    """
    fault = next((i for i in injections or [] if i.get("stimulus") == "lease_delay"), None)
    if fault is None:
        return {"veredicto": "INCONCLUSO", "motivo": "sin_retraso_inyectado"}
    reqs = {r.get("req_id"): r for r in records or [] if r.get("dir") == "req"}
    hellos = []
    for r in records or []:
        if r.get("dir") != "resp" or r.get("path") != "/hello" or not isinstance(r.get("body"), dict):
            continue
        q = reqs.get(r.get("req_id"))
        if q is None or not _is_server_hello_body(q.get("body")):
            continue
        hellos.append({"t_ms": float(r["t_ms"]), "conn": r["body"].get("conn"),
                       "session": r["body"].get("session")})
    after = [h for h in hellos if h["t_ms"] > float(fault["t_ms"])]
    if not after:
        return {"veredicto": "INCONCLUSO", "motivo": "sin_saludo_nuevo_tras_el_retraso",
                "hellos": hellos, "fault": fault}
    last = after[-1]
    cats = [r for r in records or [] if r.get("dir") == "resp" and r.get("path") == "/catalog"
            and float(r["t_ms"]) > last["t_ms"] and isinstance(r.get("body"), dict)]
    done = [r for r in cats if r["body"].get("complete") is True]
    if done:
        return {"veredicto": "PASA", "motivo": "catalogo_completo_tras_saludo_nuevo", "hellos": hellos,
                "fault": fault, "catalog_complete_t_ms": float(done[0]["t_ms"])}
    have = (cats[-1]["body"].get("have"), cats[-1]["body"].get("pages")) if cats else None
    return {"veredicto": "FALLA", "motivo": "catalogo_incompleto_tras_saludo_nuevo", "hellos": hellos,
            "fault": fault, "ultimo_have_pages": have}


def _stop_lease_server(server_ctl, *, server_exe="", server_args="", working_dir="", profile_dir="",
                       state=None, build="diag"):
    """Sonda de lease: para el servidor propio con `f2p_server_ctl.ps1 -Action stop` (StopBoth sin cliente: WM_CLOSE,
    CrashReporter sin enviar y puertos), como en los reinicios de la partida. Devuelve el resultado en texto."""
    if not server_ctl:
        return "sin server_ctl: lo cierra el lanzador"
    try:
        make_real_restart_hook(server_ctl, server_exe=server_exe, server_args=server_args,
                               working_dir=working_dir, profile_dir=str(profile_dir or ""),
                               state=state, cliente="operador", build=build)("stop")
        return "ok"
    except Exception as exc:
        return "fallo: %s" % exc


def run_lease_probe(*, evidence_base, work_root=None, server_profile=None, hello_timeout_s=120.0,
                    after_pages=LEASE_PROBE_AFTER_PAGES, delay_ms=LEASE_PROBE_DELAY_MS,
                    catalog_timeout_s=LEASE_PROBE_CATALOG_TIMEOUT_S, product_pbo="",
                    server_ctl="", server_state=None, server_exe="", server_args="", working_dir="",
                    build="diag"):
    """Sonda de lease, solo servidor (T4 917bc73): backend y tap con el retraso del poll del servidor a mitad
    del catalogo. Escribe <base>/sonda_lease.json y <base>/samples/bridge_tap.jsonl. Devuelve 0 si PASA, 1 si
    FALLA y 2 si INCONCLUSO. El servidor lo arranca y lo cierra el lanzador (-SondaLease)."""
    base = Path(evidence_base)
    (base / "samples").mkdir(parents=True, exist_ok=True)
    work = Path(work_root) if work_root else base / "lease-work"
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    def clock():
        return (time.monotonic() - t0) * 1000.0

    writer = JsonlWriter(base / "samples" / "bridge_tap.jsonl")
    backend = None
    tap = None
    out = {"veredicto": "INCONCLUSO", "motivo": "sin_empezar"}
    try:
        backend = BackendProc(work / "backend", scene1_doc(), clock, OrderLog(clock))
        backend.start()
        tap = Tap(backend.bridge_port, clock=clock, sink=writer.write).start()
        tap.delay_server_poll_once(after_catalog_pages=after_pages, delay_ms=delay_ms)
        write_product_peer_configs(work, backend.peer_key, tap.port, (server_profile,))
        deadline = time.monotonic() + float(hello_timeout_s)
        fault_seen_at = None
        while True:
            out = lease_probe_verdict(tap.records, tap.injections)
            if out["veredicto"] == "PASA":
                break
            now = time.monotonic()
            if out.get("motivo") == "sin_retraso_inyectado":
                if now > deadline:
                    out["motivo"] = "sin_retraso_inyectado: el servidor no llego a %d paginas de catalogo" \
                        % int(after_pages)
                    break
            else:
                if fault_seen_at is None:
                    fault_seen_at = now
                if now - fault_seen_at > float(delay_ms) / 1000.0 + float(catalog_timeout_s):
                    break
            time.sleep(0.5)
    except Exception as exc:
        out = {"veredicto": "INCONCLUSO", "motivo": "excepcion: %s" % exc}
    finally:
        out["parada"] = _stop_lease_server(server_ctl, server_exe=server_exe, server_args=server_args,
                                           working_dir=working_dir, profile_dir=server_profile,
                                           state=server_state, build=build)
        if product_pbo and Path(product_pbo).is_file():
            out["product_pbo_sha256"] = hashlib.sha256(Path(product_pbo).read_bytes()).hexdigest()
        out["parametros"] = {"after_pages": int(after_pages), "delay_ms": float(delay_ms),
                             "catalog_timeout_s": float(catalog_timeout_s)}
        (base / "sonda_lease.json").write_text(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
                                               encoding="utf-8", newline="\n")
        if tap is not None:
            tap.stop()
        if backend is not None:
            try:
                backend.stop()
            except Exception:
                pass
        writer.close()
    print("[sonda_lease] %s: %s" % (out["veredicto"], out.get("motivo")))
    return {"PASA": 0, "FALLA": 1}.get(out["veredicto"], 2)


def run_seco(evidence_base=None, work_root=None):
    return run_campaign(build="offline", evidence_base=evidence_base,
                        mode="seco", work_root=work_root)


def run_humo(evidence_base=None, work_root=None):
    return run_campaign(build="offline", evidence_base=evidence_base,
                        mode="humo", work_root=work_root)


def run_almacen(evidence_base=None):
    out = Path(evidence_base) if evidence_base else Path("almacen-informe.json")
    return out, []


def build_parser():
    p = argparse.ArgumentParser(prog="f2p_partida")
    p.add_argument("--build", choices=("offline", "diag", "retail"), default="offline")
    p.add_argument("--evidence", default=None)
    p.add_argument("--mode", choices=("seco", "diag", "retail", "humo", "almacen", "lease"), default="seco")
    p.add_argument("--server-profile", default=None)
    p.add_argument("--client-profile", default=None)
    p.add_argument("--work-root", default=None)
    p.add_argument("--hello-timeout-s", type=float, default=60.0)
    p.add_argument("--director-timeout-ms", type=int, default=30000)
    p.add_argument("--server-ctl", default="")
    p.add_argument("--server-exe", default="")
    # nargs="?": PowerShell 5.1 descarta un argumento vacio y argparse veia la opcion sin valor (3b de t4-d940786).
    p.add_argument("--server-args", nargs="?", const="", default="")
    p.add_argument("--working-dir", default="")
    p.add_argument("--server-pid", type=int, default=0)
    p.add_argument("--server-start", nargs="?", const="", default="")
    p.add_argument("--client-exe", default="")
    p.add_argument("--client-args", nargs="?", const="", default="")
    p.add_argument("--client-pid", type=int, default=0)
    p.add_argument("--client-start", nargs="?", const="", default="")
    p.add_argument("--client-working-dir", nargs="?", const="", default="")
    p.add_argument("--reanudar", action="store_true")
    p.add_argument("--desde", choices=_FASES.PHASES, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--maquina", choices=("willy", "portatil"), default="willy")
    p.add_argument("--cliente", choices=("lanzar", "operador"), default="lanzar")
    p.add_argument("--package-dir", default="")
    p.add_argument("--humo", action="store_true")
    # Modo real: los PBO del paquete (portátil) o los construidos (Willy); los pasa el lanzador.
    p.add_argument("--pbo", default="")
    p.add_argument("--product-pbo", default="")
    # Comprobación previa del portátil (24-nov): sin DayZ; escribe <results-dir>/comprobacion.json.
    p.add_argument("--comprobar", action="store_true")
    p.add_argument("--results-dir", default="")
    p.add_argument("--mission-dir", default="")
    return p


def _client_working_dir(args):
    """Carpeta de trabajo del cliente: la explicita o la de su ejecutable, nunca la del servidor.

    En retail el servidor va en la carpeta DayZServer (steam_appid.txt 223350) y el cliente en la de DayZ (221100).
    El reinicio relanzaba el cliente con la carpeta del servidor: Steam lo iniciaba con la app del servidor, el
    servidor no recibia su identidad (uid vacio) y lo echaba con el 49 (montaje retail, t4-e3d0978 y t4-f0059e7).
    """
    explicit = getattr(args, "client_working_dir", "") or ""
    if explicit:
        return explicit
    exe = getattr(args, "client_exe", "") or ""
    if exe:
        return str(Path(exe).parent)
    return getattr(args, "working_dir", "") or ""


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "comprobar", False):
        ok, checks = run_comprobacion(
            work_root=args.work_root or ".", results_dir=args.results_dir or (args.work_root or "."),
            server_profile=args.server_profile, client_profile=args.client_profile,
            probe_pbo=args.pbo, product_pbo=args.product_pbo, server_exe=args.server_exe,
            client_exe=args.client_exe, mission_dir=args.mission_dir, package_dir=args.package_dir)
        for c in checks:
            print("[comprobacion] %-28s %s  %s" % (c["id"], "ok" if c["ok"] else "FALLO", c["detalle"][:160]))
        print("[comprobacion] resultado: %s" % ("ok" if ok else "FALLO: no se abre DayZ"))
        return 0 if ok else 1
    if getattr(args, "dry_run", False):
        for line in dry_run_orders(maquina=args.maquina, cliente=args.cliente,
                                   work_root=args.work_root or "",
                                   build=("diag" if args.build == "offline" else args.build),
                                   package_dir=getattr(args, "package_dir", "") or "",
                                   humo=bool(getattr(args, "humo", False))):
            print(line)
        return 0
    if getattr(args, "desde", None) == "gate":
        print("gate: qa/m1_gate.py spike F2P --evaluate-only "
              "--oracle-commit %s" % ORACLE_COMMIT)
        return 0
    if args.mode == "almacen":
        out, _lines = run_almacen(args.evidence)
        print(str(out))
        return 0
    if args.mode == "lease":
        return run_lease_probe(evidence_base=args.evidence or ".", work_root=args.work_root,
                               server_profile=args.server_profile, hello_timeout_s=args.hello_timeout_s,
                               product_pbo=args.product_pbo, server_ctl=args.server_ctl,
                               server_state={"pid": args.server_pid, "start_time": args.server_start},
                               server_exe=args.server_exe, server_args=args.server_args,
                               working_dir=args.working_dir,
                               build=(args.build if args.build in ("diag", "retail") else "diag"))
    build = "offline" if args.mode in ("seco", "humo") else args.build
    if args.mode == "humo" and getattr(args, "server_ctl", ""):
        try:
            base, _steps = run_humo_real(
                evidence_base=args.evidence, work_root=args.work_root,
                build=(args.build if args.build in ("diag", "retail") else "diag"),
                server_profile=args.server_profile,
                client_profile=args.client_profile,
                hello_timeout_s=args.hello_timeout_s,
                director_timeout_ms=args.director_timeout_ms,
                server_ctl=args.server_ctl,
                server_state={"pid": args.server_pid, "start_time": args.server_start},
                client_state={"pid": args.client_pid, "start_time": args.client_start},
                server_exe=args.server_exe, server_args=args.server_args,
                working_dir=args.working_dir, client_exe=args.client_exe,
                client_args=args.client_args,
                client_working_dir=_client_working_dir(args))
        except Exception as exc:
            print("humo fallo: %s" % exc)
            return 1
        print(str(base))
        return 0
    if args.mode == "humo":
        base, _info = run_humo(evidence_base=args.evidence, work_root=args.work_root)
    else:
        base, _info = run_campaign(build=build, evidence_base=args.evidence, mode=args.mode,
                                   server_profile=args.server_profile,
                                   client_profile=args.client_profile,
                                   work_root=args.work_root,
                                   hello_timeout_s=args.hello_timeout_s,
                                   director_timeout_ms=args.director_timeout_ms,
                                   cliente=args.cliente,
                                   server_ctl=args.server_ctl,
                                   server_state={"pid": args.server_pid,
                                                 "start_time": args.server_start},
                                   client_state={"pid": args.client_pid,
                                                 "start_time": args.client_start},
                                   server_exe=args.server_exe,
                                   server_args=args.server_args,
                                   working_dir=args.working_dir,
                                   client_exe=args.client_exe,
                                   client_args=args.client_args,
                                   client_working_dir=_client_working_dir(args),
                                   probe_pbo=args.pbo, product_pbo=args.product_pbo)
    print(str(base))
    return 0


if __name__ == "__main__":
    sys.exit(main())


