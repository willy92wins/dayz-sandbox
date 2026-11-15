"""Escenario de S-puente (brief F0.1 §8 y F0.3-0 §14 F02-H1/F02-H3). Offline lanza peers falsos; retail/diag no arranca DayZ."""

import json
import math
import os
import random
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import gate_core
import wire
from bridge_qa import QABridge
from s_puente_eval import evaluate

ROOT = Path(__file__).resolve().parents[1]
PEER = Path(__file__).resolve().with_name("fake_peer.py")

SERVER_VAL = {
    "N1": (0.10, 0.937),
    "N2": (0.20, 0.912),
    "N3": (0.30, 0.927),
    "N4": (0.40, 0.45),
    "N5": (0.60, 0.65),
}
CLIENT_VAL = {
    "N1": ((7400, 380, 7400), (7350, 390, 7350)),
    "N2": ((7410, 380, 7410), (7360, 390, 7360)),
    "N3": ((7420, 380, 7420), (7370, 390, 7370)),
    "N4": ((7430, 380, 7430), (7440, 380, 7440)),
    "N5": ((7450, 380, 7450), (7460, 380, 7460)),
}


# En Windows los peers falsos y el bridge compiten por CPU con cualquier otro proceso de la maquina
# (otras suites en paralelo). Las latencias que decide la matriz (M2 p95 < 1000 ms, "d done", seq de N6)
# se miden contra el reloj, asi que bajo carga salian veredictos 1/2 espurios. Los plazos son contrato y no
# se tocan: se aisla la corrida de la carga ajena subiendo la prioridad de bridge y peers.
#
# Limites (sesion principal, 2026-11-15): la subida es solo para los procesos de la corrida (este runner y sus
# peers), como mucho HIGH y nunca REALTIME; y no se sube mientras una partida tenga el lease de la GPU
# (`gpu_lease.py comprobar` da OCUPADA), para que una corrida offline no deforme una medicion en partida
# (p. ej. la de S-perf). Si no se puede saber el estado del lease, tampoco se sube. La decision queda escrita
# en `<evidencia>/priority_boost.json`.
_HIGH_PRIORITY_CLASS = 0x00000080  # HIGH_PRIORITY_CLASS; REALTIME_PRIORITY_CLASS (0x100) no se usa nunca
_NORMAL_PRIORITY_CLASS = 0x00000020
_REALTIME_PRIORITY_CLASS = 0x00000100
_PROCESS_SET_INFORMATION = 0x0200
_PROCESS_QUERY_INFORMATION = 0x0400
_PRIORITY_CLASS_NAMES = {
    _NORMAL_PRIORITY_CLASS: "NORMAL",
    _HIGH_PRIORITY_CLASS: "HIGH",
    _REALTIME_PRIORITY_CLASS: "REALTIME",
    0x00000040: "IDLE",
    0x00004000: "BELOW_NORMAL",
    0x00008000: "ABOVE_NORMAL",
}
_CFG_REPLACE_TRIES = 40
_CFG_REPLACE_PAUSE_S = 0.05
_GPU_LEASE_SCRIPT_ENV = "DSBX_GPU_LEASE_SCRIPT"
_GPU_LEASE_DEFAULT = Path.home() / ".claude" / "tools" / "gpu_lease.py"
_LEASE_RECHECK_S = 2.0


