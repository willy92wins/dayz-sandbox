"""Motor de actores falso en memoria para F3 sin juego (brief F3-offline-1 §5).

Simula aparicion con vestuario del catalogo, marcas (ONCE, LOOP, HOLD, ROAM),
eventos de gesto y fallos inyectables con un reloj determinista inyectado.
Sin red ni hilos; solo biblioteca estandar.
"""
from __future__ import annotations

import hashlib
import math

_YAW_MDEG_MOD = 360000
_SPEED_MPS = 1.4
_ARRIVE_DIST_M = 0.3
_ROAM_STOP_MS = 1500
_DEFAULT_GESTURE_MS = 2000


def _is_int(val: object) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _m_to_mm(val: float | int) -> int:
    return round(float(val) * 1000)


def _yaw_to_mdeg(val: float | int) -> int:
    return round(float(val) * 1000) % _YAW_MDEG_MOD


class FakeClock:
    """Reloj determinista que avanza a mano en milisegundos (§5)."""

    def __init__(self, initial_ms: int = 0) -> None:
        if not _is_int(initial_ms) or initial_ms < 0:
            raise ValueError("initial_ms debe ser un entero >= 0")
        self._now_ms = int(initial_ms)

    def now_ms(self) -> int:
        return self._now_ms

    def advance(self, dt_ms: int) -> int:
        if not _is_int(dt_ms) or dt_ms < 0:
            raise ValueError("dt_ms debe ser un entero >= 0")
        self._now_ms += int(dt_ms)
        return self._now_ms


class _ActorState:
    __slots__ = (
        "lid",
        "cls",
        "x",
        "y",
        "z",
        "base_x",
        "base_z",
        "spawn_x",
        "spawn_z",
        "yaw",
        "items",
        "marks",
        "behaviour",
        "roam",
        "mark_i",
        "mark_st",
        "fault_stopped",
        "jitter_sign",
        "roam_k",
        "roam_target",
        "roam_wait_ms",
    )

    def __init__(
        self,
        lid: str,
        cls: str,
        x: float,
        z: float,
        yaw: float,
        items: list[str],
    ) -> None:
        self.lid = lid
        self.cls = cls
        self.x = float(x)
        self.y = 0.0
        self.z = float(z)
        self.base_x = float(x)
        self.base_z = float(z)
        self.spawn_x = float(x)
        self.spawn_z = float(z)
        self.yaw = float(yaw)
        self.items = list(items)
        self.marks: list[dict[str, float]] = []
        self.behaviour = "HOLD"
        self.roam = 15.0
        self.mark_i = -1
        self.mark_st = "idle"
        self.fault_stopped = False
        self.jitter_sign = -1
        self.roam_k = 0
        self.roam_target: tuple[float, float] | None = None
        self.roam_wait_ms = 0


class _GestureTask:
    __slots__ = ("lid", "gi", "emote", "duration_ms", "t_req", "t_play", "state")

    def __init__(self, lid: str, gi: int, emote: str, duration_ms: int, t_req: int) -> None:
        self.lid = lid
        self.gi = gi
        self.emote = emote
        self.duration_ms = duration_ms
        self.t_req = t_req
        self.t_play: int | None = None
        self.state = "requested"


