"""Validadores de la lectura de un actor (F3-offline-1 §2).

Fila viva, fila de muerto, evento de gesto y foto `{"actors", "gestures"}`.
Unidades y enteros como F2: reutiliza los predicados de `scene_plan`.
"""
import re

from app.backend.scene_plan import (
    _MAX_WORLD_SIZE,
    _is_int,
    _valid_xz_mm,
    _valid_y_mm,
    _valid_yaw_mdeg,
)

_ACT_LID_RE = re.compile(r"^act-(0[1-9]|[1-9]\d+)$")
_CAUSE_RE = re.compile(r"^[a-z_]{1,24}$")
_MARK_ST = frozenset({"idle", "moving", "arrived", "unreachable"})
_GESTURE_ST = frozenset({
    "requested", "playing", "finished", "canceled", "rejected", "expired",
})
_CAUSE_REQUIRED = frozenset({"canceled", "rejected", "expired"})
_MAX_CLS_LEN = 64
_MAX_ITEMS = 32
_MAX_ACTORS = 16
_MAX_GESTURE_EVENTS = 512
_MARK_I_MAX = 63
_GI_MAX = 63


def _valid_act_lid(lid):
    return isinstance(lid, str) and _ACT_LID_RE.fullmatch(lid) is not None


def _valid_cls(val):
    """Nombre vanilla: ASCII imprimible, 1..64."""
    if not isinstance(val, str) or not (1 <= len(val) <= _MAX_CLS_LEN):
        return False
    return all(32 <= ord(ch) <= 126 for ch in val)


def _valid_items(items):
    if not isinstance(items, list) or len(items) > _MAX_ITEMS:
        return False
    return all(_valid_cls(it) for it in items)


def valid_actor_row(row, world_size=_MAX_WORLD_SIZE):
    """Fila §2.1: `[lid, cls, x_mm, y_mm, z_mm, yaw_mdeg, items, mark_i, mark_st, t_ms]`."""
    if not isinstance(row, list) or len(row) != 10:
        return False
    lid, cls, x, y, z, yaw, items, mark_i, mark_st, t_ms = row
    if not _valid_act_lid(lid):
        return False
    if not _is_int(t_ms) or t_ms < 0:
        return False
    if not _is_int(mark_i) or mark_i < -1 or mark_i > _MARK_I_MAX:
        return False
    if mark_st not in _MARK_ST:
        return False

    dead = (
        cls is None
        and x is None
        and y is None
        and z is None
        and yaw is None
        and items == []
        and mark_i == -1
        and mark_st == "idle"
    )
    if dead:
        return True
    if cls is None or x is None or y is None or z is None or yaw is None:
        return False
    if mark_i == -1 and mark_st not in ("idle", "moving"):
        return False
    return (
        _valid_cls(cls)
        and _valid_xz_mm(x, world_size)
        and _valid_y_mm(y)
        and _valid_xz_mm(z, world_size)
        and _valid_yaw_mdeg(yaw)
        and _valid_items(items)
    )


def valid_gesture_event(ev):
    """Evento §2.2: `[lid, gi, st, t_ms, cause]`."""
    if not isinstance(ev, list) or len(ev) != 5:
        return False
    lid, gi, st, t_ms, cause = ev
    if not _valid_act_lid(lid):
        return False
    if not _is_int(gi) or gi < 0 or gi > _GI_MAX:
        return False
    if st not in _GESTURE_ST:
        return False
    if not _is_int(t_ms) or t_ms < 0:
        return False
    if st in _CAUSE_REQUIRED:
        return isinstance(cause, str) and _CAUSE_RE.fullmatch(cause) is not None
    return cause is None


def valid_actor_read(read, world_size=_MAX_WORLD_SIZE):
    """Foto §2.3: exactamente `actors` y `gestures`; lids únicos; t_ms no decreciente por (lid, gi)."""
    if not isinstance(read, dict) or set(read) != {"actors", "gestures"}:
        return False
    actors = read["actors"]
    gestures = read["gestures"]
    if not isinstance(actors, list) or not isinstance(gestures, list):
        return False
    if len(actors) > _MAX_ACTORS or len(gestures) > _MAX_GESTURE_EVENTS:
        return False
    lids = []
    for row in actors:
        if not valid_actor_row(row, world_size=world_size):
            return False
        lids.append(row[0])
    if len(lids) != len(set(lids)):
        return False
    lid_set = set(lids)
    last_t = {}
    for ev in gestures:
        if not valid_gesture_event(ev):
            return False
        lid, gi, _st, t_ms, _cause = ev
        if lid not in lid_set:
            return False
        key = (lid, gi)
        prev = last_t.get(key)
        if prev is not None and t_ms < prev:
            return False
        last_t[key] = t_ms
    return True
