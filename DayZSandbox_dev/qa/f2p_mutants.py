"""Mutantes y negativas contra la fabricación del oráculo F2P.

Cada entrada altera la evidencia buena y tiene que tumbar SU comprobación (`must_fail_checks`), con
`expected_exit_code` 1 FALLA o 2 INCONCLUSO. El evaluador es ciego al nombre del mutante: solo ve la
evidencia alterada.
"""

from __future__ import annotations

import copy
import json
import math
from typing import Any, Callable

import wire


def _unpack(read: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]] | None:
    try:
        u = wire.unpack_payload(read)
        return u["str"], u["num"], u["rows"]
    except Exception:
        return None


def _repack(s: dict[str, Any], n: dict[str, Any], ncol: list[str], scol: list[str],
            rows: list[dict[str, Any]], has: Any) -> dict[str, Any]:
    out = wire.pack_payload(scalars_str=s, scalars_num=n, num_cols=ncol, str_cols=scol,
                            row_dicts=rows)
    if has is not None:
        out["has"] = has
    return out


def _job_events(campaign: dict[str, Any], tag: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    bridge = campaign["samples"]["bridge.jsonl"]
    start = None
    job_id = None
    for ev in bridge:
        if ev.get("ev") == "result" and ev.get("http") == 200:
            read = ev.get("result", {}).get("read")
            u = _unpack(read) if isinstance(read, dict) else None
            if not u:
                continue
            s = u[0]
            if str(s.get("area_tag") or s.get("witness_tag") or "") == tag:
                start = ev
                job_id = str(s.get("job") or "")
                break
    pages = []
    if job_id:
        for ev in bridge:
            if ev.get("ev") == "result" and ev.get("http") == 200:
                read = ev.get("result", {}).get("read")
                u = _unpack(read) if isinstance(read, dict) else None
                if u and str(u[0].get("job") or "") == job_id and "page_n" in u[1]:
                    pages.append(ev)
    return start, pages


def _edit_rows(campaign: dict[str, Any], tag: str, fn: Callable[[list[dict[str, Any]]], None]) -> None:
    _start, pages = _job_events(campaign, tag)
    for ev in pages:
        read = ev["result"]["read"]
        u = _unpack(read)
        if not u:
            continue
        s, n, rows = u
        fn(rows)
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _add_row(campaign: dict[str, Any], tag: str, row: dict[str, Any]) -> None:
    _start, pages = _job_events(campaign, tag)
    if not pages:
        return
    last = pages[-1]
    read = last["result"]["read"]
    u = _unpack(read)
    if not u:
        return
    s, n, rows = u
    rows.append(row)
    last["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))
    for ev in pages:
        rd = ev["result"]["read"]
        uu = _unpack(rd)
        if uu:
            uu[1]["rows_total_n"] = float(uu[1]["rows_total_n"]) + 1.0
            ev["result"]["read"] = _repack(uu[0], uu[1], rd["ncol"], rd["scol"], uu[2], rd.get("has"))


def _remove_row(campaign: dict[str, Any], tag: str, pred: Callable[[dict[str, Any]], bool]) -> None:
    _start, pages = _job_events(campaign, tag)
    removed = 0
    for ev in pages:
        read = ev["result"]["read"]
        u = _unpack(read)
        if not u:
            continue
        s, n, rows = u
        new_rows = [r for r in rows if not pred(r)]
        removed += len(rows) - len(new_rows)
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], new_rows, read.get("has"))
    if removed:
        for ev in pages:
            rd = ev["result"]["read"]
            uu = _unpack(rd)
            if uu:
                uu[1]["rows_total_n"] = float(uu[1]["rows_total_n"]) - float(removed)
                ev["result"]["read"] = _repack(uu[0], uu[1], rd["ncol"], rd["scol"], uu[2], rd.get("has"))


