"""Blind evaluator for S-persist (engine non-persistence, child ownership registry, and Q9 checkpoint).

Evidence contract consumed by ``evaluate(part_dir)``
====================================================
``evaluate(part_dir)`` inspects ONLY:
1. ``part_dir / "manifest.json"`` (restricted to ``schema``, ``id``, ``kind``,
   ``build``, ``both``, ``params``, ``identity``).
2. ``part_dir / "samples" / "bridge.jsonl"`` — raw wire traffic captured by the
   QA harness between Python and the peer(s):
   - ``hello`` events: ``peer`` (``"server"`` | ``"client"``), ``inst``
     (``server_epoch`` on ``"server"``), ``args`` (or top-level) with ``proto``
     (``"qa0"``), ``build``, ``probe_ver`` (``"dsbx-qa1+<16hex>"``), ``http`` (``200``).
   - ``enq`` / ``deliver`` / ``poll`` / ``result`` events for:
     * ``ground_query`` (F0.2 verb on ``"server"``):
       - ``args``: ``x`` (m), ``z`` (m) from ``g_Game.SurfaceY(x, z)``;
       - ``read``: ``has = ["y"]``, ``y`` (m, terrain elevation).
     * ``per_status`` (instant on ``"server"``):
       - ``read`` strings: ``server_epoch`` (``m_Probe.m_Inst``), ``director_uid``;
       - ``read`` numbers: ``tick_ms``, ``frame``, ``registered_total_n``,
         ``scenes_count_n``, ``director_present_b``, ``director_alive_b``,
         ``director_inv_readable_b``, ``director_inv_count_n``;
       - ``read`` rows: ``scol = ["scene_id", "last_op_id"]``,
         ``ncol = ["gen_n", "own_alive_n"]``.
     * ``per_apply_scene`` (instant on ``"server"``):
       - ``args`` strings: ``scene_id``, ``scene_op_id``, ``expect_epoch``,
         ``q9_pathway`` (``"a"`` | ``"b"``);
       - ``args`` numbers: ``gen_n``;
       - ``args`` rows: ``scol = ["logical_id", "parent_id", "cat", "class_name", "slot_name"]``,
         ``ncol = ["req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"]``;
       - ``read`` strings: ``apply_status``, ``reason``, ``server_epoch``,
         ``scene_id``, ``scene_op_id``, ``q9_pathway``;
       - ``read`` numbers: ``gen_n``, ``created_roots_n``, ``created_children_n``,
         ``idempotent_hit_b``, ``q9_tick_ms``, ``q9_frame``;
       - ``read`` rows:
         ``scol = ["logical_id", "class_name", "net_id", "obs_loc_kind", "obs_parent_net_id", "obs_slot_name"]``,
         ``ncol = ["ok_b", "alive_b", "ai_agent_b", "req_y_m", "q9_x_m", "q9_y_m", "q9_z_m", "q9_dx_m", "q9_dy_m", "q9_dz_m", "q9_err_3d_m", "q9_yaw_deg", "q9_pitch_deg", "q9_roll_deg", "max_hp", "health_hp", "spawn_tick_ms"]``
         produced from ``CreateObjectEx`` / ``LocationCreateEntity``,
         ``GetPosition()``, ``GetOrientation()``, ``IsAlive()``, ``GetAIAgent()``,
         ``GetMaxHealth("", "")``, ``GetHealth("", "")``, ``GetNetworkID()``.
     * ``per_spawn_raw`` (instant on ``"server"``):
       - ``args`` strings: ``tag``, ``mode``, ``class_name``, ``child_cargo_class``,
         ``target_scene_id``, ``target_parent_id``;
       - ``args`` numbers: ``x_m``, ``z_m``, ``yaw_deg``, ``health_mark_ratio``;
       - ``read`` strings: ``spawn_status``, ``tag``, ``class_name``, ``net_id``,
         ``pers_id`` (``GetPersistentID``), ``obs_loc_kind``, ``obs_parent_net_id``,
         ``obs_slot_name``;
       - ``read`` numbers: ``pos_x_m``, ``pos_y_m``, ``pos_z_m``, ``yaw_deg``,
         ``pitch_deg``, ``roll_deg``, ``max_hp``, ``health_hp``, ``child_count_n``,
         ``tick_ms``, ``frame``.
     * ``per_child_transition`` (instant on ``"server"``):
       - ``args`` strings: ``scene_id``, ``logical_id``, ``action``, ``expect_epoch``,
         ``target_scene_id``, ``target_parent_id``;
       - ``read`` strings: ``transition_status``, ``net_id``, ``pre_loc_kind``,
         ``pre_parent_net_id``, ``pre_slot_name``, ``pre_owner_uid``,
         ``post_loc_kind``, ``post_parent_net_id``, ``post_slot_name``,
         ``post_owner_uid``;
       - ``read`` numbers: ``pos_x_m``, ``pos_y_m``, ``pos_z_m``, ``yaw_deg``,
         ``pitch_deg``, ``roll_deg``, ``tick_ms``, ``frame``.
     * ``per_reset_scene`` (instant on ``"server"``):
       - ``args`` strings: ``scene_id``, ``reset_op_id``, ``expect_epoch``;
       - ``read`` strings: ``reset_status`` (``"ok"`` | ``"partial"``), ``reason``
         (``"clean"`` | ``"foreign_content_retained"``), ``server_epoch``,
         ``scene_id``, ``reset_op_id``;
       - ``read`` numbers: ``deleted_n``, ``retained_n``, ``tick_ms``, ``frame``;
       - ``read`` rows (``rows == retained_n``):
         ``scol = ["logical_id", "class_name", "net_id"]``,
         ``ncol = ["foreign_descendants_n"]``.
     * ``per_census_start`` + ``job_read`` + ``job_free`` (job ``resource = "per_census"``):
       - ``per_census_start`` ``args``: ``area_tag`` (string), ``center_x_m``,
         ``center_z_m``, ``radius_m`` (60.0), ``include_director_b`` (0|1);
       - ``per_census_start`` ``read``: ``job``, ``state``, ``area_tag``,
         ``server_epoch``, ``director_uid``, ``snap_tick_ms``, ``snap_frame``,
         ``rows_captured_n``, ``center_x_m``, ``center_z_m``, ``radius_m``,
         ``director_present_b``, ``director_alive_b``, ``director_inv_readable_b``,
         ``director_inv_count_n``;
       - ``job_read`` pages (``state == "done"``, ``end_tick_ms > 0``,
         ``onjobend_tick_ms > 0``, ``released_tick_ms > 0``):
         ``scol = ["class_name", "loc_kind", "parent_class", "parent_net_id", "slot_name", "owner_uid", "own_logical_id", "net_id", "pers_id"]``,
         ``ncol = ["own_b", "in_radius_b", "alive_b", "ai_agent_b", "pos_x_m", "pos_y_m", "pos_z_m", "yaw_deg", "pitch_deg", "roll_deg", "max_hp", "health_hp", "inv_children_n", "spawn_tick_ms"]``
         captured via ``GetObjectsAtPosition3D``, ``EnumerateInventory``,
         ``GetCurrentInventoryLocation``, ``GetHierarchyRootPlayer``.
     * ``per_cleanup_qa`` (instant on ``"server"``):
       - ``read`` numbers: ``cleaned_own_n``, ``cleaned_raw_n``, ``tick_ms``, ``frame``.
3. ``part_dir / "samples" / "scenario.jsonl"`` — structured runner observations:
   - ``probe_sources_at_commit``: ``git_head``, ``probe_stamp``, ``persist_files``
     (map ``rel_path -> content_str`` from ``git show <git_head>:<rel_path>``).
   - ``storage_snapshot_t0``, ``storage_backup_t0``, ``storage_snapshot_t1``,
     ``storage_snapshot_t2``, ``storage_restore_result``: cold storage file maps
     ``files: {rel_path: {"sha256": <64hex>, "size_b": int, "mtime_ns": int}}``
     before (in ``storage_snapshot_t0``) and after the run (in ``storage_restore_result``
     or ``storage_snapshot_t6`` / ``storage_snapshot_post``), plus ``restore_ok_b == 1``.
   - ``baseline_director_foreign``: initial non-sentinel items in the director.
   - ``ledger_entry``: expected scene and raw-spawn entities for the part.
   - ``ledger_spawn_recorded``: ``logical_id`` / ``tag``, ``net_id_t1``,
     ``pers_id_t1``, ``init_max_hp``, ``init_health_hp``.

Every bridge event carries ``t_ms`` (bridge clock, written by the core, monotonic across epochs); the peers'
``tick_ms`` restart with each process.

What is evaluated per build (MEN-5)
-----------------------------------
``manifest["build"] == "offline"``: PER-01..PER-09 on the bridge evidence; PER-10 is the static scan of the
``DSBX_QA_X_Persist*.c`` sources at ``git_head`` plus the stamp/hello identity. The ``storage_*`` scenario
events are NOT required (if both ``storage_snapshot_t0`` and ``storage_restore_result`` are present they are
still validated) and PER-02 does NOT require the 10 minutes of hold (``snap - spawn >= 600000``): an offline
implementation does not have to fabricate storage files or 10 minutes of time.
``"diag"`` / ``"retail"``: additionally PER-10 requires ``storage_snapshot_t0`` and ``storage_restore_result``
(equal sha256 maps, ``restore_ok_b == 1``) and PER-02 requires the 600 s hold.

Expectations come from the frozen fixture, never from the runner (BLOQ-1): the ledger / apply args may carry
``req_x_m`` / ``req_z_m`` but they must equal the fixture to 1e-6. The director baseline comes only from the
t0 census of ``area_a`` (``include_director_b == 1``, MEN-8). N49 (creature coverage after restart) is accredited
with the peers' own reads and the bridge clock (MEN-4), see the comment above ``n49_extremes_accredited``. The
census resource is checked for real contention (MEN-6): a second ``per_census_start`` while a census is alive
must answer ``rejected/busy``, the first census must stay intact and the next one is accepted after the free.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import f03_common
import gate_core
import wire

SPIKE_ID = "S-persist"

# N49: cota del tick_ms (reloj del peer desde el arranque del proceso) en la primera lectura del epoch nuevo.
N49_MAX_FIRST_NEW_TICK_MS = 600000.0

CHECK_IDS = (
    "PER-01",
    "PER-02",
    "PER-03",
    "PER-04",
    "PER-05",
    "PER-06",
    "PER-07",
    "PER-08",
    "PER-09",
    "PER-10",
)

ALLOWED_MANIFEST_KEYS = frozenset({
    "schema",
    "id",
    "kind",
    "build",
    "both",
    "params",
    "identity",
})

FORBIDDEN_ENFORCE_TOKENS = (
    # Central economy and lifetime APIs
    "GetCEApi",
    "CEApi",
    "ECE_DYNAMIC_PERSISTENCY",
    "ExportSpawnData",
    "ExportProxyData",
    "ExportClusterData",
    "ExportProxyProto",
    "MarkCloseProxy",
    "RemoveCloseProxy",
    "ListCloseProxy",
    "SpawnAnalyze",
    "TimeShift",
    "OverrideLifeTime",
    "SpawnGroup",
    "SpawnDE",
    "SpawnDEEx",
    "SpawnLoot",
    "SpawnDynamic",
    "SpawnVehicles",
    "SpawnBuilding",
    "SpawnEntity",
    "SpawnSingleEntity",
    "SpawnRotation",
    "SpawnPerfTest",
    "CleanMap",
    "EconomyLog",
    "EconomyMap",
    "EconomyOutput",
    "RadiusLifetimeIncrease",
    "RadiusLifetimeDecrease",
    "RadiusLifetimeReset",
    "LootDepleteLifetime",
    "LootSetDamageToOne",
    "LootDepleteAndDamage",
    "SetLifetime",
    "SetLifetimeMax",
    "IncreaseLifetime",
    "IncreaseLifetimeUp",
    # File I/O primitives and serializers
    "OpenFile",
    "CloseFile",
    "ReadFile",
    "FPrint",
    "FPrintln",
    "FGets",
    "FindFile",
    "FindNextFile",
    "CloseFindFile",
    "FileExist",
    "MakeDirectory",
    "DeleteFile",
    "CopyFile",
    "BeginParse",
    "ParseLine",
    "EndParse",
    "FileSerializer",
    "JsonFileLoader",
    "JsonLoadFile",
    "JsonSaveFile",
)

FORBIDDEN_ENFORCE_SUBSTRINGS = (
    "$mission:",
    "$saves:",
    "$profile:",
)

_NET_ID_RE = re.compile(r"^-?\d+:-?\d+$")
_PERS_ID_RE = re.compile(r"^-?\d+:-?\d+:-?\d+:-?\d+$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

_KNOWN_STAGES = (
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


def _load_fixture() -> dict[str, Any]:
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "s_persist_fixture.json"
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def _strip_c_comments_preserve_strings(source: str) -> str:
    """Remove // and /* */ comments while preserving string literals."""
    out: list[str] = []
    i = 0
    n = len(source)
    in_str = False
    while i < n:
        ch = source[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "/":
            i += 2
            while i < n and source[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and source[i + 1] == "*":
            i += 2
            while i + 1 < n and not (source[i] == "*" and source[i + 1] == "/"):
                if source[i] == "\n":
                    out.append("\n")
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


ORDERED_ARRAY_MEMBERS = ("m_CacheOrder", "m_RpcLog", "m_PingLog", "m_EmitLog")


def _blank_string_literals(source: str) -> str:
    """Replace the content of every "..." literal by spaces (quotes and newlines kept)."""
    out: list[str] = []
    i = 0
    n = len(source)
    in_str = False
    while i < n:
        ch = source[i]
        if in_str:
            if ch == "\\" and i + 1 < n:
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                in_str = False
                out.append(ch)
            else:
                out.append(ch if ch == chr(10) else " ")
            i += 1
            continue
        if ch == '"':
            in_str = True
        out.append(ch)
        i += 1
    return "".join(out)


def scan_persist_enforcescript_sources(persist_files: dict[str, str]) -> list[str]:
    """Scan Enforce Script sources for forbidden CE/lifetime/storage tokens (brief 10.1) and
    `.Remove(` on the four order-sensitive arrays (m_CacheOrder, m_RpcLog, m_PingLog, m_EmitLog)."""
    if not isinstance(persist_files, dict) or not persist_files:
        return ["empty_persist_files"]
    violations: list[str] = []
    for rel_path, content in sorted(persist_files.items()):
        if not isinstance(content, str) or not content.strip():
            violations.append(f"{rel_path}:empty_content")
            continue
        stripped = _strip_c_comments_preserve_strings(content)
        for token in FORBIDDEN_ENFORCE_TOKENS:
            pat = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])")
            if pat.search(stripped):
                violations.append(f"{rel_path}:forbidden_token:{token}")
        for sub in FORBIDDEN_ENFORCE_SUBSTRINGS:
            if sub in stripped:
                violations.append(f"{rel_path}:forbidden_path:{sub}")
        # F0.3-0 F02-H2 (brief :476): `.Remove(` solo se prohibe sobre los cuatro arrays cuyo
        # orden importa; un `map.Remove(k)` o un literal "a.Remove(b)" no son violacion.
        code_only = _blank_string_literals(stripped)
        for member in ORDERED_ARRAY_MEMBERS:
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(member)}\s*\.\s*Remove\s*\(", code_only):
                violations.append(f"{rel_path}:forbidden_unordered_remove:{member}.Remove(")
    return violations


def _normalize_probe_rel_path(rel_path: str) -> str:
    norm = rel_path.replace("\\", "/").lstrip("/")
    if norm.startswith("DayZSandbox_dev/"):
        norm = norm[len("DayZSandbox_dev/") :]
    return norm


def _git_show_text(repo_root: Path, git_head: str, rel_path: str) -> str | None:
    rel_norm = _normalize_probe_rel_path(rel_path)
    candidates = [rel_norm, f"DayZSandbox_dev/{rel_norm}"]
    top = f03_common._git_toplevel(repo_root)
    cwd = str(top if top is not None else repo_root)
    for cand in candidates:
        try:
            proc = subprocess.run(
                ["git", "show", f"{git_head}:{cand}"],
                cwd=cwd,
                capture_output=True,
                timeout=15,
                check=False,
            )
        except Exception:
            continue
        if proc.returncode == 0:
            try:
                return proc.stdout.decode("utf-8")
            except UnicodeDecodeError:
                return None
    return None


def _get_required_persist_sources_at_commit(repo_root: Path, git_head: str) -> dict[str, str] | None:
    top = f03_common._git_toplevel(repo_root)
    if top is None:
        return None
    try:
        proc = subprocess.run(
            [
                "git",
                "ls-tree",
                "-r",
                "--name-only",
                git_head,
                "--",
                "qa/probe/DayZSandbox_QA",
                "DayZSandbox_dev/qa/probe/DayZSandbox_QA",
            ],
            cwd=str(top),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    required: dict[str, str] = {}
    for raw_line in proc.stdout.splitlines():
        p = raw_line.strip()
        if not p:
            continue
        norm_p = _normalize_probe_rel_path(p)
        fname = Path(norm_p).name
        if norm_p.startswith("qa/probe/DayZSandbox_QA/scripts/") and fname.startswith("DSBX_QA_X_Persist") and fname.endswith(".c"):
            content = _git_show_text(repo_root, git_head, norm_p)
            if content is None:
                return None
            required[norm_p] = content
    if not required:
        return None
    return required


def _is_finite_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _angle_diff_deg(a: float, b: float) -> float:
    d = (float(a) - float(b)) % 360.0
    if d > 180.0:
        d -= 360.0
    return abs(d)


def _valid_net_id(val: Any, logical_id: str = "") -> bool:
    if not isinstance(val, str) or not _NET_ID_RE.match(val):
        return False
    if val == "0:0":
        return False
    if logical_id and val == logical_id:
        return False
    return True


def _valid_pers_id(val: Any) -> bool:
    return isinstance(val, str) and bool(_PERS_ID_RE.match(val))


def _is_nonzero_pers_id(val: Any) -> bool:
    return _valid_pers_id(val) and val != "0:0:0:0"


def _unpack_any_payload(obj: Any) -> tuple[dict[str, str], dict[str, float], list[dict[str, Any]]] | None:
    if not isinstance(obj, dict):
        return None
    if "sk" in obj and "sv" in obj and "nk" in obj and "nv" in obj:
        try:
            u = wire.unpack_payload(obj)
            s = u.get("str") or {}
            n = u.get("num") or {}
            r = u.get("rows") or []
            return (
                {str(k): str(v) for k, v in s.items()},
                {str(k): float(v) for k, v in n.items() if _is_finite_num(v)},
                list(r),
            )
        except Exception:
            return None
    if "str" in obj or "num" in obj or "strings" in obj or "numbers" in obj or "rows" in obj:
        s = obj.get("str") if isinstance(obj.get("str"), dict) else (obj.get("strings") or {})
        n = obj.get("num") if isinstance(obj.get("num"), dict) else (obj.get("numbers") or {})
        r = obj.get("rows") if isinstance(obj.get("rows"), list) else []
        if isinstance(s, dict) and isinstance(n, dict) and isinstance(r, list):
            return (
                {str(k): str(v) for k, v in s.items()},
                {str(k): float(v) for k, v in n.items() if _is_finite_num(v)},
                list(r),
            )
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]] | None:
    if not path.is_file():
        return None
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            item = json.loads(s)
            if not isinstance(item, dict):
                return None
            rows.append(item)
    except Exception:
        return None
    return rows


def _infer_area_id(area_tag: str, cx: float | None, cz: float | None, fixture: dict[str, Any]) -> str:
    tag_low = (area_tag or "").lower()
    if "t5_track_" in tag_low:
        return area_tag
    for aid in ("area_a_mut", "area_a", "area_b", "area_c", "area_d"):
        if aid in tag_low:
            return aid
    if cx is not None and cz is not None:
        for aid, ainfo in fixture.get("areas", {}).items():
            if math.hypot(cx - float(ainfo["center_x_m"]), cz - float(ainfo["center_z_m"])) <= 1.0:
                return aid
    return area_tag


