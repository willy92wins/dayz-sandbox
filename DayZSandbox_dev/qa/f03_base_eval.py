"""Evaluador puro y ciego de F0.3-0 (brief §5.2, §6.1(12), §8.2, §13 A2-A3, §14)."""

import math
from pathlib import Path

import f03_common
import gate_core
import wire

SPIKE_ID = "F0.3-0"
CHECK_IDS = tuple(f"BASE-{i:02d}" for i in range(1, 14))
CACHE_CAP = 1024
RPCLOG_CAP = 512
CALLBACK_POOL_MAX = 8
CUT_MARGIN_MS = 250.0
HTTP_BRIDGE_EVENTS = frozenset(
    {
        "hello",
        "poll",
        "keepalive",
        "result",
        "ack_reject",
        "result_drop",
        # Nombre real del 401 que emite bridge_qa._dispatch (antes "auth_fail", que no existe: H6 de Sol r1).
        "auth_reject",
        "inst_reject",
        "bad_body",
        "wire_cap_exceeded",
    }
)


def _chk(cid: str, status: str, detail: str = "") -> dict:
    return {"detail": detail, "id": cid, "status": status}


def _unpack_result_read(res_body: dict) -> dict:
    raw_read = res_body.get("read") if isinstance(res_body.get("read"), dict) else {}
    if raw_read.get("has") == ["payload"]:
        return wire.unpack_payload(raw_read)
    return {"num": {}, "rows": [], "str": {}}


def _index_bridge(bridge_rows: list[dict]) -> dict:
    enq_by_op: dict[str, dict] = {}
    polls_by_op: dict[str, list[dict]] = {}
    results_by_op: dict[str, list[dict]] = {}
    terminal_err_by_op: dict[str, str] = {}
    ack_rejects_by_op: dict[str, int] = {}

    for ev in bridge_rows:
        kind = ev.get("ev")
        oid = ev.get("op_id")
        if kind == "enq" and isinstance(oid, str) and oid not in enq_by_op:
            enq_by_op[oid] = ev
        elif kind == "poll" and ev.get("http") == 200:
            for pid in ev.get("op_ids") or []:
                polls_by_op.setdefault(pid, []).append(ev)
        elif kind == "result" and ev.get("http") == 200 and isinstance(oid, str):
            results_by_op.setdefault(oid, []).append(ev)
        elif kind == "lost" and isinstance(oid, str):
            terminal_err_by_op.setdefault(oid, "result_lost")
        elif kind == "expire" and isinstance(oid, str):
            terminal_err_by_op.setdefault(oid, "result_timeout")
        elif kind == "ack_reject" and isinstance(oid, str):
            ack_rejects_by_op[oid] = ack_rejects_by_op.get(oid, 0) + 1

    return {
        "ack_rejects_by_op": ack_rejects_by_op,
        "enq_by_op": enq_by_op,
        "polls_by_op": polls_by_op,
        "results_by_op": results_by_op,
        "terminal_err_by_op": terminal_err_by_op,
    }


def _resolve_op(idx: dict, op_id: str) -> tuple[dict | None, str]:
    res_list = idx["results_by_op"].get(op_id) or []
    if res_list:
        return res_list[0], ""
    err = idx["terminal_err_by_op"].get(op_id)
    if err:
        return None, err
    return None, "result_timeout"


def _find_reconnect_tick_ms(bridge_rows: list[dict], peer: str, cut_start_ms: float) -> float | None:
    cut_end_t = None
    for ev in bridge_rows:
        if ev.get("ev") == "cut_end" and ev.get("peer") == peer and float(ev.get("t_ms", 0.0)) >= cut_start_ms - 1e-6:
            cut_end_t = float(ev["t_ms"])
            break
    if cut_end_t is None:
        return None
    for ev in bridge_rows:
        if (
            ev.get("ev") == "poll"
            and ev.get("http") == 200
            and ev.get("peer") == peer
            and float(ev.get("t_ms", 0.0)) >= cut_end_t
        ):
            return float(ev.get("tick_s", 0.0)) * 1000.0
    return None


def _find_pre_cut_poll(bridge_rows: list[dict], peer: str, cut_start_ms: float) -> dict | None:
    best = None
    for ev in bridge_rows:
        if ev.get("ev") != "poll" or ev.get("http") != 200 or ev.get("peer") != peer:
            continue
        t_ms = float(ev.get("t_ms", 0.0))
        if t_ms > cut_start_ms:
            continue
        if best is None or t_ms > float(best.get("t_ms", 0.0)):
            best = ev
    return best


def _poll_anchor(poll: dict | None) -> tuple[float, float, float] | None:
    """(tick_s, t_ms, held_ms) de un poll 200 valido como ancla de D8/D9, o None (fallo cerrado).

    Exige los tres campos presentes y finitos, tick_s > 0 (el bridge pone 0 si el peer no lo manda o no se parsea)
    y held_ms >= 0 (N1 de Sol r2).
    """
    if poll is None or "tick_s" not in poll or "held_ms" not in poll or "t_ms" not in poll:
        return None
    try:
        tick_s = float(poll["tick_s"])
        t_ms = float(poll["t_ms"])
        held_ms = float(poll["held_ms"])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(tick_s) and math.isfinite(t_ms) and math.isfinite(held_ms)):
        return None
    if tick_s <= 0.0 or held_ms < 0.0:
        return None
    return tick_s, t_ms, held_ms


def _enq_num_arg(idx: dict, op_id, name: str) -> float | None:
    if not isinstance(op_id, str):
        return None
    enq = idx["enq_by_op"].get(op_id) or {}
    args = enq.get("args") or {}
    nk = args.get("nk") or []
    nv = args.get("nv") or []
    for pos, key in enumerate(nk):
        if key == name and pos < len(nv):
            return float(nv[pos])
    return None