def _find_row(campaign: dict[str, Any], tag: str, pred: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    _start, pages = _job_events(campaign, tag)
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if pred(r):
                return r
    return None


def _mutate_row(campaign: dict[str, Any], tag: str, pred: Callable[[dict[str, Any]], bool],
                change: Callable[[dict[str, Any]], None]) -> None:
    def fn(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            if pred(r):
                change(r)
                break
    _edit_rows(campaign, tag, fn)


def _tap_deliveries(campaign: dict[str, Any], verb: str) -> list[dict[str, Any]]:
    out = []
    for ev in campaign["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and o.get("verb") == verb:
                    out.append(o)
    return out


def _tap_results(campaign: dict[str, Any], op_id: str) -> list[dict[str, Any]]:
    out = []
    for ev in campaign["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result":
            b = ev.get("body") or {}
            if b.get("op_id") == op_id:
                out.append(ev)
    return out


def _drop_second_poll(campaign: dict[str, Any], op_id: str) -> None:
    seen = 0
    keep = []
    for ev in campaign["samples"]["bridge_tap.jsonl"]:
        drop = False
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            ops = (ev.get("body") or {}).get("ops") or []
            if any(isinstance(o, dict) and o.get("op_id") == op_id for o in ops):
                seen += 1
                if seen == 2:
                    drop = True
        if not drop:
            keep.append(ev)
    campaign["samples"]["bridge_tap.jsonl"] = keep


def _add_op_state(campaign: dict[str, Any], op_id: str, state: str = "observado",
                  reason: Any = None) -> None:
    be = campaign["samples"]["backend.jsonl"]
    be.append({"seq": len(be) + 1, "t_ms": 999999.0, "kind": "op.state",
               "data": {"op_id": op_id, "state": state, "origin": "servidor", "reason": reason,
                        "at_ms": 999999.0}})


def _add_result_without_delivery(campaign: dict[str, Any]) -> None:
    tap = campaign["samples"]["bridge_tap.jsonl"]
    t = max(float(ev.get("t_ms") or 0.0) for ev in tap) + 1.0
    tap.append({"t_ms": t, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "query": {"peer": "server", "inst": "x" * 32, "session": "s" * 64, "conn": "1"},
                "body": {"op_id": "ghost-op", "session": "s" * 64, "epoch": "e" * 32,
                         "status": "done", "reason": "", "dup": False, "read": {}}})
    tap.append({"t_ms": t + 1.0, "dir": "resp", "method": "POST", "path": "/result", "http": 200,
                "body": {"ok": True}})


def _set_manifest(campaign: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    node = campaign["manifest"]
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value


def _edit_start_str(campaign: dict[str, Any], tag: str, key: str, value: Any) -> None:
    start, _pages = _job_events(campaign, tag)
    if start is None:
        return
    read = start["result"]["read"]
    u = _unpack(read)
    if not u:
        return
    s, n, rows = u
    s[key] = value
    start["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _edit_page_str(campaign: dict[str, Any], tag: str, key: str, value: Any) -> None:
    _start, pages = _job_events(campaign, tag)
    if not pages:
        return
    ev = pages[0]
    read = ev["result"]["read"]
    u = _unpack(read)
    if not u:
        return
    s, n, rows = u
    s[key] = value
    ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _set_pages_n(campaign: dict[str, Any], tag: str, value: int) -> None:
    _start, pages = _job_events(campaign, tag)
    for ev in pages:
        read = ev["result"]["read"]
        u = _unpack(read)
        if not u:
            continue
        s, n, rows = u
        n["pages_n"] = float(value)
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _set_page_job(campaign: dict[str, Any], tag: str, job_id: str) -> None:
    _start, pages = _job_events(campaign, tag)
    if not pages:
        return
    ev = pages[0]
    args = ev.get("args")
    if isinstance(args, dict):
        ua = _unpack(args)
        if ua:
            s, n, rows = ua
            s["job"] = job_id
            ev["args"] = _repack(s, n, args["ncol"], args["scol"], rows, args.get("has"))
    read = ev["result"]["read"]
    u = _unpack(read)
    if u:
        s, n, rows = u
        s["job"] = job_id
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _remove_page(campaign: dict[str, Any], tag: str, page_n: int) -> None:
    _start, pages = _job_events(campaign, tag)
    target = None
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if u and int(u[1].get("page_n", -1)) == page_n:
            target = ev
            break
    if target is not None:
        campaign["samples"]["bridge.jsonl"] = [
            ev for ev in campaign["samples"]["bridge.jsonl"] if ev is not target
        ]


def _drop_column(campaign: dict[str, Any], tag: str, col: str) -> None:
    _start, pages = _job_events(campaign, tag)
    for ev in pages:
        read = ev["result"]["read"]
        u = _unpack(read)
        if not u:
            continue
        s, n, rows = u
        ncol = [c for c in read["ncol"] if c != col]
        for r in rows:
            r.pop(col, None)
        ev["result"]["read"] = _repack(s, n, ncol, read["scol"], rows, read.get("has"))


def _edit_checkpoint(campaign: dict[str, Any], lid: str, dx_m: float) -> None:
    for ev in campaign["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") != "req" or ev.get("path") != "/result":
            continue
        read = (ev.get("body") or {}).get("read") or {}
        ck = read.get("checkpoint")
        if not isinstance(ck, list):
            continue
        for row in ck:
            if isinstance(row, list) and len(row) >= 7 and str(row[0]) == lid:
                row[2] = float(row[2]) + dx_m * 1000.0


def _obj1_pred(r: dict[str, Any]) -> bool:
    return str(r.get("class_name")) == "Land_Wreck_Ikarus" and \
        abs(float(r.get("pos_x_m", 0.0)) - 6188.0) <= 0.5 and \
        abs(float(r.get("pos_z_m", 0.0)) - 7626.0) <= 0.5


def _eeinit_pred(cls: str, x: float, z: float):
    def p(r: dict[str, Any]) -> bool:
        return int(r.get("sample_idx", -1)) == 0 and str(r.get("class_name")) == cls and \
            abs(float(r.get("pos_x_m", 0.0)) - x) <= 0.5 and \
            abs(float(r.get("pos_z_m", 0.0)) - z) <= 0.5
    return p


def _m_creation_suppressed(c: dict[str, Any]) -> None:
    _remove_row(c, "P2:apply", _eeinit_pred("Land_Wreck_Ikarus", 6188.0, 7626.0))
    _remove_row(c, "P2:post", _obj1_pred)


def _m_entity_moved_witness(c: dict[str, Any]) -> None:
    _mutate_row(c, "P2:apply", _eeinit_pred("Land_Wreck_Ikarus", 6188.0, 7626.0),
                lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.6))


def _m_entity_moved_census(c: dict[str, Any]) -> None:
    _mutate_row(c, "P2:post", _obj1_pred, lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.6))


def _m_creature_born_1m(c: dict[str, Any]) -> None:
    _mutate_row(c, "P2:apply", _eeinit_pred("ZmbM_FarmerFat_Brown", 6242.0, 7610.0),
                lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 1.0))


def _m_creature_jump(c: dict[str, Any]) -> None:
    def pred(r: dict[str, Any]) -> bool:
        return str(r.get("class_name")) == "ZmbM_FarmerFat_Brown" and int(r.get("sample_idx", -1)) == 1
    _mutate_row(c, "P2:apply", pred, lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.4))
    # El checkpoint se mueve con el tick 1: el mod lo declara «en su sitio» y solo el salto lo delata.
    _edit_checkpoint(c, "zmb-01", 0.4)


def _m_creature_dead(c: dict[str, Any]) -> None:
    _mutate_row(c, "P2:post", lambda r: str(r.get("class_name")) == "ZmbM_FarmerFat_Brown",
                lambda r: r.__setitem__("alive_b", 0))


def _m_foreign_to_ground(c: dict[str, Any]) -> None:
    chest = _find_row(c, "P3:post_reset1", lambda r: str(r.get("class_name")) == "SeaChest")
    parent_net = str(chest["net_id"]) if chest else ""
    def pred(r: dict[str, Any]) -> bool:
        return str(r.get("loc_kind")) == "cargo" and str(r.get("class_name")) == "Apple" and             str(r.get("parent_net_id") or "") == parent_net
    def change(r: dict[str, Any]) -> None:
        r["loc_kind"] = "ground"
        r["parent_net_id"] = ""
    _mutate_row(c, "P3:post_reset1", pred, change)


def _m_foreign_container_deleted(c: dict[str, Any]) -> None:
    _remove_row(c, "P3:post_reset1", lambda r: str(r.get("class_name")) == "SeaChest")


def _m_scene2_deleted(c: dict[str, Any]) -> None:
    _remove_row(c, "P3:post_reset1", lambda r: str(r.get("class_name")) == "Barrel_Red")


def _m_scene2_ground_deleted(c: dict[str, Any]) -> None:
    _remove_row(c, "P3:post_reset1", lambda r: str(r.get("class_name")) == "MediumTent")


def _m_duplicate(c: dict[str, Any]) -> None:
    row = _find_row(c, "P2:post", _obj1_pred)
    if row is not None:
        clone = dict(row)
        clone["net_id"] = "1:999"
        _add_row(c, "P2:post", clone)


def _m_reappears(c: dict[str, Any]) -> None:
    row = _find_row(c, "P2:post", _obj1_pred)
    if row is not None:
        _add_row(c, "P4b:post_restart", dict(row))


def _m_control_missing(c: dict[str, Any]) -> None:
    _remove_row(c, "P4b:post_restart",
                lambda r: str(r.get("class_name")) == "WoodenCrate" and
                abs(float(r.get("pos_x_m", 0.0)) - 6100.0) <= 0.5)


def _m_extra_scene_object(c: dict[str, Any]) -> None:
    _add_row(c, "P3:apply1", {"class_name": "Barrel_Red", "net_id": "1:998", "parent_net_id": "",
                              "pos_x_m": 6200.0, "pos_y_m": 8.0, "pos_z_m": 7600.0, "yaw_deg": 0.0,
                              "tick_ms": 372100.0, "frame": 11, "ai_agent_b": 0, "sample_idx": 0,
                              "alive_b": 1})


def _m_confirmed_alive(c: dict[str, Any]) -> None:
    row = _find_row(c, "P3:post_reset1", lambda r: str(r.get("class_name")) == "SeaChest")
    if row is None:
        return
    net = str(row["net_id"])
    hi, lo = net.split(":")
    c["samples"]["scene_del.jsonl"].append({
        "t_ms": 382200.0, "frame": 50, "lid": "obj-17", "net_low": int(lo), "net_high": int(hi),
        "signal_ref_b": 0, "signal_pending_b": 0, "signal_by_netid_b": 1,
        "deleted_confirmed_b": 1, "delete_failed_b": 0, "confirm_tick_ms": 382200.0})


def _m_mod_copy_perturbed(c: dict[str, Any]) -> None:
    _edit_rows(c, "P2:post", lambda rows: [r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.1)
                                           for r in rows if str(r.get("class_name")) != "WoodenCrate"])


def _m_single_delivery(c: dict[str, Any]) -> None:
    dels = _tap_deliveries(c, "scene.apply")
    if dels:
        _drop_second_poll(c, str(dels[0]["op_id"]))


def _m_cut_no_effect(c: dict[str, Any]) -> None:
    _remove_row(c, "P5:cut", lambda r: int(r.get("sample_idx", -1)) == 0)


def _m_witness_not_final(c: dict[str, Any]) -> None:
    _edit_rows(c, "P2:apply", lambda rows: [r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.1)
                                            for r in rows if int(r.get("sample_idx", -1)) == 0 and
                                            str(r.get("ai_agent_b", 0)) == "0"])


