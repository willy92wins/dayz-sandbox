"""Runner de S-persist (brief F0.3-0 §5.1, §6). Offline ejecuta peers falsos en proceso
con reloj acelerado para acreditar los 10 min sin esperar 10 min reales; diag/retail usan
las mismas ordenes contra la sonda real."""

import hashlib
import json
import math
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import f03_common
import fake_peer
import gate_core
import s_persist_eval
import s_persist_mutants
import wire
from bridge_qa import QABridge

SPIKE_ID = "S-persist"
QA_DIR = Path(__file__).resolve().parent
REPO_ROOT = QA_DIR.parent.parent
FIXTURE_PATH = QA_DIR / "fixtures" / "s_persist_fixture.json"

CENSUS_STAGES = (
    "t0_baseline_census",
    "t1_pre_transition_census",
    "t1_post_transition_census",
    "t2_census_10min",
    "t3_pre_reset_census",
    "t3_post_reset_census",
    "t5_post_restart_census",
    "t5_witness_pre_census",
    "t5_witness_post_census",
    "t6_post_cleanup_census",
)

IN_SCOL = ["logical_id", "parent_id", "cat", "class_name", "slot_name"]
IN_NCOL = ["req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"]

CREATURE_CATS = ("infected", "animal")


def _fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _planned_parts(part_arg):
    all_parts = ["run"] + [f"mut-{name}" for name in s_persist_mutants.EXPECTED_MUTANTS]
    if part_arg == "all":
        return all_parts
    if part_arg not in all_parts:
        raise ValueError(f"unknown part {part_arg!r} for {SPIKE_ID}")
    return [part_arg]


def _part_layout(part_name, fixture):
    uses_mut = part_name == "mut-foreign_wiped"
    has_d = part_name == "mut-unprotected_leak"
    ret_scene = "scene_a_mut" if uses_mut else "scene_a"
    ret_area = "area_a_mut" if uses_mut else "area_a"
    ret_pfx = "am" if uses_mut else "a"
    base_areas = ["area_a", "area_b", "area_c"]
    if uses_mut:
        base_areas.append("area_a_mut")
    if has_d:
        base_areas.append("area_d")
    active_scenes = [ret_scene, "scene_a_clean", "scene_b"]
    if has_d:
        active_scenes.append("scene_d")
    raw_tags = [
        f"{ret_pfx}_foreign_ground",
        f"{ret_pfx}_foreign_in_chest",
        f"{ret_pfx}_foreign_in_child_kit",
        "b_foreign_in_chest",
        "c_persistent_control",
    ]
    return {
        "uses_mut": uses_mut,
        "has_d": has_d,
        "ret_scene": ret_scene,
        "ret_area": ret_area,
        "ret_pfx": ret_pfx,
        "base_areas": base_areas,
        "active_scenes": active_scenes,
        "raw_tags": raw_tags,
    }


def _area_center(area_id, fixture):
    a = fixture["areas"].get(area_id)
    if not a:
        raise ValueError(f"unknown area {area_id!r}")
    return float(a["center_x_m"]), float(a["center_z_m"]), float(a["radius_m"])


def _free_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _surface_y(x, z):
    return 100.0 + 10.0 * math.sin(float(x) / 100.0) * math.cos(float(z) / 100.0)


