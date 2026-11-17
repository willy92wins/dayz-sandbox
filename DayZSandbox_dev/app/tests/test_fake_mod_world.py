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


class T02MarcaF2(unittest.TestCase):
    """T-02 (Sol sobre T1; DP-5, §3.5): el mod falso elige F2 por `args.f2 == 1`, no por tener mundo."""

    def _stub(self):
        calls = {"world": [], "finish": [], "effects": []}
        fake = types.SimpleNamespace(
            world=object(),
            world_read=lambda: {"epoch": "e" * 32, "generation": None,
                                "registry_n": 0, "registry_sha256": "0" * 64},
            _record_effect=lambda order, kind: calls["effects"].append(kind),
            _set_generation=lambda gen: None,
        )
        stub = types.SimpleNamespace(
            fake=fake,
            state_read_mode="ok",
            work_before_ms=0,
            work_between_ms=0,
            annotate_rev_delta=0,
            _stop=types.SimpleNamespace(is_set=lambda: False),
            _sleep=lambda s: None,
            _check_before_effect=lambda _entry: None,
            _execute_world=lambda entry, verb: calls["world"].append(verb),
            _finish=lambda entry, status, reason, read: calls["finish"].append((status, reason, read)),
        )
        return stub, calls

    def _run(self, verb, args):
        stub, calls = self._stub()
        order = {"op_id": "op-1", "session": "a" * 16, "epoch": "e" * 32, "verb": verb, "args": args}
        entry = types.SimpleNamespace(order=order, steps_done=0)
        _Peer._execute(stub, entry)
        return calls

    def test_con_f2_igual_a_1_va_por_el_mundo(self):
        for verb in ("state.read", "scene.apply", "scene.reset", "scene.observe"):
            calls = self._run(verb, {"f2": 1, "doc_id": "d-7c19e2a5"})
            self.assertEqual(calls["world"], [verb], verb)
            self.assertEqual(calls["finish"], [], verb)

    def test_sin_marca_o_con_marca_mal_tipada_va_por_f1(self):
        malas = [{}, {"f2": 0}, {"f2": True}, {"f2": 1.0}, {"f2": "1"}]
        for args0 in malas:
            args = dict(args0, doc_id="d-7c19e2a5", rev=1, hash="h" * 64)
            # state.read F1: lectura sin bloque `scene`
            calls = self._run("state.read", args)
            self.assertEqual(calls["world"], [], args0)
            self.assertEqual(len(calls["finish"]), 1)
            status, _reason, read = calls["finish"][0]
            self.assertEqual(status, "done")
            self.assertNotIn("scene", read)
            # scene.reset y scene.observe sin marca: el mod F1 no los conoce
            for verb in ("scene.reset", "scene.observe"):
                calls = self._run(verb, args)
                self.assertEqual(calls["world"], [], (verb, args0))
                self.assertEqual(calls["finish"], [("rejected", "unknown_verb", {})], (verb, args0))
            # scene.apply sin marca: el apply F1 de dos pasos, sin crear entidades del mundo
            calls = self._run("scene.apply", args)
            self.assertEqual(calls["world"], [], args0)
            self.assertEqual(calls["effects"], ["retirar", "anotar"], args0)


if __name__ == "__main__":
    unittest.main()
