"""Extension S-cam para fake_peer (prefijo scam_, RPC 26102820..26102829)."""

import json
import math
from pathlib import Path

import wire
from fake_peer import FakeExt

PREFIX = "scam_"
RPC_BASE = 26102820

_CLIENT_VERBS = frozenset(
    {
        "scam_fixture_setup",
        "scam_state_read",
        "scam_free_op",
        "scam_pose_save",
        "scam_pose_apply",
        "scam_path_start",
        "scam_dof_set",
        "scam_hud_op",
        "scam_sample_start",
    }
)

PATH_NCOL = [
    "seq_n",
    "frame",
    "tick_ms",
    "dtsum_ms",
    "x_m",
    "y_m",
    "z_m",
    "yaw_deg",
    "pitch_deg",
    "roll_deg",
    "eng_x_m",
    "eng_y_m",
    "eng_z_m",
    "eng_dx",
    "eng_dy",
    "eng_dz",
    "fov_rad",
    "calc_focus_dist_m",
    "sent_focus_dist_m",
    "sent_focus_blur",
    "set_focus_calls_n",
    "active_b",
    "elem_vis_mask",
    "flags_mask",
    "qb_vis_b",
    "menu_open_b",
    "ovl_vis_b",
    "m00",
    "m01",
    "m02",
    "m10",
    "m11",
    "m12",
    "m20",
    "m21",
    "m22",
]

SAMPLE_NCOL = [
    "seq_n",
    "frame",
    "tick_ms",
    "dtsum_ms",
    "eng_x_m",
    "eng_y_m",
    "eng_z_m",
    "eng_dx",
    "eng_dy",
    "eng_dz",
    "fov_rad",
    "pl_cam_x_m",
    "pl_cam_y_m",
    "pl_cam_z_m",
    "pl_cam_dx",
    "pl_cam_dy",
    "pl_cam_dz",
    "mcam_active_b",
]

_HUD_HIDE_FLAGS = 1 | 2 | 32 | 2048
_QB_HIDE_FLAGS = 128 | 256 | 512


def _is_finite(val):
    return (
        not isinstance(val, bool)
        and isinstance(val, (int, float))
        and math.isfinite(float(val))
    )


def _is_int_num(val):
    if not _is_finite(val):
        return False
    return float(val).is_integer()


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _lerp(a, b, u):
    return a + (b - a) * u


def _wrap_deg(deg):
    v = (deg + 180.0) % 360.0 - 180.0
    return v


def _cross3(a, b):
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _dot3(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm3(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-12:
        return [0.0, 0.0, 1.0]
    return [v[0] / n, v[1] / n, v[2] / n]


def ypr_matrix(yaw_deg, pitch_deg, roll_deg):
    """Replica YawPitchRollMatrix medido en DayZ (s_cam_eval.py)."""
    y = math.radians(yaw_deg)
    p = math.radians(pitch_deg)
    r = math.radians(roll_deg)
    fwd = [math.cos(p) * math.sin(y), math.sin(p), math.cos(p) * math.cos(y)]
    up = [0.0, 1.0, 0.0] if abs(fwd[1]) < 0.9 else [1.0, 0.0, 0.0]
    side = _norm3(_cross3(up, fwd))
    upv = _cross3(fwd, side)
    cr = math.cos(r)
    sr = math.sin(r)
    m0 = [cr * side[i] - sr * upv[i] for i in range(3)]
    m1 = [sr * side[i] + cr * upv[i] for i in range(3)]
    return [m0, m1, fwd]


def matrix_to_angles(mat):
    fwd = mat[2]
    pitch = math.degrees(math.asin(_clamp(fwd[1], -1.0, 1.0)))
    yaw = math.degrees(math.atan2(fwd[0], fwd[2]))
    up = [0.0, 1.0, 0.0] if abs(fwd[1]) < 0.9 else [1.0, 0.0, 0.0]
    side0 = _norm3(_cross3(up, fwd))
    cr = _dot3(mat[0], side0)
    sr = _dot3(mat[1], side0)
    roll = math.degrees(math.atan2(sr, cr))
    return [yaw, pitch, roll]


def matrix_to_quat(mat):
    r00, r01, r02 = mat[0]
    r10, r11, r12 = mat[1]
    r20, r21, r22 = mat[2]
    tr = r00 + r11 + r22
    if tr > 0.0:
        s = 2.0 * math.sqrt(tr + 1.0)
        w = 0.25 * s
        x = (r21 - r12) / s
        y = (r02 - r20) / s
        z = (r10 - r01) / s
    elif r00 > r11 and r00 > r22:
        s = 2.0 * math.sqrt(1.0 + r00 - r11 - r22)
        w = (r21 - r12) / s
        x = 0.25 * s
        y = (r01 + r10) / s
        z = (r02 + r20) / s
    elif r11 > r22:
        s = 2.0 * math.sqrt(1.0 + r11 - r00 - r22)
        w = (r02 - r20) / s
        x = (r01 + r10) / s
        y = 0.25 * s
        z = (r12 + r21) / s
    else:
        s = 2.0 * math.sqrt(1.0 + r22 - r00 - r11)
        w = (r10 - r01) / s
        x = (r02 + r20) / s
        y = (r12 + r21) / s
        z = 0.25 * s
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < 1e-12:
        return [0.0, 0.0, 0.0, 1.0]
    return [x / n, y / n, z / n, w / n]


def quat_to_matrix(q):
    x, y, z, w = q
    return [
        [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - w * z), 2.0 * (x * z + w * y)],
        [2.0 * (x * y + w * z), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - w * x)],
        [2.0 * (x * z - w * y), 2.0 * (y * z + w * x), 1.0 - 2.0 * (x * x + y * y)],
    ]


def slerp_quat(qa, qb, u):
    ax, ay, az, aw = qa
    bx, by, bz, bw = qb
    d = ax * bx + ay * by + az * bz + aw * bw
    if d < 0.0:
        bx, by, bz, bw = -bx, -by, -bz, -bw
        d = -d
    if d > 0.9995:
        ox = ax + u * (bx - ax)
        oy = ay + u * (by - ay)
        oz = az + u * (bz - az)
        ow = aw + u * (bw - aw)
    else:
        omega = math.acos(_clamp(d, -1.0, 1.0))
        sino = math.sin(omega)
        w0 = math.sin((1.0 - u) * omega) / sino
        w1 = math.sin(u * omega) / sino
        ox = w0 * ax + w1 * bx
        oy = w0 * ay + w1 * by
        oz = w0 * az + w1 * bz
        ow = w0 * aw + w1 * bw
    n = math.sqrt(ox * ox + oy * oy + oz * oz + ow * ow)
    if n < 1e-12:
        return [0.0, 0.0, 0.0, 1.0]
    return [ox / n, oy / n, oz / n, ow / n]


