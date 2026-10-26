"""S-puente de punta a punta (brief F0.1 §10.2 puntos 6-12 y §10.3).

La evidencia de cada corrida es un temporal. La clave no se imprime.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

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


def _fake_peers():
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*fake_peer.py*' } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def _stop_peers():
    for pid in _fake_peers():
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            capture_output=True,
            timeout=20,
        )


def _spike(extra, evidence, timeout):
    cmd = [PY, "qa/m1_gate.py", "spike", "S-puente", "--both", "--evidence", str(evidence), *extra]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, timeout=timeout)
    return proc


def _tree_bytes(root):
    blob = b""
    for path in root.rglob("*"):
        if path.is_file():
            blob += path.read_bytes()
    return blob


class E2ESpuenteTests(unittest.TestCase):
    def tearDown(self):
        _stop_peers()

    def test_point6_default_offline_passes(self):
        with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
            evidence = Path(tmp) / "run"
            proc = _spike(["--build", "offline"], evidence, 240)
            self.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
            verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["exit_code"], 0)
            bad = [row["id"] for row in verdict["checks"] if row["status"] != "pass"]
            self.assertEqual(bad, [])
            before = (evidence / "verdict.json").read_bytes()
            manifest = (evidence / "manifest.json").read_bytes()
            again = _spike(["--build", "offline", "--evaluate-only"], evidence, 60)
            self.assertEqual(again.returncode, 0, again.stderr[-2000:])
            self.assertEqual((evidence / "verdict.json").read_bytes(), before)
            self.assertEqual((evidence / "manifest.json").read_bytes(), manifest)
            leaked = _tree_bytes(evidence)
            self.assertNotIn(b"key=", leaked)
            self.assertNotIn(b"dsbx_qa.json", leaked)
            joined = proc.stdout + proc.stderr + again.stdout + again.stderr
            self.assertNotIn(b"key=", joined)

    def test_point7_fault_matrix(self):
        for fault, expected in MATRIX:
            with self.subTest(fault=fault, expected=expected):
                with tempfile.TemporaryDirectory(prefix="dsbx-ev-") as tmp:
                    evidence = Path(tmp) / "run"
                    extra = ["--build", "offline", *FAST]
                    if fault != "none":
                        extra.extend(["--fault", fault])
                    proc = _spike(extra, evidence, 180)
                    self.assertEqual(proc.returncode, expected, proc.stderr[-2000:])
                    verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
                    self.assertEqual(verdict["exit_code"], expected)

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
            self.assertEqual(_fake_peers(), [])

    def test_point11_no_fake_peer_survives(self):
        self.assertEqual(_fake_peers(), [])


if __name__ == "__main__":
    unittest.main()
