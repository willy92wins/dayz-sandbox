"""Pruebas de seguridad de la implementacion S-persist (ronda 7, Sol r2).

Son pruebas del runner/fake/.c de la implementacion, no del oraculo: rutas
delimitadas de storage, parada comprobada, restauracion recuperable, el
falso PASA de N49 y la limpieza que no borra lo ajeno. Todo ocurre en
carpetas temporales; nada fuera de ellas se toca.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

QA_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = QA_DIR.parent.parent
if str(QA_DIR) not in sys.path:
    sys.path.insert(0, str(QA_DIR))

import fake_ext_persist
import fake_peer
import f03_common
import s_persist_eval
import s_persist_run
import wire


def _make_env(tmp: Path):
    server = tmp / "srv"
    mission = server / "mpmissions" / "dayzOffline.chernarusplus"
    storage = mission / "storage_1"
    data = storage / "data"
    data.mkdir(parents=True)
    (data / "types.bin").write_bytes(b"types-baseline")
    (data / "events.bin").write_bytes(b"events-baseline")
    (storage / "players.db").write_bytes(b"players-baseline")
    (mission / "sentinel.txt").write_text("no tocar", encoding="utf-8")
    env = {
        "server_root_dir": str(server),
        "mission_dir": str(mission),
        "storage_dir": str(storage),
        "storage_data_dir": str(data),
        "server_exe_names": ["DayZServer_x64.exe", "DayZDiag_x64.exe"],
    }
    backup = tmp / "evidence" / "_storage_backup"
    return env, mission, storage, backup


def _tree_bytes(root: Path):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = p.read_bytes()
    return out


class _GuardedTestCase(unittest.TestCase):
    """Guardian fail-closed para todas las pruebas de este fichero.

    Cambia el cwd a una carpeta temporal propia y parchea las primitivas
    destructivas que usa el runner (en s_persist_run.py: shutil.copytree,
    shutil.rmtree y os.rename; se blindan tambien el resto de primitivas
    destructivas habituales). Cada envoltorio resuelve sus rutas y lanza
    AssertionError ANTES de delegar si alguna cae fuera de esa carpeta o
    es la raiz de la unidad. Asi, aunque fallara la validacion del runner,
    una prueba nunca puede borrar ni mover nada fuera de su temporal:
    '.' se resuelve contra el cwd temporal, no contra el cwd real.
    """

    def setUp(self):
        super().setUp()
        self._orig_cwd = os.getcwd()
        self._guard_tmp = tempfile.TemporaryDirectory(prefix="s_persist_guard_")
        self._guard_root = Path(self._guard_tmp.name).resolve()
        root = self._guard_root

        def _check(raw, rol="ruta"):
            try:
                resolved = Path(os.fspath(raw)).resolve()
            except Exception as exc:
                raise AssertionError(
                    f"guardian: {rol} no resoluble: {raw!r}"
                ) from exc
            if resolved == Path(resolved.anchor):
                raise AssertionError(
                    f"guardian: {rol} es la raiz de la unidad: {resolved}"
                )
            if resolved != root and root not in resolved.parents:
                raise AssertionError(
                    f"guardian: {rol} fuera de la carpeta de la prueba: "
                    f"{resolved} (raiz guardiana: {root})"
                )
            return resolved

        self._guard_check = _check

        def _single(real):
            def wrapper(path, *args, **kwargs):
                _check(path)
                return real(path, *args, **kwargs)

            return wrapper

        def _pair(real):
            def wrapper(src, dst, *args, **kwargs):
                _check(src, "origen")
                _check(dst, "destino")
                return real(src, dst, *args, **kwargs)

            return wrapper

        def _path_single(real):
            def wrapper(self_path, *args, **kwargs):
                _check(self_path)
                return real(self_path, *args, **kwargs)

            return wrapper

        # Rutas externas creadas por la metaprueba (centinela): se borran
        # en el teardown, ya sin parche, porque rmtree delega en os.unlink.
        self._guard_external_cleanup = []
        self._real_rmtree = shutil.rmtree
        self._guard_patchers = [
            mock.patch.object(shutil, "rmtree", _single(shutil.rmtree)),
            mock.patch.object(shutil, "copytree", _pair(shutil.copytree)),
            mock.patch.object(shutil, "copy2", _pair(shutil.copy2)),
            mock.patch.object(shutil, "copyfile", _pair(shutil.copyfile)),
            mock.patch.object(shutil, "move", _pair(shutil.move)),
            mock.patch.object(os, "rename", _pair(os.rename)),
            mock.patch.object(os, "replace", _pair(os.replace)),
            mock.patch.object(os, "remove", _single(os.remove)),
            mock.patch.object(os, "unlink", _single(os.unlink)),
            mock.patch.object(os, "rmdir", _single(os.rmdir)),
            mock.patch.object(Path, "unlink", _path_single(Path.unlink)),
            mock.patch.object(Path, "rmdir", _path_single(Path.rmdir)),
        ]
        for patcher in self._guard_patchers:
            patcher.start()
        os.chdir(self._guard_root)
        self.addCleanup(self._guard_teardown)

    def _guard_teardown(self):
        for patcher in reversed(self._guard_patchers):
            patcher.stop()
        os.chdir(self._orig_cwd)
        for external in self._guard_external_cleanup:
            self._real_rmtree(external, ignore_errors=True)
        self._guard_tmp.cleanup()

    def _inside_tmp(self):
        """Subcarpeta temporal dentro de la carpeta guardiana."""
        return tempfile.TemporaryDirectory(dir=self._guard_root)


class TestGuardian(_GuardedTestCase):
    def test_guardian_blocks_outside_and_allows_inside(self):
        outside_root = Path(tempfile.mkdtemp(prefix="s_persist_sentinel_")).resolve()
        # Se borra en el teardown, ya sin parche (ver _guard_teardown).
        self._guard_external_cleanup.append(outside_root)
        sentinel = outside_root / "centinela"
        sentinel.mkdir()
        marker = sentinel / "fichero.txt"
        marker.write_text("centinela", encoding="utf-8")
        with self.assertRaises(AssertionError):
            shutil.rmtree(sentinel)
        self.assertTrue(sentinel.is_dir())
        self.assertEqual(marker.read_text(encoding="utf-8"), "centinela")

        renamed = outside_root / "renombrada"
        with self.assertRaises(AssertionError):
            os.rename(sentinel, renamed)
        self.assertTrue(sentinel.is_dir())
        self.assertEqual(marker.read_text(encoding="utf-8"), "centinela")
        self.assertFalse(renamed.exists())

        inside = self._guard_root / "borrable"
        inside.mkdir()
        (inside / "fichero.txt").write_text("dentro", encoding="utf-8")
        shutil.rmtree(inside)
        self.assertFalse(inside.exists())

        src = self._guard_root / "origen.txt"
        dst = self._guard_root / "destino.txt"
        src.write_text("mover", encoding="utf-8")
        os.rename(src, dst)
        self.assertEqual(dst.read_text(encoding="utf-8"), "mover")


class TestStoragePaths(_GuardedTestCase):
    def test_rejected_paths_delete_nothing(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            before_storage = _tree_bytes(storage)
            bad_envs = []
            e = dict(env); e["storage_dir"] = "."; bad_envs.append(("dot", e, backup))
            e = dict(env); e["storage_dir"] = str(Path(tmp.anchor)); bad_envs.append(("root", e, backup))
            e = dict(env); e["storage_dir"] = "storage_1"; bad_envs.append(("relative", e, backup))
            e = dict(env); e["storage_dir"] = str(mission / "storage_x"); bad_envs.append(("bad_leaf", e, backup))
            e = dict(env); e["storage_dir"] = str(tmp / "srv" / "storage_1"); bad_envs.append(("outside_mission", e, backup))
            bad_envs.append(("overlap_backup_inside", dict(env), storage / "backup"))
            bad_envs.append(("overlap_backup_parent", dict(env), mission))
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                for name, bad_env, bad_backup in bad_envs:
                    with self.subTest(case=name):
                        self.assertIsNone(s_persist_run._validate_storage_env(bad_env, bad_backup))
                        with self.assertRaises(RuntimeError):
                            s_persist_run._backup_storage(bad_env, bad_backup, "t0")
                        ok_r, _snap_r, err_r = s_persist_run._restore_storage(bad_env, bad_backup, {})
                        self.assertEqual(ok_r, 0)
                        self.assertEqual(err_r, "storage_path_rejected")
            self.assertEqual(_tree_bytes(storage), before_storage)
            self.assertEqual((mission / "sentinel.txt").read_text(encoding="utf-8"), "no tocar")
            self.assertFalse(backup.exists())

    def test_valid_path_accepted_and_resolved(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            checked = s_persist_run._validate_storage_env(env, backup)
            self.assertIsNotNone(checked)
            self.assertEqual(Path(checked["storage_dir"]), storage.resolve())
            self.assertEqual(Path(checked["storage_dir"]).name, "storage_1")


class TestServerStoppedGate(_GuardedTestCase):
    def test_query_error_is_unknown_and_blocks_copy(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            self.assertEqual(s_persist_run._classify_server_processes(None, env), "unknown")
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=None):
                self.assertEqual(s_persist_run._server_state(env), "unknown")
                ok, err = s_persist_run._require_server_stopped(env)
                self.assertFalse(ok)
                self.assertEqual(err, "server_state_unknown")
                with self.assertRaises(RuntimeError):
                    s_persist_run._backup_storage(env, backup, "t0")
                ok2, _snap2, err2 = s_persist_run._restore_storage(env, backup, {})
                self.assertEqual(ok2, 0)
                self.assertEqual(err2, "server_state_unknown")
            self.assertFalse(backup.exists())
            self.assertTrue((storage / "players.db").exists())

    def test_diag_client_is_not_the_server(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            mission_s = str(mission)
            diag_client = [{
                "name": "DayZDiag_x64.exe", "pid": 11,
                "command_line": f"DayZDiag_x64.exe -connect=127.0.0.1 -mission={mission_s}",
            }]
            self.assertEqual(s_persist_run._classify_server_processes(diag_client, env), "stopped")
            other_server = [{
                "name": "DayZServer_x64.exe", "pid": 12,
                "command_line": "DayZServer_x64.exe -mission=C:/otra/mision -profiles=C:/otra",
            }]
            self.assertEqual(s_persist_run._classify_server_processes(other_server, env), "running")
            this_server = [{
                "name": "DayZServer_x64.exe", "pid": 13,
                "command_line": f"DayZServer_x64.exe -mission={mission_s} -profiles={mission_s}",
            }]
            self.assertEqual(s_persist_run._classify_server_processes(this_server, env), "running")
            self.assertEqual(
                s_persist_run._classify_server_processes(this_server, env, own_pid=13), "running"
            )
            diag_server = [{
                "name": "DayZDiag_x64.exe", "pid": 14,
                "command_line": f"DayZDiag_x64.exe -server -mission={mission_s} -profiles={mission_s}",
            }]
            self.assertEqual(s_persist_run._classify_server_processes(diag_server, env), "running")

    def test_server_empty_or_relative_mission_is_running(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            empty_cmd = [{"name": "DayZServer_x64.exe", "pid": 21, "command_line": ""}]
            self.assertEqual(s_persist_run._classify_server_processes(empty_cmd, env), "running")
            relative = [{
                "name": "DayZServer_x64.exe", "pid": 22,
                "command_line": "DayZServer_x64.exe -mission=./mpmissions/dayzOffline.chernarusplus",
            }]
            self.assertEqual(s_persist_run._classify_server_processes(relative, env), "running")

    def test_diag_empty_cmdline_is_unknown(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            rows = [{"name": "DayZDiag_x64.exe", "pid": 31, "command_line": ""}]
            self.assertEqual(s_persist_run._classify_server_processes(rows, env), "unknown")

    def test_tasklist_rows_without_cmdline_with_diag_is_unknown(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            rows = [
                {"name": "explorer.exe", "pid": 40, "command_line": ""},
                {"name": "DayZDiag_x64.exe", "pid": 41, "command_line": ""},
                {"name": "notepad.exe", "pid": 42, "command_line": ""},
            ]
            self.assertEqual(s_persist_run._classify_server_processes(rows, env), "unknown")


class TestRestoreRecoverable(_GuardedTestCase):
    def test_mid_copy_failure_keeps_destination_and_backup(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                t0, slot = s_persist_run._backup_storage(env, backup, "t0")
                self.assertTrue(slot.is_dir())
                # La corrida muta el storage.
                (storage / "players.db").write_bytes(b"players-mutados")
                (storage / "nuevo.bin").write_bytes(b"de-la-corrida")
                mutated = _tree_bytes(storage)
                # Fallo de copia a mitad: el destino queda intacto.
                with mock.patch.object(
                    s_persist_run.shutil, "copytree", side_effect=OSError("copia rota")
                ):
                    ok, snap, err = s_persist_run._restore_storage(env, slot, t0)
                self.assertEqual(ok, 0)
                self.assertIn("storage_restore_incomplete", err)
                self.assertEqual(_tree_bytes(storage), mutated)
                self.assertTrue(slot.is_dir())
                # Sin el fallo, la restauracion verifica por sha256.
                ok, snap, err = s_persist_run._restore_storage(env, slot, t0)
                self.assertEqual((ok, err), (1, ""))
                self.assertEqual(
                    s_persist_run._sha_map(snap), s_persist_run._sha_map(t0)
                )
                self.assertFalse((storage / "nuevo.bin").exists())
                self.assertTrue(slot.is_dir())

    def test_previous_backup_is_never_deleted_on_reuse(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                _t0a, slot_a = s_persist_run._backup_storage(env, backup, "t0")
                first_bytes = _tree_bytes(slot_a)
                (storage / "players.db").write_bytes(b"otra-generacion")
                _t0b, slot_b = s_persist_run._backup_storage(env, backup, "t0")
                # El backup previo se conserva byte a byte en su slot.
                self.assertEqual(_tree_bytes(slot_a), first_bytes)
                self.assertTrue(slot_a.is_dir())
                self.assertNotEqual(slot_b, slot_a)

    def test_restore_blocked_when_running_or_unknown_keeps_destination(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                t0, slot = s_persist_run._backup_storage(env, backup, "t0")
                (storage / "players.db").write_bytes(b"players-mutados")
                (storage / "nuevo.bin").write_bytes(b"de-la-corrida")
                before = _tree_bytes(storage)
                cases = [
                    ([{"name": "DayZServer_x64.exe", "pid": 51, "command_line": ""}], "server_still_running"),
                    ([{"name": "DayZDiag_x64.exe", "pid": 52, "command_line": ""}], "server_state_unknown"),
                ]
                for rows, expected_err in cases:
                    with self.subTest(error=expected_err):
                        with mock.patch.object(s_persist_run, "_list_server_processes", return_value=rows):
                            ok, _snap, err = s_persist_run._restore_storage(env, slot, t0)
                        self.assertEqual(ok, 0)
                        self.assertEqual(err, expected_err)
                        self.assertEqual(_tree_bytes(storage), before)

    def test_restore_uses_exact_slot_returned_by_backup(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                t0, slot = s_persist_run._backup_storage(env, backup, "t0")
                higher = backup.with_name(backup.name + ".bak99")
                shutil.copytree(storage, higher)
                (higher / "players.db").write_bytes(b"slot-viejo-distinto")
                (storage / "players.db").write_bytes(b"players-mutados")
                ok, snap, err = s_persist_run._restore_storage(env, slot, t0)
                self.assertEqual((ok, err), (1, ""))
                self.assertEqual(s_persist_run._sha_map(snap), s_persist_run._sha_map(t0))
                self.assertEqual((storage / "players.db").read_bytes(), b"players-baseline")

    def test_verified_restore_keeps_rollback_copy(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                t0, slot = s_persist_run._backup_storage(env, backup, "t0")
                (storage / "players.db").write_bytes(b"players-mutados")
                (storage / "nuevo.bin").write_bytes(b"de-la-corrida")
                mutated = _tree_bytes(storage)
                ok, _snap, err = s_persist_run._restore_storage(env, slot, t0)
                self.assertEqual((ok, err), (1, ""))
                rollbacks = sorted(mission.glob(".storage_1.r7rollback-*"))
                self.assertTrue(rollbacks)
                self.assertEqual(_tree_bytes(rollbacks[0]), mutated)


class _StubPeer:
    def __init__(self):
        self.inst = "epoch-1"
        self.frame = 100
        self.config = None
        self.now = 1000.0
        self.lease_calls = 0
        self.lease_budget = None  # llamadas True permitidas; luego caduca

    def local_ms(self):
        return float(self.now)

    def lease_valid(self):
        self.lease_calls += 1
        if self.lease_budget is None:
            return True
        return self.lease_calls <= self.lease_budget


def _make_fake():
    peer = _StubPeer()
    jobs = fake_peer.JobMgr(peer)
    ext = fake_ext_persist.PersistFakeExt()
    ext.init(peer, jobs)
    return peer, jobs, ext


class _ClockPeer:
    """Peer con reloj manual y lease por edad (como LeaseOk del nucleo)."""

    def __init__(self):
        self.inst = "epoch-1"
        self.frame = 100
        self.config = None
        self.now = 1000.0
        self.lease_ms = 3000
        self.last_ok_ms = 1000.0

    def local_ms(self):
        return float(self.now)

    def lease_age_ms(self):
        if self.last_ok_ms is None:
            return 1.0e9
        return max(0.0, float(self.now) - float(self.last_ok_ms))

    def lease_valid(self):
        return self.lease_age_ms() <= float(self.lease_ms)

    def renew(self):
        self.last_ok_ms = float(self.now)


def _make_clock_fake():
    peer = _ClockPeer()
    jobs = fake_peer.JobMgr(peer)
    ext = fake_ext_persist.PersistFakeExt()
    ext.init(peer, jobs)
    return peer, jobs, ext


def _make_fake_with_config(cfg_path, inst):
    peer = _StubPeer()
    peer.inst = inst
    peer.config = str(cfg_path)
    jobs = fake_peer.JobMgr(peer)
    ext = fake_ext_persist.PersistFakeExt()
    ext.init(peer, jobs)
    return peer, jobs, ext


def _census_args(include_director=0.0):
    return _unpacked(
        strings={"area_tag": "t1_pre_transition_census:area_a"},
        numbers={"center_x_m": 4500.0, "center_z_m": 10200.0,
                 "radius_m": 60.0, "include_director_b": float(include_director)},
    )


def _unpacked(strings=None, numbers=None, ncol=None, scol=None, rows=None):
    packed = wire.pack_payload(
        scalars_str=strings or {}, scalars_num=numbers or {},
        num_cols=ncol or [], str_cols=scol or [], row_dicts=rows or [],
    )
    return wire.unpack_payload(packed)


def _apply_args(scene_id, op_id, gen_n, rows):
    return _unpacked(
        strings={
            "scene_id": scene_id, "scene_op_id": op_id,
            "expect_epoch": "epoch-1", "q9_pathway": "a",
        },
        numbers={"gen_n": float(gen_n)},
        ncol=["req_x_m", "req_z_m", "req_yaw_deg", "health_mark_ratio", "must_vanish_b"],
        scol=["logical_id", "parent_id", "cat", "class_name", "slot_name"],
        rows=rows,
    )


_SCENE_ROWS = [
    {"logical_id": "cont_1", "parent_id": "", "cat": "prop", "class_name": "SeaChest",
     "slot_name": "", "req_x_m": 4500.0, "req_z_m": 10200.0, "req_yaw_deg": 0.0,
     "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
    {"logical_id": "child_1", "parent_id": "cont_1", "cat": "prop", "class_name": "WaterBottle",
     "slot_name": "Cargo", "req_x_m": 4500.0, "req_z_m": 10200.0, "req_yaw_deg": 0.0,
     "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
]


class TestFakeCleanup(_GuardedTestCase):
    def _applied_ext(self):
        peer, jobs, ext = _make_fake()
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_x", "scop-1", 1, _SCENE_ROWS), {},
        )
        self.assertEqual(status, "done")
        return peer, jobs, ext

    def test_zero_identity_never_matches_and_mark_needs_sentinel_and_disc(self):
        peer, jobs, ext = self._applied_ext()
        # Ajena con identidad cero y marca de salud, clase no centinela.
        ext._add_entity(
            net_id="0:0", pers_id="0:0:0:0", class_name="Apple", cat="raw",
            loc_kind="ground", pos=(4501.0, 100.0, 10201.0),
            max_hp=100.0, health_hp=61.5, persistent=False,
        )
        # Centinela marcada con identidad valida: control positivo con disco.
        marked = ext._add_entity(
            net_id="7:777", pers_id="0:0:0:0", class_name="Barrel_Red", cat="raw",
            loc_kind="ground", pos=(4502.0, 100.0, 10202.0),
            max_hp=100.0, health_hp=61.5, persistent=False,
        )
        # Sin disco valido no hay barrido por marca.
        status, _, _ = ext.on_start_op(
            {"op_id": "op-clean0", "verb": "per_cleanup_qa", "qa_fault": ""},
            _unpacked(strings={"cleanup_tag": "t6"}), {},
        )
        self.assertEqual(status, "done")
        self.assertIn("7:777", ext.world)

        peer2, jobs2, ext2 = self._applied_ext()
        ext2._add_entity(
            net_id="0:0", pers_id="0:0:0:0", class_name="Apple", cat="raw",
            loc_kind="ground", pos=(4501.0, 100.0, 10201.0),
            max_hp=100.0, health_hp=61.5, persistent=False,
        )
        ext2._add_entity(
            net_id="7:777", pers_id="0:0:0:0", class_name="Barrel_Red", cat="raw",
            loc_kind="ground", pos=(4502.0, 100.0, 10202.0),
            max_hp=100.0, health_hp=61.5, persistent=False,
        )
        status, _, _ = ext2.on_start_op(
            {"op_id": "op-clean1", "verb": "per_cleanup_qa", "qa_fault": ""},
            _unpacked(
                strings={"cleanup_tag": "t6"},
                ncol=["center_x_m", "center_z_m", "radius_m"], scol=["area_tag"],
                rows=[{"area_tag": "area_a", "center_x_m": 4500.0,
                       "center_z_m": 10200.0, "radius_m": 60.0}],
            ), {},
        )
        self.assertEqual(status, "done")
        # La de identidad cero sobrevive; la centinela marcada no.
        self.assertIn("0:0", ext2.world)
        self.assertNotIn("7:777", ext2.world)

    def test_container_with_foreign_descendant_is_not_deleted(self):
        peer, jobs, ext = self._applied_ext()
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-raw", "verb": "per_spawn_raw", "qa_fault": ""},
            _unpacked(
                strings={"tag": "fx", "mode": "foreign_in_container",
                         "class_name": "Compass", "child_cargo_class": "",
                         "target_scene_id": "scene_x", "target_parent_id": "cont_1"},
                numbers={"x_m": 4500.0, "z_m": 10200.0, "yaw_deg": 0.0,
                         "health_mark_ratio": 0.0},
            ), {},
        )
        self.assertEqual(status, "done")
        cont_net = ext._record_by("scene_x", "cont_1")["ent"]["net_id"]
        status, _, _ = ext.on_start_op(
            {"op_id": "op-clean", "verb": "per_cleanup_qa", "qa_fault": ""},
            _unpacked(
                strings={"cleanup_tag": "t6"},
                ncol=["center_x_m", "center_z_m", "radius_m"], scol=["area_tag"],
                rows=[{"area_tag": "area_a", "center_x_m": 4500.0,
                       "center_z_m": 10200.0, "radius_m": 60.0}],
            ), {},
        )
        self.assertEqual(status, "done")
        self.assertIn(cont_net, ext.world)


class TestPersistentControlMarkCleanup(_GuardedTestCase):
    """Ronda 24: el hijo del control nace con la marca y, sin registros en
    memoria (lo que pierde la sonda al reiniciar), la limpieza de t6 lo
    reconoce por clase centinela + marca, no por ficheros."""

    def _spawn_control(self, ext):
        status, reason, payload = ext.on_start_op(
            {"op_id": "op-ctrl", "verb": "per_spawn_raw", "qa_fault": ""},
            _unpacked(
                strings={"tag": "c_persistent_control", "mode": "persistent_control",
                         "class_name": "Barrel_Yellow", "child_cargo_class": "Fireplace",
                         "target_scene_id": "", "target_parent_id": ""},
                numbers={"x_m": 4860.0, "z_m": 10200.0, "yaw_deg": 15.0,
                         "health_mark_ratio": 0.845},
            ), {},
        )
        self.assertEqual(status, "done")
        out = wire.unpack_payload(payload)
        self.assertEqual(out["num"].get("child_count_n"), 1.0)
        ctrl_net = out["str"]["net_id"]
        child = next(e for e in ext.world.values() if e["parent_net_id"] == ctrl_net)
        return ctrl_net, child

    def _cleanup_area_c(self, ext):
        status, reason, payload = ext.on_start_op(
            {"op_id": "op-clean", "verb": "per_cleanup_qa", "qa_fault": ""},
            _unpacked(
                strings={"cleanup_tag": "t6"},
                ncol=["center_x_m", "center_z_m", "radius_m"], scol=["area_tag"],
                rows=[{"area_tag": "area_c", "center_x_m": 4860.0,
                       "center_z_m": 10200.0, "radius_m": 60.0}],
            ), {},
        )
        self.assertEqual(status, "done")
        return wire.unpack_payload(payload)

    def test_control_child_born_with_health_mark(self):
        peer, jobs, ext = _make_fake()
        ctrl_net, child = self._spawn_control(ext)
        self.assertEqual(child["class_name"], "Fireplace")
        self.assertTrue(fake_ext_persist._is_health_mark(child))
        self.assertAlmostEqual(
            child["health_hp"], child["max_hp"] * 0.845, delta=1e-2
        )

    def test_cleanup_without_memory_records_deletes_control_and_child(self):
        peer, jobs, ext = _make_fake()
        ctrl_net, child = self._spawn_control(ext)
        child_net = child["net_id"]
        ext.records = []
        ext.raw_net_ids = set()
        ext.qa_net_ids = set()
        out = self._cleanup_area_c(ext)
        self.assertNotIn(ctrl_net, ext.world)
        self.assertNotIn(child_net, ext.world)
        self.assertGreaterEqual(out["num"]["cleaned_raw_n"], 1.0)

    def test_cleanup_keeps_control_with_unmarked_foreign_descendant(self):
        peer, jobs, ext = _make_fake()
        ctrl_net, child = self._spawn_control(ext)
        ext.records = []
        ext.raw_net_ids = set()
        ext.qa_net_ids = set()
        ext._add_entity(
            net_id="9:999", pers_id="0:0:0:0", class_name="Compass", cat="raw",
            loc_kind="cargo", parent_net_id=ctrl_net, parent_class="Barrel_Yellow",
            slot_name="Cargo:0:1:0", pos=child["pos"],
            max_hp=100.0, health_hp=100.0, persistent=True, area_id="area_c",
        )
        self._cleanup_area_c(ext)
        self.assertIn(ctrl_net, ext.world)


class TestFakeGenerationsAndLease(_GuardedTestCase):
    def test_retained_rows_are_partial_and_not_duplicated(self):
        peer, jobs, ext = TestFakeCleanup()._applied_ext()
        ext.on_start_op(
            {"op_id": "op-raw", "verb": "per_spawn_raw", "qa_fault": ""},
            _unpacked(
                strings={"tag": "fx", "mode": "foreign_in_container",
                         "class_name": "Compass", "child_cargo_class": "",
                         "target_scene_id": "scene_x", "target_parent_id": "cont_1"},
                numbers={"x_m": 4500.0, "z_m": 10200.0, "yaw_deg": 0.0,
                         "health_mark_ratio": 0.0},
            ), {},
        )
        status, reason, payload = ext.on_start_op(
            {"op_id": "op-apply2", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_x", "scop-2", 2, _SCENE_ROWS), {},
        )
        self.assertEqual(status, "done")
        out = wire.unpack_payload(payload)
        self.assertEqual(out["str"].get("apply_status"), "partial")
        self.assertEqual(out["str"].get("reason"), "retained_prior_generation")
        conts = [r for r in ext.records if r["logical_id"] == "cont_1"]
        self.assertEqual(len(conts), 1)
        self.assertEqual(conts[0]["gen_n"], 1)

    def test_lease_expiry_mid_reset_propagates_as_error(self):
        peer, jobs, ext = TestFakeCleanup()._applied_ext()
        # Entrada + un borrado con lease; la siguiente guarda caduca.
        peer.lease_calls = 0
        peer.lease_budget = 2
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-reset", "verb": "per_reset_scene", "qa_fault": ""},
            _unpacked(strings={"scene_id": "scene_x", "reset_op_id": "rop-1",
                               "expect_epoch": "epoch-1"}), {},
        )
        self.assertEqual((status, reason), ("error", "lease_expired"))
        self.assertGreater(len(ext.records), 0)

    def test_capture_longer_than_lease_still_done(self):
        # Semantica de instantanea (punto 1): el lease se mira al empezar la
        # captura; que la captura dure mas que lease_ms no la tumba.
        peer, jobs, ext = _make_clock_fake()
        status, _, _ = ext.on_start_op(
            {"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_x", "scop-1", 1, _SCENE_ROWS), {},
        )
        self.assertEqual(status, "done")
        ext.capture_delay_ms = 5000.0
        status, _, payload = ext.on_start_op(
            {"op_id": "op-census", "verb": "per_census_start", "qa_fault": ""},
            _census_args(), {},
        )
        self.assertEqual(status, "done")
        out = wire.unpack_payload(payload)
        self.assertEqual(out["num"]["capture_wall_ms"], 5000.0)
        self.assertEqual(out["num"]["rows_captured_n"], 2.0)
        peer.renew()
        peer.now += 1000.0
        for _ in range(6):
            ext.on_tick(0.016)
        job = jobs.jobs_by_id["op-census"]
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["rows_total"], 2)


class TestFakeContention(_GuardedTestCase):
    def test_a_holds_until_b_attempt_and_overlap_is_observed_by_ticks(self):
        peer, jobs, ext = _make_fake()
        census_args = _unpacked(
            strings={"area_tag": "t0_baseline_census:area_a"},
            numbers={"center_x_m": 4500.0, "center_z_m": 10200.0,
                     "radius_m": 60.0, "include_director_b": 0.0},
        )
        status, _, _ = ext.on_start_op(
            {"op_id": "opA", "verb": "per_census_start", "qa_fault": ""}, census_args, {}
        )
        self.assertEqual(status, "done")
        # Sin intento de B, A sigue ocupando tras ticks y 100 ms.
        peer.now += 100.0
        for _ in range(5):
            ext.on_tick(0.016)
        self.assertEqual(jobs.get_state("opA"), "running")
        # B sin bypass: busy, y ese intento acredita la liberacion de A.
        status_b, reason_b, _ = ext.on_start_op(
            {"op_id": "opB", "verb": "per_census_start", "qa_fault": ""}, census_args, {}
        )
        self.assertEqual((status_b, reason_b), ("rejected", "busy"))

        peer2, jobs2, ext2 = _make_fake()
        ext2.on_start_op(
            {"op_id": "opA", "verb": "per_census_start", "qa_fault": ""}, census_args, {}
        )
        peer2.now += 100.0
        for _ in range(5):
            ext2.on_tick(0.016)
        self.assertEqual(jobs2.get_state("opA"), "running")
        # Mutante census_resource_bypass: B se acepta dentro de la ventana.
        status_b2, _, _ = ext2.on_start_op(
            {"op_id": "opB", "verb": "per_census_start",
             "qa_fault": "census_resource_bypass"}, census_args, {}
        )
        self.assertEqual(status_b2, "done")
        for _ in range(6):
            peer2.now += 20.0
            ext2.on_tick(0.016)
        job_a = jobs2.jobs_by_id["opA"]
        job_b = jobs2.jobs_by_id["opB"]
        self.assertEqual(job_a["state"], "done")
        # Solapamiento observado con ticks de inicio y liberacion.
        self.assertLess(job_b["start_tick_ms"], job_a["released_tick_ms"])
        self.assertGreaterEqual(job_a["released_tick_ms"], job_a["start_tick_ms"])


class TestPostCleanupCensusNotN49(_GuardedTestCase):
    def test_runner_tag_is_explicit_t6(self):
        tag = s_persist_run._census_tag(
            "t6_post_cleanup_census", "t5_track_b_inf_1_p0_r0", has_center_override=True
        )
        self.assertEqual(tag, "t6_post_cleanup_census:t5_track_b_inf_1_p0_r0")
        self.assertEqual(
            s_persist_eval._extract_stage_from_tag(tag, {}), "t6_post_cleanup_census"
        )
        t5_tag = s_persist_run._census_tag(
            "t5_post_restart_census", "t5_track_b_inf_1_p0_r0", has_center_override=True
        )
        self.assertEqual(
            s_persist_eval._extract_stage_from_tag(t5_tag, {}), "t5_post_restart_census"
        )

    def test_empty_post_cleanup_census_does_not_pass_per08(self):
        from tests.test_s_persist_offline import _SyntheticPartBuilder, _checks_by_id

        def _set_area_tag(payload, new_tag):
            if isinstance(payload, dict) and "area_tag" in (payload.get("sk") or []):
                payload["sv"][payload["sk"].index("area_tag")] = new_tag

        with self._inside_tmp() as td:
            builder = _SyntheticPartBuilder(
                "run", creature_far_move_m=75.0, include_t5_track_disks=False
            )
            part_dir = builder.build_into(Path(td) / "n49_post_cleanup")
            bpath = part_dir / "samples" / "bridge.jsonl"
            events = [json.loads(l) for l in bpath.read_text(encoding="utf-8").splitlines() if l.strip()]
            baseline = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(_checks_by_id(baseline)["PER-08"]["status"], "missing")
            # Un censo vacio posterior a la limpieza, etiquetado como emite
            # ahora el runner para ese disco, no puede acreditar N49.
            changed = 0
            for ev in events:
                if ev.get("ev") in ("enq", "poll"):
                    args = ev.get("args") or ((ev.get("ops") or [{}])[0].get("args") if ev.get("ops") else None)
                    if isinstance(args, dict) and "sk" in args:
                        u = wire.unpack_payload(args)
                        if str(u["str"].get("area_tag") or "").startswith("t6_post_cleanup_census:"):
                            _set_area_tag(args, "t6_post_cleanup_census:t5_track_b_inf_1_p0_r0")
                            changed += 1
                elif ev.get("ev") == "result":
                    for res in ev.get("results") or []:
                        if res.get("verb") == "per_census_start":
                            u = wire.unpack_payload(res["read"])
                            if str(u["str"].get("area_tag") or "").startswith("t6_post_cleanup_census:"):
                                _set_area_tag(res["read"], "t6_post_cleanup_census:t5_track_b_inf_1_p0_r0")
                                changed += 1
            self.assertGreater(changed, 0)
            bpath.write_text(
                "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
            )
            verdict = s_persist_eval.evaluate(part_dir, repo_root=REPO_ROOT)
            self.assertEqual(_checks_by_id(verdict)["PER-08"]["status"], "missing")
            self.assertNotEqual(_checks_by_id(verdict)["PER-08"]["status"], "pass")


class _FakePartContext:
    """PartContext falso: registra open y aborta sin jugar si se pide."""

    calls = []
    instances = []
    next_startup_reason = "peer_timeout"

    def __init__(self, *, base_dir, part_name, spike_id, args, argv):
        self.base_dir = Path(base_dir)
        self.part_name = part_name
        self.part_dir = self.base_dir / part_name
        self.build = args.build
        self.startup_reason = type(self).next_startup_reason
        self.git_head = ""
        self.expected_stamp = ""
        self.scenario = []
        self.bridge = _FakeBridge()
        type(self).instances.append(self)

    def __enter__(self):
        type(self).calls.append("open")
        (self.part_dir / "samples").mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def record_scenario(self, row):
        self.scenario.append(dict(row))

    def collect_probe_budget_logs(self):
        return []

    def finalize_manifest(self):
        return {}

    def _verify_hello_events(self):
        return None


def _live_args():
    return mock.Mock(build="diag", both=True)


class TestLiveColdBackupOrder(_GuardedTestCase):
    def setUp(self):
        super().setUp()
        _FakePartContext.calls = []
        _FakePartContext.instances = []
        _FakePartContext.next_startup_reason = "peer_timeout"

    def test_backup_before_open_when_server_stopped(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, _backup = _make_env(tmp)
            base_dir = tmp / "evidence"
            real_backup = s_persist_run._backup_storage

            def recording_backup(storage_env, backup_dir, label):
                _FakePartContext.calls.append("backup")
                return real_backup(storage_env, backup_dir, label)

            with mock.patch.object(s_persist_run, "_storage_env", return_value=env), mock.patch.object(
                s_persist_run, "_list_server_processes", return_value=[]
            ), mock.patch.object(
                s_persist_run, "_backup_storage", side_effect=recording_backup
            ), mock.patch.object(
                f03_common, "PartContext", _FakePartContext
            ):
                verdict = s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertEqual(verdict.get("exit_code"), 2)
            self.assertLess(
                _FakePartContext.calls.index("backup"),
                _FakePartContext.calls.index("open"),
            )
            slot = base_dir / "run" / "_storage_backup"
            self.assertTrue(slot.is_dir())
            self.assertEqual((slot / "players.db").read_bytes(), b"players-baseline")

    def test_no_backup_and_no_play_when_server_running(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, _backup = _make_env(tmp)
            base_dir = tmp / "evidence"
            _FakePartContext.next_startup_reason = None
            running = [{"name": "DayZServer_x64.exe", "pid": 99, "command_line": ""}]
            backup_mock = mock.Mock(return_value=({}, base_dir / "run" / "_storage_backup"))
            with mock.patch.object(s_persist_run, "_storage_env", return_value=env), mock.patch.object(
                s_persist_run, "_list_server_processes", return_value=running
            ), mock.patch.object(
                s_persist_run, "_backup_storage", backup_mock
            ), mock.patch.object(
                f03_common, "PartContext", _FakePartContext
            ):
                with self.assertRaises(RuntimeError):
                    s_persist_run.run_part(_live_args(), base_dir, [], "run")
            backup_mock.assert_not_called()
            self.assertFalse((base_dir / "run" / "_storage_backup").exists())
            self.assertEqual(len(_FakePartContext.instances), 1)
            scenario = _FakePartContext.instances[0].scenario
            self.assertEqual(len(scenario), 1)
            self.assertEqual(scenario[0].get("ev"), "storage_restore_result")
            self.assertEqual(scenario[0].get("restore_incomplete_b"), 1)
            self.assertIn("server_still_running", str(scenario[0].get("error") or ""))
            self.assertNotIn("t0_status", [ev.get("ev") for ev in scenario])


class _FakeBridgeT4:
    def __init__(self, now_ms):
        self._now_ms = float(now_ms)
        self.failure = None
        self.hold_ms = 2000

    def now_ms(self):
        return self._now_ms


class _FakeCtxT4:
    def __init__(self, now_ms):
        self.bridge = _FakeBridgeT4(now_ms)
        self.scenario = []

    def record_scenario(self, row):
        self.scenario.append(dict(row))


class TestT4NewServerHello(unittest.TestCase):
    def _captured_predicate(self, now_ms=5000.0):
        ctx = _FakeCtxT4(now_ms)
        captured = {}

        def fake_await_operator(ctx_arg, *, step, action, instructions, predicate, timeout_s):
            captured["predicate"] = predicate
            captured["step"] = step
            return {"ok": False, "reason": "operator_timeout"}

        with mock.patch.object(f03_common, "await_operator", fake_await_operator):
            result = s_persist_run._restart_server_live(ctx, "epoch-old", "director-1")
        self.assertEqual(result, "")
        self.assertEqual(captured.get("step"), "t4_restart")
        return captured["predicate"]

    def test_rejects_old_hello_before_threshold_and_accepts_after(self):
        predicate = self._captured_predicate(now_ms=5000.0)
        old_hello = {
            "ev": "hello", "http": 200, "peer": "server",
            "inst": "epoch-new", "t_ms": 4999.0,
        }
        self.assertFalse(predicate(old_hello))
        at_threshold = dict(old_hello, t_ms=5000.0)
        self.assertTrue(predicate(at_threshold))
        after = dict(old_hello, t_ms=5001.0)
        self.assertTrue(predicate(after))
        same_epoch_after = dict(old_hello, inst="epoch-old", t_ms=6000.0)
        self.assertFalse(predicate(same_epoch_after))
        missing_t = {"ev": "hello", "http": 200, "peer": "server", "inst": "epoch-new"}
        self.assertFalse(predicate(missing_t))


class _FakeBridge:
    def __init__(self, failure=None):
        self.failure = failure
        self.hold_ms = 2000


class _FakeCtx:
    def __init__(self, failure=None):
        self.bridge = _FakeBridge(failure)
        self.scenario = []

    def record_scenario(self, row):
        self.scenario.append(dict(row))


class TestPeerCutFailureClear(unittest.TestCase):
    def test_clears_connection_reset_error(self):
        err = ConnectionResetError(10054, "conexion restablecida")
        ctx = _FakeCtx(failure=err)
        self.assertTrue(s_persist_run._clear_expected_peer_cut_failure(ctx))
        self.assertIsNone(ctx.bridge.failure)

    def test_clears_connection_aborted_error(self):
        err = ConnectionAbortedError(10053, "conexion anulada")
        ctx = _FakeCtx(failure=err)
        self.assertTrue(s_persist_run._clear_expected_peer_cut_failure(ctx))
        self.assertIsNone(ctx.bridge.failure)

    def test_does_not_clear_other_failures(self):
        for err in (TimeoutError("timeout"), RuntimeError("boom")):
            with self.subTest(type=type(err).__name__):
                ctx = _FakeCtx(failure=err)
                self.assertFalse(s_persist_run._clear_expected_peer_cut_failure(ctx))
                self.assertIs(ctx.bridge.failure, err)

    def test_no_failure_does_nothing(self):
        ctx = _FakeCtx(failure=None)
        self.assertFalse(s_persist_run._clear_expected_peer_cut_failure(ctx))
        self.assertIsNone(ctx.bridge.failure)


def _status_outcome(uid="", present=0, alive=0, inv=0, epoch="epoch-1", players_n=None):
    if players_n is None:
        players_n = 1 if uid else 0
    return SimpleNamespace(
        status="done",
        reason="",
        op_id="op-status",
        payload={
            "str": {"server_epoch": epoch, "director_uid": uid},
            "num": {
                "players_n": float(players_n),
                "director_present_b": float(present),
                "director_alive_b": float(alive),
                "director_inv_readable_b": float(inv),
            },
        },
    )


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += float(seconds)


class TestT0DirectorWait(unittest.TestCase):
    def test_t0_waits_and_keeps_good_status(self):
        clock = _FakeClock()
        absent = _status_outcome(uid="", present=0, alive=0, inv=0)
        not_ready = _status_outcome(uid="director-1", present=0, alive=1, inv=1)
        good = _status_outcome(uid="director-1", present=1, alive=1, inv=1, epoch="epoch-good")
        outcomes = iter([absent, not_ready, good])
        with mock.patch.object(f03_common, "issue_one", side_effect=lambda *a, **k: next(outcomes)):
            st, polls, waited_ms, ready, ambiguous = s_persist_run._wait_for_director_t0(
                mock.Mock(), timeout_s=300.0, poll_s=2.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(ambiguous)
        self.assertTrue(ready)
        self.assertIs(st, good)
        self.assertEqual(st.payload["str"]["server_epoch"], "epoch-good")
        self.assertEqual(st.payload["str"]["director_uid"], "director-1")
        self.assertEqual(polls, 3)
        self.assertEqual(waited_ms, 4000)

    def test_t0_wait_exhausts_top_without_director(self):
        clock = _FakeClock()
        absent = _status_outcome(uid="", present=0, alive=0, inv=0)
        with mock.patch.object(f03_common, "issue_one", return_value=absent):
            st, polls, waited_ms, ready, ambiguous = s_persist_run._wait_for_director_t0(
                mock.Mock(), timeout_s=5.0, poll_s=2.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(ambiguous)
        self.assertFalse(ready)
        self.assertIs(st, absent)
        self.assertGreaterEqual(polls, 3)
        self.assertGreaterEqual(waited_ms, 5000)

    def test_t0_two_players_is_ambiguous(self):
        clock = _FakeClock()
        two = _status_outcome(uid="", present=0, alive=0, inv=0, players_n=2)
        with mock.patch.object(f03_common, "issue_one", return_value=two):
            st, polls, waited_ms, ready, ambiguous = s_persist_run._wait_for_director_t0(
                mock.Mock(), timeout_s=300.0, poll_s=2.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertTrue(ambiguous)
        self.assertFalse(ready)
        self.assertIs(st, two)
        self.assertEqual(polls, 1)

    def test_t0_zero_players_keeps_waiting(self):
        clock = _FakeClock()
        zero = _status_outcome(uid="", present=0, alive=0, inv=0, players_n=0)
        with mock.patch.object(f03_common, "issue_one", return_value=zero):
            st, polls, waited_ms, ready, ambiguous = s_persist_run._wait_for_director_t0(
                mock.Mock(), timeout_s=5.0, poll_s=2.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(ambiguous)
        self.assertFalse(ready)
        self.assertGreaterEqual(polls, 3)
        self.assertGreaterEqual(waited_ms, 5000)


class TestT0DirectorAbsentAborts(_GuardedTestCase):
    def setUp(self):
        super().setUp()
        _FakePartContext.calls = []
        _FakePartContext.instances = []
        _FakePartContext.next_startup_reason = None

    def test_t0_absent_cuts_part_without_playing(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, _mission, _storage, _backup = _make_env(tmp)
            base_dir = tmp / "evidence"
            absent = _status_outcome(uid="", present=0, alive=0, inv=0)
            calls = []

            def fake_issue(ctx, peer, verb, payload=None, **kwargs):
                calls.append(verb)
                return absent

            backup_return = (env, {}, tmp / "_storage_backup", None, "")
            with mock.patch.object(
                s_persist_run, "_live_cold_backup_before_open", return_value=backup_return
            ), mock.patch.object(
                s_persist_run, "_probe_sources_at_commit", return_value={}
            ), mock.patch.object(
                s_persist_run, "T0_DIRECTOR_TIMEOUT_S", 0.0
            ), mock.patch.object(
                f03_common, "PartContext", _FakePartContext
            ), mock.patch.object(
                f03_common, "issue_one", side_effect=fake_issue
            ):
                with self.assertRaises(RuntimeError) as raised:
                    s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertEqual(str(raised.exception), "t0_director_absent")
            self.assertEqual(calls, ["per_status"])
            scenario = _FakePartContext.instances[0].scenario
            evs = [row.get("ev") for row in scenario]
            self.assertIn("t0_status", evs)
            self.assertIn("t0_director_wait", evs)
            self.assertIn("t0_director_absent", evs)
            t0_row = [r for r in scenario if r.get("ev") == "t0_status"][0]
            self.assertEqual(t0_row.get("director_uid"), "")
            self.assertNotIn("baseline_director_foreign", evs)
            self.assertNotIn("apply_scene_t1", evs)


class TestT4DirectorWindow(unittest.TestCase):
    def test_t4_window_reaches_beyond_120s(self):
        self.assertEqual(s_persist_run.T0_DIRECTOR_TIMEOUT_S, 300.0)
        self.assertEqual(s_persist_run.T4_DIRECTOR_TIMEOUT_S, 300.0)
        clock = _FakeClock()
        ctx = _FakeCtxT4(now_ms=5000.0)

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            if clock.now < 150.0:
                return _status_outcome(uid="director-1", present=0, alive=0, inv=0, epoch="epoch-new")
            return _status_outcome(uid="director-1", present=1, alive=1, inv=1, epoch="epoch-new")

        hello = {"ev": "hello", "http": 200, "peer": "server", "inst": "epoch-new",
                 "t_ms": 5000.0}
        with mock.patch.object(
            f03_common, "await_operator", return_value={"ok": True, "event": hello}
        ), mock.patch.object(
            f03_common, "issue_one", side_effect=fake_issue
        ), mock.patch.object(
            s_persist_run.time, "monotonic", clock.monotonic
        ), mock.patch.object(
            s_persist_run.time, "sleep", clock.sleep
        ):
            result = s_persist_run._restart_server_live(ctx, "epoch-old", "director-1")
        self.assertEqual(result, "epoch-new")
        self.assertGreaterEqual(clock.now, 150.0)


class TestPoint2DeclaredNamesAndRecheck(_GuardedTestCase):
    def test_declared_server_name_case_insensitive_blocks(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            env["server_exe_names"] = ["DayZServer_QA.exe"]
            rows = [{"name": "dayzserver_qa.EXE", "pid": 61, "command_line": "DayZServer_QA.exe -server"}]
            self.assertEqual(s_persist_run._classify_server_processes(rows, env), "running")
            rows_none = None
            self.assertEqual(s_persist_run._classify_server_processes(rows_none, env), "unknown")

    def test_restore_rechecks_stop_before_substitution(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                t0, slot = s_persist_run._backup_storage(env, backup, "t0")
            (storage / "players.db").write_bytes(b"players-mutados")
            mutated = _tree_bytes(storage)
            calls = {"n": 0}

            def fake_list(_env):
                calls["n"] += 1
                if calls["n"] == 1:
                    return []
                return [{"name": "DayZServer_x64.exe", "pid": 62, "command_line": "DayZServer_x64.exe -server"}]

            with mock.patch.object(s_persist_run, "_list_server_processes", side_effect=fake_list):
                ok, _snap, err = s_persist_run._restore_storage(env, slot, t0)
            self.assertEqual(ok, 0)
            self.assertEqual(err, "server_still_running")
            self.assertEqual(_tree_bytes(storage), mutated)
            self.assertTrue(slot.is_dir())
            self.assertEqual((slot / "players.db").read_bytes(), b"players-baseline")

    def test_backup_rechecks_stop_before_copy(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            calls = {"n": 0}

            def fake_list(_env):
                calls["n"] += 1
                if calls["n"] == 1:
                    return []
                return [{"name": "DayZServer_x64.exe", "pid": 63, "command_line": "DayZServer_x64.exe -server"}]

            with mock.patch.object(s_persist_run, "_list_server_processes", side_effect=fake_list):
                with self.assertRaises(RuntimeError) as raised:
                    s_persist_run._backup_storage(env, backup, "t0")
            self.assertEqual(str(raised.exception), "server_still_running")
            self.assertFalse(backup.exists())


class TestPoint1RestoreOnEveryExit(_GuardedTestCase):
    def setUp(self):
        super().setUp()
        _FakePartContext.calls = []
        _FakePartContext.instances = []

    def _backup_and_mutate(self, tmp):
        env, mission, storage, _backup = _make_env(tmp)
        with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
            t0, slot = s_persist_run._backup_storage(env, tmp / "slot_backup", "t0")
        (storage / "players.db").write_bytes(b"players-calentados")
        return env, storage, t0, slot

    def test_startup_reason_exit_restores_storage(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, storage, t0, slot = self._backup_and_mutate(tmp)
            base_dir = tmp / "evidence"
            _FakePartContext.next_startup_reason = "peer_timeout"
            backup_return = (env, t0, slot, None, "")
            with mock.patch.object(s_persist_run, "_live_cold_backup_before_open", return_value=backup_return), mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]), mock.patch.object(f03_common, "PartContext", _FakePartContext):
                verdict = s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertEqual(verdict.get("exit_code"), 2)
            scenario = _FakePartContext.instances[0].scenario
            restores = [r for r in scenario if r.get("ev") == "storage_restore_result"]
            self.assertEqual(len(restores), 1)
            self.assertEqual(restores[0].get("restore_ok_b"), 1)
            self.assertEqual(restores[0].get("restore_incomplete_b"), 0)
            self.assertEqual((storage / "players.db").read_bytes(), b"players-baseline")
            self.assertTrue(slot.is_dir())

    def test_director_absent_exit_restores_storage(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, storage, t0, slot = self._backup_and_mutate(tmp)
            base_dir = tmp / "evidence"
            _FakePartContext.next_startup_reason = None
            absent = _status_outcome(uid="", present=0, alive=0, inv=0)
            backup_return = (env, t0, slot, None, "")
            with mock.patch.object(s_persist_run, "_live_cold_backup_before_open", return_value=backup_return), mock.patch.object(s_persist_run, "_probe_sources_at_commit", return_value={}), mock.patch.object(s_persist_run, "T0_DIRECTOR_TIMEOUT_S", 0.0), mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]), mock.patch.object(f03_common, "PartContext", _FakePartContext), mock.patch.object(f03_common, "issue_one", return_value=absent):
                with self.assertRaises(RuntimeError) as raised:
                    s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertEqual(str(raised.exception), "t0_director_absent")
            scenario = _FakePartContext.instances[0].scenario
            restores = [r for r in scenario if r.get("ev") == "storage_restore_result"]
            self.assertEqual(len(restores), 1)
            self.assertEqual(restores[0].get("restore_ok_b"), 1)
            self.assertEqual((storage / "players.db").read_bytes(), b"players-baseline")
            self.assertTrue(slot.is_dir())


class TestPoint3StorageMissionBinding(_GuardedTestCase):
    def setUp(self):
        super().setUp()
        _FakePartContext.calls = []
        _FakePartContext.instances = []

    def test_mission_mismatch_is_inconclusive_before_t1_and_restores(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, _backup = _make_env(tmp)
            other_mission = tmp / "srv" / "mpmissions" / "other_mission"
            other_mission.mkdir(parents=True)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                t0, slot = s_persist_run._backup_storage(env, tmp / "slot_backup", "t0")
            (storage / "players.db").write_bytes(b"players-calentados")
            base_dir = tmp / "evidence"
            _FakePartContext.next_startup_reason = None
            state = {"running": True}
            server_row = {"name": "DayZServer_x64.exe", "pid": 71, "command_line": f'DayZServer_x64.exe -server "-mission={other_mission}"'}
            operator_calls = []

            def fake_list(_env):
                return [server_row] if state["running"] else []

            def fake_await(ctx, *, step, action, instructions, predicate, timeout_s):
                operator_calls.append({"step": step, "action": action})
                state["running"] = False
                return {"ok": True, "step": step, "action": action}

            good = _status_outcome(uid="director-1", present=1, alive=1, inv=1)
            verbs = []

            def fake_issue(ctx, peer, verb, payload=None, **kwargs):
                verbs.append(verb)
                if verb == "per_status":
                    return good
                raise AssertionError(f"verbo inesperado antes de t1: {verb}")

            backup_return = (env, t0, slot, None, "")
            with mock.patch.object(s_persist_run, "_live_cold_backup_before_open", return_value=backup_return), mock.patch.object(s_persist_run, "_probe_sources_at_commit", return_value={}), mock.patch.object(s_persist_run, "_list_server_processes", side_effect=fake_list), mock.patch.object(f03_common, "PartContext", _FakePartContext), mock.patch.object(f03_common, "issue_one", side_effect=fake_issue), mock.patch.object(f03_common, "await_operator", side_effect=fake_await):
                with self.assertRaises(RuntimeError) as raised:
                    s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertIn("storage_mission", str(raised.exception))
            self.assertEqual(verbs, ["per_status"])
            scenario = _FakePartContext.instances[0].scenario
            evs = [r.get("ev") for r in scenario]
            self.assertIn("storage_mission_verify", evs)
            self.assertNotIn("apply_scene_t1", evs)
            restores = [r for r in scenario if r.get("ev") == "storage_restore_result"]
            self.assertEqual(len(restores), 1)
            self.assertEqual(restores[0].get("restore_ok_b"), 1)
            self.assertEqual((storage / "players.db").read_bytes(), b"players-baseline")
            self.assertTrue(slot.is_dir())
            self.assertTrue(operator_calls)
            self.assertEqual(operator_calls[0].get("action"), "stop_server")
            self.assertEqual(operator_calls[0].get("step"), "post_backup_stop_server_for_cold_restore")

    def test_verify_storage_mission_counts(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, _backup = _make_env(tmp)
            good_row = {"name": "DayZDiag_x64.exe", "pid": 72, "command_line": f'DayZDiag_x64.exe -server "-mission={mission}"'}
            ok, err = s_persist_run._verify_storage_mission(env, rows=[good_row])
            self.assertEqual((ok, err), (True, ""))
            ok, err = s_persist_run._verify_storage_mission(env, rows=[])
            self.assertFalse(ok)
            ok, err = s_persist_run._verify_storage_mission(env, rows=[good_row, good_row])
            self.assertFalse(ok)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=None):
                ok, err = s_persist_run._verify_storage_mission(env)
            self.assertFalse(ok)
            self.assertEqual(err, "server_state_unknown")


class TestPoint4IdempotentProbeReplaysOriginal(_GuardedTestCase):
    def test_idempotent_branch_replays_saved_retained_count(self):
        probe = QA_DIR / "probe" / "DayZSandbox_QA" / "scripts" / "5_Mission" / "DSBX_QA_X_Persist.c"
        text = probe.read_text(encoding="utf-8")
        self.assertIn("m_SceneLastRetainedSkipped", text)
        marker = "m_SceneLastOp.Get(scIdx) == sceneOpId"
        start = text.index(marker)
        segment = text[start:start + 500]
        self.assertIn("m_SceneLastRetainedSkipped.Get(scIdx)", segment)
        self.assertNotIn("m_LastApplyRetainedSkipped = 0;", segment)


class TestPoint5FakeProvenanceSurvivesRestart(_GuardedTestCase):
    def _ext_with_config(self, tmp):
        peer, jobs, ext = _make_fake()
        prof = tmp / "srvprof"
        prof.mkdir(parents=True, exist_ok=True)
        peer.config = str(prof / "dsbx_qa.json")
        return peer, jobs, ext

    def test_foreign_survivor_stays_foreign_after_save_load(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            peer, jobs, ext = self._ext_with_config(tmp)
            helper = TestPersistentControlMarkCleanup()
            ctrl_net, child = helper._spawn_control(ext)
            child_net = child["net_id"]
            apple = ext._add_entity(net_id="9:999", pers_id="9:0:0:0", class_name="Apple", cat="raw", loc_kind="cargo", parent_net_id=ctrl_net, parent_class="Barrel_Yellow", slot_name="Cargo:0:1:0", pos=child["pos"], max_hp=100.0, health_hp=100.0, persistent=True, area_id="area_c")
            apple_net = apple["net_id"]
            ext._save_state()
            peer2, jobs2, ext2 = self._ext_with_config(tmp)
            ext2.init(peer2, jobs2)
            self.assertIn(ctrl_net, ext2.world)
            self.assertIn(apple_net, ext2.world)
            self.assertNotIn(apple_net, ext2.raw_net_ids)
            self.assertNotIn(apple_net, ext2.qa_net_ids)
            self.assertIn(ctrl_net, ext2.raw_net_ids)
            helper._cleanup_area_c(ext2)
            self.assertIn(ctrl_net, ext2.world)
            self.assertIn(apple_net, ext2.world)

    def test_qa_leak_still_deleted_after_save_load_by_provenance(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            peer, jobs, ext = self._ext_with_config(tmp)
            status, reason, _payload = ext.on_start_op({"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": "omit_nopersistency_flag"}, _apply_args("scene_x", "scop-1", 1, _SCENE_ROWS), {})
            self.assertEqual(status, "done")
            cont_net = ext._record_by("scene_x", "cont_1")["ent"]["net_id"]
            ext._save_state()
            peer2, jobs2, ext2 = self._ext_with_config(tmp)
            ext2.init(peer2, jobs2)
            self.assertIn(cont_net, ext2.world)
            self.assertIn(cont_net, ext2.qa_net_ids)
            status, reason, _payload = ext2.on_start_op({"op_id": "op-clean", "verb": "per_cleanup_qa", "qa_fault": ""}, _unpacked(strings={"cleanup_tag": "t6"}, ncol=["center_x_m", "center_z_m", "radius_m"], scol=["area_tag"], rows=[{"area_tag": "area_a", "center_x_m": 4500.0, "center_z_m": 10200.0, "radius_m": 60.0}]), {})
            self.assertEqual(status, "done")
            self.assertNotIn(cont_net, ext2.world)


class _RaisingPartContext:
    calls = []

    def __init__(self, *, base_dir, part_name, spike_id, args, argv):
        self.base_dir = Path(base_dir)
        self.part_name = part_name
        self.part_dir = self.base_dir / part_name
        self.build = args.build

    def __enter__(self):
        type(self).calls.append("open")
        raise RuntimeError("open boom")

    def __exit__(self, exc_type, exc, tb):
        return False


class _FailFirstRecordContext(_FakePartContext):
    def record_scenario(self, row):
        if row.get("ev") == "probe_sources_at_commit" and not getattr(self, "_failed_once", False):
            self._failed_once = True
            raise RuntimeError("first record boom")
        super().record_scenario(row)


class _StubCtxRestore:
    def __init__(self):
        self.scenario = []

    def record_scenario(self, row):
        self.scenario.append(dict(row))


class TestR26Point1RestoreOnEveryExit(_GuardedTestCase):
    def setUp(self):
        super().setUp()
        _FakePartContext.calls = []
        _FakePartContext.instances = []
        _RaisingPartContext.calls = []

    def _backup_and_mutate(self, tmp):
        env, mission, storage, _backup = _make_env(tmp)
        with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
            t0, slot = s_persist_run._backup_storage(env, tmp / "slot_backup", "t0")
        (storage / "players.db").write_bytes(b"players-calentados")
        return env, storage, t0, slot

    def test_context_open_failure_attempts_restore_and_writes_receipt(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, storage, t0, slot = self._backup_and_mutate(tmp)
            base_dir = tmp / "evidence"
            backup_return = (env, t0, slot, None, "")
            with mock.patch.object(s_persist_run, "_live_cold_backup_before_open", return_value=backup_return), mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]), mock.patch.object(f03_common, "PartContext", _RaisingPartContext):
                with self.assertRaises(RuntimeError) as raised:
                    s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertEqual(str(raised.exception), "open boom")
            self.assertEqual((storage / "players.db").read_bytes(), b"players-baseline")
            self.assertTrue(slot.is_dir())
            self.assertEqual((slot / "players.db").read_bytes(), b"players-baseline")
            receipt_path = base_dir / "run" / "samples" / "scenario.jsonl"
            self.assertTrue(receipt_path.is_file())
            rows = [json.loads(l) for l in receipt_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            restores = [r for r in rows if r.get("ev") == "storage_restore_result"]
            self.assertEqual(len(restores), 1)
            self.assertEqual(restores[0].get("restore_ok_b"), 1)
            self.assertEqual(restores[0].get("restore_incomplete_b"), 0)
            self.assertIn("context_open_failed", str(restores[0].get("error") or ""))
            self.assertIn("open boom", str(restores[0].get("error") or ""))

    def test_first_body_record_failure_restores_without_unbound(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, storage, t0, slot = self._backup_and_mutate(tmp)
            base_dir = tmp / "evidence"
            _FakePartContext.next_startup_reason = None
            backup_return = (env, t0, slot, None, "")
            with mock.patch.object(s_persist_run, "_live_cold_backup_before_open", return_value=backup_return), mock.patch.object(s_persist_run, "_probe_sources_at_commit", return_value={}), mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]), mock.patch.object(f03_common, "PartContext", _FailFirstRecordContext):
                with self.assertRaises(RuntimeError) as raised:
                    s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertEqual(str(raised.exception), "first record boom")
            self.assertNotIsInstance(raised.exception, UnboundLocalError)
            scenario = _FakePartContext.instances[0].scenario
            restores = [r for r in scenario if r.get("ev") == "storage_restore_result"]
            self.assertEqual(len(restores), 1)
            self.assertEqual(restores[0].get("restore_ok_b"), 1)
            self.assertEqual((storage / "players.db").read_bytes(), b"players-baseline")
            self.assertTrue(slot.is_dir())

    def test_operator_step_failure_still_attempts_restore_and_records_receipt(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, storage, t0, slot = self._backup_and_mutate(tmp)
            ctx = _StubCtxRestore()
            calls = {"n": 0}

            def fake_list(_env):
                calls["n"] += 1
                if calls["n"] == 1:
                    return [{"name": "DayZServer_x64.exe", "pid": 81, "command_line": "DayZServer_x64.exe -server"}]
                return []

            with mock.patch.object(s_persist_run, "_list_server_processes", side_effect=fake_list), mock.patch.object(f03_common, "await_operator", side_effect=RuntimeError("operator boom")):
                result = s_persist_run._cold_restore_live_storage(ctx, env, slot, t0, stop_step="post_backup_stop_server_for_cold_restore")
            self.assertEqual(result, 1)
            self.assertEqual(len(ctx.scenario), 1)
            self.assertEqual(ctx.scenario[0].get("ev"), "storage_restore_result")
            self.assertEqual(ctx.scenario[0].get("restore_ok_b"), 1)
            self.assertEqual(ctx.scenario[0].get("restore_incomplete_b"), 0)
            self.assertIn("operator_step_failed", str(ctx.scenario[0].get("error") or ""))
            self.assertIn("operator boom", str(ctx.scenario[0].get("error") or ""))
            self.assertEqual((storage / "players.db").read_bytes(), b"players-baseline")
            self.assertTrue(slot.is_dir())

    def test_operator_failure_with_server_still_running_records_incomplete(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, storage, t0, slot = self._backup_and_mutate(tmp)
            ctx = _StubCtxRestore()
            running = [{"name": "DayZServer_x64.exe", "pid": 82, "command_line": "DayZServer_x64.exe -server"}]
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=running), mock.patch.object(f03_common, "await_operator", side_effect=RuntimeError("operator boom")):
                result = s_persist_run._cold_restore_live_storage(ctx, env, slot, t0, stop_step="post_backup_stop_server_for_cold_restore")
            self.assertEqual(result, 0)
            self.assertEqual(len(ctx.scenario), 1)
            self.assertEqual(ctx.scenario[0].get("restore_incomplete_b"), 1)
            self.assertIn("operator_step_failed", str(ctx.scenario[0].get("error") or ""))
            self.assertEqual((storage / "players.db").read_bytes(), b"players-calentados")
            self.assertTrue(slot.is_dir())
            self.assertEqual((slot / "players.db").read_bytes(), b"players-baseline")


_OUR_SERVER_CMD = '"C:\\Program Files (x86)\\Steam\\steamapps\\common\\DayZ\\DayZDiag_x64.exe" -server "-config=C:\\tmp\\dsbx-f03b-work\\s-persist-diag\\run_20261117T065425Z\\b1\\server\\serverDZ.cfg" "-profiles=C:\\tmp\\dsbx-f03b-work\\s-persist-diag\\run_20261117T065425Z\\profiles\\server" "-mission=C:\\tmp\\dsbx-f03b-work\\s-persist-diag\\run_20261117T065425Z\\b1\\mpmissions\\dayzOffline.chernarusplus" "-mod=C:\\tmp\\dsbx-f03b-work\\s-persist-diag\\run_20261117T065425Z\\pbo\\@DayZSandbox_QA" -port=2702 -dologs -adminlog -freezecheck'
_OTHER_SERVER_CMD = '"C:\\Program Files (x86)\\Steam\\steamapps\\common\\DayZ\\DayZDiag_x64.exe" -server -config=P:\\DayZ_MCP_dev\\_server\\serverDZ.cfg -profiles=P:\\DayZ_MCP_dev\\_server\\profiles "-mission=C:\\Program Files (x86)\\Steam\\steamapps\\common\\DayZServer\\mpmissions\\dayzOffline.chernarusplus" -mod=P:\\Mods\\@DayZ_MCP;P:\\Mods\\@CF -filePatching -port=2302'


def _env_for_mission(mission_dir):
    return {
        "server_root_dir": "C:\\qa\\srv",
        "mission_dir": mission_dir,
        "storage_dir": mission_dir + "\\storage_1",
        "storage_data_dir": mission_dir + "\\storage_1\\data",
        "server_exe_names": ["DayZServer_x64.exe", "DayZDiag_x64.exe"],
    }


class TestR26MissionParsing(_GuardedTestCase):
    def test_our_server_sample(self):
        mission = "C:\\tmp\\dsbx-f03b-work\\s-persist-diag\\run_20261117T065425Z\\b1\\mpmissions\\dayzOffline.chernarusplus"
        env = _env_for_mission(mission)
        self.assertEqual(s_persist_run._mission_from_command_line(_OUR_SERVER_CMD), s_persist_run._resolve_abs(mission))
        row = {"name": "DayZDiag_x64.exe", "pid": 91, "command_line": _OUR_SERVER_CMD}
        self.assertEqual(s_persist_run._verify_storage_mission(env, rows=[row]), (True, ""))

    def test_other_server_sample_with_spaces(self):
        mission = "C:\\Program Files (x86)\\Steam\\steamapps\\common\\DayZServer\\mpmissions\\dayzOffline.chernarusplus"
        env = _env_for_mission(mission)
        self.assertEqual(s_persist_run._mission_from_command_line(_OTHER_SERVER_CMD), s_persist_run._resolve_abs(mission))
        row = {"name": "DayZDiag_x64.exe", "pid": 92, "command_line": _OTHER_SERVER_CMD}
        self.assertEqual(s_persist_run._verify_storage_mission(env, rows=[row]), (True, ""))

    def test_m_vs_m_b_does_not_accredit_wrong_mission(self):
        declared = "C:\\qa\\srv\\mpmissions\\m"
        running_mission = "C:\\qa\\srv\\mpmissions\\m B"
        env = _env_for_mission(declared)
        cmd = 'DayZServer_x64.exe -server "-mission=C:\\qa\\srv\\mpmissions\\m B"'
        self.assertEqual(s_persist_run._mission_from_command_line(cmd), s_persist_run._resolve_abs(running_mission))
        row = {"name": "DayZServer_x64.exe", "pid": 93, "command_line": cmd}
        ok, err = s_persist_run._verify_storage_mission(env, rows=[row])
        self.assertFalse(ok)
        self.assertEqual(err, "storage_mission_mismatch")
        env_b = _env_for_mission(running_mission)
        self.assertEqual(s_persist_run._verify_storage_mission(env_b, rows=[row]), (True, ""))

    def test_mission_equals_quoted_value(self):
        running_mission = "C:\\qa\\srv\\mpmissions\\m B"
        env = _env_for_mission(running_mission)
        cmd = 'DayZServer_x64.exe -server -mission="C:\\qa\\srv\\mpmissions\\m B"'
        self.assertEqual(s_persist_run._mission_from_command_line(cmd), s_persist_run._resolve_abs(running_mission))
        row = {"name": "DayZServer_x64.exe", "pid": 94, "command_line": cmd}
        self.assertEqual(s_persist_run._verify_storage_mission(env, rows=[row]), (True, ""))
        env_m = _env_for_mission("C:\\qa\\srv\\mpmissions\\m")
        ok, _err = s_persist_run._verify_storage_mission(env_m, rows=[row])
        self.assertFalse(ok)

    def test_two_mission_options_are_unverified(self):
        mission = "C:\\qa\\srv\\mpmissions\\m"
        env = _env_for_mission(mission)
        cmd = 'DayZServer_x64.exe -server "-mission=C:\\qa\\srv\\mpmissions\\m" "-mission=C:\\qa\\srv\\mpmissions\\m"'
        self.assertIsNone(s_persist_run._mission_from_command_line(cmd))
        row = {"name": "DayZServer_x64.exe", "pid": 95, "command_line": cmd}
        ok, err = s_persist_run._verify_storage_mission(env, rows=[row])
        self.assertFalse(ok)
        self.assertIn("storage_mission_unverified", err)

    def test_unreadable_command_line_is_unverified(self):
        mission = "C:\\qa\\srv\\mpmissions\\m"
        env = _env_for_mission(mission)
        cmd = 'DayZServer_x64.exe -server "-mission=C:\\qa\\srv\\mpmissions\\m'
        self.assertIsNone(s_persist_run._mission_from_command_line(cmd))
        row = {"name": "DayZServer_x64.exe", "pid": 96, "command_line": cmd}
        ok, err = s_persist_run._verify_storage_mission(env, rows=[row])
        self.assertFalse(ok)
        self.assertIn("storage_mission_unverified", err)


class TestR26RecreatedDest(_GuardedTestCase):
    def test_recreated_dest_is_reported_and_preserved(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, mission, storage, backup = _make_env(tmp)
            with mock.patch.object(s_persist_run, "_list_server_processes", return_value=[]):
                t0, slot = s_persist_run._backup_storage(env, backup, "t0")
            (storage / "players.db").write_bytes(b"players-mutados")
            mutated = _tree_bytes(storage)
            calls = {"n": 0}

            def fake_list(_env):
                calls["n"] += 1
                if calls["n"] <= 2:
                    return []
                if not storage.exists():
                    storage.mkdir(parents=True)
                    (storage / "recreated.bin").write_bytes(b"recreated-by-server")
                return [{"name": "DayZServer_x64.exe", "pid": 97, "command_line": "DayZServer_x64.exe -server"}]

            with mock.patch.object(s_persist_run, "_list_server_processes", side_effect=fake_list):
                ok, _snap, err = s_persist_run._restore_storage(env, slot, t0)
            self.assertEqual(ok, 0)
            self.assertIn("storage_restore_dest_recreated", err)
            rollbacks = sorted(mission.glob(".storage_1.r7rollback-*"))
            self.assertEqual(len(rollbacks), 1)
            self.assertIn(str(rollbacks[0]), err)
            self.assertIn(str(slot), err)
            self.assertTrue(storage.is_dir())
            self.assertEqual((storage / "recreated.bin").read_bytes(), b"recreated-by-server")
            self.assertEqual(_tree_bytes(rollbacks[0]), mutated)
            self.assertTrue(slot.is_dir())
            self.assertEqual((slot / "players.db").read_bytes(), b"players-baseline")


class TestCensusLeaseSnapshot(_GuardedTestCase):
    """Punto 1 (lease22): instantanea del lease al empezar la captura."""

    def _applied_clock_ext(self):
        peer, jobs, ext = _make_clock_fake()
        status, _, _ = ext.on_start_op(
            {"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_x", "scop-1", 1, _SCENE_ROWS), {},
        )
        self.assertEqual(status, "done")
        return peer, jobs, ext

    def test_a_long_capture_with_valid_start_lease_is_done(self):
        peer, jobs, ext = self._applied_clock_ext()
        ext.capture_delay_ms = 5000.0  # mas que lease_ms = 3000
        status, _, payload = ext.on_start_op(
            {"op_id": "op-census-a", "verb": "per_census_start", "qa_fault": ""},
            _census_args(), {},
        )
        self.assertEqual(status, "done")
        out = wire.unpack_payload(payload)
        self.assertEqual(out["num"]["capture_wall_ms"], 5000.0)
        self.assertEqual(out["num"]["rows_captured_n"], 2.0)
        peer.renew()  # el siguiente poll renueva antes del cierre
        peer.now += 1000.0
        for _ in range(6):
            ext.on_tick(0.016)
        job = jobs.jobs_by_id["op-census-a"]
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["rows_total"], 2)

    def test_b_lease_expired_at_start_fails_without_rows(self):
        peer, jobs, ext = _make_clock_fake()
        peer.now = 10000.0  # edad del lease: 9000 ms > 3000 ms
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-census-b", "verb": "per_census_start", "qa_fault": ""},
            _census_args(), {},
        )
        self.assertEqual((status, reason), ("error", "lease_expired"))
        self.assertEqual(jobs.get_state("op-census-b"), "")
        self.assertNotIn("op-census-b", jobs.jobs_by_id)

    def test_c_lease_expired_at_finish_fails_by_deadman(self):
        peer, jobs, ext = self._applied_clock_ext()
        ext.capture_delay_ms = 100.0
        status, _, _ = ext.on_start_op(
            {"op_id": "op-census-c", "verb": "per_census_start", "qa_fault": ""},
            _census_args(), {},
        )
        self.assertEqual(status, "done")
        peer.now += 4000.0  # sin renovar: vencido en end_tick_ms
        for _ in range(6):
            ext.on_tick(0.016)
        job = jobs.jobs_by_id["op-census-c"]
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["reason"], "lease_expired")
        self.assertEqual(job["rows_total"], 2)  # la captura si capturo

    def test_d_capture_budget_exceeded_fails(self):
        peer, jobs, ext = self._applied_clock_ext()
        ext.capture_delay_ms = fake_ext_persist.CENSUS_CAPTURE_BUDGET_MS + 10000.0
        status, _, _ = ext.on_start_op(
            {"op_id": "op-census-d", "verb": "per_census_start", "qa_fault": ""},
            _census_args(), {},
        )
        self.assertEqual(status, "done")
        peer.renew()
        peer.now += 1000.0
        for _ in range(6):
            ext.on_tick(0.016)
        job = jobs.jobs_by_id["op-census-d"]
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["reason"], "capture_budget_exceeded")


class TestActorGlovesBornInInventory(_GuardedTestCase):
    """Punto 2a (lease22): pin estatico de los guantes nacidos en inventario."""

    def test_c_births_actor_gloves_in_inventory(self):
        src = (
            QA_DIR
            / "probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_X_Persist.c"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertIn("bornInInventory", src)
        self.assertIn("LocationCreateEntity", src)
        self.assertIn("CreateObjectEx", src)  # la via staged sigue para el resto
        self.assertIn("m_PurgeJobId", src)
        self.assertIn("per_purge_start", src)


_ACTOR_ROWS = [
    {"logical_id": "b_act_1", "parent_id": "", "cat": "actor", "class_name": "SurvivorF_Eva",
     "slot_name": "", "req_x_m": 4680.0, "req_z_m": 10200.0, "req_yaw_deg": 0.0,
     "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
    {"logical_id": "b_act_1_gloves_dir", "parent_id": "b_act_1", "cat": "child_attach",
     "class_name": "WorkingGloves_Yellow", "slot_name": "Gloves", "req_x_m": 4680.0,
     "req_z_m": 10200.0, "req_yaw_deg": 0.0, "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
    {"logical_id": "b_act_1_armband_drop", "parent_id": "b_act_1", "cat": "child_attach",
     "class_name": "Armband_Blue", "slot_name": "Armband", "req_x_m": 4680.0,
     "req_z_m": 10200.0, "req_yaw_deg": 0.0, "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
]


class TestDirectorGarmentPurge(_GuardedTestCase):
    """P2c: la purga la ordena el runner con pers_id; solo borra lo autorizado."""

    def _ext_with_director_gloves(self):
        peer, jobs, ext = _make_clock_fake()
        status, _, _ = ext.on_start_op(
            {"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_b", "scop-1", 1, _ACTOR_ROWS), {},
        )
        self.assertEqual(status, "done")
        status, _, _ = ext.on_start_op(
            {"op_id": "op-trans", "verb": "per_child_transition", "qa_fault": ""},
            _unpacked(strings={"scene_id": "scene_b", "logical_id": "b_act_1_gloves_dir",
                               "action": "move_to_director", "expect_epoch": "epoch-1",
                               "target_scene_id": "", "target_parent_id": "",
                               "director_uid": ext.director_uid}), {},
        )
        self.assertEqual(status, "done")
        rec = ext._record_by("scene_b", "b_act_1_gloves_dir")
        return peer, jobs, ext, rec["ent"]["pers_id"], rec["ent"]["class_name"]

    def _start_purge(self, ext, rows):
        status, reason, payload = ext.on_start_op(
            {"op_id": "op-purge", "verb": "per_purge_start", "qa_fault": ""},
            _purge_args(rows, ext.director_uid), {},
        )
        self.assertEqual((status, reason), ("done", ""))
        return wire.unpack_payload(payload)

    def _run_purge(self, peer, jobs, ext, n=20):
        for _ in range(n):
            jobs.tick_jobs(0.016, peer.local_ms())
            ext.on_tick(0.016)
            if ext.purge_job_id == "":
                break

    def test_authorized_glove_deleted_basal_kept_and_emit_before_result(self):
        peer, jobs, ext, pers, cls = self._ext_with_director_gloves()
        basal = ext._add_entity(
            net_id="1:900", pers_id=ext._alloc_pers_id(), class_name="WorkingGloves_Beige",
            cat="director", loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
            owner_uid=ext.director_uid, pos=(4500.0, 100.0, 10200.0), persistent=True,
        )
        out = self._start_purge(ext, [{"pers_id": pers, "class_name": cls}])
        self.assertEqual(out["num"]["pre_n"], 4.0)
        glove_net = ext._record_by("scene_b", "b_act_1_gloves_dir")["ent"]["net_id"]
        self.assertIn(glove_net, ext.world)
        self._run_purge(peer, jobs, ext)
        job = jobs.jobs_by_id["op-purge"]
        self.assertEqual(job["state"], "done")
        self.assertNotIn(glove_net, ext.world)
        self.assertIn(basal["net_id"], ext.world)
        self.assertIn(fake_ext_persist.DIRECTOR_JEANS_NET, ext.world)
        rows = _job_rows(job)
        phases = [r["phase"] for r in rows]
        self.assertIn("pre", phases)
        self.assertIn("emit", phases)
        self.assertTrue(any(r["phase"] == "result" and r["result"] == "deleted" and r["pers_id"] == pers for r in rows))

    def test_tree_with_foreign_child_is_retained(self):
        peer, jobs, ext = _make_clock_fake()
        chest = ext._add_entity(
            net_id="1:901", pers_id="20:0:0:0", class_name="SeaChest", cat="director",
            loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
            owner_uid=ext.director_uid, pos=(4500.0, 100.0, 10200.0), persistent=True,
        )
        child = ext._add_entity(
            net_id="1:902", pers_id="21:0:0:0", class_name="WaterBottle", cat="raw",
            loc_kind="cargo", parent_net_id="1:901", owner_uid="", persistent=True,
        )
        self._start_purge(ext, [{"pers_id": chest["pers_id"], "class_name": "SeaChest"}])
        self._run_purge(peer, jobs, ext)
        self.assertIn(chest["net_id"], ext.world)
        self.assertIn(child["net_id"], ext.world)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        self.assertTrue(any(r["phase"] == "result" and r["result"] == "retained_foreign" for r in rows))
        self.assertEqual(jobs.jobs_by_id["op-purge"]["state"], "done")

    def test_duplicate_pers_id_is_ambiguous_and_other_class_is_retained(self):
        peer, jobs, ext = _make_clock_fake()
        a = ext._add_entity(net_id="1:903", pers_id="30:0:0:0", class_name="WorkingGloves_Yellow",
                            cat="director", loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
                            owner_uid=ext.director_uid, persistent=True)
        b = ext._add_entity(net_id="1:904", pers_id="30:0:0:0", class_name="WorkingGloves_Yellow",
                            cat="director", loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
                            owner_uid=ext.director_uid, persistent=True)
        c = ext._add_entity(net_id="1:905", pers_id="31:0:0:0", class_name="WorkingGloves_Yellow",
                            cat="director", loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
                            owner_uid=ext.director_uid, persistent=True)
        self._start_purge(ext, [
            {"pers_id": "30:0:0:0", "class_name": "WorkingGloves_Yellow"},
            {"pers_id": "31:0:0:0", "class_name": "RadarCap_Black"},
        ])
        self._run_purge(peer, jobs, ext)
        self.assertIn(a["net_id"], ext.world)
        self.assertIn(b["net_id"], ext.world)
        self.assertIn(c["net_id"], ext.world)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        results = {(r["pers_id"], r["result"]) for r in rows if r["phase"] == "result"}
        self.assertIn(("30:0:0:0", "ambiguous"), results)
        self.assertIn(("31:0:0:0", "retained_foreign"), results)

    def test_parent_falls_only_after_authorized_child(self):
        peer, jobs, ext = _make_clock_fake()
        chest = ext._add_entity(net_id="1:906", pers_id="40:0:0:0", class_name="SeaChest",
                                cat="director", loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
                                owner_uid=ext.director_uid, persistent=True)
        child = ext._add_entity(net_id="1:907", pers_id="41:0:0:0", class_name="WaterBottle",
                                cat="director", loc_kind="cargo", parent_net_id="1:906",
                                owner_uid=ext.director_uid, persistent=True)
        self._start_purge(ext, [
            {"pers_id": "40:0:0:0", "class_name": "SeaChest"},
            {"pers_id": "41:0:0:0", "class_name": "WaterBottle"},
        ])
        self._run_purge(peer, jobs, ext)
        self.assertNotIn(chest["net_id"], ext.world)
        self.assertNotIn(child["net_id"], ext.world)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        emit_pers = [r["pers_id"] for r in rows if r["phase"] == "emit"]
        self.assertIn("41:0:0:0", emit_pers)
        self.assertIn("40:0:0:0", emit_pers)
        self.assertLess(emit_pers.index("41:0:0:0"), emit_pers.index("40:0:0:0"))

    def test_lease_expires_between_candidates(self):
        peer, jobs, ext = _make_clock_fake()
        a = ext._add_entity(net_id="1:910", pers_id="50:0:0:0", class_name="WorkingGloves_Yellow",
                            cat="director", loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
                            owner_uid=ext.director_uid, persistent=True)
        b = ext._add_entity(net_id="1:911", pers_id="51:0:0:0", class_name="WorkingGloves_Yellow",
                            cat="director", loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
                            owner_uid=ext.director_uid, persistent=True)
        self._start_purge(ext, [
            {"pers_id": "50:0:0:0", "class_name": "WorkingGloves_Yellow"},
            {"pers_id": "51:0:0:0", "class_name": "WorkingGloves_Yellow"},
        ])
        jobs.tick_jobs(0.016, peer.local_ms())
        ext.on_tick(0.016)
        self.assertNotIn(a["net_id"], ext.world)
        peer.now = 6000.0  # lease vencido: 5000 > 3000
        jobs.tick_jobs(0.016, peer.local_ms())
        ext.on_tick(0.016)
        job = jobs.jobs_by_id["op-purge"]
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["reason"], "lease_expired")
        self.assertIn(b["net_id"], ext.world)
        rows = _job_rows(job)
        self.assertTrue(any(r["phase"] == "emit" and r["pers_id"] == "50:0:0:0" for r in rows))

    def test_deleted_only_after_confirming_absence(self):
        peer, jobs, ext, pers, cls = self._ext_with_director_gloves()
        glove_net = ext._record_by("scene_b", "b_act_1_gloves_dir")["ent"]["net_id"]
        self._start_purge(ext, [{"pers_id": pers, "class_name": cls}])
        jobs.tick_jobs(0.016, peer.local_ms())
        ext.on_tick(0.016)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        self.assertNotIn(glove_net, ext.world)
        self.assertFalse(any(r["phase"] == "result" and r["result"] == "deleted" for r in rows))
        jobs.tick_jobs(0.016, peer.local_ms())
        ext.on_tick(0.016)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        self.assertTrue(any(r["phase"] == "result" and r["result"] == "deleted" and r["pers_id"] == pers for r in rows))

    def test_purge_pending_blocks_census_without_effects(self):
        peer, jobs, ext, pers, cls = self._ext_with_director_gloves()
        self._start_purge(ext, [{"pers_id": pers, "class_name": cls}])
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-census", "verb": "per_census_start", "qa_fault": ""},
            _census_args(), {},
        )
        self.assertEqual((status, reason), ("rejected", "purge_pending"))
        self.assertEqual(jobs.get_state("op-census"), "")
        self._run_purge(peer, jobs, ext)
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-census-2", "verb": "per_census_start", "qa_fault": ""},
            _census_args(), {},
        )
        self.assertEqual((status, reason), ("done", ""))

    def test_client_handles_purge_but_deletes_nothing(self):
        peer, jobs, ext, pers, cls = self._ext_with_director_gloves()
        self.assertFalse(ext.handles("per_purge_start", "client"))
        glove_net = ext._record_by("scene_b", "b_act_1_gloves_dir")["ent"]["net_id"]
        ext.on_tick(0.016)
        self.assertIn(glove_net, ext.world)
        self.assertEqual(ext.purge_job_id, "")


class TestP2dPurgeContract(_GuardedTestCase):
    """P2d: confirm_tick_ms, owner medido, profundidad y lease del fake."""

    def _ext_with_director_gloves(self):
        peer, jobs, ext = _make_clock_fake()
        status, _, _ = ext.on_start_op(
            {"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_b", "scop-1", 1, _ACTOR_ROWS), {},
        )
        self.assertEqual(status, "done")
        status, _, _ = ext.on_start_op(
            {"op_id": "op-trans", "verb": "per_child_transition", "qa_fault": ""},
            _unpacked(strings={"scene_id": "scene_b", "logical_id": "b_act_1_gloves_dir",
                               "action": "move_to_director", "expect_epoch": "epoch-1",
                               "target_scene_id": "", "target_parent_id": "",
                               "director_uid": ext.director_uid}), {},
        )
        self.assertEqual(status, "done")
        rec = ext._record_by("scene_b", "b_act_1_gloves_dir")
        return peer, jobs, ext, rec["ent"]["pers_id"], rec["ent"]["class_name"]

    def _start_purge(self, ext, rows):
        status, reason, payload = ext.on_start_op(
            {"op_id": "op-purge", "verb": "per_purge_start", "qa_fault": ""},
            _purge_args(rows, ext.director_uid), {},
        )
        self.assertEqual((status, reason), ("done", ""))
        return wire.unpack_payload(payload)

    def _run_purge(self, peer, jobs, ext, n=30):
        for _ in range(n):
            jobs.tick_jobs(0.016, peer.local_ms())
            ext.on_tick(0.016)
            if ext.purge_job_id == "":
                break

    def test_confirm_tick_is_after_emit_and_other_rows_are_zero(self):
        peer, jobs, ext, pers, cls = self._ext_with_director_gloves()
        self._start_purge(ext, [{"pers_id": pers, "class_name": cls}])
        self._run_purge(peer, jobs, ext)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        emits = [r for r in rows if r["phase"] == "emit" and r["pers_id"] == pers]
        deleted = [r for r in rows if r["phase"] == "result"
                   and r["result"] == "deleted" and r["pers_id"] == pers]
        self.assertTrue(emits)
        self.assertTrue(deleted)
        self.assertGreater(deleted[0]["confirm_tick_ms"], emits[0]["emit_tick_ms"])
        for row in rows:
            if not (row["phase"] == "result" and row["result"] == "deleted"):
                self.assertEqual(row["confirm_tick_ms"], 0.0)

    def test_absent_row_owner_uid_is_measured_empty(self):
        peer, jobs, ext = _make_clock_fake()
        self._start_purge(ext, [{"pers_id": "99:0:0:0", "class_name": "WorkingGloves_Yellow"}])
        self._run_purge(peer, jobs, ext)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        absent = [r for r in rows if r["phase"] == "result" and r["result"] == "absent"]
        self.assertTrue(absent)
        self.assertEqual(absent[0]["owner_uid"], "")

    def test_depth_matches_director_as_virtual_root(self):
        peer, jobs, ext = _make_clock_fake()
        jeans_pers = ext.world[fake_ext_persist.DIRECTOR_JEANS_NET]["pers_id"]
        chest = ext._add_entity(
            net_id="1:920", pers_id="60:0:0:0", class_name="SeaChest", cat="director",
            loc_kind="cargo", parent_net_id=fake_ext_persist.DIRECTOR_JEANS_NET,
            owner_uid=ext.director_uid, persistent=True,
        )
        child = ext._add_entity(
            net_id="1:921", pers_id="61:0:0:0", class_name="WaterBottle", cat="director",
            loc_kind="cargo", parent_net_id="1:920", owner_uid=ext.director_uid,
            persistent=True,
        )
        self._start_purge(ext, [
            {"pers_id": "60:0:0:0", "class_name": "SeaChest"},
            {"pers_id": "61:0:0:0", "class_name": "WaterBottle"},
        ])
        self._run_purge(peer, jobs, ext)
        rows = _job_rows(jobs.jobs_by_id["op-purge"])
        depth = {r["pers_id"]: r["depth_n"] for r in rows if r["phase"] == "pre"}
        self.assertEqual(depth[jeans_pers], 1.0)
        self.assertEqual(depth["60:0:0:0"], 2.0)
        self.assertEqual(depth["61:0:0:0"], 3.0)
        self.assertNotIn(chest["net_id"], ext.world)
        self.assertNotIn(child["net_id"], ext.world)

    def test_purge_start_rejects_expired_lease(self):
        peer, jobs, ext = _make_clock_fake()
        peer.now = 6000.0  # edad 5000 ms > 3000 ms
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-purge", "verb": "per_purge_start", "qa_fault": ""},
            _purge_args([{"pers_id": "3:0:0:0", "class_name": "WorkingGloves_Yellow"}],
                        ext.director_uid), {},
        )
        self.assertEqual((status, reason), ("error", "lease_expired"))
        self.assertEqual(ext.purge_job_id, "")
        self.assertNotIn("op-purge", jobs.jobs_by_id)

    def test_cleanup_deletes_scene_actor_and_keeps_director(self):
        peer, jobs, ext = _make_fake()
        self.assertEqual(ext.on_start_op(
            {"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_b", "scop-1", 1, _ACTOR_ROWS), {})[0], "done")
        actor = ext._record_by("scene_b", "b_act_1")["ent"]
        gloves = ext._record_by("scene_b", "b_act_1_gloves_dir")["ent"]
        status, _, payload = ext.on_start_op(
            {"op_id": "op-clean", "verb": "per_cleanup_qa", "qa_fault": ""},
            _unpacked(strings={"cleanup_tag": "t6"},
                      ncol=["center_x_m", "center_z_m", "radius_m"],
                      scol=["area_tag"],
                      rows=[{"area_tag": "area_b", "center_x_m": 4680.0,
                             "center_z_m": 10200.0, "radius_m": 60.0}]), {},
        )
        self.assertEqual(status, "done")
        self.assertNotIn(actor["net_id"], ext.world)
        self.assertNotIn(gloves["net_id"], ext.world)
        self.assertIn(fake_ext_persist.DIRECTOR_JEANS_NET, ext.world)
        self.assertIn(fake_ext_persist.DIRECTOR_APPLE_NET, ext.world)
        out = wire.unpack_payload(payload)
        self.assertGreaterEqual(out["num"]["cleaned_own_n"], 2.0)


class TestRunnerPurgeStartContract(_GuardedTestCase):
    """P2d: la interfaz de la purga (job=op_id, epoch, timeout y parada)."""

    def _accredited(self):
        return [{"pers_id": "3:0:0:0", "class_name": "WorkingGloves_Yellow",
                 "logical_id": "b_act_1_gloves_dir", "net_id": "1:10"}]

    def _payload_job(self, payload):
        sk = list((payload or {}).get("sk") or [])
        sv = list((payload or {}).get("sv") or [])
        return sv[sk.index("job")] if "job" in sk else None

    def test_job_is_op_id_and_page_size_eight(self):
        self.assertEqual(fake_ext_persist.PURGE_PAGE_SIZE, 8)
        ctx = _FakeCtxT4(now_ms=5000.0)
        calls = []

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            calls.append((verb, payload, kwargs.get("target_inst")))
            if verb == "per_purge_start":
                return _op_outcome("done", "", "op-start", {
                    "str": {"job": "op-start", "state": "done"},
                    "num": {"pre_n": 0.0},
                })
            if verb == "job_read":
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "op-start", "state": "done"},
                    "num": {"page_n": 0.0, "pages_n": 0.0, "rows_total_n": 0.0},
                    "rows": [],
                })
            if verb == "job_free":
                return _op_outcome("done", "", "op-free", {"str": {"job": "op-start", "freed": "1"}})
            raise AssertionError(verb)

        clock = _FakeClock()
        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=5.0, poll_s=1.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertTrue(result["done"])
        for verb, payload, target in calls:
            if verb in ("job_read", "job_stop", "job_free"):
                self.assertEqual(self._payload_job(payload), "op-start")
                self.assertEqual(target, "epoch-new")

    def test_ack_alias_is_ignored_and_mismatch_recorded(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        calls = []

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            calls.append((verb, payload, kwargs.get("target_inst")))
            if verb == "per_purge_start":
                return _op_outcome("done", "", "op-start", {
                    "str": {"job": "alias", "state": "done"},
                    "num": {"pre_n": 0.0},
                })
            if verb == "job_read":
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "alias", "state": "done"},
                    "num": {"page_n": 0.0, "pages_n": 0.0, "rows_total_n": 0.0},
                    "rows": [],
                })
            if verb == "job_free":
                return _op_outcome("done", "", "op-free", {"str": {"job": "alias", "freed": "1"}})
            raise AssertionError(verb)

        clock = _FakeClock()
        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=5.0, poll_s=1.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertTrue(result["done"])
        self.assertTrue(any(ev.get("ev") == "purge_job_mismatch" for ev in ctx.scenario))
        for verb, payload, _target in calls:
            if verb == "job_read":
                self.assertEqual(self._payload_job(payload), "op-start")

    def test_empty_server_epoch_does_not_order_purge(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        with mock.patch.object(f03_common, "issue_one", side_effect=AssertionError("no debe llamar")):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="", director_uid="dir-uid",
            )
        self.assertFalse(result["done"])
        self.assertEqual(result["reason"], "restart_not_validated")
        self.assertTrue(any(ev.get("ev") == "purge_not_done"
                            and ev.get("reason") == "restart_not_validated"
                            for ev in ctx.scenario))

    def test_restart_live_without_hello_has_no_epoch(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        with mock.patch.object(
            f03_common, "await_operator", return_value={"ok": True, "step": "t4_restart"}
        ), mock.patch.object(
            f03_common, "issue_one", side_effect=AssertionError("no debe llamar")
        ), mock.patch.object(
            s_persist_run.time, "sleep", lambda _s: None
        ):
            result = s_persist_run._restart_server_live(ctx, "epoch-old", "director-1")
        self.assertEqual(result, "")
        self.assertTrue(any(ev.get("ev") == "live_restart_failed"
                            and ev.get("reason") == "epoch_not_from_accepted_hello"
                            for ev in ctx.scenario))

    def test_restart_live_status_uses_new_epoch_target(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        calls = []

        def fake_await(ctx_arg, **kwargs):
            return {"ok": True, "event": {"ev": "hello", "http": 200,
                                          "peer": "server", "inst": "epoch-new",
                                          "t_ms": 5001.0}}

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            calls.append((verb, payload, kwargs.get("target_inst")))
            if verb != "per_status":
                raise AssertionError(verb)
            return SimpleNamespace(
                status="done", reason="", op_id="op-status",
                payload={
                    "str": {"server_epoch": "epoch-new", "director_uid": "director-1"},
                    "num": {"director_present_b": 1.0, "director_alive_b": 1.0,
                            "director_inv_readable_b": 1.0, "players_n": 1.0,
                            "tick_ms": 100.0},
                },
            )

        with mock.patch.object(f03_common, "await_operator", side_effect=fake_await), \
             mock.patch.object(f03_common, "issue_one", side_effect=fake_issue), \
             mock.patch.object(s_persist_run.time, "sleep", lambda _s: None):
            result = s_persist_run._restart_server_live(ctx, "epoch-old", "director-1")
        self.assertEqual(result, "epoch-new")
        self.assertTrue(calls)
        for verb, payload, target in calls:
            self.assertEqual(verb, "per_status")
            self.assertEqual(target, "epoch-new")
            sk = list((payload or {}).get("sk") or [])
            sv = list((payload or {}).get("sv") or [])
            self.assertEqual(sv[sk.index("director_uid")], "director-1")

    def test_timeout_start_stops_job_with_op_id(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        calls = []

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            calls.append((verb, payload, kwargs.get("target_inst")))
            if verb == "per_purge_start":
                return _op_outcome("timeout", "", "op-start", None)
            if verb == "job_read":
                state = "stopped" if any(v == "job_stop" for v, _p, _t in calls) else "running"
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "op-start", "state": state},
                    "num": {"page_n": 0.0, "pages_n": 0.0, "rows_total_n": 0.0},
                    "rows": [],
                })
            if verb == "job_stop":
                return _op_outcome("done", "", "op-stop", {"str": {"job": "op-start", "state": "stopped"}})
            if verb == "job_free":
                return _op_outcome("done", "", "op-free", {"str": {"job": "op-start", "freed": "1"}})
            raise AssertionError(verb)

        clock = _FakeClock()
        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=1.0, poll_s=1.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(result["done"])
        self.assertEqual(result["state"], "stopped")
        self.assertTrue(any(v == "job_stop" for v, _p, _t in calls))
        for verb, payload, target in calls:
            if verb in ("job_read", "job_stop", "job_free"):
                self.assertEqual(self._payload_job(payload), "op-start")
                self.assertEqual(target, "epoch-new")

    def test_start_rejected_before_job_does_not_stop(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        calls = []

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            calls.append((verb, payload, kwargs.get("target_inst")))
            if verb == "per_purge_start":
                return _op_outcome("rejected", "stale_epoch", "op-start", None)
            if verb == "job_read":
                return _op_outcome("error", "unknown_job", "op-read", None)
            raise AssertionError(verb)

        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=1.0, poll_s=1.0,
                monotonic=_FakeClock().monotonic, sleep=_FakeClock().sleep,
            )
        self.assertFalse(result["done"])
        self.assertTrue(result["cold_stop_ok"])
        self.assertFalse(any(v == "job_stop" for v, _p, _t in calls))

    def test_cold_stop_unaccredited_does_not_allow_live_cleanup(self):
        ctx = _FakeCtxT4(now_ms=5000.0)

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            if verb == "per_purge_start":
                return _op_outcome("timeout", "", "op-start", None)
            if verb == "job_read":
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "op-start", "state": "running"},
                    "num": {"page_n": 0.0, "pages_n": 0.0, "rows_total_n": 0.0},
                    "rows": [],
                })
            if verb == "job_stop":
                return _op_outcome("done", "", "op-stop", {"str": {"job": "op-start", "state": "stopped"}})
            raise AssertionError(verb)

        clock = _FakeClock()
        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue), \
             mock.patch.object(f03_common, "await_operator",
                               return_value={"ok": False, "reason": "operator_timeout"}):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=1.0, poll_s=1.0,
                monotonic=clock.monotonic, sleep=clock.sleep, storage_env=None,
            )
        self.assertFalse(result["done"])
        self.assertFalse(result["cold_stop_ok"])
        self.assertTrue(any(ev.get("ev") == "purge_cold_stop"
                            and ev.get("accredited_b") == 0 for ev in ctx.scenario))

    def test_cold_stop_accredited_allows_live_cleanup(self):
        ctx = _FakeCtxT4(now_ms=5000.0)

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            if verb == "per_purge_start":
                return _op_outcome("lost", "", "op-start", None)
            if verb == "job_read":
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "op-start", "state": "running"},
                    "num": {"page_n": 0.0, "pages_n": 0.0, "rows_total_n": 0.0},
                    "rows": [],
                })
            if verb == "job_stop":
                return _op_outcome("done", "", "op-stop", {"str": {"job": "op-start", "state": "stopped"}})
            raise AssertionError(verb)

        clock = _FakeClock()
        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue), \
             mock.patch.object(f03_common, "await_operator",
                               return_value={"ok": True, "step": "t4_purge_cold_stop"}):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=1.0, poll_s=1.0,
                monotonic=clock.monotonic, sleep=clock.sleep, storage_env=None,
            )
        self.assertFalse(result["done"])
        self.assertTrue(result["cold_stop_ok"])

    def test_pages_incomplete_does_not_open_t5(self):
        ctx = _FakeCtxT4(now_ms=5000.0)

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            if verb == "per_purge_start":
                return _op_outcome("done", "", "op-start", {
                    "str": {"job": "op-start", "state": "running"},
                    "num": {"pre_n": 1.0},
                })
            if verb == "job_read":
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "op-start", "state": "done"},
                    "num": {"page_n": 0.0, "pages_n": 1.0, "rows_total_n": 2.0},
                    "rows": [{"phase": "result", "result": "deleted"}],
                })
            if verb == "job_free":
                return _op_outcome("done", "", "op-free", {"str": {"job": "op-start", "freed": "1"}})
            raise AssertionError(verb)

        clock = _FakeClock()
        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=5.0, poll_s=1.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(result["done"])
        self.assertTrue(any(ev.get("ev") == "purge_pages_incomplete" for ev in ctx.scenario))


class TestStaticP2dContract(_GuardedTestCase):
    """P2d: pin estatico de los cambios que no se ejercitan offline."""

    def _c_src(self):
        return (QA_DIR / "probe/DayZSandbox_QA/scripts/5_Mission/DSBX_QA_X_Persist.c").read_text(
            encoding="utf-8", errors="replace")

    def test_c_cleanup_only_excludes_director_inventory(self):
        src = self._c_src()
        self.assertIn("cleanupDirector", src)
        self.assertIn("recEnt.GetHierarchyRootPlayer() == cleanupDirector", src)
        self.assertNotIn("recEnt.GetHierarchyRootPlayer() != null", src)
        self.assertIn("ent.GetHierarchyRootPlayer() == cleanupDirector", src)

    def test_c_confirm_tick_column_and_director_candidate_guard(self):
        src = self._c_src()
        self.assertIn('ncol.Insert("confirm_tick_ms")', src)
        self.assertIn("cand == dirEnt", src)
        self.assertIn("ackState", src)
        self.assertIn("m_PurgeConfirmEmitTick", src)

    def test_runner_accredited_before_restart_and_cleanup_skip(self):
        src = (QA_DIR / "s_persist_run.py").read_text(encoding="utf-8")
        self.assertLess(src.index("purge_authorized"), src.index("server_epoch_new = _restart_server"))
        self.assertIn("skip_live_cleanup = True", src)
        self.assertIn("if not skip_live_cleanup:", src)


class TestTransitionBornInInventory(_GuardedTestCase):
    """P2c: FLAGS_INV_OWN en el destino efectivo; brazalete estatico -> bad_args."""

    _AC_ROWS = [
        {"logical_id": "ac_act_1", "parent_id": "", "cat": "actor", "class_name": "SurvivorM_Mirek",
         "slot_name": "", "req_x_m": 4500.0, "req_z_m": 10200.0, "req_yaw_deg": 0.0,
         "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
        {"logical_id": "ac_act_1_gloves_dir", "parent_id": "ac_act_1", "cat": "child_attach",
         "class_name": "WorkingGloves_Beige", "slot_name": "Gloves", "req_x_m": 4500.0,
         "req_z_m": 10200.0, "req_yaw_deg": 0.0, "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
    ]

    def _ext(self):
        peer, jobs, ext = _make_clock_fake()
        self.assertEqual(ext.on_start_op(
            {"op_id": "op-apply-b", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_b", "scop-b", 1, _ACTOR_ROWS), {})[0], "done")
        self.assertEqual(ext.on_start_op(
            {"op_id": "op-apply-ac", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_a_clean", "scop-ac", 1, self._AC_ROWS), {})[0], "done")
        return peer, jobs, ext

    def _move(self, ext, scene_id, lid, action, target_scene="", target_parent=""):
        return ext.on_start_op(
            {"op_id": f"op-{lid}", "verb": "per_child_transition", "qa_fault": ""},
            _unpacked(strings={"scene_id": scene_id, "logical_id": lid, "action": action,
                               "expect_epoch": "epoch-1", "target_scene_id": target_scene,
                               "target_parent_id": target_parent,
                               "director_uid": ext.director_uid}), {},
        )

    def test_static_armband_rejected_for_director_and_for_player_container(self):
        peer, jobs, ext = self._ext()
        status, _, _ = self._move(ext, "scene_b", "b_act_1_gloves_dir", "move_to_director")
        self.assertEqual(status, "done")
        arm = ext._record_by("scene_b", "b_act_1_armband_drop")["ent"]
        self.assertEqual(arm["loc_kind"], "attachment")
        status, reason, _ = self._move(ext, "scene_b", "b_act_1_armband_drop", "move_to_director")
        self.assertEqual((status, reason), ("rejected", "bad_args"))
        self.assertEqual(arm["loc_kind"], "attachment")
        status, reason, _ = self._move(ext, "scene_b", "b_act_1_armband_drop", "move_to_container",
                                       "scene_b", "b_act_1_gloves_dir")
        self.assertEqual((status, reason), ("rejected", "bad_args"))
        self.assertEqual(arm["loc_kind"], "attachment")

    def test_inventory_born_glove_accepted_for_player_container(self):
        peer, jobs, ext = self._ext()
        self.assertEqual(self._move(ext, "scene_b", "b_act_1_gloves_dir", "move_to_director")[0], "done")
        status, reason, payload = self._move(ext, "scene_a_clean", "ac_act_1_gloves_dir",
                                             "move_to_container", "scene_b", "b_act_1_gloves_dir")
        self.assertEqual((status, reason), ("done", ""))
        out = wire.unpack_payload(payload)
        self.assertEqual(out["str"]["transition_status"], "ok")

    def test_subtree_child_must_be_born_in_inventory(self):
        # MENOR 15: un hijo no nacido en inventario bajo el guante bloquea el
        # movimiento a un jugador, aunque la raiz si naciera en inventario.
        peer, jobs, ext = _make_clock_fake()
        rows = list(self._AC_ROWS) + [
            {"logical_id": "ac_act_1_gloves_child", "parent_id": "ac_act_1_gloves_dir",
             "cat": "prop", "class_name": "BandageDressing", "slot_name": "Cargo",
             "req_x_m": 4500.0, "req_z_m": 10200.0, "req_yaw_deg": 0.0,
             "health_mark_ratio": 0.0, "must_vanish_b": 1.0},
        ]
        self.assertEqual(ext.on_start_op(
            {"op_id": "op-apply-ac", "verb": "per_apply_scene", "qa_fault": ""},
            _apply_args("scene_a_clean", "scop-ac", 1, rows), {})[0], "done")
        status, reason, _ = self._move(ext, "scene_a_clean", "ac_act_1_gloves_dir",
                                       "move_to_director")
        self.assertEqual((status, reason), ("rejected", "bad_args"))


class TestRunnerRestartNewProcess(_GuardedTestCase):
    """P2c MEN 10: otro proceso conserva el arbol del director con el mismo pers_id."""

    def test_glove_reappears_deleted_and_absent_with_foreign_gear_intact(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            cfg = tmp / "dsbx_qa.json"
            peer1, jobs1, ext1 = _make_fake_with_config(cfg, "epoch-1")
            self.assertEqual(ext1.on_start_op(
                {"op_id": "op-apply", "verb": "per_apply_scene", "qa_fault": ""},
                _apply_args("scene_b", "scop-1", 1, _ACTOR_ROWS), {})[0], "done")
            self.assertEqual(ext1.on_start_op(
                {"op_id": "op-trans", "verb": "per_child_transition", "qa_fault": ""},
                _unpacked(strings={"scene_id": "scene_b", "logical_id": "b_act_1_gloves_dir",
                                   "action": "move_to_director", "expect_epoch": "epoch-1",
                                   "target_scene_id": "", "target_parent_id": "",
                                   "director_uid": ext1.director_uid}), {})[0], "done")
            rec = ext1._record_by("scene_b", "b_act_1_gloves_dir")
            glove_net = rec["ent"]["net_id"]
            glove_pers = rec["ent"]["pers_id"]
            glove_cls = rec["ent"]["class_name"]
            ext1._save_state()
            peer2, jobs2, ext2 = _make_fake_with_config(cfg, "epoch-2")
            self.assertIn(glove_net, ext2.world)
            self.assertEqual(ext2.world[glove_net]["pers_id"], glove_pers)
            self.assertEqual(ext2.world[glove_net]["owner_uid"], ext2.director_uid)
            status, _, payload = ext2.on_start_op(
                {"op_id": "op-purge", "verb": "per_purge_start", "qa_fault": ""},
                _purge_args([{"pers_id": glove_pers, "class_name": glove_cls}], ext2.director_uid,
                            epoch="epoch-2"), {},
            )
            self.assertEqual(status, "done")
            out = wire.unpack_payload(payload)
            self.assertGreaterEqual(out["num"]["pre_n"], 3.0)
            for _ in range(20):
                jobs2.tick_jobs(0.016, peer2.local_ms())
                ext2.on_tick(0.016)
                if ext2.purge_job_id == "":
                    break
            self.assertNotIn(glove_net, ext2.world)
            self.assertIn(fake_ext_persist.DIRECTOR_JEANS_NET, ext2.world)
            self.assertIn(fake_ext_persist.DIRECTOR_APPLE_NET, ext2.world)
            status, _, _ = ext2.on_start_op(
                {"op_id": "op-census-t5", "verb": "per_census_start", "qa_fault": ""},
                _unpacked(strings={"area_tag": "t5_post_restart_census:area_b",
                                   "director_uid": ext2.director_uid},
                          numbers={"center_x_m": 4680.0, "center_z_m": 10200.0,
                                   "radius_m": 60.0, "include_director_b": 1.0}), {},
            )
            self.assertEqual(status, "done")
            for _ in range(10):
                jobs2.tick_jobs(0.016, peer2.local_ms())
                ext2.on_tick(0.016)
                if jobs2.get_state("op-census-t5") != "running":
                    break
            rows = _job_rows(jobs2.jobs_by_id["op-census-t5"])
            self.assertFalse(any(r["net_id"] == glove_net for r in rows))
            self.assertTrue(any(r["net_id"] == fake_ext_persist.DIRECTOR_JEANS_NET for r in rows))


class TestT0AmbiguousAborts(_GuardedTestCase):
    def setUp(self):
        super().setUp()
        _FakePartContext.calls = []
        _FakePartContext.instances = []
        _FakePartContext.next_startup_reason = None

    def test_two_players_cuts_part_with_director_ambiguous(self):
        with self._inside_tmp() as td:
            tmp = Path(td)
            env, _mission, _storage, _backup = _make_env(tmp)
            base_dir = tmp / "evidence"
            two = _status_outcome(uid="", present=0, alive=0, inv=0, players_n=2)

            def fake_issue(ctx, peer, verb, payload=None, **kwargs):
                return two

            backup_return = (env, {}, tmp / "_storage_backup", None, "")
            with mock.patch.object(
                s_persist_run, "_live_cold_backup_before_open", return_value=backup_return
            ), mock.patch.object(
                s_persist_run, "_probe_sources_at_commit", return_value={}
            ), mock.patch.object(
                s_persist_run, "T0_DIRECTOR_TIMEOUT_S", 0.0
            ), mock.patch.object(
                f03_common, "PartContext", _FakePartContext
            ), mock.patch.object(
                f03_common, "issue_one", side_effect=fake_issue
            ):
                with self.assertRaises(RuntimeError) as raised:
                    s_persist_run.run_part(_live_args(), base_dir, [], "run")
            self.assertEqual(str(raised.exception), "director_ambiguous")
            scenario = _FakePartContext.instances[0].scenario
            evs = [row.get("ev") for row in scenario]
            self.assertIn("t0_director_ambiguous", evs)


class TestFakeCensusBoundary(_GuardedTestCase):
    """MENOR 9: la aritmetica del borde del censo del fake como 63bb265."""

    def test_boundary_compass_is_captured_with_base_arithmetic(self):
        peer, jobs, ext = _make_fake()
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-spawn-edge", "verb": "per_spawn_raw", "qa_fault": ""},
            _unpacked(strings={"tag": "edge", "mode": "", "class_name": "Compass"},
                      numbers={"x_m": 4683.0, "z_m": 10202.0, "yaw_deg": 0.0,
                               "health_mark_ratio": 0.0}), {},
        )
        self.assertEqual((status, reason), ("done", ""))
        status, reason, _ = ext.on_start_op(
            {"op_id": "op-census-edge", "verb": "per_census_start", "qa_fault": ""},
            _unpacked(strings={"area_tag": "edge:area_b", "director_uid": ""},
                      numbers={"center_x_m": 4680.0, "center_z_m": 10200.0,
                               "radius_m": 3.60659408389042, "include_director_b": 0.0,
                               "select_all_entityai_b": 1.0}), {},
        )
        self.assertEqual((status, reason), ("done", ""))
        for _ in range(10):
            jobs.tick_jobs(0.016, peer.local_ms())
            ext.on_tick(0.016)
            if jobs.get_state("op-census-edge") != "running":
                break
        job = jobs.jobs_by_id["op-census-edge"]
        rows = _job_rows(job)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["class_name"], "Compass")


class TestRunnerPurgeStart(_GuardedTestCase):
    """P2c: el runner ordena la purga, sondea, para al vencer y archiva paginas."""

    def _accredited(self):
        return [{"pers_id": "3:0:0:0", "class_name": "WorkingGloves_Yellow",
                 "logical_id": "b_act_1_gloves_dir", "net_id": "1:10"}]

    def test_done_reads_pages_with_target_inst(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        calls = []

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            calls.append((verb, kwargs.get("target_inst")))
            if verb == "per_purge_start":
                return _op_outcome("done", "", "op-start", {
                    "str": {"job": "j1", "state": "running"},
                    "num": {"pre_n": 1.0},
                })
            if verb == "job_read":
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "j1", "state": "done", "reason": ""},
                    "num": {"page_n": 0.0, "pages_n": 1.0, "rows_total_n": 1.0},
                    "rows": [{"phase": "result", "result": "deleted"}],
                })
            if verb == "job_free":
                return _op_outcome("done", "", "op-free", {"str": {"job": "j1", "freed": "1"}})
            raise AssertionError(verb)

        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=5.0, poll_s=1.0,
                monotonic=_FakeClock().monotonic, sleep=_FakeClock().sleep,
            )
        self.assertTrue(result["done"])
        self.assertEqual(result["state"], "done")
        self.assertEqual(result["rows"], [{"phase": "result", "result": "deleted"}])
        self.assertTrue(any(ev.get("ev") == "purge_pages" for ev in ctx.scenario))
        self.assertTrue(all(t == "epoch-new" for _v, t in calls if _v != "per_purge_start" or t == "epoch-new"))

    def test_wait_expired_sends_job_stop_and_does_not_open_t5(self):
        clock = _FakeClock()
        ctx = _FakeCtxT4(now_ms=5000.0)
        calls = []

        def fake_issue(ctx_arg, peer, verb, payload=None, **kwargs):
            calls.append((verb, kwargs.get("target_inst")))
            if verb == "per_purge_start":
                return _op_outcome("done", "", "op-start", {
                    "str": {"job": "j1", "state": "running"},
                    "num": {"pre_n": 1.0},
                })
            if verb == "job_read":
                state = "stopped" if any(v == "job_stop" for v, _t in calls) else "running"
                return _op_outcome("done", "", "op-read", {
                    "str": {"job": "j1", "state": state, "reason": ""},
                    "num": {"page_n": 0.0, "pages_n": 0.0, "rows_total_n": 0.0},
                    "rows": [],
                })
            if verb == "job_stop":
                return _op_outcome("done", "", "op-stop", {"str": {"job": "j1", "state": "stopped"}})
            if verb == "job_free":
                return _op_outcome("done", "", "op-free", {"str": {"job": "j1", "freed": "1"}})
            raise AssertionError(verb)

        with mock.patch.object(f03_common, "issue_one", side_effect=fake_issue):
            result = s_persist_run._purge_start_t4(
                ctx, self._accredited(), server_epoch_new="epoch-new",
                director_uid="dir-uid", timeout_s=2.0, poll_s=1.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(result["done"])
        self.assertEqual(result["state"], "stopped")
        self.assertTrue(any(v == "job_stop" for v, _t in calls))
        self.assertTrue(any(ev.get("ev") == "purge_not_done" for ev in ctx.scenario))

    def test_empty_accredited_sends_no_order(self):
        ctx = _FakeCtxT4(now_ms=5000.0)
        with mock.patch.object(f03_common, "issue_one", side_effect=AssertionError("no debe llamar")):
            result = s_persist_run._purge_start_t4(
                ctx, [], server_epoch_new="epoch-new", director_uid="dir-uid",
            )
        self.assertTrue(result["done"])
        self.assertEqual(result["state"], "none")


class TestComputeAccredited(_GuardedTestCase):
    """P2c: acreditadas por identidad y clase, con basal y unicidad."""

    def _events(self):
        rows = [{"owner_uid": "dir", "net_id": "1:10", "pers_id": "3:0:0:0",
                 "class_name": "WorkingGloves_Yellow"}]
        return [
            {"ev": "child_transition_t1", "action": "move_to_director",
             "transition_status": "ok", "post_owner_uid": "dir",
             "logical_id": "b_act_1_gloves_dir", "net_id": "1:10"},
            {"ev": "census_stage", "stage": "t1_post_transition_census", "rows": rows},
            {"ev": "census_stage", "stage": "t2_census_10min", "rows": rows},
            {"ev": "census_stage", "stage": "t3_pre_reset_census", "rows": rows},
            {"ev": "census_stage", "stage": "t3_post_reset_census", "rows": rows},
            {"ev": "census_stage", "stage": "t0_baseline_census",
             "rows": [{"owner_uid": "dir", "net_id": "1:2", "pers_id": "1:0:0:0",
                       "class_name": "Jeans_Blue"}]},
        ]

    def test_positive_accredits_the_transitioned_glove(self):
        fixture = s_persist_run._fixture()
        cfg = s_persist_run._part_config("run", fixture)
        got = s_persist_run._compute_accredited(self._events(), fixture, cfg, "dir")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["pers_id"], "3:0:0:0")
        self.assertEqual(got[0]["class_name"], "WorkingGloves_Yellow")

    def test_basal_or_shared_pers_id_is_not_accredited(self):
        fixture = s_persist_run._fixture()
        cfg = s_persist_run._part_config("run", fixture)
        events = self._events()
        events[-1]["rows"].append({"owner_uid": "dir", "net_id": "1:2",
                                   "pers_id": "3:0:0:0", "class_name": "Jeans_Blue"})
        self.assertEqual(s_persist_run._compute_accredited(events, fixture, cfg, "dir"), [])
        events = self._events()
        events[1]["rows"].append({"owner_uid": "dir", "net_id": "1:99",
                                  "pers_id": "3:0:0:0", "class_name": "WorkingGloves_Yellow"})
        self.assertEqual(s_persist_run._compute_accredited(events, fixture, cfg, "dir"), [])


def _op_outcome(status, reason, op_id, payload):
    return SimpleNamespace(status=status, reason=reason, op_id=op_id, payload=payload)


def _purge_args(rows, director_uid, epoch="epoch-1"):
    return _unpacked(
        strings={"director_uid": director_uid, "expect_epoch": epoch},
        ncol=[], scol=["pers_id", "class_name"], rows=rows,
    )


def _job_rows(job):
    rows = []
    nsc = len(job["scol"])
    nnc = len(job["ncol"])
    for i in range(job["rows_total"]):
        s = job["scell"][i * nsc:(i + 1) * nsc]
        n = job["ncell"][i * nnc:(i + 1) * nnc]
        row = {job["scol"][j]: s[j] for j in range(nsc)}
        row.update({job["ncol"][j]: n[j] for j in range(nnc)})
        rows.append(row)
    return rows
if __name__ == "__main__":
    unittest.main()
