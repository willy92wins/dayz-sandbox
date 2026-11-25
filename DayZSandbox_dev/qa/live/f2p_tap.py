#!/usr/bin/env python3
"""Tap HTTP de la partida F2P: entre el mod (producto) y el bridge del backend.

Reenvia sin cambiar estado ni cuerpo (R-19), registra req/resp con req_id
unico bajo cerrojo (R-16), estampa la respuesta antes de escribirla al peer
(R-17) y clasifica upstream_status (R-18): entero del backend, None si la
respuesta la fabrica el tap (502 exacto) o 0 si el backend cerro sin linea
de estado. La clave `key` nunca entra en el query registrado (R-13).

Estimulos declarados (visibles en la evidencia):
- P2 (Q2): intercept_first_result() contesta el primer /result con 200
  {"ok":true} y upstream_status None, sin reenviarlo. Queda registrado como
  respuesta fabricada por el tap (upstream_status nulo).
- P5 (R-45): hold_from_first_result() retiene el primer /result y toda
  peticion posterior hasta release_held(), que les contesta el 502 del tap.
- Sonda de lease (T4, 24-nov): delay_server_poll_once() retrasa una sola vez,
  antes de reenviarlo, un /poll del peer servidor llegado con N paginas de
  /catalog ya vistas. Queda en `injections` con stimulus "lease_delay".
"""

from __future__ import annotations

import http.client
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

UPSTREAM_TIMEOUT_S = 5.0
TAP_502_BODY = {"ok": False, "error": "upstream_unreachable"}
TAP_502_BYTES = b'{"ok":false,"error":"upstream_unreachable"}'


def strip_key(query_string):
    """Query como dict sin la clave `key` (R-13)."""
    if not query_string:
        return {}
    parsed = parse_qs(query_string, keep_blank_values=True)
    out = {}
    for key, values in parsed.items():
        if key == "key":
            continue
        out[key] = values[0] if values else ""
    return out


def parse_body(raw):
    """Cuerpo JSON como objeto; si no es JSON, el texto (R-19 [DESIGN])."""
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return raw.decode("utf-8", "replace")


