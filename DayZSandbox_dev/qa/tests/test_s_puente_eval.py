"""Casos del evaluador de S-puente (brief F0.1 §10.1 punto 2)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import gate_core
from s_puente_eval import EvidenceError, evaluate

from .synth import write_case

ROOT = Path(__file__).resolve().parents[2]

FAILS = (
    "p95_1000",
    "six_missing",
    "h1_frame",
    "n1_read_sentinel_server",
    "n1_read_sentinel_client",
    "n2_read_sentinel_server",
    "n2_read_sentinel_client",
    "n3_read_sentinel_server",
    "n3_read_sentinel_client",
    "n1_delivered_server",
    "n1_delivered_client",
    "n2_done_server",
    "n2_done_client",
    "n3_done_server",
    "n3_done_client",
    "n4_read_a_server",
    "n4_read_a_client",
    "n5_read_c_server",
    "n5_read_c_client",
    "n4_dup_false_server",
    "n4_dup_false_client",
    "n5_dup_false_server",
    "n5_dup_false_client",
    "n6_lease",
    "n6_order",
    "n6_pose",
)

MISSING = (
    "mix_99",
    "no_hello",
    "wrong_build",
    "one_poll",
    "n_step_empty",
    "n6_no_reject",
    "n6_missing_seq",
    "resume_timeout",
)


class SPuenteEvalTests(unittest.TestCase):
    def _code(self, defect):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, defect)
            return evaluate(tmp)["exit_code"]

    def test_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp)
            verdict = evaluate(tmp)
            self.assertEqual(verdict["exit_code"], 0)
            self.assertEqual(verdict["verdict"], "PASA")
            self.assertTrue(all(c["status"] == "pass" for c in verdict["checks"]))
            gate_core.write_json(Path(tmp) / "verdict.json", verdict)
            proc = subprocess.run(
                [
                    sys.executable,
                    "qa/m1_gate.py",
                    "spike",
                    "S-puente",
                    "--build",
                    "offline",
                    "--evidence",
                    tmp,
                    "--both",
                    "--evaluate-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_each_violation_exits_1(self):
        for defect in FAILS:
            with self.subTest(defect=defect):
                self.assertEqual(self._code(defect), 1)

    def test_each_gap_exits_2(self):
        for defect in MISSING:
            with self.subTest(defect=defect):
                self.assertEqual(self._code(defect), 2)

    def test_fail_beats_missing(self):
        self.assertEqual(self._code("fail_and_missing"), 1)

    def test_p95_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "lat_1_100")
            verdict = evaluate(tmp)
            self.assertEqual(verdict["exit_code"], 0)
            self.assertEqual(verdict["metrics"]["p95_ms"], 95)
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "five_inf")
            verdict = evaluate(tmp)
            self.assertEqual(verdict["exit_code"], 0)
            self.assertNotEqual(verdict["metrics"]["p95_ms"], "inf")
            self.assertLess(verdict["metrics"]["p95_ms"], 1000)
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "six_missing")
            verdict = evaluate(tmp)
            self.assertEqual(verdict["exit_code"], 1)
            self.assertEqual(verdict["metrics"]["p95_ms"], "inf")
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "p95_999_9")
            verdict = evaluate(tmp)
            self.assertEqual(verdict["exit_code"], 0)
            self.assertLess(verdict["metrics"]["p95_ms"], 1000)

    def test_sol01_dup_false_before_dup_true_fails(self):
        self.assertEqual(self._code("sol01_repeat_both"), 1)

    def test_sol02_repeated_mix_ids_are_missing(self):
        self.assertEqual(self._code("sol02_28_ids"), 2)

    def test_sol03_sentinel_without_deliver_is_missing(self):
        self.assertEqual(self._code("sol03_no_deliver"), 2)

    def test_sol04_n4_ignores_n6_cuts(self):
        self.assertEqual(self._code("sol04_n4_client_without_cut"), 2)

    def test_sol05_read_without_status_is_evidence_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "sol05_read_no_status")
            with self.assertRaises(EvidenceError):
                evaluate(tmp)
            proc = subprocess.run(
                [
                    sys.executable,
                    "qa/m1_gate.py",
                    "spike",
                    "S-puente",
                    "--build",
                    "offline",
                    "--evidence",
                    tmp,
                    "--both",
                    "--evaluate-only",
                ],
                cwd=ROOT,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 2)

    def test_sol05_srv_read_without_tick_s_is_not_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "sol05_srv_no_tick")
            verdict = evaluate(tmp)
            self.assertEqual(verdict["metrics"]["n_not_observed"], 1)

    def test_sol06_nan_pose_fails(self):
        self.assertEqual(self._code("sol06_nan_pose"), 1)

    def test_sol07_result_before_enq_is_evidence_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "sol07_result_before_enq")
            with self.assertRaises(EvidenceError):
                evaluate(tmp)

    def test_corrupt_jsonl_exits_2_with_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_case(tmp, "corrupt_line")
            with self.assertRaises(EvidenceError):
                evaluate(tmp)
            proc = subprocess.run(
                [
                    sys.executable,
                    "qa/m1_gate.py",
                    "spike",
                    "S-puente",
                    "--build",
                    "offline",
                    "--evidence",
                    tmp,
                    "--both",
                    "--evaluate-only",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            verdict = json.loads((Path(tmp) / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["exit_code"], 2)
            self.assertTrue(verdict["error"]["traceback"].strip())


if __name__ == "__main__":
    unittest.main()
