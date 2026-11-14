"""Runner de la prueba de base F0.3-0 (brief §5.2, §8.2, §13 A1-A5, §14)."""

import secrets
import time
from pathlib import Path

import f03_base_eval
import f03_base_mutants
import f03_common
import gate_core
import wire

SPIKE_ID = "F0.3-0"
PEERS = ("server", "client")


def _planned_parts(part_arg: str) -> list[str]:
    all_parts = (
        ["run"]
        + [f"mut-{name}" for name in f03_base_mutants.EXPECTED_MUTANTS]
        + list(f03_base_mutants.EXPECTED_HARNESS_TESTS.keys())
    )
    if part_arg == "all":
        return all_parts
    if part_arg not in all_parts:
        raise ValueError(f"unknown part {part_arg!r} for {SPIKE_ID}")
    return [part_arg]


def _result_event_for(ctx: f03_common.PartContext, op_id: str) -> dict | None:
    with ctx.bridge.cv:
        for ev in reversed(ctx.bridge.events):
            if ev.get("ev") == "result" and ev.get("http") == 200 and ev.get("op_id") == op_id:
                return dict(ev)
    return None


def _wait_cut_and_reconnect_poll(
    ctx: f03_common.PartContext,
    peer: str,
    cut_start_ms: float,
    timeout_s: float = 15.0,
) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with ctx.bridge.cv:
            cut_end_ev = None
            for ev in ctx.bridge.events:
                if ev.get("ev") == "cut_end" and ev.get("peer") == peer and float(ev.get("t_ms", 0.0)) >= cut_start_ms:
                    cut_end_ev = ev
            if cut_end_ev is not None:
                end_t = float(cut_end_ev["t_ms"])
                for ev in ctx.bridge.events:
                    if (
                        ev.get("ev") == "poll"
                        and ev.get("http") == 200
                        and ev.get("peer") == peer
                        and float(ev.get("t_ms", 0.0)) >= end_t
                    ):
                        return dict(ev)
        time.sleep(0.05)
    return None


def _paginate_instant(
    ctx: f03_common.PartContext,
    peer: str,
    verb: str,
    extra_str: dict | None = None,
) -> tuple[list[f03_common.OpOutcome], list[dict]]:
    base_str = dict(extra_str or {})
    p0 = f03_common.issue_one(
        ctx,
        peer,
        verb,
        wire.pack_payload(scalars_str=base_str, scalars_num={"page_n": 0}),
    )
    outcomes = [p0]
    if p0.status != "done":
        return outcomes, []
    rows = list(p0.payload["rows"])
    pages_n = int(p0.payload["num"].get("pages_n", 0))
    for page_idx in range(1, pages_n):
        pi = f03_common.issue_one(
            ctx,
            peer,
            verb,
            wire.pack_payload(scalars_str=base_str, scalars_num={"page_n": page_idx}),
        )
        outcomes.append(pi)
        if pi.status != "done":
            break
        rows.extend(pi.payload["rows"])
    return outcomes, rows


def _run_base_01(ctx: f03_common.PartContext) -> None:
    for peer in PEERS:
        cand_id = ctx.peek_next_op_id()
        inst = ctx.bridge.registered(peer)
        issued_fixed = round(ctx.bridge.now_ms(), 3)
        probe_now = max(float(issued_fixed), 99999999.999)
        ttl_int = int(ctx.ttl_ms)

        def _make_args(pad_len: int) -> dict:
            p = wire.pack_payload(
                scalars_str={"pad_in": "x" * pad_len, "qa_fault": wire.QA_FAULT_NONE},
                scalars_num={"v1_n": 12.5, "v2_n": -2.5},
                num_cols=["c_n"],
                str_cols=["c_s"],
                row_dicts=[{"c_n": 1.0, "c_s": "ab"}, {"c_n": 2.0, "c_s": "cd"}],
            )
            return p

        base_args = _make_args(0)
        base_order = {
            "args": base_args,
            "inst": inst,
            "issued_ms": issued_fixed,
            "op_id": cand_id,
            "ttl_ms": ttl_int,
            "verb": "qa_echo",
        }
        base_len = len(wire.poll_wire_bytes(base_order, now_ms=probe_now))
        pad_len = max(0, wire.WIRE_CAP - base_len)
        sized_args = _make_args(pad_len)
        sized_order = dict(base_order, args=sized_args)
        while len(wire.poll_wire_bytes(sized_order, now_ms=probe_now)) > wire.WIRE_CAP and pad_len > 0:
            pad_len -= 1
            sized_args = _make_args(pad_len)
            sized_order = dict(base_order, args=sized_args)
        while len(wire.poll_wire_bytes(sized_order, now_ms=probe_now)) < wire.WIRE_CAP:
            pad_len += 1
            cand_args = _make_args(pad_len)
            cand_order = dict(base_order, args=cand_args)
            if len(wire.poll_wire_bytes(cand_order, now_ms=probe_now)) > wire.WIRE_CAP:
                pad_len -= 1
                break
            sized_args = cand_args
            sized_order = cand_order

        out = f03_common.issue_one(
            ctx,
            peer,
            "qa_echo",
            sized_args,
            issued_ms=issued_fixed,
        )
        ctx.record_scenario({"check": "BASE-01", "op_id": out.op_id, "peer": peer})