def _gpu_lease_busy():
    """False solo si `comprobar` responde LIBRE de forma inequivoca; True si ocupada; None si no se sabe.

    Solo cuenta como libre un codigo 0 con stdout exactamente `LIBRE` (sin espacios alrededor) y stderr
    vacio. Cualquier otra respuesta (otro texto, contradiccion, codigo distinto de 0, script ausente,
    error o timeout) no autoriza la subida.
    """
    script = os.environ.get(_GPU_LEASE_SCRIPT_ENV) or str(_GPU_LEASE_DEFAULT)
    if not Path(script).is_file():
        return None
    try:
        proc = subprocess.run(
            [sys.executable, script, "comprobar"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout or ""
    err = proc.stderr or ""
    if proc.returncode == 0 and out.strip() == "LIBRE" and not err.strip():
        return False
    if proc.returncode != 0:
        return True
    if "OCUPADA" in (out + err):
        return True
    return None


def _priority_decision(build):
    """Si esta corrida sube la prioridad ("applied") o por que no."""
    if os.name != "nt":
        return "not_windows"
    if build != "offline":
        return "not_offline"
    busy = _gpu_lease_busy()
    if busy is None:
        return "skipped_gpu_lease_unknown"
    if busy:
        return "skipped_gpu_lease_busy"
    return "applied"


def _priority_name(value):
    return _PRIORITY_CLASS_NAMES.get(int(value or 0), "unknown")


def _priority_api():
    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
    kernel32.GetPriorityClass.restype = ctypes.c_uint32
    kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.SetPriorityClass.restype = ctypes.c_int
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


def _read_priority(api, handle):
    try:
        return int(api.GetPriorityClass(handle) or 0)
    except (OSError, AttributeError, TypeError, ValueError):
        return 0


def _set_priority(api, handle, priority_class):
    """Aplica y lee de vuelta. Devuelve la clase observada, o 0 si SetPriorityClass la rechaza."""
    try:
        ok = api.SetPriorityClass(handle, priority_class)
    except (OSError, AttributeError):
        return 0
    if not ok:
        return 0
    return _read_priority(api, handle)


def _process_handle(api, proc):
    """Handle del Popen si lo expone, o uno abierto por pid. Devuelve (handle, hay_que_cerrarlo)."""
    handle = getattr(proc, "_handle", None)
    if handle:
        return handle, False
    try:
        handle = api.OpenProcess(_PROCESS_SET_INFORMATION | _PROCESS_QUERY_INFORMATION, False, int(proc.pid))
    except (OSError, AttributeError, TypeError, ValueError):
        return None, False
    if not handle:
        return None, False
    return handle, True


def _observed_priority(api, proc):
    if api is None:
        return 0
    handle, owned = _process_handle(api, proc)
    if handle is None:
        return 0
    try:
        return _read_priority(api, handle)
    finally:
        if owned:
            try:
                api.CloseHandle(handle)
            except (OSError, AttributeError):
                pass


def _lower_process_priority(api, proc):
    """Baja un peer a NORMAL. Devuelve la clase observada, o 0 si no se pudo."""
    if proc.poll() is not None:
        return 0
    handle, owned = _process_handle(api, proc)
    if handle is None:
        return 0
    try:
        return _set_priority(api, handle, _NORMAL_PRIORITY_CLASS)
    finally:
        if owned:
            try:
                api.CloseHandle(handle)
            except (OSError, AttributeError):
                pass


class _PriorityBoost:
    """Sube el runner a HIGH y lo restaura verificando SetPriorityClass y GetPriorityClass."""

    def __init__(self, api=None):
        self.api = api if api is not None else (_priority_api() if os.name == "nt" else None)
        self.handle = None
        self.previous = 0
        self.observed = 0
        self.applied = False
        self.error = None

    def apply(self):
        if self.api is None:
            return False
        try:
            self.handle = self.api.GetCurrentProcess()
            self.previous = int(self.api.GetPriorityClass(self.handle) or 0)
        except (OSError, AttributeError, TypeError, ValueError):
            self.error = "GetCurrentProcess/GetPriorityClass fallo"
            return False
        if not self.previous:
            self.error = "GetPriorityClass devolvio 0"
            return False
        observed = _set_priority(self.api, self.handle, _HIGH_PRIORITY_CLASS)
        self.observed = observed
        if not observed:
            self.error = "SetPriorityClass rechazo la subida"
            return False
        self.applied = True
        return True

    def lower(self):
        if not self.applied:
            return 0
        return _set_priority(self.api, self.handle, _NORMAL_PRIORITY_CLASS)

    def restore(self):
        """Restaura la clase previa y la verifica. Devuelve (ok, clase observada)."""
        if not self.applied or self.handle is None or not self.previous:
            return True, self.previous
        observed = _set_priority(self.api, self.handle, self.previous)
        return bool(observed) and observed == self.previous, observed


def run(args, evidence, argv=None):
    evidence = Path(evidence)
    samples = evidence / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    peers_dir = evidence / "peers"
    peers_dir.mkdir(parents=True, exist_ok=True)
    started = gate_core.utc_now()
    hold = args.hold_ms
    lease = args.lease_ms
    ttl = args.ttl_ms
    retry = args.retry_ms
    seed = args.seed
    fault = args.fault
    clock_offset_ms = float(getattr(args, "clock_offset_ms", 0.0) or 0.0)
    op_timeout = ttl + 1000
    interval = max(10, lease // 10)
    bridge_port_box = {}
    files = []
    lock = threading.Lock()
    procs = []
    profiles = []
    bridge = None

    def open_log(name):
        handle = (samples / name).open("a", encoding="utf-8", newline="\n")
        files.append(handle)
        return handle

    bridge_fp = open_log("bridge.jsonl")
    scenario_fp = open_log("scenario.jsonl")

    def write_row(handle, row):
        with lock:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()

    def sink(row):
        write_row(bridge_fp, row)

    ready = False
    priority = _priority_decision(args.build)
    boost = _PriorityBoost() if priority == "applied" else None
    boost_applied = bool(boost is not None and boost.apply())
    boost_lock = threading.Lock()
    boost_state = {"active": boost_applied, "lowered": False}
    note_lock = threading.Lock()
    peer_roles = {}
    priority_note = {
        "decision": priority,
        "priority_class": "HIGH" if boost_applied else "unchanged",
        "apply": {
            "runner": {
                "requested": "HIGH" if priority == "applied" else "unchanged",
                "observed": _priority_name(boost.observed) if boost is not None else "unchanged",
                "ok": boost_applied if priority == "applied" else None,
                "error": boost.error if boost is not None else None,
            },
            "peers": {},
        },
        "lease_lowered": [],
        "restore": {"done": False, "ok": None, "observed": "unknown"},
    }

    def write_priority_note():
        with note_lock:
            gate_core.write_json(evidence / "priority_boost.json", priority_note)

    write_priority_note()

    watch_stop = threading.Event()
    watcher = None

    def lease_watch():
        while not watch_stop.wait(_LEASE_RECHECK_S):
            try:
                busy = _gpu_lease_busy()
            except Exception:
                busy = None
            if watch_stop.is_set():
                return
            if busy is False:
                continue
            with boost_lock:
                if boost_state["lowered"]:
                    return
                boost_state["active"] = False
                boost_state["lowered"] = True
                snapshot = list(procs)
                roles = dict(peer_roles)
            runner_observed = boost.lower() if boost is not None else 0
            peers_lowered = {}
            for proc in snapshot:
                observed = _lower_process_priority(boost.api if boost is not None else None, proc)
                role = next((name for name, peer in roles.items() if peer is proc), f"pid:{proc.pid}")
                if observed:
                    peers_lowered[role] = _priority_name(observed)
            with note_lock:
                priority_note["lease_lowered"].append(
                    {
                        "at": gate_core.utc_now(),
                        "reason": "gpu_lease_busy" if busy is True else "gpu_lease_unknown",
                        "runner": _priority_name(runner_observed),
                        "peers": peers_lowered,
                    }
                )
                for role, observed in peers_lowered.items():
                    entry = priority_note["apply"]["peers"].get(role)
                    if isinstance(entry, dict):
                        entry["observed"] = observed
                        entry["lowered"] = True
            write_priority_note()
            return

    if boost_applied:
        watcher = threading.Thread(target=lease_watch, name="dsbx-lease-watch", daemon=True)
        watcher.start()

    def peer_creationflags():
        with boost_lock:
            return _HIGH_PRIORITY_CLASS if boost_state["active"] else 0

    def record_peer_priority(role, proc, requested_flags):
        observed = _observed_priority(boost.api if boost is not None else None, proc)
        with note_lock:
            priority_note["apply"]["peers"][role] = {
                "requested": "HIGH" if requested_flags else "unchanged",
                "observed": _priority_name(observed) if observed else "unknown",
                "ok": (observed == requested_flags)
                if requested_flags
                else (observed in (0, _NORMAL_PRIORITY_CLASS)),
            }
        write_priority_note()

    try:
        bridge = QABridge(hold, lease, sink, port=0)
        bridge_port_box["port"] = None
        bridge.start()
        bridge_port_box["port"] = bridge.port

        def scen(ev, **fields):
            row = {"ev": ev}
            if "t_ms" not in fields:
                row["t_ms"] = bridge.now_ms()
            row.update({k: v for k, v in fields.items() if v is not None})
            write_row(scenario_fp, row)

        def issue(peer, verb, args, ttl_ms=None, op_id=None, issued_ms=None, target=None, force=False, wait_ms=None):
            inst = bridge.registered(peer) if target is None else target
            after = bridge.now_ms()
            oid = bridge.enqueue(
                peer,
                verb,
                args,
                inst,
                ttl if ttl_ms is None else ttl_ms,
                op_id=op_id,
                issued_ms=issued_ms,
            )
            if force:
                bridge.force_deliver(oid)
            if wait_ms is None:
                return oid, None
            return oid, bridge.wait_result(oid, after, wait_ms)

        skipped = set()
        cfg_path = {}

        def launch_offline():
            rpc = _free_udp()
            home = Path(tempfile.mkdtemp(prefix="dsbx-peer-"))
            profiles.append(home)
            for role in ("server", "client"):
                key = secrets.token_hex(16)
                bridge.set_peer_key(role, key)
                folder = home / role
                folder.mkdir()
                cfg_path[role] = folder / "dsbx_qa.json"
                _write_cfg(cfg_path[role], bridge.port, key, retry)
                log = (peers_dir / f"{role}.log").open("w", encoding="utf-8", newline="\n")
                files.append(log)
                cmd = [
                    sys.executable,
                    str(PEER),
                    "--config",
                    str(folder / "dsbx_qa.json"),
                    "--peer",
                    role,
                    "--rpc-port",
                    str(rpc),
                    "--frame-hz",
                    "60",
                ]
                if fault:
                    cmd.extend(["--fault", fault])
                if clock_offset_ms != 0.0:
                    cmd.extend(["--clock-offset-ms", str(clock_offset_ms)])
                flags = peer_creationflags()
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(ROOT),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=flags,
                )
                with boost_lock:
                    procs.append(proc)
                    peer_roles[role] = proc
                    active_now = boost_state["active"]
                record_peer_priority(role, proc, flags)
                if flags and not active_now:
                    observed = _lower_process_priority(boost.api, proc)
                    if observed:
                        with note_lock:
                            entry = priority_note["apply"]["peers"].get(role)
                            if isinstance(entry, dict):
                                entry["observed"] = _priority_name(observed)
                                entry["lowered"] = True
                        write_priority_note()

        def prepare_live():
            for role, folder in (("server", Path(args.server_profile)), ("client", Path(args.client_profile))):
                key = secrets.token_hex(16)
                bridge.set_peer_key(role, key)
                cfg_path[role] = Path(folder) / "dsbx_qa.json"
                _write_cfg(cfg_path[role], bridge.port, key, retry)

        scen("step_start", step="S0")
        if args.build == "offline" and not (args.server_profile and args.client_profile):
            launch_offline()
        else:
            prepare_live()
        scen("step_end", step="S0")

        anchor_ms = bridge.now_ms()
        scen("step_start", step="S1", t_ms=anchor_ms)
        limit_ms = anchor_ms + args.peer_timeout * 1000.0
        seen = {}
        for role in ("server", "client"):
            _raise_if_bridge_failed(bridge)
            left_ms = max(0.0, limit_ms - bridge.now_ms())

            def hello_on_time(e, role=role):
                t_ms = e.get("t_ms")
                return (
                    e.get("ev") == "hello"
                    and e.get("peer") == role
                    and e.get("http") == 200
                    and e.get("ok", True) is True
                    and isinstance(t_ms, (int, float))
                    and not isinstance(t_ms, bool)
                    and math.isfinite(t_ms)
                    and t_ms <= limit_ms
                )

            ev = bridge.wait_event(hello_on_time, left_ms)
            seen[role] = ev is not None
        _raise_if_bridge_failed(bridge)
        if not all(seen.values()):
            scen("peers_absent", peer="server" if not seen["server"] else "client")
        scen("step_end", step="S1")
        if all(seen.values()):
            _retain(bridge, scen, hold)
            _mix(bridge, scen, issue, seed, op_timeout)
            for role in ("server", "client"):
                if not _negatives(role, bridge, scen, issue, hold, lease, ttl, retry, op_timeout, cfg_path):
                    skipped.add(role)
                    scen("resume_timeout", peer=role)
            if "server" not in skipped and "client" not in skipped:
                seq0 = _n6(bridge, scen, issue, lease, ttl, interval, op_timeout)
                _n6_server(bridge, scen, issue, lease, ttl, interval, op_timeout, seq0)
            scen("step_start", step="S10")
            scen("step_end", step="S10")
        _raise_if_bridge_failed(bridge)
        ready = True
    finally:
        watch_stop.set()
        if watcher is not None:
            watcher.join()
        try:
            if bridge is not None:
                bridge.stop()
        finally:
            try:
                _stop_peers(procs)
            finally:
                close_error = None
                for handle in files:
                    try:
                        handle.close()
                    except Exception as exc:
                        if close_error is None:
                            close_error = exc
                for folder in profiles:
                    shutil.rmtree(folder, ignore_errors=True)
                restore_error = None
                if priority == "applied" and boost is not None:
                    ok, observed = boost.restore()
                    with note_lock:
                        priority_note["restore"] = {
                            "done": True,
                            "ok": ok,
                            "observed": _priority_name(observed) if observed else "unknown",
                        }
                        if not ok:
                            priority_note["priority_class"] = "unchanged"
                    write_priority_note()
                    if not ok:
                        restore_error = RuntimeError(
                            "no se pudo restaurar la prioridad del runner "
                            f"(clase observada: {_priority_name(observed)})"
                        )
                else:
                    with note_lock:
                        priority_note["restore"] = {"done": True, "ok": True, "observed": "unchanged"}
                    write_priority_note()
                if restore_error is not None:
                    raise restore_error from close_error
                if close_error is not None:
                    raise close_error
    if bridge is not None and bridge.failure is not None:
        _raise_if_bridge_failed(bridge)
    if ready:
        return _finish(args, evidence, argv, started, bridge, bridge.port, fault)


def _raise_if_bridge_failed(bridge):
    failure = getattr(bridge, "failure", None)
    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)


def _finish(args, evidence, argv, started, bridge, port, fault):
    gate_core.write_json(
        Path(evidence) / "manifest.json",
        gate_core.make_manifest(
            "spike",
            "S-puente",
            args,
            argv or [],
            started,
            gate_core.utc_now(),
            port=port,
            run_id=bridge.run_id,
        ),
    )
    verdict = evaluate(evidence)
    gate_core.write_json(Path(evidence) / "verdict.json", verdict)
    return int(verdict["exit_code"])


def _retain(bridge, scen, hold):
    scen("step_start", step="S2")
    time.sleep(3 * hold / 1000.0)
    scen("step_end", step="S2")


def _mix(bridge, scen, issue, seed, op_timeout):
    scen("step_start", step="S3")
    rng = random.Random(seed)
    items = [("srv_read", {}) for _ in range(25)]
    for _ in range(25):
        items.append(("ground_query", {"x": round(rng.uniform(0, 15360), 1), "z": round(rng.uniform(0, 15360), 1)}))
    for _ in range(25):
        pos = [
            round(7500 + rng.uniform(-50, 50), 2),
            round(400 + rng.uniform(-50, 50), 2),
            round(7500 + rng.uniform(-50, 50), 2),
        ]
        yaw = round((rng.random() * 360.0) - 180.0, 2)
        if yaw >= 180:
            yaw = 179.99
        pitch = round(rng.uniform(-30, 30), 2)
        items.append(("cam_pose_set", {"pos": pos, "ypr": [yaw, pitch, 0.0]}))
    fogs = [round(0.05 * i, 2) for i in range(1, 20)]
    for _ in range(25):
        items.append(("ambient_set", {"fog": rng.choice(fogs)}))
    random.Random(seed).shuffle(items)
    for verb, args in items:
        peer = "client" if verb == "cam_pose_set" else "server"
        oid, _res = issue(peer, verb, args, wait_ms=op_timeout)
        scen("mix_op", op_id=oid, verb=verb)
    scen("step_end", step="S3")


def _negatives(role, bridge, scen, issue, hold, lease, ttl, retry, op_timeout, cfg_path):
    if not _n1(role, bridge, scen, issue, hold, ttl, retry, op_timeout, cfg_path):
        return False
    _n2(role, scen, issue, op_timeout)
    _n3(role, bridge, scen, issue, ttl, op_timeout)
    _n4(role, bridge, scen, issue, retry, op_timeout)
    _n5(role, bridge, scen, issue, op_timeout)
    return True


def _verb(role):
    if role == "server":
        return "ambient_set", "ambient_read"
    return "cam_pose_set", "cam_pose_read"


def _args_for(role, step, which):
    if role == "server":
        base, sent = SERVER_VAL[step]
        value = base if which == "a" else sent
        return {"fog": value}
    base, sent = CLIENT_VAL[step]
    xyz = base if which == "a" else sent
    ypr = [0, 0, 0] if which == "a" or step in ("N4", "N5") else [45, 0, 0]
    return {"pos": [xyz[0], xyz[1], xyz[2]], "ypr": ypr}


def _n1(role, bridge, scen, issue, hold, ttl, retry, op_timeout, cfg_path):
    set_v, read_v = _verb(role)
    scen("step_start", step="N1", peer=role)
    b_id, _res = issue(role, set_v, _args_for(role, "N1", "a"), wait_ms=op_timeout)
    scen("key_rotated", peer=role)
    rotated = bridge.now_ms()
    new_key = secrets.token_hex(16)
    bridge.set_peer_key(role, new_key)
    bridge.wait_event(
        lambda e, role=role, rotated=rotated: e.get("ev") == "auth_reject" and e.get("peer") == role and e["t_ms"] >= rotated,
        hold + 2 * retry + 2000,
    )
    s_id, _res = issue(role, set_v, _args_for(role, "N1", "b"), ttl_ms=ttl, wait_ms=None)
    time.sleep((ttl + 500) / 1000.0)
    _write_cfg(cfg_path[role], bridge.port, new_key, retry)
    scen("config_restored", peer=role)
    mark = bridge.now_ms()
    hello = bridge.wait_event(
        lambda e, role=role, mark=mark: e.get("ev") == "hello"
        and e.get("peer") == role
        and e.get("http") == 200
        and e.get("ok", True) is True
        and e["t_ms"] >= mark,
        3 * retry + 2000,
    )
    r_id, _res = issue(role, read_v, {}, wait_ms=op_timeout)
    scen("expect", step="N1", peer=role, roles={"B": b_id, "S": s_id, "read": r_id})
    scen("step_end", step="N1", peer=role)
    return hello is not None


def _n2(role, scen, issue, op_timeout):
    set_v, read_v = _verb(role)
    scen("step_start", step="N2", peer=role)
    b_id, _res = issue(role, set_v, _args_for(role, "N2", "a"), wait_ms=op_timeout)
    s_id, _res = issue(
        role,
        set_v,
        _args_for(role, "N2", "b"),
        target=secrets.token_hex(16),
        force=True,
        wait_ms=op_timeout,
    )
    r_id, _res = issue(role, read_v, {}, wait_ms=op_timeout)
    scen("expect", step="N2", peer=role, roles={"B": b_id, "S": s_id, "read": r_id})
    scen("step_end", step="N2", peer=role)


def _n3(role, bridge, scen, issue, ttl, op_timeout):
    set_v, read_v = _verb(role)
    scen("step_start", step="N3", peer=role)
    b_id, _res = issue(role, set_v, _args_for(role, "N3", "a"), wait_ms=op_timeout)
    issued = bridge.now_ms() - (ttl + 1000)
    s_id, _res = issue(
        role,
        set_v,
        _args_for(role, "N3", "b"),
        issued_ms=issued,
        force=True,
        wait_ms=op_timeout,
    )
    r_id, _res = issue(role, read_v, {}, wait_ms=op_timeout)
    scen("expect", step="N3", peer=role, roles={"B": b_id, "S": s_id, "read": r_id})
    scen("step_end", step="N3", peer=role)


def _n4(role, bridge, scen, issue, retry, op_timeout):
    set_v, read_v = _verb(role)
    scen("step_start", step="N4", peer=role)
    a_id, _res = issue(role, set_v, _args_for(role, "N4", "a"), wait_ms=op_timeout)
    b_id, _res = issue(role, set_v, _args_for(role, "N4", "b"), wait_ms=op_timeout)
    span = max(1000, retry)
    bridge.cut(role, span)
    ended = bridge.wait_event(
        lambda e, role=role: e.get("ev") == "cut_end" and e.get("peer") == role,
        span + 2000,
    )
    after_cut = ended["t_ms"] if ended else bridge.now_ms()
    bridge.wait_event(
        lambda e, role=role, after_cut=after_cut: e.get("ev") == "poll"
        and e.get("peer") == role
        and e.get("http") == 200
        and e["t_ms"] > after_cut,
        span + 3 * retry + 2000,
    )
    after = bridge.now_ms()
    issue(role, set_v, _args_for(role, "N4", "a"), op_id=a_id, wait_ms=None)
    bridge.wait_result(a_id, after, op_timeout)
    r_id, _res = issue(role, read_v, {}, wait_ms=op_timeout)
    scen("expect", step="N4", peer=role, roles={"a": a_id, "b": b_id, "read": r_id, "repeat": a_id})
    scen("step_end", step="N4", peer=role)


def _n5(role, bridge, scen, issue, op_timeout):
    set_v, read_v = _verb(role)
    scen("step_start", step="N5", peer=role)
    c_id = f"n5-{bridge.run_id}-{role}-c"
    bridge.drop_results(c_id, True)
    issue(role, set_v, _args_for(role, "N5", "a"), op_id=c_id, wait_ms=None)
    time.sleep(max(op_timeout, 2500) / 1000.0)
    d_id, _res = issue(role, set_v, _args_for(role, "N5", "b"), wait_ms=op_timeout)
    bridge.drop_results(c_id, False)
    after = bridge.now_ms()
    issue(role, set_v, _args_for(role, "N5", "a"), op_id=c_id, wait_ms=None)
    bridge.wait_result(c_id, after, op_timeout)
    r_id, _res = issue(role, read_v, {}, wait_ms=op_timeout)
    scen("expect", step="N5", peer=role, roles={"c": c_id, "d": d_id, "read": r_id, "repeat": c_id})
    scen("step_end", step="N5", peer=role)


def _n6(bridge, scen, issue, lease, ttl, interval, op_timeout):
    scen("step_start", step="N6", peer="client")
    issue("client", "cam_pose_set", {"pos": [7300, 370, 7300], "ypr": [0, 0, 0]}, wait_ms=op_timeout)
    pre_id, pre_res = issue("client", "rpc_log_read", {}, wait_ms=op_timeout)
    seq0 = 1000
    if isinstance(pre_res, dict):
        pre_read = pre_res.get("read")
        if isinstance(pre_read, dict) and isinstance(pre_read.get("rpc_log"), list):
            seqs = [
                int(entry["seq"])
                for entry in pre_read["rpc_log"]
                if isinstance(entry, dict)
                and isinstance(entry.get("seq"), (int, float))
                and not isinstance(entry.get("seq"), bool)
                and math.isfinite(entry["seq"])
            ]
            if seqs:
                seq0 = max(seqs) + 1000
    span = 40 * interval + lease + 1000
    cut_mark = bridge.now_ms()
    bridge.cut("client", span)
    client = bridge.registered("client")
    burst_id, _res = issue(
        "server",
        "rpc_burst",
        {
            "client_inst": client,
            "count": 40,
            "interval_ms": interval,
            "pos": [7200, 360, 7200],
            "seq0": seq0,
            "ypr": [90, 0, 0],
        },
        wait_ms=ttl + 40 * interval + 1000,
    )
    ended = bridge.wait_event(
        lambda e, cut_mark=cut_mark: e.get("ev") == "cut_end"
        and e.get("peer") == "client"
        and e["t_ms"] >= cut_mark,
        span + 1000,
    )
    after_cut = ended["t_ms"] if ended else bridge.now_ms()
    bridge.wait_event(
        lambda e, after_cut=after_cut: e.get("ev") == "poll"
        and e.get("peer") == "client"
        and e.get("http") == 200
        and e["t_ms"] > after_cut,
        span + 3000,
    )
    log_id, _res = issue("client", "rpc_log_read", {}, wait_ms=op_timeout)
    read_id, _res = issue("client", "cam_pose_read", {}, wait_ms=op_timeout)
    scen(
        "expect",
        step="N6",
        peer="client",
        roles={"pre_log": pre_id, "burst": burst_id, "log": log_id, "read": read_id},
    )
    scen("step_end", step="N6", peer="client")
    return seq0


def _n6_server(bridge, scen, issue, lease, ttl, interval, op_timeout, seq0):
    scen("step_start", step="N6", peer="server")
    client = bridge.registered("client")
    seq0_srv = seq0 + 1000
    after_enq = bridge.now_ms()
    burst_id, _ = issue(
        "server",
        "rpc_burst",
        {
            "client_inst": client,
            "count": 40,
            "interval_ms": interval,
            "pos": [7250, 360, 7250],
            "seq0": seq0_srv,
            "ypr": [90, 0, 0],
        },
        ttl_ms=ttl + 40 * interval + 5000,
        wait_ms=None,
    )
    bridge.wait_event(
        lambda e, oid=burst_id: e.get("ev") == "deliver" and e.get("op_id") == oid,
        op_timeout,
    )
    time.sleep(min(0.10, max(0.03, interval / 1000.0)))
    span = lease + interval + 400
    cut_mark = bridge.now_ms()
    bridge.cut("server", span)
    ended = bridge.wait_event(
        lambda e, cut_mark=cut_mark: e.get("ev") == "cut_end"
        and e.get("peer") == "server"
        and e["t_ms"] >= cut_mark,
        span + 2000,
    )
    bridge.wait_result(burst_id, after_enq, ttl + 40 * interval + 3000)
    after_cut = ended["t_ms"] if ended else bridge.now_ms()
    bridge.wait_event(
        lambda e, after_cut=after_cut: e.get("ev") == "poll"
        and e.get("peer") == "server"
        and e.get("http") == 200
        and e["t_ms"] > after_cut,
        span + 3000,
    )
    emit_pages = []
    p0_id, p0_res = issue(
        "server",
        "qa_emitlog_page",
        wire.pack_payload(
            scalars_str={"qa_fault": wire.QA_FAULT_NONE},
            scalars_num={"page_n": 0},
        ),
        wait_ms=op_timeout,
    )
    emit_pages.append(p0_id)
    pages_n = 1
    if isinstance(p0_res, dict) and p0_res.get("status") == "done":
        read0 = p0_res.get("read")
        if isinstance(read0, dict) and "payload" in (read0.get("has") or []):
            try:
                unpacked0 = wire.unpack_payload(read0)
                pages_n = int(unpacked0["num"].get("pages_n", 0))
            except ValueError:
                pages_n = 1
    for page_idx in range(1, pages_n):
        pid, _pres = issue(
            "server",
            "qa_emitlog_page",
            wire.pack_payload(
                scalars_str={"qa_fault": wire.QA_FAULT_NONE},
                scalars_num={"page_n": page_idx},
            ),
            wait_ms=op_timeout,
        )
        emit_pages.append(pid)
    scen(
        "expect",
        step="N6",
        peer="server",
        roles={"burst": burst_id, "emit_pages": emit_pages},
    )
    scen("step_end", step="N6", peer="server")


def _write_cfg(path, port, key, retry):
    body = {"key": key, "retry_ms": int(retry), "url": f"http://127.0.0.1:{port}/"}
    tmp = Path(str(path) + ".tmp")
    tmp.write_bytes(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    for attempt in range(_CFG_REPLACE_TRIES):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            # Windows: el peer (o un antivirus) tiene dsbx_qa.json abierto un instante. Reintento corto y acotado.
            if attempt == _CFG_REPLACE_TRIES - 1:
                raise
            time.sleep(_CFG_REPLACE_PAUSE_S)


def _free_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _stop_peers(procs):
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
