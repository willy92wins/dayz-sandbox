"""Nucleo del gate de F2: F2P en el registro, --oracle-commit y --product-pbo (encargo P-11)."""

import argparse
import contextlib
import hashlib
import importlib
import os
import py_compile
import io
import json
import shutil
import subprocess
import sys
import types
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import f03_common
import gate_core
import m1_gate

SPIKE = "F2P"
ORACLE_FILES = {
    "qa/f2p_eval.py": (
        b"import f2p_mutants\n"
        b"ORIGIN = 'temp-repo'\n"
        b"MUT_ORIGIN = f2p_mutants.ORIGIN\n"
        b"MARKS = []\n"
        b"def mark():\n    MARKS.append(ORIGIN)\n    return ORIGIN\n"
        b"def evaluate(part_dir):\n    return None\n"
    ),
    "qa/f2p_mutants.py": b"ORIGIN = 'temp-repo'\nEXPECTED_MUTANTS = {}\nEXPECTED_HARNESS_TESTS = {}\n",
    "qa/tests/test_f2p_offline.py": b"import unittest\n",
    "qa/fixtures/f2p_base.json": b'{"a": 1}\n',
}
PREFIX = "DayZSandbox_dev/"
# Runner del repo temporal (fuera del conjunto del oraculo): ejecuta el evaluador verificado y escribe el manifest de
# la parte por PartContext, como hace el gate real; deja constancia en evidence/integration.json.
RUN_SRC = b"""import json
from pathlib import Path

import f03_common
import f2p_eval


def run(args, evidence, argv):
    marker = f2p_eval.mark()
    ctx = f03_common.PartContext(
        base_dir=Path(evidence), part_name="run", spike_id="F2P", args=args, argv=list(argv), spawn_offline_peers=False
    )
    manifest = ctx.finalize_manifest()
    info = {
        "marker": marker,
        "eval_file": f2p_eval.__file__,
        "mut_origin": f2p_eval.MUT_ORIGIN,
        "oracle_commit_arg": args.oracle_commit,
        "identity_oracle_commit": manifest["identity"]["oracle_commit"],
    }
    Path(evidence, "integration.json").write_text(json.dumps(info), encoding="utf-8")
    return 2
"""


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
        (self.qa / "f2p_run.py").write_bytes(RUN_SRC)
        _git(self.root, "init", "-q")
        _git(self.root, "config", "user.email", "qa@example.invalid")
        _git(self.root, "config", "user.name", "QA")
        _git(self.root, "add", ".")
        _git(self.root, "commit", "-q", "-m", "oracle")
        self.sha = _git(self.root, "rev-parse", "HEAD").stdout.strip()
        patcher = mock.patch.object(m1_gate, "_oracle_context", return_value=(self.root, self.qa))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.evidence = self.tmp / "ev"
        # el runner, el evaluador y los mutantes salen del repo temporal; ninguno puede estar precargado
        saved = {n: sys.modules.pop(n, None) for n in ("f2p_eval", "f2p_mutants", "f2p_run")}
        sys.path.insert(0, str(self.qa))
        importlib.invalidate_caches()

        def _restore():
            sys.path.remove(str(self.qa))
            for name, mod in saved.items():
                sys.modules.pop(name, None)
                if mod is not None:
                    sys.modules[name] = mod

        self.addCleanup(_restore)

    def ran(self):
        return (self.evidence / "integration.json").is_file()

    def integration(self):
        return json.loads((self.evidence / "integration.json").read_text(encoding="utf-8"))

    def commit_all(self, message):
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", message)
        return _git(self.root, "rev-parse", "HEAD").stdout.strip()

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
        self.assertFalse(self.ran())
        self.assertEqual(sorted(p.name for p in self.evidence.iterdir()), ["oracle_check.json", "verdict.json"])

    def test_n2_deleted_mutants(self):
        self.disk("qa/f2p_mutants.py").unlink()
        self.assert_inconcluso(_run_main(self.argv()), [f"deleted:{PREFIX}qa/f2p_mutants.py"])
        self.assertFalse(self.ran())

    def test_n3_added_fixture(self):
        self.disk("qa/fixtures/f2p_extra.json").write_bytes(b"{}\n")
        self.assert_inconcluso(_run_main(self.argv()), [f"added:{PREFIX}qa/fixtures/f2p_extra.json"])
        self.assertFalse(self.ran())

    def test_n4_unknown_commit(self):
        self.assert_inconcluso(_run_main(self.argv(sha="0" * 40)), ["commit_unavailable"])
        self.assertFalse(self.ran())

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
        self.assertFalse(self.ran())

    def test_n6_evaluate_only_leaves_part_verdicts_intact(self):
        part = self.evidence / "run"
        (part / "samples").mkdir(parents=True)
        (part / "manifest.json").write_bytes(b"{}\n")
        verdict_bytes = gate_core.dump_text(gate_core.make_verdict(SPIKE, 2, reasons=["previo"])).encode("utf-8")
        (part / "verdict.json").write_bytes(verdict_bytes)
        self.disk("qa/f2p_eval.py").write_bytes(b"changed\n")
        code = _run_main(self.argv("--evaluate-only"))
        self.assertNotIn("f2p_eval", sys.modules)  # el evaluador no se cargo ni se llamo
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
        self.assertFalse(self.ran())

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
        self.assertFalse(self.ran())

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

    # ---- ronda 2 (Sol r1) ----
    def test_shadow_package_is_oracle_modified(self):
        pkg = self.disk("qa/f2p_eval")
        pkg.mkdir()
        (pkg / "__init__.py").write_bytes(b"evaluate = None\n")
        self.assert_inconcluso(_run_main(self.argv()), [f"shadow_package:{PREFIX}qa/f2p_eval"])
        self.assertFalse(self.ran())

    def test_shadow_loose_bytecode_is_oracle_modified(self):
        self.disk("qa/f2p_mutants.pyc").write_bytes(b"\0\0\0\0")
        self.assert_inconcluso(_run_main(self.argv()), [f"shadow_bytecode:{PREFIX}qa/f2p_mutants.pyc"])

    def test_pycache_bytecode_is_never_executed(self):
        sentinel = self.tmp / "pyc_sentinel.txt"
        evil_src = self.tmp / "evil_src.py"
        evil_src.write_text(
            f"open({str(sentinel)!r}, 'w').close()\nORIGIN = 'evil'\ndef evaluate(part_dir):\n    return None\n",
            encoding="utf-8",
        )
        cache = self.disk("qa/__pycache__")
        cache.mkdir()
        py_compile.compile(
            str(evil_src), cfile=str(cache / f"f2p_eval.{sys.implementation.cache_tag}.pyc"), doraise=True,
            invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH,
        )
        sys.modules.pop("f2p_eval", None)
        sys.path.insert(0, str(self.qa))
        self.addCleanup(sys.path.remove, str(self.qa))
        importlib.invalidate_caches()
        _run_main(self.argv())
        self.assertTrue(self.ran())
        self.assertFalse(sentinel.exists())
        self.assertEqual(sys.modules["f2p_eval"].ORIGIN, "temp-repo")

    def test_uppercase_frozen_fixture_deleted_is_detected(self):
        self.disk("qa/fixtures/F2P_Extra.json").write_bytes(b"{}\n")
        sha2 = self.commit_all("add upper fixture")
        self.disk("qa/fixtures/F2P_Extra.json").unlink()
        self.assert_inconcluso(_run_main(self.argv(sha=sha2)), [f"deleted:{PREFIX}qa/fixtures/F2P_Extra.json"])

    def test_enumeration_failure_is_a_failed_check(self):
        real = gate_core._git_bytes

        def fake(root, *args):
            if args and args[0] == "ls-tree":
                return 128, b""
            return real(root, *args)

        with mock.patch.object(gate_core, "_git_bytes", side_effect=fake):
            code = _run_main(self.argv())
        self.assert_inconcluso(code, ["enumeration_failed:commit", "enumeration_failed:head"])
        self.assertFalse(self.ran())

    def test_fixture_only_in_head_is_head_differs(self):
        self.disk("qa/fixtures/f2p_head.json").write_bytes(b"{}\n")
        self.commit_all("fixture only in head")
        self.disk("qa/fixtures/f2p_head.json").unlink()
        self.assert_inconcluso(_run_main(self.argv()), [f"head_differs:{PREFIX}qa/fixtures/f2p_head.json"])

    def test_moving_refs_and_expressions_are_rejected(self):
        branch = _git(self.root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        self.disk("qa/other.txt").write_bytes(b"x")
        self.commit_all("move head")
        for ref in ("HEAD", "HEAD~0", self.sha + "^", self.sha + "~0", branch, "deadbeefzz", self.sha[:6]):
            with self.subTest(ref=ref):
                shutil.rmtree(self.evidence, ignore_errors=True)
                argv = self.argv()
                argv[argv.index("--oracle-commit") + 1] = ref
                self.assert_inconcluso(_run_main(argv), ["commit_unavailable"])
        # nombre de rama hexadecimal que apunta a otro commit: el id resuelto no empieza por lo dado
        hexbranch = "abcdef1"
        _git(self.root, "branch", hexbranch, "HEAD")
        shutil.rmtree(self.evidence, ignore_errors=True)
        self.assert_inconcluso(_run_main(self.argv(sha=hexbranch)), ["commit_unavailable"])
        self.assertFalse(self.ran())

    def test_read_error_is_failed_check_not_exit_1(self):
        real = Path.read_bytes

        def boom(path):
            if path.name == "f2p_eval.py":
                raise PermissionError("denied")
            return real(path)

        with mock.patch.object(Path, "read_bytes", boom):
            code = _run_main(self.argv())
        self.assert_inconcluso(code, ["check_error:PermissionError"])
        self.assertFalse(self.ran())

    def _evaluate_only_with_alias(self, make_alias):
        part = self.evidence / "run"
        (part / "samples").mkdir(parents=True)
        (part / "manifest.json").write_bytes(b"{}\n")
        verdict_bytes = gate_core.dump_text(gate_core.make_verdict(SPIKE, 2, reasons=["previo"])).encode("utf-8")
        (part / "verdict.json").write_bytes(verdict_bytes)
        make_alias(self.evidence / "verdict.json", part / "verdict.json")
        self.disk("qa/f2p_eval.py").write_bytes(b"changed\n")
        code = _run_main(self.argv("--evaluate-only"))
        self.assert_inconcluso(code, [f"modified:{PREFIX}qa/f2p_eval.py"])
        self.assertEqual((part / "verdict.json").read_bytes(), verdict_bytes)
        self.assertFalse((self.evidence / "verdict.json").is_symlink())

    def test_root_verdict_symlinked_to_part_is_not_written_through(self):
        def link(dst, target):
            try:
                os.symlink(target, dst)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"no se pueden crear symlinks sin privilegios en este host: {exc}")

        self._evaluate_only_with_alias(link)

    def test_root_verdict_hardlinked_to_part_is_not_written_through(self):
        self._evaluate_only_with_alias(lambda dst, target: os.link(target, dst))

    def test_root_verdict_symlink_detection_with_patched_is_symlink(self):
        # cobertura sin privilegios: el alias se detecta por is_symlink y se desvincula antes de escribir
        part = self.evidence / "run"
        part.mkdir(parents=True)
        (part / "verdict.json").write_bytes(b"part\n")
        root_file = self.evidence / "verdict.json"
        root_file.write_bytes(b"alias\n")
        evidence = self.evidence
        with mock.patch.object(Path, "is_symlink", lambda p_: p_.name == "verdict.json" and p_.parent == evidence), \
                mock.patch.object(Path, "unlink", autospec=True, side_effect=Path.unlink) as unl:
            m1_gate._write_root_file(evidence, "verdict.json", {"k": 1})
        unl.assert_called_once()
        self.assertEqual((part / "verdict.json").read_bytes(), b"part\n")
        self.assertEqual(json.loads(root_file.read_text(encoding="utf-8")), {"k": 1})

    # ---- ronda 3 (Sol r2) ----
    def test_preloaded_oracle_or_runner_module_fails_closed(self):
        for name in ("f2p_eval", "f2p_mutants", "f2p_run"):
            with self.subTest(name=name):
                shutil.rmtree(self.evidence, ignore_errors=True)
                sys.modules[name] = types.ModuleType(name)
                try:
                    self.assert_inconcluso(_run_main(self.argv()), [f"preloaded_module:{name}"])
                finally:
                    sys.modules.pop(name, None)
                self.assertFalse(self.ran())

    def test_git_escaped_fixture_name_is_in_the_census(self):
        name = "f2p_\u00f1.json"
        self.disk(f"qa/fixtures/{name}").write_bytes(b"{}\n")
        sha2 = self.commit_all("accent fixture")
        self.disk(f"qa/fixtures/{name}").unlink()
        self.assert_inconcluso(_run_main(self.argv(sha=sha2)), [f"deleted:{PREFIX}qa/fixtures/{name}"])

    def test_evidence_subfolder_alias_via_patched_realpath_is_refused(self):
        part = self.evidence / "run"
        (part / "samples").mkdir(parents=True)
        (part / "manifest.json").write_bytes(b"{}\n")
        (part / "verdict.json").write_bytes(b"part\n")
        real = os.path.realpath
        evidence = self.evidence

        def fake(path, *a, **k):
            return str(evidence) if Path(path).name == "run" else real(path, *a, **k)

        with mock.patch.object(os.path, "realpath", fake):
            reason = m1_gate._alias_reason(evidence)
            code = _run_main(self.argv("--evaluate-only"))
        self.assertIn("subfolder", reason)
        self.assertEqual(code, 2)
        self.assertEqual((part / "verdict.json").read_bytes(), b"part\n")
        self.assertFalse((evidence / "oracle_check.json").exists())

    def test_evidence_subfolder_junction_to_evidence_is_refused(self):
        ev = self.evidence
        (ev / "samples").mkdir(parents=True)
        (ev / "manifest.json").write_bytes(b"{}\n")
        (ev / "verdict.json").write_bytes(b"root\n")
        link = ev / "run"
        try:
            os.symlink(ev, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(ev)], capture_output=True, text=True)
            if proc.returncode != 0:
                self.skipTest(f"no se puede crear symlink ni junction en este host: {proc.stdout.strip()}")
        self.addCleanup(lambda: os.rmdir(link) if os.path.lexists(link) and (link.is_symlink() or os.path.isjunction(link)) else None)
        self.disk("qa/f2p_eval.py").write_bytes(b"changed\n")
        code = _run_main(self.argv("--evaluate-only"))
        self.assertEqual(code, 2)
        self.assertEqual((ev / "verdict.json").read_bytes(), b"root\n")
        self.assertFalse((ev / "oracle_check.json").exists())

    def test_failure_writing_oracle_check_does_not_corrupt_hardlinked_part(self):
        part = self.evidence / "run"
        (part / "samples").mkdir(parents=True)
        (part / "manifest.json").write_bytes(b"{}\n")
        (part / "verdict.json").write_bytes(b"part\n")
        os.link(part / "verdict.json", self.evidence / "verdict.json")
        real = gate_core.write_json

        def flaky(path, obj):
            if Path(path).name == "oracle_check.json":
                raise OSError("injected")
            return real(path, obj)

        with mock.patch.object(gate_core, "write_json", flaky):
            code = _run_main(self.argv("--evaluate-only"))
        self.assertEqual(code, 2)
        self.assertEqual((part / "verdict.json").read_bytes(), b"part\n")
        root = json.loads((self.evidence / "verdict.json").read_text(encoding="utf-8"))
        self.assertEqual(root["exit_code"], 2)
        self.assertEqual(root["error"]["type"], "OSError")

    def test_n9_oracle_commit_with_s_puente_is_usage_error(self):
        code = _run_main(["spike", "S-puente", "--both", "--build", "offline", "--evidence", str(self.evidence),
                          "--oracle-commit", self.sha])
        self.assertEqual(code, 2)
        self.assertFalse(self.evidence.exists())


