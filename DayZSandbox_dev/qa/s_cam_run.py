"""Runner del spike S-cam (brief S-cam §4, F0.3-0 §5.1-§5.3).

Exporta ``SPIKE_ID``, ``find_dayz_window``, ``capture_window``, ``write_bmp24``
y ``run(args, evidence, argv) -> int``.
"""

import ctypes
import ctypes.wintypes as wintypes
import json
import math
import struct
import time
from pathlib import Path

import f03_common
import gate_core
import s_cam_eval
import s_cam_mutants
import wire

SPIKE_ID = "S-cam"

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_OFFLINE_W = 1280
_OFFLINE_H = 720
_OFFLINE_CACHE = None

# Codigos de scan DirectInput (en orden de KeyCode usado por S-cam).
_DIK_SCANCODES = {
    "KC_Q": 0x10,
    "KC_W": 0x11,
    "KC_E": 0x12,
    "KC_A": 0x1E,
    "KC_S": 0x1F,
    "KC_D": 0x20,
    "KC_F": 0x21,
    "KC_UP": 0x48,
    "KC_PRIOR": 0x49,
    "KC_LEFT": 0x4B,
    "KC_RIGHT": 0x4D,
    "KC_DOWN": 0x50,
    "KC_NEXT": 0x51,
}
_EXTENDED_KEYS = frozenset({"KC_UP", "KC_DOWN", "KC_LEFT", "KC_RIGHT", "KC_PRIOR", "KC_NEXT"})

_MUTANT_FAULTS = {
    name: spec["qa_fault"].rstrip("_")
    for name, spec in s_cam_mutants.EXPECTED_MUTANTS.items()
}


def _load_fixtures():
    paths = gate_core.read_json(_FIXTURES_DIR / "s_cam_paths.json")
    rois = gate_core.read_json(_FIXTURES_DIR / "s_cam_rois.json")
    return paths, rois