def _run_base_02(ctx: f03_common.PartContext) -> None:
    for peer in PEERS:
        cal = f03_common.issue_one(
            ctx,
            peer,
            "qa_echo",
            wire.pack_payload(scalars_num={"pad_bytes_n": 1, "bal_n": -1}),
        )
        cal_ev = _result_event_for(ctx, cal.op_id)
        base_body_len = int(cal_ev["body_len"]) if cal_ev is not None else 350
        # Aumentar pad_bytes_n de 1 a pad_ok suma (pad_ok - 1) bytes en pad y ~3 bytes en sv_chars_n;
        # apuntamos a WIRE_CAP - 5 dentro de [WIRE_CAP - 16, WIRE_CAP].
        pad_ok = max(1, 1 + (wire.WIRE_CAP - 5 - base_body_len) - 3)
        ok_out = f03_common.issue_one(
            ctx,
            peer,
            "qa_echo",
            wire.pack_payload(scalars_num={"pad_bytes_n": pad_ok, "bal_n": -pad_ok}),
        )
        over_out = f03_common.issue_one(
            ctx,
            peer,
            "qa_echo",
            wire.pack_payload(scalars_num={"pad_bytes_n": wire.WIRE_CAP, "bal_n": 0}),
        )
        ctx.record_scenario(
            {
                "check": "BASE-02",
                "ok_op_id": ok_out.op_id,
                "over_op_id": over_out.op_id,
                "peer": peer,
            }
        )


def _run_base_03(ctx: f03_common.PartContext, omit_mid_stop: bool) -> None:
    pre_echo = {}
    start_out = {}
    concurrent_ids: dict[str, list[str]] = {"server": [], "client": []}

    for peer in PEERS:
        pre_echo[peer] = f03_common.issue_one(ctx, peer, "qa_echo")

    for peer in PEERS:
        start_out[peer] = f03_common.issue_one(
            ctx,
            peer,
            "qa_timer_start",
            wire.pack_payload(scalars_num={"duration_ms": 6000, "sample_step_ms": 50}),
        )

    t_started = time.monotonic()
    for step_idx in range(5):
        for peer in PEERS:
            jid = start_out[peer].op_id
            if step_idx % 2 == 0:
                c_out = f03_common.issue_one(
                    ctx,
                    peer,
                    "job_read",
                    wire.pack_payload({"job": jid}, {"page_n": 0}),
                )
            else:
                c_out = f03_common.issue_one(ctx, peer, "qa_echo")
            concurrent_ids[peer].append(c_out.op_id)
        target_elapsed = (step_idx + 1) * 0.48
        rem = (t_started + target_elapsed) - time.monotonic()
        if rem > 0:
            time.sleep(rem)

    if omit_mid_stop:
        inj_when = ctx.now_h_ms()
        # Esperar a que el timer de 6 s acabe por su cuenta en "done" (sin haber enviado job_stop a mitad).
        deadline = t_started + 7.5
        for peer in PEERS:
            jid = start_out[peer].op_id
            while time.monotonic() < deadline:
                probe = f03_common.issue_one(
                    ctx,
                    peer,
                    "job_read",
                    wire.pack_payload({"job": jid}, {"page_n": 0}),
                )
                if probe.status == "done" and probe.payload["str"].get("state") != "running":
                    break
                time.sleep(0.15)

    stop1 = {}
    stop2 = {}
    post_echo = {}
    for peer in PEERS:
        jid = start_out[peer].op_id
        stop1[peer] = f03_common.issue_one(ctx, peer, "job_stop", wire.pack_payload({"job": jid}))
        stop2[peer] = f03_common.issue_one(ctx, peer, "job_stop", wire.pack_payload({"job": jid}))
        post_echo[peer] = f03_common.issue_one(ctx, peer, "qa_echo")
        ctx.record_scenario(
            {
                "check": "BASE-03",
                "concurrent_op_ids": concurrent_ids[peer],
                "peer": peer,
                "post_echo_op_id": post_echo[peer].op_id,
                "pre_echo_op_id": pre_echo[peer].op_id,
                "start_op_id": start_out[peer].op_id,
                "stop1_op_id": stop1[peer].op_id,
                "stop2_op_id": stop2[peer].op_id,
            }
        )

    if omit_mid_stop:
        ctx.write_injection(
            mutant="ignore_stop",
            kind="scenario",
            target="BASE-03:job_stop",
            observable_effect={
                "client_terminal_state": stop1["client"].payload["str"].get("state"),
                "omitted_mid_run_stop": True,
                "server_terminal_state": stop1["server"].payload["str"].get("state"),
            },
            when_h_ms=inj_when,
        )


