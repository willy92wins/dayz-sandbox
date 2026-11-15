"""M20: el motor corta cada cadena de un JSON leido a 1023 caracteres.

Sin red: se prueba directamente el recorte que `_execute_world` aplica a los
`args` de una orden de mundo antes de entregarla al mundo falso.
"""
from __future__ import annotations

import copy
import unittest

from app.tests.fake_mod import MAX_STRING_CHARS, _truncate_strings


class M20TruncadoDeArgs(unittest.TestCase):
    def test_texto_de_1030_en_args_llega_cortado_a_1023(self):
        texto = "x" * 1030
        args = {
            "doc_id": "d-7c19e2a5",
            "texto": texto,
            "anidado": {"lista": ["y" * 1030]},
        }
        original = copy.deepcopy(args)
        out = _truncate_strings(args)
        self.assertEqual(MAX_STRING_CHARS, 1023)
        self.assertEqual(len(out["texto"]), 1023)
        self.assertEqual(out["texto"], "x" * 1023)
        self.assertEqual(len(out["anidado"]["lista"][0]), 1023)
        self.assertEqual(out["anidado"]["lista"][0], "y" * 1023)
        self.assertEqual(out["doc_id"], "d-7c19e2a5")
        self.assertEqual(args, original)

    def test_texto_de_1023_no_se_corta(self):
        texto = "z" * 1023
        out = _truncate_strings({"texto": texto})
        self.assertEqual(out["texto"], texto)
        self.assertEqual(len(out["texto"]), 1023)


if __name__ == "__main__":
    unittest.main()
