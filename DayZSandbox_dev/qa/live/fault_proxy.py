#!/usr/bin/env python3
"""Proxy HTTP de inyeccion de fallos para el bridge de F1b-peers.

Se coloca entre un peer del juego y el bridge del backend. Reenvia cada
peticion al bridge salvo que una regla del fichero JSON diga otra cosa.

El parametro ``key`` (secreto) se elimina de la consulta que el proxy guarda,
registra y usa en mensajes; la peticion reenviada conserva la consulta
original porque el bridge real exige la clave para autenticar al peer.
Ningun log, fichero activo, mensaje de error ni excepcion lleva la clave.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit

ROUTE_BY_PATH = {
    "/hello": "hello",
    "/poll": "poll",
    "/result": "result",
    "/catalog": "catalog",
}

UPSTREAM_CONNECT_TIMEOUT_S = 5.0


def _now_ms():
    return int(round(time.monotonic() * 1000.0))


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _shutdown(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except (OSError, AttributeError):
        pass


def _atomic_write_json(path, obj):
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    tmp = "%s.tmp.%d.%d" % (path, os.getpid(), threading.get_ident())
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    last_error = None
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.01)
    if last_error is not None:
        raise last_error


def _strip_key(query_string):
    if not query_string:
        return {}
    parsed = parse_qs(query_string, keep_blank_values=True)
    out = {}
    for key, values in parsed.items():
        if key == "key":
            continue
        out[key] = values[0] if values else ""
    return out


def _match_request(match, req):
    route = match.get("route", "any")
    if route != "any" and route != req["route"]:
        return False
    peer = match.get("peer", "any")
    if peer != "any" and peer != req["peer"]:
        return False
    deliver = match.get("deliver", None)
    if deliver is not None:
        if req["route"] != "poll":
            return False
        if req["deliver"] is None:
            return False
        if _as_int(deliver, -1) != _as_int(req["deliver"], -2):
            return False
    return True


def _apply_set(obj, path, value):
    parts = [part for part in str(path).split(".") if part != ""]
    if not parts:
        return obj
    cur = obj
    for part in parts[:-1]:
        if isinstance(cur, list):
            idx = _as_int(part, -1)
            if idx < 0 or idx >= len(cur):
                return obj
            cur = cur[idx]
        elif isinstance(cur, dict):
            if part not in cur:
                return obj
            cur = cur[part]
        else:
            return obj
    last = parts[-1]
    delete = isinstance(value, dict) and value.get("$delete") is True
    if isinstance(cur, list):
        idx = _as_int(last, -1)
        if idx < 0 or idx >= len(cur):
            return obj
        if delete:
            del cur[idx]
        else:
            cur[idx] = value
    elif isinstance(cur, dict):
        if delete:
            cur.pop(last, None)
        else:
            cur[last] = value
    return obj


def _dechunk(data):
    out = b""
    pos = 0
    while pos < len(data):
        line_end = data.find(b"\r\n", pos)
        if line_end < 0:
            break
        size_line = data[pos:line_end].split(b";")[0].strip()
        try:
            size = int(size_line, 16)
        except ValueError:
            break
        pos = line_end + 2
        if size == 0:
            break
        out += data[pos:pos + size]
        pos += size + 2
    return out


def _parse_headers(blob):
    text = blob.decode("latin-1", "replace")
    lines = text.split("\r\n")
    status = 0
    if lines:
        parts = lines[0].split(" ", 2)
        if len(parts) >= 2:
            status = _as_int(parts[1], 0)
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
    return status, headers


def _read_body(handler):
    try:
        length = int(handler.headers.get("Content-Length") or 0)
    except (TypeError, ValueError):
        length = 0
    if length <= 0:
        return b""
    try:
        return handler.rfile.read(length)
    except (OSError, ValueError):
        return b""


class _RulesState:
    def __init__(self):
        self.version = None
        self.rules = []
        self.counters = {}


class _ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        pass


def _make_handler(proxy):
    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            proxy._handle(self, "GET")

        def do_POST(self):
            proxy._handle(self, "POST")

    return _Handler


def _with_deliver_zero(url):
    """La misma URL con deliver=0. La clave se conserva: va al bridge, nunca a un log."""
    pairs = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True) if k != "deliver"]
    pairs.append(("deliver", "0"))
    return url._replace(query=urlencode(pairs))


class FaultProxy:
    def __init__(self, upstream_port, rules_path, active_path, log_path, listen_port=0):
        self.upstream_port = int(upstream_port)
        self.rules_path = os.path.abspath(rules_path)
        self.active_path = os.path.abspath(active_path)
        self.log_path = os.path.abspath(log_path)
        self.listen_port = int(listen_port)
        self.port = None

        self._lock = threading.RLock()
        self._reload_lock = threading.Lock()
        self._state = _RulesState()
        self._sig = None
        self._windows = []
        self._inflight = {}
        self._req_counter = 0

        self._stop = threading.Event()
        self._server = None
        self._thread = None
        self._watcher = None
        self._log_lock = threading.Lock()
        self._log_fh = None

    def start(self):
        self._log_fh = open(self.log_path, "a", encoding="utf-8", newline="\n")
        self._maybe_reload()
        handler = _make_handler(self)
        server = _ProxyServer(("127.0.0.1", self.listen_port), handler)
        self._server = server
        self.port = server.server_address[1]
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.05},
            name="fault-proxy-http",
            daemon=True,
        )
        self._thread.start()
        self._watcher = threading.Thread(
            target=self._watch_rules, name="fault-proxy-rules", daemon=True
        )
        self._watcher.start()
        return self

    def stop(self):
        self._stop.set()
        server = self._server
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        if self._watcher is not None:
            self._watcher.join(timeout=5.0)
        with self._lock:
            entries = list(self._inflight.values())
        for entry in entries:
            _shutdown(entry.get("client"))
            upstream = entry.get("upstream")
            if upstream is not None:
                _shutdown(upstream)
                try:
                    upstream.close()
                except OSError:
                    pass
        with self._log_lock:
            if self._log_fh is not None:
                try:
                    self._log_fh.flush()
                    self._log_fh.close()
                except Exception:
                    pass
                self._log_fh = None
        self._server = None
        self._thread = None
        self._watcher = None

    def _watch_rules(self):
        while not self._stop.is_set():
            try:
                self._maybe_reload()
            except Exception:
                pass
            self._stop.wait(0.1)

    def _maybe_reload(self):
        try:
            stat = os.stat(self.rules_path)
        except OSError:
            return
        sig = (stat.st_mtime_ns, stat.st_size)
        if sig == self._sig:
            return
        with self._reload_lock:
            if sig == self._sig:
                return
            try:
                with open(self.rules_path, "rb") as fh:
                    raw = fh.read()
                doc = json.loads(raw.decode("utf-8"))
            except (OSError, ValueError):
                return
            if not isinstance(doc, dict):
                return
            rules = doc.get("rules")
            if not isinstance(rules, list):
                rules = []
            version = _as_int(doc.get("version"), 0)
            self._sig = sig
            self._install(version, rules)

    def _install(self, version, rules):
        clean = [rule for rule in rules if isinstance(rule, dict)]
        with self._lock:
            previous = self._state.version
            self._state.version = version
            self._state.rules = clean
            if version != previous:
                self._state.counters = {}
                self._windows = []
        if version == previous:
            return
        try:
            _atomic_write_json(
                self.active_path, {"version": version, "t_ms": _now_ms()}
            )
        except OSError:
            pass
        specs = []
        for rule in clean:
            if rule.get("abort_inflight") is True:
                match = _as_dict(rule.get("match"))
                specs.append((match.get("peer", "any"), match.get("route", "any")))
        if specs:
            self._abort_inflight(specs)

    def _abort_inflight(self, specs):
        with self._lock:
            targets = []
            for entry in self._inflight.values():
                if entry["done"] or entry["aborted"] or not entry["forwarded"]:
                    continue
                if _matches_spec(specs, entry):
                    entry["aborted"] = True
                    targets.append(entry)
        for entry in targets:
            _shutdown(entry.get("client"))
            upstream = entry.get("upstream")
            if upstream is not None:
                _shutdown(upstream)
                try:
                    upstream.close()
                except OSError:
                    pass

    def _handle(self, handler, method):
        entry = None
        t0 = time.monotonic()
        try:
            self._maybe_reload()
            url = urlsplit(handler.path)
            route = ROUTE_BY_PATH.get(url.path, "other")
            query = _strip_key(url.query)
            peer = query.get("peer")
            deliver = None
            if route == "poll":
                raw_deliver = query.get("deliver")
                if raw_deliver == "0":
                    deliver = 0
                elif raw_deliver == "1":
                    deliver = 1
            session = query.get("session")
            body = _read_body(handler)
            with self._lock:
                req_id = self._req_counter
                self._req_counter += 1
                version = self._state.version
            entry = {
                "req_id": req_id,
                "rule_id": None,
                "rules_version": version,
                "t_ms": int(round(t0 * 1000.0)),
                "method": method,
                "route": route,
                "peer": peer,
                "deliver": deliver,
                "session": session,
                "action": "pass",
                "req_bytes": len(body),
                "upstream_status": None,
                "resp_bytes": 0,
                "held_ms": 0,
                "aborted": False,
                "done": False,
                "forwarded": False,
                "client": handler.connection,
                "upstream": None,
            }
            req = {"route": route, "peer": peer, "deliver": deliver}
            with self._lock:
                self._inflight[req_id] = entry
            self._dispatch(handler, entry, req, method, url, body, t0)
        except Exception:
            pass
        finally:
            if entry is not None and not entry["done"]:
                try:
                    handler.close_connection = True
                except Exception:
                    pass
                self._finish(entry, t0)

    def _dispatch(self, handler, entry, req, method, url, body, t0):
        window = self._active_window(req["peer"], req["route"])
        if window is not None:
            entry["rule_id"] = window["rule_id"]
            if window["mode"] == "cut":
                entry["action"] = "then_cut_ms"
                entry["aborted"] = True
                self._close_client(handler)
                self._finish(entry, t0)
                return
            # Brief v1.2 (L-13): se reenvia al momento -un poll, como mantenimiento (deliver=0), para que el
            # bridge conteste ya y no sume su long-poll- y se retiene la RESPUESTA hasta el final absoluto
            # de la ventana.
            entry["action"] = "then_hold_ms"
            if req["route"] == "poll":
                url = _with_deliver_zero(url)
            result = self._forward(entry, method, url, body)
            if entry["aborted"]:
                entry["upstream_status"] = None
                self._close_client(handler)
                self._finish(entry, t0)
                return
            status, ctype, data = result
            start = time.monotonic()
            wait_s = max(0.0, window["until"] - start)
            if wait_s > 0:
                time.sleep(wait_s)
            entry["held_ms"] = int(round((time.monotonic() - start) * 1000.0))
            entry["resp_bytes"] = len(data)
            self._serve(handler, status, ctype, data)
            self._finish(entry, t0)
            return

        rule = self._select_request_rule(req)
        if rule is not None:
            self._run_action(handler, entry, rule, req, method, url, body, t0)
            return

        self._forward_and_serve(handler, entry, method, url, body, t0, response_rules=True)

    def _run_action(self, handler, entry, rule, req, method, url, body, t0):
        action = _as_dict(rule.get("action"))
        atype = action.get("type") or "pass"
        entry["rule_id"] = rule.get("id")
        entry["action"] = atype

        if atype == "status":
            code = _as_int(action.get("code"), 503)
            error = action.get("error", "fault")
            payload = json.dumps(
                {"ok": False, "error": error},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            entry["resp_bytes"] = len(payload)
            self._serve(handler, code, "application/json; charset=utf-8", payload)
            self._finish(entry, t0)
            return

        if atype == "refuse":
            entry["aborted"] = True
            self._close_client(handler)
            self._finish(entry, t0)
            return

        if atype == "hold_ms":
            start = time.monotonic()
            delay_ms = max(0, _as_int(action.get("ms"), 0))
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)
            entry["held_ms"] = int(round((time.monotonic() - start) * 1000.0))
            self._forward_and_serve(handler, entry, method, url, body, t0)
            return

        if atype == "hold_resp_ms":
            result = self._forward(entry, method, url, body)
            if entry["aborted"]:
                entry["upstream_status"] = None
                self._close_client(handler)
                self._finish(entry, t0)
                return
            start = time.monotonic()
            delay_ms = max(0, _as_int(action.get("ms"), 0))
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)
            entry["held_ms"] = int(round((time.monotonic() - start) * 1000.0))
            status, ctype, data = result
            entry["resp_bytes"] = len(data)
            self._serve(handler, status, ctype, data)
            self._finish(entry, t0)
            return

        if atype == "drop_resp":
            result = self._forward(entry, method, url, body)
            if entry["aborted"]:
                entry["upstream_status"] = None
                self._close_client(handler)
                self._finish(entry, t0)
                return
            entry["aborted"] = True
            self._close_client(handler)
            self._finish(entry, t0)
            return

        if atype == "rewrite":
            result = self._forward(entry, method, url, body)
            if entry["aborted"]:
                entry["upstream_status"] = None
                self._close_client(handler)
                self._finish(entry, t0)
                return
            status, ctype, data = result
            data = self._rewrite(data, action.get("set"))
            entry["resp_bytes"] = len(data)
            self._serve(handler, status, ctype, data)
            self._finish(entry, t0)
            return

        if atype in ("then_cut_ms", "then_hold_ms"):
            result = self._forward(entry, method, url, body)
            if entry["aborted"]:
                entry["upstream_status"] = None
                self._close_client(handler)
                self._finish(entry, t0)
                return
            status, ctype, data = result
            entry["resp_bytes"] = len(data)
            # La ventana se abre justo antes de servir para que una peticion
            # inmediatamente posterior ya la vea; el desfase con "tras servir"
            # es de milisegundos.
            self._open_window(rule, action)
            self._serve(handler, status, ctype, data)
            self._finish(entry, t0)
            return

        self._forward_and_serve(handler, entry, method, url, body, t0)

    def _forward_and_serve(self, handler, entry, method, url, body, t0, response_rules=False):
        result = self._forward(entry, method, url, body)
        if entry["aborted"]:
            entry["upstream_status"] = None
            self._close_client(handler)
            self._finish(entry, t0)
            return
        status, ctype, data = result
        if response_rules:
            rule = self._select_response_rule(entry, data)
            if rule is not None:
                action = _as_dict(rule.get("action"))
                atype = action.get("type") or "pass"
                entry["rule_id"] = rule.get("id")
                entry["action"] = atype
                if atype == "rewrite":
                    data = self._rewrite(data, action.get("set"))
                elif atype == "hold_resp_ms":
                    start = time.monotonic()
                    delay_ms = max(0, _as_int(action.get("ms"), 0))
                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000.0)
                    entry["held_ms"] = int(round((time.monotonic() - start) * 1000.0))
                if atype in ("then_cut_ms", "then_hold_ms"):
                    self._open_window(rule, action)
                entry["resp_bytes"] = len(data)
                self._serve(handler, status, ctype, data)
                self._finish(entry, t0)
                return
        entry["resp_bytes"] = len(data)
        self._serve(handler, status, ctype, data)
        self._finish(entry, t0)

    def _select_request_rule(self, req):
        with self._lock:
            for rule in self._state.rules:
                match = _as_dict(rule.get("match"))
                if match.get("resp_has_op") is True:
                    continue
                if not _match_request(match, req):
                    continue
                if self._consume(rule):
                    return rule
        return None

    def _select_response_rule(self, entry, data):
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None
        if not isinstance(obj, dict):
            return None
        ops = obj.get("ops")
        if not isinstance(ops, list) or len(ops) == 0:
            return None
        req = {"route": entry["route"], "peer": entry["peer"], "deliver": entry["deliver"]}
        with self._lock:
            for rule in self._state.rules:
                match = _as_dict(rule.get("match"))
                if match.get("resp_has_op") is not True:
                    continue
                if not _match_request(match, req):
                    continue
                if self._consume(rule):
                    return rule
        return None

    def _consume(self, rule):
        rid = rule.get("id")
        if not isinstance(rid, str):
            rid = json.dumps(rid, sort_keys=True) if rid is not None else "<none>"
        match = _as_dict(rule.get("match"))
        nth = max(1, _as_int(match.get("nth"), 1))
        count = _as_int(match.get("count"), -1)
        counter = self._state.counters.get(rid)
        if counter is None:
            counter = {"seen": 0, "acted": 0}
            self._state.counters[rid] = counter
        counter["seen"] += 1
        if counter["seen"] < nth:
            return False
        if count != -1 and counter["acted"] >= count:
            return False
        counter["acted"] += 1
        return True

    def _build_request(self, method, url, body):
        path = url.path
        if url.query:
            path += "?" + url.query
        head = (
            "%s %s HTTP/1.1\r\n"
            "Host: 127.0.0.1:%d\r\n"
            "Content-Type: application/json\r\n"
            "Content-Length: %d\r\n"
            "Connection: close\r\n"
            "\r\n"
        ) % (method, path, self.upstream_port, len(body))
        return head.encode("latin-1", "replace") + body

    def _recv(self, entry, sock):
        try:
            return sock.recv(65536)
        except socket.timeout:
            return None
        except OSError:
            if entry["aborted"]:
                return b""
            raise

    def _forward(self, entry, method, url, body):
        sock = None
        try:
            sock = socket.create_connection(
                ("127.0.0.1", self.upstream_port), timeout=UPSTREAM_CONNECT_TIMEOUT_S
            )
            entry["upstream"] = sock
            sock.sendall(self._build_request(method, url, body))
            with self._lock:
                entry["forwarded"] = True
                aborted_now = entry["aborted"]
            if aborted_now:
                return None
            sock.settimeout(0.25)
            buffer = b""
            while b"\r\n\r\n" not in buffer:
                if entry["aborted"]:
                    return None
                chunk = self._recv(entry, sock)
                if chunk is None:
                    continue
                if not chunk:
                    break
                buffer += chunk
            header_end = buffer.find(b"\r\n\r\n")
            if header_end < 0:
                header_blob, rest = buffer, b""
            else:
                header_blob = buffer[:header_end]
                rest = buffer[header_end + 4:]
            status, headers = _parse_headers(header_blob)
            entry["upstream_status"] = status
            chunked = headers.get("transfer-encoding", "").lower() == "chunked"
            content_length = headers.get("content-length")
            if content_length is not None and not chunked:
                length = max(0, _as_int(content_length, 0))
                data = rest
                while len(data) < length:
                    if entry["aborted"]:
                        return None
                    chunk = self._recv(entry, sock)
                    if chunk is None:
                        continue
                    if not chunk:
                        break
                    data += chunk
                data = data[:length]
            else:
                data = rest
                while True:
                    if entry["aborted"]:
                        return None
                    chunk = self._recv(entry, sock)
                    if chunk is None:
                        continue
                    if not chunk:
                        break
                    data += chunk
                if chunked:
                    data = _dechunk(data)
            if entry["aborted"]:
                return None
            ctype = headers.get("content-type") or "application/json; charset=utf-8"
            entry["resp_bytes"] = len(data)
            return status, ctype, data
        except Exception:
            if entry["aborted"]:
                return None
            entry["upstream_status"] = None
            payload = json.dumps(
                {"ok": False, "error": "upstream_unreachable"},
                separators=(",", ":"),
            ).encode("utf-8")
            entry["resp_bytes"] = len(payload)
            return 502, "application/json; charset=utf-8", payload
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def _rewrite(self, data, set_map):
        try:
            obj = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return data
        for path, value in _as_dict(set_map).items():
            _apply_set(obj, path, value)
        return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _serve(self, handler, status, ctype, data):
        try:
            handler.send_response(status)
            handler.send_header("Content-Type", ctype)
            handler.send_header("Content-Length", str(len(data)))
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.end_headers()
            handler.wfile.write(data)
            handler.wfile.flush()
        except OSError:
            handler.close_connection = True

    def _close_client(self, handler):
        try:
            handler.close_connection = True
        except Exception:
            pass
        try:
            handler.connection.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass

    def _open_window(self, rule, action):
        match = _as_dict(rule.get("match"))
        routes = action.get("routes")
        if not isinstance(routes, list):
            routes = []
        routes = [route for route in routes if isinstance(route, str)]
        mode = "cut" if action.get("type") == "then_cut_ms" else "hold"
        delay_ms = max(0, _as_int(action.get("ms"), 0))
        with self._lock:
            self._windows.append(
                {
                    "peer": match.get("peer", "any"),
                    "routes": routes,
                    "until": time.monotonic() + delay_ms / 1000.0,
                    "mode": mode,
                    "rule_id": rule.get("id"),
                }
            )

    def _active_window(self, peer, route):
        now = time.monotonic()
        with self._lock:
            self._windows = [window for window in self._windows if window["until"] > now]
            best = None
            for window in self._windows:
                if window["peer"] != "any" and window["peer"] != peer:
                    continue
                if route not in window["routes"]:
                    continue
                if best is None or window["until"] > best["until"]:
                    best = window
            return dict(best) if best is not None else None

    def _finish(self, entry, t0):
        if entry["done"]:
            return
        entry["done"] = True
        entry["t_done_ms"] = int(round(time.monotonic() * 1000.0))
        with self._lock:
            self._inflight.pop(entry["req_id"], None)
        line = {
            "req_id": entry["req_id"],
            "rule_id": entry["rule_id"],
            "rules_version": entry["rules_version"],
            "t_ms": entry["t_ms"],
            "t_done_ms": entry["t_done_ms"],
            "method": entry["method"],
            "route": entry["route"],
            "peer": entry["peer"],
            "deliver": entry["deliver"],
            "session": entry["session"],
            "action": entry["action"],
            "req_bytes": entry["req_bytes"],
            "upstream_status": entry["upstream_status"],
            "resp_bytes": entry["resp_bytes"],
            "held_ms": entry["held_ms"],
            "aborted": bool(entry["aborted"]),
        }
        self._write_log(line)

    def _write_log(self, line):
        payload = json.dumps(line, ensure_ascii=False, separators=(",", ":"))
        with self._log_lock:
            fh = self._log_fh
            if fh is None:
                return
            fh.write(payload + "\n")
            fh.flush()


def _matches_spec(specs, entry):
    for peer, route in specs:
        if peer != "any" and peer != entry["peer"]:
            continue
        if route != "any" and route != entry["route"]:
            continue
        return True
    return False


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Proxy de inyeccion de fallos para el bridge de DayZ Sandbox."
    )
    parser.add_argument("--upstream-port", type=int, required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--active", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--listen-port", type=int, default=0)
    args = parser.parse_args(argv)

    proxy = FaultProxy(
        args.upstream_port,
        args.rules,
        args.active,
        args.log,
        args.listen_port,
    )
    proxy.start()
    sys.stdout.write("listening port=%d\n" % proxy.port)
    sys.stdout.flush()
    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        proxy.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
