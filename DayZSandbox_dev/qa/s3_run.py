"""Runner de S3 (brief 2026-11-14-m1-f0.3-s3-brief.md §4, E1-E9).

Las ordenes van por el nucleo (``PartContext`` / ``issue_one``) y el ``bridge.jsonl`` lo escribe el nucleo. Este
runner solo decide el guion, registra en ``scenario.jsonl`` QUE op_ids son cada paso y escribe ``injection.json`` con
efectos tomados de lecturas reales. El evaluador (``s3_eval.py``) decide con las lecturas crudas, no con este fichero.
"""

import json
import os
import subprocess
import time
from pathlib import Path

import f03_common
import gate_core
import s3_eval
import s3_mutants
import wire

SPIKE_ID = "S3"
PEER = "server"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
EMOTE_KEYS = ("nod", "shake", "shrug", "clap", "move", "down", "come", "tauntthink")
ENV_BASE = {"hour_n": 10.0, "minute_n": 0.0, "fog": 0.1, "overcast": 0.2, "rain": 0.0}
ENV_MIXED = {"hour_n": 18.0, "minute_n": 45.0, "fog": 0.85, "overcast": 0.9, "rain": 0.5}
ALL_CHECK_TAGS = ("S3-08", "S3-09")


# ------------------------------------------------------------------ contexto de parte
def _resolve_exp_pbo(args):
    pbo = Path(args.pbo).resolve() if getattr(args, "pbo", None) else None
    env = os.environ.get("DSBX_QA_EXP_PBO", "").strip()
    if env:
        cand = Path(env)
    elif pbo is not None:
        if pbo.parent.name.lower() == "addons":
            cand = pbo.parent.parent.parent / "@DayZSandbox_QA_Expansion" / "Addons" / "DayZSandbox_QA_Expansion.pbo"
        else:
            cand = pbo.parent / "DayZSandbox_QA_Expansion.pbo"
    else:
        return None
    if not cand.is_file() or cand.suffix.lower() != ".pbo":
        return None
    if pbo is not None and cand.resolve() == pbo:
        return None
    return cand


