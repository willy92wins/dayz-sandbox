"""Suite offline del oraculo de S3 (E9): evaluador ciego, negativas y mutantes.

Construye evidencias sinteticas que siguen el esquema documentado en
``s3_eval.py`` y comprueba que el evaluador decide solo con lecturas crudas.
Los tests ``test_e2e_*`` corren el gate entero y hoy fallan porque la
implementacion es un esqueleto.
"""

import copy
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import f03_common
import gate_core
import s3_eval
import s3_mutants
import wire

QA_DIR = Path(__file__).resolve().parents[1]
DEV_ROOT = QA_DIR.parent
REPO_TOP = DEV_ROOT.parent
FIXTURES_DIR = QA_DIR / "fixtures"


def _git(cwd, *args):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def _init_repo(root):
    dev = Path(root) / "DayZSandbox_dev"
    core = dev / "qa" / "probe" / "DayZSandbox_QA" / "scripts" / "5_Mission"
    core.mkdir(parents=True)
    (dev / "qa" / "probe" / "DayZSandbox_QA" / "config.cpp").write_bytes(b"class CfgPatches {};\n")
    (core / "DSBX_QA_Probe.c").write_bytes(b"class DSBX_QA_Probe {}\n// v1\n")
    (core / "DSBX_QA_Stamp.c").write_bytes(b'const string DSBX_QA_STAMP = "unstamped";\n')
    exp = dev / "qa" / "probe" / "DayZSandbox_QA_Expansion"
    (exp / "scripts" / "4_World").mkdir(parents=True)
    (exp / "scripts" / "4_World" / "DSBX_QA_Exp_Backend.c").write_bytes(b"class DSBX_QA_Exp_Backend {};\n")
    (exp / "scripts" / "5_Mission").mkdir(parents=True)
    (exp / "scripts" / "5_Mission" / "DSBX_QA_Exp_Stamp.c").write_bytes(
        b'const string DSBX_QA_EXP_STAMP = "unstamped";\n'
    )
    (dev / "qa" / "wire.py").write_bytes(f"WIRE_CAP = {int(wire.WIRE_CAP)}\n".encode("utf-8"))
    _git(root, "init")
    _git(root, "config", "user.email", "qa@example.invalid")
    _git(root, "config", "user.name", "QA")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "initial")
    return _git(root, "rev-parse", "HEAD").stdout.strip()


def _write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _load_fixtures():
    return {
        "actors": gate_core.read_json(FIXTURES_DIR / "s3_actors_preset.json"),
        "marks": gate_core.read_json(FIXTURES_DIR / "s3_marks.json"),
        "emotes": gate_core.read_json(FIXTURES_DIR / "s3_emotes.json"),
        "combat": gate_core.read_json(FIXTURES_DIR / "s3_combat_qa.json"),
    }


B_NCOLS = (
    "seq_n", "frame", "tick_ms", "dtsum_ms", "x_m", "y_m", "z_m",
    "wp_x_m", "wp_y_m", "wp_z_m", "dist_center_m", "max_dist_tick_m",
    "dist_mark_m", "settle_dtsum_ms", "settle_max_drift_m", "path_len_m",
    "dest_reached_n", "legs_completed_n", "buildings_near_n", "ticks_checked_n",
    "out_of_radius_ticks_n", "actor_fighting_b", "actor_raised_b",
    "actor_health", "inf_health", "inf_chase_disp_m", "combat_obs_tick_ms",
)
B_SCOLS = ("mark_state", "faction_class", "infected_id")

E_NCOLS = (
    "seq_n", "periodic_seq_n", "frame", "tick_ms", "dtsum_ms", "req_seq_n",
    "cb_inst_id", "max_cb_inst_at_req_n", "expected_emote_id", "observed_emote_id",
    "expected_cmd_id", "anim_cmd_id", "anim_state_n", "on_finish_called_b",
    "raw_p_canceled_b", "cancel_requested_b", "stance_idx", "hands_empty_b",
    "can_play_emote_b", "em_is_playing_b", "em_cb_present_b", "exp_pending_id",
    "post_cleanup_cb_count_n", "foreign_cb_events_n", "req_tick_ms", "start_tick_ms",
    "cancel_req_tick_ms", "end_tick_ms", "cleanup_tick_ms", "actor_fighting_b",
    "actor_raised_b", "actor_health", "inf_health", "inf_chase_disp_m",
    "combat_obs_tick_ms",
)
E_SCOLS = ("emote_key", "row_kind", "emote_state", "observed_end_cause", "infected_id", "faction_class")

O_NCOLS = ("x_m", "y_m", "z_m", "health_01")
O_SCOLS = ("actor_id", "real_class", "slot_name", "item_class")


def _brow(**over):
    row = {k: 0.0 for k in B_NCOLS}
    row.update({k: "" for k in B_SCOLS})
    row.update(over)
    return row


def _erow(**over):
    row = {k: 0.0 for k in E_NCOLS}
    row.update({k: "" for k in E_SCOLS})
    row["raw_p_canceled_b"] = -1.0
    row["hands_empty_b"] = 1.0
    row["can_play_emote_b"] = 1.0
    row.update(over)
    return row


def _pack_args(strs=None, nums=None, ncols=None, scols=None, rows=None):
    packed = wire.pack_payload(
        scalars_str=strs,
        scalars_num=nums,
        num_cols=ncols,
        str_cols=scols,
        row_dicts=rows,
    )
    packed["sk"] = list(packed["sk"]) + ["qa_fault"]
    packed["sv"] = list(packed["sv"]) + [wire.QA_FAULT_NONE]
    wire.validate_payload(packed)
    return packed


def _read(payload):
    out = dict(payload)
    out["has"] = ["payload"]
    return out


def _set_arg_str(args, key, value):
    sk = list(args["sk"])
    sv = list(args["sv"])
    if key in sk:
        sv[sk.index(key)] = value
    else:
        sk.append(key)
        sv.append(value)
    args["sk"] = sk
    args["sv"] = sv


def _set_arg_num(args, key, value):
    nk = list(args["nk"])
    nv = list(args["nv"])
    if key in nk:
        nv[nk.index(key)] = value
    else:
        nk.append(key)
        nv.append(value)
    args["nk"] = nk
    args["nv"] = nv


def _set_cell(payload, col, row_index, value):
    ncol = list(payload["ncol"])
    scol = list(payload["scol"])
    if col in ncol:
        idx = ncol.index(col)
        payload["ncell"][row_index * len(ncol) + idx] = value
    elif col in scol:
        idx = scol.index(col)
        payload["scell"][row_index * len(scol) + idx] = value
    else:
        raise KeyError(col)


