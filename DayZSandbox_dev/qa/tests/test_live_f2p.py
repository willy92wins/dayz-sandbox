"""Pruebas del runner F2P (T4 §8.A.2): tap, scene_del, manifest, orden y R-61."""

import http.client
import importlib.util
import json
import sys
import tempfile
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve()
QA = HERE.parents[1]
DEV = QA.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


tap_mod = _load("f2p_tap_test", QA / "live" / "f2p_tap.py")
live = _load("f2p_partida_test", QA / "live" / "f2p_partida.py")


def _clock():
    state = {"t": 1000.0}

    def tick():
        state["t"] += 1.0
        return state["t"]

    return tick


class _Upstream:
    def __init__(self, handler):
        self.handler = handler
        self.port = None
        self.server = None

    def __enter__(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        self.port = srv.server_address[1]
        self.server = srv
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()
        return False


def _ok_handler(status=200, payload=b'{"ok":true,"n":1}'):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _go(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_GET = _go
        do_POST = _go

    return H


def _request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, path, body=body,
                     headers={"Content-Type": "application/json"} if body else {})
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


class TapTests(unittest.TestCase):
    def test_req_id_unico_emparejado_y_sin_clave(self):
        with _Upstream(_ok_handler()) as up:
            tap = tap_mod.Tap(up.port, clock=_clock()).start()
            try:
                for i in range(3):
                    status, _ = _request(tap.port, "GET",
                                         "/poll?peer=server&inst=aa&key=SECRETO&deliver=1")
                    self.assertEqual(status, 200)
            finally:
                tap.stop()
        reqs = [r for r in tap.records if r["dir"] == "req"]
        resps = [r for r in tap.records if r["dir"] == "resp"]
        self.assertEqual([r["req_id"] for r in reqs], [0, 1, 2])
        self.assertEqual([r["req_id"] for r in resps], [0, 1, 2])
        for r in reqs:
            self.assertNotIn("key", r["query"])
            self.assertNotIn("SECRETO", json.dumps(r))
        # negativa: duplicar un req_id en los registros se detecta al emparejar
        ids = [r["req_id"] for r in reqs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_respuesta_estampada_antes_y_bytes_sin_cambiar(self):
        order = []

        def sink(rec):
            order.append((rec["dir"], rec["req_id"]))

        with _Upstream(_ok_handler(payload=b'{"ok":true,"x":"abc"}')) as up:
            tap = tap_mod.Tap(up.port, clock=_clock(), sink=sink).start()
            try:
                status, data = _request(tap.port, "POST", "/result?key=k",
                                        body=b'{"op_id":"op-1"}')
            finally:
                tap.stop()
        self.assertEqual(status, 200)
        self.assertEqual(data, b'{"ok":true,"x":"abc"}')
        self.assertEqual(order, [("req", 0), ("resp", 0)])
        resp = [r for r in tap.records if r["dir"] == "resp"][0]
        self.assertEqual(resp["body"], {"ok": True, "x": "abc"})
        self.assertIsInstance(resp["t_ms"], float)
        # negativa: t_ms no finito no se acepta del reloj
        bad = tap_mod.Tap(1, clock=lambda: float("inf"))
        with self.assertRaises(ValueError):
            bad._stamp()

    def test_upstream_status_entero_nulo_502_y_cero(self):
        # entero del backend
        with _Upstream(_ok_handler(status=201, payload=b'{"ok":true}')) as up:
            tap = tap_mod.Tap(up.port, clock=_clock()).start()
            try:
                _request(tap.port, "GET", "/hello")
            finally:
                tap.stop()
        resp = [r for r in tap.records if r["dir"] == "resp"][0]
        self.assertEqual(resp["upstream_status"], 201)
        self.assertIs(type(resp["upstream_status"]), int)
        # nulo con el 502 exacto cuando el backend no contesta
        tap2 = tap_mod.Tap(1, clock=_clock()).start()
        try:
            status, data = _request(tap2.port, "GET", "/poll?peer=server")
        finally:
            tap2.stop()
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(data), {"ok": False, "error": "upstream_unreachable"})
        resp2 = [r for r in tap2.records if r["dir"] == "resp"][0]
        self.assertIsNone(resp2["upstream_status"])
        self.assertEqual(resp2["body"], {"ok": False, "error": "upstream_unreachable"})
        # cero con cuerpo vacio: se simula el cierre sin linea de estado
        tap3 = tap_mod.Tap(1, clock=_clock())
        tap3._forward = lambda *a, **k: (0, b"", 0)
        tap3.start()
        try:
            _request(tap3.port, "GET", "/poll?peer=server")
        finally:
            tap3.stop()
        resp3 = [r for r in tap3.records if r["dir"] == "resp"][0]
        self.assertEqual(resp3["upstream_status"], 0)
        self.assertIs(type(resp3["upstream_status"]), int)
        self.assertIn(resp3["body"], ("", None))
        # nunca booleano
        for r in (resp, resp2, resp3):
            self.assertIsNot(type(r["upstream_status"]), bool)

    def test_intercept_p2_visible_como_inyeccion_del_tap(self):
        with _Upstream(_ok_handler()) as up:
            tap = tap_mod.Tap(up.port, clock=_clock()).start()
            try:
                tap.intercept_first_result()
                status, data = _request(tap.port, "POST", "/result",
                                        body=b'{"op_id":"op-1","dup":false}')
            finally:
                tap.stop()
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data), {"ok": True})
        resp = [r for r in tap.records if r["dir"] == "resp"][0]
        self.assertIsNone(resp["upstream_status"])
        self.assertEqual(resp.get("injected_by"), "tap")


class SceneDelTests(unittest.TestCase):
    LINE = ("10:00:01.000 [DSBX] DSBX_SCENE_DEL frame=10 lid=obj-01 net=1:2 "
            "signal_ref=1 signal_pending=0 signal_by_netid=1 "
            "deleted_confirmed=1 delete_failed=0 confirm_tick_ms=123.5")

    def test_ancla_y_medianoche_y_varios_logs(self):
        rows = live.parse_scene_del_lines([self.LINE], 5000.0, 36000.0)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["t_ms"], 6000.0)
        self.assertEqual(rows[0]["lid"], "obj-01")
        self.assertEqual(rows[0]["net_high"], 1)
        self.assertEqual(rows[0]["net_low"], 2)
        # medianoche: linea a las 00:00:01 con ancla 23:59:59 -> +2 s
        line2 = self.LINE.replace("10:00:01.000", "00:00:01.000")
        rows2 = live.parse_scene_del_lines([line2], 5000.0, 86399.0)
        self.assertAlmostEqual(rows2[0]["t_ms"], 7000.0)
        # varios logs se juntan y ordenan
        with tempfile.TemporaryDirectory() as tmp:
            p1 = Path(tmp) / "script_a.log"
            p2 = Path(tmp) / "script_b.log"
            p1.write_text(self.LINE + "\n", encoding="utf-8")
            p2.write_text(line2.replace("00:00:01.000", "10:00:03.000") + "\n",
                          encoding="utf-8")
            rows3 = live.collect_scene_del([p1, p2], 5000.0, 36000.0)
            self.assertEqual(len(rows3), 2)
            self.assertLess(rows3[0]["t_ms"], rows3[1]["t_ms"])
        # negativa: linea sin marca no entra
        self.assertEqual(live.parse_scene_del_lines(["ruido"], 0.0, 0.0), [])


class ManifestTests(unittest.TestCase):
    def _parts(self):
        return [(n, float(i * 1000), float((i + 1) * 1000 - 1))
                for i, n in enumerate(live.PART_ORDER)]

    def test_bloque_f2p_valido_y_negativas(self):
        files = live.oracle_files_sha()
        block = live.build_f2p_block(
            oracle_commit=live.ORACLE_COMMIT, oracle_files=files,
            storage_path="C:/tmp/storage_1", storage_id="storage_1-x",
            parts=self._parts())
        self.assertEqual(block["oracle_commit"], live.ORACLE_COMMIT)
        self.assertEqual(block["witness_follow_ticks"], 3)
        self.assertEqual(block["p2n_variant"], "create_failed_after")
        self.assertEqual([p["name"] for p in block["parts"]], list(live.PART_ORDER))
        self.assertTrue(all(p["storage_id"] == "storage_1-x" for p in block["parts"]))
        with self.assertRaises(ValueError):
            live.build_f2p_block(oracle_commit="0" * 40, oracle_files=files,
                                 storage_path="x", storage_id="y", parts=self._parts())
        bad = self._parts()
        bad[1] = ("P2", 0.0, 500.0)  # solapa con P1
        with self.assertRaises(ValueError):
            live.build_f2p_block(oracle_commit=live.ORACLE_COMMIT, oracle_files=files,
                                 storage_path="x", storage_id="y", parts=bad)


class OrderTests(unittest.TestCase):
    def test_orden_cut_restart(self):
        log = live.OrderLog(_clock())
        log.add_cut("")
        log.add_restart_backend("e" * 32)
        kinds = [r["kind"] for r in log.rows]
        self.assertEqual(kinds, ["cut", "restart"])
        self.assertLess(log.rows[0]["t_ms"], log.rows[1]["t_ms"])
        self.assertEqual(log.rows[0]["data"]["target"], "backend")
        # restart de servidor con su t_ms anterior explicito (R-53)
        log2 = live.OrderLog(_clock())
        log2.add_restart_server("f" * 32, 42.0)
        self.assertEqual(log2.rows[0]["t_ms"], 42.0)
        self.assertEqual(log2.rows[0]["data"]["target"], "server")
        # negativa: sin cut previo, el orden seria otro
        self.assertNotEqual(kinds[0], "restart")


