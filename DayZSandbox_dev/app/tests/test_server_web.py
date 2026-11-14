"""F1b-web: sesión de navegador, CSRF, estáticos y origen/edad (brief §7 W1-W7)."""
import http.client
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app.backend.server as server_mod
from app.backend.server import Backend, load_config
from app.backend.store import Store

from . import test_server as ts
from .test_server import AK, FIXTURES, HK, ROOT, Sse, fog

MSG_WEB = "Web sin construir: en app/web, npm ci --ignore-scripts y después npm run build"


def raw(env, method, path, body=None, headers=None, raw_body=None):
    """Petición sin credencial por defecto. Devuelve (estado, cabeceras, texto, json|None)."""
    conn = http.client.HTTPConnection("127.0.0.1", env.port, timeout=10)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    hdrs = dict(headers or {})
    if "Host" not in hdrs:
        hdrs["Host"] = "127.0.0.1:%d" % env.port
    for name, value in hdrs.items():
        conn.putheader(name, value)
    if raw_body is not None:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
    else:
        data = b""
    if method == "POST":
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(len(data)))
    conn.endheaders(data)
    resp = conn.getresponse()
    text = resp.read().decode("utf-8")
    out_headers = {}
    for name, value in resp.getheaders():
        out_headers[name] = value
    conn.close()
    env.bodies.append(text)
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return resp.status, out_headers, text, parsed


def login(env, key=HK, headers=None):
    st, hdrs, text, parsed = raw(env, "POST", "/api/session", {"key": key}, headers=headers)
    cookie = hdrs.get("Set-Cookie", "")
    sid = None
    if cookie:
        first = cookie.split(";")[0]
        sid = first.partition("=")[2] or None
    csrf = parsed.get("csrf") if isinstance(parsed, dict) else None
    return st, hdrs, parsed, sid, csrf


def cookie_header(env, sid):
    return "dsbx_session_%d=%s" % (env.port, sid)


def good_origin(env):
    return "http://127.0.0.1:%d" % env.port


def apply_body(env):
    snap = env.store.snapshot()
    return {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]}


def sse_cookie_first(env, cookie):
    conn = http.client.HTTPConnection("127.0.0.1", env.port, timeout=10)
    conn.request("GET", "/api/events", headers={"Cookie": cookie})
    resp = conn.getresponse()
    ev = {}
    if resp.status == 200:
        while True:
            line = resp.fp.readline()
            if not line:
                break
            line = line.decode("utf-8").rstrip("\n")
            if line == "":
                if ev:
                    break
                continue
            if line.startswith(":"):
                continue
            k, _, v = line.partition(": ")
            ev[k] = json.loads(v) if k == "data" else v
    return conn, resp, ev


def close_conn(conn, resp):
    try:
        resp.fp.raw._sock.shutdown(socket.SHUT_RDWR)
    except (OSError, AttributeError):
        pass
    conn.close()


class FakeClock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class WebBase(ts.Base):
    def do_login(self, key=HK, headers=None):
        return login(self.env, key=key, headers=headers)