def _eval_base_01(scen_rows: list[dict], idx: dict, req_peers: tuple[str, ...], wire_cap: int) -> dict:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-01"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-01", "missing", "no_scenario")
    for peer in req_peers:
        oid = entries[peer].get("op_id")
        if not isinstance(oid, str):
            return _chk("BASE-01", "missing", "bad_op_id")
        res_ev, tech = _resolve_op(idx, oid)
        if res_ev is None:
            return _chk("BASE-01", "missing", tech)
        polls = idx["polls_by_op"].get(oid) or []
        if not polls:
            return _chk("BASE-01", "fail", "missing_poll_event")
        poll_ev = polls[0]
        if int(poll_ev.get("n_ops", 0)) != 1:
            return _chk("BASE-01", "fail", "poll_n_ops_not_1")
        body_len = int(poll_ev.get("body_len", -1))
        if not (wire_cap - 12 <= body_len <= wire_cap):
            return _chk("BASE-01", "fail", f"poll_body_len_out_of_range:{body_len}")
        res_body = res_ev.get("result") or {}
        if res_body.get("status") != "done" or bool(res_body.get("dup", False)):
            return _chk("BASE-01", "fail", "echo_not_done")
        unp = _unpack_result_read(res_body)
        enq_ev = idx["enq_by_op"].get(oid) or {}
        enq_args = enq_ev.get("args") or {}
        exp_sk = len(enq_args.get("sk") or [])
        exp_nk = len(enq_args.get("nk") or [])
        exp_rows = int(enq_args.get("rows") or 0)
        exp_sv_chars = sum(len(str(s)) for s in (enq_args.get("sv") or [])) + sum(
            len(str(s)) for s in (enq_args.get("scell") or [])
        )
        exp_num_sum = sum(float(v) for v in (enq_args.get("nv") or [])) + sum(
            float(v) for v in (enq_args.get("ncell") or [])
        )
        nums = unp["num"]
        if (
            int(nums.get("sk_n", -1)) != exp_sk
            or int(nums.get("nk_n", -1)) != exp_nk
            or int(nums.get("rows_n", -1)) != exp_rows
            or int(nums.get("sv_chars_n", -1)) != exp_sv_chars
            or not math.isclose(float(nums.get("num_sum", 1e99)), exp_num_sum, abs_tol=1e-6)
        ):
            return _chk("BASE-01", "fail", "echo_counts_mismatch")
    return _chk("BASE-01", "pass", "ok")


def _eval_base_02(scen_rows: list[dict], idx: dict, req_peers: tuple[str, ...], wire_cap: int) -> dict:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-02"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-02", "missing", "no_scenario")
    for peer in req_peers:
        ok_id = entries[peer].get("ok_op_id")
        over_id = entries[peer].get("over_op_id")
        if not isinstance(ok_id, str) or not isinstance(over_id, str):
            return _chk("BASE-02", "missing", "bad_op_id")
        ok_ev, tech1 = _resolve_op(idx, ok_id)
        if ok_ev is None:
            return _chk("BASE-02", "missing", tech1)
        over_ev, tech2 = _resolve_op(idx, over_id)
        if over_ev is None:
            return _chk("BASE-02", "missing", tech2)

        ok_len = int(ok_ev.get("body_len", -1))
        ok_body = ok_ev.get("result") or {}
        if ok_body.get("status") != "done" or bool(ok_body.get("dup", False)):
            return _chk("BASE-02", "fail", "at_cap_not_done")
        # D11 (c) (brief v4.5.5, §15): ventana [WIRE_CAP - 50, WIRE_CAP], medida en el bridge (body_len).
        if not (wire_cap - 50 <= ok_len <= wire_cap):
            return _chk("BASE-02", "fail", f"result_body_len_out_of_range:{ok_len}")

        over_body = over_ev.get("result") or {}
        if over_body.get("status") != "error" or over_body.get("reason") != "result_too_large":
            return _chk("BASE-02", "fail", "missing_result_too_large")
    return _chk("BASE-02", "pass", "ok")


def _eval_base_03(scen_rows: list[dict], idx: dict, req_peers: tuple[str, ...]) -> dict:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-03"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-03", "missing", "no_scenario")
    for peer in req_peers:
        row = entries[peer]
        req_keys = ("pre_echo_op_id", "start_op_id", "stop1_op_id", "stop2_op_id", "post_echo_op_id")
        if not all(isinstance(row.get(k), str) for k in req_keys):
            return _chk("BASE-03", "missing", "bad_op_id")
        c_ids = list(row.get("concurrent_op_ids") or [])
        if len(c_ids) < 5:
            return _chk("BASE-03", "fail", "fewer_than_5_concurrent_orders")

        resolved = {}
        for k in req_keys:
            ev, tech = _resolve_op(idx, row[k])
            if ev is None:
                return _chk("BASE-03", "missing", tech)
            resolved[k] = ev

        saw_running_read = False
        for cid in c_ids:
            cev, tech = _resolve_op(idx, cid)
            if cev is None:
                return _chk("BASE-03", "missing", tech)
            cbody = cev.get("result") or {}
            if cbody.get("status") != "done":
                return _chk("BASE-03", "fail", "concurrent_order_not_done")
            cunp = _unpack_result_read(cbody)
            if cunp["str"].get("state") == "running":
                saw_running_read = True
        if not saw_running_read:
            return _chk("BASE-03", "fail", "no_running_job_read")

        pre_unp = _unpack_result_read(resolved["pre_echo_op_id"]["result"])
        stop1_body = resolved["stop1_op_id"]["result"]
        stop2_body = resolved["stop2_op_id"]["result"]
        post_unp = _unpack_result_read(resolved["post_echo_op_id"]["result"])
        if stop1_body.get("status") != "done" or stop2_body.get("status") != "done":
            return _chk("BASE-03", "fail", "stop_not_done")

        s1 = _unpack_result_read(stop1_body)
        s2 = _unpack_result_read(stop2_body)
        if s1["str"].get("state") != "stopped" or s2["str"].get("state") != "stopped":
            return _chk("BASE-03", "fail", f"expected_stopped_got:{s1['str'].get('state')}")
        if int(s1["num"].get("rows_total_n", -1)) != int(s2["num"].get("rows_total_n", -2)):
            return _chk("BASE-03", "fail", "idempotent_stop_rows_changed")

        pre_ends = int(pre_unp["num"].get("ext_end_calls_n", 0))
        post_ends = int(post_unp["num"].get("ext_end_calls_n", 0))
        if (
            int(post_unp["num"].get("ext_init_b", 0)) != 1
            or post_ends - pre_ends != 1
            or post_unp["str"].get("ext_last_end_state") != "stopped"
        ):
            return _chk("BASE-03", "fail", "onjobend_accounting_mismatch")
    return _chk("BASE-03", "pass", "ok")


def _collect_pages_from_ops(idx: dict, page_ids: list[str]) -> tuple[dict | None, list[dict], str]:
    if not page_ids:
        return None, [], "no_pages"
    first_meta = None
    all_rows = []
    for pos, pid in enumerate(page_ids):
        ev, tech = _resolve_op(idx, pid)
        if ev is None:
            return None, [], f"tech:{tech}"
        body = ev.get("result") or {}
        if body.get("status") != "done":
            return None, [], "page_not_done"
        unp = _unpack_result_read(body)
        if pos == 0:
            first_meta = unp
        else:
            assert first_meta is not None
            if unp["str"].get("state") != first_meta["str"].get("state"):
                return None, [], "state_changed"
            if int(unp["num"].get("rows_total_n", -1)) != int(first_meta["num"].get("rows_total_n", -2)):
                return None, [], "rows_total_changed"
        all_rows.extend(unp["rows"])
    return first_meta, all_rows, ""


