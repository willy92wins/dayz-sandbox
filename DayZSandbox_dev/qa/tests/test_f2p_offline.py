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
import f03_common
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


def _drop_first_part_result(campaign: dict[str, Any], part: str) -> str | None:
    manifest = campaign["manifest"]
    win = next((p for p in manifest["f2p"]["parts"] if p["name"] == part), None)
    if win is None:
        return None
    tap = campaign["samples"]["bridge_tap.jsonl"]
    for ev in tap:
        if ev.get("dir") != "resp" or ev.get("path") != "/poll":
            continue
        t = float(ev.get("t_ms") or 0.0)
        if not (float(win["start_t_ms"]) <= t <= float(win["end_t_ms"])):
            continue
        for o in (ev.get("body") or {}).get("ops") or []:
            if not isinstance(o, dict):
                continue
            if str(o.get("verb") or "") not in ("scene.apply", "scene.reset", "scene.observe",
                                                "state.read"):
                continue
            oid = str(o.get("op_id") or "")
            campaign["samples"]["bridge_tap.jsonl"] = [
                x for x in tap if not (x.get("dir") == "req" and x.get("path") == "/result" and
                                       str((x.get("body") or {}).get("op_id")) == oid)]
            return oid
    return None


def _control_with_creature(campaign: dict[str, Any]) -> None:
    f2p_mutants._add_row(campaign, "P1:control", {
        "class_name": "ZmbM_FarmerFat_Brown", "net_id": "1:900", "parent_net_id": "",
        "pos_x_m": 6100.0, "pos_y_m": 6.0, "pos_z_m": 7700.0, "yaw_deg": 0.0,
        "tick_ms": 103100.0, "frame": 5, "ai_agent_b": 1, "sample_idx": 0, "alive_b": 1,
        "surface_y_m": 6.0,
    })