def write_bmp24(path, width: int, height: int, bgr_bytes: bytes) -> Path:
    """Escribe un BMP 24-bit BGR sin comprimir (BI_RGB, bottom-up)."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    w = int(width)
    h = int(height)
    row_raw = w * 3
    pad = (4 - (row_raw % 4)) % 4
    stride = row_raw + pad
    img_size = stride * h
    file_size = 54 + img_size
    if len(bgr_bytes) != row_raw * h:
        raise ValueError(f"bgr_bytes length {len(bgr_bytes)} != {row_raw * h}")

    header = struct.pack(
        "<2sIHHI",
        b"BM",
        file_size,
        0,
        0,
        54,
    ) + struct.pack(
        "<IiiHHIIiiII",
        40,
        w,
        h,
        1,
        24,
        0,
        img_size,
        2835,
        2835,
        0,
        0,
    )
    pad_bytes = b"\x00" * pad
    chunks = [header]
    for y in range(h - 1, -1, -1):
        off = y * row_raw
        chunks.append(bgr_bytes[off : off + row_raw])
        if pad:
            chunks.append(pad_bytes)
    out_path.write_bytes(b"".join(chunks))
    return out_path


def find_dayz_window(title_substring: str = "DayZ"):
    """Localiza el HWND de la ventana visible del cliente DayZ en Windows."""
    if not hasattr(ctypes, "windll"):
        return None
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title_substring.lower() in title.lower() and "server" not in title.lower():
            rect = wintypes.RECT()
            if user32.GetClientRect(hwnd, ctypes.byref(rect)):
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w >= 640 and h >= 360:
                    found.append((w * h, int(hwnd)))
        return True

    user32.EnumWindows(_enum_cb, 0)
    if not found:
        return None
    found.sort(reverse=True)
    return found[0][1]


def capture_window(hwnd, out_path) -> tuple[int, int]:
    """Captura el area cliente de hwnd desde pantalla (BitBlt SRCCOPY) y guarda BMP 24-bit."""
    if not hasattr(ctypes, "windll") or not hwnd:
        raise RuntimeError("capture_window requires a valid Win32 HWND")
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise RuntimeError("GetClientRect failed")
    w = int(rect.right - rect.left)
    h = int(rect.bottom - rect.top)
    if w <= 0 or h <= 0:
        raise RuntimeError(f"invalid client rect {w}x{h}")

    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))

    src_dc = user32.GetDC(0)
    mem_dc = gdi32.CreateCompatibleDC(src_dc)
    hbmp = gdi32.CreateCompatibleBitmap(src_dc, w, h)
    old_bmp = gdi32.SelectObject(mem_dc, hbmp)
    try:
        gdi32.BitBlt(mem_dc, 0, 0, w, h, src_dc, pt.x, pt.y, 0x00CC0020)

        class _BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = _BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 24
        bmi.biCompression = 0
        stride = ((w * 3 + 3) // 4) * 4
        raw = ctypes.create_string_buffer(stride * h)
        lines = gdi32.GetDIBits(mem_dc, hbmp, 0, h, raw, ctypes.byref(bmi), 0)
        if lines != h:
            raise RuntimeError(f"GetDIBits returned {lines} != {h}")
        raw_bytes = raw.raw
        if stride == w * 3:
            bgr = raw_bytes
        else:
            bgr = b"".join(raw_bytes[y * stride : y * stride + w * 3] for y in range(h))
        write_bmp24(out_path, w, h, bgr)
        return (w, h)
    finally:
        gdi32.SelectObject(mem_dc, old_bmp)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, src_dc)


def _offline_planes():
    """Precalcula planos deterministas 1280x720 (nitido, desenfocado y quickbar) una sola vez."""
    global _OFFLINE_CACHE
    if _OFFLINE_CACHE is not None:
        return _OFFLINE_CACHE
    w = _OFFLINE_W
    h = _OFFLINE_H
    tile_w = 16
    tile_h = 16
    sharp_rows = []
    blur_rows = []
    mid_rows = []
    for ty in range(tile_h):
        s_row = bytearray()
        b_row = bytearray()
        m_row = bytearray()
        for tx in range(tile_w):
            pat = ((tx * 37 + ty * 73 + (tx ^ ty) * 19) % 160) + 45
            if (tx + ty) % 2 == 0:
                val = min(230, pat + 25)
            else:
                val = max(25, pat - 25)
            bval = 128 + ((tx + ty) % 3) - 1
            mval = int(0.55 * bval + 0.45 * val)
            s_row.extend((val, val, val))
            b_row.extend((bval, bval, bval))
            m_row.extend((mval, mval, mval))
        rep = w // tile_w
        sharp_rows.append(bytes(s_row) * rep)
        blur_rows.append(bytes(b_row) * rep)
        mid_rows.append(bytes(m_row) * rep)

    base_sharp = bytearray(w * h * 3)
    base_blur = bytearray(w * h * 3)
    base_mid = bytearray(w * h * 3)
    row_bytes = w * 3
    for y in range(h):
        off = y * row_bytes
        base_sharp[off : off + row_bytes] = sharp_rows[y % tile_h]
        base_blur[off : off + row_bytes] = blur_rows[y % tile_h]
        base_mid[off : off + row_bytes] = mid_rows[y % tile_h]

    _OFFLINE_CACHE = (bytes(base_sharp), bytes(base_blur), bytes(base_mid))
    return _OFFLINE_CACHE


def _roi_px(roi):
    x0 = max(0, min(_OFFLINE_W, int(round(roi[0] * _OFFLINE_W))))
    y0 = max(0, min(_OFFLINE_H, int(round(roi[1] * _OFFLINE_H))))
    x1 = max(x0, min(_OFFLINE_W, int(round(roi[2] * _OFFLINE_W))))
    y1 = max(y0, min(_OFFLINE_H, int(round(roi[3] * _OFFLINE_H))))
    return x0, y0, x1, y1


def _render_offline_bmp(out_path, state_nk: dict, rois: dict) -> tuple[int, int]:
    """Render sintetico determinista dirigido estrictamente por el estado leido del peer."""
    base_sharp, base_blur, base_mid = _offline_planes()
    buf = bytearray(base_sharp)
    row_bytes = _OFFLINE_W * 3

    fdist = float(state_nk.get("sent_focus_dist_m", 0.0))
    fblur = max(0.0, min(1.0, float(state_nk.get("sent_focus_blur", 0.0))))
    qb_vis = float(state_nk.get("qb_vis_b", 0.0)) >= 0.5
    ovl_vis = float(state_nk.get("ovl_vis_b", 0.0)) >= 0.5

    if fblur > 0.05:
        bg_coc = fblur * max(0.0, min(1.0, abs(fdist - 50.0) / 48.0))
        subj_coc = fblur * max(0.0, min(1.0, abs(fdist - 2.0) / 48.0))
        if bg_coc >= 0.55:
            src = base_blur
        elif bg_coc >= 0.25:
            src = base_mid
        else:
            src = None
        if src is not None:
            x0, y0, x1, y1 = _roi_px(rois["roi_bg_50m"])
            b0, b1 = x0 * 3, x1 * 3
            for y in range(y0, y1):
                off = y * row_bytes
                buf[off + b0 : off + b1] = src[off + b0 : off + b1]
        if subj_coc >= 0.55:
            src = base_blur
        elif subj_coc >= 0.25:
            src = base_mid
        else:
            src = None
        if src is not None:
            x0, y0, x1, y1 = _roi_px(rois["roi_subject_2m"])
            b0, b1 = x0 * 3, x1 * 3
            for y in range(y0, y1):
                off = y * row_bytes
                buf[off + b0 : off + b1] = src[off + b0 : off + b1]

    if qb_vis:
        x0, y0, x1, y1 = _roi_px(rois["roi_quickbar"])
        bar_line = bytes((210, 210, 210)) * (x1 - x0)
        b0, b1 = x0 * 3, x1 * 3
        for y in range(y0, y1):
            off = y * row_bytes
            buf[off + b0 : off + b1] = bar_line

    if ovl_vis:
        red_line = bytes((0, 0, 220)) * 24
        for y in range(32, 56):
            off = y * row_bytes + 32 * 3
            buf[off : off + 72] = red_line

    write_bmp24(out_path, _OFFLINE_W, _OFFLINE_H, bytes(buf))
    return (_OFFLINE_W, _OFFLINE_H)


class _InputDriver:
    """Emisor unificado de teclado/raton: scam_os_input.jsonl en offline, SendInput en retail/diag."""

    def __init__(self, ctx: f03_common.PartContext):
        self.ctx = ctx
        self.build = ctx.build
        self.seq_n = 0
        self.file_path = None
        if self.build == "offline":
            prof = ctx.profiles.get("client")
            if prof is not None:
                self.file_path = Path(prof) / "scam_os_input.jsonl"
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                self.file_path.write_bytes(b"")

    def _next_seq(self) -> int:
        self.seq_n += 1
        return self.seq_n

    def _append_offline(self, event: dict) -> None:
        if self.file_path is None:
            return
        line = (json.dumps(event, sort_keys=True) + "\n").encode("utf-8")
        with self.file_path.open("ab") as fh:
            fh.write(line)
            fh.flush()

    def _send_win32_key(self, key_name: str, key_up: bool) -> None:
        if not hasattr(ctypes, "windll"):
            return
        sc = _DIK_SCANCODES.get(key_name)
        if sc is None:
            return
        flags = 0x0008  # KEYEVENTF_SCANCODE
        if key_name in _EXTENDED_KEYS:
            flags |= 0x0001  # KEYEVENTF_EXTENDEDKEY
        if key_up:
            flags |= 0x0002  # KEYEVENTF_KEYUP

        class _KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class _MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

        class _INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

        inp = _INPUT()
        inp.type = 1  # INPUT_KEYBOARD
        inp.union.ki.wVk = 0
        inp.union.ki.wScan = sc
        inp.union.ki.dwFlags = flags
        inp.union.ki.time = 0
        inp.union.ki.dwExtraInfo = 0
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def _send_win32_mouse_move(self, dx_px: float) -> None:
        if not hasattr(ctypes, "windll"):
            return

        class _MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wintypes.LONG),
                ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class _KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t),
            ]

        class _INPUTUNION(ctypes.Union):
            _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]

        class _INPUT(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

        inp = _INPUT()
        inp.type = 0  # INPUT_MOUSE
        inp.union.mi.dx = int(round(dx_px))
        inp.union.mi.dy = 0
        inp.union.mi.mouseData = 0
        inp.union.mi.dwFlags = 0x0001  # MOUSEEVENTF_MOVE
        inp.union.mi.time = 0
        inp.union.mi.dwExtraInfo = 0
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def key_tap(self, keys: list[str]) -> tuple[int, float]:
        seq = self._next_seq()
        issued = self.ctx.now_h_ms()
        if self.build == "offline":
            self._append_offline(
                {
                    "duration_ms": 0.0,
                    "dx_px": 0.0,
                    "issued_h_ms": issued,
                    "keys": list(keys),
                    "kind": "key_tap",
                    "seq_n": seq,
                }
            )
        else:
            for k in keys:
                self._send_win32_key(k, False)
            time.sleep(0.04)
            for k in reversed(keys):
                self._send_win32_key(k, True)
        return seq, issued

    def key_hold(self, keys: list[str], duration_ms: float) -> tuple[int, float]:
        seq = self._next_seq()
        issued = self.ctx.now_h_ms()
        if self.build == "offline":
            self._append_offline(
                {
                    "duration_ms": float(duration_ms),
                    "dx_px": 0.0,
                    "issued_h_ms": issued,
                    "keys": list(keys),
                    "kind": "key_hold",
                    "seq_n": seq,
                }
            )
        else:
            for k in keys:
                self._send_win32_key(k, False)
            time.sleep(max(0.0, float(duration_ms) / 1000.0))
            for k in reversed(keys):
                self._send_win32_key(k, True)
        return seq, issued

    def mouse_move(self, dx_px: float) -> tuple[int, float]:
        seq = self._next_seq()
        issued = self.ctx.now_h_ms()
        if self.build == "offline":
            self._append_offline(
                {
                    "duration_ms": 0.0,
                    "dx_px": float(dx_px),
                    "issued_h_ms": issued,
                    "keys": [],
                    "kind": "mouse_move",
                    "seq_n": seq,
                }
            )
        else:
            self._send_win32_mouse_move(dx_px)
        return seq, issued


def _client_inst(ctx: f03_common.PartContext) -> str:
    return str(ctx.bridge.registered("client") or "")


def _issue_op(
    ctx: f03_common.PartContext,
    phase: str,
    step: str,
    verb: str,
    payload: dict | None = None,
    qa_fault: str = "",
    record: bool = True,
):
    out = f03_common.issue_one(
        ctx,
        "client",
        verb,
        payload if payload is not None else wire.empty_payload(),
        qa_fault=qa_fault,
    )
    if record:
        ctx.record_scenario(
            {
                "done_ms": out.done_ms,
                "ev": "op",
                "frame_done": out.frame_done,
                "frame_recv": out.frame_recv,
                "h_ms": ctx.now_h_ms(),
                "op_id": out.op_id,
                "peer_inst": _client_inst(ctx),
                "phase": phase,
                "read_nk": dict(out.payload["num"]),
                "read_sk": dict(out.payload["str"]),
                "reason": out.reason,
                "recv_ms": out.recv_ms,
                "role": "client",
                "status": out.status,
                "step": step,
                "verb": verb,
            }
        )
    return out


def _read_state(ctx: f03_common.PartContext, phase: str, step: str, record: bool = True):
    out = f03_common.issue_one(ctx, "client", "scam_state_read", wire.empty_payload())
    if record:
        ctx.record_scenario(
            {
                "ev": "state",
                "frame_done": out.frame_done,
                "frame_recv": out.frame_recv,
                "h_ms": ctx.now_h_ms(),
                "op_id": out.op_id,
                "peer_inst": _client_inst(ctx),
                "phase": phase,
                "read_nk": dict(out.payload["num"]),
                "read_sk": dict(out.payload["str"]),
                "step": step,
            }
        )
    return out


def _record_state_outcome(ctx: f03_common.PartContext, phase: str, step: str, out) -> None:
    ctx.record_scenario(
        {
            "ev": "state",
            "frame_done": out.frame_done,
            "frame_recv": out.frame_recv,
            "h_ms": ctx.now_h_ms(),
            "op_id": out.op_id,
            "peer_inst": _client_inst(ctx),
            "phase": phase,
            "read_nk": dict(out.payload["num"]),
            "read_sk": dict(out.payload["str"]),
            "step": step,
        }
    )


def _find_bridge_op_times(ctx: f03_common.PartContext, op_id: str) -> tuple[float | None, float | None]:
    enq_t = None
    res_t = None
    with ctx.bridge.cv:
        events = list(ctx.bridge.events)
    for ev in events:
        if ev.get("op_id") != op_id:
            continue
        if ev.get("ev") == "enq" and enq_t is None:
            enq_t = float(ev["t_ms"])
        elif ev.get("ev") == "result" and res_t is None:
            res_t = float(ev["t_ms"])
    return enq_t, res_t


def _bridge_event_count(ctx: f03_common.PartContext) -> int:
    with ctx.bridge.cv:
        return len(ctx.bridge.events)


def _path_keys_payload(
    keys: list[dict],
    anchor_y: float,
    pos_mode: str,
    interp_mode: str,
    hide_hud: str,
) -> dict:
    row_dicts = []
    for k in keys:
        row_dicts.append(
            {
                "t_s": float(k["t_s"]),
                "x_m": float(k["pos_x_m"]),
                "y_m": float(anchor_y) + float(k["pos_y_rel_m"]),
                "z_m": float(k["pos_z_m"]),
                "yaw_deg": float(k["yaw_deg"]),
                "pitch_deg": float(k["pitch_deg"]),
                "roll_deg": float(k["roll_deg"]),
                "fov_rad": float(k["fov_rad"]),
                "focus_dist_m": float(k["focus_dist_m"]),
                "focus_blur": float(k["focus_blur"]),
            }
        )
    return wire.pack_payload(
        scalars_str={
            "hide_hud": hide_hud,
            "interp_mode": interp_mode,
            "pos_mode": pos_mode,
        },
        num_cols=[
            "t_s",
            "x_m",
            "y_m",
            "z_m",
            "yaw_deg",
            "pitch_deg",
            "roll_deg",
            "fov_rad",
            "focus_dist_m",
            "focus_blur",
        ],
        str_cols=[],
        row_dicts=row_dicts,
    )


def _wait_job_terminal(ctx: f03_common.PartContext, job_id: str, timeout_s: float = 20.0) -> str:
    deadline = time.monotonic() + timeout_s
    last_state = ""
    while time.monotonic() < deadline:
        out = f03_common.issue_one(
            ctx,
            "client",
            "job_read",
            wire.pack_payload(scalars_str={"job": job_id}, scalars_num={"page_n": 0}),
        )
        last_state = str(out.payload["str"].get("state", ""))
        if last_state in ("done", "stopped", "failed", "expired"):
            return last_state
        time.sleep(0.08)
    return last_state


def _dump_job_jsonl(ctx: f03_common.PartContext, job_id: str, cols: tuple[str, ...], out_name: str) -> list[dict]:
    pages = f03_common.read_job_pages(ctx, "client", job_id)
    rows = pages.get("rows", [])
    out_path = ctx.part_dir / "samples" / out_name
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for rdict in rows:
        lines.append(json.dumps([float(rdict[c]) for c in cols]) + "\n")
    out_path.write_bytes("".join(lines).encode("utf-8"))
    f03_common.issue_one(
        ctx,
        "client",
        "job_free",
        wire.pack_payload(scalars_str={"job": job_id}),
    )
    return rows


def _capture_scene(
    ctx: f03_common.PartContext,
    phase: str,
    step: str,
    filename: str,
    state_nk: dict,
    rois: dict,
    pre_step: str,
    post_step: str | None = None,
    capture_frame: int | None = None,
    capture_tick_ms: float | None = None,
    record: bool = True,
) -> tuple[int, int]:
    out_path = ctx.part_dir / "samples" / filename
    cap_h = ctx.now_h_ms()
    if ctx.build == "offline":
        w, h = _render_offline_bmp(out_path, state_nk, rois)
    else:
        hwnd = find_dayz_window()
        if not hwnd:
            raise RuntimeError("DayZ client window not found")
        w, h = capture_window(hwnd, out_path)
    if record:
        ev = {
            "capture_h_ms": cap_h,
            "capture_tick_ms": float(
                capture_tick_ms if capture_tick_ms is not None else state_nk.get("tick_ms", 0.0)
            ),
            "ev": "capture",
            "file": filename,
            "h_ms": cap_h,
            "phase": phase,
            "post_step": post_step if post_step is not None else pre_step,
            "pre_step": pre_step,
            "step": step,
            "window_h": h,
            "window_w": w,
        }
        if capture_frame is not None:
            ev["frame"] = int(capture_frame)
        ctx.record_scenario(ev)
    return w, h


def _run_scam_s0(ctx: f03_common.PartContext, paths_fx: dict, rois: dict) -> float:
    phase = "SCAM-S0"
    anchor = paths_fx["anchor_pose"]
    ents = paths_fx["fixture_entities"]
    fix_out = _issue_op(
        ctx,
        phase,
        "fixture",
        "scam_fixture_setup",
        wire.pack_payload(
            scalars_num={
                "anchor_eye_h_m": float(anchor["anchor_eye_h_m"]),
                "anchor_fov_rad": float(anchor["fov_rad"]),
                "anchor_pitch_deg": float(anchor["pitch_deg"]),
                "anchor_roll_deg": float(anchor["roll_deg"]),
                "anchor_x_m": float(anchor["anchor_x_m"]),
                "anchor_yaw_deg": float(anchor["yaw_deg"]),
                "anchor_z_m": float(anchor["anchor_z_m"]),
                "bg_dist_m": float(ents["background"]["dist_m"]),
                "subj_dist_m": float(ents["subject"]["dist_m"]),
            }
        ),
    )
    anchor_y = float(fix_out.payload["num"].get("anchor_y_m", 301.6))
    _read_state(ctx, phase, "s0_state")

    if ctx.build == "offline":
        ctx.record_scenario(
            {
                "accredited_b": True,
                "ev": "dof_config",
                "h_ms": ctx.now_h_ms(),
                "mad_bg_50m": 25.0,
                "mode": "offline",
                "phase": phase,
                "step": "dof_config",
                "window_h": _OFFLINE_H,
                "window_w": _OFFLINE_W,
            }
        )
    else:
        _issue_op(
            ctx,
            phase,
            "s0_hud_hide",
            "scam_hud_op",
            wire.pack_payload(scalars_num={"op_code": 1.0}),
            record=False,
        )
        _issue_op(
            ctx,
            phase,
            "s0_dof_0",
            "scam_dof_set",
            wire.pack_payload(
                scalars_num={"enable_b": 0.0, "focus_blur": 0.0, "focus_dist_m": 0.0}
            ),
            record=False,
        )
        time.sleep(0.15)
        tmp_a = ctx.part_dir / "samples" / "_s0_pre_noblur.bmp"
        tmp_b = ctx.part_dir / "samples" / "_s0_pre_near2m.bmp"
        hwnd = find_dayz_window()
        win_w = win_h = 0
        mad_bg = 0.0
        if hwnd:
            win_w, win_h = capture_window(hwnd, tmp_a)
            _issue_op(
                ctx,
                phase,
                "s0_dof_2",
                "scam_dof_set",
                wire.pack_payload(
                    scalars_num={"enable_b": 1.0, "focus_blur": 1.0, "focus_dist_m": 2.0}
                ),
                record=False,
            )
            time.sleep(0.15)
            capture_window(hwnd, tmp_b)
            ga = s_cam_eval.read_bmp_gray(tmp_a)
            gb = s_cam_eval.read_bmp_gray(tmp_b)
            mad_bg = float(s_cam_eval.mad(ga, gb, rois["roi_bg_50m"]))
        min_w = int(rois.get("min_window_w", 1280))
        min_h = int(rois.get("min_window_h", 720))
        accredited = win_w >= min_w and win_h >= min_h and mad_bg >= 0.5
        mode = "optical"
        if not accredited:
            op_res = f03_common.await_operator(
                ctx,
                step=phase,
                action="confirm_dof_and_windowed",
                instructions=(
                    "Confirmar Depth of Field activado en Opciones > Video y ventana "
                    ">=1280x720 en primer plano creando OPERATOR_DONE"
                ),
                predicate=None,
                timeout_s=120.0,
            )
            hwnd2 = find_dayz_window()
            if hwnd2:
                win_w, win_h = capture_window(hwnd2, tmp_a)
            accredited = bool(op_res.get("ok") and win_w >= min_w and win_h >= min_h)
            mode = "operator"
        for tmp_f in (tmp_a, tmp_b):
            if tmp_f.is_file():
                try:
                    tmp_f.unlink()
                except OSError:
                    pass
        ctx.record_scenario(
            {
                "accredited_b": accredited,
                "ev": "dof_config",
                "h_ms": ctx.now_h_ms(),
                "mad_bg_50m": mad_bg,
                "mode": mode,
                "phase": phase,
                "step": "dof_config",
                "window_h": win_h,
                "window_w": win_w,
            }
        )
        _issue_op(
            ctx,
            phase,
            "s0_dof_reset",
            "scam_dof_set",
            wire.pack_payload(
                scalars_num={"enable_b": 0.0, "focus_blur": 0.0, "focus_dist_m": 0.0}
            ),
            record=False,
        )
        _issue_op(
            ctx,
            phase,
            "s0_hud_restore",
            "scam_hud_op",
            wire.pack_payload(scalars_num={"op_code": 2.0}),
            record=False,
        )

    _issue_op(
        ctx,
        phase,
        "s0_close_cam",
        "scam_free_op",
        wire.pack_payload(scalars_num={"op_code": 3.0}),
        record=False,
    )
    return anchor_y


def _wait_free_input(
    ctx: f03_common.PartContext,
    target_seq: int,
    min_dt_s: float,
    min_speed: float | None = None,
    timeout_s: float = 3.0,
):
    deadline = time.monotonic() + timeout_s
    last_out = None
    while time.monotonic() < deadline:
        out = f03_common.issue_one(ctx, "client", "scam_state_read", wire.empty_payload())
        last_out = out
        nk = out.payload["num"]
        ack_ok = ctx.build != "offline" or float(nk.get("input_ack_seq_n", 0.0)) >= float(target_seq)
        dt_ok = float(nk.get("integrated_dt_s", 0.0)) >= min_dt_s
        spd_ok = min_speed is None or float(nk.get("speed_mps", 0.0)) >= min_speed
        if ack_ok and dt_ok and spd_ok:
            return out
        time.sleep(0.05)
    return last_out


def _run_scam_s1(
    ctx: f03_common.PartContext,
    drv: _InputDriver,
    paths_fx: dict,
    anchor_y: float,
    mutant: str | None,
) -> None:
    phase = "SCAM-S1"
    anchor = paths_fx["anchor_pose"]

    # Capa 1: NaN e Inf rechazados localmente sin lineas nuevas en el bridge.
    ev_before = _bridge_event_count(ctx)
    nan_rej = False
    inf_rej = False
    try:
        wire.pack_payload(scalars_num={"bad": float("nan")})
    except ValueError:
        nan_rej = True
    try:
        wire.pack_payload(scalars_num={"bad": float("inf")})
    except ValueError:
        inf_rej = True
    ev_after = _bridge_event_count(ctx)
    ctx.record_scenario(
        {
            "bridge_lines_delta": ev_after - ev_before,
            "ev": "wire_nan",
            "h_ms": ctx.now_h_ms(),
            "inf_rejected_b": inf_rej,
            "nan_rejected_b": nan_rej,
            "phase": phase,
            "step": "wire",
        }
    )

    # Negativa j = 0 con camara cerrada tras SCAM-S0.
    _read_state(ctx, phase, "pre_0")
    _issue_op(
        ctx,
        phase,
        "neg_0",
        "scam_pose_apply",
        wire.pack_payload(scalars_str={"name": "P0"}),
    )
    _read_state(ctx, phase, "post_0")

    # Abrir camara libre en estado sano (3 tramos por teclado).
    _issue_op(
        ctx,
        phase,
        "open_free",
        "scam_free_op",
        wire.pack_payload(
            scalars_num={
                "ang_speed_degps": 90.0,
                "fov_rad": float(anchor["fov_rad"]),
                "op_code": 1.0,
                "pitch_deg": float(anchor["pitch_deg"]),
                "roll_deg": float(anchor["roll_deg"]),
                "speed_mps": 4.0,
                "x_m": float(anchor["anchor_x_m"]),
                "y_m": float(anchor_y),
                "yaw_deg": float(anchor["yaw_deg"]),
                "z_m": float(anchor["anchor_z_m"]),
            }
        ),
        record=False,
    )
    s_init_out = _read_state(ctx, phase, "s_init")
    dt0 = float(s_init_out.payload["num"].get("integrated_dt_s", 0.0))

    # Tramo 1: 4.0 m/s durante 500 ms -> ~2.0 m.
    seq1, _ = drv.key_hold(["KC_W"], 500.0)
    s_a_out = _wait_free_input(ctx, seq1, dt0 + 0.48)
    _record_state_outcome(ctx, phase, "s_a", s_a_out)
    dt1 = float(s_a_out.payload["num"].get("integrated_dt_s", 0.0))

    # Tramo 2: KC_PRIOR (8.0 m/s) + KC_W durante 500 ms -> ~4.0 m.
    drv.key_tap(["KC_PRIOR"])
    seq2, _ = drv.key_hold(["KC_W"], 500.0)
    s_b_out = _wait_free_input(ctx, seq2, dt1 + 0.48, min_speed=8.0)
    _record_state_outcome(ctx, phase, "s_b", s_b_out)
    dt2 = float(s_b_out.payload["num"].get("integrated_dt_s", 0.0))

    # Tramo 3: giro KC_RIGHT + KC_UP durante 300 ms (~27 deg sin desplazarse).
    seq3, _ = drv.key_hold(["KC_RIGHT", "KC_UP"], 300.0)
    s_0_out = _wait_free_input(ctx, seq3, dt2 + 0.28)
    _record_state_outcome(ctx, phase, "s_0", s_0_out)

    _issue_op(
        ctx,
        phase,
        "save_p0",
        "scam_pose_save",
        wire.pack_payload(scalars_str={"name": "P0", "overwrite": "0"}),
    )

    # Negativas individuales 1..5 en estado sano.
    s0_nk = s_0_out.payload["num"]
    neg_specs = [
        (1, "scam_pose_save", wire.pack_payload(scalars_str={"name": "", "overwrite": "0"})),
        (2, "scam_pose_save", wire.pack_payload(scalars_str={"name": "P0", "overwrite": "0"})),
        (3, "scam_pose_apply", wire.pack_payload(scalars_str={"name": "NO_EXISTE"})),
        (
            4,
            "scam_pose_apply",
            wire.pack_payload(
                scalars_str={"name": ""},
                scalars_num={
                    "fov_rad": 0.0,
                    "pitch_deg": 0.0,
                    "roll_deg": 0.0,
                    "x_m": float(s0_nk["x_m"]),
                    "y_m": float(s0_nk["y_m"]),
                    "yaw_deg": 0.0,
                    "z_m": float(s0_nk["z_m"]),
                },
            ),
        ),
        (
            5,
            "scam_pose_apply",
            wire.pack_payload(
                scalars_str={"name": ""},
                scalars_num={
                    "fov_rad": 0.7,
                    "pitch_deg": 120.0,
                    "roll_deg": 0.0,
                    "x_m": float(s0_nk["x_m"]),
                    "y_m": float(s0_nk["y_m"]),
                    "yaw_deg": 0.0,
                    "z_m": float(s0_nk["z_m"]),
                },
            ),
        ),
    ]
    for j, verb, payload in neg_specs:
        _read_state(ctx, phase, f"pre_{j}")
        _issue_op(ctx, phase, f"neg_{j}", verb, payload)
        _read_state(ctx, phase, f"post_{j}")

    # N8: seis ordenes sin jugador (cam_no_player) acotadas por pre_nc y post_nc.
    _read_state(ctx, phase, "pre_nc")
    short_arc = paths_fx["paths"]["short_arc_6s"]
    nc_cases = [
        ("no_client_free", "scam_free_op", wire.pack_payload(scalars_num={"op_code": 3.0})),
        ("no_client_pose", "scam_pose_apply", wire.pack_payload(scalars_str={"name": "P0"})),
        ("no_client_hud", "scam_hud_op", wire.pack_payload(scalars_num={"op_code": 0.0})),
        (
            "no_client_dof",
            "scam_dof_set",
            wire.pack_payload(
                scalars_num={"enable_b": 0.0, "focus_blur": 0.0, "focus_dist_m": 0.0}
            ),
        ),
        (
            "no_client_path",
            "scam_path_start",
            _path_keys_payload(short_arc["keys"], anchor_y, "catmull_rom", "scripted", "1"),
        ),
        (
            "no_client_sample",
            "scam_sample_start",
            wire.pack_payload(scalars_num={"duration_ms": 500.0}),
        ),
    ]
    for step, verb, payload in nc_cases:
        _issue_op(ctx, phase, step, verb, payload, qa_fault="cam_no_player")
    _read_state(ctx, phase, "post_nc")

    # Ida y vuelta de pose con alabeo (P_roll y P0).
    _issue_op(
        ctx,
        phase,
        "apply_p_roll_initial",
        "scam_pose_apply",
        wire.pack_payload(
            scalars_str={"name": ""},
            scalars_num={
                "fov_rad": 0.85,
                "pitch_deg": -12.0,
                "roll_deg": 18.0,
                "x_m": float(s0_nk["x_m"]),
                "y_m": float(s0_nk["y_m"]),
                "yaw_deg": 35.0,
                "z_m": float(s0_nk["z_m"]),
            },
        ),
        record=False,
    )
    _issue_op(
        ctx,
        phase,
        "save_p_roll",
        "scam_pose_save",
        wire.pack_payload(scalars_str={"name": "P_roll", "overwrite": "1"}),
    )
    _issue_op(
        ctx,
        phase,
        "move_away",
        "scam_pose_apply",
        wire.pack_payload(
            scalars_str={"name": ""},
            scalars_num={
                "fov_rad": 1.10,
                "pitch_deg": 20.0,
                "roll_deg": -15.0,
                "x_m": float(s0_nk["x_m"]) + 15.0,
                "y_m": float(s0_nk["y_m"]) + 1.0,
                "yaw_deg": -110.0,
                "z_m": float(s0_nk["z_m"]) + 5.0,
            },
        ),
        record=False,
    )
    _read_state(ctx, phase, "moved")

    p_roll_fault = "cam_swap_axes" if mutant == "swap_axes" else ""
    _issue_op(
        ctx,
        phase,
        "reapply_p_roll_op",
        "scam_pose_apply",
        wire.pack_payload(scalars_str={"name": "P_roll"}),
        qa_fault=p_roll_fault,
        record=False,
    )
    time.sleep(0.025)
    p_roll_state = _read_state(ctx, phase, "p_roll_applied")
    if mutant == "swap_axes":
        ctx.write_injection(
            mutant="swap_axes",
            kind="qa_fault",
            target="client:scam_pose_apply:P_roll",
            observable_effect={
                "p_roll_pitch_deg": float(p_roll_state.payload["num"].get("pitch_deg", 0.0)),
                "p_roll_yaw_deg": float(p_roll_state.payload["num"].get("yaw_deg", 0.0)),
                "qa_fault": "cam_swap_axes",
            },
        )

    p0_fault = "cam_no_activate" if mutant == "inactive_cam" else ""
    _issue_op(
        ctx,
        phase,
        "reapply_p0_op",
        "scam_pose_apply",
        wire.pack_payload(scalars_str={"name": "P0"}),
        qa_fault=p0_fault,
        record=False,
    )
    time.sleep(0.025)
    p0_state = _read_state(ctx, phase, "p0_applied")
    if mutant == "inactive_cam":
        ctx.write_injection(
            mutant="inactive_cam",
            kind="qa_fault",
            target="client:scam_pose_apply:P0",
            observable_effect={
                "p0_active_b": float(p0_state.payload["num"].get("active_b", -1.0)),
                "qa_fault": "cam_no_activate",
            },
        )

    _issue_op(
        ctx,
        phase,
        "close_free",
        "scam_free_op",
        wire.pack_payload(scalars_num={"op_code": 3.0}),
        record=False,
    )


def _poll_until_dtsum(ctx: f03_common.PartContext, job_id: str, target_ms: float, timeout_s: float = 12.0):
    deadline = time.monotonic() + timeout_s
    last_out = None
    while time.monotonic() < deadline:
        out = f03_common.issue_one(ctx, "client", "scam_state_read", wire.empty_payload())
        last_out = out
        sk = out.payload["str"]
        nk = out.payload["num"]
        if sk.get("cam_job_id") == job_id and sk.get("cam_job_state") == "running":
            if float(nk.get("cam_dtsum_ms", 0.0)) >= target_ms:
                return out
        elif sk.get("cam_job_state", "") != "running":
            return out
        time.sleep(0.02)
    return last_out


def _run_scam_s2(
    ctx: f03_common.PartContext,
    paths_fx: dict,
    anchor_y: float,
    mutant: str | None,
) -> None:
    phase = "SCAM-S2"
    anchor = paths_fx["anchor_pose"]
    short_arc = paths_fx["paths"]["short_arc_6s"]
    linear_hud = paths_fx["paths"]["linear_hud_6s"]

    _issue_op(
        ctx,
        phase,
        "s2_open_cam",
        "scam_free_op",
        wire.pack_payload(
            scalars_num={
                "ang_speed_degps": 90.0,
                "fov_rad": float(anchor["fov_rad"]),
                "op_code": 1.0,
                "pitch_deg": float(anchor["pitch_deg"]),
                "roll_deg": float(anchor["roll_deg"]),
                "speed_mps": 4.0,
                "x_m": float(anchor["anchor_x_m"]),
                "y_m": float(anchor_y),
                "yaw_deg": float(anchor["yaw_deg"]),
                "z_m": float(anchor["anchor_z_m"]),
            }
        ),
        record=False,
    )

    k0 = dict(short_arc["keys"][0])
    k1 = dict(short_arc["keys"][1])
    k2 = dict(short_arc["keys"][2])

    bad_k_nonmono = [dict(k0, t_s=0.0), dict(k1, t_s=3.0), dict(k2, t_s=2.5)]
    bad_k_dup_t = [dict(k0, t_s=0.0), dict(k1, t_s=0.0)]
    bad_k_fov = [dict(k0, fov_rad=3.5), dict(k1)]
    bad_k_blur = [dict(k0, focus_blur=1.5), dict(k1)]
    bad_k_fdist = [dict(k0, focus_dist_m=-1.0), dict(k1)]

    neg_payloads = [
        (1, _path_keys_payload([k0], anchor_y, "linear", "scripted", "1")),
        (2, _path_keys_payload(bad_k_nonmono, anchor_y, "linear", "scripted", "1")),
        (3, _path_keys_payload(bad_k_dup_t, anchor_y, "linear", "scripted", "1")),
        (4, _path_keys_payload(bad_k_fov, anchor_y, "linear", "scripted", "1")),
        (5, _path_keys_payload(bad_k_blur, anchor_y, "linear", "scripted", "1")),
        (6, _path_keys_payload(bad_k_fdist, anchor_y, "linear", "scripted", "1")),
    ]
    for j, payload in neg_payloads:
        _read_state(ctx, phase, f"pre_{j}")
        _issue_op(ctx, phase, f"neg_{j}", "scam_path_start", payload)
        _read_state(ctx, phase, f"post_{j}")

    s2_fault_map = {
        "long_arc": "cam_long_arc",
        "frozen_fov": "cam_frozen_fov",
        "path_jump": "cam_path_jump",
        "late_finish": "cam_late_finish",
    }
    s2_fault = s2_fault_map.get(mutant or "", "")

    # Pasada 1: short_arc_6s catmull_rom scripted + prueba de camino ocupado.
    start1 = _issue_op(
        ctx,
        phase,
        "path_1_start",
        "scam_path_start",
        _path_keys_payload(short_arc["keys"], anchor_y, "catmull_rom", "scripted", "1"),
        qa_fault=s2_fault,
    )
    job1_id = str(start1.payload["str"].get("job", ""))
    busy_pre_out = _poll_until_dtsum(ctx, job1_id, 800.0)
    _record_state_outcome(ctx, phase, "busy_pre", busy_pre_out)
    _issue_op(
        ctx,
        phase,
        "busy_attempt",
        "scam_path_start",
        _path_keys_payload(linear_hud["keys"], anchor_y, "linear", "scripted", "1"),
    )
    _read_state(ctx, phase, "busy_post")
    _wait_job_terminal(ctx, job1_id, timeout_s=20.0)
    rows1 = _dump_job_jsonl(ctx, job1_id, s_cam_eval.PATH_COLS_36, "path_catmull_scripted.jsonl")
    if mutant in s2_fault_map:
        ctx.write_injection(
            mutant=mutant,
            kind="qa_fault",
            target="client:scam_path_start:short_arc_6s",
            observable_effect={
                "job_id": job1_id,
                "last_dtsum_ms": float(rows1[-1]["dtsum_ms"]) if rows1 else 0.0,
                "qa_fault": s2_fault,
                "rows_n": len(rows1),
            },
        )

    # Pasada 2: short_arc_6s linear engine_interp.
    start2 = _issue_op(
        ctx,
        phase,
        "path_2_start",
        "scam_path_start",
        _path_keys_payload(short_arc["keys"], anchor_y, "linear", "engine_interp", "1"),
    )
    job2_id = str(start2.payload["str"].get("job", ""))
    _wait_job_terminal(ctx, job2_id, timeout_s=20.0)
    _dump_job_jsonl(ctx, job2_id, s_cam_eval.PATH_COLS_36, "path_engine_interp.jsonl")


def _run_scam_s3(
    ctx: f03_common.PartContext,
    paths_fx: dict,
    rois: dict,
    anchor_y: float,
    mutant: str | None,
) -> None:
    phase = "SCAM-S3"
    linear_hud = paths_fx["paths"]["linear_hud_6s"]

    _issue_op(
        ctx,
        phase,
        "hud_preset_op",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 5.0, "preset_mask": 258.0}),
    )
    _read_state(ctx, phase, "hud_preset")

    s3_fault_map = {
        "hud_leak": "cam_force_quickbar",
        "hud_restore_corrupt": "cam_restore_showhud",
    }
    s3_fault = s3_fault_map.get(mutant or "", "")

    start_hud = _issue_op(
        ctx,
        phase,
        "path_hud_start",
        "scam_path_start",
        _path_keys_payload(linear_hud["keys"], anchor_y, "linear", "scripted", "1"),
        qa_fault=s3_fault,
    )
    hud_job_id = str(start_hud.payload["str"].get("job", ""))

    pre_cap_out = _poll_until_dtsum(ctx, hud_job_id, 1950.0)
    _record_state_outcome(ctx, phase, "pre_cap", pre_cap_out)
    pre_nk = pre_cap_out.payload["num"]
    cap_h = ctx.now_h_ms()
    if ctx.build == "offline":
        win_w, win_h = _render_offline_bmp(
            ctx.part_dir / "samples" / "hud_during.bmp", pre_nk, rois
        )
    else:
        hwnd = find_dayz_window()
        win_w, win_h = capture_window(hwnd, ctx.part_dir / "samples" / "hud_during.bmp")
    post_cap_out = _read_state(ctx, phase, "post_cap")
    post_nk = post_cap_out.payload["num"]

    pre_f = int(round(float(pre_nk.get("frame", 0.0))))
    post_f = int(round(float(post_nk.get("frame", pre_f))))
    cap_frame = (pre_f + post_f) // 2
    cap_tick = 0.5 * (float(pre_nk.get("tick_ms", 0.0)) + float(post_nk.get("tick_ms", 0.0)))
    ctx.record_scenario(
        {
            "capture_h_ms": cap_h,
            "capture_tick_ms": cap_tick,
            "ev": "capture",
            "file": "hud_during.bmp",
            "frame": cap_frame,
            "h_ms": cap_h,
            "phase": phase,
            "post_step": "post_cap",
            "pre_step": "pre_cap",
            "step": "cap_hud_during",
            "window_h": win_h,
            "window_w": win_w,
        }
    )

    _wait_job_terminal(ctx, hud_job_id, timeout_s=20.0)
    hud_rows = _dump_job_jsonl(ctx, hud_job_id, s_cam_eval.PATH_COLS_36, "path_linear_hud.jsonl")
    post_hud_out = _read_state(ctx, phase, "post_path_hud")
    if mutant in s3_fault_map:
        qb_leak_n = sum(1 for r in hud_rows if float(r.get("qb_vis_b", 0.0)) >= 0.5)
        ctx.write_injection(
            mutant=mutant,
            kind="qa_fault",
            target="client:scam_path_start:linear_hud_6s",
            observable_effect={
                "job_id": hud_job_id,
                "post_flags_mask": float(post_hud_out.payload["num"].get("flags_mask", -1.0)),
                "qa_fault": s3_fault,
                "qb_leak_rows_n": qb_leak_n,
            },
        )

    _issue_op(
        ctx,
        phase,
        "hud_preset_clear",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 5.0, "preset_mask": 0.0}),
        record=False,
    )

    # Pose efectiva exacta de la fila capturada para las referencias emparejadas.
    eff_row = None
    for r in hud_rows:
        if int(round(float(r["frame"]))) == cap_frame:
            eff_row = r
            break
    if eff_row is None and hud_rows:
        eff_row = min(hud_rows, key=lambda r: abs(float(r["tick_ms"]) - cap_tick))
    if eff_row is None:
        eff_row = pre_nk

    _issue_op(
        ctx,
        phase,
        "open_clean_ref",
        "scam_free_op",
        wire.pack_payload(
            scalars_num={
                "ang_speed_degps": 90.0,
                "fov_rad": float(eff_row["fov_rad"]),
                "op_code": 1.0,
                "pitch_deg": float(eff_row["pitch_deg"]),
                "roll_deg": float(eff_row["roll_deg"]),
                "speed_mps": 4.0,
                "x_m": float(eff_row["x_m"]),
                "y_m": float(eff_row["y_m"]),
                "yaw_deg": float(eff_row["yaw_deg"]),
                "z_m": float(eff_row["z_m"]),
            }
        ),
        record=False,
    )
    _issue_op(
        ctx,
        phase,
        "hide_clean_ref",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 1.0}),
        record=False,
    )
    clean_ref_out = _read_state(ctx, phase, "clean_ref_state")
    clean_nk = clean_ref_out.payload["num"]
    _capture_scene(
        ctx, phase, "cap_hud_clean_ref", "hud_clean_ref.bmp", clean_nk, rois, "clean_ref_state"
    )
    _capture_scene(
        ctx,
        phase,
        "cap_hud_clean_ref_repeat",
        "hud_clean_ref_repeat.bmp",
        clean_nk,
        rois,
        "clean_ref_state",
    )

    # Control negativo 1: forzar quickbar visible en la misma pose.
    _issue_op(
        ctx,
        phase,
        "ctrl_qb_force",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"mode": 1.0, "op_code": 4.0}),
        record=False,
    )
    qb_read = _issue_op(
        ctx,
        phase,
        "control_read_qb",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 0.0}),
    )
    _capture_scene(
        ctx,
        phase,
        "cap_hud_visible_ref",
        "hud_visible_ref.bmp",
        qb_read.payload["num"],
        rois,
        "clean_ref_state",
    )

    # Control negativo 2: crear overlay 24x24 bajo m_HudPanelWidget.
    _issue_op(
        ctx,
        phase,
        "ctrl_ovl_force",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"mode": 2.0, "op_code": 4.0}),
        record=False,
    )
    _issue_op(
        ctx,
        phase,
        "control_read_ovl",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 0.0}),
    )

    # Limpieza de SCAM-S3.
    _issue_op(
        ctx,
        phase,
        "ctrl_cleanup",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"mode": 0.0, "op_code": 4.0}),
        record=False,
    )
    _issue_op(
        ctx,
        phase,
        "s3_close_cam",
        "scam_free_op",
        wire.pack_payload(scalars_num={"op_code": 3.0}),
        record=False,
    )


def _run_dof_path_with_phases(
    ctx: f03_common.PartContext,
    phase: str,
    path_name: str,
    prefix: str,
    keys: list[dict],
    anchor_y: float,
    rois: dict,
    qa_fault: str,
    post_step: str,
    dump_file: str,
) -> tuple[str, list[dict], object]:
    start_out = _issue_op(
        ctx,
        phase,
        f"start_{path_name}",
        "scam_path_start",
        _path_keys_payload(keys, anchor_y, "linear", "scripted", "1"),
        qa_fault=qa_fault,
    )
    jid = str(start_out.payload["str"].get("job", ""))
    targets = [(1, 0.0), (2, 1460.0), (3, 2960.0), (4, 5700.0)]
    for k, target_ms in targets:
        pre_out = _poll_until_dtsum(ctx, jid, target_ms)
        pre_step = f"{path_name}_t{k}_pre"
        post_k_step = f"{path_name}_t{k}_post"
        _record_state_outcome(ctx, phase, pre_step, pre_out)
        pre_nk = pre_out.payload["num"]
        cap_h = ctx.now_h_ms()
        bmp_name = f"{prefix}_t{k}.bmp"
        if ctx.build == "offline":
            win_w, win_h = _render_offline_bmp(
                ctx.part_dir / "samples" / bmp_name, pre_nk, rois
            )
        else:
            hwnd = find_dayz_window()
            win_w, win_h = capture_window(hwnd, ctx.part_dir / "samples" / bmp_name)
        post_out = _read_state(ctx, phase, post_k_step)
        post_nk = post_out.payload["num"]
        ctx.record_scenario(
            {
                "capture_h_ms": cap_h,
                "capture_tick_ms": 0.5
                * (float(pre_nk.get("tick_ms", 0.0)) + float(post_nk.get("tick_ms", 0.0))),
                "ev": "capture",
                "file": bmp_name,
                "h_ms": cap_h,
                "phase": phase,
                "post_step": post_k_step,
                "pre_step": pre_step,
                "step": f"cap_{prefix}_t{k}",
                "window_h": win_h,
                "window_w": win_w,
            }
        )
        ctx.record_scenario(
            {
                "ev": "phase",
                "h_ms": ctx.now_h_ms(),
                "path": path_name,
                "phase": phase,
                "phase_k": k,
                "post_dtsum_ms": float(post_nk.get("cam_dtsum_ms", 0.0)),
                "post_step": post_k_step,
                "pre_dtsum_ms": float(pre_nk.get("cam_dtsum_ms", 0.0)),
                "pre_step": pre_step,
                "step": f"{path_name}_t{k}",
            }
        )

    _wait_job_terminal(ctx, jid, timeout_s=20.0)
    rows = _dump_job_jsonl(ctx, jid, s_cam_eval.PATH_COLS_36, dump_file)
    post_done_out = _read_state(ctx, phase, post_step)
    return jid, rows, post_done_out


def _run_scam_s4(
    ctx: f03_common.PartContext,
    paths_fx: dict,
    rois: dict,
    anchor_y: float,
    mutant: str | None,
) -> None:
    phase = "SCAM-S4"
    anchor = paths_fx["anchor_pose"]
    dof_var = paths_fx["paths"]["dof_var_6s"]
    dof_fix = paths_fx["paths"]["dof_fixed_6s"]

    _issue_op(
        ctx,
        phase,
        "s4_open_cam",
        "scam_free_op",
        wire.pack_payload(
            scalars_num={
                "ang_speed_degps": 90.0,
                "fov_rad": 0.70,
                "op_code": 1.0,
                "pitch_deg": float(anchor["pitch_deg"]),
                "roll_deg": float(anchor["roll_deg"]),
                "speed_mps": 4.0,
                "x_m": float(anchor["anchor_x_m"]),
                "y_m": float(anchor_y),
                "yaw_deg": float(anchor["yaw_deg"]),
                "z_m": float(anchor["anchor_z_m"]),
            }
        ),
        record=False,
    )
    _issue_op(
        ctx,
        phase,
        "s4_hud_hide",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 1.0}),
        record=False,
    )
    _issue_op(
        ctx,
        phase,
        "s4_dof_base",
        "scam_dof_set",
        wire.pack_payload(scalars_num={"enable_b": 1.0, "focus_blur": 0.6, "focus_dist_m": 3.5}),
        record=False,
    )

    neg_cases = [
        (1, 1.0, 0.0, 0.5),
        (2, 1.0, -2.0, 0.5),
        (3, 1.0, 10.0, 1.5),
        (4, 1.0, 10.0, -0.1),
    ]
    for j, en, fdist, fblur in neg_cases:
        pre_out = _read_state(ctx, phase, f"pre_{j}")
        if j == 1:
            _capture_scene(
                ctx,
                phase,
                "cap_dof_before_reject",
                "dof_before_reject.bmp",
                pre_out.payload["num"],
                rois,
                "pre_1",
            )
        _issue_op(
            ctx,
            phase,
            f"neg_{j}",
            "scam_dof_set",
            wire.pack_payload(
                scalars_num={"enable_b": en, "focus_blur": fblur, "focus_dist_m": fdist}
            ),
        )
        post_out = _read_state(ctx, phase, f"post_{j}")
        _capture_scene(
            ctx,
            phase,
            f"cap_dof_after_reject_{j}",
            f"dof_after_reject_{j}.bmp",
            post_out.payload["num"],
            rois,
            f"post_{j}",
        )

    dof_fault = "cam_dof_off" if mutant == "dof_off" else ""

    # Par estatico DOF: noblur, near2m, far50m.
    _issue_op(
        ctx,
        phase,
        "set_ctrl_noblur",
        "scam_dof_set",
        wire.pack_payload(scalars_num={"enable_b": 0.0, "focus_blur": 0.0, "focus_dist_m": 0.0}),
        record=False,
    )
    nb_pre = _read_state(ctx, phase, "ctrl_noblur_pre")
    _capture_scene(
        ctx,
        phase,
        "cap_dof_ctrl_noblur",
        "dof_ctrl_noblur.bmp",
        nb_pre.payload["num"],
        rois,
        "ctrl_noblur_pre",
        "ctrl_noblur_post",
    )
    _capture_scene(
        ctx,
        phase,
        "cap_dof_ctrl_noblur_repeat",
        "dof_ctrl_noblur_repeat.bmp",
        nb_pre.payload["num"],
        rois,
        "ctrl_noblur_pre",
        "ctrl_noblur_post",
    )
    _read_state(ctx, phase, "ctrl_noblur_post")

    _issue_op(
        ctx,
        phase,
        "set_ctrl_near2m",
        "scam_dof_set",
        wire.pack_payload(scalars_num={"enable_b": 1.0, "focus_blur": 1.0, "focus_dist_m": 2.0}),
        qa_fault=dof_fault,
        record=False,
    )
    if ctx.build != "offline":
        time.sleep(0.15)
    near_pre = _read_state(ctx, phase, "ctrl_near2m_pre")
    _capture_scene(
        ctx,
        phase,
        "cap_dof_ctrl_near2m",
        "dof_ctrl_near2m.bmp",
        near_pre.payload["num"],
        rois,
        "ctrl_near2m_pre",
        "ctrl_near2m_post",
    )
    _read_state(ctx, phase, "ctrl_near2m_post")

    _issue_op(
        ctx,
        phase,
        "set_ctrl_far50m",
        "scam_dof_set",
        wire.pack_payload(scalars_num={"enable_b": 1.0, "focus_blur": 1.0, "focus_dist_m": 50.0}),
        qa_fault=dof_fault,
        record=False,
    )
    if ctx.build != "offline":
        time.sleep(0.15)
    far_pre = _read_state(ctx, phase, "ctrl_far50m_pre")
    _capture_scene(
        ctx,
        phase,
        "cap_dof_ctrl_far50m",
        "dof_ctrl_far50m.bmp",
        far_pre.payload["num"],
        rois,
        "ctrl_far50m_pre",
        "ctrl_far50m_post",
    )
    _read_state(ctx, phase, "ctrl_far50m_post")

    if mutant == "dof_off":
        ctx.write_injection(
            mutant="dof_off",
            kind="qa_fault",
            target="client:scam_dof_set:near2m",
            observable_effect={
                "near2m_sent_blur": float(near_pre.payload["num"].get("sent_focus_blur", -1.0)),
                "qa_fault": "cam_dof_off",
            },
        )

    _issue_op(
        ctx,
        phase,
        "s4_static_reset",
        "scam_dof_set",
        wire.pack_payload(scalars_num={"enable_b": 0.0, "focus_blur": 0.0, "focus_dist_m": 0.0}),
        record=False,
    )
    _read_state(ctx, phase, "post_reset")
    _issue_op(
        ctx,
        phase,
        "s4_close_static_cam",
        "scam_free_op",
        wire.pack_payload(scalars_num={"op_code": 3.0}),
        record=False,
    )

    # Caminos de enfoque: dof_var_6s vs dof_fixed_6s.
    var_fault = "cam_ignore_focus_keys" if mutant == "ignore_focus_keys" else ""
    var_jid, var_rows, post_var_out = _run_dof_path_with_phases(
        ctx,
        phase,
        "dof_var_6s",
        "var",
        dof_var["keys"],
        anchor_y,
        rois,
        var_fault,
        "post_dof_var",
        "path_dof_var.jsonl",
    )
    if mutant == "ignore_focus_keys":
        ctx.write_injection(
            mutant="ignore_focus_keys",
            kind="qa_fault",
            target="client:scam_path_start:dof_var_6s",
            observable_effect={
                "job_id": var_jid,
                "post_sent_focus_dist_m": float(
                    post_var_out.payload["num"].get("sent_focus_dist_m", -1.0)
                ),
                "qa_fault": "cam_ignore_focus_keys",
                "rows_n": len(var_rows),
            },
        )

    _run_dof_path_with_phases(
        ctx,
        phase,
        "dof_fixed_6s",
        "fix",
        dof_fix["keys"],
        anchor_y,
        rois,
        "",
        "post_dof_fix",
        "path_dof_fix.jsonl",
    )

    _issue_op(
        ctx,
        phase,
        "s4_hud_restore",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 2.0}),
        record=False,
    )


def _run_scam_s5(
    ctx: f03_common.PartContext,
    drv: _InputDriver,
    paths_fx: dict,
    anchor_y: float,
) -> None:
    phase = "SCAM-S5"
    linear_hud = paths_fx["paths"]["linear_hud_6s"]

    _issue_op(
        ctx,
        phase,
        "hud_preset_op",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 5.0, "preset_mask": 258.0}),
    )
    _read_state(ctx, phase, "hud_preset")

    sample_start = _issue_op(
        ctx,
        phase,
        "sample_s5_start",
        "scam_sample_start",
        wire.pack_payload(scalars_num={"duration_ms": 3500.0}),
    )
    sample_job_id = str(sample_start.payload["str"].get("job", ""))

    path_start = _issue_op(
        ctx,
        phase,
        "path_s5_start",
        "scam_path_start",
        _path_keys_payload(linear_hud["keys"], anchor_y, "linear", "scripted", "1"),
    )
    cam_job_id = str(path_start.payload["str"].get("job", ""))

    _poll_until_dtsum(ctx, cam_job_id, 1500.0)

    stop_out = _issue_op(
        ctx,
        phase,
        "stop_op",
        "job_stop",
        wire.pack_payload(scalars_str={"job": cam_job_id}),
    )
    after_stop_h = ctx.now_h_ms()
    enq_t, res_t = _find_bridge_op_times(ctx, stop_out.op_id)
    send_h = enq_t if enq_t is not None else float(stop_out.issued_ms)
    ack_bridge_h = res_t if res_t is not None else after_stop_h
    u_ms = max(0.0, ack_bridge_h - send_h)
    ctx.record_scenario(
        {
            "ev": "stop",
            "h_ms": after_stop_h,
            "job_id": cam_job_id,
            "phase": phase,
            "step": "stop",
            "stop_ack_h_ms": max(after_stop_h, ack_bridge_h),
            "stop_done_ms": stop_out.done_ms,
            "stop_recv_ms": stop_out.recv_ms,
            "stop_send_h_ms": send_h,
            "u_ms": u_ms,
        }
    )

    # Ventana quieta post-handoff (> 100 ms).
    time.sleep(0.12)

    # Rafaga A: 5 pulsos +40 px cada 40 ms.
    for i in range(5):
        seq, issued_h = drv.mouse_move(40.0)
        ctx.record_scenario(
            {
                "burst": "A",
                "dx_px": 40.0,
                "ev": "pulse",
                "h_ms": issued_h,
                "issued_h_ms": issued_h,
                "kind": "mouse_move",
                "phase": phase,
                "seq_n": seq,
                "step": f"a{i}",
            }
        )
        if i < 4:
            time.sleep(0.04)

    # Separacion limpia antes de la rafaga inversa B.
    time.sleep(0.10)

    # Rafaga B: 5 pulsos -40 px cada 40 ms.
    for i in range(5):
        seq, issued_h = drv.mouse_move(-40.0)
        ctx.record_scenario(
            {
                "burst": "B",
                "dx_px": -40.0,
                "ev": "pulse",
                "h_ms": issued_h,
                "issued_h_ms": issued_h,
                "kind": "mouse_move",
                "phase": phase,
                "seq_n": seq,
                "step": f"b{i}",
            }
        )
        if i < 4:
            time.sleep(0.04)

    _wait_job_terminal(ctx, sample_job_id, timeout_s=15.0)
    _dump_job_jsonl(ctx, sample_job_id, s_cam_eval.SAMPLE_COLS_18, "control_recovery.jsonl")
    f03_common.issue_one(
        ctx,
        "client",
        "job_free",
        wire.pack_payload(scalars_str={"job": cam_job_id}),
    )

    _read_state(ctx, phase, "post_stop_state")
    _issue_op(
        ctx,
        phase,
        "hud_preset_clear",
        "scam_hud_op",
        wire.pack_payload(scalars_num={"op_code": 5.0, "preset_mask": 0.0}),
        record=False,
    )


def _run_standard_part(ctx: f03_common.PartContext, part_name: str) -> None:
    mutant = part_name[4:] if part_name.startswith("mut-") else None
    paths_fx, rois = _load_fixtures()
    drv = _InputDriver(ctx)

    anchor_y = _run_scam_s0(ctx, paths_fx, rois)
    _run_scam_s1(ctx, drv, paths_fx, anchor_y, mutant)
    _run_scam_s2(ctx, paths_fx, anchor_y, mutant)
    _run_scam_s3(ctx, paths_fx, rois, anchor_y, mutant)
    _run_scam_s4(ctx, paths_fx, rois, anchor_y, mutant)
    _run_scam_s5(ctx, drv, paths_fx, anchor_y)


def _planned_parts(part_arg: str) -> list[str]:
    valid_muts = [f"mut-{name}" for name in s_cam_mutants.EXPECTED_MUTANTS]
    all_parts = ["run", *valid_muts]
    if not part_arg or part_arg == "all":
        return all_parts
    selected = [p.strip() for p in str(part_arg).split(",") if p.strip()]
    for p in selected:
        if p not in all_parts:
            raise ValueError(f"unknown S-cam part: {p!r} (expected one of {all_parts})")
    return selected


def run_part(args, base_dir: Path, argv: list[str], part_name: str) -> dict:
    with f03_common.PartContext(
        base_dir=base_dir,
        part_name=part_name,
        spike_id=SPIKE_ID,
        args=args,
        argv=argv,
    ) as ctx:
        if ctx.startup_reason is None:
            _run_standard_part(ctx, part_name)
        ctx.collect_probe_budget_logs()
        ctx.finalize_manifest()

    part_dir = Path(base_dir) / part_name
    verdict = s_cam_eval.evaluate(part_dir)
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