class FixtureTests(unittest.TestCase):
    def test_escena2_igual_a_la_del_oraculo(self):
        nueva = json.loads((DEV / "fixtures" / "escena-f2p-2.json").read_text(encoding="utf-8"))
        oracle = json.loads((QA / "fixtures" / "f2p_scene2.json").read_text(encoding="utf-8"))
        self.assertEqual(nueva["doc_id"], oracle["doc_id"])
        self.assertEqual(len(nueva["entities"]), len(oracle["entities"]))
        for a, b in zip(nueva["entities"], oracle["entities"]):
            for key in ("id", "kind", "cls", "x", "z", "yaw"):
                self.assertEqual(a[key], b[key], key)
        for field in ("schema", "doc_id", "name", "map", "ambiente", "entities",
                      "cameras", "next"):
            self.assertIn(field, nueva)
        # negativa: doc_id distinto romperia R-61
        self.assertNotEqual(nueva["doc_id"], "d-00000000")

    def test_variante_p2n(self):
        doc = json.loads((DEV / "fixtures" / "escena-f2p-neg-1.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["doc_id"], "d-7c19e2a5")
        self.assertGreaterEqual(len(doc["entities"]), 2)
        catalog = json.loads((DEV / "fixtures" / "catalog-m1.json").read_text(encoding="utf-8"))
        first = doc["entities"][0]
        self.assertIn(first["cls"], catalog["classes"][first["kind"]])


class R2Tests(unittest.TestCase):
    def test_r2_01_oraculo_recongelado(self):
        self.assertEqual(live.ORACLE_COMMIT,
                         "75ecb097eb28467367ba1e20014eb09c3c491950")
        self.assertIn("75ecb097eb28467367ba1e20014eb09c3c491950",
                      Path(live.__file__).read_text(encoding="utf-8").splitlines()[5])
        # En subproceso limpio, como el gate: en este proceso otros tests
        # ya cargaron el oraculo y el guard lo marcaria preloaded.
        import subprocess as _sp
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "check_oracle.py"
            script.write_text(
                "import json, sys\n"
                "sys.path.insert(0, %r)\n"
                "import f2p_partida\n"
                "print(json.dumps(f2p_partida.check_oracle()))\n"
                % str(QA / "live"), encoding="utf-8")
            out = _sp.run([sys.executable, "-B", str(script)],
                          capture_output=True, text=True, encoding="utf-8",
                          cwd=str(DEV))
            self.assertEqual(out.returncode, 0, out.stderr)
            chk = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertTrue(chk.get("ok"), chk)

    def _fake_ctx(self, hellos=()):
        import threading as _th
        bridge = types.SimpleNamespace(
            cv=_th.RLock(),
            events=[{"ev": "hello", "http": 200, "ok": True, "peer": "server",
                     "inst": "b" * 32, "t_ms": float(t)} for t in hellos],
            failure=None)
        state = {"t": 5000.0}

        def now():
            state["t"] += 10.0
            return state["t"]

        ctx = types.SimpleNamespace(bridge=bridge, now_h_ms=now)
        return ctx, state

    def test_r2_02_restart_epoch_y_orden(self):
        ctx, state = self._fake_ctx(hellos=(100.0,))
        records = [
            {"req_id": 0, "t_ms": 90.0, "dir": "req", "path": "/hello",
             "body": {"peer": "server", "inst": "a" * 32, "epoch": "1" * 32}},
            {"req_id": 0, "t_ms": 100.0, "dir": "resp", "path": "/hello",
             "http": 200, "body": {"ok": True, "session": "s1"}},
        ]
        tap = types.SimpleNamespace(records=records)
        log = live.OrderLog(ctx.now_h_ms)
        seen = []

        def hook(action):
            seen.append(action)
            if action == "start":
                t_new = state["t"] + 100.0
                records.append(
                    {"req_id": 1, "t_ms": t_new - 1.0, "dir": "req",
                     "path": "/hello",
                     "body": {"peer": "server", "inst": "c" * 32,
                              "epoch": "2" * 32}})
                records.append(
                    {"req_id": 1, "t_ms": t_new, "dir": "resp",
                     "path": "/hello", "http": 200,
                     "body": {"ok": True, "session": "s2"}})
                ctx.bridge.events.append(
                    {"ev": "hello", "http": 200, "ok": True, "peer": "server",
                     "inst": "d" * 32, "t_ms": t_new})

        camp = live.Campaign(ctx, {"backend": None}, tap, log, mode="seco",
                             hello_timeout_s=5.0, restart_hook=hook)
        camp.current_epoch = "1" * 32
        epoch = camp._restart_server()
        self.assertEqual(seen, ["stop", "start"])
        self.assertEqual(epoch, "2" * 32)
        self.assertEqual(camp.current_epoch, "2" * 32)
        self.assertNotEqual(camp.current_epoch, "")
        restart = [r for r in log.rows if r["kind"] == "restart"][0]
        self.assertEqual(restart["data"], {"target": "server", "epoch": "2" * 32})
        hellos = live.tap_product_hellos(records)
        first_after = [h for h in hellos if h["t_ms"] > restart["t_ms"]][0]
        self.assertEqual(restart["data"]["epoch"], first_after["epoch"])
        self.assertEqual(live.tap_unmatched_req_ids(records), set())

    def test_r2_02_primera_vida_sin_saludo_corta_inconcluso(self):
        ctx, _state = self._fake_ctx(hellos=())
        tap = types.SimpleNamespace(records=[])
        log = live.OrderLog(ctx.now_h_ms)
        camp = live.Campaign(ctx, {"backend": None}, tap, log, mode="seco",
                             hello_timeout_s=0.2, restart_hook=lambda a: None)
        parts = camp.run()
        self.assertIn("INCONCLUSO", camp.inconcluso)
        self.assertIn("saludo", camp.inconcluso)
        self.assertEqual([p[0] for p in parts], list(live.PART_ORDER))
        self.assertEqual(camp.current_epoch, "")

    def test_r2_03_censo_uid_en_textos(self):
        import wire as _wire
        captured = {}

        def fake_issue(ctx, peer, verb, payload, timeout_ms=None):
            captured["payload"] = payload
            return types.SimpleNamespace(status="rejected", reason="x", payload={})

        old = live.f03_common.issue_one
        live.f03_common.issue_one = fake_issue
        try:
            with self.assertRaises(live.ProbeJobError):
                live.probe_census(None, "tag1", director_uid="uid-dir-1")
        finally:
            live.f03_common.issue_one = old
        data = _wire.unpack_payload(captured["payload"])
        self.assertEqual(data["str"].get("director_uid"), "uid-dir-1")
        self.assertEqual(data["num"].get("include_director_b"), 1.0)

    def test_r2_03_director_uid_players_n(self):
        def make(payloads):
            calls = {"n": 0}

            def fake_issue(ctx, peer, verb, payload, timeout_ms=None):
                idx = min(calls["n"], len(payloads) - 1)
                calls["n"] += 1
                return types.SimpleNamespace(
                    status="done", reason="", payload=payloads[idx])
            return fake_issue

        old = live.f03_common.issue_one
        try:
            live.f03_common.issue_one = make(
                [{"str": {"director_uid": "uid-9"}, "num": {"players_n": 1.0}, "rows": []}])
            self.assertEqual(live.probe_director_uid(None, timeout_ms=1000), "uid-9")
            live.f03_common.issue_one = make(
                [{"str": {}, "num": {"players_n": 2.0}, "rows": []},
                 {"str": {"director_uid": "uid-7"}, "num": {"players_n": 1.0}, "rows": []}])
            self.assertEqual(live.probe_director_uid(None, timeout_ms=5000), "uid-7")
            live.f03_common.issue_one = make(
                [{"str": {"director_uid": "uid-x"}, "num": {}, "rows": []}])
            self.assertEqual(live.probe_director_uid(None, timeout_ms=1000), "")
            live.f03_common.issue_one = make(
                [{"str": {}, "num": {"players_n": 0.0}, "rows": []}])
            with self.assertRaises(RuntimeError):
                live.probe_director_uid(None, timeout_ms=200)
        finally:
            live.f03_common.issue_one = old

    def test_r2_04_sin_rutas_de_willy_fuera_de_comentarios(self):
        import re
        # Rutas de una maquina concreta fuera de comentarios: el perfil de usuario de Windows de cualquier
        # usuario (con lo que cuelga de el), C:\tmp y el Python de Willy. Patron generico, para no escribir aqui
        # ninguna ruta personal (repo publico).
        bad = re.compile(r"[a-z]:[\\/]+users[\\/]+|c:[\\/]+tmp[\\/]|c:[\\/]+python314", re.IGNORECASE)
        files = [QA / "live" / "run_f2p_partida.ps1",
                 QA / "live" / "f2p_server_ctl.ps1",
                 QA / "live" / "f2p_partida.py",
                 QA / "live" / "f2p_paquete.py",
                 QA / "live" / "f2p_fases.py"]
        for path in files:
            self.assertTrue(path.is_file(), str(path))
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.lstrip().startswith("#"):
                    continue
                self.assertIsNone(bad.search(line), "%s: %s" % (path, line))

    def test_r2_04_paquete_manifest_sha256(self):
        paquete = _load("f2p_paquete_test", QA / "live" / "f2p_paquete.py")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "origen.txt"
            src.write_text("contenido", encoding="utf-8")
            manifest = paquete.build_package(Path(tmp) / "pkg", [(src, "origen.txt")])
            row = manifest["files"][0]
            self.assertFalse(row["missing"])
            self.assertEqual(row["origin"], str(src.resolve()))
            import hashlib as _hl
            self.assertEqual(row["sha256"], _hl.sha256(b"contenido").hexdigest())
            self.assertTrue((Path(tmp) / "pkg" / "manifest.json").is_file())
            orders = paquete.transfer_orders()
            self.assertTrue(any(o.startswith("scp ") for o in orders))
            self.assertTrue(any(o.startswith("ssh ") and "/" in o for o in orders))

    def test_r2_05_dry_run_ordenes_y_modo_real(self):
        orders = live.dry_run_orders(maquina="portatil", cliente="operador",
                                     work_root="trabajo")
        text = "\n".join(orders)
        self.assertIn("WMI servidor", text)
        self.assertIn("scp ", text)
        self.assertIn("ssh ", text)
        self.assertIn("StopBoth", text)
        self.assertIn("ESPERA_OPERADOR", text)
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("Invoke-CimMethod", ps1)
        self.assertIn("Win32_Process", ps1)
        self.assertIn("DayZServer_x64.exe", ps1)
        self.assertIn("ESPERA_OPERADOR.txt", ps1)
        self.assertIn("portatil: sin lease", ps1)
        self.assertTrue(callable(live.make_real_restart_hook))

    def test_r2_06_fases_reanudar_y_desde(self):
        fases = _load("f2p_fases_test", QA / "live" / "f2p_fases.py")
        with tempfile.TemporaryDirectory() as tmp:
            store = fases.FaseStore(tmp)
            entradas = {f: {"k": "1"} for f in fases.PHASES}
            store.mark("paquete", "ok", entradas={"pbo": "a"})
            store.mark("subida", "ok", entradas={"pkg": "a"})
            store.mark("partida", "fallida", entradas={"k": "1"})
            entradas2 = dict(entradas)
            entradas2["paquete"] = {"pbo": "a"}
            entradas2["subida"] = {"pkg": "a"}
            plan = fases.plan_fases(store, entradas2, reanudar=True)
            self.assertNotIn("paquete", plan)
            self.assertNotIn("subida", plan)
            self.assertIn("partida", plan)
            entradas3 = dict(entradas2)
            entradas3["paquete"] = {"pbo": "CAMBIADO"}
            plan3 = fases.plan_fases(store, entradas3, reanudar=True)
            self.assertIn("paquete", plan3)
            self.assertIn("partida", plan3)
            self.assertEqual(fases.plan_fases(store, entradas3, desde="gate"), ["gate"])
            store.mark_part("en_curso", "P4b")
            store2 = fases.FaseStore(tmp)
            self.assertEqual(store2.data["partida_detalle"]["parte_en_curso"], "P4b")


class R2bTests(unittest.TestCase):
    LINE = SceneDelTests.LINE

    def test_r2b_f2_dry_run_dos_mods_config_y_mision(self):
        orders = live.dry_run_orders(maquina="portatil", cliente="lanzar",
                                     work_root="trabajo", mission_b1="b1")
        text = "\n".join(orders)
        self.assertIn("@DayZSandbox", text)
        self.assertIn("@DayZSandbox_QA", text)
        self.assertIn("pbo\\@DayZSandbox;", text)
        self.assertIn("-config=", text)
        self.assertIn("serverDZ.cfg", text)
        self.assertIn("dayzOffline.chernarusplus", text)
        self.assertIn("-freezecheck", text)
        self.assertIn("-window", text)
        srv = [o for o in orders if o.startswith("WMI servidor")][0]
        cli = [o for o in orders if o.startswith("WMI cliente")][0]
        for line in (srv, cli):
            self.assertIn("@DayZSandbox", line)
            self.assertIn("@DayZSandbox_QA", line)
        self.assertIn("-mod=", srv)
        self.assertIn("-mod=", cli)

    def test_r2b_f2_paquete_carpetas_addons_y_sha(self):
        paquete = _load("f2p_paquete_r2b", QA / "live" / "f2p_paquete.py")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "pbos"
            src.mkdir()
            (src / "DayZSandbox.pbo").write_bytes(b"producto")
            (src / "DayZSandbox_QA.pbo").write_bytes(b"sonda")
            items = paquete.default_items(QA / "live", pbo_dir=str(src))
            names = [n for _o, n in items]
            self.assertIn("pbo/@DayZSandbox/addons/DayZSandbox.pbo", names)
            self.assertIn("pbo/@DayZSandbox_QA/addons/DayZSandbox_QA.pbo", names)
            manifest = paquete.build_package(Path(tmp) / "pkg", items)
            rows = {r["file"]: r for r in manifest["files"]}
            import hashlib as _hl
            row = rows["pbo/@DayZSandbox_QA/addons/DayZSandbox_QA.pbo"]
            self.assertFalse(row["missing"])
            self.assertEqual(row["sha256"], _hl.sha256(b"sonda").hexdigest())
            self.assertTrue((Path(tmp) / "pkg" / "pbo" / "@DayZSandbox" / "addons" / "DayZSandbox.pbo").is_file())
            self.assertTrue((Path(tmp) / "pkg" / "pbo" / "@DayZSandbox_QA" / "addons" / "DayZSandbox_QA.pbo").is_file())

    def test_r2b_f2_ps1_lineas_del_modelo(self):
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("@DayZSandbox_QA", ps1)
        self.assertIn("-freezecheck", ps1)
        self.assertIn("serverDZ.cfg", ps1)
        self.assertIn("dayzOffline.chernarusplus", ps1)
        self.assertIn("-window -x=1280 -y=720 -noPause", ps1)
        self.assertIn("addons", ps1)
        self.assertNotIn("-mod=@DayZSandbox -port", ps1)
        self.assertNotIn("-server -mod=@DayZSandbox ", ps1)

    def test_r2b_f1_ctl_falla_cerrado(self):
        ctl = (QA / "live" / "f2p_server_ctl.ps1").read_text(encoding="utf-8")
        self.assertNotIn("[void](StopBothOwn)", ctl)
        self.assertIn("exit 2", ctl)
        self.assertIn("exit 3", ctl)
        self.assertIn("EnsureServerPortsFree", ctl)
        self.assertIn("OwnCrashReporters", ctl)
        body = ctl.split("function StopBothOwn")[1].split("if ($Action")[0]
        self.assertIn("CloseOwnCrashReporters", body)
        self.assertIn("Test-OwnAlive $ServerPid $ServerStart", body)
        restart = ctl.split("if ($Action -eq 'restart')")[1].split("if ($Action -eq 'start')")[0]
        self.assertIn("no se arranca nada", restart)
        self.assertLess(restart.index("StopBothOwn"), restart.index("EnsureServerPortsFree"))
        # a un CrashReporter no se le mata nunca
        self.assertNotIn("Stop-Process", ctl)

    def test_r2b_f1_parada_fallida_corta_inconcluso(self):
        ctx, _state = R2Tests()._fake_ctx(hellos=(100.0,))
        tap = types.SimpleNamespace(records=[])
        log = live.OrderLog(ctx.now_h_ms)

        def hook(action):
            raise RuntimeError("ctl rc=2: el servidor propio sigue vivo")

        camp = live.Campaign(ctx, {"backend": None}, tap, log, mode="diag",
                             hello_timeout_s=0.5, restart_hook=hook,
                             director_uid="uid-1", esperar_cliente=True)
        with self.assertRaises(live.ServerHelloTimeout) as cm:
            camp._restart_server()
        self.assertIn("parada", str(cm.exception))

    def test_r2b_f3_scene_del_perfil_real_dos_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            prof = Path(tmp) / "profile-server"
            prof.mkdir()
            line2 = self.LINE.replace("10:00:01.000", "10:00:03.000").replace("lid=obj-01", "lid=obj-02")
            (prof / "script_2026.log").write_text(self.LINE + "\nruido\n", encoding="utf-8")
            (prof / "script_2027.log").write_text(line2 + "\n", encoding="utf-8")
            (prof / "otro.log").write_text(self.LINE + "\n", encoding="utf-8")
            rows = live.collect_scene_del_from_profile(prof, 5000.0, 36000.0)
            self.assertEqual(len(rows), 2)
            self.assertEqual([r["lid"] for r in rows], ["obj-01", "obj-02"])
            self.assertAlmostEqual(rows[0]["t_ms"], 6000.0)
            self.assertAlmostEqual(rows[1]["t_ms"], 8000.0)
        # en seco sigue vacio
        self.assertEqual(live.collect_scene_del([], 5000.0, 36000.0), [])

    def _camp_f4(self, *, client_hello=True, uid="uid-1"):
        ctx, state = R2Tests()._fake_ctx(hellos=(100.0,))
        records = [
            {"req_id": 0, "t_ms": 90.0, "dir": "req", "path": "/hello",
             "body": {"peer": "server", "inst": "a" * 32, "epoch": "1" * 32}},
            {"req_id": 0, "t_ms": 100.0, "dir": "resp", "path": "/hello",
             "http": 200, "body": {"ok": True, "session": "s1"}},
        ]
        tap = types.SimpleNamespace(records=records)
        log = live.OrderLog(ctx.now_h_ms)
        seen = []

        def hook(action):
            seen.append(action)
            if action == "start":
                t_new = state["t"] + 100.0
                records.append({"req_id": 1, "t_ms": t_new - 1.0, "dir": "req", "path": "/hello",
                                "body": {"peer": "server", "inst": "c" * 32, "epoch": "2" * 32}})
                records.append({"req_id": 1, "t_ms": t_new, "dir": "resp", "path": "/hello",
                                "http": 200, "body": {"ok": True, "session": "s2"}})
                ctx.bridge.events.append({"ev": "hello", "http": 200, "ok": True,
                                          "peer": "server", "inst": "d" * 32, "t_ms": t_new})
                if client_hello:
                    ctx.bridge.events.append({"ev": "hello", "http": 200, "ok": True,
                                              "peer": "client", "inst": "e" * 32, "t_ms": t_new})

        camp = live.Campaign(ctx, {"backend": None}, tap, log, mode="diag",
                             hello_timeout_s=2.0, restart_hook=hook,
                             director_uid="uid-1", cliente="lanzar",
                             esperar_cliente=True)
        camp.current_epoch = "1" * 32
        old = live.probe_director_uid
        live.probe_director_uid = lambda ctx_, timeout_ms=1000: uid
        return camp, log, seen, old

    def test_r2b_f4_orden_stopboth_y_cliente_mismo_uid(self):
        camp, log, seen, old = self._camp_f4()
        try:
            epoch = camp._restart_server()
        finally:
            live.probe_director_uid = old
        self.assertEqual(seen, ["stop", "start"])
        self.assertEqual(epoch, "2" * 32)
        restart = [r for r in log.rows if r["kind"] == "restart"][0]
        self.assertEqual(restart["data"], {"target": "server", "epoch": "2" * 32})
        hellos = live.tap_product_hellos(camp.tap.records)
        first_after = [h for h in hellos if h["t_ms"] > restart["t_ms"]][0]
        self.assertEqual(restart["data"]["epoch"], first_after["epoch"])
        clients = [h for h in live.probe_client_hellos(camp.ctx) if h["t_ms"] > restart["t_ms"]]
        self.assertEqual(len(clients), 1)

    def test_r2b_f4_cliente_no_vuelve_o_uid_distinto(self):
        camp, _log, _seen, old = self._camp_f4(client_hello=False)
        try:
            with self.assertRaises(live.ServerHelloTimeout) as cm:
                camp._restart_server()
            self.assertIn("cliente no volvio", str(cm.exception))
        finally:
            live.probe_director_uid = old
        camp2, _log2, _seen2, old2 = self._camp_f4(uid="otro-uid")
        try:
            with self.assertRaises(live.ServerHelloTimeout) as cm2:
                camp2._restart_server()
            self.assertIn("otro UID", str(cm2.exception))
        finally:
            live.probe_director_uid = old2


class R2cTests(unittest.TestCase):
    def test_r2c_1_cliente_diag_es_dayzdiag_sin_server(self):
        exe, args, adopt = live.client_launch(
            "diag", dayz_dir="C:/DayZ", mods="M1;M2", client_profile="P/client")
        self.assertIn("DayZDiag_x64.exe", exe)
        self.assertNotIn("DayZ_BE", exe)
        self.assertNotIn("-server", args)
        self.assertFalse(adopt)
        orders = live.dry_run_orders(maquina="portatil", cliente="lanzar",
                                     work_root="trabajo", build="diag",
                                     package_dir="C:/dsbx-m1")
        text = "\n".join(orders)
        cli = [o for o in orders if o.startswith("WMI cliente")][0]
        self.assertIn("DayZDiag_x64.exe", cli)
        self.assertNotIn("DayZ_BE.exe", cli)

    def test_r2c_1_cliente_retail_be_y_adopcion(self):
        exe, args, adopt = live.client_launch(
            "retail", dayz_dir="C:/DayZ", mods="M1;M2", client_profile="P/client")
        self.assertIn("DayZ_BE.exe", exe)
        self.assertTrue(args.startswith("0 1 1 -exe DayZ_x64.exe"))
        self.assertTrue(adopt)
        orders = live.dry_run_orders(maquina="portatil", cliente="lanzar",
                                     work_root="trabajo", build="retail",
                                     package_dir="C:/dsbx-m1")
        text = "\n".join(orders)
        self.assertIn("DayZ_x64 adoptado por procedencia", text)
        self.assertIn("0 1 1 -exe DayZ_x64.exe", text)
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("DayZDiag_x64.exe", ps1)
        self.assertIn("0 1 1 -exe DayZ_x64.exe", ps1)
        self.assertIn("Adopt-DayZX64", ps1)
        self.assertIn("Start-ClientOwn", ps1)
        ctl = (QA / "live" / "f2p_server_ctl.ps1").read_text(encoding="utf-8")
        self.assertIn("Adopt-DayZX64", ctl)
        self.assertIn("DayZ_x64 con procedencia", ctl)

    def test_r2c_2_mision_de_la_copia_en_ordenes_y_ps1(self):
        orders = live.dry_run_orders(maquina="portatil", cliente="lanzar",
                                     work_root="trabajo", build="diag",
                                     package_dir="C:/dsbx-m1", mission_b1="b1")
        text = "\n".join(orders)
        self.assertIn("trabajo\\mission\\server\\serverDZ.cfg", text)
        self.assertIn("trabajo\\mission\\mpmissions\\dayzOffline.chernarusplus", text)
        self.assertIn("copia nueva de la b1", text)
        self.assertNotIn("b1\\server\\serverDZ.cfg", text)
        self.assertNotIn("b1\\mpmissions", text)
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("Copy-FreshMission $MissionB1 $missionDir", ps1)
        self.assertIn("Join-Path $missionDir 'server\\serverDZ.cfg'", ps1)
        self.assertIn("Join-Path $missionDir 'mpmissions\\dayzOffline.chernarusplus'", ps1)

    def test_r2c_4_pbo_sin_relleno_y_del_paquete(self):
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertNotIn("Set-Content -Path $probePbo -Value", ps1)
        self.assertIn("falta la sonda", ps1)
        self.assertIn("PBO del paquete (sin construir)", ps1)
        paquete = _load("f2p_paquete_r2c", QA / "live" / "f2p_paquete.py")
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "pbos"
            src.mkdir()
            (src / "DayZSandbox.pbo").write_bytes(b"producto")
            (src / "DayZSandbox_QA.pbo").write_bytes(b"sonda")
            items = paquete.default_items(QA / "live", pbo_dir=str(src))
            manifest = paquete.build_package(Path(tmp) / "pkg", items)
            pkg = Path(tmp) / "pkg"
            self.assertEqual(live.check_package_manifest(pkg), [])
            (pkg / "pbo" / "@DayZSandbox_QA" / "addons" / "DayZSandbox_QA.pbo").write_bytes(b"otro")
            problems = live.check_package_manifest(pkg)
            self.assertTrue(any("DayZSandbox_QA.pbo" in p for p in problems), problems)

    def test_r2c_3_manifest_problemas_y_sin_git_en_portatil(self):
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "pkg"
            pkg.mkdir()
            self.assertTrue(live.check_package_manifest(pkg))
            (pkg / "manifest.json").write_text(
                json.dumps({"files": [{"file": "x.txt", "sha256": "0" * 64,
                                       "missing": False}]}), encoding="utf-8")
            (pkg / "x.txt").write_text("hola", encoding="utf-8")
            problems = live.check_package_manifest(pkg)
            self.assertTrue(any("x.txt" in p for p in problems), problems)
            self.assertTrue(any("PBO" in p for p in problems), problems)
        orders = live.dry_run_orders(maquina="portatil", cliente="lanzar",
                                     work_root="trabajo", build="diag",
                                     package_dir="C:/dsbx-m1")
        self.assertIn("manifest.json", "\n".join(orders))
        self.assertIn("si no casa, no se lanza", "\n".join(orders))
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("Test-PackageManifest $PackageDir", ps1)
        self.assertIn("Get-FileHash", ps1)

    def test_r2c_5_ajenos_cualquier_dayz_en_portatil(self):
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("hay DayZ ajenos en el portatil", ps1)
        seg = ps1.split("# R2c-3/5:")[1].split("} else {")[0]
        self.assertIn("Get-Process -Name 'DayZ*'", seg)
        self.assertNotIn("notmatch 'Diag", seg)
        self.assertIn("DayZDiag_x64", "\n".join(live.dry_run_orders(
            maquina="portatil", cliente="lanzar", work_root="t",
            build="diag", package_dir="C:/dsbx-m1")))

    def test_r2c_6_evidencia_bajo_resultsdir(self):
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("$Evidence = $ResultsDir", ps1)
        self.assertIn("Join-Path $PackageDir 'resultados'", ps1)
        orders = live.dry_run_orders(maquina="portatil", cliente="lanzar",
                                     work_root="trabajo", build="diag",
                                     package_dir="C:/dsbx-m1")
        self.assertIn("bajo -ResultsDir", "\n".join(orders))

    def _camp_humo(self, *, client_hello=True):
        ctx, state = R2Tests()._fake_ctx(hellos=(100.0,))
        ctx.bridge.events.append({"ev": "hello", "http": 200, "ok": True,
                                  "peer": "client", "inst": "e" * 32, "t_ms": 100.0})
        records = [
            {"req_id": 0, "t_ms": 90.0, "dir": "req", "path": "/hello",
             "body": {"peer": "server", "inst": "a" * 32, "epoch": "1" * 32}},
            {"req_id": 0, "t_ms": 100.0, "dir": "resp", "path": "/hello",
             "http": 200, "body": {"ok": True, "session": "s1"}},
        ]
        tap = types.SimpleNamespace(records=records)
        log = live.OrderLog(ctx.now_h_ms)

        def hook(action):
            if action == "start":
                t_new = state["t"] + 100.0
                records.append({"req_id": 1, "t_ms": t_new - 1.0, "dir": "req", "path": "/hello",
                                "body": {"peer": "server", "inst": "c" * 32, "epoch": "2" * 32}})
                records.append({"req_id": 1, "t_ms": t_new, "dir": "resp", "path": "/hello",
                                "http": 200, "body": {"ok": True, "session": "s2"}})
                ctx.bridge.events.append({"ev": "hello", "http": 200, "ok": True,
                                          "peer": "server", "inst": "d" * 32, "t_ms": t_new})
                if client_hello:
                    ctx.bridge.events.append({"ev": "hello", "http": 200, "ok": True,
                                              "peer": "client", "inst": "f" * 32, "t_ms": t_new})

        camp = live.Campaign(ctx, {"backend": None}, tap, log, mode="diag",
                             hello_timeout_s=2.0, restart_hook=hook,
                             cliente="lanzar", esperar_cliente=True)
        old = live.probe_director_uid
        live.probe_director_uid = lambda ctx_, timeout_ms=1000: "uid-1"
        return camp, old

    def test_r2c_7_humo_pasos_orden_y_mismo_uid(self):
        camp, old = self._camp_humo()
        try:
            steps = live.run_humo_real_steps(camp)
        finally:
            live.probe_director_uid = old
        self.assertEqual([s["paso"] for s in steps], [
            "hello_producto_y_sonda_primera_vida",
            "hello_peer_cliente_primera_vida",
            "uid_por_per_status",
            "reinicio_f4_saludos_y_mismo_uid"])
        self.assertTrue(all(s["estado"] == "ok" for s in steps), steps)
        self.assertTrue(all(s["fin"] for s in steps))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "humo_pasos.json"
            live.write_humo_pasos(out, steps)
            doc = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(doc["ok"])
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$Humo", ps1)
        self.assertIn("humo.json", ps1)
        self.assertIn("cierre_wm_close_pid_propios", ps1)
        orders = live.dry_run_orders(maquina="portatil", cliente="lanzar",
                                     work_root="trabajo", build="diag",
                                     package_dir="C:/dsbx-m1", humo=True)
        self.assertIn("humo.json", "\n".join(orders))
        self.assertIn("sin oraculo ni partida", "\n".join(orders))

    def test_r2c_7_humo_falla_si_el_cliente_no_vuelve(self):
        camp, old = self._camp_humo(client_hello=False)
        camp.hello_timeout_s = 0.3
        try:
            with self.assertRaises(live.ServerHelloTimeout):
                live.run_humo_real_steps(camp)
        finally:
            live.probe_director_uid = old


class R2dTests(unittest.TestCase):
    """24-nov, partida del portátil: en modo real el orquestador buscaba `<work>\\probe.pbo`, que no existe, y se caía
    tras arrancar el servidor y el cliente. Ahora recibe los PBO por --pbo y --product-pbo y no arranca sin ellos."""

    class _Stop(Exception):
        pass

    def _stub_ctx(self, seen):
        test = self

        class _Ctx:
            def __init__(self, *a, **kw):
                seen["args"] = kw.get("args")
                raise test._Stop()
        return _Ctx

    def test_r2d_parser_admite_pbo_y_product_pbo(self):
        args = live.build_parser().parse_args(["--build", "diag", "--mode", "diag",
                                               "--pbo", "sonda.pbo", "--product-pbo", "producto.pbo"])
        self.assertEqual(args.pbo, "sonda.pbo")
        self.assertEqual(args.product_pbo, "producto.pbo")

    def test_r2d_real_sin_pbo_falla_cerrado_antes_de_la_parte(self):
        seen = {}
        old_ctx, old_chk = live.f03_common.PartContext, live.check_oracle
        live.f03_common.PartContext = self._stub_ctx(seen)
        live.check_oracle = lambda: {"ok": True, "problems": []}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(RuntimeError) as cm:
                    live.run_campaign(build="diag", evidence_base=Path(tmp) / "ev", mode="diag",
                                      work_root=Path(tmp) / "w")
            self.assertIn("PBO", str(cm.exception))
            self.assertNotIn("args", seen)
        finally:
            live.f03_common.PartContext, live.check_oracle = old_ctx, old_chk

    def test_r2d_real_usa_los_pbo_dados(self):
        seen = {}
        old_ctx, old_chk = live.f03_common.PartContext, live.check_oracle
        live.f03_common.PartContext = self._stub_ctx(seen)
        live.check_oracle = lambda: {"ok": True, "problems": []}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                sonda = Path(tmp) / "DayZSandbox_QA.pbo"
                prod = Path(tmp) / "DayZSandbox.pbo"
                sonda.write_bytes(b"sonda")
                prod.write_bytes(b"producto")
                with self.assertRaises(self._Stop):
                    live.run_campaign(build="diag", evidence_base=Path(tmp) / "ev", mode="diag",
                                      work_root=Path(tmp) / "w", probe_pbo=str(sonda),
                                      product_pbo=str(prod))
                self.assertEqual(seen["args"].pbo, str(sonda))
                self.assertEqual(seen["args"].product_pbo, str(prod))
        finally:
            live.f03_common.PartContext, live.check_oracle = old_ctx, old_chk

    def test_r2d_lanzador_pasa_los_pbo_al_orquestador(self):
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("'--pbo', $probePbo, '--product-pbo', $productPbo", ps1)


class R2eTests(unittest.TestCase):
    """24-nov, segundo intento del portátil: el mod de producto no saludaba («[DSBX] config status=missing»), porque en
    modo real nadie escribía `dsbx_peer.json` en los perfiles. Ahora se escribe con `app/tools/peer_config.py` por
    subproceso, apuntando al tap."""

    def test_r2e_escribe_dsbx_peer_json_en_los_dos_perfiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "w"
            work.mkdir()
            srv, cli = Path(tmp) / "profile-server", Path(tmp) / "profile-client"
            key = "k" * 32
            live.write_product_peer_configs(work, key, 23456, (srv, cli))
            for prof in (srv, cli):
                cfg = json.loads((prof / "dsbx_peer.json").read_text(encoding="utf-8"))
                self.assertEqual(cfg, {"url": "http://127.0.0.1:23456/", "key": key})

    def test_r2e_sin_perfil_falla_cerrado(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                live.write_product_peer_configs(Path(tmp), "k" * 32, 23456, ("", None))

    def test_r2e_run_campaign_y_humo_escriben_la_config_en_modo_real(self):
        src = Path(live.__file__).read_text(encoding="utf-8")
        self.assertGreaterEqual(src.count("write_product_peer_configs(work, backend.peer_key, tap.port"), 2)


class R2fTests(unittest.TestCase):
    """24-nov: comprobación previa del portátil, sin DayZ (dos tandas fallaron por el montaje)."""

    class _Backend:
        def __init__(self, *a, **kw):
            self.peer_key = "p" * 32
            self.bridge_port = 34567

        def start(self):
            return self

        def stop(self):
            pass

    class _Tap:
        def __init__(self, *a, **kw):
            self.port = 45678

        def start(self):
            return self

        def stop(self):
            pass

    def _run(self, tmp, *, pbos=True):
        old = (live.BackendProc, live.Tap, live.check_oracle)
        live.BackendProc, live.Tap = self._Backend, self._Tap
        live.check_oracle = lambda: {"ok": True, "problems": []}
        try:
            sonda = Path(tmp) / "DayZSandbox_QA.pbo"
            prod = Path(tmp) / "DayZSandbox.pbo"
            if pbos:
                sonda.write_bytes(b"s")
                prod.write_bytes(b"p")
            srv, cli = Path(tmp) / "profile-server", Path(tmp) / "profile-client"
            return live.run_comprobacion(work_root=Path(tmp) / "w", results_dir=Path(tmp) / "res",
                                         server_profile=srv, client_profile=cli,
                                         probe_pbo=str(sonda), product_pbo=str(prod), ports=())
        finally:
            live.BackendProc, live.Tap, live.check_oracle = old

    def test_r2f_globals_a_cero_con_el_formato_real(self):
        real = ('<var name="AnimalMaxCount" type="0" value="200"/>\n'
                '<var name="ZombieMaxCount" type="0" value="1000"/>\n')
        cero = real.replace('value="200"', 'value="0"').replace('value="1000"', 'value="0"')
        self.assertFalse(live.globals_a_cero(real))
        self.assertTrue(live.globals_a_cero(cero))

    def test_r2f_lanzador_pone_a_cero_con_type_en_medio(self):
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn('(name="ZombieMaxCount"[^>]*?value=")\\d+(")', ps1)
        self.assertIn('(name="AnimalMaxCount"[^>]*?value=")\\d+(")', ps1)

    def test_r2f_comprobacion_sin_pbo_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, checks = self._run(tmp, pbos=False)
            byid = {c["id"]: c["ok"] for c in checks}
            self.assertFalse(ok)
            self.assertFalse(byid["pbo_sonda"])
            self.assertFalse(byid["pbo_producto"])
            self.assertTrue((Path(tmp) / "res" / "comprobacion.json").is_file())

    def test_r2f_comprobacion_escribe_valida_y_retira_dsbx_peer(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, checks = self._run(tmp)
            byid = {c["id"]: c["ok"] for c in checks}
            self.assertTrue(byid["backend_y_tap"])
            self.assertTrue(byid["dsbx_peer_profile-server"])
            self.assertTrue(byid["dsbx_peer_profile-client"])
            for prof in ("profile-server", "profile-client"):
                self.assertFalse((Path(tmp) / prof / "dsbx_peer.json").exists())


class _FakeBusyProbe:
    """Sonda falsa con busy real: un recurso ocupado rechaza el arranque
    y job_free rechaza mientras el trabajo no es terminal."""

    RES = {"per_census_start": "per_census", "per_witness_start": "per_witness"}

    def __init__(self, polls_to_terminal=3, busy_starts=0):
        self.polls_to_terminal = int(polls_to_terminal)
        self.busy_starts = int(busy_starts)
        self.held = {}
        self.jobs = {}
        self.seq = 0
        self.calls = []

    def issue(self, ctx, peer, verb, payload=None, timeout_ms=None, **kw):
        import wire as _wire
        data = _wire.unpack_payload(payload) if payload else {"str": {}, "num": {}, "rows": []}
        strs = data.get("str") or {}
        if verb in self.RES:
            if self.busy_starts > 0:
                self.busy_starts -= 1
                self.calls.append((verb, "busy"))
                return types.SimpleNamespace(status="rejected", reason="busy", payload={})
            res = self.RES[verb]
            if res in self.held:
                self.calls.append((verb, "busy"))
                return types.SimpleNamespace(status="rejected", reason="busy", payload={})
            self.seq += 1
            job = "job-%d" % self.seq
            self.jobs[job] = {"resource": res, "polls": 0, "freed": False}
            self.held[res] = job
            self.calls.append((verb, "done"))
            return types.SimpleNamespace(
                status="done", reason="",
                payload={"str": {"job": job, "state": "running"}, "num": {}, "rows": []})
        if verb == "job_read":
            job = strs.get("job") or ""
            rec = self.jobs[job]
            rec["polls"] += 1
            state = "done" if rec["polls"] >= self.polls_to_terminal else "running"
            self.calls.append((verb, state))
            return types.SimpleNamespace(
                status="done", reason="",
                payload={"str": {"job": job, "state": state},
                         "num": {"rows_total_n": 1.0, "pages_n": 1.0},
                         "rows": [{"net_id": "1:2"}]})
        if verb == "job_free":
            job = strs.get("job") or ""
            rec = self.jobs[job]
            if rec["polls"] < self.polls_to_terminal:
                self.calls.append((verb, "busy"))
                return types.SimpleNamespace(status="rejected", reason="busy", payload={})
            rec["freed"] = True
            self.held.pop(rec["resource"], None)
            self.calls.append((verb, "done"))
            return types.SimpleNamespace(
                status="done", reason="",
                payload={"str": {"job": job, "freed": "1"}, "num": {}, "rows": []})
        return types.SimpleNamespace(status="done", reason="", payload={"str": {}, "num": {}, "rows": []})


class R2gTests(unittest.TestCase):
    def _with_probe(self, probe, fn):
        old = live.f03_common.issue_one
        live.f03_common.issue_one = probe.issue
        try:
            return fn()
        finally:
            live.f03_common.issue_one = old

    def test_r2g_sonda_ciclo_serial_sin_busy(self):
        probe = _FakeBusyProbe(polls_to_terminal=3)
        def go():
            _o1, rows1 = live.probe_census(None, "P1:base")
            _o2, rows2 = live.probe_census(None, "P2:post")
            return rows1, rows2
        rows1, rows2 = self._with_probe(probe, go)
        self.assertEqual(len(rows1), 1)
        self.assertEqual(len(rows2), 1)
        self.assertEqual(probe.held, {})
        self.assertNotIn(("job_free", "busy"), probe.calls)
        starts = [i for i, c in enumerate(probe.calls) if c[0] == "per_census_start"]
        frees = [i for i, c in enumerate(probe.calls) if c == ("job_free", "done")]
        self.assertEqual(len(starts), 2)
        self.assertLess(frees[0], starts[1])

    def test_r2g_sonda_busy_reintenta_y_tope(self):
        probe = _FakeBusyProbe(polls_to_terminal=1, busy_starts=2)
        _out, rows = self._with_probe(
            probe, lambda: live.probe_census(None, "P1:base"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(probe.calls.count(("per_census_start", "busy")), 2)
        always = _FakeBusyProbe(busy_starts=99)
        def go_always():
            return live._issue_busy_retry(None, "per_census_start", {},
                                          1000, attempts=3, sleep_s=0)
        with self.assertRaises(live.ProbeJobError):
            self._with_probe(always, go_always)

    def test_r2g_testigo_espera_fin_y_libera(self):
        probe = _FakeBusyProbe(polls_to_terminal=3)
        def go():
            out = live.probe_witness(None, "P1:control", window_ms=5000)
            return live.witness_pages(None, out)
        rows = self._with_probe(probe, go)
        self.assertEqual(len(rows), 1)
        self.assertEqual(probe.held, {})
        self.assertNotIn(("job_free", "busy"), probe.calls)

    def test_r2g_censo_imposible_corta_inconcluso(self):
        ctx, state = R2Tests()._fake_ctx(hellos=(100.0,))
        records = [
            {"req_id": 0, "t_ms": 90.0, "dir": "req", "path": "/hello",
             "body": {"peer": "server", "inst": "a" * 32, "epoch": "1" * 32}},
            {"req_id": 0, "t_ms": 100.0, "dir": "resp", "path": "/hello",
             "http": 200, "body": {"ok": True, "session": "s1"}},
        ]
        tap = types.SimpleNamespace(records=records)
        log = live.OrderLog(ctx.now_h_ms)
        camp = live.Campaign(ctx, {"backend": None}, tap, log, mode="seco",
                             hello_timeout_s=2.0, restart_hook=lambda a: None,
                             director_uid="uid-1")
        old_census, old_status = live.probe_census, live.probe_status
        live.probe_census = lambda *a, **k: (_ for _ in ()).throw(
            live.ProbeJobError("per_census_start P1:base: busy tras intentos"))
        live.probe_status = lambda *a, **k: types.SimpleNamespace(
            status="done", reason="", payload={})
        try:
            parts = camp.run()
        finally:
            live.probe_census, live.probe_status = old_census, old_status
        self.assertTrue(camp.inconcluso.startswith("INCONCLUSO"), camp.inconcluso)
        self.assertIn("busy", camp.inconcluso)
        self.assertTrue(any("INCONCLUSO" in n for n in camp.notes))
        self.assertEqual([p[0] for p in parts], list(live.PART_ORDER))

    def test_r2g_reconciliacion_hello_y_poll_tras_reinicio(self):
        records = [
            {"dir": "resp", "path": "/hello", "http": 200, "t_ms": 150.0},
            {"dir": "resp", "path": "/poll", "http": 200, "t_ms": 140.0},
        ]
        tap = types.SimpleNamespace(records=records)
        self.assertFalse(live.wait_backend_reconciled(tap, 100.0, timeout_s=0.3))
        records.append({"dir": "resp", "path": "/poll", "http": 200, "t_ms": 160.0})
        self.assertTrue(live.wait_backend_reconciled(tap, 100.0, timeout_s=0.3))

    def test_r2g_logs_server_y_client_separados(self):
        ps1 = (QA / "live" / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("@($serverProfile, 'server')", ps1)
        self.assertIn("@($clientProfile, 'client')", ps1)
        self.assertIn("Join-Path $logDir $pair[1]", ps1)


class R2hTests(unittest.TestCase):
    """24-nov: en P3 el ajeno va dentro de obj-17, con el net_id del contenedor sacado del censo (brief :250, :311)."""

    DOC = {"entities": [{"id": "obj-17", "kind": "objeto", "cls": "SeaChest", "x": 6140.0, "z": 7676.0}]}

    def test_r2h_obj17_sale_del_censo(self):
        rows = [{"net_id": "0:11", "class_name": "SeaChest", "parent_net_id": "", "pos_x_m": 6140.2, "pos_z_m": 7676.1},
                {"net_id": "0:12", "class_name": "SeaChest", "parent_net_id": "", "pos_x_m": 6150.0, "pos_z_m": 7676.0},
                {"net_id": "0:13", "class_name": "Apple", "parent_net_id": "0:11", "pos_x_m": 6140.0, "pos_z_m": 7676.0}]
        self.assertEqual(live.find_scene_container_net(rows, self.DOC, "obj-17"), "0:11")

    def test_r2h_obj17_ambiguo_o_ausente_da_vacio(self):
        dos = [{"net_id": "0:11", "class_name": "SeaChest", "parent_net_id": "", "pos_x_m": 6140.1, "pos_z_m": 7676.0},
               {"net_id": "0:14", "class_name": "SeaChest", "parent_net_id": "", "pos_x_m": 6140.0, "pos_z_m": 7676.2}]
        self.assertEqual(live.find_scene_container_net(dos, self.DOC, "obj-17"), "")
        self.assertEqual(live.find_scene_container_net([], self.DOC, "obj-17"), "")

    def test_r2h_p3_pasa_el_contenedor_y_no_sigue_sin_ajenos(self):
        src = Path(live.__file__).read_text(encoding="utf-8")
        self.assertIn('{"target_net_id": _obj17}', src)
        self.assertNotIn('"P3 ajenos: %s" % exc)\n', src.replace('raise ProbeJobError("P3 ajenos: %s" % exc)', ""))


class _FakeBackendR2i:
    """Backend falso: devuelve la secuencia de (status, body) programada."""

    def __init__(self, seq):
        self.seq = list(seq)
        self.calls = []
        self.op_states = [{"op_id": "op-9", "state": "observado"}]

    def _next(self, verb, doc_id):
        self.calls.append((verb, doc_id))
        if len(self.seq) > 1:
            return self.seq.pop(0)
        return self.seq[0]

    def apply(self, doc_id):
        return self._next("apply", doc_id)

    def reset(self, doc_id):
        return self._next("reset", doc_id)


class _FakeCreatureProbe:
    """Sonda falsa: censo con las criaturas en posiciones observadas."""

    CREATURE_ROWS = [
        {"net_id": "0:101", "class_name": "Animal_CervusElaphus",
         "parent_net_id": "", "pos_x_m": 6100.0, "pos_z_m": 7700.0},
        {"net_id": "0:102", "class_name": "ZmbM_FarmerFat_Brown",
         "parent_net_id": "", "pos_x_m": 6200.0, "pos_z_m": 7650.0},
    ]

    def __init__(self):
        self.starts = []
        self.jobs = {}
        self.seq = 0

    def issue(self, ctx, peer, verb, payload=None, timeout_ms=None, **kw):
        import wire as _wire
        data = _wire.unpack_payload(payload) if payload else {"str": {}, "num": {}, "rows": []}
        strs = data.get("str") or {}
        nums = data.get("num") or {}
        if verb == "per_census_start":
            self.seq += 1
            job = "job-%d" % self.seq
            tag = strs.get("area_tag") or ""
            self.starts.append({"tag": tag,
                                "center": (nums.get("center_x_m"), nums.get("center_z_m")),
                                "radius": nums.get("radius_m")})
            rows = list(self.CREATURE_ROWS) if tag.endswith(":pre_reset") else []
            self.jobs[job] = rows
            return types.SimpleNamespace(
                status="done", reason="",
                payload={"str": {"job": job, "state": "running"}, "num": {}, "rows": []})
        if verb == "job_read":
            job = strs.get("job") or ""
            return types.SimpleNamespace(
                status="done", reason="",
                payload={"str": {"job": job, "state": "done"},
                         "num": {"rows_total_n": float(len(self.jobs.get(job, []))),
                                 "pages_n": 1.0},
                         "rows": list(self.jobs.get(job, []))})
        if verb == "job_free":
            return types.SimpleNamespace(
                status="done", reason="",
                payload={"str": {"job": strs.get("job") or "", "freed": "1"},
                         "num": {}, "rows": []})
        return types.SimpleNamespace(status="done", reason="",
                                     payload={"str": {}, "num": {}, "rows": []})


class R2iTests(unittest.TestCase):
    """Ronda 2i: formato real de scene_del, 409 catalog_pending y discos por criatura."""

    REAL1 = ("19:36:25.954 SCRIPT       : [DSBX] DSBX_SCENE_DEL tick_ms=120476 "
             "frame=207639 lid=obj-01 net_low=22896 net_high=0 signal_ref_b=0 "
             "signal_pending_b=1 signal_by_netid_b=0 deleted_confirmed_b=0 "
             "delete_failed_b=0 confirm_tick_ms=0")
    REAL2 = ("19:36:25.955 SCRIPT       : [DSBX] DSBX_SCENE_DEL tick_ms=120477 "
             "frame=207640 lid=obj-01 net_low=22896 net_high=0 signal_ref_b=1 "
             "signal_pending_b=1 signal_by_netid_b=1 deleted_confirmed_b=1 "
             "delete_failed_b=0 confirm_tick_ms=120477")

    def test_r2i_1_scene_del_formato_real_y_perfil(self):
        anchor_wall = 19 * 3600.0 + 36 * 60.0 + 25.954
        rows = live.parse_scene_del_lines([self.REAL1, self.REAL2], 100000.0, anchor_wall)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["t_ms"], 100000.0, places=3)
        self.assertEqual(rows[0]["lid"], "obj-01")
        self.assertEqual(rows[0]["frame"], 207639)
        self.assertEqual(rows[0]["net_low"], 22896)
        self.assertEqual(rows[0]["net_high"], 0)
        self.assertEqual(rows[0]["signal_pending_b"], 1)
        self.assertEqual(rows[1]["deleted_confirmed_b"], 1)
        self.assertAlmostEqual(rows[1]["confirm_tick_ms"], 120477.0)
        with tempfile.TemporaryDirectory() as tmp:
            prof = Path(tmp)
            (prof / "script_2026-11-24_19-34-25.log").write_text(
                self.REAL1 + "\n" + self.REAL2 + "\nruido sin marca\n",
                encoding="utf-8")
            got = live.collect_scene_del_from_profile(prof, 100000.0, anchor_wall)
        self.assertEqual(len(got), 2)
        self.assertEqual([r["lid"] for r in got], ["obj-01", "obj-01"])

    def _campaign(self, backend):
        ctx = types.SimpleNamespace(now_h_ms=lambda: 1000.0)
        log = live.OrderLog(ctx.now_h_ms)
        camp = live.Campaign(ctx, {"backend": backend},
                             types.SimpleNamespace(records=[]), log,
                             mode="seco", director_uid="uid-1")
        camp.catalog_sleep_s = 0.0
        return camp

    def test_r2i_2_apply_reintenta_409_catalog_pending(self):
        pending = (409, {"ok": False, "code": "catalog_pending",
                         "msg": "sin catalogo"})
        backend = _FakeBackendR2i([pending, pending, (200, {"ok": True, "op_id": "op-9"})])
        camp = self._campaign(backend)
        body = camp._apply(live.DOC1_ID)
        self.assertEqual(body.get("op_id"), "op-9")
        self.assertEqual(len(backend.calls), 3)

    def test_r2i_2_apply_sin_op_id_corta_inconcluso(self):
        backend = _FakeBackendR2i([(422, {"ok": False, "code": "unknown_class"})])
        camp = self._campaign(backend)
        with self.assertRaises(live.ProbeJobError) as cm:
            camp._apply(live.DOC1_ID)
        self.assertIn("422", str(cm.exception))
        backend2 = _FakeBackendR2i([(400, {"ok": False, "code": "bad_request"})])
        camp2 = self._campaign(backend2)
        with self.assertRaises(live.ProbeJobError):
            camp2._reset(live.DOC1_ID)

    def test_r2i_3_discos_por_criatura_tras_reset(self):
        probe = _FakeCreatureProbe()
        old = live.f03_common.issue_one
        live.f03_common.issue_one = probe.issue
        backend = _FakeBackendR2i([(200, {"ok": True, "op_id": "op-9"})])
        camp = self._campaign(backend)
        try:
            camp._census_tracked("P4a:pre_reset")
            camp._reset_and_census(live.DOC1_ID, "P4a:post_reset")
        finally:
            live.f03_common.issue_one = old
        disks = {s["tag"]: s for s in probe.starts if ":disk:" in s["tag"]}
        ani = disks.get("P4a:post_reset:disk:ani-01")
        zmb = disks.get("P4a:post_reset:disk:zmb-01")
        self.assertIsNotNone(ani, disks)
        self.assertIsNotNone(zmb, disks)
        self.assertEqual(ani["radius"], 120.0)
        self.assertEqual(ani["center"], (6100.0, 7700.0))
        self.assertEqual(zmb["radius"], 60.0)
        self.assertEqual(zmb["center"], (6200.0, 7650.0))
        main = [s for s in probe.starts if s["tag"] == "P4a:post_reset"]
        self.assertEqual(len(main), 1)
        self.assertLess(probe.starts.index(main[0]),
                        probe.starts.index(ani))



class _FakeCreatureProbeR2j(_FakeCreatureProbe):
    """Sonda falsa con las filas de cada censo fijadas por etiqueta."""

    def __init__(self, rows_by_tag):
        super().__init__()
        self.rows_by_tag = rows_by_tag

    def issue(self, ctx, peer, verb, payload=None, timeout_ms=None, **kw):
        out = super().issue(ctx, peer, verb, payload=payload, timeout_ms=timeout_ms, **kw)
        if verb == "per_census_start":
            self.jobs[out.payload["str"]["job"]] = list(self.rows_by_tag.get(self.starts[-1]["tag"], []))
        return out


class R2jTests(unittest.TestCase):
    """Ronda 2j (orquestador): disco por criatura ausente en los censos que juzgan presencia.

    Partida de 9debe9b: el ciervo y el corzo salen del disco de 115 m tras cada apply (F2P-01, F2P-07
    y F2P-09 con census_missing en P2:post, P4b:post_apply y P5:post_apply).
    """

    PRESENCIA = ("P2:post", "P3:pre_reset", "P4a:post_apply1", "P4a:post_apply2",
                 "P4b:post_apply", "P5:post_apply")

    def _campaign(self):
        ctx = types.SimpleNamespace(now_h_ms=lambda: 1000.0)
        log = live.OrderLog(ctx.now_h_ms)
        backend = _FakeBackendR2i([(200, {"ok": True, "op_id": "op-9"})])
        return live.Campaign(ctx, {"backend": backend}, types.SimpleNamespace(records=[]), log,
                             mode="seco", director_uid="uid-1")

    def test_r2j_disco_solo_para_la_criatura_que_falta(self):
        ani, zmb = _FakeCreatureProbe.CREATURE_ROWS
        probe = _FakeCreatureProbeR2j({"P2n:pre_reset": [ani, zmb], "P2:post": [zmb]})
        old = live.f03_common.issue_one
        live.f03_common.issue_one = probe.issue
        camp = self._campaign()
        try:
            camp._census_tracked("P2n:pre_reset")
            camp._census_presence("P2:post")
        finally:
            live.f03_common.issue_one = old
        self.assertEqual([s["tag"] for s in probe.starts],
                         ["P2n:pre_reset", "P2:post", "P2:post:disk:ani-01"])
        self.assertEqual(probe.starts[-1]["radius"], 120.0)
        self.assertEqual(probe.starts[-1]["center"], (6100.0, 7700.0))

    def test_r2j_los_censos_de_presencia_llevan_discos(self):
        import inspect
        src = inspect.getsource(live.Campaign._run_inner)
        for tag in self.PRESENCIA:
            self.assertIn('self._census_presence("%s")' % tag, src, tag)
            self.assertNotIn('self._census_tracked("%s"' % tag, src, tag)


class R2kTests(unittest.TestCase):
    """Ronda 2k (orquestador): la comprobación de puertos UDP no ata sockets.

    Atar UDP en 0.0.0.0 hizo saltar en el portátil la alerta del Firewall de Windows para el python del runner.
    """

    NETSTAT = ("\nConexiones activas\n\n  Proto  Direccion local  Direccion remota  Estado  PID\n"
               "  UDP    0.0.0.0:2302           *:*                                    4321\n"
               "  UDP    0.0.0.0:23040          *:*                                    4322\n")

    def _free(self, port, rc, stdout):
        """`_udp_port_free(port)` con netstat falso y sockets que no se dejan atar; devuelve (libre, binds, calls)."""
        binds, calls = [], []

        class _NoBind:
            def __init__(self, *a, **kw):
                pass

            def bind(self, addr):
                binds.append(addr)
                raise AssertionError("bind %r" % (addr,))

            def close(self):
                pass

        def _run(cmd, *a, **kw):
            calls.append(list(cmd))
            return types.SimpleNamespace(returncode=rc, stdout=stdout, stderr="")

        old_sock, old_run = live.socket.socket, live.subprocess.run
        live.socket.socket, live.subprocess.run = _NoBind, _run
        try:
            return live._udp_port_free(port), binds, calls
        finally:
            live.socket.socket, live.subprocess.run = old_sock, old_run

    def test_r2k_puerto_udp_sin_atar_sockets(self):
        ocupado, binds1, calls = self._free(2302, 0, self.NETSTAT)
        libre, binds2, _ = self._free(2304, 0, self.NETSTAT)
        self.assertEqual(binds1 + binds2, [])
        self.assertFalse(ocupado)
        self.assertTrue(libre)
        self.assertEqual(calls[0][:2], ["netstat", "-ano"])

    def test_r2k_netstat_que_falla_da_ocupado(self):
        libre, binds, _ = self._free(2304, 1, "")
        self.assertEqual(binds, [])
        self.assertFalse(libre)


class R2lTests(unittest.TestCase):
    """Ronda 2l (orquestador): sonda de lease, solo servidor (T4 917bc73, el catalogo tras perder el lease)."""

    def test_r2l_tap_retrasa_una_vez_el_poll_del_servidor(self):
        import time
        tiempos = []
        with _Upstream(_ok_handler()) as up:
            tap = live.Tap(up.port, clock=_clock()).start()
            tap.delay_server_poll_once(after_catalog_pages=2, delay_ms=400)
            try:
                for method, path in (("GET", "/poll?peer=server&inst=aa"),
                                     ("POST", "/catalog?peer=server&inst=aa"),
                                     ("POST", "/catalog?peer=server&inst=aa"),
                                     ("GET", "/poll?peer=client&inst=bb"),
                                     ("GET", "/poll?peer=server&inst=aa"),
                                     ("GET", "/poll?peer=server&inst=aa")):
                    t0 = time.monotonic()
                    status, _ = _request(tap.port, method, path, body=b"{}" if method == "POST" else None)
                    tiempos.append(time.monotonic() - t0)
                    self.assertEqual(status, 200)
            finally:
                tap.stop()
        self.assertEqual([i for i, s in enumerate(tiempos) if s >= 0.35], [4], tiempos)
        self.assertEqual([(i["stimulus"], i["req_id"], i["after_catalog_pages"]) for i in tap.injections],
                         [("lease_delay", 4, 2)])

    @staticmethod
    def _rec(rid, d, path, t, body):
        return {"req_id": rid, "dir": d, "path": path, "t_ms": float(t), "body": body}

    def _registros(self, completo):
        srv = {"inst": "aa", "modset": ["@DayZSandbox"], "peer": "server"}
        fin = {"ok": True, "have": 92, "pages": 92, "complete": True} if completo else \
            {"ok": True, "have": 8, "pages": 92}
        return [self._rec(0, "req", "/hello", 100, srv),
                self._rec(0, "resp", "/hello", 101, {"ok": True, "conn": 1, "session": "s"}),
                self._rec(1, "req", "/catalog", 300, {}),
                self._rec(1, "resp", "/catalog", 301, {"ok": True, "have": 92, "pages": 92, "complete": True}),
                self._rec(2, "req", "/hello", 600, {"inst": "cc", "peer": "client"}),
                self._rec(2, "resp", "/hello", 601, {"ok": True, "conn": 1, "session": "s"}),
                self._rec(3, "req", "/hello", 900, srv),
                self._rec(3, "resp", "/hello", 901, {"ok": True, "conn": 2, "session": "s"}),
                self._rec(4, "req", "/catalog", 950, {}),
                self._rec(4, "resp", "/catalog", 951, fin)]

    def test_r2l_veredicto_de_la_sonda_de_lease(self):
        fallo = [{"stimulus": "lease_delay", "t_ms": 500.0, "req_id": 9}]
        v = live.lease_probe_verdict(self._registros(True), fallo)
        self.assertEqual((v["veredicto"], v["motivo"]), ("PASA", "catalogo_completo_tras_saludo_nuevo"))
        # El catalogo completo de antes del saludo nuevo no cuenta, ni el saludo del cliente.
        v = live.lease_probe_verdict(self._registros(False), fallo)
        self.assertEqual((v["veredicto"], v["ultimo_have_pages"]), ("FALLA", (8, 92)))
        v = live.lease_probe_verdict(self._registros(True), [{"stimulus": "lease_delay", "t_ms": 960.0}])
        self.assertEqual((v["veredicto"], v["motivo"]), ("INCONCLUSO", "sin_saludo_nuevo_tras_el_retraso"))
        v = live.lease_probe_verdict(self._registros(True), [])
        self.assertEqual((v["veredicto"], v["motivo"]), ("INCONCLUSO", "sin_retraso_inyectado"))

    def test_r2l_modo_lease_y_lanzador(self):
        self.assertEqual(live.build_parser().parse_args(["--mode", "lease"]).mode, "lease")
        src = (Path(live.__file__).resolve().parent / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        for frag in ("[switch]$SondaLease", "[string]$PboSub = 'pbo'", "Join-Path $PackageDir $PboSub",
                     "if ($SondaLease) { $mode = 'lease' }"):
            self.assertIn(frag, src, frag)
        self.assertLess(src.index("if ($SondaLease) {\n"), src.index("$cliPid = Start-ClientOwn $clientExe"))


class R2mTests(unittest.TestCase):
    """Ronda 2m (orquestador): lo que dejo la 6.a partida de T4 (917bc73)."""

    def _campaign(self):
        ctx = types.SimpleNamespace(now_h_ms=lambda: 1000.0)
        log = live.OrderLog(ctx.now_h_ms)
        backend = _FakeBackendR2i([(200, {"ok": True, "op_id": "op-9"})])
        return live.Campaign(ctx, {"backend": backend}, types.SimpleNamespace(records=[]), log,
                             mode="seco", director_uid="uid-1")

    def test_r2m_spawn_manda_x_m_y_z_m(self):
        import wire as _wire
        seen = []

        def fake(ctx, peer, verb, payload=None, timeout_ms=None, **kw):
            seen.append((verb, _wire.unpack_payload(payload)))
            return types.SimpleNamespace(status="done", reason="", payload={"str": {}, "num": {}, "rows": []})

        old = live.f03_common.issue_one
        live.f03_common.issue_one = fake
        try:
            live.probe_spawn(None, "foreign_ground", "Barrel_Blue", tag="fg", pos=(6180.0, 7650.0))
        finally:
            live.f03_common.issue_one = old
        verb, data = seen[0]
        self.assertEqual(verb, "per_spawn_raw")
        self.assertEqual((data["num"].get("x_m"), data["num"].get("z_m")), (6180.0, 7650.0))
        self.assertNotIn("pos_x_m", data["num"])

    def test_r2m_ancla_de_scene_del_en_hora_local(self):
        import datetime as _dt
        t = 1795519495.25
        d = _dt.datetime.fromtimestamp(t)
        self.assertAlmostEqual(live._local_wall_seconds(t), d.hour * 3600 + d.minute * 60 + d.second + 0.25,
                               places=3)
        self.assertNotIn("time.time() % 86400.0", Path(live.__file__).read_text(encoding="utf-8"))

    def test_r2m_seguimiento_de_animales_en_p3(self):
        import inspect
        ani, zmb = _FakeCreatureProbe.CREATURE_ROWS
        probe = _FakeCreatureProbeR2j({"P2n:pre_reset": [ani, zmb]})
        old = live.f03_common.issue_one
        live.f03_common.issue_one = probe.issue
        camp = self._campaign()
        try:
            camp._census_tracked("P2n:pre_reset")
            camp._track_animals("P3:sigue1")
        finally:
            live.f03_common.issue_one = old
        self.assertEqual([s["tag"] for s in probe.starts], ["P2n:pre_reset", "P3:sigue1:disk:ani-01"])
        self.assertEqual((probe.starts[-1]["radius"], probe.starts[-1]["center"]), (120.0, (6100.0, 7700.0)))
        src = inspect.getsource(live.Campaign._run_inner)
        orden = ['probe_witness(ctx, "P3:apply1"', 'self._track_animals("P3:sigue1")',
                 "self._restart_backend(scene2_doc())", 'self._track_animals("P3:sigue2")',
                 'probe_witness(ctx, "P3:apply2"', 'self._track_animals("P3:sigue3")',
                 "self._restart_backend(scene1_doc())", 'self._census_presence("P3:pre_spawn")',
                 'self._census_presence("P3:pre_reset")']
        pos = [src.index(x) for x in orden]
        self.assertEqual(pos, sorted(pos))

    def test_r2m_logs_viejos_fuera_del_perfil(self):
        src = (Path(live.__file__).resolve().parent / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("function Move-OldProfileLogs([string]$ProfileDir, [string]$Dest)", src)
        self.assertLess(src.index("$nA = Move-OldProfileLogs $pairA[0]"),
                        src.index("$srvPid = Start-ExeViaWmi $serverExe"))


class R2nTests(unittest.TestCase):
    """Ronda 2n (orquestador): la 3b de t4-d940786 (sonda de lease) salio con 2 y dejo el servidor vivo."""

    def test_r2n_opcion_vacia_no_tumba_el_parser(self):
        a = live.build_parser().parse_args(["--mode", "lease", "--client-args", "--server-pid", "5",
                                            "--server-args", "-server -port=2302", "--client-start"])
        self.assertEqual((a.client_args, a.server_pid, a.server_args, a.client_start),
                         ("", 5, "-server -port=2302", ""))

    def test_r2n_lanzador_sin_client_args_vacio_y_cierre_con_espera(self):
        src = (Path(live.__file__).resolve().parent / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("if ($cliArgs) { $orchArgs += @('--client-args', $cliArgs) }", src)
        close = src[src.index("function CloseOwn {"):src.index("function Test-OwnAlive {")]
        for frag in ("$proc.Refresh()", "if ($proc.HasExited) { break }", "[void]$proc.CloseMainWindow()",
                     "sigue vivo tras WM_CLOSE acotado"):
            self.assertIn(frag, close, frag)

    def test_r2n_la_sonda_de_lease_para_su_servidor(self):
        import inspect
        calls = []

        def fake_hook(server_ctl, **kw):
            calls.append((server_ctl, kw))
            return lambda action: calls.append(("accion", action))

        old = live.make_real_restart_hook
        live.make_real_restart_hook = fake_hook
        try:
            r = live._stop_lease_server("ctl.ps1", state={"pid": 5, "start_time": "t"}, profile_dir="perfil")
            sin = live._stop_lease_server("", state={"pid": 5})
        finally:
            live.make_real_restart_hook = old
        self.assertEqual(r, "ok")
        self.assertTrue(sin.startswith("sin server_ctl"))
        self.assertEqual(calls[0][0], "ctl.ps1")
        self.assertEqual((calls[0][1]["cliente"], calls[0][1]["state"], calls[0][1]["profile_dir"]),
                         ("operador", {"pid": 5, "start_time": "t"}, "perfil"))
        self.assertEqual(calls[1], ("accion", "stop"))
        self.assertIn("_stop_lease_server(server_ctl", inspect.getsource(live.run_lease_probe))


class R2oTests(unittest.TestCase):
    """Ronda 2o (orquestador): en retail el servidor arranca con BattlEye, como en F1b (run_f1bp_partida.ps1:146-151)."""

    def test_r2o_retail_con_cfg_de_battleye(self):
        src = (Path(live.__file__).resolve().parent / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        self.assertIn("function Write-RetailCfg([string]$BaseCfg, [string]$RetailCfg)", src)
        self.assertIn("if ($effBuild -eq 'retail') { $serverCfg = Join-Path $missionDir 'server\\serverDZ_retail.cfg' }",
                      src)
        llamada = "if ($effBuild -eq 'retail') { Write-RetailCfg (Join-Path $missionDir 'server\\serverDZ.cfg') $serverCfg }"
        self.assertIn(llamada, src)
        # Despues de copiar la mision y antes de la comprobacion previa, para que -Comprobar tambien la pase.
        self.assertLess(src.index("Copy-FreshMission $MissionB1 $missionDir"), src.index(llamada))
        self.assertLess(src.index(llamada), src.index("if ($Comprobar) {"))
        fn = src[src.index("function Write-RetailCfg"):src.index("function Write-RetailCfg") + 900]
        self.assertIn("throw 'serverDZ_retail.cfg sin BattlEye = 1 antes de class Missions: no se lanza'", fn)


class R2qTests(unittest.TestCase):
    """Ronda 2q (orquestador): el montaje retail de t4-d38c552 (humo) fallo por el UID del director y el cierre."""

    def test_r2q_humo_sin_uid_del_director_sigue_como_la_partida(self):
        calls = []
        camp = types.SimpleNamespace(ctx=None, hello_timeout_s=1.0, director_timeout_ms=10, director_uid="")
        camp._wait_first_life = lambda: {"epoch": "e1"}

        def _restart():
            calls.append("reinicio")
            return "e2"

        camp._restart_server = _restart
        old = (live.probe_director_uid, live.wait_client_hello)
        live.probe_director_uid = lambda ctx, timeout_ms=0: ""
        live.wait_client_hello = lambda ctx, since, timeout_s=0: {"t_ms": 1.0}
        try:
            steps = live.run_humo_real_steps(camp)
        finally:
            live.probe_director_uid, live.wait_client_hello = old
        self.assertEqual([s["estado"] for s in steps], ["ok"] * 4, steps)
        self.assertIn("sin UID del director", steps[2]["motivo"])
        self.assertEqual(calls, ["reinicio"])

    def test_r2q_cierre_en_orden_inverso_al_registro(self):
        src = (Path(live.__file__).resolve().parent / "run_f2p_partida.ps1").read_text(encoding="utf-8")
        close = src[src.index("function CloseOwn {"):src.index("function Test-OwnAlive {")]
        self.assertIn("[array]::Reverse($ordenCierre)", close)
        self.assertIn("foreach ($pidValue in $ordenCierre) {", close)


class R2rTests(unittest.TestCase):
    """Ronda 2r (orquestador): el reinicio retail del montaje de t4-e3d0978 y los pasos del humo."""

    def test_r2r_humo_conserva_el_paso_que_falla(self):
        import inspect
        camp = types.SimpleNamespace(ctx=None, hello_timeout_s=1.0, director_timeout_ms=10, director_uid="")
        camp._wait_first_life = lambda: {"epoch": "e1"}

        def _restart():
            raise live.ServerHelloTimeout("el cliente no volvio tras el reinicio")

        camp._restart_server = _restart
        old = (live.probe_director_uid, live.wait_client_hello)
        live.probe_director_uid = lambda ctx, timeout_ms=0: ""
        live.wait_client_hello = lambda ctx, since, timeout_s=0: {"t_ms": 1.0}
        steps = []
        try:
            with self.assertRaises(live.ServerHelloTimeout):
                live.run_humo_real_steps(camp, steps)
        finally:
            live.probe_director_uid, live.wait_client_hello = old
        self.assertEqual([s["estado"] for s in steps], ["ok", "ok", "ok", "fallo"], steps)
        self.assertIn("no volvio", steps[-1]["motivo"])
        self.assertIn("run_humo_real_steps(campaign, steps)", inspect.getsource(live.run_humo_real))


class R2sTests(unittest.TestCase):
    """Ronda 2s (orquestador): en el reinicio retail el cliente se relanzaba con la carpeta del servidor.

    DayZServer lleva steam_appid.txt 223350 y DayZ 221100: Steam iniciaba el cliente con la app del servidor, el
    servidor no recibia su identidad (uid vacio) y lo echaba con el 49 (t4-e3d0978 y t4-f0059e7).
    """

    def test_r2s_carpeta_de_trabajo_del_cliente(self):
        import inspect
        ns = types.SimpleNamespace
        cliente = live._client_working_dir(ns(client_working_dir="", client_exe="C:/x/DayZ/DayZ_BE.exe",
                                              working_dir="C:/x/DayZServer"))
        self.assertEqual(cliente, str(Path("C:/x/DayZ")))
        self.assertEqual(live._client_working_dir(ns(client_working_dir="C:/y", client_exe="C:/x/DayZ/DayZ_BE.exe",
                                                     working_dir="C:/x/DayZServer")), "C:/y")
        self.assertEqual(live._client_working_dir(ns(client_working_dir="", client_exe="", working_dir="C:/w")),
                         "C:/w")
        self.assertEqual(live.build_parser().parse_args(["--client-working-dir", "C:/z"]).client_working_dir, "C:/z")
        src = inspect.getsource(live.main)
        self.assertEqual(src.count("client_working_dir=_client_working_dir(args)"), 2)
        self.assertNotIn("client_working_dir=args.working_dir", src)


if __name__ == "__main__":
    unittest.main()