def _extract_stage_from_tag(area_tag: str, strings: dict[str, str]) -> str | None:
    st = strings.get("stage", "")
    if st in _KNOWN_STAGES:
        return st
    tag_low = (area_tag or "").lower()
    for known in _KNOWN_STAGES:
        if known in tag_low:
            return known
    if tag_low.startswith("t5_track_"):
        return "t5_post_restart_census"
    return None


class _BridgeOperation:
    def __init__(self, seq_idx: int, op_id: str, verb: str, peer: str, inst: str, args: dict[str, Any]) -> None:
        self.seq_idx = seq_idx
        self.op_id = op_id
        self.verb = verb
        self.peer = peer
        self.inst = inst
        self.args = args
        self.status: str | None = None
        self.reason: str = ""
        self.read: dict[str, Any] = {}
        self.recv_ms: float = 0.0
        self.done_ms: float = 0.0
        self.frame_recv: int = 0
        self.frame_done: int = 0
        self.result_seq_idx: int = seq_idx
        self.result_t_ms: float | None = None


def _parse_bridge_timeline(
    bridge_events: list[dict[str, Any]],
    scenario_events: list[dict[str, Any]],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    hellos: list[dict[str, Any]] = []
    server_hello_insts: list[str] = []
    server_epochs: list[str] = []
    ops_by_id: dict[str, _BridgeOperation] = {}
    ordered_ops: list[_BridgeOperation] = []
    current_server_inst = ""
    any_lost_or_timeout = False
    any_lease_expired = False

    for idx, ev in enumerate(bridge_events):
        ev_type = ev.get("ev")
        peer = str(ev.get("peer") or "")
        if ev_type == "hello" and ev.get("http") == 200 and ev.get("ok") is not False:
            proto, h_build, pv = f03_common._hello_proto_and_build(ev)
            ev_args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
            inst = str(ev.get("inst") or ev_args.get("inst") or "")
            if not peer and isinstance(ev_args.get("peer"), str):
                peer = ev_args["peer"]
            hellos.append({
                "peer": peer,
                "inst": inst,
                "proto": proto,
                "build": h_build,
                "probe_ver": pv,
                "http": 200,
                "raw": ev,
            })
            if peer == "server" and inst:
                server_hello_insts.append(inst)
                current_server_inst = inst
                if not server_epochs or server_epochs[-1] != inst:
                    server_epochs.append(inst)
        elif ev_type == "enq":
            op_id = str(ev.get("op_id") or "")
            verb = str(ev.get("verb") or "")
            enq_inst = str(ev.get("inst") or current_server_inst)
            args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
            if op_id and op_id not in ops_by_id:
                bop = _BridgeOperation(idx, op_id, verb, peer, enq_inst, args)
                ops_by_id[op_id] = bop
                ordered_ops.append(bop)
        elif ev_type == "deliver":
            op_id = str(ev.get("op_id") or "")
            verb = str(ev.get("verb") or "")
            deliv_inst = str(ev.get("inst") or current_server_inst)
            args = ev.get("args") if isinstance(ev.get("args"), dict) else {}
            if op_id:
                if op_id not in ops_by_id:
                    bop = _BridgeOperation(idx, op_id, verb, peer, deliv_inst, args)
                    ops_by_id[op_id] = bop
                    ordered_ops.append(bop)
                else:
                    bop = ops_by_id[op_id]
                    if deliv_inst:
                        bop.inst = deliv_inst
                    if args:
                        bop.args = args
        elif ev_type == "poll" and ev.get("http", 200) == 200:
            poll_inst = str(ev.get("inst") or current_server_inst)
            if peer == "server" and poll_inst:
                current_server_inst = poll_inst
                if not server_epochs or server_epochs[-1] != poll_inst:
                    server_epochs.append(poll_inst)
            for pid in ev.get("op_ids") or []:
                if isinstance(pid, str) and pid in ops_by_id and poll_inst:
                    ops_by_id[pid].inst = poll_inst
            for raw_op in ev.get("ops") or []:
                if not isinstance(raw_op, dict):
                    continue
                op_id = str(raw_op.get("op_id") or "")
                verb = str(raw_op.get("verb") or "")
                args = raw_op.get("args") if isinstance(raw_op.get("args"), dict) else {}
                if not op_id:
                    continue
                if op_id not in ops_by_id:
                    bop = _BridgeOperation(idx, op_id, verb, peer, poll_inst, args)
                    ops_by_id[op_id] = bop
                    ordered_ops.append(bop)
                else:
                    bop = ops_by_id[op_id]
                    if poll_inst:
                        bop.inst = poll_inst
                    if args:
                        bop.args = args
        elif ev_type == "result" and ev.get("http", 200) == 200:
            res_inst = str(ev.get("inst") or current_server_inst)
            res_list: list[dict[str, Any]] = []
            if isinstance(ev.get("result"), dict):
                res_list.append(ev["result"])
            if isinstance(ev.get("results"), list):
                for r in ev["results"]:
                    if isinstance(r, dict):
                        res_list.append(r)
            for res in res_list:
                if bool(res.get("dup")):
                    continue
                op_id = str(res.get("op_id") or ev.get("op_id") or "")
                if not op_id:
                    continue
                if op_id not in ops_by_id:
                    bop = _BridgeOperation(idx, op_id, str(res.get("verb") or ""), peer, res_inst, {})
                    ops_by_id[op_id] = bop
                    ordered_ops.append(bop)
                bop = ops_by_id[op_id]
                if bop.status is None:
                    bop.status = str(res.get("status") or "")
                    bop.reason = str(res.get("reason") or "")
                    bop.read = res.get("read") if isinstance(res.get("read"), dict) else {}
                    bop.recv_ms = float(res.get("recv_ms") or 0.0)
                    bop.done_ms = float(res.get("done_ms") or 0.0)
                    bop.frame_recv = int(res.get("frame_recv") or 0)
                    bop.frame_done = int(res.get("frame_done") or 0)
                    bop.result_seq_idx = idx
                    _rt = ev.get("t_ms")
                    bop.result_t_ms = float(_rt) if _is_finite_num(_rt) else None
                    if res_inst and not bop.inst:
                        bop.inst = res_inst
                    if bop.status in ("lost", "timeout"):
                        any_lost_or_timeout = True
                    if bop.reason == "lease_expired":
                        any_lease_expired = True
                    if bop.reason in ("stale_instance", "expired"):
                        any_lost_or_timeout = True
        elif ev_type in ("lost", "expire", "op_timeout", "result_lost", "abandoned"):
            any_lost_or_timeout = True
            oid = str(ev.get("op_id") or "")
            if oid and oid in ops_by_id and ops_by_id[oid].status is None:
                ops_by_id[oid].status = "lost" if ev_type in ("lost", "result_lost") else "timeout"
                ops_by_id[oid].reason = "result_lost" if ev_type in ("lost", "result_lost") else "result_timeout"

    # Map scenario census annotations if present
    scen_census_stage: dict[str, tuple[str, str]] = {}
    for sev in scenario_events:
        if sev.get("ev") in ("census_recorded", "census_step", "census"):
            oid = str(sev.get("op_id") or sev.get("job_id") or "")
            stg = str(sev.get("stage") or "")
            aid = str(sev.get("area_id") or sev.get("area_tag") or "")
            if oid and stg:
                scen_census_stage[oid] = (stg, aid)

    any_reused_census_job_id = False
    any_invalid_census_resource = False
    any_census_overlap = False

    # Count per_census_start occurrences per job_id and collect all job_read / job_free ops by job_id
    census_start_ops_by_job: dict[str, list[_BridgeOperation]] = {}
    job_read_ops_by_job: dict[str, list[_BridgeOperation]] = {}
    job_free_ops_by_job: dict[str, list[_BridgeOperation]] = {}

    for bop in ordered_ops:
        if bop.verb == "per_census_start" and bop.status == "done":
            out_u = _unpack_any_payload(bop.read)
            out_s = out_u[0] if out_u else {}
            jid = out_s.get("job") or bop.op_id
            if jid:
                census_start_ops_by_job.setdefault(jid, []).append(bop)
        elif bop.verb == "job_read" and bop.status == "done":
            in_unpacked = _unpack_any_payload(bop.args)
            out_unpacked = _unpack_any_payload(bop.read)
            if not in_unpacked or not out_unpacked:
                continue
            in_s, _in_n, _ = in_unpacked
            out_s, _out_n, _out_rows = out_unpacked
            job_id = out_s.get("job") or in_s.get("job") or ""
            reason = out_s.get("reason", "")
            if reason == "lease_expired":
                any_lease_expired = True
            if job_id:
                job_read_ops_by_job.setdefault(job_id, []).append(bop)
        elif bop.verb == "job_free" and bop.status == "done":
            in_unpacked = _unpack_any_payload(bop.args)
            out_unpacked = _unpack_any_payload(bop.read)
            job_id = ""
            if out_unpacked:
                job_id = out_unpacked[0].get("job", "")
            if not job_id and in_unpacked:
                job_id = in_unpacked[0].get("job", "")
            if job_id:
                job_free_ops_by_job.setdefault(job_id, []).append(bop)

    for jid, s_ops in census_start_ops_by_job.items():
        if len(s_ops) > 1:
            any_reused_census_job_id = True

    # MEN-6: contencion real del recurso `per_census` (F0.3-0 brief :147). Se deduce solo del orden
    # de las ordenes en el bridge: mientras un censo A esta vivo (desde su start hasta su job_free)
    # otro per_census_start en el mismo epoch debe responder rejected/busy; uno aceptado es un
    # solape (el recurso no protege), y un rechazo con otro motivo no prueba la contencion.
    census_busy_probes: list[dict[str, Any]] = []
    census_overlap_offenders: set[str] = set()
    any_census_contention_wrong_reason = False
    for a_op in ordered_ops:
        if a_op.verb != "per_census_start" or a_op.status != "done" or a_op.peer != "server":
            continue
        a_out = _unpack_any_payload(a_op.read)
        a_jid = (a_out[0].get("job") if a_out else "") or a_op.op_id
        a_free_seq = min(
            (
                jf.seq_idx
                for jf in job_free_ops_by_job.get(a_jid, [])
                if jf.seq_idx > a_op.seq_idx and jf.peer == "server" and jf.inst == a_op.inst
            ),
            default=10**9,
        )
        for r_op in ordered_ops:
            if (
                r_op is a_op
                or r_op.verb != "per_census_start"
                or r_op.peer != "server"
                or r_op.inst != a_op.inst
                or not (a_op.seq_idx < r_op.seq_idx < a_free_seq)
            ):
                continue
            if r_op.status == "done":
                census_overlap_offenders.add(r_op.op_id)
                any_census_overlap = True
            elif r_op.status == "rejected":
                if r_op.reason == "busy":
                    census_busy_probes.append({
                        "first_op_id": a_op.op_id,
                        "rejected_op_id": r_op.op_id,
                        "free_seq": a_free_seq,
                        "inst": a_op.inst,
                    })
                else:
                    any_census_contention_wrong_reason = True

    server_epoch_old = server_epochs[0] if server_epochs else ""
    server_epoch_new = ""
    for ep in server_epochs[1:]:
        if ep and ep != server_epoch_old:
            server_epoch_new = ep
            break

    # Identify key milestone sequence indices for chronological stage fallback
    first_apply_seq = min((op.seq_idx for op in ordered_ops if op.verb == "per_apply_scene"), default=10**9)
    first_trans_seq = min((op.seq_idx for op in ordered_ops if op.verb == "per_child_transition"), default=10**9)
    last_trans_seq = max(
        (op.seq_idx for op in ordered_ops if op.verb == "per_child_transition" and op.inst == server_epoch_old),
        default=-1,
    )
    first_reset_old_seq = min(
        (
            op.seq_idx
            for op in ordered_ops
            if op.verb == "per_reset_scene"
            and op.inst == server_epoch_old
            and op.seq_idx > last_trans_seq
        ),
        default=10**9,
    )
    last_reset_old_seq = max(
        (
            op.seq_idx
            for op in ordered_ops
            if op.verb == "per_reset_scene" and op.inst == server_epoch_old
        ),
        default=-1,
    )
    first_new_epoch_seq = min(
        (op.seq_idx for op in ordered_ops if server_epoch_new and op.inst == server_epoch_new),
        default=10**9,
    )
    witness_apply_seq = min(
        (
            op.seq_idx
            for op in ordered_ops
            if server_epoch_new
            and op.inst == server_epoch_new
            and op.verb == "per_apply_scene"
            and op.status == "done"
        ),
        default=10**9,
    )
    stale_ops_seqs = [
        op.seq_idx
        for op in ordered_ops
        if server_epoch_new
        and op.inst == server_epoch_new
        and op.verb in ("per_reset_scene", "per_apply_scene")
        and op.status == "rejected"
    ]
    first_stale_seq = min(stale_ops_seqs, default=10**9)
    last_stale_seq = max(stale_ops_seqs, default=10**9)
    cleanup_seq = min((op.seq_idx for op in ordered_ops if op.verb == "per_cleanup_qa"), default=10**9)

    censuses: list[dict[str, Any]] = []
    mid_batches_by_area: dict[str, list[dict[str, Any]]] = {}
    active_census_windows_by_inst: dict[str, list[tuple[int, int, float, float]]] = {}

    for bop in ordered_ops:
        if bop.verb != "per_census_start":
            continue
        if bop.status == "rejected":
            # un rechazo (busy) no es un censo: no entra en el reparto por etapas
            continue
        in_unpacked = _unpack_any_payload(bop.args)
        out_unpacked = _unpack_any_payload(bop.read) if bop.status == "done" else None
        in_s, in_n, _ = in_unpacked if in_unpacked else ({}, {}, [])
        out_s, out_n, _ = out_unpacked if out_unpacked else ({}, {}, [])
        raw_tag = out_s.get("area_tag") or in_s.get("area_tag") or ""
        cx = out_n.get("center_x_m", in_n.get("center_x_m"))
        cz = out_n.get("center_z_m", in_n.get("center_z_m"))
        rad = out_n.get("radius_m", in_n.get("radius_m", 60.0))
        inc_dir = int(round(out_n.get("include_director_b", in_n.get("include_director_b", 0.0))))
        area_id = _infer_area_id(raw_tag, cx, cz, fixture)
        explicit_stage = _extract_stage_from_tag(raw_tag, {**in_s, **out_s})
        if bop.op_id in census_overlap_offenders:
            explicit_stage = "contention_overlap_offender"
        if not explicit_stage and bop.op_id in scen_census_stage:
            explicit_stage, scen_area = scen_census_stage[bop.op_id]
            if scen_area and area_id == raw_tag:
                area_id = scen_area

        job_id = out_s.get("job") or bop.op_id
        c_epoch = out_s.get("server_epoch") or bop.inst
        snap_tick_ms = float(out_n.get("snap_tick_ms", 0.0))
        rows_captured = int(round(out_n.get("rows_captured_n", -1.0))) if out_n else -1
        start_res = out_s.get("resource", "")
        if start_res and start_res != "per_census":
            any_invalid_census_resource = True

        reconstructed_rows: list[dict[str, Any]] = []
        job_complete = False
        free_done_ms = 0.0
        released_tick_ms = 0.0

        # Bind per_census_start -> job_read -> job_free strictly to this single execution (BLOQ 3 & BLOQ 12)
        if (
            bop.status == "done"
            and bop.peer == "server"
            and c_epoch
            and (not bop.inst or bop.inst == c_epoch)
            and (not out_s.get("server_epoch") or out_s.get("server_epoch") == c_epoch)
            and (not start_res or start_res == "per_census")
            and len(census_start_ops_by_job.get(job_id, [])) == 1
        ):
            all_jr = job_read_ops_by_job.get(job_id, [])
            all_jf = job_free_ops_by_job.get(job_id, [])
            # Find matching job_free after bop.seq_idx on the same peer and server epoch
            valid_jf = [
                jf
                for jf in all_jf
                if jf.seq_idx > bop.seq_idx
                and jf.peer == "server"
                and jf.inst == c_epoch
                and ((_unpack_any_payload(jf.read) or ({}, {}, []))[0].get("freed", "1") == "1")
            ]
            # Disallow any job_read or job_free for this job_id before bop.seq_idx or on a different inst
            bad_lifecycle = any(
                op.seq_idx <= bop.seq_idx or op.peer != "server" or op.inst != c_epoch
                for op in (all_jr + all_jf)
            )
            if bad_lifecycle:
                any_reused_census_job_id = True
            elif valid_jf:
                jf_op = valid_jf[0]
                free_done_ms = float(jf_op.done_ms or jf_op.recv_ms or 0.0)
                # Disallow any job_read succeeding after job_free
                if any(jr.seq_idx >= jf_op.seq_idx for jr in all_jr):
                    any_reused_census_job_id = True
                else:
                    pages_map: dict[int, list[dict[str, Any]]] = {}
                    jmeta: dict[str, Any] | None = None
                    jr_invalid = False
                    first_done_jr_seq = jf_op.seq_idx
                    for jr in all_jr:
                        if not (bop.seq_idx < jr.seq_idx < jf_op.seq_idx):
                            jr_invalid = True
                            break
                        in_jr = _unpack_any_payload(jr.args)
                        out_jr = _unpack_any_payload(jr.read)
                        if not in_jr or not out_jr:
                            jr_invalid = True
                            break
                        jr_in_s, jr_in_n, _ = in_jr
                        jr_out_s, jr_out_n, jr_out_rows = out_jr
                        if jr_out_s.get("resource") != "per_census":
                            any_invalid_census_resource = True
                            jr_invalid = True
                            break
                        jr_state = jr_out_s.get("state", "")
                        if jr_state == "done":
                            first_done_jr_seq = min(first_done_jr_seq, jr.seq_idx)
                            page_n = int(round(jr_out_n.get("page_n", jr_in_n.get("page_n", 0.0))))
                            pages_map[page_n] = jr_out_rows
                            jmeta = {
                                "state": jr_state,
                                "reason": jr_out_s.get("reason", ""),
                                "pages_n": int(round(jr_out_n.get("pages_n", 0.0))),
                                "rows_total_n": int(round(jr_out_n.get("rows_total_n", 0.0))),
                                "start_tick_ms": float(jr_out_n.get("start_tick_ms", 0.0)),
                                "end_tick_ms": float(jr_out_n.get("end_tick_ms", 0.0)),
                                "onjobend_tick_ms": float(jr_out_n.get("onjobend_tick_ms", 0.0)),
                                "released_tick_ms": float(jr_out_n.get("released_tick_ms", 0.0)),
                            }
                        elif jr_state in ("failed", "timed_out", "stopped", "expired"):
                            jr_invalid = True
                            break

                    if (
                        not jr_invalid
                        and jmeta is not None
                        and jmeta.get("state") == "done"
                        and jmeta["start_tick_ms"] > 0.0
                        and jmeta["end_tick_ms"] >= jmeta["start_tick_ms"]
                        and jmeta["onjobend_tick_ms"] >= jmeta["end_tick_ms"]
                        and jmeta["released_tick_ms"] >= jmeta["onjobend_tick_ms"]
                        and snap_tick_ms > 0.0
                        and abs(jmeta["start_tick_ms"] - snap_tick_ms) <= 50.0
                    ):
                        released_tick_ms = jmeta["released_tick_ms"]
                        # Check E9 resource contention: no other per_census_start in c_epoch may overlap,
                        # ni por orden del bridge ni por ticks (sin umbral: cualquier solape cuenta).
                        prev_windows = active_census_windows_by_inst.setdefault(c_epoch, [])
                        for p_start_seq, p_done_seq, _p_start_t, p_rel_t in prev_windows:
                            if bop.seq_idx < p_done_seq or snap_tick_ms < p_rel_t - 1e-6:
                                any_census_overlap = True
                                break
                        prev_windows.append((bop.seq_idx, first_done_jr_seq, snap_tick_ms, released_tick_ms))

                        if not jr_invalid:
                            pages_n = jmeta["pages_n"]
                            rows_total_n = jmeta["rows_total_n"]
                            if rows_total_n == 0 and pages_n == 0:
                                if 0 in pages_map and len(pages_map[0]) == 0 and rows_captured == 0:
                                    job_complete = True
                            elif pages_n > 0 and all(p in pages_map for p in range(pages_n)):
                                for p in range(pages_n):
                                    reconstructed_rows.extend(pages_map[p])
                                if len(reconstructed_rows) == rows_total_n and (
                                    rows_captured < 0 or len(reconstructed_rows) == rows_captured
                                ):
                                    job_complete = True

        c_entry: dict[str, Any] = {
            "op_id": bop.op_id,
            "job_id": job_id,
            "seq_idx": bop.seq_idx,
            "status": bop.status,
            "reason": bop.reason,
            "inst": c_epoch,
            "raw_area_tag": raw_tag,
            "area_id": area_id,
            "stage": explicit_stage,
            "center_x_m": float(cx) if cx is not None else 0.0,
            "center_z_m": float(cz) if cz is not None else 0.0,
            "radius_m": float(rad) if rad is not None else 60.0,
            "include_director_b": inc_dir,
            "snap_tick_ms": snap_tick_ms,
            "snap_frame": int(round(out_n.get("snap_frame", 0.0))),
            "released_tick_ms": released_tick_ms,
            "free_done_ms": free_done_ms,
            "rows_captured_n": rows_captured,
            "director_uid": out_s.get("director_uid", ""),
            "director_present_b": int(round(out_n.get("director_present_b", 0.0))),
            "director_alive_b": int(round(out_n.get("director_alive_b", 0.0))),
            "director_inv_readable_b": int(round(out_n.get("director_inv_readable_b", 0.0))),
            "director_inv_count_n": int(round(out_n.get("director_inv_count_n", 0.0))),
            "job_complete": job_complete,
            "rows": reconstructed_rows,
        }
        censuses.append(c_entry)

        if not explicit_stage:
            sidx = bop.seq_idx
            if sidx < first_apply_seq:
                c_entry["stage"] = "t0_baseline_census"
            elif sidx < first_trans_seq:
                c_entry["stage"] = "t1_pre_transition_census"
            elif sidx < first_reset_old_seq and (not server_epoch_new or c_entry["inst"] == server_epoch_old):
                mid_batches_by_area.setdefault(area_id, []).append(c_entry)
            elif last_reset_old_seq >= 0 and sidx > last_reset_old_seq and sidx < first_new_epoch_seq:
                c_entry["stage"] = "t3_post_reset_census"
            elif sidx >= first_new_epoch_seq and sidx < witness_apply_seq:
                c_entry["stage"] = "t5_post_restart_census"
            elif sidx > witness_apply_seq and sidx < first_stale_seq:
                c_entry["stage"] = "t5_witness_pre_census"
            elif sidx > last_stale_seq and sidx < cleanup_seq:
                c_entry["stage"] = "t5_witness_post_census"
            elif sidx > cleanup_seq:
                c_entry["stage"] = "t6_post_cleanup_census"

    # Resolve mid_batches_by_area (between t1 transitions and t3 reset: t1_post, t2_10min, t3_pre)
    for aid, clist in mid_batches_by_area.items():
        if len(clist) == 1:
            clist[0]["stage"] = "t1_post_transition_census"
        elif len(clist) == 2:
            clist[0]["stage"] = "t1_post_transition_census"
            clist[1]["stage"] = "t3_pre_reset_census"
        elif len(clist) >= 3:
            clist[0]["stage"] = "t1_post_transition_census"
            for mid_c in clist[1:-1]:
                mid_c["stage"] = "t2_census_10min"
            clist[-1]["stage"] = "t3_pre_reset_census"

    return {
        "hellos": hellos,
        "server_hello_insts": server_hello_insts,
        "server_epochs": server_epochs,
        "server_epoch_old": server_epoch_old,
        "server_epoch_new": server_epoch_new,
        "ordered_ops": ordered_ops,
        "censuses": censuses,
        "any_lost_or_timeout": any_lost_or_timeout,
        "any_lease_expired": any_lease_expired,
        "any_reused_census_job_id": any_reused_census_job_id,
        "any_invalid_census_resource": any_invalid_census_resource,
        "any_census_overlap": any_census_overlap,
        "census_busy_probes": census_busy_probes,
        "any_census_contention_wrong_reason": any_census_contention_wrong_reason,
    }


def _checks_as_list(checks_map: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "id": cid,
            "status": str(checks_map[cid]["status"]),
            "detail": str(checks_map[cid]["detail"]),
        }
        for cid in CHECK_IDS
    ]


