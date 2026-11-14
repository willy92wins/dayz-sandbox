# Assignment: S-track·2 evaluator, round 5b (Sol's v2 follow-up)

Same workspace (`C:\tmp\dsbx-strack2\eval5`), same rules as `C:\tmp\dsbx-strack2\briefs\brief_eval_r5.md` (re-read it: write-set, constant format, gate, Spanish). Sol reviewed your round 5: `C:\tmp\dsbx-strack2\lanes\sol_checkruns\LAST_v2.md` (read all of it, it has exact inputs). Closed: H2, H3, H4. Add a section «Vuelta 5b» to `REPORT_eval_r5.md` with what you changed per item (`path:line`) and the literal gate output.

## Orchestrator's arbitration (applies to this round)
- **B1 is out of scope by contract.** CONTRACT §16: the filter of frame n uses the `dt` of frame n, and the mod logs exactly the `dt` its filter integrates (`STRACK_Session.c:318`, `:1347`, `:1577`). The evaluator judges the filter against the clock the filter used. A logged `dt` that differs from what the filter integrated cannot come out of the real bench; a mismatch between engine `dt` and wall time is engine behaviour, not a camera defect. Do not add protection for adulterated `dt`.
- Consequence: **remove the jump-boundary guard** (`SUAVE_DT_TMS_TOL_MS` and the `intervalo_salto_incoherente` INCONCLUSO, `s_track_eval.py:~2410-2433`). It existed only to defend against B1, and it causes B2 and M1. Keep everything of round 5 that puts filter-time measures on the `Σdt` axis (that part Sol accepted: `:2304`).

## What to fix (each with a test that fails before and passes after)
1. **B2 (BLOQ), even after removing the guard:** the FPS-agreement criterion (`:2789`, `:2809`) must never become satisfied because a comparison is missing. If any regime that the agreement needs is INCONCLUSO or absent, the agreement is INCONCLUSO, and no regime that depends on it may be certified PASS. Test: Sol's B2 scenario (30 fps biased 1° → 73.4619° vs 72.4619°) with the 60 fps reference made INCONCLUSO by any other cause must NOT yield PASS for 30.
2. **M2:** remove `INTERVALO_MAX_MS` from `check_runs.py` (no contractual basis). Keep: finite values, `dt > 0`, strictly increasing `t_ms`, duplicate policy, load-pair handling, and the accumulated-drift limit. Test: Sol's M2 run (a coherent 101 ms frame) is VALID.
3. **Drift threshold, Sol «A MEDIAS»:** with the guard gone and filter measures on `Σdt`, `t_ms` only feeds wall-clock measures. Update the comment next to `DERIVA_MAX_MS` so it no longer refers to the guard, and state explicitly that filter correctness does not depend on `t_ms`.
4. Update/remove the round-5 tests that asserted the guard's INCONCLUSO; keep the two real calibrations VALID.

## Gate (literal in the report)
From `DayZSandbox_dev`: the full suite (`C:\Python314\python.exe -m unittest discover -s qa/strack/tests -t .`), `qa.tests.test_stdlib_only`, and `check_runs.py` on the reconstructed calibrations. Note: `C:\Python314` has numpy 2.4.4 and Pillow 12.2.0 on this host; if your sandbox can't see them, say so and use what you used before. No git, no push, no files outside the write-set.
