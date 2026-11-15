"""M20: el motor corta cada cadena de un JSON leido a 1023 caracteres.

Sin red: se prueba directamente el recorte que `_execute_world` aplica a los
`args` de una orden de mundo antes de entregarla al mundo falso.
"""
from __future__ import annotations

import copy
import types
import unittest

from app.tests.fake_mod import MAX_STRING_CHARS, _Peer, _truncate_strings


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

    def test_execute_world_despacha_scene_apply_con_args_truncados_a_1023(self):
        received: list[dict] = []
        finished: list[tuple] = []

        def spy_apply(order, check=None, tick=None):
            received.append(copy.deepcopy(order.get("args")))
            return "done", None, {}

        world_spy = types.SimpleNamespace(apply=spy_apply)
        stub = types.SimpleNamespace(
            fake=types.SimpleNamespace(world=world_spy),
            _check_before_effect=lambda _entry: None,
            _tick=lambda: None,
            _finish=lambda entry, status, reason, read: finished.append(
                (entry, status, reason, read)
            ),
        )
        entry = types.SimpleNamespace(
            order={
                "op_id": "op-01",
                "session": "a" * 16,
                "epoch": "e" * 32,
                "verb": "scene.apply",
                "args": {
                    "doc_id": "d-7c19e2a5",
                    "texto": "x" * 1030,
                    "classes": ["c" * 1030],
                },
            }
        )

        _Peer._execute_world(stub, entry, "scene.apply")

        self.assertEqual(len(received), 1)
        args_recibidos = received[0]
        self.assertEqual(len(args_recibidos["texto"]), 1023)
        self.assertEqual(args_recibidos["texto"], "x" * 1023)
        self.assertEqual(len(args_recibidos["classes"][0]), 1023)
        self.assertEqual(args_recibidos["classes"][0], "c" * 1023)
        self.assertEqual(args_recibidos["doc_id"], "d-7c19e2a5")
        self.assertEqual(len(entry.order["args"]["texto"]), 1030)
        self.assertEqual(finished, [(entry, "done", None, {})])


if __name__ == "__main__":
    unittest.main()
