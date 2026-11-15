"""Ayudante comun F0.3: ciclo de vida por parte, sello en git_head, issue_one, read_job_pages y aggregate_spike."""

import ast
from dataclasses import dataclass
import hashlib
import importlib
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from bridge_qa import QABridge
import gate_core
import wire

REPO_ROOT = Path(__file__).resolve().parents[2]
FAKE_PEER = Path(__file__).resolve().with_name("fake_peer.py")

F02_VERBS = frozenset(
    {
        "srv_read",
        "ground_query",
        "ambient_set",
        "ambient_read",
        "cam_pose_set",
        "cam_pose_read",
        "rpc_burst",
        "rpc_log_read",
    }
)

TERMINAL_JOB_STATES = frozenset({"done", "stopped", "failed", "expired"})

TECH_FAILURE_DETAILS = frozenset(
    {
        "result_timeout",
        "result_lost",
        "operator_timeout",
        "http_error",
        "wire_cap_exceeded",
        "artifact_unverified",
        "stamp_source_unavailable",
        "build_mismatch",
        "params_unverified",
        "callback_budget_exhausted",
    }
)

_NONCE16_RE = re.compile(r"^[0-9a-f]{16}$")
_PROBE_PREFIXES = (
    "DayZSandbox_dev/qa/probe/DayZSandbox_QA",
    "qa/probe/DayZSandbox_QA",
)
_F03_COMMON_PATHS = (
    "DayZSandbox_dev/qa/f03_common.py",
    "qa/f03_common.py",
)

# D12 (brief F0.3-0, §15): en la parte probe-budget el log se lee cada PROBE_BUDGET_LOG_POLL_MS y la sonda reintenta
# cada PROBE_BUDGET_RETRY_MS (reintentos escasos: el caso sano no cae en el intervalo de orden incierto). Van en
# identity.params y verify_eval_params_at_commit los compara con los que define git_head.
PROBE_BUDGET_LOG_POLL_MS = 10
PROBE_BUDGET_RETRY_MS = 1000

_WIRE_PATHS = (
    "DayZSandbox_dev/qa/wire.py",
    "qa/wire.py",
)


class StampSourceUnavailableError(RuntimeError):
    """El commit git_head o las fuentes de la sonda en ese commit no estan disponibles."""


@dataclass(frozen=True)
class OpOutcome:
    op_id: str
    peer: str
    verb: str
    status: str
    reason: str
    dup: bool
    issued_ms: float
    recv_ms: float
    done_ms: float
    frame_recv: int
    frame_done: int
    read: dict
    payload: dict


def _git_toplevel(repo_root: Path) -> Path | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return Path(proc.stdout.strip())


def _resolve_repo_root(repo_root: Path | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    cwd_top = _git_toplevel(Path.cwd())
    if cwd_top is not None:
        return cwd_top
    return REPO_ROOT


def compute_probe_stamp_at_commit(git_head: str, repo_root: Path | None = None) -> str:
    if not isinstance(git_head, str) or not git_head.strip():
        raise StampSourceUnavailableError("stamp_source_unavailable")
    head = git_head.strip()
    toplevel = _git_toplevel(_resolve_repo_root(repo_root))
    if toplevel is None:
        raise StampSourceUnavailableError("stamp_source_unavailable")
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{head}^{{commit}}"],
        cwd=toplevel,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if verify.returncode != 0:
        raise StampSourceUnavailableError("stamp_source_unavailable")

    chosen_prefix = None
    tree_paths = []
    for prefix in _PROBE_PREFIXES:
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", head, "--", prefix],
            cwd=toplevel,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if ls.returncode == 0 and ls.stdout.strip():
            chosen_prefix = prefix
            tree_paths = [line.strip() for line in ls.stdout.splitlines() if line.strip()]
            break

    if chosen_prefix is None or not tree_paths:
        raise StampSourceUnavailableError("stamp_source_unavailable")

    prefix_slash = chosen_prefix + "/"
    pairs = []
    for tree_path in sorted(tree_paths):
        if not tree_path.startswith(prefix_slash):
            continue
        rel = tree_path[len(prefix_slash) :]
        if rel == wire.STAMP_REL_PATH:
            continue
        show = subprocess.run(
            ["git", "show", f"{head}:{tree_path}"],
            cwd=toplevel,
            capture_output=True,
            check=False,
        )
        if show.returncode != 0:
            raise StampSourceUnavailableError("stamp_source_unavailable")
        pairs.append((rel, show.stdout))

    if not pairs:
        raise StampSourceUnavailableError("stamp_source_unavailable")
    return wire.compute_probe_stamp_from_pairs(pairs)


def read_wire_cap_at_commit(git_head: str, repo_root: Path | None = None) -> int | None:
    if not isinstance(git_head, str) or not git_head.strip():
        return None
    head = git_head.strip()
    toplevel = _git_toplevel(_resolve_repo_root(repo_root))
    if toplevel is None:
        return None
    for rel_wire in _WIRE_PATHS:
        show = subprocess.run(
            ["git", "show", f"{head}:{rel_wire}"],
            cwd=toplevel,
            capture_output=True,
            check=False,
        )
        if show.returncode != 0:
            continue
        try:
            tree = ast.parse(show.stdout.decode("utf-8"), filename=rel_wire)
        except (UnicodeDecodeError, SyntaxError):
            return None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "WIRE_CAP":
                        if (
                            isinstance(node.value, ast.Constant)
                            and isinstance(node.value.value, int)
                            and not isinstance(node.value.value, bool)
                        ):
                            return int(node.value.value)
            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id == "WIRE_CAP" and node.value is not None:
                    if (
                        isinstance(node.value, ast.Constant)
                        and isinstance(node.value.value, int)
                        and not isinstance(node.value.value, bool)
                    ):
                        return int(node.value.value)
        return None
    return None


def _is_untracked_precommit_wire(toplevel: Path) -> bool:
    for rel_wire in _WIRE_PATHS:
        cand = toplevel / rel_wire
        if not cand.is_file():
            continue
        ls = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel_wire],
            cwd=toplevel,
            capture_output=True,
            check=False,
        )
        if ls.returncode != 0:
            return True
    return False