def _eval_base_04(scen_rows: list[dict], idx: dict, req_peers: tuple[str, ...]) -> tuple[dict, dict]:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-04"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-04", "missing", "no_scenario"), {}
    drifts = {}
    for peer in req_peers:
        row = entries[peer]
        echo_id = row.get("post_echo_op_id")
        page_ids = list(row.get("page_op_ids") or [])
        if not isinstance(echo_id, str) or not page_ids:
            return _chk("BASE-04", "missing", "bad_op_id"), drifts
        echo_ev, tech = _resolve_op(idx, echo_id)
        if echo_ev is None:
            return _chk("BASE-04", "missing", tech), drifts
        echo_unp = _unpack_result_read(echo_ev["result"])

        meta, rows, perr = _collect_pages_from_ops(idx, page_ids)
        if perr.startswith("tech:"):
            return _chk("BASE-04", "missing", perr.split(":", 1)[1]), drifts
        if meta is None or perr:
            return _chk("BASE-04", "fail", perr or "bad_pages"), drifts

        if meta["str"].get("state") != "done" or echo_unp["str"].get("ext_last_end_state") != "done":
            return _chk("BASE-04", "fail", "not_done"), drifts
        if not rows:
            return _chk("BASE-04", "fail", "empty_rows"), drifts
        dtsum_end = float(rows[-1].get("dtsum_ms", 0.0))
        if dtsum_end < 10000.0:
            return _chk("BASE-04", "fail", f"dtsum_below_10000:{dtsum_end}"), drifts
        t_start = float(meta["num"].get("start_tick_ms", 0.0))
        t_end = float(meta["num"].get("end_tick_ms", 0.0))
        drift = abs((t_end - t_start) - dtsum_end) / dtsum_end
        drifts[f"drift_{peer}"] = drift
        if drift > 0.05:
            return _chk("BASE-04", "fail", f"drift_exceeded:{drift:.6f}"), drifts
    return _chk("BASE-04", "pass", "ok"), drifts


def _eval_base_05(scen_rows: list[dict], idx: dict, req_peers: tuple[str, ...]) -> dict:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-05"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-05", "missing", "no_scenario")
    for peer in req_peers:
        page_ids = list(entries[peer].get("page_op_ids") or [])
        meta, rows, perr = _collect_pages_from_ops(idx, page_ids)
        if perr.startswith("tech:"):
            return _chk("BASE-05", "missing", perr.split(":", 1)[1])
        if meta is None or perr:
            return _chk("BASE-05", "fail", perr or "bad_pages")
        rows_total = int(meta["num"].get("rows_total_n", 0))
        pages_n = int(meta["num"].get("pages_n", 0))
        if meta["str"].get("state") != "done" or rows_total < 80 or pages_n < 4 or len(page_ids) != pages_n:
            return _chk("BASE-05", "fail", "insufficient_pages_or_state")
        if len(rows) != rows_total:
            return _chk("BASE-05", "fail", "row_count_mismatch")
        seqs = [int(r.get("seq_n", -1)) for r in rows]
        if seqs != list(range(rows_total)):
            return _chk("BASE-05", "fail", "seq_gap_or_duplicate")
    return _chk("BASE-05", "pass", "ok")


def _eval_base_06(scen_rows: list[dict], idx: dict, req_peers: tuple[str, ...]) -> dict:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-06"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-06", "missing", "no_scenario")
    for peer in req_peers:
        row = entries[peer]
        f_id = row.get("first_op_id")
        s_id = row.get("second_op_id")
        p_ids = list(row.get("first_page_op_ids") or [])
        if not isinstance(f_id, str) or not isinstance(s_id, str) or not p_ids:
            return _chk("BASE-06", "missing", "bad_op_id")
        fev, tech1 = _resolve_op(idx, f_id)
        if fev is None:
            return _chk("BASE-06", "missing", tech1)
        sev, tech2 = _resolve_op(idx, s_id)
        if sev is None:
            return _chk("BASE-06", "missing", tech2)
        if (fev["result"] or {}).get("status") != "done":
            return _chk("BASE-06", "fail", "first_start_failed")
        sbody = sev["result"] or {}
        if sbody.get("status") != "rejected" or sbody.get("reason") != "busy":
            return _chk("BASE-06", "fail", "second_not_rejected_busy")
        meta, _rows, perr = _collect_pages_from_ops(idx, p_ids)
        if perr.startswith("tech:"):
            return _chk("BASE-06", "missing", perr.split(":", 1)[1])
        if meta is None or perr or meta["str"].get("state") != "done":
            return _chk("BASE-06", "fail", "first_did_not_finish_done")
    return _chk("BASE-06", "pass", "ok")


def _eval_base_07(scen_rows: list[dict], idx: dict) -> dict:
    matches = [r for r in scen_rows if r.get("check") == "BASE-07"]
    if not matches:
        return _chk("BASE-07", "missing", "no_scenario")
    row = matches[-1]
    for k in ("pre_echo_op_id", "ping_op_id", "post_echo_op_id"):
        if not isinstance(row.get(k), str):
            return _chk("BASE-07", "missing", "bad_op_id")
    pre_ev, t1 = _resolve_op(idx, row["pre_echo_op_id"])
    ping_ev, t2 = _resolve_op(idx, row["ping_op_id"])
    post_ev, t3 = _resolve_op(idx, row["post_echo_op_id"])
    for ev, t in ((pre_ev, t1), (ping_ev, t2), (post_ev, t3)):
        if ev is None:
            return _chk("BASE-07", "missing", t)
    pbody = ping_ev["result"] or {}
    if pbody.get("status") != "done":
        return _chk("BASE-07", "fail", "ping_not_done")
    punp = _unpack_result_read(pbody)
    if int(punp["num"].get("sent_token_n", 0)) != 4242:
        return _chk("BASE-07", "fail", "bad_sent_token")

    pre_unp = _unpack_result_read(pre_ev["result"])
    post_unp = _unpack_result_read(post_ev["result"])
    pre_cnt = int(pre_unp["num"].get("rpc_ping_count_n", 0))
    post_cnt = int(post_unp["num"].get("rpc_ping_count_n", 0))
    last_tok = int(post_unp["num"].get("rpc_last_token_n", 0))
    if post_cnt < 1 or post_cnt <= pre_cnt or last_tok != 4242:
        return _chk("BASE-07", "fail", "client_echo_missing_ping")

    ping_page_ids = list(row.get("ping_page_op_ids") or [])
    if ping_page_ids:
        seen_4242 = False
        for pid in ping_page_ids:
            pev, tp = _resolve_op(idx, pid)
            if pev is None:
                return _chk("BASE-07", "missing", tp)
            if (pev["result"] or {}).get("status") == "done":
                for pr in _unpack_result_read(pev["result"])["rows"]:
                    if int(pr.get("token_n", 0)) == 4242:
                        seen_4242 = True
        if not seen_4242:
            return _chk("BASE-07", "fail", "ping_page_missing_4242")
    return _chk("BASE-07", "pass", "ok")


