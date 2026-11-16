"""Pruebas offline del oráculo F2P (T2): evidencia buena, mutantes, negativas, páginas y cobertura."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import f2p_eval
import f2p_mutants
import gate_core
import m1_gate
import wire

REPO_ROOT = Path(__file__).resolve().parents[2]
QA_DIR = Path(__file__).resolve().parents[1]
FIXTURE = QA_DIR / "fixtures" / "f2p_campaign.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hydrate(campaign: dict[str, Any]) -> dict[str, Any]:
    c = copy.deepcopy(campaign)
    hashes = {
        "f2p_eval.py": _sha(QA_DIR / "f2p_eval.py"),
        "f2p_mutants.py": _sha(QA_DIR / "f2p_mutants.py"),
    }
    c["manifest"]["f2p"]["oracle_files"] = hashes
    for ev in c["samples"]["backend.jsonl"]:
        if ev.get("kind") == "oracle.frozen":
            ev["data"]["files"] = dict(hashes)
    return c


def _build(campaign: dict[str, Any], part_dir: Path) -> Path:
    part_dir.mkdir(parents=True, exist_ok=True)
    gate_core.write_json(part_dir / "manifest.json", campaign["manifest"])
    samples = part_dir / "samples"
    samples.mkdir(parents=True, exist_ok=True)
    for name, rows in campaign["samples"].items():
        (samples / name).write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8"
        )
    return part_dir


def _load_fixture() -> dict[str, Any]:
    return _hydrate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _clear_witness_tags(campaign: dict[str, Any]) -> None:
    for ev in campaign["samples"]["bridge.jsonl"]:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        read = ev.get("result", {}).get("read")
        if not isinstance(read, dict):
            continue
        u = f2p_mutants._unpack(read)
        if not u or "witness_tag" not in u[0]:
            continue
        s, n, rows = u
        s["witness_tag"] = ""
        ev["result"]["read"] = f2p_mutants._repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _set_witness_alive(campaign: dict[str, Any], value: int) -> None:
    f2p_mutants._mutate_row(
        campaign, "P2:apply",
        lambda r: str(r.get("class_name")) == "ZmbM_FarmerFat_Brown" and int(r.get("sample_idx", -1)) == 0,
        lambda r: r.__setitem__("alive_b", value),
    )


def _control_with_creature(campaign: dict[str, Any]) -> None:
    f2p_mutants._add_row(campaign, "P1:control", {
        "class_name": "ZmbM_FarmerFat_Brown", "net_id": "1:900", "parent_net_id": "",
        "pos_x_m": 6100.0, "pos_y_m": 6.0, "pos_z_m": 7700.0, "yaw_deg": 0.0,
        "tick_ms": 103100.0, "frame": 5, "ai_agent_b": 1, "sample_idx": 0, "alive_b": 1,
    })


def _gate_supports_oracle_commit() -> bool:
    if "F2P" not in gate_core.SPIKE_REGISTRY:
        return False
    parser = m1_gate.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            spike = action.choices.get("spike")
            if spike is not None:
                return any("--oracle-commit" in a.option_strings for a in spike._actions)
    return False


def _git_available() -> bool:
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                              capture_output=True, text=True, encoding="utf-8", check=False)
    except OSError:
        return False
    return proc.returncode == 0


def _checks(verdict: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in verdict.get("checks") or []}


class TestF2POracleOffline(unittest.TestCase):
    def test_positive_campaign_passes(self) -> None:
        campaign = _load_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "run")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 0, msg=json.dumps(v, indent=2))
        self.assertEqual(v["verdict"], "PASA")
        for cid in f2p_eval.CHECK_IDS:
            self.assertEqual(_checks(v)[cid]["status"], "pass", msg=cid)

    def test_each_mutant_knocks_its_check(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertTrue(spec["must_fail_checks"])
                self.assertTrue(set(spec["allowed_non_pass"]).isdisjoint(spec["must_fail_checks"]))
                campaign = f2p_mutants.mutate(base, name)
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=json.dumps(v, indent=2))
                c_map = _checks(v)
                expected_status = "fail" if spec["expected_exit_code"] == 1 else "missing"
                for cid in spec["must_fail_checks"]:
                    self.assertEqual(c_map[cid]["status"], expected_status, msg=(name, cid, c_map[cid]))
                for cid, allowed in spec["allowed_non_pass"].items():
                    self.assertIn(c_map[cid]["status"], allowed, msg=(name, cid, c_map[cid]))
                for cid in f2p_eval.CHECK_IDS:
                    if cid in spec["must_fail_checks"] or cid in spec["allowed_non_pass"]:
                        continue
                    self.assertEqual(c_map[cid]["status"], "pass", msg=(name, cid, c_map[cid]))

    def test_fabrication_negatives_never_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.NEGATIVES.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertNotEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))

    def test_oracle_files_hash_mismatch_inconcluso(self) -> None:
        campaign = _load_fixture()
        campaign["manifest"]["f2p"]["oracle_files"]["f2p_eval.py"] = "0" * 64
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "tamper")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2)
        self.assertIn("oracle_modified", v["reasons"])

    def test_pages_are_reconstructed_with_job_and_page(self) -> None:
        campaign = _load_fixture()
        probe = f2p_eval._parse_probe(campaign["samples"]["bridge.jsonl"])
        job = f2p_eval._census(probe, "P2:post")
        self.assertIsNotNone(job)
        self.assertTrue(job["valid"])
        self.assertEqual(job["rows_total"], 39)
        self.assertEqual(len(job["rows"]), 39)
        self.assertGreaterEqual(job["pages_n"], 1)
        for p, page in job["pages"].items():
            self.assertGreaterEqual(float(page["t_ms"]), 262000.0)
            self.assertLess(p, job["pages_n"])

    def test_rows_without_job_read_are_unbacked(self) -> None:
        campaign = f2p_mutants.mutate(_load_fixture(), "rows_without_raw_response")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "no_pages")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2)
        self.assertIn("unbacked_rows", v["reasons"])
        self.assertEqual(_checks(v)["F2P-01"]["status"], "missing")

    def test_coverage_gap_is_inconcluso(self) -> None:
        campaign = _load_fixture()
        f2p_mutants._remove_row(
            campaign, "P2:post", lambda r: str(r.get("class_name")) == "Animal_CervusElaphus"
        )
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "coverage")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(_checks(v)["F2P-02"]["status"], "missing")
        self.assertIn("coverage_gap", _checks(v)["F2P-02"]["detail"])

    def test_aggregate_parts(self) -> None:
        campaign = _load_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            d1 = _build(campaign, Path(tmp) / "run-diag")
            d2 = _build(campaign, Path(tmp) / "run-retail")
            agg = f2p_eval.aggregate_parts([d1, d2], repo_root=REPO_ROOT)
            self.assertEqual(agg["exit_code"], 0, msg=json.dumps(agg, indent=2))
            bad = _build(f2p_mutants.mutate(campaign, "creation_suppressed"), Path(tmp) / "run-bad")
            agg2 = f2p_eval.aggregate_parts([d1, bad], repo_root=REPO_ROOT)
            self.assertEqual(agg2["exit_code"], 1)

    def test_stale_rows_falla(self) -> None:
        campaign = _load_fixture()
        campaign = f2p_mutants.mutate(campaign, "stale_rows")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "stale")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 1)
        self.assertIn("stale_rows", v["reasons"])

    def test_section6_mutants_coverage(self) -> None:
        mapped = set()
        for item, names in f2p_mutants.SECTION6_MUTANTS.items():
            self.assertTrue(names, msg=item)
            for name in names:
                self.assertIn(name, f2p_mutants.MUTANTS, msg=(item, name))
                mapped.add(name)
        # El único mutante extra es el de la rama `delete_failed` de F2P-10.
        self.assertEqual(set(f2p_mutants.MUTANTS) - mapped, {"delete_failed_but_missing"})

    def test_section6_negatives_coverage(self) -> None:
        mapped = set()
        for item, names in f2p_mutants.SECTION6_NEGATIVES.items():
            self.assertTrue(names, msg=item)
            for name in names:
                self.assertIn(name, f2p_mutants.NEGATIVES, msg=(item, name))
                mapped.add(name)
        self.assertEqual(set(f2p_mutants.NEGATIVES) - mapped, set())

    def test_witness_tag_optional(self) -> None:
        campaign = _load_fixture()
        _clear_witness_tags(campaign)
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "tagless")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 0, msg=json.dumps(v, indent=2))

    def test_witness_alive_b_is_existence_not_alive(self) -> None:
        campaign = _load_fixture()
        _set_witness_alive(campaign, 0)
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "witness_alive")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 0, msg=json.dumps(v, indent=2))

    def test_extra_creature_with_control_noise_inconcluso(self) -> None:
        campaign = _load_fixture()
        _control_with_creature(campaign)
        f2p_mutants._m_extra_scene_creature(campaign)
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "extra_creature_noise")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2, msg=json.dumps(v, indent=2))
        self.assertEqual(_checks(v)["F2P-13"]["status"], "missing")

    @unittest.skipUnless(_gate_supports_oracle_commit(), "núcleo local sin F2P/--oracle-commit")
    def test_gate_oracle_commit_path_drops_modules(self) -> None:
        campaign = _load_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp)
            _build(campaign, evidence / "run")
            # Con f2p_eval/f2p_mutants ya en sys.modules, el gate no puede fiarse de los bytes.
            code = m1_gate.main(["spike", "F2P", "--build", "offline", "--evidence", str(evidence),
                                 "--evaluate-only", "--oracle-commit", "a" * 40])
            self.assertEqual(code, 2)
            verdict = json.loads((evidence / "run" / "verdict.json").read_text(encoding="utf-8"))
            self.assertIn("oracle_modified", verdict["reasons"])
            # Descargados, el gate puede comparar los bytes del commit congelado.
            for name in ("f2p_eval", "f2p_mutants", "f2p_run"):
                sys.modules.pop(name, None)
            code = m1_gate.main(["spike", "F2P", "--build", "offline", "--evidence", str(evidence),
                                 "--evaluate-only", "--oracle-commit", "a" * 40])
            self.assertIn(code, (0, 1, 2))


if __name__ == "__main__":
    unittest.main()