def _run_base_04_and_05(ctx: f03_common.PartContext) -> None:
    start_out = {}
    t0 = time.monotonic()
    for peer in PEERS:
        start_out[peer] = f03_common.issue_one(
            ctx,
            peer,
            "qa_timer_start",
            wire.pack_payload(scalars_num={"duration_ms": 10000, "sample_step_ms": 100}),
        )

    wait_rem = (t0 + 10.15) - time.monotonic()
    if wait_rem > 0:
        time.sleep(wait_rem)

    for peer in PEERS:
        jid = start_out[peer].op_id
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            chk = f03_common.issue_one(
                ctx,
                peer,
                "job_read",
                wire.pack_payload({"job": jid}, {"page_n": 0}),
            )
            if chk.status == "done" and chk.payload["str"].get("state") in f03_common.TERMINAL_JOB_STATES:
                break
            time.sleep(0.1)

        post_echo = f03_common.issue_one(ctx, peer, "qa_echo")
        paged = f03_common.read_job_pages(ctx, peer, jid)
        page_ids = [o.op_id for o in paged["outcomes"]]

        ctx.record_scenario(
            {
                "check": "BASE-04",
                "page_op_ids": page_ids,
                "peer": peer,
                "post_echo_op_id": post_echo.op_id,
                "start_op_id": jid,
            }
        )
        ctx.record_scenario(
            {
                "check": "BASE-05",
                "page_op_ids": page_ids,
                "peer": peer,
                "start_op_id": jid,
            }
        )


def _run_base_06(ctx: f03_common.PartContext) -> None:
    first_out = {}
    second_out = {}
    t0 = time.monotonic()
    for peer in PEERS:
        first_out[peer] = f03_common.issue_one(
            ctx,
            peer,
            "qa_timer_start",
            wire.pack_payload(scalars_num={"duration_ms": 600, "sample_step_ms": 50}),
        )
        second_out[peer] = f03_common.issue_one(
            ctx,
            peer,
            "qa_timer_start",
            wire.pack_payload(scalars_num={"duration_ms": 600, "sample_step_ms": 50}),
        )

    rem = (t0 + 0.75) - time.monotonic()
    if rem > 0:
        time.sleep(rem)

    for peer in PEERS:
        jid = first_out[peer].op_id
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            chk = f03_common.issue_one(
                ctx,
                peer,
                "job_read",
                wire.pack_payload({"job": jid}, {"page_n": 0}),
            )
            if chk.status == "done" and chk.payload["str"].get("state") in f03_common.TERMINAL_JOB_STATES:
                break
            time.sleep(0.08)
        paged = f03_common.read_job_pages(ctx, peer, jid)
        ctx.record_scenario(
            {
                "check": "BASE-06",
                "first_op_id": jid,
                "first_page_op_ids": [o.op_id for o in paged["outcomes"]],
                "peer": peer,
                "second_op_id": second_out[peer].op_id,
            }
        )


