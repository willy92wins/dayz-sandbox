"""Cada import de qa es biblioteca estandar o un modulo de qa (brief F0.1 §10.1 punto 4)."""

import ast
import sys
import unittest
from pathlib import Path

QA = Path(__file__).resolve().parents[1]


def _local(name):
    top = name.split(".", 1)[0]
    return (QA / f"{top}.py").is_file() or (QA / top).is_dir()


class StdlibOnlyTests(unittest.TestCase):
    def test_imports_are_stdlib_or_qa(self):
        offenders = []
        for path in sorted(QA.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                    level = 0
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        continue
                    modules = [node.module] if node.module else []
                    level = node.level
                else:
                    continue
                for module in modules:
                    top = module.split(".", 1)[0]
                    if top in sys.stdlib_module_names or _local(module):
                        continue
                    offenders.append(f"{path.relative_to(QA)}:{node.lineno} {module}")
                del level
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
