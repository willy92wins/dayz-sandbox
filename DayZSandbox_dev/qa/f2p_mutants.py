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
                    d = dict(o)
                    d["t_ms"] = float(ev.get("t_ms") or 0.0)
                    out.append(d)
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
    # Se mueve en Y: la fila sigue casando por (clase, x, z) con el documento, así que F2P-02 la
    # detecta por la distancia 3D (`witness_far`), no por dejar de existir en el testigo.
    _mutate_row(c, "P2:apply", _eeinit_pred("Land_Wreck_Ikarus", 6188.0, 7626.0),
                lambda r: r.__setitem__("pos_y_m", float(r["pos_y_m"]) + 0.6))


def _m_entity_moved_census(c: dict[str, Any]) -> None:
    _mutate_row(c, "P2:post", _obj1_pred, lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.6))


def _m_creature_born_1m(c: dict[str, Any]) -> None:
    # En Y la criatura sigue casando por (clase, x, z); F2P-02 la tumba por `witness_far`.
    _mutate_row(c, "P2:apply", _eeinit_pred("ZmbM_FarmerFat_Brown", 6242.0, 7610.0),
                lambda r: r.__setitem__("pos_y_m", float(r["pos_y_m"]) + 1.0))


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
    # El duplicado tiene que verse en el testigo de P2 (F2P-04: 33 nacimientos, no 66). Un duplicado
    # solo en el censo queda tapado por el ruido de la CE (§6.1 punto 9).
    row = _find_row(c, "P2:apply", _eeinit_pred("Land_Wreck_Ikarus", 6188.0, 7626.0))
    if row is not None:
        clone = dict(row)
        clone["net_id"] = "1:999"
        _add_row(c, "P2:apply", clone)


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
                              "alive_b": 1, "surface_y_m": 8.0})


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
                              "alive_b": 1, "surface_y_m": 6.0})


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


def _n_oracle_commit_split(c: dict[str, Any]) -> None:
    # H-7: solo `identity.oracle_commit` discrepa del manifest y del evento `oracle.frozen`.
    _set_manifest(c, ("identity", "oracle_commit"), "e" * 40)


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
    # Los edificios de referencia REALES de F2P-11 (medidos en la diag de F0.3), no los inventados.
    classes = {"Land_Lunapark_Shooting_Gallery", "Land_House_2W01",
               "Land_City_Stand_Grocery", "Land_House_2B01"}
    _remove_row(c, "P1:base", lambda r: str(r.get("class_name")) in classes)


def _n_surface_absent(c: dict[str, Any]) -> None:
    _drop_column(c, "P1:base", "surface_y_m")


# ---------------------------------------------------------------------------------------------------
# Casos de Sol r1 (T2d-1, punto 3), traducidos a la fixture nueva.
# ---------------------------------------------------------------------------------------------------

def _add_del_line(c: dict[str, Any], t: float, frame: int, lid: str, net: str) -> None:
    hi, lo = net.split(":")
    c["samples"]["scene_del.jsonl"].append({
        "t_ms": t, "frame": frame, "lid": lid, "net_low": int(lo), "net_high": int(hi),
        "signal_ref_b": 0, "signal_pending_b": 0, "signal_by_netid_b": 1,
        "deleted_confirmed_b": 1, "delete_failed_b": 0, "confirm_tick_ms": t + 33.0})


def _census_columns(c: dict[str, Any]) -> tuple[list[str], list[str]]:
    _start, pages = _job_events(c, "P1:base")
    read = pages[0]["result"]["read"]
    return list(read["ncol"]), list(read["scol"])