def _run_base_07(ctx: f03_common.PartContext) -> None:
    client_inst = ctx.bridge.registered("client") or ""
    pre_echo = f03_common.issue_one(ctx, "client", "qa_echo")
    pre_count = int(pre_echo.payload["num"].get("rpc_ping_count_n", 0))

    ping_out = f03_common.issue_one(
        ctx,
        "server",
        "qa_rpc_ping",
        wire.pack_payload({"client_inst": client_inst}, {"token_n": 4242}),
    )

    post_echo = None
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        cand = f03_common.issue_one(ctx, "client", "qa_echo")
        post_echo = cand
        if int(cand.payload["num"].get("rpc_ping_count_n", 0)) > pre_count:
            break
        time.sleep(0.05)

    assert post_echo is not None
    ping_pages, _rows = _paginate_instant(ctx, "client", "qa_ping_page")
    ctx.record_scenario(
        {
            "check": "BASE-07",
            "ping_op_id": ping_out.op_id,
            "ping_page_op_ids": [o.op_id for o in ping_pages],
            "post_echo_op_id": post_echo.op_id,
            "pre_echo_op_id": pre_echo.op_id,
        }
    )


def _run_base_09(ctx: f03_common.PartContext) -> None:
    for peer in PEERS:
        fill_id = secrets.token_hex(8)
        fill_out = f03_common.issue_one(
            ctx,
            peer,
            "qa_cache_fill",
            wire.pack_payload({"fill_id": fill_id}, {"n_n": 1030}),
        )
        first_id = fill_out.payload["str"].get("first_id", f"{fill_id}-0")
        last_id = fill_out.payload["str"].get("last_id", f"{fill_id}-1029")

        snap_out = f03_common.issue_one(ctx, peer, "qa_cache_snapshot")
        snap_id = snap_out.payload["str"].get("snap_id", snap_out.op_id)
        pages, _rows = _paginate_instant(ctx, peer, "qa_cache_page", extra_str={"snap_id": snap_id})

        # Reentrega de last_id (debe seguir en cache -> dup=True) y first_id (expulsado -> dup=False).
        f03_common.issue_one(
            ctx,
            peer,
            "qa_echo",
            wire.pack_payload(scalars_str={"probe": "last"}),
            op_id=last_id,
        )
        f03_common.issue_one(
            ctx,
            peer,
            "qa_echo",
            wire.pack_payload(scalars_str={"probe": "first"}),
            op_id=first_id,
        )
        ctx.record_scenario(
            {
                "check": "BASE-09",
                "fill_op_id": fill_out.op_id,
                "page_op_ids": [o.op_id for o in pages],
                "peer": peer,
                "snap_op_id": snap_out.op_id,
            }
        )


def _run_base_10(ctx: f03_common.PartContext) -> None:
    client_inst = ctx.bridge.registered("client") or ""
    pre_pages, pre_rows = _paginate_instant(ctx, "client", "qa_rpclog_page")
    del pre_pages
    max_seq = max((int(r["seq_n"]) for r in pre_rows), default=0)
    seq0 = max_seq + 1000 if pre_rows else 1000

    burst_out = f03_common.issue_one(
        ctx,
        "server",
        "rpc_burst",
        {
            "client_inst": client_inst,
            "count": 520,
            "interval_ms": 5,
            "pos": [10.0, 20.0, 30.0],
            "seq0": seq0,
            "ypr": [0.0, 0.0, 0.0],
        },
        ttl_ms=20000,
        timeout_ms=25000,
    )
    time.sleep(0.12)
    pages, _rows = _paginate_instant(ctx, "client", "qa_rpclog_page")
    ctx.record_scenario(
        {
            "burst_op_id": burst_out.op_id,
            "check": "BASE-10",
            "count": 520,
            "page_op_ids": [o.op_id for o in pages],
            "seq0": seq0,
        }
    )