def read_int_const_at_commit(git_head: str, rel_paths, name: str, repo_root: Path | None = None) -> int | None:
    """Entero de `name = <int>` a nivel de modulo en el primer rel_path que exista en git_head; None si no lo define."""
    if not isinstance(git_head, str) or not git_head.strip():
        return None
    toplevel = _git_toplevel(_resolve_repo_root(repo_root))
    if toplevel is None:
        return None
    for rel in rel_paths:
        show = subprocess.run(
            ["git", "show", f"{git_head.strip()}:{rel}"],
            cwd=toplevel,
            capture_output=True,
            check=False,
        )
        if show.returncode != 0:
            continue
        try:
            tree = ast.parse(show.stdout.decode("utf-8"), filename=rel)
        except (UnicodeDecodeError, SyntaxError):
            return None
        for node in tree.body:
            value = None
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
                value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, int) and not isinstance(value.value, bool):
                return int(value.value)
        return None
    return None


_D12_PARAMS = (
    ("probe_budget_log_poll_ms", "PROBE_BUDGET_LOG_POLL_MS"),
    ("probe_budget_retry_ms", "PROBE_BUDGET_RETRY_MS"),
)


def verify_eval_params_at_commit(manifest: dict, repo_root: Path | None = None) -> tuple[bool, str]:
    eff_root = _resolve_repo_root(repo_root)
    identity = manifest.get("identity")
    if not isinstance(identity, dict):
        return False, "params_unverified"
    git_head = identity.get("git_head")
    if not isinstance(git_head, str) or not git_head.strip():
        return False, "params_unverified"
    id_params = identity.get("params")
    if not isinstance(id_params, dict):
        return False, "params_unverified"
    saved_cap = id_params.get("wire_cap")
    if not isinstance(saved_cap, int) or isinstance(saved_cap, bool) or saved_cap <= 0:
        return False, "params_unverified"

    committed_cap = read_wire_cap_at_commit(git_head, repo_root=eff_root)
    if committed_cap is not None:
        if saved_cap != committed_cap:
            return False, "params_unverified"
        # D12: si git_head ya define los parametros de probe-budget, la identidad tiene que traerlos iguales.
        for pname, cname in _D12_PARAMS:
            committed = read_int_const_at_commit(git_head, _F03_COMMON_PATHS, cname, repo_root=eff_root)
            if committed is not None and id_params.get(pname) != committed:
                return False, "params_unverified"
        return True, ""

    toplevel = _git_toplevel(eff_root)
    if (
        toplevel is not None
        and toplevel.resolve() == REPO_ROOT.resolve()
        and manifest.get("build") == "offline"
        and identity.get("git_dirty") is True
        and _is_untracked_precommit_wire(toplevel)
        and saved_cap == wire.WIRE_CAP
    ):
        return True, ""

    return False, "params_unverified"