class W1Entrada(WebBase):
    def test_entrada_ok_cookie_y_sesion(self):
        st, hdrs, parsed, sid, csrf = self.do_login()
        self.assertEqual(st, 200)
        self.assertTrue(isinstance(parsed, dict) and set(parsed.keys()) == {"ok", "csrf"})
        self.assertTrue(parsed.get("ok") is True)
        self.assertTrue(isinstance(csrf, str) and len(csrf) >= 20)
        cookie = hdrs.get("Set-Cookie", "")
        self.assertTrue(cookie.startswith("dsbx_session_%d=" % self.env.port))
        self.assertTrue("HttpOnly" in cookie)
        self.assertTrue("SameSite=Strict" in cookie)
        self.assertTrue("Path=/" in cookie)
        self.assertTrue("Max-Age" not in cookie and "Expires" not in cookie)
        self.assertEqual(hdrs.get("X-Content-Type-Options"), "nosniff")
        st, hdrs, text, parsed = raw(self.env, "GET", "/api/session",
                                     headers={"Cookie": cookie_header(self.env, sid)})
        self.assertEqual(st, 200)
        self.assertTrue(parsed == {"ok": True})
        self.assertTrue(text.strip() == '{"ok": true}')

    def test_entradas_invalidas_sin_cookie_ni_sesion(self):
        before = len(self.env.backend.sessions)
        # "\ud800" y "\udfff": sustitutos aislados, JSON válido que no se puede codificar en UTF-8 (C-03).
        for body in ({}, {"key": "clave-mala"}, {"key": 123}, {"key": None}, {"key": AK},
                     {"key": "\ud800"}, {"key": "\udfff"}):
            st, hdrs, text, parsed = raw(self.env, "POST", "/api/session", body)
            self.assertEqual(st, 401)
            self.assertTrue(isinstance(parsed, dict) and parsed.get("code") == "unauthorized")
            self.assertTrue("Set-Cookie" not in hdrs)
            self.assertEqual(len(self.env.backend.sessions), before)

    def test_dos_entradas_distintas_y_sid_del_cliente_no_reutilizado(self):
        puesto = "sid-puesto-por-el-cliente"
        st1, _, _, sid1, csrf1 = self.do_login(
            headers={"Cookie": cookie_header(self.env, puesto)})
        st2, _, _, sid2, csrf2 = self.do_login()
        self.assertEqual((st1, st2), (200, 200))
        self.assertTrue(sid1 != puesto)
        self.assertTrue(sid1 != sid2)
        self.assertTrue(csrf1 != csrf2)
        self.assertTrue(sid1 != csrf1)

    def test_sesion_sin_cookie_o_con_cookie_mala(self):
        st, _, _, parsed = raw(self.env, "GET", "/api/session")
        self.assertEqual(st, 401)
        st, _, _, parsed = raw(self.env, "GET", "/api/session",
                               headers={"Cookie": cookie_header(self.env, "no-existe")})
        self.assertEqual(st, 401)
        self.assertTrue(parsed.get("code") == "unauthorized")