def _run_base_12_healthy(ctx: f03_common.PartContext) -> None:
    for peer in PEERS:
        info_before = f03_common.issue_one(ctx, peer, "qa_info")
        echo_ids = []
        for idx in range(50):
            eo = f03_common.issue_one(ctx, peer, "qa_echo", wire.pack_payload(scalars_num={"seq_n": idx}))
            echo_ids.append(eo.op_id)
        info_after = f03_common.issue_one(ctx, peer, "qa_info")
        ctx.record_scenario(
            {
                "after_op_id": info_after.op_id,
                "before_op_id": info_before.op_id,
                "check": "BASE-12",
                "echo_op_ids": echo_ids,
                "peer": peer,
            }
        )


def _run_base_08(ctx: f03_common.PartContext, timer_fault: str | None) -> None:
    start_a = {}
    inj_when = ctx.now_h_ms()
    for peer in PEERS:
        start_a[peer] = f03_common.issue_one(
            ctx,
            peer,
            "qa_timer_start",
            wire.pack_payload(
                scalars_num={
                    "duration_ms": 8000,
                    "max_duration_ms": 1200,
                    "sample_step_ms": 50,
                    "witness_b": 1,
                }
            ),
            qa_fault=timer_fault,
        )

    cut_start_ms = ctx.now_h_ms()
    for peer in PEERS:
        ctx.bridge.cut(peer, 3500)

    for peer in PEERS:
        _wait_cut_and_reconnect_poll(ctx, peer, cut_start_ms, timeout_s=15.0)

    obs_effects = {}
    for peer in PEERS:
        jid_a = start_a[peer].op_id
        p0 = f03_common.issue_one(
            ctx,
            peer,
            "job_read",
            wire.pack_payload({"job": jid_a}, {"page_n": 0}),
        )
        state_a = p0.payload["str"].get("state", "")
        if p0.status == "done" and state_a in f03_common.TERMINAL_JOB_STATES:
            paged_a = f03_common.read_job_pages(ctx, peer, jid_a)
            a_read_ids = [o.op_id for o in paged_a["outcomes"]]
            obs_effects[peer] = {
                "end_tick_ms": paged_a["num"].get("end_tick_ms"),
                "onjobend_tick_ms": paged_a["num"].get("onjobend_tick_ms"),
                "released_tick_ms": paged_a["num"].get("released_tick_ms"),
                "state": state_a,
            }
        else:
            a_read_ids = [p0.op_id]
            obs_effects[peer] = {"state": state_a}

        # Dar margen breve para que el testigo B (200 ms) termine si arranco.
        time.sleep(0.25)
        echo_out = f03_common.issue_one(ctx, peer, "qa_echo")
        w_jid = echo_out.payload["str"].get("witness_job_id") or f"{jid_a}:witness"
        w_read = f03_common.issue_one(
            ctx,
            peer,
            "job_read",
            wire.pack_payload({"job": w_jid}, {"page_n": 0}),
        )

        # Si A seguia vivo (p.ej. bajo freeze_on_wait), limpiarlo despues de registrar la evidencia de BASE-08.
        if state_a == "running":
            f03_common.issue_one(ctx, peer, "job_stop", wire.pack_payload({"job": jid_a}))
            time.sleep(0.28)
            echo_post = f03_common.issue_one(ctx, peer, "qa_echo")
            w_jid_post = echo_post.payload["str"].get("witness_job_id") or w_jid
            w_state_chk = f03_common.issue_one(
                ctx,
                peer,
                "job_read",
                wire.pack_payload({"job": w_jid_post}, {"page_n": 0}),
            )
            if w_state_chk.status == "done" and w_state_chk.payload["str"].get("state") == "running":
                f03_common.issue_one(ctx, peer, "job_stop", wire.pack_payload({"job": w_jid_post}))

        ctx.record_scenario(
            {
                "a_read_op_ids": a_read_ids,
                "check": "BASE-08",
                "cut_start_ms": cut_start_ms,
                "echo_op_id": echo_out.op_id,
                "peer": peer,
                "start_op_id": jid_a,
                "witness_read_op_id": w_read.op_id,
            }
        )

    if timer_fault is not None:
        ctx.write_injection(
            mutant=timer_fault,
            kind="qa_fault",
            target=start_a["server"].op_id,
            observable_effect=obs_effects,
            when_h_ms=inj_when,
        )