class Case:
    """Evidencia sintetica de una parte S3, construida en memoria y serializada."""

    def __init__(self, root, head, core_stamp, exp_stamp, *, build="offline", git_dirty=False,
                 exp_pbo_sha256=None, wire_cap=None, fixtures=None):
        self.root = Path(root)
        self.head = head
        self.core_stamp = core_stamp
        self.exp_stamp = exp_stamp
        self.build_kind = build
        self.git_dirty = git_dirty
        self.exp_pbo_sha256 = exp_pbo_sha256
        self.wire_cap = int(wire.WIRE_CAP if wire_cap is None else wire_cap)
        self.fixtures = fixtures or _load_fixtures()
        self.bridge = []
        self.scenario = []
        self.ops = {}
        self.jobs = {}
        self.t = 1000.0
        self.job_t = 2000.0
        self.n = 0
        self.nonce = "0123456789abcdef"

    def _id(self):
        self.n += 1
        return f"{self.nonce}-{self.n}"

    def _t(self, step=1.0):
        self.t = round(self.t + step, 3)
        return self.t

    def _alloc(self, duration, gap=1000.0):
        start = self.job_t
        end = start + duration
        self.job_t = end + gap
        return start, end

    def add_hellos(self, probe_ver=None):
        pv = probe_ver or f"dsbx-qa1+{self.core_stamp}"
        for role in ("server", "client"):
            inst = f"{role}-inst"
            self.bridge.append(
                {
                    "args": {"build": self.build_kind, "inst": inst, "peer": role, "probe_ver": pv, "proto": "qa0"},
                    "ev": "hello",
                    "http": 200,
                    "inst": inst,
                    "ok": True,
                    "peer": role,
                    "t_ms": self._t(),
                }
            )

    def add_op(self, name, verb, args, *, status="done", reason="", payload=None):
        oid = self._id()
        self.ops[name] = {
            "id": oid,
            "verb": verb,
            "args": args,
            "status": status,
            "reason": reason,
            "payload": payload,
            "t": self._t(),
        }
        return oid

    def add_job(self, name, verb, args, rows, ncols, scols, resource, start_ms, end_ms,
                start_status="done", start_reason=""):
        oid = self._id()
        pages_n = max(1, math.ceil(len(rows) / 4)) if rows else 1
        page_ids = [self._id() for _ in range(pages_n)]
        self.jobs[name] = {
            "start_id": oid,
            "page_ids": page_ids,
            "rows": rows,
            "ncols": list(ncols),
            "scols": list(scols),
            "args": args,
            "resource": resource,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "verb": verb,
            "start_status": start_status,
            "start_reason": start_reason,
        }
        return self.jobs[name]

    def observe(self, *, adapter_ver=None, backend_available=1.0,
                backend_class="DSBX_QA_ExpansionBackend", core_start=100.0,
                adapter_reg=200.0, tick=300.0, weather_frozen=1.0, hour=10.0,
                minute=0.0, fog=0.1, overcast=0.2, rain=0.0, world_props=0.0,
                world_actors=0.0, wardrobe=None, counters=None, first_effect=-1.0,
                mutations=0.0, stage=None):
        strs = {
            "core_ver": f"dsbx-qa1+{self.core_stamp}",
            "adapter_ver": f"dsbx-qa-exp1+{self.exp_stamp}" if adapter_ver is None else adapter_ver,
            "backend_class": backend_class,
            "last_op_id": "",
            "last_op_status": "",
            "last_op_reason": "",
        }
        nums = {
            "core_loaded_b": 1.0,
            "backend_available_b": backend_available,
            "core_start_tick_ms": core_start,
            "adapter_reg_tick_ms": adapter_reg,
            "weather_frozen_b": weather_frozen,
            "world_props_n": world_props,
            "world_actors_n": world_actors,
            "hour_n": hour,
            "minute_n": minute,
            "fog": fog,
            "overcast": overcast,
            "rain": rain,
            "last_op_validate_tick_ms": 0.0,
            "last_op_cap_drop_tick_ms": 0.0,
            "last_op_revalidate_tick_ms": 0.0,
            "last_op_first_effect_tick_ms": first_effect,
            "last_op_reject_tick_ms": 0.0,
            "last_op_spawned_props_ever_n": 0.0,
            "last_op_spawned_actors_ever_n": 0.0,
            "last_op_deleted_objects_ever_n": 0.0,
            "last_op_env_writes_ever_n": 0.0,
            "total_mutations_seq_n": mutations,
            "tick_ms": tick,
            "frame": 10.0,
        }
        if counters:
            nums.update(counters)
        if stage:
            nums.update(stage)
        return wire.pack_payload(strs, nums, O_NCOLS, O_SCOLS, wardrobe or [])

    def wardrobe_rows(self):
        rows = []
        for actor in self.fixtures["actors"]["actors"]:
            for item in actor["wardrobe"]:
                rows.append(
                    {
                        "actor_id": actor["actor_id"],
                        "real_class": "eAI_" + actor["character"],
                        "slot_name": item["slot"],
                        "item_class": item["item"],
                        "x_m": float(actor["x_m"]),
                        "y_m": 0.0,
                        "z_m": float(actor["z_m"]),
                        "health_01": 1.0,
                    }
                )
        return rows

    def apply_payload(self, *, state="observado", failed="", props=2.0, actors=2.0,
                      seeded=0.0, total=0.0, cleared=0.0, available=1.0):
        strs = {"apply_state": state, "failed_item": failed}
        nums = {
            "backend_available_b": available,
            "created_props_n": props,
            "created_actors_n": actors,
            "pre_gear_seeded_n": seeded,
            "pre_sweep_total_n": total,
            "pre_gear_cleared_n": cleared,
            "tick_ms": self._t(),
            "frame": 10.0,
        }
        return wire.pack_payload(strs, nums)

    def reset_payload(self):
        nums = {
            "deleted_actors_n": 2.0,
            "deleted_props_n": 2.0,
            "deleted_infected_n": 1.0,
            "tick_ms": self._t(),
            "frame": 10.0,
        }
        return wire.pack_payload(scalars_num=nums)

    def scene_args(self, *, props=2, rows=2, seed=None, cap_mode="normal", fail_slot=None,
                   hour=None, minute=None, fog=None, overcast=None, rain=None):
        strs = {"cap_mode": cap_mode}
        nums = {"props_n": float(props)}
        if seed is not None:
            nums["seed_pre_gear_b"] = float(seed)
        if fail_slot is not None:
            strs["fail_slot"] = fail_slot
        if hour is not None:
            nums["hour_n"] = float(hour)
        if minute is not None:
            nums["minute_n"] = float(minute)
        if fog is not None:
            nums["fog"] = float(fog)
        if overcast is not None:
            nums["overcast"] = float(overcast)
        if rain is not None:
            nums["rain"] = float(rain)
        if rows:
            row_dicts = []
            for actor in self.fixtures["actors"]["actors"][:rows]:
                row_dicts.append(
                    {
                        "actor_id": actor["actor_id"],
                        "character": actor["character"],
                        "wardrobe_spec": "",
                        "x_m": float(actor["x_m"]),
                        "z_m": float(actor["z_m"]),
                    }
                )
            return _pack_args(strs, nums, ["x_m", "z_m"], ["actor_id", "character", "wardrobe_spec"], row_dicts)
        return _pack_args(strs, nums)

    # ------------------------------------------------------------------ checks

    def build_s3_00(self):
        obs = self.add_op("s3_00_observe", "act_observe", _pack_args(), payload=self.observe())
        self.scenario.append(
            {"check": "S3-00", "kind": "handshake", "phase": "S0_handshake", "observe_op_id": obs, "t_ms": self._t()}
        )

    def build_s3_01(self):
        base = self.add_op("s3_01_base", "act_observe", _pack_args(), payload=self.observe(weather_frozen=1.0))
        for case, reason in (("unknown_class", "unknown_class"), ("incompatible_slot", "incompatible_slot")):
            app = self.add_op(
                f"s3_01_apply_{case}", "act_scene_apply", self.scene_args(props=2, rows=2),
                status="rejected", reason=reason,
            )
            post = self.add_op(
                f"s3_01_post_{case}", "act_observe", _pack_args(),
                payload=self.observe(weather_frozen=1.0, world_props=0.0, world_actors=0.0),
            )
            self.scenario.append(
                {"check": "S3-01", "kind": "reject", "case": case,
                 "baseline_observe_op_id": base, "apply_op_id": app, "observe_op_id": post, "t_ms": self._t()}
            )
        part = self.add_op(
            "s3_01_partial", "act_scene_apply", self.scene_args(props=2, rows=2, fail_slot="Feet"),
            payload=self.apply_payload(state="parcial", failed="actor_1:Feet:AthleticShoes_Black"),
        )
        self.scenario.append({"check": "S3-01", "kind": "partial", "apply_op_id": part, "t_ms": self._t()})
        apply1 = self.add_op(
            "s3_01_apply1", "act_scene_apply", self.scene_args(props=2, rows=2, seed=1),
            payload=self.apply_payload(state="observado", seeded=2.0, total=4.0, cleared=4.0),
        )
        obs1 = self.add_op(
            "s3_01_obs1", "act_observe", _pack_args(),
            payload=self.observe(weather_frozen=1.0, world_props=2.0, world_actors=2.0,
                                 wardrobe=self.wardrobe_rows()),
        )
        reset = self.add_op("s3_01_reset", "act_reset", _pack_args(), payload=self.reset_payload())
        apply2 = self.add_op(
            "s3_01_apply2", "act_scene_apply", self.scene_args(props=2, rows=2, seed=1),
            payload=self.apply_payload(state="observado", seeded=2.0, total=4.0, cleared=4.0),
        )
        obs2 = self.add_op(
            "s3_01_obs2", "act_observe", _pack_args(),
            payload=self.observe(weather_frozen=1.0, world_props=2.0, world_actors=2.0,
                                 wardrobe=self.wardrobe_rows()),
        )
        self.scenario.append(
            {"check": "S3-01", "kind": "positive", "apply1_op_id": apply1, "observe1_op_id": obs1,
             "reset_op_id": reset, "apply2_op_id": apply2, "observe2_op_id": obs2, "t_ms": self._t()}
        )

    def build_s3_02(self):
        start, end = self._alloc(5000)
        args = _pack_args(
            {"mode": "ONCE", "threat_case": "none", "actor_id": "actor_1"},
            {"reach_timeout_ms": 30000.0, "settle_window_ms": 10000.0, "sample_step_ms": 500.0},
        )
        rows = [
            _brow(seq_n=1, frame=1, tick_ms=start + 500, dtsum_ms=500, x_m=4520.0, z_m=10320.0,
                  wp_x_m=4540.0, wp_z_m=10320.0, dist_mark_m=20.0, mark_state="en_ruta"),
            _brow(seq_n=2, frame=2, tick_ms=start + 1000, dtsum_ms=1500, x_m=4535.0, z_m=10320.0,
                  wp_x_m=4540.0, wp_z_m=10320.0, dist_mark_m=5.0, mark_state="en_ruta"),
            _brow(seq_n=3, frame=3, tick_ms=start + 2000, dtsum_ms=2500, x_m=4539.2, z_m=10320.0,
                  wp_x_m=4540.0, wp_z_m=10320.0, dist_mark_m=0.8, mark_state="en_marca"),
            _brow(seq_n=4, frame=4, tick_ms=start + 4000, dtsum_ms=4500, x_m=4539.2, z_m=10320.0,
                  wp_x_m=4540.0, wp_z_m=10320.0, dist_mark_m=0.8, mark_state="en_marca",
                  settle_dtsum_ms=10000.0, settle_max_drift_m=0.0),
        ]
        job = self.add_job("s3_02_once", "act_behaviour_run", args, rows, B_NCOLS, B_SCOLS,
                           "actor:actor_1", start, end)
        self.scenario.append(
            {"check": "S3-02", "kind": "once_reachable", "actor_id": "actor_1",
             "start_op_id": job["start_id"], "page_op_ids": job["page_ids"], "t_ms": self._t()}
        )

    def build_s3_03(self):
        start, end = self._alloc(12000)
        args = _pack_args(
            {"mode": "HOLD", "actor_id": "actor_1"},
            {"duration_ms": 10000.0, "sample_step_ms": 500.0},
        )
        rows = [
            _brow(seq_n=1, tick_ms=start + 5000, dtsum_ms=5000, x_m=4520.0, z_m=10320.0, max_dist_tick_m=0.0),
            _brow(seq_n=2, tick_ms=start + 8000, dtsum_ms=8000, x_m=4520.0, z_m=10320.0, max_dist_tick_m=0.0),
            _brow(seq_n=3, tick_ms=start + 10000, dtsum_ms=10000, x_m=4520.0, z_m=10320.0, max_dist_tick_m=0.0),
        ]
        hold = self.add_job("s3_03_hold", "act_behaviour_run", args, rows, B_NCOLS, B_SCOLS,
                            "actor:actor_1", start, end)
        start2, end2 = self._alloc(65000)
        args2 = _pack_args(
            {"mode": "LOOP", "actor_id": "actor_1"},
            {"duration_ms": 60000.0, "sample_step_ms": 500.0},
        )
        rows2 = [
            _brow(seq_n=1, tick_ms=start2 + 20000, dtsum_ms=20000, legs_completed_n=1.0, path_len_m=10.0),
            _brow(seq_n=2, tick_ms=start2 + 40000, dtsum_ms=40000, legs_completed_n=2.0, path_len_m=20.0),
            _brow(seq_n=3, tick_ms=start2 + 55000, dtsum_ms=55000, legs_completed_n=3.0, path_len_m=25.0),
            _brow(seq_n=4, tick_ms=start2 + 60000, dtsum_ms=60000, legs_completed_n=4.0, path_len_m=35.0),
        ]
        loop = self.add_job("s3_03_loop", "act_behaviour_run", args2, rows2, B_NCOLS, B_SCOLS,
                            "actor:actor_1", start2, end2)
        self.scenario.append({"check": "S3-03", "kind": "hold", "actor_id": "actor_1",
                              "start_op_id": hold["start_id"], "page_op_ids": hold["page_ids"], "t_ms": self._t()})
        self.scenario.append({"check": "S3-03", "kind": "loop", "actor_id": "actor_1",
                              "start_op_id": loop["start_id"], "page_op_ids": loop["page_ids"], "t_ms": self._t()})

    def build_s3_04(self):
        for entry in self.fixtures["emotes"]["catalog"]:
            key = entry["emote_key"]
            eid = float(entry["emote_id"])
            cid = float(entry["cmd_id"])
            start, end = self._alloc(4000)
            args = _pack_args(
                {"emote_key": key, "test_case": "normal", "actor_id": "actor_1"},
                {"start_timeout_ms": 5000.0, "finish_timeout_ms": 15000.0, "sample_step_ms": 250.0},
            )
            req = start + 100
            rows = [
                _erow(seq_n=1, req_seq_n=1.0, tick_ms=req, req_tick_ms=req,
                      expected_emote_id=eid, expected_cmd_id=cid, max_cb_inst_at_req_n=10.0,
                      emote_key=key, row_kind="event", emote_state="pedido", observed_end_cause=""),
                _erow(seq_n=2, req_seq_n=1.0, tick_ms=req + 500, req_tick_ms=req,
                      start_tick_ms=req + 500, expected_emote_id=eid, expected_cmd_id=cid,
                      cb_inst_id=11.0, max_cb_inst_at_req_n=10.0, observed_emote_id=eid,
                      anim_cmd_id=cid, anim_state_n=7.0, can_play_emote_b=0.0,
                      emote_key=key, row_kind="event", emote_state="en_curso", observed_end_cause=""),
                _erow(seq_n=3, req_seq_n=1.0, tick_ms=req + 3500, req_tick_ms=req,
                      start_tick_ms=req + 500, end_tick_ms=req + 3500, expected_emote_id=eid,
                      expected_cmd_id=cid, cb_inst_id=11.0, max_cb_inst_at_req_n=10.0,
                      observed_emote_id=eid, anim_cmd_id=cid, anim_state_n=7.0,
                      on_finish_called_b=1.0, raw_p_canceled_b=0.0, exp_pending_id=0.0,
                      emote_key=key, row_kind="event", emote_state="terminado",
                      observed_end_cause="cb_normal"),
            ]
            job = self.add_job(f"s3_04_{key}", "act_emote_run", args, rows, E_NCOLS, E_SCOLS,
                               "actor:actor_1", start, end)
            self.scenario.append({"check": "S3-04", "kind": "emote", "emote_key": key,
                                  "actor_id": "actor_1", "start_op_id": job["start_id"],
                                  "page_op_ids": job["page_ids"], "t_ms": self._t()})

    def build_s3_05(self):
        start = self.job_t
        end = start + 600000
        self.job_t = end + 1000
        for name, actor, cx, cz, buildings, offsets in (
            ("urban", "actor_1", 4600.0, 10300.0, 5.0, ((0.0, 0.0), (4.0, 0.0), (8.0, 1.0), (12.0, 2.0))),
            ("open", "actor_2", 4400.0, 9800.0, 1.0, ((0.0, 0.0), (3.0, 0.0), (6.0, 2.0), (9.0, -1.0))),
        ):
            args = _pack_args(
                {"mode": "ROAM", "actor_id": actor},
                {"radius_m": 15.0, "duration_ms": 600000.0, "sample_step_ms": 5000.0},
            )
            pts = [(cx + dx, cz + dz) for dx, dz in offsets]
            rows = []
            for i, (x, z) in enumerate(pts):
                dc = math.hypot(x - cx, z - cz)
                rows.append(
                    _brow(seq_n=float(i + 1), frame=float(i + 1), tick_ms=start + 200000 * i,
                          dtsum_ms=200000 * i, x_m=x, z_m=z, dist_center_m=dc,
                          max_dist_tick_m=dc, path_len_m=14.0 * i, dest_reached_n=float(i),
                          buildings_near_n=buildings, ticks_checked_n=1000.0,
                          out_of_radius_ticks_n=0.0)
                )
            rows[-1]["dest_reached_n"] = 4.0
            job = self.add_job(f"s3_05_{name}", "act_behaviour_run", args, rows, B_NCOLS, B_SCOLS,
                               f"actor:{actor}", start, end)
            self.scenario.append({"check": "S3-05", "kind": f"roam_{name}", "actor_id": actor,
                                  "start_op_id": job["start_id"], "page_op_ids": job["page_ids"],
                                  "t_ms": self._t()})

    def build_s3_06(self):
        for name, actor, threat, state in (
            ("unreachable", "actor_2", "none", "no_alcanzada"),
            ("require_threat", "actor_2", "require_threat", "no_alcanzada"),
        ):
            start, end = self._alloc(15000)
            args = _pack_args(
                {"mode": "ONCE", "threat_case": threat, "actor_id": actor},
                {"reach_timeout_ms": 15000.0, "sample_step_ms": 500.0},
            )
            combat = {}
            if threat == "require_threat":
                combat = {
                    "faction_class": "eAIFactionRaiders",
                    "infected_id": "inf_1",
                    "inf_health": 80.0,
                    "actor_health": 100.0,
                    "actor_fighting_b": 1.0,
                    "inf_chase_disp_m": 0.0,
                    "combat_obs_tick_ms": start + 500,
                }
            rows = [
                _brow(seq_n=1, tick_ms=start + 500, dtsum_ms=500, dist_mark_m=20.0,
                      mark_state="en_ruta", **combat),
                _brow(seq_n=2, tick_ms=start + 14000, dtsum_ms=14000, dist_mark_m=19.0,
                      mark_state=state, **combat),
            ]
            job = self.add_job(f"s3_06_{name}", "act_behaviour_run", args, rows, B_NCOLS, B_SCOLS,
                               f"actor:{actor}", start, end)
            self.scenario.append({"check": "S3-06", "kind": name, "actor_id": actor,
                                  "start_op_id": job["start_id"], "page_op_ids": job["page_ids"],
                                  "t_ms": self._t()})

    def build_s3_07(self):
        start, end = self._alloc(10000)
        args = _pack_args(
            {"test_case": "require_combat", "actor_id": "actor_2"},
            {"combat_wait_ms": 5000.0, "start_timeout_ms": 5000.0, "sample_step_ms": 250.0},
        )
        rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=start + 1000, req_tick_ms=start + 1000,
                  combat_obs_tick_ms=start + 1000, infected_id="inf_1", inf_health=80.0,
                  actor_health=100.0, faction_class="eAIFactionRaiders", actor_fighting_b=1.0,
                  inf_chase_disp_m=0.0, emote_state="rechazado", raw_p_canceled_b=-1.0,
                  expected_emote_id=58.0, expected_cmd_id=1109.0),
        ]
        job = self.add_job("s3_07_combat", "act_emote_run", args, rows, E_NCOLS, E_SCOLS,
                           "actor:actor_2", start, end)
        self.scenario.append({"check": "S3-07", "kind": "require_combat", "actor_id": "actor_2",
                              "start_op_id": job["start_id"], "page_op_ids": job["page_ids"],
                              "t_ms": self._t()})

    def build_s3_08_09(self, want_08=True, want_09=True):
        unknown = self.add_op("s3_unknown", "act_emote_run",
                              _pack_args({"emote_key": "unknown_test_emote", "test_case": "normal",
                                          "actor_id": "actor_1"}), status="rejected", reason="unknown_emote")
        if want_08:
            self.scenario.append({"check": "S3-08", "kind": "unknown_emote", "op_id": unknown, "t_ms": self._t()})

        # cancel_before_start
        start, end = self._alloc(1000)
        cancel = start + 1000
        args = _pack_args({"emote_key": "nod", "test_case": "cancel_before_start", "actor_id": "actor_1"},
                          {"start_timeout_ms": 5000.0, "sample_step_ms": 250.0, "post_watch_ms": 3000.0})
        main_rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=start + 500, req_tick_ms=start + 500,
                  can_play_emote_b=0.0, exp_pending_id=58.0, emote_key="nod",
                  row_kind="event", emote_state="pedido", observed_end_cause=""),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=cancel, req_tick_ms=start + 500,
                  cancel_req_tick_ms=cancel, cleanup_tick_ms=cancel, exp_pending_id=0.0,
                  emote_key="nod", row_kind="event", emote_state="cancelado", observed_end_cause=""),
        ]
        before = self.add_job("s3_cancel_before", "act_emote_run", args, main_rows, E_NCOLS, E_SCOLS,
                              "actor:actor_1", start, end)
        pstart, pend = self._alloc(3000)
        post_args = _pack_args({"emote_key": "nod", "test_case": "post_stop_watch", "actor_id": "actor_1"},
                               {"sample_step_ms": 250.0, "post_watch_ms": 3000.0})
        post_rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=pstart + 1500, req_tick_ms=start + 500,
                  cancel_req_tick_ms=cancel, cleanup_tick_ms=cancel, exp_pending_id=0.0,
                  emote_key="nod", row_kind="periodic", emote_state="cancelado", observed_end_cause=""),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=pstart + 3000, req_tick_ms=start + 500,
                  cancel_req_tick_ms=cancel, cleanup_tick_ms=cancel, exp_pending_id=0.0,
                  emote_key="nod", row_kind="periodic", emote_state="cancelado", observed_end_cause=""),
        ]
        post_before = self.add_job("s3_post_before", "act_emote_run", post_args, post_rows, E_NCOLS, E_SCOLS,
                                   "actor:actor_1", pstart, pend)
        for check in (("S3-08", want_08), ("S3-09", want_09)):
            if check[1]:
                self.scenario.append({"check": check[0], "kind": "cancel_before_start", "actor_id": "actor_1",
                                      "start_op_id": before["start_id"], "page_op_ids": before["page_ids"],
                                      "stop_op_id": "stop-before",
                                      "post_watch_start_op_id": post_before["start_id"],
                                      "post_watch_page_op_ids": post_before["page_ids"], "t_ms": self._t()})

        # cancel_after_start
        start, end = self._alloc(2800)
        cancel = start + 2000
        cleanup = start + 2800
        args = _pack_args({"emote_key": "nod", "test_case": "cancel_after_start", "actor_id": "actor_1"},
                          {"start_timeout_ms": 5000.0, "sample_step_ms": 250.0, "post_watch_ms": 3000.0})
        main_rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=start + 500, req_tick_ms=start + 500,
                  exp_pending_id=58.0, emote_key="nod", row_kind="event", emote_state="pedido"),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=start + 1000, req_tick_ms=start + 500,
                  start_tick_ms=start + 1000, cb_inst_id=6.0, max_cb_inst_at_req_n=5.0,
                  expected_emote_id=58.0, observed_emote_id=58.0, expected_cmd_id=1109.0,
                  anim_cmd_id=1109.0, anim_state_n=7.0, can_play_emote_b=0.0,
                  em_is_playing_b=1.0, em_cb_present_b=1.0, exp_pending_id=58.0,
                  emote_key="nod", row_kind="event", emote_state="en_curso"),
            _erow(seq_n=3, req_seq_n=1.0, tick_ms=cancel, req_tick_ms=start + 500,
                  start_tick_ms=start + 1000, cancel_req_tick_ms=cancel, cb_inst_id=6.0,
                  max_cb_inst_at_req_n=5.0, expected_emote_id=58.0, observed_emote_id=58.0,
                  expected_cmd_id=1109.0, anim_cmd_id=1109.0, anim_state_n=7.0,
                  can_play_emote_b=0.0, em_is_playing_b=1.0, em_cb_present_b=1.0,
                  exp_pending_id=58.0, emote_key="nod", row_kind="event", emote_state="cancelado"),
            _erow(seq_n=4, req_seq_n=1.0, tick_ms=start + 2500, req_tick_ms=start + 500,
                  start_tick_ms=start + 1000, cancel_req_tick_ms=cancel, end_tick_ms=start + 2500,
                  cb_inst_id=6.0, max_cb_inst_at_req_n=5.0, expected_emote_id=58.0,
                  observed_emote_id=58.0, expected_cmd_id=1109.0, anim_cmd_id=1109.0,
                  anim_state_n=7.0, on_finish_called_b=1.0, raw_p_canceled_b=1.0,
                  can_play_emote_b=0.0, em_is_playing_b=1.0, em_cb_present_b=1.0,
                  exp_pending_id=58.0, emote_key="nod", row_kind="event",
                  emote_state="cancelado", observed_end_cause="cb_canceled"),
            _erow(seq_n=5, req_seq_n=1.0, tick_ms=cleanup, req_tick_ms=start + 500,
                  start_tick_ms=start + 1000, cancel_req_tick_ms=cancel, cleanup_tick_ms=cleanup,
                  end_tick_ms=start + 2500, cb_inst_id=6.0, max_cb_inst_at_req_n=5.0,
                  expected_emote_id=58.0, observed_emote_id=58.0, expected_cmd_id=1109.0,
                  anim_cmd_id=1109.0, anim_state_n=7.0, on_finish_called_b=1.0,
                  raw_p_canceled_b=1.0, emote_key="nod", row_kind="event",
                  emote_state="cancelado", observed_end_cause="cb_canceled"),
        ]
        after = self.add_job("s3_cancel_after", "act_emote_run", args, main_rows, E_NCOLS, E_SCOLS,
                             "actor:actor_1", start, end)
        pstart, pend = self._alloc(3000)
        post_args = _pack_args({"emote_key": "nod", "test_case": "post_stop_watch", "actor_id": "actor_1"},
                               {"sample_step_ms": 250.0, "post_watch_ms": 3000.0})
        post_rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=pstart + 1500, req_tick_ms=start + 500,
                  start_tick_ms=start + 1000, cancel_req_tick_ms=cancel, cleanup_tick_ms=cleanup,
                  end_tick_ms=start + 2500, cb_inst_id=6.0, max_cb_inst_at_req_n=5.0,
                  expected_emote_id=58.0, observed_emote_id=58.0, expected_cmd_id=1109.0,
                  anim_cmd_id=1109.0, anim_state_n=7.0, on_finish_called_b=1.0,
                  raw_p_canceled_b=1.0, emote_key="nod", row_kind="periodic",
                  emote_state="cancelado", observed_end_cause="cb_canceled"),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=pstart + 3000, req_tick_ms=start + 500,
                  start_tick_ms=start + 1000, cancel_req_tick_ms=cancel, cleanup_tick_ms=cleanup,
                  end_tick_ms=start + 2500, cb_inst_id=6.0, max_cb_inst_at_req_n=5.0,
                  expected_emote_id=58.0, observed_emote_id=58.0, expected_cmd_id=1109.0,
                  anim_cmd_id=1109.0, anim_state_n=7.0, on_finish_called_b=1.0,
                  raw_p_canceled_b=1.0, emote_key="nod", row_kind="periodic",
                  emote_state="cancelado", observed_end_cause="cb_canceled"),
        ]
        post_after = self.add_job("s3_post_after", "act_emote_run", post_args, post_rows, E_NCOLS, E_SCOLS,
                                  "actor:actor_1", pstart, pend)
        for check in (("S3-08", want_08), ("S3-09", want_09)):
            if check[1]:
                self.scenario.append({"check": check[0], "kind": "cancel_after_start", "actor_id": "actor_1",
                                      "start_op_id": after["start_id"], "page_op_ids": after["page_ids"],
                                      "stop_op_id": "stop-after",
                                      "post_watch_start_op_id": post_after["start_id"],
                                      "post_watch_page_op_ids": post_after["page_ids"], "t_ms": self._t()})

        # interrupt_between_samples
        start, end = self._alloc(1500)
        args = _pack_args({"emote_key": "nod", "test_case": "interrupt_between_samples", "actor_id": "actor_1"},
                          {"sample_step_ms": 500.0, "post_watch_ms": 3000.0})
        rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=start + 100, req_tick_ms=start + 100,
                  periodic_seq_n=1.0, row_kind="periodic", emote_state="pedido",
                  expected_emote_id=58.0, expected_cmd_id=1109.0, exp_pending_id=58.0),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=start + 200, req_tick_ms=start + 100,
                  start_tick_ms=start + 200, cb_inst_id=6.0, max_cb_inst_at_req_n=5.0,
                  expected_emote_id=58.0, observed_emote_id=58.0, expected_cmd_id=1109.0,
                  anim_cmd_id=1109.0, anim_state_n=7.0, can_play_emote_b=0.0,
                  em_is_playing_b=1.0, em_cb_present_b=1.0, exp_pending_id=58.0,
                  row_kind="event", emote_state="en_curso"),
            _erow(seq_n=3, req_seq_n=1.0, tick_ms=start + 300, req_tick_ms=start + 100,
                  start_tick_ms=start + 200, cancel_req_tick_ms=start + 300, cb_inst_id=6.0,
                  max_cb_inst_at_req_n=5.0, expected_emote_id=58.0, observed_emote_id=58.0,
                  expected_cmd_id=1109.0, anim_cmd_id=1109.0, anim_state_n=7.0,
                  can_play_emote_b=0.0, em_is_playing_b=1.0, em_cb_present_b=1.0,
                  exp_pending_id=58.0, row_kind="event", emote_state="cancelado"),
            _erow(seq_n=4, req_seq_n=1.0, tick_ms=start + 400, req_tick_ms=start + 100,
                  start_tick_ms=start + 200, cancel_req_tick_ms=start + 300,
                  end_tick_ms=start + 400, cb_inst_id=6.0, max_cb_inst_at_req_n=5.0,
                  expected_emote_id=58.0, observed_emote_id=58.0, expected_cmd_id=1109.0,
                  anim_cmd_id=1109.0, anim_state_n=7.0, on_finish_called_b=1.0,
                  raw_p_canceled_b=1.0, can_play_emote_b=0.0, em_is_playing_b=1.0,
                  em_cb_present_b=1.0, exp_pending_id=58.0, row_kind="event",
                  emote_state="cancelado", observed_end_cause="cb_canceled"),
            _erow(seq_n=5, req_seq_n=1.0, tick_ms=start + 500, req_tick_ms=start + 100,
                  periodic_seq_n=2.0, row_kind="periodic", emote_state="cancelado",
                  expected_emote_id=58.0, expected_cmd_id=1109.0, exp_pending_id=58.0),
        ]
        interrupt = self.add_job("s3_interrupt", "act_emote_run", args, rows, E_NCOLS, E_SCOLS,
                                 "actor:actor_1", start, end)
        if want_08:
            self.scenario.append({"check": "S3-08", "kind": "interrupt_between_samples", "actor_id": "actor_1",
                                  "start_op_id": interrupt["start_id"], "page_op_ids": interrupt["page_ids"],
                                  "stop_op_id": "stop-interrupt", "t_ms": self._t()})

        # never_starts
        start, end = self._alloc(5100)
        cancel = start + 5100
        args = _pack_args({"emote_key": "nod", "test_case": "never_starts", "actor_id": "actor_1"},
                          {"start_timeout_ms": 5000.0, "sample_step_ms": 250.0, "post_watch_ms": 3000.0})
        main_rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=start + 100, req_tick_ms=start + 100,
                  can_play_emote_b=0.0, exp_pending_id=58.0, row_kind="event",
                  emote_state="pedido", expected_emote_id=58.0, expected_cmd_id=1109.0),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=cancel, req_tick_ms=start + 100,
                  cancel_req_tick_ms=cancel, cleanup_tick_ms=cancel, exp_pending_id=0.0,
                  row_kind="event", emote_state="agotado", expected_emote_id=58.0,
                  expected_cmd_id=1109.0),
        ]
        never = self.add_job("s3_never", "act_emote_run", args, main_rows, E_NCOLS, E_SCOLS,
                             "actor:actor_1", start, end)
        pstart, pend = self._alloc(3000)
        post_args = _pack_args({"emote_key": "nod", "test_case": "post_stop_watch", "actor_id": "actor_1"},
                               {"sample_step_ms": 250.0, "post_watch_ms": 3000.0})
        post_rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=pstart + 1500, req_tick_ms=start + 100,
                  cancel_req_tick_ms=cancel, cleanup_tick_ms=cancel, exp_pending_id=0.0,
                  row_kind="periodic", emote_state="agotado", expected_emote_id=58.0,
                  expected_cmd_id=1109.0),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=pstart + 3000, req_tick_ms=start + 100,
                  cancel_req_tick_ms=cancel, cleanup_tick_ms=cancel, exp_pending_id=0.0,
                  row_kind="periodic", emote_state="agotado", expected_emote_id=58.0,
                  expected_cmd_id=1109.0),
        ]
        post_never = self.add_job("s3_post_never", "act_emote_run", post_args, post_rows, E_NCOLS, E_SCOLS,
                                  "actor:actor_1", pstart, pend)
        for check in (("S3-08", want_08), ("S3-09", want_09)):
            if check[1]:
                self.scenario.append({"check": check[0], "kind": "never_starts", "actor_id": "actor_1",
                                      "start_op_id": never["start_id"], "page_op_ids": never["page_ids"],
                                      "stop_op_id": "stop-never",
                                      "post_watch_start_op_id": post_never["start_id"],
                                      "post_watch_page_op_ids": post_never["page_ids"], "t_ms": self._t()})

        # stale_callback_isolation
        start, end = self._alloc(2500)
        args = _pack_args({"emote_key": "nod", "test_case": "stale_callback_isolation", "actor_id": "actor_1"},
                          {"sample_step_ms": 250.0, "post_watch_ms": 3000.0})
        rows = [
            _erow(seq_n=1, req_seq_n=1.0, tick_ms=start + 100, req_tick_ms=start + 100,
                  foreign_cb_events_n=1.0, exp_pending_id=58.0, row_kind="event",
                  emote_state="pedido", expected_emote_id=58.0, expected_cmd_id=1109.0),
            _erow(seq_n=2, req_seq_n=1.0, tick_ms=start + 1000, req_tick_ms=start + 100,
                  foreign_cb_events_n=1.0, cb_inst_id=5.0, max_cb_inst_at_req_n=5.0,
                  exp_pending_id=58.0, row_kind="event", emote_state="pedido",
                  expected_emote_id=58.0, expected_cmd_id=1109.0),
            _erow(seq_n=3, req_seq_n=1.0, tick_ms=start + 2000, req_tick_ms=start + 100,
                  foreign_cb_events_n=1.0, cancel_req_tick_ms=start + 2000,
                  cleanup_tick_ms=start + 2000, exp_pending_id=0.0, row_kind="event",
                  emote_state="cancelado", expected_emote_id=58.0, expected_cmd_id=1109.0),
        ]
        stale = self.add_job("s3_stale", "act_emote_run", args, rows, E_NCOLS, E_SCOLS,
                             "actor:actor_1", start, end)
        if want_08:
            self.scenario.append({"check": "S3-08", "kind": "stale_callback_isolation", "actor_id": "actor_1",
                                  "start_op_id": stale["start_id"], "page_op_ids": stale["page_ids"],
                                  "stop_op_id": "stop-stale", "t_ms": self._t()})

    def build_s3_11(self):
        obs = self.add_op("s3_11_obs", "act_observe", _pack_args(),
                          payload=self.observe(backend_available=0.0, adapter_ver=""))
        app = self.add_op("s3_11_apply", "act_scene_apply",
                          self.scene_args(props=2, rows=0, cap_mode="no_expansion"),
                          payload=self.apply_payload(props=2.0, actors=0.0))
        post = self.add_op("s3_11_post", "act_observe", _pack_args(), payload=self.observe(world_props=2.0))
        self.scenario.append({"check": "S3-11", "kind": "observe_no_expansion", "observe_op_id": obs, "t_ms": self._t()})
        self.scenario.append({"check": "S3-11", "kind": "apply_props_only", "apply_op_id": app,
                              "observe_op_id": post, "t_ms": self._t()})

    def build_s3_12(self):
        for kind, cap_mode, stage in (
            ("capability_lost", "drop_after_validate",
             {"last_op_validate_tick_ms": 1000.0, "last_op_cap_drop_tick_ms": 1010.0,
              "last_op_revalidate_tick_ms": 1020.0, "last_op_reject_tick_ms": 1030.0}),
            ("no_expansion", "no_expansion", None),
        ):
            base = self.add_op(f"s3_12_base_{kind}", "act_observe", _pack_args(),
                               payload=self.observe(weather_frozen=1.0, mutations=5.0))
            app = self.add_op(f"s3_12_apply_{kind}", "act_scene_apply",
                              self.scene_args(props=2, rows=2, cap_mode=cap_mode),
                              status="rejected", reason="expansion_unavailable")
            post = self.add_op(f"s3_12_post_{kind}", "act_observe", _pack_args(),
                               payload=self.observe(weather_frozen=1.0, world_props=0.0,
                                                    world_actors=0.0, first_effect=-1.0,
                                                    mutations=5.0, stage=stage))
            self.scenario.append({"check": "S3-12", "kind": kind,
                                  "baseline_observe_op_id": base, "apply_op_id": app,
                                  "post_observe_op_id": post, "t_ms": self._t()})

    def build(self, checks=None):
        self.add_hellos()
        wanted = set(s3_eval.CHECK_IDS if checks is None else checks)
        if "S3-00" in wanted:
            self.build_s3_00()
        if "S3-01" in wanted:
            self.build_s3_01()
        if "S3-02" in wanted:
            self.build_s3_02()
        if "S3-03" in wanted:
            self.build_s3_03()
        if "S3-04" in wanted:
            self.build_s3_04()
        if "S3-05" in wanted:
            self.build_s3_05()
        if "S3-06" in wanted:
            self.build_s3_06()
        if "S3-07" in wanted:
            self.build_s3_07()
        if "S3-08" in wanted or "S3-09" in wanted:
            self.build_s3_08_09("S3-08" in wanted, "S3-09" in wanted)
        if "S3-11" in wanted:
            self.build_s3_11()
        if "S3-12" in wanted:
            self.build_s3_12()
        return self

    def write(self, part_dir):
        pdir = Path(part_dir)
        samples = pdir / "samples"
        samples.mkdir(parents=True, exist_ok=True)
        bridge = list(self.bridge)
        for spec in self.ops.values():
            oid = spec["id"]
            bridge.append({"ev": "enq", "op_id": oid, "peer": "server", "verb": spec["verb"],
                           "args": spec["args"], "t_ms": spec["t"]})
            read = _read(spec["payload"]) if spec["status"] == "done" and spec["payload"] is not None else {"has": []}
            bridge.append({"ev": "result", "http": 200, "op_id": oid, "peer": "server",
                           "t_ms": spec["t"] + 0.5,
                           "result": {"status": spec["status"], "reason": spec["reason"], "read": read}})
        for spec in self.jobs.values():
            oid = spec["start_id"]
            rows = spec["rows"]
            ncols = spec["ncols"]
            scols = spec["scols"]
            start = spec["start_ms"]
            end = spec["end_ms"]
            start_payload = wire.pack_payload(
                scalars_str={"resource": spec["resource"], "state": "running"},
                scalars_num={"start_tick_ms": start, "end_tick_ms": end},
            )
            bridge.append({"ev": "enq", "op_id": oid, "peer": "server", "verb": spec["verb"],
                           "args": spec["args"], "t_ms": start})
            bridge.append({"ev": "result", "http": 200, "op_id": oid, "peer": "server",
                           "t_ms": start + 0.5,
                           "result": {"status": spec.get("start_status", "done"),
                                      "reason": spec.get("start_reason", ""),
                                      "read": _read(start_payload)}})
            pages_n = max(1, math.ceil(len(rows) / 4)) if rows else 1
            for pno, pid in enumerate(spec["page_ids"]):
                chunk = rows[pno * 4:(pno + 1) * 4]
                pp = wire.pack_payload(
                    scalars_str={"state": "done"},
                    scalars_num={"rows_total_n": len(rows), "pages_n": pages_n,
                                 "start_tick_ms": start, "end_tick_ms": end},
                    num_cols=ncols,
                    str_cols=scols,
                    row_dicts=chunk,
                )
                bridge.append({"ev": "enq", "op_id": pid, "peer": "server", "verb": "job_read",
                               "args": _pack_args({"job": oid}, {"page_n": pno}), "t_ms": end})
                bridge.append({"ev": "result", "http": 200, "op_id": pid, "peer": "server",
                               "t_ms": end + 0.5,
                               "result": {"status": "done", "reason": "", "read": _read(pp)}})
        _write_jsonl(samples / "bridge.jsonl", bridge)
        _write_jsonl(samples / "scenario.jsonl", self.scenario)
        gate_core.write_json(pdir / "part.json",
                             {"op_map": [], "op_nonce": self.nonce, "part": pdir.name, "spike_id": "S3"})
        gate_core.write_json(pdir / "manifest.json", self.manifest())

    def manifest(self):
        ident_params = {
            "hold_ms": 2000,
            "lease_ms": 3000,
            "retry_ms": 2000,
            "seed": 20261026,
            "ttl_ms": 5000,
            "wire_cap": self.wire_cap,
            "exp_probe_stamp": self.exp_stamp,
            "exp_pbo_sha256": self.exp_pbo_sha256,
        }
        return {
            "argv": [],
            "both": True,
            "build": self.build_kind,
            "ended_utc": "2026-11-15T00:00:10Z",
            "execution_identity": {
                "fake_peer_pids": {"client": 2, "server": 1},
                "key_sha256": {"client": "b" * 16, "server": "a" * 16},
                "peer_insts": {"client": ["client-inst"], "server": ["server-inst"]},
                "port": 9,
            },
            "faults": [],
            "harness": {"git_dirty": self.git_dirty, "git_head": self.head,
                        "platform": "test", "python": "3.14"},
            "id": "S3",
            "identity": {
                "build": self.build_kind,
                "git_dirty": self.git_dirty,
                "git_head": self.head,
                "params": ident_params,
                "pbo_sha256": None,
                "peer_builds": {"client": self.build_kind, "server": self.build_kind},
                "probe_stamp": self.core_stamp,
            },
            "kind": "spike",
            "params": {"hold_ms": 2000, "lease_ms": 3000, "port": 9, "retry_ms": 2000,
                       "run_id": "abcd1234", "seed": 20261026, "ttl_ms": 5000},
            "schema": gate_core.SCHEMA_MANIFEST,
            "started_utc": "2026-11-15T00:00:00Z",
        }


