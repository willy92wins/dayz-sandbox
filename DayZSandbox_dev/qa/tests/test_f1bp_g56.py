"""Pruebas de G5 y G6 del arnes F1b-peers (L2b3a), sin juego y sin suspender nada.

- Con --fake, G5 y G6 acaban `aborted` con su motivo y ninguna clave aparece en la evidencia.
- confirm_gap_zero lee solo la ULTIMA linea `config qa_step_gap_ms=` del script log mas reciente.
- La comprobacion de identidad de proceso se prueba sobre el propio Python, sin suspenderlo.
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_PATH = os.path.abspath(os.path.join(HERE, "..", "live", "f1bp_live.py"))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))

import importlib.util  # noqa: E402


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


class G56Fake(unittest.TestCase):
    def test_fake_aborta_con_motivo_y_sin_claves(self):
        live = _load_module("f1bp_live_g56_fake", LIVE_PATH)
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-g56-")
        ev = os.path.join(tmp, "evidence")
        try:
            args = argparse.Namespace(
                build="diag",
                evidence=ev,
                server_profile=os.path.join(tmp, "server"),
                client_profile=os.path.join(tmp, "client"),
                pids_file=os.path.join(tmp, "pids.json"),
                scenarios="G5,G6",
                pbo=None,
                fake=True,
            )
            rc = live.run(args)
            self.assertEqual(rc, 2, "con escenarios abortados el orquestador sale con 2")
            expected = {"G5": "fake: G5 necesita el motor", "G6": "fake: G6 necesita el motor"}
            for name, reason in expected.items():
                path = os.path.join(ev, "samples", name + ".jsonl")
                self.assertTrue(os.path.isfile(path), "falta %s" % path)
                ends = [e for e in _jsonl(path) if e.get("ev") == "end"]
                self.assertTrue(ends, "%s sin end" % name)
                self.assertEqual(ends[-1].get("status"), "aborted")
                self.assertEqual(ends[-1].get("reason"), reason)
            secrets_used = live.LAST_SECRETS
            self.assertEqual(len(secrets_used), 3)
            hits = 0
            for root, _dirs, files in os.walk(tmp):
                for fname in files:
                    with open(os.path.join(root, fname), "rb") as fh:
                        data = fh.read()
                    for secret in secrets_used:
                        hits += data.count(secret.encode("utf-8"))
            self.assertEqual(hits, 0, "una clave aparece en la carpeta de evidencia")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(os.path.exists(tmp))

    def test_argumento_g6_clock_s(self):
        live = _load_module("f1bp_live_g56_parser", LIVE_PATH)
        parser = live.build_parser()
        base = ["run", "--build", "diag", "--evidence", "e", "--server-profile", "s",
                "--client-profile", "c", "--pids-file", "p", "--scenarios", "G6"]
        self.assertEqual(parser.parse_args(base).g6_clock_s, 600.0)
        self.assertEqual(parser.parse_args(base + ["--g6-clock-s", "5"]).g6_clock_s, 5.0)


class G56CaseEvents(unittest.TestCase):
    """R5, R6 y R9 en los casos de G5 (que con el falso no corren): `case` con rule_id y sesion."""

    def test_g56_apply_case_lleva_rule_id_y_sesion(self):
        live = _load_module("f1bp_live_g56_case", LIVE_PATH)
        events = []

        class Writer:
            def emit(self, ev, t_ms=None, **fields):
                events.append(dict(fields, ev=ev, t_ms=t_ms))

        class Web:
            last_session = "sesion-9"
            last_t_ms = 10.0
            last_t_end_ms = 25.5

            def apply(self):
                return 200, "op-3"

        class Bridge:
            ttl_ms = 10000

        run = live.LiveRun.__new__(live.LiveRun)
        run.writer = Writer()
        run.bridge = Bridge()
        self.assertEqual(run._g56_apply_case(Web(), "a2500", "client", ["g5a_client_2500"]), "op-3")
        apply_ev, case_ev = events
        self.assertEqual(apply_ev["ev"], "apply")
        self.assertEqual((apply_ev["t_ms"], apply_ev["t_end_ms"]), (10.0, 25.5))
        self.assertEqual(apply_ev["session"], "sesion-9")
        self.assertEqual(case_ev["name"], "a2500")
        self.assertEqual(case_ev["peer"], "client")
        self.assertEqual(case_ev["rule_id"], "g5a_client_2500")
        self.assertEqual(case_ev["session"], "sesion-9")

    def test_g5_g6_citan_su_regla_en_el_codigo(self):
        with open(LIVE_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn('self._g56_apply_case(web, name, peer, [rule_id])', source)
        self.assertIn('self._g56_apply_case(web, name, "server", [rule_id])', source)
        self.assertIn('**_rule_fields([rule_id])', source)


class ConfirmGapZero(unittest.TestCase):
    def setUp(self):
        self.live = _load_module("f1bp_live_g56_gap", LIVE_PATH)
        self.run = self.live.LiveRun.__new__(self.live.LiveRun)
        self.tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-gap-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _log(self, name, lines, mtime=None):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_ultima_linea_cero(self):
        self._log("script_1.log", [
            "10:00:00.100 [DSBX] config qa_step_gap_ms=2500",
            "10:00:05.100 [DSBX] clock tick_ms=5000",
            "10:01:00.100 [DSBX] config qa_step_gap_ms=0",
        ])
        self.assertTrue(self.run.confirm_gap_zero(self.tmp))

    def test_cero_antes_y_2500_al_final(self):
        self._log("script_1.log", [
            "10:00:00.100 [DSBX] config qa_step_gap_ms=0",
            "10:01:00.100 [DSBX] config qa_step_gap_ms=2500",
        ])
        self.assertFalse(self.run.confirm_gap_zero(self.tmp))

    def test_solo_cuenta_el_log_mas_reciente(self):
        now = time.time()
        self._log("script_old.log", ["[DSBX] config qa_step_gap_ms=0"], mtime=now - 100)
        self._log("script_new.log", ["[DSBX] config qa_step_gap_ms=4000"], mtime=now)
        self.assertFalse(self.run.confirm_gap_zero(self.tmp))

    def test_sin_log_o_sin_linea(self):
        self.assertFalse(self.run.confirm_gap_zero(self.tmp))
        self._log("script_1.log", ["[DSBX] clock tick_ms=5000"])
        self.assertFalse(self.run.confirm_gap_zero(self.tmp))
        self.assertFalse(self.run.confirm_gap_zero(None))


class ProcessIdentity(unittest.TestCase):
    """Solo abre el proceso propio de Python con permiso de consulta; no suspende nada."""

    QUERY_LIMITED = 0x1000

    def setUp(self):
        self.live = _load_module("f1bp_live_g56_ident", LIVE_PATH)
        self.cls = self.live.LiveRun

    def _own_start(self):
        # Referencia independiente: lo que escribe el lanzador (PowerShell, formato 'o', UTC).
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "(Get-Process -Id %d).StartTime.ToUniversalTime().ToString('o')" % os.getpid()]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        text = out.stdout.strip()
        return text if out.returncode == 0 and text else None

    def test_parseo_iso(self):
        parsed = self.cls._g56_parse_iso_utc("2026-11-15T10:20:30.1234567Z")
        self.assertEqual(parsed, datetime.datetime(2026, 11, 15, 10, 20, 30, 123456, tzinfo=datetime.timezone.utc))
        self.assertIsNone(self.cls._g56_parse_iso_utc("no es una fecha"))
        self.assertIsNone(self.cls._g56_parse_iso_utc(None))

    def test_identidad_del_propio_python(self):
        pid = os.getpid()
        powershell_start = self._own_start()
        handle = self.cls._g56_open_if_own(
            pid, self._iso_from_handle(pid), self.QUERY_LIMITED
        )
        self.assertIsNotNone(handle, "el instante de creacion propio no casa consigo mismo")
        self.cls._g56_win()[2].CloseHandle(handle)

        if powershell_start is not None:
            handle = self.cls._g56_open_if_own(pid, powershell_start, self.QUERY_LIMITED)
            self.assertIsNotNone(handle, "no casa con el StartTime de PowerShell (%s)" % powershell_start)
            self.cls._g56_win()[2].CloseHandle(handle)

        # Un start_time distinto, mas alla de los 2 s de tolerancia, no casa.
        shifted = (self.cls._g56_parse_iso_utc(self._iso_from_handle(pid)) + datetime.timedelta(seconds=10))
        self.assertIsNone(self.cls._g56_open_if_own(pid, shifted.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), self.QUERY_LIMITED))
        # Dentro de la tolerancia, si.
        near = (self.cls._g56_parse_iso_utc(self._iso_from_handle(pid)) + datetime.timedelta(seconds=1.5))
        handle = self.cls._g56_open_if_own(pid, near.strftime("%Y-%m-%dT%H:%M:%S.%fZ"), self.QUERY_LIMITED)
        self.assertIsNotNone(handle)
        self.cls._g56_win()[2].CloseHandle(handle)
        # Sin start_time o invalido, nunca.
        self.assertIsNone(self.cls._g56_open_if_own(pid, None, self.QUERY_LIMITED))
        self.assertIsNone(self.cls._g56_open_if_own(pid, "basura", self.QUERY_LIMITED))
        self.assertIsNone(self.cls._g56_open_if_own(0, "2026-01-01T00:00:00Z", self.QUERY_LIMITED))

    def _iso_from_handle(self, pid):
        _ctypes, _wintypes, k32, _ntdll = self.cls._g56_win()
        handle = k32.OpenProcess(self.QUERY_LIMITED, False, pid)
        self.assertTrue(handle)
        try:
            created = self.cls._g56_creation_time(handle)
        finally:
            k32.CloseHandle(handle)
        self.assertIsNotNone(created)
        return created.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def test_entrada_del_servidor_en_pids_json(self):
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-pids-")
        try:
            path = os.path.join(tmp, "pids.json")
            run = self.cls.__new__(self.cls)
            run.args = argparse.Namespace(pids_file=path)
            forms = [
                {"processes": [{"role": "client", "pid": 1, "start_time": "x"},
                               {"role": "server", "pid": 7, "start_time": "y"}]},
                {"processes": {"role": "server", "pid": 7, "start_time": "y"}},
                {"processes": {"server": {"pid": 7, "start_time": "y"}}},
            ]
            for form in forms:
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(form, fh)
                entry = run._g56_server_entry()
                self.assertIsNotNone(entry, form)
                self.assertEqual(entry["pid"], 7)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump({"processes": [{"role": "client", "pid": 1}]}, fh)
            self.assertIsNone(run._g56_server_entry())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_suspender_se_niega_si_la_identidad_no_casa(self):
        """Con un start_time que no casa, no se suspende nada (el propio Python sigue vivo)."""
        tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-nosusp-")
        try:
            path = os.path.join(tmp, "pids.json")
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump({"processes": [{"role": "server", "pid": os.getpid(),
                                          "start_time": "2001-01-01T00:00:00.0000000Z"}]}, fh)
            run = self.cls.__new__(self.cls)
            run.args = argparse.Namespace(pids_file=path)
            t_s, t_e, why = run._g56_suspend_server(1)
            self.assertIsNone(t_s)
            self.assertIsNone(t_e)
            self.assertTrue(why)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class G6AlineaConElPoll(unittest.TestCase):
    """H-14: G6 encola justo al terminar un poll del servidor (proxy.jsonl desde la marca)."""

    def setUp(self):
        self.live = _load_module("f1bp_live_g6_align", LIVE_PATH)
        self.run = self.live.LiveRun.__new__(self.live.LiveRun)
        self.tmp = tempfile.mkdtemp(prefix="dsbx-f1bp-g6al-")
        self.run.proxy_log = os.path.join(self.tmp, "proxy.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rows, mode="w"):
        with open(self.run.proxy_log, mode, encoding="utf-8", newline="\n") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def test_devuelve_el_primer_poll_del_servidor_tras_la_marca(self):
        self._write([{"peer": "server", "route": "poll", "t_done_ms": 100}])
        mark = self.run._g56_mark()
        self._write([
            {"peer": "client", "route": "poll", "t_done_ms": 200},
            {"peer": "server", "route": "result", "t_done_ms": 300},
            {"peer": "server", "route": "poll"},
            {"peer": "server", "route": "poll", "t_done_ms": 400},
            {"peer": "server", "route": "poll", "t_done_ms": 500},
        ], mode="a")
        self.assertEqual(self.run._g6_wait_server_poll(mark, 1.0), 400)

    def test_sin_poll_del_servidor_devuelve_none(self):
        self._write([{"peer": "server", "route": "poll", "t_done_ms": 100}])
        mark = self.run._g56_mark()
        self._write([{"peer": "client", "route": "poll", "t_done_ms": 200}], mode="a")
        t0 = time.monotonic()
        self.assertIsNone(self.run._g6_wait_server_poll(mark, 0.2))
        self.assertGreaterEqual(time.monotonic() - t0, 0.2)

    def test_g6_espera_el_poll_antes_de_encolar(self):
        with open(LIVE_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        body = source[source.index("    def run_g6_body(self):"):]
        wait = body.index("self._g6_wait_server_poll(self._g56_mark(), G6_POLL_ALIGN_S)")
        apply = body.index("self.apply_emit(web, ttl_ms=1500)")
        rules = body.index("self.set_rules(self.next_rules_version(), [rule], [rule_id])")
        self.assertLess(rules, wait)
        self.assertLess(wait, apply)


if __name__ == "__main__":
    unittest.main()
