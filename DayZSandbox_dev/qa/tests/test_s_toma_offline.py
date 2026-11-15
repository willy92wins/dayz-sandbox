"""Tests offline del oráculo de S-toma (brief S-toma §5, §6, §9 y T1-T13 / E1-E9; BLOQ 1-17 de Sol, ronda 1).

La evidencia sintética sana es la que produciría una implementación honesta según el brief: reloj del arnés `h_ms` igual
al `t_ms` del puente, ticks de cada peer en su propio reloj (aquí con theta = 0 por simplicidad, los peers comparten
origen con el arnés), frames crudos monótonos por peer, `take_clock_ping` reales, filas por frame, registro terminal
único por toma, `key_rpc`/`rpc_emit` del servidor y keepalives del puente. Cada negativa `test_neg_solNN_*` reproduce la
fabricación o el defecto que Sol demostró con «siete verdes»."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

QA_DIR = Path(__file__).resolve().parents[1]
if str(QA_DIR) not in sys.path:
    sys.path.insert(0, str(QA_DIR))
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

import f03_common
import gate_core
import m1_gate
import s_toma_eval
import s_toma_mutants
import wire
from tests import test_probe_static

SRV_NCOL = [
    "srv_frame", "srv_tick_ms", "dtsum_ms", "take_dtsum_ms",
    "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11",
]
SRV_SCOL = ["row_kind", "subject_id", "state_or_origin"]

CLI_NCOL = [
    "cli_frame", "cli_tick_ms", "dtsum_ms", "take_dtsum_ms",
    "sandbox_cam_active_b", "hud_hidden_b", "quickbar_hide_flag_b", "quickbar_widget_visible_b",
    "cam_x_m", "cam_y_m", "cam_z_m", "cam_yaw_deg", "cam_pitch_deg", "cam_fov_deg",
    "ack_req_epoch_n", "ack_cur_epoch_n", "aux_n",
]
CLI_SCOL = [
    "row_kind", "detail", "ack_req_take_id", "ack_req_state", "ack_req_origin",
    "ack_resp_class", "ack_cur_take_id", "ack_cur_state", "ack_cur_origin",
]

ACT_OBS_NCOL = ["x_m", "y_m", "z_m", "net_id_low", "net_id_high", "alive_b"]
ACT_OBS_SCOL = ["actor_id", "real_class", "slot_name", "item_class"]
BIND_NCOL = ["alt_idx"]
BIND_SCOL = ["action_name", "key_name"]

EXP_STAMP = "0123456789abcdef"
ADAPTER_VER = "dsbx-qa-exp1+" + EXP_STAMP
ACTION = "UADsbxQaTakeStop"
INPUTS_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n<modded_inputs><inputs><actions>'
    b'<input name="UADsbxQaTakeStop" loc="Sandbox stop"/></actions>'
    b'<preset><input name="UADsbxQaTakeStop"><btn name="kF9"/></input></preset></inputs></modded_inputs>\n'
)


class _TestSources(s_toma_eval._GitSources):
    """Costura de lectura del commit sellado: el sello de la expansion y `inputs.xml` sintéticos; el resto, git real."""

    def __init__(self, repo_root, *, exp_stamp=EXP_STAMP, inputs_xml=INPUTS_XML, fixture_bytes=None):
        super().__init__(repo_root)
        self._exp = exp_stamp
        self._inputs = inputs_xml
        self._fix = fixture_bytes

    def exp_stamp(self, git_head):
        return self._exp

    def inputs_xml(self, git_head):
        return self._inputs

    _FIX_CACHE: dict = {}

    def fixture_bytes(self, git_head):
        if self._fix is not None:
            return self._fix
        if git_head not in _TestSources._FIX_CACHE:
            _TestSources._FIX_CACHE[git_head] = super().fixture_bytes(git_head)
        return _TestSources._FIX_CACHE[git_head]


def _evaluate(pdir, **kw):
    kw.setdefault("sources", _TestSources(f03_common.REPO_ROOT))
    return s_toma_eval.evaluate(pdir, **kw)


def _make_srv_row(srv_frame, srv_tick_ms, dtsum_ms, take_dtsum_ms, row_kind, subject_id="", state_or_origin="",
                  v1=0.0, v2=0.0, v3=0.0, v4=0.0, v5=0.0, v6=0.0, v7=0.0, v8=0.0, v9=0.0, v10=0.0, v11=0.0):
    return {
        "srv_frame": int(srv_frame), "srv_tick_ms": float(srv_tick_ms), "dtsum_ms": float(dtsum_ms),
        "take_dtsum_ms": float(take_dtsum_ms),
        "v1": float(v1), "v2": float(v2), "v3": float(v3), "v4": float(v4), "v5": float(v5), "v6": float(v6),
        "v7": float(v7), "v8": float(v8), "v9": float(v9), "v10": float(v10), "v11": float(v11),
        "row_kind": str(row_kind), "subject_id": str(subject_id), "state_or_origin": str(state_or_origin),
    }


def _make_cli_row(cli_frame, cli_tick_ms, dtsum_ms, take_dtsum_ms, row_kind, detail="",
                  sandbox_cam_active_b=0, hud_hidden_b=0, quickbar_hide_flag_b=0, quickbar_widget_visible_b=1,
                  cam_x_m=7500.0, cam_y_m=17.4, cam_z_m=7500.0, cam_yaw_deg=0.0, cam_pitch_deg=-6.0, cam_fov_deg=0.75,
                  ack_req_epoch_n=0, ack_cur_epoch_n=0, aux_n=0, ack_req_take_id="", ack_req_state="",
                  ack_req_origin="", ack_resp_class="", ack_cur_take_id="", ack_cur_state="", ack_cur_origin=""):
    return {
        "cli_frame": int(cli_frame), "cli_tick_ms": float(cli_tick_ms), "dtsum_ms": float(dtsum_ms),
        "take_dtsum_ms": float(take_dtsum_ms),
        "sandbox_cam_active_b": int(sandbox_cam_active_b), "hud_hidden_b": int(hud_hidden_b),
        "quickbar_hide_flag_b": int(quickbar_hide_flag_b), "quickbar_widget_visible_b": int(quickbar_widget_visible_b),
        "cam_x_m": round(float(cam_x_m), 4), "cam_y_m": round(float(cam_y_m), 4), "cam_z_m": round(float(cam_z_m), 4),
        "cam_yaw_deg": round(float(cam_yaw_deg), 4), "cam_pitch_deg": round(float(cam_pitch_deg), 4),
        "cam_fov_deg": round(float(cam_fov_deg), 4),
        "ack_req_epoch_n": int(ack_req_epoch_n), "ack_cur_epoch_n": int(ack_cur_epoch_n), "aux_n": int(aux_n),
        "row_kind": str(row_kind), "detail": str(detail),
        "ack_req_take_id": str(ack_req_take_id), "ack_req_state": str(ack_req_state),
        "ack_req_origin": str(ack_req_origin), "ack_resp_class": str(ack_resp_class),
        "ack_cur_take_id": str(ack_cur_take_id), "ack_cur_state": str(ack_cur_state),
        "ack_cur_origin": str(ack_cur_origin),
    }


def _sf(tick):
    """Frame del servidor a 50 ms por frame (sus filas crudas llevan el contador del propio peer)."""
    return int(float(tick) // 50.0)


def _cf(tick):
    """Frame del cliente (~88 ms por frame)."""
    return int(float(tick) // 88.0)
class _SyntheticTraceBuilder:
    """Construye una carpeta de parte sintética completa y válida para S-toma (puente, escenario y manifiesto)."""

    def __init__(self, fixture: dict, git_head: str, probe_stamp: str, op_nonce: str = "a1b2c3d4e5f60718"):
        self.fixture = fixture
        self.git_head = git_head
        self.probe_stamp = probe_stamp
        self.probe_ver = f"dsbx-qa1+{probe_stamp}"
        self.op_nonce = op_nonce
        self._op_seq = 0
        self.bridge_rows: list[dict] = []
        self.scenario_rows: list[dict] = []
        self.op_map: list[dict] = []
        self.srv_inst = "srv-inst-1"
        self.cli_inst = "cli-inst-1"
        self.t_ms = 100.0
        self.epoch = 1
        self.cuts: list[tuple[str, float, float]] = []
        self.cut_rows: list[dict] = []

    # --- reloj del arnes (= t_ms del puente) ---
    def clock(self, h_ms: float):
        self.t_ms = max(self.t_ms, float(h_ms))

    def next_op_id(self) -> str:
        self._op_seq += 1
        return f"{self.op_nonce}-{self._op_seq}"

    def emit_hello(self, peer: str, inst: str, build: str = "offline", probe_ver: str | None = None):
        pv = self.probe_ver if probe_ver is None else probe_ver
        if peer == "server":
            self.srv_inst = inst
        else:
            self.cli_inst = inst
        self.t_ms += 5.0
        self.bridge_rows.append(
            {
                "args": {"build": build, "inst": inst, "peer": peer, "probe_ver": pv, "proto": "qa0"},
                "ev": "hello", "http": 200, "inst": inst, "ok": True, "peer": peer, "t_ms": round(self.t_ms, 3),
            }
        )

    def emit_keepalive(self, peer: str, t_ms: float):
        self.bridge_rows.append(
            {
                "body_len": 30, "ev": "keepalive", "frame": _sf(t_ms) if peer == "server" else _cf(t_ms), "http": 200,
                "inst": self.srv_inst if peer == "server" else self.cli_inst, "n_ops": 0, "now_ms": round(t_ms, 3),
                "peer": peer, "t_ms": round(t_ms, 3), "tick_s": round(t_ms / 1000.0, 4),
            }
        )

    def emit_cut(self, peer: str, kind: str, t_ms: float):
        self.bridge_rows.append({"ev": kind, "peer": peer, "t_ms": round(float(t_ms), 3)})

    def emit_op(
        self,
        peer: str,
        verb: str,
        args_str: dict | None = None,
        args_num: dict | None = None,
        read_str: dict | None = None,
        read_num: dict | None = None,
        ncol: list[str] | None = None,
        scol: list[str] | None = None,
        rows: list[dict] | None = None,
        status: str = "done",
        reason: str = "",
        qa_fault: str | None = None,
        frame: int | None = None,
        tick_s: float | None = None,
        deliver_at: float | None = None,
        rtt_ms: float = 1.0,
    ) -> str:
        op_id = self.next_op_id()
        inst = self.srv_inst if peer == "server" else self.cli_inst

        packed_args_clean = wire.pack_payload(scalars_str=args_str, scalars_num=args_num)
        astr_wire = dict(args_str or {})
        astr_wire["qa_fault"] = wire.format_qa_fault(qa_fault)
        packed_args_wire = wire.pack_payload(scalars_str=astr_wire, scalars_num=args_num)

        if deliver_at is not None:
            self.t_ms = max(self.t_ms + 1.0, float(deliver_at) - 1.0)
            issued_ms = round(self.t_ms, 3)
            self.t_ms += 1.0
        else:
            self.t_ms += 2.0
            issued_ms = round(self.t_ms, 3)
            self.t_ms += 1.0
        t_deliver = round(self.t_ms, 3)
        wire_order = {
            "args": packed_args_wire, "inst": inst, "issued_ms": issued_ms, "op_id": op_id, "ttl_ms": 5000, "verb": verb,
        }
        poll_bytes = wire.poll_wire_bytes(wire_order, now_ms=t_deliver)

        packed_read = wire.pack_payload(
            scalars_str=read_str, scalars_num=read_num, num_cols=ncol, str_cols=scol, row_dicts=rows,
        )
        read_with_has = dict(packed_read)
        read_with_has["has"] = ["payload"]

        tick = float(tick_s) if tick_s is not None else (t_deliver + rtt_ms / 2.0) / 1000.0
        if frame is None:
            frame = _sf(tick * 1000.0) if peer == "server" else _cf(tick * 1000.0)
        res_body = {
            "done_ms": round(tick * 1000.0 + 1.0, 3), "dup": False, "frame_done": int(frame + 1),
            "frame_recv": int(frame), "op_id": op_id, "read": read_with_has, "reason": reason,
            "recv_ms": round(tick * 1000.0, 3), "status": status,
        }
        res_bytes = wire.result_wire_bytes(res_body)

        self.bridge_rows.append(
            {"args": packed_args_clean, "ev": "enq", "inst": inst, "op_id": op_id, "peer": peer, "t_ms": issued_ms, "verb": verb}
        )
        self.bridge_rows.append(
            {
                "body_len": len(poll_bytes), "ev": "poll", "frame": int(frame), "held_ms": 1.0, "http": 200,
                "inst": inst, "n_ops": 1, "now_ms": t_deliver, "op_ids": [op_id], "peer": peer, "t_ms": t_deliver,
                "tick_s": round(tick, 4),
            }
        )
        self.bridge_rows.append(
            {"args": packed_args_clean, "ev": "deliver", "inst": inst, "op_id": op_id, "peer": peer, "t_ms": t_deliver, "verb": verb}
        )
        self.t_ms = round(t_deliver + rtt_ms, 3)
        self.bridge_rows.append(
            {
                "body_len": len(res_bytes), "ev": "result", "http": 200, "op_id": op_id, "peer": peer,
                "result": res_body, "t_ms": round(self.t_ms, 3),
            }
        )
        self.op_map.append({"n": len(self.op_map) + 1, "op_id": op_id, "peer": peer, "verb": verb})
        return op_id

    def emit_job_with_pages(
        self,
        peer: str,
        verb: str,
        take_id: str,
        ncol: list[str],
        scol: list[str],
        all_rows: list[dict],
        *,
        mode: str = "rpc",
        state: str = "done",
        reason: str = "",
        end_tick_ms: float = 5000.0,
        onjobend_tick_ms: float = 5005.0,
        released_tick_ms: float = 5008.0,
        page_size: int = 4,
        args_extra_s: dict | None = None,
        args_extra_n: dict | None = None,
    ) -> str:
        job_id = f"job-{verb}-{take_id}-{self._op_seq + 1}"
        a_s = {"mode": mode, "take_id": take_id}
        a_s.update(args_extra_s or {})
        self.emit_op(
            peer, verb, args_str=a_s, args_num=args_extra_n,
            read_str={"job": job_id, "state": "running"}, read_num={"page_size": page_size},
        )
        pages = [all_rows[i: i + page_size] for i in range(0, len(all_rows), page_size)] or [[]]
        for p_idx, page_rows in enumerate(pages):
            self.emit_op(
                peer, "job_read", args_str={"job": job_id}, args_num={"page_n": p_idx},
                read_str={"job": job_id, "reason": reason, "state": state},
                read_num={
                    "end_tick_ms": end_tick_ms, "onjobend_tick_ms": onjobend_tick_ms, "page_n": p_idx,
                    "pages_n": len(pages), "released_tick_ms": released_tick_ms, "rows_total_n": len(all_rows),
                },
                ncol=ncol, scol=scol, rows=page_rows,
            )
        return job_id

    def emit_take_jobs(self, tid: str, arm_rows, srv_rows, cli_rows, *, mode="rpc", arm_extra_s=None, arm_extra_n=None,
                       arm_state="done", arm_reason="", arm_ticks=(5000.0, 5005.0, 5008.0), skip_arm=False,
                       skip_srv=False, skip_cli=False):
        if not skip_arm:
            self.emit_job_with_pages(
                "server", "take_arm", tid, SRV_NCOL, SRV_SCOL, arm_rows, mode=mode, state=arm_state, reason=arm_reason,
                end_tick_ms=arm_ticks[0], onjobend_tick_ms=arm_ticks[1], released_tick_ms=arm_ticks[2],
                args_extra_s=arm_extra_s, args_extra_n=arm_extra_n,
            )
        if not skip_srv:
            self.emit_job_with_pages("server", "take_srv_observe_start", tid, SRV_NCOL, SRV_SCOL, srv_rows, mode=mode)
        if not skip_cli:
            self.emit_job_with_pages("client", "take_cli_watch_start", tid, CLI_NCOL, CLI_SCOL, cli_rows, mode=mode)

    def emit_pings(self, stage: str, rep: int, base_h: float, *, srv_ticks=None, width_ms: float = 2.0,
                   peers=("server", "client"), phases=("pre", "post"), epoch: int | None = None):
        """2 pings por peer antes y despues de la toma: ordenes reales `take_clock_ping` y sus pares en el escenario."""
        ep = self.epoch if epoch is None else epoch
        seq = 0
        for phase in phases:
            n = 0
            for k in range(2):
                for peer in peers:
                    h = (base_h - 500.0 if phase == "pre" else base_h + 7000.0) + 10.0 * n
                    n += 1
                    self.clock(h - 6.0)
                    tick = h + width_ms / 2.0 + 1.0
                    frame = _sf(tick) if peer == "server" else _cf(tick)
                    inst = self.srv_inst if peer == "server" else self.cli_inst
                    self.emit_op(
                        peer, "take_clock_ping", args_num={"ping_seq": seq},
                        read_num={
                            "peer_frame": frame, "peer_tick_ms": round(tick, 3), "dtsum_ms": round(tick, 3),
                            "lease_ms": 3000.0, "last_ok_poll_ms": round(tick - 10.0, 3),
                        },
                        read_str={"peer_role": peer, "observer_stamp": self.probe_ver},
                        deliver_at=h, rtt_ms=width_ms + 2.0, frame=frame, tick_s=tick / 1000.0,
                    )
                    seq += 1
                    send_rec = self.bridge_rows[-4]
                    res_rec = self.bridge_rows[-1]
                    self.scenario_rows.append(
                        {
                            "epoch": ep, "h_recv_ms": round(res_rec["t_ms"] + 0.5, 3),
                            "h_send_ms": round(send_rec["t_ms"] - 0.5, 3), "inst": inst, "kind": "clock_pair",
                            "peer": peer, "peer_frame": frame, "peer_tick_ms": round(tick, 3), "phase": phase,
                            "rep": rep, "stage": stage,
                        }
                    )

    def finalize_bridge(self, cuts):
        """Keepalives de 1 s por peer entre su primer y ultimo evento, salvo dentro de los cortes del puente."""
        by_peer = {"server": [], "client": []}
        for r in self.bridge_rows:
            if r.get("peer") in by_peer and "t_ms" in r:
                by_peer[r["peer"]].append(r["t_ms"])
        extra = []
        for peer, ts in by_peer.items():
            if not ts:
                continue
            windows = [(s, e) for (p, s, e) in cuts if p == peer]
            t = (int(min(ts) // 1000.0) + 1) * 1000.0
            while t < max(ts):
                if not any(s <= t <= e for s, e in windows):
                    extra.append(
                        {
                            "body_len": 30, "ev": "keepalive", "frame": _sf(t) if peer == "server" else _cf(t),
                            "http": 200, "inst": self.srv_inst if peer == "server" else self.cli_inst, "n_ops": 0,
                            "now_ms": float(t), "peer": peer, "t_ms": float(t), "tick_s": round(t / 1000.0, 4),
                        }
                    )
                t += 1000.0
        order = {id(r): i for i, r in enumerate(self.bridge_rows)}
        merged = sorted(self.bridge_rows + extra, key=lambda r: (r["t_ms"], order.get(id(r), -1)))
        self.bridge_rows[:] = merged
def _ref_camera_position(keyframes, t_ms):
    """Curva de referencia INDEPENDIENTE del evaluador (BLOQ 17): forma de Hermite con tangentes de diferencia centrada.

    Catmull-Rom uniforme en el parametro de segmento: m_i = (p_{i+1} - p_{i-1}) / 2, con el extremo duplicado en los
    bordes. No comparte codigo ni formulacion polinomica con `s_toma_eval.eval_catmull_rom_path`."""
    kfs = sorted(keyframes, key=lambda k: k["t_ms"])
    pts = [k["pos_m"] for k in kfs]
    ts = [k["t_ms"] for k in kfs]
    if t_ms <= ts[0]:
        return list(pts[0])
    if t_ms >= ts[-1]:
        return list(pts[-1])
    i = max(j for j in range(len(ts) - 1) if ts[j] <= t_ms)
    u = (t_ms - ts[i]) / (ts[i + 1] - ts[i])
    p_prev = pts[i - 1] if i > 0 else pts[i]
    p_next2 = pts[i + 2] if i + 2 < len(pts) else pts[i + 1]
    h00 = 2 * u ** 3 - 3 * u ** 2 + 1
    h10 = u ** 3 - 2 * u ** 2 + u
    h01 = -2 * u ** 3 + 3 * u ** 2
    h11 = u ** 3 - u ** 2
    out = []
    for c in range(3):
        m0 = 0.5 * (pts[i + 1][c] - p_prev[c])
        m1 = 0.5 * (p_next2[c] - pts[i][c])
        out.append(h00 * pts[i][c] + h10 * m0 + h01 * pts[i + 1][c] + h11 * m1)
    return out


def _make_b6_obs_rows(fixture: dict, *, skip_reset: bool = False) -> list[dict]:
    rows = []
    for idx, act in enumerate(fixture["actors"], start=1):
        pos = list(act["mark_pos_m"])
        if skip_reset and idx == 1:
            pos[0] += 4.0
        for w in act["wardrobe"]:
            rows.append(
                {
                    "actor_id": act["actor_id"], "alive_b": 1,
                    "item_class": "TShirt_Red" if (skip_reset and idx == 1 and w["slot_name"] == "Body") else w["item_class"],
                    "net_id_high": 0, "net_id_low": 100 + idx, "real_class": act["real_class"],
                    "slot_name": w["slot_name"], "x_m": float(pos[0]), "y_m": float(pos[1]), "z_m": float(pos[2]),
                }
            )
    return rows


def _apply_frame_bits(frames, press_tick=None, hold_ms=0.0, pending=None):
    """`aux_n = press_edge_b + 2*hold_b + 4*pending_stop_b` de los frames crudos del cliente."""
    edge_done = False
    for r in frames:
        bits = 0
        t = r["cli_tick_ms"]
        if press_tick is not None and not edge_done and t >= press_tick:
            bits |= 1
            edge_done = True
        if press_tick is not None and hold_ms > 0 and press_tick <= t < press_tick + hold_ms:
            bits |= 2
        if pending is not None and pending[0] <= t < pending[1]:
            bits |= 4
        r["aux_n"] = bits


def _build_positive_take_rows(
    fixture: dict,
    take_id: str,
    stage: str,
    rep: int,
    base: float,
    *,
    mode: str = "rpc",
    origin: str = "web",
    allow_dmg_pre_b: int = 1,
    go_delay_ms: float = 0.0,
    actor1_lag_ms: float = 0.0,
    actor2_lag_ms: float = 0.0,
    actor2_dispatch_lag_ms: float = 0.0,
    cam_dev: tuple | None = None,
    cam_advance_ms: float = 0.0,
    pending_not_cancelled: bool = False,
    no_restore: bool = False,
    hold_ms: float = 0.0,
    key_delay_ms: float = 0.0,
    epoch: int = 1,
    interrupt_at_ms: float | None = None,
    drop_cam_window: tuple | None = None,
    stim_offset: float = 3000.0,
    key_flow: tuple = ((0,), (0,), (0,)),
    post_steps: int = 38,
    dup_terminal: bool = False,
):
    """Filas de una toma completa (arm, observador del servidor, watch del cliente, estimulos y metadatos)."""
    keyframes = fixture["camera_path"]["keyframes"]
    mark1 = fixture["actors"][0]["mark_pos_m"]
    mark2 = fixture["actors"][1]["mark_pos_m"]
    target1 = fixture["actors"][0]["dest_pos_m"]
    key_stop = origin == "juego"

    go_send_tick = base + 100.0
    if mode == "common_time":
        sched = base + 1000.0
        disp_tick = sched + 5.0
    else:
        sched = 0.0
        disp_tick = go_send_tick
    go_f = _sf(go_send_tick)
    disp_f = _sf(disp_tick)
    sent_seqs, srv_seqs, ack_seqs = key_flow
    first_srv = srv_seqs[0] if srv_seqs else 0
    stop_dt = float(interrupt_at_ms) if interrupt_at_ms else stim_offset + 20.0 + key_delay_ms + (250.0 * first_srv if key_stop else 0.0)
    stop_tick = disp_tick + stop_dt
    stim_h_ = disp_tick + stim_offset
    stop_f = _sf(stop_tick)
    term_origin = "abort_test" if interrupt_at_ms else origin
    so_term = f"parada:{term_origin}"
    allow_during = 0
    allow_post = 0 if no_restore else allow_dmg_pre_b
    seq0 = 1

    def S(tick, kind, subj="", so="", frame=None, **v):
        f = _sf(tick) if frame is None else frame
        return _make_srv_row(f, tick, tick - base + 50.0, tick - disp_tick, kind, subj, so, **v)

    a2_disp_tick = disp_tick + actor2_dispatch_lag_ms
    arm_rows = [
        S(go_send_tick - 32.0, "arm_ready", take_id, "armada", frame=go_f - 1, v1=allow_dmg_pre_b, v2=1.0, v3=2, v4=0,
          v5=sched, v6=sched, v7=0),
        S(go_send_tick, "go_sent", take_id, "rodando", frame=go_f, v1=go_f, v2=go_send_tick, v3=2, v4=0, v5=sched,
          v6=sched, v7=0),
        S(disp_tick, "dispatch", "actor_1", mode, v1=disp_f, v2=disp_tick),
        S(a2_disp_tick, "dispatch", "actor_2", mode, v1=_sf(a2_disp_tick), v2=a2_disp_tick),
        S(stop_tick, "stop_obs", take_id, so_term, frame=stop_f, v1=stop_f, v2=allow_during, v3=allow_post, v4=0, v5=0,
          v6=1.0, v7=1, v8=1, v9=1, v10=0, v11=len(srv_seqs) if key_stop else 0),
        S(stop_tick + 1850.0, "post_stop_end", take_id, so_term, frame=_sf(stop_tick + 1850.0), v1=stop_f,
          v2=allow_dmg_pre_b, v3=allow_post, v4=0, v5=0, v6=1.0, v7=1, v8=1, v9=1, v10=0, v11=1 if key_stop else 0),
    ]

    srv = []
    if mode == "common_time":
        for i in range(5):
            srv.append(S(sched - 20.0 + 4.0 * i, "act_sample", "actor_1", "pre_go", frame=disp_f - 1, v1=mark1[0],
                         v2=mark1[1], v3=mark1[2], v4=0.0))
    pre_tick = sched - 1.0 if mode == "common_time" else disp_tick - 4.0
    srv.append(S(pre_tick, "act_sample", "actor_1", "pre_go", frame=disp_f - 1, v1=mark1[0], v2=mark1[1], v3=mark1[2], v4=0.0))
    srv.append(S(pre_tick, "act_sample", "actor_2", "pre_go", frame=disp_f - 1, v1=mark2[0], v2=mark2[1], v3=mark2[2],
                 v5=0, v6=0, v7=0, v8=10, v9=0, v10=2, v11=0))
    a1_start = disp_tick + 4.0 + actor1_lag_ms
    if actor1_lag_ms > 0:
        srv.append(S(a1_start - 8.0, "act_sample", "actor_1", "pre_go", frame=_sf(a1_start - 8.0), v1=mark1[0], v2=mark1[1],
                     v3=mark1[2], v4=0.0))
    srv.append(S(a1_start, "act_sample", "actor_1", "rodando", frame=_sf(a1_start) if actor1_lag_ms else disp_f,
                 v1=mark1[0] + 0.25, v2=mark1[1], v3=mark1[2], v4=1.5))
    for dt_, dx_, sp_ in ((1500.0, -1.0, 1.5), (2000.0, -0.5, 1.5), (2500.0, 0.0, 1.0), (2750.0, 0.2, 0.5)):
        srv.append(S(disp_tick + dt_, "act_sample", "actor_1", "rodando", v1=target1[0] + dx_, v2=target1[1], v3=target1[2], v4=sp_))
    srv.append(S(stop_tick - 16.0, "act_sample", "actor_1", "rodando", frame=stop_f, v1=target1[0] + 0.5, v2=target1[1],
                 v3=target1[2], v4=0.1))
    for k_, off_ in ((1, 60.0), (2, 110.0)):
        srv.append(S(stop_tick + off_, "act_sample", "actor_1", so_term, frame=stop_f + k_, v1=mark1[0] + 3.0, v2=mark1[1],
                     v3=mark1[2], v4=0.0))

    a2_start = disp_tick + 4.0 + actor2_lag_ms
    if actor2_lag_ms > 0:
        srv.append(S(a2_start - 8.0, "act_sample", "actor_2", "pre_go", frame=_sf(a2_start - 8.0), v1=mark2[0], v2=mark2[1],
                     v3=mark2[2], v5=0, v6=0, v7=0, v8=10, v9=0, v10=2, v11=0))
    for k_ in range(8):
        t_ = a2_start + 50.0 * k_
        srv.append(S(t_, "act_sample", "actor_2", "rodando", frame=(_sf(t_) if actor2_lag_ms else disp_f + k_), v1=mark2[0],
                     v2=mark2[1], v3=mark2[2], v5=1, v6=1051, v7=13, v8=11, v9=0, v10=2, v11=0))
    for dt_ in (2600.0, 2800.0):
        srv.append(S(disp_tick + dt_, "act_sample", "actor_2", "rodando", v1=mark2[0], v2=mark2[1], v3=mark2[2], v5=1,
                     v6=1051, v7=13, v8=11, v9=1, v10=1, v11=0))
    for step in range(post_steps):
        td_step = stop_dt + step * 50.0
        pend = pending_not_cancelled and td_step < 3200.0 + (0 if not key_delay_ms else key_delay_ms)
        late_gesture = pending_not_cancelled and not pend
        srv.append(S(stop_tick + step * 50.0, "act_sample", "actor_2", so_term, frame=stop_f + step, v1=mark2[0],
                     v2=mark2[1], v3=mark2[2], v5=1, v6=1000 if late_gesture else 1051, v7=1 if late_gesture else 13,
                     v8=11, v9=1 if pend else 0, v10=1 if pend else 0, v11=0))

    for f_ in range(disp_f, stop_f + 10):
        in_window = f_ < stop_f
        srv.append(S(f_ * 50.0 + 20.0, "director_sample", "director", f"rodando" if in_window else so_term, frame=f_,
                     v1=1.0, v2=1, v3=allow_during if in_window else allow_post, v4=0))
    srv.append(S(disp_tick + 1000.0, "melee_hit", "infected_1", "MeleeZombie", v1=1, v2=1, v3=1, v4=1.1, v5=1.8,
                 v6=allow_during, v7=1.0, v8=1, v9=0, v10=1, v11=0))
    srv.append(S(stop_tick, "take_terminal", take_id, so_term, frame=stop_f, v1=stop_f, v2=stop_tick, v3=stop_dt, v4=120.0,
                 v5=stop_f, v6=1, v7=1, v8=allow_post, v9=0, v10=0, v11=0))
    srv.append(S(stop_tick + 16.0, "cleanup_done", take_id, so_term, frame=stop_f, v1=stop_f, v2=stop_tick + 16.0,
                 v3=allow_post, v4=1))
    srv.append(S(go_send_tick + 8.0, "rpc_emit", "TAKE_STATE", "sent", v1=40.0, v2=1))
    srv.append(S(stop_tick + 4.0, "rpc_emit", "TAKE_STATE", "sent", v1=120.0, v2=1))
    if key_stop:
        for n_, sq_ in enumerate(srv_seqs):
            t_rx = stim_h_ + 5.0 + key_delay_ms + 250.0 * sq_ + 10.0
            srv.append(S(t_rx, "key_rpc", take_id, "accepted" if n_ == 0 else "repeat_terminal", frame=_sf(t_rx),
                         v1=epoch, v2=sq_, v3=epoch))
            srv.append(S(t_rx + 20.0 if n_ == 0 else t_rx + 6.0, "rpc_emit", "ACK", "sent", v1=120.0, v2=1))

    go_recv_tick = go_send_tick + 5.0
    go_deliv_tick = sched if mode == "common_time" else go_recv_tick + go_delay_ms
    cli_base = _cf(go_recv_tick)
    f_pre_cam = cli_base + 1 + int((go_deliv_tick - 4.0 - go_recv_tick) // 88.0)

    def C(tick, kind, detail="", frame=None, take_dt=None, **kw):
        return _make_cli_row(f_pre_cam if frame is None else frame, tick, tick - base, (tick - disp_tick) if take_dt is None else take_dt,
                             kind, detail, **kw)

    cli = [
        C(go_recv_tick - 300.0, "frame_sample", "pre_go", frame=cli_base - 2, cam_yaw_deg=10.0),
        C(go_recv_tick, "go_recv", "rpc_go", frame=cli_base - 1, aux_n=disp_f),
        C(go_deliv_tick - 4.0 - cam_advance_ms, "frame_sample", "pre_cam", cam_yaw_deg=10.0),
        C(go_deliv_tick, "go_deliver", "delivered", aux_n=disp_f),
        C(go_deliv_tick + 10.0, "take_state_recv", "dir_main", ack_cur_epoch_n=epoch, ack_cur_take_id=take_id,
          ack_cur_state="rodando", ack_cur_origin=mode, aux_n=seq0 + 1),
    ]

    frames_active = []
    t_cur = 0.0
    k = 0
    while t_cur <= stop_dt:
        pos_c = _ref_camera_position(keyframes, t_cur)
        dev_x = cam_dev[0] if (cam_dev and t_cur >= cam_dev[1]) else 0.0
        drop = bool(drop_cam_window and drop_cam_window[0] <= t_cur < drop_cam_window[1])
        if not drop:
            frames_active.append(
                C(go_deliv_tick + 4.0 + t_cur - cam_advance_ms, "frame_sample", "active", frame=f_pre_cam + 1 + k,
                  take_dt=t_cur, sandbox_cam_active_b=1, hud_hidden_b=1, quickbar_hide_flag_b=1, quickbar_widget_visible_b=0,
                  cam_x_m=pos_c[0] + dev_x, cam_y_m=pos_c[1], cam_z_m=pos_c[2], cam_yaw_deg=10.0, cam_pitch_deg=-6.0,
                  cam_fov_deg=0.75)
            )
        t_cur += 88.0 if (k % 2 == 0) else 89.5
        k += 1
    f_last = f_pre_cam + k

    stim_h = stim_h_
    press_tick = stim_h + 5.0 + key_delay_ms
    ack_ticks = [press_tick + 250.0 * sq_ + 25.0 for sq_ in ack_seqs] or [press_tick]
    rel_start = (stop_tick + 20.0) if key_stop or interrupt_at_ms else stim_h + 40.0
    rel_end = rel_start + (700.0 if hold_ms > 0 else 200.0)
    released = []
    t_ = rel_start
    fr = f_last
    while t_ <= rel_end:
        fr += 1
        yaw = 14.5 if t_ >= stim_h + 70.0 else 10.0
        released.append(C(t_, "frame_sample", "released", frame=fr, take_dt=t_ - disp_tick, cam_yaw_deg=yaw))
        t_ += 80.0

    frames_all = frames_active + released
    if key_stop:
        _apply_frame_bits(
            frames_all, press_tick=press_tick, hold_ms=hold_ms,
            pending=(press_tick + 1.0, max(ack_ticks)) if (key_stop and len(sent_seqs) > 1) else None,
        )

    cli.extend(frames_active)
    if key_stop:
        cli.append(C(press_tick, "key_edge", "press_accepted", frame=f_last, take_dt=stim_offset + 5.0 + key_delay_ms, aux_n=1))
        for sq_ in sent_seqs:
            cli.append(C(press_tick + 1.0 + 250.0 * sq_, "rpc_stop_sent", take_id, frame=f_last, aux_n=sq_))
        for n_, sq_ in enumerate(ack_seqs):
            first_ = (n_ == 0 and sq_ == first_srv)
            cli.append(
                C(press_tick + 250.0 * sq_ + 25.0, "ack_recv", "stop_ack", frame=f_last + 1, ack_req_epoch_n=epoch,
                  ack_req_take_id=take_id, ack_req_state="parada", ack_req_origin="juego",
                  ack_resp_class="first_terminal" if first_ else "repeat_terminal", ack_cur_epoch_n=epoch,
                  ack_cur_take_id=take_id, ack_cur_state="parada", ack_cur_origin="juego", aux_n=seq0 + 2)
            )
    cli.append(
        C(stop_tick + 30.0, "take_state_recv", "dir_main", frame=f_last + 1, ack_cur_epoch_n=epoch,
          ack_cur_take_id=take_id, ack_cur_state="parada", ack_cur_origin=term_origin, aux_n=seq0 + 2)
    )
    cli.extend(released)

    stimuli = [
        {
            "case_id": take_id, "h_ms": stim_h, "hold_ms": hold_ms, "key": "kF9" if key_stop else "", "kind": "stimulus",
            "rep": rep, "stage": stage,
            "stim_type": "web_stop" if origin == "web" else ("key_hold" if hold_ms > 0 else "key_press"), "take_id": take_id,
        }
    ]
    for off in (70.0, 110.0, 150.0):
        stimuli.append(
            {"case_id": take_id, "dx_px": 40, "h_ms": stim_h + off, "kind": "stimulus", "rep": rep, "sign": 1,
             "stage": stage, "stim_type": "look_pulse", "take_id": take_id}
        )
    meta = {
        "allow_dmg_pre_b": allow_dmg_pre_b, "case_id": f"{stage}_r{rep}", "contemp_yaw_ref_deg": 10.0,
        "go_delay_ms": go_delay_ms, "h_start_ms": base, "kind": "take_meta", "mode": mode, "rep": rep,
        "srv_epoch": epoch, "stage": stage, "take_id": take_id,
    }
    return arm_rows, srv, cli, stimuli, meta
class _Mk:
    """Fabrica de filas de una toma pequeña (S3): frames del servidor por tick y frames del cliente crecientes."""

    def __init__(self, base: float, take_id: str):
        self.base = float(base)
        self.tid = take_id
        self.lastf = _cf(base)

    def S(self, tick, kind, subj=None, so="", **v):
        return _make_srv_row(_sf(tick), tick, tick - self.base, tick - self.base, kind,
                             self.tid if subj is None else subj, so, **v)

    def fs(self, tick, active=0, yaw=10.0, bits=0, take_dt=None):
        self.lastf = max(self.lastf + 1, _cf(tick))
        return _make_cli_row(
            self.lastf, tick, tick - self.base, tick - self.base if take_dt is None else take_dt, "frame_sample", "",
            sandbox_cam_active_b=active, hud_hidden_b=active, quickbar_hide_flag_b=active,
            quickbar_widget_visible_b=0 if active else 1, cam_yaw_deg=yaw, aux_n=bits,
        )

    def C(self, tick, kind, detail="", take_dt=None, **kw):
        return _make_cli_row(self.lastf, tick, tick - self.base, tick - self.base if take_dt is None else take_dt,
                             kind, detail, **kw)

    def arm(self, go_tick, allow_pre=1):
        return [
            self.S(go_tick - 50.0, "arm_ready", so="armada", v1=allow_pre, v2=1.0, v3=2),
            self.S(go_tick, "go_sent", so="rodando", v1=_sf(go_tick), v2=go_tick, v3=2),
            self.S(go_tick, "dispatch", "actor_1", "rpc", v1=_sf(go_tick), v2=go_tick),
            self.S(go_tick, "dispatch", "actor_2", "rpc", v1=_sf(go_tick), v2=go_tick),
        ]

    def terminal(self, tick, so, lease_age=130.0, allow_post=1, dtsum=None):
        f = _sf(tick)
        return [
            self.S(tick, "take_terminal", so=so, v1=f, v2=tick, v3=(tick - self.base) if dtsum is None else dtsum,
                   v4=lease_age, v5=f, v6=1, v7=1, v8=allow_post, v9=0, v10=0, v11=0),
            self.S(tick + 10.0, "cleanup_done", so=so, v1=_sf(tick + 10.0), v2=tick + 10.0, v3=allow_post, v4=1),
        ]

    def directors(self, t0, t1, step=500.0, allow=0, so="rodando"):
        out = []
        t = t0
        while t <= t1:
            out.append(self.S(t, "director_sample", "director", so, v1=1.0, v2=1, v3=allow, v4=0))
            t += step
        return out

    def state_recv(self, tick, state, origin, seq, epoch=1, director="dir_main", tid=None):
        return self.C(tick, "take_state_recv", director, ack_cur_epoch_n=epoch,
                      ack_cur_take_id=self.tid if tid is None else tid, ack_cur_state=state, ack_cur_origin=origin,
                      aux_n=seq)


def _srv_status_op(b, tid, *, state="rodando", origin="rpc", epoch=1, transitions=0, rejected=0, reg="", sender="",
                   payload="", term_frame=0, term_lease=0.0, director="dir_main"):
    b.emit_op(
        "server", "take_scene_prep", args_str={"op": "status", "take_id": tid},
        read_str={
            "active_take_id": tid, "take_state": state, "take_origin": origin, "director_id": director,
            "director_engine_uid": "qa-uid-dir-main", "reg_engine_uid": reg, "sender_engine_uid": sender,
            "payload_sender_id": payload, "observer_stamp": b.probe_ver, "adapter_ver": ADAPTER_VER,
        },
        read_num={
            "srv_epoch": epoch, "transitions_n": transitions, "restorations_n": transitions,
            "srv_key_rpc_recv_n": rejected, "srv_key_rpc_rejected_n": rejected, "term_frame": term_frame,
            "term_lease_age_ms": term_lease, "term_tick_ms": 0.0, "restore_frame": term_frame, "cleanup_end_frame": term_frame,
            "last_ok_poll_ms": 0.0, "lease_ms": 3000.0, "scene_ok_b": 1, "observer_ok_b": 1,
        },
    )


def _cli_status_op(b, tid, *, state="rodando", origin="rpc", epoch=1, seq=2, director="dir_main", cam_active=1):
    b.emit_op(
        "client", "take_cam_prep", args_str={"op": "status", "take_id": tid},
        read_str={
            "cli_cached_take_id": tid, "cli_cached_state": state, "cli_cached_origin": origin,
            "cli_cached_director_id": director, "loaded_path_hash": "b6_cam_v1_8f3a1c", "pending_stop_take_id": "",
        },
        read_num={
            "cli_cached_epoch": epoch, "cli_state_seq": seq, "cli_state_recv_tick_ms": 0.0,
            "sandbox_cam_active_b": cam_active, "cam_ready_b": 1, "lease_ms": 3000.0, "last_ok_poll_ms": 0.0,
        },
    )


def _binding_op(b, op, rows_keys, *, conflict_rows=(), target_key=None, build="1.30.164200"):
    rows = [{"alt_idx": 0, "action_name": ACTION, "key_name": k} for k in rows_keys]
    rows += [{"alt_idx": 0, "action_name": a, "key_name": k} for a, k in conflict_rows]
    args = {"action_name": ACTION, "op": op}
    if target_key:
        args["target_key"] = target_key
    read_s = {
        "bound_keys_csv": ",".join(rows_keys), "build_version": build, "conflicting_actions_csv": "",
        "selected_alt_key": "kF10", "selected_def_key": "kF9",
    }
    b.emit_op(
        "client", "take_key_op", args_str=args, read_str=read_s,
        read_num={
            "candidates_checked_n": 4, "conflict_count_alt": 0, "conflict_count_def": 0, "export_called_b": 1,
            "free_candidates_n": 3, "input_id": 77,
        },
        ncol=BIND_NCOL, scol=BIND_SCOL, rows=rows,
    )


def _emit_take_meta(b, tid, stage, case, rep, **extra):
    row = {"case_id": case, "kind": "take_meta", "rep": rep, "stage": stage, "take_id": tid}
    row.update(extra)
    b.scenario_rows.append(row)


def _emit_stim(b, tid, stage, case, stim_type, h_ms, **extra):
    row = {"case_id": case, "h_ms": float(h_ms), "kind": "stimulus", "stage": stage, "stim_type": stim_type, "take_id": tid}
    row.update(extra)
    b.scenario_rows.append(row)


def _emit_s0(b, ctx):
    prefix = ctx["prefix"]
    b.emit_hello("server", "srv-inst-1")
    b.emit_hello("client", "cli-inst-1")
    b.scenario_rows.append(
        {"calib_sign": 1, "calib_step_deg": 4.5, "eps_look_deg": 0.5, "kind": "run_meta", "no_pulse_shift_deg": 0.05,
         "take_id_prefix": prefix}
    )
    b.emit_op(
        "server", "take_scene_prep", args_str={"op": "verify"},
        read_str={"adapter_ver": ADAPTER_VER, "observer_stamp": b.probe_ver}, read_num={"observer_ok_b": 1, "scene_ok_b": 1},
    )
    conflict = [("UAGear", "kF9")] if ctx["mutant"] == "conflicto_tecla_ignorado" else []
    _binding_op(b, "audit_candidates", [], conflict_rows=[("UAGear", "kG")] + conflict)
    _emit_take_meta(b, prefix + "keydef", "S0a", "keydef", 1)
    _binding_op(b, "bind_key", ["kF10"], target_key="kF10")

    b.clock(900.0)
    b.emit_hello("client", "cli-inst-2")
    tid = prefix + "keyreb"
    base = 2000.0
    b.emit_pings("S0b", 1, base, phases=("pre",))
    _emit_take_meta(b, tid, "S0b", "keyreb", 1, h_start_ms=base)
    _emit_stim(b, tid, "S0b", "keyreb", "key_press", base + 600.0, key="kF9")
    _emit_stim(b, tid, "S0b", "keyreb", "key_press", base + 1300.0, key="kF10")
    mk = _Mk(base, tid)
    arm = mk.arm(base + 100.0)
    srv = mk.directors(base + 150.0, base + 1300.0, step=150.0) + mk.terminal(base + 1330.0, "parada:juego")
    cli = []
    t = base - 300.0
    press_new = base + 1305.0
    edge_done = False
    while t <= base + 1700.0:
        bits = 0
        if not edge_done and t >= press_new:
            bits = 1
            edge_done = True
        cli.append(mk.fs(t, bits=bits))
        t += 90.0
    cli.append(mk.C(press_new, "key_edge", "press_accepted", aux_n=1, take_dt=1205.0))
    b.emit_take_jobs(tid, arm, srv, cli)
    b.emit_pings("S0b", 1, base, phases=("post",))
    _binding_op(b, "bind_key", ["kF9"], target_key="kF9")
    _binding_op(b, "restore_bindings", ["kF9"])


def _emit_main_series(b, ctx):
    """S1, S1sel, S1c, S2 y S2c con sus resets observados, perturbacion y 4 pings por repeticion."""
    fixture = ctx["fixture"]
    prefix = ctx["prefix"]
    mut = ctx["mutant"]
    s1_delays = ctx["s1_delays"]

    def series(stage, label, bases, mode, origin, *, reset=False, delays=(0.0, 0.0, 0.0), extra=None):
        for rep in (1, 2, 3):
            tid = f"{prefix}{label}-r{rep}"
            base = bases[rep - 1]
            kw = dict(extra(rep)) if extra else {}
            if reset:
                b.clock(base - 2500.0)
                if rep == 2:
                    b.emit_op("server", "take_scene_prep", args_str={"op": "perturb_fixture"}, read_num={"scene_ok_b": 1})
                b.clock(base - 1500.0)
                b.emit_op("server", "take_scene_prep", args_str={"op": "reset"}, read_num={"scene_ok_b": 1}, frame=_sf(base - 1500.0))
                b.clock(base - 1400.0)
                b.emit_op(
                    "server", "act_observe",
                    args_num={"center_x_m": 103.0, "center_z_m": 101.0, "radius_m": 30.0},
                    read_str={"adapter_ver": ADAPTER_VER, "backend_class": "DSBX_QA_ActorAdapterExp", "core_ver": b.probe_ver},
                    read_num={"backend_available_b": 1}, ncol=ACT_OBS_NCOL, scol=ACT_OBS_SCOL,
                    rows=_make_b6_obs_rows(fixture, skip_reset=(ctx["no_reset_b6"] and rep == 2 and stage == "S1")),
                    frame=_sf(base - 1400.0) + 3,
                )
            b.emit_pings(stage, rep, base, phases=("pre",))
            arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
                fixture, tid, stage, rep, base, mode=mode, origin=origin, epoch=b.epoch,
                allow_dmg_pre_b=1 if rep in (1, 3) else 0, go_delay_ms=delays[rep - 1],
                hold_ms=650.0 if (origin == "juego" and rep == 2) else 0.0, **kw,
            )
            b.scenario_rows.append(meta_r)
            b.scenario_rows.extend(stim_r)
            b.emit_take_jobs(tid, arm_r, srv_r, cli_r, mode=mode, arm_extra_s={"stop_inject": "none"})
            if mut == "peer_reiniciado_en_toma" and stage == "S1" and rep == 2:
                b.clock(base + 5500.0)
                b.emit_op("server", "take_scene_prep", args_str={"op": "restart_epoch"}, read_num={"srv_epoch": b.epoch + 1})
                b.epoch += 1
            b.emit_pings(stage, rep, base, phases=("post",))

    def s1_extra(rep):
        kw = {}
        if mut == "despachar_desfasado" and rep == 2:
            kw.update(actor2_dispatch_lag_ms=160.0, actor2_lag_ms=160.0)
        if mut == "jitter_gt_100ms" and rep == 2:
            kw.update(actor1_lag_ms=160.0)
        if mut == "fase_muestreo_desplazada" and rep == 3:
            kw.update(cam_advance_ms=150.0)
        if mut == "peer_reiniciado_en_toma" and rep == 2:
            kw.update(interrupt_at_ms=1200.0)
        if mut == "proteccion_retenida_al_salir" and rep == 1:
            kw.update(no_restore=True)
        if mut == "traza_cam_incompleta" and rep == 2:
            kw.update(drop_cam_window=(1000.0, 2000.0))
        if mut == "cam_desviada_b6" and rep == 2:
            kw.update(cam_dev=(0.85, 1050.0))
        return kw

    series("S1", "s1", [10000.0, 20000.0, 30000.0], "rpc", "web", reset=True, delays=s1_delays, extra=s1_extra)
    series("S1sel", "s1sel", [60000.0, 70000.0, 80000.0], "rpc", "web", delays=(0.0, 160.0, 0.0))
    series("S1c", "s1c", [100000.0, 110000.0, 120000.0], "common_time", "web", reset=True,
           extra=lambda rep: {"actor1_lag_ms": 160.0} if (mut == "jitter_gt_100ms" and rep == 2) else {})

    def s2_extra(rep):
        kw = {}
        if mut == "retraso_lectura_tecla_gt_1s":
            kw["key_delay_ms"] = 1250.0
        if mut == "gesto_pendiente_no_cancelado":
            kw["pending_not_cancelled"] = True
        return kw

    series("S2", "s2", [140000.0, 150000.0, 160000.0], "rpc", "juego", extra=s2_extra)
    series("S2c", "s2c", [170000.0, 180000.0, 190000.0], "common_time", "juego")
def _cut_begin(b, L):
    """Ultimo keepalive 200 de cada peer exactamente en L y corte real del puente de los dos peers."""
    b.clock(L)
    for peer in ("server", "client"):
        b.emit_keepalive(peer, L)
    b.emit_cut("server", "cut_start", L + 1.0)
    b.emit_cut("client", "cut_start", L + 1.5)
    b.clock(L + 2.0)


def _cut_end(b, L, end):
    b.clock(end)
    b.emit_cut("server", "cut_end", end)
    b.emit_cut("client", "cut_end", end + 0.5)
    b.cuts.extend([("server", L + 1.0, end), ("client", L + 1.5, end + 0.5)])


def _cut_windows(b, tid, stage, case, L):
    for peer in ("server", "client"):
        row = {
            "case_id": case, "kind": "cut_window", "last_ok_poll_h_ms": float(L), "last_ok_poll_tick_ms": float(L),
            "lease_ms": 3000.0, "peer": peer, "reconnect_poll_h_ms": None, "reconnect_poll_tick_ms": None,
            "stage": stage, "take_id": tid,
        }
        b.scenario_rows.append(row)
        b.cut_rows.append(row)


def _emit_s3a(b, ctx):
    prefix = ctx["prefix"]
    b.clock(195000.0)
    for err in ("cam_not_ready", "actor_incapable", "no_director"):
        b.emit_op("server", "take_arm", args_str={"mode": "rpc", "take_id": f"{prefix}err-{err}"}, status="error",
                  reason=err, read_str={"err": err})

    # Rama 1 de conn_drop (sin efectos): GO debido a los 3400 ms del ultimo poll 200; el lease ya vencio.
    L = 210000.0
    tid = prefix + "cdrop1"
    mk = _Mk(L - 1000.0, tid)
    _emit_take_meta(b, tid, "S3a", "conn_drop_no_effects", 1, allow_dmg_pre_b=1)
    _cut_windows(b, tid, "S3a", "conn_drop_no_effects", L)
    _cut_begin(b, L)
    arm = [mk.S(L - 100.0, "arm_ready", so="armada", v1=1, v2=1.0, v3=2)]
    srv = mk.directors(L + 500.0, L + 2500.0, step=1000.0, allow=0)
    srv += mk.terminal(L + 3010.0, "parada:hombre_muerto", lease_age=3010.0, dtsum=0.0)
    srv.append(mk.S(L + 3100.0, "rpc_emit", "TAKE_STATE", "blocked_lease", v1=3100.0, v2=0))
    srv += mk.directors(L + 3100.0, L + 3300.0, step=200.0, allow=1, so="parada:hombre_muerto")
    cli = [mk.fs(L + 500.0), mk.fs(L + 1500.0), mk.fs(L + 2500.0)]
    cli.append(mk.C(L + 3030.0, "cli_safety_exit", "lease_expired", aux_n=mk.lastf + 1, take_dt=3030.0))
    cli += [mk.fs(L + 3100.0), mk.fs(L + 3300.0)]
    _cut_end(b, L, L + 3500.0)
    b.emit_take_jobs(tid, arm, srv, cli, mode="common_time", arm_state="stopped", arm_reason="lease_expired",
                     arm_ticks=(L + 3005.0, L + 3010.0, L + 3012.0))

    # Rama 2 (interrupcion tras efectos): GO a los 1500 ms del ultimo poll 200, con efectos reales.
    L = 220000.0
    tid = prefix + "cdrop2"
    mk = _Mk(L - 1000.0, tid)
    _emit_take_meta(b, tid, "S3a", "conn_drop_after_effects", 2, allow_dmg_pre_b=1)
    _cut_windows(b, tid, "S3a", "conn_drop_after_effects", L)
    _cut_begin(b, L)
    arm = mk.arm(L + 1500.0)
    srv = mk.directors(L + 1500.0, L + 3000.0, step=500.0, allow=0)
    srv += mk.terminal(L + 3010.0, "parada:hombre_muerto", lease_age=3010.0, allow_post=1, dtsum=1510.0)
    srv.append(mk.S(L + 3100.0, "rpc_emit", "TAKE_STATE", "blocked_lease", v1=3100.0, v2=0))
    srv += mk.directors(L + 3100.0, L + 3300.0, step=200.0, allow=1, so="parada:hombre_muerto")
    cli = [mk.C(L + 1505.0, "go_recv", "rpc_go", aux_n=_sf(L + 1500.0)), mk.C(L + 1506.0, "go_deliver", "delivered", aux_n=_sf(L + 1500.0))]
    t = L + 1510.0
    while t <= L + 3020.0:
        cli.append(mk.fs(t, active=1, take_dt=t - L - 1500.0))
        t += 90.0
    cli.append(mk.C(L + 3030.0, "cli_safety_exit", "lease_expired", aux_n=mk.lastf + 1, take_dt=3030.0))
    cli += [mk.fs(L + 3100.0), mk.fs(L + 3190.0), mk.fs(L + 3300.0)]
    _cut_end(b, L, L + 3500.0)
    b.emit_take_jobs(tid, arm, srv, cli, arm_state="stopped", arm_reason="lease_expired",
                     arm_ticks=(L + 3005.0, L + 3010.0, L + 3012.0))

    for i, (case, label) in enumerate((("stop_before_go", "s3a1"), ("double_stop_at_go", "s3a2"), ("stop_at_600ms", "s3a3"))):
        base = 230000.0 + 3000.0 * i
        tid = prefix + label
        mk = _Mk(base, tid)
        _emit_take_meta(b, tid, "S3a", case, 3 + i)
        arm = [mk.S(base + 50.0, "arm_ready", so="armada", v1=1, v2=1.0, v3=2)] if case == "stop_before_go" else mk.arm(base + 100.0)
        srv = mk.directors(base + 150.0, base + 400.0, step=250.0) + mk.terminal(base + 600.0, "parada:web", dtsum=600.0)
        b.clock(base + 10.0)
        b.emit_take_jobs(tid, arm, srv, [], skip_cli=True)
        for _n in range(2 if case == "double_stop_at_go" else 1):
            b.emit_op(
                "server", "take_stop", args_str={"take_id": tid, "origin": "web"},
                read_str={"take_state": "parada", "take_origin": "web"},
                read_num={"srv_frame": _sf(base + 600.0), "srv_tick_ms": base + 600.0, "dtsum_ms": 600.0, "take_dtsum_ms": 600.0,
                          "transitions_n": 1, "restorations_n": 1, "allow_dmg_post_b": 1, "pending_cues_n": 0,
                          "exp_emote_req_id_n": 0, "future_cues_fired_n": 0},
            )


GUARDS = (
    ("guard_a", "old_take_same_epoch", "guarda"),
    ("guard_b", "other_epoch", "guardb"),
    ("guard_c1", "other_director_c1", "guardc1"),
    ("guard_c2", "other_director_c2", "guardc2"),
)


def _emit_s3b(b, ctx):
    prefix = ctx["prefix"]
    b.clock(240000.0)
    for blocker in ("menu", "chat", "none"):
        b.emit_op(
            "client", "take_cam_prep", args_str={"op": "set_ui_blocker", "ui_blocker": blocker},
            read_num={"chat_open_b": 1 if blocker == "chat" else 0, "menu_open_b": 1 if blocker == "menu" else 0},
        )
    tid = prefix + "nokeys"
    mk = _Mk(241000.0, tid)
    _emit_take_meta(b, tid, "S3b", "no_take_keys", 0)
    cli = [mk.C(241100.0 + 100.0 * i, "key_edge", d, aux_n=0) for i, d in enumerate(("ignored_no_take", "ignored_menu", "ignored_chat"))]
    b.emit_take_jobs(tid, [], [], cli, skip_arm=True, skip_srv=True)

    prior = prefix + "prior"
    base = 245000.0
    mk = _Mk(base, prior)
    _emit_take_meta(b, prior, "S3b", "prior_terminal_same_epoch", 5)
    srv = mk.directors(base + 150.0, base + 400.0, step=250.0) + mk.terminal(base + 600.0, "parada:web", dtsum=600.0)
    b.emit_take_jobs(prior, mk.arm(base + 100.0), srv, [], skip_cli=True)

    for i, (case, rej_case, label) in enumerate(GUARDS):
        rep = i + 1
        base = 250000.0 + 10000.0 * i
        tid = prefix + label
        mk = _Mk(base, tid)
        Rk = base + 1500.0
        pair_tid = prior if case == "guard_a" else tid
        attempts = [Rk] if case == "guard_a" else [Rk, Rk + 260.0]
        decision = "repeat_terminal" if case == "guard_a" else "rejected"
        req_epoch = 7 if case == "guard_b" else b.epoch

        b.emit_pings("S3b", rep, base, phases=("pre",))
        arm = mk.arm(base + 100.0)
        srv = mk.directors(base + 150.0, base + 3000.0, step=500.0, allow=0)
        srv += [mk.S(t, "rpc_emit", "TAKE_STATE", "sent", v1=40.0, v2=1) for t in (base + 108.0, base + 608.0, base + 1108.0, base + 1608.0, base + 2108.0)]
        for n, t in enumerate(attempts):
            srv.append(mk.S(t + 10.0, "key_rpc", pair_tid, decision, v1=req_epoch, v2=n, v3=b.epoch))
        srv += mk.terminal(base + 3020.0, "parada:web")

        cli = [mk.fs(base - 300.0), mk.C(base + 105.0, "go_recv", "rpc_go", aux_n=_sf(base + 100.0)),
               mk.C(base + 110.0, "go_deliver", "delivered", aux_n=_sf(base + 100.0))]
        press = Rk - 10.0
        edge_done = False
        t = base + 120.0
        while t <= Rk + 40.0:
            bits = 0
            if not edge_done and t >= press:
                bits, edge_done = 1, True
            cli.append(mk.fs(t, active=1, bits=bits))
            t += 90.0
        cli.append(mk.C(press, "key_edge", "press_accepted", aux_n=1))
        for n, t_att in enumerate(attempts):
            cli.append(mk.C(t_att - 5.0, "rpc_stop_sent", pair_tid, aux_n=n))
        if case == "guard_a":
            cli.append(mk.C(Rk + 30.0, "ack_recv", "repeat_ack", ack_req_epoch_n=b.epoch, ack_req_take_id=prior,
                            ack_req_state="parada", ack_req_origin="web", ack_resp_class="repeat_terminal",
                            ack_cur_epoch_n=b.epoch, ack_cur_take_id=tid, ack_cur_state="rodando", ack_cur_origin="rpc", aux_n=2))
        t = base + 120.0
        cli.append(mk.state_recv(t, "rodando", "rpc", 2, epoch=b.epoch))
        for k in range(1, 6):
            cli.append(mk.state_recv(base + 120.0 + 500.0 * k, "rodando", "rpc", 2, epoch=b.epoch))
        t = Rk + 60.0
        while t <= base + 3200.0:
            cli.append(mk.fs(t, active=0, yaw=14.5 if t >= Rk + 120.0 else 10.0))
            t += 90.0
        cli.append(mk.state_recv(base + 3050.0, "parada", "web", 3, epoch=b.epoch))

        _emit_take_meta(b, tid, "S3b", case, rep, contemp_yaw_ref_deg=10.0, allow_dmg_pre_b=1, h_start_ms=base)
        _emit_stim(b, tid, "S3b", case, "key_press", press, key="kF9")
        for off in (120.0, 160.0):
            _emit_stim(b, tid, "S3b", case, "look_pulse", Rk + off, dx_px=40, sign=1)
        _emit_stim(b, tid, "S3b", case, "web_stop", base + 3000.0)
        b.scenario_rows.append(
            {"case_id": rej_case, "cli_tick_ms": Rk, "guard_take_id": tid, "h_ms": Rk, "kind": "key_rejection",
             "payload_sender_id": "", "reg_engine_uid": "", "sender_engine_uid": "", "srv_tick_ms": Rk + 10.0,
             "stage": "S3b", "take_id": tid}
        )
        b.emit_take_jobs(tid, arm, srv, cli, arm_extra_s={"stop_inject": "none"})
        b.clock(Rk + 300.0)
        reg, snd, pay = "", "", ""
        if case in ("guard_c1", "guard_c2"):
            reg, snd, pay = "qa-uid-dir-other", "qa-uid-real-0001", "dir_main" if case == "guard_c1" else "dir_other"
        _srv_status_op(b, tid, epoch=b.epoch, rejected=0 if case == "guard_a" else len(attempts), reg=reg, sender=snd, payload=pay)
        _cli_status_op(b, tid, epoch=b.epoch, seq=2)
        b.emit_pings("S3b", rep, base, phases=("post",))
def _key_take(b, ctx, label, case, rep, base, *, flow, inject, arm_n=None, stim_offset=1500.0, origin="juego", ping=False):
    """Toma de S3c con parada por tecla (un `_build_positive_take_rows` corto) y sus ordenes crudas."""
    prefix = ctx["prefix"]
    tid = prefix + label
    if ping:
        b.emit_pings("S3c", rep, base, phases=("pre",))
    arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
        ctx["fixture"], tid, "S3c", rep, base, mode="rpc", origin=origin, epoch=b.epoch, stim_offset=stim_offset,
        key_flow=flow, post_steps=4,
    )
    meta_r["case_id"] = case
    for s in stim_r:
        s["case_id"] = case
    b.scenario_rows.append(meta_r)
    b.scenario_rows.extend(stim_r)
    b.emit_take_jobs(tid, arm_r, srv_r, cli_r, arm_extra_s={"stop_inject": inject}, arm_extra_n=arm_n)
    if ping:
        b.emit_pings("S3c", rep, base, phases=("post",))
    return tid, srv_r, cli_r


def _emit_cut_case(b, ctx, case, label, rep, L, kind):
    prefix = ctx["prefix"]
    tid = prefix + label
    mk = _Mk(L - 1000.0, tid)
    _emit_take_meta(b, tid, "S3c", case, rep, contemp_yaw_ref_deg=10.0, allow_dmg_pre_b=1, lease_ms=3000.0, h_start_ms=L - 1000.0)
    _cut_windows(b, tid, "S3c", case, L)
    _cut_begin(b, L)
    arm = mk.arm(L - 900.0)
    srv = mk.directors(L - 800.0, L + (1500.0 if kind == "before" else 2800.0), step=500.0, allow=0)
    cli = [mk.fs(L - 950.0), mk.C(L - 895.0, "go_recv", "rpc_go", aux_n=_sf(L - 900.0)),
           mk.C(L - 890.0, "go_deliver", "delivered", aux_n=_sf(L - 900.0)),
           mk.state_recv(L - 880.0, "rodando", "rpc", 2, epoch=b.epoch)]
    t = L - 880.0
    last_active = L + (1500.0 if kind == "before" else 3020.0)
    press = L + 1500.0
    edge_done = False
    while t <= last_active:
        bits = 0
        if kind == "before" and not edge_done and t >= press + 5.0:
            bits, edge_done = 1, True
        cli.append(mk.fs(t, active=1, bits=bits))
        t += 90.0
    if kind == "before":
        srv.append(mk.S(L + 1515.0, "key_rpc", tid, "accepted", v1=b.epoch, v2=0, v3=b.epoch))
        srv.append(mk.S(L + 1535.0, "rpc_emit", "ACK", "sent", v1=1535.0, v2=1))
        srv += mk.terminal(L + 1525.0, "parada:juego", lease_age=1525.0, dtsum=2525.0)
        srv += mk.directors(L + 1600.0, L + 3300.0, step=500.0, allow=1, so="parada:juego")
        srv += mk.directors(L + 3100.0, L + 3300.0, step=200.0, allow=1, so="parada:juego")
        cli.append(mk.C(press + 5.0, "key_edge", "press_accepted", aux_n=1))
        cli.append(mk.C(press + 6.0, "rpc_stop_sent", tid, aux_n=0))
        cli.append(mk.C(press + 20.0, "cli_safety_exit", "key_press", aux_n=mk.lastf + 1, take_dt=2520.0))
        cli.append(mk.C(press + 45.0, "ack_recv", "stop_ack", ack_req_epoch_n=b.epoch, ack_req_take_id=tid,
                        ack_req_state="parada", ack_req_origin="juego", ack_resp_class="first_terminal",
                        ack_cur_epoch_n=b.epoch, ack_cur_take_id=tid, ack_cur_state="parada", ack_cur_origin="juego", aux_n=3))
        t = press + 40.0
        while t <= L + 3450.0:
            cli.append(mk.fs(t, active=0))
            t += 90.0
        _emit_stim(b, tid, "S3c", case, "key_press", press, key="kF9")
    else:
        srv += mk.terminal(L + 3010.0, "parada:hombre_muerto", lease_age=3010.0, dtsum=4010.0)
        srv.append(mk.S(L + 3100.0, "rpc_emit", "TAKE_STATE", "blocked_lease", v1=3100.0, v2=0))
        srv += mk.directors(L + 3100.0, L + 3300.0, step=200.0, allow=1, so="parada:hombre_muerto")
        cli.append(mk.C(L + 3030.0, "cli_safety_exit", "lease_expired", aux_n=mk.lastf + 1, take_dt=4030.0))
        t = L + 3040.0
        while t <= L + 3450.0:
            cli.append(mk.fs(t, active=0, yaw=14.5 if t >= L + 3200.0 else 10.0))
            t += 90.0
        _emit_stim(b, tid, "S3c", case, "look_pulse", L + 3200.0, dx_px=40, sign=1)
        if kind == "after":
            cli.append(mk.C(L + 3400.0, "key_edge", "ignored_no_take", aux_n=0))
            _emit_stim(b, tid, "S3c", case, "key_press", L + 3400.0, key="kF9")
    _cut_end(b, L, L + 3500.0)
    ticks = (L + 1530.0, L + 1535.0, L + 1537.0) if kind == "before" else (L + 3005.0, L + 3010.0, L + 3012.0)
    b.emit_take_jobs(tid, arm, srv, cli, arm_state="stopped", arm_reason="lease_expired" if kind != "before" else "",
                     arm_ticks=ticks)
    if kind != "before":
        b.clock(L + 3600.0)
        _srv_status_op(b, tid, state="parada", origin="hombre_muerto", epoch=b.epoch, transitions=1,
                       term_frame=_sf(L + 3010.0), term_lease=3010.0)
        _cli_status_op(b, tid, state="parada", origin="hombre_muerto", epoch=b.epoch, seq=3, cam_active=0)


def _plain_take(b, ctx, label, case, rep, base, *, retry_sent=(), state_epoch=None, gen_status=False, ack_for=None):
    """Toma armada sin parada (se queda rodando): armado, observadores y, si procede, reintentos de parada en vuelo."""
    prefix = ctx["prefix"]
    tid = prefix + label
    mk = _Mk(base, tid)
    ep = b.epoch if state_epoch is None else state_epoch
    _emit_take_meta(b, tid, "S3c", case, rep, contemp_yaw_ref_deg=10.0, allow_dmg_pre_b=1, h_start_ms=base)
    arm = mk.arm(base + 100.0)
    srv = mk.directors(base + 150.0, base + 2000.0, step=500.0, allow=0)
    cli = [mk.state_recv(base + 120.0, "rodando", "rpc", 2, epoch=ep)]
    for n, off in enumerate(retry_sent):
        cli.append(mk.C(base + off, "rpc_stop_sent", tid, aux_n=n))
    b.emit_take_jobs(tid, arm, srv, cli, arm_extra_s={"stop_inject": "none"})
    return tid, mk


def _emit_s3c(b, ctx):
    prefix = ctx["prefix"]
    mut = ctx["mutant"]
    b.clock(399000.0)
    _key_take(b, ctx, "dreq", "drop_first_req", 1, 400000.0, flow=((0, 1), (1,), (1,)), inject="drop_first_req", ping=True)
    _key_take(b, ctx, "dack", "drop_first_ack", 2, 410000.0, flow=((0, 1), (0, 1), (1,)), inject="drop_first_ack")
    _key_take(b, ctx, "sim", "simul_key_and_web", 3, 420000.0, flow=((0,), (0,), (0,)), inject="none")
    b.emit_op("server", "take_stop", args_str={"take_id": prefix + "sim", "origin": "web"},
              read_str={"take_state": "parada", "take_origin": "juego"},
              read_num={"transitions_n": 1, "restorations_n": 1, "allow_dmg_post_b": 1, "pending_cues_n": 0,
                        "exp_emote_req_id_n": 0, "future_cues_fired_n": 0})

    # GO retenido liberado tras pulsar la tecla
    base = 425000.0
    tid = prefix + "hgo"
    mk = _Mk(base, tid)
    _emit_take_meta(b, tid, "S3c", "held_go_after_key", 4, contemp_yaw_ref_deg=10.0)
    cli = [mk.fs(base + 100.0 + 90.0 * i) for i in range(4)]
    cli.append(mk.C(base + 450.0, "key_edge", "press_accepted", aux_n=1))
    cli.append(mk.C(base + 500.0, "go_recv", "rpc_go", aux_n=_sf(base + 100.0)))
    for i in range(4):
        cli.append(mk.fs(base + 500.0 + 90.0 * i))
    cli.append(mk.C(base + 900.0, "go_deliver", "delivered", aux_n=_sf(base + 100.0)))
    for i in range(5):
        cli.append(mk.fs(base + 910.0 + 90.0 * i, active=1 if mut == "go_tardio_reactiva_cam" else 0))
    b.emit_take_jobs(tid, mk.arm(base + 100.0), [], cli, skip_srv=True)
    b.clock(base + 1500.0)
    b.emit_op("client", "take_cam_prep", args_str={"op": "release_held_go"}, read_num={"late_go_ignored_n": 1})

    # NOTIFY viejo de A entregado con B rodando
    base = 430000.0
    tid_a = prefix + "sta"
    mk = _Mk(base, tid_a)
    _emit_take_meta(b, tid_a, "S3c", "stale_notify_take_a", 5)
    b.emit_take_jobs(tid_a, mk.arm(base + 100.0), mk.terminal(base + 600.0, "parada:web", dtsum=600.0), [], skip_cli=True)
    base_b = 435000.0
    arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
        ctx["fixture"], prefix + "stb", "S3c", 6, base_b, mode="rpc", origin="web", epoch=b.epoch, stim_offset=2500.0, post_steps=4)
    meta_r["case_id"] = "stale_notify_take_b"
    b.scenario_rows.append(meta_r)
    b.emit_take_jobs(prefix + "stb", arm_r, srv_r, cli_r)
    b.clock(base_b + 900.0)
    b.emit_op("client", "take_cam_prep", args_str={"op": "deliver_stale_msg", "take_id": tid_a},
              read_num={"sandbox_cam_active_b": 1, "stale_msg_ignored_n": 4})
    _cli_status_op(b, prefix + "stb", epoch=b.epoch, seq=2)

    # ack2 (acuse retenido) y new
    base_a2 = 440000.0
    tid_a2, _s, _c = _key_take(b, ctx, "ack2", "ack2", 7, base_a2, flow=((0,), (0,), ()), inject="hold_all_ack",
                               arm_n={"post_stop_watch_ms": 0}, stim_offset=1500.0)
    base_new = 445000.0
    arm_r, srv_r, cli_r, stim_r, meta_r = _build_positive_take_rows(
        ctx["fixture"], prefix + "new", "S3c", 8, base_new, mode="rpc", origin="web", epoch=b.epoch, stim_offset=2500.0, post_steps=4)
    meta_r["case_id"] = "new"
    cli_r.append(_make_cli_row(_cf(base_new + 800.0), base_new + 800.0, 800.0, 700.0, "ack_recv", "late_ack_from_ack2",
                               ack_req_epoch_n=b.epoch, ack_req_take_id=prefix + "ack2", ack_req_state="parada",
                               ack_req_origin="juego", ack_resp_class="first_terminal", ack_cur_epoch_n=b.epoch,
                               ack_cur_take_id=prefix + "new", ack_cur_state="rodando", ack_cur_origin="rpc", aux_n=2))
    b.scenario_rows.append(meta_r)
    b.emit_take_jobs(prefix + "new", arm_r, srv_r, cli_r)
    b.clock(base_new + 900.0)
    b.emit_op("server", "take_scene_prep", args_str={"op": "release_held_ack", "take_id": prefix + "ack2"},
              read_num={"held_acks_n": 0, "ack_sent_n": 1})
    _cli_status_op(b, prefix + "new", epoch=b.epoch, seq=2)

    # reinicio de epoch logico con reintento en vuelo y el MISMO take_id completo en el epoch nuevo
    base = 450000.0
    tid_e, _mk1 = _plain_take(b, ctx, "edup", "epoch_dup_1", 9, base, retry_sent=(1005.0, 1255.0))
    b.clock(base + 2200.0)
    b.emit_op("server", "take_scene_prep", args_str={"op": "restart_epoch"}, read_num={"srv_epoch": b.epoch + 1})
    b.epoch += 1
    base2 = 455000.0
    _plain_take(b, ctx, "edup", "epoch_dup_2", 10, base2)
    b.clock(base2 + 1000.0)
    _srv_status_op(b, tid_e, epoch=b.epoch, transitions=0)

    # hombre muerto, tecla antes y tecla despues de vencer el lease
    _emit_cut_case(b, ctx, "cut_nokey", "cutnk", 11, 460000.0, "nokey")
    _emit_cut_case(b, ctx, "cut_before", "cutbf", 12, 470000.0, "before")
    _emit_cut_case(b, ctx, "cut_after", "cutaf", 13, 480000.0, "after")

    # S3d: reinicio real del proceso servidor, mismo take_id completo en el epoch nuevo
    base = 490000.0
    tid_p, _mk2 = _plain_take(b, ctx, "pdup", "procdup_1", 14, base, retry_sent=(1005.0, 1255.0))
    b.clock(base + 2200.0)
    b.emit_hello("server", "srv-inst-2")
    b.epoch += 1
    base2 = 495000.0
    _plain_take(b, ctx, "pdup", "procdup_2", 15, base2)
    b.clock(base2 + 1000.0)
    _srv_status_op(b, tid_p, epoch=b.epoch, transitions=0)
_CORE_CACHE: dict = {}


def _scan_reconnect(bridge_rows, peer, after_t):
    for r in bridge_rows:
        if r.get("peer") == peer and r.get("ev") in ("poll", "keepalive") and r.get("http", 200) == 200 and r["t_ms"] > after_t:
            return r["t_ms"], r["tick_s"] * 1000.0
    return None, None


def _build_core(mutant, op_nonce, s1_delays, no_reset_b6):
    key = (mutant, op_nonce, tuple(s1_delays), bool(no_reset_b6))
    if key in _CORE_CACHE:
        return _CORE_CACHE[key]
    root = f03_common.REPO_ROOT
    harness = gate_core.git_harness(repo_root=root)
    git_head = harness["git_head"]
    probe_stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=root)
    fixture_path = QA_DIR / "fixtures" / "s_toma_fixture.json"
    fixture = gate_core.read_json(fixture_path)
    fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()

    b = _SyntheticTraceBuilder(fixture, git_head, probe_stamp, op_nonce=op_nonce)
    ctx = {"fixture": fixture, "prefix": "1a2b3c4d-", "mutant": mutant, "s1_delays": tuple(s1_delays),
           "no_reset_b6": bool(no_reset_b6)}
    _emit_s0(b, ctx)
    _emit_main_series(b, ctx)
    _emit_s3a(b, ctx)
    _emit_s3b(b, ctx)
    _emit_s3c(b, ctx)
    b.finalize_bridge(b.cuts)
    for row, (peer, _s, end) in zip(b.cut_rows, b.cuts):
        h, tick = _scan_reconnect(b.bridge_rows, peer, end)
        row["reconnect_poll_h_ms"] = h
        row["reconnect_poll_tick_ms"] = tick

    manifest = {
        "argv": ["m1_gate.py", "spike", "S-toma", "--both", "--build", "offline"],
        "both": True, "build": "offline", "ended_utc": "2026-11-15T08:00:10Z", "faults": [mutant] if mutant else [],
        "harness": harness, "id": "S-toma",
        "identity": {
            "build": "offline", "git_dirty": harness.get("git_dirty"), "git_head": git_head,
            "params": {
                "adapter_ver_expected": ADAPTER_VER, "fixture_sha256": fixture_sha,
                "hold_ms": gate_core.DEFAULT_HOLD_MS, "lease_ms": gate_core.DEFAULT_LEASE_MS,
                "probe_budget_log_poll_ms": f03_common.PROBE_BUDGET_LOG_POLL_MS,
                "probe_budget_retry_ms": f03_common.PROBE_BUDGET_RETRY_MS,
                "retry_ms": gate_core.DEFAULT_RETRY_MS, "seed": gate_core.DEFAULT_SEED, "ttl_ms": gate_core.DEFAULT_TTL_MS,
                "wire_cap": int(wire.WIRE_CAP),
            },
            "pbo_sha256": None, "peer_builds": {"client": "offline", "server": "offline"}, "probe_stamp": probe_stamp,
        },
        "kind": "spike",
        "params": {
            "hold_ms": gate_core.DEFAULT_HOLD_MS, "lease_ms": gate_core.DEFAULT_LEASE_MS, "port": 51234,
            "retry_ms": gate_core.DEFAULT_RETRY_MS, "run_id": "1a2b3c4d", "seed": gate_core.DEFAULT_SEED,
            "ttl_ms": gate_core.DEFAULT_TTL_MS,
        },
        "schema": gate_core.SCHEMA_MANIFEST, "started_utc": "2026-11-15T08:00:00Z",
    }
    core = {"manifest": manifest, "bridge": b.bridge_rows, "scenario": b.scenario_rows, "op_map": b.op_map}
    _CORE_CACHE[key] = core
    return core


def build_healthy_part(
    part_dir: Path,
    *,
    mutant: str | None = None,
    post_mutate=None,
    op_nonce: str = "a1b2c3d4e5f60718",
    s1_delays=(0.0, 0.0, 0.0),
    no_reset_b6: bool = False,
) -> Path:
    """Escribe una carpeta de parte sintetica sana (o con la inyeccion de uno de los 11 mutantes)."""
    pdir = Path(part_dir)
    samples_dir = pdir / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    core = copy.deepcopy(_build_core(mutant, op_nonce, s1_delays, no_reset_b6))
    manifest, bridge_rows, scenario_rows = core["manifest"], core["bridge"], core["scenario"]
    if callable(post_mutate):
        post_mutate(manifest, bridge_rows, scenario_rows)

    gate_core.write_json(pdir / "manifest.json", manifest)
    gate_core.write_json(pdir / "part.json", {"op_map": core["op_map"], "op_nonce": op_nonce, "part": pdir.name, "spike_id": "S-toma"})
    if mutant:
        gate_core.write_json(
            pdir / "injection.json",
            {"applied": True, "kind": "synthetic_fault", "mutant": mutant, "observable_effect": {"fault_injected": mutant},
             "target": "both", "when_h_ms": 100.0},
        )
    with (samples_dir / "bridge.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in bridge_rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    with (samples_dir / "scenario.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for r in scenario_rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
    return pdir


# --- utilidades para perturbar la evidencia (siempre sobre copias en memoria) ---
def _read_unp(ev):
    read = (ev.get("result") or {}).get("read") or {}
    if not all(k in read for k in wire.PAYLOAD_KEYS):
        return None
    return wire.unpack_payload(read)


def _repack(ev, unp):
    rep = wire.pack_payload(unp["str"], unp["num"], unp["ncol"], unp["scol"], unp["rows"])
    rep["has"] = ["payload"]
    ev["result"]["read"] = rep


def edit_job_rows(bridge_rows, job_prefix, fn):
    """Aplica `fn(rows) -> rows|None` a las filas de cada pagina `job_read` de los trabajos cuyo id empieza por `job_prefix`."""
    n = 0
    for ev in bridge_rows:
        if ev.get("ev") != "result":
            continue
        unp = _read_unp(ev)
        if unp is None or not unp["str"].get("job", "").startswith(job_prefix) or "reason" not in unp["str"]:
            continue
        out = fn(unp["rows"])
        if out is not None:
            unp["rows"] = out
        _repack(ev, unp)
        n += 1
    return n


def edit_ops(bridge_rows, verb, args_pred, fn):
    """Aplica `fn(unp)` al `read` de cada orden de `verb` cuyo `args` cumple `args_pred(args_str_dict)`."""
    args_by_op = {}
    for ev in bridge_rows:
        if ev.get("ev") == "enq" and ev.get("verb") == verb:
            a = wire.unpack_payload(ev["args"])
            args_by_op[ev["op_id"]] = a["str"]
    n = 0
    for ev in bridge_rows:
        if ev.get("ev") != "result" or ev.get("op_id") not in args_by_op:
            continue
        if not args_pred(args_by_op[ev["op_id"]]):
            continue
        unp = _read_unp(ev)
        if unp is None:
            continue
        fn(unp)
        _repack(ev, unp)
        n += 1
    return n


def _row_of(rows, **match):
    return [r for r in rows if all(r.get(k) == v for k, v in match.items())]


def _verdict_checks(verdict):
    return {c["id"]: c for c in verdict["checks"]}


def _assert_not_pass(case, verdict, check_id=None, reason_part=None):
    case.assertIn(verdict["exit_code"], (1, 2), verdict)
    case.assertNotEqual(verdict["verdict"], "PASA")
    if check_id is not None:
        chk = _verdict_checks(verdict).get(check_id)
        case.assertIsNotNone(chk, verdict)
        case.assertNotEqual(chk["status"], "pass", verdict)
        if reason_part is not None:
            case.assertIn(reason_part, chk["reason"], verdict)
    elif reason_part is not None:
        case.assertTrue(any(reason_part in r for r in verdict["reasons"]), verdict)


def _job_pages(bridge_rows, job_prefix):
    out = []
    for ev in bridge_rows:
        if ev.get("ev") != "result":
            continue
        unp = _read_unp(ev)
        if unp is None or "reason" not in unp["str"] or not unp["str"].get("job", "").startswith(job_prefix):
            continue
        out.append((ev, unp))
    return out


def edit_job(bridge_rows, job_prefix, fn):
    """`fn(todas_las_filas) -> filas nuevas` sobre todas las filas del trabajo, reparticion en las paginas existentes."""
    pages = _job_pages(bridge_rows, job_prefix)
    assert pages, f"sin trabajo {job_prefix}"
    allrows = [r for _ev, unp in pages for r in unp["rows"]]
    new = fn(allrows)
    for i, (ev, unp) in enumerate(pages):
        unp["rows"] = new[4 * i: 4 * i + 4] if i < len(pages) - 1 else new[4 * i:]
        _repack(ev, unp)


def job_id_of(bridge_rows, verb, take_id, nth=0):
    """Id del n-esimo trabajo `verb` cuyo `take_id` es `take_id` (de la orden cruda de arranque)."""
    found = []
    args_by_op = {}
    for ev in bridge_rows:
        if ev.get("ev") == "enq" and ev.get("verb") == verb:
            args_by_op[ev["op_id"]] = wire.unpack_payload(ev["args"])["str"]
    for ev in bridge_rows:
        if ev.get("ev") == "result" and ev.get("op_id") in args_by_op:
            if args_by_op[ev["op_id"]].get("take_id") == take_id:
                unp = _read_unp(ev)
                found.append(unp["str"]["job"])
    return found[nth]


def drop_ops(bridge_rows, pred):
    """Quita del puente todas las filas de las ordenes cuyo (verb, args_str) cumple `pred`."""
    meta = {}
    for ev in bridge_rows:
        if ev.get("ev") == "enq":
            meta[ev["op_id"]] = (ev["verb"], wire.unpack_payload(ev["args"])["str"])
    kill = {oid for oid, (v, a) in meta.items() if pred(v, a)}
    bridge_rows[:] = [r for r in bridge_rows if r.get("op_id") not in kill]
    return len(kill)


def _tid(label):
    return "1a2b3c4d-" + label


def _healthy_verdict(**kw):
    with tempfile.TemporaryDirectory() as tmp:
        pdir = build_healthy_part(Path(tmp) / "run", **kw)
        return _evaluate(pdir)


def _eval_with(post_mutate, *, sources=None, **kw):
    with tempfile.TemporaryDirectory() as tmp:
        pdir = build_healthy_part(Path(tmp) / "run", post_mutate=post_mutate, **kw)
        return _evaluate(pdir, **({"sources": sources} if sources is not None else {}))


class TestSTomaOracleOffline(unittest.TestCase):
    """Suite de pruebas offline del oráculo de S-toma."""

    def assertNonPass(self, verdict, check_id=None, reason_part=None):
        _assert_not_pass(self, verdict, check_id, reason_part)

    def test_check_12_blind_evaluators_on_s_toma_eval(self):
        self.assertEqual(test_probe_static.check_12_blind_evaluators(QA_DIR), [])

    def test_healthy_part_passes_all_7_checks(self):
        verdict = _healthy_verdict()
        self.assertEqual(verdict["exit_code"], 0, verdict)
        self.assertEqual(verdict["verdict"], "PASA")
        checks_by_id = {c["id"]: c["status"] for c in verdict["checks"]}
        for cid in s_toma_eval.CHECK_IDS:
            self.assertEqual(checks_by_id.get(cid), "pass", f"{cid} no dio pass: {verdict}")
        self.assertEqual(verdict["metrics"]["channel"], "rpc")

    def test_healthy_evidence_contains_the_raw_observations_sol_found_missing(self):
        """La sana trae lo que produciria una implementacion honesta (BLOQ 1, 4, 5, 6, 11): no solo etiquetas."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            br = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            ops, jobs, _h, _p = s_toma_eval._reconstruct_ops_and_jobs(br)
            verbs = [(o["verb"], o["args_s"].get("op")) for o in ops]
            self.assertGreaterEqual(sum(1 for v, _o in verbs if v == "take_clock_ping"), 100)
            self.assertGreaterEqual(sum(1 for v, o in verbs if (v, o) == ("take_scene_prep", "reset")), 6)
            self.assertIn(("take_scene_prep", "restart_epoch"), verbs)
            self.assertTrue(any(j["take_id"] == _tid("edup") and j["gen"] == 2 for j in jobs.values()))
            self.assertTrue(any(j["take_id"] == _tid("pdup") and j["gen"] > 2 for j in jobs.values()))
            self.assertTrue(all(o["dup_raw"] is False for o in ops))
            keep = [r for r in br if r.get("ev") == "keepalive"]
            self.assertTrue(keep)
            tl = s_toma_eval._bridge_timeline(br)
            self.assertGreaterEqual(len(tl["cuts"]), 10)

    def test_tom_01_fallback_to_common_time_when_rpc_delivery_jitter_gt_100ms(self):
        """T9/BLOQ 6: el retraso de entrega se representa con la cola de entrega del cliente (relojes crudos intactos)."""
        verdict = _healthy_verdict(s1_delays=(0.0, 130.0, 0.0))
        self.assertEqual(verdict["exit_code"], 0, verdict)
        tom01 = _verdict_checks(verdict)["TOM-01"]
        self.assertEqual(tom01["observed"]["active_mode"], "common_time")
        self.assertEqual(verdict["metrics"]["channel"], "common_time")

    def test_t9_selected_channel_is_the_only_one_consumed_by_tom_02_04_05(self):
        def break_rpc_series(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r3')}",
                     lambda rows: [dict(r, v3=1.0) if (r["row_kind"] == "director_sample" and r["state_or_origin"] == "rodando") else r
                                   for r in rows])
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s2-r2')}",
                     lambda rows: [r for r in rows if r["row_kind"] != "take_terminal"])

                # canal rpc seleccionado: romper la serie common_time no afecta a TOM-02/04/05, romper rpc si.
        def break_ct_series(_m, bridge, _s):
            for label in ("s1c-r1", "s2c-r1"):
                edit_job(bridge, f"job-take_srv_observe_start-{_tid(label)}",
                         lambda rows: [r for r in rows if r["row_kind"] != "take_terminal"])

        v_ct_broken = _eval_with(break_ct_series)
        self.assertEqual(v_ct_broken["exit_code"], 0, v_ct_broken)
        v_rpc_broken = _eval_with(break_rpc_series)
        self.assertNonPass(v_rpc_broken)
        st = {c["id"]: c["status"] for c in v_rpc_broken["checks"]}
        self.assertNotEqual(st["TOM-02"], "pass", v_rpc_broken)
        # canal common_time seleccionado: romper la serie rpc (S1/S2) no afecta; romper S1c/S2c si.
        v2 = _eval_with(break_rpc_series, s1_delays=(0.0, 130.0, 0.0))
        self.assertEqual(v2["metrics"]["channel"], "common_time", v2)
        st2 = {c["id"]: c["status"] for c in v2["checks"]}
        for cid in ("TOM-02", "TOM-04", "TOM-05"):
            self.assertEqual(st2[cid], "pass", (cid, v2))
        v3 = _eval_with(break_ct_series, s1_delays=(0.0, 130.0, 0.0))
        st3 = {c["id"]: c["status"] for c in v3["checks"]}
        self.assertNotEqual(st3["TOM-02"], "pass", v3)

    def test_valid_rpc_series_passes_without_the_fallback_series(self):
        """T9: una serie rpc valida pasa aunque la de reserva falte (la reserva solo se consulta si rpc no cumple)."""
        def drop_fallback_takes(_m, bridge, scen):
            scen[:] = [r for r in scen if not (r.get("kind") == "take_meta" and r.get("stage") in ("S1sel", "S1c", "S2c"))]

        verdict = _eval_with(drop_fallback_takes)
        self.assertEqual(verdict["exit_code"], 0, verdict)
        self.assertEqual(verdict["metrics"]["channel"], "rpc")

    def test_invariance_under_coherent_op_id_renaming_without_part_or_injection_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            v_orig = _evaluate(pdir)
            (pdir / "part.json").unlink(missing_ok=True)
            (pdir / "injection.json").unlink(missing_ok=True)
            b_path = pdir / "samples" / "bridge.jsonl"
            rows = f03_common.read_jsonl(b_path)
            rename_map = {}
            for ev in rows:
                oid = ev.get("op_id")
                if isinstance(oid, str) and oid not in rename_map:
                    rename_map[oid] = f"renamed-opaque-{len(rename_map) + 1:05d}"
            for ev in rows:
                if isinstance(ev.get("op_id"), str):
                    ev["op_id"] = rename_map[ev["op_id"]]
                if isinstance(ev.get("op_ids"), list):
                    ev["op_ids"] = [rename_map.get(x, x) for x in ev["op_ids"]]
                if isinstance(ev.get("result"), dict) and isinstance(ev["result"].get("op_id"), str):
                    ev["result"]["op_id"] = rename_map[ev["result"]["op_id"]]
            with b_path.open("w", encoding="utf-8", newline="\n") as fh:
                for r in rows:
                    fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")
            v_renamed = _evaluate(pdir)
            self.assertEqual(v_orig["exit_code"], v_renamed["exit_code"])
            self.assertEqual(v_orig["checks"], v_renamed["checks"])

    def test_invariance_under_24_char_qa_fault_in_poll_body_len(self):
        order_healthy = {
            "args": wire.pack_payload(scalars_str={"op": "verify", "qa_fault": wire.format_qa_fault(None)}),
            "inst": "srv-1", "issued_ms": 100.0, "op_id": "op-1", "ttl_ms": 5000, "verb": "take_scene_prep",
        }
        order_mutant = {
            "args": wire.pack_payload(scalars_str={"op": "verify", "qa_fault": wire.format_qa_fault("take_director_mortal")}),
            "inst": "srv-1", "issued_ms": 100.0, "op_id": "op-1", "ttl_ms": 5000, "verb": "take_scene_prep",
        }
        self.assertEqual(len(wire.poll_wire_bytes(order_healthy)), len(wire.poll_wire_bytes(order_mutant)))

    def test_invariance_when_wire_cap_changed_in_memory_uses_manifest_identity_params(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            orig_cap = wire.WIRE_CAP
            try:
                wire.WIRE_CAP = 500
                verdict = _evaluate(pdir)
                self.assertEqual(verdict["exit_code"], 0, verdict)
                self.assertEqual(verdict["metrics"]["wire_cap"], orig_cap)
            finally:
                wire.WIRE_CAP = orig_cap

    def test_worst_case_job_read_page_wire_bytes_under_wire_cap(self):
        worst_rows = [
            _make_cli_row(
                999999, 999999.999, 999999.999, 999999.999, "ack_recv", "repeat_terminal_detail_str",
                sandbox_cam_active_b=1, hud_hidden_b=1, quickbar_hide_flag_b=1, quickbar_widget_visible_b=0,
                cam_x_m=15360.1234, cam_y_m=512.5678, cam_z_m=15360.9876, cam_yaw_deg=-179.9876, cam_pitch_deg=-89.1234,
                cam_fov_deg=1.2345, ack_req_epoch_n=99, ack_cur_epoch_n=99, aux_n=99999,
                ack_req_take_id="1a2b3c4d-worst-case-01", ack_req_state="parada", ack_req_origin="hombre_muerto",
                ack_resp_class="repeat_terminal", ack_cur_take_id="1a2b3c4d-worst-case-02", ack_cur_state="rodando",
                ack_cur_origin="common_time",
            )
            for _ in range(4)
        ]
        packed = wire.pack_payload(
            scalars_str={"adapter_ver": ADAPTER_VER, "job": "job-take_cli_watch-9999", "reason": "", "state": "done"},
            scalars_num={"end_tick_ms": 999999.999, "onjobend_tick_ms": 999999.999, "page_n": 99, "pages_n": 100,
                         "released_tick_ms": 999999.999, "rows_total_n": 400},
            num_cols=CLI_NCOL, str_cols=CLI_SCOL, row_dicts=worst_rows,
        )
        packed["has"] = ["payload"]
        res_obj = {
            "done_ms": 999999.999, "dup": False, "frame_done": 999999, "frame_recv": 999998,
            "op_id": "a1b2c3d4e5f60718-9999", "read": packed, "reason": "", "recv_ms": 999999.0, "status": "done",
        }
        self.assertLess(len(wire.result_wire_bytes(res_obj)), wire.WIRE_CAP)

    def test_reference_camera_curve_is_independent_of_the_evaluator_function(self):
        """BLOQ 17: la curva de la sintetica sale de una formulacion distinta y coincide con la del evaluador."""
        fixture = gate_core.read_json(QA_DIR / "fixtures" / "s_toma_fixture.json")
        kfs = fixture["camera_path"]["keyframes"]
        for t in [0.0, 1.0, 250.0, 999.0, 1000.0, 1050.0, 1500.0, 2000.0, 2999.0, 3000.0, 3017.5, 3900.0, 4500.0, 5000.0]:
            ref = _ref_camera_position(kfs, t)
            ev = s_toma_eval.eval_catmull_rom_path(kfs, t)[0]
            for c in range(3):
                self.assertAlmostEqual(ref[c], ev[c], places=9, msg=f"t={t}")
        import inspect
        self.assertNotIn("eval_catmull_rom_path", inspect.getsource(_build_positive_take_rows))

    def test_neg_sol15_latency_decided_by_upper_bound_not_lower_bound(self):
        v = s_toma_eval._latency_verdict
        self.assertEqual(v("x", -11.0, 22.0)[0], "pass")
        self.assertEqual(v("x", 0.0, 500.0)[0], "pass")
        self.assertEqual(v("x", -5.0, 1500.0)[0], "missing")
        self.assertEqual(v("x", 1000.0, 1200.0)[0], "fail")
        self.assertEqual(v("x", -30.0, -10.0)[0], "fail")
        # la sana contiene intervalos honestos con cota inferior <= 0 y pasa
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            br = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            sc = f03_common.read_jsonl(pdir / "samples" / "scenario.jsonl")
            ops, jobs, _h, _p = s_toma_eval._reconstruct_ops_and_jobs(br)
            bundle = s_toma_eval._collect_take_bundles(ops, jobs, sc, s_toma_eval._bridge_timeline(br))
            key = s_toma_eval._stage_keys(bundle, "S1")[0]
            ts = s_toma_eval._get_take_slice(key, bundle)
            srv_cal, cli_cal, err = s_toma_eval._calibrate_take(bundle, ts, "S1", 1)
            self.assertIsNone(err)
            stop = [r for r in ts["arm_rows"] if r["row_kind"] == "stop_obs"][0]
            prior = max(r["srv_tick_ms"] for r in ts["arm_rows"] + ts["srv_rows"]
                        if r["srv_frame"] < stop["srv_frame"] and r["srv_tick_ms"] > 0)
            t0 = [s for s in ts["stimuli"] if s["stim_type"] == "web_stop"][0]["h_ms"]
            lo, hi = s_toma_eval._project_interval(prior, stop["srv_tick_ms"], srv_cal)
            self.assertLessEqual(lo - t0, 0.0)
            self.assertLess(hi - t0, 1000.0)
        verdict = _healthy_verdict()
        self.assertEqual(_verdict_checks(verdict)["TOM-02"]["status"], "pass")

    def test_neg_sol14_act_observe_uses_s3_contract_without_invented_snapshot_op(self):
        """BLOQ 14: act_observe lleva los argumentos numericos de S3; `op="snapshot"` ni se exige ni se inventa."""
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            br = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            acts = [e for e in br if e.get("ev") == "enq" and e.get("verb") == "act_observe"]
            self.assertTrue(acts)
            for e in acts:
                a = wire.unpack_payload(e["args"])
                self.assertEqual(sorted(a["num"]), ["center_x_m", "center_z_m", "radius_m"])
                self.assertNotIn("op", a["str"])
        self.assertEqual(_healthy_verdict()["exit_code"], 0)

        def with_stray_op(_m, bridge, _s):
            for ev in bridge:
                if ev.get("ev") in ("enq", "deliver") and ev.get("verb") == "act_observe":
                    ev["args"] = wire.pack_payload(scalars_str={"op": "other"}, scalars_num=wire.unpack_payload(ev["args"])["num"])

        self.assertEqual(_eval_with(with_stray_op)["exit_code"], 0)

    # ---------------------------------------------------------------- BLOQ 1, 2
    def test_neg_sol01_retry_latency_comes_from_raw_correlated_readings(self):
        """BLOQ 1: retrasar 2500 ms el terminal del reintento ya no da siete verdes."""
        def delay_terminal(_m, bridge, _s):
            def fn(rows):
                out = []
                for r in rows:
                    if r["row_kind"] in ("take_terminal", "cleanup_done"):
                        r = dict(r, srv_tick_ms=r["srv_tick_ms"] + 2500.0, srv_frame=r["srv_frame"] + 50, v1=r["v1"] + 50,
                                 v2=r["v2"] + 2500.0)
                        if r["row_kind"] == "take_terminal":
                            r["v5"] = r["v1"]
                    out.append(r)
                return out
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('dreq')}", fn)

        verdict = _eval_with(delay_terminal)
        self.assertNonPass(verdict, "TOM-07", "drop_first_req_retry_srv_stop_latency")

    def test_neg_sol01_labels_without_raw_jobs_or_rows_do_not_certify_epoch_dup_nor_procdup(self):
        for label in ("edup", "pdup"):
            def drop(_m, bridge, _s, _l=label):
                drop_ops(bridge, lambda v, a: v in ("take_arm", "take_srv_observe_start", "take_cli_watch_start")
                         and a.get("take_id") == _tid(_l))

            verdict = _eval_with(drop)
            self.assertNonPass(verdict, "TOM-07")

    def test_neg_sol01_contamination_and_restart_are_computed_from_raw_rows_not_labels(self):
        def contaminate(_m, bridge, scen):
            jid = job_id_of(bridge, "take_cli_watch_start", _tid("edup"), nth=1)
            edit_job(bridge, jid, lambda rows: rows + [_make_cli_row(9999, 456000.0, 0.0, 0.0, "rpc_stop_sent", _tid("edup"), aux_n=2)])
            for r in scen:  # la etiqueta del runner dice que no hubo contaminacion: no cuenta
                if r.get("kind") == "take_meta" and r.get("case_id") == "epoch_dup_2":
                    r["contaminated_by_old_retry_b"] = 0

        self.assertNonPass(_eval_with(contaminate), "TOM-07", "contaminated_by_old_retry")

        def new_take_stopped(_m, bridge, _s):
            jid = job_id_of(bridge, "take_srv_observe_start", _tid("edup"), nth=1)
            edit_job(bridge, jid, lambda rows: rows + [_make_srv_row(9133, 456600.0, 0.0, 0.0, "take_terminal", _tid("edup"),
                                                                   "parada:juego", v1=9133, v2=456600.0, v6=1, v7=1)])

        self.assertNonPass(_eval_with(new_take_stopped), "TOM-07", "new_epoch_take_stopped_by_old_retry")

    def test_neg_sol02_identity_is_epoch_and_take_id_and_the_full_id_is_reused_in_the_new_epoch(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            br = f03_common.read_jsonl(pdir / "samples" / "bridge.jsonl")
            sc = f03_common.read_jsonl(pdir / "samples" / "scenario.jsonl")
            ops, jobs, _h, _p = s_toma_eval._reconstruct_ops_and_jobs(br)
            bundle = s_toma_eval._collect_take_bundles(ops, jobs, sc, s_toma_eval._bridge_timeline(br))
            for label in ("edup", "pdup"):
                ks = [k for k in bundle["take_order"] if k[1] == _tid(label)]
                self.assertEqual(len(ks), 2, ks)
                self.assertNotEqual(ks[0][0], ks[1][0])
                t1 = s_toma_eval._get_take_slice(ks[0], bundle)
                t2 = s_toma_eval._get_take_slice(ks[1], bundle)
                self.assertTrue(any(r["row_kind"] == "rpc_stop_sent" for r in t1["cli_rows"]))
                self.assertFalse(any(r["row_kind"] == "rpc_stop_sent" for r in t2["cli_rows"]))
                self.assertNotEqual(t1["arm_job"]["job_id"], t2["arm_job"]["job_id"])
            self.assertEqual(bundle["identity_collisions"], [])
        self.assertEqual(_healthy_verdict()["exit_code"], 0)

        def no_restart(_m, bridge, _s):
            drop_ops(bridge, lambda v, a: v == "take_scene_prep" and a.get("op") == "restart_epoch")

        self.assertNonPass(_eval_with(no_restart), "TOM-07", "identity_collision")

    # ---------------------------------------------------------------- BLOQ 3
    def test_neg_sol03_ack_of_s2_with_wrong_current_pair_is_rejected(self):
        def wrong_pair(field, value):
            def mut(_m, bridge, _s):
                def fn(rows):
                    return [dict(r, **{field: value}) if r["row_kind"] == "ack_recv" else r for r in rows]
                edit_job(bridge, f"job-take_cli_watch_start-{_tid('s2-r1')}", fn)
            return mut

        for field, value in (("ack_cur_take_id", _tid("other")), ("ack_cur_epoch_n", 999), ("ack_cur_state", "rodando"),
                             ("ack_cur_origin", "web"), ("ack_req_epoch_n", 7), ("aux_n", 99)):
            with self.subTest(field=field):
                self.assertNonPass(_eval_with(wrong_pair(field, value)), "TOM-02")

    def test_neg_sol03_late_ack_of_ack2_requires_both_pairs_and_the_current_snapshot(self):
        for field, value in (("ack_cur_epoch_n", 0), ("ack_req_epoch_n", 0), ("ack_cur_take_id", ""), ("ack_cur_state", ""),
                             ("ack_req_state", "")):
            def mut(_m, bridge, _s, _f=field, _v=value):
                def fn(rows):
                    return [dict(r, **{_f: _v}) if (r["row_kind"] == "ack_recv" and r["ack_req_take_id"] == _tid("ack2")) else r
                            for r in rows]
                edit_job(bridge, f"job-take_cli_watch_start-{_tid('new')}", fn)

            with self.subTest(field=field):
                self.assertNonPass(_eval_with(mut), "TOM-07")

    def test_neg_sol03_take_state_reconciliation_compares_epoch_origin_director_and_seq(self):
        for field, value in (("ack_cur_epoch_n", 999), ("ack_cur_origin", "web"), ("detail", "dir_other"),
                             ("ack_cur_state", "parada"), ("ack_cur_take_id", _tid("guarda"))):
            def mut(_m, bridge, _s, _f=field, _v=value):
                def fn(rows):
                    return [dict(r, **{_f: _v}, aux_n=1) if r["row_kind"] == "take_state_recv" else r for r in rows]
                edit_job(bridge, f"job-take_cli_watch_start-{_tid('guardb')}", fn)

            with self.subTest(field=field):
                self.assertNonPass(_eval_with(mut), "TOM-07")

    def test_neg_sol03_each_server_reception_is_credited_with_its_retry_seq(self):
        def drop_rpc(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('guardb')}",
                     lambda rows: [r for r in rows if r["row_kind"] != "key_rpc"])

        self.assertNonPass(_eval_with(drop_rpc), "TOM-07", "missing_raw_rpc_records")

        def wrong_seq(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('guardc1')}",
                     lambda rows: [dict(r, v2=9.0) if r["row_kind"] == "key_rpc" else r for r in rows])

        self.assertNonPass(_eval_with(wrong_seq), "TOM-07", "retry_seq")

        def rejected_pair_gets_ack(_m, bridge, _s):
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('guardc1')}",
                     lambda rows: rows + [_make_cli_row(_cf(270300.0) + 5, 270300.0, 0, 0, "ack_recv", "x", ack_req_epoch_n=1,
                                                       ack_req_take_id=_tid("guardc1"), ack_req_state="parada",
                                                       ack_req_origin="juego", ack_resp_class="first_terminal",
                                                       ack_cur_epoch_n=1, ack_cur_take_id=_tid("guardc1"),
                                                       ack_cur_state="rodando", ack_cur_origin="rpc", aux_n=2)])

        self.assertNonPass(_eval_with(rejected_pair_gets_ack), "TOM-07", "received_an_ack")

    def test_neg_sol03_one_guardian_per_case_not_one_shared_guardian(self):
        def share(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "key_rejection" and r.get("case_id") == "other_director_c2":
                    r["take_id"] = _tid("guardc1")
                    r["guard_take_id"] = _tid("guardc1")

        self.assertNonPass(_eval_with(share), "TOM-07", "guardian_not_unique")

    def test_neg_sol03_server_snapshot_and_client_cache_are_compared_field_by_field(self):
        def stale_cache(_m, bridge, _s):
            edit_ops(bridge, "take_cam_prep", lambda a: a.get("op") == "status" and a.get("take_id") == _tid("guardb"),
                     lambda unp: unp["str"].update({"cli_cached_state": "parada"}))

        self.assertNonPass(_eval_with(stale_cache), "TOM-07", "client_cache_status_differs")

        def wrong_server_origin(_m, bridge, _s):
            edit_ops(bridge, "take_scene_prep", lambda a: a.get("op") == "status" and a.get("take_id") == _tid("guardb"),
                     lambda unp: unp["str"].update({"take_origin": "juego"}))

        self.assertNonPass(_eval_with(wrong_server_origin), "TOM-07")

    # ---------------------------------------------------------------- BLOQ 4
    def test_neg_sol04_reusing_raw_rows_of_r1_as_r3_is_rejected_even_if_declarations_are_adjusted(self):
        def reuse(_m, bridge, scen):
            for verb in ("take_arm", "take_srv_observe_start", "take_cli_watch_start"):
                src = [r for _e, u in _job_pages(bridge, f"job-{verb}-{_tid('s1-r1')}") for r in u["rows"]]
                edit_job(bridge, f"job-{verb}-{_tid('s1-r3')}", lambda rows, _s=src: copy.deepcopy(_s))
            r1 = [r for r in scen if r.get("kind") == "clock_pair" and r.get("stage") == "S1" and r.get("rep") == 1]
            for r in scen:  # declaraciones temporales ajustadas por el runner
                if r.get("kind") == "clock_pair" and r.get("stage") == "S1" and r.get("rep") == 3:
                    r["h_send_ms"] -= 20000.0
                    r["h_recv_ms"] -= 20000.0
            self.assertTrue(r1)

        self.assertNonPass(_eval_with(reuse))

    def test_neg_sol04_calibration_pairs_must_link_to_raw_take_clock_ping_responses(self):
        def no_pairs(stage, rep):
            def mut(_m, _b, scen):
                scen[:] = [r for r in scen if not (r.get("kind") == "clock_pair" and r["stage"] == stage and r["rep"] == rep
                                                   and r["peer"] == "server")]
            return mut

        self.assertNonPass(_eval_with(no_pairs("S1", 1)), "TOM-01", "insufficient_clock_pings")

        def no_raw_pings(_m, bridge, _s):
            drop_ops(bridge, lambda v, a: v == "take_clock_ping")

        v = _eval_with(no_raw_pings)
        self.assertEqual(v["exit_code"], 2, v)

        def tighter_window(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "clock_pair" and r["stage"] == "S1" and r["rep"] == 1 and r["peer"] == "server":
                    r["h_send_ms"] += 6.0

        self.assertNonPass(_eval_with(tighter_window), "TOM-01", "outside_raw_ping_interval")

        def other_instance(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "clock_pair" and r["stage"] == "S1" and r["rep"] == 1 and r["peer"] == "client":
                    r["inst"] = "cli-inst-999"

        self.assertNonPass(_eval_with(other_instance), "TOM-01", "inst")

        def invented_tick(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "clock_pair" and r["stage"] == "S1" and r["rep"] == 2 and r["phase"] == "pre":
                    r["peer_tick_ms"] += 0.5

        self.assertNonPass(_eval_with(invented_tick), "TOM-01", "without_raw_ping")

    def test_neg_sol04_pings_must_bracket_the_take_and_cannot_be_shared_between_repetitions(self):
        def shared(_m, _b, scen):
            r1 = [dict(r) for r in scen if r.get("kind") == "clock_pair" and r["stage"] == "S1" and r["rep"] == 1]
            scen[:] = [r for r in scen if not (r.get("kind") == "clock_pair" and r["stage"] == "S1" and r["rep"] == 2)]
            for r in r1:
                r["rep"] = 2
            scen.extend(r1)

        self.assertNonPass(_eval_with(shared), "TOM-01")

    # ---------------------------------------------------------------- BLOQ 5
    def test_neg_sol05_activation_comes_from_raw_edge_and_hold_bits_not_from_labels(self):
        def zero_bits(prefix):
            def mut(_m, bridge, _s):
                edit_job(bridge, prefix,
                         lambda rows: [dict(r, aux_n=0) if r["row_kind"] == "frame_sample" else r for r in rows])
            return mut

        self.assertNonPass(_eval_with(zero_bits(f"job-take_cli_watch_start-{_tid('keyreb')}")), "TOM-03")
        self.assertNonPass(_eval_with(zero_bits(f"job-take_cli_watch_start-{_tid('s2-r2')}")), "TOM-03")

        def old_key_edge(_m, bridge, _s):
            def fn(rows):
                out = []
                done = False
                for r in rows:
                    if r["row_kind"] == "frame_sample" and not done and r["cli_tick_ms"] > 2000.0 + 600.0:
                        r = dict(r, aux_n=1)
                        done = True
                    out.append(r)
                return out
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('keyreb')}", fn)

        self.assertNonPass(_eval_with(old_key_edge), "TOM-03")

    def test_neg_sol05_default_key_is_contrasted_with_inputs_xml_of_the_sealed_commit(self):
        root = f03_common.REPO_ROOT
        v_missing = _eval_with(None, sources=_TestSources(root, inputs_xml=None))
        self.assertNonPass(v_missing, "TOM-03", "inputs_xml_unavailable")
        other = INPUTS_XML.replace(b'name="kF9"', b'name="kF10"')
        self.assertNonPass(_eval_with(None, sources=_TestSources(root, inputs_xml=other)), "TOM-03", "differs_from_fixture")
        no_action = INPUTS_XML.replace(b"UADsbxQaTakeStop", b"UAOther")
        self.assertNonPass(_eval_with(None, sources=_TestSources(root, inputs_xml=no_action)), "TOM-03", "no_default_binding")
        self.assertNonPass(_eval_with(None, sources=_TestSources(root, inputs_xml=b"<not-xml")), "TOM-03")

    def test_neg_sol05_conflicts_are_recomputed_in_python_from_observed_bindings(self):
        def conflict(key):
            def mut(_m, bridge, _s):
                edit_ops(bridge, "take_key_op", lambda a: a.get("op") == "audit_candidates",
                         lambda unp: unp["rows"].append({"alt_idx": 0, "action_name": "UAGear", "key_name": key}))
            return mut

        # todas las etiquetas y contadores de la sonda dicen «sin conflicto»; las vinculaciones crudas dicen otra cosa
        self.assertNonPass(_eval_with(conflict("kF9")), "TOM-03", "default_key_conflict")
        self.assertNonPass(_eval_with(conflict("kF10")), "TOM-03", "selected_keys_differ")

        def one_free(_m, bridge, _s):
            edit_ops(bridge, "take_key_op", lambda a: a.get("op") == "audit_candidates",
                     lambda unp: unp["rows"].extend({"alt_idx": 0, "action_name": "UAGear", "key_name": k}
                                                    for k in ("kF10", "kBackslash", "kRBracket")))

        self.assertNonPass(_eval_with(one_free), "TOM-03", "insufficient_free_candidate_keys")

    # ---------------------------------------------------------------- BLOQ 7, 8 (mutantes literales) y T7
    def test_neg_sol07_08_mutants_represent_their_injection_literally(self):
        nonce = "a1b2c3d4e5f60718"
        base_br = _build_core(None, nonce, (0.0, 0.0, 0.0), False)["bridge"]

        def mut_br(m):
            return _build_core(m, nonce, (0.0, 0.0, 0.0), False)["bridge"]

        def rows(br, verb, label, nth=0):
            jid = job_id_of(br, verb, _tid(label), nth)
            return [r for _e, u in _job_pages(br, jid) for r in u["rows"]]

        def first_active(rs):
            return next(r for r in rs if r["row_kind"] == "frame_sample" and r["sandbox_cam_active_b"] == 1)

        # §6 despachar_desfasado: la orden de actor_2 se despacha 160 ms despues del frame del GO en r = 2
        br = mut_br("despachar_desfasado")
        for rep, want in ((1, 0), (2, 3), (3, 0)):
            arm = rows(br, "take_arm", f"s1-r{rep}")
            go = [r for r in arm if r["row_kind"] == "go_sent"][0]["srv_frame"]
            d2 = [r for r in arm if r["row_kind"] == "dispatch" and r["subject_id"] == "actor_2"][0]
            d1 = [r for r in arm if r["row_kind"] == "dispatch" and r["subject_id"] == "actor_1"][0]
            self.assertEqual(d2["srv_frame"] - go, want, rep)
            self.assertEqual(d1["srv_frame"] - go, 0)
        # jitter_gt_100ms: el movimiento de actor_1 arranca 160 ms tarde en r = 2, tambien en common_time
        br = mut_br("jitter_gt_100ms")
        for label, delay in (("s1-r1", 0.0), ("s1-r2", 160.0), ("s1-r3", 0.0), ("s1c-r1", 0.0), ("s1c-r2", 160.0)):
            srv = rows(br, "take_srv_observe_start", label)
            arm = rows(br, "take_arm", label)
            disp = [r for r in arm if r["row_kind"] == "dispatch" and r["subject_id"] == "actor_1"][0]["srv_tick_ms"]
            pos = min(r["srv_tick_ms"] for r in srv if r["row_kind"] == "act_sample" and r["subject_id"] == "actor_1" and r["v4"] > 0)
            self.assertAlmostEqual(pos - disp, 4.0 + delay, places=6, msg=label)
        # fase_muestreo_desplazada: la camara se activa 150 ms antes en r = 3 sin tocar go_recv
        br = mut_br("fase_muestreo_desplazada")
        for rep, want in ((1, 4.0), (2, 4.0), (3, -146.0)):
            cli = rows(br, "take_cli_watch_start", f"s1-r{rep}")
            gd = [r for r in cli if r["row_kind"] == "go_deliver"][0]["cli_tick_ms"]
            gr = [r for r in cli if r["row_kind"] == "go_recv"][0]["cli_tick_ms"]
            arm = rows(br, "take_arm", f"s1-r{rep}")
            gs = [r for r in arm if r["row_kind"] == "go_sent"][0]["srv_tick_ms"]
            self.assertAlmostEqual(first_active(cli)["cli_tick_ms"] - gd, want, places=6, msg=rep)
            self.assertAlmostEqual(gr - gs, 5.0, places=6)
        # peer_reiniciado_en_toma: reinicio del epoch del servidor e interrupcion a los 1200 ms de r = 2
        br = mut_br("peer_reiniciado_en_toma")
        ops, _j, _h, _p = s_toma_eval._reconstruct_ops_and_jobs(br)
        n_restarts = sum(1 for o in ops if o["args_s"].get("op") == "restart_epoch")
        t2 = [r for r in rows(br, "take_srv_observe_start", "s1-r2") if r["row_kind"] == "take_terminal"][0]
        self.assertAlmostEqual(t2["v3"], 1200.0)
        base_ops = s_toma_eval._reconstruct_ops_and_jobs(base_br)[0]
        self.assertEqual(n_restarts, sum(1 for o in base_ops if o["args_s"].get("op") == "restart_epoch") + 1)
        # retraso_lectura_tecla_gt_1s: la accion se lee con key_delay_ms = 1250 en S2
        br = mut_br("retraso_lectura_tecla_gt_1s")
        for rep in (1, 2, 3):
            term = [r for r in rows(br, "take_srv_observe_start", f"s2-r{rep}") if r["row_kind"] == "take_terminal"][0]
            self.assertAlmostEqual(term["v3"], 3020.0 + 1250.0)
        for rep in (1, 2, 3):  # S1 intacta
            term = [r for r in rows(br, "take_srv_observe_start", f"s1-r{rep}") if r["row_kind"] == "take_terminal"][0]
            self.assertAlmostEqual(term["v3"], 3020.0)
        # gesto_pendiente_no_cancelado: la peticion sigue abierta tras parar y el gesto 1 arranca a los 3200 ms
        br = mut_br("gesto_pendiente_no_cancelado")
        post = [r for r in rows(br, "take_srv_observe_start", "s2-r1") if r["row_kind"] == "act_sample"
                and r["subject_id"] == "actor_2" and r["state_or_origin"].startswith("parada")]
        self.assertTrue(all(r["v9"] == 1 for r in post if r["take_dtsum_ms"] < 3200.0))
        self.assertTrue(any(r["v7"] == 1 and r["v6"] == 1000 for r in post if r["take_dtsum_ms"] >= 3200.0))
        # conflicto_tecla_ignorado: una candidata con conflicto vanilla en S0a, solo en la auditoria
        br = mut_br("conflicto_tecla_ignorado")
        ops, _j, _h, _p = s_toma_eval._reconstruct_ops_and_jobs(br)
        audits = [o for o in ops if o["args_s"].get("op") == "audit_candidates"]
        self.assertIn(("UAGear", "kF9"), s_toma_eval._binding_rows(audits[0]))
        self.assertEqual([o for o in ops if o["args_s"].get("op") in ("bind_key", "restore_bindings") and
                          ("UAGear", "kF9") in s_toma_eval._binding_rows(o)], [])
        # proteccion_retenida_al_salir: no restaura el permiso previo true al salir de r = 1 (solo r = 1)
        br = mut_br("proteccion_retenida_al_salir")
        for rep, want in ((1, 0.0), (2, 0.0), (3, 1.0)):
            term = [r for r in rows(br, "take_srv_observe_start", f"s1-r{rep}") if r["row_kind"] == "take_terminal"][0]
            self.assertEqual(term["v8"], want, rep)
        # traza_cam_incompleta: sin frame_sample solo en [1000, 2000) ms de r = 2
        br = mut_br("traza_cam_incompleta")
        for rep, gap in ((1, False), (2, True), (3, False)):
            act = [r for r in rows(br, "take_cli_watch_start", f"s1-r{rep}") if r["row_kind"] == "frame_sample" and r["sandbox_cam_active_b"] == 1]
            inside = [r for r in act if 1000.0 <= r["take_dtsum_ms"] < 2000.0]
            self.assertEqual(not inside, gap, rep)
            self.assertTrue(any(r["take_dtsum_ms"] < 1000.0 for r in act) and any(r["take_dtsum_ms"] >= 2000.0 for r in act))
        # cam_desviada_b6: +0,85 m a partir de los 1050 ms en r = 2
        br = mut_br("cam_desviada_b6")
        ref = rows(base_br, "take_cli_watch_start", "s1-r2")
        got = rows(br, "take_cli_watch_start", "s1-r2")
        for a, b_ in zip(ref, got):
            if a["row_kind"] == "frame_sample" and a["sandbox_cam_active_b"] == 1:
                want = 0.85 if a["take_dtsum_ms"] >= 1050.0 else 0.0
                self.assertAlmostEqual(b_["cam_x_m"] - a["cam_x_m"], want, places=3)
        self.assertEqual(rows(base_br, "take_cli_watch_start", "s1-r1"), rows(br, "take_cli_watch_start", "s1-r1"))
        # go_tardio_reactiva_cam: el GO retenido reactiva la camara tras la pulsacion
        br = mut_br("go_tardio_reactiva_cam")
        hgo = rows(br, "take_cli_watch_start", "hgo")
        gd = [r for r in hgo if r["row_kind"] == "go_deliver"][0]["cli_tick_ms"]
        self.assertTrue(any(r["row_kind"] == "frame_sample" and r["cli_tick_ms"] > gd and r["sandbox_cam_active_b"] == 1 for r in hgo))

    def test_neg_sol07_t7_telemetria_retrasada_is_a_test_of_inconcluso_with_origin_marks_intact(self):
        def delayed(_m, bridge, _s):
            def fn(rows):
                pos = [r for r in rows if r["row_kind"] == "act_sample" and r["subject_id"] == "actor_2" and r["v7"] == 13
                       and r["v5"] == 1 and r["v8"] == 11 and r["take_dtsum_ms"] < 1000.0]
                t0 = min(r["srv_tick_ms"] for r in pos)
                return [r for r in rows if not (r in pos and r["srv_tick_ms"] <= t0 + 180.0)]
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r2')}", fn)

        verdict = _eval_with(delayed)
        self.assertEqual(verdict["exit_code"], 2, verdict)
        self.assertEqual(_verdict_checks(verdict)["TOM-01"]["status"], "missing")
        self.assertIn("threshold_inside_uncertainty", _verdict_checks(verdict)["TOM-01"]["reason"])

    # ---------------------------------------------------------------- BLOQ 9 (T13 sobre la evidencia)
    def test_neg_sol09_lease_discipline_uses_manifest_lease_raw_last_poll_and_own_clock(self):
        L1, L2, L3 = 210000.0, 220000.0, 480000.0

        def srv_rpc_after_expiry(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('cdrop1')}",
                     lambda rows: rows + [_make_srv_row(_sf(L1 + 3300.0), L1 + 3300.0, 0, 0, "rpc_emit", "TAKE_STATE", "sent", v1=3300.0, v2=1)])

        self.assertNonPass(_eval_with(srv_rpc_after_expiry), "TOM-06", "server_emitted_rpc_with_expired_lease")

        def srv_go_after_expiry(_m, bridge, _s):
            edit_job(bridge, f"job-take_arm-{_tid('cdrop2')}",
                     lambda rows: rows + [_make_srv_row(_sf(L2 + 3400.0), L2 + 3400.0, 0, 0, "go_sent", _tid("cdrop2"), "rodando",
                                                      v1=_sf(L2 + 3400.0), v2=L2 + 3400.0)])

        self.assertNonPass(_eval_with(srv_go_after_expiry), "TOM-06", "go_or_dispatch_with_expired_lease")

        def cli_stop_after_expiry(_m, bridge, _s):
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('cutaf')}",
                     lambda rows: rows + [_make_cli_row(_cf(L3 + 3300.0), L3 + 3300.0, 0, 0, "rpc_stop_sent", _tid("cutaf"), aux_n=0)])

        self.assertNonPass(_eval_with(cli_stop_after_expiry), "TOM-07", "client_emitted_stop_rpc_with_expired_lease")

        def cli_cam_active_after_expiry(_m, bridge, _s):
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('cdrop2')}",
                     lambda rows: rows + [_make_cli_row(_cf(L2 + 3400.0) + 50, L2 + 3400.0, 0, 0, "frame_sample", "", sandbox_cam_active_b=1)])

        self.assertNonPass(_eval_with(cli_cam_active_after_expiry), "TOM-06", "client_kept_sandbox_cam_active")

    def test_neg_sol09_window_lease_and_last_poll_are_not_taken_from_runner_declarations(self):
        def lease_2000(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "cut_window":
                    r["lease_ms"] = 2000.0

        v = _eval_with(lease_2000)
        self.assertNonPass(v, "TOM-06", "lease_ms_differs_from_identity")

        def last_poll(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "cut_window" and r.get("case_id") == "conn_drop_no_effects":
                    r["last_ok_poll_h_ms"] += 500.0

        self.assertNonPass(_eval_with(last_poll), "TOM-06", "declaration_differs_from_raw_bridge")

        def no_raw_cut(_m, bridge, _s):
            bridge[:] = [r for r in bridge if r.get("ev") not in ("cut_start", "cut_end")]

        self.assertNonPass(_eval_with(no_raw_cut), "TOM-06", "without_raw_bridge_cut")

        def identity_lease(m, _b, _s):
            m["identity"]["params"]["lease_ms"] = 2000

        self.assertNonPass(_eval_with(identity_lease))

    def test_neg_sol09_a_reception_at_the_other_peer_is_not_proof_of_emission(self):
        """El cliente recibe tarde un TAKE_STATE emitido por el servidor antes de vencer: no es una emision con lease vencido."""
        L2 = 220000.0

        def late_reception(_m, bridge, _s):
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('cdrop2')}",
                     lambda rows: rows + [
                         _make_cli_row(_cf(L2 + 3200.0) + 5, L2 + 3200.0, 0, 0, "take_state_recv", "dir_main", ack_cur_epoch_n=1,
                                       ack_cur_take_id=_tid("cdrop2"), ack_cur_state="rodando", ack_cur_origin="rpc", aux_n=2),
                         _make_cli_row(_cf(L2 + 3250.0) + 5, L2 + 3250.0, 0, 0, "ack_recv", "late", ack_req_epoch_n=1,
                                       ack_req_take_id=_tid("cdrop2"), ack_req_state="parada", ack_req_origin="hombre_muerto",
                                       ack_resp_class="first_terminal", ack_cur_epoch_n=1, ack_cur_take_id=_tid("cdrop2"),
                                       ack_cur_state="parada", ack_cur_origin="hombre_muerto", aux_n=3)])

        verdict = _eval_with(late_reception)
        self.assertEqual(verdict["exit_code"], 0, verdict)

    def test_neg_sol09_safety_cleanup_runs_once_and_observers_keep_observing(self):
        L2 = 220000.0

        def twice(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('cdrop2')}",
                     lambda rows: rows + [r for r in rows if r["row_kind"] == "cleanup_done"])

        self.assertNonPass(_eval_with(twice), "TOM-06", "cleanup_not_run_exactly_once")

        def stop_observing(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('cdrop2')}",
                     lambda rows: [r for r in rows if not (r["row_kind"] in ("director_sample", "act_sample") and r["srv_tick_ms"] > L2 + 3000.0)])

        self.assertNonPass(_eval_with(stop_observing), "TOM-06")

        def cli_twice(_m, bridge, _s):
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('cdrop2')}",
                     lambda rows: rows + [r for r in rows if r["row_kind"] == "cli_safety_exit"])

        self.assertNonPass(_eval_with(cli_twice), "TOM-06", "safety_exit_not_run_exactly_once")

    # ---------------------------------------------------------------- BLOQ 10, 11
    def test_neg_sol10_protective_melee_counts_only_inside_the_protected_window(self):
        def after_terminal(_m, bridge, _s):
            def fn(rows):
                return [dict(r, srv_tick_ms=r["srv_tick_ms"] + 3500.0, srv_frame=r["srv_frame"] + 70) if r["row_kind"] == "melee_hit" else r
                        for r in rows]
            for rep in (1, 2, 3):
                edit_job(bridge, f"job-take_srv_observe_start-{_tid(f's1-r{rep}')}", fn)

        self.assertNonPass(_eval_with(after_terminal), "TOM-04", "melee_only_blocked_or_dummy_light")

    def test_neg_sol10_terminal_record_is_unique_per_take(self):
        def second_terminal(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}",
                     lambda rows: rows + [dict(r, v6=2.0, v7=2.0) for r in rows if r["row_kind"] == "take_terminal"])

        verdict = _eval_with(second_terminal)
        self.assertNonPass(verdict, "TOM-04", "duplicate_take_terminal")
        self.assertNonPass(verdict, "TOM-02", "duplicate_take_terminal")
        self.assertNonPass(verdict, "TOM-01", "duplicate_take_terminal")

        def second_s3a(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s3a2')}",
                     lambda rows: rows + [dict(r, v6=2.0, v7=2.0) for r in rows if r["row_kind"] == "take_terminal"])

        self.assertNonPass(_eval_with(second_s3a), "TOM-06", "duplicate_take_terminal")

    def test_neg_sol10_director_health_coverage_is_per_frame_until_the_frontier(self):
        def gap(_m, bridge, _s):
            def fn(rows):
                ds = [r for r in rows if r["row_kind"] == "director_sample"]
                drop = ds[len(ds) // 3]
                return [r for r in rows if r is not drop and r != drop]
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}", fn)

        self.assertNonPass(_eval_with(gap), "TOM-04", "not_continuous_to_frontier")

        def unprotected(_m, bridge, _s):
            def fn(rows):
                ds = [r for r in rows if r["row_kind"] == "director_sample"]
                bad = ds[5]
                return [dict(r, v3=1.0) if r == bad else r for r in rows]
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r2')}", fn)

        self.assertNonPass(_eval_with(unprotected), "TOM-04", "allow_dmg_true_before_frontier")

        def late_restore(_m, bridge, _s):
            def fn(rows):
                return [dict(r, v3=0.0) if (r["row_kind"] == "director_sample" and r["state_or_origin"].startswith("parada")) else r
                        for r in rows]
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r3')}", fn)

        self.assertNonPass(_eval_with(late_restore), "TOM-04", "not_restored_after_frontier")

    def test_neg_sol11_camera_is_evaluated_until_the_observed_exit_not_until_3000ms(self):
        def spike_after_3000(_m, bridge, _s):
            def fn(rows):
                act = [r for r in rows if r["row_kind"] == "frame_sample" and r["sandbox_cam_active_b"] == 1]
                last = max(act, key=lambda r: r["take_dtsum_ms"])
                self.assertGreater(last["take_dtsum_ms"], 3000.0)
                self.assertLess(last["take_dtsum_ms"], 3040.0)
                return [dict(r, cam_x_m=r["cam_x_m"] + 9.0) if r == last else r for r in rows]
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('s1-r2')}", fn)

        self.assertNonPass(_eval_with(spike_after_3000), "TOM-05", "cam_deviation_vs_analytic")

    def test_neg_sol11_each_reset_needs_its_order_and_a_fresh_observation_before_the_take(self):
        self.assertNonPass(_eval_with(lambda _m, b, _s: drop_ops(b, lambda v, a: v == "take_scene_prep" and a.get("op") == "reset")),
                           "TOM-05", "missing_reset_before_take")
        self.assertNonPass(_eval_with(lambda _m, b, _s: drop_ops(b, lambda v, a: v == "act_observe")), "TOM-05")

        def drop_second_observation(_m, bridge, _s):
            ids = [e["op_id"] for e in bridge if e.get("ev") == "enq" and e.get("verb") == "act_observe"]
            bridge[:] = [r for r in bridge if r.get("op_id") != ids[1]]

        self.assertNonPass(_eval_with(drop_second_observation), "TOM-05", "missing_fresh_observation_after_reset")
        self.assertNonPass(_eval_with(lambda _m, b, _s: drop_ops(b, lambda v, a: v == "take_scene_prep" and a.get("op") == "perturb_fixture")),
                           "TOM-05", "missing_perturb_fixture")
        self.assertNonPass(_eval_with(None, no_reset_b6=True), "TOM-05", "b6_reset")

    # ---------------------------------------------------------------- BLOQ 12, 13
    def test_neg_sol12_adapter_stamp_is_recomputed_from_the_sources_of_git_head(self):
        fake = "dsbx-qa-exp1+ffffffffffffffff"

        def swap_both(m, bridge, _s):
            m["identity"]["params"]["adapter_ver_expected"] = fake
            for verb in ("take_scene_prep", "act_observe"):
                edit_ops(bridge, verb, lambda a: a.get("op", "verify") == "verify",
                         lambda unp: unp["str"].update({"adapter_ver": fake}) if "adapter_ver" in unp["str"] else None)

        verdict = _eval_with(swap_both)
        self.assertEqual(verdict["exit_code"], 2, verdict)
        self.assertIn("params_unverified", verdict["reasons"])
        # sin fuentes de la expansion en el commit (S3 aun sin integrar): INCONCLUSO, nunca PASA
        with tempfile.TemporaryDirectory() as tmp:
            pdir = build_healthy_part(Path(tmp) / "run")
            v_default = s_toma_eval.evaluate(pdir)
            self.assertEqual(v_default["exit_code"], 2, v_default)
            self.assertIn("stamp_source_unavailable", v_default["reasons"])

    def test_neg_sol12_the_fixture_consumed_is_the_one_whose_hash_was_verified(self):
        fixture_path = QA_DIR / "fixtures" / "s_toma_fixture.json"
        fixture = gate_core.read_json(fixture_path)
        fixture["camera_path"]["keyframes"][2]["pos_m"][0] += 3.0
        altered = (json.dumps(fixture, indent=2, sort_keys=True) + "\n").encode("utf-8")
        root = f03_common.REPO_ROOT

        def new_hash(m, _b, _s):
            m["identity"]["params"]["fixture_sha256"] = hashlib.sha256(altered).hexdigest()

        verdict = _eval_with(new_hash, sources=_TestSources(root, fixture_bytes=altered))
        self.assertNonPass(verdict, "TOM-05")  # el evaluador consume los bytes verificados, no el fichero del arbol actual
        self.assertEqual(_verdict_checks(verdict)["TOM-05"]["status"], "fail", verdict)
        # bytes distintos de los que firma la identidad -> INCONCLUSO
        verdict = _eval_with(None, sources=_TestSources(root, fixture_bytes=altered))
        self.assertEqual(verdict["exit_code"], 2, verdict)
        self.assertIn("params_unverified", verdict["reasons"])

    def test_neg_sol13_duplicated_first_delivery_and_core_row_cap_are_inconcluso(self):
        def dup_true(_m, bridge, _s):
            n = 0
            for ev in bridge:
                if ev.get("ev") == "result":
                    ev["result"]["dup"] = True
                    n += 1
                    if n == 3:
                        break

        v = _eval_with(dup_true)
        self.assertEqual(v["exit_code"], 2, v)
        self.assertIn("dup_first_delivery", v["reasons"])

        def dup_missing(_m, bridge, _s):
            for ev in bridge:
                if ev.get("ev") == "result":
                    del ev["result"]["dup"]
                    break

        self.assertEqual(_eval_with(dup_missing)["exit_code"], 2)

        def rows_cap(_m, bridge, _s):
            pages = _job_pages(bridge, f"job-take_srv_observe_start-{_tid('s1-r2')}")
            ev, unp = pages[-1]
            unp["str"]["state"] = "failed"
            unp["str"]["reason"] = "rows_cap"
            _repack(ev, unp)

        v = _eval_with(rows_cap)
        self.assertEqual(v["exit_code"], 2, v)
        self.assertIn("observer_capacity", v["reasons"])
        for check in v["checks"]:
            self.assertEqual(check["status"], "missing")

    # ---------------------------------------------------------------- BLOQ 17 y E9
    def test_neg_sol17_constant_dt_fabrication_fails_by_duration_not_by_nonmonotonic_ticks(self):
        def constant(_m, bridge, _s):
            def fn(rows):
                out = []
                t = None
                for r in rows:
                    if r["row_kind"] == "frame_sample":
                        t = r["cli_tick_ms"] if t is None else t
                        r = dict(r, cli_tick_ms=t)
                        t += 50.0
                    out.append(r)
                return out
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('s1-r1')}", fn)

        v = _eval_with(constant)
        self.assertEqual(v["exit_code"], 1, v)
        chk = _verdict_checks(v)["TOM-02"]
        self.assertEqual(chk["status"], "fail")
        self.assertIn("fabricated_constant_frame_dt", chk["reason"])
        self.assertNotIn("non_monotonic", chk["reason"])

        def constant_take_dtsum(_m, bridge, _s):
            def fn(rows):
                out = []
                for r in rows:
                    if r["row_kind"] == "frame_sample" and r["sandbox_cam_active_b"] == 1:
                        r = dict(r, take_dtsum_ms=r["cli_frame"] * 80.0 - 1000000.0)
                    out.append(r)
                return out
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('s1-r1')}", fn)

        self.assertNonPass(_eval_with(constant_take_dtsum))

    def test_neg_sol17_labels_without_readings_and_states_copied_from_orders_are_not_evidence(self):
        # 1. la caja de la guardiana: sin las lecturas crudas de TAKE_STATE no hay reconciliacion, aunque el estado se copie
        def drop_state_recv(_m, bridge, _s):
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('guardc2')}",
                     lambda rows: [r for r in rows if r["row_kind"] != "take_state_recv"])

        self.assertNonPass(_eval_with(drop_state_recv), "TOM-07")

        # 2. estado «copiado de la orden»: el status del servidor repite lo pedido, pero las lecturas del cliente dicen otra cosa
        def copied(_m, bridge, _s):
            edit_ops(bridge, "take_cam_prep", lambda a: a.get("op") == "status" and a.get("take_id") == _tid("guardc1"),
                     lambda unp: unp["num"].update({"cli_state_seq": 77}))

        self.assertNonPass(_eval_with(copied), "TOM-07")

        # 3. etiquetas del runner sin lecturas: ningun estado de toma se acepta solo por `take_meta`
        def labels_only(_m, bridge, scen):
            drop_ops(bridge, lambda v, a: v in ("take_arm", "take_srv_observe_start", "take_cli_watch_start")
                     and a.get("take_id", "").startswith(_tid("s1-")))

        self.assertNonPass(_eval_with(labels_only))

    def test_neg_director_not_protected_resource_does_not_protect_the_object(self):
        def mortal(_m, bridge, _s):
            def fn(rows):
                return [dict(r, v3=1.0) if (r["row_kind"] in ("director_sample", "melee_hit", "stop_obs") and r["state_or_origin"] in ("rodando", "MeleeZombie")) else r
                        for r in rows]
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}", fn)

        self.assertNonPass(_eval_with(mortal), "TOM-04")

    def test_t6_late_ack_of_ack2_recorded_without_overwriting_new_take_cache(self):
        def overwrite_cache_with_old_ack(_m, bridge, _s):
            edit_ops(bridge, "take_cam_prep", lambda a: a.get("op") == "status" and a.get("take_id") == _tid("new"),
                     lambda unp: unp["str"].update({"cli_cached_take_id": _tid("ack2"), "cli_cached_state": "parada"}))

        verdict = _eval_with(overwrite_cache_with_old_ack)
        self.assertEqual(verdict["exit_code"], 1, verdict)
        self.assertEqual(_verdict_checks(verdict)["TOM-07"]["status"], "fail")
        self.assertIn("t6_old_ack_overwrote_newer_client_cache", _verdict_checks(verdict)["TOM-07"]["reason"])

        def lower_seq(_m, bridge, _s):
            edit_ops(bridge, "take_cam_prep", lambda a: a.get("op") == "status" and a.get("take_id") == _tid("new"),
                     lambda unp: unp["num"].update({"cli_state_seq": 1}))

        self.assertNonPass(_eval_with(lower_seq), "TOM-07", "t6_old_ack_overwrote")

        def stale_state_a(_m, bridge, _s):  # TAKE_STATE(A) viejo aplicado con B rodando
            edit_ops(bridge, "take_cam_prep", lambda a: a.get("op") == "status" and a.get("take_id") == _tid("stb"),
                     lambda unp: unp["str"].update({"cli_cached_state": "parada"}))

        self.assertNonPass(_eval_with(stale_state_a), "TOM-07", "stale_notify")

    # ---------------------------------------------------------------- 11 mutantes y agregado
    def _check_vector(self, mname, verdict, spec):
        self.assertEqual(verdict["exit_code"], 1, f"{mname}: {verdict}")
        self.assertEqual(verdict["verdict"], "FALLA")
        checks_by_id = {c["id"]: c["status"] for c in verdict["checks"]}
        must_fail = set(spec["must_fail_checks"])
        allowed_non_pass = spec.get("allowed_non_pass") or {}
        for cid in s_toma_eval.CHECK_IDS:
            st = checks_by_id[cid]
            if cid in must_fail:
                self.assertEqual(st, "fail", f"{mname} debia fallar {cid} (nunca missing): {verdict}")
            elif cid in allowed_non_pass:
                self.assertIn(st, ["pass"] + list(allowed_non_pass[cid]), f"{mname} {cid}: {verdict}")
            else:
                self.assertEqual(st, "pass", f"{mname} contamino {cid}={st}: {verdict}")

    def test_all_11_mutants_and_aggregate_spike(self):
        self.assertEqual(len(s_toma_mutants.EXPECTED_MUTANTS), 11)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            p_run = build_healthy_part(base / "run", op_nonce="0000000000000001")
            gate_core.write_json(p_run / "verdict.json", _evaluate(p_run))
            for idx, (mname, spec) in enumerate(s_toma_mutants.EXPECTED_MUTANTS.items(), start=2):
                with self.subTest(mutant=mname):
                    p_mut = build_healthy_part(base / f"mut-{mname}", mutant=mname, op_nonce=f"{idx:016x}")
                    verdict = _evaluate(p_mut)
                    self._check_vector(mname, verdict, spec)
                    gate_core.write_json(p_mut / "verdict.json", verdict)
            agg = f03_common.aggregate_spike(base, "S-toma")
            self.assertEqual(agg["exit_code"], 0, agg)
            self.assertEqual(agg["verdict"], "PASA")

    def test_mutants_table_declares_each_vector_without_overlap(self):
        for mname, spec in s_toma_mutants.EXPECTED_MUTANTS.items():
            self.assertEqual(spec["expected_exit_code"], 1)
            self.assertTrue(spec["must_fail_checks"])
            self.assertTrue(set(spec["must_fail_checks"]).isdisjoint(spec["allowed_non_pass"]), mname)
            for states in spec["allowed_non_pass"].values():
                self.assertTrue(set(states) <= {"fail", "missing"})

    # ---------------------------------------------------------------- INCONCLUSO (no son mutantes)
    def test_inconcluso_cases(self):
        def wide_clock(_m, bridge, scen):
            pairs = [r for r in scen if r.get("kind") == "clock_pair" and r["stage"] == "S1" and r["rep"] == 1 and r["peer"] == "server"]
            keys = {(p["peer_tick_ms"], p["peer_frame"]) for p in pairs}
            for ev in bridge:
                if ev.get("ev") != "result":
                    continue
                unp = _read_unp(ev)
                if unp and (unp["num"].get("peer_tick_ms"), unp["num"].get("peer_frame")) in keys:
                    ev["t_ms"] += 65.0
            for p in pairs:
                p["h_recv_ms"] += 65.0

        def no_pre_neg_a1(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}",
                     lambda rows: [r for r in rows if not (r["row_kind"] == "act_sample" and r["subject_id"] == "actor_1" and r["take_dtsum_ms"] < 0.0)])

        def dead_key(_m, bridge, _s):
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('s2-r1')}", lambda rows: [r for r in rows if r["row_kind"] != "key_edge"])

        def uncalibrated_look(_m, _b, scen):
            for r in scen:
                if r.get("kind") == "run_meta":
                    r["calib_step_deg"] = 0.5
                    r["eps_look_deg"] = 0.5

        def unobserved_pending_gesture(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}",
                     lambda rows: [dict(r, v9=0.0) if (r["row_kind"] == "act_sample" and r["subject_id"] == "actor_2") else r for r in rows])

        def gk07(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}",
                     lambda rows: [dict(r, v6=0.0, v7=0.5) if r["row_kind"] == "melee_hit" else r for r in rows])

        def melee_dummy_light(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}",
                     lambda rows: [dict(r, state_or_origin="Dummy_Light", v10=0.0) if r["row_kind"] == "melee_hit" else r for r in rows])

        def low_fps(_m, bridge, _s):
            def fn(rows):
                out = [r for r in rows if not (r["row_kind"] == "frame_sample" and r["sandbox_cam_active_b"] == 1
                                               and 1000.0 <= r["take_dtsum_ms"] < 1400.0)]
                frames = sorted([r for r in out if r["row_kind"] == "frame_sample" and r["cli_frame"] >= 0], key=lambda r: r["cli_frame"])
                prev = None
                for r in frames:
                    if prev is not None and r["cli_frame"] > prev + 1 and r["sandbox_cam_active_b"] == 1:
                        shift = r["cli_frame"] - prev - 1
                    else:
                        shift = 0
                    if shift:
                        for q in frames:
                            if q["cli_frame"] >= r["cli_frame"]:
                                q["cli_frame"] -= shift
                    prev = r["cli_frame"]
                return out
            edit_job(bridge, f"job-take_cli_watch_start-{_tid('s1-r1')}", fn)

        def short_post_stop_watch(_m, bridge, _s):
            edit_job(bridge, f"job-take_srv_observe_start-{_tid('s1-r1')}",
                     lambda rows: [r for r in rows if not (r["row_kind"] == "act_sample" and r["subject_id"] == "actor_2" and r["take_dtsum_ms"] >= 4500.0)])

        def observer_capacity(_m, bridge, _s):
            for ev in bridge:
                if ev.get("ev") == "result":
                    ev["result"]["reason"] = "observer_capacity"
                    break

        def hello_build_mismatch(_m, bridge, _s):
            for ev in bridge:
                if ev.get("ev") == "hello":
                    ev["args"]["build"] = "retail"
                    break

        cases = [
            ("wide_clock", wide_clock, "TOM-01"),
            ("no_pre_neg_a1", no_pre_neg_a1, "TOM-01"),
            ("dead_key", dead_key, "TOM-02"),
            ("uncalibrated_look", uncalibrated_look, "TOM-02"),
            ("unobserved_pending_gesture", unobserved_pending_gesture, "TOM-02"),
            ("gk07_damage_with_allow_dmg_0", gk07, "TOM-04"),
            ("melee_dummy_light", melee_dummy_light, "TOM-04"),
            ("low_fps_cam_trace", low_fps, "TOM-05"),
            ("short_post_stop_watch", short_post_stop_watch, "TOM-02"),
            ("observer_capacity", observer_capacity, "TOM-01"),
            ("hello_build_mismatch", hello_build_mismatch, "TOM-01"),
        ]
        for name, mut_fn, expected_missing_cid in cases:
            with self.subTest(case=name):
                verdict = _eval_with(mut_fn)
                self.assertEqual(verdict["exit_code"], 2, f"{name}: {verdict}")
                self.assertEqual(verdict["verdict"], "INCONCLUSO")
                self.assertEqual(_verdict_checks(verdict)[expected_missing_cid]["status"], "missing", f"{name}: {verdict}")

    def test_anti_fabrication_zero_net_ids_and_copied_ids(self):
        def zero_net_id(_m, bridge, _s):
            edit_ops(bridge, "act_observe", lambda a: True,
                     lambda unp: [r.update({"net_id_low": 0, "net_id_high": 0}) for r in unp["rows"]])

        verdict = _eval_with(zero_net_id)
        self.assertEqual(verdict["exit_code"], 1, verdict)
        self.assertEqual(_verdict_checks(verdict)["TOM-05"]["status"], "fail")

        def copied_requested_ids(_m, bridge, _s):
            # el actor_id pedido se copia como observado pero con otra clase real: la correlacion con la fixture lo delata
            edit_ops(bridge, "act_observe", lambda a: True,
                     lambda unp: [r.update({"real_class": "SurvivorM_Other"}) for r in unp["rows"]])

        self.assertNonPass(_eval_with(copied_requested_ids), "TOM-05")

    # ---------------------------------------------------------------- BLOQ 16 (e2e que reevalua las evidencias)
    def _reevaluate_gate_evidence(self, ev_dir, evaluate_fn):
        """Reevalua lo que dejo el runner: la parte sana y cada mutante contra su vector; el `verdict.json` no cuenta."""
        ev = Path(ev_dir)
        run = ev / "run"
        for part in [run] + [ev / f"mut-{m}" for m in s_toma_mutants.EXPECTED_MUTANTS]:
            self.assertTrue((part / "samples" / "bridge.jsonl").is_file(), f"{part}: sin samples/bridge.jsonl")
            self.assertTrue((part / "samples" / "scenario.jsonl").is_file(), f"{part}: sin samples/scenario.jsonl")
            self.assertGreater(len(f03_common.read_jsonl(part / "samples" / "bridge.jsonl")), 100, part)
        v_run = evaluate_fn(run)
        self.assertEqual(v_run["exit_code"], 0, v_run)
        verdicts = {}
        for mname, spec in s_toma_mutants.EXPECTED_MUTANTS.items():
            v = evaluate_fn(ev / f"mut-{mname}")
            self._check_vector(mname, v, spec)
            verdicts[mname] = v
        return v_run, verdicts

    def test_neg_sol16_reevaluation_accepts_a_complete_tree_and_rejects_a_verdict_only_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = Path(tmp) / "ok"
            build_healthy_part(ok / "run", op_nonce="0000000000000001")
            for idx, mname in enumerate(s_toma_mutants.EXPECTED_MUTANTS, start=2):
                build_healthy_part(ok / f"mut-{mname}", mutant=mname, op_nonce=f"{idx:016x}")
            self._reevaluate_gate_evidence(ok, _evaluate)

            forged = Path(tmp) / "forged"
            for part in ["run"] + [f"mut-{m}" for m in s_toma_mutants.EXPECTED_MUTANTS]:
                gate_core.write_json(forged / part / "verdict.json", {"verdict": "PASA", "exit_code": 0})
            with self.assertRaises(AssertionError):
                self._reevaluate_gate_evidence(forged, _evaluate)

            # samples presentes pero un verdict.json mentiroso: lo que cuenta es la reevaluacion
            liar = Path(tmp) / "liar"
            build_healthy_part(liar / "run", op_nonce="0000000000000001")
            for idx, mname in enumerate(s_toma_mutants.EXPECTED_MUTANTS, start=2):
                p = build_healthy_part(liar / f"mut-{mname}", mutant=mname, op_nonce=f"{idx:016x}")
                gate_core.write_json(p / "verdict.json", {"verdict": "FALLA", "exit_code": 1})
            gate_core.write_json(liar / "run" / "verdict.json", {"verdict": "PASA", "exit_code": 0})
            self._reevaluate_gate_evidence(liar, _evaluate)  # pasa porque la evidencia es buena, no por sus verdict.json

            # un mutante cuya evidencia es la sana: la reevaluacion lo detecta (no era FALLA)
            lazy = Path(tmp) / "lazy"
            build_healthy_part(lazy / "run", op_nonce="0000000000000001")
            for idx, mname in enumerate(s_toma_mutants.EXPECTED_MUTANTS, start=2):
                build_healthy_part(lazy / f"mut-{mname}", op_nonce=f"{idx:016x}")
            with self.assertRaises(AssertionError):
                self._reevaluate_gate_evidence(lazy, _evaluate)

    @staticmethod
    def _tee_bridge_registry(registry):
        """Registro INDEPENDIENTE del trafico del nucleo: copia cada evento que `QABridge` entrega a su sumidero."""
        real = f03_common.QABridge

        class _Tee(real):
            def __init__(self, *a, sink=None, **kw):
                def tee(row):
                    registry.append(json.loads(json.dumps(row)))
                    if sink is not None:
                        sink(row)
                super().__init__(*a, sink=tee, **kw)

        return _Tee

    def _assert_bridge_jsonl_equals_core_traffic(self, part_dir, registry):
        written = f03_common.read_jsonl(Path(part_dir) / "samples" / "bridge.jsonl")
        self.assertEqual([json.loads(json.dumps(r)) for r in written], registry,
                         "samples/bridge.jsonl no es el trafico que el nucleo vio: evidencia fabricada")

    def test_neg_sol16_fabricating_runner_is_detected_by_the_independent_core_traffic_registry(self):
        """Un runner que envuelve `PartContext` pero escribe un `bridge.jsonl` ajeno al trafico real es detectado."""
        import argparse
        from unittest import mock

        registry: list = []
        args = argparse.Namespace(build="offline", both=True, ttl_ms=gate_core.DEFAULT_TTL_MS, retry_ms=gate_core.DEFAULT_RETRY_MS,
                                  lease_ms=gate_core.DEFAULT_LEASE_MS, hold_ms=gate_core.DEFAULT_HOLD_MS, seed=gate_core.DEFAULT_SEED,
                                  peer_timeout=20.0, pbo=None, fault=None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(f03_common, "QABridge", self._tee_bridge_registry(registry)):
            base = Path(tmp) / "ev"
            with f03_common.PartContext(base_dir=base, part_name="run", spike_id="S-toma", args=args, argv=[]) as ctx:
                self.assertIsNone(ctx.startup_reason)
            honest = base / "run"
            self._assert_bridge_jsonl_equals_core_traffic(honest, registry)  # el trafico real de un runner honesto coincide
            # el runner fabricador sustituye la traza por la sintetica y deja un verdict.json optimista
            fab = build_healthy_part(Path(tmp) / "fab" / "run")
            shutil_copy = (fab / "samples" / "bridge.jsonl").read_bytes()
            (honest / "samples" / "bridge.jsonl").write_bytes(shutil_copy)
            with self.assertRaises(AssertionError):
                self._assert_bridge_jsonl_equals_core_traffic(honest, registry)
            gate_core.write_json(honest / "verdict.json", {"verdict": "PASA", "exit_code": 0})
            with self.assertRaises(AssertionError):  # y su `verdict.json` tampoco sobrevive a la reevaluacion
                self._reevaluate_gate_evidence(base, _evaluate)

    def test_e2e_m1_gate_spike_s_toma_offline(self):
        """Punta a punta contra `m1_gate.py spike S-toma --both --build offline --evidence`; reevalua lo que deja el runner."""
        from unittest import mock

        registry: list = []
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(f03_common, "QABridge", self._tee_bridge_registry(registry)):
            out_dir = Path(tmp) / "s_toma_e2e"
            rc = m1_gate.main(["spike", "S-toma", "--both", "--build", "offline", "--evidence", str(out_dir)])
            self.assertEqual(rc, 0, "m1_gate spike S-toma offline debe terminar en PASA (exit 0)")
            verdict = gate_core.read_json(out_dir / "verdict.json")
            self.assertEqual(verdict["verdict"], "PASA")
            self.assertEqual(verdict["exit_code"], 0)
            # lo que dice el runner no cuenta: se reevaluan las evidencias de la sana y de cada mutante
            self._reevaluate_gate_evidence(out_dir, s_toma_eval.evaluate)
            # y las trazas son el trafico que el nucleo vio, no un fichero escrito aparte
            self.assertGreater(len(registry), 1000)
            for part in [out_dir / "run"] + [out_dir / f"mut-{m}" for m in s_toma_mutants.EXPECTED_MUTANTS]:
                written = f03_common.read_jsonl(part / "samples" / "bridge.jsonl")
                keys = {json.dumps(r, sort_keys=True) for r in written}
                reg_keys = {json.dumps(r, sort_keys=True) for r in registry}
                self.assertTrue(keys <= reg_keys, f"{part}: filas de bridge.jsonl que el nucleo nunca vio")


    # ---------------------------------------------------------------- T13 contra el peer falso (BLOQ 9)
    def test_e2e_t13_expired_lease_on_fake_peers_blocks_every_take_effect(self):
        """E1.7/T13 con los DOS peers falsos reales, lease propio de 3000 ms y la emision medida en SU reloj.

        Con el lease vencido quedan bloqueados el GO, las ordenes de actor, las cues, los RPC de S-toma y el movimiento
        de la camara; la limpieza de seguridad corre una vez y los dos observadores `continue` siguen observando sin
        emitir. Falla mientras `fake_ext_take.py` sea un esqueleto (no entiende los verbos `take_*`)."""
        import argparse

        args = argparse.Namespace(build="offline", both=True, ttl_ms=gate_core.DEFAULT_TTL_MS, retry_ms=gate_core.DEFAULT_RETRY_MS,
                                  lease_ms=gate_core.DEFAULT_LEASE_MS, hold_ms=gate_core.DEFAULT_HOLD_MS, seed=gate_core.DEFAULT_SEED,
                                  peer_timeout=20.0, pbo=None, fault=None)
        self.assertEqual(gate_core.DEFAULT_LEASE_MS, 3000)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "ev"
            with f03_common.PartContext(base_dir=base, part_name="run", spike_id="S-toma", args=args, argv=[]) as ctx:
                self.assertIsNone(ctx.startup_reason)

                def call(peer, verb, s=None, n=None):
                    out = f03_common.issue_one(ctx, peer, verb, wire.pack_payload(scalars_str=s, scalars_num=n))
                    self.assertEqual(out.status, "done", f"{peer} {verb}: {out.status}/{out.reason}")
                    return out

                tid = "1a2b3c4d-t13"
                call("server", "take_scene_prep", {"op": "apply", "take_id": tid}, {"director_allow_dmg_pre_b": 1, "actor_capable_b": 1,
                                                                                  "director_present_b": 1, "spawn_infected_b": 1})
                call("client", "take_cam_prep", {"op": "load_path", "take_id": tid, "path_hash": "b6_cam_v1_8f3a1c"})
                obs_s = call("server", "take_srv_observe_start", {"take_id": tid}, {"watch_ms": 30000})
                obs_c = call("client", "take_cli_watch_start", {"take_id": tid}, {"watch_ms": 30000})
                arm = call("server", "take_arm", {"take_id": tid, "mode": "common_time"}, {"sched_srv_tick_ms": 1.0e9, "sched_cli_tick_ms": 1.0e9})
                for peer in ("server", "client"):
                    ctx.bridge.cut(peer, 3600)
                ev = ctx.bridge.wait_event(lambda e: e.get("ev") == "cut_end" and e.get("peer") == "client", 8000)
                self.assertIsNotNone(ev)
                st = f03_common.read_job_pages(ctx, "server", arm.payload["str"]["job"])
                self.assertEqual(st["state"], "stopped")
                rows_s = f03_common.read_job_pages(ctx, "server", obs_s.payload["str"]["job"])["rows"]
                rows_c = f03_common.read_job_pages(ctx, "client", obs_c.payload["str"]["job"])["rows"]
                polls = {p: [e for e in ctx.bridge.events if e.get("peer") == p and e.get("ev") in ("poll", "keepalive") and e.get("http") == 200]
                         for p in ("server", "client")}
                cuts = {e["peer"]: e["t_ms"] for e in ctx.bridge.events if e.get("ev") == "cut_start"}
                for peer, rows, tick_key in (("server", rows_s, "srv_tick_ms"), ("client", rows_c, "cli_tick_ms")):
                    last_ok = [e for e in polls[peer] if e["t_ms"] <= cuts[peer]][-1]["tick_s"] * 1000.0
                    expire = last_ok + 3000.0
                    after = [r for r in rows if r[tick_key] > expire]
                    self.assertTrue(after, f"el observador `continue` del {peer} dejo de observar al vencer el lease")
                    self.assertFalse([r for r in after if r["row_kind"] in ("go_sent", "dispatch", "rpc_stop_sent")], peer)
                    self.assertFalse([r for r in after if r["row_kind"] == "rpc_emit" and r["v2"] == 1], peer)
                    self.assertFalse([r for r in after if r["row_kind"] == "frame_sample" and r["sandbox_cam_active_b"] == 1 and r[tick_key] > expire + 50.0], peer)
                self.assertEqual(sum(1 for r in rows_s if r["row_kind"] == "cleanup_done"), 1)
                self.assertEqual(sum(1 for r in rows_c if r["row_kind"] == "cli_safety_exit"), 1)


_PATCHED: dict = {}


def setUpModule():
    """Memoiza las lecturas de git del nucleo (el commit sellado es inmutable): acelera, no cambia ningun resultado."""
    stamp_cache: dict = {}
    params_cache: dict = {}
    real_stamp = f03_common.compute_probe_stamp_at_commit
    real_params = f03_common.verify_eval_params_at_commit

    def stamp(git_head, repo_root=None):
        if git_head not in stamp_cache:
            stamp_cache[git_head] = real_stamp(git_head, repo_root=repo_root)
        return stamp_cache[git_head]

    def params(manifest, repo_root=None):
        key = json.dumps(manifest.get("identity"), sort_keys=True, default=str)
        if key not in params_cache:
            params_cache[key] = real_params(manifest, repo_root=repo_root)
        return params_cache[key]

    real_top = f03_common._git_toplevel
    top_cache: dict = {}

    def toplevel(repo_root):
        key = str(repo_root)
        if key not in top_cache:
            top_cache[key] = real_top(repo_root)
        return top_cache[key]

    _PATCHED.update(stamp=real_stamp, params=real_params, top=real_top)
    f03_common.compute_probe_stamp_at_commit = stamp
    f03_common.verify_eval_params_at_commit = params
    f03_common._git_toplevel = toplevel


def tearDownModule():
    if _PATCHED:
        f03_common.compute_probe_stamp_at_commit = _PATCHED["stamp"]
        f03_common.verify_eval_params_at_commit = _PATCHED["params"]
        f03_common._git_toplevel = _PATCHED["top"]
        _PATCHED.clear()


if __name__ == "__main__":
    unittest.main()
