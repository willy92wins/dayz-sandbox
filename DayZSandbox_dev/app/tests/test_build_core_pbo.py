"""Pruebas de qa/build_core_pbo.py que no necesitan AddonBuilder ni git (brief de F1b-peers §5.3)."""
import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "qa" / "build_core_pbo.py"
_spec = importlib.util.spec_from_file_location("build_core_pbo", _PATH)
bcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bcp)


def make_pbo(prefix, files, method=0, checksum=True):
    """Bytes de un PBO sin comprimir: producto, cabeceras, terminador, datos y suma."""
    out = b"\x00" + struct.pack("<5I", bcp.PRODUCT, 0, 0, 0, 0)
    out += b"prefix\x00" + prefix.encode("utf-8") + b"\x00" + b"\x00"
    for name, data in files:
        out += name.encode("utf-8") + b"\x00" + struct.pack("<5I", method, len(data), 0, 0, len(data))
    out += b"\x00" + struct.pack("<5I", 0, 0, 0, 0, 0)
    for _name, data in files:
        out += data
    if checksum:
        out += b"\x00" + hashlib.sha1(out).digest()
    return out


class LeerPbo(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="dsbx-bcp-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _write(self, raw):
        p = self.tmp / "x.pbo"
        p.write_bytes(raw)
        return p

    def test_prefijo_y_ficheros_exactos_con_nombres_en_barra(self):
        cfg = b'class CfgPatches {};\n'
        a_c = "class A {}; // ñ\n".encode("utf-8")
        p = self._write(make_pbo("DayZSandbox", [("config.cpp", cfg), ("scripts\\3_Game\\A.c", a_c)]))
        prefix, files = bcp.read_pbo(p)
        self.assertEqual(prefix, "DayZSandbox")
        self.assertEqual(files, {"config.cpp": cfg, "scripts/3_Game/A.c": a_c})
        self.assertTrue(bcp.pbo_checksum_ok(p))

    def test_suma_mala_se_ve(self):
        raw = bytearray(make_pbo("DayZSandbox", [("config.cpp", b"x")]))
        raw[-1] ^= 0xFF
        self.assertFalse(bcp.pbo_checksum_ok(self._write(bytes(raw))))

    def test_pbo_truncado_o_comprimido_o_sin_terminar_es_error(self):
        full = make_pbo("DayZSandbox", [("config.cpp", b"0123456789")], checksum=False)
        casos = {
            "datos cortados": full[:-4],
            "comprimido": make_pbo("DayZSandbox", [("config.cpp", b"x")], method=0x43707273),
            "cabecera sin terminar": b"config.cpp",
            "cabecera corta": b"config.cpp\x00" + b"\x00" * 7,
        }
        for nombre, raw in casos.items():
            with self.subTest(nombre):
                with self.assertRaises(ValueError):
                    bcp.read_pbo(self._write(raw))


class Comparar(unittest.TestCase):
    HEAD = {"$PBOPREFIX$": b"DayZSandbox\n", "include.lst": b"*.c\n", "config.cpp": b"cfg",
            "scripts/3_Game/A.c": b"a", "scripts/3_Game/B.c": b"b"}

    def test_iguales_sin_diferencias(self):
        self.assertEqual(bcp.compare(self.HEAD, dict(self.HEAD)), [])

    def test_falta_sobra_y_distinto(self):
        pbo = {"$PBOPREFIX$": b"DayZSandbox\n", "include.lst": b"*.c\n", "config.cpp": b"cfg",
               "scripts/3_Game/A.c": b"a2", "scripts/3_Game/C.c": b"c"}
        got = bcp.compare(self.HEAD, pbo)
        self.assertEqual([(d["path"], d["problem"]) for d in got],
                         [("scripts/3_Game/B.c", "missing"), ("scripts/3_Game/C.c", "extra"),
                          ("scripts/3_Game/A.c", "different")])
        diff = got[2]
        self.assertEqual(diff["head_sha256"], hashlib.sha256(b"a").hexdigest())
        self.assertEqual(diff["pbo_sha256"], hashlib.sha256(b"a2").hexdigest())

    def test_las_directivas_tambien_van_en_el_pbo(self):
        pbo = {k: v for k, v in self.HEAD.items() if k != "include.lst"}
        self.assertEqual([(d["path"], d["problem"]) for d in bcp.compare(self.HEAD, pbo)],
                         [("include.lst", "missing")])


class Precondiciones(unittest.TestCase):
    def test_sin_addonbuilder_sale_con_2_sin_crear_nada(self):
        tmp = Path(tempfile.mkdtemp(prefix="dsbx-bcp-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        out = tmp / "out"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = bcp.main(["--out", str(out), "--addon-builder", str(tmp / "no-existe.exe")])
        self.assertEqual(rc, 2)
        self.assertIn("sin AddonBuilder", err.getvalue())
        self.assertFalse(out.exists())
        self.assertEqual(os.listdir(tmp), [])


if __name__ == "__main__":
    unittest.main()
