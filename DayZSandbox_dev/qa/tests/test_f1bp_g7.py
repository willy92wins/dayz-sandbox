"""Estructura del escenario G7 de F1b-peers con el mod falso (L2b3b).

Corre `--fake --scenarios G7`: el veredicto no importa, solo que G7 llegue a su
`end` `ok` con todos los casos, cada uno con `rule_id`, precedido de su
`rules_active` y seguido de una `recovery`. Ninguna clave en ningun fichero.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_PATH = os.path.abspath(os.path.join(HERE, "..", "live", "f1bp_live.py"))

CODES = (400, 401, 409, 413, 500)
EXPECTED = (
    ["status%d_P" % c for c in CODES]
    + ["status%d_R" % c for c in CODES]
    + [
        "timeout_P",
        "r_held",
        "invalid_no_ok_P",
        "invalid_ok_false_P",
        "invalid_now_decimal_P",
        "invalid_now_text_P",
        "measure_no_args_P",
        "invalid_all_P",
        "measure_ok1_P",
        "measure_args_empty_P",
        "late_cb",
    ]
)


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


class F1bPeersG7(unittest.TestCase):
    def test_g7_estructura_fake(self):
        live = _load_module("f1bp_live_g7", LIVE_PATH)
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-g7-")
        ev = os.path.join(tmp, "evidence")
        try:
            args = argparse.Namespace(
                build="diag",
                evidence=ev,
                server_profile=os.path.join(tmp, "server"),
                client_profile=os.path.join(tmp, "client"),
                pids_file=os.path.join(tmp, "pids.json"),
                scenarios="G7",
                pbo=None,
                fake=True,
            )
            rc = live.run(args)
            self.assertEqual(rc, 0, "el orquestador salio con %r" % rc)

            path = os.path.join(ev, "samples", "G7.jsonl")
            self.assertTrue(os.path.isfile(path), "falta samples/G7.jsonl")
            events = _load_jsonl(path)
            ends = [e for e in events if e.get("ev") == "end"]
            self.assertEqual(len(ends), 1)
            self.assertEqual(ends[0].get("status"), "ok", ends[0])

            cases = [(i, e) for i, e in enumerate(events) if e.get("ev") == "case"]
            self.assertEqual([e["name"] for _i, e in cases], list(EXPECTED))
            for pos, (idx, case) in enumerate(cases):
                name = case["name"]
                self.assertTrue(case.get("rule_id"), "%s sin rule_id" % name)
                self.assertTrue(
                    events[idx - 1].get("ev") == "rules_active"
                    or any(e.get("ev") == "rules_active" for e in events[max(0, idx - 2) : idx]),
                    "%s sin rules_active justo antes" % name,
                )
                limit = cases[pos + 1][0] if pos + 1 < len(cases) else len(events)
                recoveries = [
                    e for e in events[idx:limit] if e.get("ev") == "recovery"
                ]
                self.assertEqual(len(recoveries), 1, "%s sin recovery" % name)

            # R10: cada caso acaba con `rules` de rule_ids [] y su rules_active, antes de la recuperacion.
            for pos, (idx, case) in enumerate(cases):
                limit = cases[pos + 1][0] if pos + 1 < len(cases) else len(events)
                window = events[idx:limit]
                rec = [i for i, e in enumerate(window) if e.get("ev") == "recovery"][0]
                empties = [
                    i for i, e in enumerate(window[:rec])
                    if e.get("ev") == "rules" and e.get("rule_ids") == []
                ]
                self.assertTrue(empties, "%s sin rules vacio antes de su recuperacion" % case["name"])
                version = window[empties[0]].get("version")
                self.assertTrue(
                    any(
                        e.get("ev") == "rules_active" and e.get("version") == version
                        for e in window[empties[0] + 1:rec]
                    ),
                    "%s: el rules vacio sin rules_active antes de la recuperacion" % case["name"],
                )

            # R5/R6: todo apply lleva sesion y sus dos instantes; op_state lleva sesion y t_ms
            sessions = {
                e.get("session") for e in events if e.get("ev") in ("apply", "op_state", "recovery")
            }
            self.assertEqual(len(sessions), 1, sessions)
            self.assertTrue(next(iter(sessions)))
            for e in events:
                if e.get("ev") == "apply":
                    self.assertLessEqual(e["t_ms"], e["t_end_ms"])
                if e.get("ev") == "op_state":
                    self.assertIsInstance(e.get("t_ms"), float)

            secrets_used = tuple(getattr(live, "LAST_SECRETS", ()))
            self.assertEqual(len(secrets_used), 3)
            for root, _dirs, files in os.walk(ev):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    with open(fpath, "rb") as fh:
                        data = fh.read()
                    for secret in secrets_used:
                        self.assertNotIn(secret.encode("utf-8"), data, "clave en %s" % fpath)
            hashes = {hashlib.sha256(s.encode("utf-8")).hexdigest() for s in secrets_used}
            self.assertEqual(len(hashes), 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(os.path.exists(tmp))


if __name__ == "__main__":
    unittest.main()