def _make_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    head = _init_repo(root)
    core_stamp = f03_common.compute_probe_stamp_at_commit(head, repo_root=root)
    exp_stamp = s3_eval.compute_exp_stamp_at_commit(head, repo_root=root)
    return root, head, core_stamp, exp_stamp


def _new_case(root, head, core_stamp, exp_stamp, **kwargs):
    return Case(root, head, core_stamp, exp_stamp, **kwargs)


def _eval_case(case, root, part_name="part"):
    part = Path(root).parent / part_name
    case.write(part)
    return s3_eval.evaluate(part, repo_root=root)


def _check(verdict, cid):
    return next(c for c in verdict["checks"] if c["id"] == cid)


def _set_scalar_num(payload, key, value):
    nk = list(payload["nk"])
    nv = list(payload["nv"])
    if key in nk:
        nv[nk.index(key)] = value
    else:
        nk.append(key)
        nv.append(value)
    payload["nk"] = nk
    payload["nv"] = nv


def _set_scalar_str(payload, key, value):
    sk = list(payload["sk"])
    sv = list(payload["sv"])
    if key in sk:
        sv[sk.index(key)] = value
    else:
        sk.append(key)
        sv.append(value)
    payload["sk"] = sk
    payload["sv"] = sv


def _row(payload, col, row_index, value):
    _set_cell(payload, col, row_index, value)