def evaluate(part_dir: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    part_dir = Path(part_dir)
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    else:
        repo_root = Path(repo_root)

    checks: dict[str, dict[str, Any]] = {
        cid: {"status": "missing", "detail": "not_evaluated"} for cid in CHECK_IDS
    }
    reasons: list[str] = []
    metrics: dict[str, Any] = {
        "q9_selected_pathway": "",
        "grill_foreign_in_unreset_own_container": {"readings_available_b": 0},
        "storage_auxiliary_fingerprint": {},
    }

    manifest_path = part_dir / "manifest.json"
    bridge_path = part_dir / "samples" / "bridge.jsonl"
    scenario_path = part_dir / "samples" / "scenario.jsonl"

    if not manifest_path.is_file() or not bridge_path.is_file() or not scenario_path.is_file():
        reasons.append("missing_evidence_files")
        return gate_core.make_verdict(
            SPIKE_ID, 2, checks=_checks_as_list(checks), metrics=metrics, reasons=reasons
        )

    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw_manifest, dict):
            raise ValueError("manifest_not_dict")
        manifest = {k: v for k, v in raw_manifest.items() if k in ALLOWED_MANIFEST_KEYS}
    except Exception:
        reasons.append("corrupt_manifest")
        return gate_core.make_verdict(
            SPIKE_ID, 2, checks=_checks_as_list(checks), metrics=metrics, reasons=reasons
        )

    bridge_events = _read_jsonl(bridge_path)
    scenario_events = _read_jsonl(scenario_path)
    if bridge_events is None or scenario_events is None or not bridge_events or not scenario_events:
        reasons.append("empty_or_corrupt_samples")
        return gate_core.make_verdict(
            SPIKE_ID, 2, checks=_checks_as_list(checks), metrics=metrics, reasons=reasons
        )

    if any(ev.get("ev") == "wire_cap_exceeded" for ev in bridge_events):
        reasons.append("wire_cap_exceeded")
    if any(ev.get("ev") == "operator_timeout" for ev in scenario_events):
        reasons.append("operator_timeout")

    fixture = _load_fixture()
    sentinel_classes = set(fixture.get("sentinel_classes", []))

    timeline = _parse_bridge_timeline(bridge_events, scenario_events, fixture)
    ordered_ops: list[_BridgeOperation] = timeline["ordered_ops"]
    censuses: list[dict[str, Any]] = timeline["censuses"]
    hellos: list[dict[str, Any]] = timeline["hellos"]
    server_hello_insts: list[str] = timeline["server_hello_insts"]
    server_epoch_old: str = timeline["server_epoch_old"]
    server_epoch_new: str = timeline["server_epoch_new"]
    build_kind = str(manifest.get("build") or "offline")

    if timeline["any_lease_expired"]:
        reasons.append("lease_expired")
    if timeline["any_reused_census_job_id"]:
        reasons.append("reused_census_job_id")
    if timeline["any_invalid_census_resource"]:
        reasons.append("invalid_census_resource")
    census_overlap_detected = timeline["any_census_overlap"]
    if census_overlap_detected:
        reasons.append("unprotected_census_resource_overlap")
    census_wrong_reason = timeline["any_census_contention_wrong_reason"]
    if census_wrong_reason:
        reasons.append("census_contention_wrong_reason")

    # Check hello peers (both server and client must have hello 200 with matching build & proto)
    req_peers = ("server", "client") if manifest.get("both", True) else ("server",)
    hello_peers = {str(h.get("peer") or "") for h in hellos if h.get("http") == 200}
    if not set(req_peers).issubset(hello_peers):
        reasons.append("build_mismatch")

    for h in hellos:
        if h.get("proto") != "qa0" or str(h.get("build") or "") != build_kind:
            if "build_mismatch" not in reasons:
                reasons.append("build_mismatch")

    # Index censuses by (stage, area_id) and stage list
    censuses_by_stage: dict[str, list[dict[str, Any]]] = {}
    census_by_stage_area: dict[tuple[str, str], dict[str, Any]] = {}
    for c in censuses:
        stg = c.get("stage") or ""
        aid = c.get("area_id") or ""
        if stg:
            censuses_by_stage.setdefault(stg, []).append(c)
            if aid:
                census_by_stage_area[(stg, aid)] = c

    # Extract scenario events
    ledger_entries: list[dict[str, Any]] = [
        ev for ev in scenario_events if ev.get("ev") == "ledger_entry"
    ]
    spawn_records: dict[str, dict[str, Any]] = {}
    for ev in scenario_events:
        if ev.get("ev") == "ledger_spawn_recorded":
            lid = str(ev.get("logical_id") or ev.get("tag") or "")
            if lid:
                spawn_records[lid] = ev

    probe_source_events = [
        ev for ev in scenario_events if ev.get("ev") == "probe_sources_at_commit"
    ]
    storage_t0_events = [
        ev for ev in scenario_events if ev.get("ev") == "storage_snapshot_t0"
    ]
    storage_t1_events = [
        ev for ev in scenario_events if ev.get("ev") == "storage_snapshot_t1"
    ]
    storage_t2_events = [
        ev for ev in scenario_events if ev.get("ev") == "storage_snapshot_t2"
    ]
    storage_t6_events = [
        ev for ev in scenario_events if ev.get("ev") in ("storage_snapshot_t6", "storage_snapshot_post")
    ]
    storage_restore_events = [
        ev for ev in scenario_events if ev.get("ev") == "storage_restore_result"
    ]

    # Determine active scenes and areas for this part from ledger_entries
    ledger_by_id: dict[str, dict[str, Any]] = {}
    scenes_in_part: dict[str, list[dict[str, Any]]] = {}
    for le in ledger_entries:
        lid = str(le.get("logical_id") or "")
        sc_id = str(le.get("scene_id") or "")
        if lid:
            ledger_by_id[lid] = le
        if sc_id:
            scenes_in_part.setdefault(sc_id, []).append(le)

    uses_mut_area = "scene_a_mut" in scenes_in_part
    has_scene_d = "scene_d" in scenes_in_part
    retained_scene_id = "scene_a_mut" if uses_mut_area else "scene_a"
    retained_area_id = "area_a_mut" if uses_mut_area else "area_a"
    retained_pfx = "am" if uses_mut_area else "a"

    required_base_areas = ["area_a", "area_b", "area_c"]
    if uses_mut_area:
        required_base_areas.append("area_a_mut")
    if has_scene_d:
        required_base_areas.append("area_d")

    # Locate initial per_status in server_epoch_old to get director_uid_t0
    director_uid_t0 = ""
    status_ops_old: list[tuple[_BridgeOperation, dict[str, str], dict[str, float], list[dict[str, Any]]]] = []
    status_ops_new: list[tuple[_BridgeOperation, dict[str, str], dict[str, float], list[dict[str, Any]]]] = []
    for bop in ordered_ops:
        if bop.verb == "per_status" and bop.status == "done":
            unp = _unpack_any_payload(bop.read)
            if not unp:
                continue
            s, n, r = unp
            ep = s.get("server_epoch") or bop.inst
            if ep == server_epoch_old:
                status_ops_old.append((bop, s, n, r))
                if not director_uid_t0 and s.get("director_uid"):
                    director_uid_t0 = s["director_uid"]
            elif server_epoch_new and ep == server_epoch_new:
                status_ops_new.append((bop, s, n, r))

    # Check t0_baseline_census for dirty_initial_area (N41)
    baseline_director_rows: list[dict[str, Any]] = []
    if not all((("t0_baseline_census", aid) in census_by_stage_area) for aid in required_base_areas):
        reasons.append("missing_t0_baseline_census")
    else:
        for aid in required_base_areas:
            c0 = census_by_stage_area[("t0_baseline_census", aid)]
            if not c0["job_complete"]:
                reasons.append("incomplete_t0_baseline_census")
                break
            if aid == "area_a" and not director_uid_t0 and c0.get("director_uid"):
                director_uid_t0 = c0["director_uid"]
            if aid == "area_a" and (c0["include_director_b"] != 1 or c0["director_inv_readable_b"] != 1):
                # MEN-8: el inventario basal del director sale del censo t0 de area_a, no del runner
                reasons.append("t0_director_inventory_not_censused")
                break
            for row in c0["rows"]:
                cname = str(row.get("class_name") or "")
                ouid = str(row.get("owner_uid") or "")
                if cname in sentinel_classes or ouid == "" or (director_uid_t0 and ouid != director_uid_t0):
                    if "dirty_initial_area" not in reasons:
                        reasons.append("dirty_initial_area")
                    break
                if aid == "area_a" and ouid == director_uid_t0:
                    baseline_director_rows.append(row)

    # MEN-8: `baseline_director_foreign` del runner ya NO es una fuente de verdad: la linea base del
    # director sale solo de las filas del censo t0 de area_a (include_director_b == 1).

    # Collect per_apply_scene and per_spawn_raw and ground_query in t1
    ground_queries: list[tuple[float, float, float]] = []
    for bop in ordered_ops:
        if bop.verb == "ground_query" and bop.status == "done":
            # N48: ground_query reads args["x"] and args["z"], NOT args["pos"]
            if "x" not in bop.args or "z" not in bop.args:
                continue
            gx = bop.args.get("x")
            gz = bop.args.get("z")
            if not (_is_finite_num(gx) and _is_finite_num(gz)):
                continue
            pos_arg = bop.args.get("pos")
            if (
                float(gx) == 0.0
                and float(gz) == 0.0
                and isinstance(pos_arg, list)
                and len(pos_arg) >= 3
                and (abs(float(pos_arg[0])) > 1.0 or abs(float(pos_arg[2])) > 1.0)
            ):
                # N48: caller passed coordinates in args["pos"] leaving args["x"] = args["z"] = 0.0
                continue
            gy = None
            if isinstance(bop.read, dict):
                has_list = bop.read.get("has")
                if isinstance(has_list, list) and "y" in has_list and _is_finite_num(bop.read.get("y")):
                    gy = float(bop.read["y"])
                elif _is_finite_num(bop.read.get("ground_y_m")):
                    gy = float(bop.read["ground_y_m"])
            if gy is not None:
                ground_queries.append((float(gx), float(gz), gy))

    def _find_ground_y(req_x: float, req_z: float) -> float | None:
        for gx, gz, gy in ground_queries:
            if abs(gx - req_x) <= 1e-4 and abs(gz - req_z) <= 1e-4:
                return gy
        return None

    apply_ops_old: list[tuple[_BridgeOperation, dict[str, str], dict[str, float], list[dict[str, Any]], dict[str, str], dict[str, float], list[dict[str, Any]]]] = []
    spawn_raw_ops: dict[str, tuple[dict[str, str], dict[str, float]]] = {}
    for bop in ordered_ops:
        if bop.verb == "per_apply_scene" and bop.inst == server_epoch_old:
            in_u = _unpack_any_payload(bop.args)
            out_u = _unpack_any_payload(bop.read) if bop.status == "done" else None
            if in_u and out_u:
                apply_ops_old.append((bop, in_u[0], in_u[1], in_u[2], out_u[0], out_u[1], out_u[2]))
        elif bop.verb == "per_spawn_raw" and bop.inst == server_epoch_old and bop.status == "done":
            out_u = _unpack_any_payload(bop.read)
            if out_u:
                tag = out_u[0].get("tag", "")
                if tag:
                    spawn_raw_ops[tag] = (out_u[0], out_u[1])

    # Build authoritative entity spawn metadata from bridge per_apply_scene + per_spawn_raw
    applied_scenes_final: dict[str, tuple[dict[str, str], dict[str, float], list[dict[str, Any]], list[dict[str, Any]]]] = {}
    idempotent_hits_by_scene: dict[str, int] = {}
    selected_pathway = ""
    for _bop, in_s, _in_n, in_r, out_s, out_n, out_r in apply_ops_old:
        sc_id = out_s.get("scene_id") or in_s.get("scene_id") or ""
        idem_b = int(round(out_n.get("idempotent_hit_b", 0.0)))
        if idem_b == 1:
            idempotent_hits_by_scene[sc_id] = idempotent_hits_by_scene.get(sc_id, 0) + 1
        else:
            applied_scenes_final[sc_id] = (out_s, out_n, in_r, out_r)
            pw = out_s.get("q9_pathway") or in_s.get("q9_pathway") or ""
            if pw in ("a", "b"):
                selected_pathway = pw

    if selected_pathway:
        metrics["q9_selected_pathway"] = selected_pathway

    bridge_spawn_info: dict[str, dict[str, Any]] = {}
    for sc_id, (_out_s, _out_n, _in_r, out_r) in applied_scenes_final.items():
        for row in out_r:
            lid = str(row.get("logical_id") or "")
            if lid:
                bridge_spawn_info[lid] = {
                    "scene_id": sc_id,
                    "class_name": str(row.get("class_name") or ""),
                    "net_id": str(row.get("net_id") or ""),
                    "max_hp": float(row.get("max_hp", 0.0)),
                    "health_hp": float(row.get("health_hp", 0.0)),
                    "spawn_tick_ms": float(row.get("spawn_tick_ms", 0.0)),
                    "q9_row": row,
                }
    for tag, (out_s, out_n) in spawn_raw_ops.items():
        bridge_spawn_info[tag] = {
            "scene_id": "",
            "class_name": str(out_s.get("class_name") or ""),
            "net_id": str(out_s.get("net_id") or ""),
            "pers_id": str(out_s.get("pers_id") or ""),
            "max_hp": float(out_n.get("max_hp", 0.0)),
            "health_hp": float(out_n.get("health_hp", 0.0)),
            "spawn_tick_ms": float(out_n.get("tick_ms", 0.0)),
        }

    # =========================================================================
    # PER-01: Creation of 6 categories, slots/cargo, scene_op_id idempotency & Q9
    # =========================================================================
    expected_scenes_per01 = [retained_scene_id, "scene_a_clean", "scene_b"]
    if has_scene_d:
        expected_scenes_per01.append("scene_d")

    t1_pre_missing = False
    for aid in required_base_areas:
        c_pre = census_by_stage_area.get(("t1_pre_transition_census", aid))
        if c_pre is None or not c_pre["job_complete"]:
            t1_pre_missing = True
            break

    if (
        not ledger_entries
        or not all(sc in applied_scenes_final for sc in expected_scenes_per01)
        or t1_pre_missing
    ):
        checks["PER-01"] = {"status": "missing", "detail": "missing_apply_or_t1_pre_census"}
    else:
        per01_fail: list[str] = []
        per01_missing: list[str] = []

        t1_pre_rows_by_area: dict[str, list[dict[str, Any]]] = {
            aid: census_by_stage_area[("t1_pre_transition_census", aid)]["rows"]
            for aid in required_base_areas
        }

        # Anti-fabrication: check net_id validity and uniqueness within each census disk
        for aid, rlist in t1_pre_rows_by_area.items():
            seen_nids: set[str] = set()
            for r in rlist:
                nid = str(r.get("net_id") or "")
                lid = str(r.get("own_logical_id") or "")
                if not _valid_net_id(nid, lid):
                    per01_fail.append(f"{aid}:invalid_net_id:{nid}")
                elif nid in seen_nids:
                    per01_fail.append(f"{aid}:duplicate_net_id:{nid}")
                seen_nids.add(nid)

        expected_nids_by_area: dict[str, set[str]] = {aid: set() for aid in required_base_areas}
        for aid in required_base_areas:
            c_pre_a = census_by_stage_area[("t1_pre_transition_census", aid)]
            if c_pre_a["include_director_b"] == 1:
                for bf in baseline_director_rows:
                    bf_nid = str(bf.get("net_id") or "")
                    if bf_nid:
                        expected_nids_by_area[aid].add(bf_nid)

        for sc_id in expected_scenes_per01:
            out_s, out_n, in_r, out_r = applied_scenes_final[sc_id]
            sc_fixture = fixture["scenes"].get(sc_id, {})
            fix_entities = {e["logical_id"]: e for e in sc_fixture.get("entities", [])}
            sc_area = sc_fixture.get("area_id", "area_a")
            area_c_rows = t1_pre_rows_by_area.get(sc_area, [])
            census_by_net_id = {str(r.get("net_id") or ""): r for r in area_c_rows}
            q9_tick_ms = float(out_n.get("q9_tick_ms", 0.0))

            if out_s.get("apply_status") != "ok":
                per01_fail.append(f"{sc_id}:apply_status={out_s.get('apply_status')}")
            if len(out_r) != len(fix_entities):
                per01_fail.append(f"{sc_id}:row_count={len(out_r)}!={len(fix_entities)}")

            out_by_lid = {str(r.get("logical_id") or ""): r for r in out_r}
            in_by_lid = {str(r.get("logical_id") or ""): r for r in in_r}

            for lid, f_ent in fix_entities.items():
                if lid not in out_by_lid or lid not in ledger_by_id:
                    per01_fail.append(f"{sc_id}:missing_entity:{lid}")
                    continue
                orow = out_by_lid[lid]
                lrow = ledger_by_id[lid]
                irow = in_by_lid.get(lid, lrow)

                if str(orow.get("class_name") or "") != f_ent["class_name"]:
                    per01_fail.append(f"{lid}:class_mismatch")
                if int(round(float(orow.get("ok_b", 0.0)))) != 1:
                    per01_fail.append(f"{lid}:ok_b!=1")
                if int(round(float(orow.get("alive_b", 0.0)))) != 1:
                    per01_fail.append(f"{lid}:alive_b!=1")
                max_hp = float(orow.get("max_hp", 0.0))
                health_hp = float(orow.get("health_hp", 0.0))
                if not (max_hp > 0.0 and health_hp > 0.0):
                    per01_fail.append(f"{lid}:nonpositive_hp")
                ratio = float(f_ent.get("health_mark_ratio", 0.0))
                if ratio > 0.0 and abs(health_hp - max_hp * ratio) > 1e-2:
                    per01_fail.append(f"{lid}:health_mark_mismatch")

                nid = str(orow.get("net_id") or "")
                if not _valid_net_id(nid, lid) or nid not in census_by_net_id:
                    per01_fail.append(f"{lid}:missing_in_t1_pre_census")
                    continue
                expected_nids_by_area.setdefault(sc_area, set()).add(nid)
                crow = census_by_net_id[nid]
                if str(crow.get("class_name") or "") != f_ent["class_name"]:
                    per01_fail.append(f"{lid}:census_class_mismatch")
                if str(crow.get("own_logical_id") or "") != lid or int(round(float(crow.get("own_b", 0.0)))) != 1:
                    per01_fail.append(f"{lid}:census_ownership_mismatch")

                # BLOQ 4 & BLOQ 9: verify alive_b, max_hp, health_hp, pers_id, and spawn_tick_ms on census row
                c_alive = int(round(float(crow.get("alive_b", 0.0))))
                c_max_hp = float(crow.get("max_hp", 0.0))
                c_hp = float(crow.get("health_hp", 0.0))
                if c_alive != 1:
                    per01_fail.append(f"{lid}:census_alive_b!=1")
                if not (c_max_hp > 0.0 and c_hp > 0.0):
                    per01_fail.append(f"{lid}:census_nonpositive_hp")
                elif abs(c_max_hp - max_hp) > 1e-2 or abs(c_hp - health_hp) > 1e-2:
                    per01_fail.append(f"{lid}:census_hp_mismatch")
                elif ratio > 0.0 and abs(c_hp - c_max_hp * ratio) > 1e-2:
                    per01_fail.append(f"{lid}:census_health_mark_mismatch")
                if str(crow.get("pers_id") or "") != "0:0:0:0":
                    per01_fail.append(f"{lid}:census_nonzero_pers_id")
                o_spawn_t = float(orow.get("spawn_tick_ms", 0.0))
                c_spawn_t = float(crow.get("spawn_tick_ms", -1.0))
                if o_spawn_t <= 0.0 or (q9_tick_ms > 0.0 and abs(o_spawn_t - q9_tick_ms) > 50.0) or abs(c_spawn_t - o_spawn_t) > 1e-3:
                    per01_fail.append(f"{lid}:spawn_tick_mismatch")

                cat = f_ent["cat"]
                parent_id = f_ent["parent_id"]
                if cat in ("infected", "animal"):
                    if int(round(float(orow.get("ai_agent_b", 0.0)))) != 1:
                        per01_fail.append(f"{lid}:ai_agent_b!=1")
                    if int(round(float(crow.get("ai_agent_b", 0.0)))) != 1:
                        per01_fail.append(f"{lid}:census_ai_agent_b!=1")
                else:
                    if int(round(float(orow.get("ai_agent_b", -1.0)))) != 0 or int(round(float(crow.get("ai_agent_b", -1.0)))) != 0:
                        per01_fail.append(f"{lid}:unexpected_ai_agent_b")

                if parent_id == "":
                    if orow.get("obs_loc_kind") != "ground" or crow.get("loc_kind") != "ground":
                        per01_fail.append(f"{lid}:root_not_on_ground")
                    # BLOQ-1: la posicion esperada sale SOLO de la fixture congelada; el ledger del
                    # runner (y los args del enq) solo se contrastan contra ella, nunca la definen.
                    req_x = float(f_ent["req_x_m"])
                    req_z = float(f_ent["req_z_m"])
                    for _src_name, _src in (("ledger", lrow), ("apply_args", irow)):
                        for _k, _exp in (("req_x_m", req_x), ("req_z_m", req_z)):
                            if _k in _src:
                                try:
                                    _v = float(_src[_k])
                                except (TypeError, ValueError):
                                    _v = float("nan")
                                if not (abs(_v - _exp) <= 1e-6):
                                    per01_fail.append(f"{lid}:{_src_name}_{_k}_differs_from_fixture")
                    gy = _find_ground_y(req_x, req_z)
                    if gy is None:
                        per01_missing.append(f"{lid}:missing_ground_query")
                        continue
                    req_y_obs = float(orow.get("req_y_m", gy))
                    if abs(req_y_obs - gy) > 1e-3:
                        per01_fail.append(f"{lid}:req_y_vs_ground_query_mismatch")
                    exp_pos = (req_x, gy, req_z)
                    q9_x = float(orow.get("q9_x_m", 0.0))
                    q9_y = float(orow.get("q9_y_m", 0.0))
                    q9_z = float(orow.get("q9_z_m", 0.0))
                    q9_dx = float(orow.get("q9_dx_m", 0.0))
                    q9_dy = float(orow.get("q9_dy_m", 0.0))
                    q9_dz = float(orow.get("q9_dz_m", 0.0))
                    q9_err = float(orow.get("q9_err_3d_m", 0.0))

                    dx_abs = q9_x - exp_pos[0]
                    dy_abs = q9_y - exp_pos[1]
                    dz_abs = q9_z - exp_pos[2]
                    err_abs = math.sqrt(dx_abs * dx_abs + dy_abs * dy_abs + dz_abs * dz_abs)

                    if (
                        abs(dx_abs - q9_dx) > 1e-4
                        or abs(dy_abs - q9_dy) > 1e-4
                        or abs(dz_abs - q9_dz) > 1e-4
                        or abs(err_abs - q9_err) > 1e-4
                    ):
                        per01_fail.append(f"{lid}:q9_delta_incoherent")

                    if err_abs >= 0.5 + 1e-5:
                        per01_fail.append(f"{lid}:q9_err_3d={err_abs:.4f}m>=0.5m")
                    elif err_abs >= 0.5 - 1e-5:
                        per01_missing.append("q9_boundary_uncertainty")

                    # N53: static roots in t1_pre_transition_census checked against < 0.5 m (not 1 mm)
                    if cat in ("prop", "container", "vehicle", "actor"):
                        cx_m = float(crow.get("pos_x_m", 0.0))
                        cy_m = float(crow.get("pos_y_m", 0.0))
                        cz_m = float(crow.get("pos_z_m", 0.0))
                        c_err = math.sqrt(
                            (cx_m - exp_pos[0]) ** 2
                            + (cy_m - exp_pos[1]) ** 2
                            + (cz_m - exp_pos[2]) ** 2
                        )
                        if c_err >= 0.5 - 1e-5:
                            per01_fail.append(f"{lid}:census_static_root_err={c_err:.4f}m")
                else:
                    parent_orow = out_by_lid.get(parent_id)
                    parent_nid = str(parent_orow.get("net_id") or "") if parent_orow else ""
                    parent_cname = str(parent_orow.get("class_name") or "") if parent_orow else ""
                    if str(orow.get("obs_parent_net_id") or "") != parent_nid:
                        per01_fail.append(f"{lid}:obs_parent_net_id_mismatch")
                    if str(crow.get("parent_net_id") or "") != parent_nid or str(crow.get("parent_class") or "") != parent_cname:
                        per01_fail.append(f"{lid}:census_parent_net_id_mismatch")
                    req_slot = f_ent["slot_name"]
                    obs_loc = str(orow.get("obs_loc_kind") or "")
                    c_loc = str(crow.get("loc_kind") or "")
                    obs_slot = str(orow.get("obs_slot_name") or "")
                    c_slot = str(crow.get("slot_name") or "")
                    if req_slot == "Cargo":
                        if obs_loc != "cargo" or c_loc != "cargo":
                            per01_fail.append(f"{lid}:not_in_cargo")
                        if not obs_slot.startswith("Cargo") or not c_slot.startswith("Cargo"):
                            per01_fail.append(f"{lid}:invalid_cargo_slot_name")
                    else:
                        if obs_loc != "attachment" or c_loc != "attachment":
                            per01_fail.append(f"{lid}:not_in_attachment")
                        if obs_slot != req_slot or c_slot != req_slot:
                            per01_fail.append(f"{lid}:attachment_slot_mismatch")

            # Verify no extra own entities of this scene in t1_pre_transition_census
            own_rows_sc = [
                r for r in area_c_rows if str(r.get("own_logical_id") or "") in fix_entities
            ]
            if len(own_rows_sc) != len(fix_entities):
                per01_fail.append(f"{sc_id}:own_census_count={len(own_rows_sc)}!={len(fix_entities)}")

        # BLOQ 4 & BLOQ 6: validate all expected per_spawn_raw items and their exact container parents in t1_pre_transition_census
        expected_raw_tags = [
            f"{retained_pfx}_foreign_ground",
            f"{retained_pfx}_foreign_in_chest",
            f"{retained_pfx}_foreign_in_child_kit",
            "b_foreign_in_chest",
            "c_persistent_control",
        ]
        for rtag in expected_raw_tags:
            rdef = fixture.get("raw_spawns", {}).get(rtag)
            if not rdef or rtag not in spawn_raw_ops or rtag not in bridge_spawn_info:
                per01_fail.append(f"missing_raw_spawn:{rtag}")
                continue
            r_out_s, r_out_n = spawn_raw_ops[rtag]
            r_area = rdef["area_id"]
            r_nid = str(r_out_s.get("net_id") or "")
            r_cname = rdef["class_name"]
            r_ratio = float(rdef.get("health_mark_ratio", 0.0))
            r_max_hp = float(r_out_n.get("max_hp", 0.0))
            r_hp = float(r_out_n.get("health_hp", 0.0))
            if r_out_s.get("spawn_status") != "ok" or r_out_s.get("class_name") != r_cname:
                per01_fail.append(f"{rtag}:raw_spawn_failed")
            if not (r_max_hp > 0.0 and r_hp > 0.0) or (r_ratio > 0.0 and abs(r_hp - r_max_hp * r_ratio) > 1e-2):
                per01_fail.append(f"{rtag}:raw_spawn_hp_invalid")
            area_rmap = {str(r.get("net_id") or ""): r for r in t1_pre_rows_by_area.get(r_area, [])}
            rcrow = area_rmap.get(r_nid)
            if not rcrow:
                per01_fail.append(f"{rtag}:missing_in_t1_pre_census")
                continue
            expected_nids_by_area.setdefault(r_area, set()).add(r_nid)
            rc_alive = int(round(float(rcrow.get("alive_b", 0.0))))
            rc_max_hp = float(rcrow.get("max_hp", 0.0))
            rc_hp = float(rcrow.get("health_hp", 0.0))
            if (
                rcrow.get("class_name") != r_cname
                or rc_alive != 1
                or int(round(float(rcrow.get("own_b", -1.0)))) != 0
                or str(rcrow.get("own_logical_id") or "") != ""
                or not (rc_max_hp > 0.0 and rc_hp > 0.0)
                or abs(rc_max_hp - r_max_hp) > 1e-2
                or abs(rc_hp - r_hp) > 1e-2
            ):
                per01_fail.append(f"{rtag}:census_raw_state_invalid")
            if rdef["mode"] == "foreign_in_container":
                tgt_pid = rdef["target_parent_id"]
                exp_pnid = bridge_spawn_info.get(tgt_pid, {}).get("net_id", "")
                exp_pclass = bridge_spawn_info.get(tgt_pid, {}).get("class_name", "")
                if (
                    not exp_pnid
                    or r_out_s.get("obs_loc_kind") != "cargo"
                    or r_out_s.get("obs_parent_net_id") != exp_pnid
                    or not str(r_out_s.get("obs_slot_name") or "").startswith("Cargo")
                    or rcrow.get("loc_kind") != "cargo"
                    or rcrow.get("parent_net_id") != exp_pnid
                    or rcrow.get("parent_class") != exp_pclass
                    or not str(rcrow.get("slot_name") or "").startswith("Cargo")
                ):
                    per01_fail.append(f"{rtag}:wrong_parent_container")
            else:
                if (
                    r_out_s.get("obs_loc_kind") != "ground"
                    or rcrow.get("loc_kind") != "ground"
                    or rcrow.get("parent_net_id") != ""
                    or math.hypot(
                        float(rcrow.get("pos_x_m", 0.0)) - float(rdef["x_m"]),
                        float(rcrow.get("pos_z_m", 0.0)) - float(rdef["z_m"]),
                    )
                    >= 0.5
                ):
                    per01_fail.append(f"{rtag}:wrong_ground_placement")
                if rdef["mode"] == "persistent_control":
                    fp_children = [
                        r
                        for r in t1_pre_rows_by_area.get("area_c", [])
                        if r.get("class_name") == rdef.get("child_cargo_class", "Fireplace")
                        and r.get("loc_kind") == "cargo"
                        and r.get("parent_net_id") == r_nid
                        and int(round(float(r.get("alive_b", 0.0)))) == 1
                        and float(r.get("max_hp", 0.0)) > 0.0
                        and float(r.get("health_hp", 0.0)) > 0.0
                    ]
                    if len(fp_children) != 1:
                        per01_fail.append("c_persistent_control:missing_child_in_t1_pre")
                    else:
                        expected_nids_by_area.setdefault("area_c", set()).add(str(fp_children[0].get("net_id") or ""))

        # BLOQ 4: verify complete row accounting in every area of t1_pre_transition_census (rejects unlabeled duplicates)
        t0_baseline_unusable = any(
            r in reasons
            for r in ("missing_t0_baseline_census", "incomplete_t0_baseline_census", "t0_director_inventory_not_censused")
        )
        for aid in required_base_areas:
            area_rows_all = t1_pre_rows_by_area.get(aid, [])
            actual_nids = {str(r.get("net_id") or "") for r in area_rows_all}
            exp_nids = expected_nids_by_area.get(aid, set())
            if t0_baseline_unusable:
                # sin linea base del director en t0 no se puede contabilizar el inventario ajeno
                per01_missing.append("t0_baseline_unusable")
                break
            if len(area_rows_all) != len(exp_nids) or actual_nids != exp_nids:
                per01_fail.append(f"{aid}:unexpected_or_extra_census_rows:{len(area_rows_all)}!={len(exp_nids)}")

        # Check scene_op_id idempotency on retained_scene_id
        if idempotent_hits_by_scene.get(retained_scene_id, 0) < 1:
            per01_fail.append(f"{retained_scene_id}:missing_idempotent_repeat")

        if per01_fail:
            checks["PER-01"] = {"status": "fail", "detail": ";".join(per01_fail[:5])}
        elif per01_missing:
            checks["PER-01"] = {"status": "missing", "detail": ";".join(per01_missing[:5])}
        else:
            checks["PER-01"] = {"status": "pass", "detail": "ok"}

    # =========================================================================
    # PER-02: Creature survival at 10 min regardless of radius
    # =========================================================================
    creature_specs = [
        (f"{retained_pfx}_inf_1", retained_area_id),
        (f"{retained_pfx}_ani_1", retained_area_id),
        ("b_inf_1", "area_b"),
        ("b_ani_1", "area_b"),
    ]
    t2_missing = False
    for _cid, aid in creature_specs:
        c2 = census_by_stage_area.get(("t2_census_10min", aid))
        if c2 is None or not c2["job_complete"]:
            t2_missing = True
            break

    if t2_missing:
        checks["PER-02"] = {"status": "missing", "detail": "census_coverage_missing"}
    else:
        per02_fail: list[str] = []
        per02_missing: list[str] = []
        for cid, aid in creature_specs:
            c2 = census_by_stage_area[("t2_census_10min", aid)]
            sp_info = bridge_spawn_info.get(cid)
            if not sp_info:
                per02_missing.append(f"missing_spawn_info:{cid}")
                continue
            exp_nid = sp_info["net_id"]
            matches = [
                r
                for r in c2["rows"]
                if str(r.get("own_logical_id") or "") == cid and str(r.get("net_id") or "") == exp_nid
            ]
            if not matches:
                per02_missing.append(f"census_coverage_missing:{cid}")
                continue
            crow = matches[0]
            in_rad = int(round(float(crow.get("in_radius_b", -1.0))))
            if in_rad not in (0, 1):
                per02_fail.append(f"{cid}:invalid_in_radius_b")
            # Nuevo 8: comprobar class_name contra fixture y creación observada en t2
            f_ent = None
            for sc_name in (retained_scene_id, "scene_a_clean", "scene_b", "scene_d"):
                sc_fixture = fixture["scenes"].get(sc_name, {})
                if cid in {e["logical_id"] for e in sc_fixture.get("entities", [])}:
                    for e in sc_fixture.get("entities", []):
                        if e["logical_id"] == cid:
                            f_ent = e
                            break
            if f_ent and crow.get("class_name") != f_ent["class_name"]:
                per02_fail.append(f"{cid}:t2_class_mismatch:{crow.get('class_name')}!={f_ent['class_name']}")
            if (
                int(round(float(crow.get("alive_b", 0.0)))) != 1
                or int(round(float(crow.get("ai_agent_b", 0.0)))) != 1
                or float(crow.get("max_hp", 0.0)) <= 0.0
                or float(crow.get("health_hp", 0.0)) <= 0.0
            ):
                per02_fail.append(f"{cid}:dead_or_no_ai_at_t2")
            # BLOQ 9: require crow["spawn_tick_ms"] to match the creation tick from per_apply_scene
            auth_spawn_t = float(sp_info.get("spawn_tick_ms", 0.0))
            row_spawn_t = float(crow.get("spawn_tick_ms", -1.0))
            if auth_spawn_t <= 0.0 or abs(row_spawn_t - auth_spawn_t) > 1e-3:
                per02_fail.append(f"{cid}:spawn_tick_mismatch")
                continue
            snap_t = float(c2["snap_tick_ms"])
            if snap_t < auth_spawn_t:
                per02_missing.append("negative_hold_elapsed")
            elif build_kind in ("diag", "retail") and snap_t - auth_spawn_t < 600000.0:
                # MEN-5: los 10 min de retencion solo se exigen en diag/retail (brief); en offline no
                per02_missing.append("hold_under_600s")

        if per02_fail:
            checks["PER-02"] = {"status": "fail", "detail": ";".join(per02_fail)}
        elif per02_missing:
            checks["PER-02"] = {"status": "missing", "detail": ";".join(per02_missing)}
        else:
            checks["PER-02"] = {"status": "pass", "detail": "ok"}

    # Collect transitions and resets in server_epoch_old
    transitions_by_lid: dict[str, tuple[dict[str, str], dict[str, float]]] = {}
    resets_by_scene: dict[str, list[tuple[dict[str, str], dict[str, float], list[dict[str, Any]], dict[str, str]]]] = {}
    for bop in ordered_ops:
        if bop.inst != server_epoch_old:
            continue
        if bop.verb == "per_child_transition" and bop.status == "done":
            in_u = _unpack_any_payload(bop.args)
            out_u = _unpack_any_payload(bop.read)
            if in_u and out_u:
                lid = in_u[0].get("logical_id", "")
                if lid:
                    transitions_by_lid[lid] = (out_u[0], out_u[1])
        elif bop.verb == "per_reset_scene" and bop.status == "done":
            in_u = _unpack_any_payload(bop.args)
            out_u = _unpack_any_payload(bop.read)
            if in_u and out_u:
                sc_id = out_u[0].get("scene_id") or in_u[0].get("scene_id") or ""
                if sc_id:
                    resets_by_scene.setdefault(sc_id, []).append((out_u[0], out_u[1], out_u[2], in_u[0]))

    # =========================================================================
    # PER-03: Reset of clean scene (scene_a_clean), 3 garments, director intact
    # =========================================================================
    c_t1_pre_a = census_by_stage_area.get(("t1_pre_transition_census", "area_a"))
    c_t1_post_a = census_by_stage_area.get(("t1_post_transition_census", "area_a"))
    c_t3_pre_a = census_by_stage_area.get(("t3_pre_reset_census", "area_a"))
    c_t3_post_a = census_by_stage_area.get(("t3_post_reset_census", "area_a"))

    if (
        c_t1_pre_a is None
        or c_t1_post_a is None
        or c_t3_pre_a is None
        or c_t3_post_a is None
        or not c_t1_pre_a["job_complete"]
        or not c_t1_post_a["job_complete"]
        or not c_t3_pre_a["job_complete"]
        or not c_t3_post_a["job_complete"]
    ):
        checks["PER-03"] = {"status": "missing", "detail": "missing_area_a_census"}
    elif (
        c_t3_pre_a["director_present_b"] != 1
        or c_t3_pre_a["director_inv_readable_b"] != 1
        or c_t3_post_a["director_present_b"] != 1
        or c_t3_post_a["director_inv_readable_b"] != 1
    ):
        checks["PER-03"] = {"status": "missing", "detail": "director_absent_or_unreadable"}
    else:
        per03_fail: list[str] = []
        per03_missing: list[str] = []
        ac_act_nid = bridge_spawn_info.get("ac_act_1", {}).get("net_id", "")
        cap_nid = bridge_spawn_info.get("ac_act_1_cap_worn", {}).get("net_id", "")
        arm_nid = bridge_spawn_info.get("ac_act_1_armband_drop", {}).get("net_id", "")
        glv_nid = bridge_spawn_info.get("ac_act_1_gloves_dir", {}).get("net_id", "")

        # (1) t1_pre_transition_census: 3 garments attached to ac_act_1
        t1_pre_map = {str(r.get("net_id") or ""): r for r in c_t1_pre_a["rows"]}
        for gnid, gslot in ((cap_nid, "Headgear"), (arm_nid, "Armband"), (glv_nid, "Gloves")):
            r = t1_pre_map.get(gnid)
            if not r or r.get("loc_kind") != "attachment" or r.get("parent_net_id") != ac_act_nid or r.get("slot_name") != gslot:
                per03_fail.append(f"t1_pre_garment_invalid:{gslot}")

        # (2) per_child_transition & t1_post / t3_pre verification
        for tlid in ("ac_act_1_armband_drop", "ac_act_1_gloves_dir"):
            if tlid not in transitions_by_lid or transitions_by_lid[tlid][0].get("transition_status") != "ok":
                per03_fail.append(f"transition_missing_or_failed:{tlid}")

        for stg_name, c_obj in (("t1_post", c_t1_post_a), ("t3_pre", c_t3_pre_a)):
            rmap = {str(r.get("net_id") or ""): r for r in c_obj["rows"]}
            r_cap = rmap.get(cap_nid)
            r_arm = rmap.get(arm_nid)
            r_glv = rmap.get(glv_nid)
            if not r_cap or r_cap.get("loc_kind") != "attachment" or r_cap.get("parent_net_id") != ac_act_nid:
                per03_fail.append(f"{stg_name}:cap_not_attached")
            if not r_arm or r_arm.get("loc_kind") != "ground" or r_arm.get("parent_net_id") != "":
                per03_fail.append(f"{stg_name}:armband_not_on_ground")
            if (
                not r_glv
                or not director_uid_t0
                or r_glv.get("owner_uid") != director_uid_t0
                or not r_glv.get("parent_net_id")
                or r_glv.get("parent_net_id") == director_uid_t0
                or not r_glv.get("slot_name")
            ):
                per03_fail.append(f"{stg_name}:gloves_not_in_director")

        # (3) Two per_reset_scene calls on scene_a_clean (anti-fabrication: 2nd reset mandatory)
        clean_resets = resets_by_scene.get("scene_a_clean", [])
        if len(clean_resets) < 2:
            per03_missing.append("second_reset_observation_missing")
        else:
            r1_s, r1_n, _r1_rows, r1_in = clean_resets[0]
            r2_s, r2_n, _r2_rows, r2_in = clean_resets[1]
            if r1_in.get("reset_op_id") == r2_in.get("reset_op_id"):
                per03_fail.append("second_reset_reused_reset_op_id")
            if (
                r1_s.get("reset_status") != "ok"
                or r1_s.get("reason") != "clean"
                or int(round(r1_n.get("deleted_n", -1.0))) != 6
                or int(round(r1_n.get("retained_n", -1.0))) != 0
            ):
                per03_fail.append("first_clean_reset_unexpected_counts")
            if (
                r2_s.get("reset_status") != "ok"
                or int(round(r2_n.get("deleted_n", -1.0))) != 0
                or int(round(r2_n.get("retained_n", -1.0))) != 0
            ):
                per03_fail.append("second_clean_reset_not_idempotent")

        # (4) t3_post_reset_census of area_a: 0 entities of scene_a_clean, no unexpected unlabeled survivors, director intact
        clean_lids = {e["logical_id"] for e in fixture["scenes"]["scene_a_clean"]["entities"]}
        clean_nids = {bridge_spawn_info[lid]["net_id"] for lid in clean_lids if lid in bridge_spawn_info}
        allowed_area_a_post_nids: set[str] = set()
        if not uses_mut_area:
            for alid in (
                "a_prop_2",
                "a_cont_1",
                "a_cont_1_child",
                "b_cross_child",
                "a_foreign_ground",
                "a_foreign_in_chest",
                "a_foreign_in_child_kit",
            ):
                anid = bridge_spawn_info.get(alid, {}).get("net_id", "")
                if anid:
                    allowed_area_a_post_nids.add(anid)

        for r in c_t3_post_a["rows"]:
            rnid = str(r.get("net_id") or "")
            rlid = str(r.get("own_logical_id") or "")
            if rlid in clean_lids or rnid in clean_nids:
                per03_fail.append(f"scene_a_clean_survivor:{rlid or r.get('class_name')}")
            elif r.get("owner_uid") != director_uid_t0 and rnid not in allowed_area_a_post_nids:
                per03_fail.append(f"unexpected_area_a_survivor:{r.get('class_name')}:{rnid}")

        # Check baseline_director_foreign and WorkingGloves_Yellow in director
        t3_post_all_dir_rows: dict[str, dict[str, Any]] = {}
        for c_post in censuses_by_stage.get("t3_post_reset_census", []):
            for r in c_post["rows"]:
                if r.get("owner_uid") == director_uid_t0:
                    t3_post_all_dir_rows[str(r.get("net_id") or "")] = r

        for bf in baseline_director_rows:
            bf_nid = str(bf.get("net_id") or "")
            post_bf = t3_post_all_dir_rows.get(bf_nid)
            if (
                not post_bf
                or post_bf.get("parent_net_id") != bf.get("parent_net_id")
                or post_bf.get("slot_name") != bf.get("slot_name")
            ):
                per03_fail.append(f"baseline_director_foreign_altered:{bf_nid}")

        b_glv_nid = bridge_spawn_info.get("b_act_1_gloves_dir", {}).get("net_id", "")
        t3_pre_all_dir_rows: dict[str, dict[str, Any]] = {}
        for c_pre in censuses_by_stage.get("t3_pre_reset_census", []):
            for r in c_pre["rows"]:
                if r.get("owner_uid") == director_uid_t0:
                    t3_pre_all_dir_rows[str(r.get("net_id") or "")] = r
        pre_b_glv = t3_pre_all_dir_rows.get(b_glv_nid)
        post_b_glv = t3_post_all_dir_rows.get(b_glv_nid)
        if (
            not pre_b_glv
            or not post_b_glv
            or post_b_glv.get("parent_net_id") != pre_b_glv.get("parent_net_id")
            or post_b_glv.get("slot_name") != pre_b_glv.get("slot_name")
        ):
            per03_fail.append("b_act_1_gloves_dir_altered_during_clean_reset")

        if per03_fail:
            checks["PER-03"] = {"status": "fail", "detail": ";".join(per03_fail[:5])}
        elif per03_missing:
            checks["PER-03"] = {"status": "missing", "detail": ";".join(per03_missing[:5])}
        else:
            checks["PER-03"] = {"status": "pass", "detail": "ok"}

    # =========================================================================
    # PER-04: Retention of own containers/children holding foreign or cross-scene items
    # =========================================================================
    c_t3_pre_ret = census_by_stage_area.get(("t3_pre_reset_census", retained_area_id))
    c_t3_post_ret = census_by_stage_area.get(("t3_post_reset_census", retained_area_id))
    ret_resets = resets_by_scene.get(retained_scene_id, [])

    if (
        c_t3_pre_ret is None
        or c_t3_post_ret is None
        or not c_t3_pre_ret["job_complete"]
        or not c_t3_post_ret["job_complete"]
        or not ret_resets
    ):
        checks["PER-04"] = {"status": "missing", "detail": "missing_retained_reset_or_census"}
    else:
        per04_fail: list[str] = []
        rr_s, rr_n, rr_rows, _rr_in = ret_resets[0]
        exp_retained_ids = {f"{retained_pfx}_prop_2", f"{retained_pfx}_cont_1", f"{retained_pfx}_cont_1_child"}
        all_ret_scene_ids = {e["logical_id"] for e in fixture["scenes"][retained_scene_id]["entities"]}
        exp_deleted_ids = all_ret_scene_ids - exp_retained_ids

        if rr_s.get("reset_status") != "partial" or rr_s.get("reason") != "foreign_content_retained":
            per04_fail.append(f"reset_status={rr_s.get('reset_status')}/{rr_s.get('reason')}")
        if int(round(rr_n.get("deleted_n", -1.0))) != 9 or int(round(rr_n.get("retained_n", -1.0))) != 3:
            per04_fail.append(f"counts=del:{rr_n.get('deleted_n')},ret:{rr_n.get('retained_n')}")
        obs_ret_ids = {str(r.get("logical_id") or "") for r in rr_rows}
        if obs_ret_ids != exp_retained_ids:
            per04_fail.append(f"retained_ids={sorted(obs_ret_ids)}")

        exp_foreign_desc = {
            f"{retained_pfx}_prop_2": 1,
            f"{retained_pfx}_cont_1": 2,
            f"{retained_pfx}_cont_1_child": 1,
        }
        for rrow in rr_rows:
            rlid = str(rrow.get("logical_id") or "")
            if rlid in exp_foreign_desc:
                if int(round(float(rrow.get("foreign_descendants_n", -1.0)))) != exp_foreign_desc[rlid]:
                    per04_fail.append(f"foreign_descendants_mismatch:{rlid}")

        pre_ret_by_nid = {str(r.get("net_id") or ""): r for r in c_t3_pre_ret["rows"]}
        post_by_nid = {str(r.get("net_id") or ""): r for r in c_t3_post_ret["rows"]}
        for dlid in sorted(exp_deleted_ids):
            dnid = bridge_spawn_info.get(dlid, {}).get("net_id", "")
            if dnid in post_by_nid or any(str(r.get("own_logical_id") or "") == dlid for r in c_t3_post_ret["rows"]):
                per04_fail.append(f"deleted_entity_survived:{dlid}")

        prop2_nid = bridge_spawn_info.get(f"{retained_pfx}_prop_2", {}).get("net_id", "")
        cont1_nid = bridge_spawn_info.get(f"{retained_pfx}_cont_1", {}).get("net_id", "")
        kit_nid = bridge_spawn_info.get(f"{retained_pfx}_cont_1_child", {}).get("net_id", "")
        f_ground_nid = bridge_spawn_info.get(f"{retained_pfx}_foreign_ground", {}).get("net_id", "")
        f_chest_nid = bridge_spawn_info.get(f"{retained_pfx}_foreign_in_chest", {}).get("net_id", "")
        f_kit_nid = bridge_spawn_info.get(f"{retained_pfx}_foreign_in_child_kit", {}).get("net_id", "")
        cross_nid = bridge_spawn_info.get("b_cross_child", {}).get("net_id", "")

        for rlid in sorted(exp_retained_ids):
            rnid = bridge_spawn_info.get(rlid, {}).get("net_id", "")
            r_pre_c = pre_ret_by_nid.get(rnid)
            r_post = post_by_nid.get(rnid)
            if not r_pre_c or not r_post or int(round(float(r_post.get("alive_b", 0.0)))) != 1:
                per04_fail.append(f"retained_entity_missing:{rlid}")
            elif rlid == f"{retained_pfx}_cont_1_child":
                if (
                    r_pre_c.get("loc_kind") != "cargo"
                    or r_pre_c.get("parent_net_id") != cont1_nid
                    or r_post.get("loc_kind") != "cargo"
                    or r_post.get("parent_net_id") != cont1_nid
                ):
                    per04_fail.append("retained_child_kit_wrong_parent")
            else:
                if r_pre_c.get("loc_kind") != "ground" or r_post.get("loc_kind") != "ground":
                    per04_fail.append(f"retained_root_not_on_ground:{rlid}")

        # Nuevo 7: validate inv_children_n for retained containers against censused children
        # Count actual children in pre_reset and post_reset census for each retained container
        retained_container_ids = [
            f"{retained_pfx}_cont_1",
            f"{retained_pfx}_cont_1_child",
            f"{retained_pfx}_prop_2",
        ]
        for cont_lid in retained_container_ids:
            cont_nid = bridge_spawn_info.get(cont_lid, {}).get("net_id", "")
            if not cont_nid:
                continue
            for stg_lbl, census_map in (("pre", pre_ret_by_nid), ("post", post_by_nid)):
                r_census = census_map.get(cont_nid)
                if not r_census:
                    continue
                declared_inv = int(round(float(r_census.get("inv_children_n", -1.0))))
                if declared_inv >= 0:
                    actual_children = sum(
                        1 for r in census_map.values()
                        if str(r.get("parent_net_id") or "") == cont_nid
                        and int(round(float(r.get("own_b", 0.0)))) == 1
                    )
                    foreign_children = sum(
                        1 for r in census_map.values()
                        if str(r.get("parent_net_id") or "") == cont_nid
                        and int(round(float(r.get("own_b", 1.0)))) == 0
                    )
                    total_children = actual_children + foreign_children
                    if declared_inv != total_children:
                        per04_fail.append(f"inv_children_n_mismatch:{stg_lbl}:{cont_lid}:declared={declared_inv},censused={total_children}")

        # BLOQ 6: verify foreign items and cross-scene child are inside the required containers before and after reset
        for stg_lbl, m_by_nid in (("pre", pre_ret_by_nid), ("post", post_by_nid)):
            r_cross = m_by_nid.get(cross_nid)
            r_fc = m_by_nid.get(f_chest_nid)
            r_fk = m_by_nid.get(f_kit_nid)
            if not r_cross or r_cross.get("loc_kind") != "cargo" or r_cross.get("parent_net_id") != prop2_nid or r_cross.get("parent_class") != "WoodenCrate":
                per04_fail.append(f"{stg_lbl}:b_cross_child_not_in_prop_2")
            if not r_fc or r_fc.get("loc_kind") != "cargo" or r_fc.get("parent_net_id") != cont1_nid or r_fc.get("parent_class") != "SeaChest":
                per04_fail.append(f"{stg_lbl}:foreign_in_chest_wrong_parent")
            if not r_fk or r_fk.get("loc_kind") != "cargo" or r_fk.get("parent_net_id") != kit_nid or r_fk.get("parent_class") != "FirstAidKit":
                per04_fail.append(f"{stg_lbl}:foreign_in_child_kit_wrong_parent")

        # BLOQ 4: verify no unexpected non-director rows survive in retained_area_id
        expected_ret_post_nids = {prop2_nid, cont1_nid, kit_nid, cross_nid, f_ground_nid, f_chest_nid, f_kit_nid}
        for r in c_t3_post_ret["rows"]:
            if r.get("owner_uid") == director_uid_t0:
                continue
            rnid = str(r.get("net_id") or "")
            if rnid not in expected_ret_post_nids:
                per04_fail.append(f"unexpected_retained_area_survivor:{r.get('class_name')}:{rnid}")

        if per04_fail:
            checks["PER-04"] = {"status": "fail", "detail": ";".join(per04_fail[:5])}
        else:
            checks["PER-04"] = {"status": "pass", "detail": "ok"}

    # =========================================================================
    # PER-05: Intactness of foreign items, cross-scene child, retained containers, and scene_b during reset
    # =========================================================================
    c_t3_pre_b = census_by_stage_area.get(("t3_pre_reset_census", "area_b"))
    c_t3_post_b = census_by_stage_area.get(("t3_post_reset_census", "area_b"))

    if (
        c_t3_pre_ret is None
        or c_t3_post_ret is None
        or c_t3_pre_b is None
        or c_t3_post_b is None
        or not c_t3_pre_ret["job_complete"]
        or not c_t3_post_ret["job_complete"]
        or not c_t3_pre_b["job_complete"]
        or not c_t3_post_b["job_complete"]
        or c_t3_pre_ret["job_id"] == c_t3_post_ret["job_id"]
        or c_t3_pre_b["job_id"] == c_t3_post_b["job_id"]
    ):
        checks["PER-05"] = {"status": "missing", "detail": "missing_pre_or_post_reset_census"}
    else:
        pre_map: dict[str, dict[str, Any]] = {}
        post_map: dict[str, dict[str, Any]] = {}
        for c_item in censuses_by_stage.get("t3_pre_reset_census", []):
            if c_item["job_complete"]:
                for r in c_item["rows"]:
                    pre_map[str(r.get("net_id") or "")] = r
        for c_item in censuses_by_stage.get("t3_post_reset_census", []):
            if c_item["job_complete"]:
                for r in c_item["rows"]:
                    post_map[str(r.get("net_id") or "")] = r

        static_referents = [
            f"{retained_pfx}_prop_2",
            f"{retained_pfx}_cont_1",
            f"{retained_pfx}_cont_1_child",
            f"{retained_pfx}_foreign_ground",
            f"{retained_pfx}_foreign_in_chest",
            f"{retained_pfx}_foreign_in_child_kit",
            "b_cross_child",
            "b_prop_1",
            "b_chest_own",
            "b_chest_own_child",
            "b_chest_foreign",
            "b_foreign_in_chest",
            "b_act_1",
            "b_act_1_cap_worn",
            "b_act_1_armband_drop",
            "b_act_1_gloves_dir",
        ]
        creature_referents = ["b_inf_1", "b_ani_1"]

        missing_pre: list[str] = []
        for ref_id in static_referents + creature_referents:
            rnid = bridge_spawn_info.get(ref_id, {}).get("net_id", "")
            if not rnid or rnid not in pre_map:
                missing_pre.append(ref_id)

        if missing_pre:
            checks["PER-05"] = {
                "status": "missing",
                "detail": f"missing_pre_reset_referent:{','.join(missing_pre[:4])}",
            }
        else:
            per05_fail: list[str] = []
            # BLOQ 6: Verify exact container hierarchy in t3_pre_reset_census before reset
            prop2_nid = bridge_spawn_info.get(f"{retained_pfx}_prop_2", {}).get("net_id", "")
            cont1_nid = bridge_spawn_info.get(f"{retained_pfx}_cont_1", {}).get("net_id", "")
            kit_nid = bridge_spawn_info.get(f"{retained_pfx}_cont_1_child", {}).get("net_id", "")
            b_chest_own_nid = bridge_spawn_info.get("b_chest_own", {}).get("net_id", "")
            b_chest_for_nid = bridge_spawn_info.get("b_chest_foreign", {}).get("net_id", "")

            required_cargo_parents = [
                ("b_cross_child", prop2_nid, "WoodenCrate"),
                (f"{retained_pfx}_foreign_in_chest", cont1_nid, "SeaChest"),
                (f"{retained_pfx}_cont_1_child", cont1_nid, "SeaChest"),
                (f"{retained_pfx}_foreign_in_child_kit", kit_nid, "FirstAidKit"),
                ("b_foreign_in_chest", b_chest_for_nid, "SeaChest"),
                ("b_chest_own_child", b_chest_own_nid, "SeaChest"),
            ]
            for child_id, exp_pnid, exp_pclass in required_cargo_parents:
                cnid = bridge_spawn_info[child_id]["net_id"]
                c_row_pre = pre_map[cnid]
                if (
                    c_row_pre.get("loc_kind") != "cargo"
                    or c_row_pre.get("parent_net_id") != exp_pnid
                    or c_row_pre.get("parent_class") != exp_pclass
                    or not str(c_row_pre.get("slot_name") or "").startswith("Cargo")
                ):
                    per05_fail.append(f"{child_id}:wrong_parent_pre_reset")

            for ref_id in static_referents:
                rnid = bridge_spawn_info[ref_id]["net_id"]
                r_pre = pre_map[rnid]
                r_post = post_map.get(rnid)
                if not r_post:
                    per05_fail.append(f"{ref_id}:wiped_in_post_reset")
                    continue
                is_retained = ref_id in exp_retained_ids
                if (
                    r_post.get("class_name") != r_pre.get("class_name")
                    or r_post.get("pers_id") != r_pre.get("pers_id")
                    or int(round(float(r_post.get("alive_b", 0.0)))) != 1
                    or abs(float(r_post.get("max_hp", 0.0)) - float(r_pre.get("max_hp", 0.0))) > 1e-3
                    or abs(float(r_post.get("health_hp", 0.0)) - float(r_pre.get("health_hp", 0.0))) > 1e-3
                    or r_post.get("loc_kind") != r_pre.get("loc_kind")
                    or r_post.get("parent_class") != r_pre.get("parent_class")
                    or r_post.get("parent_net_id") != r_pre.get("parent_net_id")
                    or r_post.get("slot_name") != r_pre.get("slot_name")
                    or r_post.get("owner_uid") != r_pre.get("owner_uid")
                    or (not is_retained and int(round(float(r_post.get("inv_children_n", -1.0))))
                        != int(round(float(r_pre.get("inv_children_n", -2.0)))))
                ):
                    per05_fail.append(f"{ref_id}:state_or_location_changed")
                    continue

                # BLOQ 5 (N52): check pose and orientation stability on ALL world referents (ground, retained containers, cargo, attachments)
                if not r_pre.get("owner_uid"):
                    for coord_k in ("pos_x_m", "pos_y_m", "pos_z_m"):
                        if not (_is_finite_num(r_pre.get(coord_k)) and _is_finite_num(r_post.get(coord_k))):
                            per05_fail.append(f"{ref_id}:nonfinite_{coord_k}")
                        elif abs(float(r_post[coord_k]) - float(r_pre[coord_k])) > 1e-4:
                            per05_fail.append(f"{ref_id}:{coord_k}_changed")
                    for ang_k in ("yaw_deg", "pitch_deg", "roll_deg"):
                        if not (_is_finite_num(r_pre.get(ang_k)) and _is_finite_num(r_post.get(ang_k))):
                            per05_fail.append(f"{ref_id}:nonfinite_{ang_k}")
                        elif _angle_diff_deg(float(r_post[ang_k]), float(r_pre[ang_k])) > 1e-3:
                            per05_fail.append(f"{ref_id}:{ang_k}_changed")

            for cref_id in creature_referents:
                cnid = bridge_spawn_info[cref_id]["net_id"]
                c_pre = pre_map[cnid]
                c_post = post_map.get(cnid)
                if not c_post:
                    per05_fail.append(f"{cref_id}:wiped_in_post_reset")
                    continue
                if (
                    c_post.get("class_name") != c_pre.get("class_name")
                    or int(round(float(c_post.get("alive_b", 0.0)))) != 1
                    or int(round(float(c_post.get("ai_agent_b", 0.0)))) != 1
                    or abs(float(c_post.get("health_hp", 0.0)) - float(c_pre.get("health_hp", 0.0))) > 1e-3
                ):
                    per05_fail.append(f"{cref_id}:creature_state_altered")

            if per05_fail:
                checks["PER-05"] = {"status": "fail", "detail": ";".join(per05_fail[:5])}
            else:
                checks["PER-05"] = {"status": "pass", "detail": "ok"}

    # =========================================================================
    # PER-06: Survival of persistent foreign control after server restart
    # =========================================================================
    c_t3_post_c = census_by_stage_area.get(("t3_post_reset_census", "area_c"))
    c_t5_c = census_by_stage_area.get(("t5_post_restart_census", "area_c"))
    ctrl_info = bridge_spawn_info.get("c_persistent_control")
    ctrl_scen = spawn_records.get("c_persistent_control", {})

    if (
        not server_epoch_new
        or server_epoch_new == server_epoch_old
        or c_t3_post_c is None
        or c_t5_c is None
        or not c_t3_post_c["job_complete"]
        or not c_t5_c["job_complete"]
        or c_t5_c["inst"] != server_epoch_new
    ):
        checks["PER-06"] = {"status": "missing", "detail": "control_not_persisted"}
    elif not ctrl_info or float(ctrl_info.get("max_hp", 0.0)) <= 0.0 or float(ctrl_info.get("health_hp", 0.0)) <= 0.0:
        checks["PER-06"] = {"status": "missing", "detail": "identity_unverifiable"}
    else:
        init_max_hp = float(ctrl_scen.get("init_max_hp", ctrl_info["max_hp"]))
        init_health_hp = float(ctrl_scen.get("init_health_hp", ctrl_info["health_hp"]))
        if init_max_hp <= 0.0 or init_health_hp <= 0.0:
            checks["PER-06"] = {"status": "missing", "detail": "identity_unverifiable"}
        else:
            t3_barrels = [r for r in c_t3_post_c["rows"] if r.get("class_name") == "Barrel_Yellow"]
            t5_barrels = [r for r in c_t5_c["rows"] if r.get("class_name") == "Barrel_Yellow"]
            if not t3_barrels or not t5_barrels:
                checks["PER-06"] = {"status": "missing", "detail": "control_not_persisted"}
            else:
                b_t3 = t3_barrels[0]
                b_t5 = t5_barrels[0]
                pers_t3 = str(b_t3.get("pers_id") or "")
                pers_t5 = str(b_t5.get("pers_id") or "")

                # Anti-fabrication: after restart from storage, pers_id must be valid non-zero and not constant across distinct entities
                all_t5_pers_ids = [
                    str(r.get("pers_id") or "")
                    for r in c_t5_c["rows"]
                    if _is_nonzero_pers_id(r.get("pers_id"))
                ]
                if not _is_nonzero_pers_id(pers_t5):
                    checks["PER-06"] = {"status": "missing", "detail": "identity_unverifiable"}
                elif len(all_t5_pers_ids) != len(set(all_t5_pers_ids)):
                    checks["PER-06"] = {"status": "fail", "detail": "constant_duplicate_pers_id"}
                else:
                    per06_fail: list[str] = []
                    if _is_nonzero_pers_id(pers_t3) and pers_t5 != pers_t3:
                        per06_fail.append("pers_id_mismatch")

                    hp_t5 = float(b_t5.get("health_hp", 0.0))
                    max_t5 = float(b_t5.get("max_hp", 0.0))
                    if (
                        max_t5 <= 0.0
                        or abs(hp_t5 - init_health_hp) > 1e-2
                        or abs(hp_t5 - max_t5 * 0.8450) > 1e-2
                    ):
                        per06_fail.append("health_mark_mismatch")

                    dist_3d = math.sqrt(
                        (float(b_t5.get("pos_x_m", 0.0)) - float(b_t3.get("pos_x_m", 0.0))) ** 2
                        + (float(b_t5.get("pos_y_m", 0.0)) - float(b_t3.get("pos_y_m", 0.0))) ** 2
                        + (float(b_t5.get("pos_z_m", 0.0)) - float(b_t3.get("pos_z_m", 0.0))) ** 2
                    )
                    if dist_3d >= 0.5:
                        per06_fail.append(f"pos_drift={dist_3d:.4f}m")

                    for ang_k in ("yaw_deg", "pitch_deg", "roll_deg"):
                        if _angle_diff_deg(float(b_t5.get(ang_k, 0.0)), float(b_t3.get(ang_k, 0.0))) > 1.0:
                            per06_fail.append(f"{ang_k}_drift")

                    if int(round(float(b_t5.get("alive_b", 0.0)))) != 1 or int(round(float(b_t5.get("inv_children_n", 0.0)))) != 1:
                        per06_fail.append("control_dead_or_child_count_mismatch")

                    b_t5_nid = str(b_t5.get("net_id") or "")
                    fireplaces = [
                        r
                        for r in c_t5_c["rows"]
                        if r.get("class_name") == "Fireplace"
                        and r.get("loc_kind") == "cargo"
                        and r.get("parent_net_id") == b_t5_nid
                    ]
                    if len(fireplaces) != 1:
                        per06_fail.append("control_child_fireplace_missing")

                    if per06_fail:
                        checks["PER-06"] = {"status": "fail", "detail": ";".join(per06_fail)}
                    else:
                        checks["PER-06"] = {"status": "pass", "detail": "ok"}

    # N39 & N49: cobertura de las criaturas tras el reinicio.
    t5_censuses = [
        c for c in censuses_by_stage.get("t5_post_restart_census", [])
        if c["job_complete"] and c["inst"] == server_epoch_new
    ]

    # Ordenes que alteran el mundo (MENOR: las lecturas puras no cuentan). El evaluador es ciego a las
    # inyecciones, asi que un per_census_start aceptado cuenta como mutador (no puede saber si el peer
    # lo uso para borrar algo); los rechazados no tuvieron efecto.
    def _op_is_mutating(op: _BridgeOperation) -> bool:
        if op.status == "rejected":
            return False
        if op.verb in (
            "per_apply_scene",
            "per_reset_scene",
            "per_child_transition",
            "per_spawn_raw",
            "per_cleanup_qa",
            "per_census_start",
        ):
            return True
        if op.verb in ("job_read", "job_free", "job_stop", "per_status", "ground_query"):
            return False
        return op.verb.startswith("per_")

    t3_post_max_seq = max(
        (c["seq_idx"] for c in censuses_by_stage.get("t3_post_reset_census", [])),
        default=-1,
    )
    post_t3_mutating_old_ops = [
        op
        for op in ordered_ops
        if op.inst == server_epoch_old and op.seq_idx > t3_post_max_seq and _op_is_mutating(op)
    ]

    old_epoch_ticks: list[float] = []
    for bop in ordered_ops:
        if bop.peer == "server" and bop.inst == server_epoch_old:
            for tval in (bop.recv_ms, bop.done_ms):
                if tval > 0.0:
                    old_epoch_ticks.append(tval)
    for c_item in censuses:
        if c_item["inst"] == server_epoch_old:
            for tk in ("snap_tick_ms", "released_tick_ms", "free_done_ms"):
                if float(c_item.get(tk, 0.0)) > 0.0:
                    old_epoch_ticks.append(float(c_item[tk]))
    max_old_srv_tick_ms = max(old_epoch_ticks, default=0.0)

    # MEN-4 / N49: los extremos temporales se acreditan con LECTURAS DEL PROPIO PEER y con el reloj del
    # bridge (t_ms, lo escribe el nucleo), sin etiquetas del runner:
    #  - parada: hay un per_status del epoch viejo posterior a t3_post_reset_census (su tick_ms del peer
    #    >= los ticks de ese censo), sin ordenes mutadoras viejas despues; el tiempo que el peer viejo siguio
    #    vivo tras esa lectura (ultimo evento del bridge con su inst - t_ms del resultado) cuenta como
    #    ventana sin muestrear;
    #  - carga: la primera orden del epoch nuevo es un per_status cuyo tick_ms (del peer) es pequeno
    #    (<= N49_MAX_FIRST_NEW_TICK_MS) y posterior al hello nuevo; el intervalo hello->lectura cuenta como
    #    ventana sin muestrear.
    # Si algo falta (incl. t_ms), N49 queda sin acreditar y PER-07/08 dan INCONCLUSO. Limite: la parada
    # real del servidor y la carga real solo se acotan por esos testigos; no hay marca del peer en ellas.
    def _ev_t_ms(ev: dict[str, Any]) -> float | None:
        v = ev.get("t_ms")
        return float(v) if _is_finite_num(v) else None

    t3_post_max_tick = max(
        (
            max(float(c.get("snap_tick_ms", 0.0)), float(c.get("released_tick_ms", 0.0)), float(c.get("free_done_ms", 0.0)))
            for c in censuses_by_stage.get("t3_post_reset_census", [])
            if c["job_complete"]
        ),
        default=0.0,
    )
    stop_status: tuple[_BridgeOperation, float] | None = None
    for s_bop, _s_s, s_n, _s_r in status_ops_old:
        s_tk = s_n.get("tick_ms")
        if (
            s_bop.seq_idx > t3_post_max_seq
            and t3_post_max_tick > 0.0
            and _is_finite_num(s_tk)
            and float(s_tk) >= t3_post_max_tick
            and (stop_status is None or s_bop.seq_idx > stop_status[0].seq_idx)
        ):
            stop_status = (s_bop, float(s_tk))
    stop_gap_ms: float | None = None
    if stop_status is not None and not post_t3_mutating_old_ops and stop_status[0].result_t_ms is not None:
        old_alive_ts = []
        for ev in bridge_events:
            if ev.get("peer") == "server" and str(ev.get("inst") or "") == server_epoch_old:
                tv = _ev_t_ms(ev)
                if tv is not None:
                    old_alive_ts.append(tv)
        if old_alive_ts:
            stop_gap_ms = max(0.0, max(old_alive_ts) - float(stop_status[0].result_t_ms))

    first_new_epoch_tick_ms = 0.0
    start_gap_ms: float | None = None
    new_server_ops = [
        op for op in ordered_ops if server_epoch_new and op.inst == server_epoch_new and op.peer == "server"
    ]
    first_new_op = min(new_server_ops, key=lambda o: o.seq_idx) if new_server_ops else None
    if first_new_op is not None and first_new_op.verb == "per_status" and first_new_op.status == "done":
        fn_u = _unpack_any_payload(first_new_op.read)
        fn_tk = fn_u[1].get("tick_ms") if fn_u else None
        hello_new_ts = []
        for h in hellos:
            if h.get("peer") == "server" and h.get("inst") == server_epoch_new and isinstance(h.get("raw"), dict):
                tv = _ev_t_ms(h["raw"])
                if tv is not None:
                    hello_new_ts.append(tv)
        if (
            _is_finite_num(fn_tk)
            and 0.0 < float(fn_tk) <= N49_MAX_FIRST_NEW_TICK_MS
            and first_new_op.result_t_ms is not None
            and hello_new_ts
            and float(first_new_op.result_t_ms) >= min(hello_new_ts)
        ):
            first_new_epoch_tick_ms = float(fn_tk)
            start_gap_ms = float(first_new_op.result_t_ms) - min(hello_new_ts)

    n49_extremes_accredited = stop_gap_ms is not None and start_gap_ms is not None

    def _creature_covered_in_t5(
        creature_lid: str,
        stages_to_check: tuple[str, ...],
        *,
        is_reset_branch: bool = False,
    ) -> bool:
        sp_info = bridge_spawn_info.get(creature_lid)
        if not sp_info or not t5_censuses or max_old_srv_tick_ms <= 0.0 or first_new_epoch_tick_ms <= 0.0:
            return False
        # N49: if temporal extremes are not accredited, coverage cannot be verified
        if not n49_extremes_accredited:
            return False
        cnid = sp_info["net_id"]
        stage_obs: list[tuple[float, float, float]] = []
        for stg in stages_to_check:
            found_in_stage = False
            for c_item in censuses_by_stage.get(stg, []):
                if not c_item["job_complete"]:
                    continue
                for r in c_item["rows"]:
                    if str(r.get("own_logical_id") or "") == creature_lid or str(r.get("net_id") or "") == cnid:
                        if int(round(float(r.get("alive_b", 0.0)))) != 1:
                            return False
                        snap_t = float(c_item.get("snap_tick_ms", 0.0))
                        if snap_t <= 0.0:
                            return False
                        stage_obs.append((snap_t, float(r.get("pos_x_m", 0.0)), float(r.get("pos_z_m", 0.0))))
                        found_in_stage = True
            if not found_in_stage:
                return False
        for i in range(1, len(stage_obs)):
            if stage_obs[i][0] < stage_obs[i - 1][0]:
                return False

        last_obs_tick_ms = stage_obs[-1][0]
        if is_reset_branch:
            if not ret_resets or c_t3_post_ret is None or not c_t3_post_ret["job_complete"]:
                return False
            reset_tick_ms = float(ret_resets[0][1].get("tick_ms", 0.0))
            post_ret_snap_ms = float(c_t3_post_ret.get("snap_tick_ms", 0.0))
            if reset_tick_ms < last_obs_tick_ms or post_ret_snap_ms < reset_tick_ms:
                return False
            if any(
                str(r.get("own_logical_id") or "") == creature_lid or str(r.get("net_id") or "") == cnid
                for r in c_t3_post_ret["rows"]
            ):
                return False
            dt_pre_ms = max(0.0, reset_tick_ms - last_obs_tick_ms) + max(0.0, max_old_srv_tick_ms - post_ret_snap_ms) + float(stop_gap_ms or 0.0)
        else:
            if max_old_srv_tick_ms < last_obs_tick_ms:
                return False
            dt_pre_ms = max(0.0, max_old_srv_tick_ms - last_obs_tick_ms) + float(stop_gap_ms or 0.0)

        v_bound_m_s = 6.0
        for i in range(1, len(stage_obs)):
            dt_s = (stage_obs[i][0] - stage_obs[i - 1][0]) / 1000.0
            if dt_s > 1e-3:
                dist_m = math.hypot(stage_obs[i][1] - stage_obs[i - 1][1], stage_obs[i][2] - stage_obs[i - 1][2])
                v_bound_m_s = max(v_bound_m_s, dist_m / dt_s)

        for _obs_t, lx, lz in stage_obs:
            covered = False
            for tc in t5_censuses:
                tc_snap_ms = float(tc.get("snap_tick_ms", 0.0))
                if tc_snap_ms < first_new_epoch_tick_ms:
                    continue
                dt_post_ms = max(0.0, tc_snap_ms - first_new_epoch_tick_ms) + float(start_gap_ms or 0.0)
                dt_unsampled_s = (dt_pre_ms + dt_post_ms) / 1000.0
                reach_r_m = max(15.0, v_bound_m_s * dt_unsampled_s)
                if math.hypot(lx - float(tc["center_x_m"]), lz - float(tc["center_z_m"])) + reach_r_m <= float(tc["radius_m"]) + 1e-6:
                    covered = True
                    break
            if not covered:
                return False
        return True

    # =========================================================================
    # PER-07: Non-reappearance after restart in reset branch
    # =========================================================================
    c_t5_a = census_by_stage_area.get(("t5_post_restart_census", "area_a"))
    c_t5_ret = census_by_stage_area.get(("t5_post_restart_census", retained_area_id))

    if checks["PER-06"]["status"] != "pass":
        checks["PER-07"] = {"status": "missing", "detail": "control_not_persisted"}
    elif (
        c_t5_a is None
        or c_t5_ret is None
        or not c_t5_a["job_complete"]
        or not c_t5_ret["job_complete"]
        or c_t5_a["inst"] != server_epoch_new
        or c_t5_ret["inst"] != server_epoch_new
    ):
        checks["PER-07"] = {"status": "missing", "detail": "missing_t5_reset_branch_census"}
    elif (
        c_t5_a["director_present_b"] != 1
        or c_t5_a["director_inv_readable_b"] != 1
        or c_t5_a["director_uid"] != director_uid_t0
    ):
        checks["PER-07"] = {"status": "missing", "detail": "director_absent_or_uid_mismatch"}
    elif post_t3_mutating_old_ops:
        checks["PER-07"] = {"status": "missing", "detail": "post_t3_mutating_old_ops"}
    elif not n49_extremes_accredited:
        checks["PER-07"] = {"status": "missing", "detail": "post_restart_creature_coverage_missing:N49_extremes_unaccredited"}
    elif not (
        _creature_covered_in_t5(
            f"{retained_pfx}_inf_1",
            ("t2_census_10min", "t3_pre_reset_census"),
            is_reset_branch=True,
        )
        and _creature_covered_in_t5(
            f"{retained_pfx}_ani_1",
            ("t2_census_10min", "t3_pre_reset_census"),
            is_reset_branch=True,
        )
    ):
        checks["PER-07"] = {"status": "missing", "detail": "post_restart_creature_coverage_missing"}
    else:
        reset_vanish_classes = {
            e["class_name"]
            for sc in (retained_scene_id, "scene_a_clean")
            for e in fixture["scenes"][sc]["entities"]
            if e["must_vanish_on_restart_b"] == 1
        }
        reset_vanish_lids = {
            e["logical_id"]
            for sc in (retained_scene_id, "scene_a_clean")
            for e in fixture["scenes"][sc]["entities"]
            if e["must_vanish_on_restart_b"] == 1
        }
        creature_classes_reset = {"ZmbM_PatrolNormal_Summer", "Animal_CapraHircus_Brown"}
        foreign_allowed_classes = {"WaterBottle", "Compass", "BandageDressing"}

        relevant_t5_reset_censuses = [
            c
            for c in t5_censuses
            if c["area_id"] in ("area_a", retained_area_id)
            or f"{retained_pfx}_inf_1" in c["raw_area_tag"]
            or f"{retained_pfx}_ani_1" in c["raw_area_tag"]
        ]

        per07_fail: list[str] = []
        per07_missing: list[str] = []
        for c_item in relevant_t5_reset_censuses:
            for r in c_item["rows"]:
                cname = str(r.get("class_name") or "")
                olid = str(r.get("own_logical_id") or "")
                ouid = str(r.get("owner_uid") or "")
                max_hp = float(r.get("max_hp", 0.0))
                hp = float(r.get("health_hp", 0.0))

                if olid in reset_vanish_lids:
                    per07_fail.append(f"reappeared_logical_id:{olid}")
                    continue
                if cname in creature_classes_reset:
                    if max_hp > 0.0 and abs(hp - max_hp * 0.7325) <= 1e-2:
                        per07_fail.append(f"reappeared_marked_creature:{cname}")
                    else:
                        per07_missing.append("ce_fauna_intrusion")
                    continue
                if ouid == director_uid_t0:
                    if cname == "WorkingGloves_Beige":
                        per07_fail.append("reappeared_director_gloves:WorkingGloves_Beige")
                    continue
                if cname in foreign_allowed_classes and max_hp > 0.0 and abs(hp - max_hp * 0.6150) <= 1e-2:
                    continue
                if cname in reset_vanish_classes:
                    per07_fail.append(f"reappeared_class:{cname}")

        if per07_fail:
            checks["PER-07"] = {"status": "fail", "detail": ";".join(per07_fail[:5])}
        elif per07_missing:
            checks["PER-07"] = {"status": "missing", "detail": ";".join(per07_missing[:5])}
        else:
            checks["PER-07"] = {"status": "pass", "detail": "ok"}

    # =========================================================================
    # PER-08: Non-reappearance after restart in unreset branch (CX-04) + Grill metric
    # =========================================================================
    b_for_nid = bridge_spawn_info.get("b_foreign_in_chest", {}).get("net_id", "")
    c_t5_b = census_by_stage_area.get(("t5_post_restart_census", "area_b"))
    if c_t3_post_b and c_t3_post_b["job_complete"] and c_t5_b and c_t5_b["job_complete"] and b_for_nid:
        pre_b_for = next((r for r in c_t3_post_b["rows"] if str(r.get("net_id") or "") == b_for_nid), None)
        post_b_for = next(
            (r for r in c_t5_b["rows"] if r.get("class_name") == "OrienteeringCompass"),
            None,
        )
        if pre_b_for is not None:
            metrics["grill_foreign_in_unreset_own_container"] = {
                "readings_available_b": 1,
                "pre": {
                    "net_id": str(pre_b_for.get("net_id") or ""),
                    "pers_id": str(pre_b_for.get("pers_id") or ""),
                    "class_name": str(pre_b_for.get("class_name") or ""),
                    "loc_kind": str(pre_b_for.get("loc_kind") or ""),
                    "parent_class": str(pre_b_for.get("parent_class") or ""),
                    "parent_net_id": str(pre_b_for.get("parent_net_id") or ""),
                    "slot_name": str(pre_b_for.get("slot_name") or ""),
                    "pos_m": [
                        float(pre_b_for.get("pos_x_m", 0.0)),
                        float(pre_b_for.get("pos_y_m", 0.0)),
                        float(pre_b_for.get("pos_z_m", 0.0)),
                    ],
                    "ori_deg": [
                        float(pre_b_for.get("yaw_deg", 0.0)),
                        float(pre_b_for.get("pitch_deg", 0.0)),
                        float(pre_b_for.get("roll_deg", 0.0)),
                    ],
                    "max_hp": float(pre_b_for.get("max_hp", 0.0)),
                    "health_hp": float(pre_b_for.get("health_hp", 0.0)),
                    "inv_children_n": int(round(float(pre_b_for.get("inv_children_n", 0.0)))),
                },
                "post": None
                if post_b_for is None
                else {
                    "net_id": str(post_b_for.get("net_id") or ""),
                    "pers_id": str(post_b_for.get("pers_id") or ""),
                    "class_name": str(post_b_for.get("class_name") or ""),
                    "loc_kind": str(post_b_for.get("loc_kind") or ""),
                    "parent_class": str(post_b_for.get("parent_class") or ""),
                    "parent_net_id": str(post_b_for.get("parent_net_id") or ""),
                    "slot_name": str(post_b_for.get("slot_name") or ""),
                    "pos_m": [
                        float(post_b_for.get("pos_x_m", 0.0)),
                        float(post_b_for.get("pos_y_m", 0.0)),
                        float(post_b_for.get("pos_z_m", 0.0)),
                    ],
                    "ori_deg": [
                        float(post_b_for.get("yaw_deg", 0.0)),
                        float(post_b_for.get("pitch_deg", 0.0)),
                        float(post_b_for.get("roll_deg", 0.0)),
                    ],
                    "max_hp": float(post_b_for.get("max_hp", 0.0)),
                    "health_hp": float(post_b_for.get("health_hp", 0.0)),
                    "inv_children_n": int(round(float(post_b_for.get("inv_children_n", 0.0)))),
                },
            }

    c_t5_d = census_by_stage_area.get(("t5_post_restart_census", "area_d")) if has_scene_d else None
    if checks["PER-06"]["status"] != "pass":
        checks["PER-08"] = {"status": "missing", "detail": "control_not_persisted"}
    elif (
        c_t3_post_b is None
        or not c_t3_post_b["job_complete"]
        or c_t5_b is None
        or not c_t5_b["job_complete"]
        or c_t5_b["inst"] != server_epoch_new
        or (has_scene_d and (c_t5_d is None or not c_t5_d["job_complete"] or c_t5_d["inst"] != server_epoch_new))
    ):
        checks["PER-08"] = {"status": "missing", "detail": "missing_t5_unreset_branch_census"}
    elif (
        c_t5_b["director_present_b"] != 1
        or c_t5_b["director_inv_readable_b"] != 1
        or c_t5_b["director_uid"] != director_uid_t0
    ):
        checks["PER-08"] = {"status": "missing", "detail": "director_absent_or_uid_mismatch"}
    elif post_t3_mutating_old_ops:
        checks["PER-08"] = {"status": "missing", "detail": "post_t3_mutating_old_ops"}
    elif not n49_extremes_accredited:
        checks["PER-08"] = {"status": "missing", "detail": "post_restart_creature_coverage_missing:N49_extremes_unaccredited"}
    elif not (
        _creature_covered_in_t5("b_inf_1", ("t2_census_10min", "t3_pre_reset_census", "t3_post_reset_census"))
        and _creature_covered_in_t5("b_ani_1", ("t2_census_10min", "t3_pre_reset_census", "t3_post_reset_census"))
    ):
        checks["PER-08"] = {"status": "missing", "detail": "post_restart_creature_coverage_missing"}
    else:
        per08_fail: list[str] = []
        per08_missing: list[str] = []

        # (1) Verify scene_b 3 garments in t3_post_reset_census and b_cross_child transition in t1/t3_pre (N50)
        b_act_nid = bridge_spawn_info.get("b_act_1", {}).get("net_id", "")
        b_cap_nid = bridge_spawn_info.get("b_act_1_cap_worn", {}).get("net_id", "")
        b_arm_nid = bridge_spawn_info.get("b_act_1_armband_drop", {}).get("net_id", "")
        b_glv_nid = bridge_spawn_info.get("b_act_1_gloves_dir", {}).get("net_id", "")

        t3_post_b_map = {str(r.get("net_id") or ""): r for r in c_t3_post_b["rows"]}
        for c_extra in censuses_by_stage.get("t3_post_reset_census", []):
            if c_extra["job_complete"]:
                for r in c_extra["rows"]:
                    if r.get("owner_uid") == director_uid_t0:
                        t3_post_b_map[str(r.get("net_id") or "")] = r

        r_bcap = t3_post_b_map.get(b_cap_nid)
        r_barm = t3_post_b_map.get(b_arm_nid)
        r_bglv = t3_post_b_map.get(b_glv_nid)
        if not r_bcap or r_bcap.get("loc_kind") != "attachment" or r_bcap.get("parent_net_id") != b_act_nid:
            per08_fail.append("b_act_1_cap_worn_not_attached_pre_restart")
        if not r_barm or r_barm.get("loc_kind") != "ground" or r_barm.get("parent_net_id") != "":
            per08_fail.append("b_act_1_armband_drop_not_on_ground_pre_restart")
        if not r_bglv or r_bglv.get("owner_uid") != director_uid_t0 or not r_bglv.get("parent_net_id"):
            per08_fail.append("b_act_1_gloves_dir_not_in_director_pre_restart")

        if "b_cross_child" not in transitions_by_lid or transitions_by_lid["b_cross_child"][0].get("transition_status") != "ok":
            per08_fail.append("b_cross_child_not_transitioned")

        # (2) Verify 0 entities with role == unreset_cx04 and must_vanish_on_restart_b == 1 reappear in t5
        unreset_vanish_classes = {
            e["class_name"]
            for sc in (["scene_b"] + (["scene_d"] if has_scene_d else []))
            for e in fixture["scenes"][sc]["entities"]
            if e["must_vanish_on_restart_b"] == 1
        }
        unreset_vanish_lids = {
            e["logical_id"]
            for sc in (["scene_b"] + (["scene_d"] if has_scene_d else []))
            for e in fixture["scenes"][sc]["entities"]
            if e["must_vanish_on_restart_b"] == 1
        }
        creature_classes_b = {"ZmbF_CitizenANormal_Beige", "Animal_BosTaurus_Brown"}

        relevant_t5_unreset = [
            c
            for c in t5_censuses
            if c["area_id"] in (["area_b", "area_a", retained_area_id] + (["area_d"] if has_scene_d else []))
            or "b_inf_1" in c["raw_area_tag"]
            or "b_ani_1" in c["raw_area_tag"]
        ]

        for c_item in relevant_t5_unreset:
            aid = c_item["area_id"]
            for r in c_item["rows"]:
                cname = str(r.get("class_name") or "")
                olid = str(r.get("own_logical_id") or "")
                ouid = str(r.get("owner_uid") or "")
                max_hp = float(r.get("max_hp", 0.0))
                hp = float(r.get("health_hp", 0.0))

                if olid in unreset_vanish_lids:
                    per08_fail.append(f"reappeared_logical_id:{olid}")
                    continue
                if cname in creature_classes_b:
                    if max_hp > 0.0 and abs(hp - max_hp * 0.7325) <= 1e-2:
                        per08_fail.append(f"reappeared_marked_creature:{cname}")
                    else:
                        per08_missing.append("ce_fauna_intrusion")
                    continue
                if ouid == director_uid_t0:
                    if cname == "WorkingGloves_Yellow":
                        per08_fail.append("reappeared_director_gloves:WorkingGloves_Yellow")
                    continue
                if cname == "OrienteeringCompass" and max_hp > 0.0 and abs(hp - max_hp * 0.6150) <= 1e-2:
                    continue
                if aid in ("area_a", retained_area_id) and cname in ("WaterBottle", "Compass", "BandageDressing"):
                    if max_hp > 0.0 and abs(hp - max_hp * 0.6150) <= 1e-2:
                        continue
                if aid in ("area_b", "area_d") or "b_inf_1" in c_item["raw_area_tag"] or "b_ani_1" in c_item["raw_area_tag"]:
                    if cname in unreset_vanish_classes:
                        per08_fail.append(f"reappeared_in_{aid}:{cname}")
                elif cname == "SewingKit":
                    per08_fail.append("reappeared_cross_child:SewingKit")

        if per08_fail:
            checks["PER-08"] = {"status": "fail", "detail": ";".join(per08_fail[:5])}
        elif per08_missing:
            checks["PER-08"] = {"status": "missing", "detail": ";".join(per08_missing[:5])}
        else:
            checks["PER-08"] = {"status": "pass", "detail": "ok"}

    # MEN-6: prueba de contencion del recurso `per_census` (rechazo busy, primer censo integro,
    # tercer censo aceptado tras liberar). Sin ella PER-09 no puede pasar.
    busy_probe_ok = False
    busy_probe_detail = "census_busy_contention_unobserved"
    for _pr in timeline["census_busy_probes"]:
        _first = next((c for c in censuses if c["op_id"] == _pr["first_op_id"]), None)
        if _first is None or not _first["job_complete"]:
            busy_probe_detail = "census_first_job_not_intact_after_busy"
            continue
        _later = [
            op
            for op in ordered_ops
            if op.verb == "per_census_start"
            and op.peer == "server"
            and op.inst == _pr["inst"]
            and op.seq_idx > _pr["free_seq"]
        ]
        _next = min(_later, key=lambda o: o.seq_idx) if _later else None
        _next_c = next((c for c in censuses if _next is not None and c["op_id"] == _next.op_id), None)
        if _next is None or _next.status != "done" or _next_c is None or not _next_c["job_complete"]:
            busy_probe_detail = "census_not_accepted_after_release"
            continue
        busy_probe_ok = True
        break

    # =========================================================================
    # PER-09: Epoch change after restart and stale_epoch rejection with witness scene
    # =========================================================================
    # If census resource overlap was already detected, skip witness validation (fabrication takes precedence)
    if census_overlap_detected:
        checks["PER-09"] = {"status": "fail", "detail": "unprotected_census_resource_overlap"}
    elif census_wrong_reason:
        checks["PER-09"] = {"status": "fail", "detail": "census_contention_wrong_reason"}
    else:
        c_wit_pre = census_by_stage_area.get(("t5_witness_pre_census", "area_b"))
        c_wit_post = census_by_stage_area.get(("t5_witness_post_census", "area_b"))

        wit_apply_ops = [
            op
            for op in ordered_ops
            if server_epoch_new
            and op.inst == server_epoch_new
            and op.verb == "per_apply_scene"
            and op.status == "done"
        ]
        stale_reset_ops = [
            op
            for op in ordered_ops
            if server_epoch_new
            and op.inst == server_epoch_new
            and op.verb == "per_reset_scene"
            and (_unpack_any_payload(op.args) or ({}, {}, []))[0].get("expect_epoch") == server_epoch_old
        ]
        stale_apply_ops = [
            op
            for op in ordered_ops
            if server_epoch_new
            and op.inst == server_epoch_new
            and op.verb == "per_apply_scene"
            and (_unpack_any_payload(op.args) or ({}, {}, []))[0].get("expect_epoch") == server_epoch_old
        ]
        cleanup_ops_new = [
            op
            for op in ordered_ops
            if server_epoch_new and op.inst == server_epoch_new and op.verb == "per_cleanup_qa"
        ]
        cleanup_new_seq = min((op.seq_idx for op in cleanup_ops_new), default=10**9)

        if len(server_hello_insts) < 2:
            checks["PER-09"] = {"status": "missing", "detail": "missing_post_restart_hello"}
        elif not server_epoch_new or server_epoch_new == server_epoch_old:
            checks["PER-09"] = {"status": "fail", "detail": "server_epoch_not_rotated"}
        elif (
            not wit_apply_ops
            or c_wit_pre is None
            or c_wit_post is None
            or not c_wit_pre["job_complete"]
            or not c_wit_post["job_complete"]
            or c_wit_pre["job_id"] == c_wit_post["job_id"]
        ):
            checks["PER-09"] = {"status": "missing", "detail": "missing_witness_census"}
        else:
            wit_apply_op = wit_apply_ops[0]
            stale_seqs = [op.seq_idx for op in (stale_reset_ops + stale_apply_ops)]
            first_stale_op_seq = min(stale_seqs, default=10**9)
            last_stale_op_seq = max(stale_seqs, default=-1)

            # BLOQ 11: associate witness status and censuses by semantic operation order, not log-line count
            wit_pre_status = [
                (bop, s, n, r)
                for (bop, s, n, r) in status_ops_new
                if wit_apply_op.seq_idx < bop.seq_idx < first_stale_op_seq
            ]
            wit_post_status = [
                (bop, s, n, r)
                for (bop, s, n, r) in status_ops_new
                if last_stale_op_seq >= 0 and last_stale_op_seq < bop.seq_idx < cleanup_new_seq
            ]
            if (
                not wit_pre_status
                or not wit_post_status
                or not (wit_apply_op.seq_idx < c_wit_pre["seq_idx"] < first_stale_op_seq)
                or not (last_stale_op_seq < c_wit_post["seq_idx"] < cleanup_new_seq)
            ):
                checks["PER-09"] = {"status": "missing", "detail": "missing_witness_status"}
            else:
                per09_fail: list[str] = []
                if not stale_reset_ops or any(
                    op.status != "rejected" or op.reason != "stale_epoch" for op in stale_reset_ops
                ):
                    per09_fail.append("stale_reset_not_rejected")
                if not stale_apply_ops or any(
                    op.status != "rejected" or op.reason != "stale_epoch" for op in stale_apply_ops
                ):
                    per09_fail.append("stale_apply_not_rejected")

                # BLOQ 10: validate the witness per_apply_scene and census rows against fixture["scenes"]["scene_b"]
                wit_in_u = _unpack_any_payload(wit_apply_op.args)
                wit_out_u = _unpack_any_payload(wit_apply_op.read)
                wit_in_s, _wit_in_n, _wit_in_r = wit_in_u if wit_in_u else ({}, {}, [])
                wit_out_s, wit_out_n, wit_out_r = wit_out_u if wit_out_u else ({}, {}, [])
                fix_scene_b = {e["logical_id"]: e for e in fixture["scenes"]["scene_b"]["entities"]}
                wit_op_id = wit_out_s.get("scene_op_id") or wit_in_s.get("scene_op_id") or ""
                if (
                    wit_in_s.get("scene_id") != "scene_b"
                    or wit_out_s.get("scene_id") != "scene_b"
                    or wit_out_s.get("apply_status") != "ok"
                    or int(round(float(wit_out_n.get("gen_n", 0.0)))) != 1
                    or len(wit_out_r) != len(fix_scene_b)
                    or not wit_op_id
                ):
                    per09_fail.append("witness_apply_scene_invalid")

                wit_out_by_lid = {str(r.get("logical_id") or ""): r for r in wit_out_r}
                wit_nid_by_lid: dict[str, str] = {}
                # Nuevo 4: unicidad por epoch - solo verificar dentro del epoch nuevo, no contra epoch viejo
                # old_scene_b_nids = { ... }  # REMOVIDO: no se exige unicidad entre epochs
                for wlid, wf_ent in fix_scene_b.items():
                    worow = wit_out_by_lid.get(wlid)
                    if not worow:
                        per09_fail.append(f"witness_apply_missing:{wlid}")
                        continue
                    wnid = str(worow.get("net_id") or "")
                    if (
                        not _valid_net_id(wnid, wlid)
                        or worow.get("class_name") != wf_ent["class_name"]
                        or int(round(float(worow.get("ok_b", 0.0)))) != 1
                        or int(round(float(worow.get("alive_b", 0.0)))) != 1
                    ):
                        per09_fail.append(f"witness_apply_row_invalid:{wlid}")
                    wit_nid_by_lid[wlid] = wnid

                _bop_pre, _s_pre, n_pre, r_pre = wit_pre_status[-1]
                _bop_post, _s_post, n_post, r_post = wit_post_status[0]

                sc_b_pre = next((r for r in r_pre if r.get("scene_id") == "scene_b"), None)
                sc_b_post = next((r for r in r_post if r.get("scene_id") == "scene_b"), None)
                if (
                    not sc_b_pre
                    or not sc_b_post
                    or int(round(float(sc_b_pre.get("gen_n", 0.0)))) != 1
                    or int(round(float(sc_b_pre.get("own_alive_n", 0.0)))) != 11
                    or int(round(float(sc_b_post.get("gen_n", 0.0)))) != 1
                    or int(round(float(sc_b_post.get("own_alive_n", 0.0)))) != 11
                    or sc_b_pre.get("last_op_id") != wit_op_id
                    or sc_b_pre.get("last_op_id") != sc_b_post.get("last_op_id")
                    or int(round(float(n_pre.get("registered_total_n", -1.0))))
                    != int(round(float(n_post.get("registered_total_n", -2.0))))
                    or int(round(float(n_pre.get("scenes_count_n", -1.0))))
                    != int(round(float(n_post.get("scenes_count_n", -2.0))))
                ):
                    per09_fail.append("witness_status_mismatch")

                # Nuevo 6: exigir inclusión y cobertura del director en t5 áreas obligatorias
                # Per brief :234, t5 debe incluir director en area_a, area_b, retained_area_id
                required_t5_director_areas = ["area_a", "area_b", retained_area_id]
                for aid in required_t5_director_areas:
                    c_t5_dir = census_by_stage_area.get(("t5_post_restart_census", aid))
                    if not c_t5_dir or not c_t5_dir["job_complete"]:
                        per09_fail.append(f"t5_missing_census:{aid}")
                        continue
                    if c_t5_dir["include_director_b"] != 1:
                        per09_fail.append(f"t5_director_not_included:{aid}")
                    if c_t5_dir["director_present_b"] != 1 or c_t5_dir["director_inv_readable_b"] != 1:
                        per09_fail.append(f"t5_director_unreadable:{aid}")

                pre_w_map = {str(r.get("net_id") or ""): r for r in c_wit_pre["rows"]}
                post_w_map = {str(r.get("net_id") or ""): r for r in c_wit_post["rows"]}
                if (
                    len(c_wit_pre["rows"]) != len(pre_w_map)
                    or len(c_wit_post["rows"]) != len(post_w_map)
                    or len(pre_w_map) < 11
                    or set(pre_w_map.keys()) != set(post_w_map.keys())
                ):
                    per09_fail.append("witness_census_added_or_removed_entities")
                else:
                    for wlid, wf_ent in fix_scene_b.items():
                        wnid = wit_nid_by_lid.get(wlid, "")
                        wrow = pre_w_map.get(wnid)
                        if not wrow:
                            per09_fail.append(f"witness_census_missing:{wlid}")
                            continue
                        wcat = wf_ent["cat"]
                        wpid = wf_ent["parent_id"]
                        exp_ai = 1 if wcat in ("infected", "animal") else 0
                        if (
                            wrow.get("class_name") != wf_ent["class_name"]
                            or wrow.get("own_logical_id") != wlid
                            or int(round(float(wrow.get("own_b", 0.0)))) != 1
                            or int(round(float(wrow.get("alive_b", 0.0)))) != 1
                            or int(round(float(wrow.get("ai_agent_b", -1.0)))) != exp_ai
                            or float(wrow.get("max_hp", 0.0)) <= 0.0
                            or float(wrow.get("health_hp", 0.0)) <= 0.0
                            or str(wrow.get("pers_id") or "") != "0:0:0:0"
                        ):
                            per09_fail.append(f"witness_census_row_invalid:{wlid}")
                            continue
                        if wpid == "":
                            wcat = wf_ent["cat"]
                            # Nuevo 5: solo raíces estáticas (prop, container, vehicle, actor) tienen checkpoint de colocación en Q9
                            # Criaturas (infected, animal) pueden moverse después de Q9
                            if wcat in ("prop", "container", "vehicle", "actor"):
                                if (
                                    wrow.get("loc_kind") != "ground"
                                    or wrow.get("parent_net_id") != ""
                                    or math.hypot(
                                        float(wrow.get("pos_x_m", 0.0)) - float(wf_ent["req_x_m"]),
                                        float(wrow.get("pos_z_m", 0.0)) - float(wf_ent["req_z_m"]),
                                    )
                                    >= 0.5
                                ):
                                    per09_fail.append(f"witness_root_placement_invalid:{wlid}")
                        else:
                            exp_wpnid = wit_nid_by_lid.get(wpid, "")
                            exp_wpclass = fix_scene_b[wpid]["class_name"]
                            wslot_req = wf_ent["slot_name"]
                            if wrow.get("parent_net_id") != exp_wpnid or wrow.get("parent_class") != exp_wpclass:
                                per09_fail.append(f"witness_child_parent_invalid:{wlid}")
                            elif wslot_req == "Cargo":
                                if wrow.get("loc_kind") != "cargo" or not str(wrow.get("slot_name") or "").startswith("Cargo"):
                                    per09_fail.append(f"witness_child_cargo_invalid:{wlid}")
                            else:
                                if wrow.get("loc_kind") != "attachment" or wrow.get("slot_name") != wslot_req:
                                    per09_fail.append(f"witness_child_attachment_invalid:{wlid}")

                        # Nuevo 7: contrastar inv_children_n con el árbol censado y bajas propias previstas
                        inv_children = int(round(float(wrow.get("inv_children_n", -1.0))))
                        if inv_children >= 0:
                            # Contar hijos reales en pre_w_map que tengan este wnid como parent_net_id
                            # Solo contar entidades propias (own_b=1), no director foreign ni otros ajenos
                            actual_children = sum(
                                1 for r in pre_w_map.values()
                                if str(r.get("parent_net_id") or "") == wnid
                                and int(round(float(r.get("own_b", 0.0)))) == 1
                            )
                            # El inv_children_n declarado debe coincidir con el conteo censado actual
                            # Las bajas previstas (must_vanish_on_restart_b) se verifican por separado en PER-07/08
                            if inv_children != actual_children:
                                per09_fail.append(f"inv_children_n_mismatch:{wlid}:declared={inv_children},censused={actual_children}")

                # Verify no unexpected non-director rows in witness census
                allowed_wit_nids = set(wit_nid_by_lid.values())
                for wnid, wpre in pre_w_map.items():
                    if wnid not in allowed_wit_nids and wpre.get("owner_uid") != director_uid_t0:
                        if not (
                            wpre.get("class_name") == "OrienteeringCompass"
                            and int(round(float(wpre.get("own_b", -1.0)))) == 0
                        ):
                            per09_fail.append(f"witness_unexpected_entity:{wpre.get('class_name')}:{wnid}")

                creature_classes_w = {"ZmbF_CitizenANormal_Beige", "Animal_BosTaurus_Brown"}
                for wnid, wpre in pre_w_map.items():
                    wpost = post_w_map[wnid]
                    # Nuevo 9: validar filas crudas del censo testigo posterior coherentes con estado declarado
                    # Verificar alive_b, health_hp, ai_agent_b contra el estado declarado en per_status
                    # Only count own_b=1 entities (witness scene entities), not director foreign or other foreign
                    declared_alive = int(round(float(sc_b_post.get("own_alive_n", -1.0)))) if sc_b_post else -1
                    actual_alive = sum(
                        1 for r in post_w_map.values()
                        if int(round(float(r.get("own_b", 0.0)))) == 1
                        and int(round(float(r.get("alive_b", 0.0)))) == 1
                    )
                    if declared_alive >= 0 and actual_alive != declared_alive:
                        per09_fail.append(f"witness_post_census_alive_mismatch:declared={declared_alive},actual={actual_alive}")

                    if (
                        wpost.get("class_name") != wpre.get("class_name")
                        or wpost.get("loc_kind") != wpre.get("loc_kind")
                        or wpost.get("parent_class") != wpre.get("parent_class")
                        or wpost.get("parent_net_id") != wpre.get("parent_net_id")
                        or wpost.get("slot_name") != wpre.get("slot_name")
                        or wpost.get("owner_uid") != wpre.get("owner_uid")
                        or int(round(float(wpost.get("inv_children_n", -1.0))))
                        != int(round(float(wpre.get("inv_children_n", -2.0))))
                    ):
                        per09_fail.append(f"witness_entity_changed:{wnid}")
                        continue
                    if wpre.get("class_name") not in creature_classes_w and not wpre.get("owner_uid"):
                        for ck in ("pos_x_m", "pos_y_m", "pos_z_m"):
                            if abs(float(wpost.get(ck, 0.0)) - float(wpre.get(ck, 0.0))) > 1e-4:
                                per09_fail.append(f"witness_pos_changed:{wnid}:{ck}")
                        for ak in ("yaw_deg", "pitch_deg", "roll_deg"):
                            if _angle_diff_deg(float(wpost.get(ak, 0.0)), float(wpre.get(ak, 0.0))) > 1e-3:
                                per09_fail.append(f"witness_ang_changed:{wnid}:{ak}")

                if per09_fail:
                    checks["PER-09"] = {"status": "fail", "detail": ";".join(per09_fail[:5])}
                else:
                    # Nuevo 10: t6 cleanup censuses - require complete cleanup censuses
                    # Survivors QA -> FALLA; census absent -> INCONCLUSO (brief :284)
                    t6_censuses = [
                        c for c in censuses_by_stage.get("t6_post_cleanup_census", [])
                        if c["inst"] == server_epoch_new
                    ]
                    required_t6_areas = required_base_areas
                    t6_survivors: list[str] = []
                    t6_missing_areas: list[str] = []
                    for aid in required_t6_areas:
                        c_t6 = census_by_stage_area.get(("t6_post_cleanup_census", aid))
                        if c_t6 is None or not c_t6["job_complete"]:
                            t6_missing_areas.append(aid)
                            continue
                        # Check for non-director survivors
                        for r in c_t6["rows"]:
                            if r.get("owner_uid") != director_uid_t0 and int(round(float(r.get("alive_b", 0.0)))) == 1:
                                t6_survivors.append(f"{r.get('class_name')}:{r.get('net_id')}")

                    if t6_missing_areas:
                        checks["PER-09"] = {"status": "missing", "detail": f"t6_cleanup_census_absent:{','.join(t6_missing_areas)}"}
                    elif t6_survivors:
                        checks["PER-09"] = {"status": "fail", "detail": f"t6_cleanup_survivors:{';'.join(t6_survivors[:5])}"}
                    else:
                        checks["PER-09"] = {"status": "pass", "detail": "ok"}

    if checks["PER-09"]["status"] == "pass" and not busy_probe_ok:
        checks["PER-09"] = {"status": "missing", "detail": busy_probe_detail}

    # =========================================================================
    # PER-10: Static non-storage analysis on git_head + cold storage restore
    # =========================================================================
    ident = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    git_head = str(ident.get("git_head") or "")
    manifest_stamp = str(ident.get("probe_stamp") or "")

    if not git_head or not manifest_stamp or not probe_source_events:
        checks["PER-10"] = {"status": "missing", "detail": "stamp_source_unavailable"}
    else:
        try:
            computed_stamp = f03_common.compute_probe_stamp_at_commit(git_head, repo_root=repo_root)
        except Exception:
            computed_stamp = ""

        if not computed_stamp:
            checks["PER-10"] = {"status": "missing", "detail": "stamp_source_unavailable"}
        else:
            ps_ev = probe_source_events[-1]
            scen_head = str(ps_ev.get("git_head") or "")
            scen_stamp = str(ps_ev.get("probe_stamp") or "")
            persist_files = ps_ev.get("persist_files")

            exp_probe_ver = f"dsbx-qa1+{computed_stamp}"
            hello_vers_ok = bool(hellos) and all(
                str(h.get("probe_ver") or "") == exp_probe_ver for h in hellos if h.get("http") == 200
            )

            if (
                manifest_stamp != computed_stamp
                or scen_head != git_head
                or scen_stamp != computed_stamp
                or not hello_vers_ok
                or not isinstance(persist_files, dict)
                or not persist_files
            ):
                checks["PER-10"] = {"status": "missing", "detail": "artifact_unverified"}
            else:
                # BLOQ 8: Enumerate all DSBX_QA_X_Persist*.c sources in git_head and require exact set + byte-for-byte match
                required_git_sources = _get_required_persist_sources_at_commit(repo_root, git_head)
                norm_recorded: dict[str, str] = {}
                git_mismatch = required_git_sources is None
                if not git_mismatch:
                    for rel_p, recorded_text in persist_files.items():
                        if not isinstance(rel_p, str) or not isinstance(recorded_text, str):
                            git_mismatch = True
                            break
                        norm_p = _normalize_probe_rel_path(rel_p)
                        if norm_p in norm_recorded:
                            git_mismatch = True
                            break
                        norm_recorded[norm_p] = recorded_text
                    if (
                        not git_mismatch
                        and required_git_sources is not None
                        and (
                            set(norm_recorded.keys()) != set(required_git_sources.keys())
                            or any(norm_recorded[k] != required_git_sources[k] for k in required_git_sources)
                        )
                    ):
                        git_mismatch = True

                if git_mismatch:
                    checks["PER-10"] = {"status": "missing", "detail": "artifact_unverified"}
                else:
                    violations = scan_persist_enforcescript_sources(persist_files)
                    if violations:
                        checks["PER-10"] = {
                            "status": "fail",
                            "detail": ";".join(violations[:5]),
                        }
                    else:
                        # Cold storage snapshot before (t0) and after restore (t6) check.
                        # MEN-5: solo se exige en diag/retail; en offline sin ninguno de los dos eventos
                        # PER-10 queda en el analisis estatico + sello (si hay uno solo, o ambos, se valida).
                        storage_required = build_kind in ("diag", "retail")
                        if not storage_required and not storage_t0_events and not storage_restore_events:
                            checks["PER-10"] = {"status": "pass", "detail": "ok"}
                        elif not storage_t0_events or not storage_restore_events:
                            checks["PER-10"] = {
                                "status": "missing",
                                "detail": "storage_restore_incomplete",
                            }
                        else:
                            t0_ev = storage_t0_events[-1]
                            res_ev = storage_restore_events[-1]
                            t0_files = t0_ev.get("files") or t0_ev.get("snapshot")
                            post_files = (
                                res_ev.get("files")
                                or res_ev.get("restored_files")
                                or res_ev.get("snapshot")
                                or (storage_t6_events[-1].get("files") if storage_t6_events else None)
                                or (storage_t6_events[-1].get("snapshot") if storage_t6_events else None)
                            )
                            restore_ok_b = int(round(float(res_ev.get("restore_ok_b", 0.0))))

                            metrics["storage_auxiliary_fingerprint"] = {
                                "t0_files_n": len(t0_files) if isinstance(t0_files, dict) else 0,
                                "t1_present_b": 1 if storage_t1_events else 0,
                                "t2_present_b": 1 if storage_t2_events else 0,
                                "restore_ok_b": restore_ok_b,
                            }

                            if (
                                restore_ok_b != 1
                                or not isinstance(t0_files, dict)
                                or not t0_files
                                or not isinstance(post_files, dict)
                                or not post_files
                            ):
                                checks["PER-10"] = {
                                    "status": "missing",
                                    "detail": "storage_restore_incomplete",
                                }
                            else:
                                hash_ok = set(t0_files.keys()) == set(post_files.keys())
                                if hash_ok:
                                    for fpath, fmeta0 in t0_files.items():
                                        fmeta1 = post_files.get(fpath)
                                        h0 = fmeta0.get("sha256") if isinstance(fmeta0, dict) else fmeta0
                                        h1 = fmeta1.get("sha256") if isinstance(fmeta1, dict) else fmeta1
                                        if (
                                            not isinstance(h0, str)
                                            or not _SHA256_RE.match(h0)
                                            or h0 != h1
                                        ):
                                            hash_ok = False
                                            break
                                if not hash_ok:
                                    checks["PER-10"] = {
                                        "status": "missing",
                                        "detail": "storage_restore_incomplete",
                                    }
                                else:
                                    checks["PER-10"] = {"status": "pass", "detail": "ok"}

    checks_list = _checks_as_list(checks)
    failed = [c["id"] for c in checks_list if c["status"] == "fail"]
    if failed:
        # Include fabrication reasons (reused_census_job_id, lease_expired, etc.) in FALLA verdict
        out_reasons = list(failed)
        for r in reasons:
            if r not in out_reasons:
                out_reasons.append(r)
        return gate_core.make_verdict(
            SPIKE_ID,
            1,
            checks=checks_list,
            metrics=metrics,
            reasons=out_reasons,
        )

    if any(c["status"] != "pass" for c in checks_list) or reasons:
        out_reasons = list(reasons)
        for c in checks_list:
            if c["status"] != "pass":
                det = c["detail"]
                if det and det != "not_evaluated" and det not in out_reasons:
                    out_reasons.append(det)
                if c["id"] not in out_reasons:
                    out_reasons.append(c["id"])
        return gate_core.make_verdict(
            SPIKE_ID,
            2,
            checks=checks_list,
            metrics=metrics,
            reasons=out_reasons,
        )

    return gate_core.make_verdict(
        SPIKE_ID,
        0,
        checks=checks_list,
        metrics=metrics,
        reasons=[],
    )