class S3PartContext(f03_common.PartContext):
    """PartContext que ademas identifica el segundo PBO (adaptador de Expansion)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.exp_stamp = None
        self.exp_pbo_sha256 = None
        self.exp_detail = ""
        try:
            self.exp_stamp = s3_eval.compute_exp_stamp_at_commit(self.git_head or "", repo_root=self.repo_root)
        except f03_common.StampSourceUnavailableError:
            self.exp_stamp = None
        if self.build in ("diag", "retail"):
            pbo = _resolve_exp_pbo(self.args)
            if pbo is not None:
                self.exp_pbo_sha256 = f03_common.sha256_file_hex(pbo)

    def open(self):
        super().open()
        if self.startup_reason is None:
            if self.exp_stamp is None:
                self.startup_reason = "stamp_source_unavailable"
            elif self.build in ("diag", "retail") and self.exp_pbo_sha256 is None:
                self.startup_reason = "artifact_unverified"
                self.exp_detail = "missing_exp_pbo"
        self.finalize_manifest()

    def finalize_manifest(self):
        manifest = super().finalize_manifest()
        extra = {"exp_pbo_sha256": self.exp_pbo_sha256, "exp_probe_stamp": self.exp_stamp}
        manifest["identity"]["params"].update(extra)
        manifest.setdefault("params", {}).update(extra)
        gate_core.write_json(self.part_dir / "manifest.json", manifest)
        return manifest


# ------------------------------------------------------------------ ayudas de orden
def _fixtures():
    return {
        "actors": gate_core.read_json(FIXTURES_DIR / "s3_actors_preset.json"),
        "marks": gate_core.read_json(FIXTURES_DIR / "s3_marks.json"),
        "emotes": gate_core.read_json(FIXTURES_DIR / "s3_emotes.json"),
        "combat": gate_core.read_json(FIXTURES_DIR / "s3_combat_qa.json"),
    }


def _call(ctx, verb, strs=None, nums=None, ncols=None, scols=None, rows=None, fault=None):
    payload = wire.pack_payload(strs, nums, ncols, scols, rows)
    return f03_common.issue_one(ctx, PEER, verb, payload, qa_fault=fault)


def _observe(ctx):
    return _call(ctx, "act_observe")


def _reset(ctx):
    return _call(ctx, "act_reset")


def _freeze(ctx, on, env=None):
    nums = {"freeze_b": 1.0 if on else 0.0}
    nums.update(env or {})
    return _call(ctx, "act_env_freeze", nums=nums)


def _spec(actor):
    return ";".join(f"{w['slot']}:{w['item']}" for w in actor["wardrobe"])


def _scene(ctx, fx, *, props=2, actors=2, seed=None, cap_mode="normal", fail_slot=None, env=None,
           bad_char=None, bad_spec=None, positions=None, fault=None):
    strs = {"cap_mode": cap_mode}
    nums = {"props_n": float(props)}
    if seed is not None:
        nums["seed_pre_gear_b"] = float(seed)
    if fail_slot:
        strs["fail_slot"] = fail_slot
    nums.update(env or {})
    rows = []
    for pos, actor in enumerate(fx["actors"]["actors"][:actors]):
        x, z = (positions or {}).get(actor["actor_id"], (actor["x_m"], actor["z_m"]))
        rows.append(
            {
                "actor_id": actor["actor_id"],
                "character": bad_char if (pos == 0 and bad_char) else actor["character"],
                "wardrobe_spec": bad_spec if (pos == 0 and bad_spec) else _spec(actor),
                "x_m": float(x),
                "z_m": float(z),
            }
        )
    if rows:
        return _call(ctx, "act_scene_apply", strs, nums, ["x_m", "z_m"],
                     ["actor_id", "character", "wardrobe_spec"], rows, fault=fault)
    return _call(ctx, "act_scene_apply", strs, nums, fault=fault)


def _job_read(ctx, jid, page):
    return f03_common.issue_one(ctx, PEER, "job_read", wire.pack_payload({"job": jid}, {"page_n": page}))


def _wait_terminal(ctx, jid, timeout_s=90.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        out = _job_read(ctx, jid, 0)
        if out.status == "done" and out.payload["str"].get("state") in f03_common.TERMINAL_JOB_STATES:
            return out.payload["str"].get("state")
        time.sleep(0.05)
    raise RuntimeError(f"job {jid} did not finish in {timeout_s}s")


def _poll_rows(ctx, jid, pred, timeout_s):
    """Observa el trabajo en vivo con cursor de pagina (N16): avanza ``cursor_page_n`` hasta la ultima pagina."""
    deadline = time.monotonic() + timeout_s
    cursor = 0
    seen = {}
    while time.monotonic() < deadline:
        out = _job_read(ctx, jid, cursor)
        if out.status == "done":
            for row in out.payload["rows"]:
                seen[row["seq_n"]] = row
                if pred(row):
                    return row
            pages_n = int(out.payload["num"].get("pages_n", 0))
            if pages_n > cursor + 1:
                for page in range(cursor + 1, pages_n):
                    nxt = _job_read(ctx, jid, page)
                    if nxt.status == "done":
                        for row in nxt.payload["rows"]:
                            seen[row["seq_n"]] = row
                            if pred(row):
                                return row
                cursor = pages_n - 1
            if out.payload["str"].get("state") in f03_common.TERMINAL_JOB_STATES:
                return None
        time.sleep(0.03)
    return None


def _finish_job(ctx, out):
    """Lee todas las paginas de un trabajo terminal y lo libera. Devuelve (ids de pagina, filas)."""
    paged = f03_common.read_job_pages(ctx, PEER, out.op_id)
    page_ids = [o.op_id for o in paged["outcomes"]]
    _call_free = f03_common.issue_one(ctx, PEER, "job_free", wire.pack_payload({"job": out.op_id}))
    return page_ids, paged["rows"], _call_free


def _started(row):
    return (row["cb_inst_id"] > row["max_cb_inst_at_req_n"] and row["observed_emote_id"] == row["expected_emote_id"]
            and row["anim_cmd_id"] == row["expected_cmd_id"] != 0 and row["start_tick_ms"] >= row["req_tick_ms"] > 0
            and (row["anim_state_n"] != 0 or row["emote_state"] == "en_curso" or row["on_finish_called_b"] == 1))


def _rec(ctx, tags, row):
    for tag in tags:
        payload = dict(row)
        payload["check"] = tag
        ctx.record_scenario(payload)


def _need(out, what):
    if out.status != "done":
        raise RuntimeError(f"{what}: {out.status}/{out.reason}")
    return out


# ------------------------------------------------------------------ reinicios del servidor (S0, S8, S9)
def _restart_server(ctx, expansion):
    old = ctx.procs.get(PEER)
    if old is None:
        return None
    cmd = list(old.args)
    prof = ctx.profiles[PEER]
    flag = prof / "s3_restart.flag"
    flag.write_text("1", encoding="utf-8")
    try:
        old.wait(timeout=20)  # la extension cierra el peer sin dejar una peticion HTTP a medias
    except subprocess.TimeoutExpired:
        old.terminate()
        old.wait(timeout=5)
    flag.unlink(missing_ok=True)
    (prof / "s3_modset.json").write_text(json.dumps({"expansion": bool(expansion)}), encoding="utf-8")
    fh = ctx.peer_logs[PEER].open("a", encoding="utf-8", newline="\n")
    ctx._log_handles.append(fh)
    proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
    ctx.procs[PEER] = proc
    ctx.fake_peer_pids[PEER] = proc.pid
    return proc.pid


def _server_insts(ctx):
    with ctx.bridge.cv:
        return {ev.get("inst") for ev in ctx.bridge.events
                if ev.get("ev") == "hello" and ev.get("http") == 200 and ev.get("peer") == PEER}


def _restart_step(ctx, step, expansion, instructions):
    known = _server_insts(ctx)

    def pred(ev):
        return (ev.get("ev") == "hello" and ev.get("http") == 200 and ev.get("peer") == PEER
                and ev.get("inst") not in known)

    action = "restart_server_with_expansion" if expansion else "restart_server_without_expansion"
    res = f03_common.await_operator(ctx, step=step, action=action, instructions=instructions, predicate=pred,
                                    timeout_s=300, offline_sim=lambda c: _restart_server(c, expansion))
    if not res.get("ok"):
        raise RuntimeError("operator_timeout")
    # el nuevo inst ya esta registrado: espera a que el puente lo tome como inst vigente del servidor
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if ctx.bridge.registered(PEER) not in known and ctx.bridge.registered(PEER) is not None:
            return
        time.sleep(0.05)
    raise RuntimeError("restart_not_registered")


# ------------------------------------------------------------------ pasos
def step_s0(ctx):
    obs = _need(_observe(ctx), "S0 observe")
    if obs.payload["num"].get("backend_available_b") != 1.0:
        _restart_step(ctx, "S0_ensure_expansion", True,
                      "Reinicia DayZServer cargando Expansion + @DayZSandbox_QA + @DayZSandbox_QA_Expansion")
        obs = _need(_observe(ctx), "S0 observe tras reinicio")
    _need(_reset(ctx), "S0 reset")
    obs = _need(_observe(ctx), "S0 observe inicial")
    _rec(ctx, ("S3-00",), {"kind": "handshake", "phase": "S0_handshake", "observe_op_id": obs.op_id})


def step_s9(ctx):
    _restart_step(ctx, "S9_restore_expansion", True,
                  "Reinicia DayZServer cargando de nuevo Expansion + @DayZSandbox_QA + @DayZSandbox_QA_Expansion")
    _need(_reset(ctx), "S9 reset")
    obs = _need(_observe(ctx), "S9 observe")
    _rec(ctx, ("S3-00",), {"kind": "handshake", "phase": "S9_restore", "observe_op_id": obs.op_id})


def step_s1(ctx, fx, fault=None):
    _need(_freeze(ctx, True, ENV_BASE), "S1 freeze")
    base = _need(_observe(ctx), "S1 baseline")
    rejects = []
    for case, kw, reason in (
        ("unknown_class", {"bad_char": "SurvivorM_NoExiste"}, "unknown_class"),
        ("incompatible_slot", {"bad_spec": "Headgear:HunterPants_Autumn"}, "incompatible_slot"),
    ):
        app = _scene(ctx, fx, props=2, actors=2, env=ENV_MIXED, **kw)
        if app.status != "rejected" or app.reason != reason:
            raise RuntimeError(f"S1 {case}: {app.status}/{app.reason}")
        post = _need(_observe(ctx), "S1 post reject")
        rejects.append((case, app, post))
    partial = _scene(ctx, fx, props=2, actors=2, fail_slot="Feet")
    _need(partial, "S1 partial")
    _need(_reset(ctx), "S1 reset parcial")
    apply1 = _need(_scene(ctx, fx, props=2, actors=2, seed=1, fault=fault), "S1 apply1")
    obs1 = _need(_observe(ctx), "S1 obs1")
    reset = _need(_reset(ctx), "S1 reset")
    apply2 = _need(_scene(ctx, fx, props=2, actors=2, seed=1), "S1 apply2")
    obs2 = _need(_observe(ctx), "S1 obs2")
    _need(_freeze(ctx, False), "S1 unfreeze")
    for case, app, post in rejects:
        _rec(ctx, ("S3-01",), {"kind": "reject", "case": case, "baseline_observe_op_id": base.op_id,
                               "apply_op_id": app.op_id, "observe_op_id": post.op_id})
    _rec(ctx, ("S3-01",), {"kind": "partial", "apply_op_id": partial.op_id})
    _rec(ctx, ("S3-01",), {"kind": "positive", "apply1_op_id": apply1.op_id, "observe1_op_id": obs1.op_id,
                           "reset_op_id": reset.op_id, "apply2_op_id": apply2.op_id,
                           "observe2_op_id": obs2.op_id})
    return {"apply1": apply1.payload["num"], "obs1_rows": obs1.payload["rows"]}


def _behaviour(ctx, actor, mode, *, strs=None, nums=None, wps=None, fault=None, timeout_s=90.0, wait=True):
    s = {"actor_id": actor, "mode": mode}
    s.update(strs or {})
    n = dict(nums or {})
    rows = [{"wp_x_m": float(x), "wp_y_m": 0.0, "wp_z_m": float(z)} for x, z in (wps or [])]
    if rows:
        out = _call(ctx, "act_behaviour_run", s, n, ["wp_x_m", "wp_y_m", "wp_z_m"], [], rows, fault=fault)
    else:
        out = _call(ctx, "act_behaviour_run", s, n, fault=fault)
    _need(out, f"behaviour {mode}")
    if wait:
        _wait_terminal(ctx, out.op_id, timeout_s)
    return out


def _pt(fx, name):
    p = fx["marks"]["points"][name]
    return float(p["x_m"]), float(p["z_m"])


def step_s2_positive(ctx, fx):
    out = _behaviour(ctx, "actor_1", "ONCE", strs={"threat_case": "none"}, wps=[_pt(fx, "once_reachable")],
                     nums={"reach_timeout_ms": 30000.0, "settle_window_ms": 10000.0, "sample_step_ms": 500.0})
    page_ids, _rows, _ = _finish_job(ctx, out)
    _rec(ctx, ("S3-02",), {"kind": "once_reachable", "actor_id": "actor_1", "start_op_id": out.op_id,
                           "page_op_ids": page_ids})


def step_s2_negatives(ctx, fx, fault=None):
    un = _behaviour(ctx, "actor_2", "ONCE", strs={"threat_case": "none"}, wps=[_pt(fx, "once_unreachable")],
                    nums={"reach_timeout_ms": 15000.0, "sample_step_ms": 500.0}, fault=fault)
    un_pages, un_rows, _ = _finish_job(ctx, un)
    cb = fx["combat"]
    stage = _need(_call(ctx, "act_combat_stage",
                        {"actor_id": "actor_2", "faction_key": cb["faction_key"],
                         "infected_class": cb["infected_class"]},
                        {"dist_m": float(cb["dist_s2_m"])}), "S2 combat_stage")
    th = _behaviour(ctx, "actor_2", "ONCE", strs={"threat_case": "require_threat"}, wps=[_pt(fx, "threat_mark")],
                    nums={"reach_timeout_ms": 15000.0, "sample_step_ms": 500.0})
    th_pages, _th_rows, _ = _finish_job(ctx, th)
    _need(_reset(ctx), "S2 reset")
    _need(_scene(ctx, fx, props=2, actors=2), "S2 re-apply")
    _rec(ctx, ("S3-06",), {"kind": "unreachable", "actor_id": "actor_2", "start_op_id": un.op_id,
                           "page_op_ids": un_pages})
    _rec(ctx, ("S3-06",), {"kind": "require_threat", "actor_id": "actor_2", "start_op_id": th.op_id,
                           "page_op_ids": th_pages, "stage_op_id": stage.op_id})
    last = un_rows[-1]
    return {"mark_state": last["mark_state"], "dist_mark_m": last["dist_mark_m"]}


def step_s3(ctx, fx):
    hold = _behaviour(ctx, "actor_1", "HOLD", nums={"duration_ms": 10000.0, "sample_step_ms": 500.0})
    hold_pages, _r, _ = _finish_job(ctx, hold)
    loop = _behaviour(ctx, "actor_1", "LOOP", nums={"duration_ms": 60000.0, "sample_step_ms": 500.0},
                      wps=[_pt(fx, "loop_m0"), _pt(fx, "loop_m1")])
    loop_pages, _r, _ = _finish_job(ctx, loop)
    _rec(ctx, ("S3-03",), {"kind": "hold", "actor_id": "actor_1", "start_op_id": hold.op_id,
                           "page_op_ids": hold_pages})
    _rec(ctx, ("S3-03",), {"kind": "loop", "actor_id": "actor_1", "start_op_id": loop.op_id,
                           "page_op_ids": loop_pages})


_EMOTE_NUMS = {"start_timeout_ms": 5000.0, "finish_timeout_ms": 15000.0, "sample_step_ms": 250.0}


def _emote(ctx, key, case, nums=None, fault=None, actor="actor_1"):
    out = _call(ctx, "act_emote_run", {"actor_id": actor, "emote_key": key, "test_case": case},
                dict(nums if nums is not None else _EMOTE_NUMS), fault=fault)
    return out


def step_s4_positive(ctx, fx, fault=None):
    unknown = _emote(ctx, "unknown_test_emote", "normal")
    if unknown.status != "rejected" or unknown.reason != "unknown_emote":
        raise RuntimeError(f"unknown emote: {unknown.status}/{unknown.reason}")
    info = {}
    for key in EMOTE_KEYS:
        out = _need(_emote(ctx, key, "normal", fault=(fault if key == "nod" else None)), f"emote {key}")
        _wait_terminal(ctx, out.op_id, 60.0)
        pages, rows, _ = _finish_job(ctx, out)
        _rec(ctx, ("S3-04",), {"kind": "emote", "emote_key": key, "actor_id": "actor_1",
                               "start_op_id": out.op_id, "page_op_ids": pages})
        if key == "nod":
            info = {"expected_emote_id": rows[-1]["expected_emote_id"],
                    "observed_emote_id": rows[-1]["observed_emote_id"]}
    return unknown, info


def _stop_and_read(ctx, out):
    stop = _need(f03_common.issue_one(ctx, PEER, "job_stop", wire.pack_payload({"job": out.op_id})), "job_stop")
    pages, rows, _ = _finish_job(ctx, out)
    return stop, pages, rows


def _post_watch(ctx, key, actor="actor_1"):
    out = _need(_emote(ctx, key, "post_stop_watch",
                       {"post_watch_ms": 3000.0, "sample_step_ms": 250.0}, actor=actor), "post_stop_watch")
    _wait_terminal(ctx, out.op_id, 30.0)
    pages, rows, _ = _finish_job(ctx, out)
    return out, pages, rows


def _case_row(kind, actor, out, pages, stop, post=None):
    row = {"kind": kind, "actor_id": actor, "start_op_id": out.op_id, "page_op_ids": pages,
           "stop_op_id": stop.op_id}
    if post is not None:
        row["post_watch_start_op_id"] = post[0].op_id
        row["post_watch_page_op_ids"] = post[1]
    return row


def step_s4_negatives(ctx, fx, tags, faults, full=True):
    """Gestos negativos de ciclo de vida. ``tags``: checks que reciben las filas (S3-08, S3-09 o ambos)."""
    unknown = None
    if "S3-08" in tags:
        unknown = _emote(ctx, "unknown_test_emote", "normal")
        if unknown.status != "rejected" or unknown.reason != "unknown_emote":
            raise RuntimeError(f"unknown emote: {unknown.status}/{unknown.reason}")
    key = "nod"
    obs = {}

    # never_starts: el objeto pesado bloquea las manos; vence start_timeout_ms y la sonda retira la peticion
    out = _need(_emote(ctx, key, "never_starts", fault=faults.get("never_starts")), "never_starts")
    _poll_rows(ctx, out.op_id, lambda r: r["cancel_req_tick_ms"] > 0, 30.0)
    stop, pages, rows = _stop_and_read(ctx, out)
    post = _post_watch(ctx, key)
    _rec(ctx, tags, _case_row("never_starts", "actor_1", out, pages, stop, post))
    obs["never_starts"] = post[2][-1]

    # cancel_before_start: manos bloqueadas, el stop llega antes del inicio
    out = _need(_emote(ctx, key, "cancel_before_start", fault=faults.get("cancel_before_start")),
                "cancel_before_start")
    _poll_rows(ctx, out.op_id, lambda r: r["can_play_emote_b"] == 0 and not _started(r) and r["req_tick_ms"] > 0, 10.0)
    stop, pages, rows = _stop_and_read(ctx, out)
    post = _post_watch(ctx, key)
    _rec(ctx, tags, _case_row("cancel_before_start", "actor_1", out, pages, stop, post))

    # cancel_after_start: el gesto empieza (callback ligado) y el stop llega despues
    out = _need(_emote(ctx, key, "cancel_after_start", fault=faults.get("cancel_after_start")),
                "cancel_after_start")
    _poll_rows(ctx, out.op_id, _started, 10.0)
    stop, pages, rows = _stop_and_read(ctx, out)
    post = _post_watch(ctx, key)
    _rec(ctx, tags, _case_row("cancel_after_start", "actor_1", out, pages, stop, post))
    obs["cancel_after_start"] = post[2][-1]

    if full and "S3-08" in tags:
        # interrupt_between_samples: la sonda arranca y cancela entre dos muestras periodicas
        out = _need(_emote(ctx, key, "interrupt_between_samples",
                           {"start_timeout_ms": 5000.0, "finish_timeout_ms": 15000.0, "sample_step_ms": 500.0},
                           fault=faults.get("interrupt_between_samples")), "interrupt_between_samples")
        _poll_rows(ctx, out.op_id, lambda r: r["cleanup_tick_ms"] > 0, 15.0)
        time.sleep(0.6)  # deja que la sonda emita al menos la muestra P_2 despues de la limpieza
        stop, pages, rows = _stop_and_read(ctx, out)
        _rec(ctx, ("S3-08",), _case_row("interrupt_between_samples", "actor_1", out, pages, stop))

        # stale_callback_isolation: un callback previo termina durante la peticion y no se liga a ella
        out = _need(_emote(ctx, key, "stale_callback_isolation", fault=faults.get("stale_callback_isolation")),
                    "stale_callback_isolation")
        _poll_rows(ctx, out.op_id, lambda r: r["foreign_cb_events_n"] >= 1, 15.0)
        stop, pages, rows = _stop_and_read(ctx, out)
        post = _post_watch(ctx, key)
        _rec(ctx, ("S3-08",), _case_row("stale_callback_isolation", "actor_1", out, pages, stop, post))
        obs["stale"] = post[2][-1]
    if unknown is not None:
        ctx.record_scenario({"check": "S3-08", "kind": "unknown_emote", "op_id": unknown.op_id})
    return obs


def step_s5(ctx, fx, fault=None):
    cb = fx["combat"]
    stage = _need(_call(ctx, "act_combat_stage",
                        {"actor_id": "actor_2", "faction_key": cb["faction_key"],
                         "infected_class": cb["infected_class"]},
                        {"dist_m": float(cb["dist_s5_m"])}), "S5 combat_stage")
    out = _need(_emote(ctx, "nod", "require_combat",
                       {"combat_wait_ms": 5000.0, "start_timeout_ms": 5000.0, "sample_step_ms": 250.0},
                       fault=fault, actor="actor_2"), "require_combat")
    _wait_terminal(ctx, out.op_id, 30.0)
    pages, rows, _ = _finish_job(ctx, out)
    _rec(ctx, ("S3-07",), {"kind": "require_combat", "actor_id": "actor_2", "start_op_id": out.op_id,
                           "page_op_ids": pages, "stage_op_id": stage.op_id})
    last = [r for r in rows if r["emote_state"] in ("terminado", "rechazado")][-1]
    return {"emote_state": last["emote_state"], "raw_p_canceled_b": last["raw_p_canceled_b"]}


def step_s6(ctx, fx, fault=None):
    urban, open_c = _pt(fx, "roam_urban_center"), _pt(fx, "roam_open_center")
    _need(_reset(ctx), "S6 reset")
    _need(_scene(ctx, fx, props=2, actors=2, positions={"actor_1": urban, "actor_2": open_c}), "S6 scene")
    nums = {"radius_m": 15.0, "duration_ms": 600000.0, "sample_step_ms": 5000.0}
    a = _behaviour(ctx, "actor_1", "ROAM", nums=nums, fault=fault, wait=False)
    b = _behaviour(ctx, "actor_2", "ROAM", nums=nums, wait=False)
    _wait_terminal(ctx, a.op_id, 120.0)
    _wait_terminal(ctx, b.op_id, 120.0)
    a_pages, a_rows, _ = _finish_job(ctx, a)
    b_pages, _b_rows, _ = _finish_job(ctx, b)
    _rec(ctx, ("S3-05",), {"kind": "roam_urban", "actor_id": "actor_1", "start_op_id": a.op_id,
                           "page_op_ids": a_pages})
    _rec(ctx, ("S3-05",), {"kind": "roam_open", "actor_id": "actor_2", "start_op_id": b.op_id,
                           "page_op_ids": b_pages})
    last = a_rows[-1]
    return {"max_dist_tick_m": max(r["dist_center_m"] for r in a_rows), "out_of_radius_ticks_n":
            last["out_of_radius_ticks_n"], "path_len_m": last["path_len_m"], "dest_reached_n":
            last["dest_reached_n"]}


def step_s7(ctx, fx, fault=None):
    _need(_reset(ctx), "S7 reset")
    _need(_freeze(ctx, True, ENV_BASE), "S7 freeze")
    _need(_observe(ctx), "S7 obs previa")
    time.sleep(0.5)
    base = _need(_observe(ctx), "S7 baseline")
    app = _scene(ctx, fx, props=2, actors=2, env=ENV_MIXED, cap_mode="drop_after_validate", fault=fault)
    if app.status != "rejected" or app.reason != "expansion_unavailable":
        raise RuntimeError(f"S7 apply: {app.status}/{app.reason}")
    post = _need(_observe(ctx), "S7 post")
    _need(_freeze(ctx, False), "S7 unfreeze")
    _rec(ctx, ("S3-12",), {"kind": "capability_lost", "baseline_observe_op_id": base.op_id,
                           "apply_op_id": app.op_id, "post_observe_op_id": post.op_id})
    n = post.payload["num"]
    return {"last_op_spawned_props_ever_n": n.get("last_op_spawned_props_ever_n"),
            "last_op_deleted_objects_ever_n": n.get("last_op_deleted_objects_ever_n"),
            "last_op_env_writes_ever_n": n.get("last_op_env_writes_ever_n")}


def step_s8(ctx, fx, with_s3_11=True):
    _restart_step(ctx, "S8_restart_no_expansion", False,
                  "Reinicia DayZServer cargando solo @DayZSandbox_QA (sin Expansion ni @DayZSandbox_QA_Expansion)")
    obs = _need(_observe(ctx), "S8 observe")
    props = _need(_scene(ctx, fx, props=2, actors=0), "S8 props")
    post_props = _need(_observe(ctx), "S8 observe tras props")
    _need(_reset(ctx), "S8 reset")
    _need(_freeze(ctx, True, ENV_BASE), "S8 freeze")
    base = _need(_observe(ctx), "S8 baseline")
    app = _scene(ctx, fx, props=2, actors=2, env=ENV_MIXED)
    if app.status != "rejected" or app.reason != "expansion_unavailable":
        raise RuntimeError(f"S8 apply: {app.status}/{app.reason}")
    post = _need(_observe(ctx), "S8 post")
    _need(_freeze(ctx, False), "S8 unfreeze")
    if with_s3_11:
        _rec(ctx, ("S3-11",), {"kind": "observe_no_expansion", "observe_op_id": obs.op_id})
        _rec(ctx, ("S3-11",), {"kind": "apply_props_only", "apply_op_id": props.op_id,
                               "observe_op_id": post_props.op_id})
    _rec(ctx, ("S3-12",), {"kind": "no_expansion", "baseline_observe_op_id": base.op_id,
                           "apply_op_id": app.op_id, "post_observe_op_id": post.op_id})


# ------------------------------------------------------------------ partes
def _run_main(ctx, fx):
    step_s0(ctx)
    step_s1(ctx, fx)
    step_s2_positive(ctx, fx)
    step_s2_negatives(ctx, fx)
    step_s3(ctx, fx)
    step_s4_positive(ctx, fx)
    step_s4_negatives(ctx, fx, ALL_CHECK_TAGS, {})
    step_s5(ctx, fx)
    step_s6(ctx, fx)
    step_s7(ctx, fx)
    step_s8(ctx, fx)
    step_s9(ctx)


def _setup_scene(ctx, fx):
    _need(_scene(ctx, fx, props=2, actors=2), "setup scene")


def _run_mutant(ctx, fx, name):
    step_s0(ctx)
    effect = {}
    target = ""
    if name == "roam_out_of_radius" or name == "roam_stand_still":
        effect = step_s6(ctx, fx, fault="roam_ignore_radius" if name == "roam_out_of_radius" else "roam_stand_still")
        target = "S6:act_behaviour_run"
    elif name == "fsm_is_final_as_reached":
        _setup_scene(ctx, fx)
        effect = step_s2_negatives(ctx, fx, fault="fsm_is_final_as_reached")
        target = "S2:act_behaviour_run"
    elif name == "wrong_emote_cmd":
        _setup_scene(ctx, fx)
        _unk, effect = step_s4_positive(ctx, fx, fault="wrong_emote_played")
        target = "S4:act_emote_run"
    elif name == "stale_callback_contamination":
        _setup_scene(ctx, fx)
        obs = step_s4_negatives(ctx, fx, ("S3-08",), {"stale_callback_isolation": "accept_stale_cb"})
        effect = {k: obs["stale"][k] for k in ("cb_inst_id", "max_cb_inst_at_req_n", "emote_state")}
        target = "S4:act_emote_run"
    elif name == "canceled_emote_as_done":
        _setup_scene(ctx, fx)
        obs = step_s4_negatives(ctx, fx, ("S3-08",), {"cancel_after_start": "canceled_as_done"})
        effect = {k: obs["cancel_after_start"][k] for k in ("raw_p_canceled_b", "emote_state")}
        target = "S4:act_emote_run"
    elif name == "late_emote_after_timeout":
        _setup_scene(ctx, fx)
        obs = step_s4_negatives(ctx, fx, ("S3-09",), {"never_starts": "no_clear_on_timeout"}, full=False)
        effect = {k: obs["never_starts"][k] for k in ("exp_pending_id", "post_cleanup_cb_count_n")}
        target = "S4:act_emote_run"
    elif name == "no_clear_on_stop_after_start":
        _setup_scene(ctx, fx)
        obs = step_s4_negatives(ctx, fx, ("S3-09",), {"cancel_after_start": "no_clear_after_start"}, full=False)
        effect = {"exp_pending_id": obs["cancel_after_start"]["exp_pending_id"],
                  "cleanup_tick_ms_gt_0": 1 if obs["cancel_after_start"]["cleanup_tick_ms"] > 0 else 0}
        target = "S4:act_emote_run"
    elif name == "combat_emote_as_done":
        _setup_scene(ctx, fx)
        effect = step_s5(ctx, fx, fault="combat_emote_as_done")
        target = "S5:act_emote_run"
    elif name == "extra_default_gear":
        info = step_s1(ctx, fx, fault="extra_default_gear")
        extra = [f"{r['slot_name']}:{r['item_class']}" for r in info["obs1_rows"]
                 if r["slot_name"] == "Armband"]
        effect = {"pre_gear_seeded_n": info["apply1"]["pre_gear_seeded_n"],
                  "pre_gear_cleared_n": info["apply1"]["pre_gear_cleared_n"],
                  "extra_item": extra[0] if extra else ""}
        target = "S1:act_scene_apply"
    elif name == "props_before_actor_check":
        effect = step_s7(ctx, fx, fault="props_before_actor_check")
        step_s8(ctx, fx, with_s3_11=False)
        target = "S7:act_scene_apply"
    else:
        raise ValueError(name)
    _need(_freeze(ctx, False), "mutant unfreeze")
    _need(_reset(ctx), "mutant reset")
    step_s9(ctx)
    ctx.write_injection(mutant=name, kind="qa_fault", target=target, observable_effect=effect)


def _planned_parts(part_arg):
    all_parts = ["run"] + [f"mut-{n}" for n in s3_mutants.EXPECTED_MUTANTS]
    if part_arg == "all":
        return all_parts
    if part_arg not in all_parts:
        raise ValueError(f"unknown part {part_arg!r} for {SPIKE_ID}")
    return [part_arg]


def run_part(args, base_dir, argv, part_name):
    fx = _fixtures()
    with S3PartContext(base_dir=base_dir, part_name=part_name, spike_id=SPIKE_ID, args=args, argv=argv) as ctx:
        if ctx.startup_reason is None:
            if part_name == "run":
                _run_main(ctx, fx)
            else:
                _run_mutant(ctx, fx, part_name[len("mut-"):])
        reason, detail = ctx.startup_reason, ctx.exp_detail
        ctx.finalize_manifest()
    part_dir = Path(base_dir) / part_name
    if reason == "artifact_unverified" and detail:
        verdict = gate_core.make_verdict(SPIKE_ID, 2, reasons=[reason])
        verdict["detail"] = detail
    else:
        verdict = s3_eval.evaluate(part_dir)
    gate_core.write_json(part_dir / "verdict.json", verdict)
    return verdict


def run(args, evidence, argv):
    base_dir = Path(evidence)
    parts = _planned_parts(getattr(args, "part", "all") or "all")
    started = gate_core.utc_now()
    for part_name in parts:
        run_part(args, base_dir, argv, part_name)
    if not (base_dir / "manifest.json").is_file():
        gate_core.write_json(
            base_dir / "manifest.json",
            gate_core.make_manifest("spike", SPIKE_ID, args, argv, started, gate_core.utc_now()),
        )
    agg = f03_common.aggregate_spike(base_dir, SPIKE_ID)
    return int(agg["exit_code"])
