"""Extension DSBX_QA_X_Actor para fake_peer (prefijo act_, RPC 26102810..26102819).

Homologo Python de la extension de S3 (brief 2026-11-14-m1-f0.3-s3-brief.md §2-§3). Simula un mundo pequeno
(actores, decorado, ambiente, un infectado de combate) y produce lecturas CRUDAS a partir de ese mundo simulado:
posiciones integradas paso a paso, eventos nativos de gesto (callback ligado, OnFinish con su ``pCanceled``,
estado de animacion) y contadores. Ninguna columna se copia de lo pedido ni se calcula como etiqueta.

Relojes: los trabajos de comportamiento (ONCE/HOLD/LOOP/ROAM) integran un reloj virtual (``dtsum_ms``) mas rapido
que el real para que 10 min de ROAM quepan en la prueba offline; el tick de cada fila es ``start_tick + dtsum``.
Los gestos corren en tiempo real del peer (``local_ms``).

Modset: si junto a la configuracion del peer hay ``s3_modset.json`` con ``{"expansion": false}``, el peer arranca
"sin Expansion" (el runner lo escribe antes de relanzar el servidor, como un reinicio con otro modset).
"""

import json
import math
import os
import threading
from pathlib import Path

import wire
from fake_peer import FakeExt

PREFIX = "act_"
RPC_BASE = 26102810

FIX_DIR = Path(__file__).resolve().parent / "fixtures"

VERBS = frozenset(
    {
        "act_env_freeze",
        "act_scene_apply",
        "act_reset",
        "act_observe",
        "act_combat_stage",
        "act_behaviour_run",
        "act_emote_run",
    }
)

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

SPEED = 400.0  # ms virtuales por ms real en los trabajos de comportamiento
VSTEP_MS = 50.0
ONCE_SPEED_MPS = 5.0
WALK_SPEED_MPS = 4.0
STOP_RADIUS_M = 1.3

EMOTE_START_DELAY_MS = 300.0
EMOTE_PLAY_MS = 900.0
EMOTE_DRAIN_MS = 200.0
EMOTE_DRAIN_INTERRUPT_MS = 40.0
EMOTE_CLEANUP_MS = 50.0
EMOTE_LATE_START_MS = 300.0
RETAIN_CAP = 256

CHARACTERS = frozenset(
    ["SurvivorM_" + n for n in (
        "Mirek", "Boris", "Denis", "Elias", "Francis", "Guo", "Hassan", "Indar", "Jose",
        "Kaito", "Lewis", "Manua", "Niki", "Oliver", "Peter", "Quinn", "Rolf", "Seth", "Taiki")]
    + ["SurvivorF_" + n for n in (
        "Eva", "Frida", "Gabi", "Helga", "Irena", "Judy", "Keiko", "Linda", "Maria", "Naomi")]
)
ITEM_SLOT = {
    "RadarCap_Black": "Headgear",
    "BaseballCap_Black": "Headgear",
    "HikingJacket_Black": "Body",
    "CargoPants_Black": "Legs",
    "HunterPants_Autumn": "Legs",
    "AthleticShoes_Black": "Feet",
    "AssaultBag_Black": "Back",
    "Armband_Red": "Armband",
}
DEFAULT_GEAR = (("Shoulder", "DefaultShoulderStrap"),)  # equipo con el que "nace" un actor (se barre)
OBSTACLE = (4510.0, 4530.0, 10335.0, 10350.0)  # hangar: x0, x1, z0, z1 (inalcanzable desde el llano)
URBAN_CENTER = (4600.0, 10300.0)
FACTIONS = {"qa_hostile": "eAIFactionRaiders"}


def _r6(v):
    return round(float(v), 6)


def _r3(v):
    return round(float(v), 3)


def _dist(x1, z1, x2, z2):
    return math.hypot(x2 - x1, z2 - z1)


