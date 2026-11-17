import tempfile
import os
import json
import subprocess
import sys
from unittest import TestCase
import secrets


def run_peer_config(args):
    cmd = [sys.executable, 'app/tools/peer_config.py'] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


class TestPeerConfig(TestCase):
    def test_valid_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': secrets.token_urlsafe(32),
                'bridge_port': 9001
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 0)

            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertTrue(os.path.exists(output_file))

            with open(output_file, 'r') as f:
                output_data = json.load(f)
            self.assertEqual(output_data['url'], 'http://127.0.0.1:9001/')
            self.assertEqual(output_data['key'], config_data['peer_key'])

            self.assertFalse(os.path.exists(output_file + '.tmp'))

    def test_create_profile_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abcdefghijklmnopqrstuvwxyz012345',
                'bridge_port': 8766
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.exists(profile_path))

    def test_default_bridge_port(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abcdefghijklmnopqrstuvwxyz012345',
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 0)

            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            with open(output_file, 'r') as f:
                output_data = json.load(f)
            self.assertEqual(output_data['url'], 'http://127.0.0.1:8766/')

    def test_no_peer_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'bridge_port': 8766
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_empty_peer_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': '',
                'bridge_port': 8766
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_peer_key_with_plus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abcdefghijklmnopqrstuvwxyz+012345',
                'bridge_port': 8766
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_peer_key_with_ampersand(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abcdefghijklmnopqrstuvwxyz&012345',
                'bridge_port': 8766
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_peer_key_too_short(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abc123',
                'bridge_port': 8766
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_bridge_port_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abcdefghijklmnopqrstuvwxyz012345',
                'bridge_port': 0
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_bridge_port_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abcdefghijklmnopqrstuvwxyz012345',
                'bridge_port': 70000
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_missing_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_path = os.path.join(tmpdir, 'profile')

            exit_code, stdout, stderr = run_peer_config(['--config', 'nonexistent.json', '--profile', profile_path])
            self.assertEqual(exit_code, 2)

    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            with open(config_path, 'w') as f:
                f.write('invalid json')

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 2)
            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            self.assertFalse(os.path.exists(output_file))

    def test_no_peer_key_in_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'backend.json')
            profile_path = os.path.join(tmpdir, 'profile')
            config_data = {
                'peer_key': 'abcdefghijklmnopqrstuvwxyz012345',
                'bridge_port': 8766
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f)

            exit_code, stdout, stderr = run_peer_config(['--config', config_path, '--profile', profile_path])
            self.assertEqual(exit_code, 0)

            output_file = os.path.join(profile_path, 'dsbx_peer.json')
            with open(output_file, 'r') as f:
                output_data = json.load(f)

            self.assertEqual(output_data['key'], 'abcdefghijklmnopqrstuvwxyz012345')

            self.assertNotIn('abcdefghijklmnopqrstuvwxyz012345', stdout)
            self.assertNotIn('abcdefghijklmnopqrstuvwxyz012345', stderr)


class PeerConfigCompleta(TestCase):
    """Lo que anade el orquestador (brief de F1b-peers §5.4): main importable, bytes exactos,
    sin temporales, los casos que se colaban y la clave fuera de stdout y stderr siempre."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="dsbx-peercfg-")
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.profile = os.path.join(self.tmp, "perfil", "sub")
        self.config = os.path.join(self.tmp, "backend.json")

    def _write(self, obj, raw=None):
        with open(self.config, "w", encoding="utf-8", newline="\n") as f:
            f.write(raw if raw is not None else json.dumps(obj))

    def test_main_importado_escribe_bytes_exactos_sin_bom_ni_temporales(self):
        from app.tools.peer_config import main
        key = secrets.token_urlsafe(32)
        self.assertEqual(len(key), 43)
        self._write({"peer_key": key, "bridge_port": 9001})
        self.assertEqual(main(["--config", self.config, "--profile", self.profile]), 0)
        self.assertEqual(os.listdir(self.profile), ["dsbx_peer.json"])
        with open(os.path.join(self.profile, "dsbx_peer.json"), "rb") as f:
            raw = f.read()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)
        self.assertEqual(json.loads(raw.decode("utf-8")), {"url": "http://127.0.0.1:9001/", "key": key})

    def test_casos_que_se_colaban_salen_con_2_sin_fichero(self):
        from app.tools.peer_config import main
        good = secrets.token_urlsafe(32)
        casos = [
            ("clave con salto final", {"peer_key": good + "\n"}, None),
            ("puerto booleano", {"peer_key": good, "bridge_port": True}, None),
            ("puerto en texto", {"peer_key": good, "bridge_port": "9001"}, None),
            ("clave no texto", {"peer_key": 12345678901234567}, None),
            ("clave de 129", {"peer_key": "a" * 129}, None),
            ("json que no es objeto", None, "[1, 2]"),
        ]
        for nombre, obj, raw in casos:
            with self.subTest(nombre):
                self._write(obj, raw)
                self.assertEqual(main(["--config", self.config, "--profile", self.profile]), 2)
                self.assertFalse(os.path.exists(os.path.join(self.profile, "dsbx_peer.json")))

    def test_la_clave_no_sale_por_stdout_ni_stderr_en_ningun_caso(self):
        good = secrets.token_urlsafe(32)
        marca = "MARCA" + secrets.token_hex(8)
        casos = [
            ({"peer_key": good, "bridge_port": 9001}, good, 0),
            ({"peer_key": marca + "+x", "bridge_port": 9001}, marca, 2),
            ({"peer_key": marca + "&x", "bridge_port": 9001}, marca, 2),
            ({"peer_key": marca + " x", "bridge_port": 9001}, marca, 2),
            ({"peer_key": good, "bridge_port": 0}, good, 2),
            ({"peer_key": good, "bridge_port": 70000}, good, 2),
        ]
        for obj, secreto, rc in casos:
            with self.subTest(rc=rc, port=obj.get("bridge_port")):
                self._write(obj)
                code, out, err = run_peer_config(["--config", self.config, "--profile", self.profile])
                self.assertEqual(code, rc)
                self.assertNotIn(secreto, out)
                self.assertNotIn(secreto, err)