def _add_census_disk(c: dict[str, Any], tag: str, epoch: str, inst: str, start_t: float,
                     snap_tick: float, snap_frame: float, center: tuple[float, float],
                     radius: float, rows: list[dict[str, Any]]) -> None:
    """Añade un trabajo de censo nuevo (una lectura independiente), como el resto de la evidencia."""
    ncol, scol = _census_columns(c)
    bridge = c["samples"]["bridge.jsonl"]
    start_oid = f"extra-{tag}-start"
    page_oid = f"extra-{tag}-page"
    page_t = start_t + 20.0
    s = {"area_tag": tag, "server_epoch": epoch, "director_uid": "dir-uid-f2p",
         "job": start_oid, "state": "done"}
    n = {"snap_tick_ms": snap_tick, "snap_frame": snap_frame, "rows_captured_n": float(len(rows)),
         "center_x_m": center[0], "center_z_m": center[1], "radius_m": radius,
         "director_present_b": 1.0, "director_alive_b": 1.0,
         "director_inv_readable_b": 1.0, "director_inv_count_n": 0.0}
    read = wire.pack_payload(scalars_str=s, scalars_num=n)
    bridge.append({"t_ms": start_t, "ev": "enq", "peer": "server", "op_id": start_oid,
                   "verb": "per_census_start", "args": wire.empty_payload(), "inst": inst})
    bridge.append({"t_ms": start_t + 5, "ev": "deliver", "peer": "server", "op_id": start_oid,
                   "verb": "per_census_start", "args": wire.empty_payload(), "inst": inst})
    bridge.append({"t_ms": start_t + 10, "ev": "poll", "peer": "server", "inst": inst,
                   "http": 200, "now_ms": start_t + 10, "op_ids": [start_oid], "n_ops": 1})
    bridge.append({"t_ms": start_t + 20, "ev": "result", "peer": "server", "inst": inst,
                   "http": 200, "op_id": start_oid,
                   "result": {"op_id": start_oid, "status": "done", "reason": "", "read": read}})
    ps = {"job": start_oid, "state": "done", "reason": "", "resource": "per_census",
          "server_epoch": epoch}
    pn = {"page_n": 0.0, "pages_n": 1.0, "rows_total_n": float(len(rows)),
          "snap_tick_ms": snap_tick, "snap_frame": snap_frame, "center_x_m": center[0],
          "center_z_m": center[1], "radius_m": radius}
    pread = wire.pack_payload(scalars_str=ps, scalars_num=pn, num_cols=ncol, str_cols=scol,
                              row_dicts=rows)
    pargs = wire.pack_payload(scalars_str={"job": start_oid}, scalars_num={"page_n": 0.0})
    bridge.append({"t_ms": page_t, "ev": "enq", "peer": "server", "op_id": page_oid,
                   "verb": "job_read", "args": pargs, "inst": inst})
    bridge.append({"t_ms": page_t + 5, "ev": "deliver", "peer": "server", "op_id": page_oid,
                   "verb": "job_read", "args": pargs, "inst": inst})
    bridge.append({"t_ms": page_t + 10, "ev": "poll", "peer": "server", "inst": inst,
                   "http": 200, "now_ms": page_t + 10, "op_ids": [page_oid], "n_ops": 1})
    bridge.append({"t_ms": page_t + 20, "ev": "result", "peer": "server", "inst": inst,
                   "http": 200, "op_id": page_oid,
                   "result": {"op_id": page_oid, "status": "done", "reason": "", "read": pread}})


def _n_sol_census_before_first_P2_apply(c: dict[str, Any]) -> None:
    start, _pages = _job_events(c, "P2:post")
    if start is not None:
        start["t_ms"] = 200100.0