def catmull_rom_pos(points, s):
    n = len(points)
    if n == 0:
        return [0.0, 0.0, 0.0]
    if n == 1:
        return list(points[0])
    s = _clamp(s, 0.0, 1.0)
    if s >= 1.0:
        return list(points[-1])
    scaled = s * (n - 1)
    idx = min(int(scaled), n - 2)
    u = scaled - idx
    p0 = points[max(0, idx - 1)]
    p1 = points[idx]
    p2 = points[idx + 1]
    p3 = points[min(n - 1, idx + 2)]
    u2 = u * u
    u3 = u2 * u
    out = []
    for k in range(3):
        val = 0.5 * (
            (2.0 * p1[k])
            + (-p0[k] + p2[k]) * u
            + (2.0 * p0[k] - 5.0 * p1[k] + 4.0 * p2[k] - p3[k]) * u2
            + (-p0[k] + 3.0 * p1[k] - 3.0 * p2[k] + p3[k]) * u3
        )
        out.append(val)
    return out


def _surface_y(x, z):
    return 300.0 + 0.001 * (x - 4500.0) + 0.001 * (z - 9800.0)


def _elem_vis_mask(flags):
    mask = 0
    inv = bool(flags & 1024)
    lhud_hid = bool(flags & (_HUD_HIDE_FLAGS | 16)) and not inv
    if not lhud_hid:
        mask |= 1 | 2 | 4
    veh_vis = bool(flags & 8) and not bool(flags & (4 | 32 | 2048))
    if veh_vis:
        mask |= 8
    rhud_hid = bool(flags & _HUD_HIDE_FLAGS) and not inv
    if not rhud_hid:
        mask |= 16 | 64
        if not bool(flags & 64):
            mask |= 32
    if not bool(flags & _QB_HIDE_FLAGS):
        mask |= 128
    return mask


