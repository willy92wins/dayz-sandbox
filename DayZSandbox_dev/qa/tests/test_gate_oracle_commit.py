"""Nucleo del gate de F2: F2P en el registro, --oracle-commit y --product-pbo (encargo P-11)."""

import argparse
import contextlib
import hashlib
import importlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import f03_common
import f2p_eval
import f2p_run
import gate_core
import m1_gate

SPIKE = "F2P"
ORACLE_FILES = {
    "qa/f2p_eval.py": b"def evaluate(part_dir):\n    return None\n",
    "qa/f2p_mutants.py": b"EXPECTED_MUTANTS = {}\nEXPECTED_HARNESS_TESTS = {}\n",
    "qa/tests/test_f2p_offline.py": b"import unittest\n",
    "qa/fixtures/f2p_base.json": b'{"a": 1}\n',
}
PREFIX = "DayZSandbox_dev/"


def _git(root, *args):
    return subprocess.run(
        ["git", "-c", "core.autocrlf=false", *args], cwd=str(root), capture_output=True, text=True, check=True
    )


def _run_main(argv):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return m1_gate.main(argv)


def _part_manifest(base_dir, **extra):
    args = argparse.Namespace(build="offline", both=True, **extra)
    ctx = f03_common.PartContext(
        base_dir=Path(base_dir), part_name="run", spike_id=SPIKE, args=args, argv=[], spawn_offline_peers=False
    )
    return ctx.finalize_manifest()


