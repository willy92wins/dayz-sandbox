"""S-puente de punta a punta (brief F0.1 §10.2 puntos 6-12 y §10.3).

La evidencia de cada corrida es un temporal. La clave no se imprime.
"""

import argparse
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable

FAST = [
    "--hold-ms",
    "300",
    "--lease-ms",
    "600",
    "--ttl-ms",
    "1000",
    "--retry-ms",
    "300",
]

# brief §10.3: codigo de salida de cada fila con los tiempos rapidos de arriba.
MATRIX = (
    ("none", 0),
    ("slow", 1),
    ("drop_results", 1),
    ("ack_only", 1),
    ("blocks_on_poll", 1),
    ("ignores_instance", 1),
    ("ignores_ttl", 1),
    ("no_dedup", 1),
    ("rpc_ignores_lease", 1),
    ("no_key_reload", 2),
    ("wrong_build", 2),
)


def _peer_rows():
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*fake_peer.py*' } | "
        "ForEach-Object { \"$($_.ProcessId)|$($_.ParentProcessId)\" }"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr)
    rows = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        pid, parent = line.split("|", 1)
        rows.append(
            {
                "Name": "python.exe",
                "CommandLine": "fake_peer.py",
                "ProcessId": pid.strip(),
                "ParentProcessId": parent.strip(),
            }
        )
    return rows


def peers_owned(rows, parent_pids):
    parents = {str(pid) for pid in parent_pids}
    owned = []
    for row in rows:
        if str(row.get("Name", "")).lower() != "python.exe":
            continue
        if "fake_peer.py" not in str(row.get("CommandLine") or ""):
            continue
        if str(row.get("ParentProcessId")) not in parents:
            continue
        owned.append(str(row.get("ProcessId")))
    return owned


def _fake_peers(parent_pids):
    return peers_owned(_peer_rows(), parent_pids)


def evidence_key_bytes(root, captured=""):
    root = Path(root)
    blob = b""
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file():
                blob += path.read_bytes()
    if isinstance(captured, bytes):
        blob += captured
    else:
        blob += str(captured).encode("utf-8")
    return blob


def _kill(pids):
    for pid in pids:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            capture_output=True,
            timeout=20,
        )


def _args(**extra):
    values = {
        "both": True,
        "build": "offline",
        "client_profile": None,
        "evaluate_only": False,
        "fault": None,
        "hold_ms": 300,
        "lease_ms": 600,
        "peer_timeout": 20,
        "retry_ms": 300,
        "seed": 20261026,
        "server_profile": None,
        "ttl_ms": 1000,
    }
    values.update(extra)
    return argparse.Namespace(**values)


def _spike(extra, evidence, timeout, parents):
    cmd = [PY, "qa/m1_gate.py", "spike", "S-puente", "--both", "--evidence", str(evidence), *extra]
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    parents.add(str(proc.pid))
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def _tree_bytes(root):
    blob = b""
    for path in root.rglob("*"):
        if path.is_file():
            blob += path.read_bytes()
    return blob


class _FakeProc:
    def __init__(self, pid, handle, exit_code=None):
        self.pid = pid
        self._handle = handle
        self._exit_code = exit_code
        self.terminated = False
        self.killed = False
        self.waited = False

    def poll(self):
        return self._exit_code

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.waited = True
        return 0

    def kill(self):
        self.killed = True