class OracleCommitPositiveTests(_TempRepo):
    def test_p1_intact_oracle_runs_and_records_commit(self):
        code = _run_main(self.argv())
        self.assertEqual(code, 2)
        self.assertTrue(self.ran())
        info = self.integration()
        self.assertEqual(info["oracle_commit_arg"], self.sha)
        check = self.check_json()
        self.assertTrue(check["ok"])
        self.assertEqual(check["problems"], [])
        self.assertEqual(check["commit"], self.sha)
        self.assertEqual(
            sorted(f["path"] for f in check["files"]),
            sorted(PREFIX + rel for rel in ORACLE_FILES),
        )
        self.assertTrue(all(f["status"] == "ok" and f["blob_sha"] for f in check["files"]))
        # el modulo que ejecuta el gate es el cargado de los bytes verificados, no el del repo real
        loaded = sys.modules["f2p_eval"]
        self.assertEqual(loaded.ORIGIN, "temp-repo")
        self.assertEqual(Path(loaded.__file__), Path(os.path.realpath(self.disk("qa/f2p_eval.py"))))
        self.assertEqual(Path(sys.modules["f2p_mutants"].__file__), Path(os.path.realpath(self.disk("qa/f2p_mutants.py"))))
        # misma invocacion: el evaluador que corrio es el verificado y el manifest de la parte lleva el sha completo
        self.assertEqual(info["marker"], "temp-repo")
        self.assertEqual(info["mut_origin"], "temp-repo")  # el import cruzado eval -> mutants resolvio al verificado
        self.assertEqual(Path(info["eval_file"]), Path(os.path.realpath(self.disk("qa/f2p_eval.py"))))
        self.assertEqual(info["identity_oracle_commit"], self.sha)
        manifest = json.loads((self.evidence / "run" / "manifest.json").read_text(encoding="utf-8")) \
            if (self.evidence / "run" / "manifest.json").is_file() else None
        if manifest is not None:
            self.assertEqual(manifest["identity"]["oracle_commit"], self.sha)
        self.assertIsNone(_part_manifest(self.tmp / "q")["identity"]["oracle_commit"])

    def test_unknown_part_with_intact_oracle_exits_2_without_running(self):
        code = _run_main(self.argv("--part", "nope"))
        self.assertEqual(code, 2)
        self.assertFalse(self.ran())
        self.assertTrue(self.check_json()["ok"])

    def test_accented_fixture_intact_is_ok(self):
        name = "f2p_\u00f1.json"
        self.disk(f"qa/fixtures/{name}").write_bytes(b"{}\n")
        sha2 = self.commit_all("accent fixture")
        _run_main(self.argv(sha=sha2))
        check = self.check_json()
        self.assertTrue(check["ok"], check["problems"])
        self.assertIn(f"{PREFIX}qa/fixtures/{name}", [f["path"] for f in check["files"]])
        self.assertTrue(self.ran())

    def test_known_part_with_intact_oracle_runs(self):
        _run_main(self.argv("--part", "run"))
        self.assertTrue(self.ran())

    def test_short_sha_is_stored_resolved(self):
        _run_main(self.argv(sha=self.sha[:10]))
        self.assertEqual(self.integration()["oracle_commit_arg"], self.sha)

    def test_without_option_nothing_is_checked(self):
        self.disk("qa/fixtures/f2p_base.json").write_bytes(b"changed\n")
        code = _run_main(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(self.evidence)])
        self.assertEqual(code, 2)
        self.assertTrue(self.ran())
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

    def test_p3_dispatch_reaches_registry_run_and_evaluate(self):
        # Modulos centinela propios de la prueba: no dependen del contenido de qa/f2p_*.py (que los sustituye el oraculo).
        calls = []
        run_mod = types.ModuleType("f2p_run")
        eval_mod = types.ModuleType("f2p_eval")
        mut_mod = types.ModuleType("f2p_mutants")

        def _run(args, evidence, argv):
            calls.append(("run", args.id, Path(evidence).name))
            return 1

        def _evaluate(part_dir):
            calls.append(("evaluate", Path(part_dir).name))
            return gate_core.make_verdict(SPIKE, 1, reasons=["sentinel_eval"])

        run_mod.run = _run
        eval_mod.evaluate = _evaluate
        mut_mod.EXPECTED_MUTANTS = {}
        mut_mod.EXPECTED_HARNESS_TESTS = {}
        saved = {n: sys.modules.get(n) for n in ("f2p_run", "f2p_eval", "f2p_mutants")}

        def _restore():
            for name, mod in saved.items():
                sys.modules.pop(name, None)
                if mod is not None:
                    sys.modules[name] = mod

        self.addCleanup(_restore)
        sys.modules.update({"f2p_run": run_mod, "f2p_eval": eval_mod, "f2p_mutants": mut_mod})

        code = _run_main(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(self.ev)])
        self.assertEqual(code, 1)  # el exit del run del registro se devuelve tal cual
        self.assertEqual(calls, [("run", SPIKE, "ev")])

        calls.clear()
        ev2 = self.tmp / "ev2"
        part = ev2 / "run"
        (part / "samples").mkdir(parents=True)
        (part / "manifest.json").write_bytes(b"{}\n")
        code = _run_main(["spike", SPIKE, "--both", "--build", "offline", "--evidence", str(ev2), "--evaluate-only"])
        self.assertEqual(calls, [("evaluate", "run")])
        pv = json.loads((part / "verdict.json").read_text(encoding="utf-8"))
        self.assertEqual((pv["id"], pv["exit_code"], pv["reasons"]), (SPIKE, 1, ["sentinel_eval"]))
        self.assertEqual(code, 2)  # la agregacion del nucleo (falta part.json) decide el exit, no el centinela

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
