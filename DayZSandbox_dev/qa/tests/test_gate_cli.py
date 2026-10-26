"""Reglas del CLI (brief F0.1 §3 y §10.1 punto 3)."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gate_core
import m1_gate
from s_puente_eval import evaluate

from .synth import write_case

ROOT = Path(__file__).resolve().parents[2]

PHASE_TABLE = {
    "F1": ["A1", "A5", "A6", "C4", "C5", "D2", "E1", "E2", "E3"],
    "F2": ["A1", "A2", "A3", "A4"],
    "F3": ["A2", "A3", "A4", "C1", "C2", "C3", "C4", "C5"],
    "F4": ["B1", "B2", "B3", "B4"],
    "F5": ["B4", "B5", "B6", "B7"],
    "F6": ["A6", "D1", "D2", "D3", "D4", "D5", "E1", "E2", "E3", "E4", "E5"],
}


def _fp(path):
    path = Path(path)
    if not path.exists():
        return None
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
        return digest.hexdigest()
    for child in sorted(path.rglob("*")):
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        if child.is_file():
            digest.update(child.read_bytes())
    return digest.hexdigest()


def _git():
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return proc.stdout


def _run(args):
    return subprocess.run(
        [sys.executable, "qa/m1_gate.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class GateCliTests(unittest.TestCase):
    def test_rule1_nonempty_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "ev"
            evidence.mkdir()
            marker = evidence / "keep.txt"
            marker.write_bytes(b"same\n")
            before, git_before = _fp(evidence), _git()
            proc = _run(["spike", "S-persist", "--build", "offline", "--evidence", str(evidence)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertEqual(_fp(evidence), before)
            self.assertEqual(_git(), git_before)
            self.assertFalse((evidence / "verdict.json").exists())

    def test_rule1_evaluate_only_requires_manifest_and_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            before = _fp(missing)
            proc = _run(
                ["spike", "S-puente", "--build", "offline", "--evidence", str(missing), "--both", "--evaluate-only"]
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertEqual(_fp(missing), before)
            self.assertFalse(missing.exists())

            empty = Path(tmp) / "empty"
            empty.mkdir()
            proc = _run(
                ["spike", "S-puente", "--build", "offline", "--evidence", str(empty), "--both", "--evaluate-only"]
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertEqual(list(empty.iterdir()), [])

    def test_rule2_exception_before_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "not-a-dir"
            parent.write_bytes(b"file\n")
            target = parent / "child"
            before = parent.read_bytes()
            proc = _run(["spike", "S-persist", "--build", "offline", "--evidence", str(target)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("Traceback", proc.stderr)
            self.assertFalse(target.exists())
            self.assertEqual(parent.read_bytes(), before)

    def test_rule2_exception_after_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "corrupt_line")
            proc = _run(
                ["spike", "S-puente", "--build", "offline", "--evidence", tmp, "--both", "--evaluate-only"]
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            verdict = json.loads((Path(tmp) / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["exit_code"], 2)
            self.assertTrue(verdict["error"]["traceback"].strip())
            raw = (Path(tmp) / "verdict.json").read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertNotIn(b"\r", raw)

    def test_rule3_unimplemented_and_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "ev"
            proc = _run(["spike", "S-persist", "--build", "offline", "--evidence", str(evidence)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["exit_code"], 2)
            self.assertIn("not_implemented", verdict["reasons"])
            unknown = Path(tmp) / "nope"
            proc = _run(["spike", "NOPE", "--build", "offline", "--evidence", str(unknown)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertFalse(unknown.exists())

    def test_rule4_usage_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "ev"
            cases = [
                ["spike", "S-puente", "--build", "retail", "--evidence", str(evidence), "--fault", "slow", "--both"],
                ["spike", "S-puente", "--build", "offline", "--evidence", str(evidence), "--both", "--hold-ms", "3000", "--lease-ms", "3000"],
                ["spike", "S-puente", "--build", "retail", "--evidence", str(evidence), "--both"],
                ["spike", "S-puente", "--build", "diag", "--evidence", str(evidence), "--both", "--server-profile", str(Path(tmp) / "missing-a"), "--client-profile", str(Path(tmp) / "missing-b")],
                ["phase", "F0", "--build", "offline", "--evidence", str(evidence)],
            ]
            for args in cases:
                with self.subTest(args=args):
                    before = _fp(evidence)
                    proc = _run(args)
                    self.assertEqual(proc.returncode, 2, proc.stderr)
                    self.assertEqual(_fp(evidence), before)
                    self.assertFalse(evidence.exists())

    def test_rule5_defaults(self):
        parser = m1_gate.build_parser()
        offline = parser.parse_args(["spike", "S-persist", "--build", "offline", "--evidence", "x"])
        m1_gate.validate(parser, offline)
        self.assertEqual(offline.hold_ms, 2000)
        self.assertEqual(offline.lease_ms, 3000)
        self.assertEqual(offline.ttl_ms, 5000)
        self.assertEqual(offline.retry_ms, 2000)
        self.assertEqual(offline.seed, 20261026)
        self.assertEqual(offline.peer_timeout, 20)
        with tempfile.TemporaryDirectory() as tmp:
            server = Path(tmp) / "srv"
            client = Path(tmp) / "cli"
            server.mkdir()
            client.mkdir()
            retail = parser.parse_args(
                [
                    "spike",
                    "S-persist",
                    "--build",
                    "retail",
                    "--evidence",
                    "x",
                    "--server-profile",
                    str(server),
                    "--client-profile",
                    str(client),
                ]
            )
            m1_gate.validate(parser, retail)
            self.assertEqual(retail.peer_timeout, 120)
            diag = parser.parse_args(
                [
                    "spike",
                    "S-persist",
                    "--build",
                    "diag",
                    "--evidence",
                    "x",
                    "--server-profile",
                    str(server),
                    "--client-profile",
                    str(client),
                ]
            )
            m1_gate.validate(parser, diag)
            self.assertEqual(diag.peer_timeout, 120)
            evidence = Path(tmp) / "ev"
            proc = _run(["spike", "S-persist", "--build", "offline", "--evidence", str(evidence)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["params"]["hold_ms"], 2000)
            self.assertEqual(manifest["params"]["lease_ms"], 3000)
            self.assertEqual(manifest["params"]["ttl_ms"], 5000)
            self.assertEqual(manifest["params"]["retry_ms"], 2000)
            self.assertEqual(manifest["params"]["seed"], 20261026)

    def test_rule6_requires_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "ev"
            proc = _run(["spike", "S-puente", "--build", "offline", "--evidence", str(evidence)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["exit_code"], 2)
            self.assertIn("requires_both", verdict["reasons"])

    def test_rule7_evaluate_only_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp)
            verdict = evaluate(tmp)
            gate_core.write_json(Path(tmp) / "verdict.json", verdict)
            before = (Path(tmp) / "verdict.json").read_bytes()
            manifest = (Path(tmp) / "manifest.json").read_bytes()
            proc = _run(
                ["spike", "S-puente", "--build", "offline", "--evidence", tmp, "--both", "--evaluate-only"]
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual((Path(tmp) / "verdict.json").read_bytes(), before)
            self.assertEqual((Path(tmp) / "manifest.json").read_bytes(), manifest)

    def test_rule8_criterion_phase_suite_and_phase_map(self):
        self.assertEqual(gate_core.PHASES, PHASE_TABLE)
        self.assertEqual(len(gate_core.SUITE), 28)
        self.assertEqual(gate_core.aggregate([0, 0]), 0)
        self.assertEqual(gate_core.aggregate([0, 2]), 2)
        self.assertEqual(gate_core.aggregate([2, 1, 0]), 1)
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / "criterion"
            proc = _run(["criterion", "A1", "--build", "offline", "--evidence", str(evidence)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["exit_code"], 2)
            phase = Path(tmp) / "phase"
            proc = _run(["phase", "F1", "--build", "offline", "--evidence", str(phase)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            for cid in PHASE_TABLE["F1"]:
                self.assertTrue((phase / cid / "verdict.json").is_file(), cid)
            body = json.loads((phase / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(body["exit_code"], 2)
            self.assertEqual([row["id"] for row in body["members"]], PHASE_TABLE["F1"])
            suite = Path(tmp) / "suite"
            proc = _run(["suite", "--build", "offline", "--evidence", str(suite)])
            self.assertEqual(proc.returncode, 2, proc.stderr)
            names = sorted(p.name for p in suite.iterdir() if p.is_dir())
            self.assertEqual(names, sorted(gate_core.CRITERIA))
            self.assertEqual(len(names), 28)
            suite_body = json.loads((suite / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(suite_body["exit_code"], 2)
            self.assertEqual(len(suite_body["members"]), 28)


if __name__ == "__main__":
    unittest.main()