class CamFakeExt(FakeExt):
    def __init__(self):
        super().__init__()
        self.peer = None
        self.jobs = None
        self.cam_exists = False
        self.cam_active = False
        self.cam_pos = [0.0, 0.0, 0.0]
        self.cam_rot = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        self.cam_fov = 0.7

        self.pl_cam_pos = [4500.0, 301.6, 9796.0]
        self.pl_cam_yaw_deg = 0.0
        self.pl_cam_pitch_deg = 0.0

        self.eng_pos = list(self.pl_cam_pos)
        self.eng_dir = [0.0, 0.0, 1.0]
        self.staged_eng_pos = list(self.pl_cam_pos)
        self.staged_eng_dir = [0.0, 0.0, 1.0]

        self.free_cam_active = False
        self.free_pos = [0.0, 0.0, 0.0]
        self.free_yaw_deg = 0.0
        self.free_pitch_deg = 0.0
        self.free_roll_deg = 0.0
        self.free_fov_rad = 0.7
        self.free_speed_mps = 4.0
        self.free_ang_speed_degps = 90.0
        self.speed_steps_n = 0
        self.free_input_frames = 0
        self.free_integrated_dt_s = 0.0
        self.input_ack_seq_n = 0

        self.control_disabled = False
        self.slow_stop_pending = False
        self.slow_stop_remaining_ms = 0.0

        self.focus_enabled_b = 0.0
        self.sent_focus_dist_m = 0.0
        self.sent_focus_blur = 0.0
        self.set_focus_calls_n = 0

        self.hud_flags_mask = 0
        self.saved_hud_flags_mask = 0
        self.aux_vis_mask = 127
        self.saved_aux_vis_mask = 127
        self.hud_hidden = False
        self.hud_hidden_by_job = False
        self.test_overlay_visible = False
        self.qb_items_n = 1
        self.menu_open_b = 0.0
        self.player_in_veh_b = 0.0

        self.saved_poses = {}
        self.saved_pose_order = []

        self.active_cam_job_id = ""
        self.active_sample_job_id = ""
        self.path_fault = ""
        self.path_pos_mode = "linear"
        self.path_interp_mode = "scripted"
        self.path_keys = []
        self.path_points = []
        self.path_seq = 0
        self.path_dtsum_ms = 0.0
        self.path_duration_s = 0.0
        self.path_target_duration_ms = 0.0
        self.jump_injected = False
        self.fault_hud_forced = False
        self.engine_interp_switched = False

        self.sample_seq = 0
        self.sample_dtsum_ms = 0.0
        self.sample_duration_ms = 0.0

        self._input_offset = 0
        self._pending_taps = []
        self._active_holds = []

    def init(self, peer, jobs):
        self.peer = peer
        self.jobs = jobs
        self.active_cam_job_id = ""
        self.active_sample_job_id = ""
        self.path_fault = ""
        self.saved_poses.clear()
        self.saved_pose_order.clear()
        self._input_offset = 0
        self._pending_taps.clear()
        self._active_holds.clear()

    def handles(self, verb, role):
        return role == "client" and verb in _CLIENT_VERBS

    def _pl_dir(self):
        return ypr_matrix(self.pl_cam_yaw_deg, self.pl_cam_pitch_deg, 0.0)[2]

    def _set_cam_pose(self, pos, rot, fov_rad):
        self.cam_pos = [float(pos[0]), float(pos[1]), float(pos[2])]
        self.cam_rot = [list(rot[0]), list(rot[1]), list(rot[2])]
        self.cam_fov = float(fov_rad)
        if self.cam_active:
            self.staged_eng_pos = list(self.cam_pos)
            self.staged_eng_dir = list(self.cam_rot[2])

    def _ensure_active_cam(self, pos, ypr_deg, fov_rad, fault):
        self.cam_exists = True
        self.cam_active = fault != "cam_no_activate"
        rot = ypr_matrix(ypr_deg[0], ypr_deg[1], ypr_deg[2])
        self._set_cam_pose(pos, rot, fov_rad)
        if not self.cam_active:
            self.staged_eng_pos = list(self.pl_cam_pos)
            self.staged_eng_dir = self._pl_dir()

    def _apply_cam_focus(self, dist_m, blur):
        self.sent_focus_dist_m = float(dist_m)
        self.sent_focus_blur = float(blur)
        self.set_focus_calls_n += 1

    def _destroy_cameras(self, preserve_focus=False):
        if self.cam_exists:
            if not preserve_focus:
                self._apply_cam_focus(0.0, 0.0)
                self.focus_enabled_b = 0.0
            self.cam_active = False
            self.cam_exists = False
            self.cam_pos = [0.0, 0.0, 0.0]
            self.cam_rot = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
            self.cam_fov = 0.7
            self.eng_pos = list(self.pl_cam_pos)
            self.eng_dir = self._pl_dir()
            self.staged_eng_pos = list(self.pl_cam_pos)
            self.staged_eng_dir = self._pl_dir()

    def _ovl_vis_b(self):
        if self.test_overlay_visible:
            return 1.0
        if self.hud_hidden and self.aux_vis_mask != 0:
            return 1.0
        return 0.0

    def _qb_vis_b(self):
        return 1.0 if (_elem_vis_mask(self.hud_flags_mask) & 128) else 0.0

    def _hide_hud_and_save(self):
        self.saved_hud_flags_mask = int(self.hud_flags_mask)
        self.saved_aux_vis_mask = int(self.aux_vis_mask)
        self.hud_hidden = True
        self.hud_flags_mask = (self.hud_flags_mask & ~1024) | 391
        self.aux_vis_mask = 0

    def _restore_hud_saved(self):
        self.test_overlay_visible = False
        self.hud_flags_mask = int(self.saved_hud_flags_mask)
        self.aux_vis_mask = int(self.saved_aux_vis_mask)
        self.hud_hidden = False

    def _store_pose(self, name, pos, ypr, fov_rad):
        if name not in self.saved_poses:
            self.saved_pose_order.append(name)
        self.saved_poses[name] = {
            "pos": [float(pos[0]), float(pos[1]), float(pos[2])],
            "ypr": [float(ypr[0]), float(ypr[1]), float(ypr[2])],
            "fov_rad": float(fov_rad),
        }

    def _saved_names_csv(self):
        return ",".join(self.saved_pose_order)

    def _node_snapshot(self):
        if not self.cam_exists:
            return (
                0.0,
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 0.0],
                [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            )
        ypr = matrix_to_angles(self.cam_rot)
        return (
            1.0 if self.cam_active else 0.0,
            list(self.cam_pos),
            ypr,
            [list(r) for r in self.cam_rot],
        )

    def _is_cam_job_running(self):
        return (
            self.active_cam_job_id != ""
            and self.jobs.get_state(self.active_cam_job_id) == "running"
        )

    def on_start_op(self, op, args_unpacked, raw_args):
        verb = op["verb"]
        fault = op.get("qa_fault", "")
        if fault == "cam_no_player":
            return ("rejected", "client_not_in_game", wire.empty_payload())
        if verb == "scam_state_read":
            return self._op_state_read()
        if verb == "scam_fixture_setup":
            return self._op_fixture_setup(args_unpacked, fault)
        if verb == "scam_free_op":
            return self._op_free_op(args_unpacked, fault)
        if verb == "scam_pose_save":
            return self._op_pose_save(args_unpacked)
        if verb == "scam_pose_apply":
            return self._op_pose_apply(args_unpacked, fault)
        if verb == "scam_path_start":
            return self._op_path_start(op, args_unpacked, raw_args, fault)
        if verb == "scam_dof_set":
            return self._op_dof_set(args_unpacked, fault)
        if verb == "scam_hud_op":
            return self._op_hud_op(args_unpacked)
        if verb == "scam_sample_start":
            return self._op_sample_start(op, args_unpacked)
        return ("rejected", "unknown_verb", wire.empty_payload())

    def _op_fixture_setup(self, args_unpacked, fault):
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        nums = args_unpacked["num"]
        req = (
            "anchor_x_m",
            "anchor_z_m",
            "anchor_eye_h_m",
            "anchor_yaw_deg",
            "anchor_pitch_deg",
            "anchor_roll_deg",
            "anchor_fov_rad",
            "subj_dist_m",
            "bg_dist_m",
        )
        for k in req:
            if k not in nums or not _is_finite(nums[k]):
                return ("rejected", "bad_args", wire.empty_payload())
        ax = float(nums["anchor_x_m"])
        az = float(nums["anchor_z_m"])
        eyeh = float(nums["anchor_eye_h_m"])
        ayaw = float(nums["anchor_yaw_deg"])
        apitch = float(nums["anchor_pitch_deg"])
        aroll = float(nums["anchor_roll_deg"])
        afov = float(nums["anchor_fov_rad"])
        sdist = float(nums["subj_dist_m"])
        bdist = float(nums["bg_dist_m"])
        if (
            afov < 0.1
            or afov > 2.8
            or apitch < -89.0
            or apitch > 89.0
            or aroll < -180.0
            or aroll > 180.0
            or sdist <= 0.0
            or bdist <= 0.0
        ):
            return ("rejected", "bad_args", wire.empty_payload())
        if self.player_in_veh_b != 0.0:
            return ("rejected", "player_in_vehicle", wire.empty_payload())

        ay = _surface_y(ax, az) + eyeh
        self.pl_cam_pos = [ax, _surface_y(ax, az - 4.0) + 1.6, az - 4.0]
        self.pl_cam_yaw_deg = 0.0
        self.pl_cam_pitch_deg = 0.0
        if self.qb_items_n <= 0:
            self.qb_items_n = 1
        self._ensure_active_cam([ax, ay, az], [ayaw, apitch, aroll], afov, fault)
        self._apply_cam_focus(0.0, 0.0)
        self.focus_enabled_b = 0.0
        self.free_cam_active = False
        self.free_pos = [ax, ay, az]
        self.free_yaw_deg = ayaw
        self.free_pitch_deg = apitch
        self.free_roll_deg = aroll
        self.free_fov_rad = afov
        self.test_overlay_visible = False
        if self.cam_active:
            self.eng_pos = list(self.cam_pos)
            self.eng_dir = list(self.cam_rot[2])

        payload = wire.pack_payload(
            scalars_num={
                "frame": float(self.peer.frame),
                "tick_ms": self.peer.local_ms(),
                "active_b": 1.0 if self.cam_active else 0.0,
                "anchor_x_m": ax,
                "anchor_y_m": ay,
                "anchor_z_m": az,
                "subj_present_b": 1.0,
                "subj_dist_m": sdist,
                "bg_present_b": 1.0,
                "bg_dist_m": bdist,
                "qb_items_n": float(self.qb_items_n),
                "player_in_veh_b": 0.0,
            }
        )
        return ("done", "", payload)

    def _op_state_read(self):
        active_b, pos, ypr, rot = self._node_snapshot()
        cam_state = self.jobs.get_state(self.active_cam_job_id) if self.active_cam_job_id else ""
        sample_state = (
            self.jobs.get_state(self.active_sample_job_id) if self.active_sample_job_id else ""
        )
        payload = wire.pack_payload(
            scalars_str={
                "cam_job_id": self.active_cam_job_id,
                "cam_job_state": cam_state,
                "sample_job_id": self.active_sample_job_id,
                "sample_job_state": sample_state,
                "saved_names_csv": self._saved_names_csv(),
            },
            scalars_num={
                "frame": float(self.peer.frame),
                "tick_ms": self.peer.local_ms(),
                "cam_dtsum_ms": self.path_dtsum_ms,
                "active_b": active_b,
                "enable_b": self.focus_enabled_b,
                "sent_focus_dist_m": self.sent_focus_dist_m,
                "sent_focus_blur": self.sent_focus_blur,
                "set_focus_calls_n": float(self.set_focus_calls_n),
                "saved_count_n": float(len(self.saved_poses)),
                "speed_mps": self.free_speed_mps,
                "speed_steps_n": float(self.speed_steps_n),
                "input_frames_n": float(self.free_input_frames),
                "integrated_dt_s": self.free_integrated_dt_s,
                "input_ack_seq_n": float(self.input_ack_seq_n),
                "x_m": pos[0],
                "y_m": pos[1],
                "z_m": pos[2],
                "yaw_deg": ypr[0],
                "pitch_deg": ypr[1],
                "roll_deg": ypr[2],
                "fov_rad": self.cam_fov,
                "m00": rot[0][0],
                "m01": rot[0][1],
                "m02": rot[0][2],
                "m10": rot[1][0],
                "m11": rot[1][1],
                "m12": rot[1][2],
                "m20": rot[2][0],
                "m21": rot[2][1],
                "m22": rot[2][2],
                "eng_x_m": self.eng_pos[0],
                "eng_y_m": self.eng_pos[1],
                "eng_z_m": self.eng_pos[2],
                "eng_dx": self.eng_dir[0],
                "eng_dy": self.eng_dir[1],
                "eng_dz": self.eng_dir[2],
                "elem_vis_mask": float(_elem_vis_mask(self.hud_flags_mask)),
                "flags_mask": float(self.hud_flags_mask),
                "saved_flags_mask": float(self.saved_hud_flags_mask),
                "aux_vis_mask": float(self.aux_vis_mask),
                "saved_aux_vis_mask": float(self.saved_aux_vis_mask),
                "qb_vis_b": self._qb_vis_b(),
                "qb_items_n": float(self.qb_items_n),
                "menu_open_b": self.menu_open_b,
                "ovl_vis_b": self._ovl_vis_b(),
            },
        )
        return ("done", "", payload)

    def _op_free_op(self, args_unpacked, fault):
        nums = args_unpacked["num"]
        if "op_code" not in nums or not _is_int_num(nums["op_code"]):
            return ("rejected", "bad_args", wire.empty_payload())
        op_code = int(nums["op_code"])
        if op_code not in (1, 3):
            return ("rejected", "bad_args", wire.empty_payload())
        if op_code == 1:
            if not self.peer.lease_valid():
                return ("error", "lease_expired", wire.empty_payload())
            req = (
                "x_m",
                "y_m",
                "z_m",
                "yaw_deg",
                "pitch_deg",
                "roll_deg",
                "fov_rad",
                "speed_mps",
                "ang_speed_degps",
            )
            for k in req:
                if k not in nums or not _is_finite(nums[k]):
                    return ("rejected", "bad_args", wire.empty_payload())
            xm = float(nums["x_m"])
            ym = float(nums["y_m"])
            zm = float(nums["z_m"])
            yaw = float(nums["yaw_deg"])
            pitch = float(nums["pitch_deg"])
            roll = float(nums["roll_deg"])
            fov = float(nums["fov_rad"])
            spd = float(nums["speed_mps"])
            aspd = float(nums["ang_speed_degps"])
            if (
                fov < 0.1
                or fov > 2.8
                or spd <= 0.0
                or spd > 100.0
                or aspd <= 0.0
                or pitch < -89.0
                or pitch > 89.0
                or roll < -180.0
                or roll > 180.0
            ):
                return ("rejected", "bad_args", wire.empty_payload())
            if self._is_cam_job_running():
                return ("rejected", "busy", wire.empty_payload())
            self.control_disabled = True
            self._ensure_active_cam([xm, ym, zm], [yaw, pitch, roll], fov, fault)
            if self.cam_active:
                self.eng_pos = list(self.cam_pos)
                self.eng_dir = list(self.cam_rot[2])
            self._apply_cam_focus(0.0, 0.0)
            self.focus_enabled_b = 0.0
            self.free_cam_active = True
            self.free_pos = [xm, ym, zm]
            self.free_yaw_deg = yaw
            self.free_pitch_deg = pitch
            self.free_roll_deg = roll
            self.free_fov_rad = fov
            self.free_speed_mps = spd
            self.free_ang_speed_degps = aspd
            self.free_input_frames = 0
            self.free_integrated_dt_s = 0.0
            self.speed_steps_n = 0
        else:
            self.free_cam_active = False
            self._destroy_cameras(preserve_focus=False)
            self.control_disabled = False
            self.slow_stop_pending = False
            self.slow_stop_remaining_ms = 0.0

        active_b, pos, ypr, _ = self._node_snapshot()
        payload = wire.pack_payload(
            scalars_num={
                "frame": float(self.peer.frame),
                "tick_ms": self.peer.local_ms(),
                "active_b": active_b,
                "x_m": pos[0],
                "y_m": pos[1],
                "z_m": pos[2],
                "yaw_deg": ypr[0],
                "pitch_deg": ypr[1],
                "roll_deg": ypr[2],
                "fov_rad": self.cam_fov,
                "speed_mps": self.free_speed_mps,
                "speed_steps_n": float(self.speed_steps_n),
                "eng_x_m": self.eng_pos[0],
                "eng_y_m": self.eng_pos[1],
                "eng_z_m": self.eng_pos[2],
                "eng_dx": self.eng_dir[0],
                "eng_dy": self.eng_dir[1],
                "eng_dz": self.eng_dir[2],
                "input_frames_n": float(self.free_input_frames),
                "integrated_dt_s": self.free_integrated_dt_s,
                "input_ack_seq_n": float(self.input_ack_seq_n),
            }
        )
        return ("done", "", payload)

    def _op_pose_save(self, args_unpacked):
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        strs = args_unpacked["str"]
        name = str(strs.get("name", ""))
        overwrite = str(strs.get("overwrite", "0"))
        if name == "":
            return ("rejected", "empty_name", wire.empty_payload())
        if overwrite not in ("0", "1"):
            return ("rejected", "bad_args", wire.empty_payload())
        if name in self.saved_poses and overwrite != "1":
            return ("rejected", "duplicate_name", wire.empty_payload())
        if not self.cam_exists or not self.cam_active:
            return ("rejected", "no_active_cam", wire.empty_payload())
        _, pos, ypr, _ = self._node_snapshot()
        self._store_pose(name, pos, ypr, self.cam_fov)
        payload = wire.pack_payload(
            scalars_str={
                "name": name,
                "saved_names_csv": self._saved_names_csv(),
            },
            scalars_num={
                "frame": float(self.peer.frame),
                "tick_ms": self.peer.local_ms(),
                "saved_count_n": float(len(self.saved_poses)),
                "x_m": pos[0],
                "y_m": pos[1],
                "z_m": pos[2],
                "yaw_deg": ypr[0],
                "pitch_deg": ypr[1],
                "roll_deg": ypr[2],
                "fov_rad": self.cam_fov,
            },
        )
        return ("done", "", payload)

    def _op_pose_apply(self, args_unpacked, fault):
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        strs = args_unpacked["str"]
        nums = args_unpacked["num"]
        name = str(strs.get("name", ""))
        if name != "":
            if not self.cam_exists or (not self.cam_active and fault != "cam_no_activate"):
                return ("rejected", "no_active_cam", wire.empty_payload())
            if name not in self.saved_poses:
                return ("rejected", "unknown_pose", wire.empty_payload())
            saved = self.saved_poses[name]
            pos = list(saved["pos"])
            ypr = list(saved["ypr"])
            fov = float(saved["fov_rad"])
        else:
            req = ("x_m", "y_m", "z_m", "yaw_deg", "pitch_deg", "roll_deg", "fov_rad")
            for k in req:
                if k not in nums or not _is_finite(nums[k]):
                    return ("rejected", "bad_args", wire.empty_payload())
            xm = float(nums["x_m"])
            ym = float(nums["y_m"])
            zm = float(nums["z_m"])
            yaw = float(nums["yaw_deg"])
            pitch = float(nums["pitch_deg"])
            roll = float(nums["roll_deg"])
            fov = float(nums["fov_rad"])
            if (
                fov < 0.1
                or fov > 2.8
                or pitch < -89.0
                or pitch > 89.0
                or roll < -180.0
                or roll > 180.0
            ):
                return ("rejected", "bad_args", wire.empty_payload())
            if not self.cam_exists or (not self.cam_active and fault != "cam_no_activate"):
                return ("rejected", "no_active_cam", wire.empty_payload())
            pos = [xm, ym, zm]
            ypr = [yaw, pitch, roll]

        if fault == "cam_no_activate":
            self.cam_active = False
            self.eng_pos = list(self.pl_cam_pos)
            self.eng_dir = self._pl_dir()
            self.staged_eng_pos = list(self.pl_cam_pos)
            self.staged_eng_dir = self._pl_dir()
        if fault == "cam_swap_axes":
            ypr[0], ypr[1] = ypr[1], ypr[0]

        rot = ypr_matrix(ypr[0], ypr[1], ypr[2])
        self._set_cam_pose(pos, rot, fov)
        if self.free_cam_active:
            self.free_pos = list(pos)
            self.free_yaw_deg = float(ypr[0])
            self.free_pitch_deg = float(ypr[1])
            self.free_roll_deg = float(ypr[2])
            self.free_fov_rad = float(fov)

        active_b, out_pos, out_ypr, out_rot = self._node_snapshot()
        payload = wire.pack_payload(
            scalars_str={"name": name},
            scalars_num={
                "frame": float(self.peer.frame),
                "tick_ms": self.peer.local_ms(),
                "active_b": active_b,
                "x_m": out_pos[0],
                "y_m": out_pos[1],
                "z_m": out_pos[2],
                "yaw_deg": out_ypr[0],
                "pitch_deg": out_ypr[1],
                "roll_deg": out_ypr[2],
                "fov_rad": self.cam_fov,
                "m00": out_rot[0][0],
                "m01": out_rot[0][1],
                "m02": out_rot[0][2],
                "m10": out_rot[1][0],
                "m11": out_rot[1][1],
                "m12": out_rot[1][2],
                "m20": out_rot[2][0],
                "m21": out_rot[2][1],
                "m22": out_rot[2][2],
                "eng_x_m": self.eng_pos[0],
                "eng_y_m": self.eng_pos[1],
                "eng_z_m": self.eng_pos[2],
                "eng_dx": self.eng_dir[0],
                "eng_dy": self.eng_dir[1],
                "eng_dz": self.eng_dir[2],
            },
        )
        return ("done", "", payload)

    def _op_dof_set(self, args_unpacked, fault):
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        nums = args_unpacked["num"]
        for k in ("enable_b", "focus_dist_m", "focus_blur"):
            if k not in nums or not _is_finite(nums[k]):
                return ("rejected", "bad_args", wire.empty_payload())
        en = float(nums["enable_b"])
        fdist = float(nums["focus_dist_m"])
        fblur = float(nums["focus_blur"])
        if en not in (0.0, 1.0):
            return ("rejected", "bad_args", wire.empty_payload())
        if en == 1.0 and (fdist <= 0.0 or fblur < 0.0 or fblur > 1.0):
            return ("rejected", "bad_args", wire.empty_payload())
        if en == 0.0 and (fdist < 0.0 or fblur < 0.0 or fblur > 1.0):
            return ("rejected", "bad_args", wire.empty_payload())
        if not self.cam_exists or not self.cam_active:
            return ("rejected", "no_active_cam", wire.empty_payload())
        if en == 0.0 or fault == "cam_dof_off":
            self._apply_cam_focus(0.0, 0.0)
            self.focus_enabled_b = 1.0 if en == 1.0 else 0.0
        else:
            self._apply_cam_focus(fdist, fblur)
            self.focus_enabled_b = 1.0

        active_b, out_pos, out_ypr, _ = self._node_snapshot()
        payload = wire.pack_payload(
            scalars_num={
                "frame": float(self.peer.frame),
                "tick_ms": self.peer.local_ms(),
                "active_b": active_b,
                "enable_b": self.focus_enabled_b,
                "sent_focus_dist_m": self.sent_focus_dist_m,
                "sent_focus_blur": self.sent_focus_blur,
                "set_focus_calls_n": float(self.set_focus_calls_n),
                "x_m": out_pos[0],
                "y_m": out_pos[1],
                "z_m": out_pos[2],
                "yaw_deg": out_ypr[0],
                "pitch_deg": out_ypr[1],
                "roll_deg": out_ypr[2],
                "fov_rad": self.cam_fov,
            }
        )
        return ("done", "", payload)

    def _op_hud_op(self, args_unpacked):
        nums = args_unpacked["num"]
        if "op_code" not in nums or not _is_int_num(nums["op_code"]):
            return ("rejected", "bad_args", wire.empty_payload())
        op_code = int(nums["op_code"])
        if op_code not in (0, 1, 2, 4, 5):
            return ("rejected", "bad_args", wire.empty_payload())
        if op_code == 1:
            if not self.peer.lease_valid():
                return ("error", "lease_expired", wire.empty_payload())
            self._hide_hud_and_save()
        elif op_code == 2:
            self._restore_hud_saved()
        elif op_code == 4:
            if "mode" not in nums or not _is_int_num(nums["mode"]):
                return ("rejected", "bad_args", wire.empty_payload())
            mode = int(nums["mode"])
            if mode not in (0, 1, 2):
                return ("rejected", "bad_args", wire.empty_payload())
            if mode == 0:
                self._restore_hud_saved()
            else:
                if not self.peer.lease_valid():
                    return ("error", "lease_expired", wire.empty_payload())
                if mode == 1:
                    self.hud_flags_mask &= ~(128 | 256 | 512)
                else:
                    self.test_overlay_visible = True
        elif op_code == 5:
            if not self.peer.lease_valid():
                return ("error", "lease_expired", wire.empty_payload())
            if "preset_mask" not in nums or not _is_int_num(nums["preset_mask"]):
                return ("rejected", "bad_args", wire.empty_payload())
            pmask = int(nums["preset_mask"])
            if pmask < 0 or pmask > 4095:
                return ("rejected", "bad_args", wire.empty_payload())
            self.test_overlay_visible = False
            self.hud_flags_mask = pmask
            if pmask > 0:
                self.aux_vis_mask |= 34
            self.saved_hud_flags_mask = pmask
            self.saved_aux_vis_mask = int(self.aux_vis_mask)
            self.hud_hidden = False

        payload = wire.pack_payload(
            scalars_num={
                "frame": float(self.peer.frame),
                "tick_ms": self.peer.local_ms(),
                "elem_vis_mask": float(_elem_vis_mask(self.hud_flags_mask)),
                "flags_mask": float(self.hud_flags_mask),
                "saved_flags_mask": float(self.saved_hud_flags_mask),
                "aux_vis_mask": float(self.aux_vis_mask),
                "saved_aux_vis_mask": float(self.saved_aux_vis_mask),
                "qb_vis_b": self._qb_vis_b(),
                "qb_items_n": float(self.qb_items_n),
                "menu_open_b": self.menu_open_b,
                "ovl_vis_b": self._ovl_vis_b(),
                "player_in_veh_b": self.player_in_veh_b,
            }
        )
        return ("done", "", payload)

    def _emit_path_row(self, job_id, seq_n, dtsum_ms, calc_focus_dist):
        active_b, pos, ypr, rot = self._node_snapshot()
        row = [
            float(seq_n),
            float(self.peer.frame),
            self.peer.local_ms(),
            float(dtsum_ms),
            pos[0],
            pos[1],
            pos[2],
            ypr[0],
            ypr[1],
            ypr[2],
            self.eng_pos[0],
            self.eng_pos[1],
            self.eng_pos[2],
            self.eng_dir[0],
            self.eng_dir[1],
            self.eng_dir[2],
            self.cam_fov,
            float(calc_focus_dist),
            self.sent_focus_dist_m,
            self.sent_focus_blur,
            float(self.set_focus_calls_n),
            active_b,
            float(_elem_vis_mask(self.hud_flags_mask)),
            float(self.hud_flags_mask),
            self._qb_vis_b(),
            self.menu_open_b,
            self._ovl_vis_b(),
            rot[0][0],
            rot[0][1],
            rot[0][2],
            rot[1][0],
            rot[1][1],
            rot[1][2],
            rot[2][0],
            rot[2][1],
            rot[2][2],
        ]
        self.jobs.append_row(job_id, row, [])

    def _op_path_start(self, op, args_unpacked, raw_args, fault):
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        strs = args_unpacked["str"]
        pos_mode = str(strs.get("pos_mode", ""))
        interp_mode = str(strs.get("interp_mode", ""))
        hide_hud = str(strs.get("hide_hud", ""))
        if (
            pos_mode not in ("linear", "catmull_rom")
            or interp_mode not in ("scripted", "engine_interp")
            or hide_hud not in ("0", "1")
        ):
            return ("rejected", "bad_args", wire.empty_payload())
        rows = args_unpacked["rows"]
        req_cols = (
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
        )
        if len(rows) < 2:
            return ("rejected", "bad_args", wire.empty_payload())
        parsed = []
        prev_t = -1.0
        for idx, rdict in enumerate(rows):
            for col in req_cols:
                if col not in rdict or not _is_finite(rdict[col]):
                    return ("rejected", "bad_args", wire.empty_payload())
            ts = float(rdict["t_s"])
            xm = float(rdict["x_m"])
            ym = float(rdict["y_m"])
            zm = float(rdict["z_m"])
            yaw = float(rdict["yaw_deg"])
            pitch = float(rdict["pitch_deg"])
            roll = float(rdict["roll_deg"])
            fov = float(rdict["fov_rad"])
            fdist = float(rdict["focus_dist_m"])
            fblur = float(rdict["focus_blur"])
            if idx == 0 and ts != 0.0:
                return ("rejected", "bad_args", wire.empty_payload())
            if idx > 0 and ts <= prev_t:
                return ("rejected", "bad_args", wire.empty_payload())
            if (
                fov < 0.1
                or fov > 2.8
                or pitch < -89.0
                or pitch > 89.0
                or roll < -180.0
                or roll > 180.0
                or fdist < 0.0
                or fblur < 0.0
                or fblur > 1.0
                or (fblur > 0.0 and fdist <= 0.0)
            ):
                return ("rejected", "bad_args", wire.empty_payload())
            rot = ypr_matrix(yaw, pitch, roll)
            parsed.append(
                {
                    "t_s": ts,
                    "pos": [xm, ym, zm],
                    "ypr": [yaw, pitch, roll],
                    "fov_rad": fov,
                    "focus_dist_m": fdist,
                    "focus_blur": fblur,
                    "q": matrix_to_quat(rot),
                }
            )
            prev_t = ts
        if prev_t <= 0.0:
            return ("rejected", "bad_args", wire.empty_payload())

        op_id = op["op_id"]
        err = self.jobs.start_job(
            self,
            op_id,
            "cam",
            PATH_NCOL,
            [],
            3,
            4096,
            900000.0,
            "stop",
        )
        if err != "":
            return ("rejected", err, wire.empty_payload())

        self.path_keys = parsed
        self.path_points = [k["pos"] for k in parsed]
        self.path_fault = fault
        self.path_pos_mode = pos_mode
        self.path_interp_mode = interp_mode
        self.free_cam_active = False
        self.slow_stop_pending = False
        self.slow_stop_remaining_ms = 0.0
        self.active_cam_job_id = op_id
        self.path_seq = 0
        self.path_dtsum_ms = 0.0
        self.path_duration_s = prev_t
        if fault == "cam_late_finish":
            self.path_target_duration_ms = (self.path_duration_s + 1.0) * 1000.0
        else:
            self.path_target_duration_ms = self.path_duration_s * 1000.0
        self.jump_injected = False
        self.fault_hud_forced = False
        self.engine_interp_switched = False

        k0 = parsed[0]
        self._ensure_active_cam(k0["pos"], k0["ypr"], k0["fov_rad"], "")
        self.eng_pos = list(self.cam_pos)
        self.eng_dir = list(self.cam_rot[2])
        self.control_disabled = True
        if hide_hud == "1":
            self._hide_hud_and_save()
            self.hud_hidden_by_job = True
        else:
            self.hud_hidden_by_job = False
        self._apply_cam_focus(k0["focus_dist_m"], k0["focus_blur"])
        self.focus_enabled_b = (
            1.0 if (k0["focus_blur"] > 0.0 or k0["focus_dist_m"] > 0.0) else 0.0
        )
        self._emit_path_row(op_id, 0, 0.0, k0["focus_dist_m"])
        return ("done", "", self.jobs.fill_start_read(op_id, "cam"))

    def _emit_sample_row(self, job_id, seq_n, dtsum_ms):
        pl_dir = self._pl_dir()
        row = [
            float(seq_n),
            float(self.peer.frame),
            self.peer.local_ms(),
            float(dtsum_ms),
            self.eng_pos[0],
            self.eng_pos[1],
            self.eng_pos[2],
            self.eng_dir[0],
            self.eng_dir[1],
            self.eng_dir[2],
            self.cam_fov,
            self.pl_cam_pos[0],
            self.pl_cam_pos[1],
            self.pl_cam_pos[2],
            pl_dir[0],
            pl_dir[1],
            pl_dir[2],
            1.0 if self.cam_active else 0.0,
        ]
        self.jobs.append_row(job_id, row, [])

    def _op_sample_start(self, op, args_unpacked):
        if not self.peer.lease_valid():
            return ("error", "lease_expired", wire.empty_payload())
        nums = args_unpacked["num"]
        if "duration_ms" not in nums or not _is_finite(nums["duration_ms"]):
            return ("rejected", "bad_args", wire.empty_payload())
        dur_ms = float(nums["duration_ms"])
        if dur_ms < 200.0 or dur_ms > 10000.0:
            return ("rejected", "bad_args", wire.empty_payload())
        op_id = op["op_id"]
        err = self.jobs.start_job(
            self,
            op_id,
            "cam_sample",
            SAMPLE_NCOL,
            [],
            5,
            4096,
            900000.0,
            "stop",
        )
        if err != "":
            return ("rejected", err, wire.empty_payload())
        self.active_sample_job_id = op_id
        self.sample_seq = 0
        self.sample_dtsum_ms = 0.0
        self.sample_duration_ms = dur_ms
        self._emit_sample_row(op_id, 0, 0.0)
        return ("done", "", self.jobs.fill_start_read(op_id, "cam_sample"))

    def _poll_os_input(self):
        cfg = getattr(self.peer, "config", None)
        if not cfg:
            return
        in_path = Path(cfg).with_name("scam_os_input.jsonl")
        if not in_path.is_file():
            return
        try:
            raw = in_path.read_bytes()
        except OSError:
            return
        if len(raw) < self._input_offset:
            self._input_offset = 0
        chunk = raw[self._input_offset :]
        if not chunk:
            return
        nl_idx = chunk.rfind(b"\n")
        if nl_idx == -1:
            return
        complete = chunk[: nl_idx + 1]
        self._input_offset += nl_idx + 1
        for line in complete.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            seq_n = int(ev.get("seq_n", 0))
            if seq_n > self.input_ack_seq_n:
                self.input_ack_seq_n = seq_n
            kind = str(ev.get("kind", ""))
            if kind == "key_tap":
                for k in ev.get("keys", []):
                    self._pending_taps.append(str(k))
            elif kind == "key_hold":
                dur_s = max(0.0, float(ev.get("duration_ms", 0.0)) / 1000.0)
                if dur_s > 0.0:
                    self._active_holds.append(
                        {"keys": [str(k) for k in ev.get("keys", [])], "rem_s": dur_s}
                    )
            elif kind == "mouse_move":
                if not self.control_disabled and not self.cam_active:
                    dx = float(ev.get("dx_px", 0.0))
                    self.pl_cam_yaw_deg = _wrap_deg(self.pl_cam_yaw_deg + dx * 0.12)
                    self.eng_dir = self._pl_dir()

    def _tick_free_cam(self, timeslice_s):
        if (
            not self.free_cam_active
            or not self.cam_active
            or self.active_cam_job_id != ""
            or not self.peer.lease_valid()
        ):
            self._pending_taps.clear()
            return
        while self._pending_taps:
            tk = self._pending_taps.pop(0)
            if tk == "KC_PRIOR":
                self.free_speed_mps = _clamp(self.free_speed_mps * 2.0, 0.5, 100.0)
                self.speed_steps_n += 1
            elif tk == "KC_NEXT":
                self.free_speed_mps = _clamp(self.free_speed_mps * 0.5, 0.5, 100.0)
                self.speed_steps_n += 1
            elif tk == "KC_F":
                _, qp, qypr, _ = self._node_snapshot()
                self._store_pose("quick_pose", qp, qypr, self.cam_fov)

        if not self._active_holds:
            return
        hold = self._active_holds[0]
        step_dt = min(float(timeslice_s), float(hold["rem_s"]))
        keys = set(hold["keys"])
        hold["rem_s"] = max(0.0, float(hold["rem_s"]) - step_dt)
        if hold["rem_s"] <= 1e-9:
            self._active_holds.pop(0)
        fwd = (1.0 if "KC_W" in keys else 0.0) - (1.0 if "KC_S" in keys else 0.0)
        strafe = (1.0 if "KC_D" in keys else 0.0) - (1.0 if "KC_A" in keys else 0.0)
        up_ax = (1.0 if "KC_E" in keys else 0.0) - (1.0 if "KC_Q" in keys else 0.0)
        dyaw = (1.0 if "KC_RIGHT" in keys else 0.0) - (1.0 if "KC_LEFT" in keys else 0.0)
        dpitch = (1.0 if "KC_UP" in keys else 0.0) - (1.0 if "KC_DOWN" in keys else 0.0)
        if step_dt > 0.0 and (fwd or strafe or up_ax or dyaw or dpitch):
            self.free_yaw_deg = _wrap_deg(
                self.free_yaw_deg + dyaw * self.free_ang_speed_degps * step_dt
            )
            self.free_pitch_deg = _clamp(
                self.free_pitch_deg + dpitch * self.free_ang_speed_degps * step_dt,
                -89.0,
                89.0,
            )
            rot = ypr_matrix(self.free_yaw_deg, self.free_pitch_deg, self.free_roll_deg)
            scale = self.free_speed_mps * step_dt
            for i in range(3):
                up_c = 1.0 if i == 1 else 0.0
                self.free_pos[i] += (fwd * rot[2][i] + strafe * rot[0][i] + up_ax * up_c) * scale
            self._set_cam_pose(self.free_pos, rot, self.free_fov_rad)
            self.free_input_frames += 1
            self.free_integrated_dt_s += step_dt

    def _tick_path_job(self, timeslice_s):
        jid = self.active_cam_job_id
        if not jid:
            return
        if self.jobs.get_state(jid) != "running":
            self.active_cam_job_id = ""
            return
        if self.jobs.is_deadman_tripped(jid):
            self.jobs.end_job(jid, "failed", "lease_expired")
            return
        self.path_seq += 1
        self.path_dtsum_ms += float(timeslice_s) * 1000.0
        reached_end = self.path_dtsum_ms >= self.path_target_duration_ms
        t = self.path_duration_s if reached_end else min(self.path_dtsum_ms / 1000.0, self.path_duration_s)
        nkeys = len(self.path_keys)
        seg = 0
        while seg < nkeys - 2 and t > self.path_keys[seg + 1]["t_s"]:
            seg += 1
        ka = self.path_keys[seg]
        kb = self.path_keys[seg + 1]
        span = kb["t_s"] - ka["t_s"]
        u = 1.0 if reached_end else _clamp((t - ka["t_s"]) / span if span > 1e-6 else 1.0, 0.0, 1.0)
        calc_fdist = _lerp(ka["focus_dist_m"], kb["focus_dist_m"], u)
        calc_fblur = _lerp(ka["focus_blur"], kb["focus_blur"], u)

        if self.path_interp_mode == "scripted":
            if self.path_pos_mode == "catmull_rom":
                pos = catmull_rom_pos(self.path_points, t / self.path_duration_s)
            else:
                pos = [_lerp(ka["pos"][i], kb["pos"][i], u) for i in range(3)]
            if self.path_fault == "cam_path_jump" and not self.jump_injected and t >= 3.0:
                pos[0] += 2.0
                self.jump_injected = True
            if self.path_fault == "cam_long_arc":
                ypr = [_lerp(ka["ypr"][i], kb["ypr"][i], u) for i in range(3)]
                rot = ypr_matrix(ypr[0], ypr[1], ypr[2])
            else:
                qout = slerp_quat(ka["q"], kb["q"], u)
                rot = quat_to_matrix(qout)
            fov = self.cam_fov if self.path_fault == "cam_frozen_fov" else _lerp(ka["fov_rad"], kb["fov_rad"], u)
            self._set_cam_pose(pos, rot, fov)
            if self.path_fault != "cam_ignore_focus_keys":
                self._apply_cam_focus(calc_fdist, calc_fblur)
        else:
            pos = [_lerp(ka["pos"][i], kb["pos"][i], u) for i in range(3)]
            qout = slerp_quat(ka["q"], kb["q"], u)
            rot = quat_to_matrix(qout)
            fov = _lerp(ka["fov_rad"], kb["fov_rad"], u)
            self._set_cam_pose(pos, rot, fov)
            if not self.engine_interp_switched and nkeys >= 3 and t >= self.path_keys[1]["t_s"]:
                self.engine_interp_switched = True
                k2 = self.path_keys[2]
                self._apply_cam_focus(k2["focus_dist_m"], k2["focus_blur"])

        if self.path_fault == "cam_force_quickbar" and self.path_dtsum_ms >= 1800.0 and not self.fault_hud_forced:
            self.fault_hud_forced = True
            self.hud_flags_mask &= ~(128 | 256 | 512)
            self.test_overlay_visible = True

        self._emit_path_row(jid, self.path_seq, self.path_dtsum_ms, calc_fdist)
        if reached_end:
            self.jobs.end_job(jid, "done", "")

    def _tick_sample_job(self, timeslice_s):
        jid = self.active_sample_job_id
        if not jid:
            return
        if self.jobs.get_state(jid) != "running":
            self.active_sample_job_id = ""
            return
        if self.jobs.is_deadman_tripped(jid):
            self.jobs.end_job(jid, "failed", "lease_expired")
            return
        self.sample_seq += 1
        self.sample_dtsum_ms += float(timeslice_s) * 1000.0
        self._emit_sample_row(jid, self.sample_seq, self.sample_dtsum_ms)
        if self.sample_dtsum_ms >= self.sample_duration_ms:
            self.jobs.end_job(jid, "done", "")

    def on_tick(self, timeslice_s):
        if self.cam_active:
            self.eng_pos = list(self.staged_eng_pos)
            self.eng_dir = list(self.staged_eng_dir)
        else:
            self.eng_pos = list(self.pl_cam_pos)
            self.eng_dir = self._pl_dir()

        if self.slow_stop_pending:
            self.slow_stop_remaining_ms -= float(timeslice_s) * 1000.0
            if self.slow_stop_remaining_ms <= 0.0:
                self.slow_stop_pending = False
                self.slow_stop_remaining_ms = 0.0
                self.control_disabled = False

        self._poll_os_input()
        self._tick_free_cam(timeslice_s)
        self._tick_path_job(timeslice_s)
        self._tick_sample_job(timeslice_s)

    def on_job_end(self, job_id, state, reason):
        if job_id == self.active_cam_job_id:
            pfault = self.path_fault
            hud_by_job = self.hud_hidden_by_job
            self.active_cam_job_id = ""
            self.path_fault = ""
            self.hud_hidden_by_job = False
            self._destroy_cameras(preserve_focus=(pfault == "cam_ignore_focus_keys"))
            if hud_by_job:
                if pfault == "cam_restore_showhud":
                    self.test_overlay_visible = False
                    self.hud_flags_mask &= ~(1 | 2)
                    self.hud_hidden = False
                else:
                    self._restore_hud_saved()
            if pfault == "cam_slow_stop":
                self.slow_stop_pending = True
                self.slow_stop_remaining_ms = 1500.0
            else:
                self.slow_stop_pending = False
                self.slow_stop_remaining_ms = 0.0
                self.control_disabled = False
        if job_id == self.active_sample_job_id:
            self.active_sample_job_id = ""

    def on_shutdown(self):
        self.free_cam_active = False
        self.slow_stop_pending = False
        self.slow_stop_remaining_ms = 0.0
        self.active_cam_job_id = ""
        self.active_sample_job_id = ""
        self.path_fault = ""
        self.hud_hidden_by_job = False
        self._destroy_cameras(preserve_focus=False)
        self._restore_hud_saved()
        self.control_disabled = False


def create_ext(peer, jobs):
    return CamFakeExt()