def _run_base_11(ctx: f03_common.PartContext, effect_fault: str | None) -> None:
    client_inst = ctx.bridge.registered("client") or ""
    pre_ping_pages, pre_ping_rows = _paginate_instant(ctx, "client", "qa_ping_page")
    del pre_ping_pages
    max_tok = max((int(r["token_n"]) for r in pre_ping_rows), default=0)
    token0_n = max_tok + 1000 if pre_ping_rows else 1000

    inj_when = ctx.now_h_ms()
    start_eff = f03_common.issue_one(
        ctx,
        "server",
        "qa_effect_start",
        wire.pack_payload(
            {"client_inst": client_inst},
            {"count_n": 40, "period_ms": 300, "token0_n": token0_n, "witness_b": 1},
        ),
        qa_fault=effect_fault,
    )
    eff_jid = start_eff.op_id

    cut_start_ms = ctx.now_h_ms()
    ctx.bridge.cut("server", 6000)
    _wait_cut_and_reconnect_poll(ctx, "server", cut_start_ms, timeout_s=18.0)

    p0 = f03_common.issue_one(
        ctx,
        "server",
        "job_read",
        wire.pack_payload({"job": eff_jid}, {"page_n": 0}),
    )
    eff_state = p0.payload["str"].get("state", "")
    if p0.status == "done" and eff_state in f03_common.TERMINAL_JOB_STATES:
        paged_eff = f03_common.read_job_pages(ctx, "server", eff_jid)
        eff_read_ids = [o.op_id for o in paged_eff["outcomes"]]
        eff_rows = paged_eff["rows"]
    else:
        eff_read_ids = [p0.op_id]
        eff_rows = p0.payload["rows"]

    time.sleep(0.25)
    srv_echo = f03_common.issue_one(ctx, "server", "qa_echo")
    w_jid = srv_echo.payload["str"].get("witness_job_id") or f"{eff_jid}:witness"
    w_read = f03_common.issue_one(
        ctx,
        "server",
        "job_read",
        wire.pack_payload({"job": w_jid}, {"page_n": 0}),
    )
    time.sleep(0.1)
    ping_pages, post_ping_rows = _paginate_instant(ctx, "client", "qa_ping_page")

    if eff_state == "running":
        f03_common.issue_one(ctx, "server", "job_stop", wire.pack_payload({"job": eff_jid}))
        time.sleep(0.28)
        echo_post = f03_common.issue_one(ctx, "server", "qa_echo")
        w_jid_post = echo_post.payload["str"].get("witness_job_id") or w_jid
        w_chk = f03_common.issue_one(
            ctx,
            "server",
            "job_read",
            wire.pack_payload({"job": w_jid_post}, {"page_n": 0}),
        )
        if w_chk.status == "done" and w_chk.payload["str"].get("state") == "running":
            f03_common.issue_one(ctx, "server", "job_stop", wire.pack_payload({"job": w_jid_post}))

    ctx.record_scenario(
        {
            "check": "BASE-11",
            "cut_start_ms": cut_start_ms,
            "echo_op_id": srv_echo.op_id,
            "eff_read_op_ids": eff_read_ids,
            "ping_page_op_ids": [o.op_id for o in ping_pages],
            "start_op_id": eff_jid,
            "token0_n": token0_n,
            "witness_read_op_id": w_read.op_id,
        }
    )

    if effect_fault is not None:
        new_pings = [r for r in post_ping_rows if int(r["token_n"]) >= token0_n]
        ctx.write_injection(
            mutant=effect_fault,
            kind="qa_fault",
            target=eff_jid,
            observable_effect={
                "client_new_pings_n": len(new_pings),
                "server_rows_sample_n": len(eff_rows),
                "server_state_at_reconnect": eff_state,
            },
            when_h_ms=inj_when,
        )