def _m_creature_no_ai(c: dict[str, Any]) -> None:
    _mutate_row(c, "P2:post", lambda r: str(r.get("class_name")) == "ZmbM_FarmerFat_Brown",
                lambda r: r.__setitem__("ai_agent_b", 0))


def _m_extra_scene_creature(c: dict[str, Any]) -> None:
    _add_row(c, "P3:apply1", {"class_name": "ZmbM_FarmerFat_Brown", "net_id": "1:997", "parent_net_id": "",
                              "pos_x_m": 6210.0, "pos_y_m": 6.0, "pos_z_m": 7650.0, "yaw_deg": 0.0,
                              "tick_ms": 372100.0, "frame": 11, "ai_agent_b": 1, "sample_idx": 0,
                              "alive_b": 1})


def _m_delete_failed_missing(c: dict[str, Any]) -> None:
    row = _find_row(c, "P3:pre_reset", lambda r: str(r.get("class_name")) == "Land_Wreck_Ikarus")
    net = str(row["net_id"]) if row else "1:2"
    hi, lo = net.split(":")
    c["samples"]["scene_del.jsonl"].append({
        "t_ms": 382200.0, "frame": 50, "lid": "obj-01", "net_low": int(lo), "net_high": int(hi),
        "signal_ref_b": 0, "signal_pending_b": 0, "signal_by_netid_b": 1,
        "deleted_confirmed_b": 0, "delete_failed_b": 1, "confirm_tick_ms": 382200.0})


