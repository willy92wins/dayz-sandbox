# Assignment: S-track·2 evaluator, round 5 (timeline coherence) + `check_runs.py` hardening

You are working in `C:\tmp\dsbx-strack2\eval5`, a copy of the evaluator integrated at `4ae0727` plus the orchestrator's uncommitted changes to `check_runs.py`. **Read first:** `DayZSandbox_dev/qa/strack/CONTRACT.md` (especially §4, §13 and §16) and `SOL_checkruns_v1.md`, at the workspace root. That is Sol's verdict, with the exact input for each case. Write `REPORT_eval_r5.md` at the root: what you changed for each finding, with `path:line`, and the literal output of the gate.

## Why this round exists (facts)
- The first real bench runs (`calib_Ha` and `calib_Hb`, 13 Nov) show that per frame `dt` and `t_ms` **do not agree**:
  - `dt` comes rounded to 1 ms;
  - on a hitch they split the time differently between frames: `Δt_ms` 36+5 against `1000·dt` 8+32;
  - over 17 s they only drift apart by 1 ms.
  
  Ha has 38 pairs with a mismatch above 1 ms; Hb has 224. The clock columns of both runs are in `DayZSandbox_dev/qa/strack/fixtures/real_clock_calib.json`, as `[frame, t_ms, dt]` with the sha of the original `samples.jsonl`.
- The mod's filter integrates **`dt`**, the same value it logs: `alpha = 1 − exp(−m_Dt / smooth)`, in `qa/strack/DZS_STrack/scripts/4_World/STRACK_Session.c:1347` and `:1577`. `t_ms` is `GetTickTime`, another clock. See CONTRACT §16.
- The evaluator mixes the two clocks:
  - It simulates T-suave with `dt` (`s_track_eval.py:2130`).
  - It measures the orientation at 1/6 s and the jump's origin with `t_ms` (`:2213`, `:2231`, `:2334`).
  - With the real hitch, two correct cameras disagree by 1.7°, and that gives a false `suave_fps_agree_exceeded` (Sol, H1).
- `check_runs.py` is the check that real runs must pass before their verdict counts. Sol found 4 BLOQ in it: H1-H4 in `SOL_checkruns_v1.md`.

## What to fix (for each one, a test that fails before and passes after)
1. **H1, single timeline per consumer.**
   - Every measure of what the filter does (orientation at 1/6 s, the jump's origin, T-suave's reference, `mount03`'s filter, and any other measure you find that depends on the filter's time) goes on the **accumulated `Σdt`** axis of the frames that make it up, not on `t_ms`.
   - `t_ms` stays only for wall-clock measures: giro duration (4.0 ± 0.3 s) and windows without a `giro` label.
   - Mandatory tests:
     - the real hitch pattern placed inside a correct giro must not produce `suave_fps_agree_exceeded`;
     - Sol's case of compensated `dt` (30.6667 and 2.6667 ms around a jump) with a lagging camera must not give PASS.
   
   If you conclude that some consumer cannot use `Σdt`, say why and declare INCONCLUSO for it.
2. **H2, load frame.**
   - The same interval has to be treated the same way in `check_runs` and in the evaluator: either both exclude it (also from `N/Σdt` in the FPS calculation, `:2041` and `:2068`) or both validate it.
   - The first pair seen does not on its own prove that it is the load pair: define which one is and justify it.
   - Bound `dt` and `Δt_ms` per frame, with a limit justified in the code. Real values: load 39 ms; maximum after load, see the fixture.
3. **H3, duplicates.** `check_runs` validates exactly the canonical rows the evaluator consumes, with the same duplicate policy (`s_track_eval.py:470` and below). Two rows for the same frame that differ in `t_ms` or `dt` make the run INVALID.
4. **H4, non-finite values.** Every row needs finite `t_ms` and `dt`, and `dt > 0`, before accumulating or excluding anything. Also reject `NaN` and `Infinity` in the JSON.
5. **Drift threshold (Sol, answer 5).** The 50 ms was set after looking at the data. Once 1 is done, `t_ms` only feeds wall-clock measures: set the accumulated-drift limit from those consumers (the giro's ± 0.3 s, and windows without a label) and write the reasoning next to the constant.
6. **Tests that are missing (Sol, answer 6):**
   - the edges of the drift limit (exactly at the limit, and just above);
   - Hc with `calib_Ha` **invalid**;
   - extreme load;
   - duplicates;
   - non-finite values.
   
   Both real calibrations (the fixture) must stay VALID in `check_runs`.

## Boundaries
- Write-set: `DayZSandbox_dev/qa/strack/s_track_eval.py`, `check_runs.py`, `tests/` and `fixtures/`, and `REPORT_eval_r5.md`. Do not touch the mod (`DZS_STrack/`), the mutants (`mutants/`) or `CONTRACT.md`. If the contract needs to change, propose it in the report.
- The constants in CONTRACT §4 and §13 keep their exact format: one per line, at module level, because the mutants change them as text. If you add new constants, use the same format and list them in the report.
- Do not reopen anything from rounds 1-4 that Sol has already closed. No `git commit`, no push.
- Python stdlib, plus numpy and Pillow in the evaluator, as it already is. `check_runs.py` stays stdlib only.

## Gate (paste the literal output in the report)
From `DayZSandbox_dev`:
- `C:\Python314\python.exe -m unittest discover -s qa/strack/tests -t .` (the full suite; it takes about 22 min);
- `C:\Python314\python.exe -m unittest qa.tests.test_stdlib_only`;
- `C:\Python314\python.exe qa/strack/check_runs.py <dir>` against a temporary folder where you rebuild `calib_Ha` and `calib_Hb` from the fixture: both VALID.

If something cannot be run: `GATE NOT RUN: <reason>`. Do not finish without the gate in the report.

## Closing
Write the report, code comments and test names in Spanish, like the rest of the repo. The report ends with `WHAT I COULD NOT VERIFY`. The mod's behaviour with hitches in `suave*` cases has not been observed yet (the bench is still running); say so if your fix depends on it.
