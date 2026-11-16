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

    def test_truncated_census_ends_failed_not_done(self):
        peer, jobs, ext = TestFakeCleanup()._applied_ext()
        peer.lease_calls = 0
        peer.lease_budget = 2  # entrada + primera fila; caduca en la captura
        status, _, payload = ext.on_start_op(
            {"op_id": "op-census", "verb": "per_census_start", "qa_fault": ""},
            _unpacked(
                strings={"area_tag": "t1_pre_transition_census:area_a"},
                numbers={"center_x_m": 4500.0, "center_z_m": 10200.0,
                         "radius_m": 60.0, "include_director_b": 1.0},
            ), {},
        )
        self.assertEqual(status, "done")
        peer.now += 5000.0
        for _ in range(6):
            ext.on_tick(0.016)
        job = jobs.jobs_by_id["op-census"]
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["reason"], "lease_expired")


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


def _status_outcome(uid="", present=0, alive=0, inv=0, epoch="epoch-1"):
    return SimpleNamespace(
        status="done",
        reason="",
        op_id="op-status",
        payload={
            "str": {"server_epoch": epoch, "director_uid": uid},
            "num": {
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
            st, polls, waited_ms, ready = s_persist_run._wait_for_director_t0(
                mock.Mock(), timeout_s=300.0, poll_s=2.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
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
            st, polls, waited_ms, ready = s_persist_run._wait_for_director_t0(
                mock.Mock(), timeout_s=5.0, poll_s=2.0,
                monotonic=clock.monotonic, sleep=clock.sleep,
            )
        self.assertFalse(ready)
        self.assertIs(st, absent)
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

        with mock.patch.object(
            f03_common, "await_operator", return_value={"ok": True}
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


if __name__ == "__main__":
    unittest.main()