class W2Cookie(WebBase):
    def test_cookie_aplica_lee_y_sse(self):
        _, _, _, sid, csrf = self.do_login()
        cookie = cookie_header(self.env, sid)
        hdrs = {"Cookie": cookie, "Origin": good_origin(self.env), "X-CSRF-Token": csrf}
        st, _, _, parsed = raw(self.env, "POST", "/api/apply", apply_body(self.env), headers=hdrs)
        self.assertEqual(st, 200)
        self.assertTrue(parsed.get("ok") is True)
        self.assertEqual(len(self.env.backend.ops), 1)
        # Origen localhost también vale.
        hdrs2 = dict(hdrs, Origin="http://localhost:%d" % self.env.port)
        st, _, _, parsed = raw(self.env, "POST", "/api/apply", apply_body(self.env), headers=hdrs2)
        self.assertEqual(st, 200)
        self.assertEqual(len(self.env.backend.ops), 2)
        st, _, _, parsed = raw(self.env, "GET", "/api/scene", headers={"Cookie": cookie})
        self.assertEqual(st, 200)
        conn, resp, ev = sse_cookie_first(self.env, cookie)
        try:
            self.assertEqual(resp.status, 200)
            self.assertTrue(ev.get("event") == "snapshot")
            self.assertEqual(len(ev["data"]["ops"]), 2)
        finally:
            close_conn(conn, resp)

    def test_cookie_con_basura_y_nombre_repetido(self):
        _, _, _, sid, csrf = self.do_login()
        name = "dsbx_session_%d" % self.env.port
        for cookie in ("basura; foo=bar; %s; otra=1" % cookie_header(self.env, sid),
                       "%s=malo; %s" % (name, cookie_header(self.env, sid)),
                       "sin-igual; %s" % cookie_header(self.env, sid)):
            st, _, _, _ = raw(self.env, "GET", "/api/scene", headers={"Cookie": cookie})
            self.assertEqual(st, 200)

    def test_csrf_negativos_en_apply_sin_efectos(self):
        _, _, _, sid, csrf = self.do_login()
        _, _, _, sid2, csrf2 = self.do_login()
        cookie = cookie_header(self.env, sid)
        cases = [
            {"Cookie": cookie, "Origin": good_origin(self.env)},
            {"Cookie": cookie, "Origin": good_origin(self.env), "X-CSRF-Token": "token-malo"},
            {"Cookie": cookie, "Origin": good_origin(self.env), "X-CSRF-Token": csrf2},
            {"Cookie": cookie, "X-CSRF-Token": csrf},
            {"Cookie": cookie, "Origin": "http://evil.test", "X-CSRF-Token": csrf},
            {"Cookie": cookie, "Origin": "http://127.0.0.1:%d" % (self.env.port + 1),
             "X-CSRF-Token": csrf},
        ]
        for hdrs in cases:
            st, _, _, parsed = raw(self.env, "POST", "/api/apply", apply_body(self.env), headers=hdrs)
            self.assertEqual(st, 403)
            self.assertTrue(isinstance(parsed, dict) and parsed.get("code") == "csrf_failed")
            self.assertEqual(self.env.backend.ops, {})

    def test_csrf_negativos_en_otros_post(self):
        _, _, _, sid, csrf = self.do_login()
        cookie = cookie_header(self.env, sid)
        snap = self.env.store.snapshot()
        calls = [
            ("/api/scene/ops", {"doc_id": snap["doc_id"], "request_id": "w2-1",
                                "base_rev": snap["rev"], "label": None, "ops": [fog(0.3)]}),
            ("/api/scene/undo", {"doc_id": snap["doc_id"], "request_id": "w2-2"}),
            ("/api/ai/pause", {"paused": True}),
            ("/api/lease", {"target": "obj-01", "field": None}),
        ]
        for path, body in calls:
            st, _, _, parsed = raw(self.env, "POST", path, body,
                                   headers={"Cookie": cookie, "Origin": good_origin(self.env)})
            self.assertEqual(st, 403, path)
            self.assertTrue(isinstance(parsed, dict) and parsed.get("code") == "csrf_failed")
        self.assertEqual(self.env.backend.ops, {})
        self.assertFalse(self.env.backend.paused)
        self.assertEqual(self.env.store.snapshot()["rev"], snap["rev"])

    def test_cookie_inexistente_y_bearer_malo_con_cookie_buena(self):
        _, _, _, sid, csrf = self.do_login()
        st, _, _, _ = raw(self.env, "GET", "/api/scene",
                          headers={"Cookie": cookie_header(self.env, "no-existe")})
        self.assertEqual(st, 401)
        hdrs = {"Cookie": cookie_header(self.env, sid), "Authorization": "Bearer clave-mala",
                "Origin": good_origin(self.env), "X-CSRF-Token": csrf}
        st, _, _, _ = raw(self.env, "GET", "/api/scene", headers=hdrs)
        self.assertEqual(st, 401)
        st, _, _, _ = raw(self.env, "POST", "/api/apply", apply_body(self.env), headers=hdrs)
        self.assertEqual(st, 401)
        self.assertEqual(self.env.backend.ops, {})


class W3Bearer(WebBase):
    def test_bearer_sin_csrf_ni_origin_sigue_igual(self):
        st, _, _, parsed = raw(self.env, "POST", "/api/apply", apply_body(self.env),
                               headers={"Authorization": "Bearer " + HK})
        self.assertEqual(st, 200)
        self.assertTrue(parsed.get("ok") is True)
        self.assertEqual(len(self.env.backend.ops), 1)
        st, _, _, parsed = raw(self.env, "GET", "/api/scene",
                               headers={"Authorization": "Bearer " + AK})
        self.assertEqual(st, 200)


