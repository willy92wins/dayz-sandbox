"""Cada import de qa es biblioteca estandar o un modulo de qa (brief F0.1 §10.1 punto 4)."""

import ast
import sys
import unittest
from pathlib import Path

QA = Path(__file__).resolve().parents[1]
REPO = QA.parent

# Excepciones cerradas al paquete app del repo; el resto de qa sigue siendo solo stdlib.
# - F1b-peers (brief de partida de F1b-peers, §3): el orquestador de qa/live arranca en proceso el backend real, el
#   mod falso y peer_config, y su ensayo seco tambien; esos dos ficheros pueden importar cualquier modulo de app. El
#   evaluador (live/f1bp_eval.py) sigue siendo solo stdlib.
# - F2P (23-nov, decision de Guillermo: «Sí, en el re-congelado»), cerrada por modulo. El oraculo solo importa el
#   validador del backend: es S-08 de qa/f2p_eval.py, la ultima condicion de `_valid_read`, cuyo unico uso es un
#   requisito positivo de `_reconciliation_ok`, asi que solo puede endurecer el veredicto y nunca da un PASA. Sus
#   pruebas offline levantan el backend en proceso. Desde el primer congelado de F2P (98c7a78) esta prueba fallaba
#   por esos imports.
# - Un paquete de app no se admite como tal: en `from app.backend import X`, X cuenta como el submodulo
#   `app.backend.X` (M1 de la ronda 1 de Sol sobre el descongelado; antes, `app.backend` dejaba entrar cualquier
#   submodulo). Por eso las pruebas de F2P listan `app.backend.scene_plan`, que ya importaban en 98c7a78.
# Un modulo de app que no este en el conjunto de su fichero hace fallar la prueba.
APP_IMPORTERS = {
    "live/f1bp_live.py": None,
    "tests/test_f1bp_dryrun.py": None,
    "f2p_eval.py": frozenset({"app.backend.scene_live"}),
    "tests/test_f2p_offline.py": frozenset({"app.backend.bridge", "app.backend.scene_live",
                                            "app.backend.scene_plan"}),
}


def _local(name):
    top = name.split(".", 1)[0]
    return (QA / f"{top}.py").is_file() or (QA / top).is_dir()


def _app_package(module):
    """`module`, de app, es un paquete del repo (tiene `__init__.py`)."""
    return REPO.joinpath(*module.split(".")).joinpath("__init__.py").is_file()


def _imported_modules(node):
    """Los modulos que trae un import absoluto. En `from M import a, b` con M un paquete de app, cada nombre cuenta
    como su submodulo (`M.a`, `M.b`); con `*`, `M.*`, que no esta en ningun conjunto cerrado."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not node.module:
        return []
    if node.module.split(".", 1)[0] == "app" and _app_package(node.module):
        return [node.module + "." + alias.name for alias in node.names]
    return [node.module]


def _app_import_allowed(rel, module):
    """`rel`, ruta del fichero relativa a qa con `/`; `module`, el modulo de app que importa."""
    if rel not in APP_IMPORTERS:
        return False
    allowed = APP_IMPORTERS[rel]
    return allowed is None or module in allowed


class StdlibOnlyTests(unittest.TestCase):
    def test_imports_are_stdlib_or_qa(self):
        offenders = []
        for path in sorted(QA.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Import, ast.ImportFrom)):
                    continue
                if isinstance(node, ast.ImportFrom) and node.level:
                    continue
                for module in _imported_modules(node):
                    top = module.split(".", 1)[0]
                    if top in sys.stdlib_module_names or _local(module):
                        continue
                    if top == "app" and _app_import_allowed(path.relative_to(QA).as_posix(), module):
                        continue
                    offenders.append(f"{path.relative_to(QA)}:{node.lineno} {module}")
        self.assertEqual(offenders, [])

    def test_app_exception_is_closed_by_module(self):
        # F2P: solo los modulos de su conjunto; cualquier otro de app falla.
        self.assertTrue(_app_import_allowed("f2p_eval.py", "app.backend.scene_live"))
        self.assertFalse(_app_import_allowed("f2p_eval.py", "app.backend"))
        self.assertFalse(_app_import_allowed("f2p_eval.py", "app.backend.bridge"))
        self.assertTrue(_app_import_allowed("tests/test_f2p_offline.py", "app.backend.bridge"))
        self.assertTrue(_app_import_allowed("tests/test_f2p_offline.py", "app.backend.scene_plan"))
        self.assertFalse(_app_import_allowed("tests/test_f2p_offline.py", "app.backend"))
        self.assertFalse(_app_import_allowed("tests/test_f2p_offline.py", "app.backend.server"))
        # F1b-peers: el orquestador y su ensayo seco, cualquier modulo; su evaluador, ninguno.
        self.assertTrue(_app_import_allowed("live/f1bp_live.py", "app.backend.server"))
        self.assertFalse(_app_import_allowed("live/f1bp_eval.py", "app.backend"))
        # Un fichero fuera de la lista nunca.
        self.assertFalse(_app_import_allowed("f2p_run.py", "app.backend.scene_live"))

    def test_from_app_package_counts_each_submodule(self):
        # M1: `from app.backend import server` es `app.backend.server`, fuera del conjunto de las pruebas de F2P.
        def mods(src):
            return _imported_modules(ast.parse(src).body[0])
        self.assertEqual(mods("from app.backend import server"), ["app.backend.server"])
        self.assertEqual(mods("from app.backend import scene_plan, server"),
                         ["app.backend.scene_plan", "app.backend.server"])
        self.assertEqual(mods("from app.backend import *"), ["app.backend.*"])
        self.assertEqual(mods("from app import backend"), ["app.backend"])
        self.assertEqual(mods("from app.backend.bridge import valid_world_read"), ["app.backend.bridge"])
        self.assertEqual(mods("from unittest import mock"), ["unittest"])
        rel = "tests/test_f2p_offline.py"
        self.assertTrue(all(_app_import_allowed(rel, m) for m in mods("from app.backend import scene_plan")))
        self.assertFalse(any(_app_import_allowed(rel, m) for m in mods("from app.backend import server")))
        self.assertFalse(any(_app_import_allowed(rel, m) for m in mods("from app.backend import *")))
        self.assertFalse(any(_app_import_allowed(rel, m) for m in mods("from app import backend")))


if __name__ == "__main__":
    unittest.main()
