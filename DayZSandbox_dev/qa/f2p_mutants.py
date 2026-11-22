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


def _refresh_rows_captured(campaign: dict[str, Any], tag: str) -> None:
    """S-01: tras editar filas, `rows_captured_n` tiene que seguir igual al número de filas."""
    start, pages = _job_events(campaign, tag)
    if start is None:
        return
    total = 0
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if u:
            total += len(u[2])
    read = start["result"]["read"]
    u = _unpack(read)
    if not u:
        return
    s, n, rows = u
    n["rows_captured_n"] = float(total)
    start["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


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
    _refresh_rows_captured(campaign, tag)


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
        _refresh_rows_captured(campaign, tag)


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
    rid = _r15c_rid(campaign)
    t = max(float(ev.get("t_ms") or 0.0) for ev in tap) + 1.0
    tap.append({"t_ms": t, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid,
                "query": {"peer": "server", "inst": "x" * 32, "session": "s" * 64, "conn": "1"},
                "body": {"op_id": "ghost-op", "session": "s" * 64, "epoch": "e" * 32,
                         "status": "done", "reason": "", "dup": False, "read": {}}})
    tap.append({"t_ms": t + 1.0, "dir": "resp", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid, "body": {"ok": True}})


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


def _checkpoint_rows(read: dict[str, Any]) -> list[list[Any]] | None:
    """V-14: el checkpoint real está en `read.obs` con `at == "checkpoint"`, no en el alias."""
    obs = read.get("obs")
    if not isinstance(obs, dict) or obs.get("at") != "checkpoint":
        return None
    rows = obs.get("rows")
    return rows if isinstance(rows, list) else None


def _edit_checkpoint(campaign: dict[str, Any], lid: str, dx_m: float) -> None:
    for ev in campaign["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") != "req" or ev.get("path") != "/result":
            continue
        read = (ev.get("body") or {}).get("read") or {}
        ck = _checkpoint_rows(read)
        if ck is None:
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
    # §6: entidad movida 0,6 m en el testigo. En horizontal, porque V-10 admite hasta 2,0 m de
    # desfase vertical en objetos.
    _mutate_row(c, "P2:apply", _eeinit_pred("Land_Wreck_Ikarus", 6188.0, 7626.0),
                lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 0.6))


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
    # v1.3.10: el control se reconoce en su censo propio de 30 m, no en el censo principal.
    _remove_row(c, "P4b:control",
                lambda r: str(r.get("class_name")) == "Barrel_Yellow")


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
    """Añade un trabajo de censo nuevo (una lectura independiente), como el resto de la evidencia.

    v1.3.11: copia la forma de las páginas de la fixture que recibe. Si las páginas de `P1:base`
    llevan `server_epoch` en su `sk` y su `result` lleva `inst` (fixture de 7ed2615), los pone; si no
    (fixture nativa), no. Con 0 filas usa `pages_n` como la base: 1 si la base lleva epoch, 0 si no.
    """
    base_start, base_pages = _job_events(c, "P1:base")
    result_has_inst = base_start is not None and "inst" in base_start
    page_has_epoch = False
    for ev in base_pages:
        u = _unpack(ev["result"]["read"])
        if u and "server_epoch" in u[0]:
            page_has_epoch = True
            break
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
    args_payload = wire.pack_payload(
        scalars_str={"area_tag": tag},
        scalars_num={"center_x_m": center[0], "center_z_m": center[1], "radius_m": radius,
                     "include_director_b": 1.0, "select_all_entityai_b": 1.0})
    bridge.append({"t_ms": start_t, "ev": "enq", "peer": "server", "op_id": start_oid,
                   "verb": "per_census_start", "args": args_payload, "inst": inst})
    bridge.append({"t_ms": start_t + 5, "ev": "deliver", "peer": "server", "op_id": start_oid,
                   "verb": "per_census_start", "args": args_payload, "inst": inst})
    bridge.append({"t_ms": start_t + 10, "ev": "poll", "peer": "server", "inst": inst,
                   "http": 200, "now_ms": start_t + 10, "op_ids": [start_oid], "n_ops": 1})
    start_res = {"t_ms": start_t + 20, "ev": "result", "peer": "server",
                 "http": 200, "op_id": start_oid,
                 "result": {"op_id": start_oid, "status": "done", "reason": "", "read": read}}
    if result_has_inst:
        start_res["inst"] = inst
    bridge.append(start_res)
    ps = {"job": start_oid, "state": "done", "reason": "", "resource": "per_census"}
    if page_has_epoch:
        ps["server_epoch"] = epoch
    pages_n = (1.0 if page_has_epoch else 0.0) if not rows else 1.0
    pn = {"page_n": 0.0, "pages_n": pages_n, "rows_total_n": float(len(rows)),
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
    page_res = {"t_ms": page_t + 20, "ev": "result", "peer": "server",
                "http": 200, "op_id": page_oid,
                "result": {"op_id": page_oid, "status": "done", "reason": "", "read": pread}}
    if result_has_inst:
        page_res["inst"] = inst
    bridge.append(page_res)


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


def _remove_census_tag(c: dict[str, Any], tag: str) -> None:
    """Retira todos los trabajos de censo con `area_tag == tag` (arranque, páginas y liberación)."""
    bridge = c["samples"]["bridge.jsonl"]
    job_ids = set()
    start_ops: set[str] = set()
    for ev in bridge:
        if ev.get("ev") == "result" and ev.get("http") == 200:
            read = ev.get("result", {}).get("read")
            u = _unpack(read) if isinstance(read, dict) else None
            if u and str(u[0].get("area_tag") or "") == tag:
                job_ids.add(str(u[0].get("job") or ""))
                # El evento `result` del arranque no lleva `verb`; se identifica por su `area_tag`.
                start_ops.add(str(ev.get("op_id") or ""))
    drop = set(start_ops)
    for ev in bridge:
        oid = str(ev.get("op_id") or "")
        if not oid:
            continue
        if ev.get("verb") in ("job_read", "job_free"):
            u = _unpack(ev.get("args")) if isinstance(ev.get("args"), dict) else None
            if u and str(u[0].get("job") or "") in job_ids:
                drop.add(oid)
    c["samples"]["bridge.jsonl"] = [ev for ev in bridge if str(ev.get("op_id") or "") not in drop]


def _remove_census_prefix(c: dict[str, Any], prefix: str) -> None:
    """Retira todos los trabajos de censo cuya etiqueta empieza por `prefix` (V-08)."""
    bridge = c["samples"]["bridge.jsonl"]
    job_ids = set()
    op_ids = set()
    for ev in bridge:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        read = (ev.get("result") or {}).get("read")
        u = _unpack(read) if isinstance(read, dict) else None
        if not u:
            continue
        tag = str(u[0].get("area_tag") or "")
        if tag.startswith(prefix):
            job_ids.add(str(u[0].get("job") or ""))
            op_ids.add(str(ev.get("op_id") or ""))
    if not job_ids:
        return
    for ev in bridge:
        if ev.get("ev") in ("enq", "deliver") and \
                str(ev.get("op_id") or "") in op_ids:
            op_ids.add(str(ev.get("op_id") or ""))
    c["samples"]["bridge.jsonl"] = [
        ev for ev in bridge if str(ev.get("op_id") or "") not in op_ids]


def _drop_deliver_for_tag_start(c: dict[str, Any], tag: str) -> None:
    start, _pages = _job_events(c, tag)
    if start is None:
        return
    oid = str((start.get("result") or {}).get("op_id") or "")
    if not oid:
        return
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"]
        if not (ev.get("ev") == "deliver" and str(ev.get("op_id") or "") == oid)]


def _m_sol_creature_missing_original_disk(c: dict[str, Any]) -> None:
    # O-07/R-04: sin los discos suplementarios, las criaturas del borde (ani-01, ani-02, zmb-08)
    # solo están cubiertas por el disco original y su ausencia no es concluyente.
    _remove_census_prefix(c, "P3:post_reset1:disk:")


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
    sess = str(dels[0].get("session") or "")
    removed: set[int] = set()
    keep = []
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str((ev.get("body") or {}).get("op_id")) == oid and \
                str((ev.get("body") or {}).get("session")) == sess:
            if isinstance(ev.get("req_id"), int):
                removed.add(ev["req_id"])
            continue
        keep.append(ev)
    c["samples"]["bridge_tap.jsonl"] = [
        ev for ev in keep
        if not (ev.get("dir") == "resp" and ev.get("path") == "/result" and
                ev.get("req_id") in removed)]


def _m_sol_reconciliation_without_result(c: dict[str, Any]) -> None:
    targets: set[tuple[str, str]] = set()
    for d in _tap_deliveries(c, "state.read"):
        t = float(d.get("t_ms") or 0.0)
        if 550000.0 <= t < 610000.0 or 760000.0 <= t < 820000.0:
            targets.add((str(d["op_id"]), str(d["session"])))
    removed: set[int] = set()
    keep = []
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                (str((ev.get("body") or {}).get("op_id")),
                 str((ev.get("body") or {}).get("session"))) in targets:
            if isinstance(ev.get("req_id"), int):
                removed.add(ev["req_id"])
            continue
        keep.append(ev)
    c["samples"]["bridge_tap.jsonl"] = [
        ev for ev in keep
        if not (ev.get("dir") == "resp" and ev.get("path") == "/result" and
                ev.get("req_id") in removed)]


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
    _add_census_disk(c, "P2:post:disk:ani-01", "e1" * 16, "e1" * 16, 262600.0, 262000.0, 20.0,
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
        ck = _checkpoint_rows(read)
        if ck is None:
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
    """R-16: copia de verdad las filas de `/api/observation` del backend como filas del censo.

    Las filas son geométricamente aceptables, pero su procedencia no es la respuesta cruda de la
    sonda: sin la entrega del arranque del censo, la comprobación da INCONCLUSO `unbacked_rows`.
    """
    obs_rows: list[dict[str, Any]] = []
    for ev in c["samples"]["backend.jsonl"]:
        if ev.get("kind") != "api.observation":
            continue
        obs = (ev.get("data") or {}).get("observation") or {}
        rows = obs.get("rows")
        if isinstance(rows, list) and rows:
            obs_rows = [dict(r) for r in rows]
            break
    _start, pages = _job_events(c, "P2:post")
    if pages and obs_rows:
        first = pages[0]
        read = first["result"]["read"]
        u = _unpack(read)
        if u:
            s, n, _ = u
            n["pages_n"] = 1.0
            n["rows_total_n"] = float(len(obs_rows))
            first["result"]["read"] = _repack(s, n, read["ncol"], read["scol"],
                                              obs_rows, read.get("has"))
            for extra in pages[1:]:
                c["samples"]["bridge.jsonl"] = [
                    e for e in c["samples"]["bridge.jsonl"] if e is not extra]
    start, _pages = _job_events(c, "P2:post")
    if start is not None:
        oid = str(start["result"]["op_id"])
        c["samples"]["bridge.jsonl"] = [
            e for e in c["samples"]["bridge.jsonl"]
            if not (e.get("ev") == "deliver" and str(e.get("op_id")) == oid)]


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
                              # v1.3.9: el checkpoint se busca por `(sesión, op_id)`; con la sesión
                              # del resultado cambiada, F2P-02 no tiene checkpoint → INCONCLUSO.
                              "allowed_non_pass": {"F2P-02": ["missing"]}},
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
    "sol_p5_k_apple": {"apply": _m_p5_k_apple, "expected_exit_code": 2,
                       "must_fail_status": {"F2P-09": "missing"},
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
    # V-18 (v1.3.10): sin ningún estímulo crudo, F2P-05 y F2P-06 son INCONCLUSO, no FALLA.
    "sol_no_spawn_cleanup": {"apply": _m_no_spawn_cleanup, "expected_exit_code": 2,
                             "must_fail_status": {"F2P-05": "missing", "F2P-06": "missing",
                                                  "F2P-07": "missing"},
                             "allowed_non_pass": {}},
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

# ---------------------------------------------------------------------------------------------------
# Casos de Sol r2 (T2e-1, R-01, R-02, R-03, R-05, R-06, R-07, R-10, R-11, R-14 y R-15).
# ---------------------------------------------------------------------------------------------------

def _edit_start_num(c: dict[str, Any], tag: str, key: str, value: Any) -> None:
    start, _pages = _job_events(c, tag)
    if start is None:
        return
    read = start["result"]["read"]
    u = _unpack(read)
    if not u:
        return
    s, n, rows = u
    n[key] = value
    start["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _edit_start_args_num(c: dict[str, Any], tag: str, key: str, value: Any) -> None:
    """Cambia un escalar de los argumentos de arranque (la otra cara de `_job_args_ok`)."""
    start, _pages = _job_events(c, tag)
    if start is None:
        return
    jid = str(start["result"]["op_id"])
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") in ("enq", "deliver") and str(ev.get("op_id")) == jid:
            u = _unpack(ev.get("args") or {})
            if not u:
                continue
            s, n, rows = u
            n[key] = value
            ev["args"] = _repack(s, n, [], [], rows, ev["args"].get("has"))


def _blank_start_args(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") in ("enq", "deliver") and \
                str(ev.get("verb") or "") in ("per_census_start", "per_witness_start"):
            ev["args"] = wire.empty_payload()


def _remove_deliver_events(c: dict[str, Any]) -> None:
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"] if ev.get("ev") != "deliver"]


def _drop_deliver_for_prefix(c: dict[str, Any], prefix: str) -> None:
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"]
        if not (ev.get("ev") == "deliver" and str(ev.get("op_id") or "").startswith(prefix))]


def _hello_after_campaign(c: dict[str, Any]) -> None:
    mx = 0.0
    for name in ("bridge.jsonl", "bridge_tap.jsonl", "backend.jsonl", "scene_del.jsonl"):
        for ev in c["samples"][name]:
            t = ev.get("t_ms")
            if isinstance(t, (int, float)) and not isinstance(t, bool):
                mx = max(mx, float(t))
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "hello":
            ev["t_ms"] = mx + 100000.0


def _remove_p2_terminal(c: dict[str, Any]) -> None:
    oid = None
    for d in _tap_deliveries(c, "scene.apply"):
        if 200000.0 <= float(d.get("t_ms") or 0.0) < 300000.0:
            oid = str(d.get("op_id"))
            break
    if oid is None:
        return
    c["samples"]["backend.jsonl"] = [
        ev for ev in c["samples"]["backend.jsonl"]
        if not (ev.get("kind") == "op.state" and
                str((ev.get("data") or {}).get("op_id")) == oid and
                200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0 and
                str((ev.get("data") or {}).get("state")) in ("observado", "parcial", "fallido"))]


def _snap_frame_zero(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        read = (ev.get("result") or {}).get("read")
        u = _unpack(read) if isinstance(read, dict) else None
        if not u or "area_tag" not in u[0]:
            continue
        s, n, rows = u
        n["snap_frame"] = 0.0
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _remove_cut_event(c: dict[str, Any]) -> None:
    c["samples"]["backend.jsonl"] = [
        ev for ev in c["samples"]["backend.jsonl"] if ev.get("kind") != "cut"]


def _result_conn_999(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result":
            q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
            q["conn"] = "999"
            ev["query"] = q


def _remove_acks(c: dict[str, Any]) -> None:
    c["samples"]["bridge_tap.jsonl"] = [
        ev for ev in c["samples"]["bridge_tap.jsonl"]
        if not (ev.get("dir") == "resp" and ev.get("path") == "/result")]


def _second_result_before_delivery(c: dict[str, Any]) -> None:
    dels = [d for d in _tap_deliveries(c, "scene.apply")
            if 200000.0 <= float(d.get("t_ms") or 0.0) < 300000.0]
    if len(dels) < 2:
        return
    oid = str(dels[0]["op_id"])
    t2 = float(dels[1]["t_ms"])
    reqs = [ev for ev in c["samples"]["bridge_tap.jsonl"]
            if ev.get("dir") == "req" and ev.get("path") == "/result" and
            str((ev.get("body") or {}).get("op_id")) == oid]
    reqs.sort(key=lambda x: float(x.get("t_ms") or 0.0))
    if len(reqs) < 2:
        return
    reqs[1]["t_ms"] = t2 - 1.0
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/result" and \
                abs(float(ev.get("t_ms") or 0.0) - (t2 + 3.0)) < 0.5:
            ev["t_ms"] = t2 + 2.0
            break


def _checkpoint_missing(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") != "req" or ev.get("path") != "/result":
            continue
        if 200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0:
            b = ev.get("body") or {}
            read = b.get("read")
            if isinstance(read, dict) and "obs" in read:
                read["obs"] = {"at": "now", "rows": []}


def _bogus_checkpoint_alias(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") != "req" or ev.get("path") != "/result":
            continue
        if 200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0:
            read = (ev.get("body") or {}).get("read")
            if isinstance(read, dict):
                read["checkpoint"] = []


def _remove_reconciliada(c: dict[str, Any]) -> None:
    """R-02: el oráculo no exige ningún evento propio de la reconciliación.

    v1.3.12 (W-11): la fixture ya no trae ningún `reconciliada`, así que la variante sin evento es
    la base. Para que el mutante cambie la campaña sin tocar la reconciliación ni ningún terminal,
    se renumera el `seq` (campo que el oráculo no lee).
    """
    before = list(c["samples"]["backend.jsonl"])
    kept = [ev for ev in before
            if not (ev.get("kind") == "op.state" and
                    str((ev.get("data") or {}).get("reason")) == "reconciliada")]
    c["samples"]["backend.jsonl"] = kept
    if len(kept) == len(before):
        for ev in kept:
            if isinstance(ev.get("seq"), int):
                ev["seq"] = ev["seq"] + 1000


def _empty_reconciliation_read(c: dict[str, Any]) -> None:
    ids = {str(d.get("op_id")) for d in _tap_deliveries(c, "state.read")}
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str((ev.get("body") or {}).get("op_id")) in ids:
            ev["body"]["read"] = {}


def _oracle_check_mismatch(c: dict[str, Any]) -> None:
    c["oracle_check"] = {"ok": True, "commit": "b" * 40, "files": [], "problems": []}


def _oracle_check_missing(c: dict[str, Any]) -> None:
    c["oracle_check"] = None


def _witness_overlap(c: dict[str, Any]) -> None:
    _edit_start_num(c, "P3:apply2", "start_tick_ms", 373000.0)


def _extra_disk_survivor(c: dict[str, Any]) -> None:
    row = _find_row(c, "P3:apply1", _eeinit_pred("Land_Container_1Bo", 6224.0, 7668.0))
    if row is None:
        return
    live = _find_row(c, "P3:pre_reset", lambda r: str(r.get("net_id")) == str(row.get("net_id")))
    if live is None:
        return
    live = dict(live)
    live["pos_x_m"] = 6350.0
    live["pos_z_m"] = 7650.0
    live["pos_y_m"] = 301.0
    live["surface_y_m"] = 301.0
    _add_census_disk(c, "P3c:clean:disk:obj-17", "e1" * 16, "e1" * 16, 494120.0, 494000.0,
                     81.0, (6350.0, 7650.0), 60.0, [live])


def _unbacked_previous_census(c: dict[str, Any]) -> None:
    # La medición anterior al borrado no está respaldada: sin `deliver` no vale (R-06).
    _drop_deliver_for_tag_start(c, "P3:pre_reset")


def _spawn_raw_no_deliver(c: dict[str, Any]) -> None:
    ids = {str(ev.get("op_id")) for ev in c["samples"]["bridge.jsonl"]
           if ev.get("verb") == "per_spawn_raw"}
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"]
        if not (ev.get("ev") == "deliver" and str(ev.get("op_id")) in ids)]


def _spawn_raw_unstamped(c: dict[str, Any]) -> None:
    """R-05: el estímulo crudo viene de una instancia que nunca dio `/hello`."""
    ids = {str(ev.get("op_id")) for ev in c["samples"]["bridge.jsonl"]
           if ev.get("verb") in ("per_spawn_raw", "per_cleanup_qa")}
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id")) in ids:
            ev["inst"] = "5" * 32


def _r2_p2_window_short(c: dict[str, Any]) -> None:
    """R-11: la ventana de P2 cierra antes de la segunda entrega; con 33 duplicados en el censo
    la partida seguiría PASA si no se exigiera la cobertura completa de la op."""
    _edit_start_num(c, "P2:apply", "window_ms", 1500.0)
    _start, apages = _job_events(c, "P2:apply")
    births: set[str] = set()
    for ev in apages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if int(r.get("sample_idx", -1)) == 0 and str(r.get("parent_net_id") or "") == "":
                births.add(str(r.get("net_id")))
    _start2, ppages = _job_events(c, "P2:post")
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ev in ppages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            net = str(r.get("net_id"))
            if net in births and net not in seen:
                seen.add(net)
                picked.append(r)
    for i, r in enumerate(picked[:33]):
        clone = dict(r)
        clone["net_id"] = f"9:{9000 + i}"
        _add_row(c, "P2:post", clone)


def _shift_external_clock(c: dict[str, Any]) -> None:
    off = 5000000.0
    for name in ("bridge.jsonl", "bridge_tap.jsonl", "backend.jsonl", "scene_del.jsonl"):
        for ev in c["samples"][name]:
            t = ev.get("t_ms")
            if isinstance(t, (int, float)) and not isinstance(t, bool):
                ev["t_ms"] = float(t) + off
    for p in c["manifest"]["f2p"]["parts"]:
        p["start_t_ms"] = float(p["start_t_ms"]) + off
        p["end_t_ms"] = float(p["end_t_ms"]) + off


def _find_by_net(c: dict[str, Any], tag: str, net: str) -> dict[str, Any] | None:
    return _find_row(c, tag, lambda r: str(r.get("net_id")) == net)


def _census_sample(c: dict[str, Any], tag: str) -> dict[str, Any] | None:
    _start, pages = _job_events(c, tag)
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if u and u[2]:
            return dict(u[2][0])
    return None


def _m_r2_p2n_residue_displaced(c: dict[str, Any]) -> None:
    """R-08: un residuo de la generación de P2n desplazado 1 m sigue siendo el mismo `net_id`."""
    sample = _census_sample(c, "P2n:clean")
    if sample is None:
        return
    row = dict(sample)
    row.update({"class_name": "Land_Wreck_Ikarus", "net_id": "1:50", "parent_net_id": "",
                "loc_kind": "ground", "slot_name": "", "pos_x_m": 6189.0, "pos_z_m": 7626.0,
                "pos_y_m": 300.19, "surface_y_m": 300.19, "alive_b": 1.0, "ai_agent_b": 0.0,
                "health_hp": 100.0, "max_hp": 100.0})
    _add_row(c, "P2n:clean", row)


def _m_r2_duplicate_scene2_root(c: dict[str, Any]) -> None:
    """R-08: una cuarta raíz de escena 2 en la misma pose es un extra de su generación."""
    birth = _find_row(c, "P3:apply2",
                      lambda r: int(r.get("sample_idx", -1)) == 0 and
                      str(r.get("class_name")) == "WoodenCrate")
    if birth is None:
        return
    clone = dict(birth)
    clone["net_id"] = "1:998"
    _add_row(c, "P3:apply2", clone)


def _m_r2_p5_leftovers_plus_25(c: dict[str, Any]) -> None:
    """R-08: P5 conserva las ocho raíces del corte y crea solo 25 nuevas."""
    new_nets = [f"1:{180 + i}" for i in range(8)]
    cut_nets = [f"1:{141 + i}" for i in range(8)]
    _start, pages = _job_events(c, "P5:post_apply")
    removed: dict[str, dict[str, Any]] = {}
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            net = str(r.get("net_id"))
            if net in set(new_nets):
                removed[net] = dict(r)
    _remove_row(c, "P5:post_apply", lambda r: str(r.get("net_id")) in set(new_nets))
    for new_net, cut_net in zip(new_nets, cut_nets):
        row = removed.get(new_net)
        if row is None:
            continue
        row["net_id"] = cut_net
        _add_row(c, "P5:post_apply", row)


def _p_r2_ce_loot_between_resets_and_before_p5(c: dict[str, Any]) -> None:
    """R-12: botín nuevo de la CE entre los resets y antes de P5 no cuenta."""
    sample = _census_sample(c, "P3:post_reset2")
    if sample is not None:
        row = dict(sample)
        row.update({"class_name": "Apple", "net_id": "0:7777", "parent_net_id": "",
                    "loc_kind": "ground", "slot_name": "", "pos_x_m": 6120.0,
                    "pos_y_m": 301.0, "pos_z_m": 7630.0, "surface_y_m": 301.0,
                    "alive_b": 1.0, "ai_agent_b": 0.0, "health_hp": 100.0, "max_hp": 100.0,
                    "spawn_tick_ms": 385000.0})
        _add_row(c, "P3:post_reset2", row)
    sample = _census_sample(c, "P5:post_apply")
    if sample is not None:
        row = dict(sample)
        row.update({"class_name": "Barrel_Yellow", "net_id": "0:7778", "parent_net_id": "",
                    "loc_kind": "ground", "slot_name": "", "pos_x_m": 6110.0,
                    "pos_y_m": 301.0, "pos_z_m": 7690.0, "surface_y_m": 301.0,
                    "alive_b": 1.0, "ai_agent_b": 0.0, "health_hp": 900.0, "max_hp": 900.0,
                    "spawn_tick_ms": 750000.0})
        _add_row(c, "P5:post_apply", row)


def _m_r2_creature_coverage_gap(c: dict[str, Any]) -> None:
    """R-04: una criatura confirmada borrada cuya última posición queda fuera de la cobertura."""
    _mutate_row(c, "P3:pre_reset",
                lambda r: str(r.get("net_id")) == "1:231",
                lambda r: (r.__setitem__("pos_x_m", 6000.0),
                           r.__setitem__("pos_z_m", 7500.0)))


def _move_object_birth(c: dict[str, Any], net: str, dx: float, dy: float,
                       surface_rise: float) -> None:
    def change(r: dict[str, Any]) -> None:
        r["pos_x_m"] = float(r["pos_x_m"]) + dx
        base_surf = float(r.get("surface_y_m") or r["pos_y_m"])
        r["surface_y_m"] = base_surf + surface_rise
        r["pos_y_m"] = float(r["surface_y_m"]) + dy
    _mutate_row(c, "P2:apply", lambda r: str(r.get("net_id")) == net, change)
    _mutate_row(c, "P2:post", lambda r: str(r.get("net_id")) == net, change)


def _p_r2_r13_slope_supported(c: dict[str, Any]) -> None:
    """R-13: 0,4 m en horizontal sobre terreno que sube 0,4 m, apoyado en su suelo, es PASA."""
    _move_object_birth(c, "1:2", 0.4, 0.0, 0.4)


def _m_r2_r13_horizontal_0p6(c: dict[str, Any]) -> None:
    _move_object_birth(c, "1:2", 0.6, 0.0, 0.0)


def _m_r2_r13_unsupported_2p3(c: dict[str, Any]) -> None:
    # V-10: los objetos admiten 2,0 m de apoyo; 2,3 m ya no.
    _move_object_birth(c, "1:2", 0.0, 2.3, 0.0)


def _m_r2_reappears_at_last_known(c: dict[str, Any]) -> None:
    """R-09: una criatura reaparece en su última posición censada, 10 m desde el nacimiento."""
    pred = lambda r: str(r.get("class_name")) == "ZmbM_FarmerFat_Brown"
    row = _find_row(c, "P2:post", pred)
    if row is None:
        return
    net = str(row.get("net_id"))
    for tag in ("P2:post", "P2n:pre_reset", "P2n:post_apply"):
        _mutate_row(c, tag, lambda r, n=net: str(r.get("net_id")) == n,
                    lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 10.0))
    row = _find_row(c, "P2:post", lambda r: str(r.get("net_id")) == net)
    if row is None:
        return
    _add_row(c, "P4b:post_restart", dict(row))


def _replace_strings(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, dict):
        return {k: _replace_strings(v, mapping) for k, v in node.items()}
    if isinstance(node, list):
        return [_replace_strings(v, mapping) for v in node]
    if isinstance(node, str) and node in mapping:
        return mapping[node]
    return node


def _m_r2_reuse_previous_epochs(c: dict[str, Any]) -> None:
    """R-09: P4c reutiliza el epoch anterior; no hay epoch nuevo que acreditar.

    Solo se reutiliza e3→e2 (el reinicio de P4c). e2→e1 no, para no mezclar ticks de dos epochs
    distintos en la exclusividad de testigos.
    """
    mapping = {"e3" * 16: "e2" * 16}
    for name in ("bridge.jsonl", "bridge_tap.jsonl", "backend.jsonl", "scene_del.jsonl"):
        c["samples"][name] = _replace_strings(c["samples"][name], mapping)
    c["manifest"] = _replace_strings(c["manifest"], mapping)


def _m_r2_control_creation_missing(c: dict[str, Any]) -> None:
    """R-09: sin la respuesta cruda de creación del control persistente, F2P-07 es INCONCLUSO."""
    oid = None
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("verb") != "per_spawn_raw":
            continue
        u = _unpack(ev.get("args")) if isinstance(ev.get("args"), dict) else None
        if u and str(u[0].get("mode") or "") == "persistent_control":
            oid = str(ev.get("op_id") or "")
            break
    if oid is None:
        return
    c["samples"]["bridge.jsonl"] = [
        ev for ev in c["samples"]["bridge.jsonl"] if str(ev.get("op_id") or "") != oid]


def _p_r2_r04_creature_deletes_pass(c: dict[str, Any]) -> None:
    """R-04: la positiva conserva los borrados de criaturas y tiene que dar PASA."""
    c["samples"]["scene_del.jsonl"] = [
        r for r in c["samples"]["scene_del.jsonl"]
        if str(r.get("lid") or "").startswith(("zmb-", "ani-"))]


def _p_r2_r17_metric_first_request(c: dict[str, Any]) -> None:
    """R-17: petición, señal intermedia y confirmación separadas 33 ms: la métrica es 66 ms."""
    first = copy.deepcopy(c["samples"]["scene_del.jsonl"][0])
    req = dict(first)
    req["t_ms"] = float(first["t_ms"]) - 66.0
    req["frame"] = int(first["frame"]) - 2
    req["deleted_confirmed_b"] = 0
    req["delete_failed_b"] = 0
    req["confirm_tick_ms"] = 0.0
    req["signal_ref_b"] = 1
    req["signal_pending_b"] = 0
    req["signal_by_netid_b"] = 0
    mid = dict(req)
    mid["t_ms"] = float(first["t_ms"]) - 33.0
    mid["frame"] = int(first["frame"]) - 1
    mid["signal_ref_b"] = 0
    mid["signal_pending_b"] = 1
    c["samples"]["scene_del.jsonl"].insert(0, mid)
    c["samples"]["scene_del.jsonl"].insert(0, req)

SOL_MUTANTS_R2: dict[str, dict[str, Any]] = {
    "r2_result_conn_mismatch": {"apply": _result_conn_999, "expected_exit_code": 0,
                                "must_fail_status": {},
                                "allow_other_non_pass": True},
    "r2_missing_acks": {"apply": _remove_acks, "expected_exit_code": 1,
                        "must_fail_status": {"F2P-01": "fail"},
                        "allow_other_non_pass": True},
    "r2_second_result_before_delivery": {"apply": _second_result_before_delivery,
                                         "expected_exit_code": 1,
                                         "must_fail_status": {"F2P-04": "fail"},
                                         "allow_other_non_pass": True},
    "r2_checkpoint_missing": {"apply": _checkpoint_missing, "expected_exit_code": 2,
                              "must_fail_status": {"F2P-02": "missing"},
                              "allowed_non_pass": {}},
    # v1.3.10: en P5, una lectura de reconciliación vacía/faltante es FALLA en F2P-09, no
    # INCONCLUSO (§6.1 F2P-09: «Si falta, FALLA»).
    "r2_reconciliation_empty_read": {"apply": _empty_reconciliation_read,
                                     "expected_exit_code": 1,
                                     # v1.3.11 (F-03, §6.1 punto 6): reinicio acreditado y lectura
                                     # vacía es FALLA en F2P-08, no INCONCLUSO.
                                     "must_fail_status": {"F2P-08": "fail", "F2P-09": "fail"},
                                     "allow_other_non_pass": True},
    "r2_oracle_check_mismatch": {"apply": _oracle_check_mismatch, "expected_exit_code": 2,
                                 "must_fail_status": {"F2P-01": "missing"},
                                 "allow_other_non_pass": True},
    "r2_oracle_check_missing": {"apply": _oracle_check_missing, "expected_exit_code": 2,
                                "must_fail_status": {"F2P-01": "missing"},
                                "allow_other_non_pass": True},
    "r2_extra_disk_survivor": {"apply": _extra_disk_survivor, "expected_exit_code": 1,
                               "must_fail_status": {"F2P-06": "fail"},
                               "allowed_non_pass": {}},
    "r2_p2_window_short": {"apply": _r2_p2_window_short,
                           "expected_exit_code": 2,
                           "must_fail_status": {"F2P-13": "missing"},
                           "allow_other_non_pass": True},
    "r2_p5_window_before_cut": {"apply": lambda c: _edit_start_num(c, "P5:cut", "window_ms", 500.0),
                                "expected_exit_code": 2,
                                "must_fail_status": {"F2P-13": "missing"},
                                "allow_other_non_pass": True},
    "r2_creature_coverage_gap": {"apply": _m_r2_creature_coverage_gap,
                                 "expected_exit_code": 2,
                                 "must_fail_status": {"F2P-10": "missing"},
                                 "allowed_non_pass": {}},
    "r2_p2n_residue_displaced": {"apply": _m_r2_p2n_residue_displaced,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-03": "fail"},
                                 "allowed_non_pass": {"F2P-10": ["fail"]}},
    "r2_duplicate_scene2_root": {"apply": _m_r2_duplicate_scene2_root,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-13": "fail"},
                                 "allowed_non_pass": {}},
    "r2_p5_leftovers_plus_25": {"apply": _m_r2_p5_leftovers_plus_25,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-09": "fail"},
                                "allowed_non_pass": {}},
    "r2_same_epoch_restart": {"apply": _m_r2_reuse_previous_epochs,
                              "expected_exit_code": 2,
                              "must_fail_status": {"F2P-07": "missing"},
                              "allowed_non_pass": {}},
    "r2_control_creation_missing": {"apply": _m_r2_control_creation_missing,
                                    "expected_exit_code": 2,
                                    "must_fail_status": {"F2P-07": "missing"},
                                    "allowed_non_pass": {}},
    "r2_reappears_at_last_known": {"apply": _m_r2_reappears_at_last_known,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-07": "fail"},
                                   "allowed_non_pass": {}},
    "r2_horizontal_0p6": {"apply": _m_r2_r13_horizontal_0p6,
                          "expected_exit_code": 1,
                          "must_fail_status": {"F2P-02": "fail"},
                          "allowed_non_pass": {"F2P-01": ["fail"], "F2P-04": ["fail"],
                                               "F2P-12": ["missing"], "F2P-13": ["fail"]}},
    "r2_unsupported_2p3": {"apply": _m_r2_r13_unsupported_2p3,
                           "expected_exit_code": 1,
                           "must_fail_status": {"F2P-02": "fail"},
                           # v1.3.11 (F-06): F2P-01 también exige la pose de los objetos.
                           "allowed_non_pass": {"F2P-01": ["fail"]}},
    "r2_no_cut_event": {"apply": _remove_cut_event, "expected_exit_code": 2,
                        "must_fail_status": {"F2P-09": "missing"},
                        "allow_other_non_pass": True},
    "r2_witness_overlap": {"apply": _witness_overlap, "expected_exit_code": 2,
                           "must_fail_status": {"F2P-13": "missing"},
                           "allow_other_non_pass": True},
    "r2_unbacked_previous_census": {"apply": _unbacked_previous_census,
                                    "expected_exit_code": 2,
                                    "must_fail_status": {"F2P-10": "missing"},
                                    "allow_other_non_pass": True},
}

SOL_NEGATIVES_R2: dict[str, dict[str, Any]] = {
    "r2_no_deliver_events": {"apply": _remove_deliver_events},
    "r2_hello_after_delivery": {"apply": _hello_after_campaign},
    "r2_p2_terminal_missing": {"apply": _remove_p2_terminal},
    "r2_snap_frame_zero": {"apply": _snap_frame_zero},
    "r2_start_args_incomplete": {"apply": _blank_start_args},
    "r2_spawn_raw_no_deliver": {"apply": _spawn_raw_no_deliver},
    "r2_spawn_raw_unstamped": {"apply": _spawn_raw_unstamped},
    "r2_rows_copied_from_backend": {"apply": _n_rows_from_backend},
}

SOL_POSITIVES_R2: dict[str, dict[str, Any]] = {
    "r2_clock_external_origin": {"apply": _shift_external_clock},
    "r2_checkpoint_in_obs_only": {"apply": _bogus_checkpoint_alias},
    "r2_reconciliation_without_event": {"apply": _remove_reconciliada},
    "r2_creature_deletes_pass": {"apply": _p_r2_r04_creature_deletes_pass},
    "r2_ce_loot_between_resets": {"apply": _p_r2_ce_loot_between_resets_and_before_p5},
    "r2_slope_supported": {"apply": _p_r2_r13_slope_supported},
    "r2_metric_first_request": {"apply": _p_r2_r17_metric_first_request},
}

SOL_CASES_R2: dict[str, dict[str, Any]] = {
    "r2_R01_checkpoint_in_obs": {"kind": "positive", "name": "r2_checkpoint_in_obs_only",
                                 "check": "PASA (R-01)"},
    "r2_R01_checkpoint_missing": {"kind": "mutant", "name": "r2_checkpoint_missing",
                                  "check": "F2P-02 (R-01)"},
    "r2_R02_reconciliation_without_event": {"kind": "positive",
                                            "name": "r2_reconciliation_without_event",
                                            "check": "PASA (R-02)"},
    "r2_R02_empty_reconciliation_read": {"kind": "mutant",
                                         "name": "r2_reconciliation_empty_read",
                                         "check": "F2P-08/F2P-09 (R-02)"},
    "r2_R03_external_clock_origin": {"kind": "positive", "name": "r2_clock_external_origin",
                                     "check": "PASA (R-03)"},
    "r2_R05_no_deliver": {"kind": "negative", "name": "r2_no_deliver_events",
                          "check": "unbacked_rows (R-05)"},
    "r2_R05_hello_after_delivery": {"kind": "negative", "name": "r2_hello_after_delivery",
                                    "check": "unbacked_rows (R-05)"},
    "r2_R05_p2_terminal_missing": {"kind": "negative", "name": "r2_p2_terminal_missing",
                                   "check": "unbacked_rows (R-05)"},
    "r2_R05_snap_frame_zero": {"kind": "negative", "name": "r2_snap_frame_zero",
                               "check": "unbacked_rows (R-05)"},
    "r2_R05_spawn_raw_no_deliver": {"kind": "negative", "name": "r2_spawn_raw_no_deliver",
                                    "check": "unbacked_rows (R-05)"},
    "r2_R05_spawn_raw_unstamped": {"kind": "negative", "name": "r2_spawn_raw_unstamped",
                                   "check": "unbacked_rows (R-05)"},
    "r2_R06_unbacked_previous_census": {"kind": "mutant",
                                        "name": "r2_unbacked_previous_census",
                                        "check": "F2P-10 (R-06)"},
    "r2_R07_extra_disk_survivor": {"kind": "mutant", "name": "r2_extra_disk_survivor",
                                   "check": "F2P-06 (R-07)"},
    "r2_R10_result_conn_mismatch": {"kind": "mutant", "name": "r2_result_conn_mismatch",
                                    "check": "traza (R-10)"},
    "r2_R10_missing_acks": {"kind": "mutant", "name": "r2_missing_acks",
                            "check": "traza (R-10)"},
    "r2_R10_second_result_before_delivery": {"kind": "mutant",
                                             "name": "r2_second_result_before_delivery",
                                             "check": "traza (R-10)"},
    "r2_R11_p2_window_short": {"kind": "mutant", "name": "r2_p2_window_short",
                               "check": "F2P-13 (R-11)"},
    "r2_R11_p5_window_before_cut": {"kind": "mutant", "name": "r2_p5_window_before_cut",
                                    "check": "F2P-13 (R-11)"},
    "r2_R11_no_cut_event": {"kind": "mutant", "name": "r2_no_cut_event",
                            "check": "F2P-09 (R-11)"},
    "r2_R14_oracle_check_mismatch": {"kind": "mutant", "name": "r2_oracle_check_mismatch",
                                     "check": "oracle_unverified (R-14)"},
    "r2_R14_oracle_check_missing": {"kind": "mutant", "name": "r2_oracle_check_missing",
                                    "check": "oracle_unverified (R-14)"},
    "r2_R15_witness_overlap": {"kind": "mutant", "name": "r2_witness_overlap",
                               "check": "F2P-13 (R-15)"},
    "r2_R15_start_args_incomplete": {"kind": "negative", "name": "r2_start_args_incomplete",
                                     "check": "unbacked_rows (R-15)"},
    "r2_R04_creature_deletes_pass": {"kind": "positive", "name": "r2_creature_deletes_pass",
                                     "check": "PASA (R-04)"},
    "r2_R04_creature_coverage_gap": {"kind": "mutant", "name": "r2_creature_coverage_gap",
                                     "check": "F2P-10 (R-04)"},
    "r2_R08_p2n_residue_displaced": {"kind": "mutant", "name": "r2_p2n_residue_displaced",
                                     "check": "F2P-03 (R-08)"},
    "r2_R08_duplicate_scene2_root": {"kind": "mutant", "name": "r2_duplicate_scene2_root",
                                     "check": "F2P-13 (R-08)"},
    "r2_R08_p5_leftovers_plus_25": {"kind": "mutant", "name": "r2_p5_leftovers_plus_25",
                                    "check": "F2P-09 (R-08)"},
    "r2_R09_same_epoch_restart": {"kind": "mutant", "name": "r2_same_epoch_restart",
                                  "check": "F2P-07 (R-09)"},
    "r2_R09_control_creation_missing": {"kind": "mutant",
                                        "name": "r2_control_creation_missing",
                                        "check": "F2P-07 (R-09)"},
    "r2_R09_reappears_at_last_known": {"kind": "mutant", "name": "r2_reappears_at_last_known",
                                       "check": "F2P-07 (R-09)"},
    "r2_R12_ce_loot_between_resets": {"kind": "positive", "name": "r2_ce_loot_between_resets",
                                      "check": "PASA (R-12)"},
    "r2_R13_slope_supported": {"kind": "positive", "name": "r2_slope_supported",
                               "check": "PASA (R-13)"},
    "r2_R13_horizontal_0p6": {"kind": "mutant", "name": "r2_horizontal_0p6",
                              "check": "F2P-02 (R-13)"},
    "r2_R13_unsupported_2p3": {"kind": "mutant", "name": "r2_unsupported_2p3",
                               "check": "F2P-02 (V-10)"},
    "r2_R16_rows_copied_from_backend": {"kind": "negative",
                                        "name": "r2_rows_copied_from_backend",
                                        "check": "unbacked_rows (R-16)"},
    "r2_R17_metric_first_request": {"kind": "positive", "name": "r2_metric_first_request",
                                    "check": "métrica 66 ms (R-17)"},
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

# Los ataques de Sol r2 son casos de primera clase: entran en la tabla única de cobertura.
SOL_CASES.update(SOL_CASES_R2)

# ---------------------------------------------------------------------------------------------------
# Sol r3 y la pasada adversarial de Claude (T2f-1): base común de §6.1 v1.3.8.
# ---------------------------------------------------------------------------------------------------

def _edit_page_result_t(c: dict[str, Any], tag: str, value: float) -> None:
    _start, pages = _job_events(c, tag)
    for ev in pages:
        ev["t_ms"] = float(value)


def _tag_job_ops(c: dict[str, Any], prefix: str) -> set[str]:
    bridge = c["samples"]["bridge.jsonl"]
    jids = set()
    for ev in bridge:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        u = _unpack((ev.get("result") or {}).get("read") or {})
        if not u:
            continue
        tag = str(u[0].get("area_tag") or u[0].get("witness_tag") or "")
        if tag.startswith(prefix):
            jids.add(str(u[0].get("job") or ""))
    ids: set[str] = set()
    for ev in bridge:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        u = _unpack((ev.get("result") or {}).get("read") or {})
        if u and str(u[0].get("job") or "") in jids:
            ids.add(str(ev.get("op_id") or ""))
    return ids


def _shift_ops(c: dict[str, Any], ids: set[str], delta: float) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id") or "") in ids and isinstance(ev.get("t_ms"), (int, float)):
            ev["t_ms"] = float(ev["t_ms"]) + delta


def _replace_epoch_for_ops(c: dict[str, Any], ids: set[str], new_epoch: str) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id") or "") not in ids:
            continue
        if isinstance(ev.get("args"), dict):
            ev["args"] = _replace_strings(ev["args"], {})
        read = (ev.get("result") or {}).get("read") if ev.get("ev") == "result" else None
        if isinstance(read, dict):
            u = _unpack(read)
            if not u:
                continue
            s, n, rows = u
            if "server_epoch" in s:
                s["server_epoch"] = new_epoch
                ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows,
                                               read.get("has"))


def _n_r3_page_epoch_empty(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        read = (ev.get("result") or {}).get("read")
        u = _unpack(read) if isinstance(read, dict) else None
        if not u or "page_n" not in u[1]:
            continue
        s, n, rows = u
        s["server_epoch"] = ""
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _n_r3_delivery_instance(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "deliver":
            ev["inst"] = "9" * 32


def _n_r3_stimulus_response_instance(c: dict[str, Any]) -> None:
    """S-01: la instancia del encolado/entrega del estímulo no casa con la del `/hello`.

    v1.3.11 (A-01/F-14): el evento `result` ya no lleva `inst`; se cambian las del `enq`/`deliver`,
    que es de donde sale la identidad de la respuesta.
    """
    verbs = {str(ev.get("op_id")): str(ev.get("verb") or "")
             for ev in c["samples"]["bridge.jsonl"] if ev.get("ev") == "enq"}
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") in ("enq", "deliver") and \
                verbs.get(str(ev.get("op_id") or "")) in ("per_spawn_raw", "per_cleanup_qa"):
            ev["inst"] = "9" * 32


def _edit_census_args(c: dict[str, Any], fn: Callable[[dict[str, Any], dict[str, Any]], None]) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") not in ("enq", "deliver") or \
                str(ev.get("verb") or "") != "per_census_start":
            continue
        u = _unpack(ev.get("args") or {})
        if not u:
            continue
        s, n, rows = u
        fn(s, n)
        ev["args"] = _repack(s, n, [], [], rows, ev["args"].get("has"))


def _n_r3_selectors_zero(c: dict[str, Any]) -> None:
    _edit_census_args(c, lambda s, n: (n.__setitem__("select_all_entityai_b", 0.0),
                                       n.__setitem__("include_director_b", 0.0)))


def _n_r3_rows_captured_n(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        read = (ev.get("result") or {}).get("read")
        u = _unpack(read) if isinstance(read, dict) else None
        if not u or "area_tag" not in u[0]:
            continue
        s, n, rows = u
        n["rows_captured_n"] = float(int(n.get("rows_captured_n", 0)) + 1)
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _n_r3_s09_sin_resultado(c: dict[str, Any]) -> None:
    oid = None
    for d in _tap_deliveries(c, "scene.apply"):
        if 200000.0 <= float(d.get("t_ms") or 0.0) < 300000.0:
            oid = str(d.get("op_id"))
            break
    if oid is None:
        return
    for ev in c["samples"]["backend.jsonl"]:
        if ev.get("kind") == "op.state" and \
                str((ev.get("data") or {}).get("op_id")) == oid and \
                200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0 and \
                str((ev.get("data") or {}).get("state")) in ("observado", "parcial", "fallido"):
            ev["data"]["state"] = "parcial"
            ev["data"]["reason"] = "sin_resultado"


def _m_r3_p3_reuses_p2_nets(c: dict[str, Any]) -> None:
    def fn(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            net = str(r.get("net_id"))
            if net.startswith("1:"):
                r["net_id"] = f"1:{int(net.split(':')[1]) - 199}"
    _edit_rows(c, "P3:apply1", fn)


def _m_r3_p4a_keeps_old_root(c: dict[str, Any]) -> None:
    row = _find_row(c, "P4a:apply2", _eeinit_pred("Land_Wreck_Ikarus", 6188.0, 7626.0))
    if row is None:
        return
    clone = dict(row)
    clone["net_id"] = "1:900"
    _add_row(c, "P4a:apply2", clone)


def _m_r3_p5_cargo_root(c: dict[str, Any]) -> None:
    _mutate_row(c, "P5:post_apply",
                lambda r: str(r.get("net_id")) == "1:180",
                lambda r: r.__setitem__("parent_net_id", "1:140"))


def _m_r3_p4b_zero_roots(c: dict[str, Any]) -> None:
    _remove_row(c, "P4b:apply", lambda r: int(r.get("sample_idx", -1)) == 0)


def _p_r3_s04_creature_walk_1m(c: dict[str, Any]) -> None:
    _mutate_row(c, "P4a:post_apply2",
                lambda r: str(r.get("class_name")) == "Animal_CervusElaphus",
                lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 1.0))


def _p_cl_v06_ce_loot_in_window(c: dict[str, Any]) -> None:
    _add_row(c, "P3:apply1", {"class_name": "Apple", "net_id": "0:5555", "parent_net_id": "",
                              "pos_x_m": 6200.0, "pos_y_m": 301.0, "pos_z_m": 7660.0,
                              "yaw_deg": 0.0, "tick_ms": 371100.0, "frame": 11,
                              "ai_agent_b": 0, "sample_idx": 0, "alive_b": 1,
                              "surface_y_m": 301.0})


def _m_r3_s02_early_extra_disks(c: dict[str, Any]) -> None:
    ids = _tag_job_ops(c, "P3:post_reset1:disk:")
    _shift_ops(c, ids, -3000.0)


def _n_r3_s02_extra_epoch_wrong(c: dict[str, Any]) -> None:
    ids = _tag_job_ops(c, "P3:post_reset1:disk:ani-01")
    _replace_epoch_for_ops(c, ids, "e9" * 16)


def _n_r3_s12_no_valid_position(c: dict[str, Any]) -> None:
    _remove_row(c, "P3:pre_reset", lambda r: str(r.get("net_id")) == "1:201")
    _remove_row(c, "P3:apply1", lambda r: str(r.get("net_id")) == "1:201")


def _m_r3_s07_rejected_acks(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/result":
            ev["http"] = 409
            if isinstance(ev.get("body"), dict):
                ev["body"]["ok"] = False


def _m_r3_s07_delivery_without_result(c: dict[str, Any]) -> None:
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 200000.0 <= float(x.get("t_ms") or 0.0) < 300000.0), None)
    if d is None:
        return
    rid = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    query = {"peer": "server", "inst": str(d.get("inst") or ""),
             "session": str(d.get("session") or ""),
             "conn": str(d.get("conn")), "deliver": "1"}
    tap.append({"t_ms": 204499.5, "dir": "req", "method": "GET", "path": "/poll", "req_id": rid,
                "query": query})
    tap.append({
        "t_ms": 204500.0, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
        "req_id": rid,
        "body": {"ok": True, "now_ms": 204500.0,
                 "ops": [{"op_id": d["op_id"], "session": d["session"], "conn": d["conn"],
                          "epoch": d["epoch"], "inst": d["inst"], "verb": "scene.apply",
                          "args": d["args"], "issued_ms": 204495.0, "ttl_ms": 5000}]}})
    _r6_sort(c)


def _n_r3_s08_bogus_obs(c: dict[str, Any]) -> None:
    ids = {str(d.get("op_id")) for d in _tap_deliveries(c, "state.read")}
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str((ev.get("body") or {}).get("op_id")) in ids:
            ev["body"]["read"]["obs"] = {"at": "now", "rows": [["bogus"]]}


def _p_cl_v01_state_read_without_obs(c: dict[str, Any]) -> None:
    ids = {str(d.get("op_id")) for d in _tap_deliveries(c, "state.read")}
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str((ev.get("body") or {}).get("op_id")) in ids:
            ev["body"]["read"].pop("obs", None)
            ev["body"]["read"]["sin_obs"] = True


def _m_r3_s11_pages_before_close(c: dict[str, Any]) -> None:
    for tag in ("P2:apply", "P3:apply1", "P3:apply2", "P4a:apply1", "P4a:apply2",
                "P4b:apply", "P5:cut", "P5:apply2", "P1:control", "P2n:apply"):
        start, pages = _job_events(c, tag)
        if start is None or not pages:
            continue
        deliver = float(start.get("t_ms") or 0.0) - 10.0
        for ev in pages:
            ev["t_ms"] = deliver + 1.0


def _shift_epoch_ticks(c: dict[str, Any], epoch: str, delta: float) -> None:
    keys = ("snap_tick_ms", "start_tick_ms", "tick_ms", "start_frame", "snap_frame")
    bridge = c["samples"]["bridge.jsonl"]
    # v1.3.11 (F-01): las páginas ya no llevan `server_epoch`; el epoch se identifica por la lectura
    # de arranque de su trabajo y las páginas se ligan por `job`.
    job_ids: set[str] = set()
    for ev in bridge:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        read = (ev.get("result") or {}).get("read")
        u = _unpack(read) if isinstance(read, dict) else None
        if not u:
            continue
        s = u[0]
        if "page_n" not in u[1] and str(s.get("server_epoch") or "") == epoch:
            job_ids.add(str(s.get("job") or ""))
    for ev in bridge:
        if ev.get("ev") != "result" or ev.get("http") != 200:
            continue
        read = (ev.get("result") or {}).get("read")
        u = _unpack(read) if isinstance(read, dict) else None
        if not u:
            continue
        s, n, rows = u
        if "page_n" not in n and str(s.get("server_epoch") or "") != epoch:
            continue
        if "page_n" in n and str(s.get("job") or "") not in job_ids:
            continue
        for k in keys:
            if isinstance(n.get(k), (int, float)):
                n[k] = float(n[k]) + delta
        for r in rows:
            if isinstance(r.get("tick_ms"), (int, float)):
                r["tick_ms"] = float(r["tick_ms"]) + delta
            if isinstance(r.get("frame"), (int, float)) and delta:
                r["frame"] = float(r["frame"]) + (delta / 1000.0)
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _p_cl_v02_ticks_per_epoch(c: dict[str, Any]) -> None:
    _shift_epoch_ticks(c, "e2" * 16, 5000.0)


def _m_r3_s06_overlap(c: dict[str, Any]) -> None:
    _witness_overlap(c)


def _m_r3_v05_p5_windows_overlap(c: dict[str, Any]) -> None:
    _edit_start_num(c, "P5:cut", "window_ms", 30000.0)


def _p_cl_v05_no_overlap(c: dict[str, Any]) -> None:
    # La ventana no llega al apply nuevo; las páginas ya están después del cierre (1500 ms).
    _edit_start_num(c, "P5:cut", "window_ms", 1500.0)
    _edit_start_args_num(c, "P5:cut", "window_ms", 1500.0)


def _p_cl_v07_p4c_two_epochs(c: dict[str, Any]) -> None:
    _edit_start_num(c, "P4c:post_reset", "snap_frame", 200.0)


def _m_r3_s10_confirmed_alive_e2(c: dict[str, Any]) -> None:
    row = _find_row(c, "P4c:pre_reset", lambda r: str(r.get("net_id")) == "1:301")
    if row is None:
        return
    _add_row(c, "P4c:post_reset", dict(row))


def _rename_op_in_window(c: dict[str, Any], old_id: str, new_id: str,
                         lo: float, hi: float) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        t = float(ev.get("t_ms") or 0.0)
        if not (lo <= t < hi):
            continue
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("op_id")) == old_id:
                    o["op_id"] = new_id
        if ev.get("dir") == "req" and ev.get("path") == "/result":
            b = ev.get("body") or {}
            if str(b.get("op_id")) == old_id:
                b["op_id"] = new_id
    for ev in c["samples"]["backend.jsonl"]:
        if ev.get("kind") == "op.state" and lo <= float(ev.get("t_ms") or 0.0) < hi and \
                str((ev.get("data") or {}).get("op_id")) == old_id:
            ev["data"]["op_id"] = new_id


def _p_v139_ids_repeated_across_sessions(c: dict[str, Any]) -> None:
    """Positiva v1.3.9: los ids de la API se repiten entre sesiones (op-1 en P2 y en P4a)."""
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 373000.0 <= float(x.get("t_ms") or 0.0) < 376000.0), None)
    if d is None:
        return
    _rename_op_in_window(c, str(d["op_id"]), "op-2", 373000.0, 376000.0)


def _m_v139_terminal_from_other_session(c: dict[str, Any]) -> None:
    """v1.3.9: quita el terminal de `op-1` en P2 (sesión s1); el mismo id tiene terminal en otras
    sesiones. Un evaluador que busque solo por `op_id` tomaría el ajeno."""
    c["samples"]["backend.jsonl"] = [
        ev for ev in c["samples"]["backend.jsonl"]
        if not (ev.get("kind") == "op.state" and
                200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0 and
                str((ev.get("data") or {}).get("op_id")) == "op-1")]


def _n_v139_rd_op_state(c: dict[str, Any]) -> None:
    """v1.3.9: un `op.state` con id `rd-N` no es del backend y rompe la traza."""
    d = next((x for x in _tap_deliveries(c, "state.read")
              if 550000.0 <= float(x.get("t_ms") or 0.0) < 610000.0), None)
    if d is None:
        return
    c["samples"]["backend.jsonl"].append({
        "seq": len(c["samples"]["backend.jsonl"]) + 1, "t_ms": 552000.0, "kind": "op.state",
        "data": {"op_id": str(d["op_id"]), "state": "observado", "origin": "backend",
                 "reason": None, "at_ms": 552000.0}})


def _p_v139_cut_result_resent_rejected(c: dict[str, Any]) -> None:
    """v1.3.9: el producto reenvía el resultado cortado al backend nuevo; lo rechaza con 409 y eso
    no cuenta como resolución ni rompe la traza."""
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 760000.0 <= float(x.get("t_ms") or 0.0) < 761500.0), None)
    if d is None:
        return
    oid = str(d["op_id"])
    sess = str(d["session"])
    epoch = "e3" * 16
    rid = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": 762300.0, "dir": "req", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid,
                "query": {"peer": "server", "inst": "e3" * 16, "session": sess,
                          "conn": str(d.get("conn") or 1)},
                "body": {"op_id": oid, "session": sess, "epoch": epoch, "status": "done",
                         "reason": "", "dup": False, "read": {}}})
    tap.append({"t_ms": 762302.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 409, "req_id": rid, "body": {"ok": False, "error": "hello_required"}})


def _p_v139_poll_409_after_restart(c: dict[str, Any]) -> None:
    """v1.3.9: un `/poll` con la sesión vieja tras un reinicio del backend recibe 409 y no rompe la
    traza. Se añade otro 409 al tramo de P4a."""
    d = next((x for x in _tap_deliveries(c, "scene.reset")
              if 490000.0 <= float(x.get("t_ms") or 0.0) < 550000.0), None)
    old = str(d["session"]) if d is not None else "c3" * 8
    rid = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": 551300.0, "dir": "req", "method": "GET", "path": "/poll", "req_id": rid,
                "query": {"peer": "server", "inst": "e1" * 16, "session": old,
                          "conn": "1"}})
    tap.append({"t_ms": 551302.0, "dir": "resp", "method": "GET", "path": "/poll",
                "http": 409, "req_id": rid, "body": {"ok": False, "error": "hello_required"}})


def _p_cl_v04_cut_no_terminal(c: dict[str, Any]) -> None:
    """v1.3.9: la op cortada de P5 no tiene terminal (ni siquiera el `pendiente` inicial); la
    partida sigue siendo buena."""
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 760000.0 <= float(x.get("t_ms") or 0.0) < 761500.0), None)
    if d is None:
        return
    oid = str(d["op_id"])
    c["samples"]["backend.jsonl"] = [
        ev for ev in c["samples"]["backend.jsonl"]
        if not (ev.get("kind") == "op.state" and
                760000.0 <= float(ev.get("t_ms") or 0.0) < 762000.0 and
                str((ev.get("data") or {}).get("op_id")) == oid)]


# ---------------------------------------------------------------------------------------------------
# T2f-3 (v1.3.10): ataques de la tanda. Casos r3_* y cl_*.
# ---------------------------------------------------------------------------------------------------

def _witness_row(cls: str, net: str, x: float, z: float, tick: float, *,
                 frame: int = 999, sample: int = 0, ai: int = 0, alive: int = 1,
                 parent: str = "") -> dict[str, Any]:
    return {"sample_idx": sample, "pos_x_m": float(x), "pos_y_m": 300.0, "pos_z_m": float(z),
            "yaw_deg": 0.0, "tick_ms": float(tick), "frame": float(frame),
            "ai_agent_b": float(ai), "alive_b": float(alive), "surface_y_m": 300.0,
            "class_name": cls, "net_id": net, "parent_net_id": parent}


def _copy_census_row(c: dict[str, Any], tag: str, pred: Callable[[dict[str, Any]], bool]
                     ) -> dict[str, Any] | None:
    row = _find_row(c, tag, pred)
    return copy.deepcopy(row) if row is not None else None


def _m_v139_two_sessions_one_segment(c: dict[str, Any]) -> None:
    """v1.3.10: dos sesiones distintas en las respuestas a `/hello` de un mismo tramo."""
    rid = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": 250000.0, "dir": "req", "method": "POST", "path": "/hello", "http": 200,
                "req_id": rid,
                "body": {"proto": "dsbx1", "peer": "server", "inst": "e1" * 16,
                         "epoch": "e1" * 16, "build": "diag", "world_size": 16384}})
    tap.append({"t_ms": 250005.0, "dir": "resp", "method": "POST", "path": "/hello", "http": 200,
                "req_id": rid,
                "body": {"ok": True, "session": "f6" * 8, "conn": 1, "lease_ms": 3000,
                         "hold_ms": 2000, "wire_cap": 3500}})


def _m_v139_session_repeats_between_segments(c: dict[str, Any]) -> None:
    """v1.3.10: la sesión nueva de un tramo repite la del tramo anterior."""
    tap = c["samples"]["bridge_tap.jsonl"]
    old = "c3" * 8
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/hello" and \
                551100.0 <= float(ev.get("t_ms") or 0.0) < 551110.0:
            ev["body"]["session"] = old
            return


def _p_r3_s05_p5_two_witnesses(c: dict[str, Any]) -> None:
    """S-05/V-03: P5 con los dos testigos y los 33 nacimientos del apply nuevo; un nacimiento de una
    clase ajena al documento es ruido y no entra en la generación (V-06)."""
    # Tick del motor del epoch e3 (no `t_ms`): 1000 + (760600 − 695400) = 66200.
    _add_row(c, "P5:cut", _witness_row("Apple", "1:999", 6280.0, 7680.0, 66200.0))


def _drop_state_read_in_window(c: dict[str, Any], lo: float, hi: float) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    ids: set[str] = set()
    req_ts: set[float] = set()
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            t = float(ev.get("t_ms") or 0.0)
            if lo <= t <= hi:
                for o in (ev.get("body") or {}).get("ops") or []:
                    if isinstance(o, dict) and str(o.get("verb")) == "state.read":
                        ids.add(str(o.get("op_id")))
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll" and \
                lo <= float(ev.get("t_ms") or 0.0) <= hi:
            b = ev.get("body") or {}
            b["ops"] = [o for o in (b.get("ops") or [])
                        if str(o.get("op_id")) not in ids]
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str((ev.get("body") or {}).get("op_id")) in ids and \
                lo <= float(ev.get("t_ms") or 0.0) <= hi:
            req_ts.add(float(ev.get("t_ms") or 0.0))
    c["samples"]["bridge_tap.jsonl"] = [
        ev for ev in tap
        if not (ev.get("dir") == "req" and ev.get("path") == "/result" and
                str((ev.get("body") or {}).get("op_id")) in ids and
                lo <= float(ev.get("t_ms") or 0.0) <= hi)
        and not (ev.get("dir") == "resp" and ev.get("path") == "/result" and
                 float(ev.get("t_ms") or 0.0) - 3.0 in req_ts)
    ]


def _m_r3_s05_no_reconciliation_before_apply2(c: dict[str, Any]) -> None:
    """S-05/V-03: sin la lectura de reconciliación antes de P5:apply2, F2P-09 es FALLA."""
    _drop_state_read_in_window(c, 762000.0, 764000.0)


def _m_r3_s05_k_zero(c: dict[str, Any]) -> None:
    """S-05/V-03: la generación cortada no nació (K = 0) → INCONCLUSO `p5_sin_efecto`."""
    _remove_row(c, "P5:cut", lambda r: True)


def _m_r3_s05_cut_result_accepted(c: dict[str, Any]) -> None:
    """S-05/V-03: un resultado aceptado de la op cortada → FALLA."""
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 760000.0 <= float(x.get("t_ms") or 0.0) < 761500.0), None)
    if d is None:
        return
    oid = str(d["op_id"])
    sess = str(d["session"])
    rid = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": 761600.0, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid,
                "query": {"peer": "server", "inst": "e3" * 16, "session": sess, "conn": "1"},
                "body": {"op_id": oid, "session": sess, "epoch": "e3" * 16, "status": "done",
                         "reason": "", "dup": False, "read": {}}})
    tap.append({"t_ms": 761603.0, "dir": "resp", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid, "body": {"ok": True}})


def _p_r3_v10_land_wreck_origin_1p3(c: dict[str, Any]) -> None:
    """V-10: un `Land_Wreck_*` con el origen a +1,3 m sigue apoyado (2,0 m de tolerancia)."""
    def lift(r: dict[str, Any]) -> None:
        r["pos_y_m"] = float(r["pos_y_m"]) + 1.3
    _mutate_row(c, "P2:apply", lambda r: str(r.get("net_id")) == "1:2" and
                int(r.get("sample_idx", -1)) == 0, lift)
    _mutate_row(c, "P2:post", lambda r: str(r.get("net_id")) == "1:2", lift)


def _m_r3_v10_creature_unsupported_0p15(c: dict[str, Any]) -> None:
    """V-10: una criatura a 0,15 m del suelo → FALLA en F2P-02."""
    cls = "ZmbM_FarmerFat_Brown"

    def lift(r: dict[str, Any]) -> None:
        r["pos_y_m"] = float(r["pos_y_m"]) + 0.15
    _mutate_row(c, "P2:apply", lambda r: str(r.get("class_name")) == cls and
                int(r.get("sample_idx", -1)) == 0, lift)
    _mutate_row(c, "P2:post", lambda r: str(r.get("class_name")) == cls, lift)


def _m_r3_s14_exact_0p5(c: dict[str, Any]) -> None:
    """S-14: un nacimiento a 0,5 m exactos no casa; F2P-02 (y F2P-01/F2P-04/F2P-13) fallan."""
    _move_object_birth(c, "1:2", 0.5, 0.0, 0.0)


def _set_census_health(c: dict[str, Any], max_hp: float, health_hp: float) -> None:
    tags = ("P2:post", "P2n:pre_reset", "P2n:post_apply", "P3:pre_reset", "P3:post_reset1",
            "P3:post_reset2", "P3c:pre_reset", "P3c:clean", "P4a:post_apply1", "P4a:pre_reset",
            "P4a:post_reset", "P4a:post_apply2", "P4b:post_apply", "P4c:pre_reset",
            "P5:post_apply")

    def set_health(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            r["max_hp"] = float(max_hp)
            r["health_hp"] = float(health_hp)
    for tag in tags:
        _edit_rows(c, tag, set_health)


def _p_v1310_product_hp_minus1(c: dict[str, Any]) -> None:
    """v1.3.10 (§5.3): lo que crea el producto con `-1/-1` sigue PASA."""
    _set_census_health(c, -1.0, -1.0)


def _p_v1310_product_hp_real(c: dict[str, Any]) -> None:
    """v1.3.10 (§5.3): lo que crea el producto con salud real sigue PASA."""
    _set_census_health(c, 100.0, 73.0)


def _m_r3_v16_ttl_missing(c: dict[str, Any]) -> None:
    """V-16: sin `params.ttl_ms` (ni en `identity.params`), F2P-04 es INCONCLUSO."""
    c["manifest"].get("params", {}).pop("ttl_ms", None)
    c["manifest"].get("identity", {}).get("params", {}).pop("ttl_ms", None)


def _m_r3_v16_outside_retention(c: dict[str, Any]) -> None:
    """V-16: la segunda entrega de P2 cae fuera de la retención → FALLA."""
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 200000.0 <= float(x.get("t_ms") or 0.0) < 210000.0), None)
    if d is None:
        return
    oid = str(d["op_id"])
    tap = c["samples"]["bridge_tap.jsonl"]
    old_t = 203000.0
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll" and \
                abs(float(ev.get("t_ms") or 0.0) - old_t) < 0.5:
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("op_id")) == oid:
                    ev["t_ms"] = 207000.0
                    break
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str((ev.get("body") or {}).get("op_id")) == oid and \
                204000.0 <= float(ev.get("t_ms") or 0.0) < 205000.0:
            ev["t_ms"] = 208000.0
        if ev.get("dir") == "resp" and ev.get("path") == "/result" and \
                abs(float(ev.get("t_ms") or 0.0) - 204003.0) < 0.5:
            ev["t_ms"] = 208003.0


def _m_r3_v18_no_cleanup_stimulus(c: dict[str, Any]) -> None:
    """V-18: sin el estímulo crudo de limpieza, F2P-06 es INCONCLUSO."""
    bridge = c["samples"]["bridge.jsonl"]
    ids = {str(ev.get("op_id") or "") for ev in bridge
           if ev.get("verb") == "per_cleanup_qa"}
    c["samples"]["bridge.jsonl"] = [ev for ev in bridge
                                    if str(ev.get("op_id") or "") not in ids]


def _p_r3_r04_creature_deletes_realistic(c: dict[str, Any]) -> None:
    """R-04: borrados de criaturas con Δt realista (4,4 s de snap) → PASA."""
    _edit_start_num(c, "P3:pre_reset", "snap_tick_ms", 378600.0)


def _m_r3_r04_infected_coverage_gap(c: dict[str, Any]) -> None:
    """R-04: un infectado cuyo disco no cubre `7 m/s · Δt + 2 m` → INCONCLUSO coverage_gap."""
    _edit_start_num(c, "P3:pre_reset", "snap_tick_ms", 378600.0)
    _remove_census_tag(c, "P3:post_reset1:disk:zmb-08")


def _m_r3_s16_creature_231_isolated(c: dict[str, Any]) -> None:
    """S-16: aísla la criatura `1:231` (ani-01) y conserva la cobertura de las demás.

    Los discos de ani-02 y ani-03, a 120 m, también cubrían a ani-01. Se retiran los tres y se
    vuelven a poner los de ani-02 y ani-03 a 30 m, que cubren a las suyas sin tapar `1:231`.
    """
    for tag in ("P3:post_reset1:disk:ani-01", "P3:post_reset1:disk:ani-02",
                "P3:post_reset1:disk:ani-03"):
        _remove_census_tag(c, tag)
    _add_census_disk(c, "P3:post_reset1:disk:ani-02", "e1" * 16, "e1" * 16,
                     384800.0, 383000.0, 90.0, (6076.0, 7698.0), 30.0, [])
    _add_census_disk(c, "P3:post_reset1:disk:ani-03", "e1" * 16, "e1" * 16,
                     384960.0, 383000.0, 91.0, (6160.0, 7673.0), 30.0, [])


def _p_r3_s13_ce_loot_zone(c: dict[str, Any]) -> None:
    """S-13/V-17: botín de la CE de una clase de la escena en la zona y no exacto → INCONCLUSO."""
    _add_row(c, "P3:apply1", _witness_row("Barrel_Yellow", "1:998", 6280.0, 7680.0, 372000.0))
    row = _copy_census_row(c, "P4b:post_restart",
                           lambda r: str(r.get("class_name")) == "Barrel_Yellow")
    if row is not None:
        row["net_id"] = "1:996"
        row["pos_x_m"] = 6164.0
        row["pos_z_m"] = 7663.0
        _add_row(c, "P4b:post_restart", row)


def _p_cl_v17_ce_object_in_window(c: dict[str, Any]) -> None:
    """V-17: un objeto de la CE de una clase de la escena en una ventana → INCONCLUSO, no FALLA."""
    _add_row(c, "P3:apply1", _witness_row("Barrel_Yellow", "1:998", 6280.0, 7680.0, 372000.0))


def _m_r3_s13_exact_reappearance(c: dict[str, Any]) -> None:
    """S-13: reaparición exacta en la última posición conocida (0,1 m y 1°) → FALLA en F2P-07."""
    row = _copy_census_row(c, "P4a:post_apply2",
                           lambda r: str(r.get("class_name")) == "WoodenCrate" and
                           abs(float(r.get("pos_x_m", 0.0)) - 6163.0) < 0.5 and
                           abs(float(r.get("pos_z_m", 0.0)) - 7663.0) < 0.5)
    if row is not None:
        _add_row(c, "P4b:post_restart", row)


def _m_r3_s13_scene_class_not_ce_near(c: dict[str, Any]) -> None:
    """S-13: clase de la escena 1 que la CE no crea, a menos de 2 m → FALLA en F2P-07."""
    row = _copy_census_row(c, "P4a:post_apply2",
                           lambda r: str(r.get("class_name")) == "SeaChest")
    if row is not None:
        row["net_id"] = "1:995"
        row["pos_x_m"] = 6141.0
        row["pos_z_m"] = 7676.0
        _add_row(c, "P4b:post_restart", row)


def _m_r3_v11_control_bad_mark(c: dict[str, Any]) -> None:
    """V-11: el control con la marca mal (ratio 0,73) no se acredita → INCONCLUSO."""
    _mutate_row(c, "P4b:control", lambda r: str(r.get("class_name")) == "Barrel_Yellow",
                lambda r: (r.__setitem__("max_hp", 100.0), r.__setitem__("health_hp", 73.0)))


def _m_r3_v11_control_in_zone(c: dict[str, Any]) -> None:
    """V-11: el control dentro de la zona de F2 no se acredita."""
    oid = None
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("verb") != "per_spawn_raw":
            continue
        u = _unpack(ev.get("args")) if isinstance(ev.get("args"), dict) else None
        if u and str(u[0].get("mode") or "") == "persistent_control":
            oid = str(ev.get("op_id") or "")
            break
    if oid is None:
        return
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "result" and str(ev.get("op_id")) == oid:
            read = ev["result"]["read"]
            u = _unpack(read)
            if not u:
                return
            s, n, rows = u
            n["pos_x_m"] = 6170.0
            n["pos_z_m"] = 7643.0
            ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


SOL_MUTANTS_R3: dict[str, dict[str, Any]] = {
    "v139_terminal_from_other_session": {"apply": _m_v139_terminal_from_other_session,
                                         "expected_exit_code": 2,
                                         "must_fail_status": {"F2P-01": "missing"},
                                         "allow_other_non_pass": True},
    "r3_S03_p3_reuses_p2_nets": {"apply": _m_r3_p3_reuses_p2_nets, "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-05": "fail"},
                                 "allow_other_non_pass": True},
    "r3_S03_p4a_keeps_old_root": {"apply": _m_r3_p4a_keeps_old_root, "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-08": "fail"},
                                  # El clon con `net_id` viejo es un nacimiento de más en la ventana
                                  # de P4a:apply2; F2P-13 también lo ve (es un extra real).
                                  "allowed_non_pass": {"F2P-13": ["fail"]}},
    "r3_S03_p5_cargo_root": {"apply": _m_r3_p5_cargo_root, "expected_exit_code": 1,
                             "must_fail_status": {"F2P-09": "fail"},
                             "allowed_non_pass": {}},
    "r3_S03_p4b_zero_roots": {"apply": _m_r3_p4b_zero_roots, "expected_exit_code": 1,
                              "must_fail_status": {"F2P-07": "fail"},
                              "allowed_non_pass": {}},
    "r3_S02_early_extra_disks": {"apply": _m_r3_s02_early_extra_disks, "expected_exit_code": 2,
                                 "must_fail_status": {"F2P-10": "missing"},
                                 "allow_other_non_pass": True},
    "r3_S07_rejected_acks": {"apply": _m_r3_s07_rejected_acks, "expected_exit_code": 1,
                             "must_fail_status": {"F2P-01": "fail"},
                             "allow_other_non_pass": True},
    "r3_S07_delivery_without_result": {"apply": _m_r3_s07_delivery_without_result,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-01": "fail"},
                                       "allow_other_non_pass": True},
    "r3_S11_pages_before_close": {"apply": _m_r3_s11_pages_before_close,
                                  "expected_exit_code": 2,
                                  "must_fail_status": {"F2P-13": "missing"},
                                  "allow_other_non_pass": True},
    "r3_S06_overlap": {"apply": _m_r3_s06_overlap, "expected_exit_code": 2,
                       "must_fail_status": {"F2P-13": "missing"},
                       "allow_other_non_pass": True},
    "r3_V05_p5_windows_overlap": {"apply": _m_r3_v05_p5_windows_overlap,
                                  "expected_exit_code": 2,
                                  "must_fail_status": {"F2P-13": "missing"},
                                  "allow_other_non_pass": True},
    "r3_S10_confirmed_alive_e2": {"apply": _m_r3_s10_confirmed_alive_e2,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-10": "fail"},
                                   "allowed_non_pass": {}},
    # T2f-3 (v1.3.10).
    "v139_two_sessions_one_segment": {"apply": _m_v139_two_sessions_one_segment,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-01": "fail"},
                                       "allow_other_non_pass": True},
    "v139_session_repeats_between_segments": {"apply": _m_v139_session_repeats_between_segments,
                                               "expected_exit_code": 1,
                                               "must_fail_status": {"F2P-08": "fail"},
                                               "allow_other_non_pass": True},
    "r3_S05_no_reconciliation_before_apply2": {"apply": _m_r3_s05_no_reconciliation_before_apply2,
                                                "expected_exit_code": 1,
                                                "must_fail_status": {"F2P-09": "fail"},
                                                "allowed_non_pass": {}},
    "r3_S05_k_zero": {"apply": _m_r3_s05_k_zero, "expected_exit_code": 2,
                       "must_fail_status": {"F2P-09": "missing"},
                       "allowed_non_pass": {}},
    "r3_S05_cut_result_accepted": {"apply": _m_r3_s05_cut_result_accepted,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-09": "fail"},
                                    "allowed_non_pass": {}},
    "r3_S13_exact_reappearance": {"apply": _m_r3_s13_exact_reappearance,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-07": "fail"},
                                   "allowed_non_pass": {}},
    "r3_S13_scene_class_not_ce_near": {"apply": _m_r3_s13_scene_class_not_ce_near,
                                        "expected_exit_code": 1,
                                        "must_fail_status": {"F2P-07": "fail"},
                                        "allowed_non_pass": {}},
    "r3_V11_control_missing_census": {"apply": _m_control_missing,
                                       "expected_exit_code": 2,
                                       "must_fail_status": {"F2P-07": "missing"},
                                       "allowed_non_pass": {}},
    "r3_V11_control_bad_mark": {"apply": _m_r3_v11_control_bad_mark,
                                 "expected_exit_code": 2,
                                 "must_fail_status": {"F2P-07": "missing"},
                                 "allowed_non_pass": {}},
    "r3_V11_control_in_zone": {"apply": _m_r3_v11_control_in_zone,
                                "expected_exit_code": 2,
                                "must_fail_status": {"F2P-07": "missing"},
                                "allowed_non_pass": {}},
    "r3_S14_exact_0p5": {"apply": _m_r3_s14_exact_0p5, "expected_exit_code": 1,
                          "must_fail_status": {"F2P-02": "fail"},
                          "allowed_non_pass": {"F2P-01": ["fail"], "F2P-04": ["fail"],
                                               "F2P-12": ["missing"], "F2P-13": ["fail"]}},
    "r3_V10_creature_unsupported_0p15": {"apply": _m_r3_v10_creature_unsupported_0p15,
                                          "expected_exit_code": 1,
                                          "must_fail_status": {"F2P-02": "fail"},
                                          "allowed_non_pass": {}},
    "r3_V16_ttl_missing": {"apply": _m_r3_v16_ttl_missing, "expected_exit_code": 2,
                            "must_fail_status": {"F2P-04": "missing"},
                            "allowed_non_pass": {}},
    "r3_V16_outside_retention": {"apply": _m_r3_v16_outside_retention,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-04": "fail"},
                                  "allowed_non_pass": {}},
    "r3_V18_no_cleanup_inconcluso": {"apply": _m_r3_v18_no_cleanup_stimulus,
                                      "expected_exit_code": 2,
                                      "must_fail_status": {"F2P-06": "missing"},
                                      "allowed_non_pass": {}},
    "r3_R04_infected_coverage_gap": {"apply": _m_r3_r04_infected_coverage_gap,
                                      "expected_exit_code": 2,
                                      "must_fail_status": {"F2P-10": "missing"},
                                      "allowed_non_pass": {}},
    "r3_S16_creature_231_isolated": {"apply": _m_r3_s16_creature_231_isolated,
                                      "expected_exit_code": 2,
                                      "must_fail_status": {"F2P-10": "missing"},
                                      "allowed_non_pass": {}},
}

SOL_NEGATIVES_R3: dict[str, dict[str, Any]] = {
    "r3_S01_page_epoch_empty": {"apply": _n_r3_page_epoch_empty},
    "r3_S01_delivery_instance": {"apply": _n_r3_delivery_instance},
    "r3_S01_stimulus_response_instance": {"apply": _n_r3_stimulus_response_instance},
    "r3_S01_selectors_zero": {"apply": _n_r3_selectors_zero},
    "r3_S01_rows_captured_n": {"apply": _n_r3_rows_captured_n},
    "r3_S09_parcial_sin_resultado": {"apply": _n_r3_s09_sin_resultado},
    "r3_S02_extra_epoch_wrong": {"apply": _n_r3_s02_extra_epoch_wrong},
    "r3_S12_no_valid_position": {"apply": _n_r3_s12_no_valid_position},
    "r3_S08_bogus_obs": {"apply": _n_r3_s08_bogus_obs},
    "v139_rd_op_state": {"apply": _n_v139_rd_op_state},
}

SOL_POSITIVES_R3: dict[str, dict[str, Any]] = {
    "r3_S04_creature_walk_1m": {"apply": _p_r3_s04_creature_walk_1m},
    "cl_V06_ce_loot_in_window": {"apply": _p_cl_v06_ce_loot_in_window},
    "cl_V01_state_read_without_obs": {"apply": _p_cl_v01_state_read_without_obs},
    "cl_V02_ticks_per_epoch": {"apply": _p_cl_v02_ticks_per_epoch},
    "cl_V05_no_overlap": {"apply": _p_cl_v05_no_overlap},
    "cl_V07_p4c_two_epochs": {"apply": _p_cl_v07_p4c_two_epochs},
    "cl_V04_cut_no_terminal": {"apply": _p_cl_v04_cut_no_terminal},
    "v139_ids_repeated_across_sessions": {"apply": _p_v139_ids_repeated_across_sessions},
    "v139_cut_result_resent_rejected": {"apply": _p_v139_cut_result_resent_rejected},
    "v139_poll_409_after_restart": {"apply": _p_v139_poll_409_after_restart},
    # T2f-3 (v1.3.10).
    "v1310_product_hp_minus1": {"apply": _p_v1310_product_hp_minus1},
    "v1310_product_hp_real": {"apply": _p_v1310_product_hp_real},
    "r3_S05_V03_p5_two_witnesses": {"apply": _p_r3_s05_p5_two_witnesses},
    "r3_V10_land_wreck_origin_1p3": {"apply": _p_r3_v10_land_wreck_origin_1p3},
    "r3_R04_creature_deletes_realistic": {"apply": _p_r3_r04_creature_deletes_realistic},
}

# Variantes "buenas" que dan INCONCLUSO (botín de la CE indistinguible): nunca FALLA.
SOL_INCONCLUSO_R3: dict[str, dict[str, Any]] = {
    "r3_S13_ce_loot_zone_inconcluso": {"apply": _p_r3_s13_ce_loot_zone,
                                       "must_missing": {"F2P-07": "posible_botin_ce",
                                                        "F2P-13": "posible_botin_ce"}},
    "cl_V17_ce_object_in_window_inconcluso": {"apply": _p_cl_v17_ce_object_in_window,
                                              "must_missing": {"F2P-13": "posible_botin_ce"}},
}

SOL_CASES_R3: dict[str, dict[str, Any]] = {
    "r3_S01_page_epoch_empty": {"kind": "negative", "name": "r3_S01_page_epoch_empty",
                                "check": "unbacked_rows (S-01)"},
    "r3_S01_delivery_instance": {"kind": "negative", "name": "r3_S01_delivery_instance",
                                 "check": "unbacked_rows (S-01)"},
    "r3_S01_stimulus_response_instance": {"kind": "negative",
                                          "name": "r3_S01_stimulus_response_instance",
                                          "check": "unbacked_rows (S-01)"},
    "r3_S01_selectors_zero": {"kind": "negative", "name": "r3_S01_selectors_zero",
                              "check": "unbacked_rows (S-01)"},
    "r3_S01_rows_captured_n": {"kind": "negative", "name": "r3_S01_rows_captured_n",
                               "check": "unbacked_rows (S-01)"},
    "r3_S09_parcial_sin_resultado": {"kind": "negative",
                                     "name": "r3_S09_parcial_sin_resultado",
                                     "check": "unbacked_rows (S-09)"},
    "cl_V04_cut_no_terminal": {"kind": "positive", "name": "cl_V04_cut_no_terminal",
                               "check": "PASA (V-04, v1.3.9)"},
    "v139_terminal_from_other_session": {"kind": "mutant",
                                         "name": "v139_terminal_from_other_session",
                                         "check": "F2P-01 (v1.3.9 punto 2)"},
    "v139_rd_op_state": {"kind": "negative", "name": "v139_rd_op_state",
                         "check": "traza (v1.3.9 punto 2/5)"},
    "v139_ids_repeated_across_sessions": {"kind": "positive",
                                          "name": "v139_ids_repeated_across_sessions",
                                          "check": "PASA (v1.3.9 punto 2)"},
    "v139_cut_result_resent_rejected": {"kind": "positive",
                                        "name": "v139_cut_result_resent_rejected",
                                        "check": "PASA (v1.3.9 punto 5)"},
    "v139_poll_409_after_restart": {"kind": "positive",
                                    "name": "v139_poll_409_after_restart",
                                    "check": "PASA (v1.3.9 punto 5)"},
    "r3_S03_p3_reuses_p2_nets": {"kind": "mutant", "name": "r3_S03_p3_reuses_p2_nets",
                                 "check": "F2P-05 (S-03)"},
    "r3_S03_p4a_keeps_old_root": {"kind": "mutant", "name": "r3_S03_p4a_keeps_old_root",
                                  "check": "F2P-08 (S-03)"},
    "r3_S03_p5_cargo_root": {"kind": "mutant", "name": "r3_S03_p5_cargo_root",
                             "check": "F2P-09 (S-03)"},
    "r3_S03_p4b_zero_roots": {"kind": "mutant", "name": "r3_S03_p4b_zero_roots",
                              "check": "F2P-07 (S-03)"},
    "r3_S04_creature_walk_1m": {"kind": "positive", "name": "r3_S04_creature_walk_1m",
                                "check": "PASA (S-04)"},
    "cl_V06_ce_loot_in_window": {"kind": "positive", "name": "cl_V06_ce_loot_in_window",
                                 "check": "PASA (V-06)"},
    "r3_S02_early_extra_disks": {"kind": "mutant", "name": "r3_S02_early_extra_disks",
                                 "check": "F2P-10 (S-02, V-08)"},
    "r3_S02_extra_epoch_wrong": {"kind": "negative", "name": "r3_S02_extra_epoch_wrong",
                                 "check": "unbacked_rows (S-02)"},
    "r3_S12_no_valid_position": {"kind": "negative", "name": "r3_S12_no_valid_position",
                                 "check": "unbacked_rows (S-12)"},
    "r3_S07_rejected_acks": {"kind": "mutant", "name": "r3_S07_rejected_acks",
                             "check": "traza (S-07, V-15)"},
    "r3_S07_delivery_without_result": {"kind": "mutant",
                                       "name": "r3_S07_delivery_without_result",
                                       "check": "traza (S-07)"},
    "cl_V01_state_read_without_obs": {"kind": "positive",
                                      "name": "cl_V01_state_read_without_obs",
                                      "check": "PASA (V-01, S-08)"},
    "r3_S08_bogus_obs": {"kind": "negative", "name": "r3_S08_bogus_obs",
                         "check": "F2P-08/F2P-09 (S-08)"},
    "r3_S11_pages_before_close": {"kind": "mutant", "name": "r3_S11_pages_before_close",
                                  "check": "F2P-13 (S-11)"},
    "r3_S06_overlap": {"kind": "mutant", "name": "r3_S06_overlap",
                       "check": "F2P-13 (S-06, V-02)"},
    "cl_V02_ticks_per_epoch": {"kind": "positive", "name": "cl_V02_ticks_per_epoch",
                               "check": "PASA (S-06, V-02)"},
    "r3_V05_p5_windows_overlap": {"kind": "mutant", "name": "r3_V05_p5_windows_overlap",
                                  "check": "F2P-13 (V-05)"},
    "cl_V05_no_overlap": {"kind": "positive", "name": "cl_V05_no_overlap",
                          "check": "PASA (V-05)"},
    "r3_S10_confirmed_alive_e2": {"kind": "mutant", "name": "r3_S10_confirmed_alive_e2",
                                   "check": "F2P-10 (S-10, V-07)"},
    "cl_V07_p4c_two_epochs": {"kind": "positive", "name": "cl_V07_p4c_two_epochs",
                              "check": "PASA (S-10, V-07)"},
    # T2f-3 (v1.3.10).
    "v139_two_sessions_one_segment": {"kind": "mutant",
                                      "name": "v139_two_sessions_one_segment",
                                      "check": "traza (v1.3.10)"},
    "v139_session_repeats_between_segments": {"kind": "mutant",
                                              "name": "v139_session_repeats_between_segments",
                                              "check": "traza (v1.3.10)"},
    "v1310_product_hp_minus1": {"kind": "positive", "name": "v1310_product_hp_minus1",
                                "check": "PASA (§5.3 v1.3.10)"},
    "v1310_product_hp_real": {"kind": "positive", "name": "v1310_product_hp_real",
                              "check": "PASA (§5.3 v1.3.10)"},
    "r3_S05_V03_p5_two_witnesses": {"kind": "positive",
                                    "name": "r3_S05_V03_p5_two_witnesses",
                                    "check": "PASA (S-05, V-03)"},
    "r3_S05_no_reconciliation_before_apply2": {"kind": "mutant",
                                               "name": "r3_S05_no_reconciliation_before_apply2",
                                               "check": "F2P-09 (S-05, V-03)"},
    "r3_S05_k_zero": {"kind": "mutant", "name": "r3_S05_k_zero",
                      "check": "F2P-09 (S-05, V-03)"},
    "r3_S05_cut_result_accepted": {"kind": "mutant", "name": "r3_S05_cut_result_accepted",
                                   "check": "F2P-09 (S-05, V-03)"},
    "r3_S13_ce_loot_zone_inconcluso": {"kind": "positive",
                                       "name": "r3_S13_ce_loot_zone_inconcluso",
                                       "check": "INCONCLUSO posible_botin_ce (S-13)"},
    "r3_S13_exact_reappearance": {"kind": "mutant", "name": "r3_S13_exact_reappearance",
                                  "check": "F2P-07 (S-13)"},
    "r3_S13_scene_class_not_ce_near": {"kind": "mutant", "name": "r3_S13_scene_class_not_ce_near",
                                       "check": "F2P-07 (S-13)"},
    "r3_V11_control_missing_census": {"kind": "mutant", "name": "r3_V11_control_missing_census",
                                      "check": "F2P-07 (V-11)"},
    "r3_V11_control_bad_mark": {"kind": "mutant", "name": "r3_V11_control_bad_mark",
                                "check": "F2P-07 (V-11)"},
    "r3_V11_control_in_zone": {"kind": "mutant", "name": "r3_V11_control_in_zone",
                               "check": "F2P-07 (V-11)"},
    "cl_V17_ce_object_in_window_inconcluso": {"kind": "positive",
                                              "name": "cl_V17_ce_object_in_window_inconcluso",
                                              "check": "INCONCLUSO posible_botin_ce (V-17)"},
    "r3_S14_exact_0p5": {"kind": "mutant", "name": "r3_S14_exact_0p5",
                         "check": "F2P-02 (S-14)"},
    "r3_V10_land_wreck_origin_1p3": {"kind": "positive",
                                     "name": "r3_V10_land_wreck_origin_1p3",
                                     "check": "PASA (V-10)"},
    "r3_V10_creature_unsupported_0p15": {"kind": "mutant",
                                         "name": "r3_V10_creature_unsupported_0p15",
                                         "check": "F2P-02 (V-10)"},
    "r3_V16_ttl_missing": {"kind": "mutant", "name": "r3_V16_ttl_missing",
                           "check": "F2P-04 (V-16)"},
    "r3_V16_outside_retention": {"kind": "mutant", "name": "r3_V16_outside_retention",
                                 "check": "F2P-04 (V-16)"},
    "r3_V18_no_cleanup_inconcluso": {"kind": "mutant",
                                      "name": "r3_V18_no_cleanup_inconcluso",
                                      "check": "F2P-06 (V-18)"},
    "r3_R04_creature_deletes_realistic": {"kind": "positive",
                                          "name": "r3_R04_creature_deletes_realistic",
                                          "check": "PASA (R-04)"},
    "r3_R04_infected_coverage_gap": {"kind": "mutant", "name": "r3_R04_infected_coverage_gap",
                                     "check": "F2P-10 (R-04)"},
    "r3_S16_creature_231_isolated": {"kind": "mutant", "name": "r3_S16_creature_231_isolated",
                                     "check": "F2P-10 (S-16)"},
}

SOL_CASES.update(SOL_CASES_R3)

# ===================================================================================================
# T2f-4 (v1.3.11): casos de Sol r4 (F-01 a F-13) y A-01. Prefijo r4_.
# ===================================================================================================

def _edit_start_read(c: dict[str, Any], tag: str,
                     fn: Callable[[dict[str, Any], dict[str, Any]], None]) -> None:
    start, _pages = _job_events(c, tag)
    if start is None:
        return
    read = start["result"]["read"]
    u = _unpack(read)
    if not u:
        return
    s, n, rows = u
    fn(s, n)
    start["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _set_job_inst(c: dict[str, Any], tag: str, inst: str) -> None:
    ids = _tag_job_ops(c, tag)
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id") or "") in ids:
            ev["inst"] = inst


def _blank_start_epoch(c: dict[str, Any], tag: str) -> None:
    def fn(s: dict[str, Any], n: dict[str, Any]) -> None:
        s["server_epoch"] = ""
    _edit_start_read(c, tag, fn)


def _probe_ver(c: dict[str, Any]) -> str:
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "hello" and isinstance(ev.get("args"), dict):
            return str(ev["args"].get("probe_ver") or "dsbx-qa1+0123456789abcdef")
    return "dsbx-qa1+0123456789abcdef"


def _add_bridge_hello(c: dict[str, Any], peer: str, inst: str, t: float) -> None:
    pv = _probe_ver(c)
    c["samples"]["bridge.jsonl"].append({
        "t_ms": float(t), "ev": "hello", "peer": peer, "inst": inst, "http": 200, "ok": True,
        "args": {"proto": "qa0", "build": "diag", "probe_ver": pv, "inst": inst, "peer": peer}})


def _shift_events(c: dict[str, Any], lo: float, hi: float, delta: float,
                  skip_ids: set[str] | None = None) -> None:
    skip = skip_ids or set()
    for name in ("bridge.jsonl", "bridge_tap.jsonl", "backend.jsonl", "scene_del.jsonl"):
        for ev in c["samples"][name]:
            if str(ev.get("op_id") or "") in skip:
                continue
            t = ev.get("t_ms")
            if isinstance(t, (int, float)) and lo <= float(t) < hi:
                ev["t_ms"] = float(t) + delta


def _shift_job_snap(c: dict[str, Any], tag: str, delta: float) -> None:
    def fn(s: dict[str, Any], n: dict[str, Any]) -> None:
        if _finite_m(n.get("snap_tick_ms")):
            n["snap_tick_ms"] = float(n["snap_tick_ms"]) + delta
    _edit_start_read(c, tag, fn)
    _start, pages = _job_events(c, tag)
    for ev in pages:
        read = ev["result"]["read"]
        u = _unpack(read)
        if not u:
            continue
        s, n, rows = u
        if _finite_m(n.get("snap_tick_ms")):
            n["snap_tick_ms"] = float(n["snap_tick_ms"]) + delta
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _finite_m(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _make_census_1m_empty(c: dict[str, Any], tag: str) -> None:
    start, pages = _job_events(c, tag)
    if start is None:
        return
    oid = str(start.get("op_id") or "")
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id") or "") != oid or ev.get("ev") not in ("enq", "deliver"):
            continue
        au = _unpack(ev.get("args"))
        if not au:
            continue
        a_s, a_n, _ = au
        a_n["radius_m"] = 1.0
        ev["args"] = wire.pack_payload(scalars_str=a_s, scalars_num=a_n)
    read = start["result"]["read"]
    u = _unpack(read)
    if u:
        s, n, rows = u
        n["radius_m"] = 1.0
        n["rows_captured_n"] = 0.0
        start["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], [], read.get("has"))
    for ev in pages:
        rd = ev["result"]["read"]
        uu = _unpack(rd)
        if not uu:
            continue
        s, n, rows = uu
        n["radius_m"] = 1.0
        n["rows_total_n"] = 0.0
        n["pages_n"] = 0.0
        ev["result"]["read"] = _repack(s, n, rd["ncol"], rd["scol"], [], rd.get("has"))


def _birth_nets(c: dict[str, Any], tag: str) -> set[str]:
    _start, pages = _job_events(c, tag)
    out: set[str] = set()
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if int(r.get("sample_idx", -1)) == 0:
                out.add(str(r.get("net_id")))
    return out


def _remove_delete_nets(c: dict[str, Any], nets: set[str]) -> None:
    c["samples"]["scene_del.jsonl"] = [
        ev for ev in c["samples"]["scene_del.jsonl"]
        if f"{int(ev.get('net_high', 0))}:{int(ev.get('net_low', 0))}" not in nets]


def _set_all_tap_results(c: dict[str, Any], fn: Callable[[dict[str, Any]], None]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/result":
            fn(ev)


def _last_terminal(c: dict[str, Any], op_id: str) -> dict[str, Any] | None:
    cands = [ev for ev in c["samples"]["backend.jsonl"]
             if ev.get("kind") == "op.state" and
             str((ev.get("data") or {}).get("op_id")) == op_id]
    if not cands:
        return None
    return max(cands, key=lambda ev: float(ev.get("t_ms") or 0.0))


def _remove_terminal(c: dict[str, Any], op_id: str, lo: float, hi: float) -> None:
    c["samples"]["backend.jsonl"] = [
        ev for ev in c["samples"]["backend.jsonl"]
        if not (ev.get("kind") == "op.state" and
                str((ev.get("data") or {}).get("op_id")) == op_id and
                lo <= float(ev.get("t_ms") or 0.0) < hi and
                str((ev.get("data") or {}).get("state")) != "pendiente")]


# --- F-01 / A-01 ---

def _n_r4_f01_start_epoch_empty(c: dict[str, Any]) -> None:
    """F-01: la lectura de arranque de un censo con `server_epoch` vacío."""
    _blank_start_epoch(c, "P3:pre_reset")


def _n_r4_a01_result_other_inst(c: dict[str, Any]) -> None:
    """A-01: un `result` recibido mientras el bridge tenía aceptada otra instancia del peer."""
    start, _pages = _job_events(c, "P2:apply")
    if start is None:
        return
    t = float(start.get("t_ms") or 0.0)
    other = "9" * 32
    _add_bridge_hello(c, "server", other, t - 1.0)
    _add_bridge_hello(c, "server", "e1" * 16, t + 1.0)


# --- F-02 ---

def _m_r4_f02_disks_delayed_20s(c: dict[str, Any]) -> None:
    """F-02: los discos de después del primer reset de P3 y los eventos siguientes, 20 s después."""
    disk_ids = _tag_job_ops(c, "P3:post_reset1:disk:")
    disk_ts = [float(ev.get("t_ms") or 0.0) for ev in c["samples"]["bridge.jsonl"]
               if str(ev.get("op_id") or "") in disk_ids and isinstance(ev.get("t_ms"), (int, float))]
    max_t = max(disk_ts) if disk_ts else 383500.0
    # Los censos posteriores de la parte P3 se desplazan con sus snapshots.
    for tag in ("P3:pre_reset2", "P3:post_reset2"):
        _shift_job_snap(c, tag, 20000.0)
    _shift_events(c, max_t + 1.0, 480000.0, 20000.0, skip_ids=disk_ids)
    _shift_events(c, -1.0, 480000.0, 20000.0, skip_ids=None) if False else None
    # Los discos se desplazan ellos mismos y sus snapshots.
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id") or "") in disk_ids and isinstance(ev.get("t_ms"), (int, float)):
            ev["t_ms"] = float(ev["t_ms"]) + 20000.0
    for ev in c["samples"]["bridge.jsonl"]:
        if str(ev.get("op_id") or "") not in disk_ids or ev.get("ev") != "result":
            continue
        read = (ev.get("result") or {}).get("read")
        u = _unpack(read) if isinstance(read, dict) else None
        if not u:
            continue
        s, n, rows = u
        if _finite_m(n.get("snap_tick_ms")):
            n["snap_tick_ms"] = float(n["snap_tick_ms"]) + 20000.0
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _m_r4_f02_lid_relabel_231(c: dict[str, Any]) -> None:
    """F-02: en el caso aislado de `1:231`, solo su `lid` pasa a `obj-01`."""
    _m_r3_s16_creature_231_isolated(c)
    for ev in c["samples"]["scene_del.jsonl"]:
        if (int(ev.get("net_high", 0)), int(ev.get("net_low", 0))) == (1, 231):
            ev["lid"] = "obj-01"


# --- F-03 ---

def _m_r4_f03_no_p5_restart(c: dict[str, Any]) -> None:
    """F-03: sin el reinicio del backend de P5; sesión vieja e ids libres para la lectura y el apply."""
    tap = c["samples"]["bridge_tap.jsonl"]
    backend = c["samples"]["backend.jsonl"]
    backend[:] = [ev for ev in backend
                  if not (ev.get("kind") == "restart" and
                          str((ev.get("data") or {}).get("target")) == "backend" and
                          abs(float(ev.get("t_ms") or 0.0) - 762000.0) < 1.0)]
    tap[:] = [ev for ev in tap
              if not (762000.0 <= float(ev.get("t_ms") or 0.0) <= 762200.0)]
    # La lectura y el apply nuevo usan la sesión vieja (s4) y el registro de esa sesión.
    old_sess = "d4" * 8
    req_by_rid = {e.get("req_id"): e for e in tap
                  if e.get("dir") == "req" and isinstance(e.get("req_id"), int)}
    regs = []
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/hello" and ev.get("http") == 200:
            b = ev.get("body") or {}
            if b.get("ok") is True and str(b.get("session") or "") == old_sess:
                r = req_by_rid.get(ev.get("req_id"))
                if r is not None and str((r.get("body") or {}).get("peer") or "") == "server":
                    inst = str((r.get("body") or {}).get("inst") or "")
                    if inst:
                        regs.append((float(ev.get("t_ms") or 0.0), inst,
                                     str(b.get("conn") or "1")))
    if regs:
        _, reg_inst, reg_conn = max(regs, key=lambda x: x[0])
    else:
        reg_inst, reg_conn = "", ""
    read_ids: set[str] = set()
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("verb")) == "state.read":
                    read_ids.add(str(o.get("op_id")))
    for ev in tap:
        t = float(ev.get("t_ms") or 0.0)
        if t < 761500.0:
            continue
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("op_id")) in read_ids:
                    o["session"] = old_sess
                    o["op_id"] = "rd-2"
                    o["inst"] = reg_inst
                    o["conn"] = int(reg_conn) if reg_conn.isdigit() else reg_conn
        if ev.get("dir") == "req" and ev.get("path") == "/result":
            b = ev.get("body") or {}
            if str(b.get("op_id")) in read_ids:
                b["session"] = old_sess
                b["op_id"] = "rd-2"
                q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
                q["session"] = old_sess
                q["inst"] = reg_inst
                q["conn"] = reg_conn
                ev["query"] = q
    # Renombra el apply nuevo a op-7 en s4 y su lectura a rd-2.
    for ev in tap:
        t = float(ev.get("t_ms") or 0.0)
        if t < 763000.0:
            continue
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("verb")) == "scene.apply":
                    o["op_id"] = "op-7"
                    o["session"] = old_sess
                    o["inst"] = reg_inst
                    o["conn"] = int(reg_conn) if reg_conn.isdigit() else reg_conn
        if ev.get("dir") == "req" and ev.get("path") == "/result":
            b = ev.get("body") or {}
            if str(b.get("op_id")) == "op-1":
                b["op_id"] = "op-7"
                b["session"] = old_sess
                q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
                q["session"] = old_sess
                q["inst"] = reg_inst
                q["conn"] = reg_conn
                ev["query"] = q
    # Las peticiones de /poll de esas respuestas van en la sesión de sus ops, con su registro.
    for ev in tap:
        if ev.get("dir") != "req" or ev.get("path") != "/poll":
            continue
        q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
        if float(ev.get("t_ms") or 0.0) >= 761500.0 and str(q.get("session") or "") == "e5" * 8:
            q["session"] = old_sess
            q["inst"] = reg_inst
            q["conn"] = reg_conn
            ev["query"] = q
    for ev in backend:
        if float(ev.get("t_ms") or 0.0) >= 763000.0 and ev.get("kind") == "op.state":
            if str((ev.get("data") or {}).get("op_id")) == "op-1":
                ev["data"]["op_id"] = "op-7"
    for ev in backend:
        if ev.get("kind") == "api.observation" and float(ev.get("t_ms") or 0.0) >= 766000.0:
            gen = ((ev.get("data") or {}).get("observation") or {}).get("generation")
            if isinstance(gen, dict) and str(gen.get("op_id")) == "op-1":
                gen["op_id"] = "op-7"


def _m_r4_f03_p5_restart_unbacked(c: dict[str, Any]) -> None:
    """F-03: reinicio del backend de P5 que no se acredita (sin `/hello` de sesión nueva).

    El reinicio va después del último apply de P5: no hay entregas posteriores en el tramo, así que
    la traza no se rompe y F2P-09 da INCONCLUSO `restart_unbacked` (f2p_eval:3629).
    """
    c["samples"]["backend.jsonl"].append({
        "seq": len(c["samples"]["backend.jsonl"]) + 1, "t_ms": 767500.0,
        "kind": "restart", "data": {"target": "backend", "epoch": "e3" * 16}})
    _r6_sort(c)


def _m_r4_f03_read_before_restart(c: dict[str, Any]) -> None:
    """F-03: el reinicio sigue en 762000, pero la lectura va antes, en la sesión vieja."""
    tap = c["samples"]["bridge_tap.jsonl"]
    ids: set[str] = set()
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("verb")) == "state.read":
                    ids.add(str(o.get("op_id")))
    old_sess = "d4" * 8
    for ev in tap:
        t = float(ev.get("t_ms") or 0.0)
        if t < 761500.0:
            continue
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("op_id")) in ids:
                    o["session"] = old_sess
                    o["op_id"] = "rd-2"
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str((ev.get("body") or {}).get("op_id")) in ids:
            ev["body"]["session"] = old_sess
            ev["body"]["op_id"] = "rd-2"
            q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
            q["session"] = old_sess
            ev["query"] = q
            if abs(t - 763000.0) < 1.0:
                ev["t_ms"] = 761800.0
        if ev.get("dir") == "resp" and ev.get("path") == "/result" and \
                abs(t - 763003.0) < 1.0:
            ev["t_ms"] = 761803.0
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("op_id")) == "rd-2" and \
                        abs(t - 762500.0) < 1.0:
                    ev["t_ms"] = 761600.0


def _m_r4_f03_cut_births_after_cut(c: dict[str, Any]) -> None:
    """F-03: todos los nacimientos de `P5:cut` después del corte, dentro de su ventana."""
    _start, pages = _job_events(c, "P5:cut")
    for ev in pages:
        read = ev["result"]["read"]
        u = _unpack(read)
        if not u:
            continue
        s, n, rows = u
        for r in rows:
            si = int(r.get("sample_idx", -1))
            r["tick_ms"] = 67200.0 + 33.0 * si
        ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


def _m_r4_f03_p3_no_reconciliation(c: dict[str, Any]) -> None:
    """F-03: sin las dos lecturas de reconciliación de P3."""
    _drop_state_read_in_window(c, 370000.0, 480000.0)


# --- F-04 ---

def _m_r4_f04_result_inst_epoch(c: dict[str, Any]) -> None:
    """F-04: todos los `/result` con instancia y epoch distintos de los de su entrega."""
    def fn(ev: dict[str, Any]) -> None:
        q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
        q["inst"] = "ff" * 16
        ev["query"] = q
        b = ev.get("body") or {}
        b["epoch"] = "ff" * 16
    _set_all_tap_results(c, fn)


def _m_r4_f04_query_body_session(c: dict[str, Any]) -> None:
    """F-04: la sesión del query distinta de la del cuerpo."""
    def fn(ev: dict[str, Any]) -> None:
        q = ev.get("query") if isinstance(ev.get("query"), dict) else {}
        q["session"] = "f0" * 8
        ev["query"] = q
    _set_all_tap_results(c, fn)


def _m_r4_f04_hello_rejected(c: dict[str, Any]) -> None:
    """F-04: todos los `/hello` del producto rechazados (HTTP 200, `ok: false`)."""
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/hello":
            ev["body"]["ok"] = False


def _m_r4_f04_ack_ok_string(c: dict[str, Any]) -> None:
    """F-04: acuses con `ok: "false"` (cadena, no booleano)."""
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/result":
            ev["body"]["ok"] = "false"


def _m_r4_f04_foreign_rejected_cut_id(c: dict[str, Any]) -> None:
    """F-04: en P2, un resultado rechazado de una sesión desconocida con el `op_id` de la op cortada."""
    tap = c["samples"]["bridge_tap.jsonl"]
    # El id de la op cortada de P5 es el último apply de la sesión s4 antes del cut.
    cut_id = "op-6"
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll" and \
                abs(float(ev.get("t_ms") or 0.0) - 761000.0) < 1.0:
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("verb")) == "scene.apply":
                    cut_id = str(o.get("op_id"))
    rid = _r15c_rid(c)
    tap.append({"t_ms": 250000.0, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid,
                "query": {"peer": "server", "inst": "f0" * 16, "session": "f0" * 8, "conn": "1"},
                "body": {"op_id": cut_id, "session": "f0" * 8, "epoch": "e1" * 16,
                         "status": "error", "reason": "hello_required", "dup": False, "read": {}}})
    tap.append({"t_ms": 250003.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 409, "req_id": rid, "body": {"ok": False}})


# --- F-05 ---

def _m_r4_f05_p2_create_failed(c: dict[str, Any]) -> None:
    """F-05: P2 con resultados y terminal `create_failed`, filas geométricas intactas."""
    def fn(ev: dict[str, Any]) -> None:
        b = ev.get("body") or {}
        if 200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0:
            b["status"] = "rejected"
            b["reason"] = "create_failed"
    _set_all_tap_results(c, fn)
    cands = [ev for ev in c["samples"]["backend.jsonl"]
             if ev.get("kind") == "op.state" and
             str((ev.get("data") or {}).get("op_id")) == "op-1" and
             200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0]
    if cands:
        st = max(cands, key=lambda ev: float(ev.get("t_ms") or 0.0))
        st["data"]["state"] = "fallido"
        st["data"]["reason"] = "create_failed"


def _m_r4_f05_invented_state(c: dict[str, Any]) -> None:
    """F-05: el terminal de P2 pasa a `observado_inventado` (no es terminal)."""
    cands = [ev for ev in c["samples"]["backend.jsonl"]
             if ev.get("kind") == "op.state" and
             str((ev.get("data") or {}).get("op_id")) == "op-1" and
             200000.0 <= float(ev.get("t_ms") or 0.0) < 300000.0]
    if cands:
        st = max(cands, key=lambda ev: float(ev.get("t_ms") or 0.0))
        st["data"]["state"] = "observado_inventado"
        st["data"]["reason"] = None


# --- F-06 ---

def _m_r4_f06_p4a_apply1_zero(c: dict[str, Any]) -> None:
    """F-06: `P4a:apply1` no crea nada; se quitan nacimientos, filas posteriores y borrados."""
    nets = _birth_nets(c, "P4a:apply1")
    _remove_row(c, "P4a:apply1", lambda r: True)
    for tag in ("P4a:post_apply1", "P4a:pre_reset"):
        _remove_row(c, tag, lambda r: str(r.get("net_id")) in nets)
    _remove_delete_nets(c, nets)


def _m_r4_f06_p4b_vanish(c: dict[str, Any]) -> None:
    """F-06: los nacimientos de P4b desaparecen antes del censo posterior, sin borrados."""
    nets = _birth_nets(c, "P4b:apply")
    _remove_row(c, "P4b:post_apply", lambda r: str(r.get("net_id")) in nets)


def _m_r4_f06_p5_obj180_moved(c: dict[str, Any]) -> None:
    """F-06: el objeto nuevo `1:180` de P5, desplazado 10 m en el censo final."""
    def change(r: dict[str, Any]) -> None:
        r["pos_x_m"] = float(r["pos_x_m"]) + 10.0
    _mutate_row(c, "P5:post_apply", lambda r: str(r.get("net_id")) == "1:180", change)


# --- F-07 ---

def _m_r4_f07_201_in_post_reset2(c: dict[str, Any]) -> None:
    """F-07: `1:201`, de la generación de P3, en `P3:post_reset2`."""
    row = _copy_census_row(c, "P3:pre_reset", lambda r: str(r.get("net_id")) == "1:201")
    if row is not None:
        _add_row(c, "P3:post_reset2", row)


def _m_r4_f07_cleanup_apple_alive(c: dict[str, Any]) -> None:
    """F-07: la limpieza declara 2 y el `Apple` ajeno sigue en el censo posterior."""
    row = _copy_census_row(c, "P3c:pre_reset", lambda r: str(r.get("net_id")) == "1:238")
    if row is not None:
        _add_row(c, "P3c:clean", row)


# --- F-08 ---

def _m_r4_f08_control_prev_instance(c: dict[str, Any]) -> None:
    """F-08: `P4b:control` con la instancia y el epoch anteriores al reinicio."""
    ids = _tag_job_ops(c, "P4b:control")
    _set_job_inst(c, "P4b:control", "e1" * 16)
    _replace_epoch_for_ops(c, ids, "e1" * 16)


def _m_r4_f08_invalid_component(c: dict[str, Any]) -> None:
    """F-08: un componente inválido en `P4c:pre_reset`."""
    _add_census_disk(c, "P4c:pre_reset:disk:extra", "", "9" * 32, 690700.0, 690600.0, 61.0,
                     (6170.0, 7643.0), 60.0, [])


def _m_r4_f08_census_1m_empty(c: dict[str, Any]) -> None:
    """F-08: los censos de después del reinicio, pedidos a 1 m y vacíos."""
    _make_census_1m_empty(c, "P4b:post_restart")
    _make_census_1m_empty(c, "P4c:post_restart")


def _m_r4_f08_control_created_minus1(c: dict[str, Any]) -> None:
    """F-08: la creación del control con `-1/-1`."""
    oid = None
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "enq" and ev.get("verb") == "per_spawn_raw":
            u = _unpack(ev.get("args"))
            if u and str(u[0].get("mode") or "") == "persistent_control":
                oid = str(ev.get("op_id"))
                break
    if oid is None:
        return
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "result" and str(ev.get("op_id")) == oid:
            read = ev["result"]["read"]
            u = _unpack(read)
            if not u:
                continue
            s, n, rows = u
            n["max_hp"] = -1.0
            n["health_hp"] = -1.0
            ev["result"]["read"] = _repack(s, n, read["ncol"], read["scol"], rows, read.get("has"))


# --- F-09 ---

def _m_r4_f09_infected_moved_10m(c: dict[str, Any]) -> None:
    """F-09: el infectado de `P4a:post_apply2` en (6242, 7610), copiado al censo posterior al
    reinicio con id nuevo y 10 m más allá."""
    row = _copy_census_row(c, "P4a:post_apply2",
                           lambda r: str(r.get("class_name")) == "ZmbM_FarmerFat_Brown")
    if row is None:
        return
    row["net_id"] = "1:990"
    row["pos_x_m"] = float(row["pos_x_m"]) + 10.0
    row["alive_b"] = 1.0
    row["ai_agent_b"] = 1.0
    row["parent_net_id"] = ""
    _add_row(c, "P4b:post_restart", row)


# --- F-10 ---

def _m_r4_f10_fireplace_child_p2(c: dict[str, Any]) -> None:
    """F-10: en P2, un `Fireplace` en el cargo de `Barrel_Yellow`, con muestras 0 a 3."""
    barrel = _find_row(c, "P2:apply",
                       lambda r: str(r.get("class_name")) == "Barrel_Yellow" and
                       int(r.get("sample_idx", -1)) == 0)
    if barrel is None:
        return
    parent = str(barrel.get("net_id"))
    x = float(barrel.get("pos_x_m"))
    z = float(barrel.get("pos_z_m"))
    for s in range(4):
        _add_row(c, "P2:apply", _witness_row("Fireplace", "1:777", x, z,
                                             201000.0 + 33.0 * s, frame=500 + s, sample=s,
                                             parent=parent))
    row = _copy_census_row(c, "P2:post", lambda r: str(r.get("net_id")) == parent)
    if row is not None:
        row["class_name"] = "Fireplace"
        row["net_id"] = "1:777"
        row["parent_net_id"] = parent
        row["loc_kind"] = "cargo"
        row["slot_name"] = "cargo"
        _add_row(c, "P2:post", row)


# --- F-11 (positiva) ---

def _p_r4_f11_e2_renumbered(c: dict[str, Any]) -> None:
    """F-11: las raíces de e2, de `1:301…333` a `1:434…466`, con censos y borrados coherentes."""
    mapping = {f"1:{301 + i}": f"1:{434 + i}" for i in range(33)}

    def rec(x: Any) -> Any:
        if isinstance(x, str):
            return mapping.get(x, x)
        if isinstance(x, list):
            return [rec(v) for v in x]
        if isinstance(x, dict):
            return {k: rec(v) for k, v in x.items()}
        return x

    c["samples"] = rec(c["samples"])
    # Los borrados guardan el net como enteros `net_high`/`net_low`, no como cadena.
    for ev in c["samples"]["scene_del.jsonl"]:
        hi = int(ev.get("net_high", 0))
        lo = int(ev.get("net_low", 0))
        if hi == 1 and 301 <= lo <= 333:
            ev["net_low"] = lo + 133


# --- F-12 (inconclusas) ---

def _add_ce_extra(c: dict[str, Any], witness_tag: str, census_tag: str) -> None:
    rows = []
    _start, pages = _job_events(c, witness_tag)
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if u:
            rows.extend(u[2])
    tick = max((float(r.get("tick_ms") or 0.0) for r in rows), default=0.0) + 33.0
    frame = max((float(r.get("frame") or 0.0) for r in rows), default=0.0) + 1.0
    _add_row(c, witness_tag, _witness_row("Barrel_Yellow", "1:888", 6280.0, 7680.0, tick,
                                          frame=int(frame)))
    base = _copy_census_row(c, census_tag,
                            lambda r: str(r.get("class_name")) == "Barrel_Yellow")
    if base is not None:
        base["net_id"] = "1:888"
        base["pos_x_m"] = 6280.0
        base["pos_z_m"] = 7680.0
        base["pos_y_m"] = 300.0
        base["surface_y_m"] = 300.0
        base["parent_net_id"] = ""
        _add_row(c, census_tag, base)


def _p_r4_f12_ce_extra_p2(c: dict[str, Any]) -> None:
    _add_ce_extra(c, "P2:apply", "P2:post")


def _p_r4_f12_ce_extra_p4a(c: dict[str, Any]) -> None:
    _add_ce_extra(c, "P4a:apply2", "P4a:post_apply2")


def _p_r4_f12_ce_extra_p4b(c: dict[str, Any]) -> None:
    _add_ce_extra(c, "P4b:apply", "P4b:post_apply")


def _p_r4_f12_ce_extra_p5(c: dict[str, Any]) -> None:
    _add_ce_extra(c, "P5:apply2", "P5:post_apply")


# --- F-13 ---

def _n_r4_f13_p4a_real_survivor_401(c: dict[str, Any]) -> None:
    """F-13: un superviviente real de `1:401` en el censo de P4a, no un nacimiento nuevo."""
    row = _copy_census_row(c, "P4a:post_apply1", lambda r: str(r.get("net_id")) == "1:401")
    if row is not None:
        _add_row(c, "P4a:post_apply2", row)


def _n_r4_f13_terminal_other_session(c: dict[str, Any]) -> None:
    """F-13: sin el terminal de `(d4…, op-3)`, el segundo apply de P4a."""
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 555000.0 <= float(x.get("t_ms") or 0.0) < 610000.0 and
              float(x.get("t_ms") or 0.0) >= 559000.0), None)
    if d is None:
        return
    _remove_terminal(c, str(d["op_id"]), 555000.0, 610000.0)


SOL_MUTANTS_R4: dict[str, dict[str, Any]] = {
    "r4_F02_disks_delayed_20s": {"apply": _m_r4_f02_disks_delayed_20s,
                                 "expected_exit_code": 2,
                                 "must_fail_status": {"F2P-10": "missing"},
                                 "allowed_non_pass": {}},
    "r4_F02_lid_relabel_231": {"apply": _m_r4_f02_lid_relabel_231,
                                "expected_exit_code": 2,
                                "must_fail_status": {"F2P-10": "missing"},
                                "allowed_non_pass": {}},
    "r4_F03_no_p5_restart": {"apply": _m_r4_f03_no_p5_restart,
                              "expected_exit_code": 1,
                              "must_fail_status": {"F2P-09": "fail"},
                              "must_detail": {"F2P-09": "tap_trace_mismatch"},
                              "allowed_non_pass": {}},
    "r4_F03_p5_restart_unbacked": {"apply": _m_r4_f03_p5_restart_unbacked,
                                   "expected_exit_code": 2,
                                   "must_fail_status": {"F2P-09": "missing"},
                                   "must_detail": {"F2P-09": "restart_unbacked"},
                                   "allow_other_non_pass": True},
    "r4_F03_read_before_restart": {"apply": _m_r4_f03_read_before_restart,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-09": "fail"},
                                    "allowed_non_pass": {}},
    "r4_F03_cut_births_after_cut": {"apply": _m_r4_f03_cut_births_after_cut,
                                     "expected_exit_code": 2,
                                     "must_fail_status": {"F2P-09": "missing"},
                                     "allowed_non_pass": {}},
    "r4_F03_p3_no_reconciliation": {"apply": _m_r4_f03_p3_no_reconciliation,
                                     "expected_exit_code": 1,
                                     "must_fail_status": {"F2P-05": "fail"},
                                     "allowed_non_pass": {}},
    "r4_F04_result_inst_epoch": {"apply": _m_r4_f04_result_inst_epoch,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-01": "fail"},
                                  "allow_other_non_pass": True},
    "r4_F04_query_body_session": {"apply": _m_r4_f04_query_body_session,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-01": "fail"},
                                   "allow_other_non_pass": True},
    "r4_F04_hello_rejected": {"apply": _m_r4_f04_hello_rejected,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-01": "fail"},
                               "allow_other_non_pass": True},
    "r4_F04_ack_ok_string": {"apply": _m_r4_f04_ack_ok_string,
                              "expected_exit_code": 1,
                              "must_fail_status": {"F2P-01": "fail"},
                              "allow_other_non_pass": True},
    "r4_F04_foreign_rejected_cut_id": {"apply": _m_r4_f04_foreign_rejected_cut_id,
                                        "expected_exit_code": 1,
                                        "must_fail_status": {"F2P-01": "fail",
                                                             "F2P-04": "fail"},
                                        "allowed_non_pass": {}},
    "r4_F05_p2_create_failed": {"apply": _m_r4_f05_p2_create_failed,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-01": "fail"},
                                 "allowed_non_pass": {}},
    "r4_F05_invented_state": {"apply": _m_r4_f05_invented_state,
                               "expected_exit_code": 2,
                               "must_fail_status": {"F2P-01": "missing"},
                               "allow_other_non_pass": True},
    "r4_F06_p4a_apply1_zero": {"apply": _m_r4_f06_p4a_apply1_zero,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-08": "fail"},
                                "allowed_non_pass": {}},
    "r4_F06_p4b_vanish": {"apply": _m_r4_f06_p4b_vanish,
                           "expected_exit_code": 1,
                           "must_fail_status": {"F2P-07": "fail"},
                           "allowed_non_pass": {}},
    "r4_F06_p5_obj180_moved": {"apply": _m_r4_f06_p5_obj180_moved,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-09": "fail"},
                                "allowed_non_pass": {}},
    "r4_F07_201_in_post_reset2": {"apply": _m_r4_f07_201_in_post_reset2,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-05": "fail"},
                                   "allowed_non_pass": {}},
    "r4_F07_cleanup_apple_alive": {"apply": _m_r4_f07_cleanup_apple_alive,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-06": "fail"},
                                    "allowed_non_pass": {}},
    "r4_F08_control_prev_instance": {"apply": _m_r4_f08_control_prev_instance,
                                      "expected_exit_code": 2,
                                      "must_fail_status": {"F2P-07": "missing"},
                                      "allowed_non_pass": {}},
    "r4_F08_invalid_component": {"apply": _m_r4_f08_invalid_component,
                                  "expected_exit_code": 2,
                                  "must_fail_status": {"F2P-10": "missing"},
                                  "allowed_non_pass": {}},
    "r4_F08_census_1m_empty": {"apply": _m_r4_f08_census_1m_empty,
                                "expected_exit_code": 2,
                                "must_fail_status": {"F2P-07": "missing"},
                                "allowed_non_pass": {}},
    "r4_F08_control_created_minus1": {"apply": _m_r4_f08_control_created_minus1,
                                       "expected_exit_code": 2,
                                       "must_fail_status": {"F2P-07": "missing"},
                                       "allowed_non_pass": {}},
    "r4_F09_infected_moved_10m": {"apply": _m_r4_f09_infected_moved_10m,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-07": "fail"},
                                   "allowed_non_pass": {}},
    "r4_F10_fireplace_child_p2": {"apply": _m_r4_f10_fireplace_child_p2,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-13": "fail"},
                                   "allowed_non_pass": {}},
}

SOL_POSITIVES_R4: dict[str, dict[str, Any]] = {
    "r4_F11_e2_renumbered": {"apply": _p_r4_f11_e2_renumbered},
}

SOL_INCONCLUSO_R4: dict[str, dict[str, Any]] = {
    "r4_F12_ce_extra_p2": {"apply": _p_r4_f12_ce_extra_p2,
                           "must_missing": {"F2P-01": "posible_botin_ce",
                                            "F2P-04": "posible_botin_ce",
                                            "F2P-13": "posible_botin_ce"}},
    "r4_F12_ce_extra_p4a": {"apply": _p_r4_f12_ce_extra_p4a,
                            "must_missing": {"F2P-08": "posible_botin_ce",
                                             "F2P-13": "posible_botin_ce"}},
    "r4_F12_ce_extra_p4b": {"apply": _p_r4_f12_ce_extra_p4b,
                            "must_missing": {"F2P-07": "posible_botin_ce",
                                             "F2P-13": "posible_botin_ce"}},
    "r4_F12_ce_extra_p5": {"apply": _p_r4_f12_ce_extra_p5,
                           "must_missing": {"F2P-09": "posible_botin_ce",
                                            "F2P-13": "posible_botin_ce"}},
}

SOL_NEGATIVES_R4: dict[str, dict[str, Any]] = {
    "r4_F01_start_epoch_empty": {"apply": _n_r4_f01_start_epoch_empty,
                                  "expected_exit_code": 2,
                                  "must_fail_status": {"F2P-05": "missing"},
                                  "must_detail": {"F2P-05": "missing_p3_census"},
                                  "must_reason": "unbacked_rows"},
    "r4_A01_result_other_inst": {"apply": _n_r4_a01_result_other_inst,
                                  "expected_exit_code": 2,
                                  "must_fail_status": {"F2P-01": "missing"},
                                  "must_detail": {"F2P-01": "unbacked_rows"}},
    "r4_F13_p4a_real_survivor_401": {"apply": _n_r4_f13_p4a_real_survivor_401,
                                      "expected_exit_code": 1,
                                      "must_fail_status": {"F2P-08": "fail"},
                                      "must_detail": {"F2P-08": "leftovers"}},
    "r4_F13_terminal_other_session": {"apply": _n_r4_f13_terminal_other_session,
                                       "expected_exit_code": 2,
                                       "must_fail_status": {"F2P-08": "missing"},
                                       "must_detail": {"F2P-08": "missing_restart_or_apply"}},
}

# F-13: el motivo de cada caso r4_*, no solo el estado. Los motivos salen del verde del oráculo
# v1.3.11 (out_red_r4.txt); la prueba los exige en el `detail` de esa comprobación.
_R4_MUTANT_DETAILS: dict[str, dict[str, str]] = {
    "r4_F02_disks_delayed_20s": {"F2P-10": "coverage_gap"},
    "r4_F02_lid_relabel_231": {"F2P-10": "coverage_gap"},
    "r4_F03_no_p5_restart": {"F2P-09": "tap_trace_mismatch"},
    "r4_F03_p5_restart_unbacked": {"F2P-09": "restart_unbacked"},
    "r4_F03_read_before_restart": {"F2P-09": "no_reconciliation_before_scene"},
    "r4_F03_cut_births_after_cut": {"F2P-09": "p5_sin_efecto"},
    "r4_F03_p3_no_reconciliation": {"F2P-05": "no_reconciliation_after_restart"},
    "r4_F04_result_inst_epoch": {"F2P-01": "tap_trace_mismatch"},
    "r4_F04_query_body_session": {"F2P-01": "tap_trace_mismatch"},
    "r4_F04_hello_rejected": {"F2P-01": "tap_trace_mismatch"},
    "r4_F04_ack_ok_string": {"F2P-01": "tap_trace_mismatch"},
    "r4_F04_foreign_rejected_cut_id": {"F2P-01": "tap_trace_mismatch"},
    "r4_F05_p2_create_failed": {"F2P-01": "create_failed"},
    "r4_F05_invented_state": {"F2P-01": "unbacked_rows"},
    "r4_F06_p4a_apply1_zero": {"F2P-08": "apply1_unmatched"},
    "r4_F06_p4b_vanish": {"F2P-07": "census_missing"},
    "r4_F06_p5_obj180_moved": {"F2P-09": "pose"},
    "r4_F07_201_in_post_reset2": {"F2P-05": "retained_set2"},
    "r4_F07_cleanup_apple_alive": {"F2P-06": "cleanup_still_alive"},
    "r4_F08_control_prev_instance": {"F2P-07": "persistent_control_missing"},
    "r4_F08_invalid_component": {"F2P-10": "unbacked_rows"},
    "r4_F08_census_1m_empty": {"F2P-07": "missing_census"},
    "r4_F08_control_created_minus1": {"F2P-07": "persistent_control_missing"},
    "r4_F09_infected_moved_10m": {"F2P-07": "creature_reappeared"},
    "r4_F10_fireplace_child_p2": {"F2P-13": "Fireplace"},
}
for _n, _d in _R4_MUTANT_DETAILS.items():
    SOL_MUTANTS_R4[_n]["must_detail"] = _d

SOL_CASES_R4: dict[str, dict[str, Any]] = {
    "r4_F01_start_epoch_empty": {"kind": "negative", "name": "r4_F01_start_epoch_empty",
                                 "check": "unbacked_rows (F-01)"},
    "r4_A01_result_other_inst": {"kind": "negative", "name": "r4_A01_result_other_inst",
                                 "check": "unbacked_rows (A-01)"},
    "r4_F02_disks_delayed_20s": {"kind": "mutant", "name": "r4_F02_disks_delayed_20s",
                                 "check": "F2P-10 coverage_gap (F-02)"},
    "r4_F02_lid_relabel_231": {"kind": "mutant", "name": "r4_F02_lid_relabel_231",
                               "check": "F2P-10 kind_mismatch/coverage_gap (F-02)"},
    "r4_F03_no_p5_restart": {"kind": "mutant", "name": "r4_F03_no_p5_restart",
                             "check": "F2P-09 tap_trace_mismatch (F-03)"},
    "r4_F03_p5_restart_unbacked": {"kind": "mutant", "name": "r4_F03_p5_restart_unbacked",
                                   "check": "F2P-09 restart_unbacked (F-03)"},
    "r4_F03_read_before_restart": {"kind": "mutant", "name": "r4_F03_read_before_restart",
                                   "check": "F2P-09 no_reconciliation_before_new_apply (F-03)"},
    "r4_F03_cut_births_after_cut": {"kind": "mutant", "name": "r4_F03_cut_births_after_cut",
                                    "check": "F2P-09 p5_sin_efecto (F-03)"},
    "r4_F03_p3_no_reconciliation": {"kind": "mutant", "name": "r4_F03_p3_no_reconciliation",
                                    "check": "F2P-05 FALLA (F-03)"},
    "r4_F04_result_inst_epoch": {"kind": "mutant", "name": "r4_F04_result_inst_epoch",
                                 "check": "traza (F-04)"},
    "r4_F04_query_body_session": {"kind": "mutant", "name": "r4_F04_query_body_session",
                                  "check": "traza (F-04)"},
    "r4_F04_hello_rejected": {"kind": "mutant", "name": "r4_F04_hello_rejected",
                              "check": "traza (F-04)"},
    "r4_F04_ack_ok_string": {"kind": "mutant", "name": "r4_F04_ack_ok_string",
                             "check": "traza (F-04)"},
    "r4_F04_foreign_rejected_cut_id": {"kind": "mutant",
                                        "name": "r4_F04_foreign_rejected_cut_id",
                                        "check": "traza (F-04)"},
    "r4_F05_p2_create_failed": {"kind": "mutant", "name": "r4_F05_p2_create_failed",
                                "check": "F2P-01 (F-05)"},
    "r4_F05_invented_state": {"kind": "mutant", "name": "r4_F05_invented_state",
                              "check": "no terminal (F-05)"},
    "r4_F06_p4a_apply1_zero": {"kind": "mutant", "name": "r4_F06_p4a_apply1_zero",
                               "check": "F2P-08 (F-06)"},
    "r4_F06_p4b_vanish": {"kind": "mutant", "name": "r4_F06_p4b_vanish",
                          "check": "F2P-07 (F-06)"},
    "r4_F06_p5_obj180_moved": {"kind": "mutant", "name": "r4_F06_p5_obj180_moved",
                               "check": "F2P-09 (F-06)"},
    "r4_F07_201_in_post_reset2": {"kind": "mutant", "name": "r4_F07_201_in_post_reset2",
                                  "check": "F2P-05 (F-07)"},
    "r4_F07_cleanup_apple_alive": {"kind": "mutant", "name": "r4_F07_cleanup_apple_alive",
                                   "check": "F2P-06 (F-07)"},
    "r4_F08_control_prev_instance": {"kind": "mutant",
                                      "name": "r4_F08_control_prev_instance",
                                      "check": "F2P-07 INCONCLUSO (F-08)"},
    "r4_F08_invalid_component": {"kind": "mutant", "name": "r4_F08_invalid_component",
                                 "check": "F2P-10 unbacked_rows (F-08)"},
    "r4_F08_census_1m_empty": {"kind": "mutant", "name": "r4_F08_census_1m_empty",
                               "check": "F2P-07 INCONCLUSO disco no prescrito (F-08)"},
    "r4_F08_control_created_minus1": {"kind": "mutant",
                                       "name": "r4_F08_control_created_minus1",
                                       "check": "F2P-07 INCONCLUSO (F-08)"},
    "r4_F09_infected_moved_10m": {"kind": "mutant", "name": "r4_F09_infected_moved_10m",
                                  "check": "F2P-07 (F-09)"},
    "r4_F10_fireplace_child_p2": {"kind": "mutant", "name": "r4_F10_fireplace_child_p2",
                                  "check": "F2P-13 (F-10)"},
    "r4_F11_e2_renumbered": {"kind": "positive", "name": "r4_F11_e2_renumbered",
                             "check": "PASA (F-11)"},
    "r4_F12_ce_extra_p2": {"kind": "positive", "name": "r4_F12_ce_extra_p2",
                           "check": "INCONCLUSO posible_botin_ce (F-12)"},
    "r4_F12_ce_extra_p4a": {"kind": "positive", "name": "r4_F12_ce_extra_p4a",
                            "check": "INCONCLUSO posible_botin_ce (F-12)"},
    "r4_F12_ce_extra_p4b": {"kind": "positive", "name": "r4_F12_ce_extra_p4b",
                            "check": "INCONCLUSO posible_botin_ce (F-12)"},
    "r4_F12_ce_extra_p5": {"kind": "positive", "name": "r4_F12_ce_extra_p5",
                           "check": "INCONCLUSO posible_botin_ce (F-12)"},
    "r4_F13_p4a_real_survivor_401": {"kind": "negative",
                                      "name": "r4_F13_p4a_real_survivor_401",
                                      "check": "F2P-08 leftovers (F-13)"},
    "r4_F13_terminal_other_session": {"kind": "negative",
                                       "name": "r4_F13_terminal_other_session",
                                       "check": "F2P-08 INCONCLUSO (F-13)"},
}

SOL_CASES.update(SOL_CASES_R4)

# ===================================================================================================
# T2f-5 (v1.3.12): W-01 a W-11. Prefijo r5_.
# ===================================================================================================

def _r5_part_window(c: dict[str, Any], part: str) -> tuple[float, float]:
    for p in (c.get("manifest", {}).get("f2p", {}) or {}).get("parts") or []:
        if isinstance(p, dict) and p.get("name") == part:
            return float(p.get("start_t_ms") or 0.0), float(p.get("end_t_ms") or 1e12)
    return 0.0, 1e12


def _r5_stage_delivery(c: dict[str, Any], part: str, verb: str, index: int) -> dict[str, Any] | None:
    lo, hi = _r5_part_window(c, part)
    ds = [d for d in _tap_deliveries(c, verb) if lo <= float(d.get("t_ms") or 0.0) <= hi]
    ds.sort(key=lambda d: float(d.get("t_ms") or 0.0))
    return ds[index] if len(ds) > index else None


def _r5_set_stage_terminal(c: dict[str, Any], part: str, verb: str, index: int,
                           variant: str) -> None:
    d = _r5_stage_delivery(c, part, verb, index)
    if d is None:
        return
    oid = str(d["op_id"])
    sess = str(d["session"])
    lo, hi = _r5_part_window(c, part)
    if variant == "fallido":
        state = "fallido"
        reason = "create_failed" if verb == "scene.apply" else "lectura_no_cumple"
        status = "rejected" if verb == "scene.apply" else "error"
        for ev in c["samples"]["bridge_tap.jsonl"]:
            if ev.get("dir") != "req" or ev.get("path") != "/result":
                continue
            b = ev.get("body") or {}
            if str(b.get("op_id")) == oid and str(b.get("session")) == sess and \
                    lo <= float(ev.get("t_ms") or 0.0) <= hi:
                b["status"] = status
                b["reason"] = reason
    else:
        state = "observado"
        reason = "reconciliada"
    cands = [ev for ev in c["samples"]["backend.jsonl"]
             if ev.get("kind") == "op.state" and
             str((ev.get("data") or {}).get("op_id")) == oid and
             lo <= float(ev.get("t_ms") or 0.0) <= hi and
             str((ev.get("data") or {}).get("state")) != "pendiente"]
    if not cands:
        return
    st = max(cands, key=lambda ev: float(ev.get("t_ms") or 0.0))
    st["data"]["state"] = state
    st["data"]["reason"] = reason


_R5_STAGES: list[tuple[str, str, str, int, str, bool]] = [
    ("P2", "apply", "scene.apply", 0, "F2P-01", True),
    ("P3", "apply1", "scene.apply", 0, "F2P-05", True),
    ("P3", "apply2", "scene.apply", 1, "F2P-05", True),
    ("P3", "reset1", "scene.reset", 0, "F2P-05", False),
    ("P3", "reset2", "scene.reset", 1, "F2P-05", False),
    ("P3c", "clean", "scene.reset", 0, "F2P-06", True),
    ("P4a", "apply1", "scene.apply", 0, "F2P-08", True),
    ("P4a", "reset", "scene.reset", 0, "F2P-08", True),
    ("P4a", "apply2", "scene.apply", 1, "F2P-08", True),
    ("P4b", "apply", "scene.apply", 0, "F2P-07", True),
    ("P4c", "reset", "scene.reset", 0, "F2P-07", True),
    ("P5", "apply2", "scene.apply", 1, "F2P-09", True),
]

_R5_STAGE_RED: dict[tuple[str, str], int] = {
    ("P2", "apply"): 1, ("P3", "apply1"): 1, ("P3", "apply2"): 1,
    ("P3", "reset1"): 1, ("P3", "reset2"): 1, ("P3c", "clean"): 0,
    ("P4a", "apply1"): 0, ("P4a", "reset"): 0, ("P4a", "apply2"): 0,
    ("P4b", "apply"): 1, ("P4c", "reset"): 0, ("P5", "apply2"): 0,
}

SOL_MUTANTS_R5: dict[str, dict[str, Any]] = {}
for _part, _stage, _verb, _idx, _check, _obs in _R5_STAGES:
    _variants = ["fallido"] + (["reconciliada"] if _obs else [])
    for _variant in _variants:
        _name = f"r5_stage_{_part}_{_stage}_{_variant}"
        _detail = "fallido/create_failed" if _variant == "fallido" and _verb == "scene.apply" \
            else "fallido/lectura_no_cumple" if _variant == "fallido" else "observado/reconciliada"
        SOL_MUTANTS_R5[_name] = {
            "apply": (lambda c, p=_part, v=_verb, i=_idx, var=_variant:
                      _r5_set_stage_terminal(c, p, v, i, var)),
            "expected_exit_code": 1,
            "must_fail_status": {_check: "fail"},
            "must_detail": {_check: _detail},
            "red_exit": _R5_STAGE_RED[(_part, _stage)],
        }


# --- W-02: reconciliación tras cada reinicio del backend y antes de la primera entrega de escena ---

def _r5_state_read_events(c: dict[str, Any], part: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    lo, hi = _r5_part_window(c, part)
    tap = c["samples"]["bridge_tap.jsonl"]
    dels = [ev for ev in tap if ev.get("dir") == "resp" and ev.get("path") == "/poll" and
            lo <= float(ev.get("t_ms") or 0.0) <= hi]
    ids = set()
    for ev in dels:
        for o in (ev.get("body") or {}).get("ops") or []:
            if isinstance(o, dict) and str(o.get("verb")) == "state.read":
                ids.add(str(o.get("op_id")))
    res = [ev for ev in tap if ev.get("dir") == "req" and ev.get("path") == "/result" and
           str((ev.get("body") or {}).get("op_id")) in ids]
    acks = [ev for ev in tap if ev.get("dir") == "resp" and ev.get("path") == "/result" and
            abs(float(ev.get("t_ms") or 0.0) - (float(res[0].get("t_ms") or 0.0) + 3.0)) < 1.0] if res else []
    return dels, res, acks


def _r5_drop_read(c: dict[str, Any], part: str) -> None:
    lo, hi = _r5_part_window(c, part)
    tap = c["samples"]["bridge_tap.jsonl"]
    ids = set()
    for ev in tap:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll" and \
                lo <= float(ev.get("t_ms") or 0.0) <= hi:
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("verb")) == "state.read":
                    ids.add(str(o.get("op_id")))
    keep = []
    drop_ack = False
    for ev in tap:
        t = float(ev.get("t_ms") or 0.0)
        b = ev.get("body") or {}
        if ev.get("dir") == "resp" and ev.get("path") == "/poll" and lo <= t <= hi:
            b["ops"] = [o for o in (b.get("ops") or [])
                        if not (isinstance(o, dict) and str(o.get("op_id")) in ids)]
            keep.append(ev)
            continue
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str(b.get("op_id")) in ids and lo <= t <= hi:
            drop_ack = True
            continue
        if drop_ack and ev.get("dir") == "resp" and ev.get("path") == "/result":
            drop_ack = False
            continue
        keep.append(ev)
    c["samples"]["bridge_tap.jsonl"] = keep


def _r5_move_read(c: dict[str, Any], part: str, which: int, new_deliver: float) -> None:
    lo, hi = _r5_part_window(c, part)
    tap = c["samples"]["bridge_tap.jsonl"]
    reads = [ev for ev in tap if ev.get("dir") == "resp" and ev.get("path") == "/poll" and
             lo <= float(ev.get("t_ms") or 0.0) <= hi and
             any(isinstance(o, dict) and str(o.get("verb")) == "state.read"
                 for o in (ev.get("body") or {}).get("ops") or [])]
    if len(reads) <= which:
        return
    d = reads[which]
    oid = None
    sess = None
    for o in (d.get("body") or {}).get("ops") or []:
        if isinstance(o, dict) and str(o.get("verb")) == "state.read":
            oid = str(o.get("op_id"))
            sess = str(o.get("session") or "")
    if oid is None:
        return
    d["t_ms"] = float(new_deliver)
    old_result_t = None
    for ev in tap:
        b = ev.get("body") or {}
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str(b.get("op_id")) == oid and str(b.get("session") or "") == sess:
            old_result_t = float(ev.get("t_ms") or 0.0)
            ev["t_ms"] = float(new_deliver) + 100.0
    if old_result_t is not None:
        for ev in tap:
            if ev.get("dir") == "resp" and ev.get("path") == "/result" and \
                    old_result_t < float(ev.get("t_ms") or 0.0) < old_result_t + 10.0:
                ev["t_ms"] = float(new_deliver) + 103.0
                break
    tap.sort(key=lambda e: float(e.get("t_ms") or 0.0))


def _r5_add_reset_before(c: dict[str, Any], part: str, t_deliver: float, t_result: float,
                         session: str, inst: str, epoch: str, op_id: str) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    rid_poll = _r15c_rid(c)
    rid_result = rid_poll + 1
    tap.append({"t_ms": t_deliver - 0.5, "dir": "req", "method": "GET", "path": "/poll",
                "req_id": rid_poll,
                "query": {"peer": "server", "inst": inst, "session": session, "conn": "1",
                          "deliver": "1"}})
    tap.append({"t_ms": t_deliver, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid_poll,
                "body": {"ok": True, "now_ms": t_deliver, "ops": [
                    {"op_id": op_id, "session": session, "conn": 1, "epoch": epoch,
                     "inst": inst, "verb": "scene.reset",
                     "args": {"f2": 1, "doc_id": "d-00000001",
                              "if_pending": {"session": "", "op_id": ""}},
                     "issued_ms": t_deliver - 50, "ttl_ms": 5000}]}})
    tap.append({"t_ms": t_result, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid_result,
                "query": {"peer": "server", "inst": inst, "session": session, "conn": "1"},
                "body": {"op_id": op_id, "session": session, "epoch": epoch, "status": "done",
                         "reason": "", "dup": False, "read": {}}})
    tap.append({"t_ms": t_result + 3.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result, "body": {"ok": True}})
    be = c["samples"]["backend.jsonl"]
    be.append({"seq": len(be) + 1, "t_ms": t_deliver - 100.0, "kind": "op.state",
               "data": {"op_id": op_id, "state": "pendiente", "reason": None, "origin": "backend"}})
    be.append({"seq": len(be) + 1, "t_ms": t_result + 100.0, "kind": "op.state",
               "data": {"op_id": op_id, "state": "observado", "reason": None, "origin": "servidor"}})
    for k in ("bridge_tap.jsonl", "backend.jsonl"):
        c["samples"][k].sort(key=lambda e: float(e.get("t_ms") or 0.0))


def _r5_hello_pair(c: dict[str, Any], t: float, session: str, inst: str, epoch: str) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    rid = _r15c_rid(c)
    tap.append({"t_ms": float(t), "dir": "req", "method": "POST", "path": "/hello", "http": 200,
                "req_id": rid,
                "body": {"proto": "dsbx1", "peer": "server", "inst": inst, "epoch": epoch,
                         "mod_ver": "f2p-mod", "build": "diag", "map": "chernarusplus",
                         "world_size": 16384, "modset": ["@DayZSandbox", "@DayZSandbox_QA"],
                         "actor_engine": "none", "scene": 1}})
    tap.append({"t_ms": float(t) + 5.0, "dir": "resp", "method": "POST", "path": "/hello",
                "http": 200, "req_id": rid,
                "body": {"ok": True, "session": session, "conn": 1,
                         "lease_ms": 3000, "hold_ms": 2000, "wire_cap": 3500}})


def _r5_second_restart(c: dict[str, Any], t_restart: float, old_sess: str, new_sess: str,
                       inst: str, epoch: str) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    for entry in tap:
        when = float(entry.get("t_ms") or 0.0)
        if when < t_restart:
            continue
        body = entry.get("body") or {}
        path = entry.get("path")
        way = entry.get("dir")
        if path == "/poll" and way == "resp":
            for order in body.get("ops") or []:
                if not isinstance(order, dict):
                    continue
                if order.get("session") != old_sess:
                    continue
                order["session"] = new_sess
        if path in ("/result", "/poll") and way == "req":
            if old_sess == body.get("session"):
                body["session"] = new_sess
            query = entry.get("query")
            if isinstance(query, dict) and old_sess == query.get("session"):
                query["session"] = new_sess
        if path == "/hello" and way == "resp" and body.get("session") == old_sess:
            body["session"] = new_sess
    _r5_hello_pair(c, t_restart + 100.0, new_sess, inst, epoch)
    c["samples"]["backend.jsonl"].append({
        "seq": len(c["samples"]["backend.jsonl"]) + 1, "t_ms": float(t_restart),
        "kind": "restart", "data": {"target": "backend", "epoch": epoch}})
    for key in ("bridge_tap.jsonl", "backend.jsonl"):
        c["samples"][key].sort(key=lambda record: float(record.get("t_ms") or 0.0))


def _r5_recon_P3_restart1_apply_antes(c: dict[str, Any]) -> None:
    _r5_move_read(c, "P3", 0, 374100.0)


def _r5_recon_P3_restart2_reset_antes(c: dict[str, Any]) -> None:
    _r5_move_read(c, "P3", 1, 381100.0)


def _r5_recon_P4a_reset_antes(c: dict[str, Any]) -> None:
    _r5_add_reset_before(c, "P4a", 551300.0, 551400.0, "d4" * 8, "e1" * 16, "e1" * 16, "op-9")


def _r5_recon_P5_reset_antes(c: dict[str, Any]) -> None:
    _r5_add_reset_before(c, "P5", 762300.0, 762400.0, "e5" * 8, "e3" * 16, "e3" * 16, "op-1")


def _r5_recon_P4a_segundo_reinicio(c: dict[str, Any]) -> None:
    _r5_second_restart(c, 552500.0, "d4" * 8, "d5" * 8, "e1" * 16, "e1" * 16)


def _r5_recon_P5_segundo_reinicio(c: dict[str, Any]) -> None:
    _r5_second_restart(c, 763300.0, "e5" * 8, "f6" * 8, "e3" * 16, "e3" * 16)


def _r5_recon_P4a_sin_lectura(c: dict[str, Any]) -> None:
    _r5_drop_read(c, "P4a")


def _r5_recon_P5_sin_lectura(c: dict[str, Any]) -> None:
    _r5_drop_read(c, "P5")


# --- W-03: el corte solo exime en P5 ---

def _r5_drop_result(c: dict[str, Any], op_id: str, session: str, lo: float, hi: float) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    out = []
    drop_ack = False
    for ev in sorted(tap, key=lambda e: float(e.get("t_ms") or 0.0)):
        b = ev.get("body") or {}
        t = float(ev.get("t_ms") or 0.0)
        if ev.get("path") == "/result" and ev.get("dir") == "req" and lo <= t <= hi and \
                str(b.get("op_id")) == op_id and str(b.get("session")) == session:
            drop_ack = True
            continue
        if drop_ack and ev.get("path") == "/result" and ev.get("dir") == "resp":
            drop_ack = False
            continue
        out.append(ev)
    c["samples"]["bridge_tap.jsonl"] = out


def _r5_cut_P3_apply1_no_result(c: dict[str, Any]) -> None:
    _r5_drop_result(c, "op-4", "a1" * 8, 370000.0, 373500.0)


def _r5_cut_P3_apply2_no_result(c: dict[str, Any]) -> None:
    _r5_drop_result(c, "op-1", "b2" * 8, 373500.0, 376500.0)


def _r5_cut_P4a_apply1_no_result(c: dict[str, Any]) -> None:
    _r5_drop_result(c, "op-1", "d4" * 8, 550000.0, 556000.0)


# --- W-04: criaturas ai=0 tras el reinicio del servidor ---

def _r5_creature_row(c: dict[str, Any], source_tag: str) -> dict[str, Any] | None:
    row = _copy_census_row(c, source_tag,
                           lambda r: str(r.get("class_name")) == "ZmbM_FarmerFat_Brown")
    return row


def _r5_creature_variant(c: dict[str, Any], census_tag: str, source_tag: str, net: str,
                         variant: str) -> None:
    row = _r5_creature_row(c, source_tag)
    if row is None:
        return
    row["net_id"] = net
    row["parent_net_id"] = ""
    row["ai_agent_b"] = 0.0
    if variant == "exact_ai0":
        row["alive_b"] = 1.0
    elif variant == "exact_dead":
        row["alive_b"] = 0.0
    else:
        row["pos_x_m"] = float(row["pos_x_m"]) + 1.0
        row["alive_b"] = 1.0
    _add_row(c, census_tag, row)


def _r5_f09_P4b_exact_ai0(c: dict[str, Any]) -> None:
    _r5_creature_variant(c, "P4b:post_restart", "P4a:post_apply2", "1:991", "exact_ai0")


def _r5_f09_P4b_exact_dead(c: dict[str, Any]) -> None:
    _r5_creature_variant(c, "P4b:post_restart", "P4a:post_apply2", "1:992", "exact_dead")


def _r5_f09_P4b_1m_ai0(c: dict[str, Any]) -> None:
    _r5_creature_variant(c, "P4b:post_restart", "P4a:post_apply2", "1:993", "1m_ai0")


def _r5_f09_P4c_exact_ai0(c: dict[str, Any]) -> None:
    _r5_creature_variant(c, "P4c:post_restart", "P4c:pre_reset", "1:994", "exact_ai0")


def _r5_f09_P4c_exact_dead(c: dict[str, Any]) -> None:
    _r5_creature_variant(c, "P4c:post_restart", "P4c:pre_reset", "1:995", "exact_dead")


def _r5_f09_P4c_1m_ai0(c: dict[str, Any]) -> None:
    _r5_creature_variant(c, "P4c:post_restart", "P4c:pre_reset", "1:996", "1m_ai0")


# --- W-05: generación viva tras cada apply positivo ---

def _r5_p3_apply1_vanishes(c: dict[str, Any]) -> None:
    nets = _birth_nets(c, "P3:apply1")
    _start, pages = _job_events(c, "P3:apply1")
    obj17 = None
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if int(r.get("sample_idx", -1)) == 0 and str(r.get("class_name")) == "SeaChest":
                obj17 = str(r.get("net_id"))
                break
    if obj17 is None:
        obj17 = sorted(nets)[-1]
    gone = {n for n in nets if n != obj17}
    _remove_row(c, "P3:pre_reset", lambda r: str(r.get("net_id")) in gone)
    c["samples"]["scene_del.jsonl"] = [
        ev for ev in c["samples"]["scene_del.jsonl"]
        if not (370000.0 <= float(ev.get("t_ms") or 0.0) < 480000.0 and
                f"{int(ev.get('net_high', 0))}:{int(ev.get('net_low', 0))}" in gone)]


def _r5_p3_scene2_moved_10m(c: dict[str, Any]) -> None:
    net = None
    _start, pages = _job_events(c, "P3:apply2")
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if int(r.get("sample_idx", -1)) == 0 and str(r.get("parent_net_id") or "") == "":
                net = str(r.get("net_id"))
                break
        if net is not None:
            break
    if net is None:
        return
    for tag in ("P3:pre_reset", "P3:post_reset1", "P3:pre_reset2", "P3:post_reset2",
                "P3c:pre_reset", "P3c:clean", "P4a:post_apply1", "P4a:pre_reset",
                "P4a:post_reset", "P4a:post_apply2"):
        _mutate_row(c, tag, lambda r: str(r.get("net_id")) == net,
                    lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 10.0))


def _r5_move_birth_object(c: dict[str, Any], part: str, stage: str, census_tag: str,
                          dy: float = 0.0, dx: float = 0.0,
                          extra_tags: tuple[str, ...] = ()) -> None:
    net = None
    _start, pages = _job_events(c, f"{part}:{stage}")
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if int(r.get("sample_idx", -1)) == 0 and \
                    str(r.get("parent_net_id") or "") == "" and \
                    str(r.get("class_name", "")).startswith(("Land_", "Barrel_", "Wooden")):
                net = str(r.get("net_id"))
                break
        if net is not None:
            break
    if net is None:
        return

    def change(r: dict[str, Any]) -> None:
        r["pos_y_m"] = float(r["pos_y_m"]) + dy
        r["pos_x_m"] = float(r["pos_x_m"]) + dx
    for tag in (census_tag,) + tuple(extra_tags):
        _mutate_row(c, tag, lambda r: str(r.get("net_id")) == net, change)


def _r5_p3_apply1_apoyo(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P3", "apply1", "P3:pre_reset", dy=3.0)


def _r5_p3_apply2_apoyo(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P3", "apply2", "P3:pre_reset", dy=3.0,
                          extra_tags=("P3:post_reset1", "P3:pre_reset2", "P3:post_reset2",
                                      "P3c:pre_reset", "P3c:clean", "P4a:post_apply1",
                                      "P4a:pre_reset", "P4a:post_reset", "P4a:post_apply2"))


def _r5_p4a_apply1_apoyo(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P4a", "apply1", "P4a:post_apply1", dy=3.0)


def _r5_remove_gen(c: dict[str, Any], part: str, stage: str, census_tag: str) -> None:
    nets = _birth_nets(c, f"{part}:{stage}")
    _remove_row(c, census_tag, lambda r: str(r.get("net_id")) in nets)


def _r5_f06_P2_desaparece(c: dict[str, Any]) -> None:
    _r5_remove_gen(c, "P2", "apply", "P2:post")


def _r5_f06_P2_apoyo(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P2", "apply", "P2:post", dy=3.0)


def _r5_f06_P3_apply1_pose(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P3", "apply1", "P3:pre_reset", dx=10.0)


def _r5_f06_P3_apply2_desaparece(c: dict[str, Any]) -> None:
    _r5_remove_gen(c, "P3", "apply2", "P3:pre_reset")


def _r5_f06_P4a_apply1_pose(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P4a", "apply1", "P4a:post_apply1", dx=10.0)


def _r5_f06_P4a_apply2_desaparece(c: dict[str, Any]) -> None:
    _r5_remove_gen(c, "P4a", "apply2", "P4a:post_apply2")


def _r5_f06_P4a_apply2_pose(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P4a", "apply2", "P4a:post_apply2", dx=10.0)


def _r5_f06_P4a_apply2_apoyo(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P4a", "apply2", "P4a:post_apply2", dy=3.0)


def _r5_f06_P4b_pose(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P4b", "apply", "P4b:post_apply", dx=10.0)


def _r5_f06_P4b_apoyo(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P4b", "apply", "P4b:post_apply", dy=3.0)


def _r5_f06_P5_desaparece(c: dict[str, Any]) -> None:
    _r5_remove_gen(c, "P5", "apply2", "P5:post_apply")


def _r5_f06_P5_apoyo(c: dict[str, Any]) -> None:
    _r5_move_birth_object(c, "P5", "apply2", "P5:post_apply", dy=3.0)


# --- W-07: reenvío cortado rechazado con 400 ---

def _r5_cut_resend_400(c: dict[str, Any]) -> None:
    delivery = next((item for item in _tap_deliveries(c, "scene.apply")
                     if 760000.0 <= float(item.get("t_ms") or 0.0) < 761500.0), None)
    if delivery is None:
        return
    rid = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    sent = {"t_ms": 762300.0, "dir": "req", "method": "POST", "path": "/result",
            "http": 200, "req_id": rid,
            "query": {"peer": "server", "inst": "e3" * 16, "session": "e5" * 8,
                      "conn": str(delivery.get("conn") or 1)},
            "body": {"op_id": str(delivery["op_id"]), "session": str(delivery["session"]),
                     "epoch": "e3" * 16, "status": "done", "reason": "", "dup": False,
                     "read": {}}}
    tap.append(sent)
    rejected = {"t_ms": 762302.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 400, "req_id": rid, "body": {"ok": False, "error": "bad_request"}}
    tap.append(rejected)
    tap.sort(key=lambda record: float(record.get("t_ms") or 0.0))


# --- server_epoch de la parte ---

def _r5_no_part_epoch(c: dict[str, Any]) -> None:
    for p in (c.get("manifest", {}).get("f2p", {}) or {}).get("parts") or []:
        if isinstance(p, dict):
            p.pop("server_epoch", None)


def _r5_bad_part_epoch(c: dict[str, Any]) -> None:
    parts = (c.get("manifest", {}).get("f2p", {}) or {}).get("parts") or []
    if parts and isinstance(parts[0], dict):
        parts[0]["server_epoch"] = "no-es-32-hex"


# --- W-06: el INCONCLUSO de la CE no tapa un FALLA independiente ---

def _r5_p4b_vanish_plus_ce(c: dict[str, Any]) -> None:
    _m_r4_f06_p4b_vanish(c)
    _p_r4_f12_ce_extra_p4b(c)


def _r5_p2_pose_plus_ce(c: dict[str, Any]) -> None:
    # Un objeto de P2 desplazado 10 m en el censo posterior y un extra de la CE en la ventana.
    net = None
    _start, pages = _job_events(c, "P2:apply")
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if int(r.get("sample_idx", -1)) == 0 and \
                    str(r.get("class_name", "")).startswith(("Land_", "Barrel_")):
                net = str(r.get("net_id"))
                break
        if net is not None:
            break
    if net is not None:
        _mutate_row(c, "P2:post", lambda r: str(r.get("net_id")) == net,
                    lambda r: r.__setitem__("pos_x_m", float(r["pos_x_m"]) + 10.0))
    _p_r4_f12_ce_extra_p2(c)


SOL_POSITIVES_R5: dict[str, dict[str, Any]] = {
    "r5_cut_resend_400": {"apply": _r5_cut_resend_400, "expected_exit_code": 0, "red_exit": 1},
    "r5_no_part_epoch": {"apply": _r5_no_part_epoch, "expected_exit_code": 0, "red_exit": 2},
}

SOL_NEGATIVES_R5: dict[str, dict[str, Any]] = {
    "r5_bad_part_epoch": {"apply": _r5_bad_part_epoch,
                          "expected_exit_code": 2,
                          "must_fail_status": {"F2P-01": "missing"},
                          "must_reason": "manifest_incomplete",
                          "red_exit": 2},
}

SOL_MUTANTS_R5.update({
    "r5_recon_P3_restart1_apply_antes": {"apply": _r5_recon_P3_restart1_apply_antes,
                                          "expected_exit_code": 1,
                                          "must_fail_status": {"F2P-05": "fail"},
                                          "must_detail": {"F2P-05": "no_reconciliation_after_restart"},
                                          "red_exit": 1},
    "r5_recon_P3_restart2_reset_antes": {"apply": _r5_recon_P3_restart2_reset_antes,
                                          "expected_exit_code": 1,
                                          "must_fail_status": {"F2P-05": "fail"},
                                          "must_detail": {"F2P-05": "no_reconciliation_after_restart"},
                                          "red_exit": 1},
    "r5_recon_P4a_reset_antes": {"apply": _r5_recon_P4a_reset_antes,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-08": "fail"},
                                  "must_detail": {"F2P-08": "no_reconciliation_before_scene"},
                                  "red_exit": 0},
    "r5_recon_P5_reset_antes": {"apply": _r5_recon_P5_reset_antes,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-09": "fail"},
                                 "must_detail": {"F2P-09": "no_reconciliation_before_scene"},
                                 "red_exit": 0},
    "r5_recon_P4a_segundo_reinicio": {"apply": _r5_recon_P4a_segundo_reinicio,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-08": "fail"},
                                       "must_detail": {"F2P-08": "no_reconciliation_before_scene"},
                                       "red_exit": 0},
    "r5_recon_P5_segundo_reinicio": {"apply": _r5_recon_P5_segundo_reinicio,
                                      "expected_exit_code": 1,
                                      "must_fail_status": {"F2P-09": "fail"},
                                      "must_detail": {"F2P-09": "no_reconciliation_before_scene"},
                                      "red_exit": 0},
    "r5_recon_P4a_sin_lectura": {"apply": _r5_recon_P4a_sin_lectura,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-08": "fail"},
                                  "must_detail": {"F2P-08": "no_reconciliation_before_scene"},
                                  "red_exit": 1},
    "r5_recon_P5_sin_lectura": {"apply": _r5_recon_P5_sin_lectura,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-09": "fail"},
                                 "must_detail": {"F2P-09": "no_reconciliation_before_scene"},
                                 "red_exit": 1},
    "r5_cut_P3_apply1_no_result": {"apply": _r5_cut_P3_apply1_no_result,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-05": "fail"},
                                    "must_detail": {"F2P-05": "tap_trace_mismatch"},
                                    "red_exit": 0},
    "r5_cut_P3_apply2_no_result": {"apply": _r5_cut_P3_apply2_no_result,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-05": "fail"},
                                    "must_detail": {"F2P-05": "tap_trace_mismatch"},
                                    "red_exit": 0},
    "r5_cut_P4a_apply1_no_result": {"apply": _r5_cut_P4a_apply1_no_result,
                                     "expected_exit_code": 1,
                                     "must_fail_status": {"F2P-08": "fail"},
                                     "must_detail": {"F2P-08": "tap_trace_mismatch"},
                                     "red_exit": 1},
    "r5_f09_P4b_exact_ai0": {"apply": _r5_f09_P4b_exact_ai0,
                              "expected_exit_code": 1,
                              "must_fail_status": {"F2P-07": "fail"},
                              "must_detail": {"F2P-07": "reappeared"},
                              "red_exit": 0},
    "r5_f09_P4b_exact_dead": {"apply": _r5_f09_P4b_exact_dead,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-07": "fail"},
                               "must_detail": {"F2P-07": "reappeared"},
                               "red_exit": 0},
    "r5_f09_P4b_1m_ai0": {"apply": _r5_f09_P4b_1m_ai0,
                           "expected_exit_code": 1,
                           "must_fail_status": {"F2P-07": "fail"},
                           "must_detail": {"F2P-07": "near_last_known"},
                           "red_exit": 0},
    "r5_f09_P4c_exact_ai0": {"apply": _r5_f09_P4c_exact_ai0,
                              "expected_exit_code": 1,
                              "must_fail_status": {"F2P-07": "fail"},
                              "must_detail": {"F2P-07": "reappeared"},
                              "red_exit": 0},
    "r5_f09_P4c_exact_dead": {"apply": _r5_f09_P4c_exact_dead,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-07": "fail"},
                               "must_detail": {"F2P-07": "reappeared"},
                               "red_exit": 0},
    "r5_f09_P4c_1m_ai0": {"apply": _r5_f09_P4c_1m_ai0,
                           "expected_exit_code": 1,
                           "must_fail_status": {"F2P-07": "fail"},
                           "must_detail": {"F2P-07": "near_last_known"},
                           "red_exit": 0},
    "r5_f06_P3_apply1_desaparece": {"apply": _r5_p3_apply1_vanishes,
                                     "expected_exit_code": 1,
                                     "must_fail_status": {"F2P-05": "fail"},
                                     "must_detail": {"F2P-05": "census_missing"},
                                     "red_exit": 0},
    "r5_f06_P3_apply2_pose": {"apply": _r5_p3_scene2_moved_10m,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-05": "fail"},
                               "must_detail": {"F2P-05": "pose"},
                               "red_exit": 0},
    "r5_f06_P3_apply1_apoyo": {"apply": _r5_p3_apply1_apoyo,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-05": "fail"},
                                "must_detail": {"F2P-05": "unsupported"},
                                "red_exit": 0},
    "r5_f06_P3_apply2_apoyo": {"apply": _r5_p3_apply2_apoyo,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-05": "fail"},
                                "must_detail": {"F2P-05": "unsupported"},
                                "red_exit": 0},
    "r5_f06_P4a_apply1_apoyo": {"apply": _r5_p4a_apply1_apoyo,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-08": "fail"},
                                 "must_detail": {"F2P-08": "unsupported"},
                                 "red_exit": 0},
    "r5_f12_P4b_vanish_plus_ce": {"apply": _r5_p4b_vanish_plus_ce,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-07": "fail"},
                                   "must_detail": {"F2P-07": "census_missing"},
                                   "allowed_non_pass": {"F2P-13": ["missing"]},
                                   "red_exit": 2},
    "r5_f12_P2_pose_plus_ce": {"apply": _r5_p2_pose_plus_ce,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-01": "fail"},
                                "must_detail": {"F2P-01": "pose"},
                                "allowed_non_pass": {"F2P-02": ["fail"], "F2P-04": ["missing"],
                                                     "F2P-12": ["missing"], "F2P-13": ["missing"]},
                                "red_exit": 1},
    # Celdas de W-05 que faltaban (el rojo es cobertura si bf498a5 ya las miraba).
    "r5_f06_P2_desaparece": {"apply": _r5_f06_P2_desaparece,
                              "expected_exit_code": 1,
                              "must_fail_status": {"F2P-01": "fail"},
                              "must_detail": {"F2P-01": "census_missing"},
                              "allowed_non_pass": {"F2P-02": ["fail"], "F2P-12": ["missing"]},
                              "red_exit": 1},
    "r5_f06_P2_apoyo": {"apply": _r5_f06_P2_apoyo,
                         "expected_exit_code": 1,
                         "must_fail_status": {"F2P-01": "fail"},
                         "must_detail": {"F2P-01": "unsupported"},
                         "allowed_non_pass": {"F2P-02": ["fail"], "F2P-12": ["missing"]},
                         "red_exit": 1},
    "r5_f06_P3_apply1_pose": {"apply": _r5_f06_P3_apply1_pose,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-05": "fail"},
                               "must_detail": {"F2P-05": "pose"},
                               "red_exit": 0},
    "r5_f06_P3_apply2_desaparece": {"apply": _r5_f06_P3_apply2_desaparece,
                                     "expected_exit_code": 1,
                                     "must_fail_status": {"F2P-05": "fail"},
                                     "must_detail": {"F2P-05": "census_missing"},
                                     "allowed_non_pass": {"F2P-06": ["fail"]},
                                     "red_exit": 1},
    "r5_f06_P4a_apply1_pose": {"apply": _r5_f06_P4a_apply1_pose,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-08": "fail"},
                                "must_detail": {"F2P-08": "pose"},
                                "red_exit": 1},
    "r5_f06_P4a_apply2_desaparece": {"apply": _r5_f06_P4a_apply2_desaparece,
                                      "expected_exit_code": 1,
                                      "must_fail_status": {"F2P-08": "fail"},
                                      "must_detail": {"F2P-08": "census_missing"},
                                      "red_exit": 1},
    "r5_f06_P4a_apply2_pose": {"apply": _r5_f06_P4a_apply2_pose,
                                "expected_exit_code": 1,
                                "must_fail_status": {"F2P-08": "fail"},
                                "must_detail": {"F2P-08": "pose"},
                                "red_exit": 1},
    "r5_f06_P4a_apply2_apoyo": {"apply": _r5_f06_P4a_apply2_apoyo,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-08": "fail"},
                                 "must_detail": {"F2P-08": "unsupported"},
                                 "red_exit": 1},
    "r5_f06_P4b_pose": {"apply": _r5_f06_P4b_pose,
                         "expected_exit_code": 1,
                         "must_fail_status": {"F2P-07": "fail"},
                         "must_detail": {"F2P-07": "pose"},
                         "red_exit": 1},
    "r5_f06_P4b_apoyo": {"apply": _r5_f06_P4b_apoyo,
                          "expected_exit_code": 1,
                          "must_fail_status": {"F2P-07": "fail"},
                          "must_detail": {"F2P-07": "unsupported"},
                          "red_exit": 1},
    "r5_f06_P5_desaparece": {"apply": _r5_f06_P5_desaparece,
                              "expected_exit_code": 1,
                              "must_fail_status": {"F2P-09": "fail"},
                              "must_detail": {"F2P-09": "census_missing"},
                              "red_exit": 1},
    "r5_f06_P5_apoyo": {"apply": _r5_f06_P5_apoyo,
                         "expected_exit_code": 1,
                         "must_fail_status": {"F2P-09": "fail"},
                         "must_detail": {"F2P-09": "unsupported"},
                         "red_exit": 1},
})

SOL_CASES_R5: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R5.items():
    SOL_CASES_R5[_name] = {"kind": "mutant", "name": _name, "check": "T2f-5"}
for _name, _spec in SOL_NEGATIVES_R5.items():
    SOL_CASES_R5[_name] = {"kind": "negative", "name": _name, "check": "T2f-5"}
for _name, _spec in SOL_POSITIVES_R5.items():
    SOL_CASES_R5[_name] = {"kind": "positive", "name": _name, "check": "T2f-5"}

SOL_CASES.update(SOL_CASES_R5)

# ---------------------------------------------------------------------------------------------------
# T2f-6 (v1.3.12): los PASA falsos reproducidos del encargo. Grupos r6_.
# ---------------------------------------------------------------------------------------------------

_R6_EPOCH_GROUPS = [("P1", "P2", "P2n", "P3", "P3c", "P4a"), ("P4b", "P4c"), ("P5",)]


def _r6_sort(c: dict[str, Any]) -> None:
    for k in ("bridge_tap.jsonl", "backend.jsonl"):
        c["samples"][k].sort(key=lambda e: float(e.get("t_ms") or 0.0))


def _r6_birth_net(c: dict[str, Any], part: str, stage: str) -> str | None:
    _start, pages = _job_events(c, f"{part}:{stage}")
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            if int(r.get("sample_idx", -1)) == 0 and \
                    str(r.get("parent_net_id") or "") == "" and \
                    str(r.get("class_name", "")).startswith(("Land_", "Barrel_", "Wooden")):
                return str(r.get("net_id"))
    return None


def _r6_all_tags(c: dict[str, Any]) -> list[str]:
    """Etiquetas de todos los trabajos (testigos y censos), en el orden del bridge."""
    out: list[str] = []
    for ev in c["samples"]["bridge.jsonl"]:
        if ev.get("ev") == "result" and ev.get("http") == 200:
            read = (ev.get("result") or {}).get("read")
            u = _unpack(read) if isinstance(read, dict) else None
            if not u:
                continue
            t = str(u[0].get("area_tag") or u[0].get("witness_tag") or "")
            if t and t not in out:
                out.append(t)
    return out


def _r6_support_A(c: dict[str, Any], part: str, stage: str, census_tag: str) -> None:
    """W-05 variante A: en el censo siguiente el suelo baja 3 m; la posición no cambia."""
    net = _r6_birth_net(c, part, stage)
    if net is None:
        return
    _mutate_row(c, census_tag, lambda r: str(r.get("net_id")) == net,
                lambda r: r.__setitem__("surface_y_m", float(r["pos_y_m"]) - 3.0))


def _r6_support_B(c: dict[str, Any], part: str, stage: str) -> None:
    """W-05 variante B: el objeto nace y sigue flotando 3 m en el testigo y en todos los censos
    del mismo epoch del servidor donde sale (los `net_id` se repiten entre epochs)."""
    net = _r6_birth_net(c, part, stage)
    if net is None:
        return
    group = next(g for g in _R6_EPOCH_GROUPS if part in g)
    for tag in [t for t in _r6_all_tags(c) if t.split(":", 1)[0] in group]:
        _mutate_row(c, tag, lambda r: str(r.get("net_id")) == net,
                    lambda r: r.__setitem__("pos_y_m", float(r["pos_y_m"]) + 3.0))


def _r6_terminal(c: dict[str, Any], lo: float, hi: float, op_id: str, state: str,
                 reason: str | None, result_session: str | None = None,
                 result_status: str | None = None, result_reason: str | None = None) -> None:
    """Cambia el último terminal no pendiente de `op_id` en el tramo [lo, hi]."""
    cands = [ev for ev in c["samples"]["backend.jsonl"]
             if ev.get("kind") == "op.state" and
             str((ev.get("data") or {}).get("op_id")) == op_id and
             lo <= float(ev.get("t_ms") or 0.0) <= hi and
             str((ev.get("data") or {}).get("state")) != "pendiente"]
    if not cands:
        return
    st = max(cands, key=lambda ev: float(ev.get("t_ms") or 0.0))
    st["data"]["state"] = state
    st["data"]["reason"] = reason
    if result_status is not None:
        for ev in c["samples"]["bridge_tap.jsonl"]:
            if ev.get("dir") != "req" or ev.get("path") != "/result":
                continue
            b = ev.get("body") or {}
            if str(b.get("op_id")) == op_id and str(b.get("session")) == str(result_session):
                b["status"] = result_status
                b["reason"] = result_reason or ""


def _r6_delivery_op(c: dict[str, Any], sess: str, op: str) -> dict[str, Any] | None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("session")) == sess and \
                        str(o.get("op_id")) == op:
                    return o
    return None


def _r6_redeliver(c: dict[str, Any], sess: str, op: str, t_deliver: float,
                  inst: str, epoch: str) -> None:
    """Segunda entrega del mismo (sesión, op_id), como la de P2: resultado con dup:true y acuse."""
    src = _r6_delivery_op(c, sess, op)
    if src is None:
        return
    o2 = copy.deepcopy(src)
    tap = c["samples"]["bridge_tap.jsonl"]
    rid_poll = _r15c_rid(c)
    rid_result = rid_poll + 1
    tap.append({"t_ms": t_deliver - 0.5, "dir": "req", "method": "GET", "path": "/poll",
                "req_id": rid_poll,
                "query": {"peer": "server", "inst": inst, "session": sess, "conn": "1",
                          "deliver": "1"}})
    tap.append({"t_ms": t_deliver, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid_poll,
                "body": {"ok": True, "now_ms": t_deliver, "ops": [o2]}})
    tap.append({"t_ms": t_deliver + 1000.0, "dir": "req", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result,
                "query": {"peer": "server", "inst": inst, "session": sess, "conn": "1"},
                "body": {"op_id": op, "session": sess, "epoch": epoch, "status": "done",
                         "reason": "", "dup": True, "read": {}}})
    tap.append({"t_ms": t_deliver + 1003.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result, "body": {"ok": True}})
    _r6_sort(c)


def _r6_inflight_redeliver(c: dict[str, Any], sess: str, op: str, t_deliver2: float,
                           t_result2: float, inst: str, epoch: str) -> None:
    src = _r6_delivery_op(c, sess, op)
    if src is None:
        return
    o2 = copy.deepcopy(src)
    tap = c["samples"]["bridge_tap.jsonl"]
    rid_poll = _r15c_rid(c)
    rid_result = rid_poll + 1
    tap.append({"t_ms": t_deliver2 - 0.5, "dir": "req", "method": "GET", "path": "/poll",
                "req_id": rid_poll,
                "query": {"peer": "server", "inst": inst, "session": sess, "conn": "1",
                          "deliver": "1"}})
    tap.append({"t_ms": t_deliver2, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid_poll,
                "body": {"ok": True, "now_ms": t_deliver2, "ops": [o2]}})
    tap.append({"t_ms": t_result2, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid_result,
                "query": {"peer": "server", "inst": inst, "session": sess, "conn": "1"},
                "body": {"op_id": op, "session": sess, "epoch": epoch, "status": "done",
                         "reason": "", "dup": True, "read": {}}})
    tap.append({"t_ms": t_result2 + 3.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result, "body": {"ok": True}})
    _r6_sort(c)


def _r6_drop_result_and_ack(c: dict[str, Any], sess: str, op: str, lo: float, hi: float) -> None:
    out = []
    drop_ack = False
    for ev in sorted(c["samples"]["bridge_tap.jsonl"], key=lambda e: float(e.get("t_ms") or 0.0)):
        b = ev.get("body") or {}
        t = float(ev.get("t_ms") or 0.0)
        if ev.get("path") == "/result" and ev.get("dir") == "req" and lo <= t <= hi and \
                str(b.get("op_id")) == op and str(b.get("session")) == sess:
            drop_ack = True
            continue
        if drop_ack and ev.get("path") == "/result" and ev.get("dir") == "resp":
            drop_ack = False
            continue
        out.append(ev)
    c["samples"]["bridge_tap.jsonl"] = out


def _r6_renumber_cut_op(c: dict[str, Any]) -> None:
    """La op cortada de P5 (d4, op-6) pasa a op-7 para dejar sitio al reset de la escena 2."""
    d4 = "d4" * 8
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and str(o.get("session")) == d4 and \
                        str(o.get("op_id")) == "op-6":
                    o["op_id"] = "op-7"
        b = ev.get("body") or {}
        if ev.get("path") == "/result" and ev.get("dir") == "req" and \
                str(b.get("op_id")) == "op-6" and str(b.get("session")) == d4:
            b["op_id"] = "op-7"
    for ev in c["samples"]["backend.jsonl"]:
        if ev.get("kind") == "op.state" and \
                str((ev.get("data") or {}).get("op_id")) == "op-6" and \
                551000.0 <= float(ev["t_ms"]) < 762000.0:
            ev["data"]["op_id"] = "op-7"


def _r6_add_p4c_scene2_reset(c: dict[str, Any], state: str, reason: str | None,
                             rstatus: str = "done", rreason: str = "") -> None:
    _r6_renumber_cut_op(c)
    d4 = "d4" * 8
    e2 = "e2" * 16
    t = 697500.0
    c["samples"]["backend.jsonl"].append({
        "seq": 0, "t_ms": t - 100.0, "kind": "op.state",
        "data": {"op_id": "op-6", "state": "pendiente", "origin": "backend",
                 "reason": None, "at_ms": t - 100.0}})
    tap = c["samples"]["bridge_tap.jsonl"]
    rid_poll = _r15c_rid(c)
    rid_result = rid_poll + 1
    tap.append({"t_ms": t - 0.5, "dir": "req", "method": "GET", "path": "/poll",
                "req_id": rid_poll,
                "query": {"peer": "server", "inst": e2, "session": d4, "conn": "1",
                          "deliver": "1"}})
    tap.append({"t_ms": t, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid_poll,
                "body": {"ok": True, "now_ms": t, "ops": [
                    {"op_id": "op-6", "session": d4, "conn": 1, "epoch": e2, "inst": e2,
                     "verb": "scene.reset",
                     "args": {"f2": 1, "doc_id": "d-2f2a5c01",
                              "if_pending": {"session": "", "op_id": ""}},
                     "issued_ms": t - 50, "ttl_ms": 5000}]}})
    tap.append({"t_ms": t + 500.0, "dir": "req", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result,
                "query": {"peer": "server", "inst": e2, "session": d4, "conn": "1"},
                "body": {"op_id": "op-6", "session": d4, "epoch": e2, "status": rstatus,
                         "reason": rreason, "dup": False, "read": {}}})
    tap.append({"t_ms": t + 503.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result, "body": {"ok": True}})
    c["samples"]["backend.jsonl"].append({
        "seq": 0, "t_ms": t + 600.0, "kind": "op.state",
        "data": {"op_id": "op-6", "state": state, "origin": "servidor",
                 "reason": reason, "at_ms": t + 600.0}})
    _r6_sort(c)


def _r6_p5_second_restart_apply2_without_result(c: dict[str, Any]) -> None:
    """W-03/X-04: un segundo reinicio del backend en P5; el apply2 de la sesión que muere pierde su
    `/result` pero conserva su terminal `observado`. El respaldo del corte no debe eximirle."""
    e5 = "e5" * 8
    e3 = "e3" * 16
    f6 = "f6" * 8
    _r6_drop_result_and_ack(c, e5, "op-1", 764000.0, 765400.0)
    c["samples"]["backend.jsonl"].append({
        "seq": 0, "t_ms": 765600.0, "kind": "restart",
        "data": {"target": "backend", "epoch": e3}})
    _r5_hello_pair(c, 765700.0, f6, e3, e3)
    tap = c["samples"]["bridge_tap.jsonl"]
    t = 765750.0
    rid_rd = _r15c_rid(c)
    tap.append({"t_ms": t - 0.5, "dir": "req", "method": "GET", "path": "/poll", "req_id": rid_rd,
                "query": {"peer": "server", "inst": e3, "session": f6, "conn": "1",
                          "deliver": "1"}})
    tap.append({"t_ms": t, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid_rd,
                "body": {"ok": True, "now_ms": t, "ops": [
                    {"op_id": "rd-1", "session": f6, "conn": 1, "epoch": e3, "inst": e3,
                     "verb": "state.read", "args": {"doc_id": "d-7c19e2a5"},
                     "issued_ms": t - 50, "ttl_ms": 5000}]}})
    src = None
    for ev in tap:
        b = ev.get("body") or {}
        if ev.get("dir") == "req" and ev.get("path") == "/result" and \
                str(b.get("op_id")) == "rd-1" and str(b.get("session")) == e5:
            src = copy.deepcopy(ev)
    if src is None:
        return
    rid_rd_result = rid_rd + 1
    src["t_ms"] = t + 50.0
    src["req_id"] = rid_rd_result
    src["query"]["session"] = f6
    src["body"]["session"] = f6
    tap.append(src)
    tap.append({"t_ms": t + 53.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_rd_result, "body": {"ok": True}})
    t2 = 767000.0
    rid_op = rid_rd_result + 1
    tap.append({"t_ms": t2 - 0.5, "dir": "req", "method": "GET", "path": "/poll", "req_id": rid_op,
                "query": {"peer": "server", "inst": e3, "session": f6, "conn": "1",
                          "deliver": "1"}})
    c["samples"]["backend.jsonl"].append({
        "seq": 0, "t_ms": t2 - 100.0, "kind": "op.state",
        "data": {"op_id": "op-1", "state": "pendiente", "origin": "backend",
                 "reason": None, "at_ms": t2 - 100.0}})
    tap.append({"t_ms": t2, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid_op,
                "body": {"ok": True, "now_ms": t2, "ops": [
                    {"op_id": "op-1", "session": f6, "conn": 1, "epoch": e3, "inst": e3,
                     "verb": "scene.apply", "args": {"f2": 1, "doc_id": "d-7c19e2a5"},
                     "issued_ms": t2 - 50, "ttl_ms": 5000}]}})
    rid_op_result = rid_op + 1
    tap.append({"t_ms": t2 + 500.0, "dir": "req", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_op_result,
                "query": {"peer": "server", "inst": e3, "session": f6, "conn": "1"},
                "body": {"op_id": "op-1", "session": f6, "epoch": e3, "status": "done",
                         "reason": "", "dup": False, "read": {}}})
    tap.append({"t_ms": t2 + 503.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_op_result, "body": {"ok": True}})
    c["samples"]["backend.jsonl"].append({
        "seq": 0, "t_ms": t2 + 600.0, "kind": "op.state",
        "data": {"op_id": "op-1", "state": "observado", "origin": "servidor",
                 "reason": None, "at_ms": t2 + 600.0}})
    _r6_sort(c)


def _r6_parent_birth(c: dict[str, Any], part: str, stage: str,
                     census_tags: tuple[str, ...]) -> None:
    """X-05: la raíz de la generación aparece con padre en su censo siguiente."""
    net = _r6_birth_net(c, part, stage)
    if net is None:
        return
    parent = None
    _start, pages = _job_events(c, census_tags[0])
    for ev in pages:
        u = _unpack(ev["result"]["read"])
        if not u:
            continue
        for r in u[2]:
            n = str(r.get("net_id"))
            if n and n != net:
                parent = n
                break
        if parent is not None:
            break
    if parent is None:
        parent = "1:999999"
    for tag in census_tags:
        _mutate_row(c, tag, lambda r: str(r.get("net_id")) == net,
                    lambda r: r.__setitem__("parent_net_id", parent))


# --- W-05: el apoyo en cada apply positivo de §6.1 punto 3 (línea 510) -------------------------

_R6_W05_STAGES: list[tuple[str, str, str, str]] = [
    ("P2", "apply", "P2:post", "F2P-01"),
    ("P3", "apply1", "P3:pre_reset", "F2P-05"),
    ("P3", "apply2", "P3:pre_reset", "F2P-05"),
    ("P4a", "apply1", "P4a:post_apply1", "F2P-08"),
    ("P4a", "apply2", "P4a:post_apply2", "F2P-08"),
    ("P4b", "apply", "P4b:post_apply", "F2P-07"),
    ("P5", "apply2", "P5:post_apply", "F2P-09"),
]

_R6_W05_RED = {("P4a", "apply2"): 0}

SOL_MUTANTS_R6: dict[str, dict[str, Any]] = {}
for _part, _stage, _census, _check in _R6_W05_STAGES:
    for _variant in ("suelo_censo", "nace_flotando"):
        _name = f"r6_w05_{_part}_{_stage}_{_variant}"
        if _variant == "suelo_censo":
            _apply = (lambda c, p=_part, s=_stage, ct=_census:
                      _r6_support_A(c, p, s, ct))
        else:
            _apply = (lambda c, p=_part, s=_stage: _r6_support_B(c, p, s))
        _spec = {
            "apply": _apply,
            "expected_exit_code": 1,
            "must_fail_status": {_check: "fail"},
            "must_detail": {_check: "unsupported"},
            "red_exit": _R6_W05_RED.get((_part, _stage), 1),
        }
        if _part == "P2":
            _spec["allowed_non_pass"] = {"F2P-02": ["fail"]}
        SOL_MUTANTS_R6[_name] = _spec


# --- W-11: la op cortada de P5 no tiene terminal sin una de sus tres causas --------------------

def _r6_w11_cut_reconciliada_antes(c: dict[str, Any]) -> None:
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 760000.0 <= float(x.get("t_ms") or 0.0) < 761500.0), None)
    if d is None:
        return
    at = 761400.0
    c["samples"]["backend.jsonl"].append({
        "seq": len(c["samples"]["backend.jsonl"]) + 1, "t_ms": at, "kind": "op.state",
        "data": {"op_id": str(d["op_id"]), "state": "observado", "origin": "servidor",
                 "reason": "reconciliada", "at_ms": at}})


def _r6_w11_cut_reconciliada_despues(c: dict[str, Any]) -> None:
    d = next((x for x in _tap_deliveries(c, "scene.apply")
              if 760000.0 <= float(x.get("t_ms") or 0.0) < 761500.0), None)
    if d is None:
        return
    at = 762600.0
    c["samples"]["backend.jsonl"].append({
        "seq": len(c["samples"]["backend.jsonl"]) + 1, "t_ms": at, "kind": "op.state",
        "data": {"op_id": str(d["op_id"]), "state": "observado", "origin": "servidor",
                 "reason": "reconciliada", "at_ms": at}})


# --- X-01: búsquedas de etapa por (sesión, op_id), no por índice de entrega -------------------

def _r6_x01_P3_reset1_redelivered_reset2_fallido(c: dict[str, Any]) -> None:
    _r6_redeliver(c, "c3" * 8, "op-1", 388000.0, "e1" * 16, "e1" * 16)
    _r6_terminal(c, 376500.0, 551000.0, "op-2", "fallido", "lectura_no_cumple",
                 result_session="c3" * 8, result_status="error",
                 result_reason="lectura_no_cumple")


def _r6_x01_P3_reset1_redelivered_reset2_observado(c: dict[str, Any]) -> None:
    _r6_redeliver(c, "c3" * 8, "op-1", 388000.0, "e1" * 16, "e1" * 16)
    _r6_terminal(c, 376500.0, 551000.0, "op-2", "observado", None)


def _r6_x01_P3_reset1_redelivered_inflight_reset2_fallido(c: dict[str, Any]) -> None:
    _r6_inflight_redeliver(c, "c3" * 8, "op-1", 381500.0, 382200.0, "e1" * 16, "e1" * 16)
    _r6_terminal(c, 376500.0, 551000.0, "op-2", "fallido", "lectura_no_cumple",
                 result_session="c3" * 8, result_status="error",
                 result_reason="lectura_no_cumple")


def _r6_x01_P3_apply1_redelivered_apply2_fallido(c: dict[str, Any]) -> None:
    _r6_redeliver(c, "a1" * 8, "op-4", 372700.0, "e1" * 16, "e1" * 16)
    _r6_terminal(c, 373500.0, 376500.0, "op-1", "fallido", "create_failed",
                 result_session="b2" * 8, result_status="rejected",
                 result_reason="create_failed")


def _r6_x01_P4a_apply1_redelivered_apply2_fallido(c: dict[str, Any]) -> None:
    _r6_redeliver(c, "d4" * 8, "op-1", 556000.0, "e1" * 16, "e1" * 16)
    _r6_terminal(c, 551000.0, 762000.0, "op-3", "fallido", "create_failed",
                 result_session="d4" * 8, result_status="rejected",
                 result_reason="create_failed")


def _r6_x01_P4a_apply1_late_redelivery_apply2_fallido(c: dict[str, Any]) -> None:
    _r6_inflight_redeliver(c, "d4" * 8, "op-1", 567500.0, 567700.0, "e1" * 16, "e1" * 16)
    _r6_terminal(c, 551000.0, 762000.0, "op-3", "fallido", "create_failed",
                 result_session="d4" * 8, result_status="rejected",
                 result_reason="create_failed")


# --- X-02: el reset de limpieza de P2n se juzga (observado/``) ---------------------------------

def _r6_x02_P2n_reset_fallido(c: dict[str, Any]) -> None:
    _r6_terminal(c, 0.0, 373500.0, "op-3", "fallido", "lectura_no_cumple",
                 result_session="a1" * 8, result_status="error",
                 result_reason="lectura_no_cumple")


def _r6_x02_P2n_reset_reconciliada(c: dict[str, Any]) -> None:
    _r6_terminal(c, 0.0, 373500.0, "op-3", "observado", "reconciliada")


def _r6_x02_P2n_reset_contenido_ajeno(c: dict[str, Any]) -> None:
    _r6_terminal(c, 0.0, 373500.0, "op-3", "parcial", "contenido_ajeno")


# --- X-03: el reset de la escena 2 de P4c también se juzga ------------------------------------

def _r6_x03_P4c_reset_escena2_observado(c: dict[str, Any]) -> None:
    _r6_add_p4c_scene2_reset(c, "observado", None)


def _r6_x03_P4c_reset_escena2_fallido(c: dict[str, Any]) -> None:
    _r6_add_p4c_scene2_reset(c, "fallido", "lectura_no_cumple", "error", "lectura_no_cumple")


def _r6_x03_P4c_reset_escena2_reconciliada(c: dict[str, Any]) -> None:
    _r6_add_p4c_scene2_reset(c, "observado", "reconciliada")


# --- X-04: la excepción del corte solo vale para la op cortada de P5 --------------------------

def _r6_x04_P3_apply1_cut_no_result(c: dict[str, Any]) -> None:
    _r6_drop_result_and_ack(c, "a1" * 8, "op-4", 370000.0, 373500.0)
    c["samples"]["backend.jsonl"].append({
        "seq": 0, "t_ms": 371500.0, "kind": "cut",
        "data": {"target": "backend", "epoch": "e1" * 16}})
    _r6_sort(c)


def _r6_x04_P4a_apply2_cut_no_result(c: dict[str, Any]) -> None:
    _r6_drop_result_and_ack(c, "d4" * 8, "op-3", 567000.0, 610000.0)
    c["samples"]["backend.jsonl"].append({
        "seq": 0, "t_ms": 568200.0, "kind": "cut",
        "data": {"target": "backend", "epoch": "e1" * 16}})
    _r6_sort(c)


# --- X-05: la raíz en el censo siguiente también en P3 y P4a apply1 ---------------------------

def _r6_x05_P3_apply1_parented(c: dict[str, Any]) -> None:
    _r6_parent_birth(c, "P3", "apply1", ("P3:pre_reset",))


def _r6_x05_P4a_apply1_parented(c: dict[str, Any]) -> None:
    _r6_parent_birth(c, "P4a", "apply1", ("P4a:post_apply1", "P4a:pre_reset"))


SOL_MUTANTS_R6.update({
    "r6_w11_P5_cut_reconciliada_antes": {
        "apply": _r6_w11_cut_reconciliada_antes,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "observado/reconciliada"},
        "red_exit": 0},
    "r6_w11_P5_cut_reconciliada_despues": {
        "apply": _r6_w11_cut_reconciliada_despues,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 1},
    "r6_x01_P3_reset1_redelivered_reset2_fallido": {
        "apply": _r6_x01_P3_reset1_redelivered_reset2_fallido,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "reset2_state"},
        "red_exit": 0},
    "r6_x01_P3_reset1_redelivered_reset2_observado": {
        "apply": _r6_x01_P3_reset1_redelivered_reset2_observado,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "reset2_state"},
        "red_exit": 0},
    "r6_x01_P3_reset1_redelivered_inflight_reset2_fallido": {
        "apply": _r6_x01_P3_reset1_redelivered_inflight_reset2_fallido,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "reset2_state"},
        "red_exit": 0},
    "r6_x01_P3_apply1_redelivered_apply2_fallido": {
        "apply": _r6_x01_P3_apply1_redelivered_apply2_fallido,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "apply2_state"},
        "allowed_non_pass": {"F2P-13": ["missing"]},
        "red_exit": 2},
    "r6_x01_P4a_apply1_redelivered_apply2_fallido": {
        "apply": _r6_x01_P4a_apply1_redelivered_apply2_fallido,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "apply2_state"},
        "allowed_non_pass": {"F2P-13": ["missing"]},
        "red_exit": 2},
    "r6_x01_P4a_apply1_late_redelivery_apply2_fallido": {
        "apply": _r6_x01_P4a_apply1_late_redelivery_apply2_fallido,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "apply2_state"},
        "allowed_non_pass": {"F2P-13": ["missing"]},
        "red_exit": 2},
    "r6_x02_P2n_reset_fallido": {
        "apply": _r6_x02_P2n_reset_fallido,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-03": "fail"},
        "must_detail": {"F2P-03": "reset_state"},
        "red_exit": 0},
    "r6_x02_P2n_reset_reconciliada": {
        "apply": _r6_x02_P2n_reset_reconciliada,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-03": "fail"},
        "must_detail": {"F2P-03": "reset_state"},
        "red_exit": 0},
    "r6_x02_P2n_reset_contenido_ajeno": {
        "apply": _r6_x02_P2n_reset_contenido_ajeno,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-03": "fail"},
        "must_detail": {"F2P-03": "reset_state"},
        "red_exit": 0},
    "r6_x03_P4c_reset_escena2_observado": {
        "apply": _r6_x03_P4c_reset_escena2_observado,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "p4c_reset_fuera_de_guion"},
        "red_exit": 0},
    "r6_x03_P4c_reset_escena2_fallido": {
        "apply": _r6_x03_P4c_reset_escena2_fallido,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "p4c_reset_fuera_de_guion"},
        "red_exit": 0},
    "r6_x03_P4c_reset_escena2_reconciliada": {
        "apply": _r6_x03_P4c_reset_escena2_reconciliada,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "p4c_reset_fuera_de_guion"},
        "red_exit": 0},
    "r6_x04_P3_apply1_cut_no_result": {
        "apply": _r6_x04_P3_apply1_cut_no_result,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"},
        "red_exit": 0},
    "r6_x04_P4a_apply2_cut_no_result": {
        "apply": _r6_x04_P4a_apply2_cut_no_result,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"},
        "red_exit": 0},
    "r6_x04_P5_second_restart_apply2_without_result": {
        "apply": _r6_p5_second_restart_apply2_without_result,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r6_x05_P3_apply1_parented": {
        "apply": _r6_x05_P3_apply1_parented,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "not_root"},
        "red_exit": 0},
    "r6_x05_P4a_apply1_parented": {
        "apply": _r6_x05_P4a_apply1_parented,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "not_root"},
        "red_exit": 0},
})

SOL_POSITIVES_R6: dict[str, dict[str, Any]] = {}

SOL_NEGATIVES_R6: dict[str, dict[str, Any]] = {}

SOL_CASES_R6: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R6.items():
    SOL_CASES_R6[_name] = {"kind": "mutant", "name": _name, "check": "T2f-6"}
for _name, _spec in SOL_NEGATIVES_R6.items():
    SOL_CASES_R6[_name] = {"kind": "negative", "name": _name, "check": "T2f-6"}
for _name, _spec in SOL_POSITIVES_R6.items():
    SOL_CASES_R6[_name] = {"kind": "positive", "name": _name, "check": "T2f-6"}

SOL_CASES.update(SOL_CASES_R6)

# ---------------------------------------------------------------------------------------------------
# T2f-7 (v1.3.13): las causas del terminal de la op cortada (W-11b) y una sola identidad cortada (X-04b).
# ---------------------------------------------------------------------------------------------------

def _r7_terminal_cut(c: dict[str, Any], at: float = 761400.0) -> None:
    be = c["samples"]["backend.jsonl"]
    be.append({"seq": len(be) + 1, "t_ms": at, "kind": "op.state",
               "data": {"op_id": "op-6", "state": "observado", "origin": "servidor",
                        "reason": "reconciliada", "at_ms": at}})


def _r7_resend(c: dict[str, Any], status: str, at: float = 762300.0, kind: str = "409") -> None:
    """Reenvío del resultado de la op cortada al backend nuevo, rechazado con 409 o 400."""
    tap = c["samples"]["bridge_tap.jsonl"]
    query_session = "d4" * 8 if kind == "409" else "e5" * 8
    reason = "lectura_no_cumple" if status == "error" else ""
    rid = _r15c_rid(c)
    sent = {"t_ms": at, "dir": "req", "method": "POST", "path": "/result", "http": 200,
            "req_id": rid,
            "query": {"peer": "server", "inst": "e3" * 16, "session": query_session,
                      "conn": "1"},
            "body": {"op_id": "op-6", "session": "d4" * 8, "epoch": "e3" * 16,
                     "status": status, "reason": reason,
                     "dup": False, "read": {}}}
    tap.append(sent)
    code = 409 if kind == "409" else 400
    error = "hello_required" if kind == "409" else "bad_request"
    rejected = {"t_ms": at + 2.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": code, "req_id": rid,
                "body": {"ok": False, "error": error}}
    tap.append(rejected)
    _r6_sort(c)


def _r7_server_restart(c: dict[str, Any], at: float = 761200.0) -> None:
    be = c["samples"]["backend.jsonl"]
    be.append({"seq": len(be) + 1, "t_ms": at, "kind": "restart",
               "data": {"target": "server", "epoch": "e3" * 16}})


def _r7_accepted_error(c: dict[str, Any], at: float = 761300.0) -> None:
    """Resultado con error de la op cortada, aceptado (200) por el backend viejo antes del corte."""
    tap = c["samples"]["bridge_tap.jsonl"]
    rid = _r15c_rid(c)
    tap.append({"t_ms": at, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid,
                "query": {"peer": "server", "inst": "e3" * 16, "session": "d4" * 8, "conn": "1"},
                "body": {"op_id": "op-6", "session": "d4" * 8, "epoch": "e3" * 16,
                         "status": "error", "reason": "lectura_no_cumple", "dup": False,
                         "read": {}}})
    tap.append({"t_ms": at + 3.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid, "body": {"ok": True}})
    _r6_sort(c)


def _r7_state(c: dict[str, Any], at: float, state: str, reason: str) -> None:
    be = c["samples"]["backend.jsonl"]
    be.append({"seq": len(be) + 1, "t_ms": at, "kind": "op.state",
               "data": {"op_id": "op-6", "state": state,
                        "origin": "backend" if state == "parcial" else "servidor",
                        "reason": reason, "at_ms": at}})


def _r7_hello(c: dict[str, Any], at: float = 761200.0) -> None:
    """Un `/hello` del servidor aceptado en la sesión que muere, con la orden en vuelo."""
    tap = c["samples"]["bridge_tap.jsonl"]
    rid = _r15c_rid(c)
    tap.append({"t_ms": at, "dir": "req", "method": "POST", "path": "/hello", "http": 200,
                "req_id": rid,
                "body": {"proto": "dsbx1", "peer": "server", "inst": "e3" * 16,
                         "epoch": "e3" * 16, "mod_ver": "f2p-mod", "build": "diag",
                         "map": "chernarusplus", "world_size": 16384,
                         "modset": ["@DayZSandbox", "@DayZSandbox_QA"],
                         "actor_engine": "none", "scene": 1}})
    tap.append({"t_ms": at + 5.0, "dir": "resp", "method": "POST", "path": "/hello",
                "http": 200, "req_id": rid,
                "body": {"ok": True, "session": "d4" * 8, "conn": 1,
                         "lease_ms": 3000, "hold_ms": 2000, "wire_cap": 3500}})
    _r6_sort(c)


def _r7_x04_second_restart(c: dict[str, Any]) -> None:
    _r6_p5_second_restart_apply2_without_result(c)


def _r7_x04_segundo_cut_765500(c: dict[str, Any]) -> None:
    _r6_p5_second_restart_apply2_without_result(c)
    c["samples"]["backend.jsonl"].append({"seq": 0, "t_ms": 765500.0, "kind": "cut",
                                          "data": {"target": "backend", "epoch": "e3" * 16}})
    _r6_sort(c)


def _r7_x04_segundo_cut_antes_761200(c: dict[str, Any]) -> None:
    _r6_p5_second_restart_apply2_without_result(c)
    c["samples"]["backend.jsonl"].append({"seq": 0, "t_ms": 761200.0, "kind": "cut",
                                          "data": {"target": "backend", "epoch": "e3" * 16}})
    _r6_sort(c)


SOL_MUTANTS_R7: dict[str, dict[str, Any]] = {
    "r7_w11_terminal_y_reenvio_error_409": {
        "apply": lambda c: (_r7_terminal_cut(c), _r7_resend(c, "error", kind="409")),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r7_w11_terminal_y_reenvio_error_400": {
        "apply": lambda c: (_r7_terminal_cut(c), _r7_resend(c, "error", kind="400")),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r7_w11_terminal_y_restart_servidor": {
        "apply": lambda c: (_r7_terminal_cut(c), _r7_server_restart(c)),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r7_w11_terminal_y_error_aceptado_antes_del_corte": {
        "apply": lambda c: (_r7_terminal_cut(c), _r7_accepted_error(c)),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_had_result"},
        "red_exit": 1},
    "r7_w11_ctrl_terminal_sin_causa": {
        "apply": _r7_terminal_cut,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 1},
    "r7_w11_terminal_y_reenvio_done_409": {
        "apply": lambda c: (_r7_terminal_cut(c), _r7_resend(c, "done", kind="409")),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 1},
    "r7_x04_ctrl_sin_segundo_cut": {
        "apply": _r7_x04_second_restart,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 1},
    "r7_x04_segundo_cut_765500": {
        "apply": _r7_x04_segundo_cut_765500,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r7_x04_segundo_cut_antes_761200": {
        "apply": _r7_x04_segundo_cut_antes_761200,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 1},
}

SOL_POSITIVES_R7: dict[str, dict[str, Any]] = {
    "r7_w11_ctrl_reenvio_error_409_sin_terminal": {
        "apply": lambda c: _r7_resend(c, "error", kind="409"),
        "expected_exit_code": 0,
        "red_exit": 0},
    "r7_w11_ctrl_reenvio_error_400_sin_terminal": {
        "apply": lambda c: _r7_resend(c, "error", kind="400"),
        "expected_exit_code": 0,
        "red_exit": 0},
    "r7_w11_ctrl_sin_resultado_solo": {
        "apply": lambda c: _r7_state(c, 761400.0, "parcial", "sin_resultado"),
        "expected_exit_code": 0,
        "red_exit": 0},
    "r7_w11_sin_resultado_y_luego_reconciliada": {
        "apply": lambda c: (_r7_state(c, 761300.0, "parcial", "sin_resultado"),
                            _r7_terminal_cut(c)),
        "expected_exit_code": 0,
        "red_exit": 1},
    "r7_w11_ctrl_reconexion_servidor_con_hello": {
        "apply": lambda c: (_r7_terminal_cut(c), _r7_server_restart(c), _r7_hello(c)),
        "expected_exit_code": 0,
        "red_exit": 0},
}

# --- T2f-7b: Y-01, Y-02, Y-03, Y-04, Y-07, Y-08 e Y-06 -----------------------------------------

def _r7_seq_bump(c: dict[str, Any]) -> None:
    """Control base de Y-01: cambio inerte (`seq`, campo que el oráculo no lee)."""
    for ev in c["samples"]["backend.jsonl"]:
        if isinstance(ev.get("seq"), int):
            ev["seq"] = ev["seq"] + 1000


def _r7_witness_dy(c: dict[str, Any], tag: str, net: str, sample_idx: int, dy: float) -> None:
    def fn(rows: list[dict[str, Any]]) -> None:
        for r in rows:
            if str(r.get("net_id")) == net and int(r.get("sample_idx", -1)) == sample_idx:
                r["pos_y_m"] = float(r["pos_y_m"]) + dy
    _edit_rows(c, tag, fn)


def _r7_y01_p4a_apply2_dy(c: dict[str, Any], dy: float) -> None:
    net = _r6_birth_net(c, "P4a", "apply2")
    if net is None:
        return
    _mutate_row(c, "P4a:post_apply2", lambda r: str(r.get("net_id")) == net,
                lambda r: r.__setitem__("pos_y_m", float(r["pos_y_m"]) + dy))


def _r7_y01_p4a_apply2_born_dy(c: dict[str, Any], dy: float) -> None:
    net = _r6_birth_net(c, "P4a", "apply2")
    if net is None:
        return
    _r7_witness_dy(c, "P4a:apply2", net, 0, dy)


def _r7_y01_p4a_apply1_dy(c: dict[str, Any], dy: float) -> None:
    net = _r6_birth_net(c, "P4a", "apply1")
    if net is None:
        return
    _mutate_row(c, "P4a:post_apply1", lambda r: str(r.get("net_id")) == net,
                lambda r: r.__setitem__("pos_y_m", float(r["pos_y_m"]) + dy))


def _r7_y02_drop_apply2(c: dict[str, Any]) -> None:
    _r6_drop_result_and_ack(c, "e5" * 8, "op-1", 764000.0, 765400.0)


def _r7_y02_add_cut(c: dict[str, Any], t: float = 764500.0) -> None:
    c["samples"]["backend.jsonl"].append({"seq": 0, "t_ms": t, "kind": "cut",
                                          "data": {"target": "backend", "epoch": "e3" * 16}})
    _r6_sort(c)


_R7_SHIFT = {762000.0: 763580.0, 762052.0: 763600.0, 762100.0: 763620.0, 762105.0: 763625.0,
             762110.0: 763630.0, 762500.0: 763700.0, 763000.0: 763800.0, 763003.0: 763803.0}


def _r7_y03_shift(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"] + c["samples"]["backend.jsonl"]:
        t = float(ev.get("t_ms") or 0.0)
        if t in _R7_SHIFT:
            ev["t_ms"] = _R7_SHIFT[t]
            if isinstance(ev.get("data"), dict) and "at_ms" in ev["data"]:
                ev["data"]["at_ms"] = _R7_SHIFT[t]
    _r6_sort(c)


def _r7_y03_add_op7(c: dict[str, Any]) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    be = c["samples"]["backend.jsonl"]
    rid = _r15c_rid(c)
    tap.append({"t_ms": 763539.5, "dir": "req", "method": "GET", "path": "/poll", "req_id": rid,
                "query": {"peer": "server", "inst": "e3" * 16, "session": "d4" * 8,
                          "conn": "1", "deliver": "1"}})
    tap.append({"t_ms": 763540.0, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid,
                "body": {"ok": True, "now_ms": 763540.0, "ops": [
                    {"op_id": "op-7", "session": "d4" * 8, "conn": 1, "epoch": "e3" * 16,
                     "inst": "e3" * 16, "verb": "scene.apply",
                     "args": {"f2": 1, "doc_id": "d-7c19e2a5"},
                     "issued_ms": 763490.0, "ttl_ms": 5000}]}})
    be.append({"seq": 0, "t_ms": 763530.0, "kind": "op.state",
               "data": {"op_id": "op-7", "state": "pendiente", "origin": "backend",
                        "reason": None, "at_ms": 763530.0}})
    be.append({"seq": 0, "t_ms": 763560.0, "kind": "op.state",
               "data": {"op_id": "op-7", "state": "observado", "origin": "servidor",
                        "reason": None, "at_ms": 763560.0}})
    _r6_sort(c)


def _r7_y04_p4a_reset_fallido(c: dict[str, Any]) -> None:
    _r6_terminal(c, 551000.0, 762000.0, "op-2", "fallido", "lectura_no_cumple",
                 result_session="d4" * 8, result_status="error",
                 result_reason="lectura_no_cumple")


def _r7_y04_redeliver(c: dict[str, Any]) -> None:
    src = _r6_delivery_op(c, "c3" * 8, "op-3")
    if src is None:
        return
    o2 = copy.deepcopy(src)
    tap = c["samples"]["bridge_tap.jsonl"]
    rid_poll = _r15c_rid(c)
    rid_result = rid_poll + 1
    tap.append({"t_ms": 550199.5, "dir": "req", "method": "GET", "path": "/poll",
                "req_id": rid_poll,
                "query": {"peer": "server", "inst": "e1" * 16, "session": "c3" * 8,
                          "conn": "1", "deliver": "1"}})
    tap.append({"t_ms": 550200.0, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
                "req_id": rid_poll,
                "body": {"ok": True, "now_ms": 550200.0, "ops": [o2]}})
    tap.append({"t_ms": 550500.0, "dir": "req", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result,
                "query": {"peer": "server", "inst": "e1" * 16, "session": "c3" * 8, "conn": "1"},
                "body": {"op_id": "op-3", "session": "c3" * 8, "epoch": "e1" * 16,
                         "status": "done", "reason": "", "dup": True, "read": {}}})
    tap.append({"t_ms": 550503.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid_result, "body": {"ok": True}})
    _r6_sort(c)


def _r7_y07_move_reset_terminal(c: dict[str, Any], t_new: float) -> None:
    for ev in c["samples"]["backend.jsonl"]:
        d = ev.get("data") or {}
        if ev.get("kind") == "op.state" and d.get("op_id") == "op-3" and \
                float(ev["t_ms"]) == 314500.0:
            ev["t_ms"] = t_new
            d["at_ms"] = t_new
    _r6_sort(c)


def _r7_y08_set_doc(c: dict[str, Any], doc_id: str) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and o.get("verb") == "scene.reset" and \
                        str(o.get("session")) == "d4" * 8 and o.get("op_id") == "op-5":
                    o["args"]["doc_id"] = doc_id


def _r7_y08c_shift(c: dict[str, Any], dt: float = 14000.0) -> None:
    lo, hi = 690800.0, 692600.0
    for entry in c["samples"]["bridge_tap.jsonl"] + c["samples"]["backend.jsonl"]:
        when = float(entry.get("t_ms") or 0.0)
        if when < lo or when > hi:
            continue
        kind = entry.get("kind")
        path = entry.get("path")
        way = entry.get("dir")
        if kind == "op.state":
            payload = entry.get("data") or {}
            if payload.get("op_id") == "op-5":
                entry["t_ms"] = when + dt
                payload["at_ms"] = when + dt
        elif path == "/poll" and way == "resp":
            orders = (entry.get("body") or {}).get("ops") or []
            resets = [order for order in orders
                      if order.get("op_id") == "op-5" and order.get("verb") == "scene.reset"]
            if not resets:
                continue
            entry["t_ms"] = when + dt
            entry["body"].update({"now_ms": when + dt})
            for order in orders:
                order["inst"] = "e3" * 16
                order["epoch"] = "e3" * 16
        elif path == "/result":
            payload = entry.get("body") or {}
            if way == "req" and payload.get("op_id") == "op-5":
                entry["t_ms"] = when + dt
                payload["epoch"] = "e3" * 16
                entry["query"]["inst"] = "e3" * 16
            elif way == "resp" and when == 692003.0:
                entry["t_ms"] = when + dt
    _r6_sort(c)


def _r7_y08d_scene2_world(c: dict[str, Any]) -> None:
    _r7_y08_set_doc(c, "d-2f2a5c01")
    lo, hi = _r5_part_window(c, "P4c")
    kept = []
    for row in c["samples"]["scene_del.jsonl"]:
        when = float(row.get("t_ms") or 0.0)
        if when < lo or when > hi:
            kept.append(row)
    c["samples"]["scene_del.jsonl"] = kept
    born = _birth_nets(c, "P4b:apply")
    carried = []
    _start, pages = _job_events(c, "P4c:pre_reset")
    for event in pages:
        unpacked = _unpack(event["result"]["read"])
        if not unpacked:
            continue
        for row in unpacked[2]:
            if str(row.get("net_id")) in born:
                carried.append(row)
    for row in carried:
        _add_row(c, "P4c:post_reset", copy.deepcopy(row))


def _r7_y06_ctrl(c: dict[str, Any]) -> None:
    _r7_terminal_cut(c)


def _r7_y06a(c: dict[str, Any]) -> None:
    _r7_state(c, 761300.0, "parcial", "sin_resultado")
    _r7_terminal_cut(c)


def _r7_y06b(c: dict[str, Any]) -> None:
    _r7_hello(c)
    _r7_terminal_cut(c)


SOL_MUTANTS_R7.update({
    "r7_y01_P4a_apply2_censo_sube_1m": {
        "apply": lambda c: _r7_y01_p4a_apply2_dy(c, 1.0),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "obj-01:pose"},
        "red_exit": 0},
    "r7_y01_P4a_apply2_censo_baja_1p5m": {
        "apply": lambda c: _r7_y01_p4a_apply2_dy(c, -1.5),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "obj-01:pose"},
        "red_exit": 0},
    "r7_y01_P4a_apply2_nace_1p9m_alto": {
        "apply": lambda c: _r7_y01_p4a_apply2_born_dy(c, 1.9),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "obj-01:pose"},
        "red_exit": 0},
    "r7_y01_P4a_apply1_censo_sube_1m": {
        "apply": lambda c: _r7_y01_p4a_apply1_dy(c, 1.0),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "obj-01:apply1_pose"},
        "red_exit": 0},
    "r7_y02a_P5_apply2_sin_result_sin_segundo_cut": {
        "apply": _r7_y02_drop_apply2,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 1},
    "r7_y02b_P5_apply2_sin_result_con_segundo_cut": {
        "apply": lambda c: (_r7_y02_drop_apply2(c), _r7_y02_add_cut(c)),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r7_y03a_P5_op7_tras_cut_sin_result": {
        "apply": lambda c: (_r7_y03_shift(c), _r7_y03_add_op7(c)),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r7_y04a_P3c_reset_reentregado_en_P4a_reset_fallido": {
        "apply": lambda c: (_r7_y04_redeliver(c), _r7_y04_p4a_reset_fallido(c)),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "reset_state=fallido/lectura_no_cumple"},
        "red_exit": 0},
    "r7_y04b_P3c_reset_reentregado_en_P4a_reset_reconciliada": {
        "apply": lambda c: (_r7_y04_redeliver(c),
                            _r6_terminal(c, 551000.0, 762000.0, "op-2", "observado",
                                         "reconciliada")),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "reset_state=observado/reconciliada"},
        "red_exit": 0},
    "r7_y04_ctrl_P4a_reset_fallido_sin_reentrega": {
        "apply": _r7_y04_p4a_reset_fallido,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "reset_state=fallido/lectura_no_cumple"},
        "red_exit": 1},
    "r7_y07a_P2n_reset_terminal_tras_censo_clean": {
        "apply": lambda c: _r7_y07_move_reset_terminal(c, 315100.0),
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-03": "missing"},
        "must_detail": {"F2P-03": "unbacked_rows"},
        "red_exit": 0},
    "r7_y07b_P2n_reset_terminal_tras_todos_los_discos": {
        "apply": lambda c: _r7_y07_move_reset_terminal(c, 330000.0),
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-03": "missing"},
        "must_detail": {"F2P-03": "unbacked_rows"},
        "red_exit": 0},
    "r7_y08a_P4c_reset_de_la_escena2": {
        "apply": lambda c: _r7_y08_set_doc(c, "d-2f2a5c01"),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "p4c_reset_escena1_ausente"},
        "red_exit": 0},
    "r7_y08b_P4c_reset_de_un_doc_ajeno": {
        "apply": lambda c: _r7_y08_set_doc(c, "d-00000000"),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "p4c_reset_escena1_ausente"},
        "red_exit": 0},
    "r7_y08c_P4c_reset_despues_del_reinicio_y_del_censo": {
        "apply": _r7_y08c_shift,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "p4c_reset_escena1_ausente"},
        "red_exit": 0},
    "r7_y08d_P4c_reset_escena2_mundo_coherente": {
        "apply": _r7_y08d_scene2_world,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "p4c_reset_escena1_ausente"},
        "red_exit": 0},
    "r7_y06_ctrl_reconciliada_sin_causa": {
        "apply": _r7_y06_ctrl,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 1},
})

SOL_POSITIVES_R7.update({
    "r7_y01_ctrl_base": {
        "apply": _r7_seq_bump,
        "expected_exit_code": 0,
        "red_exit": 0},
    "r7_y02c_P5_segundo_cut_sin_mas": {
        "apply": _r7_y02_add_cut,
        "expected_exit_code": 0,
        "red_exit": 0},
    "r7_y03_ctrl_tramo_nuevo_corrido": {
        "apply": _r7_y03_shift,
        "expected_exit_code": 0,
        "red_exit": 0},
    "r7_y04_redelivery_only": {
        "apply": _r7_y04_redeliver,
        "expected_exit_code": 0,
        "red_exit": 0},
    "r7_y06a_sin_resultado_y_reconciliada": {
        "apply": _r7_y06a,
        "expected_exit_code": 0,
        "red_exit": 1},
    "r7_y06b_rehello_servidor_y_reconciliada": {
        "apply": _r7_y06b,
        "expected_exit_code": 0,
        "red_exit": 1},
})

SOL_NEGATIVES_R7: dict[str, dict[str, Any]] = {}

SOL_CASES_R7: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R7.items():
    SOL_CASES_R7[_name] = {"kind": "mutant", "name": _name, "check": "T2f-7"}
for _name, _spec in SOL_NEGATIVES_R7.items():
    SOL_CASES_R7[_name] = {"kind": "negative", "name": _name, "check": "T2f-7"}
for _name, _spec in SOL_POSITIVES_R7.items():
    SOL_CASES_R7[_name] = {"kind": "positive", "name": _name, "check": "T2f-7"}

SOL_CASES.update(SOL_CASES_R7)

# ---------------------------------------------------------------------------------------------------
# T2f-8: los PASA falsos de la pasada de Claude sobre T2f-7 (Z-01..Z-07).
# ---------------------------------------------------------------------------------------------------

def _r8_move_op_state(c: dict[str, Any], op_id: str, t_old: float, t_new: float,
                      state: str | None = None, reason: str | None = None) -> None:
    hit = 0
    for ev in c["samples"]["backend.jsonl"]:
        d = ev.get("data") or {}
        if ev.get("kind") == "op.state" and d.get("op_id") == op_id and \
                float(ev["t_ms"]) == t_old:
            ev["t_ms"] = t_new
            d["at_ms"] = t_new
            if state is not None:
                d["state"] = state
            if reason is not None:
                d["reason"] = reason
            hit += 1
    assert hit == 1, (op_id, t_old, hit)
    _r6_sort(c)


def _r8_add_op_state(c: dict[str, Any], t: float, op_id: str, state: str,
                     reason: str | None = None, origin: str = "backend") -> None:
    c["samples"]["backend.jsonl"].append({
        "seq": len(c["samples"]["backend.jsonl"]) + 1, "t_ms": t, "kind": "op.state",
        "data": {"op_id": op_id, "state": state, "origin": origin, "reason": reason,
                 "at_ms": t}})
    _r6_sort(c)


def _r8_server_hello_fields(c: dict[str, Any]) -> dict[str, Any]:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        b = ev.get("body") or {}
        if ev.get("dir") == "req" and ev.get("path") == "/hello" and b.get("peer") == "server":
            return {k: b[k] for k in b if k not in ("inst", "epoch")}
    return {}


def _r8_add_server_hello(c: dict[str, Any], t: float, session: str,
                         inst: str | None = None, epoch: str | None = None,
                         peer: str = "server") -> None:
    body = dict(_r8_server_hello_fields(c))
    body["peer"] = peer
    body["inst"] = inst or ("e3" * 16)
    body["epoch"] = epoch or ("e3" * 16)
    tap = c["samples"]["bridge_tap.jsonl"]
    rid = _r15c_rid(c)
    tap.append({"t_ms": t, "dir": "req", "method": "POST", "path": "/hello", "http": 200,
                "req_id": rid, "body": body})
    tap.append({"t_ms": t + 5.0, "dir": "resp", "method": "POST", "path": "/hello",
                "http": 200, "req_id": rid, "body": {"ok": True, "session": session}})
    _r6_sort(c)


def _r8_z05_cause_b(c: dict[str, Any], terminal_state: str, terminal_reason: str) -> None:
    _r8_add_op_state(c, 761300.0, "op-6", "parcial", "sin_resultado")
    _r8_add_op_state(c, 761400.0, "op-6", terminal_state, terminal_reason, origin="servidor")


def _r8_z05a(c: dict[str, Any]) -> None:
    _r8_z05_cause_b(c, "observado", "")


def _r8_z05b(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 761200.0, "d4" * 8)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "", origin="servidor")


def _r8_z05c(c: dict[str, Any]) -> None:
    _r8_z05_cause_b(c, "fallido", "create_failed")


def _r8_z05d(c: dict[str, Any]) -> None:
    _r8_z05_cause_b(c, "parcial", "compensada")


def _r8_z05_ctrl(c: dict[str, Any]) -> None:
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "", origin="servidor")


def _r8_z03_before(c: dict[str, Any], t_sin: float) -> None:
    _r8_add_op_state(c, t_sin, "op-6", "parcial", "sin_resultado")
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r8_z03a(c: dict[str, Any]) -> None:
    _r8_z03_before(c, 760950.0)


def _r8_z03b(c: dict[str, Any]) -> None:
    _r8_z03_before(c, 760850.0)


def _r8_z03_ctrl_after(c: dict[str, Any]) -> None:
    _r8_z03_before(c, 761300.0)


def _r8_z03_ctrl_no_cause(c: dict[str, Any]) -> None:
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r8_z04a(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 761600.0, "d4" * 8)
    _r8_add_op_state(c, 761800.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r8_z04b(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 760950.0, "d4" * 8)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r8_z04c(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 761200.0, "d4" * 8, peer="client")
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r8_z04d(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 761200.0, "d4" * 8, inst="e4" * 16, epoch="e4" * 16)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r8_z01a(c: dict[str, Any]) -> None:
    _r8_move_op_state(c, "op-2", 558500.0, 570100.0)


def _r8_z01b(c: dict[str, Any]) -> None:
    _r8_move_op_state(c, "op-2", 558500.0, 605000.0)


def _r8_z02a(c: dict[str, Any]) -> None:
    _r8_move_op_state(c, "op-5", 692500.0, 701100.0)


def _r8_z02b(c: dict[str, Any]) -> None:
    _r8_move_op_state(c, "op-5", 692500.0, 740000.0)


def _r8_z06a(c: dict[str, Any]) -> None:
    _r8_move_op_state(c, "op-2", 312500.0, 315100.0)


def _r8_z06b(c: dict[str, Any]) -> None:
    _r8_move_op_state(c, "op-2", 312500.0, 350000.0)


def _r8_p3_pre_apply1_late(c: dict[str, Any]) -> None:
    _r8_move_op_state(c, "op-4", 372500.0, 381000.0)


def _r8_z07_op7_resolved(c: dict[str, Any]) -> None:
    _r7_y03_shift(c)
    _r7_y03_add_op7(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    rid = _r15c_rid(c)
    tap.append({"t_ms": 763550.0, "dir": "req", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid,
                "query": {"peer": "server", "inst": "e3" * 16, "session": "d4" * 8,
                          "conn": "1"},
                "body": {"op_id": "op-7", "session": "d4" * 8, "epoch": "e3" * 16,
                         "status": "done", "reason": "", "dup": False, "read": {}}})
    tap.append({"t_ms": 763553.0, "dir": "resp", "method": "POST", "path": "/result",
                "http": 200, "req_id": rid, "body": {"ok": True}})
    _r6_sort(c)


def _r8_z07a(c: dict[str, Any]) -> None:
    _r8_z07_op7_resolved(c)
    _r8_move_op_state(c, "op-1", 765500.0, 766100.0)


def _r8_z07_ctrl_late_no_op7(c: dict[str, Any]) -> None:
    _r7_y03_shift(c)
    _r8_move_op_state(c, "op-1", 765500.0, 766100.0)


SOL_MUTANTS_R8: dict[str, dict[str, Any]] = {
    "r8_z05a_causa_b_y_observado_vacio": {
        "apply": _r8_z05a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/"},
        "red_exit": 0},
    "r8_z05b_causa_c_y_observado_vacio": {
        "apply": _r8_z05b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/"},
        "red_exit": 0},
    "r8_z05c_causa_b_y_fallido": {
        "apply": _r8_z05c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=fallido/create_failed"},
        "red_exit": 0},
    "r8_z05d_causa_b_y_compensada": {
        "apply": _r8_z05d,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=parcial/compensada"},
        "red_exit": 0},
    "r8_z05_ctrl_observado_sin_causa": {
        "apply": _r8_z05_ctrl,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/"},
        "red_exit": 1},
    "r8_z03a_sin_resultado_antes_de_la_entrega": {
        "apply": _r8_z03a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r8_z03b_sin_resultado_antes_del_pendiente": {
        "apply": _r8_z03b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r8_z03_ctrl_reconciliada_sin_causa": {
        "apply": _r8_z03_ctrl_no_cause,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 1},
    "r8_z04a_hello_tras_el_cut": {
        "apply": _r8_z04a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r8_z04b_hello_antes_de_la_entrega": {
        "apply": _r8_z04b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 1},
    "r8_z04c_hello_del_client": {
        "apply": _r8_z04c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 1},
    "r8_z04d_hello_otra_instancia": {
        "apply": _r8_z04d,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r8_z01a_P4a_reset_terminal_tras_censo": {
        "apply": _r8_z01a,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-08": "missing"},
        "must_detail": {"F2P-08": "unbacked_rows"},
        "red_exit": 0},
    "r8_z01b_P4a_reset_terminal_al_final": {
        "apply": _r8_z01b,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-08": "missing"},
        "must_detail": {"F2P-08": "unbacked_rows"},
        "red_exit": 0},
    "r8_z02a_P4c_reset_terminal_tras_censo": {
        "apply": _r8_z02a,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "unbacked_rows"},
        "red_exit": 0},
    "r8_z02b_P4c_reset_terminal_al_final": {
        "apply": _r8_z02b,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "unbacked_rows"},
        "red_exit": 0},
    "r8_z06a_P2n_apply_terminal_tras_censo": {
        "apply": _r8_z06a,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-03": "missing"},
        "must_detail": {"F2P-03": "unbacked_rows"},
        "red_exit": 0},
    "r8_z06b_P2n_apply_terminal_al_final": {
        "apply": _r8_z06b,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-03": "missing"},
        "must_detail": {"F2P-03": "unbacked_rows"},
        "red_exit": 0},
    "r8_z07a_op7_resuelto_y_terminal_nuevo_tras_censo": {
        "apply": _r8_z07a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r8_z07_ctrl_terminal_nuevo_tarde_sin_op7": {
        "apply": _r8_z07_ctrl_late_no_op7,
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-09": "missing"},
        "must_detail": {"F2P-09": "unbacked_rows"},
        "red_exit": 2},
    # v1.3.13 (A-01): la `op-7` de la sesión que muere se entrega y se resuelve después del cut;
    # la traza la caza. Deja de ser positiva y pasa a mutante con el mismo nombre.
    "r8_z07_ctrl_op7_resuelto": {
        "apply": _r8_z07_op7_resolved,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
}

SOL_POSITIVES_R8: dict[str, dict[str, Any]] = {
    "r8_z01_ctrl_base": {
        "apply": _r7_seq_bump,
        "expected_exit_code": 0,
        "red_exit": 0},
    "r8_z03_ctrl_sin_resultado_tras_la_entrega": {
        "apply": _r8_z03_ctrl_after,
        "expected_exit_code": 0,
        "red_exit": 0},
}

SOL_NEGATIVES_R8: dict[str, dict[str, Any]] = {}

SOL_CASES_R8: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R8.items():
    SOL_CASES_R8[_name] = {"kind": "mutant", "name": _name, "check": "T2f-8"}
for _name, _spec in SOL_NEGATIVES_R8.items():
    SOL_CASES_R8[_name] = {"kind": "negative", "name": _name, "check": "T2f-8"}
for _name, _spec in SOL_POSITIVES_R8.items():
    SOL_CASES_R8[_name] = {"kind": "positive", "name": _name, "check": "T2f-8"}

SOL_CASES.update(SOL_CASES_R8)

# ---------------------------------------------------------------------------------------------------
# T2f-9: los PASA falsos de la pasada de Claude sobre T2f-8 (A-01, A-02 y A-03).
# ---------------------------------------------------------------------------------------------------

def _r9_set_cut_inst(c: dict[str, Any], inst: str | None) -> None:
    hit = 0
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll" and \
                float(ev.get("t_ms") or 0.0) == 761000.0:
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and o.get("op_id") == "op-6":
                    if inst is None:
                        o.pop("inst", None)
                    else:
                        o["inst"] = inst
                    hit += 1
    assert hit == 1, hit


def _r9_drop_hello_inst(c: dict[str, Any], t: float) -> None:
    hit = 0
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "req" and ev.get("path") == "/hello" and \
                float(ev.get("t_ms") or 0.0) == t:
            ev["body"].pop("inst", None)
            hit += 1
    assert hit == 1, hit


def _r9_a01a(c: dict[str, Any]) -> None:
    _r8_add_op_state(c, 761600.0, "op-6", "parcial", "sin_resultado")
    _r8_add_op_state(c, 761700.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a01b(c: dict[str, Any]) -> None:
    _r8_add_op_state(c, 761300.0, "op-6", "parcial", "sin_resultado")
    _r8_add_op_state(c, 761700.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a01c(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 761200.0, "d4" * 8)
    _r8_add_op_state(c, 761700.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a01_ctrl(c: dict[str, Any]) -> None:
    _r8_add_op_state(c, 761300.0, "op-6", "parcial", "sin_resultado")
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a02(c: dict[str, Any], first_state: str, first_reason: str, cause: str = "b") -> None:
    _r8_add_op_state(c, 761200.0, "op-6", first_state, first_reason, origin="servidor")
    if cause == "b":
        _r8_add_op_state(c, 761300.0, "op-6", "parcial", "sin_resultado")
    else:
        _r8_add_server_hello(c, 761300.0, "d4" * 8)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a02a(c: dict[str, Any]) -> None:
    _r9_a02(c, "observado", "")


def _r9_a02b(c: dict[str, Any]) -> None:
    _r9_a02(c, "fallido", "create_failed")


def _r9_a02c(c: dict[str, Any]) -> None:
    _r9_a02(c, "parcial", "compensada")


def _r9_a02d(c: dict[str, Any]) -> None:
    _r9_a02(c, "observado", "", cause="c")


def _r9_a02_ctrl(c: dict[str, Any]) -> None:
    _r8_add_op_state(c, 761300.0, "op-6", "parcial", "sin_resultado")
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a02e(c: dict[str, Any]) -> None:
    _r8_add_op_state(c, 761300.0, "op-6", "parcial", "sin_resultado")
    _r8_add_op_state(c, 761350.0, "op-6", "observado", "reconciliada", origin="servidor")
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a03a(c: dict[str, Any]) -> None:
    _r9_set_cut_inst(c, None)
    _r8_add_server_hello(c, 761200.0, "d4" * 8)
    _r9_drop_hello_inst(c, 761200.0)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a03b(c: dict[str, Any]) -> None:
    _r9_set_cut_inst(c, "e4" * 16)
    _r8_add_server_hello(c, 761200.0, "d4" * 8, inst="e4" * 16, epoch="e4" * 16)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a03c(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 761200.0, "d4" * 8, inst="e3" * 16, epoch="e4" * 16)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r9_a03_ctrl_legit(c: dict[str, Any]) -> None:
    _r8_add_server_hello(c, 761200.0, "d4" * 8)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


SOL_MUTANTS_R9: dict[str, dict[str, Any]] = {
    "r9_a01a_causa_b_y_terminal_tras_el_cut": {
        "apply": _r9_a01a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r9_a01b_causa_b_antes_y_terminal_tras_el_cut": {
        "apply": _r9_a01b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r9_a01c_causa_c_antes_y_terminal_tras_el_cut": {
        "apply": _r9_a01c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r9_a02a_observado_vacio_tapado_por_reconciliada": {
        "apply": _r9_a02a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/"},
        "red_exit": 0},
    "r9_a02b_fallido_tapado_por_reconciliada": {
        "apply": _r9_a02b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=fallido/create_failed"},
        "red_exit": 0},
    "r9_a02c_compensada_tapada_por_reconciliada": {
        "apply": _r9_a02c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=parcial/compensada"},
        "red_exit": 0},
    "r9_a02d_observado_vacio_tapado_causa_c": {
        "apply": _r9_a02d,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/"},
        "red_exit": 0},
    "r9_a02e_dos_reconciliada_antes_del_cut": {
        "apply": _r9_a02e,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminals=2"},
        "red_exit": 0},
    "r9_a03a_sin_inst_en_entrega_ni_hello": {
        "apply": _r9_a03a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r9_a03b_inst_de_la_entrega_falsificado": {
        "apply": _r9_a03b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r9_a03c_misma_inst_otro_epoch": {
        "apply": _r9_a03c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
}

SOL_POSITIVES_R9: dict[str, dict[str, Any]] = {
    "r9_a01_ctrl_causa_b_y_terminal_antes_del_cut": {
        "apply": _r9_a01_ctrl,
        "expected_exit_code": 0,
        "red_exit": 0},
    "r9_a02_ctrl_sin_primer_terminal": {
        "apply": _r9_a02_ctrl,
        "expected_exit_code": 0,
        "red_exit": 0},
    "r9_a03_ctrl_legit_misma_instancia": {
        "apply": _r9_a03_ctrl_legit,
        "expected_exit_code": 0,
        "red_exit": 0},
}

SOL_NEGATIVES_R9: dict[str, dict[str, Any]] = {}

SOL_CASES_R9: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R9.items():
    SOL_CASES_R9[_name] = {"kind": "mutant", "name": _name, "check": "T2f-9"}
for _name, _spec in SOL_NEGATIVES_R9.items():
    SOL_CASES_R9[_name] = {"kind": "negative", "name": _name, "check": "T2f-9"}
for _name, _spec in SOL_POSITIVES_R9.items():
    SOL_CASES_R9[_name] = {"kind": "positive", "name": _name, "check": "T2f-9"}

SOL_CASES.update(SOL_CASES_R9)

# ---------------------------------------------------------------------------------------------------
# T2f-10: los PASA falsos de la pasada de Claude sobre T2f-9 (B-01, B-02, B-03 y B-04).
# ---------------------------------------------------------------------------------------------------

def _r10_rd1_read(c: dict[str, Any]) -> dict[str, Any]:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        b = ev.get("body") or {}
        if ev.get("dir") == "req" and ev.get("path") == "/result" and b.get("op_id") == "rd-1":
            return copy.deepcopy(b.get("read") or {})
    raise KeyError("rd-1")


def _r10_p5_apply_args(c: dict[str, Any], op_id: str = "op-6",
                       session: str = "d4" * 8) -> dict[str, Any]:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") == "resp" and ev.get("path") == "/poll":
            for o in (ev.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and o.get("op_id") == op_id and \
                        o.get("session") == session and o.get("verb") == "scene.apply":
                    return copy.deepcopy(o.get("args") or {})
    raise KeyError(op_id)


def _r10_add_delivery(c: dict[str, Any], t: float, op_id: str, session: str, verb: str,
                      args: dict[str, Any], inst: str | None = None,
                      epoch: str | None = None, rid: int | None = None) -> None:
    rid = _r15c_rid(c) if rid is None else rid
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": t - 0.5, "dir": "req", "method": "GET", "path": "/poll",
                "req_id": rid,
                "query": {"peer": "server", "inst": inst or "e3" * 16, "session": session,
                          "conn": "1", "deliver": "1"}})
    tap.append({
        "t_ms": t, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
        "req_id": rid,
        "body": {"ok": True, "now_ms": t, "ops": [
            {"op_id": op_id, "session": session, "conn": 1, "epoch": epoch or "e3" * 16,
             "inst": inst or "e3" * 16, "verb": verb, "args": copy.deepcopy(args),
             "issued_ms": t - 5.0, "ttl_ms": 5000}]}})
    _r6_sort(c)


def _r10_add_result(c: dict[str, Any], t: float, op_id: str, session: str,
                    read: dict[str, Any] | None = None, ack_dt: float = 3.0,
                    http: int = 200, ok: bool = True, inst: str | None = None,
                    epoch: str | None = None, rid: int | None = None) -> None:
    rid = _r15c_rid(c) if rid is None else rid
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": t, "dir": "req", "method": "POST", "path": "/result", "http": 200,
                "req_id": rid,
                "query": {"peer": "server", "inst": inst or "e3" * 16, "session": session,
                          "conn": "1"},
                "body": {"op_id": op_id, "session": session, "epoch": epoch or "e3" * 16,
                         "status": "done", "reason": "", "dup": False,
                         "read": copy.deepcopy(read) if read else {}}})
    tap.append({"t_ms": t + ack_dt, "dir": "resp", "method": "POST", "path": "/result",
                "http": http, "req_id": rid, "body": {"ok": ok}})
    _r6_sort(c)


def _r10_add_hello(c: dict[str, Any], t_req: float, t_resp: float, session: str | None,
                   peer: str = "server", inst: str | None = None, epoch: str | None = None,
                   http: int = 200, ok: bool = True, with_resp: bool = True,
                   world_size: int | None = None, rid: int | None = None) -> int:
    body = dict(_r8_server_hello_fields(c))
    body["peer"] = peer
    body["inst"] = inst or ("e3" * 16)
    body["epoch"] = epoch or ("e3" * 16)
    if world_size is not None:
        body["world_size"] = world_size
    rid = _r15c_rid(c) if rid is None else rid
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": t_req, "dir": "req", "method": "POST", "path": "/hello",
                "http": http, "req_id": rid, "body": body})
    if with_resp:
        resp = {"ok": ok}
        if session:
            resp["session"] = session
            resp["conn"] = 1
        tap.append({"t_ms": t_resp, "dir": "resp", "method": "POST", "path": "/hello",
                    "http": http, "req_id": rid, "body": resp})
    _r6_sort(c)
    return rid


def _r10_b01(c: dict[str, Any], t_deliv: float, t_res: float, op_id: str = "rd-9",
             verb: str = "state.read", with_result: bool = True) -> None:
    if verb == "scene.apply":
        args = _r10_p5_apply_args(c, "op-6", "d4" * 8)
    else:
        args = {"f2": 1, "doc_id": "d-7c19e2a5"}
    _r10_add_delivery(c, t_deliv, op_id, "d4" * 8, verb, args)
    if with_result:
        _r10_add_result(c, t_res, op_id, "d4" * 8, read=_r10_rd1_read(c))


def _r10_b01a(c: dict[str, Any]) -> None:
    _r10_b01(c, 761700.0, 761800.0)


def _r10_b01b(c: dict[str, Any]) -> None:
    _r10_b01(c, 762300.0, 762400.0)


def _r10_b01c(c: dict[str, Any]) -> None:
    _r10_b01(c, 761200.0, 761700.0, verb="scene.observe")


def _r10_b01d(c: dict[str, Any]) -> None:
    _r10_b01(c, 761700.0, 761800.0, verb="scene.apply")


def _r10_b01_ctrl_op9(c: dict[str, Any]) -> None:
    _r10_b01(c, 761700.0, 761800.0, op_id="op-9")


def _r10_b01_ctrl_sin_resultado(c: dict[str, Any]) -> None:
    _r10_b01(c, 761700.0, 761800.0, with_result=False)


def _r10_sol_rd99(c: dict[str, Any]) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    rid_poll = _r15c_rid(c)
    rid_result = rid_poll + 1
    for source, target, rid in ((762500.0, 761600.0, rid_poll),
                                (763000.0, 761610.0, rid_result),
                                (763003.0, 761613.0, rid_result)):
        e = copy.deepcopy(next(x for x in tap if float(x.get("t_ms") or 0.0) == source))
        e["t_ms"] = target
        e["req_id"] = rid
        if e.get("path") == "/poll":
            e["body"]["now_ms"] = target
            e["body"]["ops"][0].update(session="d4" * 8, op_id="rd-99",
                                       issued_ms=target - 5.0)
            tap.append({"t_ms": target - 0.5, "dir": "req", "method": "GET",
                        "path": "/poll", "req_id": rid,
                        "query": {"peer": "server", "inst": "e3" * 16,
                                  "session": "d4" * 8, "conn": "1", "deliver": "1"}})
        elif e.get("dir") == "req":
            e["query"]["session"] = "d4" * 8
            e["body"].update(session="d4" * 8, op_id="rd-99")
        tap.append(e)
    _r6_sort(c)


def _r10_b03a(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 761700.0, 761705.0, "d4" * 8)


def _r10_b03b(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 761700.0, 761705.0, "d4" * 8, peer="client")


def _r10_b03c(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 761450.0, 761550.0, "d4" * 8)
    _r8_add_op_state(c, 761490.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r10_b03d(c: dict[str, Any]) -> None:
    _r10_add_delivery(c, 761100.0, "op-9", "d4" * 8, "scene.observe",
                      {"f2": 1, "doc_id": "d-7c19e2a5"})
    _r10_add_result(c, 761450.0, "op-9", "d4" * 8, read=_r10_rd1_read(c), ack_dt=100.0)


def _r10_b03_ctrl(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 761200.0, 761205.0, "d4" * 8)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r10_first_other_session(c: dict[str, Any]) -> str:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        b = ev.get("body") or {}
        if ev.get("dir") == "resp" and ev.get("path") == "/hello" and b.get("session") and \
                b.get("session") not in ("d4" * 8, "e5" * 8):
            return str(b["session"])
    raise KeyError("session")


def _r10_b02(c: dict[str, Any], session: str, verb: str) -> None:
    if verb == "scene.apply":
        args = _r10_p5_apply_args(c, "op-6", "d4" * 8)
    else:
        args = {"f2": 1, "doc_id": "d-7c19e2a5"}
    _r10_add_delivery(c, 761700.0, "op-9", session, verb, args)
    _r10_add_result(c, 761800.0, "op-9", session, read=_r10_rd1_read(c))


def _r10_b02a(c: dict[str, Any]) -> None:
    _r10_b02(c, "e5" * 8, "scene.apply")


def _r10_b02b(c: dict[str, Any]) -> None:
    _r10_b02(c, "f6" * 8, "scene.apply")


def _r10_b02c(c: dict[str, Any]) -> None:
    _r10_b02(c, _r10_first_other_session(c), "scene.apply")


def _r10_b02d(c: dict[str, Any]) -> None:
    _r10_b02(c, "e5" * 8, "scene.observe")


def _r10_b02e(c: dict[str, Any]) -> None:
    _r10_b02(c, "f6" * 8, "scene.observe")


def _r10_b02f(c: dict[str, Any]) -> None:
    _r10_b02(c, _r10_first_other_session(c), "scene.observe")


def _r10_b04(c: dict[str, Any], mode: str) -> None:
    if mode != "none":
        http = 409 if mode == "409" else 200
        _r10_add_hello(c, 760950.0, 760955.0, None, inst="e4" * 16, epoch="e4" * 16,
                       http=http, ok=(mode != "ok_false"), with_resp=(mode != "no_resp"))
    _r9_set_cut_inst(c, "e4" * 16)
    _r10_add_hello(c, 761200.0, 761205.0, "d4" * 8, inst="e4" * 16, epoch="e4" * 16)
    _r8_add_op_state(c, 761400.0, "op-6", "observado", "reconciliada", origin="servidor")


def _r10_b04a(c: dict[str, Any]) -> None:
    _r10_b04(c, "ok_false")


def _r10_b04b(c: dict[str, Any]) -> None:
    _r10_b04(c, "no_resp")


def _r10_b04c(c: dict[str, Any]) -> None:
    _r10_b04(c, "409")


def _r10_b04_ctrl(c: dict[str, Any]) -> None:
    _r10_b04(c, "none")


SOL_MUTANTS_R10: dict[str, dict[str, Any]] = {
    "r10_b01a_rd_state_read_d4_tras_cut": {
        "apply": _r10_b01a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b01b_rd_state_read_d4_tras_restart": {
        "apply": _r10_b01b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b01c_rd_observe_d4_resultado_tras_cut": {
        "apply": _r10_b01c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b01d_rd_scene_apply_d4_tras_cut": {
        "apply": _r10_b01d,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b01_ctrl_op9_d4_tras_cut": {
        "apply": _r10_b01_ctrl_op9,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 1},
    "r10_b01_ctrl_rd9_sin_resultado": {
        "apply": _r10_b01_ctrl_sin_resultado,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 1},
    "r10_sol_rd99_d4_tras_cut": {
        "apply": _r10_sol_rd99,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b03a_hello_servidor_d4_tras_cut": {
        "apply": _r10_b03a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b03b_hello_cliente_d4_tras_cut": {
        "apply": _r10_b03b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b03c_causa_c_aceptada_tras_cut_y_terminal": {
        "apply": _r10_b03c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r10_b03d_acuse_d4_tras_cut": {
        "apply": _r10_b03d,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b02a_entrega_e5_en_el_hueco": {
        "apply": _r10_b02a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-13": ["missing"]},
        "red_exit": 2},
    "r10_b02b_entrega_sesion_nunca_abierta": {
        "apply": _r10_b02b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-13": ["missing"]},
        "red_exit": 2},
    "r10_b02c_entrega_sesion_de_otro_tramo": {
        "apply": _r10_b02c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-13": ["missing"]},
        "red_exit": 2},
    "r10_b02d_observe_e5_en_el_hueco": {
        "apply": _r10_b02d,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b02e_observe_sesion_nunca_abierta": {
        "apply": _r10_b02e,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b02f_observe_sesion_de_otro_tramo": {
        "apply": _r10_b02f,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 0},
    "r10_b04a_hello_previo_rechazado_ok_false": {
        "apply": _r10_b04a,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r10_b04b_hello_previo_sin_respuesta": {
        "apply": _r10_b04b,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r10_b04c_hello_previo_409": {
        "apply": _r10_b04c,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 0},
    "r10_b04_ctrl_sin_previo": {
        "apply": _r10_b04_ctrl,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_terminal=observado/reconciliada"},
        "red_exit": 1},
}

SOL_POSITIVES_R10: dict[str, dict[str, Any]] = {
    "r10_b03_ctrl_causa_c_legitima": {
        "apply": _r10_b03_ctrl,
        "expected_exit_code": 0,
        "red_exit": 0},
}

SOL_NEGATIVES_R10: dict[str, dict[str, Any]] = {}

SOL_CASES_R10: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R10.items():
    SOL_CASES_R10[_name] = {"kind": "mutant", "name": _name, "check": "T2f-10"}
for _name, _spec in SOL_NEGATIVES_R10.items():
    SOL_CASES_R10[_name] = {"kind": "negative", "name": _name, "check": "T2f-10"}
for _name, _spec in SOL_POSITIVES_R10.items():
    SOL_CASES_R10[_name] = {"kind": "positive", "name": _name, "check": "T2f-10"}

SOL_CASES.update(SOL_CASES_R10)

# ---------------------------------------------------------------------------------------------------
# T2f-11: los PASA falsos de la sexta pasada de Claude sobre T2f-10 (C-01 a C-06 y C-08).
# ---------------------------------------------------------------------------------------------------

_R11_A1, _R11_B2, _R11_C3, _R11_D4, _R11_E5 = (
    "a1" * 8, "b2" * 8, "c3" * 8, "d4" * 8, "e5" * 8)
_R11_E1, _R11_E2, _R11_E4, _R11_E9 = "e1" * 16, "e2" * 16, "e4" * 16, "e9" * 16
_R11_CLIENT_INST = "cc" * 16


def _r11_add_op(c: dict[str, Any], t_deliv: float, t_res: float, op_id: str, session: str,
                verb: str = "scene.observe", inst: str | None = None,
                epoch: str | None = None, ack_dt: float = 3.0) -> None:
    args = {"f2": 1, "doc_id": "d-7c19e2a5"}
    _r10_add_delivery(c, t_deliv, op_id, session, verb, args, inst=inst, epoch=epoch)
    _r10_add_result(c, t_res, op_id, session, read=_r10_rd1_read(c), ack_dt=ack_dt,
                    inst=inst, epoch=epoch)


def _r11_move_tap(c: dict[str, Any], t_old: float, t_new: float, path: str, dir_: str) -> None:
    hit = 0
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if float(ev.get("t_ms") or 0.0) == t_old and ev.get("path") == path and \
                ev.get("dir") == dir_:
            ev["t_ms"] = t_new
            hit += 1
    assert hit == 1, (t_old, path, dir_, hit)
    _r6_sort(c)


def _r11_hello_req(c: dict[str, Any], t: float, peer: str = "server") -> int:
    return _r10_add_hello(c, t, t, None, peer=peer, with_resp=False)


def _r11_hello_resp(c: dict[str, Any], t: float, rid: int,
                    session: str | None = _R11_D4,
                    http: int = 200, ok: bool = True) -> None:
    body: dict[str, Any] = {"ok": ok}
    if session:
        body["session"] = session
        body["conn"] = 1
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "resp", "method": "POST", "path": "/hello", "http": http,
         "req_id": rid, "body": body})
    _r6_sort(c)


def _r11_relabel_read(c: dict[str, Any], t_deliv: float, t_res: float, epoch: str) -> None:
    hits = 0
    for entry in c["samples"]["bridge_tap.jsonl"]:
        when = float(entry.get("t_ms") or 0.0)
        path = entry.get("path")
        way = entry.get("dir")
        body = entry.get("body") or {}
        if path == "/poll" and when == t_deliv:
            for order in body.get("ops") or []:
                if isinstance(order, dict) and order.get("op_id") == "rd-1":
                    order["epoch"] = epoch
                    hits += 1
        elif path == "/result" and way == "req" and when == t_res:
            if body.get("op_id") == "rd-1":
                body["epoch"] = epoch
                body["read"]["epoch"] = epoch
                hits += 1
    assert hits == 2, hits


def _r11_control_epoch(c: dict[str, Any], epoch: str) -> None:
    ids = _tag_job_ops(c, "P4c:control")
    assert ids, "P4c:control"
    _replace_epoch_for_ops(c, ids, epoch)


def _r11_obs_out_of_map(c: dict[str, Any]) -> None:
    hit = 0
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if float(ev.get("t_ms") or 0.0) == 763000.0 and ev.get("path") == "/result" and \
                ev.get("dir") == "req":
            b = ev["body"]
            assert b.get("op_id") == "rd-1"
            b["read"]["obs"] = {"at": "now",
                                "rows": [["obj-01", 17000000, 1000, 7643000, 0, 1000, 0, 0]]}
            hit += 1
    assert hit == 1, hit


def _r11_c01a(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 762060.0, 762065.0, _R11_E5, peer="client", inst=_R11_CLIENT_INST)
    _r11_add_op(c, 762070.0, 762080.0, "op-9", _R11_E5)


def _r11_c01b(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 373560.0, 373565.0, _R11_B2, peer="client", inst=_R11_CLIENT_INST,
                   epoch=_R11_E1)
    _r11_add_op(c, 373570.0, 373580.0, "op-9", _R11_B2, inst=_R11_E1, epoch=_R11_E1)


def _r11_c01c(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 551060.0, 551065.0, _R11_D4, peer="client", inst=_R11_CLIENT_INST,
                   epoch=_R11_E1)
    _r11_add_op(c, 551070.0, 551080.0, "op-9", _R11_D4, inst=_R11_E1, epoch=_R11_E1)


def _r11_c01d(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 761700.0, 761705.0, _R11_E5, peer="client", inst=_R11_CLIENT_INST)
    _r11_add_op(c, 762030.0, 762040.0, "op-9", _R11_E5)


def _r11_c01e(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 761700.0, 761705.0, _R11_E5, peer="client", inst=_R11_CLIENT_INST)


def _r11_c01f(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 250000.0, 250005.0, "f6" * 8, peer="client", inst=_R11_CLIENT_INST,
                   epoch=_R11_E1)


def _r11_c01g(c: dict[str, Any]) -> None:
    _r11_add_op(c, 762070.0, 762080.0, "op-9", _R11_E5)


def _r11_c02(c: dict[str, Any], mode: str) -> None:
    if mode != "none":
        http = 409 if mode == "409" else 200
        _r10_add_hello(c, 762300.0, 762305.0, None, inst="e3" * 16, epoch=_R11_E4,
                       http=http, ok=(mode != "ok_false"), with_resp=(mode != "no_resp"))
    _r11_relabel_read(c, 762500.0, 763000.0, _R11_E4)


def _r11_c02a(c: dict[str, Any]) -> None:
    _r11_c02(c, "409")


def _r11_c02b(c: dict[str, Any]) -> None:
    _r11_c02(c, "ok_false")


def _r11_c02c(c: dict[str, Any]) -> None:
    _r11_c02(c, "no_resp")


def _r11_c02d(c: dict[str, Any]) -> None:
    _r11_c02(c, "none")


def _r11_c02e(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 551300.0, 551305.0, None, inst=_R11_E1, epoch=_R11_E4, http=409,
                   ok=False)
    _r11_relabel_read(c, 551500.0, 552000.0, _R11_E4)


def _r11_c02f(c: dict[str, Any]) -> None:
    _r11_relabel_read(c, 551500.0, 552000.0, _R11_E4)


def _r11_c03a(c: dict[str, Any]) -> None:
    _r11_move_tap(c, 372003.0, 373520.0, "/result", "resp")


def _r11_c03b(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 373490.0, 373510.0, _R11_A1, inst=_R11_E1, epoch=_R11_E1)


def _r11_c03c(c: dict[str, Any]) -> None:
    _r11_add_op(c, 550500.0, 550900.0, "op-9", _R11_C3, inst=_R11_E1, epoch=_R11_E1,
                ack_dt=120.0)


def _r11_c03d(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 550990.0, 551010.0, _R11_C3, peer="client", inst=_R11_CLIENT_INST,
                   epoch=_R11_E1)


def _r11_c03e(c: dict[str, Any]) -> None:
    _r11_move_tap(c, 375003.0, 376520.0, "/result", "resp")


def _r11_c04a(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 701100.0, 701105.0, None, inst="e3" * 16, epoch=_R11_E2, http=409,
                   ok=False)
    _r11_control_epoch(c, _R11_E2)


def _r11_c04b(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 701100.0, 701105.0, None, inst=_R11_E2, epoch=_R11_E2, http=409,
                   ok=False)
    _r11_control_epoch(c, _R11_E2)


def _r11_c04c(c: dict[str, Any]) -> None:
    _r11_control_epoch(c, _R11_E2)


def _r11_c05a(c: dict[str, Any]) -> None:
    a = _r11_hello_req(c, 761400.0, "server")
    b = _r11_hello_req(c, 761450.0, "client")
    _r11_hello_resp(c, 761455.0, b)
    _r11_hello_resp(c, 761600.0, a)


def _r11_c05b(c: dict[str, Any]) -> None:
    a = _r11_hello_req(c, 761400.0, "server")
    _r11_hello_resp(c, 761405.0, a)
    _r11_hello_resp(c, 761600.0, a)


def _r11_c05c(c: dict[str, Any]) -> None:
    _r11_hello_resp(c, 761600.0, 9999)


def _r11_c05d(c: dict[str, Any]) -> None:
    a = _r11_hello_req(c, 761590.0, "server")
    _r11_hello_resp(c, 761600.0, a)


def _r11_c06a(c: dict[str, Any]) -> None:
    _r11_obs_out_of_map(c)
    _r10_add_hello(c, 800000.0, 800005.0, None, inst="e3" * 16, epoch="e3" * 16, http=409,
                   ok=False, world_size=20000)


def _r11_c06b(c: dict[str, Any]) -> None:
    _r11_obs_out_of_map(c)


def _r11_c08a(c: dict[str, Any]) -> None:
    _m_reappears(c)
    _r10_add_hello(c, 615000.0, 615005.0, None, inst=_R11_E1, epoch=_R11_E9, http=409,
                   ok=False)


def _r11_c08b(c: dict[str, Any]) -> None:
    _m_reappears(c)


SOL_MUTANTS_R11: dict[str, dict[str, Any]] = {
    "r11_c01a_cliente_abre_e5_antes_que_el_servidor_p5": {
        "apply": _r11_c01a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c01b_cliente_abre_b2_antes_que_el_servidor_p3": {
        "apply": _r11_c01b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c01c_cliente_abre_d4_antes_que_el_servidor_p4a": {
        "apply": _r11_c01c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c01d_cliente_e5_antes_del_reinicio_y_entrega_en_el_hueco": {
        "apply": _r11_c01d, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c01e_cliente_e5_antes_del_reinicio_solo": {
        "apply": _r11_c01e, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c01f_p2_cliente_sesion_f6_solo": {
        "apply": _r11_c01f, "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
        "must_detail": {"F2P-01": "tap_trace_mismatch", "F2P-04": "tap_trace_mismatch"},
        "red_exit": 0},
    "r11_c01g_ctrl_sin_hello_de_cliente": {
        "apply": _r11_c01g, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r11_c02a_p5_lectura_con_epoch_de_hello_409": {
        "apply": _r11_c02a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "no_reconciliation_before_scene:762000.0"}, "red_exit": 0},
    "r11_c02b_p5_lectura_con_epoch_de_hello_ok_false": {
        "apply": _r11_c02b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "no_reconciliation_before_scene:762000.0"}, "red_exit": 0},
    "r11_c02c_p5_lectura_con_epoch_de_hello_sin_respuesta": {
        "apply": _r11_c02c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "no_reconciliation_before_scene:762000.0"}, "red_exit": 0},
    "r11_c02d_ctrl_p5_lectura_e4_sin_hello": {
        "apply": _r11_c02d, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "no_reconciliation_before_scene:762000.0"}, "red_exit": 1},
    "r11_c02e_p4a_lectura_con_epoch_de_hello_409": {
        "apply": _r11_c02e, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "no_reconciliation_before_scene:551000.0"}, "red_exit": 2},
    "r11_c02f_ctrl_p4a_lectura_e4_sin_hello": {
        "apply": _r11_c02f, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "no_reconciliation_before_scene:551000.0"}, "red_exit": 1},
    "r11_c03a_p3_acuse_a1_tras_el_reinicio": {
        "apply": _r11_c03a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c03b_p3_hello_a1_aceptado_tras_el_reinicio": {
        "apply": _r11_c03b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-01": ["fail"], "F2P-02": ["missing"],
                              "F2P-04": ["missing"], "F2P-06": ["missing"],
                              "F2P-12": ["missing"]},
        "red_exit": 0},
    "r11_c03c_p4a_acuse_c3_tras_el_reinicio": {
        "apply": _r11_c03c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c03d_p4a_hello_cliente_c3_tras_el_reinicio": {
        "apply": _r11_c03d, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-05": ["fail"], "F2P-06": ["fail"],
                              "F2P-07": ["fail"], "F2P-09": ["fail"]},
        "red_exit": 0},
    "r11_c03e_p3_acuse_b2_tras_el_segundo_reinicio": {
        "apply": _r11_c03e, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c04a_p4c_control_epoch_e2_con_hello_409_inst_e3": {
        "apply": _r11_c04a, "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "persistent_control_missing"}, "red_exit": 0},
    "r11_c04b_p4c_control_epoch_e2_con_hello_409_inst_e2": {
        "apply": _r11_c04b, "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "persistent_control_missing"}, "red_exit": 0},
    "r11_c04c_ctrl_p4c_control_epoch_e2_sin_hello": {
        "apply": _r11_c04c, "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "persistent_control_missing"}, "red_exit": 2},
    "r11_c05a_respuesta_d4_tras_cut_huerfana_por_intercalado": {
        "apply": _r11_c05a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r11_c05b_segunda_respuesta_d4_tras_cut": {
        "apply": _r11_c05b, "expected_exit_code": 2,
        "must_fail_status": {"F2P-09": "missing"},
        "must_detail": {"F2P-09": "tap_req_id_missing"}, "red_exit": 1},
    "r11_c05c_respuesta_d4_tras_cut_sin_peticion": {
        "apply": _r11_c05c, "expected_exit_code": 2,
        "must_fail_status": {"F2P-09": "missing"},
        "must_detail": {"F2P-09": "tap_req_id_missing"}, "red_exit": 1},
    "r11_c05d_ctrl_respuesta_d4_tras_cut_emparejada": {
        "apply": _r11_c05d, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r11_c06a_lectura_fuera_del_mundo_con_hello_409_world_size_20000": {
        "apply": _r11_c06a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "no_reconciliation_before_scene:762000.0"}, "red_exit": 0},
    "r11_c06b_ctrl_lectura_fuera_del_mundo": {
        "apply": _r11_c06b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "no_reconciliation_before_scene:762000.0"}, "red_exit": 1},
    "r11_c08a_reaparicion_tapada_por_hello_409_antes_del_reinicio": {
        "apply": _r11_c08a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "reappeared"}, "red_exit": 0},
    "r11_c08b_ctrl_reaparicion": {
        "apply": _r11_c08b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "reappeared"}, "red_exit": 1},
}

SOL_POSITIVES_R11: dict[str, dict[str, Any]] = {}
SOL_NEGATIVES_R11: dict[str, dict[str, Any]] = {}

SOL_CASES_R11: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R11.items():
    SOL_CASES_R11[_name] = {"kind": "mutant", "name": _name, "check": "T2f-11"}
for _name, _spec in SOL_NEGATIVES_R11.items():
    SOL_CASES_R11[_name] = {"kind": "negative", "name": _name, "check": "T2f-11"}
for _name, _spec in SOL_POSITIVES_R11.items():
    SOL_CASES_R11[_name] = {"kind": "positive", "name": _name, "check": "T2f-11"}

SOL_CASES.update(SOL_CASES_R11)

# ---------------------------------------------------------------------------------------------------
# T2f-12: el falso FALLA de Sol, los PASA falsos de la septima pasada (D-02, D-03, D-05), B-05 y X-03.
# ---------------------------------------------------------------------------------------------------

_R12_A1, _R12_B2, _R12_C3, _R12_D4, _R12_E5 = (
    "a1" * 8, "b2" * 8, "c3" * 8, "d4" * 8, "e5" * 8)
_R12_E1, _R12_E2, _R12_E3 = "e1" * 16, "e2" * 16, "e3" * 16
_R12_X9 = "ab" * 16
_R12_CLIENT_INST = "cc" * 16


def _r12_set_hello_req(c: dict[str, Any], t: float, **fields: Any) -> None:
    hit = 0
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if float(ev.get("t_ms") or 0.0) == t and ev.get("dir") == "req" and \
                ev.get("path") == "/hello":
            ev["body"].update(fields)
            hit += 1
    assert hit == 1, hit


def _r12_tap_at(c: dict[str, Any], t: float, path: str, dir_: str) -> dict[str, Any]:
    hits = [ev for ev in c["samples"]["bridge_tap.jsonl"]
            if float(ev.get("t_ms") or 0.0) == t and ev.get("path") == path and
            ev.get("dir") == dir_]
    assert len(hits) == 1, (t, path, dir_, len(hits))
    return hits[0]


def _r12_poll_ok(c: dict[str, Any], t_resp: float) -> None:
    ev = _r12_tap_at(c, t_resp, "/poll", "resp")
    req = _r12_tap_at(c, t_resp - 2.0, "/poll", "req")
    assert req.get("query") is not None
    ev["http"] = 200
    ev["body"] = {"ok": True, "now_ms": t_resp, "ops": []}


def _r12_d02a(c: dict[str, Any]) -> None:
    _r12_poll_ok(c, 373552.0)


def _r12_d02b(c: dict[str, Any]) -> None:
    _r12_poll_ok(c, 551052.0)


def _r12_d02c(c: dict[str, Any]) -> None:
    _r12_poll_ok(c, 762052.0)


def _r12_d02d(c: dict[str, Any]) -> None:
    """El poll de a1 (copia) responde con la entrega de b2: el 200 de 373700 lleva su req_id."""
    rid = _r15c_rid(c)
    req = copy.deepcopy(_r12_tap_at(c, 373550.0, "/poll", "req"))
    req["t_ms"] = 373690.0
    req["req_id"] = rid
    c["samples"]["bridge_tap.jsonl"].append(req)
    _r12_tap_at(c, 373700.0, "/poll", "resp")["req_id"] = rid
    _r6_sort(c)


def _r12_d02e(c: dict[str, Any]) -> None:
    """El poll de d4 (copia) aceptado entre el cut y el reinicio: su 200 de 761702 lleva su req_id."""
    rid = _r15c_rid(c)
    req = copy.deepcopy(_r12_tap_at(c, 762050.0, "/poll", "req"))
    req["t_ms"] = 761700.0
    req["req_id"] = rid
    c["samples"]["bridge_tap.jsonl"].append(req)
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": 761702.0, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
         "req_id": rid,
         "body": {"ok": True, "now_ms": 761702.0, "ops": []}})
    _r6_sort(c)


def _r12_d03_inst(c: dict[str, Any], t: float) -> None:
    _r12_set_hello_req(c, t, inst=_R12_X9)


def _r12_d03a(c: dict[str, Any]) -> None:
    _r12_d03_inst(c, 762100.0)


def _r12_d03b(c: dict[str, Any]) -> None:
    _r12_d03_inst(c, 373600.0)


def _r12_d03c(c: dict[str, Any]) -> None:
    _r12_d03_inst(c, 551100.0)


def _r12_d03d(c: dict[str, Any]) -> None:
    _r11_move_tap(c, 762105.0, 764500.0, "/hello", "resp")
    _r10_add_hello(c, 762110.0, 762115.0, _R12_E5, peer="server", inst=_R12_X9,
                   epoch=_R12_E3)


def _r12_shift_job(c: dict[str, Any], tag: str, delta_start: float, delta_free: float,
                   inst: str, epoch: str) -> set[str]:
    ops = sorted(_tag_job_ops(c, tag), key=lambda name: int(name.split("-")[1]))
    assert len(ops) == 3, ops
    start_ops = set(ops[:2])
    free_ops = {ops[2]}
    _shift_ops(c, start_ops, delta_start)
    _shift_ops(c, free_ops, delta_free)
    for event in c["samples"]["bridge.jsonl"]:
        carried = set(event.get("op_ids") or [])
        if event.get("ev") != "poll" or not carried & set(ops):
            continue
        step = delta_start
        if carried & free_ops:
            step = delta_free
        event["t_ms"] = float(event["t_ms"]) + step
        event["now_ms"] = event["t_ms"]
        event["inst"] = inst
    _set_job_inst(c, tag, inst)
    _replace_epoch_for_ops(c, set(ops), epoch)
    c["samples"]["bridge.jsonl"] = sorted(c["samples"]["bridge.jsonl"],
                                          key=lambda record: float(record.get("t_ms") or 0.0))
    return set(ops)


def _r12_d05a(c: dict[str, Any]) -> None:
    _r12_shift_job(c, "P4c:control", -350.0, -420.0, _R12_E2, _R12_E2)


def _r12_d05b(c: dict[str, Any]) -> None:
    ops = sorted(_tag_job_ops(c, "P4b:control"), key=lambda name: int(name.split("-")[1]))
    first_at = None
    last_at = None
    for event in c["samples"]["bridge.jsonl"]:
        if event.get("ev") != "deliver":
            continue
        if event.get("op_id") == ops[0] and first_at is None:
            first_at = float(event["t_ms"])
        elif event.get("op_id") == ops[2] and last_at is None:
            last_at = float(event["t_ms"])
        if first_at is not None and last_at is not None:
            break
    assert first_at is not None and last_at is not None, ops
    _r12_shift_job(c, "P4b:control", 621315.0 - first_at, 621380.0 - last_at,
                   _R12_E1, _R12_E1)


def _r12_d05c(c: dict[str, Any]) -> None:
    _r12_shift_job(c, "P4c:control", 0.0, 0.0, _R12_E2, _R12_E2)


def _r12_dup_terminal(c: dict[str, Any], part: str, verb: str, index: int) -> str:
    """Duplica el último terminal de la op de la etapa: el último sigue siendo el esperado."""
    import f2p_eval as E  # noqa: PLC0415 (import perezoso, evita el ciclo de importación)

    tap = E._parse_tap(c["samples"]["bridge_tap.jsonl"])
    be = E._parse_backend(c["samples"]["backend.jsonl"])
    E._assign_op_sessions(tap, be)
    ops = E._tap_op(tap, verb, part, c["manifest"])
    assert len(ops) > index, (part, verb, index, len(ops))
    d = ops[index]
    sess = str(d["session"])
    oid = str(d["op_id"])
    terms = [st for st in be["op_states"]
             if str(st["data"].get("op_id") or "") == oid and
             str(st.get("session") or "") == sess and
             E._is_terminal(str(st["data"].get("state") or ""),
                            str(st["data"].get("reason") or ""))]
    assert terms, (part, verb, index, oid)
    last = max(terms, key=lambda x: x["t_ms"])
    raw = next(ev for ev in c["samples"]["backend.jsonl"]
               if ev.get("kind") == "op.state" and
               float(ev.get("t_ms") or 0.0) == float(last["t_ms"]) and
               str((ev.get("data") or {}).get("op_id") or "") == oid)
    clone = copy.deepcopy(raw)
    clone["t_ms"] = float(last["t_ms"]) - 1.0
    clone["data"]["at_ms"] = clone["t_ms"]
    clone["seq"] = max(int(e.get("seq") or 0) for e in c["samples"]["backend.jsonl"]) + 1
    c["samples"]["backend.jsonl"].append(clone)
    _r6_sort(c)
    return oid


def _r12_b05(c: dict[str, Any], part: str, verb: str, index: int) -> None:
    _r12_dup_terminal(c, part, verb, index)


def _r12_b05_p2_apply(c: dict[str, Any]) -> None:
    _r12_b05(c, "P2", "scene.apply", 0)


def _r12_b05_p2n_apply(c: dict[str, Any]) -> None:
    _r12_b05(c, "P2n", "scene.apply", 0)


def _r12_b05_p2n_reset(c: dict[str, Any]) -> None:
    _r12_b05(c, "P2n", "scene.reset", 0)


def _r12_b05_p3_apply1(c: dict[str, Any]) -> None:
    _r12_b05(c, "P3", "scene.apply", 0)


def _r12_b05_p3_apply2(c: dict[str, Any]) -> None:
    _r12_b05(c, "P3", "scene.apply", 1)


def _r12_b05_p3_reset1(c: dict[str, Any]) -> None:
    _r12_b05(c, "P3", "scene.reset", 0)


def _r12_b05_p3_reset2(c: dict[str, Any]) -> None:
    _r12_b05(c, "P3", "scene.reset", 1)


def _r12_b05_p3c_reset(c: dict[str, Any]) -> None:
    _r12_b05(c, "P3c", "scene.reset", 0)


def _r12_b05_p4c_reset(c: dict[str, Any]) -> None:
    _r12_b05(c, "P4c", "scene.reset", 0)


def _r12_b05_p4b_apply(c: dict[str, Any]) -> None:
    _r12_b05(c, "P4b", "scene.apply", 0)


def _r12_b05_p4a_apply1(c: dict[str, Any]) -> None:
    _r12_b05(c, "P4a", "scene.apply", 0)


def _r12_b05_p4a_reset(c: dict[str, Any]) -> None:
    _r12_b05(c, "P4a", "scene.reset", 0)


def _r12_b05_p4a_apply2(c: dict[str, Any]) -> None:
    _r12_b05(c, "P4a", "scene.apply", 1)


def _r12_b05_p5_apply2(c: dict[str, Any]) -> None:
    _r12_b05(c, "P5", "scene.apply", 1)


def _r12_neg_world_size(c: dict[str, Any]) -> None:
    _r11_obs_out_of_map(c)
    _r10_add_hello(c, 762400.0, 762600.0, _R12_E5, peer="server", inst=_R12_E3,
                   epoch=_R12_E3, world_size=20000)


def _r12_x03_escena2_y_reaparece(c: dict[str, Any]) -> None:
    _r6_add_p4c_scene2_reset(c, "observado", None)
    _m_reappears(c)


SOL_MUTANTS_R12: dict[str, dict[str, Any]] = {
    "r12_sol_neg_hello_resp_vieja_tras_reinicio": {
        "apply": lambda c: _r10_add_hello(
            c, 761980.0, 761990.0, _R12_E5, peer="client", inst=_R12_CLIENT_INST,
            epoch=_R12_E3),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"},
        "red_exit": 1},
    "r12_neg_hello_aceptado_tras_la_lectura_no_es_el_vigente": {
        "apply": _r12_neg_world_size,
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "no_reconciliation_before_scene:762000.0"},
        "red_exit": 0},
    "r12_d03a_p5_hello_e5_de_otra_inst": {
        "apply": _r12_d03a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d03b_p3_hello_b2_de_otra_inst": {
        "apply": _r12_d03b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d03c_p4a_hello_d4_de_otra_inst": {
        "apply": _r12_d03c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d03d_p5_e3_tarde_y_otra_inst_antes": {
        "apply": _r12_d03d, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d02a_p3_poll_a1_aceptado_tras_reinicio": {
        "apply": _r12_d02a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d02b_p4a_poll_c3_aceptado_tras_reinicio": {
        "apply": _r12_d02b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d02c_p5_poll_d4_aceptado_tras_reinicio": {
        "apply": _r12_d02c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d02d_p3_poll_a1_responde_con_entrega_b2": {
        "apply": _r12_d02d, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r12_d02e_p5_poll_d4_aceptado_entre_cut_y_reinicio": {
        "apply": _r12_d02e, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r12_d05a_p4c_control_de_e2_entre_restart_y_hello_e3": {
        "apply": _r12_d05a, "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "persistent_control_missing"}, "red_exit": 0},
    "r12_d05b_p4b_control_de_e1_entre_restart_y_hello_e2": {
        "apply": _r12_d05b, "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "persistent_control_missing"}, "red_exit": 0},
    "r12_d05c_ctrl_p4c_control_e2_en_su_sitio": {
        "apply": _r12_d05c, "expected_exit_code": 2,
        "must_fail_status": {"F2P-07": "missing"},
        "must_detail": {"F2P-07": "persistent_control_missing"}, "red_exit": 2},
    "r12_b05_p2_apply_segundo_terminal": {
        "apply": _r12_b05_p2_apply, "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail"},
        "must_detail": {"F2P-01": "segundo_terminal:op-1"}, "red_exit": 0},
    "r12_b05_p2n_apply_segundo_terminal": {
        "apply": _r12_b05_p2n_apply, "expected_exit_code": 1,
        "must_fail_status": {"F2P-03": "fail"},
        "must_detail": {"F2P-03": "segundo_terminal:op-2"}, "red_exit": 0},
    "r12_b05_p2n_reset_segundo_terminal": {
        "apply": _r12_b05_p2n_reset, "expected_exit_code": 1,
        "must_fail_status": {"F2P-03": "fail"},
        "must_detail": {"F2P-03": "segundo_terminal:op-3"}, "red_exit": 0},
    "r12_b05_p3_apply1_segundo_terminal": {
        "apply": _r12_b05_p3_apply1, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "segundo_terminal:op-4"}, "red_exit": 0},
    "r12_b05_p3_apply2_segundo_terminal": {
        "apply": _r12_b05_p3_apply2, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "segundo_terminal:op-1"}, "red_exit": 0},
    "r12_b05_p3_reset1_segundo_terminal": {
        "apply": _r12_b05_p3_reset1, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "segundo_terminal:op-1"}, "red_exit": 0},
    "r12_b05_p3_reset2_segundo_terminal": {
        "apply": _r12_b05_p3_reset2, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "segundo_terminal:op-2"}, "red_exit": 0},
    "r12_b05_p3c_reset_segundo_terminal": {
        "apply": _r12_b05_p3c_reset, "expected_exit_code": 1,
        "must_fail_status": {"F2P-06": "fail"},
        "must_detail": {"F2P-06": "segundo_terminal:op-3"}, "red_exit": 0},
    "r12_b05_p4c_reset_segundo_terminal": {
        "apply": _r12_b05_p4c_reset, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "segundo_terminal:op-5"}, "red_exit": 0},
    "r12_b05_p4b_apply_segundo_terminal": {
        "apply": _r12_b05_p4b_apply, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "segundo_terminal:op-4"}, "red_exit": 0},
    "r12_b05_p4a_apply1_segundo_terminal": {
        "apply": _r12_b05_p4a_apply1, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "segundo_terminal:op-1"}, "red_exit": 0},
    "r12_b05_p4a_reset_segundo_terminal": {
        "apply": _r12_b05_p4a_reset, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "segundo_terminal:op-2"}, "red_exit": 0},
    "r12_b05_p4a_apply2_segundo_terminal": {
        "apply": _r12_b05_p4a_apply2, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "segundo_terminal:op-3"}, "red_exit": 0},
    "r12_b05_p5_apply2_segundo_terminal": {
        "apply": _r12_b05_p5_apply2, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "segundo_terminal:op-1"}, "red_exit": 0},
    "r12_x03_reset_escena2_y_reaparece": {
        "apply": _r12_x03_escena2_y_reaparece, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "reappeared"}, "red_exit": 1},
}

SOL_POSITIVES_R12: dict[str, dict[str, Any]] = {
    "r12_sol_pos_cliente_hello_cruza_reinicio": {
        "apply": lambda c: _r10_add_hello(
            c, 550990.0, 551010.0, _R12_D4, peer="client", inst=_R12_CLIENT_INST,
            epoch=_R12_E1),
        "expected_exit_code": 0, "red_exit": 1},
    "r12_sol_pos_servidor_hello_cruza_reinicio": {
        "apply": lambda c: _r10_add_hello(
            c, 550990.0, 551010.0, _R12_D4, peer="server", inst=_R12_E1, epoch=_R12_E1),
        "expected_exit_code": 0, "red_exit": 1},
}

SOL_NEGATIVES_R12: dict[str, dict[str, Any]] = {}

SOL_CASES_R12: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R12.items():
    SOL_CASES_R12[_name] = {"kind": "mutant", "name": _name, "check": "T2f-12"}
for _name, _spec in SOL_NEGATIVES_R12.items():
    SOL_CASES_R12[_name] = {"kind": "negative", "name": _name, "check": "T2f-12"}
for _name, _spec in SOL_POSITIVES_R12.items():
    SOL_CASES_R12[_name] = {"kind": "positive", "name": _name, "check": "T2f-12"}

SOL_CASES.update(SOL_CASES_R12)

# ---------------------------------------------------------------------------------------------------
# T2f-13: el emparejamiento de `/poll` con peticiones solapadas (E-02 y E-03).
# ---------------------------------------------------------------------------------------------------

_R13_A1, _R13_B2, _R13_C3, _R13_D4, _R13_E5 = (
    "a1" * 8, "b2" * 8, "c3" * 8, "d4" * 8, "e5" * 8)
_R13_E1, _R13_E3 = "e1" * 16, "e3" * 16
_R13_CLIENT_INST = "cc" * 16


def _r13_poll_req(c: dict[str, Any], t: float, session: str, peer: str = "server",
                  inst: str | None = None, conn: str = "1",
                  rid: int | None = None) -> int:
    if inst is None:
        inst = _R13_CLIENT_INST if peer == "client" else _R13_E1
    rid = _r15c_rid(c) if rid is None else rid
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "req", "method": "GET", "path": "/poll", "req_id": rid,
         "query": {"peer": peer, "inst": inst, "session": session, "conn": conn}})
    _r6_sort(c)
    return rid


def _r13_poll_resp(c: dict[str, Any], t: float, http: int = 200,
                   ops: list[Any] | None = None, rid: int | None = None) -> None:
    if http == 200:
        body = {"ok": True, "now_ms": t, "ops": list(ops or [])}
    else:
        body = {"ok": False, "error": "hello_required"}
    rid = _r15c_rid(c) if rid is None else rid
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "resp", "method": "GET", "path": "/poll", "http": http,
         "req_id": rid, "body": body})
    _r6_sort(c)


def _r13_crossed(c: dict[str, Any], srv_req: float, cli_req: float, cli_409: float,
                 cli_hello: float, new_sess: str, old_sess: str, srv_inst: str,
                 epoch: str) -> None:
    a = _r15c_rid(c)
    b = a + 1
    _r13_poll_req(c, srv_req, new_sess, peer="server", inst=srv_inst, rid=a)
    _r13_poll_req(c, cli_req, old_sess, peer="client", inst=_R13_CLIENT_INST, rid=b)
    _r13_poll_resp(c, cli_409, 409, rid=b)
    _r10_add_hello(c, cli_hello, cli_hello + 5.0, new_sess, peer="client",
                   inst=_R13_CLIENT_INST, epoch=epoch)
    _r6_sort(c)


def _r13_sol(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 373450.0, 373455.0, _R13_A1, peer="client",
                   inst=_R13_CLIENT_INST, epoch=_R13_E1)
    _a = _r15c_rid(c)
    _b = _a + 1
    _r15c_poll_req(c, 373660.0, _R13_B2, "server", _R13_E1, "1", _a)
    _r15c_poll_req(c, 373665.0, _R13_A1, "client", _R13_CLIENT_INST, "1", _b)
    _r15c_poll_resp(c, 373670.0, 200, [], _a)
    _r15c_poll_resp(c, 373672.0, 409, [], _b)


def _r13_e02a(c: dict[str, Any]) -> None:
    _r13_crossed(c, 373690.0, 373695.0, 373702.0, 373710.0, _R13_B2, _R13_A1,
                 _R13_E1, _R13_E1)


def _r13_e02b(c: dict[str, Any]) -> None:
    _r13_crossed(c, 551490.0, 551495.0, 551502.0, 551510.0, _R13_D4, _R13_C3,
                 _R13_E1, _R13_E1)


def _r13_e02c(c: dict[str, Any]) -> None:
    _r13_crossed(c, 762490.0, 762495.0, 762502.0, 762510.0, _R13_E5, _R13_D4,
                 _R13_E3, _R13_E3)


def _r13_e02e(c: dict[str, Any]) -> None:
    _r13_crossed(c, 373699.6, 373699.8, 373700.2, 373710.0, _R13_B2, _R13_A1,
                 _R13_E1, _R13_E1)


def _r13_e02d(c: dict[str, Any]) -> None:
    _r13_crossed(c, 373690.0, 373695.0, 373697.0, 373710.0, _R13_B2, _R13_A1,
                 _R13_E1, _R13_E1)


def _r13_cliente_primero(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 373450.0, 373455.0, _R13_A1, peer="client",
                   inst=_R13_CLIENT_INST, epoch=_R13_E1)
    a = _r15c_rid(c)
    b = a + 1
    _r13_poll_req(c, 373660.0, _R13_A1, peer="client", inst=_R13_CLIENT_INST, rid=a)
    _r13_poll_req(c, 373665.0, _R13_B2, peer="server", inst=_R13_E1, rid=b)
    _r13_poll_resp(c, 373670.0, 200, rid=b)
    _r13_poll_resp(c, 373672.0, 409, rid=a)


def _r13_409_primero(c: dict[str, Any]) -> None:
    _r10_add_hello(c, 373450.0, 373455.0, _R13_A1, peer="client",
                   inst=_R13_CLIENT_INST, epoch=_R13_E1)
    a = _r15c_rid(c)
    b = a + 1
    _r13_poll_req(c, 373660.0, _R13_B2, peer="server", inst=_R13_E1, rid=a)
    _r13_poll_req(c, 373665.0, _R13_A1, peer="client", inst=_R13_CLIENT_INST, rid=b)
    _r13_poll_resp(c, 373668.0, 409, rid=b)
    _r13_poll_resp(c, 373670.0, 200, rid=a)


def _r13_old_200(c: dict[str, Any], t_resp: float) -> None:
    ev = _r12_tap_at(c, t_resp, "/poll", "resp")
    ev["http"] = 200
    ev["body"] = {"ok": True, "now_ms": t_resp, "ops": []}


def _r13_e03a(c: dict[str, Any]) -> None:
    _r13_old_200(c, 373552.0)
    _r10_add_hello(c, 373520.0, 373525.0, _R13_B2, peer="client",
                   inst=_R13_CLIENT_INST, epoch=_R13_E1)
    a = _r15c_rid(c)
    _r13_poll_req(c, 373551.0, _R13_B2, peer="client", inst=_R13_CLIENT_INST, rid=a)
    _r13_poll_resp(c, 373553.0, 200, rid=a)


def _r13_e03b(c: dict[str, Any]) -> None:
    _r13_old_200(c, 762052.0)
    _r10_add_hello(c, 762020.0, 762025.0, _R13_E5, peer="client",
                   inst=_R13_CLIENT_INST, epoch=_R13_E3)
    a = _r15c_rid(c)
    _r13_poll_req(c, 762051.0, _R13_E5, peer="client", inst=_R13_CLIENT_INST, rid=a)
    _r13_poll_resp(c, 762053.0, 200, rid=a)


def _r13_e03c(c: dict[str, Any]) -> None:
    _r13_old_200(c, 373552.0)


SOL_POSITIVES_R13: dict[str, dict[str, Any]] = {
    "r13_sol_solapados_validos": {
        "apply": _r13_sol, "expected_exit_code": 0, "red_exit": 1},
    "r13_e02a_p3_cruce": {
        "apply": _r13_e02a, "expected_exit_code": 0, "red_exit": 1},
    "r13_e02b_p4a_cruce": {
        "apply": _r13_e02b, "expected_exit_code": 0, "red_exit": 1},
    "r13_e02c_p5_cruce": {
        "apply": _r13_e02c, "expected_exit_code": 0, "red_exit": 1},
    "r13_e02e_p3_cruce_ajustado": {
        "apply": _r13_e02e, "expected_exit_code": 0, "red_exit": 1},
    "r13_e02d_ctrl_p3_sin_cruce": {
        "apply": _r13_e02d, "expected_exit_code": 0, "red_exit": 0},
    "r13_cliente_primero": {
        "apply": _r13_cliente_primero, "expected_exit_code": 0, "red_exit": 0},
    "r13_409_primero": {
        "apply": _r13_409_primero, "expected_exit_code": 0, "red_exit": 0},
}

SOL_NEGATIVES_R13: dict[str, dict[str, Any]] = {
    "r13_e03a_p3_vieja_tapada": {
        "apply": _r13_e03a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r13_e03b_p5_vieja_tapada": {
        "apply": _r13_e03b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
}

SOL_MUTANTS_R13: dict[str, dict[str, Any]] = {
    "r13_e03c_ctrl_p3_sin_cliente": {
        "apply": _r13_e03c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 1},
}

SOL_CASES_R13: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R13.items():
    SOL_CASES_R13[_name] = {"kind": "mutant", "name": _name, "check": "T2f-13"}
for _name, _spec in SOL_NEGATIVES_R13.items():
    SOL_CASES_R13[_name] = {"kind": "negative", "name": _name, "check": "T2f-13"}
for _name, _spec in SOL_POSITIVES_R13.items():
    SOL_CASES_R13[_name] = {"kind": "positive", "name": _name, "check": "T2f-13"}

SOL_CASES.update(SOL_CASES_R13)

# ---------------------------------------------------------------------------------------------------
# T2f-14: la op cortada reentregada (z91), el 200 con ops de otro peer (G-01) y la conn del registro
# de cada peer (G-04).
# ---------------------------------------------------------------------------------------------------

_R14_E1, _R14_E3 = "e1" * 16, "e3" * 16
_R14_CLIENT_INST = "cc" * 16
_R14_T0 = 761400.0
_R14_D = 2000.0
_R14_TICK_OFF = 694440.0
_R14_HI = 830000.0


def _r14_shift_common(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _r14_shift_common(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_r14_shift_common(v) for v in x]
    if isinstance(x, (int, float)) and not isinstance(x, bool) and \
            _R14_T0 <= x <= _R14_HI:
        return x + _R14_D if isinstance(x, float) else x + int(_R14_D)
    return x


def _r14_shift_ticks(read: Any) -> None:
    if not isinstance(read, dict):
        return
    floor = _R14_T0 - _R14_TICK_OFF
    names = read.get("nk") or []
    values = read.get("nv") or []
    for position, label in enumerate(names):
        if position >= len(values):
            break
        if "tick_ms" not in str(label):
            continue
        value = values[position]
        if not isinstance(value, (int, float)):
            continue
        if value < floor:
            continue
        values[position] = value + _R14_D
    columns = read.get("ncol") or []
    cells = read.get("ncell") or []
    if "tick_ms" not in columns:
        return
    offset = columns.index("tick_ms")
    width = len(columns)
    if width == 0:
        return
    rows = (len(cells) + width - 1) // width
    for row in range(rows):
        slot = row * width + offset
        if slot >= len(cells):
            continue
        value = cells[slot]
        if not isinstance(value, (int, float)):
            continue
        if value < floor:
            continue
        cells[slot] = value + _R14_D


def _r14_z91(c: dict[str, Any], redeliver_t: float | None = None) -> None:
    for sample, records in c["samples"].items():
        fresh = []
        for record in records:
            stamp = record.get("t_ms")
            late = isinstance(stamp, (int, float)) and stamp >= _R14_T0
            if late:
                record = _r14_shift_common(record)
                if sample == "bridge.jsonl":
                    read_block = (record.get("result") or {}).get("read")
                    args_block = record.get("args")
                    _r14_shift_ticks(read_block)
                    _r14_shift_ticks(args_block)
            fresh.append(record)
        c["samples"][sample] = fresh
    for record in c["samples"]["bridge.jsonl"]:
        marker = json.dumps(record)
        if '"P5:cut"' not in marker and '"op-478"' not in marker:
            continue
        blocks = [record.get("args"), (record.get("result") or {}).get("read")]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            labels = block.get("nk") or []
            values = block.get("nv") or []
            for position, label in enumerate(labels):
                if position >= len(values):
                    continue
                if label != "window_ms":
                    continue
                values[position] = 3500.0
    if redeliver_t is not None:
        tap = c["samples"]["bridge_tap.jsonl"]
        source = None
        for record in tap:
            if record.get("dir") != "resp" or record.get("path") != "/poll":
                continue
            orders = (record.get("body") or {}).get("ops") or []
            if any(isinstance(order, dict) and order.get("op_id") == "op-6" for order in orders):
                source = record
                break
        assert source is not None
        again = copy.deepcopy(source)
        again["t_ms"] = float(redeliver_t)
        again["body"].update({"now_ms": float(redeliver_t)})
        order = (again.get("body") or {}).get("ops")[0]
        rid = _r15c_rid(c)
        tap.append({"t_ms": float(redeliver_t) - 0.5, "dir": "req", "method": "GET",
                    "path": "/poll", "req_id": rid,
                    "query": {"peer": "server", "inst": str(order.get("inst") or ""),
                              "session": str(order.get("session") or ""),
                              "conn": str(order.get("conn")), "deliver": "1"}})
        again["req_id"] = rid
        tap.append(again)
    for key in c["samples"]:
        c["samples"][key].sort(key=lambda record: float(record.get("t_ms") or 0.0))


def _r14_control_desplazado(c: dict[str, Any]) -> None:
    _r14_z91(c)


def _r14_z91v_reentrega_2s(c: dict[str, Any]) -> None:
    _r14_z91(c, 763000.0)


def _r14_neg_entrega_tras_cut(c: dict[str, Any]) -> None:
    _r14_z91(c, 763600.0)


def _r14_complete(c: dict[str, Any], skip: tuple[float, ...] = ()) -> int:
    n = 0
    for ev in list(c["samples"]["bridge_tap.jsonl"]):
        if ev.get("dir") == "resp" and ev.get("path") == "/poll" and ev.get("http") == 200:
            t = float(ev["t_ms"])
            if t in skip:
                continue
            ops = (ev.get("body") or {}).get("ops") or []
            if not ops:
                continue
            o = ops[0]
            # v1.3.14 (T2f-15c): la fixture ya trae la peticion de cada 200; no duplicarla.
            _exists = any(
                e.get("dir") == "req" and e.get("path") == "/poll" and
                abs(float(e.get("t_ms") or 0.0) - (t - 0.5)) < 1e-6 and
                str((e.get("query") or {}).get("session") or "") == str(o["session"]) and
                str((e.get("query") or {}).get("inst") or "") == str(o["inst"])
                for e in c["samples"]["bridge_tap.jsonl"])
            if not _exists:
                _r13_poll_req(c, t - 0.5, str(o["session"]), peer="server",
                              inst=str(o["inst"]), conn=str(o["conn"]),
                              rid=ev["req_id"])
                n += 1
    _r6_sort(c)
    return n


def _r14_g01(c: dict[str, Any], srv_req: float, cli_req: float, r409: float,
             cli_hello: float, new_sess: str, old_sess: str, srv_inst: str, epoch: str,
             with_client: bool = True, resp_200: float | None = None) -> None:
    _r10_add_hello(c, cli_hello, cli_hello + 5.0, new_sess, peer="client",
                   inst=_R14_CLIENT_INST, epoch=epoch)
    a = _r15c_rid(c)
    b = a + 1
    _r15c_poll_req(c, srv_req, old_sess, "server", srv_inst, "1", a)
    if with_client:
        _r15c_poll_req(c, cli_req, new_sess, "client", _R14_CLIENT_INST, "1", b)
        _r15c_poll_resp(c, r409, 409, [], b)
    if resp_200 is not None:
        _r15c_poll_200(c, resp_200)["req_id"] = a
    _r6_sort(c)


def _r14_g01a(c: dict[str, Any]) -> None:
    _r14_g01(c, 373690.0, 373695.0, 373702.0, 373620.0, "b2" * 8, "a1" * 8,
             _R14_E1, _R14_E1, resp_200=373700.0)


def _r14_g01b(c: dict[str, Any]) -> None:
    _r14_g01(c, 551490.0, 551495.0, 551502.0, 551120.0, "d4" * 8, "c3" * 8,
             _R14_E1, _R14_E1, resp_200=551500.0)


def _r14_g01c(c: dict[str, Any]) -> None:
    _r14_g01(c, 762490.0, 762495.0, 762502.0, 762120.0, "e5" * 8, "d4" * 8,
             _R14_E3, _R14_E3, resp_200=762500.0)


def _r14_ctl_solo_servidor_viejo(c: dict[str, Any]) -> None:
    _r14_g01(c, 373690.0, 373695.0, 373702.0, 373620.0, "b2" * 8, "a1" * 8,
             _R14_E1, _R14_E1, with_client=False, resp_200=373700.0)


def _r14_base_completa(c: dict[str, Any]) -> None:
    _r14_complete(c)


def _r14_g01a_p3_completo(c: dict[str, Any]) -> None:
    _r14_complete(c, skip=(373700.0,))
    _r14_g01(c, 373690.0, 373695.0, 373702.0, 373620.0, "b2" * 8, "a1" * 8,
             _R14_E1, _R14_E1, resp_200=373700.0)


def _r14_g01c_p5_completo(c: dict[str, Any]) -> None:
    _r14_complete(c, skip=(762500.0,))
    _r14_g01(c, 762490.0, 762495.0, 762502.0, 762120.0, "e5" * 8, "d4" * 8,
             _R14_E3, _R14_E3, resp_200=762500.0)


def _r14_g02a_p3_retenida_completo(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r13_poll_req(c, 373002.0, "a1" * 8, peer="server", inst=_R14_E1)
    _r6_sort(c)


def _r14_g02c_p5_retenida_completo(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r13_poll_req(c, 761001.0, "d4" * 8, peer="server", inst=_R14_E3)
    _r6_sort(c)


def _r14_g04(c: dict[str, Any], t_req: float, inst: str) -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, t_req, "d4" * 8, peer="server", inst=inst, rid=a)
    _r13_poll_resp(c, 621452.0, 200, ops=[], rid=a)


def _r14_g04a(c: dict[str, Any]) -> None:
    _r14_g04(c, 621450.0, _R14_E1)


def _r14_g04b(c: dict[str, Any]) -> None:
    _r14_g04(c, 621200.0, _R14_E1)


def _r14_g04_pos_registro_nuevo(c: dict[str, Any]) -> None:
    _r14_g04(c, 621450.0, "e2" * 16)


SOL_POSITIVES_R14: dict[str, dict[str, Any]] = {
    "r14_control_desplazado": {
        "apply": _r14_control_desplazado, "expected_exit_code": 0, "red_exit": 0},
    "r14_z91v_reentrega_2s": {
        "apply": _r14_z91v_reentrega_2s, "expected_exit_code": 0, "red_exit": 1},
    "r14_base_completa": {
        "apply": _r14_base_completa, "expected_exit_code": 0, "red_exit": 0},
    "r14_g02a_p3_retenida_completo": {
        "apply": _r14_g02a_p3_retenida_completo, "expected_exit_code": 0, "red_exit": 0},
    "r14_g02c_p5_retenida_completo": {
        "apply": _r14_g02c_p5_retenida_completo, "expected_exit_code": 0, "red_exit": 0},
    "r14_g04_pos_registro_nuevo": {
        "apply": _r14_g04_pos_registro_nuevo, "expected_exit_code": 0, "red_exit": 0},
}

SOL_NEGATIVES_R14: dict[str, dict[str, Any]] = {
    "r14_g01a_p3_srv_vieja_cli_nueva": {
        "apply": _r14_g01a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r14_g01b_p4a_srv_vieja_cli_nueva": {
        "apply": _r14_g01b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"}, "red_exit": 0},
    "r14_g01c_p5_srv_muere_cli_nueva": {
        "apply": _r14_g01c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r14_g01a_p3_completo": {
        "apply": _r14_g01a_p3_completo, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r14_g04a_inst_vieja_tras_hello": {
        "apply": _r14_g04a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 0},
    "r14_g04b_retenida_tras_hello": {
        "apply": _r14_g04b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 0},
}

SOL_MUTANTS_R14: dict[str, dict[str, Any]] = {
    "r14_neg_entrega_tras_cut": {
        "apply": _r14_neg_entrega_tras_cut, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r14_g01c_p5_completo": {
        "apply": _r14_g01c_p5_completo, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
}

SOL_CASES_R14: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R14.items():
    SOL_CASES_R14[_name] = {"kind": "mutant", "name": _name, "check": "T2f-14"}
for _name, _spec in SOL_NEGATIVES_R14.items():
    SOL_CASES_R14[_name] = {"kind": "negative", "name": _name, "check": "T2f-14"}
for _name, _spec in SOL_POSITIVES_R14.items():
    SOL_CASES_R14[_name] = {"kind": "positive", "name": _name, "check": "T2f-14"}

SOL_CASES.update(SOL_CASES_R14)

# ---------------------------------------------------------------------------------------------------
# T2f-15: la entrega de otra conexion (BLOQ de Sol sobre la rama sin pareja de G-01).
# ---------------------------------------------------------------------------------------------------

def _r15_conn(c: dict[str, Any], session: str, op_id: str, op_conn: int,
              result_conn: str) -> None:
    target = (session, op_id)
    for entry in c["samples"]["bridge_tap.jsonl"]:
        kind = entry.get("path")
        way = entry.get("dir")
        if kind == "/poll" and way == "resp":
            for order in (entry.get("body") or {}).get("ops") or []:
                if isinstance(order, dict) and (order.get("session"), order.get("op_id")) == target:
                    order["conn"] = op_conn
        elif kind == "/result" and way == "req":
            body = entry.get("body") or {}
            pair = (body.get("session"), body.get("op_id"))
            if pair == target:
                entry["query"]["conn"] = result_conn
    _r6_sort(c)


def _r15_sol(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "b2" * 8, "rd-1", 2, "2")


def _r15_sol_guarda(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "b2" * 8, "rd-1", 2, "1")


def _r15_p2(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "a1" * 8, "op-1", 2, "2")


def _r15_p2n(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "a1" * 8, "op-2", 2, "2")


def _r15_p3c(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "c3" * 8, "op-3", 2, "2")


def _r15_p4a(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "d4" * 8, "rd-1", 2, "2")


def _r15_p4b(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "d4" * 8, "op-4", 2, "2")


def _r15_p4c(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "d4" * 8, "op-5", 2, "2")


def _r15_p5(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_conn(c, "d4" * 8, "op-6", 2, "2")


def _r15_faithful(c: dict[str, Any]) -> None:
    """La conn fiel al bridge real: new_conn = old + 1 por peer dentro de un backend."""
    tap = c["samples"]["bridge_tap.jsonl"]
    backend = c["samples"]["backend.jsonl"]
    cuts = []
    for event in backend:
        if event.get("kind") == "restart" and \
                str((event.get("data") or {}).get("target") or "") == "backend":
            cuts.append(float(event["t_ms"]))
    cuts.sort()
    edges = [float("-inf")] + cuts + [float("inf")]

    def segment(when: float) -> int:
        idx = 0
        while idx + 1 < len(edges) and not (edges[idx] <= when < edges[idx + 1]):
            idx += 1
        return min(idx, len(edges) - 2)

    tap.sort(key=lambda row: float(row["t_ms"]))
    waiting = None
    seen: dict[int, int] = {}
    live: dict[int, int] = {}
    for event in tap:
        when = float(event["t_ms"])
        where = segment(when)
        kind = event.get("path")
        way = event.get("dir")
        if kind == "/hello" and way == "req":
            waiting = event.get("body")
            continue
        if kind == "/hello" and way == "resp":
            payload = event.get("body") or {}
            peer = (waiting or {}).get("peer") if isinstance(waiting, dict) else None
            good_http = event.get("http") == 200
            if good_http and payload.get("ok") is True and peer == "server":
                seen[where] = 1 + seen.get(where, 0)
                live[where] = seen[where]
                payload["conn"] = live[where]
            waiting = None
            continue
        if kind == "/poll" and way == "req":
            query = event.get("query")
            if isinstance(query, dict) and query.get("peer") == "server" and where in live:
                query["conn"] = str(live[where])
            continue
        if kind == "/poll" and way == "resp":
            if where in live:
                for order in (event.get("body") or {}).get("ops") or []:
                    if isinstance(order, dict):
                        order["conn"] = live[where]
            continue
        if kind == "/result" and way == "req":
            query = event.get("query")
            if isinstance(query, dict) and query.get("peer") == "server" and where in live:
                query["conn"] = str(live[where])
    _r6_sort(c)


def _r15_pos_fiel(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15_faithful(c)


def _r15_pos_fiel_base(c: dict[str, Any]) -> None:
    _r15_faithful(c)


SOL_POSITIVES_R15: dict[str, dict[str, Any]] = {
    "r15_pos_conn_fiel_al_bridge": {
        "apply": _r15_pos_fiel, "expected_exit_code": 0, "red_exit": 0},
    "r15_pos_conn_fiel_al_bridge_base": {
        "apply": _r15_pos_fiel_base, "expected_exit_code": 0, "red_exit": 0},
}

SOL_NEGATIVES_R15: dict[str, dict[str, Any]] = {
    "r15_sol_op_conn_otra": {
        "apply": _r15_sol, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_p2_op1_conn_otra": {
        "apply": _r15_p2, "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
        "must_detail": {"F2P-01": "tap_trace_mismatch", "F2P-04": "tap_trace_mismatch"},
        "red_exit": 0},
    "r15_p2n_op2_conn_otra": {
        "apply": _r15_p2n, "expected_exit_code": 1,
        "must_fail_status": {"F2P-03": "fail"},
        "must_detail": {"F2P-03": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_p3c_op3_conn_otra": {
        "apply": _r15_p3c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-06": "fail"},
        "must_detail": {"F2P-06": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_p4a_rd1_conn_otra": {
        "apply": _r15_p4a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-08": "fail"},
        "must_detail": {"F2P-08": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_p4b_op4_conn_otra": {
        "apply": _r15_p4b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_p4c_op5_conn_otra": {
        "apply": _r15_p4c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_p5_op6_conn_otra": {
        "apply": _r15_p5, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
}

SOL_MUTANTS_R15: dict[str, dict[str, Any]] = {
    "r15_guarda_resultado_otra_conn": {
        "apply": _r15_sol_guarda, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 1},
}

SOL_CASES_R15: dict[str, dict[str, Any]] = {}
for _name, _spec in SOL_MUTANTS_R15.items():
    SOL_CASES_R15[_name] = {"kind": "mutant", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}

SOL_CASES.update(SOL_CASES_R15)

# ---------------------------------------------------------------------------------------------------
# T2f-15b: los BLOQ de la decima pasada (H-01 a H-05).
# ---------------------------------------------------------------------------------------------------

_R15B_E1, _R15B_E2, _R15B_E3 = "e1" * 16, "e2" * 16, "e3" * 16
_R15B_CC = "cc" * 16


def _r15b_poll_200(c: dict[str, Any], t: float) -> dict[str, Any]:
    hits = [e for e in c["samples"]["bridge_tap.jsonl"]
            if e.get("dir") == "resp" and e.get("path") == "/poll" and
            float(e.get("t_ms") or 0.0) == t and (e.get("body") or {}).get("ops")]
    assert len(hits) == 1, (t, len(hits))
    return hits[0]


def _r15b_cut_op(c: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(_r15b_poll_200(c, 761000.0)["body"]["ops"][0])


def _r15b_hello_req(c: dict[str, Any], t: float, peer: str, inst: str, epoch: str) -> int:
    return _r10_add_hello(c, t, t, None, peer=peer, inst=inst, epoch=epoch, with_resp=False)


def _r15b_hello_resp(c: dict[str, Any], t: float, session: str, rid: int,
                     conn: int = 1) -> None:
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "resp", "method": "POST", "path": "/hello", "http": 200,
         "req_id": rid,
         "body": {"ok": True, "session": session, "conn": conn}})
    _r6_sort(c)


def _r15b_client_cycle(c: dict[str, Any]) -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, 373551.0, "a1" * 8, peer="client", inst=_R15B_CC, rid=a)
    _r13_poll_resp(c, 373553.0, 409, rid=a)
    b = a + 1
    _r13_poll_req(c, 373650.0, "b2" * 8, peer="client", inst=_R15B_CC, rid=b)
    _r13_poll_resp(c, 375650.0, 200, ops=[], rid=b)


def _r15b_h01b(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r15b_poll_200(c, 761000.0)["body"]["ops"][0]["inst"] = _R15B_E1


def _r15b_h01d(c: dict[str, Any]) -> None:
    _r14_complete(c)
    o = _r15b_cut_op(c)
    o["conn"] = 2
    _a = _r15c_rid(c)
    _r15c_poll_req(c, 761290.0, "d4" * 8, "server", _R15B_E3, "1", _a)
    _r15c_poll_resp(c, 761300.0, 200, [o], _a)


def _r15b_h01e(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r10_add_hello(c, 551110.0, 551115.0, "d4" * 8, peer="client", inst=_R15B_CC,
                   epoch=_R15B_E1)
    _a = _r15c_rid(c)
    _r15c_poll_req(c, 761290.0, "d4" * 8, "client", _R15B_CC, "1", _a)
    _r15c_poll_resp(c, 761300.0, 200, [_r15b_cut_op(c)], _a)


def _r15b_h01f(c: dict[str, Any]) -> None:
    _r14_complete(c)
    _r10_add_hello(c, 551110.0, 551115.0, "d4" * 8, peer="client", inst=_R15B_CC,
                   epoch=_R15B_E1)
    _a = _r15c_rid(c)
    _r15c_poll_req(c, 760990.0, "d4" * 8, "client", _R15B_CC, "1", _a)
    _r15c_poll_200(c, 761000.0)["req_id"] = _a


def _r15b_h02a(c: dict[str, Any]) -> None:
    _r14_complete(c)
    a = _r15b_hello_req(c, 373598.0, "client", _R15B_CC, _R15B_E1)
    _r15b_hello_resp(c, 373603.0, "b2" * 8, a)
    _r15b_client_cycle(c)


def _r15b_h08a(c: dict[str, Any]) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    pair = [entry for entry in tap
            if entry.get("path") == "/hello" and float(entry.get("t_ms") or 0.0) == 100305.0]
    assert len(pair) == 2, pair
    ordered = []
    for wanted in ("req", "resp"):
        ordered.extend(entry for entry in pair if entry.get("dir") == wanted)
    for entry in pair:
        tap.remove(entry)
    tap.extend(ordered)
    _r6_sort(c)


def _r15b_h08b(c: dict[str, Any]) -> None:
    req = next(e for e in c["samples"]["bridge_tap.jsonl"]
               if e.get("path") == "/hello" and e.get("dir") == "req" and
               float(e.get("t_ms") or 0.0) == 100305.0)
    req["t_ms"] = 100303.0
    _r6_sort(c)


def _r15b_h08c(c: dict[str, Any]) -> None:
    _r14_complete(c)
    a = _r15b_hello_req(c, 373602.0, "client", _R15B_CC, _R15B_E1)
    _r15b_hello_resp(c, 373607.0, "b2" * 8, a)
    _r15b_client_cycle(c)


def _r15b_set_conn(c: dict[str, Any], sess: str, lo: float, hi: float, conn: int) -> None:
    for entry in c["samples"]["bridge_tap.jsonl"]:
        when = float(entry.get("t_ms") or 0.0)
        if when < lo or when >= hi:
            continue
        body = entry.get("body") or {}
        kind = entry.get("path")
        way = entry.get("dir")
        if kind == "/poll" and way == "resp":
            for order in body.get("ops") or []:
                if isinstance(order, dict) and order.get("session") == sess:
                    order["conn"] = conn
        elif kind == "/result" and way == "req" and body.get("session") == sess:
            query = entry.get("query")
            if isinstance(query, dict):
                query.update({"conn": str(conn)})
        elif kind == "/poll" and way == "req":
            query = entry.get("query") or {}
            if query.get("peer") == "server" and query.get("session") == sess:
                query["conn"] = str(conn)


def _r15b_h03b(c: dict[str, Any]) -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, 250000.0, "a1" * 8, peer="server", inst=_R15B_E1, conn="1", rid=a)
    _r13_poll_resp(c, 250002.0, 409, rid=a)
    b = _r15b_hello_req(c, 250100.0, "server", _R15B_E1, _R15B_E1)
    _r15b_hello_resp(c, 250105.0, "a1" * 8, b, 3)
    _r15b_set_conn(c, "a1" * 8, 250105.0, 373500.0, 3)
    _r14_complete(c)


def _r15b_ghost(c: dict[str, Any], op_id: str = "op-6", verb: str = "scene.observe") -> None:
    order = _r15b_cut_op(c)
    order["op_id"] = op_id
    order["verb"] = verb
    order["issued_ms"] = 694990
    order["inst"] = _R15B_E2
    order["epoch"] = _R15B_E2
    if verb == "scene.observe":
        doc = str((order.get("args") or {}).get("doc_id") or "")
        order["args"] = {"f2": 1, "doc_id": doc}
    rid = _r15c_rid(c)
    _r15c_poll_req(c, 694999.5, str(order.get("session") or ""), "server",
                   str(order.get("inst") or ""), str(order.get("conn") or ""), rid)
    _r15c_poll_resp(c, 695000.0, 200, [order], rid)


def _r15b_h04a(c: dict[str, Any]) -> None:
    _r15b_ghost(c)


def _r15b_h04b(c: dict[str, Any]) -> None:
    _r15b_ghost(c, verb="scene.apply")


def _r15b_h04c(c: dict[str, Any]) -> None:
    _r15b_ghost(c, op_id="op-9")


SOL_POSITIVES_R15.update({
    "r15_h02a_cruzados_cliente_primero": {
        "apply": _r15b_h02a, "expected_exit_code": 0, "red_exit": 1},
    "r15_h08a_p1_mismo_ms": {
        "apply": _r15b_h08a, "expected_exit_code": 0, "red_exit": 1},
    "r15_h08b_p1_cruzados_servidor_primero": {
        "apply": _r15b_h08b, "expected_exit_code": 0, "red_exit": 1},
    "r15_h08c_p3_cruzados_servidor_primero": {
        "apply": _r15b_h08c, "expected_exit_code": 0, "red_exit": 1},
    "r15_h03b_conn_tras_lease_perdido": {
        "apply": _r15b_h03b, "expected_exit_code": 0, "red_exit": 0},
})

SOL_NEGATIVES_R15.update({
    "r15_h01b_p5_op_cortada_inst_e1": {
        "apply": _r15b_h01b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_h01d_p5_reentrega_conn_2": {
        "apply": _r15b_h01d, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_h01e_p5_reentrega_al_cliente": {
        "apply": _r15b_h01e, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_h01f_p5_unica_entrega_al_cliente": {
        "apply": _r15b_h01f, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_h04a_p4c_op6_observe_sin_resultado": {
        "apply": _r15b_h04a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_h04b_p4c_op6_apply_sin_resultado": {
        "apply": _r15b_h04b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-09": ["fail"], "F2P-13": ["missing"]},
        "red_exit": 1},
})

SOL_MUTANTS_R15.update({
    "r15_h04c_ctl_p4c_op9_sin_resultado": {
        "apply": _r15b_h04c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 1},
})

for _name, _spec in SOL_MUTANTS_R15.items():
    SOL_CASES_R15[_name] = {"kind": "mutant", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}
SOL_CASES.update(SOL_CASES_R15)

# ---------------------------------------------------------------------------------------------------
# T2f-15c: el req_id del tap (v1.3.14) y las anclas de identidad (E-04).
# ---------------------------------------------------------------------------------------------------

_R15C_E1, _R15C_E2, _R15C_E3 = "e1" * 16, "e2" * 16, "e3" * 16
_R15C_CC = "cc" * 16


def _r15c_rid(c: dict[str, Any]) -> int:
    ids = [e["req_id"] for e in c["samples"]["bridge_tap.jsonl"]
           if isinstance(e.get("req_id"), int)]
    return (max(ids) if ids else -1) + 1


def _r15c_poll_req(c: dict[str, Any], t: float, session: str, peer: str, inst: str,
                   conn: str, rid: int) -> None:
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "req", "method": "GET", "path": "/poll", "req_id": rid,
         "query": {"peer": peer, "inst": inst, "session": session, "conn": conn}})
    _r6_sort(c)


def _r15c_poll_resp(c: dict[str, Any], t: float, http: int, ops: list[Any] | None,
                    rid: int) -> None:
    body = ({"ok": True, "now_ms": t, "ops": list(ops or [])} if http == 200
            else {"ok": False, "error": "hello_required"})
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "resp", "method": "GET", "path": "/poll", "http": http,
         "body": body, "req_id": rid})
    _r6_sort(c)


def _r15c_hello_req(c: dict[str, Any], t: float, peer: str, inst: str, epoch: str,
                    rid: int) -> None:
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "req", "method": "POST", "path": "/hello", "http": 200, "req_id": rid,
         "body": {"proto": "dsbx1", "peer": peer, "inst": inst, "epoch": epoch, "build": "diag",
                  "world_size": 16384}})
    _r6_sort(c)


def _r15c_hello_resp(c: dict[str, Any], t: float, session: str, conn: int, rid: int) -> None:
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": t, "dir": "resp", "method": "POST", "path": "/hello", "http": 200, "req_id": rid,
         "body": {"ok": True, "session": session, "conn": conn}})
    _r6_sort(c)


def _r15c_poll_200(c: dict[str, Any], t: float) -> dict[str, Any]:
    hits = [e for e in c["samples"]["bridge_tap.jsonl"]
            if e.get("dir") == "resp" and e.get("path") == "/poll" and
            float(e.get("t_ms") or 0.0) == t and (e.get("body") or {}).get("ops")]
    assert len(hits) == 1, (t, len(hits))
    return hits[0]



def _r15c_cruce(c: dict[str, Any], srv_req: float, cli_req: float, resp_200: float,
                r409: float, old_sess: str, new_sess: str, srv_inst: str, epoch: str,
                valid: bool) -> None:
    a = _r15c_rid(c)
    b = a + 1
    _r15c_poll_req(c, srv_req, old_sess, "server", srv_inst, "1", a)
    _r15c_poll_req(c, cli_req, new_sess, "server", srv_inst, "1", b)
    ev = _r15c_poll_200(c, resp_200)
    ev["req_id"] = b if valid else a
    _r15c_poll_resp(c, r409, 409, [], b if not valid else a)


def _r15c_cruce_p3_neg(c: dict[str, Any]) -> None:
    _r15c_cruce(c, 373690.0, 373695.0, 373700.0, 373702.0, "a1" * 8, "b2" * 8,
                _R15C_E1, _R15C_E1, False)


def _r15c_cruce_p3_pos(c: dict[str, Any]) -> None:
    _r15c_cruce(c, 373690.0, 373695.0, 373700.0, 373702.0, "a1" * 8, "b2" * 8,
                _R15C_E1, _R15C_E1, True)


def _r15c_cruce_p5_neg(c: dict[str, Any]) -> None:
    _r15c_cruce(c, 762490.0, 762495.0, 762500.0, 762502.0, "d4" * 8, "e5" * 8,
                _R15C_E3, _R15C_E3, False)


def _r15c_cruce_p5_pos(c: dict[str, Any]) -> None:
    _r15c_cruce(c, 762490.0, 762495.0, 762500.0, 762502.0, "d4" * 8, "e5" * 8,
                _R15C_E3, _R15C_E3, True)


def _r15c_hellos(c: dict[str, Any], t_req: float, t_resp: float, srv_inst: str,
                 epoch: str, sess: str, conn_srv: int, conn_cli: int, poll_conn: str,
                 rid0: int) -> None:
    _r15c_hello_req(c, t_req, "server", srv_inst, epoch, rid0)
    _r15c_hello_req(c, t_req + 2.0, "client", _R15C_CC, epoch, rid0 + 1)
    _r15c_hello_resp(c, t_resp, sess, conn_srv, rid0)
    _r15c_hello_resp(c, t_resp + 2.0, sess, conn_cli, rid0 + 1)
    _r15c_poll_req(c, t_resp + 15.0, sess, "server", srv_inst, poll_conn, rid0 + 2)
    _r15c_poll_resp(c, t_resp + 17.0, 200, [], rid0 + 2)


def _r15c_p4b_neg(c: dict[str, Any]) -> None:
    _r15c_hellos(c, 621500.0, 621505.0, _R15C_E2, _R15C_E2, "d4" * 8, 1, 2, "2",
                 _r15c_rid(c))


def _r15c_p4b_pos(c: dict[str, Any]) -> None:
    _r15c_hellos(c, 621500.0, 621505.0, _R15C_E2, _R15C_E2, "d4" * 8, 1, 2, "1",
                 _r15c_rid(c))


def _r15c_p4c_neg(c: dict[str, Any]) -> None:
    _r15c_hellos(c, 700920.0, 700925.0, _R15C_E3, _R15C_E3, "d4" * 8, 1, 2, "2",
                 _r15c_rid(c))


def _r15c_p4c_pos(c: dict[str, Any]) -> None:
    _r15c_hellos(c, 700920.0, 700925.0, _R15C_E3, _R15C_E3, "d4" * 8, 1, 2, "1",
                 _r15c_rid(c))


def _r15c_solape(c: dict[str, Any], cli_hello: float, srv_req: float, cli_req: float,
                 cli_200: float, srv_200: float, sess: str, inst: str) -> None:
    a = _r15c_rid(c)
    _r15c_hello_req(c, cli_hello, "client", _R15C_CC, inst, a + 2)
    _r15c_hello_resp(c, cli_hello + 2.0, sess, 1, a + 2)
    _r15c_poll_req(c, srv_req, sess, "server", inst, "1", a)
    _r15c_poll_req(c, cli_req, sess, "client", _R15C_CC, "1", a + 1)
    _r15c_poll_resp(c, cli_200, 200, [], a + 1)
    ev = _r15c_poll_200(c, srv_200)
    ev["req_id"] = a


def _r15c_solape_p3(c: dict[str, Any]) -> None:
    _r15c_solape(c, 373610.0, 373690.0, 373695.0, 373697.0, 373700.0, "b2" * 8, _R15C_E1)


def _r15c_solape_p5(c: dict[str, Any]) -> None:
    _r15c_solape(c, 762020.0, 762490.0, 762495.0, 762497.0, 762500.0, "e5" * 8, _R15C_E3)


def _r15c_drop_id(c: dict[str, Any], t: float, path: str, dir_: str) -> None:
    ev = next(e for e in c["samples"]["bridge_tap.jsonl"]
              if e.get("path") == path and e.get("dir") == dir_ and
              float(e.get("t_ms") or 0.0) == t)
    ev.pop("req_id", None)


def _r15c_no_req_poll_p3(c: dict[str, Any]) -> None:
    _r15c_drop_id(c, 373700.0, "/poll", "resp")


def _r15c_no_req_poll_p5(c: dict[str, Any]) -> None:
    _r15c_drop_id(c, 762500.0, "/poll", "resp")


def _r15c_no_req_hello_p3(c: dict[str, Any]) -> None:
    _r15c_drop_id(c, 373600.0, "/hello", "req")


def _r15c_no_req_hello_p4a(c: dict[str, Any]) -> None:
    _r15c_drop_id(c, 551100.0, "/hello", "req")


def _r15c_orphan_p3(c: dict[str, Any]) -> None:
    _r15c_poll_200(c, 373700.0)["req_id"] = 9999


def _r15c_orphan_p5(c: dict[str, Any]) -> None:
    _r15c_poll_200(c, 762500.0)["req_id"] = 9999


def _r15c_dup_p3(c: dict[str, Any]) -> None:
    rid = _r15c_poll_200(c, 373700.0)["req_id"]
    ev = next(e for e in c["samples"]["bridge_tap.jsonl"]
              if e.get("path") == "/poll" and e.get("dir") == "resp" and
              float(e.get("t_ms") or 0.0) == 373552.0)
    ev["req_id"] = rid


def _r15c_dup_p5(c: dict[str, Any]) -> None:
    rid = _r15c_poll_200(c, 762500.0)["req_id"]
    ev = next(e for e in c["samples"]["bridge_tap.jsonl"]
              if e.get("path") == "/poll" and e.get("dir") == "resp" and
              float(e.get("t_ms") or 0.0) == 762052.0)
    ev["req_id"] = rid


def _r15c_e04(c: dict[str, Any], hello_t: float, sess: str, lo: float, hi: float,
              everything: bool) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    greeting = next(entry for entry in tap
                    if entry.get("path") == "/hello" and entry.get("dir") == "req" and
                    float(entry.get("t_ms") or 0.0) == hello_t)
    greeting["body"].pop("inst", None)
    if not everything:
        return
    for entry in tap:
        when = float(entry.get("t_ms") or 0.0)
        if when < lo or when >= hi:
            continue
        kind = entry.get("path")
        way = entry.get("dir")
        if kind == "/poll" and way == "req":
            query = entry.get("query") if isinstance(entry.get("query"), dict) else {}
            if str(query.get("session") or "") == sess and str(query.get("peer") or "") == "server":
                query.pop("inst", None)
        elif kind == "/poll" and way == "resp":
            for order in (entry.get("body") or {}).get("ops") or []:
                if isinstance(order, dict) and order.get("session") == sess:
                    order.pop("inst", None)
        elif kind == "/result" and way == "req":
            if sess == (entry.get("body") or {}).get("session"):
                query = entry.get("query")
                if isinstance(query, dict):
                    query.pop("inst", None)


def _r15c_e04a(c: dict[str, Any]) -> None:
    _r15c_e04(c, 762100.0, "e5" * 8, 762000.0, 820000.0, True)


def _r15c_e04b(c: dict[str, Any]) -> None:
    _r15c_e04(c, 762100.0, "e5" * 8, 762000.0, 820000.0, False)


def _r15c_e04c(c: dict[str, Any]) -> None:
    _r15c_e04(c, 373600.0, "b2" * 8, 373500.0, 376500.0, True)


def _r15c_g04_inst(c: dict[str, Any], hello_t: float, resp_t: float) -> None:
    """G-04: quita la inst de todo lo que el backend sellaría con ese registro en su tramo.

    Desde su `/hello` hasta el siguiente `/hello`: la petición de `/poll`, las ops entregadas y las
    peticiones de `/result`. Así el servidor sustituido no tiene identidad en ningún sitio (E-04).
    """
    tap = c["samples"]["bridge_tap.jsonl"]
    ev = next(e for e in tap
              if e.get("path") == "/hello" and e.get("dir") == "req" and
              float(e.get("t_ms") or 0.0) == hello_t)
    ev["body"].pop("inst", None)
    nxt = min((float(e.get("t_ms") or 0.0) for e in tap
               if e.get("path") == "/hello" and e.get("dir") == "req" and
               float(e.get("t_ms") or 0.0) > hello_t),
              default=float("inf"))
    for e in tap:
        t = float(e.get("t_ms") or 0.0)
        if not (hello_t <= t < nxt):
            continue
        if e.get("dir") == "req" and e.get("path") == "/poll":
            q = e.get("query") if isinstance(e.get("query"), dict) else {}
            q.pop("inst", None)
        if e.get("dir") == "resp" and e.get("path") == "/poll":
            for o in (e.get("body") or {}).get("ops") or []:
                if isinstance(o, dict):
                    o.pop("inst", None)
        if e.get("dir") == "req" and e.get("path") == "/result":
            q = e.get("query") if isinstance(e.get("query"), dict) else {}
            q.pop("inst", None)
    _r6_sort(c)


def _r15c_g04_p4b(c: dict[str, Any]) -> None:
    _r15c_g04_inst(c, 621400.0, 623000.0)


def _r15c_g04_p4c(c: dict[str, Any]) -> None:
    _r15c_g04_inst(c, 621400.0, 691000.0)


def _r15c_no_epoch(c: dict[str, Any], op_id: str, sess: str) -> None:
    for e in c["samples"]["bridge_tap.jsonl"]:
        if e.get("dir") == "resp" and e.get("path") == "/poll":
            for o in (e.get("body") or {}).get("ops") or []:
                if isinstance(o, dict) and o.get("op_id") == op_id and o.get("session") == sess:
                    o.pop("epoch", None)
        if e.get("dir") == "req" and e.get("path") == "/result":
            b = e.get("body") or {}
            if b.get("op_id") == op_id and b.get("session") == sess:
                b.pop("epoch", None)


def _r15c_no_epoch_p4b(c: dict[str, Any]) -> None:
    _r15c_no_epoch(c, "op-4", "d4" * 8)


def _r15c_no_epoch_p4c(c: dict[str, Any]) -> None:
    _r15c_no_epoch(c, "op-5", "d4" * 8)


SOL_POSITIVES_R15.update({
    "r15_cruce_p3_pos": {
        "apply": _r15c_cruce_p3_pos, "expected_exit_code": 0, "red_exit": 0},
    "r15_cruce_p5_pos": {
        "apply": _r15c_cruce_p5_pos, "expected_exit_code": 0, "red_exit": 0},
    "r15_hellos_p4b_pos": {
        "apply": _r15c_p4b_pos, "expected_exit_code": 0, "red_exit": 0},
    "r15_hellos_p4c_pos": {
        "apply": _r15c_p4c_pos, "expected_exit_code": 0, "red_exit": 0},
    "r15_solape_p3": {
        "apply": _r15c_solape_p3, "expected_exit_code": 0, "red_exit": 0},
    "r15_solape_p5": {
        "apply": _r15c_solape_p5, "expected_exit_code": 0, "red_exit": 0},
})

SOL_NEGATIVES_R15.update({
    "r15_cruce_p3_neg": {
        "apply": _r15c_cruce_p3_neg, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_cruce_p5_neg": {
        "apply": _r15c_cruce_p5_neg, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_hellos_p4b_neg": {
        "apply": _r15c_p4b_neg, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_hellos_p4c_neg": {
        "apply": _r15c_p4c_neg, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_no_req_poll_p3": {
        "apply": _r15c_no_req_poll_p3, "expected_exit_code": 2,
        "must_fail_status": {"F2P-05": "missing"},
        "must_detail": {"F2P-05": "tap_req_id_missing"}, "red_exit": 0},
    "r15_no_req_poll_p5": {
        "apply": _r15c_no_req_poll_p5, "expected_exit_code": 2,
        "must_fail_status": {"F2P-09": "missing"},
        "must_detail": {"F2P-09": "tap_req_id_missing"}, "red_exit": 0},
    "r15_no_req_hello_p3": {
        "apply": _r15c_no_req_hello_p3, "expected_exit_code": 2,
        "must_fail_status": {"F2P-05": "missing"},
        "must_detail": {"F2P-05": "tap_req_id_missing"}, "red_exit": 0},
    "r15_no_req_hello_p4a": {
        "apply": _r15c_no_req_hello_p4a, "expected_exit_code": 2,
        "must_fail_status": {"F2P-08": "missing"},
        "must_detail": {"F2P-08": "tap_req_id_missing"}, "red_exit": 0},
    "r15_orphan_p3": {
        "apply": _r15c_orphan_p3, "expected_exit_code": 2,
        "must_fail_status": {"F2P-05": "missing"},
        "must_detail": {"F2P-05": "tap_req_id_missing"}, "red_exit": 0},
    "r15_orphan_p5": {
        "apply": _r15c_orphan_p5, "expected_exit_code": 2,
        "must_fail_status": {"F2P-09": "missing"},
        "must_detail": {"F2P-09": "tap_req_id_missing"}, "red_exit": 0},
    "r15_dup_p3": {
        "apply": _r15c_dup_p3, "expected_exit_code": 2,
        "must_fail_status": {"F2P-05": "missing"},
        "must_detail": {"F2P-05": "tap_req_id_missing"}, "red_exit": 0},
    "r15_dup_p5": {
        "apply": _r15c_dup_p5, "expected_exit_code": 2,
        "must_fail_status": {"F2P-09": "missing"},
        "must_detail": {"F2P-09": "tap_req_id_missing"}, "red_exit": 0},
    "r15_e04a_p5_inst_vacia": {
        "apply": _r15c_e04a, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_e04c_p3_inst_vacia": {
        "apply": _r15c_e04c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-05": "fail"},
        "must_detail": {"F2P-05": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_g04_inst_p4b": {
        "apply": _r15c_g04_p4b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-10": ["missing"], "F2P-13": ["missing"]},
        "red_exit": 2},
    "r15_g04_inst_p4c": {
        "apply": _r15c_g04_p4c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"},
        "allowed_non_pass": {"F2P-10": ["missing"], "F2P-13": ["missing"]},
        "red_exit": 2},
    "r15_no_epoch_p4b": {
        "apply": _r15c_no_epoch_p4b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 0},
    "r15_no_epoch_p4c": {
        "apply": _r15c_no_epoch_p4c, "expected_exit_code": 1,
        "must_fail_status": {"F2P-07": "fail"},
        "must_detail": {"F2P-07": "tap_trace_mismatch"}, "red_exit": 0},
})

SOL_MUTANTS_R15.update({
    "r15_e04b_ctl_p5_solo_hello": {
        "apply": _r15c_e04b, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
})

for _name, _spec in SOL_MUTANTS_R15.items():
    SOL_CASES_R15[_name] = {"kind": "mutant", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}
SOL_CASES.update(SOL_CASES_R15)

# ---------------------------------------------------------------------------------------------------
# T2f-15f: la conn como la guarda real, el /result sin conn (K-01), req_id fuera de parte (K-02),
# el registro a la hora de la peticion (K-03) y el /result sin respuesta en el corte (K-08).
# ---------------------------------------------------------------------------------------------------

def _r15f_set_conn(c: dict[str, Any], t: float, path: str, conn: str) -> None:
    ev = _r12_tap_at(c, t, path, "req")
    q = ev.get("query")
    if not isinstance(q, dict):
        q = {}
        ev["query"] = q
    q["conn"] = conn


def _r15f_result_conn_part(c: dict[str, Any], part: str) -> None:
    lo, hi = _r5_part_window(c, part)
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") != "req" or ev.get("path") != "/result":
            continue
        t = float(ev.get("t_ms") or 0.0)
        if lo <= t <= hi:
            q = ev.get("query")
            if isinstance(q, dict):
                q["conn"] = "999"


def _r15f_poll_mantenimiento_01_p3(c: dict[str, Any]) -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, 373650.0, "b2" * 8, "server", "e1" * 16, "01", rid=a)
    _r13_poll_resp(c, 373651.0, 200, [], rid=a)


def _r15f_conn_01_p3(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 373699.5, "/poll", "01")


def _r15f_conn_espacio_p5(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 762499.5, "/poll", " 1")


def _r15f_conn_arabe_p4a(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 551499.5, "/poll", "١")


def _r15f_conn_mas1_p3(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 373699.5, "/poll", "+1")


def _r15f_conn_espacio01_p4b(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 622999.5, "/poll", " 01")


def _r15f_conn_float_p5(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 762499.5, "/poll", "1.0")


def _r15f_conn_vacia_p3c(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 491999.5, "/poll", "")


def _r15f_result_conn_x_p2(c: dict[str, Any]) -> None:
    _r15f_set_conn(c, 202000.0, "/result", "x")


def _r15f_result_otra_inst(c: dict[str, Any]) -> None:
    _r12_tap_at(c, 202000.0, "/result", "req")["query"]["inst"] = "e4" * 16


def _r15f_result_otra_sesion(c: dict[str, Any]) -> None:
    ev = _r12_tap_at(c, 202000.0, "/result", "req")
    ev["body"]["session"] = "f0" * 8
    ev["query"]["session"] = "f0" * 8


def _r15f_result_otro_epoch(c: dict[str, Any]) -> None:
    _r12_tap_at(c, 202000.0, "/result", "req")["body"]["epoch"] = "e4" * 16


def _r15f_result_otro_peer(c: dict[str, Any]) -> None:
    _r12_tap_at(c, 202000.0, "/result", "req")["query"]["peer"] = "client"


def _r15f_result_op_sin_entrega(c: dict[str, Any]) -> None:
    _r12_tap_at(c, 202000.0, "/result", "req")["body"]["op_id"] = "op-99"


def _r15f_result_antes_de_entrega(c: dict[str, Any]) -> None:
    _r12_tap_at(c, 202000.0, "/result", "req")["t_ms"] = 200500.0
    _r12_tap_at(c, 202003.0, "/result", "resp")["t_ms"] = 200503.0
    _r6_sort(c)


def _r15f_gap_op(c: dict[str, Any], t: float, peer: str = "server",
                 inst: str = "e1" * 16, rid_mode: str = "ok") -> None:
    session = "a1" * 8
    a = _r15c_rid(c)
    _r13_poll_req(c, t - 0.5, session, peer, inst, "1", rid=a)
    op = {"op_id": "rd-9", "session": session, "conn": 1, "epoch": "e1" * 16,
          "inst": "e1" * 16, "verb": "state.read", "args": {},
          "issued_ms": t - 0.5, "ttl_ms": 5000}
    _r13_poll_resp(c, t, 200, [op], rid=a)
    ev = _r12_tap_at(c, t, "/poll", "resp")
    if rid_mode == "none":
        ev.pop("req_id", None)
    elif rid_mode == "orphan":
        ev["req_id"] = 9999


def _r15f_k02a_ctl_hueco(c: dict[str, Any]) -> None:
    _r15f_gap_op(c, 170000.0, rid_mode="ok")


def _r15f_k02b_hueco_sin_req(c: dict[str, Any]) -> None:
    _r15f_gap_op(c, 170000.0, rid_mode="none")


def _r15f_k02c_hueco_huerfano(c: dict[str, Any]) -> None:
    _r15f_gap_op(c, 170000.0, rid_mode="orphan")


def _r15f_k02d_ctl_p1(c: dict[str, Any]) -> None:
    _r15f_gap_op(c, 150000.0, rid_mode="ok")


def _r15f_k02d_p1_sin_req(c: dict[str, Any]) -> None:
    _r15f_gap_op(c, 150000.0, rid_mode="none")


def _r15f_k02e_ctl_cliente(c: dict[str, Any]) -> None:
    _r15f_gap_op(c, 170000.0, peer="client", inst="cc" * 16, rid_mode="ok")


def _r15f_k02e_cliente_sin_req(c: dict[str, Any]) -> None:
    _r15f_gap_op(c, 170000.0, peer="client", inst="cc" * 16, rid_mode="none")


def _r15f_k02f_hello_sin_req(c: dict[str, Any]) -> None:
    _r12_tap_at(c, 100310.0, "/hello", "resp").pop("req_id", None)


def _r15f_k03a(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    a = _r15c_rid(c)
    _r13_poll_req(c, 249000.0, "a1" * 8, "server", "e1" * 16, "3", rid=a)
    _r13_poll_resp(c, 251000.0, 200, [], rid=a)


def _r15f_k03b(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    a = _r15c_rid(c)
    _r13_poll_req(c, 250200.0, "a1" * 8, "server", "e1" * 16, "3", rid=a)
    _r13_poll_resp(c, 251000.0, 200, [], rid=a)


def _r15f_k03c(c: dict[str, Any]) -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, 621000.0, "d4" * 8, "server", "e2" * 16, "1", rid=a)
    _r13_poll_resp(c, 622500.0, 200, [], rid=a)


def _r15f_k03d(c: dict[str, Any]) -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, 621500.0, "d4" * 8, "server", "e2" * 16, "1", rid=a)
    _r13_poll_resp(c, 622500.0, 200, [], rid=a)


def _r15f_k08b(c: dict[str, Any]) -> None:
    src = copy.deepcopy(_r12_tap_at(c, 765000.0, "/result", "req"))
    src["t_ms"] = 761450.0
    src["req_id"] = _r15c_rid(c)
    src["body"].update({"op_id": "op-6", "session": "d4" * 8})
    src["query"]["session"] = "d4" * 8
    c["samples"]["bridge_tap.jsonl"].append(src)
    _r6_sort(c)


def _r15f_k08a(c: dict[str, Any]) -> None:
    c["samples"]["bridge_tap.jsonl"].remove(_r12_tap_at(c, 202003.0, "/result", "resp"))


def _r15f_k08c(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    a = _r15c_rid(c)
    _r13_poll_req(c, 761470.0, "d4" * 8, "server", "e3" * 16, "1", rid=a)
    _r13_poll_resp(c, 761480.0, 200, [], rid=a)


def _r15f_k08d(c: dict[str, Any]) -> None:
    _r10_add_delivery(c, 761400.0, "op-7", "d4" * 8, "scene.observe", {},
                      inst="e3" * 16, epoch="e3" * 16)
    a = _r15c_rid(c)
    c["samples"]["bridge_tap.jsonl"].append({
        "t_ms": 761450.0, "dir": "req", "method": "POST", "path": "/result",
        "http": 200, "req_id": a,
        "query": {"peer": "server", "inst": "e3" * 16, "session": "d4" * 8},
        "body": {"op_id": "op-7", "session": "d4" * 8, "epoch": "e3" * 16,
                 "status": "done", "reason": "", "dup": False, "read": {}}})
    _r6_sort(c)


def _r15f_k08_at(c: dict[str, Any], t: float) -> None:
    src = copy.deepcopy(_r12_tap_at(c, 765000.0, "/result", "req"))
    src["t_ms"] = float(t)
    src["req_id"] = _r15c_rid(c)
    src["body"].update({"op_id": "op-6", "session": "d4" * 8})
    src["query"]["session"] = "d4" * 8
    c["samples"]["bridge_tap.jsonl"].append(src)
    _r6_sort(c)


def _r15f_k08e(c: dict[str, Any]) -> None:
    _r15f_k08_at(c, 761700.0)


def _r15f_k08f(c: dict[str, Any]) -> None:
    _r15f_k08_at(c, 761500.0)


def _r15f_catalog(c: dict[str, Any], t_req: float, t_resp: float | None) -> None:
    a = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": float(t_req), "dir": "req", "method": "POST", "path": "/catalog",
                "req_id": a,
                "query": {"peer": "server", "inst": "e3" * 16, "session": "d4" * 8},
                "body": {"catalog_id": "ab" * 8, "page": 1, "pages": 2}})
    if t_resp is not None:
        tap.append({"t_ms": float(t_resp), "dir": "resp", "method": "POST", "path": "/catalog",
                    "req_id": a, "http": 200, "body": {"ok": True}})
    _r6_sort(c)


def _r15f_k08h(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15f_catalog(c, 761470.0, 761480.0)


def _r15f_k08i(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15f_catalog(c, 761400.0, 761410.0)


def _r15f_k08j(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15f_catalog(c, 761470.0, None)


SOL_POSITIVES_R15.update({
    "r15_conn_poll_mantenimiento_01_p3": {"apply": _r15f_poll_mantenimiento_01_p3,
                                          "expected_exit_code": 0, "red_exit": 1},
    "r15_conn_200_ops_01_p3": {"apply": _r15f_conn_01_p3,
                               "expected_exit_code": 0, "red_exit": 1},
    "r15_conn_200_ops_espacio_p5": {"apply": _r15f_conn_espacio_p5,
                                    "expected_exit_code": 0, "red_exit": 1},
    "r15_conn_200_ops_arabe_p4a": {"apply": _r15f_conn_arabe_p4a,
                                   "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p2_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P2"),
                                   "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p2n_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P2n"),
                                    "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p3_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P3"),
                                   "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p3c_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P3c"),
                                    "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p4a_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P4a"),
                                    "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p4b_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P4b"),
                                    "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p4c_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P4c"),
                                    "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_p5_result_conn_ignorada": {"apply": lambda c: _r15f_result_conn_part(c, "P5"),
                                   "expected_exit_code": 0, "red_exit": 1},
    "r15_k01_result_conn_x_p2": {"apply": _r15f_result_conn_x_p2,
                                 "expected_exit_code": 0, "red_exit": 1},
    "r15_k03b_ctl_poll_tras_el_hello": {"apply": _r15f_k03b,
                                        "expected_exit_code": 0, "red_exit": 1},
    "r15_k03d_ctl_poll_tras_el_hello_p4b": {"apply": _r15f_k03d,
                                            "expected_exit_code": 0, "red_exit": 1},
    "r15_k08b_result_cortado_sin_respuesta_p5": {"apply": _r15f_k08b,
                                                 "expected_exit_code": 0, "red_exit": 1},
    "r15_k08f_result_cortado_sin_respuesta_en_el_cut": {"apply": _r15f_k08f,
                                                        "expected_exit_code": 0, "red_exit": 1},
    "r15_k08i_catalog_respondido_antes_del_result": {"apply": _r15f_k08i,
                                                     "expected_exit_code": 0, "red_exit": 1},
    "r15_k08j_catalog_posterior_sin_respuesta": {"apply": _r15f_k08j,
                                                 "expected_exit_code": 0, "red_exit": 1},
})

SOL_NEGATIVES_R15.update({
    "r15_conn_200_ops_mas1_p3": {"apply": _r15f_conn_mas1_p3,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-05": "fail"},
                                 "must_detail": {"F2P-05": "tap_trace_mismatch"},
                                 "red_exit": 1},
    "r15_conn_200_ops_espacio01_p4b": {"apply": _r15f_conn_espacio01_p4b,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-07": "fail"},
                                       "must_detail": {"F2P-07": "tap_trace_mismatch"},
                                       "red_exit": 1},
    "r15_conn_200_ops_float_p5": {"apply": _r15f_conn_float_p5,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-09": "fail"},
                                  "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                  "red_exit": 1},
    "r15_conn_200_ops_vacia_p3c": {"apply": _r15f_conn_vacia_p3c,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-06": "fail"},
                                   "must_detail": {"F2P-06": "tap_trace_mismatch"},
                                   "red_exit": 1},
    "r15_k01_result_otra_inst": {"apply": _r15f_result_otra_inst,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                 "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                 "F2P-04": "tap_trace_mismatch"},
                                 "red_exit": 1},
    "r15_k01_result_otra_sesion": {"apply": _r15f_result_otra_sesion,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                   "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                   "F2P-04": "tap_trace_mismatch"},
                                   "red_exit": 1},
    "r15_k01_result_otro_epoch": {"apply": _r15f_result_otro_epoch,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                  "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                  "F2P-04": "tap_trace_mismatch"},
                                  "red_exit": 1},
    "r15_k01_result_otro_peer": {"apply": _r15f_result_otro_peer,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                 "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                 "F2P-04": "tap_trace_mismatch"},
                                 "red_exit": 1},
    "r15_k01_result_op_sin_entrega": {"apply": _r15f_result_op_sin_entrega,
                                      "expected_exit_code": 1,
                                      "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                      "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                      "F2P-04": "tap_trace_mismatch"},
                                      "red_exit": 1},
    "r15_k01_result_antes_de_entrega": {"apply": _r15f_result_antes_de_entrega,
                                        "expected_exit_code": 1,
                                        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                        "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                        "F2P-04": "tap_trace_mismatch"},
                                        "red_exit": 1},
    "r15_k02b_hueco_sin_req_id": {"apply": _r15f_k02b_hueco_sin_req,
                                  "expected_exit_code": 2,
                                  "must_fail_status": {}, "must_reason": "tap_req_id_missing", "red_exit": 1},
    "r15_k02c_hueco_req_id_huerfano": {"apply": _r15f_k02c_hueco_huerfano,
                                       "expected_exit_code": 2,
                                       "must_fail_status": {}, "must_reason": "tap_req_id_missing", "red_exit": 1},
    "r15_k02d_p1_sin_req_id": {"apply": _r15f_k02d_p1_sin_req,
                               "expected_exit_code": 2,
                               "must_fail_status": {}, "must_reason": "tap_req_id_missing", "red_exit": 1},
    "r15_k02e_cliente_hueco_sin_req_id": {"apply": _r15f_k02e_cliente_sin_req,
                                          "expected_exit_code": 2,
                                          "must_fail_status": {}, "must_reason": "tap_req_id_missing", "red_exit": 1},
    "r15_k02f_hello_cliente_p1_sin_req_id": {"apply": _r15f_k02f_hello_sin_req,
                                             "expected_exit_code": 2,
                                             "must_fail_status": {},
                                             "must_reason": "tap_req_id_missing",
                                             "red_exit": 1},
    "r15_k03a_poll_conn_futura_retenido": {"apply": _r15f_k03a,
                                           "expected_exit_code": 1,
                                           "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                           "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                           "F2P-04": "tap_trace_mismatch"},
                                           "red_exit": 1},
    "r15_k03c_poll_inst_futura_retenido_p4b": {"apply": _r15f_k03c,
                                               "expected_exit_code": 1,
                                               "must_fail_status": {"F2P-07": "fail"},
                                               "must_detail": {"F2P-07": "tap_trace_mismatch"},
                                               "red_exit": 1},
    "r15_k08a_result_sin_respuesta_p2": {"apply": _r15f_k08a,
                                         "expected_exit_code": 1,
                                         "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                         "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                         "F2P-04": "tap_trace_mismatch"},
                                         "red_exit": 1},
    "r15_k08c_cortado_con_respuesta_antes_del_cut": {"apply": _r15f_k08c,
                                                     "expected_exit_code": 1,
                                                     "must_fail_status": {"F2P-09": "fail"},
                                                     "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                     "red_exit": 1},
    "r15_k08d_otra_op_en_vuelo_sin_respuesta": {"apply": _r15f_k08d,
                                                "expected_exit_code": 1,
                                                "must_fail_status": {"F2P-09": "fail"},
                                                "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                "red_exit": 1},
    "r15_k08e_result_cortado_sin_respuesta_tras_cut": {"apply": _r15f_k08e,
                                                       "expected_exit_code": 1,
                                                       "must_fail_status": {"F2P-09": "fail"},
                                                       "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                       "red_exit": 1},
    "r15_k08h_catalog_respondido_tras_el_result": {"apply": _r15f_k08h,
                                                   "expected_exit_code": 1,
                                                   "must_fail_status": {"F2P-09": "fail"},
                                                   "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                   "red_exit": 1},
})

SOL_MUTANTS_R15.update({
    "r15_k02a_ctl_hueco_con_req_id": {"apply": _r15f_k02a_ctl_hueco,
                                      "expected_exit_code": 2,
                                      "must_fail_status": {}, "must_reason": "tap_trace_mismatch", "red_exit": 1},
    "r15_k02d_ctl_p1_con_req_id": {"apply": _r15f_k02d_ctl_p1,
                                   "expected_exit_code": 2,
                                   "must_fail_status": {}, "must_reason": "tap_trace_mismatch", "red_exit": 1},
    "r15_k02e_ctl_cliente_con_req_id": {"apply": _r15f_k02e_ctl_cliente,
                                        "expected_exit_code": 2,
                                        "must_fail_status": {}, "must_reason": "tap_trace_mismatch", "red_exit": 1},
})

for _name, _spec in SOL_MUTANTS_R15.items():
    SOL_CASES_R15[_name] = {"kind": "mutant", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}
SOL_CASES.update(SOL_CASES_R15)

# ---------------------------------------------------------------------------------------------------
# T2f-15i: el empate de milisegundo de K-03 (C-02) y el alcance de K-08 con el 502 del tap.
# ---------------------------------------------------------------------------------------------------

_R15I_UP = {"ok": False, "error": "upstream_unreachable"}
_R15I_HR = {"ok": False, "error": "hello_required"}
_R15I_D4, _R15I_E3 = "d4" * 8, "e3" * 16


def _r15i_poll(c: dict[str, Any], t_req: float, t_resp: float, session: str,
               inst: str, conn: str) -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, t_req, session, "server", inst, conn, rid=a)
    _r13_poll_resp(c, t_resp, 200, [], rid=a)


def _r15i_result(c: dict[str, Any], t: float, resp_t: float | None = None, http: int | None = None,
                 body: Any = None, upstream: Any = "absent", op_id: str = "op-6",
                 session: str = _R15I_D4) -> None:
    src = copy.deepcopy(_r12_tap_at(c, 765000.0, "/result", "req"))
    src["t_ms"] = float(t)
    src["req_id"] = _r15c_rid(c)
    src["body"]["op_id"] = op_id
    src["body"]["session"] = session
    src["query"]["session"] = session
    c["samples"]["bridge_tap.jsonl"].append(src)
    if resp_t is not None:
        ev = {"t_ms": float(resp_t), "dir": "resp", "method": "POST"}
        ev.update({"path": "/result", "http": http, "req_id": src["req_id"], "body": body})
        if upstream != "absent":
            ev["upstream_status"] = upstream
        c["samples"]["bridge_tap.jsonl"].append(ev)
    _r6_sort(c)


def _r15i_catalog(c: dict[str, Any], t_req: float, t_resp: float | None,
                  upstream: Any = "absent", peer: str = "server", inst: str = _R15I_E3,
                  http: int = 200) -> None:
    a = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": float(t_req), "dir": "req", "method": "POST", "path": "/catalog",
                "req_id": a, "query": {"peer": peer, "inst": inst, "session": _R15I_D4},
                "body": {"catalog_id": "ab" * 8, "page": 1, "pages": 2}})
    if t_resp is not None:
        ev = {"t_ms": float(t_resp), "dir": "resp", "method": "POST", "path": "/catalog",
              "http": http, "req_id": a,
              "body": {"ok": True} if http == 200 else {"ok": False}}
        if upstream != "absent":
            ev["upstream_status"] = upstream
        tap.append(ev)
    _r6_sort(c)


def _r15i_hello(c: dict[str, Any], t_req: float, t_resp: float | None,
                upstream: Any = "absent", peer: str = "client", inst: str = "cc" * 16,
                http: int = 400) -> None:
    a = _r15c_rid(c)
    tap = c["samples"]["bridge_tap.jsonl"]
    tap.append({"t_ms": float(t_req), "dir": "req", "method": "POST", "path": "/hello",
                "req_id": a, "body": {"proto": "dsbx1", "peer": peer, "inst": inst,
                                      "epoch": _R15I_E3, "build": "diag"}})
    if t_resp is not None:
        ev = {"t_ms": float(t_resp), "dir": "resp", "method": "POST", "path": "/hello",
              "http": http, "req_id": a,
              "body": {"ok": True, "session": _R15I_D4, "conn": 1} if http == 200 else
                      {"ok": False, "error": "bad_request"}}
        if upstream != "absent":
            ev["upstream_status"] = upstream
        tap.append(ev)
    _r6_sort(c)


def _r15i_c02d0(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    _r15i_poll(c, 250105.0, 251000.0, "a1" * 8, "e1" * 16, "3")


def _r15i_c02d1(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    _r15i_poll(c, 250106.0, 251000.0, "a1" * 8, "e1" * 16, "3")


def _r15i_c02e0(c: dict[str, Any]) -> None:
    _r15i_poll(c, 621405.0, 622000.0, _R15I_D4, "e2" * 16, "1")


def _r15i_c02e1(c: dict[str, Any]) -> None:
    _r15i_poll(c, 621406.0, 622000.0, _R15I_D4, "e2" * 16, "1")


def _r15i_c02t1(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    _r15i_poll(c, 250105.0, 250105.0, "a1" * 8, "e1" * 16, "1")


def _r15i_c02t2(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    _r15i_poll(c, 250105.0, 251000.0, "a1" * 8, "e1" * 16, "1")


def _r15i_c02conn(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    _r15i_poll(c, 250105.0, 251000.0, "a1" * 8, "e1" * 16, "5")


def _r15i_c02m1(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    _r15i_poll(c, 250104.0, 251000.0, "a1" * 8, "e1" * 16, "3")


def _r15i_k08k(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 761450.0, 761500.0, 502, _R15I_UP, upstream=None)


def _r15i_k08l(c: dict[str, Any]) -> None:
    _r15i_k08k(c)
    _r15i_result(c, 761750.0, 761751.0, 502, _R15I_UP, upstream=None)
    _r15i_result(c, 762250.0, 762252.0, 409, _R15I_HR)


def _r15i_k08m(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 762010.0, 762011.0, 502, _R15I_UP, upstream=None)


def _r15i_k08n(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 762051.0, 762053.0, 502, _R15I_UP, upstream=None)


def _r15i_k08o(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 762052.0, 762053.0, 502, _R15I_UP, upstream=None)


def _r15i_k08p(c: dict[str, Any]) -> None:
    _r15i_result(c, 761440.0)
    _r15f_k08b(c)


def _r15i_k08q(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 761450.0, 761500.0, 502,
                 {"ok": False, "error": "upstream_timeout"}, upstream=None)


def _r15i_k08r(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 761450.0, 761500.0, 502, _R15I_UP, upstream=502)


def _r15i_k08s(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 761450.0, 761500.0, 502, _R15I_UP)


def _r15i_k08t(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r10_add_delivery(c, 761400.0, "op-7", _R15I_D4, "scene.observe", {},
                      inst=_R15I_E3, epoch=_R15I_E3)
    _r15i_result(c, 761750.0, 761751.0, 502, _R15I_UP, upstream=None, op_id="op-7")


def _r15i_k08u(c: dict[str, Any]) -> None:
    _r15i_result(c, 761400.0, 761450.0, 502, _R15I_UP, upstream=None)


def _r15i_k08v(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_result(c, 762060.0, 762061.0, 502, _R15I_UP, upstream=None)


def _r15i_k08w(c: dict[str, Any]) -> None:
    _r15i_result(c, 761600.0, 761601.0, 502, _R15I_UP, upstream=None)


def _r15i_k08x(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_hello(c, 761460.0, 761470.0)


def _r15i_k08y(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_catalog(c, 761460.0, 761470.0)


def _r15i_k08z(c: dict[str, Any]) -> None:
    _r15i_k08k(c)
    _r15i_poll(c, 761460.0, 761470.0, _R15I_D4, _R15I_E3, "1")


def _r15i_k08aa(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_hello(c, 761460.0, 761470.0, upstream=None, http=502)


def _r15i_k08ab(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_catalog(c, 761460.0, 761470.0, upstream=None, http=502)


def _r15i_k08ac(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_poll(c, 761300.0, 761470.0, _R15I_D4, _R15I_E3, "1")


def _r15i_k08ad(c: dict[str, Any]) -> None:
    _r15f_k08b(c)
    _r15i_poll(c, 761450.0, 761451.0, _R15I_D4, _R15I_E3, "1")


def _r15i_move_409_to_end(c: dict[str, Any]) -> None:
    tap = c["samples"]["bridge_tap.jsonl"]
    hits = [e for e in tap if e.get("dir") == "resp" and e.get("req_id") == 45]
    assert len(hits) == 1 and float(hits[0]["t_ms"]) == 762052.0 and hits[0]["http"] == 409, hits
    tap.append(tap.pop(tap.index(hits[0])))


def _r15i_k08ae(c: dict[str, Any]) -> None:
    _r15i_result(c, 761450.0, 761500.0, 502, _R15I_UP, upstream=None)
    _r15i_result(c, 762100.0, 762101.0, 502, _R15I_UP, upstream=None)
    _r15i_move_409_to_end(c)


def _r15i_k08af(c: dict[str, Any]) -> None:
    _r15i_result(c, 761450.0, 761500.0, 502, _R15I_UP, upstream=None)
    _r15i_result(c, 762010.0, 762011.0, 502, _R15I_UP, upstream=None)
    _r15i_move_409_to_end(c)


def _r15i_k08ag(c: dict[str, Any]) -> None:
    _r15i_result(c, 761450.0, 761500.0, 502, _R15I_UP, upstream=None)


def _r15i_k08ah(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15i_result(c, 761750.0, 761751.0, 502, _R15I_UP, upstream=None)
    _r15i_result(c, 762250.0, 762252.0, 409, _R15I_HR)


def _r15i_k08ai(c: dict[str, Any]) -> None:
    _r15i_result(c, 761450.0, 761500.0, 502,
                 {"ok": False, "error": "upstream_timeout"}, upstream=None)


def _r15i_k08aj(c: dict[str, Any]) -> None:
    _r15i_result(c, 761450.0, 761500.0, 502, _R15I_UP, upstream=502)


def _r15i_k08ak(c: dict[str, Any]) -> None:
    _r15i_result(c, 761400.0, 761450.0, 502, _R15I_UP, upstream=None)


def _r15i_k08al(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15i_poll(c, 761460.0, 761470.0, _R15I_D4, _R15I_E3, "1")


def _r15i_c02resp_empate(c: dict[str, Any]) -> None:
    _r15b_h03b(c)
    _r15i_poll(c, 250105.0, 250105.0, "a1" * 8, "e1" * 16, "3")


def _r15i_c02entrega(c: dict[str, Any], op_conn: int) -> None:
    _r15b_h03b(c)
    a = _r15c_rid(c)
    _r13_poll_req(c, 250105.0, "a1" * 8, "server", "e1" * 16, "3", rid=a)
    op = {"op_id": "op-9", "session": "a1" * 8, "conn": op_conn, "epoch": "e1" * 16,
          "inst": "e1" * 16, "verb": "scene.observe", "args": {},
          "issued_ms": 250100.0, "ttl_ms": 5000}
    _r13_poll_resp(c, 250105.0, 200, [op], rid=a)
    _r10_add_result(c, 250106.0, "op-9", "a1" * 8, read={}, inst="e1" * 16, epoch="e1" * 16)


def _r15i_c02entrega_empate(c: dict[str, Any]) -> None:
    _r15i_c02entrega(c, 3)


def _r15i_c02entrega_otra(c: dict[str, Any]) -> None:
    _r15i_c02entrega(c, 5)


SOL_POSITIVES_R15.update({
    "r15_c02d0_conn_nueva_mismo_ms": {"apply": _r15i_c02d0, "expected_exit_code": 0,
                                      "red_exit": 1},
    "r15_c02d1_ctl_1ms_despues": {"apply": _r15i_c02d1, "expected_exit_code": 0,
                                  "red_exit": 1},
    "r15_c02e0_inst_nueva_mismo_ms_p4b": {"apply": _r15i_c02e0, "expected_exit_code": 0,
                                          "red_exit": 1},
    "r15_c02e1_ctl_1ms_despues_p4b": {"apply": _r15i_c02e1, "expected_exit_code": 0,
                                      "red_exit": 1},
    "r15_c02t1_conn_vieja_mismo_ms_inmediata": {"apply": _r15i_c02t1,
                                                "expected_exit_code": 0, "red_exit": 1},
    "r15_k08k_502_tap_en_el_cut": {"apply": _r15i_k08k, "expected_exit_code": 0,
                                   "red_exit": 1},
    "r15_k08l_502_tap_reintentos_y_409": {"apply": _r15i_k08l, "expected_exit_code": 0,
                                          "red_exit": 1},
    "r15_k08m_502_tap_tras_restart": {"apply": _r15i_k08m, "expected_exit_code": 0,
                                      "red_exit": 1},
    "r15_k08n_502_tap_pedido_762051": {"apply": _r15i_k08n, "expected_exit_code": 0,
                                       "red_exit": 1},
    "r15_k08o_502_tap_empate_762052": {"apply": _r15i_k08o, "expected_exit_code": 0,
                                       "red_exit": 1},
    "r15_k08p_dos_result_sin_respuesta_antes_cut": {"apply": _r15i_k08p,
                                                    "expected_exit_code": 0, "red_exit": 1},
    "r15_k08aa_hello_tap_502": {"apply": _r15i_k08aa, "expected_exit_code": 0, "red_exit": 1},
    "r15_k08ab_catalog_tap_502": {"apply": _r15i_k08ab, "expected_exit_code": 0, "red_exit": 1},
    "r15_k08ac_poll_antes_del_result": {"apply": _r15i_k08ac, "expected_exit_code": 0,
                                        "red_exit": 1},
    "r15_k08ad_poll_mismo_ms_del_result": {"apply": _r15i_k08ad, "expected_exit_code": 0,
                                           "red_exit": 1},
    "r15_k08af_orden_409_al_final_pos": {"apply": _r15i_k08af, "expected_exit_code": 0,
                                         "red_exit": 1},
    "r15_k08ag_forma_real_a": {"apply": _r15i_k08ag, "expected_exit_code": 0, "red_exit": 1},
    "r15_k08ah_forma_real_b": {"apply": _r15i_k08ah, "expected_exit_code": 0, "red_exit": 1},
    "r15_c02resp_empate": {"apply": _r15i_c02resp_empate, "expected_exit_code": 0,
                           "red_exit": 1},
    "r15_c02entrega_empate": {"apply": _r15i_c02entrega_empate, "expected_exit_code": 0,
                              "red_exit": 1},
})

SOL_NEGATIVES_R15.update({
    "r15_c02t2_conn_vieja_mismo_ms_retenida": {"apply": _r15i_c02t2,
                                               "expected_exit_code": 1,
                                               "must_fail_status": {"F2P-01": "fail",
                                                                    "F2P-04": "fail"},
                                               "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                               "F2P-04": "tap_trace_mismatch"},
                                               "red_exit": 1},
    "r15_c02conn_ni_vieja_ni_nueva": {"apply": _r15i_c02conn,
                                      "expected_exit_code": 1,
                                      "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                      "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                      "F2P-04": "tap_trace_mismatch"},
                                      "red_exit": 1},
    "r15_c02d_m1_conn_nueva_1ms_antes": {"apply": _r15i_c02m1,
                                         "expected_exit_code": 1,
                                         "must_fail_status": {"F2P-01": "fail",
                                                              "F2P-04": "fail"},
                                         "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                         "F2P-04": "tap_trace_mismatch"},
                                         "red_exit": 1},
    "r15_k08q_502_otro_cuerpo": {"apply": _r15i_k08q,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-09": "fail"},
                                 "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                 "red_exit": 1},
    "r15_k08r_502_upstream_502": {"apply": _r15i_k08r,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-09": "fail"},
                                  "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                  "red_exit": 1},
    "r15_k08s_502_sin_upstream": {"apply": _r15i_k08s,
                                  "expected_exit_code": 1,
                                  "must_fail_status": {"F2P-09": "fail"},
                                  "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                  "red_exit": 1},
    "r15_k08t_502_otra_identidad": {"apply": _r15i_k08t,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-09": "fail"},
                                    "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                    "red_exit": 1},
    "r15_k08u_502_antes_del_cut": {"apply": _r15i_k08u,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-09": "fail"},
                                   "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                   "red_exit": 1},
    "r15_k08v_502_reintento_tras_762052": {"apply": _r15i_k08v,
                                           "expected_exit_code": 1,
                                           "must_fail_status": {"F2P-09": "fail"},
                                           "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                           "red_exit": 1},
    "r15_k08w_502_sin_primer_result_antes_cut": {"apply": _r15i_k08w,
                                                 "expected_exit_code": 1,
                                                 "must_fail_status": {"F2P-09": "fail"},
                                                 "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                 "red_exit": 1},
    "r15_k08x_hello_cliente_400_tras_result": {"apply": _r15i_k08x,
                                               "expected_exit_code": 1,
                                               "must_fail_status": {"F2P-09": "fail"},
                                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                               "red_exit": 1},
    "r15_k08y_catalog_backend_tras_result": {"apply": _r15i_k08y,
                                             "expected_exit_code": 1,
                                             "must_fail_status": {"F2P-09": "fail"},
                                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                             "red_exit": 1},
    "r15_k08z_502_y_poll_backend_tras_result": {"apply": _r15i_k08z,
                                                "expected_exit_code": 1,
                                                "must_fail_status": {"F2P-09": "fail"},
                                                "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                "red_exit": 1},
    "r15_k08ae_orden_409_al_final_neg": {"apply": _r15i_k08ae,
                                         "expected_exit_code": 1,
                                         "must_fail_status": {"F2P-09": "fail"},
                                         "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                         "red_exit": 1},
    "r15_k08ai_forma_real_c": {"apply": _r15i_k08ai,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-09": "fail"},
                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                               "red_exit": 1},
    "r15_k08aj_forma_real_d": {"apply": _r15i_k08aj,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-09": "fail"},
                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                               "red_exit": 1},
    "r15_k08ak_forma_real_e": {"apply": _r15i_k08ak,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-09": "fail"},
                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                               "red_exit": 1},
    "r15_k08al_forma_real_f": {"apply": _r15i_k08al,
                               "expected_exit_code": 1,
                               "must_fail_status": {"F2P-09": "fail"},
                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                               "red_exit": 1},
    "r15_c02entrega_conn_otra": {"apply": _r15i_c02entrega_otra,
                                 "expected_exit_code": 1,
                                 "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                 "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                 "F2P-04": "tap_trace_mismatch"},
                                 "red_exit": 1},
})

for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}
SOL_CASES.update(SOL_CASES_R15)

# ---------------------------------------------------------------------------------------------------
# T2f-15k: la identidad de los exentos que sobran, el cuerpo exacto del 502, el acuse en el mismo ms
# y un solo orden por empate.
# ---------------------------------------------------------------------------------------------------

def _r15k_result(c: dict[str, Any], t: float, resp_t: float | None = None, http: int | None = None,
                 body: Any = None, upstream: Any = "absent", op_id: str = "op-6",
                 session: str = _R15I_D4, inst: str = _R15I_E3, epoch: str = _R15I_E3,
                 peer: str = "server", qsession: str | None = None) -> None:
    src = copy.deepcopy(_r12_tap_at(c, 765000.0, "/result", "req"))
    src["t_ms"] = float(t)
    src["req_id"] = _r15c_rid(c)
    src["body"].update({"op_id": op_id, "session": session, "epoch": epoch})
    q = src.setdefault("query", {})
    q["session"] = qsession if qsession is not None else session
    q["inst"] = inst
    q["peer"] = peer
    c["samples"]["bridge_tap.jsonl"].append(src)
    if resp_t is not None:
        ev = {"t_ms": float(resp_t), "dir": "resp", "method": "POST"}
        ev.update({"path": "/result", "http": http, "req_id": src["req_id"], "body": body})
        if upstream != "absent":
            ev["upstream_status"] = upstream
        c["samples"]["bridge_tap.jsonl"].append(ev)
    _r6_sort(c)


def _r15k_resend(c: dict[str, Any], t: float, inst: str = _R15I_E3,
                 epoch: str = _R15I_E3, http: int = 409,
                 body: Any = None) -> None:
    _r15k_result(c, t, t + 2.0, http, body if body is not None else _R15I_HR,
                 op_id="op-6", session=_R15I_D4, inst=inst, epoch=epoch, qsession="e5" * 8)


def _r15k_entrega(c: dict[str, Any], poll_conn: str, op_conn: int) -> None:
    _r15b_h03b(c)
    a = _r15c_rid(c)
    _r13_poll_req(c, 250105.0, "a1" * 8, "server", "e1" * 16, poll_conn, rid=a)
    op = {"op_id": "op-9", "session": "a1" * 8, "conn": op_conn, "epoch": "e1" * 16,
          "inst": "e1" * 16, "verb": "scene.observe", "args": {},
          "issued_ms": 250100.0, "ttl_ms": 5000}
    _r13_poll_resp(c, 250105.0, 200, [op], rid=a)
    _r10_add_result(c, 250106.0, "op-9", "a1" * 8, read={}, inst="e1" * 16, epoch="e1" * 16)


def _r15k_extra(c: dict[str, Any], t: float = 761750.0, peer: str = "server",
                inst: str = _R15I_E3, epoch: str = _R15I_E3,
                qsession: str | None = None) -> None:
    _r15f_k08b(c)
    _r15k_result(c, t, None, op_id="op-6", session=_R15I_D4, inst=inst, epoch=epoch,
                 peer=peer, qsession=qsession)


def _r15k_k08am(c: dict[str, Any]) -> None:
    _r15k_extra(c, peer="client")


def _r15k_k08an(c: dict[str, Any]) -> None:
    _r15k_extra(c, inst="e4" * 16)


def _r15k_k08ao(c: dict[str, Any]) -> None:
    _r15k_extra(c, epoch="e4" * 16)


def _r15k_k08ap(c: dict[str, Any]) -> None:
    _r15k_extra(c, qsession="e5" * 8)


def _r15k_k08aq(c: dict[str, Any]) -> None:
    _r15k_extra(c, inst="", epoch="")


def _r15k_k08ar(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15k_result(c, 761750.0, 761751.0, 502, _R15I_UP, upstream=None, epoch="e4" * 16)


def _r15k_k08as(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15k_result(c, 761750.0, 761700.0, 502, _R15I_UP, upstream=None)


def _r15k_k08at(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r12_tap_at(c, 762250.0, "/result", "req")["query"]["inst"] = "e4" * 16


def _r15k_k08au(c: dict[str, Any]) -> None:
    _r15k_resend(c, 762250.0, http=400, body={"ok": False})
    _r15k_resend(c, 762450.0, inst="", epoch="", http=400, body={"ok": False})


def _r15k_k08av(c: dict[str, Any]) -> None:
    _r15k_resend(c, 762250.0)
    _r15k_resend(c, 762450.0, inst="e4" * 16)


def _r15k_k08aw(c: dict[str, Any]) -> None:
    for _t in (762250.0, 762450.0):
        _r15k_resend(c, _t)
        _r12_tap_at(c, _t, "/result", "req")["query"]["session"] = _R15I_D4


def _r15k_k08ax(c: dict[str, Any]) -> None:
    _r15k_result(c, 761450.0, 761500.0, 502,
                 {"ok": 0, "error": "upstream_unreachable"}, upstream=None)


def _r15k_k08ay(c: dict[str, Any]) -> None:
    _r15k_result(c, 761450.0, 761500.0, 502,
                 {"ok": 0.0, "error": "upstream_unreachable"}, upstream=None)


def _r15k_k08az(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15k_result(c, 761750.0, 761751.0, 502, "texto", upstream=None)


def _r15k_k08ba(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15k_result(c, 761750.0, 761751.0, 500, [], upstream=500)


def _r15k_k08bb(c: dict[str, Any]) -> None:
    _r15k_result(c, 761450.0, 761500.0, 503, dict(_R15I_UP), upstream=None)


def _r15k_k08bc(c: dict[str, Any]) -> None:
    ack = _r12_tap_at(c, 202003.0, "/result", "resp")
    ack["t_ms"] = 202000.0
    _r6_sort(c)


def _r15k_k08bd(c: dict[str, Any]) -> None:
    _r15k_result(c, 761500.0, 761500.0, 502, dict(_R15I_UP), upstream=None)


def _r15k_k08be(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15i_catalog(c, 761460.0, 761500.0)
    _r15k_result(c, 761750.0, 761751.0, 502, dict(_R15I_UP), upstream=None)


def _r15k_k08bf(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15i_catalog(c, 761460.0, 761500.0)


def _r15k_c06a(c: dict[str, Any]) -> None:
    _r15k_entrega(c, "3", 1)


def _r15k_c06b(c: dict[str, Any]) -> None:
    _r15k_entrega(c, "1", 3)


SOL_POSITIVES_R15.update({
    "r15_k08aw_dos_409_ctl": {"apply": _r15k_k08aw, "expected_exit_code": 0, "red_exit": 1},
    "r15_k08bc_acuse_mismo_ms_p2": {"apply": _r15k_k08bc, "expected_exit_code": 0,
                                    "red_exit": 1},
    "r15_k08bd_result_en_el_cut_502_mismo_ms": {"apply": _r15k_k08bd,
                                                "expected_exit_code": 0, "red_exit": 1},
    "r15_k08bf_c05a_sin_reintento": {"apply": _r15k_k08bf, "expected_exit_code": 0,
                                     "red_exit": 1},
})

SOL_NEGATIVES_R15.update({
    "r15_k08am_sobrante_peer_cliente": {"apply": _r15k_k08am,
                                        "expected_exit_code": 1,
                                        "must_fail_status": {"F2P-09": "fail"},
                                        "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                        "red_exit": 1},
    "r15_k08an_sobrante_otra_inst": {"apply": _r15k_k08an,
                                     "expected_exit_code": 1,
                                     "must_fail_status": {"F2P-09": "fail"},
                                     "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                     "red_exit": 1},
    "r15_k08ao_sobrante_otro_epoch": {"apply": _r15k_k08ao,
                                      "expected_exit_code": 1,
                                      "must_fail_status": {"F2P-09": "fail"},
                                      "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                      "red_exit": 1},
    "r15_k08ap_sobrante_query_otra_sesion": {"apply": _r15k_k08ap,
                                             "expected_exit_code": 1,
                                             "must_fail_status": {"F2P-09": "fail"},
                                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                             "red_exit": 1},
    "r15_k08aq_sobrante_sin_inst_ni_epoch": {"apply": _r15k_k08aq,
                                             "expected_exit_code": 1,
                                             "must_fail_status": {"F2P-09": "fail"},
                                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                             "red_exit": 1},
    "r15_k08ar_reintento_otro_epoch": {"apply": _r15k_k08ar,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-09": "fail"},
                                       "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                       "red_exit": 1},
    "r15_k08as_reintento_502_antes_de_su_peticion": {"apply": _r15k_k08as,
                                                     "expected_exit_code": 1,
                                                     "must_fail_status": {"F2P-09": "fail"},
                                                     "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                     "red_exit": 1},
    "r15_k08at_reenvio409_otra_inst": {"apply": _r15k_k08at,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-09": "fail"},
                                       "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                       "red_exit": 1},
    "r15_k08au_c15d_sobrante_sin_inst_ni_epoch": {"apply": _r15k_k08au,
                                                  "expected_exit_code": 1,
                                                  "must_fail_status": {"F2P-09": "fail"},
                                                  "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                  "red_exit": 1},
    "r15_k08av_dos_409_segundo_otra_inst": {"apply": _r15k_k08av,
                                            "expected_exit_code": 1,
                                            "must_fail_status": {"F2P-09": "fail"},
                                            "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                            "red_exit": 1},
    "r15_k08ax_502_ok_0": {"apply": _r15k_k08ax,
                           "expected_exit_code": 1,
                           "must_fail_status": {"F2P-09": "fail"},
                           "must_detail": {"F2P-09": "tap_trace_mismatch"},
                           "red_exit": 1},
    "r15_k08ay_502_ok_0_0": {"apply": _r15k_k08ay,
                             "expected_exit_code": 1,
                             "must_fail_status": {"F2P-09": "fail"},
                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                             "red_exit": 1},
    "r15_k08az_reintento_502_cuerpo_texto": {"apply": _r15k_k08az,
                                             "expected_exit_code": 1,
                                             "must_fail_status": {"F2P-09": "fail"},
                                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                             "red_exit": 1},
    "r15_k08ba_reintento_500_lista": {"apply": _r15k_k08ba,
                                      "expected_exit_code": 1,
                                      "must_fail_status": {"F2P-09": "fail"},
                                      "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                      "red_exit": 1},
    "r15_k08bb_503_nulo_cuerpo_exacto": {"apply": _r15k_k08bb,
                                         "expected_exit_code": 1,
                                         "must_fail_status": {"F2P-09": "fail"},
                                         "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                         "red_exit": 1},
    "r15_k08be_c05a_catalog_en_el_cut_y_reintento": {"apply": _r15k_k08be,
                                                     "expected_exit_code": 1,
                                                     "must_fail_status": {"F2P-09": "fail"},
                                                     "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                     "red_exit": 1},
    "r15_c06a_poll_conn_nueva_op_vieja": {"apply": _r15k_c06a,
                                          "expected_exit_code": 1,
                                          "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                          "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                          "F2P-04": "tap_trace_mismatch"},
                                          "red_exit": 1},
    "r15_c06b_poll_conn_vieja_op_nueva": {"apply": _r15k_c06b,
                                          "expected_exit_code": 1,
                                          "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                          "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                          "F2P-04": "tap_trace_mismatch"},
                                          "red_exit": 1},
})

for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}
SOL_CASES.update(SOL_CASES_R15)

# ---------------------------------------------------------------------------------------------------
# T2f-15l: un solo orden total en el ms del cut, el cierre sin respuesta, la entrega sin registro y
# W-07.
# ---------------------------------------------------------------------------------------------------

_R15L_OP6 = {"op_id": "op-6", "session": _R15I_D4, "conn": 1, "epoch": _R15I_E3,
             "inst": _R15I_E3, "verb": "scene.apply", "args": {"f2": 1, "doc_id": "d-7c19e2a5"},
             "issued_ms": 760950.0, "ttl_ms": 5000}


def _r15l_poll(c: dict[str, Any], t_req: float, t_resp: float, peer: str = "server",
               inst: str = _R15I_E3, conn: str = "1", ops: list[Any] | None = None,
               http: int = 200, body: Any = None, upstream: Any = "absent") -> None:
    a = _r15c_rid(c)
    _r13_poll_req(c, t_req, _R15I_D4, peer, inst, conn, rid=a)
    ev = _r12_tap_at(c, t_req, "/poll", "req")
    ev["query"]["deliver"] = "0" if not ops else "1"
    tap = c["samples"]["bridge_tap.jsonl"]
    resp = {"t_ms": float(t_resp), "dir": "resp", "method": "GET"}
    resp.update({"path": "/poll", "http": http, "req_id": a,
                 "body": body if body is not None else
                 ({"ok": True, "now_ms": t_resp, "ops": list(ops or [])} if http == 200 else
                  {"ok": False, "error": "hello_required"})})
    if upstream != "absent":
        resp["upstream_status"] = upstream
    tap.append(resp)
    _r6_sort(c)


def _r15l_close(c: dict[str, Any], t_req: float, t_resp: float, peer: str = "server",
                inst: str = _R15I_E3, conn: str = "1", upstream: Any = 0,
                body: Any = "") -> None:
    _r15l_poll(c, t_req, t_resp, peer, inst, conn, http=0, body=body, upstream=upstream)


def _r15l_upstream_all(c: dict[str, Any]) -> None:
    for ev in c["samples"]["bridge_tap.jsonl"]:
        if ev.get("dir") != "resp" or "upstream_status" in ev:
            continue
        ev.update({"upstream_status": ev.get("http")})


def _r15l_d02(c: dict[str, Any], conn: str, http: Any, op_conn: int) -> None:
    req = _r12_tap_at(c, 200999.5, "/poll", "req")
    req["query"]["conn"] = conn
    resp = _r12_tap_at(c, 201000.0, "/poll", "resp")
    resp["http"] = http
    for o in (resp.get("body") or {}).get("ops") or []:
        if isinstance(o, dict) and o.get("op_id") == "op-1":
            o["conn"] = op_conn


def _r15l_resend(c: dict[str, Any], t: float, http: int, qsession: str | None,
                 body: Any = None, inst: str = _R15I_E3, epoch: str = _R15I_E3) -> None:
    _r15k_result(c, t, t + 2.0, http, body if body is not None else _R15I_HR,
                 op_id="op-6", session=_R15I_D4, inst=inst, epoch=epoch,
                 qsession=qsession if qsession is not None else "")


def _r15l_k08ci(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15l_poll(c, 761440.0, 761500.0)


def _r15l_k08cj(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r10_add_hello(c, 700950.0, 700955.0, _R15I_D4, peer="client", inst="cc" * 16,
                   epoch=_R15I_E3)
    _r15l_poll(c, 759500.0, 761500.0, peer="client", inst="cc" * 16)


def _r15l_k08ck(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15l_poll(c, 761001.0, 761500.0)
    _r15l_upstream_all(c)


def _r15l_k08cl(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    ev = next(e for e in c["samples"]["bridge_tap.jsonl"]
              if e.get("path") == "/result" and e.get("dir") == "resp" and
              float(e.get("t_ms") or 0.0) == 761500.0)
    ev["t_ms"] = 761503.0
    _r10_add_delivery(c, 760990.0, "rd-99", _R15I_D4, "scene.observe", {},
                      inst=_R15I_E3, epoch=_R15I_E3)
    _r15k_result(c, 761500.0, 761500.0, 200, {"ok": True}, op_id="rd-99",
                 session=_R15I_D4, inst=_R15I_E3, epoch=_R15I_E3)
    _r6_sort(c)


def _r15l_k08cm(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15l_poll(c, 761460.0, 761500.0, ops=[dict(_R15L_OP6)])


def _r15l_k08cn(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r10_add_hello(c, 761460.0, 761500.0, _R15I_D4, peer="server",
                   inst=_R15I_E3, epoch=_R15I_E3)


def _r15l_k08co(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15l_poll(c, 761460.0, 761500.0)


def _r15l_k08cp(c: dict[str, Any]) -> None:
    for i in range(5):
        _r15k_result(c, 761500.0, None, op_id=f"rd-{i}", session=_R15I_D4,
                     inst=_R15I_E3, epoch=_R15I_E3)


def _r15l_k08cq(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15l_close(c, 761001.0, 761502.0, peer="client", inst="cc" * 16)


def _r15l_k08cr(c: dict[str, Any]) -> None:
    _r15k_result(c, 761450.0, 761501.0, 0, "", upstream=0)
    _r15k_result(c, 761750.0, 761751.0, 502, dict(_R15I_UP), upstream=None)


def _r15l_k08cs(c: dict[str, Any]) -> None:
    _r15i_k08ag(c)
    _r15l_close(c, 761460.0, 761470.0)


def _r15l_k08ct(c: dict[str, Any]) -> None:
    _r15k_result(c, 761400.0, 761450.0, 0, "", upstream=0)


def _r15l_k08cu(c: dict[str, Any]) -> None:
    _r15k_result(c, 761450.0, 761500.0, 502, dict(_R15I_UP), upstream=None)
    _r10_add_delivery(c, 761400.0, "op-7", _R15I_D4, "scene.observe", {},
                      inst=_R15I_E3, epoch=_R15I_E3)
    _r15k_result(c, 761500.0, 761501.0, 0, "", upstream=0, op_id="op-7")


def _r15l_k08cv(c: dict[str, Any]) -> None:
    _r15k_result(c, 761450.0, 761501.0, 0, {"x": 1}, upstream=0)


def _r15l_k08cw(c: dict[str, Any]) -> None:
    _r15k_result(c, 761450.0, 761501.0, 0, "", upstream=200)


def _r15l_k08cx(c: dict[str, Any]) -> None:
    _r15l_d02(c, "9", 409, 9)


def _r15l_k08cy(c: dict[str, Any]) -> None:
    _r15l_d02(c, "9", "200", 9)


def _r15l_k08cz(c: dict[str, Any]) -> None:
    _r15l_d02(c, "1", 409, 9)


def _r15l_k08da(c: dict[str, Any]) -> None:
    _r15l_d02(c, "1", 409, 1)


def _r15l_k08db(c: dict[str, Any]) -> None:
    _r15l_d02(c, "9", 200, 9)


def _r15l_k08dc(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15l_resend(c, 762450.0, 409, "ff" * 8)


def _r15l_k08dd(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15l_resend(c, 762450.0, 400, "ff" * 8, {"ok": False})


def _r15l_k08de(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r12_tap_at(c, 762250.0, "/result", "req")["query"]["session"] = "ff" * 8


def _r15l_k08df(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15l_resend(c, 762450.0, 400, "", {"ok": False})


def _r15l_k08dg(c: dict[str, Any]) -> None:
    _r15k_result(c, 762250.0, 762252.0, 400, {"ok": False}, qsession="", inst=_R15I_E3,
                 epoch=_R15I_E3)


def _r15l_k08dh(c: dict[str, Any]) -> None:
    _r15k_result(c, 762250.0, 762252.0, 400, {"ok": False}, qsession="e5" * 8,
                 inst=_R15I_E3, epoch=_R15I_E3)


def _r15l_k08di(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r12_tap_at(c, 762250.0, "/result", "req")["query"]["session"] = "d4" * 8


def _r15l_k08dj(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15k_result(c, 761750.0, 761751.0, 500, ["x"], upstream=500)


SOL_POSITIVES_R15.update({
    "r15_k08ci_keepalive_en_el_cut": {"apply": _r15l_k08ci, "expected_exit_code": 0,
                                      "red_exit": 1},
    "r15_k08cj_poll_cliente_antes_del_result_vence_en_el_cut": {"apply": _r15l_k08cj,
                                                               "expected_exit_code": 0,
                                                               "red_exit": 1},
    "r15_k08ck_poll_retenido_servidor_200_en_el_cut_upstream": {"apply": _r15l_k08ck,
                                                               "expected_exit_code": 0,
                                                               "red_exit": 1},
    "r15_k08cq_close_poll_cliente_en_k08ah": {"apply": _r15l_k08cq,
                                              "expected_exit_code": 0, "red_exit": 1},
    "r15_k08cr_close_result_y_reintento": {"apply": _r15l_k08cr,
                                           "expected_exit_code": 0, "red_exit": 1},
    "r15_k08cs_close_keepalive_no_vivo": {"apply": _r15l_k08cs,
                                          "expected_exit_code": 0, "red_exit": 1},
    "r15_k08da_d02_ctl_409_conn_buena": {"apply": _r15l_k08da, "expected_exit_code": 0,
                                         "red_exit": 1},
    "r15_k08dh_d04_ctl_400_en_e5": {"apply": _r15l_k08dh, "expected_exit_code": 0,
                                    "red_exit": 1},
    "r15_k08di_d04_ctl_409_en_d4": {"apply": _r15l_k08di, "expected_exit_code": 0,
                                    "red_exit": 1},
})

SOL_NEGATIVES_R15.update({
    "r15_k08cl_bloq2": {"apply": _r15l_k08cl,
                        "expected_exit_code": 1,
                        "must_fail_status": {"F2P-09": "fail"},
                        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_k08cm_d03e1_reentrega_en_el_cut": {"apply": _r15l_k08cm,
                                            "expected_exit_code": 1,
                                            "must_fail_status": {"F2P-09": "fail"},
                                            "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                            "red_exit": 1},
    "r15_k08cn_d03e2_hello_sesion_que_muere_en_el_cut": {"apply": _r15l_k08cn,
                                                         "expected_exit_code": 1,
                                                         "must_fail_status": {"F2P-09": "fail"},
                                                         "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                                         "red_exit": 1},
    "r15_k08co_d03e3_keepalive_en_el_cut": {"apply": _r15l_k08co,
                                            "expected_exit_code": 1,
                                            "must_fail_status": {"F2P-09": "fail"},
                                            "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                            "red_exit": 1},
    "r15_k08cp_tope_tap_tie_group_too_large": {"apply": _r15l_k08cp,
                                               "expected_exit_code": 2,
                                               "must_fail_status": {"F2P-09": "missing"},
                                               "must_detail": {"F2P-09": "tap_tie_group_too_large"},
                                               "must_reason": "tap_tie_group_too_large",
                                               "red_exit": 1},
    "r15_k08ct_close_result_antes_del_cut": {"apply": _r15l_k08ct,
                                             "expected_exit_code": 1,
                                             "must_fail_status": {"F2P-09": "fail"},
                                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                             "red_exit": 1},
    "r15_k08cu_close_otra_identidad": {"apply": _r15l_k08cu,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-09": "fail"},
                                       "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                       "red_exit": 1},
    "r15_k08cv_close_con_cuerpo": {"apply": _r15l_k08cv,
                                   "expected_exit_code": 1,
                                   "must_fail_status": {"F2P-09": "fail"},
                                   "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                   "red_exit": 1},
    "r15_k08cw_close_upstream_200": {"apply": _r15l_k08cw,
                                     "expected_exit_code": 1,
                                     "must_fail_status": {"F2P-09": "fail"},
                                     "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                     "red_exit": 1},
    "r15_k08cx_d02a_poll_409_conn_ajena": {"apply": _r15l_k08cx,
                                           "expected_exit_code": 1,
                                           "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                           "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                           "F2P-04": "tap_trace_mismatch"},
                                           "red_exit": 1},
    "r15_k08cy_d02b_poll_http_texto": {"apply": _r15l_k08cy,
                                       "expected_exit_code": 1,
                                       "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                       "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                       "F2P-04": "tap_trace_mismatch"},
                                       "red_exit": 1},
    "r15_k08cz_d02_ctl_poll_casa": {"apply": _r15l_k08cz,
                                    "expected_exit_code": 1,
                                    "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                                    "must_detail": {"F2P-01": "tap_trace_mismatch",
                                                    "F2P-04": "tap_trace_mismatch"},
                                    "red_exit": 1},
    "r15_k08db_d02_ctl_200": {"apply": _r15l_k08db,
                              "expected_exit_code": 1,
                              "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
                              "must_detail": {"F2P-01": "tap_trace_mismatch",
                                              "F2P-04": "tap_trace_mismatch"},
                              "red_exit": 1},
    "r15_k08dc_d04w1_segundo_409_query_otra": {"apply": _r15l_k08dc,
                                               "expected_exit_code": 1,
                                               "must_fail_status": {"F2P-09": "fail"},
                                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                               "red_exit": 1},
    "r15_k08dd_d04w2_segundo_400_query_otra": {"apply": _r15l_k08dd,
                                               "expected_exit_code": 1,
                                               "must_fail_status": {"F2P-09": "fail"},
                                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                               "red_exit": 1},
    "r15_k08de_d04w3_unico_409_query_otra": {"apply": _r15l_k08de,
                                             "expected_exit_code": 1,
                                             "must_fail_status": {"F2P-09": "fail"},
                                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                             "red_exit": 1},
    "r15_k08df_d04w4_segundo_400_sin_sesion": {"apply": _r15l_k08df,
                                               "expected_exit_code": 1,
                                               "must_fail_status": {"F2P-09": "fail"},
                                               "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                               "red_exit": 1},
    "r15_k08dg_d04w5_unico_400_sin_sesion": {"apply": _r15l_k08dg,
                                             "expected_exit_code": 1,
                                             "must_fail_status": {"F2P-09": "fail"},
                                             "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                             "red_exit": 1},
    "r15_k08dj_d06_500_lista_en_k08ah": {"apply": _r15l_k08dj,
                                         "expected_exit_code": 1,
                                         "must_fail_status": {"F2P-09": "fail"},
                                         "must_detail": {"F2P-09": "tap_trace_mismatch"},
                                         "red_exit": 1},
})

for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}
SOL_CASES.update(SOL_CASES_R15)

# T2f-15m: H-02, el parser de `/hello`/`/poll`, la envoltura, el tope y los valores del cierre.
# ---------------------------------------------------------------------------------------------------

_R15M_C3 = "c3" * 8


def _r15m_cut_target(c: dict[str, Any], target: str | None) -> None:
    ev = next(e for e in c["samples"]["backend.jsonl"] if e.get("kind") == "cut")
    if target is None:
        ev["data"].pop("target", None)
    else:
        ev["data"]["target"] = target
    _r6_sort(c)


def _r15m_poll(c: dict[str, Any], session: str, body: Any, *, absent: bool = False) -> None:
    src = [e for e in c["samples"]["bridge_tap.jsonl"]
           if e.get("req_id") == 2 and e.get("dir") == "req" and e.get("path") == "/poll"]
    assert len(src) == 1, len(src)
    rid = _r15c_rid(c)
    req = copy.deepcopy(src[0])
    req["t_ms"] = 250000.0
    req["req_id"] = rid
    req["query"]["session"] = session
    c["samples"]["bridge_tap.jsonl"].append(req)
    ev = {"t_ms": 250001.0, "dir": "resp", "method": "GET", "path": "/poll", "http": 200,
          "req_id": rid}
    if not absent:
        ev["body"] = body
    c["samples"]["bridge_tap.jsonl"].append(ev)
    _r6_sort(c)


def _r15m_orphan(c: dict[str, Any], path: str, body: Any, *, absent: bool = False) -> None:
    rid = _r15c_rid(c)
    ev = {"t_ms": 250000.0, "dir": "resp",
          "method": "POST" if path == "/hello" else "GET", "path": path, "http": 200,
          "req_id": rid}
    if not absent:
        ev["body"] = body
    c["samples"]["bridge_tap.jsonl"].append(ev)
    _r6_sort(c)


def _r15m_h02a(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15i_result(c, 761750.0, 762010.0, 409, _R15I_HR)


def _r15m_h02b(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15i_result(c, 761750.0, 762060.0, 409, _R15I_HR)


def _r15m_h02_tap(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15i_result(c, 761750.0, 762010.0, 409, _R15I_HR, upstream=None)


def _r15m_h02_query_otra(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15k_result(c, 761750.0, 762010.0, 409, _R15I_HR, qsession=_R15M_C3)


def _r15m_h02_aceptado(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15i_result(c, 761750.0, 762010.0, 200, {"ok": True})


def _r15m_o1(c: dict[str, Any], session: str, body: Any, *, absent: bool = False) -> None:
    _r15m_poll(c, session, body, absent=absent)


def _r15m_o1_ctl(c: dict[str, Any]) -> None:
    _r15m_poll(c, "a1" * 8, None)


def _r15m_o2(c: dict[str, Any], base: Any, target: str | None) -> None:
    base(c)
    _r15m_cut_target(c, target)


def _r15m_o2_ctl(c: dict[str, Any]) -> None:
    _r15l_k08ci(c)
    _r15m_cut_target(c, "server")


def _r15m_o3_tap_x(c: dict[str, Any]) -> None:
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": "x", "dir": "resp", "method": "POST", "path": "/hello", "http": 200,
         "req_id": _r15c_rid(c), "body": {"ok": True}})


def _r15m_o3_be_x(c: dict[str, Any]) -> None:
    c["samples"]["backend.jsonl"].append({"seq": 0, "t_ms": "x", "kind": "nota",
                                          "data": {}})


def _r15m_o3_segundo_cut_lista(c: dict[str, Any]) -> None:
    c["samples"]["backend.jsonl"].append({"seq": 0, "t_ms": 761600.0, "kind": "cut",
                                          "data": ["x"]})


def _r15m_o3_acuse_texto(c: dict[str, Any]) -> None:
    _r10_add_delivery(c, 760990.0, "rd-99", _R15I_D4, "scene.observe", {},
                      inst=_R15I_E3, epoch=_R15I_E3)
    rid = _r15c_rid(c)
    src = copy.deepcopy(_r12_tap_at(c, 765000.0, "/result", "req"))
    src["t_ms"] = 761500.0
    src["req_id"] = rid
    src["body"].update({"op_id": "rd-99", "session": _R15I_D4})
    src["query"]["session"] = _R15I_D4
    c["samples"]["bridge_tap.jsonl"].append(src)
    c["samples"]["bridge_tap.jsonl"].append(
        {"t_ms": "761500", "dir": "resp", "method": "POST", "path": "/result", "http": 200,
         "req_id": rid, "body": {"ok": True}})
    _r6_sort(c)


def _r15m_o4_tope_p2(c: dict[str, Any]) -> None:
    _r15l_k08cp(c)
    _r15m_poll(c, "ff" * 8, None)


def _r15m_o4_tope_cut_op(c: dict[str, Any]) -> None:
    _r15l_k08cp(c)
    _r15k_result(c, 761450.0, 761501.0, 200, {"ok": True})


def _r15m_l01_catalog(c: dict[str, Any], base: Any, t_req: float, t_resp: float) -> None:
    base(c)
    _r15i_catalog(c, t_req, t_resp, upstream=False)


def _r15m_l01_result_close(c: dict[str, Any]) -> None:
    _r15l_k08cr(c)
    ev = next(e for e in c["samples"]["bridge_tap.jsonl"]
              if e.get("path") == "/result" and e.get("dir") == "resp" and
              float(e.get("t_ms") or 0.0) == 761501.0)
    ev["upstream_status"] = False


def _r15m_l03(c: dict[str, Any], t_req: float, t_ack: float) -> None:
    _r15i_k08ag(c)
    _r15i_result(c, t_req, t_ack, 0, "", upstream=0)


def _r15m_l05(c: dict[str, Any], base: Any, t_req: float, t_ack: float) -> None:
    base(c)
    _r15k_result(c, t_req, t_ack, 400, {"ok": False}, qsession=_R15I_D4)


def _r15m_l05_base(c: dict[str, Any]) -> None:
    _r15k_result(c, 762250.0, 762252.0, 400, {"ok": False}, qsession=_R15I_D4)


def _r15m_l06(c: dict[str, Any]) -> None:
    _r15l_k08cr(c)
    ev = next(e for e in c["samples"]["bridge_tap.jsonl"]
              if e.get("path") == "/result" and e.get("dir") == "resp" and
              float(e.get("t_ms") or 0.0) == 761501.0)
    ev["body"] = {}


def _r15m_o7(c: dict[str, Any]) -> None:
    _r15i_k08ah(c)
    _r15k_result(c, 762250.0, 762252.0, 409, _R15I_HR, qsession="e5" * 8)


SOL_POSITIVES_R15.update({
    "r15_h02a_reintento_409_primera_respuesta_nueva": {
        "apply": _r15m_h02a, "expected_exit_code": 0, "red_exit": 1},
    "r15_h02b_reintento_409_tras_poll_409": {
        "apply": _r15m_h02b, "expected_exit_code": 0, "red_exit": 1},
    "r15_o1_ctl_poll_buena_nulo": {
        "apply": _r15m_o1_ctl, "expected_exit_code": 0, "red_exit": 1},
    "r15_o2_ctl_k08ci_target_server": {
        "apply": _r15m_o2_ctl, "expected_exit_code": 0, "red_exit": 1},
    "r15_o3_tap_t_ms_x": {
        "apply": _r15m_o3_tap_x, "expected_exit_code": 0, "red_exit": 1},
    "r15_o3_be_t_ms_x": {
        "apply": _r15m_o3_be_x, "expected_exit_code": 0, "red_exit": 1},
    "r15_o3_segundo_cut_data_lista": {
        "apply": _r15m_o3_segundo_cut_lista, "expected_exit_code": 0, "red_exit": 1},
})

SOL_NEGATIVES_R15.update({
    "r15_h02_tap_409": {
        "apply": _r15m_h02_tap, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_h02_409_query_otra": {
        "apply": _r15m_h02_query_otra, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_h02_aceptado": {
        "apply": _r15m_h02_aceptado, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o1_poll_ajena_nulo": {
        "apply": lambda c: _r15m_o1(c, "ff" * 8, None), "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
        "must_detail": {"F2P-01": "tap_trace_mismatch", "F2P-04": "tap_trace_mismatch"},
        "red_exit": 1},
    "r15_o1_poll_ajena_ausente": {
        "apply": lambda c: _r15m_o1(c, "ff" * 8, None, absent=True), "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
        "must_detail": {"F2P-01": "tap_trace_mismatch", "F2P-04": "tap_trace_mismatch"},
        "red_exit": 1},
    "r15_o1_poll_ajena_lista_vacia": {
        "apply": lambda c: _r15m_o1(c, "ff" * 8, []), "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
        "must_detail": {"F2P-01": "tap_trace_mismatch", "F2P-04": "tap_trace_mismatch"},
        "red_exit": 1},
    "r15_o1_poll_ajena_lista_x": {
        "apply": lambda c: _r15m_o1(c, "ff" * 8, ["x"]), "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail"},
        "must_detail": {"F2P-01": "tap_trace_mismatch", "F2P-04": "tap_trace_mismatch"},
        "red_exit": 1},
    "r15_o2_bloq2_target_server": {
        "apply": lambda c: _r15m_o2(c, _r15l_k08cl, "server"), "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o2_bloq2_target_ausente": {
        "apply": lambda c: _r15m_o2(c, _r15l_k08cl, None), "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o2_k08cm_target_server": {
        "apply": lambda c: _r15m_o2(c, _r15l_k08cm, "server"), "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o2_k08cn_target_server": {
        "apply": lambda c: _r15m_o2(c, _r15l_k08cn, "server"), "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o2_k08co_target_server": {
        "apply": lambda c: _r15m_o2(c, _r15l_k08co, "server"), "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o3_acuse_texto_en_el_ms": {
        "apply": _r15m_o3_acuse_texto, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o4_tope_mas_p2": {
        "apply": _r15m_o4_tope_p2, "expected_exit_code": 1,
        "must_fail_status": {"F2P-01": "fail", "F2P-04": "fail", "F2P-09": "missing"},
        "must_detail": {"F2P-01": "tap_trace_mismatch", "F2P-04": "tap_trace_mismatch",
                        "F2P-09": "tap_tie_group_too_large"},
        "must_reason": "tap_tie_group_too_large", "red_exit": 1},
    "r15_o4_tope_mas_cut_op_had_result": {
        "apply": _r15m_o4_tope_cut_op, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "cut_op_had_result"}, "red_exit": 1},
    "r15_l01_catalog_false_k08ah": {
        "apply": lambda c: _r15m_l01_catalog(c, _r15i_k08ah, 761600.0, 761700.0),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l01_catalog_false_k08ag": {
        "apply": lambda c: _r15m_l01_catalog(c, _r15i_k08ag, 761460.0, 761470.0),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l01_result_close_false": {
        "apply": _r15m_l01_result_close, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l03_reintento_761750_cerrado_761700": {
        "apply": lambda c: _r15m_l03(c, 761750.0, 761700.0), "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l03_reintento_761850_cerrado_761550": {
        "apply": lambda c: _r15m_l03(c, 761850.0, 761550.0), "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l05_400_d4_762250": {
        "apply": lambda c: _r15m_l05(c, _r15i_k08ah, 762250.0, 762252.0),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l05_400_d4_762050": {
        "apply": lambda c: _r15m_l05(c, _r15i_k08ah, 762050.0, 762052.0),
        "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l05_base_unico_400_d4": {
        "apply": _r15m_l05_base, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l06_cierre_cuerpo_dict_vacio": {
        "apply": _r15m_l06, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_o7_409_query_e5": {
        "apply": _r15m_o7, "expected_exit_code": 1,
        "must_fail_status": {"F2P-09": "fail"},
        "must_detail": {"F2P-09": "tap_trace_mismatch"}, "red_exit": 1},
    "r15_l02_hello_huerfano_sin_cuerpo": {
        "apply": lambda c: _r15m_orphan(c, "/hello", None, absent=True),
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-01": "missing", "F2P-04": "missing"},
        "must_detail": {"F2P-01": "tap_req_id_missing", "F2P-04": "tap_req_id_missing"},
        "must_reason": "tap_req_id_missing", "red_exit": 1},
    "r15_l02_poll_huerfano_cuerpo_nulo": {
        "apply": lambda c: _r15m_orphan(c, "/poll", None),
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-01": "missing", "F2P-04": "missing"},
        "must_detail": {"F2P-01": "tap_req_id_missing", "F2P-04": "tap_req_id_missing"},
        "must_reason": "tap_req_id_missing", "red_exit": 1},
    "r15_l02_hello_huerfano_lista_x": {
        "apply": lambda c: _r15m_orphan(c, "/hello", ["x"]),
        "expected_exit_code": 2,
        "must_fail_status": {"F2P-01": "missing", "F2P-04": "missing"},
        "must_detail": {"F2P-01": "tap_req_id_missing", "F2P-04": "tap_req_id_missing"},
        "must_reason": "tap_req_id_missing", "red_exit": 1},
})

for _name, _spec in SOL_NEGATIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "negative", "name": _name, "check": "T2f-15"}
    SOL_CASES[_name] = SOL_CASES_R15[_name]
for _name, _spec in SOL_POSITIVES_R15.items():
    SOL_CASES_R15[_name] = {"kind": "positive", "name": _name, "check": "T2f-15"}
    SOL_CASES[_name] = SOL_CASES_R15[_name]

MUTANTS: dict[str, dict[str, Any]] = {
    "creation_suppressed": {"apply": _m_creation_suppressed, "expected_exit_code": 1,
                            "must_fail_checks": ["F2P-01"],
                            "allowed_non_pass": {"F2P-02": ["fail"], "F2P-04": ["fail"],
                                                 "F2P-12": ["missing"]}},
    "entity_moved_0p6_witness": {"apply": _m_entity_moved_witness, "expected_exit_code": 1,
                                 "must_fail_checks": ["F2P-02"],
                                 # El nacimiento a 0,6 m ya no casa con su fila del documento y
                                 # F2P-13 lo ve como un extra real.
                                 "allowed_non_pass": {"F2P-01": ["fail"], "F2P-04": ["fail"],
                                                      "F2P-12": ["missing"], "F2P-13": ["fail"]}},
    "entity_moved_0p6_census": {"apply": _m_entity_moved_census, "expected_exit_code": 1,
                                "must_fail_checks": ["F2P-02"],
                                # v1.3.11 (F-06): F2P-01 también compara la pose en el censo.
                                "allowed_non_pass": {"F2P-01": ["fail"], "F2P-12": ["missing"]}},
    "creature_born_1m": {"apply": _m_creature_born_1m, "expected_exit_code": 1,
                         "must_fail_checks": ["F2P-02"], "allowed_non_pass": {}},
    "foreign_moved_to_ground": {"apply": _m_foreign_to_ground, "expected_exit_code": 1,
                                "must_fail_checks": ["F2P-05"], "allowed_non_pass": {}},
    "foreign_container_deleted": {"apply": _m_foreign_container_deleted, "expected_exit_code": 1,
                                  "must_fail_checks": ["F2P-05"], "allowed_non_pass": {}},
    "scene2_entity_deleted": {"apply": _m_scene2_deleted, "expected_exit_code": 1,
                              "must_fail_checks": ["F2P-05"], "allowed_non_pass": {}},
    "duplicate_33_plus_k": {"apply": _m_duplicate, "expected_exit_code": 1,
                            "must_fail_checks": ["F2P-04"],
                            "allowed_non_pass": {"F2P-01": ["fail"], "F2P-13": ["fail"]}},
    "reappears_after_restart": {"apply": _m_reappears, "expected_exit_code": 1,
                                "must_fail_checks": ["F2P-07"], "allowed_non_pass": {}},
    "persistent_control_missing": {"apply": _m_control_missing, "expected_exit_code": 2,
                                   "must_fail_checks": ["F2P-07"], "allowed_non_pass": {}},
    "creature_jump_before_checkpoint": {"apply": _m_creature_jump, "expected_exit_code": 1,
                                        "must_fail_checks": ["F2P-02"], "allowed_non_pass": {}},
    "creature_dead_or_no_ai": {"apply": _m_creature_dead, "expected_exit_code": 1,
                               "must_fail_checks": ["F2P-02"],
                               # v1.3.11 (F-06): F2P-01 también exige la criatura viva.
                               "allowed_non_pass": {"F2P-01": ["fail"]}},
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
                           "must_fail_checks": ["F2P-04"],
                           "allowed_non_pass": {"F2P-01": ["fail"]}},
    "cut_before_first_effect_p5": {"apply": _m_cut_no_effect, "expected_exit_code": 2,
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
            SOL_NEGATIVES.get(name) or SOL_POSITIVES.get(name) or
            SOL_MUTANTS_R2.get(name) or SOL_NEGATIVES_R2.get(name) or
            SOL_POSITIVES_R2.get(name) or SOL_MUTANTS_R3.get(name) or
            SOL_NEGATIVES_R3.get(name) or SOL_POSITIVES_R3.get(name) or
            SOL_INCONCLUSO_R3.get(name) or SOL_MUTANTS_R4.get(name) or
            SOL_NEGATIVES_R4.get(name) or SOL_POSITIVES_R4.get(name) or
            SOL_INCONCLUSO_R4.get(name) or SOL_MUTANTS_R5.get(name) or
            SOL_NEGATIVES_R5.get(name) or SOL_POSITIVES_R5.get(name) or
            SOL_MUTANTS_R6.get(name) or SOL_NEGATIVES_R6.get(name) or
            SOL_POSITIVES_R6.get(name) or SOL_MUTANTS_R7.get(name) or
            SOL_NEGATIVES_R7.get(name) or SOL_POSITIVES_R7.get(name) or
            SOL_MUTANTS_R8.get(name) or SOL_NEGATIVES_R8.get(name) or
            SOL_POSITIVES_R8.get(name) or SOL_MUTANTS_R9.get(name) or
            SOL_NEGATIVES_R9.get(name) or SOL_POSITIVES_R9.get(name) or
            SOL_MUTANTS_R10.get(name) or SOL_NEGATIVES_R10.get(name) or
            SOL_POSITIVES_R10.get(name) or SOL_MUTANTS_R11.get(name) or
            SOL_NEGATIVES_R11.get(name) or SOL_POSITIVES_R11.get(name) or
            SOL_MUTANTS_R12.get(name) or SOL_NEGATIVES_R12.get(name) or
            SOL_POSITIVES_R12.get(name) or SOL_MUTANTS_R13.get(name) or
            SOL_NEGATIVES_R13.get(name) or SOL_POSITIVES_R13.get(name) or
            SOL_MUTANTS_R14.get(name) or SOL_NEGATIVES_R14.get(name) or
            SOL_POSITIVES_R14.get(name) or SOL_MUTANTS_R15.get(name) or
            SOL_NEGATIVES_R15.get(name) or SOL_POSITIVES_R15.get(name))
    if spec is None:
        raise KeyError(name)
    spec["apply"](c)
    return c