def _n_sol_P2_snapshot_tick_zero(c: dict[str, Any]) -> None:
    start, _pages = _job_events(c, "P2:post")
    if start is None:
        return
    read = start["result"]["read"]
    u = _unpack(read)
    if not u:
        return
    s, n, rows = u
    n["snap_tick_ms"] = 0.0
    start["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _n_sol_P2_pages_other_instance(c: dict[str, Any]) -> None:
    _start, pages = _job_events(c, "P2:post")
    oids = {str(p["result"]["op_id"]) for p in pages}
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id")) in oids:
            ev["inst"] = "9" * 32


def _m_sol_confirmed_alive_hidden(c: dict[str, Any]) -> None:
    _m_confirmed_alive(c)
    # Un censo espurio, sin hello y con epoch ajeno, justo después del borrado. No debe taparlo.
    _add_census_disk(c, "OUTSIDE:spoof", "f" * 32, "9" * 32, 382300.0, 382300.0, 51.0,
                     (6170.0, 7643.0), 115.0, [])


def _m_sol_p2n_uncompensated(c: dict[str, Any]) -> None:
    row = _find_row(c, "P2:post", _obj1_pred)
    if row is not None:
        clone = dict(row)
        clone["net_id"] = "1:990"
        _add_row(c, "P2n:clean", clone)


def _m_sol_creature_missing_original_disk(c: dict[str, Any]) -> None:
    row = _find_row(c, "P3:pre_reset", lambda r: str(r.get("class_name")) == "ZmbM_FarmerFat_Brown")
    if row is not None:
        _add_del_line(c, 382150.0, 55, "zmb-01", str(row["net_id"]))


def _m_sol_session_differ_p2(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result":
            t = float(ev.get("t_ms") or 0.0)
            if 200000.0 <= t < 300000.0 and isinstance(ev.get("body"), dict):
                ev["body"]["session"] = "different"


def _m_sol_p3_reset_without_result(c: dict[str, Any]) -> None:
    dels = [d for d in _tap_deliveries(c, "scene.reset")
            if 370000.0 <= float(d.get("t_ms") or 0.0) < 480000.0]
    if not dels:
        return
    oid = str(dels[0]["op_id"])
    c["samples"]["bridge_tap.jsonl"] = [
        ev for ev in c["samples"]["bridge_tap.jsonl"]
        if not (ev.get("dir") == "req" and ev.get("path") == "/result" and
                str((ev.get("body") or {}).get("op_id")) == oid)]


def _m_sol_reconciliation_without_result(c: dict[str, Any]) -> None:
    ids = set()
    for d in _tap_deliveries(c, "state.read"):
        t = float(d.get("t_ms") or 0.0)
        if 550000.0 <= t < 610000.0 or 760000.0 <= t < 820000.0:
            ids.add(str(d["op_id"]))
    c["samples"]["bridge_tap.jsonl"] = [
        ev for ev in c["samples"]["bridge_tap.jsonl"]
        if not (ev.get("dir") == "req" and ev.get("path") == "/result" and
                str((ev.get("body") or {}).get("op_id")) in ids)]


def _m_sol_witness_radius_window(c: dict[str, Any]) -> None:
    for tag in ("P1:control", "P2:apply", "P2n:apply", "P3:apply1", "P3:apply2",
                "P4a:apply1", "P4b:apply", "P5:cut"):
        start, _pages = _job_events(c, tag)
        if start is None:
            continue
        read = start["result"]["read"]
        u = _unpack(read)
        if not u:
            continue
        s, n, rows = u
        if "radius_m" in n:
            n["radius_m"] = 1.0
        if "window_ms" in n:
            n["window_ms"] = 1.0
        start["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _m_sol_missing_witnesses(c: dict[str, Any]) -> None:
    kill = {"P1:control", "P3:apply1", "P4a:apply1", "P4b:apply"}
    oids = set()
    for tag in kill:
        start, pages = _job_events(c, tag)
        for ev in ([start] if start else []) + pages:
            if ev is not None:
                oids.add(str(ev["result"]["op_id"]))
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"] if str(ev.get("op_id")) not in oids]


def _m_sol_no_server_restart(c: dict[str, Any]) -> None:
    c["samples"]["backend.jsonl"] = [
        ev for ev in c["samples"]["backend.jsonl"]
        if not (ev.get("kind") == "restart" and
                str((ev.get("data") or {}).get("target")) == "server")]


def _p_sol_normal_opstate(c: dict[str, Any]) -> None:
    be = c["samples"]["backend.jsonl"]
    out = []
    for ev in be:
        if ev.get("kind") == "op.state":
            b = copy.deepcopy(ev)
            b["t_ms"] -= 1000.0
            b["data"]["at_ms"] = float(b["data"].get("at_ms") or 0.0) - 1000.0
            b["data"]["state"] = "pendiente"
            b["data"]["reason"] = None
            out.append(b)
        out.append(ev)
    c["samples"]["backend.jsonl"] = out


def _p_sol_fresh_p3_generation(c: dict[str, Any]) -> None:
    mapping: dict[str, str] = {}
    for tag in ("P3:apply1", "P3:apply2"):
        _start, pages = _job_events(c, tag)
        for ev in pages:
            u = _unpack(ev["result"]["read"])
            if not u:
                continue
            for r in u[2]:
                if int(r.get("sample_idx", -1)) != 0 or str(r.get("parent_net_id") or ""):
                    continue
                net = str(r.get("net_id"))
                if net not in mapping:
                    hi, lo = net.split(":")
                    mapping[net] = f"{hi}:{int(lo) + 2000}"
    chest = _find_row(c, "P3:pre_reset", lambda r: str(r.get("class_name")) == "SeaChest")
    if chest is not None:
        net = str(chest["net_id"])
        if net not in mapping:
            hi, lo = net.split(":")
            mapping[net] = f"{hi}:{int(lo) + 2000}"

    def rec(x: Any) -> Any:
        if isinstance(x, str):
            return mapping.get(x, x)
        if isinstance(x, list):
            return [rec(a) for a in x]
        if isinstance(x, dict):
            return {k: rec(v) for k, v in x.items()}
        return x

    for ev in c["samples"]["bridge.jsonl"]:
        t = float(ev.get("t_ms") or 0.0)
        if 370000.0 <= t < 540000.0:
            for key in ("args", "result"):
                if isinstance(ev.get(key), dict):
                    ev[key] = rec(ev[key])
    for line in c["samples"]["scene_del.jsonl"]:
        t = float(line.get("t_ms") or 0.0)
        if 370000.0 <= t < 540000.0:
            net = f"{int(line['net_high'])}:{int(line['net_low'])}"
            if net in mapping:
                line["net_low"] = int(mapping[net].split(":")[1])


def _p_sol_creature_extra_disk(c: dict[str, Any]) -> None:
    row = _find_row(c, "P2:apply", _eeinit_pred("Animal_CervusElaphus", 6090.0, 7710.0))
    if row is None:
        return
    net = str(row["net_id"])
    crows = _find_row(c, "P2:post", lambda r: str(r.get("net_id")) == net)
    if crows is None:
        return
    outside = dict(crows)
    outside["pos_x_m"] = 6020.0
    _remove_row(c, "P2:post", lambda r: str(r.get("net_id")) == net)
    _add_census_disk(c, "P2:extra", "e1" * 16, "e1" * 16, 262600.0, 262000.0, 20.0,
                     (6020.0, float(outside["pos_z_m"])), 60.0, [outside])


def _p_sol_background_apple(c: dict[str, Any]) -> None:
    row = _find_row(c, "P2:post", _obj1_pred)
    if row is not None:
        apple = dict(row)
        apple["net_id"] = "1:999"
        apple["class_name"] = "Apple"
        _add_row(c, "P2:post", apple)


# ---------------------------------------------------------------------------------------------------
# Casos de Sol de T2d-2 (punto 3 del encargo).
# ---------------------------------------------------------------------------------------------------

def _m_creatures_born_50m(c: dict[str, Any]) -> None:
    # Criaturas a 50 m sobre el suelo, con trayectoria y checkpoint coherentes: solo la parte vertical
    # de F2P-02 puede delatarlo (O-04). Se mueven las filas del testigo y del censo.
    def up(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            if int(r.get("ai_agent_b", 0)) == 1:
                r["pos_y_m"] = float(r["pos_y_m"]) + 50.0
    _edit_rows(c, "P2:apply", up)
    _edit_rows(c, "P2:post", up)
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") != "req" or ev.get("path") != "/result":
            continue
        read = (ev.get("body") or {}).get("read") or {}
        ck = read.get("checkpoint")
        if not isinstance(ck, list):
            continue
        for row in ck:
            if isinstance(row, list) and len(row) >= 7 and str(row[0]).startswith(("zmb-", "ani-")):
                row[3] = float(row[3]) + 50000.0


def _m_fake_tick1_late(c: dict[str, Any]) -> None:
    # El «tick 1» llega 33 s tarde y con un frame 1000 más: la posición no cambia, pero no es la
    # trayectoria de los K ticks siguientes (§5.3, Q-01).
    def fn(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            if int(r.get("ai_agent_b", 0)) == 1 and int(r.get("sample_idx", -1)) >= 1:
                r["tick_ms"] = float(r["tick_ms"]) + 33000.0
                r["frame"] = int(r["frame"]) + 1000
    _edit_rows(c, "P2:apply", fn)


def _m_p5_total34(c: dict[str, Any]) -> None:
    # Una entidad de más, desplazada, que sigue siendo de una generación de P5 dentro de la cobertura.
    row = _find_row(c, "P5:post_apply", lambda r: str(r.get("class_name")) == "Land_Wreck_Ikarus")
    if row is not None:
        clone = dict(row)
        clone["net_id"] = "1:999"
        clone["pos_x_m"] = float(clone["pos_x_m"]) + 10.0
        _add_row(c, "P5:post_apply", clone)


def _m_p5_k_apple(c: dict[str, Any]) -> None:
    # K cuenta cualquier muestra 0: si las filas del corte no casan con el documento, K = 0.
    _edit_rows(c, "P5:cut", lambda rows: [r.__setitem__("class_name", "Apple") for r in rows])


def _scene2_pred(x: float):
    def p(r: dict[str, Any]) -> bool:
        return str(r.get("class_name")) == "MediumTent" and \
            abs(float(r.get("pos_x_m", 0.0)) - x) <= 0.5
    return p


def _m_scene2_yaw_changed(c: dict[str, Any]) -> None:
    for tag in ("P3:post_reset1", "P3:post_reset2", "P3c:clean"):
        _mutate_row(c, tag, _scene2_pred(6178.0),
                    lambda r: r.__setitem__("yaw_deg", float(r["yaw_deg"]) + 90.0))


def _m_scene2_tent_rotated_reset1(c: dict[str, Any]) -> None:
    _mutate_row(c, "P3:post_reset1", _scene2_pred(6178.0),
                lambda r: r.__setitem__("yaw_deg", float(r["yaw_deg"]) + 90.0))


def _m_scene2_20m_up_p3c(c: dict[str, Any]) -> None:
    _mutate_row(c, "P3c:clean", _scene2_pred(6178.0),
                lambda r: r.__setitem__("pos_y_m", float(r["pos_y_m"]) + 20.0))


def _m_foreign_moved_second_reset(c: dict[str, Any]) -> None:
    _mutate_row(c, "P3:post_reset2",
                lambda r: str(r.get("class_name")) == "Apple" and
                abs(float(r.get("pos_x_m", 0.0)) - 6140.0) <= 0.5,
                lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 20.0))


def _m_no_spawn_cleanup(c: dict[str, Any]) -> None:
    # Sin respuestas crudas de `per_spawn_raw` ni `per_cleanup_qa`: los estímulos no están acreditados.
    ids = {str(ev.get("op_id")) for ev in c["samples"]["bridge.jsonl"]
           if ev.get("verb") in ("per_spawn_raw", "per_cleanup_qa")}
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"] if str(ev.get("op_id")) not in ids]


def _m_reappears_1m(c: dict[str, Any]) -> None:
    _m_reappears(c)
    _mutate_row(c, "P4b:post_restart",
                lambda r: str(r.get("class_name")) == "Land_Wreck_Ikarus",
                lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 1.0))


def _m_delete_confirm_request(c: dict[str, Any]) -> None:
    # Petición y confirmación separadas por un tick: la métrica tiene que informar 33 ms, no 0.
    row = copy.deepcopy(c["samples"]["scene_del.jsonl"][0])
    row["t_ms"] = float(row["t_ms"]) - 33.0
    row["frame"] = int(row["frame"]) - 1
    row["deleted_confirmed_b"] = 0
    row["delete_failed_b"] = 0
    row["confirm_tick_ms"] = 0.0
    row["signal_ref_b"] = 1
    c["samples"]["scene_del.jsonl"].insert(0, row)


def _m_copy_perturbation_0p01(c: dict[str, Any]) -> None:
    # Perturbación por debajo de la tolerancia de F2P-12: la partida buena sigue PASA.
    _edit_rows(c, "P2:post", lambda rows: [r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.01)
                                           for r in rows if str(r.get("class_name")) != "WoodenCrate"])


def _p_h4_control_creature(c: dict[str, Any]) -> None:
    _add_row(c, "P1:control", {
        "class_name": "ZmbM_FarmerFat_Brown", "net_id": "1:900", "parent_net_id": "",
        "pos_x_m": 6100.0, "pos_y_m": 6.0, "pos_z_m": 7700.0, "yaw_deg": 0.0,
        "tick_ms": 103100.0, "frame": 5, "ai_agent_b": 0, "sample_idx": 0, "alive_b": 1,
        "surface_y_m": 6.0,
    })
    _add_row(c, "P1:control", {
        "class_name": "ZmbM_FarmerFat_Brown", "net_id": "1:900", "parent_net_id": "",
        "pos_x_m": 6100.0, "pos_y_m": 6.0, "pos_z_m": 7700.0, "yaw_deg": 0.0,
        "tick_ms": 103133.0, "frame": 6, "ai_agent_b": 1, "sample_idx": 1, "alive_b": 1,
        "surface_y_m": 6.0,
    })
    _m_extra_scene_creature(c)
    _mutate_row(c, "P3:apply1", lambda r: str(r.get("net_id")) == "1:997",
                lambda r: r.__setitem__("ai_agent_b", 0))


def _n_surface_absent_witness(c: dict[str, Any]) -> None:
    _drop_column(c, "P2:apply", "surface_y_m")


def _n_rows_from_backend(c: dict[str, Any]) -> None:
    # Las filas del censo P2:post se copian de `/api/observation` (backend) y no tienen respuesta
    # cruda de la sonda que las respalde: se retiran sus páginas de `job_read`.
    _start, pages = _job_events(c, "P2:post")
    oids = {str(ev["result"]["op_id"]) for ev in pages}
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"] if str(ev.get("op_id")) not in oids]


SOL_MUTANTS: dict[str, dict[str, Any]] = {
    "sol_confirmed_alive_hidden": {"apply": _m_sol_confirmed_alive_hidden,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-10": "fail"},
                                   "allowed_non_pass": {}},
    "sol_p2n_uncompensated": {"apply": _m_sol_p2n_uncompensated, "expected_exit_code": 1,
                              "must_fail_status": {"F2P-03": "fail"},
                              "allowed_non_pass": {}},
    "sol_creature_missing_original_disk": {"apply": _m_sol_creature_missing_original_disk,
                                           "expected_exit_code": 2,
                                           "must_fail_status": {"F2P-10": "missing"},
                                           "allowed_non_pass": {}},
    "sol_session_differ_p2": {"apply": _m_sol_session_differ_p2, "expected_exit_code": 1,
                              "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                              "allowed_non_pass": {}},
    "sol_p3_reset_without_result": {"apply": _m_sol_p3_reset_without_result,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-05": "fail"},
                                    "allowed_non_pass": {}},
    "sol_reconciliation_without_result": {"apply": _m_sol_reconciliation_without_result,
                                          "expected_exit_code": 1,
                                          "must_fail_status": {"F2P-08": "fail", "F2P-09": "fail"},
                                          "allowed_non_pass": {}},
    "sol_witness_radius_window": {"apply": _m_sol_witness_radius_window,
                                  "expected_exit_code": 2,
                                  "must_fail_status": {"F2P-13": "missing"},
                                  "allow_other_non_pass": True},
    "sol_missing_witnesses": {"apply": _m_sol_missing_witnesses, "expected_exit_code": 2,
                              "must_fail_status": {"F2P-13": "missing"},
                              "allow_other_non_pass": True},
    "sol_no_server_restart": {"apply": _m_sol_no_server_restart, "expected_exit_code": 2,
                              "must_fail_status": {"F2P-07": "missing"},
                              "allowed_non_pass": {}},
    "sol_creatures_born_50m": {"apply": _m_creatures_born_50m, "expected_exit_code": 1,
                               "must_fail_status": {"F2P-02": "fail"},
                               "allowed_non_pass": {}},
    "sol_fake_tick1_late": {"apply": _m_fake_tick1_late, "expected_exit_code": 1,
                            "must_fail_status": {"F2P-02": "fail"},
                            "allowed_non_pass": {}},
    "sol_p5_total34": {"apply": _m_p5_total34, "expected_exit_code": 1,
                       "must_fail_status": {"F2P-09": "fail"},
                       "allowed_non_pass": {}},
    "sol_p5_k_apple": {"apply": _m_p5_k_apple, "expected_exit_code": 1,
                       "must_fail_status": {"F2P-09": "fail"},
                       "allowed_non_pass": {}},
    "sol_scene2_yaw_changed": {"apply": _m_scene2_yaw_changed, "expected_exit_code": 1,
                               "must_fail_status": {"F2P-05": "fail", "F2P-06": "fail"},
                               "allowed_non_pass": {}},
    "sol_scene2_tent_rotated_reset1": {"apply": _m_scene2_tent_rotated_reset1,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-05": "fail"},
                                       "allowed_non_pass": {}},
    "sol_scene2_20m_up_p3c": {"apply": _m_scene2_20m_up_p3c, "expected_exit_code": 1,
                              "must_fail_status": {"F2P-06": "fail"},
                              "allowed_non_pass": {}},
    "sol_foreign_moved_second_reset": {"apply": _m_foreign_moved_second_reset,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-05": "fail"},
                                       "allowed_non_pass": {}},
    "sol_no_spawn_cleanup": {"apply": _m_no_spawn_cleanup, "expected_exit_code": 1,
                             "must_fail_status": {"F2P-06": "fail"},
                             "allowed_non_pass": {"F2P-05": ["fail"]}},
    "sol_reappears_1m": {"apply": _m_reappears_1m, "expected_exit_code": 1,
                         "must_fail_status": {"F2P-07": "fail"},
                         "allowed_non_pass": {}},
    # §6 (v1.3.6, errata de la v1.3.4): una criatura de más con criaturas en la ventana de control
    # da INCONCLUSO por F2P-13, no PASA.
    "sol_h4_control_creature": {"apply": _p_h4_control_creature, "expected_exit_code": 2,
                                "must_fail_status": {"F2P-13": "missing"},
                                "allowed_non_pass": {}},
}

SOL_NEGATIVES: dict[str, dict[str, Any]] = {
    "sol_census_before_first_P2_apply": {"apply": _n_sol_census_before_first_P2_apply},
    "sol_P2_snapshot_tick_zero": {"apply": _n_sol_P2_snapshot_tick_zero},
    "sol_P2_pages_other_instance": {"apply": _n_sol_P2_pages_other_instance},
}

SOL_POSITIVES: dict[str, dict[str, Any]] = {
    "sol_normal_opstate": {"apply": _p_sol_normal_opstate},
    "sol_fresh_p3_generation": {"apply": _p_sol_fresh_p3_generation},
    "sol_creature_extra_disk": {"apply": _p_sol_creature_extra_disk},
    "sol_background_apple": {"apply": _p_sol_background_apple},
    "sol_delete_confirm_request": {"apply": _m_delete_confirm_request},
    "sol_copy_perturbation_0p01": {"apply": _m_copy_perturbation_0p01},
}

# Caso de Sol -> comprobación que tiene que tumbar (o PASA). Cobertura explícita del punto 4.
SOL_CASES: dict[str, dict[str, Any]] = {
    "census_before_first_P2_apply": {"kind": "negative", "name": "sol_census_before_first_P2_apply",
                                     "check": "unbacked_rows (O-05)"},
    "P2_snapshot_tick_zero": {"kind": "negative", "name": "sol_P2_snapshot_tick_zero",
                              "check": "unbacked_rows (O-05)"},
    "P2_pages_from_other_instance_without_hello": {"kind": "negative",
                                                   "name": "sol_P2_pages_other_instance",
                                                   "check": "unbacked_rows (O-06)"},
    "confirmed_alive_hidden_by_unbacked_next_census": {"kind": "mutant",
                                                       "name": "sol_confirmed_alive_hidden",
                                                       "check": "F2P-10 (O-06)"},
    "P2n_uncompensated_new_generation_entity": {"kind": "mutant", "name": "sol_p2n_uncompensated",
                                                "check": "F2P-03 (O-03)"},
    "creature_confirmed_missing_only_from_original_disk": {
        "kind": "mutant", "name": "sol_creature_missing_original_disk", "check": "F2P-10 (O-07)"},
    "delivery_and_result_session_differ_P2": {"kind": "mutant", "name": "sol_session_differ_p2",
                                              "check": "F2P-01 (O-11)"},
    "P3_reset_opstate_without_received_result": {"kind": "mutant",
                                                 "name": "sol_p3_reset_without_result",
                                                 "check": "F2P-01 (O-11)"},
    "reconciliation_delivered_without_result": {"kind": "mutant",
                                                "name": "sol_reconciliation_without_result",
                                                "check": "F2P-08 (O-12)"},
    "witness_radius_1m_and_window_1ms": {"kind": "mutant", "name": "sol_witness_radius_window",
                                         "check": "F2P-13 (O-14)"},
    "missing_control_and_three_operation_witnesses": {"kind": "mutant",
                                                      "name": "sol_missing_witnesses",
                                                      "check": "F2P-13 (O-14)"},
    "no_server_restart_events": {"kind": "mutant", "name": "sol_no_server_restart",
                                 "check": "F2P-07 (O-10, punto 8)"},
    "normal_opstate_transitions_before_terminal": {"kind": "positive",
                                                   "name": "sol_normal_opstate",
                                                   "check": "PASA (O-02)"},
    "legitimate_fresh_P3_generation": {"kind": "positive", "name": "sol_fresh_p3_generation",
                                       "check": "PASA (O-03)"},
    "good_creature_tracked_by_extra_disk": {"kind": "positive",
                                            "name": "sol_creature_extra_disk",
                                            "check": "PASA (O-07)"},
    "33_correct_roots_plus_background_Apple": {"kind": "positive", "name": "sol_background_apple",
                                               "check": "PASA (H-6, H-10)"},
    "creatures_born_50m_above_surface": {"kind": "mutant", "name": "sol_creatures_born_50m",
                                         "check": "F2P-02 (O-04)"},
    "fake_tick1_is_33seconds_late": {"kind": "mutant", "name": "sol_fake_tick1_late",
                                     "check": "F2P-02 (trayectoria)"},
    "P5_total34_with_one_displaced_leftover": {"kind": "mutant", "name": "sol_p5_total34",
                                               "check": "F2P-09 (O-13)"},
    "P5_K_is_only_unrelated_Apple": {"kind": "mutant", "name": "sol_p5_k_apple",
                                     "check": "F2P-09 (O-13)"},
    "scene2_yaw_changed": {"kind": "mutant", "name": "sol_scene2_yaw_changed",
                           "check": "F2P-05/F2P-06 (O-09)"},
    "scene2_tent_rotated_90_on_reset1": {"kind": "mutant", "name": "sol_scene2_tent_rotated_reset1",
                                         "check": "F2P-05 (O-09)"},
    "scene2_20m_up_P3c": {"kind": "mutant", "name": "sol_scene2_20m_up_p3c",
                          "check": "F2P-06 (O-09)"},
    "foreign_moved_on_second_reset": {"kind": "mutant", "name": "sol_foreign_moved_second_reset",
                                      "check": "F2P-05 (O-09)"},
    "no_spawn_raw_no_cleanup_evidence": {"kind": "mutant", "name": "sol_no_spawn_cleanup",
                                         "check": "F2P-06 (O-08)"},
    "F2_reappears_1m_away": {"kind": "mutant", "name": "sol_reappears_1m",
                             "check": "F2P-07 (O-10)"},
    "delete_confirm_one_tick_after_request": {"kind": "positive", "name": "sol_delete_confirm_request",
                                              "check": "PASA y métrica 33 ms (O-17)"},
    "copy_perturbation_0p01_instead_of_0p1": {"kind": "positive", "name": "sol_copy_perturbation_0p01",
                                              "check": "PASA (O-16)"},
    "H4_control_creature_AI_initializes_at_tick1": {"kind": "mutant",
                                                    "name": "sol_h4_control_creature",
                                                    "check": "INCONCLUSO F2P-13 (H-4, v1.3.6)"},
}

MUTANTS: dict[str, dict[str, Any]] = {
    "creation_suppressed": {"apply": _m_creation_suppressed, "expected_exit_code": 1,
                            "must_fail_checks": ["F2P-01"],
                            "allowed_non_pass": {"F2P-02": ["fail"], "F2P-04": ["fail"],
                                                 "F2P-12": ["missing"]}},
    "entity_moved_0p6_witness": {"apply": _m_entity_moved_witness, "expected_exit_code": 1,
                                 "must_fail_checks": ["F2P-02"],
                                 "allowed_non_pass": {"F2P-12": ["missing"]}},
    "entity_moved_0p6_census": {"apply": _m_entity_moved_census, "expected_exit_code": 1,
                                "must_fail_checks": ["F2P-02"], "allowed_non_pass": {"F2P-12": ["missing"]}},
    "creature_born_1m": {"apply": _m_creature_born_1m, "expected_exit_code": 1,
                         "must_fail_checks": ["F2P-02"], "allowed_non_pass": {}},
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
    "surface_y_absent_witness": {"apply": _n_surface_absent_witness},
    "rows_copied_from_backend": {"apply": _n_rows_from_backend},
    "op_state_without_event": {"apply": _n_op_state_orphan},
    "tap_trace_mismatch": {"apply": _n_tap_mismatch},
    "oracle_commit_mismatch": {"apply": _n_oracle_commit},
    "oracle_commit_split": {"apply": _n_oracle_commit_split},
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
    "filas_sin_respuesta_cruda": ["rows_without_raw_response", "rows_copied_from_backend"],
    "trabajo_pagina_epoch_sello_no_casan": [
        "job_mismatch", "page_mismatch", "epoch_mismatch", "probe_stamp_mismatch", "missing_page",
    ],
    "frescura_antes_del_efecto": ["stale_rows"],
    "net_id_cero_en_creado": ["net_id_zero"],
    "surface_y_constante_o_ausente": ["surface_y_constant", "surface_y_absent",
                                      "surface_y_absent_witness"],
    "op_state_sin_evento": ["op_state_without_event"],
    "traza_no_cuadra_con_respuestas": ["tap_trace_mismatch"],
    "commit_oraculo_o_pbo_no_coinciden": ["oracle_commit_mismatch", "oracle_commit_split",
                                          "pbo_mismatch"],
    "censo_vacio_o_sin_baseline": ["empty_census", "baseline_missing"],
}

EXPECTED_HARNESS_TESTS: dict[str, Any] = {}


def mutate(campaign: dict[str, Any], name: str) -> dict[str, Any]:
    c = copy.deepcopy(campaign)
    spec = (MUTANTS.get(name) or NEGATIVES.get(name) or SOL_MUTANTS.get(name) or
            SOL_NEGATIVES.get(name) or SOL_POSITIVES[name])
    spec["apply"](c)
    return c