class Tap:
    def __init__(self, upstream_port, *, listen_port=0, clock=None, sink=None,
                 upstream_host="127.0.0.1", timeout_s=UPSTREAM_TIMEOUT_S):
        self.upstream_host = upstream_host
        self.upstream_port = int(upstream_port)
        self.listen_port = int(listen_port)
        self.clock = clock or (lambda: time.monotonic() * 1000.0)
        self.sink = sink
        self.timeout_s = float(timeout_s)
        self.records = []
        self._lock = threading.Lock()
        self._next_req_id = 0
        self._server = None
        self._thread = None
        # Estimulo P2 (Q2)
        self._intercept_first_result = False
        self._intercepted = False
        self.injections = []
        # Retencion P5 (R-45)
        self._hold_enabled = False
        self._hold_active = False
        self._held = []  # lista de dicts con handler/event/result
        self._hold_cond = threading.Condition()
        self.first_result_req_id = None
        self.first_result_t_ms = None
        # Sonda de lease (T4, 24-nov)
        self._poll_delay = None

    # -- registro ---------------------------------------------------------
    def _stamp(self):
        t = float(self.clock())
        if not math.isfinite(t):
            raise ValueError("reloj no finito")
        return t

    def _emit(self, record):
        with self._lock:
            self.records.append(record)
        if self.sink is not None:
            self.sink(record)
        return record

    def _alloc_req_id(self):
        with self._lock:
            rid = self._next_req_id
            self._next_req_id += 1
            return rid

    # -- estimulos --------------------------------------------------------
    def intercept_first_result(self):
        with self._hold_cond:
            self._intercept_first_result = True

    def hold_from_first_result(self):
        with self._hold_cond:
            self._hold_enabled = True

    def held_count(self):
        with self._hold_cond:
            return len(self._held)

    def release_held(self):
        """Suelta lo retenido contestando el 502 del tap a cada peticion."""
        with self._hold_cond:
            held = list(self._held)
            self._held.clear()
            self._hold_active = False
            self._hold_enabled = False
        for item in held:
            item["release"] = "tap_502"
            item["event"].set()

    def stop_holding(self):
        self.release_held()

    def delay_server_poll_once(self, *, after_catalog_pages, delay_ms):
        """Sonda de lease (T4 917bc73): retrasa una vez, antes de reenviarlo, el primer /poll del peer servidor
        que llegue con al menos `after_catalog_pages` paginas de /catalog vistas. El mod pierde el lease a mitad
        de la subida del catalogo, como en la 5.a partida, y vuelve a saludar."""
        with self._hold_cond:
            self._poll_delay = {"after": int(after_catalog_pages), "ms": float(delay_ms),
                                "pages": 0, "done": False}

    # -- servidor ---------------------------------------------------------
    def start(self):
        tap = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                pass

            def do_GET(self):
                tap._handle(self, "GET")

            def do_POST(self):
                tap._handle(self, "POST")

            def do_PUT(self):
                tap._handle(self, "PUT")

            def do_DELETE(self):
                tap._handle(self, "DELETE")

        class _Srv(ThreadingHTTPServer):
            def handle_error(self, request, client_address):
                pass

        self._server = _Srv(("127.0.0.1", self.listen_port), Handler)
        self._server.daemon_threads = True
        self.listen_port = int(self._server.server_address[1])
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def port(self):
        return self.listen_port

    def stop(self):
        self.release_held()
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()
        return False

    # -- manejo de una peticion ------------------------------------------
    def _handle(self, handler, method):
        parsed = urlsplit(handler.path)
        path = parsed.path
        length = 0
        try:
            length = int(handler.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        raw = handler.rfile.read(length) if length > 0 else b""
        req_id = self._alloc_req_id()
        t_req = self._stamp()
        req_record = {
            "req_id": req_id,
            "t_ms": t_req,
            "dir": "req",
            "method": method,
            "path": path,
            "http": None,
            "upstream_status": None,
            "query": strip_key(parsed.query),
            "body": parse_body(raw),
        }
        # El registro req no lleva http/upstream; se quitan para no confundir
        # al oraculo, que solo los lee en resp. Se conservan las claves del
        # contrato en resp.
        del req_record["http"]
        del req_record["upstream_status"]
        self._emit(req_record)

        # Sonda de lease: el /poll del servidor se retrasa una sola vez, antes de reenviarlo.
        delay_s = 0.0
        with self._hold_cond:
            pd = self._poll_delay
            if pd is not None and not pd["done"]:
                if path == "/catalog":
                    pd["pages"] += 1
                elif path == "/poll" and req_record["query"].get("peer") == "server" \
                        and pd["pages"] >= pd["after"]:
                    pd["done"] = True
                    delay_s = pd["ms"] / 1000.0
                    self.injections.append({"req_id": req_id, "stimulus": "lease_delay", "t_ms": t_req,
                                            "delay_ms": pd["ms"], "after_catalog_pages": pd["pages"]})
        if delay_s > 0:
            time.sleep(delay_s)

        # Retencion P5: desde el primer /result, todo queda retenido.
        should_hold = False
        with self._hold_cond:
            if self._hold_enabled and not self._hold_active:
                if method == "POST" and path == "/result":
                    self._hold_active = True
                    should_hold = True
                    self.first_result_req_id = req_id
                    self.first_result_t_ms = t_req
            elif self._hold_active:
                should_hold = True
        if should_hold:
            item = {"req_id": req_id, "event": threading.Event(), "release": None}
            with self._hold_cond:
                self._held.append(item)
            item["event"].wait()
            self._send_tap_502(handler, req_id, path, method)
            return

        # Estimulo P2 (Q2): el tap contesta el primer /result.
        with self._hold_cond:
            intercept = (
                self._intercept_first_result and not self._intercepted
                and method == "POST" and path == "/result"
            )
            if intercept:
                self._intercepted = True
        if intercept:
            body = {"ok": True}
            payload = b'{"ok":true}'
            resp = {
                "req_id": req_id, "t_ms": self._stamp(), "dir": "resp",
                "method": method, "path": path, "http": 200,
                "upstream_status": None, "query": strip_key(parsed.query),
                "body": body, "injected_by": "tap", "stimulus": "p2_first_result_ack",
            }
            self.injections.append({"req_id": req_id, "stimulus": "p2_first_result_ack",
                                    "t_ms": resp["t_ms"]})
            self._emit(resp)  # R-17: antes de escribir al peer
            self._write_response(handler, 200, payload)
            return

        status, resp_body_raw, upstream_status = self._forward(method, handler.path, raw, handler)
        if upstream_status is None:
            # Backend inalcanzable: 502 fabricado por el tap (R-18).
            resp = {
                "req_id": req_id, "t_ms": self._stamp(), "dir": "resp",
                "method": method, "path": path, "http": 502,
                "upstream_status": None, "query": strip_key(parsed.query),
                "body": dict(TAP_502_BODY),
            }
            self._emit(resp)
            self._write_response(handler, 502, TAP_502_BYTES)
            return
        if upstream_status == 0:
            # Backend acepto y cerro sin linea de estado (R-18).
            resp = {
                "req_id": req_id, "t_ms": self._stamp(), "dir": "resp",
                "method": method, "path": path, "http": 0,
                "upstream_status": 0, "query": strip_key(parsed.query),
                "body": "",
            }
            self._emit(resp)
            self._write_response(handler, 0, b"", close=True)
            return
        resp = {
            "req_id": req_id, "t_ms": self._stamp(), "dir": "resp",
            "method": method, "path": path, "http": int(status),
            "upstream_status": int(status), "query": strip_key(parsed.query),
            "body": parse_body(resp_body_raw),
        }
        self._emit(resp)  # R-17: estampado y registrado antes de servir
        self._write_response(handler, int(status), resp_body_raw)

    def _send_tap_502(self, handler, req_id, path, method):
        resp = {
            "req_id": req_id, "t_ms": self._stamp(), "dir": "resp",
            "method": method, "path": path, "http": 502,
            "upstream_status": None, "query": {},
            "body": dict(TAP_502_BODY),
        }
        # El query ya quedo en el registro req; aqui se rellena igual que el req.
        self._emit(resp)
        self._write_response(handler, 502, TAP_502_BYTES)

    def _forward(self, method, full_path, raw, handler):
        """Devuelve (status, body_bytes, upstream_status). upstream None = inalcanzable, 0 = cierre sin estado."""
        conn = http.client.HTTPConnection(self.upstream_host, self.upstream_port,
                                          timeout=self.timeout_s)
        headers = {}
        ctype = handler.headers.get("Content-Type")
        if ctype:
            headers["Content-Type"] = ctype
        try:
            conn.request(method, full_path, body=raw if raw else None, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            status = int(resp.status)
            return status, data, status
        except (ConnectionRefusedError, TimeoutError, socket_timeout()) as exc:
            return None, b"", None
        except http.client.RemoteDisconnected:
            return 0, b"", 0
        except OSError:
            # Distinguir cierre sin estado de inalcanzable es fragil con
            # http.client; una desconexion remota ya llego como
            # RemoteDisconnected arriba. El resto se trata inalcanzable.
            return None, b"", None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    @staticmethod
    def _write_response(handler, status, payload, close=False):
        try:
            if status and status > 0:
                handler.send_response(status)
                handler.send_header("Content-Type", "application/json")
                handler.send_header("Content-Length", str(len(payload)))
                if close:
                    handler.send_header("Connection", "close")
                handler.end_headers()
                if payload:
                    handler.wfile.write(payload)
            else:
                handler.send_response(502)
                handler.send_header("Content-Length", "0")
                handler.send_header("Connection", "close")
                handler.end_headers()
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        if close:
            handler.close_connection = True


def socket_timeout():
    import socket
    return socket.timeout
