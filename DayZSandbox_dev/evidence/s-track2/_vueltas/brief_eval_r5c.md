# Assignment: S-track·2 evaluator, round 5c (one MAY from Sol v3)

Same workspace (`C:\tmp\dsbx-strack2\eval5`), same rules as `brief_eval_r5.md` (write-set, constant format, Spanish, gate). Sol v3 (`C:\tmp\dsbx-strack2\lanes\sol_checkruns\LAST_v3.md`, read N1 entirely): 0 BLOQ; B2, M1, M2, H1 and the threshold CLOSED; B1 arbitration accepted. Add a section «Vuelta 5c» to `REPORT_eval_r5.md`.

## Fix (with a test that fails before and passes after)
**N1 (MAY)** `s_track_eval.py:2795` turns PASS giros into INCONCLUSO when a comparison is missing; then `:2806` only turns into FALLA those still PASS. Result: a disagreement already demonstrated between two regimes (30 vs 60: 73.4619° vs 72.4619°, > 0.5°) is erased to INCONCLUSO when a third regime (144) is incomplete. Required: a demonstrated pairwise disagreement keeps FALLA for the regimes involved (30 and 60), and only the incomplete regime (144) stays INCONCLUSO; the pending state from round 5b (B2) still applies when no disagreement is demonstrated. Use Sol's exact scenario for the test (frames 915–929 of `suave30_Hb` biased +1°, `cam.pos=null` only at frame 4392 of `suave144_Hb`): expected FALLA / FALLA / INCONCLUSO, exit code 1. Keep the B2 test passing.

Touch nothing else. Gate: the full suite and `qa.tests.test_stdlib_only` from `DayZSandbox_dev` if your sandbox can import numpy; if not, run what you can and write `GATE NOT RUN` for the rest — the orchestrator runs the full suite.