def _m_p5_duplicate(c: dict[str, Any]) -> None:
    row = _find_row(c, "P5:post_apply", lambda r: str(r.get("class_name")) == "Land_Wreck_Ikarus")
    if row is None:
        return
    clone1 = dict(row)
    clone1["net_id"] = "1:900"
    clone2 = dict(row)
    clone2["net_id"] = "1:901"
    _add_row(c, "P5:post_apply", clone1)
    _add_row(c, "P5:post_apply", clone2)


def _n_no_raw_rows(c: dict[str, Any]) -> None:
    keep = []
    for ev in c["samples"]["bridge.jsonl"]:
        drop = False
        if ev.get("ev") == "result":
            read = ev.get("result", {}).get("read")
            if isinstance(read, dict) and "sk" in read and "resource" in read["sk"]:
                drop = True
        if not drop:
            keep.append(ev)
    c["samples"]["bridge.jsonl"] = keep


def _n_net_zero(c: dict[str, Any]) -> None:
    def fn(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            if _obj1_pred(r) or (int(r.get("sample_idx", -1)) == 0 and
                                 str(r.get("class_name")) == "Land_Wreck_Ikarus"):
                r["net_id"] = "0:0"
    _edit_rows(c, "P2:post", fn)
    _edit_rows(c, "P2:apply", fn)


def _n_surface_constant(c: dict[str, Any]) -> None:
    _edit_rows(c, "P1:base", lambda rows: [r.__setitem__("surface_y_m", 4.0) for r in rows])


def _n_op_state_orphan(c: dict[str, Any]) -> None:
    _add_op_state(c, "ghost-op")


def _n_tap_mismatch(c: dict[str, Any]) -> None:
    _add_result_without_delivery(c)


def _n_oracle_commit(c: dict[str, Any]) -> None:
    _set_manifest(c, ("f2p", "oracle_commit"), "f" * 40)


def _n_pbo(c: dict[str, Any]) -> None:
    _set_manifest(c, ("identity", "product_pbo_sha256"), "e" * 64)


def _n_stale_rows(c: dict[str, Any]) -> None:
    _start, pages = _job_events(c, "P2:post")
    for ev in pages:
        ev["t_ms"] = 201500.0


def _n_empty_census(c: dict[str, Any]) -> None:
    _remove_row(c, "P1:base", lambda r: True)


def _n_epoch_mismatch(c: dict[str, Any]) -> None:
    _edit_start_str(c, "P2:post", "server_epoch", "f" * 32)


def _n_page_mismatch(c: dict[str, Any]) -> None:
    _set_pages_n(c, "P2:post", 99)


def _n_job_mismatch(c: dict[str, Any]) -> None:
    _set_page_job(c, "P2:post", "job-999")


def _n_missing_page(c: dict[str, Any]) -> None:
    _remove_page(c, "P2:post", 0)


def _n_probe_stamp_mismatch(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "hello" and isinstance(ev.get("args"), dict):
            ev["args"]["probe_ver"] = "dsbx-qa1+" + "f" * 16


def _n_baseline_missing(c: dict[str, Any]) -> None:
    classes = {"Land_Barn_Metal", "Land_Church_02", "Land_House_1W01", "Land_Shed_Wooden"}
    _remove_row(c, "P1:base", lambda r: str(r.get("class_name")) in classes)


def _n_surface_absent(c: dict[str, Any]) -> None:
    _drop_column(c, "P1:base", "surface_y_m")


MUTANTS: dict[str, dict[str, Any]] = {
    "creation_suppressed": {"apply": _m_creation_suppressed, "expected_exit_code": 1,
                            "must_fail_checks": ["F2P-01"],
                            "allowed_non_pass": {"F2P-02": ["fail"], "F2P-04": ["fail"],
                                                 "F2P-05": ["fail"], "F2P-12": ["missing"]}},
    "entity_moved_0p6_witness": {"apply": _m_entity_moved_witness, "expected_exit_code": 1,
                                 "must_fail_checks": ["F2P-02"],
                                 "allowed_non_pass": {"F2P-12": ["missing"], "F2P-13": ["fail"]}},
    "entity_moved_0p6_census": {"apply": _m_entity_moved_census, "expected_exit_code": 1,
                                "must_fail_checks": ["F2P-02"], "allowed_non_pass": {"F2P-12": ["missing"]}},
    "creature_born_1m": {"apply": _m_creature_born_1m, "expected_exit_code": 1,
                         "must_fail_checks": ["F2P-02"], "allowed_non_pass": {"F2P-13": ["fail"]}},
    "foreign_moved_to_ground": {"apply": _m_foreign_to_ground, "expected_exit_code": 1,
                                "must_fail_checks": ["F2P-05"], "allowed_non_pass": {}},
    "foreign_container_deleted": {"apply": _m_foreign_container_deleted, "expected_exit_code": 1,
                                  "must_fail_checks": ["F2P-05"], "allowed_non_pass": {}},
    "scene2_entity_deleted": {"apply": _m_scene2_deleted, "expected_exit_code": 1,
                              "must_fail_checks": ["F2P-05"], "allowed_non_pass": {}},
    "duplicate_33_plus_k": {"apply": _m_duplicate, "expected_exit_code": 1,
                            "must_fail_checks": ["F2P-04"], "allowed_non_pass": {"F2P-01": ["fail"]}},
    "reappears_after_restart": {"apply": _m_reappears, "expected_exit_code": 1,
                                "must_fail_checks": ["F2P-07"], "allowed_non_pass": {}},
    "persistent_control_missing": {"apply": _m_control_missing, "expected_exit_code": 2,
                                   "must_fail_checks": ["F2P-07"], "allowed_non_pass": {}},
    "creature_jump_before_checkpoint": {"apply": _m_creature_jump, "expected_exit_code": 1,
                                        "must_fail_checks": ["F2P-02"], "allowed_non_pass": {}},
    "creature_dead_or_no_ai": {"apply": _m_creature_dead, "expected_exit_code": 1,
                               "must_fail_checks": ["F2P-02"], "allowed_non_pass": {}},
    "scene2_ground_entity_deleted_by_reset": {"apply": _m_scene2_ground_deleted,
                                              "expected_exit_code": 1,
                                              "must_fail_checks": ["F2P-05"], "allowed_non_pass": {}},
    "extra_scene_class_in_coverage": {"apply": _m_extra_scene_object, "expected_exit_code": 1,
                                      "must_fail_checks": ["F2P-13"], "allowed_non_pass": {}},
    "confirmed_delete_still_alive": {"apply": _m_confirmed_alive, "expected_exit_code": 1,
                                     "must_fail_checks": ["F2P-10"], "allowed_non_pass": {}},
    "mod_readings_copy_perturbed": {"apply": _m_mod_copy_perturbed, "expected_exit_code": 2,
                                    "must_fail_checks": ["F2P-12"],
                                    "allowed_non_pass": {"F2P-02": ["missing"]}},
    "single_delivery_p2": {"apply": _m_single_delivery, "expected_exit_code": 1,
                           "must_fail_checks": ["F2P-04"], "allowed_non_pass": {}},
    "cut_before_first_effect_p5": {"apply": _m_cut_no_effect, "expected_exit_code": 1,
                                   "must_fail_checks": ["F2P-09"], "allowed_non_pass": {}},
    "witness_einit_not_final": {"apply": _m_witness_not_final, "expected_exit_code": 2,
                                "must_fail_checks": ["F2P-12"], "allowed_non_pass": {"F2P-02": ["missing"]}},
    "creature_no_ai": {"apply": _m_creature_no_ai, "expected_exit_code": 1,
                       "must_fail_checks": ["F2P-02"], "allowed_non_pass": {}},
    "extra_scene_creature_in_coverage": {"apply": _m_extra_scene_creature, "expected_exit_code": 1,
                                         "must_fail_checks": ["F2P-13"], "allowed_non_pass": {}},
    "delete_failed_but_missing": {"apply": _m_delete_failed_missing, "expected_exit_code": 1,
                                  "must_fail_checks": ["F2P-10"], "allowed_non_pass": {}},
    "p5_duplicate_33_plus_k": {"apply": _m_p5_duplicate, "expected_exit_code": 1,
                               "must_fail_checks": ["F2P-09"], "allowed_non_pass": {}},
}

# Negativas contra la fabricación: nunca PASA.
NEGATIVES: dict[str, dict[str, Any]] = {
    "rows_without_raw_response": {"apply": _n_no_raw_rows},
    "net_id_zero": {"apply": _n_net_zero},
    "surface_y_constant": {"apply": _n_surface_constant},
    "surface_y_absent": {"apply": _n_surface_absent},
    "op_state_without_event": {"apply": _n_op_state_orphan},
    "tap_trace_mismatch": {"apply": _n_tap_mismatch},
    "oracle_commit_mismatch": {"apply": _n_oracle_commit},
    "pbo_mismatch": {"apply": _n_pbo},
    "stale_rows": {"apply": _n_stale_rows},
    "empty_census": {"apply": _n_empty_census},
    "baseline_missing": {"apply": _n_baseline_missing},
    "epoch_mismatch": {"apply": _n_epoch_mismatch},
    "page_mismatch": {"apply": _n_page_mismatch},
    "job_mismatch": {"apply": _n_job_mismatch},
    "missing_page": {"apply": _n_missing_page},
    "probe_stamp_mismatch": {"apply": _n_probe_stamp_mismatch},
}

# Cobertura explícita de §6 del brief v1.3.1. Cada entrada de la lista de §6 apunta a uno o más
# mutantes/negativas reales de este módulo; las pruebas offline comprueban que no falta ninguno.
SECTION6_MUTANTS: dict[str, list[str]] = {
    "creacion_suprimida": ["creation_suppressed"],
    "entidad_movida_0p6_en_testigo": ["entity_moved_0p6_witness"],
    "entidad_movida_0p6_en_censo": ["entity_moved_0p6_census"],
    "criatura_nace_a_1m": ["creature_born_1m"],
    "ajeno_sacado_al_suelo": ["foreign_moved_to_ground"],
    "contenedor_ajeno_borrado": ["foreign_container_deleted"],
    "objeto_escena2_borrado": ["scene2_entity_deleted"],
    "duplicado_33_mas_k": ["duplicate_33_plus_k", "p5_duplicate_33_plus_k"],
    "algo_reaparece_tras_reinicio": ["reappears_after_restart"],
    "control_persistente_ausente": ["persistent_control_missing"],
    "criatura_desplazada_q01": ["creature_jump_before_checkpoint"],
    "criatura_alive_o_ai_q05": ["creature_dead_or_no_ai", "creature_no_ai"],
    "escena2_suelo_borrada_por_reset": ["scene2_ground_entity_deleted_by_reset"],
    "extra_clase_escena_en_cobertura": ["extra_scene_class_in_coverage", "extra_scene_creature_in_coverage"],
    "borrado_confirmado_sigue_vivo": ["confirmed_delete_still_alive"],
    "copia_lecturas_mod_perturbada": ["mod_readings_copy_perturbed"],
    "una_sola_entrega_p2": ["single_delivery_p2"],
    "corte_antes_primer_efecto_p5": ["cut_before_first_effect_p5"],
    "testigo_einit_no_final": ["witness_einit_not_final"],
}
SECTION6_NEGATIVES: dict[str, list[str]] = {
    "filas_sin_respuesta_cruda": ["rows_without_raw_response"],
    "trabajo_pagina_epoch_sello_no_casan": [
        "job_mismatch", "page_mismatch", "epoch_mismatch", "probe_stamp_mismatch", "missing_page",
    ],
    "frescura_antes_del_efecto": ["stale_rows"],
    "net_id_cero_en_creado": ["net_id_zero"],
    "surface_y_constante_o_ausente": ["surface_y_constant", "surface_y_absent"],
    "op_state_sin_evento": ["op_state_without_event"],
    "traza_no_cuadra_con_respuestas": ["tap_trace_mismatch"],
    "commit_oraculo_o_pbo_no_coinciden": ["oracle_commit_mismatch", "pbo_mismatch"],
    "censo_vacio_o_sin_baseline": ["empty_census", "baseline_missing"],
}

EXPECTED_HARNESS_TESTS: dict[str, Any] = {}


def mutate(campaign: dict[str, Any], name: str) -> dict[str, Any]:
    c = copy.deepcopy(campaign)
    spec = MUTANTS.get(name) or NEGATIVES[name]
    spec["apply"](c)
    return c