def read_jsonl(path: Path) -> list[dict]:
    p = Path(path)
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def sha256_file_hex(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _free_udp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _allocate_part_nonce(base_dir: Path) -> str:
    existing = set()
    if base_dir.is_dir():
        for pfile in base_dir.glob("*/part.json"):
            try:
                data = gate_core.read_json(pfile)
                if isinstance(data, dict) and isinstance(data.get("op_nonce"), str):
                    existing.add(data["op_nonce"])
            except Exception:
                continue
    while True:
        cand = secrets.token_hex(8)
        if cand not in existing:
            return cand


class _JsonlWriter:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8", newline="\n")

    def write(self, row: dict) -> None:
        self._fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh and not self._fh.closed:
            self._fh.close()


class PartContext:
    """Contexto de ejecucion de una parte individual (run, mut-*, o harness test)."""

    def __init__(
        self,
        *,
        base_dir: Path,
        part_name: str,
        spike_id: str,
        args,
        argv: list[str],
        repo_root: Path = REPO_ROOT,
        bridge: QABridge | None = None,
        spawn_offline_peers: bool = True,
        initial_callback_budget: int = 2000,
    ):
        self.base_dir = Path(base_dir)
        self.part_name = part_name
        self.part_dir = self.base_dir / part_name
        self.samples_dir = self.part_dir / "samples"
        self.spike_id = spike_id
        self.args = args
        self.argv = list(argv)
        self.repo_root = Path(repo_root)
        self.build = args.build
        self.both = bool(getattr(args, "both", True))
        self.ttl_ms = int(getattr(args, "ttl_ms", gate_core.DEFAULT_TTL_MS))
        self.retry_ms = int(getattr(args, "retry_ms", gate_core.DEFAULT_RETRY_MS))
        self.lease_ms = int(getattr(args, "lease_ms", gate_core.DEFAULT_LEASE_MS))
        self.hold_ms = int(getattr(args, "hold_ms", gate_core.DEFAULT_HOLD_MS))
        self.seed = int(getattr(args, "seed", gate_core.DEFAULT_SEED))
        self.peer_timeout_s = float(gate_core.peer_timeout_s(self.build, getattr(args, "peer_timeout", None)))
        self.initial_callback_budget = int(initial_callback_budget)
        self.spawn_offline_peers = bool(spawn_offline_peers)

        self.op_nonce = _allocate_part_nonce(self.base_dir)
        self._op_counter = 0
        self.op_map: list[dict] = []
        self.inflight_op_id: dict[str, str | None] = {"server": None, "client": None}
        self.inflight_since_idx: dict[str, int] = {"server": 0, "client": 0}
        self.operator_timed_out = False
        self.startup_reason: str | None = None

        self.started_utc = gate_core.utc_now()
        self.harness = gate_core.git_harness(repo_root=self.repo_root)
        self.git_head = self.harness.get("git_head")
        self.expected_stamp: str | None = None
        self.pbo_sha256: str | None = None

        pbo_arg = getattr(args, "pbo", None)
        if pbo_arg and Path(pbo_arg).is_file():
            self.pbo_sha256 = sha256_file_hex(Path(pbo_arg))

        self._owns_bridge = bridge is None
        self.bridge = bridge
        self._bridge_writer: _JsonlWriter | None = None
        self._scenario_writer: _JsonlWriter | None = None
        self._test_mode_writer: _JsonlWriter | None = None
        self._tmp_dir: tempfile.TemporaryDirectory | None = None
        self.profiles: dict[str, Path] = {}
        self.peer_logs: dict[str, Path] = {}
        self.keys: dict[str, str] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        self._log_handles: list = []
        self.fake_peer_pids: dict[str, int | None] = {"server": None, "client": None}

    @classmethod
    def from_bridge(
        cls,
        bridge: QABridge,
        part_dir: Path,
        *,
        spike_id: str = "F0.3-0",
        part_name: str | None = None,
        ttl_ms: int = gate_core.DEFAULT_TTL_MS,
        build: str = "offline",
        both: bool = True,
        repo_root: Path = REPO_ROOT,
    ) -> "PartContext":
        pdir = Path(part_dir)
        base_dir = pdir.parent
        pname = part_name if part_name is not None else pdir.name

        class _StubArgs:
            pass

        stub = _StubArgs()
        stub.build = build
        stub.both = both
        stub.ttl_ms = ttl_ms
        stub.retry_ms = gate_core.DEFAULT_RETRY_MS
        stub.lease_ms = bridge.lease_ms
        stub.hold_ms = bridge.hold_ms
        stub.seed = gate_core.DEFAULT_SEED
        stub.peer_timeout = 20.0
        stub.pbo = None
        stub.fault = None
        ctx = cls(
            base_dir=base_dir,
            part_name=pname,
            spike_id=spike_id,
            args=stub,
            argv=[],
            repo_root=repo_root,
            bridge=bridge,
            spawn_offline_peers=False,
        )
        ctx.samples_dir.mkdir(parents=True, exist_ok=True)
        ctx._scenario_writer = _JsonlWriter(ctx.samples_dir / "scenario.jsonl")
        ctx._write_part_json()
        return ctx

    def __enter__(self) -> "PartContext":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    def open(self) -> None:
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self._bridge_writer = _JsonlWriter(self.samples_dir / "bridge.jsonl")
        self._scenario_writer = _JsonlWriter(self.samples_dir / "scenario.jsonl")
        self._test_mode_writer = _JsonlWriter(self.part_dir / "test_mode.jsonl")
        self._write_part_json()

        if self.build in ("retail", "diag") and self.harness.get("git_dirty") is not False:
            self.startup_reason = "git_dirty"

        if self.startup_reason is None:
            try:
                self.expected_stamp = compute_probe_stamp_at_commit(self.git_head or "", repo_root=self.repo_root)
            except StampSourceUnavailableError:
                self.startup_reason = "stamp_source_unavailable"

        if self._owns_bridge:
            self.bridge = QABridge(
                hold_ms=self.hold_ms,
                lease_ms=self.lease_ms,
                sink=self._bridge_writer.write,
                test_mode_sink=self._test_mode_writer.write,
            )
            self.keys = {
                "server": secrets.token_hex(16),
                "client": secrets.token_hex(16),
            }
            for role, key in self.keys.items():
                self.bridge.set_peer_key(role, key)
            self.bridge.start()

        self._prepare_profiles()
        for role in self.required_peers():
            self.write_config(role, callback_budget=self.initial_callback_budget)

        if self.build == "offline" and self.spawn_offline_peers:
            self._spawn_peers()

        if self.startup_reason is None:
            ok = self.wait_for_peers(self.peer_timeout_s)
            if not ok and self.startup_reason is None:
                self.startup_reason = "peer_timeout"
            if self.startup_reason is None:
                self.startup_reason = self._verify_hello_events()

        self.finalize_manifest()

    def required_peers(self) -> tuple[str, ...]:
        return ("server", "client") if self.both else ("server",)

    def _prepare_profiles(self) -> None:
        srv_prof = getattr(self.args, "server_profile", None)
        cli_prof = getattr(self.args, "client_profile", None)
        if srv_prof and cli_prof:
            self.profiles = {"server": Path(srv_prof), "client": Path(cli_prof)}
            self._tmp_dir = tempfile.TemporaryDirectory(prefix="dsbx-f03-logs-")
            troot = Path(self._tmp_dir.name)
            self.peer_logs = {
                "server": troot / "server_peer.log",
                "client": troot / "client_peer.log",
            }
            return
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="dsbx-f03-prof-")
        troot = Path(self._tmp_dir.name)
        for role in ("server", "client"):
            pdir = troot / role
            pdir.mkdir(parents=True, exist_ok=True)
            self.profiles[role] = pdir
            self.peer_logs[role] = troot / f"{role}_peer.log"

    def write_config(
        self,
        peer: str,
        *,
        callback_budget: int | None = None,
        retry_ms: int | None = None,
        key: str | None = None,
        url: str | None = None,
    ) -> Path:
        prof = self.profiles[peer]
        prof.mkdir(parents=True, exist_ok=True)
        cfg_path = prof / "dsbx_qa.json"
        eff_budget = self.initial_callback_budget if callback_budget is None else int(callback_budget)
        eff_retry = self.retry_ms if retry_ms is None else int(retry_ms)
        eff_key = self.keys.get(peer, "") if key is None else str(key)
        # Con "/" final: UrlUsable() de la sonda la exige (DSBX_QA_Probe.c), igual que s_puente_run.py (H1 de Sol r1).
        eff_url = f"http://127.0.0.1:{self.bridge.port}/" if url is None else str(url)
        body = {
            "callback_budget": eff_budget,
            "key": eff_key,
            "retry_ms": eff_retry,
            "url": eff_url,
        }
        tmp_path = prof / f"dsbx_qa.{secrets.token_hex(4)}.tmp"
        tmp_path.write_bytes((json.dumps(body, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        tmp_path.replace(cfg_path)
        return cfg_path

    def _spawn_peers(self) -> None:
        rpc_port = _free_udp_port()
        fault = getattr(self.args, "fault", None)
        clock_offset_ms = float(getattr(self.args, "clock_offset_ms", 0.0) or 0.0)
        for role in self.required_peers():
            cfg_path = self.profiles[role] / "dsbx_qa.json"
            log_path = self.peer_logs[role]
            log_fh = log_path.open("w", encoding="utf-8", newline="\n")
            self._log_handles.append(log_fh)
            cmd = [
                sys.executable,
                str(FAKE_PEER),
                "--peer",
                role,
                "--config",
                str(cfg_path),
                "--rpc-port",
                str(rpc_port),
            ]
            if self.git_head:
                cmd.extend(["--git-head", self.git_head])
            elif self.expected_stamp:
                cmd.extend(["--probe-ver", f"dsbx-qa1+{self.expected_stamp}"])
            if fault:
                cmd.extend(["--fault", str(fault)])
            if clock_offset_ms:
                cmd.extend(["--clock-offset-ms", str(clock_offset_ms)])
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )
            self.procs[role] = proc
            self.fake_peer_pids[role] = proc.pid

    def wait_for_peers(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        req = self.required_peers()
        while time.monotonic() < deadline:
            if all(self.bridge.registered(r) is not None for r in req):
                return True
            for proc in self.procs.values():
                if proc.poll() is not None:
                    return False
            time.sleep(0.02)
        return all(self.bridge.registered(r) is not None for r in req)

    def _verify_hello_events(self) -> str | None:
        with self.bridge.cv:
            events = list(self.bridge.events)
        hellos = [ev for ev in events if ev.get("ev") == "hello" and ev.get("http") == 200]
        for role in self.required_peers():
            if not any(ev.get("peer") == role for ev in hellos):
                return "build_mismatch"
        for ev in hellos:
            proto, h_build, _pv = _hello_proto_and_build(ev)
            if proto != "qa0" or h_build != self.build:
                return "build_mismatch"
        if self.expected_stamp is None:
            return "stamp_source_unavailable"
        expected_pv = f"dsbx-qa1+{self.expected_stamp}"
        for ev in hellos:
            _proto, _h_build, pv = _hello_proto_and_build(ev)
            if not isinstance(pv, str) or pv == "dsbx-qa1+unstamped" or pv != expected_pv:
                return "artifact_unverified"
        return None

    def now_h_ms(self) -> float:
        return self.bridge.now_ms()

    def peek_next_op_id(self) -> str:
        return f"{self.op_nonce}-{self._op_counter + 1}"

    def commit_op_id(self, op_id: str, peer: str, verb: str, auto_allocated: bool) -> None:
        if auto_allocated:
            self._op_counter += 1
        self.op_map.append(
            {
                "n": len(self.op_map) + 1,
                "op_id": op_id,
                "peer": peer,
                "verb": verb,
            }
        )
        self._write_part_json()

    def _write_part_json(self) -> None:
        gate_core.write_json(
            self.part_dir / "part.json",
            {
                "op_map": list(self.op_map),
                "op_nonce": self.op_nonce,
                "part": self.part_name,
                "spike_id": self.spike_id,
            },
        )

    def record_scenario(self, row: dict) -> None:
        payload = dict(row)
        payload.setdefault("t_ms", self.bridge.now_ms())
        if self._scenario_writer is not None:
            self._scenario_writer.write(payload)

    def write_injection(
        self,
        mutant: str,
        kind: str,
        target: str,
        observable_effect: dict,
        when_h_ms: float | None = None,
    ) -> None:
        gate_core.write_json(
            self.part_dir / "injection.json",
            {
                "applied": True,
                "kind": kind,
                "mutant": mutant,
                "observable_effect": dict(observable_effect),
                "target": target,
                "when_h_ms": self.bridge.now_ms() if when_h_ms is None else float(when_h_ms),
            },
        )

    def collect_probe_budget_logs(self) -> list[dict]:
        """Extrae lineas [DSBX_QA] callback_budget_exhausted del log de cada peer hacia samples/probe_log.jsonl."""
        rows = []
        candidates: list[tuple[str, Path]] = []
        for role in self.required_peers():
            if role in self.peer_logs:
                candidates.append((role, self.peer_logs[role]))
            prof = self.profiles.get(role)
            if prof is not None and prof.is_dir():
                for rpt in sorted(prof.glob("*.log")) + sorted(prof.glob("script_*.log")):
                    candidates.append((role, rpt))
        seen = set()
        for role, lpath in candidates:
            if not lpath.is_file():
                continue
            try:
                lines = lpath.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                if "[DSBX_QA] callback_budget_exhausted" in line:
                    key = (role, line.strip())
                    if key in seen:
                        continue
                    seen.add(key)
                    created_m = re.search(r"created_n=(\d+)", line)
                    budget_m = re.search(r"budget_n=(\d+)", line)
                    rows.append(
                        {
                            "budget_n": int(budget_m.group(1)) if budget_m else None,
                            "created_n": int(created_m.group(1)) if created_m else None,
                            "ev": "probe_log",
                            "line": line.strip(),
                            "peer": role,
                            "tag": "callback_budget_exhausted",
                        }
                    )
        if rows:
            out_path = self.samples_dir / "probe_log.jsonl"
            with out_path.open("w", encoding="utf-8", newline="\n") as fh:
                for row in rows:
                    fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        return rows

    def wait_peer_idle(self, peer: str, timeout_ms: float) -> str:
        return wait_peer_idle(self, peer, timeout_ms)

    def finalize_manifest(self) -> dict:
        self._write_part_json()
        events = []
        if self.bridge is not None:
            with self.bridge.cv:
                events = list(self.bridge.events)
        peer_insts: dict[str, list[str]] = {"server": [], "client": []}
        peer_builds: dict[str, str | None] = {}
        for role in self.required_peers():
            peer_builds[role] = None
        for ev in events:
            if ev.get("ev") == "hello" and ev.get("http") == 200 and ev.get("ok") is not False:
                role = ev.get("peer")
                inst = ev.get("inst")
                if role in peer_insts and isinstance(inst, str) and inst not in peer_insts[role]:
                    peer_insts[role].append(inst)
                if role in peer_builds:
                    _proto, h_build, _pv = _hello_proto_and_build(ev)
                    peer_builds[role] = h_build

        ended_utc = gate_core.utc_now()
        port = self.bridge.port if self.bridge is not None else None
        run_id = self.bridge.run_id if self.bridge is not None else None
        manifest = gate_core.make_manifest(
            "spike",
            self.spike_id,
            self.args,
            self.argv,
            self.started_utc,
            ended_utc,
            port=port,
            run_id=run_id,
        )
        manifest["harness"] = dict(self.harness)
        manifest["identity"] = {
            "build": self.build,
            "git_dirty": self.harness.get("git_dirty"),
            "git_head": self.git_head,
            "params": {
                "hold_ms": self.hold_ms,
                "lease_ms": self.lease_ms,
                "probe_budget_log_poll_ms": PROBE_BUDGET_LOG_POLL_MS,
                "probe_budget_retry_ms": PROBE_BUDGET_RETRY_MS,
                "retry_ms": self.retry_ms,
                "seed": self.seed,
                "ttl_ms": self.ttl_ms,
                "wire_cap": int(wire.WIRE_CAP),
            },
            "pbo_sha256": self.pbo_sha256,
            "peer_builds": peer_builds,
            "probe_stamp": self.expected_stamp,
        }
        manifest["execution_identity"] = {
            "fake_peer_pids": dict(self.fake_peer_pids),
            "key_sha256": {
                role: (hashlib.sha256(self.keys[role].encode("utf-8")).hexdigest()[:16] if self.keys.get(role) else None)
                for role in ("server", "client")
            },
            "peer_insts": peer_insts,
            "port": port,
        }
        gate_core.write_json(self.part_dir / "manifest.json", manifest)
        return manifest

    def close(self) -> None:
        try:
            self.finalize_manifest()
        except Exception:
            pass
        for proc in self.procs.values():
            if proc.poll() is None:
                proc.terminate()
        for proc in self.procs.values():
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        self.procs.clear()
        for fh in self._log_handles:
            try:
                fh.close()
            except OSError:
                pass
        self._log_handles.clear()
        if self._owns_bridge and self.bridge is not None:
            try:
                self.bridge.stop()
            except Exception:
                pass
        if self._bridge_writer is not None:
            self._bridge_writer.close()
        if self._scenario_writer is not None:
            self._scenario_writer.close()
        if self._test_mode_writer is not None:
            self._test_mode_writer.close()
        if self._tmp_dir is not None:
            try:
                self._tmp_dir.cleanup()
            except OSError:
                pass
            self._tmp_dir = None


def _normalize_new_verb_args(payload: dict | None, qa_fault: str | None) -> dict:
    if payload is None:
        packed = wire.empty_payload()
    elif ("str" in payload or "num" in payload) and "sk" not in payload:
        packed = wire.pack_payload(
            scalars_str=payload.get("str"),
            scalars_num=payload.get("num"),
            num_cols=payload.get("ncol"),
            str_cols=payload.get("scol"),
            row_dicts=payload.get("rows"),
        )
    else:
        packed = wire.empty_payload()
        for k in ("sk", "sv", "nk", "nv", "ncol", "ncell", "scol", "scell"):
            if k in payload and payload[k] is not None:
                packed[k] = list(payload[k])
        if "rows" in payload and payload["rows"] is not None:
            packed["rows"] = int(payload["rows"])

    fault_fixed = wire.format_qa_fault(qa_fault)
    sk = list(packed["sk"])
    sv = list(packed["sv"])
    if "qa_fault" in sk:
        idx = sk.index("qa_fault")
        sv[idx] = fault_fixed
    else:
        sk.append("qa_fault")
        sv.append(fault_fixed)
    packed["sk"] = sk
    packed["sv"] = sv
    wire.validate_payload(packed)
    return packed


def _find_resolution_event(bridge: QABridge, op_id: str, since_idx: int) -> dict | None:
    if bridge.delivered:
        bridge._expire_delivered(bridge.now_ms())
    for idx in range(since_idx, len(bridge.events)):
        ev = bridge.events[idx]
        if ev.get("op_id") != op_id:
            continue
        kind = ev.get("ev")
        if kind == "result" and ev.get("http") == 200:
            return ev
        if kind in ("expire", "lost"):
            return ev
    return None


def wait_peer_idle(ctx: PartContext, peer: str, timeout_ms: float) -> str:
    prev_id = ctx.inflight_op_id.get(peer)
    if prev_id is None:
        return "idle"
    since_idx = ctx.inflight_since_idx.get(peer, 0)
    deadline = time.monotonic() + float(timeout_ms) / 1000.0
    with ctx.bridge.cv:
        while True:
            ev = _find_resolution_event(ctx.bridge, prev_id, since_idx)
            if ev is not None:
                ctx.inflight_op_id[peer] = None
                return str(ev["ev"])
            ctx.bridge._raise_failure()
            left = deadline - time.monotonic()
            if left <= 0:
                return "timeout"
            ctx.bridge.cv.wait(min(left, 0.05))


def issue_one(
    ctx: PartContext,
    peer: str,
    verb: str,
    payload: dict | None = None,
    *,
    ttl_ms: int | None = None,
    timeout_ms: int | None = None,
    target_inst: str | None = None,
    qa_fault: str | None = None,
    op_id: str | None = None,
    issued_ms: float | None = None,
) -> OpOutcome:
    with ctx.bridge.cv:
        prev_id = ctx.inflight_op_id.get(peer)
        if prev_id is not None:
            prev_ev = _find_resolution_event(ctx.bridge, prev_id, ctx.inflight_since_idx.get(peer, 0))
            if prev_ev is not None:
                ctx.inflight_op_id[peer] = None
            else:
                raise RuntimeError("peer slot busy: previous order still in flight")

    eff_inst = target_inst if target_inst is not None else ctx.bridge.registered(peer)
    if eff_inst is None:
        raise RuntimeError(f"peer {peer} is not registered")

    eff_ttl = int(ctx.ttl_ms if ttl_ms is None else ttl_ms)
    eff_timeout_ms = float((eff_ttl + 4500) if timeout_ms is None else timeout_ms)

    if verb in F02_VERBS:
        order_args = dict(payload or {})
    else:
        order_args = _normalize_new_verb_args(payload, qa_fault)

    auto_alloc = op_id is None
    cand_id = ctx.peek_next_op_id() if auto_alloc else str(op_id)

    with ctx.bridge.cv:
        prev_id = ctx.inflight_op_id.get(peer)
        if prev_id is not None:
            prev_ev = _find_resolution_event(ctx.bridge, prev_id, ctx.inflight_since_idx.get(peer, 0))
            if prev_ev is not None:
                ctx.inflight_op_id[peer] = None
            else:
                raise RuntimeError("peer slot busy: previous order still in flight")
        since_idx = len(ctx.bridge.events)
        issued_val = ctx.bridge.now_ms() if issued_ms is None else float(issued_ms)
        ctx.bridge.enqueue(
            peer,
            verb,
            order_args,
            eff_inst,
            eff_ttl,
            op_id=cand_id,
            issued_ms=issued_val,
        )
        ctx.inflight_op_id[peer] = cand_id
        ctx.inflight_since_idx[peer] = since_idx

    ctx.commit_op_id(cand_id, peer, verb, auto_allocated=auto_alloc)

    deadline = time.monotonic() + eff_timeout_ms / 1000.0
    resolved_ev = None
    with ctx.bridge.cv:
        while True:
            ev = _find_resolution_event(ctx.bridge, cand_id, since_idx)
            if ev is not None:
                ctx.inflight_op_id[peer] = None
                resolved_ev = ev
                break
            ctx.bridge._raise_failure()
            left = deadline - time.monotonic()
            if left <= 0:
                break
            ctx.bridge.cv.wait(min(left, 0.05))

    empty_unpacked = {"str": {}, "num": {}, "rows": []}
    if resolved_ev is None:
        return OpOutcome(
            op_id=cand_id,
            peer=peer,
            verb=verb,
            status="timeout",
            reason="result_timeout",
            dup=False,
            issued_ms=float(issued_val),
            recv_ms=0.0,
            done_ms=0.0,
            frame_recv=0,
            frame_done=0,
            read={},
            payload=empty_unpacked,
        )

    ev_kind = resolved_ev["ev"]
    if ev_kind == "lost":
        return OpOutcome(
            op_id=cand_id,
            peer=peer,
            verb=verb,
            status="lost",
            reason="result_lost",
            dup=False,
            issued_ms=float(issued_val),
            recv_ms=0.0,
            done_ms=0.0,
            frame_recv=0,
            frame_done=0,
            read={},
            payload=empty_unpacked,
        )
    if ev_kind == "expire":
        return OpOutcome(
            op_id=cand_id,
            peer=peer,
            verb=verb,
            status="timeout",
            reason="result_timeout",
            dup=False,
            issued_ms=float(issued_val),
            recv_ms=0.0,
            done_ms=0.0,
            frame_recv=0,
            frame_done=0,
            read={},
            payload=empty_unpacked,
        )

    res = resolved_ev.get("result") or {}
    status = str(res.get("status") or "")
    reason = str(res.get("reason") or "")
    dup = bool(res.get("dup", False))
    recv_ms = float(res.get("recv_ms") or 0.0)
    done_ms = float(res.get("done_ms") or 0.0)
    frame_recv = int(res.get("frame_recv") or 0)
    frame_done = int(res.get("frame_done") or 0)
    raw_read = dict(res.get("read") or {})
    if status == "done" and raw_read.get("has") == ["payload"]:
        unpacked = wire.unpack_payload(raw_read)
    else:
        unpacked = empty_unpacked

    return OpOutcome(
        op_id=cand_id,
        peer=peer,
        verb=verb,
        status=status,
        reason=reason,
        dup=dup,
        issued_ms=float(issued_val),
        recv_ms=recv_ms,
        done_ms=done_ms,
        frame_recv=frame_recv,
        frame_done=frame_done,
        read=raw_read,
        payload=unpacked,
    )


def read_job_pages(
    ctx: PartContext,
    peer: str,
    job_id: str,
    *,
    ttl_ms: int | None = None,
    timeout_ms: int | None = None,
) -> dict:
    p0 = issue_one(
        ctx,
        peer,
        "job_read",
        wire.pack_payload({"job": job_id}, {"page_n": 0}),
        ttl_ms=ttl_ms,
        timeout_ms=timeout_ms,
    )
    if p0.status != "done":
        raise ValueError(f"job_read page 0 returned {p0.status}/{p0.reason}")
    state = p0.payload["str"].get("state", "")
    if state not in TERMINAL_JOB_STATES:
        raise ValueError(f"read_job_pages requires terminal job state, got {state!r}")

    rows_total_n = int(p0.payload["num"]["rows_total_n"])
    pages_n = int(p0.payload["num"]["pages_n"])
    all_rows = list(p0.payload["rows"])
    outcomes = [p0]

    for page_idx in range(1, pages_n):
        pi = issue_one(
            ctx,
            peer,
            "job_read",
            wire.pack_payload({"job": job_id}, {"page_n": page_idx}),
            ttl_ms=ttl_ms,
            timeout_ms=timeout_ms,
        )
        if pi.status != "done":
            raise ValueError(f"job_read page {page_idx} returned {pi.status}/{pi.reason}")
        if pi.payload["str"].get("state") != state:
            raise ValueError(f"job state changed during pagination: {state!r} -> {pi.payload['str'].get('state')!r}")
        if int(pi.payload["num"]["rows_total_n"]) != rows_total_n:
            raise ValueError("rows_total_n changed during pagination")
        all_rows.extend(pi.payload["rows"])
        outcomes.append(pi)

    if len(all_rows) != rows_total_n:
        raise ValueError(f"row count mismatch: read {len(all_rows)} != rows_total_n {rows_total_n}")

    return {
        "job_id": job_id,
        "num": dict(p0.payload["num"]),
        "outcomes": outcomes,
        "pages_n": pages_n,
        "reason": p0.payload["str"].get("reason", ""),
        "rows": all_rows,
        "rows_total_n": rows_total_n,
        "state": state,
        "str": dict(p0.payload["str"]),
    }


def await_operator(
    ctx: PartContext,
    step: str,
    action: str,
    instructions: str,
    predicate,
    timeout_s: float,
    offline_sim=None,
) -> dict:
    if ctx.build == "offline":
        sim_out = offline_sim(ctx) if callable(offline_sim) else None
        ev = None
        if callable(predicate):
            ev = ctx.bridge.wait_event(predicate, int(float(timeout_s) * 1000.0))
            if ev is None:
                ctx.operator_timed_out = True
                ctx.record_scenario({"action": action, "ev": "operator_timeout", "step": step})
                return {"action": action, "ok": False, "reason": "operator_timeout", "step": step}
        ctx.record_scenario({"action": action, "ev": "operator_done", "mode": "offline", "step": step})
        return {"action": action, "event": ev, "mode": "offline", "ok": True, "sim": sim_out, "step": step}

    await_path = ctx.part_dir / "AWAITING_OPERATOR.json"
    done_path = ctx.part_dir / "OPERATOR_DONE"
    # Una confirmacion vale para un solo paso: se descarta la de un paso anterior antes de publicar este y se
    # consume al usarla (H9 de Sol r1).
    done_path.unlink(missing_ok=True)
    gate_core.write_json(
        await_path,
        {
            "action": action,
            "instructions": instructions,
            "started_utc": gate_core.utc_now(),
            "step": step,
            "timeout_s": float(timeout_s),
        },
    )
    deadline = time.monotonic() + float(timeout_s)
    scan_idx = 0
    while time.monotonic() < deadline:
        if done_path.exists():
            done_path.unlink(missing_ok=True)
            await_path.unlink(missing_ok=True)
            ctx.record_scenario({"action": action, "ev": "operator_done", "mode": "file", "step": step})
            return {"action": action, "mode": "file", "ok": True, "step": step}
        if callable(predicate):
            with ctx.bridge.cv:
                while scan_idx < len(ctx.bridge.events):
                    cand = ctx.bridge.events[scan_idx]
                    scan_idx += 1
                    if predicate(cand):
                        await_path.unlink(missing_ok=True)
                        ctx.record_scenario({"action": action, "ev": "operator_done", "mode": "predicate", "step": step})
                        return {"action": action, "event": cand, "mode": "predicate", "ok": True, "step": step}
        time.sleep(0.05)

    ctx.operator_timed_out = True
    ctx.record_scenario({"action": action, "ev": "operator_timeout", "step": step})
    return {"action": action, "ok": False, "reason": "operator_timeout", "step": step}


def _has_tech_detail(detail: str) -> bool:
    if detail in TECH_FAILURE_DETAILS:
        return True
    for td in TECH_FAILURE_DETAILS:
        if detail.startswith(td + ":"):
            return True
    return False


def _hello_proto_and_build(ev: dict) -> tuple[str | None, str | None, str | None]:
    args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
    proto = args.get("proto") if "proto" in args else ev.get("proto")
    build = args.get("build") if "build" in args else ev.get("build")
    probe_ver = args.get("probe_ver") if "probe_ver" in args else ev.get("probe_ver")
    return proto, build, probe_ver


def aggregate_spike(
    base_dir: Path,
    spike_id: str,
    repo_root: Path | None = None,
    *,
    expected_mutants: dict | None = None,
    expected_harness_tests: dict | None = None,
) -> dict:
    base = Path(base_dir)
    _run_mod_name, _eval_mod_name, mut_mod_name = gate_core.SPIKE_REGISTRY[spike_id]
    mut_mod = importlib.import_module(mut_mod_name) if mut_mod_name else None
    exp_mutants = (
        dict(expected_mutants)
        if expected_mutants is not None
        else dict(getattr(mut_mod, "EXPECTED_MUTANTS", {}) if mut_mod else {})
    )
    exp_harness = (
        dict(expected_harness_tests)
        if expected_harness_tests is not None
        else dict(getattr(mut_mod, "EXPECTED_HARNESS_TESTS", {}) if mut_mod else {})
    )

    required_parts = ["run"] + [f"mut-{name}" for name in exp_mutants] + list(exp_harness.keys())

    part_manifests: dict[str, dict] = {}
    part_verdicts: dict[str, dict] = {}
    part_infos: dict[str, dict] = {}
    part_bridges: dict[str, list[dict]] = {}
    seen_nonces: set[str] = set()

    def _finish(code: int, reasons: list[str], checks=None, metrics=None) -> dict:
        members = []
        for pname in required_parts:
            pv = part_verdicts.get(pname)
            if pv is not None:
                members.append(
                    {
                        "exit_code": int(pv.get("exit_code", 2)),
                        "id": pname,
                        "reasons": list(pv.get("reasons") or []),
                        "verdict": pv.get("verdict") or gate_core.verdict_name(int(pv.get("exit_code", 2))),
                    }
                )
        verdict = gate_core.make_verdict(
            spike_id,
            code,
            checks=checks or [],
            metrics=metrics or {},
            reasons=reasons,
            members=members,
        )
        gate_core.write_json(base / "verdict.json", verdict)
        return verdict

    # Regla 1: presencia de partes y op_nonce unico de 16 hex en part.json
    for pname in required_parts:
        pdir = base / pname
        mfile = pdir / "manifest.json"
        vfile = pdir / "verdict.json"
        pfile = pdir / "part.json"
        sdir = pdir / "samples"
        if not (pdir.is_dir() and mfile.is_file() and vfile.is_file() and pfile.is_file() and sdir.is_dir()):
            return _finish(2, [f"missing_part:{pname}"])
        try:
            pinfo = gate_core.read_json(pfile)
            pman = gate_core.read_json(mfile)
            pver = gate_core.read_json(vfile)
        except Exception:
            return _finish(2, [f"missing_part:{pname}"])
        if not isinstance(pinfo, dict) or not isinstance(pman, dict) or not isinstance(pver, dict):
            return _finish(2, [f"missing_part:{pname}"])
        nonce = pinfo.get("op_nonce")
        if not isinstance(nonce, str) or not _NONCE16_RE.match(nonce) or nonce in seen_nonces:
            return _finish(2, [f"missing_part:{pname}"])
        seen_nonces.add(nonce)
        part_infos[pname] = pinfo
        part_manifests[pname] = pman
        part_verdicts[pname] = pver
        part_bridges[pname] = read_jsonl(sdir / "bridge.jsonl")

    # Regla 2: identidad de implementacion comun y arbol limpio
    ref_sig = None
    ref_manifest = None
    exec_identities = {}
    for pname in required_parts:
        pman = part_manifests[pname]
        ident = pman.get("identity")
        if not isinstance(ident, dict):
            return _finish(2, ["mixed_parts"])
        git_head = ident.get("git_head")
        if not isinstance(git_head, str) or not git_head.strip():
            return _finish(2, ["mixed_parts"])
        build = ident.get("build")
        if build != pman.get("build"):
            return _finish(2, ["mixed_parts"])
        if build in ("retail", "diag"):
            if ident.get("git_dirty") is not False:
                return _finish(2, ["git_dirty"])
            if not ident.get("pbo_sha256"):
                return _finish(2, ["mixed_parts"])
        sig = (
            git_head,
            ident.get("git_dirty"),
            build,
            json.dumps(ident.get("params"), sort_keys=True),
            ident.get("probe_stamp"),
            json.dumps(ident.get("peer_builds"), sort_keys=True),
            ident.get("pbo_sha256"),
        )
        if ref_sig is None:
            ref_sig = sig
            ref_manifest = pman
        elif sig != ref_sig:
            return _finish(2, ["mixed_parts"])
        exec_identities[pname] = pman.get("execution_identity")

    assert ref_manifest is not None
    ref_ident = ref_manifest["identity"]
    ref_build = ref_manifest["build"]
    ref_git_head = ref_ident["git_head"]

    # Regla 3: build y protocolo observados en /hello
    for pname in required_parts:
        pman = part_manifests[pname]
        ident = pman["identity"]
        req_peers = ("server", "client") if pman.get("both", True) else ("server",)
        peer_builds = ident.get("peer_builds")
        if not isinstance(peer_builds, dict):
            return _finish(2, ["build_mismatch"])
        for role in req_peers:
            if peer_builds.get(role) != ref_build:
                return _finish(2, ["build_mismatch"])
        hellos = [ev for ev in part_bridges[pname] if ev.get("ev") == "hello" and ev.get("http") == 200]
        for role in req_peers:
            if not any(ev.get("peer") == role for ev in hellos):
                return _finish(2, ["build_mismatch"])
        for ev in hellos:
            proto, h_build, _pv = _hello_proto_and_build(ev)
            if proto != "qa0" or h_build != ref_build:
                return _finish(2, ["build_mismatch"])

    # Regla 4: sello historico desde git_head + parametros historicos (A3)
    try:
        expected_stamp = compute_probe_stamp_at_commit(ref_git_head, repo_root=repo_root)
    except StampSourceUnavailableError:
        return _finish(2, ["stamp_source_unavailable"])

    ok_params, param_reason = verify_eval_params_at_commit(ref_manifest, repo_root=repo_root)
    if not ok_params:
        return _finish(2, [param_reason])

    expected_pv = f"dsbx-qa1+{expected_stamp}"
    for pname in required_parts:
        ident = part_manifests[pname]["identity"]
        if ident.get("probe_stamp") != expected_stamp:
            return _finish(2, ["artifact_unverified"])
        hellos = [ev for ev in part_bridges[pname] if ev.get("ev") == "hello" and ev.get("http") == 200]
        for ev in hellos:
            _proto, _h_build, pv = _hello_proto_and_build(ev)
            if not isinstance(pv, str) or pv == "dsbx-qa1+unstamped" or pv != expected_pv:
                return _finish(2, ["artifact_unverified"])

    # Regla 5: guarda de tope en el cable (wire_cap_exceeded)
    for pname in required_parts:
        if any(ev.get("ev") == "wire_cap_exceeded" for ev in part_bridges[pname]):
            return _finish(2, ["wire_cap_exceeded"])

    # Regla 6: prueba de inyeccion y ausencia de fallos tecnicos en mutantes
    for mname, spec in exp_mutants.items():
        pname = f"mut-{mname}"
        must_fail = list(spec.get("must_fail_checks") or [])
        allowed_non_pass = dict(spec.get("allowed_non_pass") or {})
        if not must_fail or not set(allowed_non_pass).isdisjoint(must_fail):
            return _finish(2, [f"invalid_mutant_spec:{mname}"])

        inj_path = base / pname / "injection.json"
        if not inj_path.is_file():
            return _finish(2, [f"missing_injection_proof:{mname}"])
        try:
            inj = gate_core.read_json(inj_path)
        except Exception:
            return _finish(2, [f"missing_injection_proof:{mname}"])
        if (
            not isinstance(inj, dict)
            or inj.get("applied") is not True
            or not isinstance(inj.get("observable_effect"), dict)
            or len(inj["observable_effect"]) == 0
        ):
            return _finish(2, [f"missing_injection_proof:{mname}"])

        pv = part_verdicts[pname]
        if pv.get("error") is not None:
            return _finish(2, [f"mutant_inconclusive:{mname}"])
        if any(_has_tech_detail(str(r)) for r in (pv.get("reasons") or [])):
            return _finish(2, [f"mutant_inconclusive:{mname}"])
        checks_list = pv.get("checks") or []
        checks_by_id = {c.get("id"): c for c in checks_list if isinstance(c, dict)}
        for c in checks_list:
            if _has_tech_detail(str(c.get("detail") or "")):
                return _finish(2, [f"mutant_inconclusive:{mname}"])
        for cid in must_fail:
            if cid not in checks_by_id or checks_by_id[cid].get("status") == "missing":
                return _finish(2, [f"mutant_inconclusive:{mname}"])
        for cid, c in checks_by_id.items():
            if cid not in must_fail and c.get("status") == "missing":
                if "missing" not in (allowed_non_pass.get(cid) or []):
                    return _finish(2, [f"mutant_inconclusive:{mname}"])

    # Regla 7: deteccion exacta por check en mutantes
    for mname, spec in exp_mutants.items():
        pname = f"mut-{mname}"
        must_fail = list(spec.get("must_fail_checks") or [])
        pv = part_verdicts[pname]
        checks_by_id = {c.get("id"): c for c in (pv.get("checks") or []) if isinstance(c, dict)}
        if int(pv.get("exit_code", 2)) == 0:
            return _finish(1, [f"mutant_not_detected:{mname}"])
        for cid in must_fail:
            if checks_by_id[cid].get("status") != "fail":
                return _finish(1, [f"mutant_not_detected:{mname}"])

    for mname, spec in exp_mutants.items():
        pname = f"mut-{mname}"
        must_fail = list(spec.get("must_fail_checks") or [])
        allowed_non_pass = dict(spec.get("allowed_non_pass") or {})
        expected_exit = int(spec.get("expected_exit_code", 1))
        pv = part_verdicts[pname]
        checks_by_id = {c.get("id"): c for c in (pv.get("checks") or []) if isinstance(c, dict)}
        for cid, c in checks_by_id.items():
            if cid in must_fail:
                continue
            st = c.get("status")
            if st != "pass" and st not in (allowed_non_pass.get(cid) or []):
                return _finish(2, [f"mutant_wrong_check:{mname}:{cid}"])
        if int(pv.get("exit_code", 2)) != expected_exit:
            return _finish(2, [f"mutant_inconclusive:{mname}"])

    # Pruebas del arnes (EXPECTED_HARNESS_TESTS, §14 F02-H4)
    for hname, hspec in exp_harness.items():
        hv = part_verdicts[hname]
        hchecks_list = hv.get("checks") or []
        hchecks = {c.get("id"): c for c in hchecks_list if isinstance(c, dict)}
        if any(c.get("status") == "fail" for c in hchecks_list if isinstance(c, dict)):
            return _finish(1, [f"harness_test_failed:{hname}"])
        if hv.get("error") is not None:
            return _finish(2, [f"harness_test_inconclusive:{hname}"])
        exp_code = int(hspec.get("expected_exit_code", 2))
        exp_reason = str(hspec.get("expected_reason") or "")
        must_pass = list(hspec.get("must_pass_checks") or [])
        h_reasons = list(hv.get("reasons") or [])
        if int(hv.get("exit_code", -1)) != exp_code or exp_reason not in h_reasons:
            return _finish(2, [f"harness_test_inconclusive:{hname}"])
        for cid in must_pass:
            if cid not in hchecks or hchecks[cid].get("status") != "pass":
                return _finish(2, [f"harness_test_inconclusive:{hname}"])

    # Reglas 8 y 9: resultado de run/
    run_v = part_verdicts["run"]
    run_checks = list(run_v.get("checks") or [])
    agg_metrics = dict(run_v.get("metrics") or {})
    agg_metrics["execution_identities"] = exec_identities

    if int(run_v.get("exit_code", 2)) == 1:
        return _finish(
            1,
            list(run_v.get("reasons") or ["run_failed"]),
            checks=run_checks,
            metrics=agg_metrics,
        )
    if (
        int(run_v.get("exit_code", 2)) != 0
        or not run_checks
        or any(c.get("status") != "pass" for c in run_checks)
    ):
        return _finish(
            2,
            list(run_v.get("reasons") or ["run_inconclusive"]),
            checks=run_checks,
            metrics=agg_metrics,
        )

    return _finish(0, [], checks=run_checks, metrics=agg_metrics)