def _as_offline_run(campaign: dict[str, Any]) -> dict[str, Any]:
    """Convierte la campaña en una parte `run` offline con identidad y sellos reales del arnés."""
    git_head = gate_core.git_harness(repo_root=REPO_ROOT)["git_head"]
    if not git_head:
        raise unittest.SkipTest("git no disponible para la identidad del arnés")
    stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=REPO_ROOT)
    params = {
        "wire_cap": wire.WIRE_CAP,
        "probe_budget_log_poll_ms": f03_common.PROBE_BUDGET_LOG_POLL_MS,
        "probe_budget_retry_ms": f03_common.PROBE_BUDGET_RETRY_MS,
    }
    manifest = campaign["manifest"]
    manifest["build"] = "offline"
    manifest["params"] = dict(params)
    ident = manifest["identity"]
    ident["build"] = "offline"
    ident["git_head"] = git_head
    ident["git_dirty"] = False
    ident["probe_stamp"] = stamp
    ident["params"] = dict(params)
    ident["peer_builds"] = {"server": "offline", "client": "offline"}
    probe_ver = "dsbx-qa1+" + stamp
    for ev in campaign["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "hello" and isinstance(ev.get("args"), dict):
            ev["args"]["build"] = "offline"
            ev["args"]["probe_ver"] = probe_ver
    return campaign


def _write_run_part(campaign: dict[str, Any], part_dir: Path, nonce: str) -> dict[str, Any]:
    """Parte `run` completa del arnés: manifest, samples, part.json con `op_nonce` y verdict.json."""
    _build(campaign, part_dir)
    (part_dir / "part.json").write_text(
        json.dumps({"op_nonce": nonce, "part": "run", "spike_id": "F2P", "op_map": []}) + "\n",
        encoding="utf-8",
    )
    verdict = f2p_eval.evaluate(part_dir, repo_root=REPO_ROOT)
    gate_core.write_json(part_dir / "verdict.json", verdict)
    return verdict


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
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
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
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
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

    def test_oracle_commit_split_inconcluso(self) -> None:
        # H-7: `identity.oracle_commit`, `f2p.oracle_commit` y el evento `oracle.frozen` tienen que ser
        # el mismo id de 40 hex; si no, INCONCLUSO `oracle_modified`.
        campaign = f2p_mutants.mutate(_load_fixture(), "oracle_commit_split")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "commit_split")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2, msg=json.dumps(v, indent=2))
        self.assertIn("oracle_modified", v["reasons"])

    def test_pages_are_reconstructed_with_job_and_page(self) -> None:
        campaign = _load_fixture()
        probe = f2p_eval._parse_probe(campaign["samples"]["bridge.jsonl"])
        job = f2p_eval._census(probe, "P2:post")
        self.assertIsNotNone(job)
        self.assertTrue(job["valid"])
        # §6.1 punto 9: el censo puede traer botín de la CE (p. ej. Barrel_Yellow) además de la
        # base (11) y de las 33 creaciones; la reconstrucción no exige un total fijo, solo que las
        # páginas cuadren con `rows_total_n` y que estén las 33 raíces.
        self.assertEqual(job["rows_total"], len(job["rows"]))
        self.assertGreaterEqual(job["rows_total"], 33 + 11)
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

    @unittest.skipUnless("F2P" in gate_core.SPIKE_REGISTRY, "núcleo local sin F2P")
    def test_acceptance_by_core_aggregation(self) -> None:
        # H-3/O-15 (§7): la misma evidencia sintética, completada como una parte `run` del arnés de
        # F0.3, pasa por `f03_common.aggregate_spike`: la positiva PASA, un mutante da FALLA y una
        # negativa nunca PASA. Sin EXPECTED_MUTANTS, la agregación exige solo la parte `run`.
        self.assertFalse(hasattr(f2p_mutants, "EXPECTED_MUTANTS"))
        base = _as_offline_run(_load_fixture())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            pos = _write_run_part(base, root / "pos" / "run", "1111222233334444")
            self.assertEqual(pos["exit_code"], 0, msg=json.dumps(pos, indent=2))
            agg = f03_common.aggregate_spike(root / "pos", "F2P", repo_root=REPO_ROOT)
            self.assertEqual(agg["exit_code"], 0, msg=json.dumps(agg, indent=2))
            self.assertEqual(agg["verdict"], "PASA")

            mut = _write_run_part(f2p_mutants.mutate(base, "creation_suppressed"),
                                  root / "mut" / "run", "aaaabbbbccccdddd")
            self.assertEqual(mut["exit_code"], 1, msg=json.dumps(mut, indent=2))
            agg_mut = f03_common.aggregate_spike(root / "mut", "F2P", repo_root=REPO_ROOT)
            self.assertEqual(agg_mut["exit_code"], 1, msg=json.dumps(agg_mut, indent=2))
            self.assertEqual(agg_mut["verdict"], "FALLA")

            neg = _write_run_part(f2p_mutants.mutate(base, "job_mismatch"),
                                  root / "neg" / "run", "9999aaaabbbbcccc")
            self.assertNotEqual(neg["exit_code"], 0, msg=json.dumps(neg, indent=2))
            agg_neg = f03_common.aggregate_spike(root / "neg", "F2P", repo_root=REPO_ROOT)
            self.assertNotEqual(agg_neg["exit_code"], 0, msg=json.dumps(agg_neg, indent=2))

    def test_stale_rows_inconcluso(self) -> None:
        # §6.1 punto 1: una medición tomada antes del efecto que juzga no es una FALLA, es una
        # medición no respaldada (INCONCLUSO `unbacked_rows`).
        campaign = _load_fixture()
        campaign = f2p_mutants.mutate(campaign, "stale_rows")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "stale")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2, msg=json.dumps(v, indent=2))
        self.assertIn("unbacked_rows", v["reasons"])
        self.assertEqual(_checks(v)["F2P-01"]["status"], "missing")

    def test_section6_mutants_coverage(self) -> None:
        mapped = set()
        for item, names in f2p_mutants.SECTION6_MUTANTS.items():
            self.assertTrue(names, msg=item)
            for name in names:
                self.assertIn(name, f2p_mutants.MUTANTS, msg=(item, name))
                mapped.add(name)
        # El único mutante extra de §6 es el de la rama `delete_failed` de F2P-10; los casos de
        # Sol del punto 4 viven en `SOL_MUTANTS` y tienen su propia prueba.
        self.assertEqual(set(f2p_mutants.MUTANTS) - mapped, {"delete_failed_but_missing"})

    def test_section6_negatives_coverage(self) -> None:
        mapped = set()
        for item, names in f2p_mutants.SECTION6_NEGATIVES.items():
            self.assertTrue(names, msg=item)
            for name in names:
                self.assertIn(name, f2p_mutants.NEGATIVES, msg=(item, name))
                mapped.add(name)
        self.assertEqual(set(f2p_mutants.NEGATIVES) - mapped, set())

    def test_sol_cases_coverage(self) -> None:
        # Punto 4 de T2d-1: cada caso de Sol tiene su mutante, negativa o variante positiva.
        mapped = {spec["name"] for spec in f2p_mutants.SOL_CASES.values()}
        self.assertEqual(mapped, set(f2p_mutants.SOL_MUTANTS) | set(f2p_mutants.SOL_NEGATIVES) |
                         set(f2p_mutants.SOL_POSITIVES))
        expected = {
            "census_before_first_P2_apply", "P2_snapshot_tick_zero",
            "P2_pages_from_other_instance_without_hello",
            "confirmed_alive_hidden_by_unbacked_next_census",
            "P2n_uncompensated_new_generation_entity",
            "creature_confirmed_missing_only_from_original_disk",
            "delivery_and_result_session_differ_P2",
            "P3_reset_opstate_without_received_result",
            "reconciliation_delivered_without_result", "witness_radius_1m_and_window_1ms",
            "missing_control_and_three_operation_witnesses", "no_server_restart_events",
            "normal_opstate_transitions_before_terminal", "legitimate_fresh_P3_generation",
            "good_creature_tracked_by_extra_disk", "33_correct_roots_plus_background_Apple",
            "creatures_born_50m_above_surface", "fake_tick1_is_33seconds_late",
            "P5_total34_with_one_displaced_leftover", "P5_K_is_only_unrelated_Apple",
            "scene2_yaw_changed", "scene2_tent_rotated_90_on_reset1", "scene2_20m_up_P3c",
            "foreign_moved_on_second_reset", "no_spawn_raw_no_cleanup_evidence",
            "F2_reappears_1m_away", "delete_confirm_one_tick_after_request",
            "copy_perturbation_0p01_instead_of_0p1",
            "H4_control_creature_AI_initializes_at_tick1",
        }
        self.assertEqual(set(f2p_mutants.SOL_CASES), expected)

    def test_sol_mutants_knock_their_check(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS.items():
            with self.subTest(mutant=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in spec["must_fail_status"].items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                if spec.get("allow_other_non_pass"):
                    continue
                allowed = spec.get("allowed_non_pass") or {}
                for cid in f2p_eval.CHECK_IDS:
                    if cid in spec["must_fail_status"]:
                        continue
                    if cid in allowed:
                        self.assertIn(c_map[cid]["status"], allowed[cid],
                                      msg=(name, cid, c_map[cid]))
                    else:
                        self.assertEqual(c_map[cid]["status"], "pass", msg=(name, cid, c_map[cid]))

    def test_sol_negatives_never_pass(self) -> None:
        base = _load_fixture()
        for name in f2p_mutants.SOL_NEGATIVES:
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertNotEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))
                self.assertIn("unbacked_rows", v["reasons"], msg=(name, v["reasons"]))

    def test_sol_positives_pass(self) -> None:
        base = _load_fixture()
        for name in f2p_mutants.SOL_POSITIVES:
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_delete_confirm_metric_measures_request_to_confirmation(self) -> None:
        # O-17: la métrica informa la separación entre la petición y la confirmación del mismo
        # borrado (33 ms), no la resta de la propia línea confirmatoria.
        campaign = f2p_mutants.mutate(_load_fixture(), "sol_delete_confirm_request")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "delete_metric")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 0, msg=json.dumps(v, indent=2))
        self.assertAlmostEqual(float(v["metrics"]["delete_confirm_max_ms"]), 33.0, places=3)

    def test_surface_y_absent_in_witness_is_inconcluso(self) -> None:
        campaign = f2p_mutants.mutate(_load_fixture(), "surface_y_absent_witness")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "surface_absent_witness")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2, msg=json.dumps(v, indent=2))
        self.assertEqual(_checks(v)["F2P-02"]["status"], "missing")
        self.assertIn("surface_unbacked", _checks(v)["F2P-02"]["detail"])

    def test_rows_copied_from_backend_are_unbacked(self) -> None:
        campaign = f2p_mutants.mutate(_load_fixture(), "rows_copied_from_backend")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "rows_backend")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2, msg=json.dumps(v, indent=2))
        self.assertIn("unbacked_rows", v["reasons"])
        self.assertEqual(_checks(v)["F2P-01"]["status"], "missing")

    def test_trace_violation_knocks_its_part_check(self) -> None:
        # Punto 1 de T2d-2: una violación de traza tumba la comprobación de su parte, no F2P-01.
        cases = (("P2n", "F2P-03"), ("P3c", "F2P-06"), ("P4b", "F2P-07"), ("P4c", "F2P-07"))
        for part, cid in cases:
            with self.subTest(part=part):
                campaign = _load_fixture()
                oid = _drop_first_part_result(campaign, part)
                self.assertIsNotNone(oid, msg=part)
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / f"trace_{part}")
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(_checks(v)[cid]["status"], "fail",
                                 msg=(part, cid, json.dumps(v, indent=2)))

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
        # §6 (v1.3.6, errata de la v1.3.4): H4_control_creature_AI_initializes_at_tick1 lleva una
        # criatura de más y la ventana de control tuvo criaturas; por F2P-13 es INCONCLUSO, no PASA.
        campaign = _load_fixture()
        _control_with_creature(campaign)
        f2p_mutants._m_extra_scene_creature(campaign)
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "extra_creature_noise")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2, msg=json.dumps(v, indent=2))
        self.assertEqual(_checks(v)["F2P-13"]["status"], "missing")
        self.assertIn("control_had_creatures", _checks(v)["F2P-13"]["detail"])

    @unittest.skipUnless(_gate_supports_oracle_commit(), "núcleo local sin F2P/--oracle-commit")
    def test_gate_oracle_commit_path_drops_modules(self) -> None:
        # H-1/H-2: con un commit irresoluble el núcleo corta en `commit_unavailable` antes de mirar
        # `sys.modules`; escribe `oracle_check.json` y `verdict.json` en la RAÍZ de la evidencia, no en
        # `run/`, y no evalúa nada. El caso de módulos precargados ya lo prueba #20.
        campaign = _load_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp)
            _build(campaign, evidence / "run")
            code = m1_gate.main(["spike", "F2P", "--build", "offline", "--evidence", str(evidence),
                                 "--evaluate-only", "--oracle-commit", "a" * 40])
            self.assertEqual(code, 2)
            root_verdict = json.loads((evidence / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(root_verdict["verdict"], "INCONCLUSO")
            self.assertIn("oracle_modified", root_verdict["reasons"])
            check = json.loads((evidence / "oracle_check.json").read_text(encoding="utf-8"))
            self.assertFalse(check["ok"])
            self.assertIn("commit_unavailable", check["problems"])
            self.assertFalse((evidence / "run" / "verdict.json").exists())


if __name__ == "__main__":
    unittest.main()