class _TempRepo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dsbx-oracle-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "repo"
        self.qa = self.root / "DayZSandbox_dev" / "qa"
        for rel, data in ORACLE_FILES.items():
            path = self.root / "DayZSandbox_dev" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "qa@example.invalid")
        _git(self.root, "config", "user.name", "QA")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "oracle")
        self.sha = _git(self.root, "rev-parse", "HEAD").stdout.strip()
        patcher = mock.patch.object(m1_gate, "_oracle_context", return_value=(self.root, self.qa))
        patcher.start()
        self.addCleanup(patcher.stop)
        run_patcher = mock.patch.object(f2p_run, "run", return_value=2)
        self.run_mock = run_patcher.start()
        self.addCleanup(run_patcher.stop)
        self.evidence = self.tmp / "ev"

    def disk(self, rel):
        return self.root / "DayZSandbox_dev" / rel

    def argv(self, *extra, sha=None):
        return ["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(self.evidence),
                "--oracle-commit", sha or self.sha, *extra]

    def check_json(self):
        return json.loads((self.evidence / "oracle_check.json").read_text(encoding="utf-8"))

    def assert_inconcluso(self, code, problems):
        self.assertEqual(code, 2)
        verdict = json.loads((self.evidence / "verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(verdict["exit_code"], 2)
        self.assertEqual(verdict["reasons"], ["oracle_modified"])
        self.assertEqual(verdict, gate_core.make_verdict(SPIKE, 2, reasons=["oracle_modified"]))
        check = self.check_json()
        self.assertFalse(check["ok"])
        self.assertEqual(check["problems"], problems)
        return check


class OracleCommitNegativeTests(_TempRepo):
    def test_n1_modified_byte_blocks_run_and_parts(self):
        path = self.disk("qa/f2p_eval.py")
        path.write_bytes(path.read_bytes().replace(b"None", b"Nonf"))
        self.assert_inconcluso(_run_main(self.argv()), [f"modified:{PREFIX}qa/f2p_eval.py"])
        self.run_mock.assert_not_called()
        self.assertEqual(sorted(p.name for p in self.evidence.iterdir()), ["oracle_check.json", "verdict.json"])

    def test_n2_deleted_mutants(self):
        self.disk("qa/f2p_mutants.py").unlink()
        self.assert_inconcluso(_run_main(self.argv()), [f"deleted:{PREFIX}qa/f2p_mutants.py"])
        self.run_mock.assert_not_called()

    def test_n3_added_fixture(self):
        self.disk("qa/fixtures/f2p_extra.json").write_bytes(b"{}\n")
        self.assert_inconcluso(_run_main(self.argv()), [f"added:{PREFIX}qa/fixtures/f2p_extra.json"])
        self.run_mock.assert_not_called()

    def test_n4_unknown_commit(self):
        self.assert_inconcluso(_run_main(self.argv(sha="0" * 40)), ["commit_unavailable"])
        self.run_mock.assert_not_called()

    def test_n4b_option_like_commit(self):
        argv = self.argv()
        argv[argv.index("--oracle-commit") : argv.index("--oracle-commit") + 2] = ["--oracle-commit=--all"]
        self.assert_inconcluso(_run_main(argv), ["commit_unavailable"])

    def test_n5_commit_without_offline_test(self):
        self.disk("qa/tests/test_f2p_offline.py").unlink()
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "drop test")
        sha2 = _git(self.root, "rev-parse", "HEAD").stdout.strip()
        self.assert_inconcluso(
            _run_main(self.argv(sha=sha2)), [f"missing_at_commit:{PREFIX}qa/tests/test_f2p_offline.py"]
        )
        self.run_mock.assert_not_called()

    def test_n6_evaluate_only_leaves_part_verdicts_intact(self):
        part = self.evidence / "run"
        (part / "samples").mkdir(parents=True)
        (part / "manifest.json").write_bytes(b"{}\n")
        verdict_bytes = gate_core.dump_text(gate_core.make_verdict(SPIKE, 2, reasons=["previo"])).encode("utf-8")
        (part / "verdict.json").write_bytes(verdict_bytes)
        self.disk("qa/f2p_eval.py").write_bytes(b"changed\n")
        with mock.patch.object(f2p_eval, "evaluate") as ev:
            code = _run_main(self.argv("--evaluate-only"))
        ev.assert_not_called()
        self.assert_inconcluso(code, [f"modified:{PREFIX}qa/f2p_eval.py"])
        self.assertEqual((part / "verdict.json").read_bytes(), verdict_bytes)

    def test_n7_only_line_endings_differ(self):
        path = self.disk("qa/f2p_eval.py")
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assert_inconcluso(_run_main(self.argv()), [f"modified:{PREFIX}qa/f2p_eval.py"])

    def test_n8_head_differs_though_disk_matches_commit(self):
        path = self.disk("qa/f2p_eval.py")
        path.write_bytes(b"other\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", "move head")
        path.write_bytes(ORACLE_FILES["qa/f2p_eval.py"])  # el disco vuelve a casar con self.sha; HEAD no
        self.assert_inconcluso(_run_main(self.argv()), [f"head_differs:{PREFIX}qa/f2p_eval.py"])
        self.run_mock.assert_not_called()

    def test_n13_modified_mutants_module_is_never_imported(self):
        sentinel = self.tmp / "sentinel.txt"
        evil = (
            "import gate_core\n"
            f"open({str(sentinel)!r}, 'w').write('x')\n"
            "gate_core.check_oracle_files = lambda *a, **k: {'ok': True, 'commit': 'x', 'files': [], 'problems': []}\n"
            "EXPECTED_MUTANTS = {}\nEXPECTED_HARNESS_TESTS = {}\n"
        )
        self.disk("qa/f2p_mutants.py").write_bytes(evil.encode("utf-8"))
        # el modulo de mutantes que se importaria es el del repo temporal (modificado)
        sys.path.insert(0, str(self.qa))
        self.addCleanup(sys.path.remove, str(self.qa))
        real = sys.modules.pop("f2p_mutants", None)
        self.addCleanup(lambda: (sys.modules.pop("f2p_mutants", None), real and sys.modules.__setitem__("f2p_mutants", real)))
        importlib.invalidate_caches()
        original = gate_core.check_oracle_files
        self.addCleanup(setattr, gate_core, "check_oracle_files", original)
        code = _run_main(self.argv("--part", "run"))
        self.assert_inconcluso(code, [f"modified:{PREFIX}qa/f2p_mutants.py"])
        self.assertFalse(sentinel.exists())
        self.run_mock.assert_not_called()

    def test_n13_control_sentinel_fires_if_the_module_is_imported(self):
        sentinel = self.tmp / "sentinel.txt"
        self.disk("qa/f2p_mutants.py").write_bytes(
            f"open({str(sentinel)!r}, 'w').write('x')\nEXPECTED_MUTANTS = {{}}\nEXPECTED_HARNESS_TESTS = {{}}\n".encode()
        )
        sys.path.insert(0, str(self.qa))
        self.addCleanup(sys.path.remove, str(self.qa))
        real = sys.modules.pop("f2p_mutants", None)
        self.addCleanup(lambda: (sys.modules.pop("f2p_mutants", None), real and sys.modules.__setitem__("f2p_mutants", real)))
        importlib.invalidate_caches()
        importlib.import_module("f2p_mutants")
        self.assertTrue(sentinel.exists())

    def test_case_insensitive_fixture_is_reported_as_added_with_real_name(self):
        self.disk("qa/fixtures/F2P_Extra.json").write_bytes(b"{}\n")
        self.assert_inconcluso(_run_main(self.argv()), [f"added:{PREFIX}qa/fixtures/F2P_Extra.json"])

    def test_n9_oracle_commit_with_s_puente_is_usage_error(self):
        code = _run_main(["spike", "S-puente", "--both", "--build", "offline", "--evidence", str(self.evidence),
                          "--oracle-commit", self.sha])
        self.assertEqual(code, 2)
        self.assertFalse(self.evidence.exists())


class OracleCommitPositiveTests(_TempRepo):
    def test_p1_intact_oracle_runs_and_records_commit(self):
        code = _run_main(self.argv())
        self.assertEqual(code, 2)
        self.run_mock.assert_called_once()
        args = self.run_mock.call_args[0][0]
        self.assertEqual(args.oracle_commit, self.sha)
        check = self.check_json()
        self.assertTrue(check["ok"])
        self.assertEqual(check["problems"], [])
        self.assertEqual(check["commit"], self.sha)
        self.assertEqual(
            sorted(f["path"] for f in check["files"]),
            sorted(PREFIX + rel for rel in ORACLE_FILES),
        )
        self.assertTrue(all(f["status"] == "ok" and f["blob_sha"] for f in check["files"]))
        # la parte lleva identity.oracle_commit; sin la opcion, null
        manifest = _part_manifest(self.tmp / "p", oracle_commit=args.oracle_commit)
        self.assertEqual(manifest["identity"]["oracle_commit"], self.sha)
        self.assertIsNone(_part_manifest(self.tmp / "q")["identity"]["oracle_commit"])

    def test_unknown_part_with_intact_oracle_exits_2_without_running(self):
        code = _run_main(self.argv("--part", "nope"))
        self.assertEqual(code, 2)
        self.run_mock.assert_not_called()
        self.assertTrue(self.check_json()["ok"])

    def test_known_part_with_intact_oracle_runs(self):
        _run_main(self.argv("--part", "run"))
        self.run_mock.assert_called_once()

    def test_short_sha_is_stored_resolved(self):
        _run_main(self.argv(sha=self.sha[:10]))
        self.assertEqual(self.run_mock.call_args[0][0].oracle_commit, self.sha)

    def test_without_option_nothing_is_checked(self):
        self.disk("qa/f2p_eval.py").write_bytes(b"changed\n")
        code = _run_main(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(self.evidence)])
        self.assertEqual(code, 2)
        self.run_mock.assert_called_once()
        self.assertFalse((self.evidence / "oracle_check.json").exists())


class ProductPboTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dsbx-ppbo-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pbo = self.tmp / "probe.pbo"
        self.pbo.write_bytes(b"probe")
        self.product = self.tmp / "product.pbo"
        self.product.write_bytes(b"product-bytes")
        (self.tmp / "srv").mkdir()
        (self.tmp / "cli").mkdir()
        self.ev = self.tmp / "ev"

    def retail(self, build, *extra):
        return ["spike", SPIKE, "--both", "--build", build, "--evidence", str(self.ev),
                "--server-profile", str(self.tmp / "srv"), "--client-profile", str(self.tmp / "cli"),
                "--pbo", str(self.pbo), *extra]

    def test_n10_retail_and_diag_require_valid_product_pbo(self):
        not_pbo = self.tmp / "product.txt"
        not_pbo.write_bytes(b"x")
        for build in ("retail", "diag"):
            for extra in ([], ["--product-pbo", str(self.tmp / "missing.pbo")], ["--product-pbo", str(not_pbo)]):
                self.assertEqual(_run_main(self.retail(build, *extra)), 2, (build, extra))
                self.assertFalse(self.ev.exists())

    def test_n10_message_names_the_missing_option(self):
        parser = m1_gate.build_parser()
        args = parser.parse_args(self.retail("retail"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            m1_gate.validate(parser, args)
        self.assertIn("retail/diag F2P requires --product-pbo", err.getvalue())

    def test_retail_with_product_pbo_passes_validation(self):
        parser = m1_gate.build_parser()
        for build in ("retail", "diag"):
            args = parser.parse_args(self.retail(build, "--product-pbo", str(self.product)))
            m1_gate.validate(parser, args)

    def test_evaluate_only_does_not_require_product_pbo(self):
        parser = m1_gate.build_parser()
        args = parser.parse_args(["spike", SPIKE, "--both", "--build", "retail", "--evidence", str(self.ev),
                                  "--evaluate-only"])
        m1_gate.validate(parser, args)

    def test_p2_offline_valid_product_pbo_is_hashed_into_identity(self):
        parser = m1_gate.build_parser()
        args = parser.parse_args(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(self.ev),
                                  "--product-pbo", str(self.product), "--pbo", str(self.pbo)])
        m1_gate.validate(parser, args)
        ident = _part_manifest(self.tmp / "m", pbo=str(self.pbo), product_pbo=str(self.product))["identity"]
        self.assertEqual(ident["product_pbo_sha256"], hashlib.sha256(b"product-bytes").hexdigest())
        self.assertEqual(ident["pbo_sha256"], hashlib.sha256(b"probe").hexdigest())
        self.assertIsNone(_part_manifest(self.tmp / "n")["identity"]["product_pbo_sha256"])

    def test_offline_invalid_product_pbo_is_usage_error(self):
        code = _run_main(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(self.ev),
                          "--product-pbo", str(self.tmp / "missing.pbo")])
        self.assertEqual(code, 2)
        self.assertFalse(self.ev.exists())

    def test_p3_offline_run_not_implemented_and_evaluate_reaches_f2p_eval(self):
        code = _run_main(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(self.ev)])
        self.assertEqual(code, 2)
        verdict = json.loads((self.ev / "verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(verdict["reasons"], ["not_implemented"])
        ev2 = self.tmp / "ev2"
        part = ev2 / "run"
        (part / "samples").mkdir(parents=True)
        (part / "manifest.json").write_bytes(b"{}\n")
        with mock.patch.object(f2p_eval, "evaluate", wraps=f2p_eval.evaluate) as ev:
            code = _run_main(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(ev2),
                              "--evaluate-only"])
        self.assertEqual(code, 2)
        ev.assert_called_once()
        pv = json.loads((part / "verdict.json").read_text(encoding="utf-8"))
        self.assertEqual((pv["id"], pv["reasons"]), (SPIKE, ["not_implemented"]))

    def test_registry_entry(self):
        self.assertEqual(gate_core.SPIKE_REGISTRY[SPIKE], ("f2p_run", "f2p_eval", "f2p_mutants"))
        self.assertEqual(gate_core.PRODUCT_PBO_SPIKES, frozenset({"F2P"}))


class AggregationIdentityTests(unittest.TestCase):
    MUTANTS = {"m1": {}}

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dsbx-agg-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write_part(self, name, nonce, build="offline", **ident_extra):
        pdir = self.tmp / name
        (pdir / "samples").mkdir(parents=True)
        ident = {"build": build, "git_head": "a" * 40, "git_dirty": False, "params": {"seed": 1},
                 "probe_stamp": "s", "peer_builds": {}, "pbo_sha256": "p" * 64}
        ident.update(ident_extra)
        gate_core.write_json(pdir / "manifest.json", {"build": build, "identity": ident})
        gate_core.write_json(pdir / "verdict.json", gate_core.make_verdict(SPIKE, 0))
        gate_core.write_json(pdir / "part.json", {"op_nonce": nonce, "part": name, "spike_id": SPIKE})

    def reasons(self, run=None, mut=None):
        run = dict(run or {})
        mut = dict(mut or {})
        self.write_part("run", "0123456789abcdef", **run)
        self.write_part("mut-m1", "fedcba9876543210", **mut)
        return f03_common.aggregate_spike(self.tmp, SPIKE, repo_root=self.tmp, expected_mutants=self.MUTANTS)["reasons"]

    def test_n11_product_pbo_differs(self):
        self.assertEqual(
            self.reasons({"product_pbo_sha256": "1" * 64}, {"product_pbo_sha256": "2" * 64}), ["mixed_parts"]
        )

    def test_n11_oracle_commit_differs(self):
        self.assertEqual(self.reasons({"oracle_commit": "1" * 40}, {"oracle_commit": "2" * 40}), ["mixed_parts"])

    def test_n12_retail_part_without_product_pbo(self):
        self.assertEqual(
            self.reasons({"build": "retail", "product_pbo_sha256": "1" * 64}, {"build": "retail"}), ["mixed_parts"]
        )

    def test_n12_retail_all_parts_without_product_pbo(self):
        self.assertEqual(self.reasons({"build": "retail"}, {"build": "retail"}), ["mixed_parts"])

    def test_same_identity_does_not_mix(self):
        same = {"product_pbo_sha256": "1" * 64, "oracle_commit": "2" * 40}
        self.assertNotIn("mixed_parts", self.reasons(same, same))

    def test_keys_absent_are_none_and_do_not_mix_offline(self):
        self.assertNotIn("mixed_parts", self.reasons())


if __name__ == "__main__":
    unittest.main()