class FakeActorEngine:
    """Motor de actores falso en memoria con fallos inyectables (§5)."""

    def __init__(self, catalog: dict, clock: FakeClock | None = None) -> None:
        if not isinstance(catalog, dict):
            raise ValueError("catalog debe ser un dict")
        self.catalog = catalog
        self.clock = clock if clock is not None else FakeClock()
        self._actors: dict[str, _ActorState] = {}
        self._gestures: list[list] = []
        self._gesture_tasks: list[_GestureTask] = []

        # Fallos inyectables (§5)
        self._mark_faults: dict[tuple[str, int], tuple[float, str]] = {}
        self._jitter_amp: dict[str, float] = {}
        self._combat: set[str] = set()
        self._cancel_after_start: set[tuple[str, int]] = set()
        self._finish_without_start: set[tuple[str, int]] = set()
        self._never_starts: dict[tuple[str, int], int] = {}
        self._late_start: dict[tuple[str, int], int] = {}
        self._roam_escape: dict[tuple[str, int], float] = {}
        self._roam_stand_still: set[str] = set()
        self._roam_no_stops: set[str] = set()

        # F3-offline-2 §6: cuenta de creaciones, gestos del cable y fallos de la etapa.
        self.spawn_count = 0
        self._armed: dict[str, list] = {}
        self._scheduled: dict[str, list[list]] = {}
        self.apply_reject: dict[str, str] = {}
        self.apply_error: dict[str, str] = {}
        self.despawn_fail: set[str] = set()

    def _require_actor(self, lid: str) -> _ActorState:
        actor = self._actors.get(lid)
        if actor is None:
            raise ValueError(f"actor desconocido: {lid!r}")
        return actor

    def spawn(
        self,
        lid: str,
        cls: str,
        x: float | int,
        z: float | int,
        yaw: float | int,
        wardrobe: str | None = None,
        *,
        items: list[str] | None = None,
    ) -> None:
        if items is None:
            wardrobe_items = self.catalog.get("wardrobe_items")
            if not isinstance(wardrobe_items, dict) or not isinstance(wardrobe, str) or wardrobe not in wardrobe_items:
                raise ValueError(f"wardrobe desconocido: {wardrobe!r}")
            items = wardrobe_items[wardrobe]
        self._actors[lid] = _ActorState(lid, cls, float(x), float(z), float(yaw), list(items))
        self.spawn_count += 1
        for fault in self._armed.pop(lid, []):
            fault()

    def _arm_or_run(self, lid: str, fault) -> None:
        """F3-offline-2 §6: con el actor vivo, el fallo se aplica ya; si no, al crearlo."""
        if lid in self._actors:
            fault()
        else:
            self._armed.setdefault(lid, []).append(fault)

    def despawn(self, lid: str) -> None:
        """Retira el actor y sus gestos (la foto sigue pasando `valid_actor_read`)."""
        if self._actors.pop(lid, None) is None:
            return
        self._gestures = [ev for ev in self._gestures if ev[0] != lid]
        self._gesture_tasks = [t for t in self._gesture_tasks if t.lid != lid]
        self._scheduled.pop(lid, None)

    def schedule_gestures(self, lid: str, emotes: list, at: list, t_ms: list) -> None:
        """Gestos del cable: por tiempo desde ahora (`t_ms >= 0`) o al llegar a la marca `at`."""
        self._require_actor(lid)
        t0 = self.clock.now_ms()
        self._scheduled[lid] = [
            [gi, emote, int(a), int(t), t0, False]
            for gi, (emote, a, t) in enumerate(zip(emotes, at, t_ms))
        ]

    def _step_scheduled(self, now_ms: int) -> None:
        for lid, items in self._scheduled.items():
            actor = self._actors.get(lid)
            if actor is None:
                continue
            for item in items:
                gi, emote, at, t, t0, done = item
                if done:
                    continue
                due = (t >= 0 and now_ms - t0 >= t) or (
                    at >= 0 and actor.mark_i == at and actor.mark_st == "arrived"
                )
                if due:
                    item[5] = True
                    self.request_gesture(lid, gi, emote)

    def _compute_roam_dest(self, actor: _ActorState, k: int) -> tuple[float, float]:
        seed_bytes = hashlib.sha256(f"{actor.lid}:{k}".encode("utf-8")).digest()
        u_r = int.from_bytes(seed_bytes[:4], "big") / 0xFFFFFFFF
        u_a = int.from_bytes(seed_bytes[4:8], "big") / 0xFFFFFFFF
        base_bytes = hashlib.sha256(actor.lid.encode("utf-8")).digest()
        base_angle = (int.from_bytes(base_bytes[:4], "big") / 0xFFFFFFFF) * 2.0 * math.pi

        if (actor.lid, k) in self._roam_escape:
            dist = float(self._roam_escape[(actor.lid, k)])
        else:
            dist = (0.35 + 0.40 * u_r) * actor.roam

        # Angulo aureo + perturbacion determinista para recorrer bien el anillo.
        angle = base_angle + k * 2.399963229728653 + (u_a - 0.5) * 0.5
        return (
            actor.spawn_x + dist * math.cos(angle),
            actor.spawn_z + dist * math.sin(angle),
        )

    def set_marks(
        self,
        lid: str,
        marks: list[dict],
        behaviour: str,
        roam: float | int = 15.0,
    ) -> None:
        actor = self._require_actor(lid)
        if behaviour not in ("ONCE", "LOOP", "HOLD", "ROAM"):
            raise ValueError(f"behaviour desconocido: {behaviour!r}")
        actor.marks = [{"x": float(m["x"]), "z": float(m["z"])} for m in (marks or [])]
        actor.behaviour = behaviour
        actor.roam = float(roam)
        actor.fault_stopped = False
        actor.roam_wait_ms = 0
        actor.roam_k = 0
        actor.roam_target = None

        if behaviour == "HOLD":
            actor.mark_i = -1
            actor.mark_st = "idle"
        elif behaviour in ("ONCE", "LOOP"):
            if actor.marks:
                actor.mark_i = 0
                actor.mark_st = "moving"
            else:
                actor.mark_i = -1
                actor.mark_st = "idle"
        else:  # ROAM
            actor.mark_i = -1
            if lid in self._roam_stand_still or actor.roam <= 0.0:
                actor.mark_st = "idle"
                actor.roam_target = None
            else:
                actor.roam_target = self._compute_roam_dest(actor, 0)
                actor.mark_st = "moving"

    def request_gesture(
        self,
        lid: str,
        gi: int,
        emote: str,
        duration_ms: int = _DEFAULT_GESTURE_MS,
    ) -> None:
        self._require_actor(lid)
        now = self.clock.now_ms()
        self._gestures.append([lid, int(gi), "requested", now, None])
        self._gesture_tasks.append(_GestureTask(lid, int(gi), emote, int(duration_ms), now))

    # --- Fallos inyectables (§5) ---------------------------------------------

    def unreachable(self, lid: str, mark_i: int) -> None:
        self._mark_faults[(lid, int(mark_i))] = (3.0, "unreachable")

    def unreachable_near(self, lid: str, mark_i: int) -> None:
        self._mark_faults[(lid, int(mark_i))] = (1.0, "unreachable")

    def stop_short(self, lid: str, mark_i: int) -> None:
        self._mark_faults[(lid, int(mark_i))] = (1.6, "arrived")

    def jitter(self, lid: str, amp_m: float | int) -> None:
        self._jitter_amp[lid] = float(amp_m)

    def wardrobe_drop(self, lid: str, cls: str | None = None) -> None:
        def fault() -> None:
            actor = self._actors[lid]
            if cls is None:
                if actor.items:
                    actor.items.pop()
            elif cls in actor.items:
                actor.items.remove(cls)
        self._arm_or_run(lid, fault)

    def wardrobe_add(self, lid: str, cls: str) -> None:
        self._arm_or_run(lid, lambda: self._actors[lid].items.append(cls))

    def cls_swap(self, lid: str, cls: str) -> None:
        self._arm_or_run(lid, lambda: setattr(self._actors[lid], "cls", cls))

    def displace_spawn(self, lid: str, dx_m: float | int, dz_m: float | int) -> None:
        """F3-offline-2 §6: el actor aparece desplazado (dx_m, dz_m)."""
        def fault() -> None:
            actor = self._actors[lid]
            for attr, d in (("x", dx_m), ("base_x", dx_m), ("spawn_x", dx_m),
                            ("z", dz_m), ("base_z", dz_m), ("spawn_z", dz_m)):
                setattr(actor, attr, getattr(actor, attr) + float(d))
        self._arm_or_run(lid, fault)

    def reject_apply(self, lid: str, reason: str) -> None:
        self.apply_reject[lid] = reason

    def error_apply(self, lid: str, reason: str) -> None:
        self.apply_error[lid] = reason

    def despawn_fails(self, lid: str) -> None:
        self.despawn_fail.add(lid)

    def combat(self, lid: str) -> None:
        self._combat.add(lid)

    def cancel_after_start(self, lid: str, gi: int) -> None:
        self._cancel_after_start.add((lid, int(gi)))

    def finish_without_start(self, lid: str, gi: int) -> None:
        self._finish_without_start.add((lid, int(gi)))

    def never_starts(self, lid: str, gi: int, expire_ms: int = 3000) -> None:
        self._never_starts[(lid, int(gi))] = int(expire_ms)

    def late_start(self, lid: str, gi: int, expire_ms: int = 3000) -> None:
        self._late_start[(lid, int(gi))] = int(expire_ms)

    def roam_escape(self, lid: str, k: int, dist_m: float | int) -> None:
        self._roam_escape[(lid, int(k))] = float(dist_m)
        actor = self._actors.get(lid)
        if (
            actor is not None
            and actor.behaviour == "ROAM"
            and lid not in self._roam_stand_still
            and actor.roam_k == int(k)
            and actor.roam_wait_ms == 0
        ):
            actor.roam_target = self._compute_roam_dest(actor, actor.roam_k)

    def roam_stand_still(self, lid: str) -> None:
        self._roam_stand_still.add(lid)
        actor = self._actors.get(lid)
        if actor is not None and actor.behaviour == "ROAM":
            actor.roam_target = None
            actor.roam_wait_ms = 0
            actor.mark_i = -1
            actor.mark_st = "idle"

    def roam_no_stops(self, lid: str) -> None:
        self._roam_no_stops.add(lid)
        actor = self._actors.get(lid)
        if actor is not None and actor.behaviour == "ROAM":
            actor.roam_wait_ms = 0

    # --- Simulacion por paso -------------------------------------------------

    def _step_actor(self, actor: _ActorState, dt_ms: int) -> None:
        step_dist = _SPEED_MPS * (dt_ms / 1000.0)
        moved = False

        if actor.behaviour in ("ONCE", "LOOP") and actor.marks and actor.mark_i >= 0:
            if not actor.fault_stopped:
                if actor.mark_st == "arrived":
                    if actor.behaviour == "LOOP":
                        actor.mark_i = (actor.mark_i + 1) % len(actor.marks)
                        actor.mark_st = "moving"
                    elif actor.mark_i + 1 < len(actor.marks):
                        actor.mark_i += 1
                        actor.mark_st = "moving"

                if actor.mark_st == "moving":
                    moved = True
                    target = actor.marks[actor.mark_i]
                    tx, tz = target["x"], target["z"]
                    dx = tx - actor.x
                    dz = tz - actor.z
                    dist = math.hypot(dx, dz)
                    fault = self._mark_faults.get((actor.lid, actor.mark_i))

                    if fault is not None:
                        stop_dist, fault_st = fault
                        if dist <= stop_dist + step_dist:
                            if dist > 1e-9:
                                actor.x = tx - (dx / dist) * stop_dist
                                actor.z = tz - (dz / dist) * stop_dist
                            else:
                                actor.x = tx - stop_dist
                                actor.z = tz
                            actor.base_x = actor.x
                            actor.base_z = actor.z
                            actor.mark_st = fault_st
                            actor.fault_stopped = True
                        else:
                            actor.x += (dx / dist) * step_dist
                            actor.z += (dz / dist) * step_dist
                            actor.base_x = actor.x
                            actor.base_z = actor.z
                    else:
                        move_d = min(dist, step_dist)
                        if dist > 1e-9:
                            actor.x += (dx / dist) * move_d
                            actor.z += (dz / dist) * move_d
                        actor.base_x = actor.x
                        actor.base_z = actor.z
                        if dist - move_d < _ARRIVE_DIST_M:
                            actor.mark_st = "arrived"

        elif actor.behaviour == "ROAM":
            actor.mark_i = -1
            if actor.lid in self._roam_stand_still or actor.roam_target is None:
                actor.mark_st = "idle"
            elif actor.roam_wait_ms > 0 and actor.lid not in self._roam_no_stops:
                actor.roam_wait_ms = max(0, actor.roam_wait_ms - dt_ms)
                actor.mark_st = "idle"
                if actor.roam_wait_ms == 0:
                    actor.roam_k += 1
                    actor.roam_target = self._compute_roam_dest(actor, actor.roam_k)
            elif actor.lid in self._roam_no_stops:
                moved = True
                tx, tz = actor.roam_target
                dx = tx - actor.x
                dz = tz - actor.z
                dist = math.hypot(dx, dz)
                move_d = min(dist, step_dist)
                if dist > 1e-9:
                    actor.x += (dx / dist) * move_d
                    actor.z += (dz / dist) * move_d
                actor.base_x = actor.x
                actor.base_z = actor.z
                if dist - move_d < _ARRIVE_DIST_M:
                    actor.mark_st = "idle"
                    actor.roam_k += 1
                    actor.roam_target = self._compute_roam_dest(actor, actor.roam_k)
                else:
                    actor.mark_st = "moving"
            else:
                moved = True
                actor.mark_st = "moving"
                tx, tz = actor.roam_target
                dx = tx - actor.x
                dz = tz - actor.z
                dist = math.hypot(dx, dz)
                if dist <= step_dist or dist - step_dist < _ARRIVE_DIST_M:
                    actor.x = tx
                    actor.z = tz
                    actor.base_x = actor.x
                    actor.base_z = actor.z
                    actor.mark_st = "idle"
                    actor.roam_wait_ms = _ROAM_STOP_MS
                else:
                    actor.x += (dx / dist) * step_dist
                    actor.z += (dz / dist) * step_dist
                    actor.base_x = actor.x
                    actor.base_z = actor.z

        if not moved and actor.lid in self._jitter_amp:
            amp = self._jitter_amp[actor.lid]
            actor.jitter_sign = 1 if actor.jitter_sign < 0 else -1
            actor.x = actor.base_x + actor.jitter_sign * amp

    def _step_gestures(self, now_ms: int) -> None:
        for task in self._gesture_tasks:
            if task.state == "done":
                continue
            actor = self._actors.get(task.lid)
            if actor is None:
                continue
            key = (task.lid, task.gi)

            if task.state == "requested":
                if task.lid in self._combat:
                    self._gestures.append([task.lid, task.gi, "rejected", now_ms, "combat"])
                    task.state = "done"
                elif key in self._never_starts:
                    if now_ms - task.t_req >= self._never_starts[key]:
                        self._gestures.append([task.lid, task.gi, "expired", now_ms, "timeout"])
                        task.state = "done"
                elif key in self._late_start:
                    if now_ms - task.t_req >= self._late_start[key]:
                        self._gestures.append([task.lid, task.gi, "expired", now_ms, "timeout"])
                        task.state = "expired_waiting_late"
                elif key in self._finish_without_start:
                    if actor.mark_st != "moving":
                        self._gestures.append([task.lid, task.gi, "finished", now_ms, None])
                        task.state = "done"
                else:
                    if actor.mark_st != "moving":
                        self._gestures.append([task.lid, task.gi, "playing", now_ms, None])
                        task.t_play = now_ms
                        task.state = "playing"

            elif task.state == "expired_waiting_late":
                if actor.mark_st != "moving":
                    self._gestures.append([task.lid, task.gi, "playing", now_ms, None])
                    task.t_play = now_ms
                    task.state = "playing_late"

            elif task.state == "playing":
                if key in self._cancel_after_start:
                    self._gestures.append([task.lid, task.gi, "canceled", now_ms, "interrupted"])
                    task.state = "done"
                elif task.t_play is not None and now_ms - task.t_play >= task.duration_ms:
                    self._gestures.append([task.lid, task.gi, "finished", now_ms, None])
                    task.state = "done"

            elif task.state == "playing_late":
                if task.t_play is not None and now_ms - task.t_play >= task.duration_ms:
                    self._gestures.append([task.lid, task.gi, "finished", now_ms, None])
                    task.state = "done"

    def step(self, dt_ms: int) -> None:
        now_ms = self.clock.advance(dt_ms)
        for actor in self._actors.values():
            self._step_actor(actor, dt_ms)
        self._step_scheduled(now_ms)
        self._step_gestures(now_ms)

    def read(self) -> dict:
        now_ms = self.clock.now_ms()
        actors_rows = []
        for actor in self._actors.values():
            actors_rows.append([
                actor.lid,
                actor.cls,
                _m_to_mm(actor.x),
                _m_to_mm(actor.y),
                _m_to_mm(actor.z),
                _yaw_to_mdeg(actor.yaw),
                list(actor.items),
                actor.mark_i,
                actor.mark_st,
                now_ms,
            ])
        return {
            "actors": actors_rows,
            "gestures": [list(ev) for ev in self._gestures],
        }