def _bad_fixtures(tmpdir, *, emote_key="nod", emote_id=7):
    dst = Path(tmpdir) / "fixtures"
    shutil.copytree(FIXTURES_DIR, dst)
    emotes = gate_core.read_json(dst / "s3_emotes.json")
    for entry in emotes["catalog"]:
        if entry["emote_key"] == emote_key:
            entry["emote_id"] = emote_id
    gate_core.write_json(dst / "s3_emotes.json", emotes)
    return dst


class S3EvidenceTestBase(unittest.TestCase):
    """Repositorio git sintetico y evaluacion de una parte construida en memoria."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root, self.head, self.core, self.exp = _make_repo(self._tmp.name)

    def case(self, **kwargs):
        return _new_case(self.root, self.head, self.core, self.exp, **kwargs)

    def evaluate(self, case, part_name="part", fixtures_dir=None):
        part = Path(self.root).parent / part_name
        case.write(part)
        return s3_eval.evaluate(part, repo_root=self.root, fixtures_dir=fixtures_dir)

    def assert_not_pass(self, verdict, cid, statuses=("fail",)):
        chk = _check(verdict, cid)
        self.assertIn(chk["status"], statuses, chk)
        self.assertNotEqual(verdict["exit_code"], 0, verdict)
        return chk


class S3HealthyRunTests(unittest.TestCase):
    def test_healthy_full_run_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, head, core, exp = _make_repo(tmp)
            case = _new_case(root, head, core, exp)
            case.build()
            verdict = _eval_case(case, root, "run")
            self.assertEqual(verdict["exit_code"], 0, verdict)
            self.assertEqual(verdict["verdict"], "PASA")
            for c in verdict["checks"]:
                self.assertEqual(c["status"], "pass", c)
            self.assertEqual(verdict["c4_m1"], "PASA")
            self.assertEqual(verdict["c4_m2"], "pendiente")
            self.assertEqual(verdict["c4_status"], "m1=PASA; m2=pendiente")


class S3CheckNegativeTests(S3EvidenceTestBase):
    """Una negativa por check: la corrida sana con una sola alteracion que lo viola."""

    def test_neg_s3_00_observed_adapter_stamp(self):
        case = self.case()
        case.build()
        _set_scalar_str(case.ops["s3_00_observe"]["payload"], "adapter_ver",
                        "dsbx-qa-exp1+deadbeefdeadbeef")
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-00")
        self.assertIn("adapter_ver", chk["detail"])

    def test_neg_s3_01_pre_gear_sweep_incomplete(self):
        case = self.case()
        case.build()
        _set_scalar_num(case.ops["s3_01_apply1"]["payload"], "pre_gear_cleared_n", 0.0)
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-01")
        self.assertIn("pre_gear_sweep", chk["detail"])

    def test_neg_s3_02_initial_distance_not_twenty(self):
        case = self.case()
        case.build()
        case.jobs["s3_02_once"]["rows"][0]["wp_x_m"] = 4541.0
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-02")
        self.assertIn("initial_distance", chk["detail"])

    def test_neg_s3_03_loop_window_short(self):
        case = self.case()
        case.build()
        last = case.jobs["s3_03_loop"]["rows"][-1]
        last["dtsum_ms"] = 59000.0
        last["tick_ms"] = 59000.0
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-03")
        self.assertIn("loop_window_short", chk["detail"])

    def test_neg_s3_04_wrong_observed_emote(self):
        case = self.case()
        case.build()
        for row in case.jobs["s3_04_nod"]["rows"]:
            row["observed_emote_id"] = 59.0
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-04")
        self.assertIn("nod:never_started", chk["detail"])

    def test_neg_s3_05_roam_leaves_radius(self):
        case = self.case()
        case.build()
        row = case.jobs["s3_05_urban"]["rows"][2]
        row["x_m"] = 4616.0
        row["z_m"] = 10300.0
        row["dist_center_m"] = 16.0
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-05")
        self.assertIn("outside_radius", chk["detail"])

    def test_neg_s3_06_unreachable_marked_as_reached(self):
        case = self.case()
        case.build()
        case.jobs["s3_06_unreachable"]["rows"][-1]["mark_state"] = "en_marca"
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-06")
        self.assertIn("en_marca", chk["detail"])

    def test_neg_s3_07_combat_emote_terminated(self):
        case = self.case()
        case.build()
        case.jobs["s3_07_combat"]["rows"][0]["emote_state"] = "terminado"
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-07")
        self.assertIn("terminated_under_combat", chk["detail"])

    def test_neg_s3_08_cancellation_only_as_label(self):
        case = self.case()
        case.build()
        for row in case.jobs["s3_cancel_before"]["rows"] + case.jobs["s3_post_before"]["rows"]:
            row["emote_state"] = "agotado"
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-08")
        self.assertIn("cancel_before_start:not_canceled", chk["detail"])

    def test_neg_s3_09_drain_over_limit(self):
        case = self.case()
        case.build()
        start = case.jobs["s3_cancel_after"]["start_ms"]
        case.jobs["s3_cancel_after"]["rows"][4]["cleanup_tick_ms"] = start + 3500.0
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-09")
        self.assertIn("cancel_after_start:drain_too_long", chk["detail"])

    def test_neg_s3_10_fixture_contradicts_catalog(self):
        case = self.case()
        case.build()
        bad = _bad_fixtures(self._tmp.name, emote_key="nod", emote_id=7)
        verdict = self.evaluate(case, fixtures_dir=bad)
        chk = self.assert_not_pass(verdict, "S3-10")
        self.assertIn("emote_catalog_mismatch", chk["detail"])

    def test_neg_s3_11_backend_still_available_without_expansion(self):
        case = self.case()
        case.build()
        _set_scalar_num(case.ops["s3_11_obs"]["payload"], "backend_available_b", 1.0)
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-11")
        self.assertIn("backend_still_available", chk["detail"])

    def test_neg_s3_12_effect_before_reject(self):
        case = self.case()
        case.build()
        _set_scalar_num(case.ops["s3_12_post_capability_lost"]["payload"],
                        "last_op_spawned_props_ever_n", 2.0)
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-12")
        self.assertIn("counter_last_op_spawned_props_ever_n", chk["detail"])


class S3SolBlockingNegativeTests(S3EvidenceTestBase):
    """Una negativa por cada BLOQ de Sol: reproduce la fabricacion y exige FALLA/INCONCLUSO."""

    def test_neg_sol01_scene_without_live_entities(self):
        case = self.case()
        case.build()
        _set_scalar_num(case.ops["s3_01_obs1"]["payload"], "world_props_n", 0.0)
        _set_scalar_num(case.ops["s3_01_obs1"]["payload"], "world_actors_n", 0.0)
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-01")
        self.assertIn("world_counts_before_reset", chk["detail"])

    def test_neg_sol02_invented_motion_and_duration(self):
        case = self.case()
        case.build()
        for row in case.jobs["s3_02_once"]["rows"]:
            row["dtsum_ms"] = 500.0
        for row in case.jobs["s3_03_hold"]["rows"]:
            row["dtsum_ms"] = 5000.0
        verdict = self.evaluate(case)
        c02 = self.assert_not_pass(verdict, "S3-02")
        c03 = self.assert_not_pass(verdict, "S3-03")
        self.assertIn("dtsum_not_growing", c02["detail"])
        self.assertIn("hold_dtsum_not_growing", c03["detail"])

    def test_neg_sol03_labels_instead_of_native_events(self):
        case = self.case()
        case.build()
        for row in case.jobs["s3_04_nod"]["rows"]:
            row["cb_inst_id"] = 10.0
            row["observed_emote_id"] = 58.0
            row["anim_cmd_id"] = 1109.0
            row["anim_state_n"] = 7.0
        case.jobs["s3_cancel_after"]["rows"][3].update(
            {"raw_p_canceled_b": 0.0, "observed_end_cause": "cb_normal", "emote_state": "terminado"}
        )
        verdict = self.evaluate(case)
        c04 = self.assert_not_pass(verdict, "S3-04")
        c08 = self.assert_not_pass(verdict, "S3-08")
        self.assertIn("nod:never_started", c04["detail"])
        self.assertIn("cancel_after_start", c08["detail"])

    def test_neg_sol04_binding_negatives_omitted(self):
        case = self.case()
        case.build(checks={"S3-00"})
        verdict = self.evaluate(case)
        for cid in ("S3-06", "S3-08", "S3-12"):
            chk = self.assert_not_pass(verdict, cid, ("missing",))
            self.assertIn("no_scenario", chk["detail"])
        self.assertEqual(verdict["exit_code"], 2, verdict)

    def test_neg_sol05_injection_absent_from_evidence(self):
        details = []
        for label in (wire.QA_FAULT_NONE, "wrong_emote_played", "fault:wrong_emote_played"):
            case = self.case()
            case.build()
            for row in case.jobs["s3_04_nod"]["rows"]:
                row["observed_emote_id"] = 59.0
            _set_arg_str(case.jobs["s3_04_nod"]["args"], "qa_fault", label)
            verdict = self.evaluate(case)
            chk = self.assert_not_pass(verdict, "S3-04")
            self.assertIn("nod:never_started", chk["detail"])
            details.append(chk["detail"])
        self.assertEqual(len(set(details)), 1, details)

    def test_neg_sol06_backend_not_observable(self):
        case = self.case()
        case.build()
        _set_scalar_num(case.ops["s3_00_observe"]["payload"], "backend_available_b", 0.0)
        verdict = self.evaluate(case)
        chk = self.assert_not_pass(verdict, "S3-00")
        self.assertIn("backend_unavailable", chk["detail"])

    def test_neg_sol07_expected_stamp_instead_of_observed(self):
        diag = self.case(build="diag")
        diag.build()
        verdict = self.evaluate(diag)
        self.assertEqual(verdict["exit_code"], 2, verdict)
        self.assertIn("artifact_unverified", verdict["reasons"])

        case = self.case()
        case.build()
        _set_scalar_str(case.ops["s3_00_observe"]["payload"], "adapter_ver",
                        f"dsbx-qa-exp1+{'0' * 16}")
        verdict = self.evaluate(case, part_name="part-stamp")
        chk = self.assert_not_pass(verdict, "S3-00")
        self.assertIn("adapter_ver", chk["detail"])

    def test_neg_sol08_e1_without_cleanup(self):
        case = self.case()
        case.build(checks={"S3-00", "S3-09"})
        for row in case.jobs["s3_cancel_after"]["rows"] + case.jobs["s3_post_after"]["rows"]:
            row["cleanup_tick_ms"] = 0.0
        verdict = self.evaluate(case, part_name="part-no-cleanup")
        chk = self.assert_not_pass(verdict, "S3-09", ("missing",))
        self.assertIn("cancel_after_start:no_cancel_or_cleanup", chk["detail"])
        self.assertEqual(verdict["exit_code"], 2, verdict)

        case = self.case()
        case.build(checks={"S3-00", "S3-09"})
        case.jobs["s3_cancel_after"]["start_status"] = "rejected"
        case.jobs["s3_cancel_after"]["start_reason"] = "lease_expired"
        verdict = self.evaluate(case, part_name="part-lease-expired")
        chk = self.assert_not_pass(verdict, "S3-09", ("missing",))
        self.assertIn("status:rejected", chk["detail"])
        self.assertEqual(verdict["exit_code"], 2, verdict)

    def test_neg_sol09_two_jobs_on_same_actor(self):
        case = self.case()
        case.build(checks={"S3-00", "S3-02", "S3-03"})
        s2 = case.jobs["s3_02_once"]
        hold = case.jobs["s3_03_hold"]
        hold["start_ms"] = s2["start_ms"] + 1000.0
        hold["end_ms"] = s2["start_ms"] + 4000.0
        verdict = self.evaluate(case)
        self.assertEqual(verdict["exit_code"], 2, verdict)
        self.assertIn("actor_resource_overlap", verdict["reasons"])

    def test_neg_sol10_fixture_contradicts_approved_catalog(self):
        case = self.case()
        case.build()
        bad = _bad_fixtures(self._tmp.name, emote_key="shake", emote_id=41)
        verdict = self.evaluate(case, part_name="part-bad-fixture", fixtures_dir=bad)
        chk = self.assert_not_pass(verdict, "S3-10")
        self.assertIn("emote_catalog_mismatch", chk["detail"])


def _mut_roam_out_of_radius(case):
    row = case.jobs["s3_05_urban"]["rows"][2]
    row.update({"x_m": 4616.0, "z_m": 10300.0, "dist_center_m": 16.0})


def _mut_roam_stand_still(case):
    for row in case.jobs["s3_05_urban"]["rows"]:
        row["path_len_m"] = 0.0
        row["dest_reached_n"] = 0.0


def _mut_fsm_is_final_as_reached(case):
    case.jobs["s3_06_unreachable"]["rows"][-1]["mark_state"] = "en_marca"


def _mut_wrong_emote_cmd(case):
    for row in case.jobs["s3_04_nod"]["rows"]:
        row["observed_emote_id"] = 59.0


def _mut_stale_callback_contamination(case):
    for row in case.jobs["s3_stale"]["rows"]:
        row["cb_inst_id"] = 5.0
        row["max_cb_inst_at_req_n"] = 5.0
        row["observed_emote_id"] = 58.0
        row["anim_cmd_id"] = 1109.0
        row["anim_state_n"] = 7.0
    case.jobs["s3_stale"]["rows"][-1]["emote_state"] = "terminado"


def _mut_canceled_emote_as_done(case):
    case.jobs["s3_cancel_after"]["rows"][3].update(
        {"raw_p_canceled_b": 0.0, "observed_end_cause": "cb_normal", "emote_state": "terminado"}
    )


def _mut_late_emote_after_timeout(case):
    for row in case.jobs["s3_post_never"]["rows"]:
        row["exp_pending_id"] = 58.0
        row["post_cleanup_cb_count_n"] = 1.0


def _mut_no_clear_on_stop_after_start(case):
    for row in case.jobs["s3_post_after"]["rows"]:
        row["exp_pending_id"] = 58.0


def _mut_combat_emote_as_done(case):
    case.jobs["s3_07_combat"]["rows"][0]["emote_state"] = "terminado"


def _mut_extra_default_gear(case):
    _set_scalar_num(case.ops["s3_01_apply1"]["payload"], "pre_gear_cleared_n", 0.0)


def _mut_props_before_actor_check(case):
    payload = case.ops["s3_12_post_capability_lost"]["payload"]
    _set_scalar_num(payload, "last_op_spawned_props_ever_n", 2.0)
    _set_scalar_num(payload, "last_op_deleted_objects_ever_n", 2.0)
    _set_scalar_num(payload, "last_op_env_writes_ever_n", 1.0)


_MUTATIONS = {
    "roam_out_of_radius": _mut_roam_out_of_radius,
    "roam_stand_still": _mut_roam_stand_still,
    "fsm_is_final_as_reached": _mut_fsm_is_final_as_reached,
    "wrong_emote_cmd": _mut_wrong_emote_cmd,
    "stale_callback_contamination": _mut_stale_callback_contamination,
    "canceled_emote_as_done": _mut_canceled_emote_as_done,
    "late_emote_after_timeout": _mut_late_emote_after_timeout,
    "no_clear_on_stop_after_start": _mut_no_clear_on_stop_after_start,
    "combat_emote_as_done": _mut_combat_emote_as_done,
    "extra_default_gear": _mut_extra_default_gear,
    "props_before_actor_check": _mut_props_before_actor_check,
}


class S3MutantTests(S3EvidenceTestBase):
    """Cada mutante de EXPECTED_MUTANTS sale exit 1 con sus must_fail_checks en fail."""

    def test_expected_mutants_fail_only_their_checks(self):
        self.assertEqual(set(_MUTATIONS), set(s3_mutants.EXPECTED_MUTANTS))
        for name, spec in s3_mutants.EXPECTED_MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(spec["expected_exit_code"], 1)
                must = list(spec["must_fail_checks"])
                self.assertEqual(len(must), 1, spec)
                case = self.case()
                case.build(checks={"S3-00", must[0]})
                _MUTATIONS[name](case)
                verdict = self.evaluate(case, part_name=f"mut-{name}")
                self.assertEqual(verdict["exit_code"], spec["expected_exit_code"], verdict)
                self.assertEqual(verdict["verdict"], "FALLA", verdict)
                for cid in must:
                    self.assertEqual(_check(verdict, cid)["status"], "fail",
                                     _check(verdict, cid))
                for cid, allowed in spec["allowed_non_pass"].items():
                    self.assertIn(_check(verdict, cid)["status"], allowed,
                                  f"{name}:{cid}")
                self.assertEqual(_check(verdict, "S3-00")["status"], "pass", name)
                self.assertEqual(_check(verdict, "S3-10")["status"], "pass", name)


class S3E2ETests(unittest.TestCase):
    """Extremo a extremo: el gate real produce evidencias que el evaluador reevalua."""

    def _gate(self, tmp, *extra):
        evidence = Path(tmp) / "evidence"
        cmd = [sys.executable, str(QA_DIR / "m1_gate.py"), "spike", "S3",
               "--both", "--build", "offline", "--evidence", str(evidence), *extra]
        proc = subprocess.run(cmd, cwd=DEV_ROOT, capture_output=True, text=True,
                              encoding="utf-8", timeout=600)
        return proc, evidence

    def _parts(self, evidence):
        if not evidence.is_dir():
            return []
        return [p for p in sorted(evidence.iterdir())
                if p.is_dir() and (p / "manifest.json").is_file() and (p / "samples").is_dir()]

    def _assert_orders_valid(self, part):
        rows = f03_common.read_jsonl(part / "samples" / "bridge.jsonl")
        hellos = {}
        for ev in rows:
            if ev.get("ev") == "hello" and ev.get("http") == 200:
                hellos.setdefault(ev.get("peer"), set()).add(ev.get("inst"))
        manifest = gate_core.read_json(part / "manifest.json")
        ttl = (manifest.get("params") or {}).get("ttl_ms")
        self.assertIsInstance(ttl, int, part)
        self.assertGreater(ttl, 0, part)
        enq = [ev for ev in rows if ev.get("ev") == "enq"]
        self.assertTrue(enq, part)
        delivered = {}
        for ev in rows:
            if ev.get("ev") in ("deliver", "expire") and isinstance(ev.get("op_id"), str):
                delivered.setdefault(ev["op_id"], []).append(ev)
        for ev in enq:
            self.assertIsInstance(ev.get("inst"), str, ev)
            self.assertTrue(ev["inst"], ev)
            self.assertIn(ev["inst"], hellos.get(ev.get("peer"), set()), ev)
            self.assertIsInstance(ev.get("t_ms"), (int, float), ev)
            self.assertGreater(ev["t_ms"], 0, ev)
            args = ev.get("args") or {}
            sk = list(args.get("sk") or [])
            sv = list(args.get("sv") or [])
            self.assertIn("qa_fault", sk, ev)
            qf = sv[sk.index("qa_fault")]
            self.assertEqual(len(qf), wire.QA_FAULT_LEN, ev)
            self.assertTrue(qf.isascii(), ev)
            self.assertIn(ev.get("op_id"), delivered, ev)

    def test_e2e_full_run_reevaluate_and_orders(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, evidence = self._gate(tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            parts = self._parts(evidence)
            self.assertTrue(parts, "el gate no dejo ninguna parte evaluable")
            self.assertIn("run", [p.name for p in parts])
            for part in parts:
                stored = gate_core.read_json(part / "verdict.json")
                fresh = s3_eval.evaluate(part, repo_root=REPO_TOP)
                self.assertEqual(fresh["exit_code"], stored["exit_code"], part.name)
                self.assertEqual(fresh["verdict"], stored["verdict"], part.name)
                self._assert_orders_valid(part)

    def test_e2e_evaluate_only_preserves_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, evidence = self._gate(tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            parts = self._parts(evidence)
            self.assertTrue(parts, "el gate no dejo ninguna parte evaluable")
            before = {p.name: (p / "verdict.json").read_bytes() for p in parts}
            proc, _ = self._gate(tmp, "--evaluate-only")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for part in parts:
                self.assertEqual((part / "verdict.json").read_bytes(), before[part.name], part.name)


if __name__ == "__main__":
    unittest.main()