def _eval_base_08(scen_rows: list[dict], bridge_rows: list[dict], idx: dict, req_peers: tuple[str, ...]) -> dict:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-08"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-08", "missing", "no_scenario")
    for peer in req_peers:
        row = entries[peer]
        a_ids = list(row.get("a_read_op_ids") or [])
        echo_id = row.get("echo_op_id")
        w_id = row.get("witness_read_op_id")
        cut_start_ms = float(row.get("cut_start_ms", 0.0))
        if not a_ids or not isinstance(echo_id, str) or not isinstance(w_id, str):
            return _chk("BASE-08", "missing", "bad_op_id")

        reconnect_tick_ms = _find_reconnect_tick_ms(bridge_rows, peer, cut_start_ms)
        if reconnect_tick_ms is None:
            return _chk("BASE-08", "missing", "no_reconnect_poll")

        meta_a, rows_a, perr = _collect_pages_from_ops(idx, a_ids)
        if perr.startswith("tech:"):
            return _chk("BASE-08", "missing", perr.split(":", 1)[1])
        if meta_a is None or perr:
            return _chk("BASE-08", "fail", perr or "bad_job_a_pages")

        # D8 (con D9, brief v4.5.3): anclar el corte al reloj del peer con el ultimo poll 200 previo al corte (cota baja).
        # El bridge retiene el poll hasta hold_ms: tick_s es de cuando el peer lo envio y t_ms de la respuesta, asi que
        # la llegada al bridge es t_ms - held_ms. Sin tick_s o sin held_ms no hay ancla: missing (fallo cerrado).
        # N1 de Sol r2: un tick_s no positivo o no finito (el bridge convierte un parseo invalido en 0) tampoco es ancla.
        pre_poll = _find_pre_cut_poll(bridge_rows, peer, cut_start_ms)
        anchor = _poll_anchor(pre_poll)
        if anchor is None:
            return _chk("BASE-08", "missing", "no_pre_cut_poll")
        tick_s, poll_t_ms, held_ms = anchor
        poll_recv_ms = poll_t_ms - held_ms
        cut_start_peer = tick_s * 1000.0 + (cut_start_ms - poll_recv_ms)

        start_t = float(meta_a["num"].get("start_tick_ms", 0.0))
        end_t = float(meta_a["num"].get("end_tick_ms", 0.0))
        if not (end_t > cut_start_peer + CUT_MARGIN_MS):
            # D8 (brief v4.5.3, §11): caduco por su propio timeout si reason == job_timeout y
            # end - start >= max_duration_ms (un frame tardio no lo convierte en prematuro); si no, prematuro.
            max_duration_ms = _enq_num_arg(idx, row.get("start_op_id"), "max_duration_ms")
            if (
                meta_a["str"].get("reason") == "job_timeout"
                and max_duration_ms is not None
                and (end_t - start_t) >= max_duration_ms
            ):
                return _chk("BASE-08", "missing", "witness_window_missed")
            return _chk("BASE-08", "fail", "job_a_ended_before_cut")
        if not any(cut_start_peer + CUT_MARGIN_MS < float(r.get("tick_ms", 0.0)) <= end_t for r in rows_a):
            return _chk("BASE-08", "fail", "no_progress_in_cut")

        echo_ev, t_echo = _resolve_op(idx, echo_id)
        if echo_ev is None:
            return _chk("BASE-08", "missing", t_echo)
        w_ev, t_w = _resolve_op(idx, w_id)
        if w_ev is None:
            return _chk("BASE-08", "missing", t_w)

        if meta_a["str"].get("state") != "expired" or meta_a["str"].get("reason") != "job_timeout":
            return _chk("BASE-08", "fail", f"job_a_state:{meta_a['str'].get('state')}")
        rows_total = int(meta_a["num"].get("rows_total_n", 0))
        if rows_total < 10 or len(rows_a) < 10:
            return _chk("BASE-08", "fail", f"job_a_too_few_rows:{rows_total}")
        dts = [float(r.get("dtsum_ms", 0.0)) for r in rows_a]
        if any(dts[i + 1] < dts[i] for i in range(len(dts) - 1)) or dts[-1] <= dts[0]:
            return _chk("BASE-08", "fail", "dtsum_not_growing")

        start_t = float(meta_a["num"].get("start_tick_ms", 0.0))
        end_t = float(meta_a["num"].get("end_tick_ms", 0.0))
        oje_t = float(meta_a["num"].get("onjobend_tick_ms", 0.0))
        rel_t = float(meta_a["num"].get("released_tick_ms", 0.0))
        if not (0.0 < end_t - start_t <= 2000.0):
            return _chk("BASE-08", "fail", "job_a_duration_out_of_bounds")
        if not (start_t < end_t <= oje_t <= rel_t < reconnect_tick_ms):
            return _chk("BASE-08", "fail", "cleanup_order_or_after_reconnect")

        echo_unp = _unpack_result_read(echo_ev["result"])
        w_attempts = int(echo_unp["num"].get("witness_attempts_n", 0))
        w_started_echo = float(echo_unp["num"].get("witness_started_tick_ms", 0.0))
        if w_attempts < 5:
            return _chk("BASE-08", "fail", f"witness_attempts_low:{w_attempts}")

        w_body = w_ev["result"] or {}
        if w_body.get("status") != "done":
            return _chk("BASE-08", "fail", "witness_b_not_created")
        w_unp = _unpack_result_read(w_body)
        b_start_t = float(w_unp["num"].get("start_tick_ms", 0.0))
        if b_start_t <= 0.0 or w_started_echo <= 0.0:
            return _chk("BASE-08", "fail", "witness_b_missing_start_tick")
        # §13 A2: unica marca del registro de B anterior a la reconexion (sin exigir segunda lectura).
        if not (rel_t <= b_start_t < reconnect_tick_ms and rel_t <= w_started_echo < reconnect_tick_ms):
            return _chk("BASE-08", "fail", "witness_b_started_after_reconnect")
    return _chk("BASE-08", "pass", "ok")