def collect(
    engine: FakeActorEngine,
    until_ms: int,
    step_ms: int,
    drop: tuple[str, int, int] | None = None,
) -> tuple[dict[str, list[list]], list[list]]:
    """Avanza el motor hasta `until_ms` con pasos `step_ms` y recoge muestras (§5)."""
    if not _is_int(step_ms) or step_ms <= 0:
        raise ValueError("step_ms debe ser un entero > 0")
    if not _is_int(until_ms) or until_ms < 0:
        raise ValueError("until_ms debe ser un entero >= 0")

    samples: dict[str, list[list]] = {}
    last_gestures: list[list] = []

    def _record_snapshot(snap: dict) -> None:
        nonlocal last_gestures
        last_gestures = snap["gestures"]
        for row in snap["actors"]:
            lid = row[0]
            t_ms = row[9]
            if lid not in samples:
                samples[lid] = []
            if drop is not None:
                drop_lid, t_from, t_to = drop
                if lid == drop_lid and t_from <= t_ms <= t_to:
                    continue
            if samples[lid] and samples[lid][-1][9] == t_ms:
                continue
            samples[lid].append(row)

    if engine.clock.now_ms() <= until_ms:
        _record_snapshot(engine.read())

    while engine.clock.now_ms() < until_ms:
        dt = min(step_ms, until_ms - engine.clock.now_ms())
        engine.step(dt)
        _record_snapshot(engine.read())

    return samples, last_gestures
