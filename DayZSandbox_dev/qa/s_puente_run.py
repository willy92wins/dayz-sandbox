"""Escenario de S-puente (brief F0.1 §8). Offline lanza peers falsos; retail/diag no arranca DayZ."""

import json
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
    try:
        bridge = QABridge(hold, lease, sink, port=0)
        bridge_port_box["port"] = None
        bridge.start()
        bridge_port_box["port"] = bridge.port

        def scen(ev, **fields):
            row = {"ev": ev, "t_ms": bridge.now_ms()}
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
                procs.append(
                    subprocess.Popen(cmd, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
                )

        def prepare_live():
            for role, folder in (("server", Path(args.server_profile)), ("client", Path(args.client_profile))):
                key = secrets.token_hex(16)
                bridge.set_peer_key(role, key)
                cfg_path[role] = Path(folder) / "dsbx_qa.json"
                _write_cfg(cfg_path[role], bridge.port, key, retry)

        scen("step_start", step="S0")
        if args.build == "offline":
            launch_offline()
        else:
            prepare_live()
        scen("step_end", step="S0")

        scen("step_start", step="S1")
        deadline = time.monotonic() + args.peer_timeout
        seen = {}
        for role in ("server", "client"):
            _raise_if_bridge_failed(bridge)
            left_ms = max(0.0, (deadline - time.monotonic()) * 1000.0)
            ev = bridge.wait_event(
                lambda e, role=role: e.get("ev") == "hello" and e.get("peer") == role and e.get("http") == 200,
                left_ms,
            )
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
                _n6(bridge, scen, issue, lease, ttl, interval, op_timeout)
            scen("step_start", step="S10")
            scen("step_end", step="S10")
        _raise_if_bridge_failed(bridge)
        ready = True
    finally:
        _stop_peers(procs)
        if bridge is not None:
            bridge.stop()
        for handle in files:
            handle.close()
        for folder in profiles:
            shutil.rmtree(folder, ignore_errors=True)
    if ready:
        return _finish(args, evidence, argv, started, bridge, bridge.port, fault)


def _raise_if_bridge_failed(bridge):
    failure = getattr(bridge, "failure", None)
    if failure is not None:
        raise failure.with_traceback(failure.__traceback__)


def _finish(args, evidence, argv, started, bridge, port, fault):
    gate_core.write_json(
        Path(evidence) / "manifest.json",
        gate_core.make_manifest("spike", "S-puente", args, argv or [], started, gate_core.utc_now(), port=port),
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
    c_id = f"n5-{role}-c"
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
            "seq0": 1000,
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
    scen("expect", step="N6", peer="client", roles={"burst": burst_id, "log": log_id, "read": read_id})
    scen("step_end", step="N6", peer="client")


def _write_cfg(path, port, key, retry):
    body = {"key": key, "retry_ms": int(retry), "url": f"http://127.0.0.1:{port}/"}
    tmp = Path(str(path) + ".tmp")
    tmp.write_bytes(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    tmp.replace(path)


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