def _eval_base_09(bridge_rows: list[dict], idx: dict, req_peers: tuple[str, ...]) -> dict:
    verb_by_op: dict[str, str] = {}
    for ev in bridge_rows:
        if ev.get("ev") in ("enq", "deliver") and isinstance(ev.get("op_id"), str) and isinstance(ev.get("verb"), str):
            verb_by_op.setdefault(ev["op_id"], ev["verb"])

    saw_any = False
    for peer in req_peers:
        peer_results = [
            ev
            for ev in bridge_rows
            if ev.get("ev") == "result" and ev.get("http") == 200 and ev.get("peer") == peer
        ]
        sim_cache: list[str] = []

        def _push_cache(cid: str) -> None:
            if cid not in sim_cache:
                sim_cache.append(cid)
            while len(sim_cache) > CACHE_CAP:
                sim_cache.pop(0)

        fill_info = None
        expected_snap = None
        snap_id = None
        snap_pages: dict[int, list[dict]] = {}
        snap_pages_n = None
        snap_total_n = None
        redeliver_last = None
        redeliver_first = None

        for ev in peer_results:
            oid = str(ev.get("op_id") or "")
            res = ev.get("result") or {}
            dup = bool(res.get("dup", False))
            verb = verb_by_op.get(oid, "")

            if fill_info is not None and snap_id is not None:
                if oid == fill_info["last_id"] and redeliver_last is None:
                    redeliver_last = res
                    if not dup:
                        _push_cache(oid)
                    continue
                if oid == fill_info["first_id"] and redeliver_first is None:
                    redeliver_first = res
                    if not dup:
                        _push_cache(oid)
                    continue

            if dup:
                continue

            if verb == "qa_cache_fill" and res.get("status") == "done":
                saw_any = True
                unp = _unpack_result_read(res)
                first_id = str(unp["str"].get("first_id") or "")
                last_id = str(unp["str"].get("last_id") or "")
                ins_n = int(unp["num"].get("inserted_n", 0))
                if "-" not in first_id or ins_n < CACHE_CAP + 1:
                    return _chk("BASE-09", "fail", "bad_cache_fill_metadata")
                prefix, first_idx_s = first_id.rsplit("-", 1)
                if first_idx_s != "0" or last_id != f"{prefix}-{ins_n - 1}":
                    return _chk("BASE-09", "fail", "inconsistent_fill_bounds")
                for i in range(ins_n):
                    _push_cache(f"{prefix}-{i}")
                _push_cache(oid)
                fill_info = {"first_id": first_id, "inserted_n": ins_n, "last_id": last_id}
                continue

            if verb == "qa_cache_snapshot" and res.get("status") == "done" and fill_info is not None and snap_id is None:
                unp = _unpack_result_read(res)
                snap_id = str(unp["str"].get("snap_id") or oid)
                expected_snap = list(sim_cache)
                _push_cache(oid)
                continue

            if verb == "qa_cache_page" and res.get("status") == "done" and snap_id is not None:
                enq_args = (idx["enq_by_op"].get(oid) or {}).get("args") or {}
                req_snap = None
                if "sk" in enq_args and "snap_id" in enq_args["sk"]:
                    req_snap = enq_args["sv"][enq_args["sk"].index("snap_id")]
                if req_snap in (None, snap_id):
                    unp = _unpack_result_read(res)
                    pno = int(unp["num"].get("page_n", -1))
                    snap_pages_n = int(unp["num"].get("pages_n", 0))
                    snap_total_n = int(unp["num"].get("rows_total_n", 0))
                    snap_pages[pno] = list(unp["rows"])
                _push_cache(oid)
                continue

            _push_cache(oid)

        if not saw_any:
            return _chk("BASE-09", "missing", "no_cache_fill")
        if fill_info is None or expected_snap is None or snap_pages_n is None or snap_total_n is None:
            return _chk("BASE-09", "fail", "incomplete_snapshot_sequence")
        if len(expected_snap) != CACHE_CAP or snap_total_n != CACHE_CAP:
            return _chk("BASE-09", "fail", f"snapshot_size:{snap_total_n}")
        if sorted(snap_pages.keys()) != list(range(snap_pages_n)):
            return _chk("BASE-09", "fail", "missing_snapshot_pages")

        observed_rows = []
        for pno in range(snap_pages_n):
            observed_rows.extend(snap_pages[pno])
        if len(observed_rows) != CACHE_CAP:
            return _chk("BASE-09", "fail", "snapshot_row_count_mismatch")
        obs_idxs = [int(r.get("idx_n", -1)) for r in observed_rows]
        if obs_idxs != list(range(CACHE_CAP)):
            return _chk("BASE-09", "fail", "snapshot_idx_out_of_order")
        obs_ids = [str(r.get("op_id") or "") for r in observed_rows]
        if obs_ids != expected_snap:
            return _chk("BASE-09", "fail", "snapshot_suffix_or_order_mismatch")

        if redeliver_last is None or redeliver_first is None:
            return _chk("BASE-09", "fail", "missing_redeliveries")
        if not bool(redeliver_last.get("dup", False)):
            return _chk("BASE-09", "fail", "last_id_not_dup")
        last_unp = _unpack_result_read(redeliver_last)
        if "sk_n" in last_unp["num"]:
            return _chk("BASE-09", "fail", "last_id_reexecuted")
        if bool(redeliver_first.get("dup", False)) or redeliver_first.get("status") != "done":
            return _chk("BASE-09", "fail", "evicted_first_id_did_not_execute")

    return _chk("BASE-09", "pass", "ok")


def _eval_base_10(scen_rows: list[dict], idx: dict) -> dict:
    matches = [r for r in scen_rows if r.get("check") == "BASE-10"]
    if not matches:
        return _chk("BASE-10", "missing", "no_scenario")
    row = matches[-1]
    burst_id = row.get("burst_op_id")
    seq0 = int(row.get("seq0", 1000))
    count = int(row.get("count", 520))
    page_ids = list(row.get("page_op_ids") or [])
    if not isinstance(burst_id, str) or not page_ids:
        return _chk("BASE-10", "missing", "bad_op_id")
    bev, tech = _resolve_op(idx, burst_id)
    if bev is None:
        return _chk("BASE-10", "missing", tech)
    if (bev["result"] or {}).get("status") != "done":
        return _chk("BASE-10", "fail", "burst_not_done")

    all_rows = []
    pages_n_ref = None
    total_ref = None
    for pos, pid in enumerate(page_ids):
        pev, tp = _resolve_op(idx, pid)
        if pev is None:
            return _chk("BASE-10", "missing", tp)
        pbody = pev["result"] or {}
        if pbody.get("status") != "done":
            return _chk("BASE-10", "fail", "rpclog_page_not_done")
        unp = _unpack_result_read(pbody)
        if pos == 0:
            pages_n_ref = int(unp["num"].get("pages_n", 0))
            total_ref = int(unp["num"].get("rows_total_n", 0))
        all_rows.extend(unp["rows"])

    if total_ref != RPCLOG_CAP or len(page_ids) != pages_n_ref or len(all_rows) != RPCLOG_CAP:
        return _chk("BASE-10", "fail", f"rpclog_size:{len(all_rows)}")
    if [int(r.get("idx_n", -1)) for r in all_rows] != list(range(RPCLOG_CAP)):
        return _chk("BASE-10", "fail", "rpclog_idx_mismatch")
    if any(r.get("decision") != "accepted" for r in all_rows):
        return _chk("BASE-10", "fail", "rpclog_decision_not_accepted")
    expected_seqs = list(range(seq0 + (count - RPCLOG_CAP), seq0 + count))
    if [int(r.get("seq_n", -1)) for r in all_rows] != expected_seqs:
        return _chk("BASE-10", "fail", "rpclog_fifo_order_mismatch")
    return _chk("BASE-10", "pass", "ok")