@contextlib.contextmanager
def _cpu_load():
    """Satura la CPU con procesos de prioridad normal (el caso de varias suites a la vez)."""
    spin = "while True: pass"
    burners = []
    try:
        for _ in range(max(8, 2 * (os.cpu_count() or 4))):
            burners.append(subprocess.Popen([PY, "-c", spin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        yield len(burners)
    finally:
        for proc in burners:
            proc.kill()
        for proc in burners:
            proc.wait(timeout=20)


def _row_code(fault):
    import s_puente_run

    with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
        evidence = Path(tmp) / "run"
        evidence.mkdir()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = s_puente_run.run(_args(fault=None if fault == "none" else fault), evidence, [])
        verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
        bad = [(row["id"], row["status"]) for row in verdict["checks"] if row["status"] != "pass"]
    return code, bad


def _n6_ctx(
    accept_ms,
    apply_ms,
    pose_read_ms,
    read_pose=None,
    reject_ms=626,
    lease_ms=600,
    accepts=None,
    mutate_log=None,
):
    """Evidencia N6 minima con el rpc_log y la pose que produce un peer de reloj controlado.

    El peer aplica una pose diferida en el frame siguiente y solo la descarta si su lease ya no
    vale en ese frame (`fake_peer.py`, `_apply`), y anota el resultado en la entrada del rpc_log. El
    reloj lo mueve el test para fijar la edad del lease al recibir y al aplicar.

    `accepts = [(recibida_ms, aplicada_ms), ...]` sustituye a la unica aceptada `(accept_ms, apply_ms)`:
    la i-esima lleva `seq0 + i` y la pose `x = 7200 + i`. Despues llega una rechazada en `reject_ms`.
    `mutate_log(entries)` cambia una copia del rpc_log antes de evaluar, para simular un peer defectuoso
    o una sonda sin registro de aplicacion.
    """
    import fake_peer
    import s_puente_eval

    clock = [0.0]
    peer = fake_peer.Peer(
        config=None,
        role="client",
        rpc_port=0,
        frame_hz=60,
        fault=None,
        clock_ms_fn=lambda: clock[0],
    )
    peer.lease_ms = lease_ms
    peer.last_ok_ms = 0.0
    peer.pose = ([7300.0, 370.0, 7300.0], [0.0, 0.0, 0.0])
    peer.frame = 100
    seq0 = 1000
    accepts = list(accepts) if accepts is not None else [(accept_ms, apply_ms)]
    for i, (acc_ms, app_ms) in enumerate(accepts):
        clock[0] = float(acc_ms)
        peer._handle_cam_rpc(
            {
                "target_inst": peer.inst,
                "seq": seq0 + i,
                "pos": [7200.0 + i, 360.0, 7200.0],
                "ypr": [90.0, 0.0, 0.0],
            }
        )
        clock[0] = float(app_ms)
        peer.frame += 1
        peer._apply()
    clock[0] = float(reject_ms)
    peer._handle_cam_rpc(
        {
            "target_inst": peer.inst,
            "seq": seq0 + len(accepts),
            "pos": [7200.0 + len(accepts), 360.0, 7200.0],
            "ypr": [90.0, 0.0, 0.0],
        }
    )
    if read_pose is None:
        read_pose = peer.pose
    log_entries = [dict(entry) for entry in peer.rpc_log]
    if mutate_log is not None:
        mutate_log(log_entries)
    log_done_ms = max(float(pose_read_ms), float(reject_ms) + 1.0)
    bridge = [
        {
            "ev": "result",
            "op_id": "pre",
            "t_ms": 1,
            "result": {
                "status": "done",
                "dup": False,
                "done_ms": 0,
                "read": {"has": ["rpc_log"], "rpc_log": []},
            },
        },
        {
            "ev": "enq",
            "op_id": "burst",
            "t_ms": 2,
            "args": {
                "seq0": seq0,
                "count": len(accepts) + 1,
                "pos": [7200.0, 360.0, 7200.0],
                "ypr": [90.0, 0.0, 0.0],
            },
        },
        {
            "ev": "result",
            "op_id": "log",
            "t_ms": 3,
            "result": {
                "status": "done",
                "dup": False,
                "done_ms": log_done_ms,
                "read": {"has": ["rpc_log"], "rpc_log": log_entries},
            },
        },
        {
            "ev": "result",
            "op_id": "read",
            "t_ms": 4,
            "result": {
                "status": "done",
                "dup": False,
                "done_ms": float(pose_read_ms),
                "read": {
                    "has": ["pos", "ypr"],
                    "pos": list(read_pose[0]),
                    "ypr": list(read_pose[1]),
                },
            },
        },
    ]
    scenario = [
        {"ev": "step_start", "step": "N6", "peer": "client", "t_ms": 0},
        {
            "ev": "expect",
            "step": "N6",
            "peer": "client",
            "t_ms": 5,
            "roles": {"pre_log": "pre", "burst": "burst", "log": "log", "read": "read"},
        },
        {"ev": "step_end", "step": "N6", "peer": "client", "t_ms": 10},
    ]
    ctx = {
        "bridge": bridge,
        "scenario": scenario,
        "lease": lease_ms,
        "skipped": {},
        "index": {id(ev): i for i, ev in enumerate(bridge)},
    }
    return s_puente_eval._n6(ctx)


class E2ESpuenteTests(unittest.TestCase):
    def setUp(self):
        self.parents = {str(os.getpid())}
        self.owned_before = set(_fake_peers(self.parents))

    def tearDown(self):
        afterwards = set(_fake_peers(self.parents))
        leaked = afterwards - self.owned_before
        try:
            self.assertEqual(sorted(leaked), [])
        finally:
            _kill(leaked)

    def test_point6_default_offline_passes(self):
        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            evidence = Path(tmp) / "run"
            proc = _spike(["--build", "offline"], evidence, 240, self.parents)
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
            verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["exit_code"], 0)
            bad = [row["id"] for row in verdict["checks"] if row["status"] != "pass"]
            self.assertEqual(bad, [])
            before = (evidence / "verdict.json").read_bytes()
            manifest = (evidence / "manifest.json").read_bytes()
            again = _spike(["--build", "offline", "--evaluate-only"], evidence, 60, self.parents)
            self.assertEqual(again.returncode, 0, again.stderr[-2000:])
            self.assertEqual((evidence / "verdict.json").read_bytes(), before)
            self.assertEqual((evidence / "manifest.json").read_bytes(), manifest)
            leaked = _tree_bytes(evidence)
            self.assertNotIn(b"key=", leaked)
            self.assertNotIn(b"dsbx_qa.json", leaked)
            joined = proc.stdout + proc.stderr + again.stdout + again.stderr
            self.assertNotIn(b"key=", joined)

    def test_point7_fault_matrix(self):
        import s_puente_run
        from bridge_qa import QABridge

        keys = []
        original = QABridge.set_peer_key

        def set_peer_key(self, peer, key):
            keys.append(key)
            return original(self, peer, key)

        with mock.patch.object(QABridge, "set_peer_key", set_peer_key):
            for fault, expected in MATRIX:
                with self.subTest(fault=fault, expected=expected):
                    keys.clear()
                    with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
                        evidence = Path(tmp) / "run"
                        evidence.mkdir()
                        args = _args(fault=None if fault == "none" else fault)
                        out = io.StringIO()
                        err = io.StringIO()
                        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                            code = s_puente_run.run(args, evidence, [])
                        verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
                        not_passing = [(row["id"], row["status"], row["detail"]) for row in verdict["checks"] if row["status"] != "pass"]
                        self.assertEqual(code, expected, not_passing)
                        self.assertEqual(verdict["exit_code"], expected)
                        if fault == "drop_results":
                            self.assertEqual(verdict["metrics"]["n_timeouts"], 11)
                        blob = evidence_key_bytes(evidence, out.getvalue() + err.getvalue())
                        self.assertTrue(keys)
                        for key in keys:
                            self.assertNotIn(key.encode("ascii"), blob)
                        if fault == "none":
                            copied = Path(tmp) / "copy"
                            shutil.copytree(evidence, copied)
                            planted = "c0ffee" * 5
                            bridge_log = copied / "samples" / "bridge.jsonl"
                            bridge_log.write_bytes(bridge_log.read_bytes() + planted.encode("ascii"))
                            self.assertIn(planted.encode("ascii"), evidence_key_bytes(copied))
                            self.assertNotIn(planted.encode("ascii"), evidence_key_bytes(evidence))
                            self.assertIn(planted.encode("ascii"), evidence_key_bytes(evidence, planted))

    def test_point7_rows_hold_under_cpu_load(self):
        """Carga extrema, fuera del gate: M2 (p95 con carga extrema) es un residual del entorno."""
        if os.environ.get("DSBX_STRESS") != "1":
            self.skipTest("prueba de carga: solo con DSBX_STRESS=1 (fuera del gate determinista)")
        with _cpu_load():
            for fault, expected in (("none", 0), ("wrong_build", 2)):
                with self.subTest(fault=fault, expected=expected):
                    code, bad = _row_code(fault)
                    self.assertEqual(code, expected, bad)

    # --- N6 con reloj controlado (F02-H3). La pose inicial del peer es x=7300; la i-esima aceptada, x=7200+i. ---
    _PRE_BURST = ([7300.0, 370.0, 7300.0], [0.0, 0.0, 0.0])

    @staticmethod
    def _pose_of(i):
        return ([7200.0 + i, 360.0, 7200.0], [90.0, 0.0, 0.0])

    @staticmethod
    def _strip_apply(entries):
        for entry in entries:
            for key in ("apply_ms", "apply_lease_age_ms", "applied_b"):
                entry.pop(key, None)

    def test_n6_applies_last_accepted_pose_when_lease_is_valid(self):
        status, detail, _ = _n6_ctx(566, 599, 630)
        self.assertEqual((status, detail), ("pass", ""))

    def test_n6_peer_records_apply_outcome(self):
        def check(entries):
            accepted = [e for e in entries if e["decision"] == "accepted"]
            self.assertEqual([(e["apply_ms"], e["apply_lease_age_ms"], e["applied_b"]) for e in accepted],
                             [(110.0, 110.0, 1), (601.0, 601.0, 0)])
            self.assertNotIn("applied_b", [k for e in entries if e["decision"] != "accepted" for k in e])

        _n6_ctx(None, None, 640, accepts=[(100, 110), (566, 601)], mutate_log=check)

    def test_n6_discarded_single_accept_is_not_required_but_not_pass(self):
        # 566/601: el peer descarta por lease caducado (no se exige como ultima aceptada, no es FALLA). No se
        # aplico ninguna de la rafaga y la pose de antes no esta en la evidencia: INCONCLUSO.
        status, detail, _ = _n6_ctx(566, 601, 630)
        self.assertEqual((status, detail), ("missing", "no burst pose applied"))

    def test_n6_excuses_pose_discarded_after_lease_expiry(self):
        status, detail, _ = _n6_ctx(None, None, 640, accepts=[(300, 310), (566, 601)])
        self.assertEqual((status, detail), ("pass", "pose discarded after lease expiry"))

    def test_n6_slow_frame_discard_passes_without_frame_bound(self):
        # Sol delta MEN 2: peer a 2 Hz, la segunda llega a 300 y el frame siguiente es a 800 (lease 600).
        status, detail, _ = _n6_ctx(None, None, 900, accepts=[(100, 110), (300, 800)], reject_ms=850)
        self.assertEqual((status, detail), ("pass", "pose discarded after lease expiry"))

    def test_n6_fails_pose_discarded_while_lease_is_valid(self):
        status, detail, _ = _n6_ctx(100, 150, 200, read_pose=self._PRE_BURST)
        self.assertEqual((status, detail), ("fail", "pose is not last applied"))

    def test_n6_fails_must_apply_pose_dropped_even_if_read_after_expiry(self):
        # Se aplico con lease vigente (150 <= 600); que la lectura sea posterior a la caducidad no excusa nada.
        status, detail, _ = _n6_ctx(100, 150, 700, read_pose=self._PRE_BURST)
        self.assertEqual((status, detail), ("fail", "pose is not last applied"))

    def test_n6_fails_peer_keeping_first_pose_sol_delta_bloq(self):
        # Sol delta BLOQ 1: recepciones 100/400/560, frames 110/410/570, lectura 640; el peer conserva la primera.
        status, detail, _ = _n6_ctx(
            None, None, 640, accepts=[(100, 110), (400, 410), (560, 570)], read_pose=self._pose_of(0)
        )
        self.assertEqual((status, detail), ("fail", "pose is not last applied"))

    def test_n6_fails_discard_logged_with_valid_lease(self):
        # Sol delta BLOQ 1, sin obligadas: aceptada a 400, descartada a 410 con el lease vigente.
        def discard(entries):
            entries[0]["applied_b"] = 0

        status, detail, _ = _n6_ctx(400, 410, 640, read_pose=self._PRE_BURST, mutate_log=discard)
        self.assertEqual((status, detail), ("fail", "pose apply contradicts lease"))

    def test_n6_fails_apply_logged_with_expired_lease(self):
        def apply_late(entries):
            entries[1]["applied_b"] = 1

        status, detail, _ = _n6_ctx(
            None, None, 640, accepts=[(100, 110), (566, 601)], read_pose=self._pose_of(1), mutate_log=apply_late
        )
        self.assertEqual((status, detail), ("fail", "pose apply contradicts lease"))

    def test_n6_fails_pose_of_rejected_rpc(self):
        # Sol delta BLOQ 1: la pose leida es la de la RPC rechazada por lease.
        status, detail, _ = _n6_ctx(None, None, 640, accepts=[(100, 110), (300, 310)], read_pose=self._pose_of(2))
        self.assertEqual((status, detail), ("fail", "pose is not last applied"))

    def test_n6_fails_pose_older_than_last_applied(self):
        status, detail, _ = _n6_ctx(
            None, None, 640, accepts=[(100, 110), (300, 310), (560, 601)], read_pose=self._pose_of(0)
        )
        self.assertEqual((status, detail), ("fail", "pose is not last applied"))

    def test_n6_fails_when_no_burst_pose_was_applied(self):
        status, detail, _ = _n6_ctx(
            None, None, 640, accepts=[(100, 110), (300, 310), (560, 601)], read_pose=self._PRE_BURST
        )
        self.assertEqual((status, detail), ("fail", "pose is not last applied"))

    def test_n6_without_apply_record_earlier_accepted_pose_is_missing(self):
        # Sonda real (sin registro de aplicacion): la pose de una aceptada anterior puede ser un descarte valido.
        status, detail, _ = _n6_ctx(
            None,
            None,
            640,
            accepts=[(100, 110), (300, 310), (560, 601)],
            read_pose=self._pose_of(1),
            mutate_log=self._strip_apply,
        )
        self.assertEqual((status, detail), ("missing", "pose mismatch without apply evidence"))

    def test_n6_without_apply_record_foreign_pose_fails(self):
        # Sin registro: con aceptadas en dos recepciones distintas, las primeras se aplicaron; una pose que no es
        # de ninguna aceptada (la de antes de la rafaga, o la de una rechazada) es FALLA.
        for pose in (self._PRE_BURST, self._pose_of(3)):
            with self.subTest(pose=pose[0][0]):
                status, detail, _ = _n6_ctx(
                    None,
                    None,
                    640,
                    accepts=[(100, 110), (300, 310), (560, 601)],
                    read_pose=pose,
                    mutate_log=self._strip_apply,
                )
                self.assertEqual((status, detail), ("fail", "pose is not an accepted pose"))

    def test_n6_without_apply_record_last_accepted_pose_passes(self):
        status, detail, _ = _n6_ctx(566, 599, 630, mutate_log=self._strip_apply)
        self.assertEqual((status, detail), ("pass", ""))

    def test_cpu_load_kills_partially_created_burners(self):
        created = []

        def factory(*args, **kwargs):
            if len(created) >= 2:
                raise OSError("no se pudo crear el burner")
            proc = _FakeProc(len(created), None)
            created.append(proc)
            return proc

        with mock.patch.object(subprocess, "Popen", side_effect=factory):
            with self.assertRaises(OSError):
                with _cpu_load():
                    self.fail("no deberia entrar al bloque protegido")
        self.assertEqual(len(created), 2)
        self.assertTrue(all(proc.killed and proc.waited for proc in created))

    def test_write_cfg_retries_a_busy_file(self):
        import s_puente_run

        real = Path.replace
        calls = []

        def busy_twice(self, target):
            calls.append(target)
            if len(calls) <= 2:
                raise PermissionError(5, "Acceso denegado")
            return real(self, target)

        with tempfile.TemporaryDirectory(prefix="dsbx-cfg-") as tmp:
            cfg = Path(tmp) / "dsbx_qa.json"
            with mock.patch.object(Path, "replace", busy_twice), mock.patch.object(s_puente_run.time, "sleep"):
                s_puente_run._write_cfg(cfg, 1234, "k" * 32, 300)
            self.assertEqual(json.loads(cfg.read_text(encoding="utf-8"))["url"], "http://127.0.0.1:1234/")
            self.assertEqual(len(calls), 3)

    def test_write_cfg_retry_is_bounded(self):
        import s_puente_run

        def always_busy(self, target):
            raise PermissionError(5, "Acceso denegado")

        with tempfile.TemporaryDirectory(prefix="dsbx-cfg-") as tmp:
            cfg = Path(tmp) / "dsbx_qa.json"
            with mock.patch.object(Path, "replace", always_busy), mock.patch.object(s_puente_run.time, "sleep"):
                with self.assertRaises(PermissionError):
                    s_puente_run._write_cfg(cfg, 1234, "k" * 32, 300)

    def test_point8_retail_does_not_launch_and_writes_profiles(self):
        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            root = Path(tmp)
            evidence = root / "run"
            server = root / "server-profile"
            client = root / "client-profile"
            server.mkdir()
            client.mkdir()
            proc = _spike(
                [
                    "--build",
                    "retail",
                    "--peer-timeout",
                    "5",
                    "--server-profile",
                    str(server),
                    "--client-profile",
                    str(client),
                ],
                evidence,
                30,
                self.parents,
            )
            self.assertEqual(proc.returncode, 2, proc.stderr[-2000:])
            keys = []
            for folder in (server, client):
                body = json.loads((folder / "dsbx_qa.json").read_text(encoding="utf-8"))
                self.assertIn("url", body)
                self.assertIn("key", body)
                self.assertIn("retry_ms", body)
                self.assertTrue(body["url"].startswith("http://127.0.0.1:"))
                keys.append(body["key"])
            blob = _tree_bytes(evidence) + proc.stdout + proc.stderr
            for key in keys:
                self.assertNotIn(key.encode("ascii"), blob)
            self.assertFalse(set(_fake_peers(self.parents)) - self.owned_before)

    def test_sol08_evaluate_runs_after_bridge_stops(self):
        import s_puente_run

        seen = {}
        real = s_puente_run.evaluate

        def wrapped(directory):
            path = Path(directory) / "samples" / "bridge.jsonl"
            seen["size"] = path.stat().st_size
            port = json.loads((Path(directory) / "manifest.json").read_text(encoding="utf-8"))["params"]["port"]
            sock = socket.socket()
            sock.settimeout(0.3)
            try:
                sock.connect(("127.0.0.1", port))
                seen["up"] = True
            except OSError:
                seen["up"] = False
            finally:
                sock.close()
            seen["peers"] = _fake_peers(self.parents)
            return real(directory)

        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            root = Path(tmp)
            (root / "s").mkdir()
            (root / "c").mkdir()
            evidence = root / "run"
            evidence.mkdir()
            with mock.patch("s_puente_run.evaluate", wrapped):
                code = s_puente_run.run(
                    _args(
                        build="retail",
                        peer_timeout=0.2,
                        server_profile=str(root / "s"),
                        client_profile=str(root / "c"),
                    ),
                    evidence,
                    [],
                )
            later = (evidence / "samples" / "bridge.jsonl").stat().st_size
            proc_return = code
        self.assertEqual(proc_return, 2)
        self.assertIs(seen["up"], False)
        self.assertEqual(seen["peers"], [])
        self.assertEqual(later, seen["size"])

    def test_sol14_one_deadline_for_both_peers(self):
        import s_puente_run

        script = Path(tempfile.mkdtemp(prefix="dsbx-hello-")) / "hello.py"
        script.write_bytes(
            b"import json,sys,time,urllib.request\n"
            b"from pathlib import Path\n"
            b"time.sleep(float(sys.argv[1]))\n"
            b"cfg=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))\n"
            b"body=json.dumps({'proto':'qa0','peer':sys.argv[3],'inst':'ab'*16,'build':'offline','probe_ver':'t'}).encode()\n"
            b"req=urllib.request.Request(cfg['url'].rstrip('/')+'/hello?key='+cfg['key'],data=body,method='POST')\n"
            b"try:\n urllib.request.urlopen(req,timeout=5).read()\nexcept Exception:\n pass\n"
            b"time.sleep(30)\n"
        )
        real = subprocess.Popen

        def fake_popen(cmd, **kwargs):
            if "--peer" not in cmd:
                return real(cmd, **kwargs)
            role = cmd[cmd.index("--peer") + 1]
            cfg = cmd[cmd.index("--config") + 1]
            delay = "1.5" if role == "server" else "3.5"
            return real([sys.executable, str(script), delay, cfg, role], **kwargs)

        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            evidence = Path(tmp) / "run"
            evidence.mkdir()
            with mock.patch("s_puente_run.subprocess.Popen", fake_popen):
                code = s_puente_run.run(
                    _args(peer_timeout=2),
                    evidence,
                    [],
                )
            scenario = (evidence / "samples" / "scenario.jsonl").read_text(encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertIn('"ev": "peers_absent"', scenario)
        self.assertIn('"peer": "client"', scenario)

    def test_sol23_enumeration_sees_a_child_named_like_the_peer(self):
        proc = subprocess.Popen(
            [PY, "-c", "import time; time.sleep(30)", "fake_peer.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.parents.add(str(proc.pid))
        try:
            deadline_rows = []
            for _ in range(20):
                deadline_rows = _peer_rows()
                if any(str(row["ProcessId"]) == str(proc.pid) for row in deadline_rows):
                    break
                time.sleep(0.1)
            owned = peers_owned(deadline_rows, self.parents)
            self.assertIn(str(proc.pid), owned)
        finally:
            proc.kill()
            proc.wait(timeout=5)

    def test_sol15_foreign_parent_is_not_killed(self):
        rows = [
            {
                "Name": "python.exe",
                "CommandLine": r"C:\Python314\python.exe qa\fake_peer.py --peer server",
                "ProcessId": "41",
                "ParentProcessId": "999",
            },
            {
                "Name": "python.exe",
                "CommandLine": r"C:\Python314\python.exe qa\fake_peer.py --peer client",
                "ProcessId": "42",
                "ParentProcessId": "10",
            },
        ]
        self.assertEqual(peers_owned(rows, {"10", str(os.getpid())}), ["42"])

    def test_sol09_sink_error_fills_verdict(self):
        import m1_gate
        import s_puente_run

        original = s_puente_run.json.dumps

        def dumps(obj, **kwargs):
            if isinstance(obj, dict) and obj.get("ev") == "hello":
                raise OSError("sink")
            return original(obj, **kwargs)

        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            evidence = Path(tmp) / "run"
            with mock.patch("s_puente_run.json.dumps", dumps):
                code = m1_gate.main(
                    [
                        "spike",
                        "S-puente",
                        "--both",
                        "--build",
                        "offline",
                        "--evidence",
                        str(evidence),
                        "--peer-timeout",
                        "5",
                        *FAST,
                    ]
                )
            verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 2)
        self.assertEqual(verdict["error"]["type"], "OSError")
        self.assertTrue(verdict["error"]["traceback"])

    def test_point11_no_fake_peer_survives(self):
        self.assertFalse(set(_fake_peers(self.parents)) - self.owned_before)


if __name__ == "__main__":
    unittest.main()
