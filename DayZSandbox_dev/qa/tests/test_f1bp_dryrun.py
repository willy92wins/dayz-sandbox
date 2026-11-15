"""Ensayo en seco del orquestador F1b-peers con el mod falso (brief §7).

Corre G2, G3 y G9 con --fake, sin DayZ, contra el backend real a traves del
proxy de fallos. Comprueba la estructura de EVIDENCIA.md y, si existe, que el
evaluador real de PASA en las tres filas. Ninguna clave puede aparecer en la
carpeta de evidencia.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_PATH = os.path.abspath(os.path.join(HERE, "..", "live", "f1bp_live.py"))
EVAL_PATH = os.path.abspath(os.path.join(HERE, "..", "live", "f1bp_eval.py"))


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


class F1bPeersDryRun(unittest.TestCase):
    def test_dryrun_g2_g3_g9(self):
        live = _load_module("f1bp_live_dryrun", LIVE_PATH)
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-dry-")
        ev = os.path.join(tmp, "evidence")
        try:
            args = argparse.Namespace(
                build="diag",
                evidence=ev,
                server_profile=os.path.join(tmp, "server"),
                client_profile=os.path.join(tmp, "client"),
                pids_file=os.path.join(tmp, "pids.json"),
                scenarios="G2,G3,G9",
                pbo=None,
                fake=True,
            )
            rc = live.run(args)
            self.assertEqual(rc, 0, "el orquestador salio con %r" % rc)

            # 1) manifest
            manifest_path = os.path.join(ev, "manifest.json")
            self.assertTrue(os.path.isfile(manifest_path), "falta manifest.json")
            manifest = _load_json(manifest_path)
            for field in (
                "build",
                "fake",
                "git_head",
                "git_dirty",
                "pbo_sha256",
                "dayz_version",
                "ports",
                "key_sha256",
                "lease_ms",
                "hold_ms",
                "scenarios",
                "t0_ms",
            ):
                self.assertIn(field, manifest, "manifest sin %s" % field)
            self.assertIs(manifest["fake"], True)
            self.assertEqual(manifest["build"], "fake")
            self.assertEqual(manifest["scenarios"], ["G2", "G3", "G9"])
            self.assertEqual(manifest["lease_ms"], 3000)
            self.assertEqual(manifest["hold_ms"], 2000)
            self.assertIsInstance(manifest["ports"], dict)
            for port in ("web", "bridge", "proxy"):
                self.assertIn(port, manifest["ports"])
                self.assertIsInstance(manifest["ports"][port], int)
                self.assertGreater(manifest["ports"][port], 0)

            # 2) muestras con start y end ok
            samples = {}
            for name in ("G2", "G3", "G9"):
                path = os.path.join(ev, "samples", name + ".jsonl")
                self.assertTrue(os.path.isfile(path), "falta samples/%s.jsonl" % name)
                samples[name] = _load_jsonl(path)
                starts = [e for e in samples[name] if e.get("ev") == "start"]
                ends = [e for e in samples[name] if e.get("ev") == "end"]
                self.assertTrue(starts, "%s sin start" % name)
                self.assertTrue(ends, "%s sin end" % name)
                self.assertEqual(starts[0].get("scenario"), name)
                self.assertEqual(ends[-1].get("status"), "ok", "%s end no ok" % name)

            # 3) G3: rules_active antes del caso c, observado en a y b,
            #    fallido/lectura_no_cumple en c y recuperacion.
            g3 = samples["G3"]
            case_index = {}
            for idx, event in enumerate(g3):
                if event.get("ev") == "case":
                    case_index[event.get("name")] = idx
            for name in ("a", "b", "c"):
                self.assertIn(name, case_index, "G3 sin caso %s" % name)
            rules_active = [i for i, e in enumerate(g3) if e.get("ev") == "rules_active"]
            self.assertTrue(rules_active, "G3 sin rules_active")
            self.assertLess(min(rules_active), case_index["c"],
                            "rules_active no precede al caso c")

            for name in ("a", "b"):
                op_id = g3[case_index[name]].get("op_id")
                self.assertTrue(op_id, "G3 caso %s sin op_id" % name)
                observed = [
                    e for e in g3
                    if e.get("ev") == "op_state" and e.get("op_id") == op_id
                    and e.get("state") == "observado"
                ]
                self.assertTrue(observed, "G3 caso %s no observado" % name)

            op_c = g3[case_index["c"]].get("op_id")
            self.assertTrue(op_c, "G3 caso c sin op_id")
            failed = [
                e for e in g3
                if e.get("ev") == "op_state" and e.get("op_id") == op_c
                and e.get("state") == "fallido" and e.get("reason") == "lectura_no_cumple"
            ]
            self.assertTrue(failed, "G3 caso c sin fallido/lectura_no_cumple")
            never_observed = [
                e for e in g3
                if e.get("ev") == "op_state" and e.get("op_id") == op_c
                and e.get("state") == "observado"
            ]
            self.assertFalse(never_observed, "G3 caso c llego a observado")

            recoveries = [e for e in g3 if e.get("ev") == "recovery"]
            self.assertTrue(recoveries, "G3 sin recovery")
            op_r = recoveries[-1].get("op_id")
            self.assertTrue(op_r, "G3 recovery sin op_id")
            self.assertTrue(
                any(
                    e.get("ev") == "op_state" and e.get("op_id") == op_r
                    and e.get("state") == "observado"
                    for e in g3
                ),
                "G3 recovery no observado",
            )

            # 4) G9: cien mix_op
            g9 = samples["G9"]
            mix_ops = [e for e in g9 if e.get("ev") == "mix_op"]
            self.assertEqual(len(mix_ops), 100, "G9 no tiene cien mix_op")

            # 5) logs del falso: una pareja por cada op observada
            server_log = os.path.join(ev, "logs", "server_script.log")
            client_log = os.path.join(ev, "logs", "client_script.log")
            inventory_path = os.path.join(ev, "logs", "inventory.json")
            self.assertTrue(os.path.isfile(server_log), "falta logs/server_script.log")
            self.assertTrue(os.path.isfile(client_log), "falta logs/client_script.log")
            self.assertTrue(os.path.isfile(inventory_path), "falta logs/inventory.json")
            self.assertEqual(os.path.getsize(client_log), 0, "client_script.log no esta vacio")
            self.assertIsInstance(_load_json(inventory_path), dict)

            counts = {}
            with open(server_log, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if "[DSBX] effect " not in line:
                        continue
                    step = session = op = None
                    for token in line.split():
                        if token.startswith("step="):
                            step = token[len("step="):]
                        elif token.startswith("session="):
                            session = token[len("session="):]
                        elif token.startswith("op="):
                            op = token[len("op="):]
                    self.assertIn(step, ("retirar", "anotar"), line)
                    self.assertTrue(session, line)
                    self.assertTrue(op, line)
                    slot = counts.setdefault(op, {"retirar": 0, "anotar": 0})
                    slot[step] += 1

            observed_ops = set()
            for name in ("G3", "G9"):
                for event in samples[name]:
                    if event.get("ev") == "op_state" and event.get("state") == "observado":
                        observed_ops.add(event.get("op_id"))
            self.assertTrue(observed_ops, "no hay ninguna op observada")
            for op_id in observed_ops:
                slot = counts.get(op_id, {"retirar": 0, "anotar": 0})
                self.assertEqual(slot["retirar"], 1,
                                 "op %s con %d retirar" % (op_id, slot["retirar"]))
                self.assertEqual(slot["anotar"], 1,
                                 "op %s con %d anotar" % (op_id, slot["anotar"]))

            # 6) ninguna clave en ningun fichero; solo sus sha256 en manifest
            secrets_used = tuple(getattr(live, "LAST_SECRETS", ()))
            self.assertEqual(len(secrets_used), 3, "el orquestador no expuso las tres claves")
            expected_hashes = sorted(
                hashlib.sha256(secret.encode("utf-8")).hexdigest() for secret in secrets_used
            )
            self.assertEqual(sorted(manifest["key_sha256"]), expected_hashes)
            for root, _dirs, files in os.walk(ev):
                for name in files:
                    path = os.path.join(root, name)
                    with open(path, "rb") as fh:
                        data = fh.read()
                    for secret in secrets_used:
                        self.assertNotIn(secret.encode("utf-8"), data,
                                         "clave en %s" % path)

            # 7) evaluador real, si ya esta integrado
            if os.path.isfile(EVAL_PATH):
                evaluator = _load_module("f1bp_eval_dryrun", EVAL_PATH)
                result = evaluator.evaluate(ev)
                rows = None
                if isinstance(result, dict):
                    rows = result.get("rows")
                    if not isinstance(rows, dict):
                        rows = {k: v for k, v in result.items() if k in ("G2", "G3", "G9")}
                self.assertIsInstance(rows, dict, "evaluate no devolvio filas")
                for name in ("G2", "G3", "G9"):
                    row = rows.get(name)
                    self.assertIsInstance(row, dict, "evaluador sin fila %s" % name)
                    self.assertEqual(row.get("verdict"), "PASA",
                                     "evaluador %s: %r" % (name, row))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.assertFalse(os.path.exists(tmp), "la carpeta temporal no se borro")


class F1bPeersDryRunG4G8(unittest.TestCase):
    def test_dryrun_g4_g8(self):
        live = _load_module("f1bp_live_dryrun_g4g8", LIVE_PATH)
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-dry-")
        ev = os.path.join(tmp, "evidence")
        try:
            args = argparse.Namespace(
                build="diag",
                evidence=ev,
                server_profile=os.path.join(tmp, "server"),
                client_profile=os.path.join(tmp, "client"),
                pids_file=os.path.join(tmp, "pids.json"),
                scenarios="G4,G8",
                pbo=None,
                fake=True,
            )
            rc = live.run(args)
            # G4 acaba aborted a proposito con el falso: (a) y (c) necesitan el motor.
            self.assertEqual(rc, 2, "el orquestador salio con %r" % rc)

            g4 = _load_jsonl(os.path.join(ev, "samples", "G4.jsonl"))
            g8 = _load_jsonl(os.path.join(ev, "samples", "G8.jsonl"))

            # --- G4 ---
            end4 = [e for e in g4 if e.get("ev") == "end"]
            self.assertTrue(end4, "G4 sin end")
            self.assertEqual(end4[-1].get("status"), "aborted")
            self.assertEqual(end4[-1].get("reason"), "fake: G4 (a) y (c) necesitan el motor")

            index = {}
            for idx, event in enumerate(g4):
                index.setdefault(event.get("ev"), []).append(idx)
            self.assertIn("backend_restart", index, "G4 sin backend_restart")
            self.assertIn("stale_order", index, "G4 sin stale_order")
            self.assertIn("rules_active", index, "G4 sin rules_active")
            stale = g4[index["stale_order"][0]]
            self.assertLess(min(index["rules_active"]), index["stale_order"][0],
                            "rules_active no precede al stale_order")
            stale_op = stale.get("op_id")
            self.assertTrue(stale_op, "stale_order sin op_id")
            self.assertTrue(stale.get("old_session"), "stale_order sin old_session")
            restart = g4[index["backend_restart"][0]]
            self.assertEqual(restart.get("old_session"), stale.get("old_session"))
            self.assertNotEqual(restart.get("new_session"), restart.get("old_session"))

            server_log = os.path.join(ev, "logs", "server_script.log")
            with open(server_log, "r", encoding="utf-8") as fh:
                log_lines = [line.strip() for line in fh]
            stale_effects = [
                line for line in log_lines
                if "[DSBX] effect " in line and (" op=%s " % stale_op) in (line + " ")
            ]
            self.assertEqual(stale_effects, [], "la orden vieja tiene effect")

            for event in g4:
                if event.get("ev") == "result_seen" and event.get("op_id") == stale_op:
                    self.assertEqual(event.get("status"), "rejected", event)
                    self.assertEqual(event.get("reason"), "stale_session", event)

            recoveries = [e for e in g4 if e.get("ev") == "recovery"]
            self.assertTrue(recoveries, "G4 sin recovery")
            self.assertTrue(
                any(
                    e.get("ev") == "op_state" and e.get("op_id") == recoveries[-1].get("op_id")
                    and e.get("state") == "observado"
                    for e in g4
                ),
                "la recovery de G4 no llego a observado",
            )

            # --- G8 ---
            cases = {e.get("name"): e for e in g8 if e.get("ev") == "case"}
            for name in ("a", "b", "c"):
                self.assertIn(name, cases, "G8 sin caso %s" % name)
            op_b = cases["b"].get("op_id")
            self.assertTrue(
                any(
                    e.get("ev") == "result_seen" and e.get("op_id") == op_b and e.get("dup") is True
                    for e in g8
                ),
                "G8 caso b sin result_seen con dup true",
            )
            self.assertEqual(cases["c"].get("op_id"), "op-1")

            # --- evaluador real: PASA en G8 ---
            evaluator = _load_module("f1bp_eval_dryrun_g4g8", EVAL_PATH)
            result = evaluator.evaluate(ev)
            row = result.get("rows", {}).get("G8")
            self.assertIsInstance(row, dict, "evaluador sin fila G8")
            self.assertEqual(row.get("verdict"), "PASA", "evaluador G8: %r" % (row,))

            # --- ninguna clave en ningun fichero ---
            secrets_used = tuple(getattr(live, "LAST_SECRETS", ()))
            self.assertGreaterEqual(len(secrets_used), 3)
            for root, _dirs, files in os.walk(tmp):
                for name in files:
                    path = os.path.join(root, name)
                    with open(path, "rb") as fh:
                        data = fh.read()
                    for secret in secrets_used:
                        self.assertNotIn(secret.encode("utf-8"), data, "clave en %s" % path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            self.assertFalse(os.path.exists(tmp), "la carpeta temporal no se borro")


if __name__ == "__main__":
    unittest.main()