def _eval_base_11(scen_rows: list[dict], bridge_rows: list[dict], idx: dict, lease_ms: float) -> dict:
    matches = [r for r in scen_rows if r.get("check") == "BASE-11"]
    if not matches:
        return _chk("BASE-11", "missing", "no_scenario")
    row = matches[-1]
    eff_ids = list(row.get("eff_read_op_ids") or [])
    echo_id = row.get("echo_op_id")
    w_id = row.get("witness_read_op_id")
    ping_ids = list(row.get("ping_page_op_ids") or [])
    token0_n = int(row.get("token0_n", 1000))
    cut_start_ms = float(row.get("cut_start_ms", 0.0))
    if not eff_ids or not isinstance(echo_id, str) or not isinstance(w_id, str) or not ping_ids:
        return _chk("BASE-11", "missing", "bad_op_id")

    reconnect_tick_ms = _find_reconnect_tick_ms(bridge_rows, "server", cut_start_ms)
    if reconnect_tick_ms is None:
        return _chk("BASE-11", "missing", "no_reconnect_poll")

    meta_eff, eff_rows, perr = _collect_pages_from_ops(idx, eff_ids)
    if perr.startswith("tech:"):
        return _chk("BASE-11", "missing", perr.split(":", 1)[1])
    if meta_eff is None or perr:
        return _chk("BASE-11", "fail", perr or "bad_effect_pages")

    echo_ev, t_echo = _resolve_op(idx, echo_id)
    if echo_ev is None:
        return _chk("BASE-11", "missing", t_echo)
    w_ev, t_w = _resolve_op(idx, w_id)
    if w_ev is None:
        return _chk("BASE-11", "missing", t_w)

    ping_rows = []
    for pid in ping_ids:
        pev, tp = _resolve_op(idx, pid)
        if pev is None:
            return _chk("BASE-11", "missing", tp)
        if (pev["result"] or {}).get("status") == "done":
            ping_rows.extend(_unpack_result_read(pev["result"])["rows"])

    if meta_eff["str"].get("state") != "failed" or meta_eff["str"].get("reason") != "lease_expired":
        return _chk("BASE-11", "fail", f"expected_failed_lease_expired_got:{meta_eff['str'].get('state')}")

    sent_tokens = []
    blocked_tokens = []
    saw_blocked = False
    for er in eff_rows:
        outcome = er.get("outcome")
        age = float(er.get("lease_age_ms", 0.0))
        tok = int(er.get("token_n", 0))
        if outcome == "sent":
            if saw_blocked or age > lease_ms:
                return _chk("BASE-11", "fail", "sent_after_lease_or_block")
            sent_tokens.append(tok)
        elif outcome == "blocked_lease":
            if age <= lease_ms:
                return _chk("BASE-11", "fail", "blocked_with_valid_lease")
            saw_blocked = True
            blocked_tokens.append(tok)

    if not sent_tokens or not blocked_tokens:
        return _chk("BASE-11", "fail", "missing_sent_or_blocked_row")

    start_t = float(meta_eff["num"].get("start_tick_ms", 0.0))
    end_t = float(meta_eff["num"].get("end_tick_ms", 0.0))
    oje_t = float(meta_eff["num"].get("onjobend_tick_ms", 0.0))
    rel_t = float(meta_eff["num"].get("released_tick_ms", 0.0))
    if not (start_t < end_t <= oje_t <= rel_t < reconnect_tick_ms):
        return _chk("BASE-11", "fail", "cleanup_not_before_reconnect")

    # Recepcion efectiva en cliente (W4)
    recv_tokens = {int(pr.get("token_n", 0)) for pr in ping_rows if int(pr.get("token_n", 0)) >= token0_n}
    first_blocked_tok = min(blocked_tokens)
    for stok in sent_tokens:
        if stok >= token0_n and stok not in recv_tokens:
            return _chk("BASE-11", "fail", f"missing_ping_on_client:{stok}")
    if any(rtok >= first_blocked_tok for rtok in recv_tokens):
        return _chk("BASE-11", "fail", "ping_received_at_or_after_block")

    # Liberacion observada del recurso qa_effect (W4)
    echo_unp = _unpack_result_read(echo_ev["result"])
    w_started_echo = float(echo_unp["num"].get("witness_started_tick_ms", 0.0))
    w_body = w_ev["result"] or {}
    if w_body.get("status") != "done":
        return _chk("BASE-11", "fail", "effect_witness_not_started")
    w_unp = _unpack_result_read(w_body)
    b_start_t = float(w_unp["num"].get("start_tick_ms", 0.0))
    if b_start_t <= 0.0 or not (rel_t <= b_start_t < reconnect_tick_ms and rel_t <= w_started_echo < reconnect_tick_ms):
        return _chk("BASE-11", "fail", "effect_witness_not_before_reconnect")

    return _chk("BASE-11", "pass", "ok")


