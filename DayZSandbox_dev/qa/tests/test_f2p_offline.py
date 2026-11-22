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
    # R-14: `evaluate` lee `part_dir/../oracle_check.json`. Las pruebas lo escriben en su evidencia
    # con el commit del manifest (salvo que la campaña traiga uno explícito o lo anule).
    check = campaign.get("oracle_check", "default")
    if check == "default":
        check = {"ok": True, "commit": campaign["manifest"]["identity"]["oracle_commit"],
                 "files": [], "problems": []}
    if check is not None:
        gate_core.write_json(part_dir.parent / "oracle_check.json", check)
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
            # v1.3.14: el tap es completo; al quitar el /result hay que quitar tambien su acuse
            # (si no, queda una respuesta huerfana y la traza no se puede juzgar).
            rid = next((x.get("req_id") for x in tap
                        if x.get("dir") == "req" and x.get("path") == "/result" and
                        str((x.get("body") or {}).get("op_id")) == oid), None)
            kept = [
                x for x in tap
                if not (x.get("dir") == "req" and x.get("path") == "/result" and
                        str((x.get("body") or {}).get("op_id")) == oid) and
                not (rid is not None and x.get("dir") == "resp" and
                     x.get("path") == "/result" and x.get("req_id") == rid)]
            req_ids = {x.get("req_id") for x in kept if x.get("dir") == "req"}
            campaign["samples"]["bridge_tap.jsonl"] = [
                x for x in kept if x.get("dir") == "req" or x.get("req_id") in req_ids]
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
        # V-16: el arnés real lleva `ttl_ms` en `identity.params`; la retención de F2P-04 lo necesita.
        "ttl_ms": campaign["manifest"]["params"]["ttl_ms"],
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
        # Punto 4 de T2d-1 y T2e-1: cada caso de Sol (r1 y r2) tiene su mutante, negativa o variante
        # positiva, y todos están en la tabla única `SOL_CASES`.
        mapped = {spec["name"] for spec in f2p_mutants.SOL_CASES.values()}
        self.assertEqual(mapped, set(f2p_mutants.SOL_MUTANTS) | set(f2p_mutants.SOL_NEGATIVES) |
                         set(f2p_mutants.SOL_POSITIVES) | set(f2p_mutants.SOL_MUTANTS_R2) |
                         set(f2p_mutants.SOL_NEGATIVES_R2) | set(f2p_mutants.SOL_POSITIVES_R2) |
                          set(f2p_mutants.SOL_MUTANTS_R3) | set(f2p_mutants.SOL_NEGATIVES_R3) |
                          set(f2p_mutants.SOL_POSITIVES_R3) |
                          set(f2p_mutants.SOL_INCONCLUSO_R3) |
                          set(f2p_mutants.SOL_MUTANTS_R4) | set(f2p_mutants.SOL_NEGATIVES_R4) |
                          set(f2p_mutants.SOL_POSITIVES_R4) |
                          set(f2p_mutants.SOL_INCONCLUSO_R4) |
                           set(f2p_mutants.SOL_MUTANTS_R5) | set(f2p_mutants.SOL_NEGATIVES_R5) |
                           set(f2p_mutants.SOL_POSITIVES_R5) |
                           set(f2p_mutants.SOL_MUTANTS_R6) | set(f2p_mutants.SOL_NEGATIVES_R6) |
                           set(f2p_mutants.SOL_POSITIVES_R6) |
                           set(f2p_mutants.SOL_MUTANTS_R7) | set(f2p_mutants.SOL_NEGATIVES_R7) |
                           set(f2p_mutants.SOL_POSITIVES_R7) |
                           set(f2p_mutants.SOL_MUTANTS_R8) | set(f2p_mutants.SOL_NEGATIVES_R8) |
                           set(f2p_mutants.SOL_POSITIVES_R8) |
                           set(f2p_mutants.SOL_MUTANTS_R9) | set(f2p_mutants.SOL_NEGATIVES_R9) |
                           set(f2p_mutants.SOL_POSITIVES_R9) |
                           set(f2p_mutants.SOL_MUTANTS_R10) | set(f2p_mutants.SOL_NEGATIVES_R10) |
                           set(f2p_mutants.SOL_POSITIVES_R10) |
                           set(f2p_mutants.SOL_MUTANTS_R11) | set(f2p_mutants.SOL_NEGATIVES_R11) |
                           set(f2p_mutants.SOL_POSITIVES_R11) |
                           set(f2p_mutants.SOL_MUTANTS_R12) | set(f2p_mutants.SOL_NEGATIVES_R12) |
                           set(f2p_mutants.SOL_POSITIVES_R12) |
                           set(f2p_mutants.SOL_MUTANTS_R13) | set(f2p_mutants.SOL_NEGATIVES_R13) |
                           set(f2p_mutants.SOL_POSITIVES_R13) |
                           set(f2p_mutants.SOL_MUTANTS_R14) | set(f2p_mutants.SOL_NEGATIVES_R14) |
                           set(f2p_mutants.SOL_POSITIVES_R14) |
                           set(f2p_mutants.SOL_MUTANTS_R15) | set(f2p_mutants.SOL_NEGATIVES_R15) |
                           set(f2p_mutants.SOL_POSITIVES_R15))
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
            # Sol r2 (T2e-1): R-01, R-02, R-03, R-05, R-06, R-07, R-10, R-11, R-14 y R-15.
            "r2_R01_checkpoint_in_obs", "r2_R01_checkpoint_missing",
            "r2_R02_reconciliation_without_event", "r2_R02_empty_reconciliation_read",
            "r2_R03_external_clock_origin",
            "r2_R05_no_deliver", "r2_R05_hello_after_delivery", "r2_R05_p2_terminal_missing",
            "r2_R05_snap_frame_zero", "r2_R05_spawn_raw_no_deliver",
            "r2_R05_spawn_raw_unstamped",
            "r2_R06_unbacked_previous_census", "r2_R07_extra_disk_survivor",
            "r2_R10_result_conn_mismatch", "r2_R10_missing_acks",
            "r2_R10_second_result_before_delivery",
            "r2_R11_p2_window_short", "r2_R11_p5_window_before_cut", "r2_R11_no_cut_event",
            "r2_R14_oracle_check_mismatch", "r2_R14_oracle_check_missing",
            "r2_R15_witness_overlap", "r2_R15_start_args_incomplete",
            # Sol r2 (T2e-2): R-04, R-08, R-09, R-12, R-13, R-16 y R-17.
            "r2_R04_creature_deletes_pass", "r2_R04_creature_coverage_gap",
            "r2_R08_p2n_residue_displaced", "r2_R08_duplicate_scene2_root",
            "r2_R08_p5_leftovers_plus_25",
            "r2_R09_same_epoch_restart", "r2_R09_control_creation_missing",
            "r2_R09_reappears_at_last_known",
            "r2_R12_ce_loot_between_resets", "r2_R13_slope_supported",
            "r2_R13_horizontal_0p6", "r2_R13_unsupported_2p3",
            "r2_R16_rows_copied_from_backend", "r2_R17_metric_first_request",
            # Sol r3 y la pasada de Claude (T2f-1).
            "r3_S01_page_epoch_empty", "r3_S01_delivery_instance",
            "r3_S01_stimulus_response_instance", "r3_S01_selectors_zero",
            "r3_S01_rows_captured_n", "r3_S09_parcial_sin_resultado",
            "cl_V04_cut_no_terminal",
            "r3_S03_p3_reuses_p2_nets", "r3_S03_p4a_keeps_old_root",
            "r3_S03_p5_cargo_root", "r3_S03_p4b_zero_roots",
            "r3_S04_creature_walk_1m", "cl_V06_ce_loot_in_window",
            "r3_S02_early_extra_disks", "r3_S02_extra_epoch_wrong",
            "r3_S12_no_valid_position", "r3_S07_rejected_acks",
            "r3_S07_delivery_without_result", "cl_V01_state_read_without_obs",
            "r3_S08_bogus_obs", "r3_S11_pages_before_close", "r3_S06_overlap",
            "cl_V02_ticks_per_epoch", "r3_V05_p5_windows_overlap", "cl_V05_no_overlap",
            "r3_S10_confirmed_alive_e2", "cl_V07_p4c_two_epochs",
            # v1.3.9: identidad por (sesión, op_id), órdenes internas y reinicio del backend.
            "v139_ids_repeated_across_sessions", "v139_terminal_from_other_session",
            "v139_rd_op_state", "v139_cut_result_resent_rejected",
            "v139_poll_409_after_restart",
            # T2f-3 (v1.3.10).
            "v139_two_sessions_one_segment", "v139_session_repeats_between_segments",
            "v1310_product_hp_minus1", "v1310_product_hp_real",
            "r3_S05_V03_p5_two_witnesses", "r3_S05_no_reconciliation_before_apply2",
            "r3_S05_k_zero", "r3_S05_cut_result_accepted",
            "r3_S13_ce_loot_zone_inconcluso", "r3_S13_exact_reappearance",
            "r3_S13_scene_class_not_ce_near", "r3_V11_control_missing_census",
            "r3_V11_control_bad_mark", "r3_V11_control_in_zone",
            "cl_V17_ce_object_in_window_inconcluso",
            "r3_S14_exact_0p5", "r3_V10_land_wreck_origin_1p3",
            "r3_V10_creature_unsupported_0p15",
            "r3_V16_ttl_missing", "r3_V16_outside_retention",
            "r3_V18_no_cleanup_inconcluso", "r3_R04_creature_deletes_realistic",
            "r3_R04_infected_coverage_gap", "r3_S16_creature_231_isolated",
            # T2f-4 (v1.3.11): F-01 a F-13 y A-01.
            "r4_F01_start_epoch_empty", "r4_A01_result_other_inst",
            "r4_F02_disks_delayed_20s", "r4_F02_lid_relabel_231",
            "r4_F03_no_p5_restart", "r4_F03_p5_restart_unbacked",
            "r4_F03_read_before_restart",
            "r4_F03_cut_births_after_cut", "r4_F03_p3_no_reconciliation",
            "r4_F04_result_inst_epoch", "r4_F04_query_body_session",
            "r4_F04_hello_rejected", "r4_F04_ack_ok_string",
            "r4_F04_foreign_rejected_cut_id",
            "r4_F05_p2_create_failed", "r4_F05_invented_state",
            "r4_F06_p4a_apply1_zero", "r4_F06_p4b_vanish", "r4_F06_p5_obj180_moved",
            "r4_F07_201_in_post_reset2", "r4_F07_cleanup_apple_alive",
            "r4_F08_control_prev_instance", "r4_F08_invalid_component",
            "r4_F08_census_1m_empty", "r4_F08_control_created_minus1",
            "r4_F09_infected_moved_10m", "r4_F10_fireplace_child_p2",
            "r4_F11_e2_renumbered",
            "r4_F12_ce_extra_p2", "r4_F12_ce_extra_p4a", "r4_F12_ce_extra_p4b",
            "r4_F12_ce_extra_p5",
            "r4_F13_p4a_real_survivor_401", "r4_F13_terminal_other_session",
        }
        expected |= set(f2p_mutants.SOL_CASES_R5)
        expected |= set(f2p_mutants.SOL_CASES_R6)
        expected |= set(f2p_mutants.SOL_CASES_R7)
        expected |= set(f2p_mutants.SOL_CASES_R8)
        expected |= set(f2p_mutants.SOL_CASES_R9)
        expected |= set(f2p_mutants.SOL_CASES_R10)
        expected |= set(f2p_mutants.SOL_CASES_R11)
        expected |= set(f2p_mutants.SOL_CASES_R12)
        expected |= set(f2p_mutants.SOL_CASES_R13)
        expected |= set(f2p_mutants.SOL_CASES_R14)
        expected |= set(f2p_mutants.SOL_CASES_R15)
        self.assertEqual(set(f2p_mutants.SOL_CASES), expected)
        # Los diecisiete R-nn de T2e-1 y T2e-2 tienen al menos un caso con prefijo r2_R.
        r2_rnn = {k.split("_")[1] for k in f2p_mutants.SOL_CASES if k.startswith("r2_R")}
        self.assertEqual(r2_rnn, {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08",
                                  "R09", "R10", "R11", "R12", "R13", "R14", "R15", "R16",
                                  "R17"})

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

    def test_sol_r2_mutants_knock_their_check(self) -> None:
        # Sol r2 (T2e-1): cada mutante r2 tumba la comprobación que declara.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R2.items():
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

    def test_sol_r2_negatives_never_pass(self) -> None:
        # Sol r2 (T2e-1): las negativas de procedencia/frescura dan INCONCLUSO `unbacked_rows`.
        base = _load_fixture()
        for name in f2p_mutants.SOL_NEGATIVES_R2:
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertNotEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))
                self.assertIn("unbacked_rows", v["reasons"], msg=(name, v["reasons"]))

    def test_sol_r2_positives_pass(self) -> None:
        # Sol r2 (T2e-1): R-01 con el checkpoint real en obs, R-02 sin el evento inventado y R-03
        # con otro origen del reloj externo son partidas buenas.
        base = _load_fixture()
        for name in f2p_mutants.SOL_POSITIVES_R2:
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_sol_r3_mutants_knock_their_check(self) -> None:
        # Sol r3 y la v1.3.9 (T2f-2): cada mutante tumba la comprobación que declara.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R3.items():
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

    def test_sol_r3_negatives_never_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R3.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertNotEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))
                if name == "v139_rd_op_state":
                    # v1.3.9: un `op.state` con id `rd-N` no es del backend y rompe la traza.
                    self.assertIn("tap_trace_mismatch", v["reasons"],
                                  msg=(name, json.dumps(v, indent=2)))

    def test_sol_r3_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R3.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r4_mutants_knock_their_check(self) -> None:
        # T2f-4 (v1.3.11): cada caso r4_ de Sol r4 tumba la comprobación y el motivo de la tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R4.items():
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
                # F-13: el motivo concreto de la tabla, no solo el estado.
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r4_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R4.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r4_positives_pass(self) -> None:
        base = _load_fixture()
        for name in f2p_mutants.SOL_POSITIVES_R4:
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], 0, msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r4_inconcluso_variants(self) -> None:
        # F-12 y F-13: INCONCLUSO con su motivo, sin ningún FALLA.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_INCONCLUSO_R4.items():
            with self.subTest(inconcluso=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], 2, msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                self.assertFalse(any(c["status"] == "fail" for c in c_map.values()),
                                 msg=(name, json.dumps(v, indent=2)))
                for cid, reason in spec["must_missing"].items():
                    self.assertEqual(c_map[cid]["status"], "missing", msg=(name, cid, c_map[cid]))
                    text = c_map[cid]["detail"] + " " + " ".join(map(str, v.get("reasons") or []))
                    self.assertIn(reason, text, msg=(name, cid, c_map[cid]))

    def test_r4_native_probe_conformance(self) -> None:
        # v1.3.11 (F-01/A-01): las líneas reales de las diags, copiadas tal cual, dan trabajos
        # válidos con el epoch de su lectura de arranque. Cada diag se parsea como un run.
        data = json.loads((QA_DIR / "fixtures" / "f2p_native_probe.json").read_text(encoding="utf-8"))
        by_file: dict[str, list[dict[str, Any]]] = {}
        for e in data["entries"]:
            by_file.setdefault(str(e["file"]), []).append(json.loads(e["line"]))
        self.assertGreaterEqual(len(by_file), 2)
        probe_vers = set()
        for file, events in by_file.items():
            probe = f2p_eval._parse_probe(events)
            jobs = [j for j in probe["jobs"].values() if j["valid"]]
            self.assertTrue(jobs, msg=file)
            for j in jobs:
                self.assertTrue(j.get("epoch"), msg=(file, j.get("tag")))
                self.assertRegex(str(j["epoch"]), r"^[0-9a-f]{32}$", msg=(file, j.get("tag")))
            for h in probe["hellos"]:
                if h.get("probe_ver"):
                    probe_vers.add(h["probe_ver"])
        self.assertIn("dsbx-qa1+33aa01add6d21896", probe_vers)
        for e in data["entries"]:
            ev = json.loads(e["line"])
            if ev.get("ev") == "result":
                # A-01: el evento `result` del bridge no lleva `inst`.
                self.assertNotIn("inst", ev, msg=e["line_no"])
                read = (ev.get("result") or {}).get("read")
                if isinstance(read, dict) and "page_n" in (read.get("nk") or []):
                    # F-01: las páginas de `job_read` no llevan `server_epoch`.
                    self.assertNotIn("server_epoch", read.get("sk") or [], msg=e["line_no"])

    def test_r5_mutants_knock_their_check(self) -> None:
        # T2f-5 (v1.3.12): cada caso r5_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R5.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r5_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R5.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r5_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R5.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r6_mutants_knock_their_check(self) -> None:
        # T2f-6 (v1.3.12): cada caso r6_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R6.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r6_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R6.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r6_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R6.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r7_mutants_knock_their_check(self) -> None:
        # T2f-7 (v1.3.13): cada caso r7_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R7.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r7_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R7.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r7_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R7.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r8_mutants_knock_their_check(self) -> None:
        # T2f-8: cada caso r8_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R8.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r8_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R8.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r8_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R8.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r9_mutants_knock_their_check(self) -> None:
        # T2f-9: cada caso r9_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R9.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r9_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R9.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r9_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R9.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r10_mutants_knock_their_check(self) -> None:
        # T2f-10: cada caso r10_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R10.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r10_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R10.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r10_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R10.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r11_mutants_knock_their_check(self) -> None:
        # T2f-11: cada caso r11_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R11.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r11_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R11.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r11_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R11.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r12_mutants_knock_their_check(self) -> None:
        # T2f-12: cada caso r12_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R12.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
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

    def test_r12_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R12.items():
            with self.subTest(negative=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec["expected_exit_code"],
                                 msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                for cid, status in (spec.get("must_fail_status") or {}).items():
                    self.assertEqual(c_map[cid]["status"], status, msg=(name, cid, c_map[cid]))
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))
                if spec.get("must_reason"):
                    self.assertIn(spec["must_reason"], v["reasons"], msg=(name, v["reasons"]))

    def test_r12_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R12.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r13_mutants_knock_their_check(self) -> None:
        # T2f-13: cada caso r13_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R13.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))

    def test_r13_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R13.items():
            with self.subTest(negative=name):
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))

    def test_r13_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R13.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r14_mutants_knock_their_check(self) -> None:
        # T2f-14: cada caso r14_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R14.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))

    def test_r14_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R14.items():
            with self.subTest(negative=name):
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))

    def test_r14_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R14.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_r15_mutants_knock_their_check(self) -> None:
        # T2f-15: cada caso r15_ exige el estado, el motivo y el exit de su tabla.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_MUTANTS_R15.items():
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))

    def test_r15_negatives(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_NEGATIVES_R15.items():
            with self.subTest(negative=name):
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
                for cid, text in (spec.get("must_detail") or {}).items():
                    self.assertIn(text, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))

    def test_r15_positives_pass(self) -> None:
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_POSITIVES_R15.items():
            with self.subTest(positive=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], spec.get("expected_exit_code", 0),
                                 msg=(name, json.dumps(v, indent=2)))
                self.assertEqual(v["verdict"], "PASA")

    def test_tap_req_id_matches_real_proxy_capture(self) -> None:
        # v1.3.14 (§5.4): el tap numera cada peticion con un req_id unico y repite el mismo en su
        # respuesta. Contraste con las partidas reales de F1b-peers (HECHOS.txt) y con la fixture.
        ev = Path(REPO_ROOT) / "evidence" / "m1" / "F1b-peers"
        files = sorted(ev.glob("*/samples/proxy.jsonl"))
        self.assertTrue(files, "faltan las capturas de F1b-peers")
        for f in files:
            ids = []
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                self.assertIsInstance(row.get("req_id"), int, msg=(str(f), row))
                ids.append(row["req_id"])
            self.assertEqual(sorted(ids), list(range(len(ids))),
                             msg=(str(f), "req_id unicos y sin huecos"))
            # El orden del log es por fin de peticion, no por req_id: no se exige ascendente.
            self.assertGreaterEqual(len(ids), 1)
        campaign = _load_fixture()
        tap = campaign["samples"]["bridge_tap.jsonl"]
        reqs = [e for e in tap if e.get("dir") == "req"]
        resps = [e for e in tap if e.get("dir") == "resp"]
        req_ids = [e.get("req_id") for e in reqs]
        self.assertTrue(all(isinstance(r, int) for r in req_ids), msg="peticion sin req_id")
        self.assertEqual(len(set(req_ids)), len(req_ids), msg="req_id de peticion duplicado")
        resp_ids = [e.get("req_id") for e in resps]
        self.assertTrue(all(isinstance(r, int) for r in resp_ids), msg="respuesta sin req_id")
        self.assertEqual(len(set(resp_ids)), len(resp_ids), msg="req_id de respuesta duplicado")
        self.assertEqual(set(resp_ids), set(req_ids), msg="respuesta sin su peticion")
        self.assertEqual(len(reqs), len(resps), msg="respuesta o peticion huerfana")

    def test_fixture_product_reads_pass_real_validators(self) -> None:
        # R-15: las lecturas del producto de la fixture pasan los validadores reales del backend.
        repo = str(REPO_ROOT)
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from app.backend import scene_plan
        from app.backend.bridge import valid_world_read
        from app.backend.scene_live import _valid_read_compat
        campaign = _load_fixture()
        reads: list[tuple[str, dict[str, Any]]] = []
        for ev in campaign["samples"]["bridge_tap.jsonl"]:
            if ev.get("dir") != "req" or ev.get("path") != "/result":
                continue
            body = ev.get("body") or {}
            if body.get("status") not in ("done", "error"):
                continue
            read = body.get("read")
            if isinstance(read, dict) and "epoch" in read:
                reads.append((str(body.get("op_id") or ""), read))
        self.assertTrue(reads, msg="la fixture no trae lecturas del producto")
        checkpoints = 0
        for op_id, read in reads:
            self.assertTrue(valid_world_read(read), msg=("valid_world_read", op_id))
            self.assertTrue(_valid_read_compat(read, require_obs=None, world_size=16384),
                            msg=("_valid_read_compat", op_id))
            self.assertTrue(scene_plan.valid_scene_read(read, require_obs=None, world_size=16384),
                            msg=("valid_scene_read", op_id))
            obs = read.get("obs")
            if isinstance(obs, dict) and obs.get("at") == "checkpoint":
                checkpoints += 1
                self.assertTrue(scene_plan.valid_scene_read(read, require_obs="checkpoint",
                                                           world_size=16384),
                                msg=("checkpoint", op_id))
        self.assertGreaterEqual(checkpoints, 1, msg="la fixture no trae checkpoint en read.obs")

    def test_delete_confirm_metric_measures_request_to_confirmation(self) -> None:
        # O-17: la métrica informa la separación entre la petición y la confirmación del mismo
        # borrado (33 ms), no la resta de la propia línea confirmatoria.
        campaign = f2p_mutants.mutate(_load_fixture(), "sol_delete_confirm_request")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "delete_metric")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 0, msg=json.dumps(v, indent=2))
        self.assertAlmostEqual(float(v["metrics"]["delete_confirm_max_ms"]), 33.0, places=3)

    def test_delete_metric_uses_first_request(self) -> None:
        # R-17: petición, señal intermedia y confirmación separadas 33 ms; la métrica va desde la
        # PRIMERA petición (66 ms), no desde la última señal (33 ms).
        campaign = f2p_mutants.mutate(_load_fixture(), "r2_metric_first_request")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "delete_metric_first")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 0, msg=json.dumps(v, indent=2))
        self.assertAlmostEqual(float(v["metrics"]["delete_confirm_max_ms"]), 66.0, places=3)

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

    def test_sol_r3_inconcluso_variants(self) -> None:
        # T2f-3: las variantes "buenas" de botín de la CE dan INCONCLUSO `posible_botin_ce`,
        # nunca FALLA.
        base = _load_fixture()
        for name, spec in f2p_mutants.SOL_INCONCLUSO_R3.items():
            with self.subTest(inconcluso=name):
                campaign = f2p_mutants.mutate(base, name)
                self.assertNotEqual(campaign, base, msg=(name, "no cambia la campaña"))
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], 2, msg=(name, json.dumps(v, indent=2)))
                c_map = _checks(v)
                self.assertFalse(any(c["status"] == "fail" for c in c_map.values()),
                                 msg=(name, json.dumps(v, indent=2)))
                for cid, reason in spec["must_missing"].items():
                    self.assertEqual(c_map[cid]["status"], "missing", msg=(name, cid, c_map[cid]))
                    self.assertIn(reason, c_map[cid]["detail"], msg=(name, cid, c_map[cid]))

    def test_v14_checkpoint_mutants_edit_read_obs(self) -> None:
        # V-14: los mutantes del checkpoint editan `read.obs`, no el alias `read.checkpoint`.
        def checkpoint_rows(campaign: dict[str, Any]) -> list[list[Any]]:
            rows: list[list[Any]] = []
            for ev in campaign["samples"]["bridge_tap.jsonl"]:
                if ev.get("dir") != "req" or ev.get("path") != "/result":
                    continue
                if abs(float(ev.get("t_ms") or 0.0) - 202000.0) > 0.5:
                    continue
                read = (ev.get("body") or {}).get("read") or {}
                obs = read.get("obs")
                if isinstance(obs, dict) and obs.get("at") == "checkpoint":
                    rows.extend(obs.get("rows") or [])
                self.assertNotIn("checkpoint", read,
                                 msg="el alias read.checkpoint no forma parte del cable v1.3")
            return rows

        base = _load_fixture()
        before = {str(r[0]): r for r in checkpoint_rows(base)}
        self.assertIn("zmb-01", before)
        x0 = float(before["zmb-01"][2])
        y0 = float(before["zmb-01"][3])

        jump = f2p_mutants.mutate(base, "creature_jump_before_checkpoint")
        after_jump = {str(r[0]): r for r in checkpoint_rows(jump)}
        self.assertAlmostEqual(float(after_jump["zmb-01"][2]), x0 + 400.0, places=6)

        born50 = f2p_mutants.mutate(base, "sol_creatures_born_50m")
        after50 = {str(r[0]): r for r in checkpoint_rows(born50)}
        self.assertAlmostEqual(float(after50["zmb-01"][3]), y0 + 50000.0, places=6)

    def test_v14_oracle_check_requires_oracle_unverified(self) -> None:
        base = _load_fixture()
        for name in ("r2_oracle_check_mismatch", "r2_oracle_check_missing"):
            with self.subTest(case=name):
                campaign = f2p_mutants.mutate(base, name)
                with tempfile.TemporaryDirectory() as tmp:
                    pdir = _build(campaign, Path(tmp) / name)
                    v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
                self.assertEqual(v["exit_code"], 2, msg=(name, json.dumps(v, indent=2)))
                self.assertIn("oracle_unverified", v["reasons"], msg=(name, v["reasons"]))

    def test_v14_real_validators_both_directions(self) -> None:
        # V-14: lo que el backend acepta no puede dar INCONCLUSO por la lectura; lo que rechaza no
        # puede pasar.
        repo = str(REPO_ROOT)
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from app.backend import scene_plan
        from app.backend.scene_live import _valid_read_compat
        base = _load_fixture()
        read = None
        for ev in base["samples"]["bridge_tap.jsonl"]:
            if ev.get("dir") == "req" and ev.get("path") == "/result":
                r = (ev.get("body") or {}).get("read")
                if isinstance(r, dict) and r.get("epoch") and isinstance(r.get("scene"), dict):
                    read = copy.deepcopy(r)
                    break
        self.assertIsNotNone(read)
        self.assertTrue(_valid_read_compat(read, require_obs=None, world_size=16384))
        bad = copy.deepcopy(read)
        bad["obs"] = {"at": "now", "rows": [["bogus"]]}
        self.assertFalse(_valid_read_compat(bad, require_obs=None, world_size=16384))
        self.assertFalse(scene_plan.valid_scene_read(bad, require_obs=None, world_size=16384))
        campaign = f2p_mutants.mutate(base, "r3_S08_bogus_obs")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "bogus_obs")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertNotEqual(v["exit_code"], 0, msg=json.dumps(v, indent=2))

    def test_s16_creature_231_isolated_reason(self) -> None:
        # S-16: el caso de R-06 aísla la criatura `1:231` y comprueba el motivo.
        base = _load_fixture()
        campaign = f2p_mutants.mutate(base, "r3_S16_creature_231_isolated")
        with tempfile.TemporaryDirectory() as tmp:
            pdir = _build(campaign, Path(tmp) / "creature_231")
            v = f2p_eval.evaluate(pdir, repo_root=REPO_ROOT)
        self.assertEqual(v["exit_code"], 2, msg=json.dumps(v, indent=2))
        detail = _checks(v)["F2P-10"]["detail"]
        self.assertEqual(_checks(v)["F2P-10"]["status"], "missing", msg=detail)
        self.assertIn("1:231", detail, msg=detail)
        self.assertIn("coverage_gap", detail, msg=detail)

    def test_s15_fixture_health_and_completeness(self) -> None:
        # S-15 (v1.3.10): salud por tipo, censos en serie, frames que crecen, `rows_captured_n`,
        # ticks por epoch, `spawn_tick_ms` a 0, P4c con dos epochs, P5 con dos testigos y 33
        # nacimientos, control en P4a, borrados de criaturas con sus discos y censos antes de P2n
        # y de P5.
        campaign = _load_fixture()
        manifest = campaign["manifest"]
        probe = f2p_eval._parse_probe(campaign["samples"]["bridge.jsonl"])
        tap = f2p_eval._parse_tap(campaign["samples"]["bridge_tap.jsonl"])
        backend = f2p_eval._parse_backend(campaign["samples"]["backend.jsonl"])
        doc1 = f2p_eval._load_doc1(REPO_ROOT)
        censuses = sorted([j for j in probe["jobs"].values() if j["kind"] == "census"],
                          key=lambda j: float(j["deliver_t"]))
        self.assertTrue(censuses)

        # Salud por tipo (§5.3 v1.3.10).
        building_classes = {c for c, *_ in f2p_eval.BUILDINGS}
        loot_classes = {c for c, *_ in f2p_eval.LOOT} if hasattr(f2p_eval, "LOOT") else set()
        # `LOOT` vive en el generador; se replica aquí con las clases del baseline.
        loot_classes = {"Barrel_Yellow", "AKS74U", "AmmoBox_357_20Rnd", "PartyTent_Lunapark",
                        "Lockpick"}
        for j in censuses:
            for r in j["rows"]:
                cls = str(r.get("class_name"))
                if cls in building_classes:
                    self.assertEqual(float(r["max_hp"]), -1.0, msg=(j["tag"], cls, r))
                    self.assertEqual(float(r["health_hp"]), -1.0, msg=(j["tag"], cls, r))
                if j["tag"] == "P1:base" and cls in loot_classes:
                    self.assertGreater(float(r["max_hp"]), 0.0, msg=(cls, r))
                    self.assertGreater(float(r["health_hp"]), 0.0, msg=(cls, r))
                    self.assertLess(float(r["health_hp"]), float(r["max_hp"]), msg=(cls, r))
                self.assertNotIn("health_mark_pending", r)
        self.assertNotIn("health_mark_pending", json.dumps(campaign))

        creation = f2p_eval._control_creation(probe, manifest)
        self.assertIsNotNone(creation, msg="el control persistente no está acreditado")
        self.assertEqual(creation["class_name"], "Barrel_Yellow")
        self.assertAlmostEqual(float(creation["max_hp"]), 1300.0, places=3)
        self.assertAlmostEqual(float(creation["health_hp"]), 1098.5, places=3)
        self.assertAlmostEqual(float(creation["pos_x_m"]), 4860.0, places=3)
        self.assertAlmostEqual(float(creation["pos_z_m"]), 10200.0, places=3)
        self.assertIsNotNone(f2p_eval._census(probe, "P4b:control"))
        self.assertIsNotNone(f2p_eval._census(probe, "P4c:control"))

        # Lo que crea el producto trae las dos formas de salud.
        gen2 = f2p_eval._generation_rebuild(probe, manifest, "P2", "apply", doc1)
        self.assertTrue(gen2["ok"])
        p2_rows = {str(r.get("net_id")): r for j in censuses if j["tag"] == "P2:post"
                   for r in j["rows"]}
        forms = set()
        for net in gen2["pairs"].values():
            r = p2_rows.get(net)
            if r is not None:
                forms.add((float(r["max_hp"]), float(r["health_hp"])))
        self.assertTrue(any(m == -1.0 and h == -1.0 for m, h in forms),
                        msg="falta la forma -1/-1 en lo que crea el producto")
        self.assertTrue(any(m > 0.0 and h > 0.0 for m, h in forms),
                        msg="falta la forma real en lo que crea el producto")

        # Censos en serie y `rows_captured_n`.
        for i, j in enumerate(censuses):
            self.assertEqual(int(j["rows_captured_n"]), len(j["rows"]), msg=j["tag"])
            if i + 1 < len(censuses):
                nxt = censuses[i + 1]
                self.assertIsNotNone(j.get("free_t"), msg=j["tag"])
                self.assertLess(float(j["free_t"]), float(nxt["deliver_t"]),
                                msg=(j["tag"], nxt["tag"]))
            # Frames que crecen y ticks por epoch.
            self.assertGreater(float(j["snap_frame"]), 0.0, msg=j["tag"])
            self.assertGreater(float(j["snap_tick_ms"]), 0.0, msg=j["tag"])
            if str(j["epoch"]) in ("e2" * 16, "e3" * 16):
                self.assertLess(float(j["snap_tick_ms"]), 100000.0, msg=j["tag"])
            for r in j["rows"]:
                self.assertEqual(float(r.get("spawn_tick_ms", -1.0)), 0.0, msg=(j["tag"], r))
        frames = [float(j["snap_frame"]) for j in censuses]
        self.assertEqual(frames, sorted(frames), msg="los frames del censo no crecen")
        for epoch in ("e1" * 16, "e2" * 16, "e3" * 16):
            ticks = [float(j["snap_tick_ms"]) for j in censuses if j["epoch"] == epoch]
            self.assertEqual(ticks, sorted(ticks), msg=("ticks no crecen", epoch))

        # P4c con dos epochs y su censo antes del reinicio.
        self.assertTrue(any(j["tag"] == "P4c:pre_reset" and j["epoch"] == "e2" * 16
                            for j in censuses))
        self.assertTrue(any(j["tag"] == "P4c:post_restart" and j["epoch"] == "e3" * 16
                            for j in censuses))
        self.assertTrue(any(r["data"].get("target") == "server" and
                            r["data"].get("epoch") == "e3" * 16
                            for r in backend["restarts"]))

        # P5 con dos testigos y los 33 nacimientos del apply nuevo.
        self.assertIsNotNone(f2p_eval._witness(probe, "P5:cut"))
        self.assertIsNotNone(f2p_eval._witness(probe, "P5:apply2"))
        windows = f2p_eval._witness_windows(probe, tap, backend, manifest)
        self.assertTrue(windows["ok"], msg=windows)
        gen5b = f2p_eval._generation_rebuild(probe, manifest, "P5", "apply2", doc1)
        self.assertTrue(gen5b["ok"])
        self.assertEqual(len(gen5b["pairs"]), 33)

        # Censos antes de P2n y de P5.
        self.assertIsNotNone(f2p_eval._census(probe, "P2n:pre_reset"))
        self.assertIsNotNone(f2p_eval._census(probe, "P5:pre"))

        # Borrados de criaturas con sus discos después del reset.
        creature_deletes = [ln for ln in campaign["samples"]["scene_del.jsonl"]
                            if str(ln.get("lid") or "").startswith(("zmb-", "ani-"))]
        self.assertTrue(creature_deletes)
        for tag in ("P2n:clean", "P3:post_reset1", "P4a:post_reset", "P4c:post_reset"):
            disks = [j["tag"] for j in probe["jobs"].values()
                     if j["kind"] == "census" and j["tag"].startswith(tag + ":disk:")]
            self.assertEqual(len(disks), 13, msg=(tag, disks))

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