def _run_base_13(ctx: f03_common.PartContext) -> None:
    for peer in PEERS:
        hello_cut_ms = ctx.now_h_ms()
        ctx.bridge.hello_ok_false = 1
        ctx.bridge.cut(peer, 150)

        # Esperar al re-hello con ok=True y al siguiente poll 200 de ese peer.
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            with ctx.bridge.cv:
                saw_false = any(
                    ev.get("ev") == "hello"
                    and ev.get("http") == 200
                    and ev.get("ok") is False
                    and ev.get("peer") == peer
                    and float(ev.get("t_ms", 0.0)) >= hello_cut_ms
                    for ev in ctx.bridge.events
                )
                saw_true = any(
                    ev.get("ev") == "hello"
                    and ev.get("http") == 200
                    and ev.get("ok") is True
                    and ev.get("peer") == peer
                    and float(ev.get("t_ms", 0.0)) >= hello_cut_ms
                    for ev in ctx.bridge.events
                )
            if saw_false and saw_true and ctx.bridge.registered(peer) is not None:
                break
            time.sleep(0.05)

        ctx.bridge.ack_ok_false = 1
        ack_out = f03_common.issue_one(
            ctx,
            peer,
            "qa_echo",
            wire.pack_payload(scalars_num={"ack_probe_n": 1}),
        )
        ctx.record_scenario(
            {
                "ack_op_id": ack_out.op_id,
                "check": "BASE-13",
                "hello_cut_start_ms": hello_cut_ms,
                "peer": peer,
            }
        )


def _run_standard_part(ctx: f03_common.PartContext, part_name: str) -> None:
    omit_stop = part_name == "mut-ignore_stop"
    timer_fault = None
    if part_name == "mut-freeze_on_wait":
        timer_fault = "freeze_on_wait"
    elif part_name == "mut-defer_cleanup":
        timer_fault = "defer_cleanup"

    effect_fault = None
    if part_name == "mut-ignore_deadman":
        effect_fault = "ignore_deadman"
    elif part_name == "mut-skip_send":
        effect_fault = "skip_send"

    _run_base_01(ctx)
    _run_base_02(ctx)
    _run_base_03(ctx, omit_mid_stop=omit_stop)
    _run_base_04_and_05(ctx)
    _run_base_06(ctx)
    _run_base_07(ctx)
    _run_base_09(ctx)
    _run_base_10(ctx)
    _run_base_12_healthy(ctx)
    _run_base_08(ctx, timer_fault=timer_fault)
    _run_base_11(ctx, effect_fault=effect_fault)
    _run_base_13(ctx)


def _run_probe_budget_part(ctx: f03_common.PartContext) -> None:
    for role in ctx.required_peers():
        ctx.write_config(role, callback_budget=30, retry_ms=100)
    ctx.bridge.hello_503 = -1
    for role in ctx.required_peers():
        ctx.bridge.cut(role, 150)

    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        rows = ctx.collect_probe_budget_logs()
        logged_peers = {r["peer"] for r in rows}
        if all(r in logged_peers for r in ctx.required_peers()):
            break
        time.sleep(0.1)

    # Margen breve para cerrar conexiones en curso antes de abrir la ventana silenciosa de 20 s.
    time.sleep(0.25)
    quiet_start_ms = ctx.now_h_ms()
    time.sleep(20.2)
    quiet_end_ms = ctx.now_h_ms()
    ctx.collect_probe_budget_logs()
    ctx.record_scenario(
        {
            "check": "BASE-12",
            "quiet_end_ms": quiet_end_ms,
            "quiet_start_ms": quiet_start_ms,
        }
    )


def run_part(args, base_dir: Path, argv: list[str], part_name: str) -> dict:
    with f03_common.PartContext(
        base_dir=base_dir,
        part_name=part_name,
        spike_id=SPIKE_ID,
        args=args,
        argv=argv,
    ) as ctx:
        if ctx.startup_reason is None:
            if part_name == "probe-budget":
                _run_probe_budget_part(ctx)
            else:
                _run_standard_part(ctx, part_name)
        ctx.collect_probe_budget_logs()
        ctx.finalize_manifest()

    part_dir = Path(base_dir) / part_name
    verdict = f03_base_eval.evaluate(part_dir)
    gate_core.write_json(part_dir / "verdict.json", verdict)
    return verdict


def run(args, evidence: Path, argv: list[str]) -> int:
    base_dir = Path(evidence)
    part_arg = getattr(args, "part", "all") or "all"
    parts = _planned_parts(part_arg)

    started_utc = gate_core.utc_now()
    for part_name in parts:
        run_part(args, base_dir, argv, part_name)

    if not (base_dir / "manifest.json").is_file():
        gate_core.write_json(
            base_dir / "manifest.json",
            gate_core.make_manifest("spike", SPIKE_ID, args, argv, started_utc, gate_core.utc_now()),
        )

    agg = f03_common.aggregate_spike(base_dir, SPIKE_ID)
    return int(agg["exit_code"])