def _eval_base_12(
    scen_rows: list[dict],
    bridge_rows: list[dict],
    probe_logs: list[dict],
    idx: dict,
    req_peers: tuple[str, ...],
) -> dict:
    # Sol r5 N1: si el arnes no pudo identificar sin ambiguedad el script log de la sesion en curso de algun peer (mas de
    # un script_<fecha>.log en el perfil), no se sabe si hubo agotamiento ni de cuando: missing, nunca PASS.
    if any(r.get("tag") == "log_ambiguous" for r in probe_logs):
        return _chk("BASE-12", "missing", "probe_logs_ambiguous")
    budget_logs = [r for r in probe_logs if r.get("tag") == "callback_budget_exhausted"]
    scen_12 = [r for r in scen_rows if r.get("check") == "BASE-12"]

    if budget_logs or any("exhausted_ms" in r or "quiet_start_ms" in r for r in scen_12):
        # H6 de Sol (r1-r3) con D12 (brief v4.5.x, §15), en el reloj del arnes y por peer: el agotamiento se hizo visible
        # en (neg_ms, exhausted_ms]. Una peticion despues de exhausted_ms es FALLA segura; una dentro de ese intervalo
        # tiene orden incierto y da missing (nunca PASS). Sin los dos instantes por peer no se acredita: missing.
        q_rows = [
            r
            for r in scen_12
            if isinstance(r.get("exhausted_ms"), dict) and isinstance(r.get("neg_ms"), dict) and "quiet_end_ms" in r
        ]
        if not q_rows:
            return _chk("BASE-12", "missing", "callback_budget_exhausted")
        q = q_rows[-1]
        q_end = float(q["quiet_end_ms"])
        exhausted = q["exhausted_ms"]
        negs = q["neg_ms"]
        uncertain_n = 0
        for peer in req_peers:
            if peer not in exhausted or peer not in negs:
                return _chk("BASE-12", "missing", f"no_exhaustion_instant_for_{peer}")
            q_obs = float(exhausted[peer])
            q_neg = float(negs[peer])
            if not (math.isfinite(q_obs) and math.isfinite(q_neg) and math.isfinite(q_end)) or q_neg > q_obs:
                return _chk("BASE-12", "missing", f"no_exhaustion_instant_for_{peer}")
            if q_end - q_obs < 20000.0:
                return _chk("BASE-12", "fail", "quiet_window_shorter_than_20s")
            p_logs = [r for r in budget_logs if r.get("peer") == peer]
            if len(p_logs) != 1:
                return _chk("BASE-12", "fail", f"expected_single_budget_log_for_{peer}_got_{len(p_logs)}")
            c_n = p_logs[0].get("created_n")
            b_n = p_logs[0].get("budget_n")
            if not isinstance(c_n, int) or not isinstance(b_n, int) or b_n <= 0 or c_n < b_n:
                return _chk("BASE-12", "fail", "created_below_budget")
            p_reqs = [
                float(ev.get("t_ms", -1.0))
                for ev in bridge_rows
                if ev.get("ev") in HTTP_BRIDGE_EVENTS and ev.get("peer") == peer
            ]
            after_n = sum(1 for t in p_reqs if q_obs < t <= q_end)
            if after_n:
                return _chk("BASE-12", "fail", f"requests_after_budget_exhausted:{after_n}")
            uncertain_n += sum(1 for t in p_reqs if q_neg < t <= q_obs)
        # La FALLA segura de cualquier peer manda; solo despues se mira el orden incierto.
        if uncertain_n:
            return _chk("BASE-12", "missing", f"exhaustion_order_uncertain:{uncertain_n}")
        return _chk("BASE-12", "pass", "budget_exhaustion_verified")

    entries = {r.get("peer"): r for r in scen_12 if isinstance(r.get("peer"), str)}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-12", "missing", "no_scenario")
    for peer in req_peers:
        row = entries[peer]
        b_id = row.get("before_op_id")
        a_id = row.get("after_op_id")
        e_ids = list(row.get("echo_op_ids") or [])
        if not isinstance(b_id, str) or not isinstance(a_id, str) or len(e_ids) < 50:
            return _chk("BASE-12", "fail", "fewer_than_50_healthy_orders")
        bev, tb = _resolve_op(idx, b_id)
        if bev is None:
            return _chk("BASE-12", "missing", tb)
        aev, ta = _resolve_op(idx, a_id)
        if aev is None:
            return _chk("BASE-12", "missing", ta)
        for eid in e_ids:
            eev, te = _resolve_op(idx, eid)
            if eev is None:
                return _chk("BASE-12", "missing", te)
            if (eev["result"] or {}).get("status") != "done":
                return _chk("BASE-12", "fail", "healthy_echo_not_done")
        b_unp = _unpack_result_read(bev["result"])
        a_unp = _unpack_result_read(aev["result"])
        created_before = int(b_unp["num"].get("callbacks_created_n", -1))
        created_after = int(a_unp["num"].get("callbacks_created_n", -2))
        pooled_before = int(b_unp["num"].get("callbacks_pooled_n", -1))
        pooled_after = int(a_unp["num"].get("callbacks_pooled_n", -1))
        budget_n = int(a_unp["num"].get("callback_budget_n", 0))
        if budget_n != 2000:
            return _chk("BASE-12", "fail", f"unexpected_budget:{budget_n}")
        # callbacks_created_n cuenta toda la vida del proceso (§11 D5): tras S-puente con cortes ya trae historia.
        # Lo que acredita la reutilizacion es el crecimiento CERO durante las 50 ordenes sanas, con el pool dentro de
        # su tope; acotar el contador absoluto suspendia una mision sana (H2 de Sol r1).
        if created_after != created_before:
            return _chk("BASE-12", "fail", f"callbacks_grew:{created_before}->{created_after}")
        # D7: el pool dentro de su tope en CADA muestra, la inicial y la final (N4 de Sol r2).
        for pooled in (pooled_before, pooled_after):
            if not (0 <= pooled <= CALLBACK_POOL_MAX):
                return _chk("BASE-12", "fail", f"pool_out_of_bounds:{pooled}")
    return _chk("BASE-12", "pass", "ok")


def _eval_base_13(scen_rows: list[dict], bridge_rows: list[dict], idx: dict, req_peers: tuple[str, ...]) -> dict:
    entries = {r.get("peer"): r for r in scen_rows if r.get("check") == "BASE-13"}
    if not all(p in entries for p in req_peers):
        return _chk("BASE-13", "missing", "no_scenario")
    for peer in req_peers:
        row = entries[peer]
        cut_ms = float(row.get("hello_cut_start_ms", 0.0))
        ack_id = row.get("ack_op_id")
        if not isinstance(ack_id, str):
            return _chk("BASE-13", "missing", "bad_op_id")

        bad_hello_idx = None
        good_hello_idx = None
        for pos, ev in enumerate(bridge_rows):
            if float(ev.get("t_ms", 0.0)) < cut_ms - 1e-6 or ev.get("peer") != peer:
                continue
            if ev.get("ev") == "hello" and ev.get("http") == 200 and ev.get("ok") is False and bad_hello_idx is None:
                bad_hello_idx = pos
            elif (
                ev.get("ev") == "hello"
                and ev.get("http") == 200
                and ev.get("ok") is True
                and bad_hello_idx is not None
                and good_hello_idx is None
            ):
                good_hello_idx = pos
                break

        if bad_hello_idx is None or good_hello_idx is None:
            return _chk("BASE-13", "fail", "missing_hello_ok_false_or_retry")

        for mid_ev in bridge_rows[bad_hello_idx + 1 : good_hello_idx]:
            if mid_ev.get("peer") != peer:
                continue
            if mid_ev.get("ev") in ("poll", "keepalive"):
                return _chk("BASE-13", "fail", "poll_sent_after_hello_ok_false")
            if mid_ev.get("ev") == "inst_reject" and mid_ev.get("reason") == "hello_required":
                return _chk("BASE-13", "fail", "poll_attempted_after_hello_ok_false")

        if idx["ack_rejects_by_op"].get(ack_id, 0) < 1:
            return _chk("BASE-13", "fail", "ack_ok_false_not_observed")
        ack_ev, tack = _resolve_op(idx, ack_id)
        if ack_ev is None:
            return _chk("BASE-13", "fail", f"ack_not_retried:{tack}")
        if (ack_ev["result"] or {}).get("status") != "done":
            return _chk("BASE-13", "fail", "ack_retry_not_done")
    return _chk("BASE-13", "pass", "ok")


