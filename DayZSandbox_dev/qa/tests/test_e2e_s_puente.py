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


@contextlib.contextmanager
def _cpu_load():
    """Satura la CPU con procesos de prioridad normal (el caso de varias suites a la vez)."""
    spin = "while True: pass"
    burners = [
        subprocess.Popen([PY, "-c", spin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(max(8, 2 * (os.cpu_count() or 4)))
    ]
    try:
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
        # Sin el arreglo (peers y bridge a prioridad normal) esta carga da 1 en vez de 0 (M2 p95, N5 "d not done").
        import s_puente_run

        decision = s_puente_run._priority_decision("offline")
        if decision != "applied":
            self.skipTest(f"sin subida de prioridad en esta maquina ahora: {decision}")
        with _cpu_load():
            for fault, expected in (("none", 0), ("wrong_build", 2)):
                with self.subTest(fault=fault, expected=expected):
                    code, bad = _row_code(fault)
                    self.assertEqual(code, expected, bad)

    def test_point7_priority_boost_is_restored(self):
        import s_puente_run

        if os.name != "nt":
            self.skipTest("solo Windows")
        if s_puente_run._gpu_lease_busy() is not False:
            self.skipTest("lease de la GPU ocupado o desconocido: no se sube la prioridad")
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        me = kernel32.GetCurrentProcess()
        before = kernel32.GetPriorityClass(me)
        restore = s_puente_run._raise_priority()
        try:
            self.assertEqual(kernel32.GetPriorityClass(me), s_puente_run._HIGH_PRIORITY_CLASS)
        finally:
            restore()
        self.assertEqual(kernel32.GetPriorityClass(me), before)
        # como mucho HIGH: nunca REALTIME_PRIORITY_CLASS (0x100)
        self.assertEqual(s_puente_run._HIGH_PRIORITY_CLASS, 0x80)

    def test_gpu_lease_check_reads_the_lease_script(self):
        import s_puente_run

        with tempfile.TemporaryDirectory(prefix="dsbx-lease-") as tmp:
            busy = Path(tmp) / "busy.py"
            busy.write_text("import sys\nprint('OCUPADA: partida en curso')\nsys.exit(1)\n", encoding="utf-8")
            free = Path(tmp) / "free.py"
            free.write_text("print('LIBRE')\n", encoding="utf-8")
            cases = ((busy, True), (free, False), (Path(tmp) / "missing.py", None))
            for script, expected in cases:
                with self.subTest(script=script.name):
                    with mock.patch.dict(os.environ, {s_puente_run._GPU_LEASE_SCRIPT_ENV: str(script)}):
                        self.assertIs(s_puente_run._gpu_lease_busy(), expected)

    def test_priority_decision_respects_the_gpu_lease(self):
        import s_puente_run

        if os.name != "nt":
            self.assertEqual(s_puente_run._priority_decision("offline"), "not_windows")
            return
        for busy, expected in ((True, "skipped_gpu_lease_busy"), (None, "skipped_gpu_lease_unknown"), (False, "applied")):
            with self.subTest(busy=busy):
                with mock.patch.object(s_puente_run, "_gpu_lease_busy", return_value=busy):
                    self.assertEqual(s_puente_run._priority_decision("offline"), expected)
        with mock.patch.object(s_puente_run, "_gpu_lease_busy", return_value=False):
            self.assertEqual(s_puente_run._priority_decision("diag"), "not_offline")

    def test_run_does_not_boost_while_a_game_holds_the_gpu_lease(self):
        import s_puente_run

        def must_not_boost():
            raise AssertionError("subio la prioridad con el lease de la GPU ocupado")

        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            evidence = Path(tmp) / "run"
            evidence.mkdir()
            with mock.patch.object(s_puente_run, "_gpu_lease_busy", return_value=True), mock.patch.object(
                s_puente_run, "_raise_priority", must_not_boost
            ):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    s_puente_run.run(_args(fault=None), evidence, [])
            note = json.loads((evidence / "priority_boost.json").read_text(encoding="utf-8"))
            expected = "skipped_gpu_lease_busy" if os.name == "nt" else "not_windows"
            self.assertEqual(note["decision"], expected)
            self.assertEqual(note["priority_class"], "unchanged")

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