def _load_catalog():
    try:
        data = json.loads((FIX_DIR / "s3_emotes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    cat = {}
    for entry in data.get("catalog") or []:
        cat[entry["emote_key"]] = (int(entry["emote_id"]), int(entry["cmd_id"]))
    return cat


def _inside_obstacle(x, z):
    return OBSTACLE[0] <= x <= OBSTACLE[1] and OBSTACLE[2] <= z <= OBSTACLE[3]


def _buildings_near(x, z):
    return 5.0 if _dist(x, z, URBAN_CENTER[0], URBAN_CENTER[1]) <= 60.0 else 0.0


def _roam_dest(k, p0, radius, seed, bad):
    """Destino k determinista en el anillo [0.35R, 0.75R] alrededor de P0 (o a 22 m si ``bad``)."""
    ang = (k * 2.399963 + seed * 0.7) % (2.0 * math.pi)
    if bad:
        r = 22.0
    else:
        frac = (k * 0.37 + 0.11 * seed) % 1.0
        r = radius * (0.35 + 0.40 * frac)
    return p0[0] + r * math.cos(ang), p0[1] + r * math.sin(ang)


class Beh:
    """Trabajo de comportamiento sobre un actor: integra el movimiento en tiempo virtual."""

    def __init__(self, ext, jid, actor_id, mode, threat, args, wps, fault):
        self.ext = ext
        self.jid = jid
        self.actor_id = actor_id
        self.mode = mode
        self.threat = threat
        self.fault = fault
        self.step = float(args.get("sample_step_ms", 500.0))
        self.duration = float(args.get("duration_ms", 0.0))
        self.reach_timeout = float(args.get("reach_timeout_ms", 30000.0))
        self.settle_window = float(args.get("settle_window_ms", 10000.0))
        self.radius = float(args.get("radius_m", 15.0))
        self.seed = int(args.get("seed_n", 1.0))
        a = ext.actors[actor_id]
        self.p = [a["x"], a["z"]]
        self.p0 = (a["x"], a["z"])
        self.wps = list(wps)
        self.start_tick = ext.jobs.get_start_tick_ms(jid)
        self.vt = 0.0
        self.carry = 0.0
        self.seq = 0
        self.next_sample = 0.0
        self.state = "en_ruta"
        self.done = False
        self.tidx = 0
        self.dwell_until = -1.0
        self.blocked_ms = 0.0
        self.path_len = 0.0
        self.max_dist = 0.0
        self.dest_reached = 0
        self.legs = 0
        self.ticks_checked = 0
        self.out_ticks = 0
        self.settle_start = None
        self.settle_pos = None
        self.settle_drift = 0.0
        self.roam_k = 0
        if mode in ("ONCE", "LOOP") and self.wps:
            self.target = self.wps[0]
        else:
            self.target = tuple(self.p0)

    # ------------------------------------------------------------------ fisica
    def _walk(self, speed):
        tx, tz = self.target
        d = _dist(self.p[0], self.p[1], tx, tz)
        if d <= STOP_RADIUS_M:
            return True
        step = speed * VSTEP_MS / 1000.0
        nx = self.p[0] + (tx - self.p[0]) * min(1.0, step / d)
        nz = self.p[1] + (tz - self.p[1]) * min(1.0, step / d)
        if _inside_obstacle(nx, nz):
            self.blocked_ms += VSTEP_MS
            return False
        self.path_len += _dist(self.p[0], self.p[1], nx, nz)
        self.p[0], self.p[1] = nx, nz
        return _dist(nx, nz, tx, tz) <= STOP_RADIUS_M

    def _substep(self):
        """Avanza un paso virtual de VSTEP_MS."""
        self.vt += VSTEP_MS
        engaged = self.threat == "require_threat" and self.ext.combat is not None
        if self.mode == "ONCE":
            if not engaged and self.state in ("en_ruta", "en_marca"):
                self._walk(ONCE_SPEED_MPS)
            dm = _dist(self.p[0], self.p[1], self.target[0], self.target[1])
            if self.state == "en_ruta" and dm < 1.5:
                self.state = "en_marca"
                self.settle_start = self.vt
                self.settle_pos = (self.p[0], self.p[1])
            if self.state == "en_ruta":
                if self.blocked_ms >= 3000.0 and not engaged:
                    self.state = "no_alcanzada"
                    self.done = True
                elif self.vt >= self.reach_timeout - 500.0:
                    self.state = "agotado"
                    self.done = True
            if self.state == "en_marca":
                self.settle_drift = max(
                    self.settle_drift, _dist(self.p[0], self.p[1], self.settle_pos[0], self.settle_pos[1])
                )
                if self.vt - self.settle_start >= self.settle_window + self.step + 100.0:
                    self.done = True
        elif self.mode == "HOLD":
            if self.vt >= self.duration:
                self.done = True
        elif self.mode == "LOOP":
            if self.dwell_until >= 0.0:
                if self.vt >= self.dwell_until:
                    self.dwell_until = -1.0
                    self.tidx = (self.tidx + 1) % len(self.wps)
                    self.target = self.wps[self.tidx]
            elif self._walk(WALK_SPEED_MPS):
                self.dest_reached += 1
                self.legs += 1
                self.dwell_until = self.vt + 1000.0
            if self.vt >= self.duration:
                self.done = True
        elif self.mode == "ROAM":
            if self.fault != "roam_stand_still":
                if self.dwell_until >= 0.0:
                    if self.vt >= self.dwell_until:
                        self.dwell_until = -1.0
                        bad = self.fault == "roam_ignore_radius" and self.roam_k == 2
                        self.target = _roam_dest(self.roam_k, self.p0, self.radius, self.seed, bad)
                        self.roam_k += 1
                elif self.roam_k == 0:
                    self.dwell_until = self.vt + 1000.0
                    self.dest_reached += 1
                elif self._walk(WALK_SPEED_MPS):
                    self.dest_reached += 1
                    self.legs += 1
                    self.dwell_until = self.vt + 7000.0
            dc = _dist(self.p[0], self.p[1], self.p0[0], self.p0[1])
            if dc > self.radius:
                self.out_ticks += 1
            if self.vt >= self.duration:
                self.done = True
        dc = _dist(self.p[0], self.p[1], self.p0[0], self.p0[1])
        self.max_dist = max(self.max_dist, dc)
        self.ticks_checked += 1
        a = self.ext.actors.get(self.actor_id)
        if a is not None:
            a["x"], a["z"] = self.p[0], self.p[1]

    # ------------------------------------------------------------------ filas
    def row(self):
        self.seq += 1
        tx, tz = self.target
        dm = _dist(self.p[0], self.p[1], tx, tz)
        tick = self.start_tick + self.vt
        state = self.state
        if self.mode == "ONCE" and self.fault == "fsm_is_final_as_reached" and self.done and state != "en_marca":
            state = "en_marca"  # defecto inyectado: toma el fin de la FSM por llegada
        comb = self.ext.combat_cols(self.actor_id, self.vt / 1000.0, tick)
        settle_dtsum = 0.0 if self.settle_start is None else self.vt - self.settle_start
        nums = [
            self.seq, self.ext.peer.frame, _r3(tick), _r3(self.vt),
            _r6(self.p[0]), 0.0, _r6(self.p[1]),
            _r6(tx), 0.0, _r6(tz),
            _r6(_dist(self.p[0], self.p[1], self.p0[0], self.p0[1])), _r6(self.max_dist),
            _r6(dm), _r3(settle_dtsum), _r6(self.settle_drift), _r6(self.path_len),
            self.dest_reached, self.legs, _buildings_near(self.p0[0], self.p0[1]), self.ticks_checked,
            self.out_ticks, comb["fighting"], comb["raised"],
            comb["actor_health"], comb["inf_health"], comb["disp"], comb["obs_tick"],
        ]
        return nums, [state, comb["faction"], comb["infected_id"]]

    def advance(self, real_dt_ms):
        self.carry += real_dt_ms * SPEED
        while not self.done and self.carry >= VSTEP_MS:
            self.carry -= VSTEP_MS
            if self.vt >= self.next_sample:
                n, s = self.row()
                self.ext.jobs.append_row(self.jid, n, s)
                self.next_sample += self.step
            self._substep()
        if self.done:
            n, s = self.row()
            self.ext.jobs.append_row(self.jid, n, s)
            return True
        return False


class Req:
    """Una peticion de gesto sobre un actor (un monitor por peticion, vive en el peer)."""

    def __init__(self, ext, seq, actor_id, key, case, fault, now, args):
        self.ext = ext
        self.seq = seq
        self.actor_id = actor_id
        self.key = key
        self.case = case
        self.fault = fault
        self.eid, self.cmd = ext.catalog[key]
        self.t_req = now
        self.step = float(args.get("sample_step_ms", 250.0))
        self.start_timeout = float(args.get("start_timeout_ms", 5000.0))
        self.post_watch = float(args.get("post_watch_ms", 3000.0))
        self.row_seq = 0
        self.periodic_seq = 0
        self.next_periodic = now + self.step
        self.cb_max = ext.cb_counter
        self.cb = 0
        self.obs_id = 0
        self.anim_cmd = 0
        self.anim_state = 0
        self.on_finish = 0
        self.raw_p = -1
        self.cancel_requested = 0
        self.blocked = case in ("never_starts", "cancel_before_start", "stale_callback_isolation")
        self.playing = 0
        self.cb_present = 0
        self.pending = self.eid
        self.post_cb = 0
        self.foreign = 0
        self.req_tick = now
        self.start_tick = 0.0
        self.cancel_tick = 0.0
        self.end_tick = 0.0
        self.cleanup_tick = 0.0
        self.cause = ""
        self.state = "pedido"
        self.start_due = None if (self.blocked or case == "require_combat") else now + EMOTE_START_DELAY_MS
        if case == "interrupt_between_samples":
            self.start_due = None
        self.finish_due = None
        self.drain_due = None
        self.cleanup_due = None
        self.late_due = None
        self.old_cb = 0
        self.old_due = None
        self.job = None
        self.post_job = None
        self.retained = []
        self.post_claimed = False
        self.done_at = None
        self.drain_ms = EMOTE_DRAIN_MS
        self.interrupt_phase = 0
        self.interrupt_due = None
        self.canceled_label = ""

    # ------------------------------------------------------------------ lectura
    def can_play(self):
        return 0 if self.blocked else 1

    def row(self, kind, now):
        self.row_seq += 1
        p_seq = 0
        if kind == "periodic":
            self.periodic_seq += 1
            p_seq = self.periodic_seq
        ext = self.ext
        elapsed = (now - ext.combat_t0) / 1000.0 if ext.combat else 0.0
        comb = ext.combat_cols(self.actor_id, elapsed, now)
        state, raw, cause = self.state, self.raw_p, self.cause
        if self.fault == "canceled_as_done" and self.on_finish and self.state == "cancelado":
            state, raw, cause = "terminado", 0, "cb_normal"  # defecto: falsea solo las filas exportadas
        nums = [
            self.row_seq, p_seq, ext.peer.frame, _r3(now), _r3(now - self.t_req), self.seq,
            self.cb, self.cb_max, self.eid, self.obs_id,
            self.cmd, self.anim_cmd, self.anim_state, self.on_finish,
            raw, self.cancel_requested, 0, 0 if self.blocked else 1,
            self.can_play(), self.playing, self.cb_present, self.pending,
            self.post_cb, self.foreign, _r3(self.req_tick), _r3(self.start_tick),
            _r3(self.cancel_tick), _r3(self.end_tick), _r3(self.cleanup_tick), comb["fighting"],
            comb["raised"], comb["actor_health"], comb["inf_health"], comb["disp"],
            comb["obs_tick"],
        ]
        svals = [self.key, kind, state, cause, comb["infected_id"], comb["faction"]]
        return nums, svals

    def emit(self, kind, now):
        nums, svals = self.row(kind, now)
        for jid in (self.job, self.post_job):
            if jid is not None and self.ext.jobs.get_state(jid) == "running":
                self.ext.jobs.append_row(jid, nums, svals)
                return
        self.retained.append((nums, svals))
        while len(self.retained) > RETAIN_CAP:
            self.retained.pop(0)

    # ------------------------------------------------------------------ transiciones nativas
    def bind_callback(self, now):
        """DsbxOnBound + OnStateChange(STATE_NONE -> STATE_NORMAL)."""
        self.ext.cb_counter += 1
        late = self.cancel_requested == 1
        if late:
            self.post_cb += 1
        else:
            self.cb = self.ext.cb_counter
        wrong = self.fault == "wrong_emote_played" and not late
        self.obs_id = 59 if wrong else self.eid
        self.anim_cmd = 1110 if wrong else self.cmd
        self.anim_state = 7
        self.start_tick = now
        self.playing = 1
        self.cb_present = 1
        if not late:
            self.state = "en_curso"
        self.emit("event", now)

    def finish_normal(self, now):
        self.on_finish = 1
        self.raw_p = 0
        self.cause = "cb_normal"
        self.end_tick = now
        self.pending = 0
        self.playing = 0
        self.cb_present = 0
        self.state = "terminado"
        self.emit("event", now)

    def cancel(self, now, cause):
        if self.cancel_requested:
            return
        self.cancel_requested = 1
        self.cancel_tick = now
        no_clear = (self.fault == "no_clear_on_timeout" and cause == "timeout") or (
            self.fault == "no_clear_after_start" and self.cb_present
        )
        if not no_clear:
            self.pending = 0
        if self.blocked:
            self.blocked = False  # retira el objeto pesado de las manos
        self.canceled_label = "agotado" if cause == "timeout" else "cancelado"
        if self.cb_present:
            self.drain_due = now + self.drain_ms
            self.state = "en_curso"
        else:
            self.state = self.canceled_label
            self.cleanup_tick = now
            if self.pending != 0:
                self.late_due = now + EMOTE_LATE_START_MS
        self.emit("event", now)

    def on_finish_canceled(self, now):
        self.on_finish = 1
        self.raw_p = 1
        self.cause = "cb_canceled"
        self.end_tick = now
        self.state = self.canceled_label
        self.emit("event", now)
        self.cleanup_due = now + EMOTE_CLEANUP_MS

    def cleanup(self, now):
        self.playing = 0
        self.cb_present = 0
        self.cleanup_tick = now
        self.emit("event", now)

    # ------------------------------------------------------------------ avance
    def tick(self, now):
        ext = self.ext
        if self.old_due is not None and now >= self.old_due:
            self.old_due = None
            self.foreign += 1
            if self.fault == "accept_stale_cb":
                # defecto: atribuye el OnFinish del callback anterior a la peticion nueva
                self.cb = self.old_cb
                self.obs_id = self.eid
                self.anim_cmd = self.cmd
                self.anim_state = 7
                self.start_tick = now
                self.on_finish = 1
                self.raw_p = 0
                self.cause = "cb_normal"
                self.end_tick = now
                self.state = "terminado"
            self.emit("event", now)
        if self.start_due is not None and now >= self.start_due and not self.cancel_requested:
            self.start_due = None
            self.bind_callback(now)
            if self.case == "normal":
                self.finish_due = now + EMOTE_PLAY_MS
        if self.late_due is not None and now >= self.late_due:
            self.late_due = None
            self.bind_callback(now)
            self.finish_due = now + EMOTE_PLAY_MS
        if self.finish_due is not None and now >= self.finish_due:
            self.finish_due = None
            if self.cancel_requested:
                self.playing = 0
                self.cb_present = 0
                self.emit("event", now)
            else:
                self.finish_normal(now)
                self.done_at = now + 100.0
        if self.case == "never_starts" and not self.cancel_requested and now >= self.t_req + self.start_timeout:
            self.cancel(now, "timeout")
        if self.interrupt_due is not None and now >= self.interrupt_due:
            self.interrupt_due = None
            if self.cb_present and not self.cancel_requested:
                self.cancel(now, "interrupt")
        if self.drain_due is not None and now >= self.drain_due:
            self.drain_due = None
            self.on_finish_canceled(now)
        if self.cleanup_due is not None and now >= self.cleanup_due:
            self.cleanup_due = None
            self.cleanup(now)
        if self.case == "require_combat" and self.state == "pedido" and now >= self.t_req + 300.0:
            self.state = "rechazado"
            self.emit("event", now)
            self.done_at = now + 1000.0
            if self.fault == "combat_emote_as_done":
                # defecto: ignora el combate y marca el gesto como terminado
                self.on_finish = 1
                self.raw_p = 0
                self.cause = "cb_normal"
                self.end_tick = now
                self.state = "terminado"
                self.emit("event", now)
        running = any(j is not None and ext.jobs.get_state(j) == "running" for j in (self.job, self.post_job))
        while running and now >= self.next_periodic:
            self.next_periodic += self.step
            self.emit("periodic", now)
            if self.case == "interrupt_between_samples" and self.periodic_seq == 1 and self.interrupt_phase == 0:
                # la peticion arranca justo despues de la muestra P_1 y se cancela mucho antes de P_2
                self.interrupt_phase = 1
                self.drain_ms = EMOTE_DRAIN_INTERRUPT_MS
                self.start_due = now + 30.0
                self.interrupt_due = now + 100.0


class ActorFakeExt(FakeExt):
    def __init__(self):
        self.peer = None
        self.jobs = None
        self.expansion = True
        self.catalog = {}
        self.core_start = 0.0
        self.reg_tick = 0.0
        self.force_unavailable = False
        self.props_n = 0
        self.actors = {}
        self.env = {"frozen": 0.0, "hour": 12.0, "minute": 0.0, "fog": 0.0, "overcast": 0.0, "rain": 0.0}
        self.last = {}
        self._clear_last("")
        self.mutations = 0
        self.combat = None
        self.combat_t0 = 0.0
        self.behs = {}
        self.reqs = {}
        self.actor_reqs = {}
        self.job_reqs = {}
        self.cb_counter = 0
        self.req_counter = 0
        self._exp_cache = None
        self._flag_path = None
        self._ticks_n = 0

    def _clear_last(self, op_id):
        self.last = {
            "id": op_id, "status": "", "reason": "", "validate": 0.0, "cap_drop": 0.0, "revalidate": 0.0,
            "first_effect": -1.0, "reject": 0.0, "props": 0.0, "actors": 0.0, "deleted": 0.0, "env": 0.0,
        }

    # ------------------------------------------------------------------ ciclo de vida
    def init(self, peer, jobs):
        self.peer = peer
        self.jobs = jobs
        self.catalog = _load_catalog()
        self.core_start = max(0.001, peer.local_ms())
        try:
            cfg = Path(str(peer.config))
            self._flag_path = cfg.parent / "s3_restart.flag"
            modset = json.loads((cfg.parent / "s3_modset.json").read_text(encoding="utf-8"))
            self.expansion = bool(modset.get("expansion", True))
        except (OSError, ValueError, TypeError):
            self.expansion = True

    def handles(self, verb, role):
        return role == "server" and verb in VERBS

    def _available(self):
        return self.expansion and not self.force_unavailable

    def _ensure_reg(self):
        if self.expansion and self.reg_tick == 0.0:
            self.reg_tick = max(self.core_start, self.peer.local_ms())

    def _now(self):
        return self.peer.local_ms()

    # ------------------------------------------------------------------ combate (lecturas)
    def combat_cols(self, actor_id, elapsed_s, tick):
        c = self.combat
        if c is None or c["actor_id"] != actor_id:
            return {"fighting": 0.0, "raised": 0.0, "actor_health": 100.0 if actor_id in self.actors else 0.0,
                    "inf_health": 0.0, "disp": 0.0, "obs_tick": 0.0, "faction": "", "infected_id": ""}
        return {
            "fighting": 1.0,
            "raised": 1.0,
            "actor_health": _r3(max(1.0, 100.0 - 0.5 * elapsed_s)),
            "inf_health": _r3(max(1.0, 100.0 - 0.8 * elapsed_s)),
            "disp": _r3(0.3 * elapsed_s),
            "obs_tick": _r3(tick),
            "faction": c["faction_class"],
            "infected_id": c["infected_id"],
        }

    # ------------------------------------------------------------------ ordenes
    def on_start_op(self, op, args_unpacked, raw_args):
        verb = op["verb"]
        self._ensure_reg()
        if verb == "act_observe":
            return self._observe()
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        if verb == "act_env_freeze":
            return self._env_freeze(args_unpacked)
        if verb == "act_scene_apply":
            return self._scene_apply(op, args_unpacked)
        if verb == "act_reset":
            return self._reset()
        if verb == "act_combat_stage":
            return self._combat_stage(args_unpacked)
        if verb == "act_behaviour_run":
            return self._behaviour_run(op, args_unpacked)
        if verb == "act_emote_run":
            return self._emote_run(op, args_unpacked)
        return ("rejected", "unknown_verb", wire.empty_payload())

    def _bad(self):
        return ("rejected", "bad_args", wire.empty_payload())

    def _env_freeze(self, au):
        nums = au["num"]
        if "freeze_b" not in nums or float(nums["freeze_b"]) not in (0.0, 1.0):
            return self._bad()
        frozen = float(nums["freeze_b"])
        for key, env_key in (("hour_n", "hour"), ("minute_n", "minute"), ("fog", "fog"),
                             ("overcast", "overcast"), ("rain", "rain")):
            if key in nums:
                self.env[env_key] = float(nums[key])
                self.mutations += 1
        if self.env["frozen"] != frozen:
            self.mutations += 1
        self.env["frozen"] = frozen
        payload = wire.pack_payload(
            scalars_num={
                "weather_frozen_b": self.env["frozen"], "hour_n": self.env["hour"], "minute_n": self.env["minute"],
                "fog": self.env["fog"], "overcast": self.env["overcast"], "rain": self.env["rain"],
                "tick_ms": _r3(self._now()), "frame": self.peer.frame,
            }
        )
        return ("done", "", payload)

    def _exp_stamp(self):
        if self._exp_cache is None:
            import s3_eval

            self._exp_cache = s3_eval.compute_exp_stamp_at_commit(self.peer.git_head)
        return self._exp_cache

    def _observe(self):
        now = self._now()
        rows = []
        for aid, a in sorted(self.actors.items()):
            for slot, item in a["items"]:
                rows.append({"x_m": _r6(a["x"]), "y_m": 0.0, "z_m": _r6(a["z"]), "health_01": 1.0,
                             "actor_id": aid, "real_class": a["real_class"], "slot_name": slot, "item_class": item})
        avail = self._available()
        strs = {
            "core_ver": self.peer.resolve_probe_ver(),
            "adapter_ver": ("dsbx-qa-exp1+" + self._exp_stamp()) if avail else "",
            "backend_class": "DSBX_QA_ExpansionBackend" if avail else "",
            "last_op_id": self.last["id"], "last_op_status": self.last["status"],
            "last_op_reason": self.last["reason"],
        }
        nums = {
            "core_loaded_b": 1.0, "backend_available_b": 1.0 if avail else 0.0,
            "core_start_tick_ms": _r3(self.core_start), "adapter_reg_tick_ms": _r3(self.reg_tick),
            "weather_frozen_b": self.env["frozen"], "world_props_n": float(self.props_n),
            "world_actors_n": float(len(self.actors)), "hour_n": self.env["hour"], "minute_n": self.env["minute"],
            "fog": self.env["fog"], "overcast": self.env["overcast"], "rain": self.env["rain"],
            "last_op_validate_tick_ms": self.last["validate"], "last_op_cap_drop_tick_ms": self.last["cap_drop"],
            "last_op_revalidate_tick_ms": self.last["revalidate"],
            "last_op_first_effect_tick_ms": self.last["first_effect"],
            "last_op_reject_tick_ms": self.last["reject"],
            "last_op_spawned_props_ever_n": self.last["props"], "last_op_spawned_actors_ever_n": self.last["actors"],
            "last_op_deleted_objects_ever_n": self.last["deleted"], "last_op_env_writes_ever_n": self.last["env"],
            "total_mutations_seq_n": float(self.mutations), "tick_ms": _r3(now), "frame": self.peer.frame,
        }
        return ("done", "", wire.pack_payload(strs, nums, O_NCOLS, O_SCOLS, rows))

    # ------------------------------------------------------------------ escena
    def _first_effect(self):
        if self.last["first_effect"] < 0.0:
            self.last["first_effect"] = _r3(self._now())

    def _reject(self, reason):
        self.last["reject"] = _r3(self._now())
        self.last["status"], self.last["reason"] = "rejected", reason
        return ("rejected", reason, wire.empty_payload())

    def _scene_apply(self, op, au):
        strs, nums, rows = au["str"], au["num"], au["rows"]
        mode = strs.get("cap_mode")
        if mode not in ("normal", "no_expansion", "drop_after_validate") or "props_n" not in nums:
            return self._bad()
        props_n = int(nums["props_n"])
        if props_n < 0 or float(nums["props_n"]) != props_n:
            return self._bad()
        fault = op.get("qa_fault", "")
        self._clear_last(op["op_id"])
        # etapa 1: validar (clases, ranuras, capacidad), sin tocar el mundo
        self.last["validate"] = _r3(self._now())
        parsed = []
        for row in rows:
            aid, char = row.get("actor_id"), row.get("character")
            if not isinstance(aid, str) or aid == "" or not isinstance(char, str):
                return self._bad()
            if char not in CHARACTERS:
                return self._reject("unknown_class")
            items = []
            for pair in [p for p in (row.get("wardrobe_spec") or "").split(";") if p]:
                if ":" not in pair:
                    return self._bad()
                slot, item = pair.split(":", 1)
                if item not in ITEM_SLOT:
                    return self._reject("unknown_class")
                if ITEM_SLOT[item] != slot:
                    return self._reject("incompatible_slot")
                items.append((slot, item))
            parsed.append((aid, char, row, items))
        if parsed and (mode == "no_expansion" or not self._available()):
            return self._reject("expansion_unavailable")
        for aid, _c, _r, _i in parsed:
            if aid in self.actors:
                return self._reject("busy")
        # etapa 2: puerta previa a los efectos (la capacidad puede caer entre validar y aplicar)
        if mode == "drop_after_validate" and parsed:
            self.last["cap_drop"] = _r3(self._now())
            self.force_unavailable = True
            self.last["revalidate"] = _r3(self._now())
            if fault == "props_before_actor_check":
                # defecto: crea el decorado y escribe ambiente antes de mirar la capacidad, y luego compensa
                self._first_effect()
                self.last["props"] += props_n
                self.last["deleted"] += props_n
                self.mutations += 2 * props_n
                if "fog" in nums:
                    self.last["env"] += 1
                    self.mutations += 2
            return self._reject("expansion_unavailable")
        # etapa 3: efectos
        self._first_effect()
        self.props_n += props_n
        self.last["props"] += props_n
        self.mutations += props_n
        for key, env_key in (("hour_n", "hour"), ("minute_n", "minute"), ("fog", "fog"),
                             ("overcast", "overcast"), ("rain", "rain")):
            if key in nums:
                self.env[env_key] = float(nums[key])
                self.last["env"] += 1
                self.mutations += 1
        seeded = total = cleared = 0
        state, failed = "observado", ""
        fail_slot = strs.get("fail_slot", "")
        seed = float(nums.get("seed_pre_gear_b", 0.0)) == 1.0
        for aid, char, row, items in parsed:
            a = {"x": float(row.get("x_m", 0.0)), "z": float(row.get("z_m", 0.0)), "real_class": "eAI_" + char,
                 "items": list(DEFAULT_GEAR)}
            if seed:
                a["items"].append(("Armband", "Armband_Red"))
                seeded += 1
            total += len(a["items"])
            if fault != "extra_default_gear":  # el defecto omite el barrido y deja el equipo previo
                cleared += len(a["items"])
                a["items"] = []
            for slot, item in items:
                if fail_slot and slot == fail_slot and state == "observado":
                    state, failed = "parcial", f"{aid}:{slot}:{item}"
                    continue
                a["items"].append((slot, item))
            self.actors[aid] = a
            self.last["actors"] += 1
            self.mutations += 1
        payload = wire.pack_payload(
            scalars_str={"apply_state": state, "failed_item": failed[:1000]},
            scalars_num={
                "backend_available_b": 1.0 if self._available() else 0.0,
                "created_props_n": float(props_n), "created_actors_n": float(len(parsed)),
                "pre_gear_seeded_n": float(seeded), "pre_sweep_total_n": float(total),
                "pre_gear_cleared_n": float(cleared), "tick_ms": _r3(self._now()), "frame": self.peer.frame,
            },
        )
        self.last["status"] = "done"
        return ("done", "", payload)

    def _reset(self):
        self._clear_last("")
        for jid in list(self.behs):
            if self.jobs.get_state(jid) == "running":
                self.jobs.end_job(jid, "stopped", "reset")
        deleted_actors, deleted_props = len(self.actors), self.props_n
        infected = 1 if self.combat is not None else 0
        self.actors.clear()
        self.props_n = 0
        self.combat = None
        self.force_unavailable = False
        self.mutations += deleted_actors + deleted_props + infected
        payload = wire.pack_payload(
            scalars_num={
                "deleted_actors_n": float(deleted_actors), "deleted_props_n": float(deleted_props),
                "deleted_infected_n": float(infected), "tick_ms": _r3(self._now()), "frame": self.peer.frame,
            }
        )
        return ("done", "", payload)

    def _combat_stage(self, au):
        strs, nums = au["str"], au["num"]
        aid = strs.get("actor_id")
        fkey, cls = strs.get("faction_key"), strs.get("infected_class")
        if not aid or not fkey or not cls or "dist_m" not in nums:
            return self._bad()
        if aid not in self.actors:
            return ("rejected", "unknown_actor", wire.empty_payload())
        if not self._available():
            return ("rejected", "expansion_unavailable", wire.empty_payload())
        if fkey not in FACTIONS:
            return self._bad()
        a = self.actors[aid]
        dist = float(nums["dist_m"])
        self.combat = {"actor_id": aid, "faction_class": FACTIONS[fkey], "infected_id": "infected_1"}
        self.combat_t0 = self._now()
        self.mutations += 1
        payload = wire.pack_payload(
            scalars_str={"infected_id": "infected_1", "faction_class": FACTIONS[fkey]},
            scalars_num={
                "init_dist_m": _r6(dist), "actor_health_init": 100.0, "inf_health_init": 100.0,
                "inf_x0_m": _r6(a["x"] + dist), "inf_z0_m": _r6(a["z"]),
                "tick_ms": _r3(self._now()), "frame": self.peer.frame,
            },
        )
        return ("done", "", payload)

    # ------------------------------------------------------------------ comportamiento
    def _behaviour_run(self, op, au):
        strs, nums, rows = au["str"], au["num"], au["rows"]
        aid, mode = strs.get("actor_id"), strs.get("mode")
        if not aid or not mode or "sample_step_ms" not in nums or float(nums["sample_step_ms"]) <= 0.0:
            return self._bad()
        threat = strs.get("threat_case", "none")
        if threat not in ("none", "require_threat"):
            return self._bad()
        if mode not in ("ONCE", "HOLD", "LOOP", "ROAM"):
            return ("rejected", "unknown_mode", wire.empty_payload())
        if aid not in self.actors:
            return ("rejected", "unknown_actor", wire.empty_payload())
        if not self._available():
            return ("rejected", "expansion_unavailable", wire.empty_payload())
        wps = [(float(r["wp_x_m"]), float(r["wp_z_m"])) for r in rows if "wp_x_m" in r and "wp_z_m" in r]
        if mode == "ONCE" and not wps:
            return self._bad()
        if mode == "LOOP" and len(wps) < 2:
            return self._bad()
        if mode in ("HOLD", "LOOP", "ROAM") and float(nums.get("duration_ms", 0.0)) <= 0.0:
            return self._bad()
        jid = op["op_id"]
        err = self.jobs.start_job(self, jid, "actor:" + aid, list(B_NCOLS), list(B_SCOLS), 4, 4096,
                                  900000.0, "stop")
        if err:
            return ("rejected", err, wire.empty_payload())
        self.behs[jid] = Beh(self, jid, aid, mode, threat, nums, wps, op.get("qa_fault", ""))
        return ("done", "", self.jobs.fill_start_read(jid, "actor:" + aid))

    # ------------------------------------------------------------------ gestos
    def _emote_run(self, op, au):
        strs, nums = au["str"], au["num"]
        aid, key, case = strs.get("actor_id"), strs.get("emote_key"), strs.get("test_case")
        cases = ("normal", "require_combat", "cancel_before_start", "cancel_after_start", "post_stop_watch",
                 "interrupt_between_samples", "never_starts", "stale_callback_isolation")
        if not aid or not key or case not in cases:
            return self._bad()
        if aid not in self.actors:
            return ("rejected", "unknown_actor", wire.empty_payload())
        if key not in self.catalog:
            return ("rejected", "unknown_emote", wire.empty_payload())
        if not self._available():
            return ("rejected", "expansion_unavailable", wire.empty_payload())
        now = self._now()
        jid = op["op_id"]
        resource = "actor:" + aid
        if case == "post_stop_watch":
            prev = self.actor_reqs.get(aid)
            if prev is None or prev.post_claimed or not prev.cancel_requested:
                return self._bad()
            err = self.jobs.start_job(self, jid, resource, list(E_NCOLS), list(E_SCOLS), 4, 4096, 900000.0, "stop")
            if err:
                return ("rejected", err, wire.empty_payload())
            prev.post_claimed = True
            prev.post_job = jid
            prev.post_watch = float(nums.get("post_watch_ms", 3000.0))
            prev.step = float(nums.get("sample_step_ms", prev.step))
            prev.next_periodic = now + prev.step
            self.job_reqs[jid] = prev
            for n, s in prev.retained:
                self.jobs.append_row(jid, n, s)
            prev.retained = []
            return ("done", "", self.jobs.fill_start_read(jid, resource))
        if case == "require_combat" and (self.combat is None or self.combat["actor_id"] != aid):
            return ("rejected", "bad_args", wire.empty_payload())
        err = self.jobs.start_job(self, jid, resource, list(E_NCOLS), list(E_SCOLS), 4, 4096, 900000.0, "stop")
        if err:
            return ("rejected", err, wire.empty_payload())
        self.req_counter += 1
        req = Req(self, self.req_counter, aid, key, case, op.get("qa_fault", ""), now, nums)
        req.job = jid
        if case == "stale_callback_isolation":
            self.cb_counter += 1
            req.old_cb = self.cb_counter
            req.cb_max = self.cb_counter
            req.old_due = now + 500.0
        self.reqs[req.seq] = req
        self.actor_reqs[aid] = req
        self.job_reqs[jid] = req
        req.emit("event", now)
        return ("done", "", self.jobs.fill_start_read(jid, resource))

    # ------------------------------------------------------------------ ticks
    def _graceful_exit(self):
        """Reinicio del servidor pedido por el runner: cierra sin dejar una peticion HTTP a medias."""
        self.peer.alive = False
        for thr in threading.enumerate():
            if "_http_loop" in thr.name:
                thr.join(10.0)
        os._exit(0)

    def on_tick(self, timeslice_s):
        self._ensure_reg()
        self._ticks_n += 1
        if self._flag_path is not None and self._ticks_n % 6 == 0 and self._flag_path.exists():
            self._graceful_exit()
        now = self._now()
        dt_ms = float(timeslice_s) * 1000.0
        for jid in list(self.behs):
            beh = self.behs[jid]
            if self.jobs.get_state(jid) != "running":
                self.behs.pop(jid, None)
                continue
            if self.jobs.is_deadman_tripped(jid):
                self.jobs.end_job(jid, "failed", "lease_expired")
                continue
            if beh.advance(dt_ms):
                self.jobs.end_job(jid, "done", "")
        for req in list(self.reqs.values()):
            for j in (req.job, req.post_job):
                if j is not None and self.jobs.get_state(j) == "running" and self.jobs.is_deadman_tripped(j):
                    self.jobs.end_job(j, "failed", "lease_expired")
            req.tick(now)
            if req.job is not None and self.jobs.get_state(req.job) == "running":
                if req.done_at is not None and now >= req.done_at:
                    self.jobs.end_job(req.job, "done", "")
                elif now - req.t_req >= 60000.0:
                    self.jobs.end_job(req.job, "done", "")
            if req.post_job is not None and self.jobs.get_state(req.post_job) == "running":
                if (req.cleanup_tick > 0.0 and now - req.cleanup_tick >= req.post_watch) or (
                    req.cancel_requested and now - req.cancel_tick >= 1000.0 + req.post_watch
                ):
                    req.emit("periodic", now)
                    self.jobs.end_job(req.post_job, "done", "")
            if now - req.t_req > 180000.0:
                self.reqs.pop(req.seq, None)

    def on_job_end(self, job_id, state, reason):
        self.behs.pop(job_id, None)
        req = self.job_reqs.get(job_id)
        if req is None or job_id != req.job:
            return
        # parada o fallo: la limpieza de seguridad corre siempre (retira la peticion y el objeto pesado)
        if state in ("stopped", "failed", "expired") and not req.cancel_requested:
            req.cancel(self._now(), "stop")

    def on_rpc(self, rpc_type, payload):
        pass

    def on_shutdown(self):
        self.behs.clear()
        self.reqs.clear()


def create_ext(peer, jobs):
    return ActorFakeExt()