def evaluate(part_dir, *, repo_root: Path | None = None) -> dict:
    pdir = Path(part_dir)
    raw_manifest = gate_core.read_json(pdir / "manifest.json")
    manifest = {
        "both": bool(raw_manifest.get("both", True)),
        "build": raw_manifest.get("build"),
        "id": raw_manifest.get("id", SPIKE_ID),
        "identity": raw_manifest.get("identity"),
        "kind": raw_manifest.get("kind", "spike"),
        "params": raw_manifest.get("params") if isinstance(raw_manifest.get("params"), dict) else {},
        "schema": raw_manifest.get("schema"),
    }
    spike_id = str(manifest["id"] or SPIKE_ID)
    build = manifest["build"]
    req_peers = ("server", "client") if manifest["both"] else ("server",)

    samples_dir = pdir / "samples"
    bridge_rows = f03_common.read_jsonl(samples_dir / "bridge.jsonl")
    scen_rows = f03_common.read_jsonl(samples_dir / "scenario.jsonl")
    probe_logs = f03_common.read_jsonl(samples_dir / "probe_log.jsonl")

    def _early_inconclusive(reason: str) -> dict:
        checks = [_chk(cid, "missing", reason) for cid in CHECK_IDS]
        return gate_core.make_verdict(spike_id, 2, checks=checks, metrics={}, reasons=[reason])

    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        return _early_inconclusive("params_unverified")

    if build in ("retail", "diag") and identity.get("git_dirty") is not False:
        return _early_inconclusive("git_dirty")

    peer_builds = identity.get("peer_builds")
    if not isinstance(peer_builds, dict) or any(peer_builds.get(r) != build for r in req_peers):
        return _early_inconclusive("build_mismatch")

    good_hellos = [
        ev
        for ev in bridge_rows
        if ev.get("ev") == "hello" and ev.get("http") == 200 and ev.get("ok") is not False
    ]
    for role in req_peers:
        if not any(ev.get("peer") == role for ev in good_hellos):
            return _early_inconclusive("build_mismatch")
    for ev in good_hellos:
        args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
        proto = args.get("proto") if "proto" in args else ev.get("proto")
        h_build = args.get("build") if "build" in args else ev.get("build")
        if proto != "qa0" or h_build != build:
            return _early_inconclusive("build_mismatch")

    git_head = identity.get("git_head")
    try:
        expected_stamp = f03_common.compute_probe_stamp_at_commit(git_head or "", repo_root=repo_root)
    except f03_common.StampSourceUnavailableError:
        return _early_inconclusive("stamp_source_unavailable")

    expected_pv = f"dsbx-qa1+{expected_stamp}"
    if identity.get("probe_stamp") != expected_stamp:
        return _early_inconclusive("artifact_unverified")
    for ev in good_hellos:
        args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
        pv = args.get("probe_ver") if "probe_ver" in args else ev.get("probe_ver")
        if not isinstance(pv, str) or pv == "dsbx-qa1+unstamped" or pv != expected_pv:
            return _early_inconclusive("artifact_unverified")

    ok_params, param_reason = f03_common.verify_eval_params_at_commit(manifest, repo_root=repo_root)
    if not ok_params:
        return _early_inconclusive(param_reason)

    if any(ev.get("ev") == "wire_cap_exceeded" for ev in bridge_rows):
        return _early_inconclusive("wire_cap_exceeded")

    if any(r.get("ev") == "operator_timeout" for r in scen_rows):
        return _early_inconclusive("operator_timeout")

    id_params = identity["params"]
    wire_cap = int(id_params["wire_cap"])
    lease_ms = float(id_params.get("lease_ms", manifest["params"].get("lease_ms", gate_core.DEFAULT_LEASE_MS)))

    idx = _index_bridge(bridge_rows)
    c01 = _eval_base_01(scen_rows, idx, req_peers, wire_cap)
    c02 = _eval_base_02(scen_rows, idx, req_peers, wire_cap)
    c03 = _eval_base_03(scen_rows, idx, req_peers)
    c04, drift_metrics = _eval_base_04(scen_rows, idx, req_peers)
    c05 = _eval_base_05(scen_rows, idx, req_peers)
    c06 = _eval_base_06(scen_rows, idx, req_peers)
    c07 = _eval_base_07(scen_rows, idx)
    c08 = _eval_base_08(scen_rows, bridge_rows, idx, req_peers)
    c09 = _eval_base_09(bridge_rows, idx, req_peers)
    c10 = _eval_base_10(scen_rows, idx)
    c11 = _eval_base_11(scen_rows, bridge_rows, idx, lease_ms)
    c12 = _eval_base_12(scen_rows, bridge_rows, probe_logs, idx, req_peers)
    c13 = _eval_base_13(scen_rows, bridge_rows, idx, req_peers)

    checks = [c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12, c13]
    metrics = dict(drift_metrics)
    metrics["wire_cap"] = wire_cap

    failed = [c["id"] for c in checks if c["status"] == "fail"]
    if failed:
        return gate_core.make_verdict(spike_id, 1, checks=checks, metrics=metrics, reasons=failed)

    if any(r.get("tag") == "callback_budget_exhausted" for r in probe_logs):
        return gate_core.make_verdict(
            spike_id,
            2,
            checks=checks,
            metrics=metrics,
            reasons=["callback_budget_exhausted"],
        )

    tech_reasons = []
    for c in checks:
        if c["status"] != "pass" and c["detail"] in ("result_lost", "result_timeout", "operator_timeout"):
            if c["detail"] not in tech_reasons:
                tech_reasons.append(c["detail"])
    if tech_reasons:
        return gate_core.make_verdict(spike_id, 2, checks=checks, metrics=metrics, reasons=tech_reasons)

    if any(c["status"] != "pass" for c in checks):
        missing_ids = [c["id"] for c in checks if c["status"] != "pass"]
        return gate_core.make_verdict(spike_id, 2, checks=checks, metrics=metrics, reasons=missing_ids)

    return gate_core.make_verdict(spike_id, 0, checks=checks, metrics=metrics, reasons=[])