def _probe_sources_at_commit(git_head):
    top = f03_common._git_toplevel(REPO_ROOT)
    cwd = str(top if top is not None else REPO_ROOT)
    proc = subprocess.run(
        [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
            git_head,
            "--",
            "DayZSandbox_dev/qa/probe/DayZSandbox_QA",
            "qa/probe/DayZSandbox_QA",
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        return {}
    out = {}
    for raw in proc.stdout.splitlines():
        p = raw.strip()
        if not p:
            continue
        norm = p.replace("\\", "/").lstrip("/")
        if norm.startswith("DayZSandbox_dev/"):
            norm = norm[len("DayZSandbox_dev/"):]
        fname = Path(norm).name
        if norm.startswith("qa/probe/DayZSandbox_QA/scripts/") and fname.startswith("DSBX_QA_X_Persist") and fname.endswith(".c"):
            show = subprocess.run(
                ["git", "show", f"{git_head}:{p}"],
                cwd=cwd,
                capture_output=True,
                check=False,
            )
            if show.returncode == 0:
                out[p] = show.stdout.decode("utf-8")
    return out


def _storage_env():
    path = None
    import os
    cfg = os.environ.get("DSBX_S_PERSIST_STORAGE_CONFIG")
    if cfg:
        path = Path(cfg)
    if path is not None and path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return _fixture()["storage_env"]


def _snapshot_tree(root):
    root = Path(root)
    if not root.is_dir():
        return None
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            st = p.stat()
            out[rel] = {
                "sha256": f03_common.sha256_file_hex(p),
                "size_b": int(st.st_size),
                "mtime_ns": int(st.st_mtime_ns),
            }
    return out


def _offline_storage_marker():
    payload = b"dsbx-offline-storage"
    return {
        "offline_storage_marker.bin": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_b": len(payload),
            "mtime_ns": 0,
        }
    }


class _Part:
    def __init__(self, args, base_dir, part_name, argv, fixture):
        self.args = args
        self.part_name = part_name
        self.fixture = fixture
        self.layout = _part_layout(part_name, fixture)
        self.clock = {"ms": 1000.0}
        self.creature_positions = {}
        self.census_results = {}
        self.t5_centers = []
        self.ctx = f03_common.PartContext(
            base_dir=base_dir,
            part_name=part_name,
            spike_id=SPIKE_ID,
            args=args,
            argv=argv,
            spawn_offline_peers=False,
        )
        self.ctx.samples_dir.mkdir(parents=True, exist_ok=True)
        self.ctx._bridge_writer = f03_common._JsonlWriter(self.ctx.samples_dir / "bridge.jsonl")
        self.ctx._scenario_writer = f03_common._JsonlWriter(self.ctx.samples_dir / "scenario.jsonl")
        self.ctx._test_mode_writer = f03_common._JsonlWriter(self.ctx.part_dir / "test_mode.jsonl")
        self.ctx.keys = {"server": secrets.token_hex(16), "client": secrets.token_hex(16)}
        self.bridge = QABridge(
            hold_ms=self.ctx.hold_ms,
            lease_ms=self.ctx.lease_ms,
            sink=self.ctx._bridge_writer.write,
            test_mode_sink=self.ctx._test_mode_writer.write,
        )
        self.ctx.bridge = self.bridge
        for role, key in self.ctx.keys.items():
            self.bridge.set_peer_key(role, key)
        self.bridge.start()
        self.ctx._prepare_profiles()
        for role in self.ctx.required_peers():
            self.ctx.write_config(role, callback_budget=2000)
        self.ctx.expected_stamp = f03_common.compute_probe_stamp_at_commit(
            self.ctx.git_head, repo_root=self.ctx.repo_root
        )
        self.ctx._write_part_json()
        self.peers = {}
        self.server_ext = None
        self.server_epoch_old = ""
        self.server_epoch_new = ""
        self.director_uid_t0 = ""
        self.spawn_tick_max = 0.0

    # ---------------------------------------------------------------- plumbing
    def record(self, row):
        self.ctx.record_scenario(row)

    def advance(self, dt_ms=50.0):
        self.clock["ms"] += float(dt_ms)

    def set_clock(self, ms):
        self.clock["ms"] = max(float(ms), self.clock["ms"])

    def _start_peers(self):
        for role in ("server", "client"):
            cfg = str(self.ctx.profiles[role] / "dsbx_qa.json")
            peer = fake_peer.Peer(
                cfg,
                role,
                _free_udp(),
                60.0,
                self.args.fault,
                clock_ms_fn=lambda: self.clock["ms"],
                git_head=self.ctx.git_head,
            )
            self.peers[role] = peer
            threading.Thread(target=peer.run, daemon=True).start()
        deadline = time.monotonic() + float(self.ctx.peer_timeout_s)
        while time.monotonic() < deadline:
            if self.bridge.registered("server") and self.bridge.registered("client"):
                break
            time.sleep(0.02)
        if not (self.bridge.registered("server") and self.bridge.registered("client")):
            raise RuntimeError("peer hello timeout")
        expected_pv = f"dsbx-qa1+{self.ctx.expected_stamp}"
        with self.bridge.cv:
            hellos = [dict(e) for e in self.bridge.events if e.get("ev") == "hello" and e.get("http") == 200]
        for ev in hellos:
            proto, h_build, pv = f03_common._hello_proto_and_build(ev)
            if proto != "qa0" or h_build != self.ctx.build or pv != expected_pv:
                raise RuntimeError(f"hello mismatch: {ev}")
        self.server_ext = self._find_ext(self.peers["server"])
        self.server_epoch_old = self.server_ext.epoch
        self.director_uid_t0 = self.server_ext.director_uid

    @staticmethod
    def _find_ext(peer):
        for ext in peer.exts:
            if hasattr(ext, "simulate_world_restart"):
                return ext
        raise RuntimeError("PersistFakeExt not loaded")

    def _shutdown_peers(self):
        for peer in self.peers.values():
            peer.shutdown()
        for peer in self.peers.values():
            for _ in range(100):
                if not peer.alive:
                    break
                time.sleep(0.01)
        self.peers = {}

    def issue(self, verb, payload, *, qa_fault=None, peer="server"):
        return f03_common.issue_one(self.ctx, peer, verb, payload, qa_fault=qa_fault)

    def issue_done(self, verb, payload, *, qa_fault=None, peer="server"):
        out = self.issue(verb, payload, qa_fault=qa_fault, peer=peer)
        if out.status != "done":
            raise RuntimeError(f"{verb} -> {out.status}/{out.reason}")
        return out