class W4Estaticos(WebBase):
    def make_web(self):
        base = tempfile.mkdtemp(prefix="dsbx-web-")
        self.addCleanup(shutil.rmtree, base, True)
        web = Path(base) / "web"
        (web / "assets" / "sub").mkdir(parents=True)
        (web / "index.html").write_text("<h1>cola</h1>", encoding="utf-8")
        (web / "assets" / "a-1.js").write_text("console.log(1)", encoding="utf-8")
        (web / "assets" / "a-1.css").write_text("body{}", encoding="utf-8")
        (web / "otra").write_text("CENTINELA-OTRA", encoding="utf-8")
        (web / "assets" / "x.map").write_text("CENTINELA-MAP", encoding="utf-8")
        (web / "assets" / "sub" / "x.js").write_text("CENTINELA-SUB", encoding="utf-8")
        (Path(base) / "secreto.txt").write_text("CENTINELA-FUERA", encoding="utf-8")
        self.env.backend.web_root = str(web)
        return web

    def test_estaticos_ok(self):
        self.make_web()
        st, hdrs, text, _ = raw(self.env, "GET", "/")
        self.assertEqual(st, 200)
        self.assertTrue("cola" in text)
        self.assertEqual(hdrs.get("Content-Type"), "text/html; charset=utf-8")
        self.assertEqual(hdrs.get("Content-Security-Policy"),
                         "default-src 'self'; frame-ancestors 'none'")
        self.assertEqual(hdrs.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(hdrs.get("Cache-Control"), "no-cache")
        st, hdrs, text, _ = raw(self.env, "GET", "/assets/a-1.js")
        self.assertEqual(st, 200)
        self.assertEqual(hdrs.get("Content-Type"), "text/javascript; charset=utf-8")
        self.assertEqual(hdrs.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(hdrs.get("Cache-Control"), "no-cache")
        st, hdrs, text, _ = raw(self.env, "GET", "/assets/a-1.css")
        self.assertEqual(st, 200)
        self.assertEqual(hdrs.get("Content-Type"), "text/css; charset=utf-8")
        st, hdrs, text, _ = raw(self.env, "GET", "/?x=1")
        self.assertEqual(st, 200)
        self.assertTrue("cola" in text)

    def test_estaticos_404_con_centinelas_y_host_malo(self):
        self.make_web()
        for path in ("/otra", "/assets/x.map", "/assets/sub/x.js",
                     "/assets/../../secreto.txt", "/assets/%2e%2e/%2e%2e/secreto.txt",
                     "/assets/no-esta.js"):
            st, _, text, _ = raw(self.env, "GET", path)
            self.assertEqual(st, 404, path)
            self.assertTrue("CENTINELA" not in text)
        st, _, _, _ = raw(self.env, "GET", "/", headers={"Host": "evil.test"})
        self.assertEqual(st, 403)

    def test_sin_build_503_y_backend_arranca(self):
        vacio = tempfile.mkdtemp(prefix="dsbx-web-vacio-")
        self.addCleanup(shutil.rmtree, vacio, True)
        for root in (None, vacio):
            self.env.backend.web_root = root
            st, hdrs, text, _ = raw(self.env, "GET", "/")
            self.assertEqual(st, 503)
            self.assertTrue(text == MSG_WEB)
            self.assertTrue(hdrs.get("Content-Type", "").startswith("text/plain"))
            self.assertEqual(hdrs.get("X-Content-Type-Options"), "nosniff")
            st, _, _, _ = raw(self.env, "GET", "/api/scene",
                              headers={"Authorization": "Bearer " + HK})
            self.assertEqual(st, 200)

    def test_load_config_web_por_defecto_sin_reescribir(self):
        d = Path(tempfile.mkdtemp(prefix="dsbx-cfg-web-"))
        self.addCleanup(shutil.rmtree, d, True)
        cfgp = d / "backend.json"
        original = json.dumps({"scene": str(d / "scene.json"),
                               "catalog": str(FIXTURES / "catalog-m1.json"),
                               "human_key": HK, "ai_key": AK})
        cfgp.write_text(original, encoding="utf-8")
        cfg = load_config(str(cfgp))
        self.assertEqual(cfg.get("web"), "app/web/dist")
        self.assertTrue(cfgp.read_text(encoding="utf-8") == original)
        nuevo = d / "nuevo.json"
        cfg2 = load_config(str(nuevo))
        self.assertEqual(cfg2.get("web"), "app/web/dist")
        self.assertTrue(cfg2.get("human_key") != cfg2.get("ai_key"))


class W5OrigenYEdad(WebBase):
    def test_origen_en_op_state_y_snapshot_sin_age_en_op_state(self):
        sse = Sse(self.env, last_id=self.env.backend.seq)
        snap = self.env.scene()
        st, r = self.env.req("POST", "/api/apply",
                             {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.assertEqual(st, 200)
        ev = sse.take(1, "op.state")[0]
        sse.close()
        self.assertTrue(ev["data"].get("origin") == "backend")
        self.assertTrue("age_ms" not in ev["data"])
        s2 = Sse(self.env)
        data = s2.next()["data"]
        s2.close()
        ops = [o for o in data["ops"] if o["op_id"] == r["op_id"]]
        self.assertEqual(len(ops), 1)
        self.assertTrue(ops[0].get("origin") == "backend")
        self.assertTrue(isinstance(ops[0].get("age_ms"), int) and ops[0]["age_ms"] >= 0)

    def test_age_ms_con_clock_falso_y_reloj_de_pared(self):
        clock = FakeClock(1000.0)
        self.env.backend.clock = clock
        snap = self.env.scene()
        st, r = self.env.req("POST", "/api/apply",
                             {"doc_id": snap["doc_id"], "rev": snap["rev"], "hash": snap["hash"]})
        self.assertEqual(st, 200)
        clock.t += 5.5
        with mock.patch.object(server_mod, "now_ms", return_value=999999999):
            s2 = Sse(self.env)
            data = s2.next()["data"]
            s2.close()
        ops = [o for o in data["ops"] if o["op_id"] == r["op_id"]]
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0].get("age_ms"), 5500)


class W6Secretos(WebBase):
    def test_ningun_secreto_en_log_ni_respuestas(self):
        webdir = tempfile.mkdtemp(prefix="dsbx-web-w6-")
        self.addCleanup(shutil.rmtree, webdir, True)
        Path(webdir, "index.html").write_text("<h1>x</h1>", encoding="utf-8")
        self.env.backend.web_root = webdir
        st, _, parsed, sid, csrf = self.do_login()
        self.assertEqual(st, 200)
        cookie = cookie_header(self.env, sid)
        hdrs = {"Cookie": cookie, "Origin": good_origin(self.env), "X-CSRF-Token": csrf}
        st, _, _, _ = raw(self.env, "POST", "/api/apply", apply_body(self.env), headers=hdrs)
        self.assertEqual(st, 200)
        raw(self.env, "GET", "/api/session", headers={"Cookie": cookie})
        raw(self.env, "GET", "/api/scene", headers={"Cookie": cookie})
        raw(self.env, "GET", "/")
        conn, resp, ev = sse_cookie_first(self.env, cookie)
        try:
            self.assertEqual(resp.status, 200)
            self.env.bodies.append(json.dumps(ev))
        finally:
            close_conn(conn, resp)
        # Las respuestas de sesión solo traen lo pedido.
        st, _, entrada, _, _ = self.do_login()
        self.assertTrue(isinstance(entrada, dict) and set(entrada.keys()) == {"ok", "csrf"})
        st, _, _, vista = raw(self.env, "GET", "/api/session", headers={"Cookie": cookie})
        self.assertTrue(vista == {"ok": True})
        with self.env.backend._sessions_lock:
            sids = list(self.env.backend.sessions.keys())
            csrfs = [info["csrf"] for info in self.env.backend.sessions.values()]
        log_text = self.env.log.getvalue()
        for secret in [HK, AK] + sids:
            self.assertTrue(bool(secret) and secret not in log_text)
            for text in self.env.bodies:
                self.assertTrue(secret not in text)
        for secret in csrfs:
            self.assertTrue(secret not in log_text)
        # Un csrf solo aparece en una respuesta de entrada, no en el resto.
        for text in self.env.bodies:
            if any(c in text for c in csrfs):
                self.assertTrue(set(json.loads(text).keys()) == {"ok", "csrf"})


class W7ClavesIguales(unittest.TestCase):
    def make_store(self, d):
        with open(FIXTURES / "catalog-m1.json", encoding="utf-8") as f:
            catalog = json.load(f)
        return Store(os.path.join(d, "scene.json"), catalog)

    def test_backend_rechaza_iguales_o_vacias_y_acepta_distintas(self):
        d = tempfile.mkdtemp(prefix="dsbx-w7-")
        self.addCleanup(shutil.rmtree, d, True)
        store = self.make_store(d)
        for human, ai in ((HK, HK), ("", AK), (HK, ""), ("", "")):
            with self.assertRaises(ValueError):
                Backend(store, human, ai, port=0, log=io.StringIO())
        backend = Backend(store, HK, AK, port=0, log=io.StringIO())
        try:
            self.assertTrue(backend.port > 0)
        finally:
            backend.httpd.server_close()

    def test_main_con_claves_iguales_sale_2_sin_escuchar_ni_imprimirlas(self):
        d = Path(tempfile.mkdtemp(prefix="dsbx-w7-main-"))
        self.addCleanup(shutil.rmtree, d, True)
        igual = "clave-igual-de-prueba-1234567890"
        cfgp = d / "backend.json"
        cfgp.write_text(json.dumps({"scene": str(d / "scene.json"),
                                    "catalog": str(FIXTURES / "catalog-m1.json"),
                                    "human_key": igual, "ai_key": igual}), encoding="utf-8")
        script = ROOT / "app" / "backend" / "server.py"
        p = subprocess.run([sys.executable, str(script), "--config", str(cfgp), "--port", "0"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        output = p.stdout + p.stderr
        self.assertEqual(p.returncode, 2)
        self.assertTrue(igual not in output)
        self.assertTrue("Escuchando" not in output)


class C02CuerpoQueNoLlega(WebBase):
    """Un POST rechazado que anuncia cuerpo y no lo manda recibe su respuesta igual (C-02)."""

    def send_headers_only(self, headers):
        self.env.backend.drain_s = 0.3
        s = socket.create_connection(("127.0.0.1", self.env.port))
        s.settimeout(3.0)
        try:
            lines = ["POST /api/apply HTTP/1.1"] + ["%s: %s" % kv for kv in headers.items()] + \
                    ["Content-Length: 1", "", ""]
            s.sendall("\r\n".join(lines).encode("latin-1"))
            got = b""
            try:
                while True:  # el servidor cierra tras responder: se lee hasta el cierre
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    got += chunk
            except socket.timeout:
                return got.decode("latin-1") or None
            return got.decode("latin-1")
        finally:
            s.close()

    def test_rechazos_responden_sin_esperar_al_cuerpo(self):
        _, _, _, sid, csrf = self.do_login()
        port = self.env.port
        casos = [
            ({"Host": "evil.test"}, "403", "forbidden"),
            ({"Host": "127.0.0.1:%d" % port, "Cookie": cookie_header(self.env, sid),
              "Origin": good_origin(self.env)}, "403", "csrf_failed"),
            ({"Host": "127.0.0.1:%d" % port, "Authorization": "Bearer clave-mala"}, "401", "unauthorized"),
        ]
        for headers, status, code in casos:
            text = self.send_headers_only(headers)
            self.assertTrue(text is not None, "sin respuesta: %s" % code)
            self.assertTrue(text.startswith("HTTP/1.0 " + status), code)
            self.assertTrue(code in text)
        self.assertEqual(self.env.backend.ops, {})


if __name__ == "__main__":
    unittest.main()
