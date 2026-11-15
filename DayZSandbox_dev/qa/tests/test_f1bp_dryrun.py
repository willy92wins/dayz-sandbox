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


def _evaluate_clean(evaluator, ev):
    """Evalua una copia de la carpeta con git_dirty false: este arbol no tiene .git (git_dirty true
    es lo correcto aqui) y con git_dirty true el evaluador da INCONCLUSO a todo."""
    copy = tempfile.mkdtemp(prefix="dsbx-f1bp-evalcopy-")
    try:
        target = os.path.join(copy, "ev")
        shutil.copytree(ev, target)
        mpath = os.path.join(target, "manifest.json")
        manifest = _load_json(mpath)
        manifest["git_dirty"] = False
        with open(mpath, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(manifest, fh, sort_keys=True)
        return evaluator.evaluate(target)
    finally:
        shutil.rmtree(copy, ignore_errors=True)


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
            # R1: sin .git (esta copia no lo tiene) -> null y git_dirty true; con git, SHA completo.
            head, dirty = manifest["git_head"], manifest["git_dirty"]
            self.assertIsInstance(dirty, bool)
            if head is None:
                self.assertIs(dirty, True, "sin git_head, git_dirty tiene que ser true")
            else:
                self.assertRegex(head, r"^[0-9a-f]{40}$")
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

            # R5/R6/R9/R10 en G3
            sessions = {e.get("session") for e in g3 if e.get("ev") in ("apply", "case", "op_state")}
            self.assertEqual(len(sessions), 1, "G3 con mas de una sesion: %r" % sessions)
            session = sessions.pop()
            self.assertTrue(isinstance(session, str) and session, "G3 sin session")
            applies = {e["op_id"]: e for e in g3 if e.get("ev") == "apply" and e.get("op_id")}
            for e in g3:
                if e.get("ev") == "apply":
                    self.assertIsInstance(e.get("t_ms"), float)
                    self.assertIsInstance(e.get("t_end_ms"), float)
                    self.assertLessEqual(e["t_ms"], e["t_end_ms"], "apply.t_ms tras t_end_ms")
                if e.get("ev") == "case" and e.get("op_id"):
                    self.assertEqual(e.get("session"), session)
            first_state = {}
            for e in g3:
                if e.get("ev") == "op_state":
                    self.assertIsInstance(e.get("t_ms"), float)
                    self.assertNotIn("t_src", e, "el backend trae el instante: no es de lectura")
                    first_state.setdefault(e["op_id"], e)
            for op_id, ap in applies.items():
                self.assertGreaterEqual(
                    first_state[op_id]["t_ms"] + 1.0, ap["t_ms"],
                    "op_state de %s anterior a su apply" % op_id,
                )
            self.assertEqual(g3[case_index["c"]].get("rule_id"), "g3c-rewrite")
            self.assertNotIn("rule_id", g3[case_index["a"]])
            # R10: tras el caso c, `rules` con rule_ids [] y su rules_active, antes de la recuperacion.
            idx_rec = [i for i, e in enumerate(g3) if e.get("ev") == "recovery"][-1]
            empties = [
                i for i, e in enumerate(g3)
                if e.get("ev") == "rules" and e.get("rule_ids") == [] and case_index["c"] < i < idx_rec
            ]
            self.assertTrue(empties, "G3 sin rules vacio entre el caso c y la recuperacion")
            self.assertTrue(
                any(
                    e.get("ev") == "rules_active" and e.get("version") == g3[empties[0]].get("version")
                    for e in g3[empties[0] + 1:idx_rec]
                ),
                "el rules vacio de G3 sin su rules_active antes de la recuperacion",
            )

            # 4) G9: cien mix_op
            g9 = samples["G9"]
            mix_ops = [e for e in g9 if e.get("ev") == "mix_op"]
            self.assertEqual(len(mix_ops), 100, "G9 no tiene cien mix_op")
            self.assertTrue(all(e.get("session") == session for e in g9 if e.get("ev") == "mix_op"))
            for e in g9:
                if e.get("ev") == "op_state" and e.get("state") == "observado":
                    ap = [a for a in g9 if a.get("ev") == "apply" and a.get("op_id") == e["op_id"]]
                    self.assertTrue(ap and e["t_ms"] - ap[0]["t_ms"] >= 0, "latencia negativa en G9")

            # 5) logs del falso: una pareja por cada op observada
            server_log = os.path.join(ev, "logs", "server_script.log")
            client_log = os.path.join(ev, "logs", "client_script.log")
            inventory_path = os.path.join(ev, "logs", "inventory.json")
            self.assertTrue(os.path.isfile(server_log), "falta logs/server_script.log")
            self.assertTrue(os.path.isfile(client_log), "falta logs/client_script.log")
            self.assertTrue(os.path.isfile(inventory_path), "falta logs/inventory.json")
            self.assertEqual(os.path.getsize(client_log), 0, "client_script.log no esta vacio")
            inventory = _load_json(inventory_path)
            self.assertIsInstance(inventory, dict)
            # R3: {"server": {"dir", "files"}, "client": {...}, "copies": [...]}
            for role in ("server", "client"):
                self.assertTrue(os.path.isabs(inventory[role]["dir"]))
                self.assertIsInstance(inventory[role]["files"], list)
            self.assertIsInstance(inventory["copies"], list)
            self.assertEqual(
                {c["dest"] for c in inventory["copies"]}, {"server_script.log", "client_script.log"}
            )
            # R4: key_scan (en el ultimo escenario) con rutas absolutas del inventario y de logs/.
            scans = [e for e in samples["G9"] if e.get("ev") == "key_scan"]
            self.assertEqual(len(scans), 1, "G9 sin key_scan")
            self.assertEqual(scans[0].get("hits"), 0)
            self.assertTrue(all(os.path.isabs(f) for f in scans[0]["files"]))
            scanned = {os.path.normcase(f) for f in scans[0]["files"]}
            for role in ("server", "client"):
                for name in inventory[role]["files"]:
                    self.assertIn(
                        os.path.normcase(os.path.join(inventory[role]["dir"], name)), scanned
                    )
            for name in ("server_script.log", "client_script.log", "inventory.json"):
                self.assertIn(os.path.normcase(os.path.join(ev, "logs", name)), scanned)

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
                result = _evaluate_clean(evaluator, ev)
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

            # R5: la sesion de cada caso; c, en la sesion nueva del backend reiniciado.
            g8_restart = [e for e in g8 if e.get("ev") == "backend_restart"]
            self.assertEqual(len(g8_restart), 1)
            self.assertEqual(cases["a"].get("session"), g8_restart[0]["old_session"])
            self.assertEqual(cases["b"].get("session"), g8_restart[0]["old_session"])
            self.assertEqual(cases["c"].get("session"), g8_restart[0]["new_session"])
            self.assertNotEqual(cases["c"]["session"], cases["a"]["session"])
            for name in ("a", "b", "c"):
                states = [
                    e for e in g8
                    if e.get("ev") == "op_state" and e.get("op_id") == cases[name]["op_id"]
                    and e.get("session") == cases[name]["session"]
                ]
                self.assertTrue(states, "G8 %s: op_state sin la sesion del caso" % name)
            # R9
            self.assertEqual(cases["a"].get("rule_id"), "g8a_drop")
            self.assertEqual(cases["b"].get("rule_id"), "g8b_503")
            self.assertNotIn("rule_id", cases["c"])
            # R10: cada inyeccion de G8 acaba en un rules vacio con su rules_active
            for i, e in enumerate(g8):
                if e.get("ev") == "rules" and e.get("rule_ids") == []:
                    self.assertTrue(
                        any(
                            x.get("ev") == "rules_active" and x.get("version") == e.get("version")
                            for x in g8[i + 1:]
                        ),
                        "rules vacio de G8 sin su rules_active",
                    )
            self.assertGreaterEqual(
                len([e for e in g8 if e.get("ev") == "rules" and e.get("rule_ids") == []]), 2
            )
            # G4 b: sus dos reglas (R9) y la sesion vieja en el stale_order
            case_b = [e for e in g4 if e.get("ev") == "case" and e.get("name") == "b"]
            self.assertEqual(len(case_b), 1)
            self.assertEqual(case_b[0].get("rule_ids"), ["g4b_hold", "g4b_stale"])
            self.assertEqual(case_b[0].get("session"), stale.get("old_session"))

            # --- evaluador real: PASA en G8 ---
            evaluator = _load_module("f1bp_eval_dryrun_g4g8", EVAL_PATH)
            result = _evaluate_clean(evaluator, ev)
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


class F1bPeersDryRunG1(unittest.TestCase):
    def test_g1_y_hello_sin_parche_de_peer(self):
        """R15: el seco no parchea _Peer._http; el proxy saca el peer del cuerpo del hello."""
        live = _load_module("f1bp_live_dryrun_g1", LIVE_PATH)
        from app.tests import fake_mod

        before = fake_mod._Peer._http
        with open(LIVE_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn("http_with_peer", source)
        self.assertNotIn("_peer_http_patched", source)
        self.assertNotIn('"peer=" + peer_self.role', source)
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-dry-")
        ev = os.path.join(tmp, "evidence")
        try:
            args = argparse.Namespace(
                build="diag",
                evidence=ev,
                server_profile=os.path.join(tmp, "server"),
                client_profile=os.path.join(tmp, "client"),
                pids_file=os.path.join(tmp, "pids.json"),
                scenarios="G1",
                pbo=None,
                fake=True,
            )
            rc = live.run(args)
            self.assertEqual(rc, 0)
            self.assertIs(fake_mod._Peer._http, before, "el orquestador cambio _Peer._http")
            g1 = _load_jsonl(os.path.join(ev, "samples", "G1.jsonl"))
            self.assertEqual(
                sorted(e["peer"] for e in g1 if e.get("ev") == "connected"), ["client", "server"]
            )
            hellos = [
                e for e in _load_jsonl(os.path.join(ev, "samples", "proxy.jsonl"))
                if e.get("route") == "hello"
            ]
            self.assertTrue(hellos)
            self.assertTrue(all(e.get("peer") in ("server", "client") for e in hellos))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _FakeRun:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


class F1bPeersUnits(unittest.TestCase):
    def setUp(self):
        self.live = _load_module("f1bp_live_units", LIVE_PATH)

    # --- R1
    def test_git_provenance(self):
        live = self.live
        root = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
        sha = "ab" * 20
        calls = []

        def make(status_out, top=root, rc=0):
            def runner(cmd, **kw):
                calls.append((cmd, kw))
                sub = cmd[3:]
                if sub[:1] == ["rev-parse"] and "--show-toplevel" in sub:
                    return _FakeRun(rc, top + "\n")
                if sub[:1] == ["rev-parse"]:
                    return _FakeRun(rc, sha + "\n")
                if sub[:1] == ["status"]:
                    return _FakeRun(rc, status_out)
                raise AssertionError(cmd)
            return runner

        self.assertEqual(live._git_provenance(root, make("")), (sha, False))
        self.assertEqual(live._git_provenance(root, make(" M DayZSandbox/x.c\n")), (sha, True))
        status_cmd = [c for c, _kw in calls if "status" in c][0]
        self.assertEqual(status_cmd[-4:], ["--porcelain", "--", ".", ":(exclude)DayZSandbox_dev/evidence"])
        self.assertEqual(status_cmd[:3], ["git", "-C", root])
        self.assertEqual(calls[-1][1]["env"].get("GIT_OPTIONAL_LOCKS"), "0")
        # git falla (sin repo) o el repo no tiene root como raiz -> null y sucio
        self.assertEqual(live._git_provenance(root, make("", rc=128)), (None, True))
        self.assertEqual(live._git_provenance(root, make("", top=os.path.dirname(root))), (None, True))

        def boom(cmd, **kw):
            raise FileNotFoundError("git")

        self.assertEqual(live._git_provenance(root, boom), (None, True))

    # --- R4 y R2
    def _bare_run(self, tmp, secrets_used, scenarios=("G4", "G9")):
        live = self.live
        run = live.LiveRun.__new__(live.LiveRun)
        run.args = argparse.Namespace(server_profile=None, client_profile=None)
        run.scenarios = list(scenarios)
        run.evidence = tmp
        run.logs_dir = os.path.join(tmp, "logs")
        run.samples_dir = os.path.join(tmp, "samples")
        os.makedirs(run.logs_dir)
        os.makedirs(run.samples_dir)
        run.secrets = tuple(secrets_used)
        run.aborted = False
        run.logs_final = True
        run.writer = live.EvidenceWriter(run.samples_dir)
        return run

    def test_key_scan_inventario_y_salida_1(self):
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-ks-")
        try:
            run = self._bare_run(tmp, ("K" * 40, "j" * 40))
            prof_s = os.path.join(tmp, "perfil_s")
            prof_c = os.path.join(tmp, "perfil_c")
            os.makedirs(prof_s)
            os.makedirs(prof_c)
            with open(os.path.join(prof_s, "script_a.log"), "w", encoding="utf-8") as fh:
                fh.write("linea limpia\n")
            with open(os.path.join(prof_s, "crash.mdmp"), "wb") as fh:
                fh.write(b"\x00" * 10 + b"j" * 40 + b"\x00")
            with open(os.path.join(prof_c, "client.RPT"), "w", encoding="utf-8") as fh:
                fh.write("limpio\n")
            with open(os.path.join(run.logs_dir, "server_script.log"), "w", encoding="utf-8") as fh:
                fh.write("copia limpia\n")
            inventory = {
                "server": {"dir": prof_s, "files": ["script_a.log", "crash.mdmp", "falta.log"]},
                "client": {"dir": prof_c, "files": ["client.RPT"]},
                "copies": [],
            }
            with open(os.path.join(run.logs_dir, "inventory.json"), "w", encoding="utf-8") as fh:
                json.dump(inventory, fh)
            open(os.path.join(run.samples_dir, "G4.jsonl"), "w").close()
            open(os.path.join(run.samples_dir, "G9.jsonl"), "w").close()
            hits = run.key_scan()
            self.assertEqual(hits, 1, "la clave del .mdmp del perfil no se vio")
            scan = _load_jsonl(os.path.join(run.samples_dir, "G4.jsonl"))[0]
            self.assertEqual(scan["ev"], "key_scan")
            self.assertEqual(scan["hits"], 1)
            norm = {os.path.normcase(f) for f in scan["files"]}
            for name, base in (
                ("script_a.log", prof_s), ("crash.mdmp", prof_s), ("client.RPT", prof_c),
            ):
                self.assertIn(os.path.normcase(os.path.join(base, name)), norm)
            self.assertIn(os.path.normcase(os.path.join(run.logs_dir, "server_script.log")), norm)
            self.assertTrue(all(os.path.isabs(f) for f in scan["files"]))
            self.assertEqual([os.path.basename(u) for u in scan["unreadable"]], ["falta.log"])
            # el contrato de salida
            self.assertEqual(run.final_code(1), 1)
            run.aborted = True
            self.assertEqual(run.final_code(1), 1, "hits manda sobre aborted")
            self.assertEqual(run.final_code(0), 2)
            run.aborted = False
            run.logs_final = False
            self.assertEqual(run.final_code(0), 2, "R2: logs no finales -> 2")
            run.logs_final = True
            self.assertEqual(run.final_code(0), 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_clave_a_caballo_entre_trozos(self):
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-ks-")
        try:
            path = os.path.join(tmp, "f.bin")
            key = b"SECRETO-0123456789"
            with open(path, "wb") as fh:
                fh.write(b"x" * 20 + key + b"y" * 30 + key + b"z" * 5)
            self.assertEqual(self.live._count_in_file(path, [key], chunk=23), 2)
            self.assertEqual(self.live._count_in_file(path, [key], chunk=4096), 2)
            self.assertIsNone(self.live._count_in_file(os.path.join(tmp, "no_existe"), [key]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_logs_ready_solo_con_all_closed_true(self):
        live = self.live
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-lr-")
        try:
            run = live.LiveRun.__new__(live.LiveRun)
            run.evidence = tmp
            self.assertIsNone(run.wait_logs_ready(0.1), "sin fichero no hay contenido")
            with open(os.path.join(tmp, "logs_ready.json"), "w", encoding="utf-8") as fh:
                json.dump({"all_closed": False}, fh)
            doc = run.wait_logs_ready(0.1)
            self.assertEqual(doc, {"all_closed": False})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # --- R5, R6, R9
    def test_apply_emit_y_case(self):
        live = self.live
        events = []

        class Writer:
            def emit(self, ev, t_ms=None, **fields):
                events.append(dict(fields, ev=ev, t_ms=t_ms))

        class Web:
            last_session = "s-1"
            last_t_ms = 100.0
            last_t_end_ms = 130.0

            def apply(self):
                return 200, "op-7"

        class Bridge:
            ttl_ms = 10000

        run = live.LiveRun.__new__(live.LiveRun)
        run.writer = Writer()
        run.bridge = Bridge()
        web = Web()
        run.apply_case(web, "c", ["r1"])
        run.apply_case(web, "x", ["r1", "r2"])
        run.apply_case(web, "n")
        status, op_id = run.apply_emit(web, ttl_ms=1500)
        applies = [e for e in events if e["ev"] == "apply"]
        self.assertEqual(
            {(a["session"], a["t_ms"], a["t_end_ms"], a["op_id"]) for a in applies[:3]},
            {("s-1", 100.0, 130.0, "op-7")},
        )
        self.assertEqual(applies[0]["ttl_ms"], 10000)
        self.assertEqual(applies[3]["ttl_ms"], 1500)
        cases = [e for e in events if e["ev"] == "case"]
        self.assertEqual(cases[0]["rule_id"], "r1")
        self.assertNotIn("rule_ids", cases[0])
        self.assertEqual(cases[1]["rule_ids"], ["r1", "r2"])
        self.assertNotIn("rule_id", cases[1])
        self.assertNotIn("rule_id", cases[2])
        self.assertNotIn("rule_ids", cases[2])
        self.assertTrue(all(c["session"] == "s-1" for c in cases))

    def test_writer_ordena_por_t_ms(self):
        """apply.t_ms (antes del POST) puede ser anterior a eventos ya emitidos: el fichero va ordenado."""
        live = self.live
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-w-")
        try:
            writer = live.EvidenceWriter(tmp)
            writer.begin("G9")
            t = live._now_ms()
            writer.emit("op_state", t_ms=t + 5.0, op_id="op-1")
            writer.emit("apply", t_ms=t, op_id="op-1")
            writer.emit("recovery", t_ms=t + 9.0)
            writer.end()
            got = [e["ev"] for e in _load_jsonl(os.path.join(tmp, "G9.jsonl"))]
            self.assertEqual(got, ["apply", "op_state", "recovery"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ring_poller_instante_del_suceso(self):
        live = self.live
        import threading
        import time

        events = []

        class Writer:
            def emit(self, ev, t_ms=None, **fields):
                events.append(dict(fields, ev=ev, t_ms=t_ms))

        class Backend:
            seq = 0
            store = type("S", (), {"lock": threading.RLock()})()
            bridge = type("B", (), {"session": "sess-X"})()

        backend = Backend()
        backend.ring = [
            (1, "op.state", json.dumps({"op_id": "op-1", "state": "observado", "reason": None,
                                        "at_ms": int(time.time() * 1000) - 500})),
            (2, "op.state", json.dumps({"op_id": "op-2", "state": "pendiente", "reason": None})),
            (3, "otra", "{}"),
        ]
        poller = live.RingPoller(backend, Writer(), threading.Event())
        poller.baseline = 0
        before = live._now_ms()
        poller.drain()
        self.assertEqual([e["op_id"] for e in events], ["op-1", "op-2"])
        self.assertTrue(all(e["session"] == "sess-X" for e in events))
        # op-1 trae su instante (500 ms antes de leerlo): no es el de lectura
        self.assertNotIn("t_src", events[0])
        self.assertLess(events[0]["t_ms"], before - 400.0)
        self.assertGreater(events[0]["t_ms"], before - 700.0)
        # op-2 no lo trae: el de lectura, marcado
        self.assertEqual(events[1]["t_src"], "lectura")
        self.assertGreaterEqual(events[1]["t_ms"], before)


if __name__ == "__main__":
    unittest.main()
